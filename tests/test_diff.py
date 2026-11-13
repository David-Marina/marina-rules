"""diff_rules semantics pinned with two synthetic versions in temp dirs, plus the real tag history."""
import os, textwrap
import pytest
from marina_rules.diff import diff_rules


def _write(tmp, name, body):
    d = os.path.join(tmp, name, "data", "cn"); os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "x.yaml"), "w", encoding="utf-8") as fh:
        fh.write(textwrap.dedent(body))
    return os.path.join(tmp, name)


OLD = """
schema: 1.1
market: XSHG+XSHE
records:
- {id: a.main.1996, scope: main_board, rule: price_limit_pct, value: 0.1, effective_from: 1996-12-16, verification: verified, sources: [{url: u1}]}
- {id: a.st.1998, scope: st_main, rule: price_limit_pct, value: 0.05, effective_from: 1998-04-27, verification: verified, sources: [{url: u2}]}
- {id: a.fee.2008, scope: stock, rule: stamp_duty_sell, value: 0.001, effective_from: 2008-09-19, verification: verified, sources: []}
- {id: a.fee.2023, scope: stock, rule: stamp_duty_sell, value: 0.0005, effective_from: 2023-08-28, verification: verified, sources: []}
- {id: a.ipo5.star, market: XSHG, scope: ipo_first5, rule: price_limit_pct, value: unlimited, effective_from: 2019-07-22, verification: verified, sources: []}
- {id: a.gone, scope: etf, rule: price_limit_pct, value: 0.1, effective_from: 2000-01-01, verification: verified, sources: []}
"""
NEW = """
schema: 1.1
market: XSHG+XSHE
records:
- {id: a.main.1996, scope: main_board, rule: price_limit_pct, value: 0.1, effective_from: 1996-12-16, verification: verified, sources: [{url: u1}, {url: u9}], notes: more}
- {id: a.st.1998b, scope: st_main, rule: price_limit_pct, value: 0.05, effective_from: 1998-04-22, effective_to: 2026-07-06, verification: verified, sources: [{url: u2}]}
- {id: a.st.2026, scope: st_main, rule: price_limit_pct, value: 0.10, effective_from: 2026-07-06, verification: verified, sources: [{url: u3}]}
- {id: a.fee.2008, scope: stock, rule: stamp_duty_sell, value: 0.001, effective_from: 2008-09-19, effective_to: 2023-08-28, verification: verified, sources: []}
- {id: a.fee.2023, scope: stock, rule: stamp_duty_sell, value: 0.0005, effective_from: 2023-08-28, verification: single-source, sources: []}
- {id: a.ipo5.star, market: XSHG, scope: ipo_first5_star, rule: price_limit_pct, value: unlimited, effective_from: 2019-07-22, verification: verified, sources: []}
- {id: a.cb.2022, scope: convertible, rule: price_limit_pct, value: 0.2, effective_from: 2022-08-01, verification: verified, sources: []}
"""


def test_every_kind_is_classified(tmp_path):
    d = diff_rules(_write(tmp_path, "old", OLD), _write(tmp_path, "new", NEW))
    by = {c["record_id"]: c for c in d["changes"]}
    assert by["a.main.1996"]["kind"] == "metadata"                       # sources + notes only
    assert by["a.st.1998b"]["kind"] == "correction" and by["a.st.1998b"]["old_id"] == "a.st.1998"   # dates moved
    assert by["a.st.2026"]["kind"] == "regime_change"                     # appended interval
    assert by["a.fee.2008"]["kind"] == "bookkeeping"                      # closed onto existing successor
    assert by["a.fee.2023"]["kind"] == "metadata" and by["a.fee.2023"]["verification_downgraded"] is True
    assert by["a.ipo5.star"]["kind"] == "rename"                          # scope-only rename
    assert by["a.cb.2022"]["kind"] == "coverage_added"
    assert by["a.gone"]["kind"] == "removed"
    keys = {tuple(r["key"]) for r in d["rerun_intervals"]}
    assert ("XSHG+XSHE", "st_main", "price_limit_pct") in keys
    assert ("XSHG+XSHE", "stock", "stamp_duty_sell") not in keys        # bookkeeping never forces a re-run
    assert d["from"]["dataset_sha256"] != d["to"]["dataset_sha256"]


def test_filters_and_identity(tmp_path):
    o = _write(tmp_path, "old", OLD)
    assert diff_rules(o, o)["changes"] == []
    d = diff_rules(o, _write(tmp_path, "new", NEW), rule="stamp_duty_sell")
    assert {c["key"][2] for c in d["changes"]} == {"stamp_duty_sell"}


def _git_ok():
    import subprocess
    return subprocess.run(["git", "rev-parse", "2026.10.24b"], capture_output=True).returncode == 0


@pytest.mark.skipif(not _git_ok(), reason="tags not available (shallow clone)")
def test_real_history_2026_10_24_to_24b_was_corrections_plus_one_regime_change():
    d = diff_rules("2026.10.24", "2026.10.24b")
    regime = [c for c in d["changes"] if c["kind"] == "regime_change"]
    assert [c["record_id"] for c in regime] == ["cn.limit.st_main.2026-07-06"]
    assert d["summary"]["correction"] >= 4 and d["summary"]["removed"] == 0


def test_prefix_scope_is_not_a_family_when_old_scope_still_exists(tmp_path):
    old = _write(tmp_path, "o", """
    schema: 1.1
    market: XSHG+XSHE
    records:
    - {id: e.etf, scope: etf, rule: price_limit_pct, value: 0.1, effective_from: 1996-12-16, verification: verified, sources: []}
    """)
    new = _write(tmp_path, "n", """
    schema: 1.1
    market: XSHG+XSHE
    records:
    - {id: e.etf, scope: etf, rule: price_limit_pct, value: 0.1, effective_from: 1996-12-16, verification: verified, sources: []}
    - {id: e.etf20, market: XSHG, scope: etf_20pct, rule: price_limit_pct, value: 0.2, effective_from: 2020-08-21, verification: verified, sources: []}
    """)
    d = diff_rules(old, new)
    assert {c["record_id"]: c["kind"] for c in d["changes"]} == {"e.etf20": "coverage_added"}
