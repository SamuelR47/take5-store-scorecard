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
                    HOURS, NAVY, GREEN, RED, AMBER, PURPLE, MUTE, SCORECARD_DAYS,
                    ARO_TARGET, LHPC_TARGET, BIG4_GOAL)
import calc, dashboard, scorecard_pdf, identity, datastore, web
from datasource import fetch_today, fetch_history, fetch_days, healthcheck
from config import BIG4_TARGETS, DOW_FULL, TASKS_BY_DOW

_sb_state = "expanded" if (st.session_state.get("auth") or (None,))[0] == "admin" else "collapsed"
st.set_page_config(page_title=f"{BRAND} - Take 5 Scorecard", layout="wide",
                   initial_sidebar_state=_sb_state)
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


def _parse_ts(s):
    """Parse a Supabase timestamptz string to an aware datetime, or None."""
    if not s:
        return None
    try:
        return dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except Exception:
        return None


def is_mobile():
    try: return st.query_params.get("view") == "phone"
    except Exception: return False


def _picker(options, current, key, mobile):
    """Segmented-control 'tabs' on desktop where available; compact selectbox on phone
    or older Streamlit. Returns the selected option string."""
    sc = getattr(st, "segmented_control", None)
    if sc and not mobile:
        try:
            return sc("scope", options, default=current if current in options else options[0],
                      key=key, label_visibility="collapsed")
        except Exception:
            pass
    idx = options.index(current) if current in options else 0
    return st.selectbox("scope", options, index=idx, key=key, label_visibility="collapsed")


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
    # F: newest pull_time across the in-scope stores = when the data was last sourced.
    newest = None
    for _s, td, _hist in fetched:
        for r in td:
            ts = _parse_ts(r.get("pull_time"))
            if ts and (newest is None or ts > newest):
                newest = ts
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
    # Admin nav shows only regions that actually have in-scope stores, so a region-scoped
    # admin view (V4 scope tabs) doesn't list empty regions in the in-component nav.
    regions = ({r: [s for s in ids if s in allowed]
                for r, ids in REGIONS.items() if any(s in allowed for s in ids)}
               if tier == "admin" else {})
    return {"tier": tier, "scope_label": scope_label, "allowed": allowed,
            "regions": regions, "stores": stores, "rows": rows,
            "hours": hours, "date": stores[allowed[0]]["date"] if allowed else "",
            "asof": now.strftime("%-I:%M %p"), "pdf": pdf,
            "sourced_epoch": newest.timestamp() if newest else None}


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


# ---------------- V4 (B-3): admin/DM website payload ----------------
_WEB_PALETTE = [NAVY, "#2E6FB7", "#158A5A", "#B57611", PURPLE, RED, "#0E7490", "#B45309",
                "#7C3AED", "#0891B2", "#CA8A04", "#BE185D", "#15803D", "#1D4ED8", "#9A3412"]


def _target_curve(tgt, n):
    """Linear ramp from 0 to the day target across the open hours — the red target line."""
    if tgt is None or not n:
        return []
    return [round(tgt * (i + 1) / n, 2) for i in range(n)]


def _web_detail(sp):
    """Map a calc.build_store payload into the exact shape web.py's detail view expects."""
    n = len(sp["hours"]); s = sp["status"]; a = sp["aro"]; b = sp["big4"]; l = sp["lhpc"]
    def cum(d):
        return {"actual": d["actual"], "est": d["est"],
                "target": d.get("target_curve") or _target_curve(d.get("tgt"), n),
                "sofar": d["sofar"], "est_close": d["est_close"], "norm": d.get("norm"),
                "pace": d.get("pace_pct"), "status": calc.st_pace(d.get("pace_pct")),
                "tgt": d.get("tgt"), "tgtSrc": d.get("tgtSrc"), "wk": d.get("wk", [])}
    return {"name": sp["name"], "id": sp["id"], "region": sp.get("region", ""), "open": sp.get("open", ""),
            "now": sp["now"], "hours": sp["hours"],
            "kpi": {"cars": round(sp["cars"]["sofar"]), "carsNorm": sp["cars"].get("norm"),
                    "carsPace": sp["cars"].get("pace_pct"),
                    "aro": a.get("sofar") or 0, "aroGap": a.get("gap_pct"),
                    "net": round(sp["net"]["sofar"]), "netNorm": sp["net"].get("norm"),
                    "netPace": sp["net"].get("pace_pct"),
                    "big4": b.get("pct") or 0, "lhpc": l.get("day") or 0,
                    "carsStatus": s["cars"], "aroStatus": s["aro"], "netStatus": s["net"],
                    "big4Status": s["big4"], "lhpcStatus": s["lhpc"]},
            "cars": cum(sp["cars"]), "net": cum(sp["net"]),
            "aro": {"run": a["run"], "sofar": a.get("sofar") or 0, "gap": a.get("gap_pct"),
                    "target": a.get("target") or 125},
            "big4": {"run": b["run"], "pct": b.get("pct") or 0, "units": b.get("units") or 0,
                     "target": b.get("target"), "items": b.get("items", [])},
            "lhpc": {"roll": l["roll"], "hours": l["hours"], "day": l.get("day") or 0,
                     "now": l.get("now"), "target": l.get("target"), "variance": l.get("variance")},
            "drivers": a.get("drivers", []), "ops": sp.get("ops", [])}


@st.cache_data(ttl=300, show_spinner="Loading dashboard…")
def build_web_payload(tier, allowed, scope_label, stamp):
    now = dt.datetime.now(CENTRAL)
    try:
        tgts = datastore.get_targets()
    except Exception:
        tgts = {}
    def _pull(s):
        return s, fetch_today(s), fetch_history(s), fetch_days(s, 12)
    with ThreadPoolExecutor(max_workers=8) as ex:
        fetched = list(ex.map(_pull, allowed))
    today = now.strftime("%Y-%m-%d")
    dates = [(now.date() - dt.timedelta(days=k)).isoformat() for k in range(7, 0, -1)]
    labels = [dt.date.fromisoformat(d).strftime("%-m/%-d") for d in dates]
    # task completions for the historical "Task" metric (one cheap cached read per date)
    comp_by_date = {}
    for dd in dates + [today]:
        try:
            comp_by_date[dd] = datastore.get_completions(dd)
        except Exception:
            comp_by_date[dd] = {}
    rows, detail, hstores, newest, idx = [], {}, [], None, 0
    for s, td, hist, daily in fetched:
        try:
            sp = calc.build_store(s, CITY[s], region_of(s), td, hist, now, tgts.get(s))
            ar = calc.build_admin_row(s, CITY[s], td, hist, now)
        except Exception as e:
            print(f"[web] store {s}: {type(e).__name__}: {e}"); continue
        rows.append({"id": s, "name": CITY[s], "region": region_of(s), "cars": ar["cars"],
                     "net": ar["net"], "aro": ar["aro"], "lhpc": ar["lhpc"], "big4": ar["big4"],
                     "pace": ar["pace"], "status": calc.st_pace(ar["pace"]), "heat": ar.get("heat")})
        d = _web_detail(sp)
        d["messages"] = [{"from": m.get("from_user"), "body": m.get("body"),
                          "when": (m.get("sent_at") or "")[:16].replace("T", " ")}
                         for m in datastore.get_inbox("store", s)]
        # V3 score cards reused: today built fresh, yesterday+week from the hourly cache
        # (~9 KB/store base64 -> ~0.13 MB for all 15, measured; safe to embed, cf. review M6).
        try:
            tb = base64.b64encode(scorecard_pdf.build_scorecard_pdf(
                sp["name"], s, sp["date"], sp["asof"], _cards_today(sp))).decode()
        except Exception as e:
            print(f"[web scorecard today] {s}: {type(e).__name__}: {e}"); tb = ""
        md = _multiday_b64(s, stamp[:13])
        d["scorecards"] = {"today": tb, "yesterday": md.get("yesterday", ""),
                           "week": md.get("week", ""), "ylabel": md.get("ylabel", "")}
        detail[s] = d
        for r in td:
            ts = _parse_ts(r.get("pull_time"))
            if ts and (newest is None or ts > newest):
                newest = ts
        summ = {x["date"]: x for x in calc.days_back_summaries(daily, 14, today) if x}
        live = {"cars": sp["cars"]["sofar"], "net": sp["net"]["sofar"], "aro": sp["aro"].get("sofar"),
                "big4": sp["big4"].get("pct"), "lhpc": sp["lhpc"].get("day")}
        metrics = {k: [(summ.get(d) or {}).get(k) for d in dates] + [live[k]]
                   for k in ("cars", "net", "aro", "big4", "lhpc")}
        tvals, titems = [], []
        for dd in list(dates) + [today]:
            tl = TASKS_BY_DOW.get(dt.date.fromisoformat(dd).weekday(), [])
            dc = (comp_by_date.get(dd) or {}).get(s, {})
            di = [t for t in tl if t in dc]
            tvals.append(round(len(di) / len(tl) * 100) if tl else 0); titems.append(di)
        metrics["task"] = tvals
        hstores.append({"id": s, "name": f"{CITY[s]} {s}",
                        "color": _WEB_PALETTE[idx % len(_WEB_PALETTE)], "metrics": metrics,
                        "taskItems": titems}); idx += 1
    liveR = [r for r in rows if r["cars"] is not None]
    tc = sum(r["cars"] for r in liveR); tn = sum(r["net"] or 0 for r in liveR)
    b4R = [r for r in liveR if r["big4"] is not None and r["cars"]]
    b4 = (sum(r["big4"] * r["cars"] for r in b4R) / sum(r["cars"] for r in b4R)) if b4R else None
    paced = [r["pace"] for r in liveR if r["pace"] is not None]
    kpis = {"stores": len(rows), "cars": tc, "carsPace": round(sum(paced) / len(paced), 1) if paced else None,
            "net": tn, "aro": round(tn / tc, 1) if tc else None, "big4": round(b4, 1) if b4 is not None else None}
    sourced = ""
    if newest:
        srcd = dt.datetime.fromtimestamp(newest.timestamp(), CENTRAL)
        mins = int((now - srcd).total_seconds() // 60)
        sourced = f"sourced {srcd.strftime('%-I:%M %p')} · {'just now' if mins <= 0 else str(mins) + 'm ago'}"
    regions = (REGIONS if tier == "admin"
               else {k: v for k, v in REGIONS.items() if any(x in allowed for x in v)})
    o, c = HOURS[now.weekday()]
    heat_hours = (["Before " + calc.hour_label(o)] + [calc.hour_label(h) for h in range(o, c + 1)]
                  + ["After " + calc.hour_label(c)])
    return {"tier": tier, "mode": "store" if tier == "store" else "full",
            "scopeName": scope_label, "asof": now.strftime("%-I:%M %p"),
            "sourced": sourced, "kpis": kpis, "regions": regions, "rows": rows, "detail": detail,
            "heatHours": heat_hours,
            "hist": {"days": labels, "today": "Today", "stores": hstores, "metric": "cars"}}


# run_every=600 (10 min): the scraper is hourly, so this catches a new pull within
# ~10 min while staying cheap. NOTE: st.fragment only supports a fixed INTERVAL, not a
# wall-clock time, so we can't literally fire "5 min after the scraper"; the freshness
# line/label shows the true last-sourced time regardless, so any staleness is visible.
@_fragment(run_every=600)
def _dashboard_view(tier, allowed, scope, mobile, startview="overview"):
    now = dt.datetime.now(CENTRAL)
    stamp = now.strftime("%Y-%m-%d-%H-%M")
    # V4 (B-3d): every tier renders the website component. The native sidebar chooses which
    # section it opens on (startView). Store logins get a store-locked view (their store only).
    payload = dict(build_web_payload(tier, allowed, scope, stamp))
    payload["startView"] = startview
    components.html(web.html(payload), height=(1600 if mobile else 900), scrolling=True)


# ---------------- V4 (D): historical performance (DM + admin, read-only) ----------------
_HIST_METRICS = {"Cars": "cars", "Net revenue": "net", "ARO ($/car)": "aro",
                 "Big 4 attach %": "big4", "LHPC (hrs/car)": "lhpc"}
_HIST_TARGET = {"aro": ARO_TARGET, "lhpc": LHPC_TARGET, "big4": BIG4_GOAL}
_HIST_FMT = {"cars": lambda v: f"{v:,.0f}", "net": lambda v: f"${v:,.0f}",
             "aro": lambda v: f"${v:,.2f}", "big4": lambda v: f"{v:.1f}%", "lhpc": lambda v: f"{v:.2f}"}


@st.cache_data(ttl=1800, show_spinner=False)
def _hist_rows(store, daystamp):
    """~5 weeks of daily rows for one store, cached per day (daystamp = today's date)."""
    return fetch_days(store, 35)


def _history_section(role, user, mobile):
    st.markdown("---")
    st.markdown("#### Historical performance — last week vs the 4-week average")
    opts = list(STORE_CODES) if role == "admin" else list(user["stores"])
    labels = {s: f"{CITY.get(s, s)} #{s}" for s in opts}

    mlabel = _picker(list(_HIST_METRICS), "Cars", "hist_metric", mobile)
    metric = _HIST_METRICS[mlabel]
    default = opts if role == "district" else opts[:5]
    sel = st.multiselect("Stores", options=opts, default=default,
                         format_func=lambda s: labels[s], key="hist_stores")
    if not sel:
        st.caption("Pick at least one store to chart."); return

    today = dt.datetime.now(CENTRAL).strftime("%Y-%m-%d")
    try:
        import plotly.graph_objects as go
    except Exception:
        st.info("Charting library unavailable in this deployment."); return

    fig = go.Figure()
    table = []
    fmt = _HIST_FMT.get(metric, lambda v: v)
    for s in sel:
        series = calc.weekly_series(_hist_rows(s, today), today, metric, weeks=5)
        if not series:
            continue
        xs = [p["label"] for p in series]
        ys = [p["value"] for p in series]
        fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines+markers", name=labels[s],
                                 connectgaps=True))
        last, base, pct = calc.week_vs_baseline(series)
        table.append({"Store": labels[s],
                      "Last week": fmt(last) if last is not None else "—",
                      "4-wk avg": fmt(base) if base is not None else "—",
                      "Δ vs 4-wk": (f"{pct:+.1f}%" if pct is not None else "—")})
    tgt = _HIST_TARGET.get(metric)
    if tgt is not None:
        fig.add_hline(y=tgt, line_dash="dot", line_color=MUTE,
                      annotation_text=f"target {fmt(tgt)}", annotation_position="top left")
    fig.update_layout(height=360, margin=dict(l=10, r=10, t=10, b=10),
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
                      yaxis_title=mlabel, xaxis_title=None,
                      plot_bgcolor="#FFFFFF", paper_bgcolor="rgba(0,0,0,0)")
    fig.update_xaxes(showgrid=False); fig.update_yaxes(gridcolor="#E2E7EE")
    st.plotly_chart(fig, use_container_width=True)
    if table:
        st.dataframe(table, use_container_width=True, hide_index=True)
    st.caption("Weekly totals over the last 5 seven-day windows; ARO / Big 4 / LHPC are "
               "volume-weighted across each week. Baseline = average of the 4 weeks before last week.")


# ---------------- V4 (B-2): admin per-store targets editor (write path) ----------------
_TGT_FIELDS = ([("cars_boost", "Cars boost %"), ("net_boost", "Net boost %"),
                ("aro_target", "ARO target $"), ("lhpc_target", "LHPC target")]
               + [("big4_" + n, n + " %") for n in BIG4_TARGETS])


def _task_checklist(user):
    """Store-login daily task panel (left column). Native checkboxes → task_completions."""
    store = user["code"]
    now = dt.datetime.now(CENTRAL); today = now.strftime("%Y-%m-%d")
    tasks = TASKS_BY_DOW.get(now.weekday(), [])
    try:
        done = datastore.get_completions(today).get(store, {})
    except Exception:
        done = {}
    n = len(tasks); c = sum(1 for t in tasks if t in done)
    st.markdown("#### Today's tasks")
    st.caption(f"{DOW_FULL[now.weekday()]} · {c}/{n} done" + (f" · {round(c/n*100)}%" if n else ""))
    for i, t in enumerate(tasks):
        checked = t in done
        v = st.checkbox(t, value=checked, key=f"tk_{store}_{i}")
        if v != checked:
            try:
                if v:
                    datastore.complete_task(store, today, t, user.get("label"))
                else:
                    datastore.uncomplete_task(store, today, t)
            except Exception as e:
                st.error(f"Save failed: {type(e).__name__}")
            st.rerun()


def _daily_task_admin(user):
    """Admin Daily task tab: stores (rows) x today's tasks (cols), green checks + % complete."""
    import pandas as pd
    now = dt.datetime.now(CENTRAL); today = now.strftime("%Y-%m-%d"); wd = now.weekday()
    tasks = TASKS_BY_DOW.get(wd, [])
    st.markdown("#### Daily task")
    st.caption(f"{DOW_FULL[wd]} · {today} — green = complete")
    try:
        comp = datastore.get_completions(today)
    except Exception:
        comp = {}
    rows = []
    for s in STORE_CODES:
        d = comp.get(s, {}); done = sum(1 for t in tasks if t in d)
        row = {"Store": f"{CITY[s]} #{s}", "%": round(done / len(tasks) * 100) if tasks else 0}
        for t in tasks:
            row[t] = "✓" if t in d else ""
        rows.append(row)
    df = pd.DataFrame(rows)
    sty = df.style.applymap(lambda v: "background-color:#E7F3EC;color:#158A5A;font-weight:700"
                            if v == "✓" else "", subset=list(tasks))
    st.dataframe(sty, hide_index=True, use_container_width=True)


def _messages_admin(user):
    """Admin Messages tab: compose a one-way message to a single store + recent-sent list."""
    import pandas as pd
    labels = {s: f"{CITY.get(s, s)} #{s}" for s in STORE_CODES}
    st.markdown("#### Messages")
    st.caption("Send a message to one store. It shows on that store's scorecard (right side).")
    store = st.selectbox("Store", STORE_CODES, format_func=lambda s: labels[s], key="msg_store")
    body = st.text_area("Message", key="msg_body",
                        placeholder="e.g. Great Big 4 day — keep pushing the coolant exchange.")
    name = st.text_input("Your name", key="msg_name", placeholder="John Doe")
    if st.button("Send message", type="primary"):
        if body.strip():
            try:
                datastore.send_message(identity.attribution(user, name), "store", body.strip(), to_store=store)
                st.success(f"Sent to {labels[store]}.")
            except Exception as e:
                st.error(f"Couldn't send: {type(e).__name__}: {e}")
        else:
            st.warning("Write a message first.")
    st.markdown("##### Recent messages")
    try:
        sent = datastore.get_sent(50)
    except Exception:
        sent = []
    if sent:
        rows = [{"Sent": (m.get("sent_at") or "")[:16].replace("T", " "),
                 "To": labels.get(str(m.get("to_store")), m.get("to_store") or m.get("to_scope")),
                 "From": m.get("from_user"), "Message": m.get("body")} for m in sent]
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    else:
        st.caption("No messages sent yet.")


def _targets_view(user):
    """Read-only targets view with an Edit button (admin left-nav 'Targets' tab)."""
    import pandas as pd
    if st.session_state.get("tgt_editing"):
        _targets_editor(user)
        if st.button("Done — back to view"):
            st.session_state["tgt_editing"] = False; st.rerun()
        return
    st.markdown("#### Store targets")
    st.caption("Cars and Net are a % boost on each store's 4-week average. ARO $, LHPC, and "
               "each Big 4 item are absolute targets. Blank = default.")
    cur = datastore.get_targets()
    rows = []
    for s in STORE_CODES:
        t = cur.get(s, {})
        row = {"Store": f"{CITY.get(s, s)} #{s}"}
        for key, lab in _TGT_FIELDS:
            row[lab] = t.get(key)
        rows.append(row)
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    if st.button("Edit targets", type="primary"):
        st.session_state["tgt_editing"] = True; st.rerun()


def _targets_editor(user):
    import pandas as pd
    st.markdown("#### Edit store targets")
    st.caption("Cars and Net are a % boost on each store's 4-week average. ARO $, LHPC, and "
               "each Big 4 item are absolute targets. Leave a cell blank to use the default.")
    cur = datastore.get_targets()
    rows = []
    for s in STORE_CODES:
        t = cur.get(s, {})
        row = {"Store": f"{CITY.get(s, s)} #{s}", "_id": s}
        for key, lab in _TGT_FIELDS:
            row[lab] = t.get(key)
        rows.append(row)
    df = pd.DataFrame(rows)
    edited = st.data_editor(df, key="targets_editor", hide_index=True,
                            use_container_width=True, disabled=["Store"],
                            column_config={"_id": None})
    name = st.text_input("Your name (saved with each change)", key="tgt_name",
                         placeholder="John Doe")
    if st.button("Save targets", type="primary"):
        who = identity.attribution(user, name)
        edits = datastore.target_edits(cur, edited.to_dict("records"), _TGT_FIELDS)
        try:
            for s, key, val in edits:
                if val is None:
                    datastore.delete_target(s, key)
                else:
                    datastore.set_target(s, key, val, who)
            st.success(f"Saved {len(edits)} change(s)." if edits else "No changes to save.")
        except Exception as e:
            st.error(f"Couldn't save targets: {type(e).__name__}: {e}")


def main():
    if "auth" not in st.session_state:
        login_view(); return
    role, code = st.session_state.auth
    # V4: resolve the current user once for write attribution + scope.
    user = identity.resolve(role, code)
    st.session_state["user"] = user

    mobile = is_mobile()
    if mobile:
        st.markdown("<style>.stButton>button{padding:.4rem .35rem;font-size:.82rem;min-height:0}"
                    "div[data-testid='stHorizontalBlock']{gap:.4rem}</style>", unsafe_allow_html=True)
    # V4: admin/DM run the full-width website component with ONE navy left nav (the native
    # sidebar, styled). Trim page gutters; style the sidebar to match the product. Store: as-is.
    elif role in ("admin", "district"):
        st.markdown("""<style>
         .block-container{padding:.4rem .8rem 0!important;max-width:100%!important}
         [data-testid="stSidebar"]{background:#14273F!important;width:212px!important;min-width:212px!important}
         [data-testid="stSidebar"] *{color:#fff}
         /* Nav is permanent: hide the collapse arrow so the sidebar can't be hidden with no
            way back (the reopen control lives in the hidden top header). */
         [data-testid="stSidebarCollapseButton"],[data-testid="stSidebarCollapsedControl"],
         [data-testid="collapsedControl"]{display:none!important}
         .navbrand{font-weight:800;font-size:1.06rem;padding:8px 6px 16px;line-height:1.2}
         .navbrand span{display:block;color:#9FB4CC;font-weight:500;font-size:.7rem;margin-top:3px}
         [data-testid="stSidebar"] [role="radiogroup"]{gap:2px}
         [data-testid="stSidebar"] [role="radiogroup"] label{padding:9px 12px;border-radius:8px;margin:1px 0;
           cursor:pointer;font-weight:600;font-size:.9rem;color:#C6D3E4}
         [data-testid="stSidebar"] [role="radiogroup"] label:hover{background:rgba(255,255,255,.08);color:#fff}
         [data-testid="stSidebar"] [role="radiogroup"] label[data-checked="true"],
         [data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked){background:#fff;color:#14273F}
         [data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) *{color:#14273F}
         [data-testid="stSidebar"] [role="radiogroup"] div[data-testid="stMarkdownContainer"]{color:inherit}
        </style>""", unsafe_allow_html=True)

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
            if st.button("Desktop View", use_container_width=True):
                st.query_params["view"] = "desktop"; st.rerun()
        else:
            if st.button("Phone View", use_container_width=True):
                st.query_params["view"] = "phone"; st.rerun()
    with cg:
        if st.button("User Guide", use_container_width=True):
            _open_guide()
    with clo:
        if st.button("Log out", use_container_width=True):
            del st.session_state.auth; st.cache_data.clear(); st.rerun()

    # V4 (A): entry-point deep links, no on-page selector. The tier comes from the login;
    # ?scope= lets an admin/DM open a specific store or region directly by URL (each level
    # has its own shareable URL). Clicking around inside the page uses the dashboard's own
    # in-component nav (kept from V3); default (no param) = the tier's normal view.
    try:
        scope_str = st.query_params.get("scope", "") or ""
    except Exception:
        scope_str = ""
    tier, allowed, scope = identity.resolve_scope(role, user, scope_str)

    # fallback guide (only when st.dialog isn't available)
    if not _dialog and st.session_state.get("_guide_open"):
        with st.expander("Store guide", expanded=True):
            _guide_body()
            if st.button("Close guide"):
                st.session_state["_guide_open"] = False; st.rerun()

    # V4 (B-3d): ONE navy left nav (native sidebar) — Overview / Store detail / Historical,
    # plus Targets (admin only) BELOW Historical. Drives which section the website component
    # starts on. Targets renders the native view+editor (saves go through the server).
    startview = "overview"
    if role in ("admin", "district") and tier in ("admin", "district"):
        items = ["Overview", "Store detail", "Historical"] + (["Daily task", "Targets", "Messages"] if role == "admin" else [])
        with st.sidebar:
            st.markdown("<div class='navbrand'>VantEdge Auto<span>Take 5 · Scorecard</span></div>",
                        unsafe_allow_html=True)
            section = st.radio("Navigation", items, label_visibility="collapsed", key="nav_section")
        if section == "Targets":
            _targets_view(user)
            return
        if section == "Messages":
            _messages_admin(user)
            return
        if section == "Daily task":
            _daily_task_admin(user)
            return
        startview = {"Overview": "overview", "Store detail": "detail", "Historical": "hist"}[section]

    # V4 (C): store login gets the daily-task checklist in the LEFT column (native, so it can
    # save), with the dashboard component on the right. Other tiers render full-width.
    if role == "store" and not mobile:
        left, right = st.columns([1.25, 5], gap="small")
        with left:
            _task_checklist(user)
        with right:
            _dashboard_view(tier, allowed, scope, mobile, startview)
    else:
        if role == "store":
            _task_checklist(user)
        _dashboard_view(tier, allowed, scope, mobile, startview)


if __name__ == "__main__":
    main()
