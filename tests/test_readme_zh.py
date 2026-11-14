"""README.zh-CN.md is the Chinese entry page. It must stay findable by the words Chinese users search for, point to
the English README for anything that changes per release, and its examples must be true."""
import os
import re

import pytest

import marina_rules as mr
from marina_rules.contract import resolve

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(name):
    with open(os.path.join(ROOT, name), encoding="utf-8") as fh:
        return fh.read()


def test_title_and_lead_carry_the_search_words():
    head = "\n".join(_read("README.zh-CN.md").splitlines()[:8])
    for word in ("交易制度", "交易规则", "涨跌停", "回测"):
        assert word in head


def test_both_readmes_link_to_each_other():
    assert "(README.md)" in _read("README.zh-CN.md")
    assert "/blob/main/README.zh-CN.md)" in _read("README.md")


def test_no_release_specific_numbers_to_go_stale():
    zh = _read("README.zh-CN.md")
    assert mr.VERSION not in zh and mr.dataset_digest()[:16] not in zh
    assert str(len(mr.records())) not in zh


def test_links_to_files_and_english_anchors_resolve():
    zh, en = _read("README.zh-CN.md"), _read("README.md")
    anchors = {re.sub(r"[^\w\- ]", "", h.lower()).strip().replace(" ", "-")
               for h in re.findall(r"^#{2,3} (.+)$", en, flags=re.M)}
    for target in re.findall(r"\]\(([^)]+)\)", zh):
        path, _, frag = target.partition("#")
        assert os.path.exists(os.path.join(ROOT, path)), target
        if frag:
            assert path == "README.md" and frag in anchors, target


def test_the_examples_are_true():
    assert mr.rule_at("stamp_duty_sell", "2023-08-25") == 0.001
    assert mr.rule_at("stamp_duty_sell", "2023-08-28") == 0.0005
    assert mr.rule_at("price_limit_pct", "2020-08-21", "chinext", "XSHE") == 0.1
    assert mr.rule_at("price_limit_pct", "2020-08-24", "chinext", "XSHE") == 0.2
    assert mr.limit_price(10.00, "chinext", "2021-03-01", "XSHE") == (12.0, 8.0)
    assert mr.limit_price(10.00, "ipo_first5_main", "2024-01-30", "XSHG+XSHE") is None
    with pytest.raises(KeyError):
        mr.rule_at("stamp_duty_sell", "2005-01-01")
    with pytest.raises(ValueError):
        mr.rule_at("stamp_duty_sell", "20230828")
    assert mr.statutory_fee_floor(86420.00, "sell", "2023-08-28", "XSHG") == pytest.approx(44.0742)
    c = mr.coverage("XSHE", "chinext", ["price_limit_pct"], "2019-01-01", "2026-10-19")
    assert c["status"] == "complete" and c["required_context"] == ["board", "st_status", "listing_day_index"]
    d = resolve("price_limit_pct", "2024-06-14", "st_main", "XSHE", {"board": "main_board", "st_status": True})
    assert (d["status"], d["result"]["value"], d["record_id"]) == ("DETERMINED", 0.05, "cn.limit.st_main.1998-04-22")
    assert set(mr.rules_for("chinext", "XSHE")) == {"price_limit_pct", "tick_size"}


def test_the_maturity_sentence_agrees_with_the_english_one():
    assert "A 股、中金所、上期所、上期能源的记录多数是 `verified`，郑商所、广期所、港股、美股多数是 `single-source`" in _read("README.zh-CN.md")
    assert "China A-share, CFFEX, SHFE and INE records are mostly `verified`" in _read("README.md")


# --- entry points for machines and for the PyPI page ------------------------------------------------------------------
BASE = "https://github.com/David-Marina/marina-rules/"


def _repo_path(url):
    rest = url[len(BASE):]
    kind, _, tail = rest.partition("/")
    assert kind in ("blob", "tree") and tail.startswith("main/"), url
    return os.path.join(ROOT, tail[len("main/"):].split("#")[0])


@pytest.mark.parametrize("name", ["README.md", "llms.txt"])
def test_absolute_repository_links_point_at_files_that_exist(name):
    urls = [u for u in re.findall(r"\]\(([^)\s]+)\)", _read(name)) if u.startswith(BASE + "blob/") or u.startswith(BASE + "tree/")]
    assert urls
    for u in urls:
        assert os.path.exists(_repo_path(u)), u


def test_readme_has_no_relative_links():
    # README.md is the long description on PyPI, where a relative link leads nowhere
    for target in re.findall(r"\]\(([^)\s]+)\)", _read("README.md")):
        assert target.startswith(("https://", "http://", "#")), target


def test_llms_txt_says_what_it_is_how_to_ask_and_what_it_lacks():
    text = _read("llms.txt")
    assert text.startswith("# marina-rules\n")
    for needle in ("pip install marina-rules", "marina-rules skill", "marina-rules capabilities", "涨跌停", "印花税",
                   "price limits", "backtest", "AI agents", "It does not contain", "DETERMINED", "YYYY-MM-DD"):
        assert needle in text, needle
    assert mr.VERSION not in text and str(len(mr.records())) not in text      # nothing that goes stale per release
    assert mr.rule_at("price_limit_pct", "2020-08-24", "chinext", "XSHE") == 0.2
    assert mr.limit_price(10.0, "chinext", "2021-03-01", "XSHE") == (12.0, 8.0)


# --- small things a first-time user or agent trips over ---------------------------------------------------------------
def test_rule_at_answers_a_family_rule_the_way_rules_for_lists_it():
    assert "tick_size" in mr.rules_for("chinext", "XSHE")
    assert mr.rule_at("tick_size", "2024-01-02", "chinext", "XSHE") == mr.tick_size("chinext", "2024-01-02", "XSHE") == 0.01
    with pytest.raises(KeyError):                                   # record_at reads exactly the scope it is given
        mr.record_at("tick_size", "2024-01-02", "chinext", "XSHE")
    with pytest.raises(KeyError):                                   # and a futures scope still has no tick
        mr.rule_at("tick_size", "2024-01-02", "cffex_if", "CCFX")


def test_cli_scopes_refuses_an_unknown_registry_and_rules_point_to_stock(capsys):
    import json
    from marina_rules.cli import main as cli
    assert cli(["scopes", "cnx"]) == 2 and "unknown registry" in capsys.readouterr().out
    assert cli(["rules", "chinext", "XSHE"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["see_also"]["scopes"] == ["stock"] and "stamp duty" in out["see_also"]["note"]
    assert cli(["rules", "bse", "BJSE"]) == 0
    assert json.loads(capsys.readouterr().out)["see_also"]["scopes"] == ["bse_stock", "stock"]
    assert cli(["rules", "stock"]) == 0
    assert "see_also" not in json.loads(capsys.readouterr().out)


def test_diff_outside_a_clone_says_what_to_do(capsys):
    from marina_rules.diff import main as diff_main
    assert diff_main(["no-such-tag-1", "no-such-tag-2"]) == 2
    assert "clone of the repository" in capsys.readouterr().err


def test_check_help_prints_the_canonical_form_literally(capsys):
    from marina_rules.check import main as check_main
    assert check_main(["--help"]) == 0
    text = capsys.readouterr().out
    assert 'marina-check-canon/2 strict=<0|1>\\n' in text and 'separators=(",", ":")) + "\\n"' in text


def test_packaging_metadata_names_both_licences_and_the_search_words():
    py = _read("pyproject.toml")
    assert 'license = "MIT AND CC0-1.0"' in py and 'license-files = ["LICENSE", "LICENSE-DATA"]' in py
    for word in ("A-share", "涨跌停", "backtests", "AI agents"):
        assert word in re.search(r'^description = "(.*)"$', py, flags=re.M).group(1)
    for word in ("涨跌停", "印花税", "回测", "price-limit", "stamp-duty", "a-share", "backtest-validation"):
        assert f'"{word}"' in py
