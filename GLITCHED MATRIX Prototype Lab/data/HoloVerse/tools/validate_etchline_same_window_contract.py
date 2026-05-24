#!/usr/bin/env python3
"""Validate Etch-Line's real HoloVerse same-window adapter path.

The standalone Etch-Line smoke is useful for its source project, but it can
mislead HoloVerse regression checks because the standalone game intentionally
shows its full legacy HUD.  HoloVerse artifact gameplay must mount Etch-Line in
same-window mode, keep source UI hidden by default, return without deleting the
host update task, and leave the hub/HUD restored.
"""
from __future__ import annotations

import importlib
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = ROOT / "logs"
REPORT = LOG_DIR / "etchline_same_window_contract_report.json"
SCREENSHOT = LOG_DIR / "etchline_same_window_smoke.png"


def _node_hidden(node: Any) -> bool | None:
    if node is None:
        return None
    try:
        return bool(node.isHidden())
    except Exception:
        return None


def _step(app: Any, frames: int) -> None:
    for _ in range(max(0, int(frames))):
        app.taskMgr.step()


def main() -> int:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MATRIX_GAME_WIDTH", "1280")
    os.environ.setdefault("MATRIX_GAME_HEIGHT", "720")
    os.environ.setdefault("MATRIX_GAME_BORDERED_FULLSCREEN", "0")
    os.environ.setdefault("MATRIX_GAME_BORDERLESS", "0")
    os.environ.setdefault("MATRIX_GAME_FULLSCREEN", "0")

    old_cwd = Path.cwd()
    old_argv = list(sys.argv)
    app = None
    errors: list[str] = []
    report: dict[str, Any] = {
        "schema": 1,
        "kind": "etchline_same_window_contract",
        "screenshot": str(SCREENSHOT),
        "checks": {},
        "errors": errors,
    }
    try:
        os.chdir(ROOT)
        sys.path.insert(0, str(ROOT))
        # Force offscreen-friendly ShowBase config, but remove the generic
        # self-test scheduled tasks so this validator controls the sequence.
        sys.argv = ["main.py", "--self-test"]
        hv_main = importlib.import_module("main")
        app = hv_main.CommandHubApp()
        for task_name in ("self-test-setup", "self-test-exit"):
            try:
                app.taskMgr.remove(task_name)
            except Exception:
                pass
        _step(app, 45)

        record = hv_main.dimension_record_from_index("etch_line")
        if not isinstance(record, dict):
            errors.append("etch-line dimension index record missing")
            record = {}
        mode = hv_main.mode_from_dimension_record(record) if record else None
        if not isinstance(mode, dict):
            errors.append("etch-line mode conversion failed")
            mode = {}
        entry = ROOT / str(record.get("entry", "Dimensions/Etch-Line/main.py"))
        ok = bool(app.launch_native_mode(mode, entry, "Etch-Line", source="contract"))
        report["checks"]["launch_ok"] = ok
        if not ok:
            errors.append("same-window native launch failed")
        _step(app, 90)

        mode_obj = getattr(app, "active_native_mode", None)
        report["checks"]["active_native_mode"] = type(mode_obj).__name__ if mode_obj is not None else ""
        if mode_obj is None:
            errors.append("active native mode missing after launch")
        else:
            ui_names = [
                "hud_root",
                "crosshair",
                "menu_root",
                "work_root",
                "mission_overlay_root",
            ]
            ui_hidden = {name: _node_hidden(getattr(mode_obj, name, None)) for name in ui_names}
            report["checks"]["ui_hidden_default"] = ui_hidden
            for name, hidden in ui_hidden.items():
                if hidden is not True:
                    errors.append(f"etch-line source UI node not hidden by default: {name}")
            report["checks"]["chunk_count"] = len(getattr(mode_obj, "chunks", {}) or {})
            report["checks"]["enemy_count"] = len(getattr(mode_obj, "enemies", []) or [])
            if int(report["checks"]["chunk_count"] or 0) <= 0:
                errors.append("etch-line loaded no chunks in same-window mode")

        report["checks"]["host_update_task_count_during"] = len(app.taskMgr.getTasksNamed("update-task"))
        if int(report["checks"]["host_update_task_count_during"] or 0) != 1:
            errors.append("host update-task count changed during Etch-Line")
        report["checks"]["host_chunk_task_count_during"] = len(app.taskMgr.getTasksNamed("chunk-task"))
        if int(report["checks"]["host_chunk_task_count_during"] or 0) != 0:
            errors.append("Etch-Line source chunk-task leaked into host")

        try:
            from panda3d.core import Filename
            app.win.saveScreenshot(Filename.fromOsSpecific(str(SCREENSHOT)))
        except Exception as exc:
            errors.append(f"same-window screenshot failed: {exc.__class__.__name__}:{exc}")

        app.return_from_native_mode(reason="contract_return")
        _step(app, 12)
        report["checks"]["active_native_after_return"] = type(getattr(app, "active_native_mode", None)).__name__ if getattr(app, "active_native_mode", None) is not None else ""
        if report["checks"]["active_native_after_return"]:
            errors.append("active native mode remained after return")
        report["checks"]["host_update_task_count_after"] = len(app.taskMgr.getTasksNamed("update-task"))
        if int(report["checks"]["host_update_task_count_after"] or 0) != 1:
            errors.append("host update-task count changed after Etch-Line return")
        report["checks"]["host_chunk_task_count_after"] = len(app.taskMgr.getTasksNamed("chunk-task"))
        if int(report["checks"]["host_chunk_task_count_after"] or 0) != 0:
            errors.append("chunk-task leaked after Etch-Line return")
        try:
            report["checks"]["hub_root_visible_after_return"] = not bool(app.root_3d.isHidden())
            if bool(app.root_3d.isHidden()):
                errors.append("hub/root_3d hidden after Etch-Line return")
        except Exception:
            pass
        try:
            report["checks"]["hud_visible_after_return"] = not bool(app.hud_root.isHidden())
            if bool(app.hud_root.isHidden()):
                errors.append("HoloVerse HUD hidden after Etch-Line return")
        except Exception:
            pass
    except Exception as exc:
        errors.append(f"validator exception: {exc.__class__.__name__}:{exc}")
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

    report["status"] = "PASS" if not errors else "FAIL"
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
