"""Schema 1.2 contract selectors: parsing, matching, load-time disjointness, lookup, coverage and resolve."""
import textwrap

import pytest

import marina_rules as mr
from marina_rules.contract import resolve

SCOPES = """\
schema: 1.1
market: XSGE
scopes:
  shfe_au:
    description: test gold
    requires: []
  czce_sr:
    description: test sugar
    requires: []
  cffex_index_futures:
    description: umbrella
    requires: []
"""

# Gold-like tiers: until 2025-05-16 one product-wide value; then near-3 + Jun/Dec at 20, the rest at 10, except a
# named-contract close-today fee for au2506 and a gap for every other contract.
RECORDS = """\
schema: 1.2
market: XSGE
records:
- {id: t.fee.shfe_au.2024-01-01, scope: shfe_au, rule: trans_fee_per_lot, value: 2, unit: CNY,
   effective_from: '2024-01-01', effective_to: '2025-05-16', verification: unverified}
- id: t.fee.shfe_au.near3_jun_dec.2025-05-16
  scope: shfe_au
  rule: trans_fee_per_lot
  contracts: {any: [{months_to_delivery: {max: 2}}, {delivery_month: {in: [6, 12]}}]}
  value: 20
  unit: CNY
  effective_from: '2025-05-16'
  verification: unverified
- id: t.fee.shfe_au.other_months.2025-05-16
  scope: shfe_au
  rule: trans_fee_per_lot
  contracts: {none: [{months_to_delivery: {max: 2}}, {delivery_month: {in: [6, 12]}}]}
  value: 10
  unit: CNY
  effective_from: '2025-05-16'
  verification: unverified
- id: t.ct.shfe_au.au2506.2025-04-25
  scope: shfe_au
  rule: close_today_fee_per_lot
  contracts: {any: [{code: {in: [au2506]}}]}
  value: 20
  unit: CNY
  effective_from: '2025-04-25'
  effective_to: '2025-06-16'
  verification: unverified
- id: t.ct.czce_sr.sr2605.2026-01-05
  scope: czce_sr
  rule: close_today_fee_per_lot
  contracts: {any: [{code: {in: [sr2605]}}]}
  value: 3
  unit: CNY
  effective_from: '2026-01-05'
  verification: unverified
"""

GAPS = """\
schema: 1.2
gaps:
- gap_id: G-9001
  market: XSGE
  scope: shfe_au
  rule: close_today_fee_per_lot
  interval: {from: '2025-04-25', to: '2025-06-16'}
  contracts: {none: [{code: {in: [au2506]}}]}
  severity: medium
  reason: only au2506 was priced by the notice
  status: open
"""


def _install(tmp_path, monkeypatch, records=RECORDS, gaps=GAPS, scopes=SCOPES):
    d = tmp_path / "data" / "cn"
    d.mkdir(parents=True)
    (d / "scopes.yaml").write_text(scopes, encoding="utf-8")
    (d / "known_gaps.yaml").write_text(gaps, encoding="utf-8")
    (d / "test.yaml").write_text(records, encoding="utf-8")
    monkeypatch.setattr(mr, "DATA_DIR", str(tmp_path / "data"))
    for f in (mr.records, mr.scopes, mr.known_gaps, mr.dataset_digest):
        f.cache_clear()


@pytest.fixture
def data(tmp_path, monkeypatch):
    _install(tmp_path, monkeypatch)
    yield
    for f in (mr.records, mr.scopes, mr.known_gaps, mr.dataset_digest):
        f.cache_clear()


@pytest.fixture(autouse=True)
def _clear_after():
    yield
    for f in (mr.records, mr.scopes, mr.known_gaps, mr.dataset_digest):
        f.cache_clear()


# --- parsing and matching (no data) ------------------------------------------------------------------------------

def test_parse_contract_forms():
    assert mr.parse_contract("au2606", "2026-01-05") == ("au", 2026, 6)
    assert mr.parse_contract("AU2606", "2026-01-05", "shfe_au") == ("au", 2026, 6)
    assert mr.parse_contract("SR605", "2026-03-02") == ("sr", 2026, 5)       # CZCE YMM: this decade
    assert mr.parse_contract("SR605", "2026-06-01") == ("sr", 2036, 5)       # May 2026 is past: next year ending in 6
    assert mr.parse_contract("SR605", "2026-05-15") == ("sr", 2026, 5)       # delivery month itself still trades


@pytest.mark.parametrize("code,scope", [("au2613", None), ("au26", None), ("2606", None), ("ag2606", "shfe_au"),
                                        ("if2606", "cffex_index_futures"), ("au2606", "stock")])
def test_parse_contract_rejects(code, scope):
    with pytest.raises(ValueError):
        mr.parse_contract(code, "2026-01-05", scope)


def test_matching_rolls_with_the_trade_month():
    near = {"any": [{"months_to_delivery": {"max": 2}}, {"delivery_month": {"in": [6, 12]}}]}
    other = {"none": near["any"]}
    # 2025-07: au2507 (0), au2508 (1), au2509 (2), au2512 (Dec), au2606 (Jun) are near; au2510, au2602 are not
    for c in ("au2507", "au2508", "au2509", "au2512", "au2606"):
        assert mr.contract_matches(near, c, "2025-07-10") and not mr.contract_matches(other, c, "2025-07-10")
    for c in ("au2510", "au2602", "au2604"):
        assert mr.contract_matches(other, c, "2025-07-10") and not mr.contract_matches(near, c, "2025-07-10")
    # one month later au2510 rolls into the near tier
    assert mr.contract_matches(near, "au2510", "2025-08-01")
    both = {"any": [{"months_to_delivery": {"max": 2}, "delivery_month": {"not_in": [7]}}]}
    assert not mr.contract_matches(both, "au2507", "2025-07-01") and mr.contract_matches(both, "au2508", "2025-07-01")
    assert mr.contract_matches({"any": [{"code": {"in": ["sr2605"]}}]}, "SR605", "2026-02-02")


# --- loading -----------------------------------------------------------------------------------------------------

def test_loads_and_digest_changes(data):
    recs = {r.id: r for r in mr.records()}
    assert recs["t.fee.shfe_au.near3_jun_dec.2025-05-16"].contracts["any"][1] == {"delivery_month": {"in": [6, 12]}}
    assert recs["t.fee.shfe_au.2024-01-01"].contracts is None
    assert mr.known_gaps()[0]["contracts"] == {"none": [{"code": {"in": ["au2506"]}}]}


@pytest.mark.parametrize("mutate,msg", [
    (lambda s: s.replace("schema: 1.2", "schema: 1.1"), "needs schema: 1.2"),
    (lambda s: s.replace("{none: [{months_to_delivery: {max: 2}}, {delivery_month: {in: [6, 12]}}]}",
                         "{none: [{months_to_delivery: {max: 1}}, {delivery_month: {in: [6, 12]}}]}"),
     "overlapping contract selectors"),
    (lambda s: s.replace("effective_to: '2025-05-16'", "effective_to: '2025-06-01'"), "overlapping records"),
    (lambda s: s.replace("in: [au2506]", "in: [ag2506]"), "must be a lower-case auYYMM"),
    (lambda s: s.replace("in: [au2506]", "in: [AU2506]"), "lower-case"),
    (lambda s: s.replace("in: [sr2605]", "in: [sr605]"), "four digits"),
    (lambda s: s.replace("{max: 2}}, {delivery_month: {in: [6, 12]}}]}\n  value: 20",
                         "{max: 2}}, {delivery_month: {in: [13]}}]}\n  value: 20"), "1-12"),
    (lambda s: s.replace("{any: [{code: {in: [au2506]}}]}", "{any: []}"), "non-empty list"),
    (lambda s: s.replace("{any: [{code: {in: [au2506]}}]}", "{some: [{code: {in: [au2506]}}]}"), r"must be \{any"),
    (lambda s: s.replace("{any: [{code: {in: [au2506]}}]}", "{any: [{tier: {in: [1]}}]}"), "unknown contracts key"),
])
def test_load_refuses(tmp_path, monkeypatch, mutate, msg):
    _install(tmp_path, monkeypatch, records=mutate(RECORDS))
    with pytest.raises(ValueError, match=msg):
        mr.records()


def test_selector_needs_a_product_scope(tmp_path, monkeypatch):
    bad = RECORDS.replace("scope: czce_sr", "scope: cffex_index_futures")
    _install(tmp_path, monkeypatch, records=bad)
    with pytest.raises(ValueError, match="single futures product scope"):
        mr.records()


def test_gap_selector_needs_schema_1_2(tmp_path, monkeypatch):
    _install(tmp_path, monkeypatch, gaps=GAPS.replace("schema: 1.2", "schema: 1.1"))
    with pytest.raises(ValueError, match="needs schema: 1.2"):
        mr.known_gaps()


def test_named_code_overlap_is_found_in_open_interval(tmp_path, monkeypatch):
    extra = RECORDS + """\
- id: t.fee.shfe_au.au2612.2025-05-16
  scope: shfe_au
  rule: trans_fee_per_lot
  contracts: {any: [{code: {in: [au2612]}}]}
  value: 30
  unit: CNY
  effective_from: '2025-05-16'
  verification: unverified
"""
    _install(tmp_path, monkeypatch, records=extra)
    with pytest.raises(ValueError, match="au2612"):
        mr.records()


# --- lookup ------------------------------------------------------------------------------------------------------

def test_record_at_needs_a_contract_only_where_rules_differ(data):
    assert mr.rule_at("trans_fee_per_lot", "2025-03-03", "shfe_au", "XSGE") == 2
    assert mr.rule_at("trans_fee_per_lot", "2025-03-03", "shfe_au", "XSGE", contract="au2510") == 2
    with pytest.raises(mr.ContractRequired) as ei:
        mr.rule_at("trans_fee_per_lot", "2025-07-10", "shfe_au", "XSGE")
    assert isinstance(ei.value, KeyError) and len(ei.value.records) == 2
    assert mr.rule_at("trans_fee_per_lot", "2025-07-10", "shfe_au", "XSGE", contract="au2509") == 20
    assert mr.rule_at("trans_fee_per_lot", "2025-07-10", "shfe_au", "XSGE", contract="AU2510") == 10
    assert mr.rule_at("trans_fee_per_lot", "2025-08-01", "shfe_au", "XSGE", contract="au2510") == 20
    with pytest.raises(ValueError):
        mr.rule_at("trans_fee_per_lot", "2025-07-10", "shfe_au", "XSGE", contract="ag2510")


def test_named_contract_record_and_gap_for_the_rest(data):
    assert mr.rule_at("close_today_fee_per_lot", "2025-05-06", "shfe_au", "XSGE", contract="au2506") == 20
    with pytest.raises(KeyError, match="for contract au2508"):
        mr.rule_at("close_today_fee_per_lot", "2025-05-06", "shfe_au", "XSGE", contract="au2508")
    assert [g["gap_id"] for g in mr.gaps_for("XSGE", "shfe_au", "close_today_fee_per_lot", "2025-05-06",
                                             "2025-05-07", contract="au2508")] == ["G-9001"]
    assert mr.gaps_for("XSGE", "shfe_au", "close_today_fee_per_lot", "2025-05-06", "2025-05-07", contract="au2506") == []
    assert mr.rule_at("close_today_fee_per_lot", "2026-02-02", "czce_sr", None, contract="SR605") == 3


def test_coverage_with_and_without_contract(data):
    c = mr.coverage("XSGE", "shfe_au", ["trans_fee_per_lot"], "2025-05-01", "2025-08-01")
    assert c["status"] == "partial" and c["gaps"] == [] and "contract" in c["required_context"]
    assert c["contract_required"] == [{"rule": "trans_fee_per_lot", "from": "2025-05-16", "to": "2025-08-01",
                                       "record_ids": ["t.fee.shfe_au.near3_jun_dec.2025-05-16",
                                                      "t.fee.shfe_au.other_months.2025-05-16"]}]
    c = mr.coverage("XSGE", "shfe_au", ["trans_fee_per_lot"], "2025-05-01", "2025-08-01", contract="au2510")
    assert c["status"] == "complete" and c["contract"] == "au2510" and "contract_required" not in c
    assert set(c["records"]) == {"t.fee.shfe_au.2024-01-01", "t.fee.shfe_au.other_months.2025-05-16"}  # m 3..5
    c = mr.coverage("XSGE", "shfe_au", ["trans_fee_per_lot"], "2025-07-01", "2025-09-01", contract="au2510")
    assert set(c["records"]) == {"t.fee.shfe_au.other_months.2025-05-16", "t.fee.shfe_au.near3_jun_dec.2025-05-16"}
    c = mr.coverage("XSGE", "shfe_au", ["close_today_fee_per_lot"], "2025-05-01", "2025-06-01", contract="au2508")
    assert c["status"] == "partial" and c["known_gap_ids"] == ["G-9001"]
    # no selector involved → neither new key appears
    c = mr.coverage("XSGE", "shfe_au", ["trans_fee_per_lot"], "2025-01-01", "2025-05-01")
    assert "contract_required" not in c and "contract" not in c and c["status"] == "complete"


def test_resolve_statuses(data):
    d = resolve("trans_fee_per_lot", "2025-07-10", "shfe_au", "XSGE", {})
    assert d["status"] == "MISSING_CONTEXT" and d["missing_context"] == ["contract"]
    assert d["required_context"] == ["contract"] and d["result"] is None
    d = resolve("trans_fee_per_lot", "2025-07-10", "shfe_au", "XSGE", {"contract": "au2510"}, "unverified")
    assert d["status"] == "DETERMINED" and d["result"]["value"] == 10
    assert d["result"]["contracts"] == {"none": [{"months_to_delivery": {"max": 2}}, {"delivery_month": {"in": [6, 12]}}]}
    assert d["required_context"] == ["contract"]
    d = resolve("trans_fee_per_lot", "2025-03-03", "shfe_au", "XSGE", {"contract": "au2510"}, "unverified")
    assert d["status"] == "DETERMINED" and "contracts" not in d["result"] and d["required_context"] == []
    d = resolve("close_today_fee_per_lot", "2025-05-06", "shfe_au", "XSGE", {"contract": "au2508"})
    assert d["status"] == "OUT_OF_COVERAGE" and d["known_gap_ids"] == ["G-9001"]
