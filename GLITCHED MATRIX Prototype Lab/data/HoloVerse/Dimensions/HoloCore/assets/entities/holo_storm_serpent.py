"""High-ascent HoloCore storm serpent encounter entity."""
from __future__ import annotations

import math
import random
from typing import Callable

from panda3d.core import NodePath, Vec3, Vec4

from assets.entities.holo_biome_entity_primitives import (
    make_ellipsoid,
    make_orbit_loop,
    make_polyline,
    set_entity_root_defaults,
    stable_seed,
)

STORM_SERPENT_MIN_ALTITUDE = 4450.0
STORM_SERPENT_UPDATE_INTERVAL = 1.0 / 12.0
STORM_SERPENT_BEHAVIOR = "cathedral_column_coil_warning_flash_then_vertical_dash"
STORM_SERPENT_CONTACT_RADIUS = 58.0
STORM_SERPENT_SEGMENT_COUNT = 16
STORM_SERPENT_WARNING_RING_COUNT = 5


class HoloStormSerpentMob:
    """Segmented high-layer serpent with sparse warning-charge motion."""

    def __init__(self, seed: int = 0, surface_height_offset: float = 0.0) -> None:
        self.seed = int(seed) & 0xFFFFFFFF
        self.surface_height_offset = float(surface_height_offset)
        self.rng = random.Random(self.seed)
        self.root: NodePath | None = None
        self.body_root: NodePath | None = None
        self.segment_nodes: list[NodePath] = []
        self.arc_nodes: list[NodePath] = []
        self.spine_nodes: list[NodePath] = []
        self.eye_nodes: list[NodePath] = []
        self._base_pos = Vec3(0, 0, 0)
        self._charge_phase = self.rng.random() * math.tau
        self._alpha = 1.0
        self.contact_radius = STORM_SERPENT_CONTACT_RADIUS

    def build(self, parent: NodePath, pos: Vec3, scale: float = 1.0, heading: float = 0.0) -> "HoloStormSerpentMob":
        self._base_pos = Vec3(pos)
        root = parent.attachNewNode("holo_storm_serpent_mob")
        set_entity_root_defaults(root)
        root.setPos(pos)
        root.setH(heading)
        root.setScale(scale)
        self.root = root
        body_root = root.attachNewNode("storm_serpent_body_root")
        self.body_root = body_root
        for idx in range(STORM_SERPENT_SEGMENT_COUNT):
            t = idx / max(1, STORM_SERPENT_SEGMENT_COUNT - 1)
            seg = make_ellipsoid(
                f"storm_serpent_segment_{idx}",
                1.85 * (1.0 - t * 0.42),
                2.75 * (1.0 - t * 0.24),
                1.25 * (1.0 - t * 0.28),
                Vec4(0.26, 0.82, 1.0, 0.40),
                Vec4(1.0, 0.18, 0.58, 0.30),
                stacks=5,
                slices=16,
            )
            seg.reparentTo(body_root)
            coil_x = math.sin(t * math.tau * 1.55) * (2.8 + t * 2.0)
            coil_z = math.cos(t * math.tau * 1.05) * (1.2 + t * 1.6)
            seg.setPos(coil_x, -idx * 3.95, coil_z)
            seg.setH(math.sin(t * math.tau * 1.3) * 16.0)
            self.segment_nodes.append(seg)
        head = make_ellipsoid(
            "storm_serpent_head",
            2.85,
            3.95,
            1.75,
            Vec4(0.72, 0.96, 1.0, 0.50),
            Vec4(1.0, 0.20, 0.58, 0.38),
            stacks=6,
            slices=20,
        )
        head.reparentTo(body_root)
        head.setPos(0.0, 4.4, 0.2)
        self.segment_nodes.append(head)
        for side, sign in (("left", -1.0), ("right", 1.0)):
            eye = make_ellipsoid(
                f"storm_serpent_{side}_warning_eye",
                0.28,
                0.16,
                0.28,
                Vec4(1.0, 0.20, 0.62, 0.90),
                Vec4(0.70, 0.96, 1.0, 0.52),
                stacks=4,
                slices=10,
            )
            eye.reparentTo(head)
            eye.setPos(sign * 0.95, 2.14, 0.54)
            self.eye_nodes.append(eye)
            horn = make_polyline(
                f"storm_serpent_{side}_current_horn",
                [(sign * 0.72, 2.0, 1.0), (sign * 1.7, 3.8, 2.15), (sign * 2.7, 5.1, 1.45)],
                Vec4(0.86, 0.98, 1.0, 0.46),
                1.0,
            )
            horn.reparentTo(head)
            self.arc_nodes.append(horn)
        for idx in range(STORM_SERPENT_WARNING_RING_COUNT):
            radius = 4.4 + idx * 2.35
            ring = make_orbit_loop(
                f"storm_serpent_warning_ring_{idx}",
                radius,
                radius * (0.58 + idx * 0.035),
                -0.8 + idx * 0.45,
                Vec4(1.0, 0.18, 0.62, 0.32 - idx * 0.028),
                segments=52,
                thickness=0.9,
                wobble=0.20,
            )
            ring.reparentTo(body_root)
            ring.setP(66.0 + idx * 5.0)
            self.arc_nodes.append(ring)
        for idx, side in enumerate((-1.0, 1.0, -0.45, 0.45, -1.35, 1.35)):
            arc = make_polyline(
                f"storm_serpent_electric_barbel_{idx}",
                [(0.0, 3.1, 0.18), (side * 2.2, 6.4, 1.05), (side * 3.9, 10.8, -0.45)],
                Vec4(0.86, 0.98, 1.0, 0.52),
                1.05,
            )
            arc.reparentTo(body_root)
            self.arc_nodes.append(arc)
        for idx in range(4):
            spine = make_polyline(
                f"storm_serpent_tail_lightning_spine_{idx}",
                [(0.0, -8.0 - idx * 7.5, 0.0), (1.5 - idx * 0.7, -13.0 - idx * 8.0, 1.7), (-1.7 + idx * 0.55, -18.0 - idx * 8.0, -0.9)],
                Vec4(1.0, 0.28, 0.68, 0.34),
                0.92,
            )
            spine.reparentTo(body_root)
            self.spine_nodes.append(spine)
        self.set_visibility_alpha(1.0)
        return self

    def update_surface_lock(self, surface_height_at: Callable[[float, float], float]) -> None:
        return None

    def update_pose(self, time_value: float) -> None:
        if self.root is None or self.root.isEmpty():
            return
        t = float(time_value or 0.0)
        phase = (self.seed % 3323) * 0.007
        charge = max(0.0, math.sin(t * 0.255 + self._charge_phase)) ** 10
        warning = max(0.0, math.sin(t * 0.255 + self._charge_phase - 0.75)) ** 6
        coil = t * 0.072 + phase
        self.root.setPos(self._base_pos + Vec3(math.sin(coil) * (38.0 + charge * 34.0), math.cos(coil * 0.66) * (26.0 + charge * 20.0), math.sin(t * 0.17 + phase) * 32.0 + charge * 74.0))
        self.root.setH(self.root.getH() + 0.026 + charge * 2.8)
        self.root.setP(math.sin(t * 0.15 + phase) * 13.0 + charge * 28.0)
        if self.body_root is not None and not self.body_root.isEmpty():
            self.body_root.setR(math.sin(t * 0.43 + phase) * 18.0 + charge * 12.0)
        for idx, seg in enumerate(self.segment_nodes):
            if not seg.isEmpty():
                seg.setX(math.sin(t * 0.74 + phase + idx * 0.50) * (1.2 + idx * 0.18) + charge * math.sin(idx) * 0.9)
                seg.setZ(seg.getZ() + math.sin(t * 0.34 + phase + idx * 0.38) * 0.035)
                seg.setR(math.sin(t * 0.58 + idx) * 9.5 + charge * 7.0)
        for idx, node in enumerate(self.arc_nodes):
            if not node.isEmpty():
                node.setH(node.getH() + 0.48 + warning * 2.2 + charge * 8.0 + idx * 0.06)
                node.setScale(1.0 + warning * 0.13 + charge * 0.28)
                node.setColorScale(1.0, 1.0, 1.0, self._alpha * (0.20 + warning * 0.34 + charge * 0.68 + 0.10 * math.sin(t * 4.8 + idx)))
        for idx, node in enumerate(self.spine_nodes):
            if not node.isEmpty():
                node.setH(node.getH() - 0.18 - charge * 0.9)
                node.setColorScale(1.0, 1.0, 1.0, self._alpha * (0.24 + warning * 0.24 + charge * 0.36))
        for idx, node in enumerate(self.eye_nodes):
            if not node.isEmpty():
                pulse = 0.85 + warning * 0.30 + charge * 0.55
                node.setScale(pulse)
                node.setColorScale(1.0, 1.0, 1.0, self._alpha * min(1.0, 0.55 + warning * 0.30 + charge * 0.42))

    def set_visibility_alpha(self, alpha: float) -> None:
        self._alpha = max(0.0, min(1.0, float(alpha)))
        if self.root is not None and not self.root.isEmpty():
            self.root.setColorScale(1.0, 1.0, 1.0, self._alpha)

    def destroy(self) -> None:
        if self.root is not None and not self.root.isEmpty():
            self.root.removeNode()
        self.root = None


def stable_storm_serpent_seed(chunk_key: tuple[int, int], salt: int = 0x57E4FEA7) -> int:
    return stable_seed(chunk_key, salt)
