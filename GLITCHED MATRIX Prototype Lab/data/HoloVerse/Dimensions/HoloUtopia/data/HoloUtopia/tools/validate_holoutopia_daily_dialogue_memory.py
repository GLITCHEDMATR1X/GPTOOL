#!/usr/bin/env python3
"""Validate Pass 47D same-day dialogue no-repeat memory."""
from __future__ import annotations

import sys
from pathlib import Path


def _find_root() -> Path:
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        candidate = parent if (parent / "holoutopia_game_runtime.py").exists() else parent / "data" / "HoloUtopia"
        if (candidate / "holoutopia_game_runtime.py").exists():
            return candidate.resolve()
    raise SystemExit("Could not resolve data/HoloUtopia root")


def _visible_positions(root: Path, frame: dict, max_count: int = 24) -> tuple[dict, dict]:
    from holoutopia_citizen_simulation import build_node_index, load_simulation_inputs
    from holoutopia_pathfinding import safe_outdoor_xy_for_citizen

    inputs = load_simulation_inputs(root)
    node_index = build_node_index(inputs)
    pop = frame.get("residential_population_model") if isinstance(frame.get("residential_population_model"), dict) else {}
    visible = {
        **(pop.get("visible_outdoor_citizens") if isinstance(pop.get("visible_outdoor_citizens"), dict) else {}),
        **(pop.get("visible_activity_citizens") if isinstance(pop.get("visible_activity_citizens"), dict) else {}),
    }
    visible = dict(list(sorted(visible.items()))[:max_count])
    positions: dict[str, tuple[float, float, float]] = {}
    for cid, citizen in visible.items():
        if not isinstance(citizen, dict):
            continue
        x, y, placement = safe_outdoor_xy_for_citizen(root, str(cid), citizen, node_index)
        citizen["pathfinding"] = placement
        positions[str(cid)] = (float(x), float(y), 1.75)
    return visible, positions


def _bubble_daily_key(day_id: str, bubble: dict) -> str:
    pair = "__".join(sorted([str(bubble.get("speaker_id") or ""), str(bubble.get("listener_id") or "")]))
    return f"{day_id}:{pair}:{bubble.get('question_id')}:{bubble.get('answer')}"


def main() -> int:
    root = _find_root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    from holoutopia_citizen_simulation import simulate_city_at_time, load_simulation_inputs
    from holoutopia_citizen_dialogue import build_dialogue_state, load_dialogue_rules, validate_dialogue_state

    rules = load_dialogue_rules(root)
    daily = rules.get("daily_memory") if isinstance(rules.get("daily_memory"), dict) else {}
    issues: list[str] = []
    if not bool(daily.get("enabled")):
        issues.append("daily_memory_disabled")
    if not bool(daily.get("no_repeat_same_pair_question")):
        issues.append("same_pair_question_guard_missing")
    if not bool(daily.get("no_repeat_same_citizen_line")):
        issues.append("same_citizen_line_guard_missing")
    if not bool(daily.get("runtime_only")):
        issues.append("daily_memory_not_runtime_only")

    inputs = load_simulation_inputs(root)
    memory: dict = {}
    seen_same_day: set[str] = set()
    total_bubbles = 0
    clocks = ["06:45", "12:45", "18:15", "20:35", "12:45", "18:15"]
    for clock in clocks:
        frame = simulate_city_at_time(root, clock, inputs=inputs)
        visible, positions = _visible_positions(root, frame)
        state = build_dialogue_state(root, frame, visible, positions, clock=clock, day_id="day_0007", daily_memory=memory)
        for issue in validate_dialogue_state(state):
            issues.append(f"{clock}:{issue}")
        bubbles = state.get("active_bubbles") if isinstance(state.get("active_bubbles"), list) else []
        total_bubbles += len(bubbles)
        for bubble in bubbles:
            if not isinstance(bubble, dict):
                continue
            key = _bubble_daily_key("day_0007", bubble)
            if key in seen_same_day:
                issues.append(f"same_day_repeated_dialogue:{key}")
            seen_same_day.add(key)
        day_summary = state.get("daily_memory") if isinstance(state.get("daily_memory"), dict) else {}
        if day_summary.get("day_id") != "day_0007":
            issues.append(f"{clock}:bad_day_id:{day_summary.get('day_id')}")
        if not bool(day_summary.get("same_day_no_repeat")):
            issues.append(f"{clock}:same_day_no_repeat_false")

    # A new day should permit the pool to restart without carrying yesterday's memory.
    frame = simulate_city_at_time(root, "12:45", inputs=inputs)
    visible, positions = _visible_positions(root, frame)
    next_day_state = build_dialogue_state(root, frame, visible, positions, clock="12:45", day_id="day_0008", daily_memory=memory)
    next_summary = next_day_state.get("daily_memory") if isinstance(next_day_state.get("daily_memory"), dict) else {}
    if next_summary.get("day_id") != "day_0008":
        issues.append("new_day_memory_did_not_reset")
    if not (next_day_state.get("active_bubbles") if isinstance(next_day_state.get("active_bubbles"), list) else []):
        issues.append("new_day_no_dialogue_after_reset")

    if total_bubbles <= 0:
        issues.append("no_dialogue_generated")

    if issues:
        print("[FAIL] HoloUtopia daily dialogue memory validation failed")
        for issue in issues:
            print(" -", issue)
        return 1
    print("[OK] HoloUtopia daily dialogue memory validated")
    print(f"[OK] clocks={','.join(clocks)} unique_same_day_dialogues={len(seen_same_day)} total_bubbles={total_bubbles} resets_on_new_day=true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
