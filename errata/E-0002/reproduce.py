"""E-0002 — adjusted prices rounded to ¥0.01 fabricate limit breaches on sub-¥1 securities.

    python errata/E-0002/reproduce.py <adjusted.csv> [<unadjusted.csv>] [--band 0.05]

Prints each day's move from the adjusted file and, if an unadjusted file is given, the same day's
move from exchange prices plus the exact limit price round_half_up(preclose * (1 ± band), 2).
On the bundled sample (sz.000908, June–July 2024, *ST, 5% band) the adjusted file shows +6.17%,
−6.25%, +6.12%; the exchange's prices sit exactly on the limit price every one of those days.
Also demonstrates the arithmetic: at preclose 0.81 the widest move representable within a 5% band
after rounding to 0.01 is 0.85 (+4.94%) — so any 0.86 in a 2-decimal adjusted series is an artefact,
not a trade.
"""
import csv, sys
from decimal import Decimal, ROUND_HALF_UP

def rhu(x, nd=2):
    return float(Decimal(str(x)).quantize(Decimal(10) ** -nd, rounding=ROUND_HALF_UP))

def load(p):
    with open(p, newline="", encoding="utf-8") as fh:
        return {r["date"][:10]: r for r in csv.DictReader(fh)}

def main():
    a = [x for x in sys.argv[1:] if not x.startswith("--")]
    if not a:
        print(__doc__); return 2
    band = float(sys.argv[sys.argv.index("--band") + 1]) if "--band" in sys.argv else 0.05
    adj = load(a[0]); raw = load(a[1]) if len(a) > 1 else {}
    flagged = 0
    print(f"{'date':10s} {'adj close':>9s} {'adj pre':>8s} {'adj chg':>8s} | {'raw close':>9s} {'raw pre':>8s} {'raw chg':>8s} {'limit up':>8s} {'limit dn':>8s}")
    for d, r in sorted(adj.items()):
        c, pc = float(r["close"]), float(r.get("preclose") or r.get("prev_close"))
        chg = c / pc - 1
        over = abs(chg) > band + 0.011
        flagged += over
        line = f"{d:10s} {c:9.2f} {pc:8.2f} {chg * 100:7.2f}% "
        if d in raw:
            rc, rp = float(raw[d]["close"]), float(raw[d]["preclose"])
            line += f"| {rc:9.2f} {rp:8.2f} {(rc / rp - 1) * 100:7.2f}% {rhu(rp * (1 + band)):8.2f} {rhu(rp * (1 - band)):8.2f}"
        print(line + ("   <-- adjusted series breaches band" if over else ""))
    print(f"\nadjusted rows breaching ±{band:.0%} (+1.1pp tol): {flagged}")
    print("arithmetic: preclose 0.81 → widest in-band close after rounding = "
          f"{rhu(0.81 * (1 + band)):.2f} ({(rhu(0.81 * (1 + band)) / 0.81 - 1) * 100:.2f}%); a 2-decimal adjusted 0.86 is +6.17%")
    return 0

if __name__ == "__main__":
    sys.exit(main())
