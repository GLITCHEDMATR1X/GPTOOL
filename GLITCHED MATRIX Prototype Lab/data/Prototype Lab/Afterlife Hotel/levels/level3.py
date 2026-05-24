from __future__ import annotations

import math
from random import Random
from typing import Any, Dict, List, Sequence, Tuple

from panda3d.core import PNMImage, Texture, Vec3, Vec4

CELL = 2.55
MODULE_CELLS = 12
MODULE_SIZE = CELL * MODULE_CELLS
DECK_Z = 0.0
WALL_H = 4.4
STYLE_NAME = "Mariana Brine Trench"
STYLE_ID = 6


def _clamp(v: float, lo: float, hi: float) -> float:
    return lo if v < lo else hi if v > hi else v


def _hash01(a: float, b: float, c: float = 0.0) -> float:
    return 0.5 + 0.5 * math.sin(a * 12.9898 + b * 78.233 + c * 37.719)


def get_level_settings(_game=None) -> Dict[str, Any]:
    return {
        "display_name": "Level 3",
        "style_name": STYLE_NAME,
        "move_speed_mult": 0.93,
        "bg_color": (0.010, 0.030, 0.048, 1.0),
        "fog_color": (0.030, 0.082, 0.116, 1.0),
        "ambient_light": (0.050, 0.084, 0.098, 1.0),
        "sun_light": (0.016, 0.030, 0.038, 1.0),
        "fill_light": (0.026, 0.058, 0.074, 1.0),
        "lift_light": (0.034, 0.068, 0.086, 1.0),
        "dark_bg_color": (0.006, 0.018, 0.030, 1.0),
        "dark_fog_color": (0.018, 0.050, 0.076, 1.0),
        "dark_ambient_light": (0.026, 0.046, 0.056, 1.0),
        "dark_sun_light": (0.010, 0.020, 0.026, 1.0),
        "dark_fill_light": (0.016, 0.034, 0.046, 1.0),
        "dark_lift_light": (0.020, 0.040, 0.052, 1.0),
        "fog_start": 0.12,
        "fog_end": 10.6,
        "dark_fog_start": 0.08,
        "dark_fog_end": 6.8,
        "load_radius": 2,
        "unload_radius": 4,
        "static_water_default": False,
        "force_detail_overlay_alpha": 0.14,
        "force_reflection_overlay_alpha": 0.12,
        "weapon_color_scale": (0.64, 0.79, 0.92, 1.0),
        "weapon_pulse_strength": 0.035,
        "weapon_sink": -0.022,
        "weapon_indicator_tint": (0.56, 0.80, 0.90, 1.0),
        "weapon_caustic_strength": 0.0,
    }


def _make_silt_texture(game) -> Texture:
    img = PNMImage(768, 768, 4)
    for y in range(768):
        fy = y / 767.0
        for x in range(768):
            fx = x / 767.0
            ridge_a = math.sin((fx * 5.2 + fy * 0.8) * math.tau) * 0.016
            ridge_b = math.cos((fx * 0.9 - fy * 4.4) * math.tau) * 0.012
            ripple = math.sin((fx * 18.0 + fy * 2.8) * math.tau) * 0.010
            ripple += math.cos((fx * 2.4 - fy * 14.0) * math.tau) * 0.008
            grain = (((x * 17 + y * 29) % 131) / 131.0 - 0.5) * 0.040
            speck = -0.070 if ((x * 7 + y * 13) % 89) == 0 else 0.0
            base = 0.17 + ridge_a + ridge_b + ripple + grain + speck
            cold = math.sin((fx * 1.4 + fy * 1.1) * math.tau) * 0.012
            r = _clamp(base + 0.035, 0.0, 1.0)
            g = _clamp(base + 0.055 + cold, 0.0, 1.0)
            b = _clamp(base + 0.070 + cold * 1.3, 0.0, 1.0)
            img.setXelA(x, y, r, g, b, 1.0)
    tex = Texture("level3_silt_tex")
    tex.load(img)
    return game._finish_tex(tex)


def _make_brine_texture(game) -> Texture:
    img = PNMImage(512, 512, 4)
    for y in range(512):
        fy = y / 511.0
        for x in range(512):
            fx = x / 511.0
            wave = math.sin((fx * 3.6 + fy * 2.9) * math.tau) * 0.08
            wave += math.cos((fx * 8.0 - fy * 5.2) * math.tau) * 0.06
            streak = math.sin((fx * 18.0 + fy * 2.3) * math.tau) * 0.025
            swirl = math.cos((fx * 1.1 + fy * 1.6) * math.tau) * 0.03
            shade = 0.09 + wave + streak + swirl
            r = _clamp(shade * 0.42, 0.0, 1.0)
            g = _clamp(shade * 0.62 + 0.02, 0.0, 1.0)
            b = _clamp(shade * 0.86 + 0.05, 0.0, 1.0)
            alpha = _clamp(0.66 + wave * 0.45 + streak * 0.60, 0.22, 0.96)
            img.setXelA(x, y, r, g, b, alpha)
    tex = Texture("level3_brine_tex")
    tex.load(img)
    return game._finish_tex(tex, clamp_mode=True)


def _make_rim_texture(game) -> Texture:
    img = PNMImage(512, 512, 4)
    cx = cy = 255.5
    for y in range(512):
        for x in range(512):
            dx = (x - cx) / 255.5
            dy = (y - cy) / 255.5
            dist = math.sqrt(dx * dx + dy * dy)
            ring = math.exp(-((dist - 0.78) ** 2) / 0.010)
            breakup = 0.5 + 0.5 * math.sin((dx * 8.0 + dy * 5.2) * math.tau)
            breakup += 0.5 + 0.5 * math.cos((dx * 5.0 - dy * 9.0) * math.tau)
            breakup *= 0.5
            alpha = _clamp(ring * (0.30 + breakup * 0.55), 0.0, 0.92)
            r = 0.58 + breakup * 0.14
            g = 0.72 + breakup * 0.12
            b = 0.66 + breakup * 0.06
            img.setXelA(x, y, r, g, b, alpha)
    tex = Texture("level3_rim_tex")
    tex.load(img)
    return game._finish_tex(tex, clamp_mode=True)


def _make_haze_texture(game) -> Texture:
    img = PNMImage(512, 512, 4)
    for y in range(512):
        fy = y / 511.0
        for x in range(512):
            fx = x / 511.0
            cloud = 0.5 + math.sin((fx * 1.7 + fy * 1.1) * math.tau) * 0.18
            cloud += math.cos((fx * 2.8 - fy * 1.9) * math.tau) * 0.12
            cloud += math.sin((fx * 5.7 + fy * 4.3) * math.tau) * 0.06
            alpha = _clamp(0.20 + cloud * 0.18, 0.0, 0.54)
            img.setXelA(x, y, 0.22, 0.34, 0.40, alpha)
    tex = Texture("level3_haze_tex")
    tex.load(img)
    return game._finish_tex(tex, clamp_mode=True)


def _make_marine_snow_texture(game) -> Texture:
    img = PNMImage(512, 512, 4)
    for y in range(512):
        for x in range(512):
            img.setXelA(x, y, 0.0, 0.0, 0.0, 0.0)
    for y in range(512):
        for x in range(512):
            hv = ((x * 19 + y * 73 + x * y * 3) % 997) / 997.0
            if hv > 0.992:
                img.setXelA(x, y, 0.82, 0.92, 0.96, 0.92)
            elif hv > 0.988:
                img.setXelA(x, y, 0.62, 0.80, 0.90, 0.55)
            elif hv > 0.985:
                img.setXelA(x, y, 0.50, 0.70, 0.84, 0.30)
    tex = Texture("level3_marine_snow_tex")
    tex.load(img)
    return game._finish_tex(tex, clamp_mode=True)


def _make_smoker_texture(game) -> Texture:
    img = PNMImage(512, 512, 4)
    for y in range(512):
        fy = y / 511.0
        for x in range(512):
            fx = x / 511.0
            column = 0.12 + math.sin((fx * 7.0 + fy * 2.6) * math.tau) * 0.04
            column += math.cos((fx * 2.0 - fy * 6.4) * math.tau) * 0.03
            crack = -0.06 if ((x * 11 + y * 5) % 83) < 3 else 0.0
            glow = 0.02 if ((x * 13 + y * 17) % 127) == 0 else 0.0
            base = _clamp(column + crack + glow, 0.0, 1.0)
            img.setXelA(x, y, base * 0.42, base * 0.46 + 0.02, base * 0.52 + 0.03, 1.0)
    tex = Texture("level3_smoker_tex")
    tex.load(img)
    return game._finish_tex(tex)


def on_level_load(game) -> None:
    state = getattr(game, "level_runtime_state", None)
    if state is None:
        game.level_runtime_state = {}
        state = game.level_runtime_state
    state["level3_silt_tex"] = _make_silt_texture(game)
    state["level3_brine_tex"] = _make_brine_texture(game)
    state["level3_rim_tex"] = _make_rim_texture(game)
    state["level3_haze_tex"] = _make_haze_texture(game)
    state["level3_marine_snow_tex"] = _make_marine_snow_texture(game)
    state["level3_smoker_tex"] = _make_smoker_texture(game)


def build_module_data(_game, _mx: int, _my: int):
    grid = [[1 for _ in range(MODULE_CELLS)] for __ in range(MODULE_CELLS)]
    return {"grid": grid, "style_id": STYLE_ID}


def _ensure_textures(game) -> Dict[str, Texture]:
    state = getattr(game, "level_runtime_state", {})
    needed = (
        "level3_silt_tex",
        "level3_brine_tex",
        "level3_rim_tex",
        "level3_haze_tex",
        "level3_marine_snow_tex",
        "level3_smoker_tex",
    )
    if any(k not in state for k in needed):
        on_level_load(game)
        state = getattr(game, "level_runtime_state", {})
    return {k: state[k] for k in needed}


def _pool_layout(mx: int, my: int, rnd: Random) -> List[Tuple[float, float, float, float, float]]:
    anchors: Sequence[Tuple[float, float]] = (
        (0.18, 0.26),
        (0.79, 0.24),
        (0.24, 0.80),
        (0.82, 0.76),
        (0.14, 0.58),
        (0.86, 0.52),
        (0.34, 0.14),
        (0.64, 0.86),
    )
    pools: List[Tuple[float, float, float, float, float]] = []
    density = 0.5 + 0.5 * math.sin(mx * 0.63 + my * 0.91) + 0.5 * math.cos(mx * 0.27 - my * 0.51)
    count = 0
    if density > 0.82:
        count = 2
    elif density > 0.18:
        count = 1
    if mx == 0 and my == 0:
        count = 1
    count = max(0, min(2, count))
    choices = list(range(len(anchors)))
    rnd.shuffle(choices)
    for idx in choices[:count]:
        ax, ay = anchors[idx]
        px = MODULE_SIZE * (ax + rnd.uniform(-0.035, 0.035))
        py = MODULE_SIZE * (ay + rnd.uniform(-0.035, 0.035))
        if (px - MODULE_SIZE * 0.5) ** 2 + (py - MODULE_SIZE * 0.5) ** 2 < (CELL * 2.6) ** 2:
            continue
        rx = MODULE_SIZE * rnd.uniform(0.20, 0.31)
        ry = MODULE_SIZE * rnd.uniform(0.12, 0.22)
        rot = rnd.uniform(-80.0, 80.0)
        pools.append((px, py, rx, ry, rot))
    return pools


def _add_relief_planes(game, root, mx: int, my: int, silt_tex: Texture, haze_tex: Texture) -> None:
    rnd = Random(game._module_seed(mx, my) ^ 0x3A11CE)
    center = Vec3(MODULE_SIZE * 0.5, MODULE_SIZE * 0.5, DECK_Z)

    for idx in range(5):
        ridge = game._add_plane(
            root,
            Vec3(
                MODULE_SIZE * rnd.uniform(0.12, 0.88),
                MODULE_SIZE * rnd.uniform(0.12, 0.88),
                DECK_Z + 0.016 + idx * 0.002,
            ),
            MODULE_SIZE * rnd.uniform(0.60, 1.05),
            CELL * rnd.uniform(1.1, 2.8),
            (rnd.uniform(-75.0, 75.0), -90, 0),
            silt_tex,
            MODULE_CELLS * rnd.uniform(0.35, 0.75),
            2.2,
            True,
        )
        ridge.setDepthWrite(False)
        ridge.setColorScale(0.06, 0.10, 0.12, rnd.uniform(0.07, 0.15))
        game.deck_gloss_overlays.append((ridge, mx * 0.06 + idx * 0.17, my * -0.03 + idx * 0.09))

    scar = game._add_plane(
        root,
        center + Vec3(rnd.uniform(-1.1, 1.1), rnd.uniform(-1.3, 1.3), 0.018),
        MODULE_SIZE * rnd.uniform(0.90, 1.18),
        CELL * rnd.uniform(2.0, 3.6),
        (rnd.uniform(-65.0, 65.0), -90, 0),
        haze_tex,
        1.3,
        0.8,
        True,
    )
    scar.setDepthWrite(False)
    scar.setColorScale(0.03, 0.06, 0.08, 0.32)
    game.deck_reflection_overlays.append((scar, mx * 0.04 + 0.2, my * 0.05 + 0.11))

    if abs(math.sin(mx * 0.37 + my * 0.22)) > 0.72:
        side = -1.0 if math.sin(mx * 0.51 - my * 0.36) < 0.0 else 1.0
        cliff = game._add_plane(
            root,
            Vec3(MODULE_SIZE * (0.08 if side < 0.0 else 0.92), MODULE_SIZE * 0.55, WALL_H * 1.12),
            MODULE_SIZE * 0.95,
            WALL_H * 3.2,
            (90 if side < 0.0 else -90, 0, 0),
            haze_tex,
            1.0,
            1.0,
            True,
        )
        cliff.setDepthWrite(False)
        cliff.setColorScale(0.02, 0.05, 0.07, 0.22)
        game.deck_reflection_overlays.append((cliff, mx * 0.02 + 0.07, my * 0.03 + 0.21))


def _add_brine_pools(game, root, mx: int, my: int, brine_tex: Texture, rim_tex: Texture, haze_tex: Texture) -> None:
    rnd = Random(game._module_seed(mx, my) ^ 0xB91F5)
    for idx, (px, py, rx, ry, rot) in enumerate(_pool_layout(mx, my, rnd)):
        center = Vec3(px, py, DECK_Z)

        basin = game._add_plane(
            root,
            center + Vec3(0.0, 0.0, 0.010),
            rx * 1.54,
            ry * 1.54,
            (rot, -90, 0),
            haze_tex,
            1.0,
            1.0,
            True,
        )
        basin.setDepthWrite(False)
        basin.setColorScale(0.03, 0.05, 0.06, 0.34)
        game.deck_reflection_overlays.append((basin, mx * 0.03 + idx * 0.19, my * -0.02 + idx * 0.23))

        rim = game._add_plane(
            root,
            center + Vec3(0.0, 0.0, 0.016),
            rx * 1.34,
            ry * 1.34,
            (rot, -90, 0),
            rim_tex,
            1.0,
            1.0,
            True,
        )
        rim.setDepthWrite(False)
        rim.setColorScale(0.84, 0.94, 0.88, 0.50)
        game.deck_gloss_overlays.append((rim, mx * -0.02 + idx * 0.14, my * 0.03 + idx * 0.16))

        surface = game._add_plane(
            root,
            center + Vec3(0.0, 0.0, 0.022),
            rx,
            ry,
            (rot, -90, 0),
            brine_tex,
            1.6,
            1.2,
            True,
        )
        surface.setDepthWrite(False)
        surface.setColorScale(0.14, 0.24, 0.32, 0.94)
        game.water_reflection_overlays.append((surface, mx * 0.07 + idx * 0.17, my * 0.05 + idx * 0.12))

        sheen = game._add_plane(
            root,
            center + Vec3(0.0, 0.0, 0.026),
            rx * 0.82,
            ry * 0.76,
            (rot + 9.0, -90, 0),
            brine_tex,
            0.8,
            0.8,
            True,
        )
        sheen.setDepthWrite(False)
        sheen.setColorScale(0.22, 0.34, 0.38, 0.18)
        game.water_detail_overlays.append((sheen, mx * -0.05 + idx * 0.31, my * 0.02 + idx * 0.27))

        if rnd.random() < 0.55:
            mat = game._add_plane(
                root,
                center + Vec3(rx * rnd.uniform(-0.22, 0.22), ry * rnd.uniform(-0.22, 0.22), 0.024),
                rx * rnd.uniform(0.26, 0.40),
                ry * rnd.uniform(0.18, 0.30),
                (rot + rnd.uniform(-35.0, 35.0), -90, 0),
                rim_tex,
                1.0,
                1.0,
                True,
            )
            mat.setDepthWrite(False)
            mat.setColorScale(0.52, 0.88, 0.82, 0.14)
            game.deck_gloss_overlays.append((mat, mx * 0.09 + idx * 0.11, my * -0.04 + idx * 0.18))

        if rnd.random() < 0.40:
            glow_pos = Vec3(px + rx * 0.20, py - ry * 0.16, 0.12)
            game._add_point_light(
                root,
                glow_pos,
                Vec4(0.05, 0.14, 0.16, 1.0),
                Vec3(1.0, 0.0, 0.11),
                phase=(mx + my + idx) * 0.7,
                pulse=0.04,
            )


def _add_smokers(game, root, mx: int, my: int, smoker_tex: Texture, haze_tex: Texture) -> None:
    signature = math.sin(mx * 0.71 + my * 0.37) + math.cos(mx * 0.42 - my * 0.84)
    if signature < 1.0:
        return
    rnd = Random(game._module_seed(mx, my) ^ 0x541E2)
    cluster_count = 1 if signature < 1.45 else 2
    for cluster in range(cluster_count):
        base_x = MODULE_SIZE * rnd.uniform(0.16, 0.84)
        base_y = MODULE_SIZE * rnd.uniform(0.14, 0.86)
        if (base_x - MODULE_SIZE * 0.5) ** 2 + (base_y - MODULE_SIZE * 0.5) ** 2 < (CELL * 2.4) ** 2:
            base_y = MODULE_SIZE * 0.82
        for idx in range(rnd.randint(1, 3)):
            offset_x = rnd.uniform(-CELL * 0.55, CELL * 0.55)
            offset_y = rnd.uniform(-CELL * 0.55, CELL * 0.55)
            h = rnd.uniform(WALL_H * 0.70, WALL_H * 1.36)
            r = rnd.uniform(0.24, 0.48)
            chimney = game._add_round_column(root, Vec3(base_x + offset_x, base_y + offset_y, h * 0.5), r, h, smoker_tex)
            # _add_round_column returns None; darken latest geometry by wrapping a separate cap.
            cap = game._add_box(root, Vec3(base_x + offset_x, base_y + offset_y, h + 0.12), Vec3(r * 1.4, r * 1.4, 0.18), smoker_tex)
            cap.setColorScale(0.12, 0.14, 0.16, 1.0)
            plume = game._add_plane(
                root,
                Vec3(base_x + offset_x, base_y + offset_y, h + WALL_H * 0.40),
                r * 3.6,
                WALL_H * 1.8,
                (rnd.uniform(-18.0, 18.0), 0, 0),
                haze_tex,
                1.0,
                1.4,
                True,
            )
            plume.setDepthWrite(False)
            plume.setColorScale(0.10, 0.12, 0.13, 0.14)
            game.deck_reflection_overlays.append((plume, mx * 0.03 + cluster * 0.21 + idx * 0.12, my * 0.04 + idx * 0.17))
        game._add_point_light(
            root,
            Vec3(base_x, base_y, 0.32),
            Vec4(0.07, 0.16, 0.17, 1.0),
            Vec3(1.0, 0.0, 0.15),
            phase=(mx - my + cluster) * 0.9,
            pulse=0.05,
        )


def _add_marine_snow(game, root, mx: int, my: int, snow_tex: Texture) -> None:
    rnd = Random(game._module_seed(mx, my) ^ 0x8A0D4)
    for idx in range(3):
        cx = MODULE_SIZE * rnd.uniform(0.18, 0.82)
        cy = MODULE_SIZE * rnd.uniform(0.18, 0.82)
        z = WALL_H * rnd.uniform(0.75, 1.35)
        yaw = rnd.uniform(-45.0, 45.0)
        curtain = game._add_plane(
            root,
            Vec3(cx, cy, z),
            MODULE_SIZE * rnd.uniform(0.44, 0.78),
            WALL_H * rnd.uniform(1.5, 2.3),
            (yaw, 0, 0),
            snow_tex,
            1.0,
            1.8,
            True,
        )
        curtain.setDepthWrite(False)
        curtain.setColorScale(0.56, 0.74, 0.84, rnd.uniform(0.05, 0.10))
        game.deck_reflection_overlays.append((curtain, mx * 0.014 + idx * 0.07, my * 0.008 + idx * 0.11))


def build_module(game, root, _water_root, mx: int, my: int, _data) -> None:
    tex = _ensure_textures(game)
    silt_tex = tex["level3_silt_tex"]
    brine_tex = tex["level3_brine_tex"]
    rim_tex = tex["level3_rim_tex"]
    haze_tex = tex["level3_haze_tex"]
    snow_tex = tex["level3_marine_snow_tex"]
    smoker_tex = tex["level3_smoker_tex"]

    center = Vec3(MODULE_SIZE * 0.5, MODULE_SIZE * 0.5, DECK_Z)
    floor = game._add_plane(
        root,
        center,
        MODULE_SIZE,
        MODULE_SIZE,
        (0, -90, 0),
        silt_tex,
        MODULE_CELLS * 0.85,
        MODULE_CELLS * 0.85,
    )
    floor.setColorScale(0.74, 0.82, 0.88, 1.0)
    game.deck_surfaces.append(floor)

    abyss_shadow = game._add_plane(
        root,
        center + Vec3(0.0, 0.0, 0.012),
        MODULE_SIZE,
        MODULE_SIZE,
        (0, -90, 0),
        haze_tex,
        0.6,
        0.6,
        True,
    )
    abyss_shadow.setDepthWrite(False)
    abyss_shadow.setColorScale(0.04, 0.08, 0.10, 0.12)
    game.deck_reflection_overlays.append((abyss_shadow, mx * 0.03, my * -0.03))

    _add_relief_planes(game, root, mx, my, silt_tex, haze_tex)
    _add_brine_pools(game, root, mx, my, brine_tex, rim_tex, haze_tex)
    _add_smokers(game, root, mx, my, smoker_tex, haze_tex)
    _add_marine_snow(game, root, mx, my, snow_tex)

    # Sparse, cold abyssal glow.
    game._add_point_light(
        root,
        Vec3(MODULE_SIZE * 0.32, MODULE_SIZE * 0.28, WALL_H * 0.92),
        Vec4(0.04, 0.09, 0.12, 1.0),
        Vec3(1.0, 0.0, 0.020),
        phase=(mx + my) * 0.48,
        pulse=0.03,
    )
    game._add_point_light(
        root,
        Vec3(MODULE_SIZE * 0.76, MODULE_SIZE * 0.70, WALL_H * 0.84),
        Vec4(0.03, 0.07, 0.10, 1.0),
        Vec3(1.0, 0.0, 0.022),
        phase=(mx - my) * 0.42 + 1.2,
        pulse=0.025,
    )
