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
    """Clustered columns: Target (grey), Actual (blue), Projected (green).
    Hover shows the value plus variance vs the true norm."""
    hours = m["hours"]
    x = [hour_label(h) for h in hours]
    pref = "$" if money else ""
    target = [m["target"].get(h) for h in hours]
    actual = [m["actual"].get(h) for h in hours]
    proj = [m["projected"].get(h) for h in hours]
    norm = m["norm"]

    def hov(name):
        return name + ": " + pref + "%{y:,.1f}<extra></extra>"

    fig = go.Figure()
    fig.add_bar(x=x, y=target, name="Target", marker_color=GREYF,
                marker_line=dict(color=STEEL, width=1), offsetgroup="t",
                hovertemplate=hov("Target"))
    fig.add_bar(x=x, y=actual, name="Actual", marker_color=BLUE, offsetgroup="a",
                hovertemplate=hov("Actual"))
    fig.add_bar(x=x, y=proj, name="Projected", marker_color=GREEN, offsetgroup="a",
                hovertemplate=hov("Projected"))
    fig.update_layout(
        barmode="group", bargap=0.28, bargroupgap=0.0, height=300,
        margin=dict(l=10, r=10, t=10, b=14), paper_bgcolor="white", plot_bgcolor="white",
        font_color=INK, font_size=12, hovermode="x unified", showlegend=False)
    fig.update_xaxes(gridcolor="rgba(0,0,0,0)", showgrid=False)
    fig.update_yaxes(gridcolor=LINE, zeroline=False, rangemode="tozero",
                     title=("$ / hour" if money else "per hour"))
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
    return f'<div style="width:100%;max-width:640px;margin:0 auto;">{svg}</div>'
