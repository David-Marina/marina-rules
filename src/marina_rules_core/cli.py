"""One command line for the package: ``marina-rules <command> …`` or ``python -m marina_rules <command> …``.

  query <rule> <date> <scope> [market] [--context k=v,k=v] [--min verified] [--as-of D] [--require-tracked]
                              one decision as JSON (marina_rules.contract.resolve); anything but DETERMINED is a stop.
                              The exit code is 0 for every decision: read status, not the exit code
  rules <scope> [market] [--intervals]
                              rule names the dataset holds for a scope: first date, last date, number of intervals
                              (--intervals lists every interval)
  scopes [cn|hk|us]           scope names, what each means and which context it requires
  fees <turnover> <buy|sell> <date> [market]
                              statutory fees of one A-share stock fill: components, records, and their sum
  check <fills.csv> […]       check a fill log against the rules (same as marina-check; --help for its options)
  adapt <trades.csv> […]      rewrite an engine's trade export (RQAlpha, vn.py, backtrader, 掘金, any table) into the
                              rows check reads, joining previous close / ST / listing dates from a data vendor's
                              tables (--help; --list-formats)
  capabilities [cn|hk|us]     everything that can be asked, as JSON
  schema                      JSON Schema of the decision returned by query
  skill                       the usage notes shipped with the package (SKILL.md)
  version                     the citation line: data version, dataset digest, code version
  mcp                         run the MCP server on stdio, for AI assistants (needs: pip install "marina-rules[mcp]";
                              same as marina-rules-mcp)

Exit codes: 0 answered, 1 findings (check only), 2 usage error. Output is JSON except for adapt (CSV rows; its report is
JSON on stderr), skill, version and this help.
"""
from __future__ import annotations

import json
import sys


def _dump(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=1))


# The payloads below are shared with the MCP server (marina_rules.mcp_server): one answer shape for both front ends.
def scopes_payload(market_prefix: str) -> dict:
    """``marina-rules scopes``: scope → description and required context, for one market family (cn / hk / us)."""
    import marina_rules_core as mr
    return {k: {"description": v["description"], "requires": list(v["requires"])}
            for k, v in sorted(mr.scopes(market_prefix).items())}


def rules_payload(scope: str, market: str | None = None, intervals: bool = False) -> dict:
    """``marina-rules rules``: rule names the dataset holds for a scope (compact unless ``intervals``)."""
    import marina_rules_core as mr
    have = mr.rules_for(scope, market)
    shown = have if intervals else {k: {"from": v[0][0], "to": v[-1][1], "intervals": len(v)} for k, v in have.items()}
    out = {"scope": scope, "market": market, "rules": shown, "citation": mr.citation()}
    if not have:
        known = set()
        for pfx in ("cn", "hk", "us"):
            known |= set(mr.scopes(pfx))
        out["note"] = ("the dataset holds no rule for this scope" + (" on this market" if market else "")
                       + ("" if scope in known else "; the scope name is not in any registry"))
        close = mr.similar_names(scope, known)
        if close:
            out["similar_scopes"] = close
    from .equity import equity_scopes
    if have and scope in equity_scopes():
        fam = mr.lookup_scope("tick_size", scope, market)
        out["see_also"] = {"scopes": sorted({"stock", fam}),
                           "note": "an A-share board scope carries the price limit only; stamp duty, transfer fee, "
                                   "commission cap, sessions and holding period of the stock are recorded under these "
                                   "scopes — marina-rules rules stock"}
    return out


def fees_payload(turnover: float, side: str, date: str, market: str | None = None) -> dict:
    """``marina-rules fees``: statutory fees of one A-share stock fill. Raises KeyError (no rule in force) and
    ValueError (a date that is not YYYY-MM-DD) as ``statutory_fee_components`` does."""
    import marina_rules_core as mr
    comps = mr.statutory_fee_components(turnover, side, date, market)
    return {"status": "DETERMINED", "turnover": turnover, "side": side, "date": date, "market": market,
            "components": comps, "statutory_fee_floor": mr.statutory_fee_floor(turnover, side, date, market),
            "note": "statutory components only (stamp duty, transfer fee); commission is not included; a component "
                    "with amount null is charged on par value and is left out of the sum",
            "citation": mr.citation()}


def main(argv: list[str] | None = None) -> int:
    import marina_rules_core as mr
    a = list(sys.argv[1:] if argv is None else argv)
    if not a or a[0] in ("-h", "--help", "help"):
        print(__doc__.strip())
        return 0 if a else 2
    cmd, rest = a[0], a[1:]
    if cmd == "query":
        from .contract import main as contract_main
        if len(rest) < 3:
            print("usage: marina-rules query <rule> <date> <scope> [market] [--context k=v,k=v] [--min verified]"
                  " [--as-of YYYY-MM-DD] [--require-tracked]")
            return 2
        return contract_main(rest)
    if cmd == "check":
        from .check import main as check_main
        return check_main(rest)
    if cmd == "adapt":
        from .adapt import main as adapt_main
        return adapt_main(rest)
    if cmd == "capabilities":
        from .contract import capabilities
        _dump(capabilities(rest[0] if rest else "cn"))
        return 0
    if cmd == "schema":
        from .contract import contract_schema
        _dump(contract_schema())
        return 0
    if cmd == "skill":
        print(mr.skill_text())
        return 0
    if cmd == "version":
        print(mr.citation())
        return 0
    if cmd == "mcp":
        from .mcp_server import main as mcp_main
        return mcp_main(rest)
    if cmd == "scopes":
        pfx = rest[0] if rest else "cn"
        if pfx not in ("cn", "hk", "us"):
            print(f"error: unknown registry {pfx!r}; registries are cn (mainland China), hk, us")
            return 2
        try:
            payload = scopes_payload(pfx)
        except Exception as e:   # unknown market family
            print(f"error: {e}")
            return 2
        _dump(payload)
        return 0
    if cmd == "rules":
        if not rest:
            print("usage: marina-rules rules <scope> [market]")
            return 2
        full = "--intervals" in rest
        rest = [x for x in rest if x != "--intervals"]
        scope, market = rest[0], (rest[1] if len(rest) > 1 else None)
        _dump(rules_payload(scope, market, full))
        return 0
    if cmd == "fees":
        if len(rest) < 3 or rest[1] not in ("buy", "sell"):
            print("usage: marina-rules fees <turnover> <buy|sell> <date> [market]")
            return 2
        try:
            turnover = float(rest[0])
        except ValueError:
            print("error: turnover must be a number")
            return 2
        market = rest[3] if len(rest) > 3 else None
        try:
            payload = fees_payload(turnover, rest[1], rest[2], market)
        except KeyError as e:
            _dump({"status": "OUT_OF_COVERAGE", "reason": e.args[0] if e.args else str(e), "citation": mr.citation()})
            return 0
        except ValueError as e:   # a date that is not YYYY-MM-DD, an unknown side
            print(f"error: {e}")
            return 2
        _dump(payload)
        return 0
    print(f"unknown command {cmd!r}\n\n{__doc__.strip()}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
