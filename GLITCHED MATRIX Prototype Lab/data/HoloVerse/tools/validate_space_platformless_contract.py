#!/usr/bin/env python3
"""Static contract for Pass 83 platformless HoloSpace cleanup.

The Space region should feel like open space.  Space Bot must not carry the
normal named-bot hover pad / floor disc into HoloSpace, and the screenshot path
must use a dark space sky instead of daylight terrain fog.
"""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
WORLD = ROOT / "world.py"


def fail(msg: str) -> int:
    print(f"FAIL: {msg}")
    return 1


def main() -> int:
    text = WORLD.read_text(encoding="utf-8")
    checks = {
        "version-bump": 'VERSION = "1.12.06-space-actor-replacement"' in text or 'VERSION = "1.12.05-space-3d-scene-depth"' in text or 'VERSION = "1.12.04-space-visual-depth"' in text or 'VERSION = "1.12.03-space-visual-controls"' in text,
        "space-branch": 'if kind == "space":' in text,
        "space-pad-comment": 'not a\n            # humanoid placeholder with a pad and name tag' in text or ('No local hover pad or' in text and 'flat disc is drawn in HoloSpace' in text),
        "space-orbit-marker": 'space_bot_orbit_marker' in text and ('space-buoy-signal-arc' in text or 'space-orbit-halo' in text),
        "small-space-label": 'space_bot_battle_buoy_pass88' in text or ('label_text = "Space Bot"' in text and 'label_scale = 0.92' in text),
        "dark-holospace-sky": 'if bool(getattr(self, "holospace_active", False)):' in text and 'return (0.000, 0.000, 0.000)' in text,
        "dark-holospace-fog": 'self.fog.setColor(0.000, 0.000, 0.000)' in text,
        "dyson-wire-softened": 'faint orbit cages, not hard red platform-looking panels' in text,
        "report-fields": 'space_region_platformless_pass83' in text and 'space_bot_hover_pad_removed_pass83' in text,
    }
    missing = [name for name, ok in checks.items() if not ok]
    if missing:
        return fail("missing contract markers: " + ", ".join(missing))

    space_branch_idx = text.find('if kind == "space":')
    else_idx = text.find('else:\n            self.add_disc_surface(root, 4.8, 0.05, shadow, 36, f"{name.lower()}-hover-pad")', space_branch_idx)
    pad_idx = text.find('f"{name.lower()}-hover-pad"', space_branch_idx)
    if not (space_branch_idx >= 0 and else_idx >= 0 and pad_idx >= else_idx):
        return fail("named-region hover pad is not gated away from kind == space")

    print("PASS: HoloSpace platformless visual contract")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
