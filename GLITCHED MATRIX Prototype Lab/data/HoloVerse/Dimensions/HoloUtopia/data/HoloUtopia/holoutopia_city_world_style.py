"""City-atlas presentation layer for HoloUtopia.

Pass 42 turns the authored 3x3 district atlas into a readable world-view city:
subtle district pads, dark ring/radial roads, and a substantial raised central
Simulation/Core hub. Pass 43 adds district-specific landmark silhouettes so the
world atlas reads closer to the target HoloUtopia city-map art. Pass 44 strengthens the central Simulation/Core into a raised hub with a clear plaza footprint so it never reads as a thin line under buildings. Pass 45 adds atlas-depth glows, perimeter nodes, and road-flow beacons so the full city feels closer to the neon world-map reference without adding traffic lane markings. Pass 46 adds district surface motifs and elevated skyway ribbons so each sector reads with stronger identity from the world atlas view. This is visual-only, collisionless, and does not mutate
any authored data.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any


def _as_root_path(holoverse_root: Path | str | None) -> Path | None:
    if holoverse_root is None:
        return None
    try:
        return Path(holoverse_root)
    except Exception:
        return None


def _theme_for_town(town_id: str) -> tuple[float, float, float, float]:
    tid = str(town_id or "").lower()
    if "central" in tid or "core" in tid or "simulation" in tid:
        return (0.84, 0.30, 1.0, 0.90)
    if "residential" in tid:
        return (0.28, 1.0, 0.66, 0.82)
    if "market" in tid:
        return (0.40, 1.0, 0.38, 0.78)
    if "industrial" in tid:
        return (1.0, 0.42, 0.92, 0.76)
    if "harbor" in tid:
        return (0.08, 0.92, 1.0, 0.78)
    if "archive" in tid:
        return (0.30, 0.54, 1.0, 0.78)
    if "security" in tid:
        return (1.0, 0.86, 0.18, 0.78)
    if "glitched" in tid or "quarantine" in tid:
        return (1.0, 0.20, 0.18, 0.82)
    if "civic" in tid:
        return (0.20, 0.72, 1.0, 0.78)
    return (0.40, 0.96, 1.0, 0.70)


def _line3d(parent: Any, name: str, points: list[tuple[float, float, float]], color: tuple[float, float, float, float], thickness: float = 1.0, *, closed: bool = False) -> Any | None:
    if not points:
        return None
    try:
        from panda3d.core import LineSegs
    except Exception:
        return None
    seg = LineSegs(name)
    seg.setThickness(float(thickness))
    seg.setColor(*color)
    seg.moveTo(*points[0])
    for point in points[1:]:
        seg.drawTo(*point)
    if closed and len(points) > 2:
        seg.drawTo(*points[0])
    node = parent.attachNewNode(seg.create())
    node.setLightOff(True)
    node.setPythonTag("holoutopia_city_world_style", True)
    return node


def _circle_points(cx: float, cy: float, radius: float, z: float, *, segments: int = 96) -> list[tuple[float, float, float]]:
    return [(cx + math.cos(math.tau * i / segments) * radius, cy + math.sin(math.tau * i / segments) * radius, z) for i in range(segments + 1)]


def _flat_disc(parent: Any, name: str, cx: float, cy: float, radius: float, z: float, color: tuple[float, float, float, float], *, segments: int = 96) -> Any | None:
    try:
        from panda3d.core import Geom, GeomNode, GeomTriangles, GeomVertexData, GeomVertexFormat, GeomVertexWriter, TransparencyAttrib
    except Exception:
        return None
    fmt = GeomVertexFormat.getV3c4()
    vdata = GeomVertexData(name, fmt, Geom.UHStatic)
    vertex = GeomVertexWriter(vdata, "vertex")
    color_w = GeomVertexWriter(vdata, "color")
    vertex.addData3(float(cx), float(cy), float(z))
    color_w.addData4(*color)
    safe_segments = max(12, int(segments))
    for idx in range(safe_segments):
        a = math.tau * idx / safe_segments
        vertex.addData3(cx + math.cos(a) * radius, cy + math.sin(a) * radius, z)
        color_w.addData4(*color)
    tris = GeomTriangles(Geom.UHStatic)
    for idx in range(safe_segments):
        tris.addVertices(0, idx + 1, ((idx + 1) % safe_segments) + 1)
    geom = Geom(vdata)
    geom.addPrimitive(tris)
    node = GeomNode(name)
    node.addGeom(geom)
    np = parent.attachNewNode(node)
    np.setTransparency(TransparencyAttrib.M_alpha)
    np.setLightOff(True)
    np.setPythonTag("holoutopia_city_world_style", True)
    return np


def _flat_annulus(parent: Any, name: str, cx: float, cy: float, inner: float, outer: float, z: float, color: tuple[float, float, float, float], *, segments: int = 128) -> Any | None:
    try:
        from panda3d.core import Geom, GeomNode, GeomTriangles, GeomVertexData, GeomVertexFormat, GeomVertexWriter, TransparencyAttrib
    except Exception:
        return None
    safe_segments = max(16, int(segments))
    inner = max(0.01, float(inner))
    outer = max(inner + 0.01, float(outer))
    fmt = GeomVertexFormat.getV3c4()
    vdata = GeomVertexData(name, fmt, Geom.UHStatic)
    vertex = GeomVertexWriter(vdata, "vertex")
    color_w = GeomVertexWriter(vdata, "color")
    for idx in range(safe_segments):
        a = math.tau * idx / safe_segments
        vertex.addData3(cx + math.cos(a) * inner, cy + math.sin(a) * inner, z)
        color_w.addData4(*color)
        vertex.addData3(cx + math.cos(a) * outer, cy + math.sin(a) * outer, z)
        color_w.addData4(*color)
    tris = GeomTriangles(Geom.UHStatic)
    for idx in range(safe_segments):
        ni = (idx + 1) % safe_segments
        a0 = idx * 2
        a1 = idx * 2 + 1
        b0 = ni * 2
        b1 = ni * 2 + 1
        tris.addVertices(a0, a1, b1)
        tris.addVertices(a0, b1, b0)
    geom = Geom(vdata)
    geom.addPrimitive(tris)
    node = GeomNode(name)
    node.addGeom(geom)
    np = parent.attachNewNode(node)
    np.setTransparency(TransparencyAttrib.M_alpha)
    np.setLightOff(True)
    np.setPythonTag("holoutopia_city_world_style", True)
    return np


def _road_segment(parent: Any, name: str, x0: float, y0: float, x1: float, y1: float, width: float, z: float, color: tuple[float, float, float, float]) -> Any | None:
    try:
        from panda3d.core import CardMaker, TransparencyAttrib, Vec4
    except Exception:
        return None
    dx = x1 - x0
    dy = y1 - y0
    length = math.hypot(dx, dy)
    if length <= 0.001:
        return None
    cm = CardMaker(f"{name}_surface")
    cm.setFrame(-length * 0.5, length * 0.5, -width * 0.5, width * 0.5)
    card = parent.attachNewNode(cm.generate())
    card.setPos((x0 + x1) * 0.5, (y0 + y1) * 0.5, z)
    card.setHpr(math.degrees(math.atan2(dy, dx)), -90, 0)
    card.setColor(Vec4(*color))
    card.setTransparency(TransparencyAttrib.M_alpha)
    card.setLightOff(True)
    card.setPythonTag("holoutopia_city_world_style", True)
    # Subtle curbs only; no traffic/lane markings.
    px = -dy / length
    py = dx / length
    curb = (0.12, 0.14, 0.16, 0.72)
    left0 = (x0 + px * width * 0.5, y0 + py * width * 0.5, z + 0.035)
    left1 = (x1 + px * width * 0.5, y1 + py * width * 0.5, z + 0.035)
    right0 = (x0 - px * width * 0.5, y0 - py * width * 0.5, z + 0.035)
    right1 = (x1 - px * width * 0.5, y1 - py * width * 0.5, z + 0.035)
    _line3d(parent, f"{name}_curb_l", [left0, left1], curb, 1.0)
    _line3d(parent, f"{name}_curb_r", [right0, right1], curb, 1.0)
    return card


def _district_pad(parent: Any, town_id: str, cx: float, cy: float, half_w: float, half_h: float, z: float, theme: tuple[float, float, float, float]) -> None:
    try:
        from panda3d.core import CardMaker, TransparencyAttrib, Vec4
    except Exception:
        return
    cm = CardMaker(f"{town_id}_district_world_pad")
    cm.setFrame(-half_w, half_w, -half_h, half_h)
    pad = parent.attachNewNode(cm.generate())
    pad.setPos(cx, cy, z)
    pad.setHpr(0, -90, 0)
    pad.setColor(Vec4(0.010 + theme[0] * 0.025, 0.014 + theme[1] * 0.025, 0.018 + theme[2] * 0.025, 0.86))
    pad.setTransparency(TransparencyAttrib.M_alpha)
    pad.setLightOff(True)
    pad.setPythonTag("holoutopia_city_world_style", True)
    inset_w = half_w * 0.97
    inset_h = half_h * 0.96
    corners = [
        (cx - inset_w, cy - inset_h, z + 0.045),
        (cx + inset_w, cy - inset_h, z + 0.045),
        (cx + inset_w, cy + inset_h, z + 0.045),
        (cx - inset_w, cy + inset_h, z + 0.045),
    ]
    frame_color = (min(1.0, theme[0] + 0.10), min(1.0, theme[1] + 0.10), min(1.0, theme[2] + 0.10), 0.62)
    _line3d(parent, f"{town_id}_district_world_frame", corners, frame_color, 2.2, closed=True)
    # Angle ticks make the atlas read like connected sectors without label text.
    tick = min(half_w, half_h) * 0.16
    for idx, (sx, sy) in enumerate(((-1, -1), (1, -1), (1, 1), (-1, 1))):
        ox = cx + sx * inset_w
        oy = cy + sy * inset_h
        _line3d(parent, f"{town_id}_district_corner_tick_{idx}a", [(ox, oy, z + 0.075), (ox - sx * tick, oy, z + 0.075)], frame_color, 1.3)
        _line3d(parent, f"{town_id}_district_corner_tick_{idx}b", [(ox, oy, z + 0.075), (ox, oy - sy * tick, z + 0.075)], frame_color, 1.3)

def _attach_district_atlas_depth(parent: Any, town_id: str, cx: float, cy: float, half_w: float, half_h: float, z: float, theme: tuple[float, float, float, float]) -> None:
    """Pass 45: add subtle neon depth and lived-in boundary nodes.

    These are not roads/traffic lines.  They are dim atlas glow plates, side
    service nodes, and short vertical light pylons that help the city read like
    a polished neon strategy-map view from high camera angles.
    """
    halo = (0.020 + theme[0] * 0.035, 0.020 + theme[1] * 0.035, 0.026 + theme[2] * 0.040, 0.38)
    inner_halo = (0.016 + theme[0] * 0.028, 0.018 + theme[1] * 0.028, 0.024 + theme[2] * 0.032, 0.52)
    _rect_surface(parent, f"{town_id}_atlas_outer_halo", cx, cy, half_w * 1.065, half_h * 1.055, z - 0.022, halo)
    _rect_surface(parent, f"{town_id}_atlas_inner_halo", cx, cy, half_w * 0.78, half_h * 0.73, z + 0.028, inner_halo)

    glow = (min(1.0, theme[0] + 0.18), min(1.0, theme[1] + 0.18), min(1.0, theme[2] + 0.18), 0.46)
    pale = (min(1.0, theme[0] + 0.34), min(1.0, theme[1] + 0.34), min(1.0, theme[2] + 0.34), 0.34)
    for idx, scale in enumerate((1.01, 0.88, 0.58)):
        hw = half_w * scale
        hh = half_h * scale
        zz = z + 0.17 + idx * 0.020
        corners = [(cx - hw, cy - hh, zz), (cx + hw, cy - hh, zz), (cx + hw, cy + hh, zz), (cx - hw, cy + hh, zz)]
        _line3d(parent, f"{town_id}_atlas_depth_frame_{idx}", corners, glow if idx < 2 else pale, 1.15 if idx < 2 else 0.85, closed=True)

    # Mid-edge service pylons visually mark district entrances without adding labels.
    mids = [
        (cx, cy - half_h * 0.985, 0.0),
        (cx + half_w * 0.985, cy, math.pi * 0.5),
        (cx, cy + half_h * 0.985, math.pi),
        (cx - half_w * 0.985, cy, math.pi * 1.5),
    ]
    for idx, (px, py, angle) in enumerate(mids):
        h0 = z + 0.22
        h1 = h0 + 8.0 + (idx % 2) * 2.5
        _line3d(parent, f"{town_id}_atlas_gateway_pylon_{idx}", [(px, py, h0), (px, py, h1)], glow, 1.55)
        wing = min(half_w, half_h) * 0.055
        tx = math.cos(angle + math.pi * 0.5) * wing
        ty = math.sin(angle + math.pi * 0.5) * wing
        _line3d(parent, f"{town_id}_atlas_gateway_cap_{idx}", [(px - tx, py - ty, h1), (px + tx, py + ty, h1)], pale, 1.05)

    # Tiny non-label life ticks around the district border.  Kept sparse and low.
    positions = [
        (cx - half_w * 0.70, cy - half_h * 0.94), (cx - half_w * 0.34, cy - half_h * 0.94),
        (cx + half_w * 0.32, cy - half_h * 0.94), (cx + half_w * 0.68, cy - half_h * 0.94),
        (cx + half_w * 0.94, cy - half_h * 0.45), (cx + half_w * 0.94, cy + half_h * 0.06),
        (cx + half_w * 0.94, cy + half_h * 0.52), (cx + half_w * 0.38, cy + half_h * 0.94),
        (cx - half_w * 0.20, cy + half_h * 0.94), (cx - half_w * 0.78, cy + half_h * 0.94),
        (cx - half_w * 0.94, cy + half_h * 0.36), (cx - half_w * 0.94, cy - half_h * 0.28),
    ]
    for idx, (px, py) in enumerate(positions):
        if idx % 3 == 0:
            col = pale
        elif idx % 3 == 1:
            col = (0.26, 1.0, 0.95, 0.32)
        else:
            col = glow
        _line3d(parent, f"{town_id}_atlas_life_tick_{idx:02d}", [(px, py, z + 0.18), (px, py, z + 2.6 + (idx % 2) * 1.2)], col, 0.95)


def _attach_road_flow_nodes(parent: Any, name: str, x0: float, y0: float, x1: float, y1: float, z: float, theme: tuple[float, float, float, float], *, count: int = 5) -> None:
    """Small commute/energy beacons along dark roads; deliberately not lane lines."""
    count = max(2, int(count))
    for idx in range(count):
        t = (idx + 1) / float(count + 1)
        px = x0 + (x1 - x0) * t
        py = y0 + (y1 - y0) * t
        height = 2.8 + (idx % 3) * 1.2
        col = (theme[0], theme[1], theme[2], 0.42) if idx % 2 else (0.20, 1.0, 0.95, 0.36)
        _line3d(parent, f"{name}_flow_node_{idx:02d}", [(px, py, z + 0.20), (px, py, z + height)], col, 1.0)


def _attach_atlas_ring_nodes(parent: Any, center_x: float, center_y: float, radius: float, z: float, *, name: str, count: int = 24) -> None:
    """Subtle node lights on ring-road edges without creating lane stripes."""
    for idx in range(max(8, int(count))):
        a = math.tau * idx / max(8, int(count))
        px = center_x + math.cos(a) * radius
        py = center_y + math.sin(a) * radius
        col = (0.22, 1.0, 0.95, 0.38) if idx % 2 == 0 else (0.90, 0.28, 1.0, 0.34)
        _line3d(parent, f"{name}_node_{idx:02d}", [(px, py, z + 0.18), (px, py, z + 3.6 + (idx % 4) * 0.65)], col, 0.85)


def _motif_color(theme: tuple[float, float, float, float], alpha: float = 0.46) -> tuple[float, float, float, float]:
    return (min(1.0, theme[0] + 0.26), min(1.0, theme[1] + 0.26), min(1.0, theme[2] + 0.26), alpha)


def _attach_district_surface_motifs(parent: Any, town_id: str, cx: float, cy: float, half_w: float, half_h: float, z: float, theme: tuple[float, float, float, float]) -> None:
    """Pass 46: low themed floor motifs inside district pads.

    These are atlas-surface glyphs, not traffic lines: they stay inside district
    plazas/pads and help every district read differently from the high camera.
    """
    tid = str(town_id or "").lower()
    if "central" in tid or "core" in tid:
        return
    col = _motif_color(theme, 0.42)
    ghost = (theme[0], theme[1], theme[2], 0.24)
    zz = z + 0.32
    sx = half_w
    sy = half_h

    def rect(name: str, ox: float, oy: float, w: float, h: float, color: tuple[float, float, float, float] = col, thickness: float = 0.95) -> None:
        pts = [(cx + ox - w, cy + oy - h, zz), (cx + ox + w, cy + oy - h, zz), (cx + ox + w, cy + oy + h, zz), (cx + ox - w, cy + oy + h, zz)]
        _line3d(parent, f"{town_id}_motif_{name}", pts, color, thickness, closed=True)

    if "residential" in tid:
        for idx, (ox, oy) in enumerate(((-0.26, -0.20), (0.05, -0.20), (0.36, -0.18), (-0.12, 0.22), (0.24, 0.25))):
            rect(f"garden_plot_{idx}", sx * ox, sy * oy, sx * 0.080, sy * 0.045, col, 0.95)
            _line3d(parent, f"{town_id}_motif_garden_seed_{idx}", [(cx + sx * ox, cy + sy * oy, zz + 0.02), (cx + sx * ox, cy + sy * oy, zz + 2.4)], (0.46, 1.0, 0.62, 0.46), 0.8)
        for idx, yy in enumerate((-0.42, 0.42)):
            _line3d(parent, f"{town_id}_motif_res_walk_{idx}", [(cx - sx * 0.46, cy + sy * yy, zz), (cx + sx * 0.46, cy + sy * yy, zz)], ghost, 0.8)
    elif "harbor" in tid:
        for idx, oy in enumerate((-0.35, -0.18, 0.02, 0.22, 0.40)):
            pts = []
            for step in range(28):
                t = step / 27.0
                x = cx - sx * 0.48 + sx * 0.96 * t
                y = cy + sy * oy + math.sin(t * math.tau * 2.0 + idx * 0.55) * sy * 0.035
                pts.append((x, y, zz))
            _line3d(parent, f"{town_id}_motif_wave_{idx}", pts, col if idx % 2 else ghost, 0.95)
    elif "industrial" in tid:
        for idx, ox in enumerate((-0.42, -0.21, 0.0, 0.21, 0.42)):
            _line3d(parent, f"{town_id}_motif_pipe_v_{idx}", [(cx + sx * ox, cy - sy * 0.46, zz), (cx + sx * ox, cy + sy * 0.46, zz)], col if idx % 2 else ghost, 0.9)
        for idx, oy in enumerate((-0.33, -0.11, 0.11, 0.33)):
            _line3d(parent, f"{town_id}_motif_pipe_h_{idx}", [(cx - sx * 0.46, cy + sy * oy, zz), (cx + sx * 0.46, cy + sy * oy, zz)], ghost, 0.75)
    elif "archive" in tid:
        for idx, ox in enumerate((-0.44, -0.30, -0.16, -0.02, 0.12, 0.26, 0.40)):
            _line3d(parent, f"{town_id}_motif_data_column_{idx}", [(cx + sx * ox, cy - sy * 0.42, zz), (cx + sx * ox, cy + sy * 0.42, zz)], col if idx % 2 else ghost, 0.85)
            for bit in range(3):
                by = -0.28 + bit * 0.24 + (0.055 if idx % 2 else 0.0)
                rect(f"data_bit_{idx}_{bit}", sx * ox, sy * by, sx * 0.018, sy * 0.022, col, 0.70)
    elif "security" in tid:
        for idx, yy in enumerate((-0.38, -0.18, 0.02, 0.22, 0.42)):
            pts = [(cx - sx * 0.42, cy + sy * yy, zz), (cx - sx * 0.24, cy + sy * (yy + 0.08), zz), (cx - sx * 0.06, cy + sy * yy, zz), (cx + sx * 0.12, cy + sy * (yy + 0.08), zz), (cx + sx * 0.42, cy + sy * yy, zz)]
            _line3d(parent, f"{town_id}_motif_scan_chevron_{idx}", pts, col if idx % 2 else (1.0, 0.24, 0.16, 0.38), 1.0)
    elif "glitched" in tid or "quarantine" in tid:
        colors = [(1.0, 0.16, 0.10, 0.52), (0.24, 1.0, 0.44, 0.42), (0.20, 1.0, 1.0, 0.35)]
        for idx in range(9):
            x0 = cx + sx * (-0.48 + idx * 0.12)
            y0 = cy + sy * (-0.40 + ((idx * 37) % 80) / 100.0)
            pts = [(x0, y0, zz), (x0 + sx * 0.07, y0 + sy * 0.07, zz + 0.03), (x0 + sx * 0.025, y0 + sy * 0.15, zz + 0.02), (x0 + sx * 0.16, y0 + sy * 0.22, zz + 0.03)]
            _line3d(parent, f"{town_id}_motif_glitch_crack_{idx}", pts, colors[idx % len(colors)], 1.0)
    elif "market" in tid:
        for idx, (ox, oy) in enumerate(((-0.32, -0.30), (0.0, -0.30), (0.32, -0.30), (-0.18, 0.05), (0.18, 0.05), (-0.32, 0.34), (0.0, 0.34), (0.32, 0.34))):
            diamond = [(cx + sx * ox, cy + sy * (oy - 0.075), zz), (cx + sx * (ox + 0.065), cy + sy * oy, zz), (cx + sx * ox, cy + sy * (oy + 0.075), zz), (cx + sx * (ox - 0.065), cy + sy * oy, zz)]
            _line3d(parent, f"{town_id}_motif_market_diamond_{idx}", diamond, col if idx % 2 else (1.0, 0.78, 0.18, 0.42), 1.0, closed=True)
    elif "civic" in tid:
        for idx, radius in enumerate((0.18, 0.30, 0.42)):
            _line3d(parent, f"{town_id}_motif_commons_ring_{idx}", _circle_points(cx, cy, min(sx, sy) * radius, zz + idx * 0.025, segments=80), col if idx != 1 else ghost, 1.0)
        for spoke in range(8):
            a = math.tau * spoke / 8.0
            _line3d(parent, f"{town_id}_motif_commons_spoke_{spoke}", [(cx, cy, zz), (cx + math.cos(a) * sx * 0.43, cy + math.sin(a) * sy * 0.43, zz)], ghost, 0.75)
    else:
        for idx, radius in enumerate((0.20, 0.36)):
            _line3d(parent, f"{town_id}_motif_default_ring_{idx}", _circle_points(cx, cy, min(sx, sy) * radius, zz, segments=64), col, 0.85)


def _attach_atlas_skyway_ribbon(parent: Any, name: str, x0: float, y0: float, x1: float, y1: float, z: float, color: tuple[float, float, float, float], *, height: float = 46.0, count: int = 20) -> None:
    """Elevated visual-only transit/energy ribbon, not a traffic lane."""
    points: list[tuple[float, float, float]] = []
    for idx in range(max(4, int(count)) + 1):
        t = idx / float(max(4, int(count)))
        ease = math.sin(math.pi * t)
        sway = math.sin(math.tau * t) * 8.0
        dx = x1 - x0
        dy = y1 - y0
        dist = max(1.0, math.hypot(dx, dy))
        nx = -dy / dist
        ny = dx / dist
        points.append((x0 + dx * t + nx * sway, y0 + dy * t + ny * sway, z + height * ease + 7.0))
    _line3d(parent, f"{name}_skyway_ribbon", points, color, 1.15)
    for idx in range(3, len(points), 5):
        px, py, pz = points[idx]
        _line3d(parent, f"{name}_skyway_drop_{idx}", [(px, py, z + 0.7), (px, py, pz - 1.2)], (color[0], color[1], color[2], min(0.30, color[3] * 0.50)), 0.65)



def _rect_surface(parent: Any, name: str, cx: float, cy: float, half_w: float, half_h: float, z: float, color: tuple[float, float, float, float], *, heading: float = 0.0) -> Any | None:
    """Attach a flat translucent rectangle for district feature pads/pools."""
    try:
        from panda3d.core import CardMaker, TransparencyAttrib, Vec4
    except Exception:
        return None
    cm = CardMaker(f"{name}_surface")
    cm.setFrame(-float(half_w), float(half_w), -float(half_h), float(half_h))
    card = parent.attachNewNode(cm.generate())
    card.setPos(float(cx), float(cy), float(z))
    card.setHpr(float(heading), -90, 0)
    card.setColor(Vec4(*color))
    card.setTransparency(TransparencyAttrib.M_alpha)
    card.setLightOff(True)
    card.setPythonTag("holoutopia_city_world_style", True)
    return card


def _wire_box(parent: Any, name: str, cx: float, cy: float, w: float, d: float, h: float, z: float, color: tuple[float, float, float, float], *, thickness: float = 1.5) -> None:
    """Simple collisionless rectangular landmark volume."""
    hw = float(w) * 0.5
    hd = float(d) * 0.5
    z0 = float(z)
    z1 = float(z) + float(h)
    bottom = [(cx - hw, cy - hd, z0), (cx + hw, cy - hd, z0), (cx + hw, cy + hd, z0), (cx - hw, cy + hd, z0)]
    top = [(cx - hw, cy - hd, z1), (cx + hw, cy - hd, z1), (cx + hw, cy + hd, z1), (cx - hw, cy + hd, z1)]
    _line3d(parent, f"{name}_base", bottom, color, thickness, closed=True)
    _line3d(parent, f"{name}_top", top, color, thickness, closed=True)
    for idx in range(4):
        _line3d(parent, f"{name}_edge_{idx}", [bottom[idx], top[idx]], color, max(1.0, thickness * 0.82))
    if h > 18.0:
        for frac in (0.33, 0.66):
            zz = z0 + h * frac
            band = [(cx - hw, cy - hd, zz), (cx + hw, cy - hd, zz), (cx + hw, cy + hd, zz), (cx - hw, cy + hd, zz)]
            _line3d(parent, f"{name}_band_{int(frac*100)}", band, (color[0], color[1], color[2], min(color[3], 0.55)), max(0.9, thickness * 0.60), closed=True)


def _wire_prism(parent: Any, name: str, cx: float, cy: float, radius: float, height: float, z: float, color: tuple[float, float, float, float], *, sides: int = 6, thickness: float = 1.5, twist: float = 0.0) -> None:
    """Cylindrical/hexagonal skyline accent without mesh/collision."""
    pts0: list[tuple[float, float, float]] = []
    pts1: list[tuple[float, float, float]] = []
    for idx in range(max(3, int(sides))):
        a = twist + math.tau * idx / max(3, int(sides))
        pts0.append((cx + math.cos(a) * radius, cy + math.sin(a) * radius, z))
        pts1.append((cx + math.cos(a) * radius, cy + math.sin(a) * radius, z + height))
    _line3d(parent, f"{name}_base", pts0, color, thickness, closed=True)
    _line3d(parent, f"{name}_top", pts1, color, thickness, closed=True)
    for idx, p in enumerate(pts0):
        _line3d(parent, f"{name}_rib_{idx}", [p, pts1[idx]], color, max(1.0, thickness * 0.75))


def _dome_marker(parent: Any, name: str, cx: float, cy: float, radius: float, z: float, color: tuple[float, float, float, float]) -> None:
    """Layered wire dome marker for civic/park/water district landmarks."""
    for idx, scale in enumerate((1.0, 0.74, 0.46)):
        _line3d(parent, f"{name}_ring_{idx}", _circle_points(cx, cy, radius * scale, z + 1.2 + idx * 5.2, segments=72), color, 1.7)
    for spoke in range(8):
        a = math.tau * spoke / 8.0
        _line3d(parent, f"{name}_dome_spoke_{spoke}", [(cx, cy, z + 17.5), (cx + math.cos(a) * radius, cy + math.sin(a) * radius, z + 1.4)], color, 1.05)


def _tower_pair(parent: Any, name: str, cx: float, cy: float, theme: tuple[float, float, float, float], *, height: float = 58.0, spacing: float = 16.0) -> None:
    _wire_box(parent, f"{name}_tower_a", cx - spacing * 0.5, cy, 10.0, 10.0, height, 2.0, theme, thickness=1.7)
    _wire_box(parent, f"{name}_tower_b", cx + spacing * 0.5, cy, 10.0, 10.0, height * 0.86, 2.0, theme, thickness=1.7)
    _line3d(parent, f"{name}_skybridge", [(cx - spacing * 0.5, cy, height * 0.58), (cx + spacing * 0.5, cy, height * 0.52)], theme, 1.4)


def _tree_glyph(parent: Any, name: str, cx: float, cy: float, z: float, color: tuple[float, float, float, float]) -> None:
    trunk = (0.40, 0.78, 0.42, 0.60)
    _line3d(parent, f"{name}_trunk", [(cx, cy, z), (cx, cy, z + 7.0)], trunk, 1.2)
    crown = [(cx, cy, z + 13.0), (cx - 5.5, cy - 3.5, z + 6.4), (cx + 5.5, cy - 3.5, z + 6.4), (cx, cy, z + 13.0), (cx + 4.5, cy + 4.5, z + 6.2), (cx - 4.5, cy + 4.5, z + 6.2), (cx, cy, z + 13.0)]
    _line3d(parent, f"{name}_crown", crown, color, 1.3)


def _attach_district_landmarks(parent: Any, town_id: str, cx: float, cy: float, half_w: float, half_h: float, z: float, theme: tuple[float, float, float, float]) -> None:
    """Add district-specific readable landmarks visible from world-atlas camera.

    This is deliberately collisionless and data-free: the authored buildings stay
    authoritative, while this layer supplies skyline language that helps every
    district read differently from the observer/world view.
    """
    tid = str(town_id or "").lower()
    accent = (min(1.0, theme[0] + 0.20), min(1.0, theme[1] + 0.20), min(1.0, theme[2] + 0.20), min(0.92, theme[3] + 0.05))
    ghost = (theme[0], theme[1], theme[2], 0.33)
    sx = half_w * 0.34
    sy = half_h * 0.30
    base_z = z + 0.40

    if "central" in tid or "core" in tid:
        return
    if "archive" in tid:
        _tower_pair(parent, f"{town_id}_memory_spires", cx - sx * 0.45, cy + sy * 0.18, accent, height=68.0, spacing=18.0)
        _wire_prism(parent, f"{town_id}_memory_crystal", cx + sx * 0.40, cy - sy * 0.10, 9.0, 48.0, base_z, accent, sides=5, thickness=1.7, twist=0.2)
        _line3d(parent, f"{town_id}_data_arc", _circle_points(cx + sx * 0.05, cy, min(half_w, half_h) * 0.16, base_z + 17.0, segments=56), ghost, 1.6)
    elif "harbor" in tid:
        water = (0.00, 0.55, 0.80, 0.40)
        _rect_surface(parent, f"{town_id}_water_basin_a", cx - sx * 0.20, cy - sy * 0.05, half_w * 0.20, half_h * 0.105, base_z + 0.03, water, heading=7.0)
        _rect_surface(parent, f"{town_id}_water_basin_b", cx + sx * 0.34, cy + sy * 0.20, half_w * 0.145, half_h * 0.085, base_z + 0.04, water, heading=-13.0)
        _dome_marker(parent, f"{town_id}_tidal_dome", cx - sx * 0.52, cy + sy * 0.32, min(half_w, half_h) * 0.09, base_z + 0.2, accent)
        for idx in range(4):
            xx = cx + sx * (-0.04 + idx * 0.20)
            _wire_box(parent, f"{town_id}_dock_pylon_{idx}", xx, cy - sy * 0.45, 5.0, 5.0, 16.0 + idx * 3.0, base_z, accent, thickness=1.25)
    elif "glitched" in tid or "quarantine" in tid:
        warn = (1.0, 0.18, 0.12, 0.92)
        green = (0.20, 1.0, 0.44, 0.80)
        for idx, (ox, oy, h) in enumerate(((-0.38, 0.25, 58.0), (-0.08, -0.12, 44.0), (0.28, 0.18, 66.0), (0.48, -0.32, 38.0))):
            _wire_prism(parent, f"{town_id}_fracture_spike_{idx}", cx + sx * ox, cy + sy * oy, 6.0 + idx, h, base_z, warn if idx % 2 == 0 else green, sides=3 + (idx % 2), thickness=1.65, twist=0.35 * idx)
        zig = [(cx - sx * 0.55, cy - sy * 0.48, base_z + 5.0), (cx - sx * 0.25, cy - sy * 0.30, base_z + 12.0), (cx, cy - sy * 0.50, base_z + 8.0), (cx + sx * 0.35, cy - sy * 0.25, base_z + 16.0), (cx + sx * 0.55, cy - sy * 0.42, base_z + 9.0)]
        _line3d(parent, f"{town_id}_glitch_fracture_line", zig, green, 1.8)
    elif "residential" in tid:
        home = (0.52, 1.0, 0.74, 0.86)
        _tower_pair(parent, f"{town_id}_home_towers", cx - sx * 0.20, cy + sy * 0.08, home, height=42.0, spacing=20.0)
        _dome_marker(parent, f"{town_id}_garden_courtyard", cx + sx * 0.38, cy - sy * 0.18, min(half_w, half_h) * 0.12, base_z, home)
        for idx, ox in enumerate((-0.55, -0.38, 0.02, 0.18, 0.56)):
            _tree_glyph(parent, f"{town_id}_street_tree_{idx}", cx + sx * ox, cy - sy * 0.50 + (idx % 2) * 12.0, base_z, home)
    elif "security" in tid:
        yellow = (1.0, 0.86, 0.20, 0.88)
        red = (1.0, 0.18, 0.14, 0.72)
        _wire_box(parent, f"{town_id}_gate_left", cx - sx * 0.34, cy - sy * 0.10, 12.0, 14.0, 50.0, base_z, yellow, thickness=1.8)
        _wire_box(parent, f"{town_id}_gate_right", cx + sx * 0.34, cy - sy * 0.10, 12.0, 14.0, 50.0, base_z, yellow, thickness=1.8)
        _line3d(parent, f"{town_id}_gate_header", [(cx - sx * 0.34, cy - sy * 0.10, base_z + 48.0), (cx + sx * 0.34, cy - sy * 0.10, base_z + 48.0)], yellow, 2.2)
        for idx, oy in enumerate((-0.42, 0.12, 0.48)):
            _line3d(parent, f"{town_id}_security_scan_lanes_{idx}", [(cx - sx * 0.58, cy + sy * oy, base_z + 2.0), (cx + sx * 0.58, cy + sy * oy, base_z + 2.0)], red if idx == 1 else ghost, 1.4)
    elif "civic" in tid:
        park = (0.24, 1.0, 0.40, 0.82)
        blue = (0.20, 0.76, 1.0, 0.76)
        _dome_marker(parent, f"{town_id}_commons_dome", cx - sx * 0.25, cy + sy * 0.10, min(half_w, half_h) * 0.15, base_z, blue)
        _wire_prism(parent, f"{town_id}_civic_monument", cx + sx * 0.34, cy - sy * 0.06, 8.0, 54.0, base_z, blue, sides=8, thickness=1.65)
        for idx, (ox, oy) in enumerate(((-0.52, -0.40), (-0.38, 0.45), (0.04, -0.50), (0.52, 0.32), (0.54, -0.28))):
            _tree_glyph(parent, f"{town_id}_park_tree_{idx}", cx + sx * ox, cy + sy * oy, base_z, park)
    elif "market" in tid:
        gold = (1.0, 0.78, 0.18, 0.88)
        magenta = (1.0, 0.24, 0.78, 0.80)
        for idx, ox in enumerate((-0.42, -0.18, 0.08, 0.34)):
            _wire_box(parent, f"{town_id}_canopy_{idx}", cx + sx * ox, cy - sy * 0.20 + (idx % 2) * 14.0, 18.0, 10.0, 11.0, base_z, gold if idx % 2 == 0 else magenta, thickness=1.35)
            _line3d(parent, f"{town_id}_canopy_peak_{idx}", [(cx + sx * ox - 9.0, cy - sy * 0.20 + (idx % 2) * 14.0, base_z + 11.0), (cx + sx * ox, cy - sy * 0.20 + (idx % 2) * 14.0, base_z + 19.0), (cx + sx * ox + 9.0, cy - sy * 0.20 + (idx % 2) * 14.0, base_z + 11.0)], gold if idx % 2 == 0 else magenta, 1.25)
        _line3d(parent, f"{town_id}_market_arc", _circle_points(cx, cy + sy * 0.28, min(half_w, half_h) * 0.13, base_z + 7.0, segments=64), magenta, 1.9)
    elif "industrial" in tid:
        pipe = (1.0, 0.38, 0.86, 0.86)
        amber = (1.0, 0.55, 0.20, 0.78)
        for idx, ox in enumerate((-0.42, -0.22, 0.12, 0.38)):
            _wire_prism(parent, f"{town_id}_stack_{idx}", cx + sx * ox, cy + sy * (0.20 if idx % 2 else -0.06), 5.0 + idx, 38.0 + idx * 8.0, base_z, pipe if idx % 2 else amber, sides=8, thickness=1.55)
        _line3d(parent, f"{town_id}_overhead_pipe_a", [(cx - sx * 0.55, cy - sy * 0.34, base_z + 18.0), (cx + sx * 0.52, cy + sy * 0.16, base_z + 22.0)], pipe, 2.0)
        _line3d(parent, f"{town_id}_overhead_pipe_b", [(cx - sx * 0.48, cy + sy * 0.34, base_z + 12.0), (cx + sx * 0.45, cy - sy * 0.18, base_z + 16.0)], amber, 1.5)
    else:
        _wire_box(parent, f"{town_id}_district_landmark", cx, cy, 22.0, 22.0, 36.0, base_z, accent, thickness=1.5)


def _central_hub(parent: Any, cx: float, cy: float, frame_w: float, frame_h: float, z: float) -> None:
    """Attach the high-readability raised Simulation/Core plaza.

    Pass 44 intentionally lifts and widens the hub above the local authored
    central-town pads.  This gives the city atlas a real center mass instead of
    a thin ring line hidden below surrounding blocks.
    """
    purple = (0.82, 0.28, 1.0, 0.94)
    cyan = (0.20, 1.0, 0.96, 0.84)
    magenta = (1.0, 0.24, 0.72, 0.90)
    white_core = (0.86, 0.98, 1.0, 0.82)
    base_dark = (0.022, 0.014, 0.038, 0.96)
    radius = min(frame_w, frame_h) * 0.415
    lift = z + 1.10

    # High dark clearance plate: hides low central block pads and creates a
    # deliberate plaza void around the hub without adding collision.
    _flat_disc(parent, "central_simulation_hub_clearance_plate", cx, cy, radius * 1.58, lift + 0.010, (0.010, 0.008, 0.016, 0.95), segments=160)
    _flat_annulus(parent, "central_simulation_hub_moat_shadow", cx, cy, radius * 1.38, radius * 1.58, lift + 0.020, (0.022, 0.018, 0.032, 0.90), segments=160)

    # Solid layered plaza surfaces: these broad planes make the core read as
    # architecture from world view, not line art below buildings.
    _flat_disc(parent, "central_simulation_hub_lower_plaza", cx, cy, radius * 1.34, lift + 0.060, base_dark, segments=160)
    _flat_annulus(parent, "central_simulation_hub_outer_walk_ring", cx, cy, radius * 1.03, radius * 1.30, lift + 0.105, (0.060, 0.032, 0.086, 0.90), segments=160)
    _flat_disc(parent, "central_simulation_hub_upper_plinth", cx, cy, radius * 0.76, lift + 0.170, (0.070, 0.032, 0.105, 0.94), segments=128)
    _flat_annulus(parent, "central_simulation_hub_inner_gallery", cx, cy, radius * 0.48, radius * 0.66, lift + 0.240, (0.085, 0.040, 0.130, 0.92), segments=128)
    _flat_disc(parent, "central_simulation_hub_core_floor", cx, cy, radius * 0.34, lift + 0.310, (0.090, 0.045, 0.145, 0.96), segments=96)

    # Thick bright outlines and stepped retaining walls create real silhouette.
    for idx, rr in enumerate((1.56, 1.34, 1.03, 0.76, 0.56, 0.34)):
        color = purple if idx % 2 == 0 else cyan
        zz = lift + 1.15 + idx * 0.72
        _line3d(parent, f"central_simulation_hub_visible_ring_{idx}", _circle_points(cx, cy, radius * rr, zz, segments=160), color, 3.4 if idx < 3 else 2.35)
    for wall_idx, rr in enumerate((1.29, 0.76, 0.50)):
        for tick in range(32 if wall_idx == 0 else 24):
            a = math.tau * tick / (32 if wall_idx == 0 else 24)
            x = cx + math.cos(a) * radius * rr
            y = cy + math.sin(a) * radius * rr
            h0 = lift + 0.62 + wall_idx * 0.72
            h1 = h0 + (10.0 if wall_idx == 0 else 7.2) + (tick % 4) * 1.15
            _line3d(parent, f"central_simulation_hub_retaining_wall_{wall_idx}_{tick:02d}", [(x, y, h0), (x, y, h1)], purple if tick % 2 else cyan, 1.55)

    # Broad spokes/bridges tie the surrounding districts into the raised plaza.
    for spoke in range(12):
        a = math.tau * spoke / 12.0
        inner = radius * 0.38
        outer = radius * 1.48
        color = cyan if spoke % 3 == 0 else purple
        _line3d(parent, f"central_simulation_hub_spoke_{spoke:02d}", [
            (cx + math.cos(a) * inner, cy + math.sin(a) * inner, lift + 2.15),
            (cx + math.cos(a) * outer, cy + math.sin(a) * outer, lift + 2.15),
        ], color, 2.15)
        if spoke % 3 == 0:
            _line3d(parent, f"central_simulation_hub_bridge_tick_{spoke:02d}", [
                (cx + math.cos(a) * radius * 1.12, cy + math.sin(a) * radius * 1.12, lift + 2.35),
                (cx + math.cos(a) * radius * 1.28, cy + math.sin(a) * radius * 1.28, lift + 7.80),
            ], white_core, 1.25)

    # Pyramid/core glyph, intentionally tall and central so it anchors the city.
    p = radius * 0.235
    base_z = lift + 6.4
    mid_z = lift + 38.0
    top_z = lift + 92.0
    corners = [(cx - p, cy - p, base_z), (cx + p, cy - p, base_z), (cx + p, cy + p, base_z), (cx - p, cy + p, base_z)]
    _line3d(parent, "central_simulation_hub_pyramid_base", corners, magenta, 3.0, closed=True)
    for idx, corner in enumerate(corners):
        _line3d(parent, f"central_simulation_hub_pyramid_edge_{idx}", [corner, (cx, cy, top_z)], magenta, 2.65)
    # Mid-level ring/dome makes it look like a civic-simulation building, not a marker.
    _line3d(parent, "central_simulation_hub_core_mid_ring", _circle_points(cx, cy, p * 1.08, mid_z, segments=80), cyan, 2.10)
    for idx in range(8):
        a = math.tau * idx / 8.0
        _line3d(parent, f"central_simulation_hub_core_dome_rib_{idx}", [
            (cx + math.cos(a) * p * 1.08, cy + math.sin(a) * p * 1.08, mid_z),
            (cx, cy, top_z),
        ], white_core if idx % 2 else cyan, 1.40)
    _line3d(parent, "central_simulation_hub_vertical_beam", [(cx, cy, base_z), (cx, cy, top_z + 62.0)], white_core, 3.2)

    # Hovering crown rings and small light posts reinforce the hub as a civic/simulation anchor.
    for idx, (rr, zz, col) in enumerate(((0.25, top_z + 13.0, cyan), (0.36, top_z + 24.0, purple), (0.18, top_z + 36.0, white_core))):
        _line3d(parent, f"central_simulation_hub_hover_crown_{idx}", _circle_points(cx, cy, radius * rr, zz, segments=96), col, 1.55 if idx < 2 else 1.15)
    for idx in range(20):
        a = math.tau * idx / 20.0
        rr = radius * (0.88 if idx % 2 else 1.16)
        px = cx + math.cos(a) * rr
        py = cy + math.sin(a) * rr
        _line3d(parent, f"central_simulation_hub_plaza_light_{idx:02d}", [(px, py, lift + 2.5), (px, py, lift + 10.0 + (idx % 4) * 1.1)], cyan if idx % 2 else magenta, 1.05)

    # Four large gateway pylons give the hub cardinal entry points in the atlas.
    for idx, a in enumerate((0.0, math.pi * 0.5, math.pi, math.pi * 1.5)):
        gx = cx + math.cos(a) * radius * 1.42
        gy = cy + math.sin(a) * radius * 1.42
        tangent = a + math.pi * 0.5
        wing = 10.0
        left = (gx + math.cos(tangent) * wing, gy + math.sin(tangent) * wing, lift + 2.8)
        right = (gx - math.cos(tangent) * wing, gy - math.sin(tangent) * wing, lift + 2.8)
        crown = (gx, gy, lift + 30.0)
        _line3d(parent, f"central_simulation_hub_gateway_{idx}", [left, crown, right], cyan if idx % 2 == 0 else purple, 2.05)


def attach_holoutopia_central_core_overlay(parent: Any, holoverse_root: Path | str | None = None, *, z: float = 0.72) -> Any:
    """Attach the raised Simulation/Core hub as a late overlay layer.

    The full atlas style owns roads and district pads.  This overlay exists so
    the central hub can be drawn after district massing and activity props,
    preventing small local pads/props from reading as buildings on top of the
    Core in world-view screenshots and normal Watch Mode.
    """
    try:
        from holoutopia_town_blocks import city_frame_metrics, load_city_atlas
    except Exception as exc:  # pragma: no cover - validator-friendly fallback
        raise RuntimeError(f"could not import HoloUtopia town atlas helpers: {exc}") from exc
    atlas = load_city_atlas(_as_root_path(holoverse_root))
    metrics = city_frame_metrics(atlas)
    frame_w = float(metrics["frame_w"])
    frame_h = float(metrics["frame_h"])
    root = parent.attachNewNode("holoutopia_central_core_hub_overlay")
    root.setLightOff(True)
    root.setPythonTag("holoutopia_central_core_overlay", True)
    root.setPythonTag("holoutopia_core_hub_clarity_pass", 44)
    _central_hub(root, frame_w, frame_h, frame_w, frame_h, z)
    return root


def attach_holoutopia_city_world_style(parent: Any, holoverse_root: Path | str | None = None, *, z: float = -0.035) -> Any:
    """Attach collisionless world-atlas visuals beneath the authored districts."""
    try:
        from holoutopia_town_blocks import city_frame_metrics, load_city_atlas
    except Exception as exc:  # pragma: no cover - validator-friendly fallback
        raise RuntimeError(f"could not import HoloUtopia town atlas helpers: {exc}") from exc
    atlas = load_city_atlas(_as_root_path(holoverse_root))
    metrics = city_frame_metrics(atlas)
    root = parent.attachNewNode("holoutopia_city_world_atlas_style")
    root.setLightOff(True)
    root.setPythonTag("holoutopia_city_world_style", True)

    frame_w = float(metrics["frame_w"])
    frame_h = float(metrics["frame_h"])
    center_x = frame_w
    center_y = frame_h
    road_color = (0.026, 0.030, 0.036, 0.98)
    road_width = min(frame_w, frame_h) * 0.105
    # District pads first, then wide dark roads/rings, then central hub on top.
    centers: list[tuple[str, float, float, tuple[float, float, float, float]]] = []
    for entry in atlas.get("towns", []):
        if not isinstance(entry, dict):
            continue
        town_id = str(entry.get("town_id") or "").strip()
        grid = entry.get("city_grid") if isinstance(entry.get("city_grid"), list) else [1, 1]
        if not town_id:
            continue
        try:
            gx, gy = float(grid[0]), float(grid[1])
        except Exception:
            gx, gy = 1.0, 1.0
        x = gx * frame_w
        y = gy * frame_h
        theme = _theme_for_town(town_id)
        half_w = frame_w * 0.465
        half_h = frame_h * 0.455
        _district_pad(root, town_id, x, y, half_w, half_h, z + 0.005, theme)
        _attach_district_atlas_depth(root, town_id, x, y, half_w, half_h, z + 0.075, theme)
        _attach_district_surface_motifs(root, town_id, x, y, half_w, half_h, z + 0.115, theme)
        _attach_district_landmarks(root, town_id, x, y, half_w, half_h, z + 0.18, theme)
        centers.append((town_id, x, y, theme))

    # Global dark street web: ring roads and spokes across the 3x3 city atlas.
    _flat_annulus(root, "holoutopia_atlas_mid_ring_road", center_x, center_y, min(frame_w, frame_h) * 0.43, min(frame_w, frame_h) * 0.43 + road_width, z + 0.030, road_color, segments=160)
    _flat_annulus(root, "holoutopia_atlas_outer_ring_road", center_x, center_y, min(frame_w, frame_h) * 0.78, min(frame_w, frame_h) * 0.78 + road_width * 0.76, z + 0.025, road_color, segments=160)
    _line3d(root, "holoutopia_atlas_mid_ring_curb_outer", _circle_points(center_x, center_y, min(frame_w, frame_h) * 0.43 + road_width, z + 0.090, segments=160), (0.12, 0.14, 0.16, 0.78), 1.2)
    _line3d(root, "holoutopia_atlas_mid_ring_curb_inner", _circle_points(center_x, center_y, min(frame_w, frame_h) * 0.43, z + 0.090, segments=160), (0.12, 0.14, 0.16, 0.78), 1.2)
    _attach_atlas_ring_nodes(root, center_x, center_y, min(frame_w, frame_h) * 0.43 + road_width * 0.52, z + 0.115, name="holoutopia_mid_ring_life", count=32)
    _attach_atlas_ring_nodes(root, center_x, center_y, min(frame_w, frame_h) * 0.78 + road_width * 0.38, z + 0.095, name="holoutopia_outer_ring_life", count=28)
    for town_id, x, y, theme in centers:
        if abs(x - center_x) < 0.001 and abs(y - center_y) < 0.001:
            continue
        dx = x - center_x
        dy = y - center_y
        dist = max(1.0, math.hypot(dx, dy))
        # Start/end leave breathing room around the central hub and district interiors.
        sx = center_x + dx / dist * min(frame_w, frame_h) * 0.34
        sy = center_y + dy / dist * min(frame_w, frame_h) * 0.34
        ex = x - dx / dist * min(frame_w, frame_h) * 0.28
        ey = y - dy / dist * min(frame_w, frame_h) * 0.28
        _road_segment(root, f"holoutopia_atlas_radial_road_{town_id}", sx, sy, ex, ey, road_width * 0.72, z + 0.045, road_color)
        # Themed faint power/conduit lane along each spoke, not a traffic stripe.
        _line3d(root, f"holoutopia_atlas_theme_conduit_{town_id}", [(sx, sy, z + 0.12), (ex, ey, z + 0.12)], (theme[0], theme[1], theme[2], 0.36), 1.0)
        _attach_road_flow_nodes(root, f"holoutopia_atlas_radial_{town_id}", sx, sy, ex, ey, z + 0.135, theme, count=5)

    # Pass 46: a few elevated visual-only skyway ribbons connect the atlas
    # districts to the central Simulation/Core without adding collision or roads.
    for town_id, x, y, theme in centers:
        if abs(x - center_x) < 0.001 and abs(y - center_y) < 0.001:
            continue
        if any(key in town_id.lower() for key in ("residential", "harbor", "archive", "industrial", "glitched", "market")):
            dx = x - center_x
            dy = y - center_y
            dist = max(1.0, math.hypot(dx, dy))
            sx2 = center_x + dx / dist * min(frame_w, frame_h) * 0.52
            sy2 = center_y + dy / dist * min(frame_w, frame_h) * 0.52
            ex2 = x - dx / dist * min(frame_w, frame_h) * 0.18
            ey2 = y - dy / dist * min(frame_w, frame_h) * 0.18
            _attach_atlas_skyway_ribbon(root, f"holoutopia_atlas_{town_id}", sx2, sy2, ex2, ey2, z + 0.22, (theme[0], theme[1], theme[2], 0.40), height=34.0 + (len(town_id) % 5) * 4.0, count=18)

    _central_hub(root, center_x, center_y, frame_w, frame_h, z + 0.10)
    return root


__all__ = ["attach_holoutopia_city_world_style", "attach_holoutopia_central_core_overlay"]
