#!/usr/bin/env python3
"""Run the HoloVerse runtime integration smoke set.

This pass validates the player-facing runtime path without adding content:
- gateway route truth
- default world authority runtime proof
- HoloCore direct input/menu ownership proof
- Etch-Line same-window adapter proof

Each smoke writes its own report/screenshot; this tool aggregates
those results into logs/runtime_integration_smoke_report.json.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = ROOT / "logs"
REPORT = LOG_DIR / "runtime_integration_smoke_report.json"


def _short(text: str | bytes | None, limit: int = 1800) -> str:
    if isinstance(text, bytes):
        try:
            text = text.decode("utf-8", "replace")
        except Exception:
            text = repr(text)
    text = text or ""
    if len(text) <= limit:
        return text
    return text[-limit:]


def _load_json(path: Path) -> dict[str, Any]:
    try:
        if path.exists() and path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
    except Exception:
        pass
    return {}


def _run(name: str, args: list[str], *, cwd: Path = ROOT, timeout: int = 90, env: dict[str, str] | None = None) -> dict[str, Any]:
    started = time.monotonic()
    try:
        proc = subprocess.run(
            [sys.executable, *args],
            cwd=cwd,
            text=True,
            capture_output=True,
            timeout=timeout,
            env=env,
        )
        return {
            "name": name,
            "args": [sys.executable, *args],
            "cwd": str(cwd),
            "returncode": int(proc.returncode),
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "stdout_tail": _short(proc.stdout),
            "stderr_tail": _short(proc.stderr),
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "name": name,
            "args": [sys.executable, *args],
            "cwd": str(cwd),
            "returncode": 124,
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "stdout_tail": _short(exc.stdout),
            "stderr_tail": _short(exc.stderr),
            "timeout": True,
        }
    except Exception as exc:
        return {
            "name": name,
            "args": [sys.executable, *args],
            "cwd": str(cwd),
            "returncode": 125,
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "stdout_tail": "",
            "stderr_tail": f"{exc.__class__.__name__}:{exc}",
            "exception": True,
        }


def _image_ok(path: Path) -> bool:
    try:
        return path.exists() and path.is_file() and path.stat().st_size > 2048
    except Exception:
        return False


def main() -> int:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    for path in (
        ROOT / "logs" / "mode_gateway_self_test.json",
        ROOT / "logs" / "world_authority_smoke_report.json",
        ROOT / "logs" / "world_authority_smoke.png",
        ROOT / "HoloCore" / "logs" / "holocore_integration_smoke_report.json",
        ROOT / "HoloCore" / "logs" / "holocore_integration_smoke.png",
        ROOT / "logs" / "etchline_same_window_contract_report.json",
        ROOT / "logs" / "etchline_same_window_smoke.png",
    ):
        try:
            if path.exists():
                path.unlink()
        except Exception:
            pass

    env = dict(os.environ)
    env.setdefault("MATRIX_GAME_WIDTH", "1280")
    env.setdefault("MATRIX_GAME_HEIGHT", "720")
    env.setdefault("MATRIX_GAME_BORDERED_FULLSCREEN", "0")
    env.setdefault("MATRIX_GAME_BORDERLESS", "0")
    env.setdefault("MATRIX_GAME_FULLSCREEN", "0")

    runs: list[dict[str, Any]] = []
    runs.append(_run("gateway_truth", ["tools/validate_gateway_report_truth.py"], timeout=45, env=env))
    runs.append(_run("world_authority_runtime", ["tools/validate_world_authority_runtime_smoke.py"], timeout=100, env=env))
    runs.append(_run("holocore_direct_input", ["main.py", "--integration-smoke"], cwd=ROOT / "HoloCore", timeout=75, env=env))
    runs.append(_run("etchline_same_window", ["tools/validate_etchline_same_window_contract.py"], timeout=100, env=env))

    gateway_report = _load_json(ROOT / "logs" / "mode_gateway_self_test.json")
    world_report = _load_json(ROOT / "logs" / "world_authority_smoke_report.json")
    holocore_report = _load_json(ROOT / "HoloCore" / "logs" / "holocore_integration_smoke_report.json")
    etch_report = _load_json(ROOT / "logs" / "etchline_same_window_contract_report.json")

    screenshots = {
        "world_authority": str(ROOT / "logs" / "world_authority_smoke.png"),
        "holocore": str(ROOT / "HoloCore" / "logs" / "holocore_integration_smoke.png"),
        "etch_line": str(ROOT / "logs" / "etchline_same_window_smoke.png"),
    }
    screenshot_status = {key: _image_ok(Path(value)) for key, value in screenshots.items()}

    errors: list[str] = []
    for run in runs:
        if int(run.get("returncode", 1)) != 0:
            errors.append(f"{run.get('name')}-exit-{run.get('returncode')}")
    if gateway_report.get("gateway_safe") is not True:
        errors.append("gateway-safe-not-true")
    if gateway_report.get("gateway_playable_complete") is not True:
        errors.append("gateway-playable-complete-not-true")
    if world_report.get("status") != "PASS":
        errors.append("world-authority-report-not-pass")
    if world_report.get("legacy_main_world_active") is not False:
        errors.append("legacy-main-world-active")
    if holocore_report.get("status") != "PASS":
        errors.append("holocore-report-not-pass")
    if holocore_report.get("direct_input_owned_by_holocore") is not True:
        errors.append("holocore-direct-input-not-owned")
    if etch_report.get("status") != "PASS":
        errors.append("etchline-same-window-report-not-pass")
    if not all(screenshot_status.values()):
        errors.append("one-or-more-mode-screenshots-missing")

    route_summary = gateway_report.get("summary", {}) if isinstance(gateway_report.get("summary", {}), dict) else {}
    report = {
        "schema": 1,
        "kind": "holoverse_runtime_integration_smoke",
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "route_summary": route_summary,
        "gateway_safe": bool(gateway_report.get("gateway_safe", False)),
        "gateway_playable_complete": bool(gateway_report.get("gateway_playable_complete", False)),
        "world_py_source_active": bool(world_report.get("world_py_source_active", False)),
        "legacy_main_world_active": bool(world_report.get("legacy_main_world_active", True)),
        "holocore_gate_mode_count": int(holocore_report.get("gate_mode_count", 0) or 0),
        "holocore_gate_panel_visible_at_capture": bool(holocore_report.get("gate_panel_visible_at_capture", False)),
        "etchline_chunks_loaded": int((etch_report.get("checks", {}) if isinstance(etch_report.get("checks", {}), dict) else {}).get("chunk_count", 0) or 0),
        "etchline_source_ui_hidden_default": bool(all((etch_report.get("checks", {}).get("ui_hidden_default", {}) or {}).values())) if isinstance(etch_report.get("checks", {}), dict) else False,
        "screenshots": screenshots,
        "screenshot_status": screenshot_status,
        "reports": {
            "gateway": str(ROOT / "logs" / "mode_gateway_self_test.json"),
            "world_authority": str(ROOT / "logs" / "world_authority_smoke_report.json"),
            "holocore": str(ROOT / "HoloCore" / "logs" / "holocore_integration_smoke_report.json"),
            "etch_line": str(ROOT / "logs" / "etchline_same_window_contract_report.json"),
        },
        "runs": runs,
    }
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
