from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from holoutopia_citizen_simulation import simulate_city_at_time
from holoutopia_game_runtime import _robot_marker_config, load_runtime_config


def main() -> int:
    config = load_runtime_config(ROOT)
    runtime = config.get("citizen_runtime") if isinstance(config.get("citizen_runtime"), dict) else {}
    marker = runtime.get("robot_marker") if isinstance(runtime.get("robot_marker"), dict) else {}
    safety = config.get("safety") if isinstance(config.get("safety"), dict) else {}
    frame = simulate_city_at_time(ROOT, str(runtime.get("sample_clock_on_start") or "08:00"))
    resolved = _robot_marker_config(config)
    errors: list[str] = []
    if str(marker.get("style")) != "tiny_directional_wire_robot":
        errors.append("citizen_runtime.robot_marker.style must be tiny_directional_wire_robot")
    if str(marker.get("direction_source")) != "previous_or_next_schedule_target":
        errors.append("robot_marker.direction_source must use previous_or_next_schedule_target")
    if str(marker.get("animation")) != "procedural_bob_and_limb_swing":
        errors.append("robot_marker.animation must be procedural_bob_and_limb_swing")
    if not resolved.get("height", 0) > 0:
        errors.append("robot marker height must be positive")
    if not resolved.get("same_node_spread_radius", 0) >= 8.0:
        errors.append("same-node spread radius should be large enough to avoid citizen stacking")
    if safety.get("adds_collision") is not False:
        errors.append("robot civilians must not add collision")
    if safety.get("citizen_markers_are_collisionless_directional_robots") is not True:
        errors.append("safety flag for collisionless directional robots must be true")
    if int(frame.get("citizen_count", 0) or 0) < 44:
        errors.append("schedule frame must still resolve all city citizens")
    activities = frame.get("by_activity") if isinstance(frame.get("by_activity"), dict) else {}
    if not activities:
        errors.append("schedule frame must provide activity distribution for robot colors/animation")
    payload = {
        "robot_marker": marker,
        "resolved_marker": resolved,
        "citizen_count": frame.get("citizen_count"),
        "activities": activities,
        "safety": safety,
        "errors": errors,
    }
    if errors:
        print("HoloUtopia robot civilians validation FAILED")
        print(json.dumps(payload, indent=2))
        return 2
    print("HoloUtopia robot civilians validation passed")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
