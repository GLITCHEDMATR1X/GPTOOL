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
    from holoutopia_adventure_simulation import build_adventure_simulation_state, validate_adventure_simulation_rules
    from holoutopia_citizen_simulation import simulate_city_at_time

    errors = validate_adventure_simulation_rules(root)
    frame = simulate_city_at_time(root, "18:15")
    pop = frame.get("residential_population_model") if isinstance(frame.get("residential_population_model"), dict) else {}
    activity = pop.get("district_activity_model") if isinstance(pop.get("district_activity_model"), dict) else {}
    state = activity.get("adventure_simulation_state") if isinstance(activity.get("adventure_simulation_state"), dict) else {}
    if not state:
        errors.append("adventure_state_missing_from_district_activity_frame")
    if state.get("active_player_count") != 4:
        errors.append("district_activity_frame_does_not_have_4_active_players")
    if not state.get("observe_available"):
        errors.append("observe_gate_not_ready_for_active_match")
    if not state.get("combat_active") or not state.get("score_active"):
        errors.append("pass51c_must_activate_embedded_core_ring_combat_and_score")
    if state.get("dimension_entry_active"):
        errors.append("pass51c_must_not_activate_separate_dimension_route")
    if not state.get("embedded_hub_dimension_active"):
        errors.append("pass51b_must_embed_adventure_dimension_in_core_ring")
    if not state.get("hub_ring_action_active"):
        errors.append("pass51b_core_ring_action_should_be_active")
    # Ensure the inactive morning cannot be observed by clicking the hub.
    morning = build_adventure_simulation_state(root, "06:45")
    if morning.get("observe_available") or morning.get("match_active"):
        errors.append("inactive_morning_hub_should_not_be_observable")
    respawn = build_adventure_simulation_state(root, "18:45")
    if int(respawn.get("recent_respawn_count") or 0) < 1:
        errors.append("defeated_player_should_respawn_in_core_ring_after_elapsed_action")
    if int(respawn.get("active_player_count") or 0) != 4:
        errors.append("replacement_queue_should_keep_four_active_slots_after_respawn")
    if respawn.get("dimension_entry_active"):
        errors.append("respawn_state_should_not_use_external_dimension_route")
    if int(respawn.get("player_defeats") or 0) < 1:
        errors.append("respawn_state_should_record_player_defeat")
    if int(respawn.get("enemies_defeated") or 0) < 1:
        errors.append("respawn_state_should_record_enemy_defeat")
    if int(respawn.get("team_score") or 0) <= int(state.get("team_score") or 0):
        errors.append("team_score_should_progress_during_combat")
    if errors:
        print("[FAIL] HoloUtopia Adventure Simulation validation")
        for item in errors:
            print(" -", item)
        return 1
    print("[OK] HoloUtopia Adventure Simulation Combat validated")
    print(f"active_players={state.get('active_player_count')}/{state.get('max_active_players')} queue={state.get('queue_count')} remaining={state.get('remaining_label')} observe={state.get('observe_available')} hub_ring={state.get('embedded_hub_dimension_active')} combat={state.get('combat_active')} score={state.get('team_score')} respawns={respawn.get('recent_respawn_count')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
