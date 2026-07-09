"""VantEdge Auto - Take 5 Scorecard V2. Streamlit shell: auth + Supabase data +
per-tier payload -> one embedded HTML/Chart.js dashboard. Three tiers:
store (own store), DM/AM (their region's stores), admin (all 15)."""
import base64, datetime as dt
import streamlit as st
import streamlit.components.v1 as components

from config import (BRAND, CENTRAL, STORE_CODES, CITY, REGIONS, DISTRICTS, ADMIN_FALLBACK,
                    HOURS, NAVY, GREEN, RED, AMBER, PURPLE)
import calc, dashboard, scorecard_pdf
from datasource import fetch_today, fetch_history

st.set_page_config(page_title=f"{BRAND} - Take 5 Scorecard", layout="wide",
                   initial_sidebar_state="collapsed")
st.markdown("""<style>
 .block-container{padding:1rem 1rem 0;max-width:100%;}
 #MainMenu,footer{visibility:hidden;}
 header[data-testid="stHeader"]{display:none!important;}
 [data-testid="stToolbar"],[data-testid="stDecoration"],[data-testid="stStatusWidget"],
 .stDeployButton,[data-testid="stAppDeployButton"]{display:none!important;}
</style>""", unsafe_allow_html=True)

RGB = {"g": GREEN, "r": RED, "a": AMBER, "flat": NAVY}
def _hex(h): h=h.lstrip("#"); return tuple(int(h[i:i+2],16) for i in (0,2,4))


def region_of(store):
    for r, ids in REGIONS.items():
        if store in ids:
            return r
    return ""


def login_view():
    st.markdown(f"<div style='background:{NAVY};border-radius:10px;padding:16px 22px;color:#fff;"
                f"margin-bottom:16px;'><span style='font-size:1.3rem;font-weight:800;'>VantEdge Auto</span>"
                f"<span style='color:#9FB4CC;font-size:.8rem;'> &nbsp;·&nbsp; Take 5 Scorecard</span></div>",
                unsafe_allow_html=True)
    _, mid, _ = st.columns([1, 1.2, 1])
    with mid:
        st.markdown("<div style='font-weight:700;color:#14273F;text-align:center;margin-bottom:4px;'>"
                    "Enter your access code</div>", unsafe_allow_html=True)
        with st.form("login"):
            pw = st.text_input("code", type="password", label_visibility="collapsed", placeholder="Access code")
            ok = st.form_submit_button("Enter", type="primary", use_container_width=True)
        if ok:
            admin = st.secrets.get("ADMIN_PASSWORD", ADMIN_FALLBACK)
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
    stores, rows = {}, {}
    for s in allowed:
        td = fetch_today(s); hist = fetch_history(s)
        stores[s] = calc.build_store(s, CITY[s], region_of(s), td, hist, now)
        rows[s] = calc.build_admin_row(s, CITY[s], td, hist, now)
    pdf = {}
    for s in allowed:
        sp = stores[s]
        pdf[s] = base64.b64encode(scorecard_pdf.build_scorecard_pdf(
            sp["name"], s, sp["date"], sp["asof"], score_card_cards(sp))).decode()
    return {"tier": tier, "scope_label": scope_label, "allowed": allowed,
            "regions": REGIONS if tier == "admin" else {}, "stores": stores, "rows": rows,
            "hours": hours, "date": stores[allowed[0]]["date"] if allowed else "",
            "asof": now.strftime("%-I:%M %p"), "pdf": pdf}


def score_card_cards(sp):
    def rgb(k): return _hex(RGB.get(sp["status"].get(k, "flat"), NAVY))
    d = sp["diff"]; cars = sp["cars"]["sofar"] or 0
    dpct = (d["units"] / cars * 100) if cars else 0
    return [
        ("Cars", f"{sp['cars']['sofar']:,.0f}", _pace(sp["cars"]["pace_pct"]), rgb("cars")),
        ("ARO", f"${sp['aro']['sofar']:,.2f}" if sp['aro']['sofar'] else "—", _pace(sp["aro"]["gap_pct"]) + " vs $125", rgb("aro")),
        ("Net revenue", f"${sp['net']['sofar']:,.0f}", _pace(sp["net"]["pace_pct"]), rgb("net")),
        ("Big 4/5 %", f"{sp['big4']['sofar']:,.0f}%" if sp['big4']['sofar'] is not None else "—", f"target {sp['big4']['target']}%", rgb("big4")),
        ("LHPC", f"{sp['lhpc']['day']:.2f}" if sp['lhpc']['day'] else "—", "target 1.10", rgb("lhpc")),
        ("Differentials", f"{d['units']}", f"${d['amount']:,.0f} · {dpct:.0f}% of cars", _hex(PURPLE)),
    ]


def _pace(v):
    return "—" if v is None else (("+" if v >= 0 else "") + f"{v:g}%")


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

    now = dt.datetime.now(CENTRAL)
    stamp = now.strftime("%Y-%m-%d-%H")
    payload = build_payload(tier, allowed, scope, stamp)

    # ---- Log out (top-right); score card now lives inside the dashboard ----
    _, cr = st.columns([9, 1])
    with cr:
        if st.button("Log out", use_container_width=True):
            del st.session_state.auth; st.cache_data.clear(); st.rerun()

    components.html(dashboard.html(payload), height=2600, scrolling=True)


if __name__ == "__main__":
    main()
