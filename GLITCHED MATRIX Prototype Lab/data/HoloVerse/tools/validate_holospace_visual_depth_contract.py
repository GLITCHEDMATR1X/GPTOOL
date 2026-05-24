#!/usr/bin/env python3
"""Validate Pass 86 HoloSpace visual-depth polish.

Static contract only: this keeps the Space region black/platformless while
checking the new line-only depth FX for distant war, bursts, lanes, and denser
nebula/starfield presentation.
"""
from __future__ import annotations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORLD = ROOT / "world.py"
MAIN = ROOT / "main.py"


def main() -> int:
    world = WORLD.read_text(encoding="utf-8")
    main_py = MAIN.read_text(encoding="utf-8")
    checks = {
        "main-version-pass86": '0.10.94-day-night-infill' in main_py or '0.10.87-holospace-visual-depth' in main_py,
        "world-version-pass86": '1.12.07-day-night-infill' in world or '1.12.06-space-actor-replacement' in world or '1.12.05-space-3d-scene-depth' in world or '1.12.04-space-visual-depth' in world,
        "true-black-host": 'return (0.000, 0.000, 0.000)' in main_py,
        "true-black-world": 'return (0.000, 0.000, 0.000)' in world,
        "denser-starfield-pass86": 'SPACE_LAYER_STAR_COUNT = 240' in world and 'SPACE_LAYER_DEEP_STAR_COUNT = 360' in world,
        "richer-nebulas-pass86": 'SPACE_LAYER_NEBULA_COUNT = 10' in world and 'distant-nebula-hero-visible' in world,
        "more-space-war-pass86": 'SPACE_LAYER_WAR_ENTITY_COUNT = 24' in world and 'SPACE_LAYER_WAR_TRACER_COUNT = 30' in world,
        "capital-scale-pass86": 'SPACE_LAYER_CAPITAL_SHIP_COUNT = 5' in world,
        "battle-bursts-pass86": 'SPACE_LAYER_BATTLE_BURST_COUNT = 7' in world and 'space-war-distant-burst-' in world,
        "warp-lanes-pass86": 'SPACE_LAYER_WARP_LANE_COUNT = 18' in world and 'space-war-warp-lane-' in world,
        "line-only-comment": 'no cards, no solid plates, no platform-like quads' in world,
        "visual-fx-build-call": 'self.build_space_battle_visual_fx(root, rng)' in world,
        "visual-fx-update-call": 'self.update_space_battle_visual_fx(dt, space_alpha)' in world,
        "report-fields-pass86": 'space_visual_depth_pass86' in world and 'space_layer_battle_burst_count_pass86' in world,
    }
    failed = [name for name, ok in checks.items() if not ok]
    if failed:
        for name in failed:
            print(name)
        return 1
    print("holospace-visual-depth-contract-ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
