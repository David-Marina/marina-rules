"""Marina rules — point-in-time trading rules for financial markets, as data.

    >>> import marina_rules as mr
    >>> mr.rule_at("stamp_duty_sell", "2023-08-28")
    0.0005
    >>> mr.limit_price(10.00, "chinext", "2021-03-01")
    (12.0, 8.0)
    >>> mr.citation()
    'rules: marina-rules-data@<data version> sha256:<16 hex> code: marina-rules@<code version>'

Where to start (nothing here needs the network):
  * ``mr.skill_text()`` — the usage notes shipped with the package (the path to follow, when to stop).
  * ``mr.scopes()`` / ``mr.rules_for(scope, market)`` — which scopes exist and which rule names each one has.
    Ask for a rule by the exact name listed there; a name that is absent cannot be answered.
  * ``marina_rules.contract.resolve(...)`` — one decision dict per question, never raises for data reasons.
  * ``mr.statutory_fee_floor(turnover, side, date, market)`` — stamp duty + transfer fee of one A-share fill.
  * Command line: ``python -m marina_rules`` (or ``marina-rules``) lists the subcommands.

Design rules (do not relax):
  * Lookups that find no effective record raise ``KeyError``. There are no defaults.
  * Every record carries a ``verification`` level; ``strict=True`` refuses ``unverified`` records.
  * Every source on a ``verified`` or ``single-source`` record carries ``content_sha256`` — the SHA-256
    of the document's extracted text for HTML, of the bytes for PDF/DOCX (see ``sourcehash``) — and a
    verbatim quote. Loading refuses a dataset that violates this; it is not advisory.
  * The dataset digest in ``citation()`` is computed over the data files only, so a result
    that cites it can be re-run against byte-identical rules. The tracking registries
    (``data/<prefix>/tracking.yaml``: how far the sources were checked) are not rules and are excluded.

Two packages: this one (``marina-rules``, the code, semantic versions: ``__version__``) and ``marina-rules-data`` (the
dataset, date versions: ``DATA_VERSION``), which is released on its own and can be upgraded without this one. A source
checkout reads the repository's ``data/`` instead. ``citation()`` names both versions and the dataset digest.
"""
from __future__ import annotations

import hashlib
import math
import os
import re as _re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Iterable

import yaml

__all__ = ["rule_at", "record_at", "records", "scopes", "known_gaps", "gaps_for", "coverage", "market_prefix_for", "limit_price", "tick_size", "tick_family", "lookup_scope", "min_tick_band", "round_half_up",
           "citation", "dataset_digest", "DATA_DIR", "DATA_VERSION", "MIN_DATA_VERSION", "DATA_SCHEMAS",
           "DataNotInstalled", "IncompatibleData", "Record", "RuleConflict", "NotYetPublished",
           "PublicationUnknown", "ContractRequired", "parse_contract", "contract_matches", "tracked_through",
           "tracking_registry", "tracking_state", "BeyondTracking", "rules_for", "statutory_fee_floor",
           "statutory_fee_components", "skill_text", "markets_recorded"]

__version__ = "1.0.0"            # this package, the code (marina-rules); semantic versioning
MIN_DATA_VERSION = "2026.11.13"  # the oldest marina-rules-data this code reads (pyproject.toml declares the same)
DATA_SCHEMAS = (1, 1.1, 1.2)     # the data formats (``schema:`` of a data file, data/SCHEMA) this code reads


class DataNotInstalled(ImportError):
    """Neither a source checkout's data/ nor the marina-rules-data package is there."""


class IncompatibleData(ImportError):
    """The installed dataset and this code do not fit together; the message says which package to upgrade."""


_VERSION_RE = _re.compile(r"^(\d{4})\.(\d{2})\.(\d{2})(?:\.(\d+))?$")


def _version_key(v: str) -> tuple:
    """'2026.11.13' → (2026, 11, 13, 0); '2026.11.13.2' → (2026, 11, 13, 2). Raises ValueError for anything else."""
    m = _VERSION_RE.match(v)
    if not m:
        raise ValueError(f"not a dataset version (YYYY.MM.DD or YYYY.MM.DD.N): {v!r}")
    return tuple(int(x or 0) for x in m.groups())


def _locate_data() -> str:
    """Where the dataset is: a source checkout's data/ (beside src/), else the installed marina-rules-data package."""
    checkout = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "data"))
    if os.path.isfile(os.path.join(checkout, "VERSION")):
        return checkout
    try:
        import marina_rules_data
    except ImportError:
        raise DataNotInstalled(
            "marina_rules: the dataset is not installed. It is a separate package: pip install marina-rules-data "
            "(a normal `pip install marina-rules` installs it; an install with --no-deps does not)") from None
    return marina_rules_data.DATA_DIR


def _read_data_meta(data_dir: str, name: str) -> str:
    try:
        with open(os.path.join(data_dir, name), encoding="ascii") as fh:
            return fh.read().strip()
    except (OSError, UnicodeDecodeError) as e:
        raise IncompatibleData(f"marina_rules: the dataset in {data_dir} has no readable {name} file ({e}); "
                               "reinstall it: pip install --force-reinstall marina-rules-data") from None


def _check_data(data_dir: str) -> str:
    """The version of the dataset in ``data_dir`` after checking that this code can read it (data/VERSION is at least
    MIN_DATA_VERSION, data/SCHEMA is one of DATA_SCHEMAS). Raises IncompatibleData naming the package to upgrade."""
    version, schema = _read_data_meta(data_dir, "VERSION"), _read_data_meta(data_dir, "SCHEMA")
    try:
        key = _version_key(version)
    except ValueError as e:
        raise IncompatibleData(f"marina_rules: the dataset in {data_dir}: {e}") from None
    if key < _version_key(MIN_DATA_VERSION):
        raise IncompatibleData(
            f"marina_rules: marina-rules {__version__} needs marina-rules-data {MIN_DATA_VERSION} or later; the installed "
            f"dataset is {version}. Upgrade the data: pip install -U marina-rules-data")
    num = float(schema) if _re.match(r"^\d+(\.\d+)?$", schema) else None
    if num is None or num not in DATA_SCHEMAS:
        newer = num is not None and num > max(DATA_SCHEMAS)
        raise IncompatibleData(
            f"marina_rules: marina-rules-data {version} is written in data schema {schema}; marina-rules {__version__} "
            f"reads schema {', '.join(str(x) for x in DATA_SCHEMAS)}. "
            + ("The data is newer than this code. Upgrade the code: pip install -U marina-rules" if newer else
               "Reinstall the data: pip install --force-reinstall marina-rules-data"))
    return version


DATA_DIR = _locate_data()
DATA_VERSION = _check_data(DATA_DIR)   # the dataset's own version (data/VERSION); not part of dataset_digest()

_LEVELS = ("verified", "single-source", "unverified")
_SHA_RE = _re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class Record:
    id: str
    market: str
    scope: str
    rule: str
    value: Any
    effective_from: str
    effective_to: str | None
    verification: str
    sources: tuple
    notes: str
    file: str
    published_at: str | None = None   # official publication date of the notice (None = not located)
    recorded_at: str | None = None    # date this record entered Marina (never a proxy for "known at")
    unit: str | None = None           # for absolute values: CNY / USD / HKD; None for fractions and flags
    contracts: Any = None             # futures contract selector (schema 1.2); None = every contract of the scope

    def active_on(self, date: str) -> bool:
        return self.effective_from <= date and (self.effective_to is None or date < self.effective_to)

    def applies_to(self, contract: str | None, date: str) -> bool:
        """Does this record cover ``contract`` on ``date``? No selector → every contract (and the no-contract query)."""
        if self.contracts is None:
            return True
        return contract is not None and contract_matches(self.contracts, contract, date, self.scope)


# The tracking registry (data/<prefix>/tracking.yaml, see tracking_registry()) is NOT part of the rules: it says up to
# which date the maintainer has checked the official sources, and moving that date forward must not change the
# dataset digest. _iter_files() therefore skips it by name; it is loaded separately.
TRACKING_FILE = "tracking.yaml"


def _iter_files(data_dir: str | None = None) -> Iterable[str]:
    # Sorted by path relative to the data directory across directories: os.walk's directory order is
    # filesystem-dependent, and the dataset digest must not depend on it once data/ has more than one market directory.
    base = DATA_DIR if data_dir is None else data_dir
    paths = [os.path.join(root, f) for root, _, files in os.walk(base) for f in files
             if f.endswith((".yaml", ".yml")) and f != TRACKING_FILE]
    yield from sorted(paths, key=lambda p: os.path.relpath(p, base))


def _norm_date(v) -> str | None:
    if v is None:
        return None
    return v.isoformat() if hasattr(v, "isoformat") else str(v)[:10]


def _iso_dates(v):
    """Recursively replace date/datetime objects (YAML parses unquoted dates) with ISO strings, so every
    Record — value, sources, evidence — is JSON-serialisable. Applied at load time to every record."""
    import datetime as _dt
    if isinstance(v, (_dt.date, _dt.datetime)):
        return v.isoformat()
    if isinstance(v, dict):
        return {k: _iso_dates(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return type(v)(_iso_dates(x) for x in v)
    return v


# Rules whose value is a list of price bands [{gt | ge, le, tick}, ...] (docs/SCHEMA.md, Hong Kong section).
_BAND_TABLE_RULES = frozenset({"tick_size_table"})


def _is_number(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def _check_band_table(bands, where: str = "band table") -> None:
    """Validate a price-band table: a non-empty list of ``{gt | ge, le, tick}`` in ascending order.

    A price p falls in the band with ``gt < p <= le``; only the first band may use ``ge`` (``ge <= p <= le``) so
    that it includes the lowest permissible price. Each band must start exactly where the previous one ends
    (``gt`` == previous ``le``), so the table has no hole and no overlap; ``tick`` must be positive. Raises
    ``ValueError`` naming ``where`` otherwise."""
    if not isinstance(bands, list) or not bands:
        raise ValueError(f"{where}: band table must be a non-empty list")
    prev_le = None
    for i, b in enumerate(bands):
        if not isinstance(b, dict) or set(b) - {"gt", "ge", "le", "tick"} or len({"gt", "ge"} & set(b)) != 1 \
                or "le" not in b or "tick" not in b:
            raise ValueError(f"{where}: band #{i} must have exactly one of gt / ge, plus le and tick: {b!r}")
        lo_key = "ge" if "ge" in b else "gt"
        if lo_key == "ge" and i > 0:
            raise ValueError(f"{where}: band #{i}: only the first band may use ge")
        lo, hi, tick = b[lo_key], b["le"], b["tick"]
        if not (_is_number(lo) and _is_number(hi) and _is_number(tick)):
            raise ValueError(f"{where}: band #{i}: bounds and tick must be finite numbers: {b!r}")
        if not (lo < hi if lo_key == "gt" else lo <= hi) or lo < 0 or tick <= 0:
            raise ValueError(f"{where}: band #{i}: need 0 <= lower < le and tick > 0: {b!r}")
        if prev_le is not None and lo != prev_le:
            raise ValueError(f"{where}: band #{i} starts at {lo_key} {lo}, but the previous band ends at le {prev_le}: "
                             "bands must meet end to end (no hole, no overlap)")
        prev_le = hi


# Rules whose value is a LULD tier map {tier_*: [segments], hours: [start, end]} (docs/SCHEMA.md, US section).
_LULD_RULES = frozenset({"luld_band"})
# Rules whose value is a group map {<group>: [segments], hours: [start, end], lookback_minutes: n} (same section).
_PAUSE_RULES = frozenset({"single_stock_pause_pct"})
_HHMM_RE = _re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
_GROUP_RE = _re.compile(r"^[a-z][a-z0-9_]*$")
_LULD_SEGMENT_KEYS = frozenset({"gt", "ge", "lt", "le", "pct", "abs_cap", "doubled"})
_PAUSE_SEGMENT_KEYS = frozenset({"gt", "ge", "lt", "le", "pct"})


def _check_window(w, where: str) -> None:
    """A half-open time window ``[start, end]``: two ``HH:MM`` strings with start < end."""
    if not (isinstance(w, list) and len(w) == 2 and all(isinstance(x, str) and _HHMM_RE.match(x) for x in w)
            and w[0] < w[1]):
        raise ValueError(f"{where}: need a window ['HH:MM', 'HH:MM'] with start < end: {w!r}")


def _check_price_brackets(segs, where: str, keys: frozenset, required: tuple, check_segment=None) -> None:
    """Validate a list of price brackets that must cover every positive price exactly once.

    Each bracket is a mapping with keys from ``keys`` only, every key in ``required``, at most one lower bound (``gt``
    exclusive / ``ge`` inclusive; none = from 0 exclusive), at most one upper bound (``lt`` exclusive / ``le``
    inclusive; none = unbounded) and a percentage ``pct`` > 0. The brackets, in any order, meet end to end with exactly
    one side of each shared bound inclusive (``le`` / ``gt`` or ``lt`` / ``ge``); the lowest has no lower bound (or
    ``gt: 0``) and the highest no upper bound. ``check_segment(bracket, label)`` runs any further per-bracket check.
    Raises ``ValueError`` naming ``where`` otherwise."""
    if not isinstance(segs, list) or not segs:
        raise ValueError(f"{where}: must be a non-empty list of price brackets")
    ivs = []
    for i, s in enumerate(segs):
        if not isinstance(s, dict) or set(s) - keys or any(k not in s for k in required) \
                or len({"gt", "ge"} & set(s)) > 1 or len({"lt", "le"} & set(s)) > 1:
            raise ValueError(f"{where}: bracket #{i} needs {' and '.join(required)}, at most one of gt / ge and one of "
                             f"lt / le, and no key outside {sorted(keys)}: {s!r}")
        lo_key = "ge" if "ge" in s else "gt" if "gt" in s else None
        hi_key = "le" if "le" in s else "lt" if "lt" in s else None
        lo, hi = (s[lo_key] if lo_key else 0.0), (s[hi_key] if hi_key else math.inf)
        if not (_is_number(lo) and (hi_key is None or _is_number(hi))):
            raise ValueError(f"{where}: bracket #{i}: bounds must be finite numbers: {s!r}")
        if lo < 0 or (lo_key == "ge" and lo <= 0) or not lo < hi:
            raise ValueError(f"{where}: bracket #{i}: need a non-empty range of positive prices: {s!r}")
        if not (_is_number(s["pct"]) and s["pct"] > 0):
            raise ValueError(f"{where}: bracket #{i}: pct must be a number > 0: {s!r}")
        if check_segment is not None:
            check_segment(s, f"{where}: bracket #{i}")
        ivs.append((lo, lo_key == "ge", hi, hi_key == "le", i))
    ivs.sort(key=lambda t: (t[0], not t[1]))
    if ivs[0][0] != 0:
        raise ValueError(f"{where}: the lowest bracket must start above 0 (no lower bound, or gt: 0)")
    for a, b in zip(ivs, ivs[1:]):
        if a[2] != b[0] or a[3] == b[1]:
            raise ValueError(f"{where}: brackets #{a[4]} and #{b[4]} leave a hole or overlap at {a[2]} "
                             "(adjacent brackets must share a bound, inclusive on exactly one side)")
    if ivs[-1][2] != math.inf:
        raise ValueError(f"{where}: the highest bracket must have no upper bound")


def _check_luld_band(value, where: str = "luld_band") -> None:
    """Validate a LULD tier map: ``{hours: [start, end], tier_<name>: [segment, ...], ...}``.

    Each segment is a price bracket (see ``_check_price_brackets``) with a percentage parameter ``pct`` > 0, an
    optional absolute cap ``abs_cap`` > 0, and ``doubled``: the windows (each inside ``hours``) in which the parameters
    are doubled. Within a tier the brackets must cover every positive price exactly once. Raises ``ValueError`` naming
    ``where`` otherwise."""
    if not isinstance(value, dict) or "hours" not in value:
        raise ValueError(f"{where}: luld_band value must be a mapping with 'hours' and at least one tier_* key")
    _check_window(value["hours"], f"{where}: hours")
    h0, h1 = value["hours"]
    tiers = {k: v for k, v in value.items() if k != "hours"}
    if not tiers or not all(isinstance(k, str) and k.startswith("tier_") for k in tiers):
        raise ValueError(f"{where}: keys besides 'hours' must be tier_* (got {sorted(map(str, tiers))})")

    def check(s, w):
        if "abs_cap" in s and not (_is_number(s["abs_cap"]) and s["abs_cap"] > 0):
            raise ValueError(f"{w}: abs_cap must be a number > 0: {s!r}")
        if not isinstance(s["doubled"], list):
            raise ValueError(f"{w}: doubled must be a list of windows: {s!r}")
        for d in s["doubled"]:
            _check_window(d, f"{w}: doubled")
            if not (h0 <= d[0] and d[1] <= h1):
                raise ValueError(f"{w}: doubled window {d} is outside hours {value['hours']}")

    for name, segs in tiers.items():
        _check_price_brackets(segs, f"{where}: {name}", _LULD_SEGMENT_KEYS, ("pct", "doubled"), check)


def _check_single_stock_pause(value, where: str = "single_stock_pause_pct") -> None:
    """Validate a trading-pause group map: ``{hours: [start, end], lookback_minutes: n, <group>: [segment, ...], ...}``.

    ``hours`` is the monitoring window, ``lookback_minutes`` a positive integer, and every other key a lower-case
    snake_case security group (membership is the caller's) whose segments are price brackets ``{gt | ge, lt | le,
    pct}`` covering every positive price exactly once (see ``_check_price_brackets``; a group without price brackets is
    one ``{gt: 0.0, pct}``). Raises ``ValueError`` naming ``where`` otherwise."""
    if not isinstance(value, dict) or "hours" not in value or "lookback_minutes" not in value:
        raise ValueError(f"{where}: single_stock_pause_pct value must be a mapping with 'hours', 'lookback_minutes' "
                         "and at least one group")
    _check_window(value["hours"], f"{where}: hours")
    lb = value["lookback_minutes"]
    if not (isinstance(lb, int) and not isinstance(lb, bool) and lb > 0):
        raise ValueError(f"{where}: lookback_minutes must be a positive integer: {lb!r}")
    groups = {k: v for k, v in value.items() if k not in ("hours", "lookback_minutes")}
    if not groups or not all(isinstance(k, str) and _GROUP_RE.match(k) for k in groups):
        raise ValueError(f"{where}: need at least one group besides 'hours' / 'lookback_minutes', each a lower-case "
                         f"snake_case name (got {sorted(map(str, groups))})")
    for name, segs in groups.items():
        _check_price_brackets(segs, f"{where}: {name}", _PAUSE_SEGMENT_KEYS, ("pct",))


# Rule short_sale_price_test, per market (docs/SCHEMA.md). US (XNYS / XNAS / XNYS+XNAS): the string 'none' or a mapping
# of a decline fraction and three enumerated terms (US section). Hong Kong (XHKG): a mapping {restriction, duration} of
# two enumerated terms (Hong Kong section). Only the values defined there are accepted; no other market has the rule.
_SHORT_SALE_RULES = frozenset({"short_sale_price_test"})
_SHORT_SALE_US_MARKETS = frozenset({"XNYS", "XNAS", "XNYS+XNAS"})
_SHORT_SALE_ENUMS = {"reference": frozenset({"prior_close"}),
                     "restriction": frozenset({"above_national_best_bid"}),
                     "duration": frozenset({"rest_of_day_and_next_day"})}
_SHORT_SALE_HK_ENUMS = {"restriction": frozenset({"not_below_best_ask", "exempt"}),
                        "duration": frozenset({"always"})}
# Rule pattern_day_trader_min_equity: {min_equity, day_trades, window_business_days} + unit (same section).
_PDT_RULES = frozenset({"pattern_day_trader_min_equity"})
# Plain fractions with a load-time range check: rule -> (low, low inclusive, high). The upper bound is exclusive.
# Hong Kong section of docs/SCHEMA.md: a levy may be 0 (a sourced suspension); a price band may not; both below 1.
# Futures exchange fees as a fraction of turnover (CFFEX / SHFE sections): [0, 0.01); 0 is a sourced waiver.
_FRACTION_RULES = {"investor_compensation_levy_each_side": (0, True, 1),
                   "opening_auction_limit_pct": (0, False, 1),
                   "closing_auction_limit_pct": (0, False, 1),
                   "trans_fee_rate": (0, True, 0.01),
                   "close_today_fee_rate": (0, True, 0.01)}
# Futures exchange fees in a currency per lot (CFFEX / SHFE sections): need `unit: CNY` and a number >= 0.
_PER_LOT_FEE_RULES = frozenset({"trans_fee_per_lot", "close_today_fee_per_lot"})
_PER_LOT_FEE_UNITS = frozenset({"CNY"})
# Order-entry price controls, Hong Kong only (docs/SCHEMA.md, Hong Kong section): order_spread_limit is
# {max_spreads, wider_pct, reference} and order_price_multiple_limit is {max_multiple, reference}; `reference` is one of
# the enumerated values defined there. Any other market is refused.
_ORDER_LIMIT_MARKETS = frozenset({"XHKG"})
_ORDER_SPREAD_RULES = frozenset({"order_spread_limit"})
_ORDER_SPREAD_REFERENCES = frozenset({"same_side_best_or_rule_fallback"})
_ORDER_MULTIPLE_RULES = frozenset({"order_price_multiple_limit"})
_ORDER_MULTIPLE_REFERENCES = frozenset({"nominal_or_previous_close_for_opening"})
# Boolean flags (docs/SCHEMA.md, "China A-share investor suitability"): the value must be YAML true or false — not 0/1,
# not a string. retail_risk_disclosure_required: must an ordinary investor have signed the prescribed risk disclosure
# statement before the broker may accept orders in the scope's securities.
_BOOL_RULES = frozenset({"retail_risk_disclosure_required"})


def _is_pos_int(x) -> bool:
    return isinstance(x, int) and not isinstance(x, bool) and x > 0


def _check_fraction(rule: str, value, where: str = "fraction") -> None:
    """Validate a plain fraction rule from ``_FRACTION_RULES``: a finite number in [low, high) where the low end is
    inclusive, else in (low, high). Raises ``ValueError`` naming ``where`` otherwise."""
    lo, inclusive, hi = _FRACTION_RULES[rule]
    ok = _is_number(value) and (lo <= value if inclusive else lo < value) and value < hi
    if not ok:
        rng = f"[{lo}, {hi})" if inclusive else f"({lo}, {hi})"
        raise ValueError(f"{where}: {rule} must be a number in {rng}: {value!r}")


def _check_bool(rule: str, value, where: str = "flag") -> None:
    """Validate a boolean flag rule from ``_BOOL_RULES``: exactly ``True`` or ``False``. Raises ``ValueError``."""
    if not isinstance(value, bool):
        raise ValueError(f"{where}: {rule} must be true or false: {value!r}")


def _check_per_lot_fee(rule: str, value, unit, where: str = "per-lot fee") -> None:
    """Validate a per-lot exchange fee from ``_PER_LOT_FEE_RULES``: ``unit`` one of ``_PER_LOT_FEE_UNITS`` and the value
    a finite number >= 0. Raises ``ValueError`` naming ``where`` otherwise."""
    if unit not in _PER_LOT_FEE_UNITS:
        raise ValueError(f"{where}: {rule} needs unit {' or '.join(sorted(_PER_LOT_FEE_UNITS))} (the currency per lot): "
                         f"{unit!r}")
    if not (_is_number(value) and value >= 0):
        raise ValueError(f"{where}: {rule} must be a number >= 0: {value!r}")


def _check_short_sale_price_test(value, where: str = "short_sale_price_test", market: str = "XNYS+XNAS") -> None:
    """Validate a short-sale price test for ``market``.

    US markets: ``'none'`` (no price test) or ``{trigger_decline_pct, reference, restriction, duration}`` with exactly
    these keys, ``0 < trigger_decline_pct < 1`` and each of the other three one of the defined enumeration values.
    ``XHKG``: exactly ``{restriction, duration}``, ``restriction`` ``not_below_best_ask`` | ``exempt`` and ``duration``
    ``always`` (no ``'none'``). Any other market is refused. Raises ``ValueError`` naming ``where`` otherwise."""
    if market == "XHKG":
        keys = set(_SHORT_SALE_HK_ENUMS)
        if not isinstance(value, dict) or set(value) != keys:
            raise ValueError(f"{where}: XHKG short_sale_price_test value must be a mapping with exactly the keys "
                             f"{sorted(keys)}: {value!r}")
        for k, allowed in _SHORT_SALE_HK_ENUMS.items():
            if not (isinstance(value[k], str) and value[k] in allowed):
                raise ValueError(f"{where}: {k} must be one of {sorted(allowed)}: {value[k]!r}")
        return
    if market not in _SHORT_SALE_US_MARKETS:
        raise ValueError(f"{where}: short_sale_price_test is defined only for "
                         f"{sorted(_SHORT_SALE_US_MARKETS | {'XHKG'})}, not market {market!r}")
    if value == "none":
        return
    keys = {"trigger_decline_pct", *_SHORT_SALE_ENUMS}
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError(f"{where}: short_sale_price_test value must be 'none' or a mapping with exactly the keys "
                         f"{sorted(keys)}: {value!r}")
    t = value["trigger_decline_pct"]
    if not (_is_number(t) and 0 < t < 1):
        raise ValueError(f"{where}: trigger_decline_pct must be a number in (0, 1): {t!r}")
    for k, allowed in _SHORT_SALE_ENUMS.items():
        if not (isinstance(value[k], str) and value[k] in allowed):
            raise ValueError(f"{where}: {k} must be one of {sorted(allowed)}: {value[k]!r}")


def _check_order_limit_market(rule: str, where: str, market: str) -> None:
    if market not in _ORDER_LIMIT_MARKETS:
        raise ValueError(f"{where}: {rule} is defined only for {sorted(_ORDER_LIMIT_MARKETS)}, not market {market!r}")


def _check_order_spread_limit(value, where: str = "order_spread_limit", market: str = "XHKG") -> None:
    """Validate a continuous-trading quotation spread limit for ``market`` (``XHKG`` only): exactly
    ``{max_spreads, wider_pct, reference}`` with ``max_spreads`` a positive integer, ``wider_pct`` ``None`` (spreads
    only) or a number in (0, 1) (the percentage alternative; the wider of the two applies) and ``reference`` one of the
    defined enumeration values. Raises ``ValueError`` naming ``where`` otherwise."""
    _check_order_limit_market("order_spread_limit", where, market)
    keys = {"max_spreads", "wider_pct", "reference"}
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError(f"{where}: order_spread_limit value must be a mapping with exactly the keys {sorted(keys)}: "
                         f"{value!r}")
    if not _is_pos_int(value["max_spreads"]):
        raise ValueError(f"{where}: max_spreads must be a positive integer: {value['max_spreads']!r}")
    w = value["wider_pct"]
    if w is not None and not (_is_number(w) and 0 < w < 1):
        raise ValueError(f"{where}: wider_pct must be null or a number in (0, 1): {w!r}")
    if not (isinstance(value["reference"], str) and value["reference"] in _ORDER_SPREAD_REFERENCES):
        raise ValueError(f"{where}: reference must be one of {sorted(_ORDER_SPREAD_REFERENCES)}: "
                         f"{value['reference']!r}")


def _check_order_price_multiple_limit(value, where: str = "order_price_multiple_limit", market: str = "XHKG") -> None:
    """Validate an order-price multiple check for ``market`` (``XHKG`` only): exactly ``{max_multiple, reference}``
    with ``max_multiple`` a number > 1 and ``reference`` one of the defined enumeration values. Raises ``ValueError``
    naming ``where`` otherwise."""
    _check_order_limit_market("order_price_multiple_limit", where, market)
    keys = {"max_multiple", "reference"}
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError(f"{where}: order_price_multiple_limit value must be a mapping with exactly the keys "
                         f"{sorted(keys)}: {value!r}")
    m = value["max_multiple"]
    if not (_is_number(m) and m > 1):
        raise ValueError(f"{where}: max_multiple must be a number > 1: {m!r}")
    if not (isinstance(value["reference"], str) and value["reference"] in _ORDER_MULTIPLE_REFERENCES):
        raise ValueError(f"{where}: reference must be one of {sorted(_ORDER_MULTIPLE_REFERENCES)}: "
                         f"{value['reference']!r}")


def _check_pattern_day_trader(value, where: str = "pattern_day_trader_min_equity") -> None:
    """Validate a pattern-day-trader requirement: ``{min_equity, day_trades, window_business_days}`` with exactly these
    keys, ``min_equity`` a number > 0 (in the record's unit) and the other two positive integers. Raises ``ValueError``
    naming ``where`` otherwise."""
    keys = {"min_equity", "day_trades", "window_business_days"}
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError(f"{where}: pattern_day_trader_min_equity value must be a mapping with exactly the keys "
                         f"{sorted(keys)}: {value!r}")
    if not (_is_number(value["min_equity"]) and value["min_equity"] > 0):
        raise ValueError(f"{where}: min_equity must be a number > 0: {value['min_equity']!r}")
    for k in ("day_trades", "window_business_days"):
        if not _is_pos_int(value[k]):
            raise ValueError(f"{where}: {k} must be a positive integer: {value[k]!r}")


# ---------------------------------------------------------------------------------------- contract selectors
# A futures record (or known gap) may carry ``contracts``: it then covers only part of the product's contracts on
# each day. Grammar (docs/SCHEMA.md "Contract selectors"; files using it declare schema 1.2):
#   contracts: {any: [clause, ...]}    covers a contract iff at least one clause matches it
#   contracts: {none: [clause, ...]}   covers a contract iff no clause matches it
#   clause: {key: condition, ...}      every key must hold (AND)
#     code               {in | not_in: [codes]}            lower-case product + YYMM in data (au2506; CZCE SR605 → sr2605);
#                                                          a query may use either form, any case
#     delivery_month     {in | not_in: [1..12]}            the contract's delivery calendar month
#     months_to_delivery {min | max | in}                  (delivery year*12 + month) - (trade year*12 + month)
# Every feature is arithmetic on the code and the trade date; Marina never needs a contract calendar. Two records
# of one (scope, rule) in force on the same day must be disjoint for every contract; a record without a selector
# covers every contract, so it cannot share days with a selector record.
_SEL_OPS = {"code": ("in", "not_in"), "delivery_month": ("in", "not_in"), "months_to_delivery": ("min", "max", "in")}
_CODE_RE = _re.compile(r"^([A-Za-z]+)(\d{3,4})$")
_SCHEMA_SELECTORS = 1.2


class ContractRequired(KeyError):
    """The rule varies by futures contract on the date (records carry a ``contracts`` selector) and no contract was
    given. Marina does not pick a tier for the caller. Attributes: ``records`` (the in-force records)."""

    def __init__(self, msg: str, records: tuple = ()):
        self.records = records
        super().__init__(msg)

    def __str__(self):
        return self.args[0]


def _scope_product(scope: str) -> str | None:
    """'shfe_au' → 'au'. Only an ``<exchange>_<product>`` scope names one product; umbrella scopes return None."""
    parts = scope.split("_")
    return parts[1] if len(parts) == 2 and parts[1].isalpha() else None


def parse_contract(code: str, trade_date: str, scope: str | None = None) -> tuple:
    """Parse a futures contract code against a trade date → (product, delivery_year, delivery_month).

    'au2606' (YYMM: SHFE, INE, DCE, GFEX, CFFEX) → ('au', 2026, 6). Three digits (YMM: CZCE, 'SR605') take the
    first year ending in Y whose delivery month is not before the trade month. With ``scope``, the product
    letters must be that scope's product (scope shfe_au accepts only au contracts). Bad input → ValueError."""
    m = _CODE_RE.match(str(code or ""))
    if not m:
        raise ValueError(f"contract {code!r} is not a futures contract code (letters + YYMM, or YMM for CZCE)")
    prod, digits = m.group(1).lower(), m.group(2)
    if scope is not None:
        want = _scope_product(scope)
        if want is None:
            raise ValueError(f"scope {scope!r} is not a single futures product scope; a contract cannot be given")
        if prod != want:
            raise ValueError(f"contract {code!r} is product {prod!r}, but scope {scope!r} is product {want!r}")
    month = int(digits[-2:])
    if not 1 <= month <= 12:
        raise ValueError(f"contract {code!r}: month {month:02d} is not 01-12")
    trade_date = _check_date(trade_date, "trade_date")
    ty, tm = int(trade_date[:4]), int(trade_date[5:7])
    if len(digits) == 4:
        year = 2000 + int(digits[:2])
    else:
        y = int(digits[0])
        year = next(c for c in range(ty, ty + 11) if c % 10 == y and c * 12 + month >= ty * 12 + tm - 0)
    return prod, year, month


def _canonical(code: str, date: str) -> str:
    """'SR605' on 2026-03-02 → 'sr2605': product + YYMM, so CZCE three-digit codes compare like the others."""
    prod, year, month = parse_contract(code, date)
    return f"{prod}{year % 100:02d}{month:02d}"


def _clause_holds(clause: dict, code: str, year: int, month: int, date: str) -> bool:
    ty, tm = int(date[:4]), int(date[5:7])
    feats = {"code": _canonical(code, date), "delivery_month": month,
             "months_to_delivery": (year * 12 + month) - (ty * 12 + tm)}
    for key, cond in clause.items():
        v = feats[key]
        if key == "code":
            if "in" in cond and v not in {_canonical(x, date) for x in cond["in"]}:
                return False
            if "not_in" in cond and v in {_canonical(x, date) for x in cond["not_in"]}:
                return False
            continue
        if "in" in cond and v not in cond["in"]:
            return False
        if "not_in" in cond and v in cond["not_in"]:
            return False
        if "min" in cond and v < cond["min"]:
            return False
        if "max" in cond and v > cond["max"]:
            return False
    return True


def contract_matches(selector: dict, contract: str, date: str, scope: str | None = None) -> bool:
    """Does a ``contracts`` selector cover ``contract`` on trade date ``date``? (``scope`` checks the product.)"""
    d = _check_date(date)
    _, year, month = parse_contract(contract, d, scope)
    if "any" in selector:
        return any(_clause_holds(c, contract, year, month, d) for c in selector["any"])
    return not any(_clause_holds(c, contract, year, month, d) for c in selector["none"])


def _check_contracts(sel, scope: str, where: str) -> dict:
    """Validate a selector's shape; return it with codes lower-cased. Bad data → ValueError (refuse to load)."""
    prod = _scope_product(scope)
    if prod is None:
        raise ValueError(f"{where}: contracts selector needs a single futures product scope (<exchange>_<product>), "
                         f"not {scope!r}")
    if not isinstance(sel, dict) or len(sel) != 1 or next(iter(sel)) not in ("any", "none"):
        raise ValueError(f"{where}: contracts must be {{any: [...]}} or {{none: [...]}}")
    mode, clauses = next(iter(sel.items()))
    if not isinstance(clauses, list) or not clauses:
        raise ValueError(f"{where}: contracts.{mode} must be a non-empty list of clauses")
    out = []
    for c in clauses:
        if not isinstance(c, dict) or not c:
            raise ValueError(f"{where}: each contracts clause must be a non-empty mapping")
        oc = {}
        for key, cond in c.items():
            if key not in _SEL_OPS:
                raise ValueError(f"{where}: unknown contracts key {key!r} (allowed: {sorted(_SEL_OPS)})")
            if not isinstance(cond, dict) or not cond or set(cond) - set(_SEL_OPS[key]):
                raise ValueError(f"{where}: {key} takes a mapping of {_SEL_OPS[key]}")
            oc[key] = {}
            for op, v in cond.items():
                if op in ("in", "not_in"):
                    if not isinstance(v, list) or not v:
                        raise ValueError(f"{where}: {key}.{op} must be a non-empty list")
                    if key == "code":
                        for x in v:
                            m = _CODE_RE.match(str(x))
                            if not m or m.group(1) != prod or len(m.group(2)) != 4 or not 1 <= int(str(x)[-2:]) <= 12:
                                raise ValueError(f"{where}: code {x!r} must be a lower-case {prod}YYMM code "
                                                 "(CZCE three-digit codes are written with four digits in data)")
                    elif key == "delivery_month":
                        if not all(_is_pos_int(x) and x <= 12 for x in v):
                            raise ValueError(f"{where}: delivery_month values must be integers 1-12")
                    elif not all(isinstance(x, int) and not isinstance(x, bool) and x >= 0 for x in v):
                        raise ValueError(f"{where}: months_to_delivery values must be integers >= 0")
                else:
                    if not isinstance(v, int) or isinstance(v, bool) or v < 0:
                        raise ValueError(f"{where}: months_to_delivery.{op} must be an integer >= 0")
                oc[key][op] = v
            if "min" in oc[key] and "max" in oc[key] and oc[key]["min"] > oc[key]["max"]:
                raise ValueError(f"{where}: months_to_delivery min > max")
        out.append(oc)
    return {mode: out}


def _month_iter(start: str, end: str):
    """First day of every calendar month that meets [start, end) — the grain at which selector features change."""
    y, m = int(start[:4]), int(start[5:7])
    while True:
        first = f"{y:04d}-{m:02d}-01"
        if first >= end:
            return
        yield max(first, start)
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def _selector_overlap(a: dict, b: dict, scope: str, start: str, end: str | None) -> str | None:
    """A contract both selectors cover on some day of [start, end), or None if they are disjoint.

    Features change only at month boundaries, so one probe per calendar month is exact. Probes are the codes
    with months_to_delivery 0..60 that month plus every code either selector names. An open end is checked to
    24 months past the later of start and the last named code's delivery (after that nothing changes)."""
    prod = _scope_product(scope)
    named = [x for s in (a, b) for c in next(iter(s.values())) for x in (c.get("code", {}).get("in", []) +
                                                                          c.get("code", {}).get("not_in", []))]
    if end is None:
        last = max([start[:7]] + [f"20{c[-4:-2]}-{c[-2:]}" for c in (_canonical(x, start) for x in named)])
        y, m = int(last[:4]) + 2, int(last[5:7])
        end = f"{y:04d}-{m:02d}-01"
    for day in _month_iter(start, end):
        ty, tm = int(day[:4]), int(day[5:7])
        probes = {_canonical(x, day) for x in named}
        for k in range(61):
            idx = ty * 12 + tm - 1 + k
            probes.add(f"{prod}{(idx // 12) % 100:02d}{idx % 12 + 1:02d}")
        for code in sorted(probes):
            if contract_matches(a, code, day) and contract_matches(b, code, day):
                return f"{code} on {day}"
    return None


@lru_cache(maxsize=None)
def records() -> tuple[Record, ...]:
    """All records across all data files. Loading validates the schema; a bad file raises.

    An installed package reads the precompiled copy (``_compiled``) when it matches the YAML byte for byte; it was
    produced by the same loader below, so the same checks ran when it was built. Otherwise the YAML is parsed."""
    c = _compiled()
    if c is not None:
        return c["records"]
    return _records_from_yaml(DATA_DIR)


def _schema_error(path: str, schema) -> str:
    """Why a data file's ``schema`` cannot be read; for a newer schema, which package to upgrade."""
    if isinstance(schema, (int, float)) and not isinstance(schema, bool) and schema > max(DATA_SCHEMAS):
        return (f"{path}: unsupported or missing schema version: schema {schema} is newer than marina-rules "
                f"{__version__} reads (up to {max(DATA_SCHEMAS)}). Upgrade the code: pip install -U marina-rules")
    return f"{path}: unsupported or missing schema version"


def _records_from_yaml(data_dir: str) -> tuple[Record, ...]:
    out: list[Record] = []
    seen: set[str] = set()
    for path in _iter_files(data_dir):
        with open(path, encoding="utf-8") as fh:
            doc = yaml.safe_load(fh) or {}
        if doc.get("schema") not in DATA_SCHEMAS:
            raise ValueError(_schema_error(path, doc.get("schema")))
        if "records" not in doc:
            continue  # scope registry / known gaps, handled by scopes() / known_gaps()
        default_market = doc.get("market")
        for i, r in enumerate(doc.get("records") or []):
            for req in ("id", "scope", "rule", "value", "effective_from", "verification"):
                if req not in r:
                    raise ValueError(f"{path}: record #{i} missing '{req}'")
            if r["verification"] not in _LEVELS:
                raise ValueError(f"{path}: {r['id']}: verification must be one of {_LEVELS}")
            if r["id"] in seen:
                raise ValueError(f"{path}: duplicate id {r['id']}")
            seen.add(r["id"])
            if r["verification"] != "unverified":
                srcs = r.get("sources") or []
                if not srcs:
                    raise ValueError(f"{path}: {r['id']}: {r['verification']} requires at least one source")
                for s in srcs:
                    sha = str(s.get("content_sha256", ""))
                    if not _SHA_RE.match(sha):
                        raise ValueError(f"{path}: {r['id']}: source {s.get('url')} has no content_sha256 "
                                         f"(run: python scripts/hash_source.py <url>)")
                    if not str(s.get("quote", "")).strip():
                        raise ValueError(f"{path}: {r['id']}: source {s.get('url')} has no verbatim quote")
            ef, et = _norm_date(r["effective_from"]), _norm_date(r.get("effective_to"))
            if et is not None and et <= ef:
                raise ValueError(f"{path}: {r['id']}: effective_to must be after effective_from")
            if r["rule"] in _BAND_TABLE_RULES:
                if not r.get("unit"):
                    raise ValueError(f"{path}: {r['id']}: {r['rule']} needs a unit (the currency of its prices)")
                _check_band_table(r["value"], f"{path}: {r['id']}")
            if r["rule"] in _LULD_RULES:
                if not r.get("unit"):
                    raise ValueError(f"{path}: {r['id']}: {r['rule']} needs a unit (the currency of its prices)")
                _check_luld_band(r["value"], f"{path}: {r['id']}")
            if r["rule"] in _PAUSE_RULES:
                if not r.get("unit"):
                    raise ValueError(f"{path}: {r['id']}: {r['rule']} needs a unit (the currency of its prices)")
                _check_single_stock_pause(r["value"], f"{path}: {r['id']}")
            if r["rule"] in _SHORT_SALE_RULES:
                _check_short_sale_price_test(r["value"], f"{path}: {r['id']}", r.get("market", default_market))
            if r["rule"] in _FRACTION_RULES:
                _check_fraction(r["rule"], r["value"], f"{path}: {r['id']}")
            if r["rule"] in _BOOL_RULES:
                _check_bool(r["rule"], r["value"], f"{path}: {r['id']}")
            if r["rule"] in _PER_LOT_FEE_RULES:
                _check_per_lot_fee(r["rule"], r["value"], r.get("unit"), f"{path}: {r['id']}")
            if r["rule"] in _ORDER_SPREAD_RULES:
                _check_order_spread_limit(r["value"], f"{path}: {r['id']}", r.get("market", default_market))
            if r["rule"] in _ORDER_MULTIPLE_RULES:
                _check_order_price_multiple_limit(r["value"], f"{path}: {r['id']}", r.get("market", default_market))
            if r["rule"] in _PDT_RULES:
                if not r.get("unit"):
                    raise ValueError(f"{path}: {r['id']}: {r['rule']} needs a unit (the currency of min_equity)")
                _check_pattern_day_trader(r["value"], f"{path}: {r['id']}")
            sel = None
            if r.get("contracts") is not None:
                if doc.get("schema") != _SCHEMA_SELECTORS:
                    raise ValueError(f"{path}: {r['id']}: a contracts selector needs schema: {_SCHEMA_SELECTORS} "
                                     "(older readers would ignore it and misread the record)")
                sel = _check_contracts(r["contracts"], r["scope"], f"{path}: {r['id']}")
            out.append(Record(
                id=r["id"], market=r.get("market", default_market), scope=r["scope"], rule=r["rule"],
                value=_iso_dates(r["value"]), effective_from=ef, effective_to=et, verification=r["verification"],
                sources=tuple(_iso_dates(dict(x)) for x in (r.get("sources") or ())), notes=r.get("notes") or "",
                file=os.path.relpath(path, data_dir),
                published_at=_norm_date(r.get("published_at")), recorded_at=_norm_date(r.get("recorded_at")),
                unit=r.get("unit"), contracts=sel,
            ))
    _reject_overlaps(out)
    return tuple(out)


def _market_set(m: str | None) -> frozenset | None:
    """'XSHG+XSHE' → {'XSHG', 'XSHE'}; None (any market) → None."""
    return None if m is None else frozenset(m.split("+"))


def _markets_intersect(a: str | None, b: str | None) -> bool:
    """Two market strings overlap if their SETS intersect ('XSHG+XSHE' and 'XSHE' do). None overlaps everything."""
    sa, sb = _market_set(a), _market_set(b)
    return sa is None or sb is None or bool(sa & sb)


def _reject_overlaps(recs: list) -> None:
    """Two records of one (scope, rule) whose market SETS intersect may not be in force on the same day.

    'XSHG+XSHE' and 'XSHE' intersect: a query for XSHE would see both. Data error → refuse to load.
    Exception: two records that both carry a ``contracts`` selector may share days when no contract is covered
    by both (checked exactly, month by month). A record without a selector covers every contract.
    """
    by: dict = {}
    for r in recs:
        by.setdefault((r.scope, r.rule), []).append(r)
    for key, rs in by.items():
        rs = sorted(rs, key=lambda r: r.effective_from)
        for i, a in enumerate(rs):
            a_end = a.effective_to or "9999-12-31"
            for b in rs[i + 1:]:
                if b.effective_from >= a_end:
                    break   # sorted by start: no later record can overlap a
                if _markets_intersect(a.market, b.market):
                    if a.contracts is not None and b.contracts is not None:
                        lo = max(a.effective_from, b.effective_from)
                        hi = min(x for x in (a.effective_to, b.effective_to) if x) if (a.effective_to or b.effective_to) else None
                        both = _selector_overlap(a.contracts, b.contracts, a.scope, lo, hi)
                        if both is None:
                            continue
                        raise ValueError(f"overlapping contract selectors for {key}: {a.id} and {b.id} both cover {both}")
                    raise ValueError(f"overlapping records for {key} (markets {a.market} / {b.market}): {a.id} "
                                     f"[{a.effective_from},{a_end}) and {b.id} from {b.effective_from}. Close the "
                                     "earlier record with effective_to, or make the market sets disjoint.")


# Markets whose scope registry and known gaps live in their own data/<prefix>/ directory. Every other market
# (A-share, Chinese futures) and ``market=None`` use data/cn/.
_PREFIX_BY_MARKET = {"XHKG": "hk", "XNYS": "us", "XNAS": "us"}


def market_prefix_for(market: str | None) -> str:
    """The data/<prefix>/ directory holding the scope registry and known gaps for ``market``: 'hk' for XHKG,
    'us' for XNYS, XNAS and XNYS+XNAS, 'cn' for everything else (including ``None`` and any '+' set that mixes
    families)."""
    if market is None:
        return "cn"
    prefixes = {_PREFIX_BY_MARKET.get(m, "cn") for m in str(market).split("+")}
    return prefixes.pop() if len(prefixes) == 1 else "cn"


@lru_cache(maxsize=None)
def scopes(market_prefix: str = "cn") -> dict:
    """Scope registry: {scope: {description, requires, excludes, asserts, rule_asserts}} for one market family.

    ``asserts`` / ``rule_asserts`` are the declarative context constraints checked by contract.resolve
    (see the constraint grammar at the top of data/<market>/scopes.yaml)."""
    c = _compiled()
    if c is not None and market_prefix in c["scopes"]:
        return c["scopes"][market_prefix]
    return _scopes_from_yaml(DATA_DIR, market_prefix)   # also any prefix the precompiled copy does not list


def _scopes_from_yaml(data_dir: str, market_prefix: str) -> dict:
    path = os.path.join(data_dir, market_prefix, "scopes.yaml")
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as fh:
        doc = yaml.safe_load(fh) or {}
    out = {}
    for name, spec in (doc.get("scopes") or {}).items():
        out[name] = {"description": spec.get("description", ""),
                     "requires": tuple(spec.get("requires") or ()),
                     "excludes": tuple(spec.get("excludes") or ()),
                     "asserts": _iso_dates(spec.get("asserts") or {}),
                     "rule_asserts": _iso_dates(spec.get("rule_asserts") or {})}
    return out


class RuleConflict(LookupError):
    """More than one record of the same (market, scope, rule) is in force on the date.

    Marina does not pick one. Overlapping records are a data error (intervals of one key must be
    disjoint); report it rather than silently preferring the newest.
    """


class NotYetPublished(KeyError):
    """``as_of`` given, and the record in force on the date was officially published only AFTER ``as_of``.

    The answer was not knowable at ``as_of``. Marina does not fall back to the predecessor record: a backtest
    standing at ``as_of`` must not learn the future rule, and "what a trader at as_of believed" is a different
    question the caller decides. Attributes: ``record``, ``as_of``.
    """

    def __init__(self, record: "Record", as_of: str):
        self.record, self.as_of = record, as_of
        super().__init__(f"{record.id} (in force from {record.effective_from}) was published {record.published_at}, "
                         f"after as_of {as_of} — not knowable at as_of")

    def __str__(self):
        return self.args[0]


class PublicationUnknown(KeyError):
    """``as_of`` given, and the record in force on the date has ``published_at: null`` (the original notice's
    date was not located). Unknown, not absent: Marina cannot say whether it was public at ``as_of``.
    Attributes: ``record``, ``as_of``.
    """

    def __init__(self, record: "Record", as_of: str):
        self.record, self.as_of = record, as_of
        super().__init__(f"{record.id} (in force from {record.effective_from}) has no published_at — whether it was "
                         f"public on as_of {as_of} is unknown")

    def __str__(self):
        return self.args[0]


_ISO_RE = _re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _check_as_of(as_of) -> str | None:
    """Validate ``as_of``: None, or an ISO ``YYYY-MM-DD`` string (a ``datetime.date`` is accepted). Else ValueError."""
    import datetime as _dt
    if as_of is None:
        return None
    if isinstance(as_of, _dt.date) and not isinstance(as_of, _dt.datetime):
        return as_of.isoformat()
    if not isinstance(as_of, str) or not _ISO_RE.match(as_of):
        raise ValueError(f"as_of must be an ISO date 'YYYY-MM-DD', got {as_of!r}")
    try:
        _dt.date.fromisoformat(as_of)
    except ValueError:
        raise ValueError(f"as_of must be a valid ISO date 'YYYY-MM-DD', got {as_of!r}") from None
    return as_of


_DAY_RE = _re.compile(r"^(\d{4}-\d{2}-\d{2})(?:[T ].*)?$", _re.S)
_LOOSE_DAY_RE = _re.compile(r"^(\d{4})([-/.]?)(\d{1,2})\2(\d{1,2})$")


def _date_hint(text: str) -> str:
    """' — did you mean ...?' for the common non-ISO spellings (20200102, 2020/1/2, 2020-1-2), else ''."""
    import datetime as _dt
    t = text.strip()
    m = _LOOSE_DAY_RE.match(t)
    if not m or (m.group(2) == "" and len(t) != 8):
        return ""
    try:
        return f" — did you mean {_dt.date(int(m.group(1)), int(m.group(3)), int(m.group(4))).isoformat()!r}?"
    except ValueError:
        return ""


@lru_cache(maxsize=8192)
def _iso_day(text: str, name: str) -> str:
    import datetime as _dt
    m = _DAY_RE.match(text)
    if m:
        try:
            _dt.date.fromisoformat(m.group(1))
            return m.group(1)
        except ValueError:
            pass
    raise ValueError(f"{name} must be an ISO date 'YYYY-MM-DD' (or a datetime.date / datetime), got {text!r}"
                     + _date_hint(text))


def _check_date(date, name: str = "date") -> str:
    """The query date as ``YYYY-MM-DD``, or ValueError. Never a guess.

    Accepted: an ISO ``YYYY-MM-DD`` string, optionally followed by a time (``2020-01-02 09:30:00``,
    ``2020-01-02T09:30:00``); a ``datetime.date`` / ``datetime`` (pandas Timestamp included); any other object whose
    ``str()`` is such a string (numpy datetime64). Everything else is refused — ``20200102``, ``2020/01/02``,
    ``2020-1-2``, an int, None: dates are compared as ISO text, so a different spelling would silently select the
    wrong rule interval rather than fail."""
    import datetime as _dt
    if type(date) is str:
        return _iso_day(date, name)
    if isinstance(date, _dt.datetime):
        return _iso_day(str(date.date()), name)
    if isinstance(date, _dt.date):
        return _iso_day(date.isoformat(), name)
    if date is None or isinstance(date, (bool, int, float)):
        raise ValueError(f"{name} must be an ISO date 'YYYY-MM-DD' (or a datetime.date / datetime), got {date!r}"
                         + _date_hint(str(date)))
    return _iso_day(str(date), name)


def publication_state(rec: "Record", as_of: str | None) -> str:
    """'visible' | 'unknown' (published_at null) | 'not_yet' (published after as_of). as_of None → 'visible'."""
    if as_of is None:
        return "visible"
    if rec.published_at is None:
        return "unknown"
    return "visible" if rec.published_at <= as_of else "not_yet"


def _require_published(rec: "Record", as_of: str | None) -> "Record":
    st = publication_state(rec, as_of)
    if st == "unknown":
        raise PublicationUnknown(rec, as_of)
    if st == "not_yet":
        raise NotYetPublished(rec, as_of)
    return rec


def _market_matches(record_market: str | None, wanted: str | None) -> bool:
    """A record applies to the wanted market iff the wanted set is a subset of the record's set.

    'XSHG+XSHE' record ⊇ 'XSHE' request → match. 'XSHE' record vs 'XSHG+XSHE' request → NO match: a
    ChiNext-only rule must never satisfy a query about both main boards. ``wanted=None`` matches all.
    """
    if wanted is None or record_market is None:
        return True
    return set(wanted.split("+")) <= set(record_market.split("+"))


@lru_cache(maxsize=None)
def known_gaps(market_prefix: str = "cn") -> tuple:
    """Declared gaps: (market, scope, rule, interval) Marina knows it does not cover, with reason and status."""
    c = _compiled()
    if c is not None and market_prefix in c["known_gaps"]:
        return c["known_gaps"][market_prefix]
    return _gaps_from_yaml(DATA_DIR, market_prefix)


def _gaps_from_yaml(data_dir: str, market_prefix: str) -> tuple:
    path = os.path.join(data_dir, market_prefix, "known_gaps.yaml")
    if not os.path.exists(path):
        return ()
    with open(path, encoding="utf-8") as fh:
        doc = yaml.safe_load(fh) or {}
    out = []
    for g in doc.get("gaps") or []:
        iv = g.get("interval") or {}
        g = {**g, "interval": {"from": _norm_date(iv.get("from")), "to": _norm_date(iv.get("to"))}}
        if g.get("contracts") is not None:
            if doc.get("schema") != _SCHEMA_SELECTORS:
                raise ValueError(f"{path}: {g.get('gap_id')}: a contracts selector needs schema: {_SCHEMA_SELECTORS}")
            g["contracts"] = _check_contracts(g["contracts"], g["scope"], f"{path}: {g.get('gap_id')}")
        out.append(g)
    return tuple(out)


def gaps_for(market: str | None, scope: str, rule: str, start: str, end: str, market_prefix: str | None = None,
             *, contract: str | None = None) -> list:
    """Known gaps overlapping [start, end) for this (market, scope, rule). Market matching is set-overlap.
    ``market_prefix`` None: the registry of ``market`` (``market_prefix_for``). With ``contract``, a gap that carries
    a ``contracts`` selector counts only if it covers that contract on ``start`` (callers cut ranges at month
    boundaries, where selector features change); without one, every overlapping gap counts."""
    start = _check_date(start, "start")
    if isinstance(end, str) and end.endswith("\x00"):
        _check_date(end[:-1], "end")   # [d, d + "\x00"): the single day d, as resolve() asks
    else:
        end = _check_date(end, "end")
    hits = []
    for g in known_gaps(market_prefix or market_prefix_for(market)):
        if g["scope"] != scope or g["rule"] != rule:
            continue
        if market is not None and g.get("market") and not (set(market.split("+")) & set(g["market"].split("+"))):
            continue
        g0, g1 = g["interval"]["from"] or "0000-01-01", g["interval"]["to"] or "9999-12-31"
        if g0 < end and start < g1:
            if contract is not None and g.get("contracts") is not None and \
                    not contract_matches(g["contracts"], contract, max(start, g0)[:10], scope):
                continue
            hits.append(g)
    return hits


# ------------------------------------------------------------------------------------------------- tracking registry
# data/<prefix>/tracking.yaml says, per market (and optionally per scope family), up to which date the maintainer has
# checked the official sources for rule changes (docs/SCHEMA.md "Tracking registry"). For a date <= tracked_through an
# open-ended record (effective_to: null) states what the sources said; for a later date it is a carry-forward, not a
# finding. A market without an entry is untracked: nothing is defaulted. Not part of dataset_digest().
TRACKING_PREFIXES = ("cn", "hk", "us")
_TRACKING_KEYS = frozenset({"market", "scopes", "tracked_through", "basis", "updated"})


def _strict_date(v, where: str) -> str:
    """A YAML date or an ISO 'YYYY-MM-DD' string → ISO string; anything else → ValueError."""
    import datetime as _dt
    if isinstance(v, _dt.date) and not isinstance(v, _dt.datetime):
        return v.isoformat()
    if isinstance(v, str) and _ISO_RE.match(v):
        try:
            return _dt.date.fromisoformat(v).isoformat()
        except ValueError:
            pass
    raise ValueError(f"{where}: need a date YYYY-MM-DD, got {v!r}")


def _expand_scopes(patterns, prefix: str, where: str, scopes_of=None) -> frozenset:
    """Scope names, or patterns ending in '*' (a scope family by name prefix, e.g. 'cffex_t*'), against the registry
    of ``prefix`` (``scopes_of(prefix)``, default ``scopes``). Every name must exist and every pattern must match at
    least one scope."""
    reg = (scopes if scopes_of is None else scopes_of)(prefix)
    out: set = set()
    if not isinstance(patterns, list) or not patterns or not all(isinstance(p, str) and p for p in patterns):
        raise ValueError(f"{where}: scopes must be a non-empty list of scope names (or 'family_*' patterns)")
    for p in patterns:
        hit = {s for s in reg if s.startswith(p[:-1])} if p.endswith("*") else ({p} if p in reg else set())
        if not hit:
            raise ValueError(f"{where}: scope {p!r} is not in data/{prefix}/scopes.yaml")
        out |= hit
    return frozenset(out)


def _load_tracking(path: str, prefix: str, known_markets: frozenset, data_dir: str | None = None,
                   scopes_of=None) -> list:
    with open(path, encoding="utf-8") as fh:
        doc = yaml.safe_load(fh) or {}
    if doc.get("schema") != 1:
        raise ValueError(f"{path}: unsupported or missing schema version (tracking registry is schema: 1)")
    entries = doc.get("tracking")
    if not isinstance(entries, list):
        raise ValueError(f"{path}: 'tracking' must be a list of entries")
    out = []
    for i, e in enumerate(entries):
        where = f"{path}: entry #{i}"
        if not isinstance(e, dict) or set(e) - _TRACKING_KEYS or not {"market", "tracked_through", "basis", "updated"} <= set(e):
            raise ValueError(f"{where}: needs market, tracked_through, basis, updated (optional scopes) and no other key")
        mkts = str(e["market"]).split("+")
        for m in mkts:
            if m not in known_markets:
                raise ValueError(f"{where}: market {m!r} has no record in data/{prefix}/")
        tt = _strict_date(e["tracked_through"], f"{where}: tracked_through")
        up = _strict_date(e["updated"], f"{where}: updated")
        if tt > up:
            raise ValueError(f"{where}: tracked_through {tt} is after updated {up} (sources cannot have been checked "
                             "beyond the day the entry was written)")
        if not (isinstance(e["basis"], str) and e["basis"].strip()):
            raise ValueError(f"{where}: basis must be a non-empty string (how the sources were checked)")
        sc = None if e.get("scopes") is None else _expand_scopes(e["scopes"], prefix, where, scopes_of)
        out.append({"market": str(e["market"]), "markets": tuple(mkts), "scopes": sc,
                    "scope_patterns": None if sc is None else tuple(e["scopes"]), "tracked_through": tt,
                    "basis": e["basis"].strip(), "updated": up,
                    "file": os.path.relpath(path, DATA_DIR if data_dir is None else data_dir)})
    return out


@lru_cache(maxsize=None)
def _tracking_entries() -> tuple:
    c = _compiled()
    if c is not None:
        return c["tracking"]
    return _tracking_from_yaml(DATA_DIR, records(), scopes)


def _tracking_from_yaml(data_dir: str, recs, scopes_of) -> tuple:
    out: list = []
    for prefix in TRACKING_PREFIXES:
        path = os.path.join(data_dir, prefix, TRACKING_FILE)
        if not os.path.exists(path):
            continue
        known = frozenset(m for r in recs if r.file.startswith(prefix + "/") for m in (r.market or "").split("+"))
        out += _load_tracking(path, prefix, known, data_dir, scopes_of)
    _check_tracking_overlaps(out)
    return tuple(out)


def _check_tracking_overlaps(entries: list) -> None:
    """No two entries may cover the same (market, scope); an entry without ``scopes`` covers every scope."""
    for i, a in enumerate(entries):
        for b in entries[i + 1:]:
            common = set(a["markets"]) & set(b["markets"])
            if not common:
                continue
            if a["scopes"] is None or b["scopes"] is None or a["scopes"] & b["scopes"]:
                both = "every scope" if a["scopes"] is None or b["scopes"] is None else sorted(a["scopes"] & b["scopes"])
                raise ValueError(f"tracking registry: entries for {a['market']} ({a['file']}) and {b['market']} "
                                 f"({b['file']}) both cover market {sorted(common)} / {both}")


def tracking_registry(market_prefix: str | None = None) -> list:
    """The tracking registry as a list of ``{market, scopes, tracked_through, basis, updated}`` (``scopes`` None = every
    scope of the market; otherwise the scope names or ``family_*`` patterns as written). ``market_prefix`` 'cn' / 'hk' /
    'us' limits it to one data/<prefix>/tracking.yaml. A market that appears in no entry is untracked."""
    return [{"market": e["market"], "scopes": None if e["scope_patterns"] is None else list(e["scope_patterns"]),
             "tracked_through": e["tracked_through"], "basis": e["basis"], "updated": e["updated"]}
            for e in _tracking_entries() if market_prefix is None or e["file"].startswith(market_prefix + "/")]


def _tracked_one(mic: str, scope: str | None) -> str | None:
    es = [e for e in _tracking_entries() if mic in e["markets"]]
    if scope is not None:
        hit = [e for e in es if e["scopes"] is None or scope in e["scopes"]]
        return hit[0]["tracked_through"] if hit else None
    if not es:
        return None
    if any(e["scopes"] is None for e in es):
        return next(e for e in es if e["scopes"] is None)["tracked_through"]
    covered = frozenset().union(*(e["scopes"] for e in es))
    needed = {r.scope for r in records() if mic in (r.market or "").split("+")}
    return min(e["tracked_through"] for e in es) if needed <= covered else None


def tracked_through(market: str | None, scope: str | None = None) -> str | None:
    """Last date (ISO) up to which the official sources for ``market`` (and ``scope``) were checked for rule changes, or
    ``None`` when untracked. A '+' market ('XNYS+XNAS') takes the earliest of its members and is untracked if any member
    is. ``scope`` None asks about every scope of the market: the earliest date of the entries, or None if some scope with
    records is not covered. ``market`` None → None (no market, no tracking statement)."""
    if market is None:
        return None
    dates = [_tracked_one(m, scope) for m in str(market).split("+")]
    return None if any(d is None for d in dates) else min(dates)


def tracking_state(market: str | None, scope: str | None, date: str) -> dict:
    """``{tracked_through, beyond}`` for a query date: ``beyond`` is True when ``date`` > tracked_through, False when on
    or before it, None when the market (or scope) is untracked."""
    tt = tracked_through(market, scope)
    return {"tracked_through": tt, "beyond": None if tt is None else _check_date(date) > tt}


class BeyondTracking(KeyError):
    """``require_tracked=True`` and the answer would come from an open-ended record (``effective_to`` null) on a date
    after the market's ``tracked_through`` — or the market is untracked. The value would be a carry-forward, not a
    checked finding. Attributes: ``record``, ``date``, ``tracked_through`` (None = untracked)."""

    def __init__(self, record: "Record", date: str, tracked: str | None):
        self.record, self.date, self.tracked_through = record, date, tracked
        why = (f"tracked only through {tracked}" if tracked else "not tracked (no entry in data/<prefix>/tracking.yaml)")
        super().__init__(f"{record.id} is open-ended and {date} is beyond what was checked: market {record.market} is "
                         f"{why}; the value would be a carry-forward, not a finding")

    def __str__(self):
        return self.args[0]


def _require_tracked(rec: "Record", date: str, market: str | None, scope: str) -> "Record":
    if rec.effective_to is not None:
        return rec    # a closed record's end is a sourced fact
    tt = tracked_through(market or rec.market, scope)
    if tt is None or date > tt:
        raise BeyondTracking(rec, date, tt)
    return rec


def record_at(rule: str, date: str, scope: str = "stock", market: str | None = None,
              strict: bool = False, *, as_of: str | None = None, contract: str | None = None,
              require_tracked: bool = False) -> Record:
    """The record for ``rule``/``scope`` in force on ``date``.

    ``market`` of None matches any market. ``strict=True`` ignores ``unverified`` records.
    Raises ``KeyError`` if nothing is in force — callers must not substitute a default.
    Raises ``RuleConflict`` if more than one record of the same key is in force (data error).

    ``as_of`` (ISO date, keyword-only): answer using only rules officially published on or before ``as_of``.
    The record in force on ``date`` is found exactly as without ``as_of``; then, if its ``published_at`` is
    null → ``PublicationUnknown``, if later than ``as_of`` → ``NotYetPublished`` (both subclass ``KeyError``;
    no fallback to an older record). ``as_of=None`` (default): unchanged. See docs/SCHEMA.md "as_of".

    ``contract`` (keyword-only, futures): the exchange contract code, e.g. ``'au2606'``. Needed when the records in
    force carry a ``contracts`` selector (the rule differs between contracts that day); otherwise
    ``ContractRequired`` (a ``KeyError``). Records without a selector cover every contract, so passing a contract
    is always safe for futures scopes. Its product must be the scope's (``ValueError`` otherwise).
    See docs/SCHEMA.md "Contract selectors".

    ``require_tracked`` (keyword-only, default False = unchanged): refuse a carry-forward. When the record found is
    open-ended (``effective_to`` null) and ``date`` is after ``tracked_through(market or record.market, scope)``, or that
    market is untracked, raise ``BeyondTracking`` (a ``KeyError``). A closed record is never refused: its end is sourced.
    See docs/SCHEMA.md "Tracking registry".
    """
    as_of = _check_as_of(as_of)
    d = _check_date(date)
    if contract is not None:
        parse_contract(contract, d, scope)
    hits: list[Record] = []
    for r in records():
        if r.rule != rule or r.scope != scope:
            continue
        if not _market_matches(r.market, market):
            continue
        if strict and r.verification == "unverified":
            continue
        if r.active_on(d):
            hits.append(r)
    keyed = [h for h in hits if h.contracts is not None]
    if keyed and contract is None:
        raise ContractRequired(f"{rule}/{scope} differs by contract on {d} ({', '.join(h.id for h in keyed)}); "
                               "supply contract=<code>", tuple(hits))
    if contract is not None:
        hits = [h for h in hits if h.applies_to(contract, d)]
    if not hits:
        raise KeyError(f"no {rule}/{scope} rule in force on {d}" + (" (strict)" if strict else "")
                       + (f" for contract {contract}" if keyed else "") + _miss_hint(rule, scope, market, d))
    if _conflicting(hits, market):
        raise RuleConflict(f"{len(hits)} records of {rule}/{scope} in force on {d}: " + ", ".join(h.id for h in hits))
    rec = _require_published(hits[0], as_of)
    return _require_tracked(rec, d, market, scope) if require_tracked else rec


def _conflicting(hits: list, market: str | None) -> bool:
    """Do these in-force records of one (scope, rule) conflict for a query about ``market``?

    Two records conflict when their market SETS intersect and the requested market lies in both — 'XSHG+XSHE'
    and 'XSHE' conflict for an XSHE query. Every hit already contains the requested market (subset matching),
    so with a market given any second hit is a conflict. With ``market=None`` (any market) more than one hit
    is a conflict too: Marina will not pick an exchange for the caller.
    """
    if len(hits) < 2:
        return False
    if market is None:
        return True
    want = _market_set(market)
    return any(want <= _market_set(a.market) and want <= _market_set(b.market)
               for i, a in enumerate(hits) for b in hits[i + 1:])


def coverage(market: str, scope: str, rules: Iterable[str], start: str, end: str,
             strict: bool = False, market_prefix: str | None = None, *, as_of: str | None = None,
             contract: str | None = None, require_tracked: bool = False) -> dict:
    """Pre-flight for a backtest window: can Marina answer every (rule, day) in [start, end)?

    Returns a dict:
      status            complete | partial | unsupported
      gaps              [{rule, from, to}] half-open date ranges with no record in force
      conflicts         [{rule, date, record_ids}] days where more than one record is in force
      verification      lowest level among records used (verified > single-source > unverified)
      required_context  what the caller must know per security to legitimately select ``scope``
      excludes          scopes that must not be selected together with ``scope``
      records           ids of every record touched
      known_gap_ids     declared gaps (data/<market>/known_gaps.yaml) overlapping the gaps/unsupported scope —
                        a gap with an id is a known unknown; a gap without one is a genuine blind spot
      dataset_digest / citation
    ``market_prefix`` (the data/<prefix>/ registry for scopes and known gaps) defaults to ``market_prefix_for(market)``:
    'hk' for XHKG, 'us' for XNYS / XNAS, 'cn' otherwise.
    With ``as_of`` (ISO date, keyword-only) three more keys are returned — ``as_of``, ``publication_unknown``
    and ``not_yet_published`` ([{rule, from, to, record_ids}]): ranges whose in-force record has
    ``published_at`` null, or was published after ``as_of``. Both make the status ``partial``. Without
    ``as_of`` the result is unchanged (these keys are absent).
    Futures rules that differ by contract (records with a ``contracts`` selector): pass ``contract`` (keyword-only,
    e.g. ``'au2606'``) to check that one contract; the result then carries ``contract``. Without it, the ranges
    where the answer depends on the contract are listed under ``contract_required`` ([{rule, from, to,
    record_ids}]), ``contract`` joins ``required_context`` and the status is ``partial``. Neither key appears
    when no selector is involved, so existing output is unchanged.
    Tracking (docs/SCHEMA.md "Tracking registry"; additive keys, always present): ``tracking`` = ``{tracked_through,
    beyond}`` for (market, scope) — ``beyond`` is the part ``{from, to}`` of the window after ``tracked_through`` (None if
    there is none; both None when the market is untracked) — and ``beyond_tracking`` ([{rule, from, to, record_ids}]):
    ranges answered by an open-ended record after ``tracked_through`` (or anywhere, when untracked), i.e. carry-forwards.
    They do not change ``status`` unless ``require_tracked=True`` (keyword-only), which makes them ``partial``.
    ``complete`` means: no gaps, no conflicts, for exactly these rules, this scope, this interval.
    It says nothing about rules or scopes not asked for. ``unsupported`` means no record of any asked
    rule exists for this scope at all — the scope/market is not covered, not merely gappy.
    """
    import datetime as _dt
    as_of = _check_as_of(as_of)
    market_prefix = market_prefix or market_prefix_for(market)
    rules = list(rules)
    s0, s1 = _dt.date.fromisoformat(_check_date(start, "start")), _dt.date.fromisoformat(_check_date(end, "end"))
    if s1 <= s0:
        raise ValueError("end must be after start (half-open interval)")
    reg = scopes(market_prefix).get(scope)
    out = {"market": market, "scope": scope, "rules": rules, "start": s0.isoformat(), "end": s1.isoformat(),
           "status": "complete", "gaps": [], "conflicts": [], "records": [], "verification": None,
           "required_context": list(reg["requires"]) if reg else [], "excludes": list(reg["excludes"]) if reg else [],
           "scope_known": reg is not None, "dataset_digest": dataset_digest(), "citation": citation()}
    if as_of is not None:
        out.update({"as_of": as_of, "publication_unknown": [], "not_yet_published": []})
    tt = tracked_through(market, scope)
    tt_next = None if tt is None else _dt.date.fromisoformat(tt) + _dt.timedelta(days=1)
    out["tracking"] = {"tracked_through": tt,
                       "beyond": ({"from": max(s0, tt_next).isoformat(), "to": s1.isoformat()}
                                  if tt_next is not None and tt_next < s1 else None)}
    out["beyond_tracking"] = []
    levels = {"verified": 0, "single-source": 1, "unverified": 2}
    worst = -1
    touched: set[str] = set()
    any_record_for_scope = False
    need_contract: list = []
    keyed_used = False
    for rule in rules:
        lscope = lookup_scope(rule, scope, market)   # tick_size: instrument family, same as tick_size() / resolve()
        if contract is not None:
            parse_contract(contract, s0.isoformat(), lscope)
        cands = [r for r in records() if r.rule == rule and r.scope == lscope and _market_matches(r.market, market)
                 and not (strict and r.verification == "unverified")]
        if cands:
            any_record_for_scope = True
        selectors = any(r.contracts is not None for r in cands) or any(
            g.get("contracts") is not None for g in gaps_for(market, lscope, rule, s0.isoformat(), s1.isoformat(), market_prefix))
        # walk day by day over interval boundaries only (records change at effective_from/effective_to)
        cuts = {s0, s1}
        for r in cands:
            for b in (r.effective_from, r.effective_to):
                if b:
                    bd = _dt.date.fromisoformat(b)
                    if s0 < bd < s1:
                        cuts.add(bd)
        if contract is not None and selectors:   # selector features change at month boundaries
            cuts.update(_dt.date.fromisoformat(x) for x in _month_iter(s0.isoformat(), s1.isoformat()))
        cuts = sorted(cuts)
        for a, b in zip(cuts, cuts[1:]):
            active = [r for r in cands if r.active_on(a.isoformat())]
            if contract is None and any(r.contracts is not None for r in active):
                need_contract.append({"rule": rule, "from": a.isoformat(), "to": b.isoformat(),
                                      "record_ids": [r.id for r in active]})
                continue
            if contract is not None:
                keyed_used |= any(r.contracts is not None for r in active)
                active = [r for r in active if r.applies_to(contract, a.isoformat())]
            if not active:
                kg = gaps_for(market, lscope, rule, a.isoformat(), b.isoformat(), market_prefix, contract=contract)
                out["gaps"].append({"rule": rule, "from": a.isoformat(), "to": b.isoformat(),
                                    "known_gap_ids": [g["gap_id"] for g in kg],
                                    "known": [{"gap_id": g["gap_id"], "severity": g["severity"], "status": g["status"],
                                               "reason": g["reason"]} for g in kg]})
            elif _conflicting(active, market):
                out["conflicts"].append({"rule": rule, "from": a.isoformat(), "to": b.isoformat(),
                                         "record_ids": [r.id for r in active]})
            else:
                if as_of is not None:
                    for key, st in (("publication_unknown", "unknown"), ("not_yet_published", "not_yet")):
                        ids = [r.id for r in active if publication_state(r, as_of) == st]
                        if ids:
                            out[key].append({"rule": rule, "from": a.isoformat(), "to": b.isoformat(), "record_ids": ids})
                open_ids = [r.id for r in active if r.effective_to is None]
                lo = a if tt_next is None else max(a, tt_next)
                if open_ids and lo < b:
                    out["beyond_tracking"].append({"rule": rule, "from": lo.isoformat(), "to": b.isoformat(),
                                                   "record_ids": open_ids})
            for r in active:
                touched.add(r.id); worst = max(worst, levels[r.verification])
    out["records"] = sorted(touched)
    if contract is not None:
        out["contract"] = contract
    if need_contract:
        out["contract_required"] = need_contract
    if (need_contract or keyed_used) and "contract" not in out["required_context"]:
        out["required_context"].append("contract")
    out["known_gap_ids"] = sorted({gid for g in out["gaps"] for gid in g["known_gap_ids"]})
    if not any_record_for_scope:
        # unsupported — but is it a *known* unknown? An agent should report G-xxxx, not just "no rule".
        kg = [g for r in rules for g in gaps_for(market, lookup_scope(r, scope, market), r, s0.isoformat(), s1.isoformat(), market_prefix)]
        out["known_gap_ids"] = sorted({g["gap_id"] for g in kg})
        out["known"] = [{"gap_id": g["gap_id"], "severity": g["severity"], "status": g["status"], "reason": g["reason"]} for g in kg]
    out["verification"] = {0: "verified", 1: "single-source", 2: "unverified"}.get(worst)
    if not any_record_for_scope:
        out["status"] = "unsupported"
    elif out["gaps"] or out["conflicts"] or out.get("publication_unknown") or out.get("not_yet_published") \
            or out.get("contract_required") or (require_tracked and out["beyond_tracking"]):
        out["status"] = "partial"
    return out


def rule_at(rule: str, date: str, scope: str = "stock", market: str | None = None, strict: bool = False,
            *, as_of: str | None = None, contract: str | None = None, require_tracked: bool = False):
    """Value of ``rule`` in force on ``date``. See ``record_at`` (including ``as_of``, ``contract`` and
    ``require_tracked``)."""
    return record_at(rule, date, scope, market, strict, as_of=as_of, contract=contract,
                     require_tracked=require_tracked).value


@lru_cache(maxsize=None)
def _rules_recorded(scope: str, market: str | None) -> dict:
    """rule → sorted tuple of (effective_from, effective_to) of the records stored under exactly ``scope``."""
    out: dict = {}
    for r in records():
        if r.scope == scope and _market_matches(r.market, market):
            out.setdefault(r.rule, set()).add((r.effective_from, r.effective_to))
    return {k: tuple(sorted(v, key=lambda t: (t[0], t[1] or "9999-12-31"))) for k, v in sorted(out.items())}


def rules_for(scope: str = "stock", market: str | None = None) -> dict:
    """Rule names the dataset holds for ``scope`` → their intervals ``[[effective_from, effective_to], …]``
    (``effective_to`` None = open-ended), both sorted.

    ``market`` filters as in ``record_at`` (None = any market). Rules recorded per instrument family (``tick_size``)
    are listed from the family of ``scope``, as ``tick_size()`` and ``resolve()`` look them up. An empty dict means
    the dataset holds nothing for that scope / market — not that the instrument has no rules.

    Ask for a rule by the exact name listed here: a name that is absent cannot be answered, and a similar-looking
    name is a different rule (``price_limit_pct`` is a fraction of the previous close; futures scopes carry
    ``price_limit_pct_of_prev_settlement``)."""
    out = {k: [list(iv) for iv in v] for k, v in _rules_recorded(scope, market).items()}
    for rule in _FAMILY_RULES:
        fam = _family_scope(rule, scope, market)
        ivs = _rules_recorded(fam, market).get(rule) if fam else None
        if ivs:
            out[rule] = [list(iv) for iv in ivs]
    return dict(sorted(out.items()))


@lru_cache(maxsize=None)
def _market_codes() -> tuple:
    """Every market code a record carries (ISO 10383 MICs), sorted; a '+'-joined market counts once per code."""
    return tuple(sorted({m for r in records() for m in r.market.split("+")}))


@lru_cache(maxsize=None)
def _scopes_recording(rule: str) -> tuple:
    return tuple(sorted({r.scope for r in records() if r.rule == rule}))


def markets_recorded(scope: str) -> list:
    """Market codes on which the dataset holds any record stored under ``scope`` (sorted; [] = none)."""
    return sorted({m for r in records() if r.scope == scope for m in r.market.split("+")})


def _family_scope(rule: str, scope: str, market: str | None) -> str | None:
    """The family scope holding ``rule`` for ``scope`` when that is another scope, else None (see tick_family)."""
    if rule not in _FAMILY_RULES:
        return None
    fam = lookup_scope(rule, scope, market)
    return fam if fam != scope else None


def similar_names(name: str, candidates: Iterable[str], n: int = 3) -> list:
    """Candidates that contain ``name`` or are contained in it, then close spellings; at most ``n``."""
    import difflib
    cands = sorted(set(candidates) - {name})
    hits = [c for c in cands if name in c or c in name]
    hits += [c for c in difflib.get_close_matches(name, cands, n=n, cutoff=0.6) if c not in hits]
    return hits[:n]


def _miss_hint(rule: str, scope: str, market: str | None, date: str) -> str:
    """Why a lookup found nothing, as a clause appended to the KeyError message ('' when there is nothing to add)."""
    have = _rules_recorded(scope, market)
    where = f"scope {scope!r}" + (f" on market {market}" if market else "")
    if rule in have:
        ivs = have[rule]
        if any(a <= date and (b is None or date < b) for a, b in ivs):
            return ""   # an interval covers the date: the miss is about strict / contract, already said
        if len(ivs) <= 4:
            return "; records of this rule exist for " + ", ".join(f"[{a}, {b or '∞'})" for a, b in ivs)
        last = ivs[-1][1]
        return f"; {len(ivs)} intervals of this rule exist between {ivs[0][0]} and {last or '∞'}, none covers {date}"
    fam = _family_scope(rule, scope, market)
    if fam:
        return f"; {rule} is recorded per instrument family — ask under scope {fam!r} (tick_size() and resolve() do this)"
    if not have:
        on = markets_recorded(scope) if market else []
        if on:   # the scope is recorded, only not on this market: say where, and whether the code is one we use at all
            known = market in _market_codes()
            return (f"; scope {scope!r} is recorded on market(s) {', '.join(on)}, not on {market!r}"
                    + ("" if known else f" — {market!r} is not a market code used in the dataset (codes are ISO 10383 "
                                        f"MICs: {', '.join(_market_codes())})"))
        return f"; the dataset holds no rule at all for {where}"
    close = similar_names(rule, have)
    others = _scopes_recording(rule)
    return (f"; {where} has no rule named {rule!r}" + (f" — closest name(s): {', '.join(close)}" if close else "")
            + f"; rules recorded for it: {', '.join(have)}"
            + (f"; {rule} is recorded under scope(s): {', '.join(others[:5])}"
               + (f" and {len(others) - 5} more" if len(others) > 5 else "") if others else ""))


def _par_value_fee_record(date: str, market: str | None, strict: bool):
    """The par-value transfer-fee record in force on ``date`` for ``market`` (any market when None), or None."""
    try:
        return record_at("transfer_fee_par_value", date, "stock", market, strict)
    except KeyError:
        return None


def _par_value_fee_in_force(date: str, market: str | None, strict: bool) -> bool:
    return _par_value_fee_record(date, market, strict) is not None


def _transfer_fee_record(date: str, market: str, strict: bool):
    """The turnover transfer-fee record for one fill: ``bse_stock`` then ``stock`` for BJSE, ``stock`` otherwise."""
    if market == "BJSE":
        try:
            return record_at("transfer_fee_each_side", date, "bse_stock", market, strict)
        except KeyError:
            pass
    return record_at("transfer_fee_each_side", date, "stock", market, strict)


def statutory_fee_components(turnover: float, side: str, date: str, market: str | None = None,
                             strict: bool = False) -> list:
    """The statutory fees of one A-share stock fill, one dict per component, in CNY:
    ``{"rule", "record_id", "rate", "amount", "basis"}``.

    Components: stamp duty of the fill's side (``stamp_duty_sell`` for ``side == "sell"``, ``stamp_duty_buy``
    otherwise) and the transfer fee (``transfer_fee_each_side``), both fractions of ``turnover``;
    ``amount = turnover * rate``, unrounded. Where the transfer fee was charged on traded PAR VALUE
    (``transfer_fee_par_value``, SSE A shares before 2015-08-01) a fill's turnover cannot give the amount: that
    component is returned with ``amount`` None and ``basis`` "par_value", and is left out of the floor.
    Without ``market`` the lookup asks for a rule covering both XSHG and XSHE (an exchange-specific rate never
    answers for a fill whose exchange is unknown). For market BJSE the transfer fee is looked up under the BSE
    family scope ``bse_stock`` first (BSE-only rate, 2021-11-15..2022-04-29), then under ``stock``.

    Not included: broker commission and anything else that is contractual rather than statutory.
    Raises KeyError when a turnover-based rule is missing and no par-value rule explains the gap."""
    mkt = market or "XSHG+XSHE"
    recs = [record_at("stamp_duty_sell" if side == "sell" else "stamp_duty_buy", date, "stock", mkt, strict)]
    par = None
    try:
        recs.append(_transfer_fee_record(date, mkt, strict))
    except KeyError:
        par = _par_value_fee_record(date, market, strict)
        if par is None:
            raise
    out = [{"rule": r.rule, "record_id": r.id, "rate": r.value, "amount": turnover * r.value, "basis": "turnover"}
           for r in recs]
    if par is not None:
        out.append({"rule": par.rule, "record_id": par.id, "rate": par.value, "amount": None, "basis": "par_value"})
    return out


def statutory_fee_floor(turnover: float, side: str, date: str, market: str | None = None, strict: bool = False) -> float:
    """Lower bound on the statutory fees of one fill, in CNY: stamp duty of the fill's side + transfer fee on turnover
    — the sum of the turnover-based amounts of ``statutory_fee_components()`` (same arguments, same errors).

    A fee below this is impossible; a fee above it is normal (commission is not included). On days when the transfer
    fee was a fraction of traded par value the transfer component is omitted, so the result stays a valid lower bound."""
    stat = None
    for c in statutory_fee_components(turnover, side, date, market, strict):
        if c["amount"] is not None:
            stat = c["amount"] if stat is None else stat + c["amount"]
    return stat


def skill_text() -> str:
    """The usage notes for assistants and backtest authors (SKILL.md), as shipped with this package."""
    here = os.path.dirname(__file__)
    # a source checkout reads the repository file; an installed package reads its vendored copy
    for p in (os.path.join(here, "..", "..", "SKILL.md"), os.path.join(here, "SKILL.md")):
        if os.path.isfile(p):
            with open(p, encoding="utf-8") as fh:
                return fh.read()
    raise FileNotFoundError("SKILL.md is not part of this installation")


def round_half_up(x: float, decimals: int = 2) -> float:
    """Exchange rounding for limit prices (half away from zero), not banker's rounding."""
    f = 10.0 ** decimals
    return math.floor(float(x) * f + 0.5 + 1e-9) / f


_TICK_SCOPE = {"etf": "etf", "etf_20pct": "etf", "etf_bond": "etf", "etf_money": "etf", "etf_gold": "etf", "etf_commodity": "etf",
               "etf_crossborder": "etf", "reits": "etf", "reits_day1": "etf", "b_share": "b_share", "st_b_share": "b_share",
               "convertible": "convertible", "convertible_day1": "convertible",
               "bse": "bse_stock", "st_bse": "bse_stock", "ipo_day1_bse": "bse_stock", "delisting_bse": "bse_stock",
               "delisting_day1_bse": "bse_stock", "bse_stock": "bse_stock"}
# Rules recorded per instrument family rather than per scope. A scope not in _TICK_SCOPE belongs to family "stock".
_FAMILY_RULES = frozenset({"tick_size"})


def _is_bjse(market: str | None) -> bool:
    return market is not None and _market_set(market) == {"BJSE"}


def tick_family(scope: str, market: str | None = None) -> str:
    """Instrument family whose ``tick_size`` records apply to ``scope`` (stock / bse_stock / etf / b_share /
    convertible). BSE board scopes belong to ``bse_stock``; family ``stock`` asked about market BJSE is ``bse_stock``
    too (BSE-only records live there, so a market-less ``stock`` lookup never meets a BJSE record).
    A scope outside the mainland securities scopes (futures, Hong Kong, US, unknown) is its own family."""
    fam = _TICK_SCOPE.get(scope) or ("stock" if _securities_scope(scope) else scope)
    return "bse_stock" if fam == "stock" and _is_bjse(market) else fam


_SECURITIES_EXCHANGES = frozenset({"XSHG", "XSHE", "BJSE"})


@lru_cache(maxsize=None)
def _securities_scope(scope: str) -> bool:
    """True when ``scope`` is in the mainland registry and its own records, if it has any, sit on a securities
    exchange (XSHG / XSHE / BJSE). Only such a scope falls back to the ``stock`` tick family: a futures scope
    (records on a futures exchange), a Hong Kong or US scope and an unknown scope have no family, so asking their
    ``tick_size`` finds nothing instead of the A-share tick."""
    if scope not in scopes("cn"):
        return False
    markets = {m for r in records() if r.scope == scope for m in r.market.split("+")}
    return not markets or bool(markets & _SECURITIES_EXCHANGES)


def lookup_scope(rule: str, scope: str, market: str | None = None) -> str:
    """The scope under which records of ``rule`` for ``scope`` are stored. The single mapping shared by
    tick_size(), contract.resolve() and coverage(): tick_size → instrument family, everything else → itself."""
    return tick_family(scope, market) if rule in _FAMILY_RULES else scope


def tick_size(scope: str, date: str, market: str | None = None, strict: bool = False,
              *, as_of: str | None = None) -> float:
    """Minimum price increment for ``scope`` on ``date`` (CNY for A-shares/funds/convertibles; USD/HKD for B shares).

    Looks up rule ``tick_size`` under the instrument family of ``scope`` (stock / bse_stock / etf / b_share /
    convertible; BSE board scopes, and family stock with market BJSE, map to ``bse_stock``).
    Raises ``KeyError`` when no tick is recorded for that date — callers must not assume 0.01.
    """
    return rule_at("tick_size", _check_date(date), lookup_scope("tick_size", scope, market), market, strict, as_of=as_of)


def _agreed_tick(scope: str, date: str, market: str | None = None, strict: bool = False,
                 as_of: str | None = None) -> float:
    """tick_size(), except that with ``market=None`` several exchanges' records in force that all carry the SAME value
    (e.g. separate SSE and SZSE convertible records, both 0.001) answer with that value — rounding needs the value, not the exchange. Different
    values still raise ``RuleConflict``; nothing in force raises ``KeyError``."""
    try:
        return tick_size(scope, date, market, strict, as_of=as_of)
    except RuleConflict:
        if market is not None:
            raise
        fam = lookup_scope("tick_size", scope, market)
        active = [r for r in records() if r.rule == "tick_size" and r.scope == fam
                  and r.active_on(_check_date(date)) and not (strict and r.verification == "unverified")]
        vals = {(r.value, r.unit) for r in active}
        if len(vals) != 1:
            raise
        for r in active:   # every agreeing record must have been public at as_of
            _require_published(r, as_of)
        return vals.pop()[0]


def _min_tick_value(scope: str, date: str, market: str, as_of: str | None = None):
    """``limit_price_min_tick`` value for ``scope`` on ``date``: the scope's own record first, then (market BJSE)
    the BSE family scope ``bse_stock``, then scope ``stock``.

    A scope-specific record exists where an exchange wrote a board-specific floor (SSE delisting board 2013–2023:
    ¥0.01 band below / at ¥0.05). ``None`` when none is in force.
    """
    order = [scope] + (["bse_stock"] if _is_bjse(market) else []) + ["stock"]
    for sc in dict.fromkeys(order):
        try:
            return rule_at("limit_price_min_tick", date, sc, market, as_of=as_of)
        except (NotYetPublished, PublicationUnknown):
            raise   # the in-force record exists but is not knowable at as_of: never fall back
        except KeyError:
            continue
    return None


def min_tick_band(scope: str, date: str, market: str | None = None, *, as_of: str | None = None) -> bool:
    """Does the exchange floor the band at one tick on ``date``? (SZSE since 2011-02-28, SSE since 2023-04-10;
    SSE delisting board 2013-01-01..2023-04-10 conditionally, see ``limit_price``.)

    Looks up ``limit_price_min_tick`` for ``scope`` first, then ``bse_stock`` (market BJSE), then ``stock``. False when no record
    is in force — i.e. the letter of the rule was rounding only, so a very low-priced security could have
    limit == preclose. A conditional (dict) value counts as True: a floor exists, subject to its price condition.
    """
    if market is None:
        raise ValueError("min_tick_band needs an explicit market: SSE and SZSE adopted the floor 12 years apart")
    return bool(_min_tick_value(scope, _check_date(date), market, _check_as_of(as_of)))


def limit_price(prev_close: float, scope: str, date: str, market: str | None = None,
                decimals: int | None = None, strict: bool = False,
                *, as_of: str | None = None) -> tuple[float, float] | None:
    """(limit_up, limit_down) for ``scope`` on ``date``; ``None`` when the band is unlimited.

    Three separately-sourced rules compose here:
      price_limit_pct        the band
      tick_size              rounding unit (``decimals`` overrides it only if you pass one explicitly)
      limit_price_min_tick   exchange floor: if |limit − prev_close| rounds below one tick, use ± one tick.
                             Looked up for ``scope`` first, then ``bse_stock`` (market BJSE), then ``stock``. A dict value
                             ``{prev_close_lt|prev_close_lte: x, band: b}`` is a board-specific absolute band
                             (SSE delisting board 2013-01-01..2023-04-10: ±¥0.01 when preclose < / ≤ ¥0.05).
    Pass ``market`` for any date-sensitive case: the one-tick floor is SZSE-only before 2023-04-10.
    ``as_of``: every composed record must have been published by then (see ``record_at``); otherwise
    ``NotYetPublished`` / ``PublicationUnknown`` propagate — the 0.01 pre-2006 tick fallback never masks them.
    """
    as_of = _check_as_of(as_of)
    date = _check_date(date)
    v = rule_at("price_limit_pct", date, scope, market, strict, as_of=as_of)
    if v == "unlimited":
        return None
    up = v["up"] if isinstance(v, dict) else v
    dn = v["down"] if isinstance(v, dict) else v
    if decimals is None:
        try:
            tick = _agreed_tick(scope, date, market, strict, as_of)
        except (NotYetPublished, PublicationUnknown):
            raise
        except KeyError:
            tick = 0.01  # pre-2006 A-share dates: tick not sourced, 0.01 is the only value ever used (G-0005)
        decimals = max(0, -int(round(math.log10(tick))))
    else:
        tick = 10.0 ** -decimals
    hi = round_half_up(prev_close * (1 + up), decimals)
    lo = round_half_up(prev_close * (1 - dn), decimals)
    floor_hit = (hi - prev_close < tick - 1e-12) or (prev_close - lo < tick - 1e-12)
    if floor_hit:
        # Only here does the one-tick floor matter, and only here is the exchange identity decisive.
        if market is None:
            raise ValueError(f"limit_price({prev_close}, {scope!r}, {date}): the band rounds below one tick; "
                             "whether the exchange floors it at ±1 tick depends on the market (SZSE since 2011-02-28, "
                             "SSE since 2023-04-10). Pass market='XSHG' or 'XSHE'.")
    if market is not None:
        mt = _min_tick_value(scope, date, market, as_of)
        if isinstance(mt, dict):
            # Board-specific absolute band (SSE risk-warning-board measures art. 7): applies when the previous
            # close is below (2013 text) / at or below (2020 text) the threshold, regardless of rounding.
            if "prev_close_lt" in mt:
                applies = prev_close < float(mt["prev_close_lt"]) - 1e-12
            else:
                applies = prev_close <= float(mt["prev_close_lte"]) + 1e-12
            if applies:
                band = float(mt["band"])
                hi = round_half_up(prev_close + band, decimals)
                lo = round_half_up(prev_close - band, decimals)
        elif mt and floor_hit:
            if hi - prev_close < tick - 1e-12:
                hi = round_half_up(prev_close + tick, decimals)
            if prev_close - lo < tick - 1e-12:
                lo = round_half_up(prev_close - tick, decimals)
    return hi, lo


# ------------------------------------------------------------------------------------------ precompiled dataset
# The marina-rules-data wheel ships data/compiled.json (written by scripts/vendor_data.py through
# marina_rules._precompiled.build): the output of the YAML loaders above, so that the first records() call does not
# parse YAML. It is used only when it matches the YAML beside it byte for byte and was written by loader code of the
# same revision as this one (_precompiled.LOADER_REVISION); otherwise the YAML is loaded (and validated) as usual,
# with a warning. A source checkout has no such file and always reads the YAML.
def _compiled():
    return _compiled_for(DATA_DIR)


@lru_cache(maxsize=None)
def _compiled_for(data_dir: str):
    from . import _precompiled as pc
    path = os.path.join(data_dir, pc.FILE)
    if not os.path.isfile(path):
        return None
    try:
        return pc.load(path, data_dir)
    except pc.Rejected as e:
        import warnings
        warnings.warn(f"marina_rules: ignoring the precompiled dataset {path} ({e}); loading the YAML instead",
                      RuntimeWarning, stacklevel=4)
        return None


def _digest_dir(data_dir: str) -> str:
    h = hashlib.sha256()
    for path in _iter_files(data_dir):
        h.update(os.path.relpath(path, data_dir).encode())
        with open(path, "rb") as fh:
            h.update(fh.read())
    return h.hexdigest()


@lru_cache(maxsize=None)
def dataset_digest() -> str:
    """SHA-256 over all data files (sorted by relative path). This is what a citation pins. The tracking registries
    (``data/<prefix>/tracking.yaml``) are excluded: they record how far the sources were checked, not a rule."""
    return _digest_dir(DATA_DIR)


def citation(short: bool = True) -> str:
    """One line to put in any backtest result: which rules, byte-exactly, and which code read them.

    ``rules: marina-rules-data@<data version> sha256:<digest> code: marina-rules@<code version>`` — the digest is the
    first 16 hex of ``dataset_digest()`` (all 64 with ``short=False``)."""
    dg = dataset_digest()
    return f"rules: marina-rules-data@{DATA_VERSION} sha256:{dg[:16] if short else dg} code: marina-rules@{__version__}"
