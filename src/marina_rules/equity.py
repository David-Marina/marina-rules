"""Choosing an A-share equity scope from what the caller knows about a stock on a date.

    pick_scope(trade_date, board=..., st_status=..., listing_day_index=..., **context) -> dict
    equity_scopes() -> tuple of scope names pick_scope chooses from
    checkable_scopes() -> {scope: description} every A-share scope ``marina check`` can check a price band for
    board_for_code(code) -> (board, market) | None

``pick_scope`` is data-driven: it evaluates each candidate scope's own ``requires`` and ``asserts`` from
``data/cn/scopes.yaml`` (the same constraint grammar ``contract.resolve`` checks) against the context supplied, and
keeps the scopes that have a ``price_limit_pct`` record in force on the trade date. It never holds a second copy of
the rules and never guesses: when no scope or more than one scope fits, it says so and names the candidates.

Candidates (``equity_scopes()``) are the China A-share registry scopes that (1) have at least one ``price_limit_pct``
record, (2) assert ``board`` (a per-security board, i.e. an equity scope) and (3) belong to tick family ``stock`` or
``bse_stock`` (this leaves out B shares, funds, convertibles and REITs, whose scopes context cannot tell apart from
A shares). Suitability-only scopes (no price-limit record) are not candidates.
"""
from __future__ import annotations

import re
from functools import lru_cache

from . import records, scopes as _scopes, tick_family
from .contract import check_context

_TRUE = frozenset({"true", "t", "yes", "y", "1"})
_FALSE = frozenset({"false", "f", "no", "n", "0"})


@lru_cache(maxsize=None)
def _registry() -> dict:
    return _scopes("cn")


def scopes(prefix: str = "cn") -> dict:
    return _registry() if prefix == "cn" else _scopes(prefix)


@lru_cache(maxsize=None)
def _price_limit_scopes() -> frozenset:
    return frozenset(r.scope for r in records() if r.rule == "price_limit_pct")


def checkable_scopes() -> dict:
    """{scope: description} for every China A-share registry scope that has a ``price_limit_pct`` record — the scopes
    whose price band ``marina check`` can check. Generated from the registry and the records, in registry order."""
    have = _price_limit_scopes()
    return {k: v["description"] for k, v in scopes("cn").items() if k in have}


@lru_cache(maxsize=None)
def equity_scopes() -> tuple:
    """The scopes ``pick_scope`` chooses from (see the module docstring for the selection rule)."""
    have = _price_limit_scopes()
    return tuple(k for k, v in scopes("cn").items()
                 if k in have and "board" in (v.get("asserts") or {})
                 and tick_family(k) in ("stock", "bse_stock"))


@lru_cache(maxsize=None)
def context_keys() -> tuple:
    """Context keys the candidate scopes require or assert (the optional CSV columns ``marina check`` reads)."""
    reg = scopes("cn")
    keys: dict = {}
    for s in equity_scopes():
        for k in list(reg[s]["requires"]) + list((reg[s].get("asserts") or {}).keys()):
            keys[k] = None
    return tuple(keys)


def _entries(spec):
    return spec if isinstance(spec, list) else [spec if isinstance(spec, dict) else {"eq": spec}]


@lru_cache(maxsize=None)
def context_kind(key: str) -> str:
    """'bool', 'int' or 'str': the value type the registry's asserts use for ``key`` (for parsing CSV text)."""
    reg = scopes("cn")
    for s in equity_scopes():
        spec = (reg[s].get("asserts") or {}).get(key)
        if spec is None:
            continue
        for e in _entries(spec):
            vals = [e[op] for op in ("eq",) if op in e] + list(e.get("in") or ()) + list(e.get("not_in") or ())
            if any(isinstance(v, bool) for v in vals):
                return "bool"
            if "min" in e or "max" in e or any(isinstance(v, int) for v in vals):
                return "int"
    return "str"


def parse_context_value(key: str, text):
    """Parse one CSV cell for context ``key``: None when empty; raises ValueError when it does not parse."""
    t = "" if text is None else str(text).strip()
    if t == "":
        return None
    kind = context_kind(key)
    if kind == "bool":
        if t.lower() in _TRUE:
            return True
        if t.lower() in _FALSE:
            return False
        raise ValueError(f"{key}={t!r} is not true/false")
    if kind == "int":
        try:
            return int(t)
        except ValueError:
            raise ValueError(f"{key}={t!r} is not an integer") from None
    return t


@lru_cache(maxsize=65536)
def _in_force(scope: str, date: str) -> bool:
    return any(r.rule == "price_limit_pct" and r.scope == scope and r.active_on(date) for r in records())


def pick_scope(trade_date: str, board: str | None = None, st_status: bool | None = None,
               listing_day_index: int | None = None, **context) -> dict:
    """The single equity scope whose registry assertions hold for this stock on ``trade_date``.

    Pass what you know: ``board`` (main_board | chinext | star | bse), ``st_status`` (ST / *ST on that date),
    ``listing_day_index`` (1 = listing day), and any other registry key the scopes use (``issue_regime``,
    ``delisting_day_index``, ``delisting_entry_before_2020_08_24`` …; see ``context_keys()``). ``None`` = not known.

    A scope fits when every key it ``requires`` is supplied, no supplied key contradicts its ``asserts`` on that date,
    and a ``price_limit_pct`` record of that scope is in force on that date. Returns a dict:
      status      DETERMINED | NO_MATCH | AMBIGUOUS
      scope       the scope (DETERMINED only), else None
      candidates  the fitting scopes (AMBIGUOUS), or the scopes that would fit given more context (NO_MATCH)
      needs       NO_MATCH only: {scope: [missing keys]} for scopes not contradicted by what was supplied
      reason      plain words
    A stock in a delisting arrangement period also fits its ordinary or ST scope unless that is ruled out, so such a
    row is usually AMBIGUOUS: give its scope explicitly.
    """
    date = str(trade_date)[:10]
    ctx = {k: v for k, v in dict(context, board=board, st_status=st_status,
                                listing_day_index=listing_day_index).items() if v is not None}
    reg = scopes("cn")
    fits, needs = [], {}
    for s in equity_scopes():
        spec = reg[s]
        missing, conflicts = check_context(spec.get("asserts") or {}, ctx, date)
        if conflicts:
            continue
        missing = list(dict.fromkeys([k for k in spec["requires"] if k not in ctx] + missing))
        if not _in_force(s, date):
            continue
        if missing:
            needs[s] = missing
        else:
            fits.append(s)
    out = {"status": None, "scope": None, "candidates": [], "needs": {}, "reason": ""}
    if len(fits) == 1:
        out.update(status="DETERMINED", scope=fits[0], reason=f"only {fits[0]} fits {ctx} on {date}")
    elif fits:
        out.update(status="AMBIGUOUS", candidates=fits,
                   reason=f"several scopes fit {ctx} on {date}: {fits} — give the scope explicitly")
    else:
        out.update(status="NO_MATCH", candidates=sorted(needs), needs=needs,
                   reason=f"no scope fits {ctx} on {date}" +
                          ("; would need " + "; ".join(f"{s}: {m}" for s, m in needs.items()) if needs else ""))
    return out


# --- board from code: a convenience, NOT a sourced record ---------------------------------------------------------

_SUFFIX = {"SH": "XSHG", "SS": "XSHG", "XSHG": "XSHG", "SZ": "XSHE", "XSHE": "XSHE", "BJ": "BJSE", "BSE": "BJSE",
           "BJSE": "BJSE"}
_PREFIXES = (  # (code prefix, board, market) — A-share stocks only
    (("600", "601", "603", "605"), "main_board", "XSHG"),
    (("688", "689"), "star", "XSHG"),
    (("000", "001", "002", "003"), "main_board", "XSHE"),
    (("300", "301"), "chinext", "XSHE"),
    (("920", "43", "83", "87"), "bse", "BJSE"),
)
_CODE = re.compile(r"^(?:(SH|SZ|BJ)\.?)?(\d{6})(?:\.([A-Z]+))?$")


def board_for_code(code) -> tuple | None:
    """(board, market) of an A-share STOCK code, or None when the code is not recognised.

    CONVENIENCE ONLY. It follows the exchanges' code-allocation conventions (SSE 600/601/603/605 main board,
    688/689 STAR; SZSE 000/001/002/003 main board, 300/301 ChiNext; BSE 920 and the legacy 43/83/87 ranges).
    It is not a sourced record, is not part of the dataset or its digest, and says nothing about ST status or
    listing day. Funds, bonds, B shares, indices and any other prefix return None, as does a code whose exchange
    suffix (``.SH`` / ``.SZ`` / ``.BJ`` / ``.XSHG`` …) contradicts its prefix. Accepts ``600000``, ``600000.SH``,
    ``SH600000``."""
    m = _CODE.match(str(code or "").strip().upper())
    if not m:
        return None
    pre, digits, suf = m.groups()
    stated = {_SUFFIX.get(x) for x in (pre, suf) if x}
    if None in stated or len(stated) > 1:
        return None
    want = stated.pop() if stated else None
    for prefixes, board, market in _PREFIXES:
        if digits.startswith(prefixes):
            return None if want not in (None, market) else (board, market)
    return None
