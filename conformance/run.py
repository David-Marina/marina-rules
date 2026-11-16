"""Run the conformance vectors against this Marina. Usage: python conformance/run.py [--json]

Prints every disagreement. Exit 1 if any. Other implementations: read conformance/vectors/*.json and
produce the same comparisons; the vectors do not depend on this file.
"""
import glob, json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import marina_rules as mr
from marina_rules.contract import resolve

def run():
    fails = []; n = 0
    for p in sorted(glob.glob(os.path.join(os.path.dirname(__file__), "vectors", "*.json"))):
        for vec in json.load(open(p, encoding="utf-8")):
            n += 1; q = vec["query"]; e = vec["expect"]; got = {}
            try:
                if "prev_close" in q:
                    try:
                        kw = {"as_of": q["as_of"]} if "as_of" in q else {}
                        r = mr.limit_price(q["prev_close"], q["scope"], q["trade_date"], q.get("market"), **kw)
                        got = {"limit_up": None, "limit_down": None} if r is None else {"limit_up": r[0], "limit_down": r[1]}
                    except mr.NotYetPublished:
                        got = {"status": "NOT_YET_PUBLISHED"}
                    except mr.PublicationUnknown:
                        got = {"status": "UNKNOWN_PUBLICATION"}
                    except (KeyError, ValueError) as ex:
                        got = {"error": type(ex).__name__, "message": str(ex)[:120]}
                else:
                    kw = {"as_of": q["as_of"]} if "as_of" in q else {}
                    if q.get("require_tracked"): kw["require_tracked"] = True
                    d = resolve(q["rule"], q["trade_date"], q["scope"], q.get("market"), q.get("context"),
                                q.get("min_verification", "single-source"), **kw)
                    got = {"status": d["status"]}
                    if d["status"] == "DETERMINED": got["value"] = d["result"]["value"]
                    # Only the keys a vector expects are compared, so additive decision keys never break old vectors.
                    for k in ("missing_context", "known_gap_ids", "tracking", "warnings", "alternatives"):
                        if k in e: got[k] = d.get(k)
            except Exception as ex:
                got = {"error": type(ex).__name__, "message": str(ex)[:120]}
            if "error" in e:   # the call must be refused as bad input (the exception class of this implementation)
                ok = got.get("error") == e["error"]
            else:
                ok = all(got.get(k) == v for k, v in e.items()) and not got.get("error")
            if "missing_context" in e and ok:
                ok = set(got.get("missing_context", [])) == set(e["missing_context"])
            if not ok:
                fails.append({"id": vec["id"], "expect": e, "got": got, "oracle": vec["oracle"]})
    return n, fails

if __name__ == "__main__":
    n, fails = run()
    if "--json" in sys.argv:
        print(json.dumps({"vectors": n, "failures": fails, "citation": mr.citation()}, ensure_ascii=False, indent=1))
    else:
        for f in fails:
            print(f"FAIL {f['id']}\n   expect {f['expect']}\n   got    {f['got']}\n   oracle {f['oracle'][:140]}")
        print(f"{n} vectors, {len(fails)} failures — {mr.citation()}")
    sys.exit(1 if fails else 0)
