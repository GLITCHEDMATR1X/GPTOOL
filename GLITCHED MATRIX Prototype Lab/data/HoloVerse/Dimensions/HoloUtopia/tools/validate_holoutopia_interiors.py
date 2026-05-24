"""Validate authored HoloUtopia lazy-load interior blueprint files."""
from __future__ import annotations
import json
from pathlib import Path
import sys


def _find_holoverse_root() -> Path:
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        if parent.name.lower() == "holoverse":
            return parent
    for parent in [here.parent, *here.parents]:
        candidate = parent / "data" / "HoloVerse"
        if candidate.exists():
            return candidate
    raise SystemExit("Could not resolve data/HoloVerse root")


def main() -> int:
    root = _find_holoverse_root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from holoutopia_town_blocks import HoloUtopiaTownError, interior_data_dir, load_interior_blueprint
    folder = interior_data_dir(root)
    files = sorted(p for p in folder.glob("*.json") if p.name != "interior_schema.json")
    report = {"ok": True, "interior_count": 0, "interiors": [], "errors": []}
    for path in files:
        try:
            interior = load_interior_blueprint(path.stem, root)
            capacity = sum(int(unit.get("capacity", 0)) for unit in interior.get("resident_unit_slots", []) if isinstance(unit, dict))
            assigned = sum(len(unit.get("assigned_npc_ids", [])) for unit in interior.get("resident_unit_slots", []) if isinstance(unit, dict))
            max_floor = max(int(floor.get("floor", 0)) for floor in interior.get("floors", []) if isinstance(floor, dict))
            report["interiors"].append({
                "id": interior.get("id"),
                "lot_id": interior.get("lot_id"),
                "mode": interior.get("load_policy", {}).get("mode"),
                "floors": max_floor,
                "resident_units": len(interior.get("resident_unit_slots", [])),
                "capacity": capacity,
                "assigned_residents": assigned,
                "activity_nodes": len(interior.get("activity_nodes", [])),
            })
            report["interior_count"] += 1
        except HoloUtopiaTownError as exc:
            report["ok"] = False
            report["errors"].append(str(exc))
    print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
