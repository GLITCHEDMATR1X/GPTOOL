#!/usr/bin/env python3
"""Static contract checks for Pass 81 Urban dynamic battlefield polish.

Urban should read as a live battlefield as soon as the player reaches the
region, while the formal Sable match remains the scoring/wave activity.  This
keeps the ambient layer lightweight, autonomous, spaced out, and HoloVerse-audio
owned.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "Dimensions" / "Urban Warzone" / "runtime.py"


def require(text: str, needle: str, errors: list[str], label: str | None = None) -> None:
    if needle not in text:
        errors.append(label or f"missing: {needle}")


def main() -> int:
    text = RUNTIME.read_text(encoding="utf-8")
    errors: list[str] = []

    required = {
        "AMBIENT_BATTLE_MAX_ACTORS = 10": "ambient actor cap missing or too high",
        "AMBIENT_BATTLE_MAX_EVENTS = 4": "ambient event cap missing or too high",
        "AMBIENT_BATTLE_EVENT_MIN_INTERVAL = 4.8": "ambient events are not spaced apart",
        "AMBIENT_BATTLE_SFX_MIN_INTERVAL = 2.4": "background SFX throttle missing",
        "self.urban_battlefield_actors = []": "ambient actor state missing",
        "self.urban_battlefield_events = []": "ambient event state missing",
        "def _urban_play_battle_sfx": "host-owned Urban SFX relay missing",
        "audio.play(filename, bus=\"sfx\"": "Urban SFX must use HoloVerse shared audio",
        "def _spawn_ambient_battlefield_event": "spaced ambient battlefield event spawner missing",
        "def _update_urban_battlefield_ambient": "ambient battlefield AI updater missing",
        "_update_urban_battlefield_ambient(self, dt, root)": "ambient battlefield update not called from region runtime",
        "\"faction\": \"ally\" if kind == \"ally\" else \"enemy\"": "ambient actors need ally/enemy factions",
        "\"ai_state\"] = \"ambient_live_crossfire\"": "ambient autonomous crossfire state missing",
        "urban-ambient-airstrike": "ambient airstrike event missing",
        "urban-ambient-drop-pod": "ambient drop-pod event missing",
        "urban-ambient-emp": "ambient EMP event missing",
        "_urban_play_battle_sfx(self, \"fire\"": "weapon fire SFX hook missing",
        "_urban_play_battle_sfx(self, \"hit\"": "impact SFX hook missing",
        "alpha=(0.20 if typ in heavy_types else 0.15)": "Urban buried structures are still too visually solid",
    }
    for needle, label in required.items():
        require(text, needle, errors, label)

    overcrowding_markers = {
        "AMBIENT_BATTLE_MAX_ACTORS = 14": "ambient actor cap regressed toward overcrowding",
        "AMBIENT_BATTLE_MAX_EVENTS = 8": "ambient event cap regressed toward clutter",
        "rng.uniform(0.5, 1.0)": "ambient events appear too frequent",
    }
    for needle, label in overcrowding_markers.items():
        if needle in text:
            errors.append(label)

    payload = {
        "kind": "urban_dynamic_battlefield_contract_validation",
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "checked_file": str(RUNTIME.relative_to(ROOT)),
    }
    print(json.dumps(payload, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
