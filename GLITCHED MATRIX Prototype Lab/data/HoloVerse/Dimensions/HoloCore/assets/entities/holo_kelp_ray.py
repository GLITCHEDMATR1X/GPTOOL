"""Biome-specific HoloCore kelp ray entity for Abyssal Kelp Forest."""
from __future__ import annotations

import math
import random
from typing import Callable

from panda3d.core import NodePath, Vec3, Vec4

from assets.entities.holo_biome_entity_primitives import make_ellipsoid, make_orbit_loop, make_polyline, make_ribbon, set_entity_root_defaults, stable_seed

KELP_RAY_SPAWN_CHANCE = 0.07
KELP_RAY_HEIGHT_OFFSET = 26.0
KELP_RAY_HEIGHT_VARIANCE = 18.0
KELP_RAY_MIN_DISTANCE_FROM_HUB = 860.0
KELP_RAY_UPDATE_INTERVAL = 1.0 / 16.0
KELP_RAY_HEIGHT_TIERS = (18.0, 30.0, 44.0)
KELP_RAY_BEHAVIOR = "canopy_glide_and_breach"


class HoloKelpRayMob:
    """Chunk-owned ray that glides between kelp columns with slow fin pulses."""

    def __init__(self, seed: int = 0, surface_height_offset: float = KELP_RAY_HEIGHT_OFFSET) -> None:
        self.seed = int(seed) & 0xFFFFFFFF
        self.surface_height_offset = float(surface_height_offset)
        self.rng = random.Random(self.seed)
        self.root: NodePath | None = None
        self.body_root: NodePath | None = None
        self.fin_nodes: list[NodePath] = []
        self.trail_nodes: list[NodePath] = []
        self.special_nodes: list[NodePath] = []
        self._base_pos = Vec3(0, 0, 0)
        self._breach_gate = self.rng.uniform(0.35, 0.95)
        self._alpha = 1.0

    def build(self, parent: NodePath, pos: Vec3, scale: float = 1.0, heading: float = 0.0) -> "HoloKelpRayMob":
        self._base_pos = Vec3(pos)
        root = parent.attachNewNode("holo_kelp_ray_mob")
        set_entity_root_defaults(root)
        root.setPos(pos)
        root.setH(heading)
        root.setScale(scale)
        self.root = root

        body_root = root.attachNewNode("kelp_ray_body_root")
        self.body_root = body_root
        body = make_ellipsoid("kelp_ray_body", 3.7, 6.2, 0.82, Vec4(0.08, 0.86, 0.68, 0.46), Vec4(0.58, 1.0, 0.88, 0.62), stacks=7, slices=26)
        body.reparentTo(body_root)
        body.setP(7.0)
        for side, sign in (("left", -1.0), ("right", 1.0)):
            fin = make_ribbon(f"kelp_ray_{side}_wing", 8.6, 5.4, Vec4(0.06, 0.96, 0.68, 0.32), Vec4(0.30, 1.0, 0.78, 0.12), steps=14, phase=self.rng.random() * math.tau, twist=0.7 * sign)
            fin.reparentTo(body_root)
            fin.setPos(sign * 3.8, -0.3, -0.15)
            fin.setH(90.0 * sign)
            fin.setR(8.0 * sign)
            self.fin_nodes.append(fin)
        for idx in range(4):
            trail = make_polyline(
                f"kelp_ray_tail_trail_{idx}",
                [(0.0, -4.4 - idx * 0.7, -0.1), (math.sin(idx) * 0.8, -8.0 - idx * 1.7, -0.45), (math.cos(idx) * 1.4, -13.0 - idx, -0.3)],
                Vec4(0.34, 1.0, 0.82, 0.45),
                1.25,
            )
            trail.reparentTo(body_root)
            self.trail_nodes.append(trail)
        canopy_loop = make_orbit_loop("kelp_ray_canopy_sonar_loop", 6.8, 4.6, -0.52, Vec4(0.28, 1.0, 0.80, 0.34), segments=42, thickness=0.9, wobble=0.16)
        canopy_loop.reparentTo(body_root)
        canopy_loop.setP(5.0)
        self.special_nodes.append(canopy_loop)
        belly_signal = make_orbit_loop("kelp_ray_belly_signal", 2.0, 1.1, -0.76, Vec4(0.70, 1.0, 0.90, 0.44), segments=28, thickness=0.75, wobble=0.08)
        belly_signal.reparentTo(body_root)
        self.special_nodes.append(belly_signal)
        self.set_visibility_alpha(1.0)
        return self

    def update_surface_lock(self, surface_height_at: Callable[[float, float], float]) -> None:
        if self.root is None or self.root.isEmpty():
            return
        pos = self.root.getPos()
        target_z = float(surface_height_at(pos.x, pos.y)) + self.surface_height_offset
        self._base_pos.setZ(target_z)

    def update_pose(self, time_value: float) -> None:
        if self.root is None or self.root.isEmpty():
            return
        t = float(time_value or 0.0)
        phase = (self.seed % 997) * 0.013
        orbit = t * 0.115 + phase
        breach = max(0.0, math.sin(t * 0.29 + self._breach_gate)) ** 3
        slow_roll = math.sin(t * 0.42 + phase)
        self.root.setPos(self._base_pos + Vec3(math.sin(orbit) * 7.5, math.cos(orbit * 0.82) * 5.4, slow_roll * 2.2 + breach * 5.2))
        self.root.setH(self.root.getH() + 0.035 * math.sin(t * 0.25 + phase))
        self.root.setP(-3.0 + breach * 8.0 + slow_roll * 2.6)
        if self.body_root is not None and not self.body_root.isEmpty():
            self.body_root.setP(4.0 + slow_roll * 4.0 + breach * 2.0)
            self.body_root.setR(math.sin(t * 0.36 + phase) * 3.5)
        for idx, fin in enumerate(self.fin_nodes):
            if not fin.isEmpty():
                side_base = 9.0 if idx == 0 else -9.0
                fin.setR(side_base + math.sin(t * 1.18 + phase + idx) * 10.0 + breach * (4.0 if idx == 0 else -4.0))
        for idx, trail in enumerate(self.trail_nodes):
            if not trail.isEmpty():
                trail.setR(math.sin(t * 0.85 + phase + idx * 0.8) * 7.0)
                trail.setP(math.cos(t * 0.55 + idx) * 2.0)
        for idx, node in enumerate(self.special_nodes):
            if not node.isEmpty():
                node.setH(node.getH() + (0.35 + idx * 0.18))
                node.setColorScale(1.0, 1.0, 1.0, 0.52 + 0.25 * math.sin(t * 1.8 + phase + idx))

    def set_visibility_alpha(self, alpha: float) -> None:
        self._alpha = max(0.0, min(1.0, float(alpha)))
        if self.root is not None and not self.root.isEmpty():
            self.root.setColorScale(1.0, 1.0, 1.0, self._alpha)

    def destroy(self) -> None:
        if self.root is not None and not self.root.isEmpty():
            self.root.removeNode()
        self.root = None


def stable_kelp_ray_seed(chunk_key: tuple[int, int], salt: int = 0x4B315241) -> int:
    return stable_seed(chunk_key, salt)
