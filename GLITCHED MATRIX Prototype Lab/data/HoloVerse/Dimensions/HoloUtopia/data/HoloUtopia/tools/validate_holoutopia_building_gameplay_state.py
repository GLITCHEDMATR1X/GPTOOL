"""Validate Pass 53 clickable building gameplay-state UI."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from holoutopia_building_gameplay import derive_building_gameplay_state, validate_building_gameplay_state
from holoutopia_building_inspector import inspect_building
from holoutopia_display_names import build_building_panel_tabs, validate_player_panel_text
from holoutopia_game_runtime import HoloUtopiaGameRuntime, load_runtime_config
from holoutopia_snap_panels import MovableSnapPanelManager


def main() -> int:
    issues: list[str] = []
    probes = [
        "res_alpha_lot_07",
        "central_core_civic_ring:core_plaza_octagon",
        "security_gate:block_gate_tower_left",
    ]
    states: dict[str, dict[str, object]] = {}
    for building_id in probes:
        try:
            payload = inspect_building(ROOT, building_id, clock="14:30", danger_state=("security" in building_id))
            record = payload.get("building") if isinstance(payload.get("building"), dict) else {}
            state = derive_building_gameplay_state(record, clock="14:30", danger_state=bool(payload.get("danger_state")))
            state_issues = validate_building_gameplay_state(state)
            if state_issues:
                issues.append(f"{building_id}:state:{state_issues}")
            view = build_building_panel_tabs(payload, holoverse_root=ROOT, debug_raw_ids=False)
            tabs = view.get("tabs") if isinstance(view.get("tabs"), dict) else {}
            for required in ("overview", "status", "people", "activity"):
                if required not in tabs:
                    issues.append(f"{building_id}:missing_tab:{required}")
            status_text = str(tabs.get("status") or "")
            if "Site Status" not in status_text or "Local Actions" not in status_text:
                issues.append(f"{building_id}:status_tab_missing_gameplay_text")
            validation = validate_player_panel_text("\n".join(str(value) for value in tabs.values()))
            if not validation.ok:
                issues.append(f"{building_id}:player_text:{validation.issues[:4]}")
            states[building_id] = {
                "state": state.get("state_label"),
                "priority": state.get("priority_label"),
                "risk": state.get("risk_label"),
                "pressure": state.get("pressure_percent"),
                "civic_value": state.get("civic_value"),
            }
        except Exception as exc:
            issues.append(f"{building_id}:exception:{exc.__class__.__name__}:{exc}")

    config = load_runtime_config(ROOT)
    panels = config.get("panels") if isinstance(config.get("panels"), dict) else {}
    if list(panels.get("building_tabs") or []) != ["overview", "status", "people", "activity"]:
        issues.append("config_building_tabs_not_updated")
    if panels.get("site_card_enabled") is not True:
        issues.append("site_card_not_enabled")
    if panels.get("building_status_is_derived_read_only") is not True:
        issues.append("building_status_not_marked_read_only")
    for method_name in ("_create_or_update_building_site_card", "_clear_building_selection_visuals", "_current_aspect_ratio"):
        if not hasattr(HoloUtopiaGameRuntime, method_name):
            issues.append(f"runtime_missing:{method_name}")
    if not hasattr(MovableSnapPanelManager, "_tab_color"):
        issues.append("panel_manager_missing_active_tab_color_refresh")

    payload = {
        "ok": not issues,
        "runtime_id": config.get("id"),
        "building_tabs": panels.get("building_tabs"),
        "site_card_enabled": panels.get("site_card_enabled"),
        "states": states,
        "issues": issues,
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if not issues else 1


if __name__ == "__main__":
    raise SystemExit(main())
