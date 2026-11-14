"""Print the GitHub release body for one release tag, taken from CHANGELOG.md.

    python scripts/release_notes.py 2026.11.23 > notes.md     # a data release (marina-rules, the dataset)
    python scripts/release_notes.py core-v1.0.0 > notes.md    # a code release (marina-rules-core)

Data release: the citation of the data (``rules: marina-rules@<version> sha256:<16 hex>``; ``mr.citation()``
appends the code version that reads it), the full dataset_sha256, then the CHANGELOG section ``## [<version>]``.
The digest is computed from the data at that version: the working tree when the version equals data/VERSION (the
release workflow runs on the tag checkout), otherwise the git tag of that name.
Code release: the upgrade line and the oldest dataset it reads, then the section ``## [marina-rules-core X.Y.Z]``.
Exit 1 if CHANGELOG.md has no section for the release. Releases before 2026.11.13 are in
docs/history/CHANGELOG-through-2026.11.02.md (pass its path to ``changelog_section``).
"""
from __future__ import annotations

import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))

HEADING = re.compile(r"^## \[(?P<v>[^\]]+)\]", re.M)
SECTION_END = re.compile(r"^## ", re.M)   # any level-2 heading ends a section (e.g. "## Earlier releases")


def changelog_section(version: str, path: str = os.path.join(ROOT, "CHANGELOG.md")) -> str | None:
    """The body under ``## [version]`` up to the next level-2 heading, or None if absent."""
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    for m in HEADING.finditer(text):
        if m.group("v") == version:
            nxt = SECTION_END.search(text, m.end())
            return text[m.start():nxt.start() if nxt else len(text)].strip()
    return None


def unwrap(md: str) -> str:
    """Join hard-wrapped continuation lines: GitHub renders a release body's single newlines as breaks."""
    out: list[str] = []
    fence = False
    for line in md.split("\n"):
        if line.startswith("```"):
            fence = not fence
            out.append(line); continue
        cont = (not fence and out and out[-1].strip() and not out[-1].startswith(("#", "```"))
                and line.strip() and not line.lstrip().startswith(("- ", "* ", "#", "|", "```"))
                and not re.match(r"\s*\d+\. ", line))
        if cont:
            out[-1] = out[-1].rstrip() + " " + line.strip()
        else:
            out.append(line)
    return "\n".join(out)


CODE_TAG = re.compile(r"^core-v(?P<v>\d+\.\d+\.\d+)$")


def digest_for(version: str) -> str:
    import marina_rules_core as mr
    if version == mr.DATA_VERSION:
        return mr.dataset_digest()
    from marina_rules_core.diff import load_version  # same hash as dataset_digest(), read from the git tag
    return load_version(version)["digest"]


def release_notes(tag: str) -> str:
    code = CODE_TAG.match(tag)
    name = f"marina-rules-core {code.group('v')}" if code else tag
    section = changelog_section(name)
    if section is None:
        raise SystemExit(f"CHANGELOG.md has no section '## [{name}]'")
    body = section.split("\n", 1)[1].strip() if "\n" in section else ""
    if code:
        import marina_rules_core as mr
        head = (f"**Upgrade:** `pip install -U marina-rules-core` (this is the code; `pip install marina-rules` installs "
                f"it with the data). Reads the dataset marina-rules {mr.MIN_DATA_VERSION} or later (data schema "
                f"{', '.join(str(x) for x in mr.DATA_SCHEMAS)}).\n\n")
    else:
        dg = digest_for(tag)
        head = (f"**Upgrade:** `pip install -U marina-rules`\n\n**Cite it:**\n```\nrules: marina-rules@{tag} sha256:{dg[:16]}\n```\n"
                f"(`mr.citation()` adds the code version that read it: `code: marina-rules-core@<version>`.)\n\n"
                f"**dataset_sha256:** `{dg}`\n\n")
    return (f"{head}{unwrap(body)}\n\n"
            f"Full history: [CHANGELOG.md](https://github.com/David-Marina/marina-rules/blob/main/CHANGELOG.md)\n")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: python scripts/release_notes.py <data version | core-vX.Y.Z>")
    sys.stdout.write(release_notes(sys.argv[1]))
