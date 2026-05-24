#!/usr/bin/env python3
"""Validate Pass 47B citizen dialogue watch-log integration."""
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


def _visible_positions(root: Path, frame: dict, max_count: int = 20) -> tuple[dict, dict]:
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


def main() -> int:
    root = _find_root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from holoutopia_citizen_simulation import simulate_city_at_time, load_simulation_inputs
    from holoutopia_citizen_dialogue import build_dialogue_state, format_dialogue_log_lines, validate_dialogue_state
    from holoutopia_watch_mode import build_watch_snapshot, format_watch_lines

    inputs = load_simulation_inputs(root)
    issues: list[str] = []
    total_logs = 0
    total_bubbles = 0
    category_hits: set[str] = set()
    for clock in ["06:45", "12:45", "18:15", "20:35"]:
        frame = simulate_city_at_time(root, clock, inputs=inputs)
        visible, positions = _visible_positions(root, frame, max_count=20)
        state = build_dialogue_state(root, frame, visible, positions, clock=clock)
        for issue in validate_dialogue_state(state):
            issues.append(f"{clock}:{issue}")
        logs = format_dialogue_log_lines(state, max_lines=3)
        bubbles = state.get("active_bubbles") if isinstance(state.get("active_bubbles"), list) else []
        total_logs += len(logs)
        total_bubbles += len(bubbles)
        counts = state.get("dialogue_category_counts") if isinstance(state.get("dialogue_category_counts"), dict) else {}
        category_hits.update(k for k, v in counts.items() if int(v or 0) > 0)
        if bubbles and not logs:
            issues.append(f"{clock}:bubbles_without_recent_log")
        if len(logs) > 3:
            issues.append(f"{clock}:too_many_watch_log_lines")
        for line in logs:
            if len(str(line)) > 58:
                issues.append(f"{clock}:watch_log_line_too_long")
        frame["citizen_dialogue_state"] = state
        snapshot = build_watch_snapshot(root, clock, frame=frame)
        if snapshot.get("dialogue_active_count") != len(bubbles):
            issues.append(f"{clock}:watch_snapshot_dialogue_count_mismatch")
        watch_lines = format_watch_lines(snapshot, max_lines=9)
        if bubbles and not any(str(line).startswith("Talk:") for line in watch_lines):
            issues.append(f"{clock}:watch_panel_missing_talk_line")
    if total_bubbles <= 0:
        issues.append("no_dialogue_bubbles")
    if total_logs <= 0:
        issues.append("no_dialogue_watch_logs")
    if len(category_hits) < 2:
        issues.append("dialogue_categories_not_varied")
    if issues:
        print("[FAIL] HoloUtopia citizen dialogue watch-log validation failed")
        for issue in issues:
            print(" -", issue)
        return 1
    print("[OK] HoloUtopia citizen dialogue watch-log validated")
    print(f"[OK] bubbles={total_bubbles} logs={total_logs} categories={','.join(sorted(category_hits))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
