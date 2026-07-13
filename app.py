"""VantEdge Auto - Take 5 Scorecard V3. Streamlit shell: auth + Supabase data +
per-tier payload -> one embedded HTML/Chart.js dashboard. Three tiers:
store (own store), DM/AM (their region's stores), admin (all 15).

V3 shell:
- Professional centered login; phone/desktop toggle (?view=phone) with compact mobile
  controls; data-source health banner (H5).
- Score cards are embedded in the dashboard itself (Today from live data + Yesterday and
  Last-7-days from an hourly cache) and rendered as a section inside the store view.
- User guide opens in a modal as page IMAGES (reliable on every device, unlike a PDF
  data-URI) with a download fallback.
"""
import base64, os, datetime as dt
from concurrent.futures import ThreadPoolExecutor
import streamlit as st
import streamlit.components.v1 as components

from config import (BRAND, CENTRAL, STORE_CODES, CITY, REGIONS, DISTRICTS,
                    HOURS, NAVY, GREEN, RED, AMBER, PURPLE, SCORECARD_DAYS)
import calc, dashboard, scorecard_pdf
from datasource import fetch_today, fetch_history, fetch_days, healthcheck

st.set_page_config(page_title=f"{BRAND} - Take 5 Scorecard", layout="wide",
                   initial_sidebar_state="collapsed")
st.markdown("""<style>
 .block-container{padding:1rem 1rem 0;max-width:100%;}
 #MainMenu,footer{visibility:hidden;}
 header[data-testid="stHeader"]{display:none!important;}
 [data-testid="stToolbar"],[data-testid="stDecoration"],[data-testid="stStatusWidget"],
 .stDeployButton,[data-testid="stAppDeployButton"]{display:none!important;}
 .loginwrap{max-width:420px;margin:6vh auto 0;}
 .loginwrap .lc{background:#fff;border:1px solid #E2E7EE;border-radius:12px;
   box-shadow:0 6px 24px rgba(15,23,42,.08);padding:26px 26px 20px;text-align:center;}
</style>""", unsafe_allow_html=True)

RGB = {"g": GREEN, "r": RED, "a": AMBER, "flat": NAVY}
def _hex(h): h=h.lstrip("#"); return tuple(int(h[i:i+2],16) for i in (0,2,4))

def _guide_path():
    here = os.path.dirname(os.path.abspath(__file__))
    for p in (os.path.join(here, "Store_Level_Dashboard_Guide_V3.pdf"),
              os.path.join(os.getcwd(), "Store_Level_Dashboard_Guide_V3.pdf"),
              "Store_Level_Dashboard_Guide_V3.pdf"):
        if os.path.exists(p): return p
    return None


def region_of(store):
    for r, ids in REGIONS.items():
        if store in ids:
            return r
    return ""


def is_mobile():
    try: return st.query_params.get("view") == "phone"
    except Exception: return False


def login_view():
    st.markdown(f"<div style='background:{NAVY};border-radius:10px;padding:16px 22px;color:#fff;"
                f"margin-bottom:8px;'><span style='font-size:1.3rem;font-weight:800;'>VantEdge Auto</span>"
                f"<span style='color:#9FB4CC;font-size:.8rem;'> &nbsp;·&nbsp; Take 5 Scorecard</span></div>",
                unsafe_allow_html=True)
    st.markdown("<div class='loginwrap'><div class='lc'>"
                "<div style='font-size:1.05rem;font-weight:800;color:#14273F;'>Welcome back</div>"
                "<div style='color:#5B6472;font-size:.82rem;margin:4px 0 14px;'>Enter your access code to view your scorecard.</div>",
                unsafe_allow_html=True)
    with st.form("login"):
        pw = st.text_input("code", type="password", label_visibility="collapsed", placeholder="Access code")
        ok = st.form_submit_button("Enter", type="primary", use_container_width=True)
    st.markdown("<div style='color:#8A93A2;font-size:.72rem;margin-top:12px;'>"
                "Store, area-manager and admin codes each open a different view.</div></div></div>",
                unsafe_allow_html=True)
    if ok:
        admin = st.secrets.get("ADMIN_PASSWORD")
        if pw in STORE_CODES:
            st.session_state.auth = ("store", pw); st.rerun()
        elif pw in DISTRICTS:
            st.session_state.auth = ("district", pw); st.rerun()
        elif admin and pw == admin:
            st.session_state.auth = ("admin", None); st.rerun()
        else:
            st.error("Access code not recognized.")


# ---------------- score-card card builders ----------------
def _pace(v):
    return "—" if v is None else (("+" if v >= 0 else "") + f"{v:g}%")

def _cards_today(sp):
    def rgb(k): return _hex(RGB.get(sp["status"].get(k, "flat"), NAVY))
    d = sp["diff"]
    return [
        ("Cars", f"{sp['cars']['sofar']:,.0f}", _pace(sp["cars"]["pace_pct"]) + " vs 4-wk", rgb("cars")),
        ("ARO", f"${sp['aro']['sofar']:,.2f}" if sp['aro']['sofar'] else "—", _pace(sp["aro"]["gap_pct"]) + " vs $125", rgb("aro")),
        ("Net revenue", f"${sp['net']['sofar']:,.0f}", _pace(sp["net"]["pace_pct"]) + " vs 4-wk", rgb("net")),
        ("Big 4 attach %", f"{sp['big4']['pct']:,.0f}%" if sp['big4']['pct'] is not None else "—", "goal 53%", rgb("big4")),
        ("LHPC", f"{sp['lhpc']['day']:.2f}" if sp['lhpc']['day'] else "—", "target 1.10", rgb("lhpc")),
        ("Differentials", f"{d['units']}", f"${d['amount']:,.0f} · {(d.get('pct') or 0):.0f}% of cars", _hex(PURPLE)),
    ]

def _cards_day(s):
    def aro_c(v): return _hex(GREEN) if v>=125 else (_hex(AMBER) if v>=117.5 else _hex(RED))
    def b4_c(v): return _hex(GREEN) if v>=53 else (_hex(AMBER) if v>=32 else _hex(RED))
    def lh_c(v): return _hex(GREEN) if v<=1.10 else (_hex(AMBER) if v<=1.25 else _hex(RED))
    return [
        ("Cars", f"{s['cars']:,}" if s['cars'] is not None else "—", "full day", _hex(NAVY)),
        ("ARO", f"${s['aro']:,.2f}" if s['aro'] is not None else "—", "target $125", aro_c(s['aro']) if s['aro'] is not None else _hex(NAVY)),
        ("Net revenue", f"${s['net']:,.0f}" if s['net'] is not None else "—", "full day", _hex(GREEN)),
        ("Big 4 attach %", f"{s['big4']:.0f}%" if s['big4'] is not None else "—", "goal 53%", b4_c(s['big4']) if s['big4'] is not None else _hex(NAVY)),
        ("LHPC", f"{s['lhpc']:.2f}" if s['lhpc'] is not None else "—", "target 1.10", lh_c(s['lhpc']) if s['lhpc'] is not None else _hex(NAVY)),
        ("Differentials", f"{s['diff']}", f"{(s['diff_pct'] or 0):.0f}% of cars", _hex(PURPLE)),
    ]

@st.cache_data(ttl=3600, show_spinner=False)
def _multiday_b64(store, hourstamp):
    """Yesterday + weekly PDFs for one store, refreshed hourly (needs the extra
    multi-day fetch). Returns base64 strings + a yesterday date label."""
    out = {"yesterday": "", "week": "", "ylabel": ""}
    rows = fetch_days(store, SCORECARD_DAYS + 1)
    today = dt.datetime.now(CENTRAL).strftime("%Y-%m-%d")
    name = CITY.get(store, store)
    summ = calc.days_back_summaries(rows, SCORECARD_DAYS, today)
    if not summ:
        return out
    y = summ[0]
    try:
        d = dt.date.fromisoformat(y["date"]); ds = d.strftime("%A, %b %-d %Y"); out["ylabel"] = " (" + d.strftime("%b %-d") + ")"
    except Exception:
        ds = y["date"] or ""
    try:
        out["yesterday"] = base64.b64encode(scorecard_pdf.build_scorecard_pdf(name, store, ds, "", _cards_day(y))).decode()
    except Exception as e:
        print(f"[scorecard] yesterday {store}: {type(e).__name__}: {e}")
    try:
        out["week"] = base64.b64encode(scorecard_pdf.build_week_matrix(name, store, summ)).decode()
    except Exception as e:
        print(f"[scorecard] week {store}: {type(e).__name__}: {e}")
    return out


@st.cache_data(ttl=300, show_spinner="Loading store data…")
def build_payload(tier, allowed, scope_label, stamp):
    now = dt.datetime.now(CENTRAL)
    o, c = HOURS[now.weekday()]
    hours = [calc.hour_label(h) for h in range(o, c + 1)]
    def _pull(s):
        return s, fetch_today(s), fetch_history(s)
    with ThreadPoolExecutor(max_workers=8) as ex:
        fetched = list(ex.map(_pull, allowed))
    stores, rows, ok = {}, {}, []
    for s, td, hist in fetched:
        try:
            stores[s] = calc.build_store(s, CITY[s], region_of(s), td, hist, now)
            rows[s] = calc.build_admin_row(s, CITY[s], td, hist, now)
            ok.append(s)
        except Exception as e:
            print(f"[payload] store {s} skipped: {type(e).__name__}: {e}")
    allowed = [s for s in allowed if s in ok]
    # embed the score cards: today from live data, yesterday/week from the hourly cache
    hourstamp = stamp[:13]
    pdf = {}
    for s in allowed:
        sp = stores[s]
        try:
            today_b64 = base64.b64encode(scorecard_pdf.build_scorecard_pdf(
                sp["name"], s, sp["date"], sp["asof"], _cards_today(sp))).decode()
        except Exception as e:
            print(f"[scorecard] today {s}: {type(e).__name__}: {e}"); today_b64 = ""
        md = _multiday_b64(s, hourstamp)
        pdf[s] = {"today": today_b64, "yesterday": md["yesterday"], "week": md["week"], "ylabel": md["ylabel"]}
    return {"tier": tier, "scope_label": scope_label, "allowed": allowed,
            "regions": REGIONS if tier == "admin" else {}, "stores": stores, "rows": rows,
            "hours": hours, "date": stores[allowed[0]]["date"] if allowed else "",
            "asof": now.strftime("%-I:%M %p"), "pdf": pdf}


# ---------------- user guide (rendered as images -> reliable everywhere) ----------------
@st.cache_data(show_spinner=False)
def _guide_images():
    path = _guide_path()
    if not path: return []
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(path); imgs = []
        for page in doc:
            imgs.append(page.get_pixmap(dpi=110).tobytes("png"))
        doc.close(); return imgs
    except Exception as e:
        print(f"[guide] render failed: {type(e).__name__}: {e}"); return []

def _guide_body():
    path = _guide_path()
    if path:
        try:
            with open(path, "rb") as f:
                st.download_button("⬇  Download the guide (PDF)", f.read(),
                                   file_name="Store_Level_Dashboard_Guide.pdf",
                                   mime="application/pdf", use_container_width=True)
        except Exception:
            pass
    imgs = _guide_images()
    if imgs:
        for im in imgs:
            st.image(im, use_container_width=True)
    elif not path:
        st.info("The store guide file isn't in this deployment. Make sure "
                "Store_Level_Dashboard_Guide_V3.pdf is uploaded alongside the app.")
    else:
        st.info("Couldn't render the guide inline here — use the download button above to open the PDF.")

_dialog = getattr(st, "dialog", None) or getattr(st, "experimental_dialog", None)
if _dialog:
    @_dialog("Store guide", width="large")
    def _open_guide():
        _guide_body()
else:
    def _open_guide():
        st.session_state["_guide_open"] = True


# st.fragment (stable) with older-version fallback: re-runs on a timer WITHOUT reloading
# the page, so auto-refresh keeps the session (login).
_fragment = getattr(st, "fragment", None) or getattr(st, "experimental_fragment")


@_fragment(run_every=1800)
def _dashboard_view(tier, allowed, scope, mobile):
    now = dt.datetime.now(CENTRAL)
    stamp = now.strftime("%Y-%m-%d-%H-%M")
    payload = build_payload(tier, allowed, scope, stamp)
    height = 6200 if mobile else 3200
    components.html(dashboard.html(payload, mobile=mobile), height=height, scrolling=True)


def main():
    if "auth" not in st.session_state:
        login_view(); return
    role, code = st.session_state.auth
    if role == "store":
        tier, allowed, scope = "store", [code], f"{CITY[code]} · #{code}"
    elif role == "district":
        name, ids = DISTRICTS[code]; tier, allowed, scope = "district", ids, f"{name} · {len(ids)} stores"
    else:
        tier, allowed, scope = "admin", STORE_CODES, "All Stores · 15"

    mobile = is_mobile()
    if mobile:
        st.markdown("<style>.stButton>button{padding:.4rem .35rem;font-size:.82rem;min-height:0}"
                    "div[data-testid='stHorizontalBlock']{gap:.4rem}</style>", unsafe_allow_html=True)

    ok, msg = healthcheck()
    if not ok:
        st.warning("⚠️ Couldn't reach the data source just now — numbers below may be stale or empty. "
                   "Try Refresh in a minute. (This is different from a store simply not having opened yet.)")

    # top controls: Refresh · Phone/Desktop · Guide · Log out. All re-run IN the session.
    if mobile:
        cref, cview, cg, clo = st.columns(4)
    else:
        _, cref, cview, cg, clo = st.columns([6, 1.3, 1.4, 1.3, 1.1])
    with cref:
        if st.button("↻ Refresh", use_container_width=True):
            st.cache_data.clear(); st.rerun()
    with cview:
        if mobile:
            if st.button("🖥 Desktop", use_container_width=True):
                st.query_params["view"] = "desktop"; st.rerun()
        else:
            if st.button("📱 Phone", use_container_width=True):
                st.query_params["view"] = "phone"; st.rerun()
    with cg:
        if st.button("📖 Guide", use_container_width=True):
            _open_guide()
    with clo:
        if st.button("Log out", use_container_width=True):
            del st.session_state.auth; st.cache_data.clear(); st.rerun()

    # fallback guide (only when st.dialog isn't available)
    if not _dialog and st.session_state.get("_guide_open"):
        with st.expander("Store guide", expanded=True):
            _guide_body()
            if st.button("Close guide"):
                st.session_state["_guide_open"] = False; st.rerun()

    _dashboard_view(tier, allowed, scope, mobile)


if __name__ == "__main__":
    main()
