# Shared helpers for ops/*.sh. Sourced, not executed.
# Scheduled jobs are LOCAL-ONLY: they never talk to a code host and never use networked git.
# Anything that needs a code-host action is written into the report for a human to put in the
# maintainer's queue.

ops_init() {
  cd "$(dirname "$0")/.." || exit 2
  export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
  export PYTHONPATH="src${PYTHONPATH:+:$PYTHONPATH}"
  mkdir -p ops/logs ops/reports
  TODAY="$(date +%F)"
  NOW="$(date -Iseconds)"
}

# Interpreter: $MARINA_PYTHON, else this checkout's .venv, else the main checkout's .venv
# (worktrees share the main checkout's git dir; the venv lives only in the main checkout).
ops_python() {
  if [ -n "${MARINA_PYTHON:-}" ]; then echo "$MARINA_PYTHON"; return; fi
  if [ -x .venv/bin/python ]; then echo "$PWD/.venv/bin/python"; return; fi
  local common
  common="$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null)"
  if [ -n "$common" ] && [ -x "$(dirname "$common")/.venv/bin/python" ]; then
    echo "$(dirname "$common")/.venv/bin/python"; return
  fi
  echo python3
}

ops_git_line() {
  local br head dirty
  br="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo '?')"
  head="$(git rev-parse --short HEAD 2>/dev/null || echo '?')"
  if git diff --quiet 2>/dev/null && git diff --cached --quiet 2>/dev/null; then dirty="clean"; else dirty="dirty"; fi
  echo "checkout: \`$br\` @ \`$head\` ($dirty working tree)"
}
