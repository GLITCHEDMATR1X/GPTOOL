"""Dimension-local Urban Warzone arena blueprint.

Safe salvage layer for the former standalone Vector Arena concept.

This module stays data-only. It creates deterministic battlefield layouts that
Urban Warzone/runtime.py mounts into the live HoloVerse Urban biome. No ShowBase,
no separate window, no native adapter, no external process.

Pass: world-space battlefield v4

Design goal:
    Urban Warzone should be a region-owned battlefield, not a player-following
    encounter bubble. The runtime may ask for a center, but this blueprint snaps
    that center to a stable Urban district grid and then spreads anchors across
    a wide combat front. If the player walks around, the war does not teleport
    after them; they move through fixed districts, lanes, outposts, and fronts.

Runtime contract:
    The returned dict keeps the old keys runtime.py already consumes while adding
    explicit spawn/render/simulation policies and a deterministic wave planner.
    Runtime code can ask this module for fixed world-space spawn plans instead
    of inventing player-centered spawns.
"""
from __future__ import annotations

import json
import math
import random
from typing import Dict, Iterable, List, Sequence, Tuple

BLUEPRINT_SCHEMA = 4
BATTLEFIELD_GRID_SIZE = 2400.0

ROLE_STYLES: Dict[str, Dict[str, object]] = {
    "duelist": {"title": "DUELIST", "color": (1.00, 0.34, 0.16, 0.94), "torso": (2.05, 1.18, 3.20), "head": (1.55, 1.18, 1.10), "weapon_len": 2.45},
    "flanker": {"title": "FLANKER", "color": (1.00, 0.16, 0.92, 0.94), "torso": (1.72, 1.02, 2.85), "head": (1.28, 1.02, 0.96), "weapon_len": 2.15},
    "sniper": {"title": "SNIPER", "color": (0.32, 0.76, 1.00, 0.94), "torso": (1.66, 1.08, 3.45), "head": (1.18, 1.08, 1.34), "weapon_len": 3.60},
    "breaker": {"title": "BREAKER", "color": (1.00, 0.72, 0.10, 0.94), "torso": (2.55, 1.55, 3.35), "head": (1.70, 1.35, 1.08), "weapon_len": 1.55},
    "survivor": {"title": "SENTINEL", "color": (0.20, 1.00, 0.52, 0.94), "torso": (2.05, 1.30, 3.05), "head": (1.42, 1.18, 1.05), "weapon_len": 2.45},
    "hunter": {"title": "HUNTER", "color": (1.00, 0.92, 0.18, 0.94), "torso": (1.95, 1.16, 3.05), "head": (1.50, 1.04, 1.12), "weapon_len": 2.65},
    "acrobat": {"title": "ACROBAT", "color": (0.22, 1.00, 0.95, 0.94), "torso": (1.62, 0.96, 2.90), "head": (1.18, 0.98, 1.00), "weapon_len": 1.95},
}

POCKET_OFFSETS: Tuple[Tuple[float, float], ...] = (
    (-1180.0, -920.0), (1180.0, -900.0), (-1220.0, 900.0), (1210.0, 940.0),
    (0.0, -1320.0), (0.0, 1340.0), (-1450.0, -80.0), (1460.0, 80.0),
    (-760.0, -430.0), (760.0, -420.0), (-780.0, 450.0), (790.0, 470.0),
    (-360.0, 0.0), (370.0, 0.0), (0.0, -520.0), (0.0, 540.0),
)

FRONTLINE_ARCS: Tuple[Tuple[str, float, float, float], ...] = (
    ("north_front", 0.0, 1560.0, 180.0),
    ("south_front", 0.0, -1560.0, 0.0),
    ("west_front", -1660.0, 0.0, 90.0),
    ("east_front", 1660.0, 0.0, -90.0),
)

RENDER_POLICY = {
    "solid_priority": [
        "command_spine", "frontline_beacon", "mech_hangar", "drone_spire",
        "relay_core", "spawn_bunker", "gate", "watch_tower",
    ],
    "wireframe_priority": [
        "cover", "trench_line", "assault_lane", "perimeter_lane", "frontline_axis",
        "skyway_x", "skyway_y", "roof_platform",
    ],
    "effect_priority": [
        "artillery_site", "air_corridor", "capture_post", "bomb_site", "weapon_node",
    ],
    "max_full_sim_districts": 4,
    "max_visible_actor_budget": 54,
    "max_low_sim_districts": 20,
}

SPAWN_POLICY = {
    "source_of_truth": "spawn_anchors",
    "never_center_on_player": True,
    "allow_player_proximity_bonus": False,
    "visible_portal_required_for_near_player_spawn": True,
    "enemy_anchor_weights": {"tier1": 1.0, "tier2": 1.35, "tier3": 1.75},
    "far_district_mode": "low_sim_state_only",
    "despawn_policy": "store_state_do_not_teleport",
}

WAVE_PLAN_POLICY = {
    "full_sim_radius": 760.0,
    "near_sim_radius": 1550.0,
    "min_full_sim_districts": 3,
    "max_full_sim_districts": 4,
    "max_near_sim_districts": 8,
    "min_enemy_spawns": 8,
    "max_enemy_spawns": 18,
    "max_ally_spawns": 4,
    "spawn_source": "enemy_spawn_sources",
    "ally_source": "ally_spawn_sources",
    "uses_player_position_for_sim_priority_only": True,
    "never_moves_anchors": True,
}


def role_style(role: str) -> Dict[str, object]:
    return dict(ROLE_STYLES.get(str(role or "duelist").lower(), ROLE_STYLES["duelist"]))


def stable_battlefield_center(cx: float, cy: float) -> Tuple[float, float]:
    """Return a deterministic world-space anchor for the Urban battlefield."""
    try:
        gx = round(float(cx) / BATTLEFIELD_GRID_SIZE) * BATTLEFIELD_GRID_SIZE
        gy = round(float(cy) / BATTLEFIELD_GRID_SIZE) * BATTLEFIELD_GRID_SIZE
        return float(gx), float(gy)
    except Exception:
        return 0.0, 0.0


def _structure(kind: str, x: float, y: float, sx: float, sy: float, sz: float, z: float = 0.0, pocket: str = "", yaw: float = 0.0) -> Dict[str, object]:
    return {"type": kind, "x": x, "y": y, "sx": sx, "sy": sy, "sz": sz, "z": z, "pocket": pocket, "yaw": yaw}


def _lane(kind: str, ax: float, ay: float, bx: float, by: float, z: float = 0.6, width: float = 1.0, pocket: str = "") -> Dict[str, object]:
    return {"type": kind, "ax": ax, "ay": ay, "bx": bx, "by": by, "z": z, "width": width, "pocket": pocket}


def _anchor(x: float, y: float, role: str, pocket: str, *, kind: str = "mixed", faction: str = "enemy", weight: float = 1.0, tier: int = 1) -> Dict[str, object]:
    return {
        "x": x,
        "y": y,
        "z": 0.8,
        "kind": kind,
        "role": role,
        "pocket": pocket,
        "faction": faction,
        "weight": float(weight),
        "tier": int(tier),
        "world_space_locked": True,
    }


def _add_objective_cluster(capture_posts, bomb_sites, weapon_nodes, px: float, py: float, radius: float, pid: str, idx: int, outer: bool, rng: random.Random) -> None:
    capture_posts.append({"id": f"capture_{idx:02d}", "x": px, "y": py, "radius": min(48.0, max(32.0, radius * 0.32)), "pocket": pid})
    bomb_count = 3 if outer else 2
    for b in range(bomb_count):
        ba = (b / max(1, bomb_count)) * math.tau + idx * 0.39 + rng.uniform(-0.18, 0.18)
        bd = radius * (0.48 + b * 0.18)
        bomb_sites.append({"id": f"bomb_{idx:02d}_{b}", "x": px + math.cos(ba) * bd, "y": py + math.sin(ba) * bd, "radius": rng.uniform(38.0, 56.0), "pocket": pid})
    if idx % 2 == 0 or not outer:
        weapon = ("arc_lance" if idx % 4 == 0 else "mech_breaker" if idx % 4 == 2 else "pulse_rifle")
        wa = math.pi * 0.25 + idx * 0.37
        weapon_nodes.append({"id": f"weapon_{idx:02d}", "x": px + math.cos(wa) * radius * 0.44, "y": py + math.sin(wa) * radius * 0.44, "weapon": weapon, "pocket": pid})


def _district_state(pid: str, x: float, y: float, radius: float, pressure: str, outer: bool, role_bias: str) -> Dict[str, object]:
    return {
        "id": pid,
        "x": float(x),
        "y": float(y),
        "radius": float(radius),
        "pressure": str(pressure),
        "role_bias": str(role_bias),
        "outer": bool(outer),
        "sim_mode": "low_sim_until_near",
        "control": "contested",
        "threat": 0.78 if outer else 0.42,
        "reinforcement_ready": True,
        "last_resolved_wave": 0,
    }


def _kind_for_pressure(pressure: str, index: int) -> str:
    if pressure == "heavy" and index % 4 == 0:
        return "mech"
    if pressure == "air" and index % 3 == 0:
        return "drone"
    return "mixed"


def _weighted_anchor_view(anchors: Iterable[Dict[str, object]], faction: str = "enemy") -> List[Dict[str, object]]:
    out: List[Dict[str, object]] = []
    for index, anchor in enumerate(anchors):
        if str(anchor.get("faction") or "enemy") != faction:
            continue
        tier = int(anchor.get("tier") or 1)
        weight = float(anchor.get("weight") or 1.0)
        weight *= float(SPAWN_POLICY["enemy_anchor_weights"].get(f"tier{tier}", 1.0))
        item = dict(anchor)
        item["anchor_id"] = f"{faction}_{index:03d}_{item.get('pocket', 'unknown')}"
        item["spawn_weight"] = round(weight, 3)
        out.append(item)
    return out


def _distance_sq(ax: float, ay: float, bx: float, by: float) -> float:
    dx = float(ax) - float(bx)
    dy = float(ay) - float(by)
    return dx * dx + dy * dy


def _safe_float(value, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(fallback)


def generate_arena_blueprint(cx: float, cy: float, seed: int = 0) -> Dict[str, object]:
    cx, cy = stable_battlefield_center(cx, cy)
    rng = random.Random((int(seed) & 0xFFFFFFFF) ^ int(cx * 17.0) ^ int(cy * 31.0) ^ 0xA11CE)
    pockets: List[Dict[str, object]] = []
    structures: List[Dict[str, object]] = []
    anchors: List[Dict[str, object]] = []
    power_nodes: List[Dict[str, object]] = []
    capture_posts: List[Dict[str, object]] = []
    bomb_sites: List[Dict[str, object]] = []
    weapon_nodes: List[Dict[str, object]] = []
    lanes: List[Dict[str, object]] = []
    landmarks: List[Dict[str, object]] = []
    patrol_routes: List[Dict[str, object]] = []
    artillery_sites: List[Dict[str, object]] = []
    air_corridors: List[Dict[str, object]] = []
    sector_states: List[Dict[str, object]] = []
    roles = list(ROLE_STYLES.keys())

    for idx, (ox, oy) in enumerate(POCKET_OFFSETS):
        px = cx + ox + rng.uniform(-42.0, 42.0)
        py = cy + oy + rng.uniform(-42.0, 42.0)
        outer = idx < 12
        radius = rng.uniform(116.0, 172.0) if outer else rng.uniform(70.0, 98.0)
        pid = f"district_{idx:02d}"
        role_bias = roles[idx % len(roles)]
        pressure = "heavy" if outer and idx % 3 == 0 else "air" if outer and idx % 3 == 1 else "infantry"
        pockets.append({"id": pid, "x": px, "y": py, "radius": radius, "role_bias": role_bias, "outer": outer, "pressure": pressure, "world_space_locked": True})
        sector_states.append(_district_state(pid, px, py, radius, pressure, outer, role_bias))

        lanes.append(_lane("assault_lane", cx, cy, px, py, 0.52, 1.25, pid))
        if idx < len(POCKET_OFFSETS) - 1:
            next_ox, next_oy = POCKET_OFFSETS[(idx + 1) % len(POCKET_OFFSETS)]
            lanes.append(_lane("perimeter_lane", px, py, cx + next_ox, cy + next_oy, 0.48, 0.85, pid))

        tower_count = 3 if outer else 2
        for t in range(tower_count):
            a = (t / max(1, tower_count)) * math.tau + rng.uniform(-0.24, 0.24)
            tx = px + math.cos(a) * rng.uniform(42.0, radius * 0.86)
            ty = py + math.sin(a) * rng.uniform(42.0, radius * 0.86)
            structures.append(_structure("watch_tower", tx, ty, rng.uniform(12.0, 24.0), rng.uniform(12.0, 24.0), rng.uniform(36.0, 76.0), 0.0, pid))
            structures.append(_structure("roof_platform", tx, ty, rng.uniform(20.0, 38.0), rng.uniform(18.0, 36.0), 2.4, rng.uniform(24.0, 48.0), pid))
            if pressure == "air":
                power_nodes.append({"x": tx, "y": ty, "z": rng.uniform(18.0, 38.0), "pocket": pid, "role": "sniper", "node": "drone_relay"})

        if outer:
            structures.append(_structure("skyway_x", px, py, radius * 2.05, 7.0, 2.2, rng.uniform(14.0, 26.0), pid))
            structures.append(_structure("skyway_y", px, py, 7.0, radius * 2.05, 2.2, rng.uniform(16.0, 30.0), pid))

        _add_objective_cluster(capture_posts, bomb_sites, weapon_nodes, px, py, radius, pid, idx, outer, rng)

        if pressure == "heavy":
            structures.append(_structure("mech_hangar", px + rng.uniform(-24, 24), py + radius * 0.62, rng.uniform(52, 82), rng.uniform(30, 48), rng.uniform(15, 26), 0.0, pid))
            artillery_sites.append({"id": f"artillery_{idx:02d}", "x": px - radius * 0.55, "y": py + radius * 0.18, "radius": 58.0, "pocket": pid, "kind": "mech_mortar"})
        elif pressure == "air":
            structures.append(_structure("drone_spire", px + radius * 0.56, py + rng.uniform(-22, 22), rng.uniform(12, 18), rng.uniform(12, 18), rng.uniform(48, 90), 0.0, pid))
            air_corridors.append({"id": f"air_{idx:02d}", "ax": px - radius, "ay": py, "bx": px + radius, "by": py, "altitude": 48.0 + idx * 2.0, "pocket": pid})
        else:
            structures.append(_structure("relay_core", px, py, rng.uniform(14, 22), rng.uniform(14, 22), rng.uniform(20, 38), 0.0, pid))

        structures.append(_structure("relay_core", px, py, rng.uniform(12, 20), rng.uniform(12, 20), rng.uniform(18, 34), 0.0, pid))
        for g in range(3 if outer else 2):
            ga = (g / max(1, (3 if outer else 2))) * math.tau + rng.uniform(-0.10, 0.10)
            gx = px + math.cos(ga) * radius
            gy = py + math.sin(ga) * radius
            structures.append(_structure("gate", gx, gy, 24.0, 4.0, rng.uniform(20.0, 32.0), 0.0, pid, math.degrees(ga)))
            anchors.append(_anchor(gx + math.cos(ga) * 38.0, gy + math.sin(ga) * 38.0, roles[(idx + g) % len(roles)], pid, kind="mixed", faction="enemy", weight=1.25 if outer else 0.85, tier=2 if outer else 1))

        for _ in range(8 if outer else 5):
            a = rng.random() * math.tau
            d = rng.uniform(20.0, radius * 0.84)
            structures.append(_structure("cover", px + math.cos(a) * d, py + math.sin(a) * d, rng.uniform(6.0, 18.0), rng.uniform(5.0, 24.0), rng.uniform(2.0, 9.0), 0.0, pid))
        for _ in range(4 if outer else 2):
            a = rng.random() * math.tau
            d = rng.uniform(radius * 0.32, radius * 0.98)
            length = rng.uniform(58.0, 124.0)
            tx = px + math.cos(a) * d
            ty = py + math.sin(a) * d
            lanes.append(_lane("trench_line", tx - math.cos(a) * length * 0.5, ty - math.sin(a) * length * 0.5, tx + math.cos(a) * length * 0.5, ty + math.sin(a) * length * 0.5, 0.36, 1.4, pid))

        for _ in range(4 if outer else 2):
            a = rng.random() * math.tau
            d = rng.uniform(18.0, radius * 0.72)
            power_nodes.append({"x": px + math.cos(a) * d, "y": py + math.sin(a) * d, "z": rng.uniform(5.0, 18.0), "pocket": pid, "role": role_bias})

        anchor_count = 8 if outer else 4
        for s in range(anchor_count):
            a = (s / max(1, anchor_count)) * math.tau + rng.uniform(-0.20, 0.20)
            d = rng.uniform(radius * 0.35, radius * 1.10)
            role = roles[(idx + s) % len(roles)]
            kind = _kind_for_pressure(pressure, s)
            anchors.append(_anchor(px + math.cos(a) * d, py + math.sin(a) * d, role, pid, kind=kind, faction="enemy", weight=1.0 + (0.35 if outer else 0.0), tier=2 if outer else 1))

        patrol_routes.append({"id": f"patrol_{idx:02d}", "pocket": pid, "points": [(px - radius * 0.72, py - radius * 0.18), (px + radius * 0.42, py - radius * 0.64), (px + radius * 0.78, py + radius * 0.20), (px - radius * 0.28, py + radius * 0.70)], "kind": "drone" if pressure == "air" else "robot"})

    landmarks.append({"type": "command_spine", "x": cx, "y": cy, "sx": 48.0, "sy": 48.0, "sz": 86.0, "z": 0.0})
    landmarks.append({"type": "frontline_beacon", "x": cx - 116.0, "y": cy + 34.0, "sx": 16.0, "sy": 16.0, "sz": 54.0, "z": 0.0})
    landmarks.append({"type": "frontline_beacon", "x": cx + 120.0, "y": cy - 42.0, "sx": 16.0, "sy": 16.0, "sz": 54.0, "z": 0.0})
    for i, ang in enumerate((0.0, math.pi * 0.5, math.pi, math.pi * 1.5)):
        x = cx + math.cos(ang) * 180.0
        y = cy + math.sin(ang) * 180.0
        structures.append(_structure("spawn_bunker", x, y, 38.0, 24.0, 13.0, 0.0, f"central_{i}", math.degrees(ang)))
        anchors.append(_anchor(x + math.cos(ang) * 48.0, y + math.sin(ang) * 48.0, roles[i % len(roles)], f"central_{i}", kind="mixed", faction="enemy", weight=0.9, tier=1))
        anchors.append(_anchor(x - math.cos(ang) * 46.0, y - math.sin(ang) * 46.0, roles[(i + 3) % len(roles)], f"central_{i}", kind="mixed", faction="ally", weight=0.65, tier=1))
        if i % 2 == 0:
            capture_posts.append({"id": f"central_capture_{i}", "x": x, "y": y, "radius": 34.0, "pocket": f"central_{i}"})
        bomb_sites.append({"id": f"central_bomb_{i}", "x": x - math.sin(ang) * 38.0, "y": y + math.cos(ang) * 38.0, "radius": 46.0, "pocket": f"central_{i}"})

    for idx, (fid, ox, oy, yaw) in enumerate(FRONTLINE_ARCS):
        fx = cx + ox
        fy = cy + oy
        landmarks.append({"type": "frontline_beacon", "x": fx, "y": fy, "sx": 18.0, "sy": 18.0, "sz": 68.0, "z": 0.0, "pocket": fid, "yaw": yaw})
        structures.append(_structure("spawn_bunker", fx, fy, 56.0, 32.0, 18.0, 0.0, fid, yaw))
        capture_posts.append({"id": f"{fid}_capture", "x": fx, "y": fy, "radius": 52.0, "pocket": fid})
        for side in (-1, 1):
            sx = fx + math.cos(math.radians(yaw + side * 90.0)) * 92.0
            sy = fy + math.sin(math.radians(yaw + side * 90.0)) * 92.0
            anchors.append(_anchor(sx, sy, roles[(idx + side) % len(roles)], fid, kind="mixed", faction="enemy", weight=1.45, tier=3))
            structures.append(_structure("gate", sx, sy, 28.0, 4.0, 36.0, 0.0, fid, yaw))
        lanes.append(_lane("frontline_axis", cx, cy, fx, fy, 0.52, 1.65, fid))
        artillery_sites.append({"id": f"{fid}_artillery", "x": fx, "y": fy, "radius": 72.0, "pocket": fid, "kind": "sector_battery"})

    enemy_spawn_sources = _weighted_anchor_view(anchors, "enemy")
    ally_spawn_sources = _weighted_anchor_view(anchors, "ally")
    summary = {"districts": len(pockets), "enemy_spawn_sources": len(enemy_spawn_sources), "ally_spawn_sources": len(ally_spawn_sources), "structures": len(structures), "objectives": len(capture_posts) + len(bomb_sites), "patrol_routes": len(patrol_routes), "artillery_sites": len(artillery_sites), "air_corridors": len(air_corridors)}

    blueprint = {
        "schema": BLUEPRINT_SCHEMA,
        "kind": "urban_world_space_battlefield_blueprint",
        "world_space_locked": True,
        "center": {"x": cx, "y": cy, "grid_size": BATTLEFIELD_GRID_SIZE},
        "spawn_policy": dict(SPAWN_POLICY),
        "render_policy": dict(RENDER_POLICY),
        "wave_plan_policy": dict(WAVE_PLAN_POLICY),
        "summary": summary,
        "pockets": pockets,
        "districts": pockets,
        "sector_states": sector_states,
        "structures": structures,
        "spawn_anchors": anchors,
        "enemy_spawn_sources": enemy_spawn_sources,
        "ally_spawn_sources": ally_spawn_sources,
        "power_nodes": power_nodes,
        "capture_posts": capture_posts,
        "bomb_sites": bomb_sites,
        "weapon_nodes": weapon_nodes,
        "lanes": lanes,
        "landmarks": landmarks,
        "patrol_routes": patrol_routes,
        "artillery_sites": artillery_sites,
        "air_corridors": air_corridors,
        "notes": "World-space locked Urban battlefield. Anchors are fixed districts/fronts so action belongs to Urban instead of following the player.",
    }
    validate_blueprint(blueprint)
    return blueprint


def rank_districts_for_player(blueprint: Dict[str, object], player_x: float | None = None, player_y: float | None = None) -> List[Dict[str, object]]:
    """Rank districts for simulation priority without moving the battlefield.

    Player position is used only to decide which fixed districts should run in
    full simulation. Spawn anchors remain at their world-space coordinates.
    """
    validate_blueprint(blueprint)
    center = dict(blueprint.get("center") or {})
    px = _safe_float(player_x, _safe_float(center.get("x"), 0.0))
    py = _safe_float(player_y, _safe_float(center.get("y"), 0.0))
    ranked: List[Dict[str, object]] = []
    for district in list(blueprint.get("sector_states") or blueprint.get("pockets") or []):
        item = dict(district)
        dx = _safe_float(item.get("x"), 0.0)
        dy = _safe_float(item.get("y"), 0.0)
        dist = math.sqrt(_distance_sq(px, py, dx, dy))
        item["distance_to_player"] = round(dist, 3)
        if dist <= float(WAVE_PLAN_POLICY["full_sim_radius"]):
            item["sim_mode"] = "full_sim"
        elif dist <= float(WAVE_PLAN_POLICY["near_sim_radius"]):
            item["sim_mode"] = "near_low_sim"
        else:
            item["sim_mode"] = "far_low_sim"
        ranked.append(item)
    ranked.sort(key=lambda d: (float(d.get("distance_to_player") or 0.0), -float(d.get("threat") or 0.0), str(d.get("id") or "")))
    return ranked


def _weighted_pick(rng: random.Random, candidates: Sequence[Dict[str, object]], count: int) -> List[Dict[str, object]]:
    pool = [dict(item) for item in candidates]
    chosen: List[Dict[str, object]] = []
    count = max(0, min(int(count), len(pool)))
    for _ in range(count):
        total = sum(max(0.01, float(item.get("spawn_weight") or item.get("weight") or 1.0)) for item in pool)
        roll = rng.random() * total
        acc = 0.0
        pick_index = 0
        for idx, item in enumerate(pool):
            acc += max(0.01, float(item.get("spawn_weight") or item.get("weight") or 1.0))
            if acc >= roll:
                pick_index = idx
                break
        chosen.append(pool.pop(pick_index))
    return chosen


def build_wave_plan(
    blueprint: Dict[str, object],
    wave: int = 1,
    player_x: float | None = None,
    player_y: float | None = None,
    seed: int = 0,
    max_enemy_spawns: int | None = None,
) -> Dict[str, object]:
    """Build a deterministic fixed-anchor wave plan for runtime.py.

    This is the key anti-teleport helper. The player's location only selects
    which existing districts wake up; all spawn points come from fixed
    `enemy_spawn_sources` / `ally_spawn_sources` in the blueprint.
    """
    validate_blueprint(blueprint)
    wave = max(1, int(wave or 1))
    center = dict(blueprint.get("center") or {})
    ranked = rank_districts_for_player(blueprint, player_x, player_y)
    max_full = int(WAVE_PLAN_POLICY["max_full_sim_districts"])
    min_full = int(WAVE_PLAN_POLICY["min_full_sim_districts"])
    max_near = int(WAVE_PLAN_POLICY["max_near_sim_districts"])
    full_districts = [d for d in ranked if d.get("sim_mode") == "full_sim"][:max_full]
    if len(full_districts) < min_full:
        seen = {str(d.get("id")) for d in full_districts}
        for district in ranked:
            if str(district.get("id")) not in seen:
                item = dict(district)
                item["sim_mode"] = "full_sim"
                full_districts.append(item)
                seen.add(str(item.get("id")))
            if len(full_districts) >= min_full:
                break
    near_districts = [d for d in ranked if d.get("sim_mode") in {"full_sim", "near_low_sim"}][:max_near]
    active_ids = {str(d.get("id")) for d in near_districts}
    if not active_ids:
        active_ids = {str(d.get("id")) for d in ranked[:max_near]}

    enemy_sources = [dict(src) for src in list(blueprint.get("enemy_spawn_sources") or []) if str(src.get("pocket")) in active_ids]
    if len(enemy_sources) < int(WAVE_PLAN_POLICY["min_enemy_spawns"]):
        enemy_sources = [dict(src) for src in list(blueprint.get("enemy_spawn_sources") or [])]
    enemy_count = max(int(WAVE_PLAN_POLICY["min_enemy_spawns"]), min(int(WAVE_PLAN_POLICY["max_enemy_spawns"]), 7 + wave * 2))
    if max_enemy_spawns is not None:
        enemy_count = min(enemy_count, int(max_enemy_spawns))

    rng = random.Random((int(seed) & 0xFFFFFFFF) ^ (wave * 7919) ^ int(_safe_float(center.get("x"), 0.0)) ^ int(_safe_float(center.get("y"), 0.0)))
    chosen_enemies = _weighted_pick(rng, enemy_sources, enemy_count)
    ally_sources = _weighted_pick(rng, list(blueprint.get("ally_spawn_sources") or []), min(int(WAVE_PLAN_POLICY["max_ally_spawns"]), max(1, wave // 3 + 1)))

    artillery = [dict(site) for site in list(blueprint.get("artillery_sites") or []) if str(site.get("pocket")) in active_ids]
    air = [dict(corridor) for corridor in list(blueprint.get("air_corridors") or []) if str(corridor.get("pocket")) in active_ids]
    patrols = [dict(route) for route in list(blueprint.get("patrol_routes") or []) if str(route.get("pocket")) in active_ids]

    plan = {
        "schema": 1,
        "kind": "urban_world_space_wave_plan",
        "wave": wave,
        "world_space_locked": True,
        "never_center_on_player": True,
        "player_used_for_sim_priority_only": True,
        "active_district_ids": sorted(active_ids),
        "full_sim_districts": full_districts,
        "near_districts": near_districts,
        "enemy_spawns": chosen_enemies,
        "ally_spawns": ally_sources,
        "patrol_routes": patrols,
        "artillery_sites": artillery,
        "air_corridors": air,
        "notes": "Runtime should spawn from these fixed anchors. Do not recenter this plan on the player.",
    }
    validate_wave_plan(plan)
    return plan


def validate_wave_plan(plan: Dict[str, object]) -> None:
    if not plan.get("world_space_locked"):
        raise ValueError("urban wave plan must be world_space_locked")
    if not plan.get("never_center_on_player"):
        raise ValueError("urban wave plan must never center on player")
    if not plan.get("enemy_spawns"):
        raise ValueError("urban wave plan needs enemy_spawns")
    for item in list(plan.get("enemy_spawns") or []):
        if not item.get("world_space_locked"):
            raise ValueError("urban enemy spawn is missing world_space_locked")
        if "x" not in item or "y" not in item:
            raise ValueError("urban enemy spawn missing x/y")


def summarize_blueprint(blueprint: Dict[str, object]) -> Dict[str, int | bool]:
    return {
        "world_space_locked": bool(blueprint.get("world_space_locked")),
        "districts": len(blueprint.get("pockets") or []),
        "enemy_spawn_sources": len(blueprint.get("enemy_spawn_sources") or []),
        "ally_spawn_sources": len(blueprint.get("ally_spawn_sources") or []),
        "structures": len(blueprint.get("structures") or []),
        "capture_posts": len(blueprint.get("capture_posts") or []),
        "bomb_sites": len(blueprint.get("bomb_sites") or []),
        "patrol_routes": len(blueprint.get("patrol_routes") or []),
        "artillery_sites": len(blueprint.get("artillery_sites") or []),
        "air_corridors": len(blueprint.get("air_corridors") or []),
    }


def summarize_wave_plan(plan: Dict[str, object]) -> Dict[str, int | bool]:
    return {
        "world_space_locked": bool(plan.get("world_space_locked")),
        "never_center_on_player": bool(plan.get("never_center_on_player")),
        "active_districts": len(plan.get("active_district_ids") or []),
        "full_sim_districts": len(plan.get("full_sim_districts") or []),
        "enemy_spawns": len(plan.get("enemy_spawns") or []),
        "ally_spawns": len(plan.get("ally_spawns") or []),
        "patrol_routes": len(plan.get("patrol_routes") or []),
        "artillery_sites": len(plan.get("artillery_sites") or []),
        "air_corridors": len(plan.get("air_corridors") or []),
    }


def validate_blueprint(blueprint: Dict[str, object]) -> None:
    required = ("pockets", "structures", "spawn_anchors", "capture_posts", "bomb_sites", "lanes")
    missing = [key for key in required if key not in blueprint]
    if missing:
        raise ValueError(f"urban battlefield blueprint missing keys: {', '.join(missing)}")
    if not blueprint.get("world_space_locked"):
        raise ValueError("urban battlefield blueprint must be world_space_locked")
    if len(blueprint.get("pockets") or []) < 8:
        raise ValueError("urban battlefield needs multiple fixed districts")
    if len(blueprint.get("spawn_anchors") or []) < 24:
        raise ValueError("urban battlefield needs enough fixed spawn anchors")
    if not blueprint.get("enemy_spawn_sources"):
        raise ValueError("urban battlefield needs enemy spawn sources")


if __name__ == "__main__":
    demo = generate_arena_blueprint(127.5, -81.0, seed=7)
    plan = build_wave_plan(demo, wave=4, player_x=180.0, player_y=-120.0, seed=7)
    print(json.dumps({"blueprint": summarize_blueprint(demo), "wave_plan": summarize_wave_plan(plan)}, indent=2, sort_keys=True))
