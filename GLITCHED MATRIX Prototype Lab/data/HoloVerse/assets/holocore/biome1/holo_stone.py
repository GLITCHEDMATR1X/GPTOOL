"""
Drop-in natural object: holo stone.

Third biome1 hierarchy object. It uses sparse random wireframe 3D shapes that
read like holographic stones/crystals on the sonar terrain surface. The surface
placement system only attempts it after seaweed and neon weed bush fail to claim
the same candidate point, and hierarchy=2 makes it spawn 25% less than the
previous hierarchy family: 1.0 -> 0.75 -> 0.5625.
"""
from __future__ import annotations

import math
from random import Random

from panda3d.core import LineSegs, NodePath, TransparencyAttrib


SURFACE_OBJECT = {
    "id": "holo_stone",
    "weight": 1.0,
    "hierarchy": 2,
    # Uses the shared hierarchy rule: 0.75 ** 2 = 0.5625, or 25% less than bush.
    "local_density": 1.0,
    "min_distance_from_hub": 400.0,
    # Stones can sit in more rugged places than flora, but still avoid extreme faces.
    "max_slope": 0.88,
}


_PALETTES = [
    (0.10, 0.95, 1.00, 0.62),  # cyan
    (0.95, 0.24, 1.00, 0.58),  # magenta
    (0.42, 1.00, 0.22, 0.56),  # lime
    (1.00, 0.42, 0.12, 0.54),  # ember orange
    (0.34, 0.52, 1.00, 0.60),  # blue-violet
    (1.00, 0.95, 0.35, 0.50),  # yellow crystal
]


def _color(rng: Random) -> tuple[float, float, float, float]:
    base = _PALETTES[int(rng.random() * len(_PALETTES)) % len(_PALETTES)]
    drift = 0.78 + rng.random() * 0.30
    return (
        min(1.0, base[0] * drift),
        min(1.0, base[1] * drift),
        min(1.0, base[2] * drift),
        base[3],
    )


def _edge(lines: LineSegs, a: tuple[float, float, float], b: tuple[float, float, float]) -> None:
    lines.moveTo(*a)
    lines.drawTo(*b)


def _wire_box(lines: LineSegs, rng: Random, sx: float, sy: float, sz: float) -> None:
    hx = sx * 0.5
    hy = sy * 0.5
    z0 = 0.0
    z1 = sz
    pts = [
        (-hx, -hy, z0), (hx, -hy, z0), (hx, hy, z0), (-hx, hy, z0),
        (-hx, -hy, z1), (hx, -hy, z1), (hx, hy, z1), (-hx, hy, z1),
    ]
    for a, b in ((0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4), (0, 4), (1, 5), (2, 6), (3, 7)):
        lines.setColor(*_color(rng))
        _edge(lines, pts[a], pts[b])


def _wire_pyramid(lines: LineSegs, rng: Random, radius: float, height: float, sides: int) -> None:
    base = []
    for i in range(sides):
        angle = math.tau * i / sides
        base.append((math.cos(angle) * radius, math.sin(angle) * radius, 0.0))
    apex = (0.0, 0.0, height)
    for i in range(sides):
        lines.setColor(*_color(rng))
        _edge(lines, base[i], base[(i + 1) % sides])
        lines.setColor(*_color(rng))
        _edge(lines, base[i], apex)


def _wire_octahedron(lines: LineSegs, rng: Random, radius: float, height: float) -> None:
    center_z = height * 0.48
    top = (0.0, 0.0, height)
    bottom = (0.0, 0.0, 0.0)
    ring = [
        (radius, 0.0, center_z),
        (0.0, radius, center_z),
        (-radius, 0.0, center_z),
        (0.0, -radius, center_z),
    ]
    for i in range(4):
        a = ring[i]
        b = ring[(i + 1) % 4]
        lines.setColor(*_color(rng))
        _edge(lines, a, b)
        lines.setColor(*_color(rng))
        _edge(lines, a, top)
        lines.setColor(*_color(rng))
        _edge(lines, a, bottom)


def _wire_prism(lines: LineSegs, rng: Random, radius: float, height: float, sides: int) -> None:
    bottom = []
    top = []
    for i in range(sides):
        angle = math.tau * i / sides
        bottom.append((math.cos(angle) * radius, math.sin(angle) * radius, 0.0))
        top.append((math.cos(angle) * radius * rng.uniform(0.76, 1.08), math.sin(angle) * radius * rng.uniform(0.76, 1.08), height))
    for i in range(sides):
        lines.setColor(*_color(rng))
        _edge(lines, bottom[i], bottom[(i + 1) % sides])
        lines.setColor(*_color(rng))
        _edge(lines, top[i], top[(i + 1) % sides])
        lines.setColor(*_color(rng))
        _edge(lines, bottom[i], top[i])


def _wire_shard(lines: LineSegs, rng: Random, radius: float, height: float) -> None:
    # Uneven crystal shard: base stays on z=0, so it never floats above the terrain.
    sides = rng.randint(4, 6)
    base = []
    shoulder = []
    for i in range(sides):
        angle = math.tau * i / sides + rng.uniform(-0.13, 0.13)
        r = radius * rng.uniform(0.72, 1.18)
        base.append((math.cos(angle) * r, math.sin(angle) * r, 0.0))
        shoulder.append((math.cos(angle) * r * rng.uniform(0.38, 0.72), math.sin(angle) * r * rng.uniform(0.38, 0.72), height * rng.uniform(0.28, 0.58)))
    apex = (rng.uniform(-radius * 0.18, radius * 0.18), rng.uniform(-radius * 0.18, radius * 0.18), height)
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
    """Build one sparse wireframe holo stone cluster anchored to the sampled terrain."""
    root = parent.attachNewNode("flora_holo_stone")
    root.setPos(x, y, z)
    root.setH(rng.uniform(0.0, 360.0))

    line_thickness = rng.uniform(1.45, 2.45)

    shape_count = rng.randint(1, 3)
    for _ in range(shape_count):
        # Multiple stones in a candidate point read as one sparse natural cluster.
        offset_radius = rng.uniform(0.0, 5.8)
        offset_angle = rng.uniform(0.0, math.tau)
        ox = math.cos(offset_angle) * offset_radius
        oy = math.sin(offset_angle) * offset_radius
        size = rng.uniform(2.3, 6.8)
        height = rng.uniform(2.8, 10.4)

        # Temporarily draw the shape around origin, offsetting by wrapping helper calls
        # in simple translated coordinates through a local LineSegs transform would be
        # heavier than needed. Instead, create a small child per shape.
        local = LineSegs("holo_stone_local_shape")
        local.setThickness(line_thickness)
        kind = rng.choice(("box", "pyramid", "octa", "prism", "shard"))
        if kind == "box":
            _wire_box(local, rng, size * rng.uniform(0.72, 1.35), size * rng.uniform(0.72, 1.35), height)
        elif kind == "pyramid":
            _wire_pyramid(local, rng, size * 0.76, height, rng.randint(3, 6))
        elif kind == "octa":
            _wire_octahedron(local, rng, size * 0.72, height)
        elif kind == "prism":
            _wire_prism(local, rng, size * 0.62, height, rng.randint(5, 8))
        else:
            _wire_shard(local, rng, size * 0.70, height)

        shape_np = root.attachNewNode(local.create())
        shape_np.setPos(ox, oy, 0.0)
        shape_np.setH(rng.uniform(0.0, 360.0))
        shape_np.setLightOff()
        shape_np.setTransparency(TransparencyAttrib.MAlpha)
        shape_np.setBin("transparent", 10)

    root.setTransparency(TransparencyAttrib.MAlpha)
    root.setBin("transparent", 10)
    return root
