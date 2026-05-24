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
    errors: list[str] = []
    if int(config.get("schema", 0)) < 2:
        errors.append("runtime config schema must be >= 2")
    placement = config.get("placement") if isinstance(config.get("placement"), dict) else {}
    scale = float(placement.get("scale", 0))
    if scale <= 0 or scale > 2.0:
        errors.append(f"runtime placement.scale out of safe range: {scale}")
    safety = config.get("safety") if isinstance(config.get("safety"), dict) else {}
    for key in ("writes_authored_data", "writes_runtime_logs", "adds_collision", "touches_artifact_routes", "touches_holocore"):
        if safety.get(key) is not False:
            errors.append(f"runtime safety.{key} must be false")
    integration = config.get("world_integration") if isinstance(config.get("world_integration"), dict) else {}
    if str(integration.get("mode") or "") != "world_parented_city_layer":
        errors.append("runtime bridge must use world_parented_city_layer mode")
    preference = integration.get("parent_preference")
    if not isinstance(preference, list) or "root_3d" not in [str(item) for item in preference]:
        errors.append("runtime bridge must prefer root_3d before render fallback")
    summary = build_runtime_summary(ROOT).as_dict()
    if summary["town_count"] != 9:
        errors.append(f"expected 9 towns in 3x3 city, got {summary['town_count']}")
    if summary["neighborhood_count"] < 7:
        errors.append(f"expected at least 7 neighborhoods, got {summary['neighborhood_count']}")
    if summary["citizen_count"] != summary["schedule_frame_citizens"]:
        errors.append("citizen schedule frame did not resolve all citizens")
    if summary["citizen_count"] < 44:
        errors.append(f"expected at least 44 citizens, got {summary['citizen_count']}")
    if summary.get("integration_mode") != "world_parented_city_layer":
        errors.append("runtime summary did not report world integration")
    if errors:
        print("HoloUtopia runtime bridge validation FAILED")
        for error in errors:
            print(" -", error)
        print(json.dumps(summary, indent=2))
        return 2
    print("HoloUtopia runtime bridge validation passed")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
