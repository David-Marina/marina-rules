"""MCP server: the rules, asked from an AI assistant over the Model Context Protocol (stdio).

    pip install "marina-rules[mcp]"      # the MCP Python SDK is an optional dependency (it needs Python 3.10+)
    marina-rules-mcp                     # or: marina-rules mcp | python -m marina_rules.mcp_server

Tools (all read-only and deterministic; no network, no files read or written beyond the packaged dataset):

  resolve          one rule on one trading day for one scope: the decision of ``marina_rules.contract.resolve``
  limit_price      limit-up / limit-down price from the previous close (``unlimited`` when no band applies)
  statutory_fees   stamp duty + transfer fee of one A-share stock fill, per component and summed
  coverage         can every (rule, day) of a window be answered for a scope?
  list_scopes      scopes of a market family (cn / hk / us) and the context each requires
  list_rules       rule names a scope holds, with their date ranges
  check_fills      check a small fill log (rows inline as JSON) against the rules of each day
  citation         the citation line and version of the dataset

Every answer carries ``citation``. Arguments the library refuses (a date not written ``YYYY-MM-DD``, an unknown side, a
rule with no record in force) come back as a tool error whose text says what to change; nothing is filled in.

The functions in this module up to ``build_server`` need no SDK and run on any supported Python: ``run_tool(name,
arguments)`` is the whole server minus the protocol, and is what the tests exercise on Python 3.9. ``build_server``
imports the SDK; ``main`` prints what to install (exit code 2) when it is missing.
"""
import math
import sys
from typing import Any, Callable, Dict, List, Optional, Union

SERVER_NAME = "marina-rules"
REGISTRY_NAME = "io.github.David-Marina/marina-rules"   # the MCP Registry name (server.json; README mcp-name line)
SDK_REQUIREMENT = "mcp>=2.3,<3"
INSTALL_HINT = 'pip install "marina-rules[mcp]"'
SKILL_URI = "marina-rules://skill"
MAX_ROWS = 500            # check_fills: rows per call
MAX_RULES = 50            # coverage: rule names per call
MAX_CONTEXT_KEYS = 32
MAX_ROW_KEYS = 40
MAX_NAME_LEN = 64         # rule / scope / market / context key / cell text
MAX_DATE_LEN = 32
MARKET_PREFIXES = ("cn", "hk", "us")

Scalar = Union[str, int, float, bool, None]

SERVER_DESCRIPTION = (
    "Point-in-time exchange trading rules with official citations: China A-share price limits (涨跌停), stamp duty "
    "(印花税), transfer fees, tick size, trading sessions; China futures margin and limits; Hong Kong and US equities.")

INSTRUCTIONS = """\
Marina rules answers which exchange trading rule was in force on a given day, with the official source behind it:
China A-share price limits (涨跌停 / 涨跌幅限制, limit-up / limit-down), stamp duty (印花税), transfer fees, tick size,
trading sessions and T+N; CFFEX / SHFE / INE / CZCE / GFEX futures margin, price limits and fees; Hong Kong and US
equity rules. Use it for backtest validation and point-in-time questions ("what was the ChiNext limit on 2020-08-21?").

It holds rules only: no prices, no ST or suspension lists, no index constituents, no trading calendar. Facts about a
security (board, ST status, listing day) come from the caller and are never guessed.

How to ask:
1. Names first: list_scopes, then list_rules for the scope. Ask only for rule names listed there.
2. For a whole backtest window, coverage first.
3. resolve for one rule on one day: act on status DETERMINED only. MISSING_CONTEXT, OUT_OF_COVERAGE, CONFLICT,
   UNVERIFIED, NOT_YET_PUBLISHED, UNKNOWN_PUBLICATION and BEYOND_TRACKING mean stop and report; never substitute a
   value of your own. limit_price and statutory_fees compute prices and fees; check_fills checks a small fill log.
4. Dates are YYYY-MM-DD. Markets are ISO 10383 codes: XSHG (Shanghai), XSHE (Shenzhen), BJSE, XHKG, XNYS, XNAS,
   CCFX, XSGE, XINE, XZCE, GFEX.
5. Quote the citation line with every answer. Treat the exchange's own notice as authoritative.
The usage notes are the resource marina-rules://skill."""


class ToolFailure(Exception):
    """A tool call that cannot be answered as asked. The message is what the assistant reads; it says what to change
    or why there is no answer, and ends with the citation line of the dataset that was asked."""


# --------------------------------------------------------------------------------------------------- argument checks
def _text(name: str, v, *, max_len: int = MAX_NAME_LEN, optional: bool = False) -> Optional[str]:
    if v is None and optional:
        return None
    if not isinstance(v, str) or not v.strip():
        raise ValueError(f"{name} must be a non-empty string" + (" or null" if optional else ""))
    if len(v) > max_len:
        raise ValueError(f"{name} is longer than {max_len} characters")
    return v.strip()


def _date(name: str, v, *, optional: bool = False) -> Optional[str]:
    # The spelling itself (YYYY-MM-DD, nothing else) is checked by the library, whose message names the ISO form.
    return _text(name, v, max_len=MAX_DATE_LEN, optional=optional)


def _number(name: str, v, *, positive: bool = True) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise ValueError(f"{name} must be a number, got {type(v).__name__}")
    x = float(v)
    if not math.isfinite(x) or (positive and x <= 0) or abs(x) > 1e15:
        raise ValueError(f"{name} must be a finite number greater than 0, got {v!r}")
    return x


def _flag(name: str, v) -> bool:
    if not isinstance(v, bool):
        raise ValueError(f"{name} must be true or false")
    return v


def _scalar(name: str, v) -> Scalar:
    if v is None or isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        if isinstance(v, float) and not math.isfinite(v):
            raise ValueError(f"{name} must be a finite number")
        return v
    if isinstance(v, str):
        if len(v) > MAX_NAME_LEN:
            raise ValueError(f"{name} is longer than {MAX_NAME_LEN} characters")
        return v
    raise ValueError(f"{name} must be a string, number, true/false or null, got {type(v).__name__}")


def _context(v) -> Optional[Dict[str, Scalar]]:
    if v is None:
        return None
    if not isinstance(v, dict):
        raise ValueError("context must be an object of {key: value}, e.g. {\"board\": \"main_board\", \"st_status\": true}")
    if len(v) > MAX_CONTEXT_KEYS:
        raise ValueError(f"context has more than {MAX_CONTEXT_KEYS} keys")
    return {_text("context key", k): _scalar(f"context[{k!r}]", x) for k, x in v.items()}


def _cell(v) -> str:
    """A fill-log cell as the CSV reader would have given it (check_rows reads text): true/false for booleans."""
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v)


def _rows(v) -> List[Dict[str, str]]:
    if not isinstance(v, list):
        raise ValueError("rows must be a JSON array of objects, one per fill")
    if not v:
        raise ValueError("rows is empty: pass at least one fill")
    if len(v) > MAX_ROWS:
        raise ValueError(f"rows has {len(v)} fills; at most {MAX_ROWS} are checked per call. Split the log into "
                         f"batches of {MAX_ROWS} (each batch gets its own result), or run marina-check on the CSV file")
    out = []
    for i, r in enumerate(v, start=1):
        if not isinstance(r, dict):
            raise ValueError(f"row {i} is not an object")
        if len(r) > MAX_ROW_KEYS:
            raise ValueError(f"row {i} has more than {MAX_ROW_KEYS} columns")
        for k in r:
            _text(f"row {i} column name", k)          # a non-empty string of reasonable length; kept as written
        out.append({k: _cell(_scalar(f"row {i} {k}", x)) for k, x in r.items()})
    return out


# ------------------------------------------------------------------------------------------------------------- tools
def resolve(rule: str, trade_date: str, scope: str = "stock", market: Optional[str] = None,
            context: Optional[dict] = None, min_verification: str = "single-source", as_of: Optional[str] = None,
            require_tracked: bool = False) -> dict:
    from .contract import resolve as _resolve
    import marina_rules_core as mr
    d = _resolve(_text("rule", rule), _date("trade_date", trade_date), _text("scope", scope),
                 _text("market", market, optional=True), _context(context),
                 _text("min_verification", min_verification), as_of=_date("as_of", as_of, optional=True),
                 require_tracked=_flag("require_tracked", require_tracked))
    d["citation"] = mr.citation()
    return d


def limit_price(prev_close: float, scope: str, date: str, market: Optional[str] = None, as_of: Optional[str] = None,
                strict: bool = False) -> dict:
    import marina_rules_core as mr
    prev_close = _number("prev_close", prev_close)
    scope, date = _text("scope", scope), _date("date", date)
    market, as_of = _text("market", market, optional=True), _date("as_of", as_of, optional=True)
    strict = _flag("strict", strict)
    band = mr.limit_price(prev_close, scope, date, market, strict=strict, as_of=as_of)
    rec = mr.record_at("price_limit_pct", date, scope, market, strict, as_of=as_of)
    out = {"prev_close": prev_close, "scope": scope, "date": date, "market": market}
    if as_of is not None:
        out["as_of"] = as_of
    if band is None:
        out.update({"unlimited": True, "limit_up": None, "limit_down": None,
                    "note": "unlimited: no daily price limit applied to this scope on this date (record "
                            f"{rec.id}); this is a finding, not a missing value"})
    else:
        rnd = mr._rounding_record(scope, date, market, strict, None)   # the record limit_price rounded with
        how = {"half_up_2dp": "half away from zero",
               "toward_prev_close": "toward the previous close (limit-up down, limit-down up)"}[rnd.value]
        out.update({"unlimited": False, "limit_up": band[0], "limit_down": band[1],
                    "rounding": rnd.value, "rounding_record_id": rnd.id, "rounding_verification": rnd.verification,
                    "note": f"rounded {how} on the tick in force (record {rnd.id}); the scope must match the "
                            "security on that day (board, ST status, listing day), which this tool does not check: "
                            "use resolve with context for that"})
    out.update({"price_limit_pct": rec.value, "record_id": rec.id, "verification": rec.verification,
                "tracking": mr.tracking_state(market or rec.market, scope, date), "citation": mr.citation()})
    return out


def statutory_fees(turnover: float, side: str, date: str, market: Optional[str] = None) -> dict:
    from .cli import fees_payload
    turnover = _number("turnover", turnover)
    if side not in ("buy", "sell"):
        raise ValueError(f"side must be 'buy' or 'sell', got {side!r}")
    return fees_payload(turnover, side, _date("date", date), _text("market", market, optional=True))


def coverage(market: str, scope: str, rules: List[str], start: str, end: str, as_of: Optional[str] = None,
             contract: Optional[str] = None, require_tracked: bool = False) -> dict:
    import marina_rules_core as mr
    if not isinstance(rules, list) or not rules:
        raise ValueError("rules must be a non-empty array of rule names (list_rules gives them)")
    if len(rules) > MAX_RULES:
        raise ValueError(f"rules has {len(rules)} names; at most {MAX_RULES} per call")
    names = [_text("rule", r) for r in rules]
    return mr.coverage(_text("market", market), _text("scope", scope), names, _date("start", start),
                       _date("end", end), as_of=_date("as_of", as_of, optional=True),
                       contract=_text("contract", contract, optional=True),
                       require_tracked=_flag("require_tracked", require_tracked))


def list_scopes(market_prefix: str = "cn") -> dict:
    import marina_rules_core as mr
    from .cli import scopes_payload
    if market_prefix not in MARKET_PREFIXES:
        raise ValueError(f"market_prefix must be one of {', '.join(MARKET_PREFIXES)} (cn = mainland China: A-shares "
                         f"and futures; hk = Hong Kong; us = United States), got {market_prefix!r}")
    return {"market_prefix": market_prefix, "scopes": scopes_payload(market_prefix), "citation": mr.citation()}


def list_rules(scope: str, market: Optional[str] = None, intervals: bool = False) -> dict:
    from .cli import rules_payload
    return rules_payload(_text("scope", scope), _text("market", market, optional=True), _flag("intervals", intervals))


def check_fills(rows: List[dict], strict: bool = False, tick: bool = True, band_tolerance_pct: float = 0.0,
                per_row: bool = False, assume_seasoned: bool = False, assume_not_st: bool = False) -> dict:
    from .check import check_rows
    if isinstance(band_tolerance_pct, bool) or not isinstance(band_tolerance_pct, (int, float)):
        raise ValueError("band_tolerance_pct must be a number")
    return check_rows(_rows(rows), _flag("strict", strict), tick=_flag("tick", tick),
                      band_tolerance_pct=float(band_tolerance_pct), per_row=_flag("per_row", per_row),
                      assume_seasoned=_flag("assume_seasoned", assume_seasoned),
                      assume_not_st=_flag("assume_not_st", assume_not_st))


def citation() -> dict:
    import marina_rules_core as mr
    from .contract import CONTRACT_VERSION
    return {"citation": mr.citation(), "version": mr.VERSION, "code_version": mr.__version__,
            "dataset_sha256": mr.dataset_digest(), "contract_version": CONTRACT_VERSION,
            "note": "put the citation line in every result: it names the marina-rules version (the dataset), the "
                    "first 16 hex of the dataset digest and the marina-rules-core version (the code), so the answer "
                    "can be re-run against byte-identical rules"}


TOOLS: Dict[str, Callable[..., dict]] = {
    "resolve": resolve, "limit_price": limit_price, "statutory_fees": statutory_fees, "coverage": coverage,
    "list_scopes": list_scopes, "list_rules": list_rules, "check_fills": check_fills, "citation": citation,
}

DESCRIPTIONS = {
    "resolve": (
        "Which trading rule was in force on one trading day for one scope (point-in-time), as one decision with its "
        "official source: China A-share price limit 涨跌停 (price_limit_pct), stamp duty 印花税, transfer fee, tick "
        "size, trading sessions, T+N; futures margin and limits; Hong Kong and US rules. Only status DETERMINED carries "
        "a value (result). Any other status — MISSING_CONTEXT (supply the keys in missing_context via context), "
        "OUT_OF_COVERAGE, CONFLICT, UNVERIFIED, NOT_YET_PUBLISHED, UNKNOWN_PUBLICATION, BEYOND_TRACKING — means stop "
        "and report it: do not fill in a value yourself. alternatives lists rule or scope names that do exist. "
        "trade_date must be YYYY-MM-DD; market is an ISO 10383 code (XSHG, XSHE, BJSE, XHKG, XNYS, XNAS, CCFX, XSGE, "
        "XINE, XZCE, GFEX). Facts about the security (board, st_status, listing_day_index …) are the caller's: the "
        "dataset holds no ST list, prices or trading calendar."),
    "limit_price": (
        "Limit-up / limit-down price (涨停价 / 跌停价) of a China A-share or other price-limited scope on a date, from "
        "the previous close (or the exchange's ex-rights reference price), with exchange rounding and the one-tick "
        "floor. When no daily limit applied (e.g. the first five trading days of a main-board IPO since 2023-04-10), "
        "returns unlimited: true with null prices — a finding, not a gap. date must be YYYY-MM-DD; pass market (XSHG / XSHE / "
        "BJSE) for exact rounding rules. The scope must be the security's scope on that day (list_scopes; ST and "
        "IPO scopes differ); this tool does not check context, resolve does."),
    "statutory_fees": (
        "Statutory fees of one China A-share stock fill (成交): stamp duty 印花税 of the side and transfer fee 过户费, "
        "per component with rate, record id and amount, and their sum (statutory_fee_floor). Broker commission is not "
        "included, so a real fee is at least this. turnover is the fill's value in CNY; side is buy or sell; date "
        "YYYY-MM-DD; market XSHG / XSHE / BJSE (omit only when the rate is the same on both exchanges). A day with no "
        "rule in force is an error, never a guessed rate."),
    "coverage": (
        "Pre-flight for a backtest window (backtest validation): can every (rule, day) in [start, end) be answered "
        "for this market and scope? status complete / partial / unsupported, with the exact gaps, known_gap_ids, "
        "conflicts, the lowest verification level and the context the scope requires per security (required_context). "
        "Run it before simulating; do not discover gaps mid-run. Dates YYYY-MM-DD; end is exclusive; rules are names "
        "from list_rules."),
    "list_scopes": (
        "Scopes of one market family and the context each requires: cn = mainland China (A-share boards such as "
        "main_board, chinext, star, bse, st_main, IPO windows; ETFs, REITs, convertibles; CFFEX / SHFE / INE / CZCE / GFEX "
        "futures products), hk = Hong Kong, us = United States. Start here: a rule is answered only for a scope "
        "that exists."),
    "list_rules": (
        "Rule names the dataset holds for a scope (optionally on one market, ISO 10383 code), each with its first and "
        "last effective date — e.g. price_limit_pct, stamp_duty_sell, tick_size, session_schedule, margin_ratio. Ask "
        "for a rule only by a name listed here; a similar name is a different rule. intervals=true lists every "
        "interval. An empty result means the dataset holds nothing there, not that no rule exists."),
    "check_fills": (
        f"Check a small fill log from a backtest or broker (backtest validation) against the rules of each day: "
        f"price inside the A-share daily price limit 涨跌停 band, on the tick, fee not below stamp duty 印花税 + "
        f"transfer fee. rows is a JSON array of at most {MAX_ROWS} objects with the columns of marina-check: date "
        f"(YYYY-MM-DD), code, side (buy/sell), price, prev_close (same price basis, unadjusted), scope or its context "
        f"(board, st_status, listing_day_index …), market, and optional fee, turnover, day_high, day_low. Values as "
        f"strings are checked exactly as written (the tick check compares the written price). A file path is not "
        f"accepted. Returns findings per row, counts, hints and, for a strict clean run, a rules-verified stamp. "
        f"China A-shares only."),
    "citation": (
        "The citation line and version of the rule dataset this server answers from (marina-rules version, dataset "
        "sha256, and the marina-rules-core version that reads it). Put it in any result built on these answers so it "
        "can be re-run against the same rules."),
}

TITLES = {
    "resolve": "Rule in force on a date", "limit_price": "Limit-up / limit-down price",
    "statutory_fees": "A-share statutory fees (stamp duty, transfer fee)", "coverage": "Coverage of a backtest window",
    "list_scopes": "Scopes and required context", "list_rules": "Rules of a scope",
    "check_fills": "Check a fill log", "citation": "Dataset citation",
}


def _citation_line() -> str:
    try:
        import marina_rules_core as mr
        return mr.citation()
    except Exception:   # the dataset itself failed to load: report the original error, not this one
        return "rules: marina-rules (dataset not loaded)"


def run_tool(name: str, arguments: Optional[dict] = None) -> dict:
    """Call one tool as the server does, without the protocol: the JSON result, or ``ToolFailure`` with the text the
    assistant reads. ``ValueError`` / ``TypeError`` (an argument to change) and ``KeyError`` / ``LookupError`` (no
    answer in the dataset) become ``ToolFailure``; nothing becomes a successful result it is not."""
    from . import RuleConflict
    if name not in TOOLS:
        raise ToolFailure(f"unknown tool {name!r}; tools: {', '.join(TOOLS)}. {_citation_line()}")
    try:
        return TOOLS[name](**(arguments or {}))
    except RuleConflict as e:
        raise ToolFailure(f"conflict: {e} — a dataset error; do not pick one of the values. {_citation_line()}") from e
    except KeyError as e:   # includes NotYetPublished, PublicationUnknown, BeyondTracking, ContractRequired
        msg = e.args[0] if e.args else str(e)
        raise ToolFailure(f"not answered: {msg} — there is no value to use here; do not substitute one. "
                          f"{_citation_line()}") from e
    except (ValueError, TypeError) as e:
        msg = str(e)
        raise ToolFailure(f"invalid argument: {msg}{'' if msg.endswith(('.', '?', '!')) else '.'} "
                          f"{_citation_line()}") from e


# ------------------------------------------------------------------------------------------------------- the server
class SDKMissing(ImportError):
    pass


def sdk_problem() -> Optional[str]:
    """None when a usable MCP SDK is importable; otherwise one line saying what to install."""
    py = "%d.%d" % sys.version_info[:2]
    if sys.version_info < (3, 10):
        return (f"marina-rules-mcp: the MCP server needs Python 3.10 or newer (the MCP Python SDK does not support "
                f"Python {py}); everything else in marina-rules works on this Python. With Python 3.10+: "
                f"{INSTALL_HINT}")
    try:
        from mcp.server import MCPServer  # noqa: F401
        from mcp.server.mcpserver.exceptions import ToolError  # noqa: F401
        from mcp.types import ToolAnnotations  # noqa: F401
    except ImportError as e:
        return (f"marina-rules-mcp: the MCP server needs the MCP Python SDK ({SDK_REQUIREMENT}), which is not "
                f"installed or too old ({e}). Install it with: {INSTALL_HINT} — everything else in marina-rules works "
                f"without it.")
    return None


def build_server():
    """The MCP server object (``mcp.server.MCPServer``). Raises ``SDKMissing`` when the SDK is not usable."""
    problem = sdk_problem()
    if problem:
        raise SDKMissing(problem)
    from mcp.server import MCPServer
    from mcp.server.mcpserver.exceptions import ToolError
    from mcp.types import ToolAnnotations
    from pydantic import Field
    from typing import Annotated
    import marina_rules_core as mr

    server = MCPServer(SERVER_NAME, title="Marina rules", description=SERVER_DESCRIPTION, instructions=INSTRUCTIONS,
                       website_url="https://github.com/David-Marina/marina-rules", version=mr.VERSION,
                       log_level="WARNING")
    hints = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False)

    def register(fn):
        name = fn.__name__

        def call(**kwargs):
            try:
                return run_tool(name, kwargs)
            except ToolFailure as e:
                raise ToolError(str(e)) from None
        server.add_tool(_with_signature(fn, call), name=name, title=TITLES[name], description=DESCRIPTIONS[name],
                        annotations=hints, structured_output=True)

    D = lambda text: Field(description=text)  # noqa: E731
    Date = Annotated[str, D("YYYY-MM-DD")]
    Market = Annotated[Optional[str], D("ISO 10383 market code: XSHG, XSHE, BJSE, XHKG, XNYS, XNAS, CCFX, XSGE, XINE, "
                                        "XZCE, GFEX; '+'-joined for a rule shared by two exchanges (XSHG+XSHE)")]
    AsOf = Annotated[Optional[str], D("YYYY-MM-DD: answer only from rules officially published by this date "
                                      "(no look-ahead on rule changes)")]
    Scope = Annotated[str, D("scope name from list_scopes, e.g. stock, main_board, chinext, star, st_main, cffex_if")]

    def resolve(rule: Annotated[str, D("rule name from list_rules, e.g. price_limit_pct, stamp_duty_sell, tick_size")],
                trade_date: Date, scope: Scope = "stock", market: Market = None,
                context: Annotated[Optional[dict[str, Scalar]], D(
                    "facts about the security that day, keyed by the scope's requires (board, st_status, "
                    "listing_day_index, issue_regime, contract …); never inferred")] = None,
                min_verification: Annotated[str, D("verified | single-source | unverified")] = "single-source",
                as_of: AsOf = None,
                require_tracked: Annotated[bool, D("refuse a value carried forward past the date the sources were "
                                                   "last checked (status BEYOND_TRACKING)")] = False) -> dict[str, Any]:
        ...

    def limit_price(prev_close: Annotated[float, D("previous close (or the exchange's ex-rights reference price), "
                                                   "unadjusted")],
                    scope: Scope, date: Date, market: Market = None, as_of: AsOf = None,
                    strict: Annotated[bool, D("refuse records whose verification is unverified")] = False
                    ) -> dict[str, Any]:
        ...

    def statutory_fees(turnover: Annotated[float, D("value of the fill in CNY (price x quantity)")],
                       side: Annotated[str, D("buy or sell")], date: Date,
                       market: Annotated[Optional[str], D("XSHG, XSHE or BJSE")] = None) -> dict[str, Any]:
        ...

    def coverage(market: Annotated[str, D("ISO 10383 market code, e.g. XSHE, XSHG, CCFX, XHKG, XNYS")],
                 scope: Scope, rules: Annotated[list[str], D(f"rule names from list_rules (at most {MAX_RULES})")],
                 start: Date, end: Annotated[str, D("YYYY-MM-DD, exclusive")], as_of: AsOf = None,
                 contract: Annotated[Optional[str], D("futures contract code, e.g. au2606, where rules differ by "
                                                      "contract")] = None,
                 require_tracked: Annotated[bool, D("count carry-forwards past the tracked date as partial")] = False
                 ) -> dict[str, Any]:
        ...

    def list_scopes(market_prefix: Annotated[str, D("cn (mainland China: A-shares and futures), hk or us")] = "cn"
                    ) -> dict[str, Any]:
        ...

    def list_rules(scope: Scope, market: Market = None,
                   intervals: Annotated[bool, D("list every effective interval instead of first / last date")] = False
                   ) -> dict[str, Any]:
        ...

    def check_fills(rows: Annotated[list[dict[str, Scalar]], D(
                        f"fills, at most {MAX_ROWS}: objects with date, code, side, price, prev_close, scope (or "
                        f"board / st_status / listing_day_index), market, optional fee, turnover, day_high, day_low")],
                    strict: Annotated[bool, D("refuse unverified records")] = False,
                    tick: Annotated[bool, D("check that prices are on the tick (false for model prices)")] = True,
                    band_tolerance_pct: Annotated[float, D("tolerate fills outside the band by at most this percent "
                                                           "(makes the run relaxed: no stamp)")] = 0.0,
                    per_row: Annotated[bool, D("add row_status, one entry per input row")] = False,
                    assume_seasoned: Annotated[bool, D("treat rows without listing information as past the listing "
                                                       "window (relaxed)")] = False,
                    assume_not_st: Annotated[bool, D("treat rows without an ST cell as not ST (relaxed)")] = False
                    ) -> dict[str, Any]:
        ...

    def citation() -> dict[str, Any]:
        ...

    for fn in (resolve, limit_price, statutory_fees, coverage, list_scopes, list_rules, check_fills, citation):
        register(fn)

    @server.resource(SKILL_URI, name="skill", title="Marina rules: usage notes for assistants (SKILL.md)",
                     description="How to ask: names first, pre-flight the window, supply context, stop on anything "
                                 "but DETERMINED, cite the dataset.", mime_type="text/markdown")
    def skill() -> str:
        return mr.skill_text()

    return server


def _with_signature(spec: Callable, impl: Callable) -> Callable:
    """``impl`` (which takes keyword arguments) presented with the name, signature and annotations of ``spec``, so the
    SDK derives the input and output schemas from ``spec``."""
    import functools
    import inspect
    wrapper = functools.wraps(spec)(lambda **kwargs: impl(**kwargs))
    wrapper.__signature__ = inspect.signature(spec)
    return wrapper


USAGE = """usage: marina-rules-mcp            (also: marina-rules mcp, python -m marina_rules.mcp_server)

Runs the Marina rules MCP server on stdio for an AI assistant (Model Context Protocol). It reads and writes nothing
but the protocol on stdin / stdout. Needs the MCP Python SDK: pip install "marina-rules[mcp]" (Python 3.10+).
Client configuration: {"mcpServers": {"marina-rules": {"command": "marina-rules-mcp"}}}"""


def main(argv: Optional[List[str]] = None) -> int:
    a = list(sys.argv[1:] if argv is None else argv)
    if a and a[0] in ("-h", "--help", "help"):
        print(USAGE)
        return 0
    if a:
        print(f"marina-rules-mcp: unexpected arguments {a!r} (the server speaks stdio only)\n\n{USAGE}", file=sys.stderr)
        return 2
    try:
        server = build_server()
    except SDKMissing as e:
        print(str(e), file=sys.stderr)
        return 2
    server.run("stdio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
