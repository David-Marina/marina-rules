"""``marina check`` behaviour."""
import csv, io
from marina_rules.check import check_rows

def _rows(text):
    return list(csv.DictReader(io.StringIO(text.strip())))

HDR = "date,code,side,price,prev_close,scope,market,fee,turnover\n"

def test_clean_log_gets_stamp():
    out = check_rows(_rows(HDR + "2021-03-01,300001,buy,11.50,10.00,chinext,XSHE,5.10,115000\n"))
    assert out["rules_verified"] is True and out["stamp"].startswith("rules-verified@")

def test_buy_above_limit_up_is_flagged():
    out = check_rows(_rows(HDR + "2020-08-21,300001,buy,11.50,10.00,chinext,XSHE,5.10,115000\n"))
    assert out["rules_verified"] is False and out["counts"]["LIMIT_BUY_ABOVE_UP"] == 1

def test_fee_below_statutory_is_flagged():
    out = check_rows(_rows(HDR + "2023-08-01,600000,sell,9.80,10.00,main_board,XSHG,20.0,98000\n"))
    assert out["counts"]["FEE_BELOW_STATUTORY"] == 1

def test_unlimited_scope_never_flags_price():
    out = check_rows(_rows(HDR + "2024-01-30,603375,buy,45.00,30.12,ipo_first5_main,XSHG,6.0,250000\n"))
    assert out["rules_verified"] is True

def test_stamp_is_deterministic():
    rows = _rows(HDR + "2021-03-01,300001,buy,11.50,10.00,chinext,XSHE,5.10,115000\n")
    assert check_rows(rows)["stamp"] == check_rows(rows)["stamp"]


# --- par-value transfer fee (SSE A shares before 2015-08-01) must never be read as a turnover rate ---------------

def test_par_value_fee_is_not_multiplied_by_turnover():
    from marina_rules.check import statutory_fee_floor
    # 2010-03-01 sell on XSHG: stamp 1‰ of turnover; SSE transfer fee was 0.5‰ of PAR value (not computable from
    # turnover), so it is left out of the floor. Hand arithmetic: 100000 × 0.001 = 100.00.
    assert statutory_fee_floor(100000, "sell", "2010-03-01", "XSHG") == 100.0
    # same day XSHE: stamp 100.00 + 0.0255‰ × 100000 = 2.55 → 102.55
    assert abs(statutory_fee_floor(100000, "sell", "2010-03-01", "XSHE") - 102.55) < 1e-9
    # buy side 2007-06-01 (bilateral 3‰): 100000 × 0.003 = 300.00 on XSHG
    assert statutory_fee_floor(100000, "buy", "2007-06-01", "XSHG") == 300.0


def test_sse_fill_before_2015_is_not_flagged_by_a_par_value_rate():
    # 0.0005 (par-value rate) × turnover would be 50.00 here; the fee 101 ≥ stamp 100 must pass.
    out = check_rows(_rows(HDR + "2010-03-01,600000,sell,10.00,10.00,main_board,XSHG,101.0,100000\n"))
    assert "FEE_BELOW_STATUTORY" not in out["counts"] and "RULE_MISSING" not in out["counts"]
    out = check_rows(_rows(HDR + "2010-03-01,600000,sell,10.00,10.00,main_board,XSHG,99.0,100000\n"))
    assert out["counts"]["FEE_BELOW_STATUTORY"] == 1


def test_bilateral_stamp_duty_flags_a_buy_fee_below_it():
    out = check_rows(_rows(HDR + "2007-06-01,000001,buy,10.00,10.00,main_board,XSHE,200.0,100000\n"))
    assert out["counts"]["FEE_BELOW_STATUTORY"] == 1          # 3‰ buy-side duty = 300 + 2.55 transfer


# --- BSE transfer fee lives under family scope bse_stock 2021-11-15..2022-04-29 ----------------------------------

def test_bse_transfer_fee_component_2021_12_01():
    from marina_rules.check import statutory_fee_floor
    # 2021-12-01 sell, turnover 100000, stamp 1‰ = 100.00 on every exchange.
    # BJSE: + 0.025‰ × 100000 = 2.50 → 102.50 (cn.fee.transfer_fee_each_side.bjse.2021-11-15, scope bse_stock)
    assert abs(statutory_fee_floor(100000, "sell", "2021-12-01", "BJSE") - 102.5) < 1e-9
    # XSHE: + 0.02‰ × 100000 = 2.00 → 102.00
    assert abs(statutory_fee_floor(100000, "sell", "2021-12-01", "XSHE") - 102.0) < 1e-9
    # no market: the XSHG+XSHE record answers (no RuleConflict) → 102.00
    assert abs(statutory_fee_floor(100000, "sell", "2021-12-01") - 102.0) < 1e-9
    # from 2022-04-29 BJSE uses the national stock record: 100.00 + 0.01‰ × 100000 = 1.00 → 101.00
    assert abs(statutory_fee_floor(100000, "sell", "2022-04-29", "BJSE") - 101.0) < 1e-9


def test_bse_fill_checked_with_bse_transfer_fee():
    hdr = "date,code,side,price,prev_close,scope,fee,turnover,market\n"
    # 102.40 < 102.50 (BJSE floor) → flagged; 102.40 ≥ 102.00 (XSHE floor) → not flagged
    out = check_rows(_rows(hdr + "2021-12-01,830799,sell,10.00,10.00,bse,102.40,100000,BJSE\n"))
    assert out["counts"]["FEE_BELOW_STATUTORY"] == 1
    out = check_rows(_rows(hdr + "2021-12-01,000001,sell,10.00,10.00,main_board,102.40,100000,XSHE\n"))
    assert "FEE_BELOW_STATUTORY" not in out["counts"] and "RULE_MISSING" not in out["counts"]
    # no market column: 0.02‰ floor, no error
    out = check_rows(_rows("date,code,side,price,prev_close,scope,fee,turnover\n"
                           "2021-12-01,000001,sell,10.00,10.00,main_board,102.40,100000\n"))
    assert "FEE_BELOW_STATUTORY" not in out["counts"] and "RULE_MISSING" not in out["counts"]

def test_hk_fills_are_not_checked_against_a_share_rules():
    out = check_rows(_rows(HDR + "2024-06-14,0700,buy,350.2,340.0,hk_stock,XHKG,500.0,350200\n"
                                 "2024-06-14,2800,sell,18.005,18.0,hk_etf,,1.0,18005\n"))
    assert out["rules_verified"] is False and out["counts"] == {"MARKET_UNSUPPORTED": 2}

def test_us_fills_are_not_checked_against_a_share_rules():
    out = check_rows(_rows(HDR + "2024-06-14,AAPL,buy,212.49,214.24,us_stock,XNAS,0.0,21249\n"
                                 "2024-06-14,SPY,sell,542.78,543.10,us_etf,,0.01,54278\n"
                                 "2024-06-14,IBM,sell,169.21,168.00,stock,XNYS,0.01,16921\n"))
    assert out["rules_verified"] is False and out["counts"] == {"MARKET_UNSUPPORTED": 3}
