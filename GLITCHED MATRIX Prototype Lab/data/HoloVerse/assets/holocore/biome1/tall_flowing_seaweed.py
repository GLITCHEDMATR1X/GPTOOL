"""
Drop-in flora object: tall flowing holographic seaweed.

Any future file in assets/biome1/ can expose the same SURFACE_OBJECT metadata and
build(parent, x, y, z, rng, metadata) function to join the surface placer.
"""
from __future__ import annotations

import math
from random import Random

from panda3d.core import LineSegs, NodePath, TransparencyAttrib


SURFACE_OBJECT = {
    "id": "tall_flowing_seaweed",
    "weight": 1.0,
    "hierarchy": 0,
    "local_density": 1.0,
    "min_distance_from_hub": 400.0,
    # Seaweed can grow on mild slopes, but avoid steep canyon/ridge faces for now.
    "max_slope": 0.62,
}


_PALETTES = [
    (0.20, 1.00, 0.82, 0.68),  # sea-glass green
    (0.12, 0.78, 1.00, 0.64),  # cyan
    (0.72, 0.95, 0.28, 0.60),  # algae yellow-green
    (0.90, 0.36, 1.00, 0.58),  # violet-magenta
    (0.25, 1.00, 0.45, 0.62),  # electric green
]


def _color(rng: Random) -> tuple[float, float, float, float]:
    base = _PALETTES[int(rng.random() * len(_PALETTES)) % len(_PALETTES)]
    # Small per-instance drift keeps the field alive without heavy material work.
    drift = 0.82 + rng.random() * 0.28
    return (
        min(1.0, base[0] * drift),
        min(1.0, base[1] * drift),
        min(1.0, base[2] * drift),
        base[3],
    )


def build(parent: NodePath, x: float, y: float, z: float, rng: Random, metadata: dict) -> NodePath:
    """Build a small cluster anchored exactly at the sampled surface point."""
    root = parent.attachNewNode("flora_tall_flowing_seaweed")
    root.setPos(x, y, z)
    root.setH(rng.uniform(0.0, 360.0))
    root.setPythonTag("animated_surface_object", True)
    root.setPythonTag("flow_phase", rng.uniform(0.0, math.tau))
    root.setPythonTag("flow_amplitude", rng.uniform(1.2, 3.4))
    root.setPythonTag("flow_rate", rng.uniform(0.16, 0.31))

    cluster = LineSegs("seaweed_cluster_lines")
    cluster.setThickness(rng.uniform(2.0, 3.4))

    blade_count = rng.randint(4, 8)
    height_base = rng.uniform(11.0, 26.0)
    for blade in range(blade_count):
        angle = (math.tau * blade / max(1, blade_count)) + rng.uniform(-0.45, 0.45)
        radius = rng.uniform(0.0, 2.1)
        base_x = math.cos(angle) * radius
        base_y = math.sin(angle) * radius
        height = height_base * rng.uniform(0.72, 1.22)
        lean = rng.uniform(1.5, 5.2)
        curl = rng.uniform(-1.0, 1.0)
        cluster.setColor(*_color(rng))
        cluster.moveTo(base_x, base_y, 0.0)
        segments = 6
        for i in range(1, segments + 1):
            t = i / segments
            wave = math.sin(t * math.pi * 1.15 + curl) * lean * t
            taper = 1.0 - t * 0.25
            px = base_x + math.cos(angle + 1.55) * wave * taper
            py = base_y + math.sin(angle + 1.55) * wave * taper
            pz = height * t
            cluster.drawTo(px, py, pz)

    node = root.attachNewNode(cluster.create())
    node.setLightOff()
    node.setTransparency(TransparencyAttrib.MAlpha)
    node.setBin("transparent", 8)
    return root
