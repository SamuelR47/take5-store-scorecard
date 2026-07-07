"""Supabase access + baseline loader. The ONLY module that touches Streamlit
secrets / cache / network. Reads are cached (5 min) and guarded so a bad read
never crashes the UI."""
import json
import datetime as dt
import requests
import streamlit as st
from config import CENTRAL, HIST_DAYS


@st.cache_data(ttl=300, show_spinner=False)
def _get(path):
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
        return _get(f"daily_sales_pull?store_number=eq.{store}"
                    f"&pull_hour=like.{today}*&order=pull_time.asc")
    except Exception:
        return []


def fetch_history(store, days=HIST_DAYS):
    since = (dt.datetime.now(CENTRAL) - dt.timedelta(days=days)).strftime("%Y-%m-%d")
    cols = ("pull_hour,pull_time,cars,net_sales,gross_sales,big4_total_units,"
            "data,report_timestamp")
    try:
        return _get(f"daily_sales_pull?store_number=eq.{store}"
                    f"&pull_time=gte.{since}&select={cols}&order=pull_time.asc")
    except Exception:
        return []


def fetch_range(store, days):
    since = (dt.datetime.now(CENTRAL) - dt.timedelta(days=days)).strftime("%Y-%m-%d")
    try:
        return _get(f"daily_sales_pull?store_number=eq.{store}"
                    f"&pull_time=gte.{since}&order=pull_time.asc")
    except Exception:
        return []


@st.cache_data(show_spinner=False)
def load_baseline():
    import os
    here = os.path.dirname(os.path.abspath(__file__))
    for path in ("baseline.json", os.path.join(here, "baseline.json"),
                 os.path.join(here, "..", "baseline.json")):
        try:
            with open(path) as f:
                return json.load(f)
        except (OSError, ValueError):
            continue
    return {}
