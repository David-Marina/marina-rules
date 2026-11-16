"""``marina-check`` on model-price logs: relaxed options, numeric band findings, per-row view, summary, scope
derivation from context, board_for_code, and the price-basis hint."""
import csv
import hashlib
import io
import json
import os

import pytest

from marina_rules import dataset_digest, VERSION
from marina_rules.check import (CANON_FIELDS, HINT_MIN_ROWS, canonical_row, check_rows, main, scope_help)
from marina_rules.equity import board_for_code, checkable_scopes, equity_scopes, pick_scope

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
HDR = "date,code,side,price,prev_close,scope,market\n"


def _rows(text):
    return list(csv.DictReader(io.StringIO(text.strip())))


def _load(name):
    with open(os.path.join(ROOT, "examples", name), newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _stamp_by_hand(rows, strict=False):
    h = hashlib.sha256(f"marina-check-canon/2 strict={int(strict)}\n".encode())
    for r in rows:
        c = canonical_row(r)
        h.update((json.dumps([c[k] for k in CANON_FIELDS], ensure_ascii=False, separators=(",", ":")) + "\n").encode())
    return f"rules-verified@{VERSION}:" + hashlib.sha256((dataset_digest() + "\n" + h.hexdigest()).encode()).hexdigest()[:32]


# --- default behaviour is unchanged --------------------------------------------------------------------------------

def test_default_output_on_examples_unchanged():
    ok = check_rows(_load("fills_ok.csv"))
    assert ok["rules_verified"] is True and ok["findings"] == [] and ok["counts"] == {}
    assert ok["stamp"] == _stamp_by_hand(_load("fills_ok.csv"))
    assert check_rows(_load("fills_ok.csv"), strict=True)["stamp"] == _stamp_by_hand(_load("fills_ok.csv"), strict=True)
    bad = check_rows(_load("fills_bad.csv"))
    assert bad["rules_verified"] is False and bad["stamp"] is None
    assert bad["counts"] == {"LIMIT_BUY_ABOVE_UP": 1, "PRICE_OUTSIDE_BAND": 1, "FEE_BELOW_STATUTORY": 1}
    assert [(f["row"], f["check"], f["detail"]) for f in bad["findings"]] == [
        (1, "LIMIT_BUY_ABOVE_UP", "price 11.5 > limit_up 11.0"),
        (1, "PRICE_OUTSIDE_BAND", "11.5 not in [9.0, 11.0]"),
        (2, "FEE_BELOW_STATUTORY", "fee 20.00 < statutory minimum 98.98")]
    assert bad["options"] == {"strict": False, "tick": True, "band_tolerance_pct": 0.0, "assume_seasoned": False, "assume_not_st": False} and bad["relaxed"] is False
    assert bad["rows_with_findings"] == 2 and "row_status" not in bad and "stamp_withheld" not in bad
    # a non-band finding carries exactly the old keys
    assert set(bad["findings"][2]) == {"row", "code", "date", "check", "detail"}


def test_cli_exit_codes_unchanged(capsys):
    assert main([os.path.join(ROOT, "examples", "fills_ok.csv")]) == 0
    assert main([os.path.join(ROOT, "examples", "fills_bad.csv")]) == 1
    capsys.readouterr()


# --- numeric band fields ---------------------------------------------------------------------------------------------

def test_band_findings_carry_numbers():
    out = check_rows(_rows(HDR + "2021-03-01,300001,sell,7.90,10.00,chinext,XSHE\n"))
    f = [x for x in out["findings"] if x["check"] == "LIMIT_SELL_BELOW_DOWN"][0]
    assert f["limit_up"] == 12.0 and f["limit_down"] == 8.0 and f["violated_limit"] == "limit_down"
    assert f["excess"] == pytest.approx(-0.1) and f["excess_pct"] == pytest.approx(-1.25)


# --- model-price options ---------------------------------------------------------------------------------------------

SLIP = HDR + ("2021-03-01,300001,buy,12.04,10.00,chinext,XSHE\n"      # 0.04 over 12.00 = 0.333%
              "2021-03-01,300002,sell,9.00,10.00,chinext,XSHE\n")    # inside the band


def test_tolerance_moves_small_excess_out_of_findings():
    strict = check_rows(_rows(SLIP))
    assert strict["counts"] == {"LIMIT_BUY_ABOVE_UP": 1, "PRICE_OUTSIDE_BAND": 1} and strict["within_tolerance"] == 0
    out = check_rows(_rows(SLIP), band_tolerance_pct=0.4, per_row=True)
    assert out["findings"] == [] and out["counts"] == {} and out["within_tolerance"] == 1
    assert out["row_status"][0]["status"] == "within_tolerance"
    assert out["row_status"][0]["within_tolerance"][0]["excess_pct"] == pytest.approx(100 * 0.04 / 12)
    assert out["row_status"][1] == {"row": 2, "scope": "chinext", "status": "ok"}
    # a tolerance below the excess still flags it
    assert check_rows(_rows(SLIP), band_tolerance_pct=0.3)["counts"]["PRICE_OUTSIDE_BAND"] == 1


def test_relaxed_run_never_carries_a_stamp():
    for kw in ({"band_tolerance_pct": 0.4}, {"tick": False}):
        out = check_rows(_rows(SLIP if "band_tolerance_pct" in kw else HDR + "2021-03-01,300001,buy,11.503,10.00,chinext,XSHE\n"), **kw)
        assert out["clean"] is True and out["relaxed"] is True
        assert out["rules_verified"] is False and out["stamp"] is None and "strict run" in out["stamp_withheld"]
    # the same clean log, strict, keeps the stamp exactly as before
    clean = HDR + "2021-03-01,300001,buy,11.50,10.00,chinext,XSHE\n"
    assert check_rows(_rows(clean))["stamp"] == _stamp_by_hand(_rows(clean))


def test_no_tick_skips_only_the_tick_check():
    rows = _rows(HDR + "2021-03-01,300001,buy,11.503,10.00,chinext,XSHE\n2021-03-01,300001,buy,12.503,10.00,chinext,XSHE\n")
    assert check_rows(rows)["counts"]["PRICE_OFF_TICK"] == 2
    out = check_rows(rows, tick=False)
    assert "PRICE_OFF_TICK" not in out["counts"] and out["counts"]["PRICE_OUTSIDE_BAND"] == 1
    assert out["options"]["tick"] is False


def test_bad_tolerance_is_rejected(capsys):
    with pytest.raises(ValueError):
        check_rows([], band_tolerance_pct=-1)
    with pytest.raises(ValueError):
        check_rows([], band_tolerance_pct=float("nan"))
    assert main([os.path.join(ROOT, "examples", "fills_ok.csv"), "--band-tolerance-pct", "x"]) == 2
    assert main([os.path.join(ROOT, "examples", "fills_ok.csv"), "--frobnicate"]) == 2
    capsys.readouterr()


def test_cli_relaxed_run(capsys):
    rc = main([os.path.join(ROOT, "examples", "fills_ok.csv"), "--no-tick", "--band-tolerance-pct=0.5", "--rows"])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0 and out["stamp"] is None and out["options"] == {"strict": False, "tick": False, "band_tolerance_pct": 0.5, "assume_seasoned": False, "assume_not_st": False}
    assert [r["row"] for r in out["row_status"]] == [1, 2, 3]


# --- counting, per-row view, summary ---------------------------------------------------------------------------------

def test_rows_with_findings_and_summary():
    out = check_rows(_rows(HDR + "2020-08-21,300001,buy,11.50,10.00,chinext,XSHE\n"
                                 "2021-03-01,300001,buy,11.50,10.00,chinext,XSHE\n"
                                 "2021-03-02,600000,sell,8.90,10.00,main_board,XSHG\n"), per_row=True)
    assert out["counts"] == {"LIMIT_BUY_ABOVE_UP": 1, "PRICE_OUTSIDE_BAND": 2, "LIMIT_SELL_BELOW_DOWN": 1}
    assert out["rows_with_findings"] == 2           # three findings codes, two rows
    s = out["summary"]
    assert s["by_scope"]["chinext"] == {"rows": 2, "rows_with_findings": 1, "within_tolerance": 0,
                                        "findings": {"LIMIT_BUY_ABOVE_UP": 1, "PRICE_OUTSIDE_BAND": 1}}
    assert s["by_year"]["2020"]["rows_with_findings"] == 1 and s["by_year"]["2021"]["rows"] == 2
    assert s["by_side"]["sell"]["findings"] == {"LIMIT_SELL_BELOW_DOWN": 1, "PRICE_OUTSIDE_BAND": 1}
    assert [r["status"] for r in out["row_status"]] == ["findings", "ok", "findings"]
    assert out["row_status"][0]["checks"] == ["LIMIT_BUY_ABOVE_UP", "PRICE_OUTSIDE_BAND"]


# --- scope help and scope derivation -----------------------------------------------------------------------------------

def test_help_lists_every_checkable_scope(capsys):
    assert main(["--help"]) == 0
    text = capsys.readouterr().out
    assert main(["--list-scopes"]) == 0
    listed = capsys.readouterr().out
    for s in checkable_scopes():
        assert f" {s} " in text and f" {s} " in listed
    assert "st_main" in checkable_scopes() and "ipo_first5_star" in checkable_scopes()
    assert "star_growth_new" not in checkable_scopes()           # suitability only: no price-limit record
    assert "same price basis" in text.lower() and scope_help() in text


def test_pick_scope_from_registry_asserts():
    assert pick_scope("2024-03-01", "main_board", False, 100)["scope"] == "main_board"
    assert pick_scope("2024-03-01", "main_board", True, 100)["scope"] == "st_main"
    assert pick_scope("2024-03-01", "star", False, 3)["scope"] == "ipo_first5_star"
    assert pick_scope("2024-03-01", "bse", False, 1)["scope"] == "ipo_day1_bse"
    assert "b_share" not in equity_scopes() and "etf" not in equity_scopes()


def test_pick_scope_listing_window_depends_on_date():
    # a registration-regime main-board IPO on its third day: unlimited window only from 2023-04-10
    assert pick_scope("2023-04-12", "main_board", False, 3, issue_regime="registration")["scope"] == "ipo_first5_main"
    assert pick_scope("2022-03-01", "main_board", False, 3, issue_regime="registration")["scope"] == "main_board"
    # ChiNext listing day: main-board day-1 regime before 2020-08-24, five-day window after
    assert pick_scope("2019-05-06", "chinext", False, 1, issue_regime="approval")["scope"] == "ipo_day1_main"
    assert pick_scope("2020-08-24", "chinext", False, 1, issue_regime="registration")["scope"] == "ipo_first5_chinext"


def test_pick_scope_never_guesses():
    r = pick_scope("2024-03-01", "main_board", False, 3)            # day 3 in 2024: regime decides; not given
    assert r["status"] == "NO_MATCH" and r["scope"] is None and r["needs"]["ipo_first5_main"] == ["issue_regime"]
    r = pick_scope("2024-03-01", "main_board", None, 100)           # ST status unknown
    assert r["status"] == "NO_MATCH" and "st_status" in r["needs"]["main_board"]
    r = pick_scope("2024-03-01", "main_board", True, 500, delisting_day_index=3)
    assert r["status"] == "AMBIGUOUS" and set(r["candidates"]) == {"st_main", "delisting"}


CTX = "date,code,side,price,prev_close,scope,market,board,st,listing_day_index,issue_regime\n"


def test_scope_derived_from_context_columns():
    rows = _rows(CTX + "2024-03-01,600000,buy,10.95,10.00,,XSHG,,false,100,\n"       # board from code → main_board
                       "2024-03-01,600001,buy,10.55,10.00,,XSHG,main_board,true,100,\n"  # st_main: 5% band → over
                       "2024-03-01,600002,buy,10.45,10.00,main_board,XSHG,,true,100,\n"  # explicit scope wins
                       "2024-03-01,603999,buy,30.00,10.00,,XSHG,,false,3,registration\n")  # ipo_first5_main: unlimited
    out = check_rows(rows, per_row=True)
    assert [r["scope"] for r in out["row_status"]] == ["main_board", "st_main", "main_board", "ipo_first5_main"]
    assert [r["status"] for r in out["row_status"]] == ["ok", "findings", "ok", "ok"]
    assert out["row_status"][0]["scope_derived"] is True and "scope_derived" not in out["row_status"][2]
    # the stamp commits to the derived scope: same as the log with the scope written out
    clean = rows[:1] + rows[2:]
    spelled = [dict(r, scope=s) for r, s in zip(clean, ["main_board", "main_board", "ipo_first5_main"])]
    assert check_rows(clean)["stamp"] == check_rows(spelled)["stamp"] is not None


def test_undetermined_scope_is_its_own_finding():
    rows = _rows(CTX + "2024-03-01,600000,buy,10.00,10.00,,XSHG,,false,3,\n"          # regime missing
                       "2024-03-01,510300,buy,10.00,10.00,,XSHG,,false,100,\n"        # not a stock code, no board
                       "2024-03-01,600000,buy,10.00,10.00,,XSHG,,maybe,100,\n")       # unparsable st
    out = check_rows(rows, per_row=True)
    assert out["counts"] == {"SCOPE_UNDETERMINED": 3} and out["stamp"] is None
    assert out["summary"]["by_scope"]["undetermined"]["rows"] == 3
    assert "510300" in out["findings"][1]["detail"] and "maybe" in out["findings"][2]["detail"]


def test_row_without_scope_or_context_keeps_old_default():
    out = check_rows(_rows("date,code,side,price,prev_close\n2024-03-01,600000,buy,10.00,10.00\n"))
    assert out["counts"] == {"RULE_MISSING": 1}                    # scope 'stock' has no price-limit record, as before


# --- board_for_code ---------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("code,want", [
    ("600000", ("main_board", "XSHG")), ("605001", ("main_board", "XSHG")), ("688981", ("star", "XSHG")),
    ("000001", ("main_board", "XSHE")), ("002594", ("main_board", "XSHE")), ("300750", ("chinext", "XSHE")),
    ("301001", ("chinext", "XSHE")), ("920001", ("bse", "BJSE")), ("830799", ("bse", "BJSE")),
    ("600000.SH", ("main_board", "XSHG")), ("SZ000001", ("main_board", "XSHE")),
    ("510300", None), ("159915", None), ("900901", None), ("200002", None), ("113001", None), ("123001", None),
    ("000300.SH", None), ("600000.SZ", None), ("ABC", None), ("", None), (None, None), ("6000000", None),
])
def test_board_for_code(code, want):
    assert board_for_code(code) == want


# --- price-basis hint -----------------------------------------------------------------------------------------------

def test_basis_hint_fires_on_constant_factor():
    # price on an adjusted basis ≈ 2 × the unadjusted prev_close, on several days
    rows = _rows(HDR + "\n".join(f"2024-03-0{d},600000,buy,{p},10.00,main_board,XSHG"
                                 for d, p in ((1, "20.40"), (4, "20.90"), (5, "19.80"), (6, "21.10"))))
    hints = check_rows(rows)["hints"]
    assert len(hints) == 1 and hints[0]["code"] == "600000" and hints[0]["rows"] == 4
    assert 1.98 <= hints[0]["typical_factor"] <= 2.11 and "price bases" in hints[0]["message"]


@pytest.mark.parametrize("prices", [
    ("10.03", "10.02", "10.04", "10.01"),          # inside the band
    ("11.03", "11.02", "11.04", "11.01"),          # ordinary slippage over limit-up: < 5%
    ("20.40", "20.90"),                           # too few rows
    ("20.40", "35.00", "12.50"),                   # factors disagree
])
def test_basis_hint_does_not_fire(prices):
    rows = _rows(HDR + "\n".join(f"2024-03-{d + 1:02d},600000,buy,{p},10.00,main_board,XSHG" for d, p in enumerate(prices)))
    assert check_rows(rows)["hints"] == []
    assert HINT_MIN_ROWS == 3


def test_basis_hint_does_not_fire_on_one_bad_row_among_codes():
    rows = _rows(HDR + "2024-03-01,600000,buy,20.40,10.00,main_board,XSHG\n"
                       "2024-03-01,600001,buy,20.40,10.00,main_board,XSHG\n"
                       "2024-03-01,600002,buy,20.40,10.00,main_board,XSHG\n")
    assert check_rows(rows)["hints"] == []


# --- round 2: small-factor hint, day range, list_date, assume-seasoned, by_code -------------------------------------

from marina_rules.check import (HINT_MANY_ROWS, HINT_MIN_MEDIAN_EXCESS_PCT, HINT_ROW_INDEXES, TOLERANCE_BUCKETS)
from marina_rules.equity import LIST_DATE_MARGIN_DAYS, listing_index_from_list_date, seasoned_listing_day_index, scopes


def _days(n, start=1):
    import datetime as dt
    d0 = dt.date(2024, 1, 1)
    return [(d0 + dt.timedelta(days=k)).isoformat() for k in range(start, start + n)]


def _factor_rows(n, factor, code="600000"):
    # raw close / prev_close spread over the top of the 10% band, multiplied by a constant basis factor
    out = []
    for k, d in enumerate(_days(n)):
        raw = 1.05 + 0.05 * k / max(n - 1, 1)
        out.append(f"{d},{code},buy,{10 * raw * factor:.2f},10.00,main_board,XSHG")
    return _rows(HDR + "\n".join(out))


def test_small_factor_with_many_rows_is_hinted():
    rows = _factor_rows(30, 1.05)
    for kw in ({}, {"band_tolerance_pct": 0.5, "tick": False}):
        hints = check_rows(rows, **kw)["hints"]
        assert len(hints) == 1 and hints[0]["rule"] == "many_consistent" and hints[0]["source"] == "band"
        assert hints[0]["rows"] >= HINT_MANY_ROWS and hints[0]["median_excess_pct"] >= HINT_MIN_MEDIAN_EXCESS_PCT
        assert hints[0]["row_indexes_truncated"] is True and len(hints[0]["row_indexes"]) == HINT_ROW_INDEXES
    full = check_rows(rows, per_row=True)["hints"][0]
    assert len(full["row_indexes"]) == full["rows"] and full["row_indexes_truncated"] is False


def test_slippage_on_many_rows_is_never_hinted():
    out = []
    for k, d in enumerate(_days(80)):
        over = 0.001 + 0.004 * (k % 5) / 4                 # 0.1% … 0.5% over the limit
        side, price = ("buy", 11.00 * (1 + over)) if k % 2 else ("sell", 9.00 * (1 - over))
        out.append(f"{d},600000,{side},{price:.4f},10.00,main_board,XSHG")
    out += [f"{d},000001,buy,{11.00 * 1.004:.4f},10.00,main_board,XSHE" for d in _days(60)]
    rows = _rows(HDR + "\n".join(out))
    assert check_rows(rows)["hints"] == []
    relaxed = check_rows(rows, band_tolerance_pct=0.5, tick=False)
    assert relaxed["hints"] == [] and relaxed["within_tolerance"] == 140 and relaxed["findings"] == []


def test_single_bad_small_factor_row_is_not_hinted():
    assert check_rows(_factor_rows(1, 1.05))["hints"] == []
    assert check_rows(_factor_rows(HINT_MANY_ROWS - 1, 1.05))["hints"] == [] or \
        check_rows(_factor_rows(HINT_MANY_ROWS - 1, 1.05))["hints"][0]["rule"] == "few_far"


DR = "date,code,side,price,prev_close,scope,market,day_high,day_low\n"


def test_day_range_check():
    out = check_rows(_rows(DR + "2024-03-01,300750,buy,11.30,10.00,chinext,XSHE,11.20,10.10\n"   # in band, above high
                                "2024-03-01,300750,sell,10.08,10.00,chinext,XSHE,11.20,10.10\n"  # just below low
                                "2024-03-01,300750,sell,10.50,10.00,chinext,XSHE,,\n"             # no range: not checked
                                "2024-03-01,300750,sell,10.50,10.00,chinext,XSHE,10.00,10.10\n"), per_row=True)
    f = out["findings"][0]
    assert f["check"] == "PRICE_OUTSIDE_DAY_RANGE" and f["day_high"] == 11.2 and f["violated_bound"] == "day_high"
    assert f["excess"] == pytest.approx(0.1) and f["excess_pct"] == pytest.approx(100 * 0.1 / 11.2)
    assert out["counts"] == {"PRICE_OUTSIDE_DAY_RANGE": 2, "DAY_RANGE_INVALID": 1}
    tol = check_rows(_rows(DR + "2024-03-01,300750,sell,10.08,10.00,chinext,XSHE,11.20,10.10\n"),
                     band_tolerance_pct=0.5, per_row=True)
    assert tol["findings"] == [] and tol["row_status"][0]["within_tolerance"][0]["check"] == "PRICE_OUTSIDE_DAY_RANGE"


def test_day_range_feeds_the_hint():
    # a 20%-band stock whose price is ~1.13 × the unadjusted day range: never leaves the band
    lines = [f"{d},300750,buy,{10.5 * 1.13 * (0.95 + 0.05 * k / 24):.2f},10.00,chinext,XSHE,10.50,9.80"
             for k, d in enumerate(_days(25))]
    out = check_rows(_rows(DR + "\n".join(lines)))
    assert "PRICE_OUTSIDE_BAND" not in out["counts"] and out["counts"]["PRICE_OUTSIDE_DAY_RANGE"] == 25
    assert [(h["code"], h["source"]) for h in out["hints"]] == [("300750", "day_range")]


def test_day_range_columns_and_the_stamp():
    plain = HDR + "2024-03-01,300750,buy,10.50,10.00,chinext,XSHE\n"
    with_dr = DR + "2024-03-01,300750,buy,10.50,10.00,chinext,XSHE,10.60,10.20\n"
    s_plain, s_dr = check_rows(_rows(plain))["stamp"], check_rows(_rows(with_dr))["stamp"]
    assert s_plain == _stamp_by_hand(_rows(plain)) and s_dr is not None and s_dr != s_plain
    assert check_rows(_rows(with_dr.replace("10.60,10.20", "10.70,10.20")))["stamp"] != s_dr
    # empty day_high / day_low cells everywhere: the log does not use them, stamp as before
    assert check_rows(_rows(DR + "2024-03-01,300750,buy,10.50,10.00,chinext,XSHE,,\n"))["stamp"] == s_plain


LD = "date,code,side,price,prev_close,scope,market,st,list_date\n"


def test_seasoned_index_comes_from_the_registry():
    bounds = []
    for s, spec in scopes("cn").items():
        v = (spec.get("asserts") or {}).get("listing_day_index")
        for e in (v if isinstance(v, list) else [v if isinstance(v, dict) else {"eq": v}]) if v is not None else []:
            bounds += [e[k] for k in ("eq", "min", "max") if k in e]
    assert seasoned_listing_day_index() == max(bounds) + 1
    # the margin covers the longest window (in trading days) even with three weeks of closure and weekends
    assert LIST_DATE_MARGIN_DAYS >= (seasoned_listing_day_index() - 1) * 7 / 5 + 21 + 7


def test_list_date_past_margin_selects_the_ordinary_scope():
    out = check_rows(_rows(LD + "2024-03-01,600000,buy,10.50,10.00,,XSHG,false,1999-11-10\n"
                                "2024-03-01,688981,buy,10.50,10.00,,XSHG,false,20200716\n"
                                "2024-03-01,603999,buy,10.50,10.00,,XSHG,false,2024-02-20\n"     # inside the margin
                                "2024-03-01,603998,buy,10.50,10.00,,XSHG,true,2024-02-20\n"      # ST: no index needed
                                "2024-03-01,603997,buy,10.50,10.00,,XSHG,false,2024-05-01\n"),   # before listing
                     per_row=True)
    assert [r["scope"] for r in out["row_status"]] == ["main_board", "star", "undetermined", "st_main", "undetermined"]
    assert "listing_day_index" in out["findings"][0]["detail"] and out["relaxed"] is False
    assert listing_index_from_list_date("2024-03-01", "2023-12-31")[0] == seasoned_listing_day_index()
    assert listing_index_from_list_date("2024-03-01", "2024-01-01")[0] is None      # 60 days: not more than margin


def test_assume_seasoned_is_a_counted_relaxation():
    rows = _rows("date,code,side,price,prev_close,scope,market,st,list_date\n"
                 "2024-03-01,600000,buy,10.50,10.00,,XSHG,false,\n"            # relies on the assumption
                 "2024-03-01,600001,buy,10.40,10.00,,XSHG,true,\n"             # st_main: does not need it
                 "2024-03-01,603999,buy,10.50,10.00,,XSHG,false,2024-02-20\n")  # has list_date inside margin
    assert check_rows(rows)["counts"] == {"SCOPE_UNDETERMINED": 2}
    out = check_rows(rows, assume_seasoned=True, per_row=True)
    assert out["assumed_seasoned"] == 1 and out["relaxed"] is True and out["stamp"] is None
    assert "assume seasoned" in out["stamp_withheld"] and out["options"]["assume_seasoned"] is True
    assert [r.get("assumed_seasoned", False) for r in out["row_status"]] == [True, False, False]
    assert [r["scope"] for r in out["row_status"]] == ["main_board", "st_main", "undetermined"]


def test_by_code_buckets_and_top_codes(capsys):
    lines = [f"2024-03-0{k},600000,buy,11.20,10.00,main_board,XSHG" for k in range(1, 4)]      # 1.82% over
    lines += [f"2024-03-0{k},000001,buy,{x},10.00,main_board,XSHE" for k, x in ((1, "11.03"), (2, "11.005"))]
    lines += ["2024-03-01,300750,buy,11.00,10.00,chinext,XSHE"]
    rows = _rows(HDR + "\n".join(lines))
    out = check_rows(rows, band_tolerance_pct=0.5, tick=False)
    bc = out["summary"]["by_code"]
    assert [b["code"] for b in bc] == ["600000", "000001"]
    assert bc[0] == {"code": "600000", "rows": 3, "rows_with_findings": 3, "within_tolerance": 0,
                     "median_excess_pct": pytest.approx(100 * 0.2 / 11, abs=1e-4)}
    assert bc[1]["rows_with_findings"] == 0 and bc[1]["within_tolerance"] == 2
    assert out["summary"]["within_tolerance_excess"] == {"<=0.1%": 1, "<=0.25%": 0, "<=0.5%": 1, "<=1%": 0, ">1%": 0}
    assert len(TOLERANCE_BUCKETS) == 4
    assert check_rows(rows, top_codes=1)["summary"]["by_code"][0]["code"] == "600000"
    assert len(check_rows(rows, top_codes=1)["summary"]["by_code"]) == 1
    path = os.path.join(ROOT, "examples", "fills_bad.csv")
    assert main([path, "--top-codes", "1"]) == 1
    assert len(json.loads(capsys.readouterr().out)["summary"]["by_code"]) == 1
    assert main([path, "--top-codes", "-1"]) == 2
    assert main([os.path.join(ROOT, "examples", "no_such_file.csv")]) == 2
    capsys.readouterr()
