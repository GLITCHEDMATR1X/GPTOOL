"""Biome-specific HoloCore glass fish entity for Mirror Glass Shoals."""
from __future__ import annotations

import math
import random
from typing import Callable

from panda3d.core import NodePath, Vec3, Vec4

from assets.entities.holo_biome_entity_primitives import make_ellipsoid, make_orbit_loop, make_polyline, make_ribbon, set_entity_root_defaults, stable_seed

GLASS_FISH_SPAWN_CHANCE = 0.09
GLASS_FISH_HEIGHT_OFFSET = 18.0
GLASS_FISH_HEIGHT_VARIANCE = 15.0
GLASS_FISH_MIN_DISTANCE_FROM_HUB = 820.0
GLASS_FISH_UPDATE_INTERVAL = 1.0 / 24.0
GLASS_FISH_HEIGHT_TIERS = (9.0, 18.0, 29.0)
GLASS_FISH_BEHAVIOR = "mirror_shoal_flash_and_reform"


class HoloGlassFishSwarm:
    """Tiny reflective fish cluster; built as one chunk-owned entity."""

    def __init__(self, seed: int = 0, surface_height_offset: float = GLASS_FISH_HEIGHT_OFFSET) -> None:
        self.seed = int(seed) & 0xFFFFFFFF
        self.surface_height_offset = float(surface_height_offset)
        self.rng = random.Random(self.seed)
        self.root: NodePath | None = None
        self.fish_roots: list[NodePath] = []
        self.glint_nodes: list[NodePath] = []
        self._home_offsets: list[Vec3] = []
        self._base_pos = Vec3(0, 0, 0)
        self._scatter_phase = self.rng.uniform(0.0, math.tau)

    def build(self, parent: NodePath, pos: Vec3, scale: float = 1.0, heading: float = 0.0) -> "HoloGlassFishSwarm":
        self._base_pos = Vec3(pos)
        root = parent.attachNewNode("holo_glass_fish_swarm")
        set_entity_root_defaults(root)
        root.setPos(pos)
        root.setH(heading)
        root.setScale(scale)
        self.root = root
        count = self.rng.randint(7, 11)
        for idx in range(count):
            fish = root.attachNewNode(f"glass_fish_{idx}")
            home = Vec3(self.rng.uniform(-7.0, 7.0), self.rng.uniform(-6.5, 6.5), self.rng.uniform(-3.0, 4.5))
            fish.setPos(home)
            self._home_offsets.append(home)
            fish.setH(self.rng.uniform(0, 360))
            body = make_ellipsoid("glass_fish_body", 0.55, 1.35, 0.34, Vec4(0.72, 0.96, 1.0, 0.36), Vec4(1.0, 1.0, 1.0, 0.58), stacks=5, slices=16)
            body.reparentTo(fish)
            tail = make_ribbon("glass_fish_tail", 1.8, 0.85, Vec4(0.62, 0.90, 1.0, 0.30), Vec4(1.0, 1.0, 1.0, 0.10), steps=8, phase=self.rng.random() * math.tau, twist=0.6)
            tail.reparentTo(fish)
            tail.setPos(0.0, -1.25, 0.0)
            tail.setH(180.0)
            glint = make_polyline("glass_fish_glint", [(-0.35, 0.2, 0.22), (0.25, 0.75, 0.30), (0.46, 1.1, 0.18)], Vec4(1.0, 1.0, 1.0, 0.52), 0.7)
            glint.reparentTo(fish)
            self.glint_nodes.append(glint)
            self.fish_roots.append(fish)
        mirror_orbit = make_orbit_loop("glass_fish_mirror_shoal_orbit", 8.2, 5.6, 0.0, Vec4(0.76, 0.98, 1.0, 0.30), segments=48, thickness=0.82, wobble=0.11)
        mirror_orbit.reparentTo(root)
        mirror_orbit.setP(8.0)
        self.glint_nodes.append(mirror_orbit)
        return self

    def update_surface_lock(self, surface_height_at: Callable[[float, float], float]) -> None:
        if self.root is None or self.root.isEmpty():
            return
        pos = self.root.getPos()
        self._base_pos.setZ(float(surface_height_at(pos.x, pos.y)) + self.surface_height_offset)

    def update_pose(self, time_value: float) -> None:
        if self.root is None or self.root.isEmpty():
            return
        t = float(time_value or 0.0)
        phase = (self.seed % 1499) * 0.009
        shoal_orbit = t * 0.24 + phase
        flash = max(0.0, math.sin(t * 1.7 + self._scatter_phase)) ** 8
        self.root.setPos(self._base_pos + Vec3(math.sin(shoal_orbit) * 3.2, math.cos(shoal_orbit * 1.2) * 2.4, math.sin(t * 0.62 + phase) * 1.25 + flash * 2.8))
        self.root.setH(self.root.getH() + 0.16 * math.sin(t * 0.5 + phase) + flash * 0.9)
        for idx, fish in enumerate(self.fish_roots):
            if fish.isEmpty():
                continue
            home = self._home_offsets[idx] if idx < len(self._home_offsets) else Vec3(0, 0, 0)
            fan = 1.0 + flash * 1.9
            fish.setPos(Vec3(home.x * fan + math.sin(t * 1.1 + idx) * 0.45, home.y * fan + math.cos(t * 0.9 + idx) * 0.35, home.z + math.sin(t * 1.3 + phase + idx) * 0.48))
            fish.setH(heading := (math.sin(t * 0.6 + idx) * 18.0 + flash * 45.0))
            fish.setR(math.sin(t * 2.0 + idx * 0.7 + phase) * 5.5)
        for idx, glint in enumerate(self.glint_nodes):
            if not glint.isEmpty():
                glint.setColorScale(1.0, 1.0, 1.0, 0.38 + flash * 0.55 + 0.12 * math.sin(t * 2.8 + idx))
                glint.setH(glint.getH() + 0.15 + flash * 0.8)

    def set_visibility_alpha(self, alpha: float) -> None:
        if self.root is not None and not self.root.isEmpty():
            self.root.setColorScale(1.0, 1.0, 1.0, max(0.0, min(1.0, float(alpha))))

    def destroy(self) -> None:
        if self.root is not None and not self.root.isEmpty():
            self.root.removeNode()
        self.root = None


def stable_glass_fish_seed(chunk_key: tuple[int, int], salt: int = 0x61455F15) -> int:
    return stable_seed(chunk_key, salt)
