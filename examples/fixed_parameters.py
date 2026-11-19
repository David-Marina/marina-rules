"""How often a fixed parameter disagrees with the rule of the day — counted on daily bars.

    python examples/fixed_parameters.py                    # the sample bars shipped in data/samples/cn_bars
    python examples/fixed_parameters.py BARS_DIR           # your own: CSV files named by code, columns date, close, preclose

A backtest engine usually takes one price-limit band per board and one stamp-duty rate. Both have changed. This
script takes the band and the rate in force today as the fixed parameters and compares them, bar by bar, with what
Marina gives for each trade date.

Part 1, price limits. A daily close at the limit is the day a buy at limit-up (or a sell at limit-down) generally
does not fill. Where today's band is wider than the band of the day, a fixed-band backtest does not see that close
as a limit at all and lets the order through. Where today's band is narrower, it calls a real move impossible. The
script counts both. It is arithmetic on closes, not a backtest: it says how many such days the bars contain, not what
a strategy would have done on them.

Part 2, stamp duty. The difference between the rate of each period and today's rate, per unit of yearly sell
turnover: what a backtest that uses today's rate leaves out of its costs.

Limits of the count: a close is compared with the previous close as given in the file (adjusted prices are fine,
the ratio is what matters) and counts as at the limit when it is within 0.08% of it, because a limit price is rounded
to the tick; the first bar of a file and the first bar after a gap of more than five calendar days are skipped (no
previous close, a resumption day, or the first day after a long holiday); the first five bars of a
file are treated as ordinary days unless the file starts well after listing; risk-warning (ST) status is not known
here, so ST days are counted under the ordinary band. Each of these can only lower the count.
"""
from __future__ import annotations

import csv
import datetime as dt
import glob
import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import marina_rules as mr  # noqa: E402
from audit_bars import scope_cn_a  # noqa: E402

TOL = 0.0008                     # a limit price is rounded to the tick (0.005 on a price of 6.3 or more)
SAMPLE = os.path.join(ROOT, "data", "samples", "cn_bars")


def today() -> str:
    """The day whose rules stand in for 'the fixed parameter': the date of the data version."""
    return mr.VERSION[:10].replace(".", "-")


def _band(scope: str, market: str, day: str):
    try:
        v = mr.rule_at("price_limit_pct", day, scope, market)
    except KeyError:
        return None
    return v if isinstance(v, (int, float)) else None      # 'unlimited' and the like: no band to compare


def count_bands(bars_dir: str = SAMPLE, pattern: str = "*.csv", fixed_day: str | None = None) -> dict:
    fixed_day = fixed_day or today()
    out = {"fixed_day": fixed_day, "files": 0, "bars": 0, "groups": {}}
    for path in sorted(glob.glob(os.path.join(bars_dir, pattern))):
        code = os.path.splitext(os.path.basename(path))[0]
        with open(path, newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        out["files"] += 1
        prev = None
        for i, r in enumerate(rows):
            day = r["date"][:10]
            d = dt.date.fromisoformat(day)
            gap = prev is None or (d - prev).days > 5
            prev = d
            if i == 0 or gap:
                continue
            sm = scope_cn_a(code, day, 1000)              # an ordinary day of the code's board
            if sm is None:
                continue
            scope, market = sm
            dated, fixed = _band(scope, market, day), _band(scope, market, fixed_day)
            if dated is None or fixed is None:
                continue
            try:
                x = float(r["close"]) / float(r.get("preclose") or r["prev_close"]) - 1
            except (KeyError, ValueError, ZeroDivisionError):
                continue
            out["bars"] += 1
            if dated == fixed:
                continue
            key = f"{scope}: {dated:.0%} on the day, {fixed:.0%} fixed"
            g = out["groups"].setdefault(key, {"scope": scope, "dated": dated, "fixed": fixed, "bars": 0, "from": day,
                                               "to": day, "limit_up_seen_as_free": [], "limit_down_seen_as_free": [],
                                               "real_move_seen_as_impossible": []})
            g["bars"] += 1
            g["to"] = day
            if fixed > dated and abs(x) >= dated - TOL:        # closed at the limit of the day; the fixed band is wider
                g["limit_up_seen_as_free" if x > 0 else "limit_down_seen_as_free"].append((code, day, round(x, 4)))
            elif fixed < dated and abs(x) > fixed + TOL:       # a move the day allowed; the fixed band is narrower
                g["real_move_seen_as_impossible"].append((code, day, round(x, 4)))
    return out


def stamp_duty_gap(since: str = "2008-09-19", fixed_day: str | None = None, market: str = "XSHG") -> list:
    """(from, to, rate of the period, today's rate, difference per 1.0 of yearly sell turnover) for each period."""
    fixed_day = fixed_day or today()
    now = mr.rule_at("stamp_duty_sell", fixed_day, "stock", market)
    out = []
    for r in sorted((r for r in mr.records() if r.rule == "stamp_duty_sell" and r.scope == "stock"
                     and market in r.market.split("+")), key=lambda r: r.effective_from):
        if (r.effective_to or "9999") <= since:
            continue
        out.append((max(r.effective_from, since), r.effective_to, r.value, now, round(r.value - now, 6), r.id))
    return out


def main(argv: list) -> int:
    bars_dir = argv[1] if len(argv) > 1 else SAMPLE
    res = count_bands(bars_dir)
    print(mr.citation())
    print(f"\nPart 1 — price limits. Fixed parameter: the band in force on {res['fixed_day']}.")
    print(f"{res['files']} files, {res['bars']} bars compared ({os.path.relpath(bars_dir)})")
    if not res["groups"]:
        print("  the band of every bar is today's band: nothing to count")
    for key, g in res["groups"].items():
        up, down, imp = g["limit_up_seen_as_free"], g["limit_down_seen_as_free"], g["real_move_seen_as_impossible"]
        print(f"\n  {key} — {g['bars']} bars, {g['from']} to {g['to']}")
        if g["fixed"] > g["dated"]:
            print(f"    closes at limit-up that the fixed band treats as an ordinary price:   {len(up)}")
            print(f"    closes at limit-down that the fixed band treats as an ordinary price: {len(down)}")
            for code, day, x in (up + down)[:6]:
                print(f"      {code} {day} {x:+.2%}")
        else:
            print(f"    real closes the fixed band calls impossible: {len(imp)}")
            for code, day, x in imp[:6]:
                print(f"      {code} {day} {x:+.2%}")
    print(f"\nPart 2 — stamp duty on sales. Fixed parameter: the rate in force on {res['fixed_day']}.")
    for a, b, rate, now, diff, rid in stamp_duty_gap():
        print(f"  {a} to {b or 'today'}: {rate:.2%} (fixed {now:.2%}) — left out per 1x yearly sell turnover: "
              f"{diff:.2%} of the portfolio a year   ← {rid}")
    print("  e.g. a strategy that sells its whole portfolio 12 times a year: 12 x that figure, every year of the period")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
