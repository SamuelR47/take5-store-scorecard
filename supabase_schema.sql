-- Take 5 daily pricing: table the scraper upserts into, one row per store per hour.
-- Run this once in the Supabase SQL editor after creating your project.

create table if not exists daily_sales_pull (
    id                bigint generated always as identity primary key,
    store_number      text        not null,
    store_name        text,
    report_timestamp  text,                 -- store's last-transaction time from the report
    pull_time         timestamptz not null, -- when the scraper ran
    pull_hour         text        not null, -- 'YYYY-MM-DD-HH' (Central) - dedupe key
    cars              int,
    net_sales         numeric,
    gross_sales       numeric,
    total_receipts    numeric,
    materials_pct     numeric,
    asa               numeric,
    coupons           numeric,
    discounts         numeric,
    new_customers     int,
    repeat_customers  int,
    big4_total_units  int,
    big4_total_amount numeric,
    big4              jsonb,                 -- per-product Big 4 attachment
    line_items        jsonb,                 -- all product/service rows
    data              jsonb,                 -- full parsed payload
    created_at        timestamptz default now(),
    unique (store_number, pull_hour)         -- lets the scraper upsert safely
);

create index if not exists idx_dsp_store_time on daily_sales_pull (store_number, pull_time desc);

-- The dashboard reads the latest row per store like this:
-- select distinct on (store_number) *
--   from daily_sales_pull order by store_number, pull_time desc;
