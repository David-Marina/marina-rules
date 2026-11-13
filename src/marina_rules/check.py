"""``marina check`` — verify a fill log against the rules in force on each day.

Input: CSV with columns  date, code, side, price, prev_close, scope  [, market, fee, turnover, decimals]
  * side        buy | sell
  * market      XSHG | XSHE | BJSE …; needed where a rule differs by exchange (one-tick floor, B-share tick)
  * decimals    optional rounding override for the limit price; also used as the tick for PRICE_OFF_TICK
  * scope       main_board | chinext | star | bse | st_main | st_chinext | ipo_day1 | ipo_first5 …
  * fee / turnover   optional; when both present, the fee is checked against the day's statutory
                     components (stamp duty of the fill's side, transfer fee on turnover) as a *lower bound*.
                     A par-value transfer fee (SSE before 2015-08-01) is not computable from turnover and is
                     left out of the bound, never treated as a turnover rate. Supply ``market`` per row.

Checks (each produces a finding on failure):
  ROW_INVALID             missing date/code/side, or price / prev_close missing or not a finite number
                          (nan, inf, empty) — reported even when the band is unlimited
  PRICE_OFF_TICK          price is not an integer multiple of the tick in force for the scope's instrument family
                          (tick_size: stock 0.01, fund 0.001, convertible 0.001 from 2022-08-01 …), compared in
                          Decimal on the price as written. Skipped when no tick is recorded for that date.
  LIMIT_BUY_ABOVE_UP      buy price > limit-up price in force that day
  LIMIT_SELL_BELOW_DOWN   sell price < limit-down price
  PRICE_OUTSIDE_BAND      any fill outside [limit_down, limit_up]
  FEE_BELOW_STATUTORY     fee < statutory minimum (stamp + turnover-based transfer fee; commission excluded)
  RULE_MISSING            no rule in force for (scope, date) — the log cites a scope we do not cover
  MARKET_REQUIRED         prev_close so low the band rounds below one tick; the one-tick floor is
                          exchange-specific (SZSE 2011-02-28, SSE 2023-04-10) and the row has no market
  MARKET_UNSUPPORTED      the row's market or scope is not a China A-share one (XHKG, hk_stock, hk_etf; XNYS,
                          XNAS, us_stock, us_etf): these checks are A-share only, so no other check is run on the row

Output: JSON with findings, counts, the dataset digest, and a ``rules-verified`` stamp when there are
zero findings. The stamp is sha256(dataset_digest ‖ "\n" ‖ sha256(canonical fill log)) and can be recomputed by
anyone holding the same log and the same rules version. It commits to every input that can change a check.

Canonical fill log (``CANON_VERSION`` = 2): the UTF-8 bytes of
    marina-check-canon/2 strict=<0|1>\n
followed by one line per row, in input order:
    json.dumps([date, code, side, price, prev_close, scope, market, decimals, fee, turnover],
               ensure_ascii=False, separators=(",", ":")) + "\n"
where every field is the row's value as a string with surrounding whitespace stripped ("" when absent), except
date (first 10 characters), side (lower-cased) and scope (default "stock" when absent) — exactly the values the
checks used. Changing any of these fields, the row order or the strict flag changes the stamp. It says only that fills respect the rules in this
dataset; it says nothing about look-ahead, survivorship, or overfitting.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import sys
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation

from . import (RuleConflict, citation, dataset_digest, limit_price, market_prefix_for, record_at, scopes, tick_size,
               VERSION, _agreed_tick)

CANON_VERSION = 2
CANON_FIELDS = ("date", "code", "side", "price", "prev_close", "scope", "market", "decimals", "fee", "turnover")


@dataclass
class Finding:
    row: int
    code: str
    date: str
    check: str
    detail: str


def _f(x) -> float | None:
    """A finite float, or None for missing / unparsable / non-finite (nan, inf) input."""
    try:
        v = float(x) if x not in (None, "") else None
    except (TypeError, ValueError):
        return None
    return v if v is not None and math.isfinite(v) else None


def _s(x) -> str:
    return "" if x is None else str(x).strip()


def canonical_row(r: dict) -> dict:
    """The normalised field values the checks use and the stamp commits to (see module docstring)."""
    c = {k: _s(r.get(k)) for k in CANON_FIELDS}
    c["date"] = c["date"][:10]
    c["side"] = c["side"].lower()
    c["scope"] = c["scope"] or "stock"
    return c


def _off_tick(price_text: str, tick: float) -> bool:
    """Is the price, as written, not an integer multiple of ``tick``? Exact Decimal arithmetic: 10.001 vs 0.01."""
    try:
        p, t = Decimal(price_text), Decimal(repr(tick))
    except InvalidOperation:
        return False
    return t > 0 and p % t != 0


def statutory_fee_floor(turnover: float, side: str, date: str, market: str | None = None, strict: bool = False) -> float:
    """Lower bound on the statutory fees of one fill, in CNY: stamp duty of the fill's side + transfer fee on turnover.

    Only TURNOVER-based rules enter: ``stamp_duty_sell`` / ``stamp_duty_buy`` and ``transfer_fee_each_side``
    (fractions of turnover). ``transfer_fee_par_value`` (SSE A shares before 2015-08-01) is a fraction of traded
    PAR VALUE, which a fill log does not carry; it is never multiplied by turnover. On such days the transfer
    component is omitted, so the result stays a valid lower bound. Without ``market`` the lookup asks for a rule
    covering both XSHG and XSHE (an exchange-specific rate never answers for a fill whose exchange is unknown).
    For market BJSE the transfer fee is looked up under the BSE family scope ``bse_stock`` first (BSE-only rate,
    2021-11-15..2022-04-29), then under ``stock``.
    Raises KeyError when a turnover-based rule is missing and no par-value rule explains the gap.
    """
    mkt = market or "XSHG+XSHE"
    stat = turnover * record_at("stamp_duty_sell" if side == "sell" else "stamp_duty_buy", date, "stock", mkt, strict).value
    try:
        stat += turnover * _transfer_fee_record(date, mkt, strict).value
    except KeyError:
        if not _par_value_fee_in_force(date, market, strict):
            raise
    return stat


def _transfer_fee_record(date: str, market: str, strict: bool):
    """The turnover transfer-fee record for one fill: ``bse_stock`` then ``stock`` for BJSE, ``stock`` otherwise."""
    if market == "BJSE":
        try:
            return record_at("transfer_fee_each_side", date, "bse_stock", market, strict)
        except KeyError:
            pass
    return record_at("transfer_fee_each_side", date, "stock", market, strict)


def _par_value_fee_in_force(date: str, market: str | None, strict: bool) -> bool:
    """True if a par-value transfer fee is in force on ``date`` for ``market`` (any market when None)."""
    try:
        record_at("transfer_fee_par_value", date, "stock", market, strict)
        return True
    except KeyError:
        return False


def check_rows(rows: list[dict], strict: bool = False) -> dict:
    findings: list[Finding] = []
    canon = hashlib.sha256(f"marina-check-canon/{CANON_VERSION} strict={int(bool(strict))}\n".encode())
    for i, r in enumerate(rows, start=1):
        c = canonical_row(r)
        canon.update((json.dumps([c[k] for k in CANON_FIELDS], ensure_ascii=False, separators=(",", ":")) + "\n").encode())
        date, code, side, scope = c["date"], c["code"], c["side"], c["scope"]
        market = c["market"] or None
        if market_prefix_for(market) != "cn" or scope in scopes("hk") or scope in scopes("us"):
            # A-share tick, band and fee composition must never be applied to another market's fill.
            findings.append(Finding(i, code, date, "MARKET_UNSUPPORTED",
                                    f"marina check covers China A-share fills only (market {market}, scope {scope})"))
            continue
        price, pc = _f(c["price"]), _f(c["prev_close"])
        try:
            dec = int(c["decimals"]) if c["decimals"] else None   # None → tick from the dataset
        except ValueError:
            dec = None; price = None
        if price is None or pc is None or side not in ("buy", "sell") or not date:
            findings.append(Finding(i, code, date, "ROW_INVALID",
                                    "need date, code, side (buy|sell), and finite numeric price and prev_close"))
            continue
        # tick: the instrument family's tick_size in force (or 10^-decimals when the row overrides rounding)
        tick = None
        if dec is not None:
            tick = 10.0 ** -dec
        else:
            try:
                tick = _agreed_tick(scope, date, market, strict)
            except RuleConflict as e:
                findings.append(Finding(i, code, date, "MARKET_REQUIRED", f"tick differs by exchange: {e}"))
            except KeyError:
                tick = None   # no tick recorded for this date (e.g. before 2006-07-01): cannot judge, not a finding
        if tick is not None and _off_tick(c["price"], tick):
            findings.append(Finding(i, code, date, "PRICE_OFF_TICK", f"price {c['price']} is not a multiple of tick {tick}"))
        try:
            band = limit_price(pc, scope, date, market=market, decimals=dec, strict=strict)
        except KeyError as e:
            findings.append(Finding(i, code, date, "RULE_MISSING", str(e)))
            band = None
        except ValueError as e:   # band rounds below one tick and the row carries no market: cannot judge
            findings.append(Finding(i, code, date, "MARKET_REQUIRED", str(e)))
            band = None
        if band is not None:
            up, dn = band
            if side == "buy" and price > up + 1e-9:
                findings.append(Finding(i, code, date, "LIMIT_BUY_ABOVE_UP", f"price {price} > limit_up {up}"))
            if side == "sell" and price < dn - 1e-9:
                findings.append(Finding(i, code, date, "LIMIT_SELL_BELOW_DOWN", f"price {price} < limit_down {dn}"))
            if not (dn - 1e-9 <= price <= up + 1e-9):
                findings.append(Finding(i, code, date, "PRICE_OUTSIDE_BAND", f"{price} not in [{dn}, {up}]"))
        fee, turnover = _f(c["fee"]), _f(c["turnover"])
        if fee is not None and turnover is not None:
            try:
                stat = statutory_fee_floor(turnover, side, date, market, strict=strict)
                if fee + 1e-6 < stat:
                    findings.append(Finding(i, code, date, "FEE_BELOW_STATUTORY",
                                            f"fee {fee:.2f} < statutory minimum {stat:.2f}"))
            except KeyError as e:
                findings.append(Finding(i, code, date, "RULE_MISSING", str(e)))
    dg = dataset_digest()
    ok = not findings
    stamp = hashlib.sha256((dg + "\n" + canon.hexdigest()).encode()).hexdigest() if ok else None
    counts: dict[str, int] = {}
    for f in findings:
        counts[f.check] = counts.get(f.check, 0) + 1
    return {
        "marina_rules_version": VERSION, "dataset_sha256": dg, "citation": citation(),
        "rows": len(rows), "findings": [asdict(f) for f in findings], "counts": counts,
        "rules_verified": ok,
        "stamp": (f"rules-verified@{VERSION}:{stamp[:32]}" if ok else None),
        "disclaimer": "Checks fills against price-limit and fee rules only. Not a statement about "
                      "look-ahead bias, survivorship, capacity, or statistical validity.",
    }


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__); return 0
    strict = "--strict" in argv
    path = [a for a in argv if not a.startswith("--")][0]
    with open(path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    out = check_rows(rows, strict=strict)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if out["rules_verified"] else 1


if __name__ == "__main__":
    sys.exit(main())
