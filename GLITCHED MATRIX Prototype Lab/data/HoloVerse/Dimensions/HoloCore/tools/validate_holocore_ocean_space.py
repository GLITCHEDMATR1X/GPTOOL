#!/usr/bin/env python3
"""Validate HoloCore horizontal ocean-space progression."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dimensions.ocean_space import (  # noqa: E402
    OCEAN_SPACE_BANDS,
    OCEAN_SPACE_BLEND_WIDTH,
    OCEAN_SPACE_UPDATE_INTERVAL,
    OCEAN_SPACE_VISUAL_SMOOTH_SECONDS,
    ocean_space_debug_samples,
    ocean_space_state,
)


def main() -> int:
    errors: list[str] = []
    band_ids = [str(band.band_id) for band in OCEAN_SPACE_BANDS]
    if len(OCEAN_SPACE_BANDS) < 5:
        errors.append("expected-at-least-five-ocean-space-bands")
    if len(set(band_ids)) != len(band_ids):
        errors.append("duplicate-ocean-space-band-id")
    starts = [float(band.distance_min) for band in OCEAN_SPACE_BANDS]
    if starts != sorted(starts):
        errors.append("ocean-space-bands-not-sorted")
    if band_ids[0] != "safe_core_sea":
        errors.append("first-band-not-safe-core-sea")
    if band_ids[-1] != "deep_ocean_space":
        errors.append("last-band-not-deep-ocean-space")
    if not (3000.0 <= float(OCEAN_SPACE_BLEND_WIDTH) <= 8000.0):
        errors.append("blend-width-not-gradual")
    if float(OCEAN_SPACE_VISUAL_SMOOTH_SECONDS) < 18.0:
        errors.append("visual-smoothing-too-fast")
    if float(OCEAN_SPACE_UPDATE_INTERVAL) < 0.20:
        errors.append("update-interval-too-hot")

    near = ocean_space_state(0.0, 0.0)
    far = ocean_space_state(145000.0, 16420.0)
    if near.band_id != "safe_core_sea":
        errors.append("near-origin-state-not-safe")
    if far.band_id != "deep_ocean_space":
        errors.append("far-state-not-deep-ocean-space")
    if far.entity_scale_multiplier <= near.entity_scale_multiplier:
        errors.append("far-entities-not-larger")
    if far.entity_rarity_multiplier <= near.entity_rarity_multiplier:
        errors.append("far-entities-not-rarer")
    if far.signal_spacing <= near.signal_spacing:
        errors.append("far-signals-not-spaced-out")

    main_py = (ROOT / "main.py").read_text(encoding="utf-8")
    required_tokens = (
        "HOLOCORE_OCEAN_SPACE_SMOKE",
        "ocean_space_state_for_position",
        "_setup_ocean_space_ambient",
        "_update_ocean_space_effects",
        "_ocean_space_smoke_setup",
        "OCEAN-SPACE DISCOVERED",
        "HOLOCORE_OCEAN_SPACE_SCREENSHOT",
    )
    for token in required_tokens:
        if token not in main_py:
            errors.append(f"missing-main-token:{token}")
    if "__pycache__" in main_py:
        errors.append("main-mentions-cache-artifact")

    report = {
        "schema": 1,
        "kind": "holocore_ocean_space_validation",
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "band_ids": band_ids,
        "blend_width": OCEAN_SPACE_BLEND_WIDTH,
        "visual_smooth_seconds": OCEAN_SPACE_VISUAL_SMOOTH_SECONDS,
        "update_interval": OCEAN_SPACE_UPDATE_INTERVAL,
        "samples": ocean_space_debug_samples(),
    }
    print(json.dumps(report, indent=2))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
