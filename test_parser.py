"""
Dry-run tests for autopoll_parser. No network, no Supabase.

Runs the parser against every raw sample it can find, asserts each report's
line-item amounts sum to Sub Total, prints a per-store table (cars, net,
labor, validation) to eyeball before writing to the DB, and proves the
cars/average fix now reads the TOTAL column (not the "Above $X" column).

    python3 test_parser.py
"""
import glob, os, sys
import autopoll_parser as ap

HERE = os.path.dirname(os.path.abspath(__file__))
# Look in the repo and in the sibling "Hourly Data Pull/raw" tree.
SEARCH = [
    os.path.join(HERE, "**", "*.txt"),
    os.path.join(HERE, "..", "Hourly Data Pull", "raw", "**", "*.txt"),
]


def find_samples():
    seen, out = set(), []
    for pat in SEARCH:
        for p in glob.glob(pat, recursive=True):
            if os.path.basename(p).lower() == "readme.txt":
                continue
            rp = os.path.realpath(p)
            if rp not in seen and "CURRENT SALES REPORT" in open(p, errors="ignore").read():
                seen.add(rp)
                out.append(p)
    return sorted(out)


def dry_run():
    samples = find_samples()
    if not samples:
        print("No raw samples found — skipping file-based tests.")
        return 0

    print(f"\n{'store':>6} {'name':<16} {'cars':>4} {'net_sales':>10} "
          f"{'avg':>8} {'fs#':>4} {'labor_hrs':>9} {'hpc':>5}  validation")
    print("-" * 86)

    failures = 0
    for path in samples:
        d = ap.parse_report(open(path).read())
        probs = ap.validate(d)

        # Hard assert: line items must reconcile to Sub Total.
        if d.get("line_items") and d.get("sub_total") is not None:
            s = sum(li["amount"] for li in d["line_items"] if li["amount"] is not None)
            assert abs(s - d["sub_total"]) <= 0.02, (
                f"{path}: line sum {s:.2f} != sub_total {d['sub_total']:.2f}")

        lab = d.get("labor") or {}
        print(f"{d.get('store_number','?'):>6} {str(d.get('store_name',''))[:16]:<16} "
              f"{d.get('cars',0):>4} {d.get('net_sales') or 0:>10.2f} "
              f"{d.get('average') or 0:>8.2f} {d.get('full_serv_count') or 0:>4} "
              f"{lab.get('hours') or 0:>9} {lab.get('hours_per_car') or 0:>5}  "
              f"{'OK' if not probs else probs}")
        if probs:
            failures += 1

    print(f"\nline-item==Sub Total: PASS for all {len(samples)} reports")
    return failures


# --- Synthetic proof that we read the TOTAL column, not "Above $X" ---
SYNTHETIC = """CURRENT SALES REPORT
7/6/2026 11:00 AM Store # 9999 Testville Page 1
Code Description Units % Amount % / $
---- --------------------------- ----- ---- ----------- -----
1 DURAMAX FULL SYN___________ 5 100% $500.00 100%
__________________
Sub Total $500.00
Above $15.00 Total
Cars : 5 8 - Coupons $0.00
Average : $100.00 $62.50
Aver-Coup: $100.00 $62.50 - Discounts $0.00
Materials: $0.00 0%
Full Serv: $62.50 8
ASA* : $0.00
__________________
TOTAL $500.00
__________________
NET SALES $500.00
GROSS SALES $500.00
TOTAL RECEIPTS $500.00
LABOR for Total Hours Total Cost % of
Profit Center Hours /Car Cost /Car Net
------------- ------ ------ ---------- ------- ------
LUBE 8.00 1.00 $0.00 $0.00 0.00%
*Ancillary Sales Average: additional sales other than Full Services.
"""


def prove_total_column():
    d = ap.parse_report(SYNTHETIC)
    print("\n=== Above-vs-Total proof (synthetic: Above=5 cars, Total=8 cars) ===")
    print(f"  cars                -> {d['cars']}   (old parser grabbed 5 'Above', want 8 'Total')")
    print(f"  average             -> {d['average']}  (want 62.50, not 100.00)")
    print(f"  average_less_coupon -> {d['average_less_coupon']}  (want 62.50)")
    print(f"  full_serv           -> {d['full_serv']}")
    print(f"  total               -> {d['total']}   (must NOT be Sub Total 500 via 'Sub Total', or RECEIPTS)")
    assert d["cars"] == 8, "cars should read the Total column (8)"
    assert d["average"] == 62.50, "average should read the Total column"
    assert d["average_less_coupon"] == 62.50
    assert d["full_serv"] == {"count": 8, "amount": 62.50}
    assert d["total"] == 500.00
    print("  PASS: Total column used for cars/average; full_serv captured; TOTAL anchored.")


if __name__ == "__main__":
    prove_total_column()
    rc = dry_run()
    sys.exit(1 if rc else 0)
