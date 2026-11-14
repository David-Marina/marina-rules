# Governance

Marina is deliberately small and deliberately boring. Its governance is modelled on the tz database and exchange_calendars: a short list of maintainers, decisions by sources, changes in the open.

## Roles

- **Maintainers** merge pull requests, cut releases, and are the final word on `verification` levels. Current maintainers are listed in [MAINTAINERS.md](MAINTAINERS.md).
- **Contributors** are everyone who has had a PR merged. Their names stay in the git history and in release notes.

## Becoming a maintainer

Anyone who has contributed five merged records at `verified` level in a market, or who maintains the market adapter that consumes Marina in a widely used engine, may be nominated by an existing maintainer and added by consensus of the maintainers. We prefer maintainers who actually trade or research in the market they maintain.

## Decisions

- Factual disputes (what is the rule, since when) are settled by primary sources. If two official sources disagree, the record is marked `unverified` and both are cited in `notes`.
- Scope disputes (should Marina contain X) default to **no**. The scope statement in the README changes only by a documented decision recorded in `docs/decisions/`.
- Schema changes are backward compatible within a major schema version; a breaking change bumps `schema:` and ships a migration note.

## Releases

Marina is released as two packages from this one repository, the way the tz database is released apart from the code that reads it. The repository's `data/` is the only copy of the data; the data package is generated from it at release time.

- **`marina-rules-data`** — the dataset. Version numbers are dates: `YYYY.MM.DD`, and `YYYY.MM.DD.N` for a further release on the same day; the version is the file `data/VERSION`. There are no semantic versions for data; the content is the version, and the citation pins it by digest. **Never a letter suffix**: `2026.10.26b` is a *beta pre-release* under PEP 440 and `pip install` skips it by default — learned the hard way on 2026-10-25 (the letter-suffixed versions of the previous repository never reached PyPI). Git tag: the version itself (`2026.11.20`). It depends on nothing.
- **`marina-rules`** — the code (lookups, fill checker, adapters, command line, decision contract). Semantic versions from `1.0.0`: a major version for an incompatible change to the API or to the decision contract, a minor version for new functions, a patch for fixes. Git tag: `v` + the version (`v1.0.0`). It depends on `marina-rules-data` of at least `MIN_DATA_VERSION`, and reads the data formats listed in `DATA_SCHEMAS`. Before the split the `marina-rules` package was date-numbered and carried the data; PEP 440 orders those numbers above `1.0.0`, so those releases are yanked on PyPI, or `pip install marina-rules` would keep resolving to the last of them.
- **Compatibility.** A data release that needs a new data format (`data/SCHEMA`, the highest `schema:` of the data files) waits for, or ships with, a code release that reads it; the code refuses a dataset it cannot read and names the package to upgrade. A code release that changes how the data is loaded or validated increases `LOADER_REVISION` (`src/marina_rules/_precompiled.py`); a test enforces it. Until the data is rebuilt by that revision, it is read from YAML: slower, never different.
- A release is a git tag plus a GitHub release. A data release lists added / changed / re-verified records; a code release lists the changes to the code. The lists live in [CHANGELOG.md](CHANGELOG.md) (a `## [YYYY.MM.DD]` section for a data release, a `## [marina-rules X.Y.Z]` section for a code release, each required before tagging; CI checks it), and the release body is generated from it by `scripts/release_notes.py`.
- Releases are cut when there is something to release; there is no fixed cadence promised. Automated source monitoring (see `docs/automation.md`) proposes records; humans merge them.
- Scheduled jobs are local-only: they write reports on the maintainer's machine and never open issues or pull requests, push, or tag. Every action on the code host (issues, PRs, merges, pushes, releases) is taken by a human maintainer through the maintainer's queue, one at a time.
- Every data release's `dataset_sha256` is recorded in the release notes so citations can be checked without cloning.

## Succession

If the active maintainers become unreachable for 90 days, any contributor with three merged `verified` records may fork, announce the fork in an issue on this repository, and the community is encouraged to follow the fork that keeps this document. Marina must not have a bus factor of one.

## Money

There is none. Marina does not accept sponsorship that would give any party influence over its contents. Infrastructure costs are borne by maintainers. The data is CC0 and the code is MIT, forever.
