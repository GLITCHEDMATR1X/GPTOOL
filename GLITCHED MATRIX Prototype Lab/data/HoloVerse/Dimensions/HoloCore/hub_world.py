"""
HoloVerse hub world adapter.

Owns only the pyramid hub: inner ground, holographic pyramid shell,
MatrixCore, uplink beam, and distant Dyson target. No UI/HUD.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Sequence

from panda3d.core import (
    AmbientLight,
    CardMaker,
    DirectionalLight,
    Fog,
    Geom,
    GeomNode,
    GeomTriangles,
    GeomVertexData,
    GeomVertexFormat,
    GeomVertexWriter,
    LineSegs,
    Material,
    NodePath,
    PointLight,
    TransparencyAttrib,
    Vec3,
    Vec4,
)
from direct.task import Task


def make_material(
    diffuse: Sequence[float],
    emission: Sequence[float] | None = None,
    specular: Sequence[float] | None = None,
    shininess: float = 48.0,
) -> Material:
    mat = Material()
    mat.setDiffuse(Vec4(*diffuse))
    if emission:
        mat.setEmission(Vec4(*emission))
    if specular:
        mat.setSpecular(Vec4(*specular))
        mat.setShininess(shininess)
    return mat


def interp(a: Vec3, b: Vec3, t: float) -> Vec3:
    return a + (b - a) * t


@dataclass
class HubWorldAdapter:
    """Adapter for the central pyramid hub.

    The hub exposes its footprint so dimensions can generate around it without
    filling the inside. Pyramid wall collision is intentionally absent.
    """

    hub_extent: float = 130.0
    pyramid_height: float = 118.0
    floor_z: float = -0.10
    eye_height: float = 13.0
    root: NodePath | None = None
    core_nodes: list[NodePath] = field(default_factory=list)
    ring_nodes: list[NodePath] = field(default_factory=list)
    pulse_nodes: list[NodePath] = field(default_factory=list)
    beam_nodes: list[NodePath] = field(default_factory=list)
    dyson_nodes: list[NodePath] = field(default_factory=list)
    data_particle_nodes: list[NodePath] = field(default_factory=list)

    def build(self, app) -> "HubWorldAdapter":
        self.app = app
        self.render = app.render
        self.loader = app.loader
        self.root = self.render.attachNewNode("hub_world_root")
        self._setup_atmosphere()
        self._setup_lighting()
        self._build_inner_hub_ground()
        self._build_pyramid_shell()
        self._build_core_platform()
        self._build_core()
        self._build_infinite_beam_and_dyson_target()
        self._build_stabilizers()
        return self

    def get_exclusion_square(self) -> tuple[float, float, float, float]:
        e = self.hub_extent
        return (-e, e, -e, e)

    def is_inside_hub(self, x: float, y: float, margin: float = 0.0) -> bool:
        e = self.hub_extent + margin
        return -e <= x <= e and -e <= y <= e

    def get_spawn_position(self) -> Vec3:
        return Vec3(0, -58, 0)

    def get_spawn_target(self) -> Vec3:
        return Vec3(0, 0, 40.0)

    def _setup_atmosphere(self) -> None:
        fog = Fog("black_neon_depth_fog")
        fog.setColor(0.0, 0.0, 0.004)
        fog.setExpDensity(0.0022)
        self.render.setFog(fog)

    def _setup_lighting(self) -> None:
        ambient = AmbientLight("deep_ambient")
        ambient.setColor(Vec4(0.025, 0.035, 0.060, 1.0))
        self.render.setLight(self.render.attachNewNode(ambient))

        key = DirectionalLight("cold_top_key")
        key.setColor(Vec4(0.20, 0.38, 0.56, 1.0))
        key_np = self.render.attachNewNode(key)
        key_np.setHpr(-45, -70, 0)
        self.render.setLight(key_np)

        red_rim = DirectionalLight("red_back_rim")
        red_rim.setColor(Vec4(0.38, 0.035, 0.04, 1.0))
        red_np = self.render.attachNewNode(red_rim)
        red_np.setHpr(155, -22, 0)
        self.render.setLight(red_np)

        core_light = PointLight("matrixcore_red_light")
        core_light.setColor(Vec4(2.2, 0.20, 0.10, 1.0))
        core_light.setAttenuation((1.0, 0.020, 0.00052))
        core_light_np = self.render.attachNewNode(core_light)
        core_light_np.setPos(0, 0, 13.5)
        self.render.setLight(core_light_np)

        cyan_light = PointLight("cyan_shell_light")
        cyan_light.setColor(Vec4(0.18, 0.75, 1.2, 1.0))
        cyan_light.setAttenuation((1.0, 0.025, 0.00075))
        cyan_np = self.render.attachNewNode(cyan_light)
        cyan_np.setPos(0, -54, 13)
        self.render.setLight(cyan_np)

    def _build_inner_hub_ground(self) -> None:
        assert self.root is not None
        extent = int(self.hub_extent)
        cm = CardMaker("hub_inner_matte_floor")
        cm.setFrame(-self.hub_extent, self.hub_extent, -self.hub_extent, self.hub_extent)
        floor = self.root.attachNewNode(cm.generate())
        floor.setP(-90)
        floor.setZ(self.floor_z)
        floor.setColor(0.004, 0.007, 0.013, 1.0)
        floor.setBin("background", 0)

        grid = LineSegs("hub_floor_grid")
        grid.setThickness(1.0)
        for i in range(-extent, extent + 1, 5):
            major = i % 25 == 0
            alpha = 0.36 if major else 0.13
            grid.setColor(0.05, 0.68, 0.92, alpha)
            grid.moveTo(i, -extent, 0.02)
            grid.drawTo(i, extent, 0.02)
            grid.moveTo(-extent, i, 0.02)
            grid.drawTo(extent, i, 0.02)
        grid_np = self.root.attachNewNode(grid.create())
        grid_np.setLightOff()
        grid_np.setTransparency(TransparencyAttrib.MAlpha)

        red_paths = LineSegs("hub_red_floor_paths")
        red_paths.setThickness(1.0)
        for r in [38, 62, 91]:
            red_paths.setColor(0.85, 0.04, 0.05, 0.18 if r > 40 else 0.26)
            self._draw_circle(red_paths, r, z=0.05, steps=160)
        for angle in range(0, 360, 30):
            a = math.radians(angle)
            red_paths.setColor(0.9, 0.04, 0.05, 0.14)
            red_paths.moveTo(math.cos(a) * 18, math.sin(a) * 18, 0.06)
            red_paths.drawTo(math.cos(a) * 115, math.sin(a) * 115, 0.06)
        red_np = self.root.attachNewNode(red_paths.create())
        red_np.setLightOff()
        red_np.setTransparency(TransparencyAttrib.MAlpha)

    def _build_pyramid_shell(self) -> None:
        assert self.root is not None
        size = self.hub_extent
        height = self.pyramid_height
        base = [
            Vec3(-size, -size, 0),
            Vec3(size, -size, 0),
            Vec3(size, size, 0),
            Vec3(-size, size, 0),
        ]
        apex = Vec3(0, 0, height)

        fmt = GeomVertexFormat.getV3n3c4()
        vdata = GeomVertexData("pyramid_glass_faces", fmt, Geom.UHStatic)
        vw = GeomVertexWriter(vdata, "vertex")
        nw = GeomVertexWriter(vdata, "normal")
        cw = GeomVertexWriter(vdata, "color")
        prim = GeomTriangles(Geom.UHStatic)
        face_colors = [
            (0.03, 0.38, 0.52, 0.145),
            (0.04, 0.20, 0.38, 0.095),
            (0.46, 0.025, 0.045, 0.105),
            (0.03, 0.46, 0.58, 0.115),
        ]
        row = 0
        for idx in range(4):
            a = base[idx]
            b = base[(idx + 1) % 4]
            normal = (b - a).cross(apex - a).normalized()
            for p in (a, b, apex):
                vw.addData3(p)
                nw.addData3(normal)
                cw.addData4(*face_colors[idx])
            prim.addVertices(row, row + 1, row + 2)
            row += 3
        prim.closePrimitive()
        geom = Geom(vdata)
        geom.addPrimitive(prim)
        node = GeomNode("pyramid_glass_faces")
        node.addGeom(geom)
        faces = self.root.attachNewNode(node)
        faces.setTransparency(TransparencyAttrib.MAlpha)
        faces.setTwoSided(True)
        faces.setDepthWrite(False)
        faces.setBin("transparent", 10)

        edges = LineSegs("pyramid_edges_and_face_mesh")
        edges.setThickness(3.4)
        edges.setColor(0.17, 0.98, 1.0, 0.86)
        for i in range(4):
            edges.moveTo(base[i])
            edges.drawTo(base[(i + 1) % 4])
            edges.moveTo(base[i])
            edges.drawTo(apex)

        edges.setThickness(1.05)
        for i in range(4):
            a = base[i]
            b = base[(i + 1) % 4]
            for t in [0.16, 0.28, 0.40, 0.52, 0.64, 0.76, 0.88]:
                z_color = (0.08, 0.72, 0.95, 0.28) if t < 0.68 else (0.96, 0.08, 0.08, 0.34)
                edges.setColor(*z_color)
                edges.moveTo(interp(a, apex, t))
                edges.drawTo(interp(b, apex, t))
            for t in [0.25, 0.50, 0.75]:
                edges.setColor(0.08, 0.72, 0.95, 0.19)
                p = interp(a, b, t)
                edges.moveTo(p)
                edges.drawTo(apex)
        mesh_np = self.root.attachNewNode(edges.create())
        mesh_np.setLightOff()
        mesh_np.setTransparency(TransparencyAttrib.MAlpha)

    def _build_core_platform(self) -> None:
        assert self.root is not None
        platform = LineSegs("core_octagon_platform")
        platform.setThickness(2.6)
        for r, alpha in [(13, 0.78), (20, 0.46), (29, 0.28)]:
            platform.setColor(0.10, 0.88, 1.0, alpha)
            self._draw_octagon(platform, r, z=0.25)
        for angle in range(0, 360, 45):
            a = math.radians(angle)
            platform.setColor(0.95, 0.06, 0.05, 0.34)
            platform.moveTo(math.cos(a) * 8, math.sin(a) * 8, 0.30)
            platform.drawTo(math.cos(a) * 32, math.sin(a) * 32, 0.30)
        p_np = self.root.attachNewNode(platform.create())
        p_np.setLightOff()
        p_np.setTransparency(TransparencyAttrib.MAlpha)

    def _build_core(self) -> None:
        assert self.root is not None
        core = self.loader.loadModel("models/misc/sphere")
        core.reparentTo(self.root)
        core.setName("MatrixCore_energy_sphere")
        core.setScale(4.6)
        core.setPos(0, 0, 13.0)
        core.setColor(1.0, 0.03, 0.015, 1.0)
        core.setMaterial(make_material((1.0, 0.03, 0.015, 1), emission=(1.0, 0.06, 0.02, 1), specular=(1, 0.22, 0.1, 1), shininess=128))
        self.core_nodes.append(core)

        for idx, (scale, alpha) in enumerate([(7.8, 0.16), (11.6, 0.075), (15.4, 0.040)]):
            aura = self.loader.loadModel("models/misc/sphere")
            aura.reparentTo(self.root)
            aura.setName(f"MatrixCore_aura_{idx}")
            aura.setScale(scale)
            aura.setPos(0, 0, 13.0)
            aura.setColor(1.0, 0.08, 0.04, alpha)
            aura.setTransparency(TransparencyAttrib.MAlpha)
            aura.setDepthWrite(False)
            aura.setBin("transparent", 30 + idx)
            aura.setLightOff()
            self.pulse_nodes.append(aura)

        ring_specs = [
            (12.5, (90, 0, 0), (0.10, 0.95, 1.0, 0.88), 2.8),
            (17.5, (64, 0, 30), (1.0, 0.06, 0.04, 0.72), 2.1),
            (23.5, (77, 38, -34), (0.20, 0.70, 1.0, 0.42), 1.4),
        ]
        for idx, (radius, hpr, color, thickness) in enumerate(ring_specs):
            ring = self._make_ring(f"orbital_matrix_ring_{idx}", radius, thickness, color)
            ring.reparentTo(self.root)
            ring.setPos(0, 0, 13.0)
            ring.setHpr(*hpr)
            ring.setLightOff()
            ring.setTransparency(TransparencyAttrib.MAlpha)
            self.ring_nodes.append(ring)

        cross = LineSegs("core_horizontal_alignment_beams")
        cross.setThickness(1.8)
        cross.setColor(0.12, 0.95, 1.0, 0.48)
        for angle in range(0, 360, 90):
            a = math.radians(angle)
            cross.moveTo(0, 0, 13.0)
            cross.drawTo(math.cos(a) * 34, math.sin(a) * 34, 13.0)
        cross_np = self.root.attachNewNode(cross.create())
        cross_np.setLightOff()
        cross_np.setTransparency(TransparencyAttrib.MAlpha)

    def _build_infinite_beam_and_dyson_target(self) -> None:
        assert self.root is not None
        beam_height = 760.0
        beam = LineSegs("matrixcore_infinite_data_beam")
        beam.setThickness(8.0)
        beam.setColor(1.0, 0.035, 0.025, 0.46)
        beam.moveTo(0, 0, 2.0)
        beam.drawTo(0, 0, beam_height)
        beam.setThickness(3.6)
        beam.setColor(0.10, 0.95, 1.0, 0.56)
        beam.moveTo(1.25, 0, 10.0)
        beam.drawTo(1.25, 0, beam_height)
        beam.moveTo(-1.25, 0, 10.0)
        beam.drawTo(-1.25, 0, beam_height)
        beam.setThickness(1.2)
        beam.setColor(1.0, 0.98, 0.88, 0.72)
        beam.moveTo(0, 0, 14.0)
        beam.drawTo(0, 0, beam_height)
        beam_np = self.root.attachNewNode(beam.create())
        beam_np.setName("infinite_uplink_beam")
        beam_np.setLightOff()
        beam_np.setTransparency(TransparencyAttrib.MAlpha)
        self.beam_nodes.append(beam_np)

        tip_glow = self.loader.loadModel("models/misc/sphere")
        tip_glow.reparentTo(self.root)
        tip_glow.setName("beam_pyramid_tip_contact_glow")
        tip_glow.setScale(7.5, 7.5, 3.2)
        tip_glow.setPos(0, 0, self.pyramid_height)
        tip_glow.setColor(0.20, 0.95, 1.0, 0.16)
        tip_glow.setTransparency(TransparencyAttrib.MAlpha)
        tip_glow.setDepthWrite(False)
        tip_glow.setLightOff()
        tip_glow.setBin("transparent", 45)
        self.pulse_nodes.append(tip_glow)

        for idx in range(32):
            z = 18.0 + (idx * 17.0) % 330.0
            radius = 2.1 + (idx % 5) * 0.55
            angle = math.radians((idx * 137.5) % 360)
            mote = LineSegs(f"beam_data_mote_{idx:02d}")
            mote.setThickness(1.25 if idx % 3 else 1.8)
            if idx % 4 == 0:
                mote.setColor(1.0, 0.10, 0.055, 0.56)
            else:
                mote.setColor(0.14, 0.92, 1.0, 0.42)
            x = math.cos(angle) * radius
            y = math.sin(angle) * radius
            mote.moveTo(x, y, z)
            mote.drawTo(x, y, z + 3.5 + (idx % 4))
            mote_np = self.root.attachNewNode(mote.create())
            mote_np.setName(f"beam_data_mote_{idx:02d}")
            mote_np.setLightOff()
            mote_np.setTransparency(TransparencyAttrib.MAlpha)
            mote_np.setPythonTag("base_z", z)
            mote_np.setPythonTag("speed", 2.2 + (idx % 7) * 0.18)
            mote_np.setPythonTag("phase", idx * 0.37)
            self.data_particle_nodes.append(mote_np)

        self._build_distant_dyson_sphere()

    def _build_distant_dyson_sphere(self) -> None:
        assert self.root is not None
        root = self.root.attachNewNode("distant_dyson_sphere_target")
        root.setPos(0, 0, 585.0)
        root.setLightOff()
        root.setTransparency(TransparencyAttrib.MAlpha)
        self.dyson_nodes.append(root)

        star = self.loader.loadModel("models/misc/sphere")
        star.reparentTo(root)
        star.setName("white_dwarf_core")
        star.setScale(7.5)
        star.setColor(0.78, 0.95, 1.0, 0.72)
        star.setTransparency(TransparencyAttrib.MAlpha)
        star.setDepthWrite(False)
        star.setLightOff()
        star.setBin("transparent", 35)
        self.dyson_nodes.append(star)

        dyson = LineSegs("incomplete_dyson_wire_shell")
        dyson.setThickness(2.0)
        for radius, alpha in [(28.0, 0.60), (38.0, 0.36), (48.0, 0.24)]:
            dyson.setColor(1.0, 0.075, 0.045, alpha)
            self._draw_octagon(dyson, radius, z=0.0)
        for tilt, radius, color in [
            ((70, 0, 0), 42.0, (0.15, 0.88, 1.0, 0.44)),
            ((20, 65, 0), 35.0, (1.0, 0.08, 0.05, 0.36)),
            ((-35, 18, 45), 50.0, (0.14, 0.80, 1.0, 0.24)),
        ]:
            arc = self._make_arc(f"dyson_construction_arc_{len(self.dyson_nodes)}", radius, color, start_deg=18, end_deg=300, thickness=1.7)
            arc.reparentTo(root)
            arc.setHpr(*tilt)
            self.dyson_nodes.append(arc)
        shell_np = root.attachNewNode(dyson.create())
        shell_np.setName("dyson_octagon_shell_bands")
        shell_np.setLightOff()
        shell_np.setTransparency(TransparencyAttrib.MAlpha)
        self.dyson_nodes.append(shell_np)

        spokes = LineSegs("dyson_partial_spokes")
        spokes.setThickness(1.35)
        for angle in range(0, 360, 45):
            if angle in (90, 225):
                continue
            a = math.radians(angle)
            spokes.setColor(0.13, 0.86, 1.0, 0.26)
            spokes.moveTo(math.cos(a) * 18.0, math.sin(a) * 18.0, 0.0)
            spokes.drawTo(math.cos(a) * 47.0, math.sin(a) * 47.0, 0.0)
        spokes_np = root.attachNewNode(spokes.create())
        spokes_np.setLightOff()
        spokes_np.setTransparency(TransparencyAttrib.MAlpha)
        self.dyson_nodes.append(spokes_np)

    def _build_stabilizers(self) -> None:
        assert self.root is not None
        for idx, (radius, angle) in enumerate([(36, 45), (36, 135), (36, 225), (36, 315)]):
            x = math.cos(math.radians(angle)) * radius
            y = math.sin(math.radians(angle)) * radius
            spire = self._make_spire(f"core_stabilizer_{idx}", 10 + idx * 1.5)
            spire.reparentTo(self.root)
            spire.setPos(x, y, 0.25)
            spire.setH(angle)

    def _make_spire(self, name: str, height: float) -> NodePath:
        segs = LineSegs(name)
        segs.setThickness(1.9)
        segs.setColor(0.08, 0.84, 1.0, 0.56)
        r = 3.2
        base = [Vec3(-r, -r, 0), Vec3(r, -r, 0), Vec3(r, r, 0), Vec3(-r, r, 0)]
        top = Vec3(0, 0, height)
        for i in range(4):
            segs.moveTo(base[i])
            segs.drawTo(base[(i + 1) % 4])
            segs.moveTo(base[i])
            segs.drawTo(top)
        segs.setColor(1.0, 0.06, 0.035, 0.42)
        segs.moveTo(0, 0, 0)
        segs.drawTo(0, 0, height)
        np = NodePath(segs.create())
        np.setLightOff()
        np.setTransparency(TransparencyAttrib.MAlpha)
        return np

    def _make_ring(self, name: str, radius: float, thickness: float, color: Sequence[float]) -> NodePath:
        segs = LineSegs(name)
        segs.setThickness(thickness)
        segs.setColor(*color)
        self._draw_circle(segs, radius, z=0, steps=240)
        return NodePath(segs.create())

    def _make_arc(
        self,
        name: str,
        radius: float,
        color: Sequence[float],
        start_deg: float,
        end_deg: float,
        thickness: float = 1.0,
        steps: int = 96,
    ) -> NodePath:
        segs = LineSegs(name)
        segs.setThickness(thickness)
        segs.setColor(*color)
        for i in range(steps + 1):
            t = i / steps
            deg = start_deg + (end_deg - start_deg) * t
            a = math.radians(deg)
            p = Vec3(math.cos(a) * radius, math.sin(a) * radius, 0)
            if i == 0:
                segs.moveTo(p)
            else:
                segs.drawTo(p)
        np = NodePath(segs.create())
        np.setLightOff()
        np.setTransparency(TransparencyAttrib.MAlpha)
        return np

    def _draw_circle(self, segs: LineSegs, radius: float, z: float, steps: int = 160) -> None:
        for i in range(steps + 1):
            a = math.tau * i / steps
            p = Vec3(math.cos(a) * radius, math.sin(a) * radius, z)
            if i == 0:
                segs.moveTo(p)
            else:
                segs.drawTo(p)

    def _draw_octagon(self, segs: LineSegs, radius: float, z: float) -> None:
        pts = [Vec3(math.cos(math.tau * i / 8) * radius, math.sin(math.tau * i / 8) * radius, z) for i in range(8)]
        for i in range(8):
            segs.moveTo(pts[i])
            segs.drawTo(pts[(i + 1) % 8])

    def update(self, task: Task) -> None:
        t = task.time
        for idx, node in enumerate(self.core_nodes):
            node.setH(t * (20 + idx * 6))
            node.setP(math.sin(t * 0.85) * 2.0)
        core_pulse_bases = [7.8, 11.6, 15.4]
        for idx, node in enumerate(self.pulse_nodes):
            if idx < len(core_pulse_bases):
                base = core_pulse_bases[idx]
                pulse = 1.0 + math.sin(t * 1.35 + idx * 0.7) * (0.026 + idx * 0.010)
                node.setScale(base * pulse)
            else:
                tip_pulse = 1.0 + math.sin(t * 0.72) * 0.055
                node.setScale(7.5 * tip_pulse, 7.5 * tip_pulse, 3.2 * tip_pulse)
        for idx, ring in enumerate(self.ring_nodes):
            ring.setH(ring.getH() + (0.18 + idx * 0.065))
            ring.setR(ring.getR() + (0.07 + idx * 0.03))
        for idx, beam in enumerate(self.beam_nodes):
            beam.setH(math.sin(t * 0.14 + idx) * 1.5)
        for idx, mote in enumerate(self.data_particle_nodes):
            base_z = float(mote.getPythonTag("base_z"))
            speed = float(mote.getPythonTag("speed"))
            phase = float(mote.getPythonTag("phase"))
            z = 18.0 + ((base_z - 18.0 + t * speed * 9.0) % 342.0)
            mote.setZ(z - base_z)
            mote.setH(t * (4.0 + idx * 0.015) + phase)
        for dyson in self.dyson_nodes:
            if dyson.getName() == "distant_dyson_sphere_target":
                dyson.setH(t * 0.65)
                dyson.setP(math.sin(t * 0.10) * 1.5)
            elif "arc" in dyson.getName():
                dyson.setR(dyson.getR() + 0.035)
