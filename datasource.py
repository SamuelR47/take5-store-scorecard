"""Supabase reads (cached, guarded). Only module touching secrets/network."""
import datetime as dt, requests, streamlit as st
from config import CENTRAL, HIST_DAYS

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
    since=(dt.datetime.now(CENTRAL)-dt.timedelta(days=days)).strftime("%Y-%m-%d")
    try: return _get(f"daily_sales_pull?store_number=eq.{store}&pull_time=gte.{since}&order=pull_time.asc")
    except Exception: return []
