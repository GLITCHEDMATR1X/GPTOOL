#!/usr/bin/env python3
"""Validate progression scoring and Gates quick-travel contracts statically.

No Panda3D window is opened. This guards the integration points needed for:
- persisted cross-dimension points;
- native dimension result payloads;
- ESC menu Gates right-panel actions;
- region and dimension gate quick travel.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
DIMENSIONS = ROOT / "Dimensions"


def _rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except Exception:
        return path.as_posix()


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def _method_body(text: str, name: str) -> str:
    pattern = re.compile(
        rf"^(?P<indent>\s*)def {re.escape(name)}\([^\n]*\)(?:\s*->\s*[^:]+)?:\n",
        re.M,
    )
    match = pattern.search(text)
    if not match:
        return ""
    indent = match.group("indent")
    start = match.end()
    next_pattern = re.compile(rf"^{re.escape(indent)}(?:def |class )", re.M)
    next_match = next_pattern.search(text, start)
    end = next_match.start() if next_match else len(text)
    return text[start:end]


def _contains_all(text: str, needles: list[str]) -> list[str]:
    return [needle for needle in needles if needle not in text]


def main() -> int:
    errors: list[str] = []
    warnings: list[str] = []
    main_text = _read_text(MAIN)
    checked: dict[str, Any] = {}

    if not main_text:
        errors.append("main.py: missing or unreadable")
    else:
        default_body = _method_body(main_text, "matrixcore_default_progression_payload")
        missing = _contains_all(default_body, [
            '"schema_version": 5',
            '"total_points"',
            '"holoverse_score"',
            '"dimension_progress"',
            '"dimension_results"',
            '"discovered_gates"',
        ])
        if missing:
            errors.append("matrixcore_default_progression_payload: missing " + ", ".join(missing))

        recalc_body = _method_body(main_text, "recalculate_matrixcore_points")
        missing = _contains_all(recalc_body, [
            '"dimension_results"',
            '"dimension_progress"',
            '"holoverse_score"',
            '"total_points"',
            '"points_total"',
        ])
        if missing:
            errors.append("recalculate_matrixcore_points: missing " + ", ".join(missing))

        record_body = _method_body(main_text, "record_native_dimension_result")
        missing = _contains_all(record_body, [
            'progress.setdefault("dimension_results"',
            'progress.setdefault("dimension_progress"',
            'self.recalculate_matrixcore_points(progress)',
            'self.update_matrixcore_gate_result_state',
            '"score_delta"',
        ])
        if missing:
            errors.append("record_native_dimension_result: missing " + ", ".join(missing))

        save_body = _method_body(main_text, "save_matrixcore_progression")
        if "self.recalculate_matrixcore_points(merged)" not in save_body:
            errors.append("save_matrixcore_progression: does not normalize points before write")

        discovered_body = _method_body(main_text, "matrixcore_progression_discovered_gates")
        missing = _contains_all(discovered_body, [
            "self.holoverse_region_travel_map()",
            '"kind": "region"',
            '"route": "region_spawn"',
            '"source": "region_index"',
            '"target_number"',
        ])
        if missing:
            errors.append("matrixcore_progression_discovered_gates: missing " + ", ".join(missing))

        modes_body = _method_body(main_text, "matrixcore_dimension_gate_modes")
        missing = _contains_all(modes_body, [
            'kind == "region"',
            '"_matrixcore_gate_kind": "region"',
            '"_matrixcore_region_number"',
            '"_matrixcore_gate_id"',
        ])
        if missing:
            errors.append("matrixcore_dimension_gate_modes: missing " + ", ".join(missing))

        launch_body = _method_body(main_text, "matrixcore_launch_dimension_gate_mode")
        missing = _contains_all(launch_body, [
            '"region"',
            "travel_to_holoverse_region_index",
            'force=True',
            "start_dimension_transition",
        ])
        if missing:
            errors.append("matrixcore_launch_dimension_gate_mode: missing " + ", ".join(missing))

        menu_body = _method_body(main_text, "refresh_menu_actions")
        if '"gates": gate_actions' not in menu_body:
            errors.append("refresh_menu_actions: Gates tab does not use gate_actions")
        if "self.menu_gate_actions()" not in menu_body:
            errors.append("refresh_menu_actions: does not build menu_gate_actions")

        gate_menu_body = _method_body(main_text, "menu_gate_actions")
        missing = _contains_all(gate_menu_body, [
            'badge = "REG"',
            '"menu_launch_dimension_gate"',
            '"NO GATES INDEXED"',
        ])
        if missing:
            errors.append("menu_gate_actions: missing " + ", ".join(missing))

        total_body = _method_body(main_text, "holoverse_total_points")
        missing = _contains_all(total_body, [
            "MATRIXCORE_PROGRESSION_PATH",
            '"dimension_results"',
            '"dimension_progress"',
            '"holoverse_score"',
            '"total_points"',
        ])
        if missing:
            errors.append("holoverse_total_points: missing " + ", ".join(missing))

    adapters = {
        "Code Red Vector": DIMENSIONS / "Code Red Vector" / "holoverse_native_adapter.py",
        "Fractured Dimension": DIMENSIONS / "Fractured Dimension" / "holoverse_native_adapter.py",
        "Holo Campaign": DIMENSIONS / "Holo Campaign" / "main.py",
        "Holo Conquest": DIMENSIONS / "Holo Conquest" / "holoverse_native_adapter.py",
        "Vector Wars": DIMENSIONS / "Vector Wars" / "holoverse_native_adapter.py",
        "Zonez": DIMENSIONS / "Zonez" / "holoverse_native_adapter.py",
    }
    adapter_rows: list[dict[str, Any]] = []
    for name, path in adapters.items():
        text = _read_text(path)
        item: dict[str, Any] = {"name": name, "path": _rel(path), "ok": True, "issues": []}
        if not text:
            item["issues"].append("missing-or-unreadable")
        else:
            if "def get_holoverse_result" not in text:
                item["issues"].append("get_holoverse_result-missing")
            if "score_delta" not in text:
                item["issues"].append("score_delta-missing")
            if "completed" not in text:
                item["issues"].append("completed-missing")
            if "signal" not in text and "memory_fragment" not in text:
                item["issues"].append("signal-or-memory-fragment-missing")
        item["ok"] = not item["issues"]
        if item["issues"]:
            errors.append(f"{name}: " + ", ".join(item["issues"]))
        adapter_rows.append(item)

    checked["main"] = _rel(MAIN)
    checked["adapters"] = adapter_rows
    report = {
        "schema": 1,
        "kind": "progression_gates_contract_validation",
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "checked": checked,
    }
    print(json.dumps(report, indent=2), flush=True)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
