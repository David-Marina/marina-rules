#!/bin/bash
# Marina weekly maintenance — run by launchd (Mon 06:00 JST) or by hand.
# LOCAL-ONLY: tests whatever is checked out locally (no fetch, no pull), never edits data, never contacts a
# code host. Output: ops/reports/YYYY-MM-DD-weekly.md (+ ops/logs/weekly-YYYY-MM-DD.log).
#
#   ops/weekly.sh [--dry-run]
#
# watch/state.json (the listing snapshot the next run diffs against) is updated in place and left
# uncommitted; the report says so. Committing it — and any code-host action — is a human step via the
# maintainer's queue. --dry-run runs every step but does not write watch/state.json.
set -uo pipefail
source "$(dirname "$0")/lib.sh"
ops_init
DRY=0; [ "${1:-}" = "--dry-run" ] && DRY=1
PY="$(ops_python)"
LOG="ops/logs/weekly-$TODAY.log"
REPORT="ops/reports/$TODAY-weekly.md"
FAIL=0

step() {  # step "title" cmd... — run, append the tail to the report, remember failures
  local title="$1"; shift
  local out rc
  out=$("$@" 2>&1); rc=$?
  { echo "== $title (exit $rc) =="; echo "$out"; } >> "$LOG"
  { echo "## $title — $([ $rc -eq 0 ] && echo OK || echo "FAILED (exit $rc)")"; echo; echo '```'
    echo "$out" | tail -"${TAIL:-5}"; echo '```'; echo; } >> "$REPORT"
  [ $rc -eq 0 ] || FAIL=1
}

: > "$LOG"
{
  echo "# Marina weekly maintenance — $TODAY"
  echo
  if [ $DRY -eq 1 ]; then echo "**DRY RUN** (manual verification; watch/state.json is not written)."; echo; fi
  echo "- started: $NOW"
  echo "- $(ops_git_line)"
  echo "- python: \`$PY\`"
  echo "- log: \`$LOG\`"
  echo
} > "$REPORT"

TAIL=2 step "tests"                 "$PY" -m pytest -q
TAIL=3 step "conformance vectors"   "$PY" conformance/run.py
TAIL=3 step "release metadata"      "$PY" scripts/check_release_metadata.py
TAIL=3 step "sample-bar audit"      "$PY" scripts/audit_bars.py data/samples/cn_bars
# Listing diff only (--no-drift). Re-hashing every cited source is ~1,000 unthrottled requests to exchange
# websites at the current dataset size; run it by hand, throttled, before a release instead.
if [ $DRY -eq 1 ]; then
  TAIL=200 step "source watch"      "$PY" scripts/source_watch.py --no-drift --no-save-state
else
  TAIL=200 step "source watch"      "$PY" scripts/source_watch.py --no-drift
fi

{
  echo "## Listing snapshot"
  echo
  if [ $DRY -eq 1 ]; then
    echo "Dry run: \`watch/state.json\` not written."
  elif git diff --quiet -- watch/state.json 2>/dev/null; then
    echo "\`watch/state.json\` unchanged."
  else
    echo "\`watch/state.json\` updated in place and **left uncommitted** (scheduled jobs make no commits and"
    echo "push nothing). The next run diffs against this file either way. To publish the snapshot, commit it"
    echo "and add the push to the maintainer's queue."
  fi
  echo
  echo "## Summary"
  echo
  if [ $FAIL -eq 0 ]; then echo "All steps passed."; else echo "**At least one step failed** — see above and \`$LOG\`."; fi
  echo "Anything that needs a public issue, PR or release goes into the maintainer's queue by hand."
  echo
  echo "- finished: $(date -Iseconds)"
} >> "$REPORT"

echo "report: $REPORT"
grep -E '^## .* — (OK|FAILED)' "$REPORT"; sed -n '/^## Summary/,/^- finished/p' "$REPORT" | sed -n 3p
exit $FAIL
