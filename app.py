"""
VantEdge Auto — Take 5 Daily Store Scorecard (redesign).

Reads live hourly data from Supabase and benchmarks each store against its
normal DAILY performance (baseline.json) and its own accumulating by-hour
pacing curve (built from prior same-weekday hourly snapshots in Supabase).

Login: a store code (e.g. 1512) sees that store; the admin password sees all.
Secrets (Streamlit -> Settings -> Secrets): SUPABASE_URL, SUPABASE_KEY, ADMIN_PASSWORD
"""
import json
import datetime as dt
from zoneinfo import ZoneInfo

import requests
import streamlit as st
import plotly.graph_objects as go

# --------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------
CENTRAL = ZoneInfo("America/Chicago")
BRAND = "VantEdge Auto"
STORE_CODES = ["1507", "1512", "1515"]
CITY = {"1507": "Cedar Rapids", "1512": "Jefferson City", "1515": "Columbia"}
# Store open hours in Central, keyed by Python weekday (Mon=0 .. Sun=6): (open, close)
HOURS = {0: (7, 20), 1: (7, 20), 2: (7, 20), 3: (7, 20), 4: (7, 20), 5: (7, 18), 6: (9, 17)}
DOW = {0: "Mon", 1: "Tues", 2: "Wed", 3: "Thurs", 4: "Fri", 5: "Sat", 6: "Sun"}
STALE_HOURS = 2  # flag data older than this during open hours

# Take 5 palette
NAVY = "#14273F"   # structure / headers
BLUE = "#2E6FB7"   # accent
RED = "#E4002B"    # Take 5 red — alerts / behind
GREEN = "#1E8E4E"  # ahead
AMBER = "#E6A200"  # caution
INK = "#1F2A37"
MUTE = "#5B6B7F"
LINE = "#E3E8EF"
LIGHT = "#F4F7FB"

# Metrics available in the hero pace chart / heat map
METRICS = {
    "Cars": {"key": "cars", "base": "cars", "money": False},
    "Net sales": {"key": "net_sales", "base": "net_sales", "money": True},
    "Big 4 units": {"key": "big4_total_units", "base": None, "money": False},
}

st.set_page_config(page_title=f"{BRAND} — Store Scorecard", layout="wide")
st.markdown(
    "<style>"
    ".block-container{padding-top:1.2rem;max-width:1240px;}"
    "#MainMenu,footer{visibility:hidden;}"
    "html,body,[class*='css']{color:#1F2A37;}"
    "@media print{section[data-testid='stSidebar']{display:none;} .stButton{display:none;}}"
    "</style>",
    unsafe_allow_html=True,
)


# --------------------------------------------------------------------------
# Small helpers (pure — unit tested)
# --------------------------------------------------------------------------
def store_display(store, latest=None):
    """Friendly store name for display — never the bare store number."""
    return CITY.get(store) or (latest or {}).get("store_name") or "Your store"


def fmt(value, money=False, dp=0):
    if value is None:
        return "—"
    return ("$" if money else "") + format(value, f",.{dp}f")


def hour_label(h):
    ap = "a" if h < 12 else "p"
    h12 = h % 12 or 12
    return f"{h12}{ap}"


def frac_elapsed(now):
    o, c = HOURS[now.weekday()]
    return max(0.0, min(1.0, ((now.hour + now.minute / 60) - o) / (c - o)))


def status_color(actual, expected):
    """Green ahead, amber within 10% behind, red further behind. INK if no goal."""
    if expected is None or expected == 0:
        return INK
    ratio = actual / expected
    if ratio >= 1.0:
        return GREEN
    if ratio >= 0.90:
        return AMBER
    return RED


def row_date(row):
    p = (row.get("pull_hour") or "")
    parts = p.split("-")
    return "-".join(parts[:3]) if len(parts) >= 3 else None


def row_hour(row):
    p = (row.get("pull_hour") or "")
    parts = p.split("-")
    try:
        return int(parts[3]) if len(parts) >= 4 else None
    except ValueError:
        return None


def cum_by_hour(rows, key):
    """From a set of rows for ONE day, return {hour: cumulative value} (last row wins)."""
    out = {}
    for r in sorted(rows, key=lambda x: x.get("pull_time") or ""):
        h = row_hour(r)
        if h is None:
            continue
        v = r.get(key)
        if v is not None:
            out[h] = v
    return out


def normal_curve(history_rows, weekday, key):
    """Average cumulative-by-hour curve across prior dates matching `weekday`.
    Returns {hour: avg_cumulative} or {} if not enough history."""
    by_date = {}
    for r in history_rows:
        d = row_date(r)
        if not d:
            continue
        by_date.setdefault(d, []).append(r)
    same = []
    for d, rows in by_date.items():
        try:
            wd = dt.date.fromisoformat(d).weekday()
        except ValueError:
            continue
        if wd == weekday:
            same.append(cum_by_hour(rows, key))
    if len(same) < 1:
        return {}
    hours = sorted({h for c in same for h in c})
    curve = {}
    for h in hours:
        vals = [c[h] for c in same if h in c]
        if vals:
            curve[h] = sum(vals) / len(vals)
    return curve


def forecast_full_day(today_last, now_hour, curve, base_full, tfrac):
    """Nowcast: blend pace-implied full day with the baseline, weighting pace
    more as the day progresses. Returns (full_est, method)."""
    frac = None
    if curve:
        close = max(curve)
        nc_close = curve.get(close)
        near = max((h for h in curve if h <= now_hour), default=None)
        if nc_close and near is not None:
            frac = curve[near] / nc_close if nc_close else None
    pace_full = today_last / frac if (frac and frac > 0.05) else None
    if base_full and pace_full:
        w = min(1.0, max(0.35, tfrac))
        return w * pace_full + (1 - w) * base_full, "blend"
    if pace_full:
        return pace_full, "pace"
    if base_full:
        return base_full, "baseline"
    return today_last, "actual"


def rank_stores(store_stats):
    """store_stats: list of dicts with 'store','pct'. Sorted desc by pct (None last)."""
    return sorted(store_stats, key=lambda s: (s["pct"] is None, -(s["pct"] or 0)))


# --------------------------------------------------------------------------
# Supabase
# --------------------------------------------------------------------------
@st.cache_data(ttl=600)
def sb_get(path):
    url = st.secrets["SUPABASE_URL"].rstrip("/")
    key = st.secrets["SUPABASE_KEY"]
    r = requests.get(url + "/rest/v1/" + path,
                     headers={"apikey": key, "Authorization": "Bearer " + key}, timeout=25)
    r.raise_for_status()
    return r.json()


def fetch_today(store):
    today = dt.datetime.now(CENTRAL).strftime("%Y-%m-%d")
    return sb_get(f"daily_sales_pull?store_number=eq.{store}"
                  f"&pull_hour=like.{today}*&order=pull_time.asc")


def fetch_history(store, days=42):
    since = (dt.datetime.now(CENTRAL) - dt.timedelta(days=days)).strftime("%Y-%m-%d")
    cols = "pull_hour,pull_time,cars,net_sales,big4_total_units,report_timestamp"
    return sb_get(f"daily_sales_pull?store_number=eq.{store}"
                  f"&pull_time=gte.{since}&select={cols}&order=pull_time.asc")


@st.cache_data
def load_baseline():
    with open("baseline.json") as f:
        return json.load(f)


# --------------------------------------------------------------------------
# UI atoms
# --------------------------------------------------------------------------
def wordmark(sub):
    st.markdown(
        f'<div style="background:{NAVY};border-radius:10px;padding:14px 22px;margin-bottom:10px;'
        f'display:flex;justify-content:space-between;align-items:center;">'
        f'<div style="display:flex;align-items:center;gap:12px;">'
        f'<div style="width:8px;height:30px;background:{RED};border-radius:2px;"></div>'
        f'<div style="color:#fff;font-size:1.3rem;font-weight:800;letter-spacing:.04em;">{BRAND}'
        f'<span style="color:#9FB4CC;font-weight:500;font-size:.8rem;"> · Take 5 Scorecard</span></div>'
        f'</div>'
        f'<div style="color:#DCE5F0;text-align:right;font-size:.86rem;">{sub}</div></div>',
        unsafe_allow_html=True,
    )


def freshness(latest, now):
    ts = latest.get("report_timestamp") or "—"
    age_note, color = "", GREEN
    rt = latest.get("pull_time")
    try:
        pt = dt.datetime.fromisoformat(rt).astimezone(CENTRAL)
        hrs = (now - pt).total_seconds() / 3600
        if hrs > STALE_HOURS:
            color, age_note = AMBER, f" · ⚠ last pull {hrs:.1f}h ago"
    except (TypeError, ValueError):
        pass
    st.markdown(
        f'<div style="font-size:.82rem;color:{MUTE};margin:-4px 0 10px 2px;">'
        f'<span style="color:{color};">●</span> Data as of {ts}{age_note}</div>',
        unsafe_allow_html=True,
    )


def kpi_card(label, value, goal, delta, pct, color, tip):
    bar = min(150, max(0, pct)) if pct is not None else 0
    goal_line = ("<div style='position:absolute;left:66.6%;top:0;bottom:0;width:2px;"
                 f"background:{INK};opacity:.55;'></div>") if pct is not None else ""
    delta_html = (f"<span style='color:{color};font-weight:700;'>{delta}</span>"
                  if delta else "<span style='color:#9AA7B5;'>&nbsp;</span>")
    return (
        f'<div title="{tip}" style="flex:1;min-width:150px;background:#fff;border:1px solid {LINE};'
        f'border-top:3px solid {color};border-radius:9px;padding:12px 14px;">'
        f'<div style="font-size:.68rem;letter-spacing:.06em;color:{MUTE};text-transform:uppercase;">{label}</div>'
        f'<div style="font-size:1.7rem;font-weight:800;color:{INK};line-height:1.15;">{value}</div>'
        f'<div style="font-size:.74rem;color:{MUTE};margin-bottom:7px;">{goal} &nbsp; {delta_html}</div>'
        f'<div style="position:relative;height:7px;background:{LIGHT};border-radius:4px;overflow:hidden;">'
        f'<div style="width:{bar/1.5:.0f}%;height:100%;background:{color};"></div>{goal_line}</div></div>'
    )


def section_title(text):
    st.markdown(
        f'<div style="border-left:4px solid {RED};padding-left:10px;margin:18px 0 8px;'
        f'font-size:1.02rem;font-weight:800;color:{NAVY};">{text}</div>',
        unsafe_allow_html=True,
    )


# --------------------------------------------------------------------------
# Charts
# --------------------------------------------------------------------------
def base_layout(fig, height, title=None):
    fig.update_layout(
        height=height, margin=dict(l=10, r=10, t=40 if title else 12, b=10),
        paper_bgcolor="white", plot_bgcolor="white", font_color=INK,
        title={"text": title, "font": {"color": NAVY, "size": 15}} if title else None,
        legend=dict(orientation="h", y=1.12, x=0, font=dict(size=11)),
    )
    fig.update_xaxes(gridcolor=LINE)
    fig.update_yaxes(gridcolor=LINE)
    return fig


def pace_chart(hours, normal, today, fc, band, money, label):
    """hours: list of ints. normal/today: {hour:cum}. fc: {hour:cum} forecast incl now.
    band: (lower{hour:cum}, upper{hour:cum}) or None."""
    x = [hour_label(h) for h in hours]
    pref = "$" if money else ""
    fig = go.Figure()
    if normal:
        fig.add_trace(go.Scatter(
            x=x, y=[normal.get(h) for h in hours], name="Normal (this weekday)",
            mode="lines", line=dict(color="#AFC6DE", width=3),
            hovertemplate="%{x}<br>Normal: " + pref + "%{y:,.0f}<extra></extra>"))
    if band:
        lo, hi = band
        fig.add_trace(go.Scatter(x=x, y=[hi.get(h) for h in hours], mode="lines",
                                 line=dict(width=0), showlegend=False, hoverinfo="skip"))
        fig.add_trace(go.Scatter(x=x, y=[lo.get(h) for h in hours], mode="lines",
                                 line=dict(width=0), fill="tonexty",
                                 fillcolor="rgba(228,0,43,0.10)", name="Forecast range",
                                 hoverinfo="skip"))
    if fc:
        fig.add_trace(go.Scatter(
            x=x, y=[fc.get(h) for h in hours], name="Forecast (rest of day)",
            mode="lines", line=dict(color=RED, width=2, dash="dash"),
            hovertemplate="%{x}<br>Forecast: " + pref + "%{y:,.0f}<extra></extra>"))
    if today:
        fig.add_trace(go.Scatter(
            x=x, y=[today.get(h) for h in hours], name="Today (actual)",
            mode="lines+markers", line=dict(color=NAVY, width=3.5),
            marker=dict(size=6, color=NAVY),
            hovertemplate="%{x}<br>Today: " + pref + "%{y:,.0f}<extra></extra>"))
    fig.update_yaxes(title=("$ cumulative" if money else "cumulative"))
    return base_layout(fig, 360, f"Pace today vs normal — {label}")


def big4_chart(big4):
    names = list(big4.keys())
    attach = [big4[n].get("attach_pct") or 0 for n in names]
    fig = go.Figure(go.Bar(x=names, y=attach, marker_color=NAVY,
                           text=[f"{a:.0f}%" for a in attach], textposition="outside"))
    fig.update_yaxes(title="% of cars")
    return base_layout(fig, 300, "Big 4 attachment (% of cars)")


def revenue_chart(items):
    items = sorted(items, key=lambda x: x.get("amount") or 0, reverse=True)
    names = [i.get("description", "?") for i in items]
    amts = [i.get("amount") or 0 for i in items]
    fig = go.Figure(go.Bar(x=amts, y=names, orientation="h", marker_color=BLUE,
                           text=[f"${a:,.0f}" for a in amts], textposition="outside"))
    fig.update_layout(yaxis=dict(autorange="reversed"))
    fig.update_xaxes(title="$ today")
    return base_layout(fig, max(280, 24 * len(items)), "Revenue by product line (today)")


def bell(values, marker, marker_label, title):
    mean = sum(values) / len(values)
    fig = go.Figure(go.Histogram(x=values, nbinsx=18, marker_color="#BCD3EA", opacity=0.9))
    fig.add_vline(x=mean, line_color=NAVY, line_width=2,
                  annotation_text="Normal avg " + format(mean, ",.0f"), annotation_position="top")
    if marker is not None:
        fig.add_vline(x=marker, line_color=RED, line_dash="dash", line_width=3,
                      annotation_text=marker_label, annotation_position="top left")
    fig.update_yaxes(title="How often (weeks/yr)")
    fig.update_layout(bargap=0.05)
    return base_layout(fig, 280, title)


# --------------------------------------------------------------------------
# Store view
# --------------------------------------------------------------------------
def render_store(store, baseline):
    now = dt.datetime.now(CENTRAL)
    day = DOW[now.weekday()]
    o, c = HOURS[now.weekday()]
    hours = list(range(o, c + 1))
    rows = fetch_today(store)
    b = baseline.get(store, {})
    cars_base = b.get("cars", {}).get(day)
    sales_base = b.get("net_sales", {}).get(day)

    if not rows:
        wordmark(f"{store_display(store)} &middot; {now:%A, %b %d}")
        st.info("No data pulled yet today. This fills in on the first hourly run after opening.")
        return

    latest = rows[-1]
    cars = latest.get("cars") or 0
    net = latest.get("net_sales") or 0
    aro = round(net / cars, 2) if cars else 0
    frac = frac_elapsed(now)
    payload = latest.get("data") or {}
    lab = payload.get("labor") or latest.get("labor") or {}

    cars_full = cars_base["mean"] if cars_base else None
    sales_full = sales_base["mean"] if sales_base else None
    aro_norm = round(sales_full / cars_full, 2) if (cars_full and sales_full) else None
    cars_now = cars_full * frac if cars_full else None
    sales_now = sales_full * frac if sales_full else None

    wordmark(f"{store_display(store, latest)} &middot; {now:%A, %b %d} &middot; {frac*100:.0f}% through the day")
    freshness(latest, now)

    # ---- staffing callout (loudest element) ----
    hist = fetch_history(store)
    cars_curve = normal_curve(hist, now.weekday(), "cars")
    full_est, method = forecast_full_day(cars, now.hour, cars_curve, cars_full, frac)
    if cars_now is not None:
        diff = cars - cars_now
        if diff >= 1:
            verdict, vcolor = "Ahead of pace — keep full staffing on.", GREEN
        elif diff <= -1:
            verdict, vcolor = "Behind pace — you may be over-staffed for this pace.", RED
        else:
            verdict, vcolor = "Right on the normal pace.", NAVY
        proj = f" Projected to finish ~<b>{full_est:,.0f} cars</b>." if full_est else ""
        st.markdown(
            f'<div style="border-left:6px solid {vcolor};background:{LIGHT};padding:12px 18px;'
            f'border-radius:6px;margin-bottom:14px;font-size:1.02rem;">'
            f'<b>Bottom line —</b> {cars} cars / ${net:,.0f} so far. A normal {day} runs '
            f'~{cars_full:,.0f} cars / ${sales_full:,.0f}.{proj} '
            f'<b style="color:{vcolor};">{verdict}</b></div>',
            unsafe_allow_html=True)

    # ---- KPI bullet cards ----
    aro_pct = (aro / aro_norm * 100) if aro_norm else None
    cards = [
        kpi_card("Cars", f"{cars:,.0f}",
                 f"exp ~{cars_now:,.0f}" if cars_now else "no goal",
                 (f"{cars-cars_now:+,.0f}" if cars_now else ""),
                 (cars / cars_now * 100) if cars_now else None,
                 status_color(cars, cars_now), "Cars so far vs expected-by-now (baseline pace)."),
        kpi_card("Net revenue", f"${net:,.0f}",
                 f"exp ~${sales_now:,.0f}" if sales_now else "no goal",
                 (f"{net-sales_now:+,.0f}" if sales_now else ""),
                 (net / sales_now * 100) if sales_now else None,
                 status_color(net, sales_now), "Net sales so far vs expected-by-now (baseline pace)."),
        kpi_card("ARO", f"${aro:,.2f}",
                 f"normal ${aro_norm:,.2f}" if aro_norm else "no goal",
                 (f"{aro-aro_norm:+,.2f}" if aro_norm else ""),
                 aro_pct, status_color(aro, aro_norm),
                 "Average revenue per car vs this store's normal ARO."),
        kpi_card("Big 4 units", f"{latest.get('big4_total_units',0):,.0f}",
                 f"${latest.get('big4_total_amount') or 0:,.0f} sales", "", None, BLUE,
                 "Big 4 attachment units today (Air Filter, Wiper, Cabin, Coolant). No goal set."),
        kpi_card("Labor hrs/car", f"{lab.get('hours_per_car') or 0:,.2f}",
                 f"{lab.get('pct_of_net') or 0:.0f}% of net", "", None, BLUE,
                 "Labor hours per car — efficiency proxy. Lower = leaner. No goal set."),
    ]
    st.markdown(f'<div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:6px;">{"".join(cards)}</div>',
                unsafe_allow_html=True)

    # ---- hero pace chart ----
    section_title("Pace vs normal & forecast")
    metric = st.radio("Metric", list(METRICS.keys()), horizontal=True, key=f"m_{store}")
    mk = METRICS[metric]["key"]
    money = METRICS[metric]["money"]
    base_full = cars_full if mk == "cars" else (sales_full if mk == "net_sales" else None)
    curve = normal_curve(hist, now.weekday(), mk)
    today_cum = cum_by_hour(rows, mk)
    now_h = max((h for h in today_cum), default=o)
    last_val = today_cum.get(now_h, 0)
    fest, _ = forecast_full_day(last_val, now.hour, curve, base_full, frac)
    fc, lo, hi = build_forecast(hours, now_h, last_val, curve, fest, frac)
    st.plotly_chart(pace_chart(hours, curve, today_cum, fc, (lo, hi) if fc else None, money, metric),
                    use_container_width=True)
    if not curve:
        st.caption("Normal curve is still building — it fills in as more same-weekday hourly data accumulates. "
                   "Forecast currently uses the daily baseline.")

    # ---- product / attachment ----
    section_title("Products & attachment")
    col1, col2 = st.columns(2)
    big4 = latest.get("big4") or {}
    if big4:
        col1.plotly_chart(big4_chart(big4), use_container_width=True)
    items = latest.get("line_items") or []
    if items:
        col2.plotly_chart(revenue_chart(items), use_container_width=True)

    # ---- labor & customers ----
    section_title("Labor, customers & discounts")
    fleets_count = payload.get("fleets_count", latest.get("fleets_count")) or 0
    fleets_amount = payload.get("fleets_amount", latest.get("fleets_amount")) or 0
    nc_, rc_ = latest.get("new_customers") or 0, latest.get("repeat_customers") or 0
    mini = [
        ("Labor hours", f"{lab.get('hours') or 0:,.1f}"),
        ("Labor % of net", f"{lab.get('pct_of_net') or 0:.1f}%"),
        ("Fleet", f"{fleets_count} / ${fleets_amount:,.0f}"),
        ("New / Repeat", f"{nc_} / {rc_}"),
        ("Coupons", f"${latest.get('coupons') or 0:,.0f}"),
        ("Discounts", f"${latest.get('discounts') or 0:,.0f}"),
    ]
    cells = "".join(
        f'<div style="flex:1;min-width:130px;padding:8px 12px;border:1px solid {LINE};border-radius:8px;">'
        f'<div style="font-size:.66rem;text-transform:uppercase;letter-spacing:.05em;color:{MUTE};">{k}</div>'
        f'<div style="font-size:1.15rem;font-weight:700;color:{INK};">{v}</div></div>' for k, v in mini)
    st.markdown(f'<div style="display:flex;gap:8px;flex-wrap:wrap;">{cells}</div>', unsafe_allow_html=True)

    # ---- distribution (demoted) ----
    with st.expander("How today compares to a normal full day (distribution)"):
        g1, g2 = st.columns(2)
        if cars_base:
            g1.plotly_chart(bell(cars_base["values"], cars, f"today: {cars}", "Normal daily cars"),
                            use_container_width=True)
        if sales_base:
            g2.plotly_chart(bell(sales_base["values"], net, f"today: ${net:,.0f}", "Normal daily net sales"),
                            use_container_width=True)


def build_forecast(hours, now_h, last_val, curve, full_est, tfrac):
    """Return (fc, lo, hi) cumulative dicts from now_h..close, or (None,None,None)."""
    if full_est is None:
        return None, None, None
    close = hours[-1]
    rest = [h for h in hours if h >= now_h]
    if len(rest) < 2:
        return None, None, None
    # distribute (full_est - last_val) across remaining hours by normal shape, else linear
    if curve and curve.get(close) and curve.get(now_h) is not None:
        base_h = curve.get(now_h, 0)
        span = curve[close] - base_h
        shares = {}
        for h in rest:
            shares[h] = ((curve.get(h, base_h) - base_h) / span) if span > 0 else \
                ((h - now_h) / (close - now_h) if close > now_h else 1)
    else:
        shares = {h: (h - now_h) / (close - now_h) if close > now_h else 1 for h in rest}
    remain = full_est - last_val
    fc = {h: last_val + remain * shares[h] for h in rest}
    err = 0.05 + 0.15 * (1 - tfrac)
    lo = {h: last_val + (fc[h] - last_val) * (1 - err) for h in rest}
    hi = {h: last_val + (fc[h] - last_val) * (1 + err) for h in rest}
    return fc, lo, hi


# --------------------------------------------------------------------------
# Admin view
# --------------------------------------------------------------------------
def admin_snapshot(baseline):
    """Return per-store today stats + raw rows, for ranking / heat map."""
    now = dt.datetime.now(CENTRAL)
    day = DOW[now.weekday()]
    frac = frac_elapsed(now)
    stats, today_rows = [], {}
    for s in STORE_CODES:
        rows = fetch_today(s)
        today_rows[s] = rows
        if not rows:
            stats.append({"store": s, "name": store_display(s), "cars": None, "net": None,
                          "aro": None, "pct": None})
            continue
        latest = rows[-1]
        cars = latest.get("cars") or 0
        net = latest.get("net_sales") or 0
        cb = baseline.get(s, {}).get("cars", {}).get(day)
        exp = cb["mean"] * frac if cb else None
        stats.append({"store": s, "name": store_display(s, latest), "cars": cars, "net": net,
                      "aro": round(net / cars, 2) if cars else 0,
                      "pct": (cars / exp * 100) if exp else None})
    return stats, today_rows


def render_admin(baseline):
    now = dt.datetime.now(CENTRAL)
    wordmark(f"All Stores &middot; {now:%A, %b %d} &middot; {frac_elapsed(now)*100:.0f}% through the day")
    stats, today_rows = admin_snapshot(baseline)

    live = [s for s in stats if s["cars"] is not None]
    tot_cars = sum(s["cars"] for s in live)
    tot_net = sum(s["net"] for s in live)
    ahead = sum(1 for s in live if (s["pct"] or 0) >= 100)
    strip = [
        ("Stores reporting", f"{len(live)}/{len(stats)}"),
        ("Total cars", f"{tot_cars:,.0f}"),
        ("Total net", f"${tot_net:,.0f}"),
        ("Ahead of pace", f"{ahead}/{len(live)}" if live else "—"),
    ]
    cells = "".join(
        f'<div style="flex:1;min-width:140px;background:#fff;border:1px solid {LINE};border-top:3px solid {NAVY};'
        f'border-radius:9px;padding:12px 14px;"><div style="font-size:.68rem;text-transform:uppercase;'
        f'letter-spacing:.05em;color:{MUTE};">{k}</div><div style="font-size:1.6rem;font-weight:800;'
        f'color:{INK};">{v}</div></div>' for k, v in strip)
    st.markdown(f'<div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:6px;">{cells}</div>',
                unsafe_allow_html=True)

    # ---- ranking ----
    section_title("Store ranking — cars vs normal pace")
    ranked = rank_stores(stats)
    trows = ""
    for i, s in enumerate(ranked, 1):
        pct = s["pct"]
        col = status_color(pct or 0, 100) if pct is not None else MUTE
        pcttxt = f"{pct:.0f}%" if pct is not None else "no data"
        trows += (
            f'<tr style="border-bottom:1px solid {LINE};">'
            f'<td style="padding:7px 10px;color:{MUTE};">{i}</td>'
            f'<td style="padding:7px 10px;font-weight:700;color:{INK};">{s["name"]}</td>'
            f'<td style="padding:7px 10px;text-align:right;">{fmt(s["cars"])}</td>'
            f'<td style="padding:7px 10px;text-align:right;">{fmt(s["net"],money=True)}</td>'
            f'<td style="padding:7px 10px;text-align:right;">{fmt(s["aro"],money=True,dp=2)}</td>'
            f'<td style="padding:7px 10px;text-align:right;font-weight:800;color:{col};">{pcttxt}</td></tr>')
    st.markdown(
        f'<table style="width:100%;border-collapse:collapse;background:#fff;border:1px solid {LINE};border-radius:8px;">'
        f'<tr style="background:{NAVY};color:#fff;font-size:.72rem;text-transform:uppercase;letter-spacing:.04em;">'
        f'<th style="padding:8px 10px;text-align:left;">#</th><th style="padding:8px 10px;text-align:left;">Store</th>'
        f'<th style="padding:8px 10px;text-align:right;">Cars</th><th style="padding:8px 10px;text-align:right;">Net</th>'
        f'<th style="padding:8px 10px;text-align:right;">ARO</th>'
        f'<th style="padding:8px 10px;text-align:right;">% pace</th></tr>{trows}</table>',
        unsafe_allow_html=True)

    # ---- heat map: hours x stores ----
    section_title("Heat map — hour × store (per-hour volume)")
    hm_metric = st.radio("Cell metric", list(METRICS.keys()), horizontal=True, key="hm")
    mk = METRICS[hm_metric]["key"]
    heatmap(today_rows, mk, hm_metric)

    # ---- comparison overlay ----
    section_title("Compare stores — cumulative pace")
    picks = st.multiselect("Stores", STORE_CODES, default=STORE_CODES[:2],
                           format_func=lambda s: CITY.get(s, s))
    cmp_metric = st.radio("Metric", list(METRICS.keys()), horizontal=True, key="cmp")
    comparison(picks, today_rows, METRICS[cmp_metric]["key"], METRICS[cmp_metric]["money"], cmp_metric)

    # ---- export ----
    section_title("Export")
    export_controls(stats)


def heatmap(today_rows, key, label):
    now = dt.datetime.now(CENTRAL)
    o, c = HOURS[now.weekday()]
    hrs = list(range(o, c + 1))
    stores = [s for s in STORE_CODES if today_rows.get(s)]
    if not stores:
        st.info("No store data yet today for the heat map.")
        return
    z, text = [], []
    for h in hrs:
        zrow, trow = [], []
        for s in stores:
            cum = cum_by_hour(today_rows[s], key)
            hs = sorted(cum)
            prev = [x for x in hs if x < h]
            incr = (cum[h] - (cum[prev[-1]] if prev else 0)) if h in cum else None
            zrow.append(incr)
            trow.append("—" if incr is None else (f"${incr:,.0f}" if key == "net_sales" else f"{incr:,.0f}"))
        z.append(zrow)
        text.append(trow)
    # normalize per store (column) so each store shows its own peak pattern
    zt = list(zip(*z)) if z else []
    znorm = [[None] * len(stores) for _ in hrs]
    for ci, colvals in enumerate(zt):
        nums = [v for v in colvals if v is not None]
        mx = max(nums) if nums else 0
        for ri, v in enumerate(colvals):
            znorm[ri][ci] = (v / mx) if (v is not None and mx) else (0 if v == 0 else None)
    fig = go.Figure(go.Heatmap(
        z=znorm, x=[CITY.get(s, s) for s in stores], y=[hour_label(h) for h in hrs],
        text=text, texttemplate="%{text}", textfont={"size": 11},
        colorscale=[[0, "#F4F7FB"], [0.5, "#7FA8D4"], [1, NAVY]], showscale=True,
        hovertemplate="%{x} · %{y}<br>" + label + ": %{text}<extra></extra>"))
    fig.update_yaxes(autorange="reversed")
    st.plotly_chart(base_layout(fig, max(300, 26 * len(hrs)),
                                f"{label} per hour (shaded vs each store's own peak)"),
                    use_container_width=True)


def comparison(picks, today_rows, key, money, label):
    now = dt.datetime.now(CENTRAL)
    o, c = HOURS[now.weekday()]
    hrs = list(range(o, c + 1))
    if not picks:
        st.info("Pick one or more stores to compare.")
        return
    fig = go.Figure()
    palette = [NAVY, RED, BLUE, GREEN, AMBER]
    for i, s in enumerate(picks):
        cum = cum_by_hour(today_rows.get(s, []), key)
        if not cum:
            continue
        fig.add_trace(go.Scatter(x=[hour_label(h) for h in hrs], y=[cum.get(h) for h in hrs],
                                 name=CITY.get(s, s), mode="lines+markers",
                                 line=dict(width=3, color=palette[i % len(palette)])))
    fig.update_yaxes(title=("$ cumulative" if money else "cumulative"))
    st.plotly_chart(base_layout(fig, 360, f"{label} — cumulative by hour"), use_container_width=True)


def export_controls(stats):
    import io, csv
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Store", "Cars", "Net", "ARO", "% pace"])
    for s in stats:
        w.writerow([s["name"], s["cars"], s["net"], s["aro"],
                    f"{s['pct']:.0f}" if s["pct"] is not None else ""])
    today = dt.datetime.now(CENTRAL).strftime("%Y-%m-%d")
    c1, c2 = st.columns(2)
    c1.download_button("⬇ Download today (CSV)", buf.getvalue(),
                       file_name=f"take5_scorecard_{today}.csv", mime="text/csv")
    c2.markdown(
        '<button onclick="window.print()" style="width:100%;padding:9px;border:0;border-radius:7px;'
        f'background:{NAVY};color:#fff;font-weight:700;cursor:pointer;">🖨 Print / Save one-page scorecard</button>',
        unsafe_allow_html=True)


# --------------------------------------------------------------------------
# Auth + main
# --------------------------------------------------------------------------
def login_view():
    wordmark("Daily Store Scorecard")
    st.write("Enter your access code.")
    pw = st.text_input("Access code", type="password", label_visibility="collapsed")
    if st.button("Enter", type="primary"):
        admin = st.secrets.get("ADMIN_PASSWORD", "")
        if pw in STORE_CODES:
            st.session_state.auth = ("store", pw)
            st.rerun()
        elif admin and pw == admin:
            st.session_state.auth = ("admin", None)
            st.rerun()
        else:
            st.error("Access code not recognized.")


def main():
    baseline = load_baseline()
    if "auth" not in st.session_state:
        login_view()
        return
    role, store = st.session_state.auth
    with st.sidebar:
        st.markdown(f"**{BRAND}**")
        if st.button("Log out"):
            del st.session_state.auth
            st.rerun()
        if st.button("Refresh data"):
            st.cache_data.clear()
            st.rerun()
    if role == "store":
        render_store(store, baseline)
    else:
        with st.sidebar:
            view = st.radio("View", ["Executive (all stores)", "Single store"])
            if view == "Single store":
                sel = st.selectbox("Store", STORE_CODES, format_func=lambda s: CITY.get(s, s))
        if view == "Single store":
            render_store(sel, baseline)
        else:
            render_admin(baseline)


if __name__ == "__main__":
    main()
