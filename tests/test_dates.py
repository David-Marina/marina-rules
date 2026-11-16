"""A query date is ISO ``YYYY-MM-DD`` (or a date object) or the call is refused.

Dates are compared as ISO text. Before this check ``"20200102"`` sorted after ``"2020-08-24"`` and a ChiNext question
about 2 January 2020 was answered with the 20% band that began on 24 August 2020 — a wrong value, silently. The
decision schema already promised ``trade_date`` matches ``^\\d{4}-\\d{2}-\\d{2}$``; the input now has to."""
import datetime as dt

import pytest

import marina_rules as mr
from marina_rules.check import check_rows
from marina_rules.cli import main as cli
from marina_rules.contract import resolve
from marina_rules.equity import pick_scope

CTX = {"board": "chinext", "st_status": False, "listing_day_index": 100}
BAD = ["20200102", "2020/01/02", "2020-1-2", "2020.01.02", 20200102, 20200102.0, None, "", "abc", "2020-02-31",
       "2020-13-01", "2020-01-021", " 2020-01-02", "02/01/2020", True]
GOOD = ["2020-01-02", dt.date(2020, 1, 2), dt.datetime(2020, 1, 2, 9, 30), "2020-01-02 09:30:00",
        "2020-01-02T09:30:00", "2020-01-02T09:30:00+08:00"]


class _Stamp:   # stands in for numpy.datetime64 / any object whose str() is an ISO timestamp
    def __str__(self):
        return "2020-01-02T00:00:00.000000000"


@pytest.mark.parametrize("d", BAD, ids=repr)
def test_every_lookup_refuses_a_non_iso_date(d):
    calls = [lambda: mr.rule_at("price_limit_pct", d, "chinext", "XSHE"),
             lambda: mr.record_at("price_limit_pct", d, "chinext", "XSHE"),
             lambda: mr.limit_price(10.0, "chinext", d, "XSHE"),
             lambda: mr.tick_size("stock", d),
             lambda: mr.min_tick_band("stock", d, "XSHG"),
             lambda: mr.statutory_fee_floor(10000, "sell", d, "XSHG"),
             lambda: mr.statutory_fee_components(10000, "sell", d, "XSHG"),
             lambda: mr.tracking_state("XSHG", "stock", d),
             lambda: mr.coverage("XSHE", "chinext", ["price_limit_pct"], d, "2021-01-01"),
             lambda: mr.coverage("XSHE", "chinext", ["price_limit_pct"], "2019-01-01", d),
             lambda: mr.gaps_for("XSHG", "stock", "tick_size", d, "2021-01-01"),
             lambda: mr.gaps_for("XSHG", "stock", "tick_size", "2019-01-01", d),
             lambda: mr.parse_contract("au2606", d),
             lambda: mr.contract_matches({"any": [{"delivery_month": [6]}]}, "au2606", d),
             lambda: resolve("price_limit_pct", d, "chinext", "XSHE", CTX),
             lambda: pick_scope(d, board="chinext", st_status=False, listing_day_index=100)]
    for call in calls:
        with pytest.raises(ValueError, match="ISO date 'YYYY-MM-DD'"):
            call()


@pytest.mark.parametrize("d", GOOD + [_Stamp()], ids=repr)
def test_iso_dates_and_date_objects_answer_alike(d):
    assert mr.rule_at("price_limit_pct", d, "chinext", "XSHE") == 0.1      # 10% until 2020-08-24
    assert mr.limit_price(10.0, "chinext", d, "XSHE") == (11.0, 9.0)
    dec = resolve("price_limit_pct", d, "chinext", "XSHE", CTX)
    assert dec["status"] == "DETERMINED" and dec["result"]["value"] == 0.1
    assert dec["trade_date"] == "2020-01-02"                                # always the schema's YYYY-MM-DD


@pytest.mark.parametrize("d,want", [("20200102", "2020-01-02"), ("2020/01/02", "2020-01-02"), ("2020-1-2", "2020-01-02"),
                                    ("2020/1/2", "2020-01-02"), (20200102, "2020-01-02")])
def test_the_refusal_says_how_to_write_the_date(d, want):
    with pytest.raises(ValueError) as e:
        mr.rule_at("price_limit_pct", d, "chinext", "XSHE")
    assert f"did you mean '{want}'?" in str(e.value)


@pytest.mark.parametrize("d", ["abc", "", None, "2020-02-31", "202001021", "2020010"])
def test_no_suggestion_when_the_input_is_not_a_date(d):
    with pytest.raises(ValueError) as e:
        mr.rule_at("price_limit_pct", d, "chinext", "XSHE")
    assert "did you mean" not in str(e.value)


def test_the_two_regimes_are_still_told_apart():
    assert mr.rule_at("price_limit_pct", "2020-08-21", "chinext", "XSHE") == 0.1
    assert mr.rule_at("price_limit_pct", "2020-08-24", "chinext", "XSHE") == 0.2


def test_gaps_for_keeps_its_half_open_point_query():
    # resolve() asks for the single day d as [d, d + "\x00"): the upper bound is not a date and must stay accepted
    assert mr.gaps_for("XSHG", "stock", "tick_size", "2020-01-02", "2020-01-02\x00") == \
        mr.gaps_for("XSHG", "stock", "tick_size", "2020-01-02", "2020-01-03")


# --- the checker -------------------------------------------------------------------------------------------------
def _row(date, price="11.0"):
    return {"date": date, "code": "300001", "side": "buy", "price": price, "prev_close": "10.0", "scope": "chinext",
            "market": "XSHE"}


@pytest.mark.parametrize("d", ["20200102", "2020/01/02", "2020-1-2"])
def test_checker_refuses_the_row_instead_of_using_the_wrong_band(d):
    # 11.5 is outside the 10% band in force on 2020-01-02 and inside the 20% band of late 2020: read as text, the
    # non-ISO date used to select the later band and the row passed.
    rep = check_rows([_row(d, "11.5")])
    assert [(f["check"]) for f in rep["findings"]] == ["ROW_INVALID"]
    assert "did you mean '2020-01-02'?" in rep["findings"][0]["detail"]
    iso = check_rows([_row("2020-01-02", "11.5")])
    assert [f["check"] for f in iso["findings"]] == ["PRICE_OUTSIDE_BAND"] or \
        "LIMIT_BUY_ABOVE_UP" in [f["check"] for f in iso["findings"]]


def test_checker_still_accepts_a_timestamp_column():
    assert check_rows([_row("2020-01-02 09:31:00")])["findings"] == []


def test_checker_missing_date_is_reported_as_before():
    rep = check_rows([_row("")])
    assert [f["check"] for f in rep["findings"]] == ["ROW_INVALID"]
    assert "need date" in rep["findings"][0]["detail"]


# --- the command line --------------------------------------------------------------------------------------------
def test_cli_query_and_fees_exit_2_on_a_non_iso_date(capsys):
    assert cli(["query", "price_limit_pct", "20200102", "chinext", "XSHE"]) == 2
    assert "did you mean '2020-01-02'?" in capsys.readouterr().out
    assert cli(["fees", "10000", "sell", "20200102", "XSHG"]) == 2
    assert "did you mean '2020-01-02'?" in capsys.readouterr().out


# --- a wrong name is told apart from "not covered" -----------------------------------------------------------------
def test_wrong_rule_name_is_not_answered_with_a_request_for_context():
    d = resolve("price_limit", "2020-01-02", "chinext", "XSHE")            # no context supplied
    assert d["status"] == "OUT_OF_COVERAGE" and d["missing_context"] == []
    assert d["alternatives"]["similar_rules"] == ["price_limit_pct"]
    assert "has no rule named 'price_limit'" in d["reason"]


def test_missing_context_is_still_asked_for_when_the_rule_exists():
    d = resolve("price_limit_pct", "2020-01-02", "chinext", "XSHE")
    assert d["status"] == "MISSING_CONTEXT" and set(d["missing_context"]) == set(CTX)


def test_a_market_code_the_dataset_does_not_use_is_named_as_such():
    with pytest.raises(KeyError) as e:
        mr.rule_at("price_limit_pct", "2020-01-02", "chinext", "SZSE")
    msg = e.value.args[0]
    assert "recorded on market(s) XSHE, not on 'SZSE'" in msg and "not a market code used in the dataset" in msg
    d = resolve("price_limit_pct", "2020-01-02", "chinext", "SZSE", CTX)
    assert d["status"] == "OUT_OF_COVERAGE" and d["alternatives"]["markets"] == ["XSHE"]


def test_a_real_market_code_on_the_wrong_board_says_where_the_scope_is():
    with pytest.raises(KeyError) as e:
        mr.rule_at("price_limit_pct", "2020-01-02", "chinext", "XSHG")
    msg = e.value.args[0]
    assert "recorded on market(s) XSHE, not on 'XSHG'" in msg and "not a market code used" not in msg
    assert resolve("price_limit_pct", "2020-01-02", "chinext", "XSHG", CTX)["alternatives"]["markets"] == ["XSHE"]


def test_markets_recorded():
    assert mr.markets_recorded("chinext") == ["XSHE"]
    assert mr.markets_recorded("no_such_scope") == []
    assert "markets" not in resolve("price_limit_pct", "1990-01-01", "chinext", "XSHE", CTX)["alternatives"]


def test_a_rule_kept_under_another_scope_is_pointed_to():
    with pytest.raises(KeyError) as e:
        mr.rule_at("stamp_duty_sell", "2020-01-02", "chinext", "XSHE")
    assert "stamp_duty_sell is recorded under scope(s): " in e.value.args[0]
    assert "stock" in e.value.args[0].split("recorded under scope(s): ")[1]


# --- the README's one-line statement of maturity per market stays true ----------------------------------------------
def test_readme_maturity_sentence_matches_the_data():
    import collections
    import os
    share = collections.defaultdict(lambda: [0, 0])
    for r in mr.records():
        for m in r.market.split("+"):
            share[m][0] += r.verification == "verified"
            share[m][1] += 1
    mostly_verified = {m for m, (v, n) in share.items() if 2 * v > n}
    assert {"XSHG", "XSHE", "BJSE", "CCFX", "XSGE", "XINE"} <= mostly_verified
    assert not {"XZCE", "GFEX", "XHKG", "XNYS", "XNAS"} & mostly_verified
    readme = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "README.md"),
                  encoding="utf-8").read()
    assert ("China A-share, CFFEX, SHFE and INE records are mostly `verified`; CZCE, GFEX, Hong Kong and US records "
            "are mostly `single-source`") in readme
