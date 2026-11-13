"""Coverage step 3 (2026.10.26.7): explicit no-floor records, BSE, convertibles, REITs, 2013 fund switches, ChiNext split."""
import pytest

import marina_rules as mr
from marina_rules.contract import resolve


# --- limit_price_min_tick: false records must not change limit_price() --------------------------------------------
@pytest.mark.parametrize("mk,day", [("XSHE", "2006-07-03"), ("XSHE", "2011-02-25"), ("XSHG", "2006-07-03"),
                                    ("XSHG", "2015-06-01"), ("XSHG", "2023-04-07"), ("BJSE", "2024-06-14")])
def test_false_floor_records_exist(mk, day):
    fam = "bse_stock" if mk == "BJSE" else "stock"   # BSE-only records live under family scope bse_stock
    assert mr.rule_at("limit_price_min_tick", day, fam, mk) is False
    assert mr.min_tick_band("main_board", day, mk) is False


def test_limit_price_with_false_floor_is_rounding_only():
    # same answers as when no record existed (rounding only, limit may equal preclose)
    assert mr.limit_price(0.04, "main_board", "2010-06-01", "XSHG") == (0.04, 0.04)
    assert mr.limit_price(0.04, "main_board", "2008-06-02", "XSHE") == (0.04, 0.04)
    assert mr.limit_price(0.04, "st_main", "2023-04-07", "XSHG") == (0.04, 0.04)
    assert mr.limit_price(0.01, "bse", "2024-06-14", "BJSE") == (0.01, 0.01)
    # the boundary still flips on the floor's first day
    assert mr.limit_price(0.04, "main_board", "2011-02-28", "XSHE") == (0.05, 0.03)
    assert mr.limit_price(0.04, "main_board", "2023-04-10", "XSHG") == (0.05, 0.03)
    # board-specific SSE delisting cent band still wins over the stock-level false
    assert mr.limit_price(0.04, "delisting", "2015-06-01", "XSHG") == (0.05, 0.03)
    with pytest.raises(ValueError):   # floor matters and exchanges differ: market still required
        mr.limit_price(0.04, "main_board", "2015-06-01")


def test_limit_price_without_market_uses_agreed_tick_only():
    # XSHG+XSHE and BJSE stock ticks are all 0.01: an ordinary price needs no market
    assert mr.limit_price(10.0, "main_board", "2024-06-14") == (11.0, 9.0)
    with pytest.raises(mr.RuleConflict):   # convertible ticks differed by exchange before 2022-08-01
        mr.tick_size("convertible", "2015-06-01")


def test_g0006_closed():
    assert mr.gaps_for("XSHG", "stock", "limit_price_min_tick", "2006-07-01", "2023-04-10") == []


# --- BSE ----------------------------------------------------------------------------------------------------------
def test_bse_tick_holding_session():
    assert mr.tick_size("bse", "2021-11-15", "BJSE") == 0.01
    assert mr.rule_at("min_holding_days", "2024-06-14", "bse_stock", "BJSE") == 1
    s = mr.rule_at("session_schedule", "2024-06-14", "bse_stock", "BJSE")
    assert s["close_call"] == ["14:57", "15:00"] and s["continuous"] == [["09:30", "11:30"], ["13:00", "14:57"]]
    with pytest.raises(KeyError):
        mr.rule_at("min_holding_days", "2021-11-12", "bse_stock", "BJSE")


# --- BSE family scope bse_stock (2026.10.26.7): BSE-only tick/T+1/session/floor records ---------------------------
D = "2024-06-14"
BSE_FOUR = {"tick_size": 0.01, "min_holding_days": 1, "limit_price_min_tick": False}


@pytest.mark.parametrize("rule,value", [("tick_size", 0.01), ("min_holding_days", 1)])
def test_marketless_stock_tick_and_holding_answer(rule, value):
    # only the XSHG+XSHE record is under stock now: no RuleConflict without a market
    assert mr.rule_at(rule, D, "stock") == value
    assert mr.record_at(rule, D, "stock").market == "XSHG+XSHE"
    assert mr.tick_size("stock", D) == 0.01 and mr.tick_size("main_board", D) == 0.01


def test_marketless_session_and_floor_still_conflict_where_sse_szse_differ():
    with pytest.raises(mr.RuleConflict):
        mr.rule_at("session_schedule", D, "stock")
    with pytest.raises(mr.RuleConflict):
        mr.rule_at("limit_price_min_tick", "2023-04-07", "stock")
    # from 2023-04-10 SSE and SZSE floors are both true but are two records: rule_at has no agreement logic for
    # this rule, so a market-less lookup still conflicts (min_tick_band() requires a market anyway)
    with pytest.raises(mr.RuleConflict):
        mr.rule_at("limit_price_min_tick", D, "stock")


@pytest.mark.parametrize("rule", ["tick_size", "min_holding_days", "session_schedule", "limit_price_min_tick"])
def test_bse_stock_answers_and_stock_bjse_is_keyerror(rule):
    rec = mr.record_at(rule, D, "bse_stock", "BJSE")
    assert rec.market == "BJSE" and rec.id.endswith("bse.2021-11-15")
    if rule in BSE_FOUR:
        assert rec.value == BSE_FOUR[rule]
    assert mr.record_at(rule, D, "bse_stock").id == rec.id   # the only record under bse_stock
    with pytest.raises(KeyError):
        mr.rule_at(rule, D, "stock", "BJSE")


@pytest.mark.parametrize("scope", ["bse", "st_bse", "ipo_day1_bse", "delisting_bse", "delisting_day1_bse", "bse_stock"])
def test_bse_boards_map_to_bse_stock_family(scope):
    assert mr.tick_family(scope) == "bse_stock" and mr.lookup_scope("tick_size", scope) == "bse_stock"
    assert mr.tick_size(scope, D, "BJSE") == 0.01
    assert mr.tick_size(scope, D) == 0.01


def test_family_stock_with_market_bjse_maps_to_bse_stock():
    assert mr.lookup_scope("tick_size", "stock", "BJSE") == "bse_stock"
    assert mr.lookup_scope("tick_size", "main_board", "XSHG") == "stock"
    assert mr.tick_size("stock", D, "BJSE") == 0.01


def test_bse_limit_prices_and_floor_unchanged():
    assert mr.limit_price(10.0, "bse", D, "BJSE") == (13.0, 7.0)       # 10 × 1.3 / 10 × 0.7
    assert mr.limit_price(10.0, "st_bse", D, "BJSE") == (13.0, 7.0)
    assert mr.limit_price(10.0, "bse", D) == (13.0, 7.0)
    assert mr.limit_price(0.01, "bse", D, "BJSE") == (0.01, 0.01)      # no one-tick floor at BSE
    assert mr.limit_price(0.01, "st_bse", D, "BJSE") == (0.01, 0.01)
    assert mr.min_tick_band("bse", D, "BJSE") is False
    assert mr.min_tick_band("main_board", D, "XSHG") is True


@pytest.mark.parametrize("scope,ctx", [("bse", {"board": "bse", "st_status": False, "listing_day_index": 100}),
                                       ("st_bse", {"board": "bse", "st_status": True})])
def test_bse_resolve_unchanged(scope, ctx):
    t = resolve("tick_size", D, scope, "BJSE", ctx)
    assert (t["status"], t["record_id"], t["result"]["value"]) == ("DETERMINED", "cn.tick.bse.2021-11-15", 0.01)
    p = resolve("price_limit_pct", D, scope, "BJSE", ctx)
    assert p["status"] == "DETERMINED" and p["result"]["value"] == 0.3
    s = resolve("session_schedule", D, "bse_stock", "BJSE", {})
    assert s["record_id"] == "cn.session.stock.bse.2021-11-15"


def test_bse_coverage_under_family_scope():
    c = mr.coverage("BJSE", "bse_stock", ["tick_size", "min_holding_days", "session_schedule", "limit_price_min_tick"],
                    "2021-11-15", "2026-10-01")
    assert c["status"] == "complete" and not c["conflicts"]
    c = mr.coverage("BJSE", "bse", ["tick_size"], "2021-11-15", "2026-10-01")
    assert c["status"] == "complete" and c["records"] == ["cn.tick.bse.2021-11-15"]


# --- convertibles -------------------------------------------------------------------------------------------------
def test_convertible_holding_session_tick():
    for mk in ("XSHG", "XSHE"):
        for d in ("2006-07-03", "2015-06-01", "2022-08-01", "2025-06-16"):
            assert mr.rule_at("min_holding_days", d, "convertible", mk) == 0
    assert mr.tick_size("convertible", "2011-02-25", "XSHE") == 0.01
    assert mr.tick_size("convertible", "2011-02-28", "XSHE") == 0.001
    assert mr.tick_size("convertible", "2022-07-29", "XSHG") == 0.01
    assert mr.tick_size("convertible", "2022-08-01", "XSHG") == 0.001
    assert mr.rule_at("session_schedule", "2015-06-01", "convertible", "XSHG")["close_call"] is None
    assert mr.rule_at("session_schedule", "2026-07-06", "convertible", "XSHG")["close_call"] is None   # CB rules, not 2026 trading rules
    assert mr.rule_at("session_schedule", "2015-06-01", "convertible", "XSHE")["close_call"] == ["14:57", "15:00"]
    # session/tick need no listing_day_index — but they are recorded under scope convertible only
    assert resolve("session_schedule", "2015-06-01", "convertible", "XSHE")["status"] == "DETERMINED"


def test_sse_convertible_commission_window():
    assert mr.rule_at("commission_cap", "2015-06-01", "convertible", "XSHG") == 0.0002
    assert mr.rule_at("commission_min_per_order_cny", "2015-06-01", "convertible", "XSHG") == 1
    # step 4: SSE fee tables / 2007-10-12 notice before 2010-12-01; SZSE fee table 2006-12-30..2014-08-25
    assert mr.rule_at("commission_cap", "2007-10-11", "convertible", "XSHG") == 0.001
    assert mr.rule_at("commission_min_per_order_cny", "2007-10-11", "convertible", "XSHG") == 5
    assert mr.rule_at("commission_cap", "2010-11-30", "convertible", "XSHG") == 0.0002
    assert mr.rule_at("commission_min_per_order_cny", "2010-11-30", "convertible", "XSHG") == 1
    assert mr.rule_at("commission_cap", "2010-06-01", "convertible", "XSHE") == 0.001
    with pytest.raises(KeyError):
        mr.rule_at("commission_cap", "2021-12-31", "convertible", "XSHG")
    for d in ("2006-12-29", "2014-08-25"):
        with pytest.raises(KeyError):
            mr.rule_at("commission_cap", d, "convertible", "XSHE")
    with pytest.raises(KeyError):
        mr.rule_at("commission_min_per_order_cny", "2010-06-01", "convertible", "XSHE")


# --- REITs --------------------------------------------------------------------------------------------------------
def test_reits_holding_and_session():
    assert mr.rule_at("min_holding_days", "2022-06-01", "reits", "XSHG+XSHE") == 1
    assert mr.rule_at("session_schedule", "2024-06-14", "reits", "XSHG")["close_call"] is None
    assert mr.rule_at("session_schedule", "2026-07-06", "reits", "XSHG")["close_call"] == ["14:57", "15:00"]
    assert mr.rule_at("session_schedule", "2024-06-14", "reits", "XSHE")["close_call"] == ["14:57", "15:00"]


# --- ChiNext delisting split (深证上〔2020〕620号) -------------------------------------------------------------------
def test_chinext_delisting_split_by_entry_date():
    pre = {"board": "chinext", "delisting_day_index": 3, "delisting_entry_before_2020_08_24": True}
    post = {"board": "chinext", "delisting_day_index": 1, "delisting_entry_before_2020_08_24": False}
    assert resolve("price_limit_pct", "2020-09-15", "delisting_chinext_pre0824", "XSHE", pre)["result"]["value"] == 0.1
    assert resolve("price_limit_pct", "2020-09-15", "delisting_chinext_post0824", "XSHE", post)["result"]["value"] == 0.2
    # the flag must be supplied, and must agree with the scope
    d = resolve("price_limit_pct", "2020-09-15", "delisting_chinext_post0824", "XSHE", {"board": "chinext", "delisting_day_index": 1})
    assert d["status"] == "MISSING_CONTEXT" and d["missing_context"] == ["delisting_entry_before_2020_08_24"]
    assert resolve("price_limit_pct", "2020-09-15", "delisting_chinext_post0824", "XSHE", pre)["status"] == "MISSING_CONTEXT"
    # pre-0824 entrants are past their first day by construction
    assert resolve("price_limit_pct", "2020-09-15", "delisting_chinext_pre0824", "XSHE", {**pre, "delisting_day_index": 1})["status"] == "MISSING_CONTEXT"
    # delisting_day1 is main board only in this window
    assert resolve("price_limit_pct", "2020-09-15", "delisting_day1", "XSHE", {"board": "main_board", "delisting_day_index": 1})["result"]["value"] == 0.1
    assert resolve("price_limit_pct", "2020-09-15", "delisting_day1", "XSHE", {"board": "chinext", "delisting_day_index": 1})["status"] == "MISSING_CONTEXT"
    assert resolve("price_limit_pct", "2020-08-21", "delisting_day1", "XSHE", {"board": "chinext", "delisting_day_index": 1})["result"]["value"] == 0.1
    # the context-free scope still has no record there (G-0016 points to the split scopes)
    assert resolve("price_limit_pct", "2020-09-01", "delisting_chinext", "XSHE", {"board": "chinext", "delisting_day_index": 2})["known_gap_ids"] == ["G-0016"]
    assert mr.gaps_for("XSHE", "delisting_day1", "price_limit_pct", "2020-08-24", "2020-12-31") == []
