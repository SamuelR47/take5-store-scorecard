# Take 5 Store Scorecard — Hourly Scraper

Pulls the AutoPoll "Current Sales Report" for each store every hour during open
hours, parses it, saves raw + parsed captures, and (optionally) upserts to
Supabase for the dashboard. Pilot stores: **1512, 1515**.

## Files
| File | Purpose |
|---|---|
| `scraper.py` | Main job: login, open-hours gate, pull each store, retries, save + upsert |
| `autopoll_parser.py` | Turns a report into structured data (incl. Big 4 attachment); has a validation check |
| `.github/workflows/hourly.yml` | Runs the scraper hourly (UTC cron, Central-time gated in code) |
| `supabase_schema.sql` | The `daily_sales_pull` table |
| `requirements.txt` | `requests`, `beautifulsoup4` |
| `.env.example` | Config template |

## Store hours (Central) — already coded in `scraper.py`
Mon–Fri 7a–8p · Sat 7a–6p · Sun 9a–5p. The script checks the current Central time
each run and does nothing when closed, so the UTC cron and daylight-saving are
handled automatically.

## Setup (one time)

### 1. GitHub
1. Create a new repository and upload these files.
2. **Settings → Secrets and variables → Actions → Secrets**, add:
   - `AUTOPOLL_USER`, `AUTOPOLL_PASS` (the AutoPoll login — from the Login Info folder)
   - `SUPABASE_URL`, `SUPABASE_KEY` (after step 2; leave unset to start with local files only)
3. Same screen → **Variables** tab, add `STORES` = `1512,1515`.
   > Secrets are encrypted and never shown in logs. This is the one time the
   > password is entered — after that the scraper logs in on its own each run.

### 2. Supabase
1. Create a project, open the **SQL editor**, paste `supabase_schema.sql`, run it.
2. Copy the project URL and a service key into the GitHub secrets above.

### 3. Turn it on
The workflow runs automatically on the hourly schedule. To test immediately,
open the **Actions** tab → *Hourly AutoPoll pull* → **Run workflow**. Each run's
raw + parsed captures are attached as a downloadable artifact.

## Run locally (for testing)
```bash
pip install -r requirements.txt
cp .env.example .env        # fill in credentials
export $(grep -v '^#' .env | xargs)
FORCE_RUN=1 python scraper.py   # FORCE_RUN bypasses the open-hours check
```

## Reliability built in
- One login per run, reused across stores; auto re-login if the session expires mid-run.
- Each store is isolated with 3 retries — one bad store won't stop the others.
- Every pull is validated (line-item amounts must sum to the report subtotal).
- The run exits non-zero only if *every* store fails, so GitHub flags real outages
  while tolerating a single hiccup.

## To confirm on the first live run
- That the report sits in a `<pre>` block (the parser handles both `<pre>` and full-page
  text, but the first real HTML pull confirms it).
- The exact login form field names (`UserName` / `Password` assumed). If login fails,
  check the form on `/Account/LogOn` and adjust `login()` in `scraper.py`.
