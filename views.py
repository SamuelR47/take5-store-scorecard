"""Streamlit orchestration: single-store page + admin (all-stores) page.
Look/logic live in style/charts/calc/scorecard_pdf - this only wires them."""
import datetime as dt
import streamlit as st
import streamlit.components.v1 as components
import plotly.graph_objects as go

import calc, style, charts, scorecard_pdf
from config import (CENTRAL, HOURS, DOW, STORE_CODES, CITY, STALE_HOURS, METRICS,
                    SECTION_ORDER, RATE_KEYS, HEAT_SCALE,
                    NAVY, BLUE, GREEN, RED, AMBER, MUTE, LINE, LIGHT, INK, STEEL, CODE)
from datasource import fetch_today, fetch_history

MIX_COLORS = ["#2E6FB7", "#4A98C9", "#0E86A3", "#7FB2DC", "#C79A3A", "#9FB4CC"]
ACCURACY_NOTE = ("Normal = recency-weighted average of the last 4 same-weekday hours "
                 "(holiday-clean). Pace and projection are measured against the normal "
                 "for this time of day.")
ADMIN_TARGET_NOTE = ("Admin note: the Target shown to stores = normal +10% (a stretch goal). "
                     "Pace and projections always use the true normal, not the target.")
RGB = {"green": (30, 142, 78), "red": (228, 0, 43), "navy": (20, 39, 63)}


def store_name(store, latest=None):
    return CITY.get(store) or (latest or {}).get("store_name") or "Your store"


def _plot(fig, height, title=None, legend="none"):
    lg = dict(orientation="h", yanchor="top", y=-0.16, x=0, font=dict(size=11)) if legend == "bottom" else None
    fig.update_layout(height=height, margin=dict(l=10, r=10, t=40 if title else 12,
                      b=54 if legend == "bottom" else 14), paper_bgcolor="white",
                      plot_bgcolor="white", font_color=INK, font_size=12,
                      showlegend=(legend != "none"), legend=lg,
                      title=dict(text=title, font=dict(color=NAVY, size=14), x=0.01) if title else None)
    fig.update_xaxes(gridcolor=LINE, zeroline=False)
    fig.update_yaxes(gridcolor=LINE, zeroline=False)
    return fig


def _freshness(latest, now):
    ts = latest.get("report_timestamp") or "&mdash;"
    color, age = GREEN, ""
    try:
        pt = dt.datetime.fromisoformat(latest.get("pull_time")).astimezone(CENTRAL)
        hrs = (now - pt).total_seconds() / 3600
        o, c = HOURS[now.weekday()]
        if o <= now.hour < c and hrs > STALE_HOURS:
            color, age = AMBER, f" &nbsp;&#9888; last pull {hrs:.1f}h ago"
    except (TypeError, ValueError):
        pass
    st.markdown(style.freshness(ts, color, age), unsafe_allow_html=True)


def _sowhat_parts(name, cars_m):
    """Returns (bg, border, icon, html_msg, plain_headline)."""
    p = cars_m["pace"]
    so, proj, norm = cars_m["so_far"], cars_m["proj_close"], cars_m["norm_close"]
    dayname = DOW.get(dt.datetime.now(CENTRAL).weekday(), "day")
    if p is None or not norm:
        return ("#EEF3FA", "#CFE0F1", "&#9670;",
                f"<b>{name}:</b> tracking today's pace &mdash; the normal curve fills in as history builds.",
                f"{name}: tracking today's pace.")
    gap = round(proj - norm, 1)
    if p >= 1.03:
        return ("#ECF6EF", "#C4E4CF", "&#9650;",
                f"<b>{name} is running ahead of a normal {dayname}.</b> {so:,.0f} cars so far "
                f"({p:.2f}&times; pace), on track for ~{proj:,.0f} by close &mdash; <b>+{gap}</b> vs normal. "
                f"Keep the bays flowing.",
                f"Running ahead of a normal {dayname}: {so:,.0f} cars, on track for ~{proj:,.0f} (+{gap} vs normal).")
    if p >= 0.97:
        return ("#EEF3FA", "#CFE0F1", "&#9670;",
                f"<b>{name} is right on a normal {dayname}.</b> {so:,.0f} cars so far ({p:.2f}&times; pace), "
                f"tracking to ~{proj:,.0f} by close ({'+' if gap>=0 else ''}{gap} vs normal). "
                f"A strong afternoon pushes it past target.",
                f"Right on a normal {dayname}: {so:,.0f} cars, tracking to ~{proj:,.0f} ({'+' if gap>=0 else ''}{gap} vs normal).")
    return ("#FBF1EC", "#EFD3C4", "&#9679;",
            f"<b>{name} is a step behind a normal {dayname}, but it's winnable.</b> {so:,.0f} cars so far "
            f"({p:.2f}&times; pace), projecting ~{proj:,.0f} ({gap} vs normal). "
            f"The afternoon block is where it gets made up.",
            f"A step behind a normal {dayname}: {so:,.0f} cars, projecting ~{proj:,.0f} ({gap} vs normal).")


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
    st.markdown(style.section_header(title, _section_note(key),
                style.metric_chips(m, money, dp, sample=sample)), unsafe_allow_html=True)
    c1, c2 = st.columns([1.3, 1])
    with c1:
        st.plotly_chart(charts.bar_figure(m, money, title), use_container_width=True,
                        config={"displayModeBar": False})
        st.markdown(style.bar_legend(rate=m["is_rate"]), unsafe_allow_html=True)
        if sample:
            st.caption("Normal & Target build as same-weekday hourly history accumulates.")
    with c2:
        components.html(charts.dial_svg(m, money, title, dp), height=290)
        st.markdown(style.dial_legend(), unsafe_allow_html=True)


def _pace_rgb(m):
    if m["pace"] is None:
        return RGB["navy"]
    return RGB["green"] if m["pace"] >= 1 else RGB["red"]


def render_store(store, baseline):
    now = dt.datetime.now(CENTRAL)
    weekday = now.weekday(); day = DOW[weekday]
    o, c = HOURS[weekday]; hours = list(range(o, c + 1))
    rows = fetch_today(store); hist = fetch_history(store)
    code = f'<span style="color:{CODE};">({store})</span>'

    if not rows:
        st.markdown(style.header(f"{store_name(store)} {code} &middot; {now:%A, %b %-d}"),
                    unsafe_allow_html=True)
        st.info("No data pulled yet today. This fills in on the first pull after the store opens.")
        return

    latest = rows[-1]
    frac = calc.frac_elapsed(now)
    b = baseline.get(store, {})
    daily_norm = {"cars": (b.get("cars", {}).get(day) or {}).get("mean"),
                  "net_sales": (b.get("net_sales", {}).get(day) or {}).get("mean")}
    metrics = {k: calc.build_metric(k, rows, hist, hours, weekday, daily_norm.get(k),
                                    now_hour=now.hour)
               for k in SECTION_ORDER}

    st.markdown(style.header(
        f"{store_name(store, latest)} {code} &middot; {now:%A, %b %-d} &middot; "
        f"{frac*100:.0f}% through the day"), unsafe_allow_html=True)
    _freshness(latest, now)
    bg, bd, ic, msg, headline = _sowhat_parts(store_name(store, latest), metrics["cars"])
    st.markdown(style.sowhat(bg, bd, ic, msg), unsafe_allow_html=True)

    # headline KPI strip
    cards = []
    for k in SECTION_ORDER:
        m = metrics[k]; meta = METRICS[k]
        has = m["pace"] is not None; behind = has and m["pace"] < 1
        sub = (f'{m["pace"]:.2f}&times; {"behind" if behind else "ahead"}' if has else "building")
        col = (RED if behind else GREEN) if has else MUTE
        cards.append((meta["label"], style.fmt(m["so_far"], meta["money"], meta["dp"]),
                      sub, col, (RED if behind else GREEN) if has else NAVY, not m["norm"]))
    ahead = sum(1 for k in SECTION_ORDER if (metrics[k]["pace"] or 0) >= 1)
    tot = sum(1 for k in SECTION_ORDER if metrics[k]["pace"] is not None)
    cards.append(("On pace", f"{ahead}/{tot}", "metrics ahead", MUTE,
                  GREEN if ahead >= tot - ahead else RED, False))
    st.markdown(style.kpi_strip(cards), unsafe_allow_html=True)

    # ---- Download score card (real PDF, KPI only) ----
    pdf_cards = []
    for k in SECTION_ORDER:
        m = metrics[k]; meta = METRICS[k]
        has = m["pace"] is not None
        sub = (f'{m["pace"]:.2f}x {"ahead" if (has and m["pace"]>=1) else "behind"}' if has else "building")
        pdf_cards.append((meta["label"], style.fmt(m["so_far"], meta["money"], meta["dp"])
                          .replace("&mdash;", "-"), sub, _pace_rgb(m)))
    pdf_bytes = scorecard_pdf.build_scorecard_pdf(
        store_name(store, latest), store, now.strftime("%A, %b %-d %Y"), headline, pdf_cards)
    lc, rc = st.columns([3, 1])
    with rc:
        st.download_button("⬇ Score card (PDF)", pdf_bytes,
                           file_name=f"scorecard_{store}_{now:%Y-%m-%d}.pdf",
                           mime="application/pdf", use_container_width=True)

    for i, k in enumerate(SECTION_ORDER):
        _render_section(k, metrics[k])
        if i < len(SECTION_ORDER) - 1:
            st.markdown(style.divider(), unsafe_allow_html=True)

    # ---- product mix ----
    st.markdown(style.section_header("Product mix", "share of today's dollars &amp; Big 4 attachment", ""),
                unsafe_allow_html=True)
    items = latest.get("line_items") or []; big4 = latest.get("big4") or {}
    mc1, mc2 = st.columns(2)
    with mc1:
        st.markdown('<div style="font-size:.92rem;font-weight:700;color:#14273F;margin:0 0 2px;">'
                    "Today's dollars by product</div>", unsafe_allow_html=True)
        fig = charts.mix_figure(items)
        if fig:
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
        else:
            st.caption("Product detail builds as the day's tickets come in.")
    with mc2:
        st.markdown('<div style="font-size:.92rem;font-weight:700;color:#14273F;margin:0 0 2px;">'
                    "Big 4/5 attachment</div>", unsafe_allow_html=True)
        fig = charts.big4_figure(big4)
        if fig:
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
        else:
            st.caption("Big 4 attachment builds through the day.")

    # ---- operational detail ----
    st.markdown(style.divider(), unsafe_allow_html=True)
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
def _admin_stats(baseline):
    now = dt.datetime.now(CENTRAL); weekday = now.weekday(); day = DOW[weekday]
    o, c = HOURS[weekday]; hours = list(range(o, c + 1)); frac = calc.frac_elapsed(now)
    stats, today_rows, hist_rows = [], {}, {}
    for s in STORE_CODES:
        rows = fetch_today(s); today_rows[s] = rows; hist_rows[s] = fetch_history(s)
        if not rows:
            stats.append({"store": s, "name": store_name(s), "cars": None, "net": None,
                          "aro": None, "lhpc": None, "pct": None}); continue
        latest = rows[-1]; cars = latest.get("cars") or 0; net = latest.get("net_sales") or 0
        base_h = calc.hour_baselines(hist_rows[s], weekday, "cars", exclude_date=calc.row_date(latest))
        elapsed = [h for h in hours if h <= now.hour]
        if base_h and elapsed:
            exp = sum(base_h.get(h, 0) for h in elapsed)
        else:
            cb = (baseline.get(s, {}).get("cars", {}).get(day) or {}).get("mean")
            exp = cb * frac if cb else None
        stats.append({"store": s, "name": store_name(s, latest), "cars": cars, "net": net,
                      "aro": (net / cars) if cars else 0, "lhpc": calc.get_metric(latest, "lhpc"),
                      "pct": (cars / exp * 100) if exp else None})
    return stats, today_rows, hist_rows


def render_admin(baseline):
    now = dt.datetime.now(CENTRAL)
    st.markdown(style.header(f"All Stores &middot; {now:%A, %b %-d} &middot; "
                f"{calc.frac_elapsed(now)*100:.0f}% through the day"), unsafe_allow_html=True)
    stats, today_rows, hist_rows = _admin_stats(baseline)
    live = [s for s in stats if s["cars"] is not None]
    tot_cars = sum(s["cars"] for s in live); tot_net = sum(s["net"] for s in live)
    avg_aro = (tot_net / tot_cars) if tot_cars else 0
    ahead = sum(1 for s in live if (s["pct"] or 0) >= 100)
    st.markdown(style.kpi_strip([
        ("Stores reporting", f"{len(live)}/{len(stats)}", "", MUTE, NAVY, False),
        ("Total cars", f"{tot_cars:,.0f}", "", MUTE, NAVY, False),
        ("Total net", f"${tot_net:,.0f}", "", MUTE, NAVY, False),
        ("Avg ARO", f"${avg_aro:,.2f}", "", MUTE, NAVY, False),
        ("Ahead / behind", f"{ahead} / {len(live)-ahead}" if live else "&mdash;", "vs pace",
         GREEN if ahead >= len(live)-ahead else RED, GREEN if ahead >= len(live)-ahead else RED, False),
    ]), unsafe_allow_html=True)
    st.markdown(style.note(ADMIN_TARGET_NOTE), unsafe_allow_html=True)

    # ---- ranking (rolling rail: every store, id in grey) ----
    st.markdown(style.section_header("Store ranking", "cars vs pace &mdash; leaders to laggards", ""),
                unsafe_allow_html=True)
    st.markdown(
        f'<div style="display:flex;gap:16px;flex-wrap:wrap;font-size:.76rem;color:{MUTE};'
        f'margin:-4px 0 10px;align-items:center;">'
        f'<span><b>% pace</b> = cars so far vs a normal day by this time of day.</span>'
        f'<span style="color:{GREEN};">&#9679; ahead (&ge;100%)</span>'
        f'<span style="color:{AMBER};">&#9679; on pace (90&ndash;100%)</span>'
        f'<span style="color:{RED};">&#9679; behind (&lt;90%)</span></div>', unsafe_allow_html=True)
    trows = ""
    for i, s in enumerate(calc.rank_stores(stats), 1):
        pct = s["pct"]
        col = (GREEN if pct >= 100 else AMBER if pct >= 90 else RED) if pct is not None else MUTE
        pcttxt = f"{pct:.0f}%" if pct is not None else "no data"
        trows += (f'<tr style="border-bottom:1px solid {LINE};">'
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

    # ---- heat map ----
    st.markdown(style.section_header("Heat map", "per-hour pattern, shaded vs each store's own peak", ""),
                unsafe_allow_html=True)
    hc1, hc2 = st.columns(2)
    hm_key = hc1.radio("Metric", list(METRICS.keys()), horizontal=True,
                       format_func=lambda k: METRICS[k]["label"], key="hm_metric")
    hm_src = hc2.radio("Show", ["Today (actual)", "Normal pattern"], horizontal=True, key="hm_src")
    _heatmap(today_rows, hist_rows, hm_key, hm_src)

    # ---- compare stores ----
    st.markdown(style.section_header("Compare stores", "per-hour, overlaid", ""), unsafe_allow_html=True)
    picks = st.multiselect("Stores", STORE_CODES, default=STORE_CODES[:5],
                           format_func=lambda s: f"{CITY.get(s, s)} ({s})", key="cmp_stores")
    cmp_key = st.radio("Metric", list(METRICS.keys()), horizontal=True,
                       format_func=lambda k: METRICS[k]["label"], key="cmp_metric")
    _comparison(picks, today_rows, cmp_key)

    # ---- drill-down ----
    st.markdown(style.section_header("Store drill-down", "the exact view a manager sees", ""),
                unsafe_allow_html=True)
    sel = st.selectbox("Store", STORE_CODES, format_func=lambda s: f"{CITY.get(s, s)} ({s})", key="adm_drill")
    with st.expander(f"Open {CITY.get(sel, sel)} scorecard", expanded=False):
        render_store(sel, baseline)


def _heatmap(today_rows, hist_rows, key, source):
    now = dt.datetime.now(CENTRAL); weekday = now.weekday()
    o, c = HOURS[weekday]; hrs = list(range(o, c + 1))
    stores = [s for s in STORE_CODES if (today_rows.get(s) or hist_rows.get(s))]
    if not stores:
        st.info("No store data yet for the heat map."); return
    per = {}
    for s in stores:
        if source.startswith("Today"):
            per[s] = calc.to_per_period_metric(calc.cum_by_hour(today_rows.get(s, []), key), key)
        else:
            per[s] = calc.hour_baselines(hist_rows.get(s, []), weekday, key)
    if not any(per.values()):
        st.info("Normal pattern builds as history accumulates. Switch to Today (actual) for live values."); return
    money = METRICS[key]["money"]
    z, text = [], []
    for h in hrs:
        zr, tr = [], []
        for s in stores:
            v = per[s].get(h); zr.append(v)
            tr.append("\u2014" if v is None else (f"${v:,.0f}" if money else
                      (f"{v:.2f}" if key in RATE_KEYS else f"{v:,.0f}")))
        z.append(zr); text.append(tr)
    znorm = [[None] * len(stores) for _ in hrs]
    for ci in range(len(stores)):
        col = [z[ri][ci] for ri in range(len(hrs))]
        nums = [v for v in col if v is not None]; mx = max(nums) if nums else 0
        for ri, v in enumerate(col):
            znorm[ri][ci] = (v / mx) if (v is not None and mx) else (0 if v == 0 else None)
    fig = go.Figure(go.Heatmap(
        z=znorm, x=[f"{CITY.get(s, s)} ({s})" for s in stores], y=[charts.hour_label(h) for h in hrs],
        text=text, texttemplate="%{text}", textfont={"size": 10, "color": INK},
        colorscale=HEAT_SCALE, zmin=0, zmax=1, xgap=3, ygap=3,
        colorbar=dict(title="vs peak", tickformat=".0%"),
        hovertemplate="%{x}<br>%{y}: %{text}<extra></extra>"))
    fig.update_yaxes(autorange="reversed")
    st.plotly_chart(_plot(fig, max(340, 30 * len(hrs)),
                          title=f"{METRICS[key]['label']} per hour \u2014 {source.lower()}"),
                    use_container_width=True, config={"displayModeBar": False})


def _comparison(picks, today_rows, key):
    now = dt.datetime.now(CENTRAL); o, c = HOURS[now.weekday()]; hrs = list(range(o, c + 1))
    if not picks:
        st.info("Pick one or more stores to compare."); return
    money = METRICS[key]["money"]; pref = "$" if money else ""
    palette = [NAVY, RED, BLUE, GREEN, AMBER, "#0E86A3", "#9DB6D4"]
    fig = go.Figure(); any_data = False
    for i, s in enumerate(picks):
        pp = calc.to_per_period_metric(calc.cum_by_hour(today_rows.get(s, []), key), key)
        if not pp:
            continue
        any_data = True
        fig.add_bar(x=[charts.hour_label(h) for h in hrs], y=[pp.get(h) for h in hrs],
                    name=CITY.get(s, s), marker_color=palette[i % len(palette)],
                    hovertemplate="%{x}: " + pref + "%{y:,.1f}<extra></extra>")
    if not any_data:
        st.info("No per-hour data yet today for the selected stores."); return
    fig.update_layout(barmode="group")
    fig.update_yaxes(title=("$ per hour" if money else "per hour"), rangemode="tozero")
    st.plotly_chart(_plot(fig, 360, legend="bottom"), use_container_width=True,
                    config={"displayModeBar": False})
