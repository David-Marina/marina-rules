"""Precompiled dataset: the loaders' output, saved as JSON so an installed package starts without parsing YAML.

Parsing data/**/*.yaml with PyYAML is most of the cost of the first ``records()`` call. ``scripts/vendor_data.py``
runs :func:`build` on the copy of data/ it writes into the marina-rules-data package and saves ``data/compiled.json``
next to the YAML. :func:`build` produces it by running the ordinary YAML loaders (``_records_from_yaml``,
``_scopes_from_yaml``, ``_gaps_from_yaml``, ``_tracking_from_yaml``), so every load-time check (schema, enums, sources,
overlaps, selectors, tracking registry) runs at build time and an invalid dataset produces no file. It then decodes what
it wrote and compares it with the loaders' output, types included, and refuses to write a file that does not round-trip.

The data and the code are separate packages that are upgraded separately, so the file cannot be tied to the exact code
that wrote it. It is tied to :data:`LOADER_REVISION` instead: a number that names the behaviour of the loaders and of
this module. **Whenever a change could make the loaders (or the codec below) return anything different for some
input — a value, a type, an order, an accepted or refused file — LOADER_REVISION must go up by one.**
``tests/test_precompiled.py`` pins a hash of the source of that code per revision and fails when the code changed and
the revision did not.

At run time :func:`load` accepts the file only if all of these hold, and raises :class:`Rejected` otherwise (the
package then warns and loads the YAML, which is always correct, only slower):

  * the header names this format and version;
  * ``loader_revision`` equals this code's :data:`LOADER_REVISION`, so a file written by loaders that behave
    differently is never used (a data package built by newer or older code than the installed one is read from YAML);
  * ``data_version`` equals the dataset's ``VERSION`` file beside it;
  * ``payload_sha256`` equals the hash of the payload bytes, so an edited payload is noticed. This is an integrity
    check, not a signature: whoever can rewrite the package can rewrite both;
  * ``source_sha256`` equals a hash recomputed now over every YAML file beside it (tracking registries included,
    unlike ``dataset_digest()``), so an edited, added or removed YAML file disables it.

File layout: one line of JSON header, a newline, then the JSON payload. Values that JSON cannot express directly
(tuples, frozensets, dates, mappings with non-string keys) are written as ``{"__t": <type>, "v": ...}``; a plain
JSON object never contains the key ``__t``.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os

# Bump by one whenever the output of the loaders or of this module could change (see the module docstring).
LOADER_REVISION = 1

FORMAT = "marina-rules-compiled"
FORMAT_VERSION = 2   # 2: the header names loader_revision and data_version (1 named the package version and code hash)
FILE = "compiled.json"
_TAG = "__t"


class Rejected(Exception):
    """The precompiled file must not be used (stale, edited, written by other code, or unreadable)."""


# ------------------------------------------------------------------------------------------------------------ hashes
def _yaml_files(data_dir: str) -> list:
    paths = [os.path.join(root, f) for root, _, files in os.walk(data_dir) for f in files if f.endswith((".yaml", ".yml"))]
    return sorted(paths, key=lambda p: os.path.relpath(p, data_dir).replace(os.sep, "/"))


def source_digest(data_dir: str) -> str:
    """SHA-256 over every YAML file under ``data_dir`` that a loader can read (tracking registries included)."""
    h = hashlib.sha256()
    for path in _yaml_files(data_dir):
        with open(path, "rb") as fh:
            data = fh.read()
        rel = os.path.relpath(path, data_dir).replace(os.sep, "/").encode()
        h.update(b"%d:%s%d:" % (len(rel), rel, len(data)))
        h.update(data)
    return h.hexdigest()


# ------------------------------------------------------------------------------------------------------------- codec
def _enc(x):
    t = type(x)
    if x is None or t is bool or t is int or t is float or t is str:
        return x
    if t is list:
        return [_enc(v) for v in x]
    if t is dict:
        if _TAG not in x and all(type(k) is str for k in x):
            return {k: _enc(v) for k, v in x.items()}
        return {_TAG: "dict", "v": [[_enc(k), _enc(v)] for k, v in x.items()]}
    if t is tuple:
        return {_TAG: "tuple", "v": [_enc(v) for v in x]}
    if t is frozenset:
        return {_TAG: "frozenset", "v": [_enc(v) for v in sorted(x, key=repr)]}
    if t is _dt.datetime:
        return {_TAG: "datetime", "v": x.isoformat()}
    if t is _dt.date:
        return {_TAG: "date", "v": x.isoformat()}
    raise TypeError(f"precompiled dataset: cannot store a value of type {t.__name__}: {x!r}")


def _hook(d: dict):
    t = d.get(_TAG)
    if t is None:
        return d
    v = d["v"]
    if t == "tuple":
        return tuple(v)
    if t == "frozenset":
        return frozenset(v)
    if t == "dict":
        return {k: x for k, x in v}
    if t == "date":
        return _dt.date.fromisoformat(v)
    if t == "datetime":
        return _dt.datetime.fromisoformat(v)
    raise Rejected(f"unknown value tag {t!r}")


def _file_out(rel: str) -> str:
    return rel.replace(os.sep, "/")


def _file_in(rel: str) -> str:
    return rel if os.sep == "/" else rel.replace("/", os.sep)


def same(a, b) -> bool:
    """Deep equality that also requires identical types at every level (and identical key order for mappings):
    ``(1,) != [1]``, ``1 != 1.0``, ``True != 1``, ``date != 'YYYY-MM-DD'``. NaN equals NaN."""
    if type(a) is not type(b):
        return False
    if isinstance(a, float):
        return a == b or (a != a and b != b)
    if isinstance(a, dict):
        return list(a) == list(b) and all(same(a[k], b[k]) for k in a)
    if isinstance(a, (list, tuple)):
        return len(a) == len(b) and all(same(x, y) for x, y in zip(a, b))
    if isinstance(a, (frozenset, set)):
        return a == b and same(sorted(a, key=repr), sorted(b, key=repr))
    fields = getattr(type(a), "__dataclass_fields__", None)
    if fields is not None:
        return all(same(getattr(a, f), getattr(b, f)) for f in fields)
    return a == b


def _data_version(data_dir: str) -> str:
    """The dataset's VERSION file (``YYYY.MM.DD[.N]``); raises ValueError if it is missing or malformed."""
    import marina_rules as mr
    path = os.path.join(data_dir, "VERSION")
    try:
        with open(path, encoding="ascii") as fh:
            v = fh.read().strip()
    except (OSError, UnicodeDecodeError) as e:
        raise ValueError(f"{path}: cannot read the dataset version ({e})") from None
    mr._version_key(v)   # raises ValueError for anything but YYYY.MM.DD[.N]
    return v


# ------------------------------------------------------------------------------------------------------------- build
def _load_all_from_yaml(data_dir: str) -> dict:
    """Everything the loaders produce for ``data_dir``, through the YAML loaders (which validate)."""
    import marina_rules as mr
    recs = mr._records_from_yaml(data_dir)
    prefixes = sorted(d for d in os.listdir(data_dir) if os.path.isdir(os.path.join(data_dir, d)))
    scopes = {p: mr._scopes_from_yaml(data_dir, p) for p in prefixes
              if os.path.exists(os.path.join(data_dir, p, "scopes.yaml"))}
    gaps = {p: mr._gaps_from_yaml(data_dir, p) for p in prefixes
            if os.path.exists(os.path.join(data_dir, p, "known_gaps.yaml"))}
    tracking = mr._tracking_from_yaml(data_dir, recs,
                                      lambda p: scopes[p] if p in scopes else mr._scopes_from_yaml(data_dir, p))
    return {"records": recs, "scopes": scopes, "known_gaps": gaps, "tracking": tracking}


def build(data_dir: str) -> bytes:
    """The precompiled file for ``data_dir``. Raises (ValueError from the loaders, RuntimeError from the self-check)
    rather than return a file that is not exactly what the YAML loaders produce."""
    import dataclasses
    import marina_rules as mr
    data_version = _data_version(data_dir)
    before = source_digest(data_dir)
    loaded = _load_all_from_yaml(data_dir)
    if source_digest(data_dir) != before:
        raise RuntimeError(f"{data_dir}: YAML changed while the precompiled dataset was being built")
    fields = [f.name for f in dataclasses.fields(mr.Record)]
    rows = []
    for r in loaded["records"]:
        row = [_enc(getattr(r, f)) for f in fields]
        row[fields.index("file")] = _file_out(r.file)
        rows.append(row)
    tracking = [dict(e, file=_file_out(e["file"])) for e in loaded["tracking"]]
    payload = {"records": {"fields": fields, "rows": rows},
               "scopes": {p: _enc(v) for p, v in loaded["scopes"].items()},
               "known_gaps": {p: _enc(v) for p, v in loaded["known_gaps"].items()},
               "tracking": [_enc(e) for e in tracking]}
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    header = {"format": FORMAT, "format_version": FORMAT_VERSION, "loader_revision": LOADER_REVISION,
              "data_version": data_version, "source_sha256": before, "records": len(rows),
              "payload_sha256": hashlib.sha256(body).hexdigest()}
    raw = json.dumps(header, sort_keys=True).encode("ascii") + b"\n" + body
    back = _decode(body, header)
    for key in ("records", "scopes", "known_gaps", "tracking"):
        if not same(back[key], loaded[key]):
            raise RuntimeError(f"precompiled dataset: '{key}' does not round-trip exactly; not writing it")
    return raw


# -------------------------------------------------------------------------------------------------------------- load
def _decode(body: bytes, header: dict) -> dict:
    import dataclasses
    import marina_rules as mr
    try:
        p = json.loads(body.decode("utf-8"), object_hook=_hook)
        fields = [f.name for f in dataclasses.fields(mr.Record)]
        if p["records"]["fields"] != fields:
            raise Rejected("record fields differ from this version's Record")
        fi = fields.index("file")
        recs = []
        for row in p["records"]["rows"]:
            row = list(row)
            row[fi] = _file_in(row[fi])
            recs.append(mr.Record(*row))
        if len(recs) != header.get("records"):
            raise Rejected("record count differs from the header")
        tracking = tuple(dict(e, file=_file_in(e["file"])) for e in p["tracking"])
        return {"records": tuple(recs), "scopes": dict(p["scopes"]), "known_gaps": dict(p["known_gaps"]),
                "tracking": tracking}
    except Rejected:
        raise
    except (ValueError, KeyError, TypeError, IndexError, AttributeError) as e:
        raise Rejected(f"unreadable payload ({type(e).__name__}: {e})") from None


def load(path: str, data_dir: str) -> dict:
    """The loaders' output stored in ``path``, after checking that it belongs to the YAML in ``data_dir`` and to this
    loader revision. Raises :class:`Rejected` (with the reason) otherwise."""
    try:
        with open(path, "rb") as fh:
            raw = fh.read()
    except OSError as e:
        raise Rejected(f"cannot read it: {e}") from None
    head, sep, body = raw.partition(b"\n")
    try:
        header = json.loads(head.decode("ascii")) if sep else None
    except ValueError:
        header = None
    if not isinstance(header, dict):
        raise Rejected("no readable header")
    if header.get("format") != FORMAT or header.get("format_version") != FORMAT_VERSION:
        raise Rejected(f"format {header.get('format')!r} v{header.get('format_version')!r} is not "
                       f"{FORMAT!r} v{FORMAT_VERSION}")
    if type(header.get("loader_revision")) is not int or header["loader_revision"] != LOADER_REVISION:
        raise Rejected(f"written by loader revision {header.get('loader_revision')!r}, this code is revision "
                       f"{LOADER_REVISION}")
    try:
        here = _data_version(data_dir)
    except ValueError as e:
        raise Rejected(str(e)) from None
    if header.get("data_version") != here:
        raise Rejected(f"written for dataset version {header.get('data_version')!r}, the VERSION beside it is {here!r}")
    if header.get("payload_sha256") != hashlib.sha256(body).hexdigest():
        raise Rejected("payload does not match its recorded hash (the file was modified)")
    if header.get("source_sha256") != source_digest(data_dir):
        raise Rejected("the YAML beside it differs from the YAML it was built from")
    return _decode(body, header)
