#!/bin/bash
# Marina daily audit — rules × the maintainers' full bar history (private data; maintainer's machine only).
# LOCAL-ONLY: writes ops/reports/YYYY-MM-DD-daily.md and ops/logs/daily-YYYY-MM-DD.log and never contacts a
# code host. A contradiction is a finding in the report; a human decides whether it goes into the
# maintainer's queue.
#
#   MARINA_BARS=/path/to/bars ops/daily_audit.sh [--dry-run]
#
# --dry-run runs exactly the same steps (this job has no side effects besides the report and log) and
# marks the report as a manual run.
# Exit: 0 = report written (violations, if any, are listed in it); 2 = configuration error
# (MARINA_BARS unset / no bar files); anything else = the audit crashed.
set -uo pipefail
source "$(dirname "$0")/lib.sh"
ops_init
DRY=0; [ "${1:-}" = "--dry-run" ] && DRY=1
PY="$(ops_python)"
LOG="ops/logs/daily-$TODAY.log"
REPORT="ops/reports/$TODAY-daily.md"

{
  echo "# Marina daily audit — $TODAY"
  echo
  if [ $DRY -eq 1 ]; then echo "**DRY RUN** (manual verification; same steps as the scheduled run)."; echo; fi
  echo "- started: $NOW"
  echo "- $(ops_git_line)"
  echo "- python: \`$PY\`"
} > "$REPORT"

if [ -z "${MARINA_BARS:-}" ]; then
  echo "- result: **CONFIG ERROR** — MARINA_BARS is not set (set it in the launchd plist or the shell)." >> "$REPORT"
  echo "MARINA_BARS not set" > "$LOG"
  echo "report: $REPORT"; tail -1 "$REPORT"; exit 2
fi

OUT=$("$PY" scripts/audit_bars.py "$MARINA_BARS" --complete-from-listing --use-st 2>&1); RC=$?
echo "$OUT" > "$LOG"

{
  case $RC in
    0) echo "- result: **OK** — no rule contradicted by data." ;;
    1) echo "- result: **VIOLATIONS** — a rule is contradicted by data (either the rule or the data is wrong)." ;;
    2) echo "- result: **CONFIG ERROR** — the audit found no bar files (exit 2)." ;;
    *) echo "- result: **AUDIT FAILED** — exit $RC; see the log." ;;
  esac
  echo "- log: \`$LOG\`"
  echo
  echo "## Rules with violations"
  echo
  echo '```'
  # header (citation), then every rule row whose violation count is non-zero, with its examples
  echo "$OUT" | awk 'NR==1 {print; next}
                     /^ +e\.g\./ {if (show) print; next}
                     {show = 0}
                     NF >= 4 && $2 ~ /^[0-9,]+$/ && $3 ~ /^[0-9,]+$/ && $3 != "0" {show = 1; print}'
  echo '```'
  echo
  echo "## Audit output (last 40 lines)"
  echo
  echo '```'
  echo "$OUT" | tail -40
  echo '```'
  echo
  echo "Known, accepted data-side reds are documented in \`errata/\`. Anything new that needs a public issue or"
  echo "PR goes into the maintainer's queue by hand; this job never contacts a code host."
  echo
  echo "- finished: $(date -Iseconds)"
} >> "$REPORT"

echo "report: $REPORT"
tail -3 "$LOG"
case $RC in 0|1) exit 0 ;; *) exit "$RC" ;; esac
