"""VantEdge Auto - Take 5 Scorecard V3. Streamlit shell: auth + Supabase data +
per-tier payload -> one embedded HTML/Chart.js dashboard. Three tiers:
store (own store), DM/AM (their region's stores), admin (all 15).

V3 shell additions:
- Professional, centered login card.
- Phone/Desktop toggle (?view=phone) next to Log out; desktop uses more width.
- Data-source health banner distinct from "no business yet" (review H5).
- Score cards moved out of the payload and generated on demand in the shell: Today,
  Yesterday (full day) and Last 7 days (color-coded matrix). Available to store, DM
  and admin.
- Bottom "Store guide" button opens the embedded user guide in a closable modal.
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
GUIDE = os.path.join(os.path.dirname(__file__), "Store_Level_Dashboard_Guide_V3.pdf")
def _hex(h): h=h.lstrip("#"); return tuple(int(h[i:i+2],16) for i in (0,2,4))


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
        admin = st.secrets.get("ADMIN_PASSWORD")  # no hardcoded fallback: admin fails closed if unset
        if pw in STORE_CODES:
            st.session_state.auth = ("store", pw); st.rerun()
        elif pw in DISTRICTS:
            st.session_state.auth = ("district", pw); st.rerun()
        elif admin and pw == admin:
            st.session_state.auth = ("admin", None); st.rerun()
        else:
            st.error("Access code not recognized.")


@st.cache_data(ttl=300, show_spinner="Loading store data…")
def build_payload(tier, allowed, scope_label, stamp):
    now = dt.datetime.now(CENTRAL)
    o, c = HOURS[now.weekday()]
    hours = [calc.hour_label(h) for h in range(o, c + 1)]
    def _pull(s):
        return s, fetch_today(s), fetch_history(s)
    with ThreadPoolExecutor(max_workers=8) as ex:
        fetched = list(ex.map(_pull, allowed))
    # Per-store isolation: one store's bad data must never crash the dashboard for
    # everyone. Build each store in its own try/except; drop and log any that fail.
    stores, rows, ok = {}, {}, []
    for s, td, hist in fetched:
        try:
            stores[s] = calc.build_store(s, CITY[s], region_of(s), td, hist, now)
            rows[s] = calc.build_admin_row(s, CITY[s], td, hist, now)
            ok.append(s)
        except Exception as e:
            print(f"[payload] store {s} skipped: {type(e).__name__}: {e}")
    allowed = [s for s in allowed if s in ok]
    return {"tier": tier, "scope_label": scope_label, "allowed": allowed,
            "regions": REGIONS if tier == "admin" else {}, "stores": stores, "rows": rows,
            "hours": hours, "date": stores[allowed[0]]["date"] if allowed else "",
            "asof": now.strftime("%-I:%M %p")}


# ---------------- score-card builders (on demand, in the shell) ----------------
def _pace(v):
    return "—" if v is None else (("+" if v >= 0 else "") + f"{v:g}%")

def _cards_today(sp):
    def rgb(k): return _hex(RGB.get(sp["status"].get(k, "flat"), NAVY))
    d = sp["diff"]
    return [
        ("Cars", f"{sp['cars']['sofar']:,.0f}", _pace(sp["cars"]["pace_pct"]) + " vs 4-wk", rgb("cars")),
        ("ARO", f"${sp['aro']['sofar']:,.2f}" if sp['aro']['sofar'] else "—", _pace(sp["aro"]["gap_pct"]) + " vs $125", rgb("aro")),
        ("Net revenue", f"${sp['net']['sofar']:,.0f}", _pace(sp["net"]["pace_pct"]) + " vs 4-wk", rgb("net")),
        ("Big 4 (% goal)", f"{sp['big4']['score']:,.0f}%" if sp['big4']['score'] is not None else "—", "goal 100%", rgb("big4")),
        ("LHPC", f"{sp['lhpc']['day']:.2f}" if sp['lhpc']['day'] else "—", "target 1.10", rgb("lhpc")),
        ("Differentials", f"{d['units']}", f"${d['amount']:,.0f} · {(d.get('pct') or 0):.0f}% of cars", _hex(PURPLE)),
    ]

def _cards_day(s):
    """Cards for a completed day from a calc.day_summary dict."""
    def aro_c(v): return _hex(GREEN) if v>=125 else (_hex(AMBER) if v>=117.5 else _hex(RED))
    def b4_c(v): return _hex(GREEN) if v>=90 else (_hex(AMBER) if v>=60 else _hex(RED))
    def lh_c(v): return _hex(GREEN) if v<=1.10 else (_hex(AMBER) if v<=1.25 else _hex(RED))
    return [
        ("Cars", f"{s['cars']:,}" if s['cars'] is not None else "—", "full day", _hex(NAVY)),
        ("ARO", f"${s['aro']:,.2f}" if s['aro'] is not None else "—", "target $125", aro_c(s['aro']) if s['aro'] is not None else _hex(NAVY)),
        ("Net revenue", f"${s['net']:,.0f}" if s['net'] is not None else "—", "full day", _hex(GREEN)),
        ("Big 4 (% goal)", f"{s['big4']:.0f}%" if s['big4'] is not None else "—", "goal 100%", b4_c(s['big4']) if s['big4'] is not None else _hex(NAVY)),
        ("LHPC", f"{s['lhpc']:.2f}" if s['lhpc'] is not None else "—", "target 1.10", lh_c(s['lhpc']) if s['lhpc'] is not None else _hex(NAVY)),
        ("Differentials", f"{s['diff']}", f"{(s['diff_pct'] or 0):.0f}% of cars", _hex(PURPLE)),
    ]

@st.cache_data(ttl=300, show_spinner=False)
def _scorecards(store, stamp):
    """Build (today_pdf?, yesterday_pdf?, week_pdf?) for one store. Today is built by
    the caller from the payload; here we handle the multi-day cards."""
    rows = fetch_days(store, SCORECARD_DAYS + 1)
    now = dt.datetime.now(CENTRAL); today = now.strftime("%Y-%m-%d")
    name = CITY.get(store, store)
    summ = calc.days_back_summaries(rows, SCORECARD_DAYS, today)
    yday = summ[0] if summ else None
    y_pdf = None
    if yday:
        try:
            ds = dt.date.fromisoformat(yday["date"]).strftime("%A, %b %-d %Y")
        except Exception:
            ds = yday["date"] or ""
        y_pdf = scorecard_pdf.build_scorecard_pdf(name, store, ds, "", _cards_day(yday))
    w_pdf = scorecard_pdf.build_week_matrix(name, store, summ) if summ else None
    return y_pdf, w_pdf, (yday["date"] if yday else None)


def _guide_b64():
    try:
        with open(GUIDE, "rb") as f: return base64.b64encode(f.read()).decode()
    except Exception: return ""

_dialog = getattr(st, "dialog", None) or getattr(st, "experimental_dialog", None)
def _show_guide():
    b64 = _guide_b64()
    if not b64:
        st.info("The store guide file isn't available in this deployment."); return
    st.markdown(f'<iframe src="data:application/pdf;base64,{b64}" width="100%" height="640" '
                f'style="border:1px solid #E2E7EE;border-radius:8px"></iframe>', unsafe_allow_html=True)
    st.download_button("Download the guide (PDF)", data=base64.b64decode(b64),
                       file_name="Store_Level_Dashboard_Guide.pdf", mime="application/pdf")
if _dialog:
    _show_guide = _dialog("Store guide")(_show_guide)


def scorecard_section(tier, allowed, payload, stamp):
    st.markdown("---")
    st.markdown("#### Score cards & guide")
    cstore, cbtn = st.columns([2, 1])
    with cstore:
        if tier == "store":
            store = allowed[0]
            st.caption(f"{CITY.get(store, store)} · #{store}")
        else:
            opts = [s for s in allowed if s in payload["stores"]] or allowed
            store = st.selectbox("Store", opts,
                                 format_func=lambda s: f"{CITY.get(s, s)} (#{s})",
                                 label_visibility="collapsed")
    with cbtn:
        if st.button("📖  Store guide", use_container_width=True):
            if _dialog: _show_guide()
            else: st.session_state["_guide_open"] = True

    sp = payload["stores"].get(store)
    y_pdf = w_pdf = None; ylabel = ""
    try:
        y_pdf, w_pdf, ydate = _scorecards(store, stamp)
        if ydate:
            try: ylabel = " (" + dt.date.fromisoformat(ydate).strftime("%b %-d") + ")"
            except Exception: ylabel = ""
    except Exception as e:
        st.caption(f"Multi-day cards unavailable right now: {type(e).__name__}")

    d1, d2, d3 = st.columns(3)
    with d1:
        if sp:
            try:
                today_pdf = scorecard_pdf.build_scorecard_pdf(sp["name"], store, sp["date"], sp["asof"], _cards_today(sp))
                st.download_button("⬇  Today", data=today_pdf, file_name=f"scorecard_{store}_today.pdf",
                                   mime="application/pdf", use_container_width=True)
            except Exception as e:
                st.caption(f"Today card error: {type(e).__name__}")
        else:
            st.button("⬇  Today", disabled=True, use_container_width=True)
    with d2:
        if y_pdf:
            st.download_button(f"⬇  Yesterday{ylabel}", data=y_pdf, file_name=f"scorecard_{store}_yesterday.pdf",
                               mime="application/pdf", use_container_width=True)
        else:
            st.button("⬇  Yesterday", disabled=True, use_container_width=True)
    with d3:
        if w_pdf:
            st.download_button("⬇  Last 7 days", data=w_pdf, file_name=f"scorecard_{store}_7day.pdf",
                               mime="application/pdf", use_container_width=True)
        else:
            st.button("⬇  Last 7 days", disabled=True, use_container_width=True)

    if not _dialog and st.session_state.get("_guide_open"):
        with st.expander("Store guide", expanded=True):
            _show_guide()
            if st.button("Close guide"):
                st.session_state["_guide_open"] = False; st.rerun()


# st.fragment (stable) with older-version fallback. A fragment can re-run on a timer
# WITHOUT reloading the page, so auto-refresh keeps the session (login).
_fragment = getattr(st, "fragment", None) or getattr(st, "experimental_fragment")


@_fragment(run_every=1800)   # every 30 min, in-session — no reload, no logout
def _dashboard_view(tier, allowed, scope, mobile):
    now = dt.datetime.now(CENTRAL)
    stamp = now.strftime("%Y-%m-%d-%H-%M")
    payload = build_payload(tier, allowed, scope, stamp)
    height = 5200 if mobile else 3000
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

    # data-source health banner (H5): distinguishes an outage from "no business yet".
    ok, msg = healthcheck()
    if not ok:
        st.warning("⚠️ Couldn't reach the data source just now — numbers below may be stale or empty. "
                   "Try Refresh in a minute. (This is different from a store simply not having opened yet.)")

    # ---- top controls: Refresh · Phone/Desktop · Log out. All re-run IN the session
    # (not a browser reload), so data updates without logging you out. ----
    _, cref, cview, clo = st.columns([7, 1.3, 1.4, 1.1])
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
    with clo:
        if st.button("Log out", use_container_width=True):
            del st.session_state.auth; st.cache_data.clear(); st.rerun()

    _dashboard_view(tier, allowed, scope, mobile)

    # bottom: score-card downloads + guide (built on demand, outside the fragment)
    stamp = dt.datetime.now(CENTRAL).strftime("%Y-%m-%d-%H")
    payload = build_payload(tier, allowed, scope, dt.datetime.now(CENTRAL).strftime("%Y-%m-%d-%H-%M"))
    scorecard_section(tier, allowed, payload, stamp)


if __name__ == "__main__":
    main()
