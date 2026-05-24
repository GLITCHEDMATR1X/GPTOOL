"""Watch Mode focus targets for HoloUtopia.

Pass 41 keeps Watch Mode read-only while adding Director-style focus targets:
- follow one representative citizen;
- frame one Simulation Hub activity cluster;
- keep join mode inactive until a later controls pass.

The module is pure-Python until optional Panda3D guide drawing is requested.
It never writes authored data and never changes HoloVerse/artifact routing.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any
import json
import math

FOCUS_RULES_REL = Path("database/utopia/simulation/watch_focus_rules.json")

_DEFAULT_FOCUS_RULES: dict[str, Any] = {
    "schema": 1,
    "id": "holoutopia_watch_focus_rules_v1",
    "runtime_writes_allowed": False,
    "mode": "watch_over_city_focus_prep",
    "join_mode_active": False,
    "focus_modes": ["follow_citizen", "activity_cluster", "director_overview"],
    "priorities": {
        "departure": ["commute_flow", "arrival_gate_cluster", "residential_departure"],
        "work": ["east_live_model_cluster", "north_pod_cluster", "south_pod_cluster", "arrival_gate_cluster"],
        "activity": ["matrixcore_reader_cluster", "west_social_sync_cluster", "forum_briefing_cluster", "evening_cooldown_cluster"],
        "return": ["commute_flow", "simulation_departure", "residential_return"]
    },
    "visual_guides": {
        "enabled": True,
        "citizen_focus_brackets": True,
        "cluster_focus_beacon": True,
        "no_citizen_rings": True,
        "no_name_labels": True,
        "collisionless": True
    }
}


def data_root_from_holoutopia(holoutopia_root: Path | str | None = None) -> Path:
    root = Path(holoutopia_root or Path(__file__).resolve().parent).resolve()
    return root.parent if root.name.lower() in {"holoverse", "holoutopia"} else root


def _read_json(path: Path, fallback: dict[str, Any]) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return json.loads(json.dumps(fallback))
    return data if isinstance(data, dict) else json.loads(json.dumps(fallback))


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = json.loads(json.dumps(base))
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_watch_focus_rules(holoutopia_root: Path | str | None = None) -> dict[str, Any]:
    data_root = data_root_from_holoutopia(holoutopia_root)
    return _deep_merge(_DEFAULT_FOCUS_RULES, _read_json(data_root / FOCUS_RULES_REL, _DEFAULT_FOCUS_RULES))


def _visible_people_from_frame(frame: dict[str, Any]) -> dict[str, dict[str, Any]]:
    pop = frame.get("residential_population_model") if isinstance(frame.get("residential_population_model"), dict) else {}
    residential = pop.get("visible_outdoor_citizens") if isinstance(pop.get("visible_outdoor_citizens"), dict) else {}
    activity = pop.get("visible_activity_citizens") if isinstance(pop.get("visible_activity_citizens"), dict) else {}
    people: dict[str, dict[str, Any]] = {}
    for source in (residential, activity):
        for cid, citizen in source.items():
            if isinstance(citizen, dict):
                people[str(cid)] = dict(citizen)
    return people


def _resolve_node_index(holoutopia_root: Path | str | None) -> dict[str, Any]:
    try:
        from holoutopia_citizen_simulation import build_node_index, load_simulation_inputs
        return build_node_index(load_simulation_inputs(holoutopia_root))
    except Exception:
        return {}


def _safe_xy_for_citizen(holoutopia_root: Path | str | None, cid: str, citizen: dict[str, Any], node_index: dict[str, Any]) -> tuple[float, float, dict[str, Any]]:
    try:
        from holoutopia_pathfinding import safe_outdoor_xy_for_citizen
        x, y, placement = safe_outdoor_xy_for_citizen(holoutopia_root, cid, citizen, node_index)
        if isinstance(placement, dict):
            return float(x), float(y), placement
    except Exception:
        pass
    # Conservative fallback that keeps focus guides grounded even if the full
    # street-safe resolver is unavailable.
    placement = citizen.get("pathfinding") if isinstance(citizen.get("pathfinding"), dict) else {}
    try:
        grid = placement.get("grid") if isinstance(placement.get("grid"), (list, tuple)) else citizen.get("grid")
        town_id = str(placement.get("town_id") or citizen.get("town_id") or "central_core_civic_ring")
        if isinstance(grid, (list, tuple)) and len(grid) >= 2:
            from holoutopia_pathfinding import grid_to_city_xy
            x, y = grid_to_city_xy(holoutopia_root, town_id, (float(grid[0]), float(grid[1])))
            return float(x), float(y), {"town_id": town_id, "grid": [float(grid[0]), float(grid[1])], "source": "focus_grid_fallback", "on_building": False}
    except Exception:
        pass
    return 0.0, 0.0, {"source": "focus_origin_fallback", "on_building": False}


def _phase_bucket(phase: str) -> str:
    raw = str(phase or "").lower()
    if "depart" in raw:
        return "departure"
    if "return" in raw:
        return "return"
    if "work" in raw:
        return "work"
    if "activity" in raw or "replenish" in raw:
        return "activity"
    return "overview"


def _cluster_label(value: str) -> str:
    raw = str(value or "unassigned").strip().lower()
    labels = {
        "arrival_gate_cluster": "Arrival Gate",
        "north_pod_cluster": "North Simulation Pods",
        "south_pod_cluster": "South Simulation Pods",
        "east_live_model_cluster": "Live Model Consoles",
        "west_social_sync_cluster": "Social Sync Plinths",
        "forum_briefing_cluster": "Briefing Forum",
        "matrixcore_reader_cluster": "MatrixCore Reader Nook",
        "reader_lore_cluster": "MatrixCore Reader Nook",
        "evening_cooldown_cluster": "Cooldown Ring",
        "residential_departure": "Residential Departure Route",
        "simulation_departure": "Simulation Departure Route",
        "interdistrict_outbound": "Outbound Commute Route",
        "interdistrict_return": "Return Commute Route",
        "residential_return": "Residential Return Route",
    }
    if raw in labels:
        return labels[raw]
    cleaned = raw.replace("_cluster", "").replace("_", " ").strip()
    return cleaned.title() if cleaned else "Unassigned"


def _activity_label(citizen: dict[str, Any]) -> str:
    label = str(citizen.get("activity_status") or citizen.get("label") or "").strip()
    if label:
        return label[:72]
    raw = str(citizen.get("activity_id") or citizen.get("personal_phase") or citizen.get("commute_stage") or "observing city").replace("_", " ")
    return raw.title()


def _score_citizen(cid: str, citizen: dict[str, Any], bucket: str, priorities: dict[str, Any]) -> tuple[int, int, str]:
    cluster = str(citizen.get("activity_cluster_id") or citizen.get("commute_stage") or "")
    phase = str(citizen.get("personal_phase") or citizen.get("activity_stage") or "")
    pose = str(citizen.get("activity_pose") or "")
    pref = priorities.get(bucket, []) if isinstance(priorities.get(bucket), list) else []
    score = 0
    if bool(citizen.get("commute_flow_representative")):
        score += 35 if bucket in {"departure", "return"} else 5
    if bool(citizen.get("district_activity_representative")):
        score += 25
    if cluster in pref:
        score += 30 - min(20, pref.index(cluster) * 4)
    if "commute" in pref and bool(citizen.get("commute_flow_representative")):
        score += 24
    if pose and pose != "idle_activity":
        score += 8
    if phase:
        score += 4
    try:
        schedule_index = int(citizen.get("schedule_index", 0) or 0)
    except Exception:
        schedule_index = 0
    # Negative score for sort descending; schedule_index keeps target stable but
    # avoids always choosing slot 0 when similar citizens exist.
    return (-score, schedule_index % 7, str(cid))


def _choose_focus_citizen(people: dict[str, dict[str, Any]], bucket: str, priorities: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    if not people:
        return "", {}
    ordered = sorted(people.items(), key=lambda item: _score_citizen(item[0], item[1], bucket, priorities))
    cid, citizen = ordered[0]
    return str(cid), dict(citizen)


def _choose_focus_cluster(people: dict[str, dict[str, Any]], focus_citizen: dict[str, Any]) -> dict[str, Any]:
    clusters: Counter[str] = Counter()
    for citizen in people.values():
        if not isinstance(citizen, dict):
            continue
        cluster = str(citizen.get("activity_cluster_id") or citizen.get("commute_stage") or "unassigned")
        if cluster and cluster != "unassigned":
            clusters[cluster] += 1
    preferred = str(focus_citizen.get("activity_cluster_id") or focus_citizen.get("commute_stage") or "") if isinstance(focus_citizen, dict) else ""
    if preferred:
        count = clusters.get(preferred, 1)
        return {"id": preferred, "label": _cluster_label(preferred), "visible_count": int(count)}
    if clusters:
        cluster, count = clusters.most_common(1)[0]
        return {"id": cluster, "label": _cluster_label(cluster), "visible_count": int(count)}
    return {"id": "central_core_civic_ring", "label": "Central Simulation Hub", "visible_count": 0}


def _cluster_xy_from_focus(holoutopia_root: Path | str | None, cluster: dict[str, Any], focus_citizen: dict[str, Any], focus_xy: tuple[float, float]) -> tuple[float, float, dict[str, Any]]:
    # Use the street-safe focus slot as the cluster frame anchor.  Some authored
    # Simulation Hub nodes are attached to building/pad centers, but the camera
    # should frame the readable citizen activity on safe walkable surfaces.
    placement = focus_citizen.get("pathfinding") if isinstance(focus_citizen.get("pathfinding"), dict) else {}
    town_id = str(placement.get("town_id") or focus_citizen.get("town_id") or "central_core_civic_ring")
    return float(focus_xy[0]), float(focus_xy[1]), {"town_id": town_id, "source": "street_safe_focus_slot"}


def build_watch_focus_state(
    holoutopia_root: Path | str | None = None,
    clock: str = "18:15",
    *,
    frame: dict[str, Any] | None = None,
    node_index: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if frame is None:
        try:
            from holoutopia_citizen_simulation import simulate_city_at_time
            frame = simulate_city_at_time(holoutopia_root, clock)
        except Exception:
            frame = {"clock": clock}
    rules = load_watch_focus_rules(holoutopia_root)
    pop = frame.get("residential_population_model") if isinstance(frame.get("residential_population_model"), dict) else {}
    phase = str(pop.get("phase") or "unknown")
    bucket = _phase_bucket(phase)
    people = _visible_people_from_frame(frame)
    node_index = node_index if isinstance(node_index, dict) else _resolve_node_index(holoutopia_root)
    focus_cid, focus_citizen = _choose_focus_citizen(people, bucket, rules.get("priorities") if isinstance(rules.get("priorities"), dict) else {})
    if focus_citizen:
        fx, fy, placement = _safe_xy_for_citizen(holoutopia_root, focus_cid, focus_citizen, node_index)
        focus_citizen["pathfinding"] = placement
    else:
        fx, fy, placement = 0.0, 0.0, {"source": "no_visible_focus"}
    cluster = _choose_focus_cluster(people, focus_citizen)
    cx, cy, cluster_position = _cluster_xy_from_focus(holoutopia_root, cluster, focus_citizen, (fx, fy)) if focus_citizen else (0.0, 0.0, {"source": "none"})
    focus_label = _activity_label(focus_citizen) if focus_citizen else "No visible citizen selected"
    target_label = f"{_cluster_label(str(focus_citizen.get('activity_cluster_id') or focus_citizen.get('commute_stage') or cluster.get('id') or ''))}: {focus_label}" if focus_citizen else str(cluster.get("label"))
    visible_total = len(people)
    return {
        "schema": 1,
        "id": "holoutopia_watch_focus_state_v1",
        "clock": str(frame.get("clock") or clock),
        "mode": "watch_focus_prep",
        "watch_mode_active": True,
        "join_mode_active": False,
        "follow_mode_active": False,
        "phase": phase,
        "phase_bucket": bucket,
        "visible_total": visible_total,
        "focus_citizen": {
            "id": focus_cid,
            "representative_label": _representative_label(focus_cid, focus_citizen),
            "activity_label": focus_label,
            "activity_id": str(focus_citizen.get("activity_id") or ""),
            "pose": str(focus_citizen.get("activity_pose") or "default"),
            "motive": str(focus_citizen.get("motive") or "unknown"),
            "town_id": str(focus_citizen.get("town_id") or placement.get("town_id") or ""),
            "cluster_id": str(focus_citizen.get("activity_cluster_id") or focus_citizen.get("commute_stage") or ""),
            "x": round(float(fx), 3),
            "y": round(float(fy), 3),
            "z": 1.75,
            "street_safe": not bool(placement.get("on_building")),
            "placement_source": str(placement.get("source") or "unknown"),
        },
        "focus_cluster": {
            "id": str(cluster.get("id") or ""),
            "label": str(cluster.get("label") or "Central Simulation Hub"),
            "visible_count": int(cluster.get("visible_count") or 0),
            "x": round(float(cx), 3),
            "y": round(float(cy), 3),
            "z": 2.0,
            "position_source": str(cluster_position.get("source") or "unknown"),
        },
        "director_camera": {
            "preferred_view": "follow_citizen" if focus_cid else "watch_mode",
            "target_label": target_label,
            "safe_for_player_join_later": True,
            "read_only_now": True,
        },
        "safety": {
            "no_citizen_rings": True,
            "no_name_labels": True,
            "visible_focus_street_safe": not bool(placement.get("on_building")),
            "garrison_inside_buildings_is_virtual": True,
            "writes_authored_data": False,
            "touches_routes": False,
        },
    }


def _representative_label(cid: str, citizen: dict[str, Any]) -> str:
    if not cid:
        return "No representative"
    try:
        idx = int(citizen.get("schedule_index", 0) or 0) + 1
    except Exception:
        idx = 1
    role = str(citizen.get("personal_phase") or citizen.get("commute_stage") or citizen.get("activity_pose") or "citizen").replace("_", " ").title()
    return f"Representative {idx:02d} / {role}"


def format_focus_lines(focus: dict[str, Any], *, max_lines: int = 5) -> list[str]:
    citizen = focus.get("focus_citizen") if isinstance(focus.get("focus_citizen"), dict) else {}
    cluster = focus.get("focus_cluster") if isinstance(focus.get("focus_cluster"), dict) else {}
    camera = focus.get("director_camera") if isinstance(focus.get("director_camera"), dict) else {}
    lines = [
        "WATCH FOCUS PREP",
        f"Target: {citizen.get('representative_label', 'No representative')}",
        f"Action: {citizen.get('activity_label', 'observing city')}",
        f"Cluster: {cluster.get('label', 'Central Simulation Hub')} ({cluster.get('visible_count', 0)} visible)",
        f"Camera: {camera.get('preferred_view', 'watch_mode')} | join later, read-only now",
    ]
    return lines[: max(1, int(max_lines))]


def attach_watch_focus_guides(parent: Any, holoutopia_root: Path | str | None, frame: dict[str, Any], *, clock: str | None = None, node_index: dict[str, Any] | None = None) -> Any | None:
    """Attach non-circular focus guides for the current Watch Mode target."""
    try:
        from panda3d.core import LineSegs, TextNode
    except Exception:
        return None
    focus = build_watch_focus_state(holoutopia_root, clock or str(frame.get("clock") or "18:15"), frame=frame, node_index=node_index)
    root = parent.attachNewNode("holoutopia_watch_focus_guides")
    root.setPythonTag("holoutopia_watch_focus_state", focus)
    root.setPythonTag("holoutopia_watch_focus_guides", True)
    root.setLightOff(True)
    root.setTransparency(True)

    citizen = focus.get("focus_citizen") if isinstance(focus.get("focus_citizen"), dict) else {}
    cluster = focus.get("focus_cluster") if isinstance(focus.get("focus_cluster"), dict) else {}
    if citizen.get("id"):
        _draw_focus_brackets(root, float(citizen.get("x") or 0.0), float(citizen.get("y") or 0.0), float(citizen.get("z") or 1.75), color=(1.0, 0.88, 0.28, 0.92))
    if cluster.get("id"):
        _draw_cluster_beacon(root, float(cluster.get("x") or 0.0), float(cluster.get("y") or 0.0), float(cluster.get("z") or 2.0), color=(0.35, 1.0, 0.92, 0.72))

    lines = format_focus_lines(focus)
    panel = root.attachNewNode("holoutopia_watch_focus_label_root")
    # Small label sits near the Watch Mode panel, not over the citizen's head.
    panel.setPos(500.0, 260.0, 66.0)
    try:
        panel.setBillboardPointEye()
    except Exception:
        panel.setHpr(0.0, -57.0, 0.0)
    for idx, line in enumerate(lines):
        text = TextNode(f"holoutopia_focus_line_{idx:02d}")
        text.setAlign(TextNode.ALeft)
        text.setText(str(line))
        text.setTextColor(1.0, 0.90, 0.52, 0.94 if idx == 0 else 0.86)
        node = panel.attachNewNode(text)
        node.setScale(4.5 if idx else 5.4)
        node.setPos(-124.0, -0.25, 15.0 - idx * 10.5)
        node.setLightOff(True)
    return root


def _draw_focus_brackets(root: Any, x: float, y: float, z: float, *, color: tuple[float, float, float, float]) -> None:
    from panda3d.core import LineSegs
    seg = LineSegs("holoutopia_focus_citizen_brackets")
    seg.setThickness(1.65)
    seg.setColor(*color)
    # Four L-shaped corner brackets and a vertical tick.  This is intentionally
    # not a circle/ring around the citizen.
    half = 4.0
    high = z + 10.5
    low = z + 0.3
    corner = 1.8
    for sx in (-1.0, 1.0):
        for sy in (-1.0, 1.0):
            cx = x + sx * half
            cy = y + sy * half
            seg.moveTo(cx, cy, low)
            seg.drawTo(cx, cy, high)
            seg.moveTo(cx, cy, high)
            seg.drawTo(cx - sx * corner, cy, high)
            seg.moveTo(cx, cy, high)
            seg.drawTo(cx, cy - sy * corner, high)
    seg.moveTo(x, y, high + 0.4)
    seg.drawTo(x, y, high + 5.0)
    node = root.attachNewNode(seg.create())
    node.setLightOff(True)


def _draw_cluster_beacon(root: Any, x: float, y: float, z: float, *, color: tuple[float, float, float, float]) -> None:
    from panda3d.core import LineSegs
    seg = LineSegs("holoutopia_focus_cluster_beacon")
    seg.setThickness(1.35)
    seg.setColor(*color)
    # Diamond/chevron frame over the cluster, not attached to any citizen.
    radius = 12.0
    top = z + 24.0
    mid = z + 13.0
    pts = [(x, y + radius, mid), (x + radius, y, mid), (x, y - radius, mid), (x - radius, y, mid), (x, y + radius, mid)]
    seg.moveTo(*pts[0])
    for p in pts[1:]:
        seg.drawTo(*p)
    for p in pts[:4]:
        seg.moveTo(*p)
        seg.drawTo(x, y, top)
    seg.moveTo(x, y, z + 2.0)
    seg.drawTo(x, y, top)
    node = root.attachNewNode(seg.create())
    node.setLightOff(True)


def validate_watch_focus(holoutopia_root: Path | str | None = None) -> list[str]:
    errors: list[str] = []
    rules = load_watch_focus_rules(holoutopia_root)
    if bool(rules.get("join_mode_active")):
        errors.append("join_mode_active must stay false for Pass 41")
    for clock in ("06:45", "12:45", "18:15", "20:35"):
        state = build_watch_focus_state(holoutopia_root, clock)
        citizen = state.get("focus_citizen") if isinstance(state.get("focus_citizen"), dict) else {}
        cluster = state.get("focus_cluster") if isinstance(state.get("focus_cluster"), dict) else {}
        if not citizen.get("id"):
            errors.append(f"{clock}: no focus citizen selected")
        if bool(state.get("join_mode_active")):
            errors.append(f"{clock}: join mode became active")
        if not bool(citizen.get("street_safe")):
            errors.append(f"{clock}: focus citizen is not street safe")
        if not cluster.get("id"):
            errors.append(f"{clock}: no focus cluster selected")
    return errors
