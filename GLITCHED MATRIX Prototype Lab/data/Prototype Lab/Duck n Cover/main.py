import pygame
import random
import math
import os
import sys

# ================== CONFIG ==================
WIDTH, HEIGHT = 1280, 720
FPS = 60
SCROLL_SPEED = 3
GRAVITY = 0.45

BOMB_COOLDOWN_MS = 140

MAX_DUCKS = 7
KILLS_PER_DUCK = 10

ZOOM_MIN = 1.0
ZOOM_MAX = 3.0
ZOOM_STEP = 1.0

# Windmills: random, but not too constant.
# Spawn delay is re-rolled after each spawn.
WINDMILL_MIN_MS = 45_000
WINDMILL_MAX_MS = 110_000

# ================== SHIPPING-SAFE PATHS ==================
def app_base_dir() -> str:
    # PyInstaller sets sys._MEIPASS for bundled app data.
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return sys._MEIPASS  # type: ignore[attr-defined]
    return os.path.dirname(os.path.abspath(__file__))

def writable_dir() -> str:
    # For dev: same folder as script
    # For packaged: current working directory (where user runs the .exe)
    if getattr(sys, "frozen", False):
        return os.getcwd()
    return os.path.dirname(os.path.abspath(__file__))

APP_DIR = app_base_dir()
OUT_DIR = writable_dir()

ASSETS_DIR = os.path.join(APP_DIR, "assets")

SFX_DIR = os.path.join(ASSETS_DIR, "sfx")
SFX_EXPLOSION_DIR = os.path.join(SFX_DIR, "explosion")
SFX_QUACK_DIR = os.path.join(SFX_DIR, "quack")
SFX_PEOPLE_HIT_DIR = os.path.join(SFX_DIR, "people_hit")
SFX_BUILDING_HIT_DIR = os.path.join(SFX_DIR, "building_hit")
SFX_DUCK_FLY_DIR = os.path.join(SFX_DIR, "duck_fly")
SFX_INSECT_EAT_DIR = os.path.join(SFX_DIR, "insect_eat")  # NEW

MUSIC_DIR = os.path.join(ASSETS_DIR, "music")

README_PATH = os.path.join(OUT_DIR, "README.txt")
SUPPORTED_AUDIO_EXT = (".wav", ".ogg", ".mp3")

def ensure_asset_folders_dev_only():
    """
    Only create folders when running from source.
    In a packaged build, assets are shipped inside the dist folder already.
    """
    if getattr(sys, "frozen", False):
        return
    os.makedirs(SFX_EXPLOSION_DIR, exist_ok=True)
    os.makedirs(SFX_QUACK_DIR, exist_ok=True)
    os.makedirs(SFX_PEOPLE_HIT_DIR, exist_ok=True)
    os.makedirs(SFX_BUILDING_HIT_DIR, exist_ok=True)
    os.makedirs(SFX_DUCK_FLY_DIR, exist_ok=True)
    os.makedirs(SFX_INSECT_EAT_DIR, exist_ok=True)
    os.makedirs(MUSIC_DIR, exist_ok=True)

def ensure_readme():
    if os.path.exists(README_PATH):
        return
    txt = """Duck & Cover (Pygame)

Goal:
- Fly as a flock and drop bombs.
- Avoid windmills (propellers kill ducks).
- Eat insects to gain ammo (+1 per insect).

Controls:
- Mouse: move the flock (lead duck follows mouse; others in formation)
- Left Click or Space: drop bomb (uses 1 ammo)
- Z: zoom in (1x -> 2x -> 3x)
- X: zoom out (3x -> 2x -> 1x)
- C: camera mode toggle (zoom anchored to center vs anchored to lead duck)
- F: fullscreen toggle
- P: pause/unpause (cursor visible when paused)
- Esc: quit

Audio / Assets:
Drop your sound files into these folders (wav/ogg recommended; mp3 depends on SDL_mixer):
- assets/sfx/quack/           (drop-bomb button)
- assets/sfx/explosion/       (bomb explosion)
- assets/sfx/people_hit/      (human hit)
- assets/sfx/building_hit/    (structure destroyed)
- assets/sfx/duck_fly/        (looped wing/flying; first file is looped)
- assets/sfx/insect_eat/      (plays when eating an insect)
- assets/music/               (optional ambience/music; first file loops)

Windmills:
- Spawn at randomized intervals (not constant).
"""
    try:
        with open(README_PATH, "w", encoding="utf-8") as f:
            f.write(txt)
    except Exception:
        pass

def safe_mixer_init():
    try:
        pygame.mixer.pre_init(44100, -16, 2, 512)
        pygame.mixer.init()
        return True
    except Exception:
        return False

def load_sfx(folder):
    sounds = []
    try:
        if not os.path.isdir(folder):
            return sounds
        for fn in os.listdir(folder):
            if fn.lower().endswith(SUPPORTED_AUDIO_EXT):
                path = os.path.join(folder, fn)
                try:
                    sounds.append(pygame.mixer.Sound(path))
                except Exception:
                    pass
    except Exception:
        pass
    return sounds

def play_random(sounds, volume=0.8):
    if sounds:
        s = random.choice(sounds)
        try:
            s.set_volume(volume)
        except Exception:
            pass
        try:
            s.play()
        except Exception:
            pass

def load_music_playlist(folder):
    tracks = []
    try:
        if not os.path.isdir(folder):
            return tracks
        for fn in os.listdir(folder):
            if fn.lower().endswith(SUPPORTED_AUDIO_EXT):
                tracks.append(os.path.join(folder, fn))
    except Exception:
        pass
    random.shuffle(tracks)
    return tracks

def start_looped_music(tracks, mixer_ok):
    if not mixer_ok or not tracks:
        return
    try:
        pygame.mixer.music.load(tracks[0])
        pygame.mixer.music.set_volume(0.6)
        pygame.mixer.music.play(-1)
    except Exception:
        pass

# ================== INIT ==================
pygame.init()
ensure_asset_folders_dev_only()
ensure_readme()
mixer_ok = safe_mixer_init()

# smoother presentation: try vsync; fallback if unsupported
window_flags = 0
try:
    screen = pygame.display.set_mode((WIDTH, HEIGHT), window_flags, vsync=1)
except TypeError:
    screen = pygame.display.set_mode((WIDTH, HEIGHT), window_flags)

pygame.display.set_caption("Duck & Cover")
clock = pygame.time.Clock()

sfx_explosions = load_sfx(SFX_EXPLOSION_DIR) if mixer_ok else []
sfx_quacks = load_sfx(SFX_QUACK_DIR) if mixer_ok else []
sfx_people_hit = load_sfx(SFX_PEOPLE_HIT_DIR) if mixer_ok else []
sfx_building_hit = load_sfx(SFX_BUILDING_HIT_DIR) if mixer_ok else []
sfx_duck_fly = load_sfx(SFX_DUCK_FLY_DIR) if mixer_ok else []
sfx_insect_eat = load_sfx(SFX_INSECT_EAT_DIR) if mixer_ok else []

music_tracks = load_music_playlist(MUSIC_DIR)
start_looped_music(music_tracks, mixer_ok)

duck_fly_channel = None
duck_fly_sound = sfx_duck_fly[0] if sfx_duck_fly else None
if mixer_ok and duck_fly_sound:
    try:
        duck_fly_channel = pygame.mixer.Channel(2)
        duck_fly_channel.set_volume(0.35)
        duck_fly_channel.play(duck_fly_sound, loops=-1)
    except Exception:
        duck_fly_channel = None

# ================== COLORS ==================
SKY = (120, 190, 255)
BLACK = (20, 20, 20)
WHITE = (245, 245, 245)

GROUND = (70, 170, 80)
GROUND_DARK = (40, 130, 60)

DUCK_GREEN = (30, 160, 90)
DUCK_BODY = (200, 200, 200)
DUCK_CHEST = (130, 80, 40)
DUCK_BILL = (235, 200, 80)
FOOT_ORANGE = (220, 130, 60)

RED = (220, 60, 60)
DARK_RED = (140, 10, 10)
ORANGE = (255, 170, 40)

BUILDING_WALL = (155, 145, 140)
BUILDING_DARK = (105, 95, 90)
WINDOW = (190, 230, 255)
RUBBLE_LIGHT = (200, 195, 190)
RUBBLE_DARK = (120, 110, 105)

WOOD_LIGHT = (165, 120, 70)
WOOD_DARK = (95, 70, 40)

TREE_TRUNK = (120, 80, 45)
TREE_LEAF1 = (40, 140, 70)
TREE_LEAF2 = (55, 170, 85)

INSECT = (20, 20, 20)

font = pygame.font.SysFont("consolas", 20)

def clamp(v, lo, hi):
    return max(lo, min(hi, v))

GROUND_TOP_Y = HEIGHT - 100

# ================== CURSOR / PAUSE ==================
paused = False
pygame.mouse.set_visible(False)

def apply_cursor_visibility():
    pygame.mouse.set_visible(paused)

def set_fly_sound_paused(pause_it: bool):
    if not mixer_ok or duck_fly_channel is None:
        return
    try:
        if pause_it:
            duck_fly_channel.pause()
        else:
            duck_fly_channel.unpause()
    except Exception:
        pass

# ================== ZOOM / CAMERA ==================
zoom = 1.0
camera_mode = 0  # 0 center, 1 lead duck

def get_zoom_center(lead_duck):
    if camera_mode == 1 and lead_duck is not None:
        return (int(lead_duck.x), int(lead_duck.y))
    return (WIDTH // 2, HEIGHT // 2)

# ================== CLOUDS ==================
class Cloud:
    def __init__(self, x=None):
        self.x = float(x if x is not None else random.randint(0, WIDTH))
        self.y = random.randint(30, 220)
        self.w = random.randint(60, 160)
        self.h = random.randint(22, 52)
        self.speed = random.uniform(0.15, 0.45)
        self.puffs = []
        for _ in range(random.randint(4, 7)):
            self.puffs.append((random.randint(0, self.w), random.randint(0, self.h), random.randint(10, 22)))

    def update(self):
        self.x -= self.speed
        if self.x + self.w < -200:
            self.x = WIDTH + random.randint(0, 300)
            self.y = random.randint(30, 220)

    def draw(self, surf):
        base = (245, 245, 250)
        shade = (225, 225, 235)
        ox = int(self.x)
        oy = int(self.y)
        for (px, py, pr) in self.puffs:
            pygame.draw.circle(surf, base, (ox + px, oy + py), pr)
        pygame.draw.ellipse(surf, shade, (ox + 10, oy + self.h // 2, self.w - 20, self.h // 2))

# ================== ENTITIES ==================
class Duck:
    def __init__(self):
        self.x = WIDTH // 3
        self.y = HEIGHT // 3
        self.flap = 0
        self.flap_timer = 0
        self.feet_x = int(self.x) + 1
        self.feet_y = int(self.y) + 6
        self.alive = True

    def update(self, tx, ty):
        self.x += (tx - self.x) * 0.12
        self.y += (ty - self.y) * 0.12
        self.y = clamp(self.y, 40, HEIGHT - 180)
        self.flap_timer += 1
        if self.flap_timer >= 8:
            self.flap = 1 - self.flap
            self.flap_timer = 0

    def draw(self, surf):
        if not self.alive:
            return
        x = int(self.x)
        y = int(self.y)
        pygame.draw.rect(surf, DUCK_BODY, (x - 4, y, 10, 5))
        pygame.draw.rect(surf, DUCK_CHEST, (x - 2, y + 2, 4, 3))
        pygame.draw.rect(surf, DUCK_GREEN, (x + 6, y - 3, 4, 4))
        pygame.draw.rect(surf, DUCK_BILL, (x + 10, y - 2, 2, 2))
        pygame.draw.rect(surf, BLACK, (x + 7, y - 2, 1, 1))
        if self.flap == 0:
            pygame.draw.rect(surf, (180, 180, 180), (x - 6, y - 1, 5, 2))
        else:
            pygame.draw.rect(surf, (180, 180, 180), (x - 5, y - 3, 5, 2))
        self.feet_x = x + 1
        self.feet_y = y + 6
        pygame.draw.rect(surf, FOOT_ORANGE, (self.feet_x, self.feet_y, 2, 1))

    def rect(self):
        return pygame.Rect(int(self.x) - 10, int(self.y) - 8, 26, 18)

class Bomb:
    def __init__(self, x, y):
        self.x = float(x)
        self.y = float(y)
        self.vy = 0.0

    def update(self):
        self.vy += GRAVITY
        self.y += self.vy

    def draw(self, surf):
        pygame.draw.circle(surf, WHITE, (int(self.x), int(self.y)), 4)

class WorldDebris:
    def __init__(self, x, y, col, drag=0.0):
        self.x = float(x)
        self.y = float(y)
        ang = random.uniform(0, math.tau)
        spd = random.uniform(1.5, 7.5)
        self.vx = math.cos(ang) * spd
        self.vy = math.sin(ang) * spd - random.uniform(2.0, 6.0)
        self.col = col
        self.sz = random.randint(1, 3)
        self.bounced = False
        self.drag = drag

    def update(self):
        self.x -= SCROLL_SPEED
        self.vy += 0.25
        self.x += self.vx
        self.y += self.vy
        self.vx *= (1.0 - self.drag)
        if self.y >= GROUND_TOP_Y - 2 and not self.bounced:
            self.y = GROUND_TOP_Y - 2
            self.vy *= -0.35
            self.vx *= 0.6
            self.bounced = True

    def offscreen_left(self):
        return self.x < -160 or self.y > HEIGHT + 120

    def draw(self, surf):
        pygame.draw.rect(surf, self.col, (int(self.x), int(self.y), self.sz, self.sz))

class SmokePuff:
    def __init__(self, x, y):
        self.x = float(x)
        self.y = float(y)
        self.r = random.randint(6, 14)
        self.vx = random.uniform(-0.25, 0.25)
        self.vy = random.uniform(-0.6, -0.2)
        self.life = random.randint(80, 160)
        self.shade = random.randint(90, 160)

    def update(self):
        self.x -= SCROLL_SPEED * 0.8
        self.x += self.vx
        self.y += self.vy
        self.r += 0.05
        self.life -= 1

    def offscreen_left(self):
        return self.life <= 0 or self.x + self.r < -160

    def draw(self, surf):
        c = (self.shade, self.shade, self.shade)
        pygame.draw.circle(surf, c, (int(self.x), int(self.y)), int(self.r), 0)

class Flame:
    def __init__(self, x, y):
        self.x = float(x)
        self.y = float(y)
        self.t = random.random() * 6.28
        self.life = random.randint(120, 220)

    def update(self):
        self.x -= SCROLL_SPEED
        self.t += 0.35
        self.life -= 1

    def offscreen_left(self):
        return self.life <= 0 or self.x < -160

    def draw(self, surf):
        x = int(self.x)
        y = int(self.y)
        flick = int(math.sin(self.t) * 2)
        h = 10 + flick
        pygame.draw.rect(surf, ORANGE, (x, y - h, 3, h))
        pygame.draw.rect(surf, RED, (x + 1, y - h - 3, 1, 3))

class Splat:
    def __init__(self, x, y):
        self.pixels = []
        for _ in range(random.randint(16, 28)):
            px = int(x) + random.randint(-10, 10)
            py = int(y) + random.randint(-3, 6)
            sz = random.randint(1, 2)
            col = RED if random.random() < 0.7 else DARK_RED
            self.pixels.append([px, py, sz, col])

    def update(self):
        for p in self.pixels:
            p[0] -= SCROLL_SPEED

    def offscreen_left(self):
        return max(p[0] for p in self.pixels) < -120

    def draw(self, surf):
        for (px, py, sz, col) in self.pixels:
            pygame.draw.rect(surf, col, (px, py, sz, sz))

def random_shirt_color():
    palette = [
        (60, 120, 220), (220, 120, 60), (140, 200, 90),
        (200, 60, 120), (170, 140, 220), (240, 210, 90),
        (90, 200, 200), (220, 80, 80)
    ]
    return random.choice(palette)

class Person:
    def __init__(self, x):
        self.x = float(x)
        self.feet_y = GROUND_TOP_Y
        self.dead = False
        self.panic = False
        self.dir = -1
        self.run_factor = random.uniform(0.45, 0.75)
        self.anim = random.random() * 6
        self.shirt = random_shirt_color()
        self.pants = (random.randint(40, 90), random.randint(40, 90), random.randint(40, 90))
        self.skin = (230, 200, 180)

    def update(self):
        if self.dead:
            return
        self.anim += 0.30
        self.x -= SCROLL_SPEED
        if self.panic:
            run = SCROLL_SPEED * self.run_factor
            self.x += self.dir * run

    def draw(self, surf):
        if self.dead:
            return
        x = int(self.x)
        y = int(self.feet_y)
        leg = int(math.sin(self.anim) * 2)
        pygame.draw.rect(surf, self.shirt, (x - 3, y - 24, 6, 10))
        pygame.draw.rect(surf, self.pants, (x - 3, y - 14, 6, 4))
        pygame.draw.rect(surf, self.skin, (x - 2, y - 28, 4, 4))
        pygame.draw.line(surf, BLACK, (x - 1, y - 10), (x - 1 - leg, y), 2)
        pygame.draw.line(surf, BLACK, (x + 1, y - 10), (x + 1 + leg, y), 2)

class Explosion:
    def __init__(self, x, y):
        self.x = float(x)
        self.y = float(y)
        self.r = 6
        self.life = 22

    def update(self):
        self.r += 4
        self.life -= 1

    def draw(self, surf):
        if self.life > 0:
            pygame.draw.circle(surf, ORANGE, (int(self.x), int(self.y)), self.r, 2)
            pygame.draw.circle(surf, RED, (int(self.x), int(self.y)), self.r // 2, 1)

class Structure:
    def update(self):
        self.x -= SCROLL_SPEED

    def offscreen_left(self):
        return self.x + self.w < -260

class Building(Structure):
    def __init__(self, x, w, h):
        self.x = float(x)
        self.w = int(w)
        self.h = int(h)
        self.y = GROUND_TOP_Y - self.h
        self.win = []
        cols = max(2, self.w // 30)
        rows = max(2, self.h // 30)
        for r in range(rows):
            for c in range(cols):
                if random.random() < 0.75:
                    wx = 6 + c * (self.w - 12) / cols
                    wy = 6 + r * (self.h - 12) / rows
                    self.win.append((int(wx), int(wy)))

    def draw(self, surf):
        x = int(self.x)
        pygame.draw.rect(surf, BUILDING_WALL, (x, self.y, self.w, self.h))
        pygame.draw.rect(surf, BUILDING_DARK, (x, self.y, self.w, self.h), 2)
        for (wx, wy) in self.win:
            pygame.draw.rect(surf, WINDOW, (x + wx, self.y + wy, 10, 14))
            pygame.draw.rect(surf, BUILDING_DARK, (x + wx, self.y + wy, 10, 14), 1)

    def hit_by_explosion(self, ex_x, ex_r):
        cx = self.x + self.w * 0.5
        cy = self.y + self.h * 0.5
        dx = (cx - ex_x)
        dy = (cy - (GROUND_TOP_Y - 5))
        return (dx*dx + dy*dy) < (ex_r * ex_r)

class Shack(Structure):
    def __init__(self, x):
        self.w = random.randint(70, 130)
        self.h = random.randint(55, 95)
        self.x = float(x)
        self.y = GROUND_TOP_Y - self.h
        self.wood = (140 + random.randint(-20, 20), 100 + random.randint(-15, 15), 60 + random.randint(-10, 10))

    def draw(self, surf):
        x = int(self.x)
        pygame.draw.rect(surf, self.wood, (x, self.y, self.w, self.h))
        pygame.draw.rect(surf, (80, 50, 25), (x, self.y, self.w, self.h), 2)
        pygame.draw.polygon(surf, (90, 60, 30), [(x - 6, self.y), (x + self.w//2, self.y - 18), (x + self.w + 6, self.y)])
        pygame.draw.rect(surf, (60, 40, 20), (x + self.w//2 - 8, self.y + self.h - 22, 16, 22))

    def hit_by_explosion(self, ex_x, ex_r):
        cx = self.x + self.w * 0.5
        return abs(cx - ex_x) < ex_r * 0.9

class Tower(Structure):
    def __init__(self, x):
        self.w = 26
        self.h = random.randint(120, 240)
        self.x = float(x)
        self.y = GROUND_TOP_Y - self.h

    def draw(self, surf):
        x = int(self.x)
        pygame.draw.rect(surf, (120, 120, 130), (x + 11, self.y, 4, self.h))
        pygame.draw.line(surf, (80, 80, 90), (x, GROUND_TOP_Y), (x + 13, self.y), 2)
        pygame.draw.line(surf, (80, 80, 90), (x + 26, GROUND_TOP_Y), (x + 13, self.y), 2)
        pygame.draw.rect(surf, (170, 60, 60), (x + 10, self.y - 10, 6, 10))

    def hit_by_explosion(self, ex_x, ex_r):
        cx = self.x + self.w * 0.5
        return abs(cx - ex_x) < ex_r * 0.6

class Fence(Structure):
    def __init__(self, x):
        self.w = random.randint(90, 180)
        self.h = 26
        self.x = float(x)
        self.y = GROUND_TOP_Y - self.h

    def draw(self, surf):
        x = int(self.x)
        y = int(self.y)
        for px in range(0, self.w + 1, 24):
            pygame.draw.rect(surf, WOOD_DARK, (x + px, y, 6, self.h))
        pygame.draw.rect(surf, WOOD_LIGHT, (x, y + 6, self.w, 4))
        pygame.draw.rect(surf, WOOD_LIGHT, (x, y + 16, self.w, 4))
        pygame.draw.rect(surf, (70, 45, 20), (x, y, self.w, self.h), 1)

    def hit_by_explosion(self, ex_x, ex_r):
        cx = self.x + self.w * 0.5
        return abs(cx - ex_x) < ex_r

class Tree(Structure):
    def __init__(self, x):
        self.x = float(x)
        self.h = random.randint(40, 85)
        self.crown = random.randint(22, 36)
        self.w = 90

    def draw(self, surf):
        x = int(self.x)
        base_y = GROUND_TOP_Y
        pygame.draw.rect(surf, TREE_TRUNK, (x - 4, base_y - self.h, 8, self.h))
        pygame.draw.rect(surf, (70, 45, 20), (x - 4, base_y - self.h, 8, self.h), 1)
        cy = base_y - self.h
        pygame.draw.circle(surf, TREE_LEAF1, (x, cy), self.crown)
        pygame.draw.circle(surf, TREE_LEAF2, (x - 14, cy + 8), self.crown - 6)
        pygame.draw.circle(surf, TREE_LEAF2, (x + 14, cy + 8), self.crown - 6)
        pygame.draw.circle(surf, (25, 80, 40), (x, cy), self.crown, 2)

    def hit_by_explosion(self, ex_x, ex_r):
        return abs(self.x - ex_x) < ex_r * 0.8

class Windmill:
    def __init__(self, x):
        self.x = float(x)
        self.base_y = GROUND_TOP_Y
        self.h = random.randint(160, 240)
        self.w = 120
        self.y = self.base_y - self.h
        self.cx = self.x + self.w * 0.5
        self.cy = self.y + 45
        self.radius = random.randint(34, 48)
        self.angle = random.random() * math.tau
        self.spin = random.uniform(0.12, 0.20)

    def update(self):
        self.x -= SCROLL_SPEED
        self.cx = self.x + self.w * 0.5
        self.cy = self.y + 45
        self.angle += self.spin

    def offscreen_left(self):
        return self.x + self.w < -260

    def draw(self, surf):
        x = int(self.x)
        y = int(self.y)
        pygame.draw.polygon(
            surf, (210, 210, 215),
            [(x + 50, self.base_y), (x + 70, self.base_y), (x + 62, y), (x + 58, y)]
        )
        pygame.draw.polygon(
            surf, (90, 90, 95),
            [(x + 50, self.base_y), (x + 70, self.base_y), (x + 62, y), (x + 58, y)], 2
        )
        pygame.draw.circle(surf, (160, 160, 170), (int(self.cx), int(self.cy)), 8)
        pygame.draw.circle(surf, (90, 90, 95), (int(self.cx), int(self.cy)), 8, 2)
        for k in range(4):
            a = self.angle + k * (math.tau / 4.0)
            bx = self.cx + math.cos(a) * self.radius
            by = self.cy + math.sin(a) * self.radius
            pygame.draw.line(surf, (235, 235, 240), (int(self.cx), int(self.cy)), (int(bx), int(by)), 5)
            pygame.draw.line(surf, (90, 90, 95), (int(self.cx), int(self.cy)), (int(bx), int(by)), 2)

    def duck_hit(self, duck: Duck):
        if not duck.alive:
            return False
        dx = duck.x - self.cx
        dy = duck.y - self.cy
        return (dx * dx + dy * dy) <= (self.radius * self.radius)

class Insect:
    def __init__(self, x):
        self.x = float(x)
        self.y = random.randint(80, HEIGHT - 220)
        self.vx = -SCROLL_SPEED + random.uniform(-1.2, 0.6)
        self.vy = random.uniform(-0.6, 0.6)
        self.t = random.random() * 6.28

    def update(self):
        self.t += 0.25
        self.x += self.vx
        self.y += self.vy + math.sin(self.t) * 0.9
        self.y = clamp(self.y, 40, HEIGHT - 160)

    def draw(self, surf):
        x = int(self.x)
        y = int(self.y)
        pygame.draw.rect(surf, INSECT, (x, y, 2, 2))
        pygame.draw.rect(surf, INSECT, (x - 2, y + 1, 2, 1))
        pygame.draw.rect(surf, INSECT, (x + 2, y + 1, 2, 1))

    def rect(self):
        return pygame.Rect(int(self.x) - 2, int(self.y) - 2, 6, 6)

FORMATION_OFFSETS = [(0, 0), (-18, 12), (-18, -12), (-36, 24), (-36, 0), (-36, -24), (-54, 0)]

# ================== FULLSCREEN ==================
fullscreen = False
def toggle_fullscreen():
    global fullscreen, screen
    fullscreen = not fullscreen
    if fullscreen:
        screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.FULLSCREEN)
    else:
        try:
            screen = pygame.display.set_mode((WIDTH, HEIGHT), 0, vsync=1)
        except TypeError:
            screen = pygame.display.set_mode((WIDTH, HEIGHT), 0)

# ================== GAME STATE / RESET ==================
scene = pygame.Surface((WIDTH, HEIGHT))

def new_clouds():
    return [Cloud() for _ in range(10)]

def roll_windmill_delay():
    return random.randint(WINDMILL_MIN_MS, WINDMILL_MAX_MS)

def reset_game():
    global paused, zoom, camera_mode
    global ducks, bombs, people, explosions, structures, windmills, insects
    global splats, human_gibs, building_debris, smoke, flames
    global ammo, human_kills, last_bomb_time, screen_shake
    global clouds, next_windmill_ms

    paused = False
    zoom = 1.0
    camera_mode = 0

    ducks = [Duck()]
    bombs = []
    people = []
    explosions = []
    structures = []
    windmills = []
    insects = []

    splats = []
    human_gibs = []
    building_debris = []
    smoke = []
    flames = []

    ammo = 10
    human_kills = 0
    last_bomb_time = 0
    screen_shake = 0

    clouds = new_clouds()
    next_windmill_ms = pygame.time.get_ticks() + roll_windmill_delay()

    apply_cursor_visibility()
    set_fly_sound_paused(False)

def spawn_people():
    if random.random() < 0.12:
        people.append(Person(WIDTH + random.randint(0, 300)))

def spawn_structures():
    r = random.random()
    x = WIDTH + random.randint(0, 900)
    if r < 0.032:
        structures.append(Building(x, random.randint(110, 260), random.randint(90, 290)))
    elif r < 0.055:
        structures.append(Shack(x))
    elif r < 0.070:
        structures.append(Tower(x))
    elif r < 0.090:
        structures.append(Fence(x))
    elif r < 0.155:
        structures.append(Tree(x))

def spawn_insects():
    if random.random() < 0.02:
        insects.append(Insect(WIDTH + random.randint(0, 400)))

def spawn_building_destruction_fx(cx, cy):
    play_random(sfx_building_hit, 0.9)
    for _ in range(80):
        col = RUBBLE_LIGHT if random.random() < 0.6 else RUBBLE_DARK
        building_debris.append(WorldDebris(cx + random.randint(-28, 28), cy + random.randint(-22, 22), col))
    for _ in range(random.randint(3, 6)):
        flames.append(Flame(cx + random.randint(-30, 30), GROUND_TOP_Y - random.randint(0, 12)))
    for _ in range(random.randint(12, 18)):
        smoke.append(SmokePuff(cx + random.randint(-30, 30), cy + random.randint(-40, 30)))

def kill_person_with_fx(p, hit_x):
    global human_kills
    p.dead = True
    human_kills += 1
    play_random(sfx_people_hit, 0.9)
    splats.append(Splat(hit_x, GROUND_TOP_Y + random.randint(-2, 4)))
    cols = [RED, DARK_RED, p.skin, p.shirt, p.pants]
    for _ in range(22):
        human_gibs.append(WorldDebris(p.x + random.randint(-8, 8), GROUND_TOP_Y - 18 + random.randint(-10, 8), random.choice(cols)))

def kill_duck_with_splat(d: Duck):
    d.alive = False
    splats.append(Splat(d.x, d.y))
    for _ in range(18):
        human_gibs.append(WorldDebris(d.x + random.randint(-6, 6), d.y + random.randint(-6, 6), WHITE))

def cull_dead_ducks():
    global ducks
    ducks = [d for d in ducks if d.alive]

def spawn_windmill_if_due(now_ms):
    global next_windmill_ms
    if now_ms >= next_windmill_ms:
        windmills.append(Windmill(WIDTH + 300))
        next_windmill_ms = now_ms + roll_windmill_delay()

# initialize
reset_game()

# ================== MAIN LOOP ==================
running = True
apply_cursor_visibility()
set_fly_sound_paused(False)

while running:
    # smoother frame pacing
    clock.tick_busy_loop(FPS)
    now_ms = pygame.time.get_ticks()

    for e in pygame.event.get():
        if e.type == pygame.QUIT:
            running = False

        if e.type == pygame.KEYDOWN:
            if e.key == pygame.K_ESCAPE:
                running = False
            elif e.key == pygame.K_p:
                paused = not paused
                apply_cursor_visibility()
                set_fly_sound_paused(paused)
            elif e.key == pygame.K_f:
                toggle_fullscreen()
            elif e.key == pygame.K_c:
                camera_mode = 1 - camera_mode
            elif e.key == pygame.K_z:
                zoom = clamp(zoom + ZOOM_STEP, ZOOM_MIN, ZOOM_MAX)
            elif e.key == pygame.K_x:
                zoom = clamp(zoom - ZOOM_STEP, ZOOM_MIN, ZOOM_MAX)

        if not paused:
            drop = False
            if e.type == pygame.KEYDOWN and e.key == pygame.K_SPACE:
                drop = True
            if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                drop = True

            if drop and ammo > 0 and ducks:
                if now_ms - last_bomb_time > BOMB_COOLDOWN_MS:
                    lead = ducks[0]
                    bombs.append(Bomb(lead.feet_x, lead.feet_y))
                    ammo -= 1
                    play_random(sfx_quacks, 0.9)
                    last_bomb_time = now_ms

    if not paused:
        mx, my = pygame.mouse.get_pos()

        spawn_people()
        spawn_structures()
        spawn_insects()
        spawn_windmill_if_due(now_ms)

        for c in clouds:
            c.update()

        lead_tx, lead_ty = mx, my
        for i, d in enumerate(ducks):
            ox, oy = FORMATION_OFFSETS[min(i, len(FORMATION_OFFSETS) - 1)]
            d.update(lead_tx + ox, lead_ty + oy)

        for s in structures[:]:
            s.update()
            if s.offscreen_left():
                structures.remove(s)

        for w in windmills[:]:
            w.update()
            if w.offscreen_left():
                windmills.remove(w)

        for p in people[:]:
            p.update()
            if p.x < -160 or p.x > WIDTH + 160:
                people.remove(p)

        for ins in insects[:]:
            ins.update()
            if ins.x < -140:
                insects.remove(ins)

        # eat insect => +1 ammo + eat SFX
        for ins in insects[:]:
            ir = ins.rect()
            if any(d.alive and d.rect().colliderect(ir) for d in ducks):
                insects.remove(ins)
                play_random(sfx_insect_eat, 0.85)  # NEW
                globals()["ammo"] += 1

        for sp in splats[:]:
            sp.update()
            if sp.offscreen_left():
                splats.remove(sp)

        for gb in human_gibs[:]:
            gb.update()
            if gb.offscreen_left():
                human_gibs.remove(gb)

        for rb in building_debris[:]:
            rb.update()
            if rb.offscreen_left():
                building_debris.remove(rb)

        for sm in smoke[:]:
            sm.update()
            if sm.offscreen_left():
                smoke.remove(sm)

        for fl in flames[:]:
            fl.update()
            if fl.offscreen_left():
                flames.remove(fl)

        for b in bombs[:]:
            b.update()

            for p in people:
                if not p.dead and abs(p.x - b.x) < 220 and b.y > HEIGHT - 270:
                    p.panic = True
                    p.dir = -1 if p.x < b.x else 1

            if b.y > GROUND_TOP_Y:
                bombs.remove(b)
                explosions.append(Explosion(b.x, GROUND_TOP_Y - 5))
                play_random(sfx_explosions, 0.9)
                globals()["screen_shake"] = 12

                for p in people:
                    if p.dead:
                        continue
                    dx = abs(p.x - b.x)
                    if dx < 45:
                        kill_person_with_fx(p, b.x + random.randint(-6, 6))
                    elif dx < 220:
                        p.panic = True
                        p.dir = -1 if p.x < b.x else 1

                ex_r = 60
                destroyed_any = False
                for s in structures[:]:
                    if hasattr(s, "hit_by_explosion") and s.hit_by_explosion(b.x, ex_r):
                        destroyed_any = True
                        cx = s.x + getattr(s, "w", 40) * 0.5
                        cy = GROUND_TOP_Y - random.randint(20, 70)
                        spawn_building_destruction_fx(cx, cy)
                        structures.remove(s)

                if destroyed_any:
                    globals()["screen_shake"] = max(globals()["screen_shake"], 14)

        for ex in explosions[:]:
            ex.update()
            if ex.life <= 0:
                explosions.remove(ex)

        for w in windmills:
            for d in ducks:
                if d.alive and w.duck_hit(d):
                    kill_duck_with_splat(d)

        cull_dead_ducks()
        if len(ducks) == 0:
            reset_game()

        globals()["screen_shake"] = max(0, globals()["screen_shake"] - 1)

    # ================== DRAW ==================
    scene.fill(SKY)
    for c in clouds:
        c.draw(scene)

    pygame.draw.rect(scene, GROUND, (0, GROUND_TOP_Y, WIDTH, 100))
    pygame.draw.rect(scene, GROUND_DARK, (0, GROUND_TOP_Y - 40, WIDTH, 40))

    for s in structures:
        s.draw(scene)
    for w in windmills:
        w.draw(scene)

    for sp in splats:
        sp.draw(scene)
    for sm in smoke:
        sm.draw(scene)
    for fl in flames:
        fl.draw(scene)
    for rb in building_debris:
        rb.draw(scene)

    for p in people:
        p.draw(scene)
    for ins in insects:
        ins.draw(scene)
    for b in bombs:
        b.draw(scene)
    for ex in explosions:
        ex.draw(scene)
    for gb in human_gibs:
        gb.draw(scene)
    for d in ducks:
        d.draw(scene)

    hud = f"DUCKS: {len(ducks)}    AMMO: {ammo}    ZOOM: {int(zoom)}x"
    hud_surf = font.render(hud, True, BLACK)
    pygame.draw.rect(scene, (255, 255, 255), (12, 12, hud_surf.get_width() + 16, 30))
    pygame.draw.rect(scene, BLACK, (12, 12, hud_surf.get_width() + 16, 30), 2)
    scene.blit(hud_surf, (20, 18))

    if paused:
        banner = font.render("PAUSED (P to resume)  |  F fullscreen  |  C camera mode  |  Z/X zoom", True, BLACK)
        bw = banner.get_width() + 20
        pygame.draw.rect(scene, (255, 255, 255), ((WIDTH - bw) // 2, 52, bw, 34))
        pygame.draw.rect(scene, BLACK, ((WIDTH - bw) // 2, 52, bw, 34), 2)
        scene.blit(banner, ((WIDTH - banner.get_width()) // 2, 60))

    apply_cursor_visibility()

    if zoom <= 1.0001:
        ox = random.randint(-screen_shake, screen_shake) if not paused else 0
        oy = random.randint(-screen_shake, screen_shake) if not paused else 0
        screen.blit(scene, (ox, oy))
    else:
        scaled_w = int(WIDTH * zoom)
        scaled_h = int(HEIGHT * zoom)
        scaled = pygame.transform.scale(scene, (scaled_w, scaled_h))

        lead = ducks[0] if ducks else None
        cx, cy = get_zoom_center(lead)
        bx = int(cx - cx * zoom)
        by = int(cy - cy * zoom)

        ox = random.randint(-screen_shake, screen_shake) if not paused else 0
        oy = random.randint(-screen_shake, screen_shake) if not paused else 0
        screen.blit(scaled, (bx + ox, by + oy))

    pygame.display.flip()

pygame.quit()
sys.exit()

