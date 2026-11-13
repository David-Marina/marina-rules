# ops/ — scheduled maintenance jobs

**Scheduled jobs are local-only.** They never contact a code host (no issues, PRs, pushes, releases) and
never run networked git (`fetch`, `pull`, `push`, `ls-remote`, `clone`); they test whatever is checked
out locally. Their output is a Markdown report on disk. Any GitHub action a report calls for is done by
a human maintainer, through the maintainer's queue. `tests/test_ops_no_github.py` enforces this.

| job | when | script | report | log |
|---|---|---|---|---|
| daily audit | 16:30 JST | `ops/daily_audit.sh` (needs `MARINA_BARS`) | `ops/reports/YYYY-MM-DD-daily.md` | `ops/logs/daily-YYYY-MM-DD.log` |
| weekly | Mon 06:00 JST | `ops/weekly.sh` | `ops/reports/YYYY-MM-DD-weekly.md` | `ops/logs/weekly-YYYY-MM-DD.log` |

`ops/reports/` and `ops/logs/` are git-ignored.

- **daily**: `scripts/audit_bars.py MARINA_BARS --complete-from-listing --use-st`. Violations are a
  finding in the report (exit 0); exit 2 means misconfigured (no `MARINA_BARS` / no bar files).
- **weekly**: pytest, conformance vectors, release-metadata check, sample-bar audit, then
  `scripts/source_watch.py`. It updates `watch/state.json` in place and **leaves it uncommitted**
  (scheduled jobs make no commits — a commit on whatever branch happens to be checked out would be a
  surprise, and pushing it is not allowed anyway). The next run diffs against the file regardless.
  Exit 1 if any step failed.
- `--dry-run` on either script runs every step and writes the report (marked DRY RUN); the weekly dry
  run does not write `watch/state.json`.
- Python: `$MARINA_PYTHON`, else `./.venv`, else the main checkout's `.venv` (for git worktrees).
- `scripts/source_watch.py --github` is disabled: it refuses and exits non-zero.

## Running under launchd on macOS

launchd-started `/bin/bash` cannot read a script under `~/Documents` (or `~/Desktop`, `~/Downloads`):
macOS privacy protection (TCC) denies it with `Operation not permitted`, while the same script works
from a terminal (the terminal app holds the permission). The fix used here is least-privilege:

- `ops/launchd/marina-ops.c` is a ~40-line launcher with the checkout path compiled in. It accepts only
  `daily` or `weekly` (plus `--dry-run`), spawns `/bin/bash` on that one script and waits. Because the
  launcher stays the parent ("responsible process"), a Files & Folders / Full Disk Access grant given
  to *it* covers the bash child, and nothing else on the machine gains access.
- Rejected alternatives: granting `/bin/bash` (or `node`, `python`) access — every script run by that
  interpreter would inherit it; relocating a working copy outside `~/Documents` — the private bars and
  the `.venv` would also need to move or be duplicated, and the copy can drift from what is tested.

`ops/launchd/build.sh REPO BARS [STAGE]` compiles and ad-hoc signs the launcher and renders both plists
into a staging directory (default `~/.marina-rules/stage`). It installs nothing. Installing is a human
step:

```sh
REPO=/abs/path/to/marina-rules          # the checkout the jobs should run
BARS=/abs/path/to/bars                  # private bars directory for the daily audit
ops/launchd/build.sh "$REPO" "$BARS"
mkdir -p ~/.marina-rules/bin
install -m 755 ~/.marina-rules/stage/marina-ops ~/.marina-rules/bin/marina-ops
# System Settings → Privacy & Security → Full Disk Access → "+" → ⌘⇧G ~/.marina-rules/bin/marina-ops
#   (Full Disk Access is the only list that accepts an arbitrary binary; the launcher can still only
#    run the two scripts compiled into it.)
cp ~/.marina-rules/stage/com.marina-rules.{daily,weekly}.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.marina-rules.daily.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.marina-rules.weekly.plist
launchctl kickstart -k gui/$(id -u)/com.marina-rules.weekly   # verify: report appears in ops/reports/
```

Rebuilding the launcher changes its code hash; re-grant access after reinstalling it.
