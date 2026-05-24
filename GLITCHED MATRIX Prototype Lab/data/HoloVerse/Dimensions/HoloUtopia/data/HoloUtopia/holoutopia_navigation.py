"""HoloUtopia city navigation and citizen route helpers.

Pass 20 keeps travel mechanics data-first and runtime-safe:
- authored city/navigation/citizen data stays read-only;
- loose home/work/social schedule nodes are connected to a district navigation spine;
- citizens can resolve real routes through district gates before final street meshes exist;
- restricted edges are tagged for later guard/checkpoint behavior instead of being blocked.

Example use:

    from holoutopia_navigation import build_citizen_route_index
    routes = build_citizen_route_index(ROOT)

The returned routes are JSON-safe and can be fed to a future in-game activity log,
map overlay, or citizen movement controller.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import heapq
import json
import math
from pathlib import Path
from typing import Any, Iterable

from holoutopia_citizen_simulation import (
    HoloUtopiaSimulationError,
    SimulationNode,
    build_node_index,
    load_simulation_inputs,
    parse_clock_minutes,
)


class HoloUtopiaNavigationError(ValueError):
    """Raised when HoloUtopia navigation data cannot be resolved safely."""


NAVIGATION_FOLDER_NAME = "navigation"
GRAPH_FILE_NAME = "city_navigation_graph.json"
RULES_FILE_NAME = "navigation_rules.json"
ROUTE_INDEX_FILE_NAME = "citizen_commute_routes.json"


@dataclass(frozen=True)
class RouteStep:
    id: str
    town_id: str
    kind: str
    world: tuple[float, float]
    source: str
    tags: tuple[str, ...] = ()


def _data_root_from_holoverse_root(holoverse_root: Path) -> Path:
    root = Path(holoverse_root).resolve()
    if root.name.lower() in {"holoverse", "holoutopia"}:
        return root.parent
    if root.name.lower() == "tools" and root.parent.name.lower() in {"holoverse", "holoutopia"}:
        return root.parent.parent
    return root


def utopia_data_dir(holoverse_root: Path | str | None = None) -> Path:
    if holoverse_root is None:
        return _data_root_from_holoverse_root(Path(__file__).resolve().parent) / "database" / "utopia"
    return _data_root_from_holoverse_root(Path(holoverse_root)) / "database" / "utopia"


def navigation_data_dir(holoverse_root: Path | str | None = None) -> Path:
    return utopia_data_dir(holoverse_root) / NAVIGATION_FOLDER_NAME


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise HoloUtopiaNavigationError(f"Missing JSON file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise HoloUtopiaNavigationError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise HoloUtopiaNavigationError(f"Expected JSON object in {path}")
    return data


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def load_navigation_graph(holoverse_root: Path | str | None = None) -> dict[str, Any]:
    return _read_json(navigation_data_dir(holoverse_root) / GRAPH_FILE_NAME)


def load_navigation_rules(holoverse_root: Path | str | None = None) -> dict[str, Any]:
    return _read_json(navigation_data_dir(holoverse_root) / RULES_FILE_NAME)


def _route_step_from_graph_node(node: dict[str, Any]) -> RouteStep:
    raw_world = node.get("world", [0, 0])
    return RouteStep(
        id=str(node.get("id") or ""),
        town_id=str(node.get("town_id") or ""),
        kind=str(node.get("kind") or "navigation"),
        world=(float(raw_world[0]), float(raw_world[1])),
        source="navigation_graph",
        tags=tuple(str(t) for t in _as_list(node.get("tags"))),
    )


def _route_step_from_sim_node(node: SimulationNode, source: str) -> RouteStep:
    return RouteStep(
        id=node.id,
        town_id=node.town_id,
        kind=node.kind,
        world=(float(node.world[0]), float(node.world[1])),
        source=source,
        tags=node.tags,
    )


def _distance(a: RouteStep, b: RouteStep) -> float:
    return math.dist(a.world, b.world)


def _build_adjacency(graph: dict[str, Any]) -> tuple[dict[str, RouteStep], dict[str, list[tuple[str, float, list[str]]]]]:
    nodes: dict[str, RouteStep] = {}
    adjacency: dict[str, list[tuple[str, float, list[str]]]] = {}
    for node in _as_list(graph.get("nodes")):
        if not isinstance(node, dict):
            continue
        step = _route_step_from_graph_node(node)
        if step.id:
            nodes[step.id] = step
            adjacency.setdefault(step.id, [])
    for edge in _as_list(graph.get("edges")):
        if not isinstance(edge, dict):
            continue
        a = str(edge.get("from") or "")
        b = str(edge.get("to") or "")
        if a not in nodes or b not in nodes:
            continue
        distance = float(edge.get("distance_units") or _distance(nodes[a], nodes[b]))
        tags = [str(t) for t in _as_list(edge.get("tags"))]
        adjacency.setdefault(a, []).append((b, distance, tags))
        if bool(edge.get("bidirectional", True)):
            adjacency.setdefault(b, []).append((a, distance, tags))
    return nodes, adjacency


def _connect_temporary_node(
    nodes: dict[str, RouteStep],
    adjacency: dict[str, list[tuple[str, float, list[str]]]],
    step: RouteStep,
    connection_id: str,
    tags: Iterable[str],
) -> None:
    nodes[step.id] = step
    adjacency.setdefault(step.id, [])
    if connection_id not in nodes:
        return
    distance = _distance(step, nodes[connection_id])
    tag_list = [str(t) for t in tags]
    adjacency[step.id].append((connection_id, distance, tag_list))
    adjacency.setdefault(connection_id, []).append((step.id, distance, tag_list))



def _normalize_missing_node_id(node_id: str) -> list[str]:
    """Return safe aliases for common authored schedule references."""
    raw = str(node_id or "").strip()
    if not raw:
        return []
    base = raw
    aliases = [raw]
    for suffix in ("_node", "_work", "_shift"):
        if base.endswith(suffix):
            aliases.append(base[: -len(suffix)])
    aliases.append("block_" + aliases[-1])
    # Keep order and remove duplicates.
    return list(dict.fromkeys(a for a in aliases if a))


def _fuzzy_endpoint_step(
    requested_id: str,
    node_index: dict[str, SimulationNode],
    graph_nodes: dict[str, RouteStep],
    *,
    preferred_town_id: str = "",
    source: str,
) -> tuple[RouteStep | None, str]:
    """Resolve schedule/building/nav references into route endpoints.

    Existing authored citizen data occasionally points at a building/purpose name
    instead of a formal schedule node.  For pass 20 we resolve those safely to a
    matching block when possible, then fall back to the district center.  This
    keeps route generation useful without mutating authored citizen records.
    """
    raw = str(requested_id or "").strip()
    for alias in _normalize_missing_node_id(raw):
        if alias in node_index:
            return _route_step_from_sim_node(node_index[alias], source), "resolved" if alias == raw else f"alias:{alias}"
        if alias in graph_nodes:
            return graph_nodes[alias], "graph_node" if alias == raw else f"graph_alias:{alias}"
    wanted = raw.lower().replace("_node", "")
    if preferred_town_id and wanted:
        town_candidates = [node for node in node_index.values() if node.town_id == preferred_town_id]
        for node in town_candidates:
            nid = node.id.lower()
            if wanted in nid or nid in wanted or ("block_" + wanted) in nid:
                return _route_step_from_sim_node(node, source), f"fuzzy:{node.id}"
    if preferred_town_id:
        center = graph_nodes.get(f"nav:{preferred_town_id}:center")
        if center is not None:
            return center, f"fallback_town_center:{preferred_town_id}:{raw}"
    return None, f"missing:{raw}"


def _dijkstra(adjacency: dict[str, list[tuple[str, float, list[str]]]], start: str, goal: str) -> tuple[list[str], float, list[str]]:
    if start == goal:
        return [start], 0.0, []
    queue: list[tuple[float, str]] = [(0.0, start)]
    previous: dict[str, str] = {}
    edge_tags: dict[tuple[str, str], list[str]] = {}
    distances: dict[str, float] = {start: 0.0}
    seen: set[str] = set()
    while queue:
        dist, node = heapq.heappop(queue)
        if node in seen:
            continue
        seen.add(node)
        if node == goal:
            break
        for neighbor, weight, tags in adjacency.get(node, []):
            nd = dist + float(weight)
            if nd < distances.get(neighbor, float("inf")):
                distances[neighbor] = nd
                previous[neighbor] = node
                edge_tags[(node, neighbor)] = list(tags)
                heapq.heappush(queue, (nd, neighbor))
    if goal not in distances:
        return [], float("inf"), []
    path = [goal]
    while path[-1] != start:
        path.append(previous[path[-1]])
    path.reverse()
    tags_out: list[str] = []
    for a, b in zip(path, path[1:]):
        for tag in edge_tags.get((a, b), []):
            if tag not in tags_out:
                tags_out.append(tag)
    return path, distances[goal], tags_out


def resolve_route(
    holoverse_root: Path | str | None,
    start_node_id: str,
    target_node_id: str,
    *,
    inputs: dict[str, Any] | None = None,
    graph: dict[str, Any] | None = None,
    start_town_id: str = "",
    target_town_id: str = "",
) -> dict[str, Any]:
    """Resolve a route between authored schedule nodes through the city graph."""
    data = inputs or load_simulation_inputs(holoverse_root)
    nav_graph = graph or load_navigation_graph(holoverse_root)
    node_index = build_node_index(data)
    graph_nodes, adjacency = _build_adjacency(nav_graph)

    start_step, start_resolution = _fuzzy_endpoint_step(
        str(start_node_id),
        node_index,
        graph_nodes,
        preferred_town_id=str(start_town_id or ""),
        source="schedule_start",
    )
    target_step, target_resolution = _fuzzy_endpoint_step(
        str(target_node_id),
        node_index,
        graph_nodes,
        preferred_town_id=str(target_town_id or ""),
        source="schedule_target",
    )
    issues: list[str] = []
    if start_step is None:
        issues.append(f"missing-start-node:{start_node_id}")
    if target_step is None:
        issues.append(f"missing-target-node:{target_node_id}")
    if issues:
        return {
            "ok": False,
            "start_node": str(start_node_id),
            "target_node": str(target_node_id),
            "start_resolution": start_resolution,
            "target_resolution": target_resolution,
            "steps": [],
            "distance_units": 0,
            "district_hops": 0,
            "route_tags": [],
            "issues": issues,
        }

    # Graph nav nodes can be used directly.  Simulation nodes are attached as
    # temporary endpoints to their district centers.
    if not start_step.id.startswith("nav:"):
        start_id = f"tmp:start:{start_step.id}"
        start_step = RouteStep(start_id, start_step.town_id, start_step.kind, start_step.world, start_step.source, start_step.tags)
        _connect_temporary_node(graph_nodes, adjacency, start_step, f"nav:{start_step.town_id}:center", ["loose_start", "schedule_route"])
    else:
        start_id = start_step.id
    if not target_step.id.startswith("nav:"):
        target_id = f"tmp:target:{target_step.id}"
        target_step = RouteStep(target_id, target_step.town_id, target_step.kind, target_step.world, target_step.source, target_step.tags)
        _connect_temporary_node(graph_nodes, adjacency, target_step, f"nav:{target_step.town_id}:center", ["loose_target", "schedule_route"])
    else:
        target_id = target_step.id

    path_ids, distance_units, route_tags = _dijkstra(adjacency, start_id, target_id)
    if not path_ids:
        return {
            "ok": False,
            "start_node": str(start_node_id),
            "target_node": str(target_node_id),
            "start_resolution": start_resolution,
            "target_resolution": target_resolution,
            "steps": [],
            "distance_units": 0,
            "district_hops": 0,
            "route_tags": route_tags,
            "issues": [f"unroutable:{start_node_id}->{target_node_id}"],
        }
    steps = [asdict(graph_nodes[pid]) for pid in path_ids]
    towns_in_path = [str(step.get("town_id")) for step in steps if step.get("town_id")]
    district_hops = max(0, len([t for i, t in enumerate(towns_in_path) if i == 0 or t != towns_in_path[i - 1]]) - 1)
    return {
        "ok": True,
        "start_node": str(start_node_id),
        "target_node": str(target_node_id),
        "start_resolution": start_resolution,
        "target_resolution": target_resolution,
        "steps": steps,
        "step_count": len(steps),
        "distance_units": round(float(distance_units), 3),
        "district_hops": int(district_hops),
        "route_tags": route_tags,
        "issues": [],
    }


def _schedule_target_for_activity(schedule: dict[str, Any], activity_id: str) -> str:
    blocks = [b for b in _as_list(schedule.get("blocks")) if isinstance(b, dict)]
    # prefer earliest matching block during normal day, while still accepting older schedules.
    keyed = sorted((parse_clock_minutes(str(block.get("time") or "00:00")), block) for block in blocks)
    for _minute, block in keyed:
        if str(block.get("activity_id") or "") == activity_id:
            return str(block.get("target") or "")
    return ""


def build_citizen_route_index(holoverse_root: Path | str | None = None) -> dict[str, Any]:
    """Build home/work/social/home routes for every authored citizen."""
    inputs = load_simulation_inputs(holoverse_root)
    graph = load_navigation_graph(holoverse_root)
    citizens = [c for c in _as_list(inputs.get("citizen_manifest", {}).get("citizens")) if isinstance(c, dict)]
    citizens_by_id = {str(c.get("id")): c for c in citizens if str(c.get("id", "")).strip()}
    schedules = inputs.get("citizen_schedules", {}).get("schedules", {})
    routes: dict[str, Any] = {}
    issues: list[str] = []
    totals = {
        "citizens": len(citizens),
        "routes": 0,
        "total_distance_units": 0.0,
        "restricted_tagged_routes": 0,
        "max_district_hops": 0,
    }
    for citizen in citizens:
        cid = str(citizen.get("id") or "")
        if not cid:
            continue
        schedule = schedules.get(cid, {}) if isinstance(schedules, dict) else {}
        job = citizen.get("job") if isinstance(citizen.get("job"), dict) else {}
        home_node = str(citizen.get("home_node") or "")
        work_node = str(job.get("work_node") or "")
        social_node = _schedule_target_for_activity(schedule, "meal_break") or _schedule_target_for_activity(schedule, "hobby") or home_node
        friend_id = next((str(fid) for fid in _as_list(citizen.get("friends")) if str(fid) in citizens_by_id), "")
        friend = citizens_by_id.get(friend_id, {}) if friend_id else {}
        friend_home_node = str(friend.get("home_node") or social_node or home_node)
        route_specs = [
            ("home_to_work", home_node, work_node),
            ("work_to_social", work_node or home_node, social_node),
            ("social_to_home", social_node or work_node, home_node),
            ("home_to_friend", home_node, friend_home_node),
        ]
        citizen_routes: dict[str, Any] = {}
        for route_id, start, target in route_specs:
            start_town = str(citizen.get("town_id") or "") if route_id.startswith("home") else str(job.get("work_town_id") or citizen.get("town_id") or "")
            if route_id == "home_to_work":
                target_town = str(job.get("work_town_id") or citizen.get("town_id") or "")
            elif route_id == "home_to_friend" and friend:
                target_town = str(friend.get("town_id") or citizen.get("town_id") or "")
            else:
                target_town = str(citizen.get("town_id") or "")
            route = resolve_route(holoverse_root, start, target, inputs=inputs, graph=graph, start_town_id=start_town, target_town_id=target_town)
            route["route_id"] = f"{cid}:{route_id}"
            route["citizen_id"] = cid
            route["display_name"] = str(citizen.get("display_name") or cid)
            route["kind"] = route_id
            citizen_routes[route_id] = route
            totals["routes"] += 1
            if route.get("ok"):
                totals["total_distance_units"] += float(route.get("distance_units") or 0)
                totals["max_district_hops"] = max(totals["max_district_hops"], int(route.get("district_hops") or 0))
                if "restricted_checkpoint" in route.get("route_tags", []):
                    totals["restricted_tagged_routes"] += 1
            else:
                issues.extend(f"{cid}:{issue}" for issue in route.get("issues", []))
        routes[cid] = {
            "citizen_id": cid,
            "display_name": str(citizen.get("display_name") or cid),
            "home_town_id": str(citizen.get("town_id") or ""),
            "work_town_id": str(job.get("work_town_id") or citizen.get("town_id") or ""),
            "routes": citizen_routes,
        }
    totals["total_distance_units"] = round(totals["total_distance_units"], 3)
    return {
        "schema": 1,
        "id": "holoutopia_citizen_commute_routes_v1",
        "runtime_writes_allowed": False,
        "derived_from": [
            "citizens/citizen_manifest.json",
            "citizens/citizen_schedules.json",
            "navigation/city_navigation_graph.json",
            "towns/*.json",
            "neighborhoods/*.json",
        ],
        "route_policy": "district-center/gate spine with temporary endpoints for home/work/social nodes",
        "totals": totals,
        "citizens": dict(sorted(routes.items())),
        "issues": issues,
    }


def save_citizen_route_index(holoverse_root: Path | str | None = None) -> Path:
    """Regenerate and save the derived citizen commute route index."""
    out = navigation_data_dir(holoverse_root) / ROUTE_INDEX_FILE_NAME
    payload = build_citizen_route_index(holoverse_root)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return out
