"""``marina check`` on model-price logs: relaxed options, numeric band findings, per-row view, summary, scope
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
    assert bad["options"] == {"strict": False, "tick": True, "band_tolerance_pct": 0.0} and bad["relaxed"] is False
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
    assert out["row_status"][0]["within_tolerance"]["excess_pct"] == pytest.approx(100 * 0.04 / 12)
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
    assert rc == 0 and out["stamp"] is None and out["options"] == {"strict": False, "tick": False, "band_tolerance_pct": 0.5}
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
