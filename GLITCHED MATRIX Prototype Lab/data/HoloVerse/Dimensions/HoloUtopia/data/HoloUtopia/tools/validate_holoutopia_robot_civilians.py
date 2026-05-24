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
    marker = runtime.get("person_marker") if isinstance(runtime.get("person_marker"), dict) else runtime.get("robot_marker") if isinstance(runtime.get("robot_marker"), dict) else {}
    safety = config.get("safety") if isinstance(config.get("safety"), dict) else {}
    frame = simulate_city_at_time(ROOT, str(runtime.get("sample_clock_on_start") or "08:00"))
    resolved = _robot_marker_config(config)
    errors: list[str] = []
    if str(marker.get("style")) != "tiny_3d_people":
        errors.append("citizen_runtime.person_marker.style must be tiny_3d_people")
    if str(marker.get("direction_source")) != "previous_or_next_schedule_target":
        errors.append("person_marker.direction_source must use previous_or_next_schedule_target")
    if str(marker.get("animation")) != "procedural_bob_and_limb_swing":
        errors.append("person_marker.animation must be procedural_bob_and_limb_swing")
    if not (3.0 <= float(resolved.get("height", 0) or 0) <= 10.0):
        errors.append(f"person marker height should be small, got {resolved.get('height')}")
    if not resolved.get("same_node_spread_radius", 0) >= 6.0:
        errors.append("same-node spread radius should be large enough to avoid citizen stacking")
    if resolved.get("show_contact_pad") is not False:
        errors.append("person markers must not draw contact pads or ground circles")
    if resolved.get("show_name_label") is not False:
        errors.append("person markers must not draw name labels")
    if safety.get("adds_collision") is not False:
        errors.append("robot civilians must not add collision")
    if safety.get("citizen_markers_are_collisionless_3d_people") is not True:
        errors.append("safety flag for collisionless 3D people must be true")
    if safety.get("citizen_markers_have_no_ground_rings") is not True:
        errors.append("safety flag must confirm citizens have no ground rings")
    if safety.get("citizen_markers_have_no_name_labels") is not True:
        errors.append("safety flag must confirm citizens have no name labels")
    if int(frame.get("citizen_count", 0) or 0) < 44:
        errors.append("schedule frame must still resolve all city citizens")
    activities = frame.get("by_activity") if isinstance(frame.get("by_activity"), dict) else {}
    if not activities:
        errors.append("schedule frame must provide activity distribution for robot colors/animation")
    payload = {
        "person_marker": marker,
        "resolved_marker": resolved,
        "citizen_count": frame.get("citizen_count"),
        "activities": activities,
        "safety": safety,
        "errors": errors,
    }
    if errors:
        print("HoloUtopia little 3D citizens validation FAILED")
        print(json.dumps(payload, indent=2))
        return 2
    print("HoloUtopia little 3D citizens validation passed")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
