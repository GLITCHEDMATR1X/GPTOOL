#!/usr/bin/env python3
"""Static contract checks for Pass 80 Frost Circuit arcade hovercraft polish.

The user called out the Ice race as boxy and hard to control.  This validator
keeps the pass from silently reverting to the old small-box craft or the older
stiff handling profile.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "Dimensions" / "Frost Circuit" / "runtime.py"


def require(text: str, needle: str, errors: list[str], label: str | None = None) -> None:
    if needle not in text:
        errors.append(label or f"missing: {needle}")


def main() -> int:
    text = RUNTIME.read_text(encoding="utf-8")
    errors: list[str] = []

    required = {
        "ICE_CRAFT_VISUAL_SCALE = 2.25": "large hovercraft scale constant missing",
        "ICE_PLAYER_MAX_SPEED = 134.0": "player speed was not upgraded",
        "ICE_PLAYER_ACCEL = 88.0": "player acceleration was not upgraded",
        "ICE_TRACK_CENTERING_ASSIST = 0.92": "track-centering assist missing",
        "frost_circuit_camera_distance = 86.0": "larger craft camera distance default missing",
        "frost_circuit_camera_height = 33.0": "larger craft camera height default missing",
        "craft-side-thruster": "side thruster visual layer missing",
        "craft-speed-stream": "engine speed-stream visual layer missing",
        "craft-nose-core": "clear nose core visual layer missing",
        "steer_input_smooth": "smooth steering state missing",
        "keys.get(\"arrow_up\")": "arrow-key throttle support missing",
        "keys.get(\"arrow_right\")": "arrow-key steering support missing",
        "correction = max(-42.0, min(42.0, track_error * ICE_TRACK_CENTERING_ASSIST * dt))": "centerline correction missing",
        "Arcade sled handling": "updated race help text missing",
        "frameColor=(0.010, 0.018, 0.035, 0.42)": "Frost Circuit HUD panel is too solid",
        "frameSize=(-1.13, 1.13, -0.145, 0.145)": "Frost Circuit HUD was not compacted",
    }
    for needle, label in required.items():
        require(text, needle, errors, label)

    old_small_markers = (
        "width = 5.2 + rng.random() * 2.2",
        "length = 11.0 + rng.random() * 3.5",
        "max_speed = 100.0 if name == \"Player\"",
        "turn_rate = 96.0 * (0.38 + min(0.94, abs(speed) / 80.0))",
    )
    for needle in old_small_markers:
        if needle in text:
            errors.append(f"old small/stiff Frost Circuit marker still present: {needle}")

    payload = {
        "kind": "frost_circuit_arcade_contract_validation",
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "checked_file": str(RUNTIME.relative_to(ROOT)),
    }
    print(json.dumps(payload, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
