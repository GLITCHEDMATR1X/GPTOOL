"""
Drop-in flora/natural object: large crystal formation.

Second Dimension 2 / biome2 object. It follows the project hierarchy rule:
    hierarchy 0: crystal_reed baseline
    hierarchy 1: large_crystal_formation, 25% less spawn chance

The placement system claims candidate cells in hierarchy order, so these larger
formations only appear where crystal_reed did not already spawn.
"""
from __future__ import annotations

import math
from random import Random

from panda3d.core import LineSegs, NodePath, TransparencyAttrib


SURFACE_OBJECT = {
    "id": "large_crystal_formation",
    "weight": 1.0,
    "hierarchy": 1,
    "local_density": 1.0,
    "min_distance_from_hub": 470.0,
    # Keep large formations on gentler surfaces so they do not look like they are floating off steep slopes.
    "max_slope": 0.58,
}


_PALETTES = [
    (0.62, 0.18, 1.00, 0.70),  # violet core
    (0.10, 1.00, 0.86, 0.64),  # mint cyan
    (0.98, 0.30, 0.92, 0.68),  # magenta
    (0.24, 0.58, 1.00, 0.68),  # deep blue
    (1.00, 0.78, 0.22, 0.58),  # gold signal
    (0.74, 1.00, 0.36, 0.56),  # neon lime
]


def _pick_color(rng: Random, alpha_scale: float = 1.0) -> tuple[float, float, float, float]:
    base = _PALETTES[int(rng.random() * len(_PALETTES)) % len(_PALETTES)]
    drift = 0.72 + rng.random() * 0.38
    return (
        min(1.0, base[0] * drift),
        min(1.0, base[1] * drift),
        min(1.0, base[2] * drift),
        max(0.12, min(0.88, base[3] * alpha_scale)),
    )


def _edge(lines: LineSegs, a: tuple[float, float, float], b: tuple[float, float, float]) -> None:
    lines.moveTo(*a)
    lines.drawTo(*b)


def _polygon(radius: float, sides: int, z: float, twist: float, squash: float = 1.0) -> list[tuple[float, float, float]]:
    pts: list[tuple[float, float, float]] = []
    for i in range(sides):
        a = twist + math.tau * i / sides
        pts.append((math.cos(a) * radius, math.sin(a) * radius * squash, z))
    return pts


def _draw_prism(lines: LineSegs, rng: Random, radius: float, height: float, sides: int, lean: tuple[float, float]) -> None:
    twist = rng.uniform(0.0, math.tau)
    squash = rng.uniform(0.78, 1.22)
    base = _polygon(radius, sides, 0.0, twist, squash)
    mid = _polygon(radius * rng.uniform(0.56, 0.74), sides, height * rng.uniform(0.46, 0.64), twist + rng.uniform(-0.18, 0.18), squash)
    shoulder = _polygon(radius * rng.uniform(0.24, 0.38), sides, height * rng.uniform(0.74, 0.86), twist + rng.uniform(-0.26, 0.26), squash)
    apex = (lean[0], lean[1], height)

    for ring in (base, mid, shoulder):
        for i in range(len(ring)):
            lines.setColor(*_pick_color(rng, 0.86))
            _edge(lines, ring[i], ring[(i + 1) % len(ring)])

    for i in range(sides):
        lines.setColor(*_pick_color(rng, 0.76))
        _edge(lines, base[i], mid[i])
        lines.setColor(*_pick_color(rng, 0.76))
        _edge(lines, mid[i], shoulder[i])
        lines.setColor(*_pick_color(rng, 0.84))
        _edge(lines, shoulder[i], apex)

    # A couple of inner diagonals make the formation read as a data-crystal instead of plain boxes.
    for i in range(0, sides, 2):
        lines.setColor(*_pick_color(rng, 0.44))
        _edge(lines, base[i], shoulder[(i + 2) % sides])


def _draw_base_rings(parent: NodePath, rng: Random) -> None:
    ring_count = rng.randint(2, 4)
    for ring_index in range(ring_count):
        lines = LineSegs(f"large_crystal_base_ring_{ring_index}")
        lines.setThickness(rng.uniform(1.8, 3.0))
        sides = rng.randint(5, 8)
        radius = rng.uniform(7.0, 15.0) + ring_index * rng.uniform(1.5, 3.0)
        z = 0.05 + ring_index * 0.03
        pts = _polygon(radius, sides, z, rng.uniform(0.0, math.tau), rng.uniform(0.72, 1.15))
        for i in range(sides):
            lines.setColor(*_pick_color(rng, 0.46))
            _edge(lines, pts[i], pts[(i + 1) % sides])
        ring = parent.attachNewNode(lines.create())
        ring.setLightOff()
        ring.setTransparency(TransparencyAttrib.MAlpha)
        ring.setBin("transparent", 8)


def build(parent: NodePath, x: float, y: float, z: float, rng: Random, metadata: dict) -> NodePath:
    """Build a larger sparse crystal formation, anchored to the sampled surface."""
    root = parent.attachNewNode("flora_large_crystal_formation")
    root.setPos(x, y, z)
    root.setH(rng.uniform(0.0, 360.0))
    root.setPythonTag("animated_surface_object", True)
    root.setPythonTag("flow_phase", rng.uniform(0.0, math.tau))
    root.setPythonTag("flow_amplitude", rng.uniform(0.08, 0.24))
    root.setPythonTag("flow_rate", rng.uniform(0.035, 0.075))

    _draw_base_rings(root, rng)

    spire_count = rng.randint(4, 8)
    main_index = rng.randint(0, spire_count - 1)
    for i in range(spire_count):
        lines = LineSegs("large_crystal_formation_wire_prism")
        lines.setThickness(rng.uniform(2.0, 3.8) if i == main_index else rng.uniform(1.5, 2.8))
        radius = rng.uniform(2.5, 6.8) * (1.32 if i == main_index else 1.0)
        height = rng.uniform(16.0, 34.0) * (1.34 if i == main_index else 1.0)
        sides = rng.randint(4, 7)
        offset_radius = rng.uniform(0.0, 11.5)
        offset_angle = rng.uniform(0.0, math.tau)
        ox = math.cos(offset_angle) * offset_radius
        oy = math.sin(offset_angle) * offset_radius
        lean = (rng.uniform(-1.2, 1.2), rng.uniform(-1.2, 1.2))
        _draw_prism(lines, rng, radius, height, sides, lean)
        spire = root.attachNewNode(lines.create())
        spire.setPos(ox, oy, 0.0)
        spire.setH(rng.uniform(0.0, 360.0))
        spire.setLightOff()
        spire.setTransparency(TransparencyAttrib.MAlpha)
        spire.setBin("transparent", 8)

    root.setTransparency(TransparencyAttrib.MAlpha)
    root.setBin("transparent", 8)
    return root
