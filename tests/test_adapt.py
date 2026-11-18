"""marina-rules adapt: an engine's trade export becomes checker rows, by declared column readings and joins — never
by guessing. Fixtures use the column names read from each engine's source / each vendor's documentation (the
``basis`` every format states)."""
import datetime as dt
import json

import pytest

from marina_rules import adapt
from marina_rules.adapt import adapt_rows, split_code, to_iso
from marina_rules.check import check_rows, main as check_main
from marina_rules.cli import main as cli

RQ = [  # rqalpha _to_trade_record
    {"datetime": "2020-01-02 15:00:00", "trading_datetime": "2020-01-02 15:00:00", "order_book_id": "300001.XSHE",
     "symbol": "特锐德", "side": "BUY", "position_effect": "OPEN", "exec_id": 1, "tax": 0.0, "commission": 5.0,
     "last_quantity": 1000, "last_price": 11.0, "order_id": 1, "transaction_cost": 5.0},
    {"datetime": "2020-01-03 15:00:00", "trading_datetime": "2020-01-03 15:00:00", "order_book_id": "300001.XSHE",
     "symbol": "特锐德", "side": "SELL", "position_effect": "CLOSE", "exec_id": 2, "tax": 11.5, "commission": 5.0,
     "last_quantity": 1000, "last_price": 11.5, "order_id": 2, "transaction_cost": 16.5},
    {"datetime": "2020-01-03 15:00:00", "trading_datetime": "2020-01-03 15:00:00", "order_book_id": "600000.XSHG",
     "symbol": "浦发银行", "side": "BUY", "position_effect": "OPEN", "exec_id": 3, "tax": 0.0, "commission": 5.0,
     "last_quantity": 100, "last_price": 12.31, "order_id": 3, "transaction_cost": 5.0},
]
TS_DAILY = [  # tushare daily
    {"ts_code": "300001.SZ", "trade_date": "20200102", "high": "11.0", "low": "10.0", "close": "11.0", "pre_close": "10.0"},
    {"ts_code": "300001.SZ", "trade_date": "20200103", "high": "11.6", "low": "10.9", "close": "11.5", "pre_close": "11.0"},
    {"ts_code": "600000.SH", "trade_date": "20200103", "high": "12.4", "low": "12.2", "close": "12.31", "pre_close": "12.3"},
]
TS_BASIC = [{"ts_code": "300001.SZ", "list_date": "20091030"}, {"ts_code": "600000.SH", "list_date": "19991110"}]
TS_ST = [{"ts_code": "000004.SZ", "trade_date": "20200102"}, {"ts_code": "000004.SZ", "trade_date": "20200103"}]


# --- codes and dates ------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("text,exchange,want", [
    ("000001.SZ", None, ("000001", "XSHE")), ("000001.XSHE", None, ("000001", "XSHE")),
    ("000001.SZSE", None, ("000001", "XSHE")), ("sz.000001", None, ("000001", "XSHE")),
    ("SZ000001", None, ("000001", "XSHE")), ("SHSE.600000", None, ("600000", "XSHG")),
    ("600000.SH", None, ("600000", "XSHG")), ("600000.SS", None, ("600000", "XSHG")),
    ("sh.600000", None, ("600000", "XSHG")), ("600000", "SSE", ("600000", "XSHG")),
    ("600000", "Exchange.SSE", ("600000", "XSHG")), ("430047", "BSE", ("430047", "BJSE")),
    ("920001.BJ", None, ("920001", "BJSE")), ("600000", None, ("600000", "XSHG")),
    ("510300", None, ("510300", "")),                      # a fund: no stock prefix, market unknown
    ("510300.SH", None, ("510300", "XSHG")),
])
def test_split_code(text, exchange, want):
    assert split_code(text, exchange) == want


@pytest.mark.parametrize("text,exchange", [("AAPL", None), ("00700.HK", None), ("IF2006.CFFEX", None), ("60000", None),
                                           ("600000.SH", "SZSE"), ("", None), (None, None), ("600000", "NYSE")])
def test_split_code_refuses_what_it_does_not_know(text, exchange):
    assert split_code(text, exchange) is None


@pytest.mark.parametrize("value,fmt,want", [
    ("2020-01-02", "auto", "2020-01-02"), ("2020-01-02 15:00:00", "auto", "2020-01-02"), ("20200102", "auto", "2020-01-02"),
    ("20200102 150000", "auto", "2020-01-02"), ("2020/1/2", "auto", "2020-01-02"), ("2020.01.02", "auto", "2020-01-02"),
    (dt.date(2020, 1, 2), "iso", "2020-01-02"), (dt.datetime(2020, 1, 2, 23, 59, 59, 999990), "auto", "2020-01-02"),
    ("20200102", "yyyymmdd", "2020-01-02"), ("2020-01-02", "iso", "2020-01-02"),
    ("20200102", "iso", None), ("2020-01-02", "yyyymmdd", None), ("02/01/2020", "auto", None), ("1/2/2020", "auto", None),
    ("2020-02-31", "auto", None), ("20200231", "auto", None), ("", "auto", None), (None, "auto", None), ("abc", "auto", None),
])
def test_to_iso(value, fmt, want):
    assert to_iso(value, fmt) == want


# --- one engine, end to end -------------------------------------------------------------------------------------------
def test_rqalpha_with_tushare_tables_checks_clean_and_is_stamped():
    rows, rep = adapt_rows(RQ, "rqalpha", bars=TS_DAILY, bars_format="tushare", listing=TS_BASIC,
                           listing_format="tushare", st=TS_ST, st_format="tushare")
    assert rows[0] == {"date": "2020-01-02", "code": "300001", "side": "buy", "price": "11.0", "prev_close": "10.0",
                       "market": "XSHE", "board": "chinext", "st": "false", "list_date": "2009-10-30", "fee": "5",
                       "turnover": "11000", "day_high": "11.0", "day_low": "10.0", "row_error": ""}
    assert rows[1]["side"] == "sell" and rows[1]["fee"] == "16.5" and rows[2]["board"] == "main_board"
    assert rep["cells_not_read"] == {} and rep["rows_without_prev_close"] == 0 and rep["rows_without_st"] == 0
    assert rep["bars"]["fills_with_a_bar"] == 3 and rep["st"]["fills_not_st"] == 3 and rep["listing"]["fills_with_a_list_date"] == 3
    out = check_rows(rows)
    assert out["clean"] and out["stamp"] and not out["relaxed"]
    assert set(out["summary"]["by_scope"]) == {"chinext", "main_board"}


def test_a_fill_beyond_the_band_of_its_day_is_found_through_the_adapter():
    # 11.5 on 2020-01-02 is +15%: outside ChiNext's 10% band of that day (20% only from 2020-08-24)
    fills = [dict(RQ[0], last_price=11.5)]
    rows, _ = adapt_rows(fills, "rqalpha", bars=TS_DAILY, bars_format="tushare", listing=TS_BASIC, listing_format="tushare",
                         st=TS_ST, st_format="tushare")
    checks = [f["check"] for f in check_rows(rows)["findings"]]
    assert "LIMIT_BUY_ABOVE_UP" in checks


# --- the other engines' columns ---------------------------------------------------------------------------------------
def test_vnpy_trade_rows():
    fills = [{"symbol": "000001", "exchange": "SZSE", "orderid": "1", "tradeid": "1", "direction": "多", "offset": "开",
              "price": 10.5, "volume": 200, "datetime": dt.datetime(2021, 3, 1, 9, 31)},
             {"symbol": "600000", "exchange": "Exchange.SSE", "direction": "Direction.SHORT", "price": 10.0, "volume": 100,
              "datetime": "2021-03-02 09:31:00+08:00"},
             {"symbol": "600000", "exchange": "SSE", "direction": "Short", "price": 10.0, "volume": 100,
              "datetime": "2021-03-02 09:31:00"}]
    rows, rep = adapt_rows(fills, "vnpy")
    assert [(r["date"], r["code"], r["market"], r["side"], r["turnover"]) for r in rows] == [
        ("2021-03-01", "000001", "XSHE", "buy", "2100"), ("2021-03-02", "600000", "XSHG", "sell", "1000"),
        ("2021-03-02", "600000", "XSHG", "sell", "1000")]
    assert all(r["fee"] == "" for r in rows) and rep["rows_without_prev_close"] == 3


def test_backtrader_transactions_side_from_sign():
    fills = [{"date": dt.datetime(2021, 3, 1, 23, 59, 59, 999990), "amount": 100, "price": 10.0, "sid": 0, "symbol": "000001.SZ", "value": -1000.0},
             {"date": "2021-03-02 23:59:59.999990", "amount": -100, "price": 10.2, "sid": 0, "symbol": "000001.SZ", "value": 1020.0}]
    rows, rep = adapt_rows(fills, "backtrader")
    assert [(r["date"], r["side"], r["turnover"]) for r in rows] == [("2021-03-01", "buy", "1000"), ("2021-03-02", "sell", "1020")]
    assert any("nets every fill" in n for n in rep["notes"])


def test_gm_execution_reports():
    fills = [{"symbol": "SHSE.600000", "side": 1, "price": 10.0, "volume": 100, "amount": 1000.0, "created_at": "2021-03-01 09:31:00+08:00"},
             {"symbol": "SZSE.000001", "side": 2, "price": 10.2, "volume": 100, "amount": 1020.0, "created_at": "2021-03-02 09:31:00+08:00"}]
    rows, _ = adapt_rows(fills, "gm")
    assert [(r["code"], r["market"], r["side"]) for r in rows] == [("600000", "XSHG", "buy"), ("000001", "XSHE", "sell")]


# --- generic tables -----------------------------------------------------------------------------------------------------
def test_generic_recognises_common_names_and_chinese_headers():
    fills = [{"成交日期": "20200102", "证券代码": "300001.SZ", "买卖方向": "买入", "成交价格": "11.0", "成交数量": "1000",
              "手续费": "5"}]
    rows, rep = adapt_rows(fills)
    assert (rows[0]["date"], rows[0]["code"], rows[0]["side"], rows[0]["fee"], rows[0]["turnover"]) == \
        ("2020-01-02", "300001", "buy", "5", "11000")
    assert rep["columns_used"]["date"] == "成交日期"


def test_generic_map_side_values_and_date_format():
    fills = [{"d": "20200102", "sec": "300001.SZ", "bs": "23", "px": "11.0", "n": "1000"},
             {"d": "20200103", "sec": "300001.SZ", "bs": "24", "px": "11.5", "n": "1000"}]
    rows, _ = adapt_rows(fills, mapping={"date": "d", "code": "sec", "side": "bs", "price": "px", "quantity": "n"},
                         side_values={"buy": ("23",), "sell": ("24",)}, date_format="yyyymmdd")
    assert [r["side"] for r in rows] == ["buy", "sell"] and rows[1]["date"] == "2020-01-03"


def test_generic_numbers_1_and_2_are_not_read_as_sides():
    rows, rep = adapt_rows([{"date": "2020-01-02", "code": "300001.SZ", "side": "1", "price": "11.0"}])
    assert rows[0]["side"] == "" and rep["cells_not_read"]["side_not_read"]["rows"] == 1


def test_a_commission_alone_is_not_taken_as_the_fee():
    base = {"date": "2020-01-03", "code": "300001.SZ", "side": "sell", "price": "11.5", "quantity": "1000"}
    rows, rep = adapt_rows([dict(base, commission="5")])
    assert rows[0]["fee"] == "" and any("not a total fee" in n for n in rep["notes"])
    rows, _ = adapt_rows([dict(base, commission="5", tax="11.5", transfer_fee="0.23")])
    assert rows[0]["fee"] == "16.73"


def test_a_table_without_the_needed_columns_says_which_and_lists_the_header():
    with pytest.raises(ValueError, match=r"no column found for price; columns are date, code, side"):
        adapt_rows([{"date": "2020-01-02", "code": "300001.SZ", "side": "buy"}])
    with pytest.raises(ValueError, match="no column 'nope'"):
        adapt_rows([{"date": "2020-01-02", "code": "300001.SZ", "side": "buy", "price": 1}], mapping={"price": "nope"})
    with pytest.raises(ValueError, match="unknown fill format"):
        adapt_rows([], "joinquant")


# --- nothing dropped, nothing guessed -----------------------------------------------------------------------------------
def test_unreadable_cells_stay_in_place_and_the_checker_refuses_the_row():
    fills = [{"date": "02/01/2020", "code": "300001.SZ", "side": "buy", "price": "11.0"},
             {"date": "2020-01-02", "code": "AAPL", "side": "buy", "price": "11.0"},
             {"date": "2020-01-02", "code": "300001.SZ", "side": "hold", "price": "x"}]
    rows, rep = adapt_rows(fills)
    assert len(rows) == 3 and rows[0]["date"] == "02/01/2020" and rows[1]["code"] == "AAPL"
    assert {k: v["rows"] for k, v in rep["cells_not_read"].items()} == {
        "date_not_read": 1, "code_not_read": 1, "side_not_read": 1, "price_not_a_number": 1}
    assert rep["cells_not_read"]["date_not_read"]["first_rows"] == [1]
    assert {f["row"] for f in check_rows(rows)["findings"]} == {1, 2, 3}      # every such row is stopped by the checker


def test_a_vendor_date_format_is_converted_not_compared_as_text():
    # the defect of 2026.11.13 through the front door: 20200102 must be checked against the band of 2 January 2020
    fills = [{"date": "20200102", "code": "300001.SZ", "side": "buy", "price": "11.5", "prev_close": "10.0",
              "st": "0", "list_date": "20091030"}]
    rows, _ = adapt_rows(fills)
    assert rows[0]["date"] == "2020-01-02"
    assert "LIMIT_BUY_ABOVE_UP" in [f["check"] for f in check_rows(rows)["findings"]]


# --- joins --------------------------------------------------------------------------------------------------------------
def test_baostock_bars_carry_st_and_refuse_adjusted_prices():
    fills = [{"date": "2020-01-02", "code": "000004.SZ", "side": "buy", "price": "20.0"}]
    bars = [{"date": "2020-01-02", "code": "sz.000004", "high": "20.5", "low": "19.5", "preclose": "20.0",
             "adjustflag": "3", "isST": "1"}]
    rows, rep = adapt_rows(fills, bars=bars, bars_format="baostock")
    assert (rows[0]["prev_close"], rows[0]["st"], rows[0]["day_high"]) == ("20.0", "true", "20.5")
    assert rep["bars"]["fields_joined"] == ["day_high", "day_low", "prev_close", "st"]
    with pytest.raises(ValueError, match="price-adjusted"):
        adapt_rows(fills, bars=[dict(bars[0], adjustflag="2")], bars_format="baostock")


def test_rqdata_bars():
    fills = [{"date": "2020-01-02", "code": "000001.XSHE", "side": "buy", "price": "16.0"}]
    bars = [{"order_book_id": "000001.XSHE", "date": "2020-01-02", "high": 16.9, "low": 15.9, "prev_close": 16.45}]
    rows, _ = adapt_rows(fills, bars=bars, bars_format="rqdata")
    assert rows[0]["prev_close"] == "16.45"


def test_a_fill_without_a_bar_gets_no_previous_close_and_is_counted():
    rows, rep = adapt_rows(RQ, "rqalpha", bars=TS_DAILY[:1], bars_format="tushare")
    assert [r["prev_close"] for r in rows] == ["10.0", "", ""]
    assert rep["bars"]["fills_without_a_bar"] == 2 and rep["rows_without_prev_close"] == 2


def test_two_bars_for_one_security_and_day_are_refused():
    with pytest.raises(ValueError, match="two rows for 300001 XSHE on 2020-01-02"):
        adapt_rows(RQ, "rqalpha", bars=TS_DAILY + TS_DAILY[:1], bars_format="tushare")


def test_previous_close_is_never_computed_from_other_columns():
    bars = [{"日期": "2020-01-02", "股票代码": "300001", "开盘": 10.1, "收盘": 11.0, "最高": 11.0, "最低": 10.0, "涨跌额": 1.0}]
    rows, rep = adapt_rows(RQ[:1], "rqalpha", bars=bars)
    assert rows[0]["prev_close"] == "" and rows[0]["day_high"] == "11.0"
    assert rep["bars"]["fields_joined"] == ["day_high", "day_low"]


def test_st_is_unknown_on_a_day_the_table_does_not_cover():
    rows, rep = adapt_rows(RQ, "rqalpha", st=TS_ST[:1], st_format="tushare")        # the table has 2020-01-02 only
    assert [r["st"] for r in rows] == ["false", "", ""]
    assert rep["st"]["fills_st_unknown"] == 2 and rep["st"]["days_covered"] == 1
    st_fill = [{"date": "2020-01-02", "code": "000004.SZ", "side": "buy", "price": "20.0"}]
    assert adapt_rows(st_fill, st=TS_ST, st_format="tushare")[0][0]["st"] == "true"


# --- --assume-not-st ------------------------------------------------------------------------------------------------------
def test_without_st_the_scope_is_undetermined_and_assume_not_st_is_a_relaxed_run():
    rows, _ = adapt_rows(RQ, "rqalpha", bars=TS_DAILY, bars_format="tushare", listing=TS_BASIC, listing_format="tushare")
    strict = check_rows(rows)
    assert {f["check"] for f in strict["findings"]} == {"SCOPE_UNDETERMINED"} and strict["assumed_not_st"] == 0
    relaxed = check_rows(rows, assume_not_st=True, per_row=True)
    assert relaxed["clean"] and relaxed["relaxed"] and relaxed["stamp"] is None
    assert relaxed["assumed_not_st"] == 3 and relaxed["options"]["assume_not_st"] is True
    assert "assume not ST" in relaxed["stamp_withheld"]
    assert all(s.get("assumed_not_st") for s in relaxed["row_status"])


def test_assume_not_st_never_overrides_an_st_cell():
    row = {"date": "2020-01-02", "code": "000004", "side": "buy", "price": "21.5", "prev_close": "20.0", "market": "XSHE",
           "board": "main_board", "st": "true", "list_date": "1991-01-14"}
    out = check_rows([row], assume_not_st=True)        # +7.5%: inside 10%, outside the ST band of 5%
    assert "LIMIT_BUY_ABOVE_UP" in [f["check"] for f in out["findings"]] and out["assumed_not_st"] == 0


# --- files and command lines ----------------------------------------------------------------------------------------------
def _write(tmp_path, name, header, lines, encoding="utf-8", sep=","):
    p = tmp_path / name
    p.write_bytes((sep.join(header) + "\n" + "\n".join(sep.join(map(str, l)) for l in lines) + "\n").encode(encoding))
    return str(p)


@pytest.fixture
def files(tmp_path):
    rq_cols = ["datetime", "datetime", "trading_datetime", "order_book_id", "symbol", "side", "position_effect", "exec_id",
               "tax", "commission", "last_quantity", "last_price", "order_id", "transaction_cost"]   # the index repeats
    rq = _write(tmp_path, "trades.csv", rq_cols,
                [[r["datetime"]] + [r[c] for c in rq_cols[1:]] for r in RQ], encoding="utf-8-sig")
    daily = _write(tmp_path, "daily.csv", list(TS_DAILY[0]), [list(r.values()) for r in TS_DAILY])
    basic = _write(tmp_path, "basic.csv", list(TS_BASIC[0]), [list(r.values()) for r in TS_BASIC])
    st = _write(tmp_path, "st.csv", list(TS_ST[0]), [list(r.values()) for r in TS_ST])
    return rq, daily, basic, st


def test_cli_adapt_writes_rows_and_reports(files, tmp_path, capsys):
    rq, daily, basic, st = files
    out, rep = str(tmp_path / "rows.csv"), str(tmp_path / "rep.json")
    assert cli(["adapt", rq, "--format", "rqalpha", "--bars", daily, "--bars-format=tushare", "--listing", basic,
                "--listing-format", "tushare", "--st", st, "--st-format", "tushare", "-o", out, "--report", rep]) == 0
    assert adapt.read_table(out)[0]["prev_close"] == "10.0"
    assert json.load(open(rep, encoding="utf-8"))["bars"]["fills_with_a_bar"] == 3
    assert check_main([out]) == 0                      # the written rows are a checker input as they are
    capsys.readouterr()


def test_check_with_format_adapts_then_checks(files, capsys):
    rq, daily, basic, st = files
    assert check_main([rq, "--format", "rqalpha", "--bars", daily, "--bars-format", "tushare", "--listing", basic,
                       "--listing-format", "tushare", "--st", st, "--st-format", "tushare"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["stamp"] and out["adapter"]["format"] == "rqalpha" and out["adapter"]["bars"]["format"] == "tushare"
    assert check_main([rq, "--format", "rqalpha", "--bars", daily, "--bars-format", "tushare", "--listing", basic,
                       "--listing-format", "tushare", "--assume-not-st"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["relaxed"] and out["stamp"] is None and out["assumed_not_st"] == 3


@pytest.mark.parametrize("args", [["--format", "nope"], ["--format"], ["--map", "price"], ["--map", "zzz=a"],
                                  ["--side-values", "up=1"], ["--date-format", "dmy"], ["--bars", "/no/such/file.csv"]])
def test_bad_adapter_options_exit_2(files, args, capsys):
    rq = files[0]
    assert cli(["adapt", rq] + args) == 2
    assert check_main([rq] + args) == 2
    capsys.readouterr()


def test_cli_list_formats_names_every_format_and_its_basis(capsys):
    assert cli(["adapt", "--list-formats"]) == 0
    text = capsys.readouterr().out
    for table in (adapt.FILL_FORMATS, adapt.BAR_FORMATS, adapt.LISTING_FORMATS, adapt.ST_FORMATS):
        for name, spec in table.items():
            assert name in text and spec["basis"] in text


def test_read_table_handles_bom_gbk_and_tabs(tmp_path):
    a = _write(tmp_path, "a.csv", ["成交日期", "证券代码"], [["20200102", "300001.SZ"]], encoding="gb18030")
    b = _write(tmp_path, "b.tsv", ["date", "code"], [["2020-01-02", "300001.SZ"]], encoding="utf-8-sig", sep="\t")
    assert adapt.read_table(a)[0]["成交日期"] == "20200102" and adapt.read_table(b)[0]["date"] == "2020-01-02"


def test_a_plain_checker_file_with_a_bom_is_read(tmp_path, capsys):
    p = _write(tmp_path, "fills.csv", ["date", "code", "side", "price", "prev_close", "scope", "market"],
               [["2020-01-02", "300001", "buy", "11.0", "10.0", "chinext", "XSHE"]], encoding="utf-8-sig")
    assert check_main([p]) == 0
    capsys.readouterr()


def test_every_format_states_what_it_rests_on():
    for table in (adapt.FILL_FORMATS, adapt.BAR_FORMATS, adapt.LISTING_FORMATS, adapt.ST_FORMATS):
        for name, spec in table.items():
            assert spec["title"] and spec["basis"] and spec["columns"], name
            for names in spec["columns"].values():
                assert all(n == n.strip().lower() for n in names), (name, names)
