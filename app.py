"""
Take 5 Store Scorecard — dashboard (proof of concept).

Reads live hourly data from Supabase and benchmarks each store against its
normal DAILY performance (baseline.json, built from the budget workbook).
Shows all key hourly KPIs live. By-hour pacing curve is a later addition.

Login: a store code (e.g. 1512) sees that store; the admin password sees all.
Secrets (Streamlit -> Settings -> Secrets): SUPABASE_URL, SUPABASE_KEY, ADMIN_PASSWORD
"""
import json
import datetime as dt
from zoneinfo import ZoneInfo

import requests
import streamlit as st
import plotly.graph_objects as go

CENTRAL = ZoneInfo("America/Chicago")
STORE_CODES = ["1507", "1512", "1515"]
CITY = {"1507": "Cedar Rapids", "1512": "Jefferson City", "1515": "Columbia"}
HOURS = {0: (7, 20), 1: (7, 20), 2: (7, 20), 3: (7, 20), 4: (7, 20), 5: (7, 18), 6: (9, 17)}
DOW = {0: "Mon", 1: "Tues", 2: "Wed", 3: "Thurs", 4: "Fri", 5: "Sat", 6: "Sun"}

NAVY, GREEN, RED, INK, MUTE = "#1F3A5F", "#1E8E4E", "#C0392B", "#1F2A37", "#5B6B7F"

st.set_page_config(page_title="Take 5 Store Scorecard", layout="wide")
st.markdown(
    "<style>.block-container{padding-top:1.5rem;max-width:1180px;}"
    "#MainMenu,footer{visibility:hidden;}</style>",
    unsafe_allow_html=True,
)


@st.cache_data
def load_baseline():
    with open("baseline.json") as f:
        return json.load(f)


@st.cache_data(ttl=900)
def fetch_today(store):
    url = st.secrets["SUPABASE_URL"].rstrip("/")
    key = st.secrets["SUPABASE_KEY"]
    today = dt.datetime.now(CENTRAL).strftime("%Y-%m-%d")
    endpoint = (url + "/rest/v1/daily_sales_pull?store_number=eq." + store
                + "&pull_hour=like." + today + "*&order=pull_time.asc")
    r = requests.get(endpoint, headers={"apikey": key, "Authorization": "Bearer " + key}, timeout=20)
    r.raise_for_status()
    return r.json()


def frac_elapsed(now):
    o, c = HOURS[now.weekday()]
    return max(0.0, min(1.0, ((now.hour + now.minute / 60) - o) / (c - o)))


def color_for(actual, expected):
    if expected is None:
        return INK
    return GREEN if actual >= expected else RED


def kpi_group(title, rows):
    cells = ""
    for r in rows:
        cells += (
            '<div style="flex:1;padding:10px 16px;border-right:1px solid #EEF1F5;">'
            '<div style="font-size:.7rem;letter-spacing:.05em;color:' + MUTE
            + ';text-transform:uppercase;">' + r["label"] + '</div>'
            '<div style="font-size:1.55rem;font-weight:700;color:' + r.get("color", INK)
            + ';line-height:1.2;">' + r["value"] + '</div>'
            '<div style="font-size:.74rem;color:' + MUTE + ';">' + r.get("sub", "&nbsp;") + '</div></div>'
        )
    return (
        '<div style="border:1px solid #E3E8EF;border-radius:8px;overflow:hidden;margin-bottom:14px;">'
        '<div style="background:' + NAVY + ';color:#fff;font-weight:700;font-size:.78rem;'
        'letter-spacing:.06em;padding:8px 16px;text-transform:uppercase;">' + title + '</div>'
        '<div style="display:flex;background:#fff;">' + cells + '</div></div>'
    )


def store_display(store, latest=None):
    """Friendly store name for display — never the bare store number."""
    return CITY.get(store) or (latest or {}).get("store_name") or "Your store"


def header_bar(name, updated):
    st.markdown(
        '<div style="background:' + NAVY + ';color:#fff;padding:14px 22px;border-radius:8px;'
        'display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">'
        '<div style="font-size:1.25rem;font-weight:700;letter-spacing:.05em;">'
        'TAKE 5 &mdash; DAILY STORE SCORECARD</div>'
        '<div style="text-align:right;font-size:.82rem;opacity:.9;">' + name
        + '<br>Last updated ' + str(updated) + '</div></div>',
        unsafe_allow_html=True,
    )


def gauge(value, target, title, maxv):
    fig = go.Figure(go.Indicator(
        mode="gauge+number", value=value,
        title={"text": title, "font": {"size": 14, "color": INK}},
        number={"font": {"color": INK}},
        gauge={"axis": {"range": [0, maxv]}, "bar": {"color": NAVY},
               "threshold": {"line": {"color": RED, "width": 3}, "value": target}}))
    fig.update_layout(height=220, margin=dict(l=20, r=20, t=45, b=10),
                      paper_bgcolor="white", font_color=INK)
    return fig


def bell(values, marker, marker_label, title):
    mean = sum(values) / len(values)
    fig = go.Figure(go.Histogram(x=values, nbinsx=18, marker_color="#BCD3EA", opacity=0.9))
    fig.add_vline(x=mean, line_color=NAVY, line_width=2,
                  annotation_text="Normal avg " + format(mean, ",.0f"), annotation_position="top")
    if marker is not None:
        fig.add_vline(x=marker, line_color=RED, line_dash="dash", line_width=3,
                      annotation_text=marker_label, annotation_position="top left")
    fig.update_layout(title={"text": title, "font": {"color": INK}}, height=290, bargap=0.05,
                      margin=dict(l=10, r=10, t=40, b=10), showlegend=False,
                      paper_bgcolor="white", plot_bgcolor="white", font_color=INK,
                      yaxis_title="How often (weeks/yr)")
    return fig


def render_store(store, baseline):
    now = dt.datetime.now(CENTRAL)
    day = DOW[now.weekday()]
    rows = fetch_today(store)
    b = baseline.get(store, {})
    cars_base = b.get("cars", {}).get(day)
    sales_base = b.get("net_sales", {}).get(day)

    if not rows:
        header_bar(store_display(store), "—")
        st.info("No data pulled yet today. This fills in on the first hourly run after opening.")
        return

    latest = rows[-1]
    updated = latest.get("report_timestamp", "—")
    cars = latest.get("cars") or 0
    net = latest.get("net_sales") or 0
    aro = round(net / cars, 2) if cars else 0
    frac = frac_elapsed(now)

    cars_target = cars_base["mean"] if cars_base else None
    sales_target = sales_base["mean"] if sales_base else None
    aro_target = round(sales_target / cars_target, 2) if (cars_target and sales_target) else None
    cars_by_now = cars_target * frac if cars_target else None
    sales_by_now = sales_target * frac if sales_target else None

    header_bar(store_display(store, latest), updated)
    st.markdown(
        '<div style="color:' + MUTE + ';font-size:.9rem;margin-bottom:6px;">'
        + now.strftime("%A, %b %d") + ' &middot; comparing today vs a normal '
        + now.strftime("%A") + ' &middot; ' + format(frac * 100, ".0f") + '% through the day</div>',
        unsafe_allow_html=True,
    )

    if cars_target:
        diff = cars - cars_by_now
        if diff >= 1:
            verdict, vcolor = "Ahead of pace — keep full staffing on.", GREEN
        elif diff <= -1:
            verdict, vcolor = "Behind pace — you may be over-staffed for this pace.", RED
        else:
            verdict, vcolor = "Right on the normal pace.", NAVY
        st.markdown(
            '<div style="border-left:5px solid ' + vcolor + ';background:#F5F7FA;padding:10px 16px;'
            'border-radius:4px;margin-bottom:16px;color:' + INK + ';"><b>Bottom line —</b> '
            + str(cars) + ' cars and $' + format(net, ",.0f") + ' so far. A normal ' + day
            + ' runs ~' + format(cars_target, ".0f") + ' cars / $' + format(sales_target, ",.0f")
            + '. <b style="color:' + vcolor + ';">' + verdict + '</b></div>',
            unsafe_allow_html=True,
        )

    st.markdown(kpi_group("Pace today", [
        {"label": "Cars so far", "value": str(cars), "color": color_for(cars, cars_by_now),
         "sub": ("~" + format(cars_by_now, ".0f") + " expected by now") if cars_by_now else "&nbsp;"},
        {"label": "Expected full day", "value": (format(cars_target, ".0f") if cars_target else "—"),
         "sub": "normal " + day},
        {"label": "% of normal day",
         "value": (format(cars / cars_target * 100, ".0f") + "%") if cars_target else "—",
         "sub": "cars vs normal total", "color": color_for(cars, cars_by_now)},
    ]), unsafe_allow_html=True)

    st.markdown(kpi_group("Sales", [
        {"label": "Net sales so far", "value": "$" + format(net, ",.0f"),
         "color": color_for(net, sales_by_now),
         "sub": ("~$" + format(sales_by_now, ",.0f") + " expected by now") if sales_by_now else "&nbsp;"},
        {"label": "Avg per car (ARO)", "value": "$" + format(aro, ",.2f"),
         "color": color_for(aro, aro_target),
         "sub": ("normal $" + format(aro_target, ",.2f")) if aro_target else "&nbsp;"},
        {"label": "Expected full day", "value": ("$" + format(sales_target, ",.0f")) if sales_target else "—",
         "sub": "normal " + day},
    ]), unsafe_allow_html=True)

    st.markdown(kpi_group("Big 4 & ancillary", [
        {"label": "Big 4 units", "value": str(latest.get("big4_total_units", 0)),
         "sub": "$" + format(latest.get("big4_total_amount") or 0, ",.0f") + " in sales"},
        {"label": "ASA (ancillary avg)", "value": "$" + format(latest.get("asa") or 0, ",.2f"),
         "sub": "per car"},
        {"label": "Materials %", "value": format(latest.get("materials_pct") or 0, ".0f") + "%",
         "sub": "of sales"},
    ]), unsafe_allow_html=True)

    nc, rc = latest.get("new_customers") or 0, latest.get("repeat_customers") or 0
    st.markdown(kpi_group("Customers & discounts", [
        {"label": "New / Repeat", "value": str(nc) + " / " + str(rc), "sub": "customers today"},
        {"label": "Coupons", "value": "$" + format(latest.get("coupons") or 0, ",.0f"), "sub": "&nbsp;"},
        {"label": "Discounts", "value": "$" + format(latest.get("discounts") or 0, ",.0f"), "sub": "&nbsp;"},
        {"label": "Total receipts", "value": "$" + format(latest.get("total_receipts") or 0, ",.0f"),
         "sub": "&nbsp;"},
    ]), unsafe_allow_html=True)

    # Labor + fleet live inside the `data` jsonb payload, not as top-level
    # Supabase columns — read them from there (with a top-level fallback).
    payload = latest.get("data") or {}
    lab = payload.get("labor") or latest.get("labor") or {}
    fleets_count = payload.get("fleets_count", latest.get("fleets_count")) or 0
    fleets_amount = payload.get("fleets_amount", latest.get("fleets_amount")) or 0
    st.markdown(kpi_group("Labor & efficiency", [
        {"label": "Hours per car", "value": format(lab.get("hours_per_car") or 0, ".2f"),
         "sub": "labor time per car"},
        {"label": "Labor hours", "value": format(lab.get("hours") or 0, ".1f"), "sub": "total today"},
        {"label": "Labor % of net", "value": format(lab.get("pct_of_net") or 0, ".1f") + "%",
         "sub": "of net sales"},
        {"label": "Fleet", "value": str(fleets_count) + " / $"
         + format(fleets_amount, ",.0f"), "sub": "count / sales"},
    ]), unsafe_allow_html=True)

    big4 = latest.get("big4") or {}
    if big4:
        names = list(big4.keys())
        attach = [big4[n].get("attach_pct") or 0 for n in names]
        fig = go.Figure(go.Bar(x=names, y=attach, marker_color=NAVY,
                               text=[format(a, ".0f") + "%" for a in attach], textposition="outside"))
        fig.update_layout(title={"text": "Big 4 attachment (% of cars)", "font": {"color": INK}},
                          height=260, margin=dict(l=10, r=10, t=40, b=10),
                          paper_bgcolor="white", plot_bgcolor="white", font_color=INK,
                          yaxis_title="% of cars")
        st.plotly_chart(fig, use_container_width=True)

    items = sorted(latest.get("line_items") or [], key=lambda x: x.get("amount") or 0, reverse=True)
    if items:
        names = [i["description"] for i in items]
        amts = [i.get("amount") or 0 for i in items]
        figr = go.Figure(go.Bar(x=amts, y=names, orientation="h", marker_color="#2E75B6",
                                text=["$" + format(a, ",.0f") for a in amts], textposition="outside"))
        figr.update_layout(title={"text": "Revenue by product line (today)", "font": {"color": INK}},
                           height=max(260, 26 * len(items)), margin=dict(l=10, r=10, t=40, b=10),
                           paper_bgcolor="white", plot_bgcolor="white", font_color=INK,
                           yaxis=dict(autorange="reversed"), xaxis_title="$ today")
        st.plotly_chart(figr, use_container_width=True)

    st.markdown("##### How today compares to a normal day")
    g1, g2 = st.columns(2)
    if cars_target:
        g1.plotly_chart(gauge(cars, cars_target, "Cars vs normal day", max(cars_base["values"]) * 1.1),
                        use_container_width=True)
        g1.plotly_chart(bell(cars_base["values"], cars, "today: " + str(cars), "Normal daily cars"),
                        use_container_width=True)
    if sales_target:
        g2.plotly_chart(gauge(net, sales_target, "Net sales vs normal day", max(sales_base["values"]) * 1.1),
                        use_container_width=True)
        g2.plotly_chart(bell(sales_base["values"], net, "today: $" + format(net, ",.0f"),
                             "Normal daily net sales"), use_container_width=True)

    st.caption("Benchmarks compare to this store's normal FULL day. The true hour-by-hour pacing "
               "curve will be added once a few weeks of hourly data accumulate.")


def login_view():
    st.markdown(
        '<div style="background:' + NAVY + ';color:#fff;padding:16px 22px;border-radius:8px;'
        'font-size:1.3rem;font-weight:700;letter-spacing:.05em;margin-bottom:16px;">'
        'TAKE 5 &mdash; DAILY STORE SCORECARD</div>', unsafe_allow_html=True)
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
        st.markdown("**Take 5 Scorecard**")
        if st.button("Log out"):
            del st.session_state.auth
            st.rerun()
        if st.button("Refresh data"):
            st.cache_data.clear()
            st.rerun()
    if role == "store":
        render_store(store, baseline)
    else:
        sel = st.sidebar.selectbox("Store", STORE_CODES,
                                   format_func=lambda s: CITY.get(s, s))
        render_store(sel, baseline)


main()
