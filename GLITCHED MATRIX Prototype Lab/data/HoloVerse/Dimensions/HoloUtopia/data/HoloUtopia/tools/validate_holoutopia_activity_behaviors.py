from __future__ import annotations

import sys
from pathlib import Path


def _find_root() -> Path:
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        candidate = parent / "data" / "HoloUtopia"
        if (candidate / "holoutopia_activity_behaviors.py").exists():
            return candidate
        if parent.name.lower() in {"holoutopia", "holoverse"} and (parent / "holoutopia_activity_behaviors.py").exists():
            return parent
    raise SystemExit("Could not resolve data/HoloUtopia root")


def main() -> int:
    root = _find_root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from holoutopia_activity_behaviors import validate_activity_behaviors
    from holoutopia_citizen_simulation import build_node_index, load_simulation_inputs
    from holoutopia_district_activities import build_district_activity_frame
    from holoutopia_pathfinding import validate_visible_citizens_off_buildings

    errors = validate_activity_behaviors(root)
    inputs = load_simulation_inputs(root)
    node_index = build_node_index(inputs)
    frame = build_district_activity_frame(root, "18:15", node_index=node_index)
    citizens = frame.get("visible_activity_citizens") if isinstance(frame.get("visible_activity_citizens"), dict) else {}
    if not citizens:
        errors.append("expected visible activity citizens at 18:15")
    poses = {str(c.get("activity_pose") or "") for c in citizens.values() if isinstance(c, dict)}
    families = {str(c.get("activity_family") or "") for c in citizens.values() if isinstance(c, dict)}
    if len(poses) < 4:
        errors.append(f"expected at least 4 activity poses, found {sorted(poses)}")
    if len(families) < 4:
        errors.append(f"expected at least 4 activity families, found {sorted(families)}")
    for cid, citizen in citizens.items():
        if not isinstance(citizen, dict):
            continue
        for field in ("activity_pose", "activity_status", "activity_animation_speed", "activity_animation_amp", "activity_face_target"):
            if field not in citizen:
                errors.append(f"{cid} missing {field}")
    errors.extend(validate_visible_citizens_off_buildings(root, citizens, node_index))
    if errors:
        print("[FAIL] HoloUtopia activity behavior validation failed")
        for err in errors:
            print(" -", err)
        return 1
    print("[OK] HoloUtopia activity behaviors validated")
    print(f"[OK] visible_activity={len(citizens)} poses={len(poses)} families={len(families)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
