"""
VantEdge Auto - Take 5 Store Scorecard.

Single-file Streamlit front end (redesign v2). Reads live hourly data from
Supabase and scores each store against:
  * baseline.json  - the store's NORMAL daily total for this weekday, and
  * its own accumulating BY-HOUR history in Supabase (holiday-clean), used for
    the per-hour "normal" curve and the intraday re-forecast.

Every operational chart shows PER-PERIOD (per-hour) values, never cumulative
totals, so each hour compares apples-to-apples against the historical average
for that same hour of the same day-of-week.

Login: a store code (e.g. 1512) sees that store; the admin password sees all.
Secrets (Streamlit -> Settings -> Secrets): SUPABASE_URL, SUPABASE_KEY, ADMIN_PASSWORD.

This is a FRONT-END ONLY build. It does not touch the scraper / pipeline.
Allowed libs: streamlit, plotly, requests (+ Python stdlib).
"""
import io
import csv
import json
import statistics
import datetime as dt
from zoneinfo import ZoneInfo

import requests
import streamlit as st
import plotly.graph_objects as go

# ==========================================================================
# Config
# ==========================================================================
CENTRAL = ZoneInfo("America/Chicago")
BRAND = "VantEdge Auto"
SUBBRAND = "Take 5 Scorecard"

# Pilot stores live today; the design supports up to 15. Add a code + city here
# and a block in baseline.json to light up another store.
STORE_CODES = ["1507", "1512", "1515"]
CITY = {"1507": "Cedar Rapids", "1512": "Jefferson City", "1515": "Columbia"}

# Store open hours in Central, keyed by Python weekday (Mon=0 .. Sun=6): (open, close)
HOURS = {0: (7, 20), 1: (7, 20), 2: (7, 20), 3: (7, 20), 4: (7, 20), 5: (7, 18), 6: (9, 17)}
# Python weekday -> baseline.json day key
DOW = {0: "Mon", 1: "Tues", 2: "Wed", 3: "Thurs", 4: "Fri", 5: "Sat", 6: "Sun"}
STALE_HOURS = 2            # flag data older than this during open hours
HIST_DAYS = 42            # how far back to pull by-hour history (~6 weeks -> 4+ same-DOW)

# Forecast parameters (spec section 9 - implemented exactly)
RECENCY_W = [0.40, 0.30, 0.20, 0.10]   # weeks [1,2,3,4] back, newest first
MAD_K = 3.0                             # outlier threshold in MAD units (~2 sigma)
PACE_CLAMP = (0.7, 1.5)                 # clamp intraday pace factor

# Backtest error (spec section 9) -> forecast bands, so nothing looks too precise
ERR_HOUR = 0.35     # single hour-block ~35% (directional only)
ERR_DAY = 0.16      # daily ~16%

# ---- Take 5 / VantEdge palette (forced high-contrast light theme) ----
NAVY = "#14273F"    # structure / headers
BLUE = "#2E6FB7"    # today's actual
GREEN = "#1E8E4E"   # ahead / projected
RED = "#E4002B"     # Take 5 red - alerts / behind
AMBER = "#E6A200"   # caution
INK = "#1F2A37"     # body text
MUTE = "#5B6B7F"    # secondary text
STEEL = "#9FB4CC"   # Normal/Goal bars
LINE = "#E3E8EF"    # borders
LIGHT = "#F4F7FB"   # tints
CODE = "#8DA2BD"    # gray store-code text in the title
AREA = "rgba(46,111,183,0.12)"   # soft normal-curve fill

# Heat-map color scale (higher-contrast, more distinct than a near-mono navy ramp)
HEAT_SCALE = [[0.0, "#F7FBFF"], [0.25, "#CFE1F2"], [0.5, "#94C4DF"],
              [0.75, "#4A98C9"], [1.0, "#1F6FB2"]]

# Metrics offered in selectors (heat map / comparison). "aro" and "lhpc" are
# RATES (revenue-per-car, labor-hours-per-car), not running totals.
METRICS = {
    "Cars": {"key": "cars", "money": False},
    "Net sales": {"key": "net_sales", "money": True},
    "Big 4 units": {"key": "big4_total_units", "money": False},
    "ARO": {"key": "aro", "money": True},
    "Labor hrs/car": {"key": "lhpc", "money": False},
}
RATE_KEYS = ("aro", "lhpc")   # ratios: shown as-is per hour, never differenced

st.set_page_config(page_title=f"{BRAND} - Store Scorecard", layout="wide",
                   initial_sidebar_state="expanded")

# Global CSS. NOTE: generous top padding + no overflow clipping on the header
# so the navy wordmark bar always renders in full (v1 shipped a clipped bar).
st.markdown(
    """
    <style>
      .block-container {padding-top: 1.4rem; padding-bottom: 2rem; max-width: 1280px;}
      #MainMenu, footer, header [data-testid="stToolbar"] {visibility: hidden;}
      html, body, [class*="css"] {color: #1F2A37;}
      .stApp {background: #FFFFFF;}
      /* keep everything inside the header visible - never clip */
      .vea-head, .vea-head * {overflow: visible !important;}
      @media print {
        section[data-testid="stSidebar"], .stButton, [data-testid="stToolbar"],
        .vea-noprint {display: none !important;}
        .block-container {max-width: 100% !important; padding-top: 0 !important;}
      }
    </style>
    """,
    unsafe_allow_html=True,
)


# ==========================================================================
# Pure helpers (unit-tested)
# ==========================================================================
def fmt(value, money=False, dp=0):
    """Human number. None -> em dash."""
    if value is None:
        return "—"
    try:
        return ("$" if money else "") + format(float(value), f",.{dp}f")
    except (TypeError, ValueError):
        return "—"


def hour_label(h):
    ap = "a" if h < 12 else "p"
    h12 = h % 12 or 12
    return f"{h12}{ap}"


def store_display(store, latest=None):
    """Friendly store NAME for display - never the bare store number."""
    return CITY.get(store) or (latest or {}).get("store_name") or "Your store"


def frac_elapsed(now):
    """Fraction of today's OPEN hours elapsed (linear fallback for pacing)."""
    o, c = HOURS[now.weekday()]
    span = (c - o) or 1
    return max(0.0, min(1.0, ((now.hour + now.minute / 60) - o) / span))


def status_color(actual, expected):
    """Green ahead, amber within ~10% behind, red further behind, INK if no goal."""
    if expected is None or expected == 0 or actual is None:
        return INK
    ratio = actual / expected
    if ratio >= 1.0:
        return GREEN
    if ratio >= 0.90:
        return AMBER
    return RED


def arrow(actual, expected):
    """Trend glyph vs expected. Neutral dot if no goal."""
    if expected is None or actual is None:
        return "•"          # bullet (neutral)
    if actual >= expected:
        return "▲"          # up triangle
    return "▼"              # down triangle


def pace_state(actual, expected):
    """SINGLE source of truth for ahead/on-pace/behind, used by cards, the
    staffing callout, ranking, and the exec count. Same 100%/90% bands as
    status_color so nothing contradicts.
      ahead  : actual >= 100% of goal-by-now  (green)
      on pace: 90-100%                         (amber)
      behind : < 90%                           (red)
    Returns (label, color, is_ahead)."""
    if expected is None or expected == 0 or actual is None:
        return ("no goal", INK, None)
    ratio = actual / expected
    if ratio >= 1.0:
        return ("ahead of pace", GREEN, True)
    if ratio >= 0.90:
        return ("on pace", AMBER, False)
    return ("behind pace", RED, False)


# ---- holidays: the historical "normal" must EXCLUDE these (and observed dates) ----
def _nth_weekday(year, month, weekday, n):
    """n-th weekday (Mon=0..Sun=6) of a month; n<0 counts from the end."""
    if n > 0:
        d = dt.date(year, month, 1)
        offset = (weekday - d.weekday()) % 7
        return d + dt.timedelta(days=offset + 7 * (n - 1))
    # last occurrence
    if month == 12:
        d = dt.date(year, 12, 31)
    else:
        d = dt.date(year, month + 1, 1) - dt.timedelta(days=1)
    offset = (d.weekday() - weekday) % 7
    return d - dt.timedelta(days=offset)


def us_holidays(year):
    """Standard US holidays for a year PLUS their observed (Fri/Mon) dates."""
    fixed = [
        dt.date(year, 1, 1),    # New Year's Day
        dt.date(year, 6, 19),   # Juneteenth
        dt.date(year, 7, 4),    # Independence Day
        dt.date(year, 11, 11),  # Veterans Day
        dt.date(year, 12, 25),  # Christmas Day
    ]
    floating = [
        _nth_weekday(year, 1, 0, 3),    # MLK Day (3rd Mon Jan)
        _nth_weekday(year, 2, 0, 3),    # Presidents' Day (3rd Mon Feb)
        _nth_weekday(year, 5, 0, -1),   # Memorial Day (last Mon May)
        _nth_weekday(year, 9, 0, 1),    # Labor Day (1st Mon Sep)
        _nth_weekday(year, 10, 0, 2),   # Columbus / Indigenous Peoples' (2nd Mon Oct)
        _nth_weekday(year, 11, 3, 4),   # Thanksgiving (4th Thu Nov)
    ]
    out = set(fixed) | set(floating)
    for d in fixed:                     # observed shifts for fixed-date holidays
        if d.weekday() == 5:            # Saturday -> observed Friday
            out.add(d - dt.timedelta(days=1))
        elif d.weekday() == 6:          # Sunday -> observed Monday
            out.add(d + dt.timedelta(days=1))
    return out


def is_holiday(d):
    """True if date d is a standard US holiday or an observed date."""
    if d is None:
        return False
    return d in us_holidays(d.year)


# ---- row / snapshot parsing ----
def row_date(row):
    parts = (row.get("pull_hour") or "").split("-")
    return "-".join(parts[:3]) if len(parts) >= 3 else None


def row_hour(row):
    parts = (row.get("pull_hour") or "").split("-")
    try:
        return int(parts[3]) if len(parts) >= 4 else None
    except ValueError:
        return None


def _labor_block(row):
    data = row.get("data") or {}
    return data.get("labor") or row.get("labor") or {}


def _get_metric(row, key):
    """Read a metric off a snapshot row. ARO / labor-per-car are derived rates;
    labor hours come from the `data` jsonb block."""
    if key == "aro":
        cars = row.get("cars") or 0
        net = row.get("net_sales")
        return (net / cars) if (cars and net is not None) else None
    if key == "lhpc":                       # labor hours per car
        cars = row.get("cars") or 0
        hrs = _labor_block(row).get("hours")
        if hrs is not None and cars:
            return hrs / cars
        return _labor_block(row).get("hours_per_car")
    if key == "labor_hours":
        return _labor_block(row).get("hours")
    return row.get(key)


def cum_by_hour(rows, key):
    """From rows for ONE day -> {hour: cumulative value} (latest pull per hour wins)."""
    out = {}
    for r in sorted(rows, key=lambda x: x.get("pull_time") or ""):
        h = row_hour(r)
        if h is None:
            continue
        v = _get_metric(r, key)
        if v is not None:
            out[h] = v
    return out


def to_per_period(cum):
    """Cumulative-by-hour -> per-hour increments. First present hour keeps its value.

    A per-period value is the difference between consecutive hourly snapshots.
    ARO (a rate, not a running total) is passed through unchanged per hour.
    """
    if not cum:
        return {}
    hours = sorted(cum)
    pp, prev = {}, 0.0
    for h in hours:
        pp[h] = cum[h] - prev
        prev = cum[h]
    return pp


def to_per_period_metric(cum, key):
    """Per-period for a cumulative metric; rates (ARO, labor/car) are not differenced."""
    if key in RATE_KEYS:
        return dict(cum)
    return to_per_period(cum)


def median(xs):
    return statistics.median(xs) if xs else None


def mad(xs, med=None):
    if not xs:
        return None
    med = statistics.median(xs) if med is None else med
    return statistics.median([abs(x - med) for x in xs])


def reject_outliers(values, k=MAD_K):
    """Return (kept_values, kept_indices) using MAD rule |x-med| <= k*mad."""
    if not values:
        return [], []
    med = statistics.median(values)
    m = statistics.median([abs(x - med) for x in values])
    thresh = k * m
    kept, idx = [], []
    for i, x in enumerate(values):
        if abs(x - med) <= thresh:
            kept.append(x)
            idx.append(i)
    if not kept:                    # safety: never discard everything
        return list(values), list(range(len(values)))
    return kept, idx


def weighted_baseline(values, weights=RECENCY_W, k=MAD_K):
    """Spec section 9 steps 1-2. `values` newest-first (index 0 = most recent week).

    1) MAD outlier rejection. 2) recency-weighted mean over kept samples
       (weights renormalized across the survivors). Returns None if empty.
    """
    values = [v for v in values if v is not None]
    if not values:
        return None
    kept, idx = reject_outliers(values, k)
    num = sum(weights[i] * values[i] for i in idx)
    den = sum(weights[i] for i in idx)
    return (num / den) if den else statistics.fmean(kept)


def pace_factor(actual_by_hour, baseline_by_hour, completed_hours, clamp=PACE_CLAMP):
    """Spec section 9 step 3: sum(actual completed) / sum(baseline completed), clamped."""
    num = sum(actual_by_hour.get(h, 0) for h in completed_hours)
    den = sum(baseline_by_hour.get(h, 0) for h in completed_hours if baseline_by_hour.get(h))
    if not den:
        return None
    return max(clamp[0], min(clamp[1], num / den))


def hour_baselines(history_rows, weekday, key):
    """Holiday-clean recency-weighted per-hour baseline (spec section 9 steps 1-2).

    Groups history by date, keeps same-weekday non-holiday dates, takes the last
    4 occurrences (newest first), and returns {hour: baseline_per_hour}.
    """
    by_date = {}
    for r in history_rows:
        d = row_date(r)
        if d:
            by_date.setdefault(d, []).append(r)
    dated = []
    for d, rows in by_date.items():
        try:
            date = dt.date.fromisoformat(d)
        except (ValueError, TypeError):
            continue
        if date.weekday() == weekday and not is_holiday(date):
            dated.append((date, rows))
    dated.sort(key=lambda t: t[0], reverse=True)     # newest first
    dated = dated[:len(RECENCY_W)]                    # last 4 occurrences
    if not dated:
        return {}
    per_date_pp = [to_per_period_metric(cum_by_hour(rows, key), key) for _, rows in dated]
    hours = sorted({h for pp in per_date_pp for h in pp})
    out = {}
    for h in hours:
        samples = [pp.get(h) for pp in per_date_pp]   # newest-first, None where missing
        vals = [v for v in samples if v is not None]
        if not vals:
            continue
        # weights aligned to each sample's recency position (skip missing weeks)
        vals_ord, w_ord = [], []
        for i, v in enumerate(samples):
            if v is not None:
                vals_ord.append(v)
                w_ord.append(RECENCY_W[i] if i < len(RECENCY_W) else RECENCY_W[-1])
        kept, idx = reject_outliers(vals_ord)
        num = sum(w_ord[i] * vals_ord[i] for i in idx)
        den = sum(w_ord[i] for i in idx)
        out[h] = (num / den) if den else statistics.fmean(kept)
    return out


def forecast_hours(hours, today_pp, base_hours):
    """Spec section 9 steps 3-4. Returns (actual{}, projected{}, pace, completed_hours).

    actual  = per-hour values already booked today (blue bars).
    projected = base_hour * pace for hours not yet completed (green bars).
    """
    completed = sorted(today_pp)                       # hours with data = completed
    last = completed[-1] if completed else None
    future = [h for h in hours if (last is None or h > last)]
    pace = pace_factor(today_pp, base_hours, completed) if base_hours else None
    p = pace if pace is not None else 1.0
    projected = {h: base_hours[h] * p for h in future if base_hours.get(h) is not None}
    return dict(today_pp), projected, pace, completed


def rank_stores(store_stats):
    """Sort desc by pace pct (stores with no data last)."""
    return sorted(store_stats, key=lambda s: (s.get("pct") is None, -(s.get("pct") or 0)))


# ==========================================================================
# Supabase access (cached; guarded so the UI never crashes on a bad read)
# ==========================================================================
@st.cache_data(ttl=300, show_spinner=False)
def sb_get(path):
    url = st.secrets["SUPABASE_URL"].rstrip("/")
    key = st.secrets["SUPABASE_KEY"]
    r = requests.get(url + "/rest/v1/" + path,
                     headers={"apikey": key, "Authorization": "Bearer " + key},
                     timeout=25)
    r.raise_for_status()
    return r.json()


def fetch_today(store):
    today = dt.datetime.now(CENTRAL).strftime("%Y-%m-%d")
    try:
        return sb_get(f"daily_sales_pull?store_number=eq.{store}"
                      f"&pull_hour=like.{today}*&order=pull_time.asc")
    except Exception:
        return []


def fetch_history(store, days=HIST_DAYS):
    since = (dt.datetime.now(CENTRAL) - dt.timedelta(days=days)).strftime("%Y-%m-%d")
    cols = "pull_hour,pull_time,cars,net_sales,big4_total_units,data,report_timestamp"
    try:
        return sb_get(f"daily_sales_pull?store_number=eq.{store}"
                      f"&pull_time=gte.{since}&select={cols}&order=pull_time.asc")
    except Exception:
        return []


@st.cache_data(show_spinner=False)
def load_baseline():
    try:
        with open("baseline.json") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


# ==========================================================================
# UI atoms
# ==========================================================================
def wordmark(sub):
    """Centered header: brand row on top, context line (store name/date) below,
    both centered and vertically balanced in the navy box."""
    st.markdown(
        f'<div class="vea-head" style="background:{NAVY};border-radius:12px;'
        f'padding:18px 24px;margin:0 0 12px 0;display:flex;flex-direction:column;'
        f'align-items:center;justify-content:center;text-align:center;'
        f'box-sizing:border-box;min-height:74px;gap:5px;">'
        f'<div style="display:flex;align-items:center;justify-content:center;gap:12px;">'
        f'<div style="width:9px;height:30px;background:{RED};border-radius:2px;flex:none;"></div>'
        f'<div style="color:#fff;font-size:1.5rem;font-weight:800;letter-spacing:.03em;line-height:1.1;">'
        f'{BRAND}<span style="color:{STEEL};font-weight:500;font-size:.85rem;">'
        f' &nbsp;&middot;&nbsp; {SUBBRAND}</span></div></div>'
        f'<div style="color:#DCE5F0;font-size:.92rem;line-height:1.3;">{sub}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def freshness(latest, now):
    ts = latest.get("report_timestamp") or "—"
    color, age_note = GREEN, ""
    try:
        pt = dt.datetime.fromisoformat(latest.get("pull_time")).astimezone(CENTRAL)
        hrs = (now - pt).total_seconds() / 3600
        o, c = HOURS[now.weekday()]
        open_now = o <= now.hour < c
        if open_now and hrs > STALE_HOURS:
            color, age_note = AMBER, f" &nbsp;⚠ last pull {hrs:.1f}h ago"
    except (TypeError, ValueError):
        pass
    st.markdown(
        f'<div style="font-size:.84rem;color:{MUTE};margin:-4px 0 12px 2px;">'
        f'<span style="color:{color};font-size:1rem;">●</span> Data as of {ts}{age_note}</div>',
        unsafe_allow_html=True,
    )


def section_title(text, note=""):
    extra = (f'<span style="font-weight:500;font-size:.8rem;color:{MUTE};'
             f'margin-left:8px;">{note}</span>') if note else ""
    st.markdown(
        f'<div style="border-left:4px solid {RED};padding-left:11px;margin:22px 0 10px;'
        f'font-size:1.05rem;font-weight:800;color:{NAVY};">{text}{extra}</div>',
        unsafe_allow_html=True,
    )


def kpi_card(label, value, goal_txt, delta_txt, pct, color, tip):
    """Bullet-style KPI card: value, goal, signed variance + arrow, color status."""
    fill = min(100, max(4, pct / 1.5)) if pct is not None else 0     # 150% -> full bar
    goal_line = (f"<div style='position:absolute;left:66.6%;top:0;bottom:0;width:2px;"
                 f"background:{INK};opacity:.5;'></div>") if pct is not None else ""
    delta_html = (f"<span style='color:{color};font-weight:800;'>{delta_txt}</span>"
                  if delta_txt else "<span style='color:#9AA7B5;'>no goal yet</span>")
    return (
        f'<div title="{tip}" style="flex:1 1 165px;min-width:150px;background:#fff;'
        f'border:1px solid {LINE};border-top:3px solid {color};border-radius:10px;padding:12px 14px;">'
        f'<div style="font-size:.68rem;letter-spacing:.06em;color:{MUTE};text-transform:uppercase;">{label}</div>'
        f'<div style="font-size:1.72rem;font-weight:800;color:{INK};line-height:1.15;">{value}</div>'
        f'<div style="font-size:.75rem;color:{MUTE};margin-bottom:7px;white-space:nowrap;">'
        f'{goal_txt} &nbsp; {delta_html}</div>'
        f'<div style="position:relative;height:7px;background:{LIGHT};border-radius:4px;overflow:hidden;">'
        f'<div style="width:{fill:.0f}%;height:100%;background:{color};"></div>{goal_line}</div></div>'
    )


def detail_strip(pairs):
    cells = "".join(
        f'<div style="flex:1 1 140px;min-width:130px;padding:9px 13px;border:1px solid {LINE};'
        f'border-radius:9px;background:#fff;">'
        f'<div style="font-size:.65rem;text-transform:uppercase;letter-spacing:.05em;color:{MUTE};">{k}</div>'
        f'<div style="font-size:1.12rem;font-weight:700;color:{INK};">{v}</div></div>' for k, v in pairs)
    st.markdown(f'<div style="display:flex;gap:9px;flex-wrap:wrap;">{cells}</div>',
                unsafe_allow_html=True)


# ==========================================================================
# Charts
# ==========================================================================
def _layout(fig, height, title=None, legend="bottom", hovermode="closest"):
    """Shared chart chrome. Legend defaults to the BOTTOM so it never collides
    with the title (a top legend overlapped the title in the first pass)."""
    show = legend != "none"
    lg = None
    if legend == "bottom":
        lg = dict(orientation="h", yanchor="top", y=-0.16, x=0, font=dict(size=11))
    elif legend == "top":
        lg = dict(orientation="h", yanchor="bottom", y=1.03, x=0, font=dict(size=11))
    fig.update_layout(
        height=height,
        margin=dict(l=12, r=12, t=46 if title else 14,
                    b=64 if (show and legend == "bottom") else 16),
        paper_bgcolor="white", plot_bgcolor="white", font_color=INK, font_size=12,
        title={"text": title, "font": {"color": NAVY, "size": 15}, "x": 0.01, "xanchor": "left"}
        if title else None,
        showlegend=show, legend=lg, bargap=0.12, hovermode=hovermode,
    )
    fig.update_xaxes(gridcolor=LINE, zeroline=False)
    fig.update_yaxes(gridcolor=LINE, zeroline=False)
    return fig


def chart_per_hour(hours, normal, actual, projected, money, label):
    """Chart 1 (per Excel): CLUSTERED COLUMNS by time of day - Normal/Goal, Actual,
    Projected. Actual and Projected share one slot (same offsetgroup) so there is
    no empty gap between Normal/Goal and Projected when Actual is absent."""
    x = [hour_label(h) for h in hours]
    pref = "$" if money else ""
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=x, y=[normal.get(h) for h in hours], name="Normal/Goal",
        marker_color=STEEL, marker_line_width=0, offsetgroup="norm",
        hovertemplate="Normal/Goal: " + pref + "%{y:,.0f}<extra></extra>"))
    fig.add_trace(go.Bar(
        x=x, y=[actual.get(h) for h in hours], name="Actual",
        marker_color=BLUE, marker_line_width=0, offsetgroup="today",
        hovertemplate="Actual: " + pref + "%{y:,.0f}<extra></extra>"))
    if projected:
        fig.add_trace(go.Bar(
            x=x, y=[projected.get(h) for h in hours], name="Projected",
            marker_color=GREEN, marker_line_width=0, offsetgroup="today",
            hovertemplate="Projected: " + pref + "%{y:,.0f}<extra></extra>"))
    fig.update_layout(barmode="group", bargap=0.28, bargroupgap=0.0)
    fig.update_yaxes(title=("$ per hour" if money else "per hour"), rangemode="tozero")
    return _layout(fig, 360, f"Per hour: today vs Normal/Goal - {label}",
                   legend="bottom", hovermode="x unified")


def chart_gauge(value, expected_now, goal_day, money, label, dp=0):
    """Chart 2 (per Excel): enhanced semicircle speedometer gauge.

    Arc spans the whole day (0 -> day's Normal/Goal). The filled arc = value so
    far; the marker (threshold) = where a normal day would be BY NOW. Fill past
    the marker = ahead of pace (green); short of it = behind (red). Center shows
    the current value.
    """
    pref = "$" if money else ""
    ends = [v for v in (goal_day, value, expected_now) if v]
    axis_max = (max(ends) * 1.05) if ends else 1
    _, bar_color, _ = pace_state(value, expected_now)
    if bar_color == INK:                       # no goal yet -> neutral fill
        bar_color = BLUE
    gauge = {
        "shape": "angular",
        "axis": {"range": [0, axis_max], "tickcolor": MUTE, "tickwidth": 1},
        "bar": {"color": bar_color, "thickness": 0.30},
        "bgcolor": "#EEF2F7", "borderwidth": 0,
        "steps": [{"range": [0, axis_max], "color": "#EEF2F7"}],
    }
    if expected_now:
        gauge["threshold"] = {"line": {"color": INK, "width": 4},
                              "thickness": 0.92, "value": expected_now}
    fig = go.Figure(go.Indicator(
        mode="gauge+number", value=value or 0,
        number={"font": {"size": 44, "color": INK},
                "prefix": pref, "valueformat": f",.{dp}f"},
        gauge=gauge, domain={"x": [0, 1], "y": [0, 1]}))
    sub = (f"marker = normal-day pace by now ({pref}{expected_now:,.{dp}f})"
           if expected_now else "goal builds as history accumulates")
    fig.add_annotation(text=sub, showarrow=False, x=0.5, y=-0.02,
                       font=dict(size=11, color=MUTE))
    return _layout(fig, 300, f"{label} vs a normal day", legend="none")


def chart_mix_bar(items):
    """100% stacked product-mix bar (dollar share), tiny slices grouped into Other."""
    items = [(i.get("description", "?"), i.get("amount") or 0) for i in items
             if (i.get("amount") or 0) > 0]
    total = sum(a for _, a in items) or 1
    items.sort(key=lambda t: t[1], reverse=True)
    keep, other = [], 0.0
    for name, amt in items:
        if amt / total >= 0.03:
            keep.append((name, amt))
        else:
            other += amt
    if other > 0:
        keep.append(("Other", other))
    palette = [NAVY, BLUE, GREEN, AMBER, RED, "#6C7A91", "#9DB6D4", "#B5651D", "#3E8E7E"]
    fig = go.Figure()
    for i, (name, amt) in enumerate(keep):
        share = amt / total * 100
        fig.add_trace(go.Bar(
            x=[share], y=["Mix"], orientation="h", name=name,
            marker_color=palette[i % len(palette)],
            text=[f"{share:.0f}%" if share >= 6 else ""], textposition="inside",
            insidetextanchor="middle", textfont=dict(color="#fff", size=12),
            hovertemplate=f"{name}: ${amt:,.0f} (%{{x:.0f}}%)<extra></extra>"))
    fig.update_layout(barmode="stack")
    fig.update_xaxes(title=None, range=[0, 100], ticksuffix="%")
    fig.update_yaxes(showticklabels=False)
    return _layout(fig, 250, "Product mix - share of dollars (100%)", legend="bottom")


def chart_products_bar(items):
    """Standard horizontal bar chart of revenue by product line (replaces the
    treemap). Sorted largest at top; labeled with dollars."""
    rows = [(i.get("description", "?"), i.get("amount") or 0) for i in items
            if (i.get("amount") or 0) > 0]
    if not rows:
        return None
    rows.sort(key=lambda t: t[1])            # ascending -> largest ends up on top
    names = [n for n, _ in rows]
    vals = [a for _, a in rows]
    fig = go.Figure(go.Bar(
        x=vals, y=names, orientation="h", marker_color=NAVY,
        text=[f"${a:,.0f}" for a in vals], textposition="outside", cliponaxis=False,
        hovertemplate="%{y}: $%{x:,.0f}<extra></extra>"))
    fig.update_xaxes(title="$ today", rangemode="tozero")
    return _layout(fig, max(300, 26 * len(rows)),
                   "Revenue by product line (today)", legend="none")


def chart_big4(big4):
    order = ["Air Filter", "Wiper Blade", "Cabin Filter", "Coolant Exchange"]
    names = [n for n in order if n in big4] or list(big4.keys())
    attach = [(big4.get(n) or {}).get("attach_pct") or 0 for n in names]
    fig = go.Figure(go.Bar(x=names, y=attach, marker_color=NAVY,
                           text=[f"{a:.0f}%" for a in attach], textposition="outside",
                           cliponaxis=False))
    fig.update_yaxes(title="% of cars", rangemode="tozero")
    return _layout(fig, 260, "Big 4 attachment (% of cars)", legend="none")


# ==========================================================================
# Store view
# ==========================================================================
def _kpi_section(store, hist, today_rows, hours, weekday, key, money, label,
                 daily_normal):
    """Render one KPI section = Chart 1 (clustered columns) + Chart 2 (gauge)."""
    base_h = hour_baselines(hist, weekday, key)
    today_cum = cum_by_hour(today_rows, key)
    today_pp = to_per_period_metric(today_cum, key)
    actual, projected, pace, completed = forecast_hours(hours, today_pp, base_h)

    c1, c2 = st.columns([1.35, 1])
    with c1:
        st.plotly_chart(chart_per_hour(hours, base_h, actual, projected, money, label),
                        use_container_width=True)
        if not base_h:
            st.caption("Normal/Goal curve builds as more same-weekday hourly data accumulates "
                       "(needs a few weeks of pulls). Bars show today's actual per hour.")

    # ---- gauge maths for Chart 2 (day goal + goal-by-now marker) ----
    actual_so_far = sum(today_pp.values())
    goal_day = (sum(base_h.values()) if base_h else None) or daily_normal
    if base_h and completed:
        expected_now = sum(base_h.get(h, 0) for h in completed)
    elif daily_normal and hours:
        expected_now = daily_normal * (len(completed) / len(hours))
    else:
        expected_now = None
    with c2:
        st.plotly_chart(chart_gauge(actual_so_far, expected_now, goal_day, money, label),
                        use_container_width=True)
    return {"pace": pace, "goal_day": goal_day, "expected_now": expected_now,
            "actual_day": actual_so_far}


def render_store(store, baseline):
    now = dt.datetime.now(CENTRAL)
    weekday = now.weekday()
    day = DOW[weekday]
    o, c = HOURS[weekday]
    hours = list(range(o, c + 1))
    rows = fetch_today(store)
    hist = fetch_history(store)

    b = baseline.get(store, {})
    cars_base = b.get("cars", {}).get(day)
    sales_base = b.get("net_sales", {}).get(day)
    cars_norm_day = cars_base["mean"] if cars_base else None
    sales_norm_day = sales_base["mean"] if sales_base else None
    aro_norm = (sales_norm_day / cars_norm_day) if (cars_norm_day and sales_norm_day) else None

    code_html = f'<span style="color:{CODE};">({store})</span>'
    if not rows:
        wordmark(f"{store_display(store)} {code_html} &middot; {now:%A, %b %-d}")
        st.info("No data pulled yet today. This fills in on the first pull after the store opens.")
        return

    latest = rows[-1]
    frac = frac_elapsed(now)
    wordmark(f"{store_display(store, latest)} {code_html} &middot; {now:%A, %b %-d} &middot; "
             f"{frac*100:.0f}% through the day")
    freshness(latest, now)
    st.markdown(
        f'<div class="vea-noprint" style="text-align:right;margin:-6px 0 8px;">'
        f'<button onclick="window.print()" style="padding:7px 16px;border:1px solid {LINE};'
        f'border-radius:8px;background:#fff;color:{NAVY};font-weight:700;cursor:pointer;">'
        f'&#128424;&#65039; Print this scorecard</button></div>', unsafe_allow_html=True)

    cars = latest.get("cars") or 0
    net = latest.get("net_sales") or 0
    aro = (net / cars) if cars else 0
    payload = latest.get("data") or {}
    lab = payload.get("labor") or latest.get("labor") or {}

    # ---- expected-by-now, from the holiday-clean per-hour normal when available ----
    cars_base_h = hour_baselines(hist, weekday, "cars")
    completed = [h for h in hours if h in to_per_period(cum_by_hour(rows, "cars"))]
    if cars_base_h and completed:
        cars_expect_now = sum(cars_base_h.get(h, 0) for h in completed)
        sales_base_h = hour_baselines(hist, weekday, "net_sales")
        sales_expect_now = sum(sales_base_h.get(h, 0) for h in completed) or (
            sales_norm_day * frac if sales_norm_day else None)
    else:
        cars_expect_now = cars_norm_day * frac if cars_norm_day else None
        sales_expect_now = sales_norm_day * frac if sales_norm_day else None

    # ---- projected end-of-day cars (drives the staffing callout) ----
    cars_pp = to_per_period(cum_by_hour(rows, "cars"))
    _, cars_proj, cars_pace, _ = forecast_hours(hours, cars_pp, cars_base_h)
    if cars_base_h and (cars_pp or cars_proj):
        cars_eod = sum(cars_pp.values()) + sum(cars_proj.values())
    elif cars_norm_day and frac > 0.05:
        cars_eod = cars / frac                      # simple pace fallback
    else:
        cars_eod = cars_norm_day

    # ---- staffing bottom line (loudest element) — SAME pace bands as the cards ----
    state, vcolor, _ = pace_state(cars, cars_expect_now)
    if cars_expect_now is None:
        verdict = "Tracking today's pace."
        vcolor = NAVY
    elif state == "ahead of pace":
        verdict = "Ahead of the goal pace — keep full staffing on."
    elif state == "on pace":
        verdict = "On the goal pace."
    else:
        verdict = "Behind the goal pace — you may be over-staffed right now."
    eod_txt = (f" Projected to finish about <b>{cars_eod:,.0f} cars</b> "
               f"(goal for {day} ≈ {cars_norm_day:,.0f})." if cars_eod and cars_norm_day
               else (f" Projected to finish about <b>{cars_eod:,.0f} cars</b>." if cars_eod else ""))
    st.markdown(
        f'<div style="border-left:6px solid {vcolor};background:{LIGHT};padding:14px 20px;'
        f'border-radius:8px;margin-bottom:16px;font-size:1.05rem;line-height:1.5;">'
        f'<b>Bottom line —</b> {cars:,.0f} cars / ${net:,.0f} booked so far.{eod_txt} '
        f'<b style="color:{vcolor};">{verdict}</b></div>',
        unsafe_allow_html=True)

    # ---- five pinned KPI cards ----
    cards = [
        kpi_card("Cars", f"{cars:,.0f}",
                 f"goal by now ~{cars_expect_now:,.0f}" if cars_expect_now else "no goal",
                 (f"{arrow(cars, cars_expect_now)} {cars-cars_expect_now:+,.0f}"
                  if cars_expect_now else ""),
                 (cars / cars_expect_now * 100) if cars_expect_now else None,
                 status_color(cars, cars_expect_now),
                 "Cars booked so far vs the Normal/Goal by this time of day."),
        kpi_card("Net revenue", f"${net:,.0f}",
                 f"goal by now ~${sales_expect_now:,.0f}" if sales_expect_now else "no goal",
                 (f"{arrow(net, sales_expect_now)} {net-sales_expect_now:+,.0f}"
                  if sales_expect_now else ""),
                 (net / sales_expect_now * 100) if sales_expect_now else None,
                 status_color(net, sales_expect_now),
                 "Net sales so far vs the Normal/Goal by this time of day."),
        kpi_card("ARO", f"${aro:,.2f}",
                 f"goal ${aro_norm:,.2f}" if aro_norm else "no goal",
                 (f"{arrow(aro, aro_norm)} {aro-aro_norm:+,.2f}" if aro_norm else ""),
                 (aro / aro_norm * 100) if aro_norm else None,
                 status_color(aro, aro_norm),
                 "Average revenue per car vs this store's Normal/Goal ARO for this weekday."),
        kpi_card("Big 4 units", f"{latest.get('big4_total_units') or 0:,.0f}",
                 f"${latest.get('big4_total_amount') or 0:,.0f} attach $", "", None, NAVY,
                 "Big 4 attachment units today (Air Filter, Wiper, Cabin, Coolant). No goal set yet."),
        kpi_card("Labor hrs/car", f"{lab.get('hours_per_car') or 0:,.2f}",
                 f"{lab.get('pct_of_net') or 0:.0f}% of net", "", None, NAVY,
                 "Labor hours per car - an efficiency proxy (lower is leaner). No goal set yet."),
    ]
    st.markdown(f'<div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:4px;">'
                f'{"".join(cards)}</div>', unsafe_allow_html=True)

    # ---- one section per KPI, each with two charts (columns + gauge) ----
    section_title("Cars", "columns by hour vs Normal/Goal, plus the day-goal gauge")
    _kpi_section(store, hist, rows, hours, weekday, "cars", False, "Cars", cars_norm_day)

    section_title("Net revenue", "columns by hour vs Normal/Goal, plus the day-goal gauge")
    _kpi_section(store, hist, rows, hours, weekday, "net_sales", True, "Net", sales_norm_day)

    section_title("ARO", "revenue per car through the day")
    ca, cb = st.columns([1.35, 1])
    aro_base_h = hour_baselines(hist, weekday, "aro")
    aro_pp = to_per_period_metric(cum_by_hour(rows, "aro"), "aro")
    aro_actual, aro_projected, _, _ = forecast_hours(hours, aro_pp, aro_base_h)
    with ca:
        st.plotly_chart(chart_per_hour(hours, aro_base_h, aro_actual, aro_projected, True, "ARO"),
                        use_container_width=True)
        if not aro_base_h:
            st.caption("ARO-by-hour Normal/Goal builds as data accumulates.")
    with cb:
        # ARO is a rate: goal = this store's normal ARO for the weekday
        st.plotly_chart(chart_gauge(aro if aro else None, aro_norm, aro_norm, True, "ARO", dp=2),
                        use_container_width=True)

    section_title("Big 4 attachment", "columns by hour vs Normal/Goal, plus the day-goal gauge")
    _kpi_section(store, hist, rows, hours, weekday, "big4_total_units", False, "Big 4", None)

    section_title("Labor hours", "columns by hour vs Normal/Goal, plus the day-goal gauge")
    _kpi_section(store, hist, rows, hours, weekday, "labor_hours", False, "Labor hrs", None)

    # ---- product mix: 100% stacked + standard product bar (treemap replaced) ----
    section_title("Product mix", "share of today's dollars")
    items = latest.get("line_items") or []
    big4 = latest.get("big4") or {}
    if items:
        m1, m2 = st.columns(2)
        m1.plotly_chart(chart_mix_bar(items), use_container_width=True)
        pb = chart_products_bar(items)
        if pb:
            m2.plotly_chart(pb, use_container_width=True)
    if big4:
        st.plotly_chart(chart_big4(big4), use_container_width=True)
    if not items and not big4:
        st.info("Product detail builds as the day's tickets come in.")

    # ---- operational detail strip ----
    section_title("Operational detail")
    fleets_count = payload.get("fleets_count", latest.get("fleets_count")) or 0
    fleets_amount = payload.get("fleets_amount", latest.get("fleets_amount")) or 0
    detail_strip([
        ("Materials %", f"{latest.get('materials_pct') or 0:.0f}%"),
        ("ASA", fmt(latest.get("asa"), money=True, dp=2)),
        ("Coupons", fmt(latest.get("coupons"), money=True)),
        ("Discounts", fmt(latest.get("discounts"), money=True)),
        ("New / Repeat", f"{latest.get('new_customers') or 0} / {latest.get('repeat_customers') or 0}"),
        ("Fleet", f"{fleets_count} / {fmt(fleets_amount, money=True)}"),
        ("Labor hours", fmt(lab.get("hours"), dp=1)),
    ])


# ==========================================================================
# Admin (all-stores) view
# ==========================================================================
def admin_snapshot(baseline):
    now = dt.datetime.now(CENTRAL)
    weekday = now.weekday()
    day = DOW[weekday]
    o, c = HOURS[weekday]
    hours = list(range(o, c + 1))
    frac = frac_elapsed(now)
    stats, today_rows, hist_rows = [], {}, {}
    for s in STORE_CODES:
        rows = fetch_today(s)
        today_rows[s] = rows
        hist_rows[s] = fetch_history(s)
        if not rows:
            stats.append({"store": s, "name": store_display(s), "cars": None,
                          "net": None, "aro": None, "lhpc": None, "labor_hours": None,
                          "pct": None})
            continue
        latest = rows[-1]
        cars = latest.get("cars") or 0
        net = latest.get("net_sales") or 0
        base_h = hour_baselines(hist_rows[s], weekday, "cars")
        completed = [h for h in hours if h in to_per_period(cum_by_hour(rows, "cars"))]
        if base_h and completed:
            exp = sum(base_h.get(h, 0) for h in completed)
        else:
            cb = baseline.get(s, {}).get("cars", {}).get(day)
            exp = cb["mean"] * frac if cb else None
        stats.append({"store": s, "name": store_display(s, latest), "cars": cars, "net": net,
                      "aro": (net / cars) if cars else 0,
                      "lhpc": _get_metric(latest, "lhpc"),
                      "labor_hours": _labor_block(latest).get("hours"),
                      "pct": (cars / exp * 100) if exp else None})
    return stats, today_rows, hist_rows


def render_admin(baseline):
    now = dt.datetime.now(CENTRAL)
    wordmark(f"All Stores &middot; {now:%A, %b %-d} &middot; "
             f"{frac_elapsed(now)*100:.0f}% through the day")
    stats, today_rows, hist_rows = admin_snapshot(baseline)
    live = [s for s in stats if s["cars"] is not None]

    # ---- exec KPI strip ----
    tot_cars = sum(s["cars"] for s in live)
    tot_net = sum(s["net"] for s in live)
    avg_aro = (tot_net / tot_cars) if tot_cars else 0
    tot_lhrs = sum((s.get("labor_hours") or 0) for s in live)
    avg_lhpc = (tot_lhrs / tot_cars) if tot_cars else 0
    ahead = sum(1 for s in live if (s["pct"] or 0) >= 100)   # >=100% of goal-by-now
    behind = len(live) - ahead
    strip = [
        ("Stores reporting", f"{len(live)}/{len(stats)}"),
        ("Total cars", f"{tot_cars:,.0f}"),
        ("Total net", f"${tot_net:,.0f}"),
        ("Avg ARO", f"${avg_aro:,.2f}"),
        ("Avg Labor hrs/car", f"{avg_lhpc:,.2f}"),
        ("Ahead / behind pace", f"{ahead} / {behind}" if live else "—"),
    ]
    cells = "".join(
        f'<div style="flex:1 1 150px;min-width:140px;background:#fff;border:1px solid {LINE};'
        f'border-top:3px solid {NAVY};border-radius:10px;padding:12px 14px;">'
        f'<div style="font-size:.68rem;text-transform:uppercase;letter-spacing:.05em;color:{MUTE};">{k}</div>'
        f'<div style="font-size:1.55rem;font-weight:800;color:{INK};">{v}</div></div>' for k, v in strip)
    st.markdown(f'<div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:4px;">'
                f'{cells}</div>', unsafe_allow_html=True)

    # ---- ranking ----
    section_title("Store ranking", "cars vs each store's goal pace — leaders to laggards")
    ranked = rank_stores(stats)
    trows = ""
    for i, s in enumerate(ranked, 1):
        pct = s["pct"]
        col = status_color(pct or 0, 100) if pct is not None else MUTE
        pcttxt = f"{pct:.0f}%" if pct is not None else "no data"
        trows += (
            f'<tr style="border-bottom:1px solid {LINE};">'
            f'<td style="padding:8px 12px;color:{MUTE};">{i}</td>'
            f'<td style="padding:8px 12px;font-weight:700;color:{INK};">{s["name"]}</td>'
            f'<td style="padding:8px 12px;text-align:right;">{fmt(s["cars"])}</td>'
            f'<td style="padding:8px 12px;text-align:right;">{fmt(s["net"], money=True)}</td>'
            f'<td style="padding:8px 12px;text-align:right;">{fmt(s["aro"], money=True, dp=2)}</td>'
            f'<td style="padding:8px 12px;text-align:right;">{fmt(s.get("lhpc"), dp=2)}</td>'
            f'<td style="padding:8px 12px;text-align:right;font-weight:800;color:{col};">{pcttxt}</td></tr>')
    st.markdown(
        f'<table style="width:100%;border-collapse:collapse;background:#fff;border:1px solid {LINE};'
        f'border-radius:10px;overflow:hidden;">'
        f'<tr style="background:{NAVY};color:#fff;font-size:.72rem;text-transform:uppercase;letter-spacing:.04em;">'
        f'<th style="padding:9px 12px;text-align:left;">#</th>'
        f'<th style="padding:9px 12px;text-align:left;">Store</th>'
        f'<th style="padding:9px 12px;text-align:right;">Cars</th>'
        f'<th style="padding:9px 12px;text-align:right;">Net</th>'
        f'<th style="padding:9px 12px;text-align:right;">ARO</th>'
        f'<th style="padding:9px 12px;text-align:right;">Labor/car</th>'
        f'<th style="padding:9px 12px;text-align:right;">% pace</th></tr>{trows}</table>',
        unsafe_allow_html=True)

    # ---- heat map: hour x store ----
    section_title("Heat map", "per-hour pattern, shaded vs each store's own peak")
    cA, cB = st.columns([1, 1])
    hm_metric = cA.radio("Metric", list(METRICS.keys()), horizontal=True, key="hm_metric")
    hm_source = cB.radio("Show", ["Today (actual)", "Normal/Goal pattern"], horizontal=True, key="hm_src")
    heatmap(today_rows, hist_rows, METRICS[hm_metric]["key"], hm_metric, hm_source)

    # ---- multi-store comparison (per-period) ----
    section_title("Compare stores", "per-hour, overlaid")
    picks = st.multiselect("Stores", STORE_CODES, default=STORE_CODES,
                           format_func=lambda s: CITY.get(s, s), key="cmp_stores")
    cmp_metric = st.radio("Metric", list(METRICS.keys()), horizontal=True, key="cmp_metric")
    comparison(picks, today_rows, METRICS[cmp_metric]["key"], METRICS[cmp_metric]["money"], cmp_metric)

    # ---- per-store drill-down ----
    section_title("Store drill-down", "same view a store manager sees")
    sel = st.selectbox("Store", STORE_CODES, format_func=lambda s: CITY.get(s, s), key="drill")
    with st.expander(f"Open {CITY.get(sel, sel)} scorecard", expanded=False):
        render_store(sel, baseline)

    # ---- export ----
    section_title("Export")
    export_controls(stats)


def heatmap(today_rows, hist_rows, key, label, source):
    now = dt.datetime.now(CENTRAL)
    weekday = now.weekday()
    o, c = HOURS[weekday]
    hrs = list(range(o, c + 1))
    stores = [s for s in STORE_CODES if (today_rows.get(s) or hist_rows.get(s))]
    if not stores:
        st.info("No store data yet for the heat map.")
        return

    # build a per-store, per-hour value dict from the chosen source
    per_store = {}
    for s in stores:
        if source.startswith("Today"):
            per_store[s] = to_per_period_metric(cum_by_hour(today_rows.get(s, []), key), key)
        else:
            per_store[s] = hour_baselines(hist_rows.get(s, []), weekday, key)

    if not any(per_store.values()):
        st.info("Normal/Goal pattern builds as several weeks of by-hour data accumulate. "
                "Switch to “Today (actual)” for live values.")
        return

    money = METRICS[label]["money"]
    z, text = [], []
    for h in hrs:
        zrow, trow = [], []
        for s in stores:
            v = per_store[s].get(h)
            zrow.append(v)
            trow.append("—" if v is None else
                        (f"${v:,.0f}" if money else (f"{v:.2f}" if key in RATE_KEYS else f"{v:,.0f}")))
        z.append(zrow)
        text.append(trow)
    # normalize each store (column) to its own peak so the PATTERN shows, not size
    znorm = [[None] * len(stores) for _ in hrs]
    for ci in range(len(stores)):
        col = [z[ri][ci] for ri in range(len(hrs))]
        nums = [v for v in col if v is not None]
        mx = max(nums) if nums else 0
        for ri, v in enumerate(col):
            znorm[ri][ci] = (v / mx) if (v is not None and mx) else (0 if v == 0 else None)
    fig = go.Figure(go.Heatmap(
        z=znorm, x=[CITY.get(s, s) for s in stores], y=[hour_label(h) for h in hrs],
        text=text, texttemplate="%{text}", textfont={"size": 11, "color": INK},
        colorscale=HEAT_SCALE, showscale=True, xgap=3, ygap=3,
        zmin=0, zmax=1, colorbar=dict(title="vs peak", tickformat=".0%"),
        hovertemplate="%{x} · %{y}<br>" + label + ": %{text}<extra></extra>"))
    fig.update_yaxes(autorange="reversed")
    st.plotly_chart(_layout(fig, max(320, 30 * len(hrs)),
                            f"{label} per hour — {source.lower()}", legend="none"),
                    use_container_width=True)


def comparison(picks, today_rows, key, money, label):
    now = dt.datetime.now(CENTRAL)
    o, c = HOURS[now.weekday()]
    hrs = list(range(o, c + 1))
    if not picks:
        st.info("Pick one or more stores to compare.")
        return
    pref = "$" if money else ""
    palette = [NAVY, RED, BLUE, GREEN, AMBER]
    fig = go.Figure()
    any_data = False
    for i, s in enumerate(picks):
        pp = to_per_period_metric(cum_by_hour(today_rows.get(s, []), key), key)
        if not pp:
            continue
        any_data = True
        fig.add_trace(go.Bar(
            x=[hour_label(h) for h in hrs], y=[pp.get(h) for h in hrs],
            name=CITY.get(s, s), marker_color=palette[i % len(palette)],
            hovertemplate="%{x}: " + pref + "%{y:,.0f}<extra></extra>"))
    if not any_data:
        st.info("No per-hour data yet today for the selected stores.")
        return
    fig.update_layout(barmode="group")
    fig.update_yaxes(title=("$ per hour" if money else "per hour"), rangemode="tozero")
    st.plotly_chart(_layout(fig, 360, f"{label} per hour - selected stores",
                            legend="bottom", hovermode="x unified"),
                    use_container_width=True)


def export_controls(stats):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Store", "Cars", "Net", "ARO", "Labor/car", "% pace"])
    for s in stats:
        w.writerow([s["name"], s["cars"], s["net"], s["aro"], s.get("lhpc"),
                    f"{s['pct']:.0f}" if s["pct"] is not None else ""])
    today = dt.datetime.now(CENTRAL).strftime("%Y-%m-%d")
    st.download_button("Download today (CSV)", buf.getvalue(),
                       file_name=f"take5_scorecard_{today}.csv", mime="text/csv",
                       use_container_width=True)
    st.caption("Printing now lives on each store view — open a store to print its one-page scorecard.")


# ==========================================================================
# Auth + main
# ==========================================================================
def login_view():
    wordmark("Daily Store Scorecard")
    st.write("")
    _, mid, _ = st.columns([1, 1.3, 1])
    with mid:
        st.markdown(f"<div style='font-weight:700;color:{NAVY};font-size:1.05rem;"
                    f"margin-bottom:4px;text-align:center;'>Enter your access code</div>",
                    unsafe_allow_html=True)
        with st.form("login", clear_on_submit=False):
            pw = st.text_input("Access code", type="password", label_visibility="collapsed",
                               placeholder="Access code")
            ok = st.form_submit_button("Enter", type="primary", use_container_width=True)
        if ok:
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
        st.caption(SUBBRAND)
        if st.button("Refresh data", use_container_width=True):
            st.cache_data.clear()
            st.rerun()
        if st.button("Log out", use_container_width=True):
            del st.session_state.auth
            st.rerun()
        view = None
        if role == "admin":
            view = st.radio("View", ["Executive (all stores)", "Single store"])
            sel = None
            if view == "Single store":
                sel = st.selectbox("Store", STORE_CODES, format_func=lambda s: CITY.get(s, s))
    if role == "store":
        render_store(store, baseline)
    elif view == "Single store":
        render_store(sel, baseline)
    else:
        render_admin(baseline)


if __name__ == "__main__":
    main()
