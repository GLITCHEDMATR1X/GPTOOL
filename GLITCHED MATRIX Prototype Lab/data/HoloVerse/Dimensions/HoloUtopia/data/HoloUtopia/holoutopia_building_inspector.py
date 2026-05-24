"""HoloUtopia building highlight inspector.

Pass 19 keeps inspection mechanics data-first and safe for later runtime use:
- Every district block and residential lot becomes an inspectable building record.
- Highlighting a building returns residents, jobs, capacity, purpose, schedule nodes,
  and interior load policy without mutating authored data.
- Interior details remain lazy: only records with ``highlight_only`` policies should
  request interior blueprints from the renderer/gameplay layer.
- This module has no Panda3D dependency and can run in validators, previews, CI,
  and packaging checks.

Example runtime target:

    from holoutopia_building_inspector import inspect_building
    card = inspect_building(ROOT, "res_alpha_lot_07", clock="12:00")

The returned card is JSON-safe and suitable for a future hover/click panel.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any, Iterable

from holoutopia_citizen_simulation import (
    HoloUtopiaSimulationError,
    build_node_index,
    load_simulation_inputs,
    simulate_city_at_time,
)


class HoloUtopiaInspectionError(ValueError):
    """Raised when building highlight data cannot be resolved safely."""


DEFAULT_HIGHLIGHT_ID = "res_alpha_lot_07"
INSPECTION_FOLDER_NAME = "inspection"
HIGHLIGHT_RULES_NAME = "building_highlight_rules.json"
HIGHLIGHT_INDEX_NAME = "building_highlight_index.json"


@dataclass(frozen=True)
class HighlightTarget:
    """Compact reverse lookup for a node -> inspectable building."""

    building_id: str
    target_kind: str
    town_id: str
    block_id: str = ""
    lot_id: str = ""


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


def inspection_data_dir(holoverse_root: Path | str | None = None) -> Path:
    return utopia_data_dir(holoverse_root) / INSPECTION_FOLDER_NAME


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise HoloUtopiaInspectionError(f"Missing JSON file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise HoloUtopiaInspectionError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise HoloUtopiaInspectionError(f"Expected JSON object in {path}")
    return data


def load_highlight_rules(holoverse_root: Path | str | None = None) -> dict[str, Any]:
    """Load authored inspector/highlight behavior rules."""
    return _read_json(inspection_data_dir(holoverse_root) / HIGHLIGHT_RULES_NAME)


def load_saved_highlight_index(holoverse_root: Path | str | None = None) -> dict[str, Any]:
    """Load a generated highlight index if one has been committed with the patch."""
    return _read_json(inspection_data_dir(holoverse_root) / HIGHLIGHT_INDEX_NAME)


def _citizens(inputs: dict[str, Any]) -> list[dict[str, Any]]:
    citizens = inputs.get("citizen_manifest", {}).get("citizens", [])
    if not isinstance(citizens, list):
        raise HoloUtopiaInspectionError("citizen_manifest.citizens must be a list")
    return [c for c in citizens if isinstance(c, dict)]


def _citizens_by_id(inputs: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(c.get("id")): c for c in _citizens(inputs) if str(c.get("id", "")).strip()}


def _neighborhood_lot_records(inputs: dict[str, Any]) -> dict[str, dict[str, Any]]:
    lots: dict[str, dict[str, Any]] = {}
    for neighborhood_id, neighborhood in sorted(inputs.get("neighborhoods", {}).items()):
        if not isinstance(neighborhood, dict):
            continue
        town_id = str(neighborhood.get("town_id", ""))
        for lot in _as_list(neighborhood.get("lots")):
            if not isinstance(lot, dict):
                continue
            lot_id = str(lot.get("id", "")).strip()
            if not lot_id:
                continue
            merged = dict(lot)
            merged["town_id"] = town_id
            merged["neighborhood_id"] = str(neighborhood_id)
            lots[lot_id] = merged
    return lots


def _town_block_records(inputs: dict[str, Any]) -> dict[str, dict[str, Any]]:
    blocks: dict[str, dict[str, Any]] = {}
    for town_id, town in sorted(inputs.get("towns", {}).items()):
        if not isinstance(town, dict):
            continue
        for block in _as_list(town.get("town_blocks")):
            if not isinstance(block, dict):
                continue
            block_id = str(block.get("id", "")).strip()
            if not block_id:
                continue
            merged = dict(block)
            merged["town_id"] = str(town_id)
            merged["town_display_name"] = str(town.get("display_name") or town_id)
            merged["district_type"] = str(town.get("district_type") or "")
            blocks[f"{town_id}:{block_id}"] = merged
    return blocks


def _town_nodes_by_id(inputs: dict[str, Any]) -> dict[str, dict[str, Any]]:
    nodes: dict[str, dict[str, Any]] = {}
    for town_id, town in sorted(inputs.get("towns", {}).items()):
        for node in _as_list(town.get("schedule_nodes")):
            if not isinstance(node, dict):
                continue
            node_id = str(node.get("id", "")).strip()
            if not node_id:
                continue
            merged = dict(node)
            merged["town_id"] = str(town_id)
            nodes[node_id] = merged
    return nodes


def _lot_ids_by_block(inputs: dict[str, Any]) -> dict[tuple[str, str], list[str]]:
    out: dict[tuple[str, str], list[str]] = {}
    for lot_id, lot in _neighborhood_lot_records(inputs).items():
        key = (str(lot.get("town_id", "")), str(lot.get("block", "")))
        out.setdefault(key, []).append(lot_id)
    return {key: sorted(value) for key, value in out.items()}


def _resident_ids_by_lot(inputs: dict[str, Any]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for citizen in _citizens(inputs):
        lot_id = str(citizen.get("home_lot_id", "")).strip()
        cid = str(citizen.get("id", "")).strip()
        if lot_id and cid:
            out.setdefault(lot_id, []).append(cid)
    return {key: sorted(value) for key, value in out.items()}


def _worker_ids_by_node(inputs: dict[str, Any]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for citizen in _citizens(inputs):
        job = citizen.get("job") if isinstance(citizen.get("job"), dict) else {}
        node = str(job.get("work_node", "")).strip()
        cid = str(citizen.get("id", "")).strip()
        if node and cid:
            out.setdefault(node, []).append(cid)
    return {key: sorted(value) for key, value in out.items()}




def _nearest_block_key_for_node(inputs: dict[str, Any], town_id: str, node_id: str) -> str:
    """Resolve loose public/schedule nodes to the nearest inspectable district block."""
    town = inputs.get("towns", {}).get(town_id, {}) if isinstance(inputs.get("towns"), dict) else {}
    target = _town_nodes_by_id(inputs).get(node_id, {})
    raw_grid = target.get("grid") if isinstance(target, dict) else None
    if not isinstance(raw_grid, list) or len(raw_grid) < 2:
        return ""
    try:
        tx, ty = float(raw_grid[0]), float(raw_grid[1])
    except Exception:
        return ""
    best_key = ""
    best_dist = 10**9
    for block in _as_list(town.get("town_blocks")):
        if not isinstance(block, dict):
            continue
        block_id = str(block.get("id", "")).strip()
        grid = block.get("grid")
        size = block.get("size", [1, 1])
        if not block_id or not isinstance(grid, list) or len(grid) < 2:
            continue
        try:
            bx = float(grid[0]) + (float(size[0]) - 1.0) * 0.5
            by = float(grid[1]) + (float(size[1]) - 1.0) * 0.5
        except Exception:
            continue
        dist = (bx - tx) ** 2 + (by - ty) ** 2
        if dist < best_dist:
            best_dist = dist
            best_key = f"{town_id}:{block_id}"
    return best_key

def _worker_ids_by_building(inputs: dict[str, Any]) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """Return workers by district-block building id and by residential lot id."""
    node_index = build_node_index(inputs)
    by_block: dict[str, list[str]] = {}
    by_lot: dict[str, list[str]] = {}
    for citizen in _citizens(inputs):
        job = citizen.get("job") if isinstance(citizen.get("job"), dict) else {}
        node_id = str(job.get("work_node", "")).strip()
        cid = str(citizen.get("id", "")).strip()
        if not node_id or not cid:
            continue
        node = node_index.get(node_id)
        town_id = str(job.get("work_town_id") or citizen.get("town_id") or "")
        if node is not None:
            town_id = node.town_id or town_id
            if node.lot_id:
                by_lot.setdefault(node.lot_id, []).append(cid)
            if node.block_id:
                by_block.setdefault(f"{town_id}:{node.block_id}", []).append(cid)
            else:
                nearest = _nearest_block_key_for_node(inputs, town_id, node.id)
                if nearest:
                    by_block.setdefault(nearest, []).append(cid)
        else:
            # Fallback through authored town schedule node block references.
            town_nodes = _town_nodes_by_id(inputs)
            raw = town_nodes.get(node_id, {})
            block_id = str(raw.get("block", "")).strip()
            if block_id:
                by_block.setdefault(f"{town_id}:{block_id}", []).append(cid)
            else:
                nearest = _nearest_block_key_for_node(inputs, town_id, node_id)
                if nearest:
                    by_block.setdefault(nearest, []).append(cid)
    return {k: sorted(set(v)) for k, v in by_block.items()}, {k: sorted(set(v)) for k, v in by_lot.items()}


def _citizen_summary(citizen: dict[str, Any]) -> dict[str, Any]:
    job = citizen.get("job") if isinstance(citizen.get("job"), dict) else {}
    return {
        "id": str(citizen.get("id", "")),
        "display_name": str(citizen.get("display_name") or citizen.get("id") or "Citizen"),
        "role": str(citizen.get("role") or "citizen"),
        "job_title": str(job.get("title") or citizen.get("role") or ""),
        "work_town_id": str(job.get("work_town_id") or citizen.get("town_id") or ""),
        "work_node": str(job.get("work_node") or ""),
        "friends": list(dict.fromkeys(str(f) for f in _as_list(citizen.get("friends")))),
    }


def _capacity_for_lot(lot: dict[str, Any]) -> int:
    profile = lot.get("building_profile") if isinstance(lot.get("building_profile"), dict) else {}
    try:
        return max(0, int(profile.get("residential_capacity", 0)))
    except Exception:
        return 0


def _height_for_lot(lot: dict[str, Any]) -> dict[str, Any]:
    profile = lot.get("building_profile") if isinstance(lot.get("building_profile"), dict) else {}
    return {
        "building_type": str(profile.get("building_type") or lot.get("type") or "residential"),
        "height_class": str(profile.get("height_class") or "low"),
        "floor_count": int(profile.get("floor_count", 1) or 1),
        "height_units": float(profile.get("height_units", lot.get("footprint", {}).get("height_units", 12)) or 12),
        "roof_type": str(profile.get("roof_type") or "flat"),
    }


def _display_name_for_block(block: dict[str, Any], block_id: str) -> str:
    """Prefer a short player-facing site name over repeated purpose text."""
    explicit = str(block.get("display_name") or block.get("name") or "").strip()
    if explicit:
        return explicit
    raw = str(block_id or "").replace("block_", "").replace("res_alpha_", "residential_")
    text = raw.replace("_", " ").replace("-", " ").strip()
    return text.title() if text else str(block.get("purpose_summary") or "District Site")


def _height_for_block(block: dict[str, Any]) -> dict[str, Any]:
    profile = block.get("structure_massing_profile") if isinstance(block.get("structure_massing_profile"), dict) else {}
    return {
        "building_type": str(profile.get("massing_kind") or block.get("type") or "district_structure"),
        "height_class": str(profile.get("height_class") or "low"),
        "floor_count": int(profile.get("floor_count", 1) or 1),
        "height_units": float(profile.get("height_units", 12) or 12),
        "roof_type": str(profile.get("roof_profile") or "flat"),
    }


def _activity_nodes_for_block(inputs: dict[str, Any], town_id: str, block_id: str) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    for node in _town_nodes_by_id(inputs).values():
        if str(node.get("town_id")) == town_id and str(node.get("block", "")) == block_id:
            nodes.append({
                "id": str(node.get("id")),
                "kind": str(node.get("kind") or "schedule"),
                "tags": list(str(t) for t in _as_list(node.get("tags"))),
            })
    return sorted(nodes, key=lambda item: item["id"])


def _micro_nodes_for_lot(inputs: dict[str, Any], neighborhood_id: str, lot_id: str) -> list[dict[str, Any]]:
    neighborhood = inputs.get("neighborhoods", {}).get(neighborhood_id, {})
    nodes = []
    for node in _as_list(neighborhood.get("micro_schedule_nodes")):
        if isinstance(node, dict) and str(node.get("lot", "")) == lot_id:
            nodes.append({
                "id": str(node.get("id")),
                "kind": str(node.get("kind") or "micro_schedule"),
                "tags": list(str(t) for t in _as_list(node.get("tags"))),
            })
    return sorted(nodes, key=lambda item: item["id"])


def _inspection_policy(kind: str, interior_policy: str, has_interior: bool) -> dict[str, Any]:
    allow_interior = has_interior and str(interior_policy or "").strip() == "highlight_only"
    return {
        "selectable": True,
        "show_panel": True,
        "show_residents": True,
        "show_workers": True,
        "load_interior_on_highlight": bool(allow_interior),
        "interior_load_policy": "highlight_only" if allow_interior else str(interior_policy or "exterior_only"),
        "unload_interior_on_selection_change": bool(allow_interior),
        "highlight_kind": kind,
    }


def build_highlight_index(holoverse_root: Path | str | None = None, *, clock: str = "12:00", danger_state: bool = False) -> dict[str, Any]:
    """Build a JSON-safe inspectable-building index from authored city data."""
    inputs = load_simulation_inputs(holoverse_root)
    citizen_map = _citizens_by_id(inputs)
    lots = _neighborhood_lot_records(inputs)
    blocks = _town_block_records(inputs)
    lots_by_block = _lot_ids_by_block(inputs)
    residents_by_lot = _resident_ids_by_lot(inputs)
    workers_by_block, workers_by_lot = _worker_ids_by_building(inputs)
    node_index = build_node_index(inputs)

    active_frame = simulate_city_at_time(holoverse_root, clock, danger_state=danger_state, inputs=inputs)
    active_by_block: dict[str, list[str]] = {}
    active_by_lot: dict[str, list[str]] = {}
    for cid, state in active_frame.get("citizens", {}).items():
        node = node_index.get(str(state.get("resolved_node", "")))
        if node is None:
            continue
        if node.block_id:
            active_by_block.setdefault(f"{node.town_id}:{node.block_id}", []).append(str(cid))
        else:
            nearest = _nearest_block_key_for_node(inputs, node.town_id, node.id)
            if nearest:
                active_by_block.setdefault(nearest, []).append(str(cid))
        if node.lot_id:
            active_by_lot.setdefault(node.lot_id, []).append(str(cid))

    records: dict[str, dict[str, Any]] = {}

    for block_key, block in sorted(blocks.items()):
        town_id = str(block.get("town_id", ""))
        block_id = str(block.get("id", ""))
        linked_lot_ids = lots_by_block.get((town_id, block_id), [])
        residents = sorted({cid for lot_id in linked_lot_ids for cid in residents_by_lot.get(lot_id, [])})
        workers = workers_by_block.get(block_key, [])
        active = sorted(set(active_by_block.get(block_key, [])))
        linked_lots = []
        capacity = 0
        for lot_id in linked_lot_ids:
            lot = lots.get(lot_id, {})
            cap = _capacity_for_lot(lot)
            capacity += cap
            linked_lots.append({
                "id": lot_id,
                "address": str(lot.get("address") or lot_id),
                "residential_capacity": cap,
                "interior_blueprint_id": str(lot.get("interior_blueprint_id") or ""),
            })
        inspection = _inspection_policy("district_block", str(block.get("interior_policy") or "exterior_only"), False)
        center = node_index.get(block_id)
        records[block_key] = {
            "id": block_key,
            "display_name": _display_name_for_block(block, block_id),
            "highlight_kind": "district_block",
            "town_id": town_id,
            "town_display_name": str(block.get("town_display_name") or town_id),
            "district_type": str(block.get("district_type") or ""),
            "block_id": block_id,
            "lot_id": "",
            "address": "",
            "purpose_id": str(block.get("purpose_id") or ""),
            "purpose_summary": str(block.get("purpose_summary") or ""),
            "structure_variant_id": str(block.get("structure_variant_id") or ""),
            "activity_affordances": list(str(a) for a in _as_list(block.get("activity_affordances"))),
            "massing": _height_for_block(block),
            "residential_capacity": capacity,
            "current_resident_count": len(residents),
            "current_worker_count": len(workers),
            "active_citizen_count": len(active),
            "residents": [_citizen_summary(citizen_map[cid]) for cid in residents if cid in citizen_map],
            "workers": [_citizen_summary(citizen_map[cid]) for cid in workers if cid in citizen_map],
            "active_citizens": [_citizen_summary(citizen_map[cid]) for cid in active if cid in citizen_map],
            "linked_lots": linked_lots,
            "schedule_nodes": _activity_nodes_for_block(inputs, town_id, block_id),
            "micro_schedule_nodes": [],
            "interior_blueprint_id": "",
            "interior_policy": str(block.get("interior_policy") or "exterior_only"),
            "inspection_policy": inspection,
            "world_position": {"x": round(center.world[0], 3), "y": round(center.world[1], 3)} if center else {"x": 0.0, "y": 0.0},
        }

    for lot_id, lot in sorted(lots.items()):
        town_id = str(lot.get("town_id", ""))
        block_id = str(lot.get("block", ""))
        residents = residents_by_lot.get(lot_id, [])
        workers = workers_by_lot.get(lot_id, [])
        active = sorted(set(active_by_lot.get(lot_id, [])))
        interior_id = str(lot.get("interior_blueprint_id") or "")
        interior_policy = "highlight_only" if interior_id else str(lot.get("interior_policy") or "exterior_only")
        home_node = str(lot.get("home_node") or "")
        center = node_index.get(home_node) or node_index.get(block_id)
        capacity = _capacity_for_lot(lot)
        records[lot_id] = {
            "id": lot_id,
            "display_name": str(lot.get("address") or lot_id),
            "highlight_kind": "residential_lot",
            "town_id": town_id,
            "town_display_name": str(inputs.get("towns", {}).get(town_id, {}).get("display_name") or town_id),
            "district_type": str(inputs.get("towns", {}).get(town_id, {}).get("district_type") or ""),
            "block_id": block_id,
            "lot_id": lot_id,
            "address": str(lot.get("address") or ""),
            "purpose_id": "residential_home",
            "purpose_summary": str(lot.get("purpose_summary") or lot.get("type") or "Residential property"),
            "structure_variant_id": str(lot.get("building_profile", {}).get("style_variant") or lot.get("type") or "residential"),
            "activity_affordances": ["home", "sleep", "visit_friend", "return_home"],
            "massing": _height_for_lot(lot),
            "residential_capacity": capacity,
            "current_resident_count": len(residents),
            "current_worker_count": len(workers),
            "active_citizen_count": len(active),
            "residents": [_citizen_summary(citizen_map[cid]) for cid in residents if cid in citizen_map],
            "workers": [_citizen_summary(citizen_map[cid]) for cid in workers if cid in citizen_map],
            "active_citizens": [_citizen_summary(citizen_map[cid]) for cid in active if cid in citizen_map],
            "linked_lots": [],
            "schedule_nodes": [],
            "micro_schedule_nodes": _micro_nodes_for_lot(inputs, str(lot.get("neighborhood_id", "")), lot_id),
            "interior_blueprint_id": interior_id,
            "interior_policy": interior_policy,
            "inspection_policy": _inspection_policy("residential_lot", interior_policy, bool(interior_id)),
            "world_position": {"x": round(center.world[0], 3), "y": round(center.world[1], 3)} if center else {"x": 0.0, "y": 0.0},
        }

    total_capacity = sum(int(r.get("residential_capacity", 0)) for r in records.values() if r.get("highlight_kind") == "residential_lot")
    return {
        "schema": 1,
        "id": "holoutopia_building_highlight_index_v1",
        "derived_from": [
            "towns/*.json",
            "neighborhoods/*.json",
            "citizens/citizen_manifest.json",
            "citizens/citizen_schedules.json",
            "simulation/citizen_simulation_rules.json",
        ],
        "runtime_writes_allowed": False,
        "clock_sample": clock,
        "danger_state": bool(danger_state),
        "highlight_contract": {
            "selection_priority": ["residential_lot", "district_block"],
            "interior_load_policy": "highlight_only",
            "unload_interior_on_selection_change": True,
            "safe_to_render_without_panda3d": True,
        },
        "totals": {
            "highlight_records": len(records),
            "district_block_records": sum(1 for r in records.values() if r.get("highlight_kind") == "district_block"),
            "residential_lot_records": sum(1 for r in records.values() if r.get("highlight_kind") == "residential_lot"),
            "residential_capacity": total_capacity,
            "resident_assignments": sum(len(r.get("residents", [])) for r in records.values() if r.get("highlight_kind") == "residential_lot"),
            "worker_assignments": sum(len(r.get("workers", [])) for r in records.values()),
            "active_assignments": sum(len(r.get("active_citizens", [])) for r in records.values()),
        },
        "records": dict(sorted(records.items())),
    }


def inspect_building(holoverse_root: Path | str | None, building_id: str = DEFAULT_HIGHLIGHT_ID, *, clock: str = "12:00", danger_state: bool = False) -> dict[str, Any]:
    """Return one highlight panel payload for a selected building or lot."""
    index = build_highlight_index(holoverse_root, clock=clock, danger_state=danger_state)
    records = index.get("records", {}) if isinstance(index.get("records"), dict) else {}
    key = str(building_id or "").strip()
    if key not in records:
        # Convenience: if a raw block id is provided and it is unique, resolve it.
        matches = [rid for rid, rec in records.items() if rec.get("block_id") == key or rec.get("lot_id") == key]
        if len(matches) == 1:
            key = matches[0]
        else:
            raise HoloUtopiaInspectionError(f"Unknown or ambiguous building highlight id {building_id!r}")
    record = dict(records[key])
    return {
        "schema": 1,
        "id": f"holoutopia_building_inspection_{key}",
        "clock": clock,
        "danger_state": bool(danger_state),
        "building": record,
        "panel_lines": format_inspection_panel(record),
        "runtime_writes_allowed": False,
    }


def format_inspection_panel(record: dict[str, Any]) -> list[str]:
    """Format a compact human-readable panel from a highlight record."""
    massing = record.get("massing") if isinstance(record.get("massing"), dict) else {}
    lines = [
        str(record.get("display_name") or record.get("id") or "Building"),
        f"District: {record.get('town_display_name') or record.get('town_id')}",
        f"Purpose: {record.get('purpose_summary') or record.get('purpose_id')}",
        f"Type: {massing.get('building_type', 'structure')} / {massing.get('height_class', 'low')} / {massing.get('floor_count', 1)} floors",
        f"Capacity: {record.get('current_resident_count', 0)}/{record.get('residential_capacity', 0)} residents",
        f"Workers: {record.get('current_worker_count', 0)} | Active now: {record.get('active_citizen_count', 0)}",
        f"Interior: {record.get('inspection_policy', {}).get('interior_load_policy', record.get('interior_policy', 'exterior_only'))}",
    ]
    residents = record.get("residents", [])
    workers = record.get("workers", [])
    if residents:
        lines.append("Residents: " + ", ".join(str(r.get("display_name")) for r in residents[:4]) + ("…" if len(residents) > 4 else ""))
    if workers:
        lines.append("Workers: " + ", ".join(str(w.get("display_name")) for w in workers[:4]) + ("…" if len(workers) > 4 else ""))
    return lines


def write_highlight_index(path: Path | str, holoverse_root: Path | str | None = None, *, clock: str = "12:00") -> Path:
    """Write the derived building highlight index to an explicit path."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    index = build_highlight_index(holoverse_root, clock=clock)
    out.write_text(json.dumps(index, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    return out
