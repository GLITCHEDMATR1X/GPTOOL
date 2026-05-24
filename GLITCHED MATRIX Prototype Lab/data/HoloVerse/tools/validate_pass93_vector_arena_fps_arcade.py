#!/usr/bin/env python3
"""Validate Pass 93 Vector Arena first-person arcade shooter contract."""
from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIM = ROOT / "Dimensions" / "Vector Arena"
INDEX = ROOT / "Dimensions" / "dimension_index.json"


def read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def j(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def literal_constant(source: str, name: str, default=None):
    try:
        tree = ast.parse(source)
    except Exception:
        return default
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    try:
                        return ast.literal_eval(node.value)
                    except Exception:
                        return default
    return default


def main() -> int:
    errors: list[str] = []
    adapter = read(DIM / "holoverse_native_adapter.py")
    manifest = j(DIM / "holoverse_mode_manifest.json")
    index = j(INDEX)
    dims = index.get("dimensions") if isinstance(index.get("dimensions"), dict) else {}
    route = dims.get("vector_arena") if isinstance(dims.get("vector_arena"), dict) else {}

    if route.get("launch_type") != "native_panda":
        errors.append("vector_arena route must remain native_panda")
    if "first_person" not in str(route.get("host_contract", "")):
        errors.append("dimension_index host_contract should identify first-person adapter")
    host_contract = str(manifest.get("host_contract", ""))
    if "vector_arena_native_adapter" not in host_contract or "fps" not in host_contract and "first_person" not in host_contract:
        errors.append("manifest host_contract must identify a Vector Arena first-person adapter")

    gameplay = manifest.get("gameplay_contract") if isinstance(manifest.get("gameplay_contract"), dict) else {}
    if gameplay.get("camera") != "first_person":
        errors.append("Vector Arena camera contract must be first_person")
    if gameplay.get("ship_or_dogfight_controls") is not False:
        errors.append("Vector Arena must explicitly reject ship/dogfight controls")
    if gameplay.get("vector_wars_style") is not False:
        errors.append("Vector Arena must explicitly not be Vector Wars style")

    enemy_cap = literal_constant(adapter, "ENEMY_CAP", 0)
    projectile_cap = literal_constant(adapter, "PROJECTILE_CAP", 0)
    impact_cap = literal_constant(adapter, "IMPACT_CAP", 0)
    if not (12 <= int(enemy_cap or 0) <= 24):
        errors.append(f"unexpected FPS enemy cap: {enemy_cap!r}")
    if not (32 <= int(projectile_cap or 0) <= 64):
        errors.append(f"unexpected FPS beam pool size: {projectile_cap!r}")
    if not (32 <= int(impact_cap or 0) <= 64):
        errors.append(f"unexpected FPS impact pool size: {impact_cap!r}")

    required_defs = [
        "_update_pointer_look",
        "_closest_target_in_reticle",
        "_fire_primary",
        "_fire_repulsor",
        "_build_walls_and_cover",
        "_build_reticle_and_hud",
        "_update_camera",
        "get_result",
    ]
    for name in required_defs:
        if f"def {name}" not in adapter:
            errors.append(f"adapter missing FPS method {name}")

    required_terms = [
        "FIRST-PERSON ARCADE SHOOTER",
        "EYE_HEIGHT",
        "setFov(78)",
        "self.camera.setHpr(self.player_yaw, self.player_pitch, 0)",
        "self.player_pos + Vec3(0, 0, EYE_HEIGHT)",
        "reticle_root",
        "weapon_root",
        "cover_blocks",
        "hitscan",
        "repulsor",
    ]
    for term in required_terms:
        if term not in adapter:
            errors.append(f"adapter missing first-person presentation marker: {term}")

    if "_player_node" in adapter or "player_node.setH" in adapter:
        errors.append("Vector Arena should not keep the old visible player ship/avatar node")
    if "122.0" in adapter and "cam_target" in adapter:
        errors.append("old chase-camera offset appears to remain")
    if "SAME-WINDOW DOGFIGHT" in adapter:
        errors.append("Vector Arena adapter still advertises dogfight mode")

    perf = manifest.get("performance_contract") if isinstance(manifest.get("performance_contract"), dict) else {}
    if perf.get("runtime_node_creation") != "pooled_only_after_enter":
        errors.append("performance contract must remain pooled_only_after_enter")
    if int(perf.get("enemy_cap", 0) or 0) != int(enemy_cap or -1):
        errors.append("manifest enemy cap must match adapter")
    if int(perf.get("projectile_pool", 0) or 0) != int(projectile_cap or -1):
        errors.append("manifest projectile pool must match adapter")

    report = {
        "schema": 1,
        "kind": "pass93_vector_arena_fps_arcade_validation",
        "ok": not errors,
        "errors": errors,
        "enemy_cap": enemy_cap,
        "projectile_cap": projectile_cap,
        "impact_cap": impact_cap,
        "host_contract": manifest.get("host_contract"),
        "camera": gameplay.get("camera"),
    }
    print(json.dumps(report, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
