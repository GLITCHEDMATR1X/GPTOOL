"""Biome-specific HoloCore archive turtle entity for Archive Ruins Reef."""
from __future__ import annotations

import math
import random
from typing import Callable

from panda3d.core import NodePath, Vec3, Vec4

from assets.entities.holo_biome_entity_primitives import make_ellipsoid, make_orbit_loop, make_polyline, make_ribbon, set_entity_root_defaults, stable_seed

ARCHIVE_TURTLE_SPAWN_CHANCE = 0.045
ARCHIVE_TURTLE_HEIGHT_OFFSET = 12.0
ARCHIVE_TURTLE_HEIGHT_VARIANCE = 9.0
ARCHIVE_TURTLE_MIN_DISTANCE_FROM_HUB = 900.0
ARCHIVE_TURTLE_UPDATE_INTERVAL = 1.0 / 12.0
ARCHIVE_TURTLE_HEIGHT_TIERS = (5.0, 12.0, 21.0)
ARCHIVE_TURTLE_BEHAVIOR = "archive_sentinel_pause_and_scan"


class HoloArchiveTurtleMob:
    """Slow archive guardian with shell glyph lines and soft paddle motion."""

    def __init__(self, seed: int = 0, surface_height_offset: float = ARCHIVE_TURTLE_HEIGHT_OFFSET) -> None:
        self.seed = int(seed) & 0xFFFFFFFF
        self.surface_height_offset = float(surface_height_offset)
        self.rng = random.Random(self.seed)
        self.root: NodePath | None = None
        self.body_root: NodePath | None = None
        self.paddles: list[NodePath] = []
        self.glyph_nodes: list[NodePath] = []
        self._base_pos = Vec3(0, 0, 0)
        self._scan_phase = self.rng.uniform(0.0, math.tau)

    def build(self, parent: NodePath, pos: Vec3, scale: float = 1.0, heading: float = 0.0) -> "HoloArchiveTurtleMob":
        self._base_pos = Vec3(pos)
        root = parent.attachNewNode("holo_archive_turtle_mob")
        set_entity_root_defaults(root)
        root.setPos(pos)
        root.setH(heading)
        root.setScale(scale)
        self.root = root
        body_root = root.attachNewNode("archive_turtle_body_root")
        self.body_root = body_root
        shell = make_ellipsoid("archive_turtle_shell", 3.9, 5.2, 1.15, Vec4(1.0, 0.66, 0.26, 0.38), Vec4(0.22, 0.95, 1.0, 0.40), stacks=7, slices=22)
        shell.reparentTo(body_root)
        shell.setZ(0.28)
        head = make_ellipsoid("archive_turtle_head", 1.0, 1.45, 0.72, Vec4(0.18, 0.92, 1.0, 0.38), Vec4(1.0, 0.82, 0.36, 0.34), stacks=5, slices=14)
        head.reparentTo(body_root)
        head.setPos(0, 5.0, 0.10)
        for idx, (x, y, rbase) in enumerate(((-3.2, 2.2, -25), (3.2, 2.2, 25), (-3.0, -2.4, 25), (3.0, -2.4, -25))):
            paddle = make_ribbon(f"archive_turtle_paddle_{idx}", 3.5, 1.35, Vec4(0.16, 0.86, 1.0, 0.30), Vec4(1.0, 0.66, 0.26, 0.14), steps=10, phase=self.rng.random() * math.tau, twist=0.4)
            paddle.reparentTo(body_root)
            paddle.setPos(x, y, -0.25)
            paddle.setH(rbase)
            self.paddles.append(paddle)
        for gy in (-1.6, 0.0, 1.6):
            glyph = make_polyline("archive_turtle_shell_glyph", [(-2.1, gy, 1.18), (-0.6, gy + 0.6, 1.34), (0.7, gy - 0.4, 1.34), (2.1, gy, 1.18)], Vec4(0.20, 0.95, 1.0, 0.48), 0.95)
            glyph.reparentTo(body_root)
            self.glyph_nodes.append(glyph)
        archive_halo = make_orbit_loop("archive_turtle_memory_halo", 5.7, 4.4, 1.42, Vec4(0.18, 0.95, 1.0, 0.36), segments=44, thickness=0.88, wobble=0.10)
        archive_halo.reparentTo(body_root)
        self.glyph_nodes.append(archive_halo)
        scan_ring = make_orbit_loop("archive_turtle_scan_ring", 8.2, 6.6, -0.55, Vec4(1.0, 0.72, 0.26, 0.28), segments=54, thickness=0.75, wobble=0.06)
        scan_ring.reparentTo(root)
        self.glyph_nodes.append(scan_ring)
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
        phase = (self.seed % 1709) * 0.007
        scan = max(0.0, math.sin(t * 0.31 + self._scan_phase)) ** 6
        drift_gate = 1.0 - scan * 0.82
        self.root.setPos(self._base_pos + Vec3(math.sin(t * 0.075 + phase) * 1.4 * drift_gate, math.cos(t * 0.068 + phase) * 1.1 * drift_gate, math.sin(t * 0.24 + phase) * 0.55 + scan * 0.85))
        self.root.setH(self.root.getH() + 0.018 * math.sin(t * 0.17 + phase) + scan * 0.22)
        if self.body_root is not None and not self.body_root.isEmpty():
            self.body_root.setR(math.sin(t * 0.45 + phase) * 1.6)
            self.body_root.setP(scan * 3.2)
        for idx, paddle in enumerate(self.paddles):
            if not paddle.isEmpty():
                paddle.setP(math.sin(t * 0.78 + phase + idx * 0.65) * (5.0 + drift_gate * 7.0))
        for idx, glyph in enumerate(self.glyph_nodes):
            if not glyph.isEmpty():
                glyph.setH(glyph.getH() + 0.10 + scan * (0.55 + idx * 0.08))
                glyph.setColorScale(1.0, 1.0, 1.0, 0.42 + scan * 0.38 + 0.08 * math.sin(t + idx))

    def set_visibility_alpha(self, alpha: float) -> None:
        if self.root is not None and not self.root.isEmpty():
            self.root.setColorScale(1.0, 1.0, 1.0, max(0.0, min(1.0, float(alpha))))

    def destroy(self) -> None:
        if self.root is not None and not self.root.isEmpty():
            self.root.removeNode()
        self.root = None


def stable_archive_turtle_seed(chunk_key: tuple[int, int], salt: int = 0xA2C417E1) -> int:
    return stable_seed(chunk_key, salt)
