"""Validate HoloUtopia click-select building inspector UI wiring without Panda3D."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = ROOT if (ROOT / "holoutopia_game_runtime.py").exists() and (ROOT.parent / "database" / "utopia").exists() else ROOT / "data" / "HoloUtopia"
if str(MODULE_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE_ROOT))

from holoutopia_building_inspector import inspect_building
from holoutopia_display_names import build_building_panel_tabs, validate_player_panel_text
from holoutopia_game_runtime import HoloUtopiaGameRuntime
from holoutopia_snap_panels import MovableSnapPanelManager


def main() -> int:
    issues: list[str] = []
    probes = ["res_alpha_lot_07", "central_core_civic_ring:core_plaza_octagon"]
    tab_counts: dict[str, int] = {}

    for building_id in probes:
        try:
            payload = inspect_building(MODULE_ROOT, building_id, clock="12:00")
            payload["runtime_context"] = {"holoverse_root": str(MODULE_ROOT)}
            view = build_building_panel_tabs(payload, holoverse_root=MODULE_ROOT, debug_raw_ids=False)
            tabs = view.get("tabs") if isinstance(view.get("tabs"), dict) else {}
            for required in ("overview", "status", "people", "activity"):
                if required not in tabs:
                    issues.append(f"{building_id}: missing building tab {required}")
            full_text = "\n".join(str(value) for value in tabs.values())
            validation = validate_player_panel_text(full_text)
            if not validation.ok:
                issues.append(f"{building_id}: player panel text leaked raw/debug text: {validation.issues[:4]}")
            tab_counts[building_id] = len(tabs)
        except Exception as exc:
            issues.append(f"{building_id}: failed to build building panel tabs: {exc}")

    for method_name in (
        "select_building",
        "_try_select_world_from_camera",
        "_best_building_at_pointer",
        "_create_or_update_building_selection_marker",
    ):
        if not hasattr(HoloUtopiaGameRuntime, method_name):
            issues.append(f"runtime missing {method_name}")
    if not hasattr(MovableSnapPanelManager, "show_building_panel"):
        issues.append("snap panel manager missing show_building_panel")

    config_path = MODULE_ROOT.parent / "database" / "utopia" / "runtime" / "holoutopia_runtime_bridge.json"
    if not config_path.exists():
        config_path = ROOT / "data" / "database" / "utopia" / "runtime" / "holoutopia_runtime_bridge.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    panels = config.get("panels", {}) if isinstance(config.get("panels"), dict) else {}
    if "building_inspector" not in list(panels.get("panel_types") or []):
        issues.append("runtime config does not advertise building_inspector panel type")
    if list(panels.get("building_tabs") or []) != ["overview", "status", "people", "activity"]:
        issues.append("runtime config building_tabs mismatch")

    payload = {
        "ok": not issues,
        "building_click_runtime_methods": 4,
        "building_panel_tabs": tab_counts,
        "panel_types": panels.get("panel_types"),
        "building_tabs": panels.get("building_tabs"),
        "issues": issues,
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if not issues else 1


if __name__ == "__main__":
    raise SystemExit(main())
