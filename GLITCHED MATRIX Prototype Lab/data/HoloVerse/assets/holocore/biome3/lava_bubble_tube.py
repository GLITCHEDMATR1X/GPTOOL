"""
Drop-in natural object: lava bubble tube.

First Dimension 3 / biome3 object. It places sparse lava-like holo tubes far
apart on the terrain surface and emits lightweight looping bubble particles.
Bubbles are prebuilt wire loops, not spawned/destroyed every frame, so this stays
friendly to streaming performance.
"""
from __future__ import annotations

import math
from random import Random
from typing import Callable

from panda3d.core import LineSegs, NodePath, TransparencyAttrib


SURFACE_OBJECT = {
    "id": "lava_bubble_tube",
    "weight": 1.0,
    "hierarchy": 0,
    # Sparse first-object density: creates big empty valleys between emitters.
    "local_density": 0.16,
    "min_distance_from_hub": 520.0,
    # Tubes prefer valley floors/gentler terrain so they never look detached.
    "max_slope": 0.52,
}


_TUBE_COLORS = [
    (1.00, 0.22, 0.06, 0.66),  # lava red-orange
    (1.00, 0.54, 0.08, 0.58),  # amber
    (0.95, 0.12, 0.82, 0.50),  # magenta heat
    (0.20, 0.92, 1.00, 0.42),  # cyan anomaly
]

_BUBBLE_COLORS = [
    (1.00, 0.28, 0.08, 0.46),
    (1.00, 0.72, 0.18, 0.42),
    (0.30, 1.00, 0.92, 0.38),
    (0.75, 0.25, 1.00, 0.42),
    (0.38, 0.64, 1.00, 0.40),
]


def _pick_color(rng: Random, palette, alpha_scale: float = 1.0) -> tuple[float, float, float, float]:
    base = palette[int(rng.random() * len(palette)) % len(palette)]
    drift = 0.78 + rng.random() * 0.28
    return (
        min(1.0, base[0] * drift),
        min(1.0, base[1] * drift),
        min(1.0, base[2] * drift),
        max(0.04, min(0.78, base[3] * alpha_scale)),
    )


def _edge(lines: LineSegs, a: tuple[float, float, float], b: tuple[float, float, float]) -> None:
    lines.moveTo(*a)
    lines.drawTo(*b)


def _poly(radius_x: float, radius_y: float, z: float, sides: int, twist: float) -> list[tuple[float, float, float]]:
    return [
        (math.cos(twist + math.tau * i / sides) * radius_x,
         math.sin(twist + math.tau * i / sides) * radius_y,
         z)
        for i in range(sides)
    ]


def _draw_tube_shell(parent: NodePath, rng: Random, height: float, radius: float) -> None:
    lines = LineSegs("lava_bubble_tube_wire_shell")
    lines.setThickness(rng.uniform(2.0, 3.4))
    sides = rng.randint(6, 9)
    levels = rng.randint(4, 6)
    twist = rng.uniform(0.0, math.tau)
    rings: list[list[tuple[float, float, float]]] = []
    for level in range(levels):
        t = level / max(1, levels - 1)
        z = height * t
        swell = 0.82 + math.sin(t * math.pi) * rng.uniform(0.16, 0.34)
        rx = radius * swell * rng.uniform(0.88, 1.12)
        ry = radius * swell * rng.uniform(0.78, 1.22)
        ring = _poly(rx, ry, z, sides, twist + t * rng.uniform(-0.38, 0.38))
        rings.append(ring)
        for i in range(sides):
            lines.setColor(*_pick_color(rng, _TUBE_COLORS, 0.56 + t * 0.24))
            _edge(lines, ring[i], ring[(i + 1) % sides])

    for level in range(levels - 1):
        for i in range(sides):
            if i % 2 == 0 or rng.random() < 0.58:
                lines.setColor(*_pick_color(rng, _TUBE_COLORS, 0.42))
                _edge(lines, rings[level][i], rings[level + 1][i])

    # Open vent ring at top.
    top_glow = _poly(radius * 1.16, radius * 0.95, height + 0.15, sides + 2, twist + 0.32)
    for i in range(len(top_glow)):
        lines.setColor(*_pick_color(rng, _TUBE_COLORS, 0.84))
        _edge(lines, top_glow[i], top_glow[(i + 1) % len(top_glow)])

    shell = parent.attachNewNode(lines.create())
    shell.setLightOff()
    shell.setTransparency(TransparencyAttrib.MAlpha)
    shell.setBin("transparent", 8)


def _draw_base_veins(parent: NodePath, rng: Random, surface_z_at: Callable[[float, float], float], base_x: float, base_y: float, base_z: float) -> None:
    veins = LineSegs("lava_bubble_tube_ground_veins")
    veins.setThickness(rng.uniform(1.2, 2.0))
    branches = rng.randint(4, 7)
    for branch in range(branches):
        angle = rng.uniform(0.0, math.tau)
        length = rng.uniform(16.0, 36.0)
        steps = rng.randint(3, 5)
        px = 0.0
        py = 0.0
        pz = 0.06
        veins.setColor(*_pick_color(rng, _TUBE_COLORS, 0.35))
        veins.moveTo(px, py, pz)
        for step in range(1, steps + 1):
            t = step / steps
            wobble = math.sin(t * math.pi * 1.4 + rng.random()) * rng.uniform(2.0, 5.0)
            lx = math.cos(angle) * length * t + math.cos(angle + math.pi * 0.5) * wobble
            ly = math.sin(angle) * length * t + math.sin(angle + math.pi * 0.5) * wobble
            lz = surface_z_at(base_x + lx, base_y + ly) - base_z + 0.08
            veins.setColor(*_pick_color(rng, _TUBE_COLORS, 0.22 + 0.18 * (1.0 - t)))
            veins.drawTo(lx, ly, lz)
    node = parent.attachNewNode(veins.create())
    node.setLightOff()
    node.setTransparency(TransparencyAttrib.MAlpha)
    node.setBin("transparent", 7)


def _draw_wire_bubble(parent: NodePath, rng: Random, radius: float) -> NodePath:
    lines = LineSegs("lava_bubble_particle_wire")
    lines.setThickness(rng.uniform(1.0, 1.8))
    color = _pick_color(rng, _BUBBLE_COLORS, 1.0)
    steps = 16
    # Three cheap great-circle loops make a readable bubble without a mesh sphere.
    for plane in range(3):
        lines.setColor(*color)
        for i in range(steps + 1):
            angle = math.tau * i / steps
            if plane == 0:
                p = (math.cos(angle) * radius, math.sin(angle) * radius, 0.0)
            elif plane == 1:
                p = (math.cos(angle) * radius, 0.0, math.sin(angle) * radius)
            else:
                p = (0.0, math.cos(angle) * radius, math.sin(angle) * radius)
            if i == 0:
                lines.moveTo(*p)
            else:
                lines.drawTo(*p)
    bubble = parent.attachNewNode(lines.create())
    bubble.setLightOff()
    bubble.setTransparency(TransparencyAttrib.MAlpha)
    bubble.setBin("transparent", 12)
    bubble.setPythonTag("bubble_base_color", color)
    return bubble


def build(parent: NodePath, x: float, y: float, z: float, rng: Random, metadata: dict) -> NodePath:
    """Build one sparse lava tube emitter with prebuilt rising/fading bubbles."""
    root = parent.attachNewNode("flora_lava_bubble_tube")
    root.setPos(x, y, z)
    root.setH(rng.uniform(0.0, 360.0))
    root.setTransparency(TransparencyAttrib.MAlpha)
    root.setBin("transparent", 9)
    root.setPythonTag("animated_surface_object", True)
    root.setPythonTag("bubble_emitter", True)
    root.setPythonTag("flow_phase", rng.uniform(0.0, math.tau))
    root.setPythonTag("flow_rate", rng.uniform(0.018, 0.038))

    surface_z_at = metadata.get("surface_z_at")
    if not callable(surface_z_at):
        surface_z_at = lambda sx, sy: z  # noqa: E731

    tube_count = rng.randint(1, 3)
    bubble_particles: list[NodePath] = []
    highest_vent = 0.0
    for tube_index in range(tube_count):
        angle = rng.uniform(0.0, math.tau)
        spread = rng.uniform(0.0, 14.0) if tube_count > 1 else 0.0
        ox = math.cos(angle) * spread
        oy = math.sin(angle) * spread
        local_z = surface_z_at(x + ox, y + oy) - z
        tube = root.attachNewNode(f"lava_tube_vent_{tube_index}")
        tube.setPos(ox, oy, local_z)
        tube.setH(rng.uniform(0.0, 360.0))
        height = rng.uniform(12.0, 28.0) * (1.18 if tube_index == 0 else 1.0)
        radius = rng.uniform(4.2, 8.8) * (1.10 if tube_index == 0 else 0.92)
        highest_vent = max(highest_vent, local_z + height)
        _draw_tube_shell(tube, rng, height, radius)

        # 3-5 bubbles per vent: lightweight and looped, no runtime spawning.
        for _ in range(rng.randint(3, 5)):
            bubble = _draw_wire_bubble(root, rng, rng.uniform(2.2, 7.8))
            bubble.setPythonTag("bubble_origin_x", ox + rng.uniform(-radius * 0.35, radius * 0.35))
            bubble.setPythonTag("bubble_origin_y", oy + rng.uniform(-radius * 0.35, radius * 0.35))
            bubble.setPythonTag("bubble_origin_z", local_z + height + rng.uniform(0.5, 3.0))
            bubble.setPythonTag("bubble_rise", rng.uniform(38.0, 92.0))
            bubble.setPythonTag("bubble_drift", rng.uniform(3.5, 14.0))
            bubble.setPythonTag("bubble_phase", rng.random())
            bubble.setPythonTag("bubble_rate", rng.uniform(0.018, 0.045))
            bubble.setPythonTag("bubble_spin", rng.uniform(-22.0, 22.0))
            bubble_particles.append(bubble)

    _draw_base_veins(root, rng, surface_z_at, x, y, z)
    root.setPythonTag("bubble_particles", bubble_particles)
    root.setPythonTag("bubble_emitter_height", highest_vent)
    return root
