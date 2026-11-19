"""China A-share investor suitability: retail_risk_disclosure_required under the STAR growth-tier scopes."""
import os

import pytest
import yaml

import marina_rules as mr
from marina_rules.contract import resolve

RULE = "retail_risk_disclosure_required"
NEW = {"board": "star", "star_growth_tier": "new"}
LEGACY = {"board": "star", "star_growth_tier": "legacy"}


def _load_with(tmp_path, monkeypatch, value):
    """Load a one-record data directory whose record carries ``value`` for the boolean rule."""
    (tmp_path / "cn").mkdir()
    doc = {"schema": 1.1, "market": "XSHG", "records": [{
        "id": "test.suitability", "scope": "star_growth_new", "rule": RULE, "value": value,
        "effective_from": "2025-07-13", "verification": "unverified"}]}
    (tmp_path / "cn" / "x.yaml").write_text(yaml.safe_dump(doc, allow_unicode=True), encoding="utf-8")
    monkeypatch.setattr(mr, "DATA_DIR", str(tmp_path))
    mr.records.cache_clear()
    try:
        return mr.records()
    finally:
        mr.records.cache_clear()


@pytest.mark.parametrize("bad", [1, 0, "true", "yes", None, 1.0, [True]])
def test_bool_rule_rejects_non_bool(tmp_path, monkeypatch, bad):
    with pytest.raises(ValueError, match=f"{RULE} must be true or false"):
        _load_with(tmp_path, monkeypatch, bad)


@pytest.mark.parametrize("ok", [True, False])
def test_bool_rule_accepts_bool(tmp_path, monkeypatch, ok):
    (r,) = _load_with(tmp_path, monkeypatch, ok)
    assert r.value is ok


def test_both_records_resolve():
    d = resolve(RULE, "2025-07-13", "star_growth_new", "XSHG", NEW)
    assert d["status"] == "DETERMINED" and d["result"]["value"] is True
    assert d["record_id"] == "cn.suitability.star_growth_new.2025-07-13" and d["verification"] == "verified"
    d = resolve(RULE, "2026-11-02", "star_growth_legacy", "XSHG", LEGACY)
    assert d["status"] == "DETERMINED" and d["result"]["value"] is False
    assert d["record_id"] == "cn.suitability.star_growth_legacy.2025-07-13"
    assert mr.rule_at(RULE, "2025-07-13", "star_growth_new", "XSHG") is True
    assert mr.rule_at(RULE, "2025-07-13", "star_growth_legacy", "XSHG") is False


def test_no_record_before_the_tier_existed():
    with pytest.raises(KeyError):
        mr.rule_at(RULE, "2025-07-12", "star_growth_new", "XSHG")
    d = resolve(RULE, "2025-07-12", "star_growth_legacy", "XSHG", LEGACY)
    assert d["status"] == "OUT_OF_COVERAGE" and d["known_gap_ids"] == []


def test_growth_scopes_are_mutually_exclusive():
    reg = mr.scopes("cn")
    assert "star_growth_legacy" in reg["star_growth_new"]["excludes"]
    assert "star_growth_new" in reg["star_growth_legacy"]["excludes"]
    # the context that selects one scope contradicts the other
    for scope, ctx in (("star_growth_new", LEGACY), ("star_growth_legacy", NEW)):
        d = resolve(RULE, "2025-07-14", scope, "XSHG", ctx)
        assert d["status"] == "MISSING_CONTEXT" and [c["key"] for c in d["context_conflicts"]] == ["star_growth_tier"]


def test_growth_scopes_need_board_star_and_tier():
    d = resolve(RULE, "2025-07-14", "star_growth_new", "XSHG", {"board": "star"})
    assert d["status"] == "MISSING_CONTEXT" and d["missing_context"] == ["star_growth_tier"]
    d = resolve(RULE, "2025-07-14", "star_growth_new", "XSHG", {"board": "main_board", "star_growth_tier": "new"})
    assert d["status"] == "MISSING_CONTEXT" and d["context_conflicts"][0]["key"] == "board"


def test_growth_scopes_do_not_touch_existing_star_scopes():
    reg = mr.scopes("cn")
    for s in ("star", "st_star", "ipo_first5_star", "delisting_star", "delisting_day1_star"):
        assert not {"star_growth_new", "star_growth_legacy"} & set(reg[s]["excludes"])
        assert "star_growth_tier" not in reg[s]["requires"]


@pytest.mark.parametrize("scope,ctx", [("star", {"board": "star", "st_status": False, "listing_day_index": 100}),
                                       ("st_star", {"board": "star", "st_status": True}),
                                       ("stock", {})])
def test_rule_is_not_defaulted_outside_the_growth_scopes(scope, ctx):
    with pytest.raises(KeyError):
        mr.rule_at(RULE, "2025-07-14", scope, "XSHG")
    d = resolve(RULE, "2025-07-14", scope, "XSHG", ctx)
    assert d["status"] == "OUT_OF_COVERAGE" and d["result"] is None


def test_records_are_sse_only():
    rs = [r for r in mr.records() if r.rule == RULE]
    assert len(rs) == 2 and {r.market for r in rs} == {"XSHG"}
    assert all(r.published_at == "2025-07-13" and r.effective_to is None for r in rs)
    with pytest.raises(KeyError):
        mr.rule_at(RULE, "2025-07-14", "star_growth_new", "XSHG+XSHE")
