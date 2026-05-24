from __future__ import annotations

import sys
from pathlib import Path


def _root() -> Path:
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        if parent.name.lower() in {"holoverse", "holoutopia"} and (parent / "holoutopia_adventure_simulation.py").exists():
            return parent
    raise SystemExit("Could not find HoloUtopia root")


def main() -> int:
    root = _root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from holoutopia_adventure_simulation import build_adventure_simulation_state

    active = build_adventure_simulation_state(root, "18:15")
    respawn = build_adventure_simulation_state(root, "18:45")
    inactive = build_adventure_simulation_state(root, "06:45")
    errors: list[str] = []
    layout = active.get("hub_ring_layout") if isinstance(active.get("hub_ring_layout"), dict) else {}
    if not active.get("match_active"):
        errors.append("active_match_missing")
    if not active.get("embedded_hub_dimension_active"):
        errors.append("embedded_hub_dimension_not_active")
    if active.get("dimension_entry_active"):
        errors.append("should_not_use_external_dimension_entry")
    if not active.get("combat_active"):
        errors.append("embedded_core_ring_combat_should_be_active")
    if layout.get("location") != "central_hub_circle_around_pyramid":
        errors.append("hub_ring_location_wrong")
    if int(active.get("active_player_count") or 0) != 4:
        errors.append("active_slots_must_equal_4")
    if int(respawn.get("recent_respawn_count") or 0) < 1:
        errors.append("respawn_event_missing")
    if respawn.get("respawn_policy") != "defeated_players_respawn_in_central_hub_circle":
        errors.append("respawn_policy_wrong")
    if int(respawn.get("active_player_count") or 0) != 4:
        errors.append("replacement_did_not_keep_4_active")
    if inactive.get("match_active") or inactive.get("observe_available"):
        errors.append("inactive_morning_should_not_be_observable")
    if errors:
        print("[FAIL] HoloUtopia Adventure Hub Ring validation")
        for err in errors:
            print(" -", err)
        return 1
    print("[OK] HoloUtopia Adventure Hub Ring validated")
    print(f"hub_ring={layout.get('location')} active={active.get('active_player_count')}/4 queue={active.get('queue_count')} respawns={respawn.get('recent_respawn_count')} combat={active.get('combat_active')} external_dimension={active.get('dimension_entry_active')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
