"""Fixes from the independent boundary audit (2026-10-26). Each test names the probe or finding it closes."""
import dataclasses
import json
import os
import re

import pytest

import marina_rules as mr
from marina_rules.check import check_rows
from marina_rules.contract import resolve, capabilities

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BASE = {"date": "2024-06-14", "code": "000001", "side": "buy", "price": "10", "prev_close": "10",
        "scope": "main_board", "market": "XSHE"}


# --- decision schema: a small, dependency-free validator for the subset docs/decision.schema.json uses ---------
_TYPES = {"string": str, "object": dict, "array": list, "boolean": bool, "null": type(None)}


def _validate(v, s, path="$"):
    if "const" in s:
        assert v == s["const"], path
    if "enum" in s:
        assert v in s["enum"], (path, v)
    if "type" in s:
        ts = s["type"] if isinstance(s["type"], list) else [s["type"]]
        assert any(isinstance(v, _TYPES[t]) and not (t != "boolean" and isinstance(v, bool)) for t in ts), (path, v, ts)
    if isinstance(v, str) and "pattern" in s:
        assert re.search(s["pattern"], v), (path, v)
    if isinstance(v, dict):
        for k in s.get("required", ()):
            assert k in v, (path, k)
        props = s.get("properties", {})
        if s.get("additionalProperties") is False:
            assert set(v) <= set(props), (path, set(v) - set(props))
        for k, sub in props.items():
            if k in v:
                _validate(v[k], sub, f"{path}.{k}")
    if isinstance(v, list) and "items" in s:
        for i, x in enumerate(v):
            _validate(x, s["items"], f"{path}[{i}]")


def _full_context(scope, rec):
    """Context consistent with a scope's declared constraints, for exercising every record."""
    reg = mr.scopes().get(scope, {})
    ctx = {}
    for k, spec in (reg.get("asserts") or {}).items():
        entries = spec if isinstance(spec, list) else [spec if isinstance(spec, dict) else {"eq": spec}]
        e = entries[-1]
        ctx[k] = e.get("eq", e["in"][0] if "in" in e else e.get("max", e.get("min")))
        if k == "listing_day_index" and "min" in e and "max" not in e:
            ctx[k] = 1000
        if k == "delisting_day_index" and "min" in e:
            ctx[k] = 5
    for k in reg.get("requires", ()):
        ctx.setdefault(k, {"board": "main_board", "st_status": False, "listing_day_index": 1000, "fund_type": "other",
                           "issue_regime": "approval", "fund_constituents": "mixed", "delisting_day_index": 5,
                           "underlying_t0": False, "delisting_entry_before_2020_08_24": False,
                           "star_growth_tier": "new"}[k])
    if scope in ("etf", "etf_20pct"):
        ctx.setdefault("fund_type", "other")
    return ctx


def test_every_record_resolves_to_json_that_validates_against_the_published_schema():
    """Finding 8: evidence dates were datetime.date objects; json.dumps(resolve(...)) failed."""
    schema = json.load(open(os.path.join(ROOT, "docs", "decision.schema.json"), encoding="utf-8"))
    n = 0
    for r in mr.records():
        d = resolve(r.rule, r.effective_from, r.scope, r.market, _full_context(r.scope, r))
        json.loads(json.dumps(d, ensure_ascii=False))
        _validate(d, schema)
        n += 1
    assert n == len(mr.records())
    d = resolve("price_limit_pct", "2026-07-06", "st_main", "XSHG+XSHE", {"board": "main_board", "st_status": True})
    assert d["status"] == "DETERMINED" and all(isinstance(e["date"], (str, type(None))) for e in d["evidence_refs"])
    json.dumps(d)


def test_records_carry_no_date_objects():
    import datetime as dt

    def walk(v):
        if isinstance(v, (dt.date, dt.datetime)):
            raise AssertionError(v)
        if isinstance(v, dict):
            [walk(x) for x in v.values()]
        if isinstance(v, (list, tuple)):
            [walk(x) for x in v]
    for r in mr.records():
        walk(r.value); walk(r.sources); walk([r.effective_from, r.effective_to, r.published_at, r.recorded_at])


# --- OVERLAP-MARKET ---------------------------------------------------------------------------------------------
def _with_records(monkeypatch, recs):
    monkeypatch.setattr(mr, "records", lambda: tuple(recs))


def test_intersecting_market_sets_conflict(monkeypatch):
    r = next(x for x in mr.records() if x.scope == "main_board" and x.rule == "price_limit_pct")
    other = dataclasses.replace(r, id="t.xshe", market="XSHE", value=0.2)
    _with_records(monkeypatch, [r, other])
    with pytest.raises(mr.RuleConflict):
        mr.record_at("price_limit_pct", "2024-06-14", "main_board", "XSHE")
    with pytest.raises(mr.RuleConflict):
        mr.record_at("price_limit_pct", "2024-06-14", "main_board", None)
    # XSHG query: only the XSHG+XSHE record contains XSHG → no conflict
    assert mr.record_at("price_limit_pct", "2024-06-14", "main_board", "XSHG").id == r.id
    cov = mr.coverage("XSHE", "main_board", ["price_limit_pct"], "2024-06-14", "2024-06-15")
    assert cov["status"] == "partial" and cov["conflicts"]


def test_disjoint_market_sets_do_not_conflict_for_a_one_market_query(monkeypatch):
    r = next(x for x in mr.records() if x.scope == "main_board" and x.rule == "price_limit_pct")
    a = dataclasses.replace(r, id="t.g", market="XSHG"); b = dataclasses.replace(r, id="t.e", market="XSHE", value=0.2)
    _with_records(monkeypatch, [a, b])
    assert mr.record_at("price_limit_pct", "2024-06-14", "main_board", "XSHE").id == "t.e"
    with pytest.raises(mr.RuleConflict):
        mr.record_at("price_limit_pct", "2024-06-14", "main_board", None)


def test_loader_rejects_overlap_with_intersecting_market_sets():
    r = next(x for x in mr.records() if x.scope == "main_board" and x.rule == "price_limit_pct")
    with pytest.raises(ValueError, match="overlapping"):
        mr._reject_overlaps([r, dataclasses.replace(r, id="t.xshe", market="XSHE")])
    mr._reject_overlaps([dataclasses.replace(r, market="XSHG"), dataclasses.replace(r, id="t.e", market="XSHE")])


# --- CB-TICK / CB-ROUND -----------------------------------------------------------------------------------------
@pytest.mark.parametrize("mk", ["XSHG", "XSHE"])
def test_convertible_tick_and_rounding(mk):
    assert mr.tick_size("convertible", "2025-06-16", mk) == 0.001
    assert mr.tick_size("convertible_day1", "2022-08-01", mk) == 0.001
    assert mr.limit_price(100.003, "convertible", "2025-06-16", mk) == (120.004, 80.002)
    # before the 2022 rules: the exchange's 债券 tick (SSE 0.01 throughout; SZSE 0.01 → 0.001 from 2011-02-28)
    assert mr.tick_size("convertible", "2022-07-29", mk) == (0.01 if mk == "XSHG" else 0.001)
    assert mr.gaps_for(mk, "convertible", "tick_size", "2006-07-01", "2022-08-01") == []   # G-0025 closed
    with pytest.raises(mr.RuleConflict):   # the two exchanges differed: no single answer without a market
        mr.tick_size("convertible", "2022-07-29")


# --- context constraints ----------------------------------------------------------------------------------------
@pytest.mark.parametrize("scope,ctx,market,date", [
    ("main_board", {"board": "star", "st_status": False, "listing_day_index": 100}, "XSHE", "2024-06-14"),
    ("main_board", {"board": "main_board", "st_status": False, "listing_day_index": 1}, "XSHE", "2024-06-14"),
    ("main_board", {"board": "main_board", "st_status": False, "listing_day_index": 3}, "XSHE", "2024-06-14"),
    ("main_board", {"board": "main_board", "st_status": False, "listing_day_index": 1}, "XSHE", "2015-06-01"),
    ("ipo_first5_main", {"board": "main_board", "listing_day_index": 1, "issue_regime": "approval"}, "XSHE", "2024-06-14"),
    ("ipo_day1_main", {"board": "main_board", "listing_day_index": 1, "issue_regime": "registration"}, "XSHE", "2015-06-01"),
    ("ipo_day1_main", {"board": "chinext", "listing_day_index": 1, "issue_regime": "approval"}, "XSHE", "2021-06-01"),
    ("etf_20pct", {"fund_constituents": "mixed"}, "XSHE", "2024-06-14"),
    ("etf", {"fund_constituents": "all_20pct_band"}, "XSHE", "2024-06-14"),
    ("convertible", {"listing_day_index": 1}, "XSHE", "2024-06-14"),
    ("convertible_day1", {"listing_day_index": 2}, "XSHE", "2024-06-14"),
    ("delisting_day1", {"board": "main_board", "delisting_day_index": 2}, "XSHE", "2024-06-14"),
    ("delisting", {"board": "main_board", "delisting_day_index": 1}, "XSHE", "2024-06-14"),
    ("reits_day1", {"listing_day_index": 2}, "XSHG", "2024-06-14"),
    ("reits", {"listing_day_index": 1}, "XSHG", "2024-06-14"),
    ("bse", {"board": "bse", "st_status": True, "listing_day_index": 100}, "BJSE", "2024-06-14"),
    ("st_bse", {"board": "bse", "st_status": False}, "BJSE", "2024-06-14"),
    ("main_board", {"board": None, "st_status": False, "listing_day_index": None}, "XSHE", "2024-06-14"),
])
def test_contradictory_or_null_context_is_missing_context(scope, ctx, market, date):
    rule = "price_limit_pct_of_issue_price" if scope == "convertible_day1" else "price_limit_pct"
    d = resolve(rule, date, scope, market, ctx)
    assert d["status"] == "MISSING_CONTEXT", d["reason"]
    assert d["missing_context"] or d["context_conflicts"]


def test_null_counts_as_missing():
    d = resolve("price_limit_pct", "2024-06-14", "main_board", "XSHE", {"board": None, "st_status": False, "listing_day_index": None})
    assert set(d["missing_context"]) == {"board", "listing_day_index"}


@pytest.mark.parametrize("scope,ctx,date,value", [
    ("main_board", {"board": "main_board", "st_status": False, "listing_day_index": 2}, "2015-06-01", 0.1),
    ("main_board", {"board": "main_board", "st_status": False, "listing_day_index": 6}, "2024-06-14", 0.1),
    # approval-regime stock listed 2023-04-06, day 3 falls after 2023-04-10: still the ordinary band
    ("main_board", {"board": "main_board", "st_status": False, "listing_day_index": 3, "issue_regime": "approval"}, "2023-04-11", 0.1),
    ("chinext", {"board": "chinext", "st_status": False, "listing_day_index": 2}, "2019-06-03", 0.1),
    ("ipo_day1_main", {"board": "chinext", "listing_day_index": 1, "issue_regime": "approval"}, "2019-06-03", {"up": 0.44, "down": 0.36}),
])
def test_consistent_context_still_determined(scope, ctx, date, value):
    d = resolve("price_limit_pct", date, scope, "XSHE", ctx)
    assert d["status"] == "DETERMINED" and d["result"]["value"] == value, d["reason"]


def test_crossborder_fund_under_etf_needs_underlying_t0():
    """CROSSBORDER-UNKNOWN: a cross-border fund is T+1 under etf only if its underlying does not trade same-day."""
    d = resolve("min_holding_days", "2024-06-14", "etf", "XSHE", {"fund_type": "cross_border"})
    assert d["status"] == "MISSING_CONTEXT" and d["missing_context"] == ["underlying_t0"]
    d = resolve("min_holding_days", "2024-06-14", "etf", "XSHE", {"fund_type": "cross_border", "underlying_t0": True})
    assert d["status"] == "MISSING_CONTEXT" and d["context_conflicts"]
    d = resolve("min_holding_days", "2024-06-14", "etf", "XSHE", {"fund_type": "cross_border", "underlying_t0": False})
    assert d["status"] == "DETERMINED" and d["result"]["value"] == 1


def test_constraints_are_visible_in_capabilities():
    caps = capabilities()
    assert caps["scopes"]["main_board"]["asserts"]["board"] == "main_board"
    assert caps["scopes"]["etf"]["rule_asserts"]["min_holding_days"]["requires"] == ["fund_type"]
    assert caps["tick_families"]["map"]["convertible"] == "convertible"
    committed = json.load(open(os.path.join(ROOT, "capabilities.json"), encoding="utf-8"))
    assert committed["scopes"] == caps["scopes"]


# --- COVER-TICK-FAMILY ------------------------------------------------------------------------------------------
@pytest.mark.parametrize("scope,market", [("main_board", "XSHE"), ("chinext", "XSHE"), ("etf_bond", "XSHG"),
                                          ("convertible", "XSHG"), ("st_b_share", "XSHG")])
def test_coverage_and_resolve_agree_on_tick_size(scope, market):
    cov = mr.coverage(market, scope, ["tick_size"], "2024-06-14", "2024-06-15")
    d = resolve("tick_size", "2024-06-14", scope, market, {})
    assert (cov["status"] == "complete") == (d["status"] == "DETERMINED") is True
    assert cov["records"] == [d["record_id"]]
    assert mr.lookup_scope("tick_size", scope) == mr.tick_family(scope)


# --- fill checks and stamp --------------------------------------------------------------------------------------
@pytest.mark.parametrize("bad", ["nan", "inf", "-inf", "", "NaN"])
@pytest.mark.parametrize("field", ["price", "prev_close"])
def test_non_finite_is_row_invalid_even_when_unlimited(bad, field):
    out = check_rows([{**BASE, "scope": "ipo_first5_main", field: bad}])
    assert out["rules_verified"] is False and out["counts"] == {"ROW_INVALID": 1}


@pytest.mark.parametrize("row,off", [
    ({"price": "10.001"}, True), ({"price": "10.01"}, False), ({"price": "10.10"}, False),
    ({"price": "9.07", "prev_close": "9.00"}, False),          # 9.07 / 0.01 is 906.9999… in binary float
    ({"scope": "etf", "price": "1.0005", "prev_close": "1"}, True),
    ({"scope": "etf", "price": "1.001", "prev_close": "1"}, False),
    ({"scope": "convertible", "price": "110.123", "prev_close": "100"}, False),
    ({"scope": "convertible", "price": "110.1234", "prev_close": "100"}, True),
])
def test_price_off_tick(row, off):
    out = check_rows([{**BASE, **row}])
    assert ("PRICE_OFF_TICK" in out["counts"]) is off, out["findings"]


@pytest.mark.parametrize("field,a,b", [("fee", "1", "2"), ("market", "XSHE", "XSHG"), ("turnover", "10000", "10001"),
                                       ("decimals", "", "2"), ("code", "000001", "000002"), ("scope", "main_board", "etf")])
def test_stamp_commits_to_every_input(field, a, b):
    r = {**BASE, "fee": "100", "turnover": "10000"}
    s1 = check_rows([{**r, field: a}])["stamp"]; s2 = check_rows([{**r, field: b}])["stamp"]
    assert s1 and s2 and s1 != s2


def test_stamp_is_recomputable_from_the_documented_canonical_form():
    import hashlib
    rows = [{**BASE, "fee": "5", "turnover": "10000"}]
    out = check_rows(rows)
    canon = hashlib.sha256(b"marina-check-canon/2 strict=0\n")
    canon.update((json.dumps(["2024-06-14", "000001", "buy", "10", "10", "main_board", "XSHE", "", "5", "10000"],
                              ensure_ascii=False, separators=(",", ":")) + "\n").encode())
    stamp = hashlib.sha256((mr.dataset_digest() + "\n" + canon.hexdigest()).encode()).hexdigest()
    assert out["stamp"] == f"rules-verified@{mr.VERSION}:{stamp[:32]}"
    assert out["marina_rules_version"] == mr.VERSION and out["code_version"] == mr.__version__


# --- AUDIT-IPO-DATE ---------------------------------------------------------------------------------------------
def _ab():
    import importlib.util
    spec = importlib.util.spec_from_file_location("auditbars", os.path.join(ROOT, "scripts", "audit_bars.py"))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


@pytest.mark.parametrize("code,date,idx,listing,want", [
    ("sh.603000", "2023-03-01", 0, None, "ipo_day1_main"),
    ("sz.000001", "2023-04-07", 0, None, "ipo_day1_main"),
    ("sh.603000", "2023-04-10", 0, None, "ipo_first5_main"),
    ("sh.603000", "2023-04-11", 2, "2023-04-07", "main_board"),   # listed before the cutoff: no 5-day window
    ("sh.603000", "2023-04-11", 2, None, None),                   # ambiguous without the listing date: skip
    ("sh.603000", "2023-03-02", 1, None, "main_board"),
    ("sz.300001", "2020-08-21", 0, None, "ipo_day1_main"),
    ("sz.300001", "2020-08-24", 0, None, "ipo_first5_chinext"),
    ("sz.300001", "2020-08-25", 1, "2020-08-21", "chinext"),
    ("sh.688001", "2019-07-22", 0, None, "ipo_first5_star"),
    ("sh.688001", "2019-07-26", 4, "2019-07-22", "ipo_first5_star"),
])
def test_audit_bars_ipo_regime_follows_listing_date(code, date, idx, listing, want):
    got = _ab().scope_cn_a(code, date, idx, listing_date=listing)
    assert (got[0] if got else None) == want


def test_hk_capabilities_are_committed_and_generated_from_data():
    caps = capabilities("hk")
    assert set(caps["scopes"]) == {"hk_stock", "hk_etf", "hk_etf_part_b"}
    assert [g["gap_id"] for g in caps["known_gaps"]] == [f"G-HK-{n:04d}" for n in range(1, 7)]
    assert caps["context_vocabulary"] == ["spread_table"]
    assert caps["rules"]["price_limit_pct"]["markets"] == ["XHKG"]
    assert caps["rules"]["tick_size_table"]["scopes"] == ["hk_etf", "hk_etf_part_b", "hk_stock"]
    assert caps["rules"]["vcm_trigger_pct"]["earliest_effective_from"] == "2016-08-22"
    assert caps["rules"]["closing_auction_limit_pct"]["scopes"] == ["hk_etf", "hk_stock"]
    assert caps["rules"]["short_sale_price_test"]["markets"] == ["XHKG"]   # the US records are in capabilities-us.json
    assert caps["rules"]["short_sale_price_test"]["earliest_effective_from"] == "2002-03-25"   # ETF exemption
    assert caps["rules"]["investor_compensation_levy_each_side"]["earliest_effective_from"] == "2005-12-19"
    assert caps["rules"]["opening_auction_limit_pct"]["earliest_effective_from"] == "2020-10-19"   # before: G-HK-0005 / 0006
    assert caps["rules"]["order_spread_limit"]["earliest_effective_from"] == "2005-07-04"   # eight -> 24 spreads
    assert caps["rules"]["order_price_multiple_limit"]["earliest_effective_from"] == "2010-01-01"   # truncated
    assert caps["rules"]["order_price_multiple_limit"]["scopes"] == ["hk_etf", "hk_stock"]
    committed = json.load(open(os.path.join(ROOT, "capabilities-hk.json"), encoding="utf-8"))
    assert {k: committed[k] for k in ("rules", "scopes", "known_gaps", "ruleset_hash")} == \
        {k: caps[k] for k in ("rules", "scopes", "known_gaps", "ruleset_hash")}


def test_us_capabilities_are_committed_and_generated_from_data():
    caps = capabilities("us")
    assert set(caps["scopes"]) == {"us_stock", "us_etf"}
    assert [g["gap_id"] for g in caps["known_gaps"]] == [f"G-US-{n:04d}" for n in range(1, 16)]
    assert set(caps["rules"]) == {"sec_fee_rate_sell", "finra_taf_sell", "settlement_cycle_days", "min_holding_days",
                                  "min_quote_increment", "luld_band", "mwcb_decline_levels", "session_schedule",
                                  "extended_hours", "single_stock_pause_pct", "cat_fee_per_share",
                                  "cat_historical_assessment_per_share", "short_sale_price_test",
                                  "pattern_day_trader_min_equity"}
    assert caps["rules"]["settlement_cycle_days"]["markets"] == ["XNAS", "XNYS"]
    assert caps["rules"]["session_schedule"]["markets"] == ["XNAS", "XNYS"]   # per-exchange records, never both at once
    assert caps["rules"]["extended_hours"]["markets"] == ["XNAS"]              # NYSE: known gaps G-US-0008 / G-US-0009
    assert caps["rules"]["luld_band"]["earliest_effective_from"] == "2013-12-08"
    assert caps["rules"]["mwcb_decline_levels"]["records_by_verification"] == {"single-source": 2, "verified": 2}
    assert caps["rules"]["single_stock_pause_pct"]["earliest_effective_from"] == "2011-08-08"
    assert caps["rules"]["single_stock_pause_pct"]["records_by_verification"] == {"verified": 2}
    assert caps["rules"]["cat_fee_per_share"]["earliest_effective_from"] == "2024-09-01"
    assert caps["rules"]["short_sale_price_test"]["records_by_verification"] == {"single-source": 2, "verified": 2}
    assert caps["rules"]["pattern_day_trader_min_equity"]["has_open_interval"] is False   # G-US-0014 / G-US-0015 after
    committed = json.load(open(os.path.join(ROOT, "capabilities-us.json"), encoding="utf-8"))
    assert {k: committed[k] for k in ("rules", "scopes", "known_gaps", "ruleset_hash")} == \
        {k: caps[k] for k in ("rules", "scopes", "known_gaps", "ruleset_hash")}
