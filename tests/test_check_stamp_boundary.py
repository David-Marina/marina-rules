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
    out = run(scope="etf", code="510050", price="10.001", decimals="3")   # ETF tick is 0.001: the override IS the exchange grid
    assert out["rules_verified"] and out["stamp"] and out["decimals_override"] == 0


def test_decimals_cannot_stand_in_for_a_missing_market():
    # B-share tick differs by exchange; without a market the recorded tick is unknown, so decimals is the caller's
    out = run(scope="b_share", code="900901", market="", decimals="3", fee="", turnover="")
    assert out["relaxed"] and out["stamp"] is None and out["decimals_override"] == 1
    out = run(scope="b_share", code="900901", market="XSHG", decimals="3", fee="", turnover="")
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


# --- round 4: what the second review found ----------------------------------------------------------------------------
GEN = dict(date="2024-06-14", code="600000.SH", side="sell", price="10.80", prev_close="10.00", list_date="2000-01-01",
           quantity="1000", fee="20")          # +8 %: inside the 10 % band, outside the ST 5 % band


def through_adapter(fill, **tables):
    rows, rep = adapt.adapt_rows([fill], "generic", **tables)
    return check_rows(rows, strict=True), rows, rep


def test_the_plain_row_is_stamped_through_the_adapter():
    out, rows, rep = through_adapter(dict(GEN, st="0"))
    assert out["rules_verified"] and out["stamp"] and rows[0]["row_error"] == "" and rep["rows_refused"] == {}


@pytest.mark.parametrize("extra,reason", [
    (dict(st="0", is_st="1"), "st_columns_disagree"),
    (dict(st="0", st_status="true"), "st_columns_disagree"),
    (dict(pre_close="9.00"), "prev_close_columns_disagree"),
    (dict(exchange="XSHG", market="XSHE"), "exchange_columns_disagree"),
    (dict(ipo_date="2024-06-10"), "list_date_columns_disagree"),
    (dict(exchange="XSHE"), "code_and_exchange_disagree"),
    (dict(quantity="nan"), "turnover_cannot_be_formed"),
    (dict(quantity="abc"), "turnover_cannot_be_formed"),
])
def test_columns_that_disagree_behind_the_adapter_are_refused_not_settled(extra, reason):
    out, rows, rep = through_adapter(dict(GEN, **extra))
    assert checks(out) == ["ROW_INVALID"] and out["stamp"] is None, out["findings"]
    assert reason in rep["rows_refused"] and rows[0]["row_error"]
    assert rows[0]["row_error"] in out["findings"][0]["detail"]


def test_columns_that_agree_in_another_spelling_are_not_a_conflict():
    out, rows, _ = through_adapter(dict(GEN, st="0", is_st="false", pre_close="10.0", exchange="SSE", market="XSHG",
                                        ipo_date="20000101"))
    assert out["rules_verified"] and rows[0]["row_error"] == ""
    out, rows, _ = through_adapter(dict(GEN, st="0", quantity="nan", turnover="10800"))   # the quantity was not needed
    assert out["rules_verified"] and rows[0]["row_error"] == ""


@pytest.mark.parametrize("tables,reason", [
    (dict(bars=[dict(code="600000", date="2024-06-14", pre_close="9.00")]), "prev_close_differs_from_bars"),
    (dict(bars=[dict(code="600000", date="2024-06-14", pre_close="10.00", st="1")]), "st_differs_from_bars"),
    (dict(st=[dict(code="600000", date="2024-06-14", st="1")]), "st_differs_from_st_table"),
    (dict(listing=[dict(code="600000", list_date="2024-06-10")]), "list_date_differs_from_listing_table"),
])
def test_a_joined_table_that_disagrees_with_the_fills_is_refused(tables, reason):
    out, rows, rep = through_adapter(dict(GEN, st="0"), **tables)
    assert checks(out) == ["ROW_INVALID"] and out["stamp"] is None and reason in rep["rows_refused"]


def test_a_joined_table_that_agrees_changes_nothing():
    out, rows, rep = through_adapter(dict(GEN, st="0"), bars=[dict(code="600000", date="2024-06-14", pre_close="10.0")],
                                     st=[dict(code="000004", date="2024-06-14")],
                                     listing=[dict(code="600000", list_date="20000101")])
    assert out["rules_verified"] and rep["rows_refused"] == {}


def test_a_row_error_cell_is_refused_and_is_not_an_unread_column():
    out = run(row_error="columns 'st' and 'is_st' give st two values")
    assert checks(out) == ["ROW_INVALID"] and "row_error" not in out["columns_not_read"]
    assert run(row_error="")["stamp"] == run()["stamp"]


@pytest.mark.parametrize("name", ["fee ", " fee", "turnover ", " prev_close", "date ", "st_status\t"])
def test_a_column_name_with_white_space_around_it_is_still_read(name):
    row = dict(BASE, fee="0", st_status="false")
    row[name] = row.pop(name.strip())
    out = check_rows([row], strict=True)
    assert out["columns_not_read"] == []
    assert out["stamp"] == check_rows([dict(BASE, fee="0", st_status="false")], strict=True)["stamp"]
    assert "FEE_BELOW_STATUTORY" in out["counts"]            # fee 0 is found, whichever column was misspelt


def test_two_columns_whose_names_differ_only_in_white_space():
    out = check_rows([{**BASE, "fee ": "0"}], strict=True)
    assert checks(out) == ["ROW_INVALID"] and "two columns are named 'fee'" in out["findings"][0]["detail"]
    assert check_rows([{**BASE, "fee ": "5.1"}], strict=True)["rules_verified"]          # same cell twice
    assert check_rows([{**BASE, "fee ": ""}], strict=True)["rules_verified"]             # one of them empty


@pytest.mark.parametrize("cells", [
    dict(scope="convertible", price="13.00"), dict(scope="etf"), dict(scope="b_share"), dict(scope="reits"),
    dict(scope="convertible", code="SH600001"), dict(scope="etf", code="600001.SH"),
])
def test_a_stock_code_under_a_scope_of_another_instrument_is_a_conflict(cells):
    out = run(**dict(dict(fee="", turnover=""), **cells))
    assert checks(out) == ["SCOPE_CONTEXT_CONFLICT"] and "not a stock scope" in out["findings"][0]["detail"]
    assert out["stamp"] is None


@pytest.mark.parametrize("code,market", [("900901", "XSHG"), ("sh900901", "XSHG"), ("200002.SZ", "XSHE"), ("900901", "")])
def test_a_b_share_code_under_an_a_share_scope_is_a_conflict(code, market):
    out = run(code=code, market=market, fee="", turnover="")
    assert checks(out) == ["SCOPE_CONTEXT_CONFLICT"] and "B-share code" in out["findings"][0]["detail"]
    ok = run(code=code, market=market or "XSHG", scope="b_share", fee="", turnover="")
    assert ok["rules_verified"], ok["findings"]


@pytest.mark.parametrize("code", ["900901", "sh900901", "900901.SH", "SH.900901"])
def test_a_b_share_code_with_the_other_exchange_is_refused_in_every_spelling(code):
    out = run(code=code, market="XSHE", scope="b_share", fee="", turnover="")
    assert checks(out) == ["ROW_INVALID"] and "B-share code" in out["findings"][0]["detail"]


def test_funds_and_bonds_with_their_own_codes_are_checked_as_before():
    assert run(scope="etf", code="510050", price="10.001", fee="", turnover="")["rules_verified"]
    assert run(scope="convertible", code="113001", price="10.001", fee="", turnover="")["rules_verified"]
    assert run(scope="etf", code="X1", fee="", turnover="")["rules_verified"]            # an unrecognised code


@pytest.mark.parametrize("tail,ok", [(" 09:31:00", True), ("T09:31", True), (" 09:31:00.123456", True),
                                     ("T09:31:00+08:00", True), ("T09:31:00Z", True), (" 9:31", True),
                                     (" XYZ", False), ("Tjunk", False), (" 09:31 and more", False),
                                     ("T", False), (" 2024-06-15", False), ("-09:31", False)])
def test_only_a_time_may_follow_the_day(tail, ok):
    out = run(date="2024-06-14" + tail)
    if ok:
        assert out["rules_verified"] and out["stamp"] == run()["stamp"]
    else:
        assert checks(out) == ["ROW_INVALID"] and "not a time" in out["findings"][0]["detail"]


@pytest.mark.parametrize("other", ["600001.SH", "sh600001", "SH.600001", "600001.XSHG"])
def test_two_spellings_of_one_code_are_one_code_for_rows_that_disagree(other):
    rows = [dict(BASE), dict(BASE, code=other, prev_close="9.60")]
    out = check_rows(rows, strict=True)
    assert [f["check"] for f in out["findings"]] == ["ROWS_DISAGREE"] and out["stamp"] is None
    assert check_rows([dict(BASE), dict(BASE, code=other)], strict=True)["rules_verified"]


@pytest.mark.parametrize("cells", [dict(date="", scope="", st_status="false"), dict(date="", scope="", board="main_board"),
                                   dict(date=""), dict(date="  ", scope="", list_date="2000-01-01")])
def test_a_row_without_a_date_is_an_invalid_row_not_a_crash(cells):
    out = run(**cells)
    assert checks(out) == ["ROW_INVALID"] and "date is missing" in out["findings"][0]["detail"]


def test_the_fee_of_a_fund_bond_or_b_share_is_not_held_to_the_stock_floor():
    # stock stamp duty and transfer fee are not what a fund pays: fee 0.5 on 10000 is not a finding for an ETF
    out = run(scope="etf", code="510050", fee="0.5")
    assert out["rules_verified"] and out["fee_check"] == dict(out["fee_check"], rows_checked=0, rows_not_checked=1)
    for scope, code in (("convertible", "113001"), ("b_share", "900901")):
        out = run(scope=scope, code=code, fee="0")
        assert "FEE_BELOW_STATUTORY" not in out["counts"] and out["fee_check"]["rows_checked"] == 0
    out = run(fee="0.5")                                       # a stock is held to it as before
    assert checks(out) == ["FEE_BELOW_STATUTORY"] and out["fee_check"]["rows_checked"] == 1
    out = run(fee="nan", scope="etf", code="510050")           # unreadable is still refused, whatever the scope
    assert checks(out) == ["ROW_INVALID"]


def test_a_combined_market_on_a_recognised_code_is_checked_on_the_codes_exchange():
    # SZSE has floored the band at one tick since 2011-02-28, SSE only since 2023-04-10
    low = dict(date="2015-01-05", code="000001", side="buy", price="0.05", prev_close="0.04", scope="main_board",
               fee="", turnover="")
    assert check_rows([dict(low, market="XSHE")], strict=True)["rules_verified"]
    assert check_rows([dict(low, market="XSHG+XSHE")], strict=True)["rules_verified"]
    sse = dict(low, code="600000")
    for market in ("XSHG", "XSHG+XSHE"):
        assert "LIMIT_BUY_ABOVE_UP" in check_rows([dict(sse, market=market)], strict=True)["counts"]


@pytest.mark.parametrize("scope,regime,days,conflict", [
    ("ipo_first5_main", "registration", 40, True), ("ipo_first5_main", "registration", 30, True),
    ("ipo_first5_main", "registration", 29, False), ("ipo_first5_main", "registration", 3, False),
    ("ipo_day1_main", "approval", 1, True), ("ipo_day1_main", "approval", 0, False),
    ("main_board", "registration", 40, False), ("main_board", "registration", 0, True),
    ("main_board", "registration", 3, True),       # day 2 to 4 of a registration listing: still in its first five
    ("main_board", "approval", 3, False),
])
def test_a_list_date_inside_the_margin_still_rules_out_a_listing_window_it_cannot_be_in(scope, regime, days, conflict):
    import datetime as dt
    day = dt.date(2024, 6, 14)
    out = run(scope=scope, list_date=str(day - dt.timedelta(days=days)), price="10.50", side="buy",
              issue_regime=regime, st_status="false", fee="", turnover="")
    got = [f["check"] for f in out["findings"]]
    assert ("SCOPE_CONTEXT_CONFLICT" in got) is conflict, out["findings"]
    assert not (conflict and out["stamp"])


def test_listing_index_bounds():
    from marina_rules.equity import listing_index_bounds as b
    assert b("2024-06-14", "2024-06-14") == (1, 1) and b("2024-06-14", "2024-06-13") == (2, 2)
    assert b("2024-06-14", "2024-06-04") == (2, 11) and b("2024-06-14", "2024-05-15") == (6, 31)
    assert b("2024-06-14", "2024-06-15") == (None, None) and b("2024-06-14", "junk") == (None, None)


def test_command_line_reads_a_header_with_white_space_and_refuses_what_the_adapter_cannot_settle(tmp_path, capsys):
    code, out, _ = cli(tmp_path, capsys, HEAD.replace("fee", "fee ") + ROW % "0")
    assert out["stamp"] is None and "FEE_BELOW_STATUTORY" in out["counts"] and out["columns_not_read"] == []
    text = "date,code,side,price,prev_close,st,is_st,quantity,fee\n2024-06-14,600000.SH,sell,10.80,10.00,0,1,1000,20\n"
    code, out, _ = cli(tmp_path, capsys, text, "--format", "generic")
    assert code != 0 and out["stamp"] is None and out["counts"] == {"ROW_INVALID": 1}
    text = text.replace("0,1,1000", "0,0,nan")
    code, out, _ = cli(tmp_path, capsys, text, "--format", "generic")
    assert out["stamp"] is None and out["counts"] == {"ROW_INVALID": 1}
