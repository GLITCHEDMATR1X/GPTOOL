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
    active = build_adventure_simulation_state(root, "18:15")
    mid = build_adventure_simulation_state(root, "20:30")
    final = build_adventure_simulation_state(root, "22:59")
    inactive = build_adventure_simulation_state(root, "06:45")
    errors: list[str] = []

    for key in ("show_hero_status_bars", "show_enemy_status_ticks", "show_spawn_pulses", "show_final_scoreboard_lines"):
        if not bool(match.get(key, False)):
            errors.append(f"missing_match_readability_flag_{key}")

    hero_status = active.get("hero_status") if isinstance(active.get("hero_status"), list) else []
    if len(hero_status) != 4:
        errors.append("hero_status_should_have_four_slots")
    for hero in hero_status:
        pct = float(hero.get("hp_percent") or -1.0)
        if pct < 0.0 or pct > 1.0:
            errors.append("hero_hp_percent_out_of_range")
        if str(hero.get("health_band") or "") not in {"stable", "strained", "critical"}:
            errors.append("hero_health_band_invalid")

    combat = active.get("combat_state") if isinstance(active.get("combat_state"), dict) else {}
    overlays = combat.get("combat_readability_overlays") if isinstance(combat.get("combat_readability_overlays"), dict) else {}
    for key in ("hero_status_bars", "enemy_status_ticks", "spawn_pulses", "final_scoreboard_lines"):
        if not bool(overlays.get(key, False)):
            errors.append(f"combat_overlay_missing_{key}")

    spawn_count = int(active.get("spawn_pulse_count") or 0)
    if spawn_count < 4:
        errors.append("spawn_pulses_should_be_visible_for_active_match")
    enemy_summary = active.get("enemy_status_summary") if isinstance(active.get("enemy_status_summary"), dict) else {}
    if int(enemy_summary.get("total") or 0) < int(active.get("enemy_count") or 0):
        errors.append("enemy_status_summary_should_cover_enemy_count")
    if int(mid.get("spawn_pulse_count") or 0) < spawn_count:
        errors.append("later_wave_should_keep_spawn_pulses")

    final_state = final.get("final_score_state") if isinstance(final.get("final_score_state"), dict) else {}
    lines = final_state.get("scoreboard_lines") if isinstance(final_state.get("scoreboard_lines"), list) else []
    if not bool(final.get("final_score_ready")):
        errors.append("final_score_should_be_ready_for_scoreboard")
    if len(lines) < 4:
        errors.append("scoreboard_lines_should_have_four_brief_lines")
    if final.get("dimension_entry_active") or not final.get("embedded_hub_dimension_active"):
        errors.append("readability_pass_must_stay_embedded_in_core_ring")
    if inactive.get("match_active") or inactive.get("combat_active") or inactive.get("observe_available"):
        errors.append("inactive_morning_should_not_run_readability_overlays")

    if errors:
        print("[FAIL] HoloUtopia Adventure Combat Readability validation")
        for err in errors:
            print(" -", err)
        return 1
    print("[OK] HoloUtopia Adventure Combat Readability validated")
    print(
        f"hero_status={len(hero_status)} "
        f"spawn_pulses={spawn_count} "
        f"enemy_summary={enemy_summary.get('alive')}/{enemy_summary.get('total')} "
        f"final_lines={len(lines)} "
        f"final_score={final.get('final_score')} grade={final.get('final_grade')} "
        f"external_dimension={final.get('dimension_entry_active')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
