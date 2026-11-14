"""The issue forms: valid GitHub issue-form YAML, and each one asks for what a record is built from."""
import os

import pytest
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIR = os.path.join(ROOT, ".github", "ISSUE_TEMPLATE")
FORMS = ("wrong_rule.yml", "missing_rule.yml", "rule_changed.yml")


def _load(name):
    with open(os.path.join(DIR, name), encoding="utf-8") as fh:
        return yaml.safe_load(fh)


@pytest.mark.parametrize("name", FORMS)
def test_form_is_well_formed(name):
    f = _load(name)
    assert set(f) <= {"name", "description", "title", "labels", "assignees", "body"}
    assert f["name"] and f["description"] and f["body"]
    ids = [b["id"] for b in f["body"] if b["type"] != "markdown"]
    assert len(ids) == len(set(ids))
    for b in f["body"]:
        assert b["type"] in ("markdown", "input", "textarea", "dropdown", "checkboxes")
        if b["type"] != "markdown":
            assert b["attributes"]["label"]


@pytest.mark.parametrize("name,needs", [("wrong_rule.yml", {"query", "source", "quote", "citation"}),
                                        ("missing_rule.yml", {"query", "refusal", "citation"}),
                                        ("rule_changed.yml", {"source", "effective", "quote"})])
def test_form_requires_what_a_record_is_built_from(name, needs):
    required = {b["id"] for b in _load(name)["body"]
                if b["type"] != "markdown" and (b.get("validations") or {}).get("required")}
    assert needs <= required


def test_chooser_links_and_readme_points_to_it():
    cfg = _load("config.yml")
    assert cfg["blank_issues_enabled"] is True
    assert all(link["url"].startswith("https://") for link in cfg["contact_links"])
    with open(os.path.join(ROOT, "README.md"), encoding="utf-8") as fh:
        assert "https://github.com/David-Marina/marina-rules/issues/new/choose" in fh.read()


def test_readme_lead_says_what_a_stamp_does_not_certify():
    with open(os.path.join(ROOT, "README.md"), encoding="utf-8") as fh:
        head = fh.read()[:2500]
    assert head.count("**Auditable backtests:") == 1
    assert "says nothing about look-ahead in prices, survivorship or overfitting" in head
