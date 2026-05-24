from __future__ import annotations

import math
from random import Random
from typing import Dict, List, Tuple

from panda3d.core import PNMImage, Texture, TransparencyAttrib, Vec3, Vec4


CELL = 2.55
MODULE_CELLS = 12
MODULE_SIZE = CELL * MODULE_CELLS
WALL_H = 4.4

SOLID = 0
DECK = 1
WATER = 2

FLOOR_Z = -0.92
WATER_Z = 0.78
WATER_DETAIL_Z = WATER_Z + 0.018
WATER_REFLECT_Z = WATER_Z + 0.028
CEILING_Z = WALL_H
CORRIDOR_HALF_W = 2.15


# ------------------------------------------------------------
# deterministic layout helpers
# ------------------------------------------------------------
def _hash_u32(*vals: int) -> int:
    h = 2166136261
    for v in vals:
        h = (h ^ (int(v) & 0xFFFFFFFF)) * 16777619
        h &= 0xFFFFFFFF
    return h


def _clamp(v: float, lo: float, hi: float) -> float:
    return lo if v < lo else hi if v > hi else v


def _seed(game, mx: int, my: int, salt: int) -> int:
    return int(game._module_seed(mx, my) ^ salt)


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _smoothstep(t: float) -> float:
    return t * t * (3.0 - 2.0 * t)


def _seam_center(mx: int, seam_y: int) -> float:
    rnd = Random(_hash_u32(mx, seam_y, 0x5EAA12D5))
    return 3.2 + rnd.random() * 5.6


def _corridor_profile(mx: int, my: int) -> Tuple[float, float, float, float]:
    south = _seam_center(mx, my)
    north = _seam_center(mx, my + 1)
    rnd = Random(_hash_u32(mx, my, 0x511E50A5))
    amp = 0.55 + rnd.random() * 0.90
    phase = rnd.random() * math.tau
    return south, north, amp, phase


def _corridor_center(mx: int, my: int, y_cell: float) -> float:
    south, north, amp, phase = _corridor_profile(mx, my)
    t = _clamp(y_cell / max(1.0, MODULE_CELLS - 1.0), 0.0, 1.0)
    s = _smoothstep(t)
    base = _lerp(south, north, s)
    edge_fade = math.sin(t * math.pi)
    bend = math.sin(t * math.pi * 1.55 + phase) * amp * edge_fade
    return _clamp(base + bend, 2.55, MODULE_CELLS - 2.55)


def _corridor_derivative(mx: int, my: int, y_cell: float) -> float:
    a = _corridor_center(mx, my, y_cell - 0.35)
    b = _corridor_center(mx, my, y_cell + 0.35)
    return (b - a) / 0.70


def _alcove_info(mx: int, my: int) -> Tuple[int, int, int, int]:
    rnd = Random(_hash_u32(mx, my, 0xA1C0AE55))
    side = -1 if rnd.random() < 0.5 else 1
    y0 = 3 + rnd.randrange(4)
    length = 2 + (1 if rnd.random() < 0.55 else 0)
    depth = 2
    return side, y0, length, depth


def _tile_run(grid: List[List[int]], target: int, y: int) -> List[Tuple[int, int]]:
    runs: List[Tuple[int, int]] = []
    x = 0
    while x < MODULE_CELLS:
        while x < MODULE_CELLS and grid[y][x] != target:
            x += 1
        if x >= MODULE_CELLS:
            break
        start = x
        while x < MODULE_CELLS and grid[y][x] == target:
            x += 1
        runs.append((start, x))
    return runs


# ------------------------------------------------------------
# textures
# ------------------------------------------------------------
def _finish_custom_tex(game, tex: Texture, clamp_mode: bool = False) -> Texture:
    if hasattr(game, "_finish_tex"):
        return game._finish_tex(tex, clamp_mode=clamp_mode)
    return tex


def _make_tile_texture(game) -> Texture:
    size = 512
    img = PNMImage(size, size, 4)
    for y in range(size):
        for x in range(size):
            fx = x / (size - 1)
            fy = y / (size - 1)
            grime = 0.020 * math.sin(fx * 19.0 + fy * 6.0) + 0.016 * math.cos(fx * 8.0 - fy * 13.0)
            stain = 0.040 * (fy ** 1.55) + 0.014 * math.sin((fx + fy) * 10.0)
            base = _clamp(0.91 - stain + grime, 0.70, 0.97)
            r = _clamp(base + 0.028, 0.0, 1.0)
            g = _clamp(base + 0.018, 0.0, 1.0)
            b = _clamp(base - 0.010, 0.0, 1.0)
            img.setXelA(x, y, r, g, b, 1.0)

    step = 48
    line = 3
    for y in range(size):
        for x in range(size):
            if (x % step) < line or (y % step) < line:
                a = 0.70 if ((x % step) < line and (y % step) < line) else 0.54
                base = 0.70 - (0.12 if y > size * 0.65 else 0.0)
                img.setXelA(x, y, base, base, base * 0.98, a)

    tex = Texture("level5_tile_tex")
    tex.load(img)
    return _finish_custom_tex(game, tex)


def _make_ceiling_texture(game) -> Texture:
    size = 384
    img = PNMImage(size, size, 4)
    for y in range(size):
        for x in range(size):
            fx = x / (size - 1)
            fy = y / (size - 1)
            grain = 0.014 * math.sin(fx * 12.0) + 0.012 * math.cos(fy * 9.0) + 0.010 * math.sin((fx + fy) * 17.0)
            warm = 0.87 - fy * 0.05 + grain
            img.setXelA(x, y, _clamp(warm + 0.05, 0.0, 1.0), _clamp(warm + 0.03, 0.0, 1.0), _clamp(warm, 0.0, 1.0), 1.0)
    tex = Texture("level5_ceiling_tex")
    tex.load(img)
    return _finish_custom_tex(game, tex)


def _make_muck_texture(game) -> Texture:
    size = 384
    img = PNMImage(size, size, 4)
    for y in range(size):
        for x in range(size):
            fx = x / (size - 1)
            fy = y / (size - 1)
            rip = 0.06 * math.sin(fx * 13.0 + fy * 11.0) + 0.04 * math.cos(fx * 8.0 - fy * 5.0)
            sludge = 0.19 + 0.10 * fy + rip * 0.35
            img.setXelA(x, y, _clamp(sludge * 0.55, 0.0, 1.0), _clamp(sludge * 0.74, 0.0, 1.0), _clamp(sludge * 0.56, 0.0, 1.0), 1.0)
    tex = Texture("level5_muck_tex")
    tex.load(img)
    return _finish_custom_tex(game, tex)


def _make_door_texture(game) -> Texture:
    w, h = 192, 384
    img = PNMImage(w, h, 4)
    for y in range(h):
        for x in range(w):
            fx = x / (w - 1)
            fy = y / (h - 1)
            grain = 0.04 * math.sin(fx * 12.0 + fy * 7.0) + 0.02 * math.cos(fx * 27.0)
            c = 0.10 + grain * 0.35
            if 0.10 < fx < 0.90 and 0.06 < fy < 0.96:
                r = _clamp(c + 0.03, 0.0, 1.0)
                g = _clamp(c + 0.02, 0.0, 1.0)
                b = _clamp(c + 0.01, 0.0, 1.0)
            else:
                r = g = b = 0.03
            img.setXelA(x, y, r, g, b, 1.0)

    for y in range(h):
        for x in range(w):
            fx = x / (w - 1)
            fy = y / (h - 1)
            if 0.77 < fx < 0.83 and 0.46 < fy < 0.56:
                img.setXelA(x, y, 0.62, 0.57, 0.46, 1.0)
    tex = Texture("level5_door_tex")
    tex.load(img)
    return _finish_custom_tex(game, tex, clamp_mode=True)


def _make_vine_texture(game) -> Texture:
    w, h = 256, 512
    img = PNMImage(w, h, 4)
    for y in range(h):
        for x in range(w):
            img.setXelA(x, y, 0.0, 0.0, 0.0, 0.0)
    for branch in range(6):
        phase = branch * 0.95
        x0 = int(w * (0.20 + (branch % 3) * 0.22))
        for y in range(h):
            t = y / max(1, h - 1)
            cx = int(x0 + math.sin(t * 7.0 + phase) * 16.0)
            thick = 3 if branch < 2 else 2
            for dx in range(-thick, thick + 1):
                xx = cx + dx
                if 0 <= xx < w:
                    alpha = 0.52 if abs(dx) <= 1 else 0.24
                    img.setXelA(xx, y, 0.20, 0.40 + 0.12 * math.sin(t * 9.0 + phase), 0.18, alpha)
            if y % 34 == 0:
                for leaf in range(-6, 7):
                    xx = cx + leaf
                    yy = min(h - 1, y + abs(leaf) * 2)
                    if 0 <= xx < w:
                        alpha = 0.34 if abs(leaf) < 4 else 0.18
                        img.setXelA(xx, yy, 0.22, 0.46, 0.20, alpha)
    tex = Texture("level5_vine_tex")
    tex.load(img)
    return _finish_custom_tex(game, tex, clamp_mode=True)


def _theme(game) -> Dict[str, Texture]:
    state = game.level_runtime_state.setdefault("level5_theme", {})
    if not state:
        state["tile_tex"] = _make_tile_texture(game)
        state["ceiling_tex"] = _make_ceiling_texture(game)
        state["muck_tex"] = _make_muck_texture(game)
        state["door_tex"] = _make_door_texture(game)
        state["vine_tex"] = _make_vine_texture(game)
    return state


# ------------------------------------------------------------
# external level hooks
# ------------------------------------------------------------
def get_level_settings(_game) -> Dict[str, object]:
    return {
        "display_name": "Level 5 — Flooded Tiled Halls",
        "style_name": "Flooded Tiled Halls",
        "move_speed_mult": 0.90,
        "static_water_default": False,
        "weapon_sink": -0.22,
        "weapon_color_scale": [0.82, 0.98, 0.90, 1.0],
        "weapon_indicator_tint": [0.72, 0.96, 0.84, 1.0],
        "weapon_pulse_strength": 0.040,
        "bg_color": [0.060, 0.074, 0.070, 1.0],
        "fog_color": [0.185, 0.205, 0.188, 1.0],
        "ambient_light": [0.235, 0.225, 0.200, 1.0],
        "sun_light": [0.185, 0.178, 0.156, 1.0],
        "fill_light": [0.070, 0.090, 0.082, 1.0],
        "lift_light": [0.095, 0.112, 0.104, 1.0],
        "dark_bg_color": [0.036, 0.046, 0.042, 1.0],
        "dark_fog_color": [0.112, 0.126, 0.114, 1.0],
        "dark_ambient_light": [0.150, 0.144, 0.132, 1.0],
        "dark_sun_light": [0.110, 0.108, 0.098, 1.0],
        "dark_fill_light": [0.042, 0.050, 0.048, 1.0],
        "dark_lift_light": [0.055, 0.062, 0.060, 1.0],
        "fog_start": 1.8,
        "fog_end": 18.0,
        "dark_fog_start": 1.2,
        "dark_fog_end": 10.5,
    }


def on_level_load(game) -> None:
    _theme(game)
    game.return_to_halls_unlocked = True
    game.level_runtime_state["level5"] = {
        "water_z": WATER_Z,
        "floor_z": FLOOR_Z,
        "theme": "flooded_tiled_halls",
    }
    game.player_pos = Vec3(MODULE_SIZE * 0.5, CELL * 1.9, 0.0)
    game.yaw = 0.0
    game.pitch = -0.05


def build_module_data(game, mx: int, my: int) -> Dict[str, object]:
    grid = [[SOLID for _ in range(MODULE_CELLS)] for __ in range(MODULE_CELLS)]

    for y in range(MODULE_CELLS):
        c = _corridor_center(mx, my, float(y))
        width = CORRIDOR_HALF_W + 0.18 * math.sin((y / max(1, MODULE_CELLS - 1)) * math.pi)
        for x in range(MODULE_CELLS):
            if abs((x + 0.5) - c) <= width:
                grid[y][x] = WATER

    side, y0, length, depth = _alcove_info(mx, my)
    for yy in range(y0, min(MODULE_CELLS - 1, y0 + length)):
        run = _tile_run(grid, WATER, yy)
        if not run:
            continue
        start, end = run[0]
        if side < 0:
            for x in range(max(0, start - depth), start):
                grid[yy][x] = WATER
        else:
            for x in range(end, min(MODULE_CELLS, end + depth)):
                grid[yy][x] = WATER

    # soften a few rows for a more pooled, flooded look
    rnd = Random(_seed(game, mx, my, 0x51A551D5))
    for _ in range(2):
        yy = 2 + rnd.randrange(MODULE_CELLS - 4)
        run = _tile_run(grid, WATER, yy)
        if not run:
            continue
        start, end = run[0]
        if start > 1 and rnd.random() < 0.65:
            grid[yy][start - 1] = WATER
        if end < MODULE_CELLS - 1 and rnd.random() < 0.65:
            grid[yy][end] = WATER

    return {"grid": grid, "style_id": 0}


# ------------------------------------------------------------
# geometry builders
# ------------------------------------------------------------
def _build_water_planes(game, root, water_root, grid: List[List[int]], theme: Dict[str, Texture]) -> None:
    for y in range(MODULE_CELLS):
        for start, end in _tile_run(grid, WATER, y):
            width = (end - start) * CELL
            cx = start * CELL + width * 0.5
            cy = y * CELL + CELL * 0.5

            floor = game._add_plane(
                root,
                Vec3(cx, cy, FLOOR_Z),
                width,
                CELL,
                (0, -90, 0),
                theme["muck_tex"],
                max(1.0, width * 0.30),
                1.0,
            )
            floor.setColorScale(0.30, 0.40, 0.31, 1.0)

            muck = game._add_plane(
                root,
                Vec3(cx, cy, FLOOR_Z + 0.018),
                width,
                CELL,
                (0, -90, 0),
                game.deck_gloss_tex,
                max(1.0, width * 0.22),
                1.0,
                True,
            )
            muck.setColorScale(0.18, 0.26, 0.18, 0.16)

            surf = game._add_plane(
                water_root,
                Vec3(cx, cy, WATER_Z),
                width,
                CELL,
                (0, -90, 0),
                game.water_tex,
                max(1.0, width * 0.36),
                1.0,
                True,
            )
            surf.setTexture(game.water_stage, game.water_tex, 1)
            surf.setTexScale(game.water_stage, max(1.0, width * 0.36), 1.0)
            surf.setTransparency(TransparencyAttrib.MAlpha)
            surf.setColorScale(0.62, 0.84, 0.66, 0.84)
            game.water_surface_cards.append(surf)
            game.water_surfaces.append(surf)

            detail = game._add_plane(
                water_root,
                Vec3(cx, cy, WATER_DETAIL_Z),
                width,
                CELL,
                (0, -90, 0),
                game.water_detail_tex,
                max(1.0, width * 0.48),
                1.25,
                True,
            )
            detail.setTexture(game.water_detail_stage, game.water_detail_tex, 1)
            detail.setTexScale(game.water_detail_stage, max(1.0, width * 0.48), 1.25)
            detail.setColorScale(0.86, 0.96, 0.88, 0.18)
            game.water_detail_overlays.append((detail, (cx + cy) * 0.031, (cx - cy) * 0.021))

            refl = game._add_plane(
                water_root,
                Vec3(cx, cy, WATER_REFLECT_Z),
                width,
                CELL,
                (0, -90, 0),
                game.reflection_tex,
                max(1.0, width * 0.22),
                1.0,
                True,
            )
            refl.setColorScale(0.92, 0.94, 0.86, 0.05)
            game.water_reflection_overlays.append((refl, (cx + cy) * 0.026, (cx - cy) * 0.016))


def _build_ceiling(game, root, theme: Dict[str, Texture]) -> None:
    center = Vec3(MODULE_SIZE * 0.5, MODULE_SIZE * 0.5, CEILING_Z)
    ceil = game._add_plane(root, center, MODULE_SIZE, MODULE_SIZE, (0, -90, 0), theme["ceiling_tex"], 4.5, 4.5)
    ceil.setColorScale(0.92, 0.90, 0.84, 1.0)

    # warm light troughs
    for idx, y in enumerate((CELL * 2.2, CELL * 6.1, CELL * 9.6)):
        housing = game._add_box(root, Vec3(MODULE_SIZE * 0.5, y, CEILING_Z - 0.08), Vec3(CELL * 1.9, 0.22, 0.12), theme["ceiling_tex"])
        housing.setColorScale(0.62, 0.58, 0.52, 1.0)
        strip = game._add_plane(root, Vec3(MODULE_SIZE * 0.5, y, CEILING_Z - 0.022), CELL * 1.55, 0.12, (0, -90, 0), game.light_tex, 1.0, 1.0, True)
        strip.setColorScale(1.0, 0.98, 0.92, 0.28)
        game._add_point_light(
            root,
            Vec3(MODULE_SIZE * 0.5, y, CEILING_Z - 0.18),
            Vec4(0.24, 0.21, 0.16, 1.0),
            Vec3(1.0, 0.0, 0.040),
            phase=idx * 0.7,
            pulse=0.010,
        )


def _build_curved_walls(game, root, mx: int, my: int, grid: List[List[int]], theme: Dict[str, Texture]) -> None:
    seg_h = WALL_H
    scum_tex = game.water_detail_tex
    for y in range(MODULE_CELLS):
        yc = y + 0.5
        center = _corridor_center(mx, my, yc)
        deriv = _corridor_derivative(mx, my, yc)
        ang = math.degrees(math.atan2(deriv, 1.0))
        left_x = (center - CORRIDOR_HALF_W) * CELL
        right_x = (center + CORRIDOR_HALF_W) * CELL
        py = y * CELL + CELL * 0.5
        seg_len = CELL * 2.45

        left_fill_w = max(0.85, left_x + 0.90)
        left_fill = game._add_box(root, Vec3(left_x - left_fill_w * 0.5 + 0.02, py, seg_h * 0.5), Vec3(left_fill_w, seg_len + 0.10, seg_h), theme["tile_tex"])
        left_fill.setColorScale(1.02, 1.00, 0.96, 1.0)
        right_fill_w = max(0.85, (MODULE_SIZE - right_x) + 0.90)
        right_fill = game._add_box(root, Vec3(right_x + right_fill_w * 0.5 - 0.02, py, seg_h * 0.5), Vec3(right_fill_w, seg_len + 0.10, seg_h), theme["tile_tex"])
        right_fill.setColorScale(1.01, 0.99, 0.95, 1.0)

        left_scum = game._add_plane(root, Vec3(left_x + 0.020, py, 0.78), seg_len, 1.2, (-90 + ang, 0, 0), scum_tex, 1.4, 0.9, True)
        right_scum = game._add_plane(root, Vec3(right_x - 0.020, py, 0.78), seg_len, 1.2, (90 + ang, 0, 0), scum_tex, 1.4, 0.9, True)
        left_scum.setColorScale(0.36, 0.58, 0.36, 0.13)
        right_scum.setColorScale(0.36, 0.58, 0.36, 0.13)

    # dark end caps where the corridor leaves frame, keeps the void hidden in fog
    south_c = _corridor_center(mx, my, 0.4) * CELL
    north_c = _corridor_center(mx, my, MODULE_CELLS - 0.4) * CELL
    south_cap = game._add_plane(root, Vec3(south_c, -0.03, 1.75), CELL * 4.4, 3.5, (0, 0, 0), theme["tile_tex"], 1.6, 1.9)
    north_cap = game._add_plane(root, Vec3(north_c, MODULE_SIZE + 0.03, 1.75), CELL * 4.4, 3.5, (180, 0, 0), theme["tile_tex"], 1.6, 1.9)
    south_cap.setColorScale(0.78, 0.76, 0.72, 1.0)
    north_cap.setColorScale(0.76, 0.74, 0.70, 1.0)


def _build_alcove_door(game, root, mx: int, my: int, grid: List[List[int]], theme: Dict[str, Texture]) -> None:
    side, y0, length, depth = _alcove_info(mx, my)
    mid_y = (y0 + length * 0.5) * CELL
    center = _corridor_center(mx, my, y0 + length * 0.5)
    if side < 0:
        x = (center - CORRIDOR_HALF_W - depth + 0.28) * CELL
        facing = 90
        frame_x = x + 0.08
    else:
        x = (center + CORRIDOR_HALF_W + depth - 0.28) * CELL
        facing = -90
        frame_x = x - 0.08

    recess = game._add_box(root, Vec3(frame_x, mid_y, 1.62), Vec3(0.16, CELL * 1.35, 3.35), theme["tile_tex"])
    recess.setColorScale(0.12, 0.12, 0.11, 1.0)

    frame = game._add_box(root, Vec3(x, mid_y, 1.68), Vec3(0.10, CELL * 1.10, 3.18), theme["tile_tex"])
    frame.setColorScale(0.36, 0.35, 0.34, 1.0)

    door = game._add_plane(root, Vec3(x, mid_y, 1.58), CELL * 0.86, 3.00, (facing, 0, 0), theme["door_tex"], 1.0, 1.0)
    door.setColorScale(0.62, 0.60, 0.58, 1.0)

    shadow = game._add_plane(root, Vec3(x + (-0.03 if side < 0 else 0.03), mid_y, 1.55), CELL * 0.92, 3.08, (facing, 0, 0), game.beam_tex, 1.0, 1.0, True)
    shadow.setColorScale(0.0, 0.0, 0.0, 0.28)


def _build_overgrowth(game, root, mx: int, my: int, theme: Dict[str, Texture]) -> None:
    rnd = Random(_seed(game, mx, my, 0x0E6E6E10))

    # subtle wall vines, heavier near the decorative door wall
    side, y0, length, depth = _alcove_info(mx, my)
    door_y = (y0 + length * 0.5) * CELL
    for i in range(4):
        y = CELL * (1.6 + i * 2.0) + rnd.random() * 0.55
        c = _corridor_center(mx, my, y / CELL)
        deriv = _corridor_derivative(mx, my, y / CELL)
        ang = math.degrees(math.atan2(deriv, 1.0))
        left_x = (c - CORRIDOR_HALF_W) * CELL + 0.02
        right_x = (c + CORRIDOR_HALF_W) * CELL - 0.02
        weight = 1.0 if abs(y - door_y) < CELL * 1.5 else 0.0
        if rnd.random() < 0.75 or weight > 0.5:
            vine = game._add_plane(root, Vec3(right_x, y, 1.95), CELL * 0.95, 2.40 + weight * 0.8, (90 + ang, 0, 0), theme["vine_tex"], 1.0, 1.0, True)
            vine.setColorScale(0.50, 0.72, 0.46, 0.40 if weight > 0.5 else 0.30)
        if rnd.random() < 0.35:
            vine = game._add_plane(root, Vec3(left_x, y, 2.10), CELL * 0.76, 1.95, (-90 + ang, 0, 0), theme["vine_tex"], 1.0, 1.0, True)
            vine.setColorScale(0.42, 0.62, 0.40, 0.22)

    # a soft bright patch on one wall, like bounced daylight through haze
    patch_y = CELL * 3.9
    patch_c = _corridor_center(mx, my, patch_y / CELL)
    patch_ang = math.degrees(math.atan2(_corridor_derivative(mx, my, patch_y / CELL), 1.0))
    patch_x = (patch_c - CORRIDOR_HALF_W) * CELL + 0.03
    patch = game._add_plane(root, Vec3(patch_x, patch_y, 1.95), CELL * 1.35, 2.65, (-90 + patch_ang, 0, 0), game.light_tex, 1.0, 1.0, True)
    patch.setColorScale(1.0, 1.0, 0.98, 0.13)

    # floating leaves and wall-hugging debris
    for i in range(16):
        y = CELL * (1.0 + rnd.random() * (MODULE_CELLS - 2.0))
        c = _corridor_center(mx, my, y / CELL)
        x = c * CELL + (rnd.random() - 0.5) * CELL * 2.5
        leaf = game._add_plane(root, Vec3(x, y, WATER_Z + 0.022), CELL * 0.35, CELL * 0.16, (0, -90, rnd.random() * 360.0), game.coping_tex, 1.0, 1.0, True)
        leaf.setColorScale(0.26, 0.34 + rnd.random() * 0.10, 0.18, 0.18)


def _build_lights(game, root, mx: int, my: int) -> None:
    positions = (
        (MODULE_SIZE * 0.50, CELL * 2.2),
        (MODULE_SIZE * 0.48, CELL * 6.1),
        (MODULE_SIZE * 0.52, CELL * 9.5),
    )
    for idx, (x, y) in enumerate(positions):
        fixture = game._add_plane(root, Vec3(x, y, CEILING_Z - 0.03), CELL * 1.05, 0.14, (0, -90, 0), game.light_tex, 1.0, 1.0, True)
        fixture.setColorScale(1.0, 0.98, 0.92, 0.25)
        game._add_point_light(
            root,
            Vec3(x, y, CEILING_Z - 0.20),
            Vec4(0.22, 0.19, 0.15, 1.0),
            Vec3(1.0, 0.0, 0.038),
            phase=(mx * 1.3 + my * 1.7 + idx * 0.9),
            pulse=0.008,
        )


def build_module(game, root, water_root, mx: int, my: int, data) -> None:
    theme = _theme(game)
    grid = data.grid
    _build_water_planes(game, root, water_root, grid, theme)
    _build_ceiling(game, root, theme)
    _build_curved_walls(game, root, mx, my, grid, theme)
    _build_alcove_door(game, root, mx, my, grid, theme)
    _build_overgrowth(game, root, mx, my, theme)
    _build_lights(game, root, mx, my)
