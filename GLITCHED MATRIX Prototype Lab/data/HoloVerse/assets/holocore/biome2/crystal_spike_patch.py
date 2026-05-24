"""
Drop-in flora/natural object: crystal spike patch.

Third Dimension 2 / biome2 object. It follows the hierarchy density rule:
    hierarchy 0: crystal_reed baseline
    hierarchy 1: large_crystal_formation, 25% less than hierarchy 0
    hierarchy 2: crystal_spike_patch, 25% less than hierarchy 1

This object is intentionally ground-hugging: it scatters small crystal shards
across a patch and samples the terrain surface for every shard so the cluster
conforms to the streamed sonar terrain without floating gaps.
"""
from __future__ import annotations

import math
from random import Random
from typing import Callable

from panda3d.core import LineSegs, NodePath, TransparencyAttrib


SURFACE_OBJECT = {
    "id": "crystal_spike_patch",
    "weight": 1.0,
    "hierarchy": 2,
    "local_density": 1.0,
    "min_distance_from_hub": 470.0,
    # Wide patches look best on readable ground. Individual spikes still sample
    # the surface, but avoiding steeper zones keeps the patch from looking noisy.
    "max_slope": 0.56,
}


_PALETTES = [
    (0.22, 1.00, 0.94, 0.58),  # aqua shards
    (0.92, 0.38, 1.00, 0.62),  # violet shards
    (0.40, 0.66, 1.00, 0.58),  # blue shards
    (0.88, 1.00, 0.32, 0.52),  # lime shards
    (1.00, 0.50, 0.78, 0.55),  # rose shards
    (1.00, 0.84, 0.28, 0.48),  # gold shards
]


def _pick_color(rng: Random, alpha_scale: float = 1.0) -> tuple[float, float, float, float]:
    base = _PALETTES[int(rng.random() * len(_PALETTES)) % len(_PALETTES)]
    drift = 0.72 + rng.random() * 0.38
    return (
        min(1.0, base[0] * drift),
        min(1.0, base[1] * drift),
        min(1.0, base[2] * drift),
        max(0.10, min(0.80, base[3] * alpha_scale)),
    )


def _edge(lines: LineSegs, a: tuple[float, float, float], b: tuple[float, float, float]) -> None:
    lines.moveTo(*a)
    lines.drawTo(*b)


def _poly(radius: float, sides: int, z: float, twist: float, squash: float) -> list[tuple[float, float, float]]:
    points: list[tuple[float, float, float]] = []
    for i in range(sides):
        angle = twist + math.tau * i / sides
        points.append((math.cos(angle) * radius, math.sin(angle) * radius * squash, z))
    return points


def _draw_low_spike(lines: LineSegs, rng: Random, radius: float, height: float, sides: int) -> None:
    twist = rng.uniform(0.0, math.tau)
    squash = rng.uniform(0.72, 1.28)
    base = _poly(radius, sides, 0.0, twist, squash)
    mid = _poly(radius * rng.uniform(0.36, 0.58), sides, height * rng.uniform(0.34, 0.58), twist + rng.uniform(-0.16, 0.16), squash)
    apex = (rng.uniform(-0.22, 0.22) * radius, rng.uniform(-0.22, 0.22) * radius, height)

    for i in range(sides):
        lines.setColor(*_pick_color(rng, 0.56))
        _edge(lines, base[i], base[(i + 1) % sides])
        lines.setColor(*_pick_color(rng, 0.44))
        _edge(lines, base[i], mid[i])
        lines.setColor(*_pick_color(rng, 0.76))
        _edge(lines, mid[i], apex)

    # A few crossed data-edges help the patch read like crystalline growth.
    for i in range(0, sides, 2):
        lines.setColor(*_pick_color(rng, 0.34))
        _edge(lines, base[i], mid[(i + 1) % sides])


def _draw_ground_trace(parent: NodePath, rng: Random, patch_radius_x: float, patch_radius_y: float) -> None:
    traces = LineSegs("crystal_spike_patch_ground_traces")
    traces.setThickness(rng.uniform(1.1, 1.8))
    rings = rng.randint(2, 4)
    for ring in range(rings):
        sides = rng.randint(5, 8)
        radius_x = patch_radius_x * rng.uniform(0.28, 0.92)
        radius_y = patch_radius_y * rng.uniform(0.28, 0.92)
        twist = rng.uniform(0.0, math.tau)
        pts: list[tuple[float, float, float]] = []
        for i in range(sides):
            angle = twist + math.tau * i / sides
            pts.append((math.cos(angle) * radius_x, math.sin(angle) * radius_y, 0.04 + ring * 0.015))
        for i in range(sides):
            traces.setColor(*_pick_color(rng, 0.24))
            _edge(traces, pts[i], pts[(i + 1) % sides])
    node = parent.attachNewNode(traces.create())
    node.setLightOff()
    node.setTransparency(TransparencyAttrib.MAlpha)
    node.setBin("transparent", 7)


def build(parent: NodePath, x: float, y: float, z: float, rng: Random, metadata: dict) -> NodePath:
    """Build a low, wide patch of surface-conforming crystal spikes."""
    root = parent.attachNewNode("flora_crystal_spike_patch")
    root.setPos(x, y, z)
    root.setH(rng.uniform(0.0, 360.0))
    root.setPythonTag("animated_surface_object", True)
    root.setPythonTag("flow_phase", rng.uniform(0.0, math.tau))
    root.setPythonTag("flow_amplitude", rng.uniform(0.03, 0.12))
    root.setPythonTag("flow_rate", rng.uniform(0.025, 0.055))

    surface_z_at: Callable[[float, float], float] | None = metadata.get("surface_z_at")
    if not callable(surface_z_at):
        surface_z_at = lambda sx, sy: z  # noqa: E731 - compact fallback for drop-in contract

    patch_radius_x = rng.uniform(18.0, 34.0)
    patch_radius_y = rng.uniform(12.0, 28.0)
    _draw_ground_trace(root, rng, patch_radius_x, patch_radius_y)

    spike_count = rng.randint(13, 24)
    for index in range(spike_count):
        # Elliptical random placement biased slightly toward the patch center.
        angle = rng.uniform(0.0, math.tau)
        radial = math.sqrt(rng.random())
        ox = math.cos(angle) * patch_radius_x * radial
        oy = math.sin(angle) * patch_radius_y * radial
        wx = x + ox
        wy = y + oy
        local_z = surface_z_at(wx, wy) - z

        radius = rng.uniform(0.9, 2.7) * (1.25 if index < 3 else 1.0)
        height = rng.uniform(2.6, 8.8) * (1.45 if index < 3 else 1.0)
        sides = rng.randint(3, 6)
        lines = LineSegs("crystal_spike_patch_low_spike")
        lines.setThickness(rng.uniform(1.0, 2.2))
        _draw_low_spike(lines, rng, radius, height, sides)
        spike = root.attachNewNode(lines.create())
        spike.setPos(ox, oy, local_z + 0.025)
        spike.setH(rng.uniform(0.0, 360.0))
        spike.setP(rng.uniform(-3.5, 3.5))
        spike.setR(rng.uniform(-3.5, 3.5))
        spike.setLightOff()
        spike.setTransparency(TransparencyAttrib.MAlpha)
        spike.setBin("transparent", 8)

    root.setTransparency(TransparencyAttrib.MAlpha)
    root.setBin("transparent", 8)
    return root
