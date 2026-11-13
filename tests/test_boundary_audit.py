"""Regression gate: the independent boundary audit (tests/audit/boundary_audit.py, 2026-10-26) must stay green.

The probe expectations are the auditor's spec and are never edited to make a probe pass. Every probe must pass:
the four ``as_of`` probes were allow-listed until the bitemporal ``as_of`` parameter landed (2026.10.26.7).
"""
import json
import os
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
KNOWN_FAILING: set = set()


def _run_audit() -> dict:
    env = dict(os.environ, PYTHONPATH=os.path.join(ROOT, "src") + os.pathsep + os.environ.get("PYTHONPATH", ""))
    p = subprocess.run([sys.executable, os.path.join(ROOT, "tests", "audit", "boundary_audit.py"), ROOT],
                       capture_output=True, text=True, env=env, cwd=ROOT, timeout=300)
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout)


def test_boundary_audit():
    out = _run_audit()
    status = {t["id"]: t["status"] for t in out["tests"]}
    assert len(status) == len(out["tests"]), "duplicate probe ids"
    assert KNOWN_FAILING <= set(status), "an allow-listed probe disappeared from the audit"
    unexpected_fail = sorted(k for k, v in status.items() if v != "PASS" and k not in KNOWN_FAILING)
    unexpected_pass = sorted(k for k in KNOWN_FAILING if status[k] == "PASS")
    detail = {t["id"]: {"expected": t["expected"], "actual": t["actual"]} for t in out["tests"] if t["id"] in unexpected_fail}
    assert not unexpected_fail, f"probes failing: {json.dumps(detail, ensure_ascii=False)}"
    assert not unexpected_pass, f"allow-listed probes now pass — remove them from KNOWN_FAILING: {unexpected_pass}"
    assert out["summary"].get("PASS", 0) == 59 and not out["summary"].get("FAIL"), out["summary"]
