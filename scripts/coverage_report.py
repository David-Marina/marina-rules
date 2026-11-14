"""Coverage report: resolve every target in coverage/cn_targets.yaml day by day and list the gaps.

    python scripts/coverage_report.py                 # human-readable report; exit 1 on any gap not in `unresolved`
    python scripts/coverage_report.py --json          # machine-readable
    python scripts/coverage_report.py --markdown      # tables for a PR description / CI summary
    python scripts/coverage_report.py --until 2026-10-25
    python scripts/coverage_report.py --brute         # literal day-by-day walk (slow; same result)

A *target* is (market, scope, rule, start[, end]). For every calendar day d in [start, min(end, until+1))
the checker asks ``marina_rules.record_at(rule, d, scope, market)``; exactly one record must be in force
(no record → gap; a conflict → gap too). Records are constant between their effective dates, so the
default mode evaluates one day per record-boundary segment; ``--brute`` evaluates every day and must give
identical intervals (tests/test_coverage_targets.py asserts this).

Gaps the maintainer accepts as unresolvable from official sources are listed in the ``unresolved:``
section of the targets file with a reason. They still count as NOT covered in the percentage; they only
stop the run from failing. A target with ``not_applicable: {reason, sources: [hashed]}`` counts as fully covered
and is listed separately in every output mode.
Targets are never shrunk to hide a gap.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys

import yaml

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))
import marina_rules as mr  # noqa: E402
from marina_rules import RuleConflict  # noqa: E402

TARGETS = os.path.join(ROOT, "coverage", "cn_targets.yaml")
SCOPE_FLOOR = "2006-07-01"
A_SHARE_MARKETS = ("XSHG", "XSHE", "BJSE")


def _d(v) -> str | None:
    if v is None:
        return None
    return v.isoformat() if hasattr(v, "isoformat") else str(v)[:10]


_SHA64 = re.compile(r"^[0-9a-f]{64}$")


def _check_not_applicable(tid: str, na) -> None:
    """not_applicable = {reason, sources: [{url, content_sha256, hash_kind, quote}, ...]} — every source hashed."""
    if not isinstance(na, dict) or not str(na.get("reason", "")).strip():
        raise ValueError(f"target {tid}: not_applicable must be a mapping with a non-empty `reason`")
    srcs = na.get("sources") or []
    if not srcs:
        raise ValueError(f"target {tid}: not_applicable needs at least one source")
    for s in srcs:
        if not str(s.get("url", "")).startswith("http"):
            raise ValueError(f"target {tid}: not_applicable source without an http(s) url")
        if not _SHA64.match(str(s.get("content_sha256", ""))):
            raise ValueError(f"target {tid}: not_applicable source {s.get('url')} has no 64-hex content_sha256")
        if not str(s.get("quote", "")).strip():
            raise ValueError(f"target {tid}: not_applicable source {s.get('url')} has no verbatim quote")


def load(path: str = TARGETS) -> dict:
    """Parse and validate the targets file. Raises ValueError on any structural problem."""
    with open(path, encoding="utf-8") as fh:
        doc = yaml.safe_load(fh)
    existence = doc.get("existence") or {}
    for k, e in existence.items():
        if not (e.get("source") or e.get("existence_source") == "TODO"):
            raise ValueError(f"existence {k}: needs `source` or `existence_source: TODO`")
    out = []
    for t in doc["targets"]:
        for req in ("id", "market", "scope", "rule", "start", "existence"):
            if req not in t:
                raise ValueError(f"target {t.get('id')}: missing {req!r}")
        if t["id"] != f"{t['market']}:{t['scope']}:{t['rule']}":
            raise ValueError(f"target {t['id']}: id must be market:scope:rule")
        if t["market"] not in A_SHARE_MARKETS:
            raise ValueError(f"target {t['id']}: market must be one of {A_SHARE_MARKETS}")
        if t["existence"] not in existence:
            raise ValueError(f"target {t['id']}: unknown existence key {t['existence']!r}")
        start, end = _d(t["start"]), _d(t.get("end"))
        want = max(SCOPE_FLOOR, _d(existence[t["existence"]]["date"]))
        if start != want:
            raise ValueError(f"target {t['id']}: start {start} != max({SCOPE_FLOOR}, existence date) = {want}")
        if end is not None and end <= start:
            raise ValueError(f"target {t['id']}: end must be after start")
        if "not_applicable" in t:
            _check_not_applicable(t["id"], t["not_applicable"])
        out.append({**t, "start": start, "end": end})
    ids = [t["id"] for t in out]
    dup = {i for i in ids if ids.count(i) > 1}
    if dup:
        raise ValueError(f"duplicate target ids: {sorted(dup)}")
    unresolved = doc.get("unresolved") or []
    known = set(ids)
    for u in unresolved:
        if u.get("target") not in known:
            raise ValueError(f"unresolved entry for unknown target {u.get('target')}")
        if not str(u.get("reason", "")).strip():
            raise ValueError(f"unresolved entry for {u['target']} has no reason")
        if "from" not in u or "to" not in u:
            raise ValueError(f"unresolved entry for {u['target']} needs from and to (to may be null)")
    return {"targets": out, "unresolved": unresolved, "existence": existence}


def _ok(rule: str, day: str, scope: str, market: str) -> bool:
    try:
        mr.record_at(rule, day, scope, market)
        return True
    except (KeyError, RuleConflict):
        return False


def _intervals(bad_days: list) -> list:
    """Collapse sorted bad days into half-open [from, to) intervals."""
    out: list = []
    for d in bad_days:
        if out and out[-1]["to"] == d.isoformat():
            out[-1]["to"] = (d + dt.timedelta(days=1)).isoformat()
        else:
            out.append({"from": d.isoformat(), "to": (d + dt.timedelta(days=1)).isoformat()})
    for g in out:
        g["days"] = (dt.date.fromisoformat(g["to"]) - dt.date.fromisoformat(g["from"])).days
    return out


def check_target(t: dict, until: dt.date, brute: bool = False) -> dict:
    """{days, covered_days, gaps:[{from,to,days}]} over [start, min(end, until + 1 day))."""
    start = dt.date.fromisoformat(t["start"])
    end = until + dt.timedelta(days=1)
    if t.get("end"):
        end = min(end, dt.date.fromisoformat(t["end"]))
    total = max(0, (end - start).days)
    if t.get("not_applicable"):
        return {"days": total, "covered_days": total, "gaps": []}
    if brute:
        days = [start + dt.timedelta(days=i) for i in range(total)]
        bad = [d for d in days if not _ok(t["rule"], d.isoformat(), t["scope"], t["market"])]
    else:
        cuts = {start, end}
        for r in mr.records():
            if r.rule == t["rule"] and r.scope == t["scope"]:
                for b in (r.effective_from, r.effective_to):
                    if b:
                        bd = dt.date.fromisoformat(b)
                        if start < bd < end:
                            cuts.add(bd)
        cuts = sorted(cuts)
        bad = []
        for a, b in zip(cuts, cuts[1:]):
            if not _ok(t["rule"], a.isoformat(), t["scope"], t["market"]):
                bad.extend(a + dt.timedelta(days=i) for i in range((b - a).days))
    return {"days": total, "covered_days": total - len(bad), "gaps": _intervals(bad)}


def _pct(c: int, n: int) -> float:
    return round(100.0 * c / n, 2) if n else 100.0


def _breakdown(rows: list, key: str) -> list:
    agg: dict = {}
    for r in rows:
        a = agg.setdefault(r[key], {key: r[key], "targets": 0, "complete": 0, "target_days": 0, "covered_days": 0})
        a["targets"] += 1; a["complete"] += not r["gaps"]
        a["target_days"] += r["days"]; a["covered_days"] += r["covered_days"]
    out = sorted(agg.values(), key=lambda a: a[key])
    for a in out:
        a["coverage_pct"] = _pct(a["covered_days"], a["target_days"])
    return out


def run(until: str | None = None, brute: bool = False, path: str = TARGETS) -> dict:
    cfg = load(path)
    u = dt.date.fromisoformat(until) if until else dt.date.today()
    allow: dict = {}
    for x in cfg["unresolved"]:
        allow.setdefault(x["target"], []).append(x)
    rows, failing = [], []
    tot = cov = 0
    for t in cfg["targets"]:
        r = check_target(t, u, brute)
        tot += r["days"]; cov += r["covered_days"]
        allowed, unexplained = [], []
        for g in r["gaps"]:
            ok = any((_d(x.get("from")) or "0000-01-01") <= g["from"] and g["to"] <= (_d(x.get("to")) or "9999-12-31")
                     for x in allow.get(t["id"], []))
            (allowed if ok else unexplained).append(g)
        if unexplained:
            failing.append(t["id"])
        rows.append({"id": t["id"], "market": t["market"], "scope": t["scope"], "rule": t["rule"], "start": t["start"],
                     "end": t["end"], "applies_to": t.get("applies_to") or [], "not_applicable": t.get("not_applicable"),
                     **r, "allowed_gaps": allowed, "unexplained_gaps": unexplained})
    todo = sorted(k for k, e in cfg["existence"].items() if e.get("existence_source") == "TODO")
    return {"until": u.isoformat(), "scope_floor": SCOPE_FLOOR, "mode": "brute" if brute else "boundary",
            "targets": len(rows), "targets_complete": sum(1 for r in rows if not r["gaps"]),
            "target_days": tot, "covered_days": cov, "coverage_pct": round(100.0 * cov / tot, 4) if tot else 100.0,
            "by_rule": _breakdown(rows, "rule"), "by_scope": _breakdown(rows, "scope"), "by_market": _breakdown(rows, "market"),
            "failing_targets": failing, "unresolved": cfg["unresolved"], "existence_todo": todo,
            "not_applicable": [{"id": r["id"], "reason": r["not_applicable"]["reason"],
                                "sources": [x["url"] for x in r["not_applicable"]["sources"]]}
                               for r in rows if r["not_applicable"]],
            "rows": rows,
            "marina_version": mr.VERSION, "code_version": mr.__version__, "dataset_digest": mr.dataset_digest()}


def _gap_groups(rep: dict) -> list:
    """Group identical (rule, scope, interval) gaps across markets: [(rule, scope, from, to, days, [markets], allowlisted)]."""
    g: dict = {}
    for r in rep["rows"]:
        for x in r["gaps"]:
            k = (r["rule"], r["scope"], x["from"], x["to"])
            e = g.setdefault(k, {"days": x["days"], "markets": [], "allow": True})
            e["markets"].append(r["market"]); e["allow"] &= x in r["allowed_gaps"]
    return [(k[0], k[1], k[2], k[3], v["days"], v["markets"], v["allow"]) for k, v in sorted(g.items())]


def _fmt(rep: dict, markdown: bool) -> str:
    L = []
    head = (f"Coverage of China A-shares (XSHG, XSHE, BJSE) from {rep['scope_floor']} to {rep['until']} (inclusive) — "
            f"marina-rules@{rep['marina_version']} sha256:{rep['dataset_digest'][:16]} code: marina-rules-core@{rep['code_version']}")
    summary = (f"targets: {rep['targets']}, complete: {rep['targets_complete']}, "
               f"target-days covered: {rep['covered_days']}/{rep['target_days']} = {rep['coverage_pct']}%")
    groups = _gap_groups(rep)
    if markdown:
        L += [f"### {head}", "", f"**{summary}**", ""]
        for title, key in (("Per rule", "rule"), ("Per scope", "scope"), ("Per market", "market")):
            L += [f"#### {title}", "", f"| {key} | targets | complete | covered days | total days | % |", "|---|---:|---:|---:|---:|---:|"]
            for a in rep[f"by_{key}"]:
                L.append(f"| {a[key]} | {a['targets']} | {a['complete']} | {a['covered_days']} | {a['target_days']} | {a['coverage_pct']} |")
            L.append("")
        L += [f"#### Gap intervals ({len(groups)})", ""]
        if groups:
            L += ["| rule | scope | markets | gap [from, to) | days | unresolved-listed |", "|---|---|---|---|---:|---|"]
            for rule, scope, f, t, n, mk, al in groups:
                L.append(f"| {rule} | {scope} | {'+'.join(mk)} | {f} → {t} | {n} | {'yes' if al else 'no'} |")
        else:
            L.append("No gaps.")
        if rep["existence_todo"]:
            L += ["", "Existence dates without a source yet (`existence_source: TODO`): " + ", ".join(rep["existence_todo"])]
    else:
        L += [head, summary, "", "per rule:"]
        for a in rep["by_rule"]:
            L.append(f"  {a['rule']:32s} {a['coverage_pct']:7.2f}%  ({a['complete']}/{a['targets']} targets complete)")
        L.append("per scope:")
        for a in rep["by_scope"]:
            L.append(f"  {a['scope']:32s} {a['coverage_pct']:7.2f}%  ({a['complete']}/{a['targets']} targets complete)")
        L.append(f"gaps ({len(groups)}):")
        for rule, scope, f, t, n, mk, al in groups:
            L.append(f"  {'unresolved' if al else 'GAP':10s} {rule:30s} {scope:20s} {'+'.join(mk):15s} {f} → {t} ({n} d)")
    if rep["not_applicable"]:
        if markdown:
            L += ["", f"#### Not applicable ({len(rep['not_applicable'])} targets, counted as covered)", "",
                  "| target | reason | sources |", "|---|---|---|"]
            for x in rep["not_applicable"]:
                L.append(f"| {x['id']} | {x['reason']} | {' '.join(x['sources'])} |")
        else:
            L.append(f"\nNot applicable ({len(rep['not_applicable'])} targets, counted as covered):")
            for x in rep["not_applicable"]:
                L.append(f"  - {x['id']}: {x['reason'][:110]}")
    if rep["unresolved"]:
        L.append("\nUnresolved (listed, counted as NOT covered):")
        for x in rep["unresolved"]:
            L.append(f"  - {x['target']} {_d(x.get('from'))} → {_d(x.get('to'))}: {x['reason']}")
    if rep["failing_targets"]:
        L.append(f"\nFAIL: {len(rep['failing_targets'])} target(s) have gaps that are neither filled nor listed in `unresolved`.")
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--markdown", action="store_true")
    ap.add_argument("--brute", action="store_true", help="literal day-by-day walk (slow; must equal the default)")
    ap.add_argument("--until", help="last day evaluated, inclusive (default: today)")
    ap.add_argument("--targets", default=TARGETS)
    a = ap.parse_args(argv)
    rep = run(a.until, a.brute, a.targets)
    print(json.dumps(rep, ensure_ascii=False, indent=1) if a.json else _fmt(rep, a.markdown))
    return 1 if rep["failing_targets"] else 0


if __name__ == "__main__":
    sys.exit(main())
