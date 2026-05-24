from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from holoutopia_citizen_simulation import build_node_index, load_simulation_inputs, simulate_city_at_time
from holoutopia_schedule_staggering import validate_schedule_staggering

SAMPLE_CLOCKS = ("08:30", "12:45", "18:15")


def main() -> int:
    inputs = load_simulation_inputs(ROOT)
    node_index = build_node_index(inputs)
    errors = validate_schedule_staggering(ROOT)
    max_per_cluster_seen = 0
    min_unique_profiles = 999
    distributions = []
    for clock in SAMPLE_CLOCKS:
        frame = simulate_city_at_time(ROOT, clock, inputs=inputs)
        pop = frame.get("residential_population_model") if isinstance(frame.get("residential_population_model"), dict) else {}
        model = pop.get("district_activity_model") if isinstance(pop.get("district_activity_model"), dict) else {}
        activity = pop.get("visible_activity_citizens") if isinstance(pop.get("visible_activity_citizens"), dict) else {}
        if len(activity) != 20:
            errors.append(f"{clock}: expected 20 visible Simulation Hub reps, got {len(activity)}")
            continue
        profiles = {str(c.get("schedule_profile_id") or "") for c in activity.values() if isinstance(c, dict)}
        offsets = {int(c.get("personal_day_offset_minutes", -1)) for c in activity.values() if isinstance(c, dict)}
        clusters: dict[str, int] = {}
        for citizen in activity.values():
            if not isinstance(citizen, dict):
                continue
            cluster = str(citizen.get("activity_cluster_id") or "missing")
            clusters[cluster] = clusters.get(cluster, 0) + 1
            if str(citizen.get("resolved_node") or "") not in node_index:
                errors.append(f"{clock}: invalid resolved node {citizen.get('resolved_node')}")
        max_cluster = max(clusters.values()) if clusters else 0
        max_per_cluster_seen = max(max_per_cluster_seen, max_cluster)
        min_unique_profiles = min(min_unique_profiles, len(profiles))
        distributions.append(f"{clock}=" + ",".join(f"{k}:{v}" for k, v in sorted(clusters.items())))
        if len(profiles) < 18:
            errors.append(f"{clock}: expected at least 18 unique schedule profiles, got {len(profiles)}")
        if len(offsets) < 12:
            errors.append(f"{clock}: expected at least 12 schedule offsets, got {len(offsets)}")
        if len(clusters) < 5:
            errors.append(f"{clock}: expected spread across at least 5 clusters, got {len(clusters)}")
        if max_cluster > 4:
            errors.append(f"{clock}: too many representatives in one cluster: {max_cluster} {clusters}")
        if int(model.get("unique_schedule_profiles", 0) or 0) < 18:
            errors.append(f"{clock}: activity model did not report enough unique profiles")
    if errors:
        print("HoloUtopia Simulation Hub schedule staggering validation FAILED")
        for error in errors:
            print(" -", error)
        return 2
    print("[OK] HoloUtopia Simulation Hub schedule staggering validated")
    print(f"min_unique_profiles={min_unique_profiles}")
    print(f"max_cluster_population={max_per_cluster_seen}")
    print("distributions=" + " | ".join(distributions))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
