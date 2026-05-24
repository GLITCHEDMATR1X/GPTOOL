"""
MonkeysStranded

Key features:
- Procedural tropical island (bigger than screen), cyan water with waves.
- Two monkeys; TAB swaps which monkey is "controlled" (camera follows controlled).
- Press F to toggle follow mode: the other monkey will automatically trail behind the active (controlled) monkey.
- Climb coconut trees: SPACE toggles climb for controlled; RCTRL toggles climb for the other.
  - Climb controls are inverted (up/down swapped), per earlier request.
- Coconuts only drop when at top of tree and pressing interact (E / RSHIFT).
  - Fallen coconuts are picked up automatically by walking into them.
- Logs: press interact near a log to harvest 1 wood per in-game day (120s) per log.
- Rocks: tiny ground clutter (no shadow), picked up by standing near and pressing interact.
- Ground resources (press interact while standing on):
  - Sand tiles -> Sand item
  - Grass tiles -> Grass item (+ 1/5 chance Grass Seeds)
  - Dirt tiles -> Dirt item
  - Gravel tiles (gray) -> Soil item
  - Gravel flecks appear within dirt areas as micro details.
- Water:
  - Shallow water (near shore) is walkable.
  - Deep water blocks unless on a log raft.
  - Build/board raft: in shallow water near a log, press interact to consume log and board raft.
  - Dismount raft: on land, press interact to dismount and drop the log.
- Fishing:
  - Standing in shallow water, press interact to attempt catch fish (1/10 chance).
- Bones:
  - Only obtained by eating a fish (select fish in hotbar, press interact when nothing else applies).
- Birds:
  - Seagulls and parrots fly around and sometimes land on trees.
  - Throw rocks at them: left-click to throw a rock from shared inventory toward mouse cursor.
  - Crosshair is a small circle at the cursor.
  - Dead birds can be looted by pressing interact near them:
    - 5 feathers, 1 poultry, 1 bone.

Files:
- monkeys_island.py
- items.py
"""

from __future__ import annotations

import math
import os
import random
import sys
import time
import traceback
import types
from dataclasses import dataclass
from typing import List, Tuple, Optional, Dict, Any

import pygame

import items

import sfx

import items


# -------------------------
# Config
# -------------------------
INTERNAL_W, INTERNAL_H = 320, 180
SCALE = 6
WIN_W, WIN_H = 1920, 1080
MIN_WINDOW_W, MIN_WINDOW_H = 640, 360
FPS = 60

TILE = 6
WORLD_TW, WORLD_TH = 260, 260

DAY_SECONDS = 120.0



# Crabs
MAX_CRABS = 8
CRAB_WANDER_SPEED = 18.0
CRAB_FLEE_SPEED = 55.0
CRAB_FLEE_RANGE = 52.0       # px
CRAB_SHORE_RESPAWN_RANGE = 260.0  # px from controlled monkey to spawn beach crabs
CRAB_BODY_DESPAWN_SECONDS = 40.0

# Iguana (1 per island)
MAX_IGUANAS = 3
IGUANA_WANDER_SPEED = 22.0
IGUANA_FLEE_SPEED = 85.0
IGUANA_FLEE_RANGE = 85.0       # px
IGUANA_SHORE_RESPAWN_RANGE = 320.0  # px from controlled monkey to spawn near beach
IGUANA_BODY_DESPAWN_SECONDS = 60.0
IGUANA_LAND_DRAG = 0.86
IGUANA_WATER_DRIFT = 0.96
# Jump / climb (top-down pseudo-height)
JUMP_V0 = 190.0   # initial upward velocity (px/s)
JUMP_G  = 280.0   # gravity (px/s^2)

CRASH_DIRNAME = "crash_reports"
CRASH_BASENAME = "crash_report.txt"

# Palette
C_WATER = (60, 220, 235)
C_WATER_DEEP = (40, 190, 210)
C_FOAM = (235, 245, 250)
C_SAND = (232, 216, 152)
C_SAND_DARK = (220, 200, 130)
C_GRASS = (92, 182, 98)
C_GRASS_DARK = (75, 160, 82)
C_DIRT = (140, 116, 80)
C_ROCK = (120, 122, 130)

C_UI = (240, 240, 245)
C_UI_SHADOW = (15, 15, 18)


# -------------------------
# Crash reporter
# -------------------------
def _safe_str(obj: Any) -> str:
    try:
        return str(obj)
    except Exception:
        return repr(obj)

def write_crash_report(exc: BaseException, state: Optional[Dict[str, Any]] = None) -> str:
    state = state or {}
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    stamp = time.strftime("%Y%m%d_%H%M%S")

    base_dir = os.path.dirname(os.path.abspath(__file__))
    crash_dir = os.path.join(base_dir, CRASH_DIRNAME)
    os.makedirs(crash_dir, exist_ok=True)

    out_main = os.path.join(crash_dir, CRASH_BASENAME)
    out_arch = os.path.join(crash_dir, f"crash_report_{stamp}.txt")

    lines = []
    lines.append("Monkeys Island — Crash Report")
    lines.append("=" * 48)
    lines.append(f"Timestamp: {ts}")
    lines.append("")
    lines.append("Exception:")
    lines.append(f"  {type(exc).__name__}: {_safe_str(exc)}")
    lines.append("")
    lines.append("Traceback:")
    lines.append("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))
    lines.append("")
    lines.append("Environment:")
    lines.append(f"  Python: {sys.version.replace(os.linesep, ' ')}")
    try:
        lines.append(f"  pygame: {pygame.version.ver} (SDL {pygame.get_sdl_version()})")
    except Exception:
        lines.append("  pygame: (could not query version)")
    lines.append(f"  Platform: {sys.platform}")
    lines.append("")
    lines.append("Last-known game state:")
    for k in sorted(state.keys()):
        v = state.get(k)
        if isinstance(v, (list, tuple)) and len(v) > 20:
            v = list(v[:20]) + ["..."]
        lines.append(f"  {k}: {_safe_str(v)}")
    lines.append("")

    content = "\n".join(lines)
    try:
        with open(out_main, "w", encoding="utf-8") as f:
            f.write(content)
    except Exception:
        pass
    try:
        with open(out_arch, "w", encoding="utf-8") as f:
            f.write(content)
    except Exception:
        pass

    return out_main


def _patch_embedded_insect_source(raw: str) -> str:
    src = raw
    src = src.replace("WIN_W, WIN_H = 1000, 650", "WIN_W, WIN_H = globals().get('__embed_start_size__', (1920, 1080))")
    src = src.replace("running = True\nwhile running:", "running = True\n__embed_result__ = 'resume'\nwhile running:")
    src = src.replace("        if e.type == pygame.QUIT:\n            running = False", "        if e.type == pygame.QUIT:\n            __embed_result__ = 'quit'\n            running = False\n            continue")
    src = src.replace("        if e.type == pygame.KEYDOWN:\n", "        if e.type == pygame.KEYDOWN:\n            if e.key in (pygame.K_ESCAPE, pygame.K_e):\n                __embed_result__ = 'resume'\n                running = False\n                continue\n")
    src = src.replace("pygame.quit()", "try:\n    pygame.event.clear()\nexcept Exception:\n    pass\n__embed_return_value__ = globals().get('__embed_result__', 'resume')")
    return src


EMBEDDED_INSECTS_SOURCE = r'''
import pygame
import random
import math
import os
import re
from dataclasses import dataclass
from typing import List, Optional, Tuple, Set


# ---------------- DIAGNOSTICS / CRASH LOG ----------------
import sys
import ast
import traceback
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ---------------- VISUAL POLISH (SAFE) ----------------
# These are renderer-only enhancements. They do not affect simulation logic.
terrain_var = None  # type: ignore

def _clamp8(v: int) -> int:
    return 0 if v < 0 else (255 if v > 255 else v)

def _shade(col, dv: int):
    # dv is signed brightness adjustment
    return (_clamp8(col[0] + dv), _clamp8(col[1] + dv), _clamp8(col[2] + dv))

def _build_terrain_variation() -> None:
    """Precompute small per-cell brightness variation for flatter-looking terrain."""
    global terrain_var
    try:
        terrain_var = [[random.randint(-10, 10) for _y in range(HEIGHT)] for _x in range(WIDTH)]
    except Exception:
        terrain_var = None

# ---------------- SFX (FOLDER SCAFFOLD + LOADER) ----------------
# This version does NOT generate audio. It will:
# - Create a clear folder layout for you to drop files into
# - Load whatever compatible audio files you place there (wav/ogg/mp3, depending on SDL_mixer support)
# - Provide a simple API for future hooks (attack/death/etc.)
def _resolve_sfx_root() -> str:
    """Resolve the SFX root folder to match your on-disk folder layout.

    Priority:
    1) Parse folder_list.txt (PowerShell dir listing) if present and extract the base \sfx directory.
       (Your folder_list.txt is commonly UTF-16 from PowerShell.)
    2) Common local candidates relative to the script folder.
    3) Fallback to ./sfx
    """
    fl_path = os.path.join(BASE_DIR, "folder_list.txt")

    # 1) Infer from folder_list.txt
    try:
        if os.path.exists(fl_path):
            raw = open(fl_path, "rb").read()
            # Heuristic: UTF-16 PowerShell listings contain many NUL bytes early.
            if b"\x00" in raw[:200]:
                text = raw.decode("utf-16", errors="ignore")
            else:
                text = raw.decode("utf-8", errors="ignore")

            for ln in text.splitlines():
                if "Directory:" not in ln:
                    continue
                p = ln.split("Directory:", 1)[1].strip()
                pl = p.lower().replace("/", "\\")
                if "\\sfx" not in pl:
                    continue

                # Normalize to the root ...\sfx (strip any deeper subpath)
                idx = pl.find("\\sfx")
                p_root = p[: idx + 4]  # include '\sfx'
                p_root = os.path.normpath(p_root)

                if os.path.isdir(p_root):
                    return p_root
    except Exception:
        pass

    # 2) Common candidates
    for cand in (
        os.path.join(BASE_DIR, "sfx"),
        os.path.join(BASE_DIR, "assets", "sfx"),
        os.path.join(BASE_DIR, "audio", "sfx"),
    ):
        if os.path.isdir(cand):
            return cand

    # 3) Fallback (created lazily by ensure_sfx_folders)
    return os.path.join(BASE_DIR, "sfx")

SFX_ROOT = _resolve_sfx_root()
SFX_ENTITIES = [
    "black_ant", "red_ant",
    "black_queen", "red_queen",
    "worm", "hornet",
    "spider",
    "egg_black", "egg_red",
]

SFX_ACTIONS = ["attack", "death"]

SFX_EXTS = (".wav", ".ogg", ".mp3")

def ensure_sfx_folders() -> None:
    try:
        os.makedirs(SFX_ROOT, exist_ok=True)
        for ent in SFX_ENTITIES:
            for act in SFX_ACTIONS:
                os.makedirs(os.path.join(SFX_ROOT, ent, act), exist_ok=True)
        # Weather / ambience
        os.makedirs(os.path.join(SFX_ROOT, "rain", "loop"), exist_ok=True)
    except Exception as ex:
        # Never crash the game due to filesystem issues.
        log_line(f"SFX folder setup failed: {ex!r}")

class SFXManager:
    def __init__(self) -> None:
        self.ok = False
        # map: (entity, action) -> [pygame.mixer.Sound, ...]
        self.sounds = {}

    def init(self) -> None:
        # Use mixer if available. If music already initialized it, this is a no-op.
        try:
            if pygame.mixer.get_init() is None:
                pygame.mixer.init()
            self.ok = True
        except Exception as ex:
            self.ok = False
            log_line(f"SFX init failed (mixer unavailable): {ex!r}")

    def _scan_dir(self, folder: str):
        out = []
        try:
            for fn in os.listdir(folder):
                if fn.lower().endswith(SFX_EXTS):
                    out.append(os.path.join(folder, fn))
        except Exception:
            return []
        out.sort()
        return out

    def load(self) -> None:
        self.sounds.clear()
        if not self.ok:
            return
        for ent in SFX_ENTITIES:
            for act in SFX_ACTIONS:
                folder = os.path.join(SFX_ROOT, ent, act)
                paths = self._scan_dir(folder)
                if not paths:
                    continue
                loaded = []
                for p in paths:
                    try:
                        loaded.append(pygame.mixer.Sound(p))
                    except Exception as ex:
                        log_line(f"SFX load failed: {p} :: {ex!r}")
                if loaded:
                    self.sounds[(ent, act)] = loaded

    def volume_from_zoom(self, zoom: float) -> float:
        # Louder when zoomed in, quieter when zoomed out.
        # Clamp to a sensible range.
        try:
            z = float(zoom)
        except Exception:
            z = 1.0
        # zoom ~0.5..6.0 typical; map to ~0.15..1.0
        v = 0.15 + (max(0.0, min(6.0, z)) / 6.0) * 0.85
        return max(0.0, min(1.0, v))

    def play(self, entity: str, action: str, zoom: float = 1.0) -> None:
        if not self.ok:
            return
        key = (entity, action)
        lst = self.sounds.get(key)
        if not lst:
            return
        try:
            s = random.choice(lst)
            s.set_volume(self.volume_from_zoom(zoom))
            s.play()
        except Exception as ex:
            log_line(f"SFX play failed: {entity}/{action} :: {ex!r}")


class RainLoopSFX:
    """Looping rain ambience that fades in/out with the rain state."""

    def __init__(self) -> None:
        self.sound: Optional[pygame.mixer.Sound] = None
        self.channel: Optional[pygame.mixer.Channel] = None
        self.loaded = False
        self.playing = False
        self.base_volume = 0.35

    def _load(self) -> None:
        if self.loaded:
            return
        self.loaded = True
        try:
            folder = os.path.join(SFX_ROOT, "rain", "loop")
            if not os.path.isdir(folder):
                return
            files = sorted([fn for fn in os.listdir(folder) if fn.lower().endswith(SFX_EXTS)])
            if not files:
                return
            path = os.path.join(folder, files[0])
            self.sound = pygame.mixer.Sound(path)
            self.sound.set_volume(self.base_volume)
        except Exception as ex:
            log_line(f"Rain SFX load failed: {ex!r}")
            self.sound = None

    def start(self) -> None:
        if not pygame.mixer.get_init():
            return
        self._load()
        if self.sound is None:
            return
        if self.playing:
            return
        try:
            ch = pygame.mixer.find_channel(True)
            if ch is None:
                return
            self.channel = ch
            self.channel.set_volume(self.base_volume)
            self.channel.play(self.sound, loops=-1, fade_ms=1200)
            self.playing = True
        except Exception as ex:
            log_line(f"Rain SFX start failed: {ex!r}")

    def stop(self) -> None:
        if not self.playing:
            return
        try:
            if self.channel is not None:
                self.channel.fadeout(1500)
        except Exception as ex:
            log_line(f"Rain SFX stop failed: {ex!r}")
        self.playing = False


sfx = SFXManager()
rain_sfx = RainLoopSFX()
CRASH_LOG_PATH = os.path.join(BASE_DIR, "crash_log.txt")

DBG_EVENT = None
DBG_PHASE = None
DBG_STEP = None

def log_line(msg: str) -> None:
    try:
        with open(CRASH_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(msg.rstrip() + "\n")
    except Exception:
        pass

def log_header(title: str) -> None:
    log_line("=" * 80)
    log_line(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {title}")

def log_exception(where: str, exc: BaseException) -> None:
    log_header(f"CRASH in {where}")
    log_line("Traceback (most recent call last):")
    tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    for ln in tb.rstrip().splitlines():
        log_line(ln)
    log_line("")
    # Snapshot some runtime state if present
    try:
        log_line("--- RUNTIME STATE ---")
        for name in [
            "zoom", "zoom_target", "cam_x", "cam_y", "GAME_SPEED", "speed_accum",
            "camera_mode", "full_map_view",
            "queen_x", "queen_y", "red_queen_x", "red_queen_y",
        ]:
            if name in globals():
                log_line(f"{name}: {globals()[name]}")
        if "ants" in globals():
            log_line(f"ants: {len(ants)}")
        if "red_ants" in globals():
            log_line(f"red_ants: {len(red_ants)}")
        if "eggs" in globals():
            log_line(f"eggs: {len(eggs)}")
        if "red_eggs" in globals():
            log_line(f"red_eggs: {len(red_eggs)}")
        log_line(f"DBG_EVENT: {DBG_EVENT!r}")
        log_line(f"DBG_PHASE: {DBG_PHASE}")
        log_line(f"DBG_STEP: {DBG_STEP}")
    except Exception:
        pass
    log_line("")

def _global_excepthook(exc_type, exc, tb):
    try:
        log_exception("unhandled_exception", exc)
    finally:
        # fall back to default so you still see it in console if launched from terminal
        sys.__excepthook__(exc_type, exc, tb)

sys.excepthook = _global_excepthook

def sanity_check() -> None:
    """
    Lightweight validation that flags common 'bad code' conditions into crash_log.txt
    without crashing the game.
    """
    log_header("SANITY CHECK")
    # 1) Syntax parse the current file (catches accidental truncation / paste errors)
    try:
        with open(__file__, "r", encoding="utf-8") as f:
            ast.parse(f.read(), filename=__file__)
        log_line("syntax: OK")
    except Exception as e:
        log_line(f"syntax: FAIL ({e})")

    # 2) Required pygame features
    try:
        import pygame as _pg
        log_line(f"pygame: {_pg.version.ver}")
        has_wheel = hasattr(_pg, "MOUSEWHEEL")
        log_line(f"pygame.MOUSEWHEEL supported: {has_wheel}")
    except Exception as e:
        log_line(f"pygame: FAIL ({e})")

    # 3) Key globals / constants that frequently cause NameError when refactoring
    required_names = [
        "FPS", "WIDTH", "HEIGHT", "CELL",
        "SAND", "TUNNEL", "AIR", "CLUTTER",
        "QUEEN", "RED_QUEEN",
    ]
    missing = [n for n in required_names if n not in globals()]
    if missing:
        log_line("missing_globals: " + ", ".join(missing))
    else:
        log_line("missing_globals: none")

    log_line("")


# ---------------- CONFIG ----------------
CELL = 4
WIDTH, HEIGHT = 420, 260
WIN_W, WIN_H = 1000, 650

SAND    = (194, 178, 128)
DIRT    = (170, 145, 105)  # deeper soil
TUNNEL  = (160, 145, 100)
AIR     = (220, 220, 220)

WATER  = (90, 140, 220)  # underground pockets / flooding

# Expanded sky/air space for above-ground mounds/structures
AIR_ROWS = 44  # number of top rows that are AIR
SURFACE_Y = AIR_ROWS  # first row of SAND is the 'surface'

# ---------------- SURFACE PROFILE (VISUAL HILLS) ----------------
# We keep the physics grid unchanged (AIR above SURFACE_Y, SAND below), but render a bumpy
# sand surface in the AIR band to create small hills without breaking entity movement.
BASE_HILL_MAX = 7      # base rolling hills (cells)
HILL_MAX = 14          # maximum hill height after adding the red-lair boost (cells)
HILL_SMOOTH_PASSES = 2 # smoothing iterations for nicer slopes

# Per-column visual surface y (the first solid 'sand' pixel). Smaller y == higher hill.
surface_profile: List[int] = [SURFACE_Y for _ in range(WIDTH)]

def generate_surface_profile() -> None:
    """Generate a gentle rolling height profile (visual-only)."""
    global surface_profile
    heights = [0 for _ in range(WIDTH)]
    h = 0
    for x in range(WIDTH):
        # random walk with small steps (keeps hills smooth)
        step = random.choice([-1, 0, 0, 1])
        h = max(0, min(BASE_HILL_MAX, h + step))
        heights[x] = h

    # Smooth a few passes (box blur)
    for _ in range(HILL_SMOOTH_PASSES):
        sm = heights[:]
        for x in range(1, WIDTH - 1):
            sm[x] = int(round((heights[x - 1] + heights[x] * 2 + heights[x + 1]) / 4.0))
        heights = sm

    # Boost hills above the red queen lair (center-top nest) so the red colony has more
    # ground mass to build inside of. This is visual-only terrain (render overlay).
    # Center is at WIDTH//2 (same as red queen x by default).
    center_x = WIDTH // 2
    sigma = 30.0      # spread of the bump (larger = wider hill region)
    amp = 8.0         # peak added hill height in that region
    for x in range(WIDTH):
        dx = float(x - center_x)
        bump = int(round(amp * math.exp(-(dx * dx) / (2.0 * sigma * sigma))))
        if bump:
            heights[x] = min(HILL_MAX, heights[x] + bump)

    # Convert height -> y coordinate, clamp so we always have at least a thin sky ceiling
    prof = [SURFACE_Y for _ in range(WIDTH)]
    for x in range(WIDTH):
        y = SURFACE_Y - heights[x]
        if y < 2:
            y = 2
        if y > SURFACE_Y:
            y = SURFACE_Y
        prof[x] = y
    surface_profile = prof

def visual_ground_at(x: int, y: int) -> bool:
    """True if this cell should *render* as ground (sand/dirt), even if world[][] is AIR."""
    if not (0 <= x < WIDTH and 0 <= y < HEIGHT):
        return False
    # Only ever in the AIR band; below SURFACE_Y world already contains SAND/TUNNEL/etc.
    if y >= SURFACE_Y:
        return False
    return y >= surface_profile[x]

def surface_y_at(x: int) -> int:
    return surface_profile[x] if (0 <= x < WIDTH) else SURFACE_Y

# Above-ground mound blocks (placed in AIR region)
MOUND_COLOR = (180, 165, 120)
# Red-team above-ground dirt mound blocks
RED_MOUND_COLOR = (150, 120, 90)
WEB_COLOR      = (245, 245, 255)  # spider web
WEB_TTL        = 60 * 25          # frames
WEB_TRAP_TICKS = 60 * 3           # how long ants/hornets stay stuck
SPIDER_WEB_EVERY = 60 * 2          # place a web about every 2 seconds
SPIDER_EAT_COOLDOWN = 8
SPIDER_WEB_GROW_STEP = 2
SPIDER_WEB_MAX_R = 80


# Plants / grass (above-ground, grows over time)
PLANT_COLOR = (60, 180, 60)
PLANT_SEED_CHANCE = 0.10          # chance per growth pulse to drop a new seed
PLANT_GROW_EVERY = 12             # frames per growth pulse (per sim-step frame, not render)
PLANT_GROW_ATTEMPTS = 55          # random attempts per pulse (kept low for performance)
PLANT_SPREAD_CHANCE = 0.18

# Hornets (fly in AIR only; attack surface units)
HORNET_COUNT = 3
HORNET_COLOR = (240, 210, 40)
HORNET_SPEED = 0.22          # cells per sim-step
HORNET_SEEK_RADIUS = 20      # cells
HORNET_BITE_COOLDOWN = 18    # sim-steps between hits
HORNET_DAMAGE = 2
HORNET_WANDER_T = 140        # sim-steps before choosing new waypoint
        # sideways spread chance when growing

# Personality trait: some ants like building surface mounds
MOUND_TRAIT_CHANCE = 0.0
MOUND_BUILD_COOLDOWN = 30  # actions; per-ant
CLUTTER = (90,  70,  40)
RED_FORTRESS = (115, 45, 45)  # diggable enemy-built wall
ANT     = (0,   0,   0)
QUEEN   = (60, 60, 60)  # dark gray
RED_ANT = (170, 30, 30)

FOOD_COLOR   = (255, 255, 0)   # yellow
POISON_COLOR = (0, 255, 0)     # green

# Stone resources (NEW)
STONE_COLOR = (130, 130, 130)
STONE_COUNT = 320

# Fort building (NEW in v3)
BLACK_FORT_COLOR = (105, 105, 105)
RED_FORT_COLOR   = (135, 85, 85)

# v8: structure hardness (dig hits required)
BLACK_FORT_HP = 10  # tougher stonework
RED_FORT_HP   = 7   # lighter, more brittle walls

# Spawn 1 new builder ant per team every 5 game minutes (5 * 60 seconds)
# NOTE: do not reference FPS here (FPS is defined later) to avoid a NameError at import.
BUILDER_HATCH_EVERY = 60 * 60 * 5  # 18,000 frames at 60 FPS

# Fort growth pacing (v5): builders create expanding, maze-like stone forts.
# Use fixed frame counts (do not reference FPS here).
FORT_GROW_EVERY = 60 * 12      # ~12 seconds at 60 FPS
FORT_GROW_STEP  = 2            # cells per growth step
FORT_GROW_MAX   = 180          # safety cap (clamped to map bounds)

# v8.1: automatic fort expansion pulse (keeps siege pressure high)
FORT_AUTO_BUILD_EVERY = 60 * 10      # every ~10 seconds
FORT_AUTO_BUILD_ATTEMPTS = 6         # placements per pulse per team

# Earthworm
WORM_COLOR = (120, 90, 60)
# Slower, more "natural" movement (higher = slower)
WORM_STEP_FRAMES = 14
# How long the worm body is (in cells)
WORM_LENGTH = 18
# How often it considers turning (lower = smoother)
WORM_TURN_CHANCE = 0.18
# Smooth tunnel carving radius (cells). 1 = slightly wider/rounder than ant single-tile digs, but still uses TUNNEL tiles.
WORM_CARVE_RADIUS = 1
# Collapse radius when crossing existing ant tunnels
WORM_TUNNEL_COLLAPSE_RADIUS = 1
# Chance per affected tile to collapse when intersecting an ant tunnel
WORM_TUNNEL_COLLAPSE_CHANCE = 0.65
# Avoid queens within this radius (cells)
WORM_AVOID_R = 4

FOOD_COUNT   = 100
POISON_COUNT = 70

FPS = 60

# Enemy queen + eggs (top nest)
RED_QUEEN = (120, 20, 20)
RED_EGG_COLOR = (255, 210, 210)
RED_EGG_SPAWN_EVERY = FPS * 20  # lays an egg every 20 seconds
RED_EGG_HATCH_AFTER = FPS * 20  # hatches after 20 seconds

RED_QUEEN_HP = 100  # 100 bites to kill the red queen

START_BLACK_ANTS = 25

EGG_COLOR = (255, 255, 255)
EGG_SPAWN_EVERY = FPS * 30
EGG_HATCH_AFTER = FPS * 30

BLACK_STEP_FRAMES = 5
RED_STEP_FRAMES   = 3

BLACK_DIG_CHANCE   = 0.35
BLACK_DIG_COOLDOWN = 8

RED_DIG_CHANCE     = 0.55
RED_DIG_COOLDOWN   = 4

RED_MAX = 30

RED_HP = 10
BLACK_HP = 1
BLACK_BITE_COOLDOWN = FPS * 2  # 2s per bite
RED_BITE_COOLDOWN = FPS * 2  # 2s per bite

# Make detection harder (both sides)
BLACK_ENEMY_DETECT_R = 16
RED_QUEEN_DETECT_R   = 45
NOISY_NAV_CHANCE     = 0.35  # chance per move to "drift" away from target

# Help / alarm
ALARM_RADIUS = 18
ALARM_TTL = FPS * 2

# Food cooperation (reduced)
FOOD_SCAN_RADIUS = 10
FOOD_HELP_RADIUS = 18
FOOD_HELP_TTL    = FPS * 2

QUEEN_MAX_LEVEL = 100
PHEROMONE_BASE = 7
PHEROMONE_PER_LEVEL = 0.20
PHEROMONE_MAX = 60

ZOOM_MAX = 4.0
ZOOM_STEP = 1.06
ZOOM_SMOOTHING = 0.22

# Speed slider
SPEED_MIN = 1.0
SPEED_MAX = 20.0

# Builder-maze parameters
MAZE_MARGIN_X = 42
MAZE_MARGIN_Y_TOP = 46
MAZE_MARGIN_Y_BOTTOM = 10
MAZE_CELL_W = 2  # corridor grid spacing in world cells (1=every cell, 2=classic maze on odd coords)
MAZE_TARGET_CHAMBERS = 9
MAZE_ROOM_R_MIN = 3
MAZE_ROOM_R_MAX = 6
# ----------------------------------------


# ---------------- DATA ----------------
@dataclass
class BlackAnt:
    x: int
    y: int
    role: str  # worker / guard / scout / warrior
    hp: int = BLACK_HP

    # movement/dig state
    dir: Tuple[int, int] = (0, -1)
    dir_ticks: int = 20
    cool: int = 0
    dig_cool: int = 0

    # combat / alarm
    bite_cool: int = 0
    alarm_t: int = 0
    alarm_x: int = 0
    alarm_y: int = 0

    # food tasking
    carry_food: bool = False
    carry_stone: bool = False

    # mound-building trait (surface structures)
    mounder: bool = False
    carry_sand: bool = False
    mound_cool: int = 0
    food_tx: Optional[int] = None
    food_ty: Optional[int] = None
    food_help_t: int = 0

    # worker build cadence / maze building
    build_cool: int = 0
    build_tx: Optional[int] = None
    build_ty: Optional[int] = None

    # idle behavior (prevents back-and-forth wandering)
    idle_t: int = 0
    idle_task: str = ""
    idle_tx: Optional[int] = None
    idle_ty: Optional[int] = None

    # surface exploration (some reds go topside)
    surface_t: int = 0
    surface_tx: Optional[int] = None
    surface_ty: Optional[int] = None

    # surface exploration (some reds go topside)
    surface_t: int = 0
    surface_tx: Optional[int] = None
    surface_ty: Optional[int] = None

    # web trap
    trapped_t: int = 0


@dataclass
class RedAnt:
    x: int
    y: int
    role: str = "raider"  # raider / builder

    dir: Tuple[int, int] = (0, 1)
    dir_ticks: int = 30
    cool: int = 0
    dig_cool: int = 0

    hp: int = RED_HP
    bite_cool: int = 0
    carrying_food: bool = False
    carry_stone: bool = False

    # mound-building trait (surface structures)
    mounder: bool = False
    carry_sand: bool = False
    mound_cool: int = 0

    # builder state
    build_cool: int = 0
    build_tx: Optional[int] = None
    build_ty: Optional[int] = None

    # idle behavior (prevents back-and-forth wandering)
    idle_t: int = 0
    idle_task: str = ""
    idle_tx: Optional[int] = None
    idle_ty: Optional[int] = None

    # surface exploration (some reds go topside)
    surface_t: int = 0
    surface_tx: Optional[int] = None
    surface_ty: Optional[int] = None

    # web trap
    trapped_t: int = 0


@dataclass
class Egg:
    x: int
    y: int
    hatch_t: int


@dataclass
class RedEgg:
    x: int
    y: int
    hatch_t: int


@dataclass
class Earthworm:
    x: int
    y: int
    segments: List[Tuple[int, int]]
    # Heading is an index into DIR8 (smooth turns by +/-1)
    heading: int = 4  # default: down (S)
    dir_ticks: int = 20
    cool: int = 0
    leave_collapse: bool = False



@dataclass
class Hornet:
    x: float
    y: float
    vx: float = 0.0
    vy: float = 0.0
    bite_cool: int = 0
    wander_t: int = 0
    tx: float = 0.0
    ty: float = 0.0
    # surface exploration (some reds go topside)
    surface_t: int = 0
    surface_tx: Optional[int] = None
    surface_ty: Optional[int] = None

    # web trap
    trapped_t: int = 0


@dataclass
class Spider:
    x: int
    y: int
    hp: int = 999
    cool: int = 0
    web_cool: int = 0
    eat_cool: int = 0


# ---------------- HELPERS ----------------
def in_bounds(x: int, y: int) -> bool:
    return 0 <= x < WIDTH and 0 <= y < HEIGHT


def dist2(ax: int, ay: int, bx: int, by: int) -> int:
    dx = ax - bx
    dy = ay - by
    return dx*dx + dy*dy


def clamp(v: float, a: float, b: float) -> float:
    return max(a, min(b, v))


def step_toward_noisy(ax: int, ay: int, tx: int, ty: int) -> Tuple[int, int]:
    dx = 0 if tx == ax else (1 if tx > ax else -1)
    dy = 0 if ty == ay else (1 if ty > ay else -1)

    if random.random() < NOISY_NAV_CHANCE:
        return random.choice([(-1,0),(1,0),(0,-1),(0,1),(-1,-1),(1,-1),(-1,1),(1,1)])
    if random.random() < 0.62:
        return dx, 0
    return 0, dy


def pick_branch_dir() -> Tuple[int, int]:
    return random.choice([(-1,1),(0,1),(1,1),(-1,0),(1,0),(-1,-1),(0,-1),(1,-1)])


def pick_downish_dir() -> Tuple[int, int]:
    return random.choices(
        population=[(-1, 1), (0, 1), (1, 1), (-1, 0), (1, 0), (0, -1)],
        weights=[34, 52, 34, 8, 8, 1],
        k=1
    )[0]


def is_walkable(tile: Tuple[int, int, int]) -> bool:
    # Include mound tiles as walkable so ants/spider can traverse the hill surface.
    # Mounds are visual terrain in the air band and should not act like solid rock.
    return tile in (AIR, TUNNEL, WATER, QUEEN, RED_QUEEN, MOUND_COLOR, RED_MOUND_COLOR)

def is_air_cell(x: int, y: int) -> bool:
    return in_bounds(x, y) and (y < SURFACE_Y)


def is_surface_band(y: int) -> bool:
    # band of air just above the surface where mound building happens
    return (SURFACE_Y - 10) <= y < SURFACE_Y


def find_air_mound_site(ax: int, ay: int, max_r: int = 18) -> Optional[Tuple[int, int]]:
    """Find a nearby AIR cell in the surface band suitable for placing a mound block."""
    best = None
    best_d2 = 10**9
    x0 = max(1, ax - max_r)
    x1 = min(WIDTH - 2, ax + max_r)
    y0 = max(1, (SURFACE_Y - 10))
    y1 = min(SURFACE_Y - 1, ay + max_r)
    for x in range(x0, x1 + 1):
        for y in range(y0, y1 + 1):
            if world[x][y] != AIR:
                continue
            if food[x][y] or poison[x][y] or stone[x][y]:
                continue
            # don't place on queens
            if (queen_x <= x <= queen_x + 1 and queen_y <= y <= queen_y + 1) or (red_queen_x <= x <= red_queen_x + 1 and red_queen_y <= y <= red_queen_y + 1):
                continue
            # prefer adjacent to existing mound / surface for nicer piles
            adj_bonus = 0
            for nx, ny in neighbors4(x, y):
                if world[nx][ny] in (MOUND_COLOR, RED_MOUND_COLOR, SAND):
                    adj_bonus = 1
                    break
            d2 = dist2(ax, ay, x, y)
            score = d2 - (adj_bonus * 120)
            if score < best_d2:
                best_d2 = score
                best = (x, y)
    return best


def try_collect_sand(ax: int, ay: int) -> bool:
    """Collect sand by digging a nearby SAND cell (creates a tunnel and yields one 'sand unit')."""
    # prefer sand just below the surface (doesn't hollow the deep colony)
    for _ in range(12):
        nx = ax + random.randint(-1, 1)
        ny = ay + random.randint(0, 3)
        if not in_bounds(nx, ny):
            continue
        if ny < SURFACE_Y:
            continue
        if world[nx][ny] == SAND:
            dig(nx, ny)
            return True
    return False


def handle_mounder_black(a: BlackAnt) -> bool:
    """Optional mound-building behavior. Returns True if the ant used its action."""
    if not a.mounder:
        return False
    if a.role in ("builder",):  # builders already have fort duties
        return False
    if a.carry_food or a.carry_stone:
        return False
    if a.alarm_t > 0:
        return False
    if a.mound_cool > 0:
        a.mound_cool -= 1
        return False

    # only attempt sometimes to keep normal behavior dominant
    if random.random() > 0.35:
        a.mound_cool = random.randint(6, MOUND_BUILD_COOLDOWN)
        return False

    # If carrying sand, go place it near the surface in the air band.
    if a.carry_sand:
        # If we're not already above ground, head toward the surface.
        if a.y >= SURFACE_Y:
            tx, ty = a.x, SURFACE_Y - 3
            dx, dy = step_toward_noisy(a.x, a.y, tx, ty)
            a.x, a.y = try_move_any_black(a.x, a.y, dx, dy, world)
            a.mound_cool = random.randint(4, 10)
            return True

        site = find_air_mound_site(a.x, a.y, max_r=20)
        if site is None:
            # drift along the surface band
            a.x, a.y = try_move_any_black(a.x, a.y, *pick_branch_dir(), world)
            a.mound_cool = random.randint(6, 12)
            return True

        sx, sy = site
        dx, dy = step_toward_noisy(a.x, a.y, sx, sy)
        nx, ny = try_move_any_black(a.x, a.y, dx, dy, world)
        a.x, a.y = nx, ny
        if a.x == sx and a.y == sy and world[sx][sy] == AIR:
            world[sx][sy] = MOUND_COLOR
            a.carry_sand = False
            a.mound_cool = random.randint(12, MOUND_BUILD_COOLDOWN)
        else:
            a.mound_cool = random.randint(4, 10)
        return True

    # Not carrying sand: attempt to collect it by digging near the surface.
    if try_collect_sand(a.x, a.y):
        a.carry_sand = True
        a.mound_cool = random.randint(10, MOUND_BUILD_COOLDOWN)
        return True

    a.mound_cool = random.randint(8, 14)
    return False


def handle_mounder_red(r: RedAnt) -> bool:
    if not r.mounder:
        return False
    if r.role in ("builder",):
        return False
    if r.carrying_food or r.carry_stone:
        return False
    if r.mound_cool > 0:
        r.mound_cool -= 1
        return False

    if random.random() > 0.35:
        r.mound_cool = random.randint(6, MOUND_BUILD_COOLDOWN)
        return False

    if r.carry_sand:
        if r.y >= SURFACE_Y:
            tx, ty = r.x, SURFACE_Y - 3
            dx, dy = step_toward_noisy(r.x, r.y, tx, ty)
            r.x, r.y = try_move_any(r.x, r.y, dx, dy, world)
            r.mound_cool = random.randint(4, 10)
            return True

        # Prefer building the red mound roughly above the red queen (a visible surface landmark).
        # Using the queen as an anchor prevents the mounders from scattering mounds randomly.
        site = find_air_mound_site(red_queen_x, max(2, SURFACE_Y - 4), max_r=26)
        if site is None:
            # fall back to local search
            site = find_air_mound_site(r.x, r.y, max_r=20)
        if site is None:
            r.x, r.y = try_move_any(r.x, r.y, *pick_branch_dir(), world)
            r.mound_cool = random.randint(6, 12)
            return True

        sx, sy = site
        dx, dy = step_toward_noisy(r.x, r.y, sx, sy)
        r.x, r.y = try_move_any(r.x, r.y, dx, dy, world)
        if r.x == sx and r.y == sy and world[sx][sy] == AIR:
            world[sx][sy] = RED_MOUND_COLOR
            r.carry_sand = False
            r.mound_cool = random.randint(12, MOUND_BUILD_COOLDOWN)
        else:
            r.mound_cool = random.randint(4, 10)
        return True

    if try_collect_sand(r.x, r.y):
        r.carry_sand = True
        r.mound_cool = random.randint(10, MOUND_BUILD_COOLDOWN)
        return True

    r.mound_cool = random.randint(8, 14)
    return False


def neighbors4(x: int, y: int) -> List[Tuple[int, int]]:
    out = []
    if x > 0: out.append((x-1, y))
    if x < WIDTH-1: out.append((x+1, y))
    if y > 0: out.append((x, y-1))
    if y < HEIGHT-1: out.append((x, y+1))
    return out


def try_move_any(a_x: int, a_y: int, dx: int, dy: int, world: List[List[Tuple[int,int,int]]]) -> Tuple[int, int]:
    """
    Attempt intended move; if blocked, pick a reasonable alternative that keeps the agent in tunnels.
    This prevents the maze from 'trapping' hatchlings on straight-line logic.
    """
    nx, ny = a_x + dx, a_y + dy
    if in_bounds(nx, ny) and is_walkable(world[nx][ny]):
        return nx, ny

    opts = []
    for ox, oy in [(-1,0),(1,0),(0,-1),(0,1),(-1,-1),(1,-1),(-1,1),(1,1)]:
        tx, ty = a_x + ox, a_y + oy
        if in_bounds(tx, ty) and is_walkable(world[tx][ty]):
            opts.append((tx, ty))
    if not opts:
        return a_x, a_y
    return random.choice(opts)


def try_move_any_black(a_x: int, a_y: int, dx: int, dy: int, world: List[List[Tuple[int,int,int]]]) -> Tuple[int, int]:
    """Black-ant movement helper: like try_move_any, but allows pushing fortress stones if space exists."""
    nx, ny = a_x + dx, a_y + dy
    if dx == 0 and dy == 0:
        return a_x, a_y
    if in_bounds(nx, ny) and world[nx][ny] in (RED_FORTRESS, RED_FORT_COLOR):
        bx, by = nx + dx, ny + dy
        if in_bounds(bx, by) and world[bx][by] == TUNNEL:
            # push the stone forward
            world[bx][by] = world[nx][ny]
            world[nx][ny] = TUNNEL
            return nx, ny
    return try_move_any(a_x, a_y, dx, dy, world)



# ---------------- FORT BUILDING HELPERS ----------------
def find_nearest_stone(ax: int, ay: int, max_r: int = 80) -> Optional[Tuple[int, int]]:
    best = None
    best_d = 10**9
    # scan a box (fast enough at this grid size / low frequency)
    x0 = max(0, ax - max_r)
    x1 = min(WIDTH - 1, ax + max_r)
    y0 = max(1, ay - max_r)
    y1 = min(HEIGHT - 2, ay + max_r)
    for x in range(x0, x1 + 1):
        for y in range(y0, y1 + 1):
            if not stone[x][y]:
                continue
            # prefer reachable-ish cells: sand or tunnel
            if world[x][y] not in (SAND, TUNNEL):
                continue
            d2 = dist2(ax, ay, x, y)
            if d2 < best_d:
                best_d = d2
                best = (x, y)
    return best


def find_nearest_clutter(ax: int, ay: int, max_r: int = 60) -> Optional[Tuple[int, int]]:
    best = None
    best_d = 10**9
    x0 = max(1, ax - max_r)
    x1 = min(WIDTH - 2, ax + max_r)
    y0 = max(1, ay - max_r)
    y1 = min(HEIGHT - 2, ay + max_r)
    for x in range(x0, x1 + 1):
        for y in range(y0, y1 + 1):
            if world[x][y] != CLUTTER:
                continue
            d2 = dist2(ax, ay, x, y)
            if d2 < best_d:
                best_d = d2
                best = (x, y)
    return best


def idle_pick_task(is_red: bool) -> str:
    # When an ant is idle for ~1 minute, give it a purposeful "search" task.
    if is_red:
        return random.choices(["food", "stone", "clutter", "enemy", "surface"], weights=[4, 2, 3, 3, 2], k=1)[0]
    return random.choice(["food", "stone", "clutter", "enemy", "surface"])

# Idle behavior thresholds are measured in *agent actions* (not frames),
# because ants step at BLACK_STEP_FRAMES / RED_STEP_FRAMES cadences.
IDLE_ACTIONS_BLACK = 1  # act immediately; no wandering
IDLE_ACTIONS_RED   = max(30, int((FPS * 60) / max(1, RED_STEP_FRAMES)))


def idle_override_black(a: BlackAnt) -> bool:
    """If the ant has been 'wandering' for ~1 minute, assign a search task and act on it."""
    a.idle_t += 1
    if a.idle_t < IDLE_ACTIONS_BLACK:
        return False

    if not a.idle_task:
        a.idle_task = idle_pick_task(is_red=False)
        a.idle_tx = None
        a.idle_ty = None

    # Choose / refresh target
    if a.idle_task == "food":
        found = find_food_near(a.x, a.y, radius=max(FOOD_SCAN_RADIUS, 45))
        if found is not None:
            a.food_tx, a.food_ty = found
            a.food_help_t = FOOD_HELP_TTL
            a.idle_t = 0
            a.idle_task = ""
            return True

    if a.idle_task == "stone":
        tgt = find_nearest_stone(a.x, a.y, max_r=120)
        if tgt is not None:
            a.idle_tx, a.idle_ty = tgt

    elif a.idle_task == "clutter":
        tgt = find_nearest_clutter(a.x, a.y, max_r=90)
        if tgt is not None:
            a.idle_tx, a.idle_ty = tgt

    elif a.idle_task == "enemy":
        # Prefer the nearest visible enemy; otherwise head for the enemy nest.
        best = None
        best_d2 = 10**9
        for rr in red_ants:
            d2 = dist2(a.x, a.y, rr.x, rr.y)
            if d2 < best_d2:
                best_d2 = d2
                best = (rr.x, rr.y)
        if best is None:
            best = (red_nest_x, red_nest_y)
        a.idle_tx, a.idle_ty = best

    elif a.idle_task == "surface":
        # Roam the air band just above the surface to simulate surface scouting.
        y0 = max(1, SURFACE_Y - 8)
        y1 = max(1, SURFACE_Y - 1)
        a.idle_tx = random.randint(1, WIDTH - 2)
        a.idle_ty = random.randint(y0, y1)

    if a.idle_tx is not None and a.idle_ty is not None:
        tx, ty = a.idle_tx, a.idle_ty
        # If clutter task and adjacent, clear it.
        if a.idle_task == "clutter" and abs(a.x - tx) <= 1 and abs(a.y - ty) <= 1:
            if world[tx][ty] == CLUTTER:
                dig(tx, ty)
            a.idle_t = 0
            a.idle_task = ""
            a.idle_tx = None
            a.idle_ty = None
            return True

        dx, dy = step_toward_noisy(a.x, a.y, tx, ty)
        a.x, a.y = try_move_any_black(a.x, a.y, dx, dy, world)

        # If we reached the target, reset.
        if abs(a.x - tx) <= 1 and abs(a.y - ty) <= 1:
            a.idle_t = 0
            a.idle_task = ""
            a.idle_tx = None
            a.idle_ty = None
        return True

    # No target found; reset so we don't get stuck.
    a.idle_t = 0
    a.idle_task = ""
    return False


def idle_override_red(r: RedAnt) -> bool:
    r.idle_t += 1
    if r.idle_t < IDLE_ACTIONS_RED:
        return False

    if not r.idle_task:
        r.idle_task = idle_pick_task(is_red=True)
        r.idle_tx = None
        r.idle_ty = None

    if r.idle_task == "food":
        found = find_food_near(r.x, r.y, radius=max(FOOD_SCAN_RADIUS, 45))
        if found is not None:
            r.idle_tx, r.idle_ty = found

    elif r.idle_task == "stone":
        tgt = find_nearest_stone(r.x, r.y, max_r=120)
        if tgt is not None:
            r.idle_tx, r.idle_ty = tgt

    elif r.idle_task == "clutter":
        tgt = find_nearest_clutter(r.x, r.y, max_r=90)
        if tgt is not None:
            r.idle_tx, r.idle_ty = tgt

    elif r.idle_task == "enemy":
        # Enemy for red = black queen.
        r.idle_tx, r.idle_ty = (queen_x, queen_y)

    elif r.idle_task == "surface":
        y0 = max(1, SURFACE_Y - 8)
        y1 = max(1, SURFACE_Y - 1)
        r.idle_tx = random.randint(1, WIDTH - 2)
        r.idle_ty = random.randint(y0, y1)

    if r.idle_tx is not None and r.idle_ty is not None:
        tx, ty = r.idle_tx, r.idle_ty
        if r.idle_task == "clutter" and abs(r.x - tx) <= 1 and abs(r.y - ty) <= 1:
            if world[tx][ty] == CLUTTER:
                dig(tx, ty)
            r.idle_t = 0
            r.idle_task = ""
            r.idle_tx = None
            r.idle_ty = None
            return True

        dx, dy = step_toward_noisy(r.x, r.y, tx, ty)
        r.x, r.y = try_move_any(r.x, r.y, dx, dy, world)
        if abs(r.x - tx) <= 1 and abs(r.y - ty) <= 1:
            r.idle_t = 0
            r.idle_task = ""
            r.idle_tx = None
            r.idle_ty = None
        return True

    r.idle_t = 0
    r.idle_task = ""
    return False

def try_place_fort_block(is_red: bool, near_x: int, near_y: int) -> bool:
    """v5: Place a single fort stone in a way that tends to form a maze-like structure,
    and expands outward over time using a growing radius target.

    This replaces the small fixed-radius placement from v4 while keeping the same API.
    """
    fort_grid = red_fort if is_red else black_fort
    fort_color = RED_FORT_COLOR if is_red else BLACK_FORT_COLOR

    # Determine the current growth region around the appropriate queen.
    cx, cy = (red_queen_x, red_queen_y) if is_red else (queen_x, queen_y)
    grow_r = red_fort_growth_r if is_red else black_fort_growth_r

    x0 = max(1, cx - grow_r)
    x1 = min(WIDTH - 2, cx + grow_r)
    y0 = max(1, cy - grow_r)
    y1 = min(HEIGHT - 2, cy + grow_r)

    def count_adjacent(x: int, y: int) -> int:
        c = 0
        for nx, ny in neighbors4(x, y):
            if fort_grid[nx][ny]:
                c += 1
        return c

    def would_make_2x2(x: int, y: int) -> bool:
        # Avoid chunky 2x2 fort blocks; helps it look like a natural maze.
        for ox in (0, -1):
            for oy in (0, -1):
                ax, ay = x + ox, y + oy
                if not in_bounds(ax, ay) or not in_bounds(ax + 1, ay + 1):
                    continue
                a = fort_grid[ax][ay] or (ax == x and ay == y)
                b = fort_grid[ax + 1][ay] or (ax + 1 == x and ay == y)
                c = fort_grid[ax][ay + 1] or (ax == x and ay + 1 == y)
                d = fort_grid[ax + 1][ay + 1] or (ax + 1 == x and ay + 1 == y)
                if a and b and c and d:
                    return True
        return False

    candidates = []  # list[(score,x,y)]
    for x in range(x0, x1 + 1):
        for y in range(y0, y1 + 1):
            if fort_grid[x][y]:
                continue
            if (x, y) in ((queen_x, queen_y), (red_queen_x, red_queen_y)):
                continue
            if food[x][y] or poison[x][y] or stone[x][y]:
                continue
            if world[x][y] not in (SAND, TUNNEL):
                continue

            adj = count_adjacent(x, y)
            if adj == 0:
                continue
            if adj >= 4:
                continue
            if would_make_2x2(x, y):
                continue

            # Prefer 1-2 connections (branches/corridors), avoid filling in solid blocks.
            branch_bonus = 1200 if adj == 1 else (400 if adj == 2 else -200)

            # Push outward (frontier) but still slightly bias toward the builder's current location.
            d_front = dist2(x, y, cx, cy)
            d_near  = dist2(x, y, near_x, near_y)

            score = d_front - int(d_near * 0.25) + branch_bonus
            candidates.append((score, x, y))

    if not candidates:
        return False

    candidates.sort(reverse=True, key=lambda t: t[0])
    # Pick from the best few to keep it organic
    _, px, py = random.choice(candidates[: min(16, len(candidates))])

    world[px][py] = fort_color
    fort_grid[px][py] = True
    if stone[px][py]:
        stone[px][py] = False
    return True

# ---------------- SIM INIT ----------------
pygame.init()
# Write a startup sanity report into crash_log.txt
sanity_check()
screen = pygame.display.set_mode((WIN_W, WIN_H), pygame.RESIZABLE)
pygame.display.set_caption("Ant Wars")

icon_path = os.path.join("assets", "icon.png")
if os.path.exists(icon_path):
    pygame.display.set_icon(pygame.image.load(icon_path))

clock = pygame.time.Clock()
ui_font = pygame.font.SysFont("arial", 28, bold=True)
small_font = pygame.font.SysFont("arial", 20, bold=True)

def _ui_chip(text: str, font=None, *, fg=(255, 255, 255), bg=(0, 0, 0, 185), pad_x=8, pad_y=5):
    if font is None:
        font = small_font
    base = font.render(text, True, fg)
    shadow = font.render(text, True, (20, 20, 20))
    out = pygame.Surface((base.get_width() + pad_x * 2 + 2, base.get_height() + pad_y * 2 + 2), pygame.SRCALPHA)
    out.fill(bg)
    out.blit(shadow, (pad_x + 1, pad_y + 1))
    out.blit(base, (pad_x, pad_y))
    return out

def _draw_ui_chip(text: str, x: int, y: int, *, font=None, anchor="topleft", bg=(0, 0, 0, 185)):
    surf = _ui_chip(text, font=font, bg=bg)
    rect = surf.get_rect()
    setattr(rect, anchor, (int(x), int(y)))
    screen.blit(surf, rect.topleft)
    return rect

def _draw_panel(rect: pygame.Rect, *, fill=(10, 12, 16, 170), border=(235, 240, 245)):
    panel = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
    panel.fill(fill)
    screen.blit(panel, rect.topleft)
    pygame.draw.rect(screen, border, rect, 2, border_radius=10)



# ---------------- ASSETS (SPRITES) ----------------
APP_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(APP_DIR, "assets")

# Ensure basic asset folders exist (no README generation)
for rel in [
    os.path.join("plants", "grass"),
    os.path.join("entities", "black_ant"),
    os.path.join("entities", "red_ant"),
    os.path.join("entities", "worm"),
    os.path.join("entities", "hornet"),
    os.path.join("entities", "spider"),
    os.path.join("entities", "egg_black"),
    os.path.join("entities", "egg_red"),
    os.path.join("entities", "black_queen"),
    os.path.join("entities", "red_queen"),
    os.path.join("terrain", "web"),
]:
    try:
        os.makedirs(os.path.join(ASSETS_DIR, rel), exist_ok=True)
    except Exception:
        pass

# ---------------- MUSIC (loop playlist) ----------------
MUSIC_DIR = os.path.join(APP_DIR, "music")
MUSIC_EXTS = (".mp3", ".wav", ".ogg")
music_tracks: List[str] = []
music_idx = 0

def _scan_music() -> List[str]:
    tracks: List[str] = []
    for base in [MUSIC_DIR, os.path.join(ASSETS_DIR, "music")]:
        if not os.path.isdir(base):
            continue
        for root, _dirs, files in os.walk(base):
            for fn in files:
                if fn.lower().endswith(MUSIC_EXTS):
                    tracks.append(os.path.join(root, fn))
    tracks.sort()
    return tracks

def init_music() -> None:
    global music_tracks, music_idx
    try:
        pygame.mixer.init()
    except Exception:
        return
    music_tracks = _scan_music()
    music_idx = 0
    if not music_tracks:
        return
    try:
        pygame.mixer.music.load(music_tracks[music_idx])
        pygame.mixer.music.play()
    except Exception:
        music_tracks = []

music_muted = False


def set_music_muted(muted: bool) -> None:
    global music_muted
    music_muted = bool(muted)
    try:
        if music_muted:
            pygame.mixer.music.set_volume(0.0)
        else:
            pygame.mixer.music.set_volume(1.0)
    except Exception:
        pass


def toggle_music_muted() -> None:
    set_music_muted(not music_muted)

def tick_music() -> None:
    global music_idx
    if not music_tracks:
        return
    try:
        if not pygame.mixer.music.get_busy():
            music_idx = (music_idx + 1) % len(music_tracks)
            pygame.mixer.music.load(music_tracks[music_idx])
            pygame.mixer.music.play()
    except Exception:
        pass


def _ensure_dir(path: str) -> None:
    try:
        os.makedirs(path, exist_ok=True)
    except Exception:
        pass

# Requested folders (so you can drop PNGs in without touching code)
_ensure_dir(os.path.join(ASSETS_DIR, "stone"))
_ensure_dir(os.path.join(ASSETS_DIR, "terrain", "clutter"))

# Optional/expected folders
for p in [
    os.path.join(ASSETS_DIR, "terrain", "sand"),
    os.path.join(ASSETS_DIR, "terrain", "dirt"),
    os.path.join(ASSETS_DIR, "terrain", "tunnel"),
    os.path.join(ASSETS_DIR, "terrain", "air"),
    os.path.join(ASSETS_DIR, "terrain", "fortress"),
    os.path.join(ASSETS_DIR, "food"),
    os.path.join(ASSETS_DIR, "poison"),
    os.path.join(ASSETS_DIR, "plants", "grass"),
    os.path.join(ASSETS_DIR, "plants", "flowers"),
    os.path.join(ASSETS_DIR, "plants", "trees"),
    os.path.join(ASSETS_DIR, "entities", "black_ant"),
    os.path.join(ASSETS_DIR, "entities", "red_ant"),
    os.path.join(ASSETS_DIR, "entities", "black_queen"),
    os.path.join(ASSETS_DIR, "entities", "red_queen"),
    os.path.join(ASSETS_DIR, "entities", "worm"),
    os.path.join(ASSETS_DIR, "entities", "egg_black"),
    os.path.join(ASSETS_DIR, "entities", "egg_red"),
    os.path.join(ASSETS_DIR, "entities", "spider"),
    os.path.join(ASSETS_DIR, "terrain", "web"),
    os.path.join(ASSETS_DIR, "terrain", "water"),

]:
    _ensure_dir(p)

def _first_png(folder: str) -> Optional[str]:
    try:
        if not os.path.isdir(folder):
            return None
        cands = [f for f in os.listdir(folder) if f.lower().endswith(".png")]
        if not cands:
            return None
        cands.sort()
        return os.path.join(folder, cands[0])
    except Exception:
        return None

def _load_sprite(folder: str, size: Tuple[int, int]) -> Optional[pygame.Surface]:
    path = _first_png(folder)
    if path is None:
        return None
    try:
        img = pygame.image.load(path).convert_alpha()
        if img.get_size() != size:
            img = pygame.transform.smoothscale(img, size)
        return img
    except Exception:
        return None

# Tile sprites (CELL x CELL)
SPR_T_SAND     = _load_sprite(os.path.join(ASSETS_DIR, "terrain", "sand"), (CELL, CELL))
SPR_T_DIRT     = _load_sprite(os.path.join(ASSETS_DIR, "terrain", "dirt"), (CELL, CELL))
SPR_T_TUNNEL   = _load_sprite(os.path.join(ASSETS_DIR, "terrain", "tunnel"), (CELL, CELL))
SPR_T_AIR      = _load_sprite(os.path.join(ASSETS_DIR, "terrain", "air"), (CELL, CELL))
SPR_T_CLUTTER  = _load_sprite(os.path.join(ASSETS_DIR, "terrain", "clutter"), (CELL, CELL))
SPR_T_FORTRESS = _load_sprite(os.path.join(ASSETS_DIR, "terrain", "fortress"), (CELL, CELL))
SPR_T_WEB      = _load_sprite(os.path.join(ASSETS_DIR, "terrain", "web"), (CELL, CELL))
SPR_T_WATER    = _load_sprite(os.path.join(ASSETS_DIR, "terrain", "water"), (CELL, CELL))
# Resource sprites (CELL x CELL)
SPR_FOOD   = _load_sprite(os.path.join(ASSETS_DIR, "food"), (CELL, CELL))
SPR_POISON = _load_sprite(os.path.join(ASSETS_DIR, "poison"), (CELL, CELL))
SPR_PLANT  = _load_sprite(os.path.join(ASSETS_DIR, "plants", "grass"), (CELL, CELL))
SPR_FLOWER = _load_sprite(os.path.join(ASSETS_DIR, "plants", "flowers"), (CELL, CELL))
SPR_TREE   = _load_sprite(os.path.join(ASSETS_DIR, "plants", "trees"), (CELL, CELL))
SPR_STONE  = _load_sprite(os.path.join(ASSETS_DIR, "stone"), (CELL, CELL))

# Entity sprites
SPR_BLACK_ANT = _load_sprite(os.path.join(ASSETS_DIR, "entities", "black_ant"), (CELL, CELL))
SPR_RED_ANT   = _load_sprite(os.path.join(ASSETS_DIR, "entities", "red_ant"), (CELL, CELL))
SPR_HORNET    = _load_sprite(os.path.join(ASSETS_DIR, "entities", "hornet"), (CELL, CELL))
SPR_WORM      = _load_sprite(os.path.join(ASSETS_DIR, "entities", "worm"), (CELL, CELL))
SPR_WORM_BIG = None
if SPR_WORM is not None:
    try:
        SPR_WORM_BIG = pygame.transform.scale(SPR_WORM, (CELL * 2, CELL * 2))
    except Exception:
        SPR_WORM_BIG = SPR_WORM
SPR_SPIDER    = _load_sprite(os.path.join(ASSETS_DIR, "entities", "spider"), (CELL*2, CELL*2))
SPR_EGG_BLACK = _load_sprite(os.path.join(ASSETS_DIR, "entities", "egg_black"), (CELL, CELL))
SPR_EGG_RED   = _load_sprite(os.path.join(ASSETS_DIR, "entities", "egg_red"), (CELL, CELL))
# Queens are 2x2 cells
SPR_BLACK_QUEEN = _load_sprite(os.path.join(ASSETS_DIR, "entities", "black_queen"), (CELL * 2, CELL * 2))
SPR_RED_QUEEN   = _load_sprite(os.path.join(ASSETS_DIR, "entities", "red_queen"), (CELL * 2, CELL * 2))

def _blit_or_rect(surf: pygame.Surface, spr: Optional[pygame.Surface], color: Tuple[int, int, int], x: int, y: int, w: int, h: int) -> None:
    if spr is not None:
        surf.blit(spr, (x, y))
    else:
        pygame.draw.rect(surf, color, (x, y, w, h))
# ---------------- WEB DRAWING / GEOMETRY ----------------

def _center_px(x: int, y: int, x0: int, y0: int) -> Tuple[int, int]:
    return (x - x0) * CELL + CELL // 2, (y - y0) * CELL + CELL // 2

def draw_webs(surf: pygame.Surface, x0: int, y0: int, x1: int, y1: int) -> None:
    """
    Render webs as particles connected by diagonal lines (and optionally a web tile sprite).
    """
    # Draw connectors first (diagonals emphasized)
    for x in range(x0, x1):
        col = web_ttl[x]
        for y in range(y0, y1):
            if col[y] <= 0:
                continue
            # connect to forward diagonals to avoid double-drawing
            for dx, dy in ((1, 1), (1, -1), (1, 0), (0, 1)):
                nx, ny = x + dx, y + dy
                if nx < x0 or nx >= x1 or ny < y0 or ny >= y1:
                    continue
                if web_ttl[nx][ny] > 0:
                    ax, ay = _center_px(x, y, x0, y0)
                    bx, by = _center_px(nx, ny, x0, y0)
                    try:
                        pygame.draw.aaline(surf, WEB_COLOR, (ax, ay), (bx, by))
                    except Exception:
                        pygame.draw.line(surf, WEB_COLOR, (ax, ay), (bx, by), 1)

    # Draw particles
    for x in range(x0, x1):
        col = web_ttl[x]
        for y in range(y0, y1):
            if col[y] <= 0:
                continue
            px = (x - x0) * CELL
            py = (y - y0) * CELL
            if SPR_T_WEB is not None:
                surf.blit(SPR_T_WEB, (px, py))
            else:
                # small "knot" particle
                pygame.draw.circle(surf, WEB_COLOR, (px + CELL // 2, py + CELL // 2), max(1, CELL // 3))

def _bresenham_line(x0: int, y0: int, x1: int, y1: int):
    """Grid line generator (inclusive endpoints)."""
    dx = abs(x1 - x0)
    dy = -abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx + dy
    x, y = x0, y0
    while True:
        yield x, y
        if x == x1 and y == y1:
            break
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x += sx
        if e2 <= dx:
            err += dx
            y += sy

def _place_octagon_ring(cx: int, cy: int, r: int) -> None:
    """Place an octagonal ring at radius r around (cx,cy)."""
    if r < 2:
        return
    d = max(1, int(r * 0.7071))  # ~ r / sqrt(2)
    pts = [
        (cx + r, cy),
        (cx + d, cy + d),
        (cx, cy + r),
        (cx - d, cy + d),
        (cx - r, cy),
        (cx - d, cy - d),
        (cx, cy - r),
        (cx + d, cy - d),
        (cx + r, cy),
    ]
    for (ax, ay), (bx, by) in zip(pts[:-1], pts[1:]):
        for x, y in _bresenham_line(ax, ay, bx, by):
            try_place_web(x, y)

def _place_radial_spokes(cx: int, cy: int, r: int, step: int = 3) -> None:
    """Place 8 radial spokes (including diagonals) out to radius r."""
    dirs = [(1,0),(-1,0),(0,1),(0,-1),(1,1),(1,-1),(-1,1),(-1,-1)]
    for dx, dy in dirs:
        x, y = cx, cy
        for i in range(0, r + 1, step):
            try_place_web(x, y)
            x += dx * step
            y += dy * step



# --- WORLD INIT (v8: real hilly terrain) ---
# Build a true terrain heightmap so hills are actual SAND/DIRT (diggable),
# not just a render overlay.
generate_surface_profile()

DIRT_DEPTH = 10          # cells below surface that transition from SAND -> DIRT
HARD_DIRT_HP = 1         # dig hits required for dirt (set to 1 so ants can always dig through)
HARD_SAND_HP = 1         # dig hits required for sand (kept for symmetry / future tuning)

def build_world_with_hills() -> List[List[Tuple[int,int,int]]]:
    w = [[AIR for _ in range(HEIGHT)] for _ in range(WIDTH)]
    for x in range(WIDTH):
        top_y = surface_y_at(x)
        if top_y < 1:
            top_y = 1
        if top_y > SURFACE_Y:
            top_y = SURFACE_Y
        for y in range(top_y, HEIGHT):
            # SAND near the surface, DIRT deeper down
            if y >= top_y + DIRT_DEPTH:
                w[x][y] = DIRT
            else:
                w[x][y] = SAND
    return w

world: List[List[Tuple[int,int,int]]] = build_world_with_hills()

# Per-cell dig hardness / hitpoints (0 means "normal dig" or non-hard tile)
dig_hp: List[List[int]] = [[0 for _ in range(HEIGHT)] for _ in range(WIDTH)]
for x in range(WIDTH):
    top_y = surface_y_at(x)
    for y in range(top_y, HEIGHT):
        if world[x][y] == DIRT:
            dig_hp[x][y] = HARD_DIRT_HP
        elif world[x][y] in (SAND, DIRT):
            dig_hp[x][y] = HARD_SAND_HP

food: List[List[bool]] = [[False for _ in range(HEIGHT)] for _ in range(WIDTH)]
poison: List[List[bool]] = [[False for _ in range(HEIGHT)] for _ in range(WIDTH)]
# Spider webs: store TTL remaining per cell (0 = no web)
web_ttl: List[List[int]] = [[0 for _ in range(HEIGHT)] for _ in range(WIDTH)]
plants: List[List[bool]] = [[False for _ in range(HEIGHT)] for _ in range(WIDTH)]  # above-ground grass pixels
flowers: List[List[bool]] = [[False for _ in range(HEIGHT)] for _ in range(WIDTH)]  # above-ground flowers
trees:   List[List[bool]] = [[False for _ in range(HEIGHT)] for _ in range(WIDTH)]  # above-ground trees
stone: List[List[bool]] = [[False for _ in range(HEIGHT)] for _ in range(WIDTH)]  # NEW

black_fort: List[List[bool]] = [[False for _ in range(HEIGHT)] for _ in range(WIDTH)]
red_fort: List[List[bool]] = [[False for _ in range(HEIGHT)] for _ in range(WIDTH)]

# v5: expanding fort radius targets (builders try to place walls near the frontier)
black_fort_growth_r = 6
red_fort_growth_r   = 6
black_fort_growth_t = 0
red_fort_growth_t   = 0
fort_auto_t = 0
black_builder_t = 0
red_builder_t = 0

# Plant growth timers
plant_grow_t = 0

# Rain (v8): periodic weather that boosts plant growth and lightly weathers exposed forts.
RAIN_INTERVAL_MIN = 60 * 25
RAIN_INTERVAL_MAX = 60 * 55
RAIN_DURATION_MIN = 60 * 10
RAIN_DURATION_MAX = 60 * 18
RAIN_DROP_SPAWN   = 14  # drops per frame (scaled later by zoom)
RAIN_WIND         = 0.15

raining = False
rain_t = 0
rain_next = random.randint(RAIN_INTERVAL_MIN, RAIN_INTERVAL_MAX)
rain_drops: List[Tuple[float,float,float]] = []  # (x,y,vy)

# Player (black) queen
queen_x = WIDTH // 2
queen_y = HEIGHT - 5
world[queen_x][queen_y] = QUEEN

# Enemy (red) queen location (top, opposite of black queen)
red_queen_x = WIDTH // 2
red_queen_y = SURFACE_Y + 3
world[red_queen_x][red_queen_y] = RED_QUEEN

queen_level = 1
queen_bites_taken = 0

red_queen_bites_taken = 0
red_queen_dead = False
hard_mode = False


def queen_bites_allowed() -> int:
    return queen_level


def queen_bites_remaining() -> int:
    return max(0, queen_bites_allowed() - queen_bites_taken)


def queen_pheromone_radius() -> int:
    r = int(PHEROMONE_BASE + queen_level * PHEROMONE_PER_LEVEL)
    return max(PHEROMONE_BASE, min(PHEROMONE_MAX, r))


# Enemy (red) nest top marker
red_nest_x = WIDTH // 2
red_nest_y = SURFACE_Y + 2  # near surface, above the red queen chamber
world[red_nest_x][red_nest_y] = RED_ANT

# alarms
alarm_active = False
alarm_x = 0
alarm_y = 0
alarm_ttl = 0


def raise_alarm(x: int, y: int) -> None:
    global alarm_active, alarm_x, alarm_y, alarm_ttl
    alarm_active = True
    alarm_x, alarm_y = x, y
    alarm_ttl = ALARM_TTL


def update_alarm() -> None:
    global alarm_active, alarm_ttl
    if not alarm_active:
        return
    alarm_ttl -= 1
    if alarm_ttl <= 0:
        alarm_active = False


def enlist_helpers(ants: List[BlackAnt]) -> None:
    if not alarm_active:
        return
    for a in ants:
        if dist2(a.x, a.y, alarm_x, alarm_y) <= ALARM_RADIUS * ALARM_RADIUS:
            a.alarm_t = FPS
            a.alarm_x = alarm_x
            a.alarm_y = alarm_y


# food ping
food_ping_active = False
food_ping_x = 0
food_ping_y = 0
food_ping_ttl = 0


def raise_food_ping(x: int, y: int) -> None:
    global food_ping_active, food_ping_x, food_ping_y, food_ping_ttl
    food_ping_active = True
    food_ping_x, food_ping_y = x, y
    food_ping_ttl = FOOD_HELP_TTL


def update_food_ping() -> None:
    global food_ping_active, food_ping_ttl
    if not food_ping_active:
        return
    food_ping_ttl -= 1
    if food_ping_ttl <= 0:
        food_ping_active = False


def enlist_food_helpers(ants: List[BlackAnt]) -> None:
    if not food_ping_active:
        return
    for a in ants:
        if a.role not in ("scout", "worker") or a.carry_food:
            continue
        if dist2(a.x, a.y, food_ping_x, food_ping_y) <= FOOD_HELP_RADIUS * FOOD_HELP_RADIUS:
            a.food_help_t = FOOD_HELP_TTL
            a.food_tx = food_ping_x
            a.food_ty = food_ping_y




def build_red_mound_preset() -> None:
    """(Disabled) The red mound feature was removed per request.

    Previously this pre-built a visible above-ground mound and entrance tunnel. The map now uses
    the visual hill surface-profile for above-ground terrain instead.
    """
    return
def clampi(v: int, a: int, b: int) -> int:
    return a if v < a else (b if v > b else v)

def maybe_assign_red_surface(rr: 'RedAnt') -> None:
    """Give a subset of red raiders a topside exploration task."""
    if getattr(rr, "role", "") == "builder":
        return
    # low chance to avoid destabilizing the colony AI
    if random.random() > 0.20:
        return
    rr.surface_t = random.randint(220, 520)
    rr.surface_tx = clampi(red_nest_x + random.randint(-24, 24), 2, WIDTH - 3)
    rr.surface_ty = clampi((SURFACE_Y - 2) + random.randint(-10, -1), 1, SURFACE_Y - 1)

def decay_webs() -> None:
    for x in range(WIDTH):
        col = web_ttl[x]
        for y in range(HEIGHT):
            if col[y] > 0:
                col[y] -= 1


def try_place_web(x: int, y: int) -> bool:
    if not in_bounds(x, y):
        return False
    # User request: spider's domain is above ground; keep webs in AIR only.
    if world[x][y] != AIR:
        return False
    web_ttl[x][y] = WEB_TTL
    return True


def apply_web_traps() -> None:
    # Trap ants/hornets standing on active web tiles
    for a in ants:
        if a.trapped_t <= 0 and web_ttl[a.x][a.y] > 0:
            a.trapped_t = WEB_TRAP_TICKS
    for r in red_ants:
        if r.trapped_t <= 0 and web_ttl[r.x][r.y] > 0:
            r.trapped_t = WEB_TRAP_TICKS
    for h in hornets:
        hx, hy = int(round(h.x)), int(round(h.y))
        if in_bounds(hx, hy) and h.trapped_t <= 0 and web_ttl[hx][hy] > 0:
            h.trapped_t = WEB_TRAP_TICKS


# Spider "domain" / web home
spider_home_x = 0
spider_home_y = 0
spider_web_r = 14
spider_web_base_r = 14  # fixed initial web radius (no expansion)


def build_structured_web() -> Tuple[int, int]:
    """Build a structured octagonal web grid in a random above-ground spot (AIR only).

    Returns the (home_x, home_y) anchor for the spider.
    """
    # pick a roomy patch of AIR, away from edges
    x = random.randint(30, WIDTH - 31)
    y = random.randint(8, max(10, SURFACE_Y - 26))

    # Ensure anchor is actually in the AIR domain
    for _ in range(80):
        if in_bounds(x, y) and y < SURFACE_Y - 2 and world[x][y] == AIR:
            break
        x = random.randint(30, WIDTH - 31)
        y = random.randint(8, max(10, SURFACE_Y - 26))

    cx, cy = x, y

    # Initial web: multiple octagon rings + radial spokes (includes diagonal connectivity)
    base_r = random.randint(10, 16)
    global spider_web_base_r
    spider_web_base_r = base_r
    for r in range(4, base_r + 1, 3):
        _place_octagon_ring(cx, cy, r)
    _place_radial_spokes(cx, cy, base_r, step=2)

    return cx, cy


def find_nearest_trapped(sp: Spider, max_r: int = 80):
    best = None
    best_d = 10**9
    # black ants
    for a in ants:
        if a.trapped_t > 0:
            d2 = dist2(sp.x, sp.y, a.x, a.y)
            if d2 < best_d and d2 <= max_r*max_r:
                best_d = d2
                best = ('black', a)
    for r in red_ants:
        if r.trapped_t > 0:
            d2 = dist2(sp.x, sp.y, r.x, r.y)
            if d2 < best_d and d2 <= max_r*max_r:
                best_d = d2
                best = ('red', r)
    for h in hornets:
        if h.trapped_t > 0:
            hx, hy = int(round(h.x)), int(round(h.y))
            if not in_bounds(hx, hy):
                continue
            d2 = dist2(sp.x, sp.y, hx, hy)
            if d2 < best_d and d2 <= max_r*max_r:
                best_d = d2
                best = ('hornet', h)
    return best


def update_spider(sp: Spider) -> None:
    # Place webs periodically, but keep the original structured web shape (no expansion).
    global spider_web_base_r
    if sp.web_cool > 0:
        sp.web_cool -= 1
    else:
        sp.web_cool = SPIDER_WEB_EVERY + random.randint(-30, 60)
        # Re-stamp the initial octagonal rings + spokes to keep the web intact.
        base_r = max(8, int(spider_web_base_r))
        for r in range(4, base_r + 1, 3):
            _place_octagon_ring(spider_home_x, spider_home_y, r)
        _place_radial_spokes(spider_home_x, spider_home_y, base_r, step=2)
    # hunt trapped victims
    target = find_nearest_trapped(sp, max_r=100)
    if target is not None:
        kind, obj = target
        if kind == 'hornet':
            tx, ty = int(round(obj.x)), int(round(obj.y))
        else:
            tx, ty = obj.x, obj.y
        dx, dy = step_toward_noisy(sp.x, sp.y, tx, ty)
        nx, ny = sp.x + dx, sp.y + dy
        if in_bounds(nx, ny) and ny < SURFACE_Y and world[nx][ny] == AIR:
            sp.x, sp.y = nx, ny

        # eat if adjacent
        if abs(sp.x - tx) <= 1 and abs(sp.y - ty) <= 1:
            if sp.eat_cool > 0:
                sp.eat_cool -= 1
            else:
                sp.eat_cool = SPIDER_EAT_COOLDOWN
                if kind == 'black':
                    obj.hp -= 2
                    if obj.hp <= 0 and obj in ants:
                        ants.remove(obj)
                elif kind == 'red':
                    obj.hp -= 2
                    if obj.hp <= 0 and obj in red_ants:
                        red_ants.remove(obj)
                else:
                    # hornet dies quickly
                    obj.trapped_t = 0
                    if obj in hornets:
                        hornets.remove(obj)
    else:
        # wander around its web home (AIR only)
        if random.random() < 0.70:
            tx, ty = spider_home_x, spider_home_y
            dx, dy = step_toward_noisy(sp.x, sp.y, tx, ty)
        else:
            dx, dy = random.choice([(-1,0),(1,0),(0,-1),(0,1),(-1,-1),(1,-1),(-1,1),(1,1)])
        nx, ny = sp.x + dx, sp.y + dy
        if in_bounds(nx, ny) and ny < SURFACE_Y and world[nx][ny] == AIR:
            sp.x, sp.y = nx, ny


def _is_surface_cell(x: int, y: int) -> bool:
    """True if (x,y) is on/near the current surface (for crater effects)."""
    try:
        sy = surface_y_at(x)
    except Exception:
        sy = SURFACE_Y
    return y <= sy + 1

def _count_fort_neighbors(fort_grid: List[List[bool]], x: int, y: int) -> int:
    c = 0
    for nx, ny in neighbors4(x, y):
        if fort_grid[nx][ny]:
            c += 1
    return c

def _collapse_forts_around(x: int, y: int, is_red: bool) -> None:
    """Probabilistically collapse weakly-supported fort blocks near a breach."""
    fort_grid = red_fort if is_red else black_fort
    fort_color = RED_FORT_COLOR if is_red else BLACK_FORT_COLOR
    # Check a small neighborhood.
    for xx in range(max(1, x - 2), min(WIDTH - 2, x + 3)):
        for yy in range(max(1, y - 2), min(HEIGHT - 2, y + 3)):
            if not fort_grid[xx][yy]:
                continue
            # If it has little support, it may collapse into rubble.
            supports = _count_fort_neighbors(fort_grid, xx, yy)
            if supports <= 1 and random.random() < 0.55:
                fort_grid[xx][yy] = False
                # rubble becomes sand (still diggable) rather than staying a wall
                world[xx][yy] = SAND
                dig_hp[xx][yy] = HARD_SAND_HP
                if stone[xx][yy]:
                    stone[xx][yy] = False

def _make_crater(cx: int, cy: int, r: int = 2) -> None:
    """Remove some near-surface terrain to visually create a breached crater."""
    r2 = r * r
    for x in range(cx - r, cx + r + 1):
        for y in range(cy - r, cy + r + 1):
            if not in_bounds(x, y):
                continue
            if dist2(x, y, cx, cy) > r2:
                continue
            # Only carve in the above-ground band (keeps underground stable)
            if y >= SURFACE_Y:
                continue
            if world[x][y] in (SAND, DIRT):
                world[x][y] = AIR
                dig_hp[x][y] = 0
                plants[x][y] = False

def dig(x: int, y: int, strength: int = 1, is_red: bool = False) -> bool:
    """Dig with hardness support (v8):
    - SAND is 1-hit, DIRT takes multiple hits, forts take many hits.
    - Fort breaches can collapse nearby weak fort tiles into rubble.
    - Near-surface digs can create small craters for visible breaches.
    """
    if not in_bounds(x, y):
        return False

    t = world[x][y]
    # Never dig queens.
    if t in (QUEEN, RED_QUEEN):
        return False

    # Diggable terrain / structures
    diggable = (SAND, DIRT, CLUTTER, RED_FORTRESS, BLACK_FORT_COLOR, RED_FORT_COLOR)
    if t not in diggable:
        return False

    # Determine HP if not initialized (keeps backwards-compat safe)
    if dig_hp[x][y] <= 0:
        if t == DIRT:
            dig_hp[x][y] = HARD_DIRT_HP
        elif t == SAND:
            dig_hp[x][y] = HARD_SAND_HP
        elif t == BLACK_FORT_COLOR:
            dig_hp[x][y] = BLACK_FORT_HP
        elif t == RED_FORT_COLOR:
            dig_hp[x][y] = RED_FORT_HP
        elif t == CLUTTER:
            dig_hp[x][y] = 1
        else:
            dig_hp[x][y] = 3

    dig_hp[x][y] -= max(1, int(strength))
    if dig_hp[x][y] > 0:
        return False

    # Tile breaks
    was_fort_black = (t == BLACK_FORT_COLOR)
    was_fort_red   = (t == RED_FORT_COLOR)

    world[x][y] = TUNNEL
    dig_hp[x][y] = 0
    stone[x][y] = False  # digging clears stone resource

    # Crater breaches at/near the surface
    if _is_surface_cell(x, y) and y < SURFACE_Y:
        _make_crater(x, y, r=2)

    # Fort collapse behavior
    if was_fort_black:
        black_fort[x][y] = False
        _collapse_forts_around(x, y, is_red=False)
    elif was_fort_red:
        red_fort[x][y] = False
        _collapse_forts_around(x, y, is_red=True)

    return True



def carve_worm_tunnel(cx: int, cy: int, r: int) -> None:
    """Carve a slightly rounder tunnel for the earthworm, using the SAME TUNNEL tile as ants."""
    if r <= 0:
        if in_bounds(cx, cy) and world[cx][cy] not in (AIR, WATER):
            world[cx][cy] = TUNNEL
            dig_hp[cx][cy] = 0
            food[cx][cy] = False
            poison[cx][cy] = False
            plants[cx][cy] = False
            stone[cx][cy] = False
        return

    r2 = r * r
    for x in range(cx - r, cx + r + 1):
        for y in range(cy - r, cy + r + 1):
            if not in_bounds(x, y):
                continue
            if (x - cx) * (x - cx) + (y - cy) * (y - cy) > r2:
                continue
            # worm never carves into AIR; keep tunnels at/under surface
            if y < SURFACE_Y:
                continue
            if world[x][y] == AIR:
                continue
            # Keep identical to ant tunnels: use the TUNNEL tile
            world[x][y] = TUNNEL
            dig_hp[x][y] = 0
            food[x][y] = False
            poison[x][y] = False
            plants[x][y] = False
            stone[x][y] = False
def carve_disk(cx: int, cy: int, r: int) -> None:
    r2 = r*r
    for x in range(cx-r, cx+r+1):
        for y in range(cy-r, cy+r+1):
            if not in_bounds(x, y):
                continue
            if dist2(x, y, cx, cy) <= r2 and world[x][y] in (SAND, DIRT):
                world[x][y] = TUNNEL
                stone[x][y] = False


def carve_small_main_chamber() -> None:
    carve_disk(queen_x, max(2, queen_y-4), 4)
    for k in range(1, 8):
        x, y = queen_x, queen_y - k
        if in_bounds(x, y) and world[x][y] in (SAND, DIRT):
            world[x][y] = TUNNEL
            stone[x][y] = False


def carve_red_main_chamber() -> None:
    """Create a rounded red chamber plus a starting surface dirt mound and entrance tunnel.

    - The dirt mound is placed in the AIR band above the surface (RED_MOUND_COLOR).
    - The entrance/tunnel starts at the surface sand row (SURFACE_Y) and connects down.
    - The chamber is carved using overlapping disks for a more organic shape.
    """
    cx = red_queen_x

    # 1) Surface dirt mound (in AIR band only)
    mound_base_y = SURFACE_Y - 1
    for dx in range(-8, 9):
        h = max(0, int(5 - abs(dx) * 0.55) + random.randint(-1, 1))
        for k in range(h):
            x = cx + dx
            y = mound_base_y - k
            if in_bounds(x, y) and y < SURFACE_Y and world[x][y] == AIR:
                world[x][y] = RED_MOUND_COLOR

    # 2) Entrance carved at the surface (in SAND row, never in AIR)
    entrance_y = SURFACE_Y
    for y in range(entrance_y, min(HEIGHT - 1, entrance_y + 3)):
        if in_bounds(cx, y) and world[cx][y] == SAND:
            world[cx][y] = TUNNEL
            stone[cx][y] = False

    # 3) Pocket around the queen (small)
    carve_disk(cx, min(HEIGHT - 2, red_queen_y + 1), 3)

    # 4) Rounded main chamber deeper than the queen
    chamber_cy = min(HEIGHT - 6, red_queen_y + 10)
    carve_disk(cx, chamber_cy, 7)
    carve_disk(cx - 4, chamber_cy + 1, 5)
    carve_disk(cx + 4, chamber_cy + 1, 5)

    # 5) Connect surface entrance down to the queen pocket and chamber (shaft)
    for y in range(entrance_y, min(HEIGHT - 2, chamber_cy + 1)):
        if in_bounds(cx, y) and world[cx][y] == SAND:
            world[cx][y] = TUNNEL
            stone[cx][y] = False


carve_small_main_chamber()
carve_red_main_chamber()
# --- v8: initial fort rings around queens (siege gameplay) ---
def build_initial_fort_ring(cx: int, cy: int, is_red: bool) -> None:
    fort_grid = red_fort if is_red else black_fort
    fort_color = RED_FORT_COLOR if is_red else BLACK_FORT_COLOR
    base_hp = RED_FORT_HP if is_red else BLACK_FORT_HP

    # Slightly larger defenses for the red queen since she's closer to the surface.
    ring_r = 9 if is_red else 7
    thick = 1

    # Two deliberate openings (gates) so queens are not fully sealed in.
    gate1 = (cx, max(2, cy - ring_r))  # toward the surface / up
    gate2 = (cx, min(HEIGHT - 3, cy + ring_r))  # downward

    for x in range(max(2, cx - ring_r - 2), min(WIDTH - 3, cx + ring_r + 3)):
        for y in range(max(2, cy - ring_r - 2), min(HEIGHT - 3, cy + ring_r + 3)):
            d = int(round(math.sqrt(dist2(x, y, cx, cy))))
            if d < ring_r or d > ring_r + thick:
                continue
            # Leave gates open
            if (x, y) == gate1 or (x, y) == gate2:
                continue
            # Don't overwrite queens
            if world[x][y] in (QUEEN, RED_QUEEN):
                continue
            # Place fort in solid terrain or tunnels (embedded walls)
            if world[x][y] in (SAND, DIRT, TUNNEL):
                world[x][y] = fort_color
                fort_grid[x][y] = True
                dig_hp[x][y] = base_hp

    # Queen-specific style:
    # - Black: add a couple internal spokes (harder maze)
    # - Red: add more gaps (more chaotic walls)
    if not is_red:
        for ang in (0, math.pi/2, math.pi, 3*math.pi/2):
            for k in range(2, ring_r - 1):
                x = cx + int(round(math.cos(ang) * k))
                y = cy + int(round(math.sin(ang) * k))
                if in_bounds(x, y) and world[x][y] in (SAND, DIRT, TUNNEL):
                    world[x][y] = fort_color
                    black_fort[x][y] = True
                    dig_hp[x][y] = base_hp
    else:
        for _ in range(20):
            x = random.randint(max(2, cx - ring_r), min(WIDTH - 3, cx + ring_r))
            y = random.randint(max(2, cy - ring_r), min(HEIGHT - 3, cy + ring_r))
            if red_fort[x][y] and random.random() < 0.6:
                red_fort[x][y] = False
                if world[x][y] == fort_color:
                    world[x][y] = SAND
                    dig_hp[x][y] = HARD_SAND_HP

# Build rings after chambers exist
build_initial_fort_ring(queen_x, queen_y - 3, is_red=False)
build_initial_fort_ring(red_queen_x, red_queen_y + 3, is_red=True)

def scatter_food_and_poison() -> None:
    for x in range(WIDTH):
        for y in range(HEIGHT):
            food[x][y] = False
            poison[x][y] = False

    def far_from_queen(x: int, y: int) -> bool:
        return dist2(x, y, queen_x, queen_y) >= 14*14

    placed = 0
    tries = 0
    while placed < FOOD_COUNT and tries < 20000:
        tries += 1
        x = random.randint(0, WIDTH-1)
        y = random.randint(SURFACE_Y + 1, HEIGHT-2)
        if not far_from_queen(x, y):
            continue
        if world[x][y] in (SAND, DIRT) and not food[x][y] and not poison[x][y]:
            food[x][y] = True
            placed += 1

    placed = 0
    tries = 0
    while placed < POISON_COUNT and tries < 20000:
        tries += 1
        x = random.randint(0, WIDTH-1)
        y = random.randint(SURFACE_Y + 1, HEIGHT-2)
        if not far_from_queen(x, y):
            continue
        if world[x][y] in (SAND, DIRT) and not food[x][y] and not poison[x][y]:
            poison[x][y] = True
            placed += 1


def scatter_stone() -> None:
    # NEW: place stone resources in sand
    for x in range(WIDTH):
        for y in range(HEIGHT):
            stone[x][y] = False

    placed = 0
    tries = 0
    while placed < STONE_COUNT and tries < 25000:
        tries += 1
        x = random.randint(0, WIDTH - 1)
        y = random.randint(SURFACE_Y + 2, HEIGHT - 2)
        if world[x][y] in (SAND, DIRT) and (x, y) not in ((queen_x, queen_y), (red_queen_x, red_queen_y)) and not stone[x][y]:
            stone[x][y] = True
            placed += 1




def scatter_water() -> None:
    """Generate underground water pockets that can flood tunnels when breached."""
    # Clear any previous water
    for x in range(WIDTH):
        for y in range(HEIGHT):
            if world[x][y] == WATER:
                world[x][y] = SAND

    pockets = random.randint(7, 12)
    attempts = 0
    made = 0
    while made < pockets and attempts < pockets * 25:
        attempts += 1
        cx = random.randint(10, WIDTH - 11)
        # Keep water underground (well below surface), but not at the very bottom.
        cy = random.randint(min(HEIGHT - 20, SURFACE_Y + 18), HEIGHT - 12)
        r = random.randint(3, 7)

        # Avoid queens / chambers
        if dist2(cx, cy, queen_x, queen_y) < 18 * 18:
            continue
        if dist2(cx, cy, red_queen_x, red_queen_y) < 18 * 18:
            continue

        # Fill a disk
        ok = False
        for x in range(cx - r, cx + r + 1):
            for y in range(cy - r, cy + r + 1):
                if not in_bounds(x, y):
                    continue
                if (x - cx) * (x - cx) + (y - cy) * (y - cy) <= r * r:
                    t = world[x][y]
                    if t in (SAND, DIRT, TUNNEL):
                        world[x][y] = WATER
                        # water is not diggable; keep hp at 0 so it's treated as non-solid
                        dig_hp[x][y] = 0
                        food[x][y] = False
                        poison[x][y] = False
                        stone[x][y] = False
                        ok = True
        if ok:
            made += 1


def update_water() -> None:
    """Simple, fast water flow/drain model.

    Goals:
    - If a tunnel breaches a pocket, water drains into the tunnel network.
    - Water prefers to fall downward (gravity), then spill sideways.
    - Water can drain out of the bottom of the world.

    This is intentionally lightweight (random sampling) so the sim stays fast.
    """

    # Sample a small number of cells each sim step.
    samples = 55
    for _ in range(samples):
        x = random.randint(2, WIDTH - 3)
        y = random.randint(SURFACE_Y + 1, HEIGHT - 2)
        if world[x][y] != WATER:
            continue

        # 1) Drain out of the bottom.
        if y >= HEIGHT - 2:
            world[x][y] = TUNNEL
            continue

        # 2) Gravity: fall if possible.
        below = world[x][y + 1]
        if below in (AIR, TUNNEL):
            world[x][y + 1] = WATER
            dig_hp[x][y + 1] = 0
            web_ttl[x][y + 1] = 0
            world[x][y] = TUNNEL
            dig_hp[x][y] = 0
            continue

        # 3) Spill sideways into open space (tunnels/air), slightly biased toward tunnels.
        dirs = [(-1, 0), (1, 0)]
        random.shuffle(dirs)
        moved = False
        for dx, dy in dirs:
            nx, ny = x + dx, y + dy
            if not in_bounds(nx, ny):
                continue
            nt = world[nx][ny]
            if nt in (AIR, TUNNEL):
                # A little probability keeps motion from turning into a full-grid flood fill.
                p = 0.60 if nt == TUNNEL else 0.35
                if random.random() < p:
                    world[nx][ny] = WATER
                    dig_hp[nx][ny] = 0
                    web_ttl[nx][ny] = 0
                    world[x][y] = TUNNEL
                    dig_hp[x][y] = 0
                    moved = True
                    break
        if moved:
            continue

        # 4) If touching tunnels, slowly wick into them (breach draining behavior).
        for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
            nx, ny = x + dx, y + dy
            if not in_bounds(nx, ny):
                continue
            if world[nx][ny] == TUNNEL and random.random() < 0.25:
                world[nx][ny] = WATER
                dig_hp[nx][ny] = 0
                web_ttl[nx][ny] = 0


def init_plants() -> None:
    # Clear all existing flora (grass/flowers/trees) and seed starters along the visual surface.
    for x in range(WIDTH):
        for y in range(HEIGHT):
            plants[x][y] = False
            flowers[x][y] = False
            trees[x][y] = False

    # Seed initial grass/flowers along the (bumpy) surface so it can expand over time.
    for _ in range(WIDTH * 3):
        x = random.randint(1, WIDTH - 2)
        y = surface_y_at(x) - 1
        if y <= 0:
            continue
        if world[x][y] == AIR:
            if random.random() < 0.22:
                plants[x][y] = True
            if random.random() < 0.05:
                flowers[x][y] = True

    # Seed a handful of trees (static, decorative)
    for _ in range(max(8, WIDTH // 8)):
        x = random.randint(2, WIDTH - 3)
        y = surface_y_at(x) - 1
        if y <= 1:
            continue
        if world[x][y] == AIR and not plants[x][y] and random.random() < 0.6:
            trees[x][y] = True


def update_plants() -> None:
    """Grow grass in the above-ground AIR region, pixel-by-pixel."""
    global plant_grow_t
    plant_grow_t += 1
    eff_every = PLANT_GROW_EVERY
    if raining:
        eff_every = max(1, PLANT_GROW_EVERY // 2)
    if plant_grow_t < eff_every:
        return
    plant_grow_t = 0

    # Occasionally seed a brand new blade at the surface.
    if random.random() < PLANT_SEED_CHANCE:
        x = random.randint(1, WIDTH - 2)
        y = surface_y_at(x) - 1
        if 1 <= y < SURFACE_Y and world[x][y] == AIR and (not plants[x][y]):
            plants[x][y] = True
            if random.random() < 0.10:
                flowers[x][y] = True

    # Try a small number of random growth events per pulse (keeps perf stable).
    for _ in range(PLANT_GROW_ATTEMPTS):
        x = random.randint(1, WIDTH - 2)
        y = random.randint(1, SURFACE_Y - 1)
        if not plants[x][y]:
            continue

        # Grow upward if possible.
        if y > 1 and (not plants[x][y - 1]) and world[x][y - 1] == AIR:
            plants[x][y - 1] = True
            if random.random() < 0.05:
                flowers[x][y - 1] = True
            # Optional sideways spread at the same height (makes patches)
            if random.random() < PLANT_SPREAD_CHANCE:
                sx = x + random.choice([-1, 1])
                if 1 <= sx < WIDTH - 1 and world[sx][y] == AIR and (not plants[sx][y]) and y >= surface_y_at(sx) - 1:
                    plants[sx][y] = True
                    if random.random() < 0.04:
                        flowers[sx][y] = True


scatter_food_and_poison()
scatter_stone()
scatter_water()
init_plants()

# Start both forts with exactly 1 stone pixel (adjacent to each queen)
bx0, by0 = queen_x, min(HEIGHT - 2, queen_y + 2)
if in_bounds(bx0, by0) and world[bx0][by0] == TUNNEL:
    world[bx0][by0] = BLACK_FORT_COLOR
    black_fort[bx0][by0] = True

rx0, ry0 = red_queen_x, min(HEIGHT - 2, red_queen_y + 2)
if in_bounds(rx0, ry0) and world[rx0][ry0] == TUNNEL:
    world[rx0][ry0] = RED_FORT_COLOR
    red_fort[rx0][ry0] = True

# ---------------- MAZE PLAN (built by worker ants) ----------------
maze_plan: Set[Tuple[int, int]] = set()
maze_rooms: List[Tuple[int, int, int]] = []  # (cx, cy, r)
maze_frontier: List[Tuple[int, int]] = []    # planned SAND adjacent to TUNNEL





def update_rain() -> None:
    global raining, rain_t, rain_next

    if raining:
        rain_t -= 1
        # Spawn drops across the map (simple; drawing is clipped to camera)
        for _ in range(RAIN_DROP_SPAWN):
            x = random.uniform(0, WIDTH - 1)
            y = random.uniform(0, max(1, surface_y_at(int(x)) - 10))
            vy = random.uniform(0.6, 1.4)
            rain_drops.append((x, y, vy))

        # Update drops
        new_drops = []
        for x, y, vy in rain_drops:
            y2 = y + vy
            x2 = x + RAIN_WIND
            if y2 < HEIGHT - 1:
                # Stop when hitting terrain
                xi, yi = int(x2), int(y2)
                if in_bounds(xi, yi) and world[xi][yi] in (SAND, DIRT, BLACK_FORT_COLOR, RED_FORT_COLOR):
                    # small chance to soften exposed fort/soil
                    pass
                else:
                    new_drops.append((x2, y2, vy))
        rain_drops[:] = new_drops[-2500:]  # cap list size

        # Weathering: during rain, exposed forts slowly weaken
        if random.random() < 0.20:
            x = random.randint(2, WIDTH - 3)
            sy = surface_y_at(x)
            for y in range(max(1, sy), min(HEIGHT - 2, sy + 3)):
                if world[x][y] == BLACK_FORT_COLOR and dig_hp[x][y] > 0:
                    dig_hp[x][y] -= 1
                    if dig_hp[x][y] <= 0:
                        world[x][y] = SAND
                        black_fort[x][y] = False
                        dig_hp[x][y] = HARD_SAND_HP
                    break
                if world[x][y] == RED_FORT_COLOR and dig_hp[x][y] > 0:
                    dig_hp[x][y] -= 1
                    if dig_hp[x][y] <= 0:
                        world[x][y] = SAND
                        red_fort[x][y] = False
                        dig_hp[x][y] = HARD_SAND_HP
                    break

        if rain_t <= 0:
            raining = False
            rain_sfx.stop()
            rain_next = random.randint(RAIN_INTERVAL_MIN, RAIN_INTERVAL_MAX)
    else:
        rain_next -= 1
        if rain_next <= 0:
            raining = True
            rain_sfx.start()
            rain_t = random.randint(RAIN_DURATION_MIN, RAIN_DURATION_MAX)
def ensure_hornet_asset_folders(app_dir: str) -> None:
    """Create an assets folder for hornet sprites if missing (no README generation)."""
    base = os.path.join(app_dir, "assets", "hornets")
    try:
        os.makedirs(base, exist_ok=True)
    except Exception:
        pass


def load_first_png(folder: str) -> Optional[pygame.Surface]:
    """Load the first .png in a folder alphabetically; return None if none."""
    try:
        if not os.path.isdir(folder):
            return None
        files = sorted([fn for fn in os.listdir(folder) if fn.lower().endswith(".png")])
        if not files:
            return None
        p = os.path.join(folder, files[0])
        return pygame.image.load(p).convert_alpha()
    except Exception:
        return None


def spawn_one_hornet() -> Hornet:
    """Spawn a hornet in the above-ground AIR band."""
    ymax = max(2, SURFACE_Y - 6)
    hx = float(random.randint(5, WIDTH - 6))
    hy = float(random.randint(2, ymax))
    h = Hornet(x=hx, y=hy)
    h.tx = float(random.randint(5, WIDTH - 6))
    h.ty = float(random.randint(2, ymax))
    h.wander_t = random.randint(HORNET_WANDER_T // 2, HORNET_WANDER_T)
    return h


def init_hornets() -> List[Hornet]:
    hornets: List[Hornet] = []
    for _ in range(HORNET_COUNT):
        hornets.append(spawn_one_hornet())
    return hornets


def update_hornets(hornets: List[Hornet]) -> None:
    """Fly around in AIR and attack any ants lingering on/near the surface."""
    # User request: if a hornet dies, spawn a new one.
    # Maintain a stable population.
    while len(hornets) < HORNET_COUNT:
        hornets.append(spawn_one_hornet())
    if not hornets:
        return

    seek_r2 = HORNET_SEEK_RADIUS * HORNET_SEEK_RADIUS
    ymax = max(1, SURFACE_Y - 1)

    for h in hornets:
        if h.trapped_t > 0:
            h.trapped_t -= 1
            continue
        if h.bite_cool > 0:
            h.bite_cool -= 1

        # Find nearest surface target (either team)
        target_team = None
        target_idx = -1
        best_d2 = 1_000_000

        # Consider ants that are at/near the surface band.
        # NOTE: hornets stay in AIR, so they primarily hit ants that are at y==SURFACE_Y or in the air band just above it.
        for i, a in enumerate(ants):
            if a.y > SURFACE_Y + 1:
                continue
            d2 = dist2(int(h.x), int(h.y), a.x, a.y)
            if d2 <= seek_r2 and d2 < best_d2:
                best_d2 = d2
                target_team = "black"
                target_idx = i

        for i, a in enumerate(red_ants):
            if a.y > SURFACE_Y + 1:
                continue
            d2 = dist2(int(h.x), int(h.y), a.x, a.y)
            if d2 <= seek_r2 and d2 < best_d2:
                best_d2 = d2
                target_team = "red"
                target_idx = i

        # Set waypoint
        if target_team is not None and target_idx >= 0:
            if target_team == "black":
                tx = float(ants[target_idx].x)
                ty = float(ants[target_idx].y)
            else:
                tx = float(red_ants[target_idx].x)
                ty = float(red_ants[target_idx].y)
            h.tx, h.ty = tx, ty
            h.wander_t = random.randint(20, 45)
        else:
            h.wander_t -= 1
            if h.wander_t <= 0:
                h.tx = float(random.randint(2, WIDTH - 3))
                h.ty = float(random.randint(1, max(1, SURFACE_Y - 3)))
                h.wander_t = random.randint(HORNET_WANDER_T // 2, HORNET_WANDER_T)

        # Move toward waypoint (simple steering)
        dx = h.tx - h.x
        dy = h.ty - h.y
        d = math.hypot(dx, dy)
        if d > 0.0001:
            h.vx = (dx / d) * HORNET_SPEED
            h.vy = (dy / d) * HORNET_SPEED
        else:
            h.vx = 0.0
            h.vy = 0.0

        h.x += h.vx
        h.y += h.vy

        # Constrain to world bounds, but hornets may only occupy AIR or TUNNEL.
        if h.x < 0:
            h.x = 0.0
        if h.x > WIDTH - 1:
            h.x = float(WIDTH - 1)
        if h.y < 0:
            h.y = 0.0
        if h.y > HEIGHT - 1:
            h.y = float(HEIGHT - 1)

        # Block hornets from moving through solid terrain (sand/dirt/forts/etc.).
        xi, yi = int(h.x), int(h.y)
        if in_bounds(xi, yi) and world[xi][yi] not in (AIR, TUNNEL):
            # revert this step and force a new wander target
            h.x -= h.vx
            h.y -= h.vy
            h.wander_t = 0

        # Bite if we are close enough to a surface ant
        if h.bite_cool <= 0:
            hx = int(h.x)
            hy = int(h.y)

            # Black ants: only those at/near surface
            for k in range(len(ants) - 1, -1, -1):
                a = ants[k]
                if a.y > SURFACE_Y + 1:
                    continue
                # If ant is in sand/tunnel, hornet attacks from above surface edge
                ay = a.y
                if ay >= SURFACE_Y:
                    # must be adjacent to surface line
                    if abs(hx - a.x) <= 1 and abs(hy - (SURFACE_Y - 1)) <= 1:
                        a.hp -= HORNET_DAMAGE
                        h.bite_cool = HORNET_BITE_COOLDOWN
                        if a.hp <= 0:
                            ants.pop(k)
                        break
                else:
                    # ant is above ground already
                    if abs(hx - a.x) <= 1 and abs(hy - ay) <= 1:
                        a.hp -= HORNET_DAMAGE
                        h.bite_cool = HORNET_BITE_COOLDOWN
                        if a.hp <= 0:
                            ants.pop(k)
                        break

            # Red ants
            if h.bite_cool <= 0:
                for k in range(len(red_ants) - 1, -1, -1):
                    a = red_ants[k]
                    if a.y > SURFACE_Y + 1:
                        continue
                    ay = a.y
                    if ay >= SURFACE_Y:
                        if abs(hx - a.x) <= 1 and abs(hy - (SURFACE_Y - 1)) <= 1:
                            a.hp -= HORNET_DAMAGE
                            h.bite_cool = HORNET_BITE_COOLDOWN
                            if a.hp <= 0:
                                red_ants.pop(k)
                            break
                    else:
                        if abs(hx - a.x) <= 1 and abs(hy - ay) <= 1:
                            a.hp -= HORNET_DAMAGE
                            h.bite_cool = HORNET_BITE_COOLDOWN
                            if a.hp <= 0:
                                red_ants.pop(k)
                            break

def maze_region() -> Tuple[int, int, int, int]:
    """
    Define a rectangular region around the black queen where workers will build the maze.
    """
    x0 = max(1, queen_x - MAZE_MARGIN_X)
    x1 = min(WIDTH - 2, queen_x + MAZE_MARGIN_X)
    y0 = max(2, queen_y - MAZE_MARGIN_Y_TOP)
    y1 = min(HEIGHT - 2, queen_y + MAZE_MARGIN_Y_BOTTOM)
    return x0, y0, x1, y1


def _oddify(v: int) -> int:
    return v if (v % 2 == 1) else v + 1


def generate_maze_plan() -> None:
    """
    Create a *plan* (maze_plan set) of cells that should be dug into TUNNEL by worker ants.
    The plan is a classic perfect maze carved on odd coordinates, plus several round chambers.
    """
    global maze_plan, maze_rooms, maze_frontier
    maze_plan = set()
    maze_rooms = []
    maze_frontier = []

    x0, y0, x1, y1 = maze_region()
    # Ensure odd bounds for a classic maze (odd cells are nodes; even cells are walls in-between)
    sx = _oddify(x0)
    sy = _oddify(y0)
    ex = x1 if (x1 % 2 == 1) else x1 - 1
    ey = y1 if (y1 % 2 == 1) else y1 - 1

    # Safety: if region too small, just do nothing (workers will behave as before)
    if ex - sx < 5 or ey - sy < 5:
        return

    def maze_neighbors(cx: int, cy: int) -> List[Tuple[int, int, int, int]]:
        # returns list of (nx, ny, wx, wy) where w* is the wall cell between
        out = []
        for dx, dy in [(2,0), (-2,0), (0,2), (0,-2)]:
            nx, ny = cx + dx, cy + dy
            wx, wy = cx + dx // 2, cy + dy // 2
            if sx <= nx <= ex and sy <= ny <= ey:
                out.append((nx, ny, wx, wy))
        random.shuffle(out)
        return out

    # start near the queen, but inside the region
    start_x = min(max(sx, _oddify(queen_x)), ex)
    start_y = min(max(sy, _oddify(queen_y - 12)), ey)

    visited: Set[Tuple[int, int]] = set()
    stack = [(start_x, start_y)]
    visited.add((start_x, start_y))
    maze_plan.add((start_x, start_y))

    while stack:
        cx, cy = stack[-1]
        nxt = None
        for nx, ny, wx, wy in maze_neighbors(cx, cy):
            if (nx, ny) not in visited:
                nxt = (nx, ny, wx, wy)
                break
        if nxt is None:
            stack.pop()
            continue
        nx, ny, wx, wy = nxt
        visited.add((nx, ny))
        # carve: node + wall between
        maze_plan.add((wx, wy))
        maze_plan.add((nx, ny))
        stack.append((nx, ny))

    # Connect the plan to the existing main chamber / shaft by guaranteeing a corridor touching it
    best = None
    best_d2 = 10**9
    for (mx, my) in maze_plan:
        d2 = dist2(mx, my, queen_x, queen_y - 6)
        if d2 < best_d2:
            best_d2 = d2
            best = (mx, my)
    if best:
        bx, by = best
        # carve a short Manhattan connector in plan
        cx, cy = queen_x, queen_y - 6
        while cx != bx:
            cx += 1 if bx > cx else -1
            maze_plan.add((cx, cy))
        while cy != by:
            cy += 1 if by > cy else -1
            maze_plan.add((cx, cy))

    # Add chambers
    nodes = [(x, y) for (x, y) in maze_plan if (x % 2 == 1 and y % 2 == 1)]
    random.shuffle(nodes)
    chamber_count = 0
    attempts = 0
    while chamber_count < MAZE_TARGET_CHAMBERS and attempts < 200 and nodes:
        attempts += 1
        cx, cy = nodes.pop()
        if cy > queen_y - 6:
            continue
        r = random.randint(MAZE_ROOM_R_MIN, MAZE_ROOM_R_MAX)
        ok = True
        for rx, ry, rr in maze_rooms:
            if dist2(cx, cy, rx, ry) <= (r + rr + 3) ** 2:
                ok = False
                break
        if not ok:
            continue
        for x in range(cx - r, cx + r + 1):
            for y in range(cy - r, cy + r + 1):
                if not (x0 <= x <= x1 and y0 <= y <= y1):
                    continue
                if dist2(x, y, cx, cy) <= r * r:
                    maze_plan.add((x, y))
        maze_rooms.append((cx, cy, r))
        chamber_count += 1

    rebuild_maze_frontier()


def rebuild_maze_frontier() -> None:
    """
    Frontier = planned cells that are still SAND but adjacent to an existing TUNNEL.
    Workers can safely dig these without disconnecting the maze.
    """
    global maze_frontier
    maze_frontier = []
    if not maze_plan:
        return
    for (x, y) in maze_plan:
        if not in_bounds(x, y):
            continue
        if world[x][y] != SAND:
            continue
        for nx, ny in neighbors4(x, y):
            if world[nx][ny] == TUNNEL:
                maze_frontier.append((x, y))
                break
    random.shuffle(maze_frontier)


generate_maze_plan()

# ---------------- PERSONALITIES ----------------
# Equal distribution: we cycle roles so each new black ant gets the next role in a fixed rotation.
PERSONALITIES = ["worker", "guard", "scout", "warrior"]
personality_idx = 0


def next_personality() -> str:
    global personality_idx
    p = PERSONALITIES[personality_idx % len(PERSONALITIES)]
    personality_idx += 1
    return p


def make_black_ant_at(x: int, y: int, role: Optional[str] = None) -> BlackAnt:
    role = role if role is not None else next_personality()
    return BlackAnt(
        x=x,
        y=y,
        role=role,
        hp=BLACK_HP,
        dir=pick_branch_dir(),
        dir_ticks=random.randint(10, 35),
        cool=random.randint(0, BLACK_STEP_FRAMES),
        dig_cool=random.randint(0, BLACK_DIG_COOLDOWN),
        bite_cool=random.randint(0, BLACK_BITE_COOLDOWN),
        build_cool=random.randint(0, FPS),
        build_tx=None,
        build_ty=None,
        mounder=(random.random() < MOUND_TRAIT_CHANCE),
        carry_sand=False,
        mound_cool=random.randint(0, MOUND_BUILD_COOLDOWN),
    )


def make_black_ant() -> BlackAnt:
    return make_black_ant_at(
        x=queen_x + random.randint(-3, 3),
        y=queen_y - random.randint(0, 5),
    )


ants: List[BlackAnt] = [make_black_ant() for _ in range(START_BLACK_ANTS)]
red_ants: List[RedAnt] = []

eggs: List[Egg] = []
egg_spawn_timer = 0

red_eggs: List[RedEgg] = []
red_egg_spawn_timer = 0

hard_spawn_t = 0

# Earthworm (neutral hazard)
DIR8: List[Tuple[int, int]] = [
    (0, -1),   # N
    (1, -1),   # NE
    (1, 0),    # E
    (1, 1),    # SE
    (0, 1),    # S
    (-1, 1),   # SW
    (-1, 0),   # W
    (-1, -1),  # NW
]

wx0 = random.randint(10, WIDTH - 10)
wy0 = random.randint(max(SURFACE_Y + 10, 20), HEIGHT - 20)
h0 = random.randint(0, 7)
tx, ty = DIR8[(h0 + 4) % 8]  # opposite direction
segs: List[Tuple[int, int]] = []
for i in range(WORM_LENGTH):
    sx = wx0 + tx * i
    sy = wy0 + ty * i
    if in_bounds(sx, sy):
        segs.append((sx, sy))
if not segs:
    segs = [(wx0, wy0)]

worm = Earthworm(
    x=segs[0][0],
    y=segs[0][1],
    segments=segs,
    heading=h0,
    dir_ticks=random.randint(40, 90),
    cool=random.randint(0, WORM_STEP_FRAMES),
)


def find_food_near(ax: int, ay: int, radius: int = FOOD_SCAN_RADIUS) -> Optional[Tuple[int, int]]:
    r = radius
    r2 = r * r
    best = None
    best_d2 = 1_000_000
    x0 = max(0, ax - r)
    x1 = min(WIDTH - 1, ax + r)
    y0 = max(0, ay - r)
    y1 = min(HEIGHT - 1, ay + r)
    for x in range(x0, x1 + 1):
        fx = food[x]
        gx = plants[x]
        for y in range(y0, y1 + 1):
            if (not fx[y]) and (not gx[y]):
                continue
            d2 = dist2(ax, ay, x, y)
            if d2 <= r2 and d2 < best_d2:
                best = (x, y)
                best_d2 = d2
    return best


# ---------------- EGG SPAWNING ----------------
def spawn_egg_in_built_room() -> bool:
    if not maze_rooms:
        return False

    room_order = maze_rooms[:]
    random.shuffle(room_order)
    for cx, cy, r in room_order:
        for _ in range(90):
            ox = random.randint(-r + 1, r - 1)
            oy = random.randint(-r + 1, r - 1)
            x = cx + ox
            y = cy + oy
            if not in_bounds(x, y):
                continue
            if (x, y) == (queen_x, queen_y):
                continue
            if world[x][y] != TUNNEL:
                continue
            if poison[x][y]:
                continue
            if any(e.x == x and e.y == y for e in eggs):
                continue
            eggs.append(Egg(x=x, y=y, hatch_t=EGG_HATCH_AFTER))
            return True
    return False


def spawn_egg_near_queen_fallback() -> None:
    candidates: List[Tuple[int,int]] = []
    for _ in range(60):
        x = queen_x + random.randint(-4, 4)
        y = queen_y + random.randint(-4, 2)
        if not in_bounds(x, y) or (x, y) == (queen_x, queen_y):
            continue
        if world[x][y] in (AIR, TUNNEL):
            if any(e.x == x and e.y == y for e in eggs):
                continue
            candidates.append((x, y))
    if not candidates:
        return
    x, y = random.choice(candidates)
    eggs.append(Egg(x=x, y=y, hatch_t=EGG_HATCH_AFTER))


def spawn_egg_near_queen() -> None:
    if not spawn_egg_in_built_room():
        spawn_egg_near_queen_fallback()


def spawn_red_egg_near_red_queen() -> None:
    candidates: List[Tuple[int, int]] = []
    for _ in range(40):
        ox = random.randint(-4, 4)
        oy = random.randint(-2, 4)
        x = red_queen_x + ox
        y = red_queen_y + oy
        if not in_bounds(x, y):
            continue
        if (x, y) == (red_queen_x, red_queen_y):
            continue
        if world[x][y] in (AIR, TUNNEL):
            if any(e.x == x and e.y == y for e in red_eggs):
                continue
            candidates.append((x, y))
    if not candidates:
        return
    x, y = random.choice(candidates)
    red_eggs.append(RedEgg(x=x, y=y, hatch_t=RED_EGG_HATCH_AFTER))


# --------------- CAMERA / RENDER ---------------
cam_x, cam_y = 0.0, 0.0
zoom = 1.0
zoom_target = 1.0

zoom_anchor_active = False
# Anchor world point that should remain stable during smooth zoom.
# We use *center-anchored zoom* to avoid the "fighting tension" of cursor zoom.
zoom_anchor_world = (0.0, 0.0)


def dynamic_zoom_min() -> float:
    win_w, win_h = screen.get_size()
    zx = win_w / max(1.0, (WIDTH * CELL))
    zy = win_h / max(1.0, (HEIGHT * CELL))
    return max(0.25, zx, zy)


def clamp_camera() -> None:
    sc = max(1.0, CELL * zoom)
    win_w, win_h = screen.get_size()
    view_w = max(1.0, win_w / sc)
    view_h = max(1.0, win_h / sc)
    global cam_x, cam_y
    max_x = max(0.0, WIDTH - view_w)
    max_y = max(0.0, HEIGHT - view_h)
    cam_x = max(0.0, min(cam_x, max_x))
    cam_y = max(0.0, min(cam_y, max_y))


def center_camera_on(wx: float, wy: float) -> None:
    win_w, win_h = screen.get_size()
    sc = max(1.0, CELL * zoom)
    cam_w = win_w / sc
    cam_h = win_h / sc
    global cam_x, cam_y
    cam_x = wx - cam_w / 2.0
    cam_y = wy - cam_h / 2.0
    clamp_camera()


def zoom_at_center(step_dir: int) -> None:
    """Zoom in/out anchored on the *camera center* (screen center).

    This avoids the "two directions fighting" feeling that can happen with
    cursor-anchored zoom combined with camera clamping and smoothing.
    """
    global zoom_target, cam_x, cam_y
    global zoom_anchor_active, zoom_anchor_world

    win_w, win_h = screen.get_size()
    win_w = max(1, win_w)
    win_h = max(1, win_h)

    # Current visible size in world-cells at the current zoom.
    view_w_before = win_w / max(1.0, CELL * zoom)
    view_h_before = win_h / max(1.0, CELL * zoom)

    # Current world point at the camera center.
    center_wx = cam_x + view_w_before * 0.5
    center_wy = cam_y + view_h_before * 0.5

    if step_dir > 0:
        zoom_target *= ZOOM_STEP
    elif step_dir < 0:
        zoom_target /= ZOOM_STEP

    zmin = dynamic_zoom_min()
    zoom_target = clamp(zoom_target, zmin, ZOOM_MAX)

    # New visible size at the target zoom; keep the same world center.
    view_w_after = win_w / max(1.0, CELL * zoom_target)
    view_h_after = win_h / max(1.0, CELL * zoom_target)
    cam_x = center_wx - view_w_after * 0.5
    cam_y = center_wy - view_h_after * 0.5

    zoom_anchor_active = True
    zoom_anchor_world = (float(center_wx), float(center_wy))
    clamp_camera()


zoom_target = max(1.0, dynamic_zoom_min())
zoom = zoom_target
center_camera_on(float(queen_x), float(queen_y))

# Speed slider UI state
GAME_SPEED = 1.0
speed_accum = 0.0
slider_drag = False


def slider_rect() -> pygame.Rect:
    win_w, win_h = screen.get_size()
    w, h = 280, 22
    x = win_w - w - 18
    y = win_h - h - 18
    return pygame.Rect(x, y, w, h)


def slider_knob_rect(r: pygame.Rect) -> pygame.Rect:
    t = (GAME_SPEED - SPEED_MIN) / (SPEED_MAX - SPEED_MIN)
    kx = int(r.x + t * r.w)
    return pygame.Rect(kx - 9, r.y - 6, 18, r.h + 12)


def mute_button_rect() -> pygame.Rect:
    # Small UI button just above the speed slider (bottom-right).
    r = slider_rect()
    w, h = 160, 34
    x = r.right - w
    y = r.y - 26 - 18
    return pygame.Rect(x, y, w, h)


def apply_slider_from_mouse(mx: int, r: pygame.Rect) -> None:
    global GAME_SPEED
    t = (mx - r.x) / max(1, r.w)
    t = clamp(t, 0.0, 1.0)
    GAME_SPEED = SPEED_MIN + t * (SPEED_MAX - SPEED_MIN)



def screen_to_world_cell(mx: int, my: int) -> Optional[Tuple[int, int]]:
    """Convert a screen pixel coordinate to a world cell coordinate (x,y)."""
    win_w, win_h = screen.get_size()
    win_w = max(1, win_w)
    win_h = max(1, win_h)
    view_w = win_w / max(1.0, CELL * zoom)
    view_h = win_h / max(1.0, CELL * zoom)
    wx = cam_x + (mx / win_w) * view_w
    wy = cam_y + (my / win_h) * view_h
    ix, iy = int(wx), int(wy)
    if not in_bounds(ix, iy):
        return None
    return ix, iy


def hover_name_at_cell(x: int, y: int) -> Optional[str]:
    # Queens (2x2 footprint)
    if queen_x <= x <= queen_x + 1 and queen_y <= y <= queen_y + 1:
        return "black queen ant"
    if red_queen_x <= x <= red_queen_x + 1 and red_queen_y <= y <= red_queen_y + 1:
        return "red queen ant"

    # Worm segments
    for sx, sy in worm.segments:
        if sx == x and sy == y:
            return "earthworm"

    # Hornets
    for h in hornets:
        if int(h.x) == x and int(h.y) == y:
            return "hornet"

    # Eggs
    for eg in eggs:
        if eg.x == x and eg.y == y:
            return "black egg"
    for eg in red_eggs:
        if eg.x == x and eg.y == y:
            return "red egg"

    # Ants
    for a in ants:
        if a.x == x and a.y == y:
            return "black ant"
    for r in red_ants:
        if r.x == x and r.y == y:
            return "red ant"

    # Resources
    if food[x][y]:
        return "food"
    if poison[x][y]:
        return "poison"
    if plants[x][y]:
        return "grass"
    if stone[x][y]:
        return "stone"

    # Terrain
    t = world[x][y]
    if t == SAND:
        return None  # ignore sand
    if t == TUNNEL:
        return "tunnel"
    if t == AIR:
        return None  # ignore air
    if t == CLUTTER:
        return "clutter"
    if t == MOUND_COLOR:
        return "mound"
    if t == RED_MOUND_COLOR:
        return "red dirt mound"
    if t == RED_FORTRESS:
        return "red fortress wall"
    if t == BLACK_FORT_COLOR:
        return "black fortress"
    if t == RED_FORT_COLOR:
        return "red fortress"

    return None


def draw_tooltip(text: str, mx: int, my: int) -> None:
    """Draw a small hover label near the mouse cursor."""
    if not text:
        return
    pad_x, pad_y = 6, 4
    surf = ui_font.render(text, True, (255, 255, 255))
    tw, th = surf.get_size()
    win_w, win_h = screen.get_size()

    x = mx + 14
    y = my + 14
    # clamp so it stays on-screen
    if x + tw + pad_x * 2 > win_w:
        x = max(0, win_w - (tw + pad_x * 2))
    if y + th + pad_y * 2 > win_h:
        y = max(0, win_h - (th + pad_y * 2))

    bg = pygame.Surface((tw + pad_x * 2, th + pad_y * 2), pygame.SRCALPHA)
    bg.fill((0, 0, 0, 170))
    screen.blit(bg, (x, y))
    screen.blit(surf, (x + pad_x, y + pad_y))




def draw_spider(surf: pygame.Surface, px: int, py: int, cell_px: int) -> None:
    """Draw a simple spider (body + legs) at pixel coords within the pre-zoom view surface."""
    if SPR_SPIDER is not None:
        # Center a 2x2-cell sprite on the spider position
        surf.blit(SPR_SPIDER, (px - CELL, py - CELL))
        return
    r = max(2, cell_px // 2)
    body = (20, 20, 20)
    leg = (15, 15, 15)
    # Body
    pygame.draw.circle(surf, body, (px, py), r)
    pygame.draw.circle(surf, (0,0,0), (px, py), max(1, r-1), 1)
    # 8 legs
    L = max(4, cell_px * 2)
    offsets = [(-1,-1),(-1,0),(-1,1), (1,-1),(1,0),(1,1), (0,-1),(0,1)]
    for ox, oy in offsets:
        x2 = px + ox * L
        y2 = py + oy * (L//2)
        pygame.draw.line(surf, leg, (px, py), (x2, y2), 1)
def render_world() -> None:
    win_w, win_h = screen.get_size()

    sc = max(1.0, CELL * zoom)
    view_w = int(win_w / sc) + 2
    view_h = int(win_h / sc) + 2

    x0 = max(0, int(math.floor(cam_x)))
    y0 = max(0, int(math.floor(cam_y)))

    frac_x = cam_x - x0
    frac_y = cam_y - y0
    x1 = min(WIDTH, x0 + view_w)
    y1 = min(HEIGHT, y0 + view_h)

    surf_w = max(1, (x1 - x0) * CELL)
    surf_h = max(1, (y1 - y0) * CELL)
    view_surf = pygame.Surface((surf_w, surf_h), pygame.SRCALPHA)

    # Terrain + resources (drawn first)
    for x in range(x0, x1):
        px = (x - x0) * CELL
        col = world[x]
        fcol = food[x]
        pcol = poison[x]
        scol = stone[x]
        for y in range(y0, y1):
            py = (y - y0) * CELL
            t = col[y]

            # Treat queens / nest marker as background tunnel, then draw entities later.
            if t in (QUEEN, RED_QUEEN, RED_ANT):
                t = TUNNEL

            if t == SAND:
                _blit_or_rect(view_surf, SPR_T_SAND, (_shade(SAND, terrain_var[x][y]) if terrain_var else SAND), px, py, CELL, CELL)
            elif t == DIRT:
                _blit_or_rect(view_surf, SPR_T_DIRT, (_shade(DIRT, terrain_var[x][y]) if terrain_var else DIRT), px, py, CELL, CELL)
            elif t == TUNNEL:
                _blit_or_rect(view_surf, SPR_T_TUNNEL, (_shade(TUNNEL, (terrain_var[x][y]//2 - 6)) if terrain_var else TUNNEL), px, py, CELL, CELL)
            elif t == WATER:
                _blit_or_rect(view_surf, SPR_T_WATER, WATER, px, py, CELL, CELL)
            elif t == CLUTTER:
                _blit_or_rect(view_surf, SPR_T_CLUTTER, CLUTTER, px, py, CELL, CELL)
            elif t in (MOUND_COLOR, RED_MOUND_COLOR):
                # Mound feature disabled; treat as air.
                if SPR_T_AIR is not None:
                    view_surf.blit(SPR_T_AIR, (px, py))
                else:
                    pygame.draw.rect(view_surf, AIR, (px, py, CELL, CELL))
            elif t == BLACK_FORT_COLOR:
                _blit_or_rect(view_surf, SPR_T_FORTRESS, BLACK_FORT_COLOR, px, py, CELL, CELL)
            elif t == RED_FORT_COLOR:
                _blit_or_rect(view_surf, SPR_T_FORTRESS, RED_FORT_COLOR, px, py, CELL, CELL)
            elif t == RED_FORTRESS:
                _blit_or_rect(view_surf, SPR_T_FORTRESS, RED_FORTRESS, px, py, CELL, CELL)
            else:
                if SPR_T_AIR is not None:
                    view_surf.blit(SPR_T_AIR, (px, py))
                else:
                    pygame.draw.rect(view_surf, AIR, (px, py, CELL, CELL))


            # Tunnel edge shading for readability (renderer-only)
            if t == TUNNEL:
                wall = _shade(TUNNEL, -35)
                # Top
                if y > 0 and world[x][y - 1] != TUNNEL:
                    pygame.draw.line(view_surf, wall, (px, py), (px + CELL - 1, py), 1)
                # Bottom
                if y < HEIGHT - 1 and world[x][y + 1] != TUNNEL:
                    pygame.draw.line(view_surf, wall, (px, py + CELL - 1), (px + CELL - 1, py + CELL - 1), 1)
                # Left
                if x > 0 and world[x - 1][y] != TUNNEL:
                    pygame.draw.line(view_surf, wall, (px, py), (px, py + CELL - 1), 1)
                # Right
                if x < WIDTH - 1 and world[x + 1][y] != TUNNEL:
                    pygame.draw.line(view_surf, wall, (px + CELL - 1, py), (px + CELL - 1, py + CELL - 1), 1)

            # Overlays (resources)
            if fcol[y]:
                _blit_or_rect(view_surf, SPR_FOOD, FOOD_COLOR, px, py, CELL, CELL)
            if pcol[y]:
                _blit_or_rect(view_surf, SPR_POISON, POISON_COLOR, px, py, CELL, CELL)
            # Flora overlays (above-ground)
            if trees[x][y]:
                _blit_or_rect(view_surf, SPR_TREE, (40, 90, 40), px, py, CELL, CELL)
            if plants[x][y]:
                _blit_or_rect(view_surf, SPR_PLANT, PLANT_COLOR, px, py, CELL, CELL)
            if flowers[x][y]:
                _blit_or_rect(view_surf, SPR_FLOWER, (255, 220, 240), px, py, CELL, CELL)
            if scol[y]:
                _blit_or_rect(view_surf, SPR_STONE, STONE_COLOR, px, py, CELL, CELL)

    # Eggs
    for eg in eggs:
        if x0 <= eg.x < x1 and y0 <= eg.y < y1:
            _blit_or_rect(view_surf, SPR_EGG_BLACK, EGG_COLOR, (eg.x - x0) * CELL, (eg.y - y0) * CELL, CELL, CELL)

    for eg in red_eggs:
        if x0 <= eg.x < x1 and y0 <= eg.y < y1:
            _blit_or_rect(view_surf, SPR_EGG_RED, RED_EGG_COLOR, (eg.x - x0) * CELL, (eg.y - y0) * CELL, CELL, CELL)

    # Ants
    for a in ants:
        if x0 <= a.x < x1 and y0 <= a.y < y1:
            _blit_or_rect(view_surf, SPR_BLACK_ANT, ANT, (a.x - x0) * CELL, (a.y - y0) * CELL, CELL, CELL)

    for r in red_ants:
        if x0 <= r.x < x1 and y0 <= r.y < y1:
            _blit_or_rect(view_surf, SPR_RED_ANT, RED_ANT, (r.x - x0) * CELL, (r.y - y0) * CELL, CELL, CELL)

    # Worm body (tail-to-head)
    for idx in range(len(worm.segments) - 1, -1, -1):
        sx, sy = worm.segments[idx]
        if x0 <= sx < x1 and y0 <= sy < y1:
            px = (sx - x0) * CELL
            py = (sy - y0) * CELL
            if SPR_WORM_BIG is not None:
                view_surf.blit(SPR_WORM_BIG, (px - CELL // 2, py - CELL // 2))
            elif SPR_WORM is not None:
                view_surf.blit(SPR_WORM, (px, py))
            else:
                pygame.draw.rect(view_surf, WORM_COLOR, (px - CELL // 2, py - CELL // 2, CELL * 2, CELL * 2))
    # Webs
    # Webs (rendered above terrain, below entities): draw particles + diagonal connector lines
    draw_webs(view_surf, x0, y0, x1, y1)

    # Spider
    if x0 <= spider.x < x1 and y0 <= spider.y < y1:
        spx = (spider.x - x0) * CELL + CELL // 2
        spy = (spider.y - y0) * CELL + CELL // 2
        draw_spider(view_surf, int(spx), int(spy), CELL)

    # Hornets (AIR entities)
    for h in hornets:
        hx, hy = int(h.x), int(h.y)
        if x0 <= hx < x1 and y0 <= hy < y1:
            _blit_or_rect(view_surf, SPR_HORNET, HORNET_COLOR, (hx - x0) * CELL, (hy - y0) * CELL, CELL, CELL)

    # Queens (2x2)
    if x0 <= queen_x < x1 and y0 <= queen_y < y1:
        qpx = (queen_x - x0) * CELL - 2
        qpy = (queen_y - y0) * CELL - 2
        if SPR_BLACK_QUEEN is not None:
            view_surf.blit(SPR_BLACK_QUEEN, (qpx, qpy))
        else:
            pygame.draw.rect(view_surf, QUEEN, (qpx, qpy, CELL * 2, CELL * 2))

    if x0 <= red_queen_x < x1 and y0 <= red_queen_y < y1:
        qpx = (red_queen_x - x0) * CELL - 2
        qpy = (red_queen_y - y0) * CELL - 2
        if SPR_RED_QUEEN is not None:
            view_surf.blit(SPR_RED_QUEEN, (qpx, qpy))
        else:
            pygame.draw.rect(view_surf, RED_QUEEN, (qpx, qpy, CELL * 2, CELL * 2))

        
    # Rain overlay (v8)
    if raining and rain_drops:
        for rx, ry, rvy in rain_drops[-1200:]:
            if x0 <= rx < x1 and y0 <= ry < y1:
                px = int((rx - x0) * CELL)
                py = int((ry - y0) * CELL)
                # short diagonal streak
                pygame.draw.line(view_surf, (200, 200, 255, 140), (px, py), (px + 2, py + 5), 1)
# Scale to zoom, then blit with sub-cell offset to eliminate camera jitter.
    out_w = max(1, int(round(view_surf.get_width() * zoom)))
    out_h = max(1, int(round(view_surf.get_height() * zoom)))

    # Smoother scaling at low zoom; crisp scaling when zoomed in.
    if zoom < 1.0:
        scaled = pygame.transform.smoothscale(view_surf, (out_w, out_h))
    else:
        scaled = pygame.transform.scale(view_surf, (out_w, out_h))

    off_x = int(round(-frac_x * CELL * zoom))
    off_y = int(round(-frac_y * CELL * zoom))

    # Fill background (prevents edge artifacts when panning near borders)
    screen.fill((0, 0, 0))
    screen.blit(scaled, (off_x, off_y))


    # HUD (top-left)
    # Queen HP is represented as remaining "endurance".
    b_allowed = max(1, queen_bites_allowed())
    b_rem = max(0, queen_bites_remaining())
    b_pct = int(round((b_rem / float(b_allowed)) * 100.0))

    r_allowed = max(1, RED_QUEEN_HP)
    r_rem = max(0, RED_QUEEN_HP - red_queen_bites_taken)
    r_pct = int(round((r_rem / float(r_allowed)) * 100.0))

    hud_lines = [
        f"Black Queen HP {b_pct}%",
        f"Red Queen HP {r_pct}%",
        f"Black Queen Level {queen_level}",
        f"Ants  Black:{len(ants)}  Red:{len(red_ants)}",
        f"Hornets: {len(hornets)}",
    ]
    line_h = max(26, small_font.get_linesize() + 6)
    panel_w = max(_ui_chip(line, font=small_font).get_width() for line in hud_lines) + 12
    panel_h = 12 + line_h * len(hud_lines)
    hud_rect = pygame.Rect(12, 12, panel_w, panel_h)
    _draw_panel(hud_rect, fill=(7, 9, 14, 165))
    hud_y = hud_rect.y + 6
    for line in hud_lines:
        _draw_ui_chip(line, hud_rect.x + 6, hud_y, font=small_font, bg=(0, 0, 0, 0))
        hud_y += line_h

    # Speed slider overlay (bottom-right)
    r = slider_rect()
    _draw_panel(r, fill=(12, 14, 18, 180))
    inner = r.inflate(-6, -6)
    pygame.draw.rect(screen, (38, 48, 62), inner, border_radius=8)
    t = (GAME_SPEED - SPEED_MIN) / max(0.0001, (SPEED_MAX - SPEED_MIN))
    active_r = pygame.Rect(inner.x, inner.y, max(14, int(inner.w * t)), inner.h)
    pygame.draw.rect(screen, (104, 176, 255), active_r, border_radius=8)
    k = slider_knob_rect(r)
    pygame.draw.rect(screen, (245, 248, 252), k, border_radius=8)
    _draw_ui_chip(f"Speed x{GAME_SPEED:.1f}", r.x, r.y - 44, font=small_font)

    # Music mute button (above slider)
    mb = mute_button_rect()
    _draw_panel(mb, fill=(12, 14, 18, 180))
    mtxt = "Unmute" if music_muted else "Mute"
    _draw_ui_chip(mtxt, mb.centerx, mb.centery, font=small_font, anchor="center", bg=(0, 0, 0, 0))
    _draw_ui_chip("Esc / E: Return to Island", 14, screen.get_height() - 14, font=small_font, anchor="bottomleft")

    # Hover tooltip (name of what the cursor is over)
    mx, my = pygame.mouse.get_pos()
    cell = screen_to_world_cell(mx, my)
    if cell is not None:
        hx, hy = cell
        name = hover_name_at_cell(hx, hy)
        if name:
            draw_tooltip(name, mx, my)


# --------------- RESET ----------------
# --------------- RESET ----------------
def reset_game() -> None:
    global world, food, poison, plants, stone, ants, red_ants
    global queen_level, queen_bites_taken
    global red_queen_bites_taken, red_queen_dead, hard_mode
    global cam_x, cam_y, zoom, zoom_target
    global alarm_active, alarm_ttl
    global food_ping_active, food_ping_ttl
    global eggs, egg_spawn_timer
    global red_eggs, red_egg_spawn_timer
    global hard_spawn_t
    global personality_idx
    global GAME_SPEED, speed_accum
    global worm
    global maze_plan, maze_rooms, maze_frontier
    global red_fort_radius, red_fort_expand_t
    global black_fort, red_fort
    global black_builder_t, red_builder_t
    global plant_grow_t
    global hornets
    global web_ttl
    global spider

    world = [[(AIR if y < SURFACE_Y else (MOUND_COLOR if y == SURFACE_Y else SAND)) for y in range(HEIGHT)] for _ in range(WIDTH)]
    food = [[False for _ in range(HEIGHT)] for _ in range(WIDTH)]
    poison = [[False for _ in range(HEIGHT)] for _ in range(WIDTH)]
    plants = [[False for _ in range(HEIGHT)] for _ in range(WIDTH)]
    stone = [[False for _ in range(HEIGHT)] for _ in range(WIDTH)]

    web_ttl = [[0 for _ in range(HEIGHT)] for _ in range(WIDTH)]

    _build_terrain_variation()


    black_fort = [[False for _ in range(HEIGHT)] for _ in range(WIDTH)]
    red_fort = [[False for _ in range(HEIGHT)] for _ in range(WIDTH)]

    # v5: reset fort growth pacing
    global black_fort_growth_r, red_fort_growth_r, black_fort_growth_t, red_fort_growth_t
    black_fort_growth_r = 6
    red_fort_growth_r = 6
    black_fort_growth_t = 0
    red_fort_growth_t = 0


    world[queen_x][queen_y] = QUEEN
    world[red_queen_x][red_queen_y] = RED_QUEEN
    world[red_nest_x][red_nest_y] = RED_ANT

    carve_small_main_chamber()
    carve_red_main_chamber()
    scatter_food_and_poison()
    scatter_stone()
    init_plants()

    # Start both forts with exactly 1 stone pixel (adjacent to each queen)
    bx0, by0 = queen_x, min(HEIGHT - 2, queen_y + 2)
    if in_bounds(bx0, by0) and world[bx0][by0] == TUNNEL:
        world[bx0][by0] = BLACK_FORT_COLOR
        black_fort[bx0][by0] = True

    rx0, ry0 = red_queen_x, min(HEIGHT - 2, red_queen_y + 2)
    if in_bounds(rx0, ry0) and world[rx0][ry0] == TUNNEL:
        world[rx0][ry0] = RED_FORT_COLOR
        red_fort[rx0][ry0] = True

    generate_maze_plan()

    personality_idx = 0
    plant_grow_t = 0
    ants = [make_black_ant() for _ in range(START_BLACK_ANTS)]
    # Ensure at least one builder from the beginning
    ants.append(make_black_ant_at(queen_x, queen_y - 1, role="builder"))

    red_ants = []
    # Ensure at least one red builder from the beginning (so fort can start expanding)
    red_ants.append(RedAnt(x=red_nest_x, y=red_nest_y, role="builder", cool=random.randint(0, RED_STEP_FRAMES), mounder=(random.random() < MOUND_TRAIT_CHANCE), mound_cool=random.randint(0, MOUND_BUILD_COOLDOWN)))
    try:
        maybe_assign_red_surface(red_ants[-1])
    except Exception:
        pass



    eggs = []
    egg_spawn_timer = 0
    red_eggs = []
    red_egg_spawn_timer = 0

    queen_level = 1
    queen_bites_taken = 0

    red_queen_bites_taken = 0
    red_queen_dead = False
    hard_mode = False
    hard_spawn_t = 0

    alarm_active = False
    alarm_ttl = 0
    food_ping_active = False
    food_ping_ttl = 0

    GAME_SPEED = 1.0
    speed_accum = 0.0

    # reset legacy fortress (still used for some movement constraints)
    red_fort_radius = 18
    red_fort_expand_t = 0

    # builder hatch timers
    black_builder_t = 0
    red_builder_t = 0

    # new worm
    wx0 = random.randint(10, WIDTH - 10)
    wy0 = random.randint(max(SURFACE_Y + 10, 20), HEIGHT - 20)
    h0 = random.randint(0, 7)
    tx2, ty2 = DIR8[(h0 + 4) % 8]
    segs2 = []
    for i in range(WORM_LENGTH):
        sx = wx0 + tx2 * i
        sy = wy0 + ty2 * i
        if in_bounds(sx, sy):
            segs2.append((sx, sy))
    if not segs2:
        segs2 = [(wx0, wy0)]
    worm = Earthworm(
        x=segs2[0][0],
        y=segs2[0][1],
        segments=segs2,
        heading=h0,
        dir_ticks=random.randint(40, 90),
        cool=random.randint(0, WORM_STEP_FRAMES),
    )

    # Hornets are the only entities allowed to spawn in the AIR band.
    hornets = init_hornets()
    # Spider lives above ground near plants/air. Build a structured web once and
    # place the spider at its home anchor.
    global spider_home_x, spider_home_y, spider_web_r

    spider_home_x, spider_home_y = build_structured_web()
    spider_web_r = 14  # starting radius for ongoing expansion
    spider = Spider(x=spider_home_x, y=spider_home_y)

    zmin = dynamic_zoom_min()
    zoom_target = max(1.0, zmin)
    zoom = zoom_target
    center_camera_on(float(queen_x), float(queen_y))
    # NOTE: red fortress is NOT pre-generated; builders must construct it in realtime.

    # first enemy egg at start
    spawn_red_egg_near_red_queen()


# ---------------- RED FORTRESS BUILDING ----------------
red_fort_radius = 18
red_fort_expand_t = 0
RED_FORT_EXPAND_EVERY = FPS * 6   # periodically increase the build radius
RED_FORT_BUILD_COOLDOWN = 6       # builder action cadence (in sim steps)


def walkable_neighbors_count(x: int, y: int) -> int:
    c = 0
    for nx, ny in neighbors4(x, y):
        if is_walkable(world[nx][ny]):
            c += 1
    return c


def red_fortress_region_contains(x: int, y: int) -> bool:
    return (abs(x - red_queen_x) <= red_fort_radius) and (abs(y - red_queen_y) <= red_fort_radius)


def red_pick_wall_target(ax: int, ay: int) -> Optional[Tuple[int, int]]:
    best = None
    best_d = 10**9
    r = red_fort_radius
    x0 = max(2, red_queen_x - r)
    x1 = min(WIDTH - 3, red_queen_x + r)
    y0 = max(2, red_queen_y - r)
    y1 = min(HEIGHT - 3, red_queen_y + r)
    for _ in range(220):
        x = random.randint(x0, x1)
        y = random.randint(y0, y1)
        if not red_fortress_region_contains(x, y):
            continue
        if world[x][y] != TUNNEL:
            continue
        if dist2(x, y, red_queen_x, red_queen_y) <= 3*3:
            continue
        if dist2(x, y, queen_x, queen_y) <= 3*3:
            continue
        if walkable_neighbors_count(x, y) < 3:
            continue
        if any(e.x == x and e.y == y for e in eggs) or any(e.x == x and e.y == y for e in red_eggs):
            continue
        if any(a.x == x and a.y == y for a in ants) or any(r2.x == x and r2.y == y for r2 in red_ants):
            continue
        d = dist2(ax, ay, x, y)
        if d < best_d:
            best_d = d
            best = (x, y)
    return best


def red_place_wall(x: int, y: int, rx: int, ry: int) -> bool:
    # NEW: placing a wall requires consuming nearby stone.
    if not in_bounds(x, y):
        return False
    if world[x][y] != TUNNEL:
        return False
    for nx, ny in neighbors4(rx, ry):
        if in_bounds(nx, ny) and stone[nx][ny] and world[nx][ny] == SAND:
            stone[nx][ny] = False
            world[x][y] = RED_FORTRESS
            return True
    return False


def red_place_labyrinth_wall(cx: int, cy: int, rmax: int) -> bool:
    """
    Generate / refresh an expanding, structured fortress maze around the red queen.
    - Walls are RED_FORTRESS tiles.
    - Paths are TUNNEL tiles.
    """
    global red_fort_radius

    red_fort_radius = max(red_fort_radius, rmax)
    r = red_fort_radius
    x0 = max(2, red_queen_x - r)
    x1 = min(WIDTH - 3, red_queen_x + r)
    y0 = max(2, red_queen_y - r)
    y1 = min(HEIGHT - 3, red_queen_y + r)

    w = x1 - x0 + 1
    h = y1 - y0 + 1
    if w % 2 == 0:
        if x1 < WIDTH - 3: x1 += 1
        else: x0 += 1
    if h % 2 == 0:
        if y1 < HEIGHT - 3: y1 += 1
        else: y0 += 1
    w = x1 - x0 + 1
    h = y1 - y0 + 1

    if w < 9 or h < 9:
        return False

    grid = [[0 for _ in range(h)] for _ in range(w)]

    def carve_room(cxg: int, cyg: int, rw: int, rh: int) -> None:
        xra = max(1, cxg - rw // 2)
        xrb = min(w - 2, cxg + rw // 2)
        yra = max(1, cyg - rh // 2)
        yrb = min(h - 2, cyg + rh // 2)
        for xx in range(xra, xrb + 1):
            for yy in range(yra, yrb + 1):
                grid[xx][yy] = 1

    sx = (red_queen_x - x0) | 1
    sy = (red_queen_y - y0) | 1
    grid[sx][sy] = 1
    stack = [(sx, sy)]
    dirs = [(2, 0), (-2, 0), (0, 2), (0, -2)]

    while stack:
        cxg, cyg = stack[-1]
        random.shuffle(dirs)
        advanced = False
        for dx, dy in dirs:
            nx, ny = cxg + dx, cyg + dy
            if 1 <= nx < w - 1 and 1 <= ny < h - 1 and grid[nx][ny] == 0:
                grid[nx][ny] = 1
                grid[cxg + dx // 2][cyg + dy // 2] = 1
                stack.append((nx, ny))
                advanced = True
                break
        if not advanced:
            stack.pop()

    for _ in range(4):
        cxg = random.randrange(3, w - 3, 2)
        cyg = random.randrange(3, h - 3, 2)
        carve_room(cxg, cyg, rw=5, rh=5)

    qlx = red_queen_x - x0
    qly = red_queen_y - y0
    carve_room(qlx, qly, rw=7, rh=7)

    for lx in range(w):
        wx = x0 + lx
        for ly in range(h):
            wy = y0 + ly
            if wy == 0:
                continue
            if wx == red_queen_x and wy == red_queen_y:
                continue
            if grid[lx][ly] == 1:
                if world[wx][wy] != AIR:
                    world[wx][wy] = TUNNEL
                    stone[wx][wy] = False
            else:
                if world[wx][wy] != AIR:
                    world[wx][wy] = RED_FORTRESS
                    stone[wx][wy] = False

    return True


# NOTE: red fortress is NOT pre-generated; builders must construct it in realtime.


def red_try_steal_food(r: RedAnt) -> bool:
    if food[r.x][r.y] or plants[r.x][r.y]:
        food[r.x][r.y] = False
        plants[r.x][r.y] = False
        r.carrying_food = True
        return True
    return False


# --------------- INPUT / CAMERA ---------------
panning = False
pan_last = (0, 0)

# first enemy egg at start
spawn_red_egg_near_red_queen()

# Hornets: only things allowed to spawn in the AIR band
hornets = init_hornets()

# Spider (above-ground predator)
spider_home_x, spider_home_y = build_structured_web()
spider = Spider(x=spider_home_x, y=spider_home_y)

# ---------------- LOOP ----------------
ensure_sfx_folders()
# init SFX after pygame is ready; mixer may already be initialized by music
sfx.init()
sfx.load()
init_music()

running = True
while running:

    if 'spawn_tree_once' in globals():
        spawn_tree_once()
        tree_growth_timer += 1
        if tree_growth_timer >= TREE_GROW_INTERVAL:
            tree_growth_timer = 0
            grow_tree_step()

    clock.tick(FPS)
    tick_music()

    # Smooth zoom
    zmin = dynamic_zoom_min()
    if zoom_target < zmin:
        zoom_target = zmin
    zoom += (zoom_target - zoom) * ZOOM_SMOOTHING

    # Maintain center-anchored zoom during smoothing.
    if zoom_anchor_active:
        wx, wy = zoom_anchor_world
        win_w, win_h = screen.get_size()
        win_w = max(1, win_w)
        win_h = max(1, win_h)
        view_w = win_w / max(1.0, CELL * zoom)
        view_h = win_h / max(1.0, CELL * zoom)
        cam_x = wx - view_w * 0.5
        cam_y = wy - view_h * 0.5
        clamp_camera()
        if abs(zoom - zoom_target) < 0.001:
            zoom_anchor_active = False

    for e in pygame.event.get():
        DBG_EVENT = e
        if e.type == pygame.QUIT:
            running = False

        if e.type == pygame.VIDEORESIZE:
            screen = pygame.display.set_mode((e.w, e.h), pygame.RESIZABLE)
            zmin = dynamic_zoom_min()
            if zoom_target < zmin:
                zoom_target = zmin
            clamp_camera()

        if e.type == pygame.KEYDOWN:
            if e.key == pygame.K_r:
                reset_game()

            # Camera hotkeys
            elif e.key == pygame.K_f:
                # Toggle fullscreen
                try:
                    if (screen.get_flags() & pygame.FULLSCREEN) != 0:
                        screen = pygame.display.set_mode((WIN_W, WIN_H), pygame.RESIZABLE)
                    else:
                        screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
                    zmin = dynamic_zoom_min()
                    if zoom_target < zmin:
                        zoom_target = zmin
                    clamp_camera()
                except Exception:
                    pass
            elif e.key == pygame.K_z:
                zoom_at_center(+1)
            elif e.key == pygame.K_x:
                zoom_at_center(-1)
            elif e.key == pygame.K_1:
                center_camera_on(float(queen_x), float(queen_y))
            elif e.key == pygame.K_2:
                center_camera_on(float(red_queen_x), float(red_queen_y))
            elif e.key == pygame.K_3:
                center_camera_on(float(WIDTH // 2), float(HEIGHT // 2))
        # Mouse wheel zoom (supports both pygame 2 MOUSEWHEEL and older button-4/5)
        if e.type == getattr(pygame, 'MOUSEWHEEL', -1):
            dy = getattr(e, 'y', 0)
            if dy:
                zoom_at_center(int(dy))
        elif e.type == pygame.MOUSEBUTTONDOWN and getattr(e, 'button', 0) in (4, 5):
            zoom_at_center(1 if e.button == 4 else -1)

        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            mx, my = e.pos

            # Mute / unmute button
            if mute_button_rect().collidepoint(mx, my):
                toggle_music_muted()
                continue

            sr = slider_rect()
            if sr.collidepoint(mx, my) or slider_knob_rect(sr).collidepoint(mx, my):
                slider_drag = True
                apply_slider_from_mouse(mx, sr)
            else:
                # Click-to-center camera on the clicked world location.
                wc = screen_to_world_cell(mx, my)
                if wc is not None:
                    wx, wy = wc
                    center_camera_on(float(wx) + 0.5, float(wy) + 0.5)

        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 3:
            # Right-click drag pans (keeps left-click reserved for centering)
            panning = True
            pan_last = e.pos

        if e.type == pygame.MOUSEBUTTONUP and e.button == 1:
            slider_drag = False

        if e.type == pygame.MOUSEBUTTONUP and e.button == 3:
            panning = False

        if e.type == pygame.MOUSEMOTION:
            mx, my = e.pos
            if slider_drag:
                apply_slider_from_mouse(mx, slider_rect())
            elif panning:
                dx = (mx - pan_last[0]) / max(1.0, CELL * zoom)
                dy = (my - pan_last[1]) / max(1.0, CELL * zoom)
                cam_x -= dx
                cam_y -= dy
                pan_last = e.pos
                clamp_camera()

    # Keyboard camera pan (WASD + arrows): small, continuous nudges.
    keys = pygame.key.get_pressed()
    pan_step = 0.55 / max(0.35, zoom)
    if keys[pygame.K_a] or keys[pygame.K_LEFT]:
        cam_x -= pan_step
    if keys[pygame.K_d] or keys[pygame.K_RIGHT]:
        cam_x += pan_step
    if keys[pygame.K_w] or keys[pygame.K_UP]:
        cam_y -= pan_step
    if keys[pygame.K_s] or keys[pygame.K_DOWN]:
        cam_y += pan_step

    zoom_target = clamp(zoom_target, dynamic_zoom_min(), ZOOM_MAX)
    zoom = clamp(zoom, dynamic_zoom_min(), ZOOM_MAX)
    clamp_camera()

    update_alarm()
    update_food_ping()

    # Simulation speed: run N logic steps per rendered frame (stable at low speed)
    speed_accum += GAME_SPEED
    sim_steps = int(speed_accum)
    if sim_steps > 60:
        sim_steps = 60
    if sim_steps < 0:
        sim_steps = 0
    speed_accum -= sim_steps

    for _step in range(sim_steps):
        # Plants (above-ground) grow over time
        update_plants()
        # Weather
        update_rain()
        update_water()

        # Hornets fly in AIR and harass surface units
        update_hornets(hornets)

        # Spider webs
        decay_webs()
        apply_web_traps()
        update_spider(spider)

        # Builder hatch tick: spawn 1 new builder per team every 5 game minutes
        black_builder_t += 1
        red_builder_t += 1
        if black_builder_t >= BUILDER_HATCH_EVERY:
            black_builder_t = 0
            # spawn near black queen in tunnel
            ants.append(make_black_ant_at(queen_x + random.randint(-2, 2), queen_y - random.randint(0, 3), role="builder"))
        if red_builder_t >= BUILDER_HATCH_EVERY:
            red_builder_t = 0
            if len(red_ants) < RED_MAX:
                red_ants.append(RedAnt(x=red_nest_x, y=red_nest_y, role="builder", cool=random.randint(0, RED_STEP_FRAMES), mounder=(random.random() < MOUND_TRAIT_CHANCE), mound_cool=random.randint(0, MOUND_BUILD_COOLDOWN)))
                try:
                    maybe_assign_red_surface(red_ants[-1])
                except Exception:
                    pass
        # v5: expand fort build radius targets (keeps both forts growing outward over time)
        black_fort_growth_t += 1
        red_fort_growth_t += 1
        if black_fort_growth_t >= FORT_GROW_EVERY:
            black_fort_growth_t = 0
            black_fort_growth_r = min(FORT_GROW_MAX, black_fort_growth_r + FORT_GROW_STEP)
        if red_fort_growth_t >= FORT_GROW_EVERY:
            red_fort_growth_t = 0
            red_fort_growth_r = min(FORT_GROW_MAX, red_fort_growth_r + FORT_GROW_STEP)

        # v8.1: Periodic automatic fort expansion around queens so sieges keep evolving
        # (Builders still help, but this guarantees forts grow even if builders are busy.)
        fort_auto_t += 1
        if fort_auto_t >= FORT_AUTO_BUILD_EVERY:
            fort_auto_t = 0
            # a few placement attempts per team
            for _ in range(FORT_AUTO_BUILD_ATTEMPTS):
                try_place_fort_block(is_red=False, near_x=queen_x, near_y=queen_y)
                try_place_fort_block(is_red=True, near_x=red_queen_x, near_y=red_queen_y)



        # Hard-mode pressure
        if hard_mode:
            hard_spawn_t += 1
            if hard_spawn_t >= FPS * 10:
                hard_spawn_t = 0
                sp = None
                for _ in range(200):
                    sx = random.randint(2, WIDTH - 3)
                    sy = random.randint(2, HEIGHT // 2)
                    if world[sx][sy] == TUNNEL and dist2(sx, sy, red_queen_x, red_queen_y) <= red_fort_radius * red_fort_radius:
                        sp = (sx, sy)
                        break
                if sp is not None and len(red_ants) < RED_MAX:
                    for _ in range(3):
                        if len(red_ants) >= RED_MAX:
                            break
                        red_ants.append(RedAnt(x=sp[0], y=sp[1], role="raider", cool=random.randint(0, RED_STEP_FRAMES), mounder=(random.random() < MOUND_TRAIT_CHANCE), mound_cool=random.randint(0, MOUND_BUILD_COOLDOWN)))
                        try:
                            maybe_assign_red_surface(red_ants[-1])
                        except Exception:
                            pass

        red_egg_spawn_timer += 1
        if red_egg_spawn_timer >= RED_EGG_SPAWN_EVERY:
            red_egg_spawn_timer = 0
            spawn_red_egg_near_red_queen()

        egg_spawn_timer += 1
        if egg_spawn_timer >= EGG_SPAWN_EVERY:
            egg_spawn_timer = 0
            spawn_egg_near_queen()

        # Hatch black eggs
        for k in range(len(eggs) - 1, -1, -1):
            eg = eggs[k]
            eg.hatch_t -= 1
            if poison[eg.x][eg.y] and world[eg.x][eg.y] in (AIR, TUNNEL):
                eggs.pop(k)
                continue
            if eg.hatch_t <= 0:
                ants.append(make_black_ant_at(eg.x, eg.y))
                eggs.pop(k)

        # Hatch red eggs
        for k in range(len(red_eggs) - 1, -1, -1):
            eg = red_eggs[k]
            eg.hatch_t -= 1
            if eg.hatch_t <= 0:
                if len(red_ants) < RED_MAX:
                    role = "builder" if random.random() < 0.34 else "raider"
                    red_ants.append(RedAnt(
                        x=eg.x,
                        y=eg.y,
                        role=role,
                        dir=random.choice([(-1, 1), (0, 1), (1, 1)]),
                        dir_ticks=random.randint(20, 50),
                        cool=random.randint(0, RED_STEP_FRAMES),
                        dig_cool=random.randint(0, RED_DIG_COOLDOWN),
                        hp=RED_HP,
                        bite_cool=random.randint(0, RED_BITE_COOLDOWN),
                        carrying_food=False,
                        build_cool=random.randint(0, RED_FORT_BUILD_COOLDOWN),
                        build_tx=None,
                        build_ty=None,
                        mounder=(random.random() < MOUND_TRAIT_CHANCE),
                        carry_sand=False,
                        mound_cool=random.randint(0, MOUND_BUILD_COOLDOWN),
                    ))
                    try:
                        maybe_assign_red_surface(red_ants[-1])
                    except Exception:
                        pass
                red_eggs.pop(k)

        if food_ping_active:
            enlist_food_helpers(ants)

        pher_r = queen_pheromone_radius()
        pher_r2 = pher_r * pher_r

        # ---- BLACK ANTS ----
        for i in range(len(ants) - 1, -1, -1):
            a = ants[i]
            a.cool -= 1
            if a.cool > 0:
                continue
            a.cool = BLACK_STEP_FRAMES

            # Water reaction: ants can enter flooded tunnels, but it slows and can harm them.
            if world[a.x][a.y] == WATER:
                a.cool += 6
                if random.random() < 0.10:
                    a.hp -= 1
                    if a.hp <= 0:
                        sfx.play("black_ant", "death", zoom)
                        ants.pop(i)
                        continue

            if a.dig_cool > 0:
                a.dig_cool -= 1
            if a.bite_cool > 0:
                a.bite_cool -= 1
            if a.alarm_t > 0:
                a.alarm_t -= 1
            if a.food_help_t > 0:
                a.food_help_t -= 1
            if a.build_cool > 0:
                a.build_cool -= 1

            x, y = a.x, a.y

            if a.trapped_t > 0:
                a.trapped_t -= 1
                continue

            if poison[x][y]:
                ants.pop(i)
                continue

            # Plants count as food: if an ant steps onto grass, it can harvest it.
            if (not a.carry_food) and plants[x][y] and world[x][y] in (AIR, TUNNEL):
                plants[x][y] = False
                a.carry_food = True

            if a.bite_cool == 0:
                for j in range(len(red_ants) - 1, -1, -1):
                    rr = red_ants[j]
                    if dist2(x, y, rr.x, rr.y) <= 2*2:
                        rr.hp -= 1
                        a.bite_cool = BLACK_BITE_COOLDOWN
                        raise_alarm(x, y)
                        enlist_helpers(ants)
                        if rr.hp <= 0:
                            red_ants.pop(j)
                        break

            if (not red_queen_dead) and abs(x - red_queen_x) <= 1 and abs(y - red_queen_y) <= 1:
                if a.bite_cool == 0:
                    red_queen_bites_taken += 1
                    a.bite_cool = BLACK_BITE_COOLDOWN
                    if red_queen_bites_taken >= RED_QUEEN_HP:
                        red_queen_dead = True
                        hard_mode = True
                        world[red_queen_x][red_queen_y] = TUNNEL

            if a.alarm_t > 0:
                dx, dy = step_toward_noisy(x, y, a.alarm_x, a.alarm_y)
                nx, ny = try_move_any_black(x, y, dx, dy, world)
                a.x, a.y = nx, ny
                continue

            if a.carry_food:
                dx, dy = step_toward_noisy(x, y, queen_x, queen_y)
                nx, ny = try_move_any_black(x, y, dx, dy, world)
                a.x, a.y = nx, ny
                if abs(a.x - queen_x) <= 1 and abs(a.y - queen_y) <= 1:
                    a.carry_food = False
                    if queen_level < QUEEN_MAX_LEVEL:
                        queen_level += 1
                    queen_bites_taken = 0
                continue

            # Optional surface mound-building behavior (trait-based)
            if handle_mounder_black(a):
                continue

            if a.role == "builder":
                # Goal: collect stone resources and place fort blocks to expand outward.
                if not a.carry_stone:
                    tgt = find_nearest_stone(x, y, max_r=90)
                    if tgt is not None:
                        tx, ty = tgt
                        dx, dy = step_toward_noisy(x, y, tx, ty)
                        nx, ny = try_move_any_black(x, y, dx, dy, world)
                        a.x, a.y = nx, ny
                        if stone[a.x][a.y]:
                            stone[a.x][a.y] = False
                            a.carry_stone = True
                    else:
                        # no stone seen: wander near queen
                        dx, dy = step_toward_noisy(x, y, queen_x, queen_y)
                        nx, ny = try_move_any_black(x, y, dx, dy, world)
                        a.x, a.y = nx, ny
                    continue
                else:
                    # carrying stone: return to fort core and place a block
                    dx, dy = step_toward_noisy(x, y, queen_x, queen_y)
                    nx, ny = try_move_any_black(x, y, dx, dy, world)
                    a.x, a.y = nx, ny
                    if dist2(a.x, a.y, queen_x, queen_y) <= 4*4:
                        if try_place_fort_block(False, a.x, a.y):
                            a.carry_stone = False
                    continue

            if a.role == "guard":
                if dist2(x, y, queen_x, queen_y) > pher_r2:
                    dx, dy = step_toward_noisy(x, y, queen_x, queen_y)
                else:
                    if idle_override_black(a):
                        continue
                    dx, dy = pick_branch_dir()
                nx, ny = try_move_any_black(x, y, dx, dy, world)
                a.x, a.y = nx, ny
                continue

            if a.role == "warrior":
                target: Optional[Tuple[int,int]] = None
                best = 10**9
                rdet2 = BLACK_ENEMY_DETECT_R * BLACK_ENEMY_DETECT_R
                for rr in red_ants:
                    d2 = dist2(x, y, rr.x, rr.y)
                    if d2 < rdet2 and d2 < best:
                        best = d2
                        target = (rr.x, rr.y)

                if target is None:
                    if random.random() < 0.55:
                        dx, dy = step_toward_noisy(x, y, red_nest_x, red_nest_y)
                    else:
                        dx, dy = pick_branch_dir()
                else:
                    dx, dy = step_toward_noisy(x, y, target[0], target[1])

                nx, ny = x + dx, y + dy
                if in_bounds(nx, ny):
                    if world[nx][ny] in (AIR, TUNNEL):
                        a.x, a.y = nx, ny
                    elif world[nx][ny] in (SAND, RED_FORTRESS) and a.dig_cool == 0 and random.random() < 0.25:
                        dig(nx, ny)
                        a.dig_cool = BLACK_DIG_COOLDOWN
                        a.x, a.y = nx, ny
                continue

            if a.role == "worker":
                if a.food_tx is None or a.food_ty is None or a.food_help_t == 0:
                    found = find_food_near(x, y, radius=max(FOOD_SCAN_RADIUS, 70))
                    if found is not None and random.random() < 0.90:
                        a.food_tx, a.food_ty = found
                        a.food_help_t = FOOD_HELP_TTL
                        raise_food_ping(found[0], found[1])

                if a.food_tx is not None and a.food_ty is not None and a.food_help_t > 0:
                    dx, dy = step_toward_noisy(x, y, a.food_tx, a.food_ty)
                    nx, ny = try_move_any_black(x, y, dx, dy, world)

                    if in_bounds(nx, ny) and (food[nx][ny] or plants[nx][ny]) and world[nx][ny] in (AIR, TUNNEL):
                        food[nx][ny] = False
                        plants[nx][ny] = False
                        a.carry_food = True
                        a.food_tx = None
                        a.food_ty = None
                        a.food_help_t = 0
                        a.x, a.y = nx, ny
                        continue

                    if poison[nx][ny] and world[nx][ny] in (AIR, TUNNEL):
                        ants.pop(i)
                        continue

                    a.x, a.y = nx, ny
                    continue

                if dist2(x, y, queen_x, queen_y) > (pher_r2 * 2):
                    dx, dy = step_toward_noisy(x, y, queen_x, queen_y)
                    nx, ny = try_move_any_black(x, y, dx, dy, world)
                    a.x, a.y = nx, ny
                    continue

                if (a.build_tx is None or a.build_ty is None) and a.build_cool == 0 and maze_frontier:
                    best_t = None
                    best_d = 10**9
                    for tx3, ty3 in random.sample(maze_frontier, k=min(35, len(maze_frontier))):
                        d = dist2(x, y, tx3, ty3)
                        if d < best_d:
                            best_d = d
                            best_t = (tx3, ty3)
                    if best_t:
                        a.build_tx, a.build_ty = best_t
                        a.build_cool = random.randint(int(FPS * 0.35), int(FPS * 0.9))

                if a.build_tx is not None and a.build_ty is not None:
                    tx3, ty3 = a.build_tx, a.build_ty

                    if abs(x - tx3) <= 1 and abs(y - ty3) <= 1:
                        if (tx3, ty3) in maze_plan and world[tx3][ty3] == SAND:
                            dig(tx3, ty3)
                            rebuild_maze_frontier()
                        a.build_tx, a.build_ty = None, None
                    else:
                        dx, dy = step_toward_noisy(x, y, tx3, ty3)
                        nx, ny = try_move_any_black(x, y, dx, dy, world)
                        a.x, a.y = nx, ny
                    continue

                # No immediate food target: workers will actively dig/expand and manipulate clutter (structures).
                did_something = False

                # Prefer digging planned maze frontier (keeps expansion coherent).
                if a.dig_cool == 0 and maze_frontier:
                    tx, ty = random.choice(maze_frontier[: min(50, len(maze_frontier))])
                    if in_bounds(tx, ty) and world[tx][ty] == SAND:
                        dig(tx, ty)
                        a.dig_cool = BLACK_DIG_COOLDOWN
                        a.x, a.y = tx, ty
                        did_something = True

                if did_something:
                    continue

                # Otherwise: look for nearby clutter to clear or use as a structural partition.
                # Clear nearby clutter (easier detection).
                for nx2, ny2 in neighbors4(x, y):
                    if world[nx2][ny2] == CLUTTER and a.dig_cool == 0:
                        dig(nx2, ny2)
                        a.dig_cool = BLACK_DIG_COOLDOWN
                        a.x, a.y = nx2, ny2
                        did_something = True
                        break
                if did_something:
                    continue

                # Explore: carve into adjacent sand whenever possible.
                dx, dy = pick_branch_dir()
                nx, ny = x + dx, y + dy
                if in_bounds(nx, ny) and world[nx][ny] in (SAND, CLUTTER):
                    if a.dig_cool == 0 and random.random() < 0.70:
                        dig(nx, ny)
                        a.dig_cool = BLACK_DIG_COOLDOWN
                        a.x, a.y = nx, ny
                        continue

                # Move (always; no standing still).
                nx, ny = try_move_any_black(x, y, dx, dy, world)
                a.x, a.y = nx, ny

                # Random structure building: place/clear clutter in tunnels to create partitions.
                if world[a.x][a.y] == TUNNEL and random.random() < 0.05:
                    world[a.x][a.y] = CLUTTER
                elif world[a.x][a.y] == CLUTTER and random.random() < 0.25:
                    world[a.x][a.y] = TUNNEL
                continue

            if a.role == "scout":
                if a.food_tx is None or a.food_ty is None or a.food_help_t == 0:
                    found = find_food_near(x, y, radius=max(FOOD_SCAN_RADIUS, 85))
                    if found is not None:
                        a.food_tx, a.food_ty = found
                        a.food_help_t = FOOD_HELP_TTL
                        raise_food_ping(found[0], found[1])

                if a.food_tx is not None and a.food_ty is not None and a.food_help_t > 0:
                    dx, dy = step_toward_noisy(x, y, a.food_tx, a.food_ty)
                else:
                    if idle_override_black(a):
                        continue
                    a.dir_ticks -= 1
                    if a.dir_ticks <= 0:
                        a.dir = pick_branch_dir()
                        a.dir_ticks = random.randint(12, 45)
                    dx, dy = a.dir

                nx, ny = x + dx, y + dy
                if not in_bounds(nx, ny):
                    a.dir = pick_branch_dir()
                    a.dir_ticks = random.randint(8, 25)
                    continue

                if poison[nx][ny] and world[nx][ny] in (AIR, TUNNEL):
                    ants.pop(i)
                    continue

                if (food[nx][ny] or plants[nx][ny]) and world[nx][ny] in (AIR, TUNNEL):
                    food[nx][ny] = False
                    plants[nx][ny] = False
                    a.carry_food = True
                    a.food_tx = None
                    a.food_ty = None
                    a.food_help_t = 0
                    a.x, a.y = nx, ny
                    continue

                if world[nx][ny] in (AIR, TUNNEL):
                    a.x, a.y = nx, ny
                elif world[nx][ny] in (SAND, DIRT, RED_FORTRESS, BLACK_FORT_COLOR, RED_FORT_COLOR):
                    if a.dig_cool == 0 and random.random() < BLACK_DIG_CHANCE:
                        dig(nx, ny)
                        a.dig_cool = BLACK_DIG_COOLDOWN
                        a.x, a.y = nx, ny
                continue

        # ---- RED ANTS ----
        for rr in red_ants[:]:
            rr.cool -= 1
            if rr.cool > 0:
                continue
            rr.cool = RED_STEP_FRAMES

            # Water reaction (red ants): slowed and can drown in flooded tunnels.
            if world[rr.x][rr.y] == WATER:
                rr.cool += 6
                if random.random() < 0.10:
                    rr.hp -= 1
                    if rr.hp <= 0:
                        sfx.play("red_ant", "death", zoom)
                        red_ants.remove(rr)
                        continue

            if rr.dig_cool > 0:
                rr.dig_cool -= 1
            if rr.bite_cool > 0:
                rr.bite_cool -= 1

            rx, ry = rr.x, rr.y

            if poison[rx][ry] and world[rx][ry] in (AIR, TUNNEL):
                sfx.play("red_ant", "death", zoom)
                red_ants.remove(rr)
                continue

            if rr.trapped_t > 0:
                rr.trapped_t -= 1
                continue

            # Surface exploration: some red ants go topside and roam around the surface/anthill.
            # This is intentionally lightweight (no pathfinding), so it does not destabilize FPS.
            if rr.surface_t > 0 and rr.surface_tx is not None and rr.surface_ty is not None:
                rr.surface_t -= 1
                tx, ty = rr.surface_tx, rr.surface_ty
                if dist2(rx, ry, tx, ty) <= 2:
                    rr.surface_t = 0
                    rr.surface_tx = None
                    rr.surface_ty = None
                else:
                    dx, dy = step_toward_noisy(rx, ry, tx, ty)
                    nx, ny = rx + dx, ry + dy
                    if in_bounds(nx, ny) and is_walkable(world[nx][ny]):
                        rr.x, rr.y = nx, ny
                    continue
            else:
                # Occasionally pick a surface roam target (only if we're underground enough)
                if ry > SURFACE_Y + 6 and random.random() < 0.004:
                    rr.surface_t = FPS * random.randint(4, 10)
                    rr.surface_tx = clamp(red_queen_x + random.randint(-70, 70), 2, WIDTH - 3)
                    rr.surface_ty = clamp(SURFACE_Y - random.randint(2, 6), 2, SURFACE_Y - 1)

            # Plants count as food for red ants as well.
            if (not rr.carrying_food) and plants[rx][ry] and world[rx][ry] in (AIR, TUNNEL):
                plants[rx][ry] = False
                rr.carrying_food = True

            if rr.role == "builder":
                # Goal: collect stone resources and build/expand the red fort.
                if not rr.carry_stone:
                    tgt = find_nearest_stone(rx, ry, max_r=90)
                    if tgt is not None:
                        tx, ty = tgt
                        dx, dy = step_toward_noisy(rx, ry, tx, ty)
                        nx, ny = try_move_any(rx, ry, dx, dy, world)
                        rr.x, rr.y = nx, ny
                        if stone[rr.x][rr.y]:
                            stone[rr.x][rr.y] = False
                            rr.carry_stone = True
                    else:
                        dx, dy = step_toward_noisy(rx, ry, red_queen_x, red_queen_y)
                        nx, ny = try_move_any(rx, ry, dx, dy, world)
                        rr.x, rr.y = nx, ny
                    continue
                else:
                    dx, dy = step_toward_noisy(rx, ry, red_queen_x, red_queen_y)
                    nx, ny = try_move_any(rx, ry, dx, dy, world)
                    rr.x, rr.y = nx, ny
                    if dist2(rr.x, rr.y, red_queen_x, red_queen_y) <= 5*5:
                        if try_place_fort_block(True, rr.x, rr.y):
                            rr.carry_stone = False
                    continue

            # Optional surface mound-building behavior (trait-based)
            if handle_mounder_red(rr):
                continue

            # Red ants attack nearby black ants (skirmish)
            if rr.bite_cool == 0:
                target_idx = None
                best_d2 = 10**9
                for bi in range(len(ants) - 1, -1, -1):
                    ba = ants[bi]
                    d2 = dist2(rx, ry, ba.x, ba.y)
                    if d2 <= 2*2 and d2 < best_d2:
                        best_d2 = d2
                        target_idx = bi
                if target_idx is not None:
                    ants[target_idx].hp -= 1
                    rr.bite_cool = RED_BITE_COOLDOWN
                    raise_alarm(ants[target_idx].x, ants[target_idx].y)
                    enlist_helpers(ants)
                    if ants[target_idx].hp <= 0:
                        ants.pop(target_idx)
                    continue

            if not rr.carrying_food:
                red_try_steal_food(rr)

            # Red ants will also destroy black eggs on contact.
            if rr.bite_cool == 0:
                egg_idx = None
                best_e2 = 10**9
                for ei in range(len(eggs) - 1, -1, -1):
                    eg = eggs[ei]
                    d2 = dist2(rx, ry, eg.x, eg.y)
                    if d2 <= 2*2 and d2 < best_e2:
                        best_e2 = d2
                        egg_idx = ei
                if egg_idx is not None:
                    eggs.pop(egg_idx)
                    rr.bite_cool = RED_BITE_COOLDOWN
                    continue


            if rr.role == "builder":
                if dist2(rx, ry, queen_x, queen_y) <= (8 * 8):
                    rr.role = "raider"
                else:
                    if rr.build_cool > 0:
                        rr.build_cool -= 1

                    # NEW: builders place ONE wall at a time, consuming stone near themselves
                    if rr.build_cool == 0:
                        tgt = red_pick_wall_target(rr.x, rr.y)
                        if tgt:
                            txw, tyw = tgt
                            if red_place_wall(txw, tyw, rr.x, rr.y):
                                rr.build_cool = RED_FORT_BUILD_COOLDOWN

                    dx, dy = pick_branch_dir()
                    nx, ny = try_move_any(rx, ry, dx, dy, world)
                    if red_fortress_region_contains(nx, ny) and world[nx][ny] == TUNNEL:
                        rr.x, rr.y = nx, ny
                    else:
                        dx, dy = step_toward_noisy(rx, ry, red_queen_x, red_queen_y)
                        rr.x, rr.y = try_move_any(rx, ry, dx, dy, world)
                    continue

            if abs(rx - queen_x) <= 1 and abs(ry - queen_y) <= 1:
                if rr.bite_cool == 0:
                    queen_bites_taken += 1
                    rr.bite_cool = RED_BITE_COOLDOWN
                    if queen_bites_remaining() <= 0:
                        reset_game()
                        break
                continue

            # Attack/seek priorities: black ants, black eggs, then black queen.
            target = None
            target_kind = ""

            # Nearest black ant
            best_d2 = 10**9
            for ba in ants:
                d2 = dist2(rx, ry, ba.x, ba.y)
                if d2 < best_d2:
                    best_d2 = d2
                    target = (ba.x, ba.y)
                    target_kind = "black_ant"

            # Nearest black egg (if no nearby ant target)
            if target is None or best_d2 > (70 * 70):
                best_e2 = 10**9
                best_e = None
                for eg in eggs:
                    d2 = dist2(rx, ry, eg.x, eg.y)
                    if d2 < best_e2:
                        best_e2 = d2
                        best_e = (eg.x, eg.y)
                if best_e is not None and best_e2 <= (90 * 90):
                    target = best_e
                    target_kind = "egg"

            # Fallback: black queen if detected; otherwise keep pushing downward.
            if target is None:
                if dist2(rx, ry, queen_x, queen_y) <= (RED_QUEEN_DETECT_R * RED_QUEEN_DETECT_R):
                    target = (queen_x, queen_y)
                    target_kind = "queen"
                else:
                    target = None

            if target is not None:
                tx, ty = target
                dx, dy = step_toward_noisy(rx, ry, tx, ty)
            else:
                # No concrete target: always dig/explore toward the enemy side.
                if rr.dir_ticks <= 0:
                    rr.dir = pick_downish_dir()
                    rr.dir_ticks = random.randint(10, 35)
                rr.dir_ticks -= 1
                dx, dy = rr.dir
                if random.random() < 0.10:
                    dx, dy = pick_downish_dir()

            nx, ny = rx + dx, ry + dy
            if not in_bounds(nx, ny):
                continue

            if world[nx][ny] in (SAND, DIRT, RED_FORTRESS, BLACK_FORT_COLOR, RED_FORT_COLOR):
                if rr.dig_cool == 0 and random.random() < RED_DIG_CHANCE:
                    dig(nx, ny)
                    rr.dig_cool = RED_DIG_COOLDOWN
                    rr.x, rr.y = nx, ny
                else:
                    if random.random() < 0.20:
                        rr.dir = pick_downish_dir()
                        rr.dir_ticks = random.randint(10, 30)
            elif world[nx][ny] in (AIR, TUNNEL):
                rr.x, rr.y = nx, ny

        # ---- EARTHWORM ----
        def worm_near_queen(nx: int, ny: int) -> bool:
            r2 = WORM_AVOID_R * WORM_AVOID_R
            return (
                dist2(nx, ny, queen_x, queen_y) <= r2
                or dist2(nx, ny, red_queen_x, red_queen_y) <= r2
            )

        worm.cool -= 1
        if worm.cool <= 0:
            worm.cool = WORM_STEP_FRAMES

            worm.leave_collapse = False

            worm.dir_ticks -= 1
            if worm.dir_ticks <= 0 or random.random() < WORM_TURN_CHANCE:
                turn = random.choices(population=[-1, 0, 1], weights=[2, 10, 2], k=1)[0]
                worm.heading = (worm.heading + turn) % 8
                worm.dir_ticks = random.randint(40, 110)

            dx, dy = DIR8[worm.heading]

            moved = False
            for _try in range(6):
                nx, ny = worm.x + dx, worm.y + dy
                # Never move or dig in the AIR band; worm stays on/under the surface.
                if ny < SURFACE_Y:
                    worm.heading = (worm.heading + random.choice([-1, 1])) % 8
                    dx, dy = DIR8[worm.heading]
                    worm.dir_ticks = 0
                    continue
                if not in_bounds(nx, ny) or worm_near_queen(nx, ny):
                    worm.heading = (worm.heading + random.choice([-1, 1])) % 8
                    dx, dy = DIR8[worm.heading]
                    worm.dir_ticks = 0
                    continue

                # Eat anything in its path (except queens)
                food[nx][ny] = False
                poison[nx][ny] = False
                plants[nx][ny] = False
                stone[nx][ny] = False

                for k in range(len(eggs) - 1, -1, -1):
                    if eggs[k].x == nx and eggs[k].y == ny:
                        eggs.pop(k)
                for k in range(len(red_eggs) - 1, -1, -1):
                    if red_eggs[k].x == nx and red_eggs[k].y == ny:
                        red_eggs.pop(k)

                for k in range(len(ants) - 1, -1, -1):
                    if ants[k].x == nx and ants[k].y == ny:
                        ants.pop(k)
                for k in range(len(red_ants) - 1, -1, -1):
                    if red_ants[k].x == nx and red_ants[k].y == ny:
                        red_ants.pop(k)

                was_tunnel = (world[nx][ny] == TUNNEL)

                # Carve a smooth(er) worm tunnel using the same TUNNEL tile as ants.
                carve_worm_tunnel(nx, ny, WORM_CARVE_RADIUS)

                # Collapse ant tunnels when the worm intersects them.
                if was_tunnel:
                    rr = WORM_TUNNEL_COLLAPSE_RADIUS
                    rr2 = rr * rr
                    carve_r2 = WORM_CARVE_RADIUS * WORM_CARVE_RADIUS
                    for ox in range(-rr, rr + 1):
                        for oy in range(-rr, rr + 1):
                            if ox * ox + oy * oy > rr2:
                                continue
                            # Don't instantly collapse the worm's own fresh carve at the head.
                            if ox * ox + oy * oy <= carve_r2:
                                continue
                            txc, tyc = nx + ox, ny + oy
                            if not in_bounds(txc, tyc):
                                continue
                            if worm_near_queen(txc, tyc):
                                continue
                            if world[txc][tyc] != TUNNEL:
                                continue
                            if random.random() < WORM_TUNNEL_COLLAPSE_CHANCE:
                                world[txc][tyc] = SAND
                                dig_hp[txc][tyc] = 0
                                stone[txc][tyc] = False


                worm.x, worm.y = nx, ny
                worm.segments.insert(0, (nx, ny))
                if len(worm.segments) > WORM_LENGTH:
                    worm.segments.pop()
                moved = True
                break

            if moved:
                for x in range(WIDTH):
                    for y in range(HEIGHT - 2, 0, -1):
                        if world[x][y] == CLUTTER and world[x][y + 1] == AIR:
                            world[x][y] = AIR
                            world[x][y + 1] = CLUTTER

    render_world()
    pygame.display.flip()

pygame.quit()
'''
EMBEDDED_INSECTS_CODE = compile(_patch_embedded_insect_source(EMBEDDED_INSECTS_SOURCE), "<embedded_insects>", "exec")


# -------------------------
# Utilities
# -------------------------
def clamp(x, a, b):
    return a if x < a else b if x > b else x

def lerp(a, b, t):
    return a + (b - a) * t

def smoothstep(t):
    return t * t * (3 - 2 * t)

def hash2(x: int, y: int, seed: int = 1337) -> int:
    n = x * 374761393 + y * 668265263 + seed * 1442695040888963407
    n = (n ^ (n >> 13)) * 1274126177
    n = n ^ (n >> 16)
    return n & 0xFFFFFFFF

def noise2(x: int, y: int, seed: int = 1337) -> float:
    return hash2(x, y, seed) / 0xFFFFFFFF

def value_noise(x: float, y: float, seed: int = 1337) -> float:
    xi, yi = int(math.floor(x)), int(math.floor(y))
    xf, yf = x - xi, y - yi
    v00 = noise2(xi, yi, seed)
    v10 = noise2(xi + 1, yi, seed)
    v01 = noise2(xi, yi + 1, seed)
    v11 = noise2(xi + 1, yi + 1, seed)
    sx, sy = smoothstep(xf), smoothstep(yf)
    a = lerp(v00, v10, sx)
    b = lerp(v01, v11, sx)
    return lerp(a, b, sy)

def dither_choice(a: Tuple[int,int,int], b: Tuple[int,int,int], x: int, y: int, t: float) -> Tuple[int,int,int]:
    t = clamp(t, 0.0, 1.0)
    pattern = (((x * 3) ^ (y * 5)) & 7) / 7.0
    return b if pattern < t else a


# -------------------------
# World tiles
# -------------------------
T_WATER = 0
T_SAND = 1
T_GRASS = 2
T_DIRT = 3
T_GRAVEL = 4  # gray


@dataclass
class CoconutTree:
    x: int
    y: int
    trunk_h: int
    canopy_r: int

    @property
    def trunk_rect(self) -> pygame.Rect:
        # Used only for drawing/climb volume (not collision).
        return pygame.Rect(self.x - 2, self.y - self.trunk_h, 4, self.trunk_h + 2)

    @property
    def base_rect(self) -> pygame.Rect:
        # Small collider at base only (1 tile-ish)
        return pygame.Rect(self.x - TILE // 2, self.y - TILE, TILE, TILE)

    @property
    def climb_rect(self) -> pygame.Rect:
        return pygame.Rect(self.x - 7, self.y - self.trunk_h, 14, self.trunk_h + 8)

    def top_y(self) -> int:
        return self.y - self.trunk_h


@dataclass
class Log:
    x: int
    y: int
    last_harvest_day: int = -1

    @property
    def sort_y(self) -> int:
        return self.y

    def rect(self) -> pygame.Rect:
        return pygame.Rect(self.x - 8, self.y - 3, 16, 6)


@dataclass
class Raft:
    uid: int
    x: float
    y: float
    w: int = 54
    h: int = 30
    occupants: Dict[int, int] = None  # monkey_idx -> seat_index

    def __post_init__(self):
        if self.occupants is None:
            self.occupants = {}

    @property
    def sort_y(self) -> int:
        return int(self.y)

    def rect(self, pygame_mod):
        return pygame_mod.Rect(int(self.x - self.w / 2), int(self.y - self.h / 2), int(self.w), int(self.h))


@dataclass
class RockNode:
    x: int
    y: int
    size: int  # 0..1 tiny variants

    @property
    def sort_y(self) -> int:
        return self.y

    def pick_dist2(self) -> int:
        return (7 + self.size) ** 2


@dataclass
class Veg:
    x: int
    y: int
    kind: int  # 0=bush,1=fern,2=flower

    @property
    def sort_y(self) -> int:
        return self.y


@dataclass
class Monkey:
    name: str
    x: float
    y: float
    color_main: Tuple[int,int,int]
    color_dark: Tuple[int,int,int]
    speed: float = 60.0


    # Pseudo-height for jumping (visual + climb gating)
    jumping: bool = False
    jump_z: float = 0.0
    jump_vz: float = 0.0
    no_climb_until: float = 0.0
    climbing: bool = False
    climb_tree_idx: Optional[int] = None
    climb_t: float = 0.0

    on_raft: bool = False

    raft_uid: Optional[int] = None
    raft_seat: int = 0

    inv: items.Inventory = None

    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x) - 3, int(self.y) - 2, 6, 5)


@dataclass
class Bird:
    species: str  # "seagull" or "parrot"
    x: float
    y: float
    vx: float
    vy: float
    state: str = "fly"  # fly, land, dead
    perch_tree_idx: Optional[int] = None
    perch_time: float = 0.0
    target_x: float = 0.0
    target_y: float = 0.0
    hp: int = 1
    loot_ready: bool = False

    @property
    def sort_y(self) -> int:
        return int(self.y)

    def radius(self) -> int:
        return 4


@dataclass
class RockProjectile:
    x: float
    y: float
    vx: float
    vy: float
    life: float = 1.6



@dataclass
class Crab:
    x: float
    y: float
    vx: float
    vy: float
    color_a: Tuple[int, int, int]
    color_b: Tuple[int, int, int]
    state: str = "alive"  # alive, dead
    loot_ready: bool = False
    dead_until: float = 0.0
    wander_t: float = 0.0
    target_x: float = 0.0
    target_y: float = 0.0
    flee_t: float = 0.0
    sfx_t: float = 0.0

    @property
    def sort_y(self) -> int:
        return int(self.y)

    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x) - 2, int(self.y) - 1, 4, 3)

@dataclass
class Iguana:
    x: float
    y: float
    vx: float
    vy: float
    color_body: Tuple[int, int, int]
    color_belly: Tuple[int, int, int]
    state: str = "alive"  # alive, dead
    loot_ready: bool = False
    dead_until: float = 0.0
    wander_t: float = 0.0
    target_x: float = 0.0
    target_y: float = 0.0
    flee_t: float = 0.0
    swim_t: float = 0.0
    sfx_t: float = 0.0

    @property
    def sort_y(self) -> int:
        return int(self.y)

    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x) - 4, int(self.y) - 3, 8, 6)

# -------------------------
# Audio (SFX)
# -------------------------
class SFXManager:
    def __init__(self):
        self.enabled = False
        self.sounds = {}
        self.ch_ocean = None
        self._ocean_playing = False
        try:
            pygame.mixer.pre_init(22050, -16, 1, 512)
            pygame.mixer.init()
            self.enabled = True
        except Exception:
            self.enabled = False

        if self.enabled:
            self._load_all()

    def _load(self, key: str, rel_path: str):
        if not self.enabled:
            return
        base_dir = os.path.dirname(os.path.abspath(__file__))
        p = os.path.join(base_dir, rel_path)
        try:
            self.sounds[key] = pygame.mixer.Sound(p)
        except Exception:
            # Missing or invalid; keep silent
            pass

    def _load_all(self):
        # UI
        self._load("ui_click", os.path.join("sfx", "ui", "click.wav"))
        self._load("ui_toggle", os.path.join("sfx", "ui", "toggle.wav"))
        self._load("ui_error", os.path.join("sfx", "ui", "error.wav"))

        # Monkeys
        self._load("monkey_step", os.path.join("sfx", "monkeys", "step.wav"))
        self._load("monkey_throw", os.path.join("sfx", "monkeys", "throw.wav"))
        self._load("monkey_pickup", os.path.join("sfx", "monkeys", "pickup.wav"))
        self._load("monkey_interact", os.path.join("sfx", "monkeys", "interact.wav"))
        self._load("monkey_climb", os.path.join("sfx", "monkeys", "climb.wav"))

        # Birds
        self._load("bird_seagull", os.path.join("sfx", "birds", "seagull.wav"))
        self._load("bird_parrot", os.path.join("sfx", "birds", "parrot.wav"))
        self._load("bird_hit", os.path.join("sfx", "birds", "hit.wav"))
        self._load("bird_loot", os.path.join("sfx", "birds", "loot.wav"))

        # World
        self._load("coconut_fall", os.path.join("sfx", "world", "coconut_fall.wav"))
        self._load("ocean_loop", os.path.join("sfx", "world", "ocean_loop.wav"))

        try:
            self.ch_ocean = pygame.mixer.Channel(2)
        except Exception:
            self.ch_ocean = None

    def play(self, key: str, volume: float = 0.7):
        if not self.enabled:
            return
        s = self.sounds.get(key)
        if not s:
            return
        try:
            s.set_volume(max(0.0, min(1.0, volume)))
            s.play()
        except Exception:
            pass

    def ocean_set(self, volume: float):
        """Volume 0..1. Starts/stops loop automatically."""
        if not self.enabled or not self.ch_ocean:
            return
        vol = max(0.0, min(1.0, volume))
        snd = self.sounds.get("ocean_loop")
        if not snd:
            return
        try:
            if vol <= 0.01:
                if self._ocean_playing:
                    self.ch_ocean.stop()
                    self._ocean_playing = False
                return
            if not self._ocean_playing:
                self.ch_ocean.play(snd, loops=-1)
                self._ocean_playing = True
            self.ch_ocean.set_volume(vol)
        except Exception:
            pass


class IslandWorld:
    def __init__(self, seed: int = 7):
        self.seed = seed
        self.tw = WORLD_TW
        self.th = WORLD_TH
        self.tiles = [[T_WATER for _ in range(self.tw)] for _ in range(self.th)]
        self.tone = [[0.0 for _ in range(self.tw)] for _ in range(self.th)]
        self.water_shallow = [[False for _ in range(self.tw)] for _ in range(self.th)]

        self.trees: List[CoconutTree] = []
        self.logs: List[Log] = []
        self.rafts: List[Raft] = []
        self.rocks: List[RockNode] = []
        self.veg: List[Veg] = []
        self.pickups: List[items.WorldItem] = []

        self._generate()

        # Performance: build static terrain surface and spatial indices for trees.
        self._build_static_surfaces()
        self._build_tree_spatial_index()

    def _generate(self):
        random.seed(self.seed)

        cx, cy = self.tw / 2.0, self.th / 2.0
        base_r = min(self.tw, self.th) * 0.39

        height = [[0.0 for _ in range(self.tw)] for _ in range(self.th)]
        for y in range(self.th):
            for x in range(self.tw):
                dx = (x - cx)
                dy = (y - cy)
                d = math.sqrt(dx*dx + dy*dy)
                nd = d / base_r

                n = 0.0
                amp = 1.0
                freq = 0.055
                for o in range(6):
                    n += amp * (value_noise(x * freq, y * freq, self.seed + 101 + o * 17) * 2.0 - 1.0)
                    amp *= 0.5
                    freq *= 2.0

                h = (1.0 - nd) + (n * 0.20)
                height[y][x] = h

        for y in range(self.th):
            for x in range(self.tw):
                h = height[y][x]
                self.tone[y][x] = value_noise(x * 0.19, y * 0.19, self.seed + 777)

                if h < 0.08:
                    self.tiles[y][x] = T_WATER
                elif h < 0.165:
                    self.tiles[y][x] = T_SAND
                elif h < 0.58:
                    if h < 0.24 and noise2(x, y, self.seed + 222) < 0.16:
                        self.tiles[y][x] = T_SAND
                    else:
                        self.tiles[y][x] = T_GRASS
                elif h < 0.84:
                    self.tiles[y][x] = T_DIRT
                else:
                    self.tiles[y][x] = T_GRAVEL

        # Shallow water: any water tile within 2 tiles of land
        for y in range(self.th):
            for x in range(self.tw):
                if self.tiles[y][x] != T_WATER:
                    self.water_shallow[y][x] = False
                    continue
                shallow = False
                for oy in (-2, -1, 0, 1, 2):
                    for ox in (-2, -1, 0, 1, 2):
                        nx, ny = x + ox, y + oy
                        if 0 <= nx < self.tw and 0 <= ny < self.th and self.tiles[ny][nx] != T_WATER:
                            shallow = True
                            break
                    if shallow:
                        break
                self.water_shallow[y][x] = shallow

        self._stamp_clearings(count=26)
        self._place_trees()
        self._place_vegetation()
        self._place_logs()
        self._place_rocks()
        self._place_pickups()

    def _stamp_clearings(self, count: int = 14):
        for _ in range(count):
            for _ in range(240):
                tx = random.randint(12, self.tw - 13)
                ty = random.randint(12, self.th - 13)
                if self.tiles[ty][tx] != T_WATER:
                    break
            r = random.randint(4, 10)
            for y in range(ty - r, ty + r + 1):
                for x in range(tx - r, tx + r + 1):
                    if 0 <= x < self.tw and 0 <= y < self.th:
                        d = math.hypot(x - tx, y - ty)
                        if d <= r + (noise2(x, y, self.seed + 900) - 0.5) * 1.0:
                            if self.tiles[y][x] != T_WATER:
                                self.tiles[y][x] = T_SAND if d < r * 0.45 else T_GRASS

    def _place_trees(self):
        wanted = 220
        attempts = 0

        def is_shore_adjacent(tx: int, ty: int) -> bool:
            for oy in (-1, 0, 1):
                for ox in (-1, 0, 1):
                    nx, ny = tx + ox, ty + oy
                    if 0 <= nx < self.tw and 0 <= ny < self.th:
                        if self.tiles[ny][nx] == T_WATER:
                            return True
            return False

        while len(self.trees) < wanted and attempts < wanted * 120:
            attempts += 1
            tx = random.randint(8, self.tw - 9)
            ty = random.randint(8, self.th - 9)

            t = self.tiles[ty][tx]
            if t not in (T_GRASS, T_SAND):
                continue
            if is_shore_adjacent(tx, ty):
                continue

            px = tx * TILE + TILE // 2
            py = ty * TILE + TILE // 2

            ok = True
            for tr in self.trees:
                if (tr.x - px) ** 2 + (tr.y - py) ** 2 < (TILE * 7) ** 2:
                    ok = False
                    break
            if not ok:
                continue

            trunk_h = random.randint(40, 70)
            canopy_r = random.randint(10, 15)
            self.trees.append(CoconutTree(px, py, trunk_h, canopy_r))

    def _place_vegetation(self):
        cx, cy = (self.tw * TILE) / 2.0, (self.th * TILE) / 2.0
        max_r = min(self.tw, self.th) * TILE * 0.50

        def center_factor(px: float, py: float) -> float:
            d = math.hypot(px - cx, py - cy)
            return 1.0 - clamp(d / max_r, 0.0, 1.0)

        wanted = 2200
        attempts = 0
        while len(self.veg) < wanted and attempts < wanted * 3:
            attempts += 1
            tx = random.randint(2, self.tw - 3)
            ty = random.randint(2, self.th - 3)
            tile = self.tiles[ty][tx]
            if tile not in (T_GRASS, T_DIRT):
                continue

            px = tx * TILE + TILE // 2 + (hash2(tx, ty, self.seed + 333) % TILE) - (TILE // 2)
            py = ty * TILE + TILE // 2 + (hash2(tx, ty, self.seed + 444) % TILE) - (TILE // 2)

            # avoid too close to water
            near_water = False
            for oy in (-1, 0, 1):
                for ox in (-1, 0, 1):
                    nx, ny = tx + ox, ty + oy
                    if 0 <= nx < self.tw and 0 <= ny < self.th and self.tiles[ny][nx] == T_WATER:
                        near_water = True
                        break
                if near_water:
                    break
            if near_water:
                continue

            cf = center_factor(px, py)
            if random.random() > (0.25 + cf * 0.75):
                continue

            if cf > 0.55:
                kind = 1 if random.random() < 0.55 else 0
            else:
                kind = 2 if random.random() < 0.35 else (0 if random.random() < 0.55 else 1)

            ok = True
            for tr in self.trees:
                if (tr.x - px) ** 2 + (tr.y - py) ** 2 < (TILE * 5) ** 2:
                    ok = False
                    break
            if not ok:
                continue

            self.veg.append(Veg(int(px), int(py), kind))

    def _place_logs(self):
        wanted = 160
        attempts = 0
        while len(self.logs) < wanted and attempts < wanted * 100:
            attempts += 1
            tx = random.randint(6, self.tw - 7)
            ty = random.randint(6, self.th - 7)
            t = self.tiles[ty][tx]
            if t not in (T_GRASS, T_DIRT):
                continue

            # avoid water adjacency
            near_water = False
            for oy in (-2, -1, 0, 1, 2):
                for ox in (-2, -1, 0, 1, 2):
                    nx, ny = tx + ox, ty + oy
                    if 0 <= nx < self.tw and 0 <= ny < self.th and self.tiles[ny][nx] == T_WATER:
                        near_water = True
                        break
                if near_water:
                    break
            if near_water:
                continue

            px = tx * TILE + TILE // 2
            py = ty * TILE + TILE // 2

            ok = True
            for tr in self.trees:
                if (tr.x - px) ** 2 + (tr.y - py) ** 2 < (TILE * 10) ** 2:
                    ok = False
                    break
            if not ok:
                continue

            for lg in self.logs:
                if (lg.x - px) ** 2 + (lg.y - py) ** 2 < (TILE * 8) ** 2:
                    ok = False
                    break
            if not ok:
                continue

            self.logs.append(Log(px, py))

    def _place_rocks(self):
        # tiny rocks, sparse
        wanted = 260
        attempts = 0
        while len(self.rocks) < wanted and attempts < wanted * 6:
            attempts += 1
            tx = random.randint(4, self.tw - 5)
            ty = random.randint(4, self.th - 5)
            t = self.tiles[ty][tx]
            if t not in (T_DIRT, T_GRAVEL, T_GRASS):
                continue
            if t == T_GRASS and random.random() < 0.70:
                continue

            # avoid water adjacency
            near_water = False
            for oy in (-1, 0, 1):
                for ox in (-1, 0, 1):
                    if self.tiles[ty + oy][tx + ox] == T_WATER:
                        near_water = True
                        break
                if near_water:
                    break
            if near_water:
                continue

            px = tx * TILE + TILE // 2 + (hash2(tx, ty, self.seed + 909) % 3) - 1
            py = ty * TILE + TILE // 2 + (hash2(tx, ty, self.seed + 919) % 3) - 1
            size = (hash2(tx, ty, self.seed + 929) % 2)

            if t == T_DIRT and random.random() < 0.75:
                continue
            if t == T_GRAVEL and random.random() < 0.55:
                continue

            self.rocks.append(RockNode(int(px), int(py), int(size)))

        random.shuffle(self.rocks)
        self.rocks = self.rocks[:220]

    def _place_pickups(self):
        random.seed(self.seed + 1001)

        def add_pickup(item_id: str, px: float, py: float, qty: int = 1):
            self.pickups.append(items.WorldItem(item_id=item_id, x=px, y=py, qty=qty, bob_phase=random.random() * 6.28))

        # Flowers and seeds
        for v in self.veg:
            if v.kind == 2 and random.random() < 0.30:
                add_pickup(items.PINK_FLOWER, v.x + random.randint(-2, 2), v.y + random.randint(0, 2), qty=1)
            if v.kind == 2 and random.random() < 0.18:
                add_pickup(items.FLOWER_SEEDS, v.x + random.randint(-2, 2), v.y + random.randint(0, 2), qty=random.randint(2, 6))

        # Fish as world pickup near shore sand (in addition to catch mechanic)
        for _ in range(1200):
            tx = random.randint(2, self.tw - 3)
            ty = random.randint(2, self.th - 3)
            if self.tiles[ty][tx] != T_SAND:
                continue
            near_water = False
            for ox, oy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                if self.tiles[ty + oy][tx + ox] == T_WATER:
                    near_water = True
                    break
            if near_water and random.random() < 0.04:
                add_pickup(items.FISH, tx * TILE + TILE // 2, ty * TILE + TILE // 2, qty=1)

        random.shuffle(self.pickups)
        self.pickups = self.pickups[:900]

    
    # -------------------------
    # Performance helpers
    # -------------------------
    def _build_static_surfaces(self):
        """Pre-render the static terrain (tiles + micro details) into a single surface.

        This avoids per-frame per-tile draw calls and expensive per-pixel set_at operations.
        """
        world_w = self.tw * TILE
        world_h = self.th * TILE

        try:
            surf = pygame.Surface((world_w, world_h))
            # convert() is much faster to blit, but requires a display surface.
            if pygame.display.get_surface() is not None:
                surf = surf.convert()
        except Exception:
            # If pygame isn't fully initialized, skip caching; the game will fall back to slow path.
            self.base_surface = None
            return

        for ty in range(self.th):
            row = self.tiles[ty]
            tone_row = self.tone[ty]
            shallow_row = self.water_shallow[ty]
            sy = ty * TILE
            for tx in range(self.tw):
                t = row[tx]
                tone = tone_row[tx]
                sx = tx * TILE

                col = tile_color(t, tone, tx, ty)
                surf.fill(col, (sx, sy, TILE, TILE))

                # Deep water darker
                if t == T_WATER and (not shallow_row[tx]):
                    surf.fill((18, 26, 30), (sx, sy, TILE, TILE), special_flags=pygame.BLEND_RGB_SUB)

                # Micro speckles (baked)
                h = hash2(tx, ty, 999)
                if (h & 7) == 0:
                    px = sx + (h % TILE)
                    py = sy + ((h >> 3) % TILE)
                    if t == T_GRASS:
                        surf.set_at((px, py), (60, 140, 70))
                    elif t == T_DIRT:
                        surf.set_at((px, py), (120, 96, 66))
                    elif t == T_SAND:
                        surf.set_at((px, py), (240, 232, 180))
                    elif t == T_GRAVEL:
                        surf.set_at((px, py), (95, 98, 110))

                # Gravel flecks inside dirt (baked)
                if t == T_DIRT and ((h >> 9) & 15) == 0:
                    px = sx + ((h >> 12) % TILE)
                    py = sy + ((h >> 16) % TILE)
                    surf.set_at((px, py), (98, 100, 110))

        self.base_surface = surf

    def _build_tree_spatial_index(self):
        """Build a coarse spatial index for trees to speed up collision + climb queries."""
        cell = 24  # px; coarse on purpose (fast, small index)
        world_w = self.tw * TILE
        world_h = self.th * TILE
        gw = int((world_w + cell - 1) // cell)
        gh = int((world_h + cell - 1) // cell)

        self._tree_cell = cell
        self._tree_gw = gw
        self._tree_gh = gh
        self._tree_cells = [[] for _ in range(gw * gh)]
        self._tree_visit = [0] * len(self.trees)
        self._tree_visit_stamp = 1

        for i, tr in enumerate(self.trees):
            # Index the union so the same structure supports both base collision and climb queries.
            r = tr.base_rect.union(tr.climb_rect).inflate(2, 2)
            x0 = clamp(int(r.left // cell), 0, gw - 1)
            x1 = clamp(int(r.right // cell), 0, gw - 1)
            y0 = clamp(int(r.top // cell), 0, gh - 1)
            y1 = clamp(int(r.bottom // cell), 0, gh - 1)
            for cy in range(int(y0), int(y1) + 1):
                base = cy * gw
                for cx in range(int(x0), int(x1) + 1):
                    self._tree_cells[base + cx].append(i)

    def tree_indices_near_rect(self, r: pygame.Rect) -> List[int]:
        """Return tree indices near a rect using the spatial index (fast)."""
        if not getattr(self, "_tree_cells", None):
            return list(range(len(self.trees)))

        cell = self._tree_cell
        gw = self._tree_gw
        gh = self._tree_gh

        x0 = clamp(int(r.left // cell), 0, gw - 1)
        x1 = clamp(int(r.right // cell), 0, gw - 1)
        y0 = clamp(int(r.top // cell), 0, gh - 1)
        y1 = clamp(int(r.bottom // cell), 0, gh - 1)

        stamp = getattr(self, "_tree_visit_stamp", 1) + 1
        if stamp > 2_000_000_000:
            stamp = 1
            self._tree_visit = [0] * len(self.trees)
        self._tree_visit_stamp = stamp

        out: List[int] = []
        visit = self._tree_visit
        cells = self._tree_cells

        for cy in range(int(y0), int(y1) + 1):
            base = cy * gw
            for cx in range(int(x0), int(x1) + 1):
                for ti in cells[base + cx]:
                    if visit[ti] == stamp:
                        continue
                    visit[ti] = stamp
                    out.append(ti)
        return out


    def tile_at_px(self, px: float, py: float) -> int:
        tx = int(px // TILE)
        ty = int(py // TILE)
        if 0 <= tx < self.tw and 0 <= ty < self.th:
            return self.tiles[ty][tx]
        return T_WATER

    def is_shallow_water_at_px(self, px: float, py: float) -> bool:
        tx = int(px // TILE)
        ty = int(py // TILE)
        if 0 <= tx < self.tw and 0 <= ty < self.th:
            return self.tiles[ty][tx] == T_WATER and self.water_shallow[ty][tx]
        return False

    def is_deep_water_at_px(self, px: float, py: float) -> bool:
        tx = int(px // TILE)
        ty = int(py // TILE)
        if 0 <= tx < self.tw and 0 <= ty < self.th:
            return self.tiles[ty][tx] == T_WATER and (not self.water_shallow[ty][tx])
        return False

    def is_solid_at_px(self, px: float, py: float, on_raft: bool = False) -> bool:
        # Only deep water blocks (unless rafting)
        if self.is_deep_water_at_px(px, py) and (not on_raft):
            return True
        return False

    def nearest_tree_for_climb(self, p: pygame.Rect) -> Optional[int]:
        # Fast candidate query via spatial index.
        q = p.inflate(10, 10)
        best_i = None
        best_d2 = 10_000_000
        cx, cy = q.centerx, q.centery
        for i in self.tree_indices_near_rect(q):
            tr = self.trees[i]
            if tr.climb_rect.colliderect(q):
                d2 = (tr.x - cx) ** 2 + (tr.y - cy) ** 2
                if d2 < best_d2:
                    best_d2 = d2
                    best_i = i
        return best_i


# -------------------------
# Rendering helpers
# -------------------------
def _clamp_pos_to_rect(x: int, y: int, w: int, h: int, bounds: pygame.Rect) -> Tuple[int, int]:
    """Clamp a (x,y) top-left position so a w×h box stays fully within bounds."""
    if w >= bounds.width:
        x = bounds.x
    else:
        x = max(bounds.x, min(x, bounds.right - w))
    if h >= bounds.height:
        y = bounds.y
    else:
        y = max(bounds.y, min(y, bounds.bottom - h))
    return x, y

def draw_shadowed_text(surf, font, text, x, y, *, bg_alpha=150, pad=3):
    """Draw readable UI text with a soft outline and translucent backing box."""
    if not text:
        return pygame.Rect(x, y, 0, 0)

    s_shadow = font.render(text, True, C_UI_SHADOW)
    s_text = font.render(text, True, C_UI)
    tw, th = s_text.get_width(), s_text.get_height()

    bounds = pygame.Rect(0, 0, INTERNAL_W, INTERNAL_H)
    x, y = _clamp_pos_to_rect(int(x), int(y), tw + pad * 2 + 2, th + pad * 2 + 2, bounds.inflate(-4, -4))

    if bg_alpha and bg_alpha > 0:
        box = pygame.Surface((tw + pad * 2 + 2, th + pad * 2 + 2), pygame.SRCALPHA)
        box.fill((0, 0, 0, int(bg_alpha)))
        surf.blit(box, (x, y))

    tx, ty = x + pad, y + pad
    for ox, oy in ((1, 0), (0, 1), (1, 1), (-1, 1)):
        surf.blit(s_shadow, (tx + ox, ty + oy))
    surf.blit(s_text, (tx, ty))
    return pygame.Rect(x, y, tw + pad * 2 + 2, th + pad * 2 + 2)

def draw_ui_paragraph(surf, font, text: str, x: int, y: int, max_w: int, *, line_gap=2, bg_alpha=140, pad=3):
    """Word-wrap and draw multi-line UI text with readable antialiased text."""
    if not text:
        return pygame.Rect(x, y, 0, 0)
    words = text.split()
    lines_out = []
    cur = ""
    for w in words:
        test = (cur + " " + w).strip()
        if font.size(test)[0] <= max_w or not cur:
            cur = test
        else:
            lines_out.append(cur)
            cur = w
    if cur:
        lines_out.append(cur)

    lw = 0
    lh = font.get_linesize()
    for ln in lines_out:
        lw = max(lw, font.size(ln)[0])
    total_h = len(lines_out) * lh + max(0, len(lines_out) - 1) * line_gap

    bounds = pygame.Rect(0, 0, INTERNAL_W, INTERNAL_H)
    x, y = _clamp_pos_to_rect(int(x), int(y), lw + pad * 2 + 2, total_h + pad * 2 + 2, bounds.inflate(-4, -4))

    if bg_alpha and bg_alpha > 0:
        box = pygame.Surface((lw + pad * 2 + 2, total_h + pad * 2 + 2), pygame.SRCALPHA)
        box.fill((0, 0, 0, int(bg_alpha)))
        surf.blit(box, (x, y))

    cy = y + pad
    for ln in lines_out:
        s_shadow = font.render(ln, True, C_UI_SHADOW)
        s_text = font.render(ln, True, C_UI)
        for ox, oy in ((1, 0), (0, 1), (1, 1), (-1, 1)):
            surf.blit(s_shadow, (x + pad + ox, cy + oy))
        surf.blit(s_text, (x + pad, cy))
        cy += lh + line_gap
    return pygame.Rect(x, y, lw + pad * 2 + 2, total_h + pad * 2 + 2)
def tile_color(tile: int, tone: float, x: int, y: int) -> Tuple[int, int, int]:
    if tile == T_WATER:
        return dither_choice(C_WATER_DEEP, C_WATER, x, y, 0.48 + (tone - 0.5) * 0.20)
    if tile == T_SAND:
        return dither_choice(C_SAND_DARK, C_SAND, x, y, 0.60 + (tone - 0.5) * 0.35)
    if tile == T_GRASS:
        return dither_choice(C_GRASS_DARK, C_GRASS, x, y, 0.60 + (tone - 0.5) * 0.30)
    if tile == T_DIRT:
        return dither_choice((120, 98, 66), C_DIRT, x, y, 0.62 + (tone - 0.5) * 0.28)
    if tile == T_GRAVEL:
        return dither_choice((100, 102, 110), C_ROCK, x, y, 0.62 + (tone - 0.5) * 0.25)
    return (255, 0, 255)

def draw_monkey_sprite(surf: pygame.Surface, x: int, y: int, m: Monkey, t: float, highlight: bool):
    bob = int(math.sin(t * 8.0 + (x + y) * 0.02) * 1.0)
    ground_y = y + bob
    j = int(getattr(m, 'jump_z', 0.0))
    px, py = x, ground_y - j
    main = m.color_main
    dark = m.color_dark

    if highlight:
        pygame.draw.circle(surf, (255, 255, 255), (px, py + 4), 6, 1)

    # Shadow stays on the ground while the body lifts during jump
    pygame.draw.ellipse(surf, (0, 0, 0), pygame.Rect(px - 4, ground_y + 4, 8, 3), 1)
    pygame.draw.circle(surf, dark, (px + 5, py + 3), 2, 1)

    pygame.draw.rect(surf, main, pygame.Rect(px - 3, py + 1, 6, 4))
    pygame.draw.rect(surf, dark, pygame.Rect(px - 3, py + 4, 6, 1))

    pygame.draw.circle(surf, main, (px, py - 1), 3)
    pygame.draw.circle(surf, dark, (px, py - 1), 3, 1)

    pygame.draw.circle(surf, (20, 20, 22), (px - 1, py - 2), 1)
    pygame.draw.circle(surf, (20, 20, 22), (px + 1, py - 2), 1)

    pygame.draw.circle(surf, dark, (px - 4, py + 3), 1)
    pygame.draw.circle(surf, dark, (px + 4, py + 3), 1)
    pygame.draw.circle(surf, dark, (px - 2, py + 6), 1)
    pygame.draw.circle(surf, dark, (px + 2, py + 6), 1)

def draw_coconut_tree(surf: pygame.Surface, sx: int, sy: int, tr: CoconutTree, time_s: float, occluded: bool):
    trunk_col = (166, 132, 80)
    trunk_dark = (140, 110, 66)
    canopy_a = (68, 168, 86) if not occluded else (60, 150, 78)
    canopy_b = (52, 142, 68) if not occluded else (46, 126, 62)

    sway = math.sin(time_s * 0.9 + tr.x * 0.01) * 1.7
    top_dx = int(sway)

    for i in range(tr.trunk_h):
        yy = sy - i
        dx = int(top_dx * (i / tr.trunk_h))
        col = trunk_dark if (i % 5) in (0, 1) else trunk_col
        pygame.draw.line(surf, col, (sx + dx - 1, yy), (sx + dx + 1, yy))

    cx = sx + top_dx
    cy = sy - tr.trunk_h

    for k in range(7):
        ang = (k / 7.0) * math.tau + time_s * 0.15
        lx = int(cx + math.cos(ang) * (tr.canopy_r + 1))
        ly = int(cy + math.sin(ang) * (tr.canopy_r * 0.55))
        pygame.draw.circle(surf, canopy_b, (lx, ly), 3)
        pygame.draw.circle(surf, canopy_a, (lx - 1, ly - 1), 2)

    pygame.draw.circle(surf, canopy_b, (cx, cy), tr.canopy_r)
    pygame.draw.circle(surf, canopy_a, (cx - 2, cy - 2), max(2, tr.canopy_r - 2))

    for k in range(3):
        ox = int(math.cos(time_s * 0.4 + k) * 2)
        oy = int(math.sin(time_s * 0.5 + k) * 1)
        pygame.draw.circle(surf, (120, 92, 56), (cx + ox + k - 1, cy + 4 + oy), 2)

def draw_log(surf: pygame.Surface, sx: int, sy: int):
    base = (126, 92, 56)
    dark = (98, 72, 44)
    bark = (140, 104, 66)
    pygame.draw.rect(surf, base, pygame.Rect(sx - 8, sy - 3, 16, 6))
    pygame.draw.rect(surf, dark, pygame.Rect(sx - 8, sy - 3, 16, 1))
    pygame.draw.rect(surf, dark, pygame.Rect(sx - 8, sy + 2, 16, 1))
    pygame.draw.rect(surf, bark, pygame.Rect(sx - 8, sy - 3, 2, 6))
    pygame.draw.rect(surf, bark, pygame.Rect(sx + 6, sy - 3, 2, 6))
    pygame.draw.circle(surf, dark, (sx - 7, sy), 1)
    pygame.draw.circle(surf, dark, (sx + 6, sy), 1)

def draw_raft(surf: pygame.Surface, sx: int, sy: int, w: int = 54, h: int = 30):
    # Simple planked raft with rope corners
    base = (166, 132, 80)
    dark = (140, 110, 66)
    rope = (235, 245, 250)
    r = pygame.Rect(sx - w // 2, sy - h // 2, w, h)
    pygame.draw.rect(surf, base, r)
    pygame.draw.rect(surf, dark, pygame.Rect(r.x, r.y, r.w, 2))
    pygame.draw.rect(surf, dark, pygame.Rect(r.x, r.bottom - 2, r.w, 2))
    # planks
    for i in range(5):
        px = r.x + 4 + i * ((r.w - 8) // 5)
        pygame.draw.line(surf, dark, (px, r.y + 3), (px, r.bottom - 4))
    # rope corners
    for (cx, cy) in ((r.x + 2, r.y + 2), (r.right - 3, r.y + 2), (r.x + 2, r.bottom - 3), (r.right - 3, r.bottom - 3)):
        pygame.draw.rect(surf, rope, pygame.Rect(cx, cy, 2, 2))
    pygame.draw.rect(surf, (90, 70, 44), r, 1)

def draw_rocknode(surf: pygame.Surface, sx: int, sy: int, size: int):
    # Tiny rock (no shadow)
    a = (140, 142, 150)
    b = (110, 112, 122)
    c = (95, 98, 110)
    r = 1 + size
    pygame.draw.circle(surf, b, (sx, sy), r + 1)
    pygame.draw.circle(surf, a, (sx - 1, sy - 1), r)
    if r >= 2:
        pygame.draw.circle(surf, c, (sx + 1, sy + 1), 1)

def draw_veg(surf: pygame.Surface, sx: int, sy: int, kind: int, time_s: float):
    if kind == 0:  # bush
        a = (50, 140, 70)
        b = (40, 120, 60)
        pygame.draw.circle(surf, b, (sx, sy), 5)
        pygame.draw.circle(surf, a, (sx - 2, sy - 2), 4)
        pygame.draw.circle(surf, a, (sx + 3, sy - 1), 3)
        pygame.draw.circle(surf, (30, 90, 45), (sx + 1, sy + 2), 2)
    elif kind == 1:  # fern
        stem = (42, 120, 62)
        tip = (62, 168, 86)
        sway = int(math.sin(time_s * 1.3 + (sx + sy) * 0.01) * 1.0)
        pygame.draw.line(surf, stem, (sx, sy + 3), (sx + sway, sy - 6))
        for k in range(6):
            pygame.draw.line(surf, tip, (sx + sway, sy - 6 + k), (sx + sway + 3, sy - 4 + k))
            pygame.draw.line(surf, tip, (sx + sway, sy - 6 + k), (sx + sway - 3, sy - 4 + k))
    else:  # flower
        g = (58, 150, 78)
        p = (238, 120, 175)
        y = (250, 230, 120)
        pygame.draw.line(surf, g, (sx, sy + 3), (sx, sy - 2))
        pygame.draw.circle(surf, p, (sx, sy - 4), 2)
        pygame.draw.circle(surf, y, (sx, sy - 4), 1)

def draw_pickup(surf: pygame.Surface, sx: int, sy: int, w: items.WorldItem, time_s: float):
    grounded = (w.item_id in (items.COCONUT, getattr(items, "PALM_LEAF", "palm_leaf"), getattr(items, "SEAWEED", "seaweed"))) or bool(getattr(w, "grounded", False))
    if grounded:
        items.draw_icon(pygame, surf, sx - 5, sy - 6, w.item_id, scale=1)
    else:
        bob = int(math.sin(time_s * 2.8 + w.bob_phase) * 1.5)
        items.draw_icon(pygame, surf, sx - 5, sy - 7 + bob, w.item_id, scale=1)


# -------------------------
# Game
# -------------------------
class Game:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("MonkeyStranded")
        self.win_w, self.win_h = self._sanitize_window_size(WIN_W, WIN_H)
        self._rebuild_window(self.win_w, self.win_h)

        self.screen = pygame.Surface((INTERNAL_W, INTERNAL_H)).convert()
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("arial", 13, bold=True)
        self.font_small = pygame.font.SysFont("arial", 11, bold=True)

        self.sfx = sfx.SFXManager()

        self.world = IslandWorld(seed=7)


        self.mouse_x = 0
        self.mouse_y = 0

        try:
            spawn_px, spawn_py = self._find_land_spawn()
        except Exception:
            spawn_px, spawn_py = self._fallback_land_spawn()

        self.shared_inv = items.Inventory(max_slots=50)

        self.monkeys: List[Monkey] = [
            Monkey("Koko", spawn_px - 10, spawn_py + 6, (170, 120, 90), (130, 92, 70), inv=self.shared_inv),
            Monkey("Mimi", spawn_px + 10, spawn_py + 6, (150, 105, 78), (115, 82, 62), inv=self.shared_inv),
        ]

        self.p1_idx = 0  # controlled monkey
        self.p2_idx = 1  # other monkey

        # Core time accumulator (used for day/night, weather, spawn checks)
        self.time_s = 0.0

        # World ambience management (keeps wildlife present near the active camera area)
        self._bird_recenter_t = 0.0
        self._iguana_recenter_t = 0.0
        self.projectiles: List[RockProjectile] = []
        self.birds: List[Bird] = []
        self.crabs: List[Crab] = []
        self.iguanas: List[Iguana] = []
        self._day_seen = self.day_index()
        self._spawn_initial_crabs()
        self._spawn_initial_iguana()
        self._spawn_birds()

        self.cam_x = float(spawn_px - INTERNAL_W / 2)
        self.cam_y = float(spawn_py - INTERNAL_H / 2)
        self.anthill_x, self.anthill_y = self._find_anthill_site()
        self._anthill_cooldown = 0.0

        self.running = True
        self.show_inv = False
        # Inventory UI hit-testing + origin preview cache
        self._inv_layout = None  # populated during UI draw when inventory is visible
        self._origin_preview_cache = {}  # (item_id, size)->Surface


        # Follow mode: press F to make the non-controlled monkey trail the controlled monkey.
        self.follow_enabled = False

        # Gather mode (G): command the non-controlled monkey to wander and interact (press E) automatically.
        self.gather_enabled = False
        self._gather_target = None  # type: Optional[Tuple[float, float]]
        self._gather_retarget_t = 0.0
        self._gather_interact_cd = 0.0
        self._follow_points: List[Tuple[float, float]] = []
        self._follow_record_t = 0.0


        self._prev_space = False
        self._prev_rctrl = False
        self._prev_e = False
        self._prev_rshift = False
        self._prev_i = False
        self._prev_c = False

        self._last_state: Dict[str, Any] = {}
        self._last_hint: str = ""
        self._hint_t: float = 0.0

        self._step_t = 0.0
        self._seaweed_wash_t = 0.0
        self._seaweed_wash_every = random.uniform(10.0, 22.0)
        self._seaweed_wash_every = 16.0

        self._pickup_cleanup_t = 0.0  # periodic cleanup for timed pickups (e.g., shore seaweed)

        # -------------------------
        # Performance caches
        # -------------------------
        # Ocean ambience volume scanning is moderately expensive; update it at a lower rate.
        self._ocean_scan_t = 0.0
        self._ocean_vol = 0.0

        # Shore foam is a purely visual effect; render it to an off-screen surface at a lower rate.
        # Cache foam on a slightly larger surface and sample it with an offset so it stays world-locked
        # while the camera moves (prevents jitter) without disabling the animated shoreline motion.
        self._foam_margin = TILE * 4
        self._foam_surf = pygame.Surface((INTERNAL_W + self._foam_margin * 2, INTERNAL_H + self._foam_margin * 2), pygame.SRCALPHA)
        self._foam_last_update = -999.0
        # Anchor is the world top-left that corresponds to (0, 0) of _foam_surf.
        self._foam_anchor_camx = -999999
        self._foam_anchor_camy = -999999

    def _sanitize_monkey_index(self, idx: Any, fallback: int = 0) -> int:
        if not self.monkeys:
            return 0
        if not isinstance(idx, int):
            return max(0, min(len(self.monkeys) - 1, int(fallback)))
        if idx < 0 or idx >= len(self.monkeys):
            return max(0, min(len(self.monkeys) - 1, int(fallback)))
        return idx

    def _normalize_monkey_indices(self) -> int:
        self.p1_idx = self._sanitize_monkey_index(getattr(self, "p1_idx", 0), 0)
        if len(self.monkeys) > 1:
            default_p2 = 1 if self.p1_idx == 0 else 0
        else:
            default_p2 = self.p1_idx
        self.p2_idx = self._sanitize_monkey_index(getattr(self, "p2_idx", default_p2), default_p2)
        if len(self.monkeys) > 1 and self.p2_idx == self.p1_idx:
            self.p2_idx = 1 if self.p1_idx == 0 else 0
        return self.p1_idx

    def _sanitize_window_size(self, w: int, h: int) -> Tuple[int, int]:
        try:
            w = int(w)
        except Exception:
            w = WIN_W
        try:
            h = int(h)
        except Exception:
            h = WIN_H
        w = max(MIN_WINDOW_W, min(7680, w))
        h = max(MIN_WINDOW_H, min(4320, h))
        return w, h

    def _rebuild_window(self, w: Optional[int] = None, h: Optional[int] = None) -> None:
        if w is None or h is None:
            w, h = getattr(self, 'win_w', WIN_W), getattr(self, 'win_h', WIN_H)
        self.win_w, self.win_h = self._sanitize_window_size(w, h)
        flags = pygame.RESIZABLE | pygame.DOUBLEBUF
        try:
            flags |= pygame.HWSURFACE
        except Exception:
            pass
        self._vsync_enabled = False
        try:
            self.window = pygame.display.set_mode((self.win_w, self.win_h), flags, vsync=1)
            self._vsync_enabled = True
        except TypeError:
            self.window = pygame.display.set_mode((self.win_w, self.win_h), flags)
        except pygame.error:
            self.window = pygame.display.set_mode((self.win_w, self.win_h), pygame.RESIZABLE)
        self._update_viewport()

    def _update_viewport(self) -> None:
        win_w = max(1, int(getattr(self, 'win_w', WIN_W)))
        win_h = max(1, int(getattr(self, 'win_h', WIN_H)))
        scale = min(win_w / float(INTERNAL_W), win_h / float(INTERNAL_H))
        scale = max(1.0, scale)
        self.view_scale = scale
        self.view_w = max(1, int(round(INTERNAL_W * scale)))
        self.view_h = max(1, int(round(INTERNAL_H * scale)))
        self.view_x = (win_w - self.view_w) // 2
        self.view_y = (win_h - self.view_h) // 2

    def _window_to_internal(self, pos: Tuple[int, int]) -> Optional[Tuple[int, int]]:
        try:
            mx, my = int(pos[0]), int(pos[1])
        except Exception:
            return None
        if mx < self.view_x or my < self.view_y or mx >= self.view_x + self.view_w or my >= self.view_y + self.view_h:
            return None
        ix = int((mx - self.view_x) / max(1e-6, self.view_scale))
        iy = int((my - self.view_y) / max(1e-6, self.view_scale))
        ix = max(0, min(INTERNAL_W - 1, ix))
        iy = max(0, min(INTERNAL_H - 1, iy))
        return ix, iy

    def _find_anthill_site(self) -> Tuple[float, float]:
        cx = self.world.tw // 2
        cy = self.world.th // 2
        best = None
        best_d2 = 10**18
        for ty in range(max(2, cy - 24), min(self.world.th - 2, cy + 25)):
            for tx in range(max(2, cx - 24), min(self.world.tw - 2, cx + 25)):
                if self.world.tiles[ty][tx] != T_DIRT:
                    continue
                px = tx * TILE + TILE // 2
                py = ty * TILE + TILE // 2
                d2 = (tx - cx) * (tx - cx) + (ty - cy) * (ty - cy)
                if d2 < best_d2:
                    best_d2 = d2
                    best = (float(px), float(py))
        if best is not None:
            return best
        return float(cx * TILE + TILE // 2), float(cy * TILE + TILE // 2)

    def _anthill_screen_pos(self) -> Tuple[int, int]:
        return int(self.anthill_x - self.cam_x), int(self.anthill_y - self.cam_y)

    def _click_hits_anthill(self, pos: Tuple[int, int]) -> bool:
        pt = self._window_to_internal(pos)
        if pt is None:
            return False
        sx, sy = self._anthill_screen_pos()
        dx = pt[0] - sx
        dy = pt[1] - sy
        return (dx * dx + dy * dy) <= (14 * 14)

    def _draw_anthill(self, sx: int, sy: int) -> None:
        pygame.draw.ellipse(self.screen, (108, 78, 48), (sx - 11, sy - 7, 22, 14))
        pygame.draw.ellipse(self.screen, (132, 96, 58), (sx - 9, sy - 6, 18, 12), 1)
        pygame.draw.ellipse(self.screen, (38, 24, 16), (sx - 4, sy - 2, 8, 5))
        pygame.draw.circle(self.screen, (160, 122, 84), (sx - 6, sy - 5), 1)
        pygame.draw.circle(self.screen, (160, 122, 84), (sx + 5, sy - 4), 1)
        pygame.draw.circle(self.screen, (86, 60, 38), (sx - 1, sy - 7), 1)

    def _run_embedded_insect_mode(self) -> str:
        prev_hook = sys.excepthook
        module_name = '__embedded_insect_mode__'
        prev_module = sys.modules.get(module_name)
        try:
            prev_caption = pygame.display.get_caption()
        except Exception:
            prev_caption = ('MonkeyStranded', 'MonkeyStranded')
        try:
            pygame.event.clear()
        except Exception:
            pass
        insect_mod = types.ModuleType(module_name)
        insect_mod.__dict__.update({
            '__name__': module_name,
            '__file__': os.path.abspath(__file__),
            '__embed_start_size__': (int(self.win_w), int(self.win_h)),
        })
        sys.modules[module_name] = insect_mod
        result = 'resume'
        try:
            exec(EMBEDDED_INSECTS_CODE, insect_mod.__dict__, insect_mod.__dict__)
            result = str(insect_mod.__dict__.get('__embed_return_value__', 'resume'))
        except BaseException as exc:
            write_crash_report(exc, state={'where': 'embedded insect mode'})
            self.show_hint('Insect world crashed. Returned to island.')
            result = 'resume'
        finally:
            if prev_module is not None:
                sys.modules[module_name] = prev_module
            else:
                sys.modules.pop(module_name, None)
            sys.excepthook = prev_hook
            self._rebuild_window(getattr(self, 'win_w', WIN_W), getattr(self, 'win_h', WIN_H))
            try:
                pygame.display.set_caption(prev_caption[0] if prev_caption else 'MonkeyStranded')
            except Exception:
                pass
            try:
                self.screen = pygame.Surface((INTERNAL_W, INTERNAL_H)).convert()
            except Exception:
                self.screen = pygame.Surface((INTERNAL_W, INTERNAL_H))
            self.font = pygame.font.SysFont('arial', 13, bold=True)
            self.font_small = pygame.font.SysFont('arial', 11, bold=True)
            self.mouse_x = self.view_x + self.view_w // 2
            self.mouse_y = self.view_y + self.view_h // 2
            self._prev_e = True
            self._prev_rshift = True
            try:
                pygame.event.clear()
            except Exception:
                pass
        return result

    def _enter_anthill(self) -> bool:
        if getattr(self, '_anthill_cooldown', 0.0) > 0.0:
            return False
        self._normalize_monkey_indices()
        self._run_embedded_insect_mode()
        self._anthill_cooldown = 0.35
        self._prev_e = True
        self._prev_rshift = True
        self.show_hint('Returned from insect world.')
        return True

    # ---------
    # Birds
    # ---------
    def _spawn_birds(self):
        random.seed(7000)
        world_w = self.world.tw * TILE
        world_h = self.world.th * TILE

        def rand_vel():
            ang = random.random() * math.tau
            sp = random.uniform(22, 42)
            return math.cos(ang) * sp, math.sin(ang) * sp

        def pick_shore_pos():
            for _ in range(700):
                tx = random.randint(4, self.world.tw - 5)
                ty = random.randint(4, self.world.th - 5)
                if self.world.tiles[ty][tx] != T_SAND:
                    continue
                near_water = False
                for ox, oy in ((1,0),(-1,0),(0,1),(0,-1)):
                    if self.world.tiles[ty+oy][tx+ox] == T_WATER:
                        near_water = True
                        break
                if near_water:
                    return tx*TILE + TILE//2, ty*TILE + TILE//2
            return world_w * 0.5, world_h * 0.5

        def pick_inland_pos():
            cx = world_w * 0.5
            cy = world_h * 0.5
            for _ in range(700):
                tx = random.randint(8, self.world.tw - 9)
                ty = random.randint(8, self.world.th - 9)
                if self.world.tiles[ty][tx] not in (T_GRASS, T_DIRT):
                    continue
                px = tx*TILE + TILE//2
                py = ty*TILE + TILE//2
                if (px-cx)**2 + (py-cy)**2 < (min(world_w, world_h)*0.22)**2:
                    return px, py
            return cx, cy

        for _ in range(10):
            x, y = pick_shore_pos()
            vx, vy = rand_vel()
            self.birds.append(Bird("seagull", x, y - random.randint(18, 40), vx, vy, target_x=x, target_y=y))

        for _ in range(8):
            x, y = pick_inland_pos()
            vx, vy = rand_vel()
            self.birds.append(Bird("parrot", x, y - random.randint(18, 40), vx, vy, target_x=x, target_y=y))

    # ---------
    # State/Hints
    # ---------
    def _snapshot_state(self, last_event: Optional[str] = None):
        try:
            m1 = self.monkeys[self.p1_idx]
            m2 = self.monkeys[self.p2_idx]
            self._last_state = {
                "p1": m1.name,
                "p2": m2.name,
                "p1_pos": (round(m1.x, 2), round(m1.y, 2)),
                "p2_pos": (round(m2.x, 2), round(m2.y, 2)),
                "p1_climb": (m1.climbing, m1.climb_tree_idx, round(m1.climb_t, 3)),
                "p2_climb": (m2.climbing, m2.climb_tree_idx, round(m2.climb_t, 3)),
                "p1_raft": m1.on_raft,
                "p2_raft": m2.on_raft,
                "cam": (round(self.cam_x, 2), round(self.cam_y, 2)),
                "pickups": len(self.world.pickups),
                "trees": len(self.world.trees),
                "logs": len(self.world.logs),
                "rafts": len(getattr(self.world, "rafts", [])),
                "rocks": len(self.world.rocks),
                "veg": len(self.world.veg),
                "birds": len(self.birds),
                "projectiles": len(self.projectiles),
                "show_inv": self.show_inv,
                "follow": getattr(self, "follow_enabled", False),
                "follow_points": len(getattr(self, "_follow_points", [])),
                "day": self.day_index(),
                "last_event": last_event or self._last_state.get("last_event"),
            }
        except Exception:
            pass

    def day_index(self) -> int:
        return int(getattr(self, 'time_s', 0.0) // DAY_SECONDS)

    def show_hint(self, msg: str, seconds: float = 1.25):
        self._last_hint = msg
        self._hint_t = seconds


    # ---------
    # Follow mode (F)
    # ---------
    def _follow_reset(self):
        self._follow_points.clear()
        self._follow_record_t = 0.0

    def _follow_record_leader(self, dt: float):
        if (not self.follow_enabled) or dt <= 0.0:
            return
        self._follow_record_t += dt
        if self._follow_record_t < 0.05:
            return
        self._follow_record_t = 0.0
        leader = self.monkeys[self.p1_idx]
        self._follow_points.append((float(leader.x), float(leader.y)))
        if len(self._follow_points) > 240:
            del self._follow_points[:len(self._follow_points) - 240]

    def _update_follow_ai(self, dt: float):
        if (not self.follow_enabled) or dt <= 0.0:
            return
        leader = self.monkeys[self.p1_idx]
        follower = self.monkeys[self.p2_idx]

        # Follow is a "command": ensure the follower is not stuck in climb mode.
        if follower.climbing:
            follower.climbing = False
            follower.climb_tree_idx = None
            follower.climb_t = 0.0

        # Target a leader breadcrumb a short time in the past to avoid standing on top of them.
        delay = 18  # ~0.9s at 0.05s sampling
        if len(self._follow_points) >= delay:
            tx, ty = self._follow_points[-delay]
        elif self._follow_points:
            tx, ty = self._follow_points[0]
        else:
            tx, ty = float(leader.x), float(leader.y)

        dx = tx - follower.x
        dy = ty - follower.y
        dist = math.hypot(dx, dy)

        desired = 18.0
        if dist <= desired:
            return

        spd_mult = 1.0
        if dist >= 120.0:
            spd_mult = 1.25
        self._move_monkey_ai(self.p2_idx, dt, tx, ty, spd_mult=spd_mult)

    # ---------
    
    # ---------
    # Gather mode (G)
    # ---------
    def _gather_reset(self):
        self._gather_target = None
        self._gather_retarget_t = 0.0
        self._gather_interact_cd = 0.0

    def _update_gather_ai(self, dt: float):
        """Wander and repeatedly interact (press E) with nearby objects/tiles."""
        if (not self.gather_enabled) or dt <= 0.0:
            return
        idx = self.p2_idx
        m = self.monkeys[idx]
        if m.climbing:
            # Gather is a ground behavior; drop out of climb mode if needed.
            m.climbing = False
            m.climb_tree_idx = None
            m.climb_t = 0.0

        # Retarget periodically to keep wandering.
        self._gather_retarget_t -= dt
        if (self._gather_target is None) or (self._gather_retarget_t <= 0.0):
            # Pick a new nearby roam target; prefer land, but allow occasional shoreline wandering.
            world_w = self.world.tw * TILE
            world_h = self.world.th * TILE
            tx, ty = m.x, m.y
            for _ in range(16):
                ang = random.random() * (math.pi * 2.0)
                rad = random.uniform(60.0, 280.0)
                cx = clamp(m.x + math.cos(ang) * rad, 8.0, float(world_w - 8))
                cy = clamp(m.y + math.sin(ang) * rad, 8.0, float(world_h - 8))
                t = self.world.tile_at_px(cx, cy)
                if (t != T_WATER) or (random.random() < 0.25):
                    tx, ty = cx, cy
                    break
            self._gather_target = (float(tx), float(ty))
            self._gather_retarget_t = random.uniform(1.2, 3.2)

        # Move toward current target.
        if self._gather_target is not None:
            tx, ty = self._gather_target
            if math.hypot(tx - m.x, ty - m.y) <= 14.0:
                self._gather_retarget_t = 0.0
            else:
                self._move_monkey_ai(idx, dt, tx, ty, spd_mult=1.0)

        # Periodically interact with nearby resources/pickups.
        self._gather_interact_cd = max(0.0, self._gather_interact_cd - dt)
        if self._gather_interact_cd <= 0.0:
            did = self._interact(idx)
            # If something happened, wait a bit longer so we don't spam the same spot.
            self._gather_interact_cd = 0.85 if did else 0.35

    # Spawn/camera
    # ---------

    def _ocean_volume_near(self, px: float, py: float) -> float:
        # Look in a small radius (tiles) for water; if close, ramp up volume.
        tx = int(px // TILE)
        ty = int(py // TILE)
        best = 999
        for oy in range(-6, 7):
            for ox in range(-6, 7):
                nx, ny = tx + ox, ty + oy
                if 0 <= nx < self.world.tw and 0 <= ny < self.world.th:
                    if self.world.tiles[ny][nx] == T_WATER:
                        d = max(abs(ox), abs(oy))
                        if d < best:
                            best = d
        if best == 999:
            return 0.0
        if best <= 1:
            return 0.65
        if best == 2:
            return 0.45
        if best == 3:
            return 0.30
        if best == 4:
            return 0.18
        if best == 5:
            return 0.08
        return 0.0
        return 0.0

    def _is_on_screen_world(self, x: float, y: float, pad: int = 0) -> bool:
        # Screen-space check in world coordinates (uses INTERNAL_W/H camera viewport)
        if x < self.cam_x - pad or x > self.cam_x + INTERNAL_W + pad:
            return False
        if y < self.cam_y - pad or y > self.cam_y + INTERNAL_H + pad:
            return False
        return True

    def _spatial_volume(
        self,
        sx: float,
        sy: float,
        base_volume: float = 1.0,
        max_dist: float = 300.0,
        min_dist: float = 24.0,
        *,
        base: float | None = None,
    ) -> float:
        """Distance attenuation for SFX.

        Supports both legacy callers that pass `base` positionally and newer callers that pass
        `base_volume=` as a keyword. Returns a clamped 0..1 volume scalar.
        """
        # Back-compat: some call sites may still pass `base=` (or a 3rd positional) under the old name.
        if base is not None:
            base_volume = float(base)

        try:
            listener = self.monkeys[self.p1_idx]
            dx = float(sx) - float(listener.x)
            dy = float(sy) - float(listener.y)
        except Exception:
            return 0.0

        d = math.hypot(dx, dy)
        if d >= float(max_dist):
            return 0.0

        if d <= float(min_dist):
            return max(0.0, min(1.0, float(base_volume)))

        span = max(1.0, float(max_dist) - float(min_dist))
        t = 1.0 - ((d - float(min_dist)) / span)
        t = max(0.0, min(1.0, t))

        # Slightly softer curve than linear; avoids harsh cutoffs.
        vol = float(base_volume) * (t * t)
        return max(0.0, min(1.0, vol))

    def _play_bird_sfx(self, bird, key: str, base_volume: float):
        # Birds: not audible if off-screen; attenuate by distance when on-screen
        if bird is None:
            return
        if not self._is_on_screen_world(getattr(bird, "x", 0.0), getattr(bird, "y", 0.0), pad=8):
            return
        max_dist = math.hypot(INTERNAL_W, INTERNAL_H) * 0.95
        vol = self._spatial_volume(float(bird.x), float(bird.y), float(base_volume), max_dist=max_dist, min_dist=28.0)
        if vol <= 0.01:
            return
        self.sfx.play(key, vol)


    def _fallback_land_spawn(self) -> Tuple[int, int]:
        """Fallback spawn if land search method is missing or fails."""
        # Try a few random points until we find grass/sand.
        for _ in range(5000):
            tx = random.randint(4, self.world.tw - 5)
            ty = random.randint(4, self.world.th - 5)
            if self.world.tiles[ty][tx] in (T_GRASS, T_SAND):
                return tx * TILE + TILE // 2, ty * TILE + TILE // 2
        # Absolute fallback: center of world.
        return (self.world.tw // 2) * TILE, (self.world.th // 2) * TILE



    def _find_land_spawn(self) -> Tuple[int, int]:
        cx = self.world.tw // 2
        cy = self.world.th // 2
        for r in range(1, 120):
            for _ in range(200):
                tx = random.randint(cx - r, cx + r)
                ty = random.randint(cy - r, cy + r)
                if 0 <= tx < self.world.tw and 0 <= ty < self.world.th:
                    if self.world.tiles[ty][tx] in (T_GRASS, T_SAND):
                        px = tx * TILE + TILE // 2
                        py = ty * TILE + TILE // 2
                        return px, py
        return cx * TILE, cy * TILE

    # ---------
    # Input loop
    # ---------
    def run(self):
        while self.running:
            self._normalize_monkey_indices()
            dt = self.clock.tick(FPS) / 1000.0
            self.time_s += dt
            self._handle_events()
            self._update(dt)
            self._draw()
        pygame.quit()

    def _handle_events(self):
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                self._snapshot_state("QUIT")
                self.running = False
            elif e.type == pygame.KEYDOWN:
                self._snapshot_state(f"KEYDOWN:{e.key}")
                if e.key == pygame.K_ESCAPE:
                    self.running = False
                elif e.key == pygame.K_TAB:
                    self.p1_idx, self.p2_idx = self.p2_idx, self.p1_idx
                    if self.follow_enabled:
                        self._follow_reset()
                    if self.gather_enabled:
                        self._gather_reset()
                elif e.key == pygame.K_f:
                    self.follow_enabled = not self.follow_enabled
                    self._follow_reset()
                    # Prime breadcrumb buffer so follow starts immediately.
                    leader = self.monkeys[self.p1_idx]
                    self._follow_points.append((float(leader.x), float(leader.y)))
                    self.sfx.play("ui_toggle", 0.40)
                    self.show_hint("Follow: ON" if self.follow_enabled else "Follow: OFF")
                elif e.key == pygame.K_g:
                    self.gather_enabled = not self.gather_enabled
                    # Gather is a command for the non-controlled monkey; it overrides manual arrows and follow.
                    if self.gather_enabled:
                        if self.follow_enabled:
                            self.follow_enabled = False
                            self._follow_reset()
                        self._gather_reset()
                    self.sfx.play("ui_toggle", 0.40)
                    self.show_hint("Gather: ON" if self.gather_enabled else "Gather: OFF")
            elif e.type == pygame.VIDEORESIZE:
                self._snapshot_state(f"VIDEORESIZE:{e.w}x{e.h}")
                self._rebuild_window(e.w, e.h)
            elif e.type == pygame.MOUSEMOTION:
                self.mouse_x, self.mouse_y = e.pos
            elif e.type == pygame.MOUSEBUTTONDOWN:
                if e.button == 1:
                    if self._click_hits_anthill(e.pos):
                        if self._enter_anthill():
                            continue
                    if not self.show_inv:
                        self._try_throw_rock()
                    else:
                        internal_pos = self._window_to_internal(e.pos)
                        if internal_pos is None:
                            continue
                        mx, my = internal_pos
                        if self._handle_inventory_click(mx, my):
                            self.sfx.play("ui_click", 0.35)
                        else:
                            pass
            elif e.type == pygame.MOUSEWHEEL:
                self._snapshot_state(f"MOUSEWHEEL:{e.y}")
                self.shared_inv.cycle_selected(-e.y)

    # ---------
    # Interactions
    # ---------
    def _try_toggle_climb(self, idx: int):
        m = self.monkeys[idx]
        if m.climbing:
            m.climbing = False
            m.climb_tree_idx = None
            m.climb_t = 0.0
            return

        tree_i = self.world.nearest_tree_for_climb(m.rect())
        if tree_i is None:
            return
        tr = self.world.trees[tree_i]
        m.climbing = True
        m.climb_tree_idx = tree_i
        m.climb_t = 0.0
        m.x = tr.x
        m.y = tr.y - 2

    def _try_jump(self, idx: int, boost: float = 1.0):
        """Start a jump (pseudo-height). Jump is used to 'grab' a tree for climbing."""
        m = self.monkeys[idx]
        if m.climbing or m.on_raft:
            return
        if m.jumping:
            return
        m.jumping = True
        m.jump_z = 0.0
        m.jump_vz = JUMP_V0 * float(boost)

    def _update_jump_physics(self, dt: float):
        """Integrate jump height. Visual-only in this top-down prototype, but gates climbing."""
        g = JUMP_G
        for m in self.monkeys:
            if m.climbing:
                m.jumping = False
                m.jump_z = 0.0
                m.jump_vz = 0.0
                continue
            if not m.jumping:
                m.jump_z = 0.0
                m.jump_vz = 0.0
                continue
            m.jump_vz -= g * dt
            m.jump_z += m.jump_vz * dt
            if m.jump_z <= 0.0:
                m.jump_z = 0.0
                m.jump_vz = 0.0
                m.jumping = False


    def _spawn_pickup(self, item_id: str, x: float, y: float, qty: int = 1):
        self.world.pickups.append(items.WorldItem(item_id=item_id, x=x, y=y, qty=qty, bob_phase=random.random() * 6.28))

    def _spawn_leaf_after_coconut(self, tr: CoconutTree):
        """Drop exactly 1 palm leaf (slowly) after coconuts are dropped from this tree."""
        try:
            leaf_id = items.PALM_LEAF
        except Exception:
            leaf_id = "palm_leaf"

        # Start above the canopy and fall toward the base.
        start_x = tr.x + random.randint(-max(6, tr.canopy_r // 2), max(6, tr.canopy_r // 2))
        start_y = tr.y - tr.trunk_h - random.randint(max(10, tr.canopy_r // 2), max(14, tr.canopy_r))
        target_y = tr.y + random.randint(2, 8)

        w = items.WorldItem(item_id=leaf_id, x=float(start_x), y=float(start_y), qty=1, bob_phase=0.0)
        # Dynamic attributes (WorldItem is not slotted, so this is safe).
        w.falling = True
        w.vy = 0.0
        w.target_y = float(target_y)
        w.drift = random.uniform(-10.0, 10.0) * 0.35
        w.grounded = True  # disables bob in draw_pickup
        self.world.pickups.append(w)

    def _update_pickup_physics(self, dt: float):
        """Lightweight physics for special pickups (falling palm leaves)."""
        if dt <= 0.0:
            return
        try:
            leaf_id = items.PALM_LEAF
        except Exception:
            leaf_id = "palm_leaf"

        for w in self.world.pickups:
            if w.item_id != leaf_id:
                continue
            if not bool(getattr(w, "falling", False)):
                continue

            vy = float(getattr(w, "vy", 0.0))
            # Slow fall: gentle acceleration and a low terminal velocity.
            vy = min(vy + 42.0 * dt, 58.0)

            w.y += vy * dt
            w.x += float(getattr(w, "drift", 0.0)) * dt

            w.vy = vy

            ty = float(getattr(w, "target_y", w.y))
            if w.y >= ty:
                w.y = ty
                w.falling = False
                w.vy = 0.0

    def _maybe_wash_up_seaweed(self, dt: float):
        """Occasionally spawns seaweed on shoreline sand."""
        self._seaweed_wash_t += dt
        if self._seaweed_wash_t < self._seaweed_wash_every:
            return
        self._seaweed_wash_t = 0.0

        try:
            seaweed_id = items.SEAWEED
        except Exception:
            seaweed_id = "seaweed"

        # Cap active seaweed so the beach doesn't flood.
        active = 0
        for w in self.world.pickups:
            if w.item_id == seaweed_id:
                active += 1
        if active >= 18:
            return

        spawn_n = 1 if random.random() < 0.70 else (2 if random.random() < 0.80 else 3)
        spawned = 0

        for _ in range(120):
            if spawned >= spawn_n:
                break
            tx = random.randint(2, self.world.tw - 3)
            ty = random.randint(2, self.world.th - 3)
            if self.world.tiles[ty][tx] != T_SAND:
                continue
            near_water = False
            for ox, oy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                if self.world.tiles[ty + oy][tx + ox] == T_WATER:
                    near_water = True
                    break
            if not near_water:
                continue

            px = tx * TILE + TILE // 2 + random.randint(-3, 3)
            py = ty * TILE + TILE // 2 + random.randint(-2, 2)

            # Avoid stacking seaweed in one spot.
            too_close = False
            for ww in self.world.pickups:
                if ww.item_id == seaweed_id and (ww.x - px) ** 2 + (ww.y - py) ** 2 < (12 ** 2):
                    too_close = True
                    break
            if too_close:
                continue

            w = items.WorldItem(item_id=seaweed_id, x=float(px), y=float(py), qty=1, bob_phase=0.0)
            w.grounded = True  # no bob
            w.expire_t = self.time_s + random.uniform(22.0, 45.0)
            self.world.pickups.append(w)
            spawned += 1


    def _cleanup_timed_pickups(self):
        """Remove timed pickups (currently: shore seaweed) so they don't accumulate."""
        now = self.time_s
        try:
            seaweed_id = items.SEAWEED
        except Exception:
            seaweed_id = "seaweed"

        if not self.world.pickups:
            return

        kept = []
        for w in self.world.pickups:
            exp = getattr(w, "expire_t", None)
            if exp is not None and now >= float(exp):
                continue
            kept.append(w)
        self.world.pickups = kept

    def _nearest_log_index(self, mx: float, my: float, max_dist: float = 18.0) -> Optional[int]:
        best_i = None
        best_d2 = 10_000_000
        for i, lg in enumerate(self.world.logs):
            d2 = (lg.x - mx) ** 2 + (lg.y - my) ** 2
            if d2 < best_d2:
                best_d2 = d2
                best_i = i
        if best_i is None:
            return None
        if best_d2 > (max_dist ** 2):
            return None
        return best_i

    def _loot_dead_bird(self, idx: int) -> bool:
        m = self.monkeys[idx]
        if m.climbing:
            return False
        best = None
        best_d2 = 10_000_000
        for b in self.birds:
            if b.state != "dead" or (not b.loot_ready):
                continue
            d2 = (b.x - m.x) ** 2 + (b.y - m.y) ** 2
            if d2 < best_d2:
                best_d2 = d2
                best = b
        if best is None or best_d2 > (20 ** 2):
            return False

        inv = self.shared_inv
        added1 = inv.add(items.FEATHER, 5)
        added2 = inv.add(items.POULTRY, 1)
        added3 = inv.add(items.BONE, 1)

        if added1 == 0 and added2 == 0 and added3 == 0:
            self.show_hint("Inventory full.")
            return True

        best.loot_ready = False
        try:
            self.birds.remove(best)
        except ValueError:
            pass
        self._play_bird_sfx(best, "bird_loot", 0.60)
        self.show_hint("Looted bird (+feathers, poultry, bone).")
        return True

    def _drop_coconuts_from_tree(self, idx: int) -> bool:
        m = self.monkeys[idx]
        if not m.climbing or m.climb_tree_idx is None:
            return False
        if m.climb_t < 0.92:
            self.show_hint("Climb higher to reach coconuts.")
            return True

        tr = self.world.trees[m.climb_tree_idx]
        count = 1 if random.random() < 0.75 else 2
        for _ in range(count):
            self._spawn_pickup(items.COCONUT, tr.x + random.randint(-8, 8), tr.y + random.randint(2, 8), qty=1)
        # Drop exactly 1 palm leaf after coconuts fall.
        self._spawn_leaf_after_coconut(tr)
        self.sfx.play("coconut_fall", 0.65)
        self.show_hint(f"Coconuts fell! ({count})")
        return True

    def _toggle_or_build_raft(self, idx: int) -> bool:
        """Interact-based raft logic.

        - If the selected hotbar item is a crafted raft: place it in shallow water.
        - Otherwise, if near an existing placed raft: board/dismount.
        """
        m = self.monkeys[idx]
        if m.climbing:
            return False

        # 1) Place raft from selected inventory item (crafted).
        if self._place_raft_from_selected(idx):
            return True

        # 2) Board / dismount a placed raft (nearest).
        nearest = self._nearest_raft(m.x, m.y, max_dist=26.0)
        if nearest is None:
            return False

        # If already on this raft -> try dismount.
        if m.on_raft and m.raft_uid == nearest.uid:
            return self._dismount_raft(idx, nearest)

        # Otherwise board if a seat is available and monkey is not in deep water.
        return self._board_raft(idx, nearest)

    def _raft_recipe(self) -> Dict[str, int]:
        """Returns the raft crafting recipe."""
        return {
            items.WOOD: 10,
            getattr(items, "PALM_LEAF", "palm_leaf"): 10,
            items.GRASS: 20,
            items.BONE: 5,
            getattr(items, "SEAWEED", "seaweed"): 10,
        }

    def _can_craft_raft(self) -> bool:
        req = self._raft_recipe()
        inv = self.shared_inv
        for iid, qty in req.items():
            if not inv.has(iid, qty):
                return False
        return True

    def _craft_raft(self) -> bool:
        """Craft 1 raft into the shared inventory, if materials are present.

        Safe to call even when requirements are not met (will not crash).
        """
        inv = self.shared_inv
        req = self._raft_recipe()

        if not self._can_craft_raft():
            return False

        for iid, qty in req.items():
            inv.remove(iid, qty)

        raft_id = getattr(items, "RAFT", "raft")
        added = inv.add(raft_id, 1)
        if added:
            self.show_hint("Crafted: Raft.", seconds=1.4)
            return True

        self.show_hint("Inventory full; could not add raft.", seconds=1.6)
        return False

    def _nearest_raft(self, x: float, y: float, max_dist: float = 24.0) -> Optional[Raft]:
        best = None
        best_d2 = (max_dist * max_dist)
        for rf in self.world.rafts:
            d2 = (rf.x - x) ** 2 + (rf.y - y) ** 2
            if d2 < best_d2:
                best_d2 = d2
                best = rf
        return best

    def _raft_seat_offsets(self) -> List[Tuple[int, int]]:
        # Two seats so both monkeys can ride.
        return [(-12, -6), (12, -6)]

    def _place_raft_from_selected(self, idx: int) -> bool:
        """If selected hotbar item is a raft, place it in shallow water."""
        m = self.monkeys[idx]
        inv = self.shared_inv
        sel = inv.selected_stack()
        raft_id = getattr(items, "RAFT", "raft")
        if (not sel) or sel.item_id != raft_id or sel.qty <= 0:
            return False

        # Must be standing in shallow water to place.
        if not self.world.is_shallow_water_at_px(m.x, m.y):
            self.show_hint("Place raft in shallow water (near shore).")
            return True

        # Snap to tile center.
        tx = int(m.x // TILE)
        ty = int(m.y // TILE)
        cx = tx * TILE + TILE // 2
        cy = ty * TILE + TILE // 2

        # Prevent stacking rafts.
        if self._nearest_raft(cx, cy, max_dist=42.0) is not None:
            self.show_hint("Too close to another raft.")
            return True

        # Validate area: raft footprint must be on water, and shallow at the center.
        w, h = 54, 30
        for px, py in (
            (cx - w // 2 + 2, cy - h // 2 + 2),
            (cx + w // 2 - 2, cy - h // 2 + 2),
            (cx - w // 2 + 2, cy + h // 2 - 2),
            (cx + w // 2 - 2, cy + h // 2 - 2),
            (cx, cy),
        ):
            if self.world.tile_at_px(px, py) != T_WATER:
                self.show_hint("Raft must be placed on water.")
                return True

        # Place raft.
        if not hasattr(self, "_raft_uid"):
            self._raft_uid = 1
        uid = int(self._raft_uid)
        self._raft_uid += 1

        self.world.rafts.append(Raft(uid=uid, x=float(cx), y=float(cy), w=w, h=h, occupants={}))

        inv.remove_from_selected(1)
        self.show_hint("Raft placed. Press E near it to board.", seconds=1.6)
        return True

    def _board_raft(self, idx: int, rf: Raft) -> bool:
        m = self.monkeys[idx]

        # Don't allow boarding from deep water (deep water is solid unless already on a raft).
        if self.world.is_deep_water_at_px(m.x, m.y) and (not m.on_raft):
            return False

        seats = self._raft_seat_offsets()
        taken = set(rf.occupants.values())
        seat = None
        for i in range(len(seats)):
            if i not in taken:
                seat = i
                break
        if seat is None:
            self.show_hint("Raft is full.")
            return True

        rf.occupants[idx] = seat
        m.on_raft = True
        m.raft_uid = rf.uid
        m.raft_seat = seat

        ox, oy = seats[seat]
        m.x = rf.x + ox
        m.y = rf.y + oy

        self.show_hint("Boarded raft.")
        return True

    def _find_land_near(self, cx: float, cy: float, max_r_tiles: int = 3) -> Optional[Tuple[float, float]]:
        """Find nearest non-water tile center near (cx, cy)."""
        tx0 = int(cx // TILE)
        ty0 = int(cy // TILE)
        best = None
        best_d2 = 10_000_000
        for r in range(1, max_r_tiles + 1):
            for oy in range(-r, r + 1):
                for ox in range(-r, r + 1):
                    tx = tx0 + ox
                    ty = ty0 + oy
                    if not (0 <= tx < self.world.tw and 0 <= ty < self.world.th):
                        continue
                    if self.world.tiles[ty][tx] == T_WATER:
                        continue
                    px = tx * TILE + TILE // 2
                    py = ty * TILE + TILE // 2
                    d2 = (px - cx) ** 2 + (py - cy) ** 2
                    if d2 < best_d2:
                        best_d2 = d2
                        best = (float(px), float(py))
            if best is not None:
                break
        return best

    def _dismount_raft(self, idx: int, rf: Raft) -> bool:
        m = self.monkeys[idx]
        land = self._find_land_near(rf.x, rf.y, max_r_tiles=3)
        if land is None:
            self.show_hint("No land nearby to dismount.")
            return True

        # Remove occupant assignment.
        if idx in rf.occupants:
            del rf.occupants[idx]

        m.on_raft = False
        m.raft_uid = None
        m.raft_seat = 0
        m.x, m.y = land[0], land[1]
        self.show_hint("Dismounted raft.")
        return True

    def _get_raft_by_uid(self, uid: int) -> Optional[Raft]:
        for rf in self.world.rafts:
            if rf.uid == uid:
                return rf
        return None

    def _sync_raft_occupants(self):
        """Keep raft riders positioned on their seats."""
        for m_idx, m in enumerate(self.monkeys):
            if not m.on_raft or m.raft_uid is None:
                continue
            rf = self._get_raft_by_uid(m.raft_uid)
            if rf is None:
                m.on_raft = False
                m.raft_uid = None
                m.raft_seat = 0
                continue
            seats = self._raft_seat_offsets()
            seat = rf.occupants.get(m_idx, m.raft_seat)
            seat = int(max(0, min(seat, len(seats) - 1)))
            ox, oy = seats[seat]
            m.x = rf.x + ox
            m.y = rf.y + oy

    def _raft_can_move_to(self, rf: Raft, nx: float, ny: float) -> bool:
        # Require raft footprint to stay over water.
        w, h = rf.w, rf.h
        for px, py in (
            (nx - w / 2 + 2, ny - h / 2 + 2),
            (nx + w / 2 - 2, ny - h / 2 + 2),
            (nx - w / 2 + 2, ny + h / 2 - 2),
            (nx + w / 2 - 2, ny + h / 2 - 2),
            (nx, ny),
        ):
            if self.world.tile_at_px(px, py) != T_WATER:
                return False
        return True

    def _control_raft(self, idx: int, dt: float, keys, up, down, left, right):
        """If this monkey is on a raft, update the raft position (only for active controlled monkey)."""
        m = self.monkeys[idx]
        if (not m.on_raft) or m.raft_uid is None:
            return
        rf = self._get_raft_by_uid(m.raft_uid)
        if rf is None:
            m.on_raft = False
            m.raft_uid = None
            return

        # Only the active (camera) monkey steers the raft.
        if idx != self.p1_idx:
            return

        dx = 0.0
        dy = 0.0
        if keys[left]:
            dx -= 1.0
        if keys[right]:
            dx += 1.0
        if keys[up]:
            dy -= 1.0
        if keys[down]:
            dy += 1.0

        mag = math.hypot(dx, dy)
        if mag < 1e-3:
            return

        dx /= mag
        dy /= mag

        spd = 72.0
        nx = rf.x + dx * spd * dt
        ny = rf.y + dy * spd * dt

        if self._raft_can_move_to(rf, nx, ny):
            rf.x = clamp(nx, 0, self.world.tw * TILE)
            rf.y = clamp(ny, 0, self.world.th * TILE)
    def _harvest_log(self, idx: int) -> bool:
        m = self.monkeys[idx]
        if m.climbing:
            return False
        li = self._nearest_log_index(m.x, m.y, max_dist=18.0)
        if li is None:
            return False
        lg = self.world.logs[li]

        day = self.day_index()
        if lg.last_harvest_day >= day:
            self.show_hint("This log is dry. Try again tomorrow.")
            return True

        lg.last_harvest_day = day
        added = self.shared_inv.add(items.WOOD, 1)
        self.show_hint("Harvested 1 wood." if added else "Inventory full.")
        return True

    def _pickup_ground_rock(self, idx: int) -> bool:
        m = self.monkeys[idx]
        if m.climbing:
            return False
        best_i = None
        best_d2 = 10_000_000
        for i, rk in enumerate(self.world.rocks):
            d2 = (rk.x - m.x) ** 2 + (rk.y - m.y) ** 2
            if d2 < best_d2:
                best_d2 = d2
                best_i = i
        if best_i is None:
            return False
        rk = self.world.rocks[best_i]
        if best_d2 > rk.pick_dist2():
            return False

        added = self.shared_inv.add(items.ROCK, 1)
        if added:
            self.world.rocks.pop(best_i)
            if idx == self.p1_idx:
                self.sfx.play("monkey_pickup", 0.45)
            self.show_hint("Picked up rock.")
        else:
            self.show_hint("Inventory full.")
        return True

    def _harvest_ground_tile(self, idx: int) -> bool:
        m = self.monkeys[idx]
        if m.climbing:
            return False

        t = self.world.tile_at_px(m.x, m.y)
        if t == T_SAND:
            added = self.shared_inv.add(items.SAND, 1)
            self.show_hint("Picked up sand." if added else "Inventory full.")
            return True
        if t == T_GRASS:
            added = self.shared_inv.add(items.GRASS, 1)
            if added:
                if random.randint(1, 5) == 1:
                    self.shared_inv.add(items.GRASS_SEEDS, 1)
                    self.show_hint("Picked grass (+seed).")
                else:
                    self.show_hint("Picked grass.")
            else:
                self.show_hint("Inventory full.")
            return True
        if t == T_DIRT:
            added = self.shared_inv.add(items.DIRT, 1)
            if not added:
                self.show_hint("Inventory full.")
                return True

            # Chance to find a worm in dirt.
            worm_found = (random.randint(1, 8) == 1)
            if worm_found:
                worm_added = self.shared_inv.add(getattr(items, "WORM", "worm"), 1)
                if worm_added:
                    self.show_hint("Picked up dirt (+worm).")
                else:
                    # Inventory full for worm stack/slot; don't lose dirt.
                    self.show_hint("Picked up dirt (worm wriggled away).")
                return True

            self.show_hint("Picked up dirt.")
            return True
        if t == T_GRAVEL:
            added = self.shared_inv.add(items.SOIL, 1)
            self.show_hint("Picked up soil." if added else "Inventory full.")
            return True
        return False

    def _try_catch_fish(self, idx: int) -> bool:
        m = self.monkeys[idx]
        if m.climbing:
            return False
        if not self.world.is_shallow_water_at_px(m.x, m.y):
            return False

        worm_id = getattr(items, "WORM", "worm")

        # If a worm is in inventory, guarantee a fish and consume 1 worm per fish caught.
        if self.shared_inv.count_item(worm_id) > 0:
            added = self.shared_inv.add(items.FISH, 1)
            if added:
                # Consume the worm only if the fish was successfully obtained.
                self.shared_inv.remove(worm_id, 1)
                self.show_hint(f"{m.name} caught a fish!", seconds=0.85)
            else:
                self.show_hint("Fish got away (inventory full).")
            return True

        # Otherwise: normal chance.
        if random.randint(1, 10) == 1:
            added = self.shared_inv.add(items.FISH, 1)
            if added:
                self.show_hint(f"{m.name} caught a fish!", seconds=0.85)
            else:
                self.show_hint("Fish got away (inventory full).")
            return True

        self.show_hint("No bite.")
        return True

    def _pickup_nearest_world_item(self, idx: int, allowed_ids: Optional[set] = None, max_dist: int = 22) -> bool:
        m = self.monkeys[idx]
        best_j = None
        best_d2 = 10_000_000
        mx, my = m.x, m.y
        for j, w in enumerate(self.world.pickups):
            if w.item_id == items.COCONUT:
                continue  # auto pickup on collision
            if allowed_ids is not None and w.item_id not in allowed_ids:
                continue
            d2 = (w.x - mx) ** 2 + (w.y - my) ** 2
            if d2 < best_d2:
                best_d2 = d2
                best_j = j
        if best_j is None or best_d2 > (max_dist ** 2):
            return False

        w = self.world.pickups[best_j]
        added = self.shared_inv.add(w.item_id, w.qty)
        if added >= w.qty:
            self.world.pickups.pop(best_j)
        else:
            w.qty -= added
        if added > 0:
            if idx == self.p1_idx:
                self.sfx.play("monkey_pickup", 0.45)
            nm = items.ITEMS[w.item_id].name if w.item_id in items.ITEMS else w.item_id
            self.show_hint(f"Picked up {nm}.")
        return added > 0

    def _consume_selected_if_fish(self, idx: int) -> bool:
        s = self.shared_inv.selected_stack()
        if not s or s.item_id != items.FISH:
            return False
        removed = self.shared_inv.remove_from_selected(1)
        if removed <= 0:
            return False
        self.shared_inv.add(items.BONE, 1)
        self.show_hint("Ate fish (+bone).")
        return True

    def _auto_pickup_coconuts(self, idx: int):
        m = self.monkeys[idx]
        r = m.rect().inflate(6, 6)
        picked_any = False
        for j in range(len(self.world.pickups) - 1, -1, -1):
            w = self.world.pickups[j]
            if w.item_id != items.COCONUT:
                continue
            if r.collidepoint(int(w.x), int(w.y)):
                added = self.shared_inv.add(items.COCONUT, w.qty)
                if added > 0:
                    picked_any = True
                if added >= w.qty:
                    self.world.pickups.pop(j)
                else:
                    w.qty -= added

        if picked_any:
            if idx == self.p1_idx:
                self.sfx.play("monkey_pickup", 0.35)

    def _interact(self, idx: int) -> bool:
        idx = self._sanitize_monkey_index(idx, self.p1_idx)
        m = self.monkeys[idx]
        if (m.x - self.anthill_x) ** 2 + (m.y - self.anthill_y) ** 2 <= (18.0 ** 2):
            return self._enter_anthill()
        # Loot dead bird first (per request: press E on dead bird)
        if self._loot_dead_bird(idx):
            return True

        if self._loot_dead_crab(idx):
            return True

        if self._loot_dead_iguana(idx):
            return True

        # Priority pickup: palm leaves / seaweed (so they are always obtainable when you press E)
        try:
            leaf_id = items.PALM_LEAF
        except Exception:
            leaf_id = "palm_leaf"
        try:
            seaweed_id = items.SEAWEED
        except Exception:
            seaweed_id = "seaweed"
        if self._pickup_nearest_world_item(idx, allowed_ids={leaf_id, seaweed_id}, max_dist=26):
            return True
        # Tree coconut drop
        if self._drop_coconuts_from_tree(idx):
            return True
        # Raft build/dismount
        if self._toggle_or_build_raft(idx):
            return True
        # Log harvest
        if self._harvest_log(idx):
            return True
        # Rocks
        if self._pickup_ground_rock(idx):
            return True
        # Ground resources
        if self._harvest_ground_tile(idx):
            return True
        # Fishing in shallow water
        if self._try_catch_fish(idx):
            return True
        # Floating pickups
        if self._pickup_nearest_world_item(idx):
            return True
        # Eat fish -> bone
        return self._consume_selected_if_fish(idx)

    # ---------
    # Rock throwing (mouse)
    # ---------
    def _try_throw_rock(self):
        inv = self.shared_inv
        sel = inv.selected_stack()
        if sel and sel.item_id == items.ROCK and sel.qty > 0:
            inv.remove_from_selected(1)
        else:
            found = False
            for i, slot in enumerate(inv.slots):
                if slot and slot.item_id == items.ROCK and slot.qty > 0:
                    inv.selected = i
                    inv.remove_from_selected(1)
                    found = True
                    break
            if not found:
                self.show_hint("No rocks to throw.")
                return

        internal_mouse = self._window_to_internal((self.mouse_x, self.mouse_y))
        if internal_mouse is None:
            internal_mouse = (INTERNAL_W // 2, INTERNAL_H // 2)
        mx, my = internal_mouse
        wx = self.cam_x + mx
        wy = self.cam_y + my

        m = self.monkeys[self.p1_idx]
        ox, oy = float(m.x), float(m.y - 2)
        dx = wx - ox
        dy = wy - oy
        mag = math.hypot(dx, dy)
        if mag < 1e-3:
            dx, dy = 1.0, 0.0
            mag = 1.0
        dx /= mag
        dy /= mag

        sp = 240.0
        self.projectiles.append(RockProjectile(ox, oy, dx * sp, dy * sp))
        self.sfx.play("monkey_throw", 0.55)

    def _update_projectiles(self, dt: float):
        for i in range(len(self.projectiles) - 1, -1, -1):
            p = self.projectiles[i]
            p.life -= dt
            p.x += p.vx * dt
            p.y += p.vy * dt
            if p.life <= 0.0:
                self.projectiles.pop(i)
                continue

            # hit birds
            hit = False
            for b in self.birds:
                if b.state == "dead":
                    continue
                if (b.x - p.x) ** 2 + (b.y - p.y) ** 2 < (8 ** 2):
                    b.hp -= 1
                    self._play_bird_sfx(b, "bird_hit", 0.55)
                    hit = True
                    if b.hp <= 0:
                        b.state = "dead"
                        b.vx = b.vy = 0.0
                        b.perch_tree_idx = None
                        b.loot_ready = True
                        self.show_hint("Bird down.")
                    break
            if hit:
                self.projectiles.pop(i)
                continue


            # hit crabs (one rock kills)
            hit = False
            for c in self.crabs:
                if c.state != "alive":
                    continue
                # simple circle hit
                if (c.x - p.x) * (c.x - p.x) + (c.y - p.y) * (c.y - p.y) <= (4.0 ** 2):
                    c.state = "dead"
                    c.vx = c.vy = 0.0
                    c.loot_ready = True
                    c.dead_until = self.time_s + CRAB_BODY_DESPAWN_SECONDS
                    c.target_x = c.target_y = 0.0
                    c.flee_t = 0.0
                    self._play_crab_sfx(c, "crab_hit", 0.45)
                    self.show_hint("Crab down.")
                    hit = True
                    break
            if hit:
                self.projectiles.pop(i)
                continue

            # hit iguanas (one rock kills)
            hit = False
            for g in self.iguanas:
                if g.state != "alive":
                    continue
                if (g.x - p.x) * (g.x - p.x) + (g.y - p.y) * (g.y - p.y) <= (6.0 ** 2):
                    g.state = "dead"
                    g.vx = g.vy = 0.0
                    g.loot_ready = True
                    g.dead_until = self.time_s + IGUANA_BODY_DESPAWN_SECONDS
                    g.target_x = g.target_y = 0.0
                    g.flee_t = 0.0
                    g.swim_t = 0.0
                    # optional sfx if present
                    try:
                        self.sfx.play("iguana_hit", 0.45)
                    except Exception:
                        pass
                    self.show_hint("Iguana down.")
                    hit = True
                    break
            if hit:
                self.projectiles.pop(i)
                continue


            # bounds cleanup
            if p.x < -40 or p.y < -40 or p.x > self.world.tw * TILE + 40 or p.y > self.world.th * TILE + 40:
                self.projectiles.pop(i)

    def _update_birds(self, dt: float):
        world_w = self.world.tw * TILE
        world_h = self.world.th * TILE

        self._bird_recenter_t -= dt
        if self._bird_recenter_t <= 0.0:
            self._bird_recenter_t = 3.0
            self._ensure_birds_near_player()

        for b in self.birds:
            if b.state == "dead":
                continue

            # occasional ambient calls
            if random.random() < 0.0018:
                if b.species == "seagull":
                    self._play_bird_sfx(b, "bird_seagull", 0.30)
                else:
                    self._play_bird_sfx(b, "bird_parrot", 0.30)

            if b.state == "land":
                b.perch_time -= dt
                if b.perch_time <= 0.0:
                    b.state = "fly"
                    b.perch_tree_idx = None
                    ang = random.random() * math.tau
                    sp = random.uniform(30, 46)
                    b.vx = math.cos(ang) * sp
                    b.vy = math.sin(ang) * sp
                    b.target_x = clamp(b.x + random.uniform(-80, 80), 0, world_w)
                    b.target_y = clamp(b.y + random.uniform(-80, 80), 0, world_h)
                else:
                    if b.perch_tree_idx is not None and 0 <= b.perch_tree_idx < len(self.world.trees):
                        tr = self.world.trees[b.perch_tree_idx]
                        b.x = tr.x + math.sin(self.time_s * 1.7 + b.x * 0.01) * 2.0
                        b.y = tr.top_y() + 2 + math.cos(self.time_s * 1.3 + b.y * 0.01) * 1.0
                continue

            # fly state: occasionally choose a tree to land on
            if random.random() < 0.0025 and len(self.world.trees) > 0:
                b.perch_tree_idx = random.randint(0, len(self.world.trees) - 1)
                tr = self.world.trees[b.perch_tree_idx]
                b.target_x = tr.x
                b.target_y = tr.top_y() + 2

            dx = b.target_x - b.x
            dy = b.target_y - b.y
            d = math.hypot(dx, dy)
            if d < 8.0:
                if b.perch_tree_idx is not None:
                    tr = self.world.trees[b.perch_tree_idx]
                    if abs(b.x - tr.x) < 10 and abs(b.y - (tr.top_y() + 2)) < 10:
                        b.state = "land"
                        b.perch_time = random.uniform(1.5, 4.5)
                        b.vx = b.vy = 0.0
                        continue
                b.target_x = clamp(b.x + random.uniform(-140, 140), 0, world_w)
                b.target_y = clamp(b.y + random.uniform(-120, 120), 0, world_h)

            if d > 1e-3:
                ax = dx / d
                ay = dy / d
            else:
                ax, ay = 0.0, 0.0

            spd = 52.0 if b.species == "seagull" else 60.0
            b.vx = lerp(b.vx, ax * spd, clamp(dt * 1.8, 0.0, 1.0))
            b.vy = lerp(b.vy, ay * spd, clamp(dt * 1.8, 0.0, 1.0))
            b.x += b.vx * dt
            b.y += b.vy * dt

            b.x = clamp(b.x, 0, world_w)
            b.y = clamp(b.y, 0, world_h)

    # ---------
    # Movement/collision
    # ---------

    # ---------
    # Crabs
    # ---------
    def _crab_alive_count(self) -> int:
        return sum(1 for c in self.crabs if c.state == "alive")

    def _player_near_shore(self, px: float, py: float, radius_tiles: int = 10) -> bool:
        tx = int(px // TILE)
        ty = int(py // TILE)
        for oy in range(-radius_tiles, radius_tiles + 1):
            yy = ty + oy
            if yy < 1 or yy >= self.world.th - 1:
                continue
            row = self.world.tiles[yy]
            for ox in range(-radius_tiles, radius_tiles + 1):
                xx = tx + ox
                if xx < 1 or xx >= self.world.tw - 1:
                    continue
                if row[xx] == T_WATER:
                    return True
        return False

    def _spawn_crab_at(self, px: float, py: float):
        # Warm randomized palette
        r = random.randint(170, 255)
        g = random.randint(60, 140)
        b = random.randint(25, 85)
        c0 = (r, g, b)
        c1 = (max(0, r - random.randint(40, 90)),
              max(0, g - random.randint(30, 70)),
              max(0, b - random.randint(15, 45)))
        self.crabs.append(Crab(x=float(px), y=float(py), vx=0.0, vy=0.0, color_a=c0, color_b=c1))

    def _find_beach_point_near(self, px: float, py: float, radius_px: float) -> Optional[Tuple[float, float]]:
        # Prefer sand tiles adjacent to water
        for _ in range(260):
            ang = random.random() * math.tau
            rr = random.random() * radius_px
            cx = px + math.cos(ang) * rr
            cy = py + math.sin(ang) * rr
            if cx < TILE or cy < TILE or cx > self.world.tw * TILE - TILE or cy > self.world.th * TILE - TILE:
                continue
            t = self.world.tile_at_px(cx, cy)
            if t != T_SAND:
                continue
            tx = int(cx // TILE)
            ty = int(cy // TILE)
            near_water = False
            for ox, oy in ((1,0),(-1,0),(0,1),(0,-1)):
                if self.world.tiles[ty + oy][tx + ox] == T_WATER:
                    near_water = True
                    break
            if not near_water:
                continue
            return (float(cx), float(cy))
        return None


    def _find_land_point_near(self, px: float, py: float, radius_px: float) -> Optional[Tuple[float, float]]:
        # Any non-water tile within radius (used for keeping parrots near the active area).
        world_w = self.world.tw * TILE
        world_h = self.world.th * TILE
        for _ in range(260):
            ang = random.random() * math.tau
            rr = random.random() * radius_px
            cx = px + math.cos(ang) * rr
            cy = py + math.sin(ang) * rr
            cx = clamp(cx, TILE, world_w - TILE)
            cy = clamp(cy, TILE, world_h - TILE)
            if self.world.tile_at_px(cx, cy) != T_WATER:
                return float(cx), float(cy)
        return None

    def _ensure_birds_near_player(self):
        # As the player travels between islands, the original birds can end up far away.
        # Periodically pull a few birds back near the active area so the world never feels empty.
        leader = self.monkeys[self.p1_idx]
        cx, cy = leader.x, leader.y

        # Count birds near the active monkey.
        near_r2 = (900.0 ** 2)
        near_sea = 0
        near_par = 0
        for b in self.birds:
            if b.state == "dead":
                continue
            d2 = (b.x - cx) ** 2 + (b.y - cy) ** 2
            if d2 <= near_r2:
                if b.species == "seagull":
                    near_sea += 1
                else:
                    near_par += 1

        need_sea = max(0, 5 - near_sea)
        need_par = max(0, 4 - near_par)
        if need_sea == 0 and need_par == 0:
            return

        # Helper: choose a good nearby perch for a parrot (prefer trees near the player).
        def pick_tree_perch_near() -> Optional[Tuple[float, float, Optional[int]]]:
            best = []
            for i, tr in enumerate(self.world.trees):
                d2 = (tr.x - cx) ** 2 + (tr.y - cy) ** 2
                if d2 <= (1100.0 ** 2):
                    best.append((d2, i, tr))
            if best:
                best.sort(key=lambda t: t[0])
                _, idx, tr = best[random.randint(0, min(8, len(best) - 1))]
                return float(tr.x), float(tr.top_y() + 2), idx
            pt = self._find_land_point_near(cx, cy, 900.0)
            if pt is None:
                return None
            return pt[0], pt[1] - random.uniform(18, 38), None

        # Choose farthest birds to "recycle" back near the player (keeps total count stable).
        def farthest_birds(species: str, k: int):
            cand = []
            for b in self.birds:
                if b.state == "dead" or b.species != species:
                    continue
                d2 = (b.x - cx) ** 2 + (b.y - cy) ** 2
                cand.append((d2, b))
            cand.sort(key=lambda t: t[0], reverse=True)
            return [b for _, b in cand[:k]]

        # Recenter seagulls near shore.
        if need_sea > 0:
            reuse = farthest_birds("seagull", need_sea)
            for b in reuse:
                pt = self._find_beach_point_near(cx, cy, 980.0)
                if pt is None:
                    break
                b.state = "fly"
                b.perch_tree_idx = None
                b.x, b.y = pt[0], pt[1] - random.uniform(20, 42)
                ang = random.random() * math.tau
                sp = random.uniform(22, 42)
                b.vx = math.cos(ang) * sp
                b.vy = math.sin(ang) * sp
                b.target_x, b.target_y = pt[0], pt[1]

        # Recenter parrots inland / near trees.
        if need_par > 0:
            reuse = farthest_birds("parrot", need_par)
            for b in reuse:
                perch = pick_tree_perch_near()
                if perch is None:
                    break
                tx, ty, tidx = perch
                b.state = "fly"
                b.perch_tree_idx = tidx
                b.x, b.y = tx, ty - random.uniform(18, 40)
                ang = random.random() * math.tau
                sp = random.uniform(26, 48)
                b.vx = math.cos(ang) * sp
                b.vy = math.sin(ang) * sp
                b.target_x, b.target_y = tx, ty

    def _ensure_iguana_near_player(self):
        # Make sure at least one iguana is present near the current island/shoreline.
        leader = self.monkeys[self.p1_idx]
        cx, cy = leader.x, leader.y
        if not self._player_near_shore(cx, cy):
            return

        near_r2 = (950.0 ** 2)
        for g in self.iguanas:
            if g.state == "alive":
                if (g.x - cx) ** 2 + (g.y - cy) ** 2 <= near_r2:
                    return  # already have one nearby

        pt = self._find_beach_point_near(cx, cy, 420.0)
        if pt is None:
            return

        # If we're at cap, recycle the farthest alive iguana; otherwise spawn a new one.
        alive = [g for g in self.iguanas if g.state == "alive"]
        if len(alive) < MAX_IGUANAS:
            self._spawn_iguana_at(pt[0], pt[1] - 6.0)
        else:
            # recycle farthest
            far = None
            far_d2 = -1.0
            for g in alive:
                d2 = (g.x - cx) ** 2 + (g.y - cy) ** 2
                if d2 > far_d2:
                    far_d2 = d2
                    far = g
            if far is not None:
                far.x, far.y = pt[0], pt[1] - 6.0
                far.vx = far.vy = 0.0
                far.wander_t = 0.0
                far.target_x = far.target_y = 0.0

    def _spawn_missing_crabs_near_player(self, force: bool = False):
        leader = self.monkeys[self.p1_idx]
        if not force:
            if not self._player_near_shore(leader.x, leader.y):
                return
        missing = MAX_CRABS - self._crab_alive_count()
        if missing <= 0:
            return

        # Only spawn if we're within range of where we can observe (prevents hidden accumulation).
        # (Beach proximity is already enforced above unless force=True.)
        for _ in range(missing):
            pt = self._find_beach_point_near(leader.x, leader.y, CRAB_SHORE_RESPAWN_RANGE)
            if pt is None:
                break
            self._spawn_crab_at(pt[0], pt[1])

    def _spawn_initial_crabs(self):
        # Spawn near the starting area so the island feels alive immediately.
        self._spawn_missing_crabs_near_player(force=True)


    # ---------
    # Iguana
    # ---------
    def _iguana_alive_count(self) -> int:
        return sum(1 for g in self.iguanas if g.state == "alive")

    def _spawn_iguana_at(self, px: float, py: float):
        # Cute green palette with slight random variation
        r = random.randint(60, 120)
        g = random.randint(150, 220)
        b = random.randint(60, 120)
        body = (r, g, b)
        belly = (min(235, r + 80), min(235, g + 40), min(235, b + 80))
        self.iguanas.append(Iguana(x=float(px), y=float(py), vx=0.0, vy=0.0, color_body=body, color_belly=belly))

    def _spawn_missing_iguana_near_player(self, force: bool = False):
        # Keep 1 iguana per island. Only respawn when the player is near shore (unless forced).
        leader = self.monkeys[self.p1_idx]
        if not force:
            if not self._player_near_shore(leader.x, leader.y):
                return
        missing = MAX_IGUANAS - self._iguana_alive_count()
        if missing <= 0:
            return
        for _ in range(missing):
            pt = self._find_beach_point_near(leader.x, leader.y, IGUANA_SHORE_RESPAWN_RANGE)
            if pt is None:
                break
            # Iguana can spawn slightly inland too: nudge away from immediate water edge if possible.
            self._spawn_iguana_at(pt[0], pt[1] - 6.0)

    def _spawn_initial_iguana(self):
        self._spawn_missing_iguana_near_player(force=True)

    def _play_iguana_sfx(self, g: Iguana, key: str, base_volume: float):
        if not self._is_on_screen_world(g.x, g.y):
            return
        vol = self._spatial_volume(g.x, g.y, base_volume=base_volume, max_dist=260.0)
        if vol > 0.001:
            self.sfx.play(key, vol)

    def _update_iguanas(self, dt: float):
        leader = self.monkeys[self.p1_idx]

        self._iguana_recenter_t -= dt
        if self._iguana_recenter_t <= 0.0:
            self._iguana_recenter_t = 8.0
            self._ensure_iguana_near_player()
        for i in range(len(self.iguanas) - 1, -1, -1):
            g = self.iguanas[i]

            if g.state == "dead":
                if self.time_s >= g.dead_until:
                    self.iguanas.pop(i)
                continue

            # Spot player
            d2 = (g.x - leader.x) ** 2 + (g.y - leader.y) ** 2
            spotted = d2 <= (IGUANA_FLEE_RANGE ** 2)
            if spotted:
                g.flee_t = 1.6
                g.swim_t = 2.2

            # Pick a wander target occasionally
            g.wander_t -= dt
            if g.wander_t <= 0.0 or (g.target_x == 0.0 and g.target_y == 0.0):
                g.wander_t = random.uniform(1.0, 2.3)
                # random point nearby on land (sand/grass/dirt)
                for _ in range(80):
                    ang = random.random() * math.tau
                    rr = random.random() * 90.0
                    tx = g.x + math.cos(ang) * rr
                    ty = g.y + math.sin(ang) * rr
                    t = self.world.tile_at_px(tx, ty)
                    if t in (T_SAND, T_GRASS, T_DIRT):
                        g.target_x, g.target_y = tx, ty
                        break

            # Determine target direction
            target = (g.target_x, g.target_y)
            if g.flee_t > 0.0:
                g.flee_t = max(0.0, g.flee_t - dt)
                # Flee to nearest water
                nw = self._nearest_water_target(g.x, g.y, max_tiles=22)
                if nw is not None:
                    target = nw

            to_dx = target[0] - g.x
            to_dy = target[1] - g.y
            d = math.hypot(to_dx, to_dy)
            if d > 0.001:
                to_dx /= d
                to_dy /= d
            else:
                to_dx = to_dy = 0.0

            in_water = (self.world.tile_at_px(g.x, g.y) == T_WATER)
            speed = IGUANA_WANDER_SPEED if g.flee_t <= 0.0 else IGUANA_FLEE_SPEED

            # Swim jitter when chased
            if in_water and g.swim_t > 0.0:
                g.swim_t = max(0.0, g.swim_t - dt)
                to_dx += math.sin(self.time_s * 6.0 + g.x * 0.01) * 0.35
                to_dy += math.cos(self.time_s * 5.0 + g.y * 0.01) * 0.35
                nd = math.hypot(to_dx, to_dy)
                if nd > 0.001:
                    to_dx /= nd
                    to_dy /= nd
                g.vx = g.vx * IGUANA_WATER_DRIFT + to_dx * speed * 0.35
                g.vy = g.vy * IGUANA_WATER_DRIFT + to_dy * speed * 0.35
            else:
                g.vx = g.vx * IGUANA_LAND_DRAG + to_dx * speed * 0.55
                g.vy = g.vy * IGUANA_LAND_DRAG + to_dy * speed * 0.55

            # Move
            g.x += g.vx * dt
            g.y += g.vy * dt

            g.x = max(TILE, min(self.world.tw * TILE - TILE, g.x))
            g.y = max(TILE, min(self.world.th * TILE - TILE, g.y))

            # occasional tiny scurry sound on sand
            g.sfx_t -= dt
            if g.sfx_t <= 0.0:
                if self.world.tile_at_px(g.x, g.y) in (T_SAND, T_GRASS) and (abs(g.vx) + abs(g.vy)) > 20.0:
                    self._play_iguana_sfx(g, "iguana_scurry", 0.20)
                g.sfx_t = random.uniform(1.0, 2.4)

    def _ensure_reptile_meat_item(self) -> str:
        item_id = getattr(items, "REPTILE_MEAT", "reptile_meat")
        try:
            if hasattr(items, "ItemDef") and hasattr(items, "ITEMS"):
                if item_id not in items.ITEMS:
                    items.ITEMS[item_id] = items.ItemDef(item_id, "Reptile Meat", 20, ((130, 84, 80), (95, 56, 54), (235, 245, 250)))
        except Exception:
            pass
        return item_id

    def _loot_dead_iguana(self, idx: int) -> bool:
        m = self.monkeys[idx]
        best_i = None
        best_d2 = 10_000_000
        for i, g in enumerate(self.iguanas):
            if g.state != "dead" or not g.loot_ready:
                continue
            d2 = (g.x - m.x) ** 2 + (g.y - m.y) ** 2
            if d2 < best_d2:
                best_d2 = d2
                best_i = i
        if best_i is None or best_d2 > (26.0 ** 2):
            return False

        bone_id = getattr(items, "BONE", "bone")
        meat_id = self._ensure_reptile_meat_item()

        added_bone = self.shared_inv.add(bone_id, 1)
        added_meat = self.shared_inv.add(meat_id, 1)
        if added_bone > 0 or added_meat > 0:
            try:
                if idx == self.p1_idx:
                    self.sfx.play("iguana_loot", 0.45)
            except Exception:
                pass
            self.show_hint("+1 Bone, +1 Reptile Meat")

        try:
            self.iguanas.pop(best_i)
        except Exception:
            pass
        return True

    def _on_new_day(self):
        # Once per day, top up living crab population near the beach, but only if we are nearby.
        self._spawn_missing_crabs_near_player(force=False)
        # Once per day, ensure there is 1 iguana, but only if we are near the shore.
        self._spawn_missing_iguana_near_player(force=False)

    def _nearest_water_target(self, cx: float, cy: float, max_tiles: int = 22) -> Optional[Tuple[float, float]]:
        tx = int(cx // TILE)
        ty = int(cy // TILE)
        best = None
        best_d2 = 10_000_000
        for oy in range(-max_tiles, max_tiles + 1):
            yy = ty + oy
            if yy < 1 or yy >= self.world.th - 1:
                continue
            row = self.world.tiles[yy]
            for ox in range(-max_tiles, max_tiles + 1):
                xx = tx + ox
                if xx < 1 or xx >= self.world.tw - 1:
                    continue
                if row[xx] != T_WATER:
                    continue
                px = xx * TILE + TILE * 0.5
                py = yy * TILE + TILE * 0.5
                d2 = (px - cx) ** 2 + (py - cy) ** 2
                if d2 < best_d2:
                    best_d2 = d2
                    best = (px, py)
        return best

    def _play_crab_sfx(self, crab: Crab, key: str, base_volume: float):
        if not self._is_on_screen_world(crab.x, crab.y):
            return
        vol = self._spatial_volume(crab.x, crab.y, base_volume=base_volume, max_dist=240.0)
        if vol > 0.001:
            self.sfx.play(key, vol)

    def _update_crabs(self, dt: float):
        leader = self.monkeys[self.p1_idx]

        for i in range(len(self.crabs) - 1, -1, -1):
            c = self.crabs[i]

            if c.state == "dead":
                # despawn corpse after timeout if not looted
                if self.time_s >= c.dead_until:
                    self.crabs.pop(i)
                continue

            # Flee logic
            dx = c.x - leader.x
            dy = c.y - leader.y
            d2 = dx * dx + dy * dy
            if d2 < (CRAB_FLEE_RANGE * CRAB_FLEE_RANGE):
                c.flee_t = 1.0  # refresh flee state
                if c.target_x == 0.0 and c.target_y == 0.0 or random.random() < 0.08:
                    wt = self._nearest_water_target(c.x, c.y, max_tiles=20)
                    if wt is not None:
                        c.target_x, c.target_y = wt
                    else:
                        # fallback: run directly away
                        c.target_x = c.x + dx
                        c.target_y = c.y + dy

            if c.flee_t > 0.0:
                c.flee_t = max(0.0, c.flee_t - dt)
                tx = c.target_x
                ty = c.target_y
                if tx == 0.0 and ty == 0.0:
                    tx, ty = c.x + dx, c.y + dy
                vx = tx - c.x
                vy = ty - c.y
                ll = math.hypot(vx, vy)
                if ll > 0.001:
                    vx /= ll
                    vy /= ll
                c.vx = vx * CRAB_FLEE_SPEED
                c.vy = vy * CRAB_FLEE_SPEED
            else:
                # Wander on sand
                c.wander_t -= dt
                if c.wander_t <= 0.0 or ((c.x - c.target_x) ** 2 + (c.y - c.target_y) ** 2) < (8.0 ** 2):
                    # choose new sand target near current position
                    c.wander_t = random.uniform(0.7, 1.8)
                    chosen = None
                    for _ in range(60):
                        ox = random.uniform(-70, 70)
                        oy = random.uniform(-55, 55)
                        nx = c.x + ox
                        ny = c.y + oy
                        if nx < TILE or ny < TILE or nx > self.world.tw * TILE - TILE or ny > self.world.th * TILE - TILE:
                            continue
                        if self.world.tile_at_px(nx, ny) == T_SAND:
                            chosen = (nx, ny)
                            break
                    if chosen is None:
                        # fallback: try pull towards nearest beach around leader
                        pt = self._find_beach_point_near(leader.x, leader.y, CRAB_SHORE_RESPAWN_RANGE)
                        if pt:
                            chosen = pt
                        else:
                            chosen = (c.x, c.y)
                    c.target_x, c.target_y = chosen

                vx = c.target_x - c.x
                vy = c.target_y - c.y
                ll = math.hypot(vx, vy)
                if ll > 0.001:
                    vx /= ll
                    vy /= ll
                c.vx = vx * CRAB_WANDER_SPEED
                c.vy = vy * CRAB_WANDER_SPEED

                # If crab wandered off sand, bias back to sand
                if self.world.tile_at_px(c.x, c.y) not in (T_SAND, T_WATER):
                    pt = self._find_beach_point_near(c.x, c.y, 140.0)
                    if pt:
                        c.target_x, c.target_y = pt

            # integrate
            c.x += c.vx * dt
            c.y += c.vy * dt
            c.x = max(2.0, min(self.world.tw * TILE - 2.0, c.x))
            c.y = max(2.0, min(self.world.th * TILE - 2.0, c.y))

            # occasional scuttle sound when moving on sand
            c.sfx_t -= dt
            if c.sfx_t <= 0.0:
                if self.world.tile_at_px(c.x, c.y) == T_SAND and (abs(c.vx) + abs(c.vy)) > 10.0:
                    self._play_crab_sfx(c, "crab_scuttle", 0.20)
                c.sfx_t = random.uniform(1.2, 2.6)

    def _loot_dead_crab(self, idx: int) -> bool:
        m = self.monkeys[idx]
        best_i = None
        best_d2 = 10_000_000
        for i, c in enumerate(self.crabs):
            if c.state != "dead" or not c.loot_ready:
                continue
            d2 = (c.x - m.x) ** 2 + (c.y - m.y) ** 2
            if d2 < best_d2:
                best_d2 = d2
                best_i = i
        if best_i is None or best_d2 > (22.0 ** 2):
            return False

        try:
            meat_id = items.CRAB_MEAT
        except Exception:
            meat_id = "crab_meat"

        added = self.shared_inv.add(meat_id, 1)
        if added > 0:
            if idx == self.p1_idx:
                self.sfx.play("crab_loot", 0.45)
            self.show_hint("+1 Crab Meat")
        # remove crab once looted
        try:
            self.crabs.pop(best_i)
        except Exception:
            pass
        return True

    def _update(self, dt: float):
        self._normalize_monkey_indices()
        self._anthill_cooldown = max(0.0, getattr(self, "_anthill_cooldown", 0.0) - dt)
        keys = pygame.key.get_pressed()

        # Daily tick (used for respawns like crabs)
        day_now = self.day_index()
        if day_now != getattr(self, "_day_seen", day_now):
            self._day_seen = day_now
            self._on_new_day()

        self._hint_t = max(0.0, self._hint_t - dt)
        self._step_t = max(0.0, self._step_t - dt)

        i_now = bool(keys[pygame.K_i])
        if i_now and not self._prev_i:
            self.show_inv = not self.show_inv
            self.sfx.play("ui_toggle", 0.45)
        self._prev_i = i_now

        # Crafting (inventory): press C to craft a raft (only when requirements are met).
        c_now = bool(keys[pygame.K_c])
        if self.show_inv and c_now and (not self._prev_c):
            if self._can_craft_raft():
                if self._craft_raft():
                    self.sfx.play("ui_click", 0.40)
        self._prev_c = c_now

# When inventory is open, disable world controls (movement, climb, interact, throwing).
        if not self.show_inv:
            space_now = bool(keys[pygame.K_SPACE])
            rctrl_now = bool(keys[pygame.K_RCTRL])
            # Jump (SPACE). Climbing is only entered when a jumping monkey touches a tree.
            if space_now and not self._prev_space:
                self.sfx.play("monkey_step", 0.25)
                self._try_jump(self.p1_idx, boost=1.0)
            # Optional: 2nd monkey jump on RCTRL when not in follow mode.
            if rctrl_now and not self._prev_rctrl:
                if not self.follow_enabled:
                    self.sfx.play("monkey_step", 0.25)
                    self._try_jump(self.p2_idx, boost=1.0)
            self._prev_space = space_now
            self._prev_rctrl = rctrl_now

            e_now = bool(keys[pygame.K_e])
            rshift_now = bool(keys[pygame.K_RSHIFT])

            if e_now and not self._prev_e:
                self.sfx.play("monkey_interact", 0.40)
                self._interact(self.p1_idx)
            if rshift_now and not self._prev_rshift:
                # Don't play grab/interact SFX for the non-controlled monkey (AI can be noisy).
                self._interact(self.p2_idx)

            self._prev_e = e_now
            self._prev_rshift = rshift_now
        else:
            # Keep edge state updated so actions don't trigger immediately when closing inventory.
            self._prev_space = bool(keys[pygame.K_SPACE])
            self._prev_rctrl = bool(keys[pygame.K_RCTRL])
            self._prev_e = bool(keys[pygame.K_e])
            self._prev_rshift = bool(keys[pygame.K_RSHIFT])

        # Number keys select within current hotbar page
        inv = self.shared_inv
        page0 = (inv.selected // 12) * 12
        for k in range(pygame.K_1, pygame.K_9 + 1):
            if keys[k]:
                inv.selected = clamp(page0 + (k - pygame.K_1), 0, inv.max_slots - 1)

        if not self.show_inv:
            self._update_jump_physics(dt)
            # Player control
            self._move_monkey(self.p1_idx, dt, keys, up=pygame.K_w, down=pygame.K_s, left=pygame.K_a, right=pygame.K_d, invert_climb=True)

            # Companion control: either manual (arrows) or follow mode (F).
            if self.follow_enabled:
                self._follow_record_leader(dt)
                self._update_follow_ai(dt)
            elif self.gather_enabled:
                self._update_gather_ai(dt)
            else:
                self._move_monkey(self.p2_idx, dt, keys, up=pygame.K_UP, down=pygame.K_DOWN, left=pygame.K_LEFT, right=pygame.K_RIGHT, invert_climb=True)

            self._auto_pickup_coconuts(self.p1_idx)
            self._auto_pickup_coconuts(self.p2_idx)

        # Keep raft riders anchored each frame.
        self._sync_raft_occupants()

        self._update_projectiles(dt)
        self._update_birds(dt)
        self._update_crabs(dt)
        self._update_iguanas(dt)
        self._update_pickup_physics(dt)
        self._maybe_wash_up_seaweed(dt)

        self._pickup_cleanup_t += dt
        if self._pickup_cleanup_t >= 1.0:
            self._pickup_cleanup_t = 0.0
            self._cleanup_timed_pickups()


        target = self.monkeys[self.p1_idx]
        desired_x = target.x - INTERNAL_W / 2
        desired_y = target.y - INTERNAL_H / 2
        self.cam_x += (desired_x - self.cam_x) * clamp(dt * 6.0, 0.0, 1.0)
        self.cam_y += (desired_y - self.cam_y) * clamp(dt * 6.0, 0.0, 1.0)

        max_x = self.world.tw * TILE - INTERNAL_W
        max_y = self.world.th * TILE - INTERNAL_H
        self.cam_x = clamp(self.cam_x, 0, max_x)
        self.cam_y = clamp(self.cam_y, 0, max_y)

        # Ocean ambience: fade in near water (update at a lower rate for performance)
        if not self.show_inv:
            self._ocean_scan_t -= dt
            if self._ocean_scan_t <= 0.0:
                self._ocean_scan_t = 0.15  # ~6-7 Hz
                cm = self.monkeys[self.p1_idx]
                try:
                    self._ocean_vol = float(self._ocean_volume_near(cm.x, cm.y))
                except Exception:
                    self._ocean_vol = 0.0
            self.sfx.ocean_set(self._ocean_vol)
        else:
            self.sfx.ocean_set(0.0)

        self._snapshot_state("UPDATE")

    def _move_monkey(self, idx: int, dt: float, keys, up, down, left, right, invert_climb: bool):
        m = self.monkeys[idx]
        if m.climbing and m.climb_tree_idx is not None:
            tr = self.world.trees[m.climb_tree_idx]

            # Detach from tree with left/right (a small hop away).
            if keys[left] or keys[right]:
                dirx = -1 if keys[left] else 1
                m.climbing = False
                m.climb_tree_idx = None
                m.climb_t = 0.0
                m.no_climb_until = self.time_s + 0.25
                m.jumping = True
                m.jump_z = 0.0
                m.jump_vz = JUMP_V0 * 0.55
                m.x = tr.x + dirx * 14
                # continue into normal movement this frame
            else:
                dy = 0
                if keys[up]:
                    dy -= 1
                if keys[down]:
                    dy += 1
                if invert_climb:
                    dy = -dy
                m.climb_t = clamp(m.climb_t + dy * dt * 0.55, 0.0, 1.0)
                m.x = tr.x
                m.y = lerp(tr.y - 2, tr.top_y() + 6, m.climb_t)
                return

        # If riding a placed raft, steer the raft (active monkey) and stay seated.
        if m.on_raft and (m.raft_uid is not None):
            self._control_raft(idx, dt, keys, up, down, left, right)
            return

        dx = 0
        dy = 0
        if keys[left]:
            dx -= 1
        if keys[right]:
            dx += 1
        if keys[up]:
            dy -= 1
        if keys[down]:
            dy += 1

        if dx != 0 or dy != 0:
            mag = math.hypot(dx, dy)
            dx /= mag
            dy /= mag
            if (not self.show_inv) and self._step_t <= 0.0 and (not m.on_raft):
                self.sfx.play("monkey_step", 0.18)
                self._step_t = 0.22

        spd = m.speed
        if self.world.tile_at_px(m.x, m.y) == T_SAND:
            spd *= 0.88

        nx = m.x + dx * spd * dt
        ny = m.y + dy * spd * dt
        nx, ny = self._collide(m, nx, ny)
        m.x, m.y = nx, ny

        # Only start climbing while jumping: touch a tree mid-jump to grab it.
        if m.jumping and (self.time_s >= getattr(m, 'no_climb_until', 0.0)):
            tree_i = self.world.nearest_tree_for_climb(m.rect())
            if tree_i is not None:
                tr = self.world.trees[tree_i]
                bottom = tr.y - 2
                top = tr.top_y() + 6
                den = (top - bottom)
                t = 0.0 if abs(den) < 0.001 else (m.y - bottom) / den
                m.climbing = True
                m.climb_tree_idx = tree_i
                m.climb_t = clamp(t, 0.0, 1.0)
                m.x = tr.x
                m.y = lerp(bottom, top, m.climb_t)
                m.jumping = False
                m.jump_z = 0.0
                m.jump_vz = 0.0

    def _move_monkey_ai(self, idx: int, dt: float, target_x: float, target_y: float, spd_mult: float = 1.0):
        """Simple steering toward a target point (used for follow mode)."""
        m = self.monkeys[idx]
        if m.climbing:
            return

        dx = float(target_x) - m.x
        dy = float(target_y) - m.y
        mag = math.hypot(dx, dy)
        if mag < 1e-3:
            return
        dx /= mag
        dy /= mag

        spd = m.speed * 0.95 * float(spd_mult)
        if self.world.tile_at_px(m.x, m.y) == T_SAND:
            spd *= 0.88

        nx = m.x + dx * spd * dt
        ny = m.y + dy * spd * dt
        nx, ny = self._collide(m, nx, ny)
        m.x, m.y = nx, ny

    def _collide(self, m: Monkey, nx: float, ny: float) -> Tuple[float, float]:
        r = m.rect()
        r.x = int(nx) - 3
        if self._rect_hits_solid(m, r):
            step = -1 if nx > m.x else 1
            for _ in range(12):
                nx += step * 0.5
                r.x = int(nx) - 3
                if not self._rect_hits_solid(m, r):
                    break

        r = m.rect()
        r.y = int(ny) - 2
        if self._rect_hits_solid(m, r):
            step = -1 if ny > m.y else 1
            for _ in range(12):
                ny += step * 0.5
                r.y = int(ny) - 2
                if not self._rect_hits_solid(m, r):
                    break
        return nx, ny

    def _rect_hits_solid(self, m: Monkey, r: pygame.Rect) -> bool:
        pts = [
            (r.left, r.top),
            (r.right, r.top),
            (r.left, r.bottom),
            (r.right, r.bottom),
            (r.centerx, r.centery),
        ]
        for (px, py) in pts:
            if self.world.is_solid_at_px(px, py, on_raft=m.on_raft):
                return True        # Tree base collider only (spatially indexed)
        for i in self.world.tree_indices_near_rect(r):
            tr = self.world.trees[i]
            if tr.base_rect.colliderect(r):
                if not (m.climbing and m.climb_tree_idx == i):
                    return True
        return False

    # ---------
    # Drawing
    # ---------
    def _draw(self):
        self.screen.fill((0, 0, 0))

        camx = int(self.cam_x)
        camy = int(self.cam_y)

        tx0 = max(0, camx // TILE - 2)
        ty0 = max(0, camy // TILE - 2)
        tx1 = min(self.world.tw, (camx + INTERNAL_W) // TILE + 3)
        ty1 = min(self.world.th, (camy + INTERNAL_H) // TILE + 3)

        # Fast terrain rendering: blit pre-rendered world surface (tiles + micro details).
        if getattr(self.world, "base_surface", None) is not None:
            self.screen.blit(self.world.base_surface, (0, 0), area=pygame.Rect(camx, camy, INTERNAL_W, INTERNAL_H))
        else:
            # Fallback: direct tile draws (no micro-details).
            for ty in range(ty0, ty1):
                row = self.world.tiles[ty]
                tone_row = self.world.tone[ty]
                for tx in range(tx0, tx1):
                    t = row[tx]
                    tone = tone_row[tx]
                    col = tile_color(t, tone, tx, ty)
                    sx = tx * TILE - camx
                    sy = ty * TILE - camy
                    pygame.draw.rect(self.screen, col, pygame.Rect(sx, sy, TILE, TILE))

        # Shore foam: cached on a larger surface and sampled with an offset so it stays world-locked.
        foam_w, foam_h = self._foam_surf.get_size()
        margin = int(getattr(self, "_foam_margin", TILE * 4))

        need_refresh = False
        if getattr(self, "_foam_anchor_camx", -999999) < -100000:
            need_refresh = True
        if (self.time_s - self._foam_last_update) >= 0.09:
            need_refresh = True

        if not need_refresh:
            offx = camx - int(self._foam_anchor_camx)
            offy = camy - int(self._foam_anchor_camy)
            pad = TILE * 2
            if offx < pad or offy < pad or offx + INTERNAL_W > foam_w - pad or offy + INTERNAL_H > foam_h - pad:
                need_refresh = True

        if need_refresh:
            self._foam_anchor_camx = int(camx - margin)
            self._foam_anchor_camy = int(camy - margin)
            self._foam_surf.fill((0, 0, 0, 0))

            fcamx = int(self._foam_anchor_camx)
            fcamy = int(self._foam_anchor_camy)
            ftx0 = max(0, fcamx // TILE - 2)
            fty0 = max(0, fcamy // TILE - 2)
            ftx1 = min(self.world.tw, (fcamx + foam_w) // TILE + 3)
            fty1 = min(self.world.th, (fcamy + foam_h) // TILE + 3)

            self._draw_shore_foam(ftx0, fty0, ftx1, fty1, fcamx, fcamy, dest=self._foam_surf)
            self._foam_last_update = self.time_s

        offx = camx - int(self._foam_anchor_camx)
        offy = camy - int(self._foam_anchor_camy)
        self.screen.blit(self._foam_surf, (0, 0), area=pygame.Rect(int(offx), int(offy), INTERNAL_W, INTERNAL_H))


        draw_list = []

        for v in self.world.veg:
            sx = v.x - camx
            sy = v.y - camy
            if -40 <= sx <= INTERNAL_W + 40 and -40 <= sy <= INTERNAL_H + 40:
                draw_list.append(("veg", v.sort_y, v, int(sx), int(sy)))

        for rk in self.world.rocks:
            sx = rk.x - camx
            sy = rk.y - camy
            if -40 <= sx <= INTERNAL_W + 40 and -40 <= sy <= INTERNAL_H + 40:
                draw_list.append(("rock", rk.sort_y, rk, int(sx), int(sy)))

        for lg in self.world.logs:
            sx = lg.x - camx
            sy = lg.y - camy
            if -40 <= sx <= INTERNAL_W + 40 and -40 <= sy <= INTERNAL_H + 40:
                draw_list.append(("log", lg.sort_y, lg, int(sx), int(sy)))

        for rf in self.world.rafts:
            sx = rf.x - camx
            sy = rf.y - camy
            if -80 <= sx <= INTERNAL_W + 80 and -60 <= sy <= INTERNAL_H + 60:
                draw_list.append(("raft", rf.sort_y - 1, rf, int(sx), int(sy)))

        for w in self.world.pickups:
            sx = w.x - camx
            sy = w.y - camy
            if -30 <= sx <= INTERNAL_W + 30 and -30 <= sy <= INTERNAL_H + 30:
                draw_list.append(("pickup", int(w.y), w, int(sx), int(sy)))

        for b in self.birds:
            sx = b.x - camx
            sy = b.y - camy
            if -60 <= sx <= INTERNAL_W + 60 and -60 <= sy <= INTERNAL_H + 60:
                draw_list.append(("bird", b.sort_y, b, int(sx), int(sy)))

        for c in self.crabs:
            sx = c.x - camx
            sy = c.y - camy
            if -40 <= sx <= INTERNAL_W + 40 and -40 <= sy <= INTERNAL_H + 40:
                draw_list.append(("crab", c.sort_y, c, int(sx), int(sy)))

        for g in self.iguanas:
            sx = g.x - camx
            sy = g.y - camy
            if -60 <= sx <= INTERNAL_W + 60 and -60 <= sy <= INTERNAL_H + 60:
                draw_list.append(("iguana", g.sort_y, g, int(sx), int(sy)))


        for p in self.projectiles:
            sx = p.x - camx
            sy = p.y - camy
            if -20 <= sx <= INTERNAL_W + 20 and -20 <= sy <= INTERNAL_H + 20:
                draw_list.append(("proj", int(p.y), p, int(sx), int(sy)))

        for i, tr in enumerate(self.world.trees):
            sx = tr.x - camx
            sy = tr.y - camy
            if -60 <= sx <= INTERNAL_W + 60 and -120 <= sy <= INTERNAL_H + 80:
                draw_list.append(("tree", tr.y, i, int(sx), int(sy)))

        anthill_sx = int(self.anthill_x - camx)
        anthill_sy = int(self.anthill_y - camy)
        if -40 <= anthill_sx <= INTERNAL_W + 40 and -40 <= anthill_sy <= INTERNAL_H + 40:
            draw_list.append(("anthill", int(self.anthill_y), None, anthill_sx, anthill_sy))

        for i, m in enumerate(self.monkeys):
            sx = int(m.x - camx)
            sy = int(m.y - camy)
            draw_list.append(("monkey", int(m.y), i, sx, sy))

        draw_list.sort(key=lambda it: it[1])

        for kind, _, payload, sx, sy in draw_list:
            if kind == "veg":
                draw_veg(self.screen, sx, sy, payload.kind, self.time_s)
            elif kind == "rock":
                draw_rocknode(self.screen, sx, sy, payload.size)
            elif kind == "log":
                draw_log(self.screen, sx, sy)
            elif kind == "raft":
                draw_raft(self.screen, sx, sy, payload.w, payload.h)
            elif kind == "pickup":
                draw_pickup(self.screen, sx, sy, payload, self.time_s)
            elif kind == "proj":
                pygame.draw.circle(self.screen, (30, 30, 32), (sx, sy), 2)
                pygame.draw.circle(self.screen, (140, 142, 150), (sx, sy), 1)
            elif kind == "crab":
                c = payload
                if c.state == "dead":
                    body = (max(0, c.color_a[0] - 70), max(0, c.color_a[1] - 70), max(0, c.color_a[2] - 70))
                    pygame.draw.circle(self.screen, body, (sx, sy), 2)
                    # little X eyes
                    pygame.draw.line(self.screen, (30, 40, 60), (sx-1, sy-1), (sx, sy))
                    pygame.draw.line(self.screen, (30, 40, 60), (sx, sy-1), (sx-1, sy))
                else:
                    body = c.color_a
                    shade = c.color_b
                    # body
                    pygame.draw.circle(self.screen, body, (sx, sy), 2)
                    pygame.draw.circle(self.screen, shade, (sx, sy+1), 2, 1)
                    # claws
                    pygame.draw.circle(self.screen, body, (sx-3, sy), 1)
                    pygame.draw.circle(self.screen, body, (sx+3, sy), 1)
                    # legs
                    pygame.draw.line(self.screen, shade, (sx-2, sy+2), (sx-4, sy+3))
                    pygame.draw.line(self.screen, shade, (sx+2, sy+2), (sx+4, sy+3))

            elif kind == "iguana":
                g = payload
                if g.state == "dead":
                    body = (max(0, g.color_body[0] - 60), max(0, g.color_body[1] - 60), max(0, g.color_body[2] - 60))
                    belly = (max(0, g.color_belly[0] - 50), max(0, g.color_belly[1] - 50), max(0, g.color_belly[2] - 50))
                    pygame.draw.ellipse(self.screen, body, (sx-4, sy-2, 8, 4))
                    pygame.draw.ellipse(self.screen, belly, (sx-3, sy-1, 6, 3))
                    pygame.draw.line(self.screen, body, (sx+4, sy), (sx+9, sy+1))  # tail
                    pygame.draw.line(self.screen, (25, 35, 35), (sx-2, sy-1), (sx-1, sy-1))
                    pygame.draw.line(self.screen, (25, 35, 35), (sx+1, sy-1), (sx+2, sy-1))
                else:
                    body = g.color_body
                    belly = g.color_belly
                    pygame.draw.ellipse(self.screen, body, (sx-4, sy-3, 8, 6))
                    pygame.draw.ellipse(self.screen, belly, (sx-3, sy-1, 6, 4))
                    pygame.draw.circle(self.screen, body, (sx-5, sy-2), 2)     # head
                    pygame.draw.circle(self.screen, belly, (sx-6, sy-1), 1)
                    # legs (4)
                    pygame.draw.line(self.screen, body, (sx-2, sy+2), (sx-3, sy+4))
                    pygame.draw.line(self.screen, body, (sx+1, sy+2), (sx, sy+4))
                    pygame.draw.line(self.screen, body, (sx-1, sy+2), (sx-2, sy+4))
                    pygame.draw.line(self.screen, body, (sx+2, sy+2), (sx+3, sy+4))
                    # long thin tail
                    pygame.draw.line(self.screen, body, (sx+4, sy), (sx+10, sy+2))
                    pygame.draw.line(self.screen, belly, (sx+4, sy+1), (sx+9, sy+3))
                    # eyes
                    pygame.draw.circle(self.screen, (25, 35, 35), (sx-6, sy-3), 1)
                    pygame.draw.circle(self.screen, (25, 35, 35), (sx-4, sy-3), 1)

            elif kind == "bird":
                b = payload
                if b.state == "dead":
                    col = (235, 245, 250) if b.species == "seagull" else (92, 182, 98)
                    pygame.draw.circle(self.screen, col, (sx, sy), 2)
                    pygame.draw.circle(self.screen, (30, 40, 60), (sx + 1, sy), 1)
                else:
                    if b.species == "seagull":
                        body = (235, 245, 250)
                        wing = (200, 210, 220)
                    else:
                        body = (92, 182, 98)
                        wing = (238, 120, 175)
                    flap = int(math.sin(self.time_s * 10.0 + b.x * 0.02) * 1.0)
                    pygame.draw.circle(self.screen, body, (sx, sy), 2)
                    pygame.draw.line(self.screen, wing, (sx - 3, sy), (sx - 1, sy - 2 - flap))
                    pygame.draw.line(self.screen, wing, (sx + 3, sy), (sx + 1, sy - 2 + flap))
                    pygame.draw.circle(self.screen, (30, 40, 60), (sx + 1, sy - 1), 1)
            elif kind == "tree":
                idx = payload
                tr = self.world.trees[idx]
                occluded = any(m.climbing and m.climb_tree_idx == idx and m.climb_t > 0.55 for m in self.monkeys)
                draw_coconut_tree(self.screen, sx, sy, tr, self.time_s, occluded)
            elif kind == "anthill":
                self._draw_anthill(sx, sy)
                active = self.monkeys[self.p1_idx]
                if (active.x - self.anthill_x) ** 2 + (active.y - self.anthill_y) ** 2 <= (28.0 ** 2):
                    draw_shadowed_text(self.screen, self.font_small, "Anthill: E or click", max(6, sx - 26), max(6, sy - 18), bg_alpha=110, pad=2)
            else:  # monkey
                idx = self._sanitize_monkey_index(payload, self.p1_idx)
                m = self.monkeys[idx]
                highlight = (idx == self.p1_idx)
                if m.on_raft:
                    pygame.draw.rect(self.screen, (126, 92, 56), pygame.Rect(sx - 7, sy + 5, 14, 3))
                    pygame.draw.rect(self.screen, (98, 72, 44), pygame.Rect(sx - 7, sy + 5, 14, 1))
                draw_monkey_sprite(self.screen, sx, sy, m, self.time_s, highlight)

        self._draw_ui()

        self.window.fill((0, 0, 0))
        scaled = pygame.transform.scale(self.screen, (self.view_w, self.view_h))
        self.window.blit(scaled, (self.view_x, self.view_y))
        pygame.display.flip()

    def _draw_shore_foam(self, tx0, ty0, tx1, ty1, camx, camy, dest=None):
        surf = dest if dest is not None else self.screen
        phase = self.time_s * 1.6
        sw, sh = surf.get_size()
        for ty in range(ty0, ty1):
            for tx in range(tx0, tx1):
                if self.world.tiles[ty][tx] != T_WATER:
                    continue

                land_neighbors = 0
                for ox, oy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = tx + ox, ty + oy
                    if 0 <= nx < self.world.tw and 0 <= ny < self.world.th and self.world.tiles[ny][nx] != T_WATER:
                        land_neighbors += 1
                if land_neighbors == 0:
                    continue

                sx = tx * TILE - camx
                sy = ty * TILE - camy

                for k in range(5):
                    a = (hash2(tx * 31 + k * 7, ty * 29 + k * 11, 404) / 0xFFFFFFFF) * math.tau
                    r = 1.8 + (hash2(tx + k * 13, ty + k * 17, 505) % 100) / 100.0 * 2.2
                    px = int(sx + TILE / 2 + math.cos(a + phase) * r)
                    py = int(sy + TILE / 2 + math.sin(a - phase * 0.7) * r * 0.6)
                    if 0 <= px < sw and 0 <= py < sh:
                        surf.set_at((px, py), C_FOAM)

    # ---------
    # UI
    # ---------
    def _draw_hotbar(self, inv: items.Inventory):
        slot_w = 11
        pad = 1
        shown = min(12, inv.max_slots)
        total_w = shown * slot_w + (shown - 1) * pad
        x0 = (INTERNAL_W - total_w) // 2
        y0 = INTERNAL_H - (slot_w + 3)

        page0 = (inv.selected // 12) * 12
        pageN = min(12, inv.max_slots - page0)

        for pi in range(pageN):
            i = page0 + pi
            rx = x0 + pi * (slot_w + pad)
            ry = y0
            r = pygame.Rect(rx, ry, slot_w, slot_w)
            pygame.draw.rect(self.screen, (255, 255, 255), r, 1)
            if i == inv.selected:
                pygame.draw.rect(self.screen, (255, 255, 255), r.inflate(2, 2), 1)

            s = inv.slots[i]
            if s:
                items.draw_icon(pygame, self.screen, rx + 1, ry + 1, s.item_id, scale=1)


    def _handle_inventory_click(self, mx: int, my: int) -> bool:
        """Select an inventory slot by clicking it (when the inventory panel is visible)."""
        layout = getattr(self, "_inv_layout", None)
        if not layout:
            return False
        panel = layout.get("panel")
        if panel and not panel.collidepoint(mx, my):
            return False

        gx = int(layout.get("grid_x", 0))
        gy = int(layout.get("grid_y", 0))
        cols = int(layout.get("cols", 0))
        slot_w = int(layout.get("slot_w", 0))
        gap = int(layout.get("gap", 0))
        max_slots = int(layout.get("max_slots", 0))
        inv = layout.get("inv")

        if not inv or cols <= 0 or slot_w <= 0:
            return False

        relx = mx - gx
        rely = my - gy
        if relx < 0 or rely < 0:
            return False

        cell = slot_w + gap
        col = relx // cell
        row = rely // cell
        if col < 0 or col >= cols or row < 0:
            return False

        # Require the click to be inside the slot area, not in the gap.
        if (relx % cell) >= slot_w or (rely % cell) >= slot_w:
            return False

        idx = row * cols + col
        if idx < 0 or idx >= max_slots:
            return False

        inv.selected = idx
        return True

    def _get_origin_preview(self, item_id: str, size: int = 60) -> "pygame.Surface":
        """Return a cached preview surface showing the item's original form (world object)."""
        key = (str(item_id), int(size))
        if key in self._origin_preview_cache:
            return self._origin_preview_cache[key]

        surf = pygame.Surface((size, size), pygame.SRCALPHA)

        # Draw pixel-art into a 16x16 logical grid, scaled up to fit.
        grid = 16
        scale = max(1, size // grid)
        ox = (size - grid * scale) // 2
        oy = (size - grid * scale) // 2

        def px(ix: int, iy: int, col):
            if 0 <= ix < grid and 0 <= iy < grid:
                surf.fill(col, (ox + ix * scale, oy + iy * scale, scale, scale))

        def blob(cx: int, cy: int, r: int, col):
            rr = r * r
            for iy in range(cy - r, cy + r + 1):
                for ix in range(cx - r, cx + r + 1):
                    if (ix - cx) * (ix - cx) + (iy - cy) * (iy - cy) <= rr:
                        px(ix, iy, col)

        # Defaults (fallback to a scaled item icon).
        def fallback_icon():
            try:
                icon_scale = max(1, (size - 10) // 10)
                items.draw_icon(pygame, surf, (size - 10 * icon_scale) // 2, (size - 10 * icon_scale) // 2, item_id, scale=icon_scale)
            except Exception:
                pass

        # Origin previews
        if item_id == getattr(items, "CRAB_MEAT", "crab_meat"):
            # Show a crab (not meat).
            shell = (170, 80, 60)
            dark = (120, 55, 45)
            eye = (235, 235, 235)
            blob(8, 9, 4, shell)
            blob(8, 10, 3, dark)
            # legs
            for lx in (4, 5, 11, 12):
                px(lx, 10, dark); px(lx, 11, dark)
            # claws
            px(3, 8, shell); px(2, 8, dark); px(13, 8, shell); px(14, 8, dark)
            # eyes
            px(6, 7, eye); px(10, 7, eye); px(6, 6, dark); px(10, 6, dark)
        elif item_id == getattr(items, "PALM_LEAF", "palm_leaf"):
            # Show a palm frond fan (more like the dropped pickup).
            g0 = (70, 150, 70)
            g1 = (45, 120, 55)
            # stem
            for i in range(6, 13):
                px(8, i, g1)
            # fan ribs
            for dx in range(-6, 7):
                px(8 + dx, 6, g0)
            for k in range(1, 6):
                px(8 - k, 6 + k//2, g0)
                px(8 + k, 6 + k//2, g0)
            # strands
            for dx in range(-6, 7, 2):
                for step in range(1, 5):
                    px(8 + dx + (step//3), 6 + step, g0)
            px(8, 5, (120, 190, 120))
        elif item_id == getattr(items, "SEAWEED", "seaweed"):
            g0 = (55, 135, 85)
            g1 = (35, 105, 65)
            # three wavy strands
            for i in range(4, 14):
                px(6 + (i % 3 == 0), i, g0)
                px(8 + (i % 4 == 0), i, g1)
                px(10 + (i % 3 == 1), i, g0)
            # base clump
            for ix in range(5, 12):
                px(ix, 14, g1)
        elif item_id == getattr(items, "WOOD", "wood"):
            b0 = (150, 105, 65)
            b1 = (110, 75, 45)
            # driftwood/log
            for iy in range(7, 12):
                for ix in range(3, 13):
                    px(ix, iy, b0)
            for ix in range(3, 13, 2):
                px(ix, 7, b1); px(ix, 11, b1)
            px(12, 8, b1); px(3, 10, b1)
        elif item_id == getattr(items, "ROCK", "rock"):
            c0 = (150, 150, 150)
            c1 = (110, 110, 110)
            blob(8, 10, 4, c0)
            blob(7, 9, 2, c1)
            px(10, 12, c1); px(9, 13, c1)
        elif item_id == getattr(items, "REPTILE_MEAT", "reptile_meat"):
            # Show a cute iguana (not the meat).
            body = (90, 180, 95)
            belly = (170, 220, 170)
            blob(8, 10, 4, body)
            blob(8, 11, 3, belly)
            blob(5, 8, 2, body)  # head
            # legs
            px(6, 12, body); px(7, 13, body); px(9, 13, body); px(10, 12, body)
            px(7, 12, body); px(9, 12, body)
            # tail
            for t in range(6):
                px(11 + t//2, 10 + (t % 2), body)
            # eye
            px(4, 7, (25, 35, 35))

        else:
            fallback_icon()

        self._origin_preview_cache[key] = surf
        return surf

    def _draw_inventory_panel(self, inv: items.Inventory, title: str) -> pygame.Rect:
        """Compact inventory panel rendered out of the way.

        Returns the panel rect for positioning other UI elements nearby.
        """
        cols = 6
        slot_w = 12
        gap = 3
        pad = 4
        header_h = max(12, self.font_small.get_linesize() + 4)
        rows = (inv.max_slots + cols - 1) // cols

        w = pad * 2 + cols * slot_w + (cols - 1) * gap
        h = pad * 2 + header_h + rows * slot_w + (rows - 1) * gap + 10  # footer line

        # Center the inventory grid on screen; keep the UI largely transparent (icons + text only).
        x = (INTERNAL_W - w) // 2
        y = (INTERNAL_H - h) // 2

        panel = pygame.Rect(x, y, w, h)

        # Subtle translucent panel backing so text stays readable without looking like a heavy UI slab.
        panel_bg = pygame.Surface((w, h), pygame.SRCALPHA)
        panel_bg.fill((0, 0, 0, 70))
        self.screen.blit(panel_bg, (x, y))
        pygame.draw.rect(self.screen, (255, 255, 255), panel, 1)


        draw_shadowed_text(self.screen, self.font_small, title, x + pad, y + 2, bg_alpha=110, pad=3)

        grid_y = y + header_h
        for i in range(inv.max_slots):
            cx = i % cols
            cy = i // cols
            rx = x + pad + cx * (slot_w + gap)
            ry = grid_y + pad + cy * (slot_w + gap)
            r = pygame.Rect(rx, ry, slot_w, slot_w)

            pygame.draw.rect(self.screen, (255, 255, 255), r, 1)
            if i == inv.selected:
                pygame.draw.rect(self.screen, (255, 255, 255), r.inflate(2, 2), 1)

            s = inv.slots[i]
            if s:
                items.draw_icon(pygame, self.screen, rx + (slot_w - 10)//2, ry + (slot_w - 10)//2, s.item_id, scale=1)

        # Cache layout for click hit-testing while the inventory is open.
        self._inv_layout = {
            "panel": panel,
            "inv": inv,
            "grid_x": x + pad,
            "grid_y": grid_y + pad,
            "cols": cols,
            "slot_w": slot_w,
            "gap": gap,
            "max_slots": inv.max_slots,
        }

        # Names list to the right of the grid (text-only; no backing panel).
        list_x = x + w + 12
        list_y = y + 4
        # If we're near the right edge, clamp the list so it stays visible.
        if list_x > INTERNAL_W - 120:
            list_x = max(6, INTERNAL_W - 120)

        s = inv.selected_stack()
        if s:
            sel_name = items.ITEMS[s.item_id].name if s.item_id in items.ITEMS else str(s.item_id)
            draw_shadowed_text(self.screen, self.font_small, f"Selected: {sel_name}", list_x, list_y, bg_alpha=110, pad=3)
            list_y += max(10, self.font_small.get_linesize())

            # Show the origin / original form preview in the empty right-side space.
            preview = self._get_origin_preview(s.item_id, 60)
            px = min(INTERNAL_W - preview.get_width() - 6, list_x + 120)
            py = y + 18
            # If the names list is clamped near the right edge, draw the preview below the list instead.
            if px <= list_x + 4:
                px = list_x
                py = min(INTERNAL_H - preview.get_height() - 6, y + 52)
            pygame.draw.rect(self.screen, (255, 255, 255), (px - 2, py - 2, preview.get_width() + 4, preview.get_height() + 4), 1)
            self.screen.blit(preview, (px, py))

        totals = {}
        for st in inv.slots:
            if st:
                totals[st.item_id] = totals.get(st.item_id, 0) + st.qty

        def _iname(iid: str) -> str:
            return items.ITEMS[iid].name if iid in items.ITEMS else str(iid)

        for iid in sorted(totals.keys(), key=_iname):
            line = f"{_iname(iid)} x{totals[iid]}"
            draw_shadowed_text(self.screen, self.font_small, line, list_x, list_y, bg_alpha=95, pad=2)
            # (text drawn via draw_shadowed_text)
            list_y += max(9, self.font_small.get_linesize() - 1)
            # Avoid drawing off-screen.
            if list_y > INTERNAL_H - 14:
                break

        return panel

    def _draw_ui(self):
        if self._hint_t > 0.0 and self._last_hint:
            draw_shadowed_text(self.screen, self.font_small, self._last_hint, 6, 6, bg_alpha=130, pad=3)

        self._draw_hotbar(self.shared_inv)

        if not self.show_inv:
            self._inv_layout = None

        if self.show_inv:
            who = self.monkeys[self.p1_idx].name
            panel_rect = self._draw_inventory_panel(self.shared_inv, f"Inventory ({who})")
            if self._can_craft_raft():
                draw_shadowed_text(self.screen, self.font_small, "C: Craft Raft", panel_rect.x + 6, panel_rect.bottom + 2, bg_alpha=120, pad=3)


        # Crosshair
        internal_mouse = self._window_to_internal((self.mouse_x, self.mouse_y))
        if internal_mouse is not None:
            mx, my = internal_mouse
            pygame.draw.circle(self.screen, (255, 255, 255), (mx, my), 3, 1)


def main():
    def _hook(exc_type, exc, tb):
        try:
            exc.__traceback__ = tb  # type: ignore[attr-defined]
        except Exception:
            pass
        try:
            write_crash_report(exc, state={"where": "sys.excepthook"})
        except Exception:
            pass
        sys.__excepthook__(exc_type, exc, tb)

    sys.excepthook = _hook

    try:
        Game().run()
    except BaseException as e:
        state = {}
        try:
            g = None
            for v in list(locals().values()):
                if isinstance(v, Game):
                    g = v
                    break
            if g is not None:
                state = getattr(g, "_last_state", {}) or {}
        except Exception:
            state = {}
        path = write_crash_report(e, state=state)
        print(f"CRASH: wrote report to {path}")
        raise


if __name__ == "__main__":
    main()
