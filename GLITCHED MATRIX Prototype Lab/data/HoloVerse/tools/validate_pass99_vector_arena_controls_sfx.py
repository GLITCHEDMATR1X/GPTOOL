#!/usr/bin/env python3
"""Validate Pass 99 Vector Arena true-heading controls + generated SFX contract."""
from __future__ import annotations

import ast
import json
from pathlib import Path
import wave

ROOT = Path(__file__).resolve().parents[1]
DIM = ROOT / "Dimensions" / "Vector Arena"
ADAPTER = DIM / "holoverse_native_adapter.py"
MANIFEST = DIM / "holoverse_mode_manifest.json"
INDEX = ROOT / "Dimensions" / "dimension_index.json"
SFX_DIR = DIM / "assets" / "sfx"
SFX_MANIFEST = SFX_DIR / "sfx_manifest.json"

source = ADAPTER.read_text(encoding="utf-8", errors="replace")
manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
index = json.loads(INDEX.read_text(encoding="utf-8"))
errors: list[str] = []

try:
    tree = ast.parse(source)
except Exception as exc:  # pragma: no cover - report path
    tree = None
    errors.append(f"adapter does not parse: {exc}")


def require(token: str, label: str | None = None) -> None:
    if token not in source:
        errors.append(label or f"missing source token: {token}")


for token in (
    "def _heading_vec",
    "return Vec3(-math.sin(a), math.cos(a), 0.0)",
    "def _right_vec_from_forward",
    "return Vec3(forward.y, -forward.x, 0.0)",
    "vec = Vec3(-math.sin(y) * cp, math.cos(y) * cp, -math.sin(p))",
):
    require(token, f"missing true-heading control token: {token}")

for forbidden in (
    "return Vec3(math.sin(a), math.cos(a), 0.0)",
    "vec = Vec3(math.sin(y) * cp, math.cos(y) * cp, -math.sin(p))",
    "right = Vec3(forward.y, -forward.x, 0)",
):
    if forbidden in source:
        errors.append(f"forbidden old control mapping remains: {forbidden}")

for token in (
    "if self._key_down(\"w\"):",
    "if self._key_down(\"s\"):",
    "if self._key_down(\"d\"):",
    "if self._key_down(\"a\"):",
    "self._mouse_down(1)",
    "self._mouse_down(3)",
    "self._key_down(\"shift\")",
    "self._key_down(\"r\")",
):
    require(token, f"missing expected control binding: {token}")

for token in (
    "VECTOR_ARENA_SFX_FILES",
    "def _load_sfx",
    "def _play_sfx",
    "self._play_sfx(\"pulse_rifle\")",
    "self._play_sfx(\"repulsor_blast\")",
    "self._play_sfx(\"heat_vent\")",
    "self._play_sfx(\"enemy_hit\")",
    "self._play_sfx(\"enemy_destroyed\")",
    "self._play_sfx(\"wave_start\")",
    "self._play_sfx(\"player_hit\")",
):
    require(token, f"missing sfx integration token: {token}")

expected_sfx = (
    "pulse_rifle.wav",
    "repulsor_blast.wav",
    "heat_vent.wav",
    "enemy_hit.wav",
    "enemy_destroyed.wav",
    "wave_start.wav",
    "player_hit.wav",
)
if not SFX_MANIFEST.is_file():
    errors.append("missing sfx manifest")
else:
    try:
        sfx_manifest = json.loads(SFX_MANIFEST.read_text(encoding="utf-8"))
        if sfx_manifest.get("generated_by") != "GPTOOL patch gate procedural sfx generator":
            errors.append("sfx manifest generated_by missing/wrong")
    except Exception as exc:
        errors.append(f"invalid sfx manifest: {exc}")

for filename in expected_sfx:
    path = SFX_DIR / filename
    if not path.is_file():
        errors.append(f"missing sfx file: {filename}")
        continue
    if path.stat().st_size < 2048:
        errors.append(f"sfx file too small: {filename}")
    try:
        with wave.open(str(path), "rb") as wav:
            if wav.getnchannels() != 1:
                errors.append(f"sfx should be mono: {filename}")
            if wav.getframerate() < 22050:
                errors.append(f"sfx sample rate too low: {filename}")
            if wav.getnframes() <= 0:
                errors.append(f"sfx has no frames: {filename}")
    except Exception as exc:
        errors.append(f"sfx invalid wav {filename}: {exc}")

gameplay = manifest.get("gameplay_contract") if isinstance(manifest.get("gameplay_contract"), dict) else {}
perf = manifest.get("performance_contract") if isinstance(manifest.get("performance_contract"), dict) else {}
route = index.get("dimensions", {}).get("vector_arena", {})

if manifest.get("launch_type") != "native_panda":
    errors.append("Vector Arena must remain native_panda")
if gameplay.get("camera") != "first_person":
    errors.append("Vector Arena camera must remain first_person")
if gameplay.get("ship_or_dogfight_controls") is not False:
    errors.append("ship/dogfight controls must remain false")
if gameplay.get("controls") != "true_panda3d_heading_first_person_wasd_mouse_lmb_rmb_shift_r":
    errors.append("manifest controls contract missing/wrong")
if gameplay.get("sfx_assets") != "generated_pulse_repulsor_vent_hit_destroyed_wave_player_hit_wav":
    errors.append("manifest sfx assets contract missing/wrong")
if perf.get("sfx_policy") != "tiny_generated_wav_assets_loaded_optionally_no_audio_required_for_smoke":
    errors.append("manifest sfx performance policy missing/wrong")
if "controls_sfx" not in str(manifest.get("host_contract", "")):
    errors.append("manifest host_contract must identify controls_sfx pass")
if "controls_sfx" not in str(route.get("host_contract", "")):
    errors.append("dimension_index host_contract must identify controls_sfx pass")
if route.get("launch_type") != "native_panda":
    errors.append("dimension_index Vector Arena must remain native_panda")

for forbidden in ("SAME-WINDOW DOGFIGHT", "Vector Wars-style ship", "player ship"):
    if forbidden in source:
        errors.append(f"forbidden old presentation language remains: {forbidden}")

report = {
    "schema": 1,
    "kind": "pass99_vector_arena_controls_sfx_validation",
    "ok": not errors,
    "errors": errors,
    "controls": gameplay.get("controls"),
    "sfx_assets": list(expected_sfx),
    "host_contract": manifest.get("host_contract"),
}
print(json.dumps(report, indent=2))
raise SystemExit(0 if not errors else 2)
