"""Biome-specific HoloCore storm eel entity for Storm Current Trench."""
from __future__ import annotations

import math
import random
from typing import Callable

from panda3d.core import NodePath, Vec3, Vec4

from assets.entities.holo_biome_entity_primitives import make_ellipsoid, make_orbit_loop, make_polyline, make_ribbon, make_wavy_spine, set_entity_root_defaults, stable_seed

STORM_EEL_SPAWN_CHANCE = 0.06
STORM_EEL_HEIGHT_OFFSET = 34.0
STORM_EEL_HEIGHT_VARIANCE = 20.0
STORM_EEL_MIN_DISTANCE_FROM_HUB = 920.0
STORM_EEL_UPDATE_INTERVAL = 1.0 / 24.0
STORM_EEL_HEIGHT_TIERS = (20.0, 34.0, 52.0)
STORM_EEL_BEHAVIOR = "charged_vertical_dash"


class HoloStormEelMob:
    """Electric ribbon eel with a wavy spine and short lightning feelers."""

    def __init__(self, seed: int = 0, surface_height_offset: float = STORM_EEL_HEIGHT_OFFSET) -> None:
        self.seed = int(seed) & 0xFFFFFFFF
        self.surface_height_offset = float(surface_height_offset)
        self.rng = random.Random(self.seed)
        self.root: NodePath | None = None
        self.body_root: NodePath | None = None
        self.ribbon_nodes: list[NodePath] = []
        self.charge_nodes: list[NodePath] = []
        self._base_pos = Vec3(0, 0, 0)
        self._dash_phase = self.rng.uniform(0.0, math.tau)

    def build(self, parent: NodePath, pos: Vec3, scale: float = 1.0, heading: float = 0.0) -> "HoloStormEelMob":
        self._base_pos = Vec3(pos)
        root = parent.attachNewNode("holo_storm_eel_mob")
        set_entity_root_defaults(root)
        root.setPos(pos)
        root.setH(heading)
        root.setScale(scale)
        self.root = root
        body_root = root.attachNewNode("storm_eel_body_root")
        self.body_root = body_root
        body = make_ribbon("storm_eel_body_ribbon", 12.5, 1.75, Vec4(0.32, 0.76, 1.0, 0.48), Vec4(1.0, 0.10, 0.52, 0.28), steps=22, phase=self.rng.random() * math.tau, twist=1.3)
        body.reparentTo(body_root)
        self.ribbon_nodes.append(body)
        spine = make_wavy_spine("storm_eel_spine", 13.0, Vec4(0.78, 0.96, 1.0, 0.66), steps=20, phase=self.rng.random() * math.tau, radius=0.95, thickness=1.25)
        spine.reparentTo(body_root)
        head = make_ellipsoid("storm_eel_head", 0.88, 1.25, 0.65, Vec4(0.72, 0.92, 1.0, 0.52), Vec4(1.0, 0.16, 0.54, 0.34), stacks=5, slices=14)
        head.reparentTo(body_root)
        head.setPos(0, 6.6, 0.0)
        for idx, side in enumerate((-1.0, 1.0, -0.55, 0.55)):
            feeler = make_polyline(
                f"storm_eel_feeler_{idx}",
                [(0.0, 5.8, 0.0), (side * 0.9, 7.1, 0.4), (side * 1.5, 8.6, -0.2)],
                Vec4(1.0, 0.18, 0.56, 0.52),
                1.05,
            )
            feeler.reparentTo(body_root)
            self.ribbon_nodes.append(feeler)
        charge_ring = make_orbit_loop("storm_eel_charge_ring", 3.2, 2.2, -0.12, Vec4(1.0, 0.16, 0.58, 0.40), segments=36, thickness=0.95, wobble=0.14)
        charge_ring.reparentTo(body_root)
        charge_ring.setP(74.0)
        self.charge_nodes.append(charge_ring)
        for idx, z in enumerate((-3.8, 0.0, 3.8)):
            arc = make_polyline(
                f"storm_eel_charge_arc_{idx}",
                [(-1.2, z - 0.8, 0.5), (0.6, z + 0.2, -0.25), (-0.4, z + 1.1, 0.35), (1.4, z + 1.9, -0.1)],
                Vec4(0.84, 0.98, 1.0, 0.46),
                0.88,
            )
            arc.reparentTo(body_root)
            self.charge_nodes.append(arc)
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
        phase = (self.seed % 2027) * 0.011
        dash = max(0.0, math.sin(t * 0.88 + self._dash_phase)) ** 10
        coil = t * 0.34 + phase
        self.root.setPos(self._base_pos + Vec3(math.sin(coil) * (2.4 + dash * 5.0), math.cos(coil * 0.78) * (2.0 + dash * 3.2), math.sin(t * 1.05 + phase) * 1.6 + dash * 9.0))
        self.root.setH(self.root.getH() + 0.20 * math.sin(t * 0.62 + phase) + dash * 3.2)
        self.root.setP(-8.0 + dash * 22.0 + math.cos(t * 0.8 + phase) * 4.0)
        if self.body_root is not None and not self.body_root.isEmpty():
            self.body_root.setR(math.sin(t * 1.8 + phase) * (8.0 + dash * 12.0))
            self.body_root.setP(math.cos(t * 1.2 + phase) * 5.5 + dash * 7.0)
        for idx, node in enumerate(self.ribbon_nodes):
            if not node.isEmpty():
                node.setColorScale(1.0, 1.0, 1.0, 0.62 + 0.20 * math.sin(t * 4.2 + phase + idx) + dash * 0.35)
        for idx, node in enumerate(self.charge_nodes):
            if not node.isEmpty():
                node.setH(node.getH() + 1.0 + dash * 5.5 + idx * 0.15)
                node.setColorScale(1.0, 1.0, 1.0, 0.22 + dash * 0.72 + 0.15 * math.sin(t * 9.0 + idx))

    def set_visibility_alpha(self, alpha: float) -> None:
        if self.root is not None and not self.root.isEmpty():
            self.root.setColorScale(1.0, 1.0, 1.0, max(0.0, min(1.0, float(alpha))))

    def destroy(self) -> None:
        if self.root is not None and not self.root.isEmpty():
            self.root.removeNode()
        self.root = None


def stable_storm_eel_seed(chunk_key: tuple[int, int], salt: int = 0x5702E11) -> int:
    return stable_seed(chunk_key, salt)
