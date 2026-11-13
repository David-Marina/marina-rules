"""``marina check`` — verify a fill log against the rules in force on each day.

Input: CSV with columns  date, code, side, price, prev_close, scope  [, market, fee, turnover, decimals]
                          [, board, st, listing_day_index, … other scope context keys]
  * price / prev_close   SAME PRICE BASIS: both unadjusted (as traded). ``prev_close`` is the exchange's reference
                price for the day's band — the previous close, or on an ex-rights / ex-dividend day the exchange's
                ex-rights reference price (除权除息参考价), never a back- or forward-adjusted close. A log whose
                ``price`` is adjusted and ``prev_close`` is not (or the reverse) is off by a constant factor per stock;
                see ``hints`` in the output.
  * side        buy | sell
  * market      XSHG | XSHE | BJSE …; needed where a rule differs by exchange (one-tick floor, B-share tick)
  * decimals    optional rounding override for the limit price; also used as the tick for PRICE_OFF_TICK
  * scope       a China A-share scope with a price-limit record (``--list-scopes`` prints them all from the registry:
                main_board, chinext, star, st_main, ipo_first5_main, …). When the cell is empty and the row carries
                scope context (columns named like the registry keys: ``board``, ``st`` or ``st_status``,
                ``listing_day_index``, ``issue_regime``, ``delisting_day_index`` …), the scope is chosen with
                ``marina_rules.equity.pick_scope`` from the registry's own asserts; without a ``board`` cell the board
                comes from ``board_for_code(code)`` (a code-prefix convenience, A-share stocks only). A row with
                neither scope nor context keeps the old default ``stock``.
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
  SCOPE_UNDETERMINED      the scope cell is empty and the row's context fits no scope, or several (never guessed);
                          no other check is run on the row

Counting: ``counts`` counts findings, not rows. An out-of-band fill on the violating side gets BOTH
PRICE_OUTSIDE_BAND and LIMIT_BUY_ABOVE_UP / LIMIT_SELL_BELOW_DOWN: the LIMIT_* rows are a subset of the
PRICE_OUTSIDE_BAND rows. ``rows_with_findings`` counts rows. ``summary`` groups rows, rows with findings and findings
by code per scope, per year and per side. ``--rows`` adds ``row_status``: one entry per input row, in order, with its
1-based ``row`` index (the same index findings carry), the scope used and its status (ok | within_tolerance |
findings + the list of codes), to join back to the log. Band findings carry numbers too: limit_up, limit_down,
violated_limit, excess (price minus the violated limit, absolute, signed) and excess_pct (percent of that limit).

Model-price logs (backtests fill at quote ± slippage, not on the exchange grid):
  --no-tick                    skip PRICE_OFF_TICK (and the tick lookup)
  --band-tolerance-pct X       a fill outside the band by at most X percent of the violated limit price is not a
                               finding; it is counted in ``within_tolerance`` and shown in ``row_status``. Default 0.
Either option makes the run RELAXED: ``options`` in the output states what was used, ``rules_verified`` is false and
no stamp is issued (``stamp_withheld`` says why), because a stamp certifies strict compliance. ``clean`` (and the exit
code 0) then means only "no findings under these options".

Hints (not findings, never affect the stamp): ``hints`` lists codes whose out-of-band rows look like a price-basis
mismatch — at least HINT_MIN_ROWS (3) rows of one code beyond the band by at least HINT_MIN_EXCESS_PCT (5%) of
the violated limit, all on the same side, whose price / prev_close ratios agree within a factor HINT_MAX_SPREAD
(1.5: max ratio / min ratio). Ordinary slippage stays far below 5%, and a single bad row never fires.

Output: JSON with findings, counts, the dataset digest, and a ``rules-verified`` stamp when a strict run (no
relaxation) has zero findings. The stamp is sha256(dataset_digest ‖ "\n" ‖ sha256(canonical fill log)) and can be recomputed by
anyone holding the same log and the same rules version. It commits to every input that can change a check.

Canonical fill log (``CANON_VERSION`` = 2): the UTF-8 bytes of
    marina-check-canon/2 strict=<0|1>\n
followed by one line per row, in input order:
    json.dumps([date, code, side, price, prev_close, scope, market, decimals, fee, turnover],
               ensure_ascii=False, separators=(",", ":")) + "\n"
where every field is the row's value as a string with surrounding whitespace stripped ("" when absent), except
date (first 10 characters), side (lower-cased) and scope (the scope chosen from context when derived, else default
"stock" when absent) — exactly the values the checks used. Changing any of these fields, the row order or the strict flag changes the stamp. It says only that fills respect the rules in this
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
from .equity import board_for_code, checkable_scopes, context_keys, equity_scopes, parse_context_value, pick_scope

CANON_VERSION = 2
CANON_FIELDS = ("date", "code", "side", "price", "prev_close", "scope", "market", "decimals", "fee", "turnover")
BAND_CHECKS = ("LIMIT_BUY_ABOVE_UP", "LIMIT_SELL_BELOW_DOWN", "PRICE_OUTSIDE_BAND")
HINT_MIN_ROWS = 3            # rows of one code before a price-basis hint is given
HINT_MIN_EXCESS_PCT = 5.0    # each row beyond the violated limit by at least this percent of it
HINT_MAX_SPREAD = 1.5        # max(price / prev_close) / min(price / prev_close) over those rows
CONTEXT_ALIASES = {"st": "st_status"}


@dataclass
class Finding:
    row: int
    code: str
    date: str
    check: str
    detail: str


def _finding(f: Finding, extra: dict | None = None) -> dict:
    d = asdict(f)
    if extra:
        d.update(extra)
    return d


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


def _row_context(r: dict) -> dict:
    """Non-empty scope-context cells of a row, keyed by registry name (``st`` → ``st_status``), as written."""
    keys = set(context_keys())
    out = {}
    for k, v in r.items():
        if k is None:
            continue
        name = CONTEXT_ALIASES.get(str(k).strip(), str(k).strip())
        if name in keys and _s(v) != "":
            out[name] = _s(v)
    return out


def derive_scope(r: dict, date: str) -> tuple[str | None, str]:
    """(scope, reason) for a row whose scope cell is empty but which carries scope context; scope None = undetermined.

    Board comes from the ``board`` cell, else from ``board_for_code(code)``. Everything else must be in the row."""
    raw = _row_context(r)
    ctx = {}
    try:
        for k, v in raw.items():
            ctx[k] = parse_context_value(k, v)
    except ValueError as e:
        return None, str(e)
    if "board" not in ctx:
        bm = board_for_code(_s(r.get("code")))
        if bm is None:
            return None, f"no board given and code {_s(r.get('code'))!r} is not a recognised A-share stock code"
        ctx["board"] = bm[0]
    res = pick_scope(date, **ctx)
    return res["scope"], res["reason"]


def _validate_tolerance(x) -> float:
    try:
        v = float(x)
    except (TypeError, ValueError):
        raise ValueError(f"band_tolerance_pct must be a number, got {x!r}") from None
    if not math.isfinite(v) or v < 0:
        raise ValueError(f"band_tolerance_pct must be finite and >= 0, got {x!r}")
    return v


def _bump(group: dict, key: str, row_checks: list, tol: bool) -> None:
    g = group.setdefault(key, {"rows": 0, "rows_with_findings": 0, "within_tolerance": 0, "findings": {}})
    g["rows"] += 1
    g["rows_with_findings"] += bool(row_checks)
    g["within_tolerance"] += tol
    for c in row_checks:
        g["findings"][c] = g["findings"].get(c, 0) + 1


def _basis_hints(out_of_band: dict) -> list:
    """Price-basis hints from {code: [(row, ratio, side_of_band, excess_pct)]} (see module docstring)."""
    hints = []
    for code, items in out_of_band.items():
        far = [it for it in items if abs(it[3]) >= HINT_MIN_EXCESS_PCT - 1e-9]
        if len(far) < HINT_MIN_ROWS or len({it[2] for it in far}) != 1:
            continue
        ratios = sorted(it[1] for it in far)
        if ratios[0] <= 0 or ratios[-1] / ratios[0] > HINT_MAX_SPREAD:
            continue
        n = len(ratios)
        med = ratios[n // 2] if n % 2 else (ratios[n // 2 - 1] + ratios[n // 2]) / 2
        hints.append({"hint": "PRICE_BASIS_MISMATCH?", "code": code, "rows": n, "typical_factor": round(med, 4),
                      "row_indexes": [it[0] for it in far],
                      "message": f"{n} rows of {code} are {'above' if far[0][2] == 'up' else 'below'} the band by "
                                 f">= {HINT_MIN_EXCESS_PCT:g}% with price / prev_close ≈ {med:.4f}: this may indicate that "
                                 "price and prev_close are on different price bases (adjusted vs unadjusted). "
                                 "A hint, not a finding."})
    return hints


def check_rows(rows: list[dict], strict: bool = False, *, tick: bool = True, band_tolerance_pct: float = 0.0,
               per_row: bool = False) -> dict:
    """Check fills (see module docstring). ``tick=False`` skips PRICE_OFF_TICK; ``band_tolerance_pct`` > 0 lets a
    fill outside the band by at most that percent of the violated limit pass (counted in ``within_tolerance``).
    Either makes the run relaxed: no stamp. ``per_row=True`` adds ``row_status``."""
    tol = _validate_tolerance(band_tolerance_pct)
    relaxed = (not tick) or tol > 0
    findings: list[dict] = []
    foreign = set(scopes("hk")) | set(scopes("us"))
    row_status: list[dict] = []
    summary: dict = {"by_scope": {}, "by_year": {}, "by_side": {}}
    out_of_band: dict = {}
    n_flagged = n_tol = 0
    canon = hashlib.sha256(f"marina-check-canon/{CANON_VERSION} strict={int(bool(strict))}\n".encode())
    for i, r in enumerate(rows, start=1):
        c = canonical_row(r)
        row_f: list[dict] = []
        within = None
        derived = False
        if not _s(r.get("scope")) and _row_context(r):
            sc, why = derive_scope(r, c["date"])
            derived = True
            if sc is None:
                row_f.append(_finding(Finding(i, c["code"], c["date"], "SCOPE_UNDETERMINED", why)))
            else:
                c["scope"] = sc
        canon.update((json.dumps([c[k] for k in CANON_FIELDS], ensure_ascii=False, separators=(",", ":")) + "\n").encode())
        date, code, side, scope = c["date"], c["code"], c["side"], c["scope"]
        if not row_f:
            within = _check_one(i, c, strict, tick, tol, row_f, foreign, out_of_band)
        findings.extend(row_f)
        checks = [f["check"] for f in row_f]
        n_flagged += bool(checks)
        n_tol += within is not None
        used = "undetermined" if derived and checks and checks[0] == "SCOPE_UNDETERMINED" else scope
        for grp, key in (("by_scope", used), ("by_year", date[:4] or "unknown"), ("by_side", side or "unknown")):
            _bump(summary[grp], key, checks, within is not None)
        if per_row:
            st = {"row": i, "scope": used,
                  "status": "findings" if checks else ("within_tolerance" if within is not None else "ok")}
            if checks:
                st["checks"] = checks
            if within is not None:
                st["within_tolerance"] = within
            if derived:
                st["scope_derived"] = True
            row_status.append(st)
    dg = dataset_digest()
    clean = not findings
    ok = clean and not relaxed
    stamp = hashlib.sha256((dg + "\n" + canon.hexdigest()).encode()).hexdigest() if ok else None
    counts: dict[str, int] = {}
    for f in findings:
        counts[f["check"]] = counts.get(f["check"], 0) + 1
    out = {
        "marina_rules_version": VERSION, "dataset_sha256": dg, "citation": citation(),
        "rows": len(rows), "findings": findings, "counts": counts,
        "rules_verified": ok,
        "stamp": (f"rules-verified@{VERSION}:{stamp[:32]}" if ok else None),
        "disclaimer": "Checks fills against price-limit and fee rules only. Not a statement about "
                      "look-ahead bias, survivorship, capacity, or statistical validity.",
        "options": {"strict": bool(strict), "tick": bool(tick), "band_tolerance_pct": tol},
        "relaxed": relaxed, "clean": clean,
        "rows_with_findings": n_flagged, "within_tolerance": n_tol,
        "summary": summary,
        "hints": _basis_hints(out_of_band),
    }
    if relaxed:
        out["stamp_withheld"] = ("relaxed run (" + ", ".join(
            ([] if tick else ["no tick check"]) + ([f"band tolerance {tol:g}%"] if tol > 0 else [])) +
            "): a rules-verified stamp is issued only for a strict run")
    if per_row:
        out["row_status"] = row_status
    return out


def _check_one(i: int, c: dict, strict: bool, tick_on: bool, tol: float, row_f: list, foreign: set,
               out_of_band: dict):
    """Run the checks on one canonical row, appending finding dicts to ``row_f``.
    Returns the band excess (dict) when the row was outside the band but within tolerance, else None."""
    date, code, side, scope = c["date"], c["code"], c["side"], c["scope"]
    add = lambda check, detail, extra=None: row_f.append(_finding(Finding(i, code, date, check, detail), extra))
    market = c["market"] or None
    if market_prefix_for(market) != "cn" or scope in foreign:
        # A-share tick, band and fee composition must never be applied to another market's fill.
        add("MARKET_UNSUPPORTED", f"marina check covers China A-share fills only (market {market}, scope {scope})")
        return None
    price, pc = _f(c["price"]), _f(c["prev_close"])
    try:
        dec = int(c["decimals"]) if c["decimals"] else None   # None → tick from the dataset
    except ValueError:
        dec = None; price = None
    if price is None or pc is None or side not in ("buy", "sell") or not date:
        add("ROW_INVALID", "need date, code, side (buy|sell), and finite numeric price and prev_close")
        return None
    if tick_on:
        # tick: the instrument family's tick_size in force (or 10^-decimals when the row overrides rounding)
        tick = None
        if dec is not None:
            tick = 10.0 ** -dec
        else:
            try:
                tick = _agreed_tick(scope, date, market, strict)
            except RuleConflict as e:
                add("MARKET_REQUIRED", f"tick differs by exchange: {e}")
            except KeyError:
                tick = None   # no tick recorded for this date (e.g. before 2006-07-01): cannot judge, not a finding
        if tick is not None and _off_tick(c["price"], tick):
            add("PRICE_OFF_TICK", f"price {c['price']} is not a multiple of tick {tick}")
    try:
        band = limit_price(pc, scope, date, market=market, decimals=dec, strict=strict)
    except KeyError as e:
        add("RULE_MISSING", str(e))
        band = None
    except ValueError as e:   # band rounds below one tick and the row carries no market: cannot judge
        add("MARKET_REQUIRED", str(e))
        band = None
    within = None
    if band is not None:
        up, dn = band
        if not (dn - 1e-9 <= price <= up + 1e-9):
            lim, which = (up, "limit_up") if price > up else (dn, "limit_down")
            excess = price - lim
            pct = excess / lim * 100 if lim else math.inf
            nums = {"limit_up": up, "limit_down": dn, "violated_limit": which,
                    "excess": round(excess, 6), "excess_pct": round(pct, 6) if math.isfinite(pct) else None}
            if pc > 0:
                out_of_band.setdefault(code, []).append((i, price / pc, "up" if which == "limit_up" else "down", pct))
            if tol > 0 and abs(pct) <= tol + 1e-9:
                within = nums
            else:
                if side == "buy" and price > up + 1e-9:
                    add("LIMIT_BUY_ABOVE_UP", f"price {price} > limit_up {up}", nums)
                if side == "sell" and price < dn - 1e-9:
                    add("LIMIT_SELL_BELOW_DOWN", f"price {price} < limit_down {dn}", nums)
                add("PRICE_OUTSIDE_BAND", f"{price} not in [{dn}, {up}]", nums)
    fee, turnover = _f(c["fee"]), _f(c["turnover"])
    if fee is not None and turnover is not None:
        try:
            stat = statutory_fee_floor(turnover, side, date, market, strict=strict)
            if fee + 1e-6 < stat:
                add("FEE_BELOW_STATUTORY", f"fee {fee:.2f} < statutory minimum {stat:.2f}")
        except KeyError as e:
            add("RULE_MISSING", str(e))
    return within


def scope_help() -> str:
    """The A-share scopes the checker accepts, generated from the registry (printed by --help / --list-scopes)."""
    eq = set(equity_scopes())
    lines = ["Scopes with a price-limit record (from data/cn/scopes.yaml; * = can be derived from context):"]
    for k, d in checkable_scopes().items():
        lines.append(f"  {'*' if k in eq else ' '} {k:<28} {d}")
    lines.append("Scope context columns read when the scope cell is empty: " +
                 ", ".join(sorted(set(context_keys()) | set(CONTEXT_ALIASES))) + " (st = st_status)")
    return "\n".join(lines)


USAGE = ("usage: marina-check FILLS.csv [--strict] [--no-tick] [--band-tolerance-pct X] [--rows]\n"
         "       marina-check --list-scopes")


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] in ("-h", "--help") or "--help" in argv or "-h" in argv:
        print(USAGE + "\n\n" + __doc__ + "\n" + scope_help()); return 0
    if "--list-scopes" in argv:
        print(scope_help()); return 0
    tick = True
    strict, tol, per_row, paths = False, 0.0, False, []
    it = iter(argv)
    for a in it:
        if a == "--strict":
            strict = True
        elif a == "--no-tick":
            tick = False
        elif a == "--rows":
            per_row = True
        elif a == "--band-tolerance-pct" or a.startswith("--band-tolerance-pct="):
            v = a.split("=", 1)[1] if "=" in a else next(it, None)
            try:
                tol = _validate_tolerance(v)
            except ValueError as e:
                print(f"marina-check: {e}\n{USAGE}", file=sys.stderr); return 2
        elif a.startswith("--"):
            print(f"marina-check: unknown option {a}\n{USAGE}", file=sys.stderr); return 2
        else:
            paths.append(a)
    if len(paths) != 1:
        print(USAGE, file=sys.stderr); return 2
    with open(paths[0], newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    out = check_rows(rows, strict=strict, tick=tick, band_tolerance_pct=tol, per_row=per_row)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if out["clean"] else 1


if __name__ == "__main__":
    sys.exit(main())
