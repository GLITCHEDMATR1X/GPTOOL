"""Street-safe outdoor placement for HoloUtopia citizens.

Pass 39B keeps population/garrison simulation virtual while making visible
representatives obey authored street/activity-pad geometry.  The module is
pure Python so validators can prove that rendered people do not stand on
building footprints before Panda3D runs.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable

_ATLAS_CACHE: dict[str, dict[str, Any]] = {}
_TOWN_CACHE: dict[tuple[str, str], dict[str, Any]] = {}
_SAFE_SAMPLE_CACHE: dict[tuple[str, str], list[dict[str, Any]]] = {}
_ACTIVITY_CLUSTER_CACHE: dict[str, dict[str, Any]] = {}



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


def _read_json(path: Path, fallback: Any) -> Any:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback
    return data if isinstance(data, type(fallback)) else fallback


def load_activity_cluster_rules(holoverse_root: Path | str | None = None) -> dict[str, Any]:
    key = _cache_root_key(holoverse_root)
    if key not in _ACTIVITY_CLUSTER_CACHE:
        _ACTIVITY_CLUSTER_CACHE[key] = _read_json(Path(key) / "simulation" / "simulation_hub_activity_clusters.json", {"clusters": []})
    return _ACTIVITY_CLUSTER_CACHE[key]


def _cluster_for_node(holoverse_root: Path | str | None, node_id: str) -> dict[str, Any] | None:
    data = load_activity_cluster_rules(holoverse_root)
    for cluster in data.get("clusters", []) if isinstance(data.get("clusters"), list) else []:
        if isinstance(cluster, dict) and str(cluster.get("node_id") or "") == str(node_id):
            return cluster
    return None


def _activity_cluster_slot_for_citizen(
    holoverse_root: Path | str | None,
    cid: str,
    citizen: dict[str, Any],
    town: dict[str, Any],
    town_id: str,
    target_grid: tuple[float, float],
    node_id: str,
) -> dict[str, Any] | None:
    if not bool(citizen.get("district_activity_representative")):
        return None
    cluster = _cluster_for_node(holoverse_root, node_id)
    if not isinstance(cluster, dict):
        return None
    slots = cluster.get("slot_offsets") if isinstance(cluster.get("slot_offsets"), list) else []
    if not slots:
        return None
    try:
        schedule_index = int(citizen.get("schedule_index", 0) or 0)
    except Exception:
        schedule_index = 0
    # Stable slotting keeps a crowd visibly clustered around pods while avoiding
    # everyone landing on the same point.
    start_slot = (schedule_index + int(_stable_fraction(str(cid), "cluster-slot") * len(slots))) % len(slots)
    # Try the preferred slot first, then rotate through the rest.  Some authored
    # nodes sit next to large buildings, so a single bad offset should not push
    # the citizen back to a generic road if another named cluster slot is safe.
    for offset_idx in range(len(slots)):
        slot_index = (start_slot + offset_idx) % len(slots)
        raw = slots[slot_index]
        try:
            ox = float(raw[0])
            oy = float(raw[1])
        except Exception:
            ox = oy = 0.0
        gx = float(target_grid[0]) + ox
        gy = float(target_grid[1]) + oy
        if is_grid_on_building(town, (gx, gy)):
            continue
        return {
            "town_id": town_id,
            "grid": (float(gx), float(gy)),
            "snapped": True,
            "source": f"activity_cluster:{cluster.get('cluster_id') or node_id}:slot_{slot_index:02d}",
            "target_node": node_id,
            "target_grid": target_grid,
            "cluster_id": str(cluster.get("cluster_id") or ""),
            "activity_family": str(cluster.get("activity_family") or "activity"),
            "on_building": False,
        }
    return None


def _cache_root_key(holoverse_root: Path | str | None = None) -> str:
    return str(utopia_data_dir(holoverse_root).resolve())


def load_city_atlas(holoverse_root: Path | str | None = None) -> dict[str, Any]:
    key = _cache_root_key(holoverse_root)
    if key not in _ATLAS_CACHE:
        _ATLAS_CACHE[key] = _read_json(Path(key) / "city_grid_atlas.json", {})
    return _ATLAS_CACHE[key]


def load_town(holoverse_root: Path | str | None, town_id: str) -> dict[str, Any]:
    key = (_cache_root_key(holoverse_root), str(town_id))
    if key not in _TOWN_CACHE:
        _TOWN_CACHE[key] = _read_json(Path(key[0]) / "towns" / f"{town_id}.json", {})
    return _TOWN_CACHE[key]


def _stable_fraction(key: str, salt: str = "") -> float:
    digest = hashlib.sha256(f"{salt}:{key}".encode("utf-8", "ignore")).digest()
    return int.from_bytes(digest[:8], "big") / float(2**64 - 1)


def _as_pair(value: Any, default: tuple[float, float] = (0.0, 0.0)) -> tuple[float, float]:
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        try:
            return float(value[0]), float(value[1])
        except Exception:
            return default
    return default


def _atlas_metrics(atlas: dict[str, Any]) -> tuple[float, float, float, dict[str, tuple[int, int]]]:
    grid_w, grid_h = atlas.get("canonical_grid_size", [10, 8]) if isinstance(atlas.get("canonical_grid_size"), list) else [10, 8]
    gap = int(atlas.get("district_gap_blocks", 2) or 2)
    block_size = float(atlas.get("block_size", 64) or 64)
    frame_w = (float(grid_w) + gap) * block_size
    frame_h = (float(grid_h) + gap) * block_size
    town_grid: dict[str, tuple[int, int]] = {}
    for entry in atlas.get("towns", []) if isinstance(atlas.get("towns"), list) else []:
        if not isinstance(entry, dict):
            continue
        raw = entry.get("city_grid", [0, 0])
        if isinstance(raw, list) and len(raw) >= 2:
            try:
                town_grid[str(entry.get("town_id") or "")] = (int(raw[0]), int(raw[1]))
            except Exception:
                pass
    return frame_w, frame_h, block_size, town_grid


def grid_to_city_xy(holoverse_root: Path | str | None, town_id: str, grid: Iterable[float]) -> tuple[float, float]:
    """Convert a town-local grid coordinate into the runtime's render XY space."""
    atlas = load_city_atlas(holoverse_root)
    frame_w, frame_h, block_size, town_grid = _atlas_metrics(atlas)
    grid_w, grid_h = atlas.get("canonical_grid_size", [10, 8]) if isinstance(atlas.get("canonical_grid_size"), list) else [10, 8]
    gx, gy = _as_pair(list(grid)[:2] if isinstance(grid, (list, tuple)) else grid)
    tgx, tgy = town_grid.get(str(town_id), (0, 0))
    town_origin_x = tgx * frame_w
    town_origin_y = tgy * frame_h
    x = town_origin_x + (gx - (float(grid_w) - 1.0) * 0.5) * block_size
    y = town_origin_y + ((float(grid_h) - 1.0) * 0.5 - gy) * block_size
    return float(x), float(y)


def _walkable_pad_block(block: dict[str, Any]) -> bool:
    raw = " ".join(str(block.get(key) or "") for key in ("id", "type", "purpose_id", "interior_policy"))
    raw += " " + " ".join(str(t) for t in block.get("tags", []) if isinstance(block.get("tags"), list))
    text = raw.lower()
    # Plazas, gardens and gates are outdoor pads; homes/towers/kiosks/archives are building footprints.
    return any(token in text for token in ("plaza", "garden", "gate", "transit", "portal", "walk", "courtyard"))


def building_exclusion_rects(town: dict[str, Any], *, margin: float = 0.44) -> list[tuple[float, float, float, float, str]]:
    rects: list[tuple[float, float, float, float, str]] = []
    for block in town.get("town_blocks", []) if isinstance(town.get("town_blocks"), list) else []:
        if not isinstance(block, dict) or _walkable_pad_block(block):
            continue
        gx, gy = _as_pair(block.get("grid"), (9999.0, 9999.0))
        sx, sy = _as_pair(block.get("size"), (1.0, 1.0))
        sx = max(0.35, float(sx))
        sy = max(0.35, float(sy))
        half_w = sx * 0.50 + margin
        half_h = sy * 0.50 + margin
        rects.append((gx - half_w, gy - half_h, gx + half_w, gy + half_h, str(block.get("id") or "")))
    return rects


def is_grid_on_building(town: dict[str, Any], grid: Iterable[float], *, margin: float = 0.44) -> bool:
    gx, gy = _as_pair(list(grid)[:2] if isinstance(grid, (list, tuple)) else grid)
    for min_x, min_y, max_x, max_y, _bid in building_exclusion_rects(town, margin=margin):
        if min_x <= gx <= max_x and min_y <= gy <= max_y:
            return True
    return False


def _segment_samples(start: tuple[float, float], end: tuple[float, float], *, count: int, road_id: str, width: float) -> list[dict[str, Any]]:
    sx, sy = start
    ex, ey = end
    dx = ex - sx
    dy = ey - sy
    length = max(0.0001, math.hypot(dx, dy))
    nx = -dy / length
    ny = dx / length
    # Keep offset small so citizens stay on dark street slabs, not traffic stripes or buildings.
    lane_offset = min(0.22, max(0.04, float(width) / 64.0 * 0.15))
    samples: list[dict[str, Any]] = []
    for idx in range(max(2, count)):
        t = idx / float(max(1, count - 1))
        base_x = sx + dx * t
        base_y = sy + dy * t
        for side, mult in (("center", 0.0), ("left", lane_offset), ("right", -lane_offset)):
            samples.append({"grid": (base_x + nx * mult, base_y + ny * mult), "source": f"road:{road_id}:{side}", "t": t})
    return samples


def street_samples(town: dict[str, Any]) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    for road in town.get("roads", []) if isinstance(town.get("roads"), list) else []:
        if not isinstance(road, dict):
            continue
        road_id = str(road.get("id") or "road")
        width = float(road.get("width", 8) or 8)
        kind = str(road.get("kind") or "radial").lower()
        if kind == "radial" and isinstance(road.get("from"), list) and isinstance(road.get("to"), list):
            start = _as_pair(road.get("from"))
            end = _as_pair(road.get("to"))
            # More samples on long roads so people can queue without piling up.
            count = max(8, int(math.hypot(end[0] - start[0], end[1] - start[1]) * 7))
            samples.extend(_segment_samples(start, end, count=count, road_id=road_id, width=width))
        elif kind == "ring" and isinstance(road.get("center"), list):
            cx, cy = _as_pair(road.get("center"))
            radius = float(road.get("radius_blocks", 1.6) or 1.6)
            lane_offset = min(0.18, max(0.04, width / 64.0 * 0.12))
            for idx in range(72):
                angle = math.tau * idx / 72.0
                for label, delta in (("center", 0.0), ("inner", -lane_offset), ("outer", lane_offset)):
                    r = radius + delta
                    samples.append({"grid": (cx + math.cos(angle) * r, cy + math.sin(angle) * r), "source": f"road:{road_id}:{label}", "t": idx / 72.0})
    return samples


def _schedule_activity_pad_samples(town: dict[str, Any]) -> list[dict[str, Any]]:
    pads: list[dict[str, Any]] = []
    public_kinds = {"public", "portal", "transit", "social", "leisure", "shelter", "neighborhood_social_anchor", "neighborhood_seed_anchor"}
    for node in town.get("schedule_nodes", []) if isinstance(town.get("schedule_nodes"), list) else []:
        if not isinstance(node, dict) or not isinstance(node.get("grid"), list):
            continue
        kind = str(node.get("kind") or "").lower()
        tags = {str(t).lower() for t in node.get("tags", []) if isinstance(node.get("tags"), list)}
        if kind not in public_kinds and not ({"portal_ring", "plaza", "safe", "garden"} & tags):
            continue
        gx, gy = _as_pair(node.get("grid"))
        for idx in range(10):
            angle = math.tau * idx / 10.0
            radius = 0.10 + 0.10 * (idx % 3)
            pads.append({"grid": (gx + math.cos(angle) * radius, gy + math.sin(angle) * radius), "source": f"pad:{node.get('id') or 'schedule'}", "t": idx / 10.0})
    return pads


def _target_grid_from_citizen(citizen: dict[str, Any], node_index: dict[str, Any] | None) -> tuple[str, tuple[float, float], str]:
    node_id = str(citizen.get("resolved_node") or citizen.get("target_node") or "")
    town_id = str(citizen.get("town_id") or "")
    node = node_index.get(node_id) if isinstance(node_index, dict) else None
    if node is not None:
        town_id = str(getattr(node, "town_id", town_id) or town_id)
        grid = getattr(node, "grid", (4.0, 3.0))
        return town_id, _as_pair(grid), node_id
    pos = citizen.get("position") if isinstance(citizen.get("position"), dict) else {}
    if pos:
        return town_id or "central_core_civic_ring", (_as_pair([pos.get("grid_x", pos.get("x", 4.0)), pos.get("grid_y", pos.get("y", 3.0))])), node_id
    return town_id or "central_core_civic_ring", (4.0, 3.0), node_id


def _safe_samples_for_town(holoverse_root: Path | str | None, town_id: str) -> list[dict[str, Any]]:
    key = (_cache_root_key(holoverse_root), str(town_id))
    if key not in _SAFE_SAMPLE_CACHE:
        town = load_town(holoverse_root, town_id)
        samples = street_samples(town) + _schedule_activity_pad_samples(town)
        _SAFE_SAMPLE_CACHE[key] = [sample for sample in samples if not is_grid_on_building(town, sample.get("grid", (0.0, 0.0)))]
    return _SAFE_SAMPLE_CACHE[key]


def safe_outdoor_grid_for_citizen(
    holoverse_root: Path | str | None,
    cid: str,
    citizen: dict[str, Any],
    node_index: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve a citizen to a street/activity-pad grid coordinate, never a building roof.

    Garrisoned people are allowed to exist inside home buildings virtually; this
    function is only for public visible representatives.  It therefore snaps any
    home/building target to the nearest authored street sample.
    """
    town_id, target_grid, node_id = _target_grid_from_citizen(citizen, node_index)
    town = load_town(holoverse_root, town_id)
    safe_samples = _safe_samples_for_town(holoverse_root, town_id)
    tx, ty = target_grid
    cluster_slot = _activity_cluster_slot_for_citizen(holoverse_root, str(cid), citizen, town, town_id, target_grid, node_id)
    if cluster_slot is not None:
        return cluster_slot
    if not safe_samples:
        return {"town_id": town_id, "grid": target_grid, "snapped": False, "source": "target_no_samples", "target_node": node_id, "on_building": is_grid_on_building(town, target_grid)}
    # Prefer candidates near the requested node, then use stable slotting so a crowd spreads along the same street/pad.
    ranked = sorted(
        safe_samples,
        key=lambda sample: (float(sample["grid"][0]) - tx) ** 2 + (float(sample["grid"][1]) - ty) ** 2,
    )
    near = ranked[: min(len(ranked), 36)]
    pick = int(_stable_fraction(str(cid), "safe-street-pick") * len(near)) % len(near)
    chosen = near[pick]
    gx, gy = _as_pair(chosen.get("grid"))
    # Tiny jitter within walkable slabs only; if it would hit a building, discard it.
    jitter_r = 0.055 + _stable_fraction(str(cid), "jitter-r") * 0.045
    jitter_a = _stable_fraction(str(cid), "jitter-a") * math.tau
    jx = gx + math.cos(jitter_a) * jitter_r
    jy = gy + math.sin(jitter_a) * jitter_r
    if not is_grid_on_building(town, (jx, jy)):
        gx, gy = jx, jy
    return {
        "town_id": town_id,
        "grid": (float(gx), float(gy)),
        "snapped": True,
        "source": (f"commute:{citizen.get('commute_stage')}:{chosen.get('source') or 'street'}" if bool(citizen.get("commute_flow_representative")) else str(chosen.get("source") or "street")),
        "target_node": node_id,
        "target_grid": target_grid,
        "on_building": False,
    }


def safe_outdoor_xy_for_citizen(
    holoverse_root: Path | str | None,
    cid: str,
    citizen: dict[str, Any],
    node_index: dict[str, Any] | None = None,
) -> tuple[float, float, dict[str, Any]]:
    placement = safe_outdoor_grid_for_citizen(holoverse_root, cid, citizen, node_index)
    x, y = grid_to_city_xy(holoverse_root, str(placement.get("town_id") or "central_core_civic_ring"), placement.get("grid", (4.0, 3.0)))
    return float(x), float(y), placement


def validate_visible_citizens_off_buildings(
    holoverse_root: Path | str | None,
    citizens: dict[str, Any],
    node_index: dict[str, Any] | None = None,
) -> list[str]:
    errors: list[str] = []
    for cid, citizen in sorted(citizens.items()):
        if not isinstance(citizen, dict):
            continue
        mode = str(citizen.get("location_mode") or "")
        if mode == "private_home_hidden":
            continue
        placement = safe_outdoor_grid_for_citizen(holoverse_root, str(cid), citizen, node_index)
        town_id = str(placement.get("town_id") or citizen.get("town_id") or "")
        town = load_town(holoverse_root, town_id)
        if is_grid_on_building(town, placement.get("grid", (0.0, 0.0))):
            errors.append(f"{cid} resolved onto building footprint in {town_id}: {placement}")
    return errors
