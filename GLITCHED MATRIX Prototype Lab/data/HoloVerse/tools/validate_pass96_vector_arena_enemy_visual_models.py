#!/usr/bin/env python3
"""Validate Pass 96 Vector Arena menacing enemy visual model contract."""
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
    "def _diamond_node",
    "def _chevron_node",
    "def _fang_arc_node",
    "def _enemy_threat_rig",
):
    require(helper)

for visual_token in (
    "_floor_threat_aura",
    "_weak_core_diamond",
    "_predator_optic",
    "_threat_crest",
    "_back_spine_stack",
    "_vertical_threat_marker",
    "_hardlight_body_glow_panel",
    "_hardlight_shoulder_glow_panel",
    "_layered_crusher_torso",
    "_wide_targeting_eye",
    "_floating_void_mask",
    "_fortress_torso",
    "_thin_predator_torso",
    "_left_execution_blade",
    "_right_execution_blade",
):
    require(visual_token, f"missing visual model token {visual_token}")

for variant in ("stalker", "brute", "sentry", "wraith", "guardian"):
    require(f'"id": "{variant}"', f"missing enemy variant {variant}")

for label in ("VECTOR STALKER", "IRON BRUTE", "ARC SENTRY", "RED WRAITH", "GATE GUARDIAN"):
    require(label, f"missing enemy label {label}")

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

perf = manifest.get("performance_contract") if isinstance(manifest.get("performance_contract"), dict) else {}
gameplay = manifest.get("gameplay_contract") if isinstance(manifest.get("gameplay_contract"), dict) else {}
route = index.get("dimensions", {}).get("vector_arena", {})

if manifest.get("launch_type") != "native_panda":
    errors.append("Vector Arena must remain native_panda")
if gameplay.get("camera") != "first_person":
    errors.append("Vector Arena camera must remain first_person")
if gameplay.get("ship_or_dogfight_controls") is not False:
    errors.append("ship/dogfight controls must remain false")
if gameplay.get("enemy_visuals") != "enhanced_menacing_hardlight_models_with_armor_cores_horns_claws_and_threat_crests":
    errors.append("manifest enemy_visuals contract missing or wrong")
if perf.get("enemy_visual_modeling") != "prebuilt_pooled_line_primitive_enemy_rigs":
    errors.append("manifest enemy visual modeling contract missing or wrong")
if perf.get("enemy_model_variant_count") != 5:
    errors.append("manifest enemy_model_variant_count must be 5")
if perf.get("runtime_node_creation") != "pooled_only_after_enter":
    errors.append("runtime node creation contract changed")
if "menacing_models" not in str(route.get("host_contract", "")):
    errors.append("dimension_index host_contract should identify menacing model pass")
if "enemy_variants" not in str(route.get("host_contract", "")):
    errors.append("dimension_index host_contract should preserve enemy variant identity")

for forbidden in ("HoloUtopia", "player ship", "SAME-WINDOW DOGFIGHT", "Vector Wars-style ship"):
    if forbidden in source:
        errors.append(f"forbidden old presentation language remains: {forbidden}")

print(json.dumps({
    "schema": 1,
    "kind": "pass96_vector_arena_enemy_visual_models_validation",
    "ok": not errors,
    "errors": errors,
    "enemy_cap": literal_constant("ENEMY_CAP", None),
    "projectile_pool": literal_constant("PROJECTILE_CAP", None),
    "kill_burst_cap": literal_constant("KILL_BURST_CAP", None),
    "visual_contract": gameplay.get("enemy_visuals"),
    "host_contract": manifest.get("host_contract"),
}, indent=2))
raise SystemExit(1 if errors else 0)
