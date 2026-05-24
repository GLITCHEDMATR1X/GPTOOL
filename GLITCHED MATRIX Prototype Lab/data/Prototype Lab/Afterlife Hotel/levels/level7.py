from __future__ import annotations

import math
import shutil
import sys
from pathlib import Path
from random import Random
from typing import Dict, List, Optional, Sequence, Set, Tuple

_THIS_FILE = Path(__file__).resolve()
for _candidate in (_THIS_FILE.parent, _THIS_FILE.parent.parent):
    if (_candidate / "main.py").exists():
        if str(_candidate) not in sys.path:
            sys.path.insert(0, str(_candidate))
        break

from panda3d.core import PNMImage, Texture, TransparencyAttrib, Vec3, Vec4

from main import (
    CELL,
    COPING_H,
    DECK,
    DECK_Z,
    MODULE_CELLS,
    MODULE_SIZE,
    ModuleData,
    PoolroomsArtGame,
    SOLID,
    WALL_H,
    WATER,
    WATER_FLOOR_Z,
    WATER_SURFACE_Z,
    install_crash_logger,
)

LEVEL_NAME = "Caves"
STYLE_NAME = "Liminal Grotto Maze"


# -----------------------------------------------------------------------------
# Utilities
# -----------------------------------------------------------------------------
def _clamp(v: float, lo: float, hi: float) -> float:
    return lo if v < lo else hi if v > hi else v


def _hash_u32(*vals: int) -> int:
    h = 2166136261
    for v in vals:
        h = (h ^ (int(v) & 0xFFFFFFFF)) * 16777619
        h &= 0xFFFFFFFF
    return h


def _cell_center(x: int, y: int, z: float = 0.0) -> Vec3:
    return Vec3(x * CELL + CELL * 0.5, y * CELL + CELL * 0.5, z)


def _flood_walkable(grid: List[List[int]], starts: Sequence[Tuple[int, int]]) -> Set[Tuple[int, int]]:
    q = [(x, y) for x, y in starts if 0 <= x < MODULE_CELLS and 0 <= y < MODULE_CELLS and grid[y][x] != SOLID]
    seen = set(q)
    idx = 0
    while idx < len(q):
        x, y = q[idx]
        idx += 1
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if not (0 <= nx < MODULE_CELLS and 0 <= ny < MODULE_CELLS):
                continue
            if grid[ny][nx] == SOLID or (nx, ny) in seen:
                continue
            seen.add((nx, ny))
            q.append((nx, ny))
    return seen


def _open_neighbors(grid: List[List[int]], x: int, y: int) -> Tuple[bool, bool, bool, bool]:
    east = x + 1 < MODULE_CELLS and grid[y][x + 1] != SOLID
    west = x - 1 >= 0 and grid[y][x - 1] != SOLID
    north = y + 1 < MODULE_CELLS and grid[y + 1][x] != SOLID
    south = y - 1 >= 0 and grid[y - 1][x] != SOLID
    return east, west, north, south


def _degree(grid: List[List[int]], x: int, y: int) -> int:
    east, west, north, south = _open_neighbors(grid, x, y)
    return int(east) + int(west) + int(north) + int(south)


# -----------------------------------------------------------------------------
# Procedural textures
# -----------------------------------------------------------------------------
def _finish_tex(tex: Texture, clamp_mode: bool = False) -> Texture:
    tex.setMagfilter(Texture.FTLinear)
    tex.setMinfilter(Texture.FTLinearMipmapLinear)
    if clamp_mode:
        tex.setWrapU(Texture.WMClamp)
        tex.setWrapV(Texture.WMClamp)
    return tex


def _make_cave_wall_texture() -> Texture:
    img = PNMImage(512, 512, 4)
    for y in range(512):
        fy = y / 511.0
        drip_band = math.sin(fy * math.tau * 1.3 + 0.8) * 0.025
        for x in range(512):
            fx = x / 511.0
            ridge = math.sin(x * 0.032 + math.sin(y * 0.012) * 2.6) * 0.055
            calcite = math.cos(x * 0.013 - y * 0.026) * 0.030
            pock = math.sin((x + y) * 0.024) * math.cos((x - y) * 0.019) * 0.045
            grain = (((x * 17 + y * 29) % 97) / 97.0 - 0.5) * 0.040
            damp = math.exp(-(((fx - 0.72) / 0.16) ** 2 + ((fy - 0.78) / 0.14) ** 2)) * 0.080
            vertical = math.sin(x * 0.20 + math.sin(y * 0.012) * 1.4)
            curtain = 0.0
            if vertical > 0.90:
                curtain = (vertical - 0.90) * 0.70 + abs(math.sin(y * 0.11)) * 0.09
            base = 0.33 + ridge + calcite + pock + grain + drip_band + curtain - damp
            r = _clamp(base * 1.42 + 0.06, 0.0, 1.0)
            g = _clamp(base * 0.86 + 0.02, 0.0, 1.0)
            b = _clamp(base * 0.50 + 0.01, 0.0, 1.0)
            if curtain > 0.0:
                r = _clamp(r + curtain * 0.12, 0.0, 1.0)
                g = _clamp(g + curtain * 0.06, 0.0, 1.0)
            img.setXelA(x, y, r, g, b, 1.0)
    tex = Texture("cave_wall_tex")
    tex.load(img)
    return _finish_tex(tex)



def _make_cave_floor_texture() -> Texture:
    img = PNMImage(512, 512, 4)
    for y in range(512):
        fy = y / 511.0
        for x in range(512):
            fx = x / 511.0
            ripple = math.sin(x * 0.041) * 0.030 + math.cos(y * 0.035) * 0.024
            pebble = math.sin((x + y) * 0.082) * math.cos((x - y) * 0.073) * 0.020
            grit = (((x * 11 + y * 7) % 53) / 53.0 - 0.5) * 0.028
            wet = math.exp(-(((fx - 0.48) / 0.22) ** 2 + ((fy - 0.62) / 0.14) ** 2)) * 0.090
            mineral = math.exp(-(((fx - 0.16) / 0.08) ** 2 + ((fy - 0.32) / 0.10) ** 2)) * 0.040
            base = 0.18 + ripple + pebble + grit - wet + mineral
            r = _clamp(base * 1.28 + 0.03, 0.0, 1.0)
            g = _clamp(base * 0.92 + 0.04, 0.0, 1.0)
            b = _clamp(base * 0.72 + wet * 0.25 + 0.03, 0.0, 1.0)
            img.setXelA(x, y, r, g, b, 1.0)
    tex = Texture("cave_floor_tex")
    tex.load(img)
    return _finish_tex(tex)



def _make_cave_ceiling_texture() -> Texture:
    img = PNMImage(512, 512, 4)
    for y in range(512):
        fy = y / 511.0
        for x in range(512):
            fx = x / 511.0
            cavity = math.sin(x * 0.026 + math.cos(y * 0.018) * 1.8) * 0.040
            jag = math.sin((x + y) * 0.047) * 0.030 + math.cos((x - y) * 0.039) * 0.030
            speck = (((x * 23 + y * 13) % 71) / 71.0 - 0.5) * 0.024
            lime = math.exp(-(((fx - 0.62) / 0.20) ** 2 + ((fy - 0.28) / 0.18) ** 2)) * 0.045
            base = 0.16 + cavity + jag + speck + lime
            r = _clamp(base * 1.22 + 0.03, 0.0, 1.0)
            g = _clamp(base * 0.82 + 0.02, 0.0, 1.0)
            b = _clamp(base * 0.56 + 0.02, 0.0, 1.0)
            img.setXelA(x, y, r, g, b, 1.0)
    tex = Texture("cave_ceiling_tex")
    tex.load(img)
    return _finish_tex(tex)



def _make_water_texture() -> Texture:
    img = PNMImage(512, 512, 4)
    for y in range(512):
        fy = y / 511.0
        for x in range(512):
            fx = x / 511.0
            wave_a = math.sin((fx * 14.0 + fy * 4.0) * math.pi) * 0.08
            wave_b = math.cos((fx * 7.0 - fy * 11.0) * math.pi) * 0.06
            shimmer = math.sin((x + y) * 0.090) * math.cos((x - y) * 0.055) * 0.07
            deep = math.exp(-(((fx - 0.48) / 0.28) ** 2 + ((fy - 0.52) / 0.22) ** 2)) * 0.08
            glow = math.exp(-(((fx - 0.5) / 0.18) ** 2 + ((fy - 0.5) / 0.18) ** 2)) * 0.10
            base = 0.40 + wave_a + wave_b + shimmer + glow - deep
            r = _clamp(base * 0.34, 0.0, 1.0)
            g = _clamp(base * 0.90 + 0.18, 0.0, 1.0)
            b = _clamp(base * 1.18 + 0.28, 0.0, 1.0)
            a = _clamp(0.50 + glow * 0.60 + shimmer * 0.12, 0.0, 1.0)
            img.setXelA(x, y, r, g, b, a)
    tex = Texture("cave_water_tex")
    tex.load(img)
    return _finish_tex(tex)



def _make_water_detail_texture() -> Texture:
    img = PNMImage(256, 256, 4)
    for y in range(256):
        fy = y / 255.0
        for x in range(256):
            fx = x / 255.0
            caustic = abs(math.sin(fx * 18.0 + fy * 10.0) * math.cos(fx * 6.0 - fy * 17.0))
            veins = abs(math.sin((fx + fy) * 29.0))
            alpha = _clamp(max(0.0, caustic - 0.62) * 1.8 + max(0.0, veins - 0.94) * 0.4, 0.0, 1.0)
            img.setXelA(x, y, 0.84, 1.0, 1.0, alpha)
    tex = Texture("cave_water_detail_tex")
    tex.load(img)
    return _finish_tex(tex, clamp_mode=True)



def _make_glow_texture() -> Texture:
    img = PNMImage(256, 256, 4)
    for y in range(256):
        fy = y / 255.0
        for x in range(256):
            fx = x / 255.0
            dx = fx - 0.5
            dy = fy - 0.5
            radial = math.exp(-((dx / 0.34) ** 2 + (dy / 0.20) ** 2))
            vertical = math.exp(-((dx / 0.12) ** 2)) * math.exp(-((fy - 0.24) / 0.52) ** 2)
            alpha = _clamp(radial * 0.65 + vertical * 0.55, 0.0, 1.0)
            img.setXelA(x, y, 1.0, 1.0, 1.0, alpha)
    tex = Texture("cave_glow_tex")
    tex.load(img)
    return _finish_tex(tex, clamp_mode=True)



def _ensure_assets(game: PoolroomsArtGame) -> Dict[str, Texture]:
    cached = getattr(game, "_level7_assets", None)
    if cached is not None:
        return cached
    assets = {
        "wall": _make_cave_wall_texture(),
        "floor": _make_cave_floor_texture(),
        "ceiling": _make_cave_ceiling_texture(),
        "water": _make_water_texture(),
        "water_detail": _make_water_detail_texture(),
        "glow": _make_glow_texture(),
    }
    game._level7_assets = assets
    return assets


# -----------------------------------------------------------------------------
# Level settings / lifecycle
# -----------------------------------------------------------------------------
def get_level_settings(_game: PoolroomsArtGame) -> Dict[str, object]:
    return {
        "display_name": LEVEL_NAME,
        "style_name": STYLE_NAME,
        "move_speed_mult": 1.04,
        "static_water_default": False,
        "fog_start": 2.8,
        "fog_end": 24.5,
        "dark_fog_start": 0.70,
        "dark_fog_end": 9.0,
        "bg_color": Vec4(0.050, 0.040, 0.034, 1.0),
        "fog_color": Vec4(0.160, 0.130, 0.112, 1.0),
        "ambient_light": Vec4(0.128, 0.102, 0.086, 1.0),
        "sun_light": Vec4(0.036, 0.028, 0.022, 1.0),
        "fill_light": Vec4(0.022, 0.021, 0.026, 1.0),
        "lift_light": Vec4(0.032, 0.028, 0.024, 1.0),
        "dark_bg_color": Vec4(0.014, 0.012, 0.014, 1.0),
        "dark_fog_color": Vec4(0.056, 0.050, 0.056, 1.0),
        "dark_ambient_light": Vec4(0.030, 0.024, 0.024, 1.0),
        "dark_sun_light": Vec4(0.010, 0.008, 0.010, 1.0),
        "dark_fill_light": Vec4(0.008, 0.008, 0.010, 1.0),
        "dark_lift_light": Vec4(0.012, 0.011, 0.012, 1.0),
        "weapon_color_scale": Vec4(0.90, 0.88, 0.86, 1.0),
        "weapon_indicator_tint": Vec4(0.52, 0.96, 1.0, 1.0),
        "weapon_pulse_strength": 0.055,
        "weapon_sink": -0.014,
    }



def on_level_load(game: PoolroomsArtGame) -> None:
    _ensure_assets(game)
    game.return_to_halls_unlocked = False
    game.player_pos = Vec3(MODULE_SIZE * 0.5, MODULE_SIZE * 0.5, 0.0)
    game.yaw = 0.0
    game.pitch = 0.0
    game.level_runtime_state["level7"] = {"loaded": True}


# -----------------------------------------------------------------------------
# Layout generation
# -----------------------------------------------------------------------------
def build_module_data(game: PoolroomsArtGame, mx: int, my: int) -> ModuleData:
    seed = _hash_u32(mx, my, 0xCA7E7)
    rnd = Random(seed)
    grid = [[SOLID for _ in range(MODULE_CELLS)] for __ in range(MODULE_CELLS)]
    protected: Set[Tuple[int, int]] = set()

    def carve(x: int, y: int, kind: int = DECK, protect: bool = False) -> None:
        if 0 <= x < MODULE_CELLS and 0 <= y < MODULE_CELLS:
            grid[y][x] = kind
            if protect:
                protected.add((x, y))

    def carve_blob(cx: int, cy: int, rx: int, ry: int, kind: int = DECK, protect: bool = False, rough: float = 0.92) -> None:
        for y in range(cy - ry - 1, cy + ry + 2):
            for x in range(cx - rx - 1, cx + rx + 2):
                if not (0 <= x < MODULE_CELLS and 0 <= y < MODULE_CELLS):
                    continue
                dx = (x - cx) / max(1.0, float(rx))
                dy = (y - cy) / max(1.0, float(ry))
                wobble = math.sin((x + seed) * 0.7 + y * 0.9) * 0.16
                if dx * dx + dy * dy <= rough + wobble:
                    carve(x, y, kind, protect)

    def carve_corridor(a: Tuple[int, int], b: Tuple[int, int], protect: bool = False) -> None:
        ax, ay = a
        bx, by = b
        order_first_x = ((_hash_u32(ax, ay, bx, by, seed) >> 3) & 1) == 0

        def walk_x(x0: int, x1: int, y: int) -> int:
            step = 1 if x1 >= x0 else -1
            x = x0
            carve(x, y, DECK, protect)
            while x != x1:
                x += step
                carve(x, y, DECK, protect)
                if ((x + y + seed) % 5) == 0 and 1 <= y + step < MODULE_CELLS - 1:
                    carve(x, y + (1 if ((seed + x) & 1) == 0 else -1), DECK, False)
            return x

        def walk_y(y0: int, y1: int, x: int) -> int:
            step = 1 if y1 >= y0 else -1
            y = y0
            carve(x, y, DECK, protect)
            while y != y1:
                y += step
                carve(x, y, DECK, protect)
                if ((x + y + seed) % 6) == 0 and 1 <= x + step < MODULE_CELLS - 1:
                    carve(x + (1 if ((seed + y) & 1) == 0 else -1), y, DECK, False)
            return y

        if order_first_x:
            midx = walk_x(ax, bx, ay)
            walk_y(ay, by, midx)
        else:
            midy = walk_y(ay, by, ax)
            walk_x(ax, bx, midy)

    # Build a tighter 5x5 logical maze on odd coordinates so the space stays maze-like.
    logical_w = 5
    logical_h = 5

    def logical_to_grid(lx: int, ly: int) -> Tuple[int, int]:
        return 1 + lx * 2, 1 + ly * 2

    visited: Set[Tuple[int, int]] = set()
    stack: List[Tuple[int, int]] = [(2, 2)]
    while stack:
        lx, ly = stack[-1]
        if (lx, ly) not in visited:
            visited.add((lx, ly))
            gx, gy = logical_to_grid(lx, ly)
            carve(gx, gy, DECK, lx == 2 and ly == 2)

        neighbors: List[Tuple[int, int, int, int]] = []
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = lx + dx, ly + dy
            if 0 <= nx < logical_w and 0 <= ny < logical_h and (nx, ny) not in visited:
                neighbors.append((nx, ny, dx, dy))
        if not neighbors:
            stack.pop()
            continue
        nx, ny, dx, dy = neighbors[rnd.randrange(len(neighbors))]
        gx, gy = logical_to_grid(lx, ly)
        ngx, ngy = logical_to_grid(nx, ny)
        carve(gx + dx, gy + dy, DECK)
        carve(ngx, ngy, DECK)
        stack.append((nx, ny))

    # Add a few loops so the maze feels less game-board rigid.
    loop_breaks = [(2, 1), (1, 2), (3, 2), (2, 3), (1, 1), (3, 3)]
    rnd.shuffle(loop_breaks)
    for lx, ly in loop_breaks[:3]:
        gx, gy = logical_to_grid(lx, ly)
        direction = ((1, 0), (0, 1), (-1, 0), (0, -1))[(_hash_u32(seed, gx, gy) >> 1) & 3]
        wx, wy = gx + direction[0], gy + direction[1]
        tx, ty = gx + direction[0] * 2, gy + direction[1] * 2
        if 1 <= tx < MODULE_CELLS - 1 and 1 <= ty < MODULE_CELLS - 1 and grid[ty][tx] != SOLID:
            carve(wx, wy, DECK)

    center = (MODULE_CELLS // 2, MODULE_CELLS // 2)
    landmark = (center[0], min(MODULE_CELLS - 3, center[1] + 3))
    carve_blob(center[0], center[1], 1, 1, DECK, True, rough=0.94)
    carve_blob(landmark[0], landmark[1], 2, 1, DECK, False, rough=0.90)
    carve_corridor(center, landmark, protect=True)

    # Widen a few logical cells into irregular cave rooms.
    room_logical = [(0, 4), (4, 0), (4, 4), (0, 0), (3, 1), (1, 3)]
    rnd.shuffle(room_logical)
    for lx, ly in room_logical[:3]:
        gx, gy = logical_to_grid(lx, ly)
        carve_blob(gx, gy, 1 + (1 if rnd.random() < 0.35 else 0), 1, DECK, False, rough=0.88)

    portals = game._module_portals(mx, my)
    seeds: List[Tuple[int, int]] = []
    for row in sorted(portals["west"]):
        carve(0, row, DECK, True)
        carve(1, row, DECK, True)
        seeds.append((1, row))
    for row in sorted(portals["east"]):
        carve(MODULE_CELLS - 1, row, DECK, True)
        carve(MODULE_CELLS - 2, row, DECK, True)
        seeds.append((MODULE_CELLS - 2, row))
    for col in sorted(portals["south"]):
        carve(col, 0, DECK, True)
        carve(col, 1, DECK, True)
        seeds.append((col, 1))
    for col in sorted(portals["north"]):
        carve(col, MODULE_CELLS - 1, DECK, True)
        carve(col, MODULE_CELLS - 2, DECK, True)
        seeds.append((col, MODULE_CELLS - 2))

    # Tie every module edge back into the internal maze.
    anchors = [center, landmark, logical_to_grid(0, 2), logical_to_grid(4, 2), logical_to_grid(2, 0), logical_to_grid(2, 4)]
    for seed_pos in seeds:
        best = min(anchors, key=lambda p: abs(p[0] - seed_pos[0]) + abs(p[1] - seed_pos[1]))
        carve_corridor(seed_pos, best, protect=True)

    # Round some hard corners.
    for y in range(1, MODULE_CELLS - 1):
        for x in range(1, MODULE_CELLS - 1):
            if grid[y][x] != SOLID:
                continue
            east, west, north, south = _open_neighbors(grid, x, y)
            corner_count = int(east and north) + int(east and south) + int(west and north) + int(west and south)
            if corner_count and ((_hash_u32(seed, x, y) % 100) < 22):
                carve(x, y, DECK, False)

    reachable = _flood_walkable(grid, seeds if seeds else [center])
    for y in range(MODULE_CELLS):
        for x in range(MODULE_CELLS):
            if grid[y][x] != SOLID and (x, y) not in reachable:
                grid[y][x] = SOLID

    carve_blob(center[0], center[1], 1, 1, DECK, True, rough=0.94)

    # Landmark pool in the north chamber.
    for wx, wy in ((landmark[0], landmark[1]), (landmark[0] - 1, landmark[1]), (landmark[0] + 1, landmark[1])):
        if 1 <= wx < MODULE_CELLS - 1 and 1 <= wy < MODULE_CELLS - 1 and (wx, wy) not in protected and grid[wy][wx] != SOLID:
            grid[wy][wx] = WATER

    # Optional side pools.
    side_pools = [logical_to_grid(0, 4), logical_to_grid(4, 0), logical_to_grid(4, 4), logical_to_grid(0, 0)]
    rnd.shuffle(side_pools)
    for cx, cy in side_pools[:2]:
        if rnd.random() >= 0.45:
            continue
        for wx, wy in ((cx, cy), (cx + 1, cy), (cx, cy + 1)):
            if 1 <= wx < MODULE_CELLS - 1 and 1 <= wy < MODULE_CELLS - 1 and grid[wy][wx] == DECK and (wx, wy) not in protected and _degree(grid, wx, wy) >= 2:
                grid[wy][wx] = WATER

    return ModuleData(grid=grid, style_id=0)


# -----------------------------------------------------------------------------
# Geometry helpers
# -----------------------------------------------------------------------------
def _horizontal_runs(grid: List[List[int]], target: int, y: int) -> List[Tuple[int, int]]:
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



def _add_floor_and_water(game: PoolroomsArtGame, root, water_root, grid: List[List[int]], assets: Dict[str, Texture]) -> None:
    for y in range(MODULE_CELLS):
        for start, end in _horizontal_runs(grid, DECK, y):
            width = (end - start) * CELL
            center = Vec3(start * CELL + width * 0.5, y * CELL + CELL * 0.5, DECK_Z)
            floor = game._add_plane(root, center, width, CELL, (0, -90, 0), assets["floor"], max(1.0, width * 0.42), 1.2)
            floor.setColorScale(0.90, 0.88, 0.86, 1.0)
            game.deck_surfaces.append(floor)

            gloss = game._add_plane(root, center + Vec3(0, 0, 0.010), width, CELL, (0, -90, 0), game.reflection_tex, max(1.0, width * 0.20), 1.0, True)
            gloss.setColorScale(0.75, 0.88, 0.94, 0.0)
            gloss.hide()
            game.deck_gloss_overlays.append((gloss, (center.x + center.y) * 0.019, (center.x - center.y) * 0.011))

        for start, end in _horizontal_runs(grid, WATER, y):
            width = (end - start) * CELL
            center_floor = Vec3(start * CELL + width * 0.5, y * CELL + CELL * 0.5, WATER_FLOOR_Z)
            floor = game._add_plane(root, center_floor, width, CELL, (0, -90, 0), assets["floor"], max(1.0, width * 0.38), 1.0)
            floor.setColorScale(0.16, 0.34, 0.30, 1.0)
            game.water_surfaces.append(floor)

            center_surf = Vec3(center_floor.x, center_floor.y, WATER_SURFACE_Z)
            surf = game._add_plane(water_root, center_surf, width, CELL, (0, -90, 0), assets["water"], max(1.0, width * 0.30), 1.0, True)
            surf.setTexture(game.water_stage, assets["water"], 1)
            surf.setTexScale(game.water_stage, max(1.0, width * 0.30), 1.0)
            surf.setTransparency(TransparencyAttrib.MAlpha)
            surf.setColorScale(0.82, 1.0, 1.0, 0.72)
            game.water_surfaces.append(surf)
            game.water_surface_cards.append(surf)

            detail = game._add_plane(water_root, center_surf + Vec3(0, 0, 0.014), width, CELL, (0, -90, 0), assets["water_detail"], max(1.0, width * 0.44), 1.2, True)
            detail.setTexture(game.water_detail_stage, assets["water_detail"], 1)
            detail.setTexScale(game.water_detail_stage, max(1.0, width * 0.44), 1.2)
            detail.setColorScale(0.86, 1.0, 1.0, 0.0)
            detail.hide()
            game.water_detail_overlays.append((detail, (center_surf.x + center_surf.y) * 0.030, (center_surf.x - center_surf.y) * 0.018))

            overlay = game._add_plane(water_root, center_surf + Vec3(0, 0, 0.020), width, CELL, (0, -90, 0), game.reflection_tex, max(1.0, width * 0.25), 1.0, True)
            overlay.setColorScale(0.72, 0.98, 1.0, 0.0)
            overlay.hide()
            game.water_reflection_overlays.append((overlay, (center_surf.x + center_surf.y) * 0.024, (center_surf.x - center_surf.y) * 0.016))

            glow = game._add_plane(water_root, center_surf + Vec3(0, 0, 0.008), width * 0.86, CELL * 0.82, (0, -90, 0), assets["glow"], 1.0, 1.0, True)
            glow.setColorScale(0.42, 0.96, 1.0, 0.18)
            glow.setDepthWrite(False)
            glow.setBin("transparent", 22)
            game._add_point_light(root, Vec3(center_surf.x, center_surf.y, 0.80), Vec4(0.04, 0.12, 0.14, 1.0), Vec3(1.0, 0.0, 0.07), phase=(center_surf.x + center_surf.y) * 0.05, pulse=0.018)



def _add_ceiling(game: PoolroomsArtGame, root, ceiling_tex: Texture) -> None:
    center = Vec3(MODULE_SIZE * 0.5, MODULE_SIZE * 0.5, WALL_H)
    ceiling = game._add_plane(root, center, MODULE_SIZE, MODULE_SIZE, (0, -90, 0), ceiling_tex, MODULE_CELLS * 0.60, MODULE_CELLS * 0.60)
    ceiling.setColorScale(0.70, 0.66, 0.62, 1.0)



def _add_walls(game: PoolroomsArtGame, parent, mx: int, my: int, grid: List[List[int]], wall_tex: Texture) -> None:
    wall_z = WALL_H * 0.5
    for y in range(MODULE_CELLS):
        for x in range(MODULE_CELLS):
            if grid[y][x] == SOLID:
                continue
            wx = x * CELL
            wy = y * CELL
            gx = mx * MODULE_CELLS + x
            gy = my * MODULE_CELLS + y
            for dx, dy, cx, cy, hpr in (
                (1, 0, wx + CELL, wy + CELL * 0.5, (90, 0, 0)),
                (-1, 0, wx, wy + CELL * 0.5, (-90, 0, 0)),
                (0, 1, wx + CELL * 0.5, wy + CELL, (180, 0, 0)),
                (0, -1, wx + CELL * 0.5, wy, (0, 0, 0)),
            ):
                if game._world_cell_kind(gx + dx, gy + dy) != SOLID:
                    continue
                face = game._add_plane(parent, Vec3(cx, cy, wall_z), CELL, WALL_H, hpr, wall_tex, 1.3, max(1.0, WALL_H * 0.48))
                face.setColorScale(0.96, 0.92, 0.88, 1.0)
                # Give the cave walls some perceived thickness and curvature.
                inward = Vec3(-dx * 0.08, -dy * 0.08, 0.0)
                bulge = game._add_box(parent, Vec3(cx, cy, 0.76) + inward, Vec3(CELL * 0.74 if dy else 0.18, CELL * 0.74 if dx else 0.18, 1.02), wall_tex)
                bulge.setColorScale(0.40, 0.27, 0.17, 1.0)
                shelf = game._add_box(parent, Vec3(cx, cy, 2.80) + inward * 0.6, Vec3(CELL * 0.70 if dy else 0.16, CELL * 0.70 if dx else 0.16, 0.64), wall_tex)
                shelf.setColorScale(0.34, 0.24, 0.16, 1.0)



def _add_stalactite(game: PoolroomsArtGame, parent, center: Vec3, height: float, radius: float, tex: Texture, from_floor: bool) -> None:
    pieces = 3
    for i in range(pieces):
        t = i / float(pieces)
        scale = radius * (1.0 - t * 0.34)
        seg_h = height / pieces * (1.0 - t * 0.08)
        if from_floor:
            z = center.z + seg_h * 0.5 + i * height / pieces * 0.92
        else:
            z = center.z - seg_h * 0.5 - i * height / pieces * 0.92
        box = game._add_box(parent, Vec3(center.x, center.y, z), Vec3(scale * 1.18, scale * 1.18, seg_h), tex)
        shade = 0.30 + (0.06 * i)
        if from_floor:
            box.setColorScale(shade * 1.18, shade * 0.82, shade * 0.54, 1.0)
        else:
            box.setColorScale(shade * 1.05, shade * 0.72, shade * 0.46, 1.0)



def _add_flowstone_drape(game: PoolroomsArtGame, parent, center: Vec3, horizontal: bool, tex: Texture, seed: int) -> None:
    width = CELL * (0.56 + ((seed >> 4) & 7) / 18.0)
    depth = 0.16 + ((seed >> 9) & 7) * 0.02
    height = 1.6 + ((seed >> 12) & 7) * 0.22
    if horizontal:
        box = game._add_box(parent, Vec3(center.x, center.y, WALL_H - height * 0.5), Vec3(width, depth, height), tex)
    else:
        box = game._add_box(parent, Vec3(center.x, center.y, WALL_H - height * 0.5), Vec3(depth, width, height), tex)
    box.setColorScale(0.56, 0.36, 0.21, 1.0)



def _add_formations_and_mist(game: PoolroomsArtGame, parent, grid: List[List[int]], assets: Dict[str, Texture], seed_base: int) -> None:
    glow_tex = assets["glow"]
    wall_tex = assets["wall"]
    chamber_candidates: List[Tuple[int, int]] = []

    for y in range(1, MODULE_CELLS - 1):
        for x in range(1, MODULE_CELLS - 1):
            if grid[y][x] == SOLID:
                continue
            deg = _degree(grid, x, y)
            local_seed = _hash_u32(seed_base, x, y)
            c = _cell_center(x, y)

            if deg <= 2 and (local_seed % 5 == 0):
                # Keep formations close to the walls so the path remains readable.
                edge_bias = 0.36 if ((local_seed >> 7) & 1) == 0 else -0.36
                fx = c.x + (edge_bias if (local_seed & 1) == 0 else 0.0)
                fy = c.y + (edge_bias if (local_seed & 1) == 1 else 0.0)
                _add_stalactite(game, parent, Vec3(fx, fy, WALL_H), 1.3 + (local_seed % 60) / 60.0, 0.42, wall_tex, from_floor=False)
                if (local_seed % 3) == 0:
                    _add_stalactite(game, parent, Vec3(fx * 0 + c.x - (fx - c.x), fy * 0 + c.y - (fy - c.y), DECK_Z), 0.9 + ((local_seed >> 8) % 50) / 90.0, 0.34, wall_tex, from_floor=True)

            if deg >= 3:
                chamber_candidates.append((x, y))
                if (local_seed % 7) == 0:
                    haze = game._add_plane(parent, Vec3(c.x, c.y, 0.34), CELL * 1.8, CELL * 1.2, (0, 0, 0), glow_tex, 1.0, 1.0, True)
                    haze.setColorScale(0.44, 0.46, 0.52, 0.06)
                    haze.setBin("transparent", 15)
                    haze.setDepthWrite(False)

            east, west, north, south = _open_neighbors(grid, x, y)
            if east and not west and not north and not south:
                _add_flowstone_drape(game, parent, Vec3((x + 1) * CELL - 0.18, y * CELL + CELL * 0.5, WALL_H), False, wall_tex, local_seed)
            elif west and not east and not north and not south:
                _add_flowstone_drape(game, parent, Vec3(x * CELL + 0.18, y * CELL + CELL * 0.5, WALL_H), False, wall_tex, local_seed)
            elif north and not south and not east and not west:
                _add_flowstone_drape(game, parent, Vec3(x * CELL + CELL * 0.5, (y + 1) * CELL - 0.18, WALL_H), True, wall_tex, local_seed)
            elif south and not north and not east and not west:
                _add_flowstone_drape(game, parent, Vec3(x * CELL + CELL * 0.5, y * CELL + 0.18, WALL_H), True, wall_tex, local_seed)

    # One or two theatrical shafts of light in broader spaces.
    chamber_candidates.sort(key=lambda item: (0 if grid[item[1]][item[0]] == WATER else 1, _hash_u32(seed_base, item[0], item[1], 0x4455)))
    shafts_added = 0
    for x, y in chamber_candidates:
        if shafts_added >= 2:
            break
        local_seed = _hash_u32(seed_base, x, y, 0x999)
        if (local_seed % 3) != 0:
            continue
        c = _cell_center(x, y)
        width = CELL * (1.3 + (local_seed & 1) * 0.4)
        beam = game._add_plane(parent, Vec3(c.x, c.y, WALL_H * 0.55), width, WALL_H * 0.98, (0, 0, 0), glow_tex, 1.0, 1.0, True)
        beam.setColorScale(0.72, 0.84, 1.0, 0.17)
        beam.setDepthWrite(False)
        beam.setBin("transparent", 24)
        beam2 = game._add_plane(parent, Vec3(c.x, c.y, WALL_H * 0.55), width, WALL_H * 0.98, (90, 0, 0), glow_tex, 1.0, 1.0, True)
        beam2.setColorScale(0.72, 0.84, 1.0, 0.12)
        beam2.setDepthWrite(False)
        beam2.setBin("transparent", 24)

        pool_glow = game._add_plane(parent, Vec3(c.x, c.y, WATER_SURFACE_Z + 0.02 if grid[y][x] == WATER else DECK_Z + 0.02), width * 0.92, width * 0.92, (0, -90, 0), glow_tex, 1.0, 1.0, True)
        pool_glow.setColorScale(0.62, 0.94, 1.0, 0.24 if grid[y][x] == WATER else 0.12)
        pool_glow.setDepthWrite(False)
        pool_glow.setBin("transparent", 23)

        game._add_point_light(parent, Vec3(c.x, c.y, 1.25), Vec4(0.08, 0.15, 0.17, 1.0), Vec3(1.0, 0.0, 0.055), phase=(c.x + c.y) * 0.05, pulse=0.022)
        shafts_added += 1



def build_module(game: PoolroomsArtGame, root, water_root, mx: int, my: int, data: ModuleData) -> None:
    assets = _ensure_assets(game)
    seed_base = _hash_u32(mx, my, 0x71717)

    _add_floor_and_water(game, root, water_root, data.grid, assets)
    _add_ceiling(game, root, assets["ceiling"])
    _add_walls(game, root, mx, my, data.grid, assets["wall"])
    _add_formations_and_mist(game, root, data.grid, assets, seed_base)


# -----------------------------------------------------------------------------
# Optional direct launcher for local testing.
# -----------------------------------------------------------------------------
def _resolve_main_dir() -> Path:
    here = Path(__file__).resolve()
    if (here.parent / "main.py").exists():
        return here.parent
    if (here.parent.parent / "main.py").exists():
        return here.parent.parent
    return here.parent


class _DirectLevel7Preview(PoolroomsArtGame):
    def __init__(self, level_path: Optional[Path] = None) -> None:
        super().__init__()
        desired = (level_path or Path(__file__).resolve()).resolve()
        self._refresh_available_levels()
        target_index = None
        for idx, entry in self.level_entries.items():
            try:
                if Path(entry["path"]).resolve() == desired:
                    target_index = idx
                    break
            except Exception:
                continue
        if target_index is None:
            target_index = self.available_level_indices[0] if self.available_level_indices else 1
        self._load_level(target_index)



def main() -> None:
    install_crash_logger()
    main_dir = _resolve_main_dir()
    levels_dir = main_dir / "levels"
    levels_dir.mkdir(parents=True, exist_ok=True)

    source = Path(__file__).resolve()
    target = levels_dir / source.name
    if source != target:
        shutil.copy2(source, target)
        level_path = target
    else:
        level_path = source

    game = _DirectLevel7Preview(level_path=level_path)
    game.run()


if __name__ == "__main__":
    main()
