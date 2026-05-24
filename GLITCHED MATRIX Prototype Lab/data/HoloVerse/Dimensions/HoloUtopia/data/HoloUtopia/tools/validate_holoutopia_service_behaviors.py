from __future__ import annotations

import sys
from pathlib import Path


def _root() -> Path:
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        if (parent / "holoutopia_service_behaviors.py").exists():
            return parent
    raise SystemExit("Could not locate HoloUtopia module root")


def main() -> int:
    root = _root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from holoutopia_citizen_simulation import simulate_city_at_time
    from holoutopia_service_behaviors import build_service_operation_summary, validate_service_behaviors
    from holoutopia_citizen_question_router import resolve_specific_question

    issues = validate_service_behaviors(root)
    frame = simulate_city_at_time(root, "12:45")
    pop = frame.get("residential_population_model") if isinstance(frame.get("residential_population_model"), dict) else {}
    people = pop.get("visible_activity_citizens") if isinstance(pop.get("visible_activity_citizens"), dict) else {}
    service_people = [c for c in people.values() if isinstance(c, dict) and c.get("functional_service_assignment")]
    if len(service_people) < 10:
        issues.append(f"expected at least 10 visible service citizens, got {len(service_people)}")
    missing_behavior = [c.get("id") for c in service_people if not c.get("service_behavior_assignment")]
    if missing_behavior:
        issues.append("service citizens missing behavior assignment")
    if not all(c.get("service_action_label") and c.get("service_output_label") for c in service_people):
        issues.append("service citizens missing action/output labels")
    if not all(c.get("service_glyph") for c in service_people):
        issues.append("service citizens missing visual glyphs")
    summary = build_service_operation_summary(service_people)
    if summary.get("service_operation_count") != len(service_people):
        issues.append("service operation summary count mismatch")
    if len(summary.get("top_operations") or []) < 3:
        issues.append("expected multiple service operation types")
    sample = service_people[0] if service_people else {}
    ans = resolve_specific_question(root, frame, "tester", sample, "listener", sample, question_id="q_service_operation")
    if ans.confidence != "runtime_resolved" or "service" not in ans.answer.lower() and ":" not in ans.answer:
        issues.append(f"service operation question did not resolve: {ans.answer}")
    if issues:
        print("[FAIL] HoloUtopia service behaviors")
        for issue in issues:
            print(" -", issue)
        return 1
    print("[OK] HoloUtopia service behaviors validated")
    print(f"service_people={len(service_people)}")
    print(f"operations={len(summary.get('top_operations') or [])}")
    print(f"outputs={len(summary.get('top_outputs') or [])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
