"""Lightweight procedural surface-object primitives for HoloCore biomes.

These helpers intentionally avoid model files.  They build simple Panda3D
line/card structures so biome folders stay portable, cheap to stream, and safe
for HoloVerse same-window adapter use.
"""
from __future__ import annotations

import math
from panda3d.core import CardMaker, Geom, GeomNode, GeomTriangles, GeomVertexData, GeomVertexFormat, GeomVertexWriter, LineSegs, NodePath, TransparencyAttrib, Vec3

Color = tuple[float, float, float, float]


def make_root(parent: NodePath, name: str, x: float, y: float, z: float) -> NodePath:
    root = parent.attachNewNode(name)
    root.setPos(float(x), float(y), float(z))
    root.setTransparency(TransparencyAttrib.MAlpha)
    return root


def line_segments(parent: NodePath, name: str, segments: list[tuple[tuple[float, float, float], tuple[float, float, float]]], color: Color, thickness: float = 2.0) -> NodePath:
    segs = LineSegs(name)
    segs.setThickness(float(thickness))
    segs.setColor(*color)
    for start, end in segments:
        segs.moveTo(*start)
        segs.drawTo(*end)
    node = parent.attachNewNode(segs.create())
    node.setTransparency(TransparencyAttrib.MAlpha)
    return node


def ring(parent: NodePath, name: str, radius: float, z: float, color: Color, thickness: float = 2.0, segments_count: int = 24, x_scale: float = 1.0, y_scale: float = 1.0) -> NodePath:
    segments = []
    count = max(8, int(segments_count))
    for i in range(count):
        a0 = math.tau * (i / count)
        a1 = math.tau * ((i + 1) / count)
        segments.append(((math.cos(a0) * radius * x_scale, math.sin(a0) * radius * y_scale, z), (math.cos(a1) * radius * x_scale, math.sin(a1) * radius * y_scale, z)))
    return line_segments(parent, name, segments, color, thickness)


def vertical_card(parent: NodePath, name: str, width: float, height: float, color: Color, x: float = 0.0, y: float = 0.0, z: float = 0.0, heading: float = 0.0, pitch: float = 0.0, roll: float = 0.0) -> NodePath:
    cm = CardMaker(name)
    cm.setFrame(-width * 0.5, width * 0.5, 0.0, height)
    card = parent.attachNewNode(cm.generate())
    card.setPos(x, y, z)
    card.setHpr(heading, pitch, roll)
    card.setColor(*color)
    card.setTransparency(TransparencyAttrib.MAlpha)
    card.setTwoSided(True)
    return card


def flat_card(parent: NodePath, name: str, width: float, depth: float, color: Color, x: float = 0.0, y: float = 0.0, z: float = 0.0, heading: float = 0.0, roll: float = 0.0) -> NodePath:
    card = vertical_card(parent, name, width, depth, color, x=x, y=y, z=z, heading=heading, pitch=-90.0, roll=roll)
    return card


def wire_box(parent: NodePath, name: str, sx: float, sy: float, sz: float, color: Color, thickness: float = 2.0, z: float = 0.0) -> NodePath:
    x = sx * 0.5
    y = sy * 0.5
    points = [(-x, -y, z), (x, -y, z), (x, y, z), (-x, y, z), (-x, -y, z), (-x, -y, z + sz), (x, -y, z + sz), (x, y, z + sz), (-x, y, z + sz), (-x, -y, z + sz)]
    segments = []
    for a, b in zip(points, points[1:]):
        segments.append((a, b))
    for a, b in [((x, -y, z), (x, -y, z + sz)), ((x, y, z), (x, y, z + sz)), ((-x, y, z), (-x, y, z + sz))]:
        segments.append((a, b))
    return line_segments(parent, name, segments, color, thickness)


def wavy_stem_segments(height: float, sway: float, steps: int = 7, phase: float = 0.0) -> list[tuple[tuple[float, float, float], tuple[float, float, float]]]:
    pts: list[tuple[float, float, float]] = []
    for i in range(max(2, steps)):
        t = i / max(1, steps - 1)
        pts.append((math.sin(t * math.pi * 1.45 + phase) * sway * t, math.cos(t * math.pi * 1.12 + phase) * sway * 0.45 * t, height * t))
    return list(zip(pts, pts[1:]))


def set_ambient_motion(
    node: NodePath,
    phase: float,
    amp: float = 1.4,
    rate: float = 0.18,
    *,
    kind: str = "sway",
    spin_rate: float = 0.0,
    pulse_amp: float = 0.055,
    scale_amp: float = 0.0,
) -> NodePath:
    """Mark a surface object root for the shared low-cost ambience updater.

    ``kind`` is intentionally data-light: the streaming system animates only
    existing nodes with transform/color-scale changes.  No per-frame object
    creation, particles, or new tasks are introduced by biome assets.
    """
    node.setPythonTag("animated_surface_object", True)
    node.setPythonTag("ambient_motion_kind", str(kind or "sway"))
    node.setPythonTag("flow_phase", float(phase))
    node.setPythonTag("flow_amplitude", float(amp))
    node.setPythonTag("flow_rate", float(rate))
    node.setPythonTag("flow_spin_rate", float(spin_rate))
    node.setPythonTag("flow_pulse_amplitude", float(pulse_amp))
    node.setPythonTag("flow_scale_amplitude", float(scale_amp))
    node.setPythonTag("ambient_base_h", float(node.getH()))
    node.setPythonTag("ambient_base_p", float(node.getP()))
    node.setPythonTag("ambient_base_r", float(node.getR()))
    node.setPythonTag("ambient_base_sx", float(node.getSx()))
    node.setPythonTag("ambient_base_sy", float(node.getSy()))
    node.setPythonTag("ambient_base_sz", float(node.getSz()))
    return node


def organic_disc(
    parent: NodePath,
    name: str,
    radius_x: float,
    radius_y: float,
    color: Color,
    *,
    z: float = 0.0,
    points: int = 18,
    wobble: float = 0.18,
    heading: float = 0.0,
    pitch: float = -90.0,
    roll: float = 0.0,
) -> NodePath:
    """Build an irregular oval surface instead of a rectangular card."""
    count = max(8, int(points))
    fmt = GeomVertexFormat.getV3c4()
    vdata = GeomVertexData(name, fmt, Geom.UHStatic)
    vw = GeomVertexWriter(vdata, "vertex")
    cw = GeomVertexWriter(vdata, "color")
    vw.addData3f(0.0, 0.0, 0.0)
    cw.addData4f(*color)
    for i in range(count):
        t = math.tau * i / count
        ripple = 1.0 + math.sin(t * 3.0 + radius_x * 0.071) * wobble * 0.55 + math.cos(t * 5.0 + radius_y * 0.037) * wobble * 0.35
        vw.addData3f(math.cos(t) * radius_x * ripple, math.sin(t) * radius_y * ripple, 0.0)
        edge_alpha = max(0.0, min(1.0, color[3] * 0.72))
        cw.addData4f(color[0], color[1], color[2], edge_alpha)
    tris = GeomTriangles(Geom.UHStatic)
    for i in range(count):
        tris.addVertices(0, 1 + i, 1 + ((i + 1) % count))
    tris.closePrimitive()
    geom = Geom(vdata)
    geom.addPrimitive(tris)
    node = GeomNode(name)
    node.addGeom(geom)
    np = parent.attachNewNode(node)
    np.setPos(0.0, 0.0, z)
    np.setHpr(heading, pitch, roll)
    np.setTransparency(TransparencyAttrib.MAlpha)
    np.setTwoSided(True)
    return np


def organic_lobe(
    parent: NodePath,
    name: str,
    width: float,
    height: float,
    color: Color,
    *,
    x: float = 0.0,
    y: float = 0.0,
    z: float = 0.0,
    heading: float = 0.0,
    pitch: float = 0.0,
    roll: float = 0.0,
    points: int = 16,
) -> NodePath:
    """Vertical leaf/fin-shaped translucent patch with no rectangular silhouette."""
    count = max(10, int(points))
    fmt = GeomVertexFormat.getV3c4()
    vdata = GeomVertexData(name, fmt, Geom.UHStatic)
    vw = GeomVertexWriter(vdata, "vertex")
    cw = GeomVertexWriter(vdata, "color")
    vw.addData3f(0.0, 0.0, height * 0.48)
    cw.addData4f(*color)
    for i in range(count):
        t = math.tau * i / count
        # Teardrop / kelp-fin outline: full at middle, pinched at base/top.
        vertical = (math.sin(t) + 1.0) * 0.5
        taper = 0.22 + 0.78 * math.sin(math.pi * vertical)
        ripple = 1.0 + 0.09 * math.sin(t * 4.0 + width * 0.33)
        px = math.cos(t) * width * 0.5 * taper * ripple
        pz = vertical * height
        vw.addData3f(px, 0.0, pz)
        cw.addData4f(color[0], color[1], color[2], max(0.0, min(1.0, color[3] * 0.72)))
    tris = GeomTriangles(Geom.UHStatic)
    for i in range(count):
        tris.addVertices(0, 1 + i, 1 + ((i + 1) % count))
    tris.closePrimitive()
    geom = Geom(vdata)
    geom.addPrimitive(tris)
    node = GeomNode(name)
    node.addGeom(geom)
    np = parent.attachNewNode(node)
    np.setPos(x, y, z)
    np.setHpr(heading, pitch, roll)
    np.setTransparency(TransparencyAttrib.MAlpha)
    np.setTwoSided(True)
    return np


def tapered_cage(
    parent: NodePath,
    name: str,
    base_radius: float,
    height: float,
    color: Color,
    *,
    top_radius: float | None = None,
    sides: int = 7,
    thickness: float = 1.4,
    lean_x: float = 0.0,
    lean_y: float = 0.0,
) -> NodePath:
    """Wireframe tapered organic column/spire; avoids cubic box outlines."""
    count = max(5, int(sides))
    top_r = float(top_radius if top_radius is not None else base_radius * 0.34)
    base = []
    top = []
    for i in range(count):
        a = math.tau * i / count
        wob = 1.0 + 0.14 * math.sin(a * 2.0 + base_radius)
        base.append((math.cos(a) * base_radius * wob, math.sin(a) * base_radius * (1.0 + 0.10 * math.cos(a * 3.0)), 0.0))
        top.append((lean_x + math.cos(a + 0.18) * top_r, lean_y + math.sin(a + 0.18) * top_r, height))
    segs = []
    for i in range(count):
        segs.append((base[i], base[(i + 1) % count]))
        segs.append((base[i], top[i]))
        if i % 2 == 0:
            segs.append((base[i], top[(i + 1) % count]))
    for i in range(count):
        segs.append((top[i], top[(i + 1) % count]))
    return line_segments(parent, name, segs, color, thickness)


def soft_polyline_loop(
    parent: NodePath,
    name: str,
    radius_x: float,
    radius_y: float,
    z: float,
    color: Color,
    *,
    thickness: float = 1.2,
    points: int = 18,
    wobble: float = 0.16,
) -> NodePath:
    segs = []
    count = max(8, int(points))
    pts = []
    for i in range(count):
        a = math.tau * i / count
        ripple = 1.0 + math.sin(a * 3.0 + radius_x * 0.17) * wobble + math.cos(a * 5.0 + radius_y * 0.11) * wobble * 0.5
        pts.append((math.cos(a) * radius_x * ripple, math.sin(a) * radius_y * ripple, z))
    for i in range(count):
        segs.append((pts[i], pts[(i + 1) % count]))
    return line_segments(parent, name, segs, color, thickness)
