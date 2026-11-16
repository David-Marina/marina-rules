"""What a ``rules-verified`` stamp may rest on: never on a caller's own price grid, on a scope the row's own context
contradicts, or on a cell that is present but unreadable. All three passed, stamped, in 2026.11.13 and 2026.11.16."""
import math

import pytest

from marina_rules.check import MAX_DECIMALS, check_rows
from marina_rules.contract import resolve

BASE = dict(date="2024-06-14", code="600001", side="sell", price="10.00", prev_close="10.00",
            scope="main_board", market="XSHG", fee="5.1", turnover="10000")


def run(_opts=None, **cells):
    return check_rows([dict(BASE, **cells)], strict=True, per_row=True, **(_opts or {}))


def checks(out):
    return [f["check"] for f in out["findings"]]


def test_base_row_is_stamped_and_says_what_was_checked():
    out = run()
    assert out["rules_verified"] and out["stamp"] and not out["relaxed"] and out["findings"] == []
    assert out["decimals_override"] == 0
    assert out["fee_check"]["rows_checked"] == 1 and out["fee_check"]["rows_not_checked"] == 0
    assert out["row_status"][0].get("fee_checked") is True


# --- 1. a ``decimals`` cell that is not the recorded tick ----------------------------------------------------

def test_off_tick_price_is_a_finding_without_decimals():
    out = run(price="10.001")
    assert checks(out) == ["PRICE_OFF_TICK"] and out["stamp"] is None


@pytest.mark.parametrize("dec", ["3", "1", "0", "4"])
def test_decimals_other_than_the_recorded_tick_withholds_the_stamp(dec):
    price = {"3": "10.001", "1": "10.0", "0": "10", "4": "10.0001"}[dec]
    out = run(price=price, decimals=dec)
    assert out["findings"] == [] and out["clean"]            # still checked, on the caller's grid
    assert out["relaxed"] and not out["rules_verified"] and out["stamp"] is None
    assert out["decimals_override"] == 1 and out["row_status"][0]["decimals_override"] is True
    assert "decimals" in out["stamp_withheld"]


def test_decimals_equal_to_the_recorded_tick_changes_nothing_but_the_hash():
    plain, same = run(), run(decimals="2")
    assert same["rules_verified"] and same["stamp"] and not same["relaxed"] and same["decimals_override"] == 0
    assert same["stamp"] != plain["stamp"]                  # the stamp commits to the cell as written
    out = run(scope="etf", price="10.001", decimals="3")   # ETF tick is 0.001: the override IS the exchange grid
    assert out["rules_verified"] and out["stamp"] and out["decimals_override"] == 0


def test_decimals_cannot_stand_in_for_a_missing_market():
    # B-share tick differs by exchange; without a market the recorded tick is unknown, so decimals is the caller's
    out = run(scope="b_share", market="", decimals="3", fee="", turnover="")
    assert out["relaxed"] and out["stamp"] is None and out["decimals_override"] == 1
    out = run(scope="b_share", market="XSHG", decimals="3", fee="", turnover="")
    assert out["rules_verified"] and out["decimals_override"] == 0


def test_decimals_where_no_tick_is_recorded():
    # before 2006-07-01 no tick is recorded; the band is rounded to 0.01 (G-0005), so decimals=2 changes nothing
    out = run(date="2005-06-01", decimals="2", fee="", turnover="")
    assert out["decimals_override"] == 0 and not out["relaxed"]
    out = run(date="2005-06-01", price="10.001", decimals="3", fee="", turnover="")
    assert out["decimals_override"] == 1 and out["relaxed"] and out["stamp"] is None


@pytest.mark.parametrize("dec", ["400", "-1", "2.5", "abc", str(MAX_DECIMALS + 1), "1e2"])
def test_unusable_decimals_is_an_invalid_row_not_a_crash(dec):
    out = run(decimals=dec)
    assert checks(out) == ["ROW_INVALID"] and "decimals" in out["findings"][0]["detail"]
    assert out["stamp"] is None


def test_one_overriding_row_withholds_the_stamp_of_the_whole_log():
    rows = [dict(BASE), dict(BASE, code="600002", price="10.001", decimals="3")]
    out = check_rows(rows, strict=True)
    assert out["findings"] == [] and out["decimals_override"] == 1 and out["stamp"] is None and out["relaxed"]
    assert check_rows(rows[:1], strict=True)["stamp"]


# --- 2. an explicit scope the row's own context contradicts --------------------------------------------------

ST_CTX = dict(price="10.90", board="main_board", st_status="true", listing_day_index="500")


def test_scope_cell_against_st_cell_is_refused_as_resolve_refuses_it():
    out = run(**ST_CTX)
    assert checks(out) == ["SCOPE_CONTEXT_CONFLICT"] and out["stamp"] is None and not out["rules_verified"]
    assert "st_status" in out["findings"][0]["detail"]
    d = resolve("price_limit_pct", "2024-06-14", "main_board", "XSHG",
                {"board": "main_board", "st_status": True, "listing_day_index": 500})
    assert d["status"] == "MISSING_CONTEXT" and [c["key"] for c in d["context_conflicts"]] == ["st_status"]


def test_the_same_row_with_the_right_scope_is_checked_against_the_st_band():
    out = run(scope="st_main", **ST_CTX)                     # 10.90 is outside the 5% band
    assert "PRICE_OUTSIDE_BAND" in checks(out)
    out = run(scope="", **ST_CTX)                            # scope left to the context: same answer
    assert "PRICE_OUTSIDE_BAND" in checks(out) and out["row_status"][0]["scope"] == "st_main"


def test_st_alias_and_python_values():
    assert checks(run(st="1")) == ["SCOPE_CONTEXT_CONFLICT"]
    assert checks(check_rows([dict(BASE, st_status=True)], strict=True)) == ["SCOPE_CONTEXT_CONFLICT"]


def test_board_and_listing_window_conflicts():
    assert checks(run(scope="chinext", market="XSHE", board="main_board", fee="", turnover="")) == ["SCOPE_CONTEXT_CONFLICT"]
    assert checks(run(listing_day_index="1")) == ["SCOPE_CONTEXT_CONFLICT"]            # day 1 is not main_board
    # a listing date years back puts the row past every listing window: it cannot be an IPO-window fill
    out = run(scope="ipo_first5_main", list_date="2001-01-05", fee="", turnover="")
    assert checks(out) == ["SCOPE_CONTEXT_CONFLICT"] and "listing_day_index" in out["findings"][0]["detail"]


def test_context_that_agrees_or_cannot_decide_leaves_the_row_alone():
    plain = run()
    agree = run(board="main_board", st_status="false", listing_day_index="500")
    assert agree["rules_verified"] and agree["stamp"] == plain["stamp"]    # context cells are not part of the hash
    recent = run(list_date="2024-06-01")     # 13 days: the trading-day index is unknown, nothing to contradict
    assert recent["rules_verified"]
    only_some = run(listing_day_index="500")                               # absent keys are not demanded here
    assert only_some["rules_verified"]


def test_unreadable_context_cell_and_unknown_scope():
    out = run(st_status="maybe")
    assert checks(out) == ["ROW_INVALID"] and "st_status" in out["findings"][0]["detail"]
    out = run(scope="no_such_scope", st_status="true")
    assert checks(out) and "SCOPE_CONTEXT_CONFLICT" not in checks(out) and out["stamp"] is None


# --- 3. a fee or turnover cell that is present but not a number ----------------------------------------------

def test_zero_fee_is_below_the_statutory_floor():
    assert checks(run(fee="0")) == ["FEE_BELOW_STATUTORY"]


@pytest.mark.parametrize("cells", [dict(fee="nan"), dict(fee="inf"), dict(fee="-inf"), dict(fee="garbage"),
                                   dict(fee="0", turnover="nan"), dict(turnover="inf"), dict(turnover="abc"),
                                   dict(turnover="-10000"), dict(fee=math.nan), dict(turnover=math.inf)])
def test_unreadable_fee_or_turnover_is_an_invalid_row(cells):
    out = run(**cells)
    assert checks(out) == ["ROW_INVALID"] and out["stamp"] is None and not out["rules_verified"]
    name = "turnover" if "turnover" in cells and cells.get("fee") in (None, "0") else "fee"
    assert name in out["findings"][0]["detail"]


@pytest.mark.parametrize("cells", [dict(fee=""), dict(turnover=""), dict(fee="", turnover=""), dict(fee=None)])
def test_absent_fee_or_turnover_is_reported_as_not_checked(cells):
    out = run(**cells)
    assert out["rules_verified"] and out["stamp"]                # the stamp still commits to the empty cells
    assert out["fee_check"]["rows_checked"] == 0 and out["fee_check"]["rows_not_checked"] == 1
    assert "fee_checked" not in out["row_status"][0]
    assert "says nothing about fees" in out["fee_check"]["note"]


def test_negative_fee_is_a_fee_finding():
    assert checks(run(fee="-1")) == ["FEE_BELOW_STATUTORY"]


@pytest.mark.parametrize("cells", [dict(price="0"), dict(price="-10"), dict(prev_close="0"), dict(prev_close="-10"),
                                   dict(price="0", prev_close="0")])
def test_non_positive_prices_are_invalid(cells):
    out = run(**cells)
    assert checks(out) == ["ROW_INVALID"] and out["stamp"] is None


def test_invalid_row_message_keeps_its_old_opening():
    out = run(price="nan")
    assert out["findings"][0]["detail"].startswith(
        "need date, code, side (buy|sell), and finite numeric price and prev_close")
