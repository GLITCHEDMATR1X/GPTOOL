"""
Drop-in flora object: neon weed bush.

Second biome1 hierarchy object. It is shorter and wider than tall seaweed, and
surface_placement.py only attempts it on candidate points that earlier hierarchy
objects did not occupy. Its hierarchy=1 makes it attempt at 25% lower density
than the first flora family.
"""
from __future__ import annotations

import math
from random import Random

from panda3d.core import LineSegs, NodePath, TransparencyAttrib


SURFACE_OBJECT = {
    "id": "neon_weed_bush",
    "weight": 1.0,
    "hierarchy": 1,
    # 1.0 here still becomes 0.75 after the hierarchy rule.
    "local_density": 1.0,
    "min_distance_from_hub": 400.0,
    # Bushes sit lower and wider, so allow slightly more rugged areas than tall seaweed.
    "max_slope": 0.74,
}


_PALETTES = [
    (0.00, 0.95, 1.00, 0.58),  # electric cyan
    (0.52, 1.00, 0.18, 0.56),  # neon lime
    (1.00, 0.32, 0.92, 0.54),  # neon magenta
    (0.18, 0.56, 1.00, 0.58),  # vivid blue
    (1.00, 0.70, 0.15, 0.50),  # warm amber accent
]


def _color(rng: Random) -> tuple[float, float, float, float]:
    base = _PALETTES[int(rng.random() * len(_PALETTES)) % len(_PALETTES)]
    drift = 0.76 + rng.random() * 0.34
    return (
        min(1.0, base[0] * drift),
        min(1.0, base[1] * drift),
        min(1.0, base[2] * drift),
        base[3],
    )


def build(parent: NodePath, x: float, y: float, z: float, rng: Random, metadata: dict) -> NodePath:
    """Build a low, wide holographic bush anchored to the sampled surface point."""
    root = parent.attachNewNode("flora_neon_weed_bush")
    root.setPos(x, y, z)
    root.setH(rng.uniform(0.0, 360.0))
    root.setPythonTag("animated_surface_object", True)
    root.setPythonTag("flow_phase", rng.uniform(0.0, math.tau))
    root.setPythonTag("flow_amplitude", rng.uniform(0.45, 1.15))
    root.setPythonTag("flow_rate", rng.uniform(0.11, 0.22))

    bush = LineSegs("neon_weed_bush_lines")
    bush.setThickness(rng.uniform(2.1, 3.2))

    # Wide footprint, short height: reads as a neon weed clump beside taller seaweed.
    clump_count = rng.randint(10, 17)
    radius_base = rng.uniform(4.2, 8.4)
    height_base = rng.uniform(4.0, 9.2)
    center_color = _color(rng)

    # A small lower ring gives the bush width without needing solid geometry.
    ring_steps = 18
    bush.setColor(*center_color)
    first = True
    for i in range(ring_steps + 1):
        t = i / ring_steps
        angle = t * math.tau
        wobble = 0.78 + math.sin(angle * 3.0 + rng.random() * 0.25) * 0.08
        px = math.cos(angle) * radius_base * wobble
        py = math.sin(angle) * radius_base * wobble
        pz = rng.uniform(0.18, 0.75)
        if first:
            bush.moveTo(px, py, pz)
            first = False
        else:
            bush.drawTo(px, py, pz)

    for blade in range(clump_count):
        angle = rng.uniform(0.0, math.tau)
        base_radius = rng.uniform(0.0, radius_base * 0.42)
        base_x = math.cos(angle) * base_radius
        base_y = math.sin(angle) * base_radius
        spread = rng.uniform(radius_base * 0.36, radius_base * 1.05)
        height = height_base * rng.uniform(0.62, 1.16)
        curl = rng.uniform(-1.2, 1.2)
        bush.setColor(*_color(rng))
        bush.moveTo(base_x, base_y, 0.0)
        segments = 4
        for i in range(1, segments + 1):
            t = i / segments
            outward = spread * (math.sin(t * math.pi * 0.54) ** 0.85)
            sway = math.sin(t * math.pi * 1.45 + curl) * rng.uniform(0.35, 1.25) * t
            px = base_x + math.cos(angle) * outward + math.cos(angle + math.pi * 0.5) * sway
            py = base_y + math.sin(angle) * outward + math.sin(angle + math.pi * 0.5) * sway
            pz = height * math.sin(t * math.pi * 0.62)
            bush.drawTo(px, py, pz)

    # A few low cross-veins make the bush read as a clump rather than isolated stalks.
    vein_count = rng.randint(3, 6)
    for _ in range(vein_count):
        a0 = rng.uniform(0.0, math.tau)
        a1 = a0 + rng.uniform(1.4, 2.8)
        r0 = radius_base * rng.uniform(0.30, 0.90)
        r1 = radius_base * rng.uniform(0.30, 0.90)
        bush.setColor(*_color(rng))
        bush.moveTo(math.cos(a0) * r0, math.sin(a0) * r0, rng.uniform(0.5, 1.4))
        bush.drawTo(math.cos(a1) * r1, math.sin(a1) * r1, rng.uniform(0.5, 1.8))

    node = root.attachNewNode(bush.create())
    node.setLightOff()
    node.setTransparency(TransparencyAttrib.MAlpha)
    node.setBin("transparent", 9)
    return root
