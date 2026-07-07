"""Pure forecast + transform logic (spec section 9). No Streamlit, no network -
so it is fully unit-testable. Ported verbatim from the proven app, then extended
with the Target (norm x 1.10) and a single per-metric data contract (build_metric)."""
import datetime as dt
import statistics
from config import (HOURS, RECENCY_W, MAD_K, PACE_CLAMP, TARGET_MULT, RATE_KEYS,
                    NAVY, GREEN, AMBER, RED, INK)


# ---- time / status ----
def frac_elapsed(now):
    o, c = HOURS[now.weekday()]
    span = (c - o) or 1
    return max(0.0, min(1.0, ((now.hour + now.minute / 60) - o) / span))


def pace_state(actual, expected):
    """Single source of truth for ahead/on-pace/behind (measured vs the TRUE norm)."""
    if expected is None or expected == 0 or actual is None:
        return ("no goal", INK, None)
    ratio = actual / expected
    if ratio >= 1.0:
        return ("ahead of pace", GREEN, True)
    if ratio >= 0.90:
        return ("on pace", AMBER, False)
    return ("behind pace", RED, False)


# ---- holidays (norm must exclude these) ----
def _nth_weekday(year, month, weekday, n):
    if n > 0:
        d = dt.date(year, month, 1)
        return d + dt.timedelta(days=((weekday - d.weekday()) % 7) + 7 * (n - 1))
    d = (dt.date(year, 12, 31) if month == 12
         else dt.date(year, month + 1, 1) - dt.timedelta(days=1))
    return d - dt.timedelta(days=((d.weekday() - weekday) % 7))


def us_holidays(year):
    fixed = [dt.date(year, 1, 1), dt.date(year, 6, 19), dt.date(year, 7, 4),
             dt.date(year, 11, 11), dt.date(year, 12, 25)]
    floating = [_nth_weekday(year, 1, 0, 3), _nth_weekday(year, 2, 0, 3),
                _nth_weekday(year, 5, 0, -1), _nth_weekday(year, 9, 0, 1),
                _nth_weekday(year, 10, 0, 2), _nth_weekday(year, 11, 3, 4)]
    out = set(fixed) | set(floating)
    for d in fixed:
        if d.weekday() == 5:
            out.add(d - dt.timedelta(days=1))
        elif d.weekday() == 6:
            out.add(d + dt.timedelta(days=1))
    return out


def is_holiday(d):
    return bool(d) and d in us_holidays(d.year)


# ---- row parsing / metric extraction ----
def row_date(row):
    parts = (row.get("pull_hour") or "").split("-")
    return "-".join(parts[:3]) if len(parts) >= 3 else None


def row_hour(row):
    parts = (row.get("pull_hour") or "").split("-")
    try:
        return int(parts[3]) if len(parts) >= 4 else None
    except ValueError:
        return None


def labor_block(row):
    data = row.get("data") or {}
    return data.get("labor") or row.get("labor") or {}


def get_metric(row, key):
    if key == "aro":
        cars = row.get("cars") or 0
        net = row.get("net_sales")
        return (net / cars) if (cars and net is not None) else None
    if key == "lhpc":
        cars = row.get("cars") or 0
        hrs = labor_block(row).get("hours")
        if hrs is not None and cars:
            return hrs / cars
        return labor_block(row).get("hours_per_car")
    if key == "labor_hours":
        return labor_block(row).get("hours")
    return row.get(key)


def cum_by_hour(rows, key):
    out = {}
    for r in sorted(rows, key=lambda x: x.get("pull_time") or ""):
        h = row_hour(r)
        if h is None:
            continue
        v = get_metric(r, key)
        if v is not None:
            out[h] = float(v)
    return out


def to_per_period(cum):
    if not cum:
        return {}
    pp, prev = {}, 0.0
    for h in sorted(cum):
        pp[h] = cum[h] - prev
        prev = cum[h]
    return pp


def to_per_period_metric(cum, key):
    return dict(cum) if key in RATE_KEYS else to_per_period(cum)


# ---- baselines (section 9) ----
def reject_outliers(values, k=MAD_K):
    if not values:
        return [], []
    med = statistics.median(values)
    thresh = k * statistics.median([abs(x - med) for x in values])
    kept, idx = [], []
    for i, x in enumerate(values):
        if abs(x - med) <= thresh:
            kept.append(x); idx.append(i)
    return (kept, idx) if kept else (list(values), list(range(len(values))))


def hour_baselines(history_rows, weekday, key, exclude_date=None):
    """Holiday-clean recency-weighted per-hour TRUE norm. Returns {hour: value}."""
    by_date = {}
    for r in history_rows:
        d = row_date(r)
        if d:
            by_date.setdefault(d, []).append(r)
    dated = []
    for d, rows in by_date.items():
        try:
            date = dt.date.fromisoformat(d)
        except (ValueError, TypeError):
            continue
        if exclude_date and d == exclude_date:
            continue          # never let today's partial day pollute the norm
        if date.weekday() == weekday and not is_holiday(date):
            dated.append((date, rows))
    dated.sort(key=lambda t: t[0], reverse=True)
    dated = dated[:len(RECENCY_W)]
    if not dated:
        return {}
    per_date_pp = [to_per_period_metric(cum_by_hour(rows, key), key) for _, rows in dated]
    out = {}
    for h in sorted({h for pp in per_date_pp for h in pp}):
        vals_ord, w_ord = [], []
        for i, pp in enumerate(per_date_pp):
            v = pp.get(h)
            if v is not None:
                vals_ord.append(v)
                w_ord.append(RECENCY_W[i] if i < len(RECENCY_W) else RECENCY_W[-1])
        if not vals_ord:
            continue
        kept, idx = reject_outliers(vals_ord)
        num = sum(w_ord[i] * vals_ord[i] for i in idx)
        den = sum(w_ord[i] for i in idx)
        out[h] = (num / den) if den else statistics.fmean(kept)
    return out


def pace_factor(actual_by_hour, baseline_by_hour, completed_hours, clamp=PACE_CLAMP):
    num = sum(actual_by_hour.get(h, 0) for h in completed_hours)
    den = sum(baseline_by_hour.get(h, 0) for h in completed_hours if baseline_by_hour.get(h))
    if not den:
        return None
    return max(clamp[0], min(clamp[1], num / den))


def forecast_hours(hours, today_pp, base_hours):
    """Projection uses the TRUE norm x pace. Returns (actual, projected, pace, completed)."""
    completed = sorted(today_pp)
    last = completed[-1] if completed else None
    future = [h for h in hours if (last is None or h > last)]
    pace = pace_factor(today_pp, base_hours, completed) if base_hours else None
    p = pace if pace is not None else 1.0
    projected = {h: base_hours[h] * p for h in future if base_hours.get(h) is not None}
    return dict(today_pp), projected, pace, completed


def target_curve(norm_by_hour):
    """Target = true norm x TARGET_MULT (stretch goal; display only)."""
    return {h: v * TARGET_MULT for h, v in norm_by_hour.items()}


def build_metric(key, rows, hist, hours, weekday, daily_norm=None):
    """THE data contract: everything a chart/section needs for one metric.
    norm/target/projected/pace all derived here so the UI never recomputes."""
    today_date = row_date(rows[-1]) if rows else None
    base_h = hour_baselines(hist, weekday, key, exclude_date=today_date)
    today_cum = cum_by_hour(rows, key)
    today_pp = to_per_period_metric(today_cum, key)
    actual, projected, pace, completed = forecast_hours(hours, today_pp, base_h)
    target = target_curve(base_h)

    is_rate = key in RATE_KEYS
    if is_rate:                       # rate metric: "so far" = latest cumulative rate
        so_far = today_cum[max(today_cum)] if today_cum else None
        norm_close = statistics.fmean(list(base_h.values())) if base_h else daily_norm
        proj_close = so_far if so_far is not None else norm_close
    else:
        so_far = sum(today_pp.values()) if today_pp else 0
        norm_close = (sum(base_h.values()) if base_h else None) or daily_norm
        proj_close = (so_far + sum(projected.values())) if (base_h or projected) else so_far
    target_close = (norm_close * TARGET_MULT) if norm_close else None
    now_hour = completed[-1] if completed else None
    # expected-by-now uses the TRUE norm (never the target)
    expected_now = sum(base_h.get(h, 0) for h in completed) if (base_h and completed) else (
        daily_norm * (len(completed) / len(hours)) if (daily_norm and hours) else None)

    return {
        "key": key, "hours": hours, "now_hour": now_hour,
        "norm": base_h, "target": target,
        "actual": actual, "projected": projected,
        "pace": pace, "so_far": so_far,
        "norm_close": norm_close, "target_close": target_close, "proj_close": proj_close,
        "expected_now": expected_now, "is_rate": is_rate,
    }


def rank_stores(store_stats):
    return sorted(store_stats, key=lambda s: (s.get("pct") is None, -(s.get("pct") or 0)))
