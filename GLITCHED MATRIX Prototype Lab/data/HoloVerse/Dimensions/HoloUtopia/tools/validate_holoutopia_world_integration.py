from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from holoutopia_game_runtime import build_runtime_summary, load_runtime_config


def main() -> int:
    config = load_runtime_config(ROOT)
    summary = build_runtime_summary(ROOT).as_dict()
    errors: list[str] = []

    if int(config.get("schema", 0) or 0) < 2:
        errors.append("runtime config schema must be >= 2 for world integration")
    integration = config.get("world_integration") if isinstance(config.get("world_integration"), dict) else {}
    if str(integration.get("mode") or "") != "world_parented_city_layer":
        errors.append("world_integration.mode must be world_parented_city_layer")
    preference = integration.get("parent_preference")
    if not isinstance(preference, list) or "root_3d" not in [str(x) for x in preference]:
        errors.append("world_integration.parent_preference must include root_3d")
    if str(integration.get("root_node_name") or "") != "holoutopia_integrated_city_world":
        errors.append("world_integration.root_node_name must be holoutopia_integrated_city_world")
    for key in ("hide_during_native_dimensions", "hide_during_holocore", "hide_during_holospace", "no_collision_geometry"):
        if integration.get(key) is not True:
            errors.append(f"world_integration.{key} must be true")

    layers = config.get("render_layers") if isinstance(config.get("render_layers"), dict) else {}
    for key in ("city_3d_massing", "neighborhood_overlays", "citizen_markers"):
        if layers.get(key) is not True:
            errors.append(f"render_layers.{key} must be true")

    safety = config.get("safety") if isinstance(config.get("safety"), dict) else {}
    for key in ("writes_authored_data", "writes_runtime_logs", "adds_collision", "touches_artifact_routes", "touches_holocore"):
        if safety.get(key) is not False:
            errors.append(f"runtime safety.{key} must be false")

    if summary.get("integration_mode") != "world_parented_city_layer":
        errors.append("runtime summary integration_mode mismatch")
    if summary.get("town_count") != 9:
        errors.append(f"expected 9 districts, got {summary.get('town_count')}")
    if summary.get("citizen_count") != summary.get("schedule_frame_citizens"):
        errors.append("not all citizens resolved in runtime sample frame")
    if int(summary.get("citizen_count") or 0) < 44:
        errors.append("expected at least 44 citizens")

    if errors:
        print("HoloUtopia world integration validation FAILED")
        for error in errors:
            print(" -", error)
        print(json.dumps(summary, indent=2))
        return 2
    print("HoloUtopia world integration validation passed")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
