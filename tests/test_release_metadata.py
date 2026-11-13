"""Release-metadata guard (scripts/check_release_metadata.py) and changelog-driven release notes."""
import importlib.util
import os
import shutil

import pytest

import marina_rules as mr

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, "scripts", f"{name}.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


guard = _load("check_release_metadata")
notes = _load("release_notes")
FILES = ("CHANGELOG.md", "README.md", "SKILL.md", "pyproject.toml")
HISTORY = os.path.join(ROOT, "docs", "history", "CHANGELOG-through-2026.11.02.md")  # releases of the previous repository


@pytest.fixture
def repo(tmp_path):
    for f in FILES:
        shutil.copy(os.path.join(ROOT, f), tmp_path / f)
    return tmp_path


def _edit(path, old, new):
    s = path.read_text(encoding="utf-8")
    assert old in s, old
    path.write_text(s.replace(old, new), encoding="utf-8")


def test_repository_is_consistent():
    assert guard.check(ROOT, mr.VERSION, mr.dataset_digest()) == []


def test_missing_changelog_section(repo):
    _edit(repo / "CHANGELOG.md", f"## [{mr.VERSION}]", "## [0000.00.00]")
    assert any("CHANGELOG.md has no" in e for e in guard.check(str(repo), mr.VERSION, mr.dataset_digest()))


def test_stale_status_line(repo):
    _edit(repo / "README.md", f"> **Status: {mr.VERSION}.**", "> **Status: 2026.10.25.**")
    assert any("Status line" in e for e in guard.check(str(repo), mr.VERSION, mr.dataset_digest()))


def test_stale_citation_version_and_hash(repo):
    dg = mr.dataset_digest()
    _edit(repo / "README.md", f"rules: marina-rules@{mr.VERSION} sha256:{dg[:16]}",
          "rules: marina-rules@2026.10.25 sha256:8e4e9a7a7b556d6e")
    errs = guard.check(str(repo), mr.VERSION, dg)
    assert any("citation version" in e for e in errs)
    assert any("citation hash" in e for e in errs)


def test_wrong_hash_alone(repo):
    errs = guard.check(str(repo), mr.VERSION, "0" * 64)
    assert len(errs) == 1 and "citation hash" in errs[0]


def test_stale_skill_and_pyproject(repo):
    _edit(repo / "SKILL.md", f"marina-rules@{mr.VERSION} sha256", "marina-rules@2026.10.26.5 sha256")
    _edit(repo / "pyproject.toml", f'version = "{mr.VERSION}"', 'version = "2026.10.26.5"')
    errs = guard.check(str(repo), mr.VERSION, mr.dataset_digest())
    assert any(e.startswith("SKILL.md") for e in errs)
    assert any(e.startswith("pyproject.toml") for e in errs)


def test_release_notes_for_current_version():
    out = notes.release_notes(mr.VERSION)
    dg = mr.dataset_digest()
    assert f"rules: marina-rules@{mr.VERSION} sha256:{dg[:16]}" in out
    assert f"`{dg}`" in out
    assert "### Corrected (re-run needed)" in out
    assert f"## [{mr.VERSION}]" not in out  # heading replaced by the citation block
    assert "## Earlier releases" not in out  # the section ends at the next level-2 heading
    assert len(out) < 125_000  # GitHub's release-body limit


def test_current_changelog_holds_only_this_repository_releases():
    assert notes.changelog_section("2026.10.26.5") is None
    assert notes.changelog_section("2026.10.26.5", HISTORY).startswith("## [2026.10.26.5]")


def test_release_notes_section_boundaries():
    sec = notes.changelog_section("2026.10.26.4", HISTORY)
    assert sec.startswith("## [2026.10.26.4]")
    assert "## [2026.10.26.3]" not in sec and "## [2026.10.26.5]" not in sec
    assert notes.changelog_section("1999.01.01") is None
    assert notes.changelog_section("1999.01.01", HISTORY) is None


def test_every_tagged_release_has_a_section():
    for v in ("2026.10.24", "2026.10.24b", "2026.10.25", "2026.10.25b", "2026.10.25c", "2026.10.26",
              "2026.10.26.1", "2026.10.26.3", "2026.10.26.4", "2026.10.26.5"):
        assert notes.changelog_section(v, HISTORY), v


def test_unwrap_joins_continuations_only():
    md = "para one\ncontinues\n\n- item\n  wraps\n- next\n```\nkeep\nlines\n```\n### H\ntext"
    assert notes.unwrap(md) == "para one continues\n\n- item wraps\n- next\n```\nkeep\nlines\n```\n### H\ntext"
