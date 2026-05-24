from __future__ import annotations

import math
import traceback
from datetime import datetime
from pathlib import Path
from random import Random
from typing import Dict, List, Optional, Tuple

from direct.task import Task
from panda3d.core import (
    CardMaker,
    DirectionalLight,
    Geom,
    GeomNode,
    GeomTriangles,
    GeomVertexData,
    GeomVertexFormat,
    GeomVertexWriter,
    PNMImage,
    Texture,
    TransparencyAttrib,
    Vec3,
    Vec4,
)


SOLID = 0
DECK = 1
WATER = 2

CELL = 2.55
MODULE_CELLS = 12
MODULE_SIZE = CELL * MODULE_CELLS
WALL_H = 4.4
DECK_Z = 0.0

TASK_SKY = "level4_moon_sky_task"
TASK_DUST = "level4_moon_dust_task"
LOG_PREFIX = "level4_moon"
THIS_FILE = str(Path(__file__).resolve())
TERMINATOR_Y = MODULE_SIZE * 0.5


def _clamp(v: float, lo: float, hi: float) -> float:
    return lo if v < lo else hi if v > hi else v


def _smoothstep(a: float, b: float, x: float) -> float:
    if a == b:
        return 0.0
    t = _clamp((x - a) / (b - a), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def _hash_u32(*vals: int) -> int:
    h = 2166136261
    for v in vals:
        h = (h ^ (int(v) & 0xFFFFFFFF)) * 16777619
        h &= 0xFFFFFFFF
    return h


def _logs_dir(game) -> Path:
    base_dir = Path(getattr(game, "base_dir", Path(__file__).resolve().parent))
    logs = base_dir / "crash_logs"
    logs.mkdir(parents=True, exist_ok=True)
    return logs


def _write_log(game, stage: str, exc: BaseException, extra: Optional[Dict[str, object]] = None) -> None:
    try:
        logs = _logs_dir(game)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        path = logs / f"{LOG_PREFIX}_{stage}_{stamp}.txt"
        with open(path, "w", encoding="utf-8") as f:
            f.write("Level 4 Moon Terminator Crash Log\n")
            f.write("=" * 72 + "\n")
            f.write(f"Time: {datetime.now().isoformat()}\n")
            f.write(f"Stage: {stage}\n")
            f.write(f"File: {THIS_FILE}\n")
            if extra:
                f.write("\nExtra:\n")
                for key in sorted(extra):
                    f.write(f"  {key}: {extra[key]}\n")
            f.write("\nTraceback:\n")
            f.write("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))
    except Exception:
        pass


def _is_active_level(game) -> bool:
    try:
        module = game._external_level_module()
    except Exception:
        module = None
    if module is None:
        return False
    try:
        return str(Path(getattr(module, "__file__", "")).resolve()) == THIS_FILE
    except Exception:
        return False


def _moon_side_factor(world_y: float) -> float:
    return _smoothstep(TERMINATOR_Y - MODULE_SIZE * 0.85, TERMINATOR_Y + MODULE_SIZE * 0.95, world_y)


def _module_center_world(mx: int, my: int) -> Vec3:
    return Vec3(mx * MODULE_SIZE + MODULE_SIZE * 0.5, my * MODULE_SIZE + MODULE_SIZE * 0.5, 0.0)


def _overlay_aspect_width(game) -> float:
    try:
        if hasattr(game, "getAspectRatio"):
            aspect = float(game.getAspectRatio())
            if aspect > 0.01:
                return aspect
    except Exception:
        pass
    try:
        win = getattr(game, "win", None)
        if win is not None:
            x = float(win.getXSize())
            y = float(win.getYSize())
            if x > 0.0 and y > 0.0:
                return x / y
    except Exception:
        pass
    return 16.0 / 9.0


def _ensure_runtime_assets(game) -> Dict[str, Texture]:
    tex = getattr(game, "_level4_moon_tex", None)
    if isinstance(tex, dict):
        return tex

    def finish(texture: Texture, clamp_mode: bool = False) -> Texture:
        if hasattr(texture, "setMagfilter"):
            texture.setMagfilter(Texture.FTLinear)
        if hasattr(texture, "setMinfilter"):
            texture.setMinfilter(Texture.FTLinearMipmapLinear)
        if clamp_mode:
            if hasattr(texture, "setWrapU"):
                texture.setWrapU(Texture.WMClamp)
            if hasattr(texture, "setWrapV"):
                texture.setWrapV(Texture.WMClamp)
        return texture

    def make_moon_surface() -> Texture:
        img = PNMImage(512, 512, 4)
        for y in range(512):
            fy = y / 511.0
            for x in range(512):
                fx = x / 511.0
                dust = (math.sin(fx * 19.0 + math.sin(fy * 7.0) * 2.0) * 0.5 + 0.5)
                dune = math.sin((fx - fy) * 21.0 + math.cos(fx * 9.0) * 1.4) * 0.035
                swirl = math.cos((fx + fy) * 14.0 + math.sin(fy * 11.0) * 1.6) * 0.028
                pock = abs(math.sin(fx * 57.0 - fy * 43.0)) * 0.022
                grit = (((x * 17 + y * 29) % 37) / 37.0 - 0.5) * 0.07
                base = 0.56 + (dust - 0.5) * 0.09 + dune + swirl - pock + grit
                base *= 0.97 + math.sin((fx * 3.0 + fy * 5.0) * math.pi) * 0.02
                warm = _clamp(base, 0.0, 1.0)
                img.setXelA(x, y, warm * 1.03, warm * 1.01, warm * 0.95, 1.0)
        tex2 = Texture("level4_moon_surface")
        tex2.load(img)
        return finish(tex2)

    def make_rock() -> Texture:
        img = PNMImage(256, 256, 4)
        for y in range(256):
            fy = y / 255.0
            for x in range(256):
                fx = x / 255.0
                ridges = math.sin(fx * 18.0 + fy * 10.0) * 0.09 + math.cos(fx * 11.0 - fy * 17.0) * 0.06
                clay = math.sin((fx + fy) * 9.0 + math.cos(fx * 15.0) * 1.8) * 0.05
                pores = (((x * 7 + y * 17) % 23) / 23.0 - 0.5) * 0.12
                c = _clamp(0.43 + ridges + clay + pores, 0.0, 1.0)
                img.setXelA(x, y, c * 1.02, c, c * 0.93, 1.0)
        tex2 = Texture("level4_rock")
        tex2.load(img)
        return finish(tex2)

    def make_crater() -> Texture:
        img = PNMImage(512, 512, 4)
        for y in range(512):
            ny = y / 511.0 * 2.0 - 1.0
            for x in range(512):
                nx = x / 511.0 * 2.0 - 1.0
                r = math.sqrt(nx * nx + ny * ny)
                ring = math.exp(-((r - 0.74) / 0.11) ** 2)
                bowl = _clamp(1.0 - (r / 0.86), 0.0, 1.0)
                shadow = _clamp((-(ny * 0.75 + nx * 0.35) + 1.0) * 0.5, 0.0, 1.0)
                alpha = _clamp(ring * 0.95 + bowl * 0.45, 0.0, 1.0)
                c = _clamp(0.22 + ring * 0.54 - bowl * 0.18 + shadow * 0.10, 0.0, 1.0)
                img.setXelA(x, y, c, c, c, alpha * 0.82)
        tex2 = Texture("level4_crater")
        tex2.load(img)
        return finish(tex2, clamp_mode=True)

    def make_stars() -> Texture:
        img = PNMImage(1024, 512, 4)
        rnd = Random(40217)
        for y in range(512):
            for x in range(1024):
                img.setXelA(x, y, 0.0, 0.0, 0.0, 0.0)
        for _ in range(1200):
            x = rnd.randrange(1024)
            y = rnd.randrange(512)
            bright = rnd.random()
            radius = 0 if bright < 0.78 else 1
            for oy in range(-radius, radius + 1):
                for ox in range(-radius, radius + 1):
                    px = x + ox
                    py = y + oy
                    if 0 <= px < 1024 and 0 <= py < 512:
                        falloff = 1.0 if radius == 0 else _clamp(1.0 - math.sqrt(ox * ox + oy * oy) / (radius + 0.001), 0.0, 1.0)
                        a = 0.45 + bright * 0.55 * falloff
                        c = 0.82 + bright * 0.18
                        img.setXelA(px, py, c, c, c, max(img.getAlpha(px, py), a))
        tex2 = Texture("level4_stars")
        tex2.load(img)
        return finish(tex2, clamp_mode=True)

    def make_sun_glow() -> Texture:
        img = PNMImage(512, 512, 4)
        for y in range(512):
            ny = y / 511.0 * 2.0 - 1.0
            for x in range(512):
                nx = x / 511.0 * 2.0 - 1.0
                r = math.sqrt(nx * nx + ny * ny)
                core = math.exp(-(r / 0.22) ** 2)
                halo = math.exp(-(r / 0.80) ** 2)
                streak = math.exp(-(ny / 0.10) ** 2) * 0.14 + math.exp(-(nx / 0.10) ** 2) * 0.14
                alpha = _clamp(core * 1.2 + halo * 0.75 + streak, 0.0, 1.0)
                img.setXelA(x, y, 1.0, 0.96, 0.78, alpha)
        tex2 = Texture("level4_sun_glow")
        tex2.load(img)
        return finish(tex2, clamp_mode=True)

    def make_earth() -> Texture:
        img = PNMImage(512, 512, 4)
        light_dir = Vec3(0.78, -0.28, 0.56)
        try:
            light_dir.normalize()
        except Exception:
            pass
        for y in range(512):
            ny = y / 511.0 * 2.0 - 1.0
            for x in range(512):
                nx = x / 511.0 * 2.0 - 1.0
                rr = nx * nx + ny * ny
                if rr > 1.0:
                    img.setXelA(x, y, 0.0, 0.0, 0.0, 0.0)
                    continue
                z = math.sqrt(max(0.0, 1.0 - rr))
                normal = Vec3(nx, -ny, z)
                diffuse = _clamp(normal.dot(light_dir), 0.0, 1.0)
                limb = _clamp(z, 0.0, 1.0)
                n = math.sin(nx * 11.0 + ny * 7.0 + z * 3.0) * 0.5 + math.cos(nx * 17.0 - ny * 13.0) * 0.35
                land_mix = _smoothstep(0.18, 0.65, n)
                cloud_seed = math.sin(nx * 22.0 + ny * 18.0) * 0.4 + math.cos(nx * 13.0 - ny * 29.0) * 0.4
                cloud = _smoothstep(0.35, 0.72, cloud_seed) * 0.85
                ocean = Vec3(0.18, 0.34, 0.68)
                ice = Vec3(0.86, 0.92, 1.0)
                land = Vec3(0.20, 0.46, 0.28)
                base = Vec3(
                    ocean.x * (1.0 - land_mix) + land.x * land_mix,
                    ocean.y * (1.0 - land_mix) + land.y * land_mix,
                    ocean.z * (1.0 - land_mix) + land.z * land_mix,
                )
                polar = _smoothstep(0.62, 0.92, abs(ny))
                base = Vec3(
                    base.x * (1.0 - polar) + ice.x * polar,
                    base.y * (1.0 - polar) + ice.y * polar,
                    base.z * (1.0 - polar) + ice.z * polar,
                )
                shade = 0.10 + diffuse * 0.90
                base = Vec3(base.x * shade, base.y * shade, base.z * shade)
                base = Vec3(
                    base.x * (1.0 - cloud * 0.75) + 0.96 * cloud,
                    base.y * (1.0 - cloud * 0.75) + 0.98 * cloud,
                    base.z * (1.0 - cloud * 0.75) + 1.00 * cloud,
                )
                rim = _smoothstep(0.20, 0.98, limb)
                alpha = _clamp(rim, 0.0, 1.0)
                img.setXelA(x, y, _clamp(base.x, 0.0, 1.0), _clamp(base.y, 0.0, 1.0), _clamp(base.z, 0.0, 1.0), alpha)
        tex2 = Texture("level4_earth")
        tex2.load(img)
        return finish(tex2, clamp_mode=True)

    def make_vignette() -> Texture:
        img = PNMImage(768, 512, 4)
        for y in range(512):
            ny = y / 511.0 * 2.0 - 1.0
            for x in range(768):
                nx = x / 767.0 * 2.0 - 1.0
                edge = max(abs(nx), abs(ny))
                radial = math.sqrt(nx * nx + ny * ny)
                grain = ((((x * 19 + y * 13) % 31) / 31.0) - 0.5) * 0.035
                alpha = _smoothstep(0.58, 1.06, edge) * 0.82 + _smoothstep(0.82, 1.34, radial) * 0.18
                alpha += max(0.0, grain) * 0.18
                img.setXelA(x, y, 0.0, 0.0, 0.0, _clamp(alpha, 0.0, 1.0))
        tex2 = Texture("level4_vignette")
        tex2.load(img)
        return finish(tex2, clamp_mode=True)

    tex = {
        "surface": make_moon_surface(),
        "rock": make_rock(),
        "crater": make_crater(),
        "stars": make_stars(),
        "sun_glow": make_sun_glow(),
        "earth": make_earth(),
        "vignette": make_vignette(),
    }
    game._level4_moon_tex = tex
    return tex


def _cleanup_runtime(game) -> None:
    for task_name in (TASK_SKY, TASK_DUST):
        try:
            game.taskMgr.remove(task_name)
        except Exception:
            pass

    for attr in ("_level4_sky_root", "_level4_screen_overlay"):
        node = getattr(game, attr, None)
        if node is not None:
            try:
                if not node.isEmpty():
                    node.removeNode()
            except Exception:
                pass
            try:
                delattr(game, attr)
            except Exception:
                pass

    if hasattr(game, "_level4_original_shadow_enabled") and not _is_active_level(game):
        try:
            game._shadow_enabled_for_level = game._level4_original_shadow_enabled
        except Exception:
            pass


def _setup_screen_overlay(game) -> None:
    try:
        if not hasattr(game, "aspect2d"):
            return
        overlay = getattr(game, "_level4_screen_overlay", None)
        if overlay is not None:
            try:
                if not overlay.isEmpty():
                    overlay.removeNode()
            except Exception:
                pass

        tex = _ensure_runtime_assets(game)
        aspect = _overlay_aspect_width(game)
        root = game.aspect2d.attachNewNode("level4_screen_overlay")
        root.setBin("fixed", 60)
        root.setDepthWrite(False)
        root.setDepthTest(False)
        cm = CardMaker("level4_vignette_card")
        cm.setFrame(-aspect, aspect, -1.0, 1.0)
        card = root.attachNewNode(cm.generate())
        card.setTexture(tex["vignette"])
        card.setTransparency(TransparencyAttrib.MAlpha)
        card.setDepthWrite(False)
        card.setDepthTest(False)
        card.setBin("fixed", 60)
        card.setShaderOff()
        card.setColorScale(1.0, 1.0, 1.0, 0.46)
        game._level4_screen_overlay = root
    except Exception as exc:
        _write_log(game, "setup_screen_overlay", exc)

def _setup_sky(game) -> None:
    tex = _ensure_runtime_assets(game)
    _cleanup_runtime(game)
    _setup_screen_overlay(game)

    sky_root = game.render.attachNewNode("level4_sky_root")
    sky_root.setLightOff()
    sky_root.setShaderOff()

    def make_card(name: str, w: float, h: float, tex_key: str, alpha: float, sort: int):
        cm = CardMaker(name)
        cm.setFrame(-w * 0.5, w * 0.5, -h * 0.5, h * 0.5)
        np = sky_root.attachNewNode(cm.generate())
        np.setTexture(tex[tex_key])
        np.setTransparency(TransparencyAttrib.MAlpha)
        np.setDepthWrite(False)
        np.setTwoSided(True)
        np.setBin("background", sort)
        np.setBillboardPointEye()
        np.setColorScale(1.0, 1.0, 1.0, alpha)
        return np

    stars = make_card("level4_stars", 420.0, 230.0, "stars", 0.95, 0)
    earth = make_card("level4_earth", 38.0, 38.0, "earth", 1.0, 1)
    earth_glow = make_card("level4_earth_glow", 54.0, 54.0, "sun_glow", 0.14, 0)
    sun = make_card("level4_sun", 16.0, 16.0, "sun_glow", 0.95, 2)
    sun_halo = make_card("level4_sun_halo", 92.0, 92.0, "sun_glow", 0.30, 1)

    game._level4_sky_root = sky_root

    def sky_task(task):
        try:
            if not _is_active_level(game):
                _cleanup_runtime(game)
                return Task.done

            cam_pos = game.camera.getPos(game.render)
            sky_root.setPos(cam_pos.x, cam_pos.y, 0.0)

            stars.setPos(0.0, -260.0, 92.0)
            earth.setPos(-26.0, -238.0, 104.0)
            earth_glow.setPos(-26.0, -238.0, 104.0)
            sun.setPos(26.0, 240.0, 112.0)
            sun_halo.setPos(26.0, 240.0, 112.0)

            t = float(getattr(game, "ambience_t", 0.0))
            stars.setColorScale(1.0, 1.0, 1.0, 0.90 + math.sin(t * 0.17) * 0.03)
            earth_glow.setColorScale(0.40, 0.56, 0.86, 0.07 + math.sin(t * 0.41) * 0.02)
            sun_halo.setColorScale(1.0, 0.93, 0.72, 0.24 + math.sin(t * 0.33) * 0.04)
            return Task.cont
        except Exception as exc:
            _write_log(game, "sky_task", exc)
            _cleanup_runtime(game)
            return Task.done

    game.taskMgr.add(sky_task, TASK_SKY)


def _ensure_shadow_enabled(game) -> None:
    original = getattr(game, "_level4_original_shadow_enabled", None)
    if original is None:
        original = getattr(game, "_shadow_enabled_for_level", None)
        game._level4_original_shadow_enabled = original
    if original is None:
        return

    def _shadow_enabled(level_index=None, _orig=original):
        if _is_active_level(game):
            return True
        if level_index is None:
            level_index = getattr(game, "current_level", 0)
        return _orig(level_index)

    game._shadow_enabled_for_level = _shadow_enabled


def get_level_settings(game) -> Dict[str, object]:
    return {
        "display_name": "Level 4 — Moon Terminator",
        "style_name": "Moon Terminator",
        "move_speed_mult": 1.00,
        "static_water_default": True,
        "fog_start": 22.0,
        "fog_end": 86.0,
        "dark_fog_start": 10.0,
        "dark_fog_end": 52.0,
        "bg_color": Vec4(0.01, 0.01, 0.015, 1.0),
        "fog_color": Vec4(0.045, 0.045, 0.050, 1.0),
        "ambient_light": Vec4(0.030, 0.030, 0.034, 1.0),
        "sun_light": Vec4(0.020, 0.020, 0.024, 1.0),
        "fill_light": Vec4(0.014, 0.014, 0.017, 1.0),
        "lift_light": Vec4(0.018, 0.018, 0.020, 1.0),
        "dark_bg_color": Vec4(0.004, 0.004, 0.006, 1.0),
        "dark_fog_color": Vec4(0.018, 0.018, 0.022, 1.0),
        "dark_ambient_light": Vec4(0.012, 0.012, 0.014, 1.0),
        "dark_sun_light": Vec4(0.008, 0.008, 0.010, 1.0),
        "dark_fill_light": Vec4(0.006, 0.006, 0.007, 1.0),
        "dark_lift_light": Vec4(0.007, 0.007, 0.008, 1.0),
        "weapon_color_scale": Vec4(0.82, 0.84, 0.88, 1.0),
        "weapon_indicator_tint": Vec4(0.96, 0.98, 1.0, 1.0),
        "weapon_pulse_strength": 0.018,
    }


def on_level_load(game) -> None:
    try:
        _ensure_runtime_assets(game)
        _ensure_shadow_enabled(game)
        _setup_sky(game)
        game.return_to_halls_unlocked = False
        game.yaw = 0.0
        game.pitch = -0.03
        game.player_pos = Vec3(MODULE_SIZE * 0.5, TERMINATOR_Y, 0.0)
        if hasattr(game, "_toast"):
            game._toast("Moon Terminator")
    except Exception as exc:
        _write_log(game, "on_level_load", exc)
        raise


def build_module_data(game, mx: int, my: int):
    try:
        rnd = Random(_hash_u32(mx, my, 0x4D4F4F4E))
        grid: List[List[int]] = [[DECK for _ in range(MODULE_CELLS)] for __ in range(MODULE_CELLS)]

        clear_x = range(MODULE_CELLS // 2 - 2, MODULE_CELLS // 2 + 2)
        clear_y = range(MODULE_CELLS // 2 - 2, MODULE_CELLS // 2 + 2)

        obstacle_count = 2 + (1 if rnd.random() < 0.45 else 0) + (1 if rnd.random() < 0.25 else 0)
        for _ in range(obstacle_count):
            cx = rnd.randrange(1, MODULE_CELLS - 1)
            cy = rnd.randrange(1, MODULE_CELLS - 1)
            if cx in clear_x and cy in clear_y:
                continue
            if abs(cy - MODULE_CELLS // 2) <= 1:
                continue
            rad = 0 if rnd.random() < 0.55 else 1
            for oy in range(-rad, rad + 1):
                for ox in range(-rad, rad + 1):
                    x = cx + ox
                    y = cy + oy
                    if 0 < x < MODULE_CELLS - 1 and 0 < y < MODULE_CELLS - 1:
                        if x in clear_x and y in clear_y:
                            continue
                        if abs(y - MODULE_CELLS // 2) <= 1:
                            continue
                        grid[y][x] = SOLID

        style_id = (_hash_u32(mx, my, 0x51A7) >> 1) % 4
        return {"grid": grid, "style_id": int(style_id)}
    except Exception as exc:
        _write_log(game, "build_module_data", exc, {"mx": mx, "my": my})
        raise


def _terrain_anomalies(mx: int, my: int) -> List[Tuple[float, float, float, float, float, float]]:
    rnd = Random(_hash_u32(mx, my, 0x54455252))
    anomalies: List[Tuple[float, float, float, float, float, float]] = []
    count = 4 + rnd.randrange(4)
    for _ in range(count):
        x = rnd.uniform(CELL * 2.0, MODULE_SIZE - CELL * 2.0)
        y = rnd.uniform(CELL * 2.0, MODULE_SIZE - CELL * 2.0)
        sx = rnd.uniform(CELL * 1.5, CELL * 3.9)
        sy = rnd.uniform(CELL * 1.1, CELL * 3.5)
        amp = rnd.uniform(-0.18, 0.34)
        ang = rnd.uniform(0.0, math.tau)
        anomalies.append((x, y, sx, sy, amp, ang))
    return anomalies


def _terrain_height(mx: int, my: int, fx: float, fy: float) -> float:
    wx = mx * MODULE_SIZE + fx
    wy = my * MODULE_SIZE + fy
    base = (
        math.sin(wx * 0.12 + math.sin(wy * 0.04) * 1.6) * 0.10
        + math.cos(wy * 0.10 - wx * 0.03) * 0.08
        + math.sin((wx + wy) * 0.07) * 0.06
    )
    rib = abs(math.sin(wx * 0.21 - wy * 0.17 + math.sin(wx * 0.03))) * 0.07 - 0.035
    h = base + rib
    for cx, cy, sx, sy, amp, ang in _terrain_anomalies(mx, my):
        dx = fx - cx
        dy = fy - cy
        ca = math.cos(ang)
        sa = math.sin(ang)
        rx = dx * ca + dy * sa
        ry = -dx * sa + dy * ca
        rr = (rx / max(sx, 0.001)) ** 2 + (ry / max(sy, 0.001)) ** 2
        mound = math.exp(-rr * 1.65) * amp
        rim = math.exp(-((math.sqrt(max(rr, 0.0)) - 0.92) / 0.24) ** 2) * max(0.0, amp) * 0.22
        slump = math.exp(-rr * 2.4) * min(0.0, amp) * 0.35
        h += mound + rim + slump
    flatten = 1.0 - _smoothstep(0.0, CELL * 1.6, math.sqrt((fx - MODULE_SIZE * 0.5) ** 2 + (fy - MODULE_SIZE * 0.5) ** 2))
    h *= (1.0 - flatten * 0.55)
    return _clamp(h, -0.28, 0.48)


def _add_terrain_shell(game, parent, mx: int, my: int, phase: int, light_factor: float) -> None:
    tex = _ensure_runtime_assets(game)
    res = 18
    fmt = GeomVertexFormat.getV3n3t2()
    vdata = GeomVertexData(f"level4_terrain_{mx}_{my}", fmt, Geom.UHStatic)
    vdata.setNumRows((res + 1) * (res + 1))
    vertex = GeomVertexWriter(vdata, "vertex")
    normal = GeomVertexWriter(vdata, "normal")
    texcoord = GeomVertexWriter(vdata, "texcoord")
    eps = MODULE_SIZE / res * 0.5

    for gy in range(res + 1):
        fy = MODULE_SIZE * gy / res
        for gx in range(res + 1):
            fx = MODULE_SIZE * gx / res
            z = _terrain_height(mx, my, fx, fy)
            hx0 = _terrain_height(mx, my, max(0.0, fx - eps), fy)
            hx1 = _terrain_height(mx, my, min(MODULE_SIZE, fx + eps), fy)
            hy0 = _terrain_height(mx, my, fx, max(0.0, fy - eps))
            hy1 = _terrain_height(mx, my, fx, min(MODULE_SIZE, fy + eps))
            n = Vec3(-(hx1 - hx0), -(hy1 - hy0), eps * 2.0)
            try:
                n.normalize()
            except Exception:
                n = Vec3(0.0, 0.0, 1.0)
            vertex.addData3f(fx, fy, z)
            normal.addData3f(n)
            texcoord.addData2f(fx / MODULE_SIZE * 3.0, fy / MODULE_SIZE * 3.0)

    tris = GeomTriangles(Geom.UHStatic)
    stride = res + 1
    for gy in range(res):
        for gx in range(res):
            i0 = gy * stride + gx
            i1 = i0 + 1
            i2 = i0 + stride
            i3 = i2 + 1
            tris.addVertices(i0, i2, i1)
            tris.addVertices(i1, i2, i3)

    geom = Geom(vdata)
    geom.addPrimitive(tris)
    node = GeomNode(f"level4_terrain_shell_{mx}_{my}")
    node.addGeom(geom)
    np = parent.attachNewNode(node)
    np.setTwoSided(True)
    game._apply_texture(np, tex["surface"], 1.0, 1.0)
    tint = 0.86 + light_factor * 0.16 - phase * 0.015
    np.setColorScale(tint * 1.02, tint, tint * 0.94, 1.0)


def _make_ground_plane(game, parent, phase: int) -> None:
    tex = _ensure_runtime_assets(game)
    ground = game._add_plane(
        parent,
        Vec3(MODULE_SIZE * 0.5, MODULE_SIZE * 0.5, DECK_Z - 0.09),
        MODULE_SIZE,
        MODULE_SIZE,
        (0, -90, 0),
        tex["surface"],
        3.1,
        3.1,
    )
    tint = 0.72 - phase * 0.02
    ground.setColorScale(tint, tint, tint * 0.98, 1.0)
    try:
        game.deck_surfaces.append(ground)
    except Exception:
        pass


def _crater_specs(mx: int, my: int) -> List[Tuple[Vec3, float, float]]:
    rnd = Random(_hash_u32(mx, my, 0x43524154))
    specs: List[Tuple[Vec3, float, float]] = []
    count = 3 + rnd.randrange(3)
    for _ in range(count):
        x = rnd.uniform(CELL * 1.1, MODULE_SIZE - CELL * 1.1)
        y = rnd.uniform(CELL * 1.1, MODULE_SIZE - CELL * 1.1)
        radius = rnd.uniform(CELL * 1.6, CELL * 4.2)
        depth = rnd.uniform(0.25, 0.58)
        specs.append((Vec3(x, y, DECK_Z + 0.008), radius, depth))
    return specs


def _add_craters(game, parent, mx: int, my: int, light_factor: float) -> None:
    tex = _ensure_runtime_assets(game)
    for center, radius, depth in _crater_specs(mx, my):
        crater = game._add_plane(
            parent,
            center,
            radius * 2.0,
            radius * 2.0,
            (0, -90, 0),
            tex["crater"],
            1.0,
            1.0,
            True,
        )
        crater.setDepthWrite(False)
        crater.setBin("transparent", 18)
        shade = 0.80 + light_factor * 0.22
        alpha = 0.38 + depth * 0.30
        crater.setColorScale(shade, shade, shade, alpha)

        shadow = game._add_plane(
            parent,
            center + Vec3(-radius * 0.12, -radius * 0.18, 0.006),
            radius * 1.5,
            radius * 0.78,
            (0, -90, 0),
            tex["crater"],
            1.0,
            1.0,
            True,
        )
        shadow.setDepthWrite(False)
        shadow.setBin("transparent", 17)
        shadow.setColorScale(0.0, 0.0, 0.0, 0.10 + (1.0 - light_factor) * 0.12)


def _rock_height(mx: int, my: int, x: int, y: int) -> float:
    seed = _hash_u32(mx, my, x, y, 0x524F434B)
    return 1.2 + ((seed >> 8) & 255) / 255.0 * 2.5


def _add_rock_cluster(game, parent, mx: int, my: int, gx: int, gy: int, light_factor: float) -> None:
    tex = _ensure_runtime_assets(game)
    center_x = gx * CELL + CELL * 0.5
    center_y = gy * CELL + CELL * 0.5
    h = _rock_height(mx, my, gx, gy)

    seed = _hash_u32(mx, my, gx, gy, 0xA114)
    rnd = Random(seed)
    cluster = parent.attachNewNode(f"level4_blob_cluster_{mx}_{my}_{gx}_{gy}")
    cluster.setPos(center_x, center_y, 0.0)
    cluster.setH(rnd.uniform(0.0, 360.0))

    lumps = 4 + (1 if rnd.random() < 0.7 else 0) + (1 if rnd.random() < 0.3 else 0)
    base_rad = CELL * rnd.uniform(0.48, 0.92)
    for idx in range(lumps):
        sx = base_rad * rnd.uniform(0.8, 1.55)
        sy = base_rad * rnd.uniform(0.7, 1.70)
        sz = h * rnd.uniform(0.18, 0.45)
        ox = rnd.uniform(-CELL * 0.26, CELL * 0.26)
        oy = rnd.uniform(-CELL * 0.26, CELL * 0.26)
        oz = rnd.uniform(-0.06, 0.10) + sz * 0.5
        blob = game._add_box(cluster, Vec3(ox, oy, oz), Vec3(sx, sy, sz), tex["rock"])
        blob.setH(rnd.uniform(0.0, 360.0))
        blob.setP(rnd.uniform(-24.0, 24.0))
        blob.setR(rnd.uniform(-22.0, 22.0))
        shade = 0.58 + light_factor * 0.30 + idx * 0.025
        blob.setColorScale(shade * 1.02, shade, shade * 0.90, 1.0)

    if rnd.random() < 0.72:
        shard_h = h * rnd.uniform(0.46, 0.86)
        shard = game._add_box(
            cluster,
            Vec3(rnd.uniform(-0.22, 0.22), rnd.uniform(-0.22, 0.22), shard_h * 0.5 + 0.06),
            Vec3(base_rad * rnd.uniform(0.16, 0.30), base_rad * rnd.uniform(0.48, 0.72), shard_h),
            tex["rock"],
        )
        shard.setP(rnd.uniform(-36.0, 36.0))
        shard.setR(rnd.uniform(-28.0, 28.0))
        shard.setColorScale(0.64 + light_factor * 0.28, 0.63 + light_factor * 0.26, 0.56 + light_factor * 0.24, 1.0)

def _add_module_sunlight(game, parent, mx: int, my: int, light_factor: float) -> None:
    if light_factor <= 0.02:
        return
    try:
        sun = DirectionalLight(f"level4_sun_{mx}_{my}")
        power = 0.20 + light_factor * 0.85
        sun.setColor(Vec4(0.78 * power, 0.76 * power, 0.66 * power, 1.0))
        sun_np = parent.attachNewNode(sun)
        sun_np.setHpr(-22.0, -38.0, 0.0)
        parent.setLight(sun_np)
        try:
            game.module_sun_lights.append(sun_np)
        except Exception:
            pass

        game._add_point_light(
            parent,
            Vec3(MODULE_SIZE * 0.72, MODULE_SIZE * 0.88, 10.0),
            Vec4(0.24 * light_factor, 0.23 * light_factor, 0.18 * light_factor, 1.0),
            Vec3(1.0, 0.0, 0.010),
            phase=mx * 0.13 + my * 0.17,
            pulse=0.004,
        )
    except Exception as exc:
        _write_log(game, "add_module_sunlight", exc, {"mx": mx, "my": my, "light_factor": light_factor})


def _add_dust_haze(game, parent, light_factor: float) -> None:
    if light_factor <= 0.18:
        return
    try:
        tex = getattr(game, "light_tex")
        haze = game._add_plane(
            parent,
            Vec3(MODULE_SIZE * 0.5, MODULE_SIZE * 0.79, 1.55),
            MODULE_SIZE * 0.90,
            3.8,
            (0, 0, 0),
            tex,
            1.0,
            1.0,
            True,
        )
        haze.setDepthWrite(False)
        haze.setBin("transparent", 14)
        haze.setColorScale(0.90, 0.83, 0.66, 0.040 + light_factor * 0.050)
        haze2 = game._add_plane(
            parent,
            Vec3(MODULE_SIZE * 0.5, MODULE_SIZE * 0.64, 1.16),
            MODULE_SIZE * 0.62,
            2.4,
            (0, 0, 0),
            tex,
            1.0,
            1.0,
            True,
        )
        haze2.setDepthWrite(False)
        haze2.setBin("transparent", 15)
        haze2.setColorScale(0.72, 0.68, 0.56, 0.026 + light_factor * 0.028)
    except Exception as exc:
        _write_log(game, "add_dust_haze", exc, {"light_factor": light_factor})


def build_module(game, root, water_root, mx: int, my: int, data) -> None:
    del water_root
    try:
        grid: List[List[int]] = data.grid
        phase = int(getattr(data, "style_id", 0))
        center_world = _module_center_world(mx, my)
        light_factor = _moon_side_factor(center_world.y)

        _make_ground_plane(game, root, phase)
        _add_terrain_shell(game, root, mx, my, phase, light_factor)
        _add_craters(game, root, mx, my, light_factor)
        _add_dust_haze(game, root, light_factor)
        _add_module_sunlight(game, root, mx, my, light_factor)

        for y in range(MODULE_CELLS):
            for x in range(MODULE_CELLS):
                if grid[y][x] == SOLID:
                    _add_rock_cluster(game, root, mx, my, x, y, light_factor)

        world_y0 = my * MODULE_SIZE
        world_y1 = world_y0 + MODULE_SIZE
        if world_y0 < TERMINATOR_Y < world_y1:
            band_local_y = TERMINATOR_Y - world_y0
            tex = _ensure_runtime_assets(game)["crater"]
            band = game._add_plane(
                root,
                Vec3(MODULE_SIZE * 0.5, band_local_y - 1.6, DECK_Z + 0.010),
                MODULE_SIZE,
                6.4,
                (0, -90, 0),
                tex,
                1.0,
                1.0,
                True,
            )
            band.setDepthWrite(False)
            band.setBin("transparent", 16)
            band.setColorScale(0.02, 0.02, 0.024, 0.16)
    except Exception as exc:
        _write_log(game, "build_module", exc, {"mx": mx, "my": my, "style_id": getattr(data, "style_id", "?")})
        raise
