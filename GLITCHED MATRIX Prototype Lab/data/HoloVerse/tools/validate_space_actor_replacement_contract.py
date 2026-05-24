#!/usr/bin/env python3
"""Validate Pass 88 space actor replacement contract.

HoloSpace should not show upright humanoid placeholder actors standing on
platform pads or carrying name-tag panels.  Space service actors must be
small spacecraft/buoys while preserving orbit tags and click/battle routing.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORLD = ROOT / "world.py"
text = WORLD.read_text(encoding="utf-8")


def require(cond: bool, msg: str) -> None:
    if not cond:
        raise SystemExit(f"FAIL: {msg}")

require('VERSION = "1.12.07-day-night-infill"' in text, "world version was not bumped for Pass 88")
require("SPACE_LAYER_ACTOR_REPLACEMENT_PASS88 = True" in text, "missing pass 88 feature flag")
require("space-inspector-service-craft" in text, "Dyson inspectors were not renamed/rebuilt as service craft")
require("space_actor_shape" in text, "space actor shape tags missing")
require("service_craft" in text and "battle_buoy" in text, "space actor shapes should be service craft and battle buoy")
require("space-inspector-drone" not in text, "old humanoid inspector drone node name remains")
require("space-inspector-craft-hull" in text and "space-inspector-craft-left-wing" in text, "inspector craft lacks horizontal ship hull/wing geometry")
require("battle-buoy-core" in text and "battle-buoy-fins" in text, "Space Bot battle buoy geometry missing")
require("return root\n        else:\n            self.add_disc_surface" in text, "Space Bot branch must return before normal hover-pad humanoid bot builder")
require("space_bot_battle_buoy_pass88" in text and "space_inspector_service_craft_pass88" in text, "debug contract fields missing")
require('label_text = "Space Bot"' not in text, "Space Bot should not build an attached name tag in world.py")
print("PASS: HoloSpace actor replacement contract validated")
