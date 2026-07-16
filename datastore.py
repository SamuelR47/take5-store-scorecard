"""V4 write layer — reads + writes for the three interactive tables
(store_targets, task_completions, messages).

Separate from datasource.py on purpose: datasource.py is V3's read-only path and
stays untouched. This module adds the write paths V4 needs. Same PostgREST + anon-key
pattern; writes use POST/PATCH/DELETE with a Prefer header for upserts.

Cache discipline: each read is cached and each write clears ONLY its own read cache
(via <fn>.clear()), so a task check-off doesn't blow away the expensive store-data
cache in datasource.py. All reads swallow errors and return empty, so a data-source
blip degrades to "nothing there yet" rather than crashing a view.
"""
import datetime as dt
from urllib.parse import quote
import requests, streamlit as st
from config import CENTRAL

_enc = lambda s: quote(str(s), safe="")


def _base():
    return st.secrets["SUPABASE_URL"].rstrip("/"), st.secrets["SUPABASE_KEY"]


def _headers(key, write=False, upsert=False):
    h = {"apikey": key, "Authorization": "Bearer " + key}
    if write:
        h["Content-Type"] = "application/json"
        pref = ["return=minimal"]
        if upsert:
            pref.append("resolution=merge-duplicates")
        h["Prefer"] = ",".join(pref)
    return h


def _get(path):
    url, key = _base()
    r = requests.get(url + "/rest/v1/" + path, headers=_headers(key), timeout=25)
    r.raise_for_status(); return r.json()


def _post(table, payload, upsert=False, on_conflict=None):
    url, key = _base()
    q = f"?on_conflict={on_conflict}" if (upsert and on_conflict) else ""
    r = requests.post(url + "/rest/v1/" + table + q, json=payload,
                      headers=_headers(key, write=True, upsert=upsert), timeout=25)
    r.raise_for_status(); return True


def _patch(table, filt, payload):
    url, key = _base()
    r = requests.patch(url + "/rest/v1/" + table + "?" + filt, json=payload,
                       headers=_headers(key, write=True), timeout=25)
    r.raise_for_status(); return True


def _delete(table, filt):
    url, key = _base()
    r = requests.delete(url + "/rest/v1/" + table + "?" + filt,
                        headers=_headers(key), timeout=25)
    r.raise_for_status(); return True


# ---------------- B. store_targets ----------------
@st.cache_data(ttl=120, show_spinner=False)
def _targets_raw():
    try:
        return _get("store_targets?select=store_number,metric,boost_pct,updated_by,updated_at")
    except Exception:
        return []


def get_targets():
    """-> {store_number: {metric: boost_pct}}. Only norm-based metrics (cars/net/big4)."""
    out = {}
    for r in _targets_raw():
        out.setdefault(str(r["store_number"]), {})[r["metric"]] = float(r.get("boost_pct") or 0)
    return out


def set_target(store, metric, boost_pct, updated_by=""):
    """Upsert one store's boost% for one metric. Keyed (store_number, metric)."""
    _post("store_targets",
          {"store_number": str(store), "metric": metric,
           "boost_pct": float(boost_pct), "updated_by": updated_by or "",
           "updated_at": dt.datetime.now(CENTRAL).isoformat()},
          upsert=True, on_conflict="store_number,metric")
    _targets_raw.clear()


# ---------------- C. task_completions ----------------
@st.cache_data(ttl=60, show_spinner=False)
def _completions_raw(date_str):
    try:
        return _get(f"task_completions?task_date=eq.{date_str}"
                    "&select=store_number,task,completed_by,completed_at")
    except Exception:
        return []


def get_completions(date_str, stores=None):
    """-> {store_number: {task: completed_by}} for one date, optionally filtered to `stores`."""
    out = {}
    for r in _completions_raw(date_str):
        s = str(r["store_number"])
        if stores and s not in stores:
            continue
        out.setdefault(s, {})[r["task"]] = r.get("completed_by") or ""
    return out


def complete_task(store, date_str, task, completed_by=""):
    """Idempotent check-off. Keyed (store_number, task_date, task)."""
    _post("task_completions",
          {"store_number": str(store), "task_date": date_str, "task": task,
           "completed_by": completed_by or "",
           "completed_at": dt.datetime.now(CENTRAL).isoformat()},
          upsert=True, on_conflict="store_number,task_date,task")
    _completions_raw.clear()


def uncomplete_task(store, date_str, task):
    """Remove a check-off (manager un-ticks the box)."""
    _delete("task_completions",
            f"store_number=eq.{_enc(store)}&task_date=eq.{_enc(date_str)}&task=eq.{_enc(task)}")
    _completions_raw.clear()


# ---------------- E. messages ----------------
@st.cache_data(ttl=60, show_spinner=False)
def _messages_raw():
    try:
        return _get("messages?select=id,from_user,to_scope,to_store,body,sent_at,read_at"
                    "&order=sent_at.desc&limit=500")
    except Exception:
        return []


def send_message(from_user, to_scope, body, to_store=None):
    """Admin composes. to_scope in {'store','district','all'}; to_store is the
    store_number / DM code (None for 'all')."""
    _post("messages",
          {"from_user": from_user or "", "to_scope": to_scope,
           "to_store": (str(to_store) if to_store else None), "body": body,
           "sent_at": dt.datetime.now(CENTRAL).isoformat()})
    _messages_raw.clear()


def get_inbox(role, code):
    """Messages this recipient should see: broadcast ('all') + those addressed to
    exactly this store or this DM. (Store-sees-its-DM routing is a Phase-5 refinement.)"""
    out = []
    for m in _messages_raw():
        sc = m.get("to_scope")
        if sc == "all":
            out.append(m)
        elif sc == "store" and role == "store" and str(m.get("to_store")) == str(code):
            out.append(m)
        elif sc == "district" and role == "district" and str(m.get("to_store")) == str(code):
            out.append(m)
    return out


def get_sent(limit=200):
    """Admin's outbox view — everything, newest first."""
    return _messages_raw()[:limit]


def mark_read(msg_id):
    _patch("messages", f"id=eq.{_enc(msg_id)}",
           {"read_at": dt.datetime.now(CENTRAL).isoformat()})
    _messages_raw.clear()
