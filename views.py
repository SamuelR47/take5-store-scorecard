"""Streamlit orchestration: the single-store page and the admin (all-stores) page.
All look/logic lives in style/charts/calc - this module only wires them together."""
import datetime as dt
import streamlit as st
import streamlit.components.v1 as components

import calc, style, charts
from config import (CENTRAL, HOURS, DOW, STORE_CODES, CITY, STALE_HOURS,
                    METRICS, SECTION_ORDER, RATE_KEYS,
                    NAVY, BLUE, GREEN, RED, MUTE, LINE, LIGHT, INK, STEEL, CODE, DIAL_ACT)
from datasource import fetch_today, fetch_history, fetch_range

MIX_COLORS = ["#2E6FB7", "#4A98C9", "#157F6B", "#7FB2DC", "#C79A3A", "#9FB4CC"]
# Set once the backtest lands; shown as the out-of-the-way footnote.
ACCURACY_NOTE = ("Norms are the recency-weighted average of the last 4 same-weekday hours "
                 "(holiday-clean). Target = norm +10%. Projection &amp; pace are measured "
                 "against the true norm, not the target.")


def store_name(store, latest=None):
    return CITY.get(store) or (latest or {}).get("store_name") or "Your store"


def _freshness(latest, now):
    ts = latest.get("report_timestamp") or "&mdash;"
    color, age = GREEN, ""
    try:
        pt = dt.datetime.fromisoformat(latest.get("pull_time")).astimezone(CENTRAL)
        hrs = (now - pt).total_seconds() / 3600
        o, c = HOURS[now.weekday()]
        if o <= now.hour < c and hrs > STALE_HOURS:
            color, age = "#E6A200", f" &nbsp;&#9888; last pull {hrs:.1f}h ago"
    except (TypeError, ValueError):
        pass
    st.markdown(style.freshness(ts, color, age), unsafe_allow_html=True)


def _sowhat(name, cars_m):
    p = cars_m["pace"]
    so, proj, norm = cars_m["so_far"], cars_m["proj_close"], cars_m["norm_close"]
    if p is None or not norm:
        st.markdown(style.sowhat("#EEF3FA", "#CFE0F1", "&#9670;",
                    f"<b>{name}:</b> tracking today's pace &mdash; the normal curve fills in as history builds."),
                    unsafe_allow_html=True)
        return
    gap = round(proj - norm, 1)
    if p >= 1.03:
        st.markdown(style.sowhat("#ECF6EF", "#C4E4CF", "&#9650;",
            f"<b>{name} is running ahead of a normal {DOW.get(dt.datetime.now(CENTRAL).weekday(),'day')}.</b> "
            f"{so:,.0f} cars so far ({p:.2f}&times; pace), on track for ~{proj:,.0f} by close "
            f"&mdash; <b>+{gap}</b> vs normal. Keep the bays flowing."), unsafe_allow_html=True)
    elif p >= 0.97:
        st.markdown(style.sowhat("#EEF3FA", "#CFE0F1", "&#9670;",
            f"<b>{name} is right on a normal day.</b> {so:,.0f} cars so far ({p:.2f}&times; pace), "
            f"tracking to ~{proj:,.0f} by close ({'+' if gap>=0 else ''}{gap} vs normal). "
            f"A strong afternoon pushes it past target."), unsafe_allow_html=True)
    else:
        st.markdown(style.sowhat("#FBF1EC", "#EFD3C4", "&#9679;",
            f"<b>{name} is a step behind a normal day, but it's winnable.</b> {so:,.0f} cars so far "
            f"({p:.2f}&times; pace), projecting ~{proj:,.0f} ({gap} vs normal). "
            f"The afternoon block is where it gets made up."), unsafe_allow_html=True)


def _section_note(key):
    return {"cars": "cars per hour vs normal & target, plus the pace dial",
            "aro": "revenue per car through the day",
            "net_sales": "revenue per hour vs normal & target, plus the pace dial",
            "big4_total_units": "attachment units per hour, plus the pace dial",
            "labor_hours": "labor hours per hour, plus the pace dial"}.get(key, "")


def _render_section(key, m):
    meta = METRICS[key]
    money, dp, title = meta["money"], meta["dp"], meta["label"]
    sample = not m["norm"]
    chips = style.metric_chips(m, money, dp, sample=sample)
    st.markdown(style.section_header(title, _section_note(key), chips), unsafe_allow_html=True)
    c1, c2 = st.columns([1.3, 1])
    with c1:
        st.plotly_chart(charts.bar_figure(m, money, title), use_container_width=True,
                        config={"displayModeBar": False})
        if sample:
            st.caption("Normal & Target build as same-weekday hourly history accumulates.")
    with c2:
        components.html(charts.dial_svg(m, money, title, dp), height=300)


def render_store(store, baseline):
    now = dt.datetime.now(CENTRAL)
    weekday = now.weekday()
    day = DOW[weekday]
    o, c = HOURS[weekday]
    hours = list(range(o, c + 1))
    rows = fetch_today(store)
    hist = fetch_history(store)
    code = f'<span style="color:{CODE};">({store})</span>'

    if not rows:
        st.markdown(style.header(f"{store_name(store)} {code} &middot; {now:%A, %b %-d}"),
                    unsafe_allow_html=True)
        st.info("No data pulled yet today. This fills in on the first pull after the store opens.")
        return

    latest = rows[-1]
    frac = calc.frac_elapsed(now)
    b = baseline.get(store, {})
    cars_norm_day = (b.get("cars", {}).get(day) or {}).get("mean")
    net_norm_day = (b.get("net_sales", {}).get(day) or {}).get("mean")

    daily_norm = {"cars": cars_norm_day, "net_sales": net_norm_day}
    metrics = {k: calc.build_metric(k, rows, hist, hours, weekday, daily_norm.get(k))
               for k in SECTION_ORDER}

    st.markdown(style.header(
        f"{store_name(store, latest)} {code} &middot; {now:%A, %b %-d} &middot; "
        f"{frac*100:.0f}% through the day"), unsafe_allow_html=True)
    _freshness(latest, now)
    _sowhat(store_name(store, latest), metrics["cars"])

    # headline KPI strip
    cards = []
    for k in SECTION_ORDER:
        m = metrics[k]; meta = METRICS[k]
        has = m["pace"] is not None
        behind = has and m["pace"] < 1
        sub = (f'{m["pace"]:.2f}&times; {"behind" if behind else "ahead"}' if has else "building")
        col = (RED if behind else GREEN) if has else MUTE
        top = (RED if behind else GREEN) if has else NAVY
        cards.append((meta["label"], style.fmt(m["so_far"], meta["money"], meta["dp"]),
                      sub, col, top, not m["norm"]))
    ahead = sum(1 for k in SECTION_ORDER if (metrics[k]["pace"] or 0) >= 1)
    tot = sum(1 for k in SECTION_ORDER if metrics[k]["pace"] is not None)
    cards.append(("On pace", f"{ahead}/{tot}", "metrics ahead", MUTE,
                  GREEN if ahead >= tot - ahead else RED, False))
    st.markdown(style.kpi_strip(cards), unsafe_allow_html=True)

    st.markdown(
        f'<div class="vea-noprint" style="text-align:right;margin:-4px 0 6px;">'
        f'<button onclick="window.print()" style="padding:7px 16px;border:1px solid {LINE};'
        f'border-radius:8px;background:#fff;color:{NAVY};font-weight:700;cursor:pointer;">'
        f'&#128424;&#65039; Download score card</button></div>', unsafe_allow_html=True)

    for k in SECTION_ORDER:
        _render_section(k, metrics[k])

    # ---- product mix ----
    st.markdown(style.section_header("Product mix", "share of today's dollars &amp; Big 4 attachment", ""),
                unsafe_allow_html=True)
    items = latest.get("line_items") or []
    big4 = latest.get("big4") or {}
    mc1, mc2 = st.columns(2)
    with mc1:
        if items:
            total = sum((i.get("amount") or 0) for i in items) or 1
            rows_i = sorted([(i.get("description", "?").title(), i.get("amount") or 0)
                             for i in items if (i.get("amount") or 0) > 0],
                            key=lambda t: t[1], reverse=True)
            keep, other = [], 0.0
            for nme, amt in rows_i:
                (keep.append((nme, amt, round(amt / total * 100)))
                 if amt / total >= 0.03 else None)
                if amt / total < 0.03:
                    other += amt
            if other:
                keep.append(("Other", other, round(other / total * 100)))
            st.markdown(style.product_mix_stack(keep, MIX_COLORS), unsafe_allow_html=True)
        else:
            st.caption("Product detail builds as the day's tickets come in.")
    with mc2:
        if big4:
            order = ["Air Filter", "Wiper Blade", "Cabin Filter", "Coolant Exchange"]
            names = [n for n in order if n in big4] or list(big4.keys())
            b4 = [{"name": n, "units": (big4.get(n) or {}).get("units") or 0,
                   "amt": (big4.get(n) or {}).get("amount") or 0,
                   "attach": (big4.get(n) or {}).get("attach_pct") or 0} for n in names]
            st.markdown(style.big4_bars(b4), unsafe_allow_html=True)
        else:
            st.caption("Big 4 attachment builds through the day.")

    # ---- operational detail ----
    st.markdown(style.section_header("Operational detail", "the numbers behind the day", ""),
                unsafe_allow_html=True)
    lab = calc.labor_block(latest)
    st.markdown(style.ops_tiles([
        ("Materials %", f"{latest.get('materials_pct') or 0:.0f}%", "of net sales"),
        ("ASA", style.fmt(latest.get("asa"), True, 2), "avg service age"),
        ("Coupons", style.fmt(latest.get("coupons"), True), "redeemed today"),
        ("Discounts", style.fmt(latest.get("discounts"), True), "applied today"),
        ("New / Repeat", f"{latest.get('new_customers') or 0} / {latest.get('repeat_customers') or 0}", "customer split"),
        ("Gross sales", style.fmt(latest.get("gross_sales"), True), "before discounts"),
        ("Labor hours", style.fmt(lab.get("hours"), dp=1), "clocked today"),
        ("Labor hrs/car", style.fmt(lab.get("hours_per_car"), dp=2), "efficiency"),
    ]), unsafe_allow_html=True)

    st.markdown(style.note(ACCURACY_NOTE), unsafe_allow_html=True)


# ==========================================================================
# Admin (all stores)
# ==========================================================================
def _store_stats(baseline, period_days=0):
    now = dt.datetime.now(CENTRAL)
    weekday = now.weekday()
    day = DOW[weekday]
    o, c = HOURS[weekday]
    hours = list(range(o, c + 1))
    frac = calc.frac_elapsed(now)
    stats, today_rows, hist_rows = [], {}, {}
    for s in STORE_CODES:
        rows = fetch_range(s, period_days) if period_days else fetch_today(s)
        today_rows[s] = rows
        hist_rows[s] = fetch_history(s)
        if not rows:
            stats.append({"store": s, "name": store_name(s), "cars": None, "net": None,
                          "aro": None, "lhpc": None, "pct": None})
            continue
        latest = rows[-1]
        cars = sum(calc.to_per_period(calc.cum_by_hour([r], "cars")).get(calc.row_hour(r) or 0, 0)
                   for r in rows) if period_days else (latest.get("cars") or 0)
        # for today: cumulative latest; for week: sum of daily finals
        if period_days:
            by_day = {}
            for r in rows:
                by_day.setdefault(calc.row_date(r), []).append(r)
            cars = sum((calc.cum_by_hour(v, "cars") or {0: 0})[max(calc.cum_by_hour(v, "cars"))]
                       for v in by_day.values() if calc.cum_by_hour(v, "cars"))
            net = sum((calc.cum_by_hour(v, "net_sales") or {0: 0})[max(calc.cum_by_hour(v, "net_sales"))]
                      for v in by_day.values() if calc.cum_by_hour(v, "net_sales"))
        else:
            cars = latest.get("cars") or 0
            net = latest.get("net_sales") or 0
        base_h = calc.hour_baselines(hist_rows[s], weekday, "cars")
        completed = sorted(calc.to_per_period(calc.cum_by_hour(rows, "cars")))
        if base_h and completed and not period_days:
            exp = sum(base_h.get(h, 0) for h in completed)
        else:
            cb = (baseline.get(s, {}).get("cars", {}).get(day) or {}).get("mean")
            exp = (cb * frac) if (cb and not period_days) else (cb * 7 if (cb and period_days) else None)
        stats.append({"store": s, "name": store_name(s, latest), "cars": cars, "net": net,
                      "aro": (net / cars) if cars else 0,
                      "lhpc": calc.get_metric(latest, "lhpc"),
                      "pct": (cars / exp * 100) if exp else None})
    return stats, today_rows, hist_rows


def render_admin(baseline):
    now = dt.datetime.now(CENTRAL)
    st.markdown(style.header(f"All Stores &middot; {now:%A, %b %-d} &middot; "
                f"{calc.frac_elapsed(now)*100:.0f}% through the day"), unsafe_allow_html=True)
    period = st.radio("Period", ["Today", "Week to date"], horizontal=True, key="adm_period")
    days = 7 if period == "Week to date" else 0
    stats, today_rows, hist_rows = _store_stats(baseline, days)
    live = [s for s in stats if s["cars"] is not None]

    tot_cars = sum(s["cars"] for s in live)
    tot_net = sum(s["net"] for s in live)
    avg_aro = (tot_net / tot_cars) if tot_cars else 0
    ahead = sum(1 for s in live if (s["pct"] or 0) >= 100)
    cards = [
        ("Stores reporting", f"{len(live)}/{len(stats)}", "", MUTE, NAVY, False),
        ("Total cars", f"{tot_cars:,.0f}", "", MUTE, NAVY, False),
        ("Total net", f"${tot_net:,.0f}", "", MUTE, NAVY, False),
        ("Avg ARO", f"${avg_aro:,.2f}", "", MUTE, NAVY, False),
        ("Ahead / behind", f"{ahead} / {len(live)-ahead}" if live else "&mdash;", "vs pace",
         GREEN if ahead >= len(live) - ahead else RED, GREEN if ahead >= len(live)-ahead else RED, False),
    ]
    st.markdown(style.kpi_strip(cards), unsafe_allow_html=True)

    # ---- ranking (rolling rail: every store listed, id in grey) ----
    st.markdown(style.section_header("Store ranking", "cars vs pace &mdash; leaders to laggards", ""),
                unsafe_allow_html=True)
    ranked = calc.rank_stores(stats)
    trows = ""
    for i, s in enumerate(ranked, 1):
        pct = s["pct"]
        col = (GREEN if pct >= 100 else "#E6A200" if pct >= 90 else RED) if pct is not None else MUTE
        pcttxt = f"{pct:.0f}%" if pct is not None else "no data"
        trows += (
            f'<tr style="border-bottom:1px solid {LINE};">'
            f'<td style="padding:8px 12px;color:{MUTE};">{i}</td>'
            f'<td style="padding:8px 12px;font-weight:700;color:{INK};">{s["name"]} '
            f'<span style="color:{CODE};font-weight:500;">({s["store"]})</span></td>'
            f'<td style="padding:8px 12px;text-align:right;">{style.fmt(s["cars"])}</td>'
            f'<td style="padding:8px 12px;text-align:right;">{style.fmt(s["net"], True)}</td>'
            f'<td style="padding:8px 12px;text-align:right;">{style.fmt(s["aro"], True, 2)}</td>'
            f'<td style="padding:8px 12px;text-align:right;">{style.fmt(s.get("lhpc"), dp=2)}</td>'
            f'<td style="padding:8px 12px;text-align:right;font-weight:800;color:{col};">{pcttxt}</td></tr>')
    st.markdown(
        f'<table style="width:100%;border-collapse:collapse;background:#fff;border:1px solid {LINE};'
        f'border-radius:10px;overflow:hidden;">'
        f'<tr style="background:{NAVY};color:#fff;font-size:.72rem;text-transform:uppercase;letter-spacing:.04em;">'
        f'<th style="padding:9px 12px;text-align:left;">#</th><th style="padding:9px 12px;text-align:left;">Store</th>'
        f'<th style="padding:9px 12px;text-align:right;">Cars</th><th style="padding:9px 12px;text-align:right;">Net</th>'
        f'<th style="padding:9px 12px;text-align:right;">ARO</th><th style="padding:9px 12px;text-align:right;">Labor/car</th>'
        f'<th style="padding:9px 12px;text-align:right;">% pace</th></tr>{trows}</table>', unsafe_allow_html=True)

    # ---- drill-down ----
    st.markdown(style.section_header("Store drill-down", "the exact view a manager sees", ""),
                unsafe_allow_html=True)
    sel = st.selectbox("Store", STORE_CODES, format_func=lambda s: f"{CITY.get(s, s)} ({s})", key="adm_drill")
    with st.expander(f"Open {CITY.get(sel, sel)} scorecard", expanded=False):
        render_store(sel, baseline)
