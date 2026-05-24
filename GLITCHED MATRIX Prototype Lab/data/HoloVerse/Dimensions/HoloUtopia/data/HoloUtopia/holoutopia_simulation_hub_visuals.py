"""Collisionless Simulation Hub activity props for HoloUtopia.

Pass 39C makes the central Simulation Hub read like a purposeful activity
space instead of only a crowd of small citizens.  The props are simple Panda3D
line-models, authored from data/database/utopia/simulation so future passes can
replace them with real models without changing population logic.

Pass 44 keeps these props deliberately low so the raised Central Core hub
remains the visual anchor from atlas/world-view cameras.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

CLUSTERS_REL = Path("database/utopia/simulation/simulation_hub_activity_clusters.json")


def _data_root_from_holoutopia(holoutopia_root: Path | str | None = None) -> Path:
    root = Path(holoutopia_root or Path(__file__).resolve().parent).resolve()
    return root.parent if root.name.lower() in {"holoverse", "holoutopia"} else root


def load_simulation_hub_activity_clusters(holoutopia_root: Path | str | None = None) -> dict[str, Any]:
    data_root = _data_root_from_holoutopia(holoutopia_root)
    try:
        data = json.loads((data_root / CLUSTERS_REL).read_text(encoding="utf-8"))
    except Exception:
        return {"schema": 1, "town_id": "central_core_civic_ring", "clusters": []}
    return data if isinstance(data, dict) else {"schema": 1, "town_id": "central_core_civic_ring", "clusters": []}


def _accent(value: Any, fallback: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    if isinstance(value, list) and len(value) >= 4:
        try:
            return tuple(max(0.0, min(1.0, float(v))) for v in value[:4])  # type: ignore[return-value]
        except Exception:
            return fallback
    return fallback


def _node_xy(holoutopia_root: Path | str | None, node_index: dict[str, Any], node_id: str, town_id: str) -> tuple[float, float] | None:
    try:
        from holoutopia_pathfinding import grid_to_city_xy

        node = node_index.get(str(node_id)) if isinstance(node_index, dict) else None
        if node is None:
            return None
        ntown = str(getattr(node, "town_id", town_id) or town_id)
        return grid_to_city_xy(holoutopia_root, ntown, getattr(node, "grid", (4.0, 3.0)))
    except Exception:
        return None


def _line_box(seg: Any, x0: float, y0: float, z0: float, x1: float, y1: float, z1: float) -> None:
    corners = [
        (x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
        (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1),
    ]
    edges = ((0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4), (0, 4), (1, 5), (2, 6), (3, 7))
    for a, b in edges:
        seg.moveTo(*corners[a])
        seg.drawTo(*corners[b])


def _draw_hex_pad(seg: Any, radius: float, z: float) -> None:
    points = []
    for idx in range(6):
        a = math.tau * (idx / 6.0) + math.pi / 6.0
        points.append((math.cos(a) * radius, math.sin(a) * radius, z))
    for idx, point in enumerate(points):
        if idx == 0:
            seg.moveTo(*point)
        else:
            seg.drawTo(*point)
    seg.drawTo(*points[0])


def _draw_pod(seg: Any, style: str, color: tuple[float, float, float, float]) -> None:
    """Draw compact non-collision activity prop geometry in local cluster space."""
    # All props stay low and readable from street-level screenshots; no citizen rings.
    _draw_hex_pad(seg, 3.4, 0.12)
    if style == "live_model_console":
        _line_box(seg, -2.2, -1.2, 0.16, 2.2, 1.2, 1.45)
        for x in (-2.0, 0.0, 2.0):
            seg.moveTo(x, -2.1, 3.8)
            seg.drawTo(x, -2.4, 2.55)
    elif style == "briefing_steps":
        for i in range(3):
            z = 0.14 + i * 0.38
            w = 3.2 - i * 0.55
            d = 2.4 - i * 0.35
            _line_box(seg, -w, -d, z, w, d, z + 0.35)
        seg.moveTo(0.0, 0.0, 2.9)
        seg.drawTo(0.0, 0.0, 3.4)
    elif style == "matrixcore_reader":
        _line_box(seg, -1.8, -1.2, 0.16, 1.8, 1.2, 2.35)
        seg.moveTo(-2.4, 1.7, 1.15)
        seg.drawTo(2.4, 1.7, 1.15)
        seg.moveTo(-2.4, 1.7, 2.00)
        seg.drawTo(2.4, 1.7, 2.00)
    elif style == "social_sync_plinth" or style == "cooldown_plinth":
        _line_box(seg, -1.9, -1.9, 0.16, 1.9, 1.9, 1.25)
        for spoke in range(4):
            a = math.tau * spoke / 4.0
            seg.moveTo(0.0, 0.0, 2.4)
            seg.drawTo(math.cos(a) * 2.8, math.sin(a) * 2.8, 2.05)
    elif style == "arrival_gate":
        _line_box(seg, -3.0, -0.55, 0.16, -2.45, 0.55, 4.2)
        _line_box(seg, 2.45, -0.55, 0.16, 3.0, 0.55, 4.2)
        seg.moveTo(-3.0, 0.0, 4.2)
        seg.drawTo(3.0, 0.0, 4.2)
        seg.moveTo(-2.45, 0.0, 3.35)
        seg.drawTo(2.45, 0.0, 3.35)
    else:
        _line_box(seg, -2.1, -1.25, 0.16, 2.1, 1.25, 2.35)
        seg.moveTo(0.0, 0.0, 5.8)
        seg.drawTo(0.0, 0.0, 3.55)


def attach_simulation_hub_activity_visuals(parent: Any, holoutopia_root: Path | str | None, node_index: dict[str, Any]) -> Any | None:
    """Attach Simulation Hub activity props under the integrated city root."""
    try:
        from panda3d.core import LineSegs
    except Exception:
        return None
    data = load_simulation_hub_activity_clusters(holoutopia_root)
    town_id = str(data.get("town_id") or "central_core_civic_ring")
    clusters = data.get("clusters") if isinstance(data.get("clusters"), list) else []
    root = parent.attachNewNode("holoutopia_simulation_hub_activity_props")
    root.setPythonTag("holoutopia_activity_cluster_props", True)
    root.setPythonTag("holoutopia_activity_cluster_count", len(clusters))
    root.setLightOff(True)
    root.setTransparency(True)
    attached = 0
    for idx, cluster in enumerate(clusters):
        if not isinstance(cluster, dict):
            continue
        node_id = str(cluster.get("node_id") or "")
        xy = _node_xy(holoutopia_root, node_index, node_id, town_id)
        if xy is None:
            continue
        color = _accent(cluster.get("accent"), (0.62, 0.38, 1.0, 0.92))
        cluster_node = root.attachNewNode(f"simhub_cluster_{cluster.get('cluster_id') or idx}")
        cluster_node.setPos(float(xy[0]), float(xy[1]), 0.42)
        cluster_node.setLightOff(True)
        cluster_node.setTransparency(True)
        cluster_node.setPythonTag("holoutopia_activity_cluster_id", str(cluster.get("cluster_id") or idx))
        cluster_node.setPythonTag("holoutopia_activity_node_id", node_id)
        cluster_node.setPythonTag("holoutopia_activity_family", str(cluster.get("activity_family") or "activity"))
        prop_offsets = cluster.get("prop_offsets") if isinstance(cluster.get("prop_offsets"), list) else [[0.0, 0.0]]
        for pidx, offset in enumerate(prop_offsets):
            try:
                ox = float(offset[0]) * 64.0
                oy = -float(offset[1]) * 64.0
            except Exception:
                ox = oy = 0.0
            seg = LineSegs(f"{cluster.get('cluster_id') or idx}_prop_{pidx}")
            seg.setThickness(1.18)
            seg.setColor(*color)
            _draw_pod(seg, str(cluster.get("style") or "simulation_pod"), color)
            prop = cluster_node.attachNewNode(seg.create())
            prop.setPos(ox, oy, 0.0)
            prop.setLightOff(True)
            prop.setPythonTag("holoutopia_activity_prop", True)
        # Small vertical beacon ticks help the player understand these are activity points,
        # but they are not citizen selection rings and they carry no collision.
        beacon = LineSegs(f"{cluster.get('cluster_id') or idx}_beacon")
        beacon.setThickness(0.85)
        beacon.setColor(min(1.0, color[0] + 0.2), min(1.0, color[1] + 0.2), min(1.0, color[2] + 0.2), min(0.55, color[3]))
        beacon.moveTo(0.0, 0.0, 1.4)
        beacon.drawTo(0.0, 0.0, 6.5)
        beacon.moveTo(-1.1, 0.0, 5.2)
        beacon.drawTo(1.1, 0.0, 5.2)
        beacon.moveTo(0.0, -1.1, 5.2)
        beacon.drawTo(0.0, 1.1, 5.2)
        bnode = cluster_node.attachNewNode(beacon.create())
        bnode.setLightOff(True)
        bnode.setPythonTag("holoutopia_activity_beacon", True)
        attached += 1
    root.setPythonTag("holoutopia_activity_clusters_attached", attached)
    return root


def validate_simulation_activity_clusters(holoutopia_root: Path | str | None, node_index: dict[str, Any]) -> list[str]:
    """Pure validation: every cluster targets a real node and has standing slots."""
    data = load_simulation_hub_activity_clusters(holoutopia_root)
    errors: list[str] = []
    if data.get("town_id") != "central_core_civic_ring":
        errors.append("simulation activity clusters must target central_core_civic_ring")
    clusters = data.get("clusters") if isinstance(data.get("clusters"), list) else []
    if len(clusters) < 6:
        errors.append("expected at least 6 Simulation Hub activity clusters")
    seen: set[str] = set()
    for cluster in clusters:
        if not isinstance(cluster, dict):
            errors.append("cluster entry is not an object")
            continue
        cid = str(cluster.get("cluster_id") or "")
        if not cid:
            errors.append("cluster missing cluster_id")
        if cid in seen:
            errors.append(f"duplicate cluster_id: {cid}")
        seen.add(cid)
        node_id = str(cluster.get("node_id") or "")
        if node_id not in node_index:
            errors.append(f"cluster {cid} points to missing node {node_id}")
        slots = cluster.get("slot_offsets") if isinstance(cluster.get("slot_offsets"), list) else []
        if len(slots) < 4:
            errors.append(f"cluster {cid} needs at least 4 standing slots")
    return errors
