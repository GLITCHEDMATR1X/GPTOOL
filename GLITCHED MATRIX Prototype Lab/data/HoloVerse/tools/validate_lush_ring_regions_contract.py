#!/usr/bin/env python3
"""Static contract checks for Pass 78 lush ring-region polish.

This validator stays source-only: it does not launch Panda3D, write logs, or
capture screenshots. It verifies that the natural rings now have distinct,
batched detail layers and self-test/report hooks so the pass cannot silently
fall back to the older sparse region presentation.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORLD = ROOT / "world.py"


def require(text: str, needle: str, errors: list[str], label: str | None = None) -> None:
    if needle not in text:
        errors.append(label or f"missing: {needle}")


def main() -> int:
    text = WORLD.read_text(encoding="utf-8")
    errors: list[str] = []

    required_constants = {
        "FOREST_TALL_TREE_BONUS_PER_CHUNK = 14": "forest tree bonus not increased",
        "FOREST_UNDERSTORY_CLUSTERS_PER_CHUNK = 24": "forest understory density constant missing",
        "HILLS_SOLID_PLANTS_PER_CHUNK = 24": "hills solid plant density not increased",
        "HILLS_MEADOW_PATCHES_PER_CHUNK = 10": "hills meadow patch density constant missing",
        "MUSHROOM_FOREST_GROUPS_PER_CHUNK = 18": "mushroom major cluster density not increased",
        "MUSHROOM_HILL_LINE_COUNT = 10": "mushroom terrain contour density not increased",
        "MUSHROOM_GLOW_SPROUTS_PER_CHUNK = 28": "mushroom glow sprout density constant missing",
    }
    for needle, label in required_constants.items():
        require(text, needle, errors, label)

    for method in (
        "def build_forest_understory_set",
        "def build_hills_meadow_set",
        "def build_mushroom_glow_sprout_set",
    ):
        require(text, method, errors)

    for call in (
        "forest_understory_count = self.build_forest_understory_set",
        "hills_meadow_count = self.build_hills_meadow_set",
        "mushroom_glow_sprout_count = self.build_mushroom_glow_sprout_set",
    ):
        require(text, call, errors)

    for tag in (
        "forest_understory_count",
        "forest_sapling_count",
        "hills_meadow_count",
        "mushroom_glow_sprout_count",
    ):
        require(text, f'setPythonTag("{tag}"', errors)

    for report_key in (
        "forest_understory_active_count_pass78",
        "green_hills_meadow_active_count_pass78",
        "mushroom_glow_sprout_active_count_pass78",
    ):
        require(text, report_key, errors)

    require(text, 'view_key in ("mushroom", "fungal", "fungi", "glowshrooms")', errors, "mushroom self-test view missing")

    # The new layers should be batched with line/polyline helpers, not one heavy
    # model node per small blade/glow/sprout.
    for helper in (
        "forest-understory-fern-fans",
        "hills-meadow-grass-blades",
        "mushroom-glow-sprout-stems",
    ):
        require(text, helper, errors)

    payload = {
        "kind": "lush_ring_regions_contract_validation",
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "checked_file": str(WORLD.relative_to(ROOT)),
    }
    print(json.dumps(payload, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
