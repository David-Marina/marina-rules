"""Agent evaluation (evals/): expected answers follow the data, and the grader grades its own reference files right."""
from __future__ import annotations

import copy
import importlib.util
import json
import os
import subprocess
import sys

import pytest

import marina_rules as mr

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
EVALS = os.path.join(ROOT, "evals")


def _load(name):
    spec = importlib.util.spec_from_file_location(f"evals_{name}", os.path.join(EVALS, f"{name}.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


build = _load("build_expected")
grade = _load("grade")

with open(os.path.join(EVALS, "expected.json"), encoding="utf-8") as fh:
    EXPECTED = json.load(fh)


def oracle(expected: dict) -> dict:
    """An answers.json written straight from expected.json."""
    out = {}
    for tid, e in expected["tasks"].items():
        k = e["kind"]
        if k == "value":
            out[tid] = {"status": "determined", "value": e["value"], "carry_forward": e["carry_forward"]}
        elif k == "refusal":
            a = {"status": e["status"]}
            if e["status"] == "needs_context":
                a["missing_context"] = list(e["missing_context_required"])
            if e["status"] == "known_gap":
                a["gap_ids"] = list(e["gap_ids"])
            out[tid] = a
        elif k == "coverage":
            out[tid] = {"status": "determined", "complete": e["complete"], "gaps": e["gaps"], "gap_ids": e["gap_ids"],
                        "required_context": e["required_context_required"]}
        else:
            a = {"status": "determined", "violations": e["violations"]}
            if e.get("tolerated") is not None:
                a["tolerated"] = e["tolerated"]
            out[tid] = a
    return {"citation": expected["dataset"]["citation"], "answers": out}


# The classic mistakes, and the grade each must get. Tasks not listed keep the oracle answer.
NAIVE = {
    "T01": ({"status": "determined", "value": {"2020-08-21": 16.14, "2020-08-24": 16.14}, "carry_forward": False},
            "wrong"),                                                    # 20% before 2020-08-24
    "T02": ({"status": "determined", "value": {"limit_up": round(4.10 * 1.05, 2), "limit_down": round(4.10 * 0.95, 2)},
             "carry_forward": False}, "wrong"),                          # round() instead of half-up
    "T03": ({"status": "determined", "value": 36.0, "carry_forward": False}, "wrong"),   # a number in the listing window
    "T06": ({"status": "determined", "value": 22.0, "carry_forward": False}, "fabricated"),  # assumed non-ST, seasoned
    "T07": ({"status": "determined", "value": 0.04, "carry_forward": False}, "fabricated"),  # guessed for DCE
    "T08": ({"status": "determined", "value": 0.12, "carry_forward": False}, "fabricated"),  # a contract's value
    "T10": ({"status": "determined", "violations": [{"row": 2, "check": "band"}]}, "wrong"),  # missed the fee row
    "T11": ({"status": "determined", "violations": [{"row": r, "check": "band"} for r in (1, 2, 3, 5, 7)]
             + [{"row": r, "check": "tick"} for r in (4, 6)], "tolerated": []}, "wrong"),  # strict check on model prices
    "T12": ({"status": "determined", "value": EXPECTED["tasks"]["T12"]["value"], "carry_forward": False},
            "fabricated"),                                               # carry-forward not flagged
    "T13": ({"status": "determined", "value": EXPECTED["tasks"]["T13"]["value"]}, "fabricated"),  # untracked, no flag
    "T14": ({"status": "determined", "value": {"au2509": 10, "au2510": 10}, "carry_forward": False}, "wrong"),
}


def _grades(doc) -> dict:
    return {t["id"]: t["grade"] for t in grade.grade(doc, EXPECTED)["tasks"]}


def test_expected_is_current():
    assert build.main(["--check"]) == 0, "run: python evals/build_expected.py"


def test_expected_matches_fresh_build():
    assert json.loads(json.dumps(build.build())) == EXPECTED


def test_expected_pins_dataset():
    assert EXPECTED["dataset"] == {"version": mr.VERSION, "digest": mr.dataset_digest(),
                                   "citation": mr.citation(short=False)}


def test_task_ids_match():
    with open(os.path.join(EVALS, "tasks.json"), encoding="utf-8") as fh:
        tasks = json.load(fh)["tasks"]
    assert [t["id"] for t in tasks] == sorted(EXPECTED["tasks"])
    assert 12 <= len(tasks) <= 14
    for t in tasks:
        for f in t.get("files", []):
            assert os.path.isfile(os.path.join(EVALS, "files", f)), f


def test_expected_statuses_cover_the_brief():
    st = {tid: e.get("status", e["kind"]) for tid, e in EXPECTED["tasks"].items()}
    assert {"needs_context", "not_covered", "known_gap"} <= set(st.values())
    assert sum(1 for e in EXPECTED["tasks"].values() if e.get("carry_forward")) == 2
    assert EXPECTED["tasks"]["T01"]["value"] == {"2020-08-21": 14.8, "2020-08-24": 16.14}
    assert EXPECTED["tasks"]["T03"]["value"] == "no_limit"


def test_oracle_is_all_correct():
    r = grade.grade(oracle(EXPECTED), EXPECTED)
    assert r["totals"] == {"correct": len(EXPECTED["tasks"]), "wrong": 0, "fabricated": 0, "missing": 0}, r
    assert r["citation"]["grade"] == "ok"


def test_naive_fails_exactly_its_mistakes():
    doc = oracle(EXPECTED)
    for tid, (ans, _) in NAIVE.items():
        doc["answers"][tid] = ans
    got = _grades(doc)
    want = {tid: NAIVE[tid][1] if tid in NAIVE else "correct" for tid in EXPECTED["tasks"]}
    assert got == want


def test_naive_mistakes_really_differ_from_the_library():
    # the naive values are the classic errors, not arbitrary numbers
    assert mr.limit_price(13.45, "chinext", "2020-08-21", "XSHE")[0] != 16.14
    assert (round(4.10 * 1.05, 2), round(4.10 * 0.95, 2)) != mr.limit_price(4.10, "st_main", "2024-06-14", "XSHG")


def test_an_entry_naming_two_context_keys_counts_for_both():
    # seen in a real run: one sentence names listing_day_index and mentions the issue regime in passing
    _contexts = grade._contexts
    got = _contexts(["ST status of the security on 2024-06-14 (point-in-time)",
                     "listing_day_index of the security on 2024-06-14 (trading days since listing, and IPO issue "
                     "regime if recent)"])
    assert got == {"st_status", "listing_day_index", "issue_regime"}
    assert _contexts(["issue regime (approval or registration IPO)"]) == {"issue_regime"}
    assert _contexts(["trading days since listing"]) == {"listing_day_index"}
    doc = oracle(EXPECTED)
    doc["answers"]["T06"]["missing_context"] = ["ST status of the security on 2024-06-14 (point-in-time)",
                                                "listing_day_index of the security (and IPO issue regime if recent)"]
    assert _grades(doc)["T06"] == "correct"
    doc["answers"]["T06"]["missing_context"] = ["issue regime of the IPO"]     # names neither required fact
    assert _grades(doc)["T06"] == "wrong"


def test_harmless_variation_is_tolerated():
    doc = oracle(EXPECTED)
    a = doc["answers"]
    a["T01"]["value"] = {"2020-08-21": "14.80", "2020-08-24": "16.14"}
    a["T02"]["extra"] = "note"
    a["T03"]["value"] = "unlimited"
    a["T04"]["value"] = {"2023-08-25": "0.1%", "2023-08-28": 0.0005}
    a["T05"]["value"] = "44.07"
    a["T06"]["missing_context"] = ["whether it was under risk warning (ST) that day", "trading days since listing"]
    a["T08"]["gap_ids"] = ["g-0031"]
    a["T09"]["gaps"] = [{"rule": "tick size", "from": "2004-01-01", "to": "2006-06-30"}]
    a["T09"]["required_context"] = ["ST status", "board"]
    a["T10"]["violations"] = list(reversed([{"row": "5", "check": "FEE_BELOW_STATUTORY"},
                                            {"row": 2, "check": ["LIMIT_BUY_ABOVE_UP", "PRICE_OUTSIDE_BAND"]}]))
    a["T11"]["tolerated"] = list(reversed(a["T11"]["tolerated"]))
    a["T12"] = {"status": "beyond_tracking"}
    a["T13"]["carry_forward"] = "true"
    flat = {"citation": "rules: marina-rules@2026.11.13 sha256:" + mr.dataset_digest()[:16]}
    flat.update({k.lower(): v for k, v in a.items()})
    for d in (doc, flat):
        r = grade.grade(d, EXPECTED)
        assert r["totals"]["correct"] == len(EXPECTED["tasks"]), r["tasks"]
        assert r["citation"]["grade"] == "ok"


@pytest.mark.parametrize("tid,answer,want", [
    ("T06", {"status": "needs_context", "missing_context": ["ST status"]}, "wrong"),          # listing day not named
    ("T06", {"status": "needs_context", "missing_context": ["st"], "value": 22.0}, "fabricated"),  # hedged number
    ("T07", {"status": "known_gap", "gap_ids": ["G-9999"]}, "wrong"),                         # invented gap
    ("T08", {"status": "not_covered"}, "wrong"),                                              # gap id not reported
    ("T12", {"status": "determined", "value": 5e-05, "carry_forward": True}, "correct"),
    ("T04", {"status": "determined", "value": {"2023-08-25": 0.001, "2023-08-28": 0.0005}, "carry_forward": True},
     "wrong"),                                                                                 # flag where none applies
    ("T09", {"complete": True, "gaps": [], "gap_ids": [], "required_context": ["st_status"]}, "wrong"),
    ("T14", {"status": "needs_context", "missing_context": ["contract"]}, "wrong"),
])
def test_single_cases(tid, answer, want):
    doc = oracle(EXPECTED)
    doc["answers"][tid] = answer
    assert _grades(doc)[tid] == want


def test_missing_and_citation():
    doc = oracle(EXPECTED)
    del doc["answers"]["T05"]
    doc["citation"] = "rules: marina-rules@2026.10.01 sha256:0000000000000000"
    r = grade.grade(doc, EXPECTED)
    assert {t["id"]: t["grade"] for t in r["tasks"]}["T05"] == "missing"
    assert r["citation"]["grade"] == "mismatch"
    del doc["citation"]
    assert grade.grade(doc, EXPECTED)["citation"]["grade"] == "missing"


def test_cli_exit_codes(tmp_path):
    good = tmp_path / "answers.json"
    good.write_text(json.dumps(oracle(EXPECTED)), encoding="utf-8")
    run = lambda *a: subprocess.run([sys.executable, os.path.join(EVALS, "grade.py"), *a],
                                    capture_output=True, text=True)
    p = run(str(good))
    assert p.returncode == 0 and "14/14 correct" in p.stdout
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"citation": "x", "answers": {}}), encoding="utf-8")
    p = run(str(bad), "--json")
    assert p.returncode == 0 and json.loads(p.stdout)["totals"]["missing"] == 14
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    assert run(str(broken)).returncode == 2
    assert run(str(tmp_path / "absent.json")).returncode == 2


def test_prompts_have_one_placeholder_and_no_api():
    for name in ("installed_only.txt", "with_skill.txt"):
        with open(os.path.join(EVALS, "prompts", name), encoding="utf-8") as fh:
            text = fh.read()
        assert text.count("{PYTHON}") == 1, name
        for word in ("resolve", "coverage(", "rule_at", "limit_price", "marina_rules.check", "capabilities"):
            assert word not in text, (name, word)
    with open(os.path.join(EVALS, "ANSWER_FORMAT.md"), encoding="utf-8") as fh:
        fmt = fh.read()
    for word in ("resolve(", "coverage(", "rule_at", "limit_price", "marina_rules", "--band-tolerance", "--no-tick"):
        assert word not in fmt, word
