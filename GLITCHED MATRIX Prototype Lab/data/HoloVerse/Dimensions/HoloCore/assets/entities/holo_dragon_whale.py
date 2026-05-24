"""High-ascent HoloCore dragon whale encounter entity."""
from __future__ import annotations

import math
import random
from typing import Callable

from panda3d.core import NodePath, Vec3, Vec4

from assets.entities.holo_biome_entity_primitives import (
    make_ellipsoid,
    make_orbit_loop,
    make_polyline,
    make_ribbon,
    set_entity_root_defaults,
    stable_seed,
)

DRAGON_WHALE_MIN_ALTITUDE = 5600.0
DRAGON_WHALE_UPDATE_INTERVAL = 1.0 / 10.0
DRAGON_WHALE_BEHAVIOR = "cathedral_slow_breach_sonar_with_shadow_escorts"
DRAGON_WHALE_CONTACT_RADIUS = 82.0
DRAGON_WHALE_MASSIVE_SHADOW_COUNT = 3
DRAGON_WHALE_SONAR_LOOP_COUNT = 7


class HoloDragonWhaleMob:
    """Huge gentle-looking whale silhouette; contact triggers vessel rescue."""

    def __init__(self, seed: int = 0, surface_height_offset: float = 0.0) -> None:
        self.seed = int(seed) & 0xFFFFFFFF
        self.surface_height_offset = float(surface_height_offset)
        self.rng = random.Random(self.seed)
        self.root: NodePath | None = None
        self.body_root: NodePath | None = None
        self.fin_nodes: list[NodePath] = []
        self.signal_nodes: list[NodePath] = []
        self.shadow_nodes: list[NodePath] = []
        self.eye_nodes: list[NodePath] = []
        self._base_pos = Vec3(0, 0, 0)
        self._alpha = 1.0
        self.contact_radius = DRAGON_WHALE_CONTACT_RADIUS

    def build(self, parent: NodePath, pos: Vec3, scale: float = 1.0, heading: float = 0.0) -> "HoloDragonWhaleMob":
        self._base_pos = Vec3(pos)
        root = parent.attachNewNode("holo_dragon_whale_mob")
        set_entity_root_defaults(root)
        root.setPos(pos)
        root.setH(heading)
        root.setScale(scale)
        self.root = root
        body_root = root.attachNewNode("dragon_whale_body_root")
        self.body_root = body_root

        # Very faint oversized lobes make the animal read as a distant leviathan
        # without adding heavy mesh detail or full-screen particle effects.
        for idx in range(DRAGON_WHALE_MASSIVE_SHADOW_COUNT):
            shadow = make_ellipsoid(
                f"dragon_whale_far_shadow_lobe_{idx}",
                7.4 + idx * 2.2,
                22.0 + idx * 6.0,
                1.05 + idx * 0.22,
                Vec4(0.06, 0.14, 0.30, 0.075),
                Vec4(0.38, 0.10, 0.30, 0.045),
                stacks=5,
                slices=22,
            )
            shadow.reparentTo(root)
            shadow.setPos((-1.0 + idx) * 4.2, -7.0 - idx * 7.0, -2.8 - idx * 1.0)
            shadow.setH(4.0 - idx * 8.0)
            shadow.setP(2.0 + idx * 1.2)
            self.shadow_nodes.append(shadow)

        body = make_ellipsoid(
            "dragon_whale_broad_body",
            6.6,
            18.8,
            2.8,
            Vec4(0.14, 0.46, 0.82, 0.42),
            Vec4(0.90, 0.26, 0.78, 0.32),
            stacks=8,
            slices=32,
        )
        body.reparentTo(body_root)
        body.setP(-2.0)
        head = make_ellipsoid(
            "dragon_whale_soft_head",
            4.9,
            6.8,
            2.35,
            Vec4(0.55, 0.86, 1.0, 0.40),
            Vec4(1.0, 0.52, 0.88, 0.27),
            stacks=7,
            slices=28,
        )
        head.reparentTo(body_root)
        head.setPos(0.0, 15.4, 0.2)
        for side, sign in (("left", -1.0), ("right", 1.0)):
            eye = make_ellipsoid(
                f"dragon_whale_{side}_deep_eye",
                0.38,
                0.18,
                0.38,
                Vec4(1.0, 0.62, 0.94, 0.80),
                Vec4(0.45, 0.95, 1.0, 0.52),
                stacks=4,
                slices=10,
            )
            eye.reparentTo(head)
            eye.setPos(sign * 1.55, 3.52, 0.52)
            self.eye_nodes.append(eye)
        tail = make_ribbon(
            "dragon_whale_long_tail_fluke",
            22.0,
            8.8,
            Vec4(0.42, 0.86, 1.0, 0.28),
            Vec4(1.0, 0.36, 0.88, 0.18),
            steps=20,
            phase=self.rng.random() * math.tau,
            twist=0.58,
        )
        tail.reparentTo(body_root)
        tail.setPos(0.0, -19.2, -0.25)
        tail.setP(86.0)
        self.fin_nodes.append(tail)
        for side, sign in (("left", -1.0), ("right", 1.0)):
            fin = make_ribbon(
                f"dragon_whale_{side}_wing_fin",
                17.0,
                6.8,
                Vec4(0.32, 0.92, 1.0, 0.27),
                Vec4(0.96, 0.44, 0.86, 0.12),
                steps=18,
                phase=self.rng.random() * math.tau,
                twist=0.86 * sign,
            )
            fin.reparentTo(body_root)
            fin.setPos(sign * 6.2, 2.4, -0.72)
            fin.setH(sign * 82.0)
            fin.setR(sign * 10.0)
            self.fin_nodes.append(fin)
        for idx in range(DRAGON_WHALE_SONAR_LOOP_COUNT):
            y = -12.0 + idx * 5.0
            rib = make_orbit_loop(
                f"dragon_whale_sonar_rib_{idx}",
                7.0 - idx * 0.42,
                2.7,
                0.0,
                Vec4(0.60, 0.94, 1.0, 0.18),
                segments=46,
                thickness=0.70,
                wobble=0.08,
            )
            rib.reparentTo(body_root)
            rib.setPos(0, y, 0)
            rib.setP(88.0)
            self.signal_nodes.append(rib)
        for idx in range(7):
            offset = -3.6 + idx * 1.2
            trail = make_polyline(
                f"dragon_whale_back_frond_{idx}",
                [(offset, -11.0, 2.7), (offset * 0.7, -4.5, 4.6), (offset * 0.42, 3.5, 2.8)],
                Vec4(0.94, 0.36, 0.86, 0.25),
                0.95,
            )
            trail.reparentTo(body_root)
            self.signal_nodes.append(trail)
        self.set_visibility_alpha(1.0)
        return self

    def update_surface_lock(self, surface_height_at: Callable[[float, float], float]) -> None:
        # High-ascent leviathans are volumetric, not ground/surface locked.
        return None

    def update_pose(self, time_value: float) -> None:
        if self.root is None or self.root.isEmpty():
            return
        t = float(time_value or 0.0)
        phase = (self.seed % 2029) * 0.009
        drift = t * 0.036 + phase
        breath = 0.5 + 0.5 * math.sin(t * 0.13 + phase)
        breach = max(0.0, math.sin(t * 0.092 + phase)) ** 5
        self.root.setPos(self._base_pos + Vec3(math.sin(drift) * 32.0, math.cos(drift * 0.62) * 20.0, math.sin(t * 0.12 + phase) * 24.0 + breach * 44.0))
        self.root.setH(self.root.getH() + 0.012 * math.sin(t * 0.08 + phase))
        self.root.setP(-4.0 + math.sin(t * 0.07 + phase) * 4.5 + breach * 8.0)
        if self.body_root is not None and not self.body_root.isEmpty():
            self.body_root.setR(math.sin(t * 0.15 + phase) * 4.6)
            self.body_root.setSz(1.0 + breath * 0.018)
        for idx, node in enumerate(self.shadow_nodes):
            if not node.isEmpty():
                node.setH(node.getH() + 0.004 + idx * 0.002)
                node.setColorScale(1.0, 1.0, 1.0, self._alpha * (0.34 + idx * 0.10 + breath * 0.12))
        for idx, node in enumerate(self.fin_nodes):
            if not node.isEmpty():
                node.setR(math.sin(t * 0.34 + phase + idx) * 9.0)
                node.setP(node.getP() + math.sin(t * 0.22 + idx) * 0.035)
        for idx, node in enumerate(self.eye_nodes):
            if not node.isEmpty():
                pulse = 0.76 + 0.24 * math.sin(t * 0.82 + phase + idx)
                node.setScale(pulse)
                node.setColorScale(1.0, 1.0, 1.0, self._alpha * (0.62 + pulse * 0.30))
        for idx, node in enumerate(self.signal_nodes):
            if not node.isEmpty():
                sonar = 1.0 + 0.075 * math.sin(t * 0.36 + phase + idx * 0.55)
                node.setScale(sonar)
                node.setH(node.getH() + 0.07 + idx * 0.018)
                node.setColorScale(1.0, 1.0, 1.0, self._alpha * (0.30 + 0.22 * math.sin(t * 0.48 + idx + phase) + breach * 0.18))

    def set_visibility_alpha(self, alpha: float) -> None:
        self._alpha = max(0.0, min(1.0, float(alpha)))
        if self.root is not None and not self.root.isEmpty():
            self.root.setColorScale(1.0, 1.0, 1.0, self._alpha)

    def destroy(self) -> None:
        if self.root is not None and not self.root.isEmpty():
            self.root.removeNode()
        self.root = None


def stable_dragon_whale_seed(chunk_key: tuple[int, int], salt: int = 0xD6A90A1E) -> int:
    return stable_seed(chunk_key, salt)
