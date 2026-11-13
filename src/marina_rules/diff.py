"""diff_rules — what changed between two Marina versions, and whether a backtest must be re-run.

    python -m marina_rules.diff 2026.10.26.4 2026.10.26.5 [--json] [--rule price_limit_pct] [--scope st_main]

A version is a git ref (tag / commit) of this repository or a directory containing ``data/``.
Records are compared by id; ids that disappeared but match an old record on
(market, rule, value, effective_from) are reported as renames rather than remove+add.

Every change carries a ``kind`` that answers the only question a backtester has:

  regime_change    a new interval was appended for an existing (market, scope, rule) — the rule
                   itself changed on ``effective_from``. Re-run anything that touches that interval.
  correction       an existing record's value / dates were edited, or history was re-cut — Marina
                   was wrong about the past. Re-run everything that touched the affected interval
                   under the OLD version; those results were computed with a wrong rule.
  coverage_added   a (market, scope, rule) that did not exist before. Nothing to re-run unless you
                   were substituting something for the missing rule — in which case, everything.
  rename           same fact, new id/scope name. Update code, not results.
  removed          record gone with no match. Treat as correction until explained.
  bookkeeping      an open interval was closed exactly where its already-existing successor begins.
                   Lookups were unchanged (latest effective_from already won). No behavioural effect.
  metadata         notes / sources / verification / published_at changed; values and dates did not.
                   No behavioural effect. ``verification`` downgrades are flagged separately.

Both versions are pinned by their dataset digest (same function as ``citation()``); keep both in
the report. Marina does not compute P&L impact; that is the caller's job and the point of the
``affected_interval``.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from typing import Any

import yaml

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
VALUE_FIELDS = ("market", "scope", "rule", "value", "effective_from", "effective_to", "contracts")
META_FIELDS = ("verification", "notes", "published_at", "recorded_at", "sources")


# ----------------------------------------------------------------------------------------------- load
def _norm(v):
    if v is None:
        return None
    return v.isoformat() if hasattr(v, "isoformat") else (str(v)[:10] if _looks_date(v) else v)


def _looks_date(v) -> bool:
    s = str(v)
    return len(s) >= 10 and s[4] == "-" and s[7] == "-"


def _files_from_git(ref: str) -> dict[str, bytes]:
    out = subprocess.run(["git", "-C", REPO, "ls-tree", "-r", "--name-only", ref, "data/"],
                         capture_output=True, text=True)
    if out.returncode != 0:
        raise ValueError(f"not a git ref in {REPO}: {ref!r} ({out.stderr.strip()})")
    files = {}
    for rel in sorted(p for p in out.stdout.split() if p.endswith((".yaml", ".yml"))):
        files[os.path.relpath(rel, "data")] = subprocess.run(["git", "-C", REPO, "show", f"{ref}:{rel}"],
                                                             capture_output=True).stdout
    return files


def _files_from_dir(path: str) -> dict[str, bytes]:
    data = os.path.join(path, "data") if os.path.isdir(os.path.join(path, "data")) else path
    files = {}
    for root, _, names in os.walk(data):
        for f in sorted(names):
            if f.endswith((".yaml", ".yml")):
                p = os.path.join(root, f)
                with open(p, "rb") as fh:
                    files[os.path.relpath(p, data)] = fh.read()
    return files


def load_version(ref: str) -> dict[str, Any]:
    """{'ref', 'digest', 'records': {id: record}} for a git ref or a directory. Lenient: old schemas load."""
    files = _files_from_dir(ref) if os.path.isdir(ref) else _files_from_git(ref)
    h = hashlib.sha256()
    recs: dict[str, dict] = {}
    for rel in sorted(files):
        h.update(rel.encode()); h.update(files[rel])
        doc = yaml.safe_load(files[rel]) or {}
        for r in doc.get("records") or []:
            rec = {k: _norm(r.get(k)) for k in VALUE_FIELDS}
            rec["market"] = rec["market"] or doc.get("market")
            rec["verification"] = r.get("verification")
            rec["notes"] = (r.get("notes") or "").strip()
            rec["published_at"] = _norm(r.get("published_at"))
            rec["recorded_at"] = _norm(r.get("recorded_at"))
            rec["sources"] = tuple(sorted(s.get("url", "") for s in (r.get("sources") or [])))
            rec["file"] = rel
            recs[r["id"]] = rec
    return {"ref": ref, "digest": h.hexdigest(), "records": recs}


# ----------------------------------------------------------------------------------------------- diff
def _key(r): return (r["market"], r["scope"], r["rule"])


def _interval(r): return {"from": r["effective_from"], "to": r["effective_to"]}


def _union(a, b):
    lo = min(x for x in (a["from"], b["from"]) if x) if (a["from"] or b["from"]) else None
    tos = [a["to"], b["to"]]
    hi = None if any(t is None for t in tos) else max(tos)
    return {"from": lo, "to": hi}


def diff_rules(from_version: str, to_version: str, rule: str | None = None, scope: str | None = None) -> dict:
    old, new = load_version(from_version), load_version(to_version)
    O, N = old["records"], new["records"]
    _LIVE_SCOPES.clear(); _LIVE_SCOPES.update(r["scope"] for r in N.values())
    changes: list[dict] = []

    # renames: old id gone, new id present with identical fact
    gone = [i for i in O if i not in N]
    fresh = [i for i in N if i not in O]
    renamed: dict[str, str] = {}
    for oi in gone:
        o = O[oi]
        cands = [ni for ni in fresh if ni not in renamed.values()
                 and N[ni]["market"] == o["market"] and N[ni]["rule"] == o["rule"]
                 and N[ni]["value"] == o["value"] and N[ni]["effective_from"] == o["effective_from"]]
        if len(cands) == 1:
            renamed[oi] = cands[0]
    for oi, ni in renamed.items():
        o, n = O[oi], N[ni]
        ch = {"change_type": "renamed", "kind": "rename", "record_id": ni, "old_id": oi, "key": _key(n),
              "affected_interval": _interval(n), "old": None, "new": None,
              "reason": "same (market, rule, value, effective_from); " + ("scope renamed" if o["scope"] != n["scope"] else "id renamed")}
        if o["effective_to"] != n["effective_to"]:
            ch["kind"] = "correction"; ch["old"] = {"effective_to": o["effective_to"]}; ch["new"] = {"effective_to": n["effective_to"]}
            ch["affected_interval"] = _union(_interval(o), _interval(n)); ch["reason"] += "; interval end changed"
        changes.append(ch)

    # modified
    for i in O:
        if i not in N:
            continue
        o, n = O[i], N[i]
        vdiff = {k: (o[k], n[k]) for k in VALUE_FIELDS if o[k] != n[k]}
        mdiff = {k: (o[k], n[k]) for k in META_FIELDS if o[k] != n[k]}
        if not vdiff and not mdiff:
            continue
        if vdiff:
            kind = "correction"
            if set(vdiff) == {"scope"} and _scope_family(o["scope"], n["scope"]):
                kind = "rename"
            elif set(vdiff) == {"effective_to"} and n["effective_to"] and o["effective_to"] is None:
                succ = [j for j in N if _key(N[j]) == _key(n) and N[j]["effective_from"] == n["effective_to"]]
                if succ:
                    # successor existed before too → nothing a lookup returns has changed
                    kind = "bookkeeping" if any(j in O for j in succ) else "regime_change"
            changes.append({"change_type": "modified", "kind": kind, "record_id": i, "key": _key(n),
                            "affected_interval": _union(_interval(o), _interval(n)),
                            "old": {k: v[0] for k, v in vdiff.items()}, "new": {k: v[1] for k, v in vdiff.items()},
                            "reason": _reason(o, n, vdiff), "sources_added": sorted(set(n["sources"]) - set(o["sources"]))})
        else:
            changes.append({"change_type": "modified", "kind": "metadata", "record_id": i, "key": _key(n),
                            "affected_interval": _interval(n),
                            "old": {k: (v[0] if k != "sources" else len(v[0])) for k, v in mdiff.items()},
                            "new": {k: (v[1] if k != "sources" else len(v[1])) for k, v in mdiff.items()},
                            "reason": ", ".join(sorted(mdiff)),
                            "verification_downgraded": _rank(n["verification"]) > _rank(o["verification"])})

    # moved: old id gone, new id present, same key family and value, different dates = a correction of dates
    moved: dict[str, str] = {}
    for oi in gone:
        if oi in renamed:
            continue
        o = O[oi]
        cands = [ni for ni in fresh if ni not in renamed.values() and ni not in moved.values()
                 and _same_family(o, N[ni]) and N[ni]["value"] == o["value"]]
        if len(cands) == 1:
            moved[oi] = cands[0]
    for oi, ni in moved.items():
        o, n = O[oi], N[ni]
        changes.append({"change_type": "modified", "kind": "correction", "record_id": ni, "old_id": oi, "key": _key(n),
                        "affected_interval": _union(_interval(o), _interval(n)),
                        "old": {"effective_from": o["effective_from"], "effective_to": o["effective_to"]},
                        "new": {"effective_from": n["effective_from"], "effective_to": n["effective_to"]},
                        "reason": f"dates moved: [{o['effective_from']}, {o['effective_to']}) → [{n['effective_from']}, {n['effective_to']})",
                        "sources_added": sorted(set(n["sources"]) - set(o["sources"]))})

    # added
    for i in fresh:
        if i in renamed.values() or i in moved.values():
            continue
        n = N[i]; k = _key(n)
        prior = [r for r in O.values() if _same_family(r, n)]
        if not prior:
            kind, why = "coverage_added", "no record of this (market, scope, rule) in the old version"
        elif all(p["effective_from"] < n["effective_from"] and (p["effective_to"] is None or p["effective_to"] <= n["effective_from"])
                 for p in prior):
            kind, why = "regime_change", "new interval appended after all existing ones for this key"
        else:
            kind, why = "correction", "new interval inside or before existing history for this key (history re-cut)"
        changes.append({"change_type": "added", "kind": kind, "record_id": i, "key": k, "affected_interval": _interval(n),
                        "old": None, "new": {"value": n["value"], "effective_from": n["effective_from"], "effective_to": n["effective_to"]},
                        "reason": why, "verification": n["verification"], "sources": len(n["sources"])})

    # removed
    for i in gone:
        if i in renamed or i in moved:
            continue
        o = O[i]
        succ = [c["record_id"] for c in changes if c["change_type"] == "added" and c["kind"] == "correction"
                and _same_family(o, N[c["record_id"]])]
        changes.append({"change_type": "removed", "kind": "correction" if succ else "removed", "record_id": i, "key": _key(o),
                        "affected_interval": _interval(o), "old": {"value": o["value"]}, "new": None,
                        "reason": ("superseded by " + ", ".join(succ)) if succ else "no matching record in the new version"})

    if rule:
        changes = [c for c in changes if c["key"][2] == rule]
    if scope:
        changes = [c for c in changes if c["key"][1] == scope]
    order = {"correction": 0, "regime_change": 1, "removed": 2, "coverage_added": 3, "rename": 4, "bookkeeping": 5, "metadata": 6}
    changes.sort(key=lambda c: (order[c["kind"]], c["affected_interval"]["from"] or "", c["record_id"]))
    rerun = sorted({json.dumps({"key": list(c["key"]), **c["affected_interval"]}) for c in changes
                    if c["kind"] in ("correction", "regime_change", "removed")})
    return {"from": {"version": from_version, "dataset_sha256": old["digest"], "records": len(O)},
            "to": {"version": to_version, "dataset_sha256": new["digest"], "records": len(N)},
            "summary": {k: sum(1 for c in changes if c["kind"] == k) for k in order},
            "rerun_intervals": [json.loads(x) for x in rerun],
            "changes": changes}


_LIVE_SCOPES: set = set()   # scopes present in the NEW version; set by diff_rules before matching


def _scope_family(a: str, b: str) -> bool:
    """Same scope, or a prefix rename ('ipo_first5' → 'ipo_first5_star') where the OLD name no longer
    exists in the new version. 'etf' vs 'etf_20pct' with 'etf' still live is two populations, not a rename."""
    if a == b:
        return True
    if b.startswith(a + "_") and a not in _LIVE_SCOPES:
        return True
    if a.startswith(b + "_") and b not in _LIVE_SCOPES:
        return True
    return False


def _same_family(o, n) -> bool:
    """Same rule, scope family, and overlapping market sets ('XSHG' ⊂ 'XSHG+XSHE')."""
    if o["rule"] != n["rule"] or not _scope_family(o["scope"], n["scope"]):
        return False
    om, nm = set((o["market"] or "").split("+")), set((n["market"] or "").split("+"))
    return bool(om & nm)


def _rank(v): return {"verified": 0, "single-source": 1, "unverified": 2}.get(v, 3)


def _reason(o, n, vdiff):
    bits = [f"{k}: {v[0]!r} → {v[1]!r}" for k, v in vdiff.items()]
    if n["notes"] != o["notes"]:
        bits.append("notes updated")
    return "; ".join(bits)


# ----------------------------------------------------------------------------------------------- cli
def main(argv=None) -> int:
    a = list(sys.argv[1:] if argv is None else argv)
    if len(a) < 2:
        print(__doc__); return 2
    as_json = "--json" in a
    rule = a[a.index("--rule") + 1] if "--rule" in a else None
    scope = a[a.index("--scope") + 1] if "--scope" in a else None
    d = diff_rules(a[0], a[1], rule=rule, scope=scope)
    if as_json:
        print(json.dumps(d, ensure_ascii=False, indent=1)); return 0
    print(f"marina-rules {d['from']['version']} ({d['from']['records']} records, sha256:{d['from']['dataset_sha256'][:16]})")
    print(f"        →    {d['to']['version']} ({d['to']['records']} records, sha256:{d['to']['dataset_sha256'][:16]})")
    print("summary:", "  ".join(f"{k}={v}" for k, v in d["summary"].items() if v))
    for c in d["changes"]:
        iv = c["affected_interval"]; span = f"[{iv['from']}, {iv['to'] or '∞'})"
        line = f"  {c['kind']:15s} {c['record_id']:44s} {span:28s} {c['reason']}"
        if c["kind"] == "rename":
            line = f"  {c['kind']:15s} {c.get('old_id', c['record_id'])} → {c['record_id']}" + (f"  ({c['reason']})" if c.get("old") else "")
        if c.get("old") and c.get("new") and c["kind"] != "metadata":
            line += f"  | {c['old']} → {c['new']}"
        print(line)
    if d["rerun_intervals"]:
        print("re-run anything that touched:")
        for r in d["rerun_intervals"]:
            print(f"  {'/'.join(map(str, r['key'])):40s} [{r['from']}, {r['to'] or '∞'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
