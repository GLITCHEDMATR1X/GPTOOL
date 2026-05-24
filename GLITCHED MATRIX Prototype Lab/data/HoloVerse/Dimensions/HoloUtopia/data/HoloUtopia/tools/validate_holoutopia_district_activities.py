"""Validate Pass 39A district activity routing."""
from __future__ import annotations

import sys
from pathlib import Path


def _root() -> Path:
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        if (parent / "holoutopia_game_runtime.py").exists():
            return parent
    raise SystemExit("Could not resolve data/HoloUtopia root")


def main() -> int:
    root = _root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from holoutopia_citizen_simulation import build_node_index, load_simulation_inputs, simulate_city_at_time
    from holoutopia_district_activities import build_district_activity_frame, load_district_activity_rules

    inputs = load_simulation_inputs(root)
    node_index = build_node_index(inputs)
    rules = load_district_activity_rules(root)
    frame = build_district_activity_frame(root, "18:15", world_population=1000, max_visible_per_district=20, node_index=node_index, rules=rules)
    assert frame["active_district_id"] == "central_core_civic_ring", frame
    assert frame["active_district_display_name"] == "Central Simulation Hub", frame
    assert frame["visible_activity_count"] == 20, frame
    assert frame["outdoor_cap_enforced"] is True, frame
    for cid, citizen in frame["visible_activity_citizens"].items():
        assert cid.startswith("act_sim_"), cid
        assert citizen["town_id"] == "central_core_civic_ring", citizen
        assert citizen["district_activity_representative"] is True, citizen
        assert citizen["virtual_population_representative"] is True, citizen
        assert citizen["resolved_node"] in node_index, citizen
        assert citizen.get("activity_cluster_id"), citizen
        assert citizen.get("activity_stage") in {"work_shift", "evening_activity", "arrival", "cooldown_replenish"}, citizen

    sim_frame = simulate_city_at_time(root, "18:15", inputs=inputs)
    pop = sim_frame.get("residential_population_model", {})
    assert pop.get("world_population") == 1000, pop
    assert len(pop.get("visible_activity_citizens", {})) == 20, pop.get("visible_activity_citizens")
    assert pop.get("district_activity_model", {}).get("central_simulation_hub") == "central_core_civic_ring", pop.get("district_activity_model")
    print("[OK] HoloUtopia district activity routing validated")
    print(f"active_district={frame['active_district_id']} visible_activity={frame['visible_activity_count']} motive={frame['motive']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
