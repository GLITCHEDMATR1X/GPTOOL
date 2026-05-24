#!/usr/bin/env python3
"""Validate Pass 84 HoloSpace black-sky, nebula, war, and Dyson-return contract.

Static contract only: this deliberately avoids opening Panda3D.  It prevents the
Space region from regressing back to blue sky, platform-like props, or a one-way
outer-boundary exit instead of the Dyson sphere gate.
"""
from __future__ import annotations
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
WORLD = ROOT / "world.py"
MAIN = ROOT / "main.py"


def require(text: str, needle: str, errors: list[str], label: str) -> None:
    if needle not in text:
        errors.append(label)


def main() -> int:
    world = WORLD.read_text(encoding="utf-8")
    main_py = MAIN.read_text(encoding="utf-8")
    errors: list[str] = []

    require(world, 'return (0.000, 0.000, 0.000)', errors, 'standalone-holospace-black-sky-missing')
    require(main_py, 'return (0.000, 0.000, 0.000)', errors, 'host-holospace-black-sky-missing')
    require(world, 'SPACE_LAYER_NEBULA_COUNT = 10', errors, 'nebula-count-constant-missing')
    require(world, 'distant-nebula-field-root', errors, 'distant-nebula-root-missing')
    require(world, 'endless-space-war-activity-root', errors, 'endless-space-war-root-missing')
    require(world, 'SPACE_LAYER_WAR_ENTITY_COUNT = 24', errors, 'space-war-entity-cap-missing')
    require(world, 'SPACE_LAYER_WAR_TRACER_COUNT = 30', errors, 'space-war-tracer-cap-missing')
    require(world, 'self.update_space_war_activity(dt, space_alpha)', errors, 'space-war-update-call-missing')
    require(main_py, 'def respawn_holospace_ship', errors, 'holospace-respawn-function-missing')
    require(main_py, 'def update_holospace_battlefield_state', errors, 'holospace-battlefield-state-missing')
    require(main_py, 'self.update_holospace_battlefield_state(dt)', errors, 'holospace-battlefield-update-call-missing')
    require(main_py, 'HOLOSPACE_DYSON_RETURN_RADIUS = 540.0', errors, 'dyson-sphere-return-gate-missing')
    require(main_py, 'DYSON SPHERE GATE // RETURNED ON FOOT TO HUB', errors, 'dyson-return-hint-missing')
    require(main_py, 'SHIP DESTROYED // RESPAWNED AT HOLOSPACE SPAWN', errors, 'ship-destroyed-respawn-hint-missing')
    if 'r >= outer' in main_py or 'r <= inner or r >= outer' in main_py:
        errors.append('outer-space-boundary-still-exits-holospace')
    if 'CLOSE APP' in world:
        errors.append('standalone-world-close-overlay-regressed')

    if errors:
        for err in errors:
            print(err)
        return 1
    print('holospace-war-contract-ok')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
