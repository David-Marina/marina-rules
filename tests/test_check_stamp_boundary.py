"""What a ``rules-verified`` stamp may rest on: never on a caller's own price grid, on a scope the row's own context
contradicts, or on a cell that is present but unreadable. All three passed, stamped, in 2026.11.13 and 2026.11.16."""
import json
import math

import pytest

from marina_rules import adapt
from marina_rules.check import MAX_DECIMALS, check_rows, main as check_main
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


FUND_2005 = dict(date="2005-06-01", code="510050", scope="etf", market="XSHG", side="buy", price="1.234",
                 prev_close="1.200", fee="", turnover="")


@pytest.mark.parametrize("cells", [{}, dict(scope="b_share", code="900901"),
                                   dict(scope="st_b_share", code="200002", market="XSHE", st_status="true")])
@pytest.mark.parametrize("strict", [False, True])
def test_no_tick_for_a_fund_or_b_share_is_a_missing_rule_not_a_0_01_grid(cells, strict):
    # the band is recorded from 1996 / 1998, the tick only from 2006-07-01: nothing to round the limits at
    out = check_rows([dict(FUND_2005, **cells)], strict=strict)
    assert checks(out) == ["RULE_MISSING"] and "tick_size" in out["findings"][0]["detail"]
    assert not out["rules_verified"] and out["stamp"] is None and out["tick_check"]["rows_checked"] == 0


def test_decimals_for_a_fund_without_a_tick_record_is_the_callers_grid():
    out = run(**dict(FUND_2005, decimals="3"))
    assert checks(out) == [] and out["decimals_override"] == 1 and out["relaxed"] and out["stamp"] is None
    out = run(**dict(FUND_2005, decimals="2"))      # 0.01 is not the dataset's grid for a fund either
    assert checks(out) == ["PRICE_OFF_TICK"] and out["decimals_override"] == 1 and out["stamp"] is None


def test_a_fund_from_its_first_tick_record_is_checked_as_before():
    out = run(**dict(FUND_2005, date="2006-07-03"))
    assert checks(out) == [] and out["rules_verified"] and out["tick_check"]["rows_checked"] == 1


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
    # a code that names no board: the board cell is all the row says, and it is not the scope's
    assert checks(run(code="X1", scope="chinext", market="XSHE", board="main_board", fee="", turnover="")) == ["SCOPE_CONTEXT_CONFLICT"]
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


# --- second round: what an independent review of the three fixes still got stamped ---------------------------------

def invalid(out, *words):
    d = out["findings"][0]["detail"] if out["findings"] else ""
    return checks(out) == ["ROW_INVALID"] and out["stamp"] is None and all(w in d for w in words)


def test_two_columns_that_give_one_context_key_two_values():
    assert invalid(run(st="true", st_status="false", price="10.95"), "st", "st_status", "two values")
    assert invalid(run(st_status="false", st="true"), "two values")
    assert invalid(check_rows([dict(BASE, scope="", st="true", st_status="false")], strict=True), "two values")
    assert run(st="0", st_status="false")["rules_verified"]            # two spellings of one value agree


def test_context_keys_of_the_fund_scopes_are_compared_too():
    etf = dict(code="510300", scope="etf_20pct", price="11.900", prev_close="10.000", fee="", turnover="")
    out = run(**etf, fund_constituents="mixed")
    assert checks(out) == ["SCOPE_CONTEXT_CONFLICT"] and "fund_constituents" in out["findings"][0]["detail"]
    d = resolve("price_limit_pct", "2024-06-14", "etf_20pct", "XSHG", {"fund_constituents": "mixed"})
    assert d["status"] == "MISSING_CONTEXT" and [c["key"] for c in d["context_conflicts"]] == ["fund_constituents"]
    assert run(**etf, fund_constituents="all_20pct_band")["rules_verified"]


def test_the_code_itself_is_compared_with_the_scope_and_the_market():
    out = run(code="300750", scope="ipo_first5_main", market="XSHE", price="30.00", fee="", turnover="")
    assert checks(out) == ["SCOPE_CONTEXT_CONFLICT"] and "from code 300750" in out["findings"][0]["detail"]
    assert invalid(run(market="XSHE"), "market", "contradicts code")                 # 600001 is an SSE code
    assert invalid(run(board="chinext", scope=""), "board", "contradicts code")
    assert invalid(run(code="300001", scope="chinext", market="XSHE", board="main_board"), "board")
    assert run(code="600001.SH")["rules_verified"] and run(market="XSHG+XSHE")["rules_verified"]
    b = dict(code="200002", scope="b_share", price="4.565", prev_close="4.500", fee="", turnover="")
    assert invalid(run(**b, market="XSHG"), "B-share")                              # an SZSE B share labelled SSE
    assert checks(run(**b, market="XSHE")) == ["PRICE_OFF_TICK"]


@pytest.mark.parametrize("ld,word", [("garbage", "not a date"), ("2024-13-45", "not a date"), ("99999999", "not a date"),
                                     ("2025-01-01", "before list_date")])
def test_a_list_date_that_cannot_be_read_or_is_after_the_trade(ld, word):
    assert invalid(run(list_date=ld), "list_date", word)
    assert invalid(check_rows([dict(BASE, scope="", st="false", list_date=ld)], strict=True), word)


def test_a_trade_on_its_list_date_is_listing_day_one():
    out = run(list_date=BASE["date"])
    assert checks(out) == ["SCOPE_CONTEXT_CONFLICT"] and "from list_date" in out["findings"][0]["detail"]
    derived = check_rows([dict(BASE, scope="", st="false", list_date=BASE["date"], issue_regime="registration",
                               price="30.00", fee="", turnover="")], strict=True, per_row=True)
    assert derived["row_status"][0]["scope"] == "ipo_first5_main" and derived["rules_verified"]


def test_a_missing_code_and_a_date_with_a_tail_are_invalid():
    assert invalid(run(code=""), "code is missing")
    assert invalid(run(date="2024-06-14XYZ"), "after the day")
    assert run(date="2024-06-14 09:31:00")["stamp"] == run(date="2024-06-14T09:31")["stamp"] == run()["stamp"]


def test_rows_of_one_code_on_one_day_must_agree():
    two = lambda **second: check_rows([dict(BASE), dict(BASE, **second)], strict=True)
    assert two()["rules_verified"] and two(price="10.50")["rules_verified"]
    out = two(prev_close="10.50", price="10.50")
    assert checks(out) == ["ROWS_DISAGREE"] and out["findings"][0]["row"] == 2 and out["stamp"] is None
    assert "prev_close" in out["findings"][0]["detail"] and "row 1" in out["findings"][0]["detail"]
    assert checks(two(scope="st_main")) == ["ROWS_DISAGREE"]
    assert checks(two(market="")) == ["ROWS_DISAGREE"]
    assert two(prev_close="10.0")["rules_verified"]                    # another spelling of the same number
    assert two(date="2024-06-17", prev_close="10.50", price="10.50")["rules_verified"]   # another day


def test_tick_check_says_which_rows_rest_on_a_recorded_tick():
    out = run()
    assert out["tick_check"]["rows_checked"] == 1 and out["tick_check"]["rows_not_checked"] == 0
    assert "tick_not_checked" not in out["row_status"][0]
    # SZSE convertibles 2011-02-28 … 2012-12-10: the tick record is unverified, so a strict run does not use it
    cb = dict(date="2012-01-05", code="128001", scope="convertible", market="XSHE", price="110.1234",
              prev_close="105.000", fee="", turnover="")
    strict = run(**cb)
    assert strict["rules_verified"] and strict["tick_check"] == dict(strict["tick_check"], rows_checked=0, rows_not_checked=1)
    assert strict["row_status"][0]["tick_not_checked"] is True
    assert checks(check_rows([dict(BASE, **cb)], strict=False)) == ["PRICE_OFF_TICK"]
    assert run({"tick": False})["tick_check"]["rows_not_checked"] == 1
    assert run(price="10.001", decimals="3")["tick_check"]["rows_not_checked"] == 1      # the caller's grid


def test_rows_refused_before_the_checks_are_in_no_count_and_not_tracked():
    out = check_rows([dict(BASE), dict(BASE, code="600002", fee="nan"), dict(BASE, code="600003", st="true")],
                     strict=True)
    assert out["counts"] == {"ROW_INVALID": 1, "SCOPE_CONTEXT_CONFLICT": 1}
    for k in ("fee_check", "tick_check"):
        assert out[k]["rows_checked"] == 1 and out[k]["rows_not_checked"] == 0
    one = check_rows([dict(BASE)], strict=True)["tracking"]
    assert {k: out["tracking"][k] for k in ("rows_beyond_tracked_through", "rows_untracked")} == \
           {k: one[k] for k in ("rows_beyond_tracked_through", "rows_untracked")}


def test_a_fee_whose_floor_is_not_recorded_is_not_counted_as_checked():
    out = run(date="1995-06-14", fee="0", turnover="10000")
    assert "RULE_MISSING" in checks(out) and out["fee_check"]["rows_checked"] == 0


def test_b_share_without_a_market_is_a_finding_not_an_exception():
    out = run(code="900901", scope="b_share", market="", fee="", turnover="")
    assert checks(out) == ["MARKET_REQUIRED"] and out["stamp"] is None
    assert checks(run({"tick": False}, code="900901", scope="b_share", market="", fee="", turnover="")) == ["MARKET_REQUIRED"]


def test_columns_the_checker_does_not_read_are_listed():
    out = check_rows([dict(BASE, ST="true", is_st="1", Fee="0", note="x", st="false", fund_type="")], strict=True)
    assert out["columns_not_read"] == ["Fee", "ST", "is_st", "note"] and out["rules_verified"]
    assert run()["columns_not_read"] == []


def test_stamps_of_logs_these_cases_do_not_touch_are_the_ones_2026_11_16_issued():
    # recorded from the released 2026.11.16 package; the canonical form did not change
    assert run()["stamp"].split(":")[1] == GOLDEN_BASE


GOLDEN_BASE = "edd0c1afa9f77e9e69e4c5295041e256"


# --- the command line and the adapter reach the same checks --------------------------------------------------

HEAD = "date,code,side,price,prev_close,scope,market,fee,turnover\n"
ROW = "2024-06-14,600001,sell,10.00,10.00,main_board,XSHG,%s,10000\n"


def cli(tmp_path, capsys, text, *opts):
    f = tmp_path / "fills.csv"
    f.write_text(text, encoding="utf-8")
    code = check_main([str(f), "--strict", *opts])
    out = capsys.readouterr()
    return code, (json.loads(out.out) if out.out else None), out.err


def test_command_line_refuses_the_same_rows(tmp_path, capsys):
    code, out, _ = cli(tmp_path, capsys, HEAD + ROW % "5.1")
    assert code == 0 and out["stamp"].split(":")[1] == GOLDEN_BASE
    code, out, _ = cli(tmp_path, capsys, HEAD + ROW % "nan")
    assert code == 1 and out["counts"] == {"ROW_INVALID": 1} and out["stamp"] is None
    code, out, _ = cli(tmp_path, capsys, HEAD.replace("turnover", "turnover,st") + (ROW % "5.1").replace("\n", ",true\n"))
    assert code == 1 and out["counts"] == {"SCOPE_CONTEXT_CONFLICT": 1}
    code, out, _ = cli(tmp_path, capsys, HEAD.replace("turnover", "turnover,decimals") +
                       (ROW % "5.1").replace("10.00,10.00", "10.001,10.00").replace("\n", ",3\n"))
    assert code == 0 and out["relaxed"] and out["stamp"] is None and out["decimals_override"] == 1


def test_command_line_refuses_a_header_that_names_a_column_twice(tmp_path, capsys):
    # the second, empty fee would replace the first: the log would be read as giving no fee at all
    code, out, err = cli(tmp_path, capsys, HEAD.replace("turnover", "turnover,fee") + (ROW % "0").replace("\n", ",\n"))
    assert code == 2 and out is None and "more than once (fee)" in err


@pytest.mark.parametrize("cell,finding", [("nan", "ROW_INVALID"), ("abc", "ROW_INVALID"), ("0", "FEE_BELOW_STATUTORY")])
def test_adapter_passes_an_unreadable_fee_on_for_the_checker_to_refuse(cell, finding):
    fills = [{"date": "2024-06-14", "code": "600001.SH", "side": "sell", "price": "10.00", "prev_close": "10.00",
              "fee": cell, "turnover": "10000", "st": "0", "list_date": "2000-01-01"}]
    rows, report = adapt.adapt_rows(fills, "generic")
    out = check_rows(rows, strict=True)
    assert checks(out) == [finding] and out["stamp"] is None
    assert ("fee_not_a_number" in report["cells_not_read"]) == (finding == "ROW_INVALID")


def test_adapter_passes_other_unreadable_cells_on_too():
    base = {"date": "2024-06-14", "code": "600001.SH", "side": "sell", "price": "10.00", "prev_close": "10.00",
            "fee": "5.1", "turnover": "10000", "st": "0", "list_date": "2000-01-01"}
    for cell, reason in (("turnover", "turnover_not_a_number"), ("st", "st_not_read"), ("list_date", "list_date_not_read")):
        rows, report = adapt.adapt_rows([dict(base, **{cell: "??"})], "generic")
        assert reason in report["cells_not_read"], cell
        # an ST cell that cannot be read leaves the scope undetermined (the row has no scope of its own)
        assert checks(check_rows(rows, strict=True)) == ["SCOPE_UNDETERMINED" if cell == "st" else "ROW_INVALID"], cell
    rows, report = adapt.adapt_rows([base], "generic")
    assert report["cells_not_read"] == {} and check_rows(rows, strict=True)["rules_verified"]
    # a code whose suffix names another exchange than its prefix: the adapter counts it, the checker refuses the row
    rows, report = adapt.adapt_rows([dict(base, code="600001", exchange="SZSE")], "generic")
    if "code_prefix_and_exchange_disagree" in report["cells_not_read"]:
        assert checks(check_rows(rows, strict=True)) == ["ROW_INVALID"]
