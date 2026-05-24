#!/usr/bin/env python3
"""Validate Pass 87 HoloSpace 3D scene-depth contract."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORLD = ROOT / "world.py"
text = WORLD.read_text(encoding="utf-8")
mod = ast.parse(text)
assigns: dict[str, object] = {}
for node in mod.body:
    if isinstance(node, ast.Assign):
        for target in node.targets:
            if isinstance(target, ast.Name):
                try:
                    assigns[target.id] = ast.literal_eval(node.value)
                except Exception:
                    pass

def require(cond: bool, msg: str) -> None:
    if not cond:
        raise SystemExit(f"FAIL: {msg}")

require('VERSION = "1.12.07-day-night-infill"' in text or 'VERSION = "1.12.06-space-actor-replacement"' in text or 'VERSION = "1.12.05-space-3d-scene-depth"' in text, "world version was not bumped for Pass 87+")
require(int(assigns.get("SPACE_LAYER_PLANET_BACKDROP_COUNT", 0)) == 3, "expected exactly 3 distant planet backdrops")
require(8 <= int(assigns.get("SPACE_LAYER_ASTEROID_COUNT", 0)) <= 10, "asteroid count should be modest and 3D-readable")
require(10 <= int(assigns.get("SPACE_LAYER_DEBRIS_CLUSTER_COUNT", 0)) <= 16, "debris clusters should be sparse, not crowded")
require(int(assigns.get("SPACE_LAYER_CAPITAL_SHIP_COUNT", 0)) <= 5, "capital ship count should remain capped")
require(int(assigns.get("SPACE_LAYER_HERO_CRUISER_COUNT", 0)) == 2, "expected exactly 2 foreground hero cruisers")
require("def add_lowpoly_sphere" in text, "missing low-poly planet sphere helper")
require("def build_space_planet_backdrops" in text, "missing planet backdrop builder")
require("def build_space_debris_field" in text, "missing sparse debris field builder")
require("def build_space_hero_cruisers" in text, "missing foreground hero cruiser builder")
require("def update_space_3d_scene_depth" in text, "missing 3D scene-depth updater")
require("build_space_planet_backdrops(root, rng)" in text, "planet backdrops are not built during space layer rebuild")
require("build_space_debris_field(root, rng)" in text, "debris field is not built during space layer rebuild")
require("build_space_hero_cruisers(root, rng)" in text, "hero cruisers are not built during space layer rebuild")
require("update_space_3d_scene_depth(dt, space_alpha, holospace)" in text, "3D scene-depth updater is not called")
require("space_3d_planet_backdrops_pass87" in text, "planet backdrop pass tag missing")
require("space_3d_debris_field_pass87" in text, "debris field pass tag missing")
require("space_hero_cruisers_pass87" in text, "hero cruiser pass tag missing")
require("space_3d_scene_depth_pass87" in text, "debug contract flag missing")
require("space_layer_hero_cruiser_count_pass87" in text, "hero cruiser debug field missing")
require(text.count("add_solid_box(node") >= 8, "space scene should add actual translucent 3D volume, not only lines")
require("CardMaker" in text and "space-planet" in text and "cm.setFrame" not in text[text.find('def build_space_planet_backdrops'):text.find('def build_space_war_activity')], "planet backdrops must not use flat cards")
print("PASS: HoloSpace 3D scene-depth contract validated")
