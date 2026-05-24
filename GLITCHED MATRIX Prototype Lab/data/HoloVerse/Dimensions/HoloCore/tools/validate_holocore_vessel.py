"""Validate the HoloCore walkable vessel import contract."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "logs" / "holocore_vessel_validation_report.json"


def main() -> int:
    errors: list[str] = []
    main_py = ROOT / "main.py"
    vessel_py = ROOT / "assets" / "entities" / "holo_vessel.py"
    vessel_shim = ROOT / "holo_vessel.py"
    smoke_report = ROOT / "logs" / "holocore_vessel_smoke_report.json"
    if not main_py.exists():
        errors.append("main.py-missing")
        main_text = ""
    else:
        main_text = main_py.read_text(encoding="utf-8", errors="ignore")
    if not vessel_py.exists():
        errors.append("assets/entities/holo_vessel.py-missing")
        vessel_text = ""
    else:
        vessel_text = vessel_py.read_text(encoding="utf-8", errors="ignore")
    if not vessel_shim.exists():
        errors.append("holo_vessel.py-compat-shim-missing")
    else:
        shim_text = vessel_shim.read_text(encoding="utf-8", errors="ignore")
        if "assets.entities.holo_vessel" not in shim_text:
            errors.append("holo_vessel.py-shim-not-routing-to-assets-entities")

    required_main_terms = [
        "HOLOCORE_VESSEL_SMOKE",
        "_build_holo_vessel_outside_pyramid",
        "_handle_e_interaction",
        "_try_holo_vessel_interaction",
        "_update_holo_vessel_piloting",
        "_clamp_player_with_holo_vessel",
    ]
    for term in required_main_terms:
        if term not in main_text:
            errors.append(f"main-missing:{term}")

    required_vessel_terms = [
        "class HoloVessel",
        "walkable_cabin_floor",
        "rear_entry_ramp",
        "pilot_seat_trigger",
        "clamp_interior_position",
        "move_piloted",
        "terrain_height_func",
        "vertical_axis",
        "flight_altitude",
        "max_flight_altitude",
        "_surface_locked_z",
        "elliptical_tube_geom",
        "rounded_main_fuselage",
        "lower_cylindrical_keel",
        "rounded_rear_engine_pod",
        "ellipse_upper_cross_section_points",
    ]
    for term in required_vessel_terms:
        if term not in vessel_text:
            errors.append(f"vessel-missing:{term}")

    forbidden_generated_names = ["crescent_landing_pad", "landing_pad_fill", "landing_pad_frame"]
    for term in forbidden_generated_names:
        if term in vessel_text:
            errors.append(f"forbidden-platform-node:{term}")

    # Confirm the E key route is reserved for vessel/local interaction and no
    # longer toggles or opens the old dimension gate menu.
    if 'self.accept("e", self._handle_e_interaction)' not in main_text:
        errors.append("e-key-not-routed-to-vessel-interaction")
    if '"space"' not in main_text or '"c"' not in main_text:
        errors.append("flight-up-down-keys-not-bound")
    if "vertical_axis=" not in main_text:
        errors.append("vertical-axis-not-passed-to-vessel")
    e_handler_match = re.search(r"def _handle_e_interaction\(self\).*?(?=\n    def )", main_text, flags=re.S)
    e_handler = e_handler_match.group(0) if e_handler_match else ""
    if "_toggle_dimension_gate_panel" in e_handler or "_open_dimension_gate_panel" in e_handler or "_request_pyramid_gate_menu" in e_handler:
        errors.append("e-key-still-opens-dimension-menu")

    # Keep the room collider/player clamp large enough for a real walkable room.
    room_bounds = {
        name: float(value)
        for name, value in re.findall(r"(room_(?:min|max)_[xy])\s*:\s*float\s*=\s*(-?\d+(?:\.\d+)?)", vessel_text)
    }
    room_width = abs(room_bounds.get("room_max_x", 0.0) - room_bounds.get("room_min_x", 0.0))
    room_length = abs(room_bounds.get("room_max_y", 0.0) - room_bounds.get("room_min_y", 0.0))
    scale_match = re.search(r"world_scale\s*:\s*float\s*=\s*(\d+(?:\.\d+)?)", vessel_text)
    vessel_scale = float(scale_match.group(1)) if scale_match else 1.0
    physical_width = room_width * vessel_scale
    physical_length = room_length * vessel_scale
    if physical_width < 30.0:
        errors.append(f"walkable-room-too-narrow-world:{physical_width}")
    if physical_length < 75.0:
        errors.append(f"walkable-room-too-short-world:{physical_length}")

    smoke = {}
    if smoke_report.exists():
        try:
            smoke = json.loads(smoke_report.read_text(encoding="utf-8"))
            if smoke.get("status") != "PASS":
                errors.append("vessel-smoke-not-pass")
        except Exception as exc:
            errors.append(f"vessel-smoke-json-error:{exc.__class__.__name__}:{exc}")
    else:
        pass  # Smoke report is optional in clean/portable patch packages.

    result = {
        "schema": 1,
        "kind": "holocore_holo_vessel_validation",
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "vessel_scale": vessel_scale,
        "walkable_room_width_local": room_width,
        "walkable_room_length_local": room_length,
        "walkable_room_width_world": physical_width,
        "walkable_room_length_world": physical_length,
        "smoke_status": smoke.get("status"),
        "flight_controls": "Space/PageUp up, C/PageDown down, A/D yaw, W/S thrust",
        "screenshots": smoke.get("screenshots", {}),
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
