# Automation (how Marina is maintained without burning people out)

> **Since 2026-10-29 scheduled jobs are local-only.** They write reports to disk and never open issues
> or PRs, push, or run networked git. Any GitHub action a report calls for is taken by a maintainer
> through the maintainer's queue. Details and launchd setup: [ops/README.md](../ops/README.md). The
> dated sections below are a historical log; where they mention jobs opening issues or PRs, that is
> how the jobs worked at the time. The log was started in Marina's previous repository (see
> [docs/history/](history/CHANGELOG-through-2026.11.02.md)).

Marina is operated day-to-day by an AI assistant acting for the maintainers. The assistant proposes; humans merge. What runs:

| cadence | job | output |
|---|---|---|
| weekly | tests, conformance, release-metadata check, and a scan of exchange / ministry / depository notice pages for rule changes in covered markets | a local report (`ops/reports/`); a human turns findings into draft records, each with the source URL, a fetched snapshot hash, and a `quote` |
| daily (after market data refresh) | `scripts/audit_bars.py` against the maintainers' full bar history | a local report listing any rule contradicted by data |
| on PR | CI: schema tests, interval overlap, sample-bar audit | green / red |
| on tag | compute and publish `dataset_sha256` in the release notes | reproducible citations |

Humans are interrupted in exactly two cases: a rule/data contradiction the assistant cannot resolve, and an external PR that changes a `verified` record.

Status (2026-10-24): CI is live; weekly scan and daily audit are being wired up and will be documented here when running. Nothing on this page is a promise of cadence; see GOVERNANCE.md.

## Status 2026-10-24 (evening)

Wired up and running on the maintainer's machine via launchd:

| job | schedule | script | what happened on first run |
|---|---|---|---|
| source watch | Mon 06:00 JST | `ops/weekly.sh` → `scripts/source_watch.py --github` | Seeded 265 listing items across 6 pages. Found 2 "drifts" that were **CDS re-render noise**, which is why hashes are now *content* hashes (text for HTML, bytes for PDF — `marina_rules.sourcehash`). Re-run: 0 drift. |
| daily audit | 16:30 JST | `ops/daily_audit.sh` → `scripts/audit_bars.py` over 5,460 securities / 9.1M bars | First run flagged 12 bars, all data-side: resumption-after-suspension, history-start adjustment artefacts, adjusted/unadjusted preclose mix. Audit hardened (gap>5d skip, recompute from prices, listing-start detection). Remaining: **1 genuine vendor defect** (`sh.688610 2024-02-28`), left red on purpose. |

Humans are interrupted by exactly two things: a `source-watch` issue (drift or a new notice hitting a rule keyword) and an `audit` issue (a rule contradicted by data). Both carry the evidence inline.

Lesson recorded: **precomputed `pctChg` columns are not trustworthy** — in the maintainers' re-adjusted dataset 1.86% of rows disagree with close/preclose by >1pp and using them inflates limit-up counts by 7.4%. (Correction 2026-10-25: the stale column was produced by the maintainers' own re-adjustment step, not by the vendor; the vendor's file agreed with its own prices.) The audit never uses them. Now `errata/E-0001`.

## 2026-10-25: the first scheduled run failed, and why

The 16:30 daily audit on 2026-10-24 exited 126 without running: launchd started `/bin/bash` on a
script that lives under `~/Documents`, and macOS folder protection denied the read
(`Operation not permitted`). Running the same script by hand works, which is exactly why this
class of failure goes unnoticed — the automation looks fine from a terminal.

Fix in use: launchd starts a binary that already has Documents access (here `/usr/local/bin/node`,
via `~/.marina-rules/run.js`) and that process spawns bash. Child processes inherit the parent's
authorisation. No system dialog needed. If you deploy the ops scripts on a Mac, either keep them
outside `~/Documents`/`~/Desktop`/`~/Downloads` or use the same launcher trick. Verified with
`launchctl kickstart`: exit 0, log written.

## 2026-10-25: ST records audited against data for the first time

The maintainers' bars now carry point-in-time `isST` (backfilled from baostock on 2026-10-24/25), so
`audit_bars.py --use-st` selects `st_main` / `st_chinext` / `st_star` on ST days instead of auditing
them against the non-ST band. First result over 9.1M bars: `st_chinext` 27,290 days / 0 violations,
`st_star` 3,448 / 0, `st_main` (post 2026-07-06, 10%) 9,920 / 0, `st_main` (5%) 170,939 / 3. The 3 are
one security (`sz.000908`, June–July 2024) whose vendor "raw" prices are in fact forward-adjusted and
rounded to 0.01 below ¥1 — against the exchange's unadjusted prices every move sits exactly on the
limit price. Rule correct, data wrong; left red like `sh.688610`. Now `errata/E-0002`: **adjusted prices rounded to 0.01 fabricate limit breaches on sub-¥1 securities; a column named `raw_close` is not evidence that it is unadjusted.**

## Releases (2026-10-25)

A version tag (`YYYY.MM.DD` or `YYYY.MM.DD.N`) triggers `.github/workflows/release.yml`: tests, conformance vectors,
a wheel with the dataset vendored inside (`scripts/vendor_data.py`), a check that the installed wheel
reports the same `dataset_digest()` as the repository, then `scripts/export_release.py` writes
`marina-rules-<v>.json`, `.sqlite`, `capabilities.json`, `decision.schema.json`,
`conformance-vectors-<v>.json` and `SHA256SUMS`. All of it is attached to the GitHub Release; the
sdist and wheel go to PyPI through trusted publishing (environment `pypi`; no token is stored).

`pip install marina-rules==<version>` is therefore self-contained and byte-pinned: the citation it
prints is the citation of the data it ships. Anyone preferring not to run Python can take the JSON or
SQLite dump; it carries the same digest.

## Releases since the split into two packages (2026-11-14)

The dataset and the code are now two distributions. `marina-rules` keeps its name and its date versions: it holds
the data (generated from `data/` into `packages/marina-rules/` by `scripts/vendor_data.py`, with the precompiled
`compiled.json`) and the module `marina_rules`, and depends on `marina-rules-core`, the code (the module
`marina_rules_core`, semantic versions, built from the repository root, no data inside).
`.github/workflows/release.yml` tells them apart by the tag: a date tag (`YYYY.MM.DD`, `YYYY.MM.DD.N`, equal to
`data/VERSION`) builds and publishes `marina-rules`, with the JSON / SQLite dumps (`marina-rules-<v>.json`, `.sqlite`)
and the other artefacts above, through the environment `pypi`, as before; a `core-vX.Y.Z` tag (equal to
`marina_rules.__version__`) builds and publishes `marina-rules-core` through the environment `pypi-core`. A data
release is checked by installing the built wheel into a clean environment with the `marina-rules-core` already on
PyPI; a code release, by installing the built wheel with the dataset built from the same checkout. Either way the
installed packages must report the repository's dataset digest and load the precompiled file without a warning.
`pip install marina-rules==<version>` stays byte-pinned for the data; the citation also names the code version that
read it. The section above describes the single package that existed before.

## 2026-10-29: scheduled jobs no longer write to GitHub

The weekly job used to `git fetch`/`pull`, push a `watch/state-DATE` branch and open/auto-merge a PR;
the daily job and `source_watch.py --github` opened issues. That is too much unattended automated
activity on a code host for a project run by one account, so all of it is gone: both jobs now test the
local checkout and write `ops/reports/YYYY-MM-DD-{daily,weekly}.md`; `watch/state.json` is updated in
place and left uncommitted; `--github` refuses to run. `tests/test_ops_no_github.py` fails if a `gh` call
or a networked git command reappears in `ops/` or the source watch. Each script takes `--dry-run`.

The launchd launcher also changed: instead of a general-purpose interpreter (`node`) holding the folder
permission, a dedicated launcher that can run only these two scripts holds it (`ops/launchd/`).
