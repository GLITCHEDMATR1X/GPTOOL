#!/usr/bin/env python3
"""Validate Pass 85 HoloSpace visual/control polish.

This static check guards the dedicated arcade-space controller and the richer
black-space battlefield layer without requiring a Panda3D window.
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
        "main-version-pass85": '0.10.94-day-night-infill' in main_py or '0.10.87-holospace-visual-depth' in main_py or '0.10.86-holospace-visual-controls' in main_py,
        "world-version-pass85": '1.12.07-day-night-infill' in world or '1.12.06-space-actor-replacement' in world or '1.12.07-day-night-infill' in world or '1.12.06-space-actor-replacement' in world or '1.12.05-space-3d-scene-depth' in world or '1.12.04-space-visual-depth' in world or '1.12.03-space-visual-controls' in world,
        "arcade-cruise-constant": 'HOLOSPACE_CRUISE_SPEED = 380.0' in main_py,
        "arcade-boost-constant": 'HOLOSPACE_BOOST_SPEED = 720.0' in main_py,
        "arcade-brake-response": 'HOLOSPACE_BRAKE_RESPONSE = 7.2' in main_py,
        "dyson-return-radius-constant": 'HOLOSPACE_DYSON_RETURN_RADIUS = 540.0' in main_py,
        "input-hint-updated": 'WASD FLY // SHIFT BOOST // SPACE/CTRL VERTICAL // DYSON RETURNS' in main_py,
        "controller-uses-camera-up": 'desired += up * vertical * cruise_speed * float(HOLOSPACE_VERTICAL_SCALE)' in main_py,
        "controller-has-arcade-brake": 'HOLOSPACE_BRAKE_RESPONSE' in main_py and 'current *= max(0.0, 1.0 - dt * float(HOLOSPACE_BRAKE_RESPONSE))' in main_py,
        "space-black-sky-host": 'return (0.000, 0.000, 0.000)' in main_py,
        "space-black-sky-standalone": 'return (0.000, 0.000, 0.000)' in world,
        "denser-starfield": 'SPACE_LAYER_STAR_COUNT = 240' in world and 'SPACE_LAYER_DEEP_STAR_COUNT = 360' in world,
        "visible-nebulas": 'SPACE_LAYER_NEBULA_COUNT = 10' in world and 'distant-nebula-hero-visible' in world,
        "capital-ship-silhouettes": 'SPACE_LAYER_CAPITAL_SHIP_COUNT = 5' in world and 'space-war-capital-' in world,
        "more-tracers": 'SPACE_LAYER_WAR_TRACER_COUNT = 30' in world,
        "capital-update-loop": 'space_layer_capital_ship_nodes' in world and 'space_capital_radius' in world,
    }
    failed = [name for name, ok in checks.items() if not ok]
    if failed:
        for name in failed:
            print(name)
        return 1
    print("holospace-visual-controls-contract-ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
