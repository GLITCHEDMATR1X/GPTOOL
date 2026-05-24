#!/usr/bin/env python3
"""Validate HoloUtopia Pass 47A citizen dialogue foundation."""
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
    from holoutopia_citizen_dialogue import (
        build_dialogue_state,
        load_dialogue_rules,
        load_question_answer_catalog,
        validate_dialogue_state,
    )

    rules = load_dialogue_rules(root)
    qa = load_question_answer_catalog(root)
    issues: list[str] = []
    if not bool(rules.get("proximity_only")):
        issues.append("rules_not_proximity_only")
    if not bool(rules.get("garrisoned_citizens_silent")):
        issues.append("rules_garrisoned_not_silent")
    if "question_templates" not in qa:
        issues.append("qa_missing_question_templates")

    inputs = load_simulation_inputs(root)
    total_bubbles = 0
    clocks = ["06:45", "12:45", "18:15", "20:35"]
    for clock in clocks:
        frame = simulate_city_at_time(root, clock, inputs=inputs)
        visible, positions = _visible_positions(root, frame, max_count=20)
        state = build_dialogue_state(root, frame, visible, positions, clock=clock)
        state_issues = validate_dialogue_state(state)
        if state_issues:
            issues.extend(f"{clock}:{issue}" for issue in state_issues)
        bubbles = state.get("active_bubbles") if isinstance(state.get("active_bubbles"), list) else []
        total_bubbles += len(bubbles)
        # At least one Q/A-style exchange across active public phases.
        if clock in {"12:45", "18:15"} and not bubbles:
            issues.append(f"{clock}:no_dialogue_bubbles")
        for bubble in bubbles:
            if not isinstance(bubble, dict):
                continue
            if "\n" in str(bubble.get("text") or "") and (not bubble.get("question") or not bubble.get("answer")):
                issues.append(f"{clock}:qa_missing_question_or_answer")
            # Citizens must be visible and not private/garrisoned.
            for key in ("speaker_id", "listener_id"):
                cid = str(bubble.get(key) or "")
                citizen = visible.get(cid)
                if not isinstance(citizen, dict):
                    issues.append(f"{clock}:dialogue_with_non_visible:{cid}")
                elif str(citizen.get("location_mode") or "") == "private_home_hidden":
                    issues.append(f"{clock}:dialogue_with_garrisoned:{cid}")
    if total_bubbles <= 0:
        issues.append("no_dialogue_generated_any_clock")

    if issues:
        print("[FAIL] HoloUtopia citizen dialogue validation failed")
        for issue in issues:
            print(" -", issue)
        return 1
    print("[OK] HoloUtopia citizen dialogue validated")
    print(f"[OK] clocks={','.join(clocks)} bubbles={total_bubbles} proximity_only=true brief_non_overlap=true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
