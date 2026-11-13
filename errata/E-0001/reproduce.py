"""E-0001 — a precomputed pct-change column that disagrees with the prices beside it.

    python errata/E-0001/reproduce.py <bars_dir_or_csv> [--tol-pp 1.0] [--band 0.10]

For every row with close, preclose and a pct-change column (pctChg / pct_chg / change_pct), compare
the column with close/preclose - 1. Reports the share of rows that disagree by more than --tol-pp
percentage points and how many "limit-up" days each method sees at --band. Exit 1 if any row disagrees.
On the bundled sample the vendor column says +11.82% where the prices say +8.26%.
"""
import csv, glob, os, sys

def rows(path):
    paths = [path] if os.path.isfile(path) else sorted(glob.glob(os.path.join(path, "*.csv")))
    for p in paths:
        with open(p, newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                yield os.path.basename(p), r

def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__); return 2
    tol = float(a[a.index("--tol-pp") + 1]) if "--tol-pp" in a else 1.0
    band = float(a[a.index("--band") + 1]) if "--band" in a else 0.10
    n = bad = lu_col = lu_px = 0; ex = []
    for name, r in rows(a[0]):
        col = next((r[k] for k in ("pctChg", "pct_chg", "change_pct") if k in r and r[k] not in ("", None)), None)
        try:
            c, pc = float(r["close"]), float(r.get("preclose") or r.get("prev_close"))
            col = float(col)
        except (TypeError, ValueError, KeyError):
            continue
        if pc <= 0:
            continue
        n += 1
        px = (c / pc - 1) * 100
        if abs(px - col) > tol:
            bad += 1
            if len(ex) < 5:
                ex.append((name, r.get("date"), round(col, 2), round(px, 2)))
        lu_col += col >= band * 100 - 0.2
        lu_px += px >= band * 100 - 0.2
    print(f"rows {n:,}  disagree>{tol}pp {bad:,} ({bad / max(n, 1):.2%})")
    print(f"limit-up days: via column {lu_col:,}  via prices {lu_px:,}  ({(lu_col - lu_px) / max(lu_px, 1):+.1%})")
    for e in ex:
        print("  e.g.", e)
    return 1 if bad else 0

if __name__ == "__main__":
    sys.exit(main())
