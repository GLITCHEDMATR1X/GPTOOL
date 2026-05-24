from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HOLO = ROOT / "data" / "HoloUtopia"
if str(HOLO) not in sys.path:
    sys.path.insert(0, str(HOLO))

from holoutopia_commute_flow import commute_profile_for_visible_slot, validate_commute_flow
from holoutopia_district_activities import build_district_activity_frame
from holoutopia_citizen_simulation import load_simulation_inputs, build_node_index
from holoutopia_pathfinding import validate_visible_citizens_off_buildings


def main() -> int:
    errors = validate_commute_flow(HOLO)
    inputs = load_simulation_inputs(HOLO)
    node_index = build_node_index(inputs)
    for clock in ("06:45", "07:15", "20:20", "20:45"):
        frame = build_district_activity_frame(HOLO, clock, world_population=1000, max_visible_per_district=20, node_index=node_index)
        citizens = frame.get("visible_activity_citizens", {}) if isinstance(frame.get("visible_activity_citizens"), dict) else {}
        if len(citizens) != 20:
            errors.append(f"{clock}: expected 20 visible commute/activity representatives, got {len(citizens)}")
        commute = [c for c in citizens.values() if isinstance(c, dict) and c.get("commute_flow_representative")]
        if clock.startswith(("06", "07", "20")) and len(commute) < 10:
            errors.append(f"{clock}: expected commute representatives, got {len(commute)}")
        errors.extend(f"{clock}: {err}" for err in validate_visible_citizens_off_buildings(HOLO, citizens, node_index))
    dep_stages = {commute_profile_for_visible_slot(HOLO, phase="departing_residential", clock_minutes=7*60+15, slot=i, resident_sequence=100+i).get("commute_stage") for i in range(20)}
    ret_stages = {commute_profile_for_visible_slot(HOLO, phase="returning_to_residential", clock_minutes=20*60+35, slot=i, resident_sequence=200+i).get("commute_stage") for i in range(20)}
    if len(dep_stages) < 2:
        errors.append(f"departure stages too narrow: {sorted(dep_stages)}")
    if len(ret_stages) < 2:
        errors.append(f"return stages too narrow: {sorted(ret_stages)}")
    if errors:
        print("[FAIL] HoloUtopia commute flow validation failed")
        for err in errors:
            print(" -", err)
        return 1
    print("[OK] HoloUtopia commute flow validated")
    print(f"[OK] departure_stages={sorted(dep_stages)}")
    print(f"[OK] return_stages={sorted(ret_stages)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
