from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from holoutopia_citizen_simulation import DEFAULT_SAMPLE_TIMES, build_building_occupancy_index, load_simulation_inputs, simulate_city_at_time, simulate_city_day


def main() -> int:
    issues: list[str] = []
    inputs = load_simulation_inputs(ROOT)
    citizens = inputs["citizen_manifest"].get("citizens", [])
    citizen_ids = {str(c.get("id")) for c in citizens if isinstance(c, dict)}
    if len(citizen_ids) != len(citizens):
        issues.append("citizen ids must be unique")
    if len(citizen_ids) < 1:
        issues.append("citizen manifest is empty")

    result = simulate_city_day(ROOT, DEFAULT_SAMPLE_TIMES)
    for frame in result["frames"]:
        if frame["citizen_count"] != len(citizen_ids):
            issues.append(f"{frame['clock']}: expected {len(citizen_ids)} citizens, got {frame['citizen_count']}")
        if frame.get("issues"):
            issues.extend(f"{frame['clock']}:{issue}" for issue in frame["issues"])
        if not frame.get("by_activity"):
            issues.append(f"{frame['clock']}: empty activity summary")
        for cid, state in frame.get("citizens", {}).items():
            pos = state.get("position", {})
            if not isinstance(pos.get("x"), (int, float)) or not isinstance(pos.get("y"), (int, float)):
                issues.append(f"{frame['clock']}:{cid}: missing resolved position")
            if not state.get("resolved_node"):
                issues.append(f"{frame['clock']}:{cid}: missing resolved_node")

    expected_by_time = {
        "06:00": "wake_up",
        "08:00": "work_shift",
        "12:00": "meal_break",
        "17:30": "hobby",
        "21:00": "return_home",
    }
    for frame in result["frames"]:
        expected = expected_by_time.get(frame["clock"])
        if expected and frame["by_activity"].get(expected) != len(citizen_ids):
            issues.append(f"{frame['clock']}: expected all citizens in {expected}, got {frame['by_activity']}")

    danger = simulate_city_at_time(ROOT, "12:00", danger_state=True, inputs=inputs)
    if danger["citizen_count"] != len(citizen_ids):
        issues.append("danger frame did not include all citizens")
    if danger.get("by_activity", {}).get("danger_override") != len(citizen_ids):
        issues.append(f"danger frame did not override all citizens: {danger.get('by_activity')}")
    if danger.get("issues"):
        issues.extend(f"danger:{issue}" for issue in danger["issues"])

    occupancy = build_building_occupancy_index(inputs)
    resident_total = sum(len(entry.get("citizens", [])) for entry in occupancy.get("home_lots", {}).values())
    worker_total = sum(len(entry.get("citizens", [])) for entry in occupancy.get("work_nodes", {}).values())
    if resident_total != len(citizen_ids):
        issues.append(f"occupancy home citizen count mismatch: {resident_total} != {len(citizen_ids)}")
    if worker_total != len(citizen_ids):
        issues.append(f"occupancy work citizen count mismatch: {worker_total} != {len(citizen_ids)}")

    payload = {
        "ok": not issues,
        "citizens": len(citizen_ids),
        "sample_times": list(DEFAULT_SAMPLE_TIMES),
        "frames": len(result["frames"]),
        "danger_override_checked": True,
        "home_lots_with_residents": len(occupancy.get("home_lots", {})),
        "work_nodes_with_workers": len(occupancy.get("work_nodes", {})),
        "issues": issues,
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if not issues else 1


if __name__ == "__main__":
    raise SystemExit(main())
