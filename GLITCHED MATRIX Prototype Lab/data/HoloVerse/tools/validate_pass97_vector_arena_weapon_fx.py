#!/usr/bin/env python3
"""Validate Pass 97 Vector Arena weapon/FX presentation contract."""
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
    "def _build_weapon_viewmodel",
    "def _muzzle_flash",
    "def _repulsor_wave",
    "def _heat_vent_spark",
    "def _update_weapon_viewmodel",
):
    require(helper)

for token in (
    "vector_arena_fps_weapon_receiver",
    "vector_arena_fps_weapon_grip",
    "vector_arena_fps_weapon_stock",
    "vector_arena_fps_weapon_barrel_core",
    "vector_arena_fps_weapon_top_rail",
    "vector_arena_fps_weapon_capacitor_coil_a",
    "vector_arena_fps_weapon_capacitor_coil_b",
    "vector_arena_fps_weapon_left_heat_strip",
    "vector_arena_fps_weapon_right_heat_strip",
    "vector_arena_fps_weapon_muzzle_crown",
    "vector_arena_fps_weapon_charge_core",
    "vector_arena_fps_muzzle_flash",
    "vector_arena_fps_repulsor_wave",
    "vector_arena_fps_heat_vent_spark",
    "vector_arena_fps_hitscan_beam_halo",
    "vector_arena_fps_impact_star_a",
):
    require(token, f"missing weapon/FX token {token}")

if literal_constant("ENEMY_CAP", 0) != 20:
    errors.append("ENEMY_CAP should remain 20")
if literal_constant("PROJECTILE_CAP", 0) != 48:
    errors.append("PROJECTILE_CAP should remain 48")
if literal_constant("IMPACT_CAP", 0) != 48:
    errors.append("IMPACT_CAP should remain 48")
if literal_constant("SPAWN_PULSE_CAP", 0) != 10:
    errors.append("SPAWN_PULSE_CAP should remain 10")
if literal_constant("KILL_BURST_CAP", 0) != 24:
    errors.append("KILL_BURST_CAP should remain 24")
if literal_constant("MUZZLE_FLASH_CAP", 0) != 12:
    errors.append("MUZZLE_FLASH_CAP should be 12")
if literal_constant("REPULSOR_WAVE_CAP", 0) != 8:
    errors.append("REPULSOR_WAVE_CAP should be 8")
if literal_constant("HEAT_VENT_SPARK_CAP", 0) != 16:
    errors.append("HEAT_VENT_SPARK_CAP should be 16")

perf = manifest.get("performance_contract") if isinstance(manifest.get("performance_contract"), dict) else {}
gameplay = manifest.get("gameplay_contract") if isinstance(manifest.get("gameplay_contract"), dict) else {}
route = index.get("dimensions", {}).get("vector_arena", {})

if manifest.get("launch_type") != "native_panda":
    errors.append("Vector Arena must remain native_panda")
if gameplay.get("camera") != "first_person":
    errors.append("Vector Arena camera must remain first_person")
if gameplay.get("ship_or_dogfight_controls") is not False:
    errors.append("ship/dogfight controls must remain false")
if gameplay.get("weapon_visuals") != "enhanced_hardlight_pulse_rifle_with_capacitor_coils_heat_strips_muzzle_crown_and_recoil_animation":
    errors.append("manifest weapon_visuals contract missing or wrong")
if gameplay.get("weapon_fx") != "pooled_muzzle_flash_layered_hitscan_beams_impact_sparks_repulsor_waves_heat_vent_sparks_and_kill_bursts":
    errors.append("manifest weapon_fx contract missing or wrong")
# Older validator contract must be preserved.
if gameplay.get("fx_feedback") != "pooled_hitscan_impact_spawn_and_kill_burst_fx":
    errors.append("older fx_feedback contract changed")
if perf.get("weapon_visual_modeling") != "prebuilt_camera_mounted_line_primitive_pulse_rifle":
    errors.append("manifest weapon visual modeling contract missing or wrong")
if perf.get("muzzle_flash_pool") != 12:
    errors.append("manifest muzzle_flash_pool must be 12")
if perf.get("repulsor_wave_pool") != 8:
    errors.append("manifest repulsor_wave_pool must be 8")
if perf.get("heat_vent_spark_pool") != 16:
    errors.append("manifest heat_vent_spark_pool must be 16")
if perf.get("weapon_fx_runtime_creation") != "pooled_only_after_enter":
    errors.append("weapon FX runtime creation must remain pooled")
if perf.get("runtime_node_creation") != "pooled_only_after_enter":
    errors.append("global runtime node creation contract changed")
if "weapon_fx" not in str(route.get("host_contract", "")):
    errors.append("dimension_index host_contract should identify weapon_fx pass")
if "enemy_variants" not in str(route.get("host_contract", "")):
    errors.append("dimension_index host_contract should preserve enemy variant identity")

for forbidden in ("HoloUtopia", "player ship", "SAME-WINDOW DOGFIGHT", "Vector Wars-style ship"):
    if forbidden in source:
        errors.append(f"forbidden old presentation language remains: {forbidden}")

print(json.dumps({
    "schema": 1,
    "kind": "pass97_vector_arena_weapon_fx_validation",
    "ok": not errors,
    "errors": errors,
    "enemy_cap": literal_constant("ENEMY_CAP", None),
    "projectile_pool": literal_constant("PROJECTILE_CAP", None),
    "muzzle_flash_pool": literal_constant("MUZZLE_FLASH_CAP", None),
    "repulsor_wave_pool": literal_constant("REPULSOR_WAVE_CAP", None),
    "heat_vent_spark_pool": literal_constant("HEAT_VENT_SPARK_CAP", None),
    "weapon_visuals": gameplay.get("weapon_visuals"),
    "weapon_fx": gameplay.get("weapon_fx"),
    "host_contract": manifest.get("host_contract"),
}, indent=2))
raise SystemExit(1 if errors else 0)
