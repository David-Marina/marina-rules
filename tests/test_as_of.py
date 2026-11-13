"""Bitemporal ``as_of``: answer only from rules officially published on or before ``as_of`` (docs/SCHEMA.md "as_of")."""
import datetime as dt
import json
import os
import subprocess
import sys

import pytest

import marina_rules as mr
from marina_rules.contract import STATUSES, capabilities, contract_schema, resolve

sys.path.insert(0, os.path.dirname(__file__))
from test_audit_fixes import _full_context, _validate  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ST = {"board": "main_board", "st_status": True}
ST10 = "cn.limit.st_main.2026-07-06"   # effective 2026-07-06, published 2026-04-24 (SSE/SZSE 2026-04-24 notices)
ST5 = "cn.limit.st_main.1998-04-22"    # published_at null


def _rec(rid):
    return next(r for r in mr.records() if r.id == rid)


def _dates():
    ds = {"2006-07-03", "2015-06-15", "2024-06-14", "2026-10-26"}
    for r in mr.records():
        ds.add(r.effective_from)
        if r.effective_to:
            ds.add(r.effective_to)
            ds.add((dt.date.fromisoformat(r.effective_to) - dt.timedelta(days=1)).isoformat())
    return sorted(ds)


def _outcome(fn, *a, **k):
    try:
        x = fn(*a, **k)
        return ("ok", x.id if isinstance(x, mr.Record) else x)
    except Exception as e:  # noqa: BLE001 — compare exception type and message
        return (type(e).__name__, str(e))


# --- as_of=None is exactly the old behaviour ---------------------------------------------------------------------

def test_as_of_none_is_unchanged_for_every_record_key_and_date_sample():
    keys = sorted({(r.rule, r.scope, r.market) for r in mr.records()})
    n = 0
    for rule, scope, market in keys:
        for d in _dates():
            for mk in (market, None):
                assert _outcome(mr.record_at, rule, d, scope, mk) == _outcome(mr.record_at, rule, d, scope, mk, as_of=None)
                assert _outcome(mr.rule_at, rule, d, scope, mk) == _outcome(mr.rule_at, rule, d, scope, mk, as_of=None)
                a = resolve(rule, d, scope, mk, _full_context(scope, None))
                b = resolve(rule, d, scope, mk, _full_context(scope, None), as_of=None)
                assert a == b and "as_of" not in a
                n += 1
    assert n > 10000


def test_as_of_none_coverage_and_limit_price_unchanged():
    for sc, mk in (("main_board", "XSHE"), ("st_main", "XSHG+XSHE"), ("chinext", "XSHE"), ("stock", "XSHG")):
        rules = ["price_limit_pct", "tick_size", "stamp_duty_sell", "limit_price_min_tick"]
        a = mr.coverage(mk, sc, rules, "2006-07-01", "2026-10-27")
        assert a == mr.coverage(mk, sc, rules, "2006-07-01", "2026-10-27", as_of=None)
        assert "publication_unknown" not in a and "as_of" not in a
    for args in ((10.0, "main_board", "2024-06-14", "XSHE"), (0.04, "delisting", "2015-06-01", "XSHG"),
                 (10.0, "st_main", "2026-07-06", "XSHG"), (3.0, "chinext", "2021-03-01", "XSHE")):
        assert mr.limit_price(*args) == mr.limit_price(*args, as_of=None)


# --- semantics ---------------------------------------------------------------------------------------------------

def test_not_yet_published_known_case():
    assert _rec(ST10).published_at == "2026-04-24"
    with pytest.raises(mr.NotYetPublished) as ei:
        mr.record_at("price_limit_pct", "2026-07-06", "st_main", "XSHG+XSHE", as_of="2026-04-23")
    assert ei.value.record.id == ST10 and ST10 in str(ei.value) and "2026-04-24" in str(ei.value)
    assert isinstance(ei.value, KeyError)
    with pytest.raises(mr.NotYetPublished):
        mr.rule_at("price_limit_pct", "2026-07-06", "st_main", "XSHG+XSHE", as_of="2026-04-23")
    d = resolve("price_limit_pct", "2026-07-06", "st_main", "XSHG+XSHE", ST, as_of="2026-04-23")
    assert d["status"] == "NOT_YET_PUBLISHED" and d["result"] is None and d["record_id"] == ST10
    assert d["as_of"] == "2026-04-23" and "2026-04-24" in d["reason"]
    d = resolve("price_limit_pct", "2026-07-06", "st_main", "XSHG+XSHE", ST, as_of="2026-04-24")
    assert d["status"] == "DETERMINED" and d["result"]["value"] == 0.1
    assert mr.rule_at("price_limit_pct", "2026-07-06", "st_main", "XSHG+XSHE", as_of="2026-04-24") == 0.1


def test_no_silent_fallback_to_predecessor():
    """Before publication the predecessor (5%, published_at null) must NOT answer for 2026-07-06."""
    with pytest.raises(mr.NotYetPublished):
        mr.limit_price(10.0, "st_main", "2026-07-06", "XSHG", as_of="2026-04-23")
    assert mr.limit_price(10.0, "st_main", "2026-07-06", "XSHG", as_of="2026-04-24") == (11.0, 9.0)


def test_publication_unknown():
    assert _rec(ST5).published_at is None
    with pytest.raises(mr.PublicationUnknown) as ei:
        mr.record_at("price_limit_pct", "2024-06-14", "st_main", "XSHG+XSHE", as_of="2026-10-26")
    assert ei.value.record.id == ST5 and ST5 in str(ei.value) and isinstance(ei.value, KeyError)
    assert not isinstance(ei.value, mr.NotYetPublished)
    with pytest.raises(mr.PublicationUnknown):
        mr.rule_at("price_limit_pct", "2024-06-14", "st_main", "XSHG+XSHE", as_of="2026-10-26")
    d = resolve("price_limit_pct", "2024-06-14", "st_main", "XSHG+XSHE", ST, as_of="2026-10-26")
    assert d["status"] == "UNKNOWN_PUBLICATION" and d["result"] is None and d["record_id"] == ST5
    assert "published_at" in d["reason"]


def test_forward_looking_and_announced_in_advance():
    # as_of before the trade date and before effective_from, after publication: fine
    assert mr.rule_at("price_limit_pct", "2020-09-01", "chinext", "XSHE", as_of="2020-06-12") == 0.2
    # nothing in force stays a plain KeyError (not a publication exception)
    with pytest.raises(KeyError) as ei:
        mr.record_at("price_limit_pct", "1990-01-01", "main_board", "XSHE", as_of="2026-01-01")
    assert type(ei.value) is KeyError


def _a_contract(r):
    """A contract the record covers on its first day (None for records without a selector)."""
    if r.contracts is None:
        return None
    prod = r.scope.split("_")[1]
    y, m = int(r.effective_from[:4]), int(r.effective_from[5:7])
    for k in range(37):
        idx = y * 12 + m - 1 + k
        code = f"{prod}{(idx // 12) % 100:02d}{idx % 12 + 1:02d}"
        if r.applies_to(code, r.effective_from):
            return code
    raise AssertionError(f"{r.id}: no contract within 36 months is covered")


def test_visibility_rule_over_every_record():
    for r in mr.records():
        for as_of in ("1990-01-01", r.published_at, "2099-12-31"):
            if as_of is None:
                continue
            got = _outcome(mr.record_at, r.rule, r.effective_from, r.scope, r.market, as_of=as_of, contract=_a_contract(r))
            if r.published_at is None:
                assert got[0] == "PublicationUnknown", (r.id, got)
            elif r.published_at <= as_of:
                assert got == ("ok", r.id), (r.id, as_of, got)
            else:
                assert got[0] == "NotYetPublished", (r.id, got)


def test_coverage_as_of():
    c = mr.coverage("XSHG+XSHE", "st_main", ["price_limit_pct"], "2026-01-01", "2026-08-01", as_of="2026-04-23")
    assert c["status"] == "partial" and c["as_of"] == "2026-04-23"
    assert c["publication_unknown"] == [{"rule": "price_limit_pct", "from": "2026-01-01", "to": "2026-07-06", "record_ids": [ST5]}]
    assert c["not_yet_published"] == [{"rule": "price_limit_pct", "from": "2026-07-06", "to": "2026-08-01", "record_ids": [ST10]}]
    c = mr.coverage("XSHG+XSHE", "st_main", ["price_limit_pct"], "2026-07-06", "2026-08-01", as_of="2026-04-24")
    assert c["status"] == "complete" and not c["publication_unknown"] and not c["not_yet_published"]
    c = mr.coverage("XSHG+XSHE", "stock", ["stamp_duty_sell"], "2023-08-01", "2023-09-01", as_of="2023-08-26")
    assert c["status"] == "partial" and c["not_yet_published"][0]["from"] == "2023-08-28"


@pytest.mark.parametrize("bad", ["2026/04/24", "2026-4-24", "2026-13-01", "20260424", 20260424, "2026-04-24T00:00", ""])
def test_bad_as_of_is_value_error(bad):
    for fn in (lambda: mr.record_at("stamp_duty_sell", "2024-01-02", as_of=bad),
               lambda: mr.rule_at("stamp_duty_sell", "2024-01-02", as_of=bad),
               lambda: mr.coverage("XSHG", "stock", ["stamp_duty_sell"], "2024-01-01", "2024-02-01", as_of=bad),
               lambda: resolve("stamp_duty_sell", "2024-01-02", "stock", "XSHG", {}, as_of=bad),
               lambda: mr.limit_price(10, "main_board", "2024-01-02", "XSHE", as_of=bad)):
        with pytest.raises(ValueError):
            fn()


# --- contract / JSON ----------------------------------------------------------------------------------------------

def test_new_statuses_in_schema_and_capabilities():
    for s in ("NOT_YET_PUBLISHED", "UNKNOWN_PUBLICATION"):
        assert s in STATUSES and s in contract_schema()["properties"]["status"]["enum"]
        assert s in capabilities()["entrypoints"]["statuses"]
    published = json.load(open(os.path.join(ROOT, "docs", "decision.schema.json"), encoding="utf-8"))
    assert published == contract_schema()


def test_new_status_outputs_are_json_and_validate_against_published_schema():
    schema = json.load(open(os.path.join(ROOT, "docs", "decision.schema.json"), encoding="utf-8"))
    seen = set()
    for r in mr.records():
        for as_of in ("1990-01-01", "2099-12-31"):
            d = resolve(r.rule, r.effective_from, r.scope, r.market, _full_context(r.scope, r), as_of=as_of)
            _validate(json.loads(json.dumps(d, ensure_ascii=False)), schema)
            seen.add(d["status"])
    assert {"NOT_YET_PUBLISHED", "UNKNOWN_PUBLICATION", "DETERMINED"} <= seen


def test_cli_as_of():
    env = dict(os.environ, PYTHONPATH=os.path.join(ROOT, "src"))
    p = subprocess.run([sys.executable, "-m", "marina_rules.contract", "price_limit_pct", "2026-07-06", "st_main", "XSHG+XSHE",
                        "--context", "board=main_board,st_status=true", "--as-of", "2026-04-23"],
                       capture_output=True, text=True, env=env, cwd=ROOT)
    assert p.returncode == 0, p.stderr
    d = json.loads(p.stdout)
    assert d["status"] == "NOT_YET_PUBLISHED" and d["as_of"] == "2026-04-23"
    p = subprocess.run([sys.executable, "-m", "marina_rules.contract", "price_limit_pct", "2026-07-06", "st_main",
                        "--as-of", "26-04-23"], capture_output=True, text=True, env=env, cwd=ROOT)
    assert p.returncode == 2
