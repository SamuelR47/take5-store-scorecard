"""VantEdge Auto - Take 5 Store Scorecard (modular redesign).
Entry point: page config, global CSS, auth, routing. All logic lives in the
sibling modules (config / calc / datasource / style / charts / views)."""
import streamlit as st

from config import BRAND, SUBBRAND, STORE_CODES, CITY, ADMIN_FALLBACK, store_password
import style
from datasource import load_baseline
from views import render_store, render_admin

st.set_page_config(page_title=f"{BRAND} - Store Scorecard", layout="wide",
                   initial_sidebar_state="expanded")
st.markdown(style.GLOBAL_CSS, unsafe_allow_html=True)


def login_view():
    st.markdown(style.header("Daily Store Scorecard"), unsafe_allow_html=True)
    st.write("")
    _, mid, _ = st.columns([1, 1.3, 1])
    with mid:
        st.markdown("<div style='font-weight:700;color:#14273F;font-size:1.05rem;"
                    "margin-bottom:4px;text-align:center;'>Enter your access code</div>",
                    unsafe_allow_html=True)
        with st.form("login"):
            pw = st.text_input("Access code", type="password",
                               label_visibility="collapsed", placeholder="Access code")
            ok = st.form_submit_button("Enter", type="primary", use_container_width=True)
        if ok:
            admin = st.secrets.get("ADMIN_PASSWORD", ADMIN_FALLBACK)
            if pw in STORE_CODES and pw == store_password(pw):
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
    # Top utility row - always on the page, never hidden in a collapsible sidebar.
    sp, b1, b2 = st.columns([8, 1.2, 1.2])
    with b1:
        if st.button("\u21bb Refresh", use_container_width=True):
            st.cache_data.clear(); st.rerun()
    with b2:
        if st.button("Log out", use_container_width=True):
            del st.session_state.auth; st.rerun()
    if role == "store":
        render_store(store, baseline)
    else:
        render_admin(baseline)


if __name__ == "__main__":
    main()
