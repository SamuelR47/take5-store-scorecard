"""
Take 5 hourly AutoPoll scraper.

Each run: check store hours (Central) -> if any store open, log in to AutoPoll
-> pull each store's Current Sales Report -> parse -> save raw+parsed locally
-> upsert to Supabase. Per-store isolation, retries, session re-login, and a
health check so silent breakage is caught.

Config via environment variables (see .env.example):
  AUTOPOLL_USER, AUTOPOLL_PASS   AutoPoll login
  STORES                          comma-separated store numbers, e.g. "1512,1515"
  SUPABASE_URL, SUPABASE_KEY      optional; if unset, only local files are written
  OUTPUT_DIR                      where raw/parsed files go (default "Hourly Data Pull")
  FORCE_RUN=1                     bypass the open-hours gate (for manual/testing)
"""
import os, sys, json, time, datetime as dt
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

import autopoll_parser as ap

CENTRAL = ZoneInfo("America/Chicago")
BASE = "https://autopoll.drivenbrands.com"
LOGIN_URL = f"{BASE}/Account/LogOn"
REPORT_URL = f"{BASE}/MainMenu/DisplaySalesReport/csr{{store}}"

# Store open hours in Central time, keyed by Python weekday (Mon=0 .. Sun=6).
# (open_hour, close_hour) 24h. We pull on any hour where open <= hour <= close.
HOURS = {
    0: (7, 20), 1: (7, 20), 2: (7, 20), 3: (7, 20), 4: (7, 20),  # Mon-Fri 7a-8p
    5: (7, 18),   # Sat 7a-6p
    6: (9, 17),   # Sun 9a-5p
}


def is_open_now(now=None):
    now = now or dt.datetime.now(CENTRAL)
    open_h, close_h = HOURS[now.weekday()]
    return open_h <= now.hour <= close_h


def login(user, password):
    """Return an authenticated requests.Session, or raise."""
    s = requests.Session()
    s.headers["User-Agent"] = "Take5-Scorecard/1.0"
    # ASP.NET MVC forms login: standard field names are UserName / Password.
    resp = s.post(LOGIN_URL, data={
        "UserName": user, "Password": password, "RememberMe": "true",
    }, timeout=30, allow_redirects=True)
    resp.raise_for_status()
    if "/Account/LogOn" in resp.url or "Log On" in resp.text[:2000]:
        raise RuntimeError("login failed - still on LogOn page (check credentials/field names)")
    return s


def fetch_report_text(session, store):
    """Fetch a store's report and return plain text for the parser."""
    url = REPORT_URL.format(store=store)
    r = session.get(url, timeout=30)
    r.raise_for_status()
    if "/Account/LogOn" in r.url:
        raise PermissionError("session expired")
    soup = BeautifulSoup(r.text, "html.parser")
    pre = soup.find("pre")
    text = pre.get_text("\n") if pre else soup.get_text("\n")
    if "CURRENT SALES REPORT" not in text:
        raise ValueError("report body not found (page layout may have changed)")
    return text


def save_local(out_dir, store, data, raw_text, now):
    date = now.strftime("%Y-%m-%d")
    hhmm = now.strftime("%H%M")
    raw_dir = os.path.join(out_dir, "raw", date)
    parsed_dir = os.path.join(out_dir, "parsed", date)
    os.makedirs(raw_dir, exist_ok=True)
    os.makedirs(parsed_dir, exist_ok=True)
    with open(os.path.join(raw_dir, f"{store}_{hhmm}.txt"), "w") as f:
        f.write(raw_text)
    with open(os.path.join(parsed_dir, f"{store}_{hhmm}.json"), "w") as f:
        json.dump(data, f, indent=2)


def upsert_supabase(url, key, data, now):
    """Upsert one row keyed on (store_number, pull_hour) so re-runs replace."""
    row = {
        "store_number": data.get("store_number"),
        "store_name": data.get("store_name"),
        "report_timestamp": data.get("report_timestamp"),
        "pull_time": now.isoformat(),
        "pull_hour": now.strftime("%Y-%m-%d-%H"),
        "cars": data.get("cars"),
        "net_sales": data.get("net_sales"),
        "gross_sales": data.get("gross_sales"),
        "total_receipts": data.get("total_receipts"),
        "materials_pct": data.get("materials_pct"),
        "asa": data.get("asa"),
        "coupons": data.get("coupons"),
        "discounts": data.get("discounts"),
        "new_customers": data.get("new_customers"),
        "repeat_customers": data.get("repeat_customers"),
        "big4_total_units": data.get("big4_total_units"),
        "big4_total_amount": data.get("big4_total_amount"),
        "big4": data.get("big4"),
        "line_items": data.get("line_items"),
        "data": data,  # full parsed payload as jsonb
    }
    endpoint = f"{url}/rest/v1/daily_sales_pull?on_conflict=store_number,pull_hour"
    headers = {
        "apikey": key, "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }
    resp = requests.post(endpoint, headers=headers, data=json.dumps([row]), timeout=30)
    resp.raise_for_status()


def pull_store(session, store, retries=3):
    last = None
    for attempt in range(1, retries + 1):
        try:
            text = fetch_report_text(session, store)
            data = ap.parse_report(text)
            problems = ap.validate(data)
            if problems:
                raise ValueError(f"validation: {problems}")
            return data, text
        except Exception as e:
            last = e
            print(f"  [store {store}] attempt {attempt} failed: {e}")
            time.sleep(2 * attempt)
    raise last


def main():
    user = os.environ.get("AUTOPOLL_USER")
    password = os.environ.get("AUTOPOLL_PASS")
    stores = [s.strip() for s in os.environ.get("STORES", "1512,1515").split(",") if s.strip()]
    out_dir = os.environ.get("OUTPUT_DIR", "Hourly Data Pull")
    sb_url = os.environ.get("SUPABASE_URL")
    sb_key = os.environ.get("SUPABASE_KEY")
    force = os.environ.get("FORCE_RUN") == "1"

    now = dt.datetime.now(CENTRAL)
    if not force and not is_open_now(now):
        print(f"{now:%Y-%m-%d %H:%M %Z}: stores closed, nothing to do.")
        return 0
    if not user or not password:
        print("ERROR: AUTOPOLL_USER / AUTOPOLL_PASS not set.")
        return 1

    print(f"{now:%Y-%m-%d %H:%M %Z}: pulling stores {stores}")
    session = login(user, password)

    ok, failed = [], []
    for store in stores:
        try:
            data, text = pull_store(session, store)
        except PermissionError:
            print("  session expired, re-logging in...")
            session = login(user, password)
            data, text = pull_store(session, store)
        except Exception as e:
            print(f"  [store {store}] GAVE UP: {e}")
            failed.append(store)
            continue
        save_local(out_dir, store, data, text, now)
        if sb_url and sb_key:
            try:
                upsert_supabase(sb_url, sb_key, data, now)
            except Exception as e:
                print(f"  [store {store}] supabase upsert failed: {e}")
                failed.append(store)
                continue
        ok.append(store)
        print(f"  [store {store}] OK - {data.get('store_name')} "
              f"cars={data.get('cars')} net=${data.get('net_sales')}")

    print(f"Done. success={ok} failed={failed}")
    # Non-zero exit if every store failed -> surfaces as a failed Actions run.
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
