# Governance

Marina is deliberately small and deliberately boring. Its governance is modelled on the tz database and exchange_calendars: a short list of maintainers, decisions by sources, changes in the open.

## Roles

- **Maintainers** merge pull requests, cut releases, and are the final word on `verification` levels. Current maintainers are listed in [MAINTAINERS.md](MAINTAINERS.md).
- **Contributors** are everyone who has had a PR merged. Their names stay in the git history and in release notes.

## Becoming a maintainer

Anyone who has contributed five merged records at `verified` level in a market, or who maintains the market adapter that consumes Marina in a widely used engine, may be nominated by an existing maintainer and added by consensus of the maintainers. We prefer maintainers who actually trade or research in the market they maintain.

## Decisions

- Factual disputes (what is the rule, since when) are settled by primary sources. If two official sources disagree, the record is marked `unverified` and both are cited in `notes`.
- Scope disputes (should Marina contain X) default to **no**. The scope statement in the README changes only by a documented decision, recorded in the changelog entry of the release that makes it.
- Schema changes are backward compatible within a major schema version; a breaking change bumps `schema:` and ships a migration note.

## Releases

Marina is released as two packages from this one repository, the way the tz database is released apart from the code that reads it. The repository's `data/` is the only copy of the data; the packages are generated from it at release time.

- **`marina-rules`** — the dataset, and the package users install. It holds the rule files (with their precompiled form) and the module `marina_rules`, which forwards to the code; it depends on `marina-rules-core`. Version numbers are dates: `YYYY.MM.DD`, and `YYYY.MM.DD.N` for a second release on the same day; the version is the file `data/VERSION`. There are no semantic versions for data; the content is the version, and the citation pins it by digest. **Never a letter suffix**: `2026.10.26b` is a *beta pre-release* under PEP 440 and `pip install` skips it by default — learned the hard way on 2026-10-25 (the letter-suffixed versions of the previous repository never reached PyPI). The releases now on PyPI start at `2026.11.13`, the first from this repository; the earlier `2026.10.26.x` releases were removed from PyPI and are described in `docs/history/`. Releases up to and including `2026.11.16` carried the code as well; they stay on PyPI like every other release. Git tag: the version itself (`2026.11.23`).
- **`marina-rules-core`** — the code (lookups, fill checker, adapters, command line, decision contract), as the module `marina_rules_core`. Semantic versions from `1.0.0`: a major version for an incompatible change to the API or to the decision contract, a minor version for new functions, a patch for fixes. It is released when a change is ready, not on a schedule. Git tag: `core-v` + the version (`core-v1.0.0`). It reads data of at least `MIN_DATA_VERSION`, in the data formats listed in `DATA_SCHEMAS`, and does not depend on `marina-rules`.
- **Compatibility.** `marina-rules` requires a range of `marina-rules-core` (`packages/marina-rules/pyproject.toml`; CI checks that the current code is inside it). A data release that needs new code (a new data format in `data/SCHEMA`, the highest `schema:` of the data files) raises the lower bound, and is tagged only after that code release is on PyPI; the code refuses a dataset it cannot read and names the package to upgrade. A code release that changes how the data is loaded or validated increases `LOADER_REVISION` (`src/marina_rules_core/_precompiled.py`); a test enforces it. Until the data is rebuilt by that revision, it is read from YAML: slower, never different.
- **The module stays in `marina-rules`.** `marina_rules/` was part of `marina-rules` from the first release, so it stays there (as a forwarding module), with the commands `marina-rules` and `marina-check`; the code lives under another name, `marina_rules_core`. Moving those files to another package would make `pip install -U marina-rules` from a release up to 2026.11.16 delete them (pip removes the old release's files after installing the new dependency).
- A release is a git tag plus a GitHub release. A data release lists added / changed / re-verified records; a code release lists the changes to the code. The lists live in [CHANGELOG.md](CHANGELOG.md) (a `## [YYYY.MM.DD]` section for a data release, a `## [marina-rules-core X.Y.Z]` section for a code release, each required before tagging; CI checks it), and the release body is generated from it by `scripts/release_notes.py`.
- There is a data release slot every Monday (Asia/Tokyo). A data release is cut when a rule changed, a record was corrected or the tracked dates advanced; a week with nothing to release is skipped. A published version of either package is never deleted: a defect found in one is fixed in a later release, whose changelog entry names the defect and what to re-run. Automated source monitoring (see `docs/automation.md`) proposes records; humans merge them.
- Scheduled jobs are local-only: they write reports on the maintainer's machine and never open issues or pull requests, push, or tag. Every action on the code host (issues, PRs, merges, pushes, releases) is taken by a human maintainer through the maintainer's queue, one at a time.
- Every data release's `dataset_sha256` is recorded in the release notes so citations can be checked without cloning.

## Succession

If the active maintainers become unreachable for 90 days, any contributor with three merged `verified` records may fork, announce the fork in an issue on this repository, and the community is encouraged to follow the fork that keeps this document. Marina must not have a bus factor of one.

## Money

There is none. Marina does not accept sponsorship that would give any party influence over its contents. Infrastructure costs are borne by maintainers. The data is CC0 and the code is MIT, forever.
