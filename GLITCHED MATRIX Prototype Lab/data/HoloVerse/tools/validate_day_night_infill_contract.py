#!/usr/bin/env python3
"""Validate Pass 94 day/night black-backdrop infill behavior."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORLD = ROOT / "world.py"
MAIN = ROOT / "main.py"
REPORT = ROOT / "logs" / "day_night_infill_contract_report.json"


def main() -> int:
    world = WORLD.read_text(encoding="utf-8")
    main_py = MAIN.read_text(encoding="utf-8")
    checks = {
        "black-backdrop-constant": "DAY_NIGHT_BLACK_BACKDROP_RGB" in world,
        "night-infill-factor": "def day_night_infill_factor" in world,
        "infill-registration": "def register_day_night_infill_node" in world and "day_night_infill_nodes" in world,
        "infill-application-call": "self.apply_day_night_infill_state(dt)" in world,
        "wire-roots-glow": "DAY_NIGHT_WIREFRAME_GLOW_BOOST" in world and "line_root" in world and "accent_root" in world,
        "surface-tags": "self.register_day_night_infill_node(np, rgba, color_api=\"color\")" in world,
        "solid-tags": "self.register_day_night_infill_node(node" in world,
        "true-black-sky-blend": "lerp_rgb(color, DAY_NIGHT_BLACK_BACKDROP_RGB" in world,
        "holospace-excluded": "if bool(getattr(self, \"holospace_active\", False))" in world and "return 0.0" in world,
        "progression-default-world-cycle": '"world_cycle": {' in main_py,
        "restore-progress-method": "def restore_world_cycle_progress" in main_py,
        "persist-progress-method": "def persist_world_cycle_progress" in main_py,
        "exit-persists-cycle": "self.persist_world_cycle_progress(force=True)" in main_py,
        "update-persists-cycle": "self.persist_world_cycle_progress(force=False)" in main_py,
        "progression-black-flag": '"day_night_black_backdrop_enabled": True' in main_py,
        "report-fields": '"day_night_black_backdrop_enabled": True' in world and '"current_night_infill_factor"' in world,
    }
    failed = [name for name, ok in checks.items() if not ok]
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps({"schema": 1, "kind": "day_night_infill_contract", "checks": checks, "failed": failed}, indent=2) + "\n", encoding="utf-8")
    if failed:
        for name in failed:
            print(name)
        return 1
    print("day-night-infill-contract-ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
