"""Consistency audit: rules × market data.

A price-limit rule makes a falsifiable claim: after ``effective_from``, no daily close may move more
than the limit from the previous close (ignoring the first listing days and unlimited scopes).
Given daily bars, this script counts violations per rule. A violation means either the rule is wrong
or the data is bad — both are worth knowing. This is how Marina was first audited against
9.1 million A-share bars (docs/audit-2026-10-24.md).

Usage:
    python scripts/audit_bars.py BARS_DIR --pattern '*.csv' [--scope-fn cn_a]

Bars CSV needs columns: date, close, preclose (or prev_close). Vendor pct-change columns are ignored on purpose. Code is taken
from the filename stem. The first bar after a gap of more than 5 calendar days (suspension / resumption)
is skipped — no daily limit applies on resumption day, and suspension lists are outside Marina's scope.
Only a sample dataset ships with this repository (data/samples/); point it at your own bars.
"""
from __future__ import annotations

import argparse
import csv
import glob
import os
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import marina_rules as mr  # noqa: E402


# First trading day under the 5-day no-band IPO regime, per board (a listing ON or AFTER this date gets
# ipo_first5_*; a listing before it gets the day-1-only band ipo_day1_main and the ordinary band from day 2).
# STAR has had the 5-day regime since its first listing day (2019-07-22). Sources: the price_limit_pct records
# cn.limit.ipo_first5.chinext.2020-08-24, cn.limit.ipo_first5.main.2023-04-10, cn.limit.ipo_first5.star.2019-07-22.
FIRST5_FROM = {"chinext": "2020-08-24", "main_board": "2023-04-10", "star": "2019-07-22"}


def scope_cn_a(code: str, date: str, row_index: int, is_st: bool | None = None,
               listing_date: str | None = None) -> tuple[str, str] | None:
    """Map a Chinese A-share code to (scope, market). Returns None for codes we don't classify, and for
    listing-window rows whose regime cannot be told (see ``listing_date``).

    ``row_index`` is the number of bars *since listing* (0 = listing day). If your file does not start at the listing
    date, pass ``--complete-from-listing`` only when it does; otherwise newly-listed scopes are never
    assigned and early rows audit against the regular band (which can over-count, so we skip them).
    ``listing_date`` is the date of the listing-day bar. The IPO regime is decided by the LISTING date, not the row's
    date: a main-board stock listed 2023-04-07 is a day-1-only (ipo_day1_main) listing even though its 2nd–5th days fall
    after 2023-04-10. When ``row_index == 0`` the row's own date is the listing date; for rows 1..4 without
    ``listing_date`` the regime is ambiguous only if the row is on/after the cutoff, and those rows return None.
    ``is_st`` is the security's point-in-time risk-warning status ON THAT DATE (an ``isST`` column in
    the bars). None = unknown: ST days then audit against the non-ST band, which can only under-count.
    A static "is ST today" column backfilled over history is worse than None — do not pass it."""
    num = code.split(".")[-1]
    if listing_date is None and row_index == 0:
        listing_date = date

    def window(board: str) -> str | None:
        """'first5' / 'day1' / 'ordinary', or None when the regime cannot be determined."""
        if row_index >= 5:
            return "ordinary"
        cut = FIRST5_FROM[board]
        if listing_date is not None:
            first5 = listing_date >= cut
        elif date < cut:
            first5 = False          # listed no later than this row, so before the cutoff too
        else:
            return None             # row after the cutoff, listing date unknown: cannot tell the regime
        if first5:
            return "first5"
        return "day1" if row_index == 0 else "ordinary"

    if num.startswith("688"):
        w = window("star")
        if w is None:
            return None
        if w == "first5":
            return ("ipo_first5_star", "XSHG")
        return ("st_star", "XSHG") if is_st else ("star", "XSHG")
    if num.startswith(("300", "301")):
        w = window("chinext")
        if w is None:
            return None
        if w == "first5":
            return ("ipo_first5_chinext", "XSHE")
        if w == "day1":
            return ("ipo_day1_main", "XSHE")
        return ("st_chinext", "XSHE") if is_st else ("chinext", "XSHE")
    if num.startswith(("60", "00")):
        w = window("main_board")
        if w is None:
            return None
        if w == "first5":
            return ("ipo_first5_main", "XSHG+XSHE")
        if w == "day1":
            return ("ipo_day1_main", "XSHG+XSHE")
        return ("st_main", "XSHG+XSHE") if is_st else ("main_board", "XSHG+XSHE")
    return None


def audit(paths: list[str], tol: float = 0.011, complete_from_listing: bool = False, use_st: bool = False) -> dict:
    checked = Counter(); viol = Counter(); examples = defaultdict(list)
    for p in paths:
        code = os.path.splitext(os.path.basename(p))[0]
        with open(p, newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        prev_date = None
        # Does this file start at the listing date? Heuristic: if the first row has a vendor preclose
        # that is far from its close (forward-adjustment artefact at history start) or the first date
        # equals a common vendor history start, it does NOT. We require --complete-from-listing AND the
        # first row's |close/preclose - 1| < 50% to treat row 0 as listing day.
        starts_at_listing = False
        if complete_from_listing and rows:
            try:
                c0 = float(rows[0].get("close")); p0 = float(rows[0].get("preclose") or rows[0].get("prev_close"))
                starts_at_listing = p0 > 0 and abs(c0 / p0 - 1) < 0.5
            except (TypeError, ValueError):
                starts_at_listing = False
        for i, r in enumerate(rows):
            d = str(r.get("date", ""))[:10]
            # Resumption after a suspension (> 5 calendar days with no bar): no daily limit applies on
            # the first bar back; also skip when the vendor's preclose is missing. Lists of suspended /
            # delisting-period securities are out of Marina's scope, so we infer from the gap.
            gap_days = None
            if prev_date:
                try:
                    import datetime as _dt
                    gap_days = (_dt.date.fromisoformat(d) - _dt.date.fromisoformat(prev_date)).days
                except ValueError:
                    gap_days = None
            prev_date = d
            if gap_days is not None and gap_days > 5:
                continue
            # Always recompute from close / preclose. Vendor pct-change columns are frequently stale
            # (computed under a different adjustment than the prices beside them) — see errata.
            pc = r.get("preclose") or r.get("prev_close"); c = r.get("close")
            try:
                pc, c = float(pc), float(c)
            except (TypeError, ValueError):
                continue
            if pc <= 0:
                continue

            if not starts_at_listing and i < 5:
                continue  # unknown listing date: first rows may be IPO days, skip rather than mis-flag
            st_raw = r.get("isST")
            is_st = None if st_raw in (None, "") else str(st_raw).strip() in ("1", "1.0", "True", "true")
            if not use_st:
                is_st = None
            sm = scope_cn_a(code, d, i if starts_at_listing else 10**6, is_st,
                            listing_date=str(rows[0].get("date", ""))[:10] if starts_at_listing else None)
            if sm is None:
                continue
            scope, market = sm
            try:
                rec = mr.record_at("price_limit_pct", d, scope, market)
            except KeyError:
                continue
            checked[rec.id] += 1
            v = rec.value
            if v == "unlimited":
                continue
            up = v["up"] if isinstance(v, dict) else v
            dn = v["down"] if isinstance(v, dict) else v
            chg = c / pc - 1
            if chg > up + tol or chg < -(dn + tol):
                viol[rec.id] += 1
                if len(examples[rec.id]) < 5:
                    examples[rec.id].append((code, d, round(chg * 100, 2)))
    return {"checked": dict(checked), "violations": dict(viol), "examples": dict(examples),
            "citation": mr.citation()}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bars_dir"); ap.add_argument("--pattern", default="*.csv")
    ap.add_argument("--complete-from-listing", action="store_true",
                    help="bars start at each security's listing date (enables IPO-day scopes)")
    ap.add_argument("--use-st", action="store_true",
                    help="trust the bars' isST column as POINT-IN-TIME status and audit ST days against the ST band. "
                         "Only pass this if isST is per-day history, not today's status backfilled.")
    a = ap.parse_args()
    paths = sorted(glob.glob(os.path.join(a.bars_dir, a.pattern)))
    if not paths:
        print("no bar files found", file=sys.stderr); return 2
    out = audit(paths, complete_from_listing=a.complete_from_listing, use_st=a.use_st)
    print(out["citation"])
    print(f"{'rule id':48s} {'checked':>10s} {'violations':>11s}  rate")
    for rid, n in sorted(out["checked"].items()):
        v = out["violations"].get(rid, 0)
        print(f"{rid:48s} {n:>10,} {v:>11,}  {v / n:.4%}")
        for ex in out["examples"].get(rid, []):
            print(f"    e.g. {ex}")
    return 1 if out["violations"] else 0


if __name__ == "__main__":
    sys.exit(main())
