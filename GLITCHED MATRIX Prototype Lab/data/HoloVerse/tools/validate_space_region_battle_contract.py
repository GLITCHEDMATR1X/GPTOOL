#!/usr/bin/env python3
"""Validate Pass 82 infinite space, Space Bot orbit, and space-battle doorway contract."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORLD = ROOT / "world.py"
MOUNT = ROOT / "holoverse_world_shell_mount.py"
MAIN = ROOT / "main.py"
INDEX = ROOT / "Dimensions" / "dimension_index.json"
CONFIG = ROOT / "assets" / "config" / "holoverse_bot_dimension_links.json"

def fail(msg: str) -> None:
    print(f"space_region_battle_contract: FAIL: {msg}")
    sys.exit(1)

world = WORLD.read_text(encoding="utf-8", errors="ignore")
mount = MOUNT.read_text(encoding="utf-8", errors="ignore")
main = MAIN.read_text(encoding="utf-8", errors="ignore")

checks = {
    "deep star constant": "SPACE_LAYER_DEEP_STAR_COUNT" in world,
    "flying entity constant": "SPACE_LAYER_FLYING_ENTITY_COUNT" in world,
    "flying entity builder": "def build_space_flying_entity" in world,
    "flying entity updater": "def update_space_flying_entities" in world and "self.update_space_flying_entities(dt, space_alpha)" in world,
    "space bot orbit position": "def dyson_space_bot_orbit_position" in world,
    "space bot named spec": '"name": "Space Bot"' in world,
    "orbit radius safe constant": "SPACE_DYSON_BOT_ORBIT_RADIUS = 575.0" in world,
    "mount does not skip space bot anchor": '"named_region_bot_anchor"' not in re.search(r"BIOME_SOURCE_BRIDGE_METHOD_SKIP = \{([^}]+)\}", mount, re.S).group(1),
    "mount updates bots during holospace": '"space_bot_visible": True' in mount and '("update_named_region_bots", (dt,))' in mount,
    "main space bot profile": '"Space Bot": {"region": "SPACE / HoloSpace", "mode": "Vector Wars"' in main,
    "space bot click direct battle": 'bot_name in {"space bot", "orbit"}' in main and 'STARTING SPACE BATTLE' in main and 'self.launch_bot_dimension_mode(mode, ctx)' in main,
    "standalone close overlay retired": 'CLOSE APP' not in world and 'safety-exit-root-retired' in world,
    "holospace zone label": 'return "HoloSpace"' in world and 'holospace_active' in world,
}
for label, ok in checks.items():
    if not ok:
        fail(label)

try:
    index = json.loads(INDEX.read_text(encoding="utf-8"))
except Exception as exc:
    fail(f"dimension_index unreadable: {exc}")
by_bot = index.get("by_bot") if isinstance(index.get("by_bot"), dict) else {}
if by_bot.get("Space Bot") != "vector_wars" or by_bot.get("Orbit") != "vector_wars":
    fail("Space Bot / Orbit must route to vector_wars in dimension_index")
try:
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    profiles = cfg.get("profiles") if isinstance(cfg.get("profiles"), dict) else {}
except Exception as exc:
    fail(f"bot config unreadable: {exc}")
if profiles.get("Space Bot", {}).get("mode") != "Vector Wars":
    fail("Space Bot profile must launch Vector Wars")
if profiles.get("Orbit", {}).get("mode") != "Vector Wars":
    fail("legacy Orbit profile must redirect to Vector Wars")
print("space_region_battle_contract: PASS")
