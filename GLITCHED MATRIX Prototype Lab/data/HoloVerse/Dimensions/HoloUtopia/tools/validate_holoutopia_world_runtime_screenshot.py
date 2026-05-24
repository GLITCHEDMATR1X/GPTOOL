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
    placement = config.get("placement") if isinstance(config.get("placement"), dict) else {}
    safety = config.get("safety") if isinstance(config.get("safety"), dict) else {}
    errors: list[str] = []
    if str(placement.get("root_node_name") or "") != "holoutopia_integrated_city_world":
        errors.append("placement.root_node_name must be holoutopia_integrated_city_world")
    pref = placement.get("parent_preference")
    if pref != ["root_3d", "world_root", "render"]:
        errors.append("placement.parent_preference must prefer root_3d > world_root > render")
    if safety.get("not_a_2d_preview_panel") is not True:
        errors.append("safety.not_a_2d_preview_panel must be true")
    tool = ROOT / "tools" / "render_holoutopia_in_world_runtime_screenshot.py"
    if not tool.exists():
        errors.append(f"missing in-world screenshot tool: {tool}")
    summary = build_runtime_summary(ROOT).as_dict()
    if summary.get("town_count") != 9:
        errors.append("runtime summary must see the complete 3x3 city")
    if summary.get("citizen_count", 0) < 44:
        errors.append("runtime summary must include city citizens")
    payload = {"summary": summary, "placement": placement, "safety": safety, "errors": errors}
    if errors:
        print("HoloUtopia in-world runtime screenshot validation FAILED")
        print(json.dumps(payload, indent=2))
        return 2
    print("HoloUtopia in-world runtime screenshot validation passed")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
