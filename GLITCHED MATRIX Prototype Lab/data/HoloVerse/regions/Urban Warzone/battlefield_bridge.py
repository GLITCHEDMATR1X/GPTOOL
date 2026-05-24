"""Urban Warzone runtime bridge for world-space battlefield planning.

This module is intentionally small and data-oriented. It gives the very large
`runtime.py` one safe import target for the new world-space battlefield planner
without duplicating combat logic or creating a second runtime.

The bridge does three things:

1. Loads the existing `arena_blueprint.py` planner.
2. Builds a fixed-anchor wave plan using player position only for district
   simulation priority.
3. Converts the plan into simple spawn request dictionaries that runtime.py can
   consume without centering action on the player.

No Panda3D imports. No ShowBase. No window. No extra game loop.
"""
from __future__ import annotations

import importlib.util
import json
import math
from pathlib import Path
from typing import Dict, List, Tuple

BRIDGE_SCHEMA = 1
URBAN_WORLD_BATTLEFIELD_BRIDGE = True
NEVER_CENTER_ON_PLAYER = True

ROOT = Path(__file__).resolve().parent
BLUEPRINT_PATH = ROOT / "arena_blueprint.py"


def _load_blueprint_module():
    if not BLUEPRINT_PATH.exists():
        raise FileNotFoundError(f"Urban blueprint missing: {BLUEPRINT_PATH}")
    spec = importlib.util.spec_from_file_location("holoverse_urban_battlefield_blueprint", BLUEPRINT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not create Urban blueprint import spec")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _safe_float(value, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(fallback)


def _player_xy_from_app(app) -> Tuple[float, float]:
    """Best-effort player/camera xy extraction.

    The returned position is only passed to the planner for district priority.
    It must never be used as a spawn center.
    """
    for attr in ("player", "camera", "cam"):
        node = getattr(app, attr, None)
        if node is None:
            continue
        for getter in ("getPos", "get_pos"):
            fn = getattr(node, getter, None)
            if not callable(fn):
                continue
            try:
                pos = fn()
                return _safe_float(getattr(pos, "x", pos[0])), _safe_float(getattr(pos, "y", pos[1]))
            except Exception:
                pass
    for x_name, y_name in (("player_x", "player_y"), ("world_x", "world_y"), ("avatar_x", "avatar_y")):
        if hasattr(app, x_name) and hasattr(app, y_name):
            return _safe_float(getattr(app, x_name)), _safe_float(getattr(app, y_name))
    return 0.0, 0.0


def _battlefield_center_from_app(app, player_x: float, player_y: float) -> Tuple[float, float]:
    """Best-effort stable center discovery.

    If the runtime does not expose a region center yet, this intentionally falls
    back to player coordinates because arena_blueprint.stable_battlefield_center
    snaps them to a stable grid. That prevents small player movement from moving
    the battlefield.
    """
    for name in ("urban_warzone_center", "urban_region_center", "current_region_center"):
        value = getattr(app, name, None)
        if isinstance(value, (tuple, list)) and len(value) >= 2:
            return _safe_float(value[0], player_x), _safe_float(value[1], player_y)
        if isinstance(value, dict):
            return _safe_float(value.get("x"), player_x), _safe_float(value.get("y"), player_y)
    for x_name, y_name in (("urban_center_x", "urban_center_y"), ("region_center_x", "region_center_y")):
        if hasattr(app, x_name) and hasattr(app, y_name):
            return _safe_float(getattr(app, x_name), player_x), _safe_float(getattr(app, y_name), player_y)
    return player_x, player_y


def build_runtime_wave_plan(app=None, *, wave: int = 1, seed: int = 0, center_x=None, center_y=None, player_x=None, player_y=None, max_enemy_spawns=None) -> Dict[str, object]:
    """Return a world-space wave plan ready for Urban runtime consumption."""
    bp = _load_blueprint_module()
    if player_x is None or player_y is None:
        if app is not None:
            player_x, player_y = _player_xy_from_app(app)
        else:
            player_x, player_y = 0.0, 0.0
    if center_x is None or center_y is None:
        if app is not None:
            center_x, center_y = _battlefield_center_from_app(app, _safe_float(player_x), _safe_float(player_y))
        else:
            center_x, center_y = _safe_float(player_x), _safe_float(player_y)
    blueprint = bp.generate_arena_blueprint(_safe_float(center_x), _safe_float(center_y), seed=int(seed or 0))
    plan = bp.build_wave_plan(
        blueprint,
        wave=int(wave or 1),
        player_x=_safe_float(player_x),
        player_y=_safe_float(player_y),
        seed=int(seed or 0),
        max_enemy_spawns=max_enemy_spawns,
    )
    bridge_plan = {
        "schema": BRIDGE_SCHEMA,
        "kind": "urban_runtime_wave_bridge_plan",
        "world_space_locked": True,
        "never_center_on_player": True,
        "blueprint": blueprint,
        "wave_plan": plan,
        "summary": {
            "blueprint": bp.summarize_blueprint(blueprint),
            "wave_plan": bp.summarize_wave_plan(plan),
        },
    }
    validate_runtime_bridge_plan(bridge_plan)
    return bridge_plan


def enemy_spawn_requests(bridge_plan: Dict[str, object]) -> List[Dict[str, object]]:
    """Convert fixed enemy anchors into simple runtime spawn requests."""
    plan = dict(bridge_plan.get("wave_plan") or bridge_plan or {})
    requests: List[Dict[str, object]] = []
    for idx, source in enumerate(list(plan.get("enemy_spawns") or [])):
        source = dict(source)
        requests.append({
            "id": source.get("anchor_id") or f"enemy_spawn_{idx:03d}",
            "x": _safe_float(source.get("x")),
            "y": _safe_float(source.get("y")),
            "z": _safe_float(source.get("z"), 0.8),
            "kind": str(source.get("kind") or "mixed"),
            "role": str(source.get("role") or "duelist"),
            "pocket": str(source.get("pocket") or "unknown"),
            "tier": int(source.get("tier") or 1),
            "spawn_weight": _safe_float(source.get("spawn_weight"), _safe_float(source.get("weight"), 1.0)),
            "world_space_locked": True,
            "spawn_reason": "urban_fixed_anchor_wave_plan",
        })
    return requests


def ally_spawn_requests(bridge_plan: Dict[str, object]) -> List[Dict[str, object]]:
    plan = dict(bridge_plan.get("wave_plan") or bridge_plan or {})
    requests: List[Dict[str, object]] = []
    for idx, source in enumerate(list(plan.get("ally_spawns") or [])):
        source = dict(source)
        requests.append({
            "id": source.get("anchor_id") or f"ally_spawn_{idx:03d}",
            "x": _safe_float(source.get("x")),
            "y": _safe_float(source.get("y")),
            "z": _safe_float(source.get("z"), 0.8),
            "kind": str(source.get("kind") or "mixed"),
            "role": str(source.get("role") or "sentinel"),
            "pocket": str(source.get("pocket") or "unknown"),
            "tier": int(source.get("tier") or 1),
            "world_space_locked": True,
            "spawn_reason": "urban_fixed_anchor_wave_plan",
        })
    return requests


def objective_requests(bridge_plan: Dict[str, object]) -> Dict[str, List[Dict[str, object]]]:
    blueprint = dict(bridge_plan.get("blueprint") or {})
    plan = dict(bridge_plan.get("wave_plan") or {})
    return {
        "capture_posts": [dict(item) for item in list(blueprint.get("capture_posts") or [])],
        "bomb_sites": [dict(item) for item in list(blueprint.get("bomb_sites") or [])],
        "weapon_nodes": [dict(item) for item in list(blueprint.get("weapon_nodes") or [])],
        "patrol_routes": [dict(item) for item in list(plan.get("patrol_routes") or [])],
        "artillery_sites": [dict(item) for item in list(plan.get("artillery_sites") or [])],
        "air_corridors": [dict(item) for item in list(plan.get("air_corridors") or [])],
    }


def validate_runtime_bridge_plan(bridge_plan: Dict[str, object]) -> None:
    if not bridge_plan.get("world_space_locked"):
        raise ValueError("Urban runtime bridge plan must be world_space_locked")
    if not bridge_plan.get("never_center_on_player"):
        raise ValueError("Urban runtime bridge plan must never center on player")
    enemies = enemy_spawn_requests(bridge_plan)
    if not enemies:
        raise ValueError("Urban runtime bridge plan produced no enemy spawn requests")
    for request in enemies:
        if not request.get("world_space_locked"):
            raise ValueError("Urban enemy request is not world_space_locked")
        if not math.isfinite(_safe_float(request.get("x"))) or not math.isfinite(_safe_float(request.get("y"))):
            raise ValueError("Urban enemy request has invalid x/y")


def summarize_runtime_bridge_plan(bridge_plan: Dict[str, object]) -> Dict[str, int | bool]:
    objectives = objective_requests(bridge_plan)
    return {
        "world_space_locked": bool(bridge_plan.get("world_space_locked")),
        "never_center_on_player": bool(bridge_plan.get("never_center_on_player")),
        "enemy_spawn_requests": len(enemy_spawn_requests(bridge_plan)),
        "ally_spawn_requests": len(ally_spawn_requests(bridge_plan)),
        "patrol_routes": len(objectives.get("patrol_routes") or []),
        "artillery_sites": len(objectives.get("artillery_sites") or []),
        "air_corridors": len(objectives.get("air_corridors") or []),
        "capture_posts": len(objectives.get("capture_posts") or []),
        "bomb_sites": len(objectives.get("bomb_sites") or []),
    }


if __name__ == "__main__":
    demo = build_runtime_wave_plan(wave=4, seed=7, center_x=127.5, center_y=-81.0, player_x=180.0, player_y=-120.0)
    print(json.dumps(summarize_runtime_bridge_plan(demo), indent=2, sort_keys=True))
