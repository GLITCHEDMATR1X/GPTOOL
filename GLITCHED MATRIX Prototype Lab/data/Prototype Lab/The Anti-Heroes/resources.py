
from __future__ import annotations

import math
import os
import random
import json
import sys
import traceback
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LOG_DIR = ROOT / "logs"
TEX_DIR = ROOT / "generated_textures"
ASSETS_DIR = ROOT / "assets"
POWER_SFX_DIR = ASSETS_DIR / "power_sfx"
STRUCTURE_TEX_DIR = ASSETS_DIR / "textures" / "structures"
CHAR_EXPORT_DIR = ASSETS_DIR / "character_exports"
SETTINGS_PATH = ROOT / "settings.json"
LOG_DIR.mkdir(exist_ok=True)
TEX_DIR.mkdir(exist_ok=True)
POWER_SFX_DIR.mkdir(parents=True, exist_ok=True)
STRUCTURE_TEX_DIR.mkdir(parents=True, exist_ok=True)
CHAR_EXPORT_DIR.mkdir(parents=True, exist_ok=True)

FAST_CORE_STARTUP = os.environ.get("HOLOVERSE_FAST_STARTUP", "0").lower() in {"1", "true", "yes", "on"}
EXPORT_CHARACTERS_ON_LAUNCH = os.environ.get("HOLOVERSE_EXPORT_CHARACTERS_ON_LAUNCH", "0").lower() in {"1", "true", "yes", "on"}

SETTINGS_DEFAULTS = {
    "hud_visible": True,
    "overlay_visible": True,
    "mouse_sensitivity": 0.10,
    "camera_pitch_sensitivity": 0.080,
    "invert_y": False,
    "default_camera_distance": 24.5,
    "camera_fov": 76.0,
    "zoom_step": 1.4,
    "effect_density": 1.0,
    "traffic_density": 1.0,
    "weather_fx_enabled": True,
    "quality_preset": "Balanced",
    "target_lock_range": 240.0,
}


def install_crash_reporter() -> None:
    def _hook(exc_type, exc, tb):
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = LOG_DIR / f"crash_{stamp}.txt"
        with path.open("w", encoding="utf-8") as f:
            f.write("City Hero Flight crash report\n")
            f.write(f"time: {datetime.now().isoformat()}\n")
            f.write(f"python: {sys.version}\n")
            f.write(f"platform: {sys.platform}\n\n")
            traceback.print_exception(exc_type, exc, tb, file=f)
        print(f"Crash log written to: {path}")
        traceback.print_exception(exc_type, exc, tb)

    sys.excepthook = _hook


install_crash_reporter()

_HOLOVERSE_RUNTIME = None
try:
    _CORE_ROOT = ROOT.parent.parent
    if str(_CORE_ROOT) not in sys.path:
        sys.path.insert(0, str(_CORE_ROOT))
    import holoverse_mode_runtime as _HOLOVERSE_RUNTIME
except Exception:
    _HOLOVERSE_RUNTIME = None

from panda3d.core import loadPrcFileData

_preview = os.environ.get("PANDA_PREVIEW") == "1"
_prc = [
    "window-title The Anti-Villains",
    "win-size 1600 900",
    "show-frame-rate-meter 0",
    "sync-video 1",
    "framebuffer-multisample 1",
    "multisamples 4",
    "textures-power-2 none",
    "texture-anisotropic-degree 4",
    "default-near 0.05",
    "default-far 12000",
]
if _preview:
    _prc += [
        "load-display p3headlessgl",
        "window-type offscreen",
        "audio-library-name null",
        "sync-video 0",
    ]
if _HOLOVERSE_RUNTIME is not None and _HOLOVERSE_RUNTIME.embedded_mode():
    _prc.append(_HOLOVERSE_RUNTIME.panda_prc_lines("The Anti-Heroes", default=(1600, 900)))
loadPrcFileData("", "\n".join(_prc))

from direct.showbase.ShowBase import ShowBase
from direct.task import Task
from direct.gui.OnscreenText import OnscreenText
from panda3d.core import (
    AmbientLight,
    CardMaker,
    DirectionalLight,
    Filename,
    Fog,
    Geom,
    GeomNode,
    GeomTriangles,
    GeomVertexData,
    GeomVertexFormat,
    GeomVertexWriter,
    NodePath,
    PNMImage,
    SamplerState,
    Shader,
    TextNode,
    Texture,
    TransparencyAttrib,
    Vec3,
    Vec4,
    WindowProperties,
)


VERT_SHADER = """
#version 130
uniform mat4 p3d_ModelViewProjectionMatrix;
uniform float u_time;
uniform float u_phase;
uniform float u_amp;
in vec4 p3d_Vertex;
in vec2 p3d_MultiTexCoord0;
out vec2 uv;
out float fade;

void main() {
    vec4 v = p3d_Vertex;
    float radial = length(v.xy);
    float wave = sin((v.z * 1.7) + u_time * (2.2 + u_phase * 0.7) + u_phase * 6.2831);
    float shear = cos((v.x + v.y) * 0.55 + u_time * 1.4 + u_phase * 9.0);
    v.x += wave * u_amp * (0.25 + radial * 0.03);
    v.y += shear * u_amp * 0.18;
    v.z += sin(radial * 0.85 + u_time * 1.8 + u_phase * 11.0) * u_amp * 0.22;
    fade = clamp(0.35 + radial * 0.03, 0.35, 0.9);
    uv = p3d_MultiTexCoord0;
    gl_Position = p3d_ModelViewProjectionMatrix * v;
}
"""

FRAG_SHADER = """
#version 130
uniform sampler2D p3d_Texture0;
uniform vec4 u_tint;
uniform float u_time;
in vec2 uv;
in float fade;
out vec4 fragColor;

void main() {
    vec2 scroll = vec2(
        uv.x + sin(uv.y * 16.0 + u_time * 5.0) * 0.006,
        uv.y + u_time * 0.03
    );
    vec4 tex = texture(p3d_Texture0, scroll);
    float stripe = step(0.55, fract(uv.y * 44.0 + u_time * 3.0));
    float pulse = 0.6 + 0.4 * sin(u_time * 2.7 + uv.y * 8.0);
    vec3 rgb = mix(tex.rgb, u_tint.rgb, 0.35 + stripe * 0.25);
    fragColor = vec4(rgb * pulse, tex.a * u_tint.a * fade);
}
"""


def panda_path(path: str | Path) -> Filename:
    return Filename.fromOsSpecific(os.fspath(path))


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * clamp(t, 0.0, 1.0)


def lerp_angle_deg(a: float, b: float, t: float) -> float:
    delta = ((b - a + 180.0) % 360.0) - 180.0
    return a + delta * clamp(t, 0.0, 1.0)


def approach_vec(current: Vec3, target: Vec3, rate: float, dt: float) -> Vec3:
    amount = clamp(rate * dt, 0.0, 1.0)
    return current + (target - current) * amount


def segment_distance_squared(point: Vec3, start: Vec3, end: Vec3) -> float:
    seg = end - start
    length_sq = seg.lengthSquared()
    if length_sq <= 1e-8:
        return (point - start).lengthSquared()
    t = clamp((point - start).dot(seg) / length_sq, 0.0, 1.0)
    closest = start + seg * t
    return (point - closest).lengthSquared()


class TextureFactory:
    def __init__(self, app: "CityHeroApp") -> None:
        self.app = app
        self.cache: dict[str, Texture] = {}

    def _configure_tex(self, tex: Texture) -> Texture:
        tex.setWrapU(SamplerState.WM_repeat)
        tex.setWrapV(SamplerState.WM_repeat)
        tex.setMinfilter(SamplerState.FT_linear_mipmap_linear)
        tex.setMagfilter(SamplerState.FT_linear)
        tex.setAnisotropicDegree(8)
        return tex

    def _load_asset_texture(self, name: str, fallbacks: list[str] | None = None) -> Texture | None:
        candidates = [name]
        if fallbacks:
            candidates.extend(fallbacks)
        for candidate in candidates:
            path = STRUCTURE_TEX_DIR / f"{candidate}.png"
            if path.exists():
                tex = self.app.loader.loadTexture(panda_path(path))
                if tex is not None:
                    self.cache[name] = self._configure_tex(tex)
                    return self.cache[name]
        return None

    def _save_and_load(self, name: str, image: PNMImage) -> Texture:
        path = TEX_DIR / f"{name}.png"

        tex = Texture(name)
        loaded = tex.load(image)
        if not loaded:
            fallback = PNMImage(2, 2, 4)
            for y in range(2):
                for x in range(2):
                    fallback.setXelA(x, y, 1.0, 0.0, 1.0, 1.0)
            tex.load(fallback)

        try:
            image.write(Filename.fromOsSpecific(str(path)))
        except Exception:
            pass

        self.cache[name] = self._configure_tex(tex)
        return self.cache[name]

    def make_facade(self, name: str, seed: int, base_rgb: tuple[int, int, int], accent_rgb: tuple[int, int, int]) -> Texture:
        if name in self.cache:
            return self.cache[name]
        asset_tex = self._load_asset_texture(name)
        if asset_tex is not None:
            return asset_tex
        rnd = random.Random(seed)
        w, h = 256, 512
        img = PNMImage(w, h, 4)
        base = [c / 255.0 for c in base_rgb]
        accent = [c / 255.0 for c in accent_rgb]

        for y in range(h):
            t = y / max(1, h - 1)
            for x in range(w):
                n = rnd.random() * 0.035
                tone = 0.72 - t * 0.22 + math.sin((x + y) * 0.06) * 0.02
                r = clamp(base[0] * tone + n, 0.0, 1.0)
                g = clamp(base[1] * tone + n, 0.0, 1.0)
                b = clamp(base[2] * tone + n, 0.0, 1.0)
                img.setXelA(x, y, r, g, b, 1.0)

        cols = rnd.randint(6, 10)
        rows = rnd.randint(18, 26)
        margin_x = rnd.randint(8, 20)
        margin_y = rnd.randint(10, 18)
        gap_x = rnd.randint(5, 10)
        gap_y = rnd.randint(7, 12)
        cell_w = max(10, (w - margin_x * 2 - (cols - 1) * gap_x) // cols)
        cell_h = max(10, (h - margin_y * 2 - (rows - 1) * gap_y) // rows)

        for row in range(rows):
            for col in range(cols):
                x0 = margin_x + col * (cell_w + gap_x)
                y0 = margin_y + row * (cell_h + gap_y)
                lit = rnd.random() > 0.34
                win_r = accent[0] * (0.65 + rnd.random() * 0.35) if lit else 0.05 + rnd.random() * 0.06
                win_g = accent[1] * (0.65 + rnd.random() * 0.35) if lit else 0.05 + rnd.random() * 0.06
                win_b = accent[2] * (0.65 + rnd.random() * 0.35) if lit else 0.06 + rnd.random() * 0.08
                for yy in range(y0, min(h, y0 + cell_h)):
                    for xx in range(x0, min(w, x0 + cell_w)):
                        border = xx == x0 or yy == y0 or xx == x0 + cell_w - 1 or yy == y0 + cell_h - 1
                        mul = 0.55 if border else 1.0
                        img.setXelA(xx, yy, clamp(win_r * mul, 0, 1), clamp(win_g * mul, 0, 1), clamp(win_b * mul, 0, 1), 1.0)

        for _ in range(rnd.randint(14, 24)):
            band_y = rnd.randint(0, h - 4)
            band_h = rnd.randint(2, 10)
            tint = rnd.choice([
                (0.85, 0.10, 0.55),
                (0.10, 0.95, 0.92),
                (0.95, 0.86, 0.20),
                (0.75, 0.75, 0.80),
            ])
            for yy in range(band_y, min(h, band_y + band_h)):
                for xx in range(w):
                    mix = 0.12 + rnd.random() * 0.18
                    pr, pg, pb = img.getXel(xx, yy)
                    img.setXelA(
                        xx,
                        yy,
                        clamp(pr * (1 - mix) + tint[0] * mix, 0, 1),
                        clamp(pg * (1 - mix) + tint[1] * mix, 0, 1),
                        clamp(pb * (1 - mix) + tint[2] * mix, 0, 1),
                        1.0,
                    )

        return self._save_and_load(name, img)

    def make_roof(self, name: str, seed: int) -> Texture:
        if name in self.cache:
            return self.cache[name]
        asset_tex = self._load_asset_texture(name, ["roof_generic", "desert_roof"])
        if asset_tex is not None:
            return asset_tex
        rnd = random.Random(seed)
        w, h = 256, 256
        img = PNMImage(w, h, 4)
        for y in range(h):
            for x in range(w):
                band = 0.13 + ((x // 16) % 2) * 0.04
                noise = rnd.random() * 0.06
                v = clamp(0.16 + band + noise, 0, 1)
                img.setXelA(x, y, v * 0.8, v * 0.9, v, 1.0)
        for _ in range(24):
            rx = rnd.randint(8, w - 28)
            ry = rnd.randint(8, h - 28)
            rw = rnd.randint(8, 26)
            rh = rnd.randint(8, 26)
            for yy in range(ry, min(h, ry + rh)):
                for xx in range(rx, min(w, rx + rw)):
                    img.setXelA(xx, yy, 0.05, 0.08, 0.10, 1.0)
        return self._save_and_load(name, img)

    def make_road(self, name: str, seed: int) -> Texture:
        if name in self.cache:
            return self.cache[name]
        rnd = random.Random(seed)
        w, h = 512, 512
        img = PNMImage(w, h, 4)
        for y in range(h):
            for x in range(w):
                grain = rnd.random() * 0.018
                patch = 0.01 * math.sin(x * 0.035) + 0.012 * math.cos(y * 0.05)
                v = clamp(0.095 + grain + patch, 0.0, 1.0)
                img.setXelA(x, y, v, v, v * 1.03, 1.0)

        edge_positions = [54, w - 54]
        white_lane_positions = [int(w * 0.26), int(w * 0.74)]
        yellow_positions = [w // 2 - 5, w // 2 + 5]

        for y in range(h):
            dash = (y // 32) % 2 == 0
            for xx in edge_positions:
                for dx in range(-2, 3):
                    img.setXelA(int(clamp(xx + dx, 0, w - 1)), y, 0.88, 0.88, 0.88, 1.0)
            for xx in white_lane_positions:
                if dash:
                    for dx in range(-2, 3):
                        img.setXelA(int(clamp(xx + dx, 0, w - 1)), y, 0.82, 0.82, 0.82, 1.0)
            for xx in yellow_positions:
                for dx in range(-1, 2):
                    img.setXelA(int(clamp(xx + dx, 0, w - 1)), y, 0.92, 0.82, 0.24, 1.0)

        crosswalk_rows = [84, h - 84]
        for cy in crosswalk_rows:
            for stripe in range(-5, 6):
                y0 = int(cy + stripe * 10)
                if stripe % 2 != 0:
                    continue
                for yy in range(max(0, y0), min(h, y0 + 5)):
                    for xx in range(96, w - 96):
                        current = img.getXel(xx, yy)
                        mix = 0.35
                        img.setXelA(xx, yy, current[0] * (1 - mix) + 0.82 * mix, current[1] * (1 - mix) + 0.82 * mix, current[2] * (1 - mix) + 0.82 * mix, 1.0)

        return self._save_and_load(name, img)

    def make_glitch(self, name: str, seed: int) -> Texture:
        if name in self.cache:
            return self.cache[name]
        rnd = random.Random(seed)
        w, h = 256, 512
        img = PNMImage(w, h, 4)
        palette = [
            (0.06, 0.95, 0.92),
            (0.28, 1.00, 0.42),
            (0.93, 0.87, 0.18),
            (0.82, 0.82, 0.88),
            (0.16, 0.18, 0.25),
        ]
        for y in range(h):
            bar_h = rnd.randint(1, 8)
            if y % bar_h == 0:
                color = rnd.choice(palette)
            for x in range(w):
                alpha = 0.3 + rnd.random() * 0.55
                r = clamp(color[0] + rnd.random() * 0.06, 0, 1)
                g = clamp(color[1] + rnd.random() * 0.06, 0, 1)
                b = clamp(color[2] + rnd.random() * 0.06, 0, 1)
                img.setXelA(x, y, r, g, b, alpha)
        return self._save_and_load(name, img)

    def make_trail(self, name: str, seed: int) -> Texture:
        if name in self.cache:
            return self.cache[name]
        rnd = random.Random(seed)
        w, h = 96, 512
        img = PNMImage(w, h, 4)
        for y in range(h):
            fy = y / max(1, h - 1)
            tail = 1.0 - fy
            for x in range(w):
                fx = x / max(1, w - 1)
                center = 1.0 - abs(fx - 0.5) * 2.0
                edge = clamp(center ** 1.8, 0.0, 1.0)
                core = clamp(1.0 - fy * 0.86, 0.0, 1.0)
                shimmer = 0.88 + 0.12 * math.sin(fy * 24.0 + fx * 10.0 + rnd.random() * 0.2)
                alpha = clamp((core ** 1.2) * edge * shimmer, 0.0, 1.0)
                rgb = clamp(0.76 + tail * 0.24, 0.0, 1.0)
                img.setXelA(x, y, rgb, rgb, rgb, alpha)
        path = TEX_DIR / f"{name}.png"
        try:
            img.write(Filename.fromOsSpecific(str(path)))
        except Exception:
            pass
        tex = Texture(name)
        tex.load(img)
        tex.setWrapU(SamplerState.WM_clamp)
        tex.setWrapV(SamplerState.WM_clamp)
        tex.setMinfilter(SamplerState.FT_linear)
        tex.setMagfilter(SamplerState.FT_linear)
        self.cache[name] = tex
        return tex


    def make_sun(self, name: str, seed: int) -> Texture:
        if name in self.cache:
            return self.cache[name]
        rnd = random.Random(seed)
        w, h = 512, 512
        img = PNMImage(w, h, 4)
        cx = w * 0.5
        cy = h * 0.5
        max_r = min(w, h) * 0.42
        for y in range(h):
            for x in range(w):
                dx = x - cx
                dy = y - cy
                d = (dx * dx + dy * dy) ** 0.5
                t = clamp(d / max_r, 0.0, 1.0)
                glow = 1.0 - t
                corona = clamp((1.0 - t) ** 0.35, 0.0, 1.0)
                noise = (rnd.random() - 0.5) * 0.03
                r = clamp(0.72 + glow * 0.28 + noise, 0.0, 1.0)
                g = clamp(0.08 + glow * 0.10 + noise * 0.4, 0.0, 1.0)
                b = clamp(0.04 + glow * 0.05, 0.0, 1.0)
                alpha = clamp(corona * 0.96, 0.0, 1.0)
                if t > 0.95:
                    alpha *= max(0.0, 1.0 - (t - 0.95) / 0.05)
                img.setXelA(x, y, r, g, b, alpha)
        return self._save_and_load(name, img)

    def make_overlay(self, name: str, seed: int) -> Texture:
        if name in self.cache:
            return self.cache[name]
        rnd = random.Random(seed)
        w, h = 512, 512
        img = PNMImage(w, h, 4)
        cx, cy = w * 0.5, h * 0.5
        max_d = math.sqrt(cx * cx + cy * cy)
        for y in range(h):
            for x in range(w):
                dx = x - cx
                dy = y - cy
                d = math.sqrt(dx * dx + dy * dy) / max_d
                vignette = clamp((d - 0.45) * 1.7, 0.0, 0.65)
                scan = 0.04 if (y % 4) < 2 else 0.0
                jitter = rnd.random() * 0.015
                alpha = clamp(vignette + scan + jitter, 0.0, 0.75)
                img.setXelA(x, y, 0.0, 0.0, 0.0, alpha)
        return self._save_and_load(name, img)


class GeomFactory:
    @staticmethod
    def make_box(width: float, depth: float, height: float, uvx: float = 1.0, uvy: float = 1.0) -> GeomNode:
        fmt = GeomVertexFormat.getV3n3t2()
        vdata = GeomVertexData("box", fmt, Geom.UHStatic)
        vertex = GeomVertexWriter(vdata, "vertex")
        normal = GeomVertexWriter(vdata, "normal")
        texcoord = GeomVertexWriter(vdata, "texcoord")
        tris = GeomTriangles(Geom.UHStatic)

        hw = width * 0.5
        hd = depth * 0.5
        h = height

        faces = [
            ((-hw, -hd, 0), (hw, -hd, 0), (hw, -hd, h), (-hw, -hd, h), (0, -1, 0)),
            ((hw, hd, 0), (-hw, hd, 0), (-hw, hd, h), (hw, hd, h), (0, 1, 0)),
            ((-hw, hd, 0), (-hw, -hd, 0), (-hw, -hd, h), (-hw, hd, h), (-1, 0, 0)),
            ((hw, -hd, 0), (hw, hd, 0), (hw, hd, h), (hw, -hd, h), (1, 0, 0)),
            ((-hw, -hd, h), (hw, -hd, h), (hw, hd, h), (-hw, hd, h), (0, 0, 1)),
            ((-hw, hd, 0), (hw, hd, 0), (hw, -hd, 0), (-hw, -hd, 0), (0, 0, -1)),
        ]
        idx = 0
        uv_sets = [(0, 0), (uvx, 0), (uvx, uvy), (0, uvy)]
        for p1, p2, p3, p4, nrm in faces:
            for pos, uv in zip((p1, p2, p3, p4), uv_sets):
                vertex.addData3f(*pos)
                normal.addData3f(*nrm)
                texcoord.addData2f(*uv)
            tris.addVertices(idx, idx + 1, idx + 2)
            tris.addVertices(idx, idx + 2, idx + 3)
            idx += 4
        geom = Geom(vdata)
        geom.addPrimitive(tris)
        node = GeomNode("box")
        node.addGeom(geom)
        return node

    @staticmethod
    def make_quad(width: float, depth: float, uvx: float = 1.0, uvy: float = 1.0) -> GeomNode:
        fmt = GeomVertexFormat.getV3n3t2()
        vdata = GeomVertexData("quad", fmt, Geom.UHStatic)
        vertex = GeomVertexWriter(vdata, "vertex")
        normal = GeomVertexWriter(vdata, "normal")
        texcoord = GeomVertexWriter(vdata, "texcoord")
        tris = GeomTriangles(Geom.UHStatic)

        hw = width * 0.5
        hd = depth * 0.5
        verts = [(-hw, -hd, 0), (hw, -hd, 0), (hw, hd, 0), (-hw, hd, 0)]
        uvs = [(0, 0), (uvx, 0), (uvx, uvy), (0, uvy)]
        for pos, uv in zip(verts, uvs):
            vertex.addData3f(*pos)
            normal.addData3f(0, 0, 1)
            texcoord.addData2f(*uv)
        tris.addVertices(0, 1, 2)
        tris.addVertices(0, 2, 3)
        geom = Geom(vdata)
        geom.addPrimitive(tris)
        node = GeomNode("quad")
        node.addGeom(geom)
        return node


    @staticmethod
    def make_pyramid(width: float, depth: float, height: float, uvx: float = 1.0, uvy: float = 1.0) -> GeomNode:
        fmt = GeomVertexFormat.getV3n3t2()
        vdata = GeomVertexData("pyramid", fmt, Geom.UHStatic)
        vertex = GeomVertexWriter(vdata, "vertex")
        normal = GeomVertexWriter(vdata, "normal")
        texcoord = GeomVertexWriter(vdata, "texcoord")
        tris = GeomTriangles(Geom.UHStatic)

        hw = width * 0.5
        hd = depth * 0.5
        apex = (0.0, 0.0, height)
        base = [(-hw, -hd, 0.0), (hw, -hd, 0.0), (hw, hd, 0.0), (-hw, hd, 0.0)]

        def add_face(p0, p1, p2, uv=((0, 0), (1, 0), (0.5, 1.0))):
            start = vertex.getWriteRow()
            ux = Vec3(p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2])
            vx = Vec3(p2[0] - p0[0], p2[1] - p0[1], p2[2] - p0[2])
            n = ux.cross(vx)
            if n.lengthSquared() < 1e-8:
                n = Vec3(0, 0, 1)
            else:
                n.normalize()
            for pos, uvv in zip((p0, p1, p2), uv):
                vertex.addData3f(*pos)
                normal.addData3f(n)
                texcoord.addData2f(*uvv)
            tris.addVertices(start, start + 1, start + 2)

        # four sides
        add_face(base[0], base[1], apex)
        add_face(base[1], base[2], apex)
        add_face(base[2], base[3], apex)
        add_face(base[3], base[0], apex)
        # base
        start = vertex.getWriteRow()
        for pos, uv in zip((base[0], base[3], base[2], base[1]), ((0, 0), (0, uvy), (uvx, uvy), (uvx, 0))):
            vertex.addData3f(*pos)
            normal.addData3f(0, 0, -1)
            texcoord.addData2f(*uv)
        tris.addVertices(start, start + 1, start + 2)
        tris.addVertices(start, start + 2, start + 3)

        geom = Geom(vdata)
        geom.addPrimitive(tris)
        node = GeomNode("pyramid")
        node.addGeom(geom)
        return node



def _make_suit_texture(name: str = "smooth_hero_suit") -> Texture:
    size = 512
    img = PNMImage(size, size, 4)
    for y in range(size):
        fy = y / (size - 1)
        for x in range(size):
            fx = x / (size - 1)
            radial = ((fx - 0.5) ** 2 + (fy - 0.5) ** 2) ** 0.5
            base = 0.10 + 0.05 * math.sin(x * 0.045) + 0.04 * math.cos(y * 0.035)
            large_grid = 1.0 if (x % 96 in range(0, 3) or y % 96 in range(0, 3)) else 0.0
            micro_grid = 1.0 if (x % 24 == 0 or y % 24 == 0) else 0.0
            diag = 0.5 + 0.5 * math.sin((x + y) * 0.08)
            pulse = 0.5 + 0.5 * math.sin((fy * 18.0) + (fx * 9.0))
            glow = large_grid * 0.28 + micro_grid * 0.08 + diag * 0.04 + pulse * 0.03
            r = clamp(0.08 + base * 0.55 + glow * 0.42, 0.0, 1.0)
            g = clamp(0.12 + base * 0.85 + glow * 0.68, 0.0, 1.0)
            b = clamp(0.18 + base * 1.10 + glow * 0.95, 0.0, 1.0)
            alpha = clamp(0.74 + (1.0 - radial) * 0.18 + large_grid * 0.06, 0.48, 0.96)
            img.setXelA(x, y, r, g, b, alpha)
    tex = Texture(name)
    tex.load(img)
    tex.setWrapU(SamplerState.WM_repeat)
    tex.setWrapV(SamplerState.WM_repeat)
    tex.setMinfilter(SamplerState.FT_linear_mipmap_linear)
    tex.setMagfilter(SamplerState.FT_linear)
    tex.setAnisotropicDegree(8)
    return tex


def _make_emissive_texture(name: str = "smooth_hero_emissive") -> Texture:
    size = 256
    img = PNMImage(size, size, 4)
    for y in range(size):
        fy = y / (size - 1)
        for x in range(size):
            fx = x / (size - 1)
            center = 1.0 - abs(fx - 0.5) * 2.0
            scan = 1.0 if (y % 12 in range(0, 2)) else 0.0
            data_bands = 0.5 + 0.5 * math.sin(fy * 28.0 + fx * 12.0)
            alpha = clamp((center ** 1.55) * (0.48 + data_bands * 0.44) + scan * 0.18, 0.0, 1.0)
            r = clamp(0.34 + data_bands * 0.22 + scan * 0.10, 0.0, 1.0)
            g = clamp(0.76 + data_bands * 0.22 + scan * 0.16, 0.0, 1.0)
            b = clamp(0.96 + data_bands * 0.04 + scan * 0.02, 0.0, 1.0)
            img.setXelA(x, y, r, g, b, alpha)
    tex = Texture(name)
    tex.load(img)
    tex.setWrapU(SamplerState.WM_clamp)
    tex.setWrapV(SamplerState.WM_clamp)
    tex.setMinfilter(SamplerState.FT_linear)
    tex.setMagfilter(SamplerState.FT_linear)
    return tex


def _make_boss_eye_texture(name: str = "boss_eye_shell") -> Texture:
    size = 512
    img = PNMImage(size, size, 4)
    cx = cy = size * 0.5
    max_r = size * 0.48
    for y in range(size):
        for x in range(size):
            dx = x - cx
            dy = y - cy
            d = math.sqrt(dx * dx + dy * dy) / max_r
            ring = 1.0 - clamp(d, 0.0, 1.0)
            vein = 0.5 + 0.5 * math.sin((dx * 0.11 + dy * 0.07) + d * 26.0)
            core = clamp(0.10 + ring * 0.18 + vein * 0.06, 0.0, 1.0)
            img.setXelA(x, y, clamp(0.05 + core * 0.85, 0.0, 1.0), clamp(0.01 + core * 0.12, 0.0, 1.0), clamp(0.01 + core * 0.10, 0.0, 1.0), 1.0 if d <= 1.0 else 0.0)
    tex = Texture(name)
    tex.load(img)
    tex.setWrapU(SamplerState.WM_clamp)
    tex.setWrapV(SamplerState.WM_clamp)
    tex.setMinfilter(SamplerState.FT_linear_mipmap_linear)
    tex.setMagfilter(SamplerState.FT_linear)
    return tex


def _make_boss_iris_texture(name: str = "boss_eye_iris") -> Texture:
    size = 256
    img = PNMImage(size, size, 4)
    cx = cy = size * 0.5
    max_r = size * 0.48
    for y in range(size):
        for x in range(size):
            dx = x - cx
            dy = y - cy
            d = math.sqrt(dx * dx + dy * dy) / max_r
            ring = 1.0 - clamp(d, 0.0, 1.0)
            spokes = 0.5 + 0.5 * math.sin(math.atan2(dy, dx) * 14.0 + d * 16.0)
            heat = clamp(0.18 + ring * 0.74 + spokes * 0.16, 0.0, 1.0)
            img.setXelA(x, y, clamp(0.26 + heat * 0.74, 0.0, 1.0), clamp(0.02 + heat * 0.08, 0.0, 1.0), clamp(0.01 + heat * 0.05, 0.0, 1.0), 1.0 if d <= 1.0 else 0.0)
    tex = Texture(name)
    tex.load(img)
    tex.setWrapU(SamplerState.WM_clamp)
    tex.setWrapV(SamplerState.WM_clamp)
    tex.setMinfilter(SamplerState.FT_linear_mipmap_linear)
    tex.setMagfilter(SamplerState.FT_linear)
    return tex

class SmoothFactory:
    def __init__(self) -> None:
        self.fmt = GeomVertexFormat.getV3n3t2()

    def uv_sphere(self, name: str, radius: float = 0.5, slices: int = 28, stacks: int = 20) -> NodePath:
        vdata = GeomVertexData(name, self.fmt, Geom.UHStatic)
        vw = GeomVertexWriter(vdata, "vertex")
        nw = GeomVertexWriter(vdata, "normal")
        tw = GeomVertexWriter(vdata, "texcoord")
        tri = GeomTriangles(Geom.UHStatic)

        for stack in range(stacks + 1):
            phi = math.pi * stack / stacks
            for sl in range(slices + 1):
                theta = math.tau * sl / slices
                x = math.sin(phi) * math.cos(theta)
                y = math.sin(phi) * math.sin(theta)
                z = math.cos(phi)
                vw.addData3f(x * radius, y * radius, z * radius)
                nw.addData3f(x, y, z)
                tw.addData2f(theta / math.tau, phi / math.pi)

        row = slices + 1
        for stack in range(stacks):
            for sl in range(slices):
                i0 = stack * row + sl
                i1 = i0 + 1
                i2 = i0 + row
                i3 = i2 + 1
                tri.addVertices(i0, i2, i1)
                tri.addVertices(i1, i2, i3)

        geom = Geom(vdata)
        geom.addPrimitive(tri)
        node = GeomNode(name)
        node.addGeom(geom)
        return NodePath(node)

    def cylinder(self, name: str, radius: float = 0.5, height: float = 1.0, slices: int = 24) -> NodePath:
        hz = height * 0.5
        vdata = GeomVertexData(name, self.fmt, Geom.UHStatic)
        vw = GeomVertexWriter(vdata, "vertex")
        nw = GeomVertexWriter(vdata, "normal")
        tw = GeomVertexWriter(vdata, "texcoord")
        tri = GeomTriangles(Geom.UHStatic)

        for i in range(slices + 1):
            ang = math.tau * i / slices
            x = math.cos(ang)
            y = math.sin(ang)
            for z, v in ((-hz, 0.0), (hz, 1.0)):
                vw.addData3f(x * radius, y * radius, z)
                nw.addData3f(x, y, 0.0)
                tw.addData2f(i / slices, v)

        for i in range(slices):
            i0 = i * 2
            i1 = i0 + 1
            i2 = i0 + 2
            i3 = i0 + 3
            tri.addVertices(i0, i2, i1)
            tri.addVertices(i1, i2, i3)

        start_bottom = vw.getWriteRow()
        vw.addData3f(0, 0, -hz)
        nw.addData3f(0, 0, -1)
        tw.addData2f(0.5, 0.5)
        for i in range(slices + 1):
            ang = math.tau * i / slices
            x = math.cos(ang) * radius
            y = math.sin(ang) * radius
            vw.addData3f(x, y, -hz)
            nw.addData3f(0, 0, -1)
            tw.addData2f((x / (radius * 2)) + 0.5, (y / (radius * 2)) + 0.5)
        for i in range(slices):
            tri.addVertices(start_bottom, start_bottom + i + 1, start_bottom + i + 2)

        start_top = vw.getWriteRow()
        vw.addData3f(0, 0, hz)
        nw.addData3f(0, 0, 1)
        tw.addData2f(0.5, 0.5)
        for i in range(slices + 1):
            ang = math.tau * i / slices
            x = math.cos(ang) * radius
            y = math.sin(ang) * radius
            vw.addData3f(x, y, hz)
            nw.addData3f(0, 0, 1)
            tw.addData2f((x / (radius * 2)) + 0.5, (y / (radius * 2)) + 0.5)
        for i in range(slices):
            tri.addVertices(start_top, start_top + i + 2, start_top + i + 1)

        geom = Geom(vdata)
        geom.addPrimitive(tri)
        node = GeomNode(name)
        node.addGeom(geom)
        return NodePath(node)

    def box(self, name: str, sx: float, sy: float, sz: float) -> NodePath:
        x = sx * 0.5
        y = sy * 0.5
        z = sz * 0.5
        faces = [
            [(-x, y, -z), (x, y, -z), (x, y, z), (-x, y, z), (0, 1, 0)],
            [(x, -y, -z), (-x, -y, -z), (-x, -y, z), (x, -y, z), (0, -1, 0)],
            [(x, y, -z), (x, -y, -z), (x, -y, z), (x, y, z), (1, 0, 0)],
            [(-x, -y, -z), (-x, y, -z), (-x, y, z), (-x, -y, z), (-1, 0, 0)],
            [(-x, y, z), (x, y, z), (x, -y, z), (-x, -y, z), (0, 0, 1)],
            [(-x, -y, -z), (x, -y, -z), (x, y, -z), (-x, y, -z), (0, 0, -1)],
        ]
        vdata = GeomVertexData(name, self.fmt, Geom.UHStatic)
        vw = GeomVertexWriter(vdata, "vertex")
        nw = GeomVertexWriter(vdata, "normal")
        tw = GeomVertexWriter(vdata, "texcoord")
        tri = GeomTriangles(Geom.UHStatic)

        for face in faces:
            p0, p1, p2, p3, n = face
            start = vw.getWriteRow()
            for p, uv in ((p0, (0, 0)), (p1, (1, 0)), (p2, (1, 1)), (p3, (0, 1))):
                vw.addData3f(*p)
                nw.addData3f(*n)
                tw.addData2f(*uv)
            tri.addVertices(start, start + 1, start + 2)
            tri.addVertices(start, start + 2, start + 3)

        geom = Geom(vdata)
        geom.addPrimitive(tri)
        node = GeomNode(name)
        node.addGeom(geom)
        return NodePath(node)

    def ribbon(self, name: str, width: float, length: float) -> NodePath:
        return self.box(name, width, 0.015, length)


_SMOOTH_FACTORY = SmoothFactory()


def build_sheet_style_hero(parent: NodePath) -> NodePath:
    root = parent.attachNewNode("sheet_style_hero")
    suit_tex = _make_suit_texture()
    emissive_tex = _make_emissive_texture()

    parts: dict[str, NodePath] = {}
    base_hprs: dict[str, tuple[float, float, float]] = {}
    emissives: list[NodePath] = []
    trails: list[NodePath] = []
    capes: list[NodePath] = []
    cape_geos: list[NodePath] = []

    def remember(name: str, node: NodePath, hpr=(0.0, 0.0, 0.0)) -> NodePath:
        parts[name] = node
        base_hprs[name] = (hpr[0], hpr[1], hpr[2])
        return node

    def joint(name: str, target: NodePath = root, pos=(0, 0, 0), hpr=(0, 0, 0)) -> NodePath:
        node = target.attachNewNode(name)
        node.setPos(*pos)
        node.setHpr(*hpr)
        return remember(name, node, hpr)

    def attach_geom(part: NodePath, name: str, target: NodePath = root, pos=(0, 0, 0), hpr=(0, 0, 0), scale=(1, 1, 1), color=(1, 1, 1, 1), texture=None, glow=False, alpha=1.0) -> NodePath:
        part.reparentTo(target)
        part.setPos(*pos)
        part.setHpr(*hpr)
        part.setScale(*scale)
        part.setTexture(texture or suit_tex, 1)
        if glow:
            part.setLightOff(1)
            part.setColorScale(color[0] * 1.4, color[1] * 1.4, color[2] * 1.4, alpha)
            part.setTransparency(TransparencyAttrib.M_alpha)
            part.setDepthWrite(False)
            part.setBin("fixed", 20)
            emissives.append(part)
        else:
            part.setColorScale(color[0], color[1], color[2], alpha)
        return part

    suit = (0.74, 0.80, 0.90, 0.96)
    suit_dark = (0.12, 0.15, 0.22, 0.96)
    armor = (0.88, 0.92, 0.98, 0.98)
    glow = (0.92, 0.98, 1.0, 0.98)

    attach_geom(_SMOOTH_FACTORY.uv_sphere("pelvis_geo", 0.17, 30, 22), "pelvis_geo", pos=(0, 0, 0.98), scale=(0.90, 0.72, 0.82), color=suit)
    attach_geom(_SMOOTH_FACTORY.cylinder("abdomen_geo", 0.145, 0.30, 28), "abdomen_geo", pos=(0, 0, 1.17), scale=(0.82, 0.68, 1.0), color=suit)
    attach_geom(_SMOOTH_FACTORY.uv_sphere("chest_geo", 0.22, 32, 24), "chest_geo", pos=(0, 0, 1.38), scale=(0.98, 0.78, 1.08), color=suit)
    attach_geom(_SMOOTH_FACTORY.uv_sphere("clavicle_shell_geo", 0.18, 28, 18), "clavicle_shell_geo", pos=(0, 0.01, 1.47), scale=(1.22, 0.72, 0.42), color=armor)
    attach_geom(_SMOOTH_FACTORY.cylinder("neck_geo", 0.07, 0.14, 22), "neck_geo", pos=(0, 0, 1.58), scale=(0.88, 0.88, 1.0), color=suit)

    attach_geom(_SMOOTH_FACTORY.uv_sphere("helmet_geo", 0.15, 32, 24), "helmet_geo", pos=(0, 0.005, 1.74), scale=(0.84, 0.96, 1.10), color=armor)
    attach_geom(_SMOOTH_FACTORY.box("jaw_geo", 0.19, 0.15, 0.10), "jaw_geo", pos=(0, 0.08, 1.61), hpr=(0, -16, 0), color=armor)
    visor = attach_geom(_SMOOTH_FACTORY.box("visor_geo", 0.12, 0.09, 0.18), "visor_geo", pos=(0, 0.11, 1.71), hpr=(0, 16, 0), color=suit_dark)
    visor.setLightOff(1)
    visor.setColorScale(0.03, 0.05, 0.03, 1.0)

    attach_geom(_SMOOTH_FACTORY.cylinder("emblem_ring", 0.06, 0.02, 28), "emblem_ring", pos=(0, 0.145, 1.46), hpr=(0, 90, 0), color=glow, texture=emissive_tex, glow=True)
    attach_geom(_SMOOTH_FACTORY.box("emblem_bar", 0.08, 0.015, 0.02), "emblem_bar", pos=(0, 0.152, 1.46), color=glow, texture=emissive_tex, glow=True)
    attach_geom(_SMOOTH_FACTORY.box("emblem_v", 0.02, 0.015, 0.06), "emblem_v", pos=(0, 0.152, 1.46), color=glow, texture=emissive_tex, glow=True)

    def glow_strip(name: str, target: NodePath, pos, hpr, scale):
        return attach_geom(_SMOOTH_FACTORY.box(name, 0.028, 0.012, 0.24), name, target=target, pos=pos, hpr=hpr, scale=scale, color=glow, texture=emissive_tex, glow=True)

    glow_strip("center_torso", root, (0, 0.15, 1.31), (0, 0, 0), (0.8, 1.0, 0.75))
    glow_strip("left_chest", root, (-0.15, 0.14, 1.46), (0, 0, 64), (0.55, 1.0, 0.42))
    glow_strip("right_chest", root, (0.15, 0.14, 1.46), (0, 0, -64), (0.55, 1.0, 0.42))
    glow_strip("left_torso_outer", root, (-0.12, 0.15, 1.20), (0, 0, 16), (0.65, 1.0, 0.95))
    glow_strip("right_torso_outer", root, (0.12, 0.15, 1.20), (0, 0, -16), (0.65, 1.0, 0.95))
    glow_strip("left_torso_inner", root, (-0.05, 0.15, 1.18), (0, 0, 5), (0.42, 1.0, 0.84))
    glow_strip("right_torso_inner", root, (0.05, 0.15, 1.18), (0, 0, -5), (0.42, 1.0, 0.84))

    attach_geom(_SMOOTH_FACTORY.box("sternum_plate_geo", 0.16, 0.05, 0.34), "sternum_plate_geo", pos=(0.0, 0.165, 1.36), hpr=(0, 8, 0), color=armor, alpha=0.82)
    attach_geom(_SMOOTH_FACTORY.box("chest_band_geo", 0.34, 0.04, 0.08), "chest_band_geo", pos=(0.0, 0.172, 1.44), color=armor, alpha=0.78)
    for sx in (-1, 1):
        attach_geom(_SMOOTH_FACTORY.box(f"rib_plate_{'l' if sx < 0 else 'r'}_geo", 0.10, 0.04, 0.22), f"rib_plate_{'l' if sx < 0 else 'r'}_geo", pos=(0.11 * sx, 0.15, 1.30), hpr=(0, 6, -18 * sx), color=armor, alpha=0.76)
        attach_geom(_SMOOTH_FACTORY.box(f"hip_fin_{'l' if sx < 0 else 'r'}_geo", 0.08, 0.03, 0.18), f"hip_fin_{'l' if sx < 0 else 'r'}_geo", pos=(0.13 * sx, -0.02, 1.02), hpr=(0, 0, -28 * sx), color=armor, alpha=0.70)
        attach_geom(_SMOOTH_FACTORY.box(f"lat_glow_{'l' if sx < 0 else 'r'}_geo", 0.03, 0.015, 0.24), f"lat_glow_{'l' if sx < 0 else 'r'}_geo", pos=(0.16 * sx, 0.16, 1.34), hpr=(0, 0, -16 * sx), color=glow, texture=emissive_tex, glow=True, alpha=0.74)

    hip_x = 0.10
    for sx, side_name in ((-1, "l"), (1, "r")):
        shoulder = joint(f"upperarm_{side_name}", root, pos=(0.23 * sx, 0.0, 1.43), hpr=(0, 0, 0))
        attach_geom(_SMOOTH_FACTORY.uv_sphere(f"shoulder_{side_name}_geo", 0.10, 24, 18), f"shoulder_{side_name}_geo", target=shoulder, pos=(0, 0, 0), scale=(1.08, 1.00, 0.95), color=armor)
        attach_geom(_SMOOTH_FACTORY.cylinder(f"upperarm_{side_name}_geo", 0.07, 0.30, 22), f"upperarm_{side_name}_geo", target=shoulder, pos=(0, 0, -0.15), scale=(0.95, 0.85, 1.0), color=suit)
        glow_strip(f"shoulder_glow_{side_name}", shoulder, (0.0, 0.09, -0.02), (0, 0, 18 * sx), (0.34, 1.0, 0.46))
        glow_strip(f"upperarm_glow_{side_name}", shoulder, (0.0, 0.085, -0.15), (0, 10 * sx, 12 * sx), (0.28, 1.0, 0.86))

        elbow = joint(f"forearm_{side_name}", shoulder, pos=(0.0, 0.0, -0.30), hpr=(0, 0, 0))
        attach_geom(_SMOOTH_FACTORY.uv_sphere(f"elbow_{side_name}_geo", 0.055, 18, 14), f"elbow_{side_name}_geo", target=elbow, pos=(0, 0, 0), scale=(0.92, 0.82, 0.92), color=armor)
        attach_geom(_SMOOTH_FACTORY.cylinder(f"forearm_{side_name}_geo", 0.06, 0.28, 22), f"forearm_{side_name}_geo", target=elbow, pos=(0, 0, -0.14), scale=(0.88, 0.78, 1.0), color=suit)
        glow_strip(f"forearm_glow_{side_name}", elbow, (0.0, 0.07, -0.14), (0, 12 * sx, 10 * sx), (0.24, 1.0, 0.74))

        hand = joint(f"hand_{side_name}", elbow, pos=(0.0, 0.0, -0.28), hpr=(0, 0, 0))
        attach_geom(_SMOOTH_FACTORY.box(f"hand_{side_name}_geo", 0.09, 0.05, 0.16), f"hand_{side_name}_geo", target=hand, pos=(0, 0.01, -0.08), hpr=(0, 0, 0), color=armor)
        attach_geom(_SMOOTH_FACTORY.box(f"forearm_blade_{side_name}_geo", 0.04, 0.03, 0.18), f"forearm_blade_{side_name}_geo", target=elbow, pos=(0.06 * sx, 0.02, -0.10), hpr=(0, 0, -18 * sx), color=armor, alpha=0.72)
        attach_geom(_SMOOTH_FACTORY.box(f"knuckle_glow_{side_name}_geo", 0.05, 0.01, 0.10), f"knuckle_glow_{side_name}_geo", target=hand, pos=(0.0, 0.045, -0.05), color=glow, texture=emissive_tex, glow=True, alpha=0.76)

        thigh = joint(f"thigh_{side_name}", root, pos=(hip_x * sx, 0.0, 0.98), hpr=(0, 0, 0))
        attach_geom(_SMOOTH_FACTORY.cylinder(f"thigh_{side_name}_geo", 0.09, 0.42, 24), f"thigh_{side_name}_geo", target=thigh, pos=(0, 0, -0.21), scale=(0.95, 0.86, 1.0), color=suit)
        glow_strip(f"thigh_glow_{side_name}", thigh, (0.0, 0.10, -0.22), (0, 0, 0), (0.34, 1.0, 1.20))

        shin = joint(f"shin_{side_name}", thigh, pos=(0.0, 0.0, -0.42), hpr=(0, 0, 0))
        attach_geom(_SMOOTH_FACTORY.uv_sphere(f"knee_{side_name}_geo", 0.07, 20, 16), f"knee_{side_name}_geo", target=shin, pos=(0, 0.01, 0.0), scale=(1.0, 0.88, 0.92), color=armor)
        attach_geom(_SMOOTH_FACTORY.cylinder(f"shin_{side_name}_geo", 0.07, 0.43, 24), f"shin_{side_name}_geo", target=shin, pos=(0, 0, -0.215), scale=(0.86, 0.78, 1.0), color=suit)
        attach_geom(_SMOOTH_FACTORY.uv_sphere(f"calf_{side_name}_geo", 0.075, 20, 16), f"calf_{side_name}_geo", target=shin, pos=(0, -0.025, -0.21), scale=(0.90, 0.72, 1.12), color=armor)
        glow_strip(f"shin_glow_{side_name}", shin, (0.0, 0.09, -0.22), (0, 0, 0), (0.30, 1.0, 1.18))
        glow_strip(f"knee_glow_{side_name}", shin, (0.0, 0.11, 0.0), (0, 90, 0), (0.34, 0.75, 0.16))

        foot = joint(f"foot_{side_name}", shin, pos=(0.0, 0.0, -0.43), hpr=(0, 0, 0))
        attach_geom(_SMOOTH_FACTORY.box(f"foot_{side_name}_geo", 0.12, 0.28, 0.08), f"foot_{side_name}_geo", target=foot, pos=(0, 0.09, -0.04), color=armor)
        glow_strip(f"ankle_glow_{side_name}", foot, (0.0, 0.16, -0.01), (0, 65, 0), (0.32, 0.8, 0.26))
        attach_geom(_SMOOTH_FACTORY.box(f"shin_guard_{side_name}_geo", 0.08, 0.03, 0.22), f"shin_guard_{side_name}_geo", target=shin, pos=(0.0, 0.06, -0.18), hpr=(0, 8, 0), color=armor, alpha=0.74)

        attach_geom(_SMOOTH_FACTORY.box(f"eye_{side_name}", 0.045, 0.01, 0.015), f"eye_{side_name}", pos=(0.035 * sx, 0.158, 1.74), hpr=(0, 16 * sx, 14 * sx), color=glow, texture=emissive_tex, glow=True)

    # Capes removed: all character silhouettes are now built around technical armor, propulsion, and wing systems.
    capes = []
    cape_geos = []

    trail_specs = [
        ("trail_back", root, (0, -0.03, 1.38), (90, 0, 0), (0.55, 1.0, 1.25)),
        ("trail_hand_r", parts["hand_r"], (0.0, -0.01, -0.02), (90, 8, 0), (0.18, 1.0, 0.65)),
        ("trail_hand_l", parts["hand_l"], (0.0, -0.01, -0.02), (90, -8, 0), (0.18, 1.0, 0.65)),
        ("trail_foot_r", parts["foot_r"], (0.0, -0.02, -0.02), (90, 0, 0), (0.20, 1.0, 0.80)),
        ("trail_foot_l", parts["foot_l"], (0.0, -0.02, -0.02), (90, 0, 0), (0.20, 1.0, 0.80)),
    ]
    for name, target, pos, hpr, scale in trail_specs:
        trail = attach_geom(_SMOOTH_FACTORY.ribbon(name, 0.10, 0.52), name, target=target, pos=pos, hpr=hpr, scale=scale, color=(0.30, 1.0, 0.44, 1.0), texture=emissive_tex, glow=True, alpha=0.62)
        trail.setTwoSided(True)
        trails.append(trail)

    root.setPythonTag("parts", parts)
    root.setPythonTag("base_hprs", base_hprs)
    root.setPythonTag("emissives", emissives)
    root.setPythonTag("trails", trails)
    root.setPythonTag("capes", capes)
    root.setPythonTag("cape_geos", cape_geos)
    return root


class CityHeroApp(ShowBase):
    def __init__(self) -> None:
        super().__init__()
        self.disableMouse()
        self.setBackgroundColor(0.88, 0.89, 0.90, 1.0)

        self.accept("escape", self.handle_escape)
        self.accept("escape-up", self.handle_escape_release)
        self.accept("g", self.rebuild_city)
        self.accept("h", self.toggle_hud)
        self.accept("f1", self.toggle_overlay)
        self.accept("r", self.toggle_target_lock)
        self.accept("delete", self.reset_hero)
        self.accept("mouse1", self.on_attack_press)
        self.accept("mouse1-up", self.on_attack_release)
        self.accept("mouse3", self.activate_shield)
        self.accept("mouse3-up", self.release_shield)
        self.accept("wheel_up", self.adjust_zoom, [-1.2])
        self.accept("wheel_down", self.adjust_zoom, [1.2])
        self.accept("x", self.activate_xray)
        self.accept("c", self.cycle_player_emote)
        self.accept("tab", self.on_settings_input, ["tab"])
        self.accept("arrow_up", self.on_settings_input, ["up"])
        self.accept("arrow_down", self.on_settings_input, ["down"])
        self.accept("arrow_left", self.on_settings_input, ["left"])
        self.accept("arrow_right", self.on_settings_input, ["right"])
        self.accept("enter", self.on_settings_input, ["enter"])
        self.accept("backspace", self.on_settings_input, ["reset"])

        self.taskMgr.add(self.holoverse_host_tick, "holoverse-host-return-poll")

        self.escape_pending = False
        self.hud_visible = True
        self.overlay_visible = True
        self.mouse_captured = True
        self.settings_open = False
        self.settings_update_accum = 0.0
        self.settings_tab = 0
        self.settings_cursor = 0
        self.settings_tab_names = ["General", "Controls", "Performance"]
        self.settings_path = SETTINGS_PATH
        self.settings_data = self.load_settings()
        self.used_power_signatures: set[tuple] = set()
        self.used_appearance_signatures: set[tuple] = set()
        self.hero_ceiling_z = 240.0
        self.boss_respawn_delay = 5.0 if _preview else 60.0

        self.keys: set[str] = set()
        self.watch_keys = {
            "w": "w",
            "a": "a",
            "s": "s",
            "d": "d",
            "q": "q",
            "e": "e",
            "space": "space",
            "shift": "shift",
            "f": "f",
            "1": "1",
            "2": "2",
            "3": "3",
        }
        for event_name, key_name in self.watch_keys.items():
            self.accept(event_name, self.on_key_down, [key_name])
            self.accept(f"{event_name}-up", self.on_key_up, [key_name])

        self.win.set_clear_color_active(True)
        props = WindowProperties()
        props.setCursorHidden(True)
        if hasattr(self.win, "requestProperties"):
            self.win.requestProperties(props)

        self.texture_factory = TextureFactory(self)
        self.shader = Shader.make(Shader.SL_GLSL, VERT_SHADER, FRAG_SHADER)
        self.apply_runtime_settings(initial=True)

        self.city_block = 42.0
        self.city_radius = 5
        self.city_world_radius = self.city_block * (self.city_radius + 0.75)
        self.render_block_radius = self.city_world_radius * 0.82
        self.surface_water_z = 0.62
        self.outskirts_chunk_size = 160.0
        self.outskirts_visible_radius = 0

        self.city_root = self.render.attachNewNode("city_root")
        self.outskirts_root = self.render.attachNewNode("outskirts_root")
        self.traffic_root = self.render.attachNewNode("traffic_root")
        self.police_root = self.render.attachNewNode("police_root")
        self.hero_root = self.render.attachNewNode("hero_root")
        self.hero_visual: NodePath | None = None
        self.hero_parts: dict[str, NodePath] = {}
        self.hero_base_hprs: dict[str, tuple[float, float, float]] = {}
        self.hero_emissives: list[NodePath] = []
        self.hero_trails: list[NodePath] = []

        self.ghost_nodes: list[NodePath] = []
        self.dynamic_signs: list[NodePath] = []
        self.power_fx: list[dict] = []
        self.projectiles: list[dict] = []
        self.outer_chunks: dict[tuple[int, int], NodePath] = {}
        self.stream_timer = 0.0
        self.current_stream_chunk: tuple[int, int] | None = None
        self.traffic_cars: list[dict] = []
        self.traffic_guides: list[NodePath] = []
        self.traffic_route_len = 560.0
        self.structure_targets: list[dict] = []
        self.hero_hit_parts: list[dict] = []

        self.seed = random.randint(1, 999999)
        self.hero_pos = Vec3(0, -145, 26)
        self.hero_velocity = Vec3(0, 0, 0)
        self.hero_heading = 0.0
        self.hero_pitch = 0.0
        self.hero_roll = 0.0
        self.control_yaw = 0.0
        self.control_pitch = -10.0
        self.cam_yaw = 0.0
        self.cam_pitch = -12.0
        self.cam_distance = float(self.settings_data.get("default_camera_distance", 24.5))
        self.target_cam_distance = float(self.settings_data.get("default_camera_distance", 24.5))

        self.boost_timer = 0.0
        self.brake_timer = 0.0
        self.attack_timer = 0.0
        self.attack_cooldown = 0.0
        self.attack_variant = "idle"
        self.burst_cooldowns = {key: 0.0 for key in ("w", "a", "s", "d", "q", "e", "space", "f", "1", "2", "3")}
        self.last_power_text = "None"
        self.power_profile: dict[str, object] = {}
        self.attack_charge = 0.0
        self.attack_charging = False
        self.charge_fx_timer = 0.0
        self.attack_hold_origin = "visor"
        self.shield_timer = 0.0
        self.shield_cooldown = 0.0
        self.shield_radius = 6.5
        self.shield_charging = False
        self.shield_hold = 0.0
        self.shield_release_radius = 6.5
        self.xray_timer = 0.0
        self.xray_cooldown = 0.0
        self.support_timer = 0.0
        self.support_cooldown = 0.0
        self.support_fx_tick = 0.0
        self.hero_xray_shell = None
        self.look_turn_strength = 0.0
        self.mouse_turn_delta = 0.0
        self.last_power_use_pos = Vec3(0, 0, 0)
        self.last_power_use_team = "neutral"
        self.last_power_use_timer = 0.0
        self.police_alert_team = "neutral"
        self.police_alert_timer = 0.0
        self.police_drones: list[dict] = []
        self.emote_cycle = ["none", "salute", "wave", "point", "taunt", "crossed", "meditate", "victory"]
        self.player_emote_index = 0
        self.player_emote_name = "none"
        self.player_emote_strength = 0.0
        self.shadow_fx: list[dict] = []
        self.shadow_spawn_timer = 0.0
        self.player_hp = 100.0
        self.player_max_hp = 100.0
        self.launcher_alert_team = "neutral"
        self.launcher_alert_timer = 0.0
        self.ground_launchers: list[dict] = []
        self.portal_origin = Vec3(0.0, 80.0, 760.0)
        self.portal_clouds: list[dict] = []
        self.boss_spawn_timer = 0.18 if _preview else self.boss_respawn_delay
        self.boss_cleanup_timer = 0.0
        self.boss: dict | None = None
        self.boss_beam: dict | None = None
        self.locked_target: dict | None = None
        self.target_lock_range = 240.0
        self.npc_root = self.render.attachNewNode("npc_root")
        self.npcs: list[dict] = []
        self.next_npc_index = 0
        self.chunk_team_map: dict[tuple[int, int], list[int]] = {}
        self.wild_team_serial = 0
        self.actor_last_hit = "None"
        self.combat_active = False
        self.hostile_teams = set()
        self.team_variant_cache: dict[str, dict] = {}

        self.world_time = 0.0
        self.day_cycle_seconds = 1800.0
        self.weather_schedule_cycle = -1
        self.weather_events: dict[str, dict] = {}
        self.active_weather = "clear"
        self.weather_intensity = 0.0
        self.weather_wind_strength = 0.0
        self.weather_cards: list[NodePath] = []
        self.lightning_timer = 8.0
        self.lightning_flash = 0.0
        self.eclipse_intensity = 0.0
        self.time_label = "Dawn"

        self.create_lighting()
        self.create_fog()
        self.create_overlay()
        self.create_sky()
        self.init_audio_assets()
        self.init_model_pool()
        self.create_hud()
        self.save_settings()
        self.make_ground_plane()
        self.create_surface_water()
        self.build_city(self.seed)
        self.create_traffic_system()
        self.create_police_drones()
        self.create_ground_launchers()
        self.create_hero()
        self.create_npcs()
        self.randomize_power_profile(initial=True)
        if EXPORT_CHARACTERS_ON_LAUNCH or not FAST_CORE_STARTUP:
            self.export_character_models_assets()
        else:
            print("Fast Core startup: skipped character .bam export. Set HOLOVERSE_EXPORT_CHARACTERS_ON_LAUNCH=1 to regenerate.")
        self.reset_hero()
        self.taskMgr.add(self.update, "update")

        if _preview:
            self.taskMgr.doMethodLater(1.2, self.capture_preview, "capture_preview")

    def on_key_down(self, key: str) -> None:
        self.keys.add(key)
        if "shift" in self.keys and key != "shift":
            self.use_power(key)

    def on_key_up(self, key: str) -> None:
        self.keys.discard(key)

    def init_audio_assets(self) -> None:
        self.sfx: dict[str, object] = {}
        for path in sorted(POWER_SFX_DIR.glob("*.wav")):
            try:
                self.sfx[path.stem] = self.loader.loadSfx(panda_path(path))
            except Exception:
                pass

    def play_sfx(self, name: str, volume: float = 0.7, rate: float = 1.0) -> None:
        snd = getattr(self, "sfx", {}).get(name)
        if snd is None:
            return
        try:
            snd.stop()
        except Exception:
            pass
        try:
            snd.setVolume(max(0.0, min(1.0, volume)))
        except Exception:
            pass
        try:
            snd.setPlayRate(rate)
        except Exception:
            pass
        try:
            snd.play()
        except Exception:
            pass


    def xray_color_for_team(self, team_name: str) -> tuple[float, float, float, float]:
        if team_name == "ally":
            return (0.22, 1.0, 0.30, 0.76)
        if team_name in self.hostile_teams:
            return (1.0, 0.16, 0.16, 0.76)
        return (1.0, 1.0, 1.0, 0.72)

    def create_actor_aura_shell(self, parent: NodePath, visual: NodePath) -> NodePath:
        shell = visual.copyTo(parent)
        shell.setLightOff(True)
        shell.setShaderOff(True)
        shell.setTextureOff(1)
        shell.setTransparency(TransparencyAttrib.M_alpha)
        shell.setDepthWrite(False)
        shell.setDepthTest(False)
        shell.setBin("transparent", 24)
        shell.setColorScale(0.3, 0.9, 1.0, 0.0)
        shell.hide()
        return shell

    def create_xray_shell(self, parent: NodePath, visual: NodePath) -> NodePath:
        shell = visual.copyTo(parent)
        shell.setLightOff(True)
        shell.setShaderOff(True)
        shell.setTextureOff(1)
        shell.setTransparency(TransparencyAttrib.M_alpha)
        shell.setDepthWrite(False)
        shell.setDepthTest(False)
        shell.setBin("fixed", 70)
        shell.setRenderModeWireframe()
        try:
            shell.setRenderModeThickness(2.6)
        except Exception:
            pass
        shell.hide()
        return shell

    def activate_xray(self) -> None:
        if self.xray_timer > 0.0 or self.xray_cooldown > 0.0:
            return
        self.xray_timer = 10.0
        self.xray_cooldown = 15.0
        self.last_power_text = "X-Ray engaged"
        self.mark_power_activity("ally", self.hero_pos + Vec3(0,0,1.3))
        self.play_sfx("special_three", volume=0.62, rate=0.92)
        self.refresh_hud()

    def activate_actor_support(self, actor: dict | None, support_fx: str, is_player: bool = False) -> None:
        support_fx = str(support_fx or "none")
        if support_fx == "none":
            return
        if is_player:
            if self.support_cooldown > 0.0:
                return
            self.support_timer = 5.0
            self.support_cooldown = 9.0
            self.support_fx_tick = 0.0
            self.last_power_text = f"{support_fx.title()} support active"
            self.mark_power_activity("ally", self.hero_pos + Vec3(0,0,1.3))
            sfx_map = {"cloak": "move_blink", "torch": "mode_fireball", "frost": "mode_pulse", "lightning": "mode_beam"}
            self.play_sfx(sfx_map.get(support_fx, "special_two"), volume=0.58, rate=0.94 + random.random() * 0.14)
            return

        if actor is None:
            return
        if actor.get("support_cooldown", 0.0) > 0.0:
            return
        actor["support_timer"] = 4.0
        actor["support_cooldown"] = 8.0 + random.random() * 2.0
        actor["support_fx_tick"] = 0.0
        actor["support_fx"] = support_fx

    def apply_support_visuals(self, visual: NodePath, cape_geos: list[NodePath], support_fx: str, timer: float, is_player: bool = False) -> None:
        if support_fx == "cloak" and timer > 0.0:
            alpha = 0.22 + 0.06 * math.sin(globalClock.getFrameTime() * 8.0)
            visual.setTransparency(TransparencyAttrib.M_alpha)
            visual.setAlphaScale(alpha)
            for node in cape_geos:
                node.setAlphaScale(max(0.10, alpha * 0.7))
        else:
            visual.setTransparency(TransparencyAttrib.M_alpha)
            visual.setAlphaScale(1.0)
            for node in cape_geos:
                node.setAlphaScale(1.0)

    def update_support_effects(self, dt: float) -> None:
        self.support_timer = max(0.0, self.support_timer - dt)
        self.support_cooldown = max(0.0, self.support_cooldown - dt)
        self.support_fx_tick = max(0.0, self.support_fx_tick - dt)

        player_support = str(self.power_profile.get("support_fx", "none"))
        self.apply_support_visuals(self.hero_visual, getattr(self, "hero_cape_geos", []), player_support, self.support_timer, is_player=True)
        if self.support_timer > 0.0:
            self.support_fx_tick -= dt
            if self.support_fx_tick <= 0.0:
                color = self.power_profile.get("secondary", (1, 1, 1, 1))
                pos = self.hero_pos + Vec3(0, 0, 1.4)
                if player_support == "torch":
                    self.spawn_power_fx("burst", pos + Vec3(random.uniform(-0.8, 0.8), random.uniform(-0.8, 0.8), random.uniform(-0.4, 0.8)), (1.0, 0.42, 0.16, 0.84), 0.24)
                    self.support_fx_tick = 0.10
                elif player_support == "frost":
                    self.spawn_power_fx("scan", pos, (0.62, 0.90, 1.0, 0.68), 0.28)
                    self.support_fx_tick = 0.18
                elif player_support == "lightning":
                    self.spawn_power_fx("slash", pos + Vec3(random.uniform(-0.6, 0.6), random.uniform(-0.6, 0.6), random.uniform(-0.4, 0.8)), (0.88, 0.96, 1.0, 0.82), 0.22)
                    self.support_fx_tick = 0.12
                elif player_support == "cloak":
                    self.spawn_power_fx("blink", pos, (0.70, 0.90, 1.0, 0.22), 0.16)
                    self.support_fx_tick = 0.28

        for npc in self.npcs:
            npc["support_timer"] = max(0.0, npc.get("support_timer", 0.0) - dt)
            npc["support_cooldown"] = max(0.0, npc.get("support_cooldown", 0.0) - dt)
            npc["support_fx_tick"] = max(0.0, npc.get("support_fx_tick", 0.0) - dt)
            support_fx = str(npc.get("support_fx", npc["profile"].get("support_fx", "none")))
            self.apply_support_visuals(npc["visual"], npc.get("cape_geos", []), support_fx, npc.get("support_timer", 0.0), is_player=False)

            if npc.get("support_timer", 0.0) > 0.0 and npc["support_fx_tick"] <= 0.0:
                pos = npc["pos"] + Vec3(0, 0, 1.28 * npc["profile"]["scale"])
                if support_fx == "torch":
                    self.spawn_power_fx("burst", pos + Vec3(random.uniform(-0.7, 0.7), random.uniform(-0.7, 0.7), random.uniform(-0.4, 0.8)), (1.0, 0.34, 0.12, 0.68), 0.20)
                    npc["support_fx_tick"] = 0.14
                elif support_fx == "frost":
                    self.spawn_power_fx("scan", pos, (0.62, 0.90, 1.0, 0.58), 0.24)
                    npc["support_fx_tick"] = 0.22
                elif support_fx == "lightning":
                    self.spawn_power_fx("slash", pos + Vec3(random.uniform(-0.6, 0.6), random.uniform(-0.6, 0.6), random.uniform(-0.4, 0.8)), (0.92, 0.96, 1.0, 0.70), 0.18)
                    npc["support_fx_tick"] = 0.15
                elif support_fx == "cloak":
                    self.spawn_power_fx("blink", pos, (0.76, 0.90, 1.0, 0.18), 0.14)
                    npc["support_fx_tick"] = 0.34

    def update_xray_visuals(self, dt: float) -> None:
        self.xray_timer = max(0.0, self.xray_timer - dt)
        self.xray_cooldown = max(0.0, self.xray_cooldown - dt)
        active = self.xray_timer > 0.0

        if self.hero_xray_shell is not None:
            if active:
                self.hero_xray_shell.show()
                self.hero_xray_shell.setColorScale(*self.xray_color_for_team("ally"))
            else:
                self.hero_xray_shell.hide()

        for npc in self.npcs:
            shell = npc.get("xray_shell")
            if shell is None:
                continue
            if active:
                shell.show()
                shell.setColorScale(*self.xray_color_for_team(str(npc.get("team", "neutral"))))
            else:
                shell.hide()

    def cycle_player_emote(self) -> None:
        self.player_emote_index = (self.player_emote_index + 1) % len(self.emote_cycle)
        self.player_emote_name = self.emote_cycle[self.player_emote_index]
        self.player_emote_strength = 1.0 if self.player_emote_name != "none" else 0.0
        self.last_power_text = f"Emote: {self.player_emote_name}"
        self.play_sfx("special_one", volume=0.34, rate=0.92 + self.player_emote_index * 0.03)

    def init_model_pool(self) -> None:
        self.model_pool_dir = ASSETS_DIR / "models"
        self.model_pool_dir.mkdir(parents=True, exist_ok=True)
        self.external_model_paths = []
        self.external_model_cache = {}
        supported = {".bam", ".egg", ".gltf", ".glb", ".obj"}
        for path in sorted(self.model_pool_dir.rglob("*")):
            if path.is_file() and path.suffix.lower() in supported:
                self.external_model_paths.append(path)
        print("Model pool scan:")
        if self.external_model_paths:
            for path in self.external_model_paths:
                try:
                    rel = path.relative_to(ROOT)
                except Exception:
                    rel = path
                print(f"  - {rel}")
        else:
            print("  - no compatible models found in assets/models")

    def get_external_model_proto(self, path: Path):
        key = str(path)
        if key in self.external_model_cache:
            return self.external_model_cache[key]
        try:
            model = self.loader.loadModel(panda_path(path))
            if model is None or model.isEmpty():
                self.external_model_cache[key] = None
                return None
            model.clearModelNodes()
            self.external_model_cache[key] = model
            return model
        except Exception:
            self.external_model_cache[key] = None
            return None

    def sanitize_export_name(self, value: str) -> str:
        cleaned = "".join(ch.lower() if ch.isalnum() else "_" for ch in value)
        while "__" in cleaned:
            cleaned = cleaned.replace("__", "_")
        return cleaned.strip("_") or "character"

    def export_character_models_assets(self) -> None:
        export_dir = CHAR_EXPORT_DIR
        export_dir.mkdir(parents=True, exist_ok=True)
        for old_path in export_dir.glob("*.bam"):
            try:
                old_path.unlink()
            except Exception:
                pass

        records: list[dict[str, object]] = []
        samples: list[tuple[str, NodePath, dict]] = []

        if getattr(self, "hero_visual", None) is not None and self.hero_visual is not None and not self.hero_visual.isEmpty():
            samples.append(("player_current", self.hero_visual, dict(self.power_profile)))
        base_root = NodePath("base_character_export")
        base_visual = build_sheet_style_hero(base_root)
        samples.append(("procedural_base", base_visual, {"name": "Procedural Base", "family": "base"}))

        for idx, npc in enumerate(self.npcs):
            source = npc.get("visual")
            if source is None or source.isEmpty():
                continue
            label = f"{npc.get('team', 'team')}_{idx:02d}_{npc['profile'].get('family', 'variant')}"
            samples.append((label, source, dict(npc["profile"])))

        exported = 0
        for label, source, profile in samples:
            if source is None or source.isEmpty():
                continue
            name = self.sanitize_export_name(label)
            path = export_dir / f"{name}.bam"
            wrapper = NodePath(name)
            model = source.copyTo(wrapper)
            model.setPos(0, 0, 0)
            model.setHpr(0, 0, 0)
            model.setScale(1)
            try:
                wrapper.writeBamFile(panda_path(path))
                exported += 1
                records.append({
                    "file": path.name,
                    "label": label,
                    "name": profile.get("name", label),
                    "team": profile.get("team", "sample"),
                    "family": profile.get("family", "base"),
                    "helmet": profile.get("helmet", "none"),
                    "wing_style": profile.get("wing_style", "none"),
                    "tail_style": profile.get("tail_style", "none"),
                    "suit_style": profile.get("suit_style", "procedural"),
                })
            except Exception:
                pass
            finally:
                wrapper.removeNode()

        try:
            base_root.removeNode()
        except Exception:
            pass

        readme = export_dir / "README.txt"
        readme.write_text(
            "Procedural Anti-Heroes character exports\n"
            "These .bam files are generated from the current player and NPC variant pool.\n"
            "Edit these as reference character models and silhouettes.\n"
            "profiles.json lists the procedural profile used for each export.\n",
            encoding="utf-8",
        )
        (export_dir / "profiles.json").write_text(json.dumps(records, indent=2), encoding="utf-8")
        print(f"Exported {exported} character models to {export_dir}")

    def spawn_external_model_prop(self, parent, pos: Vec3, rnd: random.Random, zone: str = "outskirts") -> bool:
        if not getattr(self, "external_model_paths", None):
            return False
        path = rnd.choice(self.external_model_paths)
        proto = self.get_external_model_proto(path)
        if proto is None:
            return False
        node = proto.copyTo(parent)
        node.setPos(pos)
        node.setHpr(rnd.uniform(0.0, 360.0), 0.0, 0.0)
        node.setScale(rnd.uniform(1.4, 5.0) if zone == "outskirts" else rnd.uniform(1.0, 3.0))
        node.flattenLight()
        bounds = node.getTightBounds()
        if bounds is not None and bounds[0] is not None and bounds[1] is not None:
            min_pt, max_pt = bounds
            size = max_pt - min_pt
            if size.lengthSquared() > 0.0001:
                self.register_box_target(node, max(1.0, abs(size.x)), max(1.0, abs(size.y)), max(1.0, abs(size.z)), zone, "external_model")
        return True

    def maybe_trigger_npc_emote(self, npc: dict) -> None:
        if npc.get("emote_timer", 0.0) > 0.0 or npc.get("emote_cooldown", 0.0) > 0.0:
            return
        if npc.get("state") not in ("neutral", "escort"):
            return
        if npc.get("attack_timer", 0.0) > 0.0 or npc.get("shield_timer", 0.0) > 0.0:
            return
        npc["emote_name"] = random.choice(["salute", "wave", "point", "taunt", "crossed", "victory"])
        npc["emote_timer"] = random.uniform(1.8, 3.8)
        npc["emote_strength"] = 1.0
        npc["emote_cooldown"] = random.uniform(4.5, 10.0)

    def mark_power_activity(self, team_name: str, pos: Vec3) -> None:
        if team_name == "police":
            return
        self.last_power_use_team = str(team_name)
        self.last_power_use_pos = Vec3(pos)
        self.last_power_use_timer = 1.2
        self.launcher_alert_team = str(team_name)
        self.launcher_alert_timer = 12.0

    def create_propulsion_rig(self, parent: NodePath, parts: dict[str, NodePath], scale: float, primary, secondary, style: str = "jetpack") -> dict:
        rig = {"style": style, "glows": [], "meshes": [], "trails": [], "primary": primary, "secondary": secondary}
        trail_tex = self.texture_factory.make_trail(f"propulsion_trail_{style}", 9800 + (1 if style == "jetpack" else 2))

        def add_box(name, target, pos, scale_xyz, color, glow=False):
            node = _SMOOTH_FACTORY.box(name, scale_xyz[0], scale_xyz[1], scale_xyz[2])
            node.reparentTo(target)
            node.setPos(*pos)
            node.setColorScale(*color)
            if glow:
                node.setLightOff(True)
                node.setTransparency(TransparencyAttrib.M_alpha)
                node.setDepthWrite(False)
                node.setBin("transparent", 30)
                rig["glows"].append(node)
            else:
                rig["meshes"].append(node)
            return node

        def add_trail(name, target, pos, hpr, scale_xyz, color_slot: str, role: str):
            for layer, widen, alpha_mul in (("halo", 1.45, 0.58), ("core", 1.0, 1.0)):
                node = _SMOOTH_FACTORY.ribbon(f"{name}_{layer}", 0.11, 0.62)
                node.reparentTo(target)
                node.setPos(*pos)
                node.setHpr(*hpr)
                node.setScale(scale_xyz[0] * widen, scale_xyz[1] * (1.18 if layer == "halo" else 1.0), scale_xyz[2] * widen)
                node.setTexture(trail_tex, 1)
                node.setTwoSided(True)
                node.setLightOff(True)
                node.setTransparency(TransparencyAttrib.M_alpha)
                node.setDepthWrite(False)
                node.setBin("transparent", 26 if layer == "halo" else 29)
                node.setColorScale(1.0, 1.0, 1.0, 0.0)
                rig["trails"].append({
                    "node": node,
                    "base_scale": Vec3(scale_xyz[0] * widen, scale_xyz[1] * (1.18 if layer == "halo" else 1.0), scale_xyz[2] * widen),
                    "color_slot": color_slot,
                    "role": role,
                    "layer": layer,
                    "alpha_mul": alpha_mul,
                    "phase": random.random() * math.tau,
                })
            return rig["trails"][-1]

        dark = (0.12, 0.12, 0.14, 1.0)
        if style == "jetpack":
            for sx in (-1, 1):
                add_box(f"pack_{sx}", parent, (0.12 * sx, -0.20, 1.30 * scale), (0.10 * scale, 0.16 * scale, 0.36 * scale), dark)
                add_box(f"pack_nozzle_{sx}", parent, (0.12 * sx, -0.29, 1.10 * scale), (0.06 * scale, 0.08 * scale, 0.08 * scale), primary, True)
                add_box(f"pack_fin_{sx}", parent, (0.18 * sx, -0.16, 1.28 * scale), (0.04 * scale, 0.12 * scale, 0.22 * scale), (0.18, 0.18, 0.22, 1.0))
                add_trail(f"pack_trail_{sx}", parent, (0.12 * sx, -0.38, 1.10 * scale), (90, 0, 0), (0.20 * scale, 1.25 * scale, 0.20 * scale), "primary", "pack")
        for key in ("hand_l", "hand_r", "foot_l", "foot_r"):
            part = parts.get(key)
            if part is None:
                continue
            hand_like = "hand" in key
            offset = (0.0, -0.06, -0.02) if hand_like else (0.0, -0.04, -0.03)
            add_box(f"thruster_{key}", part, offset, (0.05 * scale, 0.09 * scale, 0.10 * scale), (0.18, 0.18, 0.22, 1.0))
            add_box(f"thruster_glow_{key}", part, (offset[0], offset[1] - 0.03 * scale, offset[2]), (0.035 * scale, 0.05 * scale, 0.08 * scale), secondary, True)
            trail_scale = (0.12 * scale, 0.78 * scale, 0.16 * scale) if hand_like else (0.14 * scale, 0.92 * scale, 0.18 * scale)
            add_trail(f"{key}_trail", part, (offset[0], offset[1] - 0.08 * scale, offset[2]), (90, 0, 0), trail_scale, "secondary", "hand" if hand_like else "foot")
        self.set_propulsion_colors(rig, primary, secondary)
        return rig

    def set_propulsion_colors(self, rig: dict | None, primary, secondary) -> None:
        if not rig:
            return
        rig["primary"] = primary
        rig["secondary"] = secondary
        for i, glow in enumerate(rig.get("glows", [])):
            color = primary if i % 2 == 0 else secondary
            glow.setColorScale(color[0] * 1.5, color[1] * 1.5, color[2] * 1.5, 0.55)
        for item in rig.get("trails", []):
            color = primary if item.get("color_slot") == "primary" else secondary
            if item.get("layer") == "halo":
                color = (
                    min(1.0, color[0] * 0.85 + 0.15),
                    min(1.0, color[1] * 0.85 + 0.15),
                    min(1.0, color[2] * 0.85 + 0.15),
                    1.0,
                )
            item["color"] = color
            item["node"].setColorScale(color[0] * 1.35, color[1] * 1.35, color[2] * 1.35, 0.0)

    def update_propulsion_rig(self, rig: dict | None, speed: float, boost: float, active: bool = True) -> None:
        if not rig:
            return
        intensity = clamp(speed / 78.0 + boost * 0.95, 0.0, 1.9) if active else 0.0
        t = globalClock.getFrameTime()
        for i, glow in enumerate(rig.get("glows", [])):
            base = 0.06 + intensity * 0.32
            pulse = 0.78 + 0.22 * math.sin(t * (10.0 + i * 0.9))
            c = glow.getColorScale()
            glow.setScale(1.0 + intensity * 0.14, 1.0 + intensity * 0.55, 1.0 + intensity * 0.30)
            glow.setColorScale(c.x, c.y, c.z, base * pulse)

        role_gain = {"pack": 1.25, "hand": 0.92, "foot": 1.05}
        for item in rig.get("trails", []):
            node = item["node"]
            base_scale = item["base_scale"]
            layer = item["layer"]
            role = item["role"]
            gain = role_gain.get(role, 1.0)
            flame = 0.82 + 0.18 * math.sin(t * (14.0 + gain * 2.0) + item["phase"])
            stretch = 0.55 + intensity * (1.7 if role == "pack" else 1.25) * gain
            width = 0.88 + intensity * (0.32 if layer == "halo" else 0.18)
            depth = 0.92 + intensity * 0.16
            node.setScale(base_scale.x * width, base_scale.y * stretch, base_scale.z * depth)
            color = item.get("color", rig.get("primary", (1, 1, 1, 1)))
            alpha = (0.08 + intensity * (0.16 if layer == "halo" else 0.28)) * item["alpha_mul"] * flame
            node.setColorScale(color[0] * 1.35, color[1] * 1.35, color[2] * 1.35, alpha)
            try:
                node.setTexOffset(0.0, -((t * (0.55 + gain * 0.18)) + item["phase"] * 0.05) % 1.0)
            except Exception:
                pass

    def create_police_drones(self) -> None:
        if not self.police_root.isEmpty():
            self.police_root.removeNode()
        self.police_root = self.render.attachNewNode("police_root")
        self.police_drones = []
        radius = self.city_world_radius * 0.62
        for i in range(5):
            root = self.police_root.attachNewNode(f"police_drone_{i}")
            body = _SMOOTH_FACTORY.uv_sphere(f"police_body_{i}", 0.55, 18, 12)
            body.reparentTo(root)
            body.setColorScale(0.16, 0.18, 0.22, 1.0)
            eye = _SMOOTH_FACTORY.box(f"police_eye_{i}", 0.22, 0.06, 0.10)
            eye.reparentTo(root)
            eye.setPos(0, 0.48, 0.02)
            eye.setLightOff(True)
            eye.setColorScale(0.30, 0.70, 1.0, 0.9)
            ring = _SMOOTH_FACTORY.cylinder(f"police_ring_{i}", 0.82, 0.04, 22)
            ring.reparentTo(root)
            ring.setHpr(0, 90, 0)
            ring.setColorScale(0.24, 0.82, 1.0, 0.4)
            ring.setLightOff(True)
            ring.setTransparency(TransparencyAttrib.M_alpha)
            ang = (i / 5.0) * math.tau
            pos = Vec3(math.cos(ang) * radius, math.sin(ang) * radius, 42.0 + i * 6.0)
            root.setPos(pos)
            root.setH(math.degrees(ang) + 180.0)
            self.police_drones.append({"root": root, "eye": eye, "ring": ring, "angle": ang, "radius": radius + i * 18.0, "alt": 42.0 + i * 6.0, "fire_cooldown": i * 0.2})

    def update_police_drones(self, dt: float) -> None:
        self.last_power_use_timer = max(0.0, self.last_power_use_timer - dt)
        self.police_alert_timer = max(0.0, self.police_alert_timer - dt)
        if self.police_alert_timer <= 0.0:
            self.police_alert_team = "neutral"
        t = globalClock.getFrameTime()

        if self.last_power_use_timer > 0.0 and self.last_power_use_team != "neutral":
            for drone in self.police_drones:
                dpos = drone["root"].getPos()
                delta = self.last_power_use_pos - dpos
                dist = delta.length()
                if dist < 130.0:
                    forward = self.forward_from_angles(drone["root"].getH(), 0.0)
                    if dist < 1e-3 or delta.normalized().dot(forward) > -0.1:
                        self.police_alert_team = self.last_power_use_team
                        self.police_alert_timer = 14.0
                        break

        for i, drone in enumerate(self.police_drones):
            root = drone["root"]
            drone["fire_cooldown"] = max(0.0, drone["fire_cooldown"] - dt)
            if self.police_alert_timer > 0.0 and self.police_alert_team != "neutral":
                target_pos = None
                if self.police_alert_team == "ally":
                    target_pos = self.hero_pos + Vec3(0, 0, 1.2)
                    ally_targets = [npc for npc in self.npcs if str(npc.get("team")) == "ally"]
                    best = self.choose_closest_npc(root.getPos(), ally_targets)
                    if best is not None and (best["pos"] - root.getPos()).lengthSquared() < (target_pos - root.getPos()).lengthSquared():
                        target_pos = best["pos"] + Vec3(0, 0, 1.2)
                else:
                    matches = [npc for npc in self.npcs if str(npc.get("team")) == self.police_alert_team]
                    best = self.choose_closest_npc(root.getPos(), matches)
                    if best is not None:
                        target_pos = best["pos"] + Vec3(0, 0, 1.2)
                if target_pos is not None:
                    vec = target_pos - root.getPos()
                    dist = max(1.0, vec.length())
                    vec.normalize()
                    desired = target_pos - vec * 26.0 + Vec3(0, 0, 12.0)
                    root.setPos(root.getPos() + (desired - root.getPos()) * clamp(dt * 1.8, 0.0, 1.0))
                    root.lookAt(target_pos)
                    if dist < 165.0 and drone["fire_cooldown"] <= 0.0:
                        muzzle = root.getPos() + self.forward_from_angles(root.getH(), 0.0) * 0.9
                        self.spawn_projectile(muzzle, vec, 138.0, False, kind_override="beam", color_override=(0.30, 0.70, 1.0, 1.0), scale_mul=0.72, life_mul=1.0, owner="police", owner_heading=root.getH())
                        self.spawn_power_fx("beam", muzzle, (0.30, 0.70, 1.0, 0.8), 0.26)
                        drone["fire_cooldown"] = 0.9 + i * 0.08
                else:
                    drone["angle"] += dt * (0.24 + i * 0.03)
            else:
                drone["angle"] += dt * (0.16 + i * 0.03)
                patrol = Vec3(math.cos(drone["angle"]) * drone["radius"], math.sin(drone["angle"]) * drone["radius"], drone["alt"] + math.sin(t * 0.8 + i) * 4.0)
                root.setPos(root.getPos() + (patrol - root.getPos()) * clamp(dt * 1.4, 0.0, 1.0))
                root.lookAt(self.hero_pos.x, self.hero_pos.y, root.getZ())

            pulse = 0.55 + 0.45 * math.sin(t * 6.0 + i)
            if self.police_alert_timer > 0.0:
                drone["eye"].setColorScale(1.0, 0.22 + pulse * 0.25, 0.20 + pulse * 0.25, 0.92)
                drone["ring"].setColorScale(1.0, 0.25, 0.22, 0.34 + pulse * 0.18)
            else:
                drone["eye"].setColorScale(0.30, 0.70 + pulse * 0.12, 1.0, 0.88)
                drone["ring"].setColorScale(0.24, 0.82, 1.0, 0.24 + pulse * 0.10)

    def create_lighting(self) -> None:
        self.amb_light = AmbientLight("amb")
        self.amb_light.setColor(Vec4(0.46, 0.48, 0.52, 1.0))
        self.amb_np = self.render.attachNewNode(self.amb_light)
        self.render.setLight(self.amb_np)

        self.sun_light = DirectionalLight("sun")
        self.sun_light.setColor(Vec4(1.08, 1.04, 0.96, 1.0))
        self.sun_np = self.render.attachNewNode(self.sun_light)
        self.sun_np.setHpr(-20, -28, 0)
        self.render.setLight(self.sun_np)

        self.rim_light = DirectionalLight("rim")
        self.rim_light.setColor(Vec4(0.42, 0.46, 0.52, 1.0))
        self.rim_np = self.render.attachNewNode(self.rim_light)
        self.rim_np.setHpr(128, -8, 0)
        self.render.setLight(self.rim_np)

        self.hero_fill = DirectionalLight("hero_fill")
        self.hero_fill.setColor(Vec4(0.18, 0.70, 0.28, 1.0))
        self.hero_fill_np = self.render.attachNewNode(self.hero_fill)
        self.hero_fill_np.setHpr(25, -4, 0)
        self.render.setLight(self.hero_fill_np)

    def create_fog(self) -> None:
        self.world_fog = Fog("city_fog")
        self.world_fog.setColor(0.72, 0.62, 0.48)
        self.world_fog.setLinearRange(42, 320)
        self.render.setFog(self.world_fog)

    def create_overlay(self) -> None:
        cm = CardMaker("overlay")
        cm.setFrameFullscreenQuad()
        self.overlay = self.render2d.attachNewNode(cm.generate())
        self.overlay.setTransparency(TransparencyAttrib.M_alpha)
        self.overlay.setBin("fixed", 100)
        self.overlay.setDepthTest(False)
        self.overlay.setDepthWrite(False)
        self.overlay.setTexture(self.texture_factory.make_overlay("overlay", 1001))
        self.overlay.setColorScale(1, 1, 1, 0.72)

    def create_sky(self) -> None:
        sun_cm = CardMaker("red_sun")
        sun_cm.setFrame(-140, 140, -140, 140)
        self.sun_node = self.render.attachNewNode(sun_cm.generate())
        self.sun_node.setTexture(self.texture_factory.make_sun("red_sun", 9081))
        self.sun_node.setTransparency(TransparencyAttrib.M_alpha)
        self.sun_node.setDepthWrite(False)
        self.sun_node.setBin("background", 0)
        self.sun_node.setLightOff(True)
        self.sun_node.setBillboardPointEye()
        self.sun_node.setColorScale(1.0, 0.52, 0.46, 0.96)

        halo_cm = CardMaker("red_sun_halo")
        halo_cm.setFrame(-280, 280, -280, 280)
        self.sun_halo = self.render.attachNewNode(halo_cm.generate())
        self.sun_halo.setTexture(self.texture_factory.make_sun("red_sun_halo", 9082))
        self.sun_halo.setTransparency(TransparencyAttrib.M_alpha)
        self.sun_halo.setDepthWrite(False)
        self.sun_halo.setBin("background", -1)
        self.sun_halo.setLightOff(True)
        self.sun_halo.setBillboardPointEye()
        self.sun_halo.setColorScale(1.0, 0.28, 0.22, 0.22)

        eclipse_cm = CardMaker("eclipse_disc")
        eclipse_cm.setFrame(-110, 110, -110, 110)
        self.eclipse_node = self.render.attachNewNode(eclipse_cm.generate())
        self.eclipse_node.setTexture(self.texture_factory.make_overlay("eclipse_disc", 9083))
        self.eclipse_node.setTransparency(TransparencyAttrib.M_alpha)
        self.eclipse_node.setDepthWrite(False)
        self.eclipse_node.setBin("background", 1)
        self.eclipse_node.setLightOff(True)
        self.eclipse_node.setBillboardPointEye()
        self.eclipse_node.hide()

        weather_tex = self.texture_factory.make_glitch("weather_card", 9090)
        dust_tex = self.texture_factory.make_glitch("dust_card", 9091)
        self.weather_cards = []
        for i in range(12):
            cm = CardMaker(f"weather_card_{i}")
            cm.setFrame(-1.0, 1.0, -2.6, 2.6)
            node = self.render.attachNewNode(cm.generate())
            node.setBillboardPointEye()
            node.setTransparency(TransparencyAttrib.M_alpha)
            node.setDepthWrite(False)
            node.setBin("transparent", 8)
            node.setLightOff(True)
            node.setTexture(weather_tex if i % 2 == 0 else dust_tex)
            node.hide()
            self.weather_cards.append(node)

        overlay_cm = CardMaker("storm_overlay")
        overlay_cm.setFrameFullscreenQuad()
        self.storm_overlay = self.render2d.attachNewNode(overlay_cm.generate())
        self.storm_overlay.setTexture(self.texture_factory.make_overlay("storm_overlay", 9092))
        self.storm_overlay.setTransparency(TransparencyAttrib.M_alpha)
        self.storm_overlay.setBin("fixed", 101)
        self.storm_overlay.setDepthTest(False)
        self.storm_overlay.setDepthWrite(False)
        self.storm_overlay.setColorScale(0.7, 0.62, 0.50, 0.0)

        portal_tex = self.texture_factory.make_sun("sky_portal_disc", 9191)
        portal_ring_tex = self.texture_factory.make_glitch("sky_portal_ring", 9192)
        portal_cloud_tex = self.texture_factory.make_glitch("sky_portal_clouds", 9193)

        portal_disc_cm = CardMaker("portal_disc")
        portal_disc_cm.setFrame(-1.0, 1.0, -1.0, 1.0)
        self.portal_disc = self.render.attachNewNode(portal_disc_cm.generate())
        self.portal_disc.setTexture(portal_tex)
        self.portal_disc.setTransparency(TransparencyAttrib.M_alpha)
        self.portal_disc.setDepthWrite(False)
        self.portal_disc.setBin("background", 3)
        self.portal_disc.setLightOff(True)
        self.portal_disc.setBillboardPointEye()
        self.portal_disc.setScale(280.0)

        portal_ring_cm = CardMaker("portal_ring")
        portal_ring_cm.setFrame(-1.0, 1.0, -1.0, 1.0)
        self.portal_ring = self.render.attachNewNode(portal_ring_cm.generate())
        self.portal_ring.setTexture(portal_tex)
        self.portal_ring.setTransparency(TransparencyAttrib.M_alpha)
        self.portal_ring.setDepthWrite(False)
        self.portal_ring.setBin("background", 4)
        self.portal_ring.setLightOff(True)
        self.portal_ring.setBillboardPointEye()
        self.portal_ring.setScale(420.0)

        portal_hole_cm = CardMaker("portal_hole")
        portal_hole_cm.setFrame(-1.0, 1.0, -1.0, 1.0)
        self.portal_hole = self.render.attachNewNode(portal_hole_cm.generate())
        self.portal_hole.setTexture(self.texture_factory.make_overlay("portal_hole", 9194))
        self.portal_hole.setTransparency(TransparencyAttrib.M_alpha)
        self.portal_hole.setDepthWrite(False)
        self.portal_hole.setBin("background", 5)
        self.portal_hole.setLightOff(True)
        self.portal_hole.setBillboardPointEye()
        self.portal_hole.setScale(170.0)
        self.portal_hole.setColorScale(0.02, 0.03, 0.04, 0.88)

        self.portal_clouds = []
        cloud_colors = [
            (0.34, 1.0, 0.78, 0.32),
            (1.0, 0.52, 0.86, 0.28),
            (0.54, 0.72, 1.0, 0.28),
            (1.0, 0.76, 0.30, 0.24),
        ]
        for i in range(18):
            cm = CardMaker(f"portal_cloud_{i}")
            cm.setFrame(-1.2, 1.2, -1.1, 1.1)
            node = self.render.attachNewNode(cm.generate())
            node.setTexture(portal_cloud_tex)
            node.setTransparency(TransparencyAttrib.M_alpha)
            node.setDepthWrite(False)
            node.setBin("transparent", 18)
            node.setLightOff(True)
            node.setBillboardPointEye()
            node.setColorScale(*cloud_colors[i % len(cloud_colors)])
            self.portal_clouds.append({
                "node": node,
                "phase": (i / 18.0) * math.tau,
                "radius": 210.0 + (i % 5) * 26.0,
                "z": -34.0 + ((i % 7) - 3) * 16.0,
                "speed": 0.18 + (i % 4) * 0.035,
                "color": cloud_colors[i % len(cloud_colors)],
            })


    def update_portal_and_boss(self, dt: float) -> None:
        time_value = globalClock.getFrameTime()
        anchor = self.portal_origin
        pulse = 0.82 + 0.18 * math.sin(time_value * 0.9)
        self.portal_disc.setPos(anchor)
        self.portal_ring.setPos(anchor + Vec3(0, 0, 2.0))
        self.portal_hole.setPos(anchor + Vec3(0, 0, 4.0))
        self.portal_disc.setColorScale(0.22, 0.92, 1.0, 0.62 + 0.12 * pulse)
        self.portal_ring.setColorScale(1.0, 0.42 + 0.10 * pulse, 0.92, 0.26 + 0.08 * pulse)
        self.portal_hole.setColorScale(0.01, 0.02, 0.03, 0.88)
        self.portal_ring.setR(self.portal_ring.getR() + dt * 14.0)
        self.portal_disc.setR(self.portal_disc.getR() - dt * 6.0)

        for i, cloud in enumerate(self.portal_clouds):
            node = cloud["node"]
            ang = time_value * cloud["speed"] + cloud["phase"]
            radius = cloud["radius"] + math.sin(time_value * 0.8 + cloud["phase"] * 2.0) * 20.0
            node.setPos(
                anchor.x + math.cos(ang) * radius,
                anchor.y + math.sin(ang * 0.92) * radius * 0.82,
                anchor.z + cloud["z"] + math.sin(ang * 2.4 + i) * 26.0,
            )
            node.setScale(38.0 + (i % 4) * 10.0 + math.sin(time_value * 1.8 + i) * 4.0)
            c = cloud["color"]
            node.setColorScale(c[0], c[1], c[2], c[3] * (0.78 + 0.22 * math.sin(time_value * 2.0 + i)))

        if self.boss is None:
            self.boss_spawn_timer = max(0.0, self.boss_spawn_timer - dt)
            if self.boss_spawn_timer <= 0.0:
                self.spawn_boss()
            return

        boss = self.boss
        if not boss.get("alive", False):
            boss["death_timer"] = max(0.0, float(boss.get("death_timer", 2.0)) - dt)
            if boss["death_timer"] <= 0.0:
                try:
                    boss["root"].removeNode()
                except Exception:
                    pass
                self.boss = None
                self.boss_beam = None
                self.locked_target = None
            return

        if str(boss.get("type", "eye")) == "sandworm":
            self.update_sandworm_boss(dt, time_value)
            return

        boss["intro"] = max(0.0, boss.get("intro", 0.0) - dt)
        boss["beam_cooldown"] = max(0.0, boss.get("beam_cooldown", 0.0) - dt)
        bob = math.sin(time_value * 0.46 + boss["phase"]) * 10.0
        sway_x = math.sin(time_value * 0.22 + boss["phase"] * 0.7) * 20.0
        sway_y = math.cos(time_value * 0.18 + boss["phase"] * 0.4) * 14.0
        center_hover = Vec3(sway_x, sway_y, 58.0 + bob)
        portal_hover = anchor + Vec3(sway_x * 0.45, -38.0, -248.0 + bob * 0.55)
        intro_blend = clamp(1.0 - boss["intro"] / 4.2, 0.0, 1.0)
        target_pos = Vec3(
            lerp(portal_hover.x, center_hover.x, intro_blend),
            lerp(portal_hover.y, center_hover.y, intro_blend),
            lerp(portal_hover.z, center_hover.z, intro_blend),
        )
        if boss["intro"] > 0.0:
            target_pos.z += boss["intro"] * 260.0
        current = boss["root"].getPos()
        boss["root"].setPos(current + (target_pos - current) * clamp(dt * 1.8, 0.0, 1.0))
        boss["root"].setHpr(math.sin(time_value * 0.20) * 9.0, math.sin(time_value * 0.28) * 6.0, math.cos(time_value * 0.24) * 8.0)
        boss["iris"].setPos(math.sin(time_value * 0.8) * 0.45, 4.35, math.cos(time_value * 0.7) * 0.38)
        boss["pupil"].setPos(math.sin(time_value * 0.8) * 0.65, 4.70, math.cos(time_value * 0.7) * 0.52)

        for tentacle in boss["tentacles"]:
            for seg in tentacle:
                joint = seg["joint"]
                base_h = seg["base_h"]
                base_p = seg["base_p"]
                phase = seg["phase"]
                strength = seg["strength"]
                joint.setHpr(
                    base_h + math.sin(time_value * 0.55 + phase) * strength * 18.0,
                    base_p + math.cos(time_value * 0.65 + phase) * strength * 14.0,
                    math.sin(time_value * 0.44 + phase * 1.3) * strength * 12.0,
                )

        self.crush_structures_with_boss(dt)

        if boss["beam_cooldown"] <= 0.0 and self.boss_beam is None:
            target = self.choose_boss_target()
            if target is not None:
                self.start_boss_beam(target)
                boss["beam_cooldown"] = 4.8 + random.random() * 2.4

        self.update_boss_beam(dt)


    def spawn_boss(self) -> None:
        if _preview or random.random() < 0.68:
            self.spawn_sandworm_boss()
        else:
            self.spawn_eye_boss()

    def spawn_eye_boss(self) -> None:
        root = self.render.attachNewNode("sky_boss")
        root.setPos(self.portal_origin + Vec3(0, 0, 140.0))
        sclera = _SMOOTH_FACTORY.uv_sphere("boss_sclera", 5.8, 30, 22)
        sclera.reparentTo(root)
        sclera.setTexture(_make_boss_eye_texture(), 1)
        sclera.setColorScale(0.20, 0.03, 0.03, 1.0)
        iris = _SMOOTH_FACTORY.uv_sphere("boss_iris", 1.9, 24, 18)
        iris.reparentTo(root)
        iris.setTexture(_make_boss_iris_texture(), 1)
        iris.setPos(0, 4.35, 0)
        iris.setScale(1.0, 0.30, 1.0)
        iris.setColorScale(1.0, 0.12, 0.08, 1.0)
        iris.setLightOff(True)
        pupil = _SMOOTH_FACTORY.uv_sphere("boss_pupil", 0.90, 20, 14)
        pupil.reparentTo(root)
        pupil.setPos(0, 4.72, 0)
        pupil.setScale(1.0, 0.18, 1.0)
        pupil.setColorScale(0.01, 0.0, 0.0, 1.0)
        rim = _SMOOTH_FACTORY.cylinder("boss_rim", 6.8, 0.28, 30)
        rim.reparentTo(root)
        rim.setHpr(0, 90, 0)
        rim.setColorScale(1.0, 0.08, 0.06, 0.24)
        rim.setLightOff(True)
        rim.setTransparency(TransparencyAttrib.M_alpha)
        tentacles = []
        for i in range(8):
            ang = (i / 8.0) * math.tau
            troot = root.attachNewNode(f"tentacle_root_{i}")
            troot.setPos(math.cos(ang) * 3.8, math.sin(ang) * 2.0 - 2.4, math.sin(ang * 1.2) * 1.8)
            troot.setHpr(math.degrees(ang), -86.0, 0.0)
            chain = []
            parent = troot
            for seg_i in range(5):
                joint = parent.attachNewNode(f"tentacle_joint_{i}_{seg_i}")
                seg = _SMOOTH_FACTORY.cylinder(f"tentacle_seg_{i}_{seg_i}", 0.42 - seg_i * 0.05, 4.0, 16)
                seg.reparentTo(joint)
                seg.setPos(0, 0, -2.0)
                seg.setColorScale(0.08, 0.01, 0.01, 1.0)
                chain.append({"joint": joint, "base_h": 0.0, "base_p": -18.0 - seg_i * 6.0, "phase": ang + seg_i * 0.68 + random.random() * 0.6, "strength": 1.0 - seg_i * 0.12})
                parent = joint
                parent.setPos(0, 0, -3.4)
            tentacles.append(chain)

        self.boss = {"root": root, "iris": iris, "pupil": pupil, "tentacles": tentacles, "hp": 420.0, "alive": True, "phase": random.random() * math.tau, "intro": 3.5, "beam_cooldown": 2.6}
        self.last_power_text = "Portal opened. Boss descended."
        self.spawn_power_fx("ring", self.portal_origin + Vec3(0, 0, -8.0), (1.0, 0.12, 0.08, 0.82), 8.8)

        self.boss["type"] = "eye"
        self.boss["name"] = "Eye Tyrant"

    def spawn_sandworm_boss(self) -> None:
        root = self.render.attachNewNode("sandworm_boss")
        ang = random.random() * math.tau
        dist = random.uniform(self.city_world_radius * 0.30, self.city_world_radius * 0.82)
        if _preview:
            dist = self.city_world_radius * 0.52
            ang = math.pi * 0.5
        ground_origin = Vec3(math.cos(ang) * dist, math.sin(ang) * dist, 0.0)
        launch_origin = self.portal_origin + Vec3(random.uniform(-34.0, 34.0), random.uniform(-34.0, 34.0), 220.0)
        if _preview:
            root.setPos(ground_origin + Vec3(0, 0, 34.0))
        else:
            root.setPos(launch_origin)

        segments = []
        segment_count = 16
        for i in range(segment_count):
            t = i / max(1, segment_count - 1)
            radius = lerp(1.25, 5.15, t)
            orb = _SMOOTH_FACTORY.uv_sphere(f"worm_orb_{i}", 1.0, 18 + min(14, i), 14 + min(10, i // 2))
            orb.reparentTo(root)
            orb.setScale(radius * (0.88 + t * 0.18), radius, radius * (0.92 + t * 0.14))
            orb.setColorScale(lerp(0.18, 0.52, t), lerp(0.11, 0.34, t), lerp(0.08, 0.18, t), 1.0)
            shell = _SMOOTH_FACTORY.uv_sphere(f"worm_shell_{i}", 1.03, 16 + min(12, i), 12 + min(8, i // 2))
            shell.reparentTo(orb)
            shell.setScale(1.05, 1.0, 0.95)
            shell.setTransparency(TransparencyAttrib.M_alpha)
            shell.setColorScale(0.10 + t * 0.06, 0.26 + t * 0.08, 0.08 + t * 0.04, 0.18)
            segments.append({"node": orb, "shell": shell, "radius": radius, "world": Vec3(0, 0, 0)})

        head_pivot = root.attachNewNode("worm_head_pivot")
        head_core = _SMOOTH_FACTORY.uv_sphere("worm_head_core", 4.3, 28, 22)
        head_core.reparentTo(head_pivot)
        head_core.setScale(1.0, 1.34, 0.94)
        head_core.setColorScale(0.44, 0.24, 0.16, 1.0)
        skull_plate = _SMOOTH_FACTORY.box("worm_skull_plate", 5.8, 3.0, 2.1)
        skull_plate.reparentTo(head_pivot)
        skull_plate.setPos(0, 1.5, 1.1)
        skull_plate.setHpr(0, -18, 0)
        skull_plate.setColorScale(0.24, 0.14, 0.10, 1.0)
        maw = _SMOOTH_FACTORY.box("worm_maw", 4.8, 2.8, 2.2)
        maw.reparentTo(head_pivot)
        maw.setPos(0, 3.6, -0.1)
        maw.setColorScale(0.12, 0.03, 0.03, 1.0)
        jaw = _SMOOTH_FACTORY.box("worm_jaw", 4.5, 2.7, 1.3)
        jaw.reparentTo(head_pivot)
        jaw.setPos(0, 3.4, -1.8)
        jaw.setColorScale(0.24, 0.07, 0.06, 1.0)

        finger_chains = []
        finger_specs = [
            (-2.45, 2.55, 0.75, -40.0, -14.0),
            (2.45, 2.55, -0.75, 40.0, 14.0),
        ]
        for idx, (sx, sy, sz, splay_h, splay_r) in enumerate(finger_specs):
            base = head_pivot.attachNewNode(f"worm_finger_base_{idx}")
            base.setPos(sx, sy, sz)
            base.setHpr(splay_h, 0.0, splay_r)
            seg_a = _SMOOTH_FACTORY.cylinder(f"worm_finger_a_{idx}", 0.40, 3.4, 12)
            seg_a.reparentTo(base)
            seg_a.setHpr(90.0, 0.0, 0.0)
            seg_a.setPos(0.0, 1.7, 0.0)
            seg_a.setColorScale(0.56, 0.42, 0.24, 1.0)
            mid = base.attachNewNode(f"worm_finger_mid_{idx}")
            mid.setPos(0.0, 3.4, 0.0)
            seg_b = _SMOOTH_FACTORY.cylinder(f"worm_finger_b_{idx}", 0.26, 2.8, 12)
            seg_b.reparentTo(mid)
            seg_b.setHpr(90.0, 0.0, 0.0)
            seg_b.setPos(0.0, 1.4, 0.0)
            seg_b.setColorScale(0.62, 0.48, 0.26, 1.0)
            tip = mid.attachNewNode(f"worm_finger_tip_{idx}")
            tip.setPos(0.0, 2.8, 0.0)
            claw = NodePath(GeomFactory.make_pyramid(0.40, 0.40, 2.35, 1.0, 1.0))
            claw.reparentTo(tip)
            claw.setHpr(45.0, 90.0, 0.0)
            claw.setColorScale(0.88, 0.84, 0.72, 1.0)
            finger_chains.append({
                "base": base,
                "mid": mid,
                "tip": tip,
                "claw": claw,
                "base_h": splay_h,
                "base_r": splay_r,
                "phase": idx * 0.8 + random.random() * 0.3,
            })

        acid = _SMOOTH_FACTORY.uv_sphere("worm_acid_glow", 1.0, 18, 14)
        acid.reparentTo(head_pivot)
        acid.setPos(0, 4.35, -0.28)
        acid.setLightOff(True)
        acid.setTransparency(TransparencyAttrib.M_alpha)
        acid.setDepthWrite(False)
        acid.setBin("transparent", 46)
        acid.setColorScale(0.34, 1.0, 0.18, 0.52)

        self.boss = {
            "type": "sandworm",
            "name": "Grasp Maw Sandworm",
            "root": root,
            "head": head_pivot,
            "jaw": jaw,
            "maw": maw,
            "acid": acid,
            "segments": segments,
            "finger_chains": finger_chains,
            "hp": 620.0,
            "alive": True,
            "phase": random.random() * math.tau,
            "intro": 0.0 if _preview else 4.2,
            "beam_cooldown": 0.0,
            "acid_cooldown": 1.6,
            "grab_cooldown": 2.2,
            "grab_active": False,
            "grab_timer": 0.0,
            "grab_target": None,
            "grab_fx_timer": 0.0,
            "grab_sound_timer": 0.0,
            "coil_timer": 0.0,
            "coil_duration": 0.56,
            "lunge_timer": 0.0,
            "lunge_duration": 0.34,
            "lunge_cooldown": 1.3,
            "attack_target": Vec3(ground_origin.x, ground_origin.y, 18.0),
            "coil_anchor": Vec3(ground_origin.x, ground_origin.y, 18.0),
            "home": Vec3(ground_origin),
            "launch_origin": Vec3(launch_origin),
            "segment_worlds": [],
            "mouth_world": Vec3(ground_origin.x, ground_origin.y, 8.0),
            "head_world": Vec3(ground_origin.x, ground_origin.y, 10.0),
            "contact_points": [],
        }
        self.last_power_text = "Portal rupture. Grasp Maw Sandworm emerged."
        self.spawn_power_fx("ring", self.portal_origin + Vec3(0, 0, -24.0), (1.0, 0.18, 0.12, 0.82), 6.2)
        self.spawn_power_fx("ring", ground_origin + Vec3(0, 0, 1.2), (0.82, 0.62, 0.24, 0.78), 4.8)

    def get_sandworm_target_world(self, target: dict | None) -> tuple[Vec3, str, dict | None]:
        if target is None or target.get("kind") == "player":
            return self.hero_pos + Vec3(0, 0, 1.2), "player", None
        npc = target.get("npc")
        if npc is None or npc.get("dead", False):
            return self.hero_pos + Vec3(0, 0, 1.2), "player", None
        return npc["pos"] + Vec3(0, 0, 1.15 * npc["profile"]["scale"]), "npc", npc

    def release_sandworm_grab(self, boss: dict) -> None:
        boss["grab_active"] = False
        boss["grab_timer"] = 0.0
        boss["grab_target"] = None
        boss["grab_fx_timer"] = 0.0
        boss["grab_sound_timer"] = 0.0
        boss["grab_cooldown"] = 5.2
        boss["coil_timer"] = 0.0
        boss["lunge_timer"] = 0.0

    def start_sandworm_grab(self, boss: dict, kind: str, npc: dict | None) -> None:
        boss["grab_active"] = True
        boss["grab_timer"] = 3.0
        boss["grab_target"] = {"kind": kind, "npc": npc}
        boss["grab_fx_timer"] = 0.0
        boss["grab_sound_timer"] = 0.0
        boss["grab_cooldown"] = 7.0
        self.last_power_text = "Sandworm grab"
        self.play_sfx("charge_up", volume=0.58, rate=0.52 + random.random() * 0.08)

    def update_sandworm_boss(self, dt: float, time_value: float) -> None:
        if self.boss is None or not self.boss.get("alive", False):
            return
        boss = self.boss
        boss["intro"] = max(0.0, boss.get("intro", 0.0) - dt)
        boss["acid_cooldown"] = max(0.0, boss.get("acid_cooldown", 0.0) - dt)
        boss["grab_cooldown"] = max(0.0, boss.get("grab_cooldown", 0.0) - dt)
        boss["lunge_cooldown"] = max(0.0, boss.get("lunge_cooldown", 0.0) - dt)
        prev_coil = float(boss.get("coil_timer", 0.0))
        prev_lunge = float(boss.get("lunge_timer", 0.0))
        boss["coil_timer"] = max(0.0, prev_coil - dt)
        boss["lunge_timer"] = max(0.0, prev_lunge - dt)
        root = boss["root"]

        target = self.choose_boss_target()
        target_pos, target_kind, target_npc = self.get_sandworm_target_world(target)
        home = Vec3(boss.get("home", Vec3(0, 0, 0)))
        current_head = root.getPos(self.render)

        grab = boss.get("grab_target") if boss.get("grab_active") else None
        if grab is not None:
            if grab.get("kind") == "player":
                target_pos = self.hero_pos + Vec3(0, 0, 1.2)
            else:
                npc = grab.get("npc")
                if npc is None or npc.get("dead", False):
                    self.release_sandworm_grab(boss)
                    grab = None
                else:
                    target_pos = npc["pos"] + Vec3(0, 0, 1.15 * npc["profile"]["scale"])

        flat = Vec3(target_pos.x - home.x, target_pos.y - home.y, 0.0)
        flat_dist = flat.length()
        if flat_dist > 1e-6:
            flat_dir = flat / flat_dist
        else:
            flat_dir = Vec3(0, 1, 0)
        side = Vec3(-flat_dir.y, flat_dir.x, 0.0)
        surface_z = 10.0 + math.sin(time_value * 0.76 + boss["phase"]) * 1.8
        reach = min(92.0, max(22.0, flat_dist * 0.88))
        bite_height = clamp(target_pos.z + 2.6 + math.sin(time_value * 1.9 + boss["phase"]) * 2.8, 15.0, 76.0)

        if (not boss.get("grab_active")) and boss["intro"] <= 0.0 and boss.get("coil_timer", 0.0) <= 0.0 and boss.get("lunge_timer", 0.0) <= 0.0 and boss.get("lunge_cooldown", 0.0) <= 0.0 and flat_dist < 116.0:
            boss["coil_timer"] = float(boss.get("coil_duration", 0.56))
            boss["coil_anchor"] = Vec3(home + flat_dir * max(8.0, reach * 0.38) + Vec3(0, 0, 14.0 + min(24.0, flat_dist * 0.10)))
            boss["attack_target"] = Vec3(target_pos + flat_dir * 5.8 + Vec3(0, 0, 2.4))
            self.play_sfx("charge_up", volume=0.48, rate=0.42 + random.random() * 0.05)

        if prev_coil > 0.0 and boss.get("coil_timer", 0.0) <= 0.0 and not boss.get("grab_active"):
            boss["lunge_timer"] = float(boss.get("lunge_duration", 0.34))
            boss["attack_target"] = Vec3(target_pos + flat_dir * 6.8 + Vec3(0, 0, 2.0))
            boss["lunge_cooldown"] = 1.65
            self.play_sfx("move_dash", volume=0.54, rate=0.66 + random.random() * 0.06)

        coil_strength = 0.0
        if boss.get("coil_duration", 0.56) > 0.0:
            coil_strength = clamp(boss.get("coil_timer", 0.0) / boss.get("coil_duration", 0.56), 0.0, 1.0)
        lunge_strength = 0.0
        if boss.get("lunge_duration", 0.34) > 0.0:
            lunge_strength = clamp(boss.get("lunge_timer", 0.0) / boss.get("lunge_duration", 0.34), 0.0, 1.0)

        desired_head = Vec3(home + flat_dir * reach + Vec3(0, 0, bite_height))
        if boss["intro"] > 0.0:
            intro_t = clamp(1.0 - boss["intro"] / 4.2, 0.0, 1.0)
            desired_head = Vec3(
                lerp(boss["launch_origin"].x, desired_head.x, intro_t),
                lerp(boss["launch_origin"].y, desired_head.y, intro_t),
                lerp(boss["launch_origin"].z, desired_head.z, intro_t),
            )
        elif boss.get("grab_active"):
            desired_head = target_pos + flat_dir * 3.2 + Vec3(0, 0, 1.6)
        elif coil_strength > 0.0:
            anchor = Vec3(boss.get("coil_anchor", desired_head))
            coil_lift = Vec3(0, 0, 6.0 * math.sin((1.0 - coil_strength) * math.pi))
            desired_head = anchor - flat_dir * (6.0 + coil_strength * 8.0) + side * math.sin(time_value * 6.5 + boss["phase"]) * (3.0 + coil_strength * 4.0) + coil_lift
        elif lunge_strength > 0.0:
            attack_target = Vec3(boss.get("attack_target", target_pos))
            lunge_t = 1.0 - lunge_strength
            overshoot = flat_dir * (10.0 * math.sin(lunge_t * math.pi))
            desired_head = Vec3(
                lerp(current_head.x, attack_target.x, clamp(lunge_t * 1.35, 0.0, 1.0)),
                lerp(current_head.y, attack_target.y, clamp(lunge_t * 1.35, 0.0, 1.0)),
                lerp(current_head.z, attack_target.z, clamp(lunge_t * 1.35, 0.0, 1.0)),
            ) + overshoot + Vec3(0, 0, 2.0 * math.sin(lunge_t * math.pi))

        head_follow = 2.2 + coil_strength * 1.4 + lunge_strength * 7.4
        root.setPos(current_head + (desired_head - current_head) * clamp(dt * head_follow, 0.0, 1.0))
        look_target = target_pos + Vec3(0, 0, -0.4 if boss.get("grab_active") else 1.4)
        root.lookAt(look_target)
        root.setR(math.sin(time_value * 1.5 + boss["phase"]) * (2.4 + lunge_strength * 4.0))
        boss["head_world"] = root.getPos(self.render)

        jaw_open = 12.0 + (0.5 + 0.5 * math.sin(time_value * 3.2 + boss["phase"])) * 20.0
        if boss.get("grab_active"):
            jaw_open = 28.0
        jaw_open += coil_strength * 12.0 + lunge_strength * 18.0
        boss["jaw"].setP(jaw_open)
        boss["jaw"].setZ(-1.8 - jaw_open * 0.018)
        boss["maw"].setScale(1.0, 1.0 + jaw_open * 0.013, 1.0 + jaw_open * 0.008)
        acid = boss.get("acid")
        if acid is not None:
            acid.setColorScale(0.36, 1.0, 0.18, 0.20 + 0.36 * (0.5 + 0.5 * math.sin(time_value * 5.2)) + lunge_strength * 0.10)
            acid.setScale(0.84 + 0.38 * max(coil_strength, grab_blend if 'grab_blend' in locals() else 0.0) + 0.34 * lunge_strength + 0.18 * math.sin(time_value * 6.4))

        mouth_world = root.getPos(self.render) + self.forward_from_angles(root.getH(), root.getP()) * 4.8 + Vec3(0, 0, -0.55)
        boss["mouth_world"] = mouth_world

        anchor = Vec3(home.x, home.y, surface_z)
        p0 = anchor
        p1 = anchor + Vec3(0, 0, 14.0 + reach * 0.18 + coil_strength * 16.0)
        p2 = desired_head - flat_dir * max(8.0, reach * (0.22 + lunge_strength * 0.08)) + Vec3(0, 0, -8.0 + coil_strength * 12.0)
        p3 = root.getPos(self.render)
        chain_length = max(1.0, (p3 - p0).length())
        visible_target = 6 + chain_length / 7.0 + coil_strength * 2.0 + lunge_strength * 4.0
        active_count = int(clamp(visible_target, 7, len(boss["segments"])))

        points = []
        for i in range(active_count):
            t = i / max(1, active_count - 1)
            omt = 1.0 - t
            point = (p0 * (omt ** 3)) + (p1 * (3.0 * omt * omt * t)) + (p2 * (3.0 * omt * t * t)) + (p3 * (t ** 3))
            coil_wave = math.sin(time_value * 5.6 + i * 0.78 + boss["phase"])
            side_amp = (1.0 - coil_strength * 0.25) * (1.4 + t * 4.0) + coil_strength * (5.2 - t * 1.8)
            point += side * coil_wave * side_amp * (0.09 + t * 0.18)
            point += Vec3(0, 0, math.cos(time_value * 4.8 + i * 0.55 + boss["phase"]) * (0.5 + lunge_strength * 0.9))
            if i == 0:
                point = p0
            elif i == active_count - 1:
                point = p3
            points.append(point)

        segment_worlds = []
        contact_points = []
        for i, seg in enumerate(boss["segments"]):
            node = seg["node"]
            shell = seg["shell"]
            if i >= active_count:
                node.hide()
                continue
            node.show()
            point = points[i]
            next_point = points[min(active_count - 1, i + 1)] if active_count > 1 else p3
            if i > 0 and (next_point - point).lengthSquared() < 1e-6:
                next_point = point + flat_dir
            node.setPos(self.render, point)
            try:
                node.lookAt(self.render, next_point)
            except Exception:
                pass
            t = i / max(1, active_count - 1)
            pulse = math.sin(time_value * 5.2 + i * 0.42 + boss["phase"])
            local_coil = coil_strength * (1.0 - t * 0.78)
            local_stretch = lunge_strength * (0.26 + t * 0.74)
            girth = 1.00 + local_coil * 0.20 + 0.05 * pulse
            lengthen = 1.00 + local_stretch * 0.48 - local_coil * 0.24
            radius = seg["radius"]
            node.setScale(radius * girth * 1.02, radius * lengthen, radius * girth * 0.94)
            shell.setScale(1.08 + local_coil * 0.05, 0.96 + local_stretch * 0.12, 0.94)
            seg["world"] = Vec3(point)
            segment_worlds.append(Vec3(point))
            if i >= active_count // 2:
                contact_points.append(Vec3(point))
        boss["segment_worlds"] = segment_worlds
        boss["contact_points"] = contact_points + [Vec3(mouth_world)]

        grab_blend = 1.0 if boss.get("grab_active") else 0.0
        for idx, finger in enumerate(boss.get("finger_chains", [])):
            curl = 0.26 + 0.54 * (0.5 + 0.5 * math.sin(time_value * 2.8 + finger["phase"]))
            curl += coil_strength * 0.42 + lunge_strength * 0.22
            if boss.get("grab_active"):
                curl = 1.0
            finger["base"].setHpr(finger["base_h"], -10.0 - curl * 30.0, finger["base_r"] + math.sin(time_value * 1.8 + idx) * (4.0 + lunge_strength * 4.0))
            finger["mid"].setHpr(0.0, -18.0 - curl * 40.0, 0.0)
            finger["tip"].setHpr(0.0, -8.0 - curl * 22.0, 0.0)

        if boss.get("grab_active"):
            boss["grab_timer"] = max(0.0, boss.get("grab_timer", 0.0) - dt)
            boss["grab_fx_timer"] = max(0.0, boss.get("grab_fx_timer", 0.0) - dt)
            boss["grab_sound_timer"] = max(0.0, boss.get("grab_sound_timer", 0.0) - dt)
            grip_world = mouth_world + self.forward_from_angles(root.getH(), root.getP()) * 1.1
            target_data = boss.get("grab_target") or {"kind": "player", "npc": None}
            if target_data.get("kind") == "player":
                self.hero_velocity *= 0.22
                self.hero_pos = self.hero_pos + (grip_world - self.hero_pos) * clamp(dt * 8.0, 0.0, 1.0)
                self.hero_root.setPos(self.hero_pos)
                self.damage_player(13.0 * dt, "sandworm")
            else:
                npc = target_data.get("npc")
                if npc is not None and not npc.get("dead", False):
                    npc["velocity"] *= 0.18
                    npc["pos"] = npc["pos"] + (grip_world - npc["pos"]) * clamp(dt * 8.0, 0.0, 1.0)
                    npc["root"].setPos(npc["pos"])
                    self.damage_npc(npc, 15.0 * dt, "sandworm")
            if boss["grab_fx_timer"] <= 0.0:
                cloud = grip_world + Vec3(random.uniform(-1.6, 1.6), random.uniform(-1.6, 1.6), random.uniform(-1.2, 1.2))
                self.spawn_power_fx("acid", cloud, (0.34, 1.0, 0.18, 0.84), 0.82)
                self.spawn_power_fx("smoke", cloud, (0.18, 0.42, 0.16, 0.42), 0.76)
                boss["grab_fx_timer"] = 0.15
            if boss["grab_sound_timer"] <= 0.0:
                self.play_sfx("mode_wire", volume=0.34, rate=0.40 + random.random() * 0.06)
                boss["grab_sound_timer"] = 0.42
            if boss["grab_timer"] <= 0.0:
                self.release_sandworm_grab(boss)
        else:
            close_enough = (mouth_world - target_pos).length() < 9.2
            if boss["intro"] <= 0.0 and boss.get("grab_cooldown", 0.0) <= 0.0 and close_enough and boss.get("coil_timer", 0.0) <= 0.0 and boss.get("lunge_timer", 0.0) <= 0.0:
                self.start_sandworm_grab(boss, target_kind, target_npc)

        self.crush_structures_with_boss(dt)
        if (not boss.get("grab_active")) and boss["acid_cooldown"] <= 0.0 and boss.get("lunge_timer", 0.0) <= 0.0:
            base_dir = target_pos - mouth_world
            if base_dir.lengthSquared() < 1e-6:
                base_dir = Vec3(0, 1, 0)
            base_dir.normalize()
            right = self.right_from_yaw(root.getH())
            for spread in (-0.16, -0.08, 0.0, 0.08, 0.16):
                spit_dir = Vec3(base_dir + right * spread + Vec3(0, 0, random.uniform(-0.06, 0.16)))
                spit_dir.normalize()
                self.spawn_projectile(mouth_world + right * spread * 3.6, spit_dir, 72.0 + random.random() * 10.0, True, kind_override="flame", color_override=(0.38, 1.0, 0.18, 1.0), scale_mul=1.20, life_mul=1.55, owner="boss", owner_heading=root.getH())
            self.spawn_power_fx("burst", mouth_world, (0.52, 1.0, 0.24, 0.86), 1.05)
            self.play_sfx("mode_fireball", volume=0.54, rate=0.74 + random.random() * 0.12)
            boss["acid_cooldown"] = 2.8 + random.random() * 1.6

    def choose_boss_target(self) -> dict | None:
        if self.boss is None or not self.boss.get("alive", False):
            return None
        boss_pos = self.boss["root"].getPos()
        candidates = []
        if self.player_hp > 0.0:
            candidates.append({"kind": "player", "dist": (self.hero_pos - boss_pos).lengthSquared()})
        for npc in self.npcs:
            if npc.get("dead", False):
                continue
            candidates.append({"kind": "npc", "npc": npc, "dist": (npc["pos"] - boss_pos).lengthSquared()})
        if not candidates:
            return None
        candidates.sort(key=lambda item: item["dist"])
        return candidates[0]

    def start_boss_beam(self, target: dict) -> None:
        if self.boss is None or not self.boss.get("alive", False):
            return
        if self.boss_beam is not None:
            for node in (self.boss_beam.get("core"), self.boss_beam.get("halo")):
                if node is not None and not node.isEmpty():
                    node.removeNode()
        core = _SMOOTH_FACTORY.box("boss_beam_core", 1.0, 1.0, 1.0)
        core.reparentTo(self.render)
        core.setTexture(self.fx_textures.get("beam", self.texture_factory.make_glitch("boss_ray_tex", 9195)), 1)
        core.setTransparency(TransparencyAttrib.M_alpha)
        core.setDepthWrite(False)
        core.setBin("transparent", 60)
        core.setLightOff(True)
        halo = _SMOOTH_FACTORY.box("boss_beam_halo", 1.0, 1.0, 1.0)
        halo.reparentTo(self.render)
        halo.setTexture(self.fx_textures.get("beam", self.texture_factory.make_glitch("boss_ray_halo", 9196)), 1)
        halo.setTransparency(TransparencyAttrib.M_alpha)
        halo.setDepthWrite(False)
        halo.setBin("transparent", 59)
        halo.setLightOff(True)
        self.boss_beam = {"core": core, "halo": halo, "target": target, "timer": 2.2}
        self.play_sfx("mode_beam", volume=0.46, rate=0.72)


    def update_boss_beam(self, dt: float) -> None:
        if self.boss_beam is None or self.boss is None or not self.boss.get("alive", False):
            return
        beam = self.boss_beam
        beam["timer"] -= dt
        if beam["timer"] <= 0.0:
            for node in (beam.get("core"), beam.get("halo")):
                if node is not None and not node.isEmpty():
                    node.removeNode()
            self.boss_beam = None
            return

        target = beam["target"]
        if target.get("kind") == "player":
            end = self.hero_pos + Vec3(0, 0, 1.2)
        else:
            npc = target.get("npc")
            if npc is None or npc.get("dead", False):
                beam["timer"] = 0.0
                return
            end = npc["pos"] + Vec3(0, 0, 1.25 * npc["profile"]["scale"])

        start = self.boss["root"].getPos() + Vec3(0, 4.8, 0.0)
        vec = end - start
        dist = max(1.0, vec.length())
        dir_vec = Vec3(vec)
        if dir_vec.lengthSquared() > 1e-6:
            dir_vec.normalize()
        else:
            dir_vec = Vec3(0, 1, 0)
        end_ext = end + dir_vec * 36.0
        mid = start + (end_ext - start) * 0.5
        dist_ext = max(1.0, (end_ext - start).length())
        for node, thick, alpha in ((beam["halo"], 2.20, 0.26), (beam["core"], 0.90, 0.84)):
            node.setPos(mid)
            node.lookAt(end_ext)
            node.setScale(thick, dist_ext * 0.5, thick)
            node.setColorScale(1.0, 0.14 + alpha * 0.22, 0.08 + alpha * 0.10, alpha)

        beam_radius_sq = 6.8 ** 2
        if segment_distance_squared(self.hero_pos + Vec3(0, 0, 1.2), start, end_ext) <= beam_radius_sq:
            self.damage_player(22.0 * dt, "boss")
        for npc in self.npcs:
            if npc.get("dead", False):
                continue
            check = npc["pos"] + Vec3(0, 0, 1.2 * npc["profile"]["scale"])
            if segment_distance_squared(check, start, end_ext) <= beam_radius_sq:
                self.damage_npc(npc, 22.0 * dt, "boss")

    def hit_boss_by_projectile(self, pos: Vec3, strong: bool, owner: str) -> bool:
        if self.boss is None or not self.boss.get("alive", False):
            return False
        if owner == "boss":
            return False
        boss = self.boss
        center = boss["root"].getPos()
        radius = 7.2 if strong else 6.1
        if str(boss.get("type", "eye")) == "sandworm":
            checks = [Vec3(boss.get("mouth_world", center))] + [Vec3(p) for p in boss.get("segment_worlds", [])[-6:]]
            hit = False
            for idx, point in enumerate(checks):
                test_radius = (5.6 if idx == 0 else 4.2) * (1.08 if strong else 0.92)
                if (point - pos).lengthSquared() <= test_radius * test_radius:
                    hit = True
                    break
            if not hit:
                return False
        elif (center - pos).lengthSquared() > radius * radius:
            return False
        damage = 1.4 if strong else 1.0
        self.boss["hp"] = max(0.0, self.boss["hp"] - damage)
        self.spawn_power_fx("burst", pos, (0.98, 0.42, 0.20, 0.86), 0.58)
        self.boss["beam_cooldown"] = min(self.boss.get("beam_cooldown", 0.0), 1.25)
        if self.boss["hp"] <= 0.0:
            self.boss["alive"] = False
            self.boss["death_timer"] = 3.0
            self.boss_spawn_timer = 0.8 if _preview else self.boss_respawn_delay
            self.random_death_fx(center + Vec3(0, 0, 2.0), (0.94, 0.26, 0.20, 0.90), 4.0)
            if self.boss_beam is not None:
                for node in (self.boss_beam.get("core"), self.boss_beam.get("halo")):
                    if node is not None and not node.isEmpty():
                        node.removeNode()
                self.boss_beam = None
            self.boss["root"].hide()
            self.last_power_text = "Boss destroyed"
        return True

    def schedule_weather_cycle(self, cycle_index: int) -> None:
        if self.weather_schedule_cycle == cycle_index:
            return
        self.weather_schedule_cycle = cycle_index
        rnd = random.Random(self.seed * 131 + cycle_index * 1709)

        def choose_weather(day_part: str) -> str:
            roll = rnd.random()
            if day_part == "day":
                if roll < 0.38:
                    return "sand"
                if roll < 0.64:
                    return "rain"
                if roll < 0.86:
                    return "thunder"
                return "acid"
            else:
                if roll < 0.24:
                    return "sand"
                if roll < 0.52:
                    return "rain"
                if roll < 0.82:
                    return "thunder"
                return "acid"

        def schedule(start_low: float, start_high: float):
            duration = rnd.uniform(300.0, 600.0)
            return duration / self.day_cycle_seconds, rnd.uniform(start_low, start_high)

        day_dur, day_start = schedule(0.06, 0.24)
        night_dur, night_start = schedule(0.58, 0.76)
        self.weather_events = {
            "day": {"type": choose_weather("day"), "start": day_start, "dur": min(day_dur, 0.26)},
            "night": {"type": choose_weather("night"), "start": night_start, "dur": min(night_dur, 0.26)},
        }

        if rnd.random() < 0.10:
            eclipse_dur = rnd.uniform(120.0, 240.0) / self.day_cycle_seconds
            eclipse_start = rnd.uniform(0.12, max(0.16, 0.42 - eclipse_dur))
            self.weather_events["eclipse"] = {"start": eclipse_start, "dur": eclipse_dur}
        else:
            self.weather_events["eclipse"] = None

    def update_environment(self, dt: float) -> None:
        self.world_time += dt
        cycle_index = int(self.world_time / self.day_cycle_seconds)
        phase = (self.world_time % self.day_cycle_seconds) / self.day_cycle_seconds
        self.schedule_weather_cycle(cycle_index)

        daylight = clamp(math.sin(phase * math.pi * 2.0), 0.0, 1.0)
        twilight = clamp(math.sin(phase * math.pi * 2.0) * 0.5 + 0.5, 0.0, 1.0)
        event = None
        intensity = 0.0
        fade = 0.04
        for key in ("day", "night"):
            info = self.weather_events.get(key)
            if info is None:
                continue
            start = float(info["start"])
            end = start + float(info["dur"])
            if start <= phase <= end:
                event = info
                local = (phase - start) / max(0.0001, float(info["dur"]))
                fade_n = min(local / fade, (1.0 - local) / fade, 1.0)
                intensity = clamp(fade_n, 0.0, 1.0)
                break

        self.active_weather = str(event["type"]) if event else "clear"
        self.weather_intensity = intensity

        eclipse = self.weather_events.get("eclipse")
        self.eclipse_intensity = 0.0
        if eclipse is not None:
            start = float(eclipse["start"])
            end = start + float(eclipse["dur"])
            if start <= phase <= end:
                local = (phase - start) / max(0.0001, float(eclipse["dur"]))
                fade_n = min(local / 0.12, (1.0 - local) / 0.12, 1.0)
                self.eclipse_intensity = clamp(fade_n, 0.0, 1.0)

        self.lightning_flash = max(0.0, self.lightning_flash - dt * 2.6)
        self.lightning_timer -= dt
        if self.active_weather in ("thunder", "acid") and self.weather_intensity > 0.25 and self.lightning_timer <= 0.0:
            self.lightning_flash = 1.0
            self.lightning_timer = random.uniform(9.0, 18.0) if self.active_weather == "thunder" else random.uniform(14.0, 26.0)
        elif self.lightning_timer <= 0.0:
            self.lightning_timer = 8.0

        storm_dark = 0.0
        fog_color = Vec4(
            lerp(0.18, 0.72, twilight),
            lerp(0.16, 0.62, twilight),
            lerp(0.20, 0.48, twilight),
            1.0,
        )
        fog_near, fog_far = 42.0, 320.0
        overlay_color = (0.70, 0.62, 0.50, 0.0)

        if self.active_weather == "sand":
            storm_dark = 0.18 * intensity
            self.weather_wind_strength = 0.85 * intensity
            fog_color = Vec4(0.78, 0.62, 0.40, 1.0)
            fog_near, fog_far = 28.0, 170.0
            overlay_color = (0.78, 0.62, 0.38, 0.12 * intensity)
        elif self.active_weather == "rain":
            storm_dark = 0.14 * intensity
            self.weather_wind_strength = 0.26 * intensity
            fog_color = Vec4(0.46, 0.48, 0.52, 1.0)
            fog_near, fog_far = 34.0, 220.0
            overlay_color = (0.48, 0.50, 0.56, 0.08 * intensity)
        elif self.active_weather == "thunder":
            storm_dark = 0.24 * intensity
            self.weather_wind_strength = 0.38 * intensity
            fog_color = Vec4(0.34, 0.36, 0.42, 1.0)
            fog_near, fog_far = 30.0, 185.0
            overlay_color = (0.38, 0.40, 0.48, 0.13 * intensity)
        elif self.active_weather == "acid":
            storm_dark = 0.18 * intensity
            self.weather_wind_strength = 0.34 * intensity
            fog_color = Vec4(0.34, 0.48, 0.24, 1.0)
            fog_near, fog_far = 26.0, 160.0
            overlay_color = (0.30, 0.54, 0.24, 0.12 * intensity)
        else:
            self.weather_wind_strength = 0.06 + (0.02 if twilight < 0.2 else 0.0)

        if self.eclipse_intensity > 0.0:
            storm_dark += self.eclipse_intensity * 0.55
            fog_color = Vec4(
                fog_color.x * (1.0 - self.eclipse_intensity * 0.36),
                fog_color.y * (1.0 - self.eclipse_intensity * 0.40),
                fog_color.z * (1.0 - self.eclipse_intensity * 0.28),
                1.0,
            )

        amb = 0.10 + daylight * 0.38
        amb *= (1.0 - storm_dark)
        sun_i = (0.18 + daylight * 1.10) * (1.0 - storm_dark) * (1.0 - self.eclipse_intensity * 0.72)
        if self.lightning_flash > 0.0:
            sun_i += self.lightning_flash * 1.25
            amb += self.lightning_flash * 0.32

        self.amb_light.setColor(Vec4(amb * 0.94, amb * 0.92, amb, 1.0))
        self.sun_light.setColor(Vec4(sun_i * 1.00, sun_i * 0.92, sun_i * 0.82, 1.0))
        rim = 0.16 + (1.0 - daylight) * 0.24
        self.rim_light.setColor(Vec4(rim * 0.75, rim * 0.78, rim, 1.0))

        self.world_fog.setColor(fog_color.x, fog_color.y, fog_color.z)
        self.world_fog.setLinearRange(fog_near, fog_far)
        self.setBackgroundColor(fog_color.x * 0.92, fog_color.y * 0.92, fog_color.z * 0.92, 1.0)
        self.storm_overlay.setColorScale(*overlay_color)

        orbit = phase * math.pi * 2.0
        sun_height = math.sin(orbit)
        sun_x = math.cos(orbit) * 1200.0
        sun_y = 2400.0
        sun_z = 900.0 + sun_height * 1400.0
        base = self.hero_pos + Vec3(sun_x, sun_y, sun_z)
        self.sun_node.setPos(base)
        self.sun_halo.setPos(base)
        sun_alpha = clamp(daylight * 1.25 + 0.08, 0.0, 1.0)
        self.sun_node.setColorScale(1.0, 0.52, 0.46, sun_alpha * (1.0 - self.eclipse_intensity * 0.86))
        self.sun_halo.setColorScale(1.0, 0.28, 0.22, (0.10 + daylight * 0.18) * (1.0 - self.eclipse_intensity * 0.72))
        if self.eclipse_intensity > 0.0:
            self.eclipse_node.show()
            self.eclipse_node.setPos(base + Vec3(18.0, -12.0, 6.0))
            self.eclipse_node.setColorScale(0.02, 0.02, 0.03, self.eclipse_intensity * 0.82)
        else:
            self.eclipse_node.hide()

        self.update_weather_visuals()
        self.update_surface_water(dt)

        hours = int(phase * 24.0) % 24
        minutes = int((phase * 24.0 - hours) * 60.0) % 60
        weather_name = "Clear" if self.active_weather == "clear" else self.active_weather.title()
        if self.eclipse_intensity > 0.12:
            weather_name = f"{weather_name} Eclipse"
        self.time_label = f"{hours:02d}:{minutes:02d} {weather_name}"

    def update_weather_visuals(self) -> None:
        t = globalClock.getFrameTime()
        active = self.active_weather
        intensity = self.weather_intensity

        for i, node in enumerate(self.weather_cards):
            if not bool(self.settings_data.get("weather_fx_enabled", True)) or active == "clear" or intensity <= 0.02:
                node.hide()
                continue

            node.show()
            if active in ("rain", "thunder", "acid"):
                swirl = t * (6.0 if active == "rain" else 7.2 if active == "thunder" else 5.4) + i * 0.91
                px = self.hero_pos.x + math.sin(swirl * 0.72) * 34.0 + (i % 4 - 1.5) * 11.0
                py = self.hero_pos.y + math.cos(swirl * 0.68) * 30.0 + (i // 4 - 1.0) * 14.0
                pz = self.hero_pos.z + 24.0 - ((t * (34.0 + i * 1.3) + i * 4.2) % 34.0)
                node.setPos(px, py, pz)
                node.setScale(0.16 + intensity * 0.08, 1.0, 1.80 + intensity * 1.10)
                if active == "acid":
                    node.setColorScale(0.38, 1.0, 0.34, 0.24 + intensity * 0.34)
                elif active == "thunder":
                    node.setColorScale(0.74 + self.lightning_flash * 0.40, 0.84 + self.lightning_flash * 0.40, 1.0, 0.22 + intensity * 0.28)
                else:
                    node.setColorScale(0.64, 0.76, 0.96, 0.20 + intensity * 0.24)
            else:
                drift = t * (4.0 + i * 0.12) + i * 0.73
                px = self.hero_pos.x + ((drift * 18.0) % 90.0) - 45.0
                py = self.hero_pos.y + math.sin(drift * 0.8) * 26.0 + (i // 3 - 1.5) * 18.0
                pz = self.hero_pos.z + 3.0 + (i % 3) * 4.0 + math.sin(drift * 1.6) * 1.2
                node.setPos(px, py, pz)
                node.setScale(1.2 + intensity * 0.60, 1.0, 1.0 + intensity * 0.20)
                node.setColorScale(0.78, 0.62, 0.36, 0.10 + intensity * 0.20)


    def load_settings(self) -> dict:
        data = dict(SETTINGS_DEFAULTS)
        try:
            if SETTINGS_PATH.exists():
                loaded = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    for key, default in SETTINGS_DEFAULTS.items():
                        value = loaded.get(key, default)
                        if isinstance(default, bool):
                            data[key] = bool(value)
                        elif isinstance(default, (int, float)):
                            try:
                                data[key] = float(value)
                            except Exception:
                                data[key] = default
                        else:
                            data[key] = str(value)
        except Exception:
            data = dict(SETTINGS_DEFAULTS)
        return data

    def save_settings(self) -> None:
        try:
            SETTINGS_PATH.write_text(json.dumps(self.settings_data, indent=2), encoding="utf-8")
        except Exception:
            pass

    def apply_runtime_settings(self, initial: bool = False) -> None:
        data = self.settings_data
        self.hud_visible = bool(data.get("hud_visible", True))
        self.overlay_visible = bool(data.get("overlay_visible", True))
        self.target_lock_range = float(data.get("target_lock_range", 240.0))
        default_distance = float(data.get("default_camera_distance", 24.5))
        if initial:
            self.target_cam_distance = clamp(default_distance, 10.0, 36.0)
            self.cam_distance = clamp(default_distance, 10.0, 36.0)
        try:
            self.camLens.setFov(float(data.get("camera_fov", 76.0)))
        except Exception:
            pass
        preset = str(data.get("quality_preset", "Balanced"))
        if preset == "Performance":
            data["effect_density"] = min(float(data.get("effect_density", 1.0)), 0.80)
            data["traffic_density"] = min(float(data.get("traffic_density", 1.0)), 0.75)
        elif preset == "Quality":
            data["effect_density"] = max(float(data.get("effect_density", 1.0)), 1.15)
            data["traffic_density"] = max(float(data.get("traffic_density", 1.0)), 1.0)
        if hasattr(self, "overlay") and self.overlay is not None:
            self.overlay.show() if self.overlay_visible else self.overlay.hide()
        if hasattr(self, "hud") and self.hud is not None:
            if self.hud_visible and not getattr(self, "settings_open", False):
                self.hud.show()
            else:
                self.hud.hide()

    def reset_settings_defaults(self) -> None:
        self.settings_data = dict(SETTINGS_DEFAULTS)
        self.apply_runtime_settings(initial=True)
        self.save_settings()
        self.refresh_hud()

    def get_settings_schema(self) -> list[tuple[str, list[dict]]]:
        return [
            ("General", [
                {"key": "hud_visible", "label": "HUD", "type": "bool"},
                {"key": "overlay_visible", "label": "Screen overlay", "type": "bool"},
                {"key": "default_camera_distance", "label": "Default zoom", "type": "float", "min": 16.0, "max": 34.0, "step": 0.5},
                {"key": "target_lock_range", "label": "Target lock range", "type": "float", "min": 120.0, "max": 360.0, "step": 10.0},
                {"key": "__reset__", "label": "Reset to defaults", "type": "action"},
            ]),
            ("Controls", [
                {"key": "mouse_sensitivity", "label": "Mouse yaw sensitivity", "type": "float", "min": 0.04, "max": 0.30, "step": 0.01},
                {"key": "camera_pitch_sensitivity", "label": "Mouse pitch sensitivity", "type": "float", "min": 0.04, "max": 0.24, "step": 0.005},
                {"key": "invert_y", "label": "Invert Y", "type": "bool"},
                {"key": "zoom_step", "label": "Mouse wheel zoom step", "type": "float", "min": 0.4, "max": 3.0, "step": 0.1},
            ]),
            ("Performance", [
                {"key": "quality_preset", "label": "Quality preset", "type": "enum", "options": ["Performance", "Balanced", "Quality"]},
                {"key": "camera_fov", "label": "Field of view", "type": "float", "min": 66.0, "max": 92.0, "step": 1.0},
                {"key": "effect_density", "label": "Power FX density", "type": "float", "min": 0.40, "max": 1.60, "step": 0.05},
                {"key": "traffic_density", "label": "Traffic density", "type": "float", "min": 0.30, "max": 1.50, "step": 0.05},
                {"key": "weather_fx_enabled", "label": "Weather FX", "type": "bool"},
            ]),
        ]

    def get_current_settings_entries(self) -> list[dict]:
        return self.get_settings_schema()[self.settings_tab][1]

    def on_settings_input(self, action: str) -> None:
        if not self.settings_open:
            return
        schema = self.get_settings_schema()
        entries = schema[self.settings_tab][1]
        if action == "tab":
            self.settings_tab = (self.settings_tab + 1) % len(schema)
            self.settings_cursor = 0
        elif action == "up":
            self.settings_cursor = (self.settings_cursor - 1) % len(entries)
        elif action == "down":
            self.settings_cursor = (self.settings_cursor + 1) % len(entries)
        elif action in ("left", "right", "enter", "reset"):
            entry = entries[self.settings_cursor]
            key = entry["key"]
            etype = entry["type"]
            changed = False
            if action == "reset":
                self.reset_settings_defaults()
                self.last_power_text = "Settings reset to defaults"
                return
            if etype == "action":
                if action == "enter":
                    self.reset_settings_defaults()
                    self.last_power_text = "Settings reset to defaults"
                    return
            elif etype == "bool":
                self.settings_data[key] = not bool(self.settings_data.get(key, False))
                changed = True
            elif etype == "float":
                step = float(entry.get("step", 1.0))
                direction = 1.0 if action in ("right", "enter") else -1.0
                value = float(self.settings_data.get(key, entry.get("min", 0.0))) + step * direction
                value = clamp(value, float(entry.get("min", value)), float(entry.get("max", value)))
                decimals = 3 if step < 0.01 else 2 if step < 0.1 else 1 if step < 1.0 else 0
                self.settings_data[key] = round(value, decimals)
                changed = True
            elif etype == "enum":
                options = entry.get("options", [])
                if options:
                    current = str(self.settings_data.get(key, options[0]))
                    try:
                        idx = options.index(current)
                    except ValueError:
                        idx = 0
                    idx = (idx + (1 if action in ("right", "enter") else -1)) % len(options)
                    self.settings_data[key] = options[idx]
                    changed = True
            if changed:
                self.apply_runtime_settings(initial=False)
                self.save_settings()
        self.refresh_settings_menu()
        self.refresh_hud()

    def create_hud(self) -> None:
        self.hud = OnscreenText(
            text="",
            pos=(-1.30, -0.94),
            scale=0.040,
            align=TextNode.ALeft,
            mayChange=True,
            fg=(0.90, 0.98, 0.94, 0.96),
            bg=(0.0, 0.0, 0.0, 0.32),
        )

        cm = CardMaker("settings_backdrop")
        cm.setFrameFullscreenQuad()
        self.settings_backdrop = self.render2d.attachNewNode(cm.generate())
        self.settings_backdrop.setTransparency(TransparencyAttrib.M_alpha)
        self.settings_backdrop.setBin("fixed", 110)
        self.settings_backdrop.setDepthWrite(False)
        self.settings_backdrop.setDepthTest(False)
        self.settings_backdrop.setColorScale(0.02, 0.03, 0.05, 0.82)
        self.settings_backdrop.hide()

        self.settings_title = OnscreenText(
            text="ANTI-HEROES SETTINGS",
            pos=(-1.22, 0.86),
            scale=0.085,
            align=TextNode.ALeft,
            mayChange=True,
            fg=(0.92, 0.98, 1.0, 0.98),
            bg=(0.0, 0.0, 0.0, 0.0),
        )
        self.settings_title.hide()

        self.settings_text = OnscreenText(
            text="",
            pos=(-1.24, 0.72),
            scale=0.045,
            align=TextNode.ALeft,
            mayChange=True,
            fg=(0.86, 0.96, 1.0, 0.98),
            bg=(0.0, 0.0, 0.0, 0.0),
        )
        self.settings_text.hide()
        self.refresh_hud()

    def format_settings_text(self) -> str:
        speed = self.hero_velocity.length()
        profile_name = self.power_profile.get("name", "Procedural")
        mode = self.power_profile.get("mode", "bolt")
        secondary_mode = self.power_profile.get("secondary_mode", "pulse")
        boss_state = "No boss"
        if self.boss is None:
            boss_state = f"Portal opens in {max(0, int(self.boss_spawn_timer + 0.99))}s"
        elif self.boss.get("alive", False):
            boss_state = f"{self.boss.get('name', 'Boss')} | HP {int(self.boss.get('hp', 0))}"
        elif self.boss_spawn_timer > 0.0:
            boss_state = f"Next boss in {max(0, int(self.boss_spawn_timer + 0.99))}s"
        aura_count = sum(1 for npc in self.npcs if float(npc.get("profile", {}).get("aura_glow", 0.0)) > 0.05) + (1 if float(self.power_profile.get("aura_glow", 0.0)) > 0.05 else 0)
        header = []
        for i, name in enumerate(self.settings_tab_names):
            header.append(f"[{name}]" if i == self.settings_tab else name)
        lines = [
            "  ".join(header),
            "TAB switch section | Up/Down select | Left/Right change | Enter toggle | Backspace defaults",
            "",
        ]
        entries = self.get_current_settings_entries()
        for idx, entry in enumerate(entries):
            prefix = ">" if idx == self.settings_cursor else " "
            key = entry["key"]
            etype = entry["type"]
            if etype == "action":
                value = "Press Enter"
            else:
                value = self.settings_data.get(key)
                if etype == "bool":
                    value = "ON" if value else "OFF"
                elif etype == "float":
                    value = f"{float(value):0.3f}" if float(entry.get("step", 1.0)) < 0.01 else f"{float(value):0.2f}"
                else:
                    value = str(value)
            lines.append(f"{prefix} {entry['label']:<26} {value}")
        lines.extend([
            "",
            "Live game status",
            f"  HP {self.player_hp:05.1f}/{self.player_max_hp:05.1f} | Speed {speed:05.1f} | Mode {mode}/{secondary_mode}",
            f"  Current hero {profile_name} | Boss {boss_state}",
            f"  Active auras {aura_count} | Weather {getattr(self, 'time_label', '00:00 Clear')}",
        ])
        return "\n".join(lines)

    def refresh_settings_menu(self) -> None:
        if not getattr(self, "settings_open", False):
            return
        self.settings_text.setText(self.format_settings_text())

    def refresh_hud(self) -> None:
        if self.settings_open:
            self.settings_backdrop.show()
            self.settings_title.show()
            self.settings_text.show()
            self.refresh_settings_menu()
            self.hud.hide()
            return

        speed = self.hero_velocity.length()
        boss_text = "No boss"
        if self.boss is None:
            boss_text = f"Portal {max(0, int(self.boss_spawn_timer + 0.99))}s"
        elif self.boss.get("alive", False):
            boss_text = f"{self.boss.get('name', 'Boss')} {int(self.boss.get('hp', 0))}HP"
        elif self.boss_spawn_timer > 0.0:
            boss_text = f"Next boss {max(0, int(self.boss_spawn_timer + 0.99))}s"
        self.hud.setText(
            f"ESC settings | HP {self.player_hp:05.1f}/{self.player_max_hp:05.1f} | Speed {speed:05.1f} | {boss_text} | {self.last_power_text}"
        )
        if self.hud_visible:
            self.hud.show()
        self.settings_backdrop.hide()
        self.settings_title.hide()
        self.settings_text.hide()


    def make_ground_plane(self) -> None:
        self.ground_plane = NodePath(GeomFactory.make_quad(9000, 9000, 1.0, 1.0))
        self.ground_plane.reparentTo(self.render)
        self.ground_plane.setZ(-10.0)
        self.ground_plane.setColorScale(0.10, 0.10, 0.12, 1.0)
        self.ground_plane.setTwoSided(True)

    def create_surface_water(self) -> None:
        size = self.render_block_radius * 2.55
        water_tex = self.texture_factory.make_overlay("surface_water", 9341)
        shimmer_tex = self.texture_factory.make_overlay("surface_water_shimmer", 9342)
        shadow_tex = self.texture_factory.make_glitch("surface_water_shadow", 9343)

        self.surface_water_root = self.render.attachNewNode("surface_water_root")
        self.surface_water_root.setPos(0.0, 0.0, self.surface_water_z)

        self.surface_water_shadow = NodePath(GeomFactory.make_quad(size, size, 1.0, 1.0))
        self.surface_water_shadow.reparentTo(self.surface_water_root)
        self.surface_water_shadow.setPos(0.0, 0.0, -0.06)
        self.surface_water_shadow.setTexture(shadow_tex)
        self.surface_water_shadow.setTransparency(TransparencyAttrib.M_alpha)
        self.surface_water_shadow.setDepthWrite(False)
        self.surface_water_shadow.setBin("transparent", 32)
        self.surface_water_shadow.setLightOff(True)
        self.surface_water_shadow.setTwoSided(True)
        self.surface_water_shadow.setColorScale(0.02, 0.10, 0.10, 0.18)

        self.surface_water = NodePath(GeomFactory.make_quad(size, size, 1.0, 1.0))
        self.surface_water.reparentTo(self.surface_water_root)
        self.surface_water.setTexture(water_tex)
        self.surface_water.setTransparency(TransparencyAttrib.M_alpha)
        self.surface_water.setDepthWrite(False)
        self.surface_water.setBin("transparent", 34)
        self.surface_water.setLightOff(True)
        self.surface_water.setTwoSided(True)
        self.surface_water.setColorScale(0.08, 0.34, 0.34, 0.36)

        self.surface_water_shimmer = NodePath(GeomFactory.make_quad(size * 0.98, size * 0.98, 1.0, 1.0))
        self.surface_water_shimmer.reparentTo(self.surface_water_root)
        self.surface_water_shimmer.setPos(0.0, 0.0, 0.035)
        self.surface_water_shimmer.setTexture(shimmer_tex)
        self.surface_water_shimmer.setTransparency(TransparencyAttrib.M_alpha)
        self.surface_water_shimmer.setDepthWrite(False)
        self.surface_water_shimmer.setBin("transparent", 35)
        self.surface_water_shimmer.setLightOff(True)
        self.surface_water_shimmer.setTwoSided(True)
        self.surface_water_shimmer.setColorScale(0.18, 0.60, 0.56, 0.12)

        self.surface_water_foam = NodePath(GeomFactory.make_quad(size * 1.01, size * 1.01, 1.0, 1.0))
        self.surface_water_foam.reparentTo(self.surface_water_root)
        self.surface_water_foam.setPos(0.0, 0.0, 0.055)
        self.surface_water_foam.setTexture(water_tex)
        self.surface_water_foam.setTransparency(TransparencyAttrib.M_alpha)
        self.surface_water_foam.setDepthWrite(False)
        self.surface_water_foam.setBin("transparent", 36)
        self.surface_water_foam.setLightOff(True)
        self.surface_water_foam.setTwoSided(True)
        self.surface_water_foam.setColorScale(0.42, 0.82, 0.70, 0.06)

    def update_surface_water(self, dt: float) -> None:
        if not hasattr(self, "surface_water_root"):
            return
        t = globalClock.getFrameTime()
        base_alpha = 0.72 + 0.10 * math.sin(t * 0.22)
        self.surface_water_root.setPos(0.0, 0.0, self.surface_water_z + math.sin(t * 0.42) * 0.035)
        self.surface_water_shadow.setR(t * 0.65)
        self.surface_water.setR(-t * 1.6)
        self.surface_water_shimmer.setR(t * 2.2)
        self.surface_water_foam.setR(-t * 1.1)
        self.surface_water.setColorScale(0.06, 0.30 + 0.03 * math.sin(t * 0.5), 0.32 + 0.04 * math.cos(t * 0.45), 0.28 + 0.04 * math.sin(t * 0.22))
        self.surface_water_shimmer.setColorScale(0.18, 0.58, 0.54, 0.08 + 0.03 * math.sin(t * 1.8))
        self.surface_water_foam.setColorScale(0.38, 0.84, 0.72, 0.04 + 0.02 * math.sin(t * 1.2 + 1.5))

    def clamp_to_render_block(self, pos: Vec3, margin: float = 4.0) -> Vec3:
        limit = max(24.0, self.render_block_radius - margin)
        flat = Vec3(pos.x, pos.y, 0.0)
        dist = flat.length()
        if dist > limit and dist > 1e-6:
            flat.normalize()
            pos.x = flat.x * limit
            pos.y = flat.y * limit
        return pos

    def clear_city(self) -> None:
        if not self.city_root.isEmpty():
            self.city_root.removeNode()
        self.city_root = self.render.attachNewNode("city_root")
        self.ghost_nodes.clear()
        self.dynamic_signs.clear()
        self.structure_targets = [t for t in self.structure_targets if t.get("zone") not in ("city", "outskirts")]
        self.clear_outskirts()
        self.clear_traffic()

    def create_ground_launchers(self) -> None:
        if hasattr(self, "launcher_root") and not self.launcher_root.isEmpty():
            self.launcher_root.removeNode()
        self.launcher_root = self.render.attachNewNode("launcher_root")
        self.ground_launchers = []
        radius = self.render_block_radius * 0.92
        count = 8
        for i in range(count):
            ang = (i / count) * math.tau
            pos = Vec3(math.cos(ang) * radius, math.sin(ang) * radius, 0.0)
            root = self.launcher_root.attachNewNode(f"ground_launcher_{i}")
            root.setPos(pos)
            base = _SMOOTH_FACTORY.box(f"launcher_base_{i}", 1.1, 1.1, 0.8)
            base.reparentTo(root)
            base.setPos(0, 0, 0.4)
            base.setColorScale(0.18, 0.18, 0.20, 1.0)
            turret = _SMOOTH_FACTORY.box(f"launcher_turret_{i}", 0.56, 0.82, 0.32)
            turret.reparentTo(root)
            turret.setPos(0, 0, 1.02)
            turret.setColorScale(0.32, 0.30, 0.28, 1.0)
            muzzle = _SMOOTH_FACTORY.box(f"launcher_muzzle_{i}", 0.18, 0.42, 0.12)
            muzzle.reparentTo(turret)
            muzzle.setPos(0, 0.62, 0.02)
            muzzle.setLightOff(True)
            muzzle.setColorScale(1.0, 0.48, 0.20, 0.78)
            self.ground_launchers.append({"root": root, "turret": turret, "muzzle": muzzle, "cooldown": i * 0.25, "phase": ang})

    def update_ground_launchers(self, dt: float) -> None:
        self.launcher_alert_timer = max(0.0, self.launcher_alert_timer - dt)
        if self.launcher_alert_timer <= 0.0:
            self.launcher_alert_team = "neutral"
        if not self.ground_launchers:
            return

        for i, launcher in enumerate(self.ground_launchers):
            launcher["cooldown"] = max(0.0, launcher["cooldown"] - dt)
            root = launcher["root"]
            turret = launcher["turret"]
            target_pos = None
            if self.launcher_alert_timer > 0.0 and self.launcher_alert_team != "neutral":
                if self.launcher_alert_team == "ally":
                    target_pos = self.hero_pos + Vec3(0, 0, 1.2)
                    ally_targets = [npc for npc in self.npcs if not npc.get("dead", False) and str(npc.get("team")) == "ally"]
                    best = self.choose_closest_npc(root.getPos(), ally_targets)
                    if best is not None and (best["pos"] - root.getPos()).lengthSquared() < (target_pos - root.getPos()).lengthSquared():
                        target_pos = best["pos"] + Vec3(0, 0, 1.2)
                else:
                    matches = [npc for npc in self.npcs if not npc.get("dead", False) and str(npc.get("team")) == self.launcher_alert_team]
                    best = self.choose_closest_npc(root.getPos(), matches)
                    if best is not None:
                        target_pos = best["pos"] + Vec3(0, 0, 1.2)

            if target_pos is None:
                yaw = math.degrees(launcher["phase"] + math.sin(globalClock.getFrameTime() * 0.2 + i) * 0.15) + 180.0
                turret.setH(lerp_angle_deg(turret.getH(), yaw, dt * 1.8))
                continue

            vec = target_pos - (root.getPos() + Vec3(0, 0, 1.0))
            flat = Vec3(vec.x, vec.y, 0)
            if flat.lengthSquared() > 1e-6:
                flat.normalize()
                turret.setH(lerp_angle_deg(turret.getH(), math.degrees(math.atan2(flat.x, flat.y)), dt * 4.0))
            dist = max(1.0, vec.length())
            if dist < 260.0 and launcher["cooldown"] <= 0.0:
                muzzle_pos = launcher["muzzle"].getPos(self.render)
                dir_vec = target_pos - muzzle_pos
                if dir_vec.lengthSquared() > 1e-6:
                    dir_vec.normalize()
                    self.spawn_projectile(muzzle_pos, dir_vec, 72.0, True, kind_override="missile", color_override=(1.0, 0.52, 0.16, 1.0), scale_mul=0.86, life_mul=1.55, owner=f"launcher:{self.launcher_alert_team}", owner_heading=turret.getH(self.render))
                    self.spawn_power_fx("burst", muzzle_pos, (1.0, 0.56, 0.18, 0.84), 0.44)
                    launcher["cooldown"] = 2.6 + i * 0.08

    def clear_outskirts(self) -> None:
        for key in list(self.chunk_team_map.keys()):
            self.remove_chunk_npcs(key)
        self.chunk_team_map.clear()
        for node in self.outer_chunks.values():
            if not node.isEmpty():
                node.removeNode()
        self.outer_chunks.clear()
        if not self.outskirts_root.isEmpty():
            self.outskirts_root.removeNode()
        self.outskirts_root = self.render.attachNewNode("outskirts_root")
        self.current_stream_chunk = None
        self.structure_targets = [t for t in self.structure_targets if t.get("zone") != "outskirts"]

    def rebuild_city(self) -> None:
        self.seed = random.randint(1, 999999)
        self.clear_city()
        self.build_city(self.seed)
        self.create_traffic_system()
        self.ensure_outskirts(force=True)

    def build_city(self, seed: int) -> None:
        rnd = random.Random(seed)
        self.structure_targets = [t for t in self.structure_targets if t.get("zone") not in ("city", "outskirts")]
        block = self.city_block
        radius = self.city_radius
        facade_colors = [
            ((58, 52, 44), (246, 198, 128)),
            ((52, 46, 40), (225, 182, 118)),
            ((64, 56, 48), (255, 214, 150)),
        ]
        facade_textures = []
        for i, (base_rgb, accent_rgb) in enumerate(facade_colors):
            facade_textures.append(self.texture_factory.make_facade(f"facade_{i}", seed + i * 17, base_rgb, accent_rgb))
        roof_tex = self.texture_factory.make_roof(f"roof_{seed}", seed + 999)
        glitch_tex = self.texture_factory.make_glitch(f"glitch_{seed}", seed + 777)

        for gx in range(-radius, radius + 1):
            for gy in range(-radius, radius + 1):
                wx = gx * block
                wy = gy * block

                corridor = abs(gx) <= 1 or abs(abs(gx) - 2) == 0  # keep aerial traffic spaces open left/right
                plaza = abs(gx) <= 1 and abs(gy) <= 1
                edge_bias = max(abs(gx), abs(gy)) / max(1, radius)

                # sandy lot / dune base
                dune_scale = 0.18 + rnd.random() * 0.10
                dune = NodePath(GeomFactory.make_quad(block, block, 1.0, 1.0))
                dune.reparentTo(self.city_root)
                dune.setPos(wx, wy, 0.030)
                dune.setColorScale(0.42 + dune_scale, 0.31 + dune_scale * 0.6, 0.18 + dune_scale * 0.4, 1.0)
                dune.setTwoSided(True)

                # low dunes / mounds
                if rnd.random() < (0.56 if corridor else 0.28):
                    hw = rnd.uniform(12.0, 24.0)
                    hd = rnd.uniform(12.0, 24.0)
                    hh = rnd.uniform(2.0, 8.0 if corridor else 6.0)
                    mound = NodePath(GeomFactory.make_pyramid(hw, hd, hh, 1.0, 1.0))
                    mound.reparentTo(self.city_root)
                    mound.setPos(wx + rnd.uniform(-8.0, 8.0), wy + rnd.uniform(-8.0, 8.0), -0.08)
                    mound.setH(rnd.uniform(0, 360))
                    mound.setColorScale(0.36, 0.27, 0.17, 1.0)
                    mound.setTexture(roof_tex)
                    self.register_pyramid_target(mound, hw, hd, hh, "city", "dune")

                if corridor or plaza:
                    continue

                if rnd.random() < 0.18:
                    continue  # more open ground for performance and desert feel

                w = rnd.uniform(16.0, 28.0)
                d = rnd.uniform(16.0, 28.0)
                h = rnd.uniform(46.0, 180.0) * (1.08 - edge_bias * 0.16)
                if rnd.random() < 0.08 and edge_bias < 0.72:
                    h *= rnd.uniform(1.15, 1.45)
                tex = rnd.choice(facade_textures)

                building = NodePath(GeomFactory.make_box(w, d, h, max(1.0, w / 16.0), max(2.0, h / 32.0)))
                building.reparentTo(self.city_root)
                building.setPos(wx + rnd.uniform(-4.0, 4.0), wy + rnd.uniform(-4.0, 4.0), 0)
                building.setH(rnd.choice([0, 90, 180, 270]))
                building.setTexture(tex)
                building.setColorScale(0.92, 0.88, 0.82, 1.0)
                self.register_box_target(building, w, d, h, "city", "building")

                roof = NodePath(GeomFactory.make_quad(w * 0.92, d * 0.92, max(1.0, w / 12.0), max(1.0, d / 12.0)))
                roof.reparentTo(building)
                roof.setZ(h + 0.08)
                roof.setTexture(roof_tex)
                roof.setColorScale(0.52, 0.44, 0.34, 1.0)
                roof.setTwoSided(True)

                dist_index = abs(gx) + abs(gy)
                if rnd.random() < (0.10 if dist_index < radius * 1.15 else 0.03):
                    ghost = building.copyTo(self.city_root)
                    ghost.setShader(self.shader)
                    ghost.setShaderInput("u_phase", rnd.random())
                    ghost.setShaderInput("u_amp", rnd.uniform(0.12, 0.34))
                    ghost.setShaderInput("u_tint", Vec4(0.72 + rnd.random() * 0.12, 0.58 + rnd.random() * 0.08, 0.28 + rnd.random() * 0.06, 0.08 + rnd.random() * 0.04))
                    ghost.setTransparency(TransparencyAttrib.M_alpha)
                    ghost.setDepthWrite(False)
                    ghost.setBin("transparent", 20)
                    ghost.setColorScale(1, 1, 1, 0.10)
                    ghost.setPos(building.getPos() + Vec3(rnd.uniform(-0.6, 0.6), rnd.uniform(-0.6, 0.6), rnd.uniform(0.0, 1.0)))
                    self.ghost_nodes.append(ghost)

                if rnd.random() < 0.03 and dist_index < radius * 1.1:
                    self.add_sign(building, glitch_tex, rnd)

                if self.external_model_paths and rnd.random() < 0.04 and edge_bias > 0.45:
                    self.spawn_external_model_prop(
                        self.city_root,
                        Vec3(wx + rnd.uniform(-10.0, 10.0), wy + rnd.uniform(-10.0, 10.0), 0.04),
                        rnd,
                        zone="city",
                    )

        self.add_collapse_core(glitch_tex, rnd)


    def add_sign(self, building: NodePath, tex: Texture, rnd: random.Random) -> None:
        cm = CardMaker("sign")
        cm.setFrame(-8, 8, -16, 16)
        sign = building.attachNewNode(cm.generate())
        sign.setBillboardAxis()
        sign.setPos(rnd.uniform(-4, 4), rnd.choice([-1, 1]) * (building.getBounds().getRadius() * 0.3), rnd.uniform(18, max(24, building.getBounds().getRadius() * 1.2)))
        sign.setScale(rnd.uniform(0.8, 1.6))
        sign.setTexture(tex)
        sign.setTransparency(TransparencyAttrib.M_alpha)
        sign.setDepthWrite(False)
        sign.setBin("transparent", 30)
        sign.setColorScale(0.7, 1.0, 0.6, 0.32)
        self.dynamic_signs.append(sign)

    def add_collapse_core(self, tex: Texture, rnd: random.Random) -> None:
        core = self.city_root.attachNewNode("collapse_core")
        for ring in range(3):
            radius = 24 + ring * 16
            count = 14 + ring * 5
            for i in range(count):
                ang = (i / count) * math.tau
                cm = CardMaker(f"core_panel_{ring}_{i}")
                cm.setFrame(-2.2, 2.2, -18, 18)
                panel = core.attachNewNode(cm.generate())
                panel.setTexture(tex)
                panel.setTransparency(TransparencyAttrib.M_alpha)
                panel.setDepthWrite(False)
                panel.setBin("transparent", 25)
                panel.setPos(math.cos(ang) * radius, math.sin(ang) * radius, 26 + ring * 16)
                panel.lookAt(0, 0, 32)
                panel.setScale(1.0 + ring * 0.18, 1.0, 1.5 + ring * 0.28)
                tint = rnd.choice([
                    Vec4(0.18, 1.00, 0.40, 0.14),
                    Vec4(0.92, 0.95, 0.22, 0.10),
                    Vec4(0.85, 1.00, 0.85, 0.12),
                ])
                panel.setColorScale(tint)
                self.dynamic_signs.append(panel)

        hub = NodePath(GeomFactory.make_box(22, 22, 68, 2, 6))
        hub.reparentTo(core)
        hub.setPos(0, 0, 0)
        hub.setTexture(self.texture_factory.make_facade("core_facade", self.seed + 144, (34, 42, 38), (58, 255, 118)))
        hub.setColorScale(0.85, 0.95, 1.05, 1.0)

        hub_ghost = hub.copyTo(core)
        hub_ghost.setShader(self.shader)
        hub_ghost.setShaderInput("u_phase", 0.65)
        hub_ghost.setShaderInput("u_amp", 1.1)
        hub_ghost.setShaderInput("u_tint", Vec4(0.18, 1.0, 0.40, 0.16))
        hub_ghost.setTransparency(TransparencyAttrib.M_alpha)
        hub_ghost.setDepthWrite(False)
        hub_ghost.setBin("transparent", 22)
        self.ghost_nodes.append(hub_ghost)


    def build_outskirts_chunk(self, cx: int, cy: int) -> NodePath | None:
        chunk_size = self.outskirts_chunk_size
        center_x = cx * chunk_size
        center_y = cy * chunk_size
        dist = math.hypot(center_x, center_y)
        if dist < self.city_world_radius + chunk_size * 0.20:
            return None

        rnd = random.Random(self.seed * 1000003 + cx * 92821 + cy * 68917)
        chunk = self.outskirts_root.attachNewNode(f"chunk_{cx}_{cy}")

        house_facades = [
            self.texture_factory.make_facade("desert_house_a", 4401, (92, 78, 62), (255, 214, 160)),
            self.texture_factory.make_facade("desert_house_b", 4402, (78, 68, 56), (238, 210, 180)),
            self.texture_factory.make_facade("desert_house_c", 4403, (68, 60, 50), (228, 198, 150)),
        ]
        roof_tex = self.texture_factory.make_roof("desert_roof", 4404)

        biome_roll = rnd.random()
        if biome_roll < 0.40:
            biome = "open_desert"
        elif biome_roll < 0.74:
            biome = "hills"
        elif biome_roll < 0.88:
            biome = "ruins"
        else:
            biome = "settlement"

        hill_count = 0
        if biome == "open_desert":
            hill_count = rnd.randint(3, 5)
        elif biome == "hills":
            hill_count = rnd.randint(5, 7)
        elif biome == "ruins":
            hill_count = rnd.randint(3, 4)
        else:
            hill_count = rnd.randint(2, 3)

        for _ in range(hill_count):
            hw = rnd.uniform(34.0, 86.0)
            hd = rnd.uniform(34.0, 92.0)
            hh = rnd.uniform(5.0, 18.0 if biome != "hills" else 28.0)
            hx = center_x + rnd.uniform(-chunk_size * 0.45, chunk_size * 0.45)
            hy = center_y + rnd.uniform(-chunk_size * 0.45, chunk_size * 0.45)
            hill = NodePath(GeomFactory.make_pyramid(hw, hd, hh, max(1.0, hw / 10.0), max(1.0, hd / 10.0)))
            hill.reparentTo(chunk)
            hill.setPos(hx, hy, -0.08)
            hill.setH(rnd.uniform(0, 360))
            hill.setColorScale(0.40, 0.31 + rnd.random() * 0.03, 0.18, 1.0)
            hill.setTexture(roof_tex)
            self.register_pyramid_target(hill, hw, hd, hh, "outskirts", "hill")

        if biome == "open_desert":
            build_count = rnd.randint(0, 1)
        elif biome == "hills":
            build_count = rnd.randint(0, 2)
        elif biome == "ruins":
            build_count = rnd.randint(1, 3)
        else:
            build_count = rnd.randint(2, 3)

        for _ in range(build_count):
            structure_roll = rnd.random()
            if structure_roll < 0.58:
                kind = "house"
            elif structure_roll < 0.86:
                kind = "warehouse"
            else:
                kind = "tower"

            if kind == "house":
                w = rnd.uniform(10.0, 16.0)
                d = rnd.uniform(10.0, 16.0)
                h = rnd.uniform(5.0, 9.0)
            elif kind == "warehouse":
                w = rnd.uniform(18.0, 26.0)
                d = rnd.uniform(14.0, 20.0)
                h = rnd.uniform(5.0, 8.0)
            else:
                w = rnd.uniform(10.0, 16.0)
                d = rnd.uniform(10.0, 16.0)
                h = rnd.uniform(15.0, 24.0)

            spread = 0.28 if biome == "settlement" else 0.36
            ox = rnd.uniform(-chunk_size * spread, chunk_size * spread)
            oy = rnd.uniform(-chunk_size * spread, chunk_size * spread)

            pad = NodePath(GeomFactory.make_quad(w + 3.2, d + 3.2, 1, 1))
            pad.reparentTo(chunk)
            pad.setPos(center_x + ox, center_y + oy, 0.044)
            pad.setColorScale(0.50, 0.40, 0.28, 1.0)
            pad.setTwoSided(True)

            building = NodePath(GeomFactory.make_box(w, d, h, max(1.0, w / 4.0), max(1.0, h / 3.0)))
            building.reparentTo(chunk)
            building.setPos(center_x + ox, center_y + oy, 0)
            building.setH(rnd.choice([0, 90, 180, 270]))
            building.setTexture(rnd.choice(house_facades))
            tint = 0.84 + rnd.random() * 0.12
            building.setColorScale(tint, tint * 0.94, tint * 0.86, 1.0)
            self.register_box_target(building, w, d, h, "outskirts", kind)

            roof = NodePath(GeomFactory.make_quad(w * 0.95, d * 0.95, max(1.0, w / 4.0), max(1.0, d / 4.0)))
            roof.reparentTo(building)
            roof.setZ(h + 0.06)
            roof.setTexture(roof_tex)
            roof.setColorScale(0.40, 0.32, 0.26, 1.0)
            roof.setTwoSided(True)

        if dist > self.city_world_radius + chunk_size * 1.15 and rnd.random() < 0.42:
            pyramid_count = 1 if rnd.random() < 0.72 else 2
            for _ in range(pyramid_count):
                pw = rnd.uniform(22.0, 40.0)
                pd = pw * rnd.uniform(0.92, 1.10)
                ph = rnd.uniform(20.0, 48.0)
                px = center_x + rnd.uniform(-chunk_size * 0.44, chunk_size * 0.44)
                py = center_y + rnd.uniform(-chunk_size * 0.44, chunk_size * 0.44)
                pyramid = NodePath(GeomFactory.make_pyramid(pw, pd, ph, 2.0, 2.0))
                pyramid.reparentTo(chunk)
                pyramid.setPos(px, py, 0.0)
                pyramid.setColorScale(0.10, 0.10, 0.12, 1.0)
                pyramid.setTexture(roof_tex)
                pyramid.setH(rnd.uniform(0.0, 360.0))
                self.register_pyramid_target(pyramid, pw, pd, ph, "outskirts", "pyramid")

        if self.external_model_paths and rnd.random() < 0.24:
            prop_count = 1 if rnd.random() < 0.76 else 2
            for _ in range(prop_count):
                self.spawn_external_model_prop(
                    chunk,
                    Vec3(center_x + rnd.uniform(-chunk_size * 0.30, chunk_size * 0.30), center_y + rnd.uniform(-chunk_size * 0.30, chunk_size * 0.30), 0.04),
                    rnd,
                    zone="outskirts",
                )

        self.spawn_world_team_for_chunk((cx, cy), center_x, center_y, rnd, biome)

        if chunk.getNumChildren() == 0:
            chunk.removeNode()
            return None
        return chunk


    def ensure_outskirts(self, force: bool = False) -> None:
        if self.outer_chunks:
            self.clear_outskirts()
        self.current_stream_chunk = None
        return


    def build_traffic_car_model(self, parent: NodePath, seed: int, color: tuple[float, float, float, float]) -> NodePath:
        rnd = random.Random(seed)
        root = parent.attachNewNode(f"traffic_car_{seed}")

        body_tex = self.texture_factory.make_roof("traffic_body", 5210 + (self.seed % 1000))

        body = NodePath(GeomFactory.make_box(3.0, 8.4, 1.0, 1, 1))
        body.reparentTo(root)
        body.setZ(0.35)
        body.setTexture(body_tex)
        body.setColorScale(color[0] * 0.80, color[1] * 0.85, color[2] * 0.88, 1.0)

        cockpit = NodePath(GeomFactory.make_box(1.85, 3.4, 0.78, 1, 1))
        cockpit.reparentTo(root)
        cockpit.setPos(0.0, 0.55, 0.95)
        cockpit.setColorScale(0.12, 0.14, 0.18, 1.0)

        nose = NodePath(GeomFactory.make_box(1.55, 1.8, 0.44, 1, 1))
        nose.reparentTo(root)
        nose.setPos(0.0, 4.15, 0.46)
        nose.setColorScale(color[0] * 0.92, color[1] * 0.96, color[2], 1.0)

        tail = NodePath(GeomFactory.make_box(1.45, 1.7, 0.50, 1, 1))
        tail.reparentTo(root)
        tail.setPos(0.0, -4.1, 0.52)
        tail.setColorScale(color[0] * 0.75, color[1] * 0.82, color[2] * 0.82, 1.0)

        wing_span = 2.45 + rnd.uniform(-0.18, 0.18)
        for sx in (-1, 1):
            wing = NodePath(GeomFactory.make_box(wing_span, 2.6, 0.18, 1, 1))
            wing.reparentTo(root)
            wing.setPos(2.2 * sx, 0.2, 0.42)
            wing.setColorScale(color[0] * 0.72, color[1] * 0.78, color[2] * 0.80, 1.0)

            engine = NodePath(GeomFactory.make_box(0.64, 1.7, 0.54, 1, 1))
            engine.reparentTo(root)
            engine.setPos(2.2 * sx, -2.25, 0.40)
            engine.setColorScale(0.18, 0.22, 0.20, 1.0)

            glow = NodePath(GeomFactory.make_box(0.30, 0.35, 0.24, 1, 1))
            glow.reparentTo(root)
            glow.setPos(2.2 * sx, -3.18, 0.40)
            glow.setColorScale(color[0] * 1.45, color[1] * 1.45, color[2] * 1.45, 1.0)
            glow.setLightOff(True)
            glow.setTransparency(TransparencyAttrib.M_alpha)
            glow.setBin("transparent", 24)

        root.setPythonTag("thrusters", root.findAllMatches("**/+GeomNode"))
        return root


    def clear_traffic(self) -> None:
        for car in getattr(self, "traffic_cars", []):
            node = car.get("node")
            if node is not None and not node.isEmpty():
                node.removeNode()
        self.traffic_cars = []
        self.traffic_guides = []
        if hasattr(self, "traffic_root") and not self.traffic_root.isEmpty():
            self.traffic_root.removeNode()
        self.traffic_root = self.render.attachNewNode("traffic_root")

    def create_traffic_system(self) -> None:
        self.clear_traffic()
        self.traffic_route_len = max(self.city_world_radius * 2.0, 640.0)

        guide_tex = self.texture_factory.make_glitch("traffic_guide", 15001 + self.seed)
        lane_specs = [
            {"lane": 0, "x": -104.0, "dir": 1.0, "alt": 20.0, "color": (0.55, 1.0, 0.72, 0.14)},
            {"lane": 1, "x": -78.0, "dir": -1.0, "alt": 28.0, "color": (0.82, 1.0, 0.90, 0.12)},
            {"lane": 2, "x": 78.0, "dir": 1.0, "alt": 24.0, "color": (0.55, 1.0, 0.72, 0.14)},
            {"lane": 3, "x": 104.0, "dir": -1.0, "alt": 32.0, "color": (0.82, 1.0, 0.90, 0.12)},
        ]
        self.traffic_lane_specs = lane_specs

        for spec in lane_specs:
            guide = NodePath(GeomFactory.make_quad(10.0, self.traffic_route_len * 2.0, 1.0, max(1.0, self.traffic_route_len / 18.0)))
            guide.reparentTo(self.traffic_root)
            guide.setPos(spec["x"], 0.0, spec["alt"] - 2.7)
            guide.setTexture(guide_tex)
            guide.setTransparency(TransparencyAttrib.M_alpha)
            guide.setDepthWrite(False)
            guide.setBin("transparent", 12)
            guide.setColorScale(*spec["color"])
            guide.setTwoSided(True)
            self.traffic_guides.append(guide)

            cars_per_lane = max(1, int(round(4 * float(self.settings_data.get("traffic_density", 1.0)))))
            spacing = (self.traffic_route_len * 2.0) / cars_per_lane
            for i in range(cars_per_lane):
                seed = self.seed * 101 + spec["lane"] * 17 + i * 13
                hue_shift = 0.80 + (0.06 * (i % 3))
                tint = (
                    min(1.0, spec["color"][0] * (4.3 * hue_shift)),
                    min(1.0, spec["color"][1] * (1.08 * hue_shift)),
                    min(1.0, spec["color"][2] * (1.02 * hue_shift)),
                    1.0,
                )
                node = self.build_traffic_car_model(self.traffic_root, seed, tint)
                lane_y = -self.traffic_route_len + spacing * (i + 0.22 * random.Random(seed).random())
                if spec["dir"] < 0:
                    lane_y *= -1.0
                node.setPos(spec["x"], lane_y, spec["alt"] + random.Random(seed + 3).uniform(-1.1, 1.1))
                node.setH(0.0 if spec["dir"] > 0 else 180.0)

                self.traffic_cars.append({
                    "node": node,
                    "lane": spec["lane"],
                    "lane_x": spec["x"],
                    "dir": spec["dir"],
                    "alt": spec["alt"],
                    "y": lane_y,
                    "speed": random.Random(seed + 5).uniform(34.0, 52.0),
                    "cruise": random.Random(seed + 7).uniform(34.0, 52.0),
                    "lateral": 0.0,
                    "vertical": 0.0,
                    "target_lateral": 0.0,
                    "target_vertical": 0.0,
                    "active": True,
                    "respawn": 0.0,
                    "radius": 4.2,
                    "bob_phase": random.Random(seed + 9).random() * math.tau,
                    "bob_speed": random.Random(seed + 11).uniform(1.4, 2.8),
                    "slot": i,
                })

    def destroy_traffic_car(self, car: dict, strong: bool = False) -> None:
        if not car.get("active", False):
            return
        pos = Vec3(car["node"].getPos())
        car["active"] = False
        car["respawn"] = 3.8 + random.random() * 3.4
        car["node"].hide()

        primary = self.power_profile.get("primary", (0.30, 1.0, 0.44, 1.0))
        secondary = self.power_profile.get("secondary", (0.95, 0.75, 0.22, 1.0))
        self.play_sfx("explosion_big" if strong else "explosion_small", volume=0.62 if strong else 0.50, rate=0.96 + random.random() * 0.08)
        self.spawn_power_fx("burst", pos, secondary, 1.25 if strong else 0.92)
        self.spawn_power_fx("smoke", pos + Vec3(0, 0, 0.6), (0.46, 0.52, 0.58, 0.70), 0.86 if strong else 0.64)
        self.spawn_power_fx("ring", pos + Vec3(0, 0, 0.25), (1.0, 0.52, 0.20, 0.55), 1.55 if strong else 1.08)
        for _ in range(3 if strong else 2):
            offset = Vec3(random.uniform(-1.8, 1.8), random.uniform(-1.8, 1.8), random.uniform(-0.4, 1.4))
            self.spawn_power_fx("slash", pos + offset, primary, 0.55 if strong else 0.40)

    def hit_traffic_by_projectile(self, pos: Vec3, strong: bool) -> bool:
        hit_radius = 5.8 if strong else 4.2
        for car in self.traffic_cars:
            if not car.get("active", False):
                continue
            delta = car["node"].getPos() - pos
            if delta.lengthSquared() <= (car["radius"] + hit_radius) ** 2:
                self.destroy_traffic_car(car, strong=strong)
                return True
        return False

    def update_traffic(self, dt: float) -> None:
        if not self.traffic_cars:
            return

        t = globalClock.getFrameTime()
        route_wrap = self.traffic_route_len * 2.0
        lane_groups: dict[int, list[dict]] = {}
        for car in self.traffic_cars:
            if not car.get("active", False):
                car["respawn"] -= dt
                if car["respawn"] <= 0.0:
                    car["active"] = True
                    car["speed"] = car["cruise"]
                    car["lateral"] = 0.0
                    car["vertical"] = 0.0
                    car["y"] = -self.traffic_route_len if car["dir"] > 0 else self.traffic_route_len
                    car["node"].setPos(car["lane_x"], car["y"], car["alt"])
                    car["node"].setH(0.0 if car["dir"] > 0 else 180.0)
                    car["node"].show()
                continue
            if (car["node"].getPos() - self.hero_pos).lengthSquared() < 420.0 * 420.0:
                lane_groups.setdefault(car["lane"], []).append(car)
            else:
                car["target_lateral"] = 0.0
                car["target_vertical"] = 0.0
                car["speed"] = lerp(car["speed"], car["cruise"], dt * 1.4)
        for lane, cars in lane_groups.items():
            if not cars:
                continue
            direction = cars[0]["dir"]
            cars.sort(key=lambda c: c["y"], reverse=(direction < 0))
            count = len(cars)
            for index, car in enumerate(cars):
                target_speed = car["cruise"]
                target_lateral = 0.0
                target_vertical = 0.0
                if count > 1:
                    ahead = cars[(index + 1) % count]
                    gap = (ahead["y"] - car["y"]) if direction > 0 else (car["y"] - ahead["y"])
                    if gap <= 0.0:
                        gap += route_wrap
                    if gap < 52.0:
                        target_speed = min(target_speed, ahead["speed"] * 0.94)
                    if gap < 30.0:
                        target_speed = min(target_speed, ahead["speed"] * 0.72)
                        target_vertical = max(target_vertical, 4.8)
                        target_lateral = 4.8 if (car["slot"] % 2 == 0) else -4.8
                car_pos = Vec3(car["lane_x"] + car["lateral"], car["y"], car["alt"] + car["vertical"])
                hero_delta = car_pos - self.hero_pos
                if abs(hero_delta.y) < 34.0 and abs(hero_delta.x) < 30.0 and abs(hero_delta.z) < 18.0:
                    away = 1.0 if hero_delta.x >= 0.0 else -1.0
                    if abs(hero_delta.x) < 1.0:
                        away = 1.0 if car["lane_x"] >= 0.0 else -1.0
                    target_lateral = away * 8.5
                    target_vertical = max(target_vertical, 9.0)
                    target_speed = min(target_speed, car["cruise"] * 0.50)
                car["target_lateral"] = target_lateral
                car["target_vertical"] = target_vertical
                car["speed"] = lerp(car["speed"], target_speed, dt * 2.4)
        for car in self.traffic_cars:
            if not car.get("active", False):
                continue
            car["lateral"] = lerp(car["lateral"], car["target_lateral"], dt * 2.4)
            car["vertical"] = lerp(car["vertical"], car["target_vertical"], dt * 2.0)
            car["y"] += car["dir"] * car["speed"] * dt
            if car["y"] > self.traffic_route_len:
                car["y"] -= route_wrap
            elif car["y"] < -self.traffic_route_len:
                car["y"] += route_wrap
            bob = math.sin(t * car["bob_speed"] + car["bob_phase"]) * 0.7
            x = car["lane_x"] + car["lateral"]
            z = car["alt"] + car["vertical"] + bob
            car["node"].setPos(x, car["y"], z)
            car["node"].setHpr(0.0 if car["dir"] > 0 else 180.0, -car["vertical"] * 0.35, -car["lateral"] * 1.25)
        for i, guide in enumerate(self.traffic_guides):
            pulse = 0.08 + 0.05 * (0.5 + 0.5 * math.sin(t * (2.2 + i * 0.3) + i))
            r, g, b, _ = self.traffic_lane_specs[i]["color"]
            guide.setColorScale(r + pulse, g + pulse * 0.4, b + pulse * 0.6, max(0.06, self.traffic_lane_specs[i]["color"][3] + pulse * 0.35))


    def spawn_npc_actor(self, profile: dict, pos: Vec3, home_anchor: Vec3, formation_slot: int, team: str, group_anchor: Vec3 | None = None, spawn_chunk: tuple[int, int] | None = None, state: str | None = None) -> dict:
        idx = self.next_npc_index
        self.next_npc_index += 1

        root = self.npc_root.attachNewNode(f"npc_root_{idx}")
        visual = build_sheet_style_hero(root)
        visual.setScale(float(profile["scale"]))
        parts = visual.getPythonTag("parts") or {}
        base_hprs = visual.getPythonTag("base_hprs") or {}
        emissives = visual.getPythonTag("emissives") or []
        for node in (visual.getPythonTag("trails") or []):
            node.hide()
        trails = []
        capes = []
        cape_geos = []
        for node in visual.getPythonTag("cape_geos") or []:
            node.hide()
        aura_shell = self.create_actor_aura_shell(root, visual)
        visual.setPythonTag("aura_shell", aura_shell)
        self.apply_profile_to_actor(visual, emissives, profile)
        self.customize_npc_helmet({"parts": parts, "profile": profile})
        self.add_npc_back_pattern({"index": idx, "visual": visual, "profile": profile})
        xray_shell = self.create_xray_shell(root, visual)
        head_nodes = [n for n in [visual.find("**/helmet_geo"), visual.find("**/jaw_geo"), visual.find("**/visor_geo"), visual.find("**/eye_l"), visual.find("**/eye_r")] if not n.isEmpty()]
        propulsion = self.create_propulsion_rig(root, parts, float(profile["scale"]), profile.get("primary", (0.3,1,0.44,1)), profile.get("secondary", (0.8,1,0.9,1)), style=profile.get("mobility_style", "jetpack" if (idx % 2 == 0) else "thrusters"))
        self.set_propulsion_colors(propulsion, profile.get("primary", (0.3,1,0.44,1)), profile.get("secondary", (0.8,1,0.9,1)))

        shield_node = _SMOOTH_FACTORY.uv_sphere(f"npc_shield_{idx}", 1.0, 24, 16)
        shield_node.reparentTo(root)
        shield_node.setScale(self.shield_radius * profile["scale"] * 0.82)
        shield_node.setTexture(self.fx_textures["shield"], 1)
        shield_node.setTransparency(TransparencyAttrib.M_alpha)
        shield_node.setDepthWrite(False)
        shield_node.setBin("transparent", 48)
        shield_node.setLightOff(True)
        shield_node.setColorScale(profile["secondary"][0] * 1.2, profile["secondary"][1] * 1.2, profile["secondary"][2] * 1.2, 0.0)
        shield_node.hide()

        npc = {
            "index": idx,
            "name": profile["name"],
            "team": team,
            "root": root,
            "visual": visual,
            "parts": parts,
            "base_hprs": base_hprs,
            "emissives": emissives,
            "trails": trails,
            "capes": capes,
            "cape_geos": cape_geos,
            "head_nodes": head_nodes,
            "propulsion": propulsion,
            "profile": profile,
            "pos": Vec3(pos),
            "velocity": Vec3(0, 0, 0),
            "heading": self.hero_heading if team == "ally" else 180.0,
            "pitch": 0.0,
            "roll": 0.0,
            "control_pitch": -8.0,
            "attack_timer": 0.0,
            "attack_cooldown": 0.6 + idx * 0.07,
            "secondary_cooldown": 1.6 + idx * 0.12,
            "attack_variant": "idle",
            "attack_charge": 0.0,
            "attack_charging": False,
            "shield_timer": 0.0,
            "shield_cooldown": 0.0,
            "recover_timer": 0.0,
            "player_aggro": 0.0,
            "hp": 100.0,
            "max_hp": 100.0,
            "hit_radius": 2.15 * profile["scale"],
            "orbit_sign": -1.0 if (idx % 2 == 0) else 1.0,
            "state": state or ("escort" if team == "ally" else "neutral"),
            "shield_node": shield_node,
            "formation_slot": int(formation_slot),
            "home_anchor": Vec3(home_anchor),
            "group_anchor": Vec3(group_anchor) if group_anchor is not None else Vec3(home_anchor),
            "spawn_chunk": spawn_chunk,
            "hit_parts": self.build_actor_hit_parts(root, parts, float(profile["scale"])),
            "ambient_cooldown": 1.6 + random.random() * 1.6,
            "support_timer": 0.0,
            "support_cooldown": random.random() * 2.0,
            "support_fx_tick": 0.0,
            "support_fx": str(profile.get("support_fx", "none")),
            "emote_name": "none",
            "emote_timer": random.random() * 2.0,
            "emote_cooldown": 2.0 + random.random() * 4.0,
            "emote_strength": 0.0,
            "xray_shell": xray_shell,
            "aura_shell": aura_shell,
            "dead": False,
            "grapple_cd": 1.4 + random.random() * 0.8 if profile.get("spider_demon") else 0.0,
            "grapple_timer": 0.0,
            "grapple_anchor": None,
            "pull_cd": 1.0 + random.random() * 1.2 if profile.get("spider_demon") else 0.0,
        }
        root.setPos(npc["pos"])
        self.npcs.append(npc)
        return npc

    def remove_chunk_npcs(self, chunk_key: tuple[int, int]) -> None:
        doomed = set(self.chunk_team_map.get(chunk_key, []))
        if not doomed:
            return
        survivors = []
        for npc in self.npcs:
            if npc["index"] in doomed:
                root = npc.get("root")
                if root is not None and not root.isEmpty():
                    root.removeNode()
                team_name = str(npc.get("team", ""))
                if team_name in self.hostile_teams and team_name not in ("ally", "enemy"):
                    still_exists = False
                    for other in self.npcs:
                        if other["index"] not in doomed and str(other.get("team")) == team_name:
                            still_exists = True
                            break
                    if not still_exists:
                        self.hostile_teams.discard(team_name)
            else:
                survivors.append(npc)
        self.npcs = survivors
        self.chunk_team_map.pop(chunk_key, None)

    def get_variant_theme_catalog(self) -> dict[str, list[dict]]:
        heroic = [
            {
                "id": "seraphic_halo",
                "names": ["Seraph", "Halo", "Virtue", "Aurelian", "Lumen", "Radiant"],
                "titles": ["Wing", "Spear", "Aegis", "Choir", "Crown", "Flare"],
                "palettes": [
                    ((0.98, 0.86, 0.46, 1.0), (0.92, 0.98, 1.0, 1.0), (1.0, 0.96, 0.72, 1.0), (0.98, 0.90, 0.78, 1.0)),
                    ((0.94, 0.62, 0.26, 1.0), (1.0, 0.92, 0.46, 1.0), (1.0, 0.78, 0.58, 1.0), (0.98, 0.78, 0.58, 1.0)),
                    ((0.80, 0.86, 1.0, 1.0), (0.96, 0.96, 1.0, 1.0), (0.64, 0.78, 1.0, 1.0), (0.86, 0.88, 0.98, 1.0)),
                ],
                "modes": ["beam", "pulse", "laser", "shockwave"],
                "secondary_modes": ["ring", "fan", "bolt", "flame"],
                "origins": ["head", "hands", "chest"],
                "supports": ["lightning", "torch", "frost"],
                "helmets": ["halo", "crown", "orb", "blade", "arc"],
                "suit_styles": ["celestial", "phoenix", "royal"],
                "back_patterns": ["angel", "sunburst", "halo", "orbital"],
                "wing_styles": ["angel", "angel", "tech"],
                "cape_chance": 0.76,
                "wing_chance": 0.70,
                "mobility": ["jetpack"],
                "scale": (0.94, 1.30),
                "hp": (92.0, 136.0),
                "speed": (52.0, 76.0),
                "evade": (82.0, 112.0),
                "attack": (1.00, 1.54),
                "secondary_cd": (2.0, 3.3),
            },
            {
                "id": "desert_ranger",
                "names": ["Dust", "Mesa", "Dune", "Kestrel", "Warden", "Range"],
                "titles": ["Ranger", "Marshal", "Shot", "Hawk", "Drift", "Guard"],
                "palettes": [
                    ((0.56, 0.70, 0.68, 1.0), (0.88, 0.30, 0.28, 1.0), (0.96, 0.82, 0.28, 1.0), (0.80, 0.84, 0.80, 1.0)),
                    ((0.30, 0.50, 0.40, 1.0), (0.72, 0.18, 0.16, 1.0), (0.94, 0.76, 0.24, 1.0), (0.76, 0.78, 0.74, 1.0)),
                    ((0.18, 0.22, 0.28, 1.0), (0.70, 0.74, 0.78, 1.0), (0.84, 0.24, 0.22, 1.0), (0.72, 0.72, 0.76, 1.0)),
                ],
                "modes": ["bolt", "fan", "missile", "shard"],
                "secondary_modes": ["wire", "laser", "pulse"],
                "origins": ["hand", "hands", "head"],
                "supports": ["cloak", "frost", "lightning"],
                "helmets": ["hood", "cowl", "mask", "antenna", "beak", "cage"],
                "suit_styles": ["ranger", "assault", "hunter"],
                "back_patterns": ["tech_spine", "blade", "halo", "spine"],
                "wing_styles": ["tech", "blade"],
                "cape_chance": 0.84,
                "wing_chance": 0.18,
                "mobility": ["thrusters", "jetpack"],
                "scale": (0.92, 1.22),
                "hp": (88.0, 122.0),
                "speed": (56.0, 82.0),
                "evade": (84.0, 114.0),
                "attack": (0.96, 1.42),
                "secondary_cd": (2.0, 3.2),
            },
            {
                "id": "chrome_surfer",
                "names": ["Chrome", "Mercury", "Argent", "Comet", "Wave", "Ion"],
                "titles": ["Surge", "Rider", "Flux", "Drift", "Arc", "Wake"],
                "palettes": [
                    ((0.74, 0.82, 0.92, 1.0), (0.94, 0.96, 1.0, 1.0), (0.38, 0.68, 1.0, 1.0), (0.84, 0.88, 0.92, 1.0)),
                    ((0.70, 0.72, 0.78, 1.0), (0.92, 0.96, 1.0, 1.0), (0.60, 0.30, 1.0, 1.0), (0.82, 0.84, 0.88, 1.0)),
                    ((0.56, 0.66, 0.92, 1.0), (0.88, 0.96, 1.0, 1.0), (0.22, 0.90, 1.0, 1.0), (0.74, 0.80, 0.96, 1.0)),
                ],
                "modes": ["beam", "wire", "shockwave", "laser"],
                "secondary_modes": ["pulse", "spiral", "atom"],
                "origins": ["hands", "head", "chest"],
                "supports": ["cloak", "lightning", "frost"],
                "helmets": ["orb", "split", "blade", "visorwide", "halo"],
                "suit_styles": ["surfer", "metallic", "circuit"],
                "back_patterns": ["orbital", "surf", "angel"],
                "wing_styles": ["surf", "tech"],
                "cape_chance": 0.20,
                "wing_chance": 0.48,
                "mobility": ["jetpack"],
                "scale": (0.92, 1.16),
                "hp": (86.0, 120.0),
                "speed": (58.0, 88.0),
                "evade": (92.0, 122.0),
                "attack": (0.90, 1.34),
                "secondary_cd": (1.8, 3.0),
            },
            {
                "id": "sentinel_megaforce",
                "names": ["Grid", "Volt", "Nova", "Vector", "Guard", "Astra"],
                "titles": ["Sentinel", "Ranger", "Morph", "Drive", "Volt", "Vector"],
                "palettes": [
                    ((0.92, 0.14, 0.12, 1.0), (1.0, 1.0, 1.0, 1.0), (0.18, 0.52, 1.0, 1.0), (0.86, 0.14, 0.12, 1.0)),
                    ((0.12, 0.42, 0.96, 1.0), (1.0, 1.0, 1.0, 1.0), (0.96, 0.18, 0.20, 1.0), (0.18, 0.42, 0.96, 1.0)),
                    ((0.98, 0.86, 0.08, 1.0), (0.08, 0.08, 0.10, 1.0), (1.0, 1.0, 1.0, 1.0), (0.92, 0.82, 0.22, 1.0)),
                ],
                "modes": ["laser", "fan", "bolt", "pulse"],
                "secondary_modes": ["beam", "missile", "shockwave"],
                "origins": ["hand", "hands", "chest"],
                "supports": ["lightning", "torch", "cloak"],
                "helmets": ["mask", "visorwide", "crest", "block", "antenna"],
                "suit_styles": ["sentinel", "assault", "circuit"],
                "back_patterns": ["sunburst", "tech_spine", "angel"],
                "wing_styles": ["tech", "blade"],
                "cape_chance": 0.18,
                "wing_chance": 0.26,
                "mobility": ["thrusters", "jetpack"],
                "scale": (0.94, 1.18),
                "hp": (92.0, 126.0),
                "speed": (58.0, 84.0),
                "evade": (86.0, 116.0),
                "attack": (0.92, 1.36),
                "secondary_cd": (2.0, 3.0),
            },
        ]
        villain = [
            {
                "id": "scarlet_mech_tyrant",
                "names": ["Crimson", "Omega", "Mecha", "Iron", "Apex", "Dread"],
                "titles": ["Tyrant", "Overlord", "Mind", "Core", "Prime", "Engine"],
                "palettes": [
                    ((0.72, 0.08, 0.10, 1.0), (0.28, 0.38, 0.82, 1.0), (0.92, 0.16, 0.18, 1.0), (0.66, 0.16, 0.20, 1.0)),
                    ((0.58, 0.10, 0.34, 1.0), (0.20, 0.20, 0.72, 1.0), (0.96, 0.36, 0.26, 1.0), (0.54, 0.18, 0.34, 1.0)),
                ],
                "modes": ["beam", "missile", "laser", "atom"],
                "secondary_modes": ["wire", "shockwave", "pulse"],
                "origins": ["head", "chest", "hands"],
                "supports": ["lightning", "cloak"],
                "helmets": ["spires", "crown", "antenna", "block", "arc"],
                "suit_styles": ["mecha", "regal", "metallic"],
                "back_patterns": ["tech_spine", "sunburst", "orbital", "tentacles"],
                "wing_styles": ["tech", "blade"],
                "cape_chance": 0.20,
                "wing_chance": 0.22,
                "mobility": ["thrusters"],
                "scale": (1.18, 1.70),
                "hp": (118.0, 182.0),
                "speed": (44.0, 64.0),
                "evade": (70.0, 96.0),
                "attack": (1.20, 1.78),
                "secondary_cd": (2.8, 4.4),
            },
            {
                "id": "golden_emperor",
                "names": ["Golden", "Crown", "Sable", "Royal", "Solar", "Void"],
                "titles": ["Emperor", "Tyrant", "King", "Lord", "Prince", "Throne"],
                "palettes": [
                    ((0.98, 0.82, 0.18, 1.0), (0.60, 0.22, 0.74, 1.0), (1.0, 0.96, 0.66, 1.0), (0.88, 0.72, 0.24, 1.0)),
                    ((0.94, 0.88, 0.22, 1.0), (0.42, 0.18, 0.54, 1.0), (0.96, 0.38, 0.94, 1.0), (0.82, 0.70, 0.30, 1.0)),
                ],
                "modes": ["laser", "beam", "atom", "shockwave"],
                "secondary_modes": ["pulse", "fan", "wire"],
                "origins": ["head", "chest", "hand"],
                "supports": ["cloak", "lightning", "torch"],
                "helmets": ["crown", "orb", "arc", "split", "spires"],
                "suit_styles": ["regal", "royal", "celestial"],
                "back_patterns": ["sunburst", "orbital", "halo", "surf"],
                "wing_styles": ["tech", "angel"],
                "cape_chance": 0.42,
                "wing_chance": 0.24,
                "mobility": ["jetpack"],
                "scale": (1.02, 1.34),
                "hp": (104.0, 146.0),
                "speed": (50.0, 72.0),
                "evade": (78.0, 104.0),
                "attack": (1.00, 1.48),
                "secondary_cd": (2.2, 3.6),
            },
            {
                "id": "inferno_wraith",
                "names": ["Inferno", "Ash", "Cinder", "Pyre", "Blaze", "Ember"],
                "titles": ["Wraith", "Maw", "Flare", "Burn", "Torch", "Ruin"],
                "palettes": [
                    ((0.96, 0.30, 0.12, 1.0), (1.0, 0.72, 0.22, 1.0), (1.0, 0.92, 0.58, 1.0), (0.88, 0.26, 0.16, 1.0)),
                    ((0.84, 0.16, 0.10, 1.0), (1.0, 0.46, 0.10, 1.0), (1.0, 0.84, 0.38, 1.0), (0.74, 0.16, 0.10, 1.0)),
                ],
                "modes": ["flame", "fireball", "shockwave", "atom"],
                "secondary_modes": ["beam", "pulse", "fan"],
                "origins": ["hands", "chest", "head"],
                "supports": ["torch", "cloak"],
                "helmets": ["horns", "frill", "spires", "cowl", "ram"],
                "suit_styles": ["infernal", "phoenix", "stealth"],
                "back_patterns": ["sunburst", "tentacles", "spine"],
                "wing_styles": ["bat", "blade"],
                "cape_chance": 0.18,
                "wing_chance": 0.44,
                "mobility": ["jetpack"],
                "scale": (0.98, 1.48),
                "hp": (96.0, 150.0),
                "speed": (52.0, 76.0),
                "evade": (80.0, 108.0),
                "attack": (0.96, 1.40),
                "secondary_cd": (2.0, 3.5),
            },
            {
                "id": "void_spider",
                "names": ["Night", "Void", "Grim", "Web", "Shade", "Noir"],
                "titles": ["Reaver", "Widow", "Crawler", "Fang", "Weaver", "Hook"],
                "palettes": [
                    ((0.08, 0.08, 0.12, 1.0), (0.70, 0.06, 0.10, 1.0), (0.92, 0.18, 0.26, 1.0), (0.16, 0.16, 0.22, 1.0)),
                    ((0.10, 0.10, 0.16, 1.0), (0.58, 0.14, 0.48, 1.0), (0.86, 0.20, 0.24, 1.0), (0.18, 0.18, 0.26, 1.0)),
                ],
                "modes": ["wire", "laser", "shockwave", "beam"],
                "secondary_modes": ["pulse", "slash", "missile"],
                "origins": ["hands", "head", "chest"],
                "supports": ["cloak", "lightning"],
                "helmets": ["mandibles", "hood", "cowl", "horns", "spires"],
                "suit_styles": ["stealth", "xeno", "demon_knight"],
                "back_patterns": ["spider", "tentacles", "tech_spine"],
                "wing_styles": ["bat", "tech"],
                "cape_chance": 0.08,
                "wing_chance": 0.52,
                "mobility": ["jetpack", "thrusters"],
                "scale": (0.94, 1.26),
                "hp": (90.0, 128.0),
                "speed": (60.0, 92.0),
                "evade": (96.0, 128.0),
                "attack": (0.84, 1.22),
                "secondary_cd": (1.8, 3.0),
            },
        ]
        outsiders = [
            {
                "id": "xeno_hunter",
                "names": ["Xeno", "Hunter", "Maw", "Stalker", "Razor", "Preda"],
                "titles": ["Claw", "Skull", "Spine", "Tracker", "Prowler", "Howl"],
                "palettes": [
                    ((0.10, 0.12, 0.12, 1.0), (0.30, 0.76, 0.20, 1.0), (0.74, 0.82, 0.90, 1.0), (0.40, 0.52, 0.36, 1.0)),
                    ((0.16, 0.14, 0.12, 1.0), (0.84, 0.20, 0.10, 1.0), (0.70, 0.76, 0.80, 1.0), (0.48, 0.42, 0.30, 1.0)),
                ],
                "modes": ["wire", "shard", "missile", "laser"],
                "secondary_modes": ["beam", "shockwave", "pulse"],
                "origins": ["head", "hand", "hands"],
                "supports": ["cloak", "frost"],
                "helmets": ["mandibles", "frill", "beak", "antenna", "cage"],
                "suit_styles": ["xeno", "hunter", "assault"],
                "back_patterns": ["spine", "tentacles", "hunter"],
                "wing_styles": ["blade", "tech"],
                "cape_chance": 0.04,
                "wing_chance": 0.16,
                "mobility": ["thrusters", "jetpack"],
                "scale": (1.00, 1.38),
                "hp": (96.0, 144.0),
                "speed": (56.0, 84.0),
                "evade": (84.0, 116.0),
                "attack": (0.98, 1.48),
                "secondary_cd": (2.2, 3.6),
            },
            {
                "id": "wild_mech_beasts",
                "names": ["Steel", "Circuit", "Titan", "Gale", "Rex", "Volt"],
                "titles": ["Claw", "Howl", "Prime", "Drive", "Fang", "Burst"],
                "palettes": [
                    ((0.74, 0.12, 0.12, 1.0), (0.18, 0.42, 1.0, 1.0), (0.90, 0.90, 0.96, 1.0), (0.46, 0.46, 0.52, 1.0)),
                    ((0.92, 0.72, 0.16, 1.0), (0.14, 0.18, 0.20, 1.0), (0.26, 0.74, 1.0, 1.0), (0.58, 0.54, 0.30, 1.0)),
                    ((0.16, 0.20, 0.26, 1.0), (0.86, 0.22, 0.20, 1.0), (0.88, 0.92, 1.0, 1.0), (0.40, 0.46, 0.56, 1.0)),
                ],
                "modes": ["beam", "missile", "pulse", "shockwave"],
                "secondary_modes": ["laser", "fan", "atom"],
                "origins": ["chest", "hands", "head"],
                "supports": ["lightning", "cloak", "torch"],
                "helmets": ["block", "crest", "spires", "visorwide", "orb"],
                "suit_styles": ["mecha", "sentinel", "metallic"],
                "back_patterns": ["tech_spine", "sunburst", "orbital", "surf"],
                "wing_styles": ["tech", "blade"],
                "cape_chance": 0.06,
                "wing_chance": 0.22,
                "mobility": ["thrusters"],
                "scale": (1.06, 1.48),
                "hp": (100.0, 158.0),
                "speed": (48.0, 74.0),
                "evade": (76.0, 104.0),
                "attack": (1.00, 1.56),
                "secondary_cd": (2.4, 3.8),
            },
        ]
        return {
            "heroic": heroic,
            "villain": villain,
            "outsider": outsiders,
            "all": heroic + villain + outsiders,
        }

    def choose_team_variant_theme(self, team_name: str, seed: int) -> dict:
        cache_key = f"{team_name}:{seed}"
        cached = self.team_variant_cache.get(cache_key)
        if cached is not None:
            return cached
        catalog = self.get_variant_theme_catalog()
        rnd = random.Random((self.seed * 9119) + sum(ord(c) for c in team_name) * 37 + seed)
        if team_name == "ally":
            pool = catalog["heroic"]
        elif team_name == "enemy":
            pool = catalog["villain"]
        elif team_name.startswith("wild_"):
            pool = catalog["all"]
        else:
            pool = catalog["all"]
        theme = rnd.choice(pool).copy()
        self.team_variant_cache[cache_key] = theme
        return theme

    def _profile_color_jitter(self, color: tuple[float, float, float, float], rnd: random.Random, sat_mul: float = 1.0, val_mul: float = 1.0) -> tuple[float, float, float, float]:
        import colorsys
        h, s, v = colorsys.rgb_to_hsv(color[0], color[1], color[2])
        h = (h + rnd.uniform(-0.035, 0.035)) % 1.0
        s = clamp(s * sat_mul + rnd.uniform(-0.08, 0.08), 0.08, 1.0)
        v = clamp(v * val_mul + rnd.uniform(-0.08, 0.08), 0.12, 1.0)
        r, g, b = colorsys.hsv_to_rgb(h, s, v)
        return (r, g, b, color[3] if len(color) > 3 else 1.0)

    def theme_for_family(self, family: str) -> dict:
        for bucket in self.get_variant_theme_catalog().values():
            if isinstance(bucket, list):
                for theme in bucket:
                    if theme.get("id") == family:
                        return theme
        return random.choice(self.get_variant_theme_catalog()["all"]).copy()

    def profile_power_signature(self, profile: dict) -> tuple:
        return (str(profile.get("mode", "bolt")), str(profile.get("secondary_mode", "pulse")), str(profile.get("origin", "head")), str(profile.get("secondary_origin", "hands")), str(profile.get("support_fx", "none")))

    def profile_appearance_signature(self, profile: dict) -> tuple:
        def q(color):
            return tuple(int(clamp(float(c), 0.0, 1.0) * 255.0) // 12 for c in color[:3])
        return (str(profile.get("family", "base")), str(profile.get("helmet", "crest")), str(profile.get("suit_style", "spectral")), str(profile.get("back_pattern", "spine")), str(profile.get("wing_style", "none")), str(profile.get("tail_style", "none")), bool(profile.get("big_horns", False)), q(profile.get("primary", (0,0,0,1))), q(profile.get("secondary", (0,0,0,1))), q(profile.get("accent", (0,0,0,1))), q(profile.get("body_tint", (0,0,0,1))))

    def ensure_unique_profile(self, profile: dict, seed: int) -> dict:
        theme = self.theme_for_family(str(profile.get("family", "")))
        rnd = random.Random(seed)
        mode_pool = list(dict.fromkeys(list(theme.get("modes", [])) + ["electric", "laser", "beam", "shockwave"]))
        secondary_pool = list(dict.fromkeys(list(theme.get("secondary_modes", [])) + ["electric", "laser", "beam", "pulse", "shockwave"]))
        support_pool = list(dict.fromkeys(list(theme.get("supports", [])) + ["lightning"]))
        origin_pool = list(dict.fromkeys(list(theme.get("origins", [])) + ["head", "hands", "chest"]))
        helmet_pool = list(dict.fromkeys(list(theme.get("helmets", [])) + ["horns", "block", "pyramid", "ram", "cage", "blade", "mandibles", "hood", "cowl", "spires", "antenna", "frill", "arc", "visorwide", "crest"]))
        suit_pool = list(dict.fromkeys(list(theme.get("suit_styles", [])) + ["circuit", "celestial", "surfer", "sentinel", "mecha", "infernal"]))
        pattern_pool = list(dict.fromkeys(list(theme.get("back_patterns", [])) + ["tech_spine", "halo", "sunburst", "blade", "orbital", "spider"]))
        wing_pool = list(dict.fromkeys(list(theme.get("wing_styles", [])) + ["none", "tech", "angel", "bat", "blade", "surf"]))
        tail_pool = ["none", "spine", "blade", "whip"]
        for attempt in range(72):
            power_sig = self.profile_power_signature(profile)
            appearance_sig = self.profile_appearance_signature(profile)
            if power_sig not in self.used_power_signatures and appearance_sig not in self.used_appearance_signatures:
                self.used_power_signatures.add(power_sig)
                self.used_appearance_signatures.add(appearance_sig)
                if float(profile.get("aura_glow", 0.0)) <= 0.0 and rnd.random() < 0.55:
                    profile["aura_color"] = self._profile_color_jitter(profile.get("secondary", (0.8, 1.0, 0.9, 1.0)), rnd, 1.30, 1.22)
                    profile["aura_glow"] = rnd.uniform(0.22, 0.58)
                else:
                    profile.setdefault("aura_color", profile.get("secondary", (0.8, 1.0, 0.9, 1.0)))
                    profile.setdefault("aura_glow", 0.0)
                return profile
            arnd = random.Random(seed + attempt * 137 + 17)
            if power_sig in self.used_power_signatures:
                profile["mode"] = arnd.choice(mode_pool)
                profile["secondary_mode"] = arnd.choice([m for m in secondary_pool if m != profile["mode"]] or secondary_pool)
                profile["origin"] = arnd.choice(origin_pool)
                profile["secondary_origin"] = arnd.choice([o for o in origin_pool if o != profile["origin"]] or origin_pool)
                profile["support_fx"] = arnd.choice(support_pool)
            if appearance_sig in self.used_appearance_signatures:
                profile["primary"] = self._profile_color_jitter(profile.get("primary", (0.3,1.0,0.44,1.0)), arnd, 1.15, 1.14)
                profile["secondary"] = self._profile_color_jitter(profile.get("secondary", (0.8,1.0,0.9,1.0)), arnd, 1.18, 1.16)
                profile["accent"] = self._profile_color_jitter(profile.get("accent", (1.0,1.0,1.0,1.0)), arnd, 1.20, 1.18)
                profile["body_tint"] = self._profile_color_jitter(profile.get("body_tint", (1.0,1.0,1.0,1.0)), arnd, 1.05, 1.08)
                profile["helmet"] = arnd.choice(helmet_pool)
                profile["suit_style"] = arnd.choice(suit_pool)
                profile["back_pattern"] = arnd.choice(pattern_pool)
                profile["wing_style"] = arnd.choice(wing_pool)
                profile["tail_style"] = arnd.choice(tail_pool)
                profile["big_horns"] = bool(profile.get("helmet") in ("horns", "ram", "spires", "frill") or arnd.random() < 0.25)
                profile["helmet_scale"] = (arnd.uniform(0.84, 1.24), arnd.uniform(0.86, 1.26), arnd.uniform(0.86, 1.34))
                profile["visor_scale"] = (arnd.uniform(0.84, 1.22), 1.0, arnd.uniform(0.84, 1.22))
                profile["jaw_scale"] = (arnd.uniform(0.82, 1.20), arnd.uniform(0.82, 1.14), arnd.uniform(0.84, 1.20))
                profile["wire_wings"] = profile.get("wing_style", "none") != "none"
                profile["wing_span"] = arnd.uniform(1.05, 1.72 if profile.get("wing_style") != "none" else 1.18)
                profile["giant_wings"] = profile.get("wing_style") != "none" and arnd.random() < 0.35
                profile["tail_length"] = arnd.uniform(0.32, 0.90) if profile.get("tail_style") != "none" else 0.0
                profile["aura_color"] = self._profile_color_jitter(profile.get("accent", (1.0,1.0,1.0,1.0)), arnd, 1.30, 1.24)
                profile["aura_glow"] = arnd.uniform(0.0, 0.62) if arnd.random() < 0.60 else 0.0
        self.used_power_signatures.add(self.profile_power_signature(profile))
        self.used_appearance_signatures.add(self.profile_appearance_signature(profile))
        profile.setdefault("aura_color", profile.get("secondary", (0.8, 1.0, 0.9, 1.0)))
        profile.setdefault("aura_glow", 0.0)
        return profile

    def build_roaming_profile(self, seed: int, team_name: str, slot: int) -> dict:
        rnd = random.Random(seed)
        theme = self.choose_team_variant_theme(team_name, seed)
        palette = rnd.choice(theme["palettes"])
        primary = self._profile_color_jitter(palette[0], rnd, 1.06, 1.02)
        secondary = self._profile_color_jitter(palette[1], rnd, 0.98, 1.00)
        accent = self._profile_color_jitter(palette[2], rnd, 1.02, 1.00)
        body_tint = self._profile_color_jitter(palette[3], rnd, 0.90, 0.98)
        mode_pool = list(dict.fromkeys(list(theme["modes"]) + ["electric"]))
        secondary_pool = list(dict.fromkeys(list(theme["secondary_modes"]) + ["electric", "laser", "beam"]))
        mode = rnd.choice(mode_pool)
        secondary_mode = rnd.choice([m for m in secondary_pool if m != mode] or secondary_pool)
        origin = rnd.choice(theme["origins"])
        secondary_origin = rnd.choice([o for o in theme["origins"] if o != origin] or theme["origins"])
        helmet = rnd.choice(theme["helmets"])
        suit_style = rnd.choice(theme["suit_styles"])
        back_pattern = rnd.choice(theme["back_patterns"])
        wing_style = rnd.choice(theme["wing_styles"]) if rnd.random() < theme.get("wing_chance", 0.0) else "none"
        giant_wings = wing_style != "none" and rnd.random() < (0.34 if "angel" in theme["wing_styles"] or "bat" in theme["wing_styles"] else 0.22)
        lower_tail = rnd.random() < 0.30
        horn_boost = helmet in ("horns", "ram", "spires", "frill") and rnd.random() < 0.72
        cape = False
        support_fx = rnd.choice(theme["supports"])
        mobility_style = rnd.choice(theme.get("mobility", ["jetpack"]))
        name = f"{rnd.choice(theme['names'])} {rnd.choice(theme['titles'])}"
        scale = rnd.uniform(*theme["scale"])
        max_hp = rnd.uniform(*theme["hp"])
        cruise_speed = rnd.uniform(*theme["speed"])
        evade_speed = rnd.uniform(*theme["evade"])
        attack_interval = rnd.uniform(*theme["attack"])
        secondary_cd = rnd.uniform(*theme["secondary_cd"])
        visor_scale = (rnd.uniform(0.84, 1.22), 1.0, rnd.uniform(0.84, 1.22))
        jaw_scale = (rnd.uniform(0.82, 1.20), rnd.uniform(0.82, 1.14), rnd.uniform(0.84, 1.20))
        helmet_scale = (rnd.uniform(0.84, 1.22), rnd.uniform(0.88, 1.24), rnd.uniform(0.86, 1.32))
        if helmet in ("block", "mask", "visorwide"):
            helmet_scale = (helmet_scale[0] * 1.08, helmet_scale[1] * 0.92, helmet_scale[2] * 0.96)
        if helmet in ("horns", "frill", "spires", "antenna"):
            helmet_scale = (helmet_scale[0] * 0.92, helmet_scale[1] * 1.06, helmet_scale[2] * 1.16)
        profile = {
            "name": name,
            "team": team_name,
            "family": theme["id"],
            "primary": primary,
            "secondary": secondary,
            "accent": accent,
            "mode": mode,
            "secondary_mode": secondary_mode,
            "origin": origin,
            "secondary_origin": secondary_origin,
            "support_fx": support_fx,
            "scale": scale,
            "body_tint": body_tint,
            "helmet": helmet,
            "helmet_scale": helmet_scale,
            "visor_scale": visor_scale,
            "jaw_scale": jaw_scale,
            "max_hp": max_hp,
            "cruise_speed": cruise_speed,
            "attack_interval": attack_interval,
            "evade_speed": evade_speed,
            "secondary_cd": secondary_cd,
            "formation_slot": slot,
            "count": rnd.randint(1, 4),
            "spread": rnd.uniform(0.05, 0.22),
            "speed": rnd.uniform(90.0, 158.0),
            "projectile_scale": rnd.uniform(0.20, 0.44),
            "cape": cape,
            "wire_wings": wing_style != "none",
            "wing_style": wing_style,
            "wing_span": rnd.uniform(1.05, 1.55 if giant_wings else 1.32),
            "giant_wings": giant_wings,
            "tail_style": rnd.choice(["spine", "blade", "whip"]) if lower_tail else "none",
            "tail_length": rnd.uniform(0.32, 0.82) if lower_tail else 0.0,
            "big_horns": horn_boost,
            "suit_style": suit_style,
            "fx_kind": rnd.choice(["burst", "ring", "scan", "slash", "beam"]),
            "secondary_fx": rnd.choice(["burst", "ring", "scan", "slash", "beam", "blink"]),
            "back_pattern": back_pattern,
            "mobility_style": mobility_style,
            "aura_color": self._profile_color_jitter(accent, rnd, 1.22, 1.20),
            "aura_glow": rnd.uniform(0.0, 0.58) if rnd.random() < 0.55 else 0.0,
        }
        if cape:
            cape_base = accent if rnd.random() < 0.5 else secondary
            profile["cape_color"] = (clamp(cape_base[0] * 0.42 + 0.08, 0.0, 1.0), clamp(cape_base[1] * 0.42 + 0.08, 0.0, 1.0), clamp(cape_base[2] * 0.42 + 0.08, 0.0, 1.0), 1.0)
        if theme["id"] == "void_spider":
            profile["spider_demon"] = True
            profile["wire_wings"] = True
            profile["wing_style"] = "bat"
            profile["back_pattern"] = "spider"
        return self.ensure_unique_profile(profile, seed)

    def spawn_world_team_for_chunk(self, chunk_key: tuple[int, int], center_x: float, center_y: float, rnd: random.Random, biome: str) -> None:
        if chunk_key in self.chunk_team_map:
            return
        if rnd.random() > (0.46 if biome in ("nature", "hills") else 0.28):
            return

        team_name = f"wild_{self.wild_team_serial}"
        self.wild_team_serial += 1
        team_size = 4 if rnd.random() < 0.65 else 3

        base_x = center_x + rnd.uniform(-self.outskirts_chunk_size * 0.22, self.outskirts_chunk_size * 0.22)
        base_y = center_y + rnd.uniform(-self.outskirts_chunk_size * 0.22, self.outskirts_chunk_size * 0.22)
        base_z = rnd.uniform(18.0, 32.0) if biome in ("nature", "hills") else rnd.uniform(16.0, 24.0)
        anchor = Vec3(base_x, base_y, base_z)

        slot_offsets = [
            Vec3(-16.0, 0.0, 0.0),
            Vec3(-5.0, -12.0, 1.0),
            Vec3(7.0, -12.0, 1.0),
            Vec3(18.0, 0.0, 0.0),
        ]
        ids = []
        for slot in range(team_size):
            profile = self.build_roaming_profile(self.seed * 313 + chunk_key[0] * 101 + chunk_key[1] * 67 + slot * 17 + self.wild_team_serial * 1009, team_name, slot)
            start = anchor + slot_offsets[slot % len(slot_offsets)]
            npc = self.spawn_npc_actor(profile, start, start, slot, team_name, group_anchor=anchor, spawn_chunk=chunk_key, state="neutral")
            npc["group_anchor"] = Vec3(anchor)
            ids.append(npc["index"])
        self.chunk_team_map[chunk_key] = ids

    def get_group_formation_target(self, npc: dict) -> Vec3:
        team_name = str(npc.get("team", ""))
        if team_name == "ally":
            return self.get_ally_formation_target(int(npc.get("formation_slot", 0)))
        if team_name == "enemy":
            return self.get_enemy_formation_target(int(npc.get("formation_slot", 0)))

        anchor = Vec3(npc.get("group_anchor", npc.get("home_anchor", npc["pos"])))
        offsets = [
            Vec3(-16.0, 0.0, 0.0),
            Vec3(-5.0, -12.0, 1.5),
            Vec3(7.0, -12.0, 1.5),
            Vec3(18.0, 0.0, 0.0),
        ]
        return anchor + offsets[int(npc.get("formation_slot", 0)) % len(offsets)]

    def get_idle_patrol_offset(self, npc: dict, team_name: str) -> Vec3:
        t = globalClock.getFrameTime()
        slot = float(int(npc.get("formation_slot", 0)))
        phase = float(npc.get("index", 0)) * 0.73 + slot * 0.41
        if team_name == "ally":
            forward = self.forward_from_angles(self.hero_heading, 0.0)
            if forward.lengthSquared() < 1e-6:
                forward = Vec3(0, 1, 0)
            forward.normalize()
            right = self.right_from_yaw(self.hero_heading)
            sway = math.sin(t * 1.35 + phase) * 1.8
            lift = math.sin(t * 1.9 + phase * 1.7) * 0.55
            push = math.cos(t * 1.15 + phase) * 0.9
            return right * sway + forward * push + Vec3(0, 0, lift)
        swirl = Vec3(
            math.sin(t * 0.82 + phase) * 6.0,
            math.cos(t * 0.76 + phase * 1.2) * 5.0,
            math.sin(t * 1.12 + phase * 1.4) * 1.6,
        )
        return swirl

    def update_dynamic_group_anchors(self, dt: float) -> None:
        teams = {}
        for npc in self.npcs:
            team_name = str(npc.get("team", ""))
            if team_name in ("ally", "enemy"):
                continue
            teams.setdefault(team_name, []).append(npc)

        for members in teams.values():
            anchor = Vec3(members[0].get("group_anchor", members[0]["pos"]))
            if members[0]["team"] in self.hostile_teams:
                continue
            drift = Vec3(math.sin(globalClock.getFrameTime() * 0.34 + members[0]["index"]) * 5.2, math.cos(globalClock.getFrameTime() * 0.27 + members[0]["index"]) * 4.8, math.sin(globalClock.getFrameTime() * 0.44 + members[0]["index"]) * 0.55)
            target_anchor = Vec3(anchor.x + drift.x * dt, anchor.y + drift.y * dt, clamp(anchor.z + drift.z * dt, 16.0, 34.0))
            for npc in members:
                npc["group_anchor"] = Vec3(target_anchor)

    def build_npc_profile(self, index: int) -> dict:
        profiles = [
            {
                "name": "Aegis Halo",
                "team": "ally",
                "primary": (0.22, 1.0, 0.70, 1.0),
                "secondary": (0.90, 1.0, 0.96, 1.0),
                "accent": (0.52, 1.0, 0.82, 1.0),
                "mode": "pulse",
                "secondary_mode": "wire",
                "origin": "chest",
                "secondary_origin": "hands",
                "fx_kind": "ring",
                "secondary_fx": "scan",
                "scale": 1.04,
                "body_tint": (0.60, 0.88, 0.74, 1.0),
                "helmet": "halo",
                "helmet_scale": (1.08, 1.02, 1.12),
                "visor_scale": (1.05, 1.00, 0.95),
                "jaw_scale": (1.02, 0.92, 1.02),
                "max_hp": 96.0,
                "cruise_speed": 54.0,
                "attack_interval": 1.38,
                "evade_speed": 82.0,
                "secondary_cd": 2.8,
                "formation_slot": 0,
            },
            {
                "name": "Rift Talon",
                "team": "ally",
                "primary": (0.18, 0.84, 1.0, 1.0),
                "secondary": (0.34, 1.0, 0.52, 1.0),
                "accent": (0.82, 1.0, 0.96, 1.0),
                "mode": "spiral",
                "secondary_mode": "beam",
                "origin": "hands",
                "secondary_origin": "head",
                "fx_kind": "slash",
                "secondary_fx": "beam",
                "scale": 0.86,
                "body_tint": (0.44, 0.62, 0.96, 1.0),
                "helmet": "blade",
                "helmet_scale": (0.86, 1.00, 1.26),
                "visor_scale": (0.94, 1.00, 1.16),
                "jaw_scale": (0.92, 0.86, 0.92),
                "max_hp": 74.0,
                "cruise_speed": 62.0,
                "attack_interval": 1.18,
                "evade_speed": 94.0,
                "secondary_cd": 2.5,
                "formation_slot": 1,
            },
            {
                "name": "Solar Maw",
                "team": "ally",
                "primary": (1.0, 0.66, 0.12, 1.0),
                "secondary": (1.0, 0.24, 0.14, 1.0),
                "accent": (1.0, 0.92, 0.48, 1.0),
                "mode": "fireball",
                "secondary_mode": "fan",
                "origin": "chest",
                "secondary_origin": "hands",
                "fx_kind": "burst",
                "secondary_fx": "ring",
                "scale": 1.42,
                "body_tint": (0.94, 0.70, 0.42, 1.0),
                "helmet": "crown",
                "helmet_scale": (1.16, 1.06, 1.08),
                "visor_scale": (1.12, 1.00, 0.92),
                "jaw_scale": (1.12, 1.04, 1.06),
                "max_hp": 132.0,
                "cruise_speed": 50.0,
                "attack_interval": 1.62,
                "evade_speed": 76.0,
                "secondary_cd": 3.4,
                "formation_slot": 2,
            },
            {
                "name": "Null Warden",
                "team": "enemy",
                "primary": (0.74, 0.22, 1.0, 1.0),
                "secondary": (0.22, 0.84, 1.0, 1.0),
                "accent": (0.96, 0.78, 1.0, 1.0),
                "mode": "shard",
                "secondary_mode": "laser",
                "origin": "head",
                "secondary_origin": "chest",
                "fx_kind": "scan",
                "secondary_fx": "beam",
                "scale": 1.02,
                "body_tint": (0.54, 0.38, 0.84, 1.0),
                "helmet": "fins",
                "helmet_scale": (1.00, 1.18, 1.08),
                "visor_scale": (0.92, 1.00, 1.12),
                "jaw_scale": (1.10, 0.92, 1.10),
                "max_hp": 90.0,
                "cruise_speed": 56.0,
                "attack_interval": 1.34,
                "evade_speed": 86.0,
                "secondary_cd": 2.8,
                "formation_slot": 0,
            },
            {
                "name": "Inferno Horn",
                "team": "enemy",
                "primary": (1.0, 0.18, 0.12, 1.0),
                "secondary": (1.0, 0.82, 0.16, 1.0),
                "accent": (1.0, 0.48, 0.28, 1.0),
                "mode": "missile",
                "secondary_mode": "fireball",
                "origin": "hands",
                "secondary_origin": "chest",
                "fx_kind": "burst",
                "secondary_fx": "slash",
                "scale": 1.84,
                "body_tint": (0.88, 0.34, 0.26, 1.0),
                "helmet": "horns",
                "helmet_scale": (1.18, 1.00, 1.16),
                "visor_scale": (1.06, 1.00, 0.92),
                "jaw_scale": (1.18, 1.12, 1.10),
                "max_hp": 160.0,
                "cruise_speed": 46.0,
                "attack_interval": 1.88,
                "evade_speed": 66.0,
                "secondary_cd": 3.9,
                "formation_slot": 1,
            },
            {
                "name": "Venom Crest",
                "team": "enemy",
                "primary": (0.42, 1.0, 0.16, 1.0),
                "secondary": (0.82, 1.0, 0.48, 1.0),
                "accent": (0.70, 1.0, 0.26, 1.0),
                "mode": "wire",
                "secondary_mode": "spiral",
                "origin": "head",
                "secondary_origin": "hand",
                "fx_kind": "scan",
                "secondary_fx": "slash",
                "scale": 1.22,
                "body_tint": (0.34, 0.74, 0.28, 1.0),
                "helmet": "crest",
                "helmet_scale": (0.94, 1.06, 1.26),
                "visor_scale": (0.94, 1.00, 1.04),
                "jaw_scale": (0.98, 0.90, 1.02),
                "max_hp": 108.0,
                "cruise_speed": 60.0,
                "attack_interval": 1.42,
                "evade_speed": 86.0,
                "secondary_cd": 3.0,
                "formation_slot": 2,
            },
            {
                "name": "Dread Splitter",
                "team": "enemy",
                "primary": (0.95, 0.12, 0.44, 1.0),
                "secondary": (0.52, 0.78, 1.0, 1.0),
                "accent": (1.0, 0.58, 0.76, 1.0),
                "mode": "beam",
                "secondary_mode": "missile",
                "origin": "hand",
                "secondary_origin": "head",
                "fx_kind": "beam",
                "secondary_fx": "burst",
                "scale": 0.92,
                "body_tint": (0.66, 0.28, 0.52, 1.0),
                "helmet": "split",
                "helmet_scale": (0.90, 1.02, 1.18),
                "visor_scale": (1.10, 1.00, 1.06),
                "jaw_scale": (0.86, 0.84, 0.96),
                "max_hp": 78.0,
                "cruise_speed": 68.0,
                "attack_interval": 1.16,
                "evade_speed": 94.0,
                "secondary_cd": 2.4,
                "formation_slot": 3,
            },
        ]
        profile = profiles[index % len(profiles)].copy()
        rnd = random.Random(self.seed * 173 + index * 41)
        support_cycle = ["lightning", "cloak", "torch", "frost", "lightning", "cloak", "frost"]
        profile["support_fx"] = support_cycle[index % len(support_cycle)]
        profile["count"] = 1 + (index % 3)
        profile["spread"] = 0.05 + (index % 4) * 0.025 + rnd.random() * 0.03
        profile["speed"] = profile.get("cruise_speed", 50.0) * (1.45 + rnd.random() * 0.55)
        profile["projectile_scale"] = 0.20 + (index % 4) * 0.035 + rnd.random() * 0.04
        if index % len(profiles) in (0, 2, 4, 6):
            profile["cape"] = True
            accent = profile.get("accent", (1.0, 1.0, 1.0, 1.0))
            profile["cape_color"] = (accent[0] * 0.42 + 0.10, accent[1] * 0.42 + 0.10, accent[2] * 0.42 + 0.10, 1.0)
        return profile


    def resolve_locked_target(self, target: dict | None = None):
        target = self.locked_target if target is None else target
        if target is None:
            return None
        kind = str(target.get("kind", ""))
        if kind == "boss":
            if self.boss is None or not self.boss.get("alive", False):
                return None
            return self.boss
        if kind == "npc":
            idx = int(target.get("index", -1))
            for npc in self.npcs:
                if npc.get("index") == idx and not npc.get("dead", False) and str(npc.get("team", "")) in self.hostile_teams:
                    return npc
        return None

    def get_locked_target_pos(self, target: dict | None = None) -> Vec3 | None:
        resolved = self.resolve_locked_target(target)
        if resolved is None:
            return None
        if resolved is self.boss:
            root = resolved.get("root")
            if root is None or root.isEmpty():
                return None
            if str(resolved.get("type", "eye")) == "sandworm":
                return Vec3(resolved.get("mouth_world", root.getPos(self.render) + Vec3(0, 0, 3.4)))
            return root.getPos(self.render) + Vec3(0, 0, 2.8)
        return resolved["pos"] + Vec3(0, 0, 1.2 * resolved["profile"]["scale"])

    def find_nearest_lockable_target(self) -> dict | None:
        best = None
        best_d2 = self.target_lock_range * self.target_lock_range
        if self.boss is not None and self.boss.get("alive", False):
            pos = self.get_locked_target_pos({"kind": "boss"})
            if pos is not None:
                d2 = (pos - self.hero_pos).lengthSquared()
                if d2 <= best_d2:
                    best_d2 = d2
                    best = {"kind": "boss", "name": str(self.boss.get("name", "Boss"))}
        for npc in self.npcs:
            if npc.get("dead", False):
                continue
            if str(npc.get("team", "")) not in self.hostile_teams:
                continue
            d2 = (npc["pos"] - self.hero_pos).lengthSquared()
            if d2 <= best_d2:
                best_d2 = d2
                best = {"kind": "npc", "index": int(npc["index"]), "name": str(npc.get("name", "Enemy"))}
        return best

    def clear_target_lock(self, reason: str | None = None) -> None:
        if self.locked_target is None:
            return
        self.locked_target = None
        if reason:
            self.last_power_text = reason

    def toggle_target_lock(self) -> None:
        if self.locked_target is not None:
            self.clear_target_lock("Target lock off")
            return
        target = self.find_nearest_lockable_target()
        if target is None:
            self.last_power_text = "No hostile in range"
            return
        self.locked_target = target
        self.last_power_text = f"Locked {target.get('name', 'target')}"

    def update_target_lock(self, dt: float) -> None:
        if self.locked_target is None:
            return
        pos = self.get_locked_target_pos()
        if pos is None:
            self.clear_target_lock("Target lost")
            return
        delta = pos - (self.hero_pos + Vec3(0, 0, 1.4))
        if delta.lengthSquared() > self.target_lock_range * self.target_lock_range:
            self.clear_target_lock("Target out of range")
            return
        flat = Vec3(delta.x, delta.y, 0.0)
        if flat.lengthSquared() < 1e-6:
            return
        desired_heading = math.degrees(math.atan2(flat.x, flat.y))
        self.hero_heading = lerp_angle_deg(self.hero_heading, desired_heading, dt * 10.0) % 360.0
        self.control_yaw = self.hero_heading
        self.cam_yaw = self.hero_heading

    def owner_team(self, owner: str) -> str:
        if owner == "player":
            return "ally"
        if owner == "police":
            return "police"
        if owner == "boss":
            return "boss"
        if owner.startswith("launcher:"):
            return "launcher"
        if owner.startswith("npc"):
            try:
                idx = int(owner[3:])
            except ValueError:
                return "neutral"
            for npc in self.npcs:
                if npc["index"] == idx:
                    return str(npc.get("team", "neutral"))
        return "neutral"

    def owner_is_enemy(self, owner: str, target_team: str) -> bool:
        owner_team = self.owner_team(owner)
        if owner_team == "police":
            return self.police_alert_team == target_team
        if owner_team == "launcher":
            return self.launcher_alert_team == target_team
        if owner_team == "boss":
            return target_team != "boss"
        return owner_team != "neutral" and owner_team != target_team

    def activate_team_combat(self, reason: str = "Engaged enemy team", team_name: str = "enemy") -> None:
        self.hostile_teams.add(team_name)
        if not self.combat_active:
            self.combat_active = True
        self.last_power_text = reason

    def choose_closest_npc(self, source_pos: Vec3, candidates: list[dict], exclude_index: int | None = None) -> dict | None:
        best = None
        best_d2 = 1e18
        for npc in candidates:
            if npc.get("dead", False):
                continue
            if exclude_index is not None and npc["index"] == exclude_index:
                continue
            d2 = (npc["pos"] - source_pos).lengthSquared()
            if d2 < best_d2:
                best_d2 = d2
                best = npc
        return best

    def register_box_target(self, node: NodePath, width: float, depth: float, height: float, zone: str, label: str = "structure") -> None:
        self.structure_targets.append({
            "node": node,
            "shape": "box",
            "w": float(width),
            "d": float(depth),
            "h": float(height),
            "hp": max(20.0, height * 0.45 + width * depth * 0.05),
            "max_hp": max(20.0, height * 0.45 + width * depth * 0.05),
            "cooldown": 0.0,
            "zone": zone,
            "label": label,
            "base_z": float(node.getZ()),
            "sink": 0.0,
            "destroyed": False,
            "remove_when_sunk": label in ("building", "house", "warehouse", "tower"),
        })

    def register_pyramid_target(self, node: NodePath, width: float, depth: float, height: float, zone: str, label: str = "pyramid") -> None:
        self.structure_targets.append({
            "node": node,
            "shape": "pyramid",
            "w": float(width),
            "d": float(depth),
            "h": float(height),
            "hp": max(28.0, height * 0.55 + width * depth * 0.05),
            "max_hp": max(28.0, height * 0.55 + width * depth * 0.05),
            "cooldown": 0.0,
            "zone": zone,
            "label": label,
            "base_z": float(node.getZ()),
            "sink": 0.0,
            "destroyed": False,
            "remove_when_sunk": False,
        })

    def build_actor_hit_parts(self, root: NodePath, parts: dict[str, NodePath], scale: float) -> list[dict]:
        hit_parts: list[dict] = []
        def add(node_key: str, radius: float):
            part = parts.get(node_key)
            if part is not None:
                hit_parts.append({"node": part, "radius": radius * scale})
        for key, radius in (
            ("helmet_geo", 0.20),
            ("chest_geo", 0.30),
            ("abdomen_geo", 0.22),
            ("pelvis_geo", 0.24),
            ("upperarm_l_geo", 0.12),
            ("upperarm_r_geo", 0.12),
            ("forearm_l_geo", 0.10),
            ("forearm_r_geo", 0.10),
            ("thigh_l_geo", 0.16),
            ("thigh_r_geo", 0.16),
            ("shin_l_geo", 0.13),
            ("shin_r_geo", 0.13),
        ):
            add(key, radius)
        return hit_parts

    def point_hits_structure(self, pos: Vec3, target: dict, radius: float = 0.0) -> bool:
        node = target.get("node")
        if node is None or node.isEmpty():
            return False
        local = node.getRelativePoint(self.render, pos)
        w = float(target["w"]) * 0.5 + radius
        d = float(target["d"]) * 0.5 + radius
        h = float(target["h"]) + radius
        if target["shape"] == "box":
            return (-w <= local.x <= w) and (-d <= local.y <= d) and (-radius <= local.z <= h)
        if target["shape"] == "pyramid":
            if not (-radius <= local.z <= h):
                return False
            if local.z <= 0.0:
                return (-w <= local.x <= w) and (-d <= local.y <= d)
            frac = 1.0 - (local.z / max(0.001, float(target["h"])))
            allowed_x = w * max(0.0, frac) + radius * 0.4
            allowed_y = d * max(0.0, frac) + radius * 0.4
            return abs(local.x) <= allowed_x and abs(local.y) <= allowed_y
        return False

    def damage_structure(self, target: dict, amount: float, pos: Vec3) -> None:
        node = target.get("node")
        if node is None or node.isEmpty() or target.get("deleted", False):
            return
        if target.get("cooldown", 0.0) > 0.0:
            return
        target["hp"] = max(0.0, float(target["hp"]) - amount)
        target["cooldown"] = 0.08
        target["sink"] = min(float(target.get("sink", 0.0)) + (0.24 if amount < 22.0 else 0.46), float(target["h"]) * 0.98)
        self.spawn_power_fx("burst", pos, (1.0, 0.66, 0.28, 0.55), 0.52 if amount < 22.0 else 0.88)
        if target["hp"] <= 0.0:
            target["destroyed"] = True
            target["sink"] = min(float(target.get("sink", 0.0)) + 0.95, float(target["h"]) * 1.20)
            self.spawn_power_fx("ring", pos + Vec3(0, 0, 1.2), (1.0, 0.42, 0.20, 0.62), 1.05)

    def update_structure_targets(self, dt: float) -> None:
        kept_targets = []
        for target in self.structure_targets:
            node = target.get("node")
            if node is None or node.isEmpty() or target.get("deleted", False):
                continue
            target["cooldown"] = max(0.0, float(target.get("cooldown", 0.0)) - dt)
            base_z = float(target.get("base_z", node.getZ()))
            sink = float(target.get("sink", 0.0))
            node.setZ(lerp(node.getZ(), base_z - sink, clamp(dt * 1.65, 0.0, 1.0)))
            if target.get("destroyed") and target.get("remove_when_sunk", False) and node.getZ() <= self.surface_water_z - 0.85:
                self.spawn_power_fx("smoke", node.getPos(self.render) + Vec3(0, 0, 1.2), (0.16, 0.22, 0.20, 0.30), 0.95)
                node.removeNode()
                target["deleted"] = True
                continue
            kept_targets.append(target)
        self.structure_targets = kept_targets

    def hit_structure_by_projectile(self, pos: Vec3, strong: bool, owner: str) -> bool:
        radius = 1.4 if strong else 0.75
        damage = 1.0
        for target in self.structure_targets:
            node = target.get("node")
            if node is None or node.isEmpty():
                continue
            if self.point_hits_structure(pos, target, radius):
                self.damage_structure(target, damage, pos)
                return True
        return False

    def choose_ambient_target_pos(self, source_pos: Vec3) -> Vec3 | None:
        best_pos = None
        best_d2 = 1e18
        for car in self.traffic_cars:
            if not car.get("active", False):
                continue
            p = car["node"].getPos() + Vec3(0, 0, 0.6)
            d2 = (p - source_pos).lengthSquared()
            if d2 < best_d2:
                best_d2 = d2
                best_pos = p
        for target in self.structure_targets:
            node = target.get("node")
            if node is None or node.isEmpty():
                continue
            p = node.getPos(self.render) + Vec3(0, 0, float(target["h"]) * 0.55)
            d2 = (p - source_pos).lengthSquared()
            if d2 < best_d2:
                best_d2 = d2
                best_pos = p
        return Vec3(best_pos) if best_pos is not None else None

    def get_enemy_formation_anchor(self) -> Vec3:
        return Vec3(0.0, 112.0, 22.0)

    def get_ally_formation_target(self, slot: int) -> Vec3:
        flat_forward = Vec3(math.sin(math.radians(self.hero_heading)), math.cos(math.radians(self.hero_heading)), 0.0)
        if flat_forward.lengthSquared() < 1e-6:
            flat_forward = Vec3(0, 1, 0)
        flat_forward.normalize()
        right = self.right_from_yaw(self.hero_heading)
        offsets = [
            right * -22.0 + flat_forward * -8.0 + Vec3(0, 0, 2.6),
            right * 0.0 + flat_forward * -16.0 + Vec3(0, 0, 3.0),
            right * 22.0 + flat_forward * -8.0 + Vec3(0, 0, 2.6),
        ]
        return self.hero_pos + offsets[slot % len(offsets)]

    def get_enemy_formation_target(self, slot: int) -> Vec3:
        anchor = self.get_enemy_formation_anchor()
        offsets = [
            Vec3(-24.0, 0.0, 0.0),
            Vec3(-8.0, -18.0, 2.0),
            Vec3(8.0, -18.0, 2.0),
            Vec3(24.0, 0.0, 0.0),
        ]
        return anchor + offsets[slot % len(offsets)]

    def apply_npc_team_avoidance(self, npc: dict, desired: Vec3) -> Vec3:
        avoid = Vec3(0, 0, 0)
        for other in self.npcs:
            if other["index"] == npc["index"]:
                continue
            delta = npc["pos"] - other["pos"]
            d2 = delta.lengthSquared()
            min_dist = 18.0 if npc["team"] == other["team"] else 12.0
            if 0.001 < d2 < min_dist * min_dist:
                delta.normalize()
                avoid += delta * ((min_dist - math.sqrt(d2)) / min_dist)
        if avoid.lengthSquared() > 0.0:
            desired += avoid * 1.25
        return desired



    def apply_profile_to_actor(self, visual: NodePath, emissives: list[NodePath], profile: dict) -> None:
        body_tint = profile.get("body_tint", (1.0, 1.0, 1.0, 1.0))
        primary = profile.get("primary", (0.30, 1.0, 0.44, 1.0))
        secondary = profile.get("secondary", (0.8, 1.0, 0.9, 1.0))
        accent = profile.get("accent", (1.0, 1.0, 1.0, 1.0))
        cape_geos = visual.getPythonTag("cape_geos") or []
        suit_style = str(profile.get("suit_style", "spectral"))

        def mix(c1, c2, a: float):
            return (
                clamp(c1[0] * (1.0 - a) + c2[0] * a, 0.0, 1.0),
                clamp(c1[1] * (1.0 - a) + c2[1] * a, 0.0, 1.0),
                clamp(c1[2] * (1.0 - a) + c2[2] * a, 0.0, 1.0),
                1.0,
            )

        style_map = {
            "spectral": (0.36, 0.52, 0.42, 0.64, 0.58),
            "assault": (0.44, 0.52, 0.28, 0.74, 0.66),
            "royal": (0.32, 0.58, 0.48, 0.68, 0.62),
            "stealth": (0.24, 0.40, 0.18, 0.52, 0.54),
            "circuit": (0.46, 0.48, 0.44, 0.66, 0.60),
            "scarab": (0.42, 0.54, 0.28, 0.72, 0.60),
            "phoenix": (0.38, 0.56, 0.52, 0.68, 0.60),
            "celestial": (0.28, 0.62, 0.54, 0.66, 0.60),
            "ranger": (0.36, 0.44, 0.24, 0.70, 0.60),
            "hunter": (0.34, 0.46, 0.26, 0.68, 0.58),
            "surfer": (0.52, 0.58, 0.52, 0.62, 0.56),
            "metallic": (0.40, 0.62, 0.34, 0.70, 0.64),
            "sentinel": (0.34, 0.60, 0.30, 0.72, 0.62),
            "infernal": (0.28, 0.48, 0.42, 0.60, 0.58),
            "mecha": (0.30, 0.66, 0.30, 0.74, 0.68),
            "regal": (0.28, 0.64, 0.46, 0.66, 0.64),
            "xeno": (0.30, 0.42, 0.18, 0.56, 0.56),
            "demon_knight": (0.24, 0.56, 0.30, 0.60, 0.62),
        }
        body_mix, armor_mix, accent_mix, body_alpha, armor_alpha = style_map.get(suit_style, style_map["spectral"])

        body_color = mix(body_tint, primary, body_mix)
        armor_color = mix(primary, secondary, armor_mix)
        helmet_color = mix(armor_color, accent, accent_mix)
        visor_color = mix(secondary, accent, 0.42 if suit_style in ("circuit", "phoenix", "surfer", "celestial") else 0.28)
        holo_shell = mix(primary, secondary, 0.50)
        holo_edge = mix(accent, secondary, 0.34)
        visual.setTransparency(TransparencyAttrib.M_alpha)

        for node in visual.findAllMatches("**/+GeomNode"):
            name = node.getName().lower()
            node.setTransparency(TransparencyAttrib.M_alpha)
            if any(key in name for key in ("pelvis", "abdomen", "chest", "upperarm", "forearm", "thigh", "shin")):
                glow_mix = mix(body_color, holo_shell, 0.22 if suit_style == "stealth" else 0.34 if "chest" in name else 0.28)
                alpha = max(0.42, body_alpha if "chest" not in name else min(0.90, body_alpha + 0.08))
                node.setColorScale(glow_mix[0], glow_mix[1], glow_mix[2], alpha)
            elif any(key in name for key in ("helmet", "jaw", "shoulder", "hand", "foot", "knee", "calf", "clavicle", "plate", "guard", "fin", "blade")):
                color = helmet_color if ("helmet" in name or "jaw" in name) else mix(armor_color, holo_edge, 0.22)
                local_alpha = max(0.46, armor_alpha if "helmet" not in name else min(0.92, armor_alpha + 0.08))
                node.setColorScale(color[0], color[1], color[2], local_alpha)
            elif "visor" in name:
                node.setLightOff(True)
                node.setColorScale(visor_color[0], visor_color[1], visor_color[2], 0.90)
            elif "cape_geo" in name:
                node.hide()

        for node in emissives:
            alpha = max(0.24, node.getColorScale().w)
            name = node.getName().lower()
            color = mix(primary, secondary, 0.30)
            if "eye" in name or "emblem" in name:
                color = mix(secondary, accent, 0.22)
                alpha = max(alpha, 0.92)
            elif "trail" in name:
                color = mix(accent, secondary, 0.18)
                alpha = 0.68
            elif suit_style in ("circuit", "phoenix", "surfer", "celestial", "mecha", "sentinel", "metallic"):
                color = mix(color, accent, 0.34)
                alpha = max(alpha, 0.82)
            node.setLightOff(True)
            node.setTransparency(TransparencyAttrib.M_alpha)
            node.setColorScale(min(1.0, color[0] * 1.85 + 0.18), min(1.0, color[1] * 1.85 + 0.18), min(1.0, color[2] * 1.92 + 0.20), alpha)

        for node in cape_geos:
            node.hide()

        aura_shell = visual.getPythonTag("aura_shell")
        if aura_shell is not None:
            aura_glow = float(profile.get("aura_glow", 0.0))
            if aura_glow > 0.03:
                aura_color = profile.get("aura_color", mix(accent, secondary, 0.5))
                aura_shell.show()
                aura_shell.setScale(visual.getScale() * (1.02 + aura_glow * 0.08))
                aura_shell.setColorScale(min(1.0, aura_color[0] * 1.7 + 0.18), min(1.0, aura_color[1] * 1.7 + 0.18), min(1.0, aura_color[2] * 1.7 + 0.18), 0.08 + aura_glow * 0.32)
            else:
                aura_shell.hide()


    def customize_npc_helmet(self, npc: dict) -> None:
        parts = npc["parts"]
        helmet_geo = parts.get("helmet_geo")
        if helmet_geo is None:
            return
        profile = npc["profile"]
        primary = profile.get("primary", (1.0, 0.2, 0.2, 1.0))
        secondary = profile.get("secondary", (1.0, 1.0, 1.0, 1.0))
        accent = profile.get("accent", secondary)
        armor_color = tuple(min(1.0, c * 0.58 + 0.16) for c in primary[:3]) + (0.94,)
        emissive_color = tuple(min(1.0, c * 1.35 + 0.18) for c in secondary[:3]) + (0.94,)
        accent_color = tuple(min(1.0, c * 1.20 + 0.10) for c in accent[:3]) + (0.94,)
        kind = str(profile.get("helmet", "crest"))

        for old in helmet_geo.getPythonTag("helmet_extras") or []:
            try:
                if old is not None and not old.isEmpty():
                    old.removeNode()
            except Exception:
                pass
        helmet_geo.setPythonTag("helmet_extras", [])

        helmet_scale = profile.get("helmet_scale", (1.0, 1.0, 1.0))
        visor_scale = profile.get("visor_scale", (1.0, 1.0, 1.0))
        jaw_scale = profile.get("jaw_scale", (1.0, 1.0, 1.0))
        helmet_geo.setScale(*helmet_scale)
        visor_geo = parts.get("visor_geo")
        if visor_geo is not None:
            visor_geo.setScale(*visor_scale)
        jaw_geo = parts.get("jaw_geo")
        if jaw_geo is not None:
            jaw_geo.setScale(*jaw_scale)

        extras = []
        visual = npc.get("visual")
        for old in (visual.getPythonTag("wing_extras") or []) if visual is not None else []:
            try:
                if old is not None and not old.isEmpty():
                    old.removeNode()
            except Exception:
                pass
        wing_extras = []

        def add_geom(np: NodePath, pos=(0, 0, 0), hpr=(0, 0, 0), scale=(1, 1, 1), glow=False, tint="armor", parent=None, wire=False, alpha=None):
            target = helmet_geo if parent is None else parent
            np.reparentTo(target)
            np.setPos(*pos)
            np.setHpr(*hpr)
            np.setScale(*scale)
            np.setTransparency(TransparencyAttrib.M_alpha)
            if wire:
                np.setRenderModeWireframe()
                np.setTwoSided(True)
            if glow:
                np.setLightOff(True)
                np.setDepthWrite(False)
                np.setBin("fixed", 20)
                color = emissive_color if tint != "accent" else accent_color
                use_alpha = 0.84 if alpha is None else alpha
                np.setColorScale(color[0], color[1], color[2], use_alpha)
            else:
                color = armor_color if tint == "armor" else accent_color
                use_alpha = 0.94 if alpha is None else alpha
                np.setColorScale(color[0], color[1], color[2], use_alpha)
            extras.append(np)
            return np

        if kind == "horns":
            for sx in (-1, 1):
                horn = _SMOOTH_FACTORY.cylinder(f"npc_horn_{sx}", 0.04, 0.28, 14)
                add_geom(horn, pos=(0.06 * sx, -0.01, 0.16), hpr=(0, -28, 32 * sx), scale=(0.72, 0.72, 1.12))
                tip = NodePath(GeomFactory.make_pyramid(0.06, 0.06, 0.12, 1.0, 1.0))
                add_geom(tip, pos=(0.06 * sx, 0.02, 0.30), hpr=(0, -20, 0), glow=True)
        elif kind == "fins":
            for sx in (-1, 1):
                fin = NodePath(GeomFactory.make_pyramid(0.08, 0.18, 0.24, 1.0, 1.0))
                add_geom(fin, pos=(0.12 * sx, -0.02, 0.04), hpr=(90 * sx, 8, 0), scale=(1.0, 1.2, 1.12))
            add_geom(NodePath(GeomFactory.make_box(0.04, 0.30, 0.08)), pos=(0.0, -0.05, 0.18), hpr=(0, 8, 0), glow=True)
        elif kind == "halo":
            ring = _SMOOTH_FACTORY.cylinder("npc_halo_ring", 0.12, 0.022, 22)
            add_geom(ring, pos=(0.0, -0.04, 0.28), hpr=(0, 90, 0), glow=True, scale=(1.18, 1.18, 1.0), tint="accent")
            add_geom(NodePath(GeomFactory.make_box(0.16, 0.18, 0.05)), pos=(0.0, 0.05, 0.10), scale=(1.05, 1.0, 1.0))
        elif kind == "blade":
            add_geom(NodePath(GeomFactory.make_pyramid(0.08, 0.16, 0.34, 1.0, 1.0)), pos=(0.0, -0.02, 0.30), hpr=(0, 6, 0), scale=(0.8, 1.0, 1.22))
            add_geom(NodePath(GeomFactory.make_box(0.03, 0.28, 0.05)), pos=(0.0, -0.04, 0.18), glow=True, scale=(1.0, 1.18, 1.0))
        elif kind == "crown":
            for sx in (-1, 0, 1):
                add_geom(NodePath(GeomFactory.make_pyramid(0.06, 0.10, 0.18, 1.0, 1.0)), pos=(0.07 * sx, -0.02, 0.22), hpr=(0, 4 + abs(sx) * 6, 0), scale=(1.0, 1.0, 1.16), tint="accent" if sx == 0 else "armor")
            add_geom(NodePath(GeomFactory.make_box(0.18, 0.18, 0.06)), pos=(0.0, 0.02, 0.10), glow=True, scale=(1.1, 1.0, 1.0))
        elif kind == "split":
            for sx in (-1, 1):
                add_geom(NodePath(GeomFactory.make_pyramid(0.06, 0.12, 0.22, 1.0, 1.0)), pos=(0.05 * sx, -0.03, 0.22), hpr=(0, 8, 12 * sx), scale=(0.9, 1.0, 1.12))
            add_geom(NodePath(GeomFactory.make_box(0.18, 0.05, 0.03)), pos=(0.0, 0.10, 0.05), glow=True, scale=(1.1, 1.0, 1.0))
        elif kind == "block":
            helmet_geo.setScale(helmet_scale[0] * 0.82, helmet_scale[1] * 0.84, helmet_scale[2] * 0.78)
            add_geom(NodePath(GeomFactory.make_box(0.24, 0.20, 0.22)), pos=(0.0, 0.00, 0.05), scale=(1.18, 1.08, 1.08))
            add_geom(NodePath(GeomFactory.make_box(0.20, 0.04, 0.04)), pos=(0.0, 0.10, 0.08), glow=True)
        elif kind == "pyramid":
            helmet_geo.setScale(helmet_scale[0] * 0.72, helmet_scale[1] * 0.72, helmet_scale[2] * 0.74)
            add_geom(NodePath(GeomFactory.make_pyramid(0.24, 0.24, 0.28, 1.0, 1.0)), pos=(0.0, -0.02, 0.04), hpr=(45.0, 0.0, 0.0), scale=(1.0, 1.0, 1.08))
            add_geom(NodePath(GeomFactory.make_box(0.04, 0.18, 0.18)), pos=(0.0, 0.02, 0.12), glow=True, tint="accent")
        elif kind == "ram":
            for sx in (-1, 1):
                horn = _SMOOTH_FACTORY.cylinder(f"npc_ram_horn_{sx}", 0.05, 0.26, 14)
                add_geom(horn, pos=(0.07 * sx, 0.02, 0.18), hpr=(0, -30, 64 * sx), scale=(0.84, 0.84, 1.0))
            add_geom(NodePath(GeomFactory.make_box(0.22, 0.08, 0.08)), pos=(0.0, 0.05, 0.14), tint="accent")
            add_geom(NodePath(GeomFactory.make_box(0.04, 0.08, 0.12)), pos=(0.0, 0.10, 0.08), glow=True)
        elif kind == "cage":
            for sx in (-1, 0, 1):
                add_geom(NodePath(GeomFactory.make_box(0.02, 0.12, 0.22)), pos=(0.05 * sx, 0.08, 0.05))
            add_geom(NodePath(GeomFactory.make_box(0.22, 0.06, 0.04)), pos=(0.0, 0.06, 0.16), glow=True, tint="accent")
        elif kind == "orb":
            add_geom(_SMOOTH_FACTORY.uv_sphere("npc_orb_helmet", 0.13, 18, 14), pos=(0.0, 0.02, 0.06), scale=(1.12, 1.00, 1.14), tint="armor")
            add_geom(_SMOOTH_FACTORY.cylinder("npc_orb_band", 0.16, 0.02, 18), pos=(0.0, 0.02, 0.06), hpr=(0, 90, 0), glow=True, tint="accent")
        elif kind == "mandibles":
            for sx in (-1, 1):
                add_geom(NodePath(GeomFactory.make_box(0.04, 0.18, 0.18)), pos=(0.07 * sx, 0.10, -0.02), hpr=(0, -18, 18 * sx), tint="armor")
                add_geom(NodePath(GeomFactory.make_box(0.02, 0.12, 0.10)), pos=(0.05 * sx, 0.16, -0.08), hpr=(0, -12, 10 * sx), glow=True, tint="accent")
        elif kind == "hood":
            add_geom(NodePath(GeomFactory.make_box(0.28, 0.24, 0.22)), pos=(0.0, -0.04, 0.08), scale=(1.06, 1.18, 1.16), tint="armor")
            add_geom(NodePath(GeomFactory.make_box(0.18, 0.04, 0.10)), pos=(0.0, 0.10, 0.08), glow=True, tint="accent")
        elif kind == "cowl":
            add_geom(NodePath(GeomFactory.make_box(0.24, 0.18, 0.18)), pos=(0.0, 0.00, 0.06), scale=(1.12, 1.0, 1.04), tint="armor")
            for sx in (-1, 1):
                add_geom(NodePath(GeomFactory.make_pyramid(0.05, 0.08, 0.14, 1.0, 1.0)), pos=(0.06 * sx, -0.02, 0.20), hpr=(0, 4, 0), tint="accent")
        elif kind == "spires":
            for sx in (-1, 0, 1):
                add_geom(NodePath(GeomFactory.make_pyramid(0.05, 0.08, 0.24, 1.0, 1.0)), pos=(0.05 * sx, -0.04, 0.18 + abs(sx) * 0.02), hpr=(0, 4, 0), tint="accent" if sx == 0 else "armor")
            add_geom(NodePath(GeomFactory.make_box(0.18, 0.06, 0.04)), pos=(0.0, 0.06, 0.10), glow=True)
        elif kind == "antenna":
            for sx in (-1, 1):
                stem = NodePath(GeomFactory.make_box(0.02, 0.02, 0.24))
                add_geom(stem, pos=(0.06 * sx, -0.02, 0.22), hpr=(0.0, -8.0, 12.0 * sx), tint="armor")
                orb = _SMOOTH_FACTORY.uv_sphere(f"npc_antenna_orb_{sx}", 0.035, 10, 8)
                add_geom(orb, pos=(0.08 * sx, -0.02, 0.34), glow=True, tint="accent")
        elif kind == "beak":
            add_geom(NodePath(GeomFactory.make_pyramid(0.16, 0.22, 0.22, 1.0, 1.0)), pos=(0.0, 0.08, -0.01), hpr=(45.0, -60.0, 0.0), scale=(1.0, 0.85, 0.90), tint="armor")
            add_geom(NodePath(GeomFactory.make_box(0.12, 0.04, 0.04)), pos=(0.0, 0.10, 0.08), glow=True, tint="accent")
        elif kind == "frill":
            for sx in (-1, -0.5, 0, 0.5, 1):
                add_geom(NodePath(GeomFactory.make_pyramid(0.04, 0.06, 0.14, 1.0, 1.0)), pos=(0.05 * sx, -0.08, 0.18 + abs(sx) * 0.02), hpr=(0.0, 18.0, 0.0), tint="armor" if sx else "accent")
            add_geom(NodePath(GeomFactory.make_box(0.20, 0.04, 0.04)), pos=(0.0, 0.06, 0.12), glow=True, tint="accent")
        elif kind == "arc":
            arc_root = helmet_geo.attachNewNode("arc_root")
            for sx in (-1, 1):
                segment = NodePath(GeomFactory.make_box(0.18, 0.02, 0.05))
                add_geom(segment, parent=arc_root, pos=(0.12 * sx, -0.02, 0.24), hpr=(0.0, 0.0, -28.0 * sx), glow=True, tint="accent")
                wing_extras.append(segment)
        elif kind == "visorwide" or kind == "mask":
            helmet_geo.setScale(helmet_scale[0] * 0.94, helmet_scale[1] * 0.90, helmet_scale[2] * 0.92)
            add_geom(NodePath(GeomFactory.make_box(0.24, 0.16, 0.14)), pos=(0.0, 0.04, 0.06), tint="armor")
            add_geom(NodePath(GeomFactory.make_box(0.22, 0.03, 0.05)), pos=(0.0, 0.10, 0.08), glow=True, tint="accent")
        else:
            add_geom(NodePath(GeomFactory.make_pyramid(0.12, 0.26, 0.24, 1.0, 1.0)), pos=(0.0, -0.02, 0.22), scale=(1.0, 1.0, 1.2))
            add_geom(NodePath(GeomFactory.make_box(0.03, 0.22, 0.10)), pos=(0.0, -0.02, 0.08), glow=True, scale=(1.0, 1.2, 1.0))

        if visual is not None and profile.get("wire_wings", False):
            wing_root = visual.attachNewNode("wire_wings_root")
            wing_root.setPos(0.0, -0.18, 1.34)
            wing_color = accent_color
            wing_style = str(profile.get("wing_style", "tech"))
            wing_span = float(profile.get("wing_span", 1.0))
            if profile.get("giant_wings", False):
                wing_span *= 1.55

            def add_wing_piece(size, pos, hpr, alpha=0.62, glow=False, tint="accent"):
                color = wing_color if tint == "accent" else armor_color
                panel = NodePath(GeomFactory.make_box(size[0], max(0.01, size[1] * 1.6), size[2]))
                panel.reparentTo(wing_root)
                panel.setPos(*pos)
                panel.setHpr(*hpr)
                panel.setTwoSided(True)
                panel.setLightOff(True)
                panel.setTransparency(TransparencyAttrib.M_alpha)
                panel.setDepthWrite(False)
                panel.setBin("transparent", 21)
                panel.setColorScale(color[0] * 0.92, color[1] * 0.96, min(1.0, color[2] * 1.04 + 0.06), alpha * 0.34)
                wing_extras.append(panel)

                piece = NodePath(GeomFactory.make_box(size[0], size[1], size[2]))
                piece.reparentTo(wing_root)
                piece.setPos(*pos)
                piece.setHpr(*hpr)
                piece.setRenderModeWireframe()
                piece.setTwoSided(True)
                piece.setLightOff(True)
                piece.setTransparency(TransparencyAttrib.M_alpha)
                piece.setDepthWrite(False)
                piece.setBin("fixed", 22)
                piece.setColorScale(color[0], color[1], color[2], alpha)
                if glow:
                    piece.setBin("fixed", 23)
                    piece.setColorScale(min(1.0, color[0] * 1.20 + 0.12), min(1.0, color[1] * 1.20 + 0.12), min(1.0, color[2] * 1.20 + 0.12), min(1.0, alpha + 0.12))
                wing_extras.append(piece)
                return piece

            for sx in (-1, 1):
                if wing_style == "angel":
                    add_wing_piece((0.52 * wing_span, 0.02, 0.07), (0.24 * sx, -0.02, 0.12), (0.0, 0.0, -24.0 * sx), 0.68)
                    add_wing_piece((0.44 * wing_span, 0.02, 0.06), (0.34 * sx, -0.01, 0.00), (0.0, 0.0, -10.0 * sx), 0.56)
                    add_wing_piece((0.36 * wing_span, 0.02, 0.05), (0.20 * sx, -0.01, -0.14), (0.0, 0.0, 8.0 * sx), 0.46)
                elif wing_style == "bat":
                    add_wing_piece((0.70 * wing_span, 0.02, 0.09), (0.28 * sx, -0.02, 0.10), (0.0, 0.0, -18.0 * sx), 0.52)
                    add_wing_piece((0.56 * wing_span, 0.02, 0.08), (0.50 * sx, -0.01, -0.10), (0.0, 0.0, -36.0 * sx), 0.42)
                    add_wing_piece((0.42 * wing_span, 0.02, 0.06), (0.22 * sx, -0.01, -0.20), (0.0, 0.0, 14.0 * sx), 0.38)
                elif wing_style == "surf":
                    board_panel = NodePath(GeomFactory.make_box(0.22, 0.08, 0.96))
                    board_panel.reparentTo(wing_root)
                    board_panel.setPos(0.0, -0.03, -0.02)
                    board_panel.setHpr(0.0, 18.0 * sx, -8.0 * sx)
                    board_panel.setTwoSided(True)
                    board_panel.setLightOff(True)
                    board_panel.setTransparency(TransparencyAttrib.M_alpha)
                    board_panel.setDepthWrite(False)
                    board_panel.setBin("transparent", 21)
                    board_panel.setColorScale(wing_color[0] * 0.90, wing_color[1] * 0.96, min(1.0, wing_color[2] * 1.04 + 0.06), 0.18)
                    wing_extras.append(board_panel)

                    board = NodePath(GeomFactory.make_box(0.20, 0.05, 0.92))
                    board.reparentTo(wing_root)
                    board.setPos(0.0, -0.03, -0.02)
                    board.setHpr(0.0, 18.0 * sx, -8.0 * sx)
                    board.setRenderModeWireframe()
                    board.setTwoSided(True)
                    board.setLightOff(True)
                    board.setTransparency(TransparencyAttrib.M_alpha)
                    board.setDepthWrite(False)
                    board.setBin("fixed", 22)
                    board.setColorScale(wing_color[0], wing_color[1], wing_color[2], 0.42)
                    wing_extras.append(board)
                else:
                    add_wing_piece((0.42 * wing_span, 0.02, 0.06), (0.24 * sx, -0.02, 0.10), (0.0, 0.0, -22.0 * sx), 0.62)
                    add_wing_piece((0.34 * wing_span, 0.02, 0.05), (0.18 * sx, -0.01, -0.04), (0.0, 0.0, -8.0 * sx), 0.48)
                    add_wing_piece((0.30 * wing_span, 0.02, 0.05), (0.38 * sx, -0.02, -0.12), (0.0, 0.0, -36.0 * sx), 0.40, glow=True)
            visual.setPythonTag("wing_extras", wing_extras)
        elif visual is not None:
            visual.setPythonTag("wing_extras", [])

        tail_nodes = []
        if visual is not None and str(profile.get("tail_style", "none")) != "none":
            tail_root = visual.attachNewNode("tail_root")
            tail_root.setPos(0.0, -0.12, 0.92)
            tail_style = str(profile.get("tail_style", "spine"))
            tail_length = float(profile.get("tail_length", 0.50))
            segments = 4 if tail_length < 0.55 else 5
            parent_tail = tail_root
            for seg_i in range(segments):
                seg_len = max(0.12, tail_length / segments)
                seg = NodePath(GeomFactory.make_box(0.06 if tail_style != "blade" else 0.08, 0.05, seg_len))
                seg.reparentTo(parent_tail)
                seg.setPos(0.0, -0.02 - seg_len * 0.45, -seg_len * 0.30)
                seg.setHpr(0.0, -16.0 - seg_i * 6.0, 0.0)
                seg.setTransparency(TransparencyAttrib.M_alpha)
                seg.setColorScale(armor_color[0], armor_color[1], armor_color[2], 0.78)
                tail_nodes.append(seg)
                glow_seg = NodePath(GeomFactory.make_box(0.025, 0.012, seg_len * 0.82))
                glow_seg.reparentTo(seg)
                glow_seg.setPos(0.0, 0.022, 0.0)
                glow_seg.setLightOff(True)
                glow_seg.setTransparency(TransparencyAttrib.M_alpha)
                glow_seg.setDepthWrite(False)
                glow_seg.setBin("fixed", 23)
                glow_seg.setColorScale(accent_color[0], accent_color[1], accent_color[2], 0.52)
                tail_nodes.append(glow_seg)
                child = seg.attachNewNode(f"tail_joint_{seg_i}")
                child.setPos(0.0, -0.01, -seg_len * 0.70)
                parent_tail = child
            tip = NodePath(GeomFactory.make_pyramid(0.10 if tail_style == "blade" else 0.06, 0.10 if tail_style == "blade" else 0.06, 0.14, 1.0, 1.0))
            tip.reparentTo(parent_tail)
            tip.setPos(0.0, -0.02, -0.06)
            tip.setHpr(45.0 if tail_style == "blade" else 0.0, -90.0, 0.0)
            tip.setTransparency(TransparencyAttrib.M_alpha)
            tip.setColorScale(accent_color[0], accent_color[1], accent_color[2], 0.78)
            tail_nodes.append(tip)
            visual.setPythonTag("tail_extras", tail_nodes)
        elif visual is not None:
            visual.setPythonTag("tail_extras", [])

        if profile.get("big_horns", False) and kind in ("horns", "ram", "spires", "frill"):
            for extra in helmet_geo.getPythonTag("helmet_extras") or []:
                try:
                    scale = extra.getScale()
                    extra.setScale(scale.x * 1.28, scale.y * 1.18, scale.z * 1.42)
                    extra.setZ(extra.getZ() + 0.03)
                except Exception:
                    pass

        helmet_geo.setPythonTag("helmet_extras", extras)

    def add_npc_back_pattern(self, npc: dict) -> None:
        visual = npc.get("visual")
        if visual is None:
            return
        old_root = npc.get("back_pattern_root")
        if old_root is not None:
            try:
                if not old_root.isEmpty():
                    old_root.removeNode()
            except Exception:
                pass
        pattern_root = visual.attachNewNode(f"npc_back_pattern_{npc['index']}")
        pattern_root.setPos(0.0, -0.165, 1.34)
        profile = npc["profile"]
        primary = profile.get("primary", (1.0, 1.0, 1.0, 1.0))
        secondary = profile.get("secondary", (1.0, 1.0, 1.0, 1.0))
        accent = profile.get("accent", secondary)
        pattern_kind = str(profile.get("back_pattern", profile.get("helmet", "crest")))

        color_primary = (min(1.0, primary[0] * 1.50), min(1.0, primary[1] * 1.50), min(1.0, primary[2] * 1.50), 0.82)
        color_secondary = (min(1.0, secondary[0] * 1.45), min(1.0, secondary[1] * 1.45), min(1.0, secondary[2] * 1.45), 0.78)
        color_accent = (min(1.0, accent[0] * 1.35), min(1.0, accent[1] * 1.35), min(1.0, accent[2] * 1.35), 0.72)

        def add_piece(name: str, sx: float, sy: float, sz: float, pos, hpr=(0.0, 0.0, 0.0), color=color_primary, alpha: float | None = None, wire: bool = False) -> NodePath:
            node = _SMOOTH_FACTORY.box(name, sx, sy, sz)
            node.reparentTo(pattern_root)
            node.setPos(*pos)
            node.setHpr(*hpr)
            node.setLightOff(True)
            node.setTransparency(TransparencyAttrib.M_alpha)
            node.setDepthWrite(False)
            node.setBin("fixed", 24)
            if wire:
                node.setRenderModeWireframe()
                node.setTwoSided(True)
            if alpha is None:
                node.setColorScale(*color)
            else:
                node.setColorScale(color[0], color[1], color[2], alpha)
            return node

        if pattern_kind in ("halo", "crown", "orbital"):
            add_piece("back_spine_top", 0.05, 0.016, 0.18, (0.0, 0.0, 0.10), color=color_secondary)
            add_piece("back_spine_mid", 0.05, 0.016, 0.14, (0.0, 0.0, -0.06), color=color_primary)
            add_piece("back_band", 0.26, 0.016, 0.05, (0.0, 0.0, 0.02), color=color_accent, wire=pattern_kind == "orbital")
            if pattern_kind == "orbital":
                add_piece("back_orbit", 0.30, 0.014, 0.04, (0.0, 0.0, 0.04), hpr=(0.0, 0.0, 22.0), color=color_secondary, wire=True, alpha=0.58)
        elif pattern_kind in ("blade", "split", "surf"):
            add_piece("back_chevron_l", 0.06, 0.016, 0.22, (-0.06, 0.0, 0.02), hpr=(0.0, 0.0, 32.0), color=color_primary)
            add_piece("back_chevron_r", 0.06, 0.016, 0.22, (0.06, 0.0, 0.02), hpr=(0.0, 0.0, -32.0), color=color_primary)
            add_piece("back_core", 0.05, 0.016, 0.14, (0.0, 0.0, -0.10), color=color_secondary)
            if pattern_kind == "surf":
                add_piece("back_fin", 0.10, 0.016, 0.34, (0.0, 0.0, -0.02), hpr=(0.0, 0.0, 0.0), color=color_accent, wire=True, alpha=0.62)
        elif pattern_kind in ("horns", "fins", "angel"):
            add_piece("back_wing_l", 0.10, 0.016, 0.22, (-0.12, 0.0, -0.02), hpr=(0.0, 0.0, 54.0), color=color_primary)
            add_piece("back_wing_r", 0.10, 0.016, 0.22, (0.12, 0.0, -0.02), hpr=(0.0, 0.0, -54.0), color=color_primary)
            add_piece("back_tail", 0.05, 0.016, 0.18, (0.0, 0.0, -0.14), color=color_secondary)
            if pattern_kind == "angel":
                add_piece("back_halo", 0.24, 0.014, 0.04, (0.0, 0.0, 0.18), color=color_accent, wire=True, alpha=0.66)
        elif pattern_kind in ("tentacles", "spider"):
            for sx in (-1, -0.35, 0.35, 1):
                add_piece(f"back_arm_{sx}", 0.04, 0.014, 0.32, (0.10 * sx, 0.0, -0.02 - abs(sx) * 0.04), hpr=(0.0, 0.0, -34.0 * sx), color=color_secondary, wire=True, alpha=0.62)
            add_piece("back_core_spider", 0.08, 0.014, 0.16, (0.0, 0.0, 0.02), color=color_accent)
        elif pattern_kind in ("tech_spine", "sunburst"):
            add_piece("back_diamond_top", 0.05, 0.016, 0.14, (0.0, 0.0, 0.08), hpr=(0.0, 0.0, 45.0), color=color_primary)
            add_piece("back_diamond_bottom", 0.05, 0.016, 0.14, (0.0, 0.0, -0.08), hpr=(0.0, 0.0, -45.0), color=color_secondary)
            add_piece("back_spine", 0.04, 0.016, 0.24, (0.0, 0.0, 0.0), color=color_accent)
            if pattern_kind == "sunburst":
                for sx in (-1, -0.5, 0.5, 1):
                    add_piece(f"back_ray_{sx}", 0.03, 0.014, 0.18, (0.11 * sx, 0.0, 0.05), hpr=(0.0, 0.0, -30.0 * sx), color=color_primary, wire=True, alpha=0.52)
        else:
            add_piece("back_diamond_top", 0.05, 0.016, 0.14, (0.0, 0.0, 0.08), hpr=(0.0, 0.0, 45.0), color=color_primary)
            add_piece("back_diamond_bottom", 0.05, 0.016, 0.14, (0.0, 0.0, -0.08), hpr=(0.0, 0.0, -45.0), color=color_secondary)
            add_piece("back_spine", 0.04, 0.016, 0.24, (0.0, 0.0, 0.0), color=color_accent)

        npc["back_pattern_root"] = pattern_root

    def create_npcs(self) -> None:
        if not self.npc_root.isEmpty():
            self.npc_root.removeNode()
        self.npc_root = self.render.attachNewNode("npc_root")
        self.npcs = []
        self.next_npc_index = 0
        self.team_variant_cache = {}
        self.hostile_teams = {"enemy"}

        spawn_positions = [
            self.get_ally_formation_target(0),
            self.get_ally_formation_target(1),
            self.get_ally_formation_target(2),
            self.get_enemy_formation_target(0),
            self.get_enemy_formation_target(1),
            self.get_enemy_formation_target(2),
            self.get_enemy_formation_target(3),
        ]
        team_order = ["ally", "ally", "ally", "enemy", "enemy", "enemy", "enemy"]
        for i in range(7):
            team_name = team_order[i]
            seed = self.seed * 811 + i * 73 + (13 if team_name == "enemy" else 0)
            profile = self.build_roaming_profile(seed, team_name, i)
            if team_name == "enemy" and profile.get("family") != "void_spider":
                profile["helmet"] = random.choice(["horns", "block", "pyramid", "ram", "cage", "blade", "mandibles", "hood", "cowl", "spires", "antenna", "frill", "arc"])
            pos = Vec3(spawn_positions[i])
            home_anchor = Vec3(pos)
            self.spawn_npc_actor(
                profile, pos, home_anchor, int(profile.get("formation_slot", i)), team_name,
                group_anchor=Vec3(home_anchor), spawn_chunk=None, state="escort" if team_name == "ally" else "fight",
            )

        spider_seed = self.seed * 911 + 707
        spider_profile = self.build_roaming_profile(spider_seed, "enemy", 9)
        spider_profile.update({
            "name": "Night Web Reaver",
            "primary": (0.10, 0.10, 0.12, 1.0),
            "secondary": (0.62, 0.04, 0.08, 1.0),
            "accent": (0.78, 0.22, 0.24, 1.0),
            "body_tint": (0.18, 0.18, 0.22, 1.0),
            "helmet": random.choice(["mandibles", "hood", "horns", "cowl", "spires"]),
            "wire_wings": True,
            "suit_style": "stealth",
            "mode": "wire",
            "secondary_mode": "shockwave",
            "support_fx": "cloak",
            "spider_demon": True,
            "projectile_scale": 0.28,
            "cruise_speed": 64.0,
            "evade_speed": 102.0,
            "attack_interval": 1.10,
            "secondary_cd": 2.8,
        })
        spider_pos = self.get_enemy_formation_target(1) + Vec3(0.0, 26.0, 8.0)
        self.spawn_npc_actor(
            spider_profile, Vec3(spider_pos), Vec3(spider_pos), 1, "enemy",
            group_anchor=Vec3(self.get_enemy_formation_anchor()), spawn_chunk=None, state="fight",
        )

    def convert_hit_damage(self, amount: float) -> float:
        if amount >= 1.0:
            return 1.0
        return amount * 1.5

    def random_death_fx(self, pos: Vec3, color: tuple[float, float, float, float], scale: float = 1.0) -> None:
        choice = random.choice(["burst", "ring", "scan", "slash", "blink", "beam"])
        self.spawn_power_fx(choice, pos, color, 0.72 * scale if choice != "ring" else 1.1 * scale)
        self.spawn_power_fx(random.choice(["burst", "ring", "slash", "sparks", "smoke", "explosion"]), pos + Vec3(0, 0, 0.8 * scale), color, 0.58 * scale)

    def damage_player(self, amount: float, owner: str) -> None:
        if self.shield_timer > 0.0:
            return
        if not self.owner_is_enemy(owner, "ally"):
            return
        owner_team = self.owner_team(owner)
        if owner_team != "ally":
            self.activate_team_combat(f"{owner_team} engaged", owner_team)
        self.player_hp = max(0.0, self.player_hp - self.convert_hit_damage(amount))
        self.last_power_text = f"Hit by {owner}"
        self.actor_last_hit = owner
        self.spawn_power_fx("slash", self.hero_pos + Vec3(0, 0, 1.2), (1.0, 0.4, 0.3, 0.72), 0.42)
        if self.player_hp <= 0.0:
            self.random_death_fx(self.hero_pos + Vec3(0, 0, 1.2), (1.0, 0.3, 0.3, 0.80), 1.2)
            self.reset_hero()

    def damage_npc(self, npc: dict, amount: float, owner: str) -> None:
        if npc.get("dead", False):
            return
        if npc.get("shield_timer", 0.0) > 0.0:
            return
        if not self.owner_is_enemy(owner, str(npc.get("team", "neutral"))):
            return

        owner_team = self.owner_team(owner)
        target_team = str(npc.get("team", "neutral"))
        if owner_team == "ally" and target_team != "ally":
            self.activate_team_combat(f"{npc['name']} provoked", target_team)
        elif owner_team != "ally" and target_team == "ally":
            self.activate_team_combat(f"{npc['name']} under fire", owner_team)

        npc["hp"] = max(0.0, npc["hp"] - self.convert_hit_damage(amount))
        npc["state"] = "fight"
        npc["attack_variant"] = "visor"
        npc["attack_timer"] = max(npc["attack_timer"], 0.22)
        self.spawn_power_fx("slash", npc["pos"] + Vec3(0, 0, 1.2 * npc["profile"]["scale"]), npc["profile"]["secondary"], 0.36)
        if npc["hp"] <= npc["max_hp"] * 0.30 and npc["hp"] > 0.0:
            npc["recover_timer"] = max(npc["recover_timer"], 2.8)
            if npc["shield_cooldown"] <= 0.0:
                npc["shield_timer"] = 1.25
                npc["shield_cooldown"] = 4.0
                npc["shield_node"].show()
        if npc["hp"] <= 0.0:
            npc["dead"] = True
            npc["root"].hide()
            npc["shield_node"].hide()
            npc["velocity"] = Vec3(0, 0, 0)
            npc["state"] = "dead"
            self.random_death_fx(npc["pos"] + Vec3(0, 0, 1.0 * npc["profile"]["scale"]), npc["profile"]["secondary"], max(0.9, npc["profile"]["scale"]))
            team_name = str(npc.get("team", "neutral"))
            if team_name in self.hostile_teams and not any((not other.get("dead", False)) and str(other.get("team")) == team_name for other in self.npcs):
                self.hostile_teams.discard(team_name)


    def hit_actor_by_projectile(self, pos: Vec3, strong: bool, owner: str) -> bool:
        damage = 26.0 if strong else 12.0
        owner_team = self.owner_team(owner)
        police_target = self.police_alert_team if owner_team == "police" else None

        if owner_team in ("enemy", "police") and (owner_team != "police" or police_target == "ally"):
            hero_center = self.hero_pos + Vec3(0, 0, 1.25)
            if self.shield_timer > 0.0 and (hero_center - pos).lengthSquared() <= self.shield_radius ** 2:
                return True
            for part in self.hero_hit_parts:
                node = part.get("node")
                if node is not None and (node.getPos(self.render) - pos).lengthSquared() <= float(part["radius"]) ** 2:
                    self.damage_player(damage, owner)
                    return True

        for npc in self.npcs:
            npc_owner = f"npc{npc['index']}"
            if owner == npc_owner:
                continue
            target_team = str(npc.get("team"))
            if owner_team == target_team:
                continue
            if owner_team == "police" and target_team != police_target:
                continue
            center = npc["pos"] + Vec3(0, 0, 1.25 * npc["profile"]["scale"])
            if npc.get("shield_timer", 0.0) > 0.0:
                shield_radius = self.shield_radius * npc["profile"]["scale"] * 0.82
                if (center - pos).lengthSquared() <= shield_radius ** 2:
                    return True
            for part in npc.get("hit_parts", []):
                node = part.get("node")
                if node is not None and (node.getPos(self.render) - pos).lengthSquared() <= float(part["radius"]) ** 2:
                    self.damage_npc(npc, damage, owner)
                    return True
        return False

    def apply_actor_pose(self, parts: dict[str, NodePath], base_hprs: dict[str, tuple[float, float, float]], velocity: Vec3, roll: float, attack_charge: float, attack_charging: bool, attack_timer: float, attack_variant: str, shield_timer: float, dt: float, emote_name: str = "none", emote_strength: float = 0.0) -> None:
        if not parts:
            return
        speed = velocity.length()
        fly = clamp(speed / 58.0, 0.0, 1.0)
        charge_n = clamp(attack_charge / 1.4, 0.0, 1.0) if attack_charging else 0.0
        attack_norm = clamp(attack_timer / 0.70, 0.0, 1.0)
        attack_push = math.sin(min(1.0, attack_norm) * math.pi)
        overload = 1.0 if attack_variant == "overload" else 0.0
        shielding = 1.0 if shield_timer > 0.0 else 0.0
        emote_blend = clamp(emote_strength, 0.0, 1.0) if (emote_name != "none" and attack_timer <= 0.01 and shield_timer <= 0.01) else 0.0
        t = globalClock.getFrameTime()
        flutter = math.sin(t * (4.2 + fly * 3.3)) * fly
        flutter2 = math.cos(t * (4.0 + fly * 3.1)) * fly

        def apply(name: str, h: float, p: float, r: float, rate: float = 10.0):
            part = parts.get(name)
            if part is None:
                return
            bh, bp, br = base_hprs.get(name, (0.0, 0.0, 0.0))
            current = part.getHpr()
            target = Vec3(bh + h, bp + p, br + r)
            next_h = lerp_angle_deg(current.x, target.x, dt * rate)
            next_p = lerp(current.y, target.y, dt * rate)
            next_r = lerp_angle_deg(current.z, target.z, dt * rate)
            part.setHpr(next_h, next_p, next_r)

        pose_bank = clamp(roll * 0.35, -14.0, 14.0)
        shoulder_spread = 12.0 + fly * 9.0 + shielding * 16.0
        shoulder_pitch = -8.0 * fly + 36.0 * charge_n + 54.0 * attack_push + 18.0 * shielding
        elbow_flex = 12.0 + 10.0 * fly + 34.0 * charge_n + 42.0 * attack_push + 12.0 * overload + 12.0 * shielding
        hand_pitch = 4.0 + 6.0 * fly + 10.0 * charge_n + 12.0 * attack_push + 4.0 * shielding

        apply("upperarm_l", pose_bank * 0.20, shoulder_pitch + flutter * 4.0, shoulder_spread + flutter2 * 7.0, 11.0)
        apply("upperarm_r", -pose_bank * 0.20, shoulder_pitch - flutter * 4.0, -shoulder_spread - flutter2 * 7.0, 11.0)
        apply("forearm_l", 0.0, elbow_flex + flutter2 * 5.0, 4.0 + shielding * 3.0, 11.0)
        apply("forearm_r", 0.0, elbow_flex - flutter2 * 5.0, -4.0 - shielding * 3.0, 11.0)
        apply("hand_l", 0.0, hand_pitch, 0.0, 12.0)
        apply("hand_r", 0.0, hand_pitch, 0.0, 12.0)

        thigh_pitch = 12.0 * fly + flutter2 * 7.0 - shielding * 14.0
        shin_pitch = -24.0 * fly - flutter * 6.0 + shielding * 18.0
        foot_pitch = -14.0 - 14.0 * fly + shielding * 8.0

        apply("thigh_l", 0.0, thigh_pitch, pose_bank * 0.12, 9.5)
        apply("thigh_r", 0.0, thigh_pitch * 0.98, -pose_bank * 0.12, 9.5)
        apply("shin_l", 0.0, shin_pitch, 0.0, 10.0)
        apply("shin_r", 0.0, shin_pitch, 0.0, 10.0)
        apply("foot_l", 0.0, foot_pitch, 0.0, 10.0)
        apply("foot_r", 0.0, foot_pitch, 0.0, 10.0)

        if emote_blend > 0.0:
            wave = math.sin(t * 5.6) * 18.0 * emote_blend
            if emote_name == "salute":
                apply("upperarm_r", 0.0, 58.0 * emote_blend, -34.0 * emote_blend, 8.0)
                apply("forearm_r", 0.0, 84.0 * emote_blend, -8.0 * emote_blend, 8.0)
                apply("hand_r", 0.0, 18.0 * emote_blend, 0.0, 8.0)
            elif emote_name == "wave":
                apply("upperarm_r", 0.0, 74.0 * emote_blend, -58.0 * emote_blend, 8.0)
                apply("forearm_r", 0.0, 72.0 * emote_blend, wave, 8.0)
                apply("hand_r", 0.0, 12.0 * emote_blend, wave * 0.35, 8.0)
            elif emote_name == "point":
                apply("upperarm_r", 0.0, 34.0 * emote_blend, -10.0 * emote_blend, 8.0)
                apply("forearm_r", 0.0, 16.0 * emote_blend, 0.0, 8.0)
                apply("hand_r", 0.0, -8.0 * emote_blend, 0.0, 8.0)
            elif emote_name == "taunt":
                apply("upperarm_l", 0.0, 18.0 * emote_blend, 50.0 * emote_blend, 8.0)
                apply("upperarm_r", 0.0, 18.0 * emote_blend, -50.0 * emote_blend, 8.0)
                apply("forearm_l", 0.0, 42.0 * emote_blend, -8.0 * emote_blend, 8.0)
                apply("forearm_r", 0.0, 42.0 * emote_blend, 8.0 * emote_blend, 8.0)
            elif emote_name == "crossed":
                apply("upperarm_l", 0.0, 28.0 * emote_blend, 18.0 * emote_blend, 8.0)
                apply("upperarm_r", 0.0, 28.0 * emote_blend, -18.0 * emote_blend, 8.0)
                apply("forearm_l", 0.0, 64.0 * emote_blend, -14.0 * emote_blend, 8.0)
                apply("forearm_r", 0.0, 64.0 * emote_blend, 14.0 * emote_blend, 8.0)
            elif emote_name == "meditate":
                apply("upperarm_l", 0.0, 8.0 * emote_blend, 16.0 * emote_blend, 8.0)
                apply("upperarm_r", 0.0, 8.0 * emote_blend, -16.0 * emote_blend, 8.0)
                apply("forearm_l", 0.0, 56.0 * emote_blend, 0.0, 8.0)
                apply("forearm_r", 0.0, 56.0 * emote_blend, 0.0, 8.0)
                apply("hand_l", 0.0, -10.0 * emote_blend, 0.0, 8.0)
                apply("hand_r", 0.0, -10.0 * emote_blend, 0.0, 8.0)
            elif emote_name == "victory":
                apply("upperarm_l", 0.0, 82.0 * emote_blend, 44.0 * emote_blend, 8.0)
                apply("upperarm_r", 0.0, 82.0 * emote_blend, -44.0 * emote_blend, 8.0)
                apply("forearm_l", 0.0, 24.0 * emote_blend, 0.0, 8.0)
                apply("forearm_r", 0.0, 24.0 * emote_blend, 0.0, 8.0)


    def update_spider_demon_npc(self, npc: dict, dt: float, fallback_target: Vec3 | None) -> Vec3 | None:
        if not npc["profile"].get("spider_demon"):
            return None
        npc["grapple_cd"] = max(0.0, npc.get("grapple_cd", 0.0) - dt)
        npc["pull_cd"] = max(0.0, npc.get("pull_cd", 0.0) - dt)
        npc["grapple_timer"] = max(0.0, npc.get("grapple_timer", 0.0) - dt)

        if npc.get("grapple_timer", 0.0) <= 0.0 and npc.get("grapple_cd", 0.0) <= 0.0:
            best_anchor = None
            best_d2 = 160.0 * 160.0
            focus = fallback_target if fallback_target is not None else self.hero_pos
            for target in self.structure_targets:
                node = target.get("node")
                if node is None or node.isEmpty():
                    continue
                anchor = node.getPos(self.render) + Vec3(0, 0, float(target["h"]) + 8.0)
                d2 = (anchor - focus).lengthSquared()
                if d2 < best_d2:
                    best_d2 = d2
                    best_anchor = anchor
            if best_anchor is not None:
                npc["grapple_anchor"] = Vec3(best_anchor)
                npc["grapple_timer"] = 0.72
                npc["grapple_cd"] = 2.4 + random.random() * 1.1
                self.spawn_power_fx("slash", npc["pos"] + Vec3(0, 0, 1.6), npc["profile"].get("secondary", (1, 0, 0, 1)), 0.68)

        if npc.get("pull_cd", 0.0) <= 0.0:
            target_npc = self.choose_closest_npc(npc["pos"], [a for a in self.npcs if str(a.get("team")) == "ally" and not a.get("dead", False)], exclude_index=npc["index"])
            player_d2 = (self.hero_pos - npc["pos"]).lengthSquared()
            if target_npc is not None and (target_npc["pos"] - npc["pos"]).lengthSquared() < player_d2 * 0.92:
                to_spider = npc["pos"] - target_npc["pos"]
                if to_spider.lengthSquared() > 1e-6:
                    to_spider.normalize()
                    target_npc["velocity"] += to_spider * 26.0 + Vec3(0, 0, 8.0)
            else:
                to_spider = npc["pos"] - self.hero_pos
                if to_spider.lengthSquared() > 1e-6:
                    to_spider.normalize()
                    self.hero_velocity += to_spider * 22.0 + Vec3(0, 0, 7.0)
            self.spawn_power_fx("beam", npc["pos"] + Vec3(0,0,1.4), npc["profile"].get("accent", (1, 0.2, 0.2, 1)), 0.82)
            self.mark_power_activity(str(npc.get("team", "enemy")), npc["pos"] + Vec3(0,0,1.4))
            npc["pull_cd"] = 3.2 + random.random() * 1.4

        anchor = npc.get("grapple_anchor")
        if anchor is not None and npc.get("grapple_timer", 0.0) > 0.0:
            return (anchor - npc["pos"]) + Vec3(0, 0, 0.25)
        return None

    def npc_fire_attack(self, npc: dict, strong: bool = False, secondary: bool = False, target_override: Vec3 | None = None) -> None:
        team_name = str(npc.get("team", "neutral"))
        boss_active = self.boss is not None and self.boss.get("alive", False)
        if boss_active:
            target_pos = self.boss["root"].getPos() + Vec3(0, 0, 2.8)
        else:
            if team_name == "ally":
                targets = [other for other in self.npcs if str(other.get("team")) in self.hostile_teams and not other.get("dead", False)]
            else:
                targets = [ally for ally in self.npcs if str(ally.get("team")) == "ally" and not ally.get("dead", False)]

            target_actor = self.choose_closest_npc(npc["pos"], targets, exclude_index=npc["index"])
            if target_override is not None:
                target_pos = Vec3(target_override)
            elif team_name != "ally":
                if target_actor is None or (self.hero_pos - npc["pos"]).lengthSquared() <= (target_actor["pos"] - npc["pos"]).lengthSquared() * 0.88:
                    target_pos = self.hero_pos
                else:
                    target_pos = target_actor["pos"]
            else:
                target_pos = target_actor["pos"] if target_actor is not None else self.hero_pos

        forward = target_pos + Vec3(0, 0, 1.2) - (npc["pos"] + Vec3(0, 0, 1.55 * npc["profile"]["scale"]))
        if forward.lengthSquared() < 1e-6:
            forward = Vec3(0, 1, 0)
        forward.normalize()
        right = self.right_from_yaw(npc["heading"])
        up = Vec3(0, 0, 1)

        npc["attack_timer"] = 0.42 if secondary else 0.30
        npc["attack_variant"] = "overload" if strong or secondary else "visor"
        npc["attack_charge"] = 1.1 if strong or secondary else 0.72
        npc["attack_charging"] = False

        mode, origin_mode = self.launch_profile_projectiles(
            npc["profile"],
            npc["pos"],
            float(npc["profile"]["scale"]),
            npc["parts"],
            forward,
            right,
            up,
            strong,
            f"npc{npc['index']}",
            npc["heading"],
            charge_n=0.74 if secondary else 0.52,
            target_pos=target_pos,
            use_secondary=secondary,
        )
        npc["last_attack_mode"] = mode
        npc["last_attack_origin"] = origin_mode
        if secondary:
            self.activate_actor_support(npc, str(npc["profile"].get("support_fx", "none")), is_player=False)
        self.mark_power_activity(team_name, npc["pos"] + Vec3(0, 0, 1.2 * npc["profile"]["scale"]))
        if (npc["pos"] - self.hero_pos).length() < 140.0:
            self.play_sfx(f"mode_{mode}", volume=0.20, rate=0.90 + random.random() * 0.16)

    def npc_is_hostile(self, npc: dict) -> bool:
        team_name = str(npc.get("team", "neutral"))
        return team_name == "ally" or team_name in self.hostile_teams

    def choose_hostile_target_for_npc(self, npc: dict, allies: list[dict], hostiles: list[dict]) -> dict | None:
        team_name = str(npc.get("team", ""))
        pos = npc["pos"]
        if team_name == "ally":
            candidates = [other for other in self.npcs if str(other.get("team")) in self.hostile_teams]
            return self.choose_closest_npc(pos, candidates, exclude_index=npc["index"])
        if team_name in self.hostile_teams:
            return self.choose_closest_npc(pos, allies, exclude_index=npc["index"])
        return None


    def update_npcs(self, dt: float) -> None:
        if not self.npcs:
            return
        t = globalClock.getFrameTime()

        ally_npcs = [npc for npc in self.npcs if (not npc.get("dead", False)) and str(npc.get("team")) == "ally"]
        hostile_npcs = [npc for npc in self.npcs if (not npc.get("dead", False)) and str(npc.get("team")) in self.hostile_teams]

        boss_active = self.boss is not None and self.boss.get("alive", False)
        self.combat_active = bool(self.hostile_teams) or boss_active
        self.update_dynamic_group_anchors(dt)

        for target in self.structure_targets:
            target["cooldown"] = max(0.0, float(target.get("cooldown", 0.0)) - dt)

        for npc in self.npcs:
            if npc.get("dead", False):
                continue
            npc["attack_timer"] = max(0.0, npc["attack_timer"] - dt)
            npc["attack_cooldown"] = max(0.0, npc["attack_cooldown"] - dt)
            npc["secondary_cooldown"] = max(0.0, npc["secondary_cooldown"] - dt)
            npc["recover_timer"] = max(0.0, npc["recover_timer"] - dt)
            npc["shield_timer"] = max(0.0, npc["shield_timer"] - dt)
            npc["shield_cooldown"] = max(0.0, npc["shield_cooldown"] - dt)
            npc["support_timer"] = max(0.0, npc.get("support_timer", 0.0) - dt)
            npc["support_cooldown"] = max(0.0, npc.get("support_cooldown", 0.0) - dt)
            npc["emote_timer"] = max(0.0, npc.get("emote_timer", 0.0) - dt)
            npc["emote_cooldown"] = max(0.0, npc.get("emote_cooldown", 0.0) - dt)
            if npc["emote_timer"] <= 0.0 and npc.get("emote_name", "none") != "none":
                npc["emote_name"] = "none"
            npc["emote_strength"] = clamp(npc.get("emote_strength", 0.0) + (dt * 3.0 if npc.get("emote_timer", 0.0) > 0.0 else -dt * 3.0), 0.0, 1.0)
            npc["player_aggro"] = max(0.0, npc["player_aggro"] - dt)
            npc["ambient_cooldown"] = max(0.0, npc.get("ambient_cooldown", 0.0) - dt)

            root = npc["root"]
            pos = Vec3(root.getPos())
            npc["pos"] = pos
            desired = Vec3(0, 0, 0)
            team_name = str(npc.get("team", "neutral"))
            npc_hostile = team_name in self.hostile_teams

            if boss_active:
                target_pos = self.boss["root"].getPos() + Vec3(0, 0, 2.8)
                to_target = target_pos - pos
                dist = max(1.0, to_target.length())
                if to_target.lengthSquared() > 1e-6:
                    to_target.normalize()
                tangent = Vec3(-to_target.y, to_target.x, 0.0) * npc["orbit_sign"]
                if npc["recover_timer"] > 0.0 or npc["hp"] < npc["max_hp"] * 0.28:
                    npc["state"] = "recover"
                    desired = -to_target + Vec3(0, 0, 0.42)
                    if npc["shield_cooldown"] <= 0.0 and npc["shield_timer"] <= 0.0:
                        npc["shield_timer"] = 1.15
                        npc["shield_cooldown"] = 4.2
                else:
                    npc["state"] = "fight"
                    desired = tangent * 0.62 + to_target * 0.18
                    if dist > 120.0:
                        desired = to_target + Vec3(0, 0, 0.18)
                    elif dist < 32.0:
                        desired = -to_target + tangent * 0.84 + Vec3(0, 0, 0.12)
                    if npc["attack_cooldown"] <= 0.0 and dist < 230.0:
                        self.npc_fire_attack(npc, strong=(random.random() < 0.26), secondary=False, target_override=target_pos)
                        npc["attack_cooldown"] = float(npc["profile"]["attack_interval"])
                    elif npc["secondary_cooldown"] <= 0.0 and dist < 180.0:
                        self.npc_fire_attack(npc, strong=True, secondary=True, target_override=target_pos)
                        npc["secondary_cooldown"] = float(npc["profile"]["secondary_cd"])
            elif team_name == "ally":
                formation_target = self.get_group_formation_target(npc) + self.get_idle_patrol_offset(npc, team_name) * 0.55
                if self.combat_active:
                    target_actor = self.choose_closest_npc(pos, hostile_npcs, exclude_index=npc["index"])
                    if target_actor is not None:
                        target_pos = target_actor["pos"]
                        to_target = target_pos - pos
                        dist = max(1.0, to_target.length())
                        to_target.normalize()
                        stay_with_hero = formation_target - pos
                        if npc["recover_timer"] > 0.0 or npc["hp"] < npc["max_hp"] * 0.32:
                            npc["state"] = "recover"
                            desired = stay_with_hero * 0.85 - to_target * 0.30 + Vec3(0, 0, 0.28)
                            if npc["shield_cooldown"] <= 0.0 and npc["shield_timer"] <= 0.0:
                                npc["shield_timer"] = 1.10
                                npc["shield_cooldown"] = 4.0
                        else:
                            npc["state"] = "escort"
                            tangent = Vec3(-to_target.y, to_target.x, 0.0) * npc["orbit_sign"]
                            desired = stay_with_hero * 1.08 + tangent * 0.22 + Vec3(0, 0, 0.10)
                            if (pos - self.hero_pos).length() > 56.0:
                                desired = (formation_target - pos) * 1.45 + Vec3(0, 0, 0.12)
                            if npc["attack_cooldown"] <= 0.0 and dist < 220.0:
                                self.npc_fire_attack(npc, strong=(random.random() < 0.26), secondary=False, target_override=target_pos)
                                npc["attack_cooldown"] = float(npc["profile"]["attack_interval"])
                            elif npc["secondary_cooldown"] <= 0.0 and dist < 170.0:
                                self.npc_fire_attack(npc, strong=True, secondary=True, target_override=target_pos)
                                npc["secondary_cooldown"] = float(npc["profile"]["secondary_cd"])
                    else:
                        desired = formation_target - pos
                        npc["state"] = "escort"
                else:
                    desired = formation_target - pos
                    npc["state"] = "escort"
            else:
                if not npc_hostile:
                    target_pos = self.get_group_formation_target(npc) + self.get_idle_patrol_offset(npc, team_name)
                    desired = target_pos - pos
                    npc["state"] = "fight"
                    ambient_target = self.choose_ambient_target_pos(pos)
                    if ambient_target is not None and npc["attack_cooldown"] <= 0.0 and npc["ambient_cooldown"] <= 0.0:
                        self.npc_fire_attack(npc, strong=(random.random() < 0.18), secondary=(random.random() < 0.32), target_override=ambient_target)
                        npc["attack_cooldown"] = float(npc["profile"]["attack_interval"]) * 0.9
                        npc["ambient_cooldown"] = 1.4 + random.random() * 1.8
                else:
                    target_actor = self.choose_closest_npc(pos, ally_npcs, exclude_index=npc["index"])
                    target_pos = self.hero_pos if target_actor is None or (self.hero_pos - pos).lengthSquared() < (target_actor["pos"] - pos).lengthSquared() * 0.90 else target_actor["pos"]
                    to_target = target_pos - pos
                    dist = max(1.0, to_target.length())
                    to_target.normalize()
                    spider_override = self.update_spider_demon_npc(npc, dt, target_pos)
                    if npc.get("profile", {}).get("spider_demon") and spider_override is not None:
                        npc["state"] = "fight"
                        desired = spider_override
                        if npc["attack_cooldown"] <= 0.0 and dist < 200.0:
                            self.npc_fire_attack(npc, strong=(random.random() < 0.28), secondary=False, target_override=target_pos)
                            npc["attack_cooldown"] = float(npc["profile"]["attack_interval"]) * 0.88
                    elif npc["recover_timer"] > 0.0 or npc["hp"] < npc["max_hp"] * 0.32:
                        npc["state"] = "recover"
                        desired = -to_target + Vec3(0, 0, 0.38)
                        if npc["shield_cooldown"] <= 0.0 and npc["shield_timer"] <= 0.0:
                            npc["shield_timer"] = 1.15
                            npc["shield_cooldown"] = 4.0
                    else:
                        npc["state"] = "fight"
                        tangent = Vec3(-to_target.y, to_target.x, 0.0) * npc["orbit_sign"]
                        desired = tangent + to_target * 0.24
                        if dist > 92.0:
                            desired = to_target + Vec3(0, 0, 0.12)
                        elif dist < 34.0:
                            desired = -to_target + tangent * 0.68 + Vec3(0, 0, 0.06)
                        if npc["attack_cooldown"] <= 0.0 and dist < 170.0:
                            self.npc_fire_attack(npc, strong=(random.random() < 0.20), secondary=False, target_override=target_pos)
                            npc["attack_cooldown"] = float(npc["profile"]["attack_interval"])
                        elif npc["secondary_cooldown"] <= 0.0 and dist < 130.0:
                            self.npc_fire_attack(npc, strong=True, secondary=True, target_override=target_pos)
                            npc["secondary_cooldown"] = float(npc["profile"]["secondary_cd"])

            if npc.get("state") in ("neutral", "escort"):
                self.maybe_trigger_npc_emote(npc)
            else:
                npc["emote_name"] = "none"
            desired = self.apply_npc_team_avoidance(npc, desired)
            desired_len = desired.length()
            if desired_len < 0.45 and npc["state"] in ("escort", "neutral"):
                desired = Vec3(0, 0, 0)
            elif desired_len > 1e-6:
                desired.normalize()
            else:
                desired = Vec3(0, 1, 0)

            speed = float(npc["profile"]["evade_speed"] if npc["state"] == "recover" else npc["profile"]["cruise_speed"])
            if npc["state"] == "escort":
                speed *= 0.92
            elif npc["state"] == "neutral":
                speed *= 0.68
            target_vel = desired * speed if desired.lengthSquared() > 0.0 else Vec3(0, 0, 0)
            steer_rate = 3.6 if npc["state"] == "recover" else 3.2 if npc["state"] == "fight" else 3.0 if npc["state"] == "escort" else 2.4
            npc["velocity"] = approach_vec(npc["velocity"], target_vel, steer_rate, dt)
            npc["velocity"] *= (0.92 if npc["state"] in ("escort", "neutral") else 0.988) ** (dt * 60.0)
            pos += npc["velocity"] * dt
            pos = self.clamp_to_render_block(pos, margin=14.0)
            z_min = 10.0 if npc["state"] == "escort" else 12.0 if npc["state"] == "neutral" else 18.0
            z_max = 180.0 if npc["state"] in ("escort", "neutral") else 280.0
            pos.z = clamp(pos.z, z_min, z_max)
            npc["pos"] = pos
            root.setPos(pos)

            if npc["velocity"].length() > 0.35:
                desired_heading = math.degrees(math.atan2(npc["velocity"].x, npc["velocity"].y))
            elif team_name == "ally":
                desired_heading = self.hero_heading
            else:
                desired_heading = npc["heading"]

            npc["heading"] = lerp_angle_deg(npc["heading"], desired_heading, dt * (7.5 if team_name == "ally" else 5.4))
            if npc["state"] in ("escort", "neutral"):
                pitch_target = 0.0
                roll_target = 0.0
            else:
                pitch_target = clamp(-npc["velocity"].z * 0.35 - npc["velocity"].length() * 0.03, -22.0, 10.0)
                right = self.right_from_yaw(npc["heading"])
                roll_target = clamp(-npc["velocity"].dot(right) * 0.30, -24.0, 24.0)
            npc["pitch"] = lerp(npc["pitch"], pitch_target, dt * 3.0)
            npc["roll"] = lerp(npc["roll"], roll_target, dt * 3.0)
            root.setHpr(npc["heading"], npc["pitch"], npc["roll"])
            desired_head = clamp(((npc.get("heading", 0.0) - self.hero_heading + 180.0) % 360.0) - 180.0, -10.0, 10.0) * 0.25
            for node in npc.get("head_nodes", []):
                node.setH(desired_head)
            self.update_propulsion_rig(npc.get("propulsion"), npc["velocity"].length(), 0.35 if npc["state"] in ("fight", "recover") else 0.0, True)

            if npc["shield_timer"] > 0.0:
                npc["shield_node"].show()
                pulse = 0.20 + 0.12 * math.sin(t * 8.0 + npc["index"])
                radius = self.shield_radius * npc["profile"]["scale"] * 0.82
                npc["shield_node"].setScale(radius * (1.0 + pulse * 0.05))
                sec = npc["profile"]["secondary"]
                npc["shield_node"].setColorScale(sec[0] * 1.2, sec[1] * 1.2, sec[2] * 1.2, 0.16 + pulse * 0.22)
                center = pos + Vec3(0, 0, 1.3 * npc["profile"]["scale"])
                if team_name != "ally":
                    if (center - (self.hero_pos + Vec3(0, 0, 1.3))).lengthSquared() <= (radius + 1.8) ** 2 and self.shield_timer <= 0.0:
                        self.damage_player(10.0 * dt, npc["name"])
                    for ally in ally_npcs:
                        ally_center = ally["pos"] + Vec3(0, 0, 1.3 * ally["profile"]["scale"])
                        if ally["index"] != npc["index"] and (ally_center - center).lengthSquared() <= (radius + ally["hit_radius"]) ** 2:
                            self.damage_npc(ally, 12.0 * dt, f"npc{npc['index']}")
                else:
                    for hostile in hostile_npcs:
                        hostile_center = hostile["pos"] + Vec3(0, 0, 1.3 * hostile["profile"]["scale"])
                        if (hostile_center - center).lengthSquared() <= (radius + hostile["hit_radius"]) ** 2:
                            self.damage_npc(hostile, 12.0 * dt, f"npc{npc['index']}")
                for car in self.traffic_cars:
                    if car.get("active", False) and (car["node"].getPos() - center).lengthSquared() <= (radius + car["radius"] * 0.55) ** 2:
                        self.destroy_traffic_car(car, strong=True)
            else:
                npc["shield_node"].hide()

            self.apply_actor_pose(
                npc["parts"],
                npc["base_hprs"],
                npc["velocity"],
                npc["roll"],
                npc["attack_charge"],
                npc["attack_charging"],
                npc["attack_timer"],
                npc["attack_variant"],
                npc["shield_timer"],
                dt,
                npc.get("emote_name", "none"),
                npc.get("emote_strength", 0.0),
            )


    def create_hero(self) -> None:
        self.hero_visual = build_sheet_style_hero(self.hero_root)
        self.hero_visual.setScale(1.36)
        self.hero_parts = self.hero_visual.getPythonTag("parts") or {}
        self.hero_base_hprs = self.hero_visual.getPythonTag("base_hprs") or {}
        self.hero_emissives = self.hero_visual.getPythonTag("emissives") or []
        for node in (self.hero_visual.getPythonTag("trails") or []):
            node.hide()
        self.hero_trails = []
        self.hero_capes = []
        self.hero_cape_geos = []
        for node in self.hero_visual.getPythonTag("cape_geos") or []:
            node.hide()
        self.hero_aura_shell = self.create_actor_aura_shell(self.hero_root, self.hero_visual)
        self.hero_visual.setPythonTag("aura_shell", self.hero_aura_shell)
        self.hero_xray_shell = self.create_xray_shell(self.hero_root, self.hero_visual)
        self.hero_head_nodes = [n for n in [self.hero_visual.find("**/helmet_geo"), self.hero_visual.find("**/jaw_geo"), self.hero_visual.find("**/visor_geo"), self.hero_visual.find("**/eye_l"), self.hero_visual.find("**/eye_r")] if not n.isEmpty()]
        self.hero_propulsion = self.create_propulsion_rig(self.hero_root, self.hero_parts, 1.0, (0.30,1.0,0.44,1.0), (0.80,1.0,0.90,1.0), style="jetpack")
        self.hero_hit_parts = self.build_actor_hit_parts(self.hero_root, self.hero_parts, 1.36)
        self.player_max_hp = 100.0
        self.player_hp = 100.0
        self.fx_textures = {kind: self.texture_factory.make_glitch(f"fx_{kind}", 5100 + i * 17) for i, kind in enumerate(["burst", "ring", "scan", "slash", "blink", "shield", "beam", "explosion", "smoke", "trail", "sparks", "laser_blast", "flame_fx", "ice", "rock", "acid", "electric"])}
        self.projectile_textures = {kind: self.texture_factory.make_glitch(f"proj_{kind}", 6200 + i * 19) for i, kind in enumerate(["bolt", "fan", "spiral", "pulse", "shard", "laser", "beam", "missile", "fireball", "wire", "shockwave", "atom", "flame", "electric"])}
        shield_tex = self.fx_textures["shield"]
        self.shield_node = _SMOOTH_FACTORY.uv_sphere("shield_orb", 1.0, 26, 18)
        self.shield_node.reparentTo(self.hero_root)
        self.shield_node.setScale(self.shield_radius)
        self.shield_node.setTexture(shield_tex, 1)
        self.shield_node.setTransparency(TransparencyAttrib.M_alpha)
        self.shield_node.setDepthWrite(False)
        self.shield_node.setBin("transparent", 48)
        self.shield_node.setLightOff(True)
        self.shield_node.setColorScale(0.30, 1.0, 0.55, 0.0)
        self.shield_node.hide()


    def randomize_power_profile(self, initial: bool = False) -> None:
        rnd = random.Random(self.seed + int(globalClock.getFrameTime() * 1000.0) + random.randint(0, 999999))
        theme = rnd.choice(self.get_variant_theme_catalog()["all"])
        local_seed = rnd.randint(1, 999999999)
        profile = self.build_roaming_profile(local_seed, f"player_{theme['id']}", rnd.randint(0, 9))
        profile["name"] = f"{rnd.choice(theme['names'])} {rnd.choice(theme['titles'])}"
        profile["mode"] = rnd.choice(list(dict.fromkeys(list(theme["modes"]) + ["electric"])))
        secondary_choices = list(dict.fromkeys(list(theme["secondary_modes"]) + ["electric", "laser", "beam"]))
        profile["secondary_mode"] = rnd.choice([m for m in secondary_choices if m != profile["mode"]] or secondary_choices)
        profile["origin"] = rnd.choice(theme["origins"])
        profile["secondary_origin"] = rnd.choice([o for o in theme["origins"] if o != profile["origin"]] or theme["origins"])
        profile["support_fx"] = rnd.choice(list(dict.fromkeys(list(theme["supports"]) + ["lightning"])))
        profile["mobility_style"] = rnd.choice(theme.get("mobility", ["jetpack"]))
        profile = self.ensure_unique_profile(profile, local_seed + 97)
        self.power_profile = profile
        self.apply_power_profile_to_hero()
        if not initial:
            self.last_power_text = f"{self.power_profile['name']} {profile['family']} {profile['mode']}/{profile['secondary_mode']}"
            self.spawn_power_fx("ring", self.hero_pos + Vec3(0, 0, 1.3), self.power_profile["primary"], 1.1)
            self.play_sfx(f"mode_{profile['mode']}", volume=0.42, rate=0.90 + random.random() * 0.18)
        self.refresh_hud()


    def apply_power_profile_to_hero(self) -> None:
        if not self.hero_visual:
            return
        primary = self.power_profile.get("primary", (0.30, 1.0, 0.44, 1.0))
        secondary = self.power_profile.get("secondary", (0.8, 1.0, 0.9, 1.0))
        self.apply_profile_to_actor(self.hero_visual, self.hero_emissives, self.power_profile)
        self.customize_npc_helmet({"parts": self.hero_parts, "profile": self.power_profile, "visual": self.hero_visual})
        self.set_propulsion_colors(getattr(self, "hero_propulsion", None), primary, secondary)
        self.hero_fill.setColor(Vec4(primary[0] * 0.35 + 0.08, primary[1] * 0.35 + 0.08, primary[2] * 0.35 + 0.08, 1.0))

    def reset_hero(self) -> None:
        self.hero_pos = Vec3(0, -145, 26)
        self.hero_velocity = Vec3(0, 0, 0)
        self.hero_heading = 0.0
        self.hero_pitch = 0.0
        self.hero_roll = 0.0
        self.control_yaw = 0.0
        self.control_pitch = -10.0
        self.cam_yaw = 0.0
        self.cam_pitch = -12.0
        self.cam_distance = float(self.settings_data.get("default_camera_distance", 24.5))
        self.target_cam_distance = float(self.settings_data.get("default_camera_distance", 24.5))
        self.attack_timer = 0.0
        self.attack_cooldown = 0.0
        self.attack_variant = "idle"
        self.player_hp = 100.0
        self.player_max_hp = 100.0
        self.attack_charge = 0.0
        self.attack_charging = False
        self.charge_fx_timer = 0.0
        self.shield_timer = 0.0
        self.shield_cooldown = 0.0
        self.shield_charging = False
        self.shield_hold = 0.0
        self.shield_release_radius = self.shield_radius
        self.combat_active = False
        self.police_alert_team = "neutral"
        self.police_alert_timer = 0.0
        self.launcher_alert_team = "neutral"
        self.launcher_alert_timer = 0.0
        self.player_emote_name = "none"
        self.player_emote_strength = 0.0
        if self.boss is not None and self.boss.get("type") == "sandworm":
            self.release_sandworm_grab(self.boss)
        self.xray_timer = 0.0
        self.xray_cooldown = 0.0
        self.boss_spawn_timer = 0.18 if _preview else self.boss_respawn_delay
        if self.boss is not None:
            try:
                self.boss["root"].removeNode()
            except Exception:
                pass
        self.boss = None
        if self.boss_beam is not None:
            for node in (self.boss_beam.get("core"), self.boss_beam.get("halo")):
                if node is not None and not node.isEmpty():
                    node.removeNode()
        self.boss_beam = None
        self.locked_target = None
        self.close_settings_menu() if self.settings_open else None
        self.hero_root.setPos(self.hero_pos)
        self.hero_root.setHpr(0, 0, 0)
        if hasattr(self, "shield_node"):
            self.shield_node.hide()
            self.shield_node.setColorScale(0.30, 1.0, 0.55, 0.0)
        for item in getattr(self, "shadow_fx", []):
            node = item.get("node")
            if node is not None and not node.isEmpty():
                node.removeNode()
        self.shadow_fx = []

        for target in self.structure_targets:
            node = target.get("node")
            if node is not None and not node.isEmpty():
                target["sink"] = 0.0
                target["hp"] = target["max_hp"]
                node.setZ(float(target.get("base_z", node.getZ())))

        for launcher in getattr(self, "ground_launchers", []):
            launcher["cooldown"] = 0.0

        for npc in self.npcs:
            npc["dead"] = False
            npc["root"].show()
            npc["hp"] = 100.0
            npc["max_hp"] = 100.0
            npc["velocity"] = Vec3(0, 0, 0)
            npc["recover_timer"] = 0.0
            npc["shield_timer"] = 0.0
            npc["shield_cooldown"] = 0.0
            npc["attack_timer"] = 0.0
            npc["attack_cooldown"] = 0.6 + npc["index"] * 0.12
            npc["secondary_cooldown"] = 1.6 + npc["index"] * 0.22
            npc["attack_variant"] = "idle"
            npc["attack_charge"] = 0.0
            if npc["team"] == "ally":
                npc["pos"] = self.get_ally_formation_target(int(npc.get("formation_slot", 0))) + Vec3(0, 0, 10.0)
                npc["state"] = "escort"
                npc["heading"] = self.hero_heading
            else:
                npc["pos"] = Vec3(npc["home_anchor"])
                npc["state"] = "fight"
                npc["heading"] = 180.0
            npc["root"].setPos(npc["pos"])
            npc["root"].setHpr(npc["heading"], 0.0, 0.0)
            npc["shield_node"].hide()

        self.center_mouse()
        self.ensure_outskirts(force=True)
        self.refresh_hud()

    def adjust_zoom(self, delta: float) -> None:
        step = float(self.settings_data.get("zoom_step", 1.4))
        self.target_cam_distance = clamp(self.target_cam_distance + (delta / 1.2) * step, 10.0, 36.0)



    def activate_shield(self) -> None:
        if self.shield_cooldown > 0.0 or self.shield_timer > 0.0 or getattr(self, "shield_charging", False):
            return
        self.play_sfx("shield_orb", volume=0.74, rate=0.96)
        self.shield_charging = True
        self.shield_hold = 0.0
        self.shield_release_radius = self.shield_radius
        self.attack_variant = "shield"
        self.attack_timer = max(self.attack_timer, 0.24)
        self.last_power_text = "Charging shield orb"

    def release_shield(self) -> None:
        if not getattr(self, "shield_charging", False):
            return
        charge_n = clamp(self.shield_hold / 1.6, 0.15, 1.0)
        self.shield_charging = False
        self.shield_timer = 0.60 + charge_n * 0.70
        self.shield_cooldown = 3.4 + charge_n * 2.2
        self.shield_release_radius = self.shield_radius + charge_n * 5.5
        self.attack_variant = "shield"
        self.attack_timer = max(self.attack_timer, 0.24 + charge_n * 0.18)
        self.last_power_text = f"Shield pulse {int(charge_n * 100)}%"
        self.spawn_power_fx("ring", self.hero_pos + Vec3(0, 0, 1.3), self.power_profile.get("secondary", (0.8,1.0,0.9,1.0)), 1.0 + charge_n * 1.1)


    def apply_area_blast(self, owner: str, pos: Vec3, radius: float, damage: float, structure_damage: float, strong: bool = False) -> None:
        r2 = radius * radius
        if self.boss is not None and self.boss.get("alive", False) and owner != "boss":
            if (self.boss["root"].getPos() - pos).lengthSquared() <= (radius + 7.0) ** 2:
                self.hit_boss_by_projectile(pos, True, owner)
        if self.owner_is_enemy(owner, "ally") and (self.hero_pos + Vec3(0, 0, 1.2) - pos).lengthSquared() <= r2:
            self.damage_player(damage, owner)
        for npc in self.npcs:
            if npc.get("dead", False):
                continue
            if not self.owner_is_enemy(owner, str(npc.get("team", "neutral"))):
                continue
            center = npc["pos"] + Vec3(0, 0, 1.2 * npc["profile"]["scale"])
            if (center - pos).lengthSquared() <= (radius + npc["hit_radius"] * 0.45) ** 2:
                self.damage_npc(npc, damage, owner)
        for car in self.traffic_cars:
            if car.get("active", False) and (car["node"].getPos() - pos).lengthSquared() <= (radius + car["radius"]) ** 2:
                self.destroy_traffic_car(car, strong=strong)
        for target in self.structure_targets:
            node = target.get("node")
            if node is None or node.isEmpty():
                continue
            center = node.getPos(self.render) + Vec3(0, 0, float(target["h"]) * 0.46)
            reach = radius + max(float(target["w"]), float(target["d"])) * 0.58
            if (center - pos).lengthSquared() <= reach * reach:
                self.damage_structure(target, structure_damage, center)


    def detonate_special_projectile(self, kind: str, pos: Vec3, color: tuple[float, float, float, float], strong: bool, owner: str) -> None:
        if kind == "shockwave":
            radius = 8.5 + (4.0 if strong else 0.0)
            self.spawn_power_fx("ring", pos, color, 1.5 if not strong else 2.0)
            self.apply_area_blast(owner, pos, radius, 9.0 if strong else 6.0, 4.0 if strong else 2.8, strong)
        elif kind == "atom":
            radius = 18.0 + (7.0 if strong else 0.0)
            self.spawn_power_fx("ring", pos, color, 2.8 if not strong else 3.6)
            self.spawn_power_fx("burst", pos + Vec3(0, 0, 1.2), (1.0, 0.52, 0.22, 0.92), 2.0 if not strong else 2.8)
            self.apply_area_blast(owner, pos, radius, 22.0 if strong else 16.0, 8.2 if strong else 6.0, True)
        elif kind == "flame":
            self.spawn_power_fx("burst", pos, color, 0.42 if not strong else 0.60)
            self.spawn_power_fx("explosion", pos + Vec3(0, 0, 0.6), color, 0.66 if not strong else 0.92)
            self.spawn_power_fx("sparks", pos + Vec3(0, 0, 0.4), (1.0, 0.90, 0.58, 0.92), 0.42)
        elif kind == "electric":
            self.spawn_power_fx("electric", pos, color, 0.72 if not strong else 0.96)
            self.spawn_power_fx("sparks", pos + Vec3(0, 0, 0.3), (min(1.0, color[0] + 0.2), min(1.0, color[1] + 0.2), min(1.0, color[2] + 0.2), 0.92), 0.48)
            self.apply_area_blast(owner, pos, 6.0 + (2.0 if strong else 0.0), 8.0 if strong else 5.5, 2.8 if strong else 1.8, strong)

    def on_attack_press(self) -> None:
        if self.attack_cooldown > 0.0 or self.attack_charging:
            return
        self.play_sfx("charge_up", volume=0.52, rate=1.0)
        self.attack_charging = True
        self.attack_charge = 0.0
        self.charge_fx_timer = 0.0
        self.attack_variant = "charge"
        self.last_power_text = "LMB charging visor lasers"

    def on_attack_release(self) -> None:
        if not self.attack_charging:
            return
        strong = "shift" in self.keys
        charge = clamp(self.attack_charge, 0.08, 1.55)
        self.attack_charging = False
        self.fire_charged_attack(charge, strong)


    def get_attack_origins(
        self,
        parts: dict[str, NodePath],
        actor_pos: Vec3,
        actor_scale: float,
        origin_mode: str,
        forward: Vec3,
        right: Vec3,
        up: Vec3,
    ) -> list[Vec3]:
        if origin_mode == "head":
            eye_l = parts.get("eye_l")
            eye_r = parts.get("eye_r")
            if eye_l is not None and eye_r is not None:
                return [eye_l.getPos(self.render), eye_r.getPos(self.render)]
            base = actor_pos + Vec3(0, 0, 1.72 * actor_scale) + forward * 0.92
            return [base - right * 0.08, base + right * 0.08]

        if origin_mode == "hand":
            hand = parts.get("hand_r") or parts.get("hand_l")
            if hand is not None:
                return [hand.getPos(self.render) + forward * 0.12]
            return [actor_pos + Vec3(0, 0, 1.28 * actor_scale) + right * 0.24 + forward * 0.46]

        if origin_mode == "hands":
            hand_l = parts.get("hand_l")
            hand_r = parts.get("hand_r")
            origins = []
            if hand_l is not None:
                origins.append(hand_l.getPos(self.render) + forward * 0.12)
            if hand_r is not None:
                origins.append(hand_r.getPos(self.render) + forward * 0.12)
            if origins:
                return origins
            base = actor_pos + Vec3(0, 0, 1.26 * actor_scale) + forward * 0.42
            return [base - right * 0.24, base + right * 0.24]

        if origin_mode == "chest":
            base = actor_pos + Vec3(0, 0, 1.46 * actor_scale) + forward * 0.22
            return [base]

        base = actor_pos + Vec3(0, 0, 1.44 * actor_scale) + forward * 0.30
        return [base]

    def make_target_list_for_owner(self, owner: str) -> list[dict]:
        team_name = self.owner_team(owner)
        if team_name == "ally":
            return [npc for npc in self.npcs if (not npc.get("dead", False)) and str(npc.get("team")) in self.hostile_teams]
        if team_name in self.hostile_teams:
            return [npc for npc in self.npcs if (not npc.get("dead", False)) and str(npc.get("team")) == "ally"]
        if team_name == "launcher":
            return [npc for npc in self.npcs if (not npc.get("dead", False)) and str(npc.get("team")) == self.launcher_alert_team]
        return []


    def launch_profile_projectiles(
        self,
        profile: dict,
        actor_pos: Vec3,
        actor_scale: float,
        parts: dict[str, NodePath],
        forward: Vec3,
        right: Vec3,
        up: Vec3,
        strong: bool,
        owner: str,
        owner_heading: float,
        charge_n: float = 1.0,
        target_pos: Vec3 | None = None,
        use_secondary: bool = False,
    ) -> tuple[str, str]:
        mode = str(profile.get("secondary_mode" if use_secondary else "mode", "laser"))
        origin_mode = str(profile.get("secondary_origin" if use_secondary else "origin", "head"))
        color = profile.get("secondary" if (strong or use_secondary) else "primary", (0.30, 1.0, 0.44, 1.0))
        base_count = int(profile.get("count", 1))
        count_bonus = 2 if strong else 0
        if mode in ("laser", "beam"):
            shot_count = max(1, base_count + (1 if charge_n > 0.72 else 0))
        elif mode in ("shockwave", "atom"):
            shot_count = 1
        elif mode == "flame":
            shot_count = max(4, base_count + 2 + (1 if strong else 0))
        elif mode == "electric":
            shot_count = max(2, base_count + 1 + (1 if strong else 0))
        else:
            shot_count = max(1, base_count + count_bonus)

        speed = float(profile.get("speed", 110.0)) * (1.0 + charge_n * 0.55)
        if mode == "missile":
            speed *= 0.64
        elif mode == "fireball":
            speed *= 0.58
        elif mode in ("laser", "beam"):
            speed *= 1.55
        elif mode == "wire":
            speed *= 0.82
        elif mode == "shockwave":
            speed *= 0.44
        elif mode == "atom":
            speed *= 0.34
        elif mode == "flame":
            speed *= 0.50
        elif mode == "electric":
            speed *= 1.08

        spread = float(profile.get("spread", 0.08)) * (0.55 + charge_n * 0.80)
        scale_mul = (0.82 + charge_n * 1.05) * (1.15 if strong else 1.0)
        if mode == "shockwave":
            scale_mul *= 1.45
        elif mode == "atom":
            scale_mul *= 1.75
        elif mode == "flame":
            scale_mul *= 1.16
        elif mode == "electric":
            scale_mul *= 1.08
        life_mul = 0.72 + charge_n * 0.46
        if mode == "atom":
            life_mul *= 1.28
        elif mode == "flame":
            life_mul *= 0.58
        elif mode == "electric":
            life_mul *= 0.88
        fx_kind = str(profile.get("fx_kind", "burst"))
        if use_secondary:
            fx_kind = str(profile.get("secondary_fx", fx_kind))

        origins = self.get_attack_origins(parts, actor_pos, actor_scale, origin_mode, forward, right, up)
        if not origins:
            origins = [actor_pos + Vec3(0, 0, 1.40 * actor_scale)]

        for origin_index, origin in enumerate(origins):
            local_count = shot_count
            if mode == "fan":
                local_count = max(3, shot_count + 1)
            elif mode == "missile":
                local_count = max(1, 1 + (1 if strong else 0) + (1 if charge_n > 0.82 else 0))
            elif mode == "fireball":
                local_count = max(1, 1 + (1 if strong else 0))
            elif mode == "wire":
                local_count = max(2, shot_count + 1)
            elif mode == "flame":
                local_count = max(4, shot_count)
            elif mode == "electric":
                local_count = max(2, shot_count)

            for i in range(local_count):
                offset = i - (local_count - 1) * 0.5
                dir_vec = Vec3(forward)
                if target_pos is not None:
                    target_vec = (target_pos + Vec3(0, 0, 1.1) - origin)
                    if target_vec.lengthSquared() > 1e-6:
                        target_vec.normalize()
                        dir_vec = target_vec

                if mode == "fan":
                    dir_vec += right * (offset * spread * 0.85)
                elif mode == "spiral":
                    dir_vec += right * (offset * spread * 0.28)
                    dir_vec += up * math.sin(offset + origin_index * 0.7) * spread * 0.26
                elif mode == "pulse":
                    dir_vec += up * (0.08 + offset * spread * 0.16)
                elif mode == "shard":
                    dir_vec += right * (offset * spread * 0.42) + up * (abs(offset) * 0.05)
                elif mode == "beam":
                    dir_vec += right * (offset * spread * 0.14)
                elif mode == "missile":
                    dir_vec += right * (offset * spread * 0.20)
                elif mode == "fireball":
                    dir_vec += up * 0.05 + right * (offset * spread * 0.18)
                elif mode == "wire":
                    dir_vec += right * (offset * spread * 0.52)
                    dir_vec += up * math.sin(i * 0.9 + origin_index) * 0.06
                elif mode == "shockwave":
                    dir_vec += up * 0.02 + right * (offset * spread * 0.10)
                elif mode == "atom":
                    dir_vec += up * 0.10
                elif mode == "flame":
                    dir_vec += right * (offset * spread * 0.48)
                    dir_vec += up * (0.08 + abs(offset) * 0.02 + random.uniform(-0.01, 0.06))
                elif mode == "electric":
                    dir_vec += right * (offset * spread * 0.42)
                    dir_vec += up * math.sin(i * 1.6 + origin_index) * 0.10

                if strong:
                    dir_vec += right * ((-1 if origin_index % 2 == 0 else 1) * 0.015)
                if dir_vec.lengthSquared() < 1e-6:
                    dir_vec = Vec3(0, 1, 0)
                dir_vec.normalize()

                self.spawn_projectile(
                    origin + dir_vec * 0.18,
                    dir_vec,
                    speed,
                    strong,
                    kind_override=mode,
                    color_override=color,
                    scale_mul=scale_mul,
                    life_mul=life_mul,
                    owner=owner,
                    owner_heading=owner_heading,
                )

        return mode, origin_mode

    def fire_charged_attack(self, charge: float, strong: bool) -> None:
        profile = self.power_profile or {
            "primary": (0.30, 1.0, 0.44, 1.0),
            "secondary": (0.85, 1.0, 0.9, 1.0),
            "mode": "laser",
            "origin": "head",
            "count": 1,
            "spread": 0.08,
            "speed": 110.0,
            "projectile_scale": 0.32,
            "fx_kind": "burst",
            "name": "Default",
        }

        forward = self.forward_from_angles(self.hero_heading, self.control_pitch)
        right = self.right_from_yaw(self.hero_heading)
        up = Vec3(0, 0, 1)

        charge_n = clamp(charge / 1.4, 0.0, 1.0)
        self.attack_variant = "overload" if strong else "visor"
        self.attack_timer = 0.32 + charge_n * (0.42 if strong else 0.30)
        self.attack_cooldown = 0.12 + charge_n * (0.26 if strong else 0.16)

        mode, origin_mode = self.launch_profile_projectiles(
            profile,
            self.hero_pos,
            1.36,
            self.hero_parts,
            forward,
            right,
            up,
            strong,
            "player",
            self.hero_heading,
            charge_n=charge_n,
            target_pos=self.get_locked_target_pos(),
            use_secondary=False,
        )
        if strong:
            self.activate_actor_support(None, str(profile.get("support_fx", "none")), is_player=True)
        self.mark_power_activity("ally", self.hero_pos + Vec3(0,0,1.3))
        self.play_sfx(f"mode_{mode}", volume=0.64 + charge_n * 0.26, rate=0.92 + charge_n * 0.22)

        label_origin = {"head": "head", "hand": "hand", "hands": "hands", "chest": "chest"}.get(origin_mode, origin_mode)
        self.last_power_text = f"{profile.get('name', 'Power')} {mode} from {label_origin} {int(charge_n * 100)}%"
        if strong or charge_n > 0.72:
            self.spawn_power_fx("ring", self.hero_pos + forward * 1.0 + Vec3(0, 0, 1.4), profile.get("accent", (1.0, 1.0, 1.0, 1.0)), 1.10 + charge_n * 0.70)
        self.refresh_hud()


    def update_attack_charge(self, dt: float) -> None:
        if not self.attack_charging:
            return
        self.attack_charge = clamp(self.attack_charge + dt, 0.0, 1.55)
        self.attack_timer = max(self.attack_timer, 0.12)
        self.attack_variant = "charge"
        self.charge_fx_timer -= dt
        if self.charge_fx_timer <= 0.0:
            charge_n = clamp(self.attack_charge / 1.4, 0.0, 1.0)
            forward = self.forward_from_angles(self.hero_heading, self.control_pitch)
            visor_pos = self.hero_pos + Vec3(0, 0, 1.70) + forward * (0.95 + charge_n * 0.28)
            self.spawn_power_fx("scan", visor_pos, self.power_profile.get("primary", (0.30, 1.0, 0.44, 1.0)), 0.26 + charge_n * 0.52)
            self.charge_fx_timer = max(0.06, 0.14 - charge_n * 0.07)
        self.last_power_text = f"Charging {self.power_profile.get('mode', 'laser')} {int(clamp(self.attack_charge / 1.4, 0.0, 1.0) * 100)}%"


    def update_shield(self, dt: float) -> None:
        if not hasattr(self, "shield_node"):
            return
        if getattr(self, "shield_charging", False):
            self.shield_hold = clamp(self.shield_hold + dt, 0.0, 1.8)
            charge_n = clamp(self.shield_hold / 1.6, 0.0, 1.0)
            self.player_hp = min(self.player_max_hp, self.player_hp + dt * (1.0 + charge_n * 1.4))
            self.shield_node.show()
            primary = self.power_profile.get("secondary", (0.80, 1.0, 0.90, 1.0))
            pulse = 0.28 + 0.18 * math.sin(globalClock.getFrameTime() * 9.0)
            self.shield_node.setScale(self.shield_radius + charge_n * 3.6 + pulse * 0.35)
            self.shield_node.setColorScale(primary[0] * 1.2, primary[1] * 1.2, primary[2] * 1.2, 0.22 + charge_n * 0.26)
            if int(globalClock.getFrameTime() * 7.0) != int((globalClock.getFrameTime() - dt) * 7.0):
                self.spawn_power_fx("ring", self.hero_pos + Vec3(0, 0, 1.3), primary, 0.30 + charge_n * 0.28)
            return

        if self.shield_timer > 0.0:
            self.shield_node.show()
            pulse = 0.22 + 0.14 * math.sin(globalClock.getFrameTime() * 10.0)
            blast_radius = getattr(self, "shield_release_radius", self.shield_radius)
            self.shield_node.setScale(blast_radius * (1.0 + pulse * 0.06))
            primary = self.power_profile.get("secondary", (0.80, 1.0, 0.90, 1.0))
            self.shield_node.setColorScale(primary[0] * 1.2, primary[1] * 1.2, primary[2] * 1.2, 0.18 + pulse * 0.24)
            hero_center = self.hero_pos + Vec3(0, 0, 1.3)
            for car in self.traffic_cars:
                if not car.get("active", False):
                    continue
                if (car["node"].getPos() - hero_center).lengthSquared() <= (blast_radius + car["radius"] * 0.55) ** 2:
                    self.destroy_traffic_car(car, strong=True)
            for npc in self.npcs:
                if npc.get("team") != "enemy" or npc.get("shield_timer", 0.0) > 0.0:
                    continue
                npc_center = npc["root"].getPos() + Vec3(0, 0, 1.3 * npc["profile"]["scale"])
                if (npc_center - hero_center).lengthSquared() <= (blast_radius + npc["hit_radius"]) ** 2:
                    self.damage_npc(npc, 16.0 * dt + blast_radius * 0.10, "player")
            for target in self.structure_targets:
                node = target.get("node")
                if node is None or node.isEmpty():
                    continue
                center = node.getPos(self.render) + Vec3(0, 0, float(target["h"]) * 0.42)
                if (center - hero_center).lengthSquared() <= (blast_radius + max(float(target["w"]), float(target["d"])) * 0.52) ** 2:
                    self.damage_structure(target, 2.6 * dt + blast_radius * 0.04, center)
            if int(globalClock.getFrameTime() * 8.0) != int((globalClock.getFrameTime() - dt) * 8.0):
                self.spawn_power_fx("ring", hero_center, primary, 0.35)
        else:
            self.shield_node.hide()
            self.shield_node.setColorScale(0.30, 1.0, 0.55, 0.0)

    def spawn_shadow_afterimage(self) -> None:
        if self.hero_visual is None:
            return
        ghost = self.hero_visual.copyTo(self.render)
        ghost.setPos(self.hero_root.getPos(self.render))
        ghost.setHpr(self.hero_root.getHpr(self.render))
        ghost.setScale(self.hero_visual.getScale(self.render))
        ghost.setTransparency(TransparencyAttrib.M_alpha)
        ghost.setDepthWrite(False)
        ghost.setBin("transparent", 18)
        ghost.setLightOff(True)
        ghost.setColorScale(0.05, 0.08, 0.06, 0.22)
        self.shadow_fx.append({"node": ghost, "life": 0.0, "max_life": 0.35})

    def update_shadow_fx(self, dt: float) -> None:
        speed = self.hero_velocity.length()
        shift_active = "shift" in self.keys or self.boost_timer > 0.0
        if shift_active and speed > 18.0:
            self.shadow_spawn_timer -= dt
            if self.shadow_spawn_timer <= 0.0:
                self.spawn_shadow_afterimage()
                self.shadow_spawn_timer = 0.05
        else:
            self.shadow_spawn_timer = max(0.0, self.shadow_spawn_timer - dt)

        alive = []
        for item in self.shadow_fx:
            item["life"] += dt
            node = item["node"]
            t = item["life"] / item["max_life"]
            if t >= 1.0 or node.isEmpty():
                if not node.isEmpty():
                    node.removeNode()
                continue
            alpha = (1.0 - t) ** 1.35 * 0.22
            node.setColorScale(0.03, 0.08, 0.04, alpha)
            node.setZ(node.getZ() + dt * 0.7)
            alive.append(item)
        self.shadow_fx = alive


    def spawn_projectile(
        self,
        pos: Vec3,
        direction: Vec3,
        speed: float,
        strong: bool,
        kind_override: str | None = None,
        color_override: tuple[float, float, float, float] | None = None,
        scale_mul: float = 1.0,
        life_mul: float = 1.0,
        owner: str = "player",
        owner_heading: float | None = None,
    ) -> None:
        profile = self.power_profile
        cm = CardMaker("projectile")
        base_size = float(profile.get("projectile_scale", 0.30))
        if kind_override == "laser":
            base_size *= 0.58
        size = base_size * (1.55 if strong else 1.0) * scale_mul
        cm.setFrame(-size, size, -size, size)
        node = self.render.attachNewNode(cm.generate())
        node.setBillboardPointEye()
        node.setTransparency(TransparencyAttrib.M_alpha)
        node.setDepthWrite(False)
        node.setBin("transparent", 52)
        kind = kind_override or profile.get("mode", "bolt")
        tex = self.projectile_textures.get(kind) if hasattr(self, "projectile_textures") else None
        if tex is None:
            tex = self.texture_factory.make_glitch(f"proj_{kind}", 6200)
        node.setTexture(tex)
        color = color_override or profile.get("secondary" if strong else "primary", (0.30, 1.0, 0.44, 1.0))
        node.setColorScale(*color)
        node.setPos(pos)
        if kind == "wire":
            node.setRenderModeWireframe()
            node.setTwoSided(True)
        elif kind == "beam":
            node.setScale(size * 1.0, 1.0, size * 2.2)
        elif kind == "missile":
            node.setScale(size * 0.72)
        elif kind == "fireball":
            node.setScale(size * 1.16)
        elif kind == "shockwave":
            node.setScale(size * 1.35)
        elif kind == "atom":
            node.setScale(size * 1.62)
        elif kind == "flame":
            node.setScale(size * 1.08)
        elif kind == "electric":
            node.setScale(size * 0.90, 1.0, size * 1.55)
        self.projectiles.append({
            "node": node,
            "velocity": direction * speed,
            "life": 0.0,
            "max_life": (1.45 if kind == "atom" else 0.42 if kind == "flame" else 0.82 if kind == "shockwave" else 0.74 if kind == "electric" else 1.2 if kind == "missile" else 1.0 if kind == "fireball" else 0.9 if strong else 0.65) * life_mul,
            "kind": kind,
            "strong": strong,
            "growth": (4.8 if kind == "shockwave" else 1.25 if kind == "atom" else 2.2 if kind == "flame" else 3.6 if kind == "electric" else 2.8 if strong else 1.7) * (1.2 if kind == "laser" else 0.75 if kind == "missile" else 0.92 if kind == "fireball" else 1.35 if kind == "wire" else 1.0),
            "wobble": random.uniform(3.0, 7.0),
            "spin": random.uniform(-160.0, 160.0),
            "owner": owner,
            "owner_heading": self.hero_heading if owner_heading is None else owner_heading,
        })

    def forward_from_angles(self, yaw_deg: float, pitch_deg: float) -> Vec3:
        yaw = math.radians(yaw_deg)
        pitch = math.radians(pitch_deg)
        cp = math.cos(pitch)
        return Vec3(math.sin(yaw) * cp, math.cos(yaw) * cp, math.sin(pitch))

    def right_from_yaw(self, yaw_deg: float) -> Vec3:
        yaw = math.radians(yaw_deg + 90.0)
        return Vec3(math.sin(yaw), math.cos(yaw), 0.0)

    def center_mouse(self) -> None:
        if self.win is None or not hasattr(self.win, "movePointer"):
            return
        x = int(self.win.getXSize() * 0.5)
        y = int(self.win.getYSize() * 0.5)
        self.win.movePointer(0, x, y)


    def _default_escape_action(self) -> None:
        if self.settings_open:
            self.close_settings_menu()
        else:
            self.open_settings_menu()

    def handle_escape(self) -> None:
        if _HOLOVERSE_RUNTIME is not None and _HOLOVERSE_RUNTIME.embedded_mode():
            _HOLOVERSE_RUNTIME.embedded_escape_pressed(self._default_escape_action)
        else:
            self._default_escape_action()

    def handle_escape_release(self) -> None:
        if _HOLOVERSE_RUNTIME is not None:
            _HOLOVERSE_RUNTIME.embedded_escape_released()

    def holoverse_host_tick(self, task):
        if _HOLOVERSE_RUNTIME is not None:
            _HOLOVERSE_RUNTIME.poll_return_to_core()
            _HOLOVERSE_RUNTIME.poll_embedded_escape_hold()
        return Task.cont

    def set_mouse_capture_state(self, captured: bool) -> None:
        self.mouse_captured = captured
        if self.win is None or not hasattr(self.win, "requestProperties"):
            return
        props = WindowProperties()
        props.setCursorHidden(captured)
        self.win.requestProperties(props)
        if captured:
            self.center_mouse()

    def open_settings_menu(self) -> None:
        self.settings_open = True
        self.settings_cursor = 0
        self.set_mouse_capture_state(False)
        self.refresh_hud()

    def close_settings_menu(self) -> None:
        self.settings_open = False
        self.set_mouse_capture_state(True)
        self.refresh_hud()

    def toggle_hud(self) -> None:
        self.hud_visible = not self.hud_visible
        self.settings_data["hud_visible"] = self.hud_visible
        self.save_settings()
        if self.hud_visible and not self.settings_open:
            self.hud.show()
            self.refresh_hud()
        else:
            self.hud.hide()


    def toggle_overlay(self) -> None:
        self.overlay_visible = not self.overlay_visible
        self.settings_data["overlay_visible"] = self.overlay_visible
        self.save_settings()
        if self.overlay_visible:
            self.overlay.show()
        else:
            self.overlay.hide()

    def update_mouse_look(self) -> None:
        if self.settings_open or not self.mouse_captured or self.win is None:
            return
        if hasattr(self.win, "getProperties") and not self.win.getProperties().getForeground():
            return
        if not hasattr(self.win, "getPointer"):
            return
        pointer = self.win.getPointer(0)
        cx = self.win.getXSize() * 0.5
        cy = self.win.getYSize() * 0.5
        dx = pointer.getX() - cx
        dy = pointer.getY() - cy
        self.mouse_turn_delta = float(dx)
        if dx != 0 or dy != 0:
            yaw_sens = float(self.settings_data.get("mouse_sensitivity", 0.10))
            pitch_sens = float(self.settings_data.get("camera_pitch_sensitivity", 0.080))
            yaw_delta = -dx * yaw_sens
            self.hero_heading = (self.hero_heading + yaw_delta) % 360.0
            self.control_yaw = self.hero_heading
            self.cam_yaw = self.hero_heading
            if bool(self.settings_data.get("invert_y", False)):
                self.control_pitch = clamp(self.control_pitch + dy * pitch_sens, -82.0, 58.0)
            else:
                self.control_pitch = clamp(self.control_pitch - dy * pitch_sens, -82.0, 58.0)
        self.look_turn_strength = lerp(self.look_turn_strength, clamp(-dx * 0.18, -16.0, 16.0), 0.28)
        self.center_mouse()

    def use_power(self, key: str) -> None:
        cd = self.burst_cooldowns.get(key, 0.0)
        if cd > 0.0:
            return

        primary = self.power_profile.get("primary", (0.30, 1.0, 0.44, 1.0))
        secondary = self.power_profile.get("secondary", (0.80, 1.0, 0.90, 1.0))
        accent = self.power_profile.get("accent", (1.0, 1.0, 1.0, 1.0))

        forward = self.forward_from_angles(self.hero_heading, self.control_pitch)
        right = self.right_from_yaw(self.hero_heading)
        up = Vec3(0, 0, 1)
        self.last_power_text = f"Shift+{key.upper()}"

        if key == "w":
            self.hero_velocity += forward * 92.0
            self.boost_timer = 0.55
            self.spawn_power_fx("burst", self.hero_pos - forward * 0.6, primary, 0.68)
            self.spawn_power_fx("trail", self.hero_pos - forward * 1.1, secondary, 0.50)
            self.burst_cooldowns[key] = 0.28
        elif key == "s":
            self.hero_velocity *= 0.28
            self.brake_timer = 0.50
            self.spawn_power_fx("ring", self.hero_pos, secondary, 0.72)
            self.spawn_power_fx("smoke", self.hero_pos, (0.55, 0.60, 0.66, 0.56), 0.62)
            self.burst_cooldowns[key] = 0.22
        elif key == "a":
            self.hero_velocity -= right * 64.0
            self.spawn_power_fx("slash", self.hero_pos - right * 0.5, primary, 0.46)
            self.spawn_power_fx("sparks", self.hero_pos - right * 0.5, accent, 0.38)
            self.burst_cooldowns[key] = 0.18
        elif key == "d":
            self.hero_velocity += right * 64.0
            self.spawn_power_fx("slash", self.hero_pos + right * 0.5, primary, 0.46)
            self.spawn_power_fx("sparks", self.hero_pos + right * 0.5, accent, 0.38)
            self.burst_cooldowns[key] = 0.18
        elif key == "q":
            self.hero_velocity -= up * 54.0
            self.spawn_power_fx("ring", self.hero_pos, accent, 0.52)
            self.spawn_power_fx("rock", self.hero_pos + Vec3(0, 0, 0.4), primary, 0.42)
            self.burst_cooldowns[key] = 0.20
        elif key == "e" or key == "space":
            self.hero_velocity += up * 58.0
            self.spawn_power_fx("ring", self.hero_pos, primary, 0.54)
            self.spawn_power_fx("ice", self.hero_pos + Vec3(0, 0, 0.5), accent, 0.44)
            self.burst_cooldowns[key] = 0.20
        elif key == "f":
            self.hero_pos += forward * 42.0
            self.hero_root.setPos(self.hero_pos)
            self.spawn_power_fx("blink", self.hero_pos, secondary, 0.50)
            self.spawn_power_fx("laser_blast", self.hero_pos + forward * 1.2, accent, 0.42)
            self.burst_cooldowns[key] = 0.50
        elif key == "1":
            self.spawn_power_fx("ring", self.hero_pos, primary, 1.0)
            self.hero_velocity += forward * 25.0
            self.burst_cooldowns[key] = 0.35
        elif key == "2":
            for _ in range(3):
                offset = Vec3(random.uniform(-2.0, 2.0), random.uniform(-2.0, 2.0), random.uniform(-0.5, 1.0))
                self.spawn_power_fx("burst", self.hero_pos + offset, secondary, 0.64)
            self.burst_cooldowns[key] = 0.55
        elif key == "3":
            self.spawn_power_fx("scan", self.hero_pos, accent, 1.2)
            self.spawn_power_fx("acid", self.hero_pos + Vec3(0, 0, 0.9), secondary, 0.56)
            self.burst_cooldowns[key] = 0.85

        sfx_map = {
            "w": "move_boost",
            "s": "move_brake",
            "a": "move_dash",
            "d": "move_dash",
            "q": "move_rise",
            "e": "move_rise",
            "space": "move_rise",
            "f": "move_blink",
            "1": "special_one",
            "2": "special_two",
            "3": "special_three",
        }
        sfx_name = sfx_map.get(key)
        if sfx_name:
            self.play_sfx(sfx_name, volume=0.58, rate=0.96 + random.random() * 0.12)
        self.mark_power_activity("ally", self.hero_pos + Vec3(0,0,1.0))
        self.refresh_hud()

    def spawn_power_fx(self, kind: str, pos: Vec3, color: tuple[float, float, float, float], start_scale: float) -> None:
        if random.random() > float(self.settings_data.get("effect_density", 1.0)) and kind not in ("ring", "beam", "shield", "electric"):
            return
        frame_map = {
            "ring": (-0.8, 0.8, -0.8, 0.8),
            "slash": (-0.28, 0.28, -0.9, 0.9),
            "blink": (-1.2, 1.2, -1.2, 1.2),
            "explosion": (-0.9, 0.9, -0.9, 0.9),
            "smoke": (-1.1, 1.1, -1.1, 1.1),
            "trail": (-0.18, 0.18, -1.3, 1.3),
            "sparks": (-0.55, 0.55, -0.55, 0.55),
            "laser_blast": (-0.40, 0.40, -1.35, 1.35),
            "flame_fx": (-0.60, 0.60, -1.10, 1.10),
            "ice": (-0.72, 0.72, -0.72, 0.72),
            "rock": (-0.70, 0.70, -0.70, 0.70),
            "acid": (-0.86, 0.86, -0.64, 0.64),
            "electric": (-0.76, 0.76, -1.10, 1.10),
        }
        cm = CardMaker(f"fx_{kind}")
        cm.setFrame(*frame_map.get(kind, (-0.5, 0.5, -0.5, 0.5)))

        fx = self.render.attachNewNode(cm.generate())
        fx.setBillboardPointEye()
        fx.setTransparency(TransparencyAttrib.M_alpha)
        fx.setDepthWrite(False)
        fx.setBin("transparent", 50)
        tex = self.fx_textures.get(kind) if hasattr(self, "fx_textures") else None
        if tex is None:
            tex = self.texture_factory.make_glitch(f"fx_{kind}", 5100)
        fx.setTexture(tex)
        fx.setColorScale(*color)
        fx.setPos(pos)
        fx.setScale(start_scale)
        life_map = {
            "slash": 0.42, "blink": 0.42, "burst": 0.65, "ring": 0.85, "scan": 1.25,
            "explosion": 0.72, "smoke": 1.40, "trail": 0.95, "sparks": 0.52,
            "laser_blast": 0.46, "flame_fx": 0.78, "ice": 0.90, "rock": 1.05, "acid": 0.96, "electric": 0.62,
        }
        growth_map = {
            "ring": 4.4, "scan": 6.5, "burst": 3.8, "explosion": 6.2, "smoke": 2.6, "trail": 2.8,
            "sparks": 5.8, "laser_blast": 8.2, "flame_fx": 4.8, "ice": 3.4, "rock": 2.2, "acid": 3.6, "electric": 6.2,
        }
        drift = Vec3(0, 0, 0)
        if kind == "smoke":
            drift = Vec3(random.uniform(-0.9, 0.9), random.uniform(-0.9, 0.9), random.uniform(1.2, 3.0))
        elif kind == "trail":
            drift = Vec3(random.uniform(-0.25, 0.25), random.uniform(-0.25, 0.25), random.uniform(0.6, 1.3))
        elif kind == "sparks":
            drift = Vec3(random.uniform(-2.4, 2.4), random.uniform(-2.4, 2.4), random.uniform(0.8, 3.4))
        elif kind == "laser_blast":
            drift = Vec3(0, 0, 1.2)
        elif kind == "flame_fx":
            drift = Vec3(random.uniform(-0.6, 0.6), random.uniform(-0.6, 0.6), random.uniform(1.6, 2.8))
        elif kind == "ice":
            drift = Vec3(random.uniform(-0.3, 0.3), random.uniform(-0.3, 0.3), random.uniform(0.4, 1.0))
        elif kind == "rock":
            drift = Vec3(random.uniform(-0.8, 0.8), random.uniform(-0.8, 0.8), random.uniform(0.3, 1.2))
        elif kind == "acid":
            drift = Vec3(random.uniform(-0.5, 0.5), random.uniform(-0.5, 0.5), random.uniform(0.2, 0.9))
        elif kind == "electric":
            drift = Vec3(random.uniform(-0.6, 0.6), random.uniform(-0.6, 0.6), random.uniform(0.4, 1.8))
        self.power_fx.append({
            "node": fx,
            "life": 0.0,
            "max_life": life_map.get(kind, 1.25),
            "growth": growth_map.get(kind, 3.8),
            "kind": kind,
            "drift": drift,
            "spin": random.uniform(-120.0, 120.0),
            "base_scale": start_scale,
        })

    def update_power_fx(self, dt: float) -> None:
        alive = []
        for item in self.power_fx:
            item["life"] += dt
            node = item["node"]
            t = item["life"] / item["max_life"]
            if t >= 1.0:
                node.removeNode()
                continue
            alpha = (1.0 - t) ** 1.2
            scale = node.getScale().x + item["growth"] * dt
            node.setScale(scale)
            drift = item.get("drift", Vec3(0, 0, 0))
            if drift.lengthSquared() > 0.0:
                node.setPos(node.getPos() + drift * dt)
            spin = item.get("spin", 0.0)
            if abs(spin) > 1e-6:
                node.setR(node.getR() + spin * dt)
            kind = item["kind"]
            if kind in ("burst", "blink"):
                node.setZ(node.getZ() + dt * 4.0)
            elif kind == "smoke":
                node.setColorScale(node.getColorScale().x * 0.98 + 0.02, node.getColorScale().y * 0.98 + 0.02, node.getColorScale().z * 0.98 + 0.02, alpha * 0.72)
            elif kind == "sparks":
                node.setScale(scale * (1.0 + math.sin(item["life"] * 22.0) * 0.08))
            elif kind == "laser_blast":
                node.setScale(scale * 1.08, scale * 0.30, scale * 1.22)
            elif kind == "trail":
                node.setScale(scale * 0.55, max(0.2, scale * 0.22), scale * 1.30)
            elif kind == "flame_fx":
                node.setScale(scale * 0.90, scale * 0.90, scale * (1.2 + 0.25 * math.sin(item["life"] * 18.0)))
            elif kind == "ice":
                node.setScale(scale * (1.0 + 0.10 * math.sin(item["life"] * 9.0)))
            elif kind == "rock":
                node.setP(node.getP() + spin * 0.25 * dt)
            elif kind == "acid":
                node.setScale(scale * (1.0 + 0.12 * math.sin(item["life"] * 14.0)))
                node.setZ(node.getZ() - dt * 0.5)
            elif kind == "electric":
                node.setScale(scale * (0.88 + 0.22 * math.sin(item["life"] * 24.0)), max(0.12, scale * 0.22), scale * (1.18 + 0.32 * math.sin(item["life"] * 18.0)))
                node.setR(node.getR() + spin * 1.4 * dt)
            r, g, b, _ = node.getColorScale()
            node.setColorScale(r, g, b, alpha)
            alive.append(item)
        self.power_fx = alive


    def update_projectiles(self, dt: float) -> None:
        alive = []
        for item in self.projectiles:
            item["life"] += dt
            node = item["node"]
            kind = item["kind"]
            owner = str(item.get("owner", "player"))
            t = item["life"] / item["max_life"]
            color = node.getColorScale()
            if t >= 1.0:
                if kind in ("shockwave", "atom", "flame", "electric"):
                    self.detonate_special_projectile(kind, node.getPos(), color, bool(item["strong"]), owner)
                else:
                    self.spawn_power_fx("burst", node.getPos(), self.power_profile.get("secondary", (0.8, 1.0, 0.9, 1.0)), 0.36)
                node.removeNode()
                continue

            vel = Vec3(item["velocity"])
            wobble = item["wobble"]
            owner_heading = float(item.get("owner_heading", self.hero_heading))

            if kind == "spiral":
                vel += self.right_from_yaw(owner_heading) * math.sin(item["life"] * wobble * 5.0) * 7.0
            elif kind == "pulse":
                vel.z += math.sin(item["life"] * wobble * 4.0) * 2.5
            elif kind == "fan":
                vel *= 0.992
            elif kind == "shard":
                vel += Vec3(math.sin(item["life"] * wobble * 3.0), math.cos(item["life"] * wobble * 3.0), 0.0) * 1.3
            elif kind == "laser":
                vel *= 1.015
            elif kind == "beam":
                vel *= 1.020
                node.setScale(node.getScale().x, node.getScale().y, max(node.getScale().z, node.getScale().x * 2.6))
            elif kind == "wire":
                vel += self.right_from_yaw(owner_heading) * math.sin(item["life"] * wobble * 6.2) * 8.0
                node.setR(node.getR() + item["spin"] * dt * 1.6)
            elif kind == "fireball":
                vel *= 0.992
                vel.z += math.sin(item["life"] * wobble * 2.4) * 1.8
            elif kind == "missile":
                vel *= 1.01
            elif kind == "shockwave":
                vel *= 0.972
            elif kind == "atom":
                vel *= 0.988
                vel.z = max(vel.z - 12.0 * dt, -42.0)
            elif kind == "flame":
                vel *= 0.90
                vel.z += math.sin(item["life"] * wobble * 5.0) * 1.4 + 0.8
            elif kind == "electric":
                vel *= 1.01
                vel += self.right_from_yaw(owner_heading) * math.sin(item["life"] * wobble * 11.0) * 10.0
                vel.z += math.cos(item["life"] * wobble * 8.0) * 1.8

            node.setPos(node.getPos() + vel * dt)

            hit = self.hit_boss_by_projectile(node.getPos(), bool(item["strong"]), owner) or self.hit_actor_by_projectile(node.getPos(), bool(item["strong"]), owner) or self.hit_traffic_by_projectile(node.getPos(), bool(item["strong"])) or self.hit_structure_by_projectile(node.getPos(), bool(item["strong"]), owner)
            if hit:
                if kind in ("shockwave", "atom", "flame", "electric"):
                    self.detonate_special_projectile(kind, node.getPos(), color, bool(item["strong"]), owner)
                elif kind == "missile":
                    self.spawn_power_fx("ring", node.getPos(), color, 0.48)
                node.removeNode()
                continue

            s = node.getScale().x + item["growth"] * dt
            if kind == "beam":
                node.setScale(s, 1.0, max(node.getScale().z, s * 2.6))
            else:
                node.setScale(s)
            node.setColorScale(color[0], color[1], color[2], max(0.0, 1.0 - t))
            if kind not in ("wire",):
                node.setR(node.getR() + item["spin"] * dt)
            item["velocity"] = vel
            alive.append(item)
        self.projectiles = alive

    def update_cooldowns(self, dt: float) -> None:
        self.boost_timer = max(0.0, self.boost_timer - dt)
        self.brake_timer = max(0.0, self.brake_timer - dt)
        self.attack_timer = max(0.0, self.attack_timer - dt)
        self.attack_cooldown = max(0.0, self.attack_cooldown - dt)
        self.shield_timer = max(0.0, self.shield_timer - dt)
        self.shield_cooldown = max(0.0, self.shield_cooldown - dt)
        self.xray_timer = max(0.0, self.xray_timer - dt)
        self.xray_cooldown = max(0.0, self.xray_cooldown - dt)
        self.support_timer = max(0.0, self.support_timer - dt)
        self.support_cooldown = max(0.0, self.support_cooldown - dt)
        for key, value in self.burst_cooldowns.items():
            self.burst_cooldowns[key] = max(0.0, value - dt)


    def resolve_structure_collisions(self, pos: Vec3, radius: float = 1.05, body_height: float = 2.4) -> Vec3:
        resolved = Vec3(pos)
        for target in self.structure_targets:
            node = target.get("node")
            if node is None or node.isEmpty():
                continue
            local = node.getRelativePoint(self.render, resolved)
            w = float(target["w"]) * 0.5 + radius
            d = float(target["d"]) * 0.5 + radius
            h = float(target["h"]) + body_height
            if not (-0.2 <= local.z <= h):
                continue
            if target["shape"] == "box":
                if abs(local.x) < w and abs(local.y) < d:
                    pen_x = w - abs(local.x)
                    pen_y = d - abs(local.y)
                    if pen_x < pen_y:
                        local.x = math.copysign(w, local.x if abs(local.x) > 1e-4 else 1.0)
                    else:
                        local.y = math.copysign(d, local.y if abs(local.y) > 1e-4 else 1.0)
                    resolved = self.render.getRelativePoint(node, local)
            elif target["shape"] == "pyramid":
                frac = 1.0 if local.z <= 0.0 else max(0.0, 1.0 - (local.z / max(0.001, float(target["h"]))))
                allowed_x = w * frac
                allowed_y = d * frac
                if abs(local.x) < allowed_x and abs(local.y) < allowed_y:
                    pen_x = allowed_x - abs(local.x)
                    pen_y = allowed_y - abs(local.y)
                    if pen_x < pen_y:
                        local.x = math.copysign(allowed_x, local.x if abs(local.x) > 1e-4 else 1.0)
                    else:
                        local.y = math.copysign(allowed_y, local.y if abs(local.y) > 1e-4 else 1.0)
                    resolved = self.render.getRelativePoint(node, local)
        return resolved

    def update_movement(self, dt: float) -> None:
        if self.boss is not None and self.boss.get("alive", False) and self.boss.get("grab_active") and (self.boss.get("grab_target") or {}).get("kind") == "player":
            self.hero_velocity *= 0.30
            self.hero_root.setPos(self.hero_pos)
            return
        move_forward = self.forward_from_angles(self.hero_heading, 0.0)
        move_forward.z = 0.0
        if move_forward.lengthSquared() < 1e-8:
            move_forward = Vec3(0, 1, 0)
        else:
            move_forward.normalize()
        right = self.right_from_yaw(self.hero_heading)
        move = Vec3(0, 0, 0)

        if "w" in self.keys:
            move += move_forward
        if "s" in self.keys:
            move -= move_forward
        if "a" in self.keys:
            move -= right
        if "d" in self.keys:
            move += right
        if "q" in self.keys:
            move.z -= 1.0
        if "e" in self.keys or "space" in self.keys:
            move.z += 1.0

        shift = "shift" in self.keys
        if shift:
            self.boost_timer = max(self.boost_timer, 0.10)
        top_speed = 84.0 if shift else 52.0
        if self.boost_timer > 0.0:
            top_speed += 64.0
        accel = 6.2 if shift else 4.6

        target = Vec3(0, 0, 0)
        if move.lengthSquared() > 0.0:
            move.normalize()
            target = move * top_speed

        self.hero_velocity = approach_vec(self.hero_velocity, target, accel, dt)
        drag = 0.95 if shift else 0.91
        if self.brake_timer > 0.0:
            drag = 0.72
        self.hero_velocity *= drag ** (dt * 60.0)

        flat_velocity = Vec3(self.hero_velocity.x, self.hero_velocity.y, 0.0)
        if flat_velocity.lengthSquared() > 1.0 and "w" in self.keys and "s" not in self.keys:
            desired_heading = math.degrees(math.atan2(flat_velocity.x, flat_velocity.y))
            self.hero_heading = desired_heading % 360.0
            self.control_yaw = self.hero_heading
            self.cam_yaw = self.hero_heading

        self.hero_pos += self.hero_velocity * dt
        self.hero_pos = self.clamp_to_render_block(self.hero_pos, margin=8.0)
        if self.hero_pos.z >= self.hero_ceiling_z and self.hero_velocity.z > 0.0:
            self.hero_velocity.z *= 0.18
        self.hero_pos.z = clamp(self.hero_pos.z, 6.0, self.hero_ceiling_z)
        resolved = self.resolve_structure_collisions(self.hero_pos, radius=1.10, body_height=2.6)
        if (resolved - self.hero_pos).lengthSquared() > 1e-6:
            self.hero_pos = resolved
            self.hero_velocity *= 0.55
        self.hero_root.setPos(self.hero_pos)

        speed = self.hero_velocity.length()
        side_speed = self.hero_velocity.dot(right)
        if speed > 1.1:
            pitch_target = clamp(-self.hero_velocity.z * 0.44 - speed * 0.08, -28.0, 14.0)
            roll_target = clamp(-side_speed * 0.42, -28.0, 28.0)
        else:
            pitch_target = 0.0
            roll_target = 0.0
        self.hero_pitch = lerp(self.hero_pitch, pitch_target, dt * 4.0)
        self.hero_roll = lerp(self.hero_roll, roll_target, dt * 4.4)
        self.hero_root.setHpr(self.hero_heading, self.hero_pitch, self.hero_roll)
        for node in getattr(self, "hero_head_nodes", []):
            node.setH(0.0)
        self.update_propulsion_rig(getattr(self, "hero_propulsion", None), speed, self.boost_timer, True)

    def update_hero_pose(self, dt: float) -> None:
        self.apply_actor_pose(
            self.hero_parts,
            self.hero_base_hprs,
            self.hero_velocity,
            self.hero_roll,
            self.attack_charge,
            self.attack_charging,
            self.attack_timer,
            self.attack_variant,
            self.shield_timer,
            dt,
        )


    def update_camera(self, dt: float) -> None:
        self.cam_yaw = self.hero_heading
        target_pitch = clamp(self.control_pitch * 0.82 - 1.0, -64.0, 36.0)
        self.cam_pitch = lerp(self.cam_pitch, target_pitch, dt * 7.0)
        self.cam_distance = lerp(self.cam_distance, self.target_cam_distance, dt * 6.0)

        pivot = self.hero_pos + Vec3(0, 0, 2.90)
        flat_forward = self.forward_from_angles(self.hero_heading, 0.0)
        flat_forward.z = 0.0
        if flat_forward.lengthSquared() < 1e-8:
            flat_forward = Vec3(0, 1, 0)
        else:
            flat_forward.normalize()
        height_offset = 2.90 + max(0.0, -self.cam_pitch) * 0.055
        back_offset = self.cam_distance + max(0.0, -self.cam_pitch) * 0.14
        desired = pivot - flat_forward * back_offset + Vec3(0, 0, height_offset)
        current = self.camera.getPos()
        amount = clamp(dt * 9.0, 0.0, 1.0)
        self.camera.setPos(current + (desired - current) * amount)
        view_forward = self.forward_from_angles(self.hero_heading, self.control_pitch)
        if view_forward.lengthSquared() < 1e-8:
            view_forward = Vec3(0, 1, 0)
        else:
            view_forward.normalize()
        lock_pos = self.get_locked_target_pos()
        if lock_pos is not None:
            look_point = pivot + view_forward * 12.0 + (lock_pos - pivot) * 0.35 + Vec3(0, 0, 0.35)
        else:
            look_point = pivot + view_forward * 30.0 + Vec3(0, 0, 0.75)
        self.camera.lookAt(look_point)

    def crush_structures_with_boss(self, dt: float) -> None:
        if self.boss is None or not self.boss.get("alive", False):
            return
        boss_root = self.boss.get("root")
        if boss_root is None or boss_root.isEmpty():
            return

        contact_points = []
        if str(self.boss.get("type", "eye")) == "sandworm":
            contact_points.extend([Vec3(p) for p in self.boss.get("contact_points", [])])
            if not contact_points:
                contact_points.append(Vec3(self.boss.get("mouth_world", boss_root.getPos(self.render))))
        else:
            contact_points = [boss_root.getPos(self.render) + Vec3(0, 0, -6.8)]
            for tentacle in self.boss.get("tentacles", []):
                if not tentacle:
                    continue
                tip_joint = tentacle[-1].get("joint")
                if tip_joint is not None and not tip_joint.isEmpty():
                    contact_points.append(tip_joint.getPos(self.render) + Vec3(0, 0, -2.4))

        for target in self.structure_targets:
            if str(target.get("zone")) != "city":
                continue
            node = target.get("node")
            if node is None or node.isEmpty():
                continue
            center = node.getPos(self.render) + Vec3(0, 0, float(target["h"]) * 0.5)
            width_reach = 6.5 + max(float(target["w"]), float(target["d"])) * 0.46
            vertical_reach = float(target["h"]) * 0.58 + 10.0
            for contact in contact_points:
                horizontal = Vec3(center.x - contact.x, center.y - contact.y, 0.0).length()
                if horizontal <= width_reach and abs(center.z - contact.z) <= vertical_reach:
                    if str(self.boss.get("type", "eye")) == "sandworm":
                        self.damage_structure(target, 24.0, contact)
                        target["sink"] = max(float(target.get("sink", 0.0)), float(target["h"]) * 1.22)
                    else:
                        self.damage_structure(target, 8.0, contact)
                        target["sink"] = min(float(target["h"]) * 0.96, float(target.get("sink", 0.0)) + dt * 4.2)
                    break


    def animate_glitch(self, time_value: float) -> None:
        for i, ghost in enumerate(self.ghost_nodes):
            ghost.setShaderInput("u_time", time_value)
            offset = math.sin(time_value * 0.8 + i * 0.73) * 0.55
            ghost.setColorScale(1.0, 1.0, 1.0, 0.10 + abs(offset) * 0.12)

        for i, sign in enumerate(self.dynamic_signs):
            pulse = 0.06 + 0.08 * (0.5 + 0.5 * math.sin(time_value * (1.8 + i * 0.03) + i))
            sign.setColorScale(0.7 + pulse, 1.0, 0.6 + pulse * 0.2, pulse)
            sign.setR(math.sin(time_value * 9.0 + i * 3.7) * 1.4)

    def capture_preview(self, task: Task) -> Task:
        shot = ROOT / "main_preview.png"
        if self.boss is not None and self.boss.get("alive", False) and str(self.boss.get("type", "eye")) == "sandworm":
            root = self.boss["root"]
            head_pos = root.getPos(self.render)
            anchor = Vec3(self.boss.get("home", Vec3(0, 0, 0))) + Vec3(0, 0, 6.0)
            axis = Vec3(head_pos.x - anchor.x, head_pos.y - anchor.y, 0.0)
            if axis.lengthSquared() < 1e-6:
                axis = Vec3(1, 0, 0)
            axis.normalize()
            side = Vec3(-axis.y, axis.x, 0.0)
            mid = (head_pos + anchor) * 0.5 + Vec3(0, 0, 6.0)
            cam_pos = mid - side * 44.0 + Vec3(0, 0, 28.0)
            self.camera.setPos(cam_pos)
            self.camera.lookAt(mid + Vec3(0, 0, 1.0))
            try:
                self.camLens.setFov(46.0)
            except Exception:
                pass
            try:
                self.render.clearFog()
            except Exception:
                pass
            if hasattr(self, "overlay"):
                self.overlay.hide()
            if hasattr(self, "storm_overlay"):
                self.storm_overlay.setColorScale(0.0, 0.0, 0.0, 0.0)
            self.hero_root.setPos(anchor - side * 10.0 + Vec3(0, 0, -4.0))
        self.graphicsEngine.renderFrame()
        self.graphicsEngine.renderFrame()
        self.graphicsEngine.renderFrame()
        self.win.saveScreenshot(str(shot))
        print(f"saved {shot}")
        self.userExit()
        return Task.done


    def update(self, task: Task) -> Task:
        dt = min(0.05, globalClock.getDt())
        t = globalClock.getFrameTime()

        if self.settings_open:
            self.settings_update_accum += dt
            if self.settings_update_accum >= 0.15:
                self.refresh_settings_menu()
                self.settings_update_accum = 0.0
            return Task.cont

        self.update_mouse_look()
        self.update_cooldowns(dt)
        self.update_attack_charge(dt)
        self.update_movement(dt)
        self.update_target_lock(dt)
        self.update_shield(dt)
        self.update_hero_pose(dt)
        self.update_support_effects(dt)
        self.update_structure_targets(dt)
        self.update_npcs(dt)
        self.update_police_drones(dt)
        self.update_ground_launchers(dt)
        self.update_xray_visuals(dt)
        self.update_camera(dt)
        self.update_environment(dt)
        self.update_portal_and_boss(dt)
        self.update_projectiles(dt)
        self.update_traffic(dt)
        self.update_power_fx(dt)
        self.update_shadow_fx(dt)
        self.animate_glitch(t)

        self.stream_timer -= dt
        if self.stream_timer <= 0.0:
            self.ensure_outskirts(force=False)
            self.stream_timer = 0.95

        if self.hud_visible and int(t * 4.0) != int((t - dt) * 4.0):
            self.refresh_hud()
        return Task.cont


if __name__ == "__main__":
    CityHeroApp().run()
