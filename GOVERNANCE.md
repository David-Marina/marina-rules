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

- Version numbers are dates: `YYYY.MM.DD`, and `YYYY.MM.DD.N` for a second release on the same day. There are no semantic versions; the content is the version. **Never a letter suffix**: `2026.10.26b` is a *beta pre-release* under PEP 440 and `pip install` skips it by default — learned the hard way on 2026-10-25 (the letter-suffixed versions of the previous repository never reached PyPI; the PyPI line starts at `2026.10.26.1`).
- A release is a git tag plus a GitHub release listing added / changed / re-verified records. The list lives in [CHANGELOG.md](CHANGELOG.md) (a `## [VERSION]` section is required before tagging; CI checks it), and the release body is generated from it by `scripts/release_notes.py`.
- There is a release slot every Monday (Asia/Tokyo). A release is cut when a rule changed, a record was corrected, the tracked dates advanced or code is ready; a week with nothing to release is skipped. A published version is never deleted: one found to give wrong answers is yanked on PyPI (a pin still installs it) and the fix is released. Automated source monitoring (see `docs/automation.md`) proposes records; humans merge them.
- Scheduled jobs are local-only: they write reports on the maintainer's machine and never open issues or pull requests, push, or tag. Every action on the code host (issues, PRs, merges, pushes, releases) is taken by a human maintainer through the maintainer's queue, one at a time.
- Every release's `dataset_sha256` is recorded in the release notes so citations can be checked without cloning.

## Succession

If the active maintainers become unreachable for 90 days, any contributor with three merged `verified` records may fork, announce the fork in an issue on this repository, and the community is encouraged to follow the fork that keeps this document. Marina must not have a bus factor of one.

## Money

There is none. Marina does not accept sponsorship that would give any party influence over its contents. Infrastructure costs are borne by maintainers. The data is CC0 and the code is MIT, forever.
