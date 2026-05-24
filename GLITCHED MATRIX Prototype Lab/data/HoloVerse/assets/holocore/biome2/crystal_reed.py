"""
Drop-in flora object: crystal reed.

First Dimension 2 / biome2 object. This keeps the same drop-in contract used by
biome1 files: SURFACE_OBJECT metadata + build(parent, x, y, z, rng, metadata).
"""
from __future__ import annotations

import math
from random import Random

from panda3d.core import LineSegs, NodePath, TransparencyAttrib


SURFACE_OBJECT = {
    "id": "crystal_reed",
    "weight": 1.0,
    "hierarchy": 0,
    "local_density": 1.0,
    "min_distance_from_hub": 400.0,
    # Crystal reeds are rigid and can tolerate a little more rugged ground.
    "max_slope": 0.76,
}


_PALETTES = [
    (0.70, 0.30, 1.00, 0.64),  # violet
    (0.16, 1.00, 0.82, 0.58),  # mint/cyan
    (0.95, 0.45, 1.00, 0.60),  # magenta prism
    (0.34, 0.62, 1.00, 0.62),  # blue crystal
    (1.00, 0.92, 0.35, 0.52),  # gold glint
]


def _color(rng: Random) -> tuple[float, float, float, float]:
    base = _PALETTES[int(rng.random() * len(_PALETTES)) % len(_PALETTES)]
    drift = 0.74 + rng.random() * 0.36
    return (
        min(1.0, base[0] * drift),
        min(1.0, base[1] * drift),
        min(1.0, base[2] * drift),
        base[3],
    )


def _edge(lines: LineSegs, a: tuple[float, float, float], b: tuple[float, float, float]) -> None:
    lines.moveTo(*a)
    lines.drawTo(*b)


def _draw_crystal_spike(lines: LineSegs, rng: Random, radius: float, height: float, sides: int) -> None:
    twist = rng.uniform(0.0, math.tau)
    base: list[tuple[float, float, float]] = []
    shoulder: list[tuple[float, float, float]] = []
    for i in range(sides):
        a = twist + math.tau * i / sides
        wobble = rng.uniform(0.82, 1.18)
        base.append((math.cos(a) * radius * wobble, math.sin(a) * radius * wobble, 0.0))
        shoulder.append((math.cos(a + 0.12) * radius * 0.54 * wobble, math.sin(a + 0.12) * radius * 0.54 * wobble, height * 0.70))
    apex = (rng.uniform(-0.45, 0.45), rng.uniform(-0.45, 0.45), height)

    for i in range(sides):
        ni = (i + 1) % sides
        lines.setColor(*_color(rng))
        _edge(lines, base[i], base[ni])
        lines.setColor(*_color(rng))
        _edge(lines, base[i], shoulder[i])
        lines.setColor(*_color(rng))
        _edge(lines, shoulder[i], shoulder[ni])
        lines.setColor(*_color(rng))
        _edge(lines, shoulder[i], apex)


def build(parent: NodePath, x: float, y: float, z: float, rng: Random, metadata: dict) -> NodePath:
    """Build a sparse cluster of tall angular crystal reeds anchored to terrain."""
    root = parent.attachNewNode("flora_crystal_reed")
    root.setPos(x, y, z)
    root.setH(rng.uniform(0.0, 360.0))
    root.setPythonTag("animated_surface_object", True)
    root.setPythonTag("flow_phase", rng.uniform(0.0, math.tau))
    root.setPythonTag("flow_amplitude", rng.uniform(0.18, 0.55))
    root.setPythonTag("flow_rate", rng.uniform(0.06, 0.12))

    cluster_count = rng.randint(3, 7)
    line_thickness = rng.uniform(1.6, 2.8)
    for _ in range(cluster_count):
        lines = LineSegs("crystal_reed_wire_spike")
        lines.setThickness(line_thickness)
        offset_radius = rng.uniform(0.0, 4.8)
        offset_angle = rng.uniform(0.0, math.tau)
        ox = math.cos(offset_angle) * offset_radius
        oy = math.sin(offset_angle) * offset_radius
        radius = rng.uniform(1.3, 3.8)
        height = rng.uniform(9.0, 22.0)
        sides = rng.randint(4, 7)
        _draw_crystal_spike(lines, rng, radius, height, sides)
        spike = root.attachNewNode(lines.create())
        spike.setPos(ox, oy, 0.0)
        spike.setH(rng.uniform(0.0, 360.0))
        spike.setLightOff()
        spike.setTransparency(TransparencyAttrib.MAlpha)
        spike.setBin("transparent", 8)

    root.setTransparency(TransparencyAttrib.MAlpha)
    root.setBin("transparent", 8)
    return root
