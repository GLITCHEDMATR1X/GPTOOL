import argparse
import json
import math
import os
import random
import re
import sys
import time
import traceback
from array import array
from collections import OrderedDict, deque
from dataclasses import dataclass

import pygame

_HOLOVERSE_RUNTIME = None
try:
    _CORE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    if _CORE_ROOT not in sys.path:
        sys.path.insert(0, _CORE_ROOT)
    import holoverse_mode_runtime as _HOLOVERSE_RUNTIME
except Exception:
    _HOLOVERSE_RUNTIME = None


VIRTUAL_W, VIRTUAL_H = 1920, 1080
RAY_W, RAY_H = 960, 540
FOV = math.radians(72.0)
USE_SMOOTHSCALE = True

MAX_STEPS = 360
MAX_DIST = 84.0
MAP_W, MAP_H = 56, 56
TERRAIN_CHUNK_TILES = 16
TERRAIN_CHUNK_PX = 64

BASE_AMBIENT = 0.042
FOG_DENSITY = 0.046

SONAR_SPEED = 25.0
SONAR_SIGMA = 1.2
SONAR_AFTERGLOW = 2.6
SONAR_ATTEN = 0.061
SONAR_COOLDOWN = 0.20
SONAR_WALL_GAIN = 2.3
SONAR_FLOOR_GAIN = 1.75

MOVE_SPEED = 4.25
SPRINT_MUL = 1.55
TURN_SPEED = 2.55
MOUSE_SENS = 0.0028

ENEMY_COUNT = 1
ENEMY_ATTACK_DIST = 0.82
AMMO_MAX = 200
SHOW_FPS = True
SHOT_LIGHT_DURATION = 0.24
ASSET_WEAPON_DIR = os.path.join("assets", "weapons")
ASSET_ENEMY_DIR = os.path.join("assets", "enemies")
ASSET_ITEM_DIR = os.path.join("assets", "items")
ASSET_POWERUP_DIR = os.path.join("assets", "powerups")
ASSET_PORTAL_DIR = os.path.join("assets", "portals")
ASSET_SKY_DIR = os.path.join("assets", "sky")
ASSET_SFX_DIR = os.path.join("assets", "sfx")
ASSET_SFX_WEAPON_DIR = os.path.join(ASSET_SFX_DIR, "weapons")
ASSET_SFX_WEAPON_PICKUP_DIR = os.path.join(ASSET_SFX_WEAPON_DIR, "pickups")
ASSET_SFX_MONSTER_DIR = os.path.join(ASSET_SFX_DIR, "monsters")
ASSET_SFX_POWERUP_DIR = os.path.join(ASSET_SFX_DIR, "powerups")
ASSET_SFX_RADAR_DIR = os.path.join(ASSET_SFX_DIR, "radar")
ASSET_SFX_AMBIENT_DIR = os.path.join(ASSET_SFX_DIR, "ambient")
ASSET_SFX_AMBIENCE_DIR = os.path.join(ASSET_SFX_DIR, "ambience")
ASSET_SFX_STEP_DIR = os.path.join(ASSET_SFX_DIR, "steps")
ASSET_SFX_STEP_WALK_DIR = os.path.join(ASSET_SFX_STEP_DIR, "walk")
ASSET_SFX_STEP_SNEAK_DIR = os.path.join(ASSET_SFX_STEP_DIR, "sneak")
ASSET_SFX_STEP_SPRINT_DIR = os.path.join(ASSET_SFX_STEP_DIR, "sprint")
ASSET_MUZZLE_MAP_DIR = os.path.join("assets", "muzzle_maps")
ASSET_CACHE_DIR = os.path.join("assets", "cache")
ASSET_SURFACE_DIR = os.path.join("assets", "surfaces")
ASSET_SURFACE_WALL_DIR = os.path.join(ASSET_SURFACE_DIR, "walls")
ASSET_SURFACE_FLOOR_DIR = os.path.join(ASSET_SURFACE_DIR, "floors")
ASSET_SURFACE_CEIL_DIR = os.path.join(ASSET_SURFACE_DIR, "ceilings")
REALM_KINDS = ("cavern", "exterior", "catacomb", "wasteland", "abyss")


def ensure_asset_folders():
    for path in (
        "assets",
        ASSET_WEAPON_DIR,
        ASSET_ENEMY_DIR,
        ASSET_ITEM_DIR,
        ASSET_POWERUP_DIR,
        ASSET_PORTAL_DIR,
        ASSET_SKY_DIR,
        ASSET_SFX_DIR,
        ASSET_SFX_WEAPON_DIR,
        ASSET_SFX_WEAPON_PICKUP_DIR,
        ASSET_SFX_MONSTER_DIR,
        ASSET_SFX_POWERUP_DIR,
        ASSET_SFX_RADAR_DIR,
        ASSET_SFX_AMBIENT_DIR,
        ASSET_SFX_AMBIENCE_DIR,
        ASSET_SFX_STEP_DIR,
        ASSET_SFX_STEP_WALK_DIR,
        ASSET_SFX_STEP_SNEAK_DIR,
        ASSET_SFX_STEP_SPRINT_DIR,
        ASSET_MUZZLE_MAP_DIR,
        ASSET_CACHE_DIR,
        ASSET_SURFACE_DIR,
        ASSET_SURFACE_WALL_DIR,
        ASSET_SURFACE_FLOOR_DIR,
        ASSET_SURFACE_CEIL_DIR,
    ):
        os.makedirs(path, exist_ok=True)

    layout_path = os.path.join("assets", "ASSET_LAYOUT.txt")
    if not os.path.exists(layout_path):
        with open(layout_path, "w", encoding="utf-8") as f:
            f.write(
                "Radar Hell asset override folders:\n"
                "- assets/weapons/weapon_<1..9>.png | .wav/.mp3 | .json\n"
                "  and optional impact: weapon_<1..9>_impact.wav/.mp3\n"
                "- assets/enemies/enemy_<0..8>.png\n"
                "- assets/items/weapon_pickup_<0..8>.png\n"
                "- assets/powerups/nightvision.png\n"
                "- assets/portals/portal_to_exterior.png\n"
                "- assets/portals/portal_to_cavern.png\n"
                "- assets/sky/sky.png (replaceable wrapped sky texture)\n"
                "- assets/sfx/weapons/weapon_<1..9>.wav/.mp3\n"
                "  and impact: assets/sfx/weapons/weapon_<1..9>_impact.wav/.mp3\n"
                "- assets/sfx/weapons/pickups/weapon_pickup_<1..9>.wav/.mp3\n"
                "- assets/sfx/monsters/monster_<0..8>.mp3 and monster_<0..8>_death.mp3\n"
                "- assets/sfx/monsters/monster_attack.wav/.mp3 (optional)\n"
                "- assets/sfx/powerups/nightvision.wav/.mp3 (optional)\n"
                "- assets/sfx/radar/radar_ping.mp3 (optional)\n"
                "- assets/sfx/ambient/rain_loop.mp3 and storm_loop.mp3 (optional loops)\n"
                "- assets/sfx/ambience/*.mp3 (optional background loop playlist)\n"
                "- assets/sfx/steps/walk/*.mp3, sneak/*.mp3, sprint/*.mp3 (optional movement sfx)\n"
                "- assets/cache/ (generated runtime cache for faster loading)\n"
                "- assets/surfaces/walls/wall_<0..4>.png (tileable wall variations)\n"
                "- assets/surfaces/floors/floor_<0..4>.png (tileable floor variations)\n"
                "- assets/surfaces/ceilings/ceiling_<0..4>.png (tileable ceiling variations)\n"
                "- assets/muzzle_maps/weapon_<1..9>_muzzle.png (optional red-dot anchor map)\n"
            )


    # Create replaceable monster SFX placeholders (MP3 filenames) for user overrides.
    for kind in range(9):
        for suffix in ("", "_death"):
            path = os.path.join(ASSET_SFX_MONSTER_DIR, f"monster_{kind}{suffix}.mp3")
            if not os.path.exists(path):
                with open(path, "wb") as f:
                    f.write(b"")

    radar_path = os.path.join(ASSET_SFX_RADAR_DIR, "radar_ping.mp3")
    if not os.path.exists(radar_path):
        with open(radar_path, "wb") as f:
            f.write(b"")

    attack_path = os.path.join(ASSET_SFX_MONSTER_DIR, "monster_attack.mp3")
    if not os.path.exists(attack_path):
        with open(attack_path, "wb") as f:
            f.write(b"")

    for ambient_name in ("rain_loop.mp3", "storm_loop.mp3"):
        ambient_path = os.path.join(ASSET_SFX_AMBIENT_DIR, ambient_name)
        if not os.path.exists(ambient_path):
            with open(ambient_path, "wb") as f:
                f.write(b"")

    for folder in (ASSET_SFX_AMBIENCE_DIR, ASSET_SFX_STEP_WALK_DIR, ASSET_SFX_STEP_SNEAK_DIR, ASSET_SFX_STEP_SPRINT_DIR):
        seed_file = os.path.join(folder, "placeholder.mp3")
        if not os.path.exists(seed_file):
            with open(seed_file, "wb") as f:
                f.write(b"")

    cache_keep = os.path.join(ASSET_CACHE_DIR, ".keep")
    if not os.path.exists(cache_keep):
        with open(cache_keep, "w", encoding="utf-8") as f:
            f.write("cache marker\n")
    cache_info = os.path.join(ASSET_CACHE_DIR, "cache_manifest.json")
    if not os.path.exists(cache_info):
        with open(cache_info, "w", encoding="utf-8") as f:
            json.dump({"created": time.time(), "version": 1}, f)

def save_surface_if_missing(path, surf):
    if not os.path.exists(path):
        pygame.image.save(surf, path)


def load_image_or_none(path, alpha=True):
    if not os.path.exists(path):
        return None
    try:
        img = pygame.image.load(path)
        return img.convert_alpha() if alpha else img.convert()
    except Exception:
        return None


def load_sound_candidates(paths, default=None, volume=0.55):
    if not pygame.mixer.get_init():
        return default
    for path in paths:
        if not path or not os.path.exists(path):
            continue
        try:
            snd = pygame.mixer.Sound(path)
            snd.set_volume(clamp(volume, 0.0, 1.0))
            return snd
        except Exception:
            continue
    return default




class LRUCache:
    def __init__(self, max_items=256):
        self.max_items = max(8, int(max_items))
        self._d = OrderedDict()

    def get(self, key):
        if key in self._d:
            v = self._d.pop(key)
            self._d[key] = v
            return v
        return None

    def set(self, key, value):
        if key in self._d:
            self._d.pop(key)
        self._d[key] = value
        while len(self._d) > self.max_items:
            self._d.popitem(last=False)


def build_spatial_buckets(points, cell_size=4.0):
    inv = 1.0 / max(0.001, cell_size)
    out = {}
    for idx, (x, y) in enumerate(points):
        k = (int(x * inv), int(y * inv))
        out.setdefault(k, []).append(idx)
    return out, inv


def query_spatial_indices(buckets, inv_cell, x, y, radius):
    cr = max(1, int(radius * inv_cell) + 1)
    cx = int(x * inv_cell)
    cy = int(y * inv_cell)
    out = []
    for yy in range(cy - cr, cy + cr + 1):
        for xx in range(cx - cr, cx + cr + 1):
            out.extend(buckets.get((xx, yy), ()))
    return out

def clamp(x, a, b):
    return a if x < a else b if x > b else x


def lerp(a, b, t):
    return a + (b - a) * t


def smoothstep(t):
    t = clamp(t, 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def wrap_pi(a):
    while a <= -math.pi:
        a += math.tau
    while a > math.pi:
        a -= math.tau
    return a


def hash2i(x, y, seed=1337):
    n = (x * 374761393 + y * 668265263 + seed * 982451653) & 0xFFFFFFFF
    n = (n ^ (n >> 13)) & 0xFFFFFFFF
    n = (n * 1274126177) & 0xFFFFFFFF
    return ((n ^ (n >> 16)) & 0xFFFFFFFF) / 4294967296.0


def value_noise(x, y, scale=0.12, seed=1337):
    fx = x * scale
    fy = y * scale
    x0 = int(math.floor(fx))
    y0 = int(math.floor(fy))
    tx = fx - x0
    ty = fy - y0
    sx = smoothstep(tx)
    sy = smoothstep(ty)

    v00 = hash2i(x0, y0, seed)
    v10 = hash2i(x0 + 1, y0, seed)
    v01 = hash2i(x0, y0 + 1, seed)
    v11 = hash2i(x0 + 1, y0 + 1, seed)
    ix0 = lerp(v00, v10, sx)
    ix1 = lerp(v01, v11, sx)
    return lerp(ix0, ix1, sy)


def fbm(x, y, seed=1337, octaves=4):
    amp = 0.55
    freq = 1.0
    s = 0.0
    total_amp = 0.0
    for i in range(octaves):
        s += amp * value_noise(x, y, scale=0.09 * freq, seed=seed + i * 19)
        total_amp += amp
        amp *= 0.5
        freq *= 2.0
    return s / max(total_amp, 1e-6)


def report_crash(exc: BaseException):
    report = {
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "python": sys.version,
        "platform": sys.platform,
        "error": repr(exc),
        "traceback": traceback.format_exc(),
    }
    with open("crash_report.log", "a", encoding="utf-8") as f:
        f.write(json.dumps(report, ensure_ascii=False) + "\n")


class Presenter:
    """Maintain a resizable/fullscreen window for the fixed virtual render surface."""

    def __init__(self, win: pygame.Surface):
        self.win = win
        self.fullscreen = False
        self.window_size = win.get_size()

    def resize(self, w: int, h: int):
        self.window_size = (max(640, int(w)), max(360, int(h)))
        if not self.fullscreen:
            self.win = pygame.display.set_mode(self.window_size, pygame.RESIZABLE | pygame.DOUBLEBUF)

    def toggle_fullscreen(self):
        self.fullscreen = not self.fullscreen
        if self.fullscreen:
            self.win = pygame.display.set_mode((0, 0), pygame.FULLSCREEN | pygame.DOUBLEBUF)
        else:
            self.win = pygame.display.set_mode(self.window_size, pygame.RESIZABLE | pygame.DOUBLEBUF)

    def present_cover(self, frame: pygame.Surface):
        ww, wh = self.win.get_size()
        sw, sh = frame.get_size()
        if sw <= 0 or sh <= 0:
            return
        scale = min(ww / sw, wh / sh)
        dw = max(1, int(sw * scale))
        dh = max(1, int(sh * scale))
        out = pygame.transform.smoothscale(frame, (dw, dh)) if (dw, dh) != (sw, sh) else frame
        self.win.fill((0, 0, 0))
        self.win.blit(out, ((ww - dw) // 2, (wh - dh) // 2))
        pygame.display.flip()


def cover_window_to_virtual(win_size, pos, virtual_size=(VIRTUAL_W, VIRTUAL_H)):
    ww, wh = win_size
    sw, sh = virtual_size
    if ww <= 0 or wh <= 0 or sw <= 0 or sh <= 0:
        return None
    scale = min(ww / sw, wh / sh)
    dw = max(1, int(sw * scale))
    dh = max(1, int(sh * scale))
    ox = (ww - dw) // 2
    oy = (wh - dh) // 2
    px, py = pos
    if px < ox or py < oy or px >= ox + dw or py >= oy + dh:
        return None
    return ((px - ox) / scale, (py - oy) / scale)


def draw_host_button(dst, rect, label, font, hovered=False, active=False):
    fill = (26, 8, 8, 228) if not hovered else (52, 12, 12, 236)
    border = (140, 34, 34) if not hovered else (210, 58, 58)
    glow = pygame.Surface((rect.w + 18, rect.h + 18), pygame.SRCALPHA)
    pygame.draw.rect(glow, (120, 20, 20, 70 if hovered else 32), glow.get_rect(), border_radius=20)
    dst.blit(glow, (rect.x - 9, rect.y - 9), special_flags=pygame.BLEND_RGBA_ADD)
    panel = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
    panel.fill(fill)
    pygame.draw.rect(panel, border, panel.get_rect(), 2, border_radius=16)
    if active:
        pygame.draw.rect(panel, (255, 120, 120, 38), panel.get_rect().inflate(-8, -8), border_radius=12)
    txt = font.render(label, True, (236, 210, 210))
    panel.blit(txt, (panel.get_width() // 2 - txt.get_width() // 2, panel.get_height() // 2 - txt.get_height() // 2))
    dst.blit(panel, rect.topleft)


def launch_embedded_mode(mode_name, window_size=(VIRTUAL_W, VIRTUAL_H), fullscreen=False):
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    if mode_name == "launch_hvh2":
        import hvh2
        return hvh2.main(
            host_mode=True,
            return_to_host_on_escape=True,
            return_to_host_on_battle_end=True,
            start_window_size=window_size,
            start_fullscreen=fullscreen,
        )
    if mode_name == "launch_book":
        import book
        return book.main(
            host_mode=True,
            start_window_size=window_size,
            start_borderless=fullscreen,
            clean_start_media=False,
        )
    return None


def parse_args():
    parser = argparse.ArgumentParser(description="Radar Hell combined host")
    parser.add_argument("--capture-frame", metavar="PNG_PATH", help="Render one Radar Hell frame and save PNG, then exit.")
    return parser.parse_args()


class Sonar:
    """Tracks sonar pings/pulses for distance-based visibility sampling."""

    def __init__(self):
        self.last_ping_t = -999.0
        self._pulses = deque()

    def ping(self, strength=1.0, duration=SONAR_AFTERGLOW):
        now = time.perf_counter()
        if now - self.last_ping_t < SONAR_COOLDOWN:
            return False
        self.last_ping_t = now
        self.add_pulse(strength=strength, duration=duration)
        return True

    def add_pulse(self, strength=1.0, duration=SONAR_AFTERGLOW):
        now = time.perf_counter()
        self._pulses.append({
            "t0": now,
            "strength": max(0.0, float(strength)),
            "duration": max(0.05, float(duration)),
        })

    def sample(self, dist):
        now = time.perf_counter()
        d = max(0.0, float(dist))
        out = 0.0
        kept = deque()
        while self._pulses:
            p = self._pulses.popleft()
            age = now - p["t0"]
            dur = p["duration"]
            if age > dur:
                continue
            kept.append(p)

            # Moving wavefront + afterglow envelope.
            wave_center = age * SONAR_SPEED
            sigma = SONAR_SIGMA + 0.045 * wave_center
            wave = math.exp(-((d - wave_center) ** 2) / (2.0 * sigma * sigma))
            tail = math.exp(-d * SONAR_ATTEN) * (1.0 - clamp(age / dur, 0.0, 1.0))
            out += p["strength"] * (0.80 * wave + 0.45 * tail)

        self._pulses = kept
        return clamp(out, 0.0, 1.5)


def is_wall(grid, x, y):
    if x < 0 or y < 0 or y >= len(grid) or x >= len(grid[0]):
        return True
    return grid[y][x] == 1


def build_style_map(w, h, seed, world_kind):
    style = [[0] * w for _ in range(h)]
    world_off = sum(ord(c) for c in world_kind) * 17
    for y in range(h):
        for x in range(w):
            n0 = fbm(x * 0.73, y * 0.73, seed=seed + world_off + 40, octaves=3)
            n1 = fbm(x * 1.19 + 71.3, y * 1.19 + 9.7, seed=seed + world_off + 111, octaves=2)
            n = 0.72 * n0 + 0.28 * n1
            style[y][x] = int(clamp(n * 4.9, 0, 4))
    return style




def carve_central_tower(grid, seed):
    """Build a central octagonal tower with a spiral stair walkway around it."""
    h = len(grid)
    w = len(grid[0]) if h else 0
    cx, cy = w // 2, h // 2

    # Carve a large central chamber first.
    chamber_r = max(20, min(w, h) // 4)
    for y in range(max(1, cy - chamber_r), min(h - 1, cy + chamber_r + 1)):
        for x in range(max(1, cx - chamber_r), min(w - 1, cx + chamber_r + 1)):
            dx = x - cx
            dy = y - cy
            if dx * dx + dy * dy <= chamber_r * chamber_r:
                grid[y][x] = 0

    # Octagonal tower shell.
    inner_r = max(6, chamber_r // 3)
    outer_r = inner_r + 2
    for y in range(max(1, cy - outer_r - 1), min(h - 1, cy + outer_r + 2)):
        for x in range(max(1, cx - outer_r - 1), min(w - 1, cx + outer_r + 2)):
            dx = abs(x - cx)
            dy = abs(y - cy)
            oct_d = max(dx, dy, int((dx + dy) * 0.72))
            if inner_r <= oct_d <= outer_r:
                grid[y][x] = 1

    # Gate openings on the octagon.
    for gx, gy in ((cx, cy - inner_r), (cx + inner_r, cy), (cx, cy + inner_r), (cx - inner_r, cy)):
        for oy in (-1, 0, 1):
            for ox in (-1, 0, 1):
                xx = gx + ox
                yy = gy + oy
                if 1 <= xx < w - 1 and 1 <= yy < h - 1:
                    grid[yy][xx] = 0

    # Spiral stair walkway around the tower.
    turns = 2.75
    steps = 220
    start_r = outer_r + 3.0
    end_r = min(chamber_r - 2.0, start_r + 11.0)
    for i in range(steps):
        t = i / max(1, steps - 1)
        ang = t * turns * math.tau - math.pi * 0.5
        rr = lerp(start_r, end_r, t)
        x = int(round(cx + math.cos(ang) * rr))
        y = int(round(cy + math.sin(ang) * rr))
        for oy in (-1, 0, 1):
            for ox in (-1, 0, 1):
                xx = x + ox
                yy = y + oy
                if 1 <= xx < w - 1 and 1 <= yy < h - 1:
                    grid[yy][xx] = 0

    # Corridor from chamber edge toward map edge so movement stays free.
    for x in range(cx, w - 2):
        for yy in range(cy - 2, cy + 3):
            if 1 <= yy < h - 1:
                grid[yy][x] = 0
def gen_world(world_kind="cavern", seed=None):
    if seed is None:
        seed = random.randint(0, 10_000_000)
    rng = random.Random(seed)
    w, h = MAP_W, MAP_H

    grid = [[1] * w for _ in range(h)]

    if world_kind == "cavern":
        # Maze-first dungeon generation with room carving for stronger navigable structure.
        for y in range(1, h - 1):
            for x in range(1, w - 1):
                grid[y][x] = 1

        # Recursive backtracker maze on odd cells.
        start_x = (rng.randrange(1, (w - 2) // 2) * 2) + 1
        start_y = (rng.randrange(1, (h - 2) // 2) * 2) + 1
        stack = [(start_x, start_y)]
        grid[start_y][start_x] = 0
        dirs = [(2, 0), (-2, 0), (0, 2), (0, -2)]
        while stack:
            cx, cy = stack[-1]
            cand = []
            for dx, dy in dirs:
                nx, ny = cx + dx, cy + dy
                if 1 <= nx < w - 1 and 1 <= ny < h - 1 and grid[ny][nx] == 1:
                    cand.append((nx, ny, dx, dy))
            if cand:
                nx, ny, dx, dy = rng.choice(cand)
                grid[cy + dy // 2][cx + dx // 2] = 0
                grid[ny][nx] = 0
                stack.append((nx, ny))
            else:
                stack.pop()

        # Carve rooms into maze and connect to nearby corridors.
        rooms = []
        for _ in range(24):
            rw = rng.randrange(5, 17) | 1
            rh = rng.randrange(5, 17) | 1
            rx = (rng.randrange(2, (w - rw - 2) // 2) * 2) + 1
            ry = (rng.randrange(2, (h - rh - 2) // 2) * 2) + 1
            for yy in range(ry, min(h - 1, ry + rh)):
                for xx in range(rx, min(w - 1, rx + rw)):
                    grid[yy][xx] = 0
            rooms.append((rx + rw // 2, ry + rh // 2))

        for cx, cy in rooms:
            for _ in range(2):
                ang = rng.random() * math.tau
                dx = int(round(math.cos(ang)))
                dy = int(round(math.sin(ang)))
                x, y = cx, cy
                for _ in range(rng.randrange(4, 15)):
                    x += dx
                    y += dy
                    if 1 <= x < w - 1 and 1 <= y < h - 1:
                        grid[y][x] = 0

        # Extra cycles/openings so it does not feel too tree-like.
        for _ in range(900):
            x = rng.randrange(2, w - 2)
            y = rng.randrange(2, h - 2)
            if (x % 2 == 0 or y % 2 == 0) and grid[y][x] == 1:
                if rng.random() < 0.28:
                    grid[y][x] = 0

        # Add larger chambers and broad hall links.
        for _ in range(6):
            rw = rng.randrange(13, 27)
            rh = rng.randrange(13, 27)
            rx = rng.randrange(3, w - rw - 3)
            ry = rng.randrange(3, h - rh - 3)
            for yy in range(ry, ry + rh):
                for xx in range(rx, rx + rw):
                    if 1 <= xx < w - 1 and 1 <= yy < h - 1:
                        grid[yy][xx] = 0
            # Stair-like internal cuts/channels.
            sx0 = rx + 2
            sy0 = ry + 2
            step_w = max(3, rw // 6)
            step_h = max(2, rh // 6)
            for si in range(6):
                for yy in range(sy0 + si * step_h, min(ry + rh - 1, sy0 + (si + 1) * step_h)):
                    for xx in range(sx0 + si * step_w, min(rx + rw - 1, sx0 + (si + 1) * step_w)):
                        if 1 <= xx < w - 1 and 1 <= yy < h - 1:
                            grid[yy][xx] = 0

        # Remove dead ends while preserving connected maze readability.
        for _ in range(3):
            changed = False
            for y in range(2, h - 2):
                for x in range(2, w - 2):
                    if grid[y][x] != 0:
                        continue
                    open_n = 0
                    for dx, dy in ((1,0),(-1,0),(0,1),(0,-1)):
                        if grid[y + dy][x + dx] == 0:
                            open_n += 1
                    if open_n <= 1 and rng.random() < 0.72:
                        # Carve forward into a neighboring wall to break dead-end.
                        dirs = [(1,0),(-1,0),(0,1),(0,-1)]
                        rng.shuffle(dirs)
                        for dx, dy in dirs:
                            nx, ny = x + dx, y + dy
                            if grid[ny][nx] == 1:
                                grid[ny][nx] = 0
                                changed = True
                                break
            if not changed:
                break

        # Pillars in broad rooms for navigation silhouettes.
        for _ in range(52):
            x = rng.randrange(4, w - 4)
            y = rng.randrange(4, h - 4)
            if grid[y][x] != 0:
                continue
            open_n = 0
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    if dx == 0 and dy == 0:
                        continue
                    if grid[y + dy][x + dx] == 0:
                        open_n += 1
            if open_n < 6:
                continue
            r = 1 if rng.random() < 0.75 else 2
            for yy in range(y - r, y + r + 1):
                for xx in range(x - r, x + r + 1):
                    if 1 <= xx < w - 1 and 1 <= yy < h - 1 and (xx - x) * (xx - x) + (yy - y) * (yy - y) <= r * r:
                        grid[yy][xx] = 1

    else:
        # Non-cavern realms also use compact maze flow into the same center room.
        for y in range(1, h - 1):
            for x in range(1, w - 1):
                grid[y][x] = 1

        start_x = (rng.randrange(1, (w - 2) // 2) * 2) + 1
        start_y = (rng.randrange(1, (h - 2) // 2) * 2) + 1
        stack = [(start_x, start_y)]
        grid[start_y][start_x] = 0
        dirs = [(2, 0), (-2, 0), (0, 2), (0, -2)]
        while stack:
            cx, cy = stack[-1]
            cand = []
            for dx, dy in dirs:
                nx, ny = cx + dx, cy + dy
                if 1 <= nx < w - 1 and 1 <= ny < h - 1 and grid[ny][nx] == 1:
                    cand.append((nx, ny, dx, dy))
            if cand:
                nx, ny, dx, dy = rng.choice(cand)
                grid[cy + dy // 2][cx + dx // 2] = 0
                grid[ny][nx] = 0
                stack.append((nx, ny))
            else:
                stack.pop()

        for _ in range(12):
            rw = rng.randrange(5, 11) | 1
            rh = rng.randrange(5, 11) | 1
            rx = (rng.randrange(2, max(3, (w - rw - 2) // 2)) * 2) + 1
            ry = (rng.randrange(2, max(3, (h - rh - 2) // 2)) * 2) + 1
            for yy in range(ry, min(h - 1, ry + rh)):
                for xx in range(rx, min(w - 1, rx + rw)):
                    grid[yy][xx] = 0

    # Build a center tower/chamber structure in every world.
    carve_central_tower(grid, seed)

    # Guaranteed central hub room keeps maze connected around the core.
    cx, cy = w // 2, h // 2
    hrx = max(6, w // 14)
    hry = max(6, h // 14)
    for yy in range(cy - hry, cy + hry + 1):
        for xx in range(cx - hrx, cx + hrx + 1):
            if 1 <= xx < w - 1 and 1 <= yy < h - 1:
                grid[yy][xx] = 0

    # largest connected open region
    visited = [[False] * w for _ in range(h)]
    best = []
    for y in range(1, h - 1):
        for x in range(1, w - 1):
            if grid[y][x] == 0 and not visited[y][x]:
                q = deque([(x, y)])
                visited[y][x] = True
                comp = []
                while q:
                    cx, cy = q.popleft()
                    comp.append((cx, cy))
                    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        nx, ny = cx + dx, cy + dy
                        if 0 <= nx < w and 0 <= ny < h and not visited[ny][nx] and grid[ny][nx] == 0:
                            visited[ny][nx] = True
                            q.append((nx, ny))
                if len(comp) > len(best):
                    best = comp
    keep = set(best)
    for y in range(1, h - 1):
        for x in range(1, w - 1):
            if grid[y][x] == 0 and (x, y) not in keep:
                grid[y][x] = 1

    sx, sy = w // 2, h // 2
    spawn = None
    for r in range(max(w, h)):
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                x = sx + dx
                y = sy + dy
                if 1 <= x < w - 1 and 1 <= y < h - 1 and grid[y][x] == 0:
                    spawn = (x + 0.5, y + 0.5)
                    break
            if spawn:
                break
        if spawn:
            break
    if spawn is None:
        spawn = (2.5, 2.5)
        grid[2][2] = 0

    style_map = build_style_map(w, h, seed + 777, world_kind)
    return grid, style_map, spawn, seed



def cast_ray(grid, px, py, ray_dir_x, ray_dir_y):
    """DDA grid raycast. Returns (distance, side, wall_u, (cell_x, cell_y))."""
    h = len(grid)
    w = len(grid[0]) if h else 0

    map_x = int(px)
    map_y = int(py)

    if abs(ray_dir_x) < 1e-12:
        ray_dir_x = 1e-12
    if abs(ray_dir_y) < 1e-12:
        ray_dir_y = 1e-12

    delta_dist_x = abs(1.0 / ray_dir_x)
    delta_dist_y = abs(1.0 / ray_dir_y)

    if ray_dir_x < 0:
        step_x = -1
        side_dist_x = (px - map_x) * delta_dist_x
    else:
        step_x = 1
        side_dist_x = (map_x + 1.0 - px) * delta_dist_x

    if ray_dir_y < 0:
        step_y = -1
        side_dist_y = (py - map_y) * delta_dist_y
    else:
        step_y = 1
        side_dist_y = (map_y + 1.0 - py) * delta_dist_y

    side = 0
    for _ in range(MAX_STEPS):
        if side_dist_x < side_dist_y:
            side_dist_x += delta_dist_x
            map_x += step_x
            side = 0
        else:
            side_dist_y += delta_dist_y
            map_y += step_y
            side = 1

        if map_x < 0 or map_y < 0 or map_y >= h or map_x >= w:
            break
        if grid[map_y][map_x] == 1:
            break

    if side == 0:
        perp = (map_x - px + (1 - step_x) * 0.5) / ray_dir_x
        hit_x = map_x
        hit_y = py + perp * ray_dir_y
        wall_u = hit_y - math.floor(hit_y)
    else:
        perp = (map_y - py + (1 - step_y) * 0.5) / ray_dir_y
        hit_x = px + perp * ray_dir_x
        hit_y = map_y
        wall_u = hit_x - math.floor(hit_x)

    perp = clamp(perp, 0.001, MAX_DIST)
    wall_u = clamp(wall_u, 0.0, 1.0)

    cell_x = int(clamp(map_x, 0, w - 1)) if w else 0
    cell_y = int(clamp(map_y, 0, h - 1)) if h else 0
    return perp, side, wall_u, (cell_x, cell_y)

def build_world_features(grid, seed):
    rng = random.Random(seed + 6262)
    h = len(grid)
    w = len(grid[0]) if h else 0
    open_tiles = [(x, y) for y in range(2, h - 2) for x in range(2, w - 2) if grid[y][x] == 0]
    rng.shuffle(open_tiles)

    spike_tiles = set()

    wall_tiles = [(x, y) for y in range(2, h - 2) for x in range(2, w - 2) if grid[y][x] == 1]
    rng.shuffle(wall_tiles)
    symbol_tiles = set(wall_tiles[:max(64, len(wall_tiles) // 26)])
    tooth_tiles = set(wall_tiles[max(64, len(wall_tiles) // 26):max(128, len(wall_tiles) // 16)])

    # Spiral stair markers around the central octagonal tower.
    stair_tiles = set()
    cx, cy = w // 2, h // 2
    chamber_r = max(20, min(w, h) // 4)
    inner_r = max(6, chamber_r // 3)
    start_r = inner_r + 5.0
    end_r = min(chamber_r - 2.0, start_r + 11.0)
    turns = 2.75
    for i in range(220):
        t = i / 219.0
        ang = t * turns * math.tau - math.pi * 0.5
        rr = lerp(start_r, end_r, t)
        x = int(round(cx + math.cos(ang) * rr))
        y = int(round(cy + math.sin(ang) * rr))
        if 1 <= x < w - 1 and 1 <= y < h - 1 and grid[y][x] == 0:
            stair_tiles.add((x, y))

    return spike_tiles, symbol_tiles, stair_tiles, tooth_tiles


# tree placeholder renderer removed by design

def make_enemy_sprite(kind, size=220):
    palettes = [
        (255, 70, 70), (120, 170, 255), (130, 255, 180), (220, 140, 255), (255, 220, 120),
        (120, 250, 255), (255, 110, 170), (190, 255, 120), (170, 170, 255),
    ]
    c = palettes[kind % len(palettes)]
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    cx, cy = size // 2, size // 2
    rng = random.Random(9999 + kind * 77)
    for _ in range(500):
        a = rng.random() * math.tau
        r = rng.uniform(12, size * 0.46) * (0.35 + 0.65 * rng.random())
        x = int(cx + math.cos(a) * r * rng.uniform(0.7, 1.4))
        y = int(cy + math.sin(a) * r * rng.uniform(0.7, 1.4))
        rad = rng.randint(2, 8)
        alpha = rng.randint(40, 170)
        pygame.draw.circle(surf, (c[0], c[1], c[2], alpha), (x, y), rad)
    for _ in range(70):
        x = rng.randint(10, size - 10)
        y = rng.randint(10, size - 10)
        pygame.draw.circle(surf, (255, 255, 255, rng.randint(40, 150)), (x, y), rng.randint(1, 3))
    return surf

def make_item_sprite(kind, color, size=64):
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    pygame.draw.rect(surf, (20, 20, 20, 220), pygame.Rect(8, 10, size - 16, size - 20), border_radius=8)
    pygame.draw.rect(surf, (*color, 220), pygame.Rect(14, 16, size - 28, 10), border_radius=4)
    pygame.draw.circle(surf, (255, 255, 255, 220), (size // 2, size // 2 + 10), 6 + kind % 6)
    return surf


def make_powerup_sprite(size=68):
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    for i in range(3):
        pygame.draw.circle(surf, (80, 255, 120, 140), (size // 2, size // 2), size // 2 - i * 7, width=2)
    pygame.draw.circle(surf, (210, 255, 220, 230), (size // 2, size // 2), 8)
    return surf


def make_sky_texture(w=1024, h=240, seed=4545):
    rng = random.Random(seed)
    surf = pygame.Surface((w, h)).convert()
    top = (18, 5, 7)
    bot = (6, 2, 3)
    for y in range(h):
        t = y / max(1, h - 1)
        pygame.draw.line(
            surf,
            (int(lerp(top[0], bot[0], t)), int(lerp(top[1], bot[1], t)), int(lerp(top[2], bot[2], t))),
            (0, y),
            (w, y),
        )
    for _ in range(max(1, w // 28)):
        x = rng.randrange(0, w)
        y = rng.randrange(0, h)
        c = rng.randrange(10, 24)
        surf.set_at((x, y), (c, max(2, c // 3), max(2, c // 3)))
    return surf


def build_skyline_layer(w, h, seed, world_kind):
    # Performance mode: no mountain/cloud skyline silhouettes.
    return pygame.Surface((w, h), pygame.SRCALPHA)


def load_or_build_skyline(cache_key, w, h, seed, world_kind):
    os.makedirs(ASSET_CACHE_DIR, exist_ok=True)
    # Keep only one persistent cached skyline per world-kind/size to avoid cache clutter.
    cache_path = os.path.join(ASSET_CACHE_DIR, f"skyline_{world_kind}_{w}x{h}.png")
    cached = load_image_or_none(cache_path, alpha=False)
    if cached is not None and cached.get_size() == (w, h):
        return cached
    built = build_skyline_layer(w, h, seed, world_kind)
    save_surface_if_missing(cache_path, built)
    return built

def make_portal_sprite(color, size=96):
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    c = (color[0], color[1], color[2], 190)
    pygame.draw.circle(surf, c, (size // 2, size // 2), size // 2 - 8, width=4)
    pygame.draw.circle(surf, (255, 255, 255, 180), (size // 2, size // 2), size // 5, width=2)
    return surf


def _load_sequence_frames(prefix):
    frames = []
    if not os.path.isdir(ASSET_ENEMY_DIR):
        return frames
    pat = re.compile(rf"^{re.escape(prefix)}_(\d+)\.png$", re.IGNORECASE)
    indexed = []
    for name in os.listdir(ASSET_ENEMY_DIR):
        m = pat.match(name)
        if m:
            indexed.append((int(m.group(1)), os.path.join(ASSET_ENEMY_DIR, name)))
    indexed.sort(key=lambda t: t[0])
    for _, path in indexed:
        surf = load_image_or_none(path)
        if surf is not None:
            frames.append(surf)
    return frames


def _extract_eye_points(frame, max_pts=28):
    w, h = frame.get_size()
    pts = []
    step_x = max(1, w // 96)
    step_y = max(1, h // 96)
    for y in range(0, h, step_y):
        for x in range(0, w, step_x):
            r, g, b, a = frame.get_at((x, y))
            if a > 24 and r >= 165 and (r - g) >= 70 and (r - b) >= 70:
                pts.append((x, y))
    if len(pts) > max_pts:
        stride = max(1, len(pts) // max_pts)
        pts = pts[::stride][:max_pts]
    return pts


def build_enemy_sprites():
    # enemy_0..enemy_9 are the primary movement animation frames,
    # attack_1..attack_N are optional attack overlays/frames.
    move_frames = _load_sequence_frames("enemy")
    attack_frames = _load_sequence_frames("attack")

    # Do not generate placeholders on disk for enemies; use provided art.
    if not move_frames:
        # Runtime-safe fallback surface only (not saved to disk).
        move_frames = [pygame.Surface((220, 220), pygame.SRCALPHA)]

    eye_points = [_extract_eye_points(f) for f in move_frames]
    return {
        "move": move_frames,
        "attack": attack_frames,
        "eye_points": eye_points,
    }


def build_marker_assets(weapons):
    pickup = []
    for i in range(9):
        path = os.path.join(ASSET_ITEM_DIR, f"weapon_pickup_{i}.png")
        surf = load_image_or_none(path)
        if surf is None:
            surf = make_item_sprite(i, weapons[i].energy_color)
            save_surface_if_missing(path, surf)
        pickup.append(surf)

    nv_path = os.path.join(ASSET_POWERUP_DIR, "nightvision.png")
    nightvision = load_image_or_none(nv_path)
    if nightvision is None:
        nightvision = make_powerup_sprite()
        save_surface_if_missing(nv_path, nightvision)

    to_ext_path = os.path.join(ASSET_PORTAL_DIR, "portal_to_exterior.png")
    to_cav_path = os.path.join(ASSET_PORTAL_DIR, "portal_to_cavern.png")
    portal_to_ext = load_image_or_none(to_ext_path)
    portal_to_cav = load_image_or_none(to_cav_path)
    if portal_to_ext is None:
        portal_to_ext = make_portal_sprite((180, 70, 255))
        save_surface_if_missing(to_ext_path, portal_to_ext)
    if portal_to_cav is None:
        portal_to_cav = make_portal_sprite((255, 90, 70))
        save_surface_if_missing(to_cav_path, portal_to_cav)

    sky_path = os.path.join(ASSET_SKY_DIR, "sky.png")
    sky = load_image_or_none(sky_path, alpha=False)
    if sky is None:
        sky = make_sky_texture()
        save_surface_if_missing(sky_path, sky)

    return {
        "pickup": pickup,
        "nightvision": nightvision,
        "portal_to_exterior": portal_to_ext,
        "portal_to_cavern": portal_to_cav,
        "sky": sky,
    }



def build_minimap_base(grid, scale=2):
    h = len(grid)
    w = len(grid[0]) if h else 0
    mm = pygame.Surface((w, h)).convert()
    for y in range(h):
        row = grid[y]
        for x in range(w):
            mm.set_at((x, y), (65, 25, 25) if row[x] else (14, 6, 6))
    if scale != 1:
        mm = pygame.transform.smoothscale(mm, (w * scale, h * scale))
    mm.set_alpha(195)
    return mm


def make_noise_texture(w, h, seed, c0, c1):
    surf = pygame.Surface((w, h))
    for y in range(h):
        for x in range(w):
            n = fbm(x + seed * 3.7, y + seed * 1.9, seed=seed + 17, octaves=3)
            t = clamp((n - 0.2) / 0.6, 0.0, 1.0)
            surf.set_at((x, y), (int(lerp(c0[0], c1[0], t)), int(lerp(c0[1], c1[1], t)), int(lerp(c0[2], c1[2], t))))
    return surf




def make_tile_texture(kind, idx, size=128, seed=0):
    rng = random.Random(seed + idx * 97 + (11 if kind == "wall" else 37 if kind == "floor" else 53))
    surf = pygame.Surface((size, size)).convert()
    if kind == "wall":
        c0, c1 = (66, 26, 24), (132, 46, 36)
    elif kind == "floor":
        c0, c1 = (34, 14, 12), (78, 30, 22)
    else:
        c0, c1 = (26, 10, 10), (58, 22, 22)
    for y in range(size):
        for x in range(size):
            n = fbm(x * 0.09 + idx * 3.1, y * 0.09 - idx * 1.7, seed=seed + idx * 29, octaves=3)
            t = clamp((n - 0.28) / 0.52, 0.0, 1.0)
            r = int(lerp(c0[0], c1[0], t))
            g = int(lerp(c0[1], c1[1], t))
            b = int(lerp(c0[2], c1[2], t))
            surf.set_at((x, y), (r, g, b))
    for _ in range(120 + idx * 20):
        x0 = rng.randrange(0, size)
        y0 = rng.randrange(0, size)
        ln = rng.randrange(4, 16)
        ang = rng.uniform(0, math.tau)
        x1 = int((x0 + math.cos(ang) * ln) % size)
        y1 = int((y0 + math.sin(ang) * ln) % size)
        col = (c1[0] + 10, c1[1] + 8, c1[2] + 8)
        pygame.draw.line(surf, col, (x0, y0), (x1, y1), 1)
    return surf


def build_surface_textures(seed=777):
    walls, floors, ceilings = [], [], []
    for i in range(5):
        wpath = os.path.join(ASSET_SURFACE_WALL_DIR, f"wall_{i}.png")
        fpath = os.path.join(ASSET_SURFACE_FLOOR_DIR, f"floor_{i}.png")
        cpath = os.path.join(ASSET_SURFACE_CEIL_DIR, f"ceiling_{i}.png")

        wimg = load_image_or_none(wpath, alpha=False)
        if wimg is None:
            wimg = make_tile_texture("wall", i, seed=seed)
            save_surface_if_missing(wpath, wimg)
        walls.append(wimg)

        fimg = load_image_or_none(fpath, alpha=False)
        if fimg is None:
            fimg = make_tile_texture("floor", i, seed=seed + 101)
            save_surface_if_missing(fpath, fimg)
        floors.append(fimg)

        cimg = load_image_or_none(cpath, alpha=False)
        if cimg is None:
            cimg = make_tile_texture("ceiling", i, seed=seed + 203)
            save_surface_if_missing(cpath, cimg)
        ceilings.append(cimg)
    return {"walls": walls, "floors": floors, "ceilings": ceilings}



def build_terrain_chunk_surface(style_map, textures, chunk_x, chunk_y, kind):
    surf = pygame.Surface((TERRAIN_CHUNK_PX, TERRAIN_CHUNK_PX)).convert()
    px_per_tile = max(1, TERRAIN_CHUNK_PX // TERRAIN_CHUNK_TILES)
    for ty in range(TERRAIN_CHUNK_TILES):
        wy = chunk_y * TERRAIN_CHUNK_TILES + ty
        for tx in range(TERRAIN_CHUNK_TILES):
            wx = chunk_x * TERRAIN_CHUNK_TILES + tx
            style_id = style_map[wy % MAP_H][wx % MAP_W]
            timg = textures[kind][style_id % len(textures[kind])]
            tw, th = timg.get_size()
            # Normal tiled sampling: repeat local tile texture without overlap/noise smearing.
            for py in range(px_per_tile):
                sy = int((py / max(1, px_per_tile)) * (th - 1))
                for px_i in range(px_per_tile):
                    sx = int((px_i / max(1, px_per_tile)) * (tw - 1))
                    surf.set_at((tx * px_per_tile + px_i, ty * px_per_tile + py), timg.get_at((sx, sy)))
    return surf



_DEMONIC_FLOOR_CACHE = {}


def _get_demonic_floor_lut(seed=0, size=256):
    key = (int(seed), int(size))
    cached = _DEMONIC_FLOOR_CACHE.get(key)
    if cached is not None:
        return cached

    base = (46, 8, 10)
    packed = array("I", [0]) * (size * size)
    inv = 1.0 / float(size)
    for y in range(size):
        wy = y * inv * 42.0
        for x in range(size):
            wx = x * inv * 42.0
            n = fbm(wx * 0.14, wy * 0.14, seed=seed + 1407, octaves=2)
            shade = int(8 * (n - 0.5))
            r = max(20, min(255, base[0] + shade))
            g = max(2, min(255, base[1] + shade // 3))
            b = max(2, min(255, base[2] + shade // 3))

            cell = 7.0
            cx = int(math.floor(wx / cell))
            cy = int(math.floor(wy / cell))
            if hash2i(cx, cy, seed=seed + 1709) > 0.72:
                lx = (wx / cell) - cx - 0.5
                ly = (wy / cell) - cy - 0.5
                ring = abs(math.hypot(lx, ly) - 0.24)
                tri = max(abs(lx), abs(ly), abs(lx + ly) * 0.72)
                rune = min(ring, tri * 0.78)
                if rune < 0.045:
                    glow = int((0.045 - rune) * 2600)
                    r = min(255, r + 48 + glow)
                    g = min(255, g + 8 + glow // 12)
                    b = min(255, b + 10 + glow // 14)

            packed[y * size + x] = (r << 16) | (g << 8) | b

    floor_scale = size / 42.0
    out = (packed, size, size - 1, floor_scale)
    _DEMONIC_FLOOR_CACHE[key] = out
    return out


def sample_demonic_floor(wx, wy, seed=0):
    packed, size, mask, floor_scale = _get_demonic_floor_lut(seed=seed, size=256)
    tx = int(wx * floor_scale) & mask
    ty = int(wy * floor_scale) & mask
    c = packed[ty * size + tx]
    return (c >> 16) & 255, (c >> 8) & 255, c & 255

def build_monster_sfx():
    alive_variants = []
    death_variants = []
    if not pygame.mixer.get_init():
        return alive_variants, death_variants

    names = []
    try:
        names = sorted(os.listdir(ASSET_SFX_MONSTER_DIR))
    except Exception:
        names = []

    for name in names:
        lname = name.lower()
        if not lname.endswith(".mp3"):
            continue
        path = os.path.join(ASSET_SFX_MONSTER_DIR, name)
        if "attack" in lname:
            continue
        if "death" in lname:
            ds = load_sound_candidates([path], default=None, volume=0.56)
            if ds:
                death_variants.append(ds)
            continue
        gs = load_sound_candidates([path], default=None, volume=0.42)
        if gs:
            alive_variants.append(gs)

    # Compatibility fallback for legacy numbered naming if directory listing is sparse.
    if not alive_variants:
        for kind in range(9):
            gpath = os.path.join(ASSET_SFX_MONSTER_DIR, f"monster_{kind}.mp3")
            gs = load_sound_candidates([gpath], default=None, volume=0.42)
            if gs:
                alive_variants.append(gs)
    if not death_variants:
        for kind in range(9):
            dpath = os.path.join(ASSET_SFX_MONSTER_DIR, f"monster_{kind}_death.mp3")
            ds = load_sound_candidates([dpath], default=None, volume=0.56)
            if ds:
                death_variants.append(ds)
    return alive_variants, death_variants


def pick_from_sound_cycle(pool, bag):
    if not pool:
        return None, bag
    if not bag:
        bag = list(range(len(pool)))
        random.shuffle(bag)
    idx = bag.pop()
    return pool[idx], bag


@dataclass
class WeaponVariant:
    idx: int
    name: str
    texture_rotated: pygame.Surface
    muzzle_color: tuple[int, int, int]
    energy_color: tuple[int, int, int]
    impact_color: tuple[int, int, int]
    bullet_color: tuple[int, int, int]
    cooldown: float
    spread: float
    damage: int
    recoil: float
    sfx: pygame.mixer.Sound | None
    impact_sfx: pygame.mixer.Sound | None
    pickup_sfx: pygame.mixer.Sound | None
    barrel_anchor: tuple[int, int]
    fx_radius: int
    fx_beam_width: int
    fx_burst_count: int


@dataclass
class Enemy:
    x: float
    y: float
    kind: int
    hp: int = 100
    last_ping_t: float = -999.0
    learn: float = 0.0
    anim_phase: float = 0.0
    flip_bias: int = 0


@dataclass
class WeaponPickup:
    x: float
    y: float
    weapon_idx: int


@dataclass
class Powerup:
    x: float
    y: float
    kind: str


@dataclass
class Portal:
    x: float
    y: float
    target_world: str


def load_weapon_override(idx):
    tex_path = os.path.join(ASSET_WEAPON_DIR, f"weapon_{idx}.png")
    blast_wav = os.path.join(ASSET_SFX_WEAPON_DIR, f"weapon_{idx}.wav")
    blast_mp3 = os.path.join(ASSET_SFX_WEAPON_DIR, f"weapon_{idx}.mp3")
    impact_wav = os.path.join(ASSET_SFX_WEAPON_DIR, f"weapon_{idx}_impact.wav")
    impact_mp3 = os.path.join(ASSET_SFX_WEAPON_DIR, f"weapon_{idx}_impact.mp3")
    json_path = os.path.join(ASSET_WEAPON_DIR, f"weapon_{idx}.json")
    cfg = {}
    if os.path.exists(json_path):
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception:
            cfg = {}

    tex = None
    if os.path.exists(tex_path):
        try:
            tex = pygame.image.load(tex_path).convert_alpha()
        except Exception:
            tex = None

    sfx = load_sound_candidates([blast_wav, blast_mp3], default=None, volume=0.58)
    impact_sfx = load_sound_candidates([impact_wav, impact_mp3], default=None, volume=0.56)
    return tex, sfx, impact_sfx, cfg


def make_weapon_sprite(idx, seed, palette):
    w, h = 960, 460
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    body_tex = make_noise_texture(560, 260, seed + idx * 30, palette[0], palette[1])
    pygame.draw.polygon(surf, (35, 35, 35, 240), [(260, 160), (640, 150), (830, 210), (900, 320), (420, 410), (250, 370)])
    pygame.draw.polygon(surf, (28, 26, 26, 240), [(220, 230), (310, 205), (350, 370), (275, 430), (200, 350)])
    pygame.draw.polygon(surf, (46, 46, 46, 240), [(650, 150), (830, 135), (935, 170), (945, 256), (815, 303), (760, 255)])

    mask = pygame.Surface((560, 260), pygame.SRCALPHA)
    pygame.draw.polygon(mask, (255, 255, 255, 255), [(15, 45), (370, 26), (545, 90), (550, 205), (178, 245), (20, 210)])
    body_tex.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    surf.blit(body_tex, (265, 145))

    glow = palette[2]
    pygame.draw.rect(surf, (*glow, 190), pygame.Rect(390, 238, 210, 19), border_radius=9)
    pygame.draw.rect(surf, (*glow, 165), pygame.Rect(665, 215, 160, 14), border_radius=7)
    pygame.draw.circle(surf, (*glow, 225), (815, 220), 17)
    pygame.draw.circle(surf, (255, 255, 255, 220), (823, 220), 4)
    return surf




def find_anchor_from_muzzle_map(path, fallback, target_size):
    img = load_image_or_none(path)
    tw, th = target_size
    if img is None:
        return fallback
    w, h = img.get_size()
    pts = []
    for y in range(h):
        for x in range(w):
            r, g, b, a = img.get_at((x, y))
            if a > 20 and r >= 180 and (r - g) >= 80 and (r - b) >= 80:
                pts.append((x, y))
    if not pts:
        return fallback

    # Use the red marker centroid exactly so muzzle flare stays centered on the painted dot.
    sx = sum(t[0] for t in pts) / len(pts)
    sy = sum(t[1] for t in pts) / len(pts)

    nx = sx / max(1.0, w - 1)
    ny = sy / max(1.0, h - 1)
    return int(nx * max(1, tw - 1)), int(ny * max(1, th - 1))




def rotate_point(px, py, ox, oy, angle_deg):
    a = math.radians(angle_deg)
    ca = math.cos(a)
    sa = math.sin(a)
    x = px - ox
    y = py - oy
    return (x * ca - y * sa) + ox, (x * sa + y * ca) + oy


def get_weapon_pose_cached(cache, weapon_idx, weapon, angle_key, angle_deg):
    d = cache[weapon_idx]
    got = d.get(angle_key)
    if got is not None:
        return got

    src = weapon.texture_rotated
    sw, sh = src.get_size()
    pivot = (sw * 0.5, sh - 1.0)  # bottom-center pivot, like held weapon stock point

    corners = [(0.0, 0.0), (sw - 1.0, 0.0), (sw - 1.0, sh - 1.0), (0.0, sh - 1.0)]
    rc = [rotate_point(x, y, pivot[0], pivot[1], angle_deg) for x, y in corners]
    min_x = min(t[0] for t in rc)
    min_y = min(t[1] for t in rc)

    surf = pygame.transform.rotozoom(src, angle_deg, 1.0)

    ax, ay = rotate_point(weapon.barrel_anchor[0], weapon.barrel_anchor[1], pivot[0], pivot[1], angle_deg)
    anchor = (int(ax - min_x), int(ay - min_y))

    d.set(angle_key, (surf, anchor))
    return d.get(angle_key)


def build_weapons():
    palettes = [
        ((45, 33, 33), (95, 55, 45), (255, 110, 80)),
        ((28, 30, 38), (66, 72, 95), (100, 170, 255)),
        ((26, 36, 30), (52, 92, 75), (100, 230, 165)),
        ((30, 24, 34), (90, 60, 120), (205, 120, 255)),
        ((38, 28, 20), (114, 72, 36), (255, 188, 74)),
        ((22, 28, 34), (45, 86, 104), (92, 220, 255)),
        ((36, 24, 24), (120, 52, 52), (255, 75, 75)),
        ((28, 34, 18), (78, 112, 36), (180, 255, 96)),
        ((28, 24, 44), (68, 62, 120), (145, 150, 255)),
    ]
    weapons = []
    for i in range(9):
        idx = i + 1
        tex_override, sfx_override, impact_override, cfg = load_weapon_override(idx)
        p = palettes[i]
        default_texture = make_weapon_sprite(idx, 911 + i * 17, p)
        default_path = os.path.join(ASSET_WEAPON_DIR, f"weapon_{idx}.png")
        save_surface_if_missing(default_path, default_texture)
        texture = tex_override if tex_override is not None else default_texture
        tex_rot = pygame.transform.rotozoom(texture, 0.0, 0.90)

        sfx = sfx_override
        impact_sfx = impact_override if impact_override is not None else sfx_override
        pickup_wav = os.path.join(ASSET_SFX_WEAPON_PICKUP_DIR, f"weapon_pickup_{idx}.wav")
        pickup_mp3 = os.path.join(ASSET_SFX_WEAPON_PICKUP_DIR, f"weapon_pickup_{idx}.mp3")
        pickup_sfx = load_sound_candidates([pickup_wav, pickup_mp3], default=None, volume=0.52)
        fx_radius = 58 + i * 8
        fx_beam_width = 2 + (i % 4)
        fx_burst_count = 3 + (i % 5)

        weapons.append(
            WeaponVariant(
                idx=idx,
                name=f"W-{idx}",
                texture_rotated=tex_rot,
                muzzle_color=tuple(cfg.get("muzzle_color", p[2])),
                energy_color=tuple(cfg.get("energy_color", p[2])),
                impact_color=tuple(cfg.get("impact_color", (255, 255, 255))),
                bullet_color=tuple(cfg.get("bullet_color", p[1])),
                cooldown=float(cfg.get("cooldown", 0.055 + i * 0.010)),
                spread=float(cfg.get("spread", 0.008 + i * 0.002)),
                damage=int(cfg.get("damage", 28 + i * 8)),
                recoil=float(cfg.get("recoil", 3.2 + i * 0.35)),
                sfx=sfx,
                impact_sfx=impact_sfx,
                pickup_sfx=pickup_sfx,
                barrel_anchor=find_anchor_from_muzzle_map(
                    os.path.join(ASSET_MUZZLE_MAP_DIR, f"weapon_{idx}_muzzle.png"),
                    (
                        int(cfg.get("barrel_x", int(tex_rot.get_width() * 0.50))),
                        int(cfg.get("barrel_y", int(tex_rot.get_height() * 0.30))),
                    ),
                    tex_rot.get_size(),
                ),
                fx_radius=int(cfg.get("fx_radius", fx_radius)),
                fx_beam_width=int(cfg.get("fx_beam_width", fx_beam_width)),
                fx_burst_count=int(cfg.get("fx_burst_count", fx_burst_count)),
            )
        )
    return weapons


def enemy_step_toward(grid, ex, ey, tx, ty, step):
    dx, dy = tx - ex, ty - ey
    d = math.hypot(dx, dy)
    if d < 1e-6:
        return ex, ey
    dx /= d
    dy /= d

    nx, ny = ex + dx * step, ey + dy * step
    if not is_wall(grid, int(nx), int(ey)):
        ex = nx
    elif not is_wall(grid, int(ex), int(ny)):
        ey = ny
    else:
        px, py = -dy, dx
        n2x, n2y = ex + px * step * 0.6, ey + py * step * 0.6
        if not is_wall(grid, int(n2x), int(n2y)):
            ex, ey = n2x, n2y

    if not is_wall(grid, int(ex), int(ny)):
        ey = ny
    return ex, ey


def has_los(grid, px, py, tx, ty):
    dx = tx - px
    dy = ty - py
    d = math.hypot(dx, dy)
    if d <= 1e-6:
        return True
    dx /= d
    dy /= d
    wall_dist, _, _, _ = cast_ray(grid, px, py, dx, dy)
    return wall_dist + 0.08 >= d


def spawn_enemies(grid, spawn, n, seed, difficulty_level=1):
    rng = random.Random(seed + 222)
    h = len(grid)
    w = len(grid[0])
    sx, sy = spawn
    enemies = []
    target_n = max(1, min(1, n))

    # Main room start: place the first monster near the center chamber whenever possible.
    cx, cy = w // 2, h // 2
    center_slots = []
    for r in range(0, max(w, h)):
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                x = cx + dx
                y = cy + dy
                if 1 <= x < w - 1 and 1 <= y < h - 1 and grid[y][x] == 0:
                    if (x + 0.5 - sx) ** 2 + (y + 0.5 - sy) ** 2 >= 9.0 ** 2:
                        center_slots.append((x + 0.5, y + 0.5))
        if center_slots:
            break
    if center_slots:
        x, y = rng.choice(center_slots)
        enemies.append(Enemy(
            x=x, y=y, kind=0,
            hp=int(1800 * (1.0 + 0.35 * max(0, difficulty_level - 1))),
            anim_phase=rng.random() * 1000.0,
            flip_bias=rng.randrange(0, 2),
        ))

    tries = 0
    while len(enemies) < target_n and tries < 4000:
        tries += 1
        x = rng.randrange(2, w - 2) + 0.5
        y = rng.randrange(2, h - 2) + 0.5
        if is_wall(grid, int(x), int(y)):
            continue
        if (x - sx) ** 2 + (y - sy) ** 2 < 14.0 ** 2:
            continue
        enemies.append(Enemy(
            x=x, y=y, kind=0,
            hp=int(1800 * (1.0 + 0.35 * max(0, difficulty_level - 1))),
            anim_phase=rng.random() * 1000.0,
            flip_bias=rng.randrange(0, 2),
        ))
    return enemies


def spawn_pickups(grid, spawn, count, seed):
    rng = random.Random(seed + 888)
    h = len(grid)
    w = len(grid[0])
    sx, sy = spawn
    pickups = []
    min_sep2 = 6.5 ** 2
    weapon_order = list(range(9))
    rng.shuffle(weapon_order)
    for wid in weapon_order:
        placed = False
        for _ in range(2200):
            x = rng.randrange(2, w - 2) + 0.5
            y = rng.randrange(2, h - 2) + 0.5
            if is_wall(grid, int(x), int(y)):
                continue
            if (x - sx) ** 2 + (y - sy) ** 2 < 12.0 ** 2:
                continue
            if any((p.x - x) ** 2 + (p.y - y) ** 2 < min_sep2 for p in pickups):
                continue
            pickups.append(WeaponPickup(x=x, y=y, weapon_idx=wid))
            placed = True
            break
        if not placed:
            pickups.append(WeaponPickup(x=sx + 1.5 + 0.15 * wid, y=sy + 1.5, weapon_idx=wid))
    return pickups


def spawn_powerups(grid, spawn, count, seed):
    rng = random.Random(seed + 1666)
    h = len(grid)
    w = len(grid[0])
    sx, sy = spawn
    powerups = []
    tries = 0
    while len(powerups) < count and tries < count * 1500:
        tries += 1
        x = rng.randrange(2, w - 2) + 0.5
        y = rng.randrange(2, h - 2) + 0.5
        if is_wall(grid, int(x), int(y)):
            continue
        if (x - sx) ** 2 + (y - sy) ** 2 < 18.0 ** 2:
            continue
        powerups.append(Powerup(x=x, y=y, kind="nightvision"))
    return powerups



def choose_next_world_kind(current_world, difficulty_level, seed):
    options = [w for w in REALM_KINDS if w != current_world]
    if not options:
        return current_world
    rng = random.Random(seed + difficulty_level * 313)
    return rng.choice(options)

def spawn_portals(grid, seed, world_kind, spawn):
    rng = random.Random(seed + 1333)
    h = len(grid)
    w = len(grid[0])
    portals = []
    target = choose_next_world_kind(world_kind, max(1, seed % 97), seed)

    # Central tower-top portal anchor (top of spiral path).
    cx, cy = w // 2, h // 2
    top_ang = 2.75 * math.tau - math.pi * 0.5
    top_r = max(9.0, min(w, h) * 0.17)
    tx = int(round(cx + math.cos(top_ang) * top_r))
    ty = int(round(cy + math.sin(top_ang) * top_r))
    if 1 <= tx < w - 1 and 1 <= ty < h - 1:
        for yy in range(ty - 1, ty + 2):
            for xx in range(tx - 1, tx + 2):
                if 1 <= xx < w - 1 and 1 <= yy < h - 1:
                    grid[yy][xx] = 0
        portals.append(Portal(x=tx + 0.5, y=ty + 0.5, target_world=target))

    if world_kind == "cavern":
        # Giant gate portal near edge with a carved open approach path.
        side = rng.choice(["left", "right", "top", "bottom"])
        if side in ("left", "right"):
            x = 6 if side == "left" else (w - 7)
            y = rng.randrange(10, h - 10)
        else:
            x = rng.randrange(10, w - 10)
            y = 6 if side == "top" else (h - 7)
        # clear gate opening and flanks
        for yy in range(y - 2, y + 3):
            for xx in range(x - 2, x + 3):
                if 1 <= xx < w - 1 and 1 <= yy < h - 1:
                    grid[yy][xx] = 0
        for off in range(-6, 7):
            gx = x + (0 if side in ("left", "right") else off)
            gy = y + (off if side in ("left", "right") else 0)
            if 1 <= gx < w - 1 and 1 <= gy < h - 1 and abs(off) >= 3:
                grid[gy][gx] = 1

        sx, sy = int(spawn[0]), int(spawn[1])
        # Carve a broad path from spawn to gate.
        steps = max(abs(x - sx), abs(y - sy))
        for i in range(steps + 1):
            t = i / max(1, steps)
            cx = int(round(lerp(sx, x, t)))
            cy = int(round(lerp(sy, y, t)))
            for yy in range(cy - 2, cy + 3):
                for xx in range(cx - 2, cx + 3):
                    if 1 <= xx < w - 1 and 1 <= yy < h - 1:
                        grid[yy][xx] = 0
        portals.append(Portal(x=x + 0.5, y=y + 0.5, target_world=target))

    tries = 0
    while len(portals) < 2 and tries < 5000:
        tries += 1
        x = rng.randrange(6, w - 6) + 0.5
        y = rng.randrange(6, h - 6) + 0.5
        if is_wall(grid, int(x), int(y)):
            continue
        portals.append(Portal(x=x, y=y, target_world=target))
    return portals


def reset_world(world_kind="cavern", difficulty_level=1):
    grid, style_map, spawn, seed = gen_world(world_kind)
    enemies = spawn_enemies(grid, spawn, ENEMY_COUNT, seed, difficulty_level)
    pickups = spawn_pickups(grid, spawn, 9, seed)
    powerups = spawn_powerups(grid, spawn, 1, seed)
    portals = []
    rng = random.Random(seed + 444)
    vulnerability = list(range(9))
    rng.shuffle(vulnerability)
    return grid, style_map, spawn, seed, enemies, pickups, powerups, portals, vulnerability, world_kind


def save_bootstrap_world_cache(grid, style_map, spawn, seed, world_kind, difficulty_level):
    os.makedirs(ASSET_CACHE_DIR, exist_ok=True)
    cache_path = os.path.join(ASSET_CACHE_DIR, "bootstrap_world.json")
    payload = {
        "grid": grid,
        "style_map": style_map,
        "spawn": [float(spawn[0]), float(spawn[1])],
        "seed": int(seed),
        "world_kind": str(world_kind),
        "difficulty_level": int(difficulty_level),
    }
    try:
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(payload, f)
    except Exception:
        pass


def load_bootstrap_world_cache():
    cache_path = os.path.join(ASSET_CACHE_DIR, "bootstrap_world.json")
    if not os.path.exists(cache_path):
        return None
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        grid = payload.get("grid")
        style_map = payload.get("style_map")
        spawn = payload.get("spawn")
        if not isinstance(grid, list) or not isinstance(style_map, list) or not isinstance(spawn, list):
            return None
        if len(grid) != MAP_H or len(style_map) != MAP_H:
            return None
        if any(len(row) != MAP_W for row in grid) or any(len(row) != MAP_W for row in style_map):
            return None
        world_kind = payload.get("world_kind", "cavern")
        seed = int(payload.get("seed", 1))
        difficulty_level = int(payload.get("difficulty_level", 1))
        return grid, style_map, (float(spawn[0]), float(spawn[1])), seed, world_kind, difficulty_level
    except Exception:
        return None


def try_fire_weapon(weapon, weapon_idx, px, py, pa, enemies, grid, fx_list, vulnerability, darkness=0.0):
    def play_impact_sound(hx, hy):
        if not weapon.impact_sfx or not pygame.mixer.get_init():
            return
        rel = wrap_pi(math.atan2(hy - py, hx - px) - pa)
        pan = clamp(rel / (math.pi / 2.0), -1.0, 1.0)
        dist = max(0.001, math.hypot(hx - px, hy - py))
        att = clamp(1.0 - dist / 30.0, 0.0, 1.0) ** 1.45
        vol = clamp(0.48 * att, 0.03, 0.42)
        left = vol * (1.0 - max(0.0, pan))
        right = vol * (1.0 + min(0.0, pan))
        ch = pygame.mixer.find_channel()
        if ch is None:
            weapon.impact_sfx.set_volume(vol)
            weapon.impact_sfx.play()
        else:
            ch.set_volume(left, right)
            ch.play(weapon.impact_sfx)

    def try_enemy_evade(en, rdx, rdy):
        # Teleport dodge sideways if there is room.
        side = random.choice((-1.0, 1.0))
        pdx = -rdy * side
        pdy = rdx * side
        step = random.uniform(1.1, 1.9)
        tx = en.x + pdx * step
        ty = en.y + pdy * step
        if is_wall(grid, int(tx), int(ty)):
            tx = en.x - pdx * step
            ty = en.y - pdy * step
        if is_wall(grid, int(tx), int(ty)):
            return False
        en.x, en.y = tx, ty
        return True

    def apply_one_shot(ang, damage_div=6, hit_width=0.36, pierce=False):
        rdx, rdy = math.cos(ang), math.sin(ang)
        wall_dist, _, _, _ = cast_ray(grid, px, py, rdx, rdy)

        hx = px + rdx * wall_dist
        hy = py + rdy * wall_dist

        if pierce:
            hits = []
            for en in enemies:
                if en.hp <= 0:
                    continue
                dx, dy = en.x - px, en.y - py
                proj = dx * rdx + dy * rdy
                if proj <= 0.0 or proj >= wall_dist:
                    continue
                perp = abs(dx * rdy - dy * rdx)
                if perp < hit_width:
                    hits.append((proj, en))
            hits.sort(key=lambda t: t[0])
            for _, en in hits:
                if vulnerability[en.kind] == weapon_idx:
                    en.hp = 0
                else:
                    en.hp -= max(4, weapon.damage // damage_div)
            return hx, hy

        best_enemy = None
        best_dist = wall_dist
        for en in enemies:
            if en.hp <= 0:
                continue
            dx, dy = en.x - px, en.y - py
            proj = dx * rdx + dy * rdy
            if proj <= 0.0 or proj >= best_dist:
                continue
            perp = abs(dx * rdy - dy * rdx)
            if perp < hit_width:
                best_dist = proj
                best_enemy = en

        hx = px + rdx * best_dist
        hy = py + rdy * best_dist
        if best_enemy is not None:
            if random.random() < 0.32 and try_enemy_evade(best_enemy, rdx, rdy):
                return hx, hy
            if vulnerability[best_enemy.kind] == weapon_idx:
                best_enemy.hp = 0
            else:
                best_enemy.hp -= max(4, weapon.damage // damage_div)
        return hx, hy

    spread = random.uniform(-weapon.spread, weapon.spread) * (1.0 + darkness * 1.35)

    if weapon.idx == 1:
        hx, hy = apply_one_shot(pa + spread, damage_div=7, hit_width=0.34)
        fx_list.append({"kind": "muzzle", "ttl": 0.07, "max": 0.07, "weapon": weapon})
        fx_list.append({"kind": "energy_broken", "ttl": 0.11, "max": 0.11, "weapon": weapon})
        fx_list.append({"kind": "impact", "ttl": 0.12, "max": 0.12, "weapon": weapon, "x": hx, "y": hy})
        play_impact_sound(hx, hy)
        return

    # Weapon 4 behaves like a shotgun (multiple pellets + wider cone).
    if weapon.idx == 4:
        fx_list.append({"kind": "muzzle", "ttl": 0.09, "max": 0.09, "weapon": weapon})
        fx_list.append({"kind": "energy", "ttl": 0.06, "max": 0.06, "weapon": weapon})
        pellet_offsets = [-0.085, -0.055, -0.025, 0.0, 0.025, 0.055, 0.085]
        impacts = []
        for off in pellet_offsets:
            ang = pa + spread + off
            hx, hy = apply_one_shot(ang, damage_div=10, hit_width=0.44)
            impacts.append((hx, hy, off))
            fx_list.append({"kind": "bullet_pellet", "ttl": 0.08, "max": 0.08, "weapon": weapon, "off": off})
        for hx, hy, _ in impacts:
            fx_list.append({"kind": "impact", "ttl": 0.12, "max": 0.12, "weapon": weapon, "x": hx, "y": hy})
            play_impact_sound(hx, hy)
        return
    if weapon.idx == 2:
        hx, hy = apply_one_shot(pa + spread, damage_div=4, hit_width=0.55, pierce=True)
        fx_list.append({"kind": "muzzle", "ttl": 0.10, "max": 0.10, "weapon": weapon})
        fx_list.append({"kind": "energy_plasma", "ttl": 0.16, "max": 0.16, "weapon": weapon})
        fx_list.append({"kind": "impact", "ttl": 0.18, "max": 0.18, "weapon": weapon, "x": hx, "y": hy})
        play_impact_sound(hx, hy)
        return

    if weapon.idx == 3:
        hx, hy = apply_one_shot(pa + spread, damage_div=5, hit_width=0.42)
        fx_list.append({"kind": "muzzle", "ttl": 0.09, "max": 0.09, "weapon": weapon})
        fx_list.append({"kind": "energy_triple", "ttl": 0.14, "max": 0.14, "weapon": weapon})
        fx_list.append({"kind": "impact", "ttl": 0.15, "max": 0.15, "weapon": weapon, "x": hx, "y": hy})
        play_impact_sound(hx, hy)
        return

    if weapon.idx == 5:
        hx, hy = apply_one_shot(pa + spread, damage_div=5, hit_width=0.40)
        fx_list.append({"kind": "muzzle", "ttl": 0.09, "max": 0.09, "weapon": weapon})
        fx_list.append({"kind": "energy_vector_cube", "ttl": 0.16, "max": 0.16, "weapon": weapon})
        fx_list.append({"kind": "impact", "ttl": 0.14, "max": 0.14, "weapon": weapon, "x": hx, "y": hy})
        play_impact_sound(hx, hy)
        return

    if weapon.idx == 6:
        hx, hy = apply_one_shot(pa + spread, damage_div=4, hit_width=0.45)
        fx_list.append({"kind": "muzzle", "ttl": 0.10, "max": 0.10, "weapon": weapon})
        fx_list.append({"kind": "energy_tri_spin", "ttl": 0.15, "max": 0.15, "weapon": weapon})
        fx_list.append({"kind": "impact", "ttl": 0.14, "max": 0.14, "weapon": weapon, "x": hx, "y": hy})
        play_impact_sound(hx, hy)
        return

    if weapon.idx == 7:
        hx, hy = apply_one_shot(pa + spread, damage_div=5, hit_width=0.50, pierce=True)
        fx_list.append({"kind": "muzzle", "ttl": 0.08, "max": 0.08, "weapon": weapon})
        fx_list.append({"kind": "energy_hold_laser", "ttl": 0.12, "max": 0.12, "weapon": weapon})
        fx_list.append({"kind": "impact", "ttl": 0.10, "max": 0.10, "weapon": weapon, "x": hx, "y": hy})
        play_impact_sound(hx, hy)
        return

    if weapon.idx == 9:
        hx, hy = apply_one_shot(pa + spread, damage_div=2, hit_width=0.72, pierce=True)
        fx_list.append({"kind": "muzzle", "ttl": 0.07, "max": 0.07, "weapon": weapon})
        fx_list.append({"kind": "energy_hellbeam", "ttl": 0.12, "max": 0.12, "weapon": weapon})
        fx_list.append({"kind": "impact", "ttl": 0.10, "max": 0.10, "weapon": weapon, "x": hx, "y": hy})
        play_impact_sound(hx, hy)
        return

    fire_ang = pa + spread
    hx, hy = apply_one_shot(fire_ang)
    fx_list.append({"kind": "muzzle", "ttl": 0.08, "max": 0.08, "weapon": weapon})
    fx_list.append({"kind": "energy", "ttl": 0.12, "max": 0.12, "weapon": weapon})
    fx_list.append({"kind": "bullet", "ttl": 0.10, "max": 0.10, "weapon": weapon})
    fx_list.append({"kind": "impact", "ttl": 0.16, "max": 0.16, "weapon": weapon, "x": hx, "y": hy})
    play_impact_sound(hx, hy)


def run_radar_session(capture_frame=None):
    pygame.init()
    ensure_asset_folders()
    pygame.display.set_caption("Radar Hell")
    win = pygame.display.set_mode((VIRTUAL_W, VIRTUAL_H), pygame.RESIZABLE | pygame.DOUBLEBUF)
    presenter = Presenter(win)

    try:
        pygame.mixer.init(frequency=22050, size=-16, channels=2)
    except Exception:
        pass

    pygame.mouse.set_visible(False)
    pygame.event.set_grab(True)

    clock = pygame.time.Clock()
    font = pygame.font.SysFont("consolas", 22)
    small = pygame.font.SysFont("consolas", 18)
    title_font = pygame.font.SysFont("consolas", 52, bold=True)

    def window_to_virtual(pos):
        return cover_window_to_virtual(presenter.win.get_size(), pos, (VIRTUAL_W, VIRTUAL_H))

    def set_pause_mouse(enabled):
        pygame.mouse.set_visible(enabled)
        pygame.event.set_grab(not enabled)
        pygame.mouse.get_rel()

    pause_buttons = [
        ("RESUME", pygame.Rect(VIRTUAL_W // 2 - 230, VIRTUAL_H // 2 + 28, 460, 58), "resume"),
        ("HEAVEN VS HELL", pygame.Rect(VIRTUAL_W // 2 - 230, VIRTUAL_H // 2 + 102, 460, 58), "launch_hvh2"),
        ("BOOK OF BLOOD", pygame.Rect(VIRTUAL_W // 2 - 230, VIRTUAL_H // 2 + 176, 460, 58), "launch_book"),
        ("QUIT", pygame.Rect(VIRTUAL_W // 2 - 230, VIRTUAL_H // 2 + 250, 460, 58), "quit"),
    ]

    render_sizes = [(800, 450), (960, 540), (1280, 720)]
    view = pygame.Surface(render_sizes[0]).convert()
    virtual = pygame.Surface((VIRTUAL_W, VIRTUAL_H)).convert()
    scanline_surf = pygame.Surface((VIRTUAL_W, VIRTUAL_H), pygame.SRCALPHA)
    for y in range(0, VIRTUAL_H, 3):
        pygame.draw.line(scanline_surf, (0, 0, 0, 60), (0, y), (VIRTUAL_W, y), 1)
    grain_surf = pygame.Surface((VIRTUAL_W, VIRTUAL_H), pygame.SRCALPHA)
    for gy in range(0, VIRTUAL_H, 2):
        for gx in range(0, VIRTUAL_W, 2):
            a = random.randint(8, 18)
            grain_surf.fill((0, 0, 0, a), pygame.Rect(gx, gy, 2, 2))
    nv_overlay_full = pygame.Surface((VIRTUAL_W, VIRTUAL_H), pygame.SRCALPHA)
    lightning_overlay_full = pygame.Surface((VIRTUAL_W, VIRTUAL_H), pygame.SRCALPHA)
    rain_overlay = pygame.Surface(render_sizes[1], pygame.SRCALPHA)

    def draw_loading_overlay(progress, fade=1.0, animate=0.0):
        progress = clamp(progress, 0.0, 1.0)
        alpha = int(255 * clamp(fade, 0.0, 1.0))
        virtual.fill((6, 0, 0))
        panel = pygame.Surface((1160, 620), pygame.SRCALPHA)
        panel.fill((0, 0, 0, int(205 * fade)))
        pygame.draw.rect(panel, (170, 50, 50, alpha), panel.get_rect(), 2)
        title = font.render("RADAR HELL", True, (200, 30, 30))
        tx = VIRTUAL_W // 2 - title.get_width() // 2
        ty = max(24, VIRTUAL_H // 2 - 380)
        virtual.blit(title, (tx, ty))
        for i in range(60):
            if i % 3:
                continue
            dx = tx + (i * 13) % max(1, title.get_width())
            dy = ty + title.get_height() + int((i * 7) % 18)
            pygame.draw.circle(virtual, (130, 10, 10), (dx, dy), 2)

        lines = [
            "LOADING / CONTROLS",
            "WASD move, Mouse look, Shift sprint",
            "LMB hold to fire, TAB next weapon, 1-9 direct weapon slots",
            "SPACE sonar pulse reveals nearby geometry and alerts the beast",
            "Night Vision overcharges the whole scene and also makes the beast track you",
            "Walk/sprint noise also attracts the beast; sneaking keeps you quieter",
            "Weapons and ammo are pickups on the ground",
            "ESC opens the mode menu for Heaven vs Hell and Book of Blood",
            "F1 minimap, H help, F2 quality, F3 scanlines, F11 fullscreen",
        ]
        for i, line in enumerate(lines):
            col = (235, 175, 175) if i == 0 else (220, 132, 132)
            panel.blit(font.render(line, True, col), (26, 24 + i * 54))
        bw, bh = 920, 24
        bx = panel.get_width() // 2 - bw // 2
        by = panel.get_height() - 78
        pygame.draw.rect(panel, (70, 20, 20), pygame.Rect(bx, by, bw, bh), border_radius=4)
        n = int(time.perf_counter() * 180) % max(1, bw)
        anim_prog = clamp(progress - 0.06 + 0.12 * (n / max(1, bw)), 0.0, 1.0)
        pygame.draw.rect(panel, (210, 58, 58), pygame.Rect(bx, by, int(bw * anim_prog), bh), border_radius=4)
        virtual.blit(panel, (VIRTUAL_W // 2 - panel.get_width() // 2, VIRTUAL_H // 2 - panel.get_height() // 2))
        presenter.present_cover(virtual)
        pygame.display.flip()
        pygame.event.pump()
        if animate > 0.0:
            end_t = time.perf_counter() + animate
            while time.perf_counter() < end_t:
                pygame.time.wait(16)
                pygame.event.pump()

    draw_loading_overlay(0.06)
    weapons = build_weapons()
    draw_loading_overlay(0.30)
    enemy_anim = build_enemy_sprites()
    draw_loading_overlay(0.45)
    marker_assets = build_marker_assets(weapons)
    draw_loading_overlay(0.60)
    surface_textures = build_surface_textures(seed=1313)
    sky_src = marker_assets["sky"]
    sky_cache = LRUCache(16)
    skyline_cache = LRUCache(24)
    enemy_scale_cache = LRUCache(220)
    text_cache = LRUCache(280)
    sprite_scale_cache = LRUCache(320)
    terrain_chunk_cache = LRUCache(220)
    weapon_pose_cache = [LRUCache(72) for _ in range(9)]

    difficulty_level = 1
    cached_bootstrap = load_bootstrap_world_cache()
    if cached_bootstrap is not None:
        grid, style_map, spawn, seed, world_kind, difficulty_level = cached_bootstrap
        enemies = spawn_enemies(grid, spawn, ENEMY_COUNT, seed, difficulty_level)
        pickups = spawn_pickups(grid, spawn, 9, seed)
        powerups = spawn_powerups(grid, spawn, 1, seed)
        portals = []
        rng = random.Random(seed + 444)
        vulnerability = list(range(9))
        rng.shuffle(vulnerability)
    else:
        grid, style_map, spawn, seed, enemies, pickups, powerups, portals, vulnerability, world_kind = reset_world("cavern", difficulty_level)
        save_bootstrap_world_cache(grid, style_map, spawn, seed, world_kind, difficulty_level)
    draw_loading_overlay(0.82)
    _spike_tiles, symbol_tiles, stair_tiles, tooth_tiles = build_world_features(grid, seed)
    minimap_base = build_minimap_base(grid, scale=2)
    px, py = spawn
    pa = 0.0

    sonar = Sonar()

    weapon_idx = 0
    inventory = [True] * 9
    ammo = [AMMO_MAX] * 9

    show_map = False
    show_help = False
    show_help_until = 0.0
    quality = 0
    last_quality = quality
    show_scanlines = False
    auto_quality_until = time.perf_counter() + 2.5
    auto_quality_enabled = False

    last_shot = -999.0
    recoil_amt = 0.0
    shot_fx = []
    obsidian_rounds = []
    walk_t = 0.0
    night_vision_until = 0.0
    gun_look_x = 0.0
    look_pitch = 0.0
    shot_light_until = -999.0
    shot_light_color = (255, 180, 120)
    contact_flash_until = -999.0
    blood_font_phase = 0.0
    world_rng = random.Random(seed + sum(ord(c) for c in world_kind) * 13)
    world_tint = (world_rng.uniform(0.88, 1.12), world_rng.uniform(0.86, 1.10), world_rng.uniform(0.86, 1.12))

    weather_mode = "clear"
    next_storm_t = time.perf_counter() + random.uniform(22.0, 46.0)
    storm_until = -999.0
    next_lightning_t = -999.0
    lightning_flash_until = -999.0
    lightning_room_until = -999.0
    lightning_true_color_until = -999.0
    next_random_bolt_t = time.perf_counter() + random.uniform(8.0, 20.0)
    active_bolts = []
    rain_drops = [[random.uniform(0.8, MAP_W - 0.8), random.uniform(0.8, MAP_H - 0.8), random.uniform(7.0, 13.0), random.uniform(0.08, 0.20)] for _ in range(220)]
    weather_channel = pygame.mixer.Channel(5) if pygame.mixer.get_init() else None
    ambience_channel = pygame.mixer.Channel(6) if pygame.mixer.get_init() else None
    step_channel = pygame.mixer.Channel(7) if pygame.mixer.get_init() else None
    enemy_blur_history = {}

    monster_alive_variants, monster_death_variants = build_monster_sfx()
    monster_alive_cycle = []
    monster_death_cycle = []
    enemy_voice_next = time.perf_counter() + random.uniform(30.0, 50.0)
    enemy_attack_sfx_next = 0.0
    radar_sfx = load_sound_candidates([
        os.path.join(ASSET_SFX_RADAR_DIR, "radar_ping.mp3"),
        os.path.join(ASSET_SFX_RADAR_DIR, "radar_ping.wav"),
    ], default=None, volume=0.46)
    monster_attack_sfx = load_sound_candidates([
        os.path.join(ASSET_SFX_MONSTER_DIR, "monster_attack.mp3"),
        os.path.join(ASSET_SFX_MONSTER_DIR, "monster_attack.wav"),
    ], default=None, volume=0.50)
    ambient_rain_sfx = load_sound_candidates([os.path.join(ASSET_SFX_AMBIENT_DIR, "rain_loop.mp3")], default=None, volume=0.28)
    ambient_storm_sfx = load_sound_candidates([os.path.join(ASSET_SFX_AMBIENT_DIR, "storm_loop.mp3")], default=None, volume=0.32)

    def load_sound_folder(folder, volume=0.35):
        items = []
        if not pygame.mixer.get_init():
            return items
        try:
            names = sorted(os.listdir(folder))
        except Exception:
            names = []
        for nm in names:
            if not nm.lower().endswith('.mp3'):
                continue
            snd = load_sound_candidates([os.path.join(folder, nm)], default=None, volume=volume)
            if snd:
                items.append(snd)
        return items

    ambience_tracks = load_sound_folder(ASSET_SFX_AMBIENCE_DIR, volume=0.26)
    ambience_cycle = []
    step_walk_sfx = load_sound_folder(ASSET_SFX_STEP_WALK_DIR, volume=0.30)
    step_sneak_sfx = load_sound_folder(ASSET_SFX_STEP_SNEAK_DIR, volume=0.18)
    step_sprint_sfx = load_sound_folder(ASSET_SFX_STEP_SPRINT_DIR, volume=0.36)
    step_ticker = 0.0
    ai_think_accum = 0.0
    enemy_alert_until = 0.0
    step_noise_until = 0.0

    def play_ambience_tick():
        nonlocal ambience_cycle
        if ambience_channel is None or not ambience_tracks:
            return
        if ambience_channel.get_busy():
            return
        if not ambience_cycle:
            ambience_cycle = list(range(len(ambience_tracks)))
            random.shuffle(ambience_cycle)
        idx = ambience_cycle.pop()
        ambience_channel.play(ambience_tracks[idx])

    draw_loading_overlay(1.0)
    loading_help_fade_until = time.perf_counter() + 0.35

    def play_spatial_sound(sound, sx, sy, base_gain=0.48, max_dist=24.0):
        if not sound or not pygame.mixer.get_init():
            return
        dx = sx - px
        dy = sy - py
        dist = math.hypot(dx, dy)
        rel = wrap_pi(math.atan2(dy, dx) - pa)
        pan = clamp(rel / (math.pi / 2.0), -1.0, 1.0)
        att = clamp(1.0 - dist / max_dist, 0.0, 1.0) ** 1.35
        vol = clamp(base_gain * att, 0.02, base_gain)
        left = vol * (1.0 - max(0.0, pan))
        right = vol * (1.0 + min(0.0, pan))
        ch = pygame.mixer.find_channel()
        if ch is None:
            sound.set_volume(vol)
            sound.play()
        else:
            ch.set_volume(left, right)
            ch.play(sound)

    def play_center_sound(sound, volume=0.42):
        if not sound or not pygame.mixer.get_init():
            return
        ch = pygame.mixer.find_channel()
        if ch is None:
            sound.set_volume(volume)
            sound.play()
        else:
            ch.set_volume(volume, volume)
            ch.play(sound)

    def render_text_cached(font_obj, text, color):
        key = (id(font_obj), text, color)
        surf = text_cache.get(key)
        if surf is None:
            surf = font_obj.render(text, True, color)
            text_cache.set(key, surf)
        return surf

    def scale_sprite_cached(src, w, h):
        key = (id(src), int(w), int(h))
        spr = sprite_scale_cache.get(key)
        if spr is None:
            spr = pygame.transform.smoothscale(src, (int(w), int(h)))
            sprite_scale_cache.set(key, spr)
        return spr

    def sample_terrain_cached(kind, wx, wy):
        cx = int(math.floor(wx / TERRAIN_CHUNK_TILES))
        cy = int(math.floor(wy / TERRAIN_CHUNK_TILES))
        key = (kind, cx, cy)
        chunk = terrain_chunk_cache.get(key)
        if chunk is None:
            chunk = build_terrain_chunk_surface(style_map, surface_textures, cx, cy, kind)
            terrain_chunk_cache.set(key, chunk)
        lx = wx - cx * TERRAIN_CHUNK_TILES
        ly = wy - cy * TERRAIN_CHUNK_TILES
        u = int(clamp(lx / TERRAIN_CHUNK_TILES, 0.0, 0.999) * (TERRAIN_CHUNK_PX - 1))
        v = int(clamp(ly / TERRAIN_CHUNK_TILES, 0.0, 0.999) * (TERRAIN_CHUNK_PX - 1))
        return chunk.get_at((u, v))

    def set_weather_audio(mode):
        if weather_channel is None:
            return
        if mode == "rain" and ambient_rain_sfx:
            if weather_channel.get_sound() != ambient_rain_sfx:
                weather_channel.play(ambient_rain_sfx, loops=-1)
        elif mode == "storm" and ambient_storm_sfx:
            if weather_channel.get_sound() != ambient_storm_sfx:
                weather_channel.play(ambient_storm_sfx, loops=-1)
        else:
            weather_channel.stop()

    def spawn_lightning_bolt(now_t, storm=False):
        ox = random.randint(int(w * 0.10), int(w * 0.90))
        oy = -random.randint(8, 28)
        segs = []
        frontier = [(ox, oy, random.uniform(0.8, 1.35), random.uniform(14, 24), 0)]
        while frontier and len(segs) < 220:
            x, y, ang, seg_len, depth = frontier.pop(0)
            nx = x + math.cos(ang) * seg_len
            ny = y + math.sin(ang) * seg_len
            segs.append((x, y, nx, ny, depth))
            if ny > half_h * 0.9 or depth > 4:
                continue
            frontier.append((nx, ny, ang + random.uniform(-0.20, 0.20), seg_len * random.uniform(0.80, 0.94), depth + 1))
            branch_chance = 0.55 - depth * 0.10 + (0.12 if storm else 0.0)
            if random.random() < max(0.10, branch_chance):
                frontier.append((nx, ny, ang + random.uniform(-1.05, -0.35), seg_len * random.uniform(0.65, 0.88), depth + 1))
            if random.random() < max(0.08, branch_chance - 0.05):
                frontier.append((nx, ny, ang + random.uniform(0.35, 1.05), seg_len * random.uniform(0.65, 0.88), depth + 1))
        active_bolts.append({"t0": now_t, "ttl": random.uniform(0.60, 1.25), "segs": segs})

    def draw_bolts_behind_walls(dst, now_t):
        alive = []
        for b in active_bolts:
            age = now_t - b["t0"]
            if age >= b["ttl"]:
                continue
            alive.append(b)
            prog = clamp(age / max(0.001, b["ttl"]), 0.0, 1.0)
            vis_n = max(2, int(len(b["segs"]) * min(1.0, prog * 1.35)))
            fade = 1.0 - prog
            for i in range(vis_n):
                x0, y0, x1, y1, depth = b["segs"][i]
                col = (170 + depth * 8, 20 + depth * 4, 22 + depth * 4, int((150 - depth * 20) * fade))
                pygame.draw.line(dst, col, (int(x0), int(y0)), (int(x1), int(y1)), max(1, 2 - depth // 2))
        active_bolts[:] = alive

    def blit_enemy_with_blend(dst, base_frames, attack_frames, eye_points, sx, sy, size, alpha, frame_t, shadow_t=0.0, flip_x=False, attack_mix=0.0):
        def resolve_pair(frames, local_t):
            count = max(1, len(frames))
            f0 = int(local_t) % count
            f1 = (f0 + 1) % count
            lerp_t = local_t - int(local_t)
            key0 = (id(frames), f0, ck, int(flip_x))
            key1 = (id(frames), f1, ck, int(flip_x))
            spr0 = enemy_scale_cache.get(key0)
            if spr0 is None:
                spr0 = pygame.transform.smoothscale(frames[f0], (ck, ck))
                if flip_x:
                    spr0 = pygame.transform.flip(spr0, True, False)
                enemy_scale_cache.set(key0, spr0)
            spr1 = enemy_scale_cache.get(key1)
            if spr1 is None:
                spr1 = pygame.transform.smoothscale(frames[f1], (ck, ck))
                if flip_x:
                    spr1 = pygame.transform.flip(spr1, True, False)
                enemy_scale_cache.set(key1, spr1)
            return f0, f1, lerp_t, spr0, spr1

        ck = max(16, min(420, (size // 4) * 4))
        draw_x = sx - ck // 2
        draw_y = sy - ck // 2

        b0, b1, bt, bs0, bs1 = resolve_pair(base_frames, frame_t)
        at_frames = attack_frames if attack_frames else base_frames
        a0, a1, at, as0, as1 = resolve_pair(at_frames, frame_t * 1.17 + 1.3)

        # Shadow blur transition to blend movement frames.
        sh_alpha = int(alpha * (0.14 + 0.20 * clamp(shadow_t, 0.0, 1.0)))
        if sh_alpha > 8:
            sh0 = bs0.copy(); sh0.set_alpha(sh_alpha)
            sh1 = bs1.copy(); sh1.set_alpha(sh_alpha)
            for ox, oy in ((2, 2), (3, 2), (2, 3), (4, 3)):
                dst.blit(sh0, (draw_x + ox, draw_y + oy))
                dst.blit(sh1, (draw_x + ox + 1, draw_y + oy + 1))

        move_mul = 1.0 - clamp(attack_mix, 0.0, 1.0)
        atk_mul = clamp(attack_mix, 0.0, 1.0)

        a_bs0 = int(alpha * (1.0 - bt) * move_mul)
        a_bs1 = int(alpha * bt * move_mul)
        a_as0 = int(alpha * (1.0 - at) * atk_mul)
        a_as1 = int(alpha * at * atk_mul)

        ghost_mask = pygame.Surface((ck, ck), pygame.SRCALPHA)
        for gy in range(ck):
            fade = 1.0 if gy < int(ck * 0.48) else clamp(1.0 - ((gy - ck * 0.48) / max(1.0, ck * 0.52)) * 0.78, 0.18, 1.0)
            ga = int(255 * fade)
            pygame.draw.line(ghost_mask, (255, 255, 255, ga), (0, gy), (ck, gy))

        if a_bs0 > 0:
            d = bs0.copy(); d.blit(ghost_mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT); d.set_alpha(a_bs0); dst.blit(d, (draw_x, draw_y))
        if a_bs1 > 0:
            d = bs1.copy(); d.blit(ghost_mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT); d.set_alpha(a_bs1); dst.blit(d, (draw_x, draw_y))
        if a_as0 > 0:
            d = as0.copy(); d.blit(ghost_mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT); d.set_alpha(a_as0); dst.blit(d, (draw_x, draw_y))
        if a_as1 > 0:
            d = as1.copy(); d.blit(ghost_mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT); d.set_alpha(a_as1); dst.blit(d, (draw_x, draw_y))

        # Red-eye drip effect.
        eyes = eye_points[b0] if b0 < len(eye_points) else []
        if eyes and alpha > 22:
            drip = pygame.Surface((ck, ck), pygame.SRCALPHA)
            sx_scale = ck / max(1, base_frames[b0].get_width())
            sy_scale = ck / max(1, base_frames[b0].get_height())
            pulse = 0.5 + 0.5 * math.sin(now * 8.0 + frame_t * 0.5)
            for i, (ex, ey) in enumerate(eyes):
                if i % 3 != int(now * 7.0) % 3:
                    continue
                x = int(ex * sx_scale)
                y = int(ey * sy_scale)
                dl = 1 + int((0.5 + 0.5 * math.sin(now * 6.0 + i * 0.7)) * 8)
                col = (180 + int(60 * pulse), 18, 18, min(220, alpha))
                pygame.draw.line(drip, col, (x, y), (x, min(ck - 1, y + dl)), 1)
                pygame.draw.circle(drip, (220, 30, 30, min(235, alpha)), (x, min(ck - 1, y + dl)), 1)
            dst.blit(drip, (draw_x, draw_y), special_flags=pygame.BLEND_RGBA_ADD)

    running = True
    paused = False
    exit_reason = "quit"
    captured_once = False
    prof_update_ms = 0.0
    prof_render_ms = 0.0
    prof_accum = 0.0

    def handle_escape_default():
        nonlocal paused, exit_reason, running
        if not paused:
            paused = True
            set_pause_mouse(True)
        else:
            exit_reason = "quit"
            running = False

    while running:
        frame_t0 = time.perf_counter()
        dt = min(clock.tick(60) / 1000.0, 1 / 20)
        did_ping = False
        did_fire = False
        if _HOLOVERSE_RUNTIME is not None:
            _HOLOVERSE_RUNTIME.poll_return_to_core()
            _HOLOVERSE_RUNTIME.poll_embedded_escape_hold()

        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                running = False
            elif e.type == pygame.VIDEORESIZE:
                presenter.resize(e.w, e.h)
            elif paused and e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                vpos = window_to_virtual(e.pos)
                if vpos is not None:
                    for _label, _rect, _action in pause_buttons:
                        if _rect.collidepoint(vpos):
                            if _action == "resume":
                                paused = False
                                set_pause_mouse(False)
                            elif _action == "quit":
                                exit_reason = "quit"
                                running = False
                            else:
                                exit_reason = _action
                                running = False
                            break
            elif e.type == pygame.KEYUP:
                if e.key == pygame.K_ESCAPE and _HOLOVERSE_RUNTIME is not None:
                    _HOLOVERSE_RUNTIME.embedded_escape_released()
            elif e.type == pygame.KEYDOWN:
                if e.key == pygame.K_ESCAPE:
                    if _HOLOVERSE_RUNTIME is not None and _HOLOVERSE_RUNTIME.embedded_mode():
                        _HOLOVERSE_RUNTIME.embedded_escape_pressed(handle_escape_default)
                    else:
                        handle_escape_default()
                elif e.key == pygame.K_F11 or (e.key == pygame.K_RETURN and (pygame.key.get_mods() & pygame.KMOD_ALT)):
                    presenter.toggle_fullscreen()
                elif e.key == pygame.K_SPACE:
                    did_ping = sonar.ping()
                    if did_ping:
                        play_center_sound(radar_sfx, volume=0.42)
                elif e.key == pygame.K_r:
                    grid, style_map, spawn, seed, enemies, pickups, powerups, portals, vulnerability, world_kind = reset_world(world_kind, difficulty_level)
                    _spike_tiles, symbol_tiles, stair_tiles, tooth_tiles = build_world_features(grid, seed)
                    world_rng = random.Random(seed + sum(ord(c) for c in world_kind) * 13)
                    world_tint = (world_rng.uniform(0.88, 1.12), world_rng.uniform(0.86, 1.10), world_rng.uniform(0.86, 1.12))
                    minimap_base = build_minimap_base(grid, scale=2)
                    px, py = spawn
                    pa = 0.0
                    save_bootstrap_world_cache(grid, style_map, spawn, seed, world_kind, difficulty_level)
                elif e.key == pygame.K_F1:
                    show_map = not show_map
                elif e.key == pygame.K_h:
                    show_help = True
                    show_help_until = time.perf_counter() + 4.0
                elif e.key == pygame.K_F2:
                    auto_quality_enabled = False
                    quality = (quality + 1) % 3
                    if quality != last_quality:
                        view = pygame.Surface(render_sizes[quality]).convert()
                        rain_overlay = pygame.Surface(render_sizes[quality], pygame.SRCALPHA)
                        last_quality = quality
                elif e.key == pygame.K_F3:
                    show_scanlines = not show_scanlines
                elif e.key == pygame.K_TAB:
                    for off in range(1, 10):
                        nidx = (weapon_idx + off) % 9
                        if inventory[nidx]:
                            weapon_idx = nidx
                            break
                elif pygame.K_1 <= e.key <= pygame.K_9:
                    desired = e.key - pygame.K_1
                    if inventory[desired]:
                        weapon_idx = desired

        if paused:
            pause_panel = virtual.copy()
            dim = pygame.Surface((VIRTUAL_W, VIRTUAL_H), pygame.SRCALPHA)
            dim.fill((0, 0, 0, 150))
            pause_panel.blit(dim, (0, 0))
            frame = pygame.Surface((620, 410), pygame.SRCALPHA)
            frame.fill((8, 0, 0, 228))
            pygame.draw.rect(frame, (150, 32, 32), frame.get_rect(), 2, border_radius=18)
            pause_panel.blit(frame, (VIRTUAL_W // 2 - frame.get_width() // 2, VIRTUAL_H // 2 - 124))
            pause_text = title_font.render("RADAR HELL", True, (208, 48, 48))
            info_text = small.render("Resume the hunt or switch modes here: Heaven vs Hell / Book of Blood", True, (220, 150, 150))
            pause_panel.blit(pause_text, (VIRTUAL_W // 2 - pause_text.get_width() // 2, VIRTUAL_H // 2 - 104))
            pause_panel.blit(info_text, (VIRTUAL_W // 2 - info_text.get_width() // 2, VIRTUAL_H // 2 - 44))
            mouse_v = window_to_virtual(pygame.mouse.get_pos())
            for btn_label, btn_rect, btn_action in pause_buttons:
                hovered = mouse_v is not None and btn_rect.collidepoint(mouse_v)
                draw_host_button(pause_panel, btn_rect, btn_label, font, hovered=hovered, active=(btn_action == exit_reason))
            presenter.present_cover(pause_panel)
            clock.tick(30)
            continue
        elif pygame.mouse.get_visible():
            set_pause_mouse(False)

        mdx, mdy = pygame.mouse.get_rel()
        pa += mdx * MOUSE_SENS
        gun_look_x = clamp(gun_look_x * 0.86 + mdx * 0.65, -28.0, 28.0)
        look_pitch = clamp(look_pitch - mdy * 0.54, -190.0, 190.0)
        keys = pygame.key.get_pressed()
        turn = (-1.0 if keys[pygame.K_LEFT] else 0.0) + (1.0 if keys[pygame.K_RIGHT] else 0.0)
        pa += turn * TURN_SPEED * dt

        fx = math.cos(pa)
        fy = math.sin(pa)
        rx = -fy
        ry = fx

        sneaking = keys[pygame.K_c] or keys[pygame.K_LALT] or keys[pygame.K_RALT]
        sprinting = (keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]) and not sneaking
        speed_mul = 0.46 if sneaking else (SPRINT_MUL if sprinting else 1.0)
        speed = MOVE_SPEED * speed_mul
        mx = (1 if keys[pygame.K_w] else 0) - (1 if keys[pygame.K_s] else 0)
        my = (1 if keys[pygame.K_d] else 0) - (1 if keys[pygame.K_a] else 0)
        mvx = fx * mx + rx * my
        mvy = fy * mx + ry * my
        mag = math.hypot(mvx, mvy)
        moving = mag > 1e-6
        if moving:
            mvx, mvy = mvx / mag, mvy / mag
            walk_t += dt * (0.62 if sneaking else (1.35 if sprinting else 1.0))

        nx = px + mvx * speed * dt
        ny = py + mvy * speed * dt
        radius = 0.18
        if not is_wall(grid, int(nx + math.copysign(radius, mvx or 1.0)), int(py)):
            px = nx
        if not is_wall(grid, int(px), int(ny + math.copysign(radius, mvy or 1.0))):
            py = ny

        now = time.perf_counter()
        if auto_quality_enabled and now >= auto_quality_until:
            fps_now = clock.get_fps()
            if fps_now < 50.0 and quality > 0:
                quality -= 1
                view = pygame.Surface(render_sizes[quality]).convert()
                rain_overlay = pygame.Surface(render_sizes[quality], pygame.SRCALPHA)
                last_quality = quality
                auto_quality_until = now + 2.2
            elif fps_now > 59.0 and quality < 2:
                quality += 1
                view = pygame.Surface(render_sizes[quality]).convert()
                rain_overlay = pygame.Surface(render_sizes[quality], pygame.SRCALPHA)
                last_quality = quality
                auto_quality_until = now + 3.8
            else:
                auto_quality_until = now + 1.6
        play_ambience_tick()

        # movement sfx cadence
        step_ticker -= dt
        if moving and step_ticker <= 0.0:
            if sneaking and step_sneak_sfx:
                random.choice(step_sneak_sfx).play()
                step_ticker = random.uniform(0.68, 0.95)
            elif sprinting and step_sprint_sfx:
                random.choice(step_sprint_sfx).play()
                step_ticker = random.uniform(0.16, 0.25)
                step_noise_until = max(step_noise_until, now + 1.00)
            elif step_walk_sfx:
                random.choice(step_walk_sfx).play()
                step_ticker = random.uniform(0.30, 0.44)
                step_noise_until = max(step_noise_until, now + 0.55)
            elif not sneaking:
                step_ticker = random.uniform(0.30, 0.44)
                step_noise_until = max(step_noise_until, now + (0.95 if sprinting else 0.45))

        # Weather system: occasional rain/storm cycles + random red lightning bolts.
        if now >= next_storm_t and now >= storm_until:
            weather_mode = "storm" if random.random() < 0.45 else "rain"
            storm_until = now + random.uniform(11.0, 23.0)
            next_lightning_t = now + random.uniform(1.5, 4.8)
            set_weather_audio(weather_mode)
        if now >= storm_until and weather_mode != "clear":
            weather_mode = "clear"
            next_storm_t = now + random.uniform(20.0, 45.0)
            set_weather_audio("clear")

        bolt_triggered = False
        if weather_mode == "storm" and now >= next_lightning_t:
            spawn_lightning_bolt(now, storm=True)
            next_lightning_t = now + random.uniform(2.8, 6.8)
            bolt_triggered = True
        if now >= next_random_bolt_t:
            if random.random() < (0.32 if weather_mode == "storm" else 0.18):
                spawn_lightning_bolt(now, storm=(weather_mode == "storm"))
                bolt_triggered = True
            next_random_bolt_t = now + random.uniform(7.0, 20.0)
        if bolt_triggered:
            lightning_flash_until = now + random.uniform(0.42, 0.85)
            lightning_room_until = now + random.uniform(0.26, 0.48)
            lightning_true_color_until = now + random.uniform(0.35, 0.70)

        # Pickups
        next_pickups = []
        for p in pickups:
            if (p.x - px) ** 2 + (p.y - py) ** 2 <= 0.7 ** 2:
                if inventory[p.weapon_idx]:
                    ammo[p.weapon_idx] = min(AMMO_MAX, ammo[p.weapon_idx] + 60)
                else:
                    inventory[p.weapon_idx] = True
                    ammo[p.weapon_idx] = min(AMMO_MAX, ammo[p.weapon_idx] + 90)
                    weapon_idx = p.weapon_idx
                if weapons[p.weapon_idx].pickup_sfx:
                    weapons[p.weapon_idx].pickup_sfx.play()
            else:
                next_pickups.append(p)
        pickups = next_pickups

        # Powerups
        next_powerups = []
        for pu in powerups:
            if (pu.x - px) ** 2 + (pu.y - py) ** 2 <= 0.75 ** 2:
                if pu.kind == "nightvision":
                    night_vision_until = now + 30.0
            else:
                next_powerups.append(pu)
        powerups = next_powerups

        # Portals are disabled until the current monster is killed.
        if enemies and all(en.hp <= 0 for en in enemies):
            for portal in portals:
                if (portal.x - px) ** 2 + (portal.y - py) ** 2 <= 1.0 ** 2:
                    difficulty_level += 1
                    grid, style_map, spawn, seed, enemies, pickups, powerups, portals, vulnerability, world_kind = reset_world(portal.target_world, difficulty_level)
                    _spike_tiles, symbol_tiles, stair_tiles, tooth_tiles = build_world_features(grid, seed)
                    world_rng = random.Random(seed + sum(ord(c) for c in world_kind) * 13)
                    world_tint = (world_rng.uniform(0.88, 1.12), world_rng.uniform(0.86, 1.10), world_rng.uniform(0.86, 1.12))
                    minimap_base = build_minimap_base(grid, scale=2)
                    px, py = spawn
                    pa = 0.0
                    break

        active_weapon = weapons[weapon_idx]
        mb = pygame.mouse.get_pressed(num_buttons=3)
        lmb = mb[0]
        rmb = mb[2]

        def perform_fire(weapon, cost):
            nonlocal last_shot, did_fire, recoil_amt, shot_light_until, shot_light_color
            alive_before = [en.hp > 0 for en in enemies]
            last_shot = now
            did_fire = True
            recoil_amt = max(recoil_amt, weapon.recoil * 0.36)
            ammo[weapon_idx] -= cost
            darkness = clamp(1.0 - (sonar.sample(2.0) + max(0.0, (shot_light_until - now) / max(0.001, SHOT_LIGHT_DURATION)) * 0.6), 0.0, 1.0)
            try_fire_weapon(weapon, weapon_idx, px, py, pa, enemies, grid, shot_fx, vulnerability, darkness=darkness)
            shot_light_until = now + SHOT_LIGHT_DURATION
            shot_light_color = weapon.energy_color
            if weapon.sfx:
                ch = pygame.mixer.find_channel() if pygame.mixer.get_init() else None
                if ch is None:
                    weapon.sfx.set_volume(0.52)
                    weapon.sfx.play()
                else:
                    ch.set_volume(0.48, 0.48)
                    ch.play(weapon.sfx)

            killed_now = 0
            for i, en in enumerate(enemies):
                if alive_before[i] and en.hp <= 0:
                    killed_now += 1
                    ds, monster_death_cycle = pick_from_sound_cycle(monster_death_variants, monster_death_cycle)
                    if ds:
                        play_spatial_sound(ds, en.x, en.y, base_gain=0.52, max_dist=28.0)
            if killed_now > 0:
                sonar.add_pulse(strength=0.78 + 0.12 * killed_now, duration=2.4 + 0.7 * killed_now)

        def perform_secondary(weapon):
            nonlocal last_shot, did_fire, recoil_amt
            speed = max(4.2, 13.0 - weapon.idx * 0.85)
            dmg = int(16 + (14.0 - speed) * 7.5)
            shape = ["diamond", "triangle", "hex", "spike", "orb", "shard", "cross", "rune", "core"][weapon.idx - 1]
            spread = random.uniform(-0.028, 0.028)
            ang = pa + spread
            obsidian_rounds.append({
                "x": px,
                "y": py,
                "vx": math.cos(ang) * speed,
                "vy": math.sin(ang) * speed,
                "ttl": 1.8 + weapon.idx * 0.08,
                "shape": shape,
                "radius": 5 + weapon.idx,
                "dmg": dmg,
                "weapon": weapon,
            })
            did_fire = True
            last_shot = now
            recoil_amt = max(recoil_amt, weapon.recoil * 0.22)
            shot_fx.append({"kind": "obsidian_muzzle", "ttl": 0.12, "max": 0.12, "weapon": weapon})

        if weapon_idx == 0:
            fire_gap = max(0.032, min(active_weapon.cooldown, 0.050))
            if lmb and now - last_shot >= fire_gap and ammo[weapon_idx] > 0:
                perform_fire(active_weapon, 1)
        elif weapon_idx == 5:
            fire_gap = max(0.020, min(active_weapon.cooldown, 0.040))
            if lmb and now - last_shot >= fire_gap and ammo[weapon_idx] > 0:
                perform_fire(active_weapon, 1)
        elif weapon_idx == 6:
            fire_gap = 0.015
            if lmb and now - last_shot >= fire_gap and ammo[weapon_idx] > 0:
                perform_fire(active_weapon, 1)
        else:
            ammo_cost = 4 if weapon_idx == 8 else 1
            sfx_len = active_weapon.sfx.get_length() if active_weapon.sfx else 0.0
            fire_gap = max(active_weapon.cooldown, sfx_len * 0.65)
            if lmb and now - last_shot >= fire_gap and ammo[weapon_idx] >= ammo_cost:
                perform_fire(active_weapon, ammo_cost)

        sec_gap = 0.44 + active_weapon.idx * 0.03
        sec_cost = 2 + (1 if active_weapon.idx >= 6 else 0)
        if rmb and now - last_shot >= sec_gap and ammo[weapon_idx] >= sec_cost:
            ammo[weapon_idx] -= sec_cost
            perform_secondary(active_weapon)

        enemy_points = [(en.x, en.y) for en in enemies if en.hp > 0]
        enemy_alive_list = [en for en in enemies if en.hp > 0]
        enemy_buckets, enemy_inv = build_spatial_buckets(enemy_points, cell_size=5.0) if enemy_points else ({}, 1.0)

        if did_ping:
            enemy_alert_until = max(enemy_alert_until, now + 2.6)
        if did_fire:
            enemy_alert_until = max(enemy_alert_until, now + 4.0)
        if now < step_noise_until:
            enemy_alert_until = max(enemy_alert_until, step_noise_until)
        sound_alert_active = now < enemy_alert_until
        vision_alert_active = now < night_vision_until
        enemy_detect_active = sound_alert_active or vision_alert_active
        ai_think_accum += dt
        ai_step = 1.0 / 12.0
        if ai_think_accum >= ai_step:
            steps = int(ai_think_accum / ai_step)
            ai_think_accum -= steps * ai_step
            for _ in range(steps):
                if enemy_detect_active:
                    for en in enemies:
                        if en.hp <= 0:
                            continue
                        en.last_ping_t = now
                        alert_gain = 0.24 if did_fire else 0.16 if sound_alert_active else 0.10
                        en.learn = clamp(en.learn + alert_gain, 0.0, 1.0)
                        dist_to_p = math.hypot(en.x - px, en.y - py)
                        base_step = max(1.55, dist_to_p * (0.115 if did_fire else 0.052 if sound_alert_active else 0.036))
                        step_mul = 1.42 if did_fire else 1.08 if sound_alert_active else 0.72
                        step = base_step * (1.0 + en.learn * 0.70) * step_mul * ai_step
                        en.x, en.y = enemy_step_toward(grid, en.x, en.y, px, py, step)
                else:
                    for en in enemies:
                        en.learn = max(0.0, en.learn - ai_step * 0.16)

        if now >= enemy_voice_next:
            nearest_en = None
            nearest_d = 999.0
            for en in enemies:
                if en.hp > 0:
                    d = math.hypot(en.x - px, en.y - py)
                    if d < nearest_d:
                        nearest_d = d
                        nearest_en = en
            if nearest_en is not None and nearest_d < 30.0:
                gs, monster_alive_cycle = pick_from_sound_cycle(monster_alive_variants, monster_alive_cycle)
                if gs:
                    play_spatial_sound(gs, nearest_en.x, nearest_en.y, base_gain=0.34, max_dist=26.0)
            enemy_voice_next = now + random.uniform(30.0, 50.0)

        touched = False
        if enemy_detect_active and enemy_alive_list:
            for idx in query_spatial_indices(enemy_buckets, enemy_inv, px, py, ENEMY_ATTACK_DIST + 0.25):
                en = enemy_alive_list[idx]
                if (en.x - px) ** 2 + (en.y - py) ** 2 <= ENEMY_ATTACK_DIST ** 2:
                    touched = True
                    break
        if touched:
            contact_flash_until = max(contact_flash_until, now + 0.20)
            if now >= enemy_attack_sfx_next:
                nearest_touch = min((en for en in enemies if en.hp > 0), key=lambda en: (en.x - px) ** 2 + (en.y - py) ** 2, default=None)
                if nearest_touch is not None:
                    play_spatial_sound(monster_attack_sfx, nearest_touch.x, nearest_touch.y, base_gain=0.46, max_dist=12.0)
                enemy_attack_sfx_next = now + 0.70
            for en in enemies:
                if en.hp <= 0:
                    continue
                dx = en.x - px
                dy = en.y - py
                d2 = dx * dx + dy * dy
                if d2 > ENEMY_ATTACK_DIST ** 2:
                    continue
                d = max(0.001, math.sqrt(d2))
                push = 0.34
                tx = en.x + (dx / d) * push
                ty = en.y + (dy / d) * push
                if not is_wall(grid, int(tx), int(ty)):
                    en.x, en.y = tx, ty
            enemy_alert_until = max(enemy_alert_until, now + 1.0)

        if enemies and all(en.hp <= 0 for en in enemies):
            if not portals:
                portals = spawn_portals(grid, seed + difficulty_level * 97, world_kind, (px, py))

        next_obsidian = []
        for ob in obsidian_rounds:
            ob["ttl"] -= dt
            if ob["ttl"] <= 0.0:
                continue
            ox = ob["x"] + ob["vx"] * dt
            oy = ob["y"] + ob["vy"] * dt
            if is_wall(grid, int(ox), int(oy)):
                continue
            hit = False
            if enemy_alive_list:
                for idx in query_spatial_indices(enemy_buckets, enemy_inv, ox, oy, 0.75):
                    en = enemy_alive_list[idx]
                    if (en.x - ox) ** 2 + (en.y - oy) ** 2 <= 0.55 ** 2:
                        en.hp -= ob["dmg"]
                        hit = True
                        break
            if hit:
                continue
            ob["x"], ob["y"] = ox, oy
            next_obsidian.append(ob)
        obsidian_rounds = next_obsidian

        recoil_amt = max(0.0, recoil_amt - dt * 22.0)

        prof_update_ms = (time.perf_counter() - frame_t0) * 1000.0

        nv_strength = 0.52 if now < night_vision_until else 0.0
        shot_light_raw = clamp((shot_light_until - now) / SHOT_LIGHT_DURATION, 0.0, 1.0)
        shot_light_t = smoothstep(shot_light_raw)
        lightning_room_t = smoothstep(clamp((lightning_room_until - now) / 0.48, 0.0, 1.0))
        lightning_true_t = smoothstep(clamp((lightning_true_color_until - now) / 0.70, 0.0, 1.0))

        # 3D render
        w, h = view.get_size()
        half_h = h // 2 + int(look_pitch * 0.40)
        base_bg = (6, 3, 3) if world_kind == "cavern" else (16, 5, 4)
        view.fill(base_bg)

        row_step = 4 if quality == 0 else 3
        # Lightweight sky: flat gradient + animated film grain (no mountains/clouds).
        sky_h = max(1, half_h)
        pygame.draw.rect(view, (18, 6, 7), pygame.Rect(0, 0, w, sky_h))
        grain_off = int(now * 96.0) % 64
        for gy in range(0, sky_h, 4):
            a = 10 + ((gy + grain_off) & 7)
            pygame.draw.line(view, (max(0, 18 - a), max(0, 8 - a // 2), max(0, 8 - a // 2)), (0, gy), (w, gy), 1)
        draw_bolts_behind_walls(view, now)
        dir_x = math.cos(pa)
        dir_y = math.sin(pa)
        plane_len = math.tan(FOV / 2.0)
        plane_x = -dir_y * plane_len
        plane_y = dir_x * plane_len
        step_px = 6 if quality == 0 else 4 if quality == 1 else 3
        for y in range(0, h, row_step):
            row_delta = abs(y - half_h) or 1
            dist = min((1.52 * h) / row_delta, MAX_DIST)
            fog = math.exp(-dist * FOG_DENSITY)
            sonar_b = max(sonar.sample(dist), nv_strength)
            pulse_t = clamp((1.2 - (now - sonar.last_ping_t)) / 1.2, 0.0, 1.0)
            local_radar = pulse_t * math.exp(-dist * 0.14) * 0.95
            flare = shot_light_t * math.exp(-dist * 0.11)
            light = (BASE_AMBIENT + SONAR_FLOOR_GAIN * sonar_b + local_radar + flare * 0.30 + lightning_room_t * 0.07) * fog
            tint_r = lerp(world_tint[0], 1.0, lightning_true_t); tint_g = lerp(world_tint[1], 1.0, lightning_true_t); tint_b = lerp(world_tint[2], 1.0, lightning_true_t)

            if y >= half_h:
                p = max(1.0, y - half_h)
                row_dist = (0.5 * h) / p
                ray0x = dir_x - plane_x
                ray0y = dir_y - plane_y
                ray1x = dir_x + plane_x
                ray1y = dir_y + plane_y
                step_x = row_dist * (ray1x - ray0x) / max(1, w)
                step_y = row_dist * (ray1y - ray0y) / max(1, w)
                fxw = px + row_dist * ray0x
                fyw = py + row_dist * ray0y
                for x in range(0, w, step_px):
                    tr, tg, tb = sample_demonic_floor(fxw, fyw, seed=seed)
                    grain = ((int(fxw * 3.0) * 73856093) ^ (int(fyw * 3.0) * 19349663) ^ (seed + 404)) & 255
                    c = clamp(light * (0.58 + 0.28 * (grain / 255.0)), 0.0, 1.0)
                    rr = int(clamp(tr * c * tint_r, 0, 255)); gg = int(clamp(tg * c * tint_g, 0, 255)); bb = int(clamp(tb * c * tint_b, 0, 255))
                    pygame.draw.line(view, (rr, gg, bb), (x, y), (min(w - 1, x + step_px - 1), y))
                    fxw += step_x * step_px
                    fyw += step_y * step_px
            else:
                p = max(1.0, half_h - y)
                row_dist = (0.5 * h) / p
                ray0x = dir_x - plane_x
                ray0y = dir_y - plane_y
                ray1x = dir_x + plane_x
                ray1y = dir_y + plane_y
                step_x = row_dist * (ray1x - ray0x) / max(1, w)
                step_y = row_dist * (ray1y - ray0y) / max(1, w)
                fxw = px + row_dist * ray0x
                fyw = py + row_dist * ray0y
                for x in range(0, w, step_px):
                    tr, tg, tb, *_ = sample_terrain_cached("ceilings", fxw, fyw)
                    c = clamp(0.25 * light, 0.0, 0.28)
                    rr = int(clamp(tr * c * tint_r, 0, 255)); gg = int(clamp(tg * c * tint_g, 0, 255)); bb = int(clamp(tb * c * tint_b, 0, 255))
                    pygame.draw.line(view, (rr, gg, bb), (x, y), (min(w - 1, x + step_px - 1), y))
                    fxw += step_x * step_px
                    fyw += step_y * step_px

        zbuf = [MAX_DIST] * w
        for sx in range(w):
            cam_x = (2.0 * sx / (w - 1)) - 1.0
            ray_ang = pa + cam_x * (FOV / 2.0)
            rdx = math.cos(ray_ang)
            rdy = math.sin(ray_ang)
            dist, side, wall_u, cell = cast_ray(grid, px, py, rdx, rdy)
            zbuf[sx] = dist

            wall_var = 0.86 + hash2i(cell[0], cell[1], seed=seed + 211) * 0.52
            line_h = int((h / dist) * wall_var * 3.0)
            draw0 = max(half_h - line_h // 2, 0)
            draw1 = min(half_h + line_h // 2, h - 1)

            hitx = px + rdx * dist
            hity = py + rdy * dist
            style_seed = seed + 999 + style_map[cell[1] % MAP_H][cell[0] % MAP_W] * 33
            rock = fbm(hitx * 2.0, hity * 2.0, seed=style_seed, octaves=3)
            rock_hi = fbm(hitx * 8.0 + 12.1, hity * 8.0 - 9.3, seed=style_seed + 17, octaves=2)
            carve = fbm(hitx * 13.5 + 3.2, hity * 13.5 + 6.4, seed=style_seed + 71, octaves=2)
            sonar_b = max(sonar.sample(dist), nv_strength)
            fog = math.exp(-dist * FOG_DENSITY)
            pulse_t = clamp((1.2 - (now - sonar.last_ping_t)) / 1.2, 0.0, 1.0)
            local_radar = pulse_t * math.exp(-dist * 0.13) * 0.90
            flare = shot_light_t * math.exp(-dist * 0.10)
            light = (BASE_AMBIENT + SONAR_WALL_GAIN * sonar_b + local_radar + flare * 0.34 + lightning_room_t * 0.08) * fog
            edge = 1.0 - ((abs(0.5 - wall_u) * 2.0) ** 1.65) * 0.5

            # Embedded relief bands and seams to make walls feel carved/3D.
            rib = 0.5 + 0.5 * math.sin(wall_u * math.tau * 6.0 + style_seed * 0.01)
            seam = 1.0 if abs((wall_u * 14.0) % 1.0 - 0.5) < 0.09 else 0.0
            relief = (rock_hi - 0.5) * 0.28 + (carve - 0.5) * 0.20 + (rib - 0.5) * 0.16 - seam * 0.22
            light *= (0.70 + 0.30 * edge + relief) * (0.84 if side else 1.0)

            style_id = style_map[cell[1] % MAP_H][cell[0] % MAP_W]
            if world_kind == "cavern":
                wall_palette = [(180, 45, 25), (140, 22, 18), (160, 30, 40), (110, 20, 36), (150, 28, 22)]
            else:
                wall_palette = [(210, 55, 35), (170, 32, 20), (190, 40, 60), (140, 28, 50), (180, 42, 28)]
            wr, wg, wb = wall_palette[style_id]
            tint_r = lerp(world_tint[0], 1.0, lightning_true_t); tint_g = lerp(world_tint[1], 1.0, lightning_true_t); tint_b = lerp(world_tint[2], 1.0, lightning_true_t)
            wr = int(clamp(wr * tint_r, 0, 255)); wg = int(clamp(wg * tint_g, 0, 255)); wb = int(clamp(wb * tint_b, 0, 255))
            base = 0.18 + 0.64 * rock + (rock_hi - 0.5) * 0.12
            c = clamp(base * light, 0.0, 1.0)
            rr = int(wr * c)
            gg = int(wg * c)
            bb = int(wb * c)
            if seam > 0.0:
                rr = int(rr * 0.78); gg = int(gg * 0.76); bb = int(bb * 0.76)
            if shot_light_t > 0.0:
                rr = min(255, rr + int(shot_light_color[0] * shot_light_t * 0.18))
                gg = min(255, gg + int(shot_light_color[1] * shot_light_t * 0.18))
                bb = min(255, bb + int(shot_light_color[2] * shot_light_t * 0.18))
            pygame.draw.line(view, (rr, gg, bb), (sx, draw0), (sx, draw1))
            if (cell[0], cell[1]) in tooth_tiles and draw1 > draw0 + 8:
                tooth_h = 3 + int(hash2i(cell[0], cell[1], seed=sx + seed) * 8)
                tc = (min(255, rr + 18), min(255, gg + 12), min(255, bb + 12))
                pygame.draw.line(view, tc, (sx, draw0), (sx, min(draw1, draw0 + tooth_h)))
            if (cell[0], cell[1]) in symbol_tiles and dist < 14.0:
                mid = (draw0 + draw1) // 2
                colr = (min(255, rr + 45), min(255, gg + 20), min(255, bb + 20))
                pygame.draw.line(view, colr, (sx, max(draw0, mid - 8)), (sx, min(draw1, mid + 8)))
                if hash2i(cell[0], cell[1], seed=seed + 313) > 0.58:
                    pygame.draw.line(view, (max(0, rr - 32), max(0, gg - 28), max(0, bb - 28)), (sx, max(draw0, mid + 10)), (sx, min(draw1, mid + 18)))

            if dist < 16.0 and sonar_b > 0.08 and hash2i(cell[0], cell[1], seed=seed + (sx & 7)) > 0.75:
                ymid = (draw0 + draw1) // 2
                pygame.draw.line(view, (255, 120, 90) if world_kind == "exterior" else (220, 85, 70), (sx, ymid - 6), (sx, ymid + 6))

        # Placeholder trees/pillars removed; arena focuses on wall/sky silhouettes.

        sprite_list = []
        move_frames = enemy_anim.get("move", [])
        attack_frames = enemy_anim.get("attack", [])
        eye_points = enemy_anim.get("eye_points", [])
        for en in enemies:
            if en.hp <= 0:
                continue
            dx = en.x - px
            dy = en.y - py
            dist = math.hypot(dx, dy)
            if dist < 0.4 or dist > MAX_DIST:
                continue
            rel = wrap_pi(math.atan2(dy, dx) - pa)
            if abs(rel) > (FOV / 2.0 + 0.22):
                continue
            sb = max(sonar.sample(dist), nv_strength)
            sonar_vis = sonar.sample(dist)
            alpha = int(clamp(112 + 143 * max(sonar_vis, nv_strength), 88, 255))
            sx = int((0.5 + rel / FOV) * w)
            size = int(clamp((h / dist) * 1.62, 24, 520))
            is_attack = dist < 3.8 or en.learn > 0.75
            attack_mix = clamp((3.8 - dist) / 2.4, 0.0, 1.0)
            if en.learn > 0.75:
                attack_mix = max(attack_mix, clamp((en.learn - 0.75) / 0.25, 0.0, 1.0) * 0.6)
            frame_rate = 9.8
            frame_t = now * frame_rate + dist * 0.8 + en.anim_phase
            flip_x = ((int(now * (13.0 if is_attack else 5.0)) + en.flip_bias + int(dist * 3.0)) % 2 == 0) if is_attack else (en.flip_bias == 1)
            sprite_list.append((dist, sx, size, alpha, frame_t, flip_x, attack_mix))

        sprite_list.sort(reverse=True, key=lambda t: t[0])
        for i_sp, (dist, sx, size, alpha, frame_t, flip_x, attack_mix) in enumerate(sprite_list):
            col = int(clamp(sx, 0, w - 1))
            if dist > zbuf[col] + 0.1:
                continue
            sy = half_h + int(math.sin(now * 3.3 + dist) * 4)
            blur_key = (i_sp, int(dist * 100.0))
            prev_state = enemy_blur_history.get(blur_key)
            if prev_state is not None:
                psx, psy, psz = prev_state
                palpha = int(alpha * 0.28)
                if palpha > 8:
                    blit_enemy_with_blend(view, move_frames, attack_frames, eye_points, psx, psy, max(24, int(psz * 0.96)), palpha, frame_t - 0.34, shadow_t=0.0, flip_x=flip_x, attack_mix=attack_mix)
            enemy_blur_history[blur_key] = (sx, sy, size)
            blit_enemy_with_blend(view, move_frames, attack_frames, eye_points, sx, sy, size, alpha, frame_t, shadow_t=1.0 - min(1.0, dist / 10.0), flip_x=flip_x, attack_mix=attack_mix)

        # Weather rain rendered in world-space and depth-tested so it stays behind walls.
        if weather_mode in ("rain", "storm"):
            if rain_overlay.get_size() != (w, h):
                rain_overlay = pygame.Surface((w, h), pygame.SRCALPHA)
            else:
                rain_overlay.fill((0, 0, 0, 0))
            for d in rain_drops:
                d[1] += d[2] * dt
                d[0] += 0.35 * dt
                if d[0] < 0.8:
                    d[0] += MAP_W - 2.0
                if d[0] > MAP_W - 0.8:
                    d[0] -= MAP_W - 2.0
                if d[1] > MAP_H - 0.8:
                    d[1] = 0.8
                dxr = d[0] - px
                dyr = d[1] - py
                dist_r = math.hypot(dxr, dyr)
                if dist_r < 1.2 or dist_r > MAX_DIST:
                    continue
                rel_r = wrap_pi(math.atan2(dyr, dxr) - pa)
                if abs(rel_r) > (FOV / 2.0 + 0.10):
                    continue
                sxr = int((0.5 + rel_r / FOV) * w)
                if sxr < 0 or sxr >= w:
                    continue
                if dist_r > zbuf[sxr] - 0.05:
                    continue
                y0 = int(half_h - (h / max(1.3, dist_r)) * 0.15)
                y1 = y0 + int(clamp(24.0 / max(1.0, dist_r * 0.12), 3, 10))
                alpha = 42 if weather_mode == "rain" else 56
                pygame.draw.line(rain_overlay, (0, 0, 0, alpha), (sxr, y0), (sxr + 1, y1), 1)
            view.blit(rain_overlay, (0, 0), special_flags=pygame.BLEND_RGBA_SUB)

        scaled_view = pygame.transform.scale(view, (VIRTUAL_W, VIRTUAL_H)) if quality == 0 else pygame.transform.smoothscale(view, (VIRTUAL_W, VIRTUAL_H))
        virtual.blit(scaled_view, (0, 0))

        if show_scanlines:
            virtual.blit(scanline_surf, (0, 0), special_flags=pygame.BLEND_RGBA_SUB)
        # dark film static grain
        virtual.blit(grain_surf, (0, 0), special_flags=pygame.BLEND_RGBA_SUB)
        if nv_strength > 0.0:
            nv_overlay_full.fill((54, 8, 8, int(48 * nv_strength)))
            virtual.blit(nv_overlay_full, (0, 0), special_flags=pygame.BLEND_RGBA_ADD)
        if lightning_room_t > 0.0:
            lightning_overlay_full.fill((34, 4, 4, int(16 * lightning_room_t)))
            virtual.blit(lightning_overlay_full, (0, 0), special_flags=pygame.BLEND_RGBA_ADD)

        # Removed placeholder white floor markers in open areas.

        # pickups + portals markers
        for p in pickups:
            dx = p.x - px
            dy = p.y - py
            dist = math.hypot(dx, dy)
            if 0.5 < dist < 24 and has_los(grid, px, py, p.x, p.y):
                rel = wrap_pi(math.atan2(dy, dx) - pa)
                if abs(rel) < (FOV / 2.0 + 0.08):
                    sx = int((0.5 + rel / FOV) * VIRTUAL_W)
                    sy = int(VIRTUAL_H * 0.53 + VIRTUAL_H / max(7.0, dist * 1.55))
                    spr = marker_assets["pickup"][p.weapon_idx]
                    scale = clamp(105 / dist, 0.40, 0.95)
                    sw, sh = int(spr.get_width() * scale), int(spr.get_height() * scale)
                    blit_spr = scale_sprite_cached(spr, sw, sh)
                    virtual.blit(blit_spr, (sx - sw // 2, sy - sh // 2))


        for pu in powerups:
            dx = pu.x - px
            dy = pu.y - py
            dist = math.hypot(dx, dy)
            if 0.5 < dist < 24 and has_los(grid, px, py, pu.x, pu.y):
                rel = wrap_pi(math.atan2(dy, dx) - pa)
                if abs(rel) < (FOV / 2.0 + 0.08):
                    sx = int((0.5 + rel / FOV) * VIRTUAL_W)
                    sy = int(VIRTUAL_H * 0.53 + math.sin(now * 5.0) * 10)
                    spr = marker_assets["nightvision"]
                    scale = clamp(180 / dist, 0.4, 1.4)
                    sw, sh = int(spr.get_width() * scale), int(spr.get_height() * scale)
                    blit_spr = scale_sprite_cached(spr, sw, sh)
                    virtual.blit(blit_spr, (sx - sw // 2, sy - sh // 2))

        for portal in portals:
            dx = portal.x - px
            dy = portal.y - py
            dist = math.hypot(dx, dy)
            if 0.6 < dist < 40 and has_los(grid, px, py, portal.x, portal.y):
                rel = wrap_pi(math.atan2(dy, dx) - pa)
                if abs(rel) < (FOV / 2.0 + 0.08):
                    sx = int((0.5 + rel / FOV) * VIRTUAL_W)
                    sy = int(VIRTUAL_H / 2 + 30)
                    pr = int(clamp(200 / dist, 9, 70))
                    col = (180, 70, 255) if portal.target_world == "exterior" else (255, 90, 70)
                    spr_key = "portal_to_exterior" if portal.target_world == "exterior" else "portal_to_cavern"
                    spr = marker_assets[spr_key]
                    scale = clamp(pr / 48.0, 0.6, 1.8)
                    sw, sh = int(spr.get_width() * scale), int(spr.get_height() * scale)
                    blit_spr = scale_sprite_cached(spr, sw, sh)
                    virtual.blit(blit_spr, (sx - sw // 2, sy - sh // 2), special_flags=pygame.BLEND_RGBA_ADD)
                    pygame.draw.circle(virtual, col, (sx, sy), pr, width=3)
                    pygame.draw.circle(virtual, (255, 255, 255), (sx, sy), max(2, pr // 5), width=1)
                    for si in range(8):
                        a = now * 2.6 + si * (math.tau / 8.0)
                        rr = pr * (0.35 + 0.55 * ((si % 3) / 2.0))
                        sx2 = int(sx + math.cos(a) * rr)
                        sy2 = int(sy + math.sin(a * 1.3) * rr * 0.7)
                        pygame.draw.circle(virtual, col, (sx2, sy2), max(2, pr // 10))

        weapon = weapons[weapon_idx]
        angle_deg = 0.0
        angle_key = 0
        wp, wp_anchor = get_weapon_pose_cached(weapon_pose_cache, weapon_idx, weapon, angle_key, angle_deg)

        pivot_x = VIRTUAL_W // 2
        pivot_y = VIRTUAL_H + 88 - int(recoil_amt)
        wp_rect = wp.get_rect(midbottom=(pivot_x, pivot_y))
        xw, yw = wp_rect.topleft
        muzzle_x = xw + wp_anchor[0]
        muzzle_y = yw + wp_anchor[1]
        cross_x = VIRTUAL_W // 2
        cross_y = VIRTUAL_H // 2 + int(look_pitch * 0.60)

        # Draw non-impact shot FX first so they emit from behind the gun sprite.
        alive_fx = []
        for fxi in shot_fx:
            fxi["ttl"] -= dt
            if fxi["ttl"] <= 0.0:
                continue
            alive_fx.append(fxi)
            t = fxi["ttl"] / fxi["max"]
            wf = fxi["weapon"]
            if fxi["kind"] == "muzzle":
                burst_n = wf.fx_burst_count + (2 if wf.idx == 4 else 0)
                for b in range(burst_n):
                    ang = (b / max(1, wf.fx_burst_count)) * math.tau + now * 8.0
                    rad = int(wf.fx_radius * t * (0.35 + b * 0.1))
                    pxo = int(math.cos(ang) * (8 + b * 3) * t)
                    pyo = int(math.sin(ang) * (6 + b * 2) * t)
                    flash = pygame.Surface((rad * 2 + 2, rad * 2 + 2), pygame.SRCALPHA)
                    pygame.draw.circle(flash, (*wf.muzzle_color, int(175 * t)), (rad + 1, rad + 1), rad)
                    virtual.blit(flash, (muzzle_x - rad + pxo, muzzle_y - rad + pyo), special_flags=pygame.BLEND_RGBA_ADD)
            elif fxi["kind"] == "obsidian_muzzle":
                for oi in range(7):
                    ang = now * 4.0 + oi * (math.tau / 7.0)
                    rr = int((8 + oi * 3) * t)
                    pygame.draw.circle(virtual, (40, 28, 28), (muzzle_x + int(math.cos(ang) * rr), muzzle_y + int(math.sin(ang) * rr)), max(1, 4 - oi // 2))
            elif fxi["kind"] == "energy":
                pygame.draw.line(virtual, wf.energy_color, (muzzle_x, muzzle_y), (cross_x, cross_y), wf.fx_beam_width)
            elif fxi["kind"] == "energy_plasma":
                segs = 7
                for si in range(segs):
                    t0 = si / segs
                    t1 = (si + 1) / segs
                    x0 = int(muzzle_x + (cross_x - muzzle_x) * t0)
                    y0 = int(muzzle_y + (cross_y - muzzle_y) * t0)
                    x1 = int(muzzle_x + (cross_x - muzzle_x) * t1)
                    y1 = int(muzzle_y + (cross_y - muzzle_y) * t1)
                    wseg = max(1, int((1.0 - t0) * 16))
                    col = (
                        min(255, wf.energy_color[0] + 25),
                        min(255, wf.energy_color[1] + 35),
                        min(255, wf.energy_color[2] + 55),
                    )
                    pygame.draw.line(virtual, col, (x0, y0), (x1, y1), wseg)
            elif fxi["kind"] == "energy_triple":
                beam = pygame.Surface((VIRTUAL_W, VIRTUAL_H), pygame.SRCALPHA)
                fade_a = int(220 * t)
                spread_px = int(48 * t)
                colors = [
                    (wf.energy_color[0], wf.energy_color[1], wf.energy_color[2], fade_a),
                    (min(255, wf.energy_color[0] + 30), min(255, wf.energy_color[1] + 30), min(255, wf.energy_color[2] + 30), fade_a),
                    (wf.energy_color[0], wf.energy_color[1], wf.energy_color[2], fade_a),
                ]
                offs = (-spread_px, 0, spread_px)
                for i, off in enumerate(offs):
                    tx = cross_x + off
                    ty = cross_y + abs(off) // 4
                    wseg = max(1, int((1.0 - abs(off) / max(1, spread_px * 2 + 1)) * 8))
                    pygame.draw.line(beam, colors[i], (muzzle_x, muzzle_y), (tx, ty), wseg)
                virtual.blit(beam, (0, 0), special_flags=pygame.BLEND_RGBA_ADD)
            elif fxi["kind"] == "energy_hellbeam":
                beam = pygame.Surface((VIRTUAL_W, VIRTUAL_H), pygame.SRCALPHA)
                dx = cross_x - muzzle_x
                dy = cross_y - muzzle_y
                segs = 12
                for si in range(segs):
                    t0 = si / segs
                    t1 = (si + 1) / segs
                    x0 = int(muzzle_x + dx * t0)
                    y0 = int(muzzle_y + dy * t0)
                    x1 = int(muzzle_x + dx * t1)
                    y1 = int(muzzle_y + dy * t1)
                    wseg = max(2, int((1.0 - t0) * 22))
                    core = (255, 64, 64, int(230 * t))
                    glow = (255, 25, 25, int(130 * t))
                    pygame.draw.line(beam, glow, (x0, y0), (x1, y1), wseg + 6)
                    pygame.draw.line(beam, core, (x0, y0), (x1, y1), wseg)
                # swarming electricity arcs around the main beam
                arc_count = 14
                for ai in range(arc_count):
                    prog0 = random.random() * 0.92
                    prog1 = min(1.0, prog0 + random.uniform(0.03, 0.11))
                    j0 = random.uniform(-36, 36)
                    j1 = random.uniform(-36, 36)
                    bx0 = int(muzzle_x + dx * prog0 - dy * (j0 / max(1.0, abs(dx) + abs(dy))))
                    by0 = int(muzzle_y + dy * prog0 + dx * (j0 / max(1.0, abs(dx) + abs(dy))))
                    bx1 = int(muzzle_x + dx * prog1 - dy * (j1 / max(1.0, abs(dx) + abs(dy))))
                    by1 = int(muzzle_y + dy * prog1 + dx * (j1 / max(1.0, abs(dx) + abs(dy))))
                    acol = (255, 120, 120, int(185 * t))
                    pygame.draw.line(beam, acol, (bx0, by0), (bx1, by1), 2)
                virtual.blit(beam, (0, 0), special_flags=pygame.BLEND_RGBA_ADD)
            elif fxi["kind"] == "bullet":
                pygame.draw.line(virtual, wf.bullet_color, (muzzle_x, muzzle_y), (cross_x, cross_y), max(1, wf.fx_beam_width - 1))
            elif fxi["kind"] == "bullet_pellet":
                off = float(fxi.get("off", 0.0))
                tx = int(cross_x + off * 180)
                ty = int(cross_y + abs(off) * 34)
                pygame.draw.line(virtual, wf.bullet_color, (muzzle_x, muzzle_y), (tx, ty), max(1, wf.fx_beam_width - 1))
            elif fxi["kind"] == "energy_vector_cube":
                beam = pygame.Surface((VIRTUAL_W, VIRTUAL_H), pygame.SRCALPHA)
                cube_count = 6
                dx = cross_x - muzzle_x
                dy = cross_y - muzzle_y
                base = max(6, wf.fx_beam_width + 2)
                for ci in range(cube_count):
                    prog = (ci + 1) / cube_count
                    px_c = int(muzzle_x + dx * prog)
                    py_c = int(muzzle_y + dy * prog)
                    size = int((1.0 - prog) * 54 + 10)
                    wire = max(1, int((1.0 - prog) * 4 + 1))
                    alpha = int((0.22 + 0.78 * t) * (1.0 - prog * 0.45) * 255)
                    col = (
                        min(255, wf.energy_color[0] + 40),
                        min(255, wf.energy_color[1] + 65),
                        min(255, wf.energy_color[2] + 95),
                        alpha,
                    )
                    half = size // 2
                    front = pygame.Rect(px_c - half, py_c - half, size, size)
                    back_off = max(3, int(size * 0.34))
                    back = front.move(-back_off, -back_off)
                    pygame.draw.rect(beam, col, back, width=wire)
                    pygame.draw.rect(beam, col, front, width=wire)
                    pygame.draw.line(beam, col, back.topleft, front.topleft, wire)
                    pygame.draw.line(beam, col, back.topright, front.topright, wire)
                    pygame.draw.line(beam, col, back.bottomleft, front.bottomleft, wire)
                    pygame.draw.line(beam, col, back.bottomright, front.bottomright, wire)
                    glow = pygame.Surface((size * 2, size * 2), pygame.SRCALPHA)
                    pygame.draw.circle(glow, (*wf.energy_color, max(18, alpha // 3)), (size, size), max(base, size // 2), width=1)
                    beam.blit(glow, (px_c - size, py_c - size), special_flags=pygame.BLEND_RGBA_ADD)
                virtual.blit(beam, (0, 0), special_flags=pygame.BLEND_RGBA_ADD)
            elif fxi["kind"] == "energy_broken":
                beam = pygame.Surface((VIRTUAL_W, VIRTUAL_H), pygame.SRCALPHA)
                segs = 14
                for si in range(segs):
                    if si % 3 == 1:
                        continue
                    t0 = si / segs
                    t1 = (si + 0.8) / segs
                    j = random.uniform(-8, 8)
                    x0 = int(muzzle_x + (cross_x - muzzle_x) * t0 + j)
                    y0 = int(muzzle_y + (cross_y - muzzle_y) * t0 - j * 0.3)
                    x1 = int(muzzle_x + (cross_x - muzzle_x) * t1 - j)
                    y1 = int(muzzle_y + (cross_y - muzzle_y) * t1 + j * 0.3)
                    col = (min(255, wf.energy_color[0] + 35), min(255, wf.energy_color[1] + 22), min(255, wf.energy_color[2] + 22), int(175 * t))
                    pygame.draw.line(beam, col, (x0, y0), (x1, y1), max(1, wf.fx_beam_width + 1))
                virtual.blit(beam, (0, 0), special_flags=pygame.BLEND_RGBA_ADD)
            elif fxi["kind"] == "energy_tri_spin":
                beam = pygame.Surface((VIRTUAL_W, VIRTUAL_H), pygame.SRCALPHA)
                dx = cross_x - muzzle_x
                dy = cross_y - muzzle_y
                for ti in range(8):
                    prog = (ti + 1) / 9.0
                    cx = muzzle_x + dx * prog
                    cy = muzzle_y + dy * prog
                    ang = now * 7.0 + ti * 0.75
                    radius = int(12 + (1.0 - prog) * 18)
                    pts = []
                    for k in range(3):
                        a = ang + k * (math.tau / 3.0)
                        pts.append((int(cx + math.cos(a) * radius), int(cy + math.sin(a) * radius)))
                    col = (wf.energy_color[0], min(255, wf.energy_color[1] + 24), min(255, wf.energy_color[2] + 48), int(165 * t))
                    pygame.draw.polygon(beam, col, pts, width=max(1, wf.fx_beam_width))
                virtual.blit(beam, (0, 0), special_flags=pygame.BLEND_RGBA_ADD)
            elif fxi["kind"] == "energy_hold_laser":
                beam = pygame.Surface((VIRTUAL_W, VIRTUAL_H), pygame.SRCALPHA)
                core = (255, 80, 80, int(170 * t))
                glow = (255, 24, 24, int(96 * t))
                wcore = max(2, wf.fx_beam_width + 1)
                pygame.draw.line(beam, glow, (muzzle_x, muzzle_y), (cross_x, cross_y), wcore + 8)
                pygame.draw.line(beam, core, (muzzle_x, muzzle_y), (cross_x, cross_y), wcore)
                virtual.blit(beam, (0, 0), special_flags=pygame.BLEND_RGBA_ADD)

        weapon_light = clamp(0.18 + 0.95 * nv_strength + 0.90 * shot_light_t + 0.50 * sonar.sample(1.6), 0.16, 1.00)
        if weapon_light < 0.995:
            wp_draw = wp.copy()
            dim = int(255 * weapon_light)
            wp_draw.fill((dim, dim, dim, 255), special_flags=pygame.BLEND_RGBA_MULT)
            if shot_light_t > 0.0:
                add_col = (
                    int(shot_light_color[0] * shot_light_t * 0.30),
                    int(shot_light_color[1] * shot_light_t * 0.30),
                    int(shot_light_color[2] * shot_light_t * 0.30),
                    0,
                )
                wp_draw.fill(add_col, special_flags=pygame.BLEND_RGBA_ADD)
            if nv_strength > 0.0:
                wp_draw.fill((int(145 * nv_strength), 0, 0, 0), special_flags=pygame.BLEND_RGBA_ADD)
            virtual.blit(wp_draw, (xw, yw))
        else:
            virtual.blit(wp, (xw, yw))

        if nv_strength > 0.0:
            nv_overlay_full.fill((42, 0, 0, int(42 * nv_strength)))
            virtual.blit(nv_overlay_full, (0, 0), special_flags=pygame.BLEND_RGBA_ADD)

        for ob in obsidian_rounds:
            dx = ob["x"] - px
            dy = ob["y"] - py
            dist = math.hypot(dx, dy)
            if dist < 0.25 or dist > MAX_DIST:
                continue
            rel = wrap_pi(math.atan2(dy, dx) - pa)
            if abs(rel) > (FOV / 2.0 + 0.08):
                continue
            sx = int((0.5 + rel / FOV) * VIRTUAL_W)
            sy = int(VIRTUAL_H / 2 + VIRTUAL_H / max(1.4, dist) * 0.20)
            r = max(2, int(ob["radius"] / max(1.0, dist * 0.24)))
            col = (24, 18, 18)
            shp = ob["shape"]
            if shp == "triangle":
                pygame.draw.polygon(virtual, col, [(sx, sy - r), (sx - r, sy + r), (sx + r, sy + r)])
            elif shp == "hex":
                pts = []
                for i in range(6):
                    a = i * (math.tau / 6.0)
                    pts.append((sx + int(math.cos(a) * r), sy + int(math.sin(a) * r)))
                pygame.draw.polygon(virtual, col, pts)
            elif shp == "cross":
                pygame.draw.line(virtual, col, (sx - r, sy), (sx + r, sy), 2)
                pygame.draw.line(virtual, col, (sx, sy - r), (sx, sy + r), 2)
            elif shp == "diamond":
                pygame.draw.polygon(virtual, col, [(sx, sy - r), (sx - r, sy), (sx, sy + r), (sx + r, sy)])
            else:
                pygame.draw.circle(virtual, col, (sx, sy), r)

        # Draw impact FX after gun (world-hit feedback).
        for fxi in alive_fx:
            if fxi["kind"] != "impact":
                continue
            t = fxi["ttl"] / fxi["max"]
            wf = fxi["weapon"]
            dist = math.hypot(fxi["x"] - px, fxi["y"] - py)
            rel = wrap_pi(math.atan2(fxi["y"] - py, fxi["x"] - px) - pa)
            if abs(rel) < FOV / 2.0:
                sx = int((0.5 + rel / FOV) * VIRTUAL_W)
                sy = int(VIRTUAL_H / 2 - VIRTUAL_H / max(1.2, dist) * 0.05)
                pygame.draw.circle(virtual, wf.impact_color, (sx, sy), int((10 + wf.fx_radius * 0.2) * t + 2), width=2)

        shot_fx = alive_fx

        ui_h = 68
        ui_rect = pygame.Rect(0, VIRTUAL_H - ui_h, VIRTUAL_W, ui_h)
        ui_panel = pygame.Surface((ui_rect.width, ui_rect.height), pygame.SRCALPHA)
        ui_panel.fill((12, 0, 0, 150))
        pygame.draw.rect(ui_panel, (155, 30, 30, 190), ui_panel.get_rect(), 1)
        virtual.blit(ui_panel, ui_rect.topleft)
        world_text = world_kind.upper()
        nv_left = max(0.0, night_vision_until - now)
        ui_line1 = f"WORLD {world_text}   REALM {difficulty_level}   WEAPON [{weapon.idx}] {weapon.name}"
        ui_line2 = f"AMMO {ammo[weapon_idx]:3d}/{AMMO_MAX}   OWNED {sum(1 for v in inventory if v)}/9   NV {nv_left:4.1f}s   MODE {['PERF', 'BAL', 'HQ'][quality]}"
        pygame.draw.rect(virtual, (58, 14, 14), pygame.Rect(8, VIRTUAL_H - ui_h - 2, VIRTUAL_W - 16, ui_h + 2), 2)
        virtual.blit(render_text_cached(small, ui_line1, (245, 198, 128)), (20, VIRTUAL_H - ui_h + 8))
        virtual.blit(render_text_cached(small, ui_line2, (236, 164, 120)), (20, VIRTUAL_H - ui_h + 34))

        if SHOW_FPS:
            fps = clock.get_fps()
            virtual.blit(render_text_cached(small, f"FPS {fps:5.1f} | upd {prof_update_ms:4.1f}ms rnd {max(0.0, prof_render_ms):4.1f}ms | seed {seed}", (220, 160, 160)), (18, VIRTUAL_H - 78))

        if show_map:
            mm = minimap_base.copy()
            pygame.draw.circle(mm, (255, 200, 200), (int(px * 2), int(py * 2)), 3)
            pygame.draw.line(mm, (255, 220, 220), (int(px * 2), int(py * 2)), (int((px + math.cos(pa) * 2.0) * 2), int((py + math.sin(pa) * 2.0) * 2)), 1)
            virtual.blit(mm, (18, 205))

        help_alpha = 0
        if show_help:
            remain = show_help_until - now
            if remain > 0:
                help_alpha = int(clamp(remain / 2.0, 0.0, 1.0) * 230)
            else:
                show_help = False

        if show_help and help_alpha > 0:
            panel = pygame.Surface((1560, 620), pygame.SRCALPHA)
            panel.fill((0, 0, 0, int(help_alpha * 0.92)))
            pygame.draw.rect(panel, (170, 50, 50), panel.get_rect(), 2)
            lines = [
                "HELP / CONTROLS",
                "WASD move, Mouse look (left/right + up/down), Shift sprint, C/Alt sneak",
                "LMB hold fire + RMB obsidian rounds (unique shapes/speeds), TAB next owned weapon, 1-9 direct select",
                "Weapons are pickups on the ground; touch pickup to unlock or refill ammo",
                "Ammo is limited to 200 rounds per weapon",
                "Each enemy type has one secret instant-kill weapon; all other weapons can still kill slowly",
                "The beast tracks radar pings, gunfire, loud footsteps, and active Night Vision",
                "In darkness with no sound and no Night Vision, the beast should stay still",
                "Touching the beast no longer banishes or resets the run",
                "SPACE sonar pulse reveals world and attracts enemies",
                "Night Vision powerup lights the whole scene in red and makes you easier to track",
                "ESC pauses; the pause menu has buttons to switch to Heaven vs Hell or Book of Blood",
                "Portals appear only after the beast dies, then move you to the next realm",
                "Sky texture: assets/sky/sky.png (wrapped). Central octagonal tower has spiral stairs to a portal.",
                "F1 minimap, H help, F2 quality (800p/960p/1280p ray buffer), F3 scanlines, R regenerate, ESC pause/ESC exit, F11 fullscreen",
                "Performance: starts in 800x450 ray buffer, trims load-delay waits, AI think-rate 12Hz for steadier pacing",
                "Surfaces override: assets/surfaces/walls, floors, ceilings (wall_0..4 / floor_0..4 / ceiling_0..4)",
                "Floor is a single dark-red demonic platform style; lightning is intentionally darker than radar",
                "Surface tiles use normal repeat mapping; cache keeps one skyline per world-kind/size",
                "Enemy frames use enemy_0..enemy_9 and attack_1..N; sky uses animated grain in performance mode",
            ]
            panel.blit(font.render(lines[0], True, (230, 180, 180)), (28, 24))
            body_lines = lines[1:]
            split = (len(body_lines) + 1) // 2
            for i, txt in enumerate(body_lines):
                col = 0 if i < split else 1
                row = i if i < split else i - split
                x = 28 + col * 760
                y = 92 + row * 48
                panel.blit(small.render(txt, True, (210, 140, 140)), (x, y))
            virtual.blit(panel, (VIRTUAL_W // 2 - panel.get_width() // 2, VIRTUAL_H // 2 - panel.get_height() // 2))

        if now < contact_flash_until:
            tflash = clamp((contact_flash_until - now) / 0.20, 0.0, 1.0)
            panel = pygame.Surface((VIRTUAL_W, VIRTUAL_H), pygame.SRCALPHA)
            panel.fill((60, 0, 0, int(46 * tflash)))
            pygame.draw.rect(panel, (170, 28, 28, int(170 * tflash)), panel.get_rect(), width=16)
            virtual.blit(panel, (0, 0), special_flags=pygame.BLEND_RGBA_ADD)

        prof_render_ms = (time.perf_counter() - frame_t0) * 1000.0 - prof_update_ms
        prof_accum = prof_accum * 0.92 + (prof_update_ms + max(0.0, prof_render_ms)) * 0.08

        presenter.present_cover(virtual)
        if capture_frame and not captured_once:
            pygame.image.save(virtual, capture_frame)
            captured_once = True
            exit_reason = "quit"
            running = False
        lf = clamp((loading_help_fade_until - now) / 1.0, 0.0, 1.0)
        if lf > 0.0:
            fade_panel = pygame.Surface((VIRTUAL_W, VIRTUAL_H), pygame.SRCALPHA)
            fade_panel.fill((0, 0, 0, int(225 * lf)))
            presenter.present_cover(fade_panel)
        pygame.display.flip()

    return exit_reason, presenter.window_size, presenter.fullscreen


def main():
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    args = parse_args()
    if args.capture_frame:
        result = run_radar_session(capture_frame=args.capture_frame)
        pygame.quit()
        return result

    window_size = (VIRTUAL_W, VIRTUAL_H)
    fullscreen = False
    action = "resume"
    while True:
        action, window_size, fullscreen = run_radar_session()
        if action in ("launch_hvh2", "launch_book"):
            launch_embedded_mode(action, window_size=window_size, fullscreen=fullscreen)
            continue
        break

    pygame.quit()
    return action


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        report_crash(exc)
        raise
