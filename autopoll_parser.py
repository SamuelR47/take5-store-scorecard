"""
Parse an AutoPoll 'CURRENT SALES REPORT' into structured data.
Parsing core for the hourly scraper. Input = report text; output = dict/JSON
with every scorecard field, including Big 4 attachment.
"""
import re, json, sys

# Big 4 products (code -> canonical name), per Take 5 definition.
BIG4 = {"2": "Air Filter", "6": "Wiper Blade", "8": "Cabin Filter", "9": "Coolant Exchange"}


def money(s):
    """'$1,234.56' or '-$9.04' -> float."""
    if s is None:
        return None
    s = s.strip().replace(",", "").replace("$", "")
    neg = s.startswith("-")
    s = s.lstrip("-+")
    try:
        v = float(s)
    except ValueError:
        return None
    return -v if neg else v


def pct(s):
    return None if s is None else float(s.strip().replace("%", ""))


def find(pattern, text, group=1, flags=0):
    m = re.search(pattern, text, flags)
    return m.group(group) if m else None


def _int_total(text, pattern):
    """Match a two-column '<Above> <Total>' int line; return Total (2nd) if
    present, else the single value. Pattern must have g1=Above, g2=Total?."""
    m = re.search(pattern, text)
    if not m:
        return 0
    val = m.group(2) if m.lastindex and m.lastindex >= 2 and m.group(2) else m.group(1)
    return int(val)


def _money_total(text, pattern):
    """Money version of _int_total: prefer the 2nd (Total) column when present."""
    m = re.search(pattern, text)
    if not m:
        return None
    val = m.group(2) if m.lastindex and m.lastindex >= 2 and m.group(2) else m.group(1)
    return money(val)


def num(s):
    """'26.83', '$0.00', '0.00%', '-$9.04' or blank -> float or None."""
    if s is None:
        return None
    s = s.strip().replace(",", "").replace("$", "").replace("%", "")
    if s in ("", "-"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


# A value token in the LABOR block: hours/percentages/dollars, e.g. "26.83",
# "1.17", "$0.00", "-$9.04", "4.20%". Used to find where the (possibly
# multi-word) profit-center name ends and the numeric columns begin. The
# scraped text collapses the report's aligned columns to single spaces, so we
# split on tokens rather than column widths.
_LABOR_VAL = re.compile(r"^-?\$?[\d,]*\.?\d+%?$")
_LABOR_KEYS = ["hours", "hours_per_car", "cost", "cost_per_car", "pct_of_net"]


def parse_labor(text):
    """Parse the LABOR block into a list of per-profit-center dicts.

    Returns [] when the block is absent (older reports / partial pulls).
    Handles multiple profit centers, multi-word names (e.g. "STATE INSP"),
    $/% signs, and $0.00 / blank values.
    """
    # Isolate the block: from the "LABOR for" header past its dashed separator,
    # up to the ancillary footnote (or end of report). Anchoring avoids matching
    # stray lines elsewhere in the report.
    m = re.search(
        r"LABOR\s+for.*?-{3,}\s*\n(?P<body>.*?)(?:\n\s*\*Ancillary|\Z)",
        text, re.S | re.I,
    )
    if not m:
        return []

    centers = []
    for line in m.group("body").splitlines():
        toks = line.split()
        if not toks:
            continue
        # Name = leading non-numeric tokens; values start at the first number.
        idx = next((i for i, t in enumerate(toks) if _LABOR_VAL.match(t)), None)
        if not idx:  # None (no values) or 0 (no name) -> header/separator/blank
            continue
        name = " ".join(toks[:idx]).strip().rstrip("-").strip()
        if not name or name.lower() in ("profit center", "total", "hours"):
            continue
        vals = toks[idx:]
        row = {"profit_center": name}
        for i, k in enumerate(_LABOR_KEYS):
            row[k] = num(vals[i]) if i < len(vals) else None
        centers.append(row)
    return centers


def labor_summary(centers):
    """Collapse per-center rows into the single `labor` dict the dashboard reads.

    Single center -> that row's values. Multiple -> summed hours/cost/pct, with
    per-car figures re-derived from the summed hours/cost. Empty -> {}.
    """
    if not centers:
        return {}
    if len(centers) == 1:
        c = centers[0]
        return {k: c.get(k) for k in
                ("hours", "hours_per_car", "cost", "cost_per_car", "pct_of_net")}

    def total(key):
        vals = [c.get(key) for c in centers if c.get(key) is not None]
        return round(sum(vals), 2) if vals else None

    hours, cost, pct = total("hours"), total("cost"), total("pct_of_net")
    # cars = hours / hours_per_car per row, summed, to re-derive blended per-car.
    cars = sum((c["hours"] / c["hours_per_car"])
               for c in centers
               if c.get("hours") and c.get("hours_per_car"))
    return {
        "hours": hours,
        "hours_per_car": round(hours / cars, 2) if (hours and cars) else None,
        "cost": cost,
        "cost_per_car": round(cost / cars, 2) if (cost is not None and cars) else None,
        "pct_of_net": pct,
    }


def parse_report(text):
    d = {}

    m = re.search(r"(\d{1,2}/\d{1,2}/\d{4}\s+\d{1,2}:\d{2}\s*[AP]M)\s+Store\s*#\s*(\d+)\s+(.+?)\s+Page", text)
    if m:
        d["report_timestamp"] = m.group(1).strip()
        d["store_number"] = m.group(2).strip()
        d["store_name"] = m.group(3).strip()

    products = []
    line_re = re.compile(
        r"^\s*(\d+)\s+([A-Za-z].*?)_*\s+(\d+)\s+(\d+)%\s+(-?\$[\d,]+\.\d{2})\s+(-?\d+)%\s*$",
        re.M,
    )
    for mm in line_re.finditer(text):
        products.append({
            "code": mm.group(1),
            "description": mm.group(2).strip().rstrip("_ ").strip(),
            "units": int(mm.group(3)),
            "units_pct": pct(mm.group(4)),
            "amount": money(mm.group(5)),
            "amount_pct": pct(mm.group(6)),
        })
    d["line_items"] = products

    d["sub_total"]      = money(find(r"Sub Total\s+(-?\$[\d,]+\.\d{2})", text))
    d["coupons"]        = money(find(r"Coupons\s+(-?\$[\d,]+\.\d{2})", text))
    d["discounts"]      = money(find(r"Discounts\s+(-?\$[\d,]+\.\d{2})", text))

    # --- Cars / Average: use the TOTAL column, not the "Above $X" column ---
    # The report prints two side-by-side columns under an "Above $X.XX  Total"
    # header. The threshold ($8.99, $15.00, ...) varies by store, so we match
    # the DUAL-column shape structurally and take the SECOND value (Total).
    # Fall back to a single value for older/one-column reports.
    d["cars"]    = _int_total(text, r"Cars\s*:\s*(\d+)(?:\s+(\d+))?")
    d["average"] = _money_total(
        text, r"Average\s*:\s*(-?\$[\d,]+\.\d{2})(?:\s+(-?\$[\d,]+\.\d{2}))?")
    d["average_less_coupon"] = _money_total(
        text, r"Aver-Coup:\s*(-?\$[\d,]+\.\d{2})(?:\s+(-?\$[\d,]+\.\d{2}))?")

    d["materials_amount"] = money(find(r"Materials:\s*(-?\$[\d,]+\.\d{2})", text))
    d["materials_pct"]  = pct(find(r"Materials:\s*-?\$[\d,]+\.\d{2}\s+(\d+)%", text))

    # Full-service count + dollars, e.g. "Full Serv: $121.41 7"
    m_fs = re.search(r"Full Serv:\s*(-?\$[\d,]+\.\d{2})\s+(\d+)", text)
    d["full_serv_amount"] = money(m_fs.group(1)) if m_fs else None
    d["full_serv_count"]  = int(m_fs.group(2)) if m_fs else None
    d["full_serv"] = ({"count": d["full_serv_count"], "amount": d["full_serv_amount"]}
                      if m_fs else None)

    d["asa"]            = money(find(r"ASA\*\s*:\s*(-?\$[\d,]+\.\d{2})", text))
    d["asa_less_coupon"]= money(find(r"ASA\*-Coup:\s*(-?\$[\d,]+\.\d{2})", text))
    # Anchor to line start so "Sub Total" / "TOTAL RECEIPTS" / "TOTAL CUSTOMERS"
    # can never be mistaken for the standalone NET-of-discounts TOTAL line.
    d["total"]          = money(find(r"^TOTAL\s+(-?\$[\d,]+\.\d{2})", text, flags=re.M))
    d["net_sales"]      = money(find(r"NET SALES\s+(-?\$[\d,]+\.\d{2})", text))
    d["sales_tax"]      = money(find(r"SALES TAX\s+(-?\$[\d,]+\.\d{2})", text))
    d["gross_sales"]    = money(find(r"GROSS SALES\s+(-?\$[\d,]+\.\d{2})", text))
    d["total_receipts"] = money(find(r"TOTAL RECEIPTS\s+(-?\$[\d,]+\.\d{2})", text))

    d["new_customers"]    = int(find(r"NEW CUSTOMERS\s+(\d+)", text) or 0)
    d["new_customers_pct"]= pct(find(r"NEW CUSTOMERS\s+\d+\s*-\s*(\d+)%", text))
    d["repeat_customers"] = int(find(r"REPEAT CUSTOMERS\s+(\d+)", text) or 0)
    d["repeat_customers_pct"] = pct(find(r"REPEAT CUSTOMERS\s+\d+\s*-\s*(\d+)%", text))
    d["total_customers"]  = int(find(r"TOTAL CUSTOMERS\s+(\d+)", text) or 0)

    d["time_opened"] = find(r"TIME OPENED\s*:\s*([\d:]+\s*[AP]M)", text)
    d["time_closed"] = find(r"TIME CLOSED\s*:\s*([\d:]+\s*[AP]M)", text)
    d["fleets_count"] = int(find(r"-\(\s*(\d+)\)\s*Fleets", text) or 0)
    d["fleets_amount"] = money(find(r"Fleets\s+(-?\$[\d,]+\.\d{2})", text))

    d["voids"]    = int(find(r"Voids:\s*(\d+)", text) or 0)
    d["reprints"] = int(find(r"Reprints:\s*(\d+)", text) or 0)
    d["cancels"]  = int(find(r"Cancels:\s*(\d+)", text) or 0)

    centers = parse_labor(text)
    d["labor_by_center"] = centers
    d["labor"] = labor_summary(centers)

    # ---- Big 4 attachment (Air Filter, Wiper Blade, Cabin Filter, Coolant Exchange) ----
    cars = d.get("cars") or 0
    big4 = {}
    for code, name in BIG4.items():
        rows = [li for li in products if li["code"] == code]
        units = sum(r["units"] for r in rows)
        amount = sum((r["amount"] or 0) for r in rows)
        big4[name] = {
            "code": code,
            "units": units,
            "amount": round(amount, 2),
            "attach_pct": round(units / cars * 100, 1) if cars else None,  # units per car
        }
    d["big4"] = big4
    d["big4_total_units"] = sum(v["units"] for v in big4.values())
    d["big4_total_amount"] = round(sum(v["amount"] for v in big4.values()), 2)
    return d


def validate(d):
    problems = []
    if not d.get("store_number"):
        problems.append("no store number parsed")
    # Only flag missing line items when there's evidence of activity. A store that is
    # open but hasn't rung anything up yet (early morning) legitimately has no product
    # rows; treating that as a failure red-X'd the whole hourly run and saved nothing.
    # With cars/net both empty, an empty report is valid -> a zero row is upserted.
    if not d.get("line_items") and (d.get("cars") or d.get("net_sales")):
        problems.append("no line items parsed")
    if d.get("net_sales") is None:
        problems.append("net_sales missing")
    if d.get("line_items") and d.get("sub_total") is not None:
        s = sum(li["amount"] for li in d["line_items"] if li["amount"] is not None)
        if abs(s - d["sub_total"]) > 0.02:
            problems.append(f"line items sum {s:.2f} != sub_total {d['sub_total']:.2f}")
    return problems


if __name__ == "__main__":
    for path in sys.argv[1:]:
        data = parse_report(open(path).read())
        probs = validate(data)
        print(f"\n===== {path} =====")
        print(json.dumps(data, indent=2))
        print("VALIDATION:", "OK" if not probs else probs)
