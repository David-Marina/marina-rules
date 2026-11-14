"""``marina-rules adapt`` — turn a backtest engine's trade export into the rows ``marina check`` reads.

A fill log from an engine has its own column names, its own way of writing a security code and a date, and usually no
previous close. This module rewrites it, and joins what the engine did not export from a data vendor's tables:

    marina-rules adapt trades.csv --format rqalpha --bars daily.csv --bars-format tushare -o fills.csv
    marina-check trades.csv --format rqalpha --bars daily.csv --bars-format tushare        # adapt, then check

  FILLS     the engine's trades                              --format   (default: generic)
  --bars    daily bars: previous close, day high / low, ST   --bars-format
  --listing listing dates (for the listing-window scopes)    --listing-format
  --st      one row per (security, day) on which it was ST   --st-format
  --list-formats   every format with the columns it reads and what that reading rests on

Output columns: date, code, side, price, prev_close, market, board, st, list_date, fee, turnover, day_high, day_low
(the checker's own; ``scope`` is left to the checker, which chooses it from board, st and the listing date).

Nothing is guessed:
  * A format is a declared reading of named columns. Each one states what it rests on (package version and source
    file, or the vendor's documentation). Engines whose export could not be read from a primary source have no
    format here; use ``generic`` with ``--map`` and send a real header so one can be added.
  * ``generic`` recognises common column names (``--list-formats`` prints them). ``--map field=column`` names a column
    outright; ``--side-values buy=A|B,sell=C`` names the cell values; ``--side-from-sign COLUMN`` reads the side from
    the sign of a quantity; ``--date-format iso|yyyymmdd`` fixes the date spelling.
  * No row is dropped. A cell that cannot be read is left empty (a date is passed through as written) and the
    checker reports the row as ROW_INVALID; the report counts every such cell by reason, so row numbers still match
    the source file.
  * ``prev_close`` comes only from a column that the vendor documents as the previous close used for the day's
    price limit. It is never computed from other columns. Bars must be UNADJUSTED; a baostock table that says it is
    adjusted (``adjustflag`` other than 3) is refused.
  * ST: a baostock ``isST`` cell, or an ``--st`` table. With an ``--st`` table a security is "not ST" on a day only
    when the table has rows for that day at all; on a day the table does not cover, ST stays unknown. Unknown ST
    leaves main-board, ChiNext and STAR rows SCOPE_UNDETERMINED unless the check is run with ``--assume-not-st``
    (a relaxed run: no stamp).

The report (JSON, to stderr or ``--report FILE``; ``adapter`` in the checker's output) lists the columns used, the
cells that could not be read, and how many fills found a bar, an ST answer and a listing date.

From Python: ``rows, report = adapt_rows(df.to_dict("records"), "rqalpha", bars=bars.to_dict("records"),
bars_format="tushare")`` then ``marina_rules.check.check_rows(rows)``.
"""
from __future__ import annotations

import csv
import datetime as _dt
import io
import json
import re
import sys

from .equity import board_for_code

OUT_FIELDS = ("date", "code", "side", "price", "prev_close", "market", "board", "st", "list_date", "fee", "turnover",
              "day_high", "day_low")

# --- security codes ---------------------------------------------------------------------------------------------
# Exchange spellings seen in engine and vendor tables → the dataset's market code (ISO 10383).
EXCHANGES = {"SH": "XSHG", "SS": "XSHG", "SSE": "XSHG", "SHSE": "XSHG", "XSHG": "XSHG",
             "SZ": "XSHE", "SZSE": "XSHE", "XSHE": "XSHE",
             "BJ": "BJSE", "BSE": "BJSE", "BJSE": "BJSE"}
_SUFFIXED = re.compile(r"^(\d{6})\.([A-Z]+)$")          # 000001.SZ  000001.XSHE  000001.SZSE
_PREFIXED = re.compile(r"^([A-Z]+)\.?(\d{6})$")         # sz.000001  SHSE.600000  SZ000001
_BARE = re.compile(r"^\d{6}$")


def split_code(text, exchange=None) -> tuple | None:
    """(six-digit code, market) from one of the usual spellings, or None when it is not one of them.

    ``000001.SZ`` / ``000001.XSHE`` / ``000001.SZSE`` / ``sz.000001`` / ``SHSE.600000`` / ``SZ000001`` / ``000001``.
    ``exchange`` is a separate exchange cell (``SSE``, ``Exchange.SZSE``). A bare code without an exchange takes its
    market from ``board_for_code`` (A-share stock prefixes) and has market '' when that does not know it. An exchange
    token that is not a mainland stock exchange gives None."""
    t = str(text if text is not None else "").strip().upper()
    ex = str(exchange if exchange is not None else "").strip().upper().rsplit(".", 1)[-1]
    m = _SUFFIXED.match(t)
    if m:
        digits, token = m.group(1), m.group(2)
    else:
        m = _PREFIXED.match(t)
        if m:
            token, digits = m.group(1), m.group(2)
        elif _BARE.match(t):
            digits, token = t, ""
        else:
            return None
    markets = set()
    for tok in (token, ex):
        if tok:
            if tok not in EXCHANGES:
                return None
            markets.add(EXCHANGES[tok])
    if len(markets) > 1:
        return None
    if markets:
        return digits, markets.pop()
    bm = board_for_code(digits)
    return digits, (bm[1] if bm else "")


# --- dates ----------------------------------------------------------------------------------------------------------
_ISO = re.compile(r"^(\d{4})-(\d{2})-(\d{2})(?:[T ].*)?$", re.S)
_YMD8 = re.compile(r"^(\d{4})(\d{2})(\d{2})(?:\D.*)?$", re.S)
_YEAR_FIRST = re.compile(r"^(\d{4})[/.-](\d{1,2})[/.-](\d{1,2})(?:[T ].*)?$", re.S)
DATE_FORMATS = ("auto", "iso", "yyyymmdd")


def to_iso(value, fmt: str = "auto") -> str | None:
    """``YYYY-MM-DD`` from a date cell, or None. ``iso``: an ISO date or timestamp. ``yyyymmdd``: eight digits.
    ``auto``: either of those, or a year-first date with ``/`` ``.`` ``-`` (2020/1/2). A date object is accepted in
    every mode. Day-first and month-first spellings are never read: 03/04/2020 has no single meaning."""
    if isinstance(value, _dt.datetime):
        value = value.date().isoformat()
    elif isinstance(value, _dt.date):
        value = value.isoformat()
    t = str(value if value is not None else "").strip()
    for name, rx in (("iso", _ISO), ("yyyymmdd", _YMD8), ("auto", _YEAR_FIRST)):
        if fmt not in ("auto", name):
            continue
        m = rx.match(t)
        if m:
            try:
                return _dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat()
            except ValueError:
                return None
    return None


# --- formats --------------------------------------------------------------------------------------------------------
_BUY = ("buy", "b", "long", "买", "买入", "证券买入", "多")
_SELL = ("sell", "s", "short", "卖", "卖出", "证券卖出", "空")

FILL_FORMATS = {
    "generic": {
        "title": "any table: common column names, or name them with --map",
        "columns": {"date": ("date", "trade_date", "datetime", "trading_datetime", "trade_time", "time", "created_at",
                             "dt", "日期", "成交日期", "成交时间", "交易日期"),
                    "code": ("code", "symbol", "ts_code", "order_book_id", "vt_symbol", "security", "security_code",
                             "stock_code", "instrument", "sid", "证券代码", "股票代码", "标的"),
                    "exchange": ("exchange", "market", "交易所"),
                    "side": ("side", "direction", "action", "trade_side", "买卖", "买卖方向", "买卖标志", "交易类型",
                             "操作"),
                    "price": ("price", "last_price", "trade_price", "traded_price", "deal_price", "avg_price",
                              "成交价", "成交价格", "成交均价"),
                    "quantity": ("quantity", "qty", "volume", "amount_shares", "shares", "last_quantity",
                                 "traded_volume", "filled", "成交数量", "成交量"),
                    "turnover": ("turnover", "total_money", "traded_amount", "trade_value", "成交金额", "成交额"),
                    "fee": ("fee", "fees", "transaction_cost", "total_fee", "trading_fee", "cost", "手续费", "费用",
                            "交易费用", "总费用"),
                    "commission": ("commission", "佣金"),
                    "tax": ("tax", "stamp_tax", "stamp_duty", "印花税"),
                    "transfer_fee": ("transfer_fee", "过户费"),
                    "prev_close": ("prev_close", "pre_close", "preclose", "前收盘", "前收盘价", "昨收", "昨收价"),
                    "day_high": ("day_high",), "day_low": ("day_low",),
                    "st": ("st", "st_status", "is_st", "isst"),
                    "list_date": ("list_date", "listed_date", "ipo_date", "ipodate", "上市日期"),
                    "scope": ("scope",), "board": ("board",)},
        "side_values": {"buy": _BUY, "sell": _SELL},
        "basis": "column-name conventions only; say --map / --side-values when a table differs",
        "notes": ("a fee is taken from one total-fee column, or from commission + tax (+ transfer fee) when both a "
                  "commission and a tax column exist; a commission column alone is not a total and is left out",),
    },
    "rqalpha": {
        "title": "RQAlpha sys_analyser: trades.csv of --report, or result['trades']",
        "columns": {"date": ("datetime",), "code": ("order_book_id",), "side": ("side",), "price": ("last_price",),
                    "quantity": ("last_quantity",), "fee": ("transaction_cost",)},
        "side_values": {"buy": ("buy",), "sell": ("sell",)},
        "basis": "rqalpha 6.5.0, rqalpha/mod/rqalpha_mod_sys_analyser/mod.py (_to_trade_record) and report/report.py",
        "notes": ("transaction_cost is the engine's own commission + tax, so FEE_BELOW_STATUTORY tests the engine's "
                  "fee model", "last_price is the engine's matching price; it must be on the same unadjusted basis "
                  "as the bars joined to it"),
    },
    "vnpy": {
        "title": "vn.py TradeData rows (symbol, exchange, direction, price, volume, datetime), e.g. from get_all_trades()",
        "columns": {"date": ("datetime",), "code": ("symbol", "vt_symbol"), "exchange": ("exchange",),
                    "side": ("direction",), "price": ("price",), "quantity": ("volume",)},
        "side_values": {"buy": ("long", "多", "direction.long"), "sell": ("short", "空", "direction.short")},
        "basis": "vnpy 4.5.0, vnpy/trader/object.py (TradeData) and vnpy/trader/constant.py (Direction, Exchange)",
        "notes": ("TradeData carries no fee: FEE_BELOW_STATUTORY cannot be checked",
                  "vn.py has no fill export of its own; write the TradeData attributes to a table yourself"),
    },
    "backtrader": {
        "title": "backtrader Transactions analyzer rows: date, amount, price, sid, symbol, value",
        "columns": {"date": ("date", "datetime"), "code": ("symbol",), "price": ("price",), "quantity": ("amount",)},
        "side_from_sign": "amount",
        "basis": "backtrader 1.9.78.123, backtrader/analyzers/transactions.py",
        "notes": ("the analyzer nets every fill of one data feed within a bar into one row: a buy and a sell in the "
                  "same bar cancel, and the price is the net position's price, not a fill price",
                  "no fee column: FEE_BELOW_STATUTORY cannot be checked",
                  "symbol is the data feed's name; it must be a security code"),
    },
    "gm": {
        "title": "掘金 gm execution reports (ExecRpt): symbol, side, price, volume, amount, created_at",
        "columns": {"date": ("created_at",), "code": ("symbol",), "side": ("side",), "price": ("price",),
                    "quantity": ("volume",), "turnover": ("amount",)},
        "side_values": {"buy": ("1", "orderside_buy"), "sell": ("2", "orderside_sell")},
        "basis": "myquant.cn API documentation (ExecRpt, OrderSide), read 2026-11-14",
        "notes": ("no fee field: FEE_BELOW_STATUTORY cannot be checked",),
    },
}

BAR_FORMATS = {
    "generic": {
        "title": "any daily table: common column names",
        "columns": {"code": ("code", "ts_code", "symbol", "order_book_id", "证券代码", "股票代码"),
                    "date": ("date", "trade_date", "日期", "交易日期"),
                    "prev_close": ("prev_close", "pre_close", "preclose", "前收盘", "前收盘价", "昨收", "昨收价"),
                    "day_high": ("high", "day_high", "最高", "最高价"), "day_low": ("low", "day_low", "最低", "最低价"),
                    "st": ("st", "st_status", "is_st", "isst")},
        "basis": "column-name conventions only; the table must be unadjusted and its previous close must be the "
                 "exchange's reference price on ex-rights days",
    },
    "tushare": {
        "title": "Tushare Pro daily: ts_code, trade_date, high, low, pre_close",
        "columns": {"code": ("ts_code",), "date": ("trade_date",), "prev_close": ("pre_close",),
                    "day_high": ("high",), "day_low": ("low",)},
        "date_format": "yyyymmdd",
        "basis": "tushare.pro documentation of daily, read 2026-11-14: unadjusted; pre_close is 昨收价【除权价】",
    },
    "baostock": {
        "title": "baostock query_history_k_data_plus: date, code, high, low, preclose [, isST, adjustflag]",
        "columns": {"code": ("code",), "date": ("date",), "prev_close": ("preclose",), "day_high": ("high",),
                    "day_low": ("low",), "st": ("isst",), "adjustflag": ("adjustflag",)},
        "date_format": "iso",
        "basis": "baostock documentation (mirror), read 2026-11-14: preclose on an ex-rights day is the price the "
                 "exchange computes and publishes; adjustflag 3 = unadjusted; isST 1 = ST",
    },
    "rqdata": {
        "title": "RQData get_price (adjust_type='none') written as a table: order_book_id, date, high, low, prev_close",
        "columns": {"code": ("order_book_id",), "date": ("date",), "prev_close": ("prev_close",),
                    "day_high": ("high",), "day_low": ("low",)},
        "basis": "ricequant.com RQData documentation, read 2026-11-14: prev_close is the previous close as disclosed "
                 "by the exchange and is not affected by the adjust type; get_price adjusts by default "
                 "(adjust_type='pre') — the table must have been fetched with adjust_type='none'",
    },
}

LISTING_FORMATS = {
    "generic": {"title": "any table with a code and a listing date",
                "columns": {"code": ("code", "ts_code", "symbol", "order_book_id", "证券代码", "股票代码"),
                            "list_date": ("list_date", "listed_date", "ipo_date", "ipodate", "上市日期")},
                "basis": "column-name conventions only"},
    "tushare": {"title": "Tushare Pro stock_basic: ts_code, list_date",
                "columns": {"code": ("ts_code",), "list_date": ("list_date",)},
                "basis": "tushare.pro documentation of stock_basic, read 2026-11-14 (list_date as YYYYMMDD)"},
    "baostock": {"title": "baostock query_stock_basic: code, ipoDate",
                 "columns": {"code": ("code",), "list_date": ("ipodate",)},
                 "basis": "baostock documentation (mirror), read 2026-11-14"},
    "rqdata": {"title": "RQData instruments: order_book_id, listed_date",
               "columns": {"code": ("order_book_id",), "list_date": ("listed_date",)},
               "basis": "ricequant.com RQData documentation, read 2026-11-14"},
}

ST_FORMATS = {
    "generic": {"title": "one row per (code, date) on which the security was ST; an optional st column gives the value",
                "columns": {"code": ("code", "ts_code", "symbol", "order_book_id", "证券代码", "股票代码"),
                            "date": ("date", "trade_date", "日期", "交易日期"), "st": ("st", "st_status", "is_st", "isst")},
                "basis": "column-name conventions only"},
    "tushare": {"title": "Tushare Pro stock_st: ts_code, trade_date (every row is an ST security on that day)",
                "columns": {"code": ("ts_code",), "date": ("trade_date",)},
                "basis": "tushare.pro documentation of stock_st, read 2026-11-14"},
}

_TRUE = frozenset({"1", "true", "t", "yes", "y", "1.0"})
_FALSE = frozenset({"0", "false", "f", "no", "n", "0.0"})


# --- helpers --------------------------------------------------------------------------------------------------------
def _key(name) -> str:
    return str(name if name is not None else "").strip().lstrip("﻿").lower()


def _cell(v) -> str:
    return "" if v is None else str(v).strip()


def _num(v):
    try:
        x = float(_cell(v))
    except ValueError:
        return None
    return x if x == x and abs(x) != float("inf") else None


def _fmt(x: float) -> str:
    return f"{x:.4f}".rstrip("0").rstrip(".")


def _bool(v) -> str:
    t = _cell(v).lower()
    return "true" if t in _TRUE else "false" if t in _FALSE else ""


def _resolve_columns(header: list, spec: dict, mapping: dict | None, what: str) -> dict:
    """field → the header's own column name, from ``--map`` first, then the format's names in order."""
    by_key = {}
    for h in header:
        by_key.setdefault(_key(h), h)
    out = {}
    for field, col in (mapping or {}).items():
        if _key(col) not in by_key:
            raise ValueError(f"{what}: --map {field}={col}: no column {col!r}; columns are {', '.join(map(str, header))}")
        out[field] = by_key[_key(col)]
    for field, names in spec.items():
        if field not in out:
            for n in names:
                if n in by_key:
                    out[field] = by_key[n]
                    break
    return out


def _need(cols: dict, fields: tuple, what: str, header: list, fmt: str) -> None:
    missing = [f for f in fields if f not in cols]
    if missing:
        raise ValueError(f"{what} (format {fmt}): no column found for {', '.join(missing)}; columns are "
                         f"{', '.join(map(str, header))} — name it with --map {missing[0]}=COLUMN, or pick another format")


def _header(rows: list) -> list:
    seen: dict = {}
    for r in rows[:50]:
        for k in r:
            if k is not None:
                seen.setdefault(k, None)
    return list(seen)


def _bump(counter: dict, reason: str, row: int) -> None:
    c = counter.setdefault(reason, {"rows": 0, "first_rows": []})
    c["rows"] += 1
    if len(c["first_rows"]) < 10:
        c["first_rows"].append(row)


# --- the adapter -----------------------------------------------------------------------------------------------------
def adapt_rows(fills, fmt: str = "generic", *, bars=None, bars_format: str = "generic", listing=None,
               listing_format: str = "generic", st=None, st_format: str = "generic", mapping: dict | None = None,
               side_values: dict | None = None, side_from_sign: str | None = None,
               date_format: str | None = None) -> tuple:
    """(rows for ``check_rows``, report). ``fills`` / ``bars`` / ``listing`` / ``st``: iterables of dicts (a
    ``csv.DictReader``, ``DataFrame.to_dict("records")``). See the module docstring; a bad option or a table without
    the columns its format needs raises ValueError."""
    for name, table, known in ((fmt, "fill", FILL_FORMATS), (bars_format, "bar", BAR_FORMATS),
                               (listing_format, "listing", LISTING_FORMATS), (st_format, "ST", ST_FORMATS)):
        if name not in known:
            raise ValueError(f"unknown {table} format {name!r}; known: {', '.join(known)}")
    if date_format is not None and date_format not in DATE_FORMATS:
        raise ValueError(f"--date-format must be one of {', '.join(DATE_FORMATS)}, got {date_format!r}")
    spec = FILL_FORMATS[fmt]
    fills = list(fills)
    header = _header(fills)
    cols = _resolve_columns(header, spec["columns"], mapping, "fills")
    _need(cols, ("date", "code", "price"), "fills", header, fmt)
    sign_col = None
    sign_name = side_from_sign or spec.get("side_from_sign")
    if sign_name:
        sign_col = _resolve_columns(header, {"x": (_key(sign_name),)}, None, "fills").get("x")
        if sign_col is None:
            raise ValueError(f"fills: --side-from-sign {sign_name}: no such column; columns are {', '.join(map(str, header))}")
    elif "side" not in cols:
        _need(cols, ("side",), "fills", header, fmt)
    values = {}
    for side, names in (side_values or spec.get("side_values") or {}).items():
        if side not in ("buy", "sell"):
            raise ValueError(f"--side-values: sides are buy and sell, got {side!r}")
        for n in names:
            values[_key(n)] = side
    dfmt = date_format or spec.get("date_format") or "auto"
    problems: dict = {}
    out, wanted = [], set()
    for i, r in enumerate(fills, start=1):
        row = dict.fromkeys(OUT_FIELDS, "")
        raw_date = _cell(r.get(cols["date"]))
        day = to_iso(r.get(cols["date"]), dfmt)
        row["date"] = day or raw_date          # an unreadable date is passed through: the checker refuses it
        if day is None:
            _bump(problems, "date_not_read", i)
        sc = split_code(r.get(cols["code"]), r.get(cols["exchange"]) if "exchange" in cols else None)
        if sc is None:
            row["code"] = _cell(r.get(cols["code"]))
            _bump(problems, "code_not_read", i)
        else:
            row["code"], row["market"] = sc
            bm = board_for_code(sc[0])
            if bm and bm[1] == sc[1]:
                row["board"] = bm[0]
            elif bm and sc[1] and bm[1] != sc[1]:
                _bump(problems, "code_prefix_and_exchange_disagree", i)
            else:
                _bump(problems, "not_a_recognised_stock_code", i)
        qty = _num(r.get(cols["quantity"])) if "quantity" in cols else None
        if sign_col is not None:
            s = _num(r.get(sign_col))
            row["side"] = "buy" if s is not None and s > 0 else "sell" if s is not None and s < 0 else ""
        else:
            row["side"] = values.get(_key(r.get(cols["side"])), "")
        if not row["side"]:
            _bump(problems, "side_not_read", i)
        row["price"] = _cell(r.get(cols["price"]))
        if _num(row["price"]) is None:
            _bump(problems, "price_not_a_number", i)
        if "turnover" in cols and _num(r.get(cols["turnover"])) is not None:
            row["turnover"] = _fmt(abs(_num(r.get(cols["turnover"]))))
        elif qty is not None and _num(row["price"]) is not None:
            row["turnover"] = _fmt(abs(qty) * _num(row["price"]))
        if "fee" in cols:
            f = _num(r.get(cols["fee"]))
            row["fee"] = "" if f is None else _fmt(abs(f))
        elif "commission" in cols and "tax" in cols:
            parts = [_num(r.get(cols[k])) for k in ("commission", "tax", "transfer_fee") if k in cols]
            row["fee"] = "" if any(p is None for p in parts) else _fmt(sum(abs(p) for p in parts))
        for k in ("prev_close", "day_high", "day_low"):
            if k in cols:
                row[k] = _cell(r.get(cols[k]))
        if "st" in cols:
            row["st"] = _bool(r.get(cols["st"]))
        if "list_date" in cols:
            row["list_date"] = to_iso(r.get(cols["list_date"])) or ""
        for k in ("scope", "board"):       # a table that already names a scope or a board keeps it
            if k in cols and _cell(r.get(cols[k])):
                row[k] = _cell(r.get(cols[k]))
        if day and sc:
            wanted.add((sc[0], day))
        out.append(row)
    report = {"format": fmt, "basis": spec["basis"], "notes": list(spec.get("notes", ())), "rows": len(out),
              "columns_used": dict(cols, **({"side_from_sign": sign_col} if sign_col else {})),
              "date_format": dfmt, "cells_not_read": problems}
    if "commission" in cols and "fee" not in cols and "tax" not in cols:
        report["notes"].append(f"column {cols['commission']!r} is a commission, not a total fee: no fee was taken")
    codes = {c for c, _ in wanted}
    if bars is not None:
        report["bars"] = _join_bars(out, bars, bars_format, wanted)
    if st is not None:
        report["st"] = _join_st(out, st, st_format, wanted)
    if listing is not None:
        report["listing"] = _join_listing(out, listing, listing_format, codes)
    report["rows_without_prev_close"] = sum(1 for r in out if not r["prev_close"])
    report["rows_without_st"] = sum(1 for r in out if not r["st"] and not r.get("scope"))
    report["rows_without_list_date"] = sum(1 for r in out if not r["list_date"] and not r.get("scope"))
    return out, report


def _table(rows, spec: dict, need: tuple, what: str, fmt: str):
    """(iterator over the table's rows, resolved columns). Reads the first row to find the header, then streams."""
    it = iter(rows)
    first = next(it, None)
    if first is None:
        return iter(()), {}
    header = [k for k in first if k is not None]
    cols = _resolve_columns(header, spec["columns"], None, what)
    _need(cols, need, what, header, fmt)

    def gen():
        yield first
        yield from it
    return gen(), cols


def _join_bars(out: list, bars, fmt: str, wanted: set) -> dict:
    spec = BAR_FORMATS[fmt]
    it, cols = _table(bars, spec, ("code", "date"), "bars", fmt)
    dfmt = spec.get("date_format", "auto")
    found: dict = {}
    n = 0
    for b in it:
        n += 1
        sc = split_code(b.get(cols["code"]))
        day = to_iso(b.get(cols["date"]), dfmt)
        if sc is None or day is None or (sc[0], day) not in wanted:
            continue
        if "adjustflag" in cols and _cell(b.get(cols["adjustflag"])) not in ("", "3"):
            raise ValueError(f"bars (format {fmt}): row {n} has adjustflag {_cell(b.get(cols['adjustflag']))!r} — the "
                             "table is price-adjusted; fetch it unadjusted (adjustflag='3')")
        if (sc[0], day) in found:
            raise ValueError(f"bars (format {fmt}): two rows for {sc[0]} on {day} (row {n}); one bar per security and day")
        found[(sc[0], day)] = {k: _cell(b.get(cols[k])) for k in ("prev_close", "day_high", "day_low") if k in cols}
        if "st" in cols:
            found[(sc[0], day)]["st"] = _bool(b.get(cols["st"]))
    matched = 0
    for r in out:
        hit = found.get((r["code"], r["date"]))
        if hit is None:
            continue
        matched += 1
        for k, v in hit.items():
            if v != "" and not r[k]:
                r[k] = v
    return {"format": fmt, "basis": spec["basis"], "columns_used": cols, "rows_read": n,
            "fills_with_a_bar": matched, "fills_without_a_bar": len(out) - matched,
            "fields_joined": sorted({k for h in found.values() for k, v in h.items() if v != ""})}


def _join_st(out: list, st, fmt: str, wanted: set) -> dict:
    spec = ST_FORMATS[fmt]
    it, cols = _table(st, spec, ("code", "date"), "ST table", fmt)
    days_covered, flagged = set(), {}
    n = 0
    for s in it:
        n += 1
        sc = split_code(s.get(cols["code"]))
        day = to_iso(s.get(cols["date"]))
        if sc is None or day is None:
            continue
        days_covered.add(day)
        if (sc[0], day) in wanted:
            flagged[(sc[0], day)] = _bool(s.get(cols["st"])) if "st" in cols else "true"
    yes = no = unknown = 0
    for r in out:
        if r["st"]:
            continue
        v = flagged.get((r["code"], r["date"]))
        if v:
            r["st"] = v
        elif r["date"] in days_covered and v is None:
            r["st"] = "false"          # the table covers this day and does not list the security
        yes += r["st"] == "true"; no += r["st"] == "false"; unknown += r["st"] == ""
    return {"format": fmt, "basis": spec["basis"], "columns_used": cols, "rows_read": n, "days_covered": len(days_covered),
            "fills_st": yes, "fills_not_st": no, "fills_st_unknown": unknown,
            "rule": "not ST only on a day the table has rows for; a day it does not cover stays unknown"}


def _join_listing(out: list, listing, fmt: str, codes: set) -> dict:
    spec = LISTING_FORMATS[fmt]
    it, cols = _table(listing, spec, ("code", "list_date"), "listing table", fmt)
    dates: dict = {}
    n = 0
    for s in it:
        n += 1
        sc = split_code(s.get(cols["code"]))
        day = to_iso(s.get(cols["list_date"]))
        if sc is not None and day is not None and sc[0] in codes:
            dates[sc[0]] = day
    hit = 0
    for r in out:
        if not r["list_date"] and r["code"] in dates:
            r["list_date"] = dates[r["code"]]
        hit += bool(r["list_date"])
    return {"format": fmt, "basis": spec["basis"], "columns_used": cols, "rows_read": n,
            "fills_with_a_list_date": hit, "fills_without_a_list_date": len(out) - hit}


# --- files and the command line ---------------------------------------------------------------------------------------
def read_table(path: str) -> list:
    """Rows of a CSV / TSV file as dicts. UTF-8 (with or without BOM), else GB18030; the delimiter is sniffed."""
    with open(path, "rb") as fh:
        raw = fh.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("gb18030")
    head = text.split("\n", 1)[0]
    delim = "\t" if head.count("\t") > head.count(",") else ","
    return list(csv.DictReader(io.StringIO(text, newline=""), delimiter=delim))


def formats_help() -> str:
    lines = []
    for title, table in (("fill formats (--format)", FILL_FORMATS), ("bar formats (--bars-format)", BAR_FORMATS),
                         ("listing formats (--listing-format)", LISTING_FORMATS), ("ST formats (--st-format)", ST_FORMATS)):
        lines.append(title)
        for name, spec in table.items():
            lines.append(f"  {name:<11}{spec['title']}")
            lines.append("             reads: " + "; ".join(f"{f} ← {' | '.join(n)}" for f, n in spec["columns"].items()))
            if spec.get("side_values"):
                lines.append("             side:  " + "; ".join(f"{s} ← {' | '.join(v)}" for s, v in spec["side_values"].items()))
            if spec.get("side_from_sign"):
                lines.append(f"             side:  sign of {spec['side_from_sign']} (positive = buy)")
            lines.append(f"             rests on: {spec['basis']}")
            for n in spec.get("notes", ()):
                lines.append(f"             note: {n}")
        lines.append("")
    lines.append("no format (use generic with --map, and send a real header): JoinQuant, RiceQuant platform, PTrade, QMT "
                 "— their exports could not be read from a primary source. Qlib: it writes no fill log and its prices "
                 "are adjusted. Zipline: no mainland securities.")
    return "\n".join(lines)


OPTIONS = ("--format", "--bars", "--bars-format", "--listing", "--listing-format", "--st", "--st-format", "--map",
           "--side-values", "--side-from-sign", "--date-format")
USAGE = ("usage: marina-rules adapt FILLS.csv [--format NAME] [--bars FILE [--bars-format NAME]]\n"
         "                          [--listing FILE [--listing-format NAME]] [--st FILE [--st-format NAME]]\n"
         "                          [--map FIELD=COLUMN …] [--side-values buy=A|B,sell=C] [--side-from-sign COLUMN]\n"
         "                          [--date-format auto|iso|yyyymmdd] [-o OUT.csv] [--report REPORT.json]\n"
         "       marina-rules adapt --list-formats")


def split_options(argv: list) -> tuple:
    """(adapter options as a dict, the remaining arguments). Raises ValueError on a malformed adapter option."""
    opts: dict = {"map": {}}
    rest = []
    it = iter(argv)
    for a in it:
        name, eq, v = a.partition("=")
        if name not in OPTIONS:
            rest.append(a)
            continue
        if not eq:
            v = next(it, None)
        if v is None or v == "":
            raise ValueError(f"{name} needs a value")
        if name == "--map":
            field, eq2, col = v.partition("=")
            if not eq2 or not field or not col:
                raise ValueError(f"--map needs FIELD=COLUMN, got {v!r}")
            if field not in FILL_FORMATS["generic"]["columns"]:
                raise ValueError(f"--map: unknown field {field!r}; fields are {', '.join(FILL_FORMATS['generic']['columns'])}")
            opts["map"][field] = col
        elif name == "--side-values":
            sv: dict = {}
            for part in v.split(","):
                side, eq2, names = part.partition("=")
                if not eq2 or side not in ("buy", "sell") or not names:
                    raise ValueError(f"--side-values needs buy=A|B,sell=C, got {v!r}")
                sv[side] = tuple(names.split("|"))
            opts["side_values"] = sv
        else:
            opts[name[2:].replace("-", "_")] = v
    return opts, rest


def adapt_files(fills_path: str, opts: dict) -> tuple:
    """``adapt_rows`` on files, with the options ``split_options`` returns."""
    kw = {"mapping": opts.get("map") or None, "side_values": opts.get("side_values"),
          "side_from_sign": opts.get("side_from_sign"), "date_format": opts.get("date_format"),
          "bars_format": opts.get("bars_format", "generic"), "listing_format": opts.get("listing_format", "generic"),
          "st_format": opts.get("st_format", "generic")}
    for k in ("bars", "listing", "st"):
        if opts.get(k):
            kw[k] = read_table(opts[k])
    return adapt_rows(read_table(fills_path), opts.get("format", "generic"), **kw)


def main(argv: list | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] in ("-h", "--help"):
        print(USAGE + "\n\n" + __doc__)
        return 0 if argv else 2
    if "--list-formats" in argv:
        print(formats_help())
        return 0
    try:
        opts, rest = split_options(argv)
        out_path = report_path = None
        paths = []
        it = iter(rest)
        for a in it:
            if a in ("-o", "--output"):
                out_path = next(it, None)
            elif a == "--report":
                report_path = next(it, None)
            elif a.startswith("-"):
                raise ValueError(f"unknown option {a}")
            else:
                paths.append(a)
        if len(paths) != 1:
            raise ValueError("give exactly one fills file")
        rows, report = adapt_files(paths[0], opts)
    except (ValueError, OSError) as e:
        print(f"marina-rules adapt: {e}\n{USAGE}", file=sys.stderr)
        return 2
    buf = io.StringIO(newline="")
    w = csv.DictWriter(buf, fieldnames=list(OUT_FIELDS) + (["scope"] if any(r.get("scope") for r in rows) else []),
                       extrasaction="ignore", lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    if out_path:
        with open(out_path, "w", encoding="utf-8", newline="") as fh:
            fh.write(buf.getvalue())
    else:
        sys.stdout.write(buf.getvalue())
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if report_path:
        with open(report_path, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
    else:
        print(text, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
