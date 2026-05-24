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
EMBEDDED_MODE = bool(globals().get("MONKEY_EMBEDDED_MODE", False))
EMBEDDED_WINDOW_SIZE = globals().get("MONKEY_WINDOW_SIZE", (1920, 1080))
EMBEDDED_START_FULLSCREEN = bool(globals().get("MONKEY_START_FULLSCREEN", False))
EMBEDDED_AUTOTEST_RETURN_FRAMES = int(globals().get("MONKEY_AUTOTEST_RETURN_FRAMES", 0) or 0)
MONKEY_EMBEDDED_RESULT = "resume"


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
WIN_W, WIN_H = 1920, 1080
MIN_WINDOW_W, MIN_WINDOW_H = 640, 360
MAX_WINDOW_W, MAX_WINDOW_H = 7680, 4320

def sanitize_window_size(size) -> Tuple[int, int]:
    try:
        w, h = int(size[0]), int(size[1])
    except Exception:
        return WIN_W, WIN_H
    w = max(MIN_WINDOW_W, min(MAX_WINDOW_W, w))
    h = max(MIN_WINDOW_H, min(MAX_WINDOW_H, h))
    return int(w), int(h)

def safe_set_mode(size=None, fullscreen: Optional[bool] = None):
    global screen
    if size is None:
        size = EMBEDDED_WINDOW_SIZE
    size = sanitize_window_size(size)
    if fullscreen is None:
        fullscreen = EMBEDDED_START_FULLSCREEN if EMBEDDED_MODE else False
    flags = pygame.DOUBLEBUF
    if fullscreen:
        flags |= pygame.FULLSCREEN
    else:
        flags |= pygame.RESIZABLE
    try:
        screen = pygame.display.set_mode((0, 0) if fullscreen else size, flags, vsync=1)
    except TypeError:
        screen = pygame.display.set_mode((0, 0) if fullscreen else size, flags)
    except Exception:
        screen = pygame.display.set_mode((0, 0) if fullscreen else size, flags & ~pygame.FULLSCREEN if fullscreen else pygame.RESIZABLE)
    globals()["MONKEY_WINDOW_SIZE"] = tuple(screen.get_size())
    return screen

def refresh_ui_fonts() -> None:
    global ui_font, small_font
    ui_font = pygame.font.SysFont("consolas", 20, bold=True)
    small_font = pygame.font.SysFont("consolas", 16, bold=True)

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
screen = safe_set_mode(EMBEDDED_WINDOW_SIZE if EMBEDDED_MODE else (WIN_W, WIN_H), fullscreen=EMBEDDED_START_FULLSCREEN if EMBEDDED_MODE else False)
pygame.display.set_caption("Ant Wars")

icon_path = os.path.join("assets", "icon.png")
if os.path.exists(icon_path):
    pygame.display.set_icon(pygame.image.load(icon_path))

clock = pygame.time.Clock()
refresh_ui_fonts()


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
    w, h = 210, 16
    x = win_w - w - 18
    y = win_h - h - 18
    return pygame.Rect(x, y, w, h)


def slider_knob_rect(r: pygame.Rect) -> pygame.Rect:
    t = (GAME_SPEED - SPEED_MIN) / (SPEED_MAX - SPEED_MIN)
    kx = int(r.x + t * r.w)
    return pygame.Rect(kx - 6, r.y - 4, 12, r.h + 8)


def mute_button_rect() -> pygame.Rect:
    # Small UI button just above the speed slider (bottom-right).
    r = slider_rect()
    w, h = 110, 26
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

    hud_y = 8
    line1 = small_font.render(f"Black Queen Ant HP {b_pct}%", True, (255,255,255))
    line2 = small_font.render(f"Red Queen Ant HP {r_pct}%", True, (255,255,255))
    line3 = small_font.render(f"Black Queen Ant Level {queen_level}", True, (255,255,255))
    line4 = small_font.render(f"Ants  Black:{len(ants)}  Red:{len(red_ants)}", True, (255,255,255))
    screen.blit(line1, (8, hud_y)); hud_y += 16
    screen.blit(line2, (8, hud_y)); hud_y += 16
    screen.blit(line3, (8, hud_y)); hud_y += 16
    screen.blit(line4, (8, hud_y))
    hud_y += 16
    line5 = small_font.render(f"Hornets: {len(hornets)}", True, (255,255,255))
    screen.blit(line5, (8, hud_y))

    # Speed slider overlay (bottom-right)
    r = slider_rect()
    pygame.draw.rect(screen, (20, 20, 20), r, border_radius=6)
    pygame.draw.rect(screen, (255, 255, 255), r, 1, border_radius=6)
    k = slider_knob_rect(r)
    pygame.draw.rect(screen, (255, 255, 255), k, border_radius=6)
    label = ui_font.render(f"Speed x{GAME_SPEED:.1f}", True, (255,255,255))
    screen.blit(label, (r.x, r.y - 18))

    # Music mute button (above slider)
    mb = mute_button_rect()
    pygame.draw.rect(screen, (20, 20, 20), mb, border_radius=6)
    pygame.draw.rect(screen, (255, 255, 255), mb, 1, border_radius=6)
    mtxt = "Unmute" if music_muted else "Mute"
    mt = ui_font.render(mtxt, True, (255,255,255))
    screen.blit(mt, (mb.x + 10, mb.y + 5))

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
autotest_return_frames = EMBEDDED_AUTOTEST_RETURN_FRAMES
while running:

    if 'spawn_tree_once' in globals():
        spawn_tree_once()
        tree_growth_timer += 1
        if tree_growth_timer >= TREE_GROW_INTERVAL:
            tree_growth_timer = 0
            grow_tree_step()

    clock.tick(FPS)
    tick_music()
    if EMBEDDED_MODE and autotest_return_frames > 0:
        autotest_return_frames -= 1
        if autotest_return_frames <= 0:
            MONKEY_EMBEDDED_RESULT = "resume"
            globals()["MONKEY_WINDOW_SIZE"] = tuple(screen.get_size())
            running = False
            continue

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
            MONKEY_EMBEDDED_RESULT = "quit" if EMBEDDED_MODE else "resume"
            globals()["MONKEY_WINDOW_SIZE"] = tuple(screen.get_size())
            running = False

        if e.type == pygame.VIDEORESIZE:
            screen = safe_set_mode((e.w, e.h), fullscreen=False)
            refresh_ui_fonts()
            zmin = dynamic_zoom_min()
            if zoom_target < zmin:
                zoom_target = zmin
            clamp_camera()

        if e.type == pygame.KEYDOWN:
            if EMBEDDED_MODE and e.key in (pygame.K_ESCAPE, pygame.K_e):
                MONKEY_EMBEDDED_RESULT = "resume"
                globals()["MONKEY_WINDOW_SIZE"] = tuple(screen.get_size())
                running = False
                continue
            if e.key == pygame.K_r:
                reset_game()

            # Camera hotkeys
            elif e.key == pygame.K_f:
                try:
                    if (screen.get_flags() & pygame.FULLSCREEN) != 0:
                        screen = safe_set_mode(globals().get("MONKEY_WINDOW_SIZE", (WIN_W, WIN_H)), fullscreen=False)
                    else:
                        screen = safe_set_mode(screen.get_size(), fullscreen=True)
                    refresh_ui_fonts()
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