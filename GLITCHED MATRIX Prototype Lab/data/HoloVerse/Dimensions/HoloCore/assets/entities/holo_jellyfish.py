"""Generated HoloCore jellyfish mob.

Preview import pass: lightweight, animated, generated Panda3D geometry only.
Jellyfish are chunk-owned world mobs with deterministic color/size variants.
They float above the sampled terrain surface and never bring preview rectangle/platform
geometry into the game.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Callable, Iterable

from panda3d.core import (
    AntialiasAttrib,
    Geom,
    GeomNode,
    GeomTriangles,
    GeomVertexData,
    GeomVertexFormat,
    GeomVertexWriter,
    LineSegs,
    NodePath,
    Point3,
    TransparencyAttrib,
    Vec3,
    Vec4,
)

JELLYFISH_SPAWN_CHANCE = 0.20
JELLYFISH_HEIGHT_OFFSET = 12.75
JELLYFISH_MIN_DISTANCE_FROM_HUB = 620.0

AQUA = Vec4(0.05, 0.98, 1.00, 0.52)
CYAN = Vec4(0.10, 0.78, 1.00, 0.54)
PALE = Vec4(0.86, 1.00, 1.00, 0.60)
TEAL = Vec4(0.10, 1.00, 0.72, 0.48)
VIOLET = Vec4(0.72, 0.34, 1.00, 0.46)
PINK = Vec4(1.00, 0.40, 0.88, 0.44)
GOLD = Vec4(1.00, 0.78, 0.28, 0.44)
WHITE_LINE = Vec4(0.88, 1.00, 1.00, 0.82)


@dataclass(frozen=True)
class JellyVariant:
    name: str
    scale: float
    bell_a: Vec4
    bell_b: Vec4
    tendril: Vec4
    seed_salt: int


JELLYFISH_VARIANTS = (
    JellyVariant("aqua_medium", 1.00, AQUA, PALE, Vec4(0.52, 1.00, 0.96, 0.76), 13),
    JellyVariant("violet_small", 0.68, VIOLET, PALE, Vec4(0.92, 0.58, 1.00, 0.72), 29),
    JellyVariant("rose_large", 1.42, PINK, PALE, Vec4(1.00, 0.62, 0.92, 0.70), 47),
    JellyVariant("gold_tiny", 0.52, GOLD, PALE, Vec4(1.00, 0.88, 0.52, 0.72), 61),
)


def stable_jellyfish_seed(chunk_key: tuple[int, int], salt: int = 0x4A311F15) -> int:
    cx, cy = int(chunk_key[0]), int(chunk_key[1])
    return ((cx * 83492791) ^ (cy * 2654435761) ^ int(salt)) & 0xFFFFFFFF


def lerp_color(a: Vec4, b: Vec4, t: float) -> Vec4:
    t = max(0.0, min(1.0, float(t)))
    return Vec4(a.x + (b.x - a.x) * t, a.y + (b.y - a.y) * t, a.z + (b.z - a.z) * t, a.w + (b.w - a.w) * t)


def make_geom(name: str, vertices: list[tuple[float, float, float]], faces: Iterable[tuple[int, int, int]], color: Vec4 | None = None, colors: list[Vec4] | None = None) -> NodePath:
    fmt = GeomVertexFormat.getV3c4()
    vdata = GeomVertexData(name, fmt, Geom.UHStatic)
    vdata.setNumRows(len(vertices))
    vw = GeomVertexWriter(vdata, "vertex")
    cw = GeomVertexWriter(vdata, "color")
    base = color or PALE
    for idx, (x, y, z) in enumerate(vertices):
        vw.addData3f(float(x), float(y), float(z))
        cw.addData4f(colors[idx] if colors and idx < len(colors) else base)
    tris = GeomTriangles(Geom.UHStatic)
    for a, b, c in faces:
        tris.addVertices(int(a), int(b), int(c))
    tris.closePrimitive()
    geom = Geom(vdata)
    geom.addPrimitive(tris)
    node = GeomNode(name)
    node.addGeom(geom)
    np = NodePath(node)
    np.setTransparency(TransparencyAttrib.MAlpha)
    np.setAntialias(AntialiasAttrib.MAuto)
    np.setTwoSided(True)
    return np


def make_polyline(name: str, points: Iterable[Point3 | Vec3 | tuple[float, float, float]], color: Vec4, thickness: float = 2.0) -> NodePath:
    pts = [Point3(p.x, p.y, p.z) if isinstance(p, (Point3, Vec3)) else Point3(*p) for p in points]
    ls = LineSegs(name)
    ls.setColor(color)
    ls.setThickness(float(thickness))
    for idx, p in enumerate(pts):
        if idx == 0:
            ls.moveTo(p)
        else:
            ls.drawTo(p)
    np = NodePath(ls.create())
    np.setTransparency(TransparencyAttrib.MAlpha)
    np.setAntialias(AntialiasAttrib.MAuto)
    return np


def make_ring_z(name: str, rx: float, ry: float, z: float, color: Vec4, segs: int = 72, thickness: float = 1.4) -> NodePath:
    pts = []
    for j in range(segs + 1):
        theta = math.tau * (j % segs) / segs
        pts.append((rx * math.cos(theta), ry * math.sin(theta), z))
    return make_polyline(name, pts, color, thickness)


def make_bell(name: str, rx: float, ry: float, height: float, color_a: Vec4, color_b: Vec4, stacks: int = 8, slices: int = 36) -> NodePath:
    """Open translucent jellyfish bell, top dome to lower rim."""
    verts: list[tuple[float, float, float]] = []
    colors: list[Vec4] = []
    faces: list[tuple[int, int, int]] = []
    for i in range(stacks + 1):
        t = i / stacks
        phi = (math.pi * 0.5) * t
        ring = math.sin(phi)
        z = height * math.cos(phi) - 0.18 * t * t
        ring_scale = 0.34 + 0.66 * ring
        for j in range(slices):
            theta = math.tau * j / slices
            ripple = 1.0 + 0.045 * math.sin(theta * 8.0 + t * 4.0)
            x = rx * ring_scale * math.cos(theta) * ripple
            y = ry * ring_scale * math.sin(theta) * ripple
            shimmer = 0.5 + 0.5 * math.sin(theta * 3.0 + t * 6.0)
            colors.append(lerp_color(color_a, color_b, 0.24 + 0.36 * shimmer))
            verts.append((x, y, z))
    for i in range(stacks):
        for j in range(slices):
            a = i * slices + j
            b = i * slices + ((j + 1) % slices)
            c = (i + 1) * slices + j
            d = (i + 1) * slices + ((j + 1) % slices)
            faces.append((a, c, b))
            faces.append((b, c, d))
    return make_geom(name, verts, faces, colors=colors)


def make_inner_core(name: str, rx: float, ry: float, rz: float, color: Vec4, stacks: int = 7, slices: int = 24) -> NodePath:
    verts: list[tuple[float, float, float]] = []
    colors: list[Vec4] = []
    faces: list[tuple[int, int, int]] = []
    for i in range(stacks + 1):
        phi = math.pi * i / stacks
        z = rz * math.cos(phi)
        ring = math.sin(phi)
        for j in range(slices):
            theta = math.tau * j / slices
            verts.append((rx * math.cos(theta) * ring, ry * math.sin(theta) * ring, z))
            colors.append(lerp_color(color, PALE, 0.22 + 0.18 * math.sin(theta * 5 + i)))
    for i in range(stacks):
        for j in range(slices):
            a = i * slices + j
            b = i * slices + ((j + 1) % slices)
            c = (i + 1) * slices + j
            d = (i + 1) * slices + ((j + 1) % slices)
            faces.append((a, c, b))
            faces.append((b, c, d))
    return make_geom(name, verts, faces, colors=colors)


def make_ribbon(name: str, phase: float, radius: float, length: float, color_a: Vec4, color_b: Vec4, width: float = 0.16, steps: int = 14) -> NodePath:
    verts: list[tuple[float, float, float]] = []
    colors: list[Vec4] = []
    faces: list[tuple[int, int, int]] = []
    for i in range(steps + 1):
        t = i / steps
        ang = phase + 0.44 * math.sin(t * 3.8 + phase)
        r = radius * (1.0 - 0.28 * t)
        z = -length * t
        cx = r * math.cos(ang) + 0.22 * math.sin(t * 7.0 + phase)
        cy = r * math.sin(ang) + 0.22 * math.cos(t * 6.0 + phase)
        side_x = math.cos(ang + math.pi * 0.5) * width * (1.0 - 0.35 * t)
        side_y = math.sin(ang + math.pi * 0.5) * width * (1.0 - 0.35 * t)
        verts.append((cx - side_x, cy - side_y, z))
        verts.append((cx + side_x, cy + side_y, z))
        c = lerp_color(color_a, color_b, 0.25 + 0.65 * t)
        colors.extend([c, c])
    for i in range(steps):
        a = i * 2
        b = a + 1
        c = (i + 1) * 2
        d = c + 1
        faces.append((a, c, b))
        faces.append((b, c, d))
    return make_geom(name, verts, faces, colors=colors)


def make_tentacle_line(name: str, phase: float, radius: float, length: float, color: Vec4, steps: int = 20, thickness: float = 1.45) -> NodePath:
    pts = []
    for i in range(steps + 1):
        t = i / steps
        ang = phase + 0.40 * math.sin(t * 6.2 + phase * 0.7)
        r = radius * (1.0 - 0.38 * t)
        x = r * math.cos(ang) + 0.34 * math.sin(t * 9.0 + phase)
        y = r * math.sin(ang) + 0.34 * math.cos(t * 8.0 + phase)
        z = -length * t - 0.08 * math.sin(t * 11.0 + phase)
        pts.append((x, y, z))
    return make_polyline(name, pts, color, thickness)


class HoloJellyfishMob:
    """Sparse chunk mob with low-cost bell pulse and tendril sway."""

    def __init__(self, seed: int = 0, variant: JellyVariant | None = None, surface_height_offset: float = JELLYFISH_HEIGHT_OFFSET) -> None:
        self.seed = int(seed) & 0xFFFFFFFF
        self.rng = random.Random(self.seed)
        self.variant = variant or JELLYFISH_VARIANTS[self.seed % len(JELLYFISH_VARIANTS)]
        self.surface_height_offset = float(surface_height_offset)
        self.root: NodePath | None = None
        self.parts_root: NodePath | None = None
        self.tendril_root: NodePath | None = None
        self.rings: list[NodePath] = []
        self.tendrils: list[NodePath] = []
        self.bubbles: list[NodePath] = []
        self.phase = self.rng.random() * math.tau

    def build(self, parent: NodePath, pos: Vec3, scale: float | None = None, heading: float | None = None) -> "HoloJellyfishMob":
        self.root = parent.attachNewNode("holo_jellyfish_chunk_mob")
        self.root.setPos(pos)
        self.root.setH(float(heading if heading is not None else self.rng.uniform(0.0, 360.0)))
        self.root.setScale(float(scale if scale is not None else self.variant.scale) * 2.85)
        self.root.setTransparency(TransparencyAttrib.MAlpha)
        self.root.setLightOff()
        self.parts_root = self.root.attachNewNode("jellyfish_bell_pulse_root")
        self.tendril_root = self.root.attachNewNode("jellyfish_tendril_sway_root")
        self._build_body()
        self.update_pose(0.0)
        return self

    def destroy(self) -> None:
        if self.root is not None and not self.root.isEmpty():
            self.root.removeNode()

    def _attach(self, np: NodePath, parent: NodePath | None = None, transparent_bin: int = 13) -> NodePath:
        if self.root is None:
            return np
        np.reparentTo(parent or self.root)
        np.setTransparency(TransparencyAttrib.MAlpha)
        np.setAntialias(AntialiasAttrib.MAuto)
        np.setLightOff()
        np.setBin("transparent", transparent_bin)
        return np

    def _build_body(self) -> None:
        assert self.parts_root is not None and self.tendril_root is not None
        v = self.variant
        bell = self._attach(make_bell("jellyfish_translucent_bell", 1.25, 1.05, 1.05, v.bell_a, v.bell_b), self.parts_root, 13)
        bell.setZ(0.35)
        core = self._attach(make_inner_core("jellyfish_inner_core", 0.38, 0.32, 0.36, lerp_color(v.bell_a, PALE, 0.36)), self.parts_root, 14)
        core.setZ(-0.10)
        for i, (z, rad, alpha) in enumerate(((0.82, 1.18, 0.62), (0.42, 1.05, 0.48), (0.05, 1.02, 0.42), (-0.19, 1.30, 0.34))):
            c = Vec4(v.tendril.x, v.tendril.y, v.tendril.z, alpha)
            ring = self._attach(make_ring_z(f"jellyfish_bell_scan_ring_{i}", rad, rad * 0.84, z, c, thickness=1.25), self.parts_root, 15)
            self.rings.append(ring)
        for j in range(14):
            theta = math.tau * j / 14
            pts = []
            for i in range(7):
                t = i / 6
                r = 0.25 + 1.05 * t
                pts.append((r * math.cos(theta), r * 0.84 * math.sin(theta), 0.95 - 1.10 * t + 0.04 * math.sin(t * 4)))
            rib = self._attach(make_polyline(f"jellyfish_bell_rib_{j}", pts, Vec4(v.tendril.x, v.tendril.y, v.tendril.z, 0.42), 1.05), self.parts_root, 15)
        rnd = random.Random(self.seed ^ v.seed_salt)
        for j in range(20):
            phase = math.tau * j / 20 + rnd.uniform(-0.12, 0.12)
            radius = rnd.uniform(0.18, 0.86)
            length = rnd.uniform(2.2, 4.8) * (1.0 + 0.15 * math.sin(j))
            if j % 5 == 0:
                ribbon = self._attach(make_ribbon(f"jellyfish_veil_tendril_{j}", phase, radius, length * 0.88, v.bell_a, v.bell_b, width=rnd.uniform(0.12, 0.23)), self.tendril_root, 16)
                self.tendrils.append(ribbon)
            else:
                line = self._attach(make_tentacle_line(f"jellyfish_tendril_{j}", phase, radius, length, v.tendril, thickness=rnd.uniform(0.95, 2.0)), self.tendril_root, 16)
                self.tendrils.append(line)
        for j in range(8):
            theta = math.tau * j / 8 + rnd.uniform(-0.2, 0.2)
            rr = rnd.uniform(1.3, 2.25)
            z = rnd.uniform(-2.6, 1.1)
            bubble = self._attach(make_ring_z(f"jellyfish_bubble_{j}", rnd.uniform(0.06, 0.15), rnd.uniform(0.05, 0.13), 0.0, Vec4(0.74, 1.0, 1.0, 0.34), segs=28, thickness=0.95), self.root, 12)
            bubble.setPos(rr * math.cos(theta), rr * math.sin(theta), z)
            bubble.lookAt(self.root, 0, 0, 0)
            self.bubbles.append(bubble)

    def update_pose(self, time_value: float) -> None:
        if self.root is None or self.parts_root is None or self.tendril_root is None:
            return
        t = float(time_value or 0.0) + self.phase
        pulse = math.sin(t * 1.25 + self.variant.seed_salt * 0.01)
        bell_xy = 1.0 + 0.055 * pulse
        bell_z = 1.0 - 0.038 * pulse
        self.parts_root.setScale(bell_xy, bell_xy, bell_z)
        self.parts_root.setH(4.0 * math.sin(t * 0.32 + self.variant.seed_salt))
        self.tendril_root.setH(6.0 * math.sin(t * 0.72 + self.variant.seed_salt * 0.1))
        self.tendril_root.setP(2.8 * math.sin(t * 0.56 + 0.6))
        self.tendril_root.setR(2.4 * math.cos(t * 0.48 + 1.7))
        bob = 0.18 * math.sin(t * 0.72 + self.variant.seed_salt)
        self.parts_root.setZ(bob)
        self.tendril_root.setZ(bob)
        for idx, ring in enumerate(self.rings):
            s = 1.0 + 0.035 * math.sin(t * 1.4 + idx * 0.8)
            ring.setScale(s, s, 1.0)
        for idx, tendril in enumerate(self.tendrils):
            tendril.setH(4.5 * math.sin(t * 0.86 + idx * 0.37))
            tendril.setP(2.2 * math.cos(t * 0.71 + idx * 0.22))
        for idx, bubble in enumerate(self.bubbles):
            bubble.setZ(bubble.getZ() + 0.003 * math.sin(t * 0.9 + idx))
            bubble.setScale(1.0 + 0.12 * math.sin(t + idx * 0.8))

    def update_surface_lock(self, surface_height_fn: Callable[[float, float], float]) -> None:
        if self.root is None or self.root.isEmpty():
            return
        world_pos = self.root.getPos(self.root.getParent())
        try:
            ground = float(surface_height_fn(float(world_pos.x), float(world_pos.y)))
        except Exception:
            return
        self.root.setZ(ground + self.surface_height_offset)
