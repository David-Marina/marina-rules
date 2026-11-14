"""An assistant that only has the installed package must be able to find out what can be asked, be told what
exists when it asks for the wrong name, and get the statutory fees of a fill without doing the sum by hand."""
import json
import os
import subprocess
import sys

import pytest

import marina_rules as mr
from marina_rules.check import statutory_fee_floor as check_floor
from marina_rules.cli import main as cli
from marina_rules.contract import contract_schema, resolve

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# --- rules_for ---------------------------------------------------------------------------------------------------
def test_rules_for_lists_what_record_at_can_answer():
    have = mr.rules_for("cffex_if", "CCFX")
    assert "price_limit_pct_of_prev_settlement" in have and "price_limit_pct" not in have
    for rule, ivs in have.items():
        assert ivs == sorted(ivs, key=lambda t: (t[0], t[1] or "9999-12-31"))
        frm = ivs[0][0]
        assert mr.record_at(rule, frm, mr.lookup_scope(rule, "cffex_if", "CCFX"), "CCFX").rule == rule


def test_rules_for_adds_family_rules_and_filters_by_market():
    assert "tick_size" in mr.rules_for("chinext", "XSHE")          # recorded under the family scope 'stock'
    assert mr.rules_for("chinext", "XSHE")["tick_size"] == mr.rules_for("stock", "XSHE")["tick_size"]
    assert mr.rules_for("no_such_scope") == {}
    assert mr.rules_for("cffex_if", "XSHG") == {}


def test_every_registered_scope_is_listed_consistently():
    for pfx in ("cn", "hk", "us"):
        for scope in mr.scopes(pfx):
            for rule, ivs in mr.rules_for(scope).items():
                assert ivs and all(len(iv) == 2 for iv in ivs), (scope, rule)


# --- the miss message --------------------------------------------------------------------------------------------
def test_wrong_rule_name_names_the_rules_the_scope_has():
    with pytest.raises(KeyError) as e:
        mr.rule_at("price_limit_pct", "2024-06-03", "cffex_if", "CCFX")
    msg = e.value.args[0]
    assert msg.startswith("no price_limit_pct/cffex_if rule in force on 2024-06-03")
    assert "price_limit_pct_of_prev_settlement" in msg and "margin_ratio" in msg


def test_date_outside_every_interval_names_the_intervals():
    with pytest.raises(KeyError) as e:
        mr.rule_at("stamp_duty_sell", "1985-01-01")
    assert "2005-01-24" in e.value.args[0] and "none covers 1985-01-01" in e.value.args[0]


def test_family_rule_under_a_board_scope_points_to_the_family():
    with pytest.raises(KeyError) as e:
        mr.rule_at("tick_size", "2024-01-02", "chinext")
    assert "'stock'" in e.value.args[0]


def test_miss_inside_an_interval_adds_nothing():
    # an interval covers the date, so the miss has another cause that the message already states
    assert mr._miss_hint("stamp_duty_sell", "stock", None, "2024-01-02") == ""


def test_unknown_scope_says_so():
    with pytest.raises(KeyError) as e:
        mr.rule_at("price_limit_pct", "2024-01-02", "unicorn")
    assert "holds no rule at all for scope 'unicorn'" in e.value.args[0]


# --- resolve: alternatives ---------------------------------------------------------------------------------------
def test_resolve_wrong_rule_name_offers_alternatives():
    d = resolve("price_limit_pct", "2024-06-03", "cffex_if", "CCFX")
    assert d["status"] == "OUT_OF_COVERAGE" and d["result"] is None
    assert d["alternatives"]["similar_rules"] == ["price_limit_pct_of_prev_settlement"]
    assert d["alternatives"]["scope_rules"] == sorted(mr.rules_for("cffex_if", "CCFX"))
    assert "price_limit_pct_of_prev_settlement" in d["reason"] and not d["reason"].startswith('"')
    good = resolve("price_limit_pct_of_prev_settlement", "2024-06-03", "cffex_if", "CCFX")
    assert good["status"] == "DETERMINED" and good["alternatives"] == {}


def test_resolve_date_before_first_record_gives_intervals():
    d = resolve("stamp_duty_sell", "1985-01-01", "stock", "XSHG")
    assert d["status"] == "OUT_OF_COVERAGE"
    assert d["alternatives"]["rule_intervals"][0][0] == "2005-01-24" and "similar_rules" not in d["alternatives"]


def test_resolve_unknown_scope_offers_scope_names():
    d = resolve("price_limit_pct", "2024-06-03", "chinex", "XSHE")
    assert d["status"] == "OUT_OF_COVERAGE" and "chinext" in d["alternatives"]["similar_scopes"]
    assert resolve("price_limit_pct", "2024-06-03", "zzzz", "XSHE")["alternatives"] == {}


def test_alternatives_never_carry_a_value():
    # the refusal lists names only; the caller has to ask again to get a value
    d = resolve("price_limit_pct", "2024-06-03", "cffex_if", "CCFX")
    assert d["result"] is None and d["record_id"] is None and d["evidence_refs"] == []
    assert set(d["alternatives"]) <= {"scope_rules", "similar_rules", "rule_intervals", "similar_scopes", "markets"}


def test_schema_declares_alternatives():
    props = contract_schema()["properties"]
    assert set(props["alternatives"]["properties"]) == {"scope_rules", "similar_rules", "rule_intervals", "similar_scopes", "markets"}


# --- statutory fees ----------------------------------------------------------------------------------------------
def test_fee_floor_is_public_and_is_the_checkers():
    assert mr.statutory_fee_floor is check_floor
    assert mr.statutory_fee_floor(86420.00, "sell", "2023-08-28", "XSHG") == pytest.approx(44.0742, abs=1e-9)


@pytest.mark.parametrize("args", [(100000, "sell", "2010-03-01", "XSHG"), (100000, "sell", "2010-03-01", "XSHE"),
                                  (100000, "buy", "2007-06-01", "XSHG"), (100000, "sell", "2021-12-01", "BJSE"),
                                  (100000, "sell", "2021-12-01"), (86420.0, "buy", "2024-03-01", "XSHE")])
def test_components_sum_to_the_floor(args):
    comps = mr.statutory_fee_components(*args)
    total = sum(c["amount"] for c in comps if c["amount"] is not None)
    assert mr.statutory_fee_floor(*args) == pytest.approx(total, abs=1e-12)
    for c in comps:
        rec = next(r for r in mr.records() if r.id == c["record_id"])
        assert rec.rule == c["rule"] and rec.value == c["rate"]
        assert (c["amount"] is None) == (c["basis"] == "par_value")


def test_par_value_component_is_reported_but_not_summed():
    comps = mr.statutory_fee_components(100000, "sell", "2010-03-01", "XSHG")
    assert [c["rule"] for c in comps] == ["stamp_duty_sell", "transfer_fee_par_value"]
    assert comps[1]["amount"] is None and mr.statutory_fee_floor(100000, "sell", "2010-03-01", "XSHG") == 100.0


def test_fee_floor_refuses_before_the_first_record():
    with pytest.raises(KeyError):
        mr.statutory_fee_floor(1000, "sell", "1985-01-01", "XSHG")


# --- usage notes and the command line ----------------------------------------------------------------------------
def test_skill_text_is_the_repository_file():
    with open(os.path.join(ROOT, "SKILL.md"), encoding="utf-8") as fh:
        assert mr.skill_text() == fh.read()


def test_module_docstring_points_to_the_entry_points():
    for name in ("skill_text", "rules_for", "statutory_fee_floor", "python -m marina_rules"):
        assert name in mr.__doc__
    for name in ("rules_for", "statutory_fee_floor", "statutory_fee_components", "skill_text"):
        assert name in mr.__all__ and callable(getattr(mr, name))


def _run(capsys, *argv):
    code = cli(list(argv))
    return code, capsys.readouterr().out


def test_cli_help_and_unknown(capsys):
    code, out = _run(capsys)
    assert code == 2 and "query <rule> <date> <scope>" in out
    assert _run(capsys, "--help")[0] == 0
    code, out = _run(capsys, "nonsense")
    assert code == 2 and "unknown command" in out


def test_cli_query_matches_resolve(capsys):
    code, out = _run(capsys, "query", "price_limit_pct", "2024-06-14", "st_main", "XSHE",
                     "--context", "board=main_board,st_status=true")
    want = resolve("price_limit_pct", "2024-06-14", "st_main", "XSHE", {"board": "main_board", "st_status": True})
    assert code == 0 and json.loads(out) == json.loads(json.dumps(want))
    assert _run(capsys, "query", "price_limit_pct")[0] == 2


def test_cli_rules_is_compact_by_default(capsys):
    code, out = _run(capsys, "rules", "cffex_if", "CCFX")
    d = json.loads(out)
    assert code == 0 and d["rules"]["price_limit_pct_of_prev_settlement"]["from"] == "2010-04-16"
    assert d["citation"] == mr.citation()
    code, out = _run(capsys, "rules", "cffex_if", "CCFX", "--intervals")
    assert json.loads(out)["rules"] == mr.rules_for("cffex_if", "CCFX")
    code, out = _run(capsys, "rules", "chinex")
    d = json.loads(out)
    assert d["rules"] == {} and "chinext" in d["similar_scopes"] and "not in any registry" in d["note"]


def test_cli_fees(capsys):
    code, out = _run(capsys, "fees", "86420", "sell", "2023-08-28", "XSHG")
    d = json.loads(out)
    assert code == 0 and d["status"] == "DETERMINED" and d["statutory_fee_floor"] == pytest.approx(44.0742, abs=1e-9)
    assert [c["rule"] for c in d["components"]] == ["stamp_duty_sell", "transfer_fee_each_side"]
    code, out = _run(capsys, "fees", "1000", "sell", "1985-01-01", "XSHG")
    assert code == 0 and json.loads(out)["status"] == "OUT_OF_COVERAGE"
    assert _run(capsys, "fees", "abc", "sell", "2023-08-28")[0] == 2
    assert _run(capsys, "fees", "1000", "hold", "2023-08-28")[0] == 2


def test_cli_scopes_schema_capabilities_skill_version(capsys):
    code, out = _run(capsys, "scopes")
    assert code == 0 and json.loads(out)["chinext"]["requires"] == list(mr.scopes()["chinext"]["requires"])
    assert "hk_stock" in json.loads(_run(capsys, "scopes", "hk")[1])
    assert json.loads(_run(capsys, "schema")[1]) == json.loads(json.dumps(contract_schema()))
    assert "cli" in json.loads(_run(capsys, "capabilities", "us")[1])["entrypoints"]["python"]
    assert _run(capsys, "skill")[1].startswith("---\nname: marina-rules")
    assert _run(capsys, "version")[1].strip() == mr.citation()


def test_python_dash_m_runs_the_same_cli():
    env = dict(os.environ, PYTHONPATH=os.path.join(ROOT, "src"))
    p = subprocess.run([sys.executable, "-B", "-m", "marina_rules", "version"], capture_output=True, text=True, env=env)
    assert p.returncode == 0 and p.stdout.strip() == mr.citation()


def test_packaging_declares_the_script_and_the_notes():
    with open(os.path.join(ROOT, "pyproject.toml"), encoding="utf-8") as fh:
        text = fh.read()
    assert 'marina-rules = "marina_rules.cli:main"' in text and '"SKILL.md"' in text
    with open(os.path.join(ROOT, "scripts", "vendor_data.py"), encoding="utf-8") as fh:
        assert "SKILL.md" in fh.read()
    with open(os.path.join(ROOT, ".gitignore"), encoding="utf-8") as fh:
        assert "src/marina_rules/SKILL.md" in fh.read()


# --- the stock tick must not answer for a scope that is not a mainland security -----------------------------------
@pytest.mark.parametrize("scope", ["cffex_if", "shfe_au", "hk_stock", "us_stock", "unicorn"])
def test_stock_tick_does_not_answer_for_other_instruments(scope):
    with pytest.raises(KeyError):
        mr.tick_size(scope, "2024-01-02")
    assert mr.tick_family(scope) == scope


def test_futures_scope_without_market_is_refused_for_tick_size():
    d = resolve("tick_size", "2024-01-02", "cffex_if")
    assert d["status"] == "OUT_OF_COVERAGE" and d["result"] is None
    assert mr.coverage(None, "cffex_if", ["tick_size"], "2024-01-01", "2024-02-01")["status"] != "complete"


def test_no_futures_hk_us_scope_lists_a_borrowed_tick():
    for scope in mr.scopes("cn"):
        markets = {m for r in mr.records() if r.scope == scope for m in r.market.split("+")}
        if markets and not markets & {"XSHG", "XSHE", "BJSE"}:
            assert "tick_size" not in mr.rules_for(scope), scope
    for pfx in ("hk", "us"):
        for scope in mr.scopes(pfx):
            own = {r.rule for r in mr.records() if r.scope == scope}
            assert set(mr.rules_for(scope)) == own, scope


@pytest.mark.parametrize("scope,market,want", [("main_board", None, 0.01), ("chinext", "XSHE", 0.01), ("etf", "XSHG", 0.001),
                                               ("star_growth_new", "XSHG", 0.01), ("bse", "BJSE", 0.01)])
def test_securities_scopes_keep_their_tick(scope, market, want):
    assert mr.tick_size(scope, "2024-01-02", market) == want
