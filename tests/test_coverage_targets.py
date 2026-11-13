"""Coverage targets (coverage/cn_targets.yaml) and scripts/coverage_report.py."""
import json
import os
import subprocess
import sys

import pytest
import yaml

import marina_rules as mr

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import coverage_report as cr  # noqa: E402

UNTIL = "2026-10-25"   # fixed so the test does not drift with the calendar
# futures scopes (CFFEX, SHFE, INE, CZCE, GFEX) are not part of the A-share target
FUTURES_SCOPES = {s for s in mr.scopes("cn") if s.startswith(("cffex_", "shfe_", "ine_", "czce_", "gfex_"))}


def _doc():
    with open(cr.TARGETS, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def test_targets_well_formed_and_reference_known_scopes_and_rules():
    cfg = cr.load()                       # raises on structural problems (ids, starts, unresolved format)
    reg = mr.scopes("cn")
    data_rules = {r.rule for r in mr.records()}
    new_rules = set((_doc().get("new_rules") or {}))
    with open(os.path.join(ROOT, "docs", "SCHEMA.md"), encoding="utf-8") as fh:
        schema = fh.read()
    for t in cfg["targets"]:
        assert t["scope"] in reg, f"{t['id']}: scope not in scopes.yaml"
        assert t["scope"] not in FUTURES_SCOPES, f"{t['id']}: futures are not part of the A-share target"
        for s in t.get("applies_to") or []:
            assert s in reg, f"{t['id']}: applies_to scope {s!r} not in scopes.yaml"
        # a rule must exist in the data, or be declared in new_rules (to be registered with its first record)
        assert t["rule"] in data_rules or t["rule"] in new_rules, f"{t['id']}: unknown rule {t['rule']!r}"
        if t["rule"] in data_rules:
            assert f"`{t['rule']}`" in schema, f"{t['rule']} not registered in docs/SCHEMA.md"
        assert t["start"] >= cr.SCOPE_FLOOR


def test_every_a_share_scope_is_targeted():
    cfg = cr.load()
    covered = {t["scope"] for t in cfg["targets"]} | {s for t in cfg["targets"] for s in (t.get("applies_to") or [])}
    a_share = set(mr.scopes("cn")) - FUTURES_SCOPES
    assert a_share - covered == set(), f"scopes without any target: {sorted(a_share - covered)}"


def test_unresolved_section_exists_with_documented_format():
    doc = _doc()
    assert "unresolved" in doc
    for u in doc["unresolved"] or []:
        assert {"target", "from", "to", "reason"} <= set(u)


def test_brute_and_boundary_modes_agree():
    a, b = cr.run(UNTIL), cr.run(UNTIL, brute=True)
    assert a["mode"] == "boundary" and b["mode"] == "brute"
    a.pop("mode"); b.pop("mode")
    assert a == b


def test_report_runs_in_every_output_mode():
    env = {**os.environ, "PYTHONPATH": os.path.join(ROOT, "src")}
    script = os.path.join(ROOT, "scripts", "coverage_report.py")
    for flag in ([], ["--markdown"], ["--json"]):
        p = subprocess.run([sys.executable, script, "--until", UNTIL, *flag], capture_output=True, text=True, env=env)
        assert p.returncode in (0, 1), p.stderr
        assert "target" in p.stdout
    rep = json.loads(subprocess.run([sys.executable, script, "--until", UNTIL, "--json"], capture_output=True,
                                    text=True, env=env).stdout)
    assert rep["targets"] == len(cr.load()["targets"]) and 0 <= rep["coverage_pct"] <= 100
    assert (p.returncode == 1) == bool(rep["failing_targets"])


def test_unlisted_gap_fails_and_listed_gap_does_not(tmp_path):
    doc = _doc()
    rep = cr.run(UNTIL)
    assert doc["unresolved"], "the exercise needs at least one unresolved entry"
    victim = doc["unresolved"][0]["target"]
    doc["unresolved"] = [u for u in doc["unresolved"] if u["target"] != victim]   # un-list one target's gaps
    p = tmp_path / "t.yaml"
    p.write_text(yaml.safe_dump(doc, allow_unicode=True), encoding="utf-8")
    rep2 = cr.run(UNTIL, path=str(p))
    assert victim in rep2["failing_targets"] and victim not in rep["failing_targets"]
    assert rep2["coverage_pct"] == rep["coverage_pct"]          # listed gaps still count as not covered


def test_no_gap_outside_unresolved():
    """Every gap must be filled or listed in `unresolved` (which still counts against the percentage)."""
    rep = cr.run(UNTIL)
    assert rep["failing_targets"] == []
    assert all(not r["unexplained_gaps"] for r in rep["rows"])
    listed = sum(g["days"] for r in rep["rows"] for g in r["allowed_gaps"])
    assert rep["target_days"] - rep["covered_days"] == listed      # the only uncovered days are the unresolved ones


def test_not_applicable_needs_hashed_sources_and_is_reported_separately(tmp_path):
    doc = _doc()
    na = [t for t in doc["targets"] if t.get("not_applicable")]
    assert na, "step 2 marks fund / REIT / convertible stamp duty and transfer fee not applicable"
    rep = cr.run(UNTIL)
    assert {x["id"] for x in rep["not_applicable"]} == {t["id"] for t in na}
    for t in na:
        assert all(len(s["content_sha256"]) == 64 for s in t["not_applicable"]["sources"])
    bad = dict(doc)
    bad["targets"] = [dict(t) for t in doc["targets"]]
    t0 = next(t for t in bad["targets"] if t.get("not_applicable"))
    t0["not_applicable"] = "funds are exempt, see https://example.org"          # old free-text form: rejected
    p = tmp_path / "t.yaml"
    p.write_text(yaml.safe_dump(bad, allow_unicode=True), encoding="utf-8")
    with pytest.raises(ValueError, match="not_applicable"):
        cr.load(str(p))


def test_one_transfer_fee_rule_per_market_and_day():
    """XSHG: transfer_fee_par_value before 2015-08-01, transfer_fee_each_side from it; never both, never neither."""
    import datetime as dt
    for day in ("2006-07-03", "2012-06-01", "2015-07-31", "2015-08-03", "2022-04-29"):
        hits = []
        for rule in ("transfer_fee_par_value", "transfer_fee_each_side"):
            try:
                mr.record_at(rule, day, "stock", "XSHG"); hits.append(rule)
            except KeyError:
                pass
        assert len(hits) == 1, (day, hits)
    tg = {t["id"]: t for t in cr.load()["targets"]}
    assert tg["XSHG:stock:transfer_fee_par_value"]["end"] == tg["XSHG:stock:transfer_fee_each_side"]["start"] == "2015-08-01"


def test_chinext_delisting_window_split_targets_complete_and_parent_unresolved():
    rep = cr.run(UNTIL)
    rows = {r["id"]: r for r in rep["rows"]}
    for sc in ("delisting_chinext_pre0824", "delisting_chinext_post0824"):
        r = rows[f"XSHE:{sc}:price_limit_pct"]
        assert not r["gaps"] and r["days"] == 129
    parent = rows["XSHE:delisting_chinext:price_limit_pct"]
    assert [(g["from"], g["to"]) for g in parent["gaps"]] == [("2020-08-24", "2020-12-31")]
    assert parent["gaps"] == parent["allowed_gaps"]          # listed as unresolved, still not covered
