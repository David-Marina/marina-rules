"""Release-metadata guard: the version and dataset hash every reader sees must agree.

    python scripts/check_release_metadata.py             # exit 0 = consistent, 1 = list of problems
    python scripts/check_release_metadata.py --release   # also bound the tracking dates by the release date

Checks, against marina_rules.VERSION and marina_rules.dataset_digest():
  (a) CHANGELOG.md has a ``## [VERSION]`` section;
  (b) pyproject.toml ``version``, README's ``> **Status: X.**`` line, README's example citation
      ``rules: marina-rules@X sha256:…`` and every ``marina-rules@X`` in SKILL.md equal VERSION;
  (c) README's example citation hash equals the first 16 hex of dataset_digest();
  (d) tracking registry (data/<prefix>/tracking.yaml): no ``tracked_through`` or ``updated`` after today (Asia/Tokyo),
      and with ``--release`` none after the release date (the date in CHANGELOG.md's ``## [VERSION] - YYYY-MM-DD``
      heading). The age of every entry is printed. An old date is not an error: staleness is information.
"""
from __future__ import annotations

import datetime as dt
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

STATUS = re.compile(r"^> \*\*Status: (?P<v>[^*]+?)\.\*\*", re.M)
CITATION = re.compile(r"rules: marina-rules@(?P<v>[0-9A-Za-z.]+) sha256:(?P<h>[0-9a-f]{16})\b")
SKILL_REF = re.compile(r"marina-rules@(?P<v>[0-9][0-9A-Za-z.]*[0-9A-Za-z])")
PYPROJECT = re.compile(r'^version\s*=\s*"(?P<v>[^"]+)"', re.M)
HEADING = re.compile(r"^## \[(?P<v>[^\]]+)\]", re.M)
DATED_HEADING = re.compile(r"^## \[(?P<v>[^\]]+)\] - (?P<d>\d{4}-\d{2}-\d{2})", re.M)
JST = dt.timezone(dt.timedelta(hours=9))


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


def release_date(root: str, version: str) -> str | None:
    """The date after CHANGELOG.md's ``## [version] - YYYY-MM-DD`` heading, or None."""
    for m in DATED_HEADING.finditer(_read(root, "CHANGELOG.md")):
        if m.group("v") == version:
            return m.group("d")
    return None


def check_tracking(entries: list, today: str, release: str | None = None) -> tuple:
    """(errors, report lines) for the tracking registry. A date after ``today`` — or after ``release`` when given — is
    an error; an old date is reported with its age and is not an error."""
    errors: list[str] = []
    lines: list[str] = []
    bound = release or today
    for e in entries:
        what = e["market"] + ("" if not e.get("scopes") else " " + ",".join(e["scopes"]))
        for key in ("tracked_through", "updated"):
            if e[key] > today:
                errors.append(f"tracking {what}: {key} {e[key]} is in the future (today {today})")
            elif release is not None and e[key] > release:
                errors.append(f"tracking {what}: {key} {e[key]} is after the release date {release}")
        age = (dt.date.fromisoformat(bound) - dt.date.fromisoformat(e["tracked_through"])).days
        lines.append(f"tracking {what}: tracked through {e['tracked_through']} ({age} days before {bound}), "
                     f"updated {e['updated']}")
    return errors, lines


def main(argv: list | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    sys.path.insert(0, os.path.join(ROOT, "src"))
    import marina_rules as mr
    errors = check(ROOT, mr.VERSION, mr.dataset_digest())
    release = None
    if "--release" in argv:
        release = release_date(ROOT, mr.VERSION)
        if release is None:
            errors.append(f"CHANGELOG.md has no dated heading '## [{mr.VERSION}] - YYYY-MM-DD'")
    t_errors, t_lines = check_tracking(mr.tracking_registry(), dt.datetime.now(JST).date().isoformat(), release)
    errors += t_errors
    for e in errors:
        print(f"::error::{e}")
    for line in t_lines:
        print(line)
    if not errors:
        print(f"release metadata consistent: {mr.citation()}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
