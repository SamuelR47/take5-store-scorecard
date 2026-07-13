"""Supabase reads (cached, guarded). Only module touching secrets/network.

V3 changes:
- fetch_history orders pull_time DESC with an explicit row cap (review H1). Ordering
  newest-first means that if PostgREST's db-max-rows cap is lower than our request,
  we keep the RECENT rows the norms need instead of silently getting the oldest ones.
  The date window stays wide (HIST_DAYS) because the seeded baseline is ~1yr old, so a
  narrow cap would empty the norms.
- healthcheck() lets the app show a "couldn't reach the data source" banner that is
  distinct from a store that simply has no business yet (review H5).
- fetch_days() pulls full daily rows for the yesterday + 7-day score cards.
"""
import datetime as dt, requests, streamlit as st
from config import CENTRAL, HIST_DAYS, HIST_MAX_ROWS, SCORECARD_DAYS

@st.cache_data(ttl=300, show_spinner=False)
def _get(path):
    url=st.secrets["SUPABASE_URL"].rstrip("/"); key=st.secrets["SUPABASE_KEY"]
    r=requests.get(url+"/rest/v1/"+path,headers={"apikey":key,"Authorization":"Bearer "+key},timeout=25)
    r.raise_for_status(); return r.json()

def fetch_today(store):
    today=dt.datetime.now(CENTRAL).strftime("%Y-%m-%d")
    try: return _get(f"daily_sales_pull?store_number=eq.{store}&pull_hour=like.{today}*&order=pull_time.asc")
    except Exception: return []

def fetch_history(store,days=HIST_DAYS):
    # History feeds the cars + net-sales norms only, so fetch just those columns.
    # DESC + explicit limit is the H1 fix: keep the newest rows under any server cap.
    since=(dt.datetime.now(CENTRAL)-dt.timedelta(days=days)).strftime("%Y-%m-%d")
    cols="pull_hour,pull_time,cars,net_sales"
    try:
        return _get(f"daily_sales_pull?store_number=eq.{store}&pull_time=gte.{since}"
                    f"&select={cols}&order=pull_time.desc&limit={HIST_MAX_ROWS}")
    except Exception:
        return []

def fetch_days(store,days=SCORECARD_DAYS+1):
    """Full daily rows for the last `days` days (incl. today), newest first. Used by
    the yesterday + weekly score cards, which need big4/line_items/labor per day."""
    since=(dt.datetime.now(CENTRAL)-dt.timedelta(days=days)).strftime("%Y-%m-%d")
    cols="pull_hour,pull_time,cars,net_sales,big4,big4_total_units,line_items,data"
    try:
        return _get(f"daily_sales_pull?store_number=eq.{store}&pull_time=gte.{since}"
                    f"&select={cols}&order=pull_time.desc&limit={HIST_MAX_ROWS}")
    except Exception:
        return []

@st.cache_data(ttl=120, show_spinner=False)
def healthcheck():
    """Cheap connectivity probe. Returns (ok, message). Distinguishes a data-source
    outage from a store that just hasn't opened yet."""
    try:
        _get("daily_sales_pull?select=store_number&limit=1")
        return True, ""
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"
