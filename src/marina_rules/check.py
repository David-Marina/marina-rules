"""``marina check`` — verify a fill log against the rules in force on each day.

Input: CSV with columns  date, code, side, price, prev_close, scope  [, market, fee, turnover, decimals]
                          [, board, st, listing_day_index, list_date, … other scope context keys]
                          [, day_high, day_low]
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
  * list_date   optional listing date (YYYY-MM-DD or YYYYMMDD), used only when ``listing_day_index`` is empty. Marina
                has no trading calendar and never computes a trading-day index: a trade more than
                LIST_DATE_MARGIN_DAYS (60) calendar days after ``list_date`` is past every listing window (the
                registry's windows end within 5 trading days; 60 days exceeds that even across a three-week market
                closure); a trade within the margin stays SCOPE_UNDETERMINED unless ``listing_day_index`` is given.
                A stock suspended for weeks inside its own first five trading days needs ``listing_day_index``.
  * day_high / day_low   optional, SAME PRICE BASIS as ``price``: the day's traded high and low. When both are given,
                the fill price must lie within them (PRICE_OUTSIDE_DAY_RANGE). This is a DATA-CONSISTENCY check, not
                an exchange rule: it catches a price-basis mismatch that stays inside a wide band. It says the fill price and the
                day's range disagree, not which of the two is wrong.
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
  PRICE_OUTSIDE_DAY_RANGE price outside [day_low, day_high] of the row (data consistency, not an exchange rule)
  DAY_RANGE_INVALID       day_high / day_low given but not both finite, positive and day_low <= day_high

Counting: ``counts`` counts findings, not rows. An out-of-band fill on the violating side gets BOTH
PRICE_OUTSIDE_BAND and LIMIT_BUY_ABOVE_UP / LIMIT_SELL_BELOW_DOWN: the LIMIT_* rows are a subset of the
PRICE_OUTSIDE_BAND rows. ``rows_with_findings`` counts rows. ``summary`` groups rows, rows with findings and findings
by code per scope, per year and per side. ``--rows`` adds ``row_status``: one entry per input row, in order, with its
1-based ``row`` index (the same index findings carry), the scope used and its status (ok | within_tolerance |
findings + the list of codes), to join back to the log. Band findings carry numbers too: limit_up, limit_down,
violated_limit, excess (price minus the violated limit, absolute, signed) and excess_pct (percent of that limit);
day-range findings carry day_high, day_low, violated_bound, excess and excess_pct the same way.
``summary.by_code`` lists the top TOP_CODES (20; ``--top-codes N``) codes by rows with findings (then rows within
tolerance), each with rows, rows_with_findings, within_tolerance and median_excess_pct (median |excess_pct| over the
code's rows outside the band or day range, flagged or tolerated); ``summary.codes_with_findings`` counts all such
codes. ``summary.within_tolerance_excess`` buckets every tolerated excess by |excess_pct|: <=0.1%, <=0.25%, <=0.5%,
<=1%, >1% (TOLERANCE_BUCKETS).

Model-price logs (backtests fill at quote ± slippage, not on the exchange grid):
  --no-tick                    skip PRICE_OFF_TICK (and the tick lookup)
  --band-tolerance-pct X       a fill outside the band (or the day's range) by at most X percent of the violated
                               bound is not a finding; it is counted in ``within_tolerance`` and shown in
                               ``row_status``. Default 0.
  --assume-seasoned            a row whose scope is derived and that has neither ``listing_day_index`` nor
                               ``list_date`` is treated as past every listing window; ``assumed_seasoned`` counts the
                               rows whose scope depended on it and ``row_status`` marks them.
Any of these makes the run RELAXED: ``options`` in the output states what was used, ``rules_verified`` is false and
no stamp is issued (``stamp_withheld`` says why), because a stamp certifies strict compliance.
The tolerance also absorbs small price-basis errors: rows of an affected stock that exceed a limit by less than the
tolerance pass. Read a relaxed run together with ``hints`` and ``summary.by_code``.

Exit codes: 0 = no findings under the options used (``clean``; in a relaxed run this is NOT a verification),
1 = findings, 2 = usage error (bad option, unreadable file). Scripts should read ``relaxed``, ``within_tolerance``
and ``assumed_seasoned`` from the JSON rather than rely on the exit code alone.

Tracking (not findings, never affect the stamp or the exit code): ``tracking`` counts the checked rows dated after
the ``tracked_through`` date of their market and scope (``rows_beyond_tracked_through``) and the rows whose market is not
tracked at all (``rows_untracked``; a row without a market counts here), and lists ``tracked_through`` per market seen.
Such rows were checked against open-ended rules carried forward past the date the official sources were last checked
for changes (docs/SCHEMA.md "Tracking registry"). Rows reported MARKET_UNSUPPORTED or SCOPE_UNDETERMINED are not counted.

Hints (not findings, never affect the stamp): ``hints`` lists codes whose rows outside the band (source ``band``,
ratio = price / prev_close) or outside the day's range (source ``day_range``, ratio = price / violated day bound)
look like a price-basis mismatch, judged per code and source, whether the rows were flagged or tolerated:
  few_far          >= HINT_MIN_ROWS (3) rows beyond the bound by >= HINT_MIN_EXCESS_PCT (5%), all on one side;
  many_consistent  >= HINT_MANY_ROWS (20) rows on one side whose MEDIAN excess is >= HINT_MIN_MEDIAN_EXCESS_PCT (1.5%)
                   — catches small factors (1.05: the excess spreads from 0 to ~5%, median ~2.5%);
both also require the ratios to agree within a factor HINT_MAX_SPREAD (1.5, max / min). Slippage puts fills a few
tenths of a percent past a limit, so its median stays well under 1.5% however many rows there are, and one bad row
never fires. A hint can also mean a wrong scope (e.g. a 10%-band stock labelled with a 5% scope). Each hint lists the
first HINT_ROW_INDEXES (20) row indexes (all with ``--rows``) and the total in ``rows``.

Output: JSON with findings, counts, the dataset digest, and a ``rules-verified`` stamp when a strict run (no
relaxation) has zero findings. The stamp is sha256(dataset_digest ‖ "\n" ‖ sha256(canonical fill log)) and can be recomputed by
anyone holding the same log and the same rules version. It commits to every input that can change a check.

Canonical fill log (``CANON_VERSION`` = 2): the UTF-8 bytes of
    marina-check-canon/2 strict=<0|1>\n
followed by one line per row, in input order:
    json.dumps([date, code, side, price, prev_close, scope, market, decimals, fee, turnover],
               ensure_ascii=False, separators=(",", ":")) + "\n"
A log in which any row has a non-empty day_high or day_low instead starts with
    marina-check-canon/3 strict=<0|1> day_range=1\n
and every row's list ends with day_high, day_low. Logs without them hash exactly as before.
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
               tracked_through, VERSION, _agreed_tick)
from .equity import (LIST_DATE_MARGIN_DAYS, board_for_code, checkable_scopes, context_keys, equity_scopes,
                     listing_index_from_list_date, parse_context_value, pick_scope, seasoned_listing_day_index)

CANON_VERSION = 2
CANON_FIELDS = ("date", "code", "side", "price", "prev_close", "scope", "market", "decimals", "fee", "turnover")
BAND_CHECKS = ("LIMIT_BUY_ABOVE_UP", "LIMIT_SELL_BELOW_DOWN", "PRICE_OUTSIDE_BAND")
DAY_RANGE_FIELDS = ("day_high", "day_low")
# Price-basis hint (see the module docstring). Two ways to fire, both per (code, source):
HINT_MIN_ROWS = 3                  # few_far: at least this many rows …
HINT_MIN_EXCESS_PCT = 5.0          # … each beyond the violated bound by at least this percent of it, all one side
HINT_MANY_ROWS = 20                # many_consistent: at least this many rows on one side …
HINT_MIN_MEDIAN_EXCESS_PCT = 1.5   # … whose median excess is at least this percent of the bound
HINT_MAX_SPREAD = 1.5              # both: max(price / reference) / min(price / reference) over the rows
HINT_ROW_INDEXES = 20              # row indexes listed per hint without --rows
TOP_CODES = 20                     # default length of summary.by_code
TOLERANCE_BUCKETS = (0.1, 0.25, 0.5, 1.0)   # summary.within_tolerance_excess: |excess_pct| <= each, then above
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
    """Non-empty scope-context cells of a row (registry keys, ``st`` → ``st_status``, plus ``list_date``), as written."""
    keys = set(context_keys()) | {"list_date"}
    out = {}
    for k, v in r.items():
        if k is None:
            continue
        name = CONTEXT_ALIASES.get(str(k).strip(), str(k).strip())
        if name in keys and _s(v) != "":
            out[name] = _s(v)
    return out


def derive_scope(r: dict, date: str, assume_seasoned: bool = False) -> tuple:
    """(scope, reason, relied_on_assumption) for a row whose scope cell is empty but which carries scope context;
    scope None = undetermined.

    Board comes from the ``board`` cell, else from ``board_for_code(code)``. ``listing_day_index`` comes from its cell,
    else from ``list_date`` when the trade is more than ``LIST_DATE_MARGIN_DAYS`` calendar days after it, else — only
    with ``assume_seasoned`` and only when the row has neither — the registry's post-window value
    (``seasoned_listing_day_index()``). ``relied_on_assumption`` is True when that assumption decided the scope."""
    raw = _row_context(r)
    list_date = raw.pop("list_date", None)
    ctx = {}
    try:
        for k, v in raw.items():
            ctx[k] = parse_context_value(k, v)
    except ValueError as e:
        return None, str(e), False
    if "board" not in ctx:
        bm = board_for_code(_s(r.get("code")))
        if bm is None:
            return None, f"no board given and code {_s(r.get('code'))!r} is not a recognised A-share stock code", False
        ctx["board"] = bm[0]
    note = ""
    if "listing_day_index" not in ctx and list_date is not None:
        idx, why = listing_index_from_list_date(date, list_date)
        if idx is None:
            res = pick_scope(date, **ctx)      # a scope that needs no listing index may still fit
            return res["scope"], f"{res['reason']}; {why}" if res["scope"] is None else res["reason"], False
        ctx["listing_day_index"] = idx
        note = f" (listing_day_index ≥ {idx} from list_date: {why})"
    res = pick_scope(date, **ctx)
    if res["scope"] is None and assume_seasoned and "listing_day_index" not in ctx and list_date is None:
        res2 = pick_scope(date, **dict(ctx, listing_day_index=seasoned_listing_day_index()))
        if res2["scope"] is not None:
            return res2["scope"], res2["reason"] + " (--assume-seasoned: listing window assumed past)", True
    return res["scope"], res["reason"] + note, False


def _validate_tolerance(x) -> float:
    try:
        v = float(x)
    except (TypeError, ValueError):
        raise ValueError(f"band_tolerance_pct must be a number, got {x!r}") from None
    if not math.isfinite(v) or v < 0:
        raise ValueError(f"band_tolerance_pct must be finite and >= 0, got {x!r}")
    return v


def _median(xs: list):
    if not xs:
        return None
    ys = sorted(xs)
    n = len(ys)
    return ys[n // 2] if n % 2 else (ys[n // 2 - 1] + ys[n // 2]) / 2


def _bump(group: dict, key: str, row_checks: list, tol: bool) -> None:
    g = group.setdefault(key, {"rows": 0, "rows_with_findings": 0, "within_tolerance": 0, "findings": {}})
    g["rows"] += 1
    g["rows_with_findings"] += bool(row_checks)
    g["within_tolerance"] += tol
    for c in row_checks:
        g["findings"][c] = g["findings"].get(c, 0) + 1


def _bucket(pct: float) -> str:
    a = abs(pct)
    for b in TOLERANCE_BUCKETS:
        if a <= b + 1e-12:
            return f"<={b:g}%"
    return f">{TOLERANCE_BUCKETS[-1]:g}%"


def _basis_hints(out_of_range: dict, full: bool) -> list:
    """Price-basis hints from {(code, source): [(row, ratio, side, excess_pct)]} (see module docstring)."""
    hints = []
    for (code, source), items in out_of_range.items():
        rule = None
        far = [it for it in items if abs(it[3]) >= HINT_MIN_EXCESS_PCT - 1e-9]
        if len(far) >= HINT_MIN_ROWS and len({it[2] for it in far}) == 1 and _spread_ok(far):
            rule, sel = "few_far", far
        else:
            up = [it for it in items if it[2] == "up"]
            dn = [it for it in items if it[2] == "down"]
            side = up if len(up) >= len(dn) else dn
            if (len(side) >= HINT_MANY_ROWS and _median([abs(it[3]) for it in side]) >= HINT_MIN_MEDIAN_EXCESS_PCT - 1e-9
                    and _spread_ok(side)):
                rule, sel = "many_consistent", side
        if rule is None:
            continue
        n = len(sel)
        med = _median([it[1] for it in sel])
        mex = _median([abs(it[3]) for it in sel])
        idx = [it[0] for it in sel]
        ref = "prev_close" if source == "band" else "the day's high / low"
        where = "the band" if source == "band" else "the day's range"
        hints.append({"hint": "PRICE_BASIS_MISMATCH?", "code": code, "source": source, "rule": rule, "rows": n,
                      "median_excess_pct": round(mex, 4), "typical_factor": round(med, 4),
                      "row_indexes": idx if full else idx[:HINT_ROW_INDEXES],
                      "row_indexes_truncated": (not full) and n > HINT_ROW_INDEXES,
                      "message": f"{n} rows of {code} are {'above' if sel[0][2] == 'up' else 'below'} {where} by a median "
                                 f"{mex:.2f}% with price / {ref} ≈ {med:.4f}: this may indicate that price and "
                                 f"{'prev_close' if source == 'band' else 'day_high / day_low'} are on different price "
                                 "bases (adjusted vs unadjusted, or an ex-rights event applied with the wrong factor), or that "
                                 "the scope is wrong. A hint, not a finding."})
    return hints


def _spread_ok(items: list) -> bool:
    ratios = [it[1] for it in items]
    return min(ratios) > 0 and max(ratios) / min(ratios) <= HINT_MAX_SPREAD


def _uses_day_range(rows: list) -> bool:
    return any(_s(r.get(k)) != "" for r in rows for k in DAY_RANGE_FIELDS)


def check_rows(rows: list[dict], strict: bool = False, *, tick: bool = True, band_tolerance_pct: float = 0.0,
               per_row: bool = False, assume_seasoned: bool = False, top_codes: int = TOP_CODES) -> dict:
    """Check fills (see module docstring). ``tick=False`` skips PRICE_OFF_TICK; ``band_tolerance_pct`` > 0 lets a
    fill outside the band (or the day's range) by at most that percent of the violated bound pass (counted in
    ``within_tolerance``); ``assume_seasoned`` treats rows without listing information as past the listing window.
    Any of these makes the run relaxed: no stamp. ``per_row=True`` adds ``row_status`` and full hint row lists;
    ``top_codes`` sets the length of ``summary.by_code``."""
    tol = _validate_tolerance(band_tolerance_pct)
    if isinstance(top_codes, bool) or not isinstance(top_codes, int) or top_codes < 0:
        raise ValueError(f"top_codes must be an integer >= 0, got {top_codes!r}")
    relaxed = (not tick) or tol > 0 or bool(assume_seasoned)
    day_range = _uses_day_range(rows)
    fields = CANON_FIELDS + (DAY_RANGE_FIELDS if day_range else ())
    findings: list[dict] = []
    foreign = set(scopes("hk")) | set(scopes("us"))
    row_status: list[dict] = []
    summary: dict = {"by_scope": {}, "by_year": {}, "by_side": {}}
    per_code: dict = {}
    buckets: dict = {}
    out_of_range: dict = {}
    n_flagged = n_tol = n_assumed = 0
    trk_beyond = trk_untracked = 0
    trk_dates: dict = {}
    head = (f"marina-check-canon/3 strict={int(bool(strict))} day_range=1\n" if day_range
            else f"marina-check-canon/{CANON_VERSION} strict={int(bool(strict))}\n")
    canon = hashlib.sha256(head.encode())
    for i, r in enumerate(rows, start=1):
        c = canonical_row(r)
        for k in DAY_RANGE_FIELDS:
            c[k] = _s(r.get(k))
        row_f: list[dict] = []
        within: list = []
        derived = assumed = False
        if not _s(r.get("scope")) and _row_context(r):
            sc, why, assumed = derive_scope(r, c["date"], assume_seasoned)
            derived = True
            if sc is None:
                row_f.append(_finding(Finding(i, c["code"], c["date"], "SCOPE_UNDETERMINED", why)))
            else:
                c["scope"] = sc
        canon.update((json.dumps([c[k] for k in fields], ensure_ascii=False, separators=(",", ":")) + "\n").encode())
        date, code, side, scope = c["date"], c["code"], c["side"], c["scope"]
        excesses: list = []
        if not row_f:
            _check_one(i, c, strict, tick, tol, row_f, within, foreign, out_of_range, excesses)
            if date and not any(f["check"] == "MARKET_UNSUPPORTED" for f in row_f):
                mk = c["market"] or None
                key = (mk, scope)
                if key not in trk_dates:
                    trk_dates[key] = tracked_through(mk, scope)
                tt = trk_dates[key]
                if tt is None:
                    trk_untracked += 1
                elif date > tt:
                    trk_beyond += 1
        findings.extend(row_f)
        checks = [f["check"] for f in row_f]
        n_flagged += bool(checks)
        n_tol += bool(within)
        n_assumed += assumed
        for w in within:
            b = _bucket(w["excess_pct"])
            buckets[b] = buckets.get(b, 0) + 1
        used = "undetermined" if derived and checks and checks[0] == "SCOPE_UNDETERMINED" else scope
        for grp, key in (("by_scope", used), ("by_year", date[:4] or "unknown"), ("by_side", side or "unknown")):
            _bump(summary[grp], key, checks, bool(within))
        pc_ = per_code.setdefault(code, {"rows": 0, "rows_with_findings": 0, "within_tolerance": 0, "_ex": []})
        pc_["rows"] += 1
        pc_["rows_with_findings"] += bool(checks)
        pc_["within_tolerance"] += bool(within)
        pc_["_ex"].extend(excesses)
        if per_row:
            st = {"row": i, "scope": used,
                  "status": "findings" if checks else ("within_tolerance" if within else "ok")}
            if checks:
                st["checks"] = checks
            if within:
                st["within_tolerance"] = within
            if derived:
                st["scope_derived"] = True
            if assumed:
                st["assumed_seasoned"] = True
            row_status.append(st)
    dg = dataset_digest()
    clean = not findings
    ok = clean and not relaxed
    stamp = hashlib.sha256((dg + "\n" + canon.hexdigest()).encode()).hexdigest() if ok else None
    counts: dict[str, int] = {}
    for f in findings:
        counts[f["check"]] = counts.get(f["check"], 0) + 1
    ranked = sorted(((k, v) for k, v in per_code.items() if v["rows_with_findings"] or v["within_tolerance"]),
                    key=lambda kv: (-kv[1]["rows_with_findings"], -kv[1]["within_tolerance"], kv[0]))
    summary["by_code"] = [{"code": k, "rows": v["rows"], "rows_with_findings": v["rows_with_findings"],
                           "within_tolerance": v["within_tolerance"],
                           "median_excess_pct": (round(_median(v["_ex"]), 4) if v["_ex"] else None)}
                          for k, v in ranked[:top_codes]]
    summary["codes_with_findings"] = sum(1 for v in per_code.values() if v["rows_with_findings"])
    order = [f"<={b:g}%" for b in TOLERANCE_BUCKETS] + [f">{TOLERANCE_BUCKETS[-1]:g}%"]
    summary["within_tolerance_excess"] = {b: buckets.get(b, 0) for b in order}
    out = {
        "marina_rules_version": VERSION, "dataset_sha256": dg, "citation": citation(),
        "rows": len(rows), "findings": findings, "counts": counts,
        "rules_verified": ok,
        "stamp": (f"rules-verified@{VERSION}:{stamp[:32]}" if ok else None),
        "disclaimer": "Checks fills against price-limit and fee rules only. Not a statement about "
                      "look-ahead bias, survivorship, capacity, or statistical validity.",
        "options": {"strict": bool(strict), "tick": bool(tick), "band_tolerance_pct": tol,
                    "assume_seasoned": bool(assume_seasoned)},
        "relaxed": relaxed, "clean": clean,
        "rows_with_findings": n_flagged, "within_tolerance": n_tol, "assumed_seasoned": n_assumed,
        "summary": summary,
        "hints": _basis_hints(out_of_range, per_row),
        "tracking": {"rows_beyond_tracked_through": trk_beyond, "rows_untracked": trk_untracked,
                     "tracked_through": {m: tracked_through(m or None) for m in sorted({k[0] or "" for k in trk_dates})},
                     "note": "not findings: a row dated after its market's tracked_through, or on an untracked market, may "
                             "rest on rules carried forward past the date the official sources were last checked"},
    }
    if relaxed:
        out["stamp_withheld"] = ("relaxed run (" + ", ".join(
            ([] if tick else ["no tick check"]) + ([f"band tolerance {tol:g}%"] if tol > 0 else []) +
            (["assume seasoned"] if assume_seasoned else [])) +
            "): a rules-verified stamp is issued only for a strict run")
    if per_row:
        out["row_status"] = row_status
    return out


def _excess(price: float, hi: float, lo: float) -> tuple:
    """(violated 'up'|'down', bound, excess, excess_pct) for a price outside [lo, hi]."""
    bound, which = (hi, "up") if price > hi else (lo, "down")
    excess = price - bound
    pct = excess / bound * 100 if bound else math.inf
    return which, bound, excess, pct


def _check_one(i: int, c: dict, strict: bool, tick_on: bool, tol: float, row_f: list, within: list, foreign: set,
               out_of_range: dict, excesses: list) -> None:
    """Run the checks on one canonical row, appending finding dicts to ``row_f`` and tolerated excesses to
    ``within``."""
    date, code, side, scope = c["date"], c["code"], c["side"], c["scope"]
    add = lambda check, detail, extra=None: row_f.append(_finding(Finding(i, code, date, check, detail), extra))
    market = c["market"] or None
    if market_prefix_for(market) != "cn" or scope in foreign:
        # A-share tick, band and fee composition must never be applied to another market's fill.
        add("MARKET_UNSUPPORTED", f"marina check covers China A-share fills only (market {market}, scope {scope})")
        return
    price, pc = _f(c["price"]), _f(c["prev_close"])
    try:
        dec = int(c["decimals"]) if c["decimals"] else None   # None → tick from the dataset
    except ValueError:
        dec = None; price = None
    if price is None or pc is None or side not in ("buy", "sell") or not date:
        add("ROW_INVALID", "need date, code, side (buy|sell), and finite numeric price and prev_close")
        return
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
    if band is not None:
        up, dn = band
        if not (dn - 1e-9 <= price <= up + 1e-9):
            which, lim, excess, pct = _excess(price, up, dn)
            nums = {"limit_up": up, "limit_down": dn, "violated_limit": "limit_" + which,
                    "excess": round(excess, 6), "excess_pct": round(pct, 6) if math.isfinite(pct) else None}
            if pc > 0:
                out_of_range.setdefault((code, "band"), []).append((i, price / pc, which, pct))
            if math.isfinite(pct):
                excesses.append(abs(pct))
            if tol > 0 and abs(pct) <= tol + 1e-9:
                within.append(dict(check="PRICE_OUTSIDE_BAND", **nums))
            else:
                if side == "buy" and price > up + 1e-9:
                    add("LIMIT_BUY_ABOVE_UP", f"price {price} > limit_up {up}", nums)
                if side == "sell" and price < dn - 1e-9:
                    add("LIMIT_SELL_BELOW_DOWN", f"price {price} < limit_down {dn}", nums)
                add("PRICE_OUTSIDE_BAND", f"{price} not in [{dn}, {up}]", nums)
    if c.get("day_high") or c.get("day_low"):
        hi, lo = _f(c.get("day_high")), _f(c.get("day_low"))
        if hi is None or lo is None or lo > hi + 1e-12 or lo <= 0:
            add("DAY_RANGE_INVALID", f"need finite day_low <= day_high, both > 0 (got {c.get('day_low')!r}, "
                                     f"{c.get('day_high')!r})")
        elif not (lo - 1e-9 <= price <= hi + 1e-9):
            which, b, excess, pct = _excess(price, hi, lo)
            nums = {"day_high": hi, "day_low": lo, "violated_bound": "day_" + ("high" if which == "up" else "low"),
                    "excess": round(excess, 6), "excess_pct": round(pct, 6)}
            out_of_range.setdefault((code, "day_range"), []).append((i, price / b, which, pct))
            excesses.append(abs(pct))
            if tol > 0 and abs(pct) <= tol + 1e-9:
                within.append(dict(check="PRICE_OUTSIDE_DAY_RANGE", **nums))
            else:
                add("PRICE_OUTSIDE_DAY_RANGE", f"{price} not in the day's range [{lo}, {hi}]", nums)
    fee, turnover = _f(c["fee"]), _f(c["turnover"])
    if fee is not None and turnover is not None:
        try:
            stat = statutory_fee_floor(turnover, side, date, market, strict=strict)
            if fee + 1e-6 < stat:
                add("FEE_BELOW_STATUTORY", f"fee {fee:.2f} < statutory minimum {stat:.2f}")
        except KeyError as e:
            add("RULE_MISSING", str(e))


def scope_help() -> str:
    """The A-share scopes the checker accepts, generated from the registry (printed by --help / --list-scopes)."""
    eq = set(equity_scopes())
    lines = ["Scopes with a price-limit record (from data/cn/scopes.yaml; * = can be derived from context):"]
    for k, d in checkable_scopes().items():
        lines.append(f"  {'*' if k in eq else ' '} {k:<28} {d}")
    lines.append("Scope context columns read when the scope cell is empty: " +
                 ", ".join(sorted(set(context_keys()) | set(CONTEXT_ALIASES) | {"list_date"})) +
                 f" (st = st_status; list_date: past every listing window when more than {LIST_DATE_MARGIN_DAYS} "
                 "calendar days earlier)")
    return "\n".join(lines)


USAGE = ("usage: marina-check FILLS.csv [--strict] [--no-tick] [--band-tolerance-pct X] [--assume-seasoned]\n"
         "                    [--rows] [--top-codes N]\n"
         "       marina-check --list-scopes\n"
         "exit: 0 = no findings under the options used, 1 = findings, 2 = usage error")


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] in ("-h", "--help") or "--help" in argv or "-h" in argv:
        print(USAGE + "\n\n" + __doc__ + "\n" + scope_help()); return 0
    if "--list-scopes" in argv:
        print(scope_help()); return 0
    tick, strict, tol, per_row, seasoned, top, paths = True, False, 0.0, False, False, TOP_CODES, []
    it = iter(argv)
    for a in it:
        if a == "--strict":
            strict = True
        elif a == "--no-tick":
            tick = False
        elif a == "--rows":
            per_row = True
        elif a == "--assume-seasoned":
            seasoned = True
        elif a in ("--band-tolerance-pct", "--top-codes") or a.startswith(("--band-tolerance-pct=", "--top-codes=")):
            name, v = (a.split("=", 1) if "=" in a else (a, next(it, None)))
            try:
                if name == "--top-codes":
                    if v is None or not str(v).isdigit():
                        raise ValueError(f"--top-codes needs a non-negative integer, got {v!r}")
                    top = int(v)
                else:
                    tol = _validate_tolerance(v)
            except ValueError as e:
                print(f"marina-check: {e}\n{USAGE}", file=sys.stderr); return 2
        elif a.startswith("--"):
            print(f"marina-check: unknown option {a}\n{USAGE}", file=sys.stderr); return 2
        else:
            paths.append(a)
    if len(paths) != 1:
        print(USAGE, file=sys.stderr); return 2
    try:
        with open(paths[0], newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
    except OSError as e:
        print(f"marina-check: cannot read {paths[0]}: {e.strerror}", file=sys.stderr); return 2
    out = check_rows(rows, strict=strict, tick=tick, band_tolerance_pct=tol, per_row=per_row,
                     assume_seasoned=seasoned, top_codes=top)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if out["clean"] else 1


if __name__ == "__main__":
    sys.exit(main())
