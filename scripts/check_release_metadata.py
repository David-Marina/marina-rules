"""Release-metadata guard: the versions and dataset hash every reader sees must agree.

    python scripts/check_release_metadata.py                  # exit 0 = consistent, 1 = list of problems
    python scripts/check_release_metadata.py --release data   # releasing marina-rules, the dataset (tag YYYY.MM.DD[.N])
    python scripts/check_release_metadata.py --release code   # releasing marina-rules-core, the code (tag core-vX.Y.Z)

Two packages, two versions: the dataset (marina-rules, ``marina_rules.VERSION`` = ``DATA_VERSION`` = data/VERSION) and
the code (marina-rules-core, ``marina_rules.__version__``). Checks, against those and marina_rules.dataset_digest():
  (a) CHANGELOG.md has a ``## [VERSION]`` section;
  (b) pyproject.toml ``version`` equals the code version; packages/marina-rules/pyproject.toml requires
      ``marina-rules-core>=A,<B`` with A <= the code version < B (the dataset must be installable with this code);
      README's ``> **Status: X.**`` line equals the data version; README's example citation
      ``rules: marina-rules@X sha256:<16 hex> code: marina-rules-core@Y`` names the data version, the first 16 hex of
      dataset_digest() and the code version;
  (c) SKILL.md names no concrete version: it ships inside the code wheel, and the data under it is upgraded separately;
  (d) tracking registry (data/<prefix>/tracking.yaml): no ``tracked_through`` or ``updated`` after today (Asia/Tokyo),
      and with ``--release data`` none after the release date (the date in CHANGELOG.md's
      ``## [VERSION] - YYYY-MM-DD`` heading). The age of every entry is printed. An old date is not an error:
      staleness is information;
  (e) with ``--release code``: CHANGELOG.md has a dated ``## [marina-rules-core X.Y.Z] - YYYY-MM-DD`` section.
"""
from __future__ import annotations

import datetime as dt
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

STATUS = re.compile(r"^> \*\*Status: (?P<v>[^*]+?)\.\*\*", re.M)
CITATION = re.compile(r"rules: marina-rules@(?P<v>[0-9][0-9A-Za-z.]*[0-9A-Za-z]) sha256:(?P<h>[0-9a-f]{16})\b"
                      r"(?: code: marina-rules-core@(?P<c>[0-9][0-9A-Za-z.]*[0-9A-Za-z]))?")
VERSIONED_REF = re.compile(r"marina-rules(?:-core)?@[0-9][0-9A-Za-z.]*")
CORE_REQ = re.compile(r'"marina-rules-core>=(?P<lo>[0-9][0-9.]*),<(?P<hi>[0-9][0-9.]*)"')
DATA_PYPROJECT = os.path.join("packages", "marina-rules", "pyproject.toml")
PYPROJECT = re.compile(r'^version\s*=\s*"(?P<v>[^"]+)"', re.M)
HEADING = re.compile(r"^## \[(?P<v>[^\]]+)\]", re.M)
DATED_HEADING = re.compile(r"^## \[(?P<v>[^\]]+)\] - (?P<d>\d{4}-\d{2}-\d{2})", re.M)
JST = dt.timezone(dt.timedelta(hours=9))


def code_heading(code_version: str) -> str:
    """The CHANGELOG.md heading name of a code release: ``marina-rules-core X.Y.Z``."""
    return f"marina-rules-core {code_version}"


def _semver(v: str) -> tuple:
    return tuple(int(x) for x in v.split("."))


def _read(root: str, name: str) -> str:
    with open(os.path.join(root, name), encoding="utf-8") as fh:
        return fh.read()


def check(root: str, data_version: str, code_version: str, digest: str) -> list[str]:
    """Return a list of human-readable problems; empty means consistent."""
    errors: list[str] = []

    if data_version not in [m.group("v") for m in HEADING.finditer(_read(root, "CHANGELOG.md"))]:
        errors.append(f"CHANGELOG.md has no '## [{data_version}]' section")

    m = PYPROJECT.search(_read(root, "pyproject.toml"))
    if not m or m.group("v") != code_version:
        errors.append(f"pyproject.toml version {m.group('v') if m else None!r} != code version {code_version!r}")

    req = CORE_REQ.search(_read(root, DATA_PYPROJECT))
    if not req:
        errors.append(f"{DATA_PYPROJECT} has no dependency '\"marina-rules-core>=A,<B\"'")
    elif not _semver(req.group("lo")) <= _semver(code_version) < _semver(req.group("hi")):
        errors.append(f"{DATA_PYPROJECT} requires marina-rules-core>={req.group('lo')},<{req.group('hi')}, "
                      f"which excludes the code version {code_version!r}")

    readme = _read(root, "README.md")
    statuses = [s.group("v") for s in STATUS.finditer(readme)]
    if not statuses:
        errors.append("README.md has no '> **Status: X.**' line")
    for s in statuses:
        if s != data_version:
            errors.append(f"README.md Status line says {s!r}, the data version is {data_version!r}")

    cites = list(CITATION.finditer(readme))
    if not cites:
        errors.append("README.md has no example citation "
                      "'rules: marina-rules@<data version> sha256:<16 hex> code: marina-rules-core@<code version>'")
    for c in cites:
        if c.group("v") != data_version:
            errors.append(f"README.md citation data version {c.group('v')!r} != {data_version!r}")
        if c.group("h") != digest[:16]:
            errors.append(f"README.md citation hash {c.group('h')} != dataset_digest()[:16] {digest[:16]}")
        if c.group("c") is None:
            errors.append(f"README.md citation {c.group(0)!r} does not name the code version "
                          f"(' code: marina-rules-core@{code_version}')")
        elif c.group("c") != code_version:
            errors.append(f"README.md citation code version {c.group('c')!r} != {code_version!r}")

    for ref in sorted(set(VERSIONED_REF.findall(_read(root, "SKILL.md")))):
        errors.append(f"SKILL.md names {ref}: it ships inside the code wheel while the data is upgraded separately, "
                      "so it must not name a version (write <data version> / <code version>)")

    return errors


def release_date(root: str, version: str) -> str | None:
    """The date after CHANGELOG.md's ``## [version] - YYYY-MM-DD`` heading, or None. ``version`` is a data version or
    a :func:`code_heading`."""
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
    kind = None
    if "--release" in argv:
        i = argv.index("--release")
        kind = argv[i + 1] if i + 1 < len(argv) else None
        if kind not in ("data", "code"):
            print("usage: check_release_metadata.py [--release data|code]")
            return 2
    sys.path.insert(0, os.path.join(ROOT, "src"))
    import marina_rules as mr
    errors = check(ROOT, mr.VERSION, mr.__version__, mr.dataset_digest())
    release = None
    if kind == "data":
        release = release_date(ROOT, mr.VERSION)
        if release is None:
            errors.append(f"CHANGELOG.md has no dated heading '## [{mr.VERSION}] - YYYY-MM-DD'")
    elif kind == "code" and release_date(ROOT, code_heading(mr.__version__)) is None:
        errors.append(f"CHANGELOG.md has no dated heading '## [{code_heading(mr.__version__)}] - YYYY-MM-DD'")
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
