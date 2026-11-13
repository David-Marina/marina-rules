"""Rule Decision Contract: every status reachable, result only on DETERMINED, output validates against its schema."""
import json
import pytest
from marina_rules.contract import resolve, contract_schema, capabilities, CONTRACT_VERSION

STATUSES = {"DETERMINED", "MISSING_CONTEXT", "OUT_OF_COVERAGE", "CONFLICT", "UNVERIFIED"}


def _valid(d):
    """Minimal structural validation without a jsonschema dependency."""
    sch = contract_schema()
    assert set(d) == set(sch["required"]) | {"market"}, set(d) ^ (set(sch["required"]) | {"market"})
    assert d["status"] in STATUSES and d["contract_version"] == CONTRACT_VERSION
    assert (d["result"] is not None) == (d["status"] == "DETERMINED")
    assert len(d["ruleset_hash"]) == 64
    json.dumps(d)  # serialisable
    return d


def test_determined_with_full_context():
    d = _valid(resolve("price_limit_pct", "2024-06-14", "st_main", "XSHE", {"board": "main_board", "st_status": True}))
    assert d["status"] == "DETERMINED" and d["result"]["value"] == 0.05 and d["record_id"] == "cn.limit.st_main.1998-04-22"
    assert d["evidence_refs"] and all(e["content_sha256"] for e in d["evidence_refs"])


def test_missing_context_names_the_keys_and_never_returns_a_value():
    d = _valid(resolve("price_limit_pct", "2024-06-14", "main_board", "XSHE"))
    assert d["status"] == "MISSING_CONTEXT" and set(d["missing_context"]) == {"board", "st_status", "listing_day_index"}


def test_contradictory_context_is_not_silently_accepted():
    d = _valid(resolve("price_limit_pct", "2024-06-14", "main_board", "XSHE",
                       {"board": "main_board", "st_status": True, "listing_day_index": 500}))
    assert d["status"] == "MISSING_CONTEXT" and d["context_conflicts"][0]["key"] == "st_status"
    d = _valid(resolve("price_limit_pct", "2024-01-30", "ipo_first5_main", "XSHG",
                       {"board": "main_board", "listing_day_index": 9, "issue_regime": "registration"}))
    assert d["status"] == "MISSING_CONTEXT" and d["context_conflicts"][0]["key"] == "listing_day_index"


def test_out_of_coverage_distinguishes_known_gap_from_blind_spot():
    k = _valid(resolve("min_holding_days", "2005-06-14", "etf", "XSHG+XSHE", {"fund_type": "other"}))
    b = _valid(resolve("price_limit_pct", "2024-06-14", "unicorn"))
    assert k["status"] == b["status"] == "OUT_OF_COVERAGE"
    assert k["known_gap_ids"] == ["G-0013"] and b["known_gap_ids"] == []
    bydate = _valid(resolve("price_limit_pct", "2005-06-01", "convertible", "XSHG+XSHE", {"listing_day_index": 30}))
    assert bydate["status"] == "OUT_OF_COVERAGE" and bydate["known_gap_ids"] == ["G-0001"]


def test_unverified_respects_callers_bar():
    ctx = {"board": "main_board", "st_status": False}
    ok = _valid(resolve("price_limit_pct", "2024-01-05", "b_share", "XSHG", ctx))                       # default bar: single-source
    strict = _valid(resolve("price_limit_pct", "2024-01-05", "b_share", "XSHG", ctx, min_verification="verified"))
    assert ok["status"] == "DETERMINED" and strict["status"] == "UNVERIFIED" and strict["record_id"] == ok["record_id"]


def test_bad_min_verification_is_a_programmer_error():
    with pytest.raises(ValueError):
        resolve("stamp_duty_sell", "2024-01-05", "stock", min_verification="gold")


def test_capabilities_is_generated_from_data():
    c = capabilities()
    assert c["ruleset_version"] and len(c["ruleset_hash"]) == 64
    assert "price_limit_pct" in c["rules"] and "st_star" in c["rules"]["price_limit_pct"]["scopes"]
    assert "st_status" in c["context_vocabulary"]
    assert any(g["gap_id"] == "G-0013" for g in c["known_gaps"])
    assert set(c["scopes"]) == set(__import__("marina_rules").scopes("cn"))


def test_min_holding_days_asks_only_for_fund_type_not_band_or_st_context():
    d = _valid(resolve("min_holding_days", "2024-06-14", "etf", "XSHG+XSHE", {}))
    assert d["status"] == "MISSING_CONTEXT" and d["missing_context"] == ["fund_type"]   # not fund_constituents
    d = _valid(resolve("min_holding_days", "2024-06-14", "etf", "XSHG+XSHE", {"fund_type": "other"}))
    assert d["status"] == "DETERMINED" and d["result"]["value"] == 1
    # a bond ETF must not get T+1 by being asked under the generic scope
    d = _valid(resolve("min_holding_days", "2024-06-14", "etf", "XSHG+XSHE", {"fund_type": "bond_etf"}))
    assert d["status"] == "MISSING_CONTEXT" and d["context_conflicts"][0]["key"] == "fund_type"
    d = _valid(resolve("min_holding_days", "2024-06-14", "etf_crossborder", "XSHG+XSHE", {"fund_type": "cross_border"}))
    assert d["missing_context"] == ["underlying_t0"]
    d = _valid(resolve("min_holding_days", "2024-06-14", "etf_crossborder", "XSHG+XSHE",
                       {"fund_type": "cross_border", "underlying_t0": False}))
    assert d["status"] == "MISSING_CONTEXT" and d["context_conflicts"][0]["key"] == "underlying_t0"
    # stocks and B shares: no ST / listing context needed for the holding period
    d = _valid(resolve("min_holding_days", "2024-06-14", "b_share", "XSHG", {}))
    assert d["status"] == "DETERMINED" and d["result"]["value"] == 1
    assert _valid(resolve("session_schedule", "2024-06-14", "etf", "XSHE", {}))["status"] == "DETERMINED"
