"""Marina is one implementation under test against conformance/vectors. A failing vector is a bug in Marina
until someone shows the vector's oracle (primary text / arithmetic) was misread — then fix the vector in the same PR."""
import glob, json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "conformance"))
from run import run  # noqa: E402


def test_all_vectors_agree():
    n, fails = run()
    assert n >= 80
    assert not fails, "\n".join(f"{f['id']}: expect {f['expect']} got {f['got']} | {f['oracle'][:100]}" for f in fails)


def test_every_vector_has_an_oracle_and_unique_id():
    seen = set()
    for p in glob.glob(os.path.join(os.path.dirname(__file__), "..", "conformance", "vectors", "*.json")):
        for v in json.load(open(p, encoding="utf-8")):
            assert v["id"] not in seen, f"duplicate id {v['id']}"; seen.add(v["id"])
            assert len(v["oracle"].strip()) >= 10, f"{v['id']}: oracle must cite a text or show the arithmetic"
            assert v["expect"], v["id"]
