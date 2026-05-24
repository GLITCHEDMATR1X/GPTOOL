#!/usr/bin/env python3
"""Validate Pass 95 Vector Arena enemy variants and satisfying pooled FX contract."""
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


def literal_constant(name: str, default=None):
    try:
        tree = ast.parse(source)
    except Exception as exc:
        errors.append(f"adapter does not parse: {exc}")
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


for variant in ("stalker", "brute", "sentry", "wraith", "guardian"):
    require(f'"id": "{variant}"', f"missing enemy variant {variant}")

for label in ("VECTOR STALKER", "IRON BRUTE", "ARC SENTRY", "RED WRAITH", "GATE GUARDIAN"):
    require(label, f"missing player-facing enemy label {label}")

for token in (
    "ENEMY_VARIANTS",
    "ENEMY_POOL_VARIANTS",
    "VARIANT_BY_ID",
    "def _enemy_profile",
    "def _kill_burst",
    "def _score_enemy_kill",
    "self.kill_bursts",
    "KILL_BURST_CAP",
    "THREAT MIX: STALKER / BRUTE / SENTRY / WRAITH / GUARDIAN",
):
    require(token)

if literal_constant("KILL_BURST_CAP", 0) != 24:
    errors.append("KILL_BURST_CAP should remain 24")
if literal_constant("ENEMY_CAP", 0) != 20:
    errors.append("ENEMY_CAP should remain 20")
if literal_constant("PROJECTILE_CAP", 0) != 48:
    errors.append("PROJECTILE_CAP should remain 48")
if literal_constant("IMPACT_CAP", 0) != 48:
    errors.append("IMPACT_CAP should remain 48")
if literal_constant("SPAWN_PULSE_CAP", 0) != 10:
    errors.append("SPAWN_PULSE_CAP should remain 10")

perf = manifest.get("performance_contract") if isinstance(manifest.get("performance_contract"), dict) else {}
gameplay = manifest.get("gameplay_contract") if isinstance(manifest.get("gameplay_contract"), dict) else {}
route = index.get("dimensions", {}).get("vector_arena", {})

if manifest.get("launch_type") != "native_panda":
    errors.append("Vector Arena must remain native_panda")
if gameplay.get("camera") != "first_person":
    errors.append("Vector Arena must remain first_person")
if gameplay.get("ship_or_dogfight_controls") is not False:
    errors.append("ship/dogfight controls must remain false")
if gameplay.get("enemy_variants") != "stalker_brute_sentry_wraith_guardian":
    errors.append("manifest enemy variant contract missing or wrong")
if gameplay.get("fx_feedback") != "pooled_hitscan_impact_spawn_and_kill_burst_fx":
    errors.append("manifest FX feedback contract missing or wrong")
if perf.get("kill_burst_pool") != 24:
    errors.append("manifest kill_burst_pool must be 24")
if perf.get("enemy_variant_count") != 5:
    errors.append("manifest enemy_variant_count must be 5")
if perf.get("runtime_node_creation") != "pooled_only_after_enter":
    errors.append("runtime node creation contract changed")
if "enemy_variants" not in str(route.get("host_contract", "")):
    errors.append("dimension_index host_contract should identify enemy variant adapter")

for forbidden in ("player ship", "SAME-WINDOW DOGFIGHT", "Vector Wars-style ship"):
    if forbidden in source:
        errors.append(f"forbidden old presentation language remains: {forbidden}")

print(json.dumps({
    "schema": 1,
    "kind": "pass95_vector_arena_enemy_variants_fx_validation",
    "ok": not errors,
    "errors": errors,
    "enemy_cap": literal_constant("ENEMY_CAP", None),
    "kill_burst_cap": literal_constant("KILL_BURST_CAP", None),
    "variant_count": 5,
    "host_contract": manifest.get("host_contract"),
}, indent=2))
raise SystemExit(1 if errors else 0)
