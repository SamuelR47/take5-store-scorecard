"""
fleet_check.py — one-off diagnostic: how much of revenue is fleet vs. common (retail) customer?

Reads your existing Supabase creds and reports, per store over the last N days:
  - how often fleet $ is non-zero (is the field actually populated?)
  - fleet $ as a % of TOTAL RECEIPTS (correct basis) and of NET SALES (for reference)
  - the fleet vs. retail split

WHY receipts, not net: on the Daily Sales Report "Fleets" sits in the tender/receipts
block (next to Payouts), so it's a receipts-basis figure. Dividing by net mixes bases
(fleet incl. tax, net doesn't). Both are printed so you can see the gap.

HOW TO RUN (from the take5-scraper folder):
  # option A — you already have a .env with SUPABASE_URL / SUPABASE_KEY:
  python fleet_check.py
  # option B — pass them inline:
  SUPABASE_URL="https://xxxx.supabase.co" SUPABASE_KEY="eyJ..." python fleet_check.py
  # optional: change the window (default 30 days)
  DAYS=45 python fleet_check.py
"""
import os, json, datetime as dt, urllib.request, urllib.parse, collections

def load_env():
    url = os.environ.get("SUPABASE_URL"); key = os.environ.get("SUPABASE_KEY")
    if url and key:
        return url.rstrip("/"), key
    # fall back to a local .env (KEY=VALUE lines)
    for path in (".env", os.path.join(os.path.dirname(__file__), ".env")):
        if os.path.exists(path):
            for line in open(path):
                line = line.strip()
                if line.startswith("SUPABASE_URL"): url = line.split("=", 1)[1].strip().strip('"').strip("'")
                if line.startswith("SUPABASE_KEY"): key = line.split("=", 1)[1].strip().strip('"').strip("'")
    if not (url and key):
        raise SystemExit("Set SUPABASE_URL and SUPABASE_KEY (env vars or a .env in this folder).")
    return url.rstrip("/"), key

def fetch(url, key, days):
    since = (dt.datetime.now() - dt.timedelta(days=days)).strftime("%Y-%m-%d")
    # arrow-select fleet fields out of the jsonb `data` blob so we don't download whole blobs
    sel = ("store_number,store_name,pull_hour,pull_time,net_sales,total_receipts,gross_sales,"
           "fa:data->>fleets_amount,fc:data->>fleets_count")
    q = (f"{url}/rest/v1/daily_sales_pull?select={urllib.parse.quote(sel, safe='=,:>-')}"
         f"&pull_time=gte.{since}&order=pull_time.desc&limit=100000")
    req = urllib.request.Request(q, headers={"apikey": key, "Authorization": "Bearer " + key})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)

def num(x):
    try: return float(x)
    except (TypeError, ValueError): return 0.0

def main():
    url, key = load_env()
    days = int(os.environ.get("DAYS", "30"))
    rows = fetch(url, key, days)
    print(f"pulled {len(rows)} rows over the last {days} days\n")
    # keep the LAST cumulative pull per (store, calendar day) — the report is cumulative
    latest = {}
    for r in rows:
        store = r.get("store_number"); day = (r.get("pull_hour") or "")[:10]
        if not store or not day: continue
        k = (store, day)
        if k not in latest or (r.get("pull_time") or "") > (latest[k].get("pull_time") or ""):
            latest[k] = r
    per = collections.defaultdict(lambda: {"name": "", "days": 0, "nz": 0,
                                            "fleet": 0.0, "receipts": 0.0, "net": 0.0, "cnt": 0})
    for (store, day), r in latest.items():
        p = per[store]; p["name"] = r.get("store_name") or ""
        fa = num(r.get("fa")); rec = num(r.get("total_receipts")) or num(r.get("gross_sales"))
        p["days"] += 1; p["fleet"] += fa; p["receipts"] += rec; p["net"] += num(r.get("net_sales"))
        p["cnt"] += int(num(r.get("fc")))
        if fa > 0: p["nz"] += 1

    tot_days = tot_nz = 0
    print(f"{'store':>6}  {'name':<18} {'days':>4} {'nz-days':>7} {'fleet$':>10} {'%receipts':>9} {'%net':>7} {'retail%':>7}")
    for store in sorted(per):
        p = per[store]; tot_days += p["days"]; tot_nz += p["nz"]
        pr = 100 * p["fleet"] / p["receipts"] if p["receipts"] else 0.0
        pn = 100 * p["fleet"] / p["net"] if p["net"] else 0.0
        print(f"{str(store):>6}  {p['name'][:18]:<18} {p['days']:>4} {p['nz']:>7} "
              f"{p['fleet']:>10,.0f} {pr:>8.1f}% {pn:>6.1f}% {100-pr:>6.1f}%")
    print(f"\nfleet field populated on {tot_nz}/{tot_days} store-days "
          f"({(100*tot_nz/tot_days if tot_days else 0):.0f}%).")
    print("If that % is near 0, fleet is effectively unused/unlogged and the split isn't meaningful.")
    print("If it's healthy, '%receipts' is the trustworthy fleet share; retail% = 100 - that.")

if __name__ == "__main__":
    main()
