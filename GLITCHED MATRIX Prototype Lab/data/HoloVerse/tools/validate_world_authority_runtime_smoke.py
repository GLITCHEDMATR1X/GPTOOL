#!/usr/bin/env python3
"""Run the Panda3D default-world authority smoke test.

This validates the runtime side of the world.py authority rule: the default
HoloVerse shell should be built from world.py while main.py legacy terrain
streaming stays off. The test runs offscreen through main.py's
--world-authority-smoke-test path and reads logs/world_authority_smoke_report.json.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "logs" / "world_authority_smoke_report.json"
SCREENSHOT = ROOT / "logs" / "world_authority_smoke.png"


def _short(text: str, limit: int = 1800) -> str:
    text = text or ""
    if len(text) <= limit:
        return text
    return text[-limit:]


def main() -> int:
    errors: list[str] = []
    for path in (REPORT, SCREENSHOT):
        try:
            if path.exists():
                path.unlink()
        except Exception:
            pass

    try:
        proc = subprocess.run(
            [sys.executable, "main.py", "--world-authority-smoke-test"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=75,
        )
    except subprocess.TimeoutExpired as exc:
        result = {
            "schema": 1,
            "kind": "holoverse_world_authority_runtime_smoke_validation",
            "status": "FAIL",
            "errors": ["world authority smoke timed out"],
            "stdout_tail": _short(exc.stdout if isinstance(exc.stdout, str) else ""),
            "stderr_tail": _short(exc.stderr if isinstance(exc.stderr, str) else ""),
        }
        print(json.dumps(result, indent=2))
        return 1

    report = {}
    if REPORT.exists():
        try:
            report = json.loads(REPORT.read_text(encoding="utf-8"))
        except Exception as exc:
            errors.append(f"report json unreadable: {exc}")
    else:
        errors.append("logs/world_authority_smoke_report.json missing")

    if proc.returncode != 0:
        errors.append(f"smoke command exited {proc.returncode}")
    if isinstance(report, dict):
        if report.get("status") != "PASS":
            errors.append(f"report status is {report.get('status')!r}")
        if report.get("world_py_source_active") is not True:
            errors.append("world_py_source_active is not true")
        if report.get("legacy_main_world_active") is not False:
            errors.append("legacy_main_world_active is not false")
        if report.get("should_stream_legacy_default") is not False:
            errors.append("should_stream_legacy_default is not false")
        if int(report.get("main_terrain_chunks", -1) or 0) != 0:
            errors.append("main_terrain_chunks is not zero")
        audit = report.get("source_surface_audit", {}) if isinstance(report.get("source_surface_audit", {}), dict) else {}
        if int(audit.get("active_surface_authority_count", 0) or 0) <= 0:
            errors.append("source surface audit did not report active surfaces")
        if int(audit.get("duplicate_surface_owner_keys", 0) or 0) != 0:
            errors.append("source surface audit found duplicate owner keys")
    else:
        errors.append("report is not a JSON object")

    result = {
        "schema": 1,
        "kind": "holoverse_world_authority_runtime_smoke_validation",
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "command_returncode": proc.returncode,
        "report_path": str(REPORT),
        "screenshot_path": str(SCREENSHOT) if SCREENSHOT.exists() else "",
        "world_py_source_active": bool(report.get("world_py_source_active", False)) if isinstance(report, dict) else False,
        "main_terrain_chunks": int(report.get("main_terrain_chunks", -1) or 0) if isinstance(report, dict) else -1,
        "source_bridge_status": str(report.get("source_bridge_status", "")) if isinstance(report, dict) else "",
        "stdout_tail": _short(proc.stdout),
        "stderr_tail": _short(proc.stderr),
    }
    print(json.dumps(result, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
