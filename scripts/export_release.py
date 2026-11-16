"""Write the release artefacts next to a tag: machine-readable dumps of the same bytes the wheel ships.

    python scripts/export_release.py dist/

Produces marina-rules-<version>.json (all records, scopes, known gaps, digest), .sqlite (same, queryable),
capabilities.json (China), capabilities-hk.json (Hong Kong) and capabilities-us.json (US equities),
decision.schema.json, conformance vectors, and SHA256SUMS. Nothing here is a second source of truth: every file
carries the dataset digest and can be regenerated from the YAML.
"""
import datetime, glob, hashlib, json, os, sqlite3, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
import marina_rules as mr
from marina_rules.contract import capabilities, contract_schema

def _json_default(o):
    if isinstance(o, (datetime.date, datetime.datetime)):
        return o.isoformat()
    if isinstance(o, (set, tuple)):
        return list(o)
    raise TypeError(type(o).__name__)


PREFIXES = ("cn", "hk", "us")   # data/<prefix>/ registries: scopes and known gaps of each market family


def main(out: str) -> int:
    os.makedirs(out, exist_ok=True)
    all_scopes = {k: v for pfx in PREFIXES for k, v in mr.scopes(pfx).items()}
    all_gaps = [g for pfx in PREFIXES for g in mr.known_gaps(pfx)]
    ver, dg = mr.VERSION, mr.dataset_digest()
    recs = [{**{k: getattr(r, k) for k in ("id", "market", "scope", "rule", "value", "effective_from", "effective_to",
                                            "published_at", "recorded_at", "verification", "notes", "file", "unit", "contracts")},
             "sources": list(r.sources)} for r in mr.records()]
    dump = {"ruleset_version": ver, "dataset_sha256": dg, "citation": mr.citation(short=False),
            "records": recs, "scopes": all_scopes, "known_gaps": all_gaps,
            "tracking": mr.tracking_registry()}   # not part of dataset_sha256 (docs/SCHEMA.md, Tracking registry)
    files = {}
    p = os.path.join(out, f"marina-rules-{ver}.json")
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(dump, fh, ensure_ascii=False, indent=1, default=_json_default)
    files[p] = 1
    # sqlite
    p = os.path.join(out, f"marina-rules-{ver}.sqlite")
    if os.path.exists(p): os.remove(p)
    con = sqlite3.connect(p); c = con.cursor()
    c.execute("create table meta(key text primary key, value text)")
    c.executemany("insert into meta values(?,?)", [("ruleset_version", ver), ("dataset_sha256", dg), ("citation", dump["citation"])])
    c.execute("""create table records(id text primary key, market text, scope text, rule text, value_json text,
                 effective_from text, effective_to text, published_at text, recorded_at text, verification text, unit text, notes text, file text,
                 contracts_json text)""")
    c.executemany("insert into records values(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                  [(r["id"], r["market"], r["scope"], r["rule"], json.dumps(r["value"]), r["effective_from"], r["effective_to"],
                    r["published_at"], r["recorded_at"], r["verification"], r["unit"], r["notes"], r["file"],
                    None if r["contracts"] is None else json.dumps(r["contracts"])) for r in recs])
    c.execute("create table sources(record_id text, url text, publisher text, title text, date text, kind text, quote text, content_sha256 text, hash_kind text)")
    c.executemany("insert into sources values(?,?,?,?,?,?,?,?,?)",
                  [(r["id"], s.get("url"), s.get("publisher"), s.get("title"), str(s.get("date")), s.get("kind"), s.get("quote"), s.get("content_sha256"), s.get("hash_kind"))
                   for r in recs for s in r["sources"]])
    c.execute("create table scopes(scope text primary key, description text, requires_json text, excludes_json text)")
    c.executemany("insert into scopes values(?,?,?,?)", [(k, v["description"], json.dumps(list(v["requires"])), json.dumps(list(v["excludes"]))) for k, v in all_scopes.items()])
    c.execute("create table known_gaps(gap_id text primary key, market text, scope text, rule text, from_date text, to_date text, severity text, status text, reason text, contracts_json text)")
    c.executemany("insert into known_gaps values(?,?,?,?,?,?,?,?,?,?)", [(g["gap_id"], g["market"], g["scope"], g["rule"], g["interval"]["from"], g["interval"]["to"], g["severity"], g["status"], g["reason"], None if g.get("contracts") is None else json.dumps(g["contracts"])) for g in all_gaps])
    c.execute("create table tracking(market text, scopes_json text, tracked_through text, basis text, updated text)")
    c.executemany("insert into tracking values(?,?,?,?,?)", [(t["market"], None if t["scopes"] is None else json.dumps(t["scopes"]), t["tracked_through"], t["basis"], t["updated"]) for t in dump["tracking"]])
    con.commit(); con.close(); files[p] = 1
    for name, obj in (("capabilities.json", capabilities()), ("capabilities-hk.json", capabilities("hk")),
                      ("capabilities-us.json", capabilities("us")),
                      ("decision.schema.json", contract_schema())):
        p = os.path.join(out, name)
        with open(p, "w", encoding="utf-8") as fh: json.dump(obj, fh, ensure_ascii=False, indent=1, default=_json_default)
        files[p] = 1
    root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
    vecs = []
    for vp in sorted(glob.glob(os.path.join(root, "conformance", "vectors", "*.json"))):
        vecs += json.load(open(vp, encoding="utf-8"))
    p = os.path.join(out, f"conformance-vectors-{ver}.json")
    with open(p, "w", encoding="utf-8") as fh: json.dump({"ruleset_version": ver, "dataset_sha256": dg, "vectors": vecs}, fh, ensure_ascii=False, indent=1, default=_json_default)
    files[p] = 1
    with open(os.path.join(out, "SHA256SUMS"), "w") as fh:
        for p in sorted(files):
            fh.write(f"{hashlib.sha256(open(p, 'rb').read()).hexdigest()}  {os.path.basename(p)}\n")
    print(f"{len(files)} files + SHA256SUMS in {out}  (dataset {dg[:16]})")
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "dist"))
