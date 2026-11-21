"""Schema and semantics tests. Run with: pytest -q"""
import datetime as dt
import re

import pytest

import marina_rules as mr

ID_RE = re.compile(r"^[a-z0-9_]+(\.[a-z0-9_\-]+)+$")
SCOPES = set(mr.scopes("cn")) | set(mr.scopes("hk")) | set(mr.scopes("us"))  # registries are authoritative
MARKETS = {"XSHG", "XSHE", "BJSE", "XSHG+XSHE", "XSHG+XSHE+BJSE", "CCFX", "XSGE", "XINE", "XZCE", "GFEX", "XHKG", "XNYS+XNAS", "XNYS", "XNAS"}


def test_loads_and_nonempty():
    assert len(mr.records()) >= 20


@pytest.mark.parametrize("r", mr.records(), ids=lambda r: r.id)
def test_record_shape(r):
    assert ID_RE.match(r.id), f"bad id {r.id}"
    assert r.scope in SCOPES, f"{r.id}: unknown scope {r.scope}"
    assert r.market in MARKETS, f"{r.id}: unknown market {r.market}"
    dt.date.fromisoformat(r.effective_from)
    if r.effective_to:
        dt.date.fromisoformat(r.effective_to)
        assert r.effective_to > r.effective_from
    assert r.verification in ("verified", "single-source", "unverified")
    if r.verification != "unverified":
        assert r.sources, f"{r.id}: {r.verification} requires at least one source"
    for s in r.sources:
        assert s.get("url", "").startswith("http"), f"{r.id}: source without URL"
        assert s.get("publisher"), f"{r.id}: source without publisher"
        if r.verification != "unverified":
            assert re.fullmatch(r"[0-9a-f]{64}", str(s.get("content_sha256", ""))), f"{r.id}: source without content_sha256 — mandatory"
            assert s.get("hash_kind") in ("text", "bytes"), f"{r.id}: hash_kind missing"
            assert str(s.get("quote", "")).strip(), f"{r.id}: source without verbatim quote — mandatory"
    if r.rule == "price_limit_pct":
        v = r.value
        if isinstance(v, dict):
            assert set(v) == {"up", "down"} and 0 < v["up"] < 1 and 0 < v["down"] < 1
        else:
            assert v == "unlimited" or 0 < float(v) < 1
    if r.rule.startswith(("stamp_", "transfer_", "commission_cap")):
        assert 0 <= float(r.value) < 0.01


def _probe_codes(scope, date, months=25):
    """Contract codes of a futures product scope with months_to_delivery 0..months-1 on ``date``."""
    prod = scope.split("_")[1]
    y, m = int(date[:4]), int(date[5:7])
    out = []
    for k in range(months):
        idx = y * 12 + m - 1 + k
        out.append(f"{prod}{(idx // 12) % 100:02d}{idx % 12 + 1:02d}")
    return out


def test_no_overlapping_intervals_within_same_key():
    # Records with a contracts selector may share days with other selector records of the key (the loader proves
    # per-contract disjointness); they are grouped by their selector here, so each selector's own history is checked.
    import json
    by_key: dict = {}
    for r in mr.records():
        by_key.setdefault((r.market, r.scope, r.rule, json.dumps(r.contracts, sort_keys=True)), []).append(r)
    for key, rs in by_key.items():
        rs = sorted(rs, key=lambda r: r.effective_from)
        for a, b in zip(rs, rs[1:]):
            # Two records of the same key may not both be open-ended; later one must start after earlier starts.
            assert b.effective_from > a.effective_from, f"{key}: duplicate effective_from"
            if a.effective_to is not None:
                assert a.effective_to <= b.effective_from, f"{key}: {a.id} overlaps {b.id}"


def test_known_points():
    assert mr.rule_at("stamp_duty_sell", "2023-08-27") == 0.001
    assert mr.rule_at("stamp_duty_sell", "2023-08-28") == 0.0005
    # BSE charged 0.025‰ until 2022-04-29 while SSE/SZSE charged 0.02‰: the BSE rate lives under family scope
    # bse_stock, so a market-less `stock` query is answered by the single SSE/SZSE record.
    assert mr.rule_at("transfer_fee_each_side", "2022-04-28", market="XSHG+XSHE") == 0.00002
    assert mr.rule_at("transfer_fee_each_side", "2022-04-29") == 0.00001
    for d in ("2021-11-15", "2021-12-01", "2022-04-28"):
        assert mr.rule_at("transfer_fee_each_side", d, "stock") == 0.00002
        for m in ("XSHG", "XSHE", "XSHG+XSHE"):
            assert mr.rule_at("transfer_fee_each_side", d, "stock", m) == 0.00002
        assert mr.rule_at("transfer_fee_each_side", d, "bse_stock", "BJSE") == 0.000025
        with pytest.raises(KeyError):
            mr.rule_at("transfer_fee_each_side", d, "stock", "BJSE")
    assert mr.rule_at("transfer_fee_each_side", "2022-04-29", "stock", "BJSE") == 0.00001
    c = mr.coverage(None, "stock", ["transfer_fee_each_side"], "2021-11-15", "2022-04-29")
    assert c["status"] == "complete", c
    assert mr.rule_at("stamp_duty_buy", "2008-09-18") == 0.001 and mr.rule_at("stamp_duty_buy", "2008-09-19") == 0
    assert mr.rule_at("stamp_duty_sell", "2007-05-30") == 0.003
    assert mr.rule_at("price_limit_pct", "2020-08-23", "chinext", "XSHE") == 0.10
    assert mr.rule_at("price_limit_pct", "2020-08-24", "chinext", "XSHE") == 0.20
    assert mr.rule_at("price_limit_pct", "2018-06-14", "ipo_day1_main", "XSHG") == {"up": 0.44, "down": 0.36}
    assert mr.rule_at("price_limit_pct", "2018-06-14", "ipo_day1_main", "XSHE") == {"up": 0.44, "down": 0.36}
    assert mr.rule_at("price_limit_pct", "2024-01-30", "ipo_first5_main", "XSHG+XSHE") == "unlimited"


def test_source_audit_corrections_2026_10_24():
    """Dates corrected by the primary-source audit (see docs/sources-audit-2026-10-24.md)."""
    # SZSE had no full-day 64%-144% band until 2014-06-13 (listing day stayed unlimited there)
    assert mr.rule_at("price_limit_pct", "2014-03-01", "ipo_day1_main", "XSHE") == "unlimited"
    assert mr.rule_at("price_limit_pct", "2014-03-01", "ipo_day1_main", "XSHG") == {"up": 0.44, "down": 0.36}
    assert mr.rule_at("price_limit_pct", "2014-07-01", "ipo_day1_main", "XSHE") == {"up": 0.44, "down": 0.36}
    # main-board first-5-days-unlimited applies from the first registration-based listing, 2023-04-10
    with pytest.raises(KeyError):
        mr.rule_at("price_limit_pct", "2023-03-01", "ipo_first5_main", "XSHG+XSHE")
    assert mr.rule_at("price_limit_pct", "2023-04-10", "ipo_first5_main", "XSHG+XSHE") == "unlimited"
    assert mr.rule_at("price_limit_pct", "2023-03-01", "ipo_day1_main", "XSHG") == {"up": 0.44, "down": 0.36}
    # main-board ST band 5% -> 10% on 2026-07-06
    assert mr.rule_at("price_limit_pct", "2026-07-05", "st_main") == 0.05
    assert mr.rule_at("price_limit_pct", "2026-07-06", "st_main") == 0.10


def test_every_verified_record_has_official_source_with_quote():
    for r in mr.records():
        if r.verification == "verified":
            assert any(s.get("kind") == "official" and s.get("quote") for s in r.sources), r.id


def test_refuses_without_rule():
    with pytest.raises(KeyError):
        mr.rule_at("stamp_duty_sell", "2005-01-01")
    with pytest.raises(KeyError):
        mr.rule_at("price_limit_pct", "1990-01-01", "main_board")


def test_rounding_is_half_up_not_bankers():
    assert mr.round_half_up(4.30 * 1.10) == 4.73
    assert mr.round_half_up(2.675) == 2.68  # Python round(2.675, 2) == 2.67
    assert mr.round_half_up(13.585) == 13.59  # 福耀 2015-07-09 case from dbl_common's notes


def test_limit_price_examples():
    assert mr.limit_price(10.0, "chinext", "2021-03-01", "XSHE") == (12.0, 8.0)
    assert mr.limit_price(10.0, "ipo_day1_main", "2018-06-14", "XSHG") == (14.4, 6.4)
    assert mr.limit_price(10.0, "ipo_first5_main", "2024-01-30", "XSHG+XSHE") is None


def test_citation_pins_bytes():
    c = mr.citation(short=False)
    dg = mr.dataset_digest()
    assert c == f"rules: marina-rules@{mr.VERSION} sha256:{dg} code: marina-rules-core@{mr.__version__}"
    assert mr.citation() == f"rules: marina-rules@{mr.VERSION} sha256:{dg[:16]} code: marina-rules-core@{mr.__version__}"


def test_scope_registry_covers_every_scope_in_data():
    reg = mr.scopes("cn")
    used = {r.scope for r in mr.records() if r.file.startswith("cn/")}
    assert used <= set(reg), f"scopes used in data but not registered: {used - set(reg)}"
    for name, spec in reg.items():
        for ex in spec["excludes"]:
            assert ex in reg, f"{name} excludes unknown scope {ex}"


def test_coverage_complete_partial_unsupported():
    c = mr.coverage("XSHE", "chinext", ["price_limit_pct"], "2019-01-01", "2026-10-19")
    assert c["status"] == "complete" and not c["gaps"] and not c["conflicts"]
    assert "st_status" in c["required_context"]
    # SZSE listing day 2014-01..06: still "unlimited" under the pre-2014-06-13 record, then the 64-144% band → complete
    c = mr.coverage("XSHE", "ipo_day1_main", ["price_limit_pct"], "2014-01-01", "2015-01-01")
    assert c["status"] == "complete" and len(c["records"]) == 2
    assert mr.rule_at("price_limit_pct", "2014-03-01", "ipo_day1_main", "XSHE") == "unlimited"
    c = mr.coverage("XSHG", "lof_gold", ["price_limit_pct"], "2024-01-01", "2025-01-01")
    assert c["status"] == "unsupported" and c["scope_known"] is False   # not a scope at all
    c = mr.coverage("XSHG", "etf", ["price_limit_pct"], "2024-01-01", "2025-01-01")
    assert c["status"] == "complete"
    c = mr.coverage("XSHG+XSHE", "stock", ["stamp_duty_sell"], "2005-01-01", "2010-01-01")
    assert c["status"] == "partial" and c["gaps"][0]["to"] == "2005-01-24"   # bilateral regime recorded from 财税〔2005〕11号


def test_coverage_verification_is_the_weakest_record():
    c = mr.coverage("XSHG+XSHE", "stock", ["stamp_duty_sell", "transfer_fee_each_side"], "2019-01-01", "2026-10-19")
    assert c["verification"] == "verified"


def test_no_overlapping_records_in_dataset():
    # loader already refuses overlaps; this pins the behaviour with a synthetic case
    from marina_rules import Record, _reject_overlaps
    mk = lambda i, f, t: Record(id=i, market="X", scope="s", rule="r", value=1, effective_from=f, effective_to=t,
                                verification="verified", sources=(), notes="", file="x")
    _reject_overlaps([mk("a", "2020-01-01", "2021-01-01"), mk("b", "2021-01-01", None)])
    with pytest.raises(ValueError):
        _reject_overlaps([mk("a", "2020-01-01", None), mk("b", "2021-01-01", None)])


def test_published_at_never_after_effective_from():
    for r in mr.records():
        if r.published_at:
            assert r.published_at <= r.effective_from, f"{r.id}: published_at {r.published_at} after effect {r.effective_from}"
        assert r.recorded_at, f"{r.id}: recorded_at missing"


def test_star_has_risk_warnings_and_same_band():
    # D-0016: STAR does have *ST (2019) and ST (2024-10-30); the band stays 20%. 'star' must require st_status.
    assert "st_status" in mr.scopes("cn")["star"]["requires"]
    assert mr.rule_at("price_limit_pct", "2026-06-11", "st_star", "XSHG") == 0.2
    assert mr.rule_at("price_limit_pct", "2026-06-11", "star", "XSHG") == 0.2
    with pytest.raises(KeyError):
        mr.rule_at("price_limit_pct", "2019-07-19", "st_star", "XSHG")


def test_convertible_day1_is_relative_to_issue_price():
    # distinct rule name so limit_price(prev_close, ...) cannot be misapplied
    assert mr.rule_at("price_limit_pct_of_issue_price", "2023-01-05", "convertible_day1") == {"up": 0.573, "down": 0.433}
    with pytest.raises(KeyError):
        mr.rule_at("price_limit_pct", "2023-01-05", "convertible_day1")
    # before the 2022 rules: no band (2006 rules limit only stocks and funds; SZSE: 可转债交易不设价格涨跌幅限制)
    assert mr.rule_at("price_limit_pct", "2022-07-29", "convertible") == "unlimited"
    assert mr.limit_price(130.0, "convertible", "2022-07-29", "XSHE") is None
    assert mr.rule_at("price_limit_pct_of_issue_price", "2022-07-29", "convertible_day1") == "unlimited"
    with pytest.raises(KeyError):   # G-0001: before the 2006 rules nothing is recorded
        mr.rule_at("price_limit_pct", "2006-06-30", "convertible")


def test_one_tick_floor_is_exchange_and_date_specific():
    # SZSE's own worked example (2011 investor education): preclose 0.04, 10% band → [0.03, 0.05], not [0.04, 0.04]
    assert mr.limit_price(0.04, "main_board", "2011-03-01", "XSHE") == (0.05, 0.03)
    assert mr.limit_price(0.04, "main_board", "2011-02-25", "XSHE") == (0.04, 0.04)   # three days earlier: rounding only
    # SSE adopted the floor with the 2023 rules, effective 2023-04-10
    assert mr.limit_price(0.04, "main_board", "2023-04-07", "XSHG") == (0.04, 0.04)
    assert mr.limit_price(0.04, "main_board", "2023-04-10", "XSHG") == (0.05, 0.03)
    # 5% band: the floor bites up to preclose 0.09 (0.09*1.05=0.0945→0.09)
    assert mr.limit_price(0.09, "st_main", "2024-06-14", "XSHE") == (0.10, 0.08)
    assert mr.limit_price(0.10, "st_main", "2024-06-14", "XSHE") == (0.11, 0.09)   # 0.105 → half-up 0.11, no floor needed
    # ordinary prices unchanged and need no market
    assert mr.limit_price(10.0, "main_board", "2024-06-14") == (11.0, 9.0)
    assert mr.limit_price(0.81, "st_main", "2024-06-14", "XSHE") == (0.85, 0.77)


def test_one_tick_boundary_refuses_without_market():
    with pytest.raises(ValueError):
        mr.limit_price(0.04, "main_board", "2024-06-14")
    # a single-exchange scope (only XSHG records) whose band rounds below a tick: the market must still be explicit
    with pytest.raises(ValueError):
        mr.limit_price(0.02, "delisting_day1_star", "2020-06-01")


def test_sse_delisting_board_cent_band_is_scope_specific():
    # 2013 measures art. 7: preclose strictly below ¥0.05 → ±¥0.01, years before SSE's general floor (2023-04-10)
    assert mr.limit_price(0.04, "delisting", "2015-06-01", "XSHG") == (0.05, 0.03)
    assert mr.limit_price(0.04, "main_board", "2015-06-01", "XSHG") == (0.04, 0.04)   # same day, ordinary stock: rounding only
    # exactly 0.05: '低于' excludes it in 2013 → 10% rounding, down limit == preclose
    assert mr.limit_price(0.05, "delisting", "2015-06-01", "XSHG") == (0.06, 0.05)
    # 2020-12 revision: '低于或等于' → the band now applies at 0.05
    assert mr.limit_price(0.05, "delisting", "2021-01-04", "XSHG") == (0.06, 0.04)
    # day 1 had a band before 2020-12-31, so the same clause applied; from 2020-12-31 day 1 is unlimited
    assert mr.limit_price(0.03, "delisting_day1", "2015-06-01", "XSHG") == (0.04, 0.02)
    assert mr.limit_price(0.03, "delisting_day1", "2021-01-04", "XSHG") is None
    # after 2023-04-10 the measures are repealed: falls back to the scope-'stock' one-tick floor, same result at 0.05
    assert mr.limit_price(0.05, "delisting", "2024-06-14", "XSHG") == (0.06, 0.04)
    # prices above the threshold: ordinary 10%
    assert mr.limit_price(0.06, "delisting", "2015-06-01", "XSHG") == (0.07, 0.05)
    assert mr.limit_price(10.0, "delisting", "2015-06-01", "XSHG") == (11.0, 9.0)


def test_min_tick_lookup_prefers_scope_then_stock():
    assert mr.min_tick_band("delisting", "2015-06-01", "XSHG") is True     # scope-specific record
    assert mr.min_tick_band("main_board", "2015-06-01", "XSHG") is False   # no stock-level SSE floor yet
    assert mr.min_tick_band("delisting", "2024-06-14", "XSHG") is True     # falls back to scope 'stock'
    assert mr.min_tick_band("delisting", "2015-06-01", "XSHE") is True     # SZSE stock-level floor since 2011
    with pytest.raises(ValueError):
        mr.min_tick_band("delisting", "2015-06-01")


def test_star_delisting_day1_band_changed_in_december_2020():
    assert mr.rule_at("price_limit_pct", "2020-12-30", "delisting_day1_star", "XSHG") == 0.2
    assert mr.rule_at("price_limit_pct", "2020-12-31", "delisting_day1_star", "XSHG") == "unlimited"
    assert mr.rule_at("price_limit_pct", "2024-06-14", "delisting_day1_star", "XSHG") == "unlimited"


def test_szse_delisting_and_2006_extensions():
    assert mr.rule_at("price_limit_pct", "2015-06-01", "delisting", "XSHE") == 0.1
    assert mr.rule_at("price_limit_pct", "2015-06-01", "delisting_day1", "XSHE") == 0.1
    assert mr.rule_at("price_limit_pct", "2015-06-01", "delisting_chinext", "XSHE") == 0.1
    with pytest.raises(KeyError):   # G-0016: band depended on the entry date
        mr.rule_at("price_limit_pct", "2020-09-15", "delisting_chinext", "XSHE")
    with pytest.raises(KeyError):   # G-0010
        mr.rule_at("price_limit_pct", "2012-12-14", "delisting", "XSHE")
    assert mr.rule_at("min_holding_days", "2006-07-03", "b_share", "XSHG+XSHE") == 1
    with pytest.raises(KeyError):   # G-0014 shrunk to before 2006-07-01
        mr.rule_at("min_holding_days", "2006-06-30", "b_share", "XSHG+XSHE")
    assert mr.tick_size("main_board", "2006-07-03", "XSHG") == 0.01
    assert mr.tick_size("b_share", "2006-07-03", "XSHE") == 0.01


def test_tick_size_by_instrument_family():
    assert mr.tick_size("main_board", "2024-01-05", "XSHG") == 0.01
    assert mr.tick_size("etf", "2024-01-05", "XSHE") == 0.001
    assert mr.tick_size("b_share", "2024-01-05", "XSHG") == 0.001   # USD
    assert mr.tick_size("b_share", "2024-01-05", "XSHE") == 0.01    # HKD
    # SSE B-share tick: the 2011-02-28 cut is only an alignment date (released id, kept); both sides verified, same value
    a, b = (mr.record_at("tick_size", d, "b_share", "XSHG") for d in ("2011-02-25", "2024-01-05"))
    assert (a.id, b.id) == ("cn.tick.b_share.sse.2006-07-01", "cn.tick.b_share.sse.2011-02-28")
    assert a.value == b.value == 0.001 and a.verification == b.verification == "verified"
    # SZSE convertible tick 2011-02-28..2012-12-10: two official texts disagree (0.01 vs 0.001) -> unverified
    assert mr.record_at("tick_size", "2012-06-01", "convertible", "XSHE").verification == "unverified"
    assert mr.record_at("tick_size", "2013-06-03", "convertible", "XSHE").verification == "verified"
    assert mr.limit_price(1.0, "etf", "2024-01-05", "XSHG") == (1.1, 0.9)
    assert mr.limit_price(1.234, "etf", "2024-01-05", "XSHG") == (1.357, 1.111)   # 3-decimal rounding for funds


def test_limit_price_substitutes_a_tick_for_a_share_stocks_before_2006_only():
    # G-0005: the A-share tick before 2006-07-01 is not sourced; 0.01 is the only value it ever had
    assert mr.limit_price(1.234, "main_board", "2005-01-05", "XSHG") == (1.36, 1.11)
    assert mr.limit_price(1.234, "st_main", "2005-01-05") == (1.3, 1.17)
    assert mr.limit_price(1.234, "main_board", "2005-01-05", "XSHG", strict=True) == (1.36, 1.11)
    # a fund or a B share has a band from 1996 / 1998 but no tick before 2006-07-01: nothing to round at, no guess
    for scope, market in (("etf", "XSHG"), ("etf", None), ("b_share", "XSHG"), ("b_share", "XSHE"),
                          ("st_b_share", "XSHE")):
        for strict in (False, True):
            with pytest.raises(KeyError) as e:
                mr.limit_price(1.234, scope, "2006-06-30", market, strict=strict)
            msg = e.value.args[0]
            assert "tick_size" in msg and "G-0005" in msg and "2006-07-01" in msg and "decimals" in msg
            assert not isinstance(e.value, (mr.NotYetPublished, mr.PublicationUnknown))
        with pytest.raises(KeyError):
            mr.tick_size(scope, "2006-06-30", market)
    # the caller's own grid is still accepted, and the first recorded day answers as before
    assert mr.limit_price(1.234, "etf", "2006-06-30", "XSHG", decimals=3) == (1.357, 1.111)
    assert mr.limit_price(1.234, "etf", "2006-07-03", "XSHG") == (1.357, 1.111)
    assert mr.limit_price(1.234, "b_share", "2006-07-03", "XSHE") == (1.36, 1.11)


def test_limit_price_does_not_substitute_where_a_stock_tick_record_exists_but_is_not_usable(monkeypatch):
    # the substitution is for dates with no stock tick record at all; a record that may not be used is a refusal
    def refused(scope, date, market=None, strict=False, as_of=None):
        raise KeyError(f"no tick_size/stock rule in force on {date} (strict)")
    monkeypatch.setattr(mr, "_agreed_tick", refused)
    with pytest.raises(KeyError, match="tick_size"):
        mr.limit_price(10.0, "main_board", "2020-01-02", "XSHG", strict=True)
    assert mr.limit_price(10.0, "main_board", "2005-01-05", "XSHG") == (11.0, 9.0)


def test_known_gaps_are_well_formed_and_do_not_overlap_records():
    gaps = mr.known_gaps("cn")
    ids = [g["gap_id"] for g in gaps]
    assert len(ids) == len(set(ids)) and all(i.startswith("G-") for i in ids)
    for g in gaps:
        assert g["status"] in ("open", "pending", "wontfix") and g["severity"] in ("low", "medium", "high")
        assert g["reason"].strip()
        # a declared gap must actually be a gap: no record of that key may be in force inside it
        g0, g1 = g["interval"]["from"] or "0000-01-01", g["interval"]["to"] or "9999-12-31"
        for r in mr.records():
            if r.scope == g["scope"] and r.rule == g["rule"] and set(r.market.split("+")) & set(g["market"].split("+")):
                r1 = r.effective_to or "9999-12-31"
                if not (r.effective_from < g1 and g0 < r1):
                    continue
                # overlapping in time is allowed only between a selector gap and a selector record covering other
                # contracts (e.g. "every contract except AU2506" next to the AU2506 record)
                assert g.get("contracts") is not None and r.contracts is not None, \
                    f"{g['gap_id']} overlaps record {r.id}: close the gap or shrink it"
                lo, hi = max(g0, r.effective_from), min(g1, r1)
                both = mr._selector_overlap(g["contracts"], r.contracts, r.scope, lo, None if hi == "9999-12-31" else hi)
                assert both is None, f"{g['gap_id']} and {r.id} both cover {both}"


def test_coverage_distinguishes_known_unknown_from_blind_spot():
    known = mr.coverage("XSHG+XSHE", "bse_st_unsourced", ["price_limit_pct"], "2024-01-01", "2025-01-01")
    blind = mr.coverage("XSHG", "unicorn", ["price_limit_pct"], "2024-01-01", "2025-01-01")
    assert known["status"] == blind["status"] == "unsupported"
    assert known["known_gap_ids"] == [] and blind["known_gap_ids"] == []
    partial = mr.coverage("XSHG+XSHE", "convertible", ["price_limit_pct"], "2005-01-01", "2026-10-20")
    assert partial["status"] == "partial" and partial["gaps"][0]["known_gap_ids"] == ["G-0001"]


def test_same_day_fund_types_and_ordinary_funds():
    for sc in ("etf_bond", "etf_money", "etf_gold", "etf_crossborder"):
        assert mr.rule_at("min_holding_days", "2015-01-19", sc, "XSHG+XSHE") == 0
    # 2013 switch dates now sourced (2026.10.26.7): first rule / first listing per exchange
    assert mr.rule_at("min_holding_days", "2015-01-16", "etf_bond", "XSHG+XSHE") == 0
    assert mr.rule_at("min_holding_days", "2013-03-15", "etf_bond", "XSHG") == 0
    assert mr.rule_at("min_holding_days", "2013-07-27", "etf_gold", "XSHG") == 0
    assert mr.rule_at("min_holding_days", "2013-06-03", "etf_money", "XSHG") == 1      # before the 2013-12-09 revision
    assert mr.rule_at("min_holding_days", "2013-12-09", "etf_money", "XSHG+XSHE") == 0
    for sc, d in (("etf_bond", "2013-03-14"), ("etf_gold", "2013-07-26"), ("etf_money", "2013-01-25")):
        with pytest.raises(KeyError):   # before the type existed: G-0019..G-0021, outside the coverage denominator
            mr.rule_at("min_holding_days", d, sc, "XSHG")
    assert mr.rule_at("min_holding_days", "2015-01-16", "etf_crossborder", "XSHG+XSHE") == 1
    assert mr.rule_at("min_holding_days", "2019-01-11", "etf_commodity", "XSHE") == 0
    assert mr.rule_at("min_holding_days", "2019-01-10", "etf_commodity", "XSHE") == 1
    assert mr.rule_at("min_holding_days", "2020-01-17", "etf_commodity", "XSHG") == 1
    assert mr.rule_at("min_holding_days", "2020-01-20", "etf_commodity", "XSHG") == 0
    assert mr.rule_at("min_holding_days", "2024-06-14", "etf", "XSHG+XSHE") == 1
    # new fund scopes share the fund tick and band family
    assert mr.tick_size("etf_gold", "2024-01-05", "XSHG") == 0.001


def test_session_schedule_per_exchange():
    szse = mr.rule_at("session_schedule", "2010-06-01", "stock", "XSHE")
    assert szse["close_call"] == ["14:57", "15:00"] and szse["continuous"][1] == ["13:00", "14:57"]
    assert mr.rule_at("session_schedule", "2018-08-17", "stock", "XSHG")["close_call"] is None
    assert mr.rule_at("session_schedule", "2018-08-20", "stock", "XSHG")["close_call"] == ["14:57", "15:00"]
    assert mr.rule_at("session_schedule", "2026-07-03", "etf", "XSHG")["continuous"][1] == ["13:00", "15:00"]
    assert mr.rule_at("session_schedule", "2026-07-06", "etf", "XSHG")["close_call"] == ["14:57", "15:00"]
    with pytest.raises(KeyError):   # G-0007
        mr.rule_at("session_schedule", "2006-06-30", "stock", "XSHE")


def test_cffex_index_futures_margin_and_fees():
    # 2020 National Day: 13% from settlement 2020-09-29; IF/IH 11% after 10-09, IC stays 13%
    assert mr.rule_at("margin_ratio", "2020-09-28", "cffex_if", "CCFX") == 0.10
    assert mr.rule_at("margin_ratio", "2020-10-01", "cffex_if", "CCFX") == 0.13
    assert mr.rule_at("margin_ratio", "2020-10-09", "cffex_ih", "CCFX") == 0.11
    assert mr.rule_at("margin_ratio", "2020-10-09", "cffex_ic", "CCFX") == 0.13
    assert mr.rule_at("margin_ratio", "2023-05-04", "cffex_ic", "CCFX") == 0.12
    with pytest.raises(KeyError):   # IM listed 2022-07-22
        mr.rule_at("margin_ratio", "2022-07-21", "cffex_im", "CCFX")
    # IH is its own scope with the same margin history as IF
    for r in mr.records():
        if r.scope == "cffex_if" and r.rule == "margin_ratio":
            ih = mr.record_at(r.rule, r.effective_from, "cffex_ih", "CCFX")
            assert (ih.value, ih.effective_from, ih.effective_to) == (r.value, r.effective_from, r.effective_to), r.id
    # close-today fee is NOT the XML JG_TRANSFEE_RATE (that is the delivery fee)
    assert mr.rule_at("close_today_fee_rate", "2023-03-17", "cffex_index_futures", "CCFX") == 0.000345
    assert mr.rule_at("close_today_fee_rate", "2023-03-20", "cffex_index_futures", "CCFX") == 0.00023
    assert mr.rule_at("delivery_fee_rate", "2021-08-16", "cffex_index_futures", "CCFX") == 0.00005
    assert mr.rule_at("trans_fee_rate", "2024-06-14", "cffex_index_futures", "CCFX") == 0.000023
    # A-share scopes never answer a futures question and vice versa
    with pytest.raises(KeyError):
        mr.rule_at("margin_ratio", "2024-06-14", "stock")
    c = mr.coverage("CCFX", "cffex_if", ["margin_ratio"], "2015-09-07", "2026-10-25")
    assert c["status"] == "complete" and c["verification"] == "verified"
    # close-today fee: notice + settlement-parameter CSV (2026.11.02)
    c = mr.coverage("CCFX", "cffex_index_futures", ["close_today_fee_rate"], "2015-08-26", "2026-10-25")
    assert c["status"] == "complete" and c["verification"] == "verified"
    # delivery fee 1/10,000 from the IH/IC listing day 2015-04-16 (was answered only from 2018-12-03 before 2026.11.02)
    r = mr.record_at("delivery_fee_rate", "2016-06-01", "cffex_index_futures", "CCFX")
    assert (r.value, r.effective_from, r.verification) == (0.0001, "2015-04-16", "verified")
    with pytest.raises(KeyError):
        mr.rule_at("delivery_fee_rate", "2015-04-15", "cffex_index_futures", "CCFX")
    # delivery fee 2024-01-01..2024-01-08 is inferred from two notices, so a window over it stays single-source
    c = mr.coverage("CCFX", "cffex_index_futures", ["delivery_fee_rate"], "2023-12-01", "2024-02-01")
    assert c["status"] == "complete" and c["verification"] == "single-source"


def test_cffex_index_futures_trading_rules():
    from marina_rules.contract import resolve

    rule = "price_limit_pct_of_prev_settlement"
    for date, scope, value in (("2012-06-01", "cffex_if", 0.1),
                               ("2016-01-05", "cffex_ih", 0.07),
                               ("2016-01-08", "cffex_ic", 0.1)):
        decision = resolve(rule, date, scope, "CCFX")
        assert decision["status"] == "DETERMINED"
        assert decision["result"]["value"] == value
    assert mr.rule_at("session_schedule", "2015-06-01", "cffex_if", "CCFX") == {
        "open_call": ["09:10", "09:15"],
        "continuous": [["09:15", "11:30"], ["13:00", "15:15"]],
        "close_call": None,
    }
    assert mr.rule_at("session_schedule", "2024-06-14", "cffex_im", "CCFX") == {
        "open_call": ["09:25", "09:30"],
        "continuous": [["09:30", "11:30"], ["13:00", "15:00"]],
        "close_call": None,
    }
    assert mr.rule_at("min_holding_days", "2024-06-14", "cffex_if", "CCFX") == 0
    assert resolve("min_holding_days", "2024-06-14", "cffex_if", "CCFX",
                   min_verification="verified")["status"] == "UNVERIFIED"
    with pytest.raises(KeyError):  # IH had not yet listed.
        mr.rule_at(rule, "2015-04-15", "cffex_ih", "CCFX")
    with pytest.raises(KeyError):
        mr.rule_at(rule, "2024-06-14", "stock", "XSHG")


def test_cffex_bond_futures_rules():
    from marina_rules.contract import resolve

    rule = "price_limit_pct_of_prev_settlement"
    assert mr.rule_at(rule, "2016-06-01", "cffex_t", "CCFX") == 0.02
    assert mr.rule_at("margin_ratio", "2020-10-08", "cffex_ts", "CCFX") == 0.006
    assert mr.rule_at("session_schedule", "2024-06-14", "cffex_tl", "CCFX") == {
        "open_call": ["09:25", "09:30"],
        "continuous": [["09:30", "11:30"], ["13:00", "15:15"]],
        "close_call": None,
    }
    for name in (rule, "margin_ratio"):
        assert mr.rule_at(name, "2015-03-15", "cffex_tf", "CCFX") == 0.015
        for date in ("2015-03-16", "2015-06-01", "2015-09-11"):
            with pytest.raises(KeyError):
                mr.rule_at(name, date, "cffex_tf", "CCFX")
            assert resolve(name, date, "cffex_tf", "CCFX")["status"] == "OUT_OF_COVERAGE"
        for date in ("2015-09-12", "2015-09-14"):
            assert mr.rule_at(name, date, "cffex_tf", "CCFX") == 0.012
        gap = next(g for g in mr.known_gaps("cn") if g["scope"] == "cffex_tf" and g["rule"] == name)
        assert gap["interval"] == {"from": "2015-03-16", "to": "2015-09-12"}
        assert gap["market"] == "CCFX" and gap["severity"] == "medium"
        assert resolve(name, "2015-06-01", "cffex_tf", "CCFX")["known_gap_ids"] == [gap["gap_id"]]
    with pytest.raises(KeyError):
        mr.rule_at("margin_ratio", "2018-08-16", "cffex_ts", "CCFX")
    assert mr.rule_at("delivery_fee_per_lot", "2022-06-01", "cffex_t", "CCFX") == 2.5
    assert mr.rule_at("trans_fee_per_lot", "2024-06-14", "cffex_tf", "CCFX") == 3
    assert mr.rule_at("min_holding_days", "2024-06-14", "cffex_tf", "CCFX") == 0
    assert resolve("min_holding_days", "2024-06-14", "cffex_tf", "CCFX",
                   min_verification="verified")["status"] == "UNVERIFIED"


def test_shfe_nonferrous_futures_rules():
    from marina_rules.contract import resolve

    band = "price_limit_pct_of_prev_settlement"
    assert mr.rule_at("margin_ratio", "2024-02-08", "shfe_cu", "XSGE") == 0.1      # 2024 Spring Festival raise
    assert mr.rule_at(band, "2024-10-24", "shfe_ao", "XSGE") == 0.09
    assert mr.rule_at("margin_ratio", "2025-10-15", "shfe_ni", "XSGE") == 0.1
    assert mr.rule_at("session_schedule", "2024-06-14", "shfe_cu", "XSGE") == {
        "open_call": ["20:55", "21:00"],
        "night": ["21:00", "01:00"],
        "day_call": ["08:55", "09:00"],
        "continuous": [["09:00", "10:15"], ["10:30", "11:30"], ["13:30", "15:00"]],
        "close_call": None,
    }
    # coverage floor 2024-01-01, but the record in force then starts at its real change date
    rec = mr.record_at("margin_ratio", "2023-12-31", "shfe_cu", "XSGE")
    assert (rec.id, rec.value) == ("cn.futures.margin_ratio.shfe_cu.2023-10-09", 0.08)
    with pytest.raises(KeyError):
        mr.rule_at("margin_ratio", "2023-10-08", "shfe_cu", "XSGE")
    # 2026 already-listed vs new-contract levels: declared gap, no guess
    with pytest.raises(KeyError):
        mr.rule_at("margin_ratio", "2026-06-01", "shfe_cu", "XSGE")
    gap = next(g for g in mr.known_gaps("cn") if g["scope"] == "shfe_cu" and g["rule"] == "margin_ratio"
               and g["interval"]["from"] <= "2026-06-01" < (g["interval"]["to"] or "9999-12-31"))
    assert gap["market"] == "XSGE" and gap["interval"] == {"from": "2026-05-06", "to": "2026-09-29"}
    d = resolve("margin_ratio", "2026-06-01", "shfe_cu", "XSGE")
    assert d["status"] == "OUT_OF_COVERAGE" and d["known_gap_ids"] == [gap["gap_id"]]
    assert resolve("min_holding_days", "2024-06-14", "shfe_sn", "XSGE",
                   min_verification="verified")["status"] == "UNVERIFIED"
    with pytest.raises(KeyError):
        mr.rule_at(band, "2024-06-14", "shfe_cu", "XSHG")


def test_shfe_precious_ferrous_futures_rules():
    from marina_rules.contract import resolve

    band = "price_limit_pct_of_prev_settlement"
    day = [["09:00", "10:15"], ["10:30", "11:30"], ["13:30", "15:00"]]
    assert mr.rule_at("margin_ratio", "2024-08-15", "shfe_au", "XSGE") == 0.12
    assert mr.rule_at(band, "2025-07-15", "shfe_rb", "XSGE") == 0.05
    assert mr.rule_at("session_schedule", "2024-06-14", "shfe_ag", "XSGE") == {
        "open_call": ["20:55", "21:00"],
        "night": ["21:00", "02:30"],
        "day_call": ["08:55", "09:00"],
        "continuous": day,
        "close_call": None,
    }
    # wire rod has no night session: the opening call is the pre-day auction, no separate day_call
    assert mr.rule_at("session_schedule", "2024-06-14", "shfe_wr", "XSGE") == {
        "open_call": ["08:55", "09:00"],
        "night": None,
        "day_call": None,
        "continuous": day,
        "close_call": None,
    }
    # coverage floor 2024-01-01, but the record in force then starts at its real change date
    rec = mr.record_at("margin_ratio", "2024-01-01", "shfe_wr", "XSGE")
    assert (rec.id, rec.value) == ("cn.futures.margin_ratio.shfe_wr.2023-07-19", 0.09)
    with pytest.raises(KeyError):
        mr.rule_at("margin_ratio", "2023-10-08", "shfe_au", "XSGE")
    # 2024-07-31 RB2410 special margin: general months carry two values, declared gap, no guess
    with pytest.raises(KeyError):
        mr.rule_at("margin_ratio", "2024-08-05", "shfe_rb", "XSGE")
    gap = next(g for g in mr.known_gaps("cn") if g["scope"] == "shfe_rb" and g["rule"] == "margin_ratio"
               and g["interval"]["from"] <= "2024-08-05" < (g["interval"]["to"] or "9999-12-31"))
    assert gap["market"] == "XSGE" and gap["interval"] == {"from": "2024-07-31", "to": "2024-08-16"}
    d = resolve("margin_ratio", "2024-08-05", "shfe_rb", "XSGE")
    assert d["status"] == "OUT_OF_COVERAGE" and d["known_gap_ids"] == [gap["gap_id"]]
    assert resolve("min_holding_days", "2024-06-14", "shfe_hc", "XSGE",
                   min_verification="verified")["status"] == "UNVERIFIED"


def test_shfe_energy_chem_futures_rules():
    from marina_rules.contract import resolve

    band = "price_limit_pct_of_prev_settlement"
    day = [["09:00", "10:15"], ["10:30", "11:30"], ["13:30", "15:00"]]
    assert mr.rule_at("margin_ratio", "2024-06-14", "shfe_fu", "XSGE") == 0.1
    assert mr.rule_at(band, "2024-06-14", "shfe_ru", "XSGE") == 0.06
    assert mr.rule_at("session_schedule", "2025-07-01", "shfe_ad", "XSGE") == {
        "open_call": ["20:55", "21:00"],
        "night": ["21:00", "01:00"],
        "day_call": ["08:55", "09:00"],
        "continuous": day,
        "close_call": None,
    }
    assert mr.rule_at("session_schedule", "2024-06-14", "shfe_fu", "XSGE")["night"] == ["21:00", "23:00"]
    # coverage floor 2024-01-01, but the record in force then starts at its real change date
    rec = mr.record_at("margin_ratio", "2024-01-01", "shfe_fu", "XSGE")
    assert (rec.id, rec.value) == ("cn.futures.margin_ratio.shfe_fu.2023-12-28", 0.11)
    # new products are covered from their listing day; the listing-day double band is not the ordinary band
    assert mr.rule_at("margin_ratio", "2025-06-10", "shfe_ad", "XSGE") == 0.09
    assert mr.rule_at(band, "2025-06-10", "shfe_ad", "XSGE") == 0.07
    assert mr.rule_at("margin_ratio", "2025-09-10", "shfe_op", "XSGE") == 0.08
    with pytest.raises(KeyError):
        mr.rule_at("margin_ratio", "2025-09-09", "shfe_op", "XSGE")
    assert resolve("margin_ratio", "2025-09-09", "shfe_op", "XSGE")["status"] == "OUT_OF_COVERAGE"
    # 2026-10-12 named BU contracts raised on their own: general months carry two values, declared gap, no guess
    with pytest.raises(KeyError):
        mr.rule_at("margin_ratio", "2026-10-20", "shfe_bu", "XSGE")
    gap = next(g for g in mr.known_gaps("cn") if g["scope"] == "shfe_bu" and g["rule"] == "margin_ratio"
               and g["interval"]["from"] <= "2026-10-20" < (g["interval"]["to"] or "9999-12-31"))
    assert gap["market"] == "XSGE" and gap["interval"] == {"from": "2026-10-12", "to": "2026-11-17"}
    d = resolve("margin_ratio", "2026-10-20", "shfe_bu", "XSGE")
    assert d["status"] == "OUT_OF_COVERAGE" and d["known_gap_ids"] == [gap["gap_id"]]
    # the split ended when the raised contracts became the two nearest expiries: one value again from 2026-11-17
    assert mr.rule_at("margin_ratio", "2026-11-17", "shfe_bu", "XSGE") == 0.12
    assert resolve("margin_ratio", "2026-11-16", "shfe_bu", "XSGE")["status"] == "OUT_OF_COVERAGE"
    assert resolve("min_holding_days", "2024-06-14", "shfe_br", "XSGE",
                   min_verification="verified")["status"] == "UNVERIFIED"


# SHFE fees, first batch: (scope, rule) -> first day Marina is expected to answer. Every key is covered by records or
# known gaps from that day to the end of the window, without overlap. Per product the trading fee is either a rate
# or per lot (one form throughout the window); the close-today fee likewise.
SHFE_FEE_END = "2026-11-03"
SHFE_FEE_KEYS = {
    ("shfe_cu", "trans_fee_rate"): "2024-01-01", ("shfe_cu", "close_today_fee_rate"): "2024-01-01",
    ("shfe_al", "trans_fee_per_lot"): "2024-01-01", ("shfe_al", "close_today_fee_per_lot"): "2024-01-01",
    ("shfe_zn", "trans_fee_per_lot"): "2024-01-01", ("shfe_zn", "close_today_fee_per_lot"): "2024-01-01",
    ("shfe_pb", "trans_fee_rate"): "2024-01-01", ("shfe_pb", "close_today_fee_rate"): "2024-01-01",
    ("shfe_ni", "trans_fee_per_lot"): "2024-01-01", ("shfe_ni", "close_today_fee_per_lot"): "2024-01-01",
    ("shfe_sn", "trans_fee_per_lot"): "2024-01-01", ("shfe_sn", "close_today_fee_per_lot"): "2024-01-01",
    ("shfe_ao", "trans_fee_rate"): "2024-01-01", ("shfe_ao", "close_today_fee_rate"): "2024-01-01",
    ("shfe_ad", "trans_fee_rate"): "2025-06-10", ("shfe_ad", "close_today_fee_rate"): "2025-06-10",
    ("shfe_au", "trans_fee_per_lot"): "2024-01-01", ("shfe_au", "close_today_fee_per_lot"): "2024-01-01",
    ("shfe_ag", "trans_fee_rate"): "2024-01-01", ("shfe_ag", "close_today_fee_rate"): "2024-01-01",
    ("shfe_rb", "trans_fee_rate"): "2024-01-01", ("shfe_rb", "close_today_fee_rate"): "2024-01-01",
    ("shfe_wr", "trans_fee_rate"): "2024-01-01", ("shfe_wr", "close_today_fee_rate"): "2024-01-01",
    ("shfe_hc", "trans_fee_rate"): "2024-01-01", ("shfe_hc", "close_today_fee_rate"): "2024-01-01",
    ("shfe_ss", "trans_fee_per_lot"): "2024-01-01", ("shfe_ss", "close_today_fee_per_lot"): "2024-01-01",
    ("shfe_fu", "trans_fee_rate"): "2024-01-01", ("shfe_fu", "close_today_fee_rate"): "2024-01-01",
    ("shfe_bu", "trans_fee_rate"): "2024-01-01", ("shfe_bu", "close_today_fee_rate"): "2024-01-01",
    ("shfe_ru", "trans_fee_per_lot"): "2024-01-01", ("shfe_ru", "close_today_fee_per_lot"): "2024-01-01",
    ("shfe_sp", "trans_fee_rate"): "2024-01-01", ("shfe_sp", "close_today_fee_rate"): "2024-01-01",
    ("shfe_br", "trans_fee_rate"): "2024-01-01", ("shfe_br", "close_today_fee_rate"): "2024-01-01",
    ("shfe_op", "trans_fee_rate"): "2025-09-10", ("shfe_op", "close_today_fee_rate"): "2025-09-10",
}
_SHFE_FEE_RULES = {"trans_fee_rate", "trans_fee_per_lot", "close_today_fee_rate", "close_today_fee_per_lot"}


def test_shfe_fee_keys_covered_by_records_or_gaps():
    _fee_keys_covered("XSGE", SHFE_FEE_KEYS, (177, 65, 130, 39))


INE_FEE_KEYS = {
    ("ine_sc", "trans_fee_per_lot"): "2024-01-01", ("ine_sc", "close_today_fee_per_lot"): "2024-01-01",
    ("ine_lu", "trans_fee_rate"): "2024-01-01", ("ine_lu", "close_today_fee_rate"): "2024-01-01",
    ("ine_nr", "trans_fee_rate"): "2024-01-01", ("ine_nr", "close_today_fee_rate"): "2024-01-01",
    ("ine_bc", "trans_fee_rate"): "2024-01-01", ("ine_bc", "close_today_fee_rate"): "2024-01-01",
    ("ine_ec", "trans_fee_rate"): "2024-01-01", ("ine_ec", "close_today_fee_rate"): "2024-01-01",
}


def test_ine_fee_keys_covered_by_records_or_gaps():
    _fee_keys_covered("XINE", INE_FEE_KEYS, (40, 21, 31, 15))


CZCE_FEE_KEYS = {
    ("czce_ap", "close_today_fee_per_lot"): "2024-01-01",
    ("czce_ap", "trans_fee_per_lot"): "2024-01-01",
    ("czce_cf", "close_today_fee_per_lot"): "2024-01-01",
    ("czce_cf", "trans_fee_per_lot"): "2024-01-01",
    ("czce_cj", "close_today_fee_per_lot"): "2024-01-01",
    ("czce_cj", "trans_fee_per_lot"): "2024-01-01",
    ("czce_cy", "close_today_fee_per_lot"): "2024-01-01",
    ("czce_cy", "trans_fee_per_lot"): "2024-01-01",
    ("czce_fg", "close_today_fee_per_lot"): "2024-01-01",
    ("czce_fg", "trans_fee_per_lot"): "2024-01-01",
    ("czce_jr", "close_today_fee_per_lot"): "2024-01-01",
    ("czce_jr", "trans_fee_per_lot"): "2024-01-01",
    ("czce_lr", "close_today_fee_per_lot"): ("2024-01-01", "2026-01-19"),
    ("czce_lr", "trans_fee_per_lot"): ("2024-01-01", "2026-01-19"),
    ("czce_ma", "close_today_fee_rate"): "2024-01-01",
    ("czce_ma", "trans_fee_rate"): "2024-01-01",
    ("czce_oi", "close_today_fee_per_lot"): "2024-01-01",
    ("czce_oi", "trans_fee_per_lot"): "2024-01-01",
    ("czce_pf", "close_today_fee_per_lot"): "2024-01-01",
    ("czce_pf", "trans_fee_per_lot"): "2024-01-01",
    ("czce_pk", "close_today_fee_per_lot"): "2024-01-01",
    ("czce_pk", "trans_fee_per_lot"): "2024-01-01",
    ("czce_pl", "close_today_fee_per_lot"): "2026-06-08",
    ("czce_pl", "close_today_fee_rate"): ("2025-07-22", "2026-06-08"),
    ("czce_pl", "trans_fee_per_lot"): "2026-06-08",
    ("czce_pl", "trans_fee_rate"): ("2025-07-22", "2026-06-08"),
    ("czce_pm", "close_today_fee_per_lot"): "2024-01-01",
    ("czce_pm", "trans_fee_per_lot"): "2024-01-01",
    ("czce_pr", "close_today_fee_rate"): "2024-08-30",
    ("czce_pr", "trans_fee_rate"): "2024-08-30",
    ("czce_px", "close_today_fee_rate"): "2024-01-01",
    ("czce_px", "trans_fee_rate"): "2024-01-01",
    ("czce_ri", "close_today_fee_per_lot"): "2024-01-01",
    ("czce_ri", "trans_fee_per_lot"): "2024-01-01",
    ("czce_rm", "close_today_fee_per_lot"): "2024-01-01",
    ("czce_rm", "trans_fee_per_lot"): "2024-01-01",
    ("czce_rs", "close_today_fee_per_lot"): "2024-01-01",
    ("czce_rs", "trans_fee_per_lot"): "2024-01-01",
    ("czce_sa", "close_today_fee_rate"): "2024-01-01",
    ("czce_sa", "trans_fee_rate"): "2024-01-01",
    ("czce_sf", "close_today_fee_per_lot"): "2024-01-01",
    ("czce_sf", "trans_fee_per_lot"): "2024-01-01",
    ("czce_sh", "close_today_fee_rate"): "2024-01-01",
    ("czce_sh", "trans_fee_rate"): "2024-01-01",
    ("czce_sm", "close_today_fee_per_lot"): "2024-01-01",
    ("czce_sm", "trans_fee_per_lot"): "2024-01-01",
    ("czce_so", "close_today_fee_rate"): ("2026-11-12", "2026-11-19"),   # listed 2026-11-12, after the default window
    ("czce_so", "trans_fee_rate"): ("2026-11-12", "2026-11-19"),
    ("czce_sr", "close_today_fee_per_lot"): "2024-01-01",
    ("czce_sr", "trans_fee_per_lot"): "2024-01-01",
    ("czce_ta", "close_today_fee_per_lot"): "2024-01-01",
    ("czce_ta", "trans_fee_per_lot"): "2024-01-01",
    ("czce_ur", "close_today_fee_rate"): "2024-01-01",
    ("czce_ur", "trans_fee_rate"): "2024-01-01",
    ("czce_wh", "close_today_fee_per_lot"): "2024-01-01",
    ("czce_wh", "trans_fee_per_lot"): "2024-01-01",
    ("czce_zc", "close_today_fee_per_lot"): "2024-01-01",
    ("czce_zc", "trans_fee_per_lot"): "2024-01-01",
}


def test_czce_fee_keys_covered_by_records_or_gaps():
    _fee_keys_covered("XZCE", CZCE_FEE_KEYS, (184, 0, 90, 0))


GFEX_FEE_KEYS = {
    (f"gfex_{p}", rule): start
    for p, start in (("si", "2024-01-01"), ("lc", "2024-01-01"), ("ps", "2024-12-26"), ("pt", "2025-11-27"), ("pd", "2025-11-27"))
    for rule in ("trans_fee_rate", "close_today_fee_rate")
}


def test_gfex_fee_keys_covered_by_records_or_gaps():
    _fee_keys_covered("GFEX", GFEX_FEE_KEYS, (99, 67, 80, 49))


def _fee_keys_covered(market, keys, counts):
    """keys: {(scope, rule): start | (start, end)} — the window each fee key must cover exactly once per contract."""
    recs = [r for r in mr.records() if r.market == market and r.rule in _SHFE_FEE_RULES]
    gaps = [g for g in mr.known_gaps("cn") if g["market"] == market and g["rule"] in _SHFE_FEE_RULES]
    n_rec, n_gap, n_rsel, n_gsel = counts
    assert len(recs) == n_rec and len(gaps) == n_gap
    assert sum(r.contracts is not None for r in recs) == n_rsel and sum(g.get("contracts") is not None for g in gaps) == n_gsel
    assert {(r.scope, r.rule) for r in recs} | {(g["scope"], g["rule"]) for g in gaps} == set(keys)
    for r in recs:
        if r.rule.endswith("_per_lot"):
            assert r.unit == "CNY" and r.value >= 0
        else:
            assert r.unit is None and 0 <= r.value < 0.01
    for key, window in keys.items():
        start, end = (window, SHFE_FEE_END) if isinstance(window, str) else window
        krecs = [r for r in recs if (r.scope, r.rule) == key]
        kgaps = [g for g in gaps if (g["scope"], g["rule"]) == key]
        # every contract (months_to_delivery 0..24) on every boundary date and month start is covered exactly once
        cuts = {start} | {r.effective_from for r in krecs} | {g["interval"]["from"] for g in kgaps}
        cuts |= {f"{y}-{m:02d}-01" for y in (2024, 2025, 2026) for m in range(1, 13)}
        for d in sorted(c for c in cuts if start <= c < end):
            for code in _probe_codes(key[0], d):
                n = sum(r.active_on(d) and r.applies_to(code, d) for r in krecs)
                n += sum((g["interval"]["from"] <= d < (g["interval"]["to"] or "9999-12-31")) and
                         (g.get("contracts") is None or mr.contract_matches(g["contracts"], code, d)) for g in kgaps)
                assert n == 1, f"{key}: {code} on {d} covered {n} times"
        ends = [r.effective_to or "9999-12-31" for r in krecs] + [g["interval"]["to"] or "9999-12-31" for g in kgaps]
        assert max(ends) >= end, key


def test_shfe_fee_rules():
    from marina_rules.contract import resolve

    # TRADEFEERATIO is per mille in the daily file: 0.05 -> 0.00005 of turnover
    assert mr.rule_at("trans_fee_rate", "2025-01-02", "shfe_cu", "XSGE") == 0.00005
    rec = mr.record_at("trans_fee_per_lot", "2024-06-03", "shfe_al", "XSGE")
    assert (rec.value, rec.unit) == (3, "CNY")
    # alumina: raised to 3/10000 from 2024-10-30, cut to 1.5/10000 from 2025-03-11 (both close-today and opening)
    assert mr.rule_at("trans_fee_rate", "2024-11-01", "shfe_ao", "XSGE") == 0.0003
    assert mr.rule_at("trans_fee_rate", "2025-03-12", "shfe_ao", "XSGE") == 0.00015
    assert mr.rule_at("close_today_fee_rate", "2025-03-12", "shfe_ao", "XSGE") == 0.00015
    # cast aluminium alloy: 0.5/10000 and close-today waived (a sourced 0, not a default) from 2025-11-10
    assert mr.rule_at("trans_fee_rate", "2025-11-10", "shfe_ad", "XSGE") == 0.00005
    assert mr.rule_at("close_today_fee_rate", "2025-11-10", "shfe_ad", "XSGE") == 0
    assert mr.rule_at("close_today_fee_rate", "2025-11-07", "shfe_ad", "XSGE") == 0.0001
    # tin close-today CNY 3 per lot once the specially priced SN2504-SN2506 have expired (notice only)
    rec = mr.record_at("close_today_fee_per_lot", "2025-07-01", "shfe_sn", "XSGE")
    assert (rec.value, rec.unit, rec.verification) == (3, "CNY", "single-source")
    assert resolve("close_today_fee_per_lot", "2025-07-01", "shfe_sn", "XSGE",
                   min_verification="verified")["status"] == "UNVERIFIED"
    # before the coverage floor there is no record and no gap
    with pytest.raises(KeyError):
        mr.rule_at("trans_fee_per_lot", "2023-12-29", "shfe_al", "XSGE")
    assert resolve("trans_fee_per_lot", "2023-12-29", "shfe_al", "XSGE")["known_gap_ids"] == []

    def in_gap(rule, date, scope, gap_id=None):
        with pytest.raises(KeyError):
            mr.rule_at(rule, date, scope, "XSGE")
        d = resolve(rule, date, scope, "XSGE")
        assert d["status"] == "OUT_OF_COVERAGE" and len(d["known_gap_ids"]) == 1
        if gap_id:
            assert d["known_gap_ids"] == [gap_id]
        return d["known_gap_ids"][0]

    def by_contract(rule, date, scope, contract):
        with pytest.raises(mr.ContractRequired):
            mr.rule_at(rule, date, scope, "XSGE")
        d = resolve(rule, date, scope, "XSGE")
        assert d["status"] == "MISSING_CONTEXT" and d["missing_context"] == ["contract"]
        return mr.rule_at(rule, date, scope, "XSGE", contract=contract)

    # NI2409 named contract at CNY 6 while the rest paid 3: one record per tier, the caller names the contract
    assert by_contract("trans_fee_per_lot", "2024-06-03", "shfe_ni", "ni2409") == 6
    assert by_contract("trans_fee_per_lot", "2024-06-03", "shfe_ni", "ni2410") == 3
    assert mr.rule_at("trans_fee_per_lot", "2024-05-10", "shfe_ni", "XSGE") == 3
    assert mr.rule_at("trans_fee_per_lot", "2024-07-02", "shfe_ni", "XSGE") == 3
    # gold: month-category tiers rolling towards expiry, over the whole window
    assert by_contract("trans_fee_per_lot", "2024-01-02", "shfe_au", "au2402") == 10
    assert by_contract("trans_fee_per_lot", "2024-01-02", "shfe_au", "au2403") == 2
    assert by_contract("trans_fee_per_lot", "2025-05-06", "shfe_au", "au2506") == 20
    assert by_contract("trans_fee_per_lot", "2025-05-06", "shfe_au", "au2507") == 10
    assert by_contract("trans_fee_per_lot", "2026-11-02", "shfe_au", "au2702") == 10
    assert by_contract("trans_fee_per_lot", "2026-11-02", "shfe_au", "au2701") == 20
    assert by_contract("trans_fee_rate", "2024-06-03", "shfe_ag", "ag2412") == 0.00005
    assert by_contract("trans_fee_rate", "2024-06-03", "shfe_ag", "ag2410") == 0.00001
    # close-today: only the named contract is priced; the others fall in a selector gap
    assert by_contract("close_today_fee_per_lot", "2025-05-06", "shfe_au", "au2506") == 20
    d = resolve("close_today_fee_per_lot", "2025-05-06", "shfe_au", "XSGE", {"contract": "au2508"})
    assert d["status"] == "OUT_OF_COVERAGE" and d["known_gap_ids"] == ["G-0368"]
    in_gap("close_today_fee_rate", "2025-01-02", "shfe_cu", "G-0352")
    gap = next(g for g in mr.known_gaps("cn") if g["gap_id"] == "G-0352")
    assert (gap["market"], gap["scope"], gap["interval"]) == ("XSGE", "shfe_cu", {"from": "2024-01-01", "to": None})

    # fuel oil margin: 2026-11-03 notice raised only the two excluded nearest expiries; general months stay 0.16
    rec = mr.record_at("margin_ratio", "2026-11-03", "shfe_fu", "XSGE")
    assert (rec.id, rec.value, rec.verification) == ("cn.futures.margin_ratio.shfe_fu.2026-11-03", 0.16, "single-source")
    rec = mr.record_at("margin_ratio", "2026-11-02", "shfe_fu", "XSGE")
    assert (rec.id, rec.effective_to) == ("cn.futures.margin_ratio.shfe_fu.2026-11-02", "2026-11-03")
    in_gap("margin_ratio", "2026-10-30", "shfe_fu")


@pytest.mark.parametrize("record,ok", [
    ({"rule": "trans_fee_per_lot", "value": 3, "unit": "CNY"}, True),
    ({"rule": "close_today_fee_per_lot", "value": 0, "unit": "CNY"}, True),
    ({"rule": "trans_fee_per_lot", "value": 3}, False),                                       # no unit
    ({"rule": "close_today_fee_per_lot", "value": 3}, False),
    ({"rule": "close_today_fee_per_lot", "value": 3, "unit": "USD"}, False),
    ({"rule": "trans_fee_per_lot", "value": -1, "unit": "CNY"}, False),
    ({"rule": "close_today_fee_per_lot", "value": -0.5, "unit": "CNY"}, False),
    ({"rule": "trans_fee_per_lot", "value": "3", "unit": "CNY"}, False),
    ({"rule": "trans_fee_per_lot", "value": True, "unit": "CNY"}, False),
    ({"rule": "trans_fee_rate", "value": 0.00005}, True),
    ({"rule": "close_today_fee_rate", "value": 0}, True),
    ({"rule": "trans_fee_rate", "value": 0.05}, False),                                       # per mille not converted
    ({"rule": "trans_fee_rate", "value": 0.01}, False),
    ({"rule": "close_today_fee_rate", "value": -0.0001}, False),
    ({"rule": "close_today_fee_rate", "value": float("nan")}, False),
])
def test_futures_fee_rules_validated_at_load(tmp_path, monkeypatch, record, ok):
    rec = {"id": "cn.futures.x.shfe_cu.2024-01-01", "scope": "shfe_cu", "effective_from": "2024-01-01",
           "verification": "single-source", "sources": [_SRC], **record}
    if ok:
        assert [r.value for r in _load_with(tmp_path, monkeypatch, rec, "cn", "XSGE")] == [record["value"]]
    else:
        with pytest.raises(ValueError):
            _load_with(tmp_path, monkeypatch, rec, "cn", "XSGE")


def test_ine_futures_rules():
    from marina_rules.contract import resolve

    band = "price_limit_pct_of_prev_settlement"
    day = [["09:00", "10:15"], ["10:30", "11:30"], ["13:30", "15:00"]]
    assert mr.rule_at("margin_ratio", "2024-06-14", "ine_sc", "XINE") == 0.1
    assert mr.rule_at(band, "2024-06-14", "ine_sc", "XINE") == 0.08
    assert mr.rule_at("margin_ratio", "2024-06-14", "ine_bc", "XINE") == 0.09
    assert mr.rule_at(band, "2024-06-14", "ine_nr", "XINE") == 0.06
    assert mr.rule_at(band, "2025-03-14", "ine_ec", "XINE") == 0.16
    assert mr.rule_at("session_schedule", "2024-06-14", "ine_sc", "XINE") == {
        "open_call": ["20:55", "21:00"],
        "night": ["21:00", "02:30"],
        "day_call": ["08:55", "09:00"],
        "continuous": day,
        "close_call": None,
    }
    assert mr.rule_at("session_schedule", "2024-06-14", "ine_bc", "XINE")["night"] == ["21:00", "01:00"]
    assert mr.rule_at("session_schedule", "2024-06-14", "ine_lu", "XINE")["night"] == ["21:00", "23:00"]
    assert mr.rule_at("session_schedule", "2024-06-14", "ine_nr", "XINE")["night"] == ["21:00", "23:00"]
    # EC has no night session; its session record starts on the listing day 2023-08-18
    assert mr.rule_at("session_schedule", "2023-08-18", "ine_ec", "XINE") == {
        "open_call": ["08:55", "09:00"],
        "night": None,
        "day_call": None,
        "continuous": day,
        "close_call": None,
    }
    with pytest.raises(KeyError):
        mr.rule_at("session_schedule", "2023-08-17", "ine_ec", "XINE")
    # coverage floor 2024-01-01, but the record in force then starts at its real change date
    rec = mr.record_at("margin_ratio", "2024-01-01", "ine_sc", "XINE")
    assert (rec.id, rec.value) == ("cn.futures.margin_ratio.ine_sc.2023-12-28", 0.11)
    rec = mr.record_at("margin_ratio", "2024-01-01", "ine_nr", "XINE")
    assert (rec.id, rec.value) == ("cn.futures.margin_ratio.ine_nr.2023-10-09", 0.08)
    assert resolve("margin_ratio", "2023-09-01", "ine_sc", "XINE")["status"] == "OUT_OF_COVERAGE"
    # 2026-10-12 named SC contracts at a different level: general months carry two values, declared gap, no guess
    with pytest.raises(KeyError):
        mr.rule_at("margin_ratio", "2026-10-20", "ine_sc", "XINE")
    gap = next(g for g in mr.known_gaps("cn") if g["scope"] == "ine_sc" and g["rule"] == "margin_ratio"
               and g["interval"]["from"] <= "2026-10-20" < (g["interval"]["to"] or "9999-12-31"))
    assert gap["market"] == "XINE" and gap["interval"] == {"from": "2026-10-12", "to": None}
    d = resolve("margin_ratio", "2026-10-20", "ine_sc", "XINE")
    assert d["status"] == "OUT_OF_COVERAGE" and d["known_gap_ids"] == [gap["gap_id"]]
    # EC 2024 spring: contracts at different levels, no product-level margin
    d = resolve("margin_ratio", "2024-03-15", "ine_ec", "XINE")
    assert d["status"] == "OUT_OF_COVERAGE" and len(d["known_gap_ids"]) == 1
    assert resolve("min_holding_days", "2024-06-14", "ine_lu", "XINE",
                   min_verification="verified")["status"] == "UNVERIFIED"
    with pytest.raises(KeyError):
        mr.rule_at(band, "2024-06-14", "ine_sc", "XSGE")


def test_czce_futures_rules():
    from marina_rules.contract import resolve

    band = "price_limit_pct_of_prev_settlement"
    day = [["09:00", "10:15"], ["10:30", "11:30"], ["13:30", "15:00"]]
    assert mr.rule_at("margin_ratio", "2024-06-14", "czce_cf", "XZCE") == 0.07
    assert mr.rule_at(band, "2024-06-14", "czce_sr", "XZCE") == 0.06
    assert mr.rule_at("margin_ratio", "2025-03-14", "czce_sf", "XZCE") == 0.09
    # 2024 National Day raise: margin from the 2024-09-27 settlement, band from the next trading day 2024-09-30
    assert mr.rule_at("margin_ratio", "2024-09-26", "czce_ma", "XZCE") == 0.08
    rec = mr.record_at("margin_ratio", "2024-09-27", "czce_ma", "XZCE")
    assert (rec.value, rec.verification) == (0.1, "verified")
    rec = mr.record_at(band, "2024-09-30", "czce_oi", "XZCE")
    assert (rec.id, rec.value, rec.verification) == (
        "cn.futures.price_limit_pct_of_prev_settlement.czce_oi.2024-09-30", 0.1, "verified")
    # PF: night session 21:00-23:00; 08:55-08:59 is cancel-only, so there is no day-session call
    assert mr.rule_at("session_schedule", "2024-06-14", "czce_pf", "XZCE") == {
        "open_call": ["20:55", "21:00"],
        "night": ["21:00", "23:00"],
        "day_call": None,
        "continuous": day,
        "close_call": None,
    }
    # other CZCE sessions are declared gaps, not guesses
    d = resolve("session_schedule", "2024-06-14", "czce_ap", "XZCE")
    assert d["status"] == "OUT_OF_COVERAGE" and len(d["known_gap_ids"]) == 1
    # coverage floor 2024-01-01, but the record in force then starts at its real change date
    rec = mr.record_at("margin_ratio", "2024-01-01", "czce_cy", "XZCE")
    assert rec.id == "cn.futures.margin_ratio.czce_cy.2023-10-09"
    assert resolve("margin_ratio", "2023-09-01", "czce_sf", "XZCE")["status"] == "OUT_OF_COVERAGE"
    # AP 2023-11-08 -> 2024-04-15: general months at 13% and 10% at once, declared gap, no guess
    with pytest.raises(KeyError):
        mr.rule_at("margin_ratio", "2024-03-01", "czce_ap", "XZCE")
    gap = next(g for g in mr.known_gaps("cn") if g["scope"] == "czce_ap" and g["rule"] == "margin_ratio"
               and g["interval"]["from"] <= "2024-03-01" < (g["interval"]["to"] or "9999-12-31"))
    assert gap["market"] == "XZCE" and gap["interval"] == {"from": "2023-11-08", "to": "2024-04-15"}
    d = resolve("margin_ratio", "2024-03-01", "czce_ap", "XZCE")
    assert d["status"] == "OUT_OF_COVERAGE" and d["known_gap_ids"] == [gap["gap_id"]]
    # PX margin: no quotable delivery-ladder source, whole window is a gap
    d = resolve("margin_ratio", "2025-06-16", "czce_px", "XZCE")
    assert d["status"] == "OUT_OF_COVERAGE" and len(d["known_gap_ids"]) == 1
    assert resolve("min_holding_days", "2024-06-14", "czce_sr", "XZCE",
                   min_verification="verified")["status"] == "UNVERIFIED"
    with pytest.raises(KeyError):
        mr.rule_at(band, "2024-06-14", "czce_sr", "XSGE")


def test_czce_thin_products_rules():
    from marina_rules.contract import resolve

    band = "price_limit_pct_of_prev_settlement"
    # PR: coverage from listing day 2024-08-30; 2024 National Day raise 7% -> 9% from the next trading day 2024-09-30
    assert mr.rule_at(band, "2024-09-27", "czce_pr", "XZCE") == 0.07
    rec = mr.record_at(band, "2024-09-30", "czce_pr", "XZCE")
    assert (rec.value, rec.verification) == (0.09, "verified")
    assert resolve(band, "2024-08-29", "czce_pr", "XZCE")["status"] == "OUT_OF_COVERAGE"
    assert mr.rule_at("session_schedule", "2024-09-30", "czce_pr", "XZCE")["night"] == ["21:00", "23:00"]
    # PR / PL margin: no quotable delivery-ladder source, whole window is a gap
    for scope, day in (("czce_pr", "2025-06-16"), ("czce_pl", "2025-09-01")):
        d = resolve("margin_ratio", day, scope, "XZCE")
        assert d["status"] == "OUT_OF_COVERAGE" and len(d["known_gap_ids"]) == 1
    # PL: first band record the trading day after the first daily file
    assert resolve(band, "2025-07-22", "czce_pl", "XZCE")["status"] == "OUT_OF_COVERAGE"
    assert mr.rule_at(band, "2025-07-23", "czce_pl", "XZCE") == 0.07
    assert mr.rule_at("margin_ratio", "2025-06-16", "czce_wh", "XZCE") == 0.15
    assert mr.rule_at(band, "2025-08-18", "czce_wh", "XZCE") == 0.07
    assert mr.rule_at("margin_ratio", "2025-06-16", "czce_rs", "XZCE") == 0.2
    assert mr.rule_at("margin_ratio", "2026-09-22", "czce_rs", "XZCE") == 0.08
    assert mr.rule_at("margin_ratio", "2025-06-16", "czce_zc", "XZCE") == 0.5
    for scope in ("czce_pm", "czce_ri", "czce_jr"):
        assert mr.rule_at("margin_ratio", "2025-06-16", scope, "XZCE") == 0.15
    # every listed PM / RI / JR / LR / ZC contract carries the doubled listing band all window: gap, no carried value
    for scope in ("czce_pm", "czce_ri", "czce_jr", "czce_lr", "czce_zc"):
        d = resolve(band, "2025-06-16", scope, "XZCE")
        assert d["status"] == "OUT_OF_COVERAGE" and len(d["known_gap_ids"]) == 1
        with pytest.raises(KeyError):
            mr.rule_at(band, "2025-06-16", scope, "XZCE")
    # LR: no general month left from 2025-12-15 (gap); no LR contract listed from 2026-01-19 (no record, no gap)
    assert mr.rule_at("margin_ratio", "2025-12-12", "czce_lr", "XZCE") == 0.15
    d = resolve("margin_ratio", "2026-01-05", "czce_lr", "XZCE")
    assert d["status"] == "OUT_OF_COVERAGE" and len(d["known_gap_ids"]) == 1
    d = resolve("margin_ratio", "2026-03-02", "czce_lr", "XZCE")
    assert d["status"] == "OUT_OF_COVERAGE" and d["known_gap_ids"] == []
    for scope in ("czce_wh", "czce_rs", "czce_pm", "czce_ri", "czce_jr", "czce_zc", "czce_pl"):
        d = resolve("session_schedule", "2025-09-01", scope, "XZCE")
        assert d["status"] == "OUT_OF_COVERAGE" and len(d["known_gap_ids"]) == 1
    assert resolve("min_holding_days", "2025-06-16", "czce_zc", "XZCE",
                   min_verification="verified")["status"] == "UNVERIFIED"


def test_gfex_futures_rules():
    from marina_rules.contract import resolve

    band = "price_limit_pct_of_prev_settlement"
    # 2024 Spring Festival notice: margin from the 2024-02-07 settlement, band from the next trading day 2024-02-08
    rec = mr.record_at("margin_ratio", "2024-02-07", "gfex_si", "GFEX")
    assert (rec.value, rec.verification) == (0.11, "verified")
    assert mr.rule_at(band, "2024-02-08", "gfex_lc", "GFEX") == 0.15
    assert mr.rule_at("margin_ratio", "2024-03-15", "gfex_lc", "GFEX") == 0.12
    assert mr.rule_at(band, "2024-03-15", "gfex_si", "GFEX") == 0.06
    # 2026 National Day: margin 2026-09-29 -> 2026-10-08, band one trading day later; last records open-ended
    assert mr.rule_at("margin_ratio", "2026-09-29", "gfex_pt", "GFEX") == 0.18
    assert mr.rule_at(band, "2026-09-29", "gfex_pt", "GFEX") == 0.14
    assert mr.rule_at(band, "2026-09-30", "gfex_pt", "GFEX") == 0.16
    rec = mr.record_at("margin_ratio", "2026-10-20", "gfex_ps", "GFEX")
    assert (rec.id, rec.value, rec.effective_to) == ("cn.futures.margin_ratio.gfex_ps.2026-10-08", 0.13, None)
    # PS: covered from listing day 2024-12-26; listing-day 14% band is not a record, the ordinary 7% is
    assert mr.rule_at("margin_ratio", "2024-12-26", "gfex_ps", "GFEX") == 0.09
    assert mr.rule_at(band, "2024-12-26", "gfex_ps", "GFEX") == 0.07
    d = resolve("margin_ratio", "2024-12-25", "gfex_ps", "GFEX")
    assert d["status"] == "OUT_OF_COVERAGE" and d["known_gap_ids"] == []
    # PT / PD listed 2025-11-27: T+0 from listing day; margin and band start inside a declared gap
    assert mr.rule_at("min_holding_days", "2025-11-27", "gfex_pd", "GFEX") == 0
    with pytest.raises(KeyError):
        mr.rule_at("min_holding_days", "2025-11-26", "gfex_pt", "GFEX")
    for scope in ("gfex_pt", "gfex_pd"):
        d = resolve("margin_ratio", "2025-11-27", scope, "GFEX")
        assert d["status"] == "OUT_OF_COVERAGE" and len(d["known_gap_ids"]) == 1
    # LC 2024-04-29 -> 2024-09-27: no dated notice chain, declared gap, no guess from settlement observations
    with pytest.raises(KeyError):
        mr.rule_at("margin_ratio", "2024-06-14", "gfex_lc", "GFEX")
    gap = next(g for g in mr.known_gaps("cn") if g["scope"] == "gfex_lc" and g["rule"] == "margin_ratio"
               and g["interval"]["from"] <= "2024-06-14" < (g["interval"]["to"] or "9999-12-31"))
    assert gap["market"] == "GFEX" and gap["interval"] == {"from": "2024-04-29", "to": "2024-09-27"}
    d = resolve("margin_ratio", "2024-06-14", "gfex_lc", "GFEX")
    assert d["status"] == "OUT_OF_COVERAGE" and d["known_gap_ids"] == [gap["gap_id"]]
    # sessions: declared gaps for all five products
    for scope, day in (("gfex_si", "2024-06-14"), ("gfex_lc", "2024-06-14"), ("gfex_ps", "2025-06-16"),
                       ("gfex_pt", "2026-06-15"), ("gfex_pd", "2026-06-15")):
        d = resolve("session_schedule", day, scope, "GFEX")
        assert d["status"] == "OUT_OF_COVERAGE" and len(d["known_gap_ids"]) == 1
    # bands rest on the notice alone; T+0 inferred from the settlement rules
    assert resolve(band, "2024-03-15", "gfex_si", "GFEX", min_verification="verified")["status"] == "UNVERIFIED"
    assert resolve("min_holding_days", "2024-06-14", "gfex_lc", "GFEX",
                   min_verification="verified")["status"] == "UNVERIFIED"
    with pytest.raises(KeyError):
        mr.rule_at("margin_ratio", "2024-03-15", "gfex_si", "XZCE")


# --- Hong Kong (XHKG, data/hk/) -----------------------------------------------------------------------------------
HK_FLOOR, HK_END = "2010-01-01", "2026-11-04"
# (scope, rule) -> first day Marina is expected to answer; before it there is no record and no gap
# (the AFRC levy was introduced on 2022-01-01, the closing auction on 2016-07-25, the VCM on 2016-08-22 for stocks
# and on 2022-05-03 for ETFs). opening_auction_limit_pct is a known gap from the floor to 2020-10-19 (G-HK-0005 / 0006).
# order_spread_limit starts 2005-07-04 (before the floor); order_price_multiple_limit is truncated at the floor.
HK_KEYS = {(s, r): HK_FLOOR for s in ("hk_stock", "hk_etf")
           for r in ("stamp_duty_buy", "stamp_duty_sell", "transaction_levy_each_side", "trading_fee_each_side",
                     "trading_tariff_per_trade", "settlement_fee_each_side", "price_limit_pct", "session_schedule",
                     "min_holding_days", "settlement_cycle_days", "tick_size_table",
                     "investor_compensation_levy_each_side", "opening_auction_limit_pct", "short_sale_price_test",
                     "order_spread_limit", "order_price_multiple_limit")}
HK_KEYS.update({("hk_stock", "afrc_levy_each_side"): "2022-01-01", ("hk_etf", "afrc_levy_each_side"): "2022-01-01",
                ("hk_stock", "closing_auction_limit_pct"): "2016-07-25", ("hk_etf", "closing_auction_limit_pct"): "2016-07-25",
                ("hk_stock", "vcm_trigger_pct"): "2016-08-22", ("hk_etf", "vcm_trigger_pct"): "2022-05-03",
                ("hk_etf_part_b", "tick_size_table"): HK_FLOOR})   # Part B ETFs: spread table only (scope hk_etf_part_b)
HK_VCM_TIERS = {"hsi_hscei_constituents", "hsci_largecap_constituents", "hsci_midcap_constituents",
                "hsci_smallcap_constituents", "vcm_eligible_etfs"}


def test_hk_loads_scopes_and_gaps():
    hk = [r for r in mr.records() if r.file.startswith("hk/")]
    assert len(hk) == 75 and {r.market for r in hk} == {"XHKG"} and all(r.id.startswith("hk.") for r in hk)
    assert sum(r.verification == "verified" for r in hk) == 6 and sum(r.verification == "single-source" for r in hk) == 69
    assert {(r.scope, r.rule) for r in hk} == set(HK_KEYS) - {("hk_etf", "session_schedule")}
    reg = mr.scopes("hk")
    assert set(reg) == {"hk_stock", "hk_etf", "hk_etf_part_b"} and not set(reg) & set(mr.scopes("cn"))
    assert reg["hk_stock"]["excludes"] == ("hk_etf",) and reg["hk_etf"]["requires"] == ()
    # an ETF's spread table is per-security context: required only for tick_size_table under hk_etf; Part B is its
    # own scope, which does not exclude hk_etf (the same ETF's fees are still asked under hk_etf)
    assert reg["hk_etf"]["rule_asserts"]["tick_size_table"]["requires"] == ["spread_table"]
    assert set(reg["hk_etf"]["rule_asserts"]) == {"tick_size_table"}
    assert reg["hk_etf_part_b"]["requires"] == ("spread_table",) and reg["hk_etf_part_b"]["excludes"] == ("hk_stock",)
    assert reg["hk_etf_part_b"]["asserts"] == {"spread_table": "part_b"}
    assert {r.rule for r in hk if r.scope == "hk_etf_part_b"} == {"tick_size_table"}
    assert {r.scope for r in hk} <= set(reg)
    for r in hk:   # value shapes of the Hong Kong rules (docs/SCHEMA.md)
        if r.rule == "settlement_fee_each_side":
            assert set(r.value) == {"rate", "min", "max"} and 0 < r.value["rate"] < 0.01 and r.unit == "HKD", r.id
        elif r.rule == "trading_tariff_per_trade":
            assert r.value >= 0 and r.unit == "HKD", r.id
        elif r.rule.endswith("_each_side") or r.rule.startswith("stamp_duty"):
            assert 0 <= r.value < 0.01 and r.unit is None, r.id
        elif r.rule in ("settlement_cycle_days", "min_holding_days"):
            assert isinstance(r.value, int) and r.value >= 0, r.id
        elif r.rule == "tick_size_table":   # bands meet end to end (also enforced at load); Part A / D from HKD 0.01
            first_last = {"hk.tick_size_table.hk_etf.2020-06-01": (0.01, 9999.0),            # Part D
                          "hk.tick_size_table.hk_etf_part_b.2010-01-01": (0.5, 9999.95)}       # Part B
            assert r.unit == "HKD" and (r.value[0]["ge"], r.value[-1]["le"]) == first_last.get(r.id, (0.01, 9995.0)), r.id
            assert all(set(b) == {"gt", "le", "tick"} for b in r.value[1:]), r.id
            assert all(a["le"] == b["gt"] for a, b in zip(r.value, r.value[1:])), r.id
        elif r.rule == "closing_auction_limit_pct":
            assert r.value == 0.05 and r.unit is None, r.id
        elif r.rule == "opening_auction_limit_pct":
            assert r.value == 0.15 and r.unit is None, r.id
        elif r.rule == "short_sale_price_test":   # Hong Kong shape: {restriction, duration}, no 'none' (docs/SCHEMA.md)
            exp = "exempt" if r.scope == "hk_etf" else "not_below_best_ask"
            assert r.value == {"restriction": exp, "duration": "always"} and r.unit is None, r.id
        elif r.rule == "order_spread_limit":   # {max_spreads, wider_pct, reference}, key order as in the data
            assert list(r.value) == ["max_spreads", "wider_pct", "reference"] and r.unit is None, r.id
            assert r.value["max_spreads"] == 24 and r.value["reference"] == "same_side_best_or_rule_fallback", r.id
            assert r.value["wider_pct"] in (None, 0.05, 0.035), r.id
        elif r.rule == "order_price_multiple_limit":
            assert set(r.value) == {"max_multiple", "reference"} and r.value["max_multiple"] in (9, 5), r.id
            assert r.value["reference"] == "nominal_or_previous_close_for_opening" and r.unit is None, r.id
        elif r.rule == "vcm_trigger_pct":
            assert isinstance(r.value, dict) and r.value and set(r.value) <= HK_VCM_TIERS and r.unit is None, r.id
            assert all(0 < x < 1 for x in r.value.values()), r.id
    gaps = mr.known_gaps("hk")
    assert [g["gap_id"] for g in gaps] == [f"G-HK-{n:04d}" for n in range(1, 7)]
    assert not {g["gap_id"] for g in gaps} & {g["gap_id"] for g in mr.known_gaps("cn")}
    for g in gaps:
        assert g["market"] == "XHKG" and g["status"] == "open" and g["severity"] in ("low", "medium", "high")
        assert g["reason"].strip() and g["evidence"]
        g0, g1 = g["interval"]["from"], g["interval"]["to"] or "9999-12-31"
        for r in hk:
            if (r.scope, r.rule) == (g["scope"], g["rule"]):
                assert not (r.effective_from < g1 and g0 < (r.effective_to or "9999-12-31")), (g["gap_id"], r.id)
    assert mr.market_prefix_for("XHKG") == "hk"
    assert mr.market_prefix_for(None) == mr.market_prefix_for("XSHG+XSHE") == mr.market_prefix_for("GFEX") == "cn"


@pytest.mark.parametrize("scope,rule", sorted(HK_KEYS))
def test_hk_records_and_gaps_cover_the_window(scope, rule):
    """Every (scope, rule) is answered or declared a known gap on every day of [start, 2026-11-04)."""
    start = HK_KEYS[(scope, rule)]
    c = mr.coverage("XHKG", scope, [rule], start, HK_END)
    assert c["scope_known"] and not c["conflicts"]
    if c["status"] == "unsupported":   # no record at all: declared gaps must tile the whole window, open-ended
        kg = sorted(mr.gaps_for("XHKG", scope, rule, start, HK_END), key=lambda g: g["interval"]["from"])
        assert kg and kg[0]["interval"]["from"] <= start and kg[-1]["interval"]["to"] is None
        assert all(a["interval"]["to"] == b["interval"]["from"] for a, b in zip(kg, kg[1:]))
        assert c["known_gap_ids"] == sorted(g["gap_id"] for g in kg)
        return
    for g in c["gaps"]:
        assert len(g["known_gap_ids"]) == 1, g
        gap = next(x for x in mr.known_gaps("hk") if x["gap_id"] == g["known_gap_ids"][0])
        assert gap["interval"]["from"] <= g["from"] and (gap["interval"]["to"] is None or g["to"] <= gap["interval"]["to"])
    assert c["status"] == ("partial" if c["gaps"] else "complete")
    if start > HK_FLOOR:   # nothing before commencement: no record, no gap
        eve = (dt.date.fromisoformat(start) - dt.timedelta(days=1)).isoformat()
        d = __import__("marina_rules.contract", fromlist=["resolve"]).resolve(rule, eve, scope, "XHKG")
        assert d["status"] == "OUT_OF_COVERAGE" and d["known_gap_ids"] == []


def test_hk_equity_rules():
    from marina_rules.contract import resolve

    # stamp duty: 0.1% -> 0.13% on 2021-08-01 -> 0.1% on 2023-11-17, both sides
    for rule in ("stamp_duty_buy", "stamp_duty_sell"):
        assert mr.rule_at(rule, "2021-07-31", "hk_stock", "XHKG") == 0.001
        rec = mr.record_at(rule, "2021-08-01", "hk_stock", "XHKG")
        assert (rec.value, rec.verification, rec.published_at) == (0.0013, "verified", "2021-06-03")
        assert mr.rule_at(rule, "2023-11-16", "hk_stock", "XHKG") == 0.0013
        rec = mr.record_at(rule, "2023-11-17", "hk_stock", "XHKG")
        assert (rec.value, rec.verification, rec.effective_to) == (0.001, "verified", None)
        # ETFs: waived for all ETFs from 2015-02-13; before it the rate depended on the fund (declared gap)
        assert mr.rule_at(rule, "2015-02-13", "hk_etf", "XHKG") == 0
        assert resolve(rule, "2024-06-14", "hk_etf", "XHKG", min_verification="verified")["status"] == "DETERMINED"
        with pytest.raises(KeyError):
            mr.rule_at(rule, "2015-02-12", "hk_etf", "XHKG")
        d = resolve(rule, "2015-02-12", "hk_etf", "XHKG")
        assert d["status"] == "OUT_OF_COVERAGE" and d["known_gap_ids"] == [{"stamp_duty_buy": "G-HK-0002",
                                                                             "stamp_duty_sell": "G-HK-0003"}[rule]]
    # no daily price limit: unlimited, limit_price answers None (as for A-share unlimited scopes)
    for scope in ("hk_stock", "hk_etf"):
        rec = mr.record_at("price_limit_pct", "2024-06-14", scope, "XHKG")
        assert (rec.value, rec.verification, rec.published_at) == ("unlimited", "single-source", None)
        assert mr.limit_price(10.0, scope, "2024-06-14", "XHKG") is None
        assert mr.limit_price(10.0, scope, "2010-01-04") is None
        with pytest.raises(KeyError):
            mr.rule_at("price_limit_pct", "2009-12-31", scope, "XHKG")
        assert resolve("price_limit_pct", "2024-06-14", scope, "XHKG", min_verification="verified")["status"] == "UNVERIFIED"
    with pytest.raises(mr.PublicationUnknown):
        mr.limit_price(10.0, "hk_stock", "2024-06-14", "XHKG", as_of="2024-06-14")
    # settlement fee: 0.002% (HKD 2..100) -> 0.0042%, no floor / cap, from 2025-06-30
    rec = mr.record_at("settlement_fee_each_side", "2025-06-29", "hk_stock", "XHKG")
    assert (rec.value, rec.unit) == ({"rate": 0.00002, "min": 2, "max": 100}, "HKD")
    rec = mr.record_at("settlement_fee_each_side", "2025-06-30", "hk_etf", "XHKG")
    assert (rec.value, rec.unit, rec.published_at) == ({"rate": 0.000042, "min": None, "max": None}, "HKD", "2025-05-29")
    # levies and exchange fees
    assert mr.rule_at("transaction_levy_each_side", "2010-09-30", "hk_stock", "XHKG") == 0.00004
    assert mr.rule_at("transaction_levy_each_side", "2014-11-01", "hk_etf", "XHKG") == 0.000027
    assert mr.rule_at("afrc_levy_each_side", "2022-01-01", "hk_stock", "XHKG") == 0.0000015
    with pytest.raises(KeyError):
        mr.rule_at("afrc_levy_each_side", "2021-12-31", "hk_stock", "XHKG")
    assert mr.rule_at("trading_fee_each_side", "2022-12-31", "hk_stock", "XHKG") == 0.00005
    assert mr.rule_at("trading_fee_each_side", "2023-01-01", "hk_stock", "XHKG") == 0.0000565
    assert mr.record_at("trading_tariff_per_trade", "2022-12-31", "hk_etf", "XHKG").value == 0.5
    assert mr.record_at("trading_tariff_per_trade", "2023-01-01", "hk_etf", "XHKG").value == 0
    # sessions (hk_stock): CAS phase-in is a declared gap; hk_etf has no session record at all
    v = mr.rule_at("session_schedule", "2020-10-19", "hk_stock", "XHKG")
    assert v == {"open_call": ["09:00", "09:22"], "continuous": [["09:30", "12:00"], ["13:00", "16:00"]],
                 "close_call": ["16:01", "16:10"]}
    assert mr.rule_at("session_schedule", "2012-03-05", "hk_stock", "XHKG")["close_call"] is None
    assert resolve("session_schedule", "2018-06-14", "hk_stock", "XHKG")["known_gap_ids"] == ["G-HK-0001"]
    assert resolve("session_schedule", "2024-06-14", "hk_etf", "XHKG")["known_gap_ids"] == ["G-HK-0004"]
    # settlement cycle and same-day resale
    assert mr.rule_at("settlement_cycle_days", "2024-06-14", "hk_etf", "XHKG") == 2
    assert mr.rule_at("min_holding_days", "2024-06-14", "hk_stock", "XHKG") == 0
    # the hk registry is found from the market; an A-share market never sees hk records
    assert mr.coverage("XHKG", "hk_stock", ["price_limit_pct"], HK_FLOOR, HK_END)["status"] == "complete"
    with pytest.raises(KeyError):
        mr.rule_at("stamp_duty_sell", "2024-06-14", "hk_stock", "XSHG")
    assert mr.rule_at("stamp_duty_sell", "2024-06-14") == 0.0005   # default scope stock: A-share only


def _hk_tick(price: float, date: str, scope: str = "hk_stock") -> float:
    """Increment for ``price`` from the tick_size_table in force: the band with gt < p <= le (first band ge <= p)."""
    for b in mr.rule_at("tick_size_table", date, scope, "XHKG"):
        if ("ge" in b and b["ge"] <= price <= b["le"]) or ("gt" in b and b["gt"] < price <= b["le"]):
            return b["tick"]
    raise ValueError(f"{price} outside the table")


def test_hk_second_batch_spread_table_cas_vcm():
    from marina_rules.contract import resolve

    # spread table (Part A): 2025-08-04 phase 1 (10-20 -> 0.01, 20-50 -> 0.02), 2026-08-03 phase 2 (0.50-10 -> 0.005)
    assert _hk_tick(15.00, "2025-08-01") == 0.02 and _hk_tick(15.00, "2025-08-04") == 0.01
    assert _hk_tick(30.00, "2025-08-01") == 0.05 and _hk_tick(30.00, "2025-08-04") == 0.02
    assert _hk_tick(5.00, "2026-07-31") == 0.01 and _hk_tick(5.00, "2026-08-03") == 0.005
    assert _hk_tick(0.30, "2026-08-03") == 0.005 and _hk_tick(0.30, "2010-01-04") == 0.005
    assert _hk_tick(0.01, "2010-01-04") == 0.001 and _hk_tick(0.25, "2010-01-04") == 0.001   # first band includes 0.01
    assert _hk_tick(10.00, "2010-01-04") == 0.01 and _hk_tick(10.01, "2010-01-04") == 0.02   # upper bound inclusive
    assert _hk_tick(9995.0, "2026-08-03") == 5.0
    with pytest.raises(ValueError):
        _hk_tick(10000.0, "2026-08-03")
    rec = mr.record_at("tick_size_table", "2026-08-03", "hk_stock", "XHKG")
    assert (rec.unit, rec.effective_to, rec.published_at, rec.verification) == ("HKD", None, "2026-07-14", "single-source")
    assert mr.record_at("tick_size_table", "2024-06-14", "hk_stock", "XHKG").published_at is None
    # tick_size_table is not tick_size: no tick family, tick_size() knows nothing about Hong Kong
    with pytest.raises(KeyError):
        mr.tick_size("hk_stock", "2024-06-14", "XHKG")
    assert mr.lookup_scope("tick_size_table", "hk_etf", "XHKG") == "hk_etf"
    c = mr.coverage("XHKG", "hk_etf", ["tick_size_table"], HK_FLOOR, HK_END)
    assert c["status"] == "complete" and c["known_gap_ids"] == []
    assert mr.coverage("XHKG", "hk_etf_part_b", ["tick_size_table"], HK_FLOOR, HK_END)["status"] == "complete"


def test_hk_etf_spread_tables():
    from marina_rules.contract import resolve

    # hk_etf (Part A to 2020-06-01, Part D from it); ETPs are outside the 2025 / 2026 share reductions
    assert _hk_tick(1.00, "2015-06-15", "hk_etf") == 0.01 and _hk_tick(1.00, "2020-05-29", "hk_etf") == 0.01
    assert _hk_tick(15.00, "2015-06-15", "hk_etf") == 0.02 and _hk_tick(30.00, "2015-06-15", "hk_etf") == 0.05
    assert _hk_tick(1.00, "2021-06-14", "hk_etf") == 0.001 and _hk_tick(1.01, "2021-06-14", "hk_etf") == 0.002
    assert _hk_tick(5.00, "2021-06-14", "hk_etf") == 0.002 and _hk_tick(5.00, "2020-06-01", "hk_etf") == 0.002
    assert _hk_tick(5.00, "2026-08-03", "hk_etf") == 0.002 and _hk_tick(15.00, "2025-08-04", "hk_etf") == 0.01
    assert _hk_tick(9999.0, "2026-08-03", "hk_etf") == 1.0
    with pytest.raises(ValueError):
        _hk_tick(9999.5, "2026-08-03", "hk_etf")
    rec = mr.record_at("tick_size_table", "2020-06-01", "hk_etf", "XHKG")
    assert (rec.effective_to, rec.published_at, rec.verification) == (None, "2020-05-18", "single-source")
    rec = mr.record_at("tick_size_table", "2020-05-29", "hk_etf", "XHKG")
    assert (rec.effective_to, rec.published_at, rec.value) == \
        ("2020-06-01", None, mr.rule_at("tick_size_table", "2015-06-15", "hk_stock", "XHKG"))   # the shares' Part A
    # hk_etf_part_b: one band, HKD 0.05 from 0.50 to 9,999.95, any date
    for d in ("2010-01-04", "2015-06-15", "2020-06-01", "2026-11-03"):
        assert _hk_tick(0.50, d, "hk_etf_part_b") == 0.05 and _hk_tick(9999.95, d, "hk_etf_part_b") == 0.05
    with pytest.raises(ValueError):
        _hk_tick(0.49, "2015-06-15", "hk_etf_part_b")
    # resolve: hk_etf needs spread_table for this rule only, and it must match the date
    d = resolve("tick_size_table", "2021-06-14", "hk_etf", "XHKG")
    assert d["status"] == "MISSING_CONTEXT" and d["missing_context"] == ["spread_table"] and not d["context_conflicts"]
    d = resolve("tick_size_table", "2021-06-14", "hk_etf", "XHKG", {"spread_table": "part_a"})
    assert d["status"] == "MISSING_CONTEXT" and d["missing_context"] == []
    assert [(c["key"], c["supplied"]) for c in d["context_conflicts"]] == [("spread_table", "part_a")]
    d = resolve("tick_size_table", "2021-06-14", "hk_etf", "XHKG", {"spread_table": "part_d"})
    assert d["status"] == "DETERMINED" and d["record_id"] == "hk.tick_size_table.hk_etf.2020-06-01"
    assert d["required_context"] == ["spread_table"]
    assert resolve("tick_size_table", "2015-06-15", "hk_etf", "XHKG", {"spread_table": "part_a"})["status"] == "DETERMINED"
    for st, date in (("part_d", "2020-05-29"), ("part_a", "2020-06-01"), ("part_b", "2015-06-15"), ("part_b", "2021-06-14")):
        assert resolve("tick_size_table", date, "hk_etf", "XHKG", {"spread_table": st})["context_conflicts"], (st, date)
    # hk_etf_part_b requires part_b
    assert resolve("tick_size_table", "2015-06-15", "hk_etf_part_b", "XHKG")["missing_context"] == ["spread_table"]
    d = resolve("tick_size_table", "2021-06-14", "hk_etf_part_b", "XHKG", {"spread_table": "part_b"})
    assert d["status"] == "DETERMINED" and d["record_id"] == "hk.tick_size_table.hk_etf_part_b.2010-01-01"
    d = resolve("tick_size_table", "2021-06-14", "hk_etf_part_b", "XHKG", {"spread_table": "part_d"})
    assert d["status"] == "MISSING_CONTEXT" and d["context_conflicts"]
    # every other hk_etf rule is unaffected: no spread_table asked for, and a supplied one is not checked
    for rule in ("trading_fee_each_side", "transaction_levy_each_side", "stamp_duty_buy", "vcm_trigger_pct",
                 "closing_auction_limit_pct", "settlement_cycle_days"):
        d = resolve(rule, "2024-06-14", "hk_etf", "XHKG")
        assert d["status"] == "DETERMINED" and d["required_context"] == [], (rule, d)
        assert resolve(rule, "2024-06-14", "hk_etf", "XHKG", {"spread_table": "part_b"})["status"] == "DETERMINED"
    assert "spread_table" in __import__("marina_rules.contract", fromlist=["capabilities"]).capabilities("hk")["context_vocabulary"]
    # closing auction: +/-5% of the CAS reference price from 2016-07-25, both scopes; nothing before (no gap)
    for scope in ("hk_stock", "hk_etf"):
        assert mr.rule_at("closing_auction_limit_pct", "2016-07-25", scope, "XHKG") == 0.05
        assert mr.rule_at("closing_auction_limit_pct", "2026-11-03", scope, "XHKG") == 0.05
        with pytest.raises(KeyError):
            mr.rule_at("closing_auction_limit_pct", "2016-07-22", scope, "XHKG")
        r = resolve("closing_auction_limit_pct", "2016-07-22", scope, "XHKG")
        assert r["status"] == "OUT_OF_COVERAGE" and r["known_gap_ids"] == []
        # an intraday band, not a daily price limit: limit_price still answers from price_limit_pct (unlimited)
        assert mr.limit_price(10.0, scope, "2024-06-14", "XHKG") is None
    # VCM: HSI / HSCEI +/-10% from 2016-08-22; HSCI Large / Mid / Small 10 / 15 / 20% from 2020-05-11
    assert mr.rule_at("vcm_trigger_pct", "2016-08-22", "hk_stock", "XHKG") == {"hsi_hscei_constituents": 0.1}
    tiers = {"hsci_largecap_constituents": 0.1, "hsci_midcap_constituents": 0.15, "hsci_smallcap_constituents": 0.2}
    assert mr.rule_at("vcm_trigger_pct", "2020-05-08", "hk_stock", "XHKG") == {"hsi_hscei_constituents": 0.1}
    assert mr.rule_at("vcm_trigger_pct", "2020-05-11", "hk_stock", "XHKG")["hsci_midcap_constituents"] == 0.15
    assert mr.rule_at("vcm_trigger_pct", "2020-05-11", "hk_stock", "XHKG") == tiers
    rec = mr.record_at("vcm_trigger_pct", "2021-03-29", "hk_stock", "XHKG")   # multiple triggers: same fractions
    assert (rec.value, rec.effective_to, rec.published_at) == (tiers, None, "2021-03-05")
    with pytest.raises(KeyError):
        mr.rule_at("vcm_trigger_pct", "2016-08-19", "hk_stock", "XHKG")
    # ETFs: only from 2022-05-03, eligible ETFs +/-5%; no record and no gap before
    assert mr.rule_at("vcm_trigger_pct", "2022-05-03", "hk_etf", "XHKG") == {"vcm_eligible_etfs": 0.05}
    r = resolve("vcm_trigger_pct", "2022-05-02", "hk_etf", "XHKG")
    assert r["status"] == "OUT_OF_COVERAGE" and r["known_gap_ids"] == []
    assert resolve("vcm_trigger_pct", "2024-06-14", "hk_etf", "XHKG", min_verification="verified")["status"] == "UNVERIFIED"
    c = mr.coverage("XHKG", "hk_stock", ["tick_size_table", "closing_auction_limit_pct", "vcm_trigger_pct"],
                    "2022-05-03", HK_END)
    assert c["status"] == "complete" and c["verification"] == "single-source"


@pytest.mark.parametrize("bands", [
    [],
    [{"gt": 0.0, "le": 1.0, "tick": 0.01}, {"gt": 1.5, "le": 2.0, "tick": 0.02}],                   # hole
    [{"gt": 0.0, "le": 1.0, "tick": 0.01}, {"gt": 0.5, "le": 2.0, "tick": 0.02}],                   # overlap
    [{"ge": 0.01, "le": 1.0, "tick": 0.01}, {"ge": 1.0, "le": 2.0, "tick": 0.02}],                  # ge after the first band
    [{"gt": 0.0, "ge": 0.0, "le": 1.0, "tick": 0.01}],                                               # both lower keys
    [{"over": 0.0, "up_to": 1.0, "tick": 0.01}],                                                     # old key names
    [{"gt": 1.0, "le": 1.0, "tick": 0.01}],                                                          # empty band
    [{"gt": 0.0, "le": 1.0, "tick": 0}],                                                             # zero tick
])
def test_band_table_validation_rejects(bands):
    with pytest.raises(ValueError):
        mr._check_band_table(bands, "test")


def test_band_table_validation_accepts_the_hk_shape():
    mr._check_band_table([{"ge": 0.01, "le": 0.25, "tick": 0.001}, {"gt": 0.25, "le": 0.5, "tick": 0.005}], "test")


def test_hk_third_batch_short_sale_levy_pre_opening():
    from marina_rules.contract import resolve

    stock = {"restriction": "not_below_best_ask", "duration": "always"}
    etf = {"restriction": "exempt", "duration": "always"}
    # short selling (tick rule): shares never below the best current ask in continuous trading; ETFs exempt
    assert mr.rule_at("short_sale_price_test", "2015-06-01", "hk_stock", "XHKG")["restriction"] == "not_below_best_ask"
    assert mr.rule_at("short_sale_price_test", "2015-06-01", "hk_etf", "XHKG")["restriction"] == "exempt"
    # the ETF exemption is dated 2002-03-25 (before the coverage floor); the share record is truncated at the floor
    rec = mr.record_at("short_sale_price_test", "2009-12-31", "hk_etf", "XHKG")
    assert rec.value == etf and rec.id == "hk.short_sale_price_test.hk_etf.2002-03-25" and rec.published_at is None
    d = resolve("short_sale_price_test", "2009-12-31", "hk_stock", "XHKG")
    assert d["status"] == "OUT_OF_COVERAGE" and d["known_gap_ids"] == []
    # same-value segments on the dates the auction / exemption arrangements changed (notes differ, value does not)
    for day, rid in (("2010-01-04", "2010-01-01"), ("2017-07-21", "2010-01-01"), ("2017-07-24", "2017-07-24"),
                     ("2020-10-19", "2020-10-19"), ("2023-06-16", "2020-10-19"), ("2023-06-19", "2023-06-19"),
                     ("2026-11-03", "2023-06-19")):
        rec = mr.record_at("short_sale_price_test", day, "hk_stock", "XHKG")
        assert (rec.value, rec.id) == (stock, f"hk.short_sale_price_test.hk_stock.{rid}"), day
    for day, rid in (("2017-07-24", "2017-07-24"), ("2020-10-19", "2020-10-19"), ("2024-10-31", "2020-10-19"),
                     ("2024-11-01", "2024-11-01"), ("2026-11-03", "2024-11-01")):
        rec = mr.record_at("short_sale_price_test", day, "hk_etf", "XHKG")
        assert (rec.value, rec.id) == (etf, f"hk.short_sale_price_test.hk_etf.{rid}"), day
    d = resolve("short_sale_price_test", "2015-06-01", "hk_stock", "XHKG")
    assert d["status"] == "DETERMINED" and d["result"]["value"] == stock and d["verification"] == "single-source"
    assert resolve("short_sale_price_test", "2015-06-01", "hk_etf", "XHKG", min_verification="verified")["status"] == \
        "UNVERIFIED"
    # the US records keep their own shape (four keys or 'none'), unaffected by the Hong Kong one
    assert mr.rule_at("short_sale_price_test", "2020-01-02", "us_stock", "XNYS")["reference"] == "prior_close"
    assert mr.rule_at("short_sale_price_test", "2010-06-01", "us_etf", "XNAS") == "none"
    # Investor Compensation Fund levy: suspended (0) from 2005-12-19; same-value split on 2020-01-01 (new trigger levels)
    for scope in ("hk_stock", "hk_etf"):
        assert mr.rule_at("investor_compensation_levy_each_side", "2005-12-19", scope, "XHKG") == 0
        rec = mr.record_at("investor_compensation_levy_each_side", "2019-12-31", scope, "XHKG")
        assert (rec.effective_to, rec.published_at, rec.unit) == ("2020-01-01", "2005-11-11", None)
        rec = mr.record_at("investor_compensation_levy_each_side", "2020-01-01", scope, "XHKG")
        assert (rec.value, rec.effective_to, rec.published_at) == (0, None, "2019-10-11")
        d = resolve("investor_compensation_levy_each_side", "2005-12-16", scope, "XHKG")
        assert d["status"] == "OUT_OF_COVERAGE" and d["known_gap_ids"] == []
    assert mr.rule_at("investor_compensation_levy_each_side", "2012-01-03", "hk_stock", "XHKG") == 0
    assert mr.rule_at("investor_compensation_levy_each_side", "2021-01-04", "hk_etf", "XHKG") == 0
    # pre-opening session: +/-15% outer band from 2020-10-19; before it the old POS had no fixed range (known gaps)
    assert mr.rule_at("opening_auction_limit_pct", "2020-10-19", "hk_stock", "XHKG") == 0.15
    assert mr.rule_at("opening_auction_limit_pct", "2026-11-03", "hk_etf", "XHKG") == 0.15
    assert mr.record_at("opening_auction_limit_pct", "2026-10-30", "hk_etf", "XHKG").id == \
        "hk.opening_auction_limit_pct.hk_etf.2020-10-19"
    rec = mr.record_at("opening_auction_limit_pct", "2026-11-02", "hk_stock", "XHKG")   # 9-times -> 5-times, same 15%
    assert (rec.value, rec.effective_to, rec.published_at) == (0.15, None, None)
    for scope, gid in (("hk_stock", "G-HK-0005"), ("hk_etf", "G-HK-0006")):
        for day in ("2010-01-04", "2020-10-16"):
            with pytest.raises(KeyError):
                mr.rule_at("opening_auction_limit_pct", day, scope, "XHKG")
            d = resolve("opening_auction_limit_pct", day, scope, "XHKG")
            assert d["status"] == "OUT_OF_COVERAGE" and d["known_gap_ids"] == [gid], (scope, day, d)
        c = mr.coverage("XHKG", scope, ["opening_auction_limit_pct"], HK_FLOOR, HK_END)
        assert c["status"] == "partial" and c["known_gap_ids"] == [gid]
        assert mr.coverage("XHKG", scope, ["opening_auction_limit_pct"], "2020-10-19", HK_END)["status"] == "complete"
        # intraday auction bands, not a daily price limit
        assert mr.limit_price(10.0, scope, "2024-06-14", "XHKG") is None
    c = mr.coverage("XHKG", "hk_stock", ["short_sale_price_test", "investor_compensation_levy_each_side",
                                         "opening_auction_limit_pct", "closing_auction_limit_pct"], "2020-10-19", HK_END)
    assert c["status"] == "complete" and c["verification"] == "single-source"


_HK_SSPT_OK = {"restriction": "not_below_best_ask", "duration": "always"}
_SSPT_US_SHAPE = {"trigger_decline_pct": 0.1, "reference": "prior_close", "restriction": "above_national_best_bid",
                  "duration": "rest_of_day_and_next_day"}   # the US Rule 201 value (also _SSPT_OK, US section)


@pytest.mark.parametrize("value,market", [
    (_SSPT_US_SHAPE, "XHKG"),                                                               # US shape in Hong Kong
    ("none", "XHKG"), (None, "XHKG"), ("not_below_best_ask", "XHKG"), ([_HK_SSPT_OK], "XHKG"),
    ({"restriction": "not_below_best_ask"}, "XHKG"),                                        # missing key
    ({**_HK_SSPT_OK, "reference": "prior_close"}, "XHKG"),                                  # extra key
    ({**_HK_SSPT_OK, "restriction": "not_below_last_sale"}, "XHKG"),                        # unknown enums
    ({**_HK_SSPT_OK, "restriction": "above_national_best_bid"}, "XHKG"),
    ({**_HK_SSPT_OK, "duration": "rest_of_day_and_next_day"}, "XHKG"),
    ({**_HK_SSPT_OK, "duration": None}, "XHKG"),
    (_HK_SSPT_OK, "XNYS"), (_HK_SSPT_OK, "XNYS+XNAS"),                                      # Hong Kong shape in the US
    (_HK_SSPT_OK, "XSHG"), ("none", "XSHG"),                                                # no such rule elsewhere
])
def test_hk_short_sale_price_test_validation_rejects(value, market):
    with pytest.raises(ValueError):
        mr._check_short_sale_price_test(value, "test", market)


def test_hk_short_sale_price_test_validation_accepts():
    for v in (_HK_SSPT_OK, {"restriction": "exempt", "duration": "always"}):
        mr._check_short_sale_price_test(v, "test", "XHKG")
    for market in ("XNYS", "XNAS", "XNYS+XNAS"):   # the US shapes are still validated as before
        mr._check_short_sale_price_test("none", "test", market)
        mr._check_short_sale_price_test(_SSPT_US_SHAPE, "test", market)
        with pytest.raises(ValueError):
            mr._check_short_sale_price_test({**_SSPT_US_SHAPE, "trigger_decline_pct": 1.0}, "test", market)


@pytest.mark.parametrize("rule,value", [
    ("investor_compensation_levy_each_side", 1), ("investor_compensation_levy_each_side", 1.5),
    ("investor_compensation_levy_each_side", -0.00002), ("investor_compensation_levy_each_side", "0.00002"),
    ("investor_compensation_levy_each_side", True), ("investor_compensation_levy_each_side", None),
    ("investor_compensation_levy_each_side", float("nan")),
    ("opening_auction_limit_pct", 0), ("opening_auction_limit_pct", 0.0), ("opening_auction_limit_pct", 1),
    ("opening_auction_limit_pct", 1.15), ("opening_auction_limit_pct", -0.15), ("opening_auction_limit_pct", "0.15"),
    ("opening_auction_limit_pct", float("inf")), ("opening_auction_limit_pct", "unlimited"),
    ("closing_auction_limit_pct", 0), ("closing_auction_limit_pct", 5),
])
def test_hk_fraction_validation_rejects(rule, value):
    with pytest.raises(ValueError):
        mr._check_fraction(rule, value, "test")


def test_hk_fraction_validation_accepts():
    for rule, value in (("investor_compensation_levy_each_side", 0), ("investor_compensation_levy_each_side", 0.00002),
                        ("opening_auction_limit_pct", 0.15), ("closing_auction_limit_pct", 0.05)):
        mr._check_fraction(rule, value, "test")
    for r in mr.records():
        if r.rule in mr._FRACTION_RULES:
            mr._check_fraction(r.rule, r.value, r.id)


def test_hk_fourth_batch_order_spread_and_multiple_limits():
    from marina_rules.contract import resolve

    ref = "same_side_best_or_rule_fallback"
    # CTS quotation rule: 24 spreads from 2005-07-04 (eight -> twenty-four), before the coverage floor
    assert mr.rule_at("order_spread_limit", "2015-06-01", "hk_stock", "XHKG") == \
        {"max_spreads": 24, "wider_pct": None, "reference": ref}
    rec = mr.record_at("order_spread_limit", "2009-06-01", "hk_stock", "XHKG")
    assert rec.id == "hk.order_spread_limit.hk_stock.2005-07-04" and rec.published_at == "2005-06-29"
    assert mr.rule_at("order_spread_limit", "2009-06-01", "hk_etf", "XHKG")["max_spreads"] == 24
    # shares: the wider of 24 spreads or 5% from 2025-08-04
    assert mr.rule_at("order_spread_limit", "2025-08-01", "hk_stock", "XHKG")["wider_pct"] is None
    rec = mr.record_at("order_spread_limit", "2025-08-04", "hk_stock", "XHKG")
    assert rec.value == {"max_spreads": 24, "wider_pct": 0.05, "reference": ref}
    assert (rec.effective_to, rec.published_at) == (None, "2025-07-21")
    assert mr.rule_at("order_spread_limit", "2026-11-03", "hk_stock", "XHKG")["wider_pct"] == 0.05
    # ETFs: the wider of 24 spreads or 3.5% from 2023-03-20 (shares unchanged then)
    assert mr.rule_at("order_spread_limit", "2023-03-17", "hk_etf", "XHKG")["wider_pct"] is None
    assert mr.rule_at("order_spread_limit", "2023-03-20", "hk_etf", "XHKG")["wider_pct"] == 0.035
    assert mr.rule_at("order_spread_limit", "2023-03-20", "hk_stock", "XHKG")["wider_pct"] is None
    assert mr.record_at("order_spread_limit", "2026-11-03", "hk_etf", "XHKG").id == \
        "hk.order_spread_limit.hk_etf.2023-03-20"
    # order-price multiple check: nine times (truncated at the floor) -> five times from 2026-11-02
    mref = "nominal_or_previous_close_for_opening"
    for scope in ("hk_stock", "hk_etf"):
        assert mr.rule_at("order_price_multiple_limit", "2010-01-04", scope, "XHKG") == \
            {"max_multiple": 9, "reference": mref}
        assert mr.rule_at("order_price_multiple_limit", "2026-10-30", scope, "XHKG")["max_multiple"] == 9
        rec = mr.record_at("order_price_multiple_limit", "2026-11-02", scope, "XHKG")
        assert (rec.value["max_multiple"], rec.effective_to, rec.published_at) == (5, None, "2026-10-26")
        rec = mr.record_at("order_price_multiple_limit", "2015-06-01", scope, "XHKG")
        assert (rec.id, rec.published_at) == (f"hk.order_price_multiple_limit.{scope}.2010-01-01", None)
        # before the truncated start: no record and no gap (as for other truncated records)
        with pytest.raises(KeyError):
            mr.rule_at("order_price_multiple_limit", "2009-12-31", scope, "XHKG")
        d = resolve("order_price_multiple_limit", "2009-12-31", scope, "XHKG")
        assert d["status"] == "OUT_OF_COVERAGE" and d["known_gap_ids"] == []
        d = resolve("order_spread_limit", "2015-06-01", scope, "XHKG")
        assert d["status"] == "DETERMINED" and d["verification"] == "single-source"
        assert resolve("order_price_multiple_limit", "2026-11-03", scope, "XHKG",
                       min_verification="verified")["status"] == "UNVERIFIED"
        c = mr.coverage("XHKG", scope, ["order_spread_limit", "order_price_multiple_limit"], HK_FLOOR, HK_END)
        assert c["status"] == "complete" and c["verification"] == "single-source" and not c["known_gap_ids"]
        assert mr.limit_price(10.0, scope, "2026-11-03", "XHKG") is None   # order-entry checks, not a daily limit


_OSL_OK = {"max_spreads": 24, "wider_pct": 0.05, "reference": "same_side_best_or_rule_fallback"}
_OPM_OK = {"max_multiple": 5, "reference": "nominal_or_previous_close_for_opening"}


@pytest.mark.parametrize("value,market", [
    ({**_OSL_OK, "reference": "best_opposite_or_nominal"}, "XHKG"),                         # unknown enum
    ({**_OSL_OK, "reference": None}, "XHKG"),
    ({**_OSL_OK, "max_spreads": 0}, "XHKG"), ({**_OSL_OK, "max_spreads": -24}, "XHKG"),
    ({**_OSL_OK, "max_spreads": 24.0}, "XHKG"), ({**_OSL_OK, "max_spreads": True}, "XHKG"),
    ({**_OSL_OK, "wider_pct": 1}, "XHKG"), ({**_OSL_OK, "wider_pct": 1.5}, "XHKG"),       # wider_pct >= 1
    ({**_OSL_OK, "wider_pct": 0}, "XHKG"), ({**_OSL_OK, "wider_pct": -0.05}, "XHKG"),
    ({**_OSL_OK, "wider_pct": "5%"}, "XHKG"), ({**_OSL_OK, "wider_pct": float("nan")}, "XHKG"),
    ({"max_spreads": 24, "reference": "same_side_best_or_rule_fallback"}, "XHKG"),          # missing wider_pct
    ({**_OSL_OK, "max_multiple": 5}, "XHKG"),                                               # extra key
    (24, "XHKG"), (None, "XHKG"), ([_OSL_OK], "XHKG"),
    (_OSL_OK, "XNYS"), (_OSL_OK, "XNYS+XNAS"), (_OSL_OK, "XSHG"),                           # Hong Kong only
])
def test_hk_order_spread_limit_validation_rejects(value, market):
    with pytest.raises(ValueError):
        mr._check_order_spread_limit(value, "test", market)


@pytest.mark.parametrize("value,market", [
    ({**_OPM_OK, "reference": "nominal"}, "XHKG"), ({**_OPM_OK, "reference": None}, "XHKG"),   # unknown enum
    ({**_OPM_OK, "max_multiple": 1}, "XHKG"), ({**_OPM_OK, "max_multiple": 1.0}, "XHKG"),     # max_multiple <= 1
    ({**_OPM_OK, "max_multiple": 0.2}, "XHKG"), ({**_OPM_OK, "max_multiple": 0}, "XHKG"),
    ({**_OPM_OK, "max_multiple": "5"}, "XHKG"), ({**_OPM_OK, "max_multiple": True}, "XHKG"),
    ({**_OPM_OK, "max_multiple": float("inf")}, "XHKG"),
    ({"max_multiple": 5}, "XHKG"), ({**_OPM_OK, "wider_pct": None}, "XHKG"),                  # missing / extra key
    (5, "XHKG"), (None, "XHKG"),
    (_OPM_OK, "XNYS"), (_OPM_OK, "XNAS"), (_OPM_OK, "XSHE"),                                  # Hong Kong only
])
def test_hk_order_price_multiple_limit_validation_rejects(value, market):
    with pytest.raises(ValueError):
        mr._check_order_price_multiple_limit(value, "test", market)


def test_hk_order_limit_validation_accepts():
    for v in (_OSL_OK, {**_OSL_OK, "wider_pct": None}, {**_OSL_OK, "wider_pct": 0.035}):
        mr._check_order_spread_limit(v, "test", "XHKG")
    for v in (_OPM_OK, {**_OPM_OK, "max_multiple": 9}, {**_OPM_OK, "max_multiple": 9.5}):
        mr._check_order_price_multiple_limit(v, "test", "XHKG")
    for r in mr.records():   # the records themselves passed the same checks at load
        if r.rule == "order_spread_limit":
            mr._check_order_spread_limit(r.value, r.id, r.market)
        elif r.rule == "order_price_multiple_limit":
            mr._check_order_price_multiple_limit(r.value, r.id, r.market)


# --- US equities (XNYS, XNAS, data/us/) ------------------------------------------------------------------------------
US_FLOOR, US_END = "2010-01-01", "2026-11-04"
# Federal and national-plan rules: one record for both exchanges (market XNYS+XNAS).
US_RULES = ("sec_fee_rate_sell", "finra_taf_sell", "settlement_cycle_days", "min_holding_days", "min_quote_increment",
            "price_limit_pct", "luld_band", "mwcb_decline_levels", "single_stock_pause_pct", "cat_fee_per_share",
            "cat_historical_assessment_per_share", "short_sale_price_test", "pattern_day_trader_min_equity")
# Per-exchange rules: market XNYS or XNAS = the security's primary listing exchange; never XNYS+XNAS.
US_EXCHANGE_RULES = ("session_schedule", "extended_hours")
US_SCOPES = ("us_stock", "us_etf")
US_KEYS = [(s, r) for s in US_SCOPES for r in US_RULES + US_EXCHANGE_RULES]
# (scope, rule) -> first day Marina is expected to answer; before it there is no record and no gap
# (the LULD Plan's phase I began on 2013-04-08; the trading-pause pilot on 2010-06-11, for ETFs on 2010-09-14; CAT LLC
# first billed September 2024 transactions for its fee and October 2024 transactions for the historical assessment).
US_START = {**{(s, "luld_band"): "2013-04-08" for s in US_SCOPES},
            ("us_stock", "single_stock_pause_pct"): "2010-06-11", ("us_etf", "single_stock_pause_pct"): "2010-09-14",
            **{(s, "cat_fee_per_share"): "2024-09-01" for s in US_SCOPES},
            **{(s, "cat_historical_assessment_per_share"): "2024-10-01" for s in US_SCOPES}}
# (scope, rule) -> day the mechanism ended (LULD covered all NMS stocks on 2013-12-08): from it, no record and no gap.
US_STOP = {(s, "single_stock_pause_pct"): "2013-12-08" for s in US_SCOPES}
US_COVER = [(s, r, m) for s in US_SCOPES for r in US_RULES for m in ("XNYS+XNAS", "XNYS", "XNAS")] + \
           [(s, r, m) for s in US_SCOPES for r in US_EXCHANGE_RULES for m in ("XNYS", "XNAS")]
US_GAPS = {   # gap id -> (market, scope, rule, from, to)
    "G-US-0001": ("XNYS+XNAS", "us_stock", "price_limit_pct", US_FLOOR, None),
    "G-US-0002": ("XNYS+XNAS", "us_etf", "price_limit_pct", US_FLOOR, None),
    "G-US-0003": ("XNAS", "us_stock", "extended_hours", US_FLOOR, "2013-03-18"),
    "G-US-0004": ("XNAS", "us_etf", "extended_hours", US_FLOOR, "2013-03-18"),
    "G-US-0005": ("XNYS+XNAS", "us_stock", "luld_band", "2013-04-08", "2013-12-08"),
    "G-US-0006": ("XNYS+XNAS", "us_etf", "luld_band", "2013-04-08", "2013-12-08"),
    "G-US-0007": ("XNYS", "us_etf", "session_schedule", US_FLOOR, None),
    "G-US-0008": ("XNYS", "us_stock", "extended_hours", US_FLOOR, None),
    "G-US-0009": ("XNYS", "us_etf", "extended_hours", US_FLOOR, None),
    "G-US-0010": ("XNYS+XNAS", "us_stock", "single_stock_pause_pct", "2010-06-11", "2011-08-08"),
    "G-US-0011": ("XNYS+XNAS", "us_stock", "single_stock_pause_pct", "2013-04-08", "2013-12-08"),
    "G-US-0012": ("XNYS+XNAS", "us_etf", "single_stock_pause_pct", "2010-09-14", "2011-08-08"),
    "G-US-0013": ("XNYS+XNAS", "us_etf", "single_stock_pause_pct", "2013-04-08", "2013-12-08"),
    "G-US-0014": ("XNYS+XNAS", "us_stock", "pattern_day_trader_min_equity", "2026-06-04", None),
    "G-US-0015": ("XNYS+XNAS", "us_etf", "pattern_day_trader_min_equity", "2026-06-04", None),
}
_HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def _us():
    return [r for r in mr.records() if r.file.startswith("us/")]


def _numbers(v):
    if isinstance(v, dict):
        for x in v.values():
            yield from _numbers(x)
    elif isinstance(v, list):
        for x in v:
            yield from _numbers(x)
    elif isinstance(v, (int, float)) and not isinstance(v, bool):
        yield v


def _window(w):
    return isinstance(w, list) and len(w) == 2 and all(isinstance(x, str) and _HHMM.match(x) for x in w) and w[0] < w[1]


def test_us_loads_scopes_and_gaps():
    us = _us()
    assert len(us) == 107 and {r.market for r in us} == {"XNYS+XNAS", "XNYS", "XNAS"} and all(r.id.startswith("us.") for r in us)
    assert sum(r.verification == "verified" for r in us) == 14 and sum(r.verification == "single-source" for r in us) == 93
    assert {(r.scope, r.rule) for r in us} == set(US_KEYS) - {("us_stock", "price_limit_pct"), ("us_etf", "price_limit_pct")}
    for r in us:   # national rules name both exchanges; sessions name one, and say so in the id
        if r.rule in US_EXCHANGE_RULES:
            assert r.market in ("XNYS", "XNAS") and f".{r.market.lower()}." in r.id, r.id
        else:
            assert r.market == "XNYS+XNAS", r.id
    reg = mr.scopes("us")
    assert set(reg) == {"us_stock", "us_etf"} and not set(reg) & (set(mr.scopes("cn")) | set(mr.scopes("hk")))
    assert reg["us_stock"]["excludes"] == ("us_etf",) and reg["us_etf"]["requires"] == ()
    for r in us:   # value shapes of the US rules (docs/SCHEMA.md)
        if r.rule == "sec_fee_rate_sell":
            assert isinstance(r.value, float) and 0 <= r.value < 0.0001 and r.unit is None, r.id
        elif r.rule == "finra_taf_sell":
            assert set(r.value) == {"per_share", "max_per_trade"} and r.unit == "USD", r.id
            assert 0 <= r.value["per_share"] < 0.001 and 0 <= r.value["max_per_trade"] < 20, r.id
        elif r.rule == "min_quote_increment":
            assert r.value == {"threshold": 1.0, "at_or_above": 0.01, "below": 0.0001} and r.unit == "USD", r.id
        elif r.rule in ("settlement_cycle_days", "min_holding_days"):
            assert isinstance(r.value, int) and r.value >= 0 and r.unit is None, r.id
        elif r.rule == "session_schedule":   # US shape: core window and instantaneous crosses, no call windows
            assert r.value == {"open_call": None, "continuous": [["09:30", "16:00"]], "close_call": None,
                               "open_cross": "09:30", "close_cross": "16:00"} and r.unit is None, r.id
        elif r.rule == "extended_hours":
            assert set(r.value) == {"pre_market", "post_market"} and r.unit is None, r.id
            assert all(_window(w) for w in r.value.values()), r.id
            assert r.value["pre_market"][1] == "09:30" and r.value["post_market"][0] == "16:00", r.id
        elif r.rule == "luld_band":   # also validated at load (brackets cover every positive price once)
            assert set(r.value) == {"tier_1", "tier_2", "hours"} and r.unit == "USD" and _window(r.value["hours"]), r.id
            for tier in ("tier_1", "tier_2"):
                assert [set(b) & {"gt", "ge", "lt", "le"} for b in r.value[tier]] == [{"gt"}, {"ge", "le"}, {"lt"}], r.id
                assert all(0 < b["pct"] <= 0.75 for b in r.value[tier]), r.id
        elif r.rule == "mwcb_decline_levels":
            assert set(r.value) == {"reference", "levels"} and r.unit is None, r.id
            assert r.value["reference"] in ("djia_quarterly_points", "sp500_prev_close"), r.id
            assert len(r.value["levels"]) == 3 and r.value["levels"] == sorted(r.value["levels"]), r.id
        elif r.rule == "single_stock_pause_pct":   # also validated at load (each group covers every positive price once)
            assert set(r.value) == {"sp500_constituents", "russell1000_constituents", "specified_etps", "other_nms_stocks",
                                    "hours", "lookback_minutes"} and r.unit == "USD", r.id
            assert r.value["hours"] == ["09:45", "15:35"] and r.value["lookback_minutes"] == 5, r.id
        elif r.rule in ("cat_fee_per_share", "cat_historical_assessment_per_share"):   # USD per executed equivalent share
            assert isinstance(r.value, (int, float)) and 0 <= r.value < 0.0001 and r.unit == "USD", r.id
            assert r.effective_from >= "2024-09-01" and r.effective_from[8:] == "01", r.id   # billed transaction months
        elif r.rule == "short_sale_price_test":   # also validated at load
            assert r.unit is None and (r.value == "none" or set(r.value) == {"trigger_decline_pct", "reference",
                                                                             "restriction", "duration"}), r.id
        elif r.rule == "pattern_day_trader_min_equity":   # also validated at load
            assert set(r.value) == {"min_equity", "day_trades", "window_business_days"} and r.unit == "USD", r.id
    # ETFs share every value with common stocks (no ETF session record on XNYS: G-US-0007)
    by = {(r.rule, r.market, r.effective_from, r.scope): r for r in us}
    for (rule, market, ef, scope), r in by.items():
        if scope == "us_stock" and (rule, market) != ("session_schedule", "XNYS"):
            o = by[(rule, market, ef, "us_etf")]
            assert (o.value, o.effective_to, o.verification) == (r.value, r.effective_to, r.verification), r.id
            if rule != "session_schedule":   # the Nasdaq ETF session record also cites the FAQ's ETP passages
                assert o.sources == r.sources, r.id
    gaps = mr.known_gaps("us")
    assert [g["gap_id"] for g in gaps] == sorted(US_GAPS)
    for g in gaps:
        m, scope, rule, g0, g1 = US_GAPS[g["gap_id"]]
        assert (g["market"], g["scope"], g["rule"], g["status"]) == (m, scope, rule, "open"), g["gap_id"]
        assert g["interval"] == {"from": g0, "to": g1} and g["reason"].strip() and g["evidence"], g["gap_id"]
        assert len(g["evidence"]) == len(set(g["evidence"])), g["gap_id"]
    assert mr.market_prefix_for("XNYS") == mr.market_prefix_for("XNAS") == mr.market_prefix_for("XNYS+XNAS") == "us"
    assert mr.market_prefix_for("XHKG") == "hk" and mr.market_prefix_for("XSHG") == mr.market_prefix_for(None) == "cn"
    assert mr.market_prefix_for("XNYS+XHKG") == "cn"   # a set that mixes families falls back to cn


def test_us_values_are_clean_decimals():
    """Every number in the US data is the decimal the source states, not a float with a binary tail."""
    for r in _us():
        for x in _numbers(r.value):
            assert float(f"{x:.6g}") == x, (r.id, x)
            assert "9999" not in repr(x) and "0000" not in repr(x), (r.id, repr(x))


@pytest.mark.parametrize("scope,rule,market", US_COVER)
def test_us_records_and_gaps_cover_the_window(scope, rule, market):
    """Every (scope, rule, market) is answered or declared a known gap on every day from its start to 2026-11-04."""
    start, stop = US_START.get((scope, rule), US_FLOOR), US_STOP.get((scope, rule), US_END)
    c = mr.coverage(market, scope, [rule], start, stop)
    assert c["scope_known"] and not c["conflicts"]
    if c["status"] == "unsupported":   # no record at all: declared gaps must tile the whole window, open-ended
        kg = sorted(mr.gaps_for(market, scope, rule, start, stop), key=lambda g: g["interval"]["from"])
        assert kg and kg[0]["interval"]["from"] <= start and kg[-1]["interval"]["to"] is None
        assert all(a["interval"]["to"] == b["interval"]["from"] for a, b in zip(kg, kg[1:]))
        assert c["known_gap_ids"] == sorted(g["gap_id"] for g in kg)
        return
    for g in c["gaps"]:
        assert len(g["known_gap_ids"]) == 1, g
        gap = US_GAPS[g["known_gap_ids"][0]]
        assert gap[3] <= g["from"] and (gap[4] is None or g["to"] <= gap[4]), g
    assert c["status"] == ("partial" if c["gaps"] else "complete")
    if stop < US_END:   # nothing after the mechanism ended: no record, no gap
        d = __import__("marina_rules.contract", fromlist=["resolve"]).resolve(rule, stop, scope, market)
        assert d["status"] == "OUT_OF_COVERAGE" and d["known_gap_ids"] == []
        assert not mr.gaps_for(market, scope, rule, stop, US_END)
    if start > US_FLOOR:   # nothing before commencement: no record, no gap
        eve = (dt.date.fromisoformat(start) - dt.timedelta(days=1)).isoformat()
        d = __import__("marina_rules.contract", fromlist=["resolve"]).resolve(rule, eve, scope, market)
        assert d["status"] == "OUT_OF_COVERAGE" and d["known_gap_ids"] == []


@pytest.mark.parametrize("scope,rule", [(s, r) for s in US_SCOPES for r in US_EXCHANGE_RULES])
def test_us_exchange_rules_are_not_answered_for_both_exchanges(scope, rule):
    """A per-exchange rule is never answered for market XNYS+XNAS (subset matching): pick the listing exchange."""
    c = mr.coverage("XNYS+XNAS", scope, [rule], US_FLOOR, US_END)
    assert c["status"] == "unsupported" and c["records"] == []
    with pytest.raises(KeyError):
        mr.rule_at(rule, "2024-06-14", scope, "XNYS+XNAS")


def test_us_equity_rules():
    from marina_rules.contract import resolve

    for scope in ("us_stock", "us_etf"):
        # settlement cycle: T+3 -> T+2 on 2017-09-05 -> T+1 on 2024-05-28 (both switches verified)
        assert mr.rule_at("settlement_cycle_days", "2017-09-04", scope, "XNYS") == 3
        rec = mr.record_at("settlement_cycle_days", "2017-09-05", scope, "XNAS")
        assert (rec.value, rec.verification) == (2, "verified")
        assert mr.rule_at("settlement_cycle_days", "2024-05-27", scope, "XNYS") == 2
        rec = mr.record_at("settlement_cycle_days", "2024-05-28", scope, "XNYS+XNAS")
        assert (rec.value, rec.verification, rec.effective_to) == (1, "verified", None)
        assert resolve("settlement_cycle_days", "2024-06-14", scope, "XNYS", min_verification="verified")["status"] == "DETERMINED"
        # Section 31: 27.80 per million to 2025-05-14, 0 to 2026-04-04, then 20.60 per million (verified)
        assert mr.rule_at("sec_fee_rate_sell", "2010-01-01", scope, "XNYS") == 2.57e-05
        assert mr.rule_at("sec_fee_rate_sell", "2010-01-15", scope, "XNYS") == 1.27e-05
        assert mr.rule_at("sec_fee_rate_sell", "2025-05-13", scope, "XNYS") == 2.78e-05
        assert mr.rule_at("sec_fee_rate_sell", "2025-05-14", scope, "XNAS") == 0
        assert mr.rule_at("sec_fee_rate_sell", "2026-04-03", scope, "XNAS") == 0
        rec = mr.record_at("sec_fee_rate_sell", "2026-04-04", scope, "XNYS")
        assert (rec.value, rec.verification, rec.effective_to, rec.unit) == (2.06e-05, "verified", None, None)
        with pytest.raises(KeyError):
            mr.rule_at("sec_fee_rate_sell", "2009-12-31", scope, "XNYS")
        # FINRA TAF: 0.000195 / 9.79 in 2026, the fee holiday 2026-10-01 .. 2026-12-31, nothing recorded from 2027
        assert mr.rule_at("finra_taf_sell", "2026-09-30", scope, "XNYS") == {"per_share": 0.000195, "max_per_trade": 9.79}
        rec = mr.record_at("finra_taf_sell", "2026-10-01", scope, "XNYS")
        assert (rec.value, rec.unit, rec.effective_to, rec.published_at) == (
            {"per_share": 0, "max_per_trade": 0}, "USD", "2027-01-01", "2026-09-23")
        assert mr.rule_at("finra_taf_sell", "2026-12-31", scope, "XNAS") == {"per_share": 0, "max_per_trade": 0}
        with pytest.raises(KeyError):
            mr.rule_at("finra_taf_sell", "2027-01-01", scope, "XNYS")
        d = resolve("finra_taf_sell", "2027-01-04", scope, "XNYS")
        assert d["status"] == "OUT_OF_COVERAGE" and d["known_gap_ids"] == []
        assert mr.rule_at("finra_taf_sell", "2012-07-01", scope, "XNYS") == {"per_share": 0.000119, "max_per_trade": 5.95}
        # Rule 612 minimum quotation increment, from the 2006-01-31 compliance date
        rec = mr.record_at("min_quote_increment", "2024-06-14", scope, "XNAS")
        assert (rec.value, rec.unit, rec.effective_from) == ({"threshold": 1.0, "at_or_above": 0.01, "below": 0.0001},
                                                             "USD", "2006-01-31")
        # same-day resale is an inference: refused at the verified bar
        assert mr.rule_at("min_holding_days", "2024-06-14", scope, "XNYS") == 0
        assert resolve("min_holding_days", "2024-06-14", scope, "XNYS", min_verification="verified")["status"] == "UNVERIFIED"
        # no daily price limit record: a declared gap, not unlimited
        with pytest.raises(KeyError):
            mr.rule_at("price_limit_pct", "2024-06-14", scope, "XNYS")
        with pytest.raises(KeyError):
            mr.limit_price(10.0, scope, "2024-06-14", "XNYS")
        d = resolve("price_limit_pct", "2024-06-14", scope, "XNAS")
        assert d["status"] == "OUT_OF_COVERAGE" and d["known_gap_ids"] == [{"us_stock": "G-US-0001", "us_etf": "G-US-0002"}[scope]]
    # the us registry is found from the market; other markets never see us records
    with pytest.raises(KeyError):
        mr.rule_at("settlement_cycle_days", "2024-06-14", "us_stock", "XHKG")
    with pytest.raises(KeyError):
        mr.rule_at("settlement_cycle_days", "2024-06-14", "hk_stock", "XNYS")
    assert mr.rule_at("settlement_cycle_days", "2024-06-14", "hk_stock", "XHKG") == 2


def _luld(price: float, tier: str, date: str, scope: str = "us_stock") -> dict:
    """The LULD bracket for ``price`` (the reference price) in ``tier`` from the luld_band record in force."""
    for b in mr.rule_at("luld_band", date, scope, "XNYS+XNAS")[tier]:
        if (("gt" not in b or price > b["gt"]) and ("ge" not in b or price >= b["ge"])
                and ("lt" not in b or price < b["lt"]) and ("le" not in b or price <= b["le"])):
            return b
    raise ValueError(f"{price} in no bracket")


def _in(t: str, windows) -> bool:
    return any(a <= t < b for a, b in windows)


def test_us_second_batch_luld():
    from marina_rules.contract import resolve

    for scope in US_SCOPES:
        # 2014-06-02: Tier 1 above USD 3 -> 5%, doubled in the first 15 and the last 25 minutes (to 16:00 from 2014-02-24)
        b = _luld(10.0, "tier_1", "2014-06-02", scope)
        assert b["pct"] == 0.05 and _in("15:40", b["doubled"]) and _in("09:30", b["doubled"]) and not _in("12:00", b["doubled"])
        assert _luld(10.0, "tier_2", "2014-06-02", scope)["pct"] == 0.1
        assert mr.rule_at("luld_band", "2014-06-02", scope, "XNAS")["hours"] == ["09:30", "16:00"]
        # bracket bounds: 3.00 is in the 20% bracket (le), 0.75 too (ge); below 0.75: 75% capped at USD 0.15
        assert _luld(3.0, "tier_1", "2014-06-02", scope)["pct"] == 0.2 and _luld(3.01, "tier_1", "2014-06-02", scope)["pct"] == 0.05
        assert _luld(0.75, "tier_2", "2014-06-02", scope)["pct"] == 0.2
        low = _luld(0.5, "tier_2", "2014-06-02", scope)
        assert (low["pct"], low["abs_cap"]) == (0.75, 0.15)
        # 2013-12-08 .. 2014-02-24: the Plan ran to 15:45 only, so closing doubling was 15:35-15:45
        rec = mr.record_at("luld_band", "2013-12-09", scope, "XNYS")
        assert rec.value["hours"] == ["09:30", "15:45"] and rec.unit == "USD" and rec.effective_to == "2014-02-24"
        assert _luld(10.0, "tier_1", "2013-12-09", scope)["doubled"] == [["09:30", "09:45"], ["15:35", "15:45"]]
        # 2020-02-24 (Amendment 18): no opening doubling; Tier 2 above USD 3 never doubled; other closing doubling stays
        assert _luld(10.0, "tier_2", "2020-02-21", scope)["doubled"] == [["09:30", "09:45"], ["15:35", "16:00"]]
        assert _luld(10.0, "tier_2", "2020-03-02", scope)["doubled"] == []
        assert _luld(2.0, "tier_2", "2020-03-02", scope)["doubled"] == [["15:35", "16:00"]]
        assert _luld(10.0, "tier_1", "2020-03-02", scope)["doubled"] == [["15:35", "16:00"]]
        assert not _in("09:35", _luld(10.0, "tier_1", "2020-03-02", scope)["doubled"])
        # phase-in 2013-04-08 .. 2013-12-08 is a known gap; before the Plan there is no record and no gap
        gid = {"us_stock": "G-US-0005", "us_etf": "G-US-0006"}[scope]
        with pytest.raises(KeyError):
            mr.rule_at("luld_band", "2013-05-01", scope, "XNYS")
        d = resolve("luld_band", "2013-05-01", scope, "XNYS")
        assert d["status"] == "OUT_OF_COVERAGE" and d["known_gap_ids"] == [gid]
        d = resolve("luld_band", "2013-04-05", scope, "XNAS")
        assert d["status"] == "OUT_OF_COVERAGE" and d["known_gap_ids"] == []
        assert resolve("luld_band", "2024-06-14", scope, "XNYS", min_verification="verified")["status"] == "UNVERIFIED"
        # an intraday band, not a daily price limit: price_limit_pct stays a known gap
        with pytest.raises(KeyError):
            mr.limit_price(10.0, scope, "2024-06-14", "XNYS")


def test_us_second_batch_mwcb_sessions_section31():
    from marina_rules.contract import resolve

    for scope in US_SCOPES:
        # market-wide circuit breakers: DJIA quarterly points 10/20/30% to 2013-04-08, then S&P 500 7/13/20% (verified)
        assert mr.rule_at("mwcb_decline_levels", "2012-06-01", scope, "XNYS") == {
            "reference": "djia_quarterly_points", "levels": [0.1, 0.2, 0.3]}
        assert mr.rule_at("mwcb_decline_levels", "2013-04-05", scope, "XNAS")["reference"] == "djia_quarterly_points"
        rec = mr.record_at("mwcb_decline_levels", "2013-04-08", scope, "XNYS+XNAS")
        assert (rec.value, rec.verification, rec.effective_to) == (
            {"reference": "sp500_prev_close", "levels": [0.07, 0.13, 0.2]}, "verified", None)
        assert resolve("mwcb_decline_levels", "2026-11-03", scope, "XNAS", min_verification="verified")["status"] == "DETERMINED"
        # Nasdaq extended hours: pre-market 04:00 from 2013-03-18; before it a known gap
        with pytest.raises(KeyError):
            mr.rule_at("extended_hours", "2013-03-15", scope, "XNAS")
        d = resolve("extended_hours", "2013-03-15", scope, "XNAS")
        assert d["status"] == "OUT_OF_COVERAGE" and d["known_gap_ids"] == [{"us_stock": "G-US-0003", "us_etf": "G-US-0004"}[scope]]
        assert mr.rule_at("extended_hours", "2013-03-18", scope, "XNAS") == {"pre_market": ["04:00", "09:30"],
                                                                             "post_market": ["16:00", "20:00"]}
        # NYSE extended hours: known gaps over the whole window
        d = resolve("extended_hours", "2024-06-14", scope, "XNYS")
        assert d["status"] == "OUT_OF_COVERAGE" and d["known_gap_ids"] == [{"us_stock": "G-US-0008", "us_etf": "G-US-0009"}[scope]]
        # Nasdaq sessions: regular 09:30-16:00, opening / closing crosses, for both scopes from the coverage floor
        s = mr.rule_at("session_schedule", "2010-01-04", scope, "XNAS")
        assert (s["continuous"], s["open_cross"], s["close_cross"], s["open_call"], s["close_call"]) == (
            [["09:30", "16:00"]], "09:30", "16:00", None, None)
        # per-exchange rule: market XNYS+XNAS (both exchanges) is never answered
        with pytest.raises(KeyError):
            mr.rule_at("session_schedule", "2024-06-14", scope, "XNYS+XNAS")
        assert resolve("session_schedule", "2024-06-14", scope, "XNYS+XNAS")["status"] == "OUT_OF_COVERAGE"
        # Section 31 2010-01-15 upgraded to verified (FINRA notice + SEC mid-year order appendix); value unchanged
        rec = mr.record_at("sec_fee_rate_sell", "2010-01-15", scope, "XNYS")
        assert (rec.value, rec.verification, rec.effective_to, len(rec.sources)) == (1.27e-05, "verified", "2010-04-01", 3)
        assert resolve("sec_fee_rate_sell", "2010-03-31", scope, "XNAS", min_verification="verified")["status"] == "DETERMINED"
    # NYSE sessions: NYSE-listed common stocks only; NYSE-listed ETFs are a known gap
    rec = mr.record_at("session_schedule", "2024-06-14", "us_stock", "XNYS")
    assert rec.value["close_cross"] == "16:00" and rec.id == "us.session_schedule.us_stock.xnys.2010-01-01"
    assert (rec.market, rec.effective_from, rec.effective_to, rec.verification) == ("XNYS", "2010-01-01", None, "single-source")
    d = resolve("session_schedule", "2024-06-14", "us_etf", "XNYS")
    assert d["status"] == "OUT_OF_COVERAGE" and d["known_gap_ids"] == ["G-US-0007"]
    c = mr.coverage("XNAS", "us_stock", ["session_schedule", "extended_hours", "luld_band", "mwcb_decline_levels"],
                    "2014-01-02", US_END)
    assert c["status"] == "complete" and c["verification"] == "single-source"


_LULD_OK = {"hours": ["09:30", "16:00"],
            "tier_1": [{"gt": 3.0, "pct": 0.05, "doubled": [["15:35", "16:00"]]},
                       {"ge": 0.75, "le": 3.0, "pct": 0.2, "doubled": []},
                       {"lt": 0.75, "pct": 0.75, "abs_cap": 0.15, "doubled": []}]}


def _luld_variant(**tier_1):
    v = {"hours": ["09:30", "16:00"], "tier_1": tier_1.pop("segs")}
    v.update(tier_1)
    return v


@pytest.mark.parametrize("value", [
    {"tier_1": _LULD_OK["tier_1"]},                                                                     # no hours
    {"hours": ["09:30", "16:00"]},                                                                     # no tier
    {**_LULD_OK, "band_x": _LULD_OK["tier_1"]},                                                        # not a tier_* key
    _luld_variant(segs=[{"gt": 3.0, "pct": 0.05, "doubled": []}, {"lt": 3.0, "pct": 0.1, "doubled": []}]),   # hole at 3
    _luld_variant(segs=[{"ge": 3.0, "pct": 0.05, "doubled": []}, {"le": 3.0, "pct": 0.1, "doubled": []}]),   # 3 twice
    _luld_variant(segs=[{"gt": 2.0, "pct": 0.05, "doubled": []}, {"lt": 3.0, "pct": 0.1, "doubled": []}]),   # overlap
    _luld_variant(segs=[{"gt": 3.0, "pct": 0.05, "doubled": []}, {"gt": 0.5, "le": 3.0, "pct": 0.1, "doubled": []}]),  # gap below
    _luld_variant(segs=[{"le": 3.0, "pct": 0.05, "doubled": []}]),                                     # no top bracket
    _luld_variant(segs=[{"ge": 0.0, "pct": 0.05, "doubled": []}]),                                     # includes 0
    _luld_variant(segs=[{"gt": 3.0, "ge": 3.0, "pct": 0.05, "doubled": []}, {"le": 3.0, "pct": 0.1, "doubled": []}]),
    _luld_variant(segs=[{"pct": 0, "doubled": []}]),                                                   # pct 0
    _luld_variant(segs=[{"pct": 0.05, "abs_cap": 0, "doubled": []}]),                                  # abs_cap 0
    _luld_variant(segs=[{"pct": 0.05}]),                                                               # no doubled
    _luld_variant(segs=[{"pct": 0.05, "doubled": [["15:35", "16:15"]]}]),                              # outside hours
    _luld_variant(segs=[{"pct": 0.05, "doubled": [["16:00", "15:35"]]}]),                              # reversed window
    _luld_variant(segs=[{"pct": 0.05, "doubled": [], "tick": 0.01}]),                                  # unknown key
    _luld_variant(segs=[{"over": 3.0, "pct": 0.05, "doubled": []}, {"lt": 3.0, "pct": 0.1, "doubled": []}]),
])
def test_luld_band_validation_rejects(value):
    with pytest.raises(ValueError):
        mr._check_luld_band(value, "test")


def test_luld_band_validation_accepts():
    mr._check_luld_band(_LULD_OK, "test")
    mr._check_luld_band({"hours": ["09:30", "16:00"], "tier_1": [{"pct": 0.05, "doubled": []}]}, "test")   # one bracket
    mr._check_luld_band({"hours": ["09:30", "16:00"], "tier_1": [{"gt": 0.0, "lt": 1.0, "pct": 0.1, "doubled": []},
                                                                 {"ge": 1.0, "pct": 0.05, "doubled": []}]}, "test")


def _pause_pct(price: float, group: str, date: str, scope: str = "us_stock", market: str = "XNYS") -> float:
    """The trading-pause trigger for a security of ``group`` whose bracket price is ``price``."""
    for b in mr.rule_at("single_stock_pause_pct", date, scope, market)[group]:
        if (("gt" not in b or price > b["gt"]) and ("ge" not in b or price >= b["ge"])
                and ("lt" not in b or price < b["lt"]) and ("le" not in b or price <= b["le"])):
            return b["pct"]
    raise ValueError(f"{price} in no bracket")


def test_us_third_batch_single_stock_pause():
    from marina_rules.contract import resolve

    for scope in US_SCOPES:
        # Phase III from 2011-08-08: named groups 10%; other NMS stocks 30% at or above USD 1 (ge), 50% below it
        for market in ("XNYS", "XNAS", "XNYS+XNAS"):
            assert _pause_pct(0.5, "other_nms_stocks", "2012-06-01", scope, market) == 0.5
        assert _pause_pct(1.0, "other_nms_stocks", "2012-06-01", scope) == 0.3
        assert _pause_pct(0.9999, "other_nms_stocks", "2012-06-01", scope) == 0.5
        assert _pause_pct(250.0, "other_nms_stocks", "2012-06-01", scope) == 0.3
        for group in ("sp500_constituents", "russell1000_constituents", "specified_etps"):
            assert _pause_pct(0.5, group, "2012-06-01", scope) == _pause_pct(80.0, group, "2012-06-01", scope) == 0.1
        rec = mr.record_at("single_stock_pause_pct", "2011-08-08", scope, "XNAS")
        assert (rec.id, rec.market, rec.unit, rec.verification, rec.effective_to, rec.published_at) == (
            f"us.single_stock_pause_pct.{scope}.2011-08-08", "XNYS+XNAS", "USD", "verified", "2013-04-08", "2011-08-04")
        assert rec.value["hours"] == ["09:45", "15:35"] and rec.value["lookback_minutes"] == 5
        assert resolve("single_stock_pause_pct", "2013-04-05", scope, "XNYS", min_verification="verified")["status"] == "DETERMINED"
        # LULD phase-in 2013-04-08 .. 2013-12-08: mixed mechanisms, a known gap; from 2013-12-08 no record and no gap
        gid = {"us_stock": "G-US-0011", "us_etf": "G-US-0013"}[scope]
        for day in ("2013-04-08", "2013-12-06"):
            with pytest.raises(KeyError):
                mr.rule_at("single_stock_pause_pct", day, scope, "XNYS")
            d = resolve("single_stock_pause_pct", day, scope, "XNAS")
            assert d["status"] == "OUT_OF_COVERAGE" and d["known_gap_ids"] == [gid]
        d = resolve("single_stock_pause_pct", "2014-06-02", scope, "XNYS")
        assert d["status"] == "OUT_OF_COVERAGE" and d["known_gap_ids"] == []
    # pilot phases I and II: activated security by security, a known gap; before the pilot no record and no gap
    for scope, day, gid in (("us_stock", "2010-06-11", "G-US-0010"), ("us_stock", "2011-01-03", "G-US-0010"),
                            ("us_stock", "2011-08-05", "G-US-0010"), ("us_etf", "2010-09-14", "G-US-0012"),
                            ("us_etf", "2011-01-03", "G-US-0012")):
        with pytest.raises(KeyError):
            mr.rule_at("single_stock_pause_pct", day, scope, "XNYS")
        d = resolve("single_stock_pause_pct", day, scope, "XNYS")
        assert d["status"] == "OUT_OF_COVERAGE" and d["known_gap_ids"] == [gid], (scope, day)
    for scope, day in (("us_stock", "2010-06-10"), ("us_etf", "2010-09-13"), ("us_etf", "2010-06-14")):
        d = resolve("single_stock_pause_pct", day, scope, "XNAS")
        assert d["status"] == "OUT_OF_COVERAGE" and d["known_gap_ids"] == [], (scope, day)
    c = mr.coverage("XNYS", "us_stock", ["single_stock_pause_pct"], "2010-06-11", "2013-12-08")
    assert c["status"] == "partial" and sorted(c["known_gap_ids"]) == ["G-US-0010", "G-US-0011"]
    # an intraday trigger, not a daily price limit
    with pytest.raises(KeyError):
        mr.limit_price(10.0, "us_stock", "2012-06-01", "XNYS")


def test_us_third_batch_cat_fees():
    from marina_rules.contract import resolve

    for scope in US_SCOPES:
        for market in ("XNYS", "XNAS", "XNYS+XNAS"):
            # CAT Fee (USD per executed equivalent share, per CEBB / CEBS): by charged transaction month
            assert mr.rule_at("cat_fee_per_share", "2024-09-02", scope, market) == 0.000035
            assert mr.rule_at("cat_fee_per_share", "2024-12-31", scope, market) == 0.000035
            assert mr.rule_at("cat_fee_per_share", "2025-01-02", scope, market) == 0.000022
            assert mr.rule_at("cat_fee_per_share", "2025-07-01", scope, market) == 0.000009
            assert mr.rule_at("cat_fee_per_share", "2025-12-15", scope, market) == 0
            assert mr.rule_at("cat_fee_per_share", "2026-04-30", scope, market) == 0
            assert mr.rule_at("cat_fee_per_share", "2026-05-01", scope, market) == 0.000001
            # Historical CAT Assessment: 1 from October 2024, none Dec 2025 - Apr 2026, Assessment 1A from May 2026
            assert mr.rule_at("cat_historical_assessment_per_share", "2024-10-01", scope, market) == 0.000013
            assert mr.rule_at("cat_historical_assessment_per_share", "2025-11-28", scope, market) == 0.000013
            assert mr.rule_at("cat_historical_assessment_per_share", "2025-12-15", scope, market) == 0
            assert mr.rule_at("cat_historical_assessment_per_share", "2026-06-01", scope, market) == 0.000002
        for rule, first in (("cat_fee_per_share", "2024-09-01"), ("cat_historical_assessment_per_share", "2024-10-01")):
            rec = mr.record_at(rule, "2026-11-03", scope, "XNYS")
            assert (rec.unit, rec.verification, rec.effective_to, rec.effective_from) == (
                "USD", "single-source", None, "2026-05-01")
            assert resolve(rule, "2026-11-03", scope, "XNAS", min_verification="verified")["status"] == "UNVERIFIED"
            # before the first billed transaction month: no record and no gap (earlier invoices were tests)
            eve = (dt.date.fromisoformat(first) - dt.timedelta(days=1)).isoformat()
            d = resolve(rule, eve, scope, "XNYS")
            assert d["status"] == "OUT_OF_COVERAGE" and d["known_gap_ids"] == [], (rule, eve)
        d = resolve("cat_fee_per_share", "2024-08-30", scope, "XNYS")
        assert d["status"] == "OUT_OF_COVERAGE" and d["known_gap_ids"] == []
        d = resolve("cat_historical_assessment_per_share", "2024-09-16", scope, "XNAS")
        assert d["status"] == "OUT_OF_COVERAGE" and d["known_gap_ids"] == []
        c = mr.coverage("XNYS", scope, ["cat_fee_per_share", "cat_historical_assessment_per_share"], "2024-10-01", US_END)
        assert c["status"] == "complete" and c["verification"] == "single-source"


_PAUSE_OK = {"sp500_constituents": [{"gt": 0.0, "pct": 0.1}],
             "other_nms_stocks": [{"ge": 1.0, "pct": 0.3}, {"lt": 1.0, "pct": 0.5}],
             "hours": ["09:45", "15:35"], "lookback_minutes": 5}


@pytest.mark.parametrize("value", [
    {k: v for k, v in _PAUSE_OK.items() if k != "hours"},                                              # no hours
    {k: v for k, v in _PAUSE_OK.items() if k != "lookback_minutes"},                                   # no lookback
    {"hours": ["09:45", "15:35"], "lookback_minutes": 5},                                              # no group
    {**_PAUSE_OK, "hours": ["15:35", "09:45"]},                                                        # reversed hours
    {**_PAUSE_OK, "hours": ["9:45", "15:35"]},                                                         # not HH:MM
    {**_PAUSE_OK, "lookback_minutes": 0},
    {**_PAUSE_OK, "lookback_minutes": 5.0},
    {**_PAUSE_OK, "lookback_minutes": True},
    {**_PAUSE_OK, "Other-Stocks": [{"gt": 0.0, "pct": 0.1}]},                                          # bad group name
    {**_PAUSE_OK, "other_nms_stocks": []},                                                             # empty group
    {**_PAUSE_OK, "other_nms_stocks": [{"gt": 1.0, "pct": 0.3}, {"lt": 1.0, "pct": 0.5}]},             # hole at 1
    {**_PAUSE_OK, "other_nms_stocks": [{"ge": 1.0, "pct": 0.3}, {"le": 1.0, "pct": 0.5}]},             # 1 twice
    {**_PAUSE_OK, "other_nms_stocks": [{"ge": 0.5, "pct": 0.3}, {"lt": 1.0, "pct": 0.5}]},             # overlap
    {**_PAUSE_OK, "other_nms_stocks": [{"ge": 1.0, "pct": 0.3}, {"gt": 0.1, "lt": 1.0, "pct": 0.5}]},  # misses (0, 0.1]
    {**_PAUSE_OK, "other_nms_stocks": [{"lt": 1.0, "pct": 0.5}]},                                      # no top bracket
    {**_PAUSE_OK, "sp500_constituents": [{"ge": 0.0, "pct": 0.1}]},                                    # includes 0
    {**_PAUSE_OK, "sp500_constituents": [{"gt": 0.0, "pct": 0}]},                                      # pct 0
    {**_PAUSE_OK, "sp500_constituents": [{"gt": 0.0}]},                                                # no pct
    {**_PAUSE_OK, "sp500_constituents": [{"gt": 0.0, "pct": 0.1, "doubled": []}]},                     # LULD-only key
    {**_PAUSE_OK, "sp500_constituents": [{"gt": 0.0, "ge": 0.0, "pct": 0.1}]},                         # two lower bounds
    {**_PAUSE_OK, "sp500_constituents": {"gt": 0.0, "pct": 0.1}},                                      # not a list
    [_PAUSE_OK],
])
def test_single_stock_pause_validation_rejects(value):
    with pytest.raises(ValueError):
        mr._check_single_stock_pause(value, "test")


def test_single_stock_pause_validation_accepts():
    mr._check_single_stock_pause(_PAUSE_OK, "test")
    mr._check_single_stock_pause({"any_group": [{"pct": 0.1}], "hours": ["09:45", "15:35"], "lookback_minutes": 1}, "test")
    mr._check_single_stock_pause({"g": [{"le": 1.0, "pct": 0.5}, {"gt": 1.0, "pct": 0.3}], "hours": ["09:30", "16:00"],
                                  "lookback_minutes": 5}, "test")
    for r in mr.records():   # the records themselves passed the same check at load
        if r.rule == "single_stock_pause_pct":
            mr._check_single_stock_pause(r.value, r.id)


def test_us_fourth_batch_short_sale_price_test():
    from marina_rules.contract import resolve

    rule_201 = {"trigger_decline_pct": 0.1, "reference": "prior_close", "restriction": "above_national_best_bid",
                "duration": "rest_of_day_and_next_day"}
    for scope in US_SCOPES:
        for market in ("XNYS", "XNAS", "XNYS+XNAS"):
            # no price test from the 2007 compliance date (also before the coverage floor) until Rule 201 compliance
            for day in ("2007-07-06", "2010-01-04", "2010-06-01", "2010-11-10", "2011-02-25"):
                assert mr.rule_at("short_sale_price_test", day, scope, market) == "none", (scope, market, day)
            for day in ("2011-02-28", "2020-01-02", "2026-11-03"):
                assert mr.rule_at("short_sale_price_test", day, scope, market) == rule_201, (scope, market, day)
        d = resolve("short_sale_price_test", "2010-06-01", scope, "XNYS")
        assert d["status"] == "DETERMINED" and d["result"]["value"] == "none" and d["result"]["unit"] is None
        assert d["record_id"] == f"us.short_sale_price_test.{scope}.2007-07-06" and d["verification"] == "single-source"
        assert d["result"]["effective_to"] == "2011-02-28"
        assert resolve("short_sale_price_test", "2010-06-01", scope, "XNAS", min_verification="verified")["status"] == "UNVERIFIED"
        d = resolve("short_sale_price_test", "2011-02-28", scope, "XNAS", min_verification="verified")
        assert d["status"] == "DETERMINED" and d["result"]["value"]["trigger_decline_pct"] == 0.1
        assert d["result"]["effective_to"] is None and d["result"]["published_at"] == "2010-11-09"
        # before the 2007 regime: no record and no gap (before the coverage floor)
        d = resolve("short_sale_price_test", "2007-07-05", scope, "XNYS")
        assert d["status"] == "OUT_OF_COVERAGE" and d["known_gap_ids"] == []
        c = mr.coverage("XNYS", scope, ["short_sale_price_test"], US_FLOOR, US_END)
        assert c["status"] == "complete" and c["verification"] == "single-source"
        assert mr.coverage("XNAS", scope, ["short_sale_price_test"], "2011-02-28", US_END, strict=True)["status"] == "complete"
    # a short-sale restriction, not a daily price limit
    with pytest.raises(KeyError):
        mr.limit_price(10.0, "us_stock", "2012-06-01", "XNYS")


def test_us_fourth_batch_pattern_day_trader():
    from marina_rules.contract import resolve

    pdt = {"min_equity": 25000.0, "day_trades": 4, "window_business_days": 5}
    for scope in US_SCOPES:
        gid = {"us_stock": "G-US-0014", "us_etf": "G-US-0015"}[scope]
        for market in ("XNYS", "XNAS", "XNYS+XNAS"):
            for day in ("2001-09-28", "2010-01-04", "2010-12-02", "2015-03-02", "2026-06-03"):
                assert mr.rule_at("pattern_day_trader_min_equity", day, scope, market) == pdt, (scope, market, day)
            # from 2026-06-04 members switch to intraday margin one by one until 2027-10-20: a known gap
            for day in ("2026-06-04", "2026-11-03", "2027-10-19"):
                with pytest.raises(KeyError):
                    mr.rule_at("pattern_day_trader_min_equity", day, scope, market)
                d = resolve("pattern_day_trader_min_equity", day, scope, market)
                assert d["status"] == "OUT_OF_COVERAGE" and d["known_gap_ids"] == [gid], (scope, market, day)
        rec = mr.record_at("pattern_day_trader_min_equity", "2015-03-02", scope, "XNYS")
        assert (rec.id, rec.market, rec.unit, rec.verification, rec.effective_to, rec.published_at) == (
            f"us.pattern_day_trader_min_equity.{scope}.2001-09-28", "XNYS+XNAS", "USD", "single-source", "2026-06-04",
            "2001-03-27")
        assert "G-US-0014" in rec.notes and "G-US-0015" in rec.notes
        d = resolve("pattern_day_trader_min_equity", "2015-03-02", scope, "XNAS")
        assert d["status"] == "DETERMINED" and d["result"]["unit"] == "USD" and d["result"]["value"] == pdt
        assert resolve("pattern_day_trader_min_equity", "2015-03-02", scope, "XNYS",
                       min_verification="verified")["status"] == "UNVERIFIED"
        d = resolve("pattern_day_trader_min_equity", "2001-09-27", scope, "XNYS")
        assert d["status"] == "OUT_OF_COVERAGE" and d["known_gap_ids"] == []
        c = mr.coverage("XNYS", scope, ["pattern_day_trader_min_equity"], US_FLOOR, US_END)
        assert c["status"] == "partial" and c["known_gap_ids"] == [gid]
        assert c["gaps"] == [{"rule": "pattern_day_trader_min_equity", "from": "2026-06-04", "to": US_END,
                              "known_gap_ids": [gid], "known": c["gaps"][0]["known"]}]
        assert mr.coverage("XNAS", scope, ["pattern_day_trader_min_equity"], US_FLOOR, "2026-06-04")["status"] == "complete"
    # the removal (none) is not recorded: no record from 2026-06-04 in either scope
    assert not [r for r in _us() if r.rule == "pattern_day_trader_min_equity" and r.effective_from >= "2026-06-04"]


_SSPT_OK = {"trigger_decline_pct": 0.1, "reference": "prior_close", "restriction": "above_national_best_bid",
            "duration": "rest_of_day_and_next_day"}


@pytest.mark.parametrize("value", [
    "None", "unlimited", None, 0.1, [_SSPT_OK],
    {k: v for k, v in _SSPT_OK.items() if k != "duration"},                         # missing key
    {**_SSPT_OK, "extra": 1},                                                         # extra key
    {**_SSPT_OK, "trigger_decline_pct": 1.0},                                         # ratio >= 1
    {**_SSPT_OK, "trigger_decline_pct": 1.5},
    {**_SSPT_OK, "trigger_decline_pct": 0},                                           # ratio <= 0
    {**_SSPT_OK, "trigger_decline_pct": -0.1},
    {**_SSPT_OK, "trigger_decline_pct": "0.1"},
    {**_SSPT_OK, "trigger_decline_pct": True},
    {**_SSPT_OK, "trigger_decline_pct": float("nan")},
    {**_SSPT_OK, "reference": "last_sale"},                                           # unknown enums
    {**_SSPT_OK, "restriction": "uptick"},
    {**_SSPT_OK, "duration": "rest_of_day"},
    {**_SSPT_OK, "reference": None},
])
def test_short_sale_price_test_validation_rejects(value):
    with pytest.raises(ValueError):
        mr._check_short_sale_price_test(value, "test")


def test_short_sale_price_test_validation_accepts():
    mr._check_short_sale_price_test("none", "test")
    mr._check_short_sale_price_test(_SSPT_OK, "test")
    mr._check_short_sale_price_test({**_SSPT_OK, "trigger_decline_pct": 0.05}, "test")
    for r in mr.records():   # the records themselves passed the same check at load (US and Hong Kong shapes)
        if r.rule == "short_sale_price_test":
            mr._check_short_sale_price_test(r.value, r.id, r.market)


_PDT_OK = {"min_equity": 25000.0, "day_trades": 4, "window_business_days": 5}


@pytest.mark.parametrize("value", [
    "none", None, 25000.0, [_PDT_OK],
    {k: v for k, v in _PDT_OK.items() if k != "day_trades"},                          # missing key
    {**_PDT_OK, "extra": 1},                                                          # extra key
    {**_PDT_OK, "min_equity": 0},
    {**_PDT_OK, "min_equity": -25000.0},
    {**_PDT_OK, "min_equity": "25000"},
    {**_PDT_OK, "min_equity": float("inf")},
    {**_PDT_OK, "day_trades": 0},
    {**_PDT_OK, "day_trades": -4},
    {**_PDT_OK, "day_trades": 4.0},
    {**_PDT_OK, "day_trades": True},
    {**_PDT_OK, "window_business_days": 0},
    {**_PDT_OK, "window_business_days": 5.5},
])
def test_pattern_day_trader_validation_rejects(value):
    with pytest.raises(ValueError):
        mr._check_pattern_day_trader(value, "test")


def test_pattern_day_trader_validation_accepts():
    mr._check_pattern_day_trader(_PDT_OK, "test")
    mr._check_pattern_day_trader({"min_equity": 25000, "day_trades": 1, "window_business_days": 1}, "test")
    for r in mr.records():
        if r.rule == "pattern_day_trader_min_equity":
            mr._check_pattern_day_trader(r.value, r.id)


def _load_with(tmp_path, monkeypatch, record: dict, prefix: str = "us", market: str = "XNYS+XNAS"):
    """Load a one-record data directory (US by default) through records() (which caches; cleared before and after)."""
    import yaml as _yaml
    d = tmp_path / "data" / prefix
    d.mkdir(parents=True)
    (d / "equity.yaml").write_text(_yaml.safe_dump({"schema": 1.1, "market": market, "records": [record]}))
    monkeypatch.setattr(mr, "DATA_DIR", str(tmp_path / "data"))
    mr.records.cache_clear()
    try:
        return mr.records()
    finally:
        mr.records.cache_clear()


_SRC = {"url": "https://example.org/x", "content_sha256": "0" * 64, "quote": "q"}


@pytest.mark.parametrize("record,ok", [
    ({"rule": "pattern_day_trader_min_equity", "value": _PDT_OK, "unit": "USD"}, True),
    ({"rule": "pattern_day_trader_min_equity", "value": _PDT_OK}, False),                     # no unit
    ({"rule": "pattern_day_trader_min_equity", "value": {**_PDT_OK, "day_trades": 0}, "unit": "USD"}, False),
    ({"rule": "pattern_day_trader_min_equity", "value": "none", "unit": "USD"}, False),
    ({"rule": "short_sale_price_test", "value": "none"}, True),
    ({"rule": "short_sale_price_test", "value": _SSPT_OK}, True),
    ({"rule": "short_sale_price_test", "value": {**_SSPT_OK, "reference": "vwap"}}, False),
    ({"rule": "short_sale_price_test", "value": {**_SSPT_OK, "trigger_decline_pct": 1.0}}, False),
])
def test_us_fourth_batch_rules_validated_at_load(tmp_path, monkeypatch, record, ok):
    rec = {"id": "us.x.us_stock.2011-02-28", "scope": "us_stock", "effective_from": "2011-02-28",
           "verification": "single-source", "sources": [_SRC], **record}
    if ok:
        assert [r.value for r in _load_with(tmp_path, monkeypatch, rec)] == [record["value"]]
    else:
        with pytest.raises(ValueError):
            _load_with(tmp_path, monkeypatch, rec)


@pytest.mark.parametrize("record,ok", [
    ({"rule": "short_sale_price_test", "value": _HK_SSPT_OK}, True),
    ({"rule": "short_sale_price_test", "value": {"restriction": "exempt", "duration": "always"}}, True),
    ({"rule": "short_sale_price_test", "value": _SSPT_OK}, False),                            # US shape under XHKG
    ({"rule": "short_sale_price_test", "value": "none"}, False),
    ({"rule": "short_sale_price_test", "value": {**_HK_SSPT_OK, "restriction": "uptick"}}, False),
    ({"rule": "investor_compensation_levy_each_side", "value": 0}, True),
    ({"rule": "investor_compensation_levy_each_side", "value": 1.0}, False),
    ({"rule": "opening_auction_limit_pct", "value": 0.15}, True),
    ({"rule": "opening_auction_limit_pct", "value": 0}, False),
    ({"rule": "opening_auction_limit_pct", "value": 1}, False),
    ({"rule": "order_spread_limit", "value": _OSL_OK}, True),
    ({"rule": "order_spread_limit", "value": {**_OSL_OK, "wider_pct": None}}, True),
    ({"rule": "order_spread_limit", "value": {**_OSL_OK, "max_spreads": 0}}, False),
    ({"rule": "order_spread_limit", "value": {**_OSL_OK, "wider_pct": 1.0}}, False),
    ({"rule": "order_spread_limit", "value": {**_OSL_OK, "reference": "nominal"}}, False),
    ({"rule": "order_price_multiple_limit", "value": _OPM_OK}, True),
    ({"rule": "order_price_multiple_limit", "value": {**_OPM_OK, "max_multiple": 1}}, False),
    ({"rule": "order_price_multiple_limit", "value": {**_OPM_OK, "reference": "previous_close"}}, False),
])
def test_hk_third_batch_rules_validated_at_load(tmp_path, monkeypatch, record, ok):
    rec = {"id": "hk.x.hk_stock.2020-10-19", "scope": "hk_stock", "effective_from": "2020-10-19",
           "verification": "single-source", "sources": [_SRC], **record}
    if ok:
        assert [r.value for r in _load_with(tmp_path, monkeypatch, rec, "hk", "XHKG")] == [record["value"]]
    else:
        with pytest.raises(ValueError):
            _load_with(tmp_path, monkeypatch, rec, "hk", "XHKG")


def test_us_short_sale_price_test_refuses_the_hong_kong_shape_at_load(tmp_path, monkeypatch):
    rec = {"id": "us.x.us_stock.2011-02-28", "scope": "us_stock", "effective_from": "2011-02-28",
           "verification": "single-source", "sources": [_SRC], "rule": "short_sale_price_test", "value": _HK_SSPT_OK}
    with pytest.raises(ValueError):
        _load_with(tmp_path, monkeypatch, rec)


@pytest.mark.parametrize("record", [
    {"rule": "order_spread_limit", "value": _OSL_OK},
    {"rule": "order_price_multiple_limit", "value": _OPM_OK},
])
def test_hk_order_limit_rules_refused_outside_xhkg_at_load(tmp_path, monkeypatch, record):
    rec = {"id": "us.x.us_stock.2020-10-19", "scope": "us_stock", "effective_from": "2020-10-19",
           "verification": "single-source", "sources": [_SRC], **record}
    with pytest.raises(ValueError):
        _load_with(tmp_path, monkeypatch, rec, "us", "XNYS")


def test_limit_price_with_a_market_naming_several_exchanges():
    # one record spanning them, or the exchanges' own records agreeing: answered
    assert mr.limit_price(1.234, "etf", "2024-06-14", "XSHG+XSHE") == (1.357, 1.111)
    assert mr.limit_price(1.234, "main_board", "2024-06-14", "XSHG+XSHE") == (1.36, 1.11)
    # the exchanges' records differ: the caller must name one (it used to round at 0.01, right for Shenzhen only)
    with pytest.raises(mr.RuleConflict, match="differs by exchange"):
        mr.limit_price(1.234, "b_share", "2024-06-14", "XSHG+XSHE")
    assert mr.limit_price(1.234, "b_share", "2024-06-14", "XSHG") == (1.357, 1.111)
    assert mr.limit_price(1.234, "b_share", "2024-06-14", "XSHE") == (1.36, 1.11)
    with pytest.raises(KeyError):                               # no record at all on that date: still a missing rule
        mr.limit_price(1.234, "b_share", "2005-06-01", "XSHG+XSHE")


def test_czce_sunflower_oil_listed_2026_11_12():
    """SO appears in the daily settlement table on 2026-11-12. The listing and fee notices could not be fetched in a
    hashable form, so the records rest on the daily file alone, and what only a notice states is a declared gap."""
    from marina_rules.contract import resolve
    band = "price_limit_pct_of_prev_settlement"
    assert not mr.scopes("cn")["czce_so"]["requires"]
    for rule in ("trans_fee_rate", "close_today_fee_rate", band, "margin_ratio", "session_schedule", "min_holding_days"):
        d = resolve(rule, "2026-11-11", "czce_so", "XZCE")
        assert d["status"] == "OUT_OF_COVERAGE" and d["known_gap_ids"] == [], rule      # not listed yet: no record, no gap
    assert mr.rule_at("trans_fee_rate", "2026-11-12", "czce_so", "XZCE") == 0.0001
    assert mr.rule_at("close_today_fee_rate", "2026-11-18", "czce_so", "XZCE") == 0.0001   # not free on the same day
    assert mr.rule_at("min_holding_days", "2026-11-12", "czce_so", "XZCE") == 0
    # the table of day D carries the band of the next trading day: the listing day itself is a gap, 7% from 2026-11-13
    d = resolve(band, "2026-11-12", "czce_so", "XZCE")
    assert d["status"] == "OUT_OF_COVERAGE" and len(d["known_gap_ids"]) == 1
    assert mr.rule_at(band, "2026-11-13", "czce_so", "XZCE") == 0.07
    assert not [r for r in mr.records() if r.scope == "czce_so" and r.rule == band and r.value != 0.07]   # no 14% record
    for rule in ("margin_ratio", "session_schedule"):     # the daily 8% is not a ladder boundary; hours need the notice
        for day in ("2026-11-12", "2026-11-18"):
            d = resolve(rule, day, "czce_so", "XZCE")
            assert d["status"] == "OUT_OF_COVERAGE" and len(d["known_gap_ids"]) == 1, (rule, day)
    recs = [r for r in mr.records() if r.scope == "czce_so"]
    assert len(recs) == 4 and all(r.verification == "single-source" and r.published_at is None for r in recs)
    assert resolve("trans_fee_rate", "2026-11-13", "czce_so", "XZCE", None, "verified")["status"] == "UNVERIFIED"
    assert mr.rule_at("trans_fee_rate", "2026-11-13", "czce_so", "XZCE", contract="SO705") == 0.0001
    assert mr.parse_contract("SO705", "2026-11-12") == ("so", 2027, 5)


def test_limit_price_rounding_is_a_record_per_exchange():
    """SSE / SZSE round the band half up (their rules say so); BSE rounds toward the previous close (its rules make any
    order beyond the band invalid and say nothing about rounding). Before marina-rules-core 1.0.0 every market was
    rounded half up with no BSE record behind it."""
    assert mr.limit_price(12.86, "bse", "2024-06-14", "BJSE") == (16.71, 9.01)          # 16.718 / 9.002
    assert mr.limit_price(12.86, "bse", "2024-06-14") == (16.71, 9.01)                  # the scope says BSE
    assert mr.limit_price(10.00, "bse", "2024-06-14", "BJSE") == (13.0, 7.0)            # exact values stay exact
    assert mr.limit_price(12.86, "st_bse", "2026-09-01", "BJSE") == (16.71, 9.01)
    assert mr.limit_price(12.86, "main_board", "2024-06-14", "XSHG") == (14.15, 11.57)  # 14.146 / 11.574: half up
    rec = mr.record_at("limit_price_rounding", "2024-06-14", "bse_stock", "BJSE")
    assert rec.value == "toward_prev_close" and rec.verification == "single-source"
    assert mr.record_at("limit_price_rounding", "2024-06-14", "stock", "XSHG").value == "half_up_2dp"
    with pytest.raises(KeyError, match="limit_price_rounding"):
        mr._rounding_mode("bse", "2021-11-12", "BJSE", False, None)                     # before the BSE opened
