#!/usr/bin/env python3
"""Anti-Heroes exported-model gameplay proof runner.

Runs a compact Panda3D preview scene that prefers the exported Anti-Heroes
character .bam files from assets/character_exports and animates them in the
current city/world presentation.  If an exported .bam is not present in the
local environment, it builds a textured procedural proxy from the same profile
metadata so the proof scene can still render and show placement, animation,
labels, and team roles.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
from typing import Any

from panda3d.core import loadPrcFileData

if os.environ.get("PANDA_PREVIEW", "1").lower() in {"1", "true", "yes", "on"}:
    loadPrcFileData("", "\n".join([
        "window-title Anti-Heroes exported model gameplay proof",
        "win-size 1600 900",
        "load-display p3headlessgl",
        "window-type offscreen",
        "audio-library-name null",
        "sync-video 0",
        "show-frame-rate-meter 0",
        "framebuffer-multisample 1",
        "multisamples 4",
        "default-near 0.05",
        "default-far 9000",
    ]))
else:
    loadPrcFileData("", "\n".join([
        "window-title Anti-Heroes exported model gameplay proof",
        "win-size 1600 900",
        "show-frame-rate-meter 0",
        "sync-video 1",
        "framebuffer-multisample 1",
        "multisamples 4",
    ]))

from direct.showbase.ShowBase import ShowBase
from direct.gui.OnscreenText import OnscreenText
from panda3d.core import (
    AmbientLight,
    CardMaker,
    DirectionalLight,
    Filename,
    Geom,
    GeomNode,
    GeomTriangles,
    GeomVertexData,
    GeomVertexFormat,
    GeomVertexWriter,
    LineSegs,
    NodePath,
    PNMImage,
    SamplerState,
    TextNode,
    Texture,
    TransparencyAttrib,
    Vec3,
    Vec4,
)

ROOT = Path(__file__).resolve().parent
CHAR_EXPORT_DIR = ROOT / "assets" / "character_exports"
PROFILE_PATH = CHAR_EXPORT_DIR / "profiles.json"
DEFAULT_PROFILES: list[dict[str, Any]] = [
    {"file": "player_current.bam", "name": "Cinder Maw", "team": "player_inferno_wraith", "family": "seraphic_halo", "helmet": "antenna", "wing_style": "surf", "tail_style": "whip", "suit_style": "celestial"},
    {"file": "ally_00_seraphic_halo.bam", "name": "Aurelian Aegis", "team": "ally", "family": "seraphic_halo", "helmet": "arc", "wing_style": "tech", "tail_style": "none", "suit_style": "royal"},
    {"file": "ally_01_seraphic_halo.bam", "name": "Virtue Crown", "team": "ally", "family": "seraphic_halo", "helmet": "crown", "wing_style": "none", "tail_style": "none", "suit_style": "phoenix"},
    {"file": "enemy_03_inferno_wraith.bam", "name": "Cinder Flare", "team": "enemy", "family": "inferno_wraith", "helmet": "antenna", "wing_style": "blade", "tail_style": "none", "suit_style": "infernal"},
    {"file": "enemy_04_void_spider.bam", "name": "Noir Crawler", "team": "enemy", "family": "void_spider", "helmet": "mandibles", "wing_style": "bat", "tail_style": "none", "suit_style": "demon_knight"},
    {"file": "enemy_06_golden_emperor.bam", "name": "Royal Prince", "team": "enemy", "family": "golden_emperor", "helmet": "hood", "wing_style": "none", "tail_style": "spine", "suit_style": "royal"},
]

PALETTE = {
    "seraphic_halo": ((1.0, 0.76, 0.22, 1), (0.2, 0.95, 1.0, 1)),
    "inferno_wraith": ((1.0, 0.18, 0.06, 1), (1.0, 0.68, 0.12, 1)),
    "void_spider": ((0.34, 0.10, 0.74, 1), (0.95, 0.22, 1.0, 1)),
    "golden_emperor": ((1.0, 0.62, 0.10, 1), (1.0, 0.92, 0.25, 1)),
    "base": ((0.35, 0.65, 0.9, 1), (0.85, 0.95, 1.0, 1)),
}


def load_profiles() -> list[dict[str, Any]]:
    if PROFILE_PATH.exists():
        try:
            data = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
            if isinstance(data, list) and data:
                return [p for p in data if isinstance(p, dict)][:9]
        except Exception:
            pass
    return DEFAULT_PROFILES


def make_texture(name: str, base: tuple[float, float, float, float], accent: tuple[float, float, float, float]) -> Texture:
    img = PNMImage(256, 256, 4)
    for y in range(256):
        fy = y / 255.0
        for x in range(256):
            fx = x / 255.0
            grid = 1.0 if (x % 32 < 2 or y % 32 < 2) else 0.0
            diagonal = 0.5 + 0.5 * math.sin((x + y) * 0.065)
            pulse = 0.5 + 0.5 * math.sin(fy * 18.0 + fx * 10.0)
            mix = 0.18 + 0.34 * grid + 0.12 * diagonal + 0.08 * pulse
            r = base[0] * (1 - mix) + accent[0] * mix
            g = base[1] * (1 - mix) + accent[1] * mix
            b = base[2] * (1 - mix) + accent[2] * mix
            img.setXelA(x, y, max(0, min(1, r)), max(0, min(1, g)), max(0, min(1, b)), 1.0)
    tex = Texture(name)
    tex.load(img)
    tex.setWrapU(SamplerState.WM_repeat)
    tex.setWrapV(SamplerState.WM_repeat)
    tex.setMinfilter(SamplerState.FT_linear_mipmap_linear)
    tex.setMagfilter(SamplerState.FT_linear)
    return tex


def make_box_node(name: str, w: float, d: float, h: float) -> GeomNode:
    fmt = GeomVertexFormat.getV3n3t2()
    vdata = GeomVertexData(name, fmt, Geom.UHStatic)
    vertex = GeomVertexWriter(vdata, "vertex")
    normal = GeomVertexWriter(vdata, "normal")
    texcoord = GeomVertexWriter(vdata, "texcoord")
    tris = GeomTriangles(Geom.UHStatic)
    hw, hd = w * 0.5, d * 0.5
    faces = [
        ((-hw, -hd, 0), (hw, -hd, 0), (hw, -hd, h), (-hw, -hd, h), (0, -1, 0)),
        ((hw, hd, 0), (-hw, hd, 0), (-hw, hd, h), (hw, hd, h), (0, 1, 0)),
        ((-hw, hd, 0), (-hw, -hd, 0), (-hw, -hd, h), (-hw, hd, h), (-1, 0, 0)),
        ((hw, -hd, 0), (hw, hd, 0), (hw, hd, h), (hw, -hd, h), (1, 0, 0)),
        ((-hw, -hd, h), (hw, -hd, h), (hw, hd, h), (-hw, hd, h), (0, 0, 1)),
        ((-hw, hd, 0), (hw, hd, 0), (hw, -hd, 0), (-hw, -hd, 0), (0, 0, -1)),
    ]
    idx = 0
    uvs = [(0, 0), (1, 0), (1, 1), (0, 1)]
    for p1, p2, p3, p4, nrm in faces:
        for pos, uv in zip((p1, p2, p3, p4), uvs):
            vertex.addData3f(*pos)
            normal.addData3f(*nrm)
            texcoord.addData2f(*uv)
        tris.addVertices(idx, idx + 1, idx + 2)
        tris.addVertices(idx, idx + 2, idx + 3)
        idx += 4
    geom = Geom(vdata)
    geom.addPrimitive(tris)
    node = GeomNode(name)
    node.addGeom(geom)
    return node


def box(parent: NodePath, name: str, pos: tuple[float, float, float], size: tuple[float, float, float], color: tuple[float, float, float, float], tex: Texture | None = None) -> NodePath:
    np = parent.attachNewNode(make_box_node(name, size[0], size[1], size[2]))
    np.setPos(*pos)
    np.setColor(*color)
    if tex:
        np.setTexture(tex, 1)
    return np


def make_label(parent: NodePath, text: str, pos: tuple[float, float, float], color=(0.9, 1, 1, 1)) -> NodePath:
    tn = TextNode(text)
    tn.setText(text)
    tn.setAlign(TextNode.ACenter)
    tn.setTextColor(*color)
    tn.setShadow(0.05, 0.05)
    tn.setShadowColor(0, 0, 0, 0.9)
    np = parent.attachNewNode(tn)
    np.setPos(*pos)
    np.setScale(1.35)
    np.setBillboardPointEye()
    return np


class Avatar:
    def __init__(self, app: "PreviewApp", profile: dict[str, Any], index: int, pos: Vec3) -> None:
        self.app = app
        self.profile = profile
        self.index = index
        self.name = str(profile.get("name") or profile.get("label") or f"Avatar {index}")
        self.family = str(profile.get("family") or "base")
        self.team = str(profile.get("team") or "unknown")
        self.phase = index * 0.77
        self.root = app.render.attachNewNode(f"avatar_{index}_{self.name}")
        self.root.setPos(pos)
        self.model = NodePath()
        self.loaded_export = False
        self.parts: dict[str, NodePath] = {}
        self._build()
        self.label = make_label(app.render, self.name, (pos.x, pos.y, pos.z + 4.4), self._accent())

    def _base_accent(self):
        return PALETTE.get(self.family, PALETTE["base"])

    def _base(self):
        return self._base_accent()[0]

    def _accent(self):
        return self._base_accent()[1]

    def _build(self) -> None:
        model_file = self.profile.get("file")
        if model_file:
            path = CHAR_EXPORT_DIR / str(model_file)
            if path.exists() and path.stat().st_size > 0:
                try:
                    self.model = self.app.loader.loadModel(Filename.fromOsSpecific(str(path)))
                    if self.model and not self.model.isEmpty():
                        self.model.reparentTo(self.root)
                        self.model.setScale(1.8)
                        self.model.setZ(0.3)
                        self.model.setTwoSided(True)
                        self.loaded_export = True
                        return
                except Exception as exc:
                    print(f"Could not load export {path}: {exc}")
        self._build_procedural_proxy()

    def _build_procedural_proxy(self) -> None:
        base, accent = self._base(), self._accent()
        tex = make_texture(f"antiheroes_{self.family}_{self.index}", base, accent)
        root = self.root
        self.parts["body"] = box(root, "body", (0, 0, 0.9), (1.25, 0.82, 2.25), base, tex)
        self.parts["chest"] = box(root, "chest", (0, -0.05, 2.15), (1.65, 0.92, 1.1), accent, tex)
        self.parts["head"] = box(root, "head", (0, 0, 3.28), (0.82, 0.72, 0.82), accent, tex)
        self.parts["l_arm"] = box(root, "l_arm", (-1.08, 0, 1.75), (0.38, 0.42, 1.55), base, tex)
        self.parts["r_arm"] = box(root, "r_arm", (1.08, 0, 1.75), (0.38, 0.42, 1.55), base, tex)
        self.parts["l_leg"] = box(root, "l_leg", (-0.44, 0, -0.02), (0.42, 0.48, 1.05), base, tex)
        self.parts["r_leg"] = box(root, "r_leg", (0.44, 0, -0.02), (0.42, 0.48, 1.05), base, tex)
        helmet = str(self.profile.get("helmet") or "none")
        if helmet != "none":
            self.parts["helmet"] = box(root, "helmet", (0, 0, 4.05), (1.05, 0.88, 0.34), accent, tex)
        wing_style = str(self.profile.get("wing_style") or "none")
        if wing_style != "none":
            self.parts["l_wing"] = box(root, "l_wing", (-1.15, 0.42, 2.25), (0.35, 1.85, 1.35), accent, tex)
            self.parts["r_wing"] = box(root, "r_wing", (1.15, 0.42, 2.25), (0.35, 1.85, 1.35), accent, tex)
        tail_style = str(self.profile.get("tail_style") or "none")
        if tail_style != "none":
            self.parts["tail"] = box(root, "tail", (0, 0.95, 0.95), (0.34, 1.65, 0.36), accent, tex)

    def animate(self, elapsed: float) -> None:
        path_radius = 13 + self.index * 1.45
        speed = 0.28 + (self.index % 4) * 0.055
        angle = elapsed * speed + self.phase
        x = math.cos(angle) * path_radius
        y = math.sin(angle) * path_radius * 0.55 + (self.index - 4) * 1.6
        z = 0.2 + math.sin(elapsed * 2.6 + self.phase) * 0.25
        self.root.setPos(x, y, z)
        self.root.lookAt(Vec3(math.cos(angle + 0.15) * path_radius, math.sin(angle + 0.15) * path_radius * 0.55 + (self.index - 4) * 1.6, z))
        self.root.setH(self.root.getH() + 180)
        self.root.setP(math.sin(elapsed * 2.0 + self.phase) * 3.0)
        if self.loaded_export:
            self.model.setP(math.sin(elapsed * 2.8 + self.phase) * 2.5)
            self.model.setR(math.cos(elapsed * 2.1 + self.phase) * 2.5)
        else:
            arm = math.sin(elapsed * 5.5 + self.phase) * 24
            leg = math.sin(elapsed * 5.5 + self.phase + math.pi) * 18
            if "l_arm" in self.parts:
                self.parts["l_arm"].setP(arm)
            if "r_arm" in self.parts:
                self.parts["r_arm"].setP(-arm)
            if "l_leg" in self.parts:
                self.parts["l_leg"].setP(leg)
            if "r_leg" in self.parts:
                self.parts["r_leg"].setP(-leg)
            if "l_wing" in self.parts:
                self.parts["l_wing"].setH(28 + math.sin(elapsed * 6.0 + self.phase) * 18)
            if "r_wing" in self.parts:
                self.parts["r_wing"].setH(-28 - math.sin(elapsed * 6.0 + self.phase) * 18)
            if "tail" in self.parts:
                self.parts["tail"].setH(math.sin(elapsed * 4.0 + self.phase) * 22)
        self.label.setPos(self.root.getX(), self.root.getY(), self.root.getZ() + 5.0)


class PreviewApp(ShowBase):
    def __init__(self, proof_path: Path | None = None, frames: int = 120) -> None:
        self.proof_path = proof_path
        self.proof_frames = frames
        super().__init__()
        self.disableMouse()
        self.setBackgroundColor(0.01, 0.015, 0.028, 1)
        self.camera.setPos(0, -54, 26)
        self.camera.lookAt(0, 0, 2)
        self.camLens.setFov(64)
        self.avatars: list[Avatar] = []
        self._setup_lights()
        self._build_world()
        self._spawn_avatars()
        self._build_ui()
        self.taskMgr.add(self._tick, "antiheroes_exported_model_gameplay_tick")
        if proof_path:
            self.taskMgr.add(self._proof_task, "antiheroes_exported_model_gameplay_proof")

    def _setup_lights(self) -> None:
        amb = AmbientLight("ambient")
        amb.setColor(Vec4(0.18, 0.22, 0.34, 1))
        self.render.setLight(self.render.attachNewNode(amb))
        sun = DirectionalLight("sun")
        sun.setColor(Vec4(0.95, 0.72, 0.55, 1))
        sun_np = self.render.attachNewNode(sun)
        sun_np.setHpr(-35, -52, 0)
        self.render.setLight(sun_np)
        rim = DirectionalLight("cyan_rim")
        rim.setColor(Vec4(0.18, 0.72, 0.95, 1))
        rim_np = self.render.attachNewNode(rim)
        rim_np.setHpr(130, -26, 0)
        self.render.setLight(rim_np)

    def _build_world(self) -> None:
        cm = CardMaker("ground")
        cm.setFrame(-42, 42, -28, 28)
        ground = self.render.attachNewNode(cm.generate())
        ground.setHpr(0, -90, 0)
        ground.setColor(0.025, 0.035, 0.052, 1)
        grid = LineSegs("matrix_city_grid")
        grid.setThickness(1.0)
        for x in range(-42, 43, 4):
            grid.setColor(0.0, 0.72, 0.95, 0.22)
            grid.moveTo(x, -28, 0.03)
            grid.drawTo(x, 28, 0.03)
        for y in range(-28, 29, 4):
            grid.setColor(0.0, 0.72, 0.95, 0.22)
            grid.moveTo(-42, y, 0.03)
            grid.drawTo(42, y, 0.03)
        self.render.attachNewNode(grid.create())
        road_color = (0.06, 0.065, 0.075, 1)
        box(self.render, "main_road", (0, 0, 0.035), (70, 5, 0.04), road_color)
        box(self.render, "cross_road", (0, 0, 0.04), (6, 44, 0.04), road_color)
        palette = [(0.12, 0.18, 0.27, 1), (0.17, 0.12, 0.25, 1), (0.18, 0.10, 0.10, 1), (0.10, 0.18, 0.16, 1)]
        for i in range(36):
            sx = -36 + (i % 9) * 9
            sy = -22 + (i // 9) * 13
            if abs(sx) < 5 or abs(sy) < 4:
                continue
            height = 2.5 + (i % 7) * 1.45
            b = box(self.render, f"city_tower_{i}", (sx, sy, 0.05), (3.2 + (i % 3), 2.6 + (i % 4) * 0.4, height), palette[i % len(palette)])
            b.setTransparency(TransparencyAttrib.MAlpha)
        ring = LineSegs("antiheroes_dyson_gate")
        ring.setThickness(3.5)
        for i in range(64):
            a = math.tau * i / 64
            b = math.tau * (i + 1) / 64
            ring.setColor(1.0, 0.12, 0.06, 0.45 + 0.25 * ((i % 4) == 0))
            ring.moveTo(math.cos(a) * 25, math.sin(a) * 15, 7 + math.sin(a * 3) * 1.0)
            ring.drawTo(math.cos(b) * 25, math.sin(b) * 15, 7 + math.sin(b * 3) * 1.0)
        self.render.attachNewNode(ring.create())

    def _spawn_avatars(self) -> None:
        profiles = load_profiles()
        priority = []
        for key in ("player", "ally", "enemy"):
            priority.extend([p for p in profiles if key in str(p.get("team", "")) and p not in priority])
        priority.extend([p for p in profiles if p not in priority])
        for i, profile in enumerate(priority[:8]):
            x = -14 + i * 4.0
            y = -3 + math.sin(i) * 6.0
            avatar = Avatar(self, profile, i, Vec3(x, y, 0.2))
            self.avatars.append(avatar)

    def _build_ui(self) -> None:
        loaded = sum(1 for a in self.avatars if a.loaded_export)
        total = len(self.avatars)
        OnscreenText(
            text="THE ANTI-HEROES // EXPORTED MODEL GAMEPLAY PROOF",
            pos=(-1.29, 0.92), scale=0.052, align=TextNode.ALeft,
            fg=(0.88, 1.0, 1.0, 1), shadow=(0, 0, 0, 0.8), mayChange=False,
        )
        OnscreenText(
            text=f"Exported BAM models loaded: {loaded}/{total}  |  fallback only when local binary access is unavailable",
            pos=(-1.29, 0.84), scale=0.035, align=TextNode.ALeft,
            fg=(0.45, 0.95, 1.0, 1), shadow=(0, 0, 0, 0.8), mayChange=False,
        )
        OnscreenText(
            text="Animated patrols • textured suits • allies vs enemies • latest city-world proof scene",
            pos=(-1.29, 0.78), scale=0.033, align=TextNode.ALeft,
            fg=(1.0, 0.78, 0.34, 1), shadow=(0, 0, 0, 0.8), mayChange=False,
        )

    def _tick(self, task):
        elapsed = task.time
        for avatar in self.avatars:
            avatar.animate(elapsed)
        self.camera.setX(math.sin(elapsed * 0.18) * 5.0)
        self.camera.setY(-54 + math.cos(elapsed * 0.15) * 4.0)
        self.camera.lookAt(0, 0, 2.2)
        return task.cont

    def _proof_task(self, task):
        if task.frame < self.proof_frames:
            return task.cont
        assert self.proof_path is not None
        self.proof_path.parent.mkdir(parents=True, exist_ok=True)
        self.win.saveScreenshot(Filename.fromOsSpecific(str(self.proof_path)))
        print(f"Anti-Heroes proof screenshot: {self.proof_path}")
        self.userExit()
        return task.done


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--proof-shot", type=Path, default=None, help="Write an offscreen proof screenshot and exit.")
    parser.add_argument("--frames", type=int, default=120)
    args = parser.parse_args()
    app = PreviewApp(args.proof_shot, frames=max(1, args.frames))
    app.run()


if __name__ == "__main__":
    main()
