"""The precompiled dataset (data/compiled.json in a wheel, see marina_rules/_precompiled.py).

It must load exactly what the YAML loaders load (same values, same types), be produced only through the validating
loaders, and never be used when it does not belong to the YAML beside it or to this loader code.
"""
import datetime as dt
import json
import os
import shutil
import warnings

import pytest

import marina_rules as mr
from marina_rules import _precompiled as pc

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PREFIXES = ("cn", "hk", "us")
CACHED = (mr.records, mr.scopes, mr.known_gaps, mr._tracking_entries, mr.dataset_digest, mr._compiled_for)


def _clear():
    for f in CACHED:
        f.cache_clear()


@pytest.fixture(autouse=True)
def _clear_after():
    yield
    _clear()


def _snapshot():
    return {"records": mr.records(), "scopes": {p: mr.scopes(p) for p in PREFIXES + ("samples", "nowhere")},
            "known_gaps": {p: mr.known_gaps(p) for p in PREFIXES + ("samples", "nowhere")},
            "tracking": mr._tracking_entries(), "registry": mr.tracking_registry(),
            "registry_by_prefix": {p: mr.tracking_registry(p) for p in PREFIXES}, "digest": mr.dataset_digest()}


@pytest.fixture(scope="module")
def from_yaml():
    """What the source checkout loads: the repository YAML, parsed (no precompiled file there)."""
    _clear()
    assert mr._compiled() is None and not os.path.exists(os.path.join(mr.DATA_DIR, pc.FILE))
    snap = _snapshot()
    _clear()
    return snap


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    """A copy of data/ with its precompiled file, as scripts/vendor_data.py lays it out in the package."""
    d = str(tmp_path_factory.mktemp("vendored") / "data")
    shutil.copytree(mr.DATA_DIR, d)
    with open(os.path.join(d, pc.FILE), "wb") as fh:
        fh.write(pc.build(d))
    return d


@pytest.fixture
def copy_of(built, tmp_path, monkeypatch):
    """A fresh copy of the built directory, installed as DATA_DIR."""
    d = str(tmp_path / "data")
    shutil.copytree(built, d)
    monkeypatch.setattr(mr, "DATA_DIR", d)
    _clear()
    return d


def _use(monkeypatch, d):
    monkeypatch.setattr(mr, "DATA_DIR", d)
    _clear()


# --- the comparison itself must be type-strict ----------------------------------------------------------------------

@pytest.mark.parametrize("a, b", [((1,), [1]), (1, 1.0), (True, 1), (dt.date(2024, 1, 2), "2024-01-02"),
                                  ({"a": 1, "b": 2}, {"b": 2, "a": 1}), (frozenset({1}), {1}), (None, ""),
                                  ({"x": (1, [2])}, {"x": (1, (2,))})])
def test_same_is_type_strict(a, b):
    assert not pc.same(a, b) and pc.same(a, a) and pc.same(b, b)


def test_codec_round_trips_types_json_cannot_express():
    tz = dt.timezone(dt.timedelta(hours=8))
    v = {"plain": [1, 2.5, -0.0, True, None, "中文", 10 ** 30], "tup": (1, (2, "x"), [3]), "fs": frozenset({"a", "b"}),
         1: "int key", (1, 2): "tuple key", "__t": "a key that looks like the tag", "d": dt.date(2024, 1, 2),
         "ts": dt.datetime(2024, 1, 2, 3, 4, 5, 6, tzinfo=tz), "nested": {"__t": {"__t": ("deep",)}}}
    back = json.loads(json.dumps(pc._enc(v), ensure_ascii=False), object_hook=pc._hook)
    assert pc.same(back, v)
    with pytest.raises(TypeError):
        pc._enc({"x": b"bytes"})


# --- installed layout: loads exactly what the YAML loads ------------------------------------------------------------

def test_precompiled_equals_yaml_field_by_field(from_yaml, built, monkeypatch):
    _use(monkeypatch, built)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        c = mr._compiled()
    assert c is not None
    got = _snapshot()
    assert got["records"] is c["records"]          # really served from the precompiled file
    assert len(got["records"]) == len(from_yaml["records"]) > 0
    for a, b in zip(got["records"], from_yaml["records"]):
        assert pc.same(a, b), a.id
    for key in ("scopes", "known_gaps", "tracking", "registry", "registry_by_prefix", "digest"):
        assert pc.same(got[key], from_yaml[key]), key
    # spot-check the types the comparison covered
    r = got["records"][0]
    assert type(r.effective_from) is str and type(r.sources) is tuple and all(type(s) is dict for s in r.sources)
    assert all(type(v["requires"]) is tuple for v in got["scopes"]["cn"].values())
    assert all(e["scopes"] is None or type(e["scopes"]) is frozenset for e in got["tracking"])
    assert all(e["scope_patterns"] is None or type(e["scope_patterns"]) is tuple for e in got["tracking"])


def test_queries_agree_through_the_precompiled_file(from_yaml, built, monkeypatch):
    _use(monkeypatch, built)
    assert mr._compiled() is not None
    assert mr.rule_at("stamp_duty_sell", "2023-08-28") == 0.0005
    assert mr.limit_price(10.00, "chinext", "2021-03-01") == (12.0, 8.0)
    assert mr.tracked_through("XSHG") is not None


def test_source_checkout_reads_yaml():
    assert mr.DATA_DIR == os.path.join(ROOT, "data")
    assert not os.path.exists(os.path.join(mr.DATA_DIR, pc.FILE))
    assert mr._compiled() is None


# --- refused when it does not belong to the YAML or to this code: warn, then load the YAML --------------------------

def _refused(match):
    with pytest.warns(RuntimeWarning, match=match):
        assert mr._compiled() is None


def test_edited_payload_is_refused_and_yaml_is_loaded(from_yaml, copy_of):
    p = os.path.join(copy_of, pc.FILE)
    raw = open(p, "rb").read()
    head, _, body = raw.partition(b"\n")
    i = body.index(b'"verified"')
    open(p, "wb").write(head + b"\n" + body[:i] + b'"unverified"' + body[i + len(b'"verified"'):])
    _refused("modified")
    _clear()
    with pytest.warns(RuntimeWarning):
        recs = mr.records()
    assert pc.same(recs, from_yaml["records"])


@pytest.mark.parametrize("rel", ["cn/equity_fees.yaml", "cn/tracking.yaml", "hk/scopes.yaml"])
def test_edited_yaml_is_refused(copy_of, rel):
    with open(os.path.join(copy_of, rel), "a", encoding="utf-8") as fh:
        fh.write("\n# edited after the build\n")
    _refused("YAML beside it differs")


def test_added_or_removed_yaml_is_refused(copy_of):
    shutil.copyfile(os.path.join(copy_of, "us", "known_gaps.yaml"), os.path.join(copy_of, "us", "extra.yaml"))
    _refused("YAML beside it differs")
    os.remove(os.path.join(copy_of, "us", "extra.yaml"))
    _clear()
    assert mr._compiled() is not None
    os.remove(os.path.join(copy_of, "us", "tracking.yaml"))
    _clear()
    _refused("YAML beside it differs")


def test_other_loader_code_is_refused(copy_of, monkeypatch):
    monkeypatch.setattr(pc, "loader_fingerprint", lambda: "0" * 64)
    _refused("different loader code")


def test_other_package_version_is_refused(copy_of, monkeypatch):
    monkeypatch.setattr(mr, "VERSION", "0.0.0")
    _refused("written by marina-rules")


@pytest.mark.parametrize("content", [b"", b"not json\n{}", b'{"format": "something-else"}\n{}'])
def test_unreadable_or_foreign_file_is_refused(copy_of, content):
    open(os.path.join(copy_of, pc.FILE), "wb").write(content)
    _refused("header|format")


def test_header_must_match_payload_count(copy_of):
    p = os.path.join(copy_of, pc.FILE)
    head, _, body = open(p, "rb").read().partition(b"\n")
    h = json.loads(head)
    h["records"] += 1
    open(p, "wb").write(json.dumps(h, sort_keys=True).encode() + b"\n" + body)
    _refused("record count")


# --- the checks run at build time: invalid data produces no file ----------------------------------------------------

_SRC = {"url": "https://example.org/x", "content_sha256": "0" * 64, "quote": "q"}


def _write_dataset(d, records, tracking=None):
    import yaml
    os.makedirs(os.path.join(d, "us"))
    with open(os.path.join(d, "us", "equity.yaml"), "w", encoding="utf-8") as fh:
        yaml.safe_dump({"schema": 1.1, "market": "XNYS+XNAS", "records": records}, fh)
    if tracking is not None:
        with open(os.path.join(d, "us", "tracking.yaml"), "w", encoding="utf-8") as fh:
            yaml.safe_dump({"schema": 1, "tracking": tracking}, fh)


def _rec(i, start, end=None, **kw):
    r = {"id": f"t.{i}", "scope": "us_stock", "rule": "some_rule", "value": 1, "effective_from": start,
         "verification": "single-source", "sources": [dict(_SRC)]}
    if end:
        r["effective_to"] = end
    r.update(kw)
    return r


def test_build_writes_a_valid_small_dataset(tmp_path):
    d = str(tmp_path / "data")
    _write_dataset(d, [_rec(1, "2020-01-01", "2021-01-01"), _rec(2, "2021-01-01")])
    raw = pc.build(d)
    assert json.loads(raw.partition(b"\n")[0])["records"] == 2


@pytest.mark.parametrize("records, match", [
    ([_rec(1, "2020-01-01"), _rec(2, "2021-01-01")], "overlapping records"),
    ([_rec(1, "2020-01-01"), _rec(1, "2019-01-01", "2019-06-01")], "duplicate id"),
    ([_rec(1, "2020-01-01", verification="maybe")], "verification must be one of"),
    ([_rec(1, "2020-01-01", sources=[{"url": "https://example.org/x", "quote": "q"}])], "content_sha256"),
    ([_rec(1, "2020-01-01", sources=[])], "requires at least one source"),
    ([_rec(1, "2020-01-01", "2019-01-01")], "effective_to must be after"),
])
def test_build_refuses_invalid_records(tmp_path, records, match):
    d = str(tmp_path / "data")
    _write_dataset(d, records)
    with pytest.raises(ValueError, match=match):
        pc.build(d)


def test_build_refuses_an_invalid_tracking_registry(tmp_path):
    d = str(tmp_path / "data")
    _write_dataset(d, [_rec(1, "2020-01-01")], tracking=[
        {"market": "XNYS+XNAS", "tracked_through": "2026-11-10", "basis": "x", "updated": "2026-11-01"}])
    with pytest.raises(ValueError, match="after updated"):
        pc.build(d)


# --- packaging declarations ------------------------------------------------------------------------------------------

def test_packaging_ships_and_ignores_the_precompiled_file():
    with open(os.path.join(ROOT, "pyproject.toml"), encoding="utf-8") as fh:
        assert '"data/compiled.json"' in fh.read()
    with open(os.path.join(ROOT, ".gitignore"), encoding="utf-8") as fh:
        assert "src/marina_rules/data/compiled.json" in fh.read().splitlines()
    with open(os.path.join(ROOT, "scripts", "vendor_data.py"), encoding="utf-8") as fh:
        assert "_precompiled.build(dst)" in fh.read()
