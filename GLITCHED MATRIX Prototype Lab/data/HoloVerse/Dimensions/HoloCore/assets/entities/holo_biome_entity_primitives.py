"""Shared generated-geometry helpers for biome-specific HoloCore entities."""
from __future__ import annotations

import math
from typing import Iterable

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


def stable_seed(chunk_key: tuple[int, int], salt: int) -> int:
    cx, cy = int(chunk_key[0]), int(chunk_key[1])
    return ((cx * 1103515245) ^ (cy * 2654435761) ^ int(salt)) & 0xFFFFFFFF


def lerp_color(a: Vec4, b: Vec4, t: float) -> Vec4:
    t = max(0.0, min(1.0, float(t)))
    return Vec4(a.x + (b.x - a.x) * t, a.y + (b.y - a.y) * t, a.z + (b.z - a.z) * t, a.w + (b.w - a.w) * t)


def make_geom(name: str, vertices: list[tuple[float, float, float]], faces: Iterable[tuple[int, int, int]], color: Vec4 | None = None, colors: list[Vec4] | None = None) -> NodePath:
    fmt = GeomVertexFormat.getV3c4()
    vdata = GeomVertexData(name, fmt, Geom.UHStatic)
    vw = GeomVertexWriter(vdata, "vertex")
    cw = GeomVertexWriter(vdata, "color")
    base = color or Vec4(0.8, 1.0, 1.0, 0.6)
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


def make_polyline(name: str, points: Iterable[Point3 | Vec3 | tuple[float, float, float]], color: Vec4, thickness: float = 1.35) -> NodePath:
    pts = [Point3(p.x, p.y, p.z) if isinstance(p, (Point3, Vec3)) else Point3(*p) for p in points]
    line = LineSegs(name)
    line.setColor(color)
    line.setThickness(float(thickness))
    for idx, point in enumerate(pts):
        if idx == 0:
            line.moveTo(point)
        else:
            line.drawTo(point)
    np = NodePath(line.create())
    np.setTransparency(TransparencyAttrib.MAlpha)
    np.setAntialias(AntialiasAttrib.MAuto)
    return np


def make_ellipsoid(name: str, rx: float, ry: float, rz: float, color_a: Vec4, color_b: Vec4 | None = None, stacks: int = 8, slices: int = 24) -> NodePath:
    verts: list[tuple[float, float, float]] = []
    colors: list[Vec4] = []
    faces: list[tuple[int, int, int]] = []
    b = color_b or color_a
    for i in range(stacks + 1):
        phi = math.pi * i / stacks
        z = rz * math.cos(phi)
        ring = math.sin(phi)
        for j in range(slices):
            theta = math.tau * j / slices
            ripple = 1.0 + 0.035 * math.sin(theta * 5.0 + i * 0.7)
            verts.append((rx * math.cos(theta) * ring * ripple, ry * math.sin(theta) * ring * ripple, z))
            colors.append(lerp_color(color_a, b, 0.36 + 0.32 * math.sin(theta * 2.0 + i)))
    for i in range(stacks):
        for j in range(slices):
            a = i * slices + j
            b0 = i * slices + ((j + 1) % slices)
            c = (i + 1) * slices + j
            d = (i + 1) * slices + ((j + 1) % slices)
            faces.append((a, c, b0))
            faces.append((b0, c, d))
    return make_geom(name, verts, faces, colors=colors)


def make_ribbon(name: str, length: float, width: float, color_a: Vec4, color_b: Vec4, steps: int = 16, phase: float = 0.0, twist: float = 0.0) -> NodePath:
    verts: list[tuple[float, float, float]] = []
    colors: list[Vec4] = []
    faces: list[tuple[int, int, int]] = []
    for i in range(steps + 1):
        t = i / max(1, steps)
        x = math.sin(t * math.pi * 1.2 + phase) * width * 0.45
        y = -length * (t - 0.5)
        z = math.sin(t * math.pi + phase * 0.4) * width * 0.22
        taper = 1.0 - 0.72 * t
        side = width * 0.5 * taper
        angle = twist * t + 0.22 * math.sin(t * 5.0 + phase)
        sx = math.cos(angle) * side
        sz = math.sin(angle) * side
        verts.append((x - sx, y, z - sz))
        verts.append((x + sx, y, z + sz))
        c = lerp_color(color_a, color_b, t)
        colors.extend([c, c])
    for i in range(steps):
        a = i * 2
        b = a + 1
        c = (i + 1) * 2
        d = c + 1
        faces.append((a, c, b))
        faces.append((b, c, d))
    return make_geom(name, verts, faces, colors=colors)


def make_wavy_spine(name: str, length: float, color: Vec4, steps: int = 18, phase: float = 0.0, radius: float = 0.85, thickness: float = 1.5) -> NodePath:
    pts = []
    for i in range(steps + 1):
        t = i / max(1, steps)
        pts.append((math.sin(t * math.pi * 2.4 + phase) * radius, -length * (t - 0.5), math.cos(t * math.pi * 1.7 + phase) * radius * 0.42))
    return make_polyline(name, pts, color, thickness)


def set_entity_root_defaults(root: NodePath) -> NodePath:
    root.setTransparency(TransparencyAttrib.MAlpha)
    root.setAntialias(AntialiasAttrib.MAuto)
    return root


def make_orbit_loop(name: str, radius_x: float, radius_y: float, z: float, color: Vec4, segments: int = 36, thickness: float = 1.0, wobble: float = 0.0) -> NodePath:
    pts = []
    for i in range(segments + 1):
        t = i / max(1, segments)
        angle = math.tau * t
        ripple = 1.0 + wobble * math.sin(angle * 3.0 + radius_x * 0.37)
        pts.append((math.cos(angle) * radius_x * ripple, math.sin(angle) * radius_y * ripple, z + math.sin(angle * 2.0) * wobble * 0.7))
    return make_polyline(name, pts, color, thickness)


def make_star_polyline(name: str, radius_inner: float, radius_outer: float, z: float, color: Vec4, points: int = 7, thickness: float = 1.0, phase: float = 0.0) -> NodePath:
    pts = []
    total = max(3, points) * 2
    for i in range(total + 1):
        angle = phase + math.tau * i / total
        radius = radius_outer if i % 2 == 0 else radius_inner
        pts.append((math.cos(angle) * radius, math.sin(angle) * radius, z + math.sin(angle * 3.0) * 0.12))
    return make_polyline(name, pts, color, thickness)
