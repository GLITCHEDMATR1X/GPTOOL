#!/usr/bin/env python3
"""Validate Pass 98 Vector Arena current-gen hardlight style contract."""
from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIM = ROOT / "Dimensions" / "Vector Arena"
ADAPTER = DIM / "holoverse_native_adapter.py"
MANIFEST = DIM / "holoverse_mode_manifest.json"
INDEX = ROOT / "Dimensions" / "dimension_index.json"

source = ADAPTER.read_text(encoding="utf-8", errors="replace")
manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
index = json.loads(INDEX.read_text(encoding="utf-8"))
errors: list[str] = []

try:
    tree = ast.parse(source)
except Exception as exc:
    tree = None
    errors.append(f"adapter does not parse: {exc}")


def literal_constant(name: str, default=None):
    if tree is None:
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


def require(token: str, label: str | None = None):
    if token not in source:
        errors.append(label or f"missing source token: {token}")

for helper in (
    "def _solid_box_node",
    "def _armor_strip_node",
    "def _build_walls_and_cover",
    "def _build_spawn_gates",
    "def _build_weapon_viewmodel",
):
    require(helper)

for token in (
    "solid_armored_wall",
    "solid_armored_cover",
    "cover_beveled_top_cap",
    "thin_front_light_seam",
    "solid_spawn_gate_machine",
    "left_armored_pylon",
    "heavy_header",
    "solid_skyline_pylon",
    "current_gen_armored_core",
    "current_gen_chest_plate",
    "current_gen_left_shoulder_armor",
    "weapon_barrel_opaque_shell",
    "weapon_projector_sight_bridge",
):
    require(token, f"missing current-gen hardlight style token {token}")

# Preserve gameplay/performance caps from prior passes.
for name, expected in (
    ("ENEMY_CAP", 20),
    ("PROJECTILE_CAP", 48),
    ("IMPACT_CAP", 48),
    ("SPAWN_PULSE_CAP", 10),
    ("KILL_BURST_CAP", 24),
    ("MUZZLE_FLASH_CAP", 12),
    ("REPULSOR_WAVE_CAP", 8),
    ("HEAT_VENT_SPARK_CAP", 16),
):
    if literal_constant(name, None) != expected:
        errors.append(f"{name} should remain {expected}")

gameplay = manifest.get("gameplay_contract") if isinstance(manifest.get("gameplay_contract"), dict) else {}
perf = manifest.get("performance_contract") if isinstance(manifest.get("performance_contract"), dict) else {}
route = index.get("dimensions", {}).get("vector_arena", {})

if manifest.get("launch_type") != "native_panda":
    errors.append("Vector Arena must remain native_panda")
if gameplay.get("camera") != "first_person":
    errors.append("Vector Arena camera must remain first_person")
if gameplay.get("ship_or_dogfight_controls") is not False:
    errors.append("ship/dogfight controls must remain false")
if gameplay.get("current_gen_style") != "solid_black_armored_hardlight_with_controlled_emissive_seams":
    errors.append("current_gen_style gameplay contract missing or wrong")
if gameplay.get("transparency_policy") != "minimal_alpha_for_fx_only_not_primary_forms":
    errors.append("transparency_policy gameplay contract missing or wrong")
if gameplay.get("arena_visuals") != "opaque_armored_walls_cover_spawn_gate_machines_with_thin_glow_cuts":
    errors.append("arena_visuals gameplay contract missing or wrong")
if gameplay.get("enemy_materials") != "opaque_black_armor_bodies_with_red_magenta_corrupted_cores_and_thin_emissive_accents":
    errors.append("enemy_materials gameplay contract missing or wrong")
if gameplay.get("weapon_materials") != "opaque_black_tactical_hardlight_rifle_with_cyan_power_coils_and_heat_slits":
    errors.append("weapon_materials gameplay contract missing or wrong")
if perf.get("current_gen_style_nodes") != "prebuilt_solid_card_cuboids_plus_line_seams":
    errors.append("current_gen_style_nodes performance contract missing or wrong")
if perf.get("transparency_policy") != "limited_to_thin_seams_hud_and_pooled_fx":
    errors.append("performance transparency policy missing or wrong")
if perf.get("runtime_node_creation") != "pooled_only_after_enter":
    errors.append("runtime node creation contract changed")
if "current_gen_hardlight_style" not in str(manifest.get("host_contract", "")):
    errors.append("manifest host_contract must identify current-gen hardlight style pass")
if "current_gen_hardlight_style" not in str(route.get("host_contract", "")):
    errors.append("dimension_index host_contract must identify current-gen hardlight style pass")

for forbidden in ("HoloUtopia", "player ship", "SAME-WINDOW DOGFIGHT", "Vector Wars-style ship"):
    if forbidden in source:
        errors.append(f"forbidden old presentation language remains: {forbidden}")

print(json.dumps({
    "schema": 1,
    "kind": "pass98_vector_arena_current_gen_style_validation",
    "ok": not errors,
    "errors": errors,
    "enemy_cap": literal_constant("ENEMY_CAP", None),
    "projectile_pool": literal_constant("PROJECTILE_CAP", None),
    "current_gen_style": gameplay.get("current_gen_style"),
    "transparency_policy": gameplay.get("transparency_policy"),
    "host_contract": manifest.get("host_contract"),
}, indent=2))
raise SystemExit(1 if errors else 0)
