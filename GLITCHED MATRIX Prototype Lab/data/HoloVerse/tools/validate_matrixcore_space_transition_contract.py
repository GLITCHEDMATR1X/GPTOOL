#!/usr/bin/env python3
"""Validate MatrixCore RMB HoloSpace transition / Dyson return contract."""
from __future__ import annotations

import importlib
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
WORLD = ROOT / "world.py"
TRAVEL = ROOT / "holospace_travel_sequence.py"
REPORT = ROOT / "logs" / "matrixcore_space_transition_contract_report.json"


def _hidden(node: Any) -> bool:
    try:
        return bool(node.isHidden())
    except Exception:
        return False


def _step(app: Any, frames: int = 1) -> None:
    for _ in range(max(0, int(frames))):
        app.taskMgr.step()


def static_checks(errors: list[str], report: dict[str, Any]) -> None:
    main_py = MAIN.read_text(encoding="utf-8")
    world_py = WORLD.read_text(encoding="utf-8")
    travel_py = TRAVEL.read_text(encoding="utf-8")
    checks = {
        "version-pass96": 'VERSION = "0.10.96-existing-holospace-transition-corrected"' in main_py,
        "slow-cycle-default": "DAY_NIGHT_CYCLE_SECONDS = 1800.0" in world_py and '"cycle_seconds": 1800.0' in main_py,
        "slow-cycle-minimum": "max(900.0, float(getattr(self.cfg, \"day_night_cycle_seconds\"" in world_py and "max(900.0, float(getattr(cfg, \"day_night_cycle_seconds\", 1800.0)))" in main_py,
        "rmb-matrixcore-enters-space": "def native_mouse3_down" in main_py and "source=\"matrixcore_rmb\", destination=\"space\"" in main_py,
        "transition-destination-owned": "holospace_transition_destination" in main_py and "destination == \"hub\"" in main_py,
        "dyson-move-starts-return-transition": "def handle_holospace_boundary_return" in main_py and "self.start_holospace_return_sequence(source=\"dyson_sphere\")" in main_py,
        "dyson-click-starts-return-transition": "def is_looking_at_holospace_dyson_gate" in main_py and "source=\"dyson_click\"" in main_py and "source=\"dyson_click_rmb\"" in main_py,
        "transition-look-control": "self.update_look(dt)" in main_py and "look control while the countdown runs" in main_py,
        "transition-hud-suppression": "def set_holospace_transition_hud_suppressed" in main_py and "only its countdown may show" in main_py,
        "countdown-only-runtime": "self.countdown_label" in travel_py and "DirectLabel" in travel_py and "countdown_label[\"text\"] = str(max(1, int(math.ceil(remaining))))" in travel_py,
        "no-entry-help-text": "HOLOSPACE WAR // WASD FLY" not in main_py and "WASD bends light" not in travel_py and "SPACE TRANSIT //" not in travel_py,
    }
    report["static_checks"] = checks
    for name, ok in checks.items():
        if not ok:
            errors.append(name)


def runtime_checks(errors: list[str], report: dict[str, Any]) -> None:
    old_cwd = Path.cwd()
    old_argv = list(sys.argv)
    app = None
    try:
        os.chdir(ROOT)
        sys.path.insert(0, str(ROOT))
        os.environ.setdefault("MATRIX_GAME_WIDTH", "960")
        os.environ.setdefault("MATRIX_GAME_HEIGHT", "540")
        os.environ.setdefault("MATRIX_GAME_BORDERED_FULLSCREEN", "0")
        os.environ.setdefault("MATRIX_GAME_BORDERLESS", "0")
        os.environ.setdefault("MATRIX_GAME_FULLSCREEN", "0")
        os.environ.setdefault("HOLOVERSE_NATIVE_ADAPTER_LOGS", "0")
        sys.argv = ["main.py", "--self-test", "--matrixcore-space-transition-contract"]
        hv_main = importlib.import_module("main")
        app = hv_main.CommandHubApp()
        for task_name in ("self-test-setup", "self-test-exit", "matrixcore-gleebs-first-contact"):
            try:
                app.taskMgr.remove(task_name)
            except Exception:
                pass
        _step(app, 8)

        entry = app.holoverse_region_entry_for_number(8) or {}
        ok_start = bool(app.start_holospace_travel_sequence(entry, source="validator_matrixcore_rmb", destination="space"))
        _step(app, 2)
        runtime = getattr(app, "holospace_travel_runtime", None)
        countdown = getattr(runtime, "countdown_label", None)
        report["runtime_start"] = {
            "ok_start": ok_start,
            "traveling": bool(app.is_holospace_traveling()),
            "destination": str(getattr(app, "holospace_transition_destination", "")),
            "hud_hidden": _hidden(getattr(app, "hud_root", None)),
            "top_hidden": _hidden(getattr(app, "top_panel", None)),
            "crosshair_hidden": _hidden(getattr(app, "crosshair_root", None)),
            "center_hint_hidden": _hidden(getattr(app, "center_hint", None)),
            "world_root_hidden": _hidden(getattr(app, "root_3d", None)),
            "countdown_visible": bool(countdown is not None and not _hidden(countdown)),
            "countdown_text": str(countdown["text"] if countdown is not None else ""),
        }
        if not ok_start or not app.is_holospace_traveling():
            errors.append("space transition did not start")
        if str(getattr(app, "holospace_transition_destination", "")) != "space":
            errors.append("space transition destination not recorded")
        for key in ("hud_hidden", "top_hidden", "crosshair_hidden", "center_hint_hidden"):
            if not report["runtime_start"].get(key):
                errors.append(f"transition HUD not suppressed: {key}")
        if not report["runtime_start"].get("world_root_hidden"):
            errors.append("transition showed the HoloVerse hub/world root instead of the HoloSpace transition scene")
        if not report["runtime_start"].get("countdown_visible"):
            errors.append("countdown label was not the visible transition UI")

        app.complete_holospace_travel_sequence()
        _step(app, 4)
        report["runtime_space"] = {
            "holospace_active": bool(app.is_holospace_active()),
            "hint_text": str(app.center_hint["text"]),
            "destination": str(getattr(app, "holospace_transition_destination", "")),
            "world_root_visible": not _hidden(getattr(app, "root_3d", None)),
        }
        if not app.is_holospace_active():
            errors.append("space transition did not enter HoloSpace")
        if "WASD" in str(app.center_hint["text"]).upper() or "DYSON RETURNS" in str(app.center_hint["text"]).upper():
            errors.append("HoloSpace entry displayed old help UI text")

        app.start_holospace_return_sequence(source="validator_dyson")
        _step(app, 2)
        report["runtime_return_start"] = {
            "traveling": bool(app.is_holospace_traveling()),
            "destination": str(getattr(app, "holospace_transition_destination", "")),
            "countdown_visible": bool(countdown is not None and not _hidden(countdown)),
        }
        if str(getattr(app, "holospace_transition_destination", "")) != "hub":
            errors.append("Dyson return did not target hub transition")
        app.complete_holospace_travel_sequence()
        _step(app, 4)
        report["runtime_return_complete"] = {
            "holospace_active": bool(app.is_holospace_active()),
            "player_pos": [round(float(app.player_pos.x), 3), round(float(app.player_pos.y), 3), round(float(app.player_pos.z), 3)],
            "signature": str(getattr(app, "runtime_world_signature", "")),
            "world_root_visible": not _hidden(getattr(app, "root_3d", None)),
        }
        if app.is_holospace_active():
            errors.append("Dyson transition did not return to hub on foot")
    finally:
        try:
            if app is not None and hasattr(app, "destroy"):
                app.destroy()
        except Exception:
            pass
        sys.argv = old_argv
        try:
            os.chdir(old_cwd)
        except Exception:
            pass


def main() -> int:
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    report: dict[str, Any] = {"schema": 1, "kind": "matrixcore_space_transition_contract", "errors": errors}
    static_checks(errors, report)
    runtime_checks(errors, report)
    report["status"] = "PASS" if not errors else "FAIL"
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
