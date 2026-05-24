from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from holoutopia_navigation import build_citizen_route_index, load_navigation_graph, load_navigation_rules, resolve_route, save_citizen_route_index
from holoutopia_citizen_simulation import load_simulation_inputs


def main() -> int:
    issues: list[str] = []
    graph = load_navigation_graph(ROOT)
    rules = load_navigation_rules(ROOT)
    inputs = load_simulation_inputs(ROOT)
    towns = {str(t.get("town_id")) for t in graph.get("nodes", []) if isinstance(t, dict) and str(t.get("town_id", "")).strip()}
    atlas_towns = {str(t.get("town_id")) for t in inputs["city_atlas"].get("towns", []) if isinstance(t, dict)}
    if towns != atlas_towns:
        issues.append(f"navigation towns do not match atlas: {sorted(towns ^ atlas_towns)}")
    expected_nodes = len(atlas_towns) * 5
    if len(graph.get("nodes", [])) != expected_nodes:
        issues.append(f"expected {expected_nodes} nav nodes, got {len(graph.get('nodes', []))}")
    if len(graph.get("edges", [])) < len(atlas_towns) * 4:
        issues.append("navigation graph has too few edges")
    if not rules.get("route_selection"):
        issues.append("missing navigation route_selection rules")

    probe = resolve_route(
        ROOT,
        "res_alpha_home_a_node",
        "nav:industrial_yard_alpha:center",
        inputs=inputs,
        graph=graph,
        start_town_id="residential_alpha",
        target_town_id="industrial_yard_alpha",
    )
    if not probe.get("ok"):
        issues.extend(probe.get("issues", ["probe route failed"]))
    if probe.get("district_hops", 0) < 1:
        issues.append("probe route should cross at least one district")
    if len(probe.get("steps", [])) < 4:
        issues.append("probe route has too few steps")

    route_index = build_citizen_route_index(ROOT)
    save_citizen_route_index(ROOT)
    totals = route_index.get("totals", {})
    citizen_count = len(inputs["citizen_manifest"].get("citizens", []))
    expected_routes = citizen_count * 4
    if totals.get("citizens") != citizen_count:
        issues.append(f"route index citizen mismatch: {totals.get('citizens')} != {citizen_count}")
    if totals.get("routes") != expected_routes:
        issues.append(f"route count mismatch: {totals.get('routes')} != {expected_routes}")
    if route_index.get("issues"):
        issues.extend(str(i) for i in route_index.get("issues", []))
    if float(totals.get("total_distance_units") or 0) <= 0:
        issues.append("route index total distance did not resolve")

    saved_path = ROOT.parent / "database" / "utopia" / "navigation" / "citizen_commute_routes.json"
    if not saved_path.exists():
        issues.append("citizen_commute_routes.json was not written")

    payload = {
        "ok": not issues,
        "districts": len(atlas_towns),
        "navigation_nodes": len(graph.get("nodes", [])),
        "navigation_edges": len(graph.get("edges", [])),
        "citizens": citizen_count,
        "routes": totals.get("routes"),
        "total_distance_units": totals.get("total_distance_units"),
        "restricted_tagged_routes": totals.get("restricted_tagged_routes"),
        "max_district_hops": totals.get("max_district_hops"),
        "probe_step_count": len(probe.get("steps", [])),
        "issues": issues,
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if not issues else 1


if __name__ == "__main__":
    raise SystemExit(main())
