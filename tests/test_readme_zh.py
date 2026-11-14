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
    assert "(README.zh-CN.md)" in _read("README.md")


def test_no_release_specific_numbers_to_go_stale():
    zh = _read("README.zh-CN.md")
    assert mr.DATA_VERSION not in zh and mr.__version__ not in zh and mr.dataset_digest()[:16] not in zh
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
