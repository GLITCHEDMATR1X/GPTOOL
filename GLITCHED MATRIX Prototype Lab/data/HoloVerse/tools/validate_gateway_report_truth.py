"""Validate HoloVerse gateway self-test truth fields without importing Panda3D.

This is a report-contract check for the early ``main.py --gateway-self-test``
path.  It makes sure placeholders, hosted fallbacks, and issue routes do not
accidentally count as complete playable routes.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"


def _read_gateway_report() -> tuple[dict, list[str]]:
    errors: list[str] = []
    try:
        proc = subprocess.run(
            [sys.executable, str(MAIN), "--gateway-self-test"],
            cwd=str(ROOT),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=45,
        )
    except Exception as exc:
        return {}, [f"gateway-self-test-run-failed:{exc.__class__.__name__}:{exc}"]

    try:
        payload = json.loads(proc.stdout or "{}")
    except Exception as exc:
        payload = {}
        errors.append(f"gateway-self-test-json-invalid:{exc.__class__.__name__}:{exc}")

    # A non-zero self-test can be correct when the report contains real route
    # errors.  Treat it as a validator error only if the report claims it is safe.
    if proc.returncode and bool(payload.get("gateway_safe", False)):
        errors.append(f"gateway-self-test-exit-code:{proc.returncode}")
    if proc.stderr.strip():
        errors.append(f"gateway-self-test-stderr:{proc.stderr.strip()[:500]}")
    return payload, errors


def main() -> int:
    report, errors = _read_gateway_report()
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    modes = report.get("modes") if isinstance(report.get("modes"), list) else []

    placeholder_count = int(summary.get("PLACEHOLDER", 0) or 0)
    embedded_count = int(summary.get("EMBEDDED", 0) or 0)
    in_world_count = int(summary.get("IN-WORLD", 0) or 0)
    panel_count = int(summary.get("PANEL", 0) or 0)
    same_window_count = int(summary.get("SAME-WINDOW", 0) or 0)
    hosted_count = int(summary.get("HOSTED", 0) or 0)
    issue_count = int(summary.get("CHECK", 0) or 0)
    calculated_playable = embedded_count + in_world_count + panel_count + same_window_count
    calculated_expected = max(0, len(modes) - placeholder_count)

    if report.get("schema") != 2:
        errors.append(f"schema-expected-2-got-{report.get('schema')!r}")
    def report_int(key: str, default: int = -1) -> int:
        try:
            return int(report.get(key, default))
        except Exception:
            return default

    if report_int("mode_count") != len(modes):
        errors.append("mode-count-mismatch")
    if report_int("placeholder_routes") != placeholder_count:
        errors.append("placeholder-routes-mismatch")
    if report_int("hosted_fallback_routes") != hosted_count:
        errors.append("hosted-fallback-routes-mismatch")
    if report_int("issue_count") != issue_count:
        errors.append("issue-count-mismatch")
    if report_int("playable_ready_routes") != calculated_playable:
        errors.append("playable-ready-routes-mismatch")
    if report_int("expected_playable_routes") != calculated_expected:
        errors.append("expected-playable-routes-mismatch")

    gateway_safe = issue_count == 0
    gateway_playable_complete = gateway_safe and hosted_count == 0 and placeholder_count == 0 and calculated_playable >= calculated_expected
    if bool(report.get("gateway_safe", False)) != gateway_safe:
        errors.append("gateway-safe-truth-mismatch")
    if bool(report.get("gateway_playable_complete", False)) != gateway_playable_complete:
        errors.append("gateway-playable-complete-truth-mismatch")
    if bool(report.get("gateway_complete", False)) != gateway_playable_complete:
        errors.append("gateway-complete-truth-mismatch")

    result = {
        "schema": 1,
        "kind": "holoverse_gateway_report_truth_validation",
        "report_schema": report.get("schema"),
        "mode_count": len(modes),
        "expected_playable_routes": calculated_expected,
        "playable_ready_routes": calculated_playable,
        "placeholder_routes": placeholder_count,
        "hosted_fallback_routes": hosted_count,
        "issue_count": issue_count,
        "gateway_safe": gateway_safe,
        "gateway_playable_complete": gateway_playable_complete,
        "errors": errors,
        "ok": not errors,
    }
    print(json.dumps(result, indent=2))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
