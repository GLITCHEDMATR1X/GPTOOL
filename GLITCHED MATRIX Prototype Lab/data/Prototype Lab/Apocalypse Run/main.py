import pygame
import random
import sys
import math
import os

import datetime

# =====================================================
# FX HELPERS (embedded from x_country_fx.py)
# =====================================================
# Defaults (kept here so x_country.py can stay focused on gameplay)
FX_DUST = (74, 64, 56)
FX_FIRE1 = (210, 110, 44)
FX_FIRE2 = (170, 80, 36)


def draw_vertical_gradient(surf, top, bottom):
    """Fill an entire surface with a vertical RGB gradient."""
    w, h = surf.get_size()
    if h <= 0 or w <= 0:
        return
    denom = (h - 1) if h > 1 else 1
    for y in range(h):
        t = y / denom
        c = (
            int(top[0] * (1 - t) + bottom[0] * t),
            int(top[1] * (1 - t) + bottom[1] * t),
            int(top[2] * (1 - t) + bottom[2] * t),
        )
        pygame.draw.line(surf, c, (0, y), (w, y))


def dither_fill(surf, c1, c2, step=2):
    """Cheap checker dither fill for gritty pixel-art vibes."""
    w, h = surf.get_size()
    if w <= 0 or h <= 0:
        return
    step = max(1, int(step))
    for y in range(0, h, step):
        for x in range(0, w, step):
            surf.set_at((x, y), c1 if ((x // step + y // step) & 1) == 0 else c2)


def draw_scanlines(surf, step=3):
    """Subtle CRT scanlines. Draws dark horizontal lines every `step` pixels."""
    w, h = surf.get_size()
    if w <= 0 or h <= 0:
        return
    step = max(1, int(step))
    for y in range(0, h, step):
        pygame.draw.line(surf, (0, 0, 0), (0, y), (w, y), 1)


class Particle:
    __slots__ = ("x", "y", "vx", "vy", "life", "color", "grow")
    def __init__(self, x, y, vx, vy, life, color, grow=False):
        self.x = float(x)
        self.y = float(y)
        self.vx = float(vx)
        self.vy = float(vy)
        self.life = int(life)
        self.color = color
        self.grow = bool(grow)

    def update(self):
        self.x += self.vx
        self.y += self.vy
        self.vx *= 0.98
        self.vy *= 0.98
        self.life -= 1

    def draw(self, surf):
        if self.life <= 0:
            return
        r = 2 if (self.grow and self.life < 18) else 1
        pygame.draw.circle(surf, self.color, (int(self.x), int(self.y)), r)

    def draw_screen(self, surf, cam_x, cam_y, base_w, base_h):
        if self.life <= 0:
            return
        sx = int(self.x - cam_x)
        sy = int(self.y - cam_y)
        if 0 <= sx < base_w and 0 <= sy < base_h:
            r = 2 if (self.grow and self.life < 18) else 1
            pygame.draw.circle(surf, self.color, (sx, sy), r)


class DustSystem:
    """Simple drifting dust motes for the road scenes."""
    def __init__(self, color=FX_DUST, base_h=360):
        self.p = []
        self.color = color
        self.base_h = int(base_h)

    def emit(self, x, y, n=1):
        for _ in range(int(n)):
            self.p.append([
                x + random.randint(-3, 3),
                y + random.randint(-2, 2),
                random.uniform(-1.2, -0.3),
                random.uniform(-0.2, 0.2),
                random.randint(10, 18),
            ])

    def update(self, scroll, base_h=None):
        bh = self.base_h if base_h is None else int(base_h)
        for d in self.p[:]:
            d[0] += d[2] - scroll * 0.2
            d[1] += d[3]
            d[4] -= 1
            if d[4] <= 0 or d[0] < -20 or d[1] > bh + 20:
                self.p.remove(d)

    def draw(self, surf):
        for x, y, _, _, life in self.p:
            r = 1 if life > 12 else 2
            pygame.draw.circle(surf, self.color, (int(x), int(y)), r)



class DebrisPiece:
    """Lightweight rectangle debris used for vehicle explosions.

    Coordinates are in *screen/world* space (same as gameplay objects).
    update(scroll) shifts the piece by the world's scroll value so debris stays
    anchored to the road background motion.
    """

    def __init__(self, x, y, vx, vy, w, h, color, life=90):
        self.x = float(x)
        self.y = float(y)
        self.vx = float(vx)
        self.vy = float(vy)
        self.w = int(max(1, w))
        self.h = int(max(1, h))
        self.color = tuple(color)
        self.life = int(life)

        # simple spin for visual richness
        self.ang = random.uniform(0.0, math.tau)
        self.ang_v = random.uniform(-0.22, 0.22)

    def update(self, scroll=0.0):
        # world scroll
        self.x -= float(scroll)

        # integrate
        self.x += self.vx
        self.y += self.vy
        self.vy += 0.18  # gravity

        # mild drag
        self.vx *= 0.985
        self.vy *= 0.99

        self.ang += self.ang_v
        self.life -= 1

    def draw(self, surf):
        if self.life <= 0:
            return
        # fade out near end
        alpha = 255 if self.life > 18 else int(max(0, min(255, self.life / 18.0 * 255)))
        col = (int(self.color[0]), int(self.color[1]), int(self.color[2]), alpha)

        # draw onto a tiny temp surface so we can rotate without depending on gfx libs
        tmp = pygame.Surface((self.w + 2, self.h + 2), pygame.SRCALPHA)
        pygame.draw.rect(tmp, col, (1, 1, self.w, self.h))
        rot = pygame.transform.rotate(tmp, (self.ang * 57.2958))  # rad->deg
        surf.blit(rot, (int(self.x - rot.get_width() * 0.5), int(self.y - rot.get_height() * 0.5)))


class Explosion:
    __slots__ = ("x", "y", "radius", "dmg", "life", "_c1", "_c2")
    def __init__(self, x, y, radius, dmg):
        self.x = float(x)
        self.y = float(y)
        self.radius = float(radius)
        self.dmg = int(dmg)
        self.life = 12
        self._c1 = FX_FIRE1
        self._c2 = FX_FIRE2

    def update(self):
        self.life -= 1

    def draw_screen(self, surf, cam_x, cam_y):
        if self.life <= 0:
            return
        t = self.life / 12.0
        r = int(self.radius * (1.0 - t * 0.3))
        col = self._c1 if self.life > 6 else self._c2
        pygame.draw.circle(surf, col, (int(self.x - cam_x), int(self.y - cam_y)), max(1, r), 1)



# =====================================================
# SIMPLE ASSET AUDIT LOGGER (non-fatal)
# =====================================================
class AssetLogger:
    """
    Writes a lightweight audit log for missing/empty asset folders and missing SFX keys.
    This is intentionally non-fatal: it must never crash the game.
    """
    def __init__(self, project_root):
        self.project_root = project_root
        self.log_dir = os.path.join(project_root, "logs")
        self._path = None
        self._seen = set()  # de-dupe identical lines per run
        try:
            os.makedirs(self.log_dir, exist_ok=True)
            day = datetime.datetime.now().strftime("%Y%m%d")
            self._path = os.path.join(self.log_dir, f"assets_audit_{day}.txt")
        except Exception:
            self._path = None

    def log(self, msg):
        if not msg:
            return
        try:
            if msg in self._seen:
                return
            self._seen.add(msg)
            ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            line = f"[{ts}] {msg}\n"
            if self._path:
                with open(self._path, "a", encoding="utf-8") as f:
                    f.write(line)
        except Exception:
            return

    def _has_audio_files(self, folder):
        try:
            if not os.path.isdir(folder):
                return False
            for name in os.listdir(folder):
                low = name.lower()
                if low.endswith((".wav", ".ogg", ".mp3")):
                    return True
        except Exception:
            return False
        return False

    def audit_audio_folders(self, folders, label="audio"):
        try:
            for p in folders:
                try:
                    rel = os.path.relpath(p, self.project_root)
                except Exception:
                    rel = str(p)
                if not os.path.isdir(p):
                    self.log(f"MISSING {label} folder: {rel}")
                else:
                    if not self._has_audio_files(p):
                        self.log(f"EMPTY {label} folder (no .wav/.ogg/.mp3): {rel}")
        except Exception:
            return

"""
X COUNTRY — Single-file Seamless Road <-> Pit Stop (expanded pit stop)

ROAD:
- D = throttle (consumes gas)
- LMB = shoot (vehicle roof gun if present)
- Gas reaches 0 => enters PIT STOP (same window)

PIT STOP (top-down):
- WASD move
- Auto-pickup by walking into items (fuel/ammo/medkits/weapons/explosives)
- LMB attack:
    - Unarmed: short-range punch
    - Armed: shoot (ammo required)
- RMB throw explosive (grenade/dynamite) if in inventory
- F uses a medkit if available
- TAB cycles owned weapons
- SPACE return to road (transfers all "FUEL" collected to vehicle gas; keeps inventory)

Notes:
- Inventory: 20 slots, stacks to 100/slot.
- Zombies are lightly animated (two-frame walk), less frequent than before.
- Dead zombies leave persistent blood splats.

Core loop is a single pygame window and switches mode state.
"""

# =====================================================
# RENDER SCALE (pixel look)
# =====================================================
SCALE = 2
BASE_W, BASE_H = 640, 360
SCREEN_W, SCREEN_H = BASE_W * SCALE, BASE_H * SCALE
FPS = 60

# Vehicle armor & upgrades
ARMOR_MAX_LEVEL = 10
ARMOR_DAMAGE_REDUCTION_PER_LEVEL = 0.06   # 6% less damage per level
ARMOR_MAX_REDUCTION = 0.60               # cap total reduction at 60%
ARMOR_UPGRADE_PART_COST = 4              # parts required per armor level

# Road layout
GROUND_Y = BASE_H - 86
ROAD_Y = GROUND_Y + 25
ROAD_H = 60
SCROLL_SPEED_MAX = 10.0

# Parallax strips
STRIP_W = 320
NUM_STRIPS = 9

MODE_ROAD = "road"
MODE_PIT = "pit"

# =====================================================
# PALETTE (Fallout-ish / rusty / gritty)
# =====================================================
OUTLINE = (10, 10, 12)

SKY_TOP = (16, 18, 20)
SKY_BOT = (56, 50, 46)
SUN = (150, 86, 40)
HAZE = (70, 60, 54)

ROAD = (24, 24, 26)
ROAD_DARK = (18, 18, 20)
ROAD_EDGE = (62, 54, 48)
LANE = (88, 80, 72)

DUST = (74, 64, 56)
SMOKE = (72, 72, 74)
FIRE1 = (210, 110, 44)
FIRE2 = (170, 80, 36)

SCRAP_DARK = (34, 32, 30)
SCRAP = (66, 60, 54)
RUST = (120, 70, 40)
RUST_DARK = (86, 50, 32)
STEEL = (92, 98, 104)
STEEL_DARK = (56, 60, 64)

UI_BG = (14, 14, 14)
UI_FG = (212, 206, 196)
OK = (92, 190, 96)
WARN = (210, 170, 72)
BAD = (210, 80, 72)

# Biomes (road)
BIOME_DESERT = "desert"
BIOME_SCRUB = "scrub"
BIOME_BADLANDS = "badlands"
BIOME_RUINS = "ruins"

GROUND_TINT = {
    BIOME_DESERT: (84, 68, 52),
    BIOME_SCRUB: (68, 70, 54),
    BIOME_BADLANDS: (68, 56, 52),
    BIOME_RUINS: (60, 60, 68),
}

# Pit stop palette
DIRT_A = (50, 44, 40)
DIRT_B = (42, 38, 34)
CRATE = (78, 62, 46)
WALL = (62, 62, 70)
WRECK = (46, 46, 50)
ROCK = (60, 54, 48)

GAS_CAN = (190, 120, 60)
GAS_CAN_DARK = (140, 80, 40)

AMMO_COL = (110, 150, 120)
AMMO_DARK = (70, 110, 86)

MED_COL = (190, 90, 90)
MED_DARK = (120, 40, 40)

WEAPON_COL = (120, 120, 132)
WEAPON_DARK = (80, 80, 92)

EXPLO_COL = (160, 140, 90)
EXPLO_DARK = (100, 86, 56)

PARTS_COL = (146, 132, 118)
PARTS_DARK = (86, 78, 70)

BULLET_COL = (220, 220, 180)
MUZZLE = (230, 210, 150)
SPARK = (200, 180, 120)

ZOMBIE_COL_A = (94, 148, 98)
ZOMBIE_COL_B = (78, 122, 82)
ZOMBIE_FACE = (40, 40, 40)

BLOOD = (120, 20, 20)
BLOOD_DARK = (70, 10, 10)

# =====================================================
# UTILS
# =====================================================
def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


def outline_rect(surf, rect, fill, outline=OUTLINE, radius=0):
    pygame.draw.rect(surf, outline, rect, border_radius=radius)
    inner = pygame.Rect(rect[0] + 1, rect[1] + 1, rect[2] - 2, rect[3] - 2)
    pygame.draw.rect(surf, fill, inner, border_radius=max(0, radius - 1))

def outline_poly(surf, pts, fill, outline=OUTLINE):
    pygame.draw.polygon(surf, outline, pts)
    pygame.draw.polygon(surf, fill, pts)

def v2_norm(dx, dy):
    mag = math.hypot(dx, dy)
    if mag <= 1e-6:
        return 0.0, 0.0
    return dx / mag, dy / mag

def point_in_radius(ax, ay, bx, by, r):
    return (ax - bx) * (ax - bx) + (ay - by) * (ay - by) <= r * r


# =====================================================
# ASSET PATHS + SAFE AUDIO
# =====================================================
def _project_root_dir():
    """
    Returns the directory containing this script. This makes asset loading robust
    regardless of the current working directory (double-click, shortcuts, etc.).
    """
    try:
        return os.path.dirname(os.path.abspath(__file__))
    except Exception:
        # Fallback: current working directory
        return os.getcwd()

PROJECT_ROOT = _project_root_dir()
ASSETS_DIR = os.path.join(PROJECT_ROOT, "assets")
SFX_DIR = os.path.join(ASSETS_DIR, "sfx")
MUSIC_DIR = os.path.join(ASSETS_DIR, "music")

# =====================================================
# ASSET RESOLVER (overlay-friendly)
# =====================================================
# To override assets without editing the game, set:
#   ASSET_OVERLAY_DIR=<path to your overlay folder>
# and mirror the in-game relative paths under that folder.
#
# Example:
#   Game asks: assets/sfx/road/mg/<first .wav/.ogg/.mp3>
#   Overlay:   <ASSET_OVERLAY_DIR>/assets/sfx/road/mg/my_mg.ogg
#
# This resolver is intentionally defensive and will never crash the game.
ASSET_OVERLAY_DIR = os.environ.get("ASSET_OVERLAY_DIR", "").strip()
ASSET_ROOTS = []
try:
    if ASSET_OVERLAY_DIR:
        ASSET_ROOTS.append(os.path.abspath(ASSET_OVERLAY_DIR))
except Exception:
    pass
ASSET_ROOTS.append(ASSETS_DIR)

def _norm_rel(p):
    try:
        return str(p).replace("\\", "/").lstrip("/")
    except Exception:
        return str(p)

def resolve_asset(rel_path):
    '''
    Resolve an asset path against:
      1) ASSET_OVERLAY_DIR (if set)
      2) the game's own ./assets folder

    rel_path may be:
      - relative within assets (e.g. 'images/player.png')
      - or start with 'assets/' (both are accepted)

    Returns an absolute path if found, else None.
    '''
    rel = _norm_rel(rel_path)
    if rel.startswith("assets/"):
        rel = rel[len("assets/"):]
    for root in ASSET_ROOTS:
        try:
            cand = os.path.join(root, *rel.split("/"))
            if os.path.isfile(cand):
                return cand
        except Exception:
            continue
    return None

def load_image(rel_path, size=None, alpha=True, colorkey=None, logger=None):
    '''
    Safe image load for future sprite replacements.
    - Returns a pygame.Surface (placeholder if missing).
    - size: (w,h) to scale to.
    '''
    try:
        path = resolve_asset(rel_path)
        if path:
            img = pygame.image.load(path)
            img = img.convert_alpha() if alpha else img.convert()
            if colorkey is not None:
                img.set_colorkey(colorkey)
            if size:
                img = pygame.transform.smoothscale(img, (int(size[0]), int(size[1])))
            return img
        if logger is not None:
            logger.log("NO IMAGE for key: %s" % (rel_path,))
    except Exception:
        if logger is not None:
            logger.log("IMAGE LOAD FAILED for key: %s" % (rel_path,))
    w, h = (32, 32) if not size else (max(2, int(size[0])), max(2, int(size[1])))
    ph = pygame.Surface((w, h), pygame.SRCALPHA)
    ph.fill((180, 0, 180, 255))
    pygame.draw.rect(ph, (10, 10, 12, 255), (0, 0, w, h), 2)
    return ph

def load_font(rel_path, size, fallback_name="consolas", logger=None):
    '''
    Safe font load:
      - If rel_path exists in overlay/assets -> pygame.font.Font(file, size)
      - Else -> pygame.font.SysFont(fallback_name, size)
    '''
    try:
        if rel_path:
            path = resolve_asset(rel_path)
            if path:
                return pygame.font.Font(path, int(size))
            if logger is not None:
                logger.log("NO FONT for key: %s" % (rel_path,))
    except Exception:
        if logger is not None:
            logger.log("FONT LOAD FAILED for key: %s" % (rel_path,))
    try:
        return pygame.font.SysFont(fallback_name, int(size))
    except Exception:
        return pygame.font.Font(None, int(size))

def ensure_dir(path):
    try:
        os.makedirs(path, exist_ok=True)
    except Exception:
        # Never crash on directory creation
        pass

def ensure_asset_folders():
    """
    Creates the expected folder structure on launch.
    These folders may be empty; audio must never crash when missing.

    Returns:
        dict with keys:
            - 'sfx': list of absolute folders under assets/sfx
            - 'music': list of absolute folders under assets/music
    """
    sfx_folders = []
    music_folders = []

    def _mk(p):
        ensure_dir(p)
        return p

    _mk(ASSETS_DIR)
    _mk(SFX_DIR)
    _mk(MUSIC_DIR)

    # Image + font buckets (optional; game is procedural by default)
    _mk(os.path.join(ASSETS_DIR, "images"))
    _mk(os.path.join(ASSETS_DIR, "images", "ui"))
    _mk(os.path.join(ASSETS_DIR, "images", "items"))
    _mk(os.path.join(ASSETS_DIR, "images", "actors"))
    _mk(os.path.join(ASSETS_DIR, "fonts"))


    # Existing (root buckets)
    sfx_folders.append(_mk(os.path.join(SFX_DIR, "road")))
    sfx_folders.append(_mk(os.path.join(SFX_DIR, "pit")))

    # Road SFX
    sfx_folders.append(_mk(os.path.join(SFX_DIR, "road", "mg")))
    sfx_folders.append(_mk(os.path.join(SFX_DIR, "road", "enemy_mg")))
    sfx_folders.append(_mk(os.path.join(SFX_DIR, "road", "explosion")))
    sfx_folders.append(_mk(os.path.join(SFX_DIR, "road", "hit_metal")))
    sfx_folders.append(_mk(os.path.join(SFX_DIR, "road", "hit_soft")))
    sfx_folders.append(_mk(os.path.join(SFX_DIR, "road", "pit_enter")))
    sfx_folders.append(_mk(os.path.join(SFX_DIR, "road", "vehicle_damage")))
    sfx_folders.append(_mk(os.path.join(SFX_DIR, "road", "vehicle_idle")))
    sfx_folders.append(_mk(os.path.join(SFX_DIR, "road", "vehicle_throttle")))

    # Optional legacy-compatible layout (harmless if unused)
    sfx_folders.append(_mk(os.path.join(SFX_DIR, "vehicle")))
    sfx_folders.append(_mk(os.path.join(SFX_DIR, "vehicle", "idle")))
    sfx_folders.append(_mk(os.path.join(SFX_DIR, "vehicle", "throttle")))

    # Pit SFX
    sfx_folders.append(_mk(os.path.join(SFX_DIR, "pit", "pickup")))
    sfx_folders.append(_mk(os.path.join(SFX_DIR, "pit", "hurt")))
    sfx_folders.append(_mk(os.path.join(SFX_DIR, "pit", "runout_ammo")))
    sfx_folders.append(_mk(os.path.join(SFX_DIR, "pit", "pistol")))
    sfx_folders.append(_mk(os.path.join(SFX_DIR, "pit", "rifle")))
    sfx_folders.append(_mk(os.path.join(SFX_DIR, "pit", "shotgun")))
    sfx_folders.append(_mk(os.path.join(SFX_DIR, "pit", "smg")))
    sfx_folders.append(_mk(os.path.join(SFX_DIR, "pit", "marksman")))
    sfx_folders.append(_mk(os.path.join(SFX_DIR, "pit", "grenade")))
    sfx_folders.append(_mk(os.path.join(SFX_DIR, "pit", "dynamite")))
    sfx_folders.append(_mk(os.path.join(SFX_DIR, "pit", "explosion")))
    sfx_folders.append(_mk(os.path.join(SFX_DIR, "pit", "zombie_death")))
    sfx_folders.append(_mk(os.path.join(SFX_DIR, "pit", "medkit")))

    # Music folders
    music_folders.append(_mk(os.path.join(MUSIC_DIR, "road")))
    music_folders.append(_mk(os.path.join(MUSIC_DIR, "pit")))

    return {"sfx": sfx_folders, "music": music_folders}


class AudioManager:
    """
    Ultra-defensive audio loader/player:
    - Uses assets/ relative to this script (not cwd)
    - Missing files never crash
    - If mixer fails (no audio device), it gracefully disables audio
    - Logs missing/empty folders and missing SFX keys (de-duped) when a logger is provided
    """
    def __init__(self, assets_dir, asset_logger=None):
        self.assets_dir = assets_dir
        self.enabled = False
        self.mixer_ok = False
        self.sfx_cache = {}  # key -> pygame.mixer.Sound
        self.logger = asset_logger
        self._warned_folders = set()
        self._warned_keys = set()

        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            self.mixer_ok = True
            self.enabled = True

            # Reserve dedicated channels for looped engine audio (kept separate from one-shot SFX).
            try:
                pygame.mixer.set_num_channels(16)
                self._channels = {
                    "engine": pygame.mixer.Channel(1),
                    "enemy_engine": pygame.mixer.Channel(2),
                }
            except Exception:
                self._channels = {}
            self._loop_state = {
                "engine": {"key": None, "sound": None},
                "enemy_engine": {"key": None, "sound": None},
            }
        except Exception:
            self.mixer_ok = False
            self.enabled = False

    def _pick_first_audio_file(self, folder):
        """
        Returns the first audio file path in the folder (mp3/ogg/wav), or None.
        """
        try:
            if not os.path.isdir(folder):
                if self.logger is not None:
                    key = ("missing:" + str(folder)).replace("\\", "/")
                    if key not in self._warned_folders:
                        self._warned_folders.add(key)
                        try:
                            rel = os.path.relpath(folder, PROJECT_ROOT)
                        except Exception:
                            rel = folder
                        self.logger.log(f"MISSING audio folder: {rel}")
                return None

            for name in sorted(os.listdir(folder)):
                low = name.lower()
                if low.endswith((".wav", ".ogg", ".mp3")):
                    return os.path.join(folder, name)

            if self.logger is not None:
                key = ("empty:" + str(folder)).replace("\\", "/")
                if key not in self._warned_folders:
                    self._warned_folders.add(key)
                    try:
                        rel = os.path.relpath(folder, PROJECT_ROOT)
                    except Exception:
                        rel = folder
                    self.logger.log(f"EMPTY audio folder (no .wav/.ogg/.mp3): {rel}")
        except Exception:
            return None
        return None

    def _get_sound(self, rel_folder):
        """
        rel_folder is relative to assets/sfx, e.g. "road/mg"
        """
        if not self.enabled:
            return None
        key = rel_folder.replace("\\", "/")
        if key in self.sfx_cache:
            return self.sfx_cache[key]

        folder = os.path.join(self.assets_dir, "sfx", *key.split("/"))
        path = self._pick_first_audio_file(folder)
        if not path:
            self.sfx_cache[key] = None
            return None

        try:
            snd = pygame.mixer.Sound(path)
            self.sfx_cache[key] = snd
            return snd
        except Exception:
            self.sfx_cache[key] = None
            return None

    def play(self, rel_folder, volume=0.9):
        """
        Safe no-op if missing/disabled.
        """
        snd = self._get_sound(rel_folder)
        if snd is None:
            if self.logger is not None:
                k = ("nosfx:" + str(rel_folder)).replace("\\", "/")
                if k not in self._warned_keys:
                    self._warned_keys.add(k)
                    self.logger.log(f"NO SFX found for key: {rel_folder}")
            return False
        try:
            snd.set_volume(max(0.0, min(1.0, float(volume))))
            snd.play()
            return True
        except Exception:
            return False


    def play_loop(self, rel_folder, volume=0.8, channel_name="engine"):
        """Play a loop from the *first* mp3 found in assets/sfx/<rel_folder>.

        If the loop is already playing from the same folder, this is a no-op.
        """
        if not self.enabled or not self.mixer_ok:
            return False
        ch = self._channels.get(channel_name)
        if ch is None:
            return False
        key = rel_folder.replace("\\", "/").strip("/")
        # If already on this key, keep playing.
        if self._loop_state.get(channel_name, {}).get("key") == key and ch.get_busy():
            return True
        snd = self._get_sound(key)
        if snd is None:
            return False
        try:
            ch.set_volume(max(0.0, min(1.0, float(volume))))
            ch.play(snd, loops=-1)
            self._loop_state[channel_name] = {"key": key, "sound": snd}
            return True
        except Exception:
            return False

    def stop_loop(self, channel_name="engine"):
        if not self.enabled or not self.mixer_ok:
            return
        ch = self._channels.get(channel_name)
        if ch is None:
            return
        try:
            ch.stop()
        except Exception:
            pass
        if channel_name in self._loop_state:
            self._loop_state[channel_name]["key"] = None
            self._loop_state[channel_name]["sound"] = None

    def set_player_engine_state(self, throttle_active):
        """Switch between idle and throttle engine loops (player vehicle)."""
        # Prefer the requested folder structure:
        #   assets/sfx/vehicle/idle
        #   assets/sfx/vehicle/throttle
        if throttle_active:
            if self.play_loop("vehicle/throttle", volume=0.85, channel_name="engine"):
                return
            # Backwards-compatible fallback (older builds)
            self.play_loop("road/vehicle_throttle", volume=0.85, channel_name="engine")
        else:
            if self.play_loop("vehicle/idle", volume=0.75, channel_name="engine"):
                return
            self.play_loop("road/vehicle_idle", volume=0.75, channel_name="engine")



    # -----------------------------
    # MUSIC (assets/music/<mode>/)
    # -----------------------------
    def _music_folder(self, rel_folder):
        key = (rel_folder or "").replace("\\", "/").strip("/")
        return os.path.join(self.assets_dir, "music", *key.split("/")) if key else os.path.join(self.assets_dir, "music")

    def play_music(self, rel_folder, volume=0.65):
        """
        Plays the first audio file found in assets/music/<rel_folder>/ on loop.
        Safe no-op if audio is disabled or no file exists.
        """
        if not self.enabled:
            return False

        # Lazy init music state
        if not hasattr(self, "_music_key"):
            self._music_key = None
            self._music_path = None

        key = (rel_folder or "").replace("\\", "/").strip("/")
        folder = self._music_folder(key)
        path = self._pick_first_audio_file(folder)
        if not path:
            if self.logger is not None:
                k = ("nomusic:" + str(key)).replace("\\", "/")
                if k not in self._warned_keys:
                    self._warned_keys.add(k)
                    self.logger.log(f"NO MUSIC found for key: {key}")
            return False

        if self._music_path == path and pygame.mixer.music.get_busy():
            # Already playing this track
            return True

        try:
            pygame.mixer.music.load(path)
            pygame.mixer.music.set_volume(max(0.0, min(1.0, float(volume))))
            pygame.mixer.music.play(-1)
            self._music_key = key
            self._music_path = path
            return True
        except Exception:
            return False

    def stop_music(self):
        if not self.enabled:
            return
        try:
            pygame.mixer.music.stop()
        except Exception:
            return


# =====================================================
# INVENTORY (20 slots, stack 100)
# =====================================================
class Inventory:
    def __init__(self, slots=20, stack_max=100):
        self.slots = [None] * slots  # each: (item_id, qty)
        self.stack_max = stack_max

    def add(self, item_id, qty):
        if qty <= 0:
            return 0
        remaining = int(qty)

        # fill existing stacks
        for i, s in enumerate(self.slots):
            if s and s[0] == item_id and s[1] < self.stack_max:
                take = min(self.stack_max - s[1], remaining)
                self.slots[i] = (item_id, s[1] + take)
                remaining -= take
                if remaining <= 0:
                    return 0

        # open new stacks
        for i, s in enumerate(self.slots):
            if s is None:
                take = min(self.stack_max, remaining)
                self.slots[i] = (item_id, take)
                remaining -= take
                if remaining <= 0:
                    return 0

        return remaining  # couldn't fit

    def count(self, item_id):
        total = 0
        for s in self.slots:
            if s and s[0] == item_id:
                total += s[1]
        return total

    def consume(self, item_id, qty):
        need = int(qty)
        if need <= 0:
            return True

        for i, s in enumerate(self.slots):
            if not s or s[0] != item_id:
                continue
            take = min(s[1], need)
            need -= take
            left = s[1] - take
            self.slots[i] = (item_id, left) if left > 0 else None
            if need <= 0:
                return True
        return False

    def owned_weapons(self):
        weps = []
        for w in ["weapon_pistol", "weapon_rifle", "weapon_shotgun", "weapon_smg", "weapon_marksman"]:
            if self.count(w) > 0:
                weps.append(w)
        return weps

# =====================================================
# PARTICLES / BULLETS (shared style)
# =====================================================

class Bullet:
    __slots__ = ("x", "y", "vx", "vy", "life", "owner", "dmg")
    def __init__(self, x, y, vx, vy, owner, dmg=20):
        self.x = float(x)
        self.y = float(y)
        self.vx = float(vx)
        self.vy = float(vy)
        self.life = 70
        self.owner = owner
        self.dmg = dmg

    def update(self):
        self.x += self.vx
        self.y += self.vy
        self.life -= 1

    def draw(self, surf):
        pygame.draw.rect(surf, BULLET_COL, (int(self.x), int(self.y), 3, 1))

    def rect(self):
        # Slightly generous hitbox so fast bullets reliably register impacts.
        return pygame.Rect(int(self.x), int(self.y) - 1, 5, 3)

    def draw_screen(self, surf, cam_x, cam_y):
        sx = int(self.x - cam_x)
        sy = int(self.y - cam_y)
        pygame.draw.rect(surf, BULLET_COL, (sx, sy, 3, 1))

# =====================================================
# ROAD VEHICLE GENERATION (procedural steampunk junkers)
# =====================================================
class VehicleStyle:
    def __init__(self, seed):
        rng = random.Random(seed)
        self.kind = rng.choices(["car", "van", "truck"], weights=[6, 3, 2], k=1)[0]

        self.body = rng.choice([SCRAP_DARK, (40, 38, 36), (46, 42, 40)])
        self.body2 = rng.choice([SCRAP, (62, 58, 52), (72, 64, 56)])
        self.rust = rng.choice([RUST, RUST_DARK, (132, 78, 44)])
        self.steel = rng.choice([STEEL, STEEL_DARK])

        if self.kind == "car":
            self.L = rng.randint(78, 90)
            self.H = rng.randint(24, 28)
            self.cab_x = rng.randint(20, 26)
            self.cab_w = rng.randint(32, 38)
        elif self.kind == "van":
            self.L = rng.randint(86, 98)
            self.H = rng.randint(26, 30)
            self.cab_x = rng.randint(18, 22)
            self.cab_w = rng.randint(40, 46)
        else:
            self.L = rng.randint(96, 112)
            self.H = rng.randint(28, 34)
            self.cab_x = rng.randint(16, 22)
            self.cab_w = rng.randint(36, 42)

        self.has_roof_gun = rng.random() < (0.55 if self.kind != "truck" else 0.65)
        self.has_side_spikes = rng.random() < 0.45
        self.has_ram = rng.random() < 0.75
        self.has_exposed_engine = rng.random() < (0.55 if self.kind == "car" else 0.40)
        self.has_roof_rack = rng.random() < 0.45
        self.has_fender_armor = rng.random() < 0.65

        self.decal = rng.choice(["stripe", "slash", "none"])
        self.decal_color = rng.choice([self.rust, (150, 70, 40)])

class PlayerVehicle:
    def __init__(self):
        self.x = 110
        self.y = GROUND_Y - 34
        self.speed = 0.0
        self.max_health = 100.0
        self.gas = 100.0   # can exceed 100 (unbounded from pit stop)
        self.health = self.max_health
        self.armor_level = 0

        self._phase = 0.0
        self._susp = 0.0
        self.style = VehicleStyle(random.randint(0, 2**31 - 1))
        self.shoot_cd = 0

    def update(self, throttle):
        if throttle and self.gas > 0:
            self.speed = min(self.speed + 0.28, SCROLL_SPEED_MAX)
            self.gas -= 0.045 * self.speed
        else:
            self.speed *= 0.955

        if self.gas < 0:
            self.gas = 0

        self._phase += self.speed * 0.38
        self._susp = math.sin(self._phase * 0.6) * min(1.6, 0.4 + self.speed * 0.10)

        if self.shoot_cd > 0:
            self.shoot_cd -= 1


    def armor_reduction(self):
        return min(ARMOR_MAX_REDUCTION, float(self.armor_level) * ARMOR_DAMAGE_REDUCTION_PER_LEVEL)

    def apply_damage(self, dmg):
        # Damage is reduced by current armor level.
        red = self.armor_reduction()
        actual = float(dmg) * (1.0 - red)
        self.health = max(0.0, self.health - actual)
        return actual

    def gun_muzzle(self):
        # Turret muzzle point (used for spawning bullets + muzzle FX)
        s = self.style
        x = int(self.x)
        y = int(self.y + self._susp)

        # place turret roughly over the cab roof
        turret_x = x + s.cab_x + int(s.cab_w * 0.55)
        turret_y = y + 6  # roof height baseline
        barrel_len = 18
        return turret_x + barrel_len, turret_y - 4

    def shoot(self, bullets, particles, audio=None):
        # Improved roof MG: faster ROF, slight recoil spread, stronger feedback
        if self.shoot_cd > 0:
            return False
        mx, my = self.gun_muzzle()

        spread = random.uniform(-0.35, 0.35)
        bullets.append(Bullet(mx, my + spread, 9.2, spread * 0.35, "player_vehicle", dmg=14))

        # muzzle flare + sparks + brief ember
        particles.append(Particle(mx + 1, my, random.uniform(0.6, 1.2), random.uniform(-0.6, 0.1), 10, MUZZLE, grow=False))
        particles.append(Particle(mx + 2, my + 1, random.uniform(0.2, 0.6), random.uniform(-0.2, 0.2), 8, SPARK, grow=False))
        particles.append(Particle(mx + 1, my, random.uniform(0.2, 0.8), random.uniform(-0.2, 0.1), 12, FIRE1, grow=True))

        self.shoot_cd = 3
        if audio is not None:
            audio.play('road/mg', volume=0.85)
        return True
    def draw(self, surf):
        s = self.style
        x = int(self.x)
        y = int(self.y + self._susp)
        L = s.L
        H = s.H

        pygame.draw.ellipse(surf, (0, 0, 0), (x + 6, y + H + 8, L - 6, 8))

        outline_rect(surf, (x, y + 10, L, 16 if H <= 28 else 18), s.body, radius=2)
        pygame.draw.rect(surf, (18, 18, 20), (x + 6, y + 14, L - 12, 8), border_radius=2)

        cab_x = x + s.cab_x
        if s.kind == "van":
            pts = [(cab_x, y + 18), (cab_x + s.cab_w, y + 18), (cab_x + s.cab_w + 10, y + 10), (cab_x + 6, y + 8)]
        elif s.kind == "truck":
            pts = [(cab_x, y + 20), (cab_x + s.cab_w, y + 20), (cab_x + s.cab_w + 12, y + 12), (cab_x + 8, y + 8)]
            outline_rect(surf, (x + int(L * 0.62), y + 14, int(L * 0.28), 6), s.body2, radius=1)
        else:
            pts = [(cab_x, y + 18), (cab_x + s.cab_w, y + 18), (cab_x + s.cab_w + 10, y + 10), (cab_x + 8, y + 8)]
        outline_poly(surf, pts, s.body2)

        pygame.draw.rect(surf, (78, 96, 108), (cab_x + 14, y + 12, 10, 4))
        pygame.draw.rect(surf, (40, 54, 62), (cab_x + 15, y + 13, 8, 2))
        # Driver head popping out the window (player is the driver)
        # Small outline head + eye, Fallout-ish
        head_x = cab_x + 18
        head_y = y + 12
        pygame.draw.circle(surf, OUTLINE, (head_x, head_y), 4)
        pygame.draw.circle(surf, (170, 150, 92), (head_x, head_y), 3)
        pygame.draw.rect(surf, (30, 30, 34), (head_x + 1, head_y - 1, 2, 1))

        # Roof turret + gunner (use pit-stop player silhouette as the gunman)
        turret_base_x = cab_x + int(s.cab_w * 0.55)
        turret_base_y = y + 6

        # hatch ring
        pygame.draw.circle(surf, OUTLINE, (turret_base_x, turret_base_y), 5)
        pygame.draw.circle(surf, STEEL_DARK, (turret_base_x, turret_base_y), 4)

        # gunner torso (pops from hatch)
        outline_rect(surf, (turret_base_x - 4, turret_base_y - 12, 8, 10), (178, 162, 90), radius=1)
        pygame.draw.rect(surf, (40, 40, 40), (turret_base_x - 2, turret_base_y - 8, 4, 2))  # face shadow
        pygame.draw.rect(surf, (48, 40, 34), (turret_base_x - 4, turret_base_y - 4, 8, 2))   # belt

        # turret barrel (fixed facing right)
        barrel_len = 18
        pygame.draw.rect(surf, STEEL, (turret_base_x + 2, turret_base_y - 6, barrel_len, 2))
        pygame.draw.rect(surf, STEEL_DARK, (turret_base_x + barrel_len + 1, turret_base_y - 7, 2, 4))


        if s.has_exposed_engine:
            outline_rect(surf, (x + int(L * 0.64), y + 8, 14, 8), s.steel, radius=2)
            pygame.draw.rect(surf, s.steel, (x + int(L * 0.64) + 6, y + 4, 5, 16))
            pygame.draw.circle(surf, s.rust, (x + int(L * 0.64) + 2, y + 12), 2)
            pygame.draw.circle(surf, s.rust, (x + int(L * 0.64) + 12, y + 12), 2)

        if s.has_ram:
            outline_rect(surf, (x + L - 4, y + 12, 8, 10), s.steel, radius=1)
            outline_poly(surf, [(x + L + 4, y + 13), (x + L + 12, y + 16), (x + L + 4, y + 19)], s.steel)

        if s.has_side_spikes:
            sx = x + int(L * 0.55)
            outline_poly(surf, [(sx, y + 22), (sx + 8, y + 20), (sx + 8, y + 24)], s.steel)
            outline_poly(surf, [(sx + 12, y + 22), (sx + 20, y + 20), (sx + 20, y + 24)], s.steel)

        if s.has_roof_rack:
            outline_rect(surf, (cab_x + 6, y + 2, 22, 4), s.steel, radius=1)
            pygame.draw.rect(surf, s.steel, (cab_x + 8, y + 0, 3, 6))
            pygame.draw.rect(surf, s.steel, (cab_x + 24, y + 0, 3, 6))

        if s.has_roof_gun:
            outline_rect(surf, (cab_x + 18, y - 6, 8, 4), s.steel, radius=1)
            pygame.draw.rect(surf, s.steel, (cab_x + 22, y - 8, 12, 2))
            pygame.draw.rect(surf, s.steel, (cab_x + 20, y - 2, 3, 8))

        if s.has_fender_armor:
            outline_rect(surf, (x + 4, y + 16, 18, 5), s.rust, radius=1)
            outline_rect(surf, (x + 36, y + 20, 20, 5), s.rust, radius=1)

        if s.decal != "none":
            if s.decal == "stripe":
                pygame.draw.line(surf, s.decal_color, (x + 18, y + 20), (x + 42, y + 14), 2)
                pygame.draw.line(surf, s.decal_color, (x + 20, y + 24), (x + 44, y + 18), 1)
            else:
                pygame.draw.line(surf, s.decal_color, (x + 32, y + 24), (x + 46, y + 14), 2)

        for i in range(max(5, L // 18)):
            pygame.draw.circle(surf, (110, 110, 110), (x + 10 + i * 14, y + 23 + (i & 1)), 1)

        outline_rect(surf, (x + 14, y + H + 2, 14, 7), (16, 16, 16), radius=1)
        outline_rect(surf, (x + L - 28, y + H + 2, 14, 7), (16, 16, 16), radius=1)
        pygame.draw.rect(surf, s.steel, (x + 18, y + H + 4, 6, 3))
        pygame.draw.rect(surf, s.steel, (x + L - 24, y + H + 4, 6, 3))

        if self.speed > 2.0 and random.random() < 0.25:
            pygame.draw.circle(surf, (62, 62, 62), (x - 6, y + 22), random.randint(1, 2))

# =====================================================
# ROAD BACKGROUND STRIPS (pre-rendered)
# =====================================================
class WorldStrip:
    def __init__(self, world_x, biome, seed=None, rng=None):
        self.world_x = world_x
        self.biome = biome
        self.seed = int(seed) if seed is not None else (rng.randint(0, 2**31 - 1) if rng is not None else random.randint(0, 2**31 - 1))
        rng = random.Random(self.seed)

        self.far = pygame.Surface((STRIP_W, BASE_H), pygame.SRCALPHA)
        self.far.fill((0, 0, 0, 0))
        base_y = GROUND_Y - rng.randint(110, 140)
        far_col = (30, 30, 36) if biome != BIOME_RUINS else (26, 26, 34)

        x = -30
        while x < STRIP_W + 40:
            w = rng.randint(40, 90)
            h = rng.randint(40, 100)
            y = base_y - h
            pygame.draw.rect(self.far, far_col, (x, y, w, h))
            x += rng.randint(30, 70)

        if biome == BIOME_RUINS:
            skyl_y = GROUND_Y - rng.randint(86, 104)
            x = rng.randint(-20, 30)
            for _ in range(rng.randint(8, 14)):
                w = rng.randint(14, 34)
                h = rng.randint(36, 120)
                pygame.draw.rect(self.far, (38, 38, 48), (x, skyl_y - h, w, h))
                if rng.random() < 0.6:
                    pygame.draw.rect(self.far, (20, 20, 26), (x + rng.randint(0, 5), skyl_y - h, w - rng.randint(4, 8), rng.randint(4, 7)))
                x += w + rng.randint(6, 14)

        self.mid = pygame.Surface((STRIP_W, BASE_H), pygame.SRCALPHA)
        self.mid.fill((0, 0, 0, 0))
        mid_col = (52, 50, 48) if biome != BIOME_RUINS else (54, 54, 62)

        n_mid = rng.randint(8, 14)
        for _ in range(n_mid):
            px = rng.randint(0, STRIP_W - 10)
            kind_pool = ["pole", "dead_tree", "wreck", "sign"]
            if biome == BIOME_RUINS:
                kind_pool += ["building", "building"]
            kind = rng.choice(kind_pool)

            if kind == "pole":
                h = rng.randint(34, 74)
                y = GROUND_Y - 12 - h
                pygame.draw.rect(self.mid, mid_col, (px, y, 3, h))
                if rng.random() < 0.45:
                    pygame.draw.rect(self.mid, mid_col, (px - 8, y + rng.randint(10, 22), 20, 2))
                if rng.random() < 0.25:
                    pygame.draw.line(self.mid, (38, 36, 34), (px + 1, y + 10), (px + 20, y + 18), 1)

            elif kind == "dead_tree":
                h = rng.randint(44, 86)
                y = GROUND_Y - 10 - h
                pygame.draw.rect(self.mid, mid_col, (px, y, 4, h))
                pygame.draw.rect(self.mid, mid_col, (px - 10, y + 18, 10, 2))
                pygame.draw.rect(self.mid, mid_col, (px + 4, y + 30, 10, 2))

            elif kind == "wreck":
                w = rng.randint(18, 42)
                h = rng.randint(10, 16)
                y = GROUND_Y + rng.randint(1, 10)
                pygame.draw.rect(self.mid, (42, 40, 38), (px, y - h, w, h))
                pygame.draw.rect(self.mid, (22, 22, 24), (px + 4, y - h + 3, w - 8, h - 6))

            elif kind == "car_wreck":
                outline_rect(surf, rr, self.pal['wreck'], radius=2)
                pygame.draw.rect(surf, (18, 18, 20), (rr.x + 3, rr.y + 3, rr.w - 6, rr.h - 6), border_radius=2)
                pygame.draw.rect(surf, (10, 10, 12), (rr.x + 2, rr.y + 1, 3, 3))
                pygame.draw.rect(surf, (10, 10, 12), (rr.x + rr.w - 5, rr.y + 1, 3, 3))
                pygame.draw.rect(surf, (10, 10, 12), (rr.x + 2, rr.y + rr.h - 4, 3, 3))
                pygame.draw.rect(surf, (10, 10, 12), (rr.x + rr.w - 5, rr.y + rr.h - 4, 3, 3))
            elif kind == "graveyard":
                outline_rect(surf, rr, self.pal['wall'], radius=2)
                for _ in range(18):
                    tx = rr.x + random.randint(4, max(4, rr.w - 8))
                    ty = rr.y + random.randint(4, max(4, rr.h - 8))
                    pygame.draw.rect(surf, self.pal.get('decor_a', (90, 90, 100)), (tx, ty, 3, 4), border_radius=2)
                for _ in range(5):
                    tx = rr.x + random.randint(6, max(6, rr.w - 10))
                    ty = rr.y + random.randint(6, max(6, rr.h - 10))
                    pygame.draw.rect(surf, self.pal.get('decor_b', (46, 46, 52)), (tx, ty, 1, 6))
                    pygame.draw.rect(surf, self.pal.get('decor_b', (46, 46, 52)), (tx - 2, ty + 2, 5, 1))
            elif kind == "mausoleum":
                outline_rect(surf, rr, self.pal['building'], radius=3)
                pygame.draw.rect(surf, self.pal.get('window', (18, 18, 24)), (rr.x + rr.w // 2 - 6, rr.y + 8, 12, 5))
                pygame.draw.rect(surf, self.pal.get('accent', (120, 20, 20)), (rr.x + rr.w // 2 - 2, rr.y + rr.h - 12, 4, 8))
            elif kind == "lot":
                outline_rect(surf, rr, self.pal['dirt_b'], radius=2)
            elif kind == "store":
                outline_rect(surf, rr, self.pal['building'], radius=2)
                pygame.draw.rect(surf, self.pal.get('window', (22, 22, 28)), (rr.x + 8, rr.y + rr.h // 2 - 3, rr.w - 16, 6))
            elif kind == "sign":
                h = rng.randint(34, 70)
                y = GROUND_Y - 6 - h
                pygame.draw.rect(self.mid, mid_col, (px, y, 3, h))
                pygame.draw.rect(self.mid, (70, 60, 50), (px - 10, y + 10, 26, 10))
                pygame.draw.rect(self.mid, (26, 24, 22), (px - 9, y + 11, 24, 8))
                pygame.draw.line(self.mid, (120, 70, 40), (px - 6, y + 15), (px + 12, y + 15), 1)

            else:
                bw = rng.randint(18, 46)
                bh = rng.randint(40, 120)
                by = GROUND_Y - 4 - bh
                col = (50, 50, 58)
                pygame.draw.rect(self.mid, col, (px, by, bw, bh))
                for wy in range(by + 8, by + bh - 8, 12):
                    if rng.random() < 0.8:
                        pygame.draw.rect(self.mid, (24, 24, 30), (px + 6, wy, 8, 4))
                    if rng.random() < 0.6:
                        pygame.draw.rect(self.mid, (60, 42, 34), (px + bw - 14, wy, 8, 4))
                if rng.random() < 0.22:
                    pygame.draw.rect(self.mid, (70, 62, 54), (px + 4, by + 10, bw - 8, 8))
                    pygame.draw.rect(self.mid, (30, 28, 26), (px + 5, by + 11, bw - 10, 6))

        self.near = pygame.Surface((STRIP_W, BASE_H), pygame.SRCALPHA)
        self.near.fill((0, 0, 0, 0))
        n_near = rng.randint(18, 34)
        for _ in range(n_near):
            px = rng.randint(0, STRIP_W - 1)
            py = rng.randint(GROUND_Y + 2, BASE_H - 1)
            if py < ROAD_Y:
                c = (58, 52, 46) if biome == BIOME_DESERT else (52, 54, 50)
                pygame.draw.circle(self.near, c, (px, py), rng.randint(1, 2))
            else:
                pygame.draw.rect(self.near, (44, 44, 46), (px, py, 1, 1))

        self.ground_band = pygame.Surface((STRIP_W, 120))
        base = GROUND_TINT[biome]
        self.ground_band.fill(base)
        dither_fill(
            self.ground_band,
            (clamp(base[0] + 8, 0, 255), clamp(base[1] + 8, 0, 255), clamp(base[2] + 8, 0, 255)),
            (clamp(base[0] - 8, 0, 255), clamp(base[1] - 8, 0, 255), clamp(base[2] - 8, 0, 255)),
            step=2
        )

# =====================================================
# ENEMY VEHICLES (road)
# =====================================================

class EnemyVehicle:
    def __init__(self, x):
        self.x = float(x)
        self.y = float(GROUND_Y - 34)
        self.speed = random.uniform(3.0, 6.0)
        self.style = VehicleStyle(random.randint(0, 2**31 - 1))
        self.hp = 60 if self.style.kind == "car" else 85 if self.style.kind == "van" else 120
        self.disabled = False
        self.explode_timer = 0
        self.remove_me = False
        self.shoot_cd = random.randint(30, 90)

    def rect(self):
        # Covers turret + body + wheels so player MG impacts register properly.
        top = int(self.y + 2)
        h = int(self.style.H + 14)
        return pygame.Rect(int(self.x), top, int(self.style.L), max(18, h))

    def update(self, scroll, bullets, particles, audio=None):
        # If disabled, burn out and then vanish
        if self.disabled:
            self.explode_timer -= 1
            if random.random() < 0.30:
                particles.append(Particle(self.x + random.randint(10, self.style.L - 10),
                                          self.y + 14,
                                          random.uniform(-0.3, 0.2),
                                          random.uniform(-0.8, -0.2),
                                          random.randint(20, 40),
                                          SMOKE,
                                          grow=True))
            if random.random() < 0.12:
                particles.append(Particle(self.x + self.style.L * 0.55,
                                          self.y + 18,
                                          random.uniform(-0.6, 0.6),
                                          random.uniform(-0.8, 0.2),
                                          random.randint(10, 18),
                                          random.choice([FIRE1, FIRE2]),
                                          grow=True))
            # drift off screen with the world
            self.x -= scroll
            if self.explode_timer <= 0 or self.x < -300:
                self.remove_me = True
            return

        # normal movement
        self.x -= (scroll + self.speed)

        # fire occasionally at the player
        self.shoot_cd -= 1
        if self.shoot_cd <= 0:
            mx = int(self.x + self.style.cab_x + self.style.cab_w + 2)
            my = int(self.y + 4)
            bullets.append(Bullet(mx, my, -6.5, 0.0, "enemy_vehicle", dmg=10))
            particles.append(Particle(mx, my, -0.4, -0.2, 10, MUZZLE, grow=False))
            if audio is not None:
                audio.play('road/enemy_mg', volume=0.7)
            self.shoot_cd = random.randint(55, 120)

    def damage(self, amt, particles, audio=None, debris=None):
        if self.disabled:
            return
        self.hp -= amt

        # impact sparks at hit
        for _ in range(3):
            particles.append(Particle(self.x + random.randint(8, self.style.L - 8),
                                      self.y + random.randint(10, 20),
                                      random.uniform(-1.2, 1.2),
                                      random.uniform(-1.0, 0.2),
                                      random.randint(10, 16),
                                      SPARK,
                                      grow=False))

        if self.hp <= 0:
            # BIG blow-up
            self.disabled = True
            if audio is not None:
                audio.play('road/explosion', volume=0.9)
            self.explode_timer = random.randint(90, 150)

            cx = self.x + self.style.L * 0.55
            cy = self.y + 18
            # Debris: blow into pieces
            if debris is not None:
                cols = [self.style.body, self.style.steel, self.style.rust]
                for _ in range(random.randint(10, 16)):
                    w = random.randint(3, 10)
                    h = random.randint(3, 9)
                    debris.append(DebrisPiece(cx + random.uniform(-10, 10),
                                              cy + random.uniform(-6, 6),
                                              random.uniform(-3.2, 3.2),
                                              random.uniform(-3.0, -0.6),
                                              w, h,
                                              random.choice(cols),
                                              life=random.randint(70, 120)))

            for _ in range(28):
                particles.append(Particle(cx, cy,
                                          random.uniform(-2.6, 2.6),
                                          random.uniform(-2.6, 1.4),
                                          random.randint(18, 34),
                                          random.choice([FIRE1, FIRE2, (220, 200, 140)]),
                                          grow=True))
            for _ in range(30):
                particles.append(Particle(cx, cy,
                                          random.uniform(-1.6, 1.6),
                                          random.uniform(-2.0, -0.2),
                                          random.randint(28, 55),
                                          SMOKE,
                                          grow=True))

    def draw(self, surf):
        tmp = PlayerVehicle()
        tmp.x = self.x
        tmp.y = self.y
        tmp._susp = 0.0
        tmp.style = self.style
        tmp.speed = 0.0
        tmp.draw(surf)
        if self.disabled:
            pygame.draw.rect(surf, (18, 18, 18), (int(self.x) + 6, int(self.y) + 18, max(10, self.style.L - 12), 2))


# =====================================================
# DUST
# =====================================================

# =====================================================
# ROAD DRAW
# =====================================================
def pick_biome(prev=None, rng=None):
    rng = rng or random
    choices = [BIOME_DESERT, BIOME_SCRUB, BIOME_SCRUB, BIOME_BADLANDS, BIOME_DESERT, BIOME_RUINS]
    b = rng.choice(choices)
    if prev and b == prev and rng.random() < 0.55:
        b = rng.choice(choices)
    return b

def jitter_color(rgb, rng, amount=18):
    """Small deterministic palette drift used for 'city color changes' per load."""
    return (
        clamp(rgb[0] + rng.randint(-amount, amount), 0, 255),
        clamp(rgb[1] + rng.randint(-amount, amount), 0, 255),
        clamp(rgb[2] + rng.randint(-amount, amount), 0, 255),
    )

def draw_sky(surf, city_pal, weather=None):
    # Base sky
    sky_top = city_pal.get("sky_top", SKY_TOP)
    sky_bot = city_pal.get("sky_bot", SKY_BOT)
    sun = city_pal.get("sun", SUN)
    haze = city_pal.get("haze", HAZE)

    # Weather mood shifts
    if weather is not None:
        if weather.kind in ("storm", "heavy_rain"):
            # darken + desaturate
            sky_top = (max(0, sky_top[0] - 18), max(0, sky_top[1] - 18), max(0, sky_top[2] - 18))
            sky_bot = (max(0, sky_bot[0] - 26), max(0, sky_bot[1] - 26), max(0, sky_bot[2] - 26))
            sun = (max(0, sun[0] - 40), max(0, sun[1] - 40), max(0, sun[2] - 40))
            haze = (max(0, haze[0] - 10), max(0, haze[1] - 10), max(0, haze[2] - 10))
        elif weather.kind in ("fog",):
            # lighten a little to simulate haze
            sky_top = (min(255, sky_top[0] + 10), min(255, sky_top[1] + 10), min(255, sky_top[2] + 10))
            sky_bot = (min(255, sky_bot[0] + 14), min(255, sky_bot[1] + 14), min(255, sky_bot[2] + 14))
        elif weather.kind in ("dust_storm",):
            # warm tint
            sky_top = (min(255, sky_top[0] + 16), min(255, sky_top[1] + 6), min(255, sky_top[2] + 0))
            sky_bot = (min(255, sky_bot[0] + 20), min(255, sky_bot[1] + 10), min(255, sky_bot[2] + 0))
            haze = (min(255, haze[0] + 16), min(255, haze[1] + 8), min(255, haze[2] + 2))

    draw_vertical_gradient(surf, sky_top, sky_bot)
    pygame.draw.circle(surf, sun, (BASE_W - 90, 64), 18)
    pygame.draw.rect(surf, haze, (0, GROUND_Y - 118, BASE_W, 34))

def draw_road(surf, scroll, biome, city_pal=None):
    city_pal = city_pal or {}
    road = city_pal.get("road", ROAD)
    road_dark = city_pal.get("road_dark", ROAD_DARK)
    road_edge = city_pal.get("road_edge", ROAD_EDGE)
    lane = city_pal.get("lane", LANE)

    pygame.draw.rect(surf, GROUND_TINT[biome], (0, GROUND_Y, BASE_W, BASE_H - GROUND_Y))
    pygame.draw.rect(surf, road, (0, ROAD_Y, BASE_W, ROAD_H))
    pygame.draw.rect(surf, road_dark, (0, ROAD_Y + 3, BASE_W, ROAD_H - 6))
    pygame.draw.rect(surf, road_edge, (0, ROAD_Y, BASE_W, 3))
    pygame.draw.rect(surf, road_edge, (0, ROAD_Y + ROAD_H - 3, BASE_W, 3))

    for x in range(-80, BASE_W + 80, 52):
        ox = int(x - (scroll * 4) % 52)
        pygame.draw.rect(surf, lane, (ox, ROAD_Y + 30, 22, 2))

    for x in range(-120, BASE_W + 120, 92):
        ox = int(x - (scroll * 2) % 92)
        pygame.draw.rect(surf, (20, 20, 22), (ox, ROAD_Y + 10, 32, 8))
        pygame.draw.rect(surf, (22, 22, 24), (ox + 40, ROAD_Y + 42, 24, 6))

    for x in range(-100, BASE_W + 100, 70):
        ox = int(x - (scroll * 3) % 70)
        pygame.draw.line(surf, (16, 16, 18), (ox, ROAD_Y + 16), (ox + 14, ROAD_Y + 22), 1)
        pygame.draw.line(surf, (16, 16, 18), (ox + 10, ROAD_Y + 46), (ox + 22, ROAD_Y + 50), 1)

def draw_hud(surf, font_small, vehicle, pitstop_fuel_total, mode, inv, equipped_weapon):
    outline_rect(surf, (6, 6, 360, 68), UI_BG, radius=2)

    gas_val = max(0, int(vehicle.gas))
    gas_pct = min(1.0, gas_val / 100.0) if gas_val <= 100 else 1.0
    gas_color = OK if gas_val > 35 else WARN if gas_val > 15 else BAD

    pygame.draw.rect(surf, (24, 24, 24), (14, 18, 120, 6))
    pygame.draw.rect(surf, gas_color, (14, 18, int(120 * gas_pct), 6))

    # Vehicle health bar
    hp_val = int(max(0, min(vehicle.max_health, vehicle.health)))
    hp_pct = hp_val / float(vehicle.max_health if vehicle.max_health else 100.0)
    hp_col = OK if hp_val > 60 else WARN if hp_val > 30 else BAD
    pygame.draw.rect(surf, (24, 24, 24), (14, 28, 120, 6))
    pygame.draw.rect(surf, hp_col, (14, 28, int(120 * hp_pct), 6))

    surf.blit(font_small.render("GAS", True, UI_FG), (140, 16))
    surf.blit(font_small.render(f"{gas_val}", True, UI_FG), (170, 16))
    arm_lvl = getattr(vehicle, "armor_level", 0)
    arm_red = int(100 * (vehicle.armor_reduction() if hasattr(vehicle, "armor_reduction") else 0.0))
    surf.blit(font_small.render(f"HP {int(vehicle.health)}  ARM {arm_lvl} (-{arm_red}%)", True, UI_FG), (140, 26))
    surf.blit(font_small.render(f"SPD {vehicle.speed:0.1f}", True, UI_FG), (14, 38))
    surf.blit(font_small.render("D throttle", True, (160, 160, 160)), (78, 38))
    surf.blit(font_small.render("LMB shoot", True, (160, 160, 160)), (160, 38))
    surf.blit(font_small.render(f"PITSTOP FUEL GAINED: {pitstop_fuel_total}", True, (160, 160, 160)), (14, 52))

    ammo = inv.count("ammo") if inv else 0
    meds = inv.count("medkit") if inv else 0
    grens = inv.count("grenade") if inv else 0
    dyn = inv.count("dynamite") if inv else 0
    weapon_name = equipped_weapon.replace("weapon_", "").upper() if equipped_weapon else "NONE"
    surf.blit(font_small.render(f"WPN {weapon_name} | AMMO {ammo} | MED {meds} | GRN {grens} | DYN {dyn}", True, (180, 180, 180)), (14, 58))

    if mode == MODE_PIT:
        surf.blit(font_small.render("IN PIT STOP", True, (190, 190, 190)), (280, 16))

# =====================================================
# PIT STOP SYSTEM
# =====================================================
CHUNK_W, CHUNK_H = 256, 256
PIT_DRAW_RADIUS = 2

# -----------------------------------------------------
# Pit Stop Variants (visual + structure flavor)
# - Same player + item generation across variants.
# - Variants affect only scenery palette + structure distribution.
# -----------------------------------------------------
PIT_VARIANTS = [
    "default",      # original
    "junkyard",
    "wasteland",
    "ghost_town",
    "desert",
    "toxic_dumps",
    "cemetery",
    "parking_lot",

    # New variants
    "military_outpost",
    "market_ruins",
    "industrial_plant",
    "swamp_marsh",
    "mountain_pass",
]


# Base palette uses your original values (DIRT_A/..., etc.)
PIT_VARIANT_PALETTES = {
    "default": {
        "dirt_a": DIRT_A, "dirt_b": DIRT_B,
        "crate": CRATE, "wall": WALL, "wreck": WRECK, "rock": ROCK,
        "building": (54, 54, 64), "window": (24, 24, 30), "roof": (70, 62, 54),
        "barrel": (64, 54, 48),
        "decor_a": (46, 42, 40), "decor_b": (26, 24, 22),
        "toxic_a": (70, 140, 92), "toxic_b": (40, 90, 60),
        "sand_a": (72, 62, 50), "sand_b": (62, 54, 44),
    },
    "junkyard": {
        "dirt_a": (46, 44, 44), "dirt_b": (40, 38, 38),
        "crate": (86, 66, 48), "wall": (66, 66, 74), "wreck": (42, 42, 46), "rock": (56, 52, 48),
        "building": (50, 50, 56), "window": (22, 22, 26), "roof": (78, 66, 56),
        "barrel": (62, 52, 48),
        "decor_a": (82, 64, 42), "decor_b": (24, 22, 20),
        "toxic_a": (70, 130, 92), "toxic_b": (40, 84, 60),
        "sand_a": (66, 58, 50), "sand_b": (58, 52, 44),
    },
    "wasteland": {
        "dirt_a": (48, 44, 40), "dirt_b": (40, 36, 34),
        "crate": (74, 60, 46), "wall": (60, 60, 68), "wreck": (44, 44, 48), "rock": (58, 54, 48),
        "building": (52, 52, 60), "window": (22, 22, 28), "roof": (66, 58, 54),
        "barrel": (58, 50, 46),
        "decor_a": (52, 48, 44), "decor_b": (24, 22, 20),
        "toxic_a": (70, 132, 94), "toxic_b": (40, 86, 62),
        "sand_a": (70, 60, 50), "sand_b": (60, 52, 44),
    },
    "ghost_town": {
        "dirt_a": (40, 40, 46), "dirt_b": (34, 34, 40),
        "crate": (70, 58, 44), "wall": (64, 64, 76), "wreck": (40, 40, 46), "rock": (56, 54, 54),
        "building": (48, 48, 62), "window": (18, 18, 26), "roof": (74, 68, 60),
        "barrel": (54, 48, 46),
        "decor_a": (60, 60, 72), "decor_b": (22, 22, 30),
        "toxic_a": (68, 128, 96), "toxic_b": (38, 82, 62),
        "sand_a": (66, 60, 54), "sand_b": (56, 52, 46),
    },
    "desert": {
        "dirt_a": (66, 58, 48), "dirt_b": (58, 52, 44),
        "crate": (82, 66, 48), "wall": (68, 64, 60), "wreck": (46, 44, 44), "rock": (70, 62, 52),
        "building": (60, 56, 54), "window": (24, 22, 20), "roof": (86, 76, 64),
        "barrel": (64, 56, 50),
        "decor_a": (76, 66, 54), "decor_b": (30, 26, 22),
        "toxic_a": (70, 130, 90), "toxic_b": (40, 84, 58),
        "sand_a": (84, 74, 62), "sand_b": (74, 66, 54),
    },
    "toxic_dumps": {
        "dirt_a": (38, 42, 38), "dirt_b": (32, 36, 32),
        "crate": (72, 60, 46), "wall": (58, 62, 58), "wreck": (42, 46, 42), "rock": (54, 58, 54),
        "building": (44, 52, 46), "window": (16, 22, 16), "roof": (64, 74, 66),
        "barrel": (60, 54, 48),
        "decor_a": (54, 70, 54), "decor_b": (20, 28, 20),
        "toxic_a": (86, 176, 102), "toxic_b": (44, 112, 68),
        "sand_a": (62, 58, 50), "sand_b": (54, 50, 44),
    },
    "cemetery": {
        "dirt_a": (34, 34, 38), "dirt_b": (28, 28, 32),
        "crate": (62, 54, 48), "wall": (70, 70, 78), "wreck": (44, 44, 50), "rock": (62, 62, 70),
        "building": (52, 52, 62), "window": (18, 18, 24), "roof": (64, 60, 58),
        "barrel": (54, 52, 56),
        "decor_a": (90, 90, 100), "decor_b": (46, 46, 52),
        "accent": (120, 20, 20),
    },
    "parking_lot": {
        "dirt_a": (26, 26, 30), "dirt_b": (20, 20, 24),
        "crate": (78, 62, 46), "wall": (66, 66, 72), "wreck": (50, 48, 52), "rock": (60, 54, 48),
        "building": (54, 54, 64), "window": (22, 22, 28), "roof": (72, 66, 60),
        "barrel": (64, 54, 48),
        "decor_a": (96, 88, 80), "decor_b": (36, 36, 40),
        "lane": (120, 112, 100),
    },
    "military_outpost": {
        "dirt_a": (28, 30, 34), "dirt_b": (22, 24, 28),
        "crate": (74, 62, 50), "wall": (86, 92, 104), "wreck": (46, 48, 54), "rock": (60, 62, 68),
        "building": (52, 56, 64), "window": (20, 22, 26), "roof": (88, 90, 92),
        "barrel": (62, 58, 54),
        "decor_a": (140, 128, 96), "decor_b": (34, 36, 40),
        "accent": (120, 150, 190),
    },
    "market_ruins": {
        "dirt_a": (52, 46, 44), "dirt_b": (44, 40, 38),
        "crate": (96, 74, 48), "wall": (70, 64, 58), "wreck": (44, 42, 44), "rock": (58, 54, 52),
        "building": (66, 58, 52), "window": (24, 22, 20), "roof": (98, 84, 62),
        "barrel": (62, 52, 46),
        "decor_a": (128, 92, 54), "decor_b": (32, 26, 22),
        "accent": (170, 120, 70),
    },
    "industrial_plant": {
        "dirt_a": (26, 28, 30), "dirt_b": (20, 22, 24),
        "crate": (70, 62, 54), "wall": (78, 80, 88), "wreck": (52, 54, 60), "rock": (60, 60, 66),
        "building": (46, 50, 54), "window": (18, 20, 22), "roof": (90, 92, 96),
        "barrel": (66, 60, 54),
        "decor_a": (112, 112, 120), "decor_b": (34, 34, 38),
        "accent": (210, 170, 70),
    },
    "swamp_marsh": {
        "dirt_a": (28, 34, 30), "dirt_b": (22, 28, 24),
        "crate": (74, 60, 46), "wall": (54, 64, 54), "wreck": (36, 44, 38), "rock": (48, 56, 48),
        "building": (44, 52, 44), "window": (16, 22, 18), "roof": (64, 74, 64),
        "barrel": (58, 54, 48),
        "decor_a": (70, 96, 70), "decor_b": (18, 28, 18),
        "toxic_a": (60, 140, 92), "toxic_b": (34, 92, 60),
    },
    "mountain_pass": {
        "dirt_a": (40, 40, 44), "dirt_b": (34, 34, 38),
        "crate": (78, 62, 46), "wall": (74, 74, 84), "wreck": (44, 44, 48), "rock": (86, 86, 92),
        "building": (52, 52, 60), "window": (18, 18, 22), "roof": (70, 70, 78),
        "barrel": (60, 54, 48),
        "decor_a": (120, 120, 132), "decor_b": (34, 34, 40),
        "accent": (160, 170, 180),
    },

}

WEAPON_DISPLAY = {
    "weapon_pistol": "PISTOL",
    "weapon_rifle": "RIFLE",
    "weapon_shotgun": "SHOTGUN",
    "weapon_smg": "SMG",
    "weapon_marksman": "MARKSMAN",
}

WEAPON_STATS = {
    "weapon_pistol": {"spd": 8.2, "cd": 10, "dmg": 22, "spread": 0.00, "pellets": 1, "ammo": 1},
    "weapon_rifle": {"spd": 9.6, "cd": 6, "dmg": 18, "spread": 0.00, "pellets": 1, "ammo": 1},
    "weapon_shotgun": {"spd": 8.6, "cd": 18, "dmg": 12, "spread": 0.25, "pellets": 6, "ammo": 1},
    "weapon_smg": {"spd": 9.0, "cd": 4, "dmg": 12, "spread": 0.08, "pellets": 1, "ammo": 1},
    "weapon_marksman": {"spd": 11.0, "cd": 14, "dmg": 44, "spread": 0.00, "pellets": 1, "ammo": 2},
}

EXPLOSIVE_STATS = {
    "grenade": {"radius": 42, "dmg": 75},
    "dynamite": {"radius": 58, "dmg": 110},
}

WEAPON_SPAWN_POOL = [
    ("weapon_pistol", 0.42),
    ("weapon_rifle", 0.28),
    ("weapon_shotgun", 0.18),
    ("weapon_smg", 0.10),
    ("weapon_marksman", 0.02),
]

def weighted_choice(rng, items):
    total = sum(w for _, w in items)
    r = rng.random() * total
    acc = 0.0
    for v, w in items:
        acc += w
        if r <= acc:
            return v
    return items[-1][0]


class PitZombie:
    def __init__(self, wx, wy, rng):
        self.wx = float(wx)
        self.wy = float(wy)
        self.hp = rng.randint(55, 95)
        self.speed = rng.uniform(0.55, 1.05)
        self.attack_cd = rng.randint(10, 40)
        self.anim = rng.randint(0, 59)

    def update(self, player_wx, player_wy, particles):
        dx = player_wx - self.wx
        dy = player_wy - self.wy
        dist = math.hypot(dx, dy)

        if dist < 260:
            nx, ny = v2_norm(dx, dy)
            self.wx += nx * self.speed
            self.wy += ny * self.speed

        self.anim = (self.anim + 1) % 60

        if self.attack_cd > 0:
            self.attack_cd -= 1

        hit = False
        if dist < 14 and self.attack_cd == 0:
            hit = True
            self.attack_cd = 30
            for _ in range(2):
                particles.append(Particle(self.wx, self.wy, random.uniform(-0.8, 0.8), random.uniform(-0.8, 0.4),
                                          random.randint(10, 16), SPARK, grow=False))
        return hit

    def draw(self, surf, cam_x, cam_y):
        sx = int(self.wx - cam_x)
        sy = int(self.wy - cam_y)

        frame = (self.anim // 15) & 1
        body = ZOMBIE_COL_A if frame == 0 else ZOMBIE_COL_B
        leg = 1 if (self.anim // 8) & 1 else 0

        outline_rect(surf, (sx - 4, sy - 6, 8, 12), body, radius=1)
        pygame.draw.rect(surf, ZOMBIE_FACE, (sx - 2, sy - 2, 4, 2))
        pygame.draw.rect(surf, ZOMBIE_FACE, (sx - 3, sy + 2, 2, 2 + leg))
        pygame.draw.rect(surf, ZOMBIE_FACE, (sx + 1, sy + 2, 2, 2 + (1 - leg)))


class PitRaider:
    """Human raider with a gun (ranged)."""
    def __init__(self, wx, wy, rng, weapon_key="rifle"):
        self.wx = float(wx)
        self.wy = float(wy)
        self.hp = rng.randint(60, 95)
        self.speed = rng.uniform(0.65, 1.05)
        self.weapon_key = weapon_key  # 'pistol'|'rifle'|'smg'|'marksman'
        self.shoot_cd = rng.randint(20, 80)
        self.anim = rng.randint(0, 59)

    def update(self, player_wx, player_wy, bullets, particles, audio=None):
        dx = player_wx - self.wx
        dy = player_wy - self.wy
        dist = math.hypot(dx, dy)

        # keep some spacing: drift a bit, not pure rush
        if dist < 220:
            nx, ny = v2_norm(dx, dy)
            # strafe-ish wobble
            wob = math.sin((self.anim / 60.0) * math.tau) * 0.35
            sx, sy = -ny * wob, nx * wob
            self.wx += (nx * self.speed * 0.35) + sx
            self.wy += (ny * self.speed * 0.35) + sy
        elif dist < 360:
            nx, ny = v2_norm(dx, dy)
            self.wx += nx * self.speed * 0.55
            self.wy += ny * self.speed * 0.55

        self.anim = (self.anim + 1) % 60

        if self.shoot_cd > 0:
            self.shoot_cd -= 1

        if dist < 320 and self.shoot_cd == 0:
            nx, ny = v2_norm(dx, dy)
            if nx == 0.0 and ny == 0.0:
                return False
            spd = 6.8
            dmg = 10
            spread = 0.06
            if self.weapon_key == "pistol":
                spd, dmg, spread = 6.2, 8, 0.09
            elif self.weapon_key == "smg":
                spd, dmg, spread = 6.6, 8, 0.12
            elif self.weapon_key == "marksman":
                spd, dmg, spread = 8.0, 14, 0.03

            ang = random.uniform(-spread, spread)
            cx = nx * math.cos(ang) - ny * math.sin(ang)
            cy = nx * math.sin(ang) + ny * math.cos(ang)

            bullets.append(Bullet(self.wx + cx * 6, self.wy + cy * 6, cx * spd, cy * spd, "pit_raider", dmg=dmg))
            particles.append(Particle(self.wx + cx * 6, self.wy + cy * 6, cx * 0.6, cy * 0.6, 10, MUZZLE, grow=False))
            for _ in range(2):
                particles.append(Particle(self.wx + cx * 6, self.wy + cy * 6, random.uniform(-0.6, 0.6), random.uniform(-0.6, 0.6),
                                          random.randint(8, 14), SPARK, grow=False))

            if audio is not None:
                audio.play(f"pit/{self.weapon_key}", volume=0.75)

            # cooldown varies
            self.shoot_cd = 22 if self.weapon_key == "pistol" else 10 if self.weapon_key == "rifle" else 6 if self.weapon_key == "smg" else 16
            return True
        return False

    def draw(self, surf, cam_x, cam_y):
        sx = int(self.wx - cam_x)
        sy = int(self.wy - cam_y)
        bob = -1 if (self.anim // 12) & 1 else 0
        outline_rect(surf, (sx - 4, sy - 6 + bob, 8, 12), (128, 120, 110), radius=1)
        pygame.draw.rect(surf, (30, 30, 30), (sx - 2, sy - 2 + bob, 4, 2))
        # gun
        pygame.draw.line(surf, STEEL, (sx, sy - 1 + bob), (sx + 8, sy - 1 + bob), 2)
        pygame.draw.circle(surf, STEEL_DARK, (sx + 8, sy - 1 + bob), 2)


class PitVehicle:
    """Drivable pit-stop vehicle for parking_lot variant."""
    def __init__(self, wx, wy, rng):
        self.wx = float(wx)
        self.wy = float(wy)
        self.vx = 0.0
        self.vy = 0.0
        self.speed = rng.uniform(2.6, 3.4)
        self.shoot_cd = rng.randint(0, 10)

    def update(self, keys):
        dx = dy = 0.0
        if keys[pygame.K_w]: dy -= 1.0
        if keys[pygame.K_s]: dy += 1.0
        if keys[pygame.K_a]: dx -= 1.0
        if keys[pygame.K_d]: dx += 1.0
        if dx != 0.0 or dy != 0.0:
            nx, ny = v2_norm(dx, dy)
            self.vx = nx * self.speed
            self.vy = ny * self.speed
        else:
            self.vx *= 0.80
            self.vy *= 0.80
        self.wx += self.vx
        self.wy += self.vy
        if self.shoot_cd > 0:
            self.shoot_cd -= 1

    def try_shoot(self, bullets, particles, cam_x, cam_y, mouse_pos, inv, audio=None):
        if self.shoot_cd > 0:
            return False
        mx, my = mouse_pos
        aim_x = cam_x + mx
        aim_y = cam_y + my
        dx = aim_x - self.wx
        dy = aim_y - self.wy
        nx, ny = v2_norm(dx, dy)
        use_ammo = inv is not None and inv.count("ammo") > 0
        if use_ammo:
            inv.consume("ammo", 1)
        spd = 9.4
        dmg = 14 if use_ammo else 6
        bullets.append(Bullet(self.wx + nx * 10, self.wy + ny * 10, nx * spd, ny * spd, "pit_vehicle", dmg=dmg))
        particles.append(Particle(self.wx + nx * 10, self.wy + ny * 10, nx * 0.6, ny * 0.6, 10, MUZZLE, grow=False))
        if audio is not None:
            audio.play("road/mg", volume=0.75)
        self.shoot_cd = 3
        return True

    def draw(self, surf, cam_x, cam_y):
        sx = int(self.wx - cam_x)
        sy = int(self.wy - cam_y)
        outline_rect(surf, (sx - 10, sy - 6, 20, 12), (50, 48, 52), radius=2)
        pygame.draw.rect(surf, (20, 20, 24), (sx - 6, sy - 3, 12, 6), border_radius=1)
        pygame.draw.rect(surf, (12, 12, 14), (sx - 12, sy - 6, 3, 4))
        pygame.draw.rect(surf, (12, 12, 14), (sx + 9, sy - 6, 3, 4))
        pygame.draw.rect(surf, (12, 12, 14), (sx - 12, sy + 2, 3, 4))
        pygame.draw.rect(surf, (12, 12, 14), (sx + 9, sy + 2, 3, 4))

class PitMutant:
    """Chunky melee monstrosity (toxic/wasteland flavor)."""
    def __init__(self, wx, wy, rng):
        self.wx = float(wx)
        self.wy = float(wy)
        self.hp = rng.randint(85, 140)
        self.speed = rng.uniform(0.45, 0.85)
        self.attack_cd = rng.randint(10, 50)
        self.anim = rng.randint(0, 59)

    def update(self, player_wx, player_wy, particles):
        dx = player_wx - self.wx
        dy = player_wy - self.wy
        dist = math.hypot(dx, dy)

        if dist < 320:
            nx, ny = v2_norm(dx, dy)
            self.wx += nx * self.speed
            self.wy += ny * self.speed

        self.anim = (self.anim + 1) % 60
        if self.attack_cd > 0:
            self.attack_cd -= 1

        hit = False
        if dist < 16 and self.attack_cd == 0:
            hit = True
            self.attack_cd = 34
            for _ in range(3):
                particles.append(Particle(self.wx, self.wy, random.uniform(-1.0, 1.0), random.uniform(-1.0, 0.6),
                                          random.randint(10, 16), SPARK, grow=False))
        return hit

    def draw(self, surf, cam_x, cam_y):
        sx = int(self.wx - cam_x)
        sy = int(self.wy - cam_y)
        frame = (self.anim // 12) & 1
        col = (96, 120, 80) if frame == 0 else (78, 100, 64)
        outline_rect(surf, (sx - 6, sy - 8, 12, 16), col, radius=2)
        pygame.draw.rect(surf, (24, 24, 24), (sx - 3, sy - 2, 6, 3))

class PitWraith:
    """Ghost-town wraith: fragile, fast bursts, fades when close."""
    def __init__(self, wx, wy, rng):
        self.wx = float(wx)
        self.wy = float(wy)
        self.hp = rng.randint(40, 70)
        self.speed = rng.uniform(0.85, 1.35)
        self.attack_cd = rng.randint(10, 40)
        self.fade = 0  # 0..60

    def update(self, player_wx, player_wy, particles):
        dx = player_wx - self.wx
        dy = player_wy - self.wy
        dist = math.hypot(dx, dy)

        # fade out when too close, reappear a little farther
        if dist < 18:
            self.fade = min(60, self.fade + 6)
        else:
            self.fade = max(0, self.fade - 2)

        if dist < 260 and self.fade < 54:
            nx, ny = v2_norm(dx, dy)
            self.wx += nx * self.speed
            self.wy += ny * self.speed

        if self.attack_cd > 0:
            self.attack_cd -= 1

        hit = False
        if dist < 14 and self.attack_cd == 0 and self.fade < 54:
            hit = True
            self.attack_cd = 28
            for _ in range(2):
                particles.append(Particle(self.wx, self.wy, random.uniform(-0.8, 0.8), random.uniform(-0.8, 0.4),
                                          random.randint(10, 16), (180, 180, 200), grow=False))
        return hit

    def draw(self, surf, cam_x, cam_y):
        # simple alpha-less "fade" by darkening / shrinking
        sx = int(self.wx - cam_x)
        sy = int(self.wy - cam_y)
        s = 8 if self.fade < 30 else 6 if self.fade < 48 else 4
        col = (120, 120, 140) if self.fade < 30 else (90, 90, 110)
        outline_rect(surf, (sx - s//2, sy - s//2, s, s), col, radius=1)


class PitHound:
    """Fast melee predator. Very aggressive, low-ish HP."""
    def __init__(self, wx, wy, rng):
        self.wx = float(wx)
        self.wy = float(wy)
        self.hp = rng.randint(40, 70)
        self.speed = rng.uniform(1.35, 1.95)
        self.attack_cd = rng.randint(8, 24)
        self.anim = rng.randint(0, 59)

    def update(self, player_wx, player_wy, particles):
        dx = player_wx - self.wx
        dy = player_wy - self.wy
        dist = math.hypot(dx, dy)

        # sprint in, then circle a bit when very close
        if dist < 360:
            nx, ny = v2_norm(dx, dy)
            close = 1.0 if dist < 80 else 0.55 if dist < 180 else 0.35
            wob = math.sin((self.anim / 60.0) * math.tau) * (0.55 if dist < 140 else 0.25)
            sx, sy = -ny * wob, nx * wob
            self.wx += (nx * self.speed * close) + sx
            self.wy += (ny * self.speed * close) + sy

        self.anim = (self.anim + 1) % 60
        if self.attack_cd > 0:
            self.attack_cd -= 1

        hit = False
        if dist < 12 and self.attack_cd == 0:
            hit = True
            self.attack_cd = 22
            for _ in range(3):
                particles.append(Particle(self.wx, self.wy,
                                          random.uniform(-1.2, 1.2),
                                          random.uniform(-1.0, 0.6),
                                          random.randint(10, 16),
                                          SPARK, grow=False))
        return hit

    def draw(self, surf, cam_x, cam_y):
        sx = int(self.wx - cam_x)
        sy = int(self.wy - cam_y)
        frame = (self.anim // 10) & 1
        body = (120, 92, 66) if frame == 0 else (98, 78, 58)
        outline_rect(surf, (sx - 5, sy - 3, 10, 6), body, radius=2)
        pygame.draw.circle(surf, (34, 30, 26), (sx + (2 if frame == 0 else 1), sy - 1), 1)
        pygame.draw.line(surf, (34, 30, 26), (sx - 2, sy + 2), (sx - 6, sy + 4), 1)


class PitSentry:
    """Stationary gun turret / sentry. Ranged threat."""
    def __init__(self, wx, wy, rng):
        self.wx = float(wx)
        self.wy = float(wy)
        self.hp = rng.randint(70, 120)
        self.shoot_cd = rng.randint(25, 90)
        self.anim = rng.randint(0, 59)

    def update(self, player_wx, player_wy, bullets, particles, audio=None):
        self.anim = (self.anim + 1) % 60
        dx = player_wx - self.wx
        dy = player_wy - self.wy
        dist = math.hypot(dx, dy)

        if self.shoot_cd > 0:
            self.shoot_cd -= 1

        if dist < 360 and self.shoot_cd == 0:
            nx, ny = v2_norm(dx, dy)
            if nx == 0.0 and ny == 0.0:
                return
            spd = 7.2
            dmg = 12
            bullets.append(Bullet(self.wx + nx * 8, self.wy + ny * 8, nx * spd, ny * spd, "pit_sentry", dmg=dmg))
            particles.append(Particle(self.wx + nx * 8, self.wy + ny * 8, nx * 0.8, ny * 0.8, 10, MUZZLE, grow=False))
            for _ in range(2):
                particles.append(Particle(self.wx + nx * 8, self.wy + ny * 8,
                                          random.uniform(-0.6, 0.6), random.uniform(-0.6, 0.6),
                                          random.randint(8, 14), SPARK, grow=False))
            if audio is not None and random.random() < 0.35:
                audio.play("pit/rifle", volume=0.65)
            self.shoot_cd = random.randint(18, 46)

    def draw(self, surf, cam_x, cam_y):
        sx = int(self.wx - cam_x)
        sy = int(self.wy - cam_y)
        outline_rect(surf, (sx - 6, sy - 6, 12, 12), (70, 76, 86), radius=2)
        pygame.draw.rect(surf, (34, 36, 42), (sx - 3, sy - 3, 6, 6))
        pygame.draw.rect(surf, (150, 160, 170), (sx - 1, sy - 9, 2, 6))

class PitPlayer:
    def __init__(self, inventory):
        self.wx = 0.0
        self.wy = 0.0
        self.speed = 1.9
        self.anim = 0

        self.hp = 100
        self.hp_max = 100

        self.aim_dx = 1.0
        self.aim_dy = 0.0

        self.shoot_cd = 0
        self.melee_cd = 0
        self.inv = inventory

        self.equipped = None
        owned = self.inv.owned_weapons()
        self.equipped = owned[0] if owned else None

    def cycle_weapon(self):
        owned = self.inv.owned_weapons()
        if not owned:
            self.equipped = None
            return
        if self.equipped not in owned:
            self.equipped = owned[0]
            return
        idx = owned.index(self.equipped)
        self.equipped = owned[(idx + 1) % len(owned)]

    def update(self, keys):
        dx = dy = 0.0
        if keys[pygame.K_w]: dy -= 1.0
        if keys[pygame.K_s]: dy += 1.0
        if keys[pygame.K_a]: dx -= 1.0
        if keys[pygame.K_d]: dx += 1.0

        if dx != 0.0 or dy != 0.0:
            nx, ny = v2_norm(dx, dy)
            self.wx += nx * self.speed
            self.wy += ny * self.speed
            self.aim_dx, self.aim_dy = nx, ny
            self.anim = (self.anim + 1) % 60
        else:
            self.anim = (self.anim + 1) % 90

        if self.shoot_cd > 0:
            self.shoot_cd -= 1
        if self.melee_cd > 0:
            self.melee_cd -= 1

    def try_use_medkit(self, particles):
        if self.inv.consume("medkit", 1):
            old = self.hp
            self.hp = min(self.hp_max, self.hp + 45)
            for _ in range(8):
                particles.append(Particle(self.wx, self.wy, random.uniform(-1.0, 1.0), random.uniform(-1.4, 0.6),
                                          random.randint(10, 16), (120, 200, 140), grow=False))
            return self.hp > old
        return False

    
    def _shoot_dir_from_mouse(self, mouse_pos, cam_x, cam_y):
        mx, my = mouse_pos
        aim_x = cam_x + mx
        aim_y = cam_y + my
        dx = aim_x - self.wx
        dy = aim_y - self.wy
        nx, ny = v2_norm(dx, dy)
        if nx == 0.0 and ny == 0.0:
            nx, ny = self.aim_dx, self.aim_dy
        self.aim_dx, self.aim_dy = nx, ny
        return nx, ny
    
    def try_attack(self, bullets, particles, mouse_pos, cam_x, cam_y, zombies, audio=None):
        # Armed shooting or melee punch
        if self.equipped is not None:
            if self.shoot_cd > 0:
                return
    
            stats = WEAPON_STATS[self.equipped]
            if self.inv.count("ammo") < stats["ammo"]:
                particles.append(Particle(self.wx, self.wy, random.uniform(-0.4, 0.4), random.uniform(-0.6, 0.2),
                                          10, (120, 120, 120), grow=False))
                if audio is not None:
                    audio.play("pit/runout_ammo", volume=0.9)
                self.shoot_cd = 8
                return
    
            nx, ny = self._shoot_dir_from_mouse(mouse_pos, cam_x, cam_y)
            spd = stats["spd"]
            dmg = stats["dmg"]
    
            for _ in range(stats["pellets"]):
                ang = random.uniform(-stats["spread"], stats["spread"])
                cx = nx * math.cos(ang) - ny * math.sin(ang)
                cy = nx * math.sin(ang) + ny * math.cos(ang)
                bullets.append(Bullet(self.wx + cx * 6, self.wy + cy * 6, cx * spd, cy * spd, "pit_player", dmg=dmg))
    
            particles.append(Particle(self.wx + nx * 6, self.wy + ny * 6, nx * 0.6, ny * 0.6, 10, MUZZLE, grow=False))
            for _ in range(2):
                particles.append(Particle(self.wx + nx * 6, self.wy + ny * 6, random.uniform(-0.6, 0.6), random.uniform(-0.6, 0.6),
                                          random.randint(8, 14), SPARK, grow=False))
    
            self.inv.consume("ammo", stats["ammo"])
            self.shoot_cd = stats["cd"]
    
            if audio is not None:
                w = self.equipped.replace("weapon_", "")
                audio.play(f"pit/{w}", volume=0.85)
            return
    
        if self.melee_cd > 0:
            return
    
        ax, ay = self.aim_dx, self.aim_dy
        hit_any = False
        for z in zombies:
            dx = z.wx - self.wx
            dy = z.wy - self.wy
            dist = math.hypot(dx, dy)
            if dist < 18:
                nx, ny = v2_norm(dx, dy)
                dot = nx * ax + ny * ay
                if dot > 0.15:
                    z.hp -= 18
                    hit_any = True
    
        for _ in range(3 if hit_any else 1):
            particles.append(Particle(self.wx + ax * 6, self.wy + ay * 6,
                                      random.uniform(-0.6, 0.6), random.uniform(-0.8, 0.2),
                                      random.randint(10, 14),
                                      SPARK if hit_any else (120, 120, 120),
                                      grow=False))
        self.melee_cd = 10
    
    def try_throw_explosive(self, explosions, particles, mouse_pos, cam_x, cam_y, audio=None):
        if self.inv.count("grenade") <= 0 and self.inv.count("dynamite") <= 0:
            return False
    
        kind = "grenade" if self.inv.count("grenade") > 0 else "dynamite"
        if not self.inv.consume(kind, 1):
            return False
    
        mx, my = mouse_pos
        tx = cam_x + mx
        ty = cam_y + my
    
        st = EXPLOSIVE_STATS[kind]
        explosions.append(Explosion(tx, ty, st["radius"], st["dmg"]))
    
        if audio is not None:
            audio.play(f"pit/{kind}", volume=0.85)
            audio.play("pit/explosion", volume=0.95)
    
        for _ in range(22 if kind == "grenade" else 34):
            particles.append(Particle(tx, ty,
                                      random.uniform(-2.4, 2.4),
                                      random.uniform(-2.4, 1.8),
                                      random.randint(14, 24),
                                      random.choice([FIRE1, FIRE2, SPARK]),
                                      grow=True))
        for _ in range(20 if kind == "grenade" else 28):
            particles.append(Particle(tx, ty,
                                      random.uniform(-1.4, 1.4),
                                      random.uniform(-1.8, -0.2),
                                      random.randint(18, 44),
                                      SMOKE,
                                      grow=True))
        return True

    def draw(self, surf, cam_x, cam_y):
        sx = int(self.wx - cam_x)
        sy = int(self.wy - cam_y)

        leg = 1 if (self.anim // 8) % 2 == 0 else 0
        bob = -1 if (self.anim // 12) % 2 == 0 else 0

        outline_rect(surf, (sx - 4, sy - 6 + bob, 8, 12), (178, 162, 90), radius=1)
        pygame.draw.rect(surf, (40, 40, 40), (sx - 2, sy - 2 + bob, 4, 2))

        pygame.draw.rect(surf, (48, 40, 34), (sx - 4, sy + 1 + bob, 8, 2))

        pygame.draw.rect(surf, (28, 28, 30), (sx - 3, sy + 5 + bob, 2, 2 + leg))
        pygame.draw.rect(surf, (28, 28, 30), (sx + 1, sy + 5 + bob, 2, 2 + (1 - leg)))

        ax, ay = self.aim_dx, self.aim_dy
        if self.equipped is not None:
            gun_len = 10 if self.equipped in ("weapon_rifle", "weapon_marksman") else 8
            ex = sx + int(ax * gun_len)
            ey = sy + int(ay * gun_len)
            pygame.draw.line(surf, STEEL, (sx, sy - 1 + bob), (ex, ey - 1 + bob), 2)
            pygame.draw.circle(surf, STEEL_DARK, (ex, ey - 1 + bob), 2)
        else:
            pygame.draw.rect(surf, (60, 50, 42), (sx + int(ax * 3), sy + int(ay * 3), 2, 2))

# -----------------------------------------------------
# Pit Chunk
# -----------------------------------------------------
class PitChunk:
    def __init__(self, cx, cy, seed, breakdown=False, audio=None, variant='default', pal=None):
        self.cx = cx
        self.cy = cy
        self.seed = seed
        self.breakdown = bool(breakdown)
        self.audio = audio
        self.variant = variant or 'default'
        self.pal = pal if isinstance(pal, dict) else PIT_VARIANT_PALETTES.get(self.variant, PIT_VARIANT_PALETTES['default'])
        self.structs = []     # (kind, Rect)
        self.resources = []   # [gx, gy, kind, value]
        self.zombies = []     # list[PitZombie]
        self.raiders = []     # list[PitRaider]
        self.mutants = []     # list[PitMutant]
        self.wraiths = []     # list[PitWraith]
        self.hounds = []      # list[PitHound]
        self.sentries = []    # list[PitSentry]
        self.vehicles = []    # list[PitVehicle] (parking_lot only)

        self._gen()

    def _gen(self):
        rng = random.Random(self.seed)
        building_rects = []  # local rects (chunk space) for loot stuffing
        # --- Base scatter: variant-flavored debris (visual only; gameplay unchanged) ---
        base_n = rng.randint(26, 46)
        # weights: rock, crate, wreck, barrel, decor (extra props)
        wmap = {
            "default":      [5, 3, 2, 2, 0],
            "junkyard":     [2, 3, 6, 4, 1],
            "wasteland":    [6, 2, 2, 2, 0],
            "ghost_town":   [2, 2, 1, 1, 5],
            "desert":       [9, 1, 1, 1, 0],
            "toxic_dumps":  [3, 2, 3, 6, 2],
            "cemetery":     [4, 2, 2, 1, 5],
            "parking_lot":  [1, 2, 7, 2, 1],
            "military_outpost": [1, 2, 4, 1, 2],
            "market_ruins":     [2, 3, 2, 2, 3],
            "industrial_plant": [1, 2, 5, 2, 2],
            "swamp_marsh":      [4, 2, 2, 2, 2],
            "mountain_pass":    [7, 1, 2, 1, 1],
        }
        ww = wmap.get(self.variant, wmap["default"])
        kinds = ["rock", "crate", "wreck", "barrel", "decor"]
        for _ in range(base_n):
            x = rng.randint(0, CHUNK_W - 8)
            y = rng.randint(0, CHUNK_H - 8)
            kind = rng.choices(kinds, weights=ww, k=1)[0]

            w = 8
            h = 8

            if kind == "wreck" and rng.random() < 0.45:
                w = 10
                h = 6

            if kind == "decor":
                # lightweight props that read differently per variant
                # (no collisions beyond the rect itself, like the other structs)
                if self.variant == "ghost_town":
                    kind = rng.choice(["sign", "porch", "fence"])
                    w = rng.randint(8, 14)
                    h = rng.randint(4, 10)
                elif self.variant == "toxic_dumps":
                    kind = rng.choice(["toxic_pool", "pipe"])
                    w = rng.randint(10, 18) if kind == "toxic_pool" else rng.randint(6, 12)
                    h = rng.randint(8, 14) if kind == "toxic_pool" else rng.randint(4, 8)
                elif self.variant == "junkyard":
                    kind = rng.choice(["stack", "tire"])
                    w = rng.randint(8, 14)
                    h = rng.randint(6, 12)
                elif self.variant == "desert":
                    kind = rng.choice(["dune", "bones"])
                    w = rng.randint(10, 18)
                    h = rng.randint(4, 8)
                else:
                    kind = rng.choice(["scrap", "stump"])
                    w = rng.randint(6, 12)
                    h = rng.randint(6, 12)

            self.structs.append((kind, pygame.Rect(x, y, w, h)))


        # Larger structure clusters help pit stops read like "places" (and concentrate loot).
        compound_chance = 0.84
        if self.variant == 'ghost_town':
            compound_chance = 0.94
        elif self.variant == 'cemetery':
            compound_chance = 0.90
        elif self.variant == 'desert':
            compound_chance = 0.72
        elif self.variant == 'junkyard':
            compound_chance = 0.80
        elif self.variant == 'wasteland':
            compound_chance = 0.78
        elif self.variant == 'toxic_dumps':
            compound_chance = 0.82
        elif self.variant == 'parking_lot':
            compound_chance = 0.80
        elif self.variant == 'military_outpost':
            compound_chance = 0.92
        elif self.variant == 'market_ruins':
            compound_chance = 0.90
        elif self.variant == 'industrial_plant':
            compound_chance = 0.92
        elif self.variant == 'swamp_marsh':
            compound_chance = 0.80
        elif self.variant == 'mountain_pass':
            compound_chance = 0.74

        if rng.random() < compound_chance:
            bx = rng.randint(18, CHUNK_W - 120)
            by = rng.randint(18, CHUNK_H - 120)
            bw = rng.randint(70, 130)
            bh = rng.randint(60, 120)

            for x in range(bx, bx + bw, 10):
                self.structs.append(("wall", pygame.Rect(x, by, 10, 6)))
                self.structs.append(("wall", pygame.Rect(x, by + bh, 10, 6)))
            for y in range(by, by + bh, 10):
                self.structs.append(("wall", pygame.Rect(bx, y, 6, 10)))
                self.structs.append(("wall", pygame.Rect(bx + bw, y, 6, 10)))

            if rng.random() < 0.65:
                bx2 = bx + rng.randint(10, 24)
                by2 = by + rng.randint(10, 24)
                bw2 = rng.randint(28, 56)
                bh2 = rng.randint(22, 46)
                brect = pygame.Rect(bx2, by2, bw2, bh2)
                self.structs.append(("building", brect))
                building_rects.append(brect)
            # Variant: ghost town gets extra scattered shacks (purely visual structures)
            if self.variant == "ghost_town" and rng.random() < 0.85:
                for _ in range(rng.randint(1, 3)):
                    gx = bx + rng.randint(4, max(5, bw - 40))
                    gy = by + rng.randint(4, max(5, bh - 30))
                    gw = rng.randint(24, 48)
                    gh = rng.randint(20, 40)
                    brect = pygame.Rect(gx, gy, gw, gh)
                self.structs.append(("building", brect))
                building_rects.append(brect)


            for _ in range(rng.randint(6, 16)):
                rx = rng.randint(bx + 6, bx + bw - 14)
                ry = rng.randint(by + 6, by + bh - 14)
                self.structs.append(("wreck", pygame.Rect(rx, ry, 10, 6)))

        
        # --- Variant POIs: larger structures that feel like "zones" ---
        # These add scenery + extra loot placements (same item TYPES as normal generation).
        # Kept conservative so performance stays stable.
        def _add_poi(kind, r):
            self.structs.append((kind, r))
            building_rects.append(r)

        if self.variant == "ghost_town":
            for _ in range(rng.randint(1, 3)):
                rx = rng.randint(18, CHUNK_W - 88)
                ry = rng.randint(18, CHUNK_H - 68)
                rw = rng.randint(54, 84)
                rh = rng.randint(40, 64)
                _add_poi("house", pygame.Rect(rx, ry, rw, rh))
        elif self.variant == "junkyard":
            for _ in range(rng.randint(1, 2)):
                rx = rng.randint(18, CHUNK_W - 110)
                ry = rng.randint(18, CHUNK_H - 72)
                rw = rng.randint(74, 110)
                rh = rng.randint(44, 72)
                _add_poi("garage", pygame.Rect(rx, ry, rw, rh))
        elif self.variant == "toxic_dumps":
            for _ in range(rng.randint(1, 2)):
                rx = rng.randint(18, CHUNK_W - 120)
                ry = rng.randint(18, CHUNK_H - 86)
                rw = rng.randint(84, 120)
                rh = rng.randint(52, 86)
                _add_poi("facility", pygame.Rect(rx, ry, rw, rh))
        elif self.variant in ("wasteland", "desert"):
            if rng.random() < 0.70:
                rx = rng.randint(18, CHUNK_W - 102)
                ry = rng.randint(18, CHUNK_H - 70)
                rw = rng.randint(66, 102)
                rh = rng.randint(42, 70)
                _add_poi("bunker", pygame.Rect(rx, ry, rw, rh))

        elif self.variant == "cemetery":
            if rng.random() < 0.85:
                rx = rng.randint(18, CHUNK_W - 108)
                ry = rng.randint(18, CHUNK_H - 86)
                rw = rng.randint(84, 108)
                rh = rng.randint(56, 86)
                _add_poi("graveyard", pygame.Rect(rx, ry, rw, rh))
            if rng.random() < 0.45:
                rx = rng.randint(18, CHUNK_W - 82)
                ry = rng.randint(18, CHUNK_H - 62)
                rw = rng.randint(56, 82)
                rh = rng.randint(38, 62)
                _add_poi("mausoleum", pygame.Rect(rx, ry, rw, rh))
        elif self.variant == "parking_lot":
            if rng.random() < 0.75:
                rx = rng.randint(12, CHUNK_W - 132)
                ry = rng.randint(12, CHUNK_H - 102)
                rw = rng.randint(108, 132)
                rh = rng.randint(78, 102)
                _add_poi("lot", pygame.Rect(rx, ry, rw, rh))
            if rng.random() < 0.35:
                rx = rng.randint(18, CHUNK_W - 94)
                ry = rng.randint(18, CHUNK_H - 74)
                rw = rng.randint(64, 94)
                rh = rng.randint(44, 74)
                _add_poi("store", pygame.Rect(rx, ry, rw, rh))

        elif self.variant == "military_outpost":
            for _ in range(rng.randint(1, 2)):
                rx = rng.randint(18, CHUNK_W - 114)
                ry = rng.randint(18, CHUNK_H - 88)
                rw = rng.randint(84, 114)
                rh = rng.randint(54, 88)
                _add_poi("outpost", pygame.Rect(rx, ry, rw, rh))
            if rng.random() < 0.55:
                rx = rng.randint(18, CHUNK_W - 92)
                ry = rng.randint(18, CHUNK_H - 66)
                rw = rng.randint(60, 92)
                rh = rng.randint(40, 66)
                _add_poi("barracks", pygame.Rect(rx, ry, rw, rh))

        elif self.variant == "market_ruins":
            for _ in range(rng.randint(1, 2)):
                rx = rng.randint(18, CHUNK_W - 118)
                ry = rng.randint(18, CHUNK_H - 80)
                rw = rng.randint(86, 118)
                rh = rng.randint(46, 80)
                _add_poi("market", pygame.Rect(rx, ry, rw, rh))
            if rng.random() < 0.40:
                rx = rng.randint(18, CHUNK_W - 84)
                ry = rng.randint(18, CHUNK_H - 62)
                rw = rng.randint(54, 84)
                rh = rng.randint(38, 62)
                _add_poi("shop", pygame.Rect(rx, ry, rw, rh))

        elif self.variant == "industrial_plant":
            for _ in range(rng.randint(1, 2)):
                rx = rng.randint(18, CHUNK_W - 126)
                ry = rng.randint(18, CHUNK_H - 92)
                rw = rng.randint(92, 126)
                rh = rng.randint(56, 92)
                _add_poi("plant", pygame.Rect(rx, ry, rw, rh))
            if rng.random() < 0.50:
                rx = rng.randint(18, CHUNK_W - 92)
                ry = rng.randint(18, CHUNK_H - 66)
                rw = rng.randint(60, 92)
                rh = rng.randint(40, 66)
                _add_poi("warehouse", pygame.Rect(rx, ry, rw, rh))

        elif self.variant == "swamp_marsh":
            for _ in range(rng.randint(1, 3)):
                rx = rng.randint(18, CHUNK_W - 90)
                ry = rng.randint(18, CHUNK_H - 70)
                rw = rng.randint(54, 90)
                rh = rng.randint(38, 70)
                _add_poi("shack", pygame.Rect(rx, ry, rw, rh))

        elif self.variant == "mountain_pass":
            if rng.random() < 0.85:
                rx = rng.randint(18, CHUNK_W - 118)
                ry = rng.randint(18, CHUNK_H - 86)
                rw = rng.randint(84, 118)
                rh = rng.randint(50, 86)
                _add_poi("cave", pygame.Rect(rx, ry, rw, rh))
            if rng.random() < 0.35:
                rx = rng.randint(18, CHUNK_W - 96)
                ry = rng.randint(18, CHUNK_H - 70)
                rw = rng.randint(64, 96)
                rh = rng.randint(42, 70)
                _add_poi("cabin", pygame.Rect(rx, ry, rw, rh))
        # Loot stuffing inside any building-like rects (houses/buildings/garages/facilities/bunkers)
        # Uses the same resources list and item kinds as the base generation.
        for br in building_rects:
            # Avoid overfilling: 0..6 extra items per structure
            extra = 1 + rng.randint(0, 5)
            for _ in range(extra):
                gx = rng.randint(br.x + 6, min(br.x + br.w - 6, CHUNK_W - 10))
                gy = rng.randint(br.y + 6, min(br.y + br.h - 6, CHUNK_H - 10))
                roll = rng.random()
                if roll < 0.34:
                    self.resources.append([gx, gy, "ammo", rng.randint(10, 26)])
                elif roll < 0.52:
                    self.resources.append([gx, gy, "fuel", rng.randint(10, 28)])
                elif roll < 0.64:
                    self.resources.append([gx, gy, "medkit", 1])
                elif roll < 0.73:
                    self.resources.append([gx, gy, "grenade", 1])
                elif roll < 0.79:
                    self.resources.append([gx, gy, "dynamite", 1])
                elif roll < 0.92 and rng.random() < 0.55:
                    self.resources.append([gx, gy, "parts", 1])
                else:
                    # weapon pickup (rare)
                    if rng.random() < 0.25:
                        wname = weighted_choice(rng, WEAPON_SPAWN_POOL)
                        self.resources.append([gx, gy, "weapon", wname])
        # --- Parking lot vehicles ---
        if self.variant == "parking_lot":
            for _ in range(rng.randint(5, 10)):
                x = rng.randint(22, CHUNK_W - 22)
                y = rng.randint(22, CHUNK_H - 22)
                self.structs.append(("car_wreck", pygame.Rect(x - 10, y - 6, 20, 12)))
            if rng.random() < 0.65:
                for _ in range(rng.randint(1, 2)):
                    wx = self.cx * CHUNK_W + rng.randint(34, CHUNK_W - 34)
                    wy = self.cy * CHUNK_H + rng.randint(34, CHUNK_H - 34)
                    self.vehicles.append(PitVehicle(wx, wy, rng))
# zombies reduced
        if rng.random() < 0.45:
            for _ in range(rng.randint(1, 3)):
                ex = rng.randint(30, CHUNK_W - 30)
                ey = rng.randint(30, CHUNK_H - 30)
                self.zombies.append(PitZombie(self.cx * CHUNK_W + ex, self.cy * CHUNK_H + ey, rng))

        
        # --- Variant enemies (kept rare) ---
        # Raiders with guns (shooters)
        # Shooters appear across several pit stop variants (still uncommon).
        raider_ch = 0.0
        if self.variant == "parking_lot":
            raider_ch = 0.12
        elif self.variant in ("market_ruins", "military_outpost", "industrial_plant"):
            raider_ch = 0.18
        elif self.variant in ("ghost_town", "junkyard", "wasteland"):
            raider_ch = 0.10

        if rng.random() < raider_ch:
            n = rng.randint(1, 2)
            for _ in range(n):
                ex = rng.randint(34, CHUNK_W - 34)
                ey = rng.randint(34, CHUNK_H - 34)
                weapon_key = rng.choices(["pistol", "rifle", "smg", "marksman"], weights=[6, 6, 3, 1], k=1)[0]
                self.raiders.append(PitRaider(self.cx * CHUNK_W + ex, self.cy * CHUNK_H + ey, rng, weapon_key=weapon_key))

        # Mutants (toxic / wasteland)
        if self.variant in ("toxic_dumps", "wasteland") and rng.random() < 0.22:
            for _ in range(rng.randint(1, 2)):
                ex = rng.randint(34, CHUNK_W - 34)
                ey = rng.randint(34, CHUNK_H - 34)
                self.mutants.append(PitMutant(self.cx * CHUNK_W + ex, self.cy * CHUNK_H + ey, rng))

        # Wraiths (ghost town)
        if self.variant in ("ghost_town", "cemetery") and rng.random() < 0.28:
            for _ in range(rng.randint(1, 2)):
                ex = rng.randint(34, CHUNK_W - 34)
                ey = rng.randint(34, CHUNK_H - 34)
                self.wraiths.append(PitWraith(self.cx * CHUNK_W + ex, self.cy * CHUNK_H + ey, rng))

        # Hounds (fast melee)
        if self.variant in ("desert", "wasteland", "junkyard", "mountain_pass") and rng.random() < 0.24:
            n = rng.randint(1, 2)
            for _ in range(n):
                ex = rng.randint(34, CHUNK_W - 34)
                ey = rng.randint(34, CHUNK_H - 34)
                self.hounds.append(PitHound(self.cx * CHUNK_W + ex, self.cy * CHUNK_H + ey, rng))

        # Sentries (stationary ranged)
        if self.variant in ("military_outpost", "industrial_plant", "parking_lot") and rng.random() < 0.22:
            ex = rng.randint(40, CHUNK_W - 40)
            ey = rng.randint(40, CHUNK_H - 40)
            self.sentries.append(PitSentry(self.cx * CHUNK_W + ex, self.cy * CHUNK_H + ey, rng))

        # -------------------------------------------------
        # Loot placement
        # Prefer placing loot inside building-like structures
        # so pit stops feel like "searching houses" vs. open-field loot.
        # -------------------------------------------------
        loot_bias_in_buildings = 0.82 if building_rects else 0.0

        def _pick_loot_xy(pad=6):
            if building_rects and rng.random() < loot_bias_in_buildings:
                br = rng.choice(building_rects)
                lx0 = int(br.x + pad)
                ly0 = int(br.y + pad)
                lx1 = int(min(br.x + br.w - pad, CHUNK_W - 12))
                ly1 = int(min(br.y + br.h - pad, CHUNK_H - 12))
                if lx1 > lx0 and ly1 > ly0:
                    return rng.randint(lx0, lx1), rng.randint(ly0, ly1)
            return rng.randint(20, CHUNK_W - 20), rng.randint(20, CHUNK_H - 20)

        # fuel
        if rng.random() < 0.95:
            for _ in range(rng.randint(2, 5)):
                gx, gy = _pick_loot_xy()
                amt = rng.randint(10, 35)
                self.resources.append([gx, gy, "fuel", amt])

        # ammo
        if rng.random() < 0.80:
            for _ in range(rng.randint(1, 3)):
                ax, ay = _pick_loot_xy()
                amt = rng.randint(10, 30)
                self.resources.append([ax, ay, "ammo", amt])

        # medkits
        if rng.random() < 0.62:
            for _ in range(rng.randint(1, 2)):
                mx, my = _pick_loot_xy()
                self.resources.append([mx, my, "medkit", 1])

        # explosives
        if rng.random() < 0.48:
            for _ in range(rng.randint(0, 2)):
                ex, ey = _pick_loot_xy()
                self.resources.append([ex, ey, "grenade", 1])
        if rng.random() < 0.32:
            dx, dy = _pick_loot_xy()
            self.resources.append([dx, dy, "dynamite", 1])

        # vehicle parts (repair road car) — boosted when this pit stop was triggered by breakdown
        parts_chance = 0.30 if not self.breakdown else 0.85
        if rng.random() < parts_chance:
            for _ in range(rng.randint(1, 2 if not self.breakdown else 4)):
                px, py = _pick_loot_xy()
                amt = rng.randint(1, 2) if not self.breakdown else rng.randint(1, 3)
                self.resources.append([px, py, "parts", amt])

        # weapons
        if rng.random() < 0.58:
            wx, wy = _pick_loot_xy(pad=8)
            wname = weighted_choice(rng, WEAPON_SPAWN_POOL)
            self.resources.append([wx, wy, "weapon", wname])



    def draw(self, surf, cam_x, cam_y):
        base_x = self.cx * CHUNK_W - cam_x
        base_y = self.cy * CHUNK_H - cam_y

        pygame.draw.rect(surf, self.pal['dirt_a'], (base_x, base_y, CHUNK_W, CHUNK_H))
        for yy in range(int(base_y), int(base_y + CHUNK_H), 6):
            pygame.draw.line(surf, self.pal['dirt_b'], (base_x, yy), (base_x + CHUNK_W, yy), 1)

        if self.variant == "parking_lot":
            # NOTE: Previously this variant drew a full vertical+horizontal grid which could look like debug grid lines.
            # Replace with subtle, sparse, *dashed* parking markings so it reads as asphalt without the overlay-grid look.
            lane_col = self.pal.get("lane", (120, 112, 100))
            prng = random.Random(self.seed ^ 0xBEEF1234)
            orientation = prng.choice(["vertical", "horizontal"])

            if orientation == "vertical":
                x0 = prng.randint(10, 26)
                step = prng.choice([44, 48, 52])
                for lx in range(x0, CHUNK_W, step):
                    sx = int(base_x + lx)
                    # dashed segments
                    for yy2 in range(12, CHUNK_H - 12, 16):
                        if prng.random() < 0.88:
                            pygame.draw.line(surf, lane_col, (sx, base_y + yy2), (sx, base_y + yy2 + 8), 1)
            else:
                y0 = prng.randint(10, 26)
                step = prng.choice([44, 48, 52])
                for ly in range(y0, CHUNK_H, step):
                    sy = int(base_y + ly)
                    for xx in range(12, CHUNK_W - 12, 16):
                        if prng.random() < 0.88:
                            pygame.draw.line(surf, lane_col, (base_x + xx, sy), (base_x + xx + 8, sy), 1)

            # occasional cracked/patch lines (very subtle)
            if prng.random() < 0.45:
                for _ in range(prng.randint(2, 5)):
                    x1 = int(base_x + prng.randint(12, CHUNK_W - 12))
                    y1 = int(base_y + prng.randint(12, CHUNK_H - 12))
                    x2 = x1 + prng.randint(-22, 22)
                    y2 = y1 + prng.randint(-18, 18)
                    pygame.draw.line(surf, (24, 24, 26), (x1, y1), (x2, y2), 1)

        for kind, r in self.structs:
            rr = pygame.Rect(int(r.x + base_x), int(r.y + base_y), r.w, r.h)
            if kind == "crate":
                outline_rect(surf, rr, self.pal['crate'], radius=1)
                pygame.draw.rect(surf, (30, 24, 20), (rr.x + 2, rr.y + 2, rr.w - 4, 2))
            elif kind == "wall":
                outline_rect(surf, rr, self.pal['wall'], radius=1)
            elif kind == "building":
                outline_rect(surf, rr, self.pal['building'], radius=2)
                for wy in range(rr.y + 6, rr.y + rr.h - 6, 10):
                    pygame.draw.rect(surf, self.pal['window'], (rr.x + 6, wy, 8, 4))
                pygame.draw.rect(surf, self.pal['roof'], (rr.x + 4, rr.y + 4, rr.w - 8, 6))
            
            elif kind == "barrel":
                outline_rect(surf, rr, self.pal['barrel'], radius=2)
                pygame.draw.rect(surf, (30, 28, 26), (rr.x + 2, rr.y + 2, rr.w - 4, 2))
                pygame.draw.rect(surf, (30, 28, 26), (rr.x + 2, rr.y + rr.h - 4, rr.w - 4, 2))
            elif kind == "wreck":
                outline_rect(surf, rr, self.pal['wreck'], radius=1)
                pygame.draw.rect(surf, (22, 22, 24), (rr.x + 2, rr.y + 2, max(1, rr.w - 4), max(1, rr.h - 4)))
            elif kind == "sign":
                outline_rect(surf, rr, self.pal["wall"], radius=1)
                pygame.draw.rect(surf, self.pal["decor_b"], (rr.x + 1, rr.y + 1, max(1, rr.w - 2), max(1, rr.h - 2)))
                pygame.draw.line(surf, self.pal["decor_a"], (rr.x, rr.y), (rr.x + rr.w, rr.y + rr.h), 1)
            elif kind == "fence":
                outline_rect(surf, rr, self.pal["decor_a"], radius=1)
                for fx in range(rr.x + 1, rr.x + rr.w - 1, 3):
                    pygame.draw.line(surf, self.pal["decor_b"], (fx, rr.y + 1), (fx, rr.y + rr.h - 2), 1)
            elif kind == "porch":
                outline_rect(surf, rr, self.pal["roof"], radius=1)
                pygame.draw.rect(surf, self.pal["decor_b"], (rr.x + 2, rr.y + 2, max(1, rr.w - 4), max(1, rr.h - 4)))
            elif kind == "toxic_pool":
                pygame.draw.rect(surf, self.pal["toxic_a"], rr, border_radius=2)
                pygame.draw.rect(surf, self.pal["toxic_b"], (rr.x + 2, rr.y + 2, max(1, rr.w - 4), max(1, rr.h - 4)), border_radius=2)
                if random.random() < 0.35:
                    pygame.draw.circle(surf, (10, 10, 10), (rr.x + rr.w // 2, rr.y + rr.h // 2), 1)
            elif kind == "pipe":
                outline_rect(surf, rr, self.pal["wall"], radius=2)
                pygame.draw.line(surf, self.pal["decor_b"], (rr.x + 2, rr.y + rr.h // 2), (rr.x + rr.w - 3, rr.y + rr.h // 2), 1)
            elif kind == "stack":
                outline_rect(surf, rr, self.pal["wreck"], radius=1)
                pygame.draw.rect(surf, self.pal["decor_b"], (rr.x + 2, rr.y + 2, max(1, rr.w - 4), 2))
                pygame.draw.rect(surf, self.pal["decor_b"], (rr.x + 2, rr.y + rr.h - 4, max(1, rr.w - 4), 2))
            elif kind == "tire":
                pygame.draw.ellipse(surf, self.pal["decor_b"], rr, 2)
                pygame.draw.ellipse(surf, self.pal["decor_a"], (rr.x + 2, rr.y + 2, max(1, rr.w - 4), max(1, rr.h - 4)), 1)
            elif kind == "dune":
                pygame.draw.ellipse(surf, self.pal["sand_a"], rr)
                pygame.draw.ellipse(surf, self.pal["sand_b"], (rr.x + 2, rr.y + 2, max(1, rr.w - 4), max(1, rr.h - 4)))
            elif kind == "bones":
                pygame.draw.rect(surf, (190, 180, 150), rr, 1)
                pygame.draw.line(surf, (190, 180, 150), (rr.x, rr.y + rr.h // 2), (rr.x + rr.w, rr.y + rr.h // 2), 1)
            elif kind == "scrap":
                outline_rect(surf, rr, self.pal["decor_a"], radius=1)
                pygame.draw.rect(surf, self.pal["decor_b"], (rr.x + 1, rr.y + 1, max(1, rr.w - 2), max(1, rr.h - 2)))
            elif kind == "stump":
                outline_rect(surf, rr, self.pal["decor_a"], radius=1)
                pygame.draw.circle(surf, self.pal["decor_b"], (rr.x + rr.w // 2, rr.y + rr.h // 2), max(1, min(rr.w, rr.h)//3), 1)
            else:
                pygame.draw.circle(surf, self.pal['rock'], (rr.x + 3, rr.y + 3), 2)

        if self.variant == "parking_lot":
            for v in self.vehicles:
                v.draw(surf, cam_x, cam_y)

        for gx, gy, kind, val in self.resources:
            sx = int(gx + base_x)
            sy = int(gy + base_y)

            if kind == "fuel":
                outline_rect(surf, (sx - 4, sy - 4, 9, 9), GAS_CAN, radius=1)
                pygame.draw.rect(surf, GAS_CAN_DARK, (sx - 2, sy - 2, 5, 5))
                pygame.draw.rect(surf, STEEL_DARK, (sx + 1, sy - 5, 2, 2))
            elif kind == "ammo":
                outline_rect(surf, (sx - 4, sy - 4, 9, 9), AMMO_COL, radius=1)
                pygame.draw.rect(surf, AMMO_DARK, (sx - 2, sy - 2, 5, 5))
                pygame.draw.rect(surf, (30, 30, 32), (sx - 2, sy - 5, 5, 2))
            elif kind == "medkit":
                outline_rect(surf, (sx - 4, sy - 4, 9, 9), MED_COL, radius=1)
                pygame.draw.rect(surf, MED_DARK, (sx - 2, sy - 2, 5, 5))
                pygame.draw.rect(surf, (230, 230, 230), (sx - 1, sy - 5, 2, 7))
                pygame.draw.rect(surf, (230, 230, 230), (sx - 4, sy - 2, 7, 2))
            elif kind in ("grenade", "dynamite"):
                outline_rect(surf, (sx - 4, sy - 4, 9, 9), EXPLO_COL, radius=1)
                pygame.draw.rect(surf, EXPLO_DARK, (sx - 2, sy - 2, 5, 5))
                pygame.draw.circle(surf, (30, 30, 30), (sx, sy), 1)
            elif kind == "parts":
                outline_rect(surf, (sx - 4, sy - 4, 9, 9), PARTS_COL, radius=1)
                pygame.draw.rect(surf, PARTS_DARK, (sx - 2, sy - 2, 5, 5))
                pygame.draw.circle(surf, STEEL_DARK, (sx, sy), 2)
            elif kind == "weapon":
                outline_rect(surf, (sx - 6, sy - 3, 12, 7), WEAPON_COL, radius=1)
                pygame.draw.rect(surf, WEAPON_DARK, (sx - 4, sy - 1, 8, 3))
                pygame.draw.rect(surf, STEEL_DARK, (sx + 1, sy - 4, 6, 2))

    def try_auto_pickups(self, player_wx, player_wy, pickup_r=13):
        got = []
        for r in self.resources[:]:
            gx, gy, kind, val = r
            wx = self.cx * CHUNK_W + gx
            wy = self.cy * CHUNK_H + gy
            if point_in_radius(player_wx, player_wy, wx, wy, pickup_r):
                got.append((kind, val))
                self.resources.remove(r)
        return got

# -----------------------------------------------------
# Pit Session
# -----------------------------------------------------
class PitStopSession:
    def __init__(self, base_w=BASE_W, base_h=BASE_H, seed_base=None, persistent_inventory=None, persistent_hp=100, breakdown=False, audio=None):
        self.base_w = base_w
        self.base_h = base_h

        self.seed_base = seed_base if seed_base is not None else random.randint(0, 2**31 - 1)
        self.breakdown = bool(breakdown)
        self.audio = audio
        # Pick a pit-stop variant each session. This changes ONLY scenery + structure flavor.
        # Item generation and player behavior remain unchanged.
        _vrng = random.Random(self.seed_base ^ 0x5A17)
        self.variant = _vrng.choice(PIT_VARIANTS)
        self.pal = PIT_VARIANT_PALETTES.get(self.variant, PIT_VARIANT_PALETTES['default'])
        self.chunks = {}

        self.in_vehicle = False
        self.vehicle = None
        self.e_cd = 0

        self.inv = persistent_inventory if persistent_inventory else Inventory()
        self.player = PitPlayer(self.inv)
        self.player.hp = persistent_hp

        self.bullets = []
        self.particles = []
        self.explosions = []

        self.splats = []
        self.cam_x = self.player.wx - self.base_w / 2
        self.cam_y = self.player.wy - self.base_h / 2

        self.done = False

        self.dead = False
        self.font = load_font("fonts/ui.ttf", 10)
        self.font_small = load_font("fonts/ui.ttf", 9)

        self.msg = ""
        self.msg_t = 0
        if self.breakdown:
            self.msg = "BREAKDOWN PIT STOP — FIND PARTS"
            self.msg_t = 150

        self._tab_cd = 0
        self._med_cd = 0
        self._throw_cd = 0

    def _chunk_seed(self, cx, cy):
        return (self.seed_base ^ (cx * 73856093) ^ (cy * 19349663)) & 0x7fffffff

    def _get_chunk(self, cx, cy):
        key = (cx, cy)
        if key not in self.chunks:
            self.chunks[key] = PitChunk(cx, cy, self._chunk_seed(cx, cy), breakdown=self.breakdown, audio=self.audio, variant=self.variant, pal=self.pal)
        return self.chunks[key]

    def _world_to_chunk(self, wx, wy):
        return int(math.floor(wx / CHUNK_W)), int(math.floor(wy / CHUNK_H))

    def _add_splat(self, x, y):
        r = random.randint(3, 7)
        self.splats.append((float(x) + random.uniform(-2, 2), float(y) + random.uniform(-2, 2), r))
        if len(self.splats) > 260:
            self.splats = self.splats[-220:]

    def update(self, keys, mouse_pressed, mouse_pos):
        if keys[pygame.K_SPACE]:
            self.done = True
            return

        if self._tab_cd > 0: self._tab_cd -= 1
        if self._med_cd > 0: self._med_cd -= 1
        if self._throw_cd > 0: self._throw_cd -= 1
        if self.e_cd > 0: self.e_cd -= 1

        if keys[pygame.K_TAB] and self._tab_cd == 0:
            self.player.cycle_weapon()
            self._tab_cd = 14

        if keys[pygame.K_f] and self._med_cd == 0:
            if self.player.try_use_medkit(self.particles):
                if self.audio is not None:
                    self.audio.play('pit/medkit', volume=0.9)
                self.msg = "USED MEDKIT"
                self.msg_t = 40
            self._med_cd = 14

        # Vehicle enter/exit (parking lot variant only)
        if keys[pygame.K_e] and self.e_cd == 0:
            if self.in_vehicle:
                self.in_vehicle = False
                self.vehicle = None
                self.msg = "EXITED VEHICLE"
                self.msg_t = 40
                self.e_cd = 18
            elif self.variant == "parking_lot":
                nearest = None
                best_d2 = 18 * 18
                pcx0, pcy0 = self._world_to_chunk(self.player.wx, self.player.wy)
                for ddx in range(-PIT_DRAW_RADIUS, PIT_DRAW_RADIUS + 1):
                    for ddy in range(-PIT_DRAW_RADIUS, PIT_DRAW_RADIUS + 1):
                        ch = self._get_chunk(pcx0 + ddx, pcy0 + ddy)
                        for v in getattr(ch, "vehicles", []):
                            dx = v.wx - self.player.wx
                            dy = v.wy - self.player.wy
                            d2 = dx * dx + dy * dy
                            if d2 < best_d2:
                                best_d2 = d2
                                nearest = v
                if nearest is not None:
                    self.in_vehicle = True
                    self.vehicle = nearest
                    self.player.wx = nearest.wx
                    self.player.wy = nearest.wy
                    self.msg = "ENTERED VEHICLE"
                    self.msg_t = 40
                    self.e_cd = 18

        if self.in_vehicle and self.vehicle is not None:
            self.vehicle.update(keys)
            self.player.wx = self.vehicle.wx
            self.player.wy = self.vehicle.wy
            if mouse_pressed[0]:
                self.vehicle.try_shoot(self.bullets, self.particles, self.cam_x, self.cam_y, mouse_pos, self.player.inv, audio=self.audio)
        else:
            self.player.update(keys)

        pcx, pcy = self._world_to_chunk(self.player.wx, self.player.wy)
        for dx in range(-PIT_DRAW_RADIUS, PIT_DRAW_RADIUS + 1):
            for dy in range(-PIT_DRAW_RADIUS, PIT_DRAW_RADIUS + 1):
                self._get_chunk(pcx + dx, pcy + dy)

        target_cam_x = self.player.wx - self.base_w / 2
        target_cam_y = self.player.wy - self.base_h / 2
        self.cam_x += (target_cam_x - self.cam_x) * 0.12
        self.cam_y += (target_cam_y - self.cam_y) * 0.12

        # Auto pickups
        got_any = False
        for dx in range(-1, 2):
            for dy in range(-1, 2):
                ch = self._get_chunk(pcx + dx, pcy + dy)
                got = ch.try_auto_pickups(self.player.wx, self.player.wy, pickup_r=13)
                for kind, val in got:
                    got_any = True
                    if kind == "fuel":
                        self.inv.add("fuel", int(val))
                        self.msg = f"+FUEL {int(val)}"
                        self.msg_t = 20
                    elif kind == "ammo":
                        self.inv.add("ammo", int(val))
                        self.msg = f"+AMMO {int(val)}"
                        self.msg_t = 20
                    elif kind == "medkit":
                        self.inv.add("medkit", 1)
                        self.msg = "+MEDKIT"
                        self.msg_t = 20
                    elif kind == "grenade":
                        self.inv.add("grenade", 1)
                        self.msg = "+GRENADE"
                        self.msg_t = 20
                    elif kind == "dynamite":
                        self.inv.add("dynamite", 1)
                        self.msg = "+DYNAMITE"
                        self.msg_t = 20
                    elif kind == "parts":
                        self.inv.add("parts", int(val))
                        self.msg = f"+PARTS x{int(val)}"
                        self.msg_t = 30
                    elif kind == "weapon":
                        self.inv.add(val, 1)
                        if self.player.equipped is None:
                            self.player.equipped = val
                        self.msg = f"FOUND {WEAPON_DISPLAY.get(val, val.upper())}"
                        self.msg_t = 60

        if got_any:
            if self.audio is not None:
                self.audio.play('pit/pickup', volume=0.85)
            for _ in range(6):
                self.particles.append(Particle(self.player.wx, self.player.wy,
                                               random.uniform(-1.0, 1.0),
                                               random.uniform(-1.2, 0.4),
                                               random.randint(10, 16),
                                               SPARK, grow=False))

        # Attack
        if mouse_pressed[0]:
            near_z = []
            for dx in range(-1, 2):
                for dy in range(-1, 2):
                    ch = self._get_chunk(pcx + dx, pcy + dy)
                    near_z.extend(ch.zombies)
                    near_z.extend(ch.raiders)
                    near_z.extend(ch.mutants)
                    near_z.extend(ch.wraiths)
                    near_z.extend(getattr(ch, 'hounds', []))
                    near_z.extend(getattr(ch, 'sentries', []))
            self.player.try_attack(self.bullets, self.particles, mouse_pos, self.cam_x, self.cam_y, near_z, audio=self.audio)

        # Throw explosive
        if mouse_pressed[2] and self._throw_cd == 0:
            if self.player.try_throw_explosive(self.explosions, self.particles, mouse_pos, self.cam_x, self.cam_y, audio=self.audio):
                self.msg = "THREW EXPLOSIVE"
                self.msg_t = 30
                self._throw_cd = 18

        
        # Enemies + player damage (melee from zombies/mutants/wraiths)
        player_hit = False
        for dx in range(-1, 2):
            for dy in range(-1, 2):
                ch = self._get_chunk(pcx + dx, pcy + dy)

                for z in ch.zombies:
                    if z.update(self.player.wx, self.player.wy, self.particles):
                        player_hit = True

                for m in ch.mutants:
                    if m.update(self.player.wx, self.player.wy, self.particles):
                        player_hit = True

                for w in ch.wraiths:
                    if w.update(self.player.wx, self.player.wy, self.particles):
                        player_hit = True

                for h in ch.hounds:
                    if h.update(self.player.wx, self.player.wy, self.particles):
                        player_hit = True

                for t in ch.sentries:
                    t.update(self.player.wx, self.player.wy, self.bullets, self.particles, audio=self.audio)

                for r in ch.raiders:
                    r.update(self.player.wx, self.player.wy, self.bullets, self.particles, audio=self.audio)
                # Vehicle run-overs (parking lot): splat enemies on contact
                if self.in_vehicle and self.vehicle is not None:
                    vx = self.vehicle.wx
                    vy = self.vehicle.wy
                    rad2 = 14 * 14
                    def _splat(px, py):
                        for _ in range(10):
                            self.particles.append(Particle(px, py, random.uniform(-1.2, 1.2), random.uniform(-1.2, 1.2), random.randint(10, 22), BLOOD, grow=False))
                    for z in ch.zombies:
                        dx0 = z.wx - vx; dy0 = z.wy - vy
                        if dx0 * dx0 + dy0 * dy0 < rad2:
                            z.hp = 0; _splat(z.wx, z.wy)
                            if self.audio is not None: self.audio.play('pit/zombie_death', volume=0.7)
                    for mm in ch.mutants:
                        dx0 = mm.wx - vx; dy0 = mm.wy - vy
                        if dx0 * dx0 + dy0 * dy0 < rad2:
                            mm.hp = 0; _splat(mm.wx, mm.wy)
                            if self.audio is not None: self.audio.play('pit/zombie_death', volume=0.7)
                    for ww in ch.wraiths:
                        dx0 = ww.wx - vx; dy0 = ww.wy - vy
                        if dx0 * dx0 + dy0 * dy0 < rad2:
                            ww.hp = 0; _splat(ww.wx, ww.wy)
                    for rr in ch.raiders:
                        dx0 = rr.wx - vx; dy0 = rr.wy - vy
                        if dx0 * dx0 + dy0 * dy0 < rad2:
                            rr.hp = 0; _splat(rr.wx, rr.wy)
                            if self.audio is not None: self.audio.play('pit/zombie_death', volume=0.7)
                    for hh in ch.hounds:
                        dx0 = hh.wx - vx; dy0 = hh.wy - vy
                        if dx0 * dx0 + dy0 * dy0 < rad2:
                            hh.hp = 0; _splat(hh.wx, hh.wy)
                            if self.audio is not None: self.audio.play('pit/zombie_death', volume=0.7)
                    for tt in ch.sentries:
                        dx0 = tt.wx - vx; dy0 = tt.wy - vy
                        if dx0 * dx0 + dy0 * dy0 < rad2:
                            tt.hp = 0; _splat(tt.wx, tt.wy)
                            if self.audio is not None: self.audio.play('pit/zombie_death', volume=0.7)

        if player_hit:
            if self.audio is not None:
                self.audio.play('pit/hurt', volume=0.9)
            self.player.hp = max(0, self.player.hp - 2)
            if self.msg_t <= 0:
                self.msg = "YOU'RE GETTING SWARMED"
                self.msg_t = 30

        if self.player.hp <= 0:
            self.dead = True
            self.done = True
            self.msg = "YOU DIED"
            self.msg_t = 120
            return

        # Explosions apply AoE damage once (on first frame)
        for ex in self.explosions[:]:
            if ex.life == 12:
                bc, br = self._world_to_chunk(ex.x, ex.y)
                for dx in range(-1, 2):
                    for dy in range(-1, 2):
                        ch = self._get_chunk(bc + dx, br + dy)
                        def _blast(e, hit_color=SPARK, death_particles=10, death_sfx=None):
                            dist = math.hypot(e.wx - ex.x, e.wy - ex.y)
                            if dist > ex.radius:
                                return False
                            dmg = int(ex.dmg * (1.0 - (dist / ex.radius) * 0.65))
                            e.hp -= max(10, dmg)
                            for _ in range(3):
                                self.particles.append(Particle(e.wx, e.wy,
                                                               random.uniform(-1.0, 1.0),
                                                               random.uniform(-1.0, 0.6),
                                                               random.randint(10, 16),
                                                               hit_color, grow=False))
                            if e.hp <= 0:
                                self._add_splat(e.wx, e.wy)
                                for _ in range(death_particles):
                                    self.particles.append(Particle(e.wx, e.wy,
                                                                   random.uniform(-1.8, 1.8),
                                                                   random.uniform(-1.8, 1.2),
                                                                   random.randint(14, 22),
                                                                   random.choice([FIRE1, FIRE2, SMOKE]),
                                                                   grow=True))
                                if self.audio is not None and death_sfx is not None:
                                    self.audio.play(death_sfx, volume=0.9)
                                return True
                            return False

                        for z in ch.zombies[:]:
                            if _blast(z, hit_color=SPARK, death_particles=10, death_sfx='pit/zombie_death'):
                                ch.zombies.remove(z)

                        for r in ch.raiders[:]:
                            if _blast(r, hit_color=SPARK, death_particles=8, death_sfx='pit/zombie_death'):
                                ch.raiders.remove(r)

                        for m in ch.mutants[:]:
                            if _blast(m, hit_color=SPARK, death_particles=9, death_sfx='pit/zombie_death'):
                                ch.mutants.remove(m)

                        for w in ch.wraiths[:]:
                            if _blast(w, hit_color=(180, 180, 200), death_particles=7, death_sfx=None):
                                ch.wraiths.remove(w)

                        for h in ch.hounds[:]:
                            if _blast(h, hit_color=SPARK, death_particles=7, death_sfx='pit/zombie_death'):
                                ch.hounds.remove(h)

                        for t in ch.sentries[:]:
                            if _blast(t, hit_color=SPARK, death_particles=6, death_sfx='pit/zombie_death'):
                                ch.sentries.remove(t)

            ex.update()
            if ex.life <= 0:
                self.explosions.remove(ex)

        
        # bullets hit enemies / player
        for b in self.bullets[:]:
            b.update()
            if b.life <= 0:
                self.bullets.remove(b)
                continue

            # Raider bullets can hit the player
            if b.owner in ("pit_raider", "pit_sentry"):
                if abs(b.x - self.player.wx) < 7 and abs(b.y - self.player.wy) < 7:
                    self.player.hp = max(0, self.player.hp - max(1, int(b.dmg * 0.8)))
                    for _ in range(4):
                        self.particles.append(Particle(self.player.wx, self.player.wy, random.uniform(-1.0, 1.0), random.uniform(-1.0, 0.6),
                                                       random.randint(10, 16), SPARK, grow=False))
                    if self.audio is not None and random.random() < 0.6:
                        self.audio.play('pit/hurt', volume=0.75)
                    self.bullets.remove(b)
                continue

            # Player bullets hit enemies
            bc, br = self._world_to_chunk(b.x, b.y)
            hit = False
            for dx in range(-1, 2):
                for dy in range(-1, 2):
                    ch = self._get_chunk(bc + dx, br + dy)

                    # zombies
                    for z in ch.zombies[:]:
                        if abs(b.x - z.wx) < 7 and abs(b.y - z.wy) < 7:
                            z.hp -= b.dmg
                            hit = True
                            for _ in range(4):
                                self.particles.append(Particle(z.wx, z.wy, random.uniform(-1.0, 1.0), random.uniform(-1.0, 0.6),
                                                               random.randint(10, 16), SPARK, grow=False))
                            if z.hp <= 0:
                                self._add_splat(z.wx, z.wy)
                                if self.audio is not None:
                                    self.audio.play('pit/zombie_death', volume=0.75)
                                for _ in range(10):
                                    self.particles.append(Particle(z.wx, z.wy, random.uniform(-1.8, 1.8), random.uniform(-1.8, 1.2),
                                                                   random.randint(14, 22), random.choice([FIRE1, FIRE2, SMOKE]), grow=True))
                                ch.zombies.remove(z)
                            break

                    if hit:
                        break

                    # raiders
                    for r in ch.raiders[:]:
                        if abs(b.x - r.wx) < 7 and abs(b.y - r.wy) < 7:
                            r.hp -= b.dmg
                            hit = True
                            for _ in range(4):
                                self.particles.append(Particle(r.wx, r.wy, random.uniform(-1.0, 1.0), random.uniform(-1.0, 0.6),
                                                               random.randint(10, 16), SPARK, grow=False))
                            if r.hp <= 0:
                                self._add_splat(r.wx, r.wy)
                                # raiders can drop loot
                                if random.random() < 0.55:
                                    ch.resources.append([int(r.wx - ch.cx * CHUNK_W), int(r.wy - ch.cy * CHUNK_H), "ammo", random.randint(8, 18)])
                                if random.random() < 0.18:
                                    wname = weighted_choice(random.Random((int(r.wx)*92821) ^ (int(r.wy)*68917) ^ 1337), WEAPON_SPAWN_POOL)
                                    ch.resources.append([int(r.wx - ch.cx * CHUNK_W), int(r.wy - ch.cy * CHUNK_H), "weapon", wname])
                                ch.raiders.remove(r)
                            break

                    if hit:
                        break

                    # mutants
                    for m in ch.mutants[:]:
                        if abs(b.x - m.wx) < 8 and abs(b.y - m.wy) < 8:
                            m.hp -= b.dmg
                            hit = True
                            for _ in range(4):
                                self.particles.append(Particle(m.wx, m.wy, random.uniform(-1.0, 1.0), random.uniform(-1.0, 0.6),
                                                               random.randint(10, 16), SPARK, grow=False))
                            if m.hp <= 0:
                                self._add_splat(m.wx, m.wy)
                                if random.random() < 0.35:
                                    ch.resources.append([int(m.wx - ch.cx * CHUNK_W), int(m.wy - ch.cy * CHUNK_H), "parts", 1])
                                ch.mutants.remove(m)
                            break

                    if hit:
                        break

                    # wraiths
                    for w in ch.wraiths[:]:
                        if abs(b.x - w.wx) < 7 and abs(b.y - w.wy) < 7:
                            w.hp -= b.dmg
                            hit = True
                            for _ in range(3):
                                self.particles.append(Particle(w.wx, w.wy, random.uniform(-1.0, 1.0), random.uniform(-1.0, 0.6),
                                                               random.randint(10, 16), (180, 180, 200), grow=False))
                            if w.hp <= 0:
                                self._add_splat(w.wx, w.wy)
                                ch.wraiths.remove(w)
                            break

                    if hit:
                        break


                    # hounds
                    for h in ch.hounds[:]:
                        if abs(b.x - h.wx) < 7 and abs(b.y - h.wy) < 7:
                            h.hp -= b.dmg
                            hit = True
                            for _ in range(4):
                                self.particles.append(Particle(h.wx, h.wy, random.uniform(-1.0, 1.0), random.uniform(-1.0, 0.6),
                                                               random.randint(10, 16), SPARK, grow=False))
                            if h.hp <= 0:
                                self._add_splat(h.wx, h.wy)
                                if self.audio is not None:
                                    self.audio.play('pit/zombie_death', volume=0.7)
                                ch.hounds.remove(h)
                            break

                    if hit:
                        break

                    # sentries
                    for t in ch.sentries[:]:
                        if abs(b.x - t.wx) < 8 and abs(b.y - t.wy) < 8:
                            t.hp -= b.dmg
                            hit = True
                            for _ in range(4):
                                self.particles.append(Particle(t.wx, t.wy, random.uniform(-1.0, 1.0), random.uniform(-1.0, 0.6),
                                                               random.randint(10, 16), SPARK, grow=False))
                            if t.hp <= 0:
                                self._add_splat(t.wx, t.wy)
                                if self.audio is not None:
                                    self.audio.play('pit/zombie_death', volume=0.7)
                                ch.sentries.remove(t)
                            break

                    if hit:
                        break

                if hit:
                    break

            if hit and b in self.bullets:
                self.bullets.remove(b)
        for p in self.particles[:]:
            p.update()
            if p.life <= 0:
                self.particles.remove(p)

        if self.msg_t > 0:
            self.msg_t -= 1

    def draw(self, surf):
        pcx, pcy = self._world_to_chunk(self.player.wx, self.player.wy)

        for cx in range(pcx - PIT_DRAW_RADIUS, pcx + PIT_DRAW_RADIUS + 1):
            for cy in range(pcy - PIT_DRAW_RADIUS, pcy + PIT_DRAW_RADIUS + 1):
                self._get_chunk(cx, cy).draw(surf, self.cam_x, self.cam_y)

        for x, y, r in self.splats:
            sx = int(x - self.cam_x)
            sy = int(y - self.cam_y)
            pygame.draw.circle(surf, BLOOD, (sx, sy), r)
            pygame.draw.circle(surf, BLOOD_DARK, (sx + 1, sy + 1), max(1, r - 2))

        for dx in range(-PIT_DRAW_RADIUS, PIT_DRAW_RADIUS + 1):
            for dy in range(-PIT_DRAW_RADIUS, PIT_DRAW_RADIUS + 1):
                ch = self._get_chunk(pcx + dx, pcy + dy)
                for z in ch.zombies:
                    z.draw(surf, self.cam_x, self.cam_y)
                for m in ch.mutants:
                    m.draw(surf, self.cam_x, self.cam_y)
                for w in ch.wraiths:
                    w.draw(surf, self.cam_x, self.cam_y)
                for r in ch.raiders:
                    r.draw(surf, self.cam_x, self.cam_y)
                for h in ch.hounds:
                    h.draw(surf, self.cam_x, self.cam_y)
                for t in ch.sentries:
                    t.draw(surf, self.cam_x, self.cam_y)

        for b in self.bullets:
            b.draw_screen(surf, self.cam_x, self.cam_y)

        for ex in self.explosions:
            ex.draw_screen(surf, self.cam_x, self.cam_y)

        self.player.draw(surf, self.cam_x, self.cam_y)

        for p in self.particles:
            p.draw_screen(surf, self.cam_x, self.cam_y, self.base_w, self.base_h)

        pygame.draw.rect(surf, UI_BG, (0, 0, self.base_w, 22))
        surf.blit(self.font.render("PIT STOP — WASD | LMB fight | RMB explosive | TAB cycle | F medkit | SPACE return", True, UI_FG), (8, 6))

        pygame.draw.rect(surf, UI_BG, (0, self.base_h - 24, self.base_w, 24))
        ammo = self.inv.count("ammo")
        meds = self.inv.count("medkit")
        fuel = self.inv.count("fuel")
        wep = WEAPON_DISPLAY.get(self.player.equipped, "NONE")
        gren = self.inv.count("grenade")
        dyn = self.inv.count("dynamite")
        parts = self.inv.count('parts')
        info = f"HP {self.player.hp}/{self.player.hp_max} | WPN {wep} | AMMO {ammo} | MED {meds} | FUEL {fuel} | PARTS {parts} | GRN {gren} | DYN {dyn}"
        surf.blit(self.font_small.render(info, True, UI_FG), (8, self.base_h - 16))

        pygame.draw.rect(surf, (24, 24, 24), (self.base_w - 126, self.base_h - 18, 110, 6))
        hp_pct = self.player.hp / max(1, self.player.hp_max)
        hp_col = OK if hp_pct > 0.55 else WARN if hp_pct > 0.25 else BAD
        pygame.draw.rect(surf, hp_col, (self.base_w - 126, self.base_h - 18, int(110 * hp_pct), 6))

        if self.msg_t > 0:
            outline_rect(surf, (self.base_w - 240, 26, 234, 18), UI_BG, radius=2)
            surf.blit(self.font_small.render(self.msg, True, (200, 180, 120)), (self.base_w - 232, 30))



# =====================================================
# ROAD CITY (regenerate on every return-to-car)
# =====================================================
def build_new_city(num_strips=NUM_STRIPS, start_x=0.0, seed=None):
    """
    Build a fresh road 'city' (background strip set) and a per-load palette variation.
    Called:
    - at game start
    - every time the player returns from a pit stop to the car
    """
    city_seed = int(seed) if seed is not None else random.randint(0, 2**31 - 1)
    rng = random.Random(city_seed)

    # Per-load palette drift (kept subtle so readability stays high).
    city_pal = {
        "sky_top": jitter_color(SKY_TOP, rng, amount=20),
        "sky_bot": jitter_color(SKY_BOT, rng, amount=22),
        "sun": jitter_color(SUN, rng, amount=26),
        "haze": jitter_color(HAZE, rng, amount=18),

        "road": jitter_color(ROAD, rng, amount=10),
        "road_dark": jitter_color(ROAD_DARK, rng, amount=10),
        "road_edge": jitter_color(ROAD_EDGE, rng, amount=12),
        "lane": jitter_color(LANE, rng, amount=14),
    }

    # Color-grade overlay used to vary the *city* look each load (background only).
    grade_choices = [
        ((18, 12, 6), 26),    # warm rust
        ((6, 10, 18), 26),    # cool dusk
        ((12, 16, 8), 22),    # sickly green haze
        ((18, 6, 12), 22),    # magenta-ish twilight
    ]
    gc, ga = rng.choice(grade_choices)
    city_pal["grade_col"] = gc
    city_pal["grade_alpha"] = ga

    strips = []
    wx = float(start_x)
    prev = None
    for _ in range(num_strips):
        b = pick_biome(prev, rng=rng)
        strip_seed = rng.randint(0, 2**31 - 1)
        strips.append(WorldStrip(wx, b, seed=strip_seed))
        prev = b
        wx += STRIP_W
    return strips, city_seed, city_pal


# =====================================================
# WEATHER (road + mild ambient in pit)
# =====================================================
class WeatherSystem:
    """Lightweight weather that changes over time (visual-first, stable gameplay)."""
    def __init__(self, seed=0, biome=BIOME_DESERT):
        self.rng = random.Random(int(seed) ^ 0xA11CE)
        self.kind = "clear"
        self.intensity = 0.0
        self.timer = 0
        self.flash_t = 0
        self.drops = []  # [x,y,spd]
        self.reset_for_city(seed, biome)

    def reset_for_city(self, seed, biome):
        self.rng = random.Random(int(seed) ^ 0xA11CE)
        # Biome-weighted starting weather
        if biome == BIOME_DESERT:
            kinds = ["clear", "clear", "dust_storm", "clear", "fog"]
        elif biome == BIOME_RUINS:
            kinds = ["fog", "fog", "clear", "storm"]
        elif biome == BIOME_SCRUB:
            kinds = ["clear", "clear", "rain", "fog"]
        else:
            kinds = ["clear", "clear", "rain", "storm", "fog"]

        self.kind = self.rng.choice(kinds)
        if self.kind == "storm":
            self.kind = self.rng.choice(["storm", "heavy_rain"])
        self.intensity = self.rng.uniform(0.35, 0.85) if self.kind != "clear" else 0.0
        self.timer = self.rng.randint(FPS * 18, FPS * 42)
        self.flash_t = 0
        self.drops.clear()
        if self.kind in ("rain", "heavy_rain", "storm"):
            self._seed_drops()

    def _seed_drops(self):
        n = 70 if self.kind == "rain" else 120
        for _ in range(n):
            x = self.rng.uniform(0, BASE_W)
            y = self.rng.uniform(0, BASE_H)
            spd = self.rng.uniform(8.0, 14.0) * (1.0 + self.intensity * 0.7)
            self.drops.append([x, y, spd])

    def update(self, biome, scroll, in_pit=False):
        self.timer -= 1
        if self.timer <= 0:
            # rotate weather using a fresh seed but keep biome weighting
            self.reset_for_city(self.rng.randint(0, 2**31 - 1), biome)

        # lightning flashes (storm only)
        if self.kind in ("storm",) and self.rng.random() < 0.012:
            self.flash_t = self.rng.randint(4, 10)
        if self.flash_t > 0:
            self.flash_t -= 1

        # update rain drops
        if self.kind in ("rain", "heavy_rain", "storm"):
            if not self.drops:
                self._seed_drops()
            wind = (-0.4 if self.kind == "storm" else -0.2) * (0.5 + self.intensity)
            for d in self.drops:
                d[0] += wind * (1.0 + scroll * 0.05)
                d[1] += d[2] * (0.8 + scroll * 0.02)
                if d[1] > BASE_H + 20:
                    d[0] = self.rng.uniform(-40, BASE_W + 40)
                    d[1] = self.rng.uniform(-60, -10)
                if d[0] < -60:
                    d[0] = BASE_W + 40

    def draw_background_overlay(self, surf):
        # overlays that should sit above sky/buildings but below vehicles
        if self.kind == "fog":
            a = int(28 + 90 * self.intensity)
            fog = pygame.Surface((BASE_W, BASE_H), pygame.SRCALPHA)
            fog.fill((80, 78, 74, a))
            surf.blit(fog, (0, 0))
        elif self.kind == "dust_storm":
            a = int(24 + 80 * self.intensity)
            dust = pygame.Surface((BASE_W, BASE_H), pygame.SRCALPHA)
            dust.fill((96, 70, 42, a))
            surf.blit(dust, (0, 0))

    def draw_foreground(self, surf):
        # rain streaks + lightning flash (drawn above entities)
        if self.kind in ("rain", "heavy_rain", "storm"):
            for x, y, spd in self.drops:
                x2 = x - 3
                y2 = y - 10
                pygame.draw.line(surf, (180, 180, 190), (int(x), int(y)), (int(x2), int(y2)), 1)

        if self.flash_t > 0:
            flash = pygame.Surface((BASE_W, BASE_H), pygame.SRCALPHA)
            flash.fill((230, 230, 230, 80))
            surf.blit(flash, (0, 0))

# =====================================================
# MAIN GAME
# =====================================================
def main():
    pygame.init()
    expected = ensure_asset_folders()
    asset_logger = AssetLogger(PROJECT_ROOT)
    try:
        asset_logger.audit_audio_folders(expected.get('sfx', []), label='sfx')
        asset_logger.audit_audio_folders(expected.get('music', []), label='music')
    except Exception:
        pass
    audio = AudioManager(ASSETS_DIR, asset_logger=asset_logger)
    # Start road music if present
    audio.play_music('road', volume=0.65)
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
    pygame.display.set_caption("X COUNTRY — Seamless (Road + Pit Stop)")
    clock = pygame.time.Clock()
    canvas = pygame.Surface((BASE_W, BASE_H))
    font_small = load_font("fonts/ui.ttf", 9)

    while True:
        # (Re)initialize run state

        vehicle = PlayerVehicle()
        dust = DustSystem()

        strips, city_seed, city_pal = build_new_city(NUM_STRIPS, start_x=0.0)
        current_biome = strips[len(strips) // 2].biome if strips else BIOME_DESERT
        weather = WeatherSystem(seed=city_seed, biome=current_biome)

        enemies = []
        bullets = []
        particles = []
        debris = []
        player_dead = False
        player_death_timer = 0
        pitstop_fuel_total = 0

        persistent_inv = Inventory()
        persistent_hp = 100
        equipped_weapon = None

        mode = MODE_ROAD
        pit = None

        running = True
        restart = False
        while running:
            clock.tick(FPS)
            keys = pygame.key.get_pressed()
            mouse_pressed = pygame.mouse.get_pressed()
            mouse_pos = (pygame.mouse.get_pos()[0] // SCALE, pygame.mouse.get_pos()[1] // SCALE)
            # Determine current biome early each frame (used by rendering + weather + death-camera).
            current_biome = strips[len(strips) // 2].biome if strips else BIOME_DESERT

            for e in pygame.event.get():
                if e.type == pygame.QUIT:
                    running = False

            if keys[pygame.K_ESCAPE]:
                running = False

            canvas.fill((0, 0, 0))

            if mode == MODE_ROAD:
                if player_dead:
                    # Let the explosion play out before resetting.
                    player_death_timer -= 1
                    if player_death_timer <= 0:
                        restart = True
                        running = False

                    # Keep visuals updating while dead.
                    scroll = 0.0
                    for p in particles[:]:
                        p.update()
                        if p.life <= 0:
                            particles.remove(p)
                    for d in debris[:]:
                        d.update(scroll)
                        if d.life <= 0:
                            debris.remove(d)

                    # Render a frozen frame + explosion
                    draw_sky(canvas, city_pal, weather=weather)
                    for s in strips:
                        canvas.blit(s.far, (int(s.world_x * 0.6), 0))
                    for s in strips:
                        canvas.blit(s.mid, (int(s.world_x * 0.75), 0))
                    for s in strips:
                        canvas.blit(s.ground_band, (int(s.world_x), GROUND_Y))
                    draw_road(canvas, 0.0, current_biome, city_pal=city_pal)
                    for s in strips:
                        canvas.blit(s.near, (int(s.world_x * 0.9), 0))

                    for d in debris:
                        d.draw(canvas)
                    for p in particles:
                        p.draw(canvas)

                    pygame.transform.scale(canvas, (SCREEN_W, SCREEN_H), screen)
                    pygame.display.flip()
                    continue

                throttle = keys[pygame.K_d]
                # Engine audio: idle loop when not accelerating; throttle loop while accelerating.
                if audio is not None:
                    throttle_active = bool(throttle and vehicle.gas > 0 and vehicle.speed > 0.2)
                    audio.set_player_engine_state(throttle_active)
                vehicle.update(throttle)
                scroll = vehicle.speed

                for s in strips:
                    s.world_x -= scroll

                if strips and strips[0].world_x <= -STRIP_W:
                    strips.pop(0)
                    last = strips[-1]
                    nb = pick_biome(last.biome)
                    strips.append(WorldStrip(last.world_x + STRIP_W, nb))

                if random.random() < 0.015:
                    enemies.append(EnemyVehicle(BASE_W + 200))

                for en in enemies[:]:
                    en.update(scroll, bullets, particles, audio=audio)
                    if getattr(en, 'remove_me', False) or en.x < -260:
                        enemies.remove(en)

                if mouse_pressed[0]:
                    vehicle.shoot(bullets, particles, audio=audio)

                for b in bullets[:]:
                    b.update()
                    if b.life <= 0:
                        bullets.remove(b)
                        continue

                    if b.y < -20 or b.y > BASE_H + 20 or b.x < -40 or b.x > BASE_W + 240:
                        bullets.remove(b)
                        continue

                    if b.owner == "player_vehicle":
                        br = b.rect()
                        for en in enemies:
                            if (not en.disabled) and br.colliderect(en.rect()):
                                en.damage(b.dmg, particles, audio=audio, debris=debris)
                                if audio is not None:
                                    # Impact SFX (assets/sfx/road/hit_metal/*)
                                    audio.play('road/hit_metal', volume=0.85)
                                # impact sparks / tiny smoke puff
                                for _ in range(4):
                                    particles.append(Particle(b.x, b.y,
                                                              random.uniform(-1.2, 1.2),
                                                              random.uniform(-1.2, 0.6),
                                                              random.randint(10, 16),
                                                              SPARK, grow=False))
                                if random.random() < 0.35:
                                    particles.append(Particle(b.x, b.y,
                                                              random.uniform(-0.4, 0.4),
                                                              random.uniform(-0.8, -0.2),
                                                              random.randint(18, 30),
                                                              SMOKE, grow=True))
                                if b in bullets:
                                    bullets.remove(b)
                                break
                    else:
                        if abs(b.x - vehicle.x) < 22 and abs(b.y - (vehicle.y + 12)) < 14:
                            vehicle.apply_damage(b.dmg if hasattr(b, "dmg") else 2.5)

                        if vehicle.health <= 0 and not player_dead:
                            # Player death: explode into pieces + flames, then reset game
                            player_dead = True
                            player_death_timer = 110
                            if audio is not None:
                                audio.play('road/explosion', volume=0.95)
                                audio.stop_loop('engine')
                            enemies.clear()
                            bullets.clear()

                            cx = vehicle.x + 26
                            cy = vehicle.y + 18

                            cols = [vehicle.style.body, vehicle.style.steel, vehicle.style.rust]
                            for _ in range(random.randint(14, 22)):
                                w = random.randint(4, 12)
                                h = random.randint(3, 10)
                                debris.append(DebrisPiece(cx + random.uniform(-10, 10),
                                    cy + random.uniform(-8, 8),
                                    random.uniform(-3.8, 3.8),
                                    random.uniform(-3.6, -0.8),
                                    w, h,
                                    random.choice(cols),
                                    life=random.randint(80, 140)))

                            for _ in range(36):
                                particles.append(Particle(cx, cy,
                                    random.uniform(-2.9, 2.9),
                                    random.uniform(-2.9, 1.6),
                                    random.randint(18, 36),
                                    random.choice([FIRE1, FIRE2, (220, 200, 140)]),
                                    grow=True))
                            for _ in range(30):
                                particles.append(Particle(cx, cy,
                                    random.uniform(-1.6, 1.6),
                                    random.uniform(-2.0, -0.2),
                                    random.randint(30, 60),
                                    SMOKE,
                                    grow=True))

                        if b in bullets:
                            bullets.remove(b)

                for p in particles[:]:
                    p.update()
                    if p.life <= 0:
                        particles.remove(p)
                for d in debris[:]:
                    d.update(scroll)
                    if d.life <= 0:
                        debris.remove(d)


                # Vehicle damage smoke
                if vehicle.health < 40.0 and random.random() < 0.25:
                    particles.append(Particle(vehicle.x + random.randint(14, 60), vehicle.y + 14,
                                              random.uniform(-0.4, 0.2), random.uniform(-0.8, -0.2),
                                              random.randint(18, 34), SMOKE, grow=True))

                if throttle and vehicle.speed > 1.8:
                    dust.emit(vehicle.x + 6, vehicle.y + 40, n=1 + (1 if vehicle.speed > 6 else 0))

                # Weather-driven ambient dust (adds life to dust storms)
                if weather.kind == "dust_storm" and random.random() < (0.65 + 0.25 * weather.intensity):
                    dust.emit(random.randint(0, BASE_W), ROAD_Y + random.randint(6, ROAD_H - 6), n=1)

                dust.update(scroll)

                if vehicle.gas <= 0:
                    vehicle.speed = 0.0
                    enemies.clear()
                    bullets.clear()
                    particles.clear()
                    if audio is not None:
                        audio.play('road/pit_enter', volume=0.9)
                    pit = PitStopSession(base_w=BASE_W, base_h=BASE_H, persistent_inventory=persistent_inv, persistent_hp=persistent_hp,
                                       breakdown=(vehicle.gas <= 0), audio=audio)
                    mode = MODE_PIT
                    if audio is not None:
                        audio.stop_loop('engine')
                        audio.play_music('pit', volume=0.65)

                draw_sky(canvas, city_pal, weather=weather)

                for s in strips:
                    canvas.blit(s.far, (int(s.world_x * 0.25), 0))
                for s in strips:
                    canvas.blit(s.mid, (int(s.world_x * 0.5), 0))
                for s in strips:
                    canvas.blit(s.ground_band, (int(s.world_x), GROUND_Y))

                draw_road(canvas, scroll, current_biome, city_pal=city_pal)

                for s in strips:
                    canvas.blit(s.near, (int(s.world_x * 0.9), 0))

                # Per-load city color grading (background only)
                gc = city_pal.get("grade_col", (0, 0, 0))
                ga = int(city_pal.get("grade_alpha", 0))
                if ga > 0:
                    grade = pygame.Surface((BASE_W, BASE_H), pygame.SRCALPHA)
                    grade.fill((gc[0], gc[1], gc[2], ga))
                    canvas.blit(grade, (0, 0))

                # Weather overlays that sit above sky/buildings but below vehicles.
                weather.update(current_biome, scroll, in_pit=False)
                weather.draw_background_overlay(canvas)

                for en in enemies:
                    en.draw(canvas)
                vehicle.draw(canvas)

                for b in bullets:
                    b.draw(canvas)
                for d in debris:
                    d.draw(canvas)


                dust.draw(canvas)
                for p in particles:
                    p.draw(canvas)

                weather.draw_foreground(canvas)

                draw_scanlines(canvas)
                hud_weapon = equipped_weapon
                if hud_weapon is None:
                    owned = persistent_inv.owned_weapons()
                    hud_weapon = owned[0] if owned else None
                draw_hud(canvas, font_small, vehicle, pitstop_fuel_total, mode, persistent_inv, hud_weapon)

            else:
                pit.update(keys, mouse_pressed, mouse_pos)
                pit.draw(canvas)
                # Keep weather evolving while in pit; apply only ambient overlays.
                weather.update(current_biome, 0.0, in_pit=True)
                weather.draw_background_overlay(canvas)
                draw_scanlines(canvas)

                if pit.done:
                    fuel_units = persistent_inv.count("fuel")
                    if fuel_units > 0:
                        pitstop_fuel_total += fuel_units
                        vehicle.gas += fuel_units
                        persistent_inv.consume("fuel", fuel_units)


                    # Apply vehicle repairs using collected PARTS
                    if vehicle.health < vehicle.max_health:
                        parts = persistent_inv.count("parts")
                        if parts > 0:
                            repair_per_part = 8
                            missing = int(vehicle.max_health - vehicle.health)
                            max_repair = parts * repair_per_part
                            repair = min(missing, max_repair)
                            used = int(math.ceil(repair / repair_per_part))
                            if persistent_inv.consume("parts", used):
                                vehicle.health = min(vehicle.max_health, vehicle.health + used * repair_per_part)
                    persistent_hp = pit.player.hp
                    equipped_weapon = pit.player.equipped

                    # Return to road: apply pit rewards, then generate a fresh city.
                    pit = None
                    mode = MODE_ROAD
                    strips, city_seed, city_pal = build_new_city(NUM_STRIPS, start_x=0.0)
                    current_biome = strips[len(strips) // 2].biome if strips else BIOME_DESERT
                    weather.reset_for_city(city_seed, current_biome)
                    enemies.clear()
                    bullets.clear()
                    particles.clear()
                    debris.clear()
                    dust = DustSystem()
                    if audio is not None:
                        audio.play_music('road', volume=0.65)

                    if vehicle.gas <= 0:
                        vehicle.gas = 10.0

            pygame.transform.scale(canvas, (SCREEN_W, SCREEN_H), screen)
            pygame.display.flip()

        
        if restart:
            continue
        break

    pygame.quit()
    sys.exit()



# =====================================================
# DOOMSDAY TOOL-WINDOW RUNNER (external window, pause/resume via IPC)
# =====================================================

def _win32_hide_from_taskbar(make_toolwindow: bool = True):
    """Best-effort: mark this pygame window as a TOOLWINDOW so it doesn't appear on the taskbar.

    This is Windows-only. On other platforms it is a no-op.
    """
    try:
        if os.name != 'nt' or not make_toolwindow:
            return
        import ctypes
        import pygame
        info = pygame.display.get_wm_info()
        hwnd = info.get('window')
        if not hwnd:
            return
        GWL_EXSTYLE = -20
        WS_EX_TOOLWINDOW = 0x00000080
        WS_EX_APPWINDOW = 0x00040000
        user32 = ctypes.windll.user32
        get = user32.GetWindowLongW
        set_ = user32.SetWindowLongW
        style = get(hwnd, GWL_EXSTYLE)
        # Remove APPWINDOW, add TOOLWINDOW
        style = style & (~WS_EX_APPWINDOW)
        style = style | WS_EX_TOOLWINDOW
        set_(hwnd, GWL_EXSTYLE, style)
        # Force refresh
        SWP_NOMOVE = 0x0002
        SWP_NOSIZE = 0x0001
        SWP_NOZORDER = 0x0004
        SWP_FRAMECHANGED = 0x0020
        user32.SetWindowPos(hwnd, None, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED)
    except Exception:
        return


def _win32_show_window(show: bool):
    """Best-effort show/hide for Windows."""
    try:
        if os.name != 'nt':
            return False
        import ctypes
        import pygame
        info = pygame.display.get_wm_info()
        hwnd = info.get('window')
        if not hwnd:
            return False
        user32 = ctypes.windll.user32
        SW_HIDE = 0
        SW_SHOW = 5
        user32.ShowWindow(hwnd, SW_SHOW if show else SW_HIDE)
        return True
    except Exception:
        return False


class _DoomsdayToolWindowServer:
    """Runs this game in its own resizable window and listens for control commands.

    Commands (one per line): SHOW, HIDE, PAUSE, RESUME, QUIT

    ESC inside the window will PAUSE+HIDE (state preserved).
    """

    def __init__(self, port: int, start_hidden: bool = False, hide_taskbar: bool = True, title: str = 'Apocalyptic Combat'):
        self.port = int(port)
        self.start_hidden = bool(start_hidden)
        self.hide_taskbar = bool(hide_taskbar)
        self.title = str(title)

        self._paused = bool(start_hidden)
        self._hidden = bool(start_hidden)

        self._sock = None
        self._running = True

        self._embedded = None
        self._freeze = None

    def _open_socket(self):
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(('127.0.0.1', self.port))
        s.listen(4)
        s.setblocking(False)
        self._sock = s

    def _poll_commands(self):
        if self._sock is None:
            return
        import socket
        while True:
            try:
                conn, _ = self._sock.accept()
            except BlockingIOError:
                break
            except Exception:
                break
            try:
                data = b''
                conn.settimeout(0.05)
                while True:
                    chunk = conn.recv(4096)
                    if not chunk:
                        break
                    data += chunk
                    if len(data) > 64 * 1024:
                        break
                text = data.decode('utf-8', errors='ignore')
                for line in text.splitlines():
                    cmd = line.strip().upper()
                    if not cmd:
                        continue
                    self._handle_cmd(cmd)
            except Exception:
                pass
            try:
                conn.close()
            except Exception:
                pass

    def _set_paused(self, paused: bool):
        paused = bool(paused)
        if paused == self._paused:
            return
        self._paused = paused
        if paused:
            # Freeze current frame
            try:
                if self._freeze is None and pygame.display.get_surface() is not None:
                    self._freeze = pygame.display.get_surface().copy()
            except Exception:
                pass
            # Stop audio cleanly if available
            try:
                if getattr(self._embedded, 'audio', None) is not None:
                    try:
                        self._embedded.audio.stop_loop('engine')
                    except Exception:
                        pass
                    try:
                        self._embedded.audio.stop_music()
                    except Exception:
                        pass
            except Exception:
                pass
        else:
            self._freeze = None

    def _set_hidden(self, hidden: bool):
        hidden = bool(hidden)
        if hidden == self._hidden:
            return
        self._hidden = hidden
        # Best-effort hide/show
        if os.name == 'nt':
            _win32_show_window(not hidden)
        else:
            # On non-Windows platforms, iconify as a reasonable approximation.
            try:
                if hidden:
                    pygame.display.iconify()
            except Exception:
                pass

    def _handle_cmd(self, cmd: str):
        if cmd == 'QUIT':
            self._running = False
            return
        if cmd == 'PAUSE':
            self._set_paused(True)
            return
        if cmd == 'RESUME':
            self._set_paused(False)
            return
        if cmd == 'HIDE':
            self._set_hidden(True)
            return
        if cmd == 'SHOW':
            self._set_hidden(False)
            return

    def run(self):
        pygame.init()
        # Start with a sensible 16:9 window size.
        w, h = 960, 540
        flags = pygame.RESIZABLE
        screen = pygame.display.set_mode((w, h), flags)
        pygame.display.set_caption(self.title)
        _win32_hide_from_taskbar(make_toolwindow=self.hide_taskbar)

        # Socket server for control
        self._open_socket()

        # Create embedded runner (uses this file's assets relative to __file__).
        self._embedded = EmbeddedXCountry(screen)

        # Apply initial hidden/paused state
        if self.start_hidden:
            self._set_paused(True)
            self._set_hidden(True)

        clock = pygame.time.Clock()
        pending_events = []
        while self._running:
            dt = clock.tick(60) / 1000.0
            pending_events.clear()

            for ev in pygame.event.get():
                pending_events.append(ev)

                if ev.type == pygame.QUIT:
                    # Treat OS-close as full quit.
                    self._running = False

                elif ev.type == pygame.VIDEORESIZE:
                    # Recreate display surface on resize and update embedded output sizing.
                    try:
                        screen = pygame.display.set_mode((max(240, ev.w), max(180, ev.h)), flags)
                        self._embedded.external_surface = screen
                        self._embedded.out_w, self._embedded.out_h = screen.get_size()
                    except Exception:
                        pass

                elif ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
                    # ESC pauses + hides, but keeps the process and state alive.
                    self._set_paused(True)
                    self._set_hidden(True)

            # IPC commands
            self._poll_commands()

            # If paused, keep the last frame visible (or redraw freeze if needed).
            if self._paused:
                if self._freeze is not None and pygame.display.get_surface() is not None:
                    try:
                        pygame.display.get_surface().blit(self._freeze, (0, 0))
                        pygame.display.flip()
                    except Exception:
                        pass
                continue

            # If hidden (but not paused), still pause to avoid background CPU.
            if self._hidden:
                self._set_paused(True)
                continue

            # Advance one frame.
            try:
                self._embedded.step(dt, pending_events, allow_escape_exit=False)
            except Exception:
                # Never crash the process on a bad frame; pause so the launcher can recover.
                self._set_paused(True)

            try:
                pygame.display.flip()
            except Exception:
                pass

        # Cleanup
        try:
            if self._sock is not None:
                self._sock.close()
        except Exception:
            pass
        try:
            pygame.quit()
        except Exception:
            pass


def _maybe_run_as_toolwindow():
    """Entry point for Doomsday: run as an IPC-controlled tool window."""
    try:
        import argparse
        p = argparse.ArgumentParser(add_help=False)
        p.add_argument('--doomsday-toolwindow', action='store_true')
        p.add_argument('--port', type=int, default=0)
        p.add_argument('--start-hidden', type=int, default=0)
        p.add_argument('--hide-taskbar', type=int, default=1)
        p.add_argument('--title', type=str, default='Apocalyptic Combat')
        args, _ = p.parse_known_args()
        if not args.doomsday_toolwindow:
            return False
        if not args.port:
            # Without a port we cannot be controlled; fall back to standalone main.
            return False
        srv = _DoomsdayToolWindowServer(
            port=args.port,
            start_hidden=bool(args.start_hidden),
            hide_taskbar=bool(args.hide_taskbar),
            title=args.title,
        )
        srv.run()
        return True
    except Exception:
        return False


# =====================================================
# EMBEDDED MODE (for Doomsday launcher)
# =====================================================

class EmbeddedXCountry:
    """Step-driven wrapper so this game can run inside another Pygame UI.

    The hub provides an external surface (viewport) and calls:
      - handle_event(ev) for input
      - step(dt) each frame

    This wrapper keeps the original standalone main() untouched.
    """

    def __init__(self, external_surface):
        if external_surface is None:
            raise ValueError('external_surface is required')
        # Init pygame (does not create a new window; hub owns the display).
        if not pygame.get_init():
            pygame.init()

        self.external_surface = external_surface
        self.out_w, self.out_h = external_surface.get_size()

        # Input tracking (hub should provide events with local coords).
        self._mouse_pos = (BASE_W // 2, BASE_H // 2)
        self._mouse_buttons = [False, False, False]
        self._quit = False

        # Assets + audio
        expected = ensure_asset_folders()
        asset_logger = AssetLogger(PROJECT_ROOT)
        try:
            asset_logger.audit_audio_folders(expected.get('sfx', []), label='sfx')
            asset_logger.audit_audio_folders(expected.get('music', []), label='music')
        except Exception:
            pass

        self.audio = AudioManager(ASSETS_DIR, asset_logger=asset_logger)
        try:
            self.audio.play_music('road', volume=0.65)
        except Exception:
            pass

        self.canvas = pygame.Surface((BASE_W, BASE_H))
        self.font_small = load_font("fonts/ui.ttf", 9)
        self.clock = pygame.time.Clock()

        self._reset_run_state()

    def _reset_run_state(self):
        # Mirrors the '(Re)initialize run state' section in main().
        self.vehicle = PlayerVehicle()
        self.dust = DustSystem()

        self.strips, self.city_seed, self.city_pal = build_new_city(NUM_STRIPS, start_x=0.0)
        self.current_biome = self.strips[len(self.strips)//2].biome if self.strips else BIOME_DESERT
        self.weather = WeatherSystem(seed=self.city_seed, biome=self.current_biome)

        self.enemies = []
        self.bullets = []
        self.particles = []
        self.debris = []

        self.player_dead = False
        self.player_death_timer = 0
        self.pitstop_fuel_total = 0

        self.persistent_inv = Inventory()
        self.persistent_hp = 100
        self.equipped_weapon = None

        self.mode = MODE_ROAD
        self.pit = None

    def handle_event(self, ev):
        # Track mouse state in BASE coords. Hub is expected to send local event.pos.
        try:
            if ev.type == pygame.MOUSEMOTION:
                x, y = ev.pos
                self._mouse_pos = (int(x) // max(1, SCALE), int(y) // max(1, SCALE))
            elif ev.type == pygame.MOUSEBUTTONDOWN:
                if ev.button == 1:
                    self._mouse_buttons[0] = True
                elif ev.button == 2:
                    self._mouse_buttons[1] = True
                elif ev.button == 3:
                    self._mouse_buttons[2] = True
            elif ev.type == pygame.MOUSEBUTTONUP:
                if ev.button == 1:
                    self._mouse_buttons[0] = False
                elif ev.button == 2:
                    self._mouse_buttons[1] = False
                elif ev.button == 3:
                    self._mouse_buttons[2] = False
            elif ev.type == pygame.QUIT:
                self._quit = True
        except Exception:
            pass

    def step(self, dt, events=None, allow_escape_exit=True):
        """Advance the simulation by dt seconds. Returns False when it should close."""
        if self._quit:
            return False
        if events:
            for ev in events:
                self.handle_event(ev)

        # Escape in embedded mode normally returns to hub (hub interprets False as exit-to-menu).
        # For external-window tool mode, we disable escape-exit and let the host handle ESC explicitly.
        keys = pygame.key.get_pressed()
        if allow_escape_exit and keys[pygame.K_ESCAPE]:
            return False

        mouse_pressed = tuple(bool(x) for x in self._mouse_buttons)
        mouse_pos = self._mouse_pos

        self.canvas.fill((0, 0, 0))

        # Keep biome updated (used by weather + palette).
        try:
            self.current_biome = self.strips[len(self.strips)//2].biome if self.strips else BIOME_DESERT
        except Exception:
            self.current_biome = BIOME_DESERT

        # --- ROAD MODE ---
        if self.mode == MODE_ROAD:
            if self.player_dead:
                self.player_death_timer -= 1
                if self.player_death_timer <= 0:
                    # Restart run
                    self._reset_run_state()
                    return True

                scroll = 0.0
                for p in self.particles[:]:
                    p.update()
                    if p.life <= 0:
                        self.particles.remove(p)
                for d in self.debris[:]:
                    d.update(scroll)
                    if d.life <= 0:
                        self.debris.remove(d)

                # Render frozen frame
                draw_sky(self.canvas, self.city_pal, weather=self.weather)
                for s in self.strips:
                    self.canvas.blit(s.far, (int(s.world_x * 0.6), 0))
                for s in self.strips:
                    self.canvas.blit(s.mid, (int(s.world_x * 0.75), 0))
                for s in self.strips:
                    self.canvas.blit(s.ground_band, (int(s.world_x), GROUND_Y))
                draw_road(self.canvas, 0.0, self.current_biome, city_pal=self.city_pal)
                for s in self.strips:
                    self.canvas.blit(s.near, (int(s.world_x * 0.9), 0))
                for d in self.debris:
                    d.draw(self.canvas)
                for p in self.particles:
                    p.draw(self.canvas)

                # Present
                pygame.transform.scale(self.canvas, (self.out_w, self.out_h), self.external_surface)
                return True

            throttle = bool(keys[pygame.K_d])
            if self.audio is not None:
                throttle_active = bool(throttle and self.vehicle.gas > 0 and self.vehicle.speed > 0.2)
                self.audio.set_player_engine_state(throttle_active)

            self.vehicle.update(throttle)
            scroll = float(self.vehicle.speed)

            for s in self.strips:
                s.world_x -= scroll

            if self.strips and self.strips[0].world_x <= -STRIP_W:
                self.strips.pop(0)
                last = self.strips[-1]
                nb = pick_biome(last.biome)
                self.strips.append(WorldStrip(last.world_x + STRIP_W, nb))

            if random.random() < 0.015:
                self.enemies.append(EnemyVehicle(BASE_W + 200))

            for en in self.enemies[:]:
                en.update(scroll, self.bullets, self.particles, audio=self.audio)
                if getattr(en, 'remove_me', False) or en.x < -260:
                    self.enemies.remove(en)

            if mouse_pressed[0]:
                self.vehicle.shoot(self.bullets, self.particles, audio=self.audio)

            # update bullets + collisions (simplified; keeps original feel)
            for b in self.bullets[:]:
                b.update()
                if b.life <= 0:
                    self.bullets.remove(b)
                    continue
                if b.y < -20 or b.y > BASE_H + 20 or b.x < -40 or b.x > BASE_W + 240:
                    self.bullets.remove(b)
                    continue

                if b.owner == 'player_vehicle':
                    br = b.rect()
                    for en in self.enemies:
                        if (not en.disabled) and br.colliderect(en.rect()):
                            en.damage(getattr(b, 'dmg', 2.5), self.particles, audio=self.audio, debris=self.debris)
                            if self.audio is not None:
                                self.audio.play('road/hit_metal', volume=0.85)
                            if b in self.bullets:
                                self.bullets.remove(b)
                            break
                else:
                    # enemy bullet hits
                    if abs(b.x - self.vehicle.x) < 22 and abs(b.y - (self.vehicle.y + 12)) < 14:
                        try:
                            self.vehicle.apply_damage(getattr(b, 'dmg', 2.5))
                        except Exception:
                            pass
                        if b in self.bullets:
                            self.bullets.remove(b)

                    if getattr(self.vehicle, 'health', 1) <= 0 and not self.player_dead:
                        self.player_dead = True
                        self.player_death_timer = 110
                        try:
                            if self.audio is not None:
                                self.audio.play('road/explosion', volume=0.95)
                                self.audio.stop_loop('engine')
                        except Exception:
                            pass
                        self.enemies.clear()
                        self.bullets.clear()

            # Enter pit stop when gas hits 0
            if self.vehicle.gas <= 0 and self.mode == MODE_ROAD:
                self.mode = MODE_PIT
                try:
                    self.audio.stop_loop('engine')
                    self.audio.play_music('pit', volume=0.65)
                except Exception:
                    pass
                self.pit = PitStopSession(base_w=BASE_W, base_h=BASE_H, seed_base=random.randint(0, 2**31-1),
                                         persistent_inventory=self.persistent_inv, persistent_hp=self.persistent_hp,
                                         breakdown=False, audio=self.audio)

            # Render road scene
            draw_sky(self.canvas, self.city_pal, weather=self.weather)
            for s in self.strips:
                self.canvas.blit(s.far, (int(s.world_x * 0.6), 0))
            for s in self.strips:
                self.canvas.blit(s.mid, (int(s.world_x * 0.75), 0))
            for s in self.strips:
                self.canvas.blit(s.ground_band, (int(s.world_x), GROUND_Y))

            draw_road(self.canvas, scroll, self.current_biome, city_pal=self.city_pal)
            for s in self.strips:
                self.canvas.blit(s.near, (int(s.world_x * 0.9), 0))

            for en in self.enemies:
                en.draw(self.canvas)
            for b in self.bullets:
                b.draw(self.canvas)

            self.vehicle.draw(self.canvas)

            for d in self.debris:
                d.draw(self.canvas)
            for p in self.particles:
                p.draw(self.canvas)

            try:
                draw_hud(self.canvas, self.font_small, self.vehicle, self.pitstop_fuel_total, self.mode, self.persistent_inv, self.equipped_weapon)
            except Exception:
                pass

        # --- PIT MODE ---
        elif self.mode == MODE_PIT and self.pit is not None:
            # Update pit stop session
            self.pit.update(keys, mouse_pressed, mouse_pos)
            try:
                self.pit.draw(self.canvas, self.font_small)
            except Exception:
                # Some builds implement draw without font args
                try:
                    self.pit.draw(self.canvas)
                except Exception:
                    pass

            if getattr(self.pit, 'done', False):
                # Transfer collected fuel back to vehicle
                try:
                    gained = int(getattr(self.pit, 'fuel_gained', 0))
                    self.pitstop_fuel_total += gained
                    self.vehicle.gas += gained
                except Exception:
                    pass
                try:
                    self.persistent_hp = int(getattr(self.pit.player, 'hp', self.persistent_hp))
                except Exception:
                    pass

                self.mode = MODE_ROAD
                self.pit = None
                try:
                    self.audio.play_music('road', volume=0.65)
                except Exception:
                    pass

        # Present
        pygame.transform.scale(self.canvas, (self.out_w, self.out_h), self.external_surface)
        return True


def create_embedded(external_surface, viewport_rect=None):
    """Factory used by the Doomsday launcher."""
    return EmbeddedXCountry(external_surface)



if __name__ == "__main__":
    if not _maybe_run_as_toolwindow():
        main()
