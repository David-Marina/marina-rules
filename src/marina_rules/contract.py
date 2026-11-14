"""Rule Decision Contract — one stable, language-neutral answer shape for "what rule applied?".

    resolve(rule, trade_date, scope, market=None, context=None, min_verification="single-source", as_of=None)

Returns a plain dict (JSON-serialisable, schema in ``contract_schema()``) whose ``status`` is one of

  DETERMINED        a single record is in force, required context was supplied, evidence meets the bar
  MISSING_CONTEXT   the scope requires context the caller did not supply (st_status, listing_day_index…)
  OUT_OF_COVERAGE   no record in force for (market, scope, rule, date); known_gap_ids says whether we knew
  CONFLICT          more than one record in force — a dataset error, never resolved by guessing
  UNVERIFIED        a record exists but its verification level is below ``min_verification``
  NOT_YET_PUBLISHED ``as_of`` given: the record in force on trade_date was published after ``as_of``
                    (record_id names it; never answered with the predecessor)
  UNKNOWN_PUBLICATION ``as_of`` given: the record in force has no ``published_at`` — unknown, not absent
  BEYOND_TRACKING   only with ``require_tracked=True``: the answer would come from an open-ended record on a date after
                    the market's ``tracked_through`` (or the market is untracked) — a carry-forward, refused

Only DETERMINED carries a ``result``. Every status carries ``ruleset_version`` / ``ruleset_hash`` and a
``reason`` in plain words.

Every decision also carries ``tracking`` = ``{tracked_through, beyond}`` (docs/SCHEMA.md "Tracking registry"):
the last date up to which the official sources for the market were checked for rule changes, and whether
``trade_date`` lies after it (both null when the market is untracked), and ``warnings``, a list of codes. A DETERMINED
answer from an open-ended record (``effective_to`` null) on a date after ``tracked_through`` carries
``CARRY_FORWARD_BEYOND_TRACKED``; on an untracked market ``CARRY_FORWARD_UNTRACKED``. The value is then the last
checked rule carried forward, not a finding. ``require_tracked=True`` turns both into status BEYOND_TRACKING.

The Python exceptions (KeyError, RuleConflict, ValueError) remain for the in-process API; this module is the boundary
other languages, agents and logs should see.

``context`` is the caller's knowledge about the security on that date, keyed by the names in
``data/<market>/scopes.yaml`` ``requires`` (``board``, ``st_status``, ``listing_day_index``,
``issue_regime``, ``fund_constituents``, ``fund_type``, ``underlying_t0`` …). Marina never infers these; it checks that they were supplied
and that they are consistent with the scope (e.g. ``st_status=True`` with scope ``main_board`` is a
contradiction and is reported as MISSING_CONTEXT with the mismatch named).

Futures: ``context["contract"]`` is the exchange contract code (``'au2606'``). It is needed only where the records in
force differ by contract (a ``contracts`` selector, docs/SCHEMA.md); there, leaving it out is MISSING_CONTEXT with
``missing_context: ["contract"]``. Supplying it for a rule that does not differ by contract is harmless.
"""
from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from . import (VERSION, rules_for, similar_names, markets_recorded, ContractRequired, RuleConflict, Record, NotYetPublished, PublicationUnknown, _check_as_of, _check_date,
               dataset_digest, gaps_for, lookup_scope, market_prefix_for, record_at, records, scopes, tracked_through,
               tracking_registry, tracking_state)

CONTRACT_VERSION = "1"
STATUSES = ["DETERMINED", "MISSING_CONTEXT", "OUT_OF_COVERAGE", "CONFLICT", "UNVERIFIED", "NOT_YET_PUBLISHED",
            "UNKNOWN_PUBLICATION", "BEYOND_TRACKING"]
# Warning codes in ``warnings`` (additive; a DETERMINED answer that is a carry-forward of an open-ended record).
WARNING_BEYOND = "CARRY_FORWARD_BEYOND_TRACKED"
WARNING_UNTRACKED = "CARRY_FORWARD_UNTRACKED"
WARNINGS = [WARNING_BEYOND, WARNING_UNTRACKED]
_LEVEL = {"verified": 0, "single-source": 1, "unverified": 2}

_FAMILY_ONLY_RULES = {"tick_size"}   # depends on instrument family, not on the security's status that day
# Rules that depend on only part of a scope's context. min_holding_days depends on WHAT the security is (A share,
# B share, which fund type), never on its ST status, listing day or band; tick_size and session_schedule depend on
# exchange and instrument family only. Ask only for the keys listed here (intersected with the scope's requires),
# plus the rule's own ``rule_asserts.<rule>.requires`` from the scope registry.
_RULE_CONTEXT = {"tick_size": frozenset(), "session_schedule": frozenset(), "min_holding_days": frozenset({"fund_type", "underlying_t0"})}
# Hong Kong ``tick_size_table`` is deliberately absent: it has no tick family (lookup_scope leaves it under its own
# scope) and it does depend on per-security context. Under ``hk_etf`` the scope requires nothing, and the rule's
# ``rule_asserts.tick_size_table`` adds ``spread_table`` (required; part_a before 2020-06-01, part_d from it) for this
# rule only, so fees, sessions and VCM under ``hk_etf`` still need no context; ``hk_etf_part_b`` requires
# ``spread_table`` for every rule and asserts part_b. A contradicting value is a context conflict (MISSING_CONTEXT).
_QUALIFIERS = ("from", "to", "unless", "when", "required")
_OPS = ("eq", "in", "not_in", "min", "max")


def _supplied(ctx: dict, k: str) -> bool:
    """A key counts as supplied only with a non-null value (``{"board": None}`` is missing, not a value)."""
    return ctx.get(k) is not None


def _applies(entry: dict, ctx: dict, date: str) -> bool:
    """Does a constraint entry apply on ``date`` given the context (from/to/unless/when qualifiers)?"""
    if "from" in entry and date < str(entry["from"]):
        return False
    if "to" in entry and date >= str(entry["to"]):
        return False
    if any(ctx.get(k) == v for k, v in (entry.get("unless") or {}).items()):
        return False
    if any(ctx.get(k) != v for k, v in (entry.get("when") or {}).items()):
        return False
    return True


def _holds(entry: dict, v) -> bool:
    """Does value ``v`` satisfy the comparison operators of one constraint entry?"""
    unknown = set(entry) - set(_OPS) - set(_QUALIFIERS)
    if unknown:
        raise ValueError(f"scopes.yaml: unknown constraint operator(s) {sorted(unknown)}")
    if "eq" in entry and v != entry["eq"]:
        return False
    if "in" in entry and v not in entry["in"]:
        return False
    if "not_in" in entry and v in entry["not_in"]:
        return False
    if "min" in entry or "max" in entry:
        if not isinstance(v, int) or isinstance(v, bool):
            return False
        if "min" in entry and v < entry["min"]:
            return False
        if "max" in entry and v > entry["max"]:
            return False
    return True


def _describe(entry: dict) -> str:
    bits = []
    for op in _OPS:
        if op in entry:
            bits.append({"eq": "= ", "in": "in ", "not_in": "not in ", "min": "≥ ", "max": "≤ "}[op] + repr(entry[op]))
    if "from" in entry: bits.append(f"from {entry['from']}")
    if "to" in entry: bits.append(f"before {entry['to']}")
    if "unless" in entry: bits.append(f"unless {entry['unless']}")
    if "when" in entry: bits.append(f"when {entry['when']}")
    return " ".join(bits)


def check_context(asserts: dict, ctx: dict, date: str) -> tuple[list, list]:
    """Evaluate a declarative constraint map (data/<market>/scopes.yaml ``asserts``) against supplied context.

    Returns (missing, conflicts). A scalar constraint means equality. A dict is one entry; a list is several, all of
    which must hold where they apply. ``required: true`` makes an applicable entry's key missing when absent;
    otherwise an absent (or null) key is not checked here — the scope's ``requires`` list decides what is missing.
    """
    missing, conflicts = [], []
    for k, spec in asserts.items():
        entries = spec if isinstance(spec, list) else [spec if isinstance(spec, dict) else {"eq": spec}]
        for e in entries:
            if not _applies(e, ctx, date):
                continue
            if not _supplied(ctx, k):
                if e.get("required") and k not in missing:
                    missing.append(k)
                continue
            if not _holds(e, ctx[k]):
                conflicts.append({"key": k, "supplied": ctx[k], "scope_asserts": _describe(e) if isinstance(spec, (dict, list)) else spec})
    return missing, conflicts


def _base(rule, date, scope, market) -> dict:
    return {"contract_version": CONTRACT_VERSION, "status": None, "rule": rule, "trade_date": _check_date(date, "trade_date"),
            "market": market, "scope": scope, "result": None, "record_id": None,
            "required_context": [], "missing_context": [], "context_conflicts": [],
            "known_gap_ids": [], "evidence_refs": [], "verification": None,
            "ruleset_version": VERSION, "ruleset_hash": dataset_digest(), "reason": "",
            "tracking": {"tracked_through": None, "beyond": None}, "warnings": [], "alternatives": {}}


def _evidence(rec: Record) -> list[dict]:
    return [{"url": s.get("url"), "publisher": s.get("publisher"), "date": s.get("date"), "kind": s.get("kind"),
             "content_sha256": s.get("content_sha256")} for s in rec.sources]


@lru_cache(maxsize=None)
def _by_id() -> dict:
    return {r.id: r for r in records()}


def resolve(rule: str, trade_date: str, scope: str = "stock", market: str | None = None,
            context: dict | None = None, min_verification: str = "single-source",
            market_prefix: str | None = None, *, as_of: str | None = None, require_tracked: bool = False) -> dict:
    """See module docstring. Never raises for data reasons; raises only on programmer error (bad args).

    ``market_prefix`` (the data/<prefix>/ scope registry and known gaps) defaults to ``market_prefix_for(market)``:
    'hk' for XHKG, 'us' for XNYS / XNAS, 'cn' otherwise.

    ``as_of`` (ISO date): answer only from rules officially published on or before it. The output then carries
    an ``as_of`` key; without it there is no ``as_of`` key and the answer is the same.

    ``tracking`` / ``warnings`` are always present (module docstring). ``require_tracked=True`` (keyword-only):
    a carry-forward answer is refused with status BEYOND_TRACKING (``record_id`` and evidence kept, ``result`` null)."""
    out = _resolve(rule, trade_date, scope, market, context, min_verification, market_prefix, as_of)
    rec = _by_id().get(out["record_id"]) if out["record_id"] else None
    trk = tracking_state(market or (rec.market if rec is not None else None), scope, out["trade_date"])
    out["tracking"] = trk
    if out["status"] == "DETERMINED" and rec is not None and rec.effective_to is None and trk["beyond"] is not False:
        untracked = trk["tracked_through"] is None
        out["warnings"] = [WARNING_UNTRACKED if untracked else WARNING_BEYOND]
        if require_tracked:
            out["status"] = "BEYOND_TRACKING"; out["result"] = None
            out["reason"] = (f"{rec.id} is open-ended and {out['trade_date']} is beyond what was checked: "
                             + (f"market {market or rec.market} is not tracked" if untracked else
                                f"the sources were checked only through {trk['tracked_through']}")
                             + "; the value would be a carry-forward, not a finding (require_tracked)")
    return out


def _resolve(rule, trade_date, scope, market, context, min_verification, market_prefix, as_of) -> dict:
    if min_verification not in _LEVEL:
        raise ValueError(f"min_verification must be one of {sorted(_LEVEL)}")
    as_of = _check_as_of(as_of)
    trade_date = _check_date(trade_date, "trade_date")
    market_prefix = market_prefix or market_prefix_for(market)
    out = _base(rule, trade_date, scope, market)
    if as_of is not None:
        out["as_of"] = as_of
    ctx = dict(context or {})
    reg = scopes(market_prefix).get(scope)
    if reg is None:
        out["status"] = "OUT_OF_COVERAGE"
        d = out["trade_date"]
        kg = gaps_for(market, scope, rule, d, d + "\x00", market_prefix)  # point query: [d, d]
        out["known_gap_ids"] = sorted(g["gap_id"] for g in kg)
        out["reason"] = f"scope {scope!r} is not in the registry" + (f"; known gap(s) {out['known_gap_ids']}" if kg else "; no known gap matches — a blind spot")
        close = similar_names(scope, scopes(market_prefix))
        if close:
            out["alternatives"] = {"similar_scopes": close}
            out["reason"] += f"; closest scope name(s): {', '.join(close)}"
        return out

    # 1) context: required keys present (non-null), and not contradicting the scope's declared constraints.
    #    A rule that depends only on the instrument family (tick size) does not need the scope's
    #    status context: asking for st_status to answer "what is the tick" would be a false demand.
    #    Supplied keys are always checked against the scope's ``asserts`` — a contradiction is never ignored.
    if rule in _RULE_CONTEXT:
        required = [k for k in reg["requires"] if k in _RULE_CONTEXT[rule]]
    else:
        required = list(reg["requires"])
    rule_spec = (reg.get("rule_asserts") or {}).get(rule) or {}
    required += [k for k in rule_spec.get("requires", ()) if k not in required]
    out["required_context"] = required
    d = out["trade_date"]
    missing = [k for k in required if not _supplied(ctx, k)]
    m1, conflicts = check_context(reg.get("asserts") or {}, ctx, d)
    m2, c2 = check_context(rule_spec.get("asserts") or {}, ctx, d)
    conflicts += c2
    missing += [k for k in m1 + m2 if k not in missing]
    # A rule the dataset does not hold for this scope / market cannot be answered whatever context is supplied:
    # fall through to the lookup, which reports OUT_OF_COVERAGE with what does exist, instead of asking for context.
    if (missing or conflicts) and rule in rules_for(scope, market):
        out["status"] = "MISSING_CONTEXT"; out["missing_context"] = missing; out["context_conflicts"] = conflicts
        bits = []
        if missing:
            bits.append(f"scope {scope!r} requires {missing} — Marina holds rules, not a security's history; supply it")
        if conflicts:
            bits.append("supplied context contradicts the scope: " + "; ".join(f"{c['key']}={c['supplied']!r} but {scope} asserts {c['scope_asserts']!r}" for c in conflicts))
        out["reason"] = ". ".join(bits)
        return out

    # 2) lookup. tick_size is recorded per instrument family (stock / bse_stock / etf / b_share): look it up under
    #    the family of the requested scope (BSE boards, or family stock with market BJSE → bse_stock), the same
    #    mapping tick_size() and limit_price() use.
    lscope = lookup_scope(rule, scope, market)
    contract = ctx.get("contract")
    try:
        rec = record_at(rule, trade_date, lscope, market, as_of=as_of, contract=contract)
    except ContractRequired as e:
        out["status"] = "MISSING_CONTEXT"; out["missing_context"] = ["contract"]
        out["required_context"] = required + ["contract"]
        out["reason"] = (f"{rule} under {scope!r} differs by futures contract on {out['trade_date']} "
                         f"({', '.join(r.id for r in e.records if r.contracts is not None)}); supply context.contract, "
                         "e.g. the exchange code 'au2606'")
        return out
    except NotYetPublished as e:
        r = e.record
        out["status"] = "NOT_YET_PUBLISHED"; out["record_id"] = r.id; out["verification"] = r.verification
        out["evidence_refs"] = _evidence(r)
        out["reason"] = (f"{r.id} is in force on {out['trade_date']} but was published {r.published_at}, after as_of "
                         f"{as_of}: the answer was not knowable at as_of (Marina does not substitute the predecessor rule)")
        return out
    except PublicationUnknown as e:
        r = e.record
        out["status"] = "UNKNOWN_PUBLICATION"; out["record_id"] = r.id; out["verification"] = r.verification
        out["evidence_refs"] = _evidence(r)
        out["reason"] = (f"{r.id} is in force on {out['trade_date']} but its publication date was not located "
                         f"(published_at: null): whether it was public on as_of {as_of} is unknown")
        return out
    except RuleConflict as e:
        out["status"] = "CONFLICT"; out["reason"] = f"{e} — dataset error; open an issue, do not pick one"
        return out
    except KeyError as e:
        out["status"] = "OUT_OF_COVERAGE"
        d = out["trade_date"]
        kg = gaps_for(market, lscope, rule, d, d + "\x00", market_prefix, contract=contract)
        out["known_gap_ids"] = sorted(g["gap_id"] for g in kg)
        msg = e.args[0] if e.args and isinstance(e.args[0], str) else str(e).strip("'")
        out["reason"] = msg + (f"; known gap(s) {out['known_gap_ids']}: " + " | ".join(g["reason"] for g in kg) if kg else "; no known gap matches — a blind spot")
        have = rules_for(scope, market)
        alt = {"scope_rules": sorted(have)}
        if rule in have:
            alt["rule_intervals"] = have[rule]
        else:
            alt["similar_rules"] = similar_names(rule, have)
        on = markets_recorded(scope) if market else []
        if on and not set(market.split("+")) <= set(on):
            alt["markets"] = on
        out["alternatives"] = alt
        return out

    # 3) evidence bar
    out["record_id"] = rec.id; out["verification"] = rec.verification; out["evidence_refs"] = _evidence(rec)
    if rec.contracts is not None and "contract" not in out["required_context"]:
        out["required_context"] = required + ["contract"]
    if _LEVEL[rec.verification] > _LEVEL[min_verification]:
        out["status"] = "UNVERIFIED"
        out["reason"] = f"record {rec.id} is {rec.verification!r}; caller requires at least {min_verification!r}"
        return out
    out["status"] = "DETERMINED"
    out["result"] = {"value": rec.value, "effective_from": rec.effective_from, "effective_to": rec.effective_to,
                     "published_at": rec.published_at, "unit": getattr(rec, "unit", None)}
    if rec.contracts is not None:
        out["result"]["contracts"] = rec.contracts
    out["reason"] = f"{rec.id} in force [{rec.effective_from}, {rec.effective_to or '∞'}), {rec.verification}, {len(rec.sources)} source(s)"
    return out


def contract_schema() -> dict:
    """JSON Schema (draft 2020-12) of the dict returned by resolve(). Stable within contract_version."""
    status = list(STATUSES)
    nullable = lambda t: {"type": [t, "null"]}
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://github.com/David-Marina/marina-rules/contract/v1",
        "title": "Marina Rule Decision",
        "type": "object", "additionalProperties": False,
        "required": ["contract_version", "status", "rule", "trade_date", "scope", "result", "record_id",
                     "required_context", "missing_context", "context_conflicts", "known_gap_ids",
                     "evidence_refs", "verification", "ruleset_version", "ruleset_hash", "reason"],
        "properties": {
            "contract_version": {"const": CONTRACT_VERSION},
            "status": {"enum": status},
            "rule": {"type": "string"}, "trade_date": {"type": "string", "pattern": r"^\d{4}-\d{2}-\d{2}$"},
            "market": nullable("string"), "scope": {"type": "string"},
            "as_of": {"type": "string", "pattern": r"^\d{4}-\d{2}-\d{2}$"},
            "result": {"type": ["object", "null"], "properties": {
                "value": {}, "effective_from": {"type": "string"}, "effective_to": nullable("string"),
                "published_at": nullable("string"), "unit": nullable("string"),
                "contracts": {"type": "object", "description": "present only when the record covers part of the "
                              "product's contracts (docs/SCHEMA.md, Contract selectors)"}}},
            "tracking": {"type": "object", "additionalProperties": False, "required": ["tracked_through", "beyond"],
                         "description": "how far the official sources for the market were checked for rule changes "
                                        "(docs/SCHEMA.md, Tracking registry); both null when the market is untracked",
                         "properties": {"tracked_through": {"type": ["string", "null"], "pattern": r"^\d{4}-\d{2}-\d{2}$"},
                                        "beyond": {"type": ["boolean", "null"]}}},
            "warnings": {"type": "array", "items": {"enum": list(WARNINGS)},
                         "description": "carry-forward warnings on a DETERMINED answer from an open-ended record"},
            "alternatives": {"type": "object", "additionalProperties": False,
                             "description": "what can be asked instead, on OUT_OF_COVERAGE only (empty otherwise): the "
                                            "rule names the scope has, names close to the one asked, the intervals the "
                                            "asked rule does have, scope names close to an unknown scope, or the market codes "
                                            "the scope is recorded on when it is not recorded on the one asked. A "
                                            "similar name is a different rule: read its definition before using it",
                             "properties": {"scope_rules": {"type": "array", "items": {"type": "string"}},
                                            "similar_rules": {"type": "array", "items": {"type": "string"}},
                                            "rule_intervals": {"type": "array", "items": {"type": "array"}},
                                            "similar_scopes": {"type": "array", "items": {"type": "string"}},
                                            "markets": {"type": "array", "items": {"type": "string"}}}},
            "record_id": nullable("string"),
            "required_context": {"type": "array", "items": {"type": "string"}},
            "missing_context": {"type": "array", "items": {"type": "string"}},
            "context_conflicts": {"type": "array", "items": {"type": "object"}},
            "known_gap_ids": {"type": "array", "items": {"type": "string", "pattern": r"^G-([A-Z]{2}-)?\d{4}$"}},
            "evidence_refs": {"type": "array", "items": {"type": "object", "properties": {
                "url": {"type": "string"}, "publisher": nullable("string"), "date": nullable("string"),
                "kind": {"enum": ["official", "secondary", None]}, "content_sha256": nullable("string")}}},
            "verification": {"enum": ["verified", "single-source", "unverified", None]},
            "ruleset_version": {"type": "string"}, "ruleset_hash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
            "reason": {"type": "string"},
        },
    }


def _tick_map() -> dict:
    from . import _TICK_SCOPE
    return dict(_TICK_SCOPE)


def capabilities(market_prefix: str = "cn") -> dict:
    """Machine-readable capability sheet: what can be asked, for which markets/scopes/dates, what context
    each scope needs, what the answer looks like, and what is known to be missing. Generated from the
    data, never hand-maintained; publish it next to each release."""
    from . import records as _records, known_gaps as _gaps
    recs = [r for r in _records() if r.file.startswith(market_prefix + "/")]
    rules: dict[str, dict] = {}
    for r in recs:
        e = rules.setdefault(r.rule, {"scopes": set(), "markets": set(), "earliest": r.effective_from, "latest_open": False,
                                      "verification": {}})
        e["scopes"].add(r.scope); e["markets"].update(r.market.split("+"))
        e["earliest"] = min(e["earliest"], r.effective_from); e["latest_open"] |= r.effective_to is None
        e["verification"][r.verification] = e["verification"].get(r.verification, 0) + 1
        if r.contracts is not None:
            e.setdefault("contract_keyed", set()).add(r.scope)
    reg = scopes(market_prefix)
    return {
        "capabilities_version": CONTRACT_VERSION, "ruleset_version": VERSION, "ruleset_hash": dataset_digest(),
        "entrypoints": {
            "python": {"resolve": "marina_rules.contract.resolve(rule, trade_date, scope, market, context, min_verification, "
                                  "as_of=None, require_tracked=False)",
                       "coverage": "marina_rules.coverage(market, scope, rules, start, end, as_of=None, contract=None, "
                                   "require_tracked=False)",
                       "tracked_through": "marina_rules.tracked_through(market, scope=None)",
                       "rules_for": "marina_rules.rules_for(scope, market=None) — rule names a scope has, with intervals",
                       "statutory_fee_floor": "marina_rules.statutory_fee_floor(turnover, side, date, market=None); "
                                              "statutory_fee_components(...) for the per-rule amounts and record ids",
                       "skill_text": "marina_rules.skill_text() — the usage notes shipped with the package",
                       "cli": "marina-rules | python -m marina_rules: query, rules, scopes, fees, check, adapt, capabilities, "
                              "schema, skill, version",
                       "limit_price": "marina_rules.limit_price(prev_close, scope, date, market, as_of=None)",
                       "diff": "python -m marina_rules.diff <from_tag> <to_tag>",
                       "check": "python -m marina_rules.check fills.csv",
                       "adapt": "marina-rules adapt trades.csv --format NAME [--bars FILE --bars-format NAME] — an "
                                "engine's trade export as checker rows; marina_rules.adapt.adapt_rows(...) in process"},
            "statuses": list(STATUSES),
            "as_of": "optional ISO date on record_at/rule_at/coverage/resolve/limit_price/tick_size: answer only from "
                     "rules with published_at <= as_of; published later → NOT_YET_PUBLISHED, published_at null → "
                     "UNKNOWN_PUBLICATION; never falls back to an older record",
            "decision_schema": "python -m marina_rules.contract --schema",
            "tracking": "every decision carries tracking {tracked_through, beyond}; a DETERMINED answer from an open-ended "
                        "record after tracked_through warns CARRY_FORWARD_BEYOND_TRACKED (untracked market: "
                        "CARRY_FORWARD_UNTRACKED) — a carry-forward, not a finding; require_tracked=True refuses it as "
                        "BEYOND_TRACKING (record_at / rule_at raise BeyondTracking)",
        },
        "preflight": ["pass dates as ISO 'YYYY-MM-DD' strings or date / datetime objects; any other spelling "
                      "(20200102, 2020/1/2, an int) raises ValueError — it is refused, never guessed",
                      "coverage() over the whole window before any computation",
                      "supply every key in scope.requires per security per day; Marina never infers them",
                      "stop on any status other than DETERMINED; cite known_gap_ids when present",
                      "on OUT_OF_COVERAGE read alternatives: the scope may hold the rule under another name "
                      "(scope_rules, similar_rules) or on another market code (markets) — a different name is a different "
                      "rule, check its definition",
                      "when tracking.beyond is true or warnings is not empty, say the answer is carried forward beyond "
                      "the date the sources were checked, or pass require_tracked=True",
                      "put citation() into every result"],
        "rules": {k: {"scopes": sorted(v["scopes"]), "markets": sorted(v["markets"]), "earliest_effective_from": v["earliest"],
                      "has_open_interval": v["latest_open"], "records_by_verification": v["verification"],
                      **({"contract_keyed_scopes": sorted(v["contract_keyed"])} if v.get("contract_keyed") else {})}
                  for k, v in sorted(rules.items())},
        "scopes": {k: {"description": v["description"], "requires": list(v["requires"]), "excludes": list(v["excludes"]),
                       "asserts": v.get("asserts") or {}, "rule_asserts": v.get("rule_asserts") or {}}
                   for k, v in sorted(reg.items())},
        "context_constraints": {"grammar": "data/<market>/scopes.yaml header: scalar = equality; {eq|in|not_in|min|max} with "
                                           "qualifiers from/to (trade-date window), unless/when (context condition), required; "
                                           "a list = every applicable entry must hold; null value = not supplied",
                                "on_violation": "MISSING_CONTEXT with context_conflicts / missing_context"},
        **({"contract_selectors": {
            "context_key": "contract — the exchange contract code, e.g. au2606; needed where rules[*].contract_keyed_scopes "
                           "lists the scope (otherwise MISSING_CONTEXT with missing_context ['contract'])",
            "grammar": "record/gap field contracts: {any|none: [clause]}; clause keys (AND): code {in|not_in}, "
                       "delivery_month {in|not_in}, months_to_delivery {min|max|in} = delivery month index minus trade "
                       "month index; docs/SCHEMA.md 'Contract selectors'"}}
           if any(r.contracts is not None for r in recs) else {}),
        "tick_families": {"rule": "tick_size", "map": dict(sorted(_tick_map().items())), "default": "stock",
                          "default_applies_to": "mainland securities scopes only (records on XSHG / XSHE / BJSE); a "
                                                "futures, Hong Kong or US scope has no tick family"},
        "context_vocabulary": sorted({c for v in reg.values() for c in v["requires"]}
                                     | ({"contract"} if any(r.contracts is not None for r in recs) else set())),
        "known_gaps": [{**{k: g[k] for k in ("gap_id", "market", "scope", "rule", "interval", "severity", "status")},
                        **({"contracts": g["contracts"]} if g.get("contracts") is not None else {})} for g in _gaps(market_prefix)],
        "tracking": {"entries": tracking_registry(market_prefix),
                     "untracked_markets": sorted(m for m in {x for r in recs for x in r.market.split("+")}
                                                 if tracked_through(m) is None),
                     "meaning": "tracked_through = last date the official sources were checked for rule changes; after "
                                "it (or on an untracked market) an open-ended record is a carry-forward, not a finding"},
        "not_in_scope": ["market data", "security master", "point-in-time ST / listing histories", "matching, slippage, strategy"],
    }


def main(argv=None) -> int:
    import sys
    a = list(sys.argv[1:] if argv is None else argv)
    if "--schema" in a:
        print(json.dumps(contract_schema(), indent=1)); return 0
    if "--capabilities" in a:   # optional market family after the flag: --capabilities hk | us
        i = a.index("--capabilities")
        pfx = a[i + 1] if i + 1 < len(a) and not a[i + 1].startswith("--") else "cn"
        print(json.dumps(capabilities(pfx), ensure_ascii=False, indent=1)); return 0
    if len(a) < 3:
        print("usage: python -m marina_rules.contract <rule> <date> <scope> [market] [--context k=v,k=v] [--min verified]"
              " [--as-of YYYY-MM-DD] [--require-tracked]\n"
              "       python -m marina_rules.contract --schema\n"
              "       python -m marina_rules.contract --capabilities [cn|hk|us]"); return 2
    rule, date, scope = a[0], a[1], a[2]
    market = a[3] if len(a) > 3 and not a[3].startswith("--") else None
    ctx = {}
    if "--context" in a:
        for kv in a[a.index("--context") + 1].split(","):
            k, v = kv.split("=", 1)
            ctx[k] = {"true": True, "false": False}.get(v.lower(), int(v) if v.lstrip("-").isdigit() else v)
    mv = a[a.index("--min") + 1] if "--min" in a else "single-source"
    as_of = None
    if "--as-of" in a:
        i = a.index("--as-of")
        if i + 1 >= len(a):
            print("--as-of needs a date YYYY-MM-DD"); return 2
        as_of = a[i + 1]
    try:
        d = resolve(rule, date, scope, market, ctx, mv, as_of=as_of, require_tracked="--require-tracked" in a)
    except ValueError as e:
        print(f"error: {e}"); return 2
    print(json.dumps(d, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
