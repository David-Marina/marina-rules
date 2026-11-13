"""E-0003 — the standard bonus-share formula gives the wrong reference price on reorganisation conversions.

    python errata/E-0003/reproduce.py <unadjusted.csv> <ex_date> <ratio>

<unadjusted.csv> is a daily series with date, close and preclose (preclose = the exchange's basis for
the day's price limit). <ratio> is the share-change ratio of the conversion as an event table would
record it: new shares per old share, as a decimal or a fraction (e.g. 2205000000/1854853500).
Prints the previous close, the exchange's reference price on <ex_date> (its preclose), the standard
formula round(prev_close / (1 + ratio), 2) and the factor between them. Exit 1 if the exchange's price
and the standard-formula price differ by more than one tick (¥0.01), 0 otherwise.

Bundled samples (baostock, adjustflag=3):
  sh.600715_unadjusted_baostock_2024-12.csv 2024-12-16 2205000000/1854853500
      prev close 2.45, exchange 2.12, standard formula 1.12, factor 1.893 -> exit 1
  sz.000908_unadjusted_baostock_2026-03.csv 2026-03-11 879774351/879774351
      prev close 6.37, exchange 4.36, standard formula 3.19, factor 1.367 -> exit 1
"""
import csv, sys
from decimal import Decimal, ROUND_HALF_UP
from fractions import Fraction

def rhu(x, nd=2):
    return float(Decimal(str(x)).quantize(Decimal(10) ** -nd, rounding=ROUND_HALF_UP))

def main():
    a = sys.argv[1:]
    if len(a) != 3:
        print(__doc__); return 2
    path, ex, ratio = a[0], a[1][:10], float(Fraction(a[2]))
    with open(path, newline="", encoding="utf-8") as fh:
        rows = sorted((r["date"][:10], r) for r in csv.DictReader(fh))
    i = next((k for k, (d, _) in enumerate(rows) if d == ex), None)
    if i is None or i == 0:
        print(f"{ex}: not in file, or no row before it"); return 2
    prev_d, prev = rows[i - 1]
    pc = float(prev["close"]); ref = float(rows[i][1]["preclose"])
    std = rhu(pc / (1 + ratio))
    print(f"previous close     {prev_d}  {pc:8.2f}")
    print(f"exchange reference {ex}  {ref:8.2f}   (preclose on the ex-date)")
    print(f"standard formula   {ex}  {std:8.2f}   = {pc:.2f} / (1 + {ratio:.6f})")
    print(f"implied factor     exchange / standard = {ref / std:.4f}")
    bad = abs(ref - std) > 0.01 + 1e-9
    print("-> differ by more than one tick: every price before the ex-date rebuilt with the standard"
          f" formula is off by x{ref / std:.4f}" if bad else "-> agree within one tick")
    return 1 if bad else 0

if __name__ == "__main__":
    sys.exit(main())
