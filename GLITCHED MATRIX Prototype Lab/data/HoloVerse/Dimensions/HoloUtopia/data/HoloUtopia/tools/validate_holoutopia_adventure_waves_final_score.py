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
    from holoutopia_adventure_simulation import build_adventure_simulation_state, load_adventure_simulation_rules

    rules = load_adventure_simulation_rules(root)
    match = rules.get("match") if isinstance(rules.get("match"), dict) else {}
    start = build_adventure_simulation_state(root, "18:15")
    wave_mid = build_adventure_simulation_state(root, "20:30")
    final = build_adventure_simulation_state(root, "22:59")
    inactive = build_adventure_simulation_state(root, "23:00")
    errors: list[str] = []

    if int(match.get("active_player_slots") or 0) != 4:
        errors.append("active_player_slots_must_stay_4")
    if int(match.get("duration_real_seconds") or 0) != 300:
        errors.append("duration_real_seconds_must_stay_300")
    if int(match.get("max_waves") or 0) < 4:
        errors.append("max_waves_too_low")
    if int(match.get("final_score_window_seconds") or 0) <= 0:
        errors.append("final_score_window_missing")
    if start.get("dimension_entry_active") or not start.get("embedded_hub_dimension_active"):
        errors.append("adventure_must_stay_embedded_in_core_ring")
    if int(start.get("wave_number") or 0) != 1:
        errors.append("start_should_be_wave_1")
    if int(wave_mid.get("wave_number") or 0) < 2:
        errors.append("mid_match_should_advance_waves")
    if int(wave_mid.get("enemy_count") or 0) <= int(start.get("enemy_count") or 0):
        errors.append("later_waves_should_add_enemy_pressure")
    combat = wave_mid.get("combat_state") if isinstance(wave_mid.get("combat_state"), dict) else {}
    if len(combat.get("hit_effects") if isinstance(combat.get("hit_effects"), list) else []) < 4:
        errors.append("hit_effects_should_exist_for_four_heroes")
    summary = combat.get("class_action_summary") if isinstance(combat.get("class_action_summary"), dict) else {}
    if len(summary) < 3:
        errors.append("class_action_visuals_should_be_varied")
    if not bool(final.get("final_score_ready")) or str(final.get("match_phase")) != "final_score":
        errors.append("final_score_should_be_ready_near_end")
    final_state = final.get("final_score_state") if isinstance(final.get("final_score_state"), dict) else {}
    if int(final_state.get("final_score") or 0) <= int(final_state.get("base_score") or 0):
        errors.append("final_score_should_include_end_bonus")
    if str(final_state.get("grade") or "") not in {"S", "A", "B", "C"}:
        errors.append("final_grade_missing")
    if inactive.get("match_active") or inactive.get("combat_active"):
        errors.append("match_should_be_inactive_after_window")
    if errors:
        print("[FAIL] HoloUtopia Adventure Waves/Final Score validation")
        for err in errors:
            print(" -", err)
        return 1
    print("[OK] HoloUtopia Adventure Waves/Final Score validated")
    print(
        f"start_wave={start.get('wave_label')} "
        f"mid_wave={wave_mid.get('wave_label')} "
        f"mid_enemies={wave_mid.get('enemies_alive')}/{wave_mid.get('enemy_count')} "
        f"hit_effects={len(combat.get('hit_effects') if isinstance(combat.get('hit_effects'), list) else [])} "
        f"final_score={final.get('final_score')} grade={final.get('final_grade')} "
        f"external_dimension={final.get('dimension_entry_active')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
