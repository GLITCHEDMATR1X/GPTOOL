"""Minimal smoke checks for GPTOOL's repository form."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_bridge(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(ROOT / "bridge.py"), *args],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )


def test_version_reports_current_pass() -> None:
    result = run_bridge("--version")
    assert "0.6.6-pass16" in result.stdout


def test_package_audit_runs() -> None:
    result = run_bridge("package-audit", ".", "--json")
    assert "total_size_bytes" in result.stdout
