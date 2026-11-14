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
    os.makedirs(tmp_path / "packages" / "marina-rules")
    shutil.copy(os.path.join(ROOT, "packages", "marina-rules", "pyproject.toml"), tmp_path / "packages" / "marina-rules")
    return tmp_path


def _edit(path, old, new):
    s = path.read_text(encoding="utf-8")
    assert old in s, old
    path.write_text(s.replace(old, new), encoding="utf-8")


DV, CV = mr.VERSION, mr.__version__


def _check(root=ROOT, digest=None):
    return guard.check(str(root), DV, CV, mr.dataset_digest() if digest is None else digest)


def test_repository_is_consistent():
    assert _check() == []


def test_missing_changelog_section(repo):
    _edit(repo / "CHANGELOG.md", f"## [{DV}]", "## [0000.00.00]")
    assert any("CHANGELOG.md has no" in e for e in _check(repo))


def test_stale_status_line(repo):
    _edit(repo / "README.md", f"> **Status: {DV}.**", "> **Status: 2026.10.25.**")
    assert any("Status line" in e for e in _check(repo))


def test_stale_citation_versions_and_hash(repo):
    dg = mr.dataset_digest()
    _edit(repo / "README.md", f"rules: marina-rules@{DV} sha256:{dg[:16]} code: marina-rules-core@{CV}",
          "rules: marina-rules@2026.10.25 sha256:8e4e9a7a7b556d6e code: marina-rules-core@0.9.0")
    errs = _check(repo)
    assert any("citation data version" in e for e in errs)
    assert any("citation hash" in e for e in errs)
    assert any("citation code version" in e for e in errs)


def test_example_citation_must_name_the_code_version(repo):
    dg = mr.dataset_digest()
    _edit(repo / "README.md", f"rules: marina-rules@{DV} sha256:{dg[:16]} code: marina-rules-core@{CV}",
          f"rules: marina-rules@{DV} sha256:{dg[:16]}")
    assert any("does not name the code version" in e for e in _check(repo))


def test_example_citation_of_the_previous_split_is_not_accepted(repo):
    dg = mr.dataset_digest()
    s = (repo / "README.md").read_text(encoding="utf-8")
    (repo / "README.md").write_text(s.replace(f"rules: marina-rules@{DV} sha256:{dg[:16]} code: marina-rules-core@{CV}",
                                              f"rules: marina-rules-data@{DV} sha256:{dg[:16]} code: marina-rules@{CV}"),
                                    encoding="utf-8")
    assert any("has no example citation" in e for e in _check(repo))


def test_dataset_must_accept_this_code_version(repo):
    _edit(repo / "packages" / "marina-rules" / "pyproject.toml", '"marina-rules-core>=1.0.0,<2"',
          '"marina-rules-core>=1.1.0,<2"')
    assert any("excludes the code version" in e for e in _check(repo))
    _edit(repo / "packages" / "marina-rules" / "pyproject.toml", '"marina-rules-core>=1.1.0,<2"', '"marina-rules-core"')
    assert any("has no dependency" in e for e in _check(repo))


def test_wrong_hash_alone(repo):
    errs = _check(repo, "0" * 64)
    assert errs and all("citation hash" in e for e in errs)   # one per example citation in README.md


def test_versioned_skill_and_stale_pyproject(repo):
    with open(repo / "SKILL.md", "a", encoding="utf-8") as fh:
        fh.write(f"\nrules: marina-rules@{DV} sha256:0000 code: marina-rules-core@{CV}\n")
    _edit(repo / "pyproject.toml", f'version = "{CV}"', 'version = "2026.10.26.5"')
    errs = _check(repo)
    assert sum(e.startswith("SKILL.md names") for e in errs) == 2
    assert any(e.startswith("pyproject.toml") for e in errs)


def test_code_release_needs_a_dated_code_section(repo):
    assert guard.code_heading("1.2.3") == "marina-rules-core 1.2.3"
    assert guard.release_date(str(repo), guard.code_heading("1.2.3")) is None
    with open(repo / "CHANGELOG.md", "a", encoding="utf-8") as fh:
        fh.write("\n## [marina-rules-core 1.2.3] - 2026-12-01\n\nx\n")
    assert guard.release_date(str(repo), guard.code_heading("1.2.3")) == "2026-12-01"


def test_release_kind_must_be_named():
    assert guard.main(["--release"]) == 2 and guard.main(["--release", "both"]) == 2


def test_release_notes_for_current_data_version():
    out = notes.release_notes(DV)
    dg = mr.dataset_digest()
    assert f"rules: marina-rules@{DV} sha256:{dg[:16]}" in out and "pip install -U marina-rules`" in out
    assert f"`{dg}`" in out
    assert "### Corrected (re-run needed)" in out
    assert f"## [{DV}]" not in out  # heading replaced by the citation block
    assert "## Earlier releases" not in out  # the section ends at the next level-2 heading
    assert len(out) < 125_000  # GitHub's release-body limit


def test_release_notes_for_a_code_tag(monkeypatch, tmp_path):
    cl = tmp_path / "CHANGELOG.md"
    cl.write_text("# Changelog\n\n## [marina-rules-core 1.2.3] - 2026-12-01\n\n### Changed\n\n- a thing\n\n"
                  "## [2026.11.13] - 2026-11-13\n\ndata\n", encoding="utf-8")
    real = notes.changelog_section
    monkeypatch.setattr(notes, "changelog_section", lambda v, path=str(cl): real(v, path))
    out = notes.release_notes("core-v1.2.3")
    assert "pip install -U marina-rules-core" in out and f"marina-rules {mr.MIN_DATA_VERSION} or later" in out
    assert "- a thing" in out and "\ndata\n" not in out and "2026.11.13]" not in out
    with pytest.raises(SystemExit):
        notes.release_notes("core-v9.9.9")
    with pytest.raises(SystemExit):
        notes.release_notes("v1.2.3")          # not a tag of this repository: the code tags are core-vX.Y.Z


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
