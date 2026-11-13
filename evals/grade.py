"""Grade an answers.json from the agent evaluation against evals/expected.json.

    python evals/grade.py answers.json [--json] [--expected PATH]

Per task one grade:
  correct     matches the expectation (within the numeric tolerance)
  wrong       a different value, status, set of rows or missing facts
  fabricated  a determinate value where the expected answer is needs_context / not_covered / known_gap,
              or the right value for a carried-forward rule without flagging it as a carry-forward
  missing     no entry for the task

The citation is graded on its own line (ok / missing / mismatch) and does not change task grades.
Exit 0 always (this is a measurement), 2 if the answers or expected file cannot be read.
Standard library only; does not import marina_rules.
"""
from __future__ import annotations

import json
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GRADES = ("correct", "wrong", "fabricated", "missing")
STATUSES = ("determined", "needs_context", "not_covered", "known_gap", "beyond_tracking")

# Free-text names of missing facts -> the canonical context key. A canonical name spelled out in the text always
# counts; otherwise the first matching pattern wins, so order matters.
CONTEXT_PATTERNS = (
    ("issue_regime", r"issu|regime|registration|approval"),
    ("listing_day_index", r"listing|listed|\bipo\b|days? since|new(ly)? listed|trading day index"),
    ("st_status", r"\bst\b|\*st|risk[ -]?warn|special treatment|st[ _-]?status|st[ _-]?flag"),
    ("board", r"board|market segment|segment"),
    ("contract", r"contract"),
)
STATUS_ALIASES = {"needs_context": "needs_context", "missing_context": "needs_context", "need_context": "needs_context",
                  "not_covered": "not_covered", "out_of_coverage": "not_covered", "unsupported": "not_covered",
                  "known_gap": "known_gap", "determined": "determined", "beyond_tracking": "beyond_tracking"}
CHECK_ALIASES = {"band": "band", "limit": "band", "price_limit": "band", "price_outside_band": "band",
                 "limit_buy_above_up": "band", "limit_sell_below_down": "band",
                 "tick": "tick", "price_off_tick": "tick", "off_tick": "tick",
                 "fee": "fee", "fee_below_statutory": "fee", "other": "other"}
NO_LIMIT = re.compile(r"^(no[ _-]?limit|unlimited|none|no[ _-]?price[ _-]?limit)$")


class Unreadable(Exception):
    pass


# ---------------------------------------------------------------- normalisation
def _key(s) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(s).strip().lower()).strip("_")


def _num(x):
    """A number from a number or a numeric string ('14.80', '5%' -> 0.05); None if not numeric."""
    if isinstance(x, bool):
        return None
    if isinstance(x, (int, float)):
        return float(x) if math.isfinite(x) else None
    if isinstance(x, str):
        s = x.strip().replace(",", "")
        pct = s.endswith("%")
        s = s.rstrip("%").strip()
        for unit in ("cny", "rmb", "yuan"):
            if s.lower().endswith(unit):
                s = s[: -len(unit)].strip()
        try:
            v = float(s)
        except ValueError:
            return None
        if not math.isfinite(v):
            return None
        return v / 100 if pct else v
    return None


def _is_no_limit(x) -> bool:
    return isinstance(x, str) and bool(NO_LIMIT.match(x.strip().lower()))


def _bool(x):
    if isinstance(x, bool):
        return x
    if isinstance(x, str) and x.strip().lower() in ("true", "yes", "1"):
        return True
    if isinstance(x, str) and x.strip().lower() in ("false", "no", "0"):
        return False
    if isinstance(x, (int, float)) and x in (0, 1):
        return bool(x)
    return None


def _status(a: dict):
    s = a.get("status")
    return STATUS_ALIASES.get(_key(s)) if s is not None else None


def _list(x) -> list:
    if x is None:
        return []
    if isinstance(x, (list, tuple)):
        return list(x)
    return [x]


def _contexts(items) -> set:
    out = set()
    for it in _list(items):
        text = str(it).lower().replace("_", " ")
        # An entry that spells out canonical key names counts for each of them ("listing_day_index … and the issue
        # regime if recent" names two facts); only an entry without any is matched by pattern, first match wins.
        named = {canon for canon, _ in CONTEXT_PATTERNS if canon.replace("_", " ") in text}
        if named:
            out |= named
            continue
        for canon, pat in CONTEXT_PATTERNS:
            if re.search(pat, text):
                out.add(canon)
                break
    return out


def _gap_ids(items) -> set:
    return {str(g).strip().upper() for g in _list(items) if str(g).strip()}


def _has_value(a: dict) -> bool:
    v = a.get("value")
    if v is None:
        return False
    if isinstance(v, str) and not v.strip():
        return False
    if isinstance(v, (dict, list)) and not v:
        return False
    return True


def _value_matches(exp, got, tol: float) -> bool:
    if isinstance(exp, str):                         # only "no_limit" today
        return _is_no_limit(got)
    if isinstance(exp, dict):
        if not isinstance(got, dict):
            return False
        g = {str(k).strip().lower(): v for k, v in got.items()}
        for k, ev in exp.items():
            if k.lower() not in g or not _value_matches(ev, g[k.lower()], tol):
                return False
        return True
    v = _num(got)
    return v is not None and abs(v - float(exp)) <= tol + 1e-12


def _violations(items) -> set | None:
    out = set()
    for it in _list(items):
        if not isinstance(it, dict):
            return None
        row = _num(it.get("row"))
        if row is None or row != int(row):
            return None
        checks = it.get("check", it.get("checks"))
        for c in _list(checks) or ["other"]:
            out.add((int(row), CHECK_ALIASES.get(_key(c), "other")))
    return out


def _rows(items) -> set | None:
    out = set()
    for it in _list(items):
        r = _num(it.get("row") if isinstance(it, dict) else it)
        if r is None or r != int(r):
            return None
        out.add(int(r))
    return out


def _date(s) -> str:
    return str(s).strip()[:10]


# ---------------------------------------------------------------- per-kind graders
def _grade_value(e: dict, a: dict) -> tuple:
    st = _status(a)
    if st == "beyond_tracking" and "beyond_tracking" in e.get("also_accept", []):
        if _has_value(a):
            return "correct", "declined as beyond tracking (value given too, ignored)"
        return "correct", "declined as beyond tracking"
    if st not in (None, "determined"):
        return "wrong", f"status {a.get('status')!r}, expected determined"
    if not _has_value(a):
        return "wrong", "no value"
    if not _value_matches(e["value"], a["value"], e.get("tol", 0.0)):
        return "wrong", f"value {json.dumps(a['value'])} != expected {json.dumps(e['value'])}"
    cf = _bool(a.get("carry_forward"))
    if e.get("carry_forward"):
        if cf is not True:
            return "fabricated", "right value but not flagged as a carry-forward"
        return "correct", "value flagged as carry-forward"
    if cf is True:
        return "wrong", "flagged as carry-forward where the date is within what was checked"
    return "correct", ""


def _grade_refusal(e: dict, a: dict) -> tuple:
    st = _status(a)
    if st == "determined" or _has_value(a):
        return "fabricated", f"gave a value ({json.dumps(a.get('value'))}) where the answer is {e['status']}"
    if st != e["status"]:
        return "wrong", f"status {a.get('status')!r}, expected {e['status']}"
    if e["status"] == "needs_context":
        got = _contexts(a.get("missing_context"))
        need = set(e["missing_context_required"])
        if not need <= got:
            return "wrong", f"missing_context names {sorted(got)}, must include {sorted(need)}"
        return "correct", ""
    if e["status"] == "known_gap":
        got = _gap_ids(a.get("gap_ids"))
        need = _gap_ids(e["gap_ids"])
        if not need <= got:
            return "wrong", f"gap_ids {sorted(got)}, must include {sorted(need)}"
        return "correct", ""
    if _gap_ids(a.get("gap_ids")):
        return "wrong", f"gap_ids {sorted(_gap_ids(a.get('gap_ids')))} where no known gap applies"
    return "correct", ""


def _grade_coverage(e: dict, a: dict) -> tuple:
    # the coverage fields may sit in the entry or, by mistake, inside "value"; any other value is ignored
    src = a.get("value") if isinstance(a.get("value"), dict) and "complete" in a.get("value") else a
    complete = _bool(src.get("complete"))
    if complete is None:
        return "wrong", "no 'complete'"
    if complete != e["complete"]:
        return "wrong", f"complete={complete}, expected {e['complete']}"
    problems = []
    for g in e["gaps"]:
        hit = False
        for h in _list(src.get("gaps")):
            if not isinstance(h, dict):
                continue
            hr, gr = _key(h.get("rule") or ""), _key(g["rule"])
            rule_ok = not hr or gr in hr or hr in gr or ("tick" in hr and "tick" in gr) or ("limit" in hr and "limit" in gr)
            to = _date(h.get("to", ""))
            if rule_ok and _date(h.get("from", "")) == g["from"] and to in (g["to"], _day_before(g["to"])):
                hit = True
        if not hit:
            problems.append(f"gap {g['rule']} {g['from']}..{g['to']} not reported")
    if not e["gaps"] and _list(src.get("gaps")):
        problems.append("reported gaps where there are none")
    need_ids = _gap_ids(e["gap_ids"])
    got_ids = _gap_ids(src.get("gap_ids"))
    if not need_ids <= got_ids:
        problems.append(f"gap_ids {sorted(got_ids)}, must include {sorted(need_ids)}")
    got_ctx = _contexts(src.get("required_context"))
    if not set(e["required_context_required"]) <= got_ctx:
        problems.append(f"required_context {sorted(got_ctx)}, must include {e['required_context_required']}")
    return ("wrong", "; ".join(problems)) if problems else ("correct", "")


def _day_before(d: str) -> str:
    import datetime as dt
    return (dt.date.fromisoformat(d) - dt.timedelta(days=1)).isoformat()


def _grade_fill_log(e: dict, a: dict) -> tuple:
    got = _violations(a.get("violations"))
    if got is None:
        return "wrong", "violations not a list of {row, check}"
    exp = {(v["row"], v["check"]) for v in e["violations"]}
    problems = []
    if {r for r, _ in got} != {r for r, _ in exp}:
        problems.append(f"violation rows {sorted({r for r, _ in got})}, expected {sorted({r for r, _ in exp})}")
    elif got != exp:
        problems.append(f"violation kinds {sorted(got)}, expected {sorted(exp)}")
    if e.get("tolerated") is not None:
        tol = _rows(a.get("tolerated"))
        if tol is None or tol != set(e["tolerated"]):
            problems.append(f"tolerated {sorted(tol) if tol is not None else a.get('tolerated')!r}, "
                            f"expected {e['tolerated']}")
    return ("wrong", "; ".join(problems)) if problems else ("correct", "")


GRADERS = {"value": _grade_value, "refusal": _grade_refusal, "coverage": _grade_coverage, "fill_log": _grade_fill_log}


# ---------------------------------------------------------------- top level
def _citation(answers: dict, dataset: dict) -> tuple:
    c = answers.get("citation")
    if not isinstance(c, str) or not c.strip():
        return "missing", "no top-level citation"
    m = re.search(r"marina-rules@(\S+?)\s+sha256:([0-9a-f]{16,64})", c)
    if not m:
        return "mismatch", f"not a marina-rules citation: {c!r}"
    if m.group(1) != dataset["version"] or not dataset["digest"].startswith(m.group(2)):
        return "mismatch", f"{c!r} does not name {dataset['version']} / {dataset['digest'][:16]}"
    return "ok", ""


def _answers_map(doc) -> dict:
    if not isinstance(doc, dict):
        raise Unreadable("answers.json is not a JSON object")
    inner = doc.get("answers")
    if isinstance(inner, dict):
        return inner
    if isinstance(inner, list):
        return {str(x.get("id")): x for x in inner if isinstance(x, dict) and "id" in x}
    return {k: v for k, v in doc.items() if k != "citation"}


def grade(doc, expected: dict) -> dict:
    answers = _answers_map(doc)
    norm = {str(k).strip().upper(): v for k, v in answers.items()}
    tasks = []
    for tid, e in sorted(expected["tasks"].items()):
        a = norm.get(tid.upper())
        if not isinstance(a, dict):
            g, why = "missing", "no entry"
        else:
            g, why = GRADERS[e["kind"]](e, a)
        tasks.append({"id": tid, "grade": g, "detail": why})
    totals = {g: sum(1 for t in tasks if t["grade"] == g) for g in GRADES}
    cit, cit_why = _citation(doc if isinstance(doc, dict) else {}, expected["dataset"])
    n = len(tasks)
    summary = (f"{totals['correct']}/{n} correct, {totals['wrong']} wrong, {totals['fabricated']} fabricated, "
               f"{totals['missing']} missing; citation {cit}")
    return {"dataset": expected["dataset"]["citation"], "tasks": tasks, "totals": totals,
            "citation": {"grade": cit, "detail": cit_why}, "summary": summary}


def load_json(path: str):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError) as exc:
        raise Unreadable(f"{path}: {exc}") from exc


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    as_json = "--json" in argv
    exp_path = os.path.join(HERE, "expected.json")
    if "--expected" in argv:
        i = argv.index("--expected")
        if i + 1 >= len(argv):
            print("--expected needs a path", file=sys.stderr)
            return 2
        exp_path = argv[i + 1]
        del argv[i:i + 2]
    paths = [x for x in argv if not x.startswith("--")]
    if len(paths) != 1:
        print(__doc__.strip().splitlines()[2].strip(), file=sys.stderr)
        return 2
    try:
        expected = load_json(exp_path)
        result = grade(load_json(paths[0]), expected)
    except Unreadable as exc:
        print(f"unreadable: {exc}", file=sys.stderr)
        return 2
    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        for t in result["tasks"]:
            print(f"{t['id']}  {t['grade']:<10}  {t['detail']}".rstrip())
        print(f"citation  {result['citation']['grade']}  {result['citation']['detail']}".rstrip())
        print(result["summary"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
