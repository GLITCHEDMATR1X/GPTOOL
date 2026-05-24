"""Validate HoloCore terrain footing across automatic biome bands.

This smoke test is intentionally small and deterministic. It proves that the
controller no longer treats the distant sonar terrain as visual-only after the
player travels far enough to trigger the next biome layer.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from panda3d.core import Vec3  # noqa: E402
from dimensions.outer_flat_world import FlatOuterWorldAdapter  # noqa: E402
from world_grid import BIOME_BLEND_WIDTH, BIOME_DISTANCE_STRIDE, FLAT_WORLD_RADIUS, sonar_height_at  # noqa: E402


def main() -> int:
    adapter = FlatOuterWorldAdapter(floor_z=-0.10)
    samples: list[dict] = []
    errors: list[str] = []

    distances = [
        0.0,
        FLAT_WORLD_RADIUS - 5.0,
        FLAT_WORLD_RADIUS + 5.0,
        FLAT_WORLD_RADIUS + BIOME_DISTANCE_STRIDE - BIOME_BLEND_WIDTH - 5.0,
        FLAT_WORLD_RADIUS + BIOME_DISTANCE_STRIDE - 2.0,
        FLAT_WORLD_RADIUS + BIOME_DISTANCE_STRIDE + 2.0,
        FLAT_WORLD_RADIUS + BIOME_DISTANCE_STRIDE * 2.0 + 18.0,
    ]
    headings = [0.0, math.pi * 0.25, math.pi * 0.5, math.pi, math.pi * 1.35]

    for distance in distances:
        for heading in headings:
            x = math.cos(heading) * distance
            y = math.sin(heading) * distance
            expected = sonar_height_at(x, y)
            pos = Vec3(x, y, -999.0)
            clamped = adapter.clamp_position(pos)
            actual = float(clamped.z)
            delta = abs(actual - expected)
            sample = {
                "distance": round(distance, 3),
                "heading": round(heading, 4),
                "x": round(x, 3),
                "y": round(y, 3),
                "expected_ground_z": round(expected, 6),
                "clamped_z": round(actual, 6),
                "delta": round(delta, 8),
            }
            samples.append(sample)
            if delta > 0.0001:
                errors.append(f"ground-mismatch:{sample}")
            if distance > FLAT_WORLD_RADIUS + BIOME_DISTANCE_STRIDE - 10.0 and math.isclose(actual, 0.0, abs_tol=0.0001):
                errors.append(f"distant-band-still-flat:{sample}")

    report = {
        "schema": 1,
        "kind": "holocore_terrain_collision_smoke",
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "sample_count": len(samples),
        "samples": samples,
    }
    out = ROOT / "logs" / "holocore_terrain_collision_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
