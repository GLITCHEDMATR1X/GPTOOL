from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from holoutopia_citizen_simulation import build_node_index, load_simulation_inputs, simulate_city_at_time
from holoutopia_pathfinding import safe_outdoor_grid_for_citizen
from holoutopia_simulation_hub_visuals import load_simulation_hub_activity_clusters, validate_simulation_activity_clusters


def main() -> int:
    inputs = load_simulation_inputs(ROOT)
    node_index = build_node_index(inputs)
    errors = validate_simulation_activity_clusters(ROOT, node_index)
    data = load_simulation_hub_activity_clusters(ROOT)
    frame = simulate_city_at_time(ROOT, "18:15", inputs=inputs)
    pop = frame.get("residential_population_model") if isinstance(frame.get("residential_population_model"), dict) else {}
    activity = pop.get("visible_activity_citizens") if isinstance(pop.get("visible_activity_citizens"), dict) else {}
    cluster_sources = 0
    for cid, citizen in activity.items():
        if not isinstance(citizen, dict):
            continue
        placement = safe_outdoor_grid_for_citizen(ROOT, str(cid), citizen, node_index)
        source = str(placement.get("source") or "")
        if source.startswith("activity_cluster:"):
            cluster_sources += 1
        if placement.get("on_building"):
            errors.append(f"{cid} resolved onto a building: {placement}")
        if not citizen.get("activity_cluster_id"):
            errors.append(f"{cid} missing activity_cluster_id")
    if len(activity) != 20:
        errors.append(f"expected 20 visible activity citizens at 18:15, got {len(activity)}")
    if cluster_sources < 12:
        errors.append(f"expected most Simulation Hub citizens to use activity cluster slots, got {cluster_sources}")
    if errors:
        print("HoloUtopia Simulation Hub activity cluster validation FAILED")
        for error in errors:
            print(" -", error)
        return 2
    print("[OK] HoloUtopia Simulation Hub activity clusters validated")
    print(f"clusters={len(data.get('clusters', []))} visible_activity={len(activity)} cluster_slot_sources={cluster_sources}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
