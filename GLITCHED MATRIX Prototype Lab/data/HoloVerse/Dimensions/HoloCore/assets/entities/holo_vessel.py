"""Walkable HoloCore vessel module.

Generated geometry only.  The vessel uses simple central AABB navigation for
stable walking/collision while the crescent blades stay visual-only.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable

from panda3d.core import (
    CardMaker,
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
)

CYAN = (0.0, 0.92, 1.0, 0.92)
CYAN_DIM = (0.0, 0.58, 1.0, 0.55)
MAGENTA = (1.0, 0.16, 0.82, 0.88)
AMBER = (1.0, 0.42, 0.08, 0.82)
DARK_PANEL = (0.025, 0.055, 0.085, 0.92)
GLASS = (0.0, 0.85, 1.0, 0.16)
FLOOR = (0.02, 0.10, 0.15, 0.90)


def add_line(parent: NodePath, name: str, points: Iterable[tuple[float, float, float]], color=CYAN, thickness: float = 2.0) -> NodePath:
    pts = list(points)
    segs = LineSegs(name)
    segs.setThickness(thickness)
    segs.setColor(*color)
    if pts:
        segs.moveTo(*pts[0])
        for p in pts[1:]:
            segs.drawTo(*p)
    node = parent.attachNewNode(segs.create())
    node.setLightOff()
    node.setTransparency(TransparencyAttrib.MAlpha)
    return node


def add_card(parent: NodePath, name: str, scale: tuple[float, float, float], pos: tuple[float, float, float],
             hpr: tuple[float, float, float] = (0, 0, 0), color=GLASS) -> NodePath:
    cm = CardMaker(name)
    cm.setFrame(-1.0, 1.0, -1.0, 1.0)
    node = parent.attachNewNode(cm.generate())
    node.setScale(*scale)
    node.setPos(*pos)
    node.setHpr(*hpr)
    node.setColor(*color)
    node.setTwoSided(True)
    node.setTransparency(TransparencyAttrib.MAlpha)
    return node


def cube_geom(name: str) -> GeomNode:
    fmt = GeomVertexFormat.getV3n3c4()
    vdata = GeomVertexData(name, fmt, Geom.UHStatic)
    vertex = GeomVertexWriter(vdata, "vertex")
    normal = GeomVertexWriter(vdata, "normal")
    color = GeomVertexWriter(vdata, "color")
    faces = [
        ((0, -1, 0), [(-.5, -.5, -.5), (.5, -.5, -.5), (.5, -.5, .5), (-.5, -.5, .5)]),
        ((0, 1, 0), [(.5, .5, -.5), (-.5, .5, -.5), (-.5, .5, .5), (.5, .5, .5)]),
        ((-1, 0, 0), [(-.5, .5, -.5), (-.5, -.5, -.5), (-.5, -.5, .5), (-.5, .5, .5)]),
        ((1, 0, 0), [(.5, -.5, -.5), (.5, .5, -.5), (.5, .5, .5), (.5, -.5, .5)]),
        ((0, 0, 1), [(-.5, -.5, .5), (.5, -.5, .5), (.5, .5, .5), (-.5, .5, .5)]),
        ((0, 0, -1), [(-.5, .5, -.5), (.5, .5, -.5), (.5, -.5, -.5), (-.5, -.5, -.5)]),
    ]
    tris = GeomTriangles(Geom.UHStatic)
    for face_i, (n, corners) in enumerate(faces):
        base = face_i * 4
        for p in corners:
            vertex.addData3f(*p)
            normal.addData3f(*n)
            color.addData4f(1, 1, 1, 1)
        tris.addVertices(base, base + 1, base + 2)
        tris.addVertices(base, base + 2, base + 3)
    geom = Geom(vdata)
    geom.addPrimitive(tris)
    node = GeomNode(name)
    node.addGeom(geom)
    return node


def add_cube(parent: NodePath, name: str, scale: tuple[float, float, float], pos: tuple[float, float, float],
             color=DARK_PANEL, hpr: tuple[float, float, float] = (0, 0, 0)) -> NodePath:
    node = parent.attachNewNode(cube_geom(name))
    node.setScale(*scale)
    node.setPos(*pos)
    node.setHpr(*hpr)
    node.setColor(*color)
    if color[3] < 1.0:
        node.setTransparency(TransparencyAttrib.MAlpha)
    return node


def add_line_box(parent: NodePath, name: str, center: tuple[float, float, float], size: tuple[float, float, float],
                 color=CYAN, thickness: float = 2.0) -> NodePath:
    cx, cy, cz = center
    sx, sy, sz = size[0] / 2, size[1] / 2, size[2] / 2
    p = [
        (cx-sx, cy-sy, cz-sz), (cx+sx, cy-sy, cz-sz), (cx+sx, cy+sy, cz-sz), (cx-sx, cy+sy, cz-sz),
        (cx-sx, cy-sy, cz+sz), (cx+sx, cy-sy, cz+sz), (cx+sx, cy+sy, cz+sz), (cx-sx, cy+sy, cz+sz),
    ]
    edges = [(0,1),(1,2),(2,3),(3,0),(4,5),(5,6),(6,7),(7,4),(0,4),(1,5),(2,6),(3,7)]
    segs = LineSegs(name)
    segs.setThickness(thickness)
    segs.setColor(*color)
    for a, b in edges:
        segs.moveTo(*p[a])
        segs.drawTo(*p[b])
    node = parent.attachNewNode(segs.create())
    node.setLightOff()
    node.setTransparency(TransparencyAttrib.MAlpha)
    return node


def tapered_box_geom(name: str, front_w: float, rear_w: float, length: float, height: float) -> GeomNode:
    fmt = GeomVertexFormat.getV3n3c4()
    vdata = GeomVertexData(name, fmt, Geom.UHStatic)
    vw = GeomVertexWriter(vdata, "vertex")
    nw = GeomVertexWriter(vdata, "normal")
    cw = GeomVertexWriter(vdata, "color")
    fy, ry = length / 2, -length / 2
    hz = height / 2
    verts = [
        (-rear_w/2, ry, -hz), (rear_w/2, ry, -hz), (rear_w/2, ry, hz), (-rear_w/2, ry, hz),
        (-front_w/2, fy, -hz*0.65), (front_w/2, fy, -hz*0.65), (front_w/2, fy, hz*0.65), (-front_w/2, fy, hz*0.65),
    ]
    faces = [
        (0,1,2,3,(0,-1,0)), (4,7,6,5,(0,1,0)),
        (0,4,5,1,(0,0,-1)), (3,2,6,7,(0,0,1)),
        (0,3,7,4,(-1,0,0)), (1,5,6,2,(1,0,0)),
    ]
    tris = GeomTriangles(Geom.UHStatic)
    for fi, (a,b,c,d,n) in enumerate(faces):
        base = fi*4
        for idx in (a,b,c,d):
            vw.addData3f(*verts[idx])
            nw.addData3f(*n)
            cw.addData4f(1,1,1,1)
        tris.addVertices(base, base+1, base+2)
        tris.addVertices(base, base+2, base+3)
    geom = Geom(vdata)
    geom.addPrimitive(tris)
    node = GeomNode(name)
    node.addGeom(geom)
    return node


def add_tapered_box(parent: NodePath, name: str, front_w: float, rear_w: float, length: float, height: float,
                    pos: tuple[float,float,float], color=DARK_PANEL, hpr=(0,0,0)) -> NodePath:
    node = parent.attachNewNode(tapered_box_geom(name, front_w, rear_w, length, height))
    node.setPos(*pos)
    node.setHpr(*hpr)
    node.setColor(*color)
    if color[3] < 1.0:
        node.setTransparency(TransparencyAttrib.MAlpha)
    return node



def elliptical_tube_geom(name: str, rings: list[tuple[float, float, float, float]], segments: int = 28) -> GeomNode:
    """Create a lightweight rounded hull running along local Y.

    Each ring is (y, radius_x, radius_z, center_z).  This keeps the vessel
    generated and cheap while giving the silhouette a cylindrical body.
    """
    fmt = GeomVertexFormat.getV3n3c4()
    vdata = GeomVertexData(name, fmt, Geom.UHStatic)
    vertex = GeomVertexWriter(vdata, "vertex")
    normal = GeomVertexWriter(vdata, "normal")
    color = GeomVertexWriter(vdata, "color")
    rings = list(rings)
    if len(rings) < 2:
        rings = [(-1.0, 1.0, 1.0, 0.0), (1.0, 1.0, 1.0, 0.0)]
    for _y, rx, rz, cz in rings:
        rx = max(0.05, float(rx))
        rz = max(0.05, float(rz))
        for i in range(segments):
            a = math.tau * i / segments
            ca = math.cos(a)
            sa = math.sin(a)
            vertex.addData3f(rx * ca, float(_y), float(cz) + rz * sa)
            normal.addData3f(ca, 0.0, sa)
            color.addData4f(1, 1, 1, 1)
    tris = GeomTriangles(Geom.UHStatic)
    for r in range(len(rings) - 1):
        base_a = r * segments
        base_b = (r + 1) * segments
        for i in range(segments):
            j = (i + 1) % segments
            tris.addVertices(base_a + i, base_b + i, base_b + j)
            tris.addVertices(base_a + i, base_b + j, base_a + j)
    geom = Geom(vdata)
    geom.addPrimitive(tris)
    node = GeomNode(name)
    node.addGeom(geom)
    return node


def add_elliptical_tube(parent: NodePath, name: str, rings: list[tuple[float, float, float, float]],
                        color=DARK_PANEL, segments: int = 28, pos: tuple[float, float, float] = (0, 0, 0),
                        hpr: tuple[float, float, float] = (0, 0, 0)) -> NodePath:
    node = parent.attachNewNode(elliptical_tube_geom(name, rings, segments=segments))
    node.setPos(*pos)
    node.setHpr(*hpr)
    node.setColor(*color)
    if color[3] < 1.0:
        node.setTransparency(TransparencyAttrib.MAlpha)
    return node


def ellipse_cross_section_points(y: float, radius_x: float, radius_z: float, center_z: float, n: int = 56) -> list[tuple[float, float, float]]:
    return [
        (math.cos(math.tau * i / n) * radius_x, y, center_z + math.sin(math.tau * i / n) * radius_z)
        for i in range(n + 1)
    ]


def ellipse_upper_cross_section_points(y: float, radius_x: float, radius_z: float, center_z: float, n: int = 32) -> list[tuple[float, float, float]]:
    # Top half only: this preserves the cylindrical canopy read without drawing
    # a bright closed circle through the pilot's forward sightline.
    return [
        (math.cos(math.pi * i / n) * radius_x, y, center_z + math.sin(math.pi * i / n) * radius_z)
        for i in range(n + 1)
    ]

def circle_points(x: float, y: float, z: float, radius: float, n: int = 48) -> list[tuple[float,float,float]]:
    return [(x + math.cos(math.tau*i/n)*radius, y + math.sin(math.tau*i/n)*radius, z) for i in range(n+1)]


def arc_points(side: int, y0: float, y1: float, radius_x: float, z: float, n: int = 36) -> list[tuple[float,float,float]]:
    pts = []
    for i in range(n+1):
        t = i/n
        y = y0 + (y1-y0)*t
        bulge = math.sin(math.pi*t)
        x = side * (14 + radius_x*bulge)
        pts.append((x, y, z + 2.0*math.sin(math.pi*t)))
    return pts


@dataclass
class HoloVessel:
    """Floating, walkable HoloCore vessel with conservative AABB collision."""

    name: str = "Holo Vessel // Crescent Runner"
    root: NodePath | None = None
    app: object | None = None
    base_ground_z: float = 0.0
    world_scale: float = 1.36
    floor_local_z: float = 6.08
    flight_altitude: float = 0.0
    min_flight_altitude: float = 0.0
    max_flight_altitude: float = 250000.0
    vertical_speed: float = 42.0
    forward_speed: float = 68.0
    turn_speed: float = 72.0
    # Smoothed pilot inputs make ascent feel like a heavy sea vessel instead
    # of a debug/free-fly camera. These are runtime state values, not saved.
    forward_velocity: float = 0.0
    vertical_velocity: float = 0.0
    turn_velocity: float = 0.0
    bank_angle: float = 0.0
    pitch_angle: float = 0.0
    room_min_x: float = -12.2
    room_max_x: float = 12.2
    room_min_y: float = -31.5
    room_max_y: float = 30.5
    entry_min_y: float = -53.5
    entry_max_y: float = -25.0
    entry_radius_x: float = 11.0
    pilot_min_x: float = -4.5
    pilot_max_x: float = 4.5
    pilot_min_y: float = 11.6
    pilot_max_y: float = 20.2
    exit_min_y: float = -34.8
    exit_max_y: float = -24.7
    pilot_camera_local: tuple[float, float, float] = (0.0, 14.7, 12.3)
    pilot_look_local: tuple[float, float, float] = (0.0, 82.0, 15.2)

    def build(self, app, pos: Vec3 | None = None, heading: float = 180.0) -> "HoloVessel":
        self.app = app
        if pos is None:
            pos = Vec3(0, -210, 0)
        self.base_ground_z = float(pos.z)
        v = app.render.attachNewNode("holo_vessel_crescent_runner")
        v.setPos(pos)
        v.setH(heading)
        v.setScale(float(self.world_scale))
        self.root = v
        self._build_visuals(v)
        return self

    def _build_visuals(self, v: NodePath) -> None:
        # No rectangular landing platform is created here.  Only vessel geometry.
        # Pass 33: keep the walkable center stable, but wrap it in a rounded
        # cylindrical fuselage so the craft reads less like a box and more like
        # the sketch-style long tube/crescent runner.
        add_cube(v, "walkable_cabin_floor", (25.0, 57.0, 1.05), (0, -2, 5.4), FLOOR)
        add_elliptical_tube(
            v,
            "rounded_main_fuselage",
            [
                (-43.0, 6.0, 3.4, 9.2),
                (-34.0, 12.8, 5.9, 10.0),
                (-18.0, 14.5, 6.9, 10.6),
                (2.0, 14.0, 7.4, 11.0),
                (21.0, 11.7, 7.1, 11.2),
                (39.0, 6.5, 5.1, 11.0),
                (58.0, 1.1, 1.0, 10.8),
            ],
            (0.014, 0.050, 0.078, 0.66),
            segments=32,
        )
        add_elliptical_tube(
            v,
            "lower_cylindrical_keel",
            [
                (-36.0, 8.8, 2.0, 5.8),
                (-12.0, 9.8, 2.4, 5.7),
                (18.0, 8.2, 2.1, 5.9),
                (42.0, 2.2, 0.8, 6.1),
            ],
            (0.0, 0.28, 0.42, 0.34),
            segments=28,
        )
        add_tapered_box(v, "subtle_spear_spine", 2.5, 13.0, 77.0, 2.2, (0, 4, 16.4), (0.0, 0.18, 0.25, 0.30))
        for y, rx, rz, cz in [(-36, 12.8, 5.9, 10.0), (-18, 14.5, 6.9, 10.6), (2, 14.0, 7.4, 11.0), (21, 11.7, 7.1, 11.2), (39, 6.5, 5.1, 11.0)]:
            add_line(v, f"cylindrical_hull_ring_{y}", ellipse_upper_cross_section_points(y, rx, rz, cz, 38), (0.0, .78, 1.0, .30), .85)
        for x in (-11.5, 11.5):
            add_line(v, f"longitudinal_hull_stringer_low_{x}", [(x, -37, 8.2), (x*.82, 10, 7.8), (x*.42, 57, 10.5)], CYAN_DIM, 1.25)
            add_line(v, f"longitudinal_hull_stringer_high_{x}", [(x*.45, -34, 15.0), (x*.55, 18, 18.2), (x*.15, 56, 11.6)], CYAN, 1.1)
        add_line(v, "needle_top_sightline", [(0, 20, 18.3), (0, 74, 15.1)], (0.0, 1.0, 0.30, 0.95), 1.5)
        add_cube(v, "cockpit_floor", (18, 17, 0.85), (0, 20, 6.1), FLOOR)
        add_line_box(v, "cockpit_room_frame", (0, 21, 14.2), (20, 18, 14), CYAN, 2.2)
        add_card(v, "curved_cockpit_front_glass", (10.5, 7.0, 1), (0, 31.0, 15.0), (0, 0, 0), GLASS)
        add_card(v, "curved_cockpit_roof_glass", (9.0, 7.5, 1), (0, 22.5, 21.2), (0, -24, 0), (0.0, .85, 1.0, .105))
        for y, rx, rz, cz in [(13, 10.4, 5.7, 14.1), (22, 9.8, 6.6, 14.4), (31, 7.0, 4.5, 14.4)]:
            add_line(v, f"cockpit_rounded_canopy_ring_{y}", ellipse_upper_cross_section_points(y, rx, rz, cz, 34), (0.0, .92, 1.0, .34), .85)
        for x in (-10.8, 10.8):
            add_line(v, f"cockpit_side_A_{x}", [(x, 13, 8), (x, 31, 16)], CYAN, 2.0)
            add_line(v, f"cockpit_side_B_{x}", [(x, 12, 17), (x, 30, 16)], CYAN_DIM, 1.4)
        add_cube(v, "rear_core_deck", (22, 17, 0.75), (0, -17, 6.0), (0.0, .36, .8, .24))
        add_line(v, "rear_room_circular_bulkhead", ellipse_cross_section_points(-28.5, 12.0, 6.4, 11.0, 64), MAGENTA, 2.0)
        add_line_box(v, "rear_walkable_core_room", (0, -17, 13.4), (23, 18, 13), MAGENTA, 1.25)
        for side in (-1, 1):
            outer = arc_points(side, -34, 38, 24, 11.4, 44)
            inner = [(side*14, p[1], p[2]-1.8) for p in outer]
            add_line(v, f"crescent_outer_blade_{side}", outer, CYAN, 2.6)
            add_line(v, f"crescent_inner_blade_{side}", inner, CYAN_DIM, 1.8)
            for a, b in zip(outer[::6], inner[::6]):
                add_line(v, f"crescent_cross_{side}_{a[1]:.1f}", [a,b], MAGENTA, 1.3)
            for j, y in enumerate([-24, -10, 4, 18, 32]):
                x = side * (20 + 9*math.sin((j+1)/6*math.pi))
                add_cube(v, f"side_blade_panel_{side}_{j}", (8, 8, .65), (x, y, 8.8+j*.45), (0.0, .28, .45, .32), (side*8, 0, side*16))
        for side in (-1, 1):
            x = side*15.0
            add_elliptical_tube(
                v,
                f"rounded_rear_engine_pod_{side}",
                [(-40.0, 3.8, 3.2, 9.2), (-34.0, 4.7, 4.2, 9.2), (-22.0, 4.6, 4.0, 9.3), (-15.0, 2.9, 2.6, 9.4)],
                (0.018, .055, .09, .76),
                segments=28,
                pos=(x, 0, 0),
                hpr=(0, 0, side*3),
            )
            add_line_box(v, f"rear_engine_pod_wire_{side}", (x, -27, 9.2), (9.2, 24.5, 7.9), CYAN, 1.15)
            for y, rx, rz, cz in [(-39.4, 4.2, 3.6, 9.2), (-33.0, 4.9, 4.4, 9.25), (-22.0, 4.8, 4.1, 9.3)]:
                pts = [(x + px, py, pz) for px, py, pz in ellipse_cross_section_points(y, rx, rz, cz, 56)]
                add_line(v, f"engine_cyl_ring_{side}_{y}", pts, (0.0, .8, 1.0, .48), 1.35)
            add_line(v, f"engine_beam_{side}", [(x, -40, 9.2), (side*20, -55, 9.0)], AMBER, 1.6)
        add_cube(v, "rear_entry_ramp", (15, 20, .7), (0, -39, 3.1), (0.0, .43, .75, .38), (0, -9, 0))
        add_line_box(v, "rear_entry_trigger", (0, -31.5, 7.8), (15, 6, 8), AMBER, 2.0)
        add_cube(v, "pilot_seat_base", (4.2, 4.8, 1.4), (0, 16, 7.0), (0.015, .018, .05, 1.0))
        add_cube(v, "pilot_seat_back", (4.2, 1.1, 5.8), (0, 13.2, 9.2), (0.018, .02, .07, 1.0), (0, -13, 0))
        add_line_box(v, "pilot_seat_trigger", (0, 16, 9.5), (7.5, 8, 7.6), (0.0, 1.0, .65, 1.0), 2.0)
        add_cube(v, "low_split_console", (9, 3.2, 1.8), (0, 23.5, 7.2), (0.0, .22, .36, .65))
        add_line_box(v, "console_frame", (0, 23.5, 9.0), (9.4, 3.7, 3.0), CYAN, 1.6)
        for y in [-20, -8, 4, 16, 29]:
            add_line(v, f"left_interior_rib_{y}", [(-11, y, 6.3), (-8, y+2, 18)], MAGENTA, 1.4)
            add_line(v, f"right_interior_rib_{y}", [(11, y, 6.3), (8, y+2, 18)], MAGENTA, 1.4)
        for i, (x,y) in enumerate([(-10,-14),(10,-14),(-9,20),(9,20),(0,43)]):
            add_line_box(v, f"hover_node_{i}", (x,y,2.5), (4.8,5.2,3), CYAN_DIM, 1.5)
            for r in [2.3, 3.8, 5.2]:
                add_line(v, f"hover_node_ring_{i}_{r}", circle_points(x,y,.8-r*.15,r,42), (0, .8, 1, .35), 1.0)

    def local_point(self, x: float, y: float, z: float) -> Point3:
        assert self.root is not None and self.app is not None
        return self.app.render.getRelativePoint(self.root, Point3(x, y, z))

    def world_to_local(self, world: Point3 | Vec3) -> Point3:
        assert self.root is not None and self.app is not None
        return self.root.getRelativePoint(self.app.render, Point3(world.x, world.y, world.z))

    def entry_world_position(self) -> Point3:
        return self.local_point(0.0, -47.5, 0.0)

    def board_spawn_world_position(self) -> Point3:
        return self.local_point(0.0, -22.0, self.floor_local_z)

    def exit_world_position(self, terrain_z: float) -> Point3:
        point = self.local_point(0.0, -55.0, 0.0)
        point.setZ(float(terrain_z))
        return point

    def pilot_seat_world_position(self) -> Point3:
        return self.local_point(0.0, 14.4, self.floor_local_z)

    def pilot_camera_world_position(self) -> Point3:
        return self.local_point(*self.pilot_camera_local)

    def pilot_look_world_position(self) -> Point3:
        return self.local_point(*self.pilot_look_local)

    def is_near_entry(self, world: Point3 | Vec3) -> bool:
        p = self.world_to_local(world)
        return abs(float(p.x)) <= self.entry_radius_x and self.entry_min_y <= float(p.y) <= self.entry_max_y

    def is_inside_room(self, world: Point3 | Vec3) -> bool:
        p = self.world_to_local(world)
        return self.room_min_x <= float(p.x) <= self.room_max_x and self.room_min_y <= float(p.y) <= self.room_max_y

    def is_near_pilot(self, world: Point3 | Vec3) -> bool:
        p = self.world_to_local(world)
        return self.pilot_min_x <= float(p.x) <= self.pilot_max_x and self.pilot_min_y <= float(p.y) <= self.pilot_max_y

    def is_near_exit(self, world: Point3 | Vec3) -> bool:
        p = self.world_to_local(world)
        return abs(float(p.x)) <= 8.5 and self.exit_min_y <= float(p.y) <= self.exit_max_y

    def clamp_interior_position(self, world: Point3 | Vec3) -> Point3:
        p = self.world_to_local(world)
        x = max(self.room_min_x, min(self.room_max_x, float(p.x)))
        y = max(self.room_min_y, min(self.room_max_y, float(p.y)))
        return self.local_point(x, y, self.floor_local_z)

    def blocks_outside_position(self, world: Point3 | Vec3) -> bool:
        p = self.world_to_local(world)
        if abs(float(p.x)) > 17.0 or float(p.y) < -25.0 or float(p.y) > 39.0:
            return False
        # Above the floor and hull silhouette, keep the outside player from
        # walking through the central vessel body.  Boarding uses the rear ramp.
        return True

    def push_outside_around_hull(self, old_world: Point3 | Vec3, new_world: Point3 | Vec3) -> Point3:
        if not self.blocks_outside_position(new_world):
            return Point3(new_world.x, new_world.y, new_world.z)
        old_local = self.world_to_local(old_world)
        p = self.world_to_local(new_world)
        # Push to the nearest side/front edge while keeping the terrain-owned Z.
        candidates = [
            (abs(float(p.x) - -17.0), -17.1, float(p.y)),
            (abs(float(p.x) - 17.0), 17.1, float(p.y)),
            (abs(float(p.y) - 39.0), float(p.x), 39.1),
            (abs(float(p.y) - -25.0), float(p.x), -25.1),
        ]
        _, x, y = min(candidates, key=lambda item: item[0])
        # If the previous point was already safely outside on a clearer axis,
        # favor that side for less sticky first-person collision.
        if abs(float(old_local.x)) >= 17.0:
            x = 17.1 if float(old_local.x) > 0 else -17.1
            y = max(-24.9, min(38.9, float(p.y)))
        elif float(old_local.y) >= 39.0:
            y = 39.1
            x = max(-16.9, min(16.9, float(p.x)))
        result = self.local_point(x, y, 0.0)
        result.setZ(float(new_world.z))
        return result

    def _surface_locked_z(self, x: float, y: float, terrain_height_func) -> float:
        try:
            ground = float(terrain_height_func(float(x), float(y)))
        except Exception:
            ground = float(self.base_ground_z)
        self.base_ground_z = ground
        self.flight_altitude = max(float(self.min_flight_altitude), min(float(self.max_flight_altitude), float(self.flight_altitude)))
        return ground + float(self.flight_altitude)

    def update_ground_lock(self, terrain_height_func) -> None:
        """Keep the vessel from ignoring the current terrain surface.

        Parked or piloted, the root Z is always terrain height plus the current
        flight altitude.  This lets the vessel fly while still respecting new
        biome terrain when travelling over hills/valleys.
        """
        if self.root is None:
            return
        pos = self.root.getPos()
        target_z = self._surface_locked_z(float(pos.x), float(pos.y), terrain_height_func)
        if abs(float(pos.z) - target_z) > 0.005:
            self.root.setZ(target_z)

    def physical_room_size(self) -> tuple[float, float, float]:
        scale = float(getattr(self, "world_scale", 1.0) or 1.0)
        return (
            abs(float(self.room_max_x) - float(self.room_min_x)) * scale,
            abs(float(self.room_max_y) - float(self.room_min_y)) * scale,
            14.0 * scale,
        )

    @staticmethod
    def _smooth_value(current: float, target: float, dt: float, response: float) -> float:
        dt = max(0.0, min(0.12, float(dt or 0.0)))
        response = max(0.1, float(response or 0.1))
        blend = 1.0 - math.exp(-response * dt)
        return float(current) + (float(target) - float(current)) * blend

    def reset_motion(self) -> None:
        self.forward_velocity = 0.0
        self.vertical_velocity = 0.0
        self.turn_velocity = 0.0
        self.bank_angle = 0.0
        self.pitch_angle = 0.0
        if self.root is not None and not self.root.isEmpty():
            self.root.setP(0.0)
            self.root.setR(0.0)

    def move_piloted(
        self,
        dt: float,
        forward_axis: float,
        turn_axis: float,
        vertical_axis: float,
        terrain_height_func,
        keepout_func=None,
    ) -> bool:
        if self.root is None:
            return False
        dt = max(0.0, min(0.08, float(dt or 0.0)))
        old_pos = self.root.getPos()
        old_h = float(self.root.getH())
        old_altitude = float(self.flight_altitude)

        # Heavy, readable ascent controls: the target speed is modest, but the
        # craft eases toward it instead of snapping between motion states.
        self.forward_velocity = self._smooth_value(self.forward_velocity, float(forward_axis) * float(self.forward_speed), dt, 1.65)
        self.vertical_velocity = self._smooth_value(self.vertical_velocity, float(vertical_axis) * float(self.vertical_speed), dt, 0.92)
        self.turn_velocity = self._smooth_value(self.turn_velocity, float(turn_axis) * float(self.turn_speed), dt, 2.15)
        self.bank_angle = self._smooth_value(self.bank_angle, -float(turn_axis) * 7.0, dt, 1.35)
        self.pitch_angle = self._smooth_value(self.pitch_angle, float(vertical_axis) * 3.6 + float(forward_axis) * 1.15, dt, 1.10)

        if abs(float(self.turn_velocity)) > 0.001:
            self.root.setH(old_h + float(self.turn_velocity) * dt)
        self.root.setR(float(self.bank_angle))
        self.root.setP(float(self.pitch_angle))

        if abs(float(self.vertical_velocity)) > 0.001:
            self.flight_altitude = max(
                float(self.min_flight_altitude),
                min(float(self.max_flight_altitude), old_altitude + float(self.vertical_velocity) * dt),
            )
            if (self.flight_altitude <= self.min_flight_altitude + 0.001 and self.vertical_velocity < 0.0) or (self.flight_altitude >= self.max_flight_altitude - 0.001 and self.vertical_velocity > 0.0):
                self.vertical_velocity = 0.0

        candidate = Point3(old_pos)
        if abs(float(self.forward_velocity)) > 0.001:
            forward_world = self.app.render.getRelativeVector(self.root, Vec3(0, 1, 0))
            forward_world.setZ(0)
            if forward_world.lengthSquared() > 0:
                forward_world.normalize()
            candidate = Point3(old_pos + forward_world * (float(self.forward_velocity) * dt))
            if keepout_func is not None:
                try:
                    if not keepout_func(float(candidate.x), float(candidate.y)):
                        candidate = Point3(old_pos)
                        self.forward_velocity *= 0.35
                except Exception:
                    pass

        candidate.setZ(self._surface_locked_z(float(candidate.x), float(candidate.y), terrain_height_func))
        self.root.setPos(candidate)
        moved = (
            abs(float(self.flight_altitude) - old_altitude) > 0.0001
            or (candidate - old_pos).lengthSquared() > 0.0001
            or abs(float(self.turn_velocity)) > 0.001
            or abs(float(self.bank_angle)) > 0.001
            or abs(float(self.pitch_angle)) > 0.001
        )
        return moved
