#!/usr/bin/env python3
"""Validate Pass 94 Vector Arena phased wave/scenery presentation contract."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / "Dimensions" / "Vector Arena" / "holoverse_native_adapter.py"
MANIFEST = ROOT / "Dimensions" / "Vector Arena" / "holoverse_mode_manifest.json"

errors: list[str] = []
source = ADAPTER.read_text(encoding="utf-8") if ADAPTER.exists() else ""
manifest = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else {}

def require_source(token: str, label: str | None = None):
    if token not in source:
        errors.append(label or f"missing source token: {token}")

def require_manifest(path: tuple[str, ...], expected=None):
    value = manifest
    for key in path:
        if not isinstance(value, dict) or key not in value:
            errors.append("missing manifest key: " + ".".join(path))
            return
        value = value[key]
    if expected is not None and value != expected:
        errors.append(f"manifest {'.'.join(path)} expected {expected!r}, got {value!r}")

require_source("SCENERY_THEMES", "theme catalog missing")
require_source("PRISM FOUNDRY", "theme PRISM FOUNDRY missing")
require_source("NEON CANYON", "theme NEON CANYON missing")
require_source("FROST CIRCUIT", "theme FROST CIRCUIT missing")
require_source("DATA STORM", "theme DATA STORM missing")
require_source("REDLINE CORE", "theme REDLINE CORE missing")
require_source("def _build_scenery_shell", "scenery shell builder missing")
require_source("def _apply_scenery_theme", "theme application method missing")
require_source("def _advance_wave", "wave advancement method missing")
require_source("def _update_scenery", "scenery update method missing")
require_source("self._update_scenery(dt)", "scenery update not called")

require_manifest(("id",), "vector_arena")
require_manifest(("launch_type",), "native_panda")
require_manifest(("gameplay_contract", "camera"), "first_person")
require_manifest(("gameplay_contract", "ship_or_dogfight_controls"), False)
require_manifest(("gameplay_contract", "vector_wars_style"), False)
require_manifest(("gameplay_contract", "wave_scenery"), "hardlight_theme_shell_changes_each_wave")
require_manifest(("gameplay_contract", "scenery_changes_affect_layout"), False)
require_manifest(("performance_contract", "enemy_cap"), 20)
require_manifest(("performance_contract", "projectile_pool"), 48)
require_manifest(("performance_contract", "impact_pool"), 48)
require_manifest(("performance_contract", "spawn_pulse_pool"), 10)
require_manifest(("performance_contract", "scenery_theme_count"), 5)
require_manifest(("performance_contract", "scenery_runtime_creation"), "prebuilt_theme_nodes_recolored_per_wave")

# Guard against accidental return to dogfight language/controls in the adapter.
for forbidden in ("player ship", "Vector Wars-style ship"):
    if forbidden in source:
        errors.append(f"forbidden old presentation language remains: {forbidden}")

print(json.dumps({
    "schema": 1,
    "kind": "pass94_vector_arena_wave_scenery_validation",
    "adapter": str(ADAPTER.relative_to(ROOT)),
    "manifest": str(MANIFEST.relative_to(ROOT)),
    "theme_count": source.count('"name":'),
    "errors": errors,
    "ok": not errors,
}, indent=2))
raise SystemExit(1 if errors else 0)
