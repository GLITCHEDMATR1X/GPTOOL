"""Validate cross-district residential infill neighborhoods."""
from __future__ import annotations
import json
from pathlib import Path
import sys


def _find_holoverse_root() -> Path:
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        if parent.name.lower() in {"holoverse", "holoutopia"}:
            return parent
    for parent in [here.parent, *here.parents]:
        candidate = parent / "data" / "HoloUtopia"
        if candidate.exists():
            return candidate
    raise SystemExit("Could not resolve data/HoloUtopia root")


def main() -> int:
    root = _find_holoverse_root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from holoutopia_town_blocks import HoloUtopiaTownError, load_all_neighborhoods
    report = {"ok": True, "neighborhoods": [], "towns_with_residential": {}, "total_lots": 0, "total_capacity": 0, "errors": []}
    try:
        neighborhoods = load_all_neighborhoods(root)
    except HoloUtopiaTownError as exc:
        report["ok"] = False
        report["errors"].append(str(exc))
        print(json.dumps(report, indent=2))
        return 2
    for neighborhood in neighborhoods:
        lots = neighborhood.get("lots", [])
        capacity = 0
        missing_foundations = []
        missing_policy = []
        for lot in lots:
            if not isinstance(lot, dict):
                continue
            profile = lot.get("building_profile", {}) if isinstance(lot.get("building_profile"), dict) else {}
            try:
                capacity += int(profile.get("residential_capacity", 0))
            except Exception:
                pass
            if not isinstance(lot.get("foundation_profile"), dict):
                missing_foundations.append(lot.get("id"))
            profile = lot.get("building_profile", {}) if isinstance(lot.get("building_profile"), dict) else {}
            if not isinstance(lot.get("line_policy"), dict) and not isinstance(profile.get("line_policy"), dict):
                missing_policy.append(lot.get("id"))
        if missing_foundations or missing_policy:
            report["ok"] = False
            report["errors"].append(f"{neighborhood.get('id')}: missing foundation/line policy")
        town_id = str(neighborhood.get("town_id"))
        report["towns_with_residential"].setdefault(town_id, {"neighborhoods": 0, "lots": 0, "capacity": 0})
        report["towns_with_residential"][town_id]["neighborhoods"] += 1
        report["towns_with_residential"][town_id]["lots"] += len(lots)
        report["towns_with_residential"][town_id]["capacity"] += capacity
        report["total_lots"] += len(lots)
        report["total_capacity"] += capacity
        report["neighborhoods"].append({"id": neighborhood.get("id"), "town_id": town_id, "lots": len(lots), "capacity": capacity})
    print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
