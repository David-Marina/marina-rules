"""Build evals/expected.json (and evals/TASKS.md) from the library, so the expectations follow the data.

    python evals/build_expected.py           # rewrite expected.json and TASKS.md
    python evals/build_expected.py --check   # exit 1 if either file differs from a fresh build

Every expected value below comes from a call into marina_rules; the per-task ``judgement`` states the behaviour the
grader enforces where the expectation is not just a number (refuse, flag, name the missing facts).
"""
from __future__ import annotations

import csv
import json
import os
import sys

import marina_rules as mr
from marina_rules.check import check_rows, statutory_fee_floor
from marina_rules.contract import capabilities, resolve

HERE = os.path.dirname(os.path.abspath(__file__))
TASKS = os.path.join(HERE, "tasks.json")
EXPECTED = os.path.join(HERE, "expected.json")
TASKS_MD = os.path.join(HERE, "TASKS.md")
FILES = os.path.join(HERE, "files")

# Numeric tolerances (absolute), by quantity. Documented in README.md.
TOL_PRICE = 0.001      # prices have 2 decimals: a one-cent rounding error (0.01) is wrong
TOL_RATE = 1e-9        # fractions recorded exactly in the data
TOL_CNY = 0.01         # fee amounts: one cent
TOL_PER_LOT = 1e-6     # CNY per lot, recorded exactly

SEASONED = 1000        # "listed several years earlier": far past any listing window


def _status(d: dict) -> str:
    s = d["status"]
    if s == "DETERMINED":
        return "determined"
    if s == "MISSING_CONTEXT":
        return "needs_context"
    if s == "OUT_OF_COVERAGE":
        return "known_gap" if d["known_gap_ids"] else "not_covered"
    if s == "BEYOND_TRACKING":
        return "beyond_tracking"
    raise AssertionError(f"unexpected status {s} for {d['rule']} {d['trade_date']}: {d['reason']}")


def _carry_forward(d: dict) -> bool:
    return bool(d["warnings"]) and any(w.startswith("CARRY_FORWARD") for w in d["warnings"])


def _determined(rule, date, scope, market, ctx=None) -> dict:
    d = resolve(rule, date, scope, market, ctx or {})
    assert d["status"] == "DETERMINED", (rule, date, scope, d["reason"])
    return d


def _limit_up_price(prev_close, scope, date, market, ctx) -> tuple:
    d = _determined("price_limit_pct", date, scope, market, ctx)
    lp = mr.limit_price(prev_close, scope, date, market)
    return d, (None if lp is None else lp[0]), lp


def _rows(name: str) -> list:
    with open(os.path.join(FILES, name), newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


_KIND = {"LIMIT_BUY_ABOVE_UP": "band", "LIMIT_SELL_BELOW_DOWN": "band", "PRICE_OUTSIDE_BAND": "band",
         "PRICE_OFF_TICK": "tick", "FEE_BELOW_STATUTORY": "fee"}


def _violations(out: dict) -> list:
    v = set()
    for r in out["row_status"]:
        if r["status"] == "findings":
            for c in r["checks"]:
                v.add((r["row"], _KIND.get(c, "other")))
    return [{"row": r, "check": k} for r, k in sorted(v)]


def build() -> dict:
    tasks = {}

    # T01 ChiNext band: 10% through 2020-08-21, 20% from 2020-08-24. 13.45 * 1.1 = 14.795 -> half-up 14.80.
    ctx = {"board": "chinext", "st_status": False, "listing_day_index": SEASONED}
    v, cf = {}, False
    for day in ("2020-08-21", "2020-08-24"):
        d, up, _ = _limit_up_price(13.45, "chinext", day, "XSHE", ctx)
        v[day] = up; cf = cf or _carry_forward(d)
    tasks["T01"] = {"kind": "value", "status": "determined", "value": v, "tol": TOL_PRICE, "carry_forward": cf,
                    "derivation": "limit_price(13.45, 'chinext', day, 'XSHE')[0] for each day; resolve() DETERMINED with "
                                  "board=chinext, st_status=false, a seasoned listing_day_index",
                    "judgement": "the band changes on 2020-08-24, not before; exchange half-up rounding (14.795 -> 14.80)"}

    # T02 ST main board, 5% before 2026-07-06; 4.305 / 3.895 differ under half-up vs round().
    ctx = {"board": "main_board", "st_status": True}
    d = _determined("price_limit_pct", "2024-06-14", "st_main", "XSHG", ctx)
    up, dn = mr.limit_price(4.10, "st_main", "2024-06-14", "XSHG")
    tasks["T02"] = {"kind": "value", "status": "determined", "value": {"limit_up": up, "limit_down": dn}, "tol": TOL_PRICE,
                    "carry_forward": _carry_forward(d),
                    "derivation": "limit_price(4.10, 'st_main', '2024-06-14', 'XSHG')",
                    "judgement": "half-up rounding: 4.305 -> 4.31 and 3.895 -> 3.90 (Python round() gives 4.3 / 3.89)"}

    # T03 registration-regime ChiNext IPO, day 3: unlimited.
    ctx = {"board": "chinext", "st_status": False, "listing_day_index": 3, "issue_regime": "registration"}
    d, up, lp = _limit_up_price(30.00, "ipo_first5_chinext", "2024-03-05", "XSHE", ctx)
    assert lp is None
    tasks["T03"] = {"kind": "value", "status": "determined", "value": "no_limit", "carry_forward": _carry_forward(d),
                    "derivation": "limit_price(30.00, 'ipo_first5_chinext', '2024-03-05', 'XSHE') is None; resolve() "
                                  f"DETERMINED value {d['result']['value']!r}",
                    "judgement": "the answer is 'no price limit', not a number"}

    # T04 stamp duty, sell side.
    v, cf = {}, False
    for day in ("2023-08-25", "2023-08-28"):
        d = _determined("stamp_duty_sell", day, "stock", "XSHG+XSHE")
        v[day] = d["result"]["value"]; cf = cf or _carry_forward(d)
    tasks["T04"] = {"kind": "value", "status": "determined", "value": v, "tol": TOL_RATE, "carry_forward": cf,
                    "derivation": "rule_at('stamp_duty_sell', day) / resolve(..., 'stock', 'XSHG+XSHE')",
                    "judgement": "the halving applies from 2023-08-28, not before"}

    # T05 statutory fee floor of one sell fill.
    floor = statutory_fee_floor(86420.00, "sell", "2023-08-28", "XSHG")
    d = _determined("transfer_fee_each_side", "2023-08-28", "stock", "XSHG")
    tasks["T05"] = {"kind": "value", "status": "determined", "value": round(floor, 6), "tol": TOL_CNY,
                    "carry_forward": _carry_forward(d),
                    "derivation": "marina_rules.check.statutory_fee_floor(86420.00, 'sell', '2023-08-28', 'XSHG') "
                                  "(stamp duty of the sell side + transfer fee, both on turnover)",
                    "judgement": "the new stamp duty rate applies on 2023-08-28"}

    # T06 only a code and a date: ST status and listing-day index are unknown.
    d = resolve("price_limit_pct", "2024-06-14", "main_board", "XSHG", {"board": "main_board"})
    assert _status(d) == "needs_context"
    tasks["T06"] = {"kind": "refusal", "status": "needs_context",
                    "missing_context_required": sorted(d["missing_context"]),
                    "missing_context_allowed": ["board", "issue_regime"],
                    "derivation": "resolve('price_limit_pct', '2024-06-14', 'main_board', 'XSHG', {'board': 'main_board'}) "
                                  f"-> MISSING_CONTEXT {d['missing_context']} (the board follows from the code)",
                    "judgement": "no number: ST status decides 5% vs 10% and a listing window would mean no limit; the "
                                 "answer must name both missing facts"}

    # T07 DCE is not covered at all.
    d = resolve("price_limit_pct_of_prev_settlement", "2025-03-03", "dce_m", "XDCE")
    assert _status(d) == "not_covered", d
    assert not [s for s in capabilities()["scopes"] if s.startswith("dce")]
    assert not [r.id for r in mr.records() if "XDCE" in (r.market or "")]
    tasks["T07"] = {"kind": "refusal", "status": "not_covered", "gap_ids": [],
                    "derivation": "resolve('price_limit_pct_of_prev_settlement', '2025-03-03', 'dce_m', 'XDCE') -> "
                                  "OUT_OF_COVERAGE, no known gap; no DCE scope or record in the dataset",
                    "judgement": "no number; not a known gap either (an invented gap id is wrong)"}

    # T08 a registered gap.
    d = resolve("margin_ratio", "2026-04-15", "shfe_cu", "XSGE")
    assert _status(d) == "known_gap", d
    tasks["T08"] = {"kind": "refusal", "status": "known_gap", "gap_ids": d["known_gap_ids"],
                    "derivation": f"resolve('margin_ratio', '2026-04-15', 'shfe_cu', 'XSGE') -> OUT_OF_COVERAGE, "
                                  f"known_gap_ids {d['known_gap_ids']} (same with a contract)",
                    "judgement": "no number; report the known gap and its id"}

    # T09 coverage pre-flight.
    rules = ["price_limit_pct", "tick_size"]
    cov = mr.coverage("XSHG", "st_main", rules, "2004-01-01", "2012-01-01")
    tasks["T09"] = {"kind": "coverage", "complete": cov["status"] == "complete",
                    "gaps": [{"rule": g["rule"], "from": g["from"], "to": g["to"]} for g in cov["gaps"]],
                    "gap_ids": cov["known_gap_ids"],
                    "required_context_required": [k for k in cov["required_context"] if k != "board"],
                    "required_context_allowed": ["board"],
                    "derivation": "coverage('XSHG', 'st_main', ['price_limit_pct', 'tick_size'], '2004-01-01', "
                                  f"'2012-01-01') -> {cov['status']}, required_context {cov['required_context']}",
                    "judgement": "not complete: name the missing stretch and its known gap id; ST status must be "
                                 "supplied per security and day (the board is implied by the task)"}

    # T10 exchange fills, strict.
    out = check_rows(_rows("fills_exchange.csv"), strict=False, per_row=True)
    tasks["T10"] = {"kind": "fill_log", "violations": _violations(out), "tolerated": None,
                    "derivation": "python -m marina_rules.check fills_exchange.csv --rows",
                    "judgement": "row 3 is fine only because the 20% band starts 2020-08-24; row 4 only under half-up "
                                 "rounding; row 7 only because of the SZSE one-tick floor; row 6 only because the new "
                                 "stamp duty applies from 2023-08-28; row 8 is in an unlimited listing window"}

    # T11 model prices: relaxed run, 0.3% band tolerance, no tick check.
    out = check_rows(_rows("fills_model.csv"), tick=False, band_tolerance_pct=0.3, per_row=True)
    tasks["T11"] = {"kind": "fill_log", "violations": _violations(out),
                    "tolerated": sorted(r["row"] for r in out["row_status"] if r["status"] == "within_tolerance"),
                    "derivation": "python -m marina_rules.check fills_model.csv --no-tick --band-tolerance-pct 0.3 --rows",
                    "judgement": "off-tick prices are not violations here; rows beyond a limit by <= 0.3% are tolerated, "
                                 "not violations; row 7 is tolerated only under the pre-2020-08-24 10% ChiNext band"}

    # T12 beyond the tracked-through date of SHFE.
    d = _determined("trans_fee_rate", "2026-11-10", "shfe_cu", "XSGE")
    assert _carry_forward(d) and d["tracking"]["beyond"] is True
    tasks["T12"] = {"kind": "value", "status": "determined", "value": d["result"]["value"], "tol": TOL_RATE,
                    "carry_forward": True, "also_accept": ["beyond_tracking"],
                    "derivation": "resolve('trans_fee_rate', '2026-11-10', 'shfe_cu', 'XSGE') -> DETERMINED with "
                                  f"warning {d['warnings']}, tracked_through {d['tracking']['tracked_through']}",
                    "judgement": "the value must come flagged as a carry-forward (or be declined as beyond tracking)"}

    # T13 an untracked market.
    d = _determined("price_limit_pct_of_prev_settlement", "2025-06-03", "cffex_if", "CCFX")
    assert _carry_forward(d) and d["tracking"]["tracked_through"] is None
    tasks["T13"] = {"kind": "value", "status": "determined", "value": d["result"]["value"], "tol": TOL_RATE,
                    "carry_forward": True, "also_accept": ["beyond_tracking"],
                    "derivation": "resolve('price_limit_pct_of_prev_settlement', '2025-06-03', 'cffex_if', 'CCFX') -> "
                                  f"DETERMINED with warning {d['warnings']} (CCFX is not tracked)",
                    "judgement": "the value must come flagged as a carry-forward (or be declined as beyond tracking)"}

    # T14 fee by contract.
    v, cf = {}, False
    for c in ("au2509", "au2510"):
        d = _determined("trans_fee_per_lot", "2025-07-10", "shfe_au", "XSGE", {"contract": c})
        v[c] = d["result"]["value"]; cf = cf or _carry_forward(d)
    assert resolve("trans_fee_per_lot", "2025-07-10", "shfe_au", "XSGE")["missing_context"] == ["contract"]
    assert v["au2509"] != v["au2510"]
    tasks["T14"] = {"kind": "value", "status": "determined", "value": v, "tol": TOL_PER_LOT, "carry_forward": cf,
                    "derivation": "resolve('trans_fee_per_lot', '2025-07-10', 'shfe_au', 'XSGE', {'contract': c})",
                    "judgement": "the two contracts are in different fee tiers; one value for both is wrong"}

    with open(TASKS, encoding="utf-8") as fh:
        ids = [t["id"] for t in json.load(fh)["tasks"]]
    assert ids == sorted(tasks), (ids, sorted(tasks))
    return {"eval_version": 1,
            "dataset": {"version": mr.VERSION, "digest": mr.dataset_digest(), "citation": mr.citation(short=False)},
            "tolerances": {"price": TOL_PRICE, "rate": TOL_RATE, "cny": TOL_CNY, "cny_per_lot": TOL_PER_LOT},
            "tasks": tasks}


def _brief(e: dict) -> str:
    k = e["kind"]
    if k == "value":
        s = f"`determined`: {json.dumps(e['value'])}"
        if e.get("carry_forward"):
            s += ", flagged as carry-forward (or `beyond_tracking`)"
        return s
    if k == "refusal":
        if e["status"] == "needs_context":
            return f"`needs_context`: must name {', '.join(e['missing_context_required'])}"
        if e["status"] == "known_gap":
            return f"`known_gap`: {', '.join(e['gap_ids'])}"
        return "`not_covered`"
    if k == "coverage":
        g = "; ".join(f"{x['rule']} {x['from']} → {x['to']}" for x in e["gaps"])
        return (f"complete={str(e['complete']).lower()}; gaps: {g or 'none'}; gap ids: {', '.join(e['gap_ids']) or 'none'}; "
                f"context: {', '.join(e['required_context_required'])}")
    v = ", ".join(f"row {x['row']} {x['check']}" for x in e["violations"]) or "none"
    s = f"violations: {v}"
    if e.get("tolerated") is not None:
        s += f"; tolerated rows: {', '.join(map(str, e['tolerated'])) or 'none'}"
    return s


def render_tasks_md(expected: dict) -> str:
    with open(TASKS, encoding="utf-8") as fh:
        spec = json.load(fh)
    lines = ["# Agent evaluation tasks", "",
             "Generated by `evals/build_expected.py` from `tasks.json` and `expected.json`; do not edit by hand.",
             "The assistant under test sees only `tasks.json`; this page shows the expected answers too.", "",
             f"Dataset: `{expected['dataset']['citation']}`", "",
             "General instructions given to the assistant:", ""]
    lines += [f"- {s}" for s in spec["instructions"]]
    lines.append("")
    for t in spec["tasks"]:
        e = expected["tasks"][t["id"]]
        lines += [f"## {t['id']} · {t['title']}", "", t["question"], "",
                  f"*Return:* {t['return']}", "",
                  f"*Expected:* {_brief(e)}", "",
                  f"*Why:* {e['judgement']}.", "",
                  f"*Derived from:* `{e['derivation']}`", ""]
    return "\n".join(lines)


def _dump(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    exp = build()
    files = {EXPECTED: _dump(exp), TASKS_MD: render_tasks_md(exp)}
    if "--check" in argv:
        stale = []
        for path, text in files.items():
            try:
                with open(path, encoding="utf-8") as fh:
                    if fh.read() != text:
                        stale.append(os.path.basename(path))
            except FileNotFoundError:
                stale.append(os.path.basename(path))
        if stale:
            print("stale: " + ", ".join(stale) + " (run python evals/build_expected.py)")
            return 1
        print("expected.json and TASKS.md are current")
        return 0
    for path, text in files.items():
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
    print(f"wrote {os.path.basename(EXPECTED)} and {os.path.basename(TASKS_MD)} for {exp['dataset']['citation']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
