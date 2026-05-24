import sys
import math
import random
import os
import time
import traceback
import datetime
from pathlib import Path
import pygame

from sound_handler import SoundHandler
# ============================================================
# Mewtants - Pretty World + Enemies (v1)
# New in v8:
# - Kittens ALWAYS scratch enemies that get close (regardless of follow/assist mode).
# - Scratch has sharper "claw" slash VFX (3 sharp slashes).
# - Companions can now use their own powers automatically (each with its own cooldown).
# - Encounter-based enemy spawning retained (v7 behavior).
# ============================================================

SCREEN_W, SCREEN_H = 1920, 1080

LOG_DIR = Path(__file__).resolve().parent / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LATEST_LOG = LOG_DIR / "latest.log"


def _write_log_line(text: str) -> None:
    try:
        with open(LATEST_LOG, "a", encoding="utf-8") as f:
            f.write(text.rstrip() + "\n")
    except Exception:
        pass


def _write_crash(exc: BaseException) -> Path:
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out = LOG_DIR / f"crash_{ts}.txt"
    try:
        with open(out, "w", encoding="utf-8") as f:
            f.write("Mewtants Co-op crash report\n")
            f.write(f"Timestamp: {datetime.datetime.now().isoformat()}\n\n")
            f.write("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))
    except Exception:
        pass
    return out


def _env_int(name: str, default: int) -> int:
    try:
        return int(float(os.getenv(name, str(default))))
    except Exception:
        return default

FPS = max(30, min(240, _env_int("DESKTOP_MAX_FPS", 60)))

TILE = 32
CHUNK_TILES = 24
CHUNK_PX = TILE * CHUNK_TILES

UI_BG = (10, 10, 12)
WHITE = (235, 235, 240)
BG = (14, 16, 18)

SPRITE_SCALE = 4

LEADER_SPEED = 245.0
FOLLOW_SPEED = 350.0
FOLLOW_CATCHUP_SPEED = 520.0
FOLLOW_STOP_RADIUS = 10.0
FOLLOW_ACCEL = 2200.0
LEADER_ACCEL = 2500.0

SEPARATION_RADIUS = 34.0
SEPARATION_FORCE = 175.0
MAX_VEL = 780.0

POWER_CD = {
    "Ember": 0.45,
    "Breeze": 0.85,
    "Frost": 1.10,
    "Sparkle": 0.95,
}

LEADER_MAX_HP = 100
LEADER_RESPAWN_TIME = 2.0

# Melee
MELEE_SCRATCH_RANGE = 54
MELEE_BITE_RANGE = 38
MELEE_SCRATCH_DMG = 7
MELEE_BITE_DMG = 10
MELEE_SCRATCH_CD = 0.35
MELEE_BITE_CD = 0.70

# Arm (paw) rendering / melee swat animation
ARM_IDLE_LEN = 6
ARM_SWING_LEN_SCRATCH = 20
ARM_SWING_LEN_BITE = 14
ARM_SWING_TIME_SCRATCH = 0.18
ARM_SWING_TIME_BITE = 0.22
ARM_SPREAD = 7
ARM_FORWARD = 6
ARM_ANCHOR_Y = 4
ARM_WIDTH = 3
ARM_SWING_ANGLE_DEG = 55

# Always-scratch scan (close-range)
AUTO_SCRATCH_SCAN_RADIUS = 64

# Assist AI
ASSIST_ACQUIRE_RANGE = 680.0
ASSIST_BREAK_RANGE = 980.0
ASSIST_ORBIT_RANGE = 110.0
ASSIST_CHASE_SPEED = 330.0
ASSIST_CHASE_ACCEL = 2200.0

# AI powers
AI_POWER_RANGE = 520.0
AI_POWER_CHANCE = 0.65
AI_POWER_DECISION_RATE = 0.22
AI_SPARKLE_MAX_BLINK = 220.0

# Encounters
ENCOUNTER_GROUP_MIN = 2
ENCOUNTER_GROUP_MAX = 4
ENCOUNTER_DISTANCE_MIN = 900.0
ENCOUNTER_DISTANCE_JITTER = 650.0
ENCOUNTER_COOLDOWN = 3.5
ENCOUNTER_MAX_LIVE = 10
ENCOUNTER_VIEW_CLEARANCE = 1.2


# Water / Overworld detail
WATER_POND_THRESHOLD = 0.78
WATER_RIVER_BASE_HALF_WIDTH = 1.8
WATER_RIVER_WIDTH_JITTER = 1.2
WATER_RIVER_PERIOD_TILES = 240.0
WATER_RIVER_COUNT = 2

# Non-hostile animals (Overworld)
SQUIRREL_SPAWN_RATE = 0.22
SQUIRREL_MAX_PER_CHUNK = 2
SQUIRREL_RADIUS = 14
SQUIRREL_FEAR_RADIUS = 170.0
SQUIRREL_WANDER_SPEED = 110.0
SQUIRREL_RUN_SPEED = 270.0
SQUIRREL_TURN_RATE = 3.2
SQUIRREL_CAPTURE_RADIUS = 26
SQUIRREL_POWER_CATNIP_CHANCE = 0.65
SQUIRREL_CATNIP_TIME = 6.5
SQUIRREL_TUNA_HEAL = 18


# Pickups / Powerups
PICKUP_RADIUS = 16
CATNIP_BUFF_TIME = 12.0
CATNIP_SPAWN_RATE = 0.10
TUNA_SPAWN_RATE = 0.10
WHISTLE_SPAWN_RATE = 0.012
MAX_LIVES = 9
TUNA_HEAL = 35
CATNIP_DMG_MULT = 1.25
CATNIP_CD_MULT = 0.75
CATNIP_SPEED_MULT = 1.12
# Jumping (party jump on Space)
JUMP_VEL = 920.0         # upward impulse (px/s) - intentionally "pretty high"         # upward impulse (px/s) - intentionally "pretty high"
JUMP_GRAVITY = 2600.0    # gravity (px/s^2)    # gravity (px/s^2)
JUMP_MAX_Z_FOR_SHADOW = 170.0
JUMP_COOLDOWN = 0.18
JUMP_PARTY_RADIUS = 320.0

# Biome blending (overworld): as you travel along +X, the overworld gradually transitions
# between these biomes in order. Transitions are tile-level blended for a smooth gradient.
BIOME_ORDER = ["grass", "desert", "snow", "mountain", "jungle", "swamp", "beach"]
BIOME_BAND_PX = 9000.0     # distance spent primarily in one biome before transitioning
BIOME_BLEND_PX = 3000.0    # last portion of each band used for cross-fade to next biome
WORLD_CHUNK_CACHE_LIMIT = 196  # ~14x14 chunks cached (keeps memory bounded)



# Cat Towers / Dungeons
TOWER_RADIUS = 30
TOWER_SPAWN_RATE = 0.14

DUNGEON_W = 61   # must be odd
DUNGEON_H = 61   # must be odd
DUNGEON_FLOOR = 0
DUNGEON_WALL = 1

DUNGEON_ENEMY_COUNT_MIN = 14
DUNGEON_ENEMY_COUNT_MAX = 22

BOSS_HP = 420
BOSS_RADIUS = 34
BOSS_SHOOT_CD = 0.75
BOSS_SHOOT_SPREAD = 7
BOSS_CHARGE_CD = 2.2
BOSS_CHARGE_TIME = 0.35
BOSS_CHARGE_SPEED = 620.0
BOSS_PROJECTILE_DMG = 14
BOSS_MOVE_SPEED = 220.0
BOSS_MOVE_SPEED = 220.0

# Permanent upgrades after boss win (stacking)
UPG_DMG_PER_LEVEL = 0.08
UPG_HP_PER_LEVEL = 10
UPG_SPEED_PER_LEVEL = 0.03
UPG_CD_REDUCTION_PER_LEVEL = 0.03
UPG_MAX_LEVEL_FOR_CD = 8

ENEMY_ACTIVATION_DIST = 520.0

DESPAWN_DORMANT_DIST = 1600.0
DESPAWN_ACTIVE_DIST = 2200.0
DESPAWN_ACTIVE_MINCOUNT = 6

# Enemies
ROBOT_CAT_HP = 36
ROBOT_DOG_HP = 52

CAT_AGGRO = 760
CAT_SHOOT_RANGE = 360
CAT_DESIRED_RANGE = 250
CAT_SHOOT_CD = 1.15

DOG_AGGRO = 780
DOG_BITE_RANGE = 48
DOG_LUNGE_CD = 1.40
DOG_LUNGE_TIME = 0.22

# Damage
DMG_EMBER = 14
DMG_FROST = 9
DMG_BREEZE_DASH = 12
DMG_CAT_BOLT = 10
DMG_DOG_BITE = 14


def hash2i(x, y, seed=1337):
    n = (x * 374761393) ^ (y * 668265263) ^ (seed * 2246822519)
    n = (n ^ (n >> 13)) * 1274126177
    n = n ^ (n >> 16)
    return n & 0xFFFFFFFF


def rand01(x, y, seed=1337, salt=0):
    return (hash2i(x + 17 * salt, y - 31 * salt, seed) / 0xFFFFFFFF)


def clamp_vec(v, max_len):
    if v.length_squared() <= max_len * max_len:
        return v
    if v.length_squared() == 0:
        return pygame.Vector2(0, 0)
    return v.normalize() * max_len


def lerp(a, b, t):
    return a + (b - a) * t


def smoothstep(t):
    return t * t * (3.0 - 2.0 * t)


def value_noise(x, y, scale, seed=1337, salt=0):
    # Deterministic, smooth-ish noise via bilinear interpolation of rand01 on a coarse grid.
    # x, y are in tile coordinates; scale is in tiles (larger => smoother/lower frequency).
    if scale <= 0:
        return rand01(int(x), int(y), seed, salt=salt)

    sx = math.floor(x / scale)
    sy = math.floor(y / scale)

    fx = (x / scale) - sx
    fy = (y / scale) - sy
    fx = smoothstep(fx)
    fy = smoothstep(fy)

    v00 = rand01(sx, sy, seed, salt=salt)
    v10 = rand01(sx + 1, sy, seed, salt=salt)
    v01 = rand01(sx, sy + 1, seed, salt=salt)
    v11 = rand01(sx + 1, sy + 1, seed, salt=salt)

    vx0 = lerp(v00, v10, fx)
    vx1 = lerp(v01, v11, fx)
    return lerp(vx0, vx1, fy)


def river_distance(gx, gy, seed=1337):
    # Returns distance-to-nearest river centerline in tile units.
    # The implementation intentionally uses periodic wrapping so rivers recur across the infinite world.
    period = WATER_RIVER_PERIOD_TILES
    off_y = rand01(91, 17, seed, salt=77) * period
    off_x = rand01(31, 61, seed, salt=82) * period

    gy_mod = (gy + off_y) % period
    gx_mod = (gx + off_x) % period

    # Horizontal-ish river (center y varies with x)
    amp1 = 10.0 + rand01(12, 34, seed, salt=78) * 18.0
    amp2 = 6.0 + rand01(56, 78, seed, salt=79) * 12.0
    ph1 = rand01(7, 9, seed, salt=80) * math.tau
    ph2 = rand01(11, 13, seed, salt=81) * math.tau
    t = (gx * 0.11)
    cy = (period * 0.5) + amp1 * math.sin(t + ph1) + amp2 * math.sin(t * 0.55 + ph2)
    d_h = abs(gy_mod - cy)
    d_h = min(d_h, period - d_h)

    # Vertical-ish river (center x varies with y)
    ax1 = 9.0 + rand01(90, 22, seed, salt=83) * 16.0
    ax2 = 5.0 + rand01(44, 55, seed, salt=84) * 11.0
    px1 = rand01(2, 5, seed, salt=85) * math.tau
    px2 = rand01(6, 8, seed, salt=86) * math.tau
    t2 = (gy * 0.105)
    cx = (period * 0.5) + ax1 * math.sin(t2 + px1) + ax2 * math.sin(t2 * 0.60 + px2)
    d_v = abs(gx_mod - cx)
    d_v = min(d_v, period - d_v)

    return min(d_h, d_v)


def make_surface_px(w, h):
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    s.fill((0, 0, 0, 0))
    return s


def px(surf, x, y, color):
    if 0 <= x < surf.get_width() and 0 <= y < surf.get_height():
        surf.set_at((x, y), color)


def draw_rect_px(surf, x, y, w, h, color):
    for yy in range(y, y + h):
        for xx in range(x, x + w):
            px(surf, xx, yy, color)


def outline_from_alpha(src, outline_color=(0, 0, 0, 255)):
    w, h = src.get_size()
    out = make_surface_px(w, h)
    alpha = pygame.surfarray.pixels_alpha(src)
    for y in range(h):
        for x in range(w):
            if alpha[x][y] > 0:
                for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                    if 0 <= nx < w and 0 <= ny < h and alpha[nx][ny] == 0:
                        out.set_at((nx, ny), outline_color)
    del alpha
    out.blit(src, (0, 0))
    return out


def scale_nearest(surf, scale):
    w, h = surf.get_size()
    return pygame.transform.scale(surf, (w * scale, h * scale))


def make_jump_variants(img):
    """Build 3 quick 'animation' poses (takeoff/air/land) from a base frame."""
    w, h = img.get_size()
    def sc(sx, sy):
        return pygame.transform.scale(img, (max(1, int(w * sx)), max(1, int(h * sy))))
    takeoff = sc(1.08, 0.92)
    air = sc(0.95, 1.08)
    land = sc(1.08, 0.90)
    return [takeoff, air, land]


def build_cat_sprites(base_rgb, accent_rgb, seed=0):
    W, H = 16, 16

    basec = base_rgb + (255,)
    shade1 = tuple(max(0, c - 35) for c in base_rgb) + (255,)
    shade2 = tuple(min(255, c + 28) for c in base_rgb) + (255,)
    accentc = accent_rgb + (255,)
    eye = (245, 245, 245, 255)
    pupil = (30, 30, 30, 255)
    nose = (230, 150, 170, 255)

    paw_y_off = [0, -1, 0, 0, -1, 0]
    paw_alt = [0, 1, 0, 0, 1, 0]
    bob = [0, 0, 1, 0, 0, 0]
    tail_sway = [-1, 0, 1, 1, 0, -1]

    def add_markings(surf):
        for i in range(3):
            rx = int(2 + rand01(seed + i, seed - i, 9991, salt=7) * 12)
            ry = int(3 + rand01(seed - i, seed + i, 8887, salt=9) * 10)
            if surf.get_at((rx, ry)).a > 0:
                px(surf, rx, ry, shade2)

    def draw_common(s, direction, b):
        body_x, body_y = 5, 7 + b
        head_x, head_y = 5, 2 + b
        draw_rect_px(s, body_x, body_y, 6, 6, basec)
        draw_rect_px(s, head_x, head_y, 6, 5, basec)

        if direction in ("down", "up"):
            px(s, head_x + 1, head_y + 0, basec)
            px(s, head_x + 4, head_y + 0, basec)
            px(s, head_x + 1, head_y + 1, shade2)
            px(s, head_x + 4, head_y + 1, shade2)
        else:
            px(s, head_x + 5, head_y + 1, shade2)
            px(s, head_x + 4, head_y + 0, basec)

    def draw_face(s, direction, b, blink=False):
        head_x, head_y = 5, 2 + b
        if direction == "down":
            if blink:
                px(s, head_x + 1, head_y + 2, shade1)
                px(s, head_x + 4, head_y + 2, shade1)
            else:
                px(s, head_x + 1, head_y + 2, eye)
                px(s, head_x + 1, head_y + 2, pupil)
                px(s, head_x + 4, head_y + 2, eye)
                px(s, head_x + 4, head_y + 2, pupil)
            px(s, head_x + 3, head_y + 3, nose)
        elif direction == "right":
            if blink:
                px(s, head_x + 5, head_y + 2, shade1)
            else:
                px(s, head_x + 5, head_y + 2, eye)
                px(s, head_x + 5, head_y + 2, pupil)
            px(s, head_x + 6, head_y + 3, nose)
        elif direction == "up":
            px(s, head_x + 2, head_y + 4, shade2)
            px(s, head_x + 3, head_y + 4, shade2)

    def draw_tail(s, direction, b, sway):
        body_x, body_y = 5, 7 + b
        if direction == "down":
            px(s, body_x - 1 + sway, body_y + 2, shade1)
            px(s, body_x - 2 + sway, body_y + 3, shade1)
            px(s, body_x - 2 + sway, body_y + 4, shade2)
        elif direction == "up":
            px(s, body_x + 5 + sway, body_y + 3, shade1)
            px(s, body_x + 6 + sway, body_y + 4, shade1)
            px(s, body_x + 6 + sway, body_y + 5, shade2)
        elif direction == "right":
            px(s, body_x - 1 + sway, body_y + 3, shade1)
            px(s, body_x - 2 + sway, body_y + 4, shade1)

    def draw_paws(s, direction, b, phase):
        body_x, body_y = 5, 7 + b
        paw_y = body_y + 5 + paw_y_off[phase]
        if direction in ("down", "up"):
            if paw_alt[phase] == 0:
                px(s, body_x + 1, paw_y, shade2)
                px(s, body_x + 4, paw_y - 1, shade2)
            else:
                px(s, body_x + 1, paw_y - 1, shade2)
                px(s, body_x + 4, paw_y, shade2)
        elif direction == "right":
            if paw_alt[phase] == 0:
                px(s, body_x + 2, paw_y - 1, shade2)
                px(s, body_x + 4, paw_y, shade2)
            else:
                px(s, body_x + 2, paw_y, shade2)
                px(s, body_x + 4, paw_y - 1, shade2)

    def draw_accent(s, direction, b):
        body_x, body_y = 5, 7 + b
        if direction == "down":
            px(s, body_x + 2, body_y + 3, accentc)
            px(s, body_x + 3, body_y + 3, accentc)
        elif direction == "up":
            px(s, body_x + 2, body_y + 2, accentc)
            px(s, body_x + 3, body_y + 2, accentc)
        elif direction == "right":
            px(s, body_x + 3, body_y + 3, accentc)

    def make_frame(direction, phase, blink=False, extra_idle_sway=0):
        s = make_surface_px(W, H)
        b = bob[phase]
        sway = tail_sway[phase] + extra_idle_sway
        draw_common(s, direction, b)
        draw_tail(s, direction, b, sway)
        draw_paws(s, direction, b, phase)
        draw_accent(s, direction, b)
        draw_face(s, direction, b, blink=blink)
        add_markings(s)
        return outline_from_alpha(s, (0, 0, 0, 255))

    walk = {
        "down": [make_frame("down", i) for i in range(6)],
        "up": [make_frame("up", i) for i in range(6)],
        "right": [make_frame("right", i) for i in range(6)],
    }
    walk["left"] = [pygame.transform.flip(f, True, False) for f in walk["right"]]

    idle = {}
    idle["down"] = [
        make_frame("down", 1, blink=False, extra_idle_sway=-1),
        make_frame("down", 1, blink=False, extra_idle_sway=0),
        make_frame("down", 1, blink=True, extra_idle_sway=0),
        make_frame("down", 1, blink=False, extra_idle_sway=1),
    ]
    idle["up"] = [
        make_frame("up", 1, blink=False, extra_idle_sway=-1),
        make_frame("up", 1, blink=False, extra_idle_sway=0),
        make_frame("up", 1, blink=False, extra_idle_sway=1),
        make_frame("up", 1, blink=False, extra_idle_sway=0),
    ]
    idle_right = [
        make_frame("right", 1, blink=False, extra_idle_sway=-1),
        make_frame("right", 1, blink=False, extra_idle_sway=0),
        make_frame("right", 1, blink=True, extra_idle_sway=0),
        make_frame("right", 1, blink=False, extra_idle_sway=1),
    ]
    idle["right"] = idle_right
    idle["left"] = [pygame.transform.flip(f, True, False) for f in idle_right]
    return walk, idle


def build_robot_sprites(kind="cat"):
    W, H = 16, 16
    metal = (150, 160, 172, 255)
    dark = (92, 98, 112, 255)
    bolt = (205, 215, 230, 255)
    glow = (255, 70, 90, 255) if kind == "cat" else (90, 200, 255, 255)

    bob = [0, 1, 0, 0]
    paw = [0, 1, 0, 1]
    tail = [-1, 0, 1, 0]

    def make(direction, phase, idle=False):
        s = make_surface_px(W, H)
        b = bob[phase] if not idle else 0

        if kind == "cat":
            body_x, body_y, body_w, body_h = 5, 7 + b, 6, 6
            head_x, head_y, head_w, head_h = 5, 2 + b, 6, 5
        else:
            body_x, body_y, body_w, body_h = 4, 8 + b, 8, 5
            head_x, head_y, head_w, head_h = 6, 3 + b, 6, 5

        draw_rect_px(s, body_x, body_y, body_w, body_h, metal)
        draw_rect_px(s, head_x, head_y, head_w, head_h, metal)

        px(s, body_x + 1, body_y + 2, dark)
        px(s, body_x + 3, body_y + 3, dark)
        px(s, head_x + 2, head_y + 1, dark)

        if kind == "cat":
            if direction in ("down", "up"):
                px(s, head_x + 1, head_y + 0, metal)
                px(s, head_x + 4, head_y + 0, metal)
                px(s, head_x + 1, head_y + 1, bolt)
                px(s, head_x + 4, head_y + 1, bolt)
            else:
                px(s, head_x + 5, head_y + 1, bolt)
                px(s, head_x + 4, head_y + 0, metal)
        else:
            if direction in ("down", "up"):
                px(s, head_x + 0, head_y + 2, dark)
                px(s, head_x + 5, head_y + 2, dark)
            else:
                px(s, head_x + 4, head_y + 3, dark)

        if direction == "down":
            px(s, head_x + 1, head_y + 2, glow)
            px(s, head_x + 4, head_y + 2, glow)
        elif direction == "right":
            px(s, head_x + 5, head_y + 2, glow)
        elif direction == "up":
            px(s, head_x + 2, head_y + 4, bolt)
            px(s, head_x + 3, head_y + 4, bolt)

        if not idle:
            py = body_y + body_h - 1
            if direction in ("down", "up"):
                if paw[phase] == 0:
                    px(s, body_x + 1, py, bolt)
                    px(s, body_x + body_w - 2, py - 1, bolt)
                else:
                    px(s, body_x + 1, py - 1, bolt)
                    px(s, body_x + body_w - 2, py, bolt)
            else:
                if paw[phase] == 0:
                    px(s, body_x + 2, py - 1, bolt)
                    px(s, body_x + 4, py, bolt)
                else:
                    px(s, body_x + 2, py, bolt)
                    px(s, body_x + 4, py - 1, bolt)

        if direction != "up":
            if kind == "cat":
                px(s, body_x - 1 + tail[phase], body_y + 3, dark)
                px(s, body_x - 2 + tail[phase], body_y + 4, dark)
            else:
                px(s, body_x - 1, body_y + 3, dark)

        return outline_from_alpha(s, (0, 0, 0, 255))

    def make_dir(direction):
        walk = [make(direction, i) for i in range(4)]
        idle = [make(direction, 0, idle=True), make(direction, 0, idle=True)]
        return walk, idle

    walk, idle = {}, {}
    for d in ("down", "up", "right"):
        w, i = make_dir(d)
        walk[d] = w
        idle[d] = i
    walk["left"] = [pygame.transform.flip(f, True, False) for f in walk["right"]]
    idle["left"] = [pygame.transform.flip(f, True, False) for f in idle["right"]]
    return walk, idle



def build_boss_sprites():
    # Bigger, darker boss cat with glowing eyes.
    W, H = 20, 20
    body = (70, 55, 86, 255)
    body2 = (95, 78, 112, 255)
    dark = (40, 30, 50, 255)
    gold = (255, 210, 110, 255)
    glow = (255, 80, 130, 255)

    def make(direction, phase, idle=False):
        s = make_surface_px(W, H)
        b = 1 if (phase % 2 == 0 and not idle) else 0

        draw_rect_px(s, 6, 9 + b, 8, 8, body)
        draw_rect_px(s, 7, 10 + b, 6, 6, body2)
        draw_rect_px(s, 6, 3 + b, 8, 6, body)
        draw_rect_px(s, 7, 4 + b, 6, 4, body2)

        px(s, 7, 2 + b, body2); px(s, 12, 2 + b, body2)
        px(s, 7, 3 + b, body);  px(s, 12, 3 + b, body)

        if direction == "down":
            px(s, 8, 6 + b, glow); px(s, 11, 6 + b, glow)
            px(s, 9, 7 + b, gold); px(s, 10, 7 + b, gold)
        elif direction == "right":
            px(s, 13, 6 + b, glow); px(s, 14, 7 + b, gold)
        elif direction == "up":
            px(s, 9, 8 + b, dark); px(s, 10, 8 + b, dark)

        if not idle:
            if direction in ("down", "up"):
                px(s, 7, 17 + b, gold); px(s, 12, 16 + b, gold)
            else:
                px(s, 10, 16 + b, gold); px(s, 12, 17 + b, gold)

        if direction != "up":
            px(s, 5, 13 + b, dark); px(s, 4, 14 + b, dark); px(s, 4, 15 + b, body2)

        return outline_from_alpha(s, (0, 0, 0, 255))

    def make_dir(direction):
        walk = [make(direction, i) for i in range(4)]
        idle = [make(direction, 0, idle=True), make(direction, 0, idle=True)]
        return walk, idle

    walk, idle = {}, {}
    for d in ("down", "up", "right"):
        w, i = make_dir(d)
        walk[d] = [scale_nearest(f, 4) for f in w]
        idle[d] = [scale_nearest(f, 4) for f in i]
    walk["left"] = [pygame.transform.flip(f, True, False) for f in walk["right"]]
    idle["left"] = [pygame.transform.flip(f, True, False) for f in idle["right"]]
    return walk, idle


def build_pickup_sprites(scale=3):
    catnip = pygame.Surface((18, 18), pygame.SRCALPHA)
    tuna = pygame.Surface((18, 18), pygame.SRCALPHA)
    whistle = pygame.Surface((18, 18), pygame.SRCALPHA)

    # Catnip leaf
    for i, col in enumerate([(40, 200, 90), (30, 160, 70), (60, 230, 120)]):
        pygame.draw.ellipse(catnip, col, pygame.Rect(4 + i, 2 + i, 9, 12))
    pygame.draw.circle(catnip, (0, 0, 0), (9, 10), 7, 2)

    # Tuna can
    pygame.draw.rect(tuna, (180, 190, 205), pygame.Rect(4, 6, 10, 9), border_radius=2)
    pygame.draw.rect(tuna, (110, 120, 135), pygame.Rect(4, 6, 10, 9), 2, border_radius=2)
    pygame.draw.rect(tuna, (230, 220, 120), pygame.Rect(5, 9, 8, 3), border_radius=2)
    pygame.draw.rect(tuna, (0, 0, 0), pygame.Rect(4, 6, 10, 9), 2, border_radius=2)

    # Cat Whistle (restores 1 fallen kitten)
    # Body
    pygame.draw.rect(whistle, (210, 210, 220), pygame.Rect(5, 6, 8, 8), border_radius=3)
    pygame.draw.rect(whistle, (90, 90, 105), pygame.Rect(5, 6, 8, 8), 2, border_radius=3)
    # Hole + mouth
    pygame.draw.circle(whistle, (40, 40, 50), (9, 10), 2)
    pygame.draw.rect(whistle, (230, 220, 120), pygame.Rect(12, 9, 3, 4), border_radius=2)
    pygame.draw.rect(whistle, (0, 0, 0), pygame.Rect(12, 9, 3, 4), 2, border_radius=2)
    # Lanyard loop
    pygame.draw.circle(whistle, (0, 0, 0), (6, 6), 2, 1)

    return (
        scale_nearest(outline_from_alpha(catnip), scale),
        scale_nearest(outline_from_alpha(tuna), scale),
        scale_nearest(outline_from_alpha(whistle), scale),
    )


def build_squirrel_sprite(scale=3):
    W, H = 14, 14
    s = make_surface_px(W, H)

    fur = (160, 112, 72, 255)
    fur2 = (132, 88, 56, 255)
    belly = (205, 168, 128, 255)
    eye = (20, 20, 22, 255)
    nose = (30, 22, 20, 255)

    # Tail (big and fluffy)
    for i in range(6):
        px(s, 2 + i, 4 - (i // 2), fur2 if (i % 2 == 0) else fur)
        px(s, 2 + i, 5 - (i // 2), fur)
        px(s, 2 + i, 6 - (i // 2), fur)

    # Body
    draw_rect_px(s, 6, 7, 5, 5, fur)
    draw_rect_px(s, 7, 8, 3, 3, belly)

    # Head
    draw_rect_px(s, 7, 4, 4, 3, fur)
    px(s, 8, 5, eye)
    px(s, 10, 5, eye)
    px(s, 9, 6, nose)

    # Ears
    px(s, 7, 3, fur2)
    px(s, 10, 3, fur2)

    # Paws
    px(s, 7, 12, fur2)
    px(s, 9, 12, fur2)

    return scale_nearest(outline_from_alpha(s), scale)


def draw_tree(surf, x, y, seedv):
    rng = random.Random(int(seedv * 10_000_000) ^ 0xA51CE)

    trunk_main = (112, 80, 52)
    trunk_dark = (84, 60, 40)
    trunk_light = (140, 104, 72)

    leaf1 = (22, 118, 56)
    leaf2 = (18, 92, 44)
    leaf3 = (34, 152, 72)

    outline = (0, 0, 0)

    height = rng.randint(34, 46)
    base_w = rng.randint(6, 8)

    curve = rng.choice([-1, 1])
    kink1 = rng.randint(height // 3, height // 2)
    kink2 = rng.randint(height // 2, int(height * 0.85))

    points = []
    for i in range(height):
        t = i / max(1, height - 1)
        w = int(round(base_w * (1.0 - 0.45 * t)))
        w = max(3, w)

        off = 0
        if i > kink1:
            off += curve
        if i > kink2:
            off += curve

        pxc = x + off
        pyc = y - i
        points.append((pxc, pyc, w))

    for (pxc, pyc, w) in points:
        rect = pygame.Rect(pxc - w // 2, pyc, w, 1)
        pygame.draw.rect(surf, trunk_dark, rect.move(1, 1))
        pygame.draw.rect(surf, trunk_main, rect)
        if (pyc % 6) == 0 and w >= 4:
            pygame.draw.line(surf, trunk_light, (pxc - w // 2 + 1, pyc), (pxc - w // 2 + 1, pyc), 1)

    pygame.draw.line(surf, outline, (x - base_w // 2 - 2, y - height + 6), (x - base_w // 2 - 2, y), 2)
    pygame.draw.line(surf, outline, (x + base_w // 2 + 2, y - height + 6), (x + base_w // 2 + 2, y), 2)

    branch_count = rng.randint(2, 3)
    branch_ends = []
    for _ in range(branch_count):
        bi = rng.randint(int(height * 0.35), int(height * 0.78))
        bx, by, bw = points[bi]
        dirx = rng.choice([-1, 1])
        blen = rng.randint(12, 18)
        bend = rng.randint(-3, 3)

        ex = bx + dirx * blen
        ey = by - rng.randint(2, 6) + bend

        thickness = 3 if bw >= 5 else 2
        pygame.draw.line(surf, trunk_dark, (bx + 1, by + 1), (ex + 1, ey + 1), thickness)
        pygame.draw.line(surf, trunk_main, (bx, by), (ex, ey), thickness)
        branch_ends.append((ex, ey))

    def leaf_cluster(cx0, cy0, radius):
        for _ in range(4):
            col = rng.choice([leaf1, leaf2, leaf3])
            ox = rng.randint(-radius, radius)
            oy = rng.randint(-radius, radius)
            rr = max(7, radius + rng.randint(-2, 2))
            pygame.draw.circle(surf, col, (cx0 + ox, cy0 + oy), rr)
            pygame.draw.circle(surf, outline, (cx0 + ox, cy0 + oy), rr, 2)

    topx, topy, _ = points[-1]
    leaf_cluster(topx, topy - 6, rng.randint(10, 14))
    leaf_cluster(topx - rng.randint(6, 10), topy - 2, rng.randint(9, 12))
    leaf_cluster(topx + rng.randint(6, 10), topy - 2, rng.randint(9, 12))
    for ex, ey in branch_ends:
        leaf_cluster(ex, ey, rng.randint(8, 11))


def draw_bush(surf, x, y, seedv):
    b1 = (22, 116, 58)
    b2 = (18, 88, 44)
    b3 = (32, 144, 70)
    r = 10 + int((seedv * 9) % 3)
    for i, (ox, oy) in enumerate(((-8, 0), (0, -3), (8, 0))):
        col = b1 if i == 0 else (b2 if i == 1 else b3)
        pygame.draw.circle(surf, col, (x + ox, y + oy), r)
        pygame.draw.circle(surf, (0, 0, 0), (x + ox, y + oy), r, 2)


def draw_flower_patch(surf, x, y, seedv):
    petal = (250, 190, 220)
    petal2 = (255, 230, 160)
    center = (255, 240, 140)
    stem = (30, 140, 70)

    for i in range(3):
        sx = x + (i - 1) * 7
        pygame.draw.line(surf, stem, (sx, y), (sx, y - 10), 3)

    for i in range(3):
        bx = x + (i - 1) * 7
        by = y - 12
        col = petal if (int(seedv * 100) + i) % 2 == 0 else petal2
        pygame.draw.circle(surf, col, (bx, by), 6)
        pygame.draw.circle(surf, (0, 0, 0), (bx, by), 6, 2)
        pygame.draw.circle(surf, center, (bx, by), 2)


def draw_stone(surf, x, y, seedv):
    c1 = (120, 130, 140)
    c2 = (90, 98, 108)
    r = 7 + int((seedv * 11) % 3)
    pygame.draw.circle(surf, c2, (x + 1, y + 1), r)
    pygame.draw.circle(surf, c1, (x, y), r)
    pygame.draw.circle(surf, (0, 0, 0), (x, y), r, 2)



class GrassWorld:
    """
    Infinite chunked overworld with smooth biome blending along +X.
    The underlying topology (water/land noise) remains consistent; palettes + props blend.
    """

    BIOME_PALETTES = {
        "grass": {
            "land": (22, 74, 30),
            "dirt": (64, 86, 44),
            "detail": (24, 92, 38),
            "accent": (255, 225, 170),
            "accent2": (255, 190, 220),
            "blade": (12, 80, 28),
            "water": (20, 140, 150),
            "water_hi": (35, 165, 182),
            "rock": (120, 126, 122),
        },
        "desert": {
            "land": (176, 150, 84),
            "dirt": (160, 132, 70),
            "detail": (200, 176, 110),
            "accent": (255, 238, 190),
            "accent2": (245, 210, 160),
            "blade": (176, 150, 84),
            "water": (26, 132, 152),
            "water_hi": (44, 160, 178),
            "rock": (154, 144, 128),
        },
        "snow": {
            "land": (224, 232, 242),
            "dirt": (198, 210, 228),
            "detail": (242, 248, 255),
            "accent": (255, 255, 255),
            "accent2": (210, 230, 255),
            "blade": (210, 222, 240),
            "water": (40, 128, 178),
            "water_hi": (70, 160, 210),
            "rock": (170, 178, 186),
        },
        "mountain": {
            "land": (92, 98, 92),
            "dirt": (72, 78, 72),
            "detail": (118, 126, 118),
            "accent": (210, 210, 210),
            "accent2": (180, 180, 180),
            "blade": (88, 98, 88),
            "water": (28, 118, 150),
            "water_hi": (52, 142, 176),
            "rock": (134, 138, 134),
        },
        "jungle": {
            "land": (18, 64, 28),
            "dirt": (50, 72, 40),
            "detail": (28, 108, 52),
            "accent": (210, 255, 200),
            "accent2": (150, 240, 190),
            "blade": (16, 92, 40),
            "water": (18, 120, 98),
            "water_hi": (34, 148, 120),
            "rock": (102, 110, 102),
        },
        "swamp": {
            "land": (34, 56, 36),
            "dirt": (60, 66, 46),
            "detail": (22, 88, 58),
            "accent": (210, 240, 210),
            "accent2": (170, 220, 190),
            "blade": (20, 90, 60),
            "water": (18, 96, 76),
            "water_hi": (34, 122, 98),
            "rock": (100, 98, 88),
        },
        "beach": {
            "land": (210, 190, 120),
            "dirt": (190, 170, 100),
            "detail": (230, 210, 140),
            "accent": (255, 248, 210),
            "accent2": (240, 225, 190),
            "blade": (210, 190, 120),
            "water": (18, 152, 192),
            "water_hi": (40, 188, 224),
            "rock": (156, 148, 132),
        },
    }

    def __init__(self, seed=1337):
        self.seed = seed
        self.chunk_cache = {}
        self._cache_touch = {}

    def world_to_chunk(self, wx, wy):
        return math.floor(wx / CHUNK_PX), math.floor(wy / CHUNK_PX)

    def biome_mix(self, wx_px):
        """
        Returns (b0, b1, t) where t is the smooth blend from b0 -> b1.
        Biomes advance as wx increases.
        """
        band = float(BIOME_BAND_PX)
        blend = max(1.0, float(BIOME_BLEND_PX))
        idx = math.floor(wx_px / band)
        local = wx_px - idx * band  # [0, band)
        b0 = BIOME_ORDER[int(idx) % len(BIOME_ORDER)]
        b1 = BIOME_ORDER[int(idx + 1) % len(BIOME_ORDER)]

        # Transition during last "blend" portion of the band.
        x0 = band - blend
        if local <= x0:
            t = 0.0
        else:
            t = (local - x0) / blend
            t = max(0.0, min(1.0, t))
            t = smoothstep(t)
        return b0, b1, t

    @staticmethod
    def _clamp255(v):
        return 0 if v < 0 else 255 if v > 255 else int(v)

    @classmethod
    def _lerp_col(cls, c0, c1, t):
        return (
            cls._clamp255(c0[0] + (c1[0] - c0[0]) * t),
            cls._clamp255(c0[1] + (c1[1] - c0[1]) * t),
            cls._clamp255(c0[2] + (c1[2] - c0[2]) * t),
        )

    def _pal_at_x(self, wx_px):
        b0, b1, t = self.biome_mix(wx_px)
        p0 = self.BIOME_PALETTES[b0]
        p1 = self.BIOME_PALETTES[b1]
        out = {}
        for k in p0.keys():
            out[k] = self._lerp_col(p0[k], p1[k], t)
        out["_b0"] = b0
        out["_b1"] = b1
        out["_t"] = t
        return out

    def _is_water(self, gx, gy):
        # gx, gy are in tile coordinates.
        # Ponds: low frequency noise + a second noise gate for sharper clusters.
        pond = value_noise(gx, gy, 8, seed=self.seed, salt=201)
        pond2 = value_noise(gx, gy, 4, seed=self.seed, salt=202)
        pond_ok = (pond > WATER_POND_THRESHOLD) and (pond2 > 0.48)

        # Rivers: periodic, sin-warped bands so they recur across infinite travel.
        d = river_distance(gx, gy, seed=self.seed)
        wj = value_noise(gx, gy, 5, seed=self.seed, salt=207)
        half_w = WATER_RIVER_BASE_HALF_WIDTH + (wj - 0.5) * 0.8
        river_ok = abs(d) < half_w

        return pond_ok or river_ok

    # --- Biome props (lightweight pixel primitives) ---

    @staticmethod
    def _outline_rect(surf, rect, fill, outline=(0, 0, 0)):
        pygame.draw.rect(surf, fill, rect)
        pygame.draw.rect(surf, outline, rect, 1)

    def _draw_cactus(self, surf, x, y, rng):
        outline = (0, 0, 0)
        g1 = (46, 142, 84)
        g2 = (30, 110, 64)
        h = rng.randint(18, 26)
        w = rng.randint(5, 7)
        trunk = pygame.Rect(x - w // 2, y - h, w, h)
        pygame.draw.rect(surf, g1, trunk)
        pygame.draw.rect(surf, outline, trunk, 1)
        if rng.random() < 0.75:
            arm_h = rng.randint(8, 12)
            arm_w = max(3, w - 2)
            side = rng.choice([-1, 1])
            arm = pygame.Rect(x + side * (w // 2), y - h + rng.randint(6, 12), arm_w, arm_h)
            pygame.draw.rect(surf, g2, arm)
            pygame.draw.rect(surf, outline, arm, 1)

    def _draw_pine(self, surf, x, y, rng):
        outline = (0, 0, 0)
        trunk = pygame.Rect(x - 2, y - 10, 4, 10)
        pygame.draw.rect(surf, (112, 80, 52), trunk)
        pygame.draw.rect(surf, outline, trunk, 1)
        # layered triangles
        for i in range(3):
            w = 18 - i * 4
            h = 10 - i * 2
            top = y - 10 - i * 6 - h
            pts = [(x, top), (x - w // 2, top + h), (x + w // 2, top + h)]
            col = (48, 120, 76) if i == 0 else (34, 100, 64)
            pygame.draw.polygon(surf, col, pts)
            pygame.draw.polygon(surf, outline, pts, 1)

    def _draw_palm(self, surf, x, y, rng):
        outline = (0, 0, 0)
        # trunk
        h = rng.randint(20, 28)
        for i in range(h):
            dx = int(math.sin(i * 0.22) * 2.0)
            surf.set_at((x + dx, y - i), (132, 96, 60))
            if rng.random() < 0.4:
                surf.set_at((x + dx + 1, y - i), (160, 120, 72))
            surf.set_at((x + dx, y - i), (132, 96, 60))
        # outline-ish
        for i in range(h):
            dx = int(math.sin(i * 0.22) * 2.0)
            if 0 <= x + dx - 1 < CHUNK_PX:
                surf.set_at((x + dx - 1, y - i), outline)
            if 0 <= x + dx + 1 < CHUNK_PX:
                surf.set_at((x + dx + 1, y - i), outline)

        # fronds
        topy = y - h
        for k in range(rng.randint(4, 6)):
            ang = rng.uniform(-2.5, 2.5)
            length = rng.randint(14, 20)
            for i in range(length):
                px = x + int(math.cos(ang) * i)
                py = topy + int(math.sin(ang) * i * 0.6)
                if 0 <= px < CHUNK_PX and 0 <= py < CHUNK_PX:
                    surf.set_at((px, py), (42, 156, 96))
                    if rng.random() < 0.15:
                        surf.set_at((px, py), outline)

    def _draw_reeds(self, surf, x, y, rng):
        outline = (0, 0, 0)
        col = (22, 116, 78)
        for i in range(rng.randint(3, 5)):
            h = rng.randint(10, 18)
            dx = rng.randint(-5, 5)
            pygame.draw.line(surf, col, (x + dx, y), (x + dx, y - h), 2)
            pygame.draw.line(surf, outline, (x + dx - 1, y), (x + dx - 1, y - h), 1)

    def _draw_snow_pile(self, surf, x, y, rng):
        outline = (0, 0, 0)
        w = rng.randint(10, 16)
        h = rng.randint(5, 7)
        rect = pygame.Rect(x - w // 2, y - h, w, h)
        pygame.draw.ellipse(surf, (245, 250, 255), rect)
        pygame.draw.ellipse(surf, outline, rect, 1)

    def _draw_driftwood(self, surf, x, y, rng):
        outline = (0, 0, 0)
        col = (138, 110, 76)
        length = rng.randint(10, 18)
        angle = rng.uniform(-0.8, 0.8)
        for i in range(length):
            px = x + int(math.cos(angle) * i)
            py = y - int(math.sin(angle) * i * 0.4)
            if 0 <= px < CHUNK_PX and 0 <= py < CHUNK_PX:
                surf.set_at((px, py), col)
                if rng.random() < 0.25:
                    surf.set_at((px, py), outline)

    def _apply_biome_props(self, surf, water, cx, cy):
        # Decide props by chunk-center blend.
        wx_center = cx * CHUNK_PX + CHUNK_PX * 0.5
        b0, b1, t = self.biome_mix(wx_center)
        w0 = 1.0 - t
        w1 = t

        def rnd(seed_add):
            return rand01(cx, cy, self.seed, salt=seed_add)

        rng0 = random.Random(int((cx * 73856093) ^ (cy * 19349663) ^ (self.seed * 83492791) ^ 0xB10AE))
        rng1 = random.Random(int((cx * 83492791) ^ (cy * 2654435761) ^ (self.seed * 19349663) ^ 0xB10AE2))

        margin = 16

        def place_ok(px, py):
            tx = int(px // TILE)
            ty = int(py // TILE)
            if 0 <= tx < CHUNK_TILES and 0 <= ty < CHUNK_TILES:
                return not water[ty][tx]
            return True

        def do_props_for(biome, weight, rng):
            if weight <= 0.01:
                return

            # Scale counts by weight (and biome flavor)
            if biome == "grass":
                n_trees = int((2 + int(rnd(10) * 3)) * weight)
                n_bushes = int((3 + int(rnd(11) * 4)) * weight)
                n_flowers = int((2 + int(rnd(12) * 3)) * weight)
                n_stones = int((2 + int(rnd(13) * 3)) * weight)
                for i in range(n_trees):
                    rx = margin + int(rng.random() * (CHUNK_PX - 2 * margin))
                    ry = margin + int(rng.random() * (CHUNK_PX - 2 * margin))
                    if place_ok(rx, ry):
                        draw_tree(surf, rx, ry, rng.random())
                for i in range(n_bushes):
                    rx = margin + int(rng.random() * (CHUNK_PX - 2 * margin))
                    ry = margin + int(rng.random() * (CHUNK_PX - 2 * margin))
                    if place_ok(rx, ry):
                        draw_bush(surf, rx, ry, rng.random())
                for i in range(n_flowers):
                    rx = margin + int(rng.random() * (CHUNK_PX - 2 * margin))
                    ry = margin + int(rng.random() * (CHUNK_PX - 2 * margin))
                    if place_ok(rx, ry):
                        draw_flower_patch(surf, rx, ry, rng.random())
                for i in range(n_stones):
                    rx = margin + int(rng.random() * (CHUNK_PX - 2 * margin))
                    ry = margin + int(rng.random() * (CHUNK_PX - 2 * margin))
                    if place_ok(rx, ry):
                        draw_stone(surf, rx, ry, rng.random())

            elif biome == "desert":
                n_cacti = int((2 + int(rng.random() * 4)) * weight)
                n_stones = int((2 + int(rng.random() * 4)) * weight)
                for _ in range(n_cacti):
                    rx = margin + int(rng.random() * (CHUNK_PX - 2 * margin))
                    ry = margin + int(rng.random() * (CHUNK_PX - 2 * margin))
                    if place_ok(rx, ry):
                        self._draw_cactus(surf, rx, ry, rng)
                for _ in range(n_stones):
                    rx = margin + int(rng.random() * (CHUNK_PX - 2 * margin))
                    ry = margin + int(rng.random() * (CHUNK_PX - 2 * margin))
                    if place_ok(rx, ry):
                        draw_stone(surf, rx, ry, rng.random())

            elif biome == "snow":
                n_pine = int((2 + int(rng.random() * 3)) * weight)
                n_piles = int((2 + int(rng.random() * 4)) * weight)
                for _ in range(n_pine):
                    rx = margin + int(rng.random() * (CHUNK_PX - 2 * margin))
                    ry = margin + int(rng.random() * (CHUNK_PX - 2 * margin))
                    if place_ok(rx, ry):
                        self._draw_pine(surf, rx, ry, rng)
                for _ in range(n_piles):
                    rx = margin + int(rng.random() * (CHUNK_PX - 2 * margin))
                    ry = margin + int(rng.random() * (CHUNK_PX - 2 * margin))
                    if place_ok(rx, ry):
                        self._draw_snow_pile(surf, rx, ry, rng)

            elif biome == "mountain":
                n_stones = int((4 + int(rng.random() * 6)) * weight)
                for _ in range(n_stones):
                    rx = margin + int(rng.random() * (CHUNK_PX - 2 * margin))
                    ry = margin + int(rng.random() * (CHUNK_PX - 2 * margin))
                    if place_ok(rx, ry):
                        draw_stone(surf, rx, ry, rng.random())

            elif biome == "jungle":
                n_trees = int((3 + int(rng.random() * 5)) * weight)
                n_reeds = int((2 + int(rng.random() * 3)) * weight)
                for _ in range(n_trees):
                    rx = margin + int(rng.random() * (CHUNK_PX - 2 * margin))
                    ry = margin + int(rng.random() * (CHUNK_PX - 2 * margin))
                    if place_ok(rx, ry):
                        # Use the existing tree (looks fine for jungle), plus extra reeds.
                        draw_tree(surf, rx, ry, rng.random())
                for _ in range(n_reeds):
                    rx = margin + int(rng.random() * (CHUNK_PX - 2 * margin))
                    ry = margin + int(rng.random() * (CHUNK_PX - 2 * margin))
                    if place_ok(rx, ry):
                        self._draw_reeds(surf, rx, ry, rng)

            elif biome == "swamp":
                n_reeds = int((4 + int(rng.random() * 6)) * weight)
                n_logs = int((2 + int(rng.random() * 3)) * weight)
                for _ in range(n_reeds):
                    rx = margin + int(rng.random() * (CHUNK_PX - 2 * margin))
                    ry = margin + int(rng.random() * (CHUNK_PX - 2 * margin))
                    if place_ok(rx, ry):
                        self._draw_reeds(surf, rx, ry, rng)
                for _ in range(n_logs):
                    rx = margin + int(rng.random() * (CHUNK_PX - 2 * margin))
                    ry = margin + int(rng.random() * (CHUNK_PX - 2 * margin))
                    if place_ok(rx, ry):
                        self._draw_driftwood(surf, rx, ry, rng)

            elif biome == "beach":
                n_palms = int((1 + int(rng.random() * 3)) * weight)
                n_drift = int((2 + int(rng.random() * 4)) * weight)
                for _ in range(n_palms):
                    rx = margin + int(rng.random() * (CHUNK_PX - 2 * margin))
                    ry = margin + int(rng.random() * (CHUNK_PX - 2 * margin))
                    if place_ok(rx, ry):
                        self._draw_palm(surf, rx, ry, rng)
                for _ in range(n_drift):
                    rx = margin + int(rng.random() * (CHUNK_PX - 2 * margin))
                    ry = margin + int(rng.random() * (CHUNK_PX - 2 * margin))
                    if place_ok(rx, ry):
                        self._draw_driftwood(surf, rx, ry, rng)

        # Apply in both biomes based on blend weights
        do_props_for(b0, w0, rng0)
        do_props_for(b1, w1, rng1)

    def gen_chunk_surface(self, cx, cy):
        surf = pygame.Surface((CHUNK_PX, CHUNK_PX))
        # Fill with the approximate land color for this chunk (prevents edge gaps).
        wx_center = cx * CHUNK_PX + CHUNK_PX * 0.5
        pal_center = self._pal_at_x(wx_center)
        surf.fill(pal_center["land"])

        # Precompute water flags for edge shading within this chunk.
        water = [[False for _ in range(CHUNK_TILES)] for _ in range(CHUNK_TILES)]
        for ty in range(CHUNK_TILES):
            for tx in range(CHUNK_TILES):
                gx = cx * CHUNK_TILES + tx
                gy = cy * CHUNK_TILES + ty
                water[ty][tx] = self._is_water(gx, gy)

        for ty in range(CHUNK_TILES):
            for tx in range(CHUNK_TILES):
                gx = cx * CHUNK_TILES + tx
                gy = cy * CHUNK_TILES + ty
                wx_px = gx * TILE + TILE * 0.5
                pal = self._pal_at_x(wx_px)

                rect = pygame.Rect(tx * TILE, ty * TILE, TILE, TILE)

                r = value_noise(gx, gy, 6, seed=self.seed, salt=9)

                if water[ty][tx]:
                    # Water base color with subtle variation, palette-blended.
                    n0 = value_noise(gx, gy, 3, seed=self.seed, salt=301)
                    n1 = rand01(gx, gy, self.seed, salt=302)

                    base = pal["water"]
                    hi = pal["water_hi"]
                    col = (
                        self._clamp255(base[0] + (n0 - 0.5) * 18),
                        self._clamp255(base[1] + (n1 - 0.5) * 34),
                        self._clamp255(base[2] + (n0 - 0.5) * 28),
                    )
                    pygame.draw.rect(surf, col, rect)

                    # Gentle ripples
                    if n1 > 0.72:
                        pygame.draw.rect(surf, hi, rect.inflate(-TILE // 2, -TILE // 2))

                    # Edge shading where adjacent tiles are land.
                    edge_col = (0, 0, 0)
                    if tx > 0 and not water[ty][tx - 1]:
                        pygame.draw.rect(surf, edge_col, pygame.Rect(rect.left, rect.top, 3, rect.height))
                    if tx < CHUNK_TILES - 1 and not water[ty][tx + 1]:
                        pygame.draw.rect(surf, edge_col, pygame.Rect(rect.right - 3, rect.top, 3, rect.height))
                    if ty > 0 and not water[ty - 1][tx]:
                        pygame.draw.rect(surf, edge_col, pygame.Rect(rect.left, rect.top, rect.width, 3))
                    if ty < CHUNK_TILES - 1 and not water[ty + 1][tx]:
                        pygame.draw.rect(surf, edge_col, pygame.Rect(rect.left, rect.bottom - 3, rect.width, 3))

                    # Occasional lily pads / reeds (more in swamp/jungle)
                    if n0 > 0.78 and n1 > 0.55:
                        # Use a tile-local biome weight to bias these features.
                        if pal["_b0"] in ("swamp", "jungle") or pal["_b1"] in ("swamp", "jungle"):
                            if rand01(gx, gy, self.seed, salt=333) > 0.55:
                                pad = rect.inflate(-TILE // 2, -TILE // 2)
                                pygame.draw.ellipse(surf, (24, 140, 96), pad)
                                pygame.draw.ellipse(surf, (0, 0, 0), pad, 1)

                else:
                    # Land tile: biome-blended ground with dirt patches and micro detail.
                    base = pal["land"]
                    # variance keeps the world from looking flat; intensity depends on biome
                    var = (r - 0.5)
                    amp = 24.0 if pal["_b0"] in ("desert", "beach", "snow") or pal["_b1"] in ("desert", "beach", "snow") else 18.0
                    gcol = (
                        self._clamp255(base[0] + var * amp),
                        self._clamp255(base[1] + var * (amp * 0.9)),
                        self._clamp255(base[2] + var * (amp * 0.8)),
                    )
                    pygame.draw.rect(surf, gcol, rect)

                    dirt = value_noise(gx, gy, 5, seed=self.seed, salt=210)
                    if dirt > 0.84:
                        pygame.draw.rect(surf, pal["dirt"], rect.inflate(-TILE // 3, -TILE // 3))
                    if r > 0.92:
                        pygame.draw.rect(surf, pal["detail"], rect.inflate(-TILE // 2, -TILE // 2))

                    # Small highlights (pebbles / flowers / snow sparkle)
                    rf = rand01(gx, gy, self.seed, salt=7)
                    if rf > 0.994:
                        fx = tx * TILE + TILE // 2
                        fy = ty * TILE + TILE // 2
                        surf.set_at((fx, fy), pal["accent"])
                        if 0 <= fx + 1 < CHUNK_PX:
                            surf.set_at((fx + 1, fy), pal["accent2"])

                    # Texture blades / grains: suppress in mountain/snow, boost in jungle/swamp
                    blade_bias = 0.02
                    if pal["_b0"] in ("mountain", "snow") and pal["_t"] < 0.6:
                        blade_bias = 0.008
                    if pal["_b0"] in ("jungle", "swamp") or pal["_b1"] in ("jungle", "swamp"):
                        blade_bias = 0.03

                    if rf < blade_bias:
                        bx = tx * TILE + 6 + int((rf * 1000) % 8)
                        by = ty * TILE + 8 + int((r * 1000) % 8)
                        pygame.draw.line(surf, pal["blade"], (bx, by + 6), (bx, by), 2)

        # Biome props (trees/cacti/pines/etc) layered on top.
        self._apply_biome_props(surf, water, cx, cy)

        return surf

    def get_chunk(self, cx, cy):
        k = (cx, cy)
        if k not in self.chunk_cache:
            self.chunk_cache[k] = self.gen_chunk_surface(cx, cy)
        self._cache_touch[k] = pygame.time.get_ticks()

        # Bounded cache: evict least-recently-touched chunks.
        if len(self.chunk_cache) > WORLD_CHUNK_CACHE_LIMIT:
            # Remove oldest ~10% to amortize cost.
            n_evict = max(1, int(WORLD_CHUNK_CACHE_LIMIT * 0.1))
            oldest = sorted(self._cache_touch.items(), key=lambda kv: kv[1])[:n_evict]
            for kk, _ in oldest:
                self.chunk_cache.pop(kk, None)
                self._cache_touch.pop(kk, None)

        return self.chunk_cache[k]

    def draw(self, screen, camera):
        left, top = camera.x, camera.y
        right, bottom = camera.x + SCREEN_W, camera.y + SCREEN_H
        cmin = self.world_to_chunk(left, top)
        cmax = self.world_to_chunk(right, bottom)

        for cy in range(cmin[1] - 1, cmax[1] + 2):
            for cx in range(cmin[0] - 1, cmax[0] + 2):
                ch = self.get_chunk(cx, cy)
                x = int(cx * CHUNK_PX - camera.x)
                y = int(cy * CHUNK_PX - camera.y)
                screen.blit(ch, (x, y))

class Pickup:
    def __init__(self, pid, kind, pos):
        self.id = pid
        self.kind = kind  # "catnip", "tuna", or "whistle"
        self.pos = pygame.Vector2(pos)


class CatTower:
    def __init__(self, tid, pos):
        self.id = tid
        self.pos = pygame.Vector2(pos)
        self.radius = TOWER_RADIUS

    def draw(self, surf, camera, cleared=False):
        sx = int(self.pos.x - camera.x)
        sy = int(self.pos.y - camera.y)

        w, h = 64, 84
        body = pygame.Rect(sx - w // 2, sy - h // 2, w, h)
        pygame.draw.rect(surf, (0, 0, 0), body.inflate(6, 6), border_radius=16)
        pygame.draw.rect(surf, (120, 102, 86), body, border_radius=16)
        pygame.draw.rect(surf, (80, 66, 56), body, 3, border_radius=16)
        pygame.draw.rect(surf, (140, 120, 100), pygame.Rect(body.x + 6, body.y + 8, w - 12, h - 16), 2, border_radius=14)

        hole_r = 10
        offsets = [(-14, -10), (14, -10), (-14, 16), (14, 16)]
        for ox, oy in offsets:
            pygame.draw.circle(surf, (0, 0, 0), (sx + ox, sy + oy), hole_r + 2)
            pygame.draw.circle(surf, (20, 20, 24), (sx + ox, sy + oy), hole_r)

        pygame.draw.ellipse(surf, (0, 0, 0), pygame.Rect(sx - w // 2 - 3, body.y - 12, w + 6, 26), 3)
        pygame.draw.ellipse(surf, (150, 130, 110), pygame.Rect(sx - w // 2, body.y - 10, w, 22), 0)

        if cleared:
            pygame.draw.circle(surf, (0, 0, 0), (sx, sy + h // 2 + 18), 14, 3)
            pygame.draw.circle(surf, (255, 210, 110), (sx, sy + h // 2 + 18), 12, 3)
class Squirrel:
    def __init__(self, sid, pos, seedv):
        self.id = sid
        self.pos = pygame.Vector2(pos)
        self.vel = pygame.Vector2(0, 0)
        self.radius = SQUIRREL_RADIUS
        self.rng = random.Random(seedv ^ 0x51A11CE)
        ang = self.rng.random() * math.tau
        self.wander_dir = pygame.Vector2(math.cos(ang), math.sin(ang))
        self.wander_t = 0.6 + self.rng.random() * 1.2

    def update(self, dt, kittens):
        # Choose nearest kitten (any team member can chase).
        nearest = None
        best_d2 = 1e18
        for k in kittens:
            if k.down_timer > 0:
                k.z = 0.0
                k.vz = 0.0
                continue
            d2 = (k.pos - self.pos).length_squared()
            if d2 < best_d2:
                best_d2 = d2
                nearest = k

        desired = pygame.Vector2(0, 0)
        speed = SQUIRREL_WANDER_SPEED

        if nearest is not None and best_d2 <= (SQUIRREL_FEAR_RADIUS * SQUIRREL_FEAR_RADIUS):
            away = self.pos - nearest.pos
            if away.length_squared() == 0:
                away = pygame.Vector2(1, 0)
            desired = away.normalize()
            speed = SQUIRREL_RUN_SPEED
        else:
            self.wander_t -= dt
            if self.wander_t <= 0:
                self.wander_t = 0.7 + self.rng.random() * 1.4
                ang = self.rng.random() * math.tau
                self.wander_dir = pygame.Vector2(math.cos(ang), math.sin(ang))
            desired = pygame.Vector2(self.wander_dir)

        target_v = desired * speed
        self.vel += (target_v - self.vel) * min(1.0, dt * SQUIRREL_TURN_RATE)
        self.vel = clamp_vec(self.vel, 520.0)
        self.pos += self.vel * dt

    def draw(self, surf, camera, img):
        x = int(self.pos.x - camera.x - img.get_width() // 2)
        y = int(self.pos.y - camera.y - img.get_height() // 2)
        surf.blit(img, (x, y))






class Dungeon:
    def __init__(self, seed):
        self.seed = seed
        self.rng = random.Random(seed ^ 0xDA7A1CE)
        self.w = DUNGEON_W
        self.h = DUNGEON_H
        self.grid = [[DUNGEON_WALL for _ in range(self.w)] for _ in range(self.h)]

        self.start_cell = (1, 1)
        self.exit_cell = (3, 3)
        self.boss_cell = (self.w - 2, self.h - 2)

        # Widen corridors so the maze feels more open
        self._widen_passages(passes=1)

        self.floor_cells = []
        self._generate()
        self._build_tiles()

    def in_bounds(self, x, y):
        return 0 <= x < self.w and 0 <= y < self.h

    def _carve(self, x, y):
        self.grid[y][x] = DUNGEON_FLOOR

    def _generate_maze(self):
        for y in range(self.h):
            for x in range(self.w):
                self.grid[y][x] = DUNGEON_WALL

        sx, sy = self.start_cell
        self._carve(sx, sy)
        stack = [(sx, sy)]
        dirs = [(2, 0), (-2, 0), (0, 2), (0, -2)]

        while stack:
            x, y = stack[-1]
            self.rng.shuffle(dirs)
            carved = False
            for dx, dy in dirs:
                nx, ny = x + dx, y + dy
                if not self.in_bounds(nx, ny):
                    continue
                if self.grid[ny][nx] == DUNGEON_WALL:
                    self._carve(x + dx // 2, y + dy // 2)
                    self._carve(nx, ny)
                    stack.append((nx, ny))
                    carved = True
                    break
            if not carved:
                stack.pop()

    def _clear_rect(self, cx, cy, rw, rh):
        for y in range(cy - rh // 2, cy + rh // 2 + 1):
            for x in range(cx - rw // 2, cx + rw // 2 + 1):
                if 1 <= x < self.w - 1 and 1 <= y < self.h - 1:
                    self.grid[y][x] = DUNGEON_FLOOR


    def _widen_passages(self, passes=1):
        # Make the dungeon feel more "open" by thickening corridors and
        # knocking out thin wall spikes. Keeps borders intact.
        for _ in range(passes):
            new = [row[:] for row in self.grid]
            for y in range(1, self.h - 1):
                for x in range(1, self.w - 1):
                    if self.grid[y][x] == DUNGEON_FLOOR:
                        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                            new[y + dy][x + dx] = DUNGEON_FLOOR
                        # Occasionally soften corners
                        if self.rng.random() < 0.35:
                            for dx, dy in ((1, 1), (1, -1), (-1, 1), (-1, -1)):
                                new[y + dy][x + dx] = DUNGEON_FLOOR
            self.grid = new

        # Remove skinny wall spikes to increase sight-lines
        for y in range(1, self.h - 1):
            for x in range(1, self.w - 1):
                if self.grid[y][x] != DUNGEON_WALL:
                    continue
                n = 0
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    if self.grid[y + dy][x + dx] == DUNGEON_FLOOR:
                        n += 1
                if n >= 3 and self.rng.random() < 0.55:
                    self.grid[y][x] = DUNGEON_FLOOR


    def _bfs_farthest(self, start):
        from collections import deque
        q = deque([start])
        dist = {start: 0}
        best = start
        bestd = 0
        while q:
            x, y = q.popleft()
            d = dist[(x, y)]
            if d > bestd:
                bestd = d
                best = (x, y)
            for dx, dy in ((1,0),(-1,0),(0,1),(0,-1)):
                nx, ny = x + dx, y + dy
                if not self.in_bounds(nx, ny):
                    continue
                if self.grid[ny][nx] != DUNGEON_FLOOR:
                    continue
                if (nx, ny) in dist:
                    continue
                dist[(nx, ny)] = d + 1
                q.append((nx, ny))
        return best

    def _generate(self):
        self._generate_maze()

        sx, sy = self.start_cell
        # Larger entry room
        self._clear_rect(sx + 2, sy + 2, 13, 13)
        self.exit_cell = (sx + 2, sy + 2)

        far = self._bfs_farthest(self.exit_cell)
        bx, by = far
        # Larger boss arena
        self._clear_rect(bx, by, 19, 19)
        self.boss_cell = (bx, by)

        # More (and larger) rooms to create open areas
        for _ in range(9):
            rx = self.rng.randrange(5, self.w - 5, 2)
            ry = self.rng.randrange(5, self.h - 5, 2)
            self._clear_rect(rx, ry, self.rng.choice([11, 13, 15, 17]), self.rng.choice([11, 13, 15, 17]))

        self.floor_cells = [(x, y) for y in range(1, self.h - 1) for x in range(1, self.w - 1) if self.grid[y][x] == DUNGEON_FLOOR]

    def _build_tiles(self):
        self.floor_tile = pygame.Surface((TILE, TILE))
        self.wall_tile = pygame.Surface((TILE, TILE))
        # Brighter dungeon tiles for visibility
        self.floor_tile.fill((26, 26, 32))
        # Bright walls so the maze reads clearly
        self.wall_tile.fill((78, 66, 108))
        for i in range(50):
            x = (i * 13) % TILE
            y = (i * 29) % TILE
            self.floor_tile.set_at((x, y), (34, 34, 44))
        for i in range(70):
            x = (i * 11) % TILE
            y = (i * 23) % TILE
            self.wall_tile.set_at((x, y), (98, 84, 132))
        # Add a few darker pits to give depth (still bright overall)
        for i in range(35):
            x = (i * 7) % TILE
            y = (i * 19) % TILE
            self.wall_tile.set_at((x, y), (56, 48, 82))

    def tile_at(self, tx, ty):
        if 0 <= tx < self.w and 0 <= ty < self.h:
            return self.grid[ty][tx]
        return DUNGEON_WALL

    def world_from_tile_center(self, tx, ty):
        return pygame.Vector2((tx + 0.5) * TILE, (ty + 0.5) * TILE)

    def draw(self, screen, camera):
        left = int(camera.x // TILE)
        top = int(camera.y // TILE)
        right = int((camera.x + SCREEN_W) // TILE) + 1
        bottom = int((camera.y + SCREEN_H) // TILE) + 1

        left = max(0, left)
        top = max(0, top)
        right = min(self.w, right)
        bottom = min(self.h, bottom)

        for ty in range(top, bottom):
            wy = ty * TILE - camera.y
            for tx in range(left, right):
                wx = tx * TILE - camera.x
                if self.grid[ty][tx] == DUNGEON_FLOOR:
                    screen.blit(self.floor_tile, (int(wx), int(wy)))
                else:
                    screen.blit(self.wall_tile, (int(wx), int(wy)))

        ex = self.world_from_tile_center(self.exit_cell[0], self.exit_cell[1])
        bx = self.world_from_tile_center(self.boss_cell[0], self.boss_cell[1])
        for pos, col in ((ex, (90, 200, 255)), (bx, (255, 90, 180))):
            sx = int(pos.x - camera.x)
            sy = int(pos.y - camera.y)
            pygame.draw.circle(screen, (0, 0, 0), (sx, sy), 18, 3)
            pygame.draw.circle(screen, col, (sx, sy), 16, 3)


class Particle:
    def __init__(self, pos, vel, color, ttl, radius):
        self.pos = pygame.Vector2(pos)
        self.vel = pygame.Vector2(vel)
        self.color = color
        self.ttl = ttl
        self.radius = radius

    def update(self, dt):
        self.pos += self.vel * dt
        self.vel *= (0.90 ** (dt * 60.0))
        self.ttl -= dt

    def draw(self, surf, camera):
        if self.ttl <= 0:
            return
        p = (int(self.pos.x - camera.x), int(self.pos.y - camera.y))
        pygame.draw.circle(surf, self.color, p, max(1, int(self.radius)))


class SlashFX:
    # sharp claw slashes (short-lived line segments)
    def __init__(self, a, b, color=(250, 250, 255), ttl=0.12, width=3):
        self.a = pygame.Vector2(a)
        self.b = pygame.Vector2(b)
        self.color = color
        self.ttl = ttl
        self.width = width

    def update(self, dt):
        self.ttl -= dt

    def draw(self, surf, camera):
        if self.ttl <= 0:
            return
        aa = (int(self.a.x - camera.x), int(self.a.y - camera.y))
        bb = (int(self.b.x - camera.x), int(self.b.y - camera.y))
        pygame.draw.line(surf, (0, 0, 0), aa, bb, self.width + 2)
        pygame.draw.line(surf, self.color, aa, bb, self.width)


class Projectile:
    def __init__(self, owner, team, pos, vel, color, ttl=1.0, radius=5, damage=10):
        self.owner = owner
        self.team = team
        self.pos = pygame.Vector2(pos)
        self.vel = pygame.Vector2(vel)
        self.color = color
        self.ttl = ttl
        self.radius = radius
        self.damage = damage

    def update(self, dt):
        self.pos += self.vel * dt
        self.ttl -= dt

    def draw(self, surf, camera):
        p = (int(self.pos.x - camera.x), int(self.pos.y - camera.y))
        pygame.draw.circle(surf, self.color, p, self.radius)
        pygame.draw.circle(surf, (0, 0, 0), p, self.radius, 2)


class Kitten:
    def __init__(self, name, base_rgb, accent_rgb, pos, seed):
        self.name = name
        self.pos = pygame.Vector2(pos)
        self.vel = pygame.Vector2(0, 0)
        self.radius = 18

        # Colors (used for procedural sprite generation and arm/paw drawing)
        self.base_rgb = tuple(base_rgb)
        self.accent_rgb = tuple(accent_rgb)

        # Paw/arm swat animation state (used for melee attacks)
        self.arm_swing = 0.0
        self.arm_swing_dur = 0.0
        self.arm_dir = pygame.Vector2(0, 1)
        self.arm_kind = "scratch"
        self.arm_lead = 1  # alternates between -1 and +1 each swat
        self.dir = "down"
        self.is_moving = False
        self.walk_t = 0.0
        self.idle_t = 0.0

        self.cooldown = 0.0
        self.melee_cd = 0.0
        self.power_think = 0.0

        self.dash_time = 0.0
        self.dash_dir = pygame.Vector2(1, 0)

        self.max_hp = LEADER_MAX_HP
        self.hp = self.max_hp
        self.down_timer = 0.0

        # Lives system
        self.lives_left = MAX_LIVES
        self.permadead = False

        # Jump state (top-down 'z' height for a high hop)
        self.z = 0.0
        self.vz = 0.0
        self.jump_cd = 0.0
        self.jump_t = 0.0

        self.ai_target = None
        self.ai_target_lock = 0.0

        walk, idle = build_cat_sprites(base_rgb, accent_rgb, seed=seed)
        self.walk_frames = {d: [scale_nearest(f, SPRITE_SCALE) for f in frames] for d, frames in walk.items()}
        self.idle_frames = {d: [scale_nearest(f, SPRITE_SCALE) for f in frames] for d, frames in idle.items()}

        # Pre-baked jump poses per direction (takeoff / air / land)
        self.jump_frames = {d: make_jump_variants(self.idle_frames[d][1]) for d in self.idle_frames}

    def _choose_dir_from_vec(self, v):
        if abs(v.x) > abs(v.y):
            return "right" if v.x > 0 else "left"
        return "down" if v.y > 0 else "up"

    def update_anim(self, dt):
        self.is_moving = self.vel.length_squared() > 20.0
        if self.is_moving:
            self.dir = self._choose_dir_from_vec(self.vel)
            self.walk_t += dt
            self.idle_t = 0.0
        else:
            self.idle_t += dt

    def _draw_arms(self, surf, camera, z_off=0):
        """Render simple forepaws/arms; swat animation is driven by self.arm_swing timers."""
        if self.permadead or self.down_timer > 0:
            return

        cx = int(self.pos.x - camera.x)
        cy = int(self.pos.y - camera.y - int(z_off))

        # Facing direction: during a swat, prefer the actual attack direction.
        if getattr(self, "arm_swing", 0.0) > 0.0:
            f = pygame.Vector2(getattr(self, "arm_dir", pygame.Vector2(0, 1)))
            if f.length_squared() < 1e-6:
                f = pygame.Vector2(0, 1)
            f = f.normalize()
        else:
            if self.dir == "up":
                f = pygame.Vector2(0, -1)
            elif self.dir == "left":
                f = pygame.Vector2(-1, 0)
            elif self.dir == "right":
                f = pygame.Vector2(1, 0)
            else:
                f = pygame.Vector2(0, 1)

        side = pygame.Vector2(-f.y, f.x)

        swing = float(getattr(self, "arm_swing", 0.0))
        dur = float(getattr(self, "arm_swing_dur", 0.0))
        if swing > 0.0 and dur > 0.0:
            p = 1.0 - (swing / dur)
            if p < 0.0:
                p = 0.0
            elif p > 1.0:
                p = 1.0
            s = math.sin(p * math.pi)  # 0->1->0
        else:
            s = 0.0

        kind = getattr(self, "arm_kind", "scratch")
        if kind == "bite":
            swing_len = ARM_SWING_LEN_BITE
        else:
            swing_len = ARM_SWING_LEN_SCRATCH

        length = ARM_IDLE_LEN + (swing_len - ARM_IDLE_LEN) * s

        # Simple palette derived from the kitten colors.
        br, bg, bb = getattr(self, "base_rgb", (220, 220, 220))
        paw = (min(255, br + 55), min(255, bg + 55), min(255, bb + 55))
        claw = (245, 245, 250)

        lead = int(getattr(self, "arm_lead", 1))

        for sign in (-1, 1):  # left(-1), right(+1) relative to facing
            amt = 1.0 if sign == lead else 0.65
            ang = (ARM_SWING_ANGLE_DEG * s * amt) * sign

            idle_dir = (f * 0.25) + (side * (sign * 0.75))
            if idle_dir.length_squared() < 1e-6:
                idle_dir = side * sign
            attack_dir = (f * 1.0) + (side * (sign * 0.20))
            if attack_dir.length_squared() < 1e-6:
                attack_dir = f

            dvec = (idle_dir * (1.0 - s)) + (attack_dir * s)
            if dvec.length_squared() < 1e-6:
                dvec = f
            dvec = dvec.normalize().rotate(ang)

            base = pygame.Vector2(cx, cy + ARM_ANCHOR_Y) + (f * ARM_FORWARD) + (side * (sign * ARM_SPREAD))
            end = base + dvec * length

            pygame.draw.line(surf, paw, (int(base.x), int(base.y)), (int(end.x), int(end.y)), ARM_WIDTH)
            pygame.draw.circle(surf, paw, (int(end.x), int(end.y)), 2)

            # Claws pop out during scratches.
            if s > 0.08 and kind == "scratch":
                for ca in (-14, 0, 14):
                    cdir = dvec.rotate(ca)
                    cend = end + cdir * 5
                    pygame.draw.line(surf, claw, (int(end.x), int(end.y)), (int(cend.x), int(cend.y)), 2)


    def draw(self, surf, camera, selected=False):
        if self.permadead:
            sx = int(self.pos.x - camera.x)
            sy = int(self.pos.y - camera.y)
            pygame.draw.circle(surf, (80, 80, 90), (sx, sy), 13, 2)
            # simple skull mark
            pygame.draw.circle(surf, (80, 80, 90), (sx-4, sy-2), 2)
            pygame.draw.circle(surf, (80, 80, 90), (sx+4, sy-2), 2)
            pygame.draw.line(surf, (80, 80, 90), (sx-4, sy+4), (sx+4, sy+4), 2)
            return

        if self.down_timer > 0:
            sx = int(self.pos.x - camera.x)
            sy = int(self.pos.y - camera.y)
            pygame.draw.circle(surf, (120, 120, 130), (sx, sy), 14, 2)
            return

        # Jump rendering: draw a shadow on the ground and offset the sprite upward by self.z.
        if getattr(self, "z", 0.0) > 0.0:
            sx = int(self.pos.x - camera.x)
            sy = int(self.pos.y - camera.y)

            t = max(0.0, min(1.0, 1.0 - (self.z / JUMP_MAX_Z_FOR_SHADOW)))
            sr = int(10 + 8 * t)
            alpha = int(140 * t)
            sh = pygame.Surface((sr * 2 + 2, sr + 2), pygame.SRCALPHA)
            pygame.draw.ellipse(sh, (0, 0, 0, alpha), sh.get_rect())
            surf.blit(sh, (sx - sh.get_width() // 2, sy + 18 - sh.get_height() // 2))

            jf = self.jump_frames.get(self.dir, None) if hasattr(self, "jump_frames") else None
            if jf is not None:
                if self.vz > 150.0:
                    img = jf[0]   # takeoff
                elif self.vz < -150.0 and self.z < 26.0:
                    img = jf[2]   # landing
                else:
                    img = jf[1]   # airborne
            else:
                # Fallback to idle frame if jump poses are missing for some reason.
                img = self.idle_frames[self.dir][1]

            x = int(self.pos.x - camera.x - img.get_width() // 2)
            y = int(self.pos.y - camera.y - img.get_height() // 2 - int(self.z))
            surf.blit(img, (x, y))
            self._draw_arms(surf, camera, z_off=int(self.z))
        else:
            if self.is_moving:
                idx = int(self.walk_t * 12) % 6
                img = self.walk_frames[self.dir][idx]
            else:
                idx = int(self.idle_t * 3.5) % 4
                img = self.idle_frames[self.dir][idx]

            x = int(self.pos.x - camera.x - img.get_width() // 2)
            y = int(self.pos.y - camera.y - img.get_height() // 2)
            surf.blit(img, (x, y))
            self._draw_arms(surf, camera, z_off=0)

        if selected:
            sx = int(self.pos.x - camera.x)
            sy = int(self.pos.y - camera.y)
            pygame.draw.circle(surf, (245, 220, 140), (sx, sy + 26), 10, 2)


class Enemy:
    def __init__(self, kind, pos, dormant=True):
        self.kind = kind
        self.pos = pygame.Vector2(pos)
        self.vel = pygame.Vector2(0, 0)
        if kind == "robot_cat":
            self.radius = 18
            self.hp = ROBOT_CAT_HP
            walk, idle = build_robot_sprites("cat")
        elif kind == "robot_dog":
            self.radius = 20
            self.hp = ROBOT_DOG_HP
            walk, idle = build_robot_sprites("dog")
        else:
            self.radius = BOSS_RADIUS
            self.hp = BOSS_HP
            walk, idle = build_boss_sprites()

        self.max_hp = self.hp
        self.dead = False

        self.dir = "down"
        self.walk_t = 0.0
        self.idle_t = 0.0
        self.is_moving = False

        self.ai_cd = 0.0
        self.lunge_time = 0.0
        self.lunge_dir = pygame.Vector2(1, 0)

        self.boss_shoot_cd = 0.0
        self.boss_charge_cd = 0.0
        self.boss_charge_time = 0.0
        self.boss_charge_dir = pygame.Vector2(1, 0)

        self.dormant = dormant

        self.walk_frames = {d: [scale_nearest(f, SPRITE_SCALE) for f in frames] for d, frames in walk.items()}
        self.idle_frames = {d: [scale_nearest(f, SPRITE_SCALE) for f in frames] for d, frames in idle.items()}

    def _choose_dir_from_vec(self, v):
        if abs(v.x) > abs(v.y):
            return "right" if v.x > 0 else "left"
        return "down" if v.y > 0 else "up"

    def update_anim(self, dt):
        self.is_moving = self.vel.length_squared() > 15.0
        if self.is_moving:
            self.dir = self._choose_dir_from_vec(self.vel)
            self.walk_t += dt
            self.idle_t = 0.0
        else:
            self.idle_t += dt

    def draw(self, surf, camera):
        if self.dead:
            return

        if self.is_moving:
            idx = int(self.walk_t * 10) % 4
            img = self.walk_frames[self.dir][idx]
        else:
            idx = int(self.idle_t * 2.0) % 2
            img = self.idle_frames[self.dir][idx]

        x = int(self.pos.x - camera.x - img.get_width() // 2)
        y = int(self.pos.y - camera.y - img.get_height() // 2)
        surf.blit(img, (x, y))

        sx = int(self.pos.x - camera.x)
        sy = int(self.pos.y - camera.y)
        pygame.draw.rect(surf, (0, 0, 0), pygame.Rect(sx - 18, sy - 30, 36, 6))
        fill = int(34 * max(0.0, self.hp) / self.max_hp)
        pygame.draw.rect(surf, (255, 70, 90), pygame.Rect(sx - 17, sy - 29, fill, 4))

        if self.dormant:
            pygame.draw.circle(surf, (210, 210, 215), (sx, sy + 26), 8, 1)


class Game:
    def __init__(self):
        pygame.init()
        try:
            pygame.event.set_allowed([pygame.QUIT, pygame.KEYDOWN, pygame.KEYUP, pygame.MOUSEBUTTONDOWN, pygame.VIDEORESIZE])
        except Exception:
            pass
        self.running = True
        self.autotest_until = 0.0
        self.autotest_screenshot = os.getenv("MEWTANTS_AUTOTEST_SCREENSHOT", "").strip()
        autotest_secs = os.getenv("MEWTANTS_AUTOTEST_SECONDS", "").strip()
        if autotest_secs:
            try:
                self.autotest_until = time.time() + max(0.25, float(autotest_secs))
            except Exception:
                self.autotest_until = 0.0
        self.snd = SoundHandler(os.path.dirname(os.path.abspath(__file__)))
        _write_log_line(f"Start {datetime.datetime.now().isoformat()} | fps={FPS}")
        pygame.display.set_caption("Mewtants v1 - Biome Blending + Audio")

        # --- 16:9 1080p virtual canvas + resizable window (no world expansion) ---
        # The game always renders to a fixed 1920x1080 surface (SCREEN_W/SCREEN_H).
        # The OS window can be resized; the render is scaled with letterbox/pillarbox.
        info = pygame.display.Info()
        dw, dh = max(1, info.current_w), max(1, info.current_h)
        s = min(dw / SCREEN_W, dh / SCREEN_H, 1.0)
        init_size = (max(640, int(SCREEN_W * s)), max(360, int(SCREEN_H * s)))

        self.window_flags = pygame.RESIZABLE
        self.window = pygame.display.set_mode(init_size, self.window_flags)
        self.canvas = pygame.Surface((SCREEN_W, SCREEN_H)).convert()

        # Updated whenever the window changes size.
        self._scale = 1.0
        self._scaled_size = (SCREEN_W, SCREEN_H)
        self._offset = (0, 0)
        self._viewport = pygame.Rect(0, 0, SCREEN_W, SCREEN_H)
        self._recalc_view()

        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("consolas", 18)
        self.font_big = pygame.font.SysFont("consolas", 28, bold=True)

        self.world = GrassWorld(seed=1337)
        self.rng = random.Random(20260101)

        self.kittens = [
            Kitten("Ember", (220, 130, 120), (255, 190, 140), (120, 120), seed=11),
            Kitten("Breeze", (135, 205, 170), (200, 255, 230), (170, 120), seed=22),
            Kitten("Frost", (130, 170, 235), (200, 230, 255), (120, 170), seed=33),
            Kitten("Sparkle", (205, 160, 235), (255, 210, 245), (170, 170), seed=44),
        ]
        self.leader_idx = 0
        self.camera = pygame.Vector2(0, 0)

        self.projectiles = []
        self.particles = []
        self.slashes = []
        self.enemies = []

        # Overworld persistence
        self.collected_pickups = set()
        self.cleared_towers = set()

        # Non-hostile animals (Overworld)
        self.collected_squirrels = set()
        self.active_squirrels = {}
        self.squirrel_img = build_squirrel_sprite(scale=3)

        # Guaranteed starter tower so you always see at least one quickly
        leader0 = self.kittens[self.leader_idx]
        self.starter_tower = CatTower("T:starter", leader0.pos + pygame.Vector2(260, 40))

        # Buffs / upgrades
        self.catnip_timer = 0.0
        self.upgrade_level = 0
        self.banner_text = ""
        self.banner_timer = 0.0

        # Pickup art
        self.catnip_img, self.tuna_img, self.whistle_img = build_pickup_sprites(scale=3)

        # Dungeon state
        self.mode = "overworld"
        self.active_squirrels.clear()
        self.dungeon = None
        self.active_tower_id = None
        self.overworld_enemies = []
        self.overworld_return_pos = pygame.Vector2(self.leader().pos)

        self.team_follow = True
        self.mew_flash = 0.0

        self.encounter_cooldown = 1.0
        self.travel_accum = 0.0
        self.next_encounter_dist = ENCOUNTER_DISTANCE_MIN + self.rng.random() * ENCOUNTER_DISTANCE_JITTER
        self._last_leader_pos = pygame.Vector2(self.leader().pos)

    def _set_window(self, size):
        w, h = int(size[0]), int(size[1])
        w = max(640, w)
        h = max(360, h)
        self.window = pygame.display.set_mode((w, h), self.window_flags)
        self._recalc_view()

    def _recalc_view(self):
        ww, wh = self.window.get_size()
        scale = min(ww / SCREEN_W, wh / SCREEN_H)
        if scale <= 0:
            scale = 1.0
        sw = max(1, int(SCREEN_W * scale))
        sh = max(1, int(SCREEN_H * scale))
        offx = (ww - sw) // 2
        offy = (wh - sh) // 2
        self._scale = scale
        self._scaled_size = (sw, sh)
        self._offset = (offx, offy)
        self._viewport = pygame.Rect(offx, offy, sw, sh)

    def window_to_canvas(self, pos):
        mx, my = pos
        offx, offy = self._offset
        scale = self._scale if self._scale > 0 else 1.0
        cx = (mx - offx) / scale
        cy = (my - offy) / scale
        # Clamp inside the virtual canvas so black bars don't break input.
        cx = 0 if cx < 0 else (SCREEN_W - 1 if cx >= SCREEN_W else cx)
        cy = 0 if cy < 0 else (SCREEN_H - 1 if cy >= SCREEN_H else cy)
        return cx, cy

    def present(self):
        # Scale the virtual canvas into the resizable window, preserving aspect ratio.
        self.window.fill((0, 0, 0))
        sw, sh = self._scaled_size
        if (sw, sh) == (SCREEN_W, SCREEN_H):
            scaled = self.canvas
        else:
            # Fast scaling (swap to smoothscale if you prefer softer edges).
            scaled = pygame.transform.scale(self.canvas, (sw, sh))
        self.window.blit(scaled, self._viewport.topleft)
        pygame.display.flip()

    def leader(self):
        return self.kittens[self.leader_idx]

    # ---------- Lives / party management ----------
    def alive_indices(self):
        return [i for i, k in enumerate(self.kittens) if not k.permadead]

    def ensure_valid_leader(self):
        if self.leader_idx < 0 or self.leader_idx >= len(self.kittens):
            self.leader_idx = 0
        if not self.alive_indices():
            return False
        if self.kittens[self.leader_idx].permadead:
            # Switch to the next alive kitten
            for j in range(len(self.kittens)):
                ii = (self.leader_idx + 1 + j) % len(self.kittens)
                if not self.kittens[ii].permadead:
                    self.leader_idx = ii
                    break
        return True

    def handle_cat_death(self, k):
        # Called exactly once when a kitten reaches 0 HP (while not already down/permadead).
        if k.permadead:
            return
        k.lives_left = max(0, k.lives_left - 1)

        if k.lives_left > 0:
            k.down_timer = LEADER_RESPAWN_TIME
            k.hp = 0
            return

        # Out of lives: remove from play.
        k.permadead = True
        k.down_timer = 0.0
        k.hp = 0
        k.pos = pygame.Vector2(-99999, -99999)
        k.vel *= 0

        # If everybody is out, reset the run entirely.
        if not self.ensure_valid_leader() or (not self.alive_indices()):
            self.reset_game_and_progress()
            return

        # Otherwise, transfer control immediately to the next alive kitten.
        self.ensure_valid_leader()
        self.banner_text = f"{k.name} is out of lives!"
        self.banner_timer = 2.2

    def restore_one_cat(self):
        dead = [k for k in self.kittens if k.permadead]
        if not dead:
            return False
        k = dead[0]
        k.permadead = False
        k.lives_left = MAX_LIVES
        k.hp = k.max_hp
        k.down_timer = 0.0

        # Respawn near the current leader.
        lead = self.leader()
        k.pos = pygame.Vector2(lead.pos) + pygame.Vector2(32, 0)
        k.vel *= 0
        return True

    def reset_game_and_progress(self):
        # Reset progress, party, and generate a new world (same assets / rendering).
        self.upgrade_level = 0
        self.catnip_timer = 0.0
        self.banner_text = "All kittens lost... New world begins"
        self.banner_timer = 2.6

        # New world seed (visual assets remain the same: procedural art).
        self.world = GrassWorld(seed=self.rng.randrange(1, 2_000_000_000))

        # Reset persistence
        self.collected_pickups = set()
        self.cleared_towers = set()

        # Reset enemies / effects
        self.projectiles = []
        self.particles = []
        self.slashes = []
        self.enemies = []
        self.overworld_enemies = []
        self.active_squirrels = {}

        # Reset dungeon state
        self.mode = "overworld"
        self.dungeon = None
        self.active_tower_id = None

        # Reset kittens
        self.leader_idx = 0
        base = pygame.Vector2(140, 140)
        offsets = [pygame.Vector2(-22, 0), pygame.Vector2(22, 0), pygame.Vector2(0, -20), pygame.Vector2(0, 20)]
        for i, k in enumerate(self.kittens):
            k.permadead = False
            k.lives_left = MAX_LIVES
            k.down_timer = 0.0
            k.max_hp = LEADER_MAX_HP
            k.hp = k.max_hp
            k.pos = base + offsets[i]
            k.vel *= 0

        self.apply_upgrades_to_team()
        self.camera = pygame.Vector2(0, 0)


    # ---------- Derived stats ----------
    def effective_max_hp(self):
        return LEADER_MAX_HP + self.upgrade_level * UPG_HP_PER_LEVEL

    def dmg_mult(self):
        return 1.0 + self.upgrade_level * UPG_DMG_PER_LEVEL

    def speed_mult(self):
        return 1.0 + self.upgrade_level * UPG_SPEED_PER_LEVEL

    def cd_mult(self):
        lvl = min(self.upgrade_level, UPG_MAX_LEVEL_FOR_CD)
        return max(0.65, 1.0 - lvl * UPG_CD_REDUCTION_PER_LEVEL)

    def buff_dmg_mult(self):
        return CATNIP_DMG_MULT if self.catnip_timer > 0 else 1.0

    def buff_cd_mult(self):
        return CATNIP_CD_MULT if self.catnip_timer > 0 else 1.0

    def buff_speed_mult(self):
        return CATNIP_SPEED_MULT if self.catnip_timer > 0 else 1.0

    def total_dmg_mult(self):
        return self.dmg_mult() * self.buff_dmg_mult()

    def total_cd_mult(self):
        return self.cd_mult() * self.buff_cd_mult()

    def total_speed_mult(self):
        return self.speed_mult() * self.buff_speed_mult()

    def apply_upgrades_to_team(self):
        for k in self.kittens:
            if k.permadead:
                continue
            k.max_hp = self.effective_max_hp()
            if k.down_timer <= 0:
                k.hp = min(k.hp, k.max_hp)


    def mouse_world(self):
        mx, my = pygame.mouse.get_pos()
        cx, cy = self.window_to_canvas((mx, my))
        return pygame.Vector2(cx + self.camera.x, cy + self.camera.y)

    def _move_input(self):
        keys = pygame.key.get_pressed()
        v = pygame.Vector2(
            (keys[pygame.K_d] or keys[pygame.K_RIGHT]) - (keys[pygame.K_a] or keys[pygame.K_LEFT]),
            (keys[pygame.K_s] or keys[pygame.K_DOWN]) - (keys[pygame.K_w] or keys[pygame.K_UP]),
        )
        if v.length_squared() > 0:
            v = v.normalize()
        return v

    def _formation_offsets(self, facing_dir):
        slots = [pygame.Vector2(-52, 28), pygame.Vector2(-52, -28), pygame.Vector2(-92, 0)]
        if facing_dir == "up":
            rot = -math.pi / 2
        elif facing_dir == "down":
            rot = math.pi / 2
        elif facing_dir == "left":
            rot = math.pi
        else:
            rot = 0.0
        c, s = math.cos(rot), math.sin(rot)
        return [pygame.Vector2(v.x * c - v.y * s, v.x * s + v.y * c) for v in slots]

    def circle_hit(self, a_pos, a_r, b_pos, b_r):
        d2 = (a_pos - b_pos).length_squared()
        r = a_r + b_r
        return d2 <= r * r

    def _view_rect_world(self):
        return pygame.Rect(int(self.camera.x), int(self.camera.y), SCREEN_W, SCREEN_H)
    # ---------- Overworld: deterministic pickups / towers ----------
    def _chunk_iter_visible(self):
        view = self._view_rect_world()
        cmin = self.world.world_to_chunk(view.left, view.top)
        cmax = self.world.world_to_chunk(view.right, view.bottom)
        for cy in range(cmin[1] - 1, cmax[1] + 2):
            for cx in range(cmin[0] - 1, cmax[0] + 2):
                yield cx, cy

    def _gen_pickups_in_chunk(self, cx, cy):
        seed = hash2i(cx, cy, self.world.seed ^ 981337)
        rng = random.Random(seed)
        out = []
        margin = 72
        for i in range(2):
            r = rng.random()
            if r < CATNIP_SPAWN_RATE:
                kind = "catnip"
            elif r < CATNIP_SPAWN_RATE + TUNA_SPAWN_RATE:
                kind = "tuna"
            elif r < CATNIP_SPAWN_RATE + TUNA_SPAWN_RATE + WHISTLE_SPAWN_RATE:
                kind = "whistle"
            else:
                continue
            px = cx * CHUNK_PX + margin + rng.random() * (CHUNK_PX - 2 * margin)
            py = cy * CHUNK_PX + margin + rng.random() * (CHUNK_PX - 2 * margin)
            pid = f"P:{cx},{cy},{i},{kind}"
            out.append(Pickup(pid, kind, (px, py)))
        return out

    def _gen_tower_in_chunk(self, cx, cy):
        seed = hash2i(cx, cy, self.world.seed ^ 551122)
        rng = random.Random(seed)
        if rng.random() >= TOWER_SPAWN_RATE:
            return None
        margin = 120
        px = cx * CHUNK_PX + margin + rng.random() * (CHUNK_PX - 2 * margin)
        py = cy * CHUNK_PX + margin + rng.random() * (CHUNK_PX - 2 * margin)
        tid = f"T:{cx},{cy}"
        return CatTower(tid, (px, py))

    def iter_pickups_visible(self):
        if self.mode != "overworld":
            return []
        items = []
        for cx, cy in self._chunk_iter_visible():
            for p in self._gen_pickups_in_chunk(cx, cy):
                if p.id not in self.collected_pickups:
                    items.append(p)
        return items

    def iter_towers_visible(self):
        # Returns towers that are near enough to potentially appear on screen.
        if self.mode != "overworld":
            return []
        leader = self.leader()
        view = self._view_rect_world().inflate(int(SCREEN_W * 1.4), int(SCREEN_H * 1.4))
        lc, lr = self.world.world_to_chunk(leader.pos.x, leader.pos.y)

        out = []
        # Guaranteed starter tower
        if hasattr(self, "starter_tower"):
            t0 = self.starter_tower
            if view.collidepoint(t0.pos.x, t0.pos.y):
                out.append(t0)

        # Search a wider neighborhood so towers are discoverable without traveling far
        R = 3
        for cy in range(lr - R, lr + R + 1):
            for cx in range(lc - R, lc + R + 1):
                t = self._gen_tower_in_chunk(cx, cy)
                if t is not None and view.collidepoint(t.pos.x, t.pos.y):
                    out.append(t)
        return out

    def try_collect_pickups(self):
        if self.mode != "overworld":
            return
        leader = self.leader()
        if leader.down_timer > 0:
            return
        for p in self.iter_pickups_visible():
            if self.circle_hit(leader.pos, leader.radius, p.pos, PICKUP_RADIUS):
                self.collected_pickups.add(p.id)
                if p.kind == "catnip":
                    self.snd.play_powerup("catnip")
                    self.catnip_timer = CATNIP_BUFF_TIME
                    self.banner_text = "Catnip Rush!"
                    self.banner_timer = 1.8
                    for i in range(22):
                        ang = (i / 22.0) * math.tau
                        v = pygame.Vector2(math.cos(ang), math.sin(ang)) * (140 + (i % 3) * 40)
                        self.particles.append(Particle(p.pos, v, (60, 240, 140), 0.50, 2))
                elif p.kind == "tuna":
                    self.snd.play_powerup("tuna")
                    leader.hp = min(leader.max_hp, leader.hp + TUNA_HEAL)
                    self.banner_text = "Tuna +HP"
                    self.banner_timer = 1.4
                    for i in range(18):
                        ang = (i / 18.0) * math.tau
                        v = pygame.Vector2(math.cos(ang), math.sin(ang)) * 120
                        self.particles.append(Particle(p.pos, v, (230, 220, 120), 0.45, 2))
                else:
                    self.snd.play_powerup("whistle")
                    restored = self.restore_one_cat()
                    if restored:
                        self.banner_text = "Cat Whistle! A kitten returns"
                        self.banner_timer = 2.0
                        for i in range(22):
                            ang = (i / 22.0) * math.tau
                            v = pygame.Vector2(math.cos(ang), math.sin(ang)) * (120 + (i % 3) * 40)
                            self.particles.append(Particle(p.pos, v, (230, 230, 250), 0.55, 2))
                    else:
                        self.banner_text = "Whistle... but no one is lost"
                        self.banner_timer = 1.5


    def nearest_tower(self):
        # Nearest tower within a neighborhood of chunks around the player (not limited to on-screen).
        if self.mode != "overworld":
            return None, None
        leader = self.leader()
        lc, lr = self.world.world_to_chunk(leader.pos.x, leader.pos.y)

        best = None
        best_d2 = 999999999.0

        # Starter tower
        if hasattr(self, "starter_tower"):
            t0 = self.starter_tower
            d2 = (t0.pos - leader.pos).length_squared()
            if d2 < best_d2:
                best_d2 = d2
                best = t0

        R = 4
        for cy in range(lr - R, lr + R + 1):
            for cx in range(lc - R, lc + R + 1):
                t = self._gen_tower_in_chunk(cx, cy)
                if t is None:
                    continue
                d2 = (t.pos - leader.pos).length_squared()
                if d2 < best_d2:
                    best_d2 = d2
                    best = t

        return best, math.sqrt(best_d2) if best else None

    # ---------- Overworld: squirrels ----------
    def _gen_squirrels_in_chunk(self, cx, cy):
        seed = hash2i(cx, cy, self.world.seed ^ 0x5A51771E)
        rng = random.Random(seed)
        out = []
        margin = 90
        for i in range(SQUIRREL_MAX_PER_CHUNK):
            if rng.random() >= SQUIRREL_SPAWN_RATE:
                continue
            px = cx * CHUNK_PX + margin + rng.random() * (CHUNK_PX - 2 * margin)
            py = cy * CHUNK_PX + margin + rng.random() * (CHUNK_PX - 2 * margin)
            sid = f"SQ:{cx},{cy},{i}"
            out.append((sid, pygame.Vector2(px, py), seed ^ (i * 0x9E3779B1)))
        return out

    def _sync_active_squirrels(self):
        if self.mode != "overworld":
            self.active_squirrels.clear()
            return

        view = self._view_rect_world().inflate(int(SCREEN_W * 1.6), int(SCREEN_H * 1.6))

        # Spawn/keep squirrels for visible chunks.
        for cx, cy in self._chunk_iter_visible():
            for sid, pos, seedv in self._gen_squirrels_in_chunk(cx, cy):
                if sid in self.collected_squirrels:
                    continue
                if sid in self.active_squirrels:
                    continue
                if view.collidepoint(pos.x, pos.y):
                    self.active_squirrels[sid] = Squirrel(sid, pos, seedv)

        # Despawn far squirrels (keeps CPU usage stable).
        to_remove = []
        far = view.inflate(int(SCREEN_W * 2.0), int(SCREEN_H * 2.0))
        for sid, sq in self.active_squirrels.items():
            if sid in self.collected_squirrels:
                to_remove.append(sid)
                continue
            if not far.collidepoint(sq.pos.x, sq.pos.y):
                to_remove.append(sid)
        for sid in to_remove:
            self.active_squirrels.pop(sid, None)

    def update_squirrels(self, dt):
        if self.mode != "overworld":
            return
        self._sync_active_squirrels()

        # Update and handle capture.
        for sid in list(self.active_squirrels.keys()):
            sq = self.active_squirrels.get(sid)
            if sq is None:
                continue
            sq.update(dt, self.kittens)

            caught = False
            catcher = None
            for k in self.kittens:
                if k.down_timer > 0:
                    continue
                if (k.pos - sq.pos).length() <= SQUIRREL_CAPTURE_RADIUS:
                    caught = True
                    catcher = k
                    break
            if not caught:
                continue

            # Mark as collected so it won't respawn.
            self.collected_squirrels.add(sid)
            self.active_squirrels.pop(sid, None)

            # Reward: short catnip rush or small heal.
            roll = rand01(int(sq.pos.x) // 6, int(sq.pos.y) // 6, self.world.seed, salt=909)
            if roll < SQUIRREL_POWER_CATNIP_CHANCE:
                self.catnip_timer = max(self.catnip_timer, SQUIRREL_CATNIP_TIME)
                self.banner_text = "Squirrel Stash! (Catnip)"
                self.banner_timer = 1.8
                col = (140, 255, 190)
            else:
                leader = self.leader()
                leader.hp = min(leader.max_hp, leader.hp + SQUIRREL_TUNA_HEAL)
                self.banner_text = "Squirrel Snack! (+HP)"
                self.banner_timer = 1.6
                col = (230, 220, 120)

            # VFX
            for i in range(20):
                ang = (i / 20.0) * math.tau
                v = pygame.Vector2(math.cos(ang), math.sin(ang)) * (120 + (i % 3) * 45)
                self.particles.append(Particle(sq.pos, v, col, 0.40, 2))


    # ---------- Dungeon: enter/exit ----------
    def enter_dungeon(self, tower):
        self.snd.play_action("enter_dungeon")
        self.snd.enter_dungeon("tower_maze")
        if tower is None:
            return
        self.mode = "dungeon"
        self.active_squirrels.clear()
        self.active_tower_id = tower.id
        self.overworld_return_pos = pygame.Vector2(self.leader().pos)

        self.overworld_enemies = self.enemies
        self.enemies = []
        self.projectiles = []
        self.particles = []
        self.slashes = []

        seed = hash2i(int(tower.pos.x) // 10, int(tower.pos.y) // 10, self.world.seed ^ 0xD00D)
        self.dungeon = Dungeon(seed)

        start_pos = self.dungeon.world_from_tile_center(self.dungeon.exit_cell[0], self.dungeon.exit_cell[1])
        offsets = [pygame.Vector2(-24, 0), pygame.Vector2(24, 0), pygame.Vector2(0, -22), pygame.Vector2(0, 22)]
        for i, k in enumerate(self.kittens):
            if k.permadead:
                continue
            k.pos = start_pos + offsets[i]
            k.vel *= 0
            k.down_timer = 0.0
            k.hp = min(k.hp, k.max_hp)

        self.spawn_dungeon_enemies()
        self.banner_text = "Dungeon Entered"
        self.banner_timer = 1.6

    def exit_dungeon(self):
        self.snd.play_action("exit_dungeon")
        self.snd.exit_dungeon()
        self.mode = "overworld"
        self.active_squirrels.clear()
        self.dungeon = None
        self.enemies = self.overworld_enemies
        self.projectiles = []
        self.particles = []
        self.slashes = []

        base = pygame.Vector2(self.overworld_return_pos)
        offsets = [pygame.Vector2(-22, 0), pygame.Vector2(22, 0), pygame.Vector2(0, -20), pygame.Vector2(0, 20)]
        for i, k in enumerate(self.kittens):
            if k.permadead:
                continue
            k.pos = base + offsets[i]
            k.vel *= 0

        self.active_tower_id = None
        self.banner_text = "Back Outside"
        self.banner_timer = 1.3

    def spawn_dungeon_enemies(self):
        if self.dungeon is None:
            return
        rng = random.Random(self.dungeon.seed ^ 0xB055)
        floor = self.dungeon.floor_cells[:]
        rng.shuffle(floor)

        boss_pos = self.dungeon.world_from_tile_center(self.dungeon.boss_cell[0], self.dungeon.boss_cell[1])
        boss = Enemy("boss_cat", boss_pos, dormant=False)
        self.enemies.append(boss)

        n = rng.randint(DUNGEON_ENEMY_COUNT_MIN, DUNGEON_ENEMY_COUNT_MAX)
        start_pos = self.dungeon.world_from_tile_center(self.dungeon.exit_cell[0], self.dungeon.exit_cell[1])
        for (tx, ty) in floor:
            if len(self.enemies) >= n + 1:
                break
            pos = self.dungeon.world_from_tile_center(tx, ty)
            if (pos - start_pos).length() < 220:
                continue
            if (pos - boss_pos).length() < 260:
                continue
            kind = "robot_cat" if rng.random() < 0.55 else "robot_dog"
            self.enemies.append(Enemy(kind, pos, dormant=False))

    def dungeon_portal_near(self):
        if self.dungeon is None:
            return False
        leader = self.leader()
        ex = self.dungeon.world_from_tile_center(self.dungeon.exit_cell[0], self.dungeon.exit_cell[1])
        bx = self.dungeon.world_from_tile_center(self.dungeon.boss_cell[0], self.dungeon.boss_cell[1])
        if (leader.pos - ex).length() <= 34:
            return True
        boss_alive = any((e.kind == "boss_cat" and not e.dead) for e in self.enemies)
        if (not boss_alive) and (leader.pos - bx).length() <= 34:
            return True
        return False

    def on_boss_defeated(self):
        if self.active_tower_id is None:
            return
        if self.active_tower_id in self.cleared_towers:
            return
        self.cleared_towers.add(self.active_tower_id)
        self.upgrade_level += 1
        self.apply_upgrades_to_team()
        self.snd.play_action("boss_defeated")
        self.banner_text = "Boss Defeated! Team Upgraded"
        self.banner_timer = 2.4

    # ---------- Dungeon collision ----------
    def _circle_vs_rect_push(self, pos, radius, rect):
        cx = max(rect.left, min(pos.x, rect.right))
        cy = max(rect.top, min(pos.y, rect.bottom))
        dx = pos.x - cx
        dy = pos.y - cy
        d2 = dx * dx + dy * dy
        if d2 >= radius * radius:
            return pos
        if d2 > 0.000001:
            d = math.sqrt(d2)
            push = (radius - d)
            pos.x += (dx / d) * push
            pos.y += (dy / d) * push
            return pos

        dl = abs(pos.x - rect.left)
        dr = abs(rect.right - pos.x)
        dt = abs(pos.y - rect.top)
        db = abs(rect.bottom - pos.y)
        m = min(dl, dr, dt, db)
        if m == dl:
            pos.x = rect.left - radius
        elif m == dr:
            pos.x = rect.right + radius
        elif m == dt:
            pos.y = rect.top - radius
        else:
            pos.y = rect.bottom + radius
        return pos

    def resolve_circle_dungeon(self, obj):
        if self.dungeon is None:
            return
        pos = obj.pos
        r = obj.radius
        tx0 = int((pos.x - r) // TILE)
        ty0 = int((pos.y - r) // TILE)
        tx1 = int((pos.x + r) // TILE)
        ty1 = int((pos.y + r) // TILE)

        for ty in range(ty0 - 1, ty1 + 2):
            for tx in range(tx0 - 1, tx1 + 2):
                if self.dungeon.tile_at(tx, ty) == DUNGEON_WALL:
                    rect = pygame.Rect(tx * TILE, ty * TILE, TILE, TILE)
                    obj.pos = self._circle_vs_rect_push(obj.pos, r, rect)


    def _enemies_near_view(self):
        view = self._view_rect_world()
        view = view.inflate(int(SCREEN_W * ENCOUNTER_VIEW_CLEARANCE), int(SCREEN_H * ENCOUNTER_VIEW_CLEARANCE))
        for e in self.enemies:
            if e.dead:
                continue
            if view.collidepoint(e.pos.x, e.pos.y):
                return True
        return False

    def spawn_enemy_offscreen(self, dormant=True):
        leader = self.leader()
        view = self._view_rect_world()
        margin = 160
        outer = view.inflate(margin * 2, margin * 2)

        for _ in range(60):
            side = self.rng.randint(0, 3)
            if side == 0:
                x = outer.left
                y = self.rng.uniform(outer.top, outer.bottom)
            elif side == 1:
                x = outer.right
                y = self.rng.uniform(outer.top, outer.bottom)
            elif side == 2:
                x = self.rng.uniform(outer.left, outer.right)
                y = outer.top
            else:
                x = self.rng.uniform(outer.left, outer.right)
                y = outer.bottom

            pos = pygame.Vector2(x, y)
            if view.collidepoint(pos.x, pos.y):
                continue
            if (pos - leader.pos).length() < 280:
                continue
            kind = "robot_cat" if self.rng.random() < 0.55 else "robot_dog"
            self.enemies.append(Enemy(kind, pos, dormant=dormant))
            return True
        return False

    def spawn_encounter_group(self):
        group_n = self.rng.randint(ENCOUNTER_GROUP_MIN, ENCOUNTER_GROUP_MAX)
        spawned = 0
        if self.spawn_enemy_offscreen(dormant=True):
            spawned += 1
            base_pos = pygame.Vector2(self.enemies[-1].pos)
            for _ in range(group_n - 1):
                if len(self.enemies) >= ENCOUNTER_MAX_LIVE:
                    break
                ang = self.rng.random() * math.tau
                dist = self.rng.uniform(40, 110)
                pos = base_pos + pygame.Vector2(math.cos(ang), math.sin(ang)) * dist
                kind = "robot_cat" if self.rng.random() < 0.55 else "robot_dog"
                self.enemies.append(Enemy(kind, pos, dormant=True))
                spawned += 1
        return spawned

    def update_encounters(self, dt):
        if self.mode != "overworld":
            return
        leader = self.leader()
        delta = (leader.pos - self._last_leader_pos).length()
        self._last_leader_pos.update(leader.pos)
        self.travel_accum += delta

        self.encounter_cooldown = max(0.0, self.encounter_cooldown - dt)

        self.enemies = [e for e in self.enemies if not e.dead]

        for e in list(self.enemies):
            if e.dormant and (e.pos - leader.pos).length() > DESPAWN_DORMANT_DIST:
                self.enemies.remove(e)

        if len(self.enemies) > DESPAWN_ACTIVE_MINCOUNT:
            for e in list(self.enemies):
                if (not e.dormant) and (e.pos - leader.pos).length() > DESPAWN_ACTIVE_DIST:
                    self.enemies.remove(e)

        if len(self.enemies) >= ENCOUNTER_MAX_LIVE:
            return
        if self.encounter_cooldown > 0:
            return
        if self.travel_accum < self.next_encounter_dist:
            return
        if self._enemies_near_view():
            return

        spawned = self.spawn_encounter_group()
        if spawned > 0:
            self.encounter_cooldown = ENCOUNTER_COOLDOWN
            self.travel_accum = 0.0
            self.next_encounter_dist = ENCOUNTER_DISTANCE_MIN + self.rng.random() * ENCOUNTER_DISTANCE_JITTER

    def cast_power_for(self, kitten, aim_dir, move_dir=None, ai_mode=False):
        if kitten.cooldown > 0 or kitten.down_timer > 0:
            return False

        aim = pygame.Vector2(aim_dir)
        if aim.length_squared() == 0:
            aim = pygame.Vector2(1, 0)
        else:
            aim = aim.normalize()

        # SFX: power cast (tries power_<name> then power)
        self.snd.play_action(f"power_{kitten.name.lower()}", fallbacks=["power"])

        if kitten.name == "Ember":
            self.projectiles.append(Projectile(kitten.name, "kittens", kitten.pos + aim * 18, aim * 860.0, (255, 160, 90), ttl=1.0, radius=6, damage=int(DMG_EMBER * self.total_dmg_mult())))
            for i in range(10):
                ang = (i / 10.0) * math.tau
                self.particles.append(Particle(kitten.pos + aim * 16, pygame.Vector2(math.cos(ang), math.sin(ang)) * 120 + aim * 220, (255, 180, 110), 0.25, 2))

        elif kitten.name == "Breeze":
            dash_dir = move_dir if (move_dir is not None and move_dir.length_squared() > 0) else aim
            dash_dir = dash_dir.normalize() if dash_dir.length_squared() > 0 else pygame.Vector2(1, 0)
            kitten.dash_dir = dash_dir
            kitten.dash_time = 0.24
            for i in range(18):
                r = (i / 18.0) * math.tau
                self.particles.append(Particle(kitten.pos, pygame.Vector2(math.cos(r), math.sin(r)) * 85 - kitten.dash_dir * 160, (160, 255, 220), 0.35, 2))

        elif kitten.name == "Frost":
            count = 12
            for i in range(count):
                ang = (i / count) * math.tau
                v = pygame.Vector2(math.cos(ang), math.sin(ang))
                self.projectiles.append(Projectile(kitten.name, "kittens", kitten.pos + v * 14, v * 540.0, (180, 230, 255), ttl=0.8, radius=5, damage=int(DMG_FROST * self.total_dmg_mult())))
            for i in range(26):
                ang = (i / 26.0) * math.tau
                self.particles.append(Particle(kitten.pos, pygame.Vector2(math.cos(ang), math.sin(ang)) * 240, (200, 240, 255), 0.45, 2))

        elif kitten.name == "Sparkle":
            blink_max = AI_SPARKLE_MAX_BLINK if ai_mode else 260.0
            delta = aim * blink_max
            start = pygame.Vector2(kitten.pos)
            kitten.pos += delta
            for i in range(22):
                t = i / 21.0
                pos = start.lerp(kitten.pos, t)
                jitter = pygame.Vector2((i * 97 % 31) - 15, (i * 53 % 27) - 13) * 0.7
                self.particles.append(Particle(pos + jitter, jitter * 2.8, (255, 210, 245), 0.40, 2))
            for i in range(16):
                ang = (i / 16.0) * math.tau
                self.particles.append(Particle(kitten.pos, pygame.Vector2(math.cos(ang), math.sin(ang)) * 160, (255, 230, 250), 0.35, 2))

        kitten.cooldown = POWER_CD.get(kitten.name, 0.9) * self.total_cd_mult()
        return True

    def cast_leader_power(self):
        k = self.leader()
        mw = self.mouse_world()
        aim = mw - k.pos
        move = self._move_input()
        self.cast_power_for(k, aim, move_dir=move, ai_mode=False)


    def party_jump(self):
        """Spacebar: make the party hop. All active cats jump together."""
        leader = self.leader()
        did = False
        for k in self.kittens:
            if k.permadead or k.down_timer > 0:
                continue
            if k.z > 0.0 or k.jump_cd > 0.0:
                continue

            k.z = 0.01
            k.vz = JUMP_VEL
            k.jump_cd = JUMP_COOLDOWN
            k.jump_t = 0.0
            did = True
            jumped_any = True

            # Tiny dust puff on takeoff
            for i in range(8):
                ang = (i / 8.0) * math.tau
                v = pygame.Vector2(math.cos(ang), math.sin(ang)) * 140 + k.vel * 0.25
                self.particles.append(Particle(k.pos, v, (235, 225, 210), 0.25, 2))
        if jumped_any:
            self.snd.play_action("jump")
        return did

    def leader_scratch(self):
        k = self.leader()
        if k.down_timer > 0 or k.melee_cd > 0:
            return False

        live = [e for e in self.enemies if not e.dead]
        if not live:
            return False

        # Only allow scratches if the target is within scratch range of the leader.
        in_range = []
        r2 = MELEE_SCRATCH_RANGE * MELEE_SCRATCH_RANGE
        for e in live:
            if (e.pos - k.pos).length_squared() <= r2:
                in_range.append(e)
        if not in_range:
            return False

        # Prefer the enemy closest to the mouse cursor, so clicking "aims" the scratch.
        mw = self.mouse_world()
        target = min(in_range, key=lambda e: (e.pos - mw).length_squared())

        self.kitten_melee_attack(k, target, prefer_scratch=True)
        return True


    def ai_cast_powers(self, dt):
        live = [e for e in self.enemies if not e.dead]
        if not live:
            return

        for i, k in enumerate(self.kittens):
            if i == self.leader_idx:
                continue
            if k.down_timer > 0:
                continue

            k.power_think = max(0.0, k.power_think - dt)
            if k.power_think > 0:
                continue
            k.power_think = AI_POWER_DECISION_RATE + self.rng.random() * 0.12

            if k.cooldown > 0:
                continue

            best = None
            best_d2 = 1e18
            for e in live:
                d2 = (e.pos - k.pos).length_squared()
                if d2 < best_d2 and d2 <= AI_POWER_RANGE * AI_POWER_RANGE:
                    best = e
                    best_d2 = d2
            if best is None:
                continue

            if self.rng.random() > AI_POWER_CHANCE:
                continue

            if best.dormant and (best.pos - k.pos).length() <= ENEMY_ACTIVATION_DIST:
                best.dormant = False

            aim = best.pos - k.pos
            move = aim.normalize() if aim.length_squared() > 0 else pygame.Vector2(1, 0)
            self.cast_power_for(k, aim, move_dir=move, ai_mode=True)

    def claw_slash_vfx(self, attacker, enemy):
        d = enemy.pos - attacker.pos
        if d.length_squared() == 0:
            d = pygame.Vector2(1, 0)
        n = d.normalize()
        perp = pygame.Vector2(-n.y, n.x)

        base = pygame.Vector2(enemy.pos) - n * 10
        for s in (-1, 0, 1):
            offset = perp * (s * 8)
            a = base + offset - perp * 16 + n * 2
            b = base + offset + perp * 16 + n * 8
            self.slashes.append(SlashFX(a, b, color=(250, 250, 255), ttl=0.12, width=3))

        for i in range(12):
            ang = (i / 12.0) * math.tau
            self.particles.append(Particle(enemy.pos, pygame.Vector2(math.cos(ang), math.sin(ang)) * 95 + n * 80, (255, 245, 220), 0.16, 2))

    def kitten_melee_attack(self, kitten, enemy, prefer_scratch=False):
        if kitten.melee_cd > 0 or kitten.down_timer > 0 or enemy.dead:
            return
        d = enemy.pos - kitten.pos
        dist = d.length()
        if dist <= 0.0001:
            d = pygame.Vector2(1, 0)
            dist = 1.0
        n = d / dist

        did = False
        dmg = 0

        if (not prefer_scratch) and dist <= MELEE_BITE_RANGE and self.rng.random() < 0.50:
            dmg = MELEE_BITE_DMG
            kitten.melee_cd = MELEE_BITE_CD * self.total_cd_mult()
            # Animate paws/arms for the swat/bite.
            kitten.arm_lead = -int(getattr(kitten, "arm_lead", 1))
            kitten.arm_swing_dur = ARM_SWING_TIME_BITE
            kitten.arm_swing = kitten.arm_swing_dur
            kitten.arm_dir = pygame.Vector2(n)
            kitten.arm_kind = "bite"
            col = (255, 180, 160)
            for i in range(12):
                ang = (i / 12.0) * math.tau
                self.particles.append(Particle(enemy.pos, pygame.Vector2(math.cos(ang), math.sin(ang)) * 110 + n * 80, col, 0.20, 2))
            did = True
            jumped_any = True

        if (not did) and dist <= MELEE_SCRATCH_RANGE:
            dmg = MELEE_SCRATCH_DMG
            kitten.melee_cd = MELEE_SCRATCH_CD * self.total_cd_mult()
            self.claw_slash_vfx(kitten, enemy)
            # Animate paws/arms for the scratch.
            kitten.arm_lead = -int(getattr(kitten, "arm_lead", 1))
            kitten.arm_swing_dur = ARM_SWING_TIME_SCRATCH
            kitten.arm_swing = kitten.arm_swing_dur
            kitten.arm_dir = pygame.Vector2(n)
            kitten.arm_kind = "scratch"
            did = True
            jumped_any = True

        if not did:
            return

        # SFX: melee
        if getattr(kitten, "arm_kind", "") == "bite":
            self.snd.play_action("bite", fallbacks=["scratch"])
        else:
            self.snd.play_action("scratch", fallbacks=["bite"])
        self.snd.play_action("hit", volume=0.65, fallbacks=[])

        enemy.hp -= int(dmg * self.total_dmg_mult())
        enemy.vel += n * 160.0
        if enemy.hp <= 0:
            enemy.dead = True
            if enemy.kind == "boss_cat":
                self.on_boss_defeated()
            for i in range(18):
                ang = (i / 18.0) * math.tau
                self.particles.append(Particle(enemy.pos, pygame.Vector2(math.cos(ang), math.sin(ang)) * 190, (205, 215, 230), 0.35, 2))

    def always_scratch_nearby(self):
        live = [e for e in self.enemies if not e.dead]
        if not live:
            return
        for k in self.kittens:
            if k.down_timer > 0 or k.melee_cd > 0:
                continue
            best = None
            best_d2 = AUTO_SCRATCH_SCAN_RADIUS * AUTO_SCRATCH_SCAN_RADIUS
            for e in live:
                d2 = (e.pos - k.pos).length_squared()
                if d2 <= best_d2:
                    best = e
                    best_d2 = d2
            if best is None:
                continue
            if best.dormant and (best.pos - k.pos).length() <= ENEMY_ACTIVATION_DIST:
                best.dormant = False
            self.kitten_melee_attack(k, best, prefer_scratch=True)

    def apply_knockback(self, enemy, from_pos, strength):
        d = enemy.pos - from_pos
        d = pygame.Vector2(1, 0) if d.length_squared() == 0 else d.normalize()
        enemy.vel += d * strength

    def update_projectiles(self, dt):
        kept = []
        for p in self.projectiles:
            old_pos = pygame.Vector2(p.pos)
            p.update(dt)
            if p.ttl <= 0:
                continue

            # In dungeons, projectiles collide with (and destroy) maze wall tiles instead of passing through.
            if self.mode == "dungeon" and self.dungeon is not None:
                new_pos = pygame.Vector2(p.pos)
                seg = new_pos - old_pos
                dist = seg.length()
                steps = max(1, int(dist / (TILE / 3)))
                hit_pos = None
                for si in range(steps + 1):
                    t = si / steps
                    sp = old_pos.lerp(new_pos, t)
                    tx = int(sp.x // TILE)
                    ty = int(sp.y // TILE)
                    if 0 <= tx < self.dungeon.w and 0 <= ty < self.dungeon.h:
                        if self.dungeon.grid[ty][tx] == DUNGEON_WALL:
                            # Keep border walls intact to avoid escaping the dungeon.
                            if 0 < tx < self.dungeon.w - 1 and 0 < ty < self.dungeon.h - 1:
                                self.dungeon.grid[ty][tx] = DUNGEON_FLOOR
                            hit_pos = sp
                            break
                if hit_pos is not None:
                    for i in range(12):
                        ang = (i / 12.0) * math.tau
                        self.particles.append(
                            Particle(hit_pos, pygame.Vector2(math.cos(ang), math.sin(ang)) * 135, (235, 230, 255), 0.25, 2)
                        )
                    # Remove the projectile on impact.
                    continue

            hit = False
            if p.team == "kittens":
                for e in self.enemies:
                    if e.dead:
                        continue
                    if self.circle_hit(p.pos, p.radius, e.pos, e.radius):
                        e.hp -= p.damage
                        hit = True
                        self.apply_knockback(e, p.pos, 180.0)
                        col = (255, 200, 130) if p.owner == "Ember" else (210, 245, 255)
                        for i in range(10):
                            ang = (i / 10.0) * math.tau
                            self.particles.append(Particle(e.pos, pygame.Vector2(math.cos(ang), math.sin(ang)) * 140, col, 0.22, 2))
                        if e.hp <= 0:
                            e.dead = True
                            if e.kind == "boss_cat":
                                self.on_boss_defeated()
                                for i in range(18):
                                    ang = (i / 18.0) * math.tau
                                    self.particles.append(Particle(e.pos, pygame.Vector2(math.cos(ang), math.sin(ang)) * 190, (205, 215, 230), 0.35, 2))
                        break
            else:
                leader = self.leader()
                if leader.down_timer <= 0 and self.circle_hit(p.pos, p.radius, leader.pos, leader.radius):
                    leader.hp -= p.damage
                    hit = True
                    for i in range(10):
                        ang = (i / 10.0) * math.tau
                        self.particles.append(Particle(leader.pos, pygame.Vector2(math.cos(ang), math.sin(ang)) * 120, (255, 90, 110), 0.20, 2))

            if not hit:
                kept.append(p)
        self.projectiles = kept

    def update_particles(self, dt):
        newp = []
        for fx in self.particles:
            fx.update(dt)
            if fx.ttl > 0:
                newp.append(fx)
        self.particles = newp

    def update_slashes(self, dt):
        kept = []
        for s in self.slashes:
            s.update(dt)
            if s.ttl > 0:
                kept.append(s)
        self.slashes = kept

    def update_kittens(self, dt):
        self.mew_flash = max(0.0, self.mew_flash - dt)
        self.catnip_timer = max(0.0, self.catnip_timer - dt)
        self.banner_timer = max(0.0, self.banner_timer - dt)

        for k in self.kittens:
            k.cooldown = max(0.0, k.cooldown - dt)
            k.melee_cd = max(0.0, k.melee_cd - dt)
            k.ai_target_lock = max(0.0, k.ai_target_lock - dt)
            k.jump_cd = max(0.0, getattr(k, "jump_cd", 0.0) - dt)
            # Paw/arm swat animation timer
            k.arm_swing = max(0.0, getattr(k, "arm_swing", 0.0) - dt)
            # Jump physics (simple top-down 'z' hop)
            if getattr(k, "z", 0.0) > 0.0 or getattr(k, "vz", 0.0) != 0.0:
                k.vz -= JUMP_GRAVITY * dt
                k.z += k.vz * dt
                if k.z <= 0.0:
                    k.z = 0.0
                    k.vz = 0.0
            if k.down_timer > 0:
                k.arm_swing = 0.0
                k.down_timer -= dt
                if k.down_timer <= 0:
                    if not k.permadead:
                        k.hp = k.max_hp

        leader = self.leader()
        speed_mul = self.total_speed_mult()

        if leader.down_timer <= 0:
            move = self._move_input()
            if leader.dash_time > 0:
                leader.dash_time -= dt
                leader.vel = leader.dash_dir * (790.0 * speed_mul)
            else:
                desired = move * (LEADER_SPEED * speed_mul)
                dv = desired - leader.vel
                max_dv = LEADER_ACCEL * dt
                if dv.length_squared() > max_dv * max_dv and dv.length_squared() > 0:
                    dv.scale_to_length(max_dv)
                leader.vel += dv
        else:
            leader.vel *= (0.86 ** (dt * 60.0))

        offsets = self._formation_offsets(leader.dir)
        follower_indices = [i for i in range(len(self.kittens)) if i != self.leader_idx]
        live_enemies = [e for e in self.enemies if not e.dead]

        for slot_i, idx in enumerate(follower_indices):
            k = self.kittens[idx]
            if k.down_timer > 0:
                k.vel *= (0.86 ** (dt * 60.0))
                continue

            if self.team_follow:
                target = leader.pos + offsets[slot_i]
                to_target = target - k.pos
                dist = to_target.length()
                if dist < FOLLOW_STOP_RADIUS:
                    desired = pygame.Vector2(0, 0)
                else:
                    spd = FOLLOW_SPEED if dist < 220 else FOLLOW_CATCHUP_SPEED
                    desired = (to_target / dist) * spd
                dv = desired - k.vel
                max_dv = FOLLOW_ACCEL * dt
                if dv.length_squared() > max_dv * max_dv and dv.length_squared() > 0:
                    dv.scale_to_length(max_dv)
                k.vel += dv
            else:
                if k.ai_target is not None:
                    if k.ai_target.dead:
                        k.ai_target = None
                    elif (k.ai_target.pos - leader.pos).length() > ASSIST_BREAK_RANGE:
                        k.ai_target = None

                if k.ai_target is None or k.ai_target_lock <= 0:
                    best = None
                    best_d2 = 1e18
                    for e in live_enemies:
                        d2 = (e.pos - k.pos).length_squared()
                        if d2 < best_d2 and d2 <= ASSIST_ACQUIRE_RANGE * ASSIST_ACQUIRE_RANGE:
                            best = e
                            best_d2 = d2
                    k.ai_target = best
                    k.ai_target_lock = 0.25

                if k.ai_target is None:
                    target = leader.pos + offsets[slot_i] * 0.7
                    to_target = target - k.pos
                    dist = to_target.length()
                    desired = (to_target / dist) * min(ASSIST_CHASE_SPEED, 220.0) if dist > 20 else pygame.Vector2(0, 0)
                else:
                    e = k.ai_target
                    to_e = e.pos - k.pos
                    dist = to_e.length()
                    n = (to_e / dist) if dist > 0.001 else pygame.Vector2(1, 0)

                    if e.dormant and dist <= ENEMY_ACTIVATION_DIST:
                        e.dormant = False

                    if dist < ASSIST_ORBIT_RANGE:
                        desired = pygame.Vector2(-n.y, n.x) * 170.0
                    else:
                        desired = n * ASSIST_CHASE_SPEED

                dv = desired - k.vel
                max_dv = ASSIST_CHASE_ACCEL * dt
                if dv.length_squared() > max_dv * max_dv and dv.length_squared() > 0:
                    dv.scale_to_length(max_dv)
                k.vel += dv

        for i in range(len(self.kittens)):
            for j in range(i + 1, len(self.kittens)):
                a = self.kittens[i]
                b = self.kittens[j]
                if a.down_timer > 0 or b.down_timer > 0:
                    continue
                d = b.pos - a.pos
                dist2 = d.length_squared()
                if dist2 <= 0.0001:
                    continue
                dist = math.sqrt(dist2)
                if dist < SEPARATION_RADIUS:
                    push_dir = d / dist
                    strength = (SEPARATION_RADIUS - dist) / SEPARATION_RADIUS
                    push = push_dir * (SEPARATION_FORCE * strength)
                    a.vel -= push
                    b.vel += push

        for k in self.kittens:
            k.vel = clamp_vec(k.vel, MAX_VEL)
            k.pos += k.vel * dt
            if self.mode == "dungeon":
                self.resolve_circle_dungeon(k)
            k.update_anim(dt)

        # Always scratch nearby enemies (independent of follow/assist)
        self.always_scratch_nearby()

        # Companions use their powers (with cooldowns)
        self.ai_cast_powers(dt)

        if leader.down_timer <= 0 and leader.hp <= 0 and (not leader.permadead):
            # Spend a life; if none remain, rotate control to the next kitten.
            self.handle_cat_death(leader)
            for i in range(30):
                ang = (i / 30.0) * math.tau
                self.particles.append(Particle(leader.pos, pygame.Vector2(math.cos(ang), math.sin(ang)) * 220, (255, 90, 110), 0.55, 2))

    def update_enemies(self, dt):
        leader = self.leader()
        if leader.down_timer > 0:
            for e in self.enemies:
                e.ai_cd = max(0.0, e.ai_cd - dt)
                e.vel *= (0.90 ** (dt * 60.0))
                e.pos += e.vel * dt
                if self.mode == "dungeon":
                    self.resolve_circle_dungeon(e)
                e.update_anim(dt)
            return

        for e in self.enemies:
            if e.dead:
                continue
            if e.dormant and (leader.pos - e.pos).length() <= ENEMY_ACTIVATION_DIST:
                e.dormant = False

        for e in self.enemies:
            if e.dead:
                continue
            to_leader = leader.pos - e.pos
            dist = to_leader.length()
            e.ai_cd = max(0.0, e.ai_cd - dt)

            if e.dormant:
                e.vel *= (0.80 ** (dt * 60.0))
                e.pos += e.vel * dt
                e.update_anim(dt)
                continue

            if e.kind == "boss_cat":
                e.boss_shoot_cd = max(0.0, e.boss_shoot_cd - dt)
                e.boss_charge_cd = max(0.0, e.boss_charge_cd - dt)
                e.boss_charge_time = max(0.0, e.boss_charge_time - dt)

                dirv = to_leader.normalize() if dist > 0.001 else pygame.Vector2(1, 0)

                if e.boss_charge_time > 0:
                    e.vel = dirv * BOSS_CHARGE_SPEED
                else:
                    desired = dirv * (BOSS_MOVE_SPEED * 1.0)
                    if dist < 160:
                        desired = -dirv * (BOSS_MOVE_SPEED * 0.75)
                    e.vel += (desired - e.vel) * min(1.0, dt * 3.5)

                    if e.boss_charge_cd <= 0.0 and dist < 420:
                        e.boss_charge_cd = BOSS_CHARGE_CD
                        e.boss_charge_time = BOSS_CHARGE_TIME

                if e.boss_shoot_cd <= 0.0 and dist < 520:
                    e.boss_shoot_cd = BOSS_SHOOT_CD
                    base = math.atan2(dirv.y, dirv.x)
                    for i in range(-BOSS_SHOOT_SPREAD//2, BOSS_SHOOT_SPREAD//2 + 1):
                        ang = base + (i * 0.10)
                        v = pygame.Vector2(math.cos(ang), math.sin(ang)) * 520
                        self.projectiles.append(Projectile("boss_cat", "enemies", e.pos, v, (255, 90, 180), ttl=1.1, radius=7, damage=BOSS_PROJECTILE_DMG))
            elif e.kind == "robot_cat":
                if dist < CAT_AGGRO:
                    dirv = (to_leader / dist) if dist > 0 else pygame.Vector2(1, 0)
                    if dist > CAT_DESIRED_RANGE + 35:
                        desired = dirv * 185.0
                    elif dist < CAT_DESIRED_RANGE - 30:
                        desired = -dirv * 210.0
                    else:
                        desired = pygame.Vector2(-dirv.y, dirv.x) * 140.0

                    dv = desired - e.vel
                    max_dv = 980.0 * dt
                    if dv.length_squared() > max_dv * max_dv and dv.length_squared() > 0:
                        dv.scale_to_length(max_dv)
                    e.vel += dv

                    if dist < CAT_SHOOT_RANGE and e.ai_cd <= 0:
                        e.ai_cd = CAT_SHOOT_CD
                        bolt_speed = 560.0
                        self.projectiles.append(Projectile("robot_cat", "enemies", e.pos + dirv * 16, dirv * bolt_speed, (255, 80, 95), ttl=1.15, radius=5, damage=DMG_CAT_BOLT))
                        for i in range(8):
                            ang = (i / 8.0) * math.tau
                            self.particles.append(Particle(e.pos + dirv * 12, pygame.Vector2(math.cos(ang), math.sin(ang)) * 95 + dirv * 120, (255, 90, 110), 0.18, 2))
                else:
                    e.vel *= (0.92 ** (dt * 60.0))
            else:
                if e.lunge_time > 0:
                    e.lunge_time -= dt
                    e.vel = e.lunge_dir * 430.0
                elif dist < DOG_AGGRO:
                    dirv = to_leader.normalize() if dist > 0 else pygame.Vector2(1, 0)
                    desired = dirv * 235.0
                    dv = desired - e.vel
                    max_dv = 1050.0 * dt
                    if dv.length_squared() > max_dv * max_dv and dv.length_squared() > 0:
                        dv.scale_to_length(max_dv)
                    e.vel += dv

                    if dist < 170 and e.ai_cd <= 0:
                        e.ai_cd = DOG_LUNGE_CD
                        e.lunge_time = DOG_LUNGE_TIME
                        e.lunge_dir = dirv
                        for i in range(14):
                            ang = (i / 14.0) * math.tau
                            self.particles.append(Particle(e.pos, pygame.Vector2(math.cos(ang), math.sin(ang)) * 90 - dirv * 120, (120, 220, 255), 0.22, 2))
                else:
                    e.vel *= (0.92 ** (dt * 60.0))

            e.vel = clamp_vec(e.vel, 460.0)
            e.pos += e.vel * dt
            e.update_anim(dt)

        # Separation among enemies
        for i in range(len(self.enemies)):
            a = self.enemies[i]
            if a.dead:
                continue
            for j in range(i + 1, len(self.enemies)):
                b = self.enemies[j]
                if b.dead:
                    continue
                d = b.pos - a.pos
                dist2 = d.length_squared()
                if dist2 <= 0.0001:
                    continue
                dist = math.sqrt(dist2)
                min_d = (a.radius + b.radius) * 1.05
                if dist < min_d:
                    push = (d / dist) * (min_d - dist) * 24.0
                    a.pos -= push * 0.5
                    b.pos += push * 0.5

        # Enemies vs kittens separation
        for e in self.enemies:
            if e.dead or e.dormant:
                continue
            for k in self.kittens:
                if k.down_timer > 0:
                    continue
                d = e.pos - k.pos
                dist2 = d.length_squared()
                if dist2 <= 0.0001:
                    continue
                dist = math.sqrt(dist2)
                min_d = (e.radius + k.radius) + 10.0
                if dist < min_d:
                    n = (d / dist)
                    push_amt = (min_d - dist)
                    e.pos += n * (push_amt * 0.70)
                    k.pos -= n * (push_amt * 0.30)

                    rel = e.vel - k.vel
                    into = rel.dot(n)
                    if into < 0:
                        e.vel -= n * (into * 0.85)

        # Contact damage (dogs)
        for e in self.enemies:
            if e.dead or e.dormant:
                continue
            if e.kind == "robot_dog" and leader.down_timer <= 0:
                if self.circle_hit(e.pos, e.radius, leader.pos, leader.radius) and (e.lunge_time > 0.0 or (leader.pos - e.pos).length() < DOG_BITE_RANGE):
                    if e.ai_cd <= DOG_LUNGE_CD - 0.35:
                        leader.hp -= DMG_DOG_BITE
                        self.apply_knockback(e, leader.pos, 140.0)

        # Breeze dash damage (any breeze kitten)
        for k in self.kittens:
            if k.name != "Breeze" or k.dash_time <= 0:
                continue
            for e in self.enemies:
                if e.dead:
                    continue
                if self.circle_hit(k.pos, k.radius, e.pos, e.radius):
                    e.hp -= int(DMG_BREEZE_DASH * self.total_dmg_mult())
                    self.apply_knockback(e, k.pos, 240.0)
                    if e.hp <= 0:
                        e.dead = True

    def request_exit(self):
        self.running = False

    def save_runtime_screenshot(self, path_str: str = "") -> None:
        path_str = (path_str or "").strip()
        if not path_str:
            return
        try:
            out = Path(path_str)
            out.parent.mkdir(parents=True, exist_ok=True)
            pygame.image.save(self.window, str(out))
            _write_log_line(f"Saved screenshot: {out}")
        except Exception as exc:
            _write_log_line(f"Screenshot save failed: {exc}")

    def shutdown(self):
        try:
            self.snd.shutdown()
        except Exception:
            pass
        try:
            pygame.quit()
        except Exception:
            pass
        _write_log_line(f"Exit {datetime.datetime.now().isoformat()}")

    def draw_ui(self):
        panel = pygame.Rect(0, 0, SCREEN_W, 64)
        pygame.draw.rect(self.canvas, UI_BG, panel)
        pygame.draw.line(self.canvas, (0, 0, 0), (0, 64), (SCREEN_W, 64), 2)

        leader = self.leader()
        cd = f"{leader.cooldown:.2f}s" if leader.cooldown > 0 else "Ready"
        hp = max(0, leader.hp)
        down = f" DOWN({leader.down_timer:.1f})" if leader.down_timer > 0 else ""
        lives = "OUT" if leader.permadead else f"{leader.lives_left}/{MAX_LIVES}"
        alive = len([e for e in self.enemies if not e.dead])
        dormant = sum(1 for e in self.enemies if (not e.dead) and e.dormant)
        mode = "FOLLOW" if self.team_follow else "ASSIST"

        text = f"Leader: {leader.name} | Mode: {mode} | Power CD: {cd} | HP: {hp}/{LEADER_MAX_HP}{down} | Lives: {lives} | Enemies: {alive} (Dormant:{dormant})"
        self.canvas.blit(self.font.render(text, True, WHITE), (12, 16))
        self.canvas.blit(self.font.render("WASD/Arrows move | Space=Jump (party) | RMB=Power | 1-4=Leader | M=Toggle follow/assist", True, (205, 205, 212)), (12, 38))
        # Buff + progression
        if self.catnip_timer > 0:
            self.canvas.blit(self.font.render(f"Catnip: {self.catnip_timer:0.1f}s (DMG+ / Faster / CD-)", True, (120, 240, 160)), (12, 74))
        self.canvas.blit(self.font.render(f"Boss Wins (Upgrades): {self.upgrade_level}", True, (255, 210, 110)), (12, 94))
        # Biome readout (overworld blending along +X)
        if self.mode != "dungeon":
            wx = self.camera.x + SCREEN_W * 0.5
            b0, b1, tt = self.world.biome_mix(wx)
            if tt <= 0.001:
                btxt = f"Biome: {b0}"
            else:
                pct = int(tt * 100)
                btxt = f"Biome: {b0} → {b1} ({pct}%)"
            self.canvas.blit(self.font.render(btxt, True, (220, 220, 240)), (12, 134))

        if self.mode == "dungeon":
            self.canvas.blit(self.font.render("Mode: Dungeon (Press E at portal to exit)", True, (200, 200, 220)), (12, 114))
        else:
            t, dist = self.nearest_tower()
            if t is not None and dist is not None and dist < 90:
                cleared = (t.id in self.cleared_towers)
                msg = "Press E to enter Cat Tower Dungeon" + (" (cleared)" if cleared else "")
                self.canvas.blit(self.font.render(msg, True, (255, 230, 170)), (12, 114))

        if self.banner_timer > 0 and self.banner_text:
            srf = self.font_big.render(self.banner_text, True, (255, 255, 255))
            sh = self.font_big.render(self.banner_text, True, (0, 0, 0))
            bx = (SCREEN_W - srf.get_width()) // 2
            by = 18
            self.canvas.blit(sh, (bx + 2, by + 2))
            self.canvas.blit(srf, (bx, by))

        bar = pygame.Rect(12, 56, 220, 6)
        pygame.draw.rect(self.canvas, (0, 0, 0), bar)
        fill = int(218 * hp / max(1, leader.max_hp))
        pygame.draw.rect(self.canvas, (255, 90, 110), pygame.Rect(13, 57, fill, 4))

        if self.mew_flash > 0:
            a = min(180, int(180 * (self.mew_flash / 0.35)))
            overlay = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
            overlay.fill((255, 255, 255, a))
            self.canvas.blit(overlay, (0, 0))

    def run(self):
        while self.running:
            dt = self.clock.tick(FPS) / 1000.0

            for event in pygame.event.get():
                if event.type == pygame.VIDEORESIZE:
                    self._set_window(event.size)
                if event.type == pygame.QUIT:
                    self.request_exit()
                if event.type == pygame.MOUSEBUTTONDOWN:
                    # LMB: scratch (melee). RMB: leader power.
                    if event.button == 1:
                        self.leader_scratch()
                    elif event.button == 3:
                        self.cast_leader_power()
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        self.request_exit()
                    if event.key in (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4):
                        self.leader_idx = {pygame.K_1: 0, pygame.K_2: 1, pygame.K_3: 2, pygame.K_4: 3}[event.key]
                    if event.key == pygame.K_SPACE:
                        self.party_jump()
                    if event.key == pygame.K_m:
                        self.team_follow = not self.team_follow
                        self.mew_flash = 0.35
                    if event.key == pygame.K_e:
                        if self.mode == "overworld":
                            t, dist = self.nearest_tower()
                            if t is not None and dist is not None and dist < 90:
                                self.enter_dungeon(t)
                        else:
                            if self.dungeon_portal_near():
                                self.exit_dungeon()
                        c = (255, 245, 210)
                        for i in range(28):
                            ang = (i / 28.0) * math.tau
                            self.particles.append(Particle(self.leader().pos, pygame.Vector2(math.cos(ang), math.sin(ang)) * 160, c, 0.30, 2))

            if self.autotest_until and time.time() >= self.autotest_until:
                self.save_runtime_screenshot(self.autotest_screenshot)
                self.request_exit()

            leader = self.leader()
            # Audio: biome ambience/music crossfade in overworld
            if self.mode == "overworld":
                b0, b1, t = self.world.biome_mix(leader.pos.x)
                self.snd.update_overworld_biome(b0, b1, t)

            self.camera.x = leader.pos.x - SCREEN_W / 2
            self.camera.y = leader.pos.y - SCREEN_H / 2
            if self.mode == "dungeon" and self.dungeon is not None:
                max_x = max(0, self.dungeon.w * TILE - SCREEN_W)
                max_y = max(0, self.dungeon.h * TILE - SCREEN_H)
                self.camera.x = max(0, min(self.camera.x, max_x))
                self.camera.y = max(0, min(self.camera.y, max_y))

            self.update_encounters(dt)

            self.update_kittens(dt)
            self.update_squirrels(dt)
            self.try_collect_pickups()
            self.update_enemies(dt)
            self.update_projectiles(dt)
            self.update_particles(dt)
            self.update_slashes(dt)

            self.canvas.fill(BG)
            if self.mode == "dungeon" and self.dungeon is not None:
                self.dungeon.draw(self.canvas, self.camera)
            else:
                self.world.draw(self.canvas, self.camera)

                for sq in self.active_squirrels.values():
                    sq.draw(self.canvas, self.camera, self.squirrel_img)

                for p in self.iter_pickups_visible():
                    img = self.catnip_img if p.kind == "catnip" else (self.tuna_img if p.kind == "tuna" else self.whistle_img)
                    x = int(p.pos.x - self.camera.x - img.get_width() / 2)
                    y = int(p.pos.y - self.camera.y - img.get_height() / 2)
                    self.canvas.blit(img, (x, y))

                for t in self.iter_towers_visible():
                    t.draw(self.canvas, self.camera, cleared=(t.id in self.cleared_towers))

            for fx in self.particles:
                fx.draw(self.canvas, self.camera)
            for s in self.slashes:
                s.draw(self.canvas, self.camera)
            for p in self.projectiles:
                p.draw(self.canvas, self.camera)

            for e in self.enemies:
                e.draw(self.canvas, self.camera)
            for i, k in enumerate(self.kittens):
                k.draw(self.canvas, self.camera, selected=(i == self.leader_idx))

            self.draw_ui()
            self.present()

        self.save_runtime_screenshot(self.autotest_screenshot)
        self.shutdown()


if __name__ == "__main__":
    try:
        Game().run()
    except BaseException as exc:
        crash_path = _write_crash(exc)
        try:
            pygame.quit()
        except Exception:
            pass
        raise SystemExit(f"Crash report saved to {crash_path}")
