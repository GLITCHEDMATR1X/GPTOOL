"""HoloUtopia citizen schedule simulation spine.

Pass 18 keeps the living-world mechanics data-first and runtime-safe:
- Authored citizens, schedules, relationships, homes, and jobs stay read-only.
- Simulation samples are derived from authored data and can be written to saves/logs by callers.
- No HoloVerse main.py or artifact routing code is touched by this module.
- The module has no Panda3D dependency; it can run in validators, CI, and packaging checks.

The first runtime integration target is simple:

    from holoutopia_citizen_simulation import simulate_city_at_time
    frame = simulate_city_at_time(ROOT, "08:00")

The returned frame contains citizen positions, current activities, occupancy counts,
and append-only event records suitable for a future activity log panel.
"""

from __future__ import annotations

from dataclasses import dataclass
import copy
import json
from pathlib import Path
from typing import Any, Iterable


class HoloUtopiaSimulationError(ValueError):
    """Raised when authored simulation data cannot be resolved safely."""


@dataclass(frozen=True)
class SimulationNode:
    """Resolved city node used by the citizen schedule runner."""

    id: str
    town_id: str
    kind: str
    grid: tuple[float, float]
    world: tuple[float, float]
    source: str
    tags: tuple[str, ...] = ()
    block_id: str = ""
    lot_id: str = ""


DEFAULT_SAMPLE_TIMES = ("06:00", "08:00", "12:00", "17:30", "21:00")
UTOPIA_RELATIVE = Path("../database/utopia")
ACTIVITY_ALIASES = {
    "leave_home": "commute",
    "work": "work_shift",
    "social_pause": "meal_break",
    "personal_activity": "hobby",
    "seek_nearest_shelter_or_guard_route": "danger_override",
}


def _data_root_from_holoverse_root(holoverse_root: Path) -> Path:
    root = Path(holoverse_root).resolve()
    if (root / "database" / "utopia").exists():
        return root
    if (root / "data" / "database" / "utopia").exists():
        return root / "data"
    if (root.parent / "database" / "utopia").exists():
        return root.parent
    if root.name.lower() in {"holoverse", "holoutopia"}:
        return root.parent
    if root.name.lower() == "tools" and root.parent.name.lower() in {"holoverse", "holoutopia"}:
        return root.parent.parent
    return root


def utopia_data_dir(holoverse_root: Path | str | None = None) -> Path:
    if holoverse_root is None:
        return _data_root_from_holoverse_root(Path(__file__).resolve().parent) / "database" / "utopia"
    return _data_root_from_holoverse_root(Path(holoverse_root)) / "database" / "utopia"


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise HoloUtopiaSimulationError(f"Missing JSON file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise HoloUtopiaSimulationError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise HoloUtopiaSimulationError(f"Expected JSON object in {path}")
    return data


def _read_json_optional(path: Path, fallback: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return dict(fallback or {})
    except json.JSONDecodeError as exc:
        raise HoloUtopiaSimulationError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise HoloUtopiaSimulationError(f"Expected JSON object in {path}")
    return data


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def parse_clock_minutes(value: str) -> int:
    """Convert HH:MM to minutes after midnight."""
    raw = str(value or "").strip()
    if ":" not in raw:
        raise HoloUtopiaSimulationError(f"Invalid clock value {value!r}; expected HH:MM")
    hh, mm = raw.split(":", 1)
    try:
        hour = int(hh)
        minute = int(mm)
    except Exception as exc:
        raise HoloUtopiaSimulationError(f"Invalid clock value {value!r}; expected HH:MM") from exc
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        raise HoloUtopiaSimulationError(f"Clock value out of range: {value!r}")
    return hour * 60 + minute


def format_clock_minutes(minutes: int) -> str:
    minutes = int(minutes) % (24 * 60)
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def load_simulation_inputs(holoverse_root: Path | str | None = None) -> dict[str, Any]:
    """Load all authored data needed by the schedule runner."""
    root = utopia_data_dir(holoverse_root)
    citizens_dir = root / "citizens"
    simulation_dir = root / "simulation"
    towns_dir = root / "towns"
    neighborhoods_dir = root / "neighborhoods"
    return {
        "utopia_root": root,
        "city_atlas": _read_json(root / "city_grid_atlas.json"),
        "citizen_manifest": _read_json(citizens_dir / "citizen_manifest.json"),
        "citizen_schedules": _read_json(citizens_dir / "citizen_schedules.json"),
        "citizen_relationships": _read_json(citizens_dir / "citizen_relationships.json"),
        "activity_catalog": _read_json(citizens_dir / "activity_catalog.json"),
        "social_circles": _read_json(citizens_dir / "citizen_social_circles.json"),
        "city_time_profile": _read_json(simulation_dir / "city_time_profile.json"),
        "simulation_rules": _read_json(simulation_dir / "citizen_simulation_rules.json"),
        "civilian_visit_rules": _read_json_optional(simulation_dir / "civilian_visit_rules.json", {"schema": 1, "enabled": False}),
        "towns": {p.stem: _read_json(p) for p in sorted(towns_dir.glob("*.json")) if p.name != "town_schema.json"},
        "neighborhoods": {p.stem: _read_json(p) for p in sorted(neighborhoods_dir.glob("*.json")) if p.name != "neighborhood_schema.json"},
    }


def _atlas_position(atlas: dict[str, Any], town_id: str) -> tuple[int, int]:
    for town in _as_list(atlas.get("towns")):
        if str(town.get("town_id")) == town_id:
            raw = town.get("city_grid", [0, 0])
            return int(raw[0]), int(raw[1])
    return 0, 0


def _district_origin(atlas: dict[str, Any], town_id: str) -> tuple[float, float]:
    frame_w, frame_h = atlas.get("canonical_grid_size", [10, 8])
    gap = int(atlas.get("district_gap_blocks", 2))
    block_size = float(atlas.get("block_size", 64))
    gx, gy = _atlas_position(atlas, town_id)
    return gx * (int(frame_w) + gap) * block_size, gy * (int(frame_h) + gap) * block_size


def _grid_to_world(atlas: dict[str, Any], town_id: str, grid: Iterable[float]) -> tuple[float, float]:
    block_size = float(atlas.get("block_size", 64))
    gx, gy = list(grid)[:2]
    ox, oy = _district_origin(atlas, town_id)
    return ox + (float(gx) + 0.5) * block_size, oy + (float(gy) + 0.5) * block_size


def build_node_index(inputs: dict[str, Any]) -> dict[str, SimulationNode]:
    """Resolve town, block, lot, and micro-schedule nodes to city-space positions."""
    atlas = inputs["city_atlas"]
    index: dict[str, SimulationNode] = {}
    block_lookup: dict[tuple[str, str], dict[str, Any]] = {}

    def add_node(node_id: str, town_id: str, grid: Iterable[float], *, kind: str = "node", source: str, tags: Iterable[str] = (), block_id: str = "", lot_id: str = "") -> None:
        if not node_id:
            return
        grid_pair = tuple(float(v) for v in list(grid)[:2])
        world_pair = _grid_to_world(atlas, town_id, grid_pair)
        index[node_id] = SimulationNode(
            id=node_id,
            town_id=town_id,
            kind=str(kind or "node"),
            grid=grid_pair,
            world=world_pair,
            source=source,
            tags=tuple(str(t) for t in tags),
            block_id=str(block_id or ""),
            lot_id=str(lot_id or ""),
        )

    for town_id, town in sorted(inputs["towns"].items()):
        for block in _as_list(town.get("town_blocks")):
            if not isinstance(block, dict):
                continue
            block_id = str(block.get("id", "")).strip()
            grid = block.get("grid")
            if block_id and isinstance(grid, list) and len(grid) >= 2:
                block_lookup[(town_id, block_id)] = block
                add_node(
                    block_id,
                    town_id,
                    grid,
                    kind=str(block.get("type") or "block"),
                    source="town_block",
                    tags=_as_list(block.get("tags")),
                    block_id=block_id,
                )
        for node in _as_list(town.get("schedule_nodes")):
            if not isinstance(node, dict):
                continue
            node_id = str(node.get("id", "")).strip()
            grid = node.get("grid")
            if node_id and isinstance(grid, list) and len(grid) >= 2:
                add_node(
                    node_id,
                    town_id,
                    grid,
                    kind=str(node.get("kind") or "schedule"),
                    source="town_schedule_node",
                    tags=_as_list(node.get("tags")),
                    block_id=str(node.get("block") or ""),
                )

    for neighborhood_id, neighborhood in sorted(inputs["neighborhoods"].items()):
        town_id = str(neighborhood.get("town_id", "")).strip()
        if not town_id:
            continue
        for lot in _as_list(neighborhood.get("lots")):
            if not isinstance(lot, dict):
                continue
            block_id = str(lot.get("block", "")).strip()
            lot_id = str(lot.get("id", "")).strip()
            block = block_lookup.get((town_id, block_id), {})
            base_grid = block.get("grid", [0, 0])
            if lot.get("home_node"):
                add_node(
                    str(lot.get("home_node")),
                    town_id,
                    base_grid,
                    kind="home",
                    source=f"neighborhood_lot:{neighborhood_id}",
                    tags=["home", neighborhood_id, lot_id],
                    block_id=block_id,
                    lot_id=lot_id,
                )
            anchors = lot.get("anchors") if isinstance(lot.get("anchors"), dict) else {}
            for anchor in anchors.values():
                if not isinstance(anchor, dict):
                    continue
                anchor_id = str(anchor.get("id", "")).strip()
                offset = anchor.get("local_offset", [0, 0])
                if anchor_id and isinstance(offset, list) and len(offset) >= 2:
                    add_node(
                        anchor_id,
                        town_id,
                        [float(base_grid[0]) + float(offset[0]), float(base_grid[1]) + float(offset[1])],
                        kind=str(anchor.get("kind") or "lot_anchor"),
                        source=f"lot_anchor:{neighborhood_id}",
                        tags=["lot_anchor", neighborhood_id, lot_id],
                        block_id=block_id,
                        lot_id=lot_id,
                    )
        for micro in _as_list(neighborhood.get("micro_schedule_nodes")):
            if not isinstance(micro, dict):
                continue
            micro_id = str(micro.get("id", "")).strip()
            block_id = str(micro.get("block", "")).strip()
            lot_id = str(micro.get("lot", "")).strip()
            block = block_lookup.get((town_id, block_id), {})
            base_grid = block.get("grid", [0, 0])
            offset = micro.get("local_offset", [0, 0])
            if micro_id and isinstance(offset, list) and len(offset) >= 2:
                add_node(
                    micro_id,
                    town_id,
                    [float(base_grid[0]) + float(offset[0]), float(base_grid[1]) + float(offset[1])],
                    kind=str(micro.get("kind") or "micro_schedule"),
                    source=f"micro_schedule:{neighborhood_id}",
                    tags=_as_list(micro.get("tags")),
                    block_id=block_id,
                    lot_id=lot_id,
                )
    return index


def _citizen_records(inputs: dict[str, Any]) -> list[dict[str, Any]]:
    citizens = inputs["citizen_manifest"].get("citizens")
    if not isinstance(citizens, list):
        raise HoloUtopiaSimulationError("citizen_manifest.citizens must be a list")
    return citizens


def _schedule_map(inputs: dict[str, Any]) -> dict[str, dict[str, Any]]:
    schedules = inputs["citizen_schedules"].get("schedules")
    if not isinstance(schedules, dict):
        raise HoloUtopiaSimulationError("citizen_schedules.schedules must be an object")
    return schedules


def select_schedule_block(schedule: dict[str, Any], clock: str) -> tuple[int, dict[str, Any]]:
    blocks = [b for b in _as_list(schedule.get("blocks")) if isinstance(b, dict)]
    if not blocks:
        raise HoloUtopiaSimulationError(f"Schedule {schedule.get('id')} has no blocks")
    minute = parse_clock_minutes(clock)
    keyed = sorted((parse_clock_minutes(str(block.get("time"))), i, block) for i, block in enumerate(blocks))
    selected = keyed[-1]
    for item in keyed:
        if item[0] <= minute:
            selected = item
        else:
            break
    return int(selected[1]), selected[2]


def _safe_node_for_town(node_index: dict[str, SimulationNode], town_id: str) -> SimulationNode | None:
    priority_tags = ("shelter", "safe", "triage", "guard", "security")
    for tag in priority_tags:
        for node in node_index.values():
            if node.town_id == town_id and tag in node.tags:
                return node
    for node in node_index.values():
        if node.town_id == town_id:
            return node
    return node_index.get("core_plaza_center")


def _resolve_target_node(target_id: str, citizen: dict[str, Any], node_index: dict[str, SimulationNode], *, danger_state: bool = False) -> tuple[SimulationNode | None, str]:
    if danger_state or target_id == "nearest_safe_node":
        town_id = str(citizen.get("town_id") or citizen.get("job", {}).get("work_town_id") or "central_core_civic_ring")
        return _safe_node_for_town(node_index, town_id), "danger_safe_node"
    if target_id in node_index:
        return node_index[target_id], "resolved"
    # Last resort: home node, then district seed, then core plaza.
    home_node = str(citizen.get("home_node", "")).strip()
    if home_node in node_index:
        return node_index[home_node], f"fallback_home_missing_target:{target_id}"
    town_id = str(citizen.get("town_id") or "central_core_civic_ring")
    return _safe_node_for_town(node_index, town_id), f"fallback_safe_missing_target:{target_id}"


def build_building_occupancy_index(inputs: dict[str, Any]) -> dict[str, Any]:
    """Build derived home/work occupancy without mutating authored citizen files."""
    home_lots: dict[str, dict[str, Any]] = {}
    work_nodes: dict[str, dict[str, Any]] = {}
    towns: dict[str, dict[str, int]] = {}
    for citizen in _citizen_records(inputs):
        cid = str(citizen.get("id"))
        town_id = str(citizen.get("town_id"))
        towns.setdefault(town_id, {"residents": 0, "workers": 0})["residents"] += 1
        home_lot = str(citizen.get("home_lot_id") or "unknown_home_lot")
        h = home_lots.setdefault(home_lot, {
            "home_lot_id": home_lot,
            "town_id": town_id,
            "neighborhood_id": str(citizen.get("neighborhood_id") or ""),
            "citizens": [],
        })
        h["citizens"].append(cid)
        job = citizen.get("job") if isinstance(citizen.get("job"), dict) else {}
        work_town = str(job.get("work_town_id") or town_id)
        work_node = str(job.get("work_node") or "unknown_work_node")
        towns.setdefault(work_town, {"residents": 0, "workers": 0})["workers"] += 1
        w = work_nodes.setdefault(work_node, {
            "work_node": work_node,
            "town_id": work_town,
            "job_titles": [],
            "citizens": [],
        })
        title = str(job.get("title") or citizen.get("role") or "worker")
        if title not in w["job_titles"]:
            w["job_titles"].append(title)
        w["citizens"].append(cid)
    return {
        "schema": 1,
        "id": "holoutopia_building_occupancy_index_v1",
        "derived_from": ["citizen_manifest.json", "citizen_schedules.json", "neighborhoods/*.json"],
        "runtime_writes_allowed": False,
        "home_lots": dict(sorted(home_lots.items())),
        "work_nodes": dict(sorted(work_nodes.items())),
        "town_summary": dict(sorted(towns.items())),
    }


def _stable_int(seed: str) -> int:
    value = 2166136261
    for ch in str(seed):
        value ^= ord(ch)
        value = (value * 16777619) & 0xFFFFFFFF
    return value


def _stable_fraction(seed: str) -> float:
    return (_stable_int(seed) % 1000003) / 1000003.0


def _rule_int(rules: dict[str, Any], key: str, default: int) -> int:
    try:
        return int(float(rules.get(key, default)))
    except Exception:
        return int(default)


def _visit_minutes_allowed(minute: int, rules: dict[str, Any]) -> bool:
    start = _rule_int(rules, "start_minute", 7 * 60)
    end = _rule_int(rules, "end_minute", 22 * 60)
    minute = int(minute) % (24 * 60)
    if start <= end:
        return start <= minute <= end
    return minute >= start or minute <= end


def _candidate_visit_nodes_for_town(town_id: str, rules: dict[str, Any], node_index: dict[str, SimulationNode]) -> list[str]:
    configured = rules.get("districts") if isinstance(rules.get("districts"), list) else []
    for item in configured:
        if isinstance(item, dict) and str(item.get("town_id") or "") == town_id:
            nodes = [str(n) for n in _as_list(item.get("target_nodes")) if str(n) in node_index]
            if nodes:
                return nodes
    public_priority = ("gather", "social", "service", "gate", "work", "public_green", "recreation", "watch", "district_anchor")
    nodes: list[str] = []
    for kind in public_priority:
        for node in node_index.values():
            if node.town_id == town_id and (node.kind == kind or kind in node.tags):
                nodes.append(node.id)
        if nodes:
            return list(dict.fromkeys(nodes))
    return [node.id for node in node_index.values() if node.town_id == town_id][:4]


def _visit_rule_for_town(town_id: str, rules: dict[str, Any]) -> dict[str, Any]:
    for item in _as_list(rules.get("districts")):
        if isinstance(item, dict) and str(item.get("town_id") or "") == town_id:
            return dict(item)
    return {"town_id": town_id, "display_name": town_id.replace("_", " ").title(), "reasons": ["Civic errand"]}


def _safe_select_schedule(schedule: dict[str, Any], clock: str) -> tuple[int, dict[str, Any]]:
    try:
        return select_schedule_block(schedule, clock)
    except Exception:
        return 0, {}


def build_civilian_visit_plan(data: dict[str, Any], clock: str, node_index: dict[str, SimulationNode]) -> dict[str, dict[str, Any]]:
    """Derive deterministic random-feeling cross-district visits for the current frame.

    The plan is read-only and does not mutate authored schedules. It gives some
    civilians an in-world reason to visit districts outside their normal home/work
    loop so every district can periodically receive public traffic.
    """
    rules = data.get("civilian_visit_rules") if isinstance(data.get("civilian_visit_rules"), dict) else {}
    if not bool(rules.get("enabled", False)):
        return {}
    minute = parse_clock_minutes(clock)
    if not _visit_minutes_allowed(minute, rules):
        return {}
    window_minutes = max(15, _rule_int(rules, "time_window_minutes", 45))
    window = minute // window_minutes
    max_visitors = max(0, _rule_int(rules, "max_visitors_per_frame", 10))
    min_districts = max(0, _rule_int(rules, "min_active_districts_per_frame", 5))
    if max_visitors <= 0:
        return {}
    districts = [d for d in _as_list(rules.get("districts")) if isinstance(d, dict) and str(d.get("town_id") or "").strip()]
    if not districts:
        towns = data.get("towns") if isinstance(data.get("towns"), dict) else {}
        districts = [{"town_id": tid, "display_name": str(town.get("display_name") or tid), "reasons": ["Civic errand"]} for tid, town in sorted(towns.items())]
    activation_chance = max(0.05, min(1.0, float(rules.get("district_activation_chance", 0.68) or 0.68)))
    scored: list[tuple[float, dict[str, Any]]] = []
    for item in districts:
        tid = str(item.get("town_id") or "")
        score = _stable_fraction(f"visit-active:{tid}:{window}:{clock}")
        active = score <= activation_chance
        # Bias at least a minimum number of districts on each frame so the city
        # never looks like only the player's home block has life.
        scored.append((score if active else score + 1.0, item))
    active_districts = [item for _, item in sorted(scored, key=lambda pair: pair[0])[: max(1, min(max_visitors, max(min_districts, 1), len(scored)))]]
    citizens = [c for c in _citizen_records(data) if isinstance(c, dict) and str(c.get("id") or "").strip()]
    schedules = _schedule_map(data)
    plan: dict[str, dict[str, Any]] = {}
    used_citizens: set[str] = set()
    for district in active_districts:
        town_id = str(district.get("town_id") or "")
        target_nodes = _candidate_visit_nodes_for_town(town_id, rules, node_index)
        if not target_nodes:
            continue
        reasons = [str(r) for r in _as_list(district.get("reasons")) if str(r).strip()] or ["Civic errand"]
        prefer_outside = bool(rules.get("prefer_cross_district_visits", True))
        attempts = min(len(citizens), 18)
        start = _stable_int(f"visit-candidate:{town_id}:{window}") % max(1, len(citizens))
        selected: dict[str, Any] | None = None
        selected_block: dict[str, Any] = {}
        selected_index = 0
        for offset in range(attempts):
            citizen = citizens[(start + offset * 7) % len(citizens)]
            cid = str(citizen.get("id") or "")
            if not cid or cid in used_citizens:
                continue
            home_town = str(citizen.get("town_id") or "")
            if prefer_outside and home_town == town_id and offset < attempts - 3:
                continue
            schedule = schedules.get(cid) if isinstance(schedules, dict) else {}
            schedule_index, block = _safe_select_schedule(schedule if isinstance(schedule, dict) else {}, clock)
            activity = _canonical_activity_id(block.get("activity_id") or block.get("action") or "")
            visibility = str(block.get("visibility") or "public_schedule")
            # Keep sleep/home privacy intact and avoid yanking citizens out of the
            # late-night return-home beat. Work blocks are allowed because couriers,
            # guards, researchers, and engineers can have cross-district reasons.
            if visibility == "private_home" or activity in {"wake_up", "sleep"}:
                continue
            if activity == "return_home" and (minute < 8 * 60 or minute > 20 * 60):
                continue
            selected = citizen
            selected_block = dict(block)
            selected_index = schedule_index
            break
        if selected is None:
            continue
        cid = str(selected.get("id") or "")
        used_citizens.add(cid)
        node_id = target_nodes[_stable_int(f"visit-node:{cid}:{town_id}:{window}") % len(target_nodes)]
        reason = reasons[_stable_int(f"visit-reason:{cid}:{town_id}:{window}") % len(reasons)]
        display_name = str(district.get("display_name") or town_id.replace("_", " ").title())
        plan[cid] = {
            "citizen_id": cid,
            "source": "random_civic_visit",
            "window": int(window),
            "window_minutes": int(window_minutes),
            "schedule_index": int(selected_index),
            "previous_activity_id": _canonical_activity_id(selected_block.get("activity_id") or selected_block.get("action") or "unknown_activity"),
            "destination_town_id": town_id,
            "destination_display_name": display_name,
            "target_node": node_id,
            "reason": reason,
            "action": "district_visit",
            "activity_id": "district_errand",
            "duration_minutes": int(rules.get("visit_duration_minutes", window_minutes) or window_minutes),
            "visibility": "public_schedule",
            "interruptible": True,
        }
        if len(plan) >= max_visitors:
            break
    return plan


def simulate_city_at_time(holoverse_root: Path | str | None, clock: str, *, danger_state: bool = False, inputs: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return a deterministic city simulation frame for a single clock time."""
    data = inputs or load_simulation_inputs(holoverse_root)
    node_index = build_node_index(data)
    schedules = _schedule_map(data)
    activity_catalog = data["activity_catalog"].get("activities", {})
    if isinstance(activity_catalog, list):
        activity_ids = {str(item.get("id")) for item in activity_catalog if isinstance(item, dict)}
    elif isinstance(activity_catalog, dict):
        activity_ids = set(activity_catalog.keys())
    else:
        activity_ids = set()
    citizens_out: dict[str, Any] = {}
    events: list[dict[str, Any]] = []
    issues: list[str] = []
    by_activity: dict[str, int] = {}
    by_town: dict[str, int] = {}
    private_hidden = 0
    civilian_visit_plan = {} if danger_state else build_civilian_visit_plan(data, clock, node_index)
    civilian_visits_by_destination: dict[str, int] = {}

    for citizen in _citizen_records(data):
        cid = str(citizen.get("id", "")).strip()
        if not cid:
            issues.append("citizen-without-id")
            continue
        schedule = schedules.get(cid)
        if not isinstance(schedule, dict):
            issues.append(f"missing-schedule:{cid}")
            continue
        schedule_index, block = select_schedule_block(schedule, clock)
        active_block = copy.deepcopy(block)
        civic_visit = civilian_visit_plan.get(cid) if isinstance(civilian_visit_plan, dict) else None
        if isinstance(civic_visit, dict):
            active_block = {
                "time": clock,
                "action": str(civic_visit.get("action") or "district_visit"),
                "target": str(civic_visit.get("target_node") or ""),
                "activity_id": str(civic_visit.get("activity_id") or "district_errand"),
                "duration_minutes": int(civic_visit.get("duration_minutes") or 45),
                "visibility": "public_schedule",
                "interruptible": True,
                "reason": str(civic_visit.get("reason") or "Civic errand"),
            }
        target_id = str(active_block.get("target") or citizen.get("home_node") or "").strip()
        if danger_state:
            override = schedule.get("danger_override") if isinstance(schedule.get("danger_override"), dict) else {}
            active_block = {
                "time": clock,
                "action": str(override.get("action") or "seek_shelter"),
                "target": str(override.get("target") or "nearest_safe_node"),
                "activity_id": str(override.get("activity_id") or "danger_override"),
                "duration_minutes": 30,
                "visibility": "public_schedule",
                "interruptible": False,
            }
            target_id = str(active_block.get("target"))
        node, resolution = _resolve_target_node(target_id, citizen, node_index, danger_state=danger_state)
        if node is None:
            issues.append(f"unresolved-target:{cid}:{target_id}")
            continue
        activity_id = _canonical_activity_id(active_block.get("activity_id") or active_block.get("action") or "unknown_activity")
        if activity_id not in activity_ids:
            issues.append(f"unknown-activity:{cid}:{activity_id}")
        visibility = str(active_block.get("visibility") or "public_schedule")
        location_mode = "private_home_hidden" if visibility == "private_home" else "public_visible"
        if location_mode == "private_home_hidden":
            private_hidden += 1
        friends = list(dict.fromkeys(str(f) for f in _as_list(citizen.get("friends"))))
        by_activity[activity_id] = by_activity.get(activity_id, 0) + 1
        by_town[node.town_id] = by_town.get(node.town_id, 0) + 1
        if isinstance(civic_visit, dict):
            civilian_visits_by_destination[node.town_id] = civilian_visits_by_destination.get(node.town_id, 0) + 1
        citizens_out[cid] = {
            "id": cid,
            "display_name": str(citizen.get("display_name") or cid),
            "role": str(citizen.get("role") or "citizen"),
            "home_town_id": str(citizen.get("town_id") or ""),
            "home_lot_id": str(citizen.get("home_lot_id") or ""),
            "job_title": str((citizen.get("job") if isinstance(citizen.get("job"), dict) else {}).get("title") or ""),
            "schedule_index": schedule_index,
            "action": str(active_block.get("action") or ""),
            "activity_id": activity_id,
            "target_node": target_id,
            "resolved_node": node.id,
            "target_resolution": resolution,
            "town_id": node.town_id,
            "location_mode": location_mode,
            "visibility": visibility,
            "position": {"x": round(node.world[0], 3), "y": round(node.world[1], 3)},
            "friends": friends,
            "interruptible": bool(active_block.get("interruptible", True)),
            "civic_visit": dict(civic_visit) if isinstance(civic_visit, dict) else None,
            "visit_reason": str(civic_visit.get("reason") or "") if isinstance(civic_visit, dict) else "",
            "visit_destination": str(civic_visit.get("destination_display_name") or "") if isinstance(civic_visit, dict) else "",
        }
        event_result = "civic_visit" if isinstance(civic_visit, dict) else ("scheduled" if not danger_state else "danger_override")
        events.append({
            "time": f"day_01_{clock}",
            "citizen_id": cid,
            "display_name": str(citizen.get("display_name") or cid),
            "event": activity_id,
            "action": str(active_block.get("action") or ""),
            "town_id": node.town_id,
            "node_id": node.id,
            "visibility": visibility,
            "result": event_result,
            "reason": str(civic_visit.get("reason") or "") if isinstance(civic_visit, dict) else "",
            "visit_destination": str(civic_visit.get("destination_display_name") or "") if isinstance(civic_visit, dict) else "",
        })
    return {
        "schema": 1,
        "id": f"holoutopia_schedule_frame_{clock.replace(':', '')}",
        "clock": clock,
        "danger_state": bool(danger_state),
        "citizen_count": len(citizens_out),
        "private_home_hidden": private_hidden,
        "by_activity": dict(sorted(by_activity.items())),
        "by_town": dict(sorted(by_town.items())),
        "civic_visits": {
            "enabled": bool((data.get("civilian_visit_rules") if isinstance(data.get("civilian_visit_rules"), dict) else {}).get("enabled", False)),
            "active_count": len(civilian_visit_plan),
            "by_destination_town": dict(sorted(civilian_visits_by_destination.items())),
            "visitor_ids": sorted(civilian_visit_plan.keys()),
        },
        "citizens": dict(sorted(citizens_out.items())),
        "events": events,
        "issues": issues,
    }


def simulate_city_day(holoverse_root: Path | str | None = None, sample_times: Iterable[str] = DEFAULT_SAMPLE_TIMES, *, danger_state: bool = False) -> dict[str, Any]:
    """Return deterministic sample frames across one authored city day."""
    inputs = load_simulation_inputs(holoverse_root)
    frames = [simulate_city_at_time(holoverse_root, str(clock), danger_state=danger_state, inputs=inputs) for clock in sample_times]
    return {
        "schema": 1,
        "id": "holoutopia_citizen_day_simulation_v1",
        "sample_times": [str(t) for t in sample_times],
        "danger_state": bool(danger_state),
        "citizen_count": len(_citizen_records(inputs)),
        "frames": frames,
        "building_occupancy_index": build_building_occupancy_index(inputs),
    }


def events_as_jsonl(frames: Iterable[dict[str, Any]]) -> str:
    """Serialize frame events as append-only JSONL text."""
    lines: list[str] = []
    for frame in frames:
        for event in _as_list(frame.get("events")):
            lines.append(json.dumps(event, ensure_ascii=False, sort_keys=True))
    return "\n".join(lines) + ("\n" if lines else "")


def write_simulation_jsonl(path: Path | str, frames: Iterable[dict[str, Any]]) -> Path:
    """Write JSONL activity events to an explicit caller-provided path."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(events_as_jsonl(frames), encoding="utf-8")
    return out


def _canonical_activity_id(value: Any) -> str:
    raw = str(value or "unknown_activity")
    return ACTIVITY_ALIASES.get(raw, raw)
