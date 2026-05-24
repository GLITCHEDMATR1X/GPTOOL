#!/usr/bin/env python3
"""Validate HoloUtopia Pass 47C specific citizen question router."""
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


def _sample_visible_citizen(frame: dict) -> dict:
    pop = frame.get("residential_population_model") if isinstance(frame.get("residential_population_model"), dict) else {}
    visible = {}
    visible.update(pop.get("visible_outdoor_citizens") if isinstance(pop.get("visible_outdoor_citizens"), dict) else {})
    visible.update(pop.get("visible_activity_citizens") if isinstance(pop.get("visible_activity_citizens"), dict) else {})
    for _cid, citizen in sorted(visible.items()):
        if isinstance(citizen, dict):
            return citizen
    return {}


def main() -> int:
    root = _find_root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from holoutopia_citizen_simulation import simulate_city_at_time, load_simulation_inputs
    from holoutopia_citizen_question_router import (
        load_specific_question_catalog,
        resolve_specific_question,
        validate_specific_question_router,
    )

    inputs = load_simulation_inputs(root)
    frame = simulate_city_at_time(root, "18:15", inputs=inputs)
    citizen = _sample_visible_citizen(frame)
    issues = validate_specific_question_router(root, frame, citizen)

    exact_checks = {
        "What time is it?": "18:15",
        "Where do you live?": "Residential Alpha",
        "How many citizens live here?": "1000",
        "How many can be outside?": "20",
        "How long can you stay active?": "15",
        "How long do you recharge?": "9",
    }
    for question, expected in exact_checks.items():
        routed = resolve_specific_question(root, frame, "citizen_a", citizen, "citizen_b", citizen, question=question)
        if expected not in routed.answer:
            issues.append(f"bad_exact_answer:{question}:{routed.answer}")
        if routed.confidence != "runtime_resolved":
            issues.append(f"not_runtime_resolved:{question}")

    unknown = resolve_specific_question(root, frame, "citizen_a", citizen, "citizen_b", citizen, question="What is behind the moon gate?")
    if unknown.confidence != "safe_unknown":
        issues.append("unknown_specific_question_not_safe_unknown")

    catalog = load_specific_question_catalog(root)
    if not bool((catalog.get("answer_policy") or {}).get("runtime_state_only")):
        issues.append("catalog_runtime_state_only_missing")
    if not bool((catalog.get("answer_policy") or {}).get("do_not_guess")):
        issues.append("catalog_do_not_guess_missing")

    if issues:
        print("[FAIL] HoloUtopia specific question router validation failed")
        for issue in issues:
            print(" -", issue)
        return 1
    print("[OK] HoloUtopia specific question router validated")
    print("[OK] exact_answers=time,home,population,outdoor_cap,energy,recharge unknown=safe")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
