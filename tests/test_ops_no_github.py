"""Scheduled jobs are local-only: no code-host CLI and no networked git in ops/ or the source watch.

Any GitHub action goes through the maintainer's queue by hand (docs/automation.md, ops/README.md).
"""
from __future__ import annotations

import glob
import os
import re
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
FILES = sorted(glob.glob(os.path.join(ROOT, "ops", "*.sh"))
               + glob.glob(os.path.join(ROOT, "ops", "launchd", "*"))
               + [os.path.join(ROOT, "scripts", "source_watch.py")])

# `gh` as a command (shell word or a Python argv element), and git subcommands that touch a remote.
GH = re.compile(r"""(?:^|[\s;&|(`$]|["'\[,])gh(?:["']?\s*,|\s)""")
NET_GIT = re.compile(r"""\bgit\b(?:\s+-\S+(?:\s+\S+)?)*\s+(fetch|pull|push|ls-remote|clone)\b"""
                     r"""|["']git["']\s*,(?:\s*["'][^"']*["']\s*,)*?\s*["'](fetch|pull|push|ls-remote|clone)["']""")


def _code_lines(path: str):
    with open(path, encoding="utf-8", errors="replace") as fh:
        for n, line in enumerate(fh, 1):
            stripped = line.lstrip()
            if stripped.startswith("#") or stripped.startswith("//") or stripped.startswith("*"):
                continue  # comments may explain the rule; code may not break it
            yield n, line


def test_files_exist():
    assert any(p.endswith("daily_audit.sh") for p in FILES)
    assert any(p.endswith("weekly.sh") for p in FILES)


def test_no_gh_or_networked_git():
    hits = []
    for p in FILES:
        for n, line in _code_lines(p):
            if GH.search(line) or NET_GIT.search(line):
                hits.append(f"{os.path.relpath(p, ROOT)}:{n}: {line.strip()}")
    assert not hits, "scheduled jobs must not call gh or networked git:\n" + "\n".join(hits)


def test_patterns_catch_the_old_calls():
    bad = ['gh issue create --title "x"', "  git fetch -q origin main && git pull -q --ff-only",
           "git push -q -u origin HEAD", 'subprocess.run(["gh", "issue", "list"])',
           'subprocess.run(["git", "push", "origin"])', "git -C /tmp/x ls-remote origin", "git clone url"]
    for line in bad:
        assert GH.search(line) or NET_GIT.search(line), line
    ok = ["git diff --quiet -- watch/state.json", "git rev-parse --short HEAD", "high-level",
          'print("weigh this")']
    for line in ok:
        assert not (GH.search(line) or NET_GIT.search(line)), line


def test_source_watch_github_flag_refuses():
    r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "source_watch.py"), "--github"],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode != 0
    assert "disabled: GitHub writes are not allowed from scheduled jobs" in r.stderr
