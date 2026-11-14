"""One command line for the package: ``marina-rules <command> …`` or ``python -m marina_rules <command> …``.

  query <rule> <date> <scope> [market] [--context k=v,k=v] [--min verified] [--as-of D] [--require-tracked]
                              one decision as JSON (marina_rules.contract.resolve); anything but DETERMINED is a stop
  rules <scope> [market] [--intervals]
                              rule names the dataset holds for a scope: first date, last date, number of intervals
                              (--intervals lists every interval)
  scopes [cn|hk|us]           scope names, what each means and which context it requires
  fees <turnover> <buy|sell> <date> [market]
                              statutory fees of one A-share stock fill: components, records, and their sum
  check <fills.csv> […]       check a fill log against the rules (same as marina-check; --help for its options)
  capabilities [cn|hk|us]     everything that can be asked, as JSON
  schema                      JSON Schema of the decision returned by query
  skill                       the usage notes shipped with the package (SKILL.md)
  version                     the citation line: package version and dataset digest

Exit codes: 0 answered, 1 findings (check only), 2 usage error. Output is JSON except for skill, version and this help.
"""
from __future__ import annotations

import json
import sys


def _dump(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=1))


def main(argv: list[str] | None = None) -> int:
    import marina_rules as mr
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
    if cmd == "scopes":
        pfx = rest[0] if rest else "cn"
        try:
            reg = mr.scopes(pfx)
        except Exception as e:   # unknown market family
            print(f"error: {e}")
            return 2
        _dump({k: {"description": v["description"], "requires": list(v["requires"])} for k, v in sorted(reg.items())})
        return 0
    if cmd == "rules":
        if not rest:
            print("usage: marina-rules rules <scope> [market]")
            return 2
        full = "--intervals" in rest
        rest = [x for x in rest if x != "--intervals"]
        scope, market = rest[0], (rest[1] if len(rest) > 1 else None)
        have = mr.rules_for(scope, market)
        shown = have if full else {k: {"from": v[0][0], "to": v[-1][1], "intervals": len(v)} for k, v in have.items()}
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
        _dump(out)
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
            comps = mr.statutory_fee_components(turnover, rest[1], rest[2], market)
        except KeyError as e:
            _dump({"status": "OUT_OF_COVERAGE", "reason": e.args[0] if e.args else str(e), "citation": mr.citation()})
            return 0
        except ValueError as e:   # a date that is not YYYY-MM-DD, an unknown side
            print(f"error: {e}")
            return 2
        _dump({"status": "DETERMINED", "turnover": turnover, "side": rest[1], "date": rest[2], "market": market,
               "components": comps, "statutory_fee_floor": mr.statutory_fee_floor(turnover, rest[1], rest[2], market),
               "note": "statutory components only (stamp duty, transfer fee); commission is not included; a component "
                       "with amount null is charged on par value and is left out of the sum",
               "citation": mr.citation()})
        return 0
    print(f"unknown command {cmd!r}\n\n{__doc__.strip()}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
