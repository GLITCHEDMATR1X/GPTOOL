from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from holoutopia_citizen_simulation import build_node_index, load_simulation_inputs, simulate_city_at_time
from holoutopia_pathfinding import safe_outdoor_grid_for_citizen, validate_visible_citizens_off_buildings


SAMPLE_CLOCKS = ("06:30", "08:30", "18:15", "20:30")


def main() -> int:
    inputs = load_simulation_inputs(ROOT)
    node_index = build_node_index(inputs)
    errors: list[str] = []
    checked = 0
    snapped = 0
    sources: set[str] = set()
    cluster_sources = 0
    for clock in SAMPLE_CLOCKS:
        frame = simulate_city_at_time(ROOT, clock, inputs=inputs)
        pop = frame.get("residential_population_model") if isinstance(frame.get("residential_population_model"), dict) else {}
        visible: dict[str, object] = {}
        for key in ("visible_outdoor_citizens", "visible_activity_citizens"):
            chunk = pop.get(key) if isinstance(pop.get(key), dict) else {}
            visible.update(chunk)
        errors.extend(f"{clock}: {error}" for error in validate_visible_citizens_off_buildings(ROOT, visible, node_index))
        for cid, citizen in visible.items():
            if isinstance(citizen, dict):
                placement = safe_outdoor_grid_for_citizen(ROOT, str(cid), citizen, node_index)
                checked += 1
                snapped += 1 if placement.get("snapped") else 0
                source = str(placement.get("source") or "")
                sources.add(source)
                if source.startswith("activity_cluster:"):
                    cluster_sources += 1
                if placement.get("on_building"):
                    errors.append(f"{clock}: {cid} reported on_building placement {placement}")
                if str(citizen.get("location_mode") or "") == "private_home_hidden":
                    errors.append(f"{clock}: visible citizen {cid} should not be private_home_hidden")
    if checked <= 0:
        errors.append("no visible population representatives were checked")
    if snapped <= 0:
        errors.append("no visible citizens were snapped to street/activity surfaces")
    if not sources:
        errors.append("no pathfinding sources were recorded")
    if cluster_sources <= 0:
        errors.append("Simulation Hub activity representatives did not use activity cluster slot sources")
    if errors:
        print("HoloUtopia citizen pathfinding validation FAILED")
        for error in errors:
            print(" -", error)
        return 2
    print("HoloUtopia citizen pathfinding validation passed")
    print(f"checked_visible_citizens={checked}")
    print(f"street_safe_snaps={snapped}")
    print("sample_sources=" + ",".join(sorted(s for s in sources if s)[:8]))
    print(f"activity_cluster_sources={cluster_sources}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
