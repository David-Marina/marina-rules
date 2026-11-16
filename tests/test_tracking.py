"""Tracking registry (data/<prefix>/tracking.yaml): how far the official sources were checked for rule changes.

Outside the dataset digest; additive on every API; opt-in refusal of carry-forwards (docs/SCHEMA.md "Tracking registry").
"""
import importlib.util
import json
import os
import shutil

import pytest

import marina_rules as mr
from marina_rules import check as chk
from marina_rules.contract import (STATUSES, WARNING_BEYOND, WARNING_UNTRACKED, capabilities, contract_schema, main,
                                   resolve)

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PINNED_DIGEST = "80188ec249ce22ae0b4fd74f5acd8f420ac280846a5cf081dd6dcf091f102536"
TRACKING_FILES = [os.path.join(mr.DATA_DIR, p, mr.TRACKING_FILE) for p in mr.TRACKING_PREFIXES]


def _entry(market, tt, scopes=None, updated="2026-11-14"):
    return {"market": market, "markets": tuple(market.split("+")), "scopes": None if scopes is None else frozenset(scopes),
            "scope_patterns": None if scopes is None else tuple(scopes), "tracked_through": tt, "basis": "test",
            "updated": updated, "file": "cn/tracking.yaml"}


@pytest.fixture
def registry(monkeypatch):
    """Replace the registry with the given entries for one test."""
    def use(*entries):
        mr._check_tracking_overlaps(list(entries))
        monkeypatch.setattr(mr, "_tracking_entries", lambda: tuple(entries))
    return use


# --- digest -------------------------------------------------------------------------------------------------------

def test_digest_is_pinned_and_ignores_tracking_files(tmp_path):
    assert all(os.path.exists(p) for p in TRACKING_FILES)
    assert mr.dataset_digest() == PINNED_DIGEST
    d = tmp_path / "data"
    shutil.copytree(mr.DATA_DIR, d)
    assert mr._digest_dir(str(d)) == PINNED_DIGEST                  # with tracking files
    p = d / "cn" / mr.TRACKING_FILE
    p.write_text(p.read_text(encoding="utf-8").replace("2026-11-02", "2026-11-09"), encoding="utf-8")
    assert mr._digest_dir(str(d)) == PINNED_DIGEST                  # tracking date moved forward
    for pfx in mr.TRACKING_PREFIXES:
        os.remove(d / pfx / mr.TRACKING_FILE)
    assert mr._digest_dir(str(d)) == PINNED_DIGEST                  # without them
    assert not any(f.endswith(mr.TRACKING_FILE) for f in mr._iter_files())


def test_diff_digest_ignores_tracking_files():
    from marina_rules.diff import load_version
    v = load_version(mr.DATA_DIR)
    assert v["digest"] == PINNED_DIGEST
    assert not any(r["file"].endswith(mr.TRACKING_FILE) for r in v["records"].values())


# --- registry loading and validation ------------------------------------------------------------------------------

def test_registry_contents():
    reg = {e["market"]: e for e in mr.tracking_registry()}
    assert set(reg) == {"XSHG+XSHE", "XSGE", "XINE", "XZCE", "GFEX", "XHKG", "XNYS+XNAS"}
    assert mr.tracked_through("XSHG") == mr.tracked_through("XSHE") == mr.tracked_through("XSHG+XSHE") == "2026-11-13"
    assert all(e["tracked_through"] <= e["updated"] for e in reg.values())
    assert {e["market"] for e in mr.tracking_registry("hk")} == {"XHKG"}
    for m in ("BJSE", "CCFX", "XSHG+XSHE+BJSE"):  # not on the watch list: untracked, never defaulted
        assert mr.tracked_through(m) is None


def _write(tmp_path, body):
    p = tmp_path / "tracking.yaml"
    p.write_text(body, encoding="utf-8")
    return str(p)


GOOD = "schema: 1\ntracking:\n- market: XSGE\n  tracked_through: '2026-11-02'\n  basis: daily files\n  updated: '2026-11-14'\n"


@pytest.mark.parametrize("old,new,msg", [
    ("'2026-11-02'", "'2026-11-31'", "need a date"),
    ("'2026-11-02'", "'2026-11-20'", "after updated"),
    ("XSGE", "XXXX", "has no record"),
    ("  basis: daily files\n", "", "needs market"),
    ("  basis: daily files\n", "  basis: daily files\n  note: x\n", "no other key"),
    ("  basis: daily files\n", "  basis: daily files\n  scopes: [shfe_zz]\n", "not in data/cn/scopes.yaml"),
    ("  basis: daily files\n", "  basis: daily files\n  scopes: [nothing_*]\n", "not in data/cn/scopes.yaml"),
    ("schema: 1\n", "schema: 2\n", "schema"),
])
def test_bad_registry_refuses_to_load(tmp_path, old, new, msg):
    known = frozenset({"XSGE"})
    assert mr._load_tracking(_write(tmp_path, GOOD), "cn", known)[0]["tracked_through"] == "2026-11-02"
    with pytest.raises(ValueError, match=msg):
        mr._load_tracking(_write(tmp_path, GOOD.replace(old, new)), "cn", known)


def test_scope_patterns_expand_against_the_registry(tmp_path):
    body = GOOD.replace("  basis: daily files\n", "  basis: daily files\n  scopes: [shfe_a*, shfe_cu]\n")
    e = mr._load_tracking(_write(tmp_path, body), "cn", frozenset({"XSGE"}))[0]
    assert e["scopes"] == {"shfe_al", "shfe_ao", "shfe_au", "shfe_ag", "shfe_ad", "shfe_cu"}


def test_overlapping_entries_are_refused():
    with pytest.raises(ValueError, match="both cover"):
        mr._check_tracking_overlaps([_entry("XSGE", "2026-11-02"), _entry("XSGE", "2026-11-01", ["shfe_cu"])])
    with pytest.raises(ValueError, match="both cover"):
        mr._check_tracking_overlaps([_entry("XNYS+XNAS", "2026-11-03"), _entry("XNAS", "2026-11-03")])
    with pytest.raises(ValueError, match="both cover"):
        mr._check_tracking_overlaps([_entry("CCFX", "2026-11-02", ["cffex_if", "cffex_t"]),
                                     _entry("CCFX", "2026-11-01", ["cffex_t"])])
    mr._check_tracking_overlaps([_entry("CCFX", "2026-11-02", ["cffex_if"]), _entry("CCFX", "2026-10-01", ["cffex_t"])])


# --- tracked_through ----------------------------------------------------------------------------------------------

def test_tracked_through_lookup():
    assert mr.tracked_through("XSGE") == mr.tracked_through("XSGE", "shfe_cu") == "2026-11-02"
    assert mr.tracked_through("XNYS") == mr.tracked_through("XNAS", "us_etf") == "2026-11-03"
    assert mr.tracked_through("XNYS+XNAS") == "2026-11-03"
    assert mr.tracked_through("XNYS+XSGE") == "2026-11-02"         # earliest member
    assert mr.tracked_through("XSHG+XSGE") == "2026-11-02"
    assert mr.tracked_through("BJSE+XSGE") is None                 # one member untracked
    assert mr.tracked_through(None) is None
    assert mr.tracking_state("XSGE", "shfe_cu", "2026-11-03") == {"tracked_through": "2026-11-02", "beyond": True}
    assert mr.tracking_state("XSGE", "shfe_cu", "2026-11-02") == {"tracked_through": "2026-11-02", "beyond": False}
    assert mr.tracking_state("BJSE", "stock", "2026-11-02") == {"tracked_through": None, "beyond": None}


def test_scope_families(registry):
    index = ["cffex_if", "cffex_ih", "cffex_ic", "cffex_im", "cffex_index_futures"]
    registry(_entry("CCFX", "2026-11-05", index))
    assert mr.tracked_through("CCFX", "cffex_if") == "2026-11-05"
    assert mr.tracked_through("CCFX", "cffex_t") is None           # treasury futures not covered
    assert mr.tracked_through("CCFX") is None                      # not every CCFX scope is covered
    registry(_entry("CCFX", "2026-11-05", index), _entry("CCFX", "2026-10-30", ["cffex_tf", "cffex_t", "cffex_ts", "cffex_tl"]))
    assert mr.tracked_through("CCFX", "cffex_t") == "2026-10-30"
    assert mr.tracked_through("CCFX") == "2026-10-30"              # every scope covered: the earliest


# --- resolve --------------------------------------------------------------------------------------------------------

def _schema_ok(d):
    sch = contract_schema()
    assert set(d) <= set(sch["properties"]) and set(sch["required"]) <= set(d)
    assert d["status"] in sch["properties"]["status"]["enum"]
    assert set(d["tracking"]) == {"tracked_through", "beyond"}
    assert all(w in sch["properties"]["warnings"]["items"]["enum"] for w in d["warnings"])
    json.dumps(d)
    return d


def test_resolve_within_beyond_closed_untracked():
    d = _schema_ok(resolve("session_schedule", "2026-11-02", "shfe_cu", "XSGE"))
    assert d["status"] == "DETERMINED" and d["tracking"] == {"tracked_through": "2026-11-02", "beyond": False}
    assert d["warnings"] == []
    d = _schema_ok(resolve("session_schedule", "2026-11-03", "shfe_cu", "XSGE"))
    assert d["status"] == "DETERMINED" and d["result"] is not None and d["warnings"] == [WARNING_BEYOND]
    d = _schema_ok(resolve("finra_taf_sell", "2026-12-01", "us_stock", "XNYS+XNAS"))
    assert d["tracking"]["beyond"] is True and d["result"]["effective_to"] == "2027-01-01" and d["warnings"] == []
    d = _schema_ok(resolve("margin_ratio", "2026-11-10", "cffex_if", "CCFX"))
    assert d["tracking"] == {"tracked_through": None, "beyond": None} and d["warnings"] == [WARNING_UNTRACKED]


def test_a_share_tracking_and_the_mixed_market_record():
    """cn.fee.stamp_duty_sell.2023-08-28 is XSHG+XSHE+BJSE and open-ended; XSHG / XSHE are tracked, BJSE is not."""
    d = _schema_ok(resolve("stamp_duty_sell", "2026-11-10", "stock", "XSHE"))
    assert d["tracking"] == {"tracked_through": "2026-11-13", "beyond": False} and d["warnings"] == []
    assert resolve("stamp_duty_sell", "2026-11-10", "stock", "XSHE", require_tracked=True)["status"] == "DETERMINED"
    d = _schema_ok(resolve("stamp_duty_sell", "2026-11-20", "stock", "XSHG"))
    assert d["tracking"]["beyond"] is True and d["warnings"] == [WARNING_BEYOND]
    assert resolve("stamp_duty_sell", "2026-11-20", "stock", "XSHG", require_tracked=True)["status"] == "BEYOND_TRACKING"
    d = _schema_ok(resolve("stamp_duty_sell", "2026-11-10", "stock", "BJSE"))
    assert d["tracking"] == {"tracked_through": None, "beyond": None} and d["warnings"] == [WARNING_UNTRACKED]
    d = _schema_ok(resolve("stamp_duty_sell", "2026-11-10", "stock"))            # no market: the record's market,
    assert d["tracking"]["tracked_through"] is None and d["warnings"] == [WARNING_UNTRACKED]   # which includes BJSE
    d = _schema_ok(resolve("stamp_duty_sell", "2026-11-04", "hk_stock", "XHKG"))
    assert d["warnings"] == [WARNING_BEYOND] and d["result"]["value"] == 0.001


def test_non_determined_statuses_carry_tracking_but_no_warning():
    d = _schema_ok(resolve("price_limit_pct", "2026-11-20", "main_board", "XSHE"))
    assert d["status"] == "MISSING_CONTEXT" and d["warnings"] == [] and d["tracking"]["beyond"] is True
    d = _schema_ok(resolve("margin_ratio", "2026-11-20", "shfe_xx", "XSGE"))
    assert d["status"] == "OUT_OF_COVERAGE" and d["tracking"]["beyond"] is True and d["warnings"] == []


def test_require_tracked_refuses_only_carry_forwards():
    d = _schema_ok(resolve("session_schedule", "2026-11-03", "shfe_cu", "XSGE", require_tracked=True))
    assert d["status"] == "BEYOND_TRACKING" and d["result"] is None
    assert d["record_id"] == "cn.futures.session_schedule.shfe_cu.2024-01-01" and d["evidence_refs"]
    assert "2026-11-02" in d["reason"] and d["warnings"] == [WARNING_BEYOND]
    d = _schema_ok(resolve("stamp_duty_sell", "2026-11-10", "stock", "BJSE", require_tracked=True))
    assert d["status"] == "BEYOND_TRACKING" and "not tracked" in d["reason"]
    for q in (("session_schedule", "2026-11-02", "shfe_cu", "XSGE"), ("finra_taf_sell", "2026-12-01", "us_stock", "XNYS+XNAS"),
              ("stamp_duty_sell", "2022-01-04", "stock", "BJSE")):
        assert resolve(*q, require_tracked=True) == resolve(*q)


def test_default_resolve_answers_are_unchanged_except_additive_keys():
    """Without require_tracked the status, result and every pre-existing key are exactly as before."""
    from marina_rules.contract import _resolve
    n = 0
    for r in mr.records()[::7]:
        for d in (r.effective_from, "2026-11-03", "2026-12-15"):
            a = resolve(r.rule, d, r.scope, r.market)
            b = _resolve(r.rule, d, r.scope, r.market, None, "single-source", None, None)
            assert {k: v for k, v in a.items() if k not in ("tracking", "warnings")} == \
                   {k: v for k, v in b.items() if k not in ("tracking", "warnings")}
            assert a["status"] != "BEYOND_TRACKING"
            n += 1
    assert n > 1000


def test_schema_and_capabilities():
    sch = contract_schema()
    assert "BEYOND_TRACKING" in STATUSES and "BEYOND_TRACKING" in sch["properties"]["status"]["enum"]
    assert "tracking" not in sch["required"] and "warnings" not in sch["required"]
    with open(os.path.join(ROOT, "docs", "decision.schema.json"), encoding="utf-8") as fh:
        assert json.load(fh) == json.loads(json.dumps(sch))
    for pfx, markets in (("cn", {"XSHG+XSHE", "XSGE", "XINE", "XZCE", "GFEX"}), ("hk", {"XHKG"}), ("us", {"XNYS+XNAS"})):
        c = capabilities(pfx)
        assert {e["market"] for e in c["tracking"]["entries"]} == markets
        assert "BEYOND_TRACKING" in c["entrypoints"]["statuses"]
    assert capabilities()["tracking"]["untracked_markets"] == ["BJSE", "CCFX"]
    assert capabilities("us")["tracking"]["untracked_markets"] == []


def test_cli_require_tracked(capsys):
    assert main(["session_schedule", "2026-11-03", "shfe_cu", "XSGE", "--require-tracked"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "BEYOND_TRACKING"
    assert main(["session_schedule", "2026-11-03", "shfe_cu", "XSGE"]) == 0
    assert json.loads(capsys.readouterr().out)["warnings"] == [WARNING_BEYOND]


# --- record_at / rule_at --------------------------------------------------------------------------------------------

def test_record_at_opt_in_raises_beyond_tracking():
    assert mr.rule_at("session_schedule", "2026-11-20", "shfe_cu", "XSGE") == \
        mr.rule_at("session_schedule", "2026-11-20", "shfe_cu", "XSGE", require_tracked=False)
    with pytest.raises(mr.BeyondTracking) as ei:
        mr.rule_at("session_schedule", "2026-11-20", "shfe_cu", "XSGE", require_tracked=True)
    assert isinstance(ei.value, KeyError) and ei.value.tracked_through == "2026-11-02"
    assert ei.value.record.id == "cn.futures.session_schedule.shfe_cu.2024-01-01" and ei.value.date == "2026-11-20"
    with pytest.raises(KeyError):
        mr.record_at("stamp_duty_sell", "2026-11-10", "stock", "BJSE", require_tracked=True)
    assert mr.rule_at("stamp_duty_sell", "2026-11-10", "stock", "XSHE", require_tracked=True) == 0.0005
    assert mr.rule_at("session_schedule", "2026-11-02", "shfe_cu", "XSGE", require_tracked=True)
    assert mr.rule_at("stamp_duty_sell", "2022-01-04", "stock", "BJSE", require_tracked=True) == 0.001   # closed record
    assert mr.record_at("finra_taf_sell", "2026-12-01", "us_stock", "XNYS+XNAS", require_tracked=True).effective_to


# --- coverage -------------------------------------------------------------------------------------------------------

def test_coverage_reports_tracking_without_changing_status():
    a = mr.coverage("XSGE", "shfe_cu", ["session_schedule"], "2026-10-01", "2026-12-01")
    assert a["status"] == "complete"
    assert a["tracking"] == {"tracked_through": "2026-11-02", "beyond": {"from": "2026-11-03", "to": "2026-12-01"}}
    assert a["beyond_tracking"] == [{"rule": "session_schedule", "from": "2026-11-03", "to": "2026-12-01",
                                     "record_ids": ["cn.futures.session_schedule.shfe_cu.2024-01-01"]}]
    b = mr.coverage("XSGE", "shfe_cu", ["session_schedule"], "2026-10-01", "2026-12-01", require_tracked=True)
    assert b["status"] == "partial" and b["beyond_tracking"] == a["beyond_tracking"]
    c = mr.coverage("XSGE", "shfe_cu", ["session_schedule"], "2026-10-01", "2026-11-03", require_tracked=True)
    assert c["status"] == "complete" and c["tracking"]["beyond"] is None and c["beyond_tracking"] == []
    u = mr.coverage("BJSE", "stock", ["stamp_duty_sell"], "2022-01-01", "2026-12-01")
    assert u["status"] == "complete" and u["tracking"] == {"tracked_through": None, "beyond": None}
    assert u["beyond_tracking"] == [{"rule": "stamp_duty_sell", "from": "2023-08-28", "to": "2026-12-01",
                                     "record_ids": ["cn.fee.stamp_duty_sell.2023-08-28"]}]   # closed records are facts
    t = mr.coverage("XNYS+XNAS", "us_stock", ["finra_taf_sell"], "2026-10-01", "2026-12-31", require_tracked=True)
    assert t["status"] == "complete" and t["beyond_tracking"] == []                           # closed fee holiday


# --- marina-check ----------------------------------------------------------------------------------------------------

HDR = ["date", "code", "side", "price", "prev_close", "scope", "market"]


def _rows(*lines):
    return [dict(zip(HDR, ln.split(","))) for ln in lines]


def test_check_counts_rows_beyond_tracking_without_touching_the_stamp(registry):
    rows = _rows("2026-11-13,000001,buy,10.00,10.00,main_board,XSHE", "2026-11-20,000001,buy,10.00,10.00,main_board,XSHE",
                 "2026-11-20,600000,buy,10.00,10.00,main_board,", "2026-11-05,600000,buy,10.00,10.00,main_board,XSHG")
    for r in rows:
        r.update(board="main_board", st="false", listing_day_index="1000")
        r["scope"] = ""
    plain = chk.check_rows(rows, strict=True)
    # a row without a market has no tracking statement (BJSE is untracked, and the checker never picks an exchange)
    assert plain["tracking"]["rows_beyond_tracked_through"] == 1 and plain["tracking"]["rows_untracked"] == 1
    assert plain["tracking"]["tracked_through"] == {"": None, "XSHE": "2026-11-13", "XSHG": "2026-11-13"}
    registry(_entry("XSHE", "2026-11-02"))
    tracked = chk.check_rows(rows, strict=True)
    # registry replaced by XSHE through 2026-11-02 only: both XSHE rows beyond; XSHG and the market-less row untracked
    assert tracked["tracking"]["rows_beyond_tracked_through"] == 2 and tracked["tracking"]["rows_untracked"] == 2
    assert tracked["stamp"] == plain["stamp"] and tracked["findings"] == plain["findings"] == []


def test_check_example_stamp_unchanged():
    import csv
    with open(os.path.join(ROOT, "examples", "fills_ok.csv"), newline="", encoding="utf-8") as fh:
        out = chk.check_rows(list(csv.DictReader(fh)), strict=True)
    assert out["stamp"].endswith("87ff86b08134065c107cbb5368058de5")
    # every example row has a market (XSHG / XSHE, tracked) and a date before 2026-11-13
    assert out["tracking"]["rows_untracked"] == out["tracking"]["rows_beyond_tracked_through"] == 0
    assert out["tracking"]["tracked_through"] == {"XSHE": "2026-11-13", "XSHG": "2026-11-13"}


# --- release guard ----------------------------------------------------------------------------------------------------

def _guard():
    spec = importlib.util.spec_from_file_location("crm", os.path.join(ROOT, "scripts", "check_release_metadata.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_release_guard_tracking_dates():
    g = _guard()
    entries = [{"market": "XSGE", "scopes": None, "tracked_through": "2026-11-02", "updated": "2026-11-14"}]
    errs, lines = g.check_tracking(entries, today="2026-11-14")
    assert errs == [] and "12 days before 2026-11-14" in lines[0]
    errs, _ = g.check_tracking(entries, today="2026-11-13")
    assert errs == ["tracking XSGE: updated 2026-11-14 is in the future (today 2026-11-13)"]
    errs, lines = g.check_tracking(entries, today="2026-12-01", release="2026-11-13")
    assert errs == ["tracking XSGE: updated 2026-11-14 is after the release date 2026-11-13"]
    old = [{"market": "XSGE", "scopes": ["shfe_cu"], "tracked_through": "2020-01-01", "updated": "2020-01-02"}]
    errs, lines = g.check_tracking(old, today="2026-11-14", release="2026-11-14")
    assert errs == [] and lines[0].startswith("tracking XSGE shfe_cu: tracked through 2020-01-01")   # stale is not an error
    assert g.release_date(ROOT, "2026.11.13") == "2026-11-13" and g.release_date(ROOT, "1999.01.01") is None
    errs, _ = g.check_tracking(mr.tracking_registry(), today="2026-11-14")
    assert errs == []
