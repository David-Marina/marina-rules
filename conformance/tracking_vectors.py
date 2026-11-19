"""Rewrite the dates of the tracking vectors (vectors/tracking.json) from data/<prefix>/tracking.yaml.

    python conformance/tracking_vectors.py            # rewrite the file
    python conformance/tracking_vectors.py --check    # exit 1 if the file is not what this script writes

The tracked-through dates move with every weekly data release. The vectors keep what they test - the last checked
day is within, the day after is a carry-forward, a closed record is never refused, an untracked market is refused on
request - and take the dates from the registry. Values (0.001, 0.0005) and statuses stay as written in the file: this
script changes ``query.trade_date``, ``expect.tracking`` and the first sentence of ``oracle`` only. Run it on every
data release; tests/test_conformance.py fails when it was forgotten.
"""
import datetime, json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import marina_rules as mr

PATH = os.path.join(os.path.dirname(__file__), "vectors", "tracking.json")
# id: (market whose tracked-through date the vector rests on, days after that date for the query; None = date as written)
PLAN = {
    "TRK-0001": ("XSGE", 0), "TRK-0002": ("XSGE", 7), "TRK-0003": ("XSGE", 7),
    "TRK-0004": ("XHKG", 1), "TRK-0005": ("XHKG", 0),
    "TRK-0006": ("XNYS+XNAS", None), "TRK-0007": ("XNYS+XNAS", None),
    "TRK-0011": ("XSHG+XSHE", -3), "TRK-0012": ("XSHG+XSHE", 7), "TRK-0013": ("XSHG+XSHE", 7),
}
MARK = " || "   # the generated first sentence of an oracle ends here; what follows is the vector's own reasoning


def build(vectors):
    reg = {e["market"]: dict(e, file=f"{pfx}/{mr.TRACKING_FILE}") for pfx in mr.TRACKING_PREFIXES
           for e in mr.tracking_registry(pfx)}
    out = []
    for v in vectors:
        v = json.loads(json.dumps(v))
        if v["id"] in PLAN:
            market, days = PLAN[v["id"]]
            e = reg[market]; tt = e["tracked_through"]
            if days is not None:
                v["query"]["trade_date"] = (datetime.date.fromisoformat(tt) + datetime.timedelta(days=days)).isoformat()
            day = v["query"]["trade_date"]
            if "tracking" in v["expect"]:
                v["expect"]["tracking"] = {"tracked_through": tt, "beyond": day > tt}
            tail = v["oracle"].split(MARK, 1)[1] if MARK in v["oracle"] else v["oracle"]
            where = "after it" if day > tt else "on or before it"
            v["oracle"] = (f"data/{e['file']}: {market} tracked_through {tt} ({' '.join(e['basis'].split())}) "
                           f"{day} is {where}.{MARK}{tail}")
            v["ruleset_version_min"] = mr.VERSION
        out.append(v)
    return out


def main():
    with open(PATH, encoding="utf-8") as fh:
        text = fh.read()
    new = json.dumps(build(json.loads(text)), ensure_ascii=False, indent=1) + "\n"
    if "--check" in sys.argv:
        if new != text:
            print("conformance/vectors/tracking.json is behind the tracking registry: run python conformance/tracking_vectors.py")
            return 1
        return 0
    with open(PATH, "w", encoding="utf-8") as fh:
        fh.write(new)
    print(f"wrote {PATH} for {mr.citation()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
