"""Generated HoloCore fluid alien octopus mob.

Sparse streamed-world mob.  The octopus is intentionally rare, surface-aware,
and visual-only: it does not bring preview platforms or heavy imported models.
It watches nearby mob anchors, keeps distance, and continuously shifts its
chromatophore colors while its tentacles flow.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Callable, Iterable, Sequence

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

OCTOPUS_SPAWN_CHANCE = 0.03
OCTOPUS_HEIGHT_OFFSET = 18.0
OCTOPUS_HEIGHT_VARIANCE = 13.0
OCTOPUS_MIN_DISTANCE_FROM_HUB = 720.0
OCTOPUS_UPDATE_INTERVAL = 1.0 / 10.0
OCTOPUS_MERMAID_CURIOSITY_RADIUS = 165.0
OCTOPUS_JELLYFISH_CAUTION_RADIUS = 190.0
OCTOPUS_MERMAID_KEEP_DISTANCE = 72.0
OCTOPUS_JELLYFISH_KEEP_DISTANCE = 105.0

AQUA = Vec4(0.04, 0.96, 1.00, 0.54)
CYAN = Vec4(0.12, 0.78, 1.00, 0.60)
TEAL = Vec4(0.10, 1.00, 0.70, 0.50)
VIOLET = Vec4(0.58, 0.30, 1.00, 0.52)
PINK = Vec4(1.00, 0.40, 0.92, 0.48)
GOLD = Vec4(1.00, 0.80, 0.26, 0.46)
INDIGO = Vec4(0.12, 0.16, 0.52, 0.48)
DARK = Vec4(0.02, 0.05, 0.11, 0.58)
PALE = Vec4(0.88, 1.00, 1.00, 0.68)
GREEN_GROUND = Vec4(0.05, 0.42, 0.30, 0.25)


def stable_octopus_seed(chunk_key: tuple[int, int], salt: int = 0x0C70B00F) -> int:
    cx, cy = int(chunk_key[0]), int(chunk_key[1])
    return ((cx * 92837111) ^ (cy * 689287499) ^ int(salt)) & 0xFFFFFFFF


def clamp01(v: float) -> float:
    return max(0.0, min(1.0, float(v)))


def lerp_color(a: Vec4, b: Vec4, t: float) -> Vec4:
    t = clamp01(t)
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


def make_ring_xy(name: str, rx: float, ry: float, z: float, color: Vec4, segs: int = 48, thickness: float = 1.4) -> NodePath:
    pts = []
    for j in range(segs + 1):
        theta = math.tau * (j % segs) / segs
        pts.append((rx * math.cos(theta), ry * math.sin(theta), z))
    return make_polyline(name, pts, color, thickness)


def make_ring_xz(name: str, rx: float, rz: float, y: float, color: Vec4, segs: int = 32, thickness: float = 1.2) -> NodePath:
    pts = []
    for j in range(segs + 1):
        theta = math.tau * (j % segs) / segs
        pts.append((rx * math.cos(theta), y, rz * math.sin(theta)))
    return make_polyline(name, pts, color, thickness)


def make_ellipsoid(name: str, rx: float, ry: float, rz: float, color_a: Vec4, color_b: Vec4, stacks: int = 11, slices: int = 32, vertical_offset: float = 0.0) -> NodePath:
    verts: list[tuple[float, float, float]] = []
    colors: list[Vec4] = []
    faces: list[tuple[int, int, int]] = []
    for i in range(stacks + 1):
        phi = math.pi * i / stacks
        z = rz * math.cos(phi) + vertical_offset
        ring = math.sin(phi)
        for j in range(slices):
            theta = math.tau * j / slices
            ripple = 1.0 + 0.035 * math.sin(theta * 8.0 + phi * 3.0)
            x = rx * math.cos(theta) * ring * ripple
            y = ry * math.sin(theta) * ring * ripple
            shimmer = 0.5 + 0.5 * math.sin(theta * 3.0 + phi * 2.6)
            colors.append(lerp_color(color_a, color_b, 0.18 + 0.54 * shimmer))
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


def tentacle_point(phase: float, length: float, base_radius: float, z0: float, behavior: str, t: float, time_phase: float, strand: float = 0.0) -> tuple[float, float, float, float]:
    reach = {"idle": 0.04, "curious_mermaid": 0.58, "cautious_jellyfish": -0.28, "camouflage": -0.10}.get(behavior, 0.0)
    lift = {"idle": 0.15, "curious_mermaid": 0.48, "cautious_jellyfish": 0.08, "camouflage": -0.18}.get(behavior, 0.0)
    curl = {"idle": 0.60, "curious_mermaid": 0.26, "cautious_jellyfish": 1.05, "camouflage": 0.72}.get(behavior, 0.55)
    energy = {"idle": 0.62, "curious_mermaid": 0.92, "cautious_jellyfish": 0.72, "camouflage": 0.36}.get(behavior, 0.62)
    wave_a = math.sin(time_phase * math.tau + phase * 0.9 + t * math.pi * 3.2)
    wave_b = math.sin(time_phase * math.tau * 1.45 + phase * 1.7 + t * math.pi * 5.6)
    wave_c = math.cos(time_phase * math.tau * 0.70 + phase * 0.4 + t * math.pi * 2.1)
    ang = phase + curl * math.sin(t * math.pi * 1.55 + phase * 0.64 + time_phase * math.tau * 0.55) + reach * t
    ang += (0.16 * wave_a + 0.07 * wave_b) * energy * t
    r = base_radius + length * (0.16 + 0.84 * t)
    lateral = (0.22 * wave_a + 0.11 * wave_b) * energy * t
    vertical = (0.16 * wave_c + 0.08 * wave_b) * energy * math.sin(t * math.pi)
    x = r * math.cos(ang) + lateral * math.cos(ang + math.pi * 0.5 + strand)
    y = r * math.sin(ang) + lateral * math.sin(ang + math.pi * 0.5 + strand)
    z = z0 - 0.42 * t + lift * math.sin(t * math.pi) - 0.16 * t * t + vertical
    return x, y, z, ang


def make_tapered_arm_mesh(name: str, phase: float, length: float, base_radius: float, width: float, z0: float, color_a: Vec4, color_b: Vec4, behavior: str, steps: int = 22, time_phase: float = 0.0) -> NodePath:
    verts: list[tuple[float, float, float]] = []
    colors: list[Vec4] = []
    faces: list[tuple[int, int, int]] = []
    for i in range(steps + 1):
        t = i / steps
        x, y, z, ang = tentacle_point(phase, length, base_radius, z0, behavior, t, time_phase)
        taper = max(0.18, 1.0 - 0.78 * t)
        pulse = 1.0 + 0.10 * math.sin(time_phase * math.tau * 2.2 + t * math.pi * 7.0 + phase)
        side_ang = ang + math.pi * 0.5
        side_x = math.cos(side_ang) * width * taper * pulse
        side_y = math.sin(side_ang) * width * taper * pulse
        verts.append((x - side_x, y - side_y, z))
        verts.append((x + side_x, y + side_y, z))
        verts.append((x, y, z + width * 0.48 * taper))
        c = lerp_color(color_a, color_b, 0.12 + 0.78 * t)
        c = lerp_color(c, Vec4(0.90, 1.0, 1.0, c.w), 0.10 + 0.10 * math.sin(time_phase * math.tau + t * 8.0))
        colors.extend([c, c, Vec4(c.x, c.y, c.z, min(0.70, c.w + 0.08))])
    for i in range(steps):
        a = i * 3
        b = a + 1
        c = a + 2
        d = (i + 1) * 3
        e = d + 1
        f = d + 2
        faces.append((a, d, c))
        faces.append((c, d, f))
        faces.append((c, f, b))
        faces.append((b, f, e))
        faces.append((a, b, d))
        faces.append((b, e, d))
    return make_geom(name, verts, faces, colors=colors)


def make_suction_lines(name: str, phase: float, length: float, base_radius: float, z0: float, color: Vec4, behavior: str, steps: int = 9, time_phase: float = 0.0) -> NodePath:
    root = NodePath(name)
    for i in range(2, steps + 1):
        t = i / steps
        x, y, z, ang = tentacle_point(phase, length, base_radius, z0, behavior, t, time_phase)
        ring = make_ring_xy(f"{name}_sucker_{i:02d}", 0.050 * (1.0 - 0.46 * t), 0.030 * (1.0 - 0.46 * t), 0.0, color, segs=12, thickness=0.80)
        ring.reparentTo(root)
        ring.setPos(x, y, z - 0.018)
        ring.setH(math.degrees(ang))
    return root


def make_flow_filaments(name: str, phase: float, length: float, base_radius: float, z0: float, color: Vec4, behavior: str, count: int = 2, time_phase: float = 0.0) -> NodePath:
    root = NodePath(name)
    for strand in range(count):
        offset = (strand - (count - 1) * 0.5) * 0.24
        pts = []
        for i in range(16):
            t = i / 15
            x, y, z, ang = tentacle_point(phase + offset * 0.15, length * (1.02 + 0.08 * strand), base_radius, z0, behavior, t, time_phase, strand=offset)
            peel = 0.20 * t * t
            x += peel * math.cos(ang + math.pi * 0.5 + offset)
            y += peel * math.sin(ang + math.pi * 0.5 + offset)
            z -= 0.12 * t
            pts.append((x, y, z))
        make_polyline(f"{name}_{strand}", pts, color, thickness=0.85).reparentTo(root)
    return root


def make_eye(name: str, side: float) -> NodePath:
    root = NodePath(name)
    white = make_ellipsoid(f"{name}_eye_glow", 0.155, 0.030, 0.098, PALE, CYAN, stacks=6, slices=16)
    white.reparentTo(root)
    white.setPos(0.26 * side, -0.96, 0.20)
    pupil = make_ellipsoid(f"{name}_pupil", 0.056, 0.010, 0.042, DARK, VIOLET, stacks=5, slices=12)
    pupil.reparentTo(root)
    pupil.setPos(0.26 * side, -1.005, 0.20)
    halo = make_ring_xz(f"{name}_eye_halo", 0.18, 0.11, -1.018, Vec4(0.90, 1.0, 1.0, 0.88), segs=28, thickness=1.2)
    halo.reparentTo(root)
    halo.setX(0.26 * side)
    halo.setZ(0.20)
    return root


@dataclass(frozen=True)
class BehaviorState:
    name: str
    color_a: Vec4
    color_b: Vec4
    accent: Vec4
    min_distance: float
    curiosity: float


STATES = {
    "idle": BehaviorState("idle", INDIGO, AQUA, CYAN, 9.0, 0.20),
    "curious_mermaid": BehaviorState("curious_mermaid", TEAL, PINK, PALE, 13.5, 0.78),
    "cautious_jellyfish": BehaviorState("cautious_jellyfish", VIOLET, GOLD, PALE, 18.0, 0.45),
    "camouflage": BehaviorState("camouflage", DARK, GREEN_GROUND, TEAL, 10.0, 0.12),
}


def make_octopus(name: str, state_name: str = "idle", scale: float = 1.0, seed: int = 7, time_phase: float = 0.0, color_phase: float | None = None) -> NodePath:
    rng = random.Random(seed)
    state = STATES.get(state_name, STATES["idle"])
    root = NodePath(name)
    if color_phase is None:
        color_phase = time_phase
    flow_a = lerp_color(state.color_a, TEAL, 0.20 + 0.18 * math.sin(color_phase * math.tau))
    flow_b = lerp_color(state.color_b, PINK, 0.18 + 0.22 * math.sin(color_phase * math.tau + 1.9))
    flow_accent = lerp_color(state.accent, PALE, 0.20 + 0.22 * math.sin(color_phase * math.tau + 3.1))
    mantle = make_ellipsoid(f"{name}_mantle", 0.84, 1.06, 0.90, flow_a, flow_b, stacks=12, slices=36, vertical_offset=0.42 + 0.04 * math.sin(time_phase * math.tau * 1.2))
    mantle.reparentTo(root)
    head = make_ellipsoid(f"{name}_head_lower", 0.68, 0.80, 0.50, lerp_color(flow_a, flow_b, 0.35), flow_b, stacks=10, slices=30, vertical_offset=-0.12)
    head.reparentTo(root)
    for z, rx, ry, a in [(1.02, 0.50, 0.64, 0.42), (0.72, 0.70, 0.88, 0.52), (0.38, 0.82, 1.02, 0.64), (0.04, 0.72, 0.90, 0.48)]:
        ring = make_ring_xy(f"{name}_scan_{z:.2f}", rx, ry, z, Vec4(flow_accent.x, flow_accent.y, flow_accent.z, a), thickness=1.1)
        ring.reparentTo(root)
    for j in range(12):
        theta = math.tau * j / 12
        pts = []
        for i in range(7):
            t = i / 6
            r = 0.18 + 0.72 * math.sin(t * math.pi * 0.88)
            pts.append((r * math.cos(theta + 0.08 * math.sin(t * 5)), r * math.sin(theta + 0.08 * math.sin(t * 5)), 1.18 - 1.04 * t))
        make_polyline(f"{name}_mantle_rib_{j:02d}", pts, Vec4(flow_accent.x, flow_accent.y, flow_accent.z, 0.40), thickness=0.8).reparentTo(root)
    for side in (-1.0, 1.0):
        make_eye(f"{name}_eye_{side}", side).reparentTo(root)
    for j in range(8):
        phase = -math.pi * 0.5 + math.tau * j / 8.0
        length = 1.12 + 0.18 * math.sin(j * 1.7)
        width = 0.15 + 0.025 * (j % 3)
        arm = make_tapered_arm_mesh(
            f"{name}_arm_{j:02d}",
            phase,
            length=length,
            base_radius=0.18,
            width=width,
            z0=-0.50,
            color_a=lerp_color(flow_a, flow_b, 0.28),
            color_b=Vec4(flow_accent.x, flow_accent.y, flow_accent.z, 0.30),
            behavior=state_name,
            time_phase=time_phase + j * 0.045,
        )
        arm.reparentTo(root)
        make_suction_lines(f"{name}_suckers_{j:02d}", phase, length, 0.18, -0.50, Vec4(0.92, 1.0, 1.0, 0.50), state_name, time_phase=time_phase + j * 0.045).reparentTo(root)
        make_flow_filaments(f"{name}_flow_filaments_{j:02d}", phase, length * 1.18, 0.18, -0.52, Vec4(flow_accent.x, flow_accent.y, flow_accent.z, 0.42), state_name, count=2, time_phase=time_phase + j * 0.055).reparentTo(root)
        if state_name == "curious_mermaid" and j == 1:
            make_polyline(
                f"{name}_curiosity_probe",
                [(0.0, -0.44, -0.42), (0.25, -1.08, -0.58), (0.62, -1.70, -0.42), (0.95, -2.08, -0.20)],
                Vec4(0.92, 1.0, 1.0, 0.86),
                thickness=2.0,
            ).reparentTo(root)
    for j in range(28):
        theta = rng.random() * math.tau
        z = rng.uniform(-0.02, 0.96)
        r = rng.uniform(0.32, 0.82) * max(0.38, math.sin((1.15 - z) * 1.7))
        dot = make_ring_xy(f"{name}_chromadot_{j:02d}", 0.018, 0.014, 0.0, lerp_color(flow_accent, flow_b, rng.random()), segs=10, thickness=0.72)
        dot.reparentTo(root)
        dot.setPos(r * math.cos(theta), r * math.sin(theta), z)
    root.setScale(scale)
    root.setTransparency(TransparencyAttrib.MAlpha)
    return root


class HoloOctopusMob:
    """Very rare intelligent chunk mob with cheap stateful local behavior."""

    def __init__(self, seed: int = 0, surface_height_offset: float = OCTOPUS_HEIGHT_OFFSET) -> None:
        self.seed = int(seed) & 0xFFFFFFFF
        self.surface_height_offset = max(3.0, float(surface_height_offset))
        self.root: NodePath | None = None
        self.visual_root: NodePath | None = None
        self.phase = random.Random(self.seed).random() * math.tau
        self.behavior_state = "idle"
        self._last_rebuild_key: tuple[str, int] | None = None
        self._last_time_phase = -1.0
        self._visibility_alpha = 0.0
        self.scale = 5.5

    def build(self, parent: NodePath, pos: Vec3, scale: float = 5.5, heading: float | None = None) -> "HoloOctopusMob":
        self.scale = float(scale)
        self.root = parent.attachNewNode("holo_octopus_fluid_alien_chunk_mob")
        self.root.setPos(pos)
        self.root.setH(float(heading if heading is not None else random.Random(self.seed).uniform(0.0, 360.0)))
        self.root.setTransparency(TransparencyAttrib.MAlpha)
        self.root.setColorScale(1.0, 1.0, 1.0, 0.0)
        self.update_pose(0.0, force=True)
        return self

    def destroy(self) -> None:
        if self.root is not None and not self.root.isEmpty():
            self.root.removeNode()

    def set_visibility_alpha(self, alpha: float) -> None:
        self._visibility_alpha = clamp01(alpha)
        if self.root is not None and not self.root.isEmpty():
            self.root.setTransparency(TransparencyAttrib.MAlpha)
            self.root.setColorScale(1.0, 1.0, 1.0, self._visibility_alpha)

    def world_position(self) -> Vec3:
        if self.root is None or self.root.isEmpty():
            return Vec3(0, 0, 0)
        return self.root.getPos(self.root.getParent())

    @staticmethod
    def _nearest(pos: Vec3, anchors: Sequence[Vec3]) -> tuple[Vec3 | None, float]:
        best = None
        best_d = 1.0e9
        for anchor in anchors:
            dx = float(anchor.x - pos.x)
            dy = float(anchor.y - pos.y)
            dz = float(anchor.z - pos.z)
            d = math.sqrt(dx * dx + dy * dy + dz * dz)
            if d < best_d:
                best = anchor
                best_d = d
        return best, best_d

    def update_behavior(self, mermaid_positions: Sequence[Vec3], jellyfish_positions: Sequence[Vec3], dt: float = 0.05) -> None:
        if self.root is None or self.root.isEmpty():
            return
        pos = self.world_position()
        nearest_jelly, jelly_d = self._nearest(pos, jellyfish_positions)
        nearest_mermaid, mermaid_d = self._nearest(pos, mermaid_positions)
        state = "idle"
        target = None
        keep_distance = OCTOPUS_MERMAID_KEEP_DISTANCE
        if nearest_jelly is not None and jelly_d <= OCTOPUS_JELLYFISH_CAUTION_RADIUS:
            state = "cautious_jellyfish"
            target = nearest_jelly
            keep_distance = OCTOPUS_JELLYFISH_KEEP_DISTANCE
        elif nearest_mermaid is not None and mermaid_d <= OCTOPUS_MERMAID_CURIOSITY_RADIUS:
            state = "curious_mermaid"
            target = nearest_mermaid
            keep_distance = OCTOPUS_MERMAID_KEEP_DISTANCE
        elif math.sin(self.phase + random.Random(self.seed).random() + pos.x * 0.002 + pos.y * 0.002) > 0.92:
            state = "camouflage"
        if state != self.behavior_state:
            self.behavior_state = state
            self._last_rebuild_key = None
        if target is not None:
            dx = float(pos.x - target.x)
            dy = float(pos.y - target.y)
            dist2 = max(1.0, dx * dx + dy * dy)
            dist = math.sqrt(dist2)
            # Curious: drift in only until the keep ring. Cautious: back away.
            if dist < keep_distance:
                amount = min(7.0, (keep_distance - dist) * 0.035) * max(0.2, float(dt) * 24.0)
            elif state == "curious_mermaid" and dist > keep_distance * 1.22:
                amount = -min(2.4, (dist - keep_distance * 1.22) * 0.010) * max(0.2, float(dt) * 24.0)
            else:
                amount = 0.0
            if amount:
                nx = dx / dist
                ny = dy / dist
                self.root.setX(self.root.getX() + nx * amount)
                self.root.setY(self.root.getY() + ny * amount)
            try:
                self.root.lookAt(Point3(float(target.x), float(target.y), float(pos.z)))
                self.root.setH(self.root.getH() + 180.0)
            except Exception:
                pass

    def update_pose(self, time_value: float, force: bool = False) -> None:
        if self.root is None or self.root.isEmpty():
            return
        t = float(time_value or 0.0) + self.phase
        time_phase = (t * 0.045) % 1.0
        bucket = int(time_phase * 28.0)
        key = (self.behavior_state, bucket)
        if not force and key == self._last_rebuild_key:
            # Subtle whole-body swim between geometry rebuilds.
            self.root.setP(math.sin(t * 0.55) * 2.2)
            self.root.setR(math.cos(t * 0.44) * 1.8)
            return
        if self.visual_root is not None and not self.visual_root.isEmpty():
            self.visual_root.removeNode()
        color_phase = (time_phase + (self.seed & 255) / 255.0) % 1.0
        self.visual_root = make_octopus("fluid_alien_octopus_visual", self.behavior_state, scale=self.scale, seed=self.seed, time_phase=time_phase, color_phase=color_phase)
        self.visual_root.reparentTo(self.root)
        self.visual_root.setTransparency(TransparencyAttrib.MAlpha)
        self.visual_root.setLightOff()
        self.visual_root.setBin("transparent", 18)
        self._last_rebuild_key = key
        self.root.setP(math.sin(t * 0.55) * 2.2)
        self.root.setR(math.cos(t * 0.44) * 1.8)

    def update_surface_lock(self, surface_height_fn: Callable[[float, float], float]) -> None:
        if self.root is None or self.root.isEmpty():
            return
        pos = self.root.getPos(self.root.getParent())
        try:
            ground = float(surface_height_fn(float(pos.x), float(pos.y)))
        except Exception:
            return
        self.root.setZ(ground + self.surface_height_offset)
