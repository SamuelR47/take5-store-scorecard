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
    d["cars"]           = int(find(r"Cars\s*:\s*(\d+)", text) or 0)
    d["average"]        = money(find(r"Average\s*:\s*(-?\$[\d,]+\.\d{2})", text))
    d["average_less_coupon"] = money(find(r"Aver-Coup:\s*(-?\$[\d,]+\.\d{2})", text))
    d["materials_amount"] = money(find(r"Materials:\s*(-?\$[\d,]+\.\d{2})", text))
    d["materials_pct"]  = pct(find(r"Materials:\s*-?\$[\d,]+\.\d{2}\s+(\d+)%", text))
    d["asa"]            = money(find(r"ASA\*\s*:\s*(-?\$[\d,]+\.\d{2})", text))
    d["asa_less_coupon"]= money(find(r"ASA\*-Coup:\s*(-?\$[\d,]+\.\d{2})", text))
    d["total"]          = money(find(r"\bTOTAL\s+(-?\$[\d,]+\.\d{2})", text))
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

    lm = re.search(r"LUBE\s+([\d.]+)\s+([\d.]+)\s+(-?\$[\d,]+\.\d{2})\s+(-?\$[\d,]+\.\d{2})\s+([\d.]+)%", text)
    if lm:
        d["labor"] = {
            "hours": float(lm.group(1)),
            "hours_per_car": float(lm.group(2)),
            "cost": money(lm.group(3)),
            "cost_per_car": money(lm.group(4)),
            "pct_of_net": float(lm.group(5)),
        }

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
    if not d.get("line_items"):
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
