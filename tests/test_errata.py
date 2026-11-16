"""Errata detectors: reproduce the defect on the bundled sample (exit non-zero), pass a clean day (exit 0)."""
from __future__ import annotations

import os
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
E3 = os.path.join(ROOT, "errata", "E-0003")


def _run(*args):
    return subprocess.run([sys.executable, os.path.join(E3, "reproduce.py"), *args],
                          capture_output=True, text=True)


def test_e0003_flags_600715():
    r = _run(os.path.join(E3, "sh.600715_unadjusted_baostock_2024-12.csv"), "2024-12-16", "2205000000/1854853500")
    assert r.returncode == 1, r.stdout + r.stderr
    assert "2.12" in r.stdout and "1.12" in r.stdout


def test_e0003_flags_000908():
    r = _run(os.path.join(E3, "sz.000908_unadjusted_baostock_2026-03.csv"), "2026-03-11", "1")
    assert r.returncode == 1, r.stdout + r.stderr
    assert "4.36" in r.stdout and "3.19" in r.stdout


def test_e0003_clean_day_passes():
    r = _run(os.path.join(E3, "sh.600715_unadjusted_baostock_2024-12.csv"), "2024-12-17", "0")
    assert r.returncode == 0, r.stdout + r.stderr
