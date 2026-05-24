"""Generated HoloCore mermaid mob.

Preview import pass: lightweight, animated, generated Panda3D geometry only.
Mermaids are chunk-owned world mobs; they float above the sampled terrain surface
and never bring the preview rectangle/platform into the game.
"""
from __future__ import annotations

import math
import random
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

MERMAID_SPAWN_CHANCE = 0.10
MERMAID_HEIGHT_OFFSET = 8.25
MERMAID_MIN_DISTANCE_FROM_HUB = 660.0

CYAN = Vec4(0.08, 0.96, 1.00, 0.76)
AQUA = Vec4(0.02, 0.86, 0.74, 0.52)
PALE = Vec4(0.82, 1.00, 1.00, 0.72)
PINK = Vec4(1.00, 0.38, 0.92, 0.34)
VIOLET = Vec4(0.62, 0.30, 1.00, 0.34)
TEAL_GLASS = Vec4(0.10, 0.95, 0.86, 0.26)
WHITE_GLASS = Vec4(0.86, 1.00, 1.00, 0.42)
HAIR_MAIN = Vec4(0.74, 0.97, 1.00, 0.70)
HAIR_EDGE = Vec4(0.13, 1.00, 0.85, 0.52)
SCALE_A = Vec4(0.55, 1.00, 0.92, 0.64)
SCALE_B = Vec4(1.00, 0.48, 0.95, 0.50)
SCALE_C = Vec4(0.40, 0.74, 1.00, 0.56)


def stable_chunk_seed(chunk_key: tuple[int, int], salt: int = 0x4D3D5EA) -> int:
    cx, cy = int(chunk_key[0]), int(chunk_key[1])
    return ((cx * 73856093) ^ (cy * 19349663) ^ int(salt)) & 0xFFFFFFFF


def lerp_color(a: Vec4, b: Vec4, t: float) -> Vec4:
    t = max(0.0, min(1.0, float(t)))
    return Vec4(a.x + (b.x - a.x) * t, a.y + (b.y - a.y) * t, a.z + (b.z - a.z) * t, a.w + (b.w - a.w) * t)


def _make_geom(name: str, vertices: list[tuple[float, float, float]], faces: Iterable[tuple[int, int, int]], color: Vec4 | None = None, colors: list[Vec4] | None = None, two_sided: bool = True) -> NodePath:
    fmt = GeomVertexFormat.getV3c4()
    vdata = GeomVertexData(name, fmt, Geom.UHStatic)
    vw = GeomVertexWriter(vdata, "vertex")
    cw = GeomVertexWriter(vdata, "color")
    default_color = color or PALE
    for idx, (x, y, z) in enumerate(vertices):
        vw.addData3f(float(x), float(y), float(z))
        cw.addData4f(colors[idx] if colors and idx < len(colors) else default_color)
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
    if two_sided:
        np.setTwoSided(True)
    return np


def make_uv_ellipsoid(name: str, rx: float, ry: float, rz: float, color: Vec4, stacks: int = 9, slices: int = 18) -> NodePath:
    verts: list[tuple[float, float, float]] = []
    colors: list[Vec4] = []
    faces: list[tuple[int, int, int]] = []
    for i in range(stacks + 1):
        phi = math.pi * i / stacks
        z = rz * math.cos(phi)
        ring = math.sin(phi)
        for j in range(slices):
            theta = math.tau * j / slices
            shimmer = 0.5 + 0.5 * math.sin(theta * 3.0 + i * 0.9)
            verts.append((rx * math.cos(theta) * ring, ry * math.sin(theta) * ring, z))
            colors.append(lerp_color(color, PALE, shimmer * 0.22))
    for i in range(stacks):
        for j in range(slices):
            a = i * slices + j
            b = i * slices + ((j + 1) % slices)
            c = (i + 1) * slices + j
            d = (i + 1) * slices + ((j + 1) % slices)
            faces.append((a, c, b))
            faces.append((b, c, d))
    return _make_geom(name, verts, faces, colors=colors)


def make_cylinder_y(name: str, rx: float, rz: float, length: float, color: Vec4, slices: int = 16) -> NodePath:
    verts: list[tuple[float, float, float]] = []
    colors: list[Vec4] = []
    faces: list[tuple[int, int, int]] = []
    for row, y in enumerate((-length * 0.5, length * 0.5)):
        for j in range(slices):
            theta = math.tau * j / slices
            verts.append((rx * math.cos(theta), y, rz * math.sin(theta)))
            colors.append(lerp_color(color, CYAN, (0.5 + 0.5 * math.sin(theta * 2 + row)) * 0.16))
    for j in range(slices):
        a = j
        b = (j + 1) % slices
        c = slices + j
        d = slices + ((j + 1) % slices)
        faces.append((a, c, b))
        faces.append((b, c, d))
    return _make_geom(name, verts, faces, colors=colors)


def make_tapered_segment(name: str, rx0: float, rz0: float, rx1: float, rz1: float, length: float, color: Vec4, slices: int = 20) -> NodePath:
    verts: list[tuple[float, float, float]] = []
    colors: list[Vec4] = []
    faces: list[tuple[int, int, int]] = []
    for row, (y, rx, rz) in enumerate(((-length * 0.5, rx0, rz0), (length * 0.5, rx1, rz1))):
        for j in range(slices):
            theta = math.tau * j / slices
            verts.append((rx * math.cos(theta), y, rz * math.sin(theta)))
            colors.append(lerp_color(color, PINK if j % 5 == 0 else CYAN, 0.16 + 0.04 * row))
    for j in range(slices):
        a = j
        b = (j + 1) % slices
        c = slices + j
        d = slices + ((j + 1) % slices)
        faces.append((a, c, b))
        faces.append((b, c, d))
    return _make_geom(name, verts, faces, colors=colors)


def make_polyline(name: str, points: Iterable[Point3 | Vec3 | tuple[float, float, float]], color: Vec4, thickness: float = 1.5) -> NodePath:
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


def make_ring_y(name: str, rx: float, rz: float, y: float, color: Vec4, segs: int = 36, thickness: float = 1.35) -> NodePath:
    pts = []
    for j in range(segs + 1):
        theta = math.tau * (j % segs) / segs
        pts.append((rx * math.cos(theta), y, rz * math.sin(theta)))
    return make_polyline(name, pts, color, thickness)


def make_ribbon_surface(name: str, spine: list[Vec3], width_fn, color_a: Vec4, color_b: Vec4, normal_axis: str = "x") -> NodePath:
    verts: list[tuple[float, float, float]] = []
    colors: list[Vec4] = []
    faces: list[tuple[int, int, int]] = []
    n = max(1, len(spine) - 1)
    for i, p in enumerate(spine):
        t = i / n
        width = float(width_fn(i, t))
        if normal_axis == "x":
            a = Vec3(p.x - width, p.y, p.z)
            b = Vec3(p.x + width, p.y, p.z)
        else:
            a = Vec3(p.x, p.y - width, p.z)
            b = Vec3(p.x, p.y + width, p.z)
        verts.extend([(a.x, a.y, a.z), (b.x, b.y, b.z)])
        colors.extend([lerp_color(color_a, color_b, t), lerp_color(color_b, color_a, t)])
    for i in range(len(spine) - 1):
        a = i * 2
        b = a + 1
        c = a + 2
        d = a + 3
        faces.append((a, c, b))
        faces.append((b, c, d))
    return _make_geom(name, verts, faces, colors=colors, two_sided=True)


def make_diamond(name: str, center: Vec3, sx: float, sy: float, sz: float, color: Vec4) -> NodePath:
    x, y, z = center.x, center.y, center.z
    pts = [(x, y - sy, z), (x + sx, y, z + sz * 0.45), (x, y + sy, z), (x - sx, y, z - sz * 0.45)]
    return _make_geom(name, pts, [(0, 1, 2), (0, 2, 3)], color=color, two_sided=True)


def orient_between(node: NodePath, start: Vec3, end: Vec3) -> None:
    mid = (start + end) * 0.5
    node.setPos(mid)
    node.lookAt(Point3(end.x, end.y, end.z))


class HoloMermaidMob:
    """Sparse chunk mob with low-cost idle swim animation."""

    def __init__(self, seed: int = 0, surface_height_offset: float = MERMAID_HEIGHT_OFFSET) -> None:
        self.seed = int(seed) & 0xFFFFFFFF
        self.surface_height_offset = float(surface_height_offset)
        self.root: NodePath | None = None
        self.body_root: NodePath | None = None
        self.tail_segments: list[NodePath] = []
        self.tail_rings: list[NodePath] = []
        self.fluke_nodes: list[NodePath] = []
        self.ribbon_nodes: list[NodePath] = []
        self.hair_lines: list[NodePath] = []
        self.bubbles: list[NodePath] = []
        self._rng = random.Random(self.seed)
        self.phase = self._rng.random() * math.tau

    def build(self, parent: NodePath, pos: Vec3, scale: float = 2.65, heading: float | None = None) -> "HoloMermaidMob":
        self.root = parent.attachNewNode("holo_mermaid_chunk_mob")
        self.root.setPos(pos)
        self.root.setScale(float(scale))
        self.root.setH(float(heading if heading is not None else self._rng.uniform(0.0, 360.0)))
        self.root.setTransparency(TransparencyAttrib.MAlpha)
        self.body_root = self.root.attachNewNode("holo_mermaid_body_anim_root")
        self._build_body()
        self._build_tail()
        self._build_flowing_fins()
        self._build_bubbles()
        self.update_pose(0.0)
        return self

    def destroy(self) -> None:
        if self.root is not None and not self.root.isEmpty():
            self.root.removeNode()

    def _attach(self, np: NodePath, parent: NodePath | None = None) -> NodePath:
        if self.root is None:
            return np
        np.reparentTo(parent or self.root)
        np.setTransparency(TransparencyAttrib.MAlpha)
        np.setAntialias(AntialiasAttrib.MAuto)
        np.setLightOff()
        np.setBin("transparent", 12)
        return np

    def _build_body(self) -> None:
        assert self.body_root is not None
        body = self.body_root.attachNewNode("upper_iridescent_body")
        torso = self._attach(make_uv_ellipsoid("torso_holo_shell", 0.46, 0.34, 0.82, TEAL_GLASS, 9, 20), body)
        torso.setPos(0, 0, 3.40)
        torso.setP(-5)
        waist = self._attach(make_uv_ellipsoid("waist_scale_core", 0.38, 0.30, 0.36, AQUA, 8, 18), body)
        waist.setPos(0, -0.03, 2.78)
        head = self._attach(make_uv_ellipsoid("soft_holo_head", 0.27, 0.23, 0.34, PALE, 8, 18), body)
        head.setPos(0, -0.02, 4.55)
        neck = self._attach(make_cylinder_y("neck_light_column", 0.10, 0.13, 0.34, PALE, 12), body)
        neck.setPos(0, -0.01, 4.12)
        neck.setP(90)
        for row in range(8):
            z = 3.72 - row * 0.13
            width = 0.32 - row * 0.019
            count = 3 + (row % 3)
            for col in range(count):
                u = ((col + 0.5) / count * 2 - 1) * width
                y = -0.34 - row * 0.018
                color = [SCALE_A, SCALE_C, SCALE_B][(row + col) % 3]
                d = self._attach(make_diamond(f"torso_scale_{row}_{col}", Vec3(u, y, z), 0.035, 0.040, 0.075, color), body)
                d.setH((row * 7 + col * 11) % 20 - 10)
        arm_specs = [
            (Vec3(-0.42, -0.02, 3.86), Vec3(-0.78, -0.11, 3.30), Vec3(-1.04, 0.10, 2.88), "left", -1),
            (Vec3(0.42, -0.02, 3.86), Vec3(0.78, -0.11, 3.30), Vec3(1.04, 0.10, 2.88), "right", 1),
        ]
        arms = body.attachNewNode("arms_and_veil_fins")
        for shoulder, elbow, wrist, side, sx in arm_specs:
            upper = self._attach(make_cylinder_y(f"{side}_upper_arm_shell", 0.090, 0.110, (elbow - shoulder).length(), Vec4(0.72, 1.0, 1.0, 0.42), 14), arms)
            orient_between(upper, shoulder, elbow)
            lower = self._attach(make_cylinder_y(f"{side}_forearm_shell", 0.065, 0.084, (wrist - elbow).length(), Vec4(0.72, 1.0, 1.0, 0.40), 14), arms)
            orient_between(lower, elbow, wrist)
            self._attach(make_polyline(f"{side}_arm_light_path", [shoulder, elbow, wrist], CYAN, 1.6), arms)
            spine = []
            for k in range(6):
                t = k / 5
                spine.append(Vec3(wrist.x + sx * (0.05 + 0.08 * math.sin(t * math.pi)), wrist.y + 0.04 + 0.24 * t, wrist.z - 0.08 - 0.72 * t))
            veil = self._attach(make_ribbon_surface(f"{side}_forearm_veil", spine, lambda _i, t: 0.08 + 0.14 * math.sin(t * math.pi), WHITE_GLASS, PINK, "x"), arms)
            self.ribbon_nodes.append(veil)
        crown = body.attachNewNode("hair_and_fins")
        for sx in (-1, 1):
            ear_spine = [Vec3(sx * 0.24, -0.02, 4.66), Vec3(sx * 0.52, 0.01, 4.78), Vec3(sx * 0.72, 0.09, 4.60), Vec3(sx * 0.44, 0.04, 4.48)]
            fin = self._attach(make_ribbon_surface(f"ear_flower_fin_{sx}", ear_spine, lambda _i, t: 0.03 + 0.07 * math.sin(t * math.pi), WHITE_GLASS, AQUA, "y"), crown)
            self.ribbon_nodes.append(fin)
        hair_root = crown.attachNewNode("flowing_hair_lines")
        for idx in range(18):
            side = -1 if idx < 9 else 1
            local = idx % 9
            offset = side * (0.06 + local * 0.028)
            depth = 0.05 + self._rng.uniform(-0.03, 0.10)
            pts = []
            for k in range(7):
                t = k / 6
                wave = math.sin(t * math.pi * 1.7 + idx * 0.5) * (0.05 + 0.10 * t)
                pts.append((offset + side * wave, depth + 0.18 * t, 4.74 - 1.03 * t - 0.18 * math.sin(t * math.pi)))
            line = self._attach(make_polyline(f"hair_curl_{idx:02d}", pts, HAIR_MAIN if idx % 2 else HAIR_EDGE, 1.15 + (idx % 4) * 0.2), hair_root)
            self.hair_lines.append(line)

    def _build_tail(self) -> None:
        assert self.body_root is not None
        tail = self.body_root.attachNewNode("animated_tail_body")
        radii = [(0.43, 0.36), (0.39, 0.34), (0.34, 0.30), (0.28, 0.25), (0.22, 0.20), (0.16, 0.15), (0.11, 0.11)]
        for idx, (rx, rz) in enumerate(radii):
            rx1, rz1 = radii[min(idx + 1, len(radii) - 1)]
            seg = self._attach(make_tapered_segment(f"tail_crystal_segment_{idx}", rx, rz, rx1, rz1, 0.50, Vec4(0.05, 0.86, 0.78, 0.46), 22), tail)
            self.tail_segments.append(seg)
            ring = self._attach(make_ring_y(f"tail_scan_ring_{idx}", rx * 1.05, rz * 1.06, 0.0, Vec4(0.24, 1.0, 1.0, 0.52), 36, 1.25), tail)
            self.tail_rings.append(ring)
        scale_parent = tail.attachNewNode("tail_scale_lattice")
        for row in range(12):
            z = 2.28 - row * 0.14
            width = max(0.08, 0.34 - row * 0.019)
            count = 3 + (row % 3)
            for col in range(count):
                u = ((col + 0.5) / count * 2 - 1) * width
                y = -0.30 - row * 0.095
                color = [SCALE_A, SCALE_C, SCALE_B][(row + col) % 3]
                d = self._attach(make_diamond(f"tail_scale_{row}_{col}", Vec3(u, y, z), 0.038, 0.046, 0.092, color), scale_parent)
                d.setH((row * 11 + col * 9) % 24 - 12)
        for side, sx in (("left", -1), ("right", 1)):
            spine = [Vec3(0, 0, 0), Vec3(sx * 0.36, -0.24, -0.18), Vec3(sx * 0.82, -0.55, -0.37), Vec3(sx * 1.16, -0.86, -0.54)]
            fluke = self._attach(make_ribbon_surface(f"{side}_large_tail_fluke", spine, lambda _i, t: 0.10 + 0.36 * math.sin(t * math.pi), WHITE_GLASS, AQUA, "x"), tail)
            edge = self._attach(make_polyline(f"{side}_fluke_edge_line", spine, Vec4(0.55, 1.0, 1.0, 0.58), 1.6), tail)
            self.fluke_nodes.extend([fluke, edge])
        for idx, sx in enumerate((-1.0, -0.45, 0.45, 1.0)):
            spine = [Vec3(0, 0, 0)]
            for k in range(1, 7):
                t = k / 6
                spine.append(Vec3(sx * 0.13 * k + math.sin(t * math.pi * 2 + idx) * 0.08, -0.15 * k, -0.18 - 0.86 * t))
            rib = self._attach(make_ribbon_surface(f"fluke_trailing_veil_{idx}", spine, lambda _i, t: 0.030 + 0.11 * (1.0 - t), WHITE_GLASS, VIOLET, "x"), tail)
            self.fluke_nodes.append(rib)

    def _build_flowing_fins(self) -> None:
        assert self.body_root is not None
        fins = self.body_root.attachNewNode("long_body_fins")
        for idx, sx in enumerate((-1.0, 1.0)):
            for layer in range(2):
                spine = []
                for k in range(7):
                    t = k / 6
                    spine.append(Vec3(sx * (0.30 + 0.08 * layer + 0.16 * math.sin(t * math.pi)), -0.03 + 0.16 * layer + 0.16 * t, 2.70 - 1.52 * t - 0.12 * math.sin(t * math.pi * 2 + layer)))
                ribbon = self._attach(make_ribbon_surface(f"hip_veil_{idx}_{layer}", spine, lambda _i, t: 0.075 + 0.19 * math.sin(t * math.pi), TEAL_GLASS, PINK if layer % 2 else WHITE_GLASS, "x"), fins)
                self.ribbon_nodes.append(ribbon)
        spine = [Vec3(0.0, 0.34 + 0.04 * math.sin(k), 2.40 - k * 0.22) for k in range(8)]
        dorsal = self._attach(make_ribbon_surface("back_dorsal_translucent_fin", spine, lambda _i, t: 0.08 + 0.17 * math.sin(t * math.pi), VIOLET, TEAL_GLASS, "x"), fins)
        self.ribbon_nodes.append(dorsal)

    def _build_bubbles(self) -> None:
        assert self.body_root is not None
        bubbles = self.body_root.attachNewNode("holo_mermaid_bubbles")
        for idx in range(7):
            r = self._rng.uniform(0.035, 0.10)
            bubble = self._attach(make_uv_ellipsoid(f"holo_bubble_{idx:02d}", r, r, r, Vec4(0.76, 0.96, 1.0, 0.14), 5, 10), bubbles)
            bubble.setPos(self._rng.uniform(-1.35, 1.35), self._rng.uniform(-0.70, 0.75), self._rng.uniform(0.3, 4.8))
            self.bubbles.append(bubble)

    def _tail_points(self, t: float) -> list[Vec3]:
        points: list[Vec3] = []
        for idx in range(8):
            y = -0.10 - idx * 0.25
            z = 2.48 - idx * 0.30
            amp = 0.030 + idx * 0.042
            x = math.sin(t * 2.0 + idx * 0.62) * amp
            points.append(Vec3(x, y, z))
        points[0] = Vec3(0, -0.04, 2.50)
        return points

    def update_pose(self, t: float) -> None:
        t = float(t) + self.phase
        if self.body_root is not None:
            self.body_root.setP(math.sin(t * 0.72) * 2.2)
            self.body_root.setR(math.cos(t * 0.53) * 1.6)
        points = self._tail_points(t)
        for idx, seg in enumerate(self.tail_segments):
            start = points[idx]
            end = points[idx + 1]
            orient_between(seg, start, end)
            seg.setR(math.sin(t * 2.0 + idx * 0.55) * 7.0)
            ring = self.tail_rings[idx]
            ring.setPos((start + end) * 0.5)
            ring.lookAt(Point3(end.x, end.y, end.z))
        tip = points[-1]
        tail_dir = points[-1] - points[-2]
        if tail_dir.length() <= 0.001:
            tail_dir = Vec3(0, -1, -0.3)
        for idx, fluke in enumerate(self.fluke_nodes):
            fluke.setPos(tip)
            fluke.lookAt(Point3((tip + tail_dir).x, (tip + tail_dir).y, (tip + tail_dir).z))
            fluke.setR(math.sin(t * 2.0 + idx * 0.22) * (9.0 if idx < 4 else 4.5))
            fluke.setH(math.sin(t * 1.1 + idx * 0.12) * 3.5)
        for idx, node in enumerate(self.ribbon_nodes):
            node.setX(math.sin(t * 1.4 + idx * 0.5) * 0.030)
            node.setR(math.sin(t * 1.2 + idx * 0.37) * 1.6)
        for idx, line in enumerate(self.hair_lines):
            line.setX(math.sin(t * 1.55 + idx * 0.33) * 0.046)
            line.setH(math.sin(t * 1.1 + idx * 0.15) * 2.2)
        for idx, bubble in enumerate(self.bubbles):
            bubble.setZ(bubble.getZ() + 0.006 * math.sin(t * 2.0 + idx))
            bubble.setScale(1.0 + 0.06 * math.sin(t * 2.7 + idx * 0.4))

    def update_surface_lock(self, surface_height_at: Callable[[float, float], float]) -> None:
        if self.root is None:
            return
        try:
            pos = self.root.getPos()
            self.root.setZ(float(surface_height_at(float(pos.x), float(pos.y))) + self.surface_height_offset)
        except Exception:
            pass
