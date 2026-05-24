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

    start = build_adventure_simulation_state(root, "18:15")
    combat = start.get("combat_state") if isinstance(start.get("combat_state"), dict) else {}
    mid = build_adventure_simulation_state(root, "18:45")
    mid_combat = mid.get("combat_state") if isinstance(mid.get("combat_state"), dict) else {}
    inactive = build_adventure_simulation_state(root, "06:45")
    errors: list[str] = []
    if not start.get("match_active") or not start.get("combat_active"):
        errors.append("active_match_should_have_embedded_combat")
    if start.get("dimension_entry_active"):
        errors.append("combat_must_not_use_external_dimension_entry")
    if int(start.get("active_player_count") or 0) != 4:
        errors.append("combat_must_keep_four_active_players")
    if int(combat.get("enemy_count") or 0) < 4:
        errors.append("combat_enemy_count_too_low")
    if len(combat.get("actions") if isinstance(combat.get("actions"), list) else []) != 4:
        errors.append("combat_should_have_four_action_ticks")
    if int(start.get("team_score") or 0) <= 0:
        errors.append("combat_score_should_start_positive")
    if int(mid.get("recent_respawn_count") or 0) < 1:
        errors.append("mid_match_should_have_respawn_event")
    if int(mid.get("active_player_count") or 0) != 4:
        errors.append("replacement_queue_should_keep_four_active_players")
    if int(mid.get("enemies_defeated") or 0) < 1:
        errors.append("mid_match_should_defeat_at_least_one_enemy")
    if int(mid.get("player_defeats") or 0) < 1:
        errors.append("mid_match_should_record_player_defeat")
    if int(mid.get("team_score") or 0) <= int(start.get("team_score") or 0):
        errors.append("score_should_progress_after_enemy_defeat")
    if inactive.get("match_active") or inactive.get("combat_active") or inactive.get("observe_available"):
        errors.append("inactive_morning_should_not_run_combat")
    if not bool(mid_combat.get("embedded_core_ring_combat")):
        errors.append("combat_state_should_be_marked_embedded_core_ring")
    if errors:
        print("[FAIL] HoloUtopia Adventure Combat validation")
        for err in errors:
            print(" -", err)
        return 1
    print("[OK] HoloUtopia Adventure Combat validated")
    print(f"active={start.get('active_player_count')}/4 enemies={start.get('enemies_alive')}/{start.get('enemy_count')} score={start.get('team_score')} mid_score={mid.get('team_score')} kills={mid.get('enemies_defeated')} respawns={mid.get('recent_respawn_count')} external_dimension={mid.get('dimension_entry_active')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
