"""Design system: one global stylesheet + pure HTML-atom builders that mirror the
approved prototype (header, so-what line, KPI strip, section header w/ chips,
product mix, Big 4 attach, ops tiles, print score card). No Streamlit imports -
every function returns an HTML string, so the whole look is testable and lives in
ONE place (no drift)."""
from config import (NAVY, RED, BLUE, GREEN, STEEL, INK, MUTE, LINE, LIGHT, GREYF,
                    CODE, EXP, DIAL_ACT, BRAND, SUBBRAND)


def fmt(v, money=False, dp=0):
    if v is None:
        return "&mdash;"
    try:
        return ("$" if money else "") + format(float(v), f",.{dp}f")
    except (TypeError, ValueError):
        return "&mdash;"


GLOBAL_CSS = f"""
<style>
  .block-container {{padding-top:2.4rem;padding-bottom:2rem;max-width:1240px;}}
  #MainMenu, footer {{visibility:hidden;}}
  /* Streamlit's top bar is a white strip - make it transparent (NOT zero-height,
     which hides the sidebar reopen arrow) so the navy box isn't cut off. */
  [data-testid="stHeader"] {{background:rgba(0,0,0,0) !important;}}
  [data-testid="stToolbar"] {{visibility:hidden;}}
  /* keep the "open sidebar" chevron visible after the user collapses it */
  [data-testid="stSidebarCollapsedControl"], [data-testid="collapsedControl"]
    {{visibility:visible !important;opacity:1 !important;z-index:1000;}}
  html, body, [class*="css"] {{color:{INK};}}
  .stApp {{background:#FFFFFF;}}
  .vea-head, .vea-head * {{overflow:visible !important;}}
  /* header - fixed height so the wordmark is TRULY vertically centered */
  .vea-head {{background:{NAVY};border-radius:12px;min-height:78px;
     padding:16px 26px;margin:0 0 8px;display:flex;flex-direction:column;
     align-items:center;justify-content:center;text-align:center;gap:6px;box-sizing:border-box;}}
  .vea-head > div {{width:100%;}}
  .vea-brandrow {{display:flex;align-items:center;justify-content:center;gap:12px;}}
  .vea-tick {{width:9px;height:30px;background:{RED};border-radius:2px;flex:none;}}
  .vea-name {{color:#fff;font-size:1.5rem;font-weight:800;letter-spacing:.03em;line-height:1;}}
  .vea-name span {{color:{STEEL};font-weight:500;font-size:.82rem;}}
  .vea-sub {{color:#DCE5F0;font-size:.92rem;line-height:1.2;}}
  .vea-fresh {{font-size:.84rem;color:{MUTE};margin:0 0 10px 2px;}}
  .vea-sowhat {{display:flex;align-items:center;gap:11px;border-radius:11px;padding:12px 16px;
     margin:0 0 14px;font-size:1.02rem;line-height:1.4;border:1px solid {LINE};}}
  .vea-sowhat b {{font-weight:800;}}
  .vea-kpi {{background:#fff;border:1px solid {LINE};border-top:3px solid {NAVY};
     border-radius:11px;padding:11px 14px;position:relative;flex:1 1 150px;min-width:140px;}}
  .vea-kpi .l {{font-size:.62rem;text-transform:uppercase;letter-spacing:.05em;color:{MUTE};}}
  .vea-kpi .v {{font-size:1.5rem;font-weight:800;color:{INK};line-height:1.2;}}
  .vea-kpi .d {{font-size:.72rem;font-weight:700;}}
  .vea-mhead {{display:flex;align-items:center;gap:12px;border-left:4px solid {RED};
     padding:2px 0 2px 11px;margin:20px 0 10px;flex-wrap:wrap;}}
  .vea-mhead .ttl {{font-size:1.08rem;font-weight:800;color:{NAVY};}}
  .vea-mhead .note {{font-size:.8rem;font-weight:500;color:{MUTE};}}
  .vea-mhead .chips {{margin-left:auto;display:flex;gap:8px;flex-wrap:wrap;}}
  .vea-chip {{background:#fff;border:1px solid {LINE};border-top:3px solid {STEEL};
     border-radius:9px;padding:5px 11px;min-width:88px;}}
  .vea-chip .l {{font-size:.58rem;letter-spacing:.06em;text-transform:uppercase;color:{MUTE};}}
  .vea-chip .v {{font-size:1.05rem;font-weight:800;color:{INK};line-height:1.15;}}
  .vea-chip .d {{font-size:.66rem;font-weight:700;}}
  .vea-tile {{background:#fff;border:1px solid {LINE};border-radius:11px;padding:11px 14px;
     flex:1 1 150px;min-width:135px;}}
  .vea-tile .l {{font-size:.62rem;text-transform:uppercase;letter-spacing:.05em;color:{MUTE};}}
  .vea-tile .v {{font-size:1.25rem;font-weight:800;color:{INK};line-height:1.2;}}
  .vea-tile .c {{font-size:.7rem;color:{MUTE};}}
  .vea-note {{font-size:.78rem;color:{MUTE};background:#FBF7EC;border:1px solid #EADFBE;
     border-radius:10px;padding:9px 13px;margin-top:22px;}}
  @media print {{
    section[data-testid="stSidebar"], .stButton, [data-testid="stToolbar"], .vea-noprint
      {{display:none !important;}}
    .block-container {{max-width:100% !important;padding-top:0 !important;}}
  }}
</style>
"""


def header(sub):
    return (f'<div class="vea-head"><div class="vea-brandrow"><div class="vea-tick"></div>'
            f'<div class="vea-name">{BRAND}<span> &middot; {SUBBRAND}</span></div></div>'
            f'<div class="vea-sub">{sub}</div></div>')


def freshness(ts, color, age_note=""):
    return (f'<div class="vea-fresh"><span style="color:{color};font-size:1rem;">&#9679;</span> '
            f'Data as of {ts}{age_note}</div>')


def sowhat(cls_bg, border, ic, msg):
    return (f'<div class="vea-sowhat" style="background:{cls_bg};border-color:{border};">'
            f'<span style="font-size:1.2rem;line-height:1;">{ic}</span><span>{msg}</span></div>')


def _chip(label, value, sub, sub_color, top=STEEL):
    return (f'<div class="vea-chip" style="border-top-color:{top};"><div class="l">{label}</div>'
            f'<div class="v">{value}</div><div class="d" style="color:{sub_color};">{sub or "&nbsp;"}</div></div>')


def section_header(title, note, chips_html):
    return (f'<div class="vea-mhead"><span class="ttl">{title}</span>'
            f'<span class="note">{note}</span><div class="chips">{chips_html}</div></div>')


def metric_chips(m, money, dp, sample=False):
    """So far / Target / Proj close / Pace  -- pace + proj colored vs the TRUE norm."""
    has = m["pace"] is not None
    behind = has and m["pace"] < 1
    proj, tgt = m["proj_close"], m["target_close"]
    proj_col = GREEN if (proj is not None and tgt is not None and proj >= tgt) else (RED if tgt else MUTE)
    proj_sub = ""
    if proj is not None and m["norm_close"]:
        d = proj - m["norm_close"]
        proj_sub = f'{"+" if d >= 0 else ""}{round(d, 1)} vs norm'
    pace_top = GREEN if (has and not behind) else (RED if has else STEEL)
    return (
        _chip("So far", fmt(m["so_far"], money, dp), "sample" if sample else "", MUTE)
        + _chip("Target", fmt(tgt, money, dp), "", MUTE)
        + _chip("Proj close", fmt(proj, money, dp), proj_sub, proj_col)
        + _chip("Pace", (f'{m["pace"]:.2f}&times;' if has else "&mdash;"),
                ("behind" if behind else "ahead") if has else "", (RED if behind else GREEN) if has else MUTE, pace_top)
    )


def kpi_strip(cards):
    """cards: list of (label, value, sub, sub_color, top_border, sample_bool)."""
    cells = ""
    for label, value, sub, sub_color, top, sample in cards:
        smp = (f'<span style="position:absolute;top:9px;right:10px;font-size:.56rem;'
               f'font-weight:700;color:#B99433;">SAMPLE</span>') if sample else ""
        cells += (f'<div class="vea-kpi" style="border-top-color:{top};">{smp}'
                  f'<div class="l">{label}</div><div class="v">{value}</div>'
                  f'<div class="d" style="color:{sub_color};">{sub or "&nbsp;"}</div></div>')
    return f'<div style="display:flex;gap:11px;flex-wrap:wrap;margin:0 0 16px;">{cells}</div>'


def product_mix_stack(items, colors):
    seg = "".join(f'<div style="width:{p}%;background:{colors[i%len(colors)]}" title="{n} {p}%"></div>'
                  for i, (n, a, p) in enumerate(items))
    rows = "".join(
        f'<div style="display:flex;align-items:center;gap:8px;font-size:.82rem;margin-top:8px;">'
        f'<span style="width:11px;height:11px;border-radius:3px;background:{colors[i%len(colors)]}"></span>{n}'
        f'<span style="margin-left:auto;color:{MUTE};">${a:,.0f} &middot; {p}%</span></div>'
        for i, (n, a, p) in enumerate(items))
    return (f'<div style="display:flex;height:30px;border-radius:7px;overflow:hidden;'
            f'border:1px solid {LINE};">{seg}</div>{rows}')


def big4_bars(big4, teal=DIAL_ACT):
    mx = max([b["attach"] for b in big4] + [15])
    out = ""
    for b in big4:
        w = max(2, b["attach"] / mx * 100)
        col = teal if b["attach"] > 0 else LINE
        out += (f'<div style="display:flex;align-items:center;gap:10px;margin-top:11px;">'
                f'<span style="width:120px;font-size:.82rem;font-weight:600;">{b["name"]}</span>'
                f'<span style="flex:1;height:10px;background:{LIGHT};border-radius:5px;overflow:hidden;">'
                f'<span style="display:block;height:100%;width:{w:.0f}%;background:{col};border-radius:5px;"></span></span>'
                f'<span style="width:150px;text-align:right;font-size:.78rem;color:{MUTE};">'
                f'{b["attach"]:.1f}% &middot; {b["units"]}u &middot; ${b["amt"]:,.0f}</span></div>')
    return out


def ops_tiles(pairs):
    cells = "".join(f'<div class="vea-tile"><div class="l">{l}</div><div class="v">{v}</div>'
                    f'<div class="c">{c}</div></div>' for l, v, c in pairs)
    return f'<div style="display:flex;gap:11px;flex-wrap:wrap;">{cells}</div>'


def note(html):
    return f'<div class="vea-note">{html}</div>'


def dial_legend():
    """Color key placed BELOW the dial (slate expected, teal actual, green ahead)."""
    def item(c, t):
        return (f'<span style="display:inline-flex;align-items:center;gap:6px;">'
                f'<span style="width:11px;height:11px;border-radius:3px;background:{c};"></span>{t}</span>')
    from config import EXP, DIAL_ACT, GREEN
    return ('<div style="display:flex;gap:14px;flex-wrap:wrap;justify-content:center;'
            f'font-size:.74rem;color:{MUTE};margin:-6px 0 6px;">'
            + item(EXP, "Expected by now") + item(DIAL_ACT, "Actual (on/under pace)")
            + item(GREEN, "Ahead of pace") + "</div>")


def bar_legend(rate=False):
    """Legend below the bars (aligns with the dial legend). Rate metrics show
    Actual vs Normal (line); everything else shows Target/Actual/Projected."""
    from config import GREYF, STEEL, BLUE, GREEN
    def item(c, t, brd=""):
        b = f";border:1px solid {brd}" if brd else ""
        return (f'<span style="display:inline-flex;align-items:center;gap:6px;">'
                f'<span style="width:11px;height:11px;border-radius:3px;background:{c}{b}"></span>{t}</span>')
    def line_item(c, t):
        return (f'<span style="display:inline-flex;align-items:center;gap:6px;">'
                f'<span style="width:14px;height:0;border-top:2px dotted {c};"></span>{t}</span>')
    inner = (item(BLUE, "Actual") + line_item(STEEL, "Normal")) if rate else (
        item(GREYF, "Target", STEEL) + item(BLUE, "Actual") + item(GREEN, "Projected"))
    return ('<div style="display:flex;gap:14px;flex-wrap:wrap;justify-content:center;'
            f'font-size:.74rem;color:{MUTE};margin:-6px 0 6px;">' + inner + "</div>")


def divider():
    """Thin gray rule between metric sections for visual separation."""
    return f'<div style="border-top:1px solid {LINE};margin:22px 0 2px;"></div>'
