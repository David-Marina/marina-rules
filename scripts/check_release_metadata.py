"""Release-metadata guard: the version and dataset hash every reader sees must agree.

    python scripts/check_release_metadata.py        # exit 0 = consistent, 1 = list of problems

Checks, against marina_rules.VERSION and marina_rules.dataset_digest():
  (a) CHANGELOG.md has a ``## [VERSION]`` section;
  (b) pyproject.toml ``version``, README's ``> **Status: X.**`` line, README's example citation
      ``rules: marina-rules@X sha256:…`` and every ``marina-rules@X`` in SKILL.md equal VERSION;
  (c) README's example citation hash equals the first 16 hex of dataset_digest().
"""
from __future__ import annotations

import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

STATUS = re.compile(r"^> \*\*Status: (?P<v>[^*]+?)\.\*\*", re.M)
CITATION = re.compile(r"rules: marina-rules@(?P<v>[0-9A-Za-z.]+) sha256:(?P<h>[0-9a-f]{16})\b")
SKILL_REF = re.compile(r"marina-rules@(?P<v>[0-9][0-9A-Za-z.]*[0-9A-Za-z])")
PYPROJECT = re.compile(r'^version\s*=\s*"(?P<v>[^"]+)"', re.M)
HEADING = re.compile(r"^## \[(?P<v>[^\]]+)\]", re.M)


def _read(root: str, name: str) -> str:
    with open(os.path.join(root, name), encoding="utf-8") as fh:
        return fh.read()


def check(root: str, version: str, digest: str) -> list[str]:
    """Return a list of human-readable problems; empty means consistent."""
    errors: list[str] = []

    if version not in [m.group("v") for m in HEADING.finditer(_read(root, "CHANGELOG.md"))]:
        errors.append(f"CHANGELOG.md has no '## [{version}]' section")

    m = PYPROJECT.search(_read(root, "pyproject.toml"))
    if not m or m.group("v") != version:
        errors.append(f"pyproject.toml version {m.group('v') if m else None!r} != VERSION {version!r}")

    readme = _read(root, "README.md")
    statuses = [s.group("v") for s in STATUS.finditer(readme)]
    if not statuses:
        errors.append("README.md has no '> **Status: X.**' line")
    for s in statuses:
        if s != version:
            errors.append(f"README.md Status line says {s!r}, VERSION is {version!r}")

    cites = list(CITATION.finditer(readme))
    if not cites:
        errors.append("README.md has no example citation 'rules: marina-rules@<version> sha256:<16 hex>'")
    for c in cites:
        if c.group("v") != version:
            errors.append(f"README.md citation version {c.group('v')!r} != VERSION {version!r}")
        if c.group("h") != digest[:16]:
            errors.append(f"README.md citation hash {c.group('h')} != dataset_digest()[:16] {digest[:16]}")

    skill_refs = [s.group("v") for s in SKILL_REF.finditer(_read(root, "SKILL.md"))]
    if not skill_refs:
        errors.append("SKILL.md cites no 'marina-rules@<version>'")
    for s in skill_refs:
        if s != version:
            errors.append(f"SKILL.md cites marina-rules@{s}, VERSION is {version!r}")

    return errors


def main() -> int:
    sys.path.insert(0, os.path.join(ROOT, "src"))
    import marina_rules as mr
    errors = check(ROOT, mr.VERSION, mr.dataset_digest())
    for e in errors:
        print(f"::error::{e}")
    if not errors:
        print(f"release metadata consistent: {mr.citation()}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
