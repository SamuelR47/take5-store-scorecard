"""Charts: Plotly per-hour bars (Target / Actual / Projected) + a server-rendered
SVG dome pace-dial (embedded via components.html). Both pure - bars return a figure,
the dial returns an HTML string - so they are testable without Streamlit."""
import math
import plotly.graph_objects as go
from config import (NAVY, BLUE, GREEN, STEEL, GREYF, INK, MUTE, LINE, RED,
                    EXP, EXPLN, DIAL_ACT)


def hour_label(h):
    ap = "a" if h < 12 else "p"
    return f"{h % 12 or 12}{ap}"


def bar_figure(m, money, label):
    """Non-rate: clustered Target/Actual/Projected columns.
    Rate (ARO, labor/car): Actual columns vs a Normal reference LINE - a rate has
    no accumulating per-hour target, so no flat grey target bars."""
    hours = m["hours"]
    x = [hour_label(h) for h in hours]
    pref = "$" if money else ""
    fig = go.Figure()
    if m["is_rate"]:
        fig.add_bar(x=x, y=[m["actual"].get(h) for h in hours], name="Actual",
                    marker_color=BLUE, hovertemplate="Actual: " + pref + "%{y:,.2f}<extra></extra>")
        fig.add_trace(go.Scatter(
            x=x, y=[m["norm"].get(h) for h in hours], name="Normal", mode="lines+markers",
            line=dict(color=STEEL, width=2, dash="dot"), marker=dict(size=5, color=STEEL),
            hovertemplate="Normal: " + pref + "%{y:,.2f}<extra></extra>"))
        ytitle = ("$ per car" if money else "per car")
    else:
        fig.add_bar(x=x, y=[m["target"].get(h) for h in hours], name="Target",
                    marker_color=GREYF, marker_line=dict(color=STEEL, width=1),
                    offsetgroup="t", hovertemplate="Target: " + pref + "%{y:,.1f}<extra></extra>")
        fig.add_bar(x=x, y=[m["actual"].get(h) for h in hours], name="Actual",
                    marker_color=BLUE, offsetgroup="a", hovertemplate="Actual: " + pref + "%{y:,.1f}<extra></extra>")
        fig.add_bar(x=x, y=[m["projected"].get(h) for h in hours], name="Projected",
                    marker_color=GREEN, offsetgroup="a", hovertemplate="Projected: " + pref + "%{y:,.1f}<extra></extra>")
        fig.update_layout(barmode="group", bargap=0.28, bargroupgap=0.0)
        ytitle = ("$ / hour" if money else "per hour")
    fig.update_layout(height=300, margin=dict(l=10, r=10, t=10, b=14),
                      paper_bgcolor="white", plot_bgcolor="white", font_color=INK,
                      font_size=12, hovermode="x unified", showlegend=False)
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(gridcolor=LINE, zeroline=False, rangemode="tozero", title=ytitle)
    return fig


def dial_svg(m, money, label, dp=0, height=300):
    """Dome (speedometer) pace dial: time runs over the arc (open->close).
    Sand = expected-by-now (TRUE norm) per hour, indigo/green fill = actual
    (green when ahead of that hour's norm). Center = value so far vs pace."""
    hours = m["hours"]
    norm, actual, now_hour = m["norm"], m["actual"], m["now_hour"]
    pref = "$" if money else ""
    W, H = 640, 320
    cx, cy, r_in, r_out = 320, 268, 88, 250
    n = len(hours)
    vals = [max(norm.get(h, 0) or 0, actual.get(h) or 0) for h in hours]
    maxv = max(vals + [0.1])

    def th(i):
        return math.pi * (1 - i / n)

    def pt(r, t):
        return (cx + r * math.cos(t), cy - r * math.sin(t))

    def wedge(ri, ro, ts, te, K=8):
        pts = []
        for k in range(K + 1):
            t = ts + (te - ts) * k / K
            x, y = pt(ro, t); pts.append(f"{'L' if k else 'M'}{x:.1f},{y:.1f}")
        for k in range(K, -1, -1):
            t = ts + (te - ts) * k / K
            x, y = pt(ri, t); pts.append(f"L{x:.1f},{y:.1f}")
        return " ".join(pts) + " Z"

    out, comp_a, comp_e = [], 0.0, 0.0
    for i, h in enumerate(hours):
        ts, te = th(i) - 0.012, th(i + 1) + 0.012
        nv = norm.get(h, 0) or 0
        av = actual.get(h)
        out.append(f'<path d="{wedge(r_in, r_in + (r_out - r_in) * (nv / maxv), ts, te)}" '
                   f'fill="{EXP}" stroke="{EXPLN}" stroke-width=".5">'
                   f'<title>{hour_label(h)} - expected {pref}{nv:,.{dp}f}</title></path>')
        if av is not None:
            ahead = av >= nv
            mid, hw = (ts + te) / 2, (ts - te) * 0.30
            out.append(f'<path d="{wedge(r_in, r_in + (r_out - r_in) * (av / maxv), mid - hw, mid + hw)}" '
                       f'fill="{GREEN if ahead else DIAL_ACT}">'
                       f'<title>{hour_label(h)} - actual {pref}{av:,.{dp}f} vs expected {pref}{nv:,.{dp}f}</title></path>')
            comp_a += av; comp_e += nv
        lx, ly = pt(r_out + 16, (ts + te) / 2)
        out.append(f'<text x="{lx:.0f}" y="{ly:.0f}" font-size="10.5" fill="{MUTE}" '
                   f'text-anchor="middle" dominant-baseline="middle">{hour_label(h)}</text>')
    if now_hour is not None and now_hour in hours:
        ni = hours.index(now_hour) + 1
        a = pt(r_in - 7, th(ni)); b = pt(r_out + 7, th(ni))
        out.append(f'<line x1="{a[0]:.0f}" y1="{a[1]:.0f}" x2="{b[0]:.0f}" y2="{b[1]:.0f}" '
                   f'stroke="{NAVY}" stroke-width="2" stroke-dasharray="4 3"/>')
        out.append(f'<text x="{b[0]:.0f}" y="{b[1] - 6:.0f}" font-size="10.5" fill="{NAVY}" '
                   f'text-anchor="middle">now</text>')
    behind = comp_a < comp_e
    sofar = m["so_far"]
    sofar_txt = (pref + format(sofar, f",.{dp}f")) if sofar is not None else "&mdash;"
    state = "behind" if behind else "ahead of"
    out.append(f'<text x="{cx}" y="{cy - 30}" font-size="42" font-weight="800" fill="{INK}" '
               f'text-anchor="middle">{sofar_txt}</text>')
    out.append(f'<text x="{cx}" y="{cy - 8}" font-size="12" fill="{RED if behind else GREEN}" '
               f'text-anchor="middle">so far &middot; {state} pace</text>')
    svg = (f'<svg viewBox="0 0 {W} {H}" width="100%" height="100%" '
           f'xmlns="http://www.w3.org/2000/svg" style="font-family:-apple-system,Segoe UI,Arial,sans-serif;">'
           + "".join(out) + "</svg>")
    tip = ('<div id="vtip" style="position:fixed;pointer-events:none;background:#14273F;color:#fff;'
           'font:11px -apple-system,Segoe UI,Arial,sans-serif;padding:4px 9px;border-radius:6px;'
           'opacity:0;transition:opacity .08s;z-index:99999;white-space:nowrap;"></div>')
    script = ('<script>(function(){var t=document.getElementById("vtip");'
              'document.querySelectorAll("svg path").forEach(function(p){'
              'var ti=p.querySelector("title");if(!ti)return;p.style.cursor="pointer";'
              'p.addEventListener("mousemove",function(e){t.textContent=ti.textContent;'
              't.style.opacity=1;t.style.left=(e.clientX+12)+"px";t.style.top=(e.clientY+12)+"px";});'
              'p.addEventListener("mouseleave",function(){t.style.opacity=0;});});})();</script>')
    return f'<div style="width:100%;max-width:640px;margin:0 auto;position:relative;">{svg}{tip}{script}</div>'


MIX_COLORS = ["#2E6FB7", "#4A98C9", "#0E86A3", "#7FB2DC", "#C79A3A", "#9FB4CC"]


def _chrome(fig, height, legend=False):
    fig.update_layout(height=height, margin=dict(l=8, r=8, t=8, b=40 if legend else 12),
                      paper_bgcolor="white", plot_bgcolor="white", font_color=INK, font_size=12,
                      showlegend=legend,
                      legend=dict(orientation="h", yanchor="top", y=-0.15, x=0, font=dict(size=11)) if legend else None)
    fig.update_xaxes(gridcolor=LINE, zeroline=False)
    fig.update_yaxes(gridcolor=LINE, zeroline=False)
    return fig


def mix_figure(items):
    """100% stacked dollar-share bar. Hover shows product $ and share%."""
    rows = [(i.get("description", "?").title(), i.get("amount") or 0)
            for i in items if (i.get("amount") or 0) > 0]
    if not rows:
        return None
    total = sum(a for _, a in rows) or 1
    rows.sort(key=lambda t: t[1], reverse=True)
    keep, other = [], 0.0
    for n, a in rows:
        keep.append((n, a)) if a / total >= 0.03 else None
        if a / total < 0.03:
            other += a
    if other > 0:
        keep.append(("Other", other))
    fig = go.Figure()
    for i, (n, a) in enumerate(keep):
        share = a / total * 100
        fig.add_bar(x=[share], y=["Today's $"], orientation="h", name=n,
                    marker_color=MIX_COLORS[i % len(MIX_COLORS)],
                    text=[f"{share:.0f}%" if share >= 6 else ""], textposition="inside",
                    insidetextanchor="middle", textfont=dict(color="#fff", size=12),
                    hovertemplate=f"{n}: ${a:,.0f} (%{{x:.0f}}%)<extra></extra>")
    fig.update_layout(barmode="stack")
    fig.update_xaxes(range=[0, 100], visible=False)
    fig.update_yaxes(showticklabels=False)
    return _chrome(fig, 200, legend=True)


def big4_figure(big4):
    """Big 4 attach-rate bars. Hover shows attach %, units and $."""
    order = ["Coolant Exchange", "Air Filter", "Cabin Filter", "Wiper Blade", "Differential"]
    names = [n for n in order if n in big4] or list(big4.keys())
    if not names:
        return None
    attach = [(big4.get(n) or {}).get("attach_pct") or 0 for n in names]
    units = [(big4.get(n) or {}).get("units") or 0 for n in names]
    amt = [(big4.get(n) or {}).get("amount") or 0 for n in names]
    fig = go.Figure(go.Bar(
        x=attach, y=names, orientation="h", marker_color=DIAL_ACT,
        text=[f"{a:.1f}%" for a in attach], textposition="outside", cliponaxis=False,
        customdata=list(zip(units, amt)),
        hovertemplate="%{y}: %{x:.1f}% of cars<br>%{customdata[0]} units &middot; $%{customdata[1]:,.0f}<extra></extra>"))
    fig.update_xaxes(title="% of cars", rangemode="tozero")
    fig.update_yaxes(autorange="reversed")
    return _chrome(fig, 230)
