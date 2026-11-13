#!/bin/bash
# Build the launcher and render the two launchd plists into a staging directory.
# Does NOT install, load or unload anything — that is a human step (see ops/README.md).
#
#   ops/launchd/build.sh REPO BARS [STAGE]
#     REPO   absolute path of the checkout the jobs run (its ops/*.sh are executed)
#     BARS   absolute path of the private bars directory (MARINA_BARS for the daily audit)
#     STAGE  output directory (default: $HOME/.marina-rules/stage)
set -euo pipefail
[ $# -ge 2 ] || { echo "usage: $0 REPO BARS [STAGE]" >&2; exit 64; }
REPO="$(cd "$1" && pwd)"; BARS="$2"; STAGE="${3:-$HOME/.marina-rules/stage}"
HERE="$(cd "$(dirname "$0")" && pwd)"
HELPER_DIR="$HOME/.marina-rules/bin"; HELPER="$HELPER_DIR/marina-ops"
case "$REPO$BARS" in *'"'*|*'&'*|*'<'*) echo "paths must not contain \" & <" >&2; exit 64 ;; esac
mkdir -p "$STAGE"
cc -O2 -Wall -DMARINA_REPO="\"$REPO\"" -o "$STAGE/marina-ops" "$HERE/marina-ops.c"
codesign -s - -i org.marina-rules.ops -f "$STAGE/marina-ops" 2>/dev/null

render() {  # render JOB EXTRA_ENV SCHEDULE
  local tmp; tmp="$(mktemp)"
  sed -e "s|@JOB@|$1|g" -e "s|@HELPER@|$HELPER|g" -e "s|@HOME@|$HOME|g" -e "s|@REPO@|$REPO|g" \
      "$HERE/job.plist.in" > "$tmp"
  EXTRA_ENV="$2" SCHEDULE="$3" awk '{ if ($0=="@EXTRA_ENV@\t</dict>") { printf "%s\n\t</dict>\n", ENVIRON["EXTRA_ENV"] }
            else if ($0=="@SCHEDULE@\t</dict>") { printf "%s\n\t</dict>\n", ENVIRON["SCHEDULE"] }
            else print }' "$tmp" | grep -v '^$' > "$STAGE/com.marina-rules.$1.plist"
  rm -f "$tmp"
  plutil -lint "$STAGE/com.marina-rules.$1.plist" >/dev/null
}
render daily  "$(printf '\t\t<key>MARINA_BARS</key>\n\t\t<string>%s</string>\n' "$BARS")" \
              "$(printf '\t\t<key>Hour</key>\n\t\t<integer>16</integer>\n\t\t<key>Minute</key>\n\t\t<integer>30</integer>\n')"
render weekly "" \
              "$(printf '\t\t<key>Weekday</key>\n\t\t<integer>1</integer>\n\t\t<key>Hour</key>\n\t\t<integer>6</integer>\n\t\t<key>Minute</key>\n\t\t<integer>0</integer>\n')"
echo "staged in $STAGE:"; ls -1 "$STAGE"
echo "helper will be installed as $HELPER (see ops/README.md for the install steps)"
