"""Central Hub embedded adventure simulation foundation.

Pass 51B keeps the adventure activity inside the Central Simulation/Core hub
circle around the pyramid rather than routing through an artifact or distant
dimension.  The module is intentionally pure Python/read-only so it can be
validated without Panda3D:
- citizens can queue from the Central Hub circle;
- exactly four citizens can be active players per match;
- extra citizens wait in a replacement queue around the hub;
- matches last five real minutes;
- the active adventure dimension is embedded in the hub ring;
- defeated players respawn safely at hub pads while queued citizens fill slots;
- a lightweight combat prototype runs inside the Core Ring bubble with enemies,
  weapon/magic action ticks, HP, replacement events, and live scoring.

Real player control remains staged for later passes. Pass 51E adds clearer hero health/status bars, enemy spawn pulses, class indicators, and final-score board metadata while keeping the action embedded in the Core Ring.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

RULES_REL = Path("database/utopia/simulation/adventure_simulation_rules.json")

_DEFAULT_RULES: dict[str, Any] = {
    "schema": 1,
    "id": "holoutopia_adventure_simulation_rules_v4",
    "runtime_writes_allowed": False,
    "enabled": True,
    "hub": {
        "town_id": "central_core_civic_ring",
        "display_name": "Central Adventure Simulation",
        "host_service_id": "sim_core",
        "observe_requires_active_players": True,
        "embedded_dimension_location": "central_hub_circle_around_pyramid",
        "join_zone_label": "Core Ring",
    },
    "match": {
        "duration_real_seconds": 300,
        "duration_game_hours": 5,
        "active_player_slots": 4,
        "queue_size": 8,
        "replacement_policy": "dead_players_replaced_by_next_queue_member",
        "defeated_respawn_policy": "defeated_players_respawn_in_central_hub_circle",
        "combat_active": True,
        "score_active": True,
        "dimension_entry_active": False,
        "embedded_hub_dimension_active": True,
        "hub_ring_action_active": True,
        "enemy_slots": 6,
        "enemy_reinforce_every_seconds": 70,
        "player_defeat_every_seconds": 45,
        "enemy_score_value": 100,
        "action_score_value": 12,
        "survival_score_value": 5,
        "wave_interval_seconds": 70,
        "max_waves": 4,
        "wave_enemy_bonus": 2,
        "final_score_window_seconds": 60,
        "final_score_bonus_per_survivor": 75,
        "final_score_bonus_per_queue_left": 10,
        "show_hero_status_bars": True,
        "show_enemy_status_ticks": True,
        "show_spawn_pulses": True,
        "show_final_scoreboard_lines": True,
    },
    "daily_match_windows": [
        {"start": "08:00", "label": "morning adventure simulation"},
        {"start": "13:00", "label": "midday adventure simulation"},
        {"start": "18:00", "label": "evening adventure simulation"},
    ],
    "classes": [
        {"id": "arc_mage", "label": "Mage", "weapon": "focus staff", "magic": "arc bolt", "visual": "cyan_arc", "role": "burst_damage"},
        {"id": "blade_guard", "label": "Blade", "weapon": "simulation sword", "magic": "guard flare", "visual": "gold_slash", "role": "frontline"},
        {"id": "rune_archer", "label": "Archer", "weapon": "rune bow", "magic": "mark shot", "visual": "green_arrow", "role": "precision"},
        {"id": "shield_mender", "label": "Mender", "weapon": "light mace", "magic": "heal ward", "visual": "violet_ward", "role": "support"},
    ],
    "observer_gate": {
        "click_target": "central_simulation_core_hub",
        "only_when_active": True,
        "inactive_label": "No active adventure simulation in the Core Ring.",
        "active_label": "Observe active Core Ring adventure simulation.",
    },
    "safety": {
        "read_only": True,
        "no_route_changes": True,
        "no_collision_changes": True,
        "no_artifact_routing": True,
        "no_player_control_yet": True,
        "combat_dimension_not_spawned_yet": False,
        "combat_dimension_embedded_in_hub_ring": True,
        "dimension_embedded_in_hub_ring": True,
        "defeated_respawn_in_hub": True,
    },
}


def data_root_from_holoutopia(holoutopia_root: Path | str | None = None) -> Path:
    root = Path(holoutopia_root or Path(__file__).resolve().parent).resolve()
    return root.parent if root.name.lower() in {"holoverse", "holoutopia"} else root


def _read_json(path: Path, fallback: dict[str, Any]) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return copy.deepcopy(fallback)
    return data if isinstance(data, dict) else copy.deepcopy(fallback)


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_adventure_simulation_rules(holoutopia_root: Path | str | None = None) -> dict[str, Any]:
    data_root = data_root_from_holoutopia(holoutopia_root)
    return _deep_merge(_DEFAULT_RULES, _read_json(data_root / RULES_REL, _DEFAULT_RULES))


def parse_clock_minutes(value: Any) -> int:
    raw = str(value or "00:00").strip()
    if ":" not in raw:
        return 0
    hh, mm = raw.split(":", 1)
    try:
        return max(0, min(23, int(hh))) * 60 + max(0, min(59, int(mm)))
    except Exception:
        return 0


def _format_clock(minutes: int) -> str:
    minutes = int(minutes) % (24 * 60)
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _stable_int(seed: str, modulo: int) -> int:
    if modulo <= 0:
        return 0
    total = 0
    for idx, ch in enumerate(str(seed)):
        total = (total * 131 + (idx + 23) * ord(ch)) % 10000019
    return total % modulo


def _match_window(clock_minutes: int, rules: dict[str, Any]) -> dict[str, Any] | None:
    match = rules.get("match") if isinstance(rules.get("match"), dict) else {}
    duration_game_hours = max(1, int(match.get("duration_game_hours", 5) or 5))
    duration_minutes = duration_game_hours * 60
    windows = rules.get("daily_match_windows") if isinstance(rules.get("daily_match_windows"), list) else []
    for idx, item in enumerate(windows):
        if not isinstance(item, dict):
            continue
        start = parse_clock_minutes(item.get("start", "00:00"))
        end = start + duration_minutes
        if start <= clock_minutes < end:
            elapsed = clock_minutes - start
            return {
                "index": idx,
                "start_minutes": start,
                "end_minutes": end % (24 * 60),
                "elapsed_game_minutes": elapsed,
                "remaining_game_minutes": max(0, duration_minutes - elapsed),
                "duration_game_minutes": duration_minutes,
                "label": str(item.get("label") or "adventure simulation"),
            }
    return None


def _candidate_pool(visible_citizens: dict[str, Any] | None, world_population: int, rules: dict[str, Any], clock_minutes: int) -> list[dict[str, Any]]:
    hub = rules.get("hub") if isinstance(rules.get("hub"), dict) else {}
    hub_town = str(hub.get("town_id") or "central_core_civic_ring")
    values: list[dict[str, Any]] = []
    for cid, citizen in sorted((visible_citizens or {}).items()):
        if not isinstance(citizen, dict):
            continue
        # Prefer public activity citizens already associated with the Central Hub;
        # service-routed citizens from other districts may still queue, but the
        # selected four are represented as entering hub simulation pods.
        values.append({
            "source_id": str(cid),
            "display_name": str(citizen.get("display_name") or cid),
            "resident_sequence": _sequence_from_id(str(cid), fallback=len(values) + 1),
            "home_garrison": str(citizen.get("garrison_id") or "residential_alpha_virtual_garrison"),
            "source_town_id": str(citizen.get("town_id") or hub_town),
            "source_activity": str(citizen.get("current_task_readable") or citizen.get("activity_status") or "city activity"),
        })
    if len(values) < 12:
        population = max(1, int(world_population or 1000))
        seed_offset = (clock_minutes * 41) % population
        for idx in range(12 - len(values)):
            seq = ((seed_offset + idx * 73) % population) + 1
            values.append({
                "source_id": f"virtual_resident_{seq:04d}",
                "display_name": f"Resident {seq:04d}",
                "resident_sequence": seq,
                "home_garrison": "residential_alpha_virtual_garrison",
                "source_town_id": hub_town,
                "source_activity": "queued from Residential garrison",
            })
    return values


def _sequence_from_id(value: str, fallback: int = 1) -> int:
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    try:
        return max(1, int(digits[-4:]))
    except Exception:
        return int(fallback)


def _brief(value: Any, max_chars: int = 44) -> str:
    raw = " ".join(str(value or "").split())
    if len(raw) <= max_chars:
        return raw
    return raw[: max(3, max_chars - 1)].rstrip(" ,.;:") + "…"


def _elapsed_real_seconds(window: dict[str, Any] | None, duration_real_seconds: int) -> int:
    if not isinstance(window, dict):
        return 0
    elapsed_game = float(window.get("elapsed_game_minutes", 0) or 0)
    duration_game = max(1.0, float(window.get("duration_game_minutes", 300) or 300))
    return max(0, int(round(float(duration_real_seconds) * (elapsed_game / duration_game))))


def _build_hub_ring_layout() -> dict[str, Any]:
    return {
        "location": "central_hub_circle_around_pyramid",
        "display_name": "Core Ring Adventure Bubble",
        "center": {"x": 0.0, "y": 0.0, "z": 67.0},
        "arena_radius": 54.0,
        "join_radius": 76.0,
        "respawn_radius": 24.0,
        "queue_radius": 92.0,
        "active_slot_radius": 48.0,
        "dimension_embedded_in_hub": True,
        "separate_dimension_route": False,
        "hub_click_observes_ring": True,
    }


def _apply_deterministic_respawn_cycle(
    active_players: list[dict[str, Any]],
    queue: list[dict[str, Any]],
    *,
    elapsed_real_seconds: int,
    classes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Model the hub-ring replacement rule without running combat AI yet."""
    if elapsed_real_seconds < 45 or not active_players or not queue:
        return []
    # One deterministic example event per validator/screenshot moment.  Later
    # passes will replace this with real enemy damage/death events.
    slot_index = ((elapsed_real_seconds // 45) - 1) % len(active_players)
    defeated = dict(active_players[slot_index])
    replacement = dict(queue.pop(0))
    klass = classes[(slot_index + 1) % len(classes)] if classes else {}
    active_players[slot_index] = {
        "slot": slot_index + 1,
        "citizen_id": str(replacement.get("citizen_id") or f"queued_{slot_index + 1:02d}"),
        "display_name": str(replacement.get("display_name") or "Queued Resident"),
        "class_id": str(klass.get("id") or "adventurer"),
        "class_label": str(klass.get("label") or replacement.get("preferred_class") or "Adventurer"),
        "weapon": str(klass.get("weapon") or "simulation weapon"),
        "magic": str(klass.get("magic") or "simulation spell"),
        "status": "active_in_core_ring_replacement",
        "score": 0,
        "deaths": 0,
        "replace_if_dead": True,
        "home_garrison": "residential_alpha_virtual_garrison",
        "joined_from_queue_position": int(replacement.get("queue_position") or 1),
    }
    return [{
        "slot": slot_index + 1,
        "defeated_citizen_id": str(defeated.get("citizen_id") or "unknown"),
        "defeated_display_name": str(defeated.get("display_name") or "Resident"),
        "replacement_citizen_id": str(active_players[slot_index].get("citizen_id") or "unknown"),
        "replacement_display_name": str(active_players[slot_index].get("display_name") or "Resident"),
        "respawn_location": "central_hub_circle_respawn_pad",
        "respawn_policy": "defeated_players_respawn_in_central_hub_circle",
        "status": "defeated_respawned_to_hub_and_slot_refilled",
    }]


def _enemy_template(idx: int) -> dict[str, Any]:
    kinds = [
        ("void_wisp", "Wisp", 42),
        ("shard_imp", "Imp", 48),
        ("rune_sentinel", "Sentinel", 64),
        ("hollow_knight", "Hollow", 76),
        ("static_mage", "Static", 58),
        ("rift_beast", "Rift", 92),
    ]
    kind, label, hp = kinds[idx % len(kinds)]
    return {"enemy_id": f"enemy_{idx + 1:02d}", "type_id": kind, "label": label, "max_hp": hp}


def _action_for_player(player: dict[str, Any], idx: int, elapsed_real_seconds: int, enemies: list[dict[str, Any]]) -> dict[str, Any]:
    target = enemies[(idx + max(0, elapsed_real_seconds // 12)) % max(1, len(enemies))] if enemies else {"enemy_id": "enemy_00", "label": "Rift"}
    class_id = str(player.get("class_id") or "adventurer")
    if class_id == "arc_mage":
        action_type, verb, effect = "magic", "casts", "arc bolt"
    elif class_id == "rune_archer":
        action_type, verb, effect = "weapon", "fires", "rune arrow"
    elif class_id == "shield_mender":
        action_type, verb, effect = "magic", "raises", "heal ward"
    else:
        action_type, verb, effect = "weapon", "strikes", "simulation sword"
    return {
        "actor_slot": int(player.get("slot") or idx + 1),
        "actor_id": str(player.get("citizen_id") or f"slot_{idx + 1}"),
        "actor_label": str(player.get("display_name") or f"Hero {idx + 1}"),
        "action_type": action_type,
        "verb": verb,
        "effect": effect,
        "target_enemy_id": str(target.get("enemy_id") or "enemy_00"),
        "target_label": str(target.get("label") or "Enemy"),
        "damage": 9 + ((elapsed_real_seconds + idx * 7) % 11),
        "brief": _brief(f"{str(player.get('class_label') or 'Hero')} {verb} {effect}", 34),
    }


def _wave_state(elapsed_real_seconds: int, rules: dict[str, Any], base_enemy_slots: int) -> dict[str, Any]:
    match = rules.get("match") if isinstance(rules.get("match"), dict) else {}
    wave_interval = max(20, int(match.get("wave_interval_seconds", 70) or 70))
    max_waves = max(1, int(match.get("max_waves", 4) or 4))
    wave_bonus = max(0, int(match.get("wave_enemy_bonus", 2) or 2))
    wave_number = min(max_waves, 1 + max(0, int(elapsed_real_seconds)) // wave_interval)
    wave_progress = (max(0, int(elapsed_real_seconds)) % wave_interval) / float(wave_interval)
    active_enemy_slots = int(base_enemy_slots) + max(0, wave_number - 1) * wave_bonus
    return {
        "wave_number": wave_number,
        "max_waves": max_waves,
        "wave_interval_seconds": wave_interval,
        "wave_progress": round(wave_progress, 3),
        "enemy_slots": active_enemy_slots,
        "wave_label": f"Wave {wave_number}/{max_waves}",
        "next_wave_seconds": 0 if wave_number >= max_waves else max(0, wave_interval - (max(0, int(elapsed_real_seconds)) % wave_interval)),
    }


def _class_visual_for_action(action: dict[str, Any]) -> dict[str, Any]:
    effect = str(action.get("effect") or "")
    if "arc" in effect:
        return {"visual_id": "cyan_arc_bolt", "color": "cyan", "shape": "forked_arc"}
    if "rune" in effect or "arrow" in effect:
        return {"visual_id": "green_rune_arrow", "color": "green", "shape": "straight_shot"}
    if "heal" in effect or "ward" in effect:
        return {"visual_id": "violet_heal_ward", "color": "violet", "shape": "shield_ring"}
    return {"visual_id": "gold_blade_slash", "color": "gold", "shape": "slash_tick"}


def _health_band(percent: float) -> str:
    pct = max(0.0, min(1.0, float(percent)))
    if pct >= 0.70:
        return "stable"
    if pct >= 0.38:
        return "strained"
    return "critical"


def _build_hero_status(active_players: list[dict[str, Any]]) -> list[dict[str, Any]]:
    status: list[dict[str, Any]] = []
    for player in active_players[:4]:
        max_hp = max(1, int(player.get("max_hp") or 100))
        hp = max(0, min(max_hp, int(player.get("hp") or max_hp)))
        pct = hp / float(max_hp)
        status.append({
            "slot": int(player.get("slot") or len(status) + 1),
            "citizen_id": str(player.get("citizen_id") or "unknown"),
            "display_name": str(player.get("display_name") or "Resident"),
            "class_label": str(player.get("class_label") or "Adventurer"),
            "class_id": str(player.get("class_id") or "adventurer"),
            "hp": hp,
            "max_hp": max_hp,
            "hp_percent": round(pct, 3),
            "health_band": _health_band(pct),
            "score": int(player.get("score") or 0),
            "status": str(player.get("combat_status") or player.get("status") or "active"),
        })
    return status


def _build_enemy_status_summary(enemies: list[dict[str, Any]]) -> dict[str, Any]:
    alive = [e for e in enemies if str(e.get("status") or "") != "defeated"]
    wounded = 0
    critical = 0
    for enemy in alive:
        max_hp = max(1, int(enemy.get("max_hp") or 1))
        hp = max(0, int(enemy.get("hp") or 0))
        pct = hp / float(max_hp)
        if pct < 0.35:
            critical += 1
        elif pct < 0.70:
            wounded += 1
    return {
        "alive": len(alive),
        "defeated": max(0, len(enemies) - len(alive)),
        "wounded": wounded,
        "critical": critical,
        "total": len(enemies),
    }


def _build_spawn_pulses(wave: dict[str, Any], elapsed_real_seconds: int, enemy_slots: int) -> list[dict[str, Any]]:
    wave_number = max(1, int(wave.get("wave_number") or 1))
    progress = max(0.0, min(1.0, float(wave.get("wave_progress") or 0.0)))
    # Spawn pulses sit on the outer edge of the embedded bubble.  They are
    # status/readability markers only, not extra enemies or collision geometry.
    pulses: list[dict[str, Any]] = []
    pulse_count = min(8, max(4, int(enemy_slots // 2)))
    phase = (int(elapsed_real_seconds) % 30) / 30.0
    for idx in range(pulse_count):
        angle = (idx / float(pulse_count)) * 6.283185307179586 + wave_number * 0.17 + phase * 0.45
        pulses.append({
            "pulse_id": f"wave_{wave_number}_spawn_{idx + 1:02d}",
            "wave_number": wave_number,
            "ring_angle": round(angle, 3),
            "ring_radius": 58.0 + (idx % 2) * 8.0,
            "intensity": round(0.35 + 0.55 * progress, 3),
            "status": "incoming_wave_pulse" if wave_number < int(wave.get("max_waves") or wave_number) else "final_wave_pulse",
        })
    return pulses


def _final_score_state(*, active_players: list[dict[str, Any]], queue: list[dict[str, Any]], combat_state: dict[str, Any], elapsed_real_seconds: int, duration_real_seconds: int, rules: dict[str, Any]) -> dict[str, Any]:
    match = rules.get("match") if isinstance(rules.get("match"), dict) else {}
    final_window = max(1, int(match.get("final_score_window_seconds", 10) or 10))
    final_ready = bool(duration_real_seconds - max(0, int(elapsed_real_seconds)) <= final_window)
    survivor_count = len(active_players)
    queue_left = len(queue)
    survivor_bonus = survivor_count * int(match.get("final_score_bonus_per_survivor", 75) or 75)
    queue_bonus = queue_left * int(match.get("final_score_bonus_per_queue_left", 10) or 10)
    base_score = int(combat_state.get("team_score") or 0)
    final_score = base_score + (survivor_bonus + queue_bonus if final_ready else 0)
    grade = "S" if final_score >= 650 else "A" if final_score >= 450 else "B" if final_score >= 260 else "C"
    scoreboard_lines = [
        f"Final Score {final_score}",
        f"Grade {grade}",
        f"Survivors {survivor_count}  Queue {queue_left}",
        f"Bonus +{survivor_bonus + queue_bonus if final_ready else 0}",
    ]
    return {
        "final_score_ready": final_ready,
        "final_window_seconds": final_window,
        "base_score": base_score,
        "survivor_bonus": survivor_bonus if final_ready else 0,
        "queue_bonus": queue_bonus if final_ready else 0,
        "final_score": final_score,
        "survivors": survivor_count,
        "queue_remaining": queue_left,
        "grade": grade,
        "summary": f"Final score {final_score} Grade {grade}" if final_ready else "Final score pending",
        "scoreboard_lines": scoreboard_lines if final_ready else ["Final score pending"],
    }


def _build_core_ring_combat_state(active_players: list[dict[str, Any]], *, elapsed_real_seconds: int, rules: dict[str, Any], recent_respawns: list[dict[str, Any]], queue: list[dict[str, Any]] | None = None, duration_real_seconds: int = 300) -> dict[str, Any]:
    match = rules.get("match") if isinstance(rules.get("match"), dict) else {}
    combat_active = bool(active_players and match.get("combat_active", True))
    score_active = bool(active_players and match.get("score_active", True))
    base_enemy_slots = max(1, int(match.get("enemy_slots", 6) or 6))
    wave = _wave_state(elapsed_real_seconds, rules, base_enemy_slots)
    enemy_slots = max(base_enemy_slots, int(wave.get("enemy_slots") or base_enemy_slots))
    # One defeated enemy roughly every 35 seconds, with wave reinforcements keeping
    # the ring active.  Counts are deterministic for validation/screenshots.
    defeated_enemy_count = min(enemy_slots, max(0, int(elapsed_real_seconds) // 35)) if combat_active else 0
    action_tick = max(0, int(elapsed_real_seconds) // 6)
    enemies: list[dict[str, Any]] = []
    for idx in range(enemy_slots):
        e = _enemy_template(idx)
        defeated = idx < defeated_enemy_count
        max_hp = int(e.get("max_hp") or 50) + max(0, int(wave.get("wave_number") or 1) - 1) * 8
        hp_loss = (action_tick * (7 + idx * 3) + idx * 5 + int(wave.get("wave_number") or 1) * 4) % max(1, max_hp + 15)
        hp = 0 if defeated else max(6, max_hp - hp_loss)
        angle = (idx / float(enemy_slots)) * 6.283185307179586 + 0.32 + (int(wave.get("wave_number") or 1) - 1) * 0.11
        e.update({
            "slot": idx + 1,
            "hp": hp,
            "max_hp": max_hp,
            "status": "defeated" if defeated else "engaged",
            "ring_angle": round(angle, 3),
            "ring_radius": 34.0 + (idx % 3) * 8.0,
            "wave_number": int(wave.get("wave_number") or 1),
        })
        enemies.append(e)
    alive_enemies = [e for e in enemies if str(e.get("status")) != "defeated"]
    actions = [_action_for_player(player, idx, elapsed_real_seconds, alive_enemies or enemies) for idx, player in enumerate(active_players[:4])] if combat_active else []
    for action in actions:
        action.update(_class_visual_for_action(action))
    hit_effects: list[dict[str, Any]] = []
    for idx, action in enumerate(actions):
        if not enemies:
            continue
        target = enemies[idx % len(enemies)]
        hit_effects.append({
            "source_slot": int(action.get("actor_slot") or idx + 1),
            "target_enemy_id": str(target.get("enemy_id") or f"enemy_{idx + 1:02d}"),
            "visual_id": str(action.get("visual_id") or "hit_tick"),
            "color": str(action.get("color") or "cyan"),
            "ring_angle": float(target.get("ring_angle") or 0.0),
            "ring_radius": float(target.get("ring_radius") or 40.0),
            "pulse": round(((int(elapsed_real_seconds) + idx * 9) % 18) / 18.0, 3),
        })
    player_defeats = int(len(recent_respawns))
    team_score = 0
    if score_active:
        team_score += defeated_enemy_count * int(match.get("enemy_score_value", 100) or 100)
        team_score += len(actions) * int(match.get("action_score_value", 12) or 12)
        team_score += max(0, int(elapsed_real_seconds) // 20) * int(match.get("survival_score_value", 5) or 5)
        team_score += max(0, int(wave.get("wave_number") or 1) - 1) * 35
        team_score -= player_defeats * 20
        team_score = max(0, team_score)
    for idx, player in enumerate(active_players):
        base_hp = 100 - ((int(elapsed_real_seconds) * (idx + 3)) % 41)
        if recent_respawns and idx == int(recent_respawns[0].get("slot", 0) or -1) - 1:
            base_hp = 100
        player["hp"] = max(25, int(base_hp))
        player["max_hp"] = 100
        player["combat_status"] = "active_combat"
        player["score"] = int(team_score // max(1, len(active_players)))
        player["wave_number"] = int(wave.get("wave_number") or 1)
    hero_status = _build_hero_status(active_players)
    enemy_status_summary = _build_enemy_status_summary(enemies)
    spawn_pulses = _build_spawn_pulses(wave, elapsed_real_seconds, enemy_slots) if combat_active else []
    event_log = []
    if actions:
        event_log.append(_brief(actions[0].get("brief"), 40))
    if int(wave.get("wave_number") or 1) > 1:
        event_log.append(str(wave.get("wave_label") or "Wave active"))
    if defeated_enemy_count:
        event_log.append(f"Enemy defeated x{defeated_enemy_count}")
    if player_defeats:
        event_log.append(f"Hero respawn x{player_defeats}")
    final_state = _final_score_state(
        active_players=active_players,
        queue=queue or [],
        combat_state={"team_score": team_score},
        elapsed_real_seconds=elapsed_real_seconds,
        duration_real_seconds=duration_real_seconds,
        rules=rules,
    )
    if bool(final_state.get("final_score_ready")):
        event_log.insert(0, str(final_state.get("summary") or "Final score ready"))
    class_summary = {str(action.get("visual_id") or action.get("effect") or "action"): 0 for action in actions}
    for action in actions:
        key = str(action.get("visual_id") or action.get("effect") or "action")
        class_summary[key] = class_summary.get(key, 0) + 1
    return {
        "combat_active": combat_active,
        "score_active": score_active,
        "enemy_count": enemy_slots,
        "enemies_alive": len(alive_enemies),
        "enemies_defeated": defeated_enemy_count,
        "player_defeats": player_defeats,
        "team_score": team_score,
        "actions": actions,
        "class_action_summary": dict(sorted(class_summary.items())),
        "hero_status": hero_status,
        "enemy_status_summary": enemy_status_summary,
        "spawn_pulses": spawn_pulses,
        "hit_effects": hit_effects,
        "enemies": enemies,
        "wave_state": wave,
        "wave_number": int(wave.get("wave_number") or 1),
        "max_waves": int(wave.get("max_waves") or 1),
        "wave_label": str(wave.get("wave_label") or "Wave 1"),
        "event_log": event_log[:5],
        "final_score_state": final_state,
        "final_score_ready": bool(final_state.get("final_score_ready")),
        "final_score": int(final_state.get("final_score") or team_score),
        "final_grade": str(final_state.get("grade") or "C"),
        "combat_line": f"Combat: {len(active_players)}/4 heroes | {wave.get('wave_label')} | foes {len(alive_enemies)}/{enemy_slots} | score {team_score} | K{defeated_enemy_count} D{player_defeats}" if combat_active else "Combat: idle",
        "combat_readability_overlays": {
            "hero_status_bars": bool(match.get("show_hero_status_bars", True)),
            "enemy_status_ticks": bool(match.get("show_enemy_status_ticks", True)),
            "spawn_pulses": bool(match.get("show_spawn_pulses", True)),
            "final_scoreboard_lines": bool(match.get("show_final_scoreboard_lines", True)),
        },
        "embedded_core_ring_combat": True,
    }


def build_adventure_simulation_state(
    holoutopia_root: Path | str | None,
    clock: str,
    *,
    visible_citizens: dict[str, Any] | None = None,
    world_population: int = 1000,
    rules: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the Central Hub adventure-simulation queue/match state."""
    rules = rules if isinstance(rules, dict) else load_adventure_simulation_rules(holoutopia_root)
    hub = rules.get("hub") if isinstance(rules.get("hub"), dict) else {}
    match = rules.get("match") if isinstance(rules.get("match"), dict) else {}
    observer = rules.get("observer_gate") if isinstance(rules.get("observer_gate"), dict) else {}
    enabled = bool(rules.get("enabled", True))
    clock_minutes = parse_clock_minutes(clock)
    window = _match_window(clock_minutes, rules) if enabled else None
    slot_count = max(1, int(match.get("active_player_slots", 4) or 4))
    queue_size = max(0, int(match.get("queue_size", 8) or 8))
    duration_real_seconds = max(1, int(match.get("duration_real_seconds", 300) or 300))
    active_players: list[dict[str, Any]] = []
    queue: list[dict[str, Any]] = []
    classes = [c for c in (rules.get("classes") if isinstance(rules.get("classes"), list) else []) if isinstance(c, dict)] or _DEFAULT_RULES["classes"]
    if window is not None:
        pool = _candidate_pool(visible_citizens, world_population, rules, clock_minutes)
        # Stable rotation keeps matches from using the same first four citizens
        # every day/time, while validators stay deterministic.
        rotation = _stable_int(f"{clock}:{window.get('index')}", max(1, len(pool)))
        pool = pool[rotation:] + pool[:rotation]
        match_id = f"adv_sim_day0_{int(window.get('index', 0)):02d}_{_format_clock(int(window.get('start_minutes', 0))).replace(':', '')}"
        for slot, person in enumerate(pool[:slot_count]):
            c = classes[slot % len(classes)]
            active_players.append({
                "slot": slot + 1,
                "citizen_id": str(person.get("source_id") or f"resident_{slot + 1:02d}"),
                "display_name": str(person.get("display_name") or f"Resident {slot + 1:04d}"),
                "class_id": str(c.get("id") or "adventurer"),
                "class_label": str(c.get("label") or "Adventurer"),
                "weapon": str(c.get("weapon") or "simulation weapon"),
                "magic": str(c.get("magic") or "simulation spell"),
                "status": "active_in_core_ring",
                "score": 0,
                "deaths": 0,
                "replace_if_dead": True,
                "home_garrison": str(person.get("home_garrison") or "residential_alpha_virtual_garrison"),
            })
        for idx, person in enumerate(pool[slot_count:slot_count + queue_size]):
            c = classes[(idx + slot_count) % len(classes)]
            queue.append({
                "queue_position": idx + 1,
                "citizen_id": str(person.get("source_id") or f"queued_{idx + 1:02d}"),
                "display_name": str(person.get("display_name") or f"Resident {idx + 1:04d}"),
                "preferred_class": str(c.get("label") or "Adventurer"),
                "status": "waiting_for_replacement_slot",
            })
    else:
        match_id = ""

    elapsed_real_seconds = _elapsed_real_seconds(window, duration_real_seconds)
    hub_ring_layout = _build_hub_ring_layout()
    recent_respawns = _apply_deterministic_respawn_cycle(
        active_players,
        queue,
        elapsed_real_seconds=elapsed_real_seconds,
        classes=classes,
    ) if window is not None else []

    combat_state = _build_core_ring_combat_state(
        active_players,
        elapsed_real_seconds=elapsed_real_seconds,
        rules=rules,
        recent_respawns=recent_respawns,
        queue=queue,
        duration_real_seconds=duration_real_seconds,
    ) if window is not None else {"combat_active": False, "score_active": False, "combat_line": "Combat: idle", "team_score": 0, "enemies_alive": 0, "enemies_defeated": 0, "player_defeats": 0, "actions": [], "enemies": [], "wave_number": 0, "wave_label": "No wave", "final_score_ready": False}

    active = bool(active_players)
    remaining_real_seconds = 0
    remaining_label = "idle"
    if window is not None:
        remaining_fraction = float(window.get("remaining_game_minutes", 0)) / max(1.0, float(window.get("duration_game_minutes", 300)))
        remaining_real_seconds = max(0, int(round(duration_real_seconds * remaining_fraction)))
        remaining_label = f"{remaining_real_seconds // 60:02d}:{remaining_real_seconds % 60:02d}"
    observe_available = bool(active and observer.get("only_when_active", True)) or bool(active and not observer.get("only_when_active", True))
    return {
        "schema": 1,
        "id": "holoutopia_adventure_simulation_state_v1",
        "clock": str(clock),
        "enabled": enabled,
        "hub_town_id": str(hub.get("town_id") or "central_core_civic_ring"),
        "hub_display_name": str(hub.get("display_name") or "Central Adventure Simulation"),
        "match_active": active,
        "match_id": match_id,
        "match_label": str(window.get("label") if isinstance(window, dict) else "No active match"),
        "active_player_count": len(active_players),
        "max_active_players": slot_count,
        "queue_count": len(queue),
        "max_queue_size": queue_size,
        "duration_real_seconds": duration_real_seconds,
        "duration_game_hours": int(match.get("duration_game_hours", 5) or 5),
        "remaining_real_seconds": remaining_real_seconds,
        "remaining_label": remaining_label,
        "observe_available": observe_available,
        "hub_click_action": str(observer.get("active_label") if observe_available else observer.get("inactive_label") or "No active adventure simulation."),
        "observer_mode_ready": observe_available,
        "dimension_entry_active": False,
        "embedded_hub_dimension_active": bool(active and match.get("embedded_hub_dimension_active", True)),
        "hub_ring_action_active": bool(active and match.get("hub_ring_action_active", True)),
        "hub_ring_layout": hub_ring_layout,
        "combat_active": bool(combat_state.get("combat_active")),
        "score_active": bool(combat_state.get("score_active")),
        "combat_state": combat_state,
        "combat_line": str(combat_state.get("combat_line") or "Combat: idle"),
        "team_score": int(combat_state.get("team_score") or 0),
        "enemy_count": int(combat_state.get("enemy_count") or 0),
        "enemies_alive": int(combat_state.get("enemies_alive") or 0),
        "enemies_defeated": int(combat_state.get("enemies_defeated") or 0),
        "player_defeats": int(combat_state.get("player_defeats") or 0),
        "wave_number": int(combat_state.get("wave_number") or 0),
        "max_waves": int(combat_state.get("max_waves") or 0),
        "wave_label": str(combat_state.get("wave_label") or "No wave"),
        "hit_effect_count": len(combat_state.get("hit_effects") if isinstance(combat_state.get("hit_effects"), list) else []),
        "hero_status": combat_state.get("hero_status") if isinstance(combat_state.get("hero_status"), list) else [],
        "enemy_status_summary": combat_state.get("enemy_status_summary") if isinstance(combat_state.get("enemy_status_summary"), dict) else {},
        "spawn_pulse_count": len(combat_state.get("spawn_pulses") if isinstance(combat_state.get("spawn_pulses"), list) else []),
        "combat_readability_overlays": combat_state.get("combat_readability_overlays") if isinstance(combat_state.get("combat_readability_overlays"), dict) else {},
        "final_score_ready": bool(combat_state.get("final_score_ready")),
        "final_score_state": combat_state.get("final_score_state") if isinstance(combat_state.get("final_score_state"), dict) else {},
        "final_score": int(combat_state.get("final_score") or combat_state.get("team_score") or 0),
        "final_grade": str(combat_state.get("final_grade") or ""),
        "match_phase": "final_score" if bool(combat_state.get("final_score_ready")) else ("combat" if bool(combat_state.get("combat_active")) else "idle"),
        "elapsed_real_seconds": elapsed_real_seconds,
        "active_players": active_players,
        "replacement_queue": queue,
        "recent_respawns": recent_respawns,
        "recent_respawn_count": len(recent_respawns),
        "respawn_policy": str(match.get("defeated_respawn_policy") or "defeated_players_respawn_in_central_hub_circle"),
        "replacement_policy": str(match.get("replacement_policy") or "dead_players_replaced_by_next_queue_member"),
        "participant_summary": _participant_summary(active_players, queue),
        "watch_line": format_adventure_watch_line({
            "match_active": active,
            "active_player_count": len(active_players),
            "max_active_players": slot_count,
            "queue_count": len(queue),
            "remaining_label": remaining_label,
            "observe_available": observe_available,
            "embedded_hub_dimension_active": bool(active and match.get("embedded_hub_dimension_active", True)),
            "recent_respawn_count": len(recent_respawns),
            "combat_active": bool(combat_state.get("combat_active")),
            "team_score": int(combat_state.get("team_score") or 0),
            "enemies_alive": int(combat_state.get("enemies_alive") or 0),
            "enemies_defeated": int(combat_state.get("enemies_defeated") or 0),
            "player_defeats": int(combat_state.get("player_defeats") or 0),
            "wave_label": str(combat_state.get("wave_label") or ""),
            "final_score_ready": bool(combat_state.get("final_score_ready")),
            "final_score": int(combat_state.get("final_score") or combat_state.get("team_score") or 0),
            "final_grade": str(combat_state.get("final_grade") or ""),
        }),
        "safety": dict(rules.get("safety") if isinstance(rules.get("safety"), dict) else {}),
    }


def _participant_summary(active_players: list[dict[str, Any]], queue: list[dict[str, Any]]) -> dict[str, Any]:
    classes = {}
    for player in active_players:
        label = str(player.get("class_label") or "Adventurer")
        classes[label] = classes.get(label, 0) + 1
    return {
        "active_slots": [f"{p.get('display_name')}:{p.get('class_label')}" for p in active_players],
        "queued_names": [str(q.get("display_name") or "Resident") for q in queue[:4]],
        "class_counts": dict(sorted(classes.items())),
    }


def format_adventure_watch_line(state: dict[str, Any]) -> str:
    if not bool(state.get("match_active")):
        return "Adventure: idle | click Core unavailable"
    active = int(state.get("active_player_count") or 0)
    max_players = int(state.get("max_active_players") or 4)
    queue = int(state.get("queue_count") or 0)
    remaining = str(state.get("remaining_label") or "00:00")
    gate = "core ring ready" if bool(state.get("observe_available")) else "not observable"
    ring = "hub bubble" if bool(state.get("embedded_hub_dimension_active")) else "idle hub"
    respawns = int(state.get("recent_respawn_count") or 0)
    combat = "combat" if bool(state.get("combat_active")) else ring
    score = int(state.get("team_score") or 0)
    kills = int(state.get("enemies_defeated") or 0)
    defeats = int(state.get("player_defeats") or respawns)
    wave = str(state.get("wave_label") or "").strip()
    if bool(state.get("final_score_ready")):
        final_score = int(state.get("final_score") or score)
        grade = str(state.get("final_grade") or "")
        return f"Adventure: FINAL | {active}/{max_players} active | {wave or 'Wave'} | S{final_score} {grade}".strip()
    suffix = f" | {wave} | K{kills} D{defeats} S{score}" if bool(state.get("combat_active")) else (f" | respawn {respawns}" if respawns else "")
    return f"Adventure: {active}/{max_players} active | Q{queue} | {remaining} | {combat} | {gate}{suffix}"


def validate_adventure_simulation_rules(holoutopia_root: Path | str | None = None) -> list[str]:
    errors: list[str] = []
    rules = load_adventure_simulation_rules(holoutopia_root)
    match = rules.get("match") if isinstance(rules.get("match"), dict) else {}
    safety = rules.get("safety") if isinstance(rules.get("safety"), dict) else {}
    if bool(rules.get("runtime_writes_allowed", True)):
        errors.append("runtime_writes_allowed_must_be_false")
    if int(match.get("active_player_slots", 0) or 0) != 4:
        errors.append("active_player_slots_must_be_4")
    if int(match.get("duration_real_seconds", 0) or 0) != 300:
        errors.append("duration_real_seconds_must_be_300")
    if not bool(match.get("combat_active", False)):
        errors.append("combat_should_be_active_for_pass51c")
    if not bool(match.get("score_active", False)):
        errors.append("score_should_be_active_for_pass51c")
    if int(match.get("max_waves", 0) or 0) < 3:
        errors.append("max_waves_should_support_pass51d")
    if int(match.get("final_score_window_seconds", 0) or 0) <= 0:
        errors.append("final_score_window_missing_for_pass51d")
    for key in ("show_hero_status_bars", "show_enemy_status_ticks", "show_spawn_pulses", "show_final_scoreboard_lines"):
        if not bool(match.get(key, False)):
            errors.append(f"readability_overlay_missing_{key}")
    if bool(match.get("dimension_entry_active", True)):
        errors.append("separate_dimension_entry_should_not_be_active")
    if not bool(match.get("embedded_hub_dimension_active", False)):
        errors.append("embedded_hub_dimension_must_be_active")
    for key in ("read_only", "no_route_changes", "no_collision_changes", "no_artifact_routing", "no_player_control_yet", "combat_dimension_embedded_in_hub_ring"):
        if not bool(safety.get(key, False)):
            errors.append(f"safety_missing_{key}")
    inactive = build_adventure_simulation_state(holoutopia_root, "06:45")
    if inactive.get("match_active") or inactive.get("observe_available"):
        errors.append("inactive_morning_state_should_not_be_observable")
    active = build_adventure_simulation_state(holoutopia_root, "18:15")
    if not active.get("match_active") or not active.get("observe_available"):
        errors.append("active_evening_state_should_be_observable")
    if int(active.get("active_player_count") or 0) != 4:
        errors.append("active_evening_state_must_have_4_players")
    if int(active.get("queue_count") or 0) < 1:
        errors.append("active_evening_state_should_have_replacement_queue")
    if not bool(active.get("combat_active")):
        errors.append("active_evening_state_should_have_core_ring_combat")
    combat = active.get("combat_state") if isinstance(active.get("combat_state"), dict) else {}
    if int(combat.get("enemy_count") or 0) < 4:
        errors.append("combat_state_should_have_enemies")
    if int(active.get("team_score") or 0) <= 0:
        errors.append("active_evening_state_should_have_live_score")
    if len(active.get("hero_status") if isinstance(active.get("hero_status"), list) else []) != 4:
        errors.append("active_evening_state_should_have_four_hero_status_bars")
    if int(active.get("spawn_pulse_count") or 0) < 4:
        errors.append("active_evening_state_should_have_spawn_pulses")
    if not bool(active.get("embedded_hub_dimension_active")):
        errors.append("active_evening_state_must_embed_dimension_in_hub")
    if active.get("dimension_entry_active"):
        errors.append("active_evening_state_must_not_use_separate_dimension_route")
    respawn = build_adventure_simulation_state(holoutopia_root, "18:45")
    if int(respawn.get("recent_respawn_count") or 0) < 1:
        errors.append("hub_ring_respawn_event_should_exist_after_action_elapsed")
    if str(respawn.get("respawn_policy") or "") != "defeated_players_respawn_in_central_hub_circle":
        errors.append("respawn_policy_must_return_defeated_players_to_hub")
    if int(respawn.get("active_player_count") or 0) != 4:
        errors.append("active_slots_must_remain_full_after_replacement")
    if int(respawn.get("player_defeats") or 0) < 1:
        errors.append("combat_should_record_player_defeat_count")
    if int(respawn.get("enemies_defeated") or 0) < 1:
        errors.append("combat_should_record_enemy_defeat_count")
    if int(respawn.get("wave_number") or 0) < 1:
        errors.append("combat_should_report_wave_number")
    final = build_adventure_simulation_state(holoutopia_root, "22:59")
    if not bool(final.get("final_score_ready")):
        errors.append("final_score_should_be_ready_near_match_end")
    if str(final.get("match_phase") or "") != "final_score":
        errors.append("match_phase_should_report_final_score")
    if int(final.get("final_score") or 0) <= int(respawn.get("team_score") or 0):
        errors.append("final_score_should_include_bonus")
    final_state = final.get("final_score_state") if isinstance(final.get("final_score_state"), dict) else {}
    if len(final_state.get("scoreboard_lines") if isinstance(final_state.get("scoreboard_lines"), list) else []) < 4:
        errors.append("final_scoreboard_lines_missing")
    return errors
