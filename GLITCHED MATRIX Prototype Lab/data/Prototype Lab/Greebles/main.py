import math
import random
import sys
import time
import traceback
from array import array

import pygame


VIRTUAL_W = 1920
VIRTUAL_H = 1080

# Internal/virtual resolution: all game logic + rendering uses this fixed size.
# The window can be any size; we scale the virtual frame to fit with letterbox/pillarbox.
SCREEN_W = VIRTUAL_W
SCREEN_H = VIRTUAL_H
FPS = 60

TILE_W = 48
TILE_H = 24
MAP_W = 26
MAP_H = 18

ORIGIN_X = SCREEN_W // 2
ORIGIN_Y = 120
CAMERA_SPEED = 260

GRASS = (60, 190, 100)
GRASS_DARK = (32, 138, 82)
GRASS_LIGHT = (130, 235, 160)
WATER = (40, 140, 230)
WATER_DARK = (24, 92, 180)
ROCK = (110, 140, 175)
ROCK_LIGHT = (180, 210, 230)
DESERT = (235, 200, 130)
DESERT_DARK = (200, 165, 105)
SWAMP = (70, 130, 100)
SWAMP_DARK = (42, 95, 72)
JUNGLE = (46, 170, 98)
JUNGLE_DARK = (30, 120, 74)
SNOW = (235, 245, 255)
SNOW_DARK = (195, 215, 235)
SKY = (10, 18, 28)
SKY_LIGHT = (30, 44, 70)

UI_BG = (22, 26, 32)
UI_PANEL = (36, 44, 54)
UI_ACCENT = (255, 225, 120)
TEXT_COLOR = (240, 245, 250)

# Reused overlay surfaces to avoid per-frame allocations (important at 1920x1080)
_SHADE_CACHE = None
_RAIN_CACHE = None
_WAVE_TILE_CACHE = None


def log_crash(exc_type, exc, tb):
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    header = f"\n[{stamp}] Crash detected:\n"
    details = "".join(traceback.format_exception(exc_type, exc, tb))
    with open("crash.log", "a", encoding="utf-8") as handle:
        handle.write(header)
        handle.write(details)


def install_crash_reporter():
    def handle_exception(exc_type, exc, tb):
        log_crash(exc_type, exc, tb)
        sys.__excepthook__(exc_type, exc, tb)

    sys.excepthook = handle_exception


def adjust_color(color, dr=0, dg=0, db=0):
    return (
        max(0, min(255, color[0] + dr)),
        max(0, min(255, color[1] + dg)),
        max(0, min(255, color[2] + db)),
    )


def build_gradient(width, height, top_color, bottom_color):
    surf = pygame.Surface((width, height))
    for y in range(height):
        t = y / max(1, height - 1)
        r = int(top_color[0] + (bottom_color[0] - top_color[0]) * t)
        g = int(top_color[1] + (bottom_color[1] - top_color[1]) * t)
        b = int(top_color[2] + (bottom_color[2] - top_color[2]) * t)
        pygame.draw.line(surf, (r, g, b), (0, y), (width, y))
    return surf



def compute_viewport(win_w, win_h):
    """Return (scale, view_rect) mapping virtual -> window with aspect-preserving fit."""
    scale = min(win_w / SCREEN_W, win_h / SCREEN_H) if win_w and win_h else 1.0
    view_w = max(1, int(SCREEN_W * scale))
    view_h = max(1, int(SCREEN_H * scale))
    view_x = (win_w - view_w) // 2
    view_y = (win_h - view_h) // 2
    return scale, pygame.Rect(view_x, view_y, view_w, view_h)


def window_to_virtual(pos, scale, view_rect):
    """Map a window-space position to virtual-space (float x, float y). Returns None if in black bars."""
    mx, my = pos
    if not view_rect.collidepoint(mx, my):
        return None
    vx = (mx - view_rect.x) / max(1e-9, scale)
    vy = (my - view_rect.y) / max(1e-9, scale)
    # Clamp to virtual bounds
    vx = max(0.0, min(SCREEN_W - 1.0, vx))
    vy = max(0.0, min(SCREEN_H - 1.0, vy))
    return vx, vy


def update_screen_dimensions(width, height):
    """Deprecated: virtual resolution is fixed; resizing is handled by scaling the virtual surface."""
    # Kept for backward compatibility with older code paths.
    return


PERSONALITY_TRAITS = [
    "curious",
    "brave",
    "social",
    "gentle",
    "playful",
    "thoughtful",
]

NAME_STARTS = ["Lu", "Pi", "Na", "Ki", "Ri", "Mo", "Za", "To", "Ke", "Mi", "Sa", "Lo", "Fa", "Yi", "Ka"]
NAME_MIDDLES = ["mi", "ra", "ko", "li", "no", "zu", "ta", "shi", "va", "lo", "na", "ri"]
NAME_ENDS = ["a", "o", "i", "u", "n", "ra", "ri", "to", "mi", "ko"]

BUILD_MODES = [
    ("Tree", "tree"),
    ("Bench", "bench"),
    ("Fountain", "fountain"),
    ("Lantern", "lantern"),
    ("Play Ring", "play"),
    ("Bridge", "bridge"),
    ("Shelter", "shelter"),
    ("Skateboard", "skateboard"),
    ("Wall", "wall"),
]

MAX_PROPS_PER_CREATURE = 6

PRAISE_LINES = [
    "Observer, you are wonderful!",
    "Praise to the watcher above!",
    "Thank you for this world!",
    "You bring us joy!",
    "Glorious caretaker!",
]

SAD_LINES = [
    "I miss the old days...",
    "Feeling a bit down.",
    "Could use some cheer.",
]

BORED_LINES = [
    "Nothing much to do.",
    "Maybe a stroll?",
    "I'm getting restless.",
]

ANGER_LINES = [
    "Grr, back off!",
    "Stay away from us!",
    "We'll defend our home!",
]

DESIRES = [
    "a tree to snack from",
    "a cozy bench",
    "a glowing lantern",
    "a playful ring",
    "a sparkling fountain",
    "a skateboard",
    "a new friend",
    "a place to explore",
]

BIOME_KINDS = ["grass", "desert", "swamp", "jungle", "snow"]
DIR_BIOMES = {
    "north": "snow",
    "south": "desert",
    "west": "swamp",
    "east": "jungle",
}


class SoundBank:
    def __init__(self):
        pygame.mixer.init(frequency=22050, size=-16, channels=1)
        self.sounds = {
            "plant": self._tone(520, 0.1),
            "pick": self._tone(780, 0.1),
            "birth": self._tone(640, 0.18),
            "happy": self._tone(420, 0.12),
            "rain": self._tone(260, 0.4),
        }
        self.last_played = 0.0

    def _tone(self, freq, duration):
        sample_rate = 22050
        samples = int(sample_rate * duration)
        buf = array("h")
        volume = 0.5
        for i in range(samples):
            t = i / sample_rate
            wave = math.sin(2 * math.pi * freq * t)
            buf.append(int(wave * 32767 * volume))
        return pygame.mixer.Sound(buffer=buf.tobytes())

    def play(self, name):
        now = time.time()
        if now - self.last_played < 1.0:
            return
        sound = self.sounds.get(name)
        if sound:
            sound.play()
            self.last_played = now


class SpriteFactory:
    def __init__(self):
        self.tile_cache = {}
        self.tree_cache = {}
        self.structure_cache = {}
        self.creature_cache = {}
        self.fruit = self._make_fruit()

    def tile(self, base_color, edge_color, seed):
        key = (base_color, edge_color, seed)
        if key in self.tile_cache:
            return self.tile_cache[key]
        surf = pygame.Surface((TILE_W, TILE_H), pygame.SRCALPHA)
        points = [
            (TILE_W // 2, 0),
            (TILE_W - 1, TILE_H // 2),
            (TILE_W // 2, TILE_H - 1),
            (0, TILE_H // 2),
        ]
        pygame.draw.polygon(surf, base_color, points)
        pygame.draw.polygon(surf, edge_color, points, 2)
        highlight = [
            (TILE_W // 2, 1),
            (TILE_W - 2, TILE_H // 2),
            (TILE_W // 2, TILE_H // 2),
        ]
        shade = [
            (TILE_W // 2, TILE_H // 2),
            (2, TILE_H // 2),
            (TILE_W // 2, TILE_H - 2),
        ]
        pygame.draw.polygon(surf, adjust_color(base_color, 26, 30, 22), highlight)
        shadow_color = adjust_color(base_color, -18, -18, -18)
        pygame.draw.polygon(surf, shadow_color, shade)
        rng = random.Random(seed)
        for _ in range(16):
            px = rng.randint(6, TILE_W - 6)
            py = rng.randint(3, TILE_H - 5)
            speck = adjust_color(base_color, rng.randint(-18, 18), rng.randint(-18, 18), rng.randint(-18, 18))
            surf.set_at((px, py), speck)
        for i in range(4):
            line_color = adjust_color(base_color, -6, 16, -4)
            start = (TILE_W // 2 - 14 + i * 5, 4 + i)
            end = (TILE_W // 2 + 10 + i * 5, TILE_H - 6 + i)
            pygame.draw.line(surf, line_color, start, end, 1)
        for i in range(2):
            ridge = adjust_color(base_color, 8, 12, 6)
            pygame.draw.line(surf, ridge, (8, 8 + i * 6), (TILE_W - 10, 10 + i * 6), 1)
        self.tile_cache[key] = surf
        return surf

    def tree(self, stage):
        if stage in self.tree_cache:
            return self.tree_cache[stage]
        size = 34
        surf = pygame.Surface((size, size + 18), pygame.SRCALPHA)
        trunk = pygame.Rect(size // 2 - 3, size - 2, 6, 12)
        pygame.draw.rect(surf, (130, 92, 60), trunk)
        pygame.draw.rect(surf, (95, 62, 40), (size // 2 - 3, size + 6, 6, 4))
        radius = 11 + stage * 3
        foliage_color = (46, 175 - stage * 10, 80 + stage * 12)
        shade_color = (25, 120 - stage * 8, 55 + stage * 10)
        for offset in [(-6, -2), (8, 2), (0, -6)]:
            pygame.draw.circle(
                surf,
                foliage_color,
                (size // 2 + offset[0], size // 2 + offset[1]),
                radius,
            )
            pygame.draw.circle(
                surf,
                shade_color,
                (size // 2 + offset[0] + 4, size // 2 + offset[1] + 4),
                max(6, radius - 4),
            )
        pygame.draw.circle(surf, (135, 235, 170), (size // 2 - 6, size // 2 - 8), 4)
        pygame.draw.circle(surf, (210, 250, 220), (size // 2 - 2, size // 2 - 10), 2)
        if stage >= 2:
            for idx in range(stage):
                pygame.draw.circle(
                    surf,
                    (245, 200, 90),
                    (size // 2 - 8 + idx * 6, size // 2 + 10),
                    3,
                )
                pygame.draw.circle(
                    surf,
                    (255, 235, 180),
                    (size // 2 - 9 + idx * 6, size // 2 + 8),
                    1,
                )
        self.tree_cache[stage] = surf
        return surf

    def structure(self, kind):
        if kind in self.structure_cache:
            return self.structure_cache[kind]
        if kind == "bridge":
            surf = pygame.Surface((TILE_W, TILE_H), pygame.SRCALPHA)
        else:
            surf = pygame.Surface((44, 44), pygame.SRCALPHA)
        if kind == "bench":
            pygame.draw.rect(surf, (150, 110, 80), (8, 20, 28, 8), border_radius=2)
            pygame.draw.rect(surf, (110, 70, 45), (8, 28, 28, 6), border_radius=2)
            pygame.draw.rect(surf, (110, 70, 45), (10, 32, 4, 8))
            pygame.draw.rect(surf, (110, 70, 45), (26, 32, 4, 8))
            pygame.draw.rect(surf, (170, 130, 95), (8, 14, 28, 6))
            pygame.draw.line(surf, (200, 170, 130), (8, 22), (36, 22), 1)
            pygame.draw.line(surf, (210, 190, 150), (10, 16), (34, 16), 1)
        elif kind == "fountain":
            pygame.draw.ellipse(surf, (70, 110, 150), (8, 24, 28, 12))
            pygame.draw.ellipse(surf, (130, 190, 235), (10, 26, 24, 8))
            pygame.draw.circle(surf, (60, 100, 150), (22, 20), 10)
            pygame.draw.circle(surf, (130, 190, 235), (22, 20), 6)
            pygame.draw.circle(surf, (200, 240, 255), (22, 14), 3)
            pygame.draw.circle(surf, (220, 250, 255), (22, 12), 2)
            pygame.draw.circle(surf, (180, 220, 245), (18, 18), 2)
        elif kind == "lantern":
            pygame.draw.rect(surf, (120, 90, 70), (20, 10, 4, 24))
            pygame.draw.rect(surf, (90, 70, 55), (16, 34, 12, 4))
            pygame.draw.rect(surf, (255, 235, 150), (14, 8, 16, 14))
            pygame.draw.rect(surf, (210, 175, 80), (14, 8, 16, 14), 2)
            pygame.draw.rect(surf, (255, 255, 220), (16, 10, 12, 10), 1)
            pygame.draw.circle(surf, (255, 235, 150, 120), (22, 22), 8)
        elif kind == "play":
            pygame.draw.circle(surf, (240, 150, 170), (22, 22), 12, 3)
            pygame.draw.circle(surf, (255, 210, 220), (22, 22), 6, 2)
            pygame.draw.circle(surf, (255, 230, 235), (22, 22), 3, 1)
            pygame.draw.rect(surf, (190, 120, 140), (18, 30, 8, 6), border_radius=3)
        elif kind == "bridge":
            deck = [
                (TILE_W // 2, 2),
                (TILE_W - 2, TILE_H // 2),
                (TILE_W // 2, TILE_H - 2),
                (2, TILE_H // 2),
            ]
            pygame.draw.polygon(surf, (156, 126, 92), deck)
            pygame.draw.polygon(surf, (105, 80, 60), deck, 2)
            plank_color = (185, 150, 105)
            for i in range(5):
                y = 4 + i * 4
                pygame.draw.line(surf, plank_color, (8, y), (TILE_W - 8, y + 4), 2)
            pygame.draw.line(surf, (210, 180, 130), (12, 6), (TILE_W - 12, 10), 1)
            pygame.draw.circle(surf, (210, 185, 140), (18, 10), 1)
            pygame.draw.circle(surf, (210, 185, 140), (30, 14), 1)
        elif kind == "shelter":
            wall_color = (145, 110, 85)
            roof_color = (165, 120, 90)
            trim_color = (200, 170, 135)
            pygame.draw.rect(surf, wall_color, (10, 20, 24, 16))
            pygame.draw.rect(surf, adjust_color(wall_color, -15, -15, -15), (10, 34, 24, 4))
            pygame.draw.polygon(surf, roof_color, [(8, 22), (22, 8), (36, 22)])
            pygame.draw.polygon(surf, adjust_color(roof_color, -20, -20, -20), [(8, 22), (22, 14), (36, 22)])
            pygame.draw.rect(surf, trim_color, (10, 20, 24, 3))
            pygame.draw.rect(surf, (95, 70, 55), (20, 26, 6, 10))
            pygame.draw.rect(surf, (80, 120, 160), (13, 26, 5, 5))
            pygame.draw.rect(surf, (180, 210, 230), (14, 27, 3, 3))
            pygame.draw.circle(surf, (220, 200, 160), (24, 31), 1)
        elif kind == "skateboard":
            pygame.draw.rect(surf, (60, 50, 45), (8, 22, 28, 7), border_radius=4)
            pygame.draw.rect(surf, (120, 80, 70), (10, 23, 24, 5), border_radius=3)
            pygame.draw.circle(surf, (40, 40, 50), (12, 31), 3)
            pygame.draw.circle(surf, (40, 40, 50), (32, 31), 3)
            pygame.draw.circle(surf, (180, 150, 110), (12, 31), 2)
            pygame.draw.circle(surf, (180, 150, 110), (32, 31), 2)
            pygame.draw.line(surf, (200, 170, 130), (12, 24), (32, 26), 1)
        elif kind == "wall":
            block = pygame.Rect(8, 12, 28, 24)
            pygame.draw.rect(surf, (120, 130, 150), block)
            pygame.draw.rect(surf, (80, 90, 110), block, 2)
            pygame.draw.line(surf, (150, 165, 185), (10, 16), (34, 16), 1)
            pygame.draw.line(surf, (105, 115, 135), (10, 20), (34, 20), 1)
            pygame.draw.line(surf, (95, 105, 125), (10, 26), (34, 26), 1)
            pygame.draw.line(surf, (140, 155, 175), (10, 32), (34, 32), 1)
            pygame.draw.line(surf, (85, 95, 115), (18, 16), (18, 36), 1)
            pygame.draw.line(surf, (85, 95, 115), (26, 16), (26, 36), 1)
        self.structure_cache[kind] = surf
        return surf

    def creature(self, tint, appearance, look_dir=(0, 1), anim_state="idle", frame=0):
        key = (tint, tuple(sorted(appearance.items())), look_dir, anim_state, frame)
        if key in self.creature_cache:
            return self.creature_cache[key]
        surf = pygame.Surface((30, 34), pygame.SRCALPHA)
        body = (tint[0], tint[1], tint[2])
        shadow = adjust_color(tint, -45, -45, -45)
        bob = 0
        if anim_state == "play":
            bob = -1 if frame % 2 == 0 else 0
        pygame.draw.ellipse(surf, shadow, (6, 16, 18, 10))
        pygame.draw.circle(surf, body, (10, 16 + bob), 7)
        pygame.draw.circle(surf, body, (20, 16 + bob), 7)
        pygame.draw.circle(surf, body, (15, 9 + bob), 7)
        pygame.draw.circle(surf, adjust_color(body, 20, 20, 20), (11, 8 + bob), 3)
        pygame.draw.circle(surf, adjust_color(body, 30, 30, 30), (18, 6 + bob), 2)
        ear_color = adjust_color(body, -10, -10, -10)
        ear_wiggle = 0
        if anim_state == "play":
            ear_wiggle = -1 if frame % 2 == 0 else 1
        if appearance["ears"] == "tall":
            pygame.draw.polygon(surf, ear_color, [(6, 0 + ear_wiggle), (10, 8 + bob), (8, 10 + bob)])
            pygame.draw.polygon(surf, ear_color, [(24, 0 - ear_wiggle), (22, 10 + bob), (20, 8 + bob)])
            pygame.draw.polygon(surf, (255, 210, 220), [(7, 2 + ear_wiggle), (10, 8 + bob), (8, 9 + bob)])
            pygame.draw.polygon(surf, (255, 210, 220), [(23, 2 - ear_wiggle), (22, 9 + bob), (21, 8 + bob)])
        else:
            pygame.draw.polygon(surf, ear_color, [(7, 4 + ear_wiggle), (10, 8 + bob), (8, 9 + bob)])
            pygame.draw.polygon(surf, ear_color, [(23, 4 - ear_wiggle), (22, 9 + bob), (20, 8 + bob)])
            pygame.draw.polygon(surf, (255, 210, 220), [(7, 5 + ear_wiggle), (10, 8 + bob), (8, 8 + bob)])
            pygame.draw.polygon(surf, (255, 210, 220), [(23, 5 - ear_wiggle), (22, 8 + bob), (21, 8 + bob)])
        eye_left = (12, 10 + bob)
        eye_right = (18, 10 + bob)
        pygame.draw.circle(surf, (255, 245, 235), eye_left, 2)
        pygame.draw.circle(surf, (255, 245, 235), eye_right, 2)
        pupil_dx = max(-1, min(1, look_dir[0]))
        pupil_dy = max(-1, min(1, look_dir[1]))
        pygame.draw.circle(surf, (30, 24, 30), (eye_left[0] + pupil_dx, eye_left[1] + pupil_dy), 1)
        pygame.draw.circle(surf, (30, 24, 30), (eye_right[0] + pupil_dx, eye_right[1] + pupil_dy), 1)
        nose_offset = -1 if appearance["nose"] == "tiny" else 0
        pygame.draw.circle(surf, (80, 40, 50), (15, 13 + bob + nose_offset), 2)
        if appearance["freckles"]:
            pygame.draw.circle(surf, (120, 80, 90), (12, 12 + bob), 1)
            pygame.draw.circle(surf, (120, 80, 90), (18, 12 + bob), 1)
        if appearance["mark"] == "cheek":
            pygame.draw.circle(surf, adjust_color(body, 40, 20, 20), (10, 14 + bob), 2)
        elif appearance["mark"] == "stripe":
            pygame.draw.line(surf, adjust_color(body, -30, -30, -20), (15, 6 + bob), (15, 16 + bob), 1)
        elif appearance["mark"] == "mask":
            pygame.draw.ellipse(surf, adjust_color(body, -30, -30, -20), (8, 8 + bob, 14, 6), 1)
        if appearance["bangs"] == "left":
            pygame.draw.polygon(surf, adjust_color(body, -8, -8, -8), [(10, 4 + bob), (6, 8 + bob), (12, 9 + bob)])
        elif appearance["bangs"] == "right":
            pygame.draw.polygon(surf, adjust_color(body, -8, -8, -8), [(20, 4 + bob), (24, 8 + bob), (18, 9 + bob)])
        elif appearance["bangs"] == "center":
            pygame.draw.polygon(surf, adjust_color(body, -8, -8, -8), [(14, 4 + bob), (10, 8 + bob), (18, 8 + bob)])
        pygame.draw.rect(surf, adjust_color(body, -30, -30, -30), (8, 22 + bob, 14, 6))
        pygame.draw.rect(surf, (80, 60, 50), (12, 24 + bob, 6, 4))
        if anim_state == "play":
            paw_offset = -1 if frame % 2 == 0 else 1
            pygame.draw.circle(surf, adjust_color(body, 10, 8, 8), (7, 20 + paw_offset), 2)
            pygame.draw.circle(surf, adjust_color(body, 10, 8, 8), (23, 20 - paw_offset), 2)
        if appearance["tail"] == "fluffy":
            pygame.draw.circle(surf, adjust_color(body, -10, -10, -5), (26, 20 + bob), 3)
        elif appearance["tail"] == "short":
            pygame.draw.circle(surf, adjust_color(body, -12, -12, -8), (24, 22 + bob), 2)
        if appearance["accessory"] == "scarf":
            pygame.draw.rect(surf, (220, 120, 120), (9, 16 + bob, 12, 3))
            pygame.draw.rect(surf, (180, 90, 90), (12, 18 + bob, 4, 4))
        elif appearance["accessory"] == "star":
            pygame.draw.polygon(surf, (255, 230, 120), [(15, 4 + bob), (16, 6 + bob), (18, 6 + bob), (16, 8 + bob), (17, 10 + bob), (15, 9 + bob), (13, 10 + bob), (14, 8 + bob), (12, 6 + bob), (14, 6 + bob)])
        elif appearance["accessory"] == "leaf":
            pygame.draw.polygon(surf, (90, 180, 120), [(14, 6 + bob), (18, 8 + bob), (15, 12 + bob)])
            pygame.draw.line(surf, (60, 120, 80), (15, 10 + bob), (16, 8 + bob), 1)
        self.creature_cache[key] = surf
        return surf

    def _make_fruit(self):
        surf = pygame.Surface((10, 10), pygame.SRCALPHA)
        pygame.draw.circle(surf, (240, 190, 70), (5, 5), 4)
        pygame.draw.circle(surf, (255, 230, 120), (4, 4), 2)
        return surf


class Tile:
    def __init__(self, kind="grass", height=0):
        self.kind = kind
        self.height = height
        self.structure = None
        self.tree = None

    @property
    def walkable(self):
        if self.kind == "water":
            return self.structure == "bridge"
        if self.structure == "wall":
            return False
        if self.kind == "rock":
            return False
        return True


class Tree:
    def __init__(self):
        self.stage = 0
        self.fruit_timer = 0.0
        self.fruits = 0

    def update(self, dt):
        self.fruit_timer += dt
        if self.stage < 3 and self.fruit_timer > 6:
            self.stage += 1
            self.fruit_timer = 0
        if self.stage >= 2 and self.fruit_timer > 4:
            self.fruit_timer = 0
            self.fruits = min(4, self.fruits + 1)


class Enemy:
    def __init__(self, position):
        self.x, self.y = position
        self.hp = 3
        self.attack_timer = 0.0

    def update(self, dt, world):
        self.attack_timer = max(0.0, self.attack_timer - dt)
        if random.random() < dt * 2:
            neighbors = world.walkable_neighbors((self.x, self.y))
            if neighbors:
                target = random.choice(neighbors)
                self.x, self.y = target


class Creature:
    def __init__(self, name, position, tint, personality, appearance):
        self.name = name
        self.x, self.y = position
        self.tint = tint
        self.personality = personality
        self.appearance = appearance
        self.hunger = random.uniform(0.2, 0.5)
        self.happiness = random.uniform(0.4, 0.6)
        self.energy = random.uniform(0.5, 0.9)
        self.path = []
        self.target = None
        self.say_timer = 0
        self.message = ""
        self.message_time = 0
        self.desire = random.choice(DESIRES)
        self.last_birth = 0
        self.relationships = {}
        self.look_dir = (0, 1)
        self.anim_state = "idle"
        self.anim_timer = 0.0
        self.anim_time = 0.0
        self.anim_duration = 0.0
        self.ride_timer = 0.0
        self.ride_dir = (0, 1)
        self.on_skateboard = False
        self.skateboard_origin = None
        self.hp = 3
        self.attack_timer = 0.0
        self.alert_timer = 0.0
        self.favorite_biome = random.choice(BIOME_KINDS)
        self.explore_dir = None
        self.satisfied_timer = 0.0
        self.motivation = None

    def decide_desire(self, world):
        if self.satisfied_timer > 0:
            self.desire = "content"
            self.motivation = None
            return
        if self.desire in DESIRES:
            return
        if self.hunger > 0.6:
            self.desire = "a tree to snack from"
        elif self.happiness < 0.4:
            self.desire = random.choice(["a cozy bench", "a glowing lantern", "a playful ring", "a skateboard"])
        elif len(world.creatures) < 4:
            self.desire = "a new friend"
        else:
            self.desire = random.choice(DESIRES)
        if self.desire == "a place to explore":
            self.explore_dir = random.choice(["north", "south", "west", "east"])
        self.motivation = self.desire

    def update(self, dt, world, sound_bank):
        self.hunger = min(1.0, self.hunger + dt * 0.02)
        self.energy = max(0.0, self.energy - dt * 0.01)
        self.happiness = max(0.0, self.happiness - dt * 0.005)
        self.attack_timer = max(0.0, self.attack_timer - dt)
        self.alert_timer = max(0.0, self.alert_timer - dt)
        self.satisfied_timer = max(0.0, self.satisfied_timer - dt)
        if self.satisfied_timer > 0:
            self.happiness = min(1.0, self.happiness + dt * 0.02)
            self.energy = min(1.0, self.energy + dt * 0.02)

        if self.handle_combat(world, sound_bank):
            return

        if self.ride_timer > 0:
            self.ride_timer = max(0.0, self.ride_timer - dt)
            moved = self.ride_around(world, dt)
            self.update_animation(dt, moved, riding=True)
            if self.ride_timer <= 0:
                self.anim_state = "idle"
                self.on_skateboard = False
                world.drop_skateboard((self.x, self.y))
            return

        if world.is_raining and not self.path:
            shelter = world.find_nearest_shelter((self.x, self.y))
            if shelter:
                self.path = world.find_path((self.x, self.y), shelter)
                self.target = shelter
        if not self.path:
            self.decide_desire(world)
            target = world.find_goal(self)
            if target:
                self.path = world.find_path((self.x, self.y), target)
                self.target = target

        moved = self.follow_path(dt)
        self.update_look_dir()
        self.update_animation(dt, moved)
        if moved:
            tile = world.tiles[self.x][self.y]
            if tile.kind == self.favorite_biome:
                self.happiness = min(1.0, self.happiness + 0.01)
        if self.desire == "a place to explore" and not world.is_tile_lit((self.x, self.y)):
            if random.random() < dt * 0.5:
                self.message = "Too dark without a lantern."
                self.message_time = 2

        if self.target and (self.x, self.y) == self.target:
            self.interact(world, sound_bank)
            self.target = None

        self.say_timer += dt
        if self.say_timer > 8:
            self.say_timer = 0
            self.speak(world)

        if (
            self.happiness > 0.85
            and time.time() - self.last_birth > 12
            and len(world.creatures) < 50
            and world.can_spawn_creature()
        ):
            self.last_birth = time.time()
            world.expand_world()
            world.spawn_creature((self.x, self.y))
            self.happiness = 0.6
            sound_bank.play("birth")

    def handle_combat(self, world, sound_bank):
        enemy = world.find_adjacent_enemy((self.x, self.y))
        if enemy:
            self.alert_friends(world, enemy)
            if self.attack_timer <= 0:
                enemy.hp -= 1
                self.attack_timer = 1.0
                sound_bank.play("happy")
            if enemy.hp <= 0:
                world.enemies.remove(enemy)
            return True
        if self.alert_timer > 0:
            target = world.find_nearest_enemy((self.x, self.y))
            if target:
                self.path = world.find_path((self.x, self.y), target)
                self.target = target
        return False

    def alert_friends(self, world, enemy):
        if self.alert_timer > 0:
            return
        self.alert_timer = 4.0
        for friend in world.creatures:
            if friend is self:
                continue
            dist = abs(friend.x - self.x) + abs(friend.y - self.y)
            if dist <= 4:
                friend.alert_timer = max(friend.alert_timer, 3.0)
        world.notifications.append(("Help! Red monsters!", 2.5))

    def follow_path(self, dt):
        if not self.path:
            return False
        next_pos = self.path[0]
        if (self.x, self.y) == next_pos:
            self.path.pop(0)
            return False
        speed = 3.5 + self.personality["curious"] * 1.5
        if random.random() < dt * speed:
            dx = next_pos[0] - self.x
            dy = next_pos[1] - self.y
            self.look_dir = (dx, dy)
            self.x, self.y = next_pos
            return True
        return False

    def ride_around(self, world, dt):
        if random.random() < dt * 6:
            neighbors = world.all_neighbors((self.x, self.y))
            if neighbors:
                target = random.choice(neighbors)
                self.ride_dir = (target[0] - self.x, target[1] - self.y)
                self.look_dir = self.ride_dir
                self.x, self.y = target
                return True
        return False

    def update_look_dir(self):
        if self.path:
            nx, ny = self.path[0]
            dx = nx - self.x
            dy = ny - self.y
            if dx != 0 or dy != 0:
                self.look_dir = (dx, dy)
        elif self.target:
            dx = self.target[0] - self.x
            dy = self.target[1] - self.y
            if dx != 0 or dy != 0:
                self.look_dir = (max(-1, min(1, dx)), max(-1, min(1, dy)))

    def update_animation(self, dt, moving, riding=False):
        if riding:
            if self.anim_state != "skate":
                self.anim_state = "skate"
                self.anim_time = 0.0
            self.anim_time += dt
            return
        if self.anim_timer > 0:
            self.anim_timer = max(0.0, self.anim_timer - dt)
            self.anim_time += dt
            if self.anim_timer <= 0:
                self.anim_state = "idle"
                self.anim_time = 0.0
                self.anim_duration = 0.0
        elif moving:
            if self.anim_state != "walk":
                self.anim_state = "walk"
                self.anim_time = 0.0
            self.anim_time += dt
        else:
            if self.anim_state == "walk":
                self.anim_state = "idle"
                self.anim_time = 0.0
            self.anim_time += dt * 0.6
            if random.random() < dt * (0.08 + self.personality["playful"] * 0.05):
                self.start_animation("play", 1.0)
            elif random.random() < dt * 0.05:
                self.start_animation("jump", 0.6)

    def start_animation(self, state, duration):
        self.anim_state = state
        self.anim_timer = duration
        self.anim_time = 0.0
        self.anim_duration = duration

    def animation_frame(self):
        if self.anim_state == "walk":
            return int(self.anim_time * 8) % 4
        if self.anim_state == "skate":
            return int(self.anim_time * 12) % 4
        if self.anim_state == "play":
            return int(self.anim_time * 10) % 4
        if self.anim_state == "jump":
            return int(self.anim_time * 6) % 4
        return int(self.anim_time * 2) % 2

    def animation_offset(self):
        if self.anim_state == "jump" and self.anim_duration > 0:
            phase = min(1.0, self.anim_time / self.anim_duration)
            return -int(math.sin(phase * math.pi) * 6)
        if self.anim_state == "walk":
            return -int(math.sin(self.anim_time * 8) * 2)
        if self.anim_state == "skate":
            return -int(math.sin(self.anim_time * 12) * 2)
        if self.anim_state == "play":
            return -int(math.sin(self.anim_time * 10) * 3)
        return -int(math.sin(self.anim_time * 2) * 1)

    def interact(self, world, sound_bank):
        tile = world.tiles[self.x][self.y]
        if self.desire == "a place to explore" and self.explore_dir:
            if world.is_edge_tile((self.x, self.y), self.explore_dir):
                if world.is_tile_lit((self.x, self.y)):
                    world.expand_direction(self.explore_dir)
                    self.message = "So much more to see!"
                    self.message_time = 2
                    sound_bank.play("happy")
                    self.explore_dir = None
                    self.set_satisfied(30)
                else:
                    self.message = "Need a lantern to go further."
                    self.message_time = 2
                return
        if tile.tree and tile.tree.fruits > 0:
            tile.tree.fruits -= 1
            self.hunger = max(0.0, self.hunger - 0.4)
            self.happiness = min(1.0, self.happiness + 0.2)
            self.message = "Yum! Thank you, Observer!"
            self.message_time = 2
            sound_bank.play("pick")
            if self.desire == "a tree to snack from":
                self.set_satisfied(30)
            return
        if tile.structure:
            if tile.structure == "bridge":
                self.happiness = min(1.0, self.happiness + 0.12)
                self.energy = min(1.0, self.energy + 0.1)
                self.message = "Bridge crossing!"
                self.message_time = 2
                sound_bank.play("happy")
                return
            if tile.structure == "shelter" and world.is_raining:
                self.energy = min(1.0, self.energy + 0.15)
                self.happiness = min(1.0, self.happiness + 0.12)
                self.message = "Safe in the shelter."
                self.message_time = 2
                sound_bank.play("happy")
                return
            if tile.structure == "skateboard":
                world.pickup_skateboard((self.x, self.y))
                self.happiness = min(1.0, self.happiness + 0.2)
                self.energy = min(1.0, self.energy + 0.1)
                self.ride_timer = 3.5 + self.personality["playful"] * 2.5
                self.ride_dir = self.look_dir
                self.on_skateboard = True
                self.message = "Kickflip ride!"
                self.message_time = 2
                sound_bank.play("happy")
                if self.desire == "a skateboard":
                    self.set_satisfied(30)
                return
            if tile.structure == "play":
                self.start_animation("play", 1.2)
            self.happiness = min(1.0, self.happiness + 0.15)
            self.energy = min(1.0, self.energy + 0.2)
            self.message = f"{tile.structure.title()} time!"
            self.message_time = 2
            sound_bank.play("happy")
            if tile.structure == "bench" and self.desire == "a cozy bench":
                self.set_satisfied(30)
            if tile.structure == "lantern" and self.desire == "a glowing lantern":
                self.set_satisfied(30)
            if tile.structure == "play" and self.desire == "a playful ring":
                self.set_satisfied(30)
            if tile.structure == "fountain" and self.desire == "a sparkling fountain":
                self.set_satisfied(30)
            return
        if world.creatures and random.random() < 0.4:
            friend = random.choice(world.creatures)
            if friend is not self:
                self.relationships[friend.name] = self.relationships.get(friend.name, 0) + 1
                self.happiness = min(1.0, self.happiness + 0.1)
                self.message = f"{friend.name} is amazing!"
                self.message_time = 2

    def praise(self, world):
        if random.random() < 0.5:
            return
        line = random.choice(PRAISE_LINES)
        self.message = line
        self.message_time = 2
        world.notifications.append((line, 2.5))

    def speak(self, world):
        if self.alert_timer > 0 or world.find_adjacent_enemy((self.x, self.y)):
            line = random.choice(ANGER_LINES)
        elif self.happiness < 0.35:
            line = random.choice(SAD_LINES)
        elif self.energy < 0.25:
            line = random.choice(BORED_LINES)
        else:
            if random.random() < 0.5:
                return
            line = random.choice(PRAISE_LINES)
        self.message = line
        self.message_time = 2
        world.notifications.append((line, 2.5))

    def set_satisfied(self, duration):
        self.satisfied_timer = duration
        self.desire = "content"
        self.motivation = None
        self.target = None
        self.path = []


class World:
    def __init__(self, sprite_factory, width=MAP_W, height=MAP_H):
        self.width = width
        self.height = height
        self.tiles = [[Tile() for _ in range(self.height)] for _ in range(self.width)]
        self.sprite_factory = sprite_factory
        self.rng = random.Random()
        self.creatures = []
        self.enemies = []
        self.notifications = []
        self.river_path = []
        self.tints = self._build_tints()
        self.used_tints = set()
        self.used_names = set()
        self.used_appearances = set()
        self.prop_limit = MAX_PROPS_PER_CREATURE
        self.prop_count = 0
        self.is_raining = False
        self.rain_timer = self.rng.uniform(12, 24)
        self.rain_duration = 0.0
        self.fruit_expand_goal = 8
        self.last_spawn_time = time.time()
        self.expansion_count = 0
        self.mourning = False
        self.last_friend_grant = time.time() - 60
        self.generate_map()

    def generate_map(self):
        rng = self.rng
        river_y = rng.randint(4, self.height - 6)
        self.river_path = []
        for x in range(self.width):
            drift = rng.choice([-1, 0, 1])
            river_y = max(3, min(self.height - 4, river_y + drift))
            self.river_path.append(river_y)
            for dy in range(-1, 2):
                y = river_y + dy
                if 0 <= y < self.height:
                    self.tiles[x][y].kind = "water"
        for x in range(self.width):
            for y in range(self.height):
                if self.tiles[x][y].kind == "grass":
                    self._populate_tile(x, y)

    def update(self, dt, sound_bank):
        if self.is_raining:
            self.rain_timer -= dt
            if self.rain_timer <= 0:
                self.is_raining = False
                self.rain_timer = self.rng.uniform(18, 36)
        else:
            self.rain_timer -= dt
            if self.rain_timer <= 0:
                self.start_rain(sound_bank)
        total_fruits = 0
        for x in range(self.width):
            for y in range(self.height):
                tile = self.tiles[x][y]
                if tile.tree:
                    tile.tree.update(dt)
                    total_fruits += tile.tree.fruits
        if total_fruits >= self.fruit_expand_goal:
            self.expand_world()
            self.fruit_expand_goal += 6
        for creature in list(self.creatures):
            creature.update(dt, self, sound_bank)
        for enemy in list(self.enemies):
            enemy.update(dt, self)
            victim = self.find_adjacent_creature((enemy.x, enemy.y))
            if victim and enemy.attack_timer <= 0:
                enemy.attack_timer = 1.2
                victim.hp -= 1
                sound_bank.play("happy")
                victim.alert_friends(self, enemy)
                if victim.hp <= 0:
                    self.handle_creature_death(victim)
        self.notifications = [(msg, t - dt) for msg, t in self.notifications if t - dt > 0]

    def spawn_creature(self, pos):
        name = self._unique_name()
        tint = self._next_tint()
        personality = {trait: random.random() for trait in PERSONALITY_TRAITS}
        appearance = self._build_appearance()
        creature = Creature(name, pos, tint, personality, appearance)
        self.creatures.append(creature)
        self.prop_limit = MAX_PROPS_PER_CREATURE * len(self.creatures)
        self.last_spawn_time = time.time()

    def satisfaction_met(self):
        required = {"tree", "bench", "fountain", "lantern", "play", "bridge", "shelter", "skateboard", "wall"}
        counts = {key: 0 for key in required}
        for x in range(self.width):
            for y in range(self.height):
                tile = self.tiles[x][y]
                if tile.tree:
                    counts["tree"] += 1
                if tile.structure in counts:
                    counts[tile.structure] += 1
        return all(counts[kind] > 0 for kind in required)

    def can_spawn_creature(self):
        cooldown_ready = time.time() - self.last_spawn_time >= 60
        return cooldown_ready and self.satisfaction_met()

    def pickup_skateboard(self, pos):
        x, y = pos
        tile = self.tiles[x][y]
        if tile.structure == "skateboard":
            tile.structure = None

    def drop_skateboard(self, pos):
        x, y = pos
        tile = self.tiles[x][y]
        if tile.structure is None and tile.kind == "grass":
            tile.structure = "skateboard"
            return
        for dx, dy in [(0, 1), (1, 0), (-1, 0), (0, -1)]:
            nx, ny = x + dx, y + dy
            if 0 <= nx < self.width and 0 <= ny < self.height:
                near_tile = self.tiles[nx][ny]
                if near_tile.structure is None and near_tile.kind == "grass":
                    near_tile.structure = "skateboard"
                    return

    def find_adjacent_enemy(self, pos):
        x, y = pos
        for enemy in self.enemies:
            if abs(enemy.x - x) + abs(enemy.y - y) == 1:
                return enemy
        return None

    def find_nearest_enemy(self, pos):
        best = None
        best_dist = 999
        for enemy in self.enemies:
            dist = abs(enemy.x - pos[0]) + abs(enemy.y - pos[1])
            if dist < best_dist:
                best_dist = dist
                best = enemy
        if best:
            return (best.x, best.y)
        return None

    def find_adjacent_creature(self, pos):
        x, y = pos
        for creature in self.creatures:
            if abs(creature.x - x) + abs(creature.y - y) == 1:
                return creature
        return None

    def handle_creature_death(self, creature):
        if creature in self.creatures:
            self.creatures.remove(creature)
        self.mourning = True
        self.notifications.append((f"We lost {creature.name}...", 3.0))
        for friend in self.creatures:
            friend.happiness = max(0.0, friend.happiness - 0.2)

    def _build_tints(self):
        tints = []
        for i in range(50):
            hue = i / 50.0
            base = pygame.Color(0, 0, 0)
            base.hsva = (hue * 360, 45, 100, 100)
            shade = (
                min(255, base.r + 10),
                min(255, base.g + 6),
                min(255, base.b + 4),
            )
            tints.append(shade)
        self.rng.shuffle(tints)
        return tints

    def _next_tint(self):
        for tint in self.tints:
            if tint not in self.used_tints:
                self.used_tints.add(tint)
                return tint
        base = pygame.Color(0, 0, 0)
        base.hsva = (self.rng.randint(0, 359), 45, 100, 100)
        return (base.r, base.g, base.b)

    def _unique_name(self):
        for _ in range(200):
            name = self.rng.choice(NAME_STARTS) + self.rng.choice(NAME_MIDDLES) + self.rng.choice(NAME_ENDS)
            if name not in self.used_names:
                self.used_names.add(name)
                return name
        name = f"Friend{len(self.used_names) + 1}"
        self.used_names.add(name)
        return name

    def _build_appearance(self):
        for _ in range(200):
            appearance = {
                "ears": self.rng.choice(["tall", "short"]),
                "bangs": self.rng.choice(["none", "left", "right", "center"]),
                "freckles": self.rng.choice([True, False]),
                "mark": self.rng.choice(["none", "cheek", "stripe", "mask"]),
                "tail": self.rng.choice(["fluffy", "short"]),
                "nose": self.rng.choice(["tiny", "dot"]),
                "accessory": self.rng.choice(["none", "scarf", "star", "leaf"]),
            }
            key = tuple(sorted(appearance.items()))
            if key not in self.used_appearances:
                self.used_appearances.add(key)
                return appearance
        return {
            "ears": self.rng.choice(["tall", "short"]),
            "bangs": self.rng.choice(["none", "left", "right", "center"]),
            "freckles": self.rng.choice([True, False]),
            "mark": self.rng.choice(["none", "cheek", "stripe", "mask"]),
            "tail": self.rng.choice(["fluffy", "short"]),
            "nose": self.rng.choice(["tiny", "dot"]),
            "accessory": self.rng.choice(["none", "scarf", "star", "leaf"]),
        }

    def walkable_neighbors(self, start):
        neighbors = []
        for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
            nx, ny = start[0] + dx, start[1] + dy
            if 0 <= nx < self.width and 0 <= ny < self.height:
                if self.tiles[nx][ny].walkable:
                    neighbors.append((nx, ny))
        return neighbors

    def all_neighbors(self, start):
        neighbors = []
        for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
            nx, ny = start[0] + dx, start[1] + dy
            if 0 <= nx < self.width and 0 <= ny < self.height:
                neighbors.append((nx, ny))
        return neighbors

    def start_rain(self, sound_bank):
        self.is_raining = True
        self.rain_duration = self.rng.uniform(8, 14)
        self.rain_timer = self.rain_duration
        sound_bank.play("rain")

    def _populate_tile(self, x, y):
        rng = self.rng
        river_y = self.river_path[x]
        if abs(y - river_y) <= 1:
            self.tiles[x][y].kind = "water"
            return
        roll = rng.random()
        if roll < 0.1:
            self.tiles[x][y].kind = "rock"
            self.tiles[x][y].height = 1
            return
        biome_roll = rng.random()
        if biome_roll < 0.08:
            self.tiles[x][y].kind = "desert"
        elif biome_roll < 0.16:
            self.tiles[x][y].kind = "swamp"
        elif biome_roll < 0.24:
            self.tiles[x][y].kind = "jungle"
        elif biome_roll < 0.32:
            self.tiles[x][y].kind = "snow"

    def _populate_directional_tile(self, x, y, direction):
        river_y = self.river_path[x]
        if abs(y - river_y) <= 1:
            self.tiles[x][y].kind = "water"
            return
        biome = DIR_BIOMES.get(direction, "grass")
        self.tiles[x][y].kind = biome

    def expand_world(self):
        old_width = self.width
        old_height = self.height
        new_width = self.width + 2
        new_height = self.height + 2
        new_tiles = []

        for _ in range(2):
            self.tiles.append([Tile() for _ in range(old_height)])
        last_river = self.river_path[-1] if self.river_path else self.rng.randint(3, old_height - 4)
        for _ in range(2):
            drift = self.rng.choice([-1, 0, 1])
            last_river = max(3, min(old_height - 4, last_river + drift))
            self.river_path.append(last_river)

        for x in range(new_width):
            for _ in range(2):
                self.tiles[x].append(Tile())

        self.width = new_width
        self.height = new_height
        self.river_path = [max(3, min(self.height - 4, y)) for y in self.river_path]

        for x in range(self.width):
            for y in range(self.height):
                if x >= old_width or y >= old_height:
                    if self.tiles[x][y].kind == "grass":
                        if y == 0:
                            self._populate_directional_tile(x, y, "north")
                        elif y == self.height - 1:
                            self._populate_directional_tile(x, y, "south")
                        elif x == 0:
                            self._populate_directional_tile(x, y, "west")
                        elif x == self.width - 1:
                            self._populate_directional_tile(x, y, "east")
                        else:
                            self._populate_tile(x, y)
                    if x >= old_width or y >= old_height:
                        new_tiles.append((x, y))
        self.expansion_count += 1
        if self.expansion_count % 2 == 0:
            self.spawn_enemy_group(new_tiles)

    def spawn_enemy_group(self, new_tiles=None):
        if not new_tiles:
            return
        candidates = [
            pos
            for pos in new_tiles
            if self.tiles[pos[0]][pos[1]].walkable and self.tiles[pos[0]][pos[1]].kind != "water"
        ]
        self.rng.shuffle(candidates)
        for pos in candidates[:3]:
            self.enemies.append(Enemy(pos))

    def find_goal(self, creature):
        if creature.hunger > 0.5:
            return self.find_nearest_fruit((creature.x, creature.y))
        if creature.desire in {"a cozy bench", "a glowing lantern", "a playful ring", "a sparkling fountain"}:
            return self.find_structure(creature.desire)
        if creature.desire == "a skateboard":
            return self.find_structure(creature.desire)
        if creature.desire == "a new friend" and len(self.creatures) > 1:
            friend = random.choice([c for c in self.creatures if c is not creature])
            return (friend.x, friend.y)
        if creature.desire == "a place to explore":
            return self.find_explore_goal(creature)
        return self.find_random_grass()

    def find_structure(self, desire):
        mapping = {
            "a cozy bench": "bench",
            "a glowing lantern": "lantern",
            "a playful ring": "play",
            "a sparkling fountain": "fountain",
            "a skateboard": "skateboard",
        }
        kind = mapping.get(desire)
        if not kind:
            return None
        for x in range(self.width):
            for y in range(self.height):
                tile = self.tiles[x][y]
                if tile.structure == kind:
                    return (x, y)
        return None

    def find_nearest_shelter(self, start):
        best = None
        best_dist = 999
        for x in range(self.width):
            for y in range(self.height):
                tile = self.tiles[x][y]
                if tile.structure == "shelter":
                    dist = abs(x - start[0]) + abs(y - start[1])
                    if dist < best_dist:
                        best_dist = dist
                        best = (x, y)
        return best

    def find_nearest_fruit(self, start):
        best = None
        best_dist = 999
        for x in range(self.width):
            for y in range(self.height):
                tile = self.tiles[x][y]
                if tile.tree and tile.tree.fruits > 0:
                    dist = abs(x - start[0]) + abs(y - start[1])
                    if dist < best_dist:
                        best_dist = dist
                        best = (x, y)
        return best

    def find_random_grass(self):
        for _ in range(60):
            x = random.randint(0, self.width - 1)
            y = random.randint(0, self.height - 1)
            if self.tiles[x][y].walkable:
                return (x, y)
        return None

    def find_path(self, start, goal):
        if not goal:
            return []
        frontier = [start]
        came_from = {start: None}
        while frontier:
            current = frontier.pop(0)
            if current == goal:
                break
            for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
                nx, ny = current[0] + dx, current[1] + dy
                if 0 <= nx < self.width and 0 <= ny < self.height:
                    if not self.tiles[nx][ny].walkable:
                        continue
                    if (nx, ny) not in came_from:
                        frontier.append((nx, ny))
                        came_from[(nx, ny)] = current
        if goal not in came_from:
            return []
        path = []
        current = goal
        while current != start:
            path.append(current)
            current = came_from[current]
        path.reverse()
        return path

    def can_build(self, pos):
        x, y = pos
        tile = self.tiles[x][y]
        return tile.walkable and not tile.structure

    def find_explore_goal(self, creature):
        direction = creature.explore_dir or random.choice(["north", "south", "west", "east"])
        if not self.is_tile_lit((creature.x, creature.y)):
            return None
        if direction == "north":
            return (creature.x, 0)
        if direction == "south":
            return (creature.x, self.height - 1)
        if direction == "west":
            return (0, creature.y)
        return (self.width - 1, creature.y)

    def is_edge_tile(self, pos, direction):
        x, y = pos
        if direction == "north":
            return y == 0
        if direction == "south":
            return y == self.height - 1
        if direction == "west":
            return x == 0
        return x == self.width - 1

    def expand_direction(self, direction):
        new_tiles = []
        if direction in {"north", "south"}:
            for column in self.tiles:
                if direction == "north":
                    column.insert(0, Tile())
                else:
                    column.append(Tile())
            if direction == "north":
                self.river_path = [min(self.height, y + 1) for y in self.river_path]
                for creature in self.creatures:
                    creature.y += 1
                for enemy in self.enemies:
                    enemy.y += 1
            self.height += 1
            for x in range(self.width):
                y = 0 if direction == "north" else self.height - 1
                self._populate_directional_tile(x, y, direction)
                new_tiles.append((x, y))
        else:
            if direction == "west":
                drift = self.rng.choice([-1, 0, 1])
                river_y = max(3, min(self.height - 4, self.river_path[0] + drift))
                self.river_path.insert(0, river_y)
                self.tiles.insert(0, [Tile() for _ in range(self.height)])
                for creature in self.creatures:
                    creature.x += 1
                for enemy in self.enemies:
                    enemy.x += 1
            else:
                drift = self.rng.choice([-1, 0, 1])
                river_y = max(3, min(self.height - 4, self.river_path[-1] + drift))
                self.river_path.append(river_y)
                self.tiles.append([Tile() for _ in range(self.height)])
            self.width += 1
            x = 0 if direction == "west" else self.width - 1
            for y in range(self.height):
                self._populate_directional_tile(x, y, direction)
                new_tiles.append((x, y))
        self.expansion_count += 1
        if self.expansion_count % 2 == 0:
            self.spawn_enemy_group(new_tiles)

    def is_tile_lit(self, pos, radius=6):
        x, y = pos
        min_x = max(0, x - radius)
        max_x = min(self.width - 1, x + radius)
        min_y = max(0, y - radius)
        max_y = min(self.height - 1, y + radius)
        for ix in range(min_x, max_x + 1):
            for iy in range(min_y, max_y + 1):
                if abs(ix - x) + abs(iy - y) > radius:
                    continue
                tile = self.tiles[ix][iy]
                if tile.structure == "lantern":
                    return True
        return False


def iso_to_screen(x, y, height=0, camera=(0, 0)):
    cam_x, cam_y = camera
    sx = (x - y) * TILE_W // 2 + ORIGIN_X + cam_x
    sy = (x + y) * TILE_H // 2 + ORIGIN_Y + cam_y - height * 6
    return sx, sy


def screen_to_iso(world, sx, sy, camera=(0, 0)):
    cam_x, cam_y = camera
    sx -= ORIGIN_X + cam_x
    sy -= ORIGIN_Y + cam_y
    x = (sx / (TILE_W / 2) + sy / (TILE_H / 2)) / 2
    y = (sy / (TILE_H / 2) - sx / (TILE_W / 2)) / 2
    ix, iy = int(round(x)), int(round(y))
    if 0 <= ix < world.width and 0 <= iy < world.height:
        return ix, iy
    return None


def draw_world(screen, world, sprites, selected, hover, font, now, camera):
    global _SHADE_CACHE, _RAIN_CACHE, _WAVE_TILE_CACHE
    if _WAVE_TILE_CACHE is None or _WAVE_TILE_CACHE.get_size() != (TILE_W, TILE_H):
        _WAVE_TILE_CACHE = pygame.Surface((TILE_W, TILE_H), pygame.SRCALPHA)
    if _SHADE_CACHE is None or _SHADE_CACHE.get_size() != (SCREEN_W, SCREEN_H):
        _SHADE_CACHE = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        _SHADE_CACHE.fill((0, 0, 0, 120))
    if _RAIN_CACHE is None or _RAIN_CACHE.get_size() != (SCREEN_W, SCREEN_H):
        _RAIN_CACHE = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
    lantern_visible = False
    for layer in range(world.width + world.height):
        for x in range(world.width):
            y = layer - x
            if 0 <= y < world.height:
                tile = world.tiles[x][y]
                height = tile.height
                base = GRASS
                edge = GRASS_DARK
                if tile.kind == "water":
                    base = WATER
                    edge = WATER_DARK
                if tile.kind == "rock":
                    base = ROCK
                    edge = ROCK_LIGHT
                if tile.kind == "desert":
                    base = DESERT
                    edge = DESERT_DARK
                if tile.kind == "swamp":
                    base = SWAMP
                    edge = SWAMP_DARK
                if tile.kind == "jungle":
                    base = JUNGLE
                    edge = JUNGLE_DARK
                if tile.kind == "snow":
                    base = SNOW
                    edge = SNOW_DARK
                seed = (x * 73856093) ^ (y * 19349663)
                tile_surf = sprites.tile(base, edge, seed)
                sx, sy = iso_to_screen(x, y, height, camera)
                screen.blit(tile_surf, (sx - TILE_W // 2, sy))
                if tile.kind == "water":
                    wave = _WAVE_TILE_CACHE
                    wave.fill((0, 0, 0, 0))
                    offset = int((math.sin(now * 2 + x * 0.6 + y * 0.4) + 1) * 2)
                    pygame.draw.line(wave, (160, 235, 255), (5 + offset, 6), (34, 10), 2)
                    pygame.draw.line(wave, (110, 190, 250), (10, 12), (30, 16), 2)
                    pygame.draw.line(wave, (60, 140, 220), (14, 18), (26, 20), 1)
                    screen.blit(wave, (sx - TILE_W // 2, sy))
                    pygame.draw.line(screen, (90, 170, 240), (sx - 8, sy + 2), (sx + 12, sy + 6), 1)
                if tile.kind == "desert":
                    pygame.draw.line(screen, (230, 205, 150), (sx - 10, sy + 6), (sx + 10, sy + 10), 1)
                    pygame.draw.line(screen, (210, 180, 120), (sx - 6, sy + 12), (sx + 12, sy + 16), 1)
                if tile.kind == "swamp":
                    pygame.draw.circle(screen, (40, 80, 65), (sx - 6, sy + 12), 2)
                    pygame.draw.circle(screen, (50, 95, 70), (sx + 6, sy + 8), 2)
                if tile.kind == "jungle":
                    pygame.draw.line(screen, (60, 170, 110), (sx - 10, sy + 6), (sx - 2, sy + 12), 1)
                    pygame.draw.line(screen, (40, 120, 80), (sx + 4, sy + 6), (sx + 10, sy + 14), 1)
                if tile.kind == "snow":
                    pygame.draw.circle(screen, (245, 250, 255), (sx - 6, sy + 8), 1)
                    pygame.draw.circle(screen, (235, 245, 255), (sx + 6, sy + 12), 1)
                if tile.tree:
                    pygame.draw.ellipse(screen, (18, 40, 26), (sx - 14, sy + 6, 28, 10))
                    tree_surf = sprites.tree(tile.tree.stage)
                    screen.blit(tree_surf, (sx - 16, sy - 26))
                    if tile.tree.fruits > 0:
                        for i in range(tile.tree.fruits):
                            screen.blit(sprites.fruit, (sx - 10 + i * 6, sy - 8))
                if tile.structure:
                    if tile.structure != "bridge":
                        pygame.draw.ellipse(screen, (14, 22, 18), (sx - 16, sy + 6, 32, 10))
                    if tile.structure == "shelter":
                        screen.blit(sprites.structure(tile.structure), (sx - 22, sy - 30))
                    elif tile.structure == "bridge":
                        screen.blit(sprites.structure(tile.structure), (sx - TILE_W // 2, sy))
                    else:
                        screen.blit(sprites.structure(tile.structure), (sx - 20, sy - 26))
                    if tile.structure == "lantern":
                        if -TILE_W <= sx <= SCREEN_W + TILE_W and -TILE_H <= sy <= SCREEN_H + TILE_H:
                            lantern_visible = True
                if tile.kind == "rock":
                    seed = (x * 92837111) ^ (y * 68928731)
                    rng = random.Random(seed)
                    for _ in range(2):
                        rx = sx - 10 + rng.randint(0, 18)
                        ry = sy + 4 + rng.randint(0, 8)
                        pygame.draw.polygon(
                            screen,
                            adjust_color(ROCK_LIGHT, 10, 10, 12),
                            [(rx, ry), (rx + 6, ry - 2), (rx + 10, ry + 4), (rx + 4, ry + 6)],
                        )
    if not lantern_visible:
        screen.blit(_SHADE_CACHE, (0, 0))
    for creature in sorted(world.creatures, key=lambda c: (c.x + c.y, c.y)):
        sx, sy = iso_to_screen(creature.x, creature.y, camera=camera)
        bob = creature.animation_offset()
        frame = creature.animation_frame()
        shadow_width = 24 - min(6, abs(bob))
        pygame.draw.ellipse(
            screen,
            (8, 12, 16),
            (sx - shadow_width // 2, sy + 10, shadow_width, 8),
        )
        if creature.on_skateboard:
            board = pygame.Surface((18, 6), pygame.SRCALPHA)
            pygame.draw.rect(board, (70, 60, 55), (0, 0, 18, 6), border_radius=3)
            pygame.draw.circle(board, (40, 40, 50), (4, 5), 2)
            pygame.draw.circle(board, (40, 40, 50), (14, 5), 2)
            screen.blit(board, (sx - 9, sy + 8))
        screen.blit(
            sprites.creature(creature.tint, creature.appearance, creature.look_dir, creature.anim_state, frame),
            (sx - 15, sy - 24 + bob),
        )
        if creature.message_time > 0:
            label = font.render(creature.message, True, TEXT_COLOR)
            bubble = pygame.Surface((label.get_width() + 12, label.get_height() + 8), pygame.SRCALPHA)
            bubble.fill((20, 24, 30, 200))
            screen.blit(bubble, (sx - bubble.get_width() // 2, sy - 50))
            screen.blit(label, (sx - label.get_width() // 2, sy - 46))
            creature.message_time -= 1 / FPS
    for enemy in sorted(world.enemies, key=lambda e: (e.x + e.y, e.y)):
        sx, sy = iso_to_screen(enemy.x, enemy.y, camera=camera)
        pygame.draw.ellipse(screen, (10, 12, 16), (sx - 12, sy + 10, 24, 8))
        pygame.draw.circle(screen, (200, 40, 40), (sx, sy - 4), 10)
        pygame.draw.circle(screen, (150, 20, 20), (sx - 4, sy - 2), 5)
        pygame.draw.circle(screen, (255, 220, 220), (sx - 3, sy - 6), 2)
        pygame.draw.circle(screen, (255, 220, 220), (sx + 3, sy - 6), 2)
        pygame.draw.circle(screen, (30, 10, 10), (sx - 3, sy - 6), 1)
        pygame.draw.circle(screen, (30, 10, 10), (sx + 3, sy - 6), 1)
    if world.is_raining:
        rain = _RAIN_CACHE
        rain.fill((0, 0, 0, 0))
        rng = random.Random(int(now * 10))
        for _ in range(120):
            rx = rng.randint(0, SCREEN_W - 1)
            ry = rng.randint(0, SCREEN_H - 1)
            pygame.draw.line(rain, (150, 180, 220, 120), (rx, ry), (rx + 2, ry + 6), 1)
        screen.blit(rain, (0, 0))
    if hover:
        hx, hy = hover
        sx, sy = iso_to_screen(hx, hy, camera=camera)
        points = [
            (sx, sy + 1),
            (sx + TILE_W // 2, sy + TILE_H // 2),
            (sx, sy + TILE_H),
            (sx - TILE_W // 2, sy + TILE_H // 2),
        ]
        pygame.draw.polygon(screen, (255, 255, 255), points, 1)
    if selected:
        sx, sy = iso_to_screen(selected.x, selected.y, camera=camera)
        pygame.draw.circle(screen, (255, 235, 140), (sx, sy + 10), 18, 2)


def draw_ui(screen, world, selected, build_mode, font, small_font):    # --- Observer Tools panel (auto-sized so all options fit cleanly) ---
    panel_x, panel_y = 16, 16
    text_x = 30
    title_y = 24
    options_y0 = 60
    option_step = 24
    left_pad = text_x - panel_x
    right_pad = 14
    bottom_pad = 16

    title_text = "Observer Tools"
    hint_text = "Right click: select"
    prop_text = f"Props {world.prop_count}/{world.prop_limit}"

    max_w = font.size(title_text)[0]
    for i, (label, _) in enumerate(BUILD_MODES):
        max_w = max(max_w, small_font.size(f"{i+1}. {label}")[0])
    max_w = max(max_w, small_font.size(hint_text)[0], small_font.size(prop_text)[0])

    panel_w = max(210, left_pad + max_w + right_pad)

    hint_y = options_y0 + len(BUILD_MODES) * option_step
    prop_y = hint_y + 18
    panel_h = max(274, (prop_y + small_font.get_height() + bottom_pad) - panel_y)

    panel = pygame.Rect(panel_x, panel_y, panel_w, panel_h)
    pygame.draw.rect(screen, UI_BG, panel, border_radius=10)
    pygame.draw.rect(screen, UI_ACCENT, panel, 2, border_radius=10)

    title = font.render(title_text, True, TEXT_COLOR)
    screen.blit(title, (text_x, title_y))
    for i, (label, _) in enumerate(BUILD_MODES):
        y = options_y0 + i * option_step
        active = build_mode == i
        color = UI_ACCENT if active else TEXT_COLOR
        line = small_font.render(f"{i+1}. {label}", True, color)
        screen.blit(line, (text_x, y))

    hint = small_font.render(hint_text, True, (180, 190, 200))
    screen.blit(hint, (text_x, hint_y))
    prop_line = small_font.render(prop_text, True, (200, 210, 220))
    screen.blit(prop_line, (text_x, prop_y))

    info_panel = pygame.Rect(SCREEN_W - 260, 16, 240, 150)
    pygame.draw.rect(screen, UI_PANEL, info_panel, border_radius=10)
    if selected:
        name = font.render(selected.name, True, UI_ACCENT)
        screen.blit(name, (SCREEN_W - 240, 24))
        traits = ", ".join(sorted(selected.personality, key=selected.personality.get, reverse=True)[:2])
        screen.blit(small_font.render(f"Traits: {traits}", True, TEXT_COLOR), (SCREEN_W - 240, 54))
        screen.blit(small_font.render(f"Hunger: {selected.hunger:.2f}", True, TEXT_COLOR), (SCREEN_W - 240, 74))
        screen.blit(small_font.render(f"Happiness: {selected.happiness:.2f}", True, TEXT_COLOR), (SCREEN_W - 240, 92))
        screen.blit(small_font.render("Desire:", True, TEXT_COLOR), (SCREEN_W - 240, 110))
        screen.blit(small_font.render(selected.desire, True, UI_ACCENT), (SCREEN_W - 240, 128))
        screen.blit(small_font.render("Press G to grant", True, (200, 210, 220)), (SCREEN_W - 240, 146))
    else:
        screen.blit(font.render("No greeble", True, (120, 130, 150)), (SCREEN_W - 240, 74))

    note_panel = pygame.Rect(SCREEN_W - 260, 176, 240, 90)
    pygame.draw.rect(screen, UI_PANEL, note_panel, border_radius=10)
    note_title = font.render("World Echo", True, UI_ACCENT)
    screen.blit(note_title, (SCREEN_W - 240, 184))
    for i, (msg, _) in enumerate(world.notifications[-3:]):
        screen.blit(small_font.render(msg, True, TEXT_COLOR), (SCREEN_W - 240, 212 + i * 18))
    if world.is_raining:
        screen.blit(
            small_font.render("Rainfall", True, UI_ACCENT),
            (SCREEN_W - 240, 212 + len(world.notifications[-3:]) * 18),
        )



def draw_quit_prompt(screen, font, small_font, remaining_ms):
    # Simple confirmation: ESC arms quit, second ESC exits.
    # remaining_ms controls optional timeout display.
    title = "Exit game?"
    line1 = "Press ESC again to quit."
    line2 = "Press any other key to cancel."

    title_surf = font.render(title, True, TEXT_COLOR)
    l1 = small_font.render(line1, True, TEXT_COLOR)
    l2 = small_font.render(line2, True, (200, 210, 220))

    pad_x = 22
    pad_y = 18
    gap = 10

    content_w = max(title_surf.get_width(), l1.get_width(), l2.get_width())
    content_h = title_surf.get_height() + gap + l1.get_height() + 6 + l2.get_height()

    panel_w = content_w + pad_x * 2
    panel_h = content_h + pad_y * 2

    rect = pygame.Rect(0, 0, panel_w, panel_h)
    rect.center = (SCREEN_W // 2, SCREEN_H // 2)

    pygame.draw.rect(screen, (12, 14, 18), rect, border_radius=14)
    pygame.draw.rect(screen, UI_ACCENT, rect, 2, border_radius=14)

    x = rect.x + pad_x
    y = rect.y + pad_y

    screen.blit(title_surf, (x + (content_w - title_surf.get_width()) // 2, y))
    y += title_surf.get_height() + gap
    screen.blit(l1, (x + (content_w - l1.get_width()) // 2, y))
    y += l1.get_height() + 6
    screen.blit(l2, (x + (content_w - l2.get_width()) // 2, y))

def menu_item_rects():
    rects = []
    for i in range(len(BUILD_MODES)):
        y = 60 + i * 24
        rects.append(pygame.Rect(28, y - 2, 180, 20))
    return rects


def main():
    pygame.init()

    # --- Windowing / scaling setup (fixed virtual resolution) ---
    # Start in borderless fullscreen-windowed (no monitor mode switch).
    info = pygame.display.Info()
    desktop_size = (max(1, info.current_w), max(1, info.current_h))

    windowed_size = (SCREEN_W, SCREEN_H)  # 1920x1080 default windowed size
    flags_windowed = pygame.RESIZABLE | pygame.DOUBLEBUF
    flags_borderless = pygame.NOFRAME | pygame.DOUBLEBUF

    is_borderless = True
    display = pygame.display.set_mode(desktop_size, flags_borderless, vsync=1)
    pygame.display.set_caption("Isometric Greatures")

    # Virtual render target (never changes size).
    screen = pygame.Surface((SCREEN_W, SCREEN_H))

    clock = pygame.time.Clock()
    font = pygame.font.SysFont("trebuchetms", 16, bold=True)
    small_font = pygame.font.SysFont("trebuchetms", 13)

    sprites = SpriteFactory()
    sound_bank = SoundBank()
    world = World(sprites)
    world.spawn_creature((world.width // 2, world.height // 2))

    sky = build_gradient(SCREEN_W, SCREEN_H, SKY, SKY_LIGHT)

    build_mode = 0
    selected = world.creatures[0] if world.creatures else None
    hover_tile = None
    camera = [0.0, 0.0]

    if selected:
        sx, sy = iso_to_screen(selected.x, selected.y, camera=(0, 0))
        camera[0] = SCREEN_W // 2 - sx
        camera[1] = SCREEN_H // 2 - sy

    running = True
    quit_confirm = False
    quit_confirm_until = 0
    QUIT_CONFIRM_MS = 2500
    while running:
        dt = clock.tick(FPS) / 1000.0

        # Compute current viewport for input mapping (window -> virtual).
        win_w, win_h = display.get_size()
        view_scale, view_rect = compute_viewport(win_w, win_h)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            elif event.type == pygame.VIDEORESIZE and not is_borderless:
                # Resize the *window* only; virtual resolution stays fixed.
                windowed_size = (max(1, event.w), max(1, event.h))
                display = pygame.display.set_mode(windowed_size, flags_windowed, vsync=1)

            elif event.type == pygame.KEYDOWN:
                now_ms = pygame.time.get_ticks()
                if event.key == pygame.K_ESCAPE:
                    if quit_confirm and now_ms <= quit_confirm_until:
                        running = False
                    else:
                        quit_confirm = True
                        quit_confirm_until = now_ms + QUIT_CONFIRM_MS
                    continue
                else:
                    # Any other key cancels the pending quit.
                    if quit_confirm:
                        quit_confirm = False

                # Build mode hotkeys
                if event.key in (
                    pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4, pygame.K_5,
                    pygame.K_6, pygame.K_7, pygame.K_8, pygame.K_9,
                ):
                    build_mode = event.key - pygame.K_1

                # Cycle selected creature
                if event.key == pygame.K_TAB:
                    if world.creatures:
                        if selected in world.creatures:
                            idx = world.creatures.index(selected)
                            selected = world.creatures[(idx + 1) % len(world.creatures)]
                        else:
                            selected = world.creatures[0]
                        sx, sy = iso_to_screen(selected.x, selected.y, camera=(0, 0))
                        camera[0] = SCREEN_W // 2 - sx
                        camera[1] = SCREEN_H // 2 - sy

                # Toggle fullscreen-windowed (borderless) <-> resizable windowed
                if event.key == pygame.K_F11 or (
                    event.key == pygame.K_RETURN and (event.mod & pygame.KMOD_ALT)
                ):
                    is_borderless = not is_borderless
                    if is_borderless:
                        # Borderless fullscreen-windowed (desktop resolution)
                        info = pygame.display.Info()
                        desktop_size = (max(1, info.current_w), max(1, info.current_h))
                        display = pygame.display.set_mode(desktop_size, flags_borderless, vsync=1)
                    else:
                        display = pygame.display.set_mode(windowed_size, flags_windowed, vsync=1)

                    # Refresh viewport mapping immediately after mode switch
                    win_w, win_h = display.get_size()
                    view_scale, view_rect = compute_viewport(win_w, win_h)

                if event.key == pygame.K_g and selected:
                    grant_desire(world, selected, sound_bank)

            elif event.type == pygame.MOUSEBUTTONDOWN:
                if quit_confirm:
                    quit_confirm = False
                # Map click to virtual coordinates (ignore black bars).
                mouse_v = window_to_virtual(event.pos, view_scale, view_rect)
                if mouse_v is None:
                    continue
                vx, vy = mouse_v
                vpos = (int(vx), int(vy))

                hover_for_click = screen_to_iso(world, vx, vy, camera)

                if event.button == 1:
                    ui_clicked = False
                    for idx, rect in enumerate(menu_item_rects()):
                        if rect.collidepoint(vpos):
                            build_mode = idx
                            ui_clicked = True
                            break
                    if hover_for_click and not ui_clicked:
                        apply_build(world, hover_for_click, build_mode, sound_bank)

                if event.button == 3:
                    if hover_for_click and remove_prop(world, hover_for_click):
                        selected = None
                    else:
                        selected = select_creature(world, hover_for_click)

        now_ms = pygame.time.get_ticks()
        if quit_confirm and now_ms > quit_confirm_until:
            quit_confirm = False

        keys = pygame.key.get_pressed()
        if keys[pygame.K_a]:
            camera[0] += CAMERA_SPEED * dt
        if keys[pygame.K_d]:
            camera[0] -= CAMERA_SPEED * dt
        if keys[pygame.K_w]:
            camera[1] += CAMERA_SPEED * dt
        if keys[pygame.K_s]:
            camera[1] -= CAMERA_SPEED * dt

        # Hover mapping (window -> virtual -> tile)
        mouse_v = window_to_virtual(pygame.mouse.get_pos(), view_scale, view_rect)
        if mouse_v is None:
            hover_tile = None
        else:
            mx_v, my_v = mouse_v
            hover_tile = screen_to_iso(world, mx_v, my_v, camera)

        world.update(dt, sound_bank)

        # --- Render to virtual surface ---
        screen.blit(sky, (0, 0))
        draw_world(screen, world, sprites, selected, hover_tile, small_font, pygame.time.get_ticks() / 1000.0, camera)
        draw_ui(screen, world, selected, build_mode, font, small_font)
        if quit_confirm:
            remaining = max(0, quit_confirm_until - pygame.time.get_ticks())
            draw_quit_prompt(screen, font, small_font, remaining)

        # --- Present scaled to window with letterbox/pillarbox ---
        display.fill((0, 0, 0))
        frame = pygame.transform.scale(screen, (view_rect.w, view_rect.h))
        display.blit(frame, (view_rect.x, view_rect.y))
        pygame.display.flip()

    pygame.quit()


def apply_build(world, tile_pos, build_mode, sound_bank):
    x, y = tile_pos
    tile = world.tiles[x][y]
    label, kind = BUILD_MODES[build_mode]
    if kind != "bridge" and world.prop_count >= world.prop_limit:
        world.notifications.append(("Prop limit reached", 2.5))
        return
    if kind == "tree":
        if tile.kind == "grass" and tile.tree is None:
            tile.tree = Tree()
            sound_bank.play("plant")
            world.prop_count += 1
    elif kind == "bridge":
        if tile.kind == "water" and tile.structure is None:
            tile.structure = kind
            sound_bank.play("plant")
    else:
        if world.can_build(tile_pos):
            tile.structure = kind
            sound_bank.play("plant")
            world.prop_count += 1


def remove_prop(world, tile_pos):
    x, y = tile_pos
    tile = world.tiles[x][y]
    if tile.tree:
        tile.tree = None
        world.prop_count = max(0, world.prop_count - 1)
        return True
    if tile.structure:
        if tile.structure != "bridge":
            world.prop_count = max(0, world.prop_count - 1)
        tile.structure = None
        return True
    return False


def select_creature(world, tile_pos):
    if not tile_pos:
        return None
    for creature in world.creatures:
        if (creature.x, creature.y) == tile_pos:
            return creature
    return None


def grant_desire(world, creature, sound_bank):
    desire = creature.desire
    if desire == "a new friend":
        now = time.time()
        if now - world.last_friend_grant < 60:
            remaining = int(max(0, 60 - (now - world.last_friend_grant)))
            world.notifications.append((f"Friend grant cooling down ({remaining}s).", 2.5))
            return
    if desire != "a new friend" and world.prop_count >= world.prop_limit:
        world.notifications.append(("Prop limit reached", 2.5))
        return
    if desire == "a tree to snack from":
        pos = world.find_random_grass()
        if pos:
            world.tiles[pos[0]][pos[1]].tree = Tree()
            world.prop_count += 1
    elif desire == "a cozy bench":
        place_structure(world, "bench")
    elif desire == "a glowing lantern":
        place_structure(world, "lantern")
    elif desire == "a playful ring":
        place_structure(world, "play")
    elif desire == "a sparkling fountain":
        place_structure(world, "fountain")
    elif desire == "a skateboard":
        place_structure(world, "skateboard")
    elif desire == "a new friend":
        world.spawn_creature((creature.x, creature.y))
        world.last_friend_grant = time.time()
        creature.set_satisfied(60)
        world.expand_direction("north")
        world.expand_direction("south")
        world.expand_direction("west")
        world.expand_direction("east")
    elif desire == "a place to explore":
        world.expand_direction("north")
        world.expand_direction("north")
        creature.message = "New land to explore!"
        creature.message_time = 2
        creature.set_satisfied(30)
    else:
        place_structure(world, "bench")
    bonus = 0.2
    if world.mourning:
        bonus = 0.35
        world.mourning = False
        world.notifications.append(("The gifts lifted our spirits.", 2.5))
    creature.happiness = min(1.0, creature.happiness + bonus)
    creature.message = "Your wish is granted!"
    creature.message_time = 2
    sound_bank.play("happy")


def place_structure(world, kind):
    for _ in range(40):
        pos = world.find_random_grass()
        if pos and world.can_build(pos):
            world.tiles[pos[0]][pos[1]].structure = kind
            world.prop_count += 1
            return


if __name__ == "__main__":
    install_crash_reporter()
    try:
        main()
    except Exception:
        log_crash(*sys.exc_info())
        raise
