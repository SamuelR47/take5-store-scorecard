-- Take 5 Scorecard V4 — new tables for write-back interactivity.
-- Run once in the Supabase SQL editor (additive; does NOT touch daily_sales_pull).
-- Posture note: RLS is intentionally LEFT OFF here to match the existing setup
-- (daily_sales_pull is read with the anon key and no policies). The app enforces
-- access at the tier-login layer, not in the database. When the security-hardening
-- item is picked up, enable RLS on these three tables and add real policies — a
-- starting template is at the bottom of this file (commented out). Until then,
-- anyone with the anon key can write, so keep the key out of source.

-- ---------------------------------------------------------------------------
-- B. store_targets — admin-set % boost per store per norm-based metric.
--    New target = metric's 4-week average x (1 + boost_pct/100).
--    Only the norm-based metrics use this (cars, net, big4); ARO ($125) and
--    LHPC (1.10) stay flat and are NOT stored here.
-- ---------------------------------------------------------------------------
create table if not exists store_targets (
    id           bigint generated always as identity primary key,
    store_number text        not null,
    metric       text        not null,           -- 'cars' | 'net' | 'big4'
    boost_pct    numeric     not null default 0,  -- e.g. 10 = target is 4-wk avg +10%
    updated_by   text,                            -- attribution (tier-code + typed name)
    updated_at   timestamptz not null default now(),
    unique (store_number, metric)                 -- one boost per store per metric (upsert key)
);
create index if not exists idx_store_targets_store on store_targets (store_number);

-- ---------------------------------------------------------------------------
-- C. task_completions — a store manager checking off a daily task.
--    One row = one task marked complete for one store on one date.
-- ---------------------------------------------------------------------------
create table if not exists task_completions (
    id           bigint generated always as identity primary key,
    store_number text        not null,
    task_date    date        not null,            -- the day the task belongs to (Central)
    task         text        not null,            -- task label from the weekly planner
    completed_by text,                            -- attribution
    completed_at timestamptz not null default now(),
    unique (store_number, task_date, task)        -- idempotent check-off (upsert key)
);
create index if not exists idx_task_completions_store_date on task_completions (store_number, task_date);

-- ---------------------------------------------------------------------------
-- E. messages — admin -> store/DM messaging. to_scope routes the message;
--    to_store is set only when the target is a single store.
-- ---------------------------------------------------------------------------
create table if not exists messages (
    id         bigint generated always as identity primary key,
    from_user  text        not null,              -- attribution (admin + typed name)
    to_scope   text        not null,              -- 'store' | 'district' | 'all'
    to_store   text,                              -- store_number or DM code; null for 'all'
    body       text        not null,
    sent_at    timestamptz not null default now(),
    read_at    timestamptz                        -- null until the recipient opens it
);
create index if not exists idx_messages_target on messages (to_scope, to_store, sent_at desc);

-- ---------------------------------------------------------------------------
-- Security-hardening template (leave commented until the security item lands):
-- alter table store_targets    enable row level security;
-- alter table task_completions enable row level security;
-- alter table messages         enable row level security;
-- -- then add policies granting the intended roles the intended verbs, e.g.:
-- -- create policy tc_insert on task_completions for insert to authenticated with check (true);
-- ---------------------------------------------------------------------------
