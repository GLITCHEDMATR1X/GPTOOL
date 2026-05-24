#!/usr/bin/env python3
"""
Regions at War (Prototype) - single-file Pygame world simulation

This is an RTS-style evolution of the earlier Colonies & Collapse prototype:
- Every WORLD "region" is an AI-controlled faction (RTS macro-sim).
- Factions build over time; buildings enable faster troop recruitment.
- Factions only attempt expansion (invasion) when they have sufficient troop surplus.
- When a faction captures and destroys a region's Capital, the entire region flips to
  the winner's color/name (region control transfers to the winner).
- The "Area View" still uses the same procedural building structures and their damaged
  counterparts; region styles introduce terrain + architectural variation.

Controls:
- Left Click: open Area View at clicked location (world map)
- Right Click: inspect tile (no mode change)
- SPACE: pause/unpause simulation
- [ and ]: decrease/increase speed
- ESC: back (from Area View) / quit (from world view)
- R: restart world

Requirements:
- Python 3.10+
- pygame (pip install pygame)
"""

from __future__ import annotations

import math
import random
import hashlib
import os
import sys
import subprocess
import socket
import time
import traceback
import contextlib
import inspect
import importlib.util
import textwrap
from dataclasses import dataclass, field
from collections import deque, defaultdict
from typing import Dict, List, Optional, Tuple, Set

import pygame



def _doomsday_find_music_mp3(root: str) -> Optional[str]:
    try:
        if not os.path.isdir(root):
            return None
        hits = []
        for base, _, files in os.walk(root):
            for fn in files:
                if fn.lower().endswith(('.mp3', '.wav', '.ogg')):
                    hits.append(os.path.join(base, fn))
        if not hits:
            return None
        hits.sort(key=lambda x: x.lower())
        return hits[0]
    except Exception:
        return None



def _doomsday_write_placeholder_wav(path: str, frequency: float = 84.0, duration: float = 1.0, volume: float = 0.12) -> None:
    try:
        import wave, struct
        os.makedirs(os.path.dirname(path), exist_ok=True)
        sr = 22050
        total = max(1, int(sr * duration))
        with wave.open(path, 'w') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sr)
            for i in range(total):
                t = i / sr
                env = 0.75 + 0.25 * math.sin(2.0 * math.pi * 0.75 * t)
                s = math.sin(2.0 * math.pi * frequency * t)
                wf.writeframes(struct.pack('<h', int(32767 * volume * env * s)))
    except Exception:
        pass


def _doomsday_ensure_map_audio() -> None:
    try:
        os.makedirs(DOOMSDAY_SOUNDS_DIR, exist_ok=True)
        if _doomsday_find_music_mp3(DOOMSDAY_SOUNDS_DIR) is None:
            _doomsday_write_placeholder_wav(os.path.join(DOOMSDAY_SOUNDS_DIR, 'map_loop.wav'))
    except Exception:
        pass


def _doomsday_play_map_music(volume: float = 0.55) -> None:
    try:
        if not pygame.mixer.get_init():
            pygame.mixer.init()
        mp3 = _doomsday_find_music_mp3(DOOMSDAY_SOUNDS_DIR)
        if not mp3:
            return
        cur = None
        try:
            cur = pygame.mixer.music.get_busy()
        except Exception:
            cur = None
        # Always (re)load when called; safe for testing.
        pygame.mixer.music.load(mp3)
        pygame.mixer.music.set_volume(max(0.0, min(1.0, volume)))
        pygame.mixer.music.play(-1)
    except Exception:
        pass


def _doomsday_stop_all_audio() -> None:
    try:
        if pygame.mixer.get_init():
            try:
                pygame.mixer.music.stop()
            except Exception:
                pass
            try:
                pygame.mixer.stop()
            except Exception:
                pass
    except Exception:
        pass


# ----------------------------
# Config
# ----------------------------

WORLD_W = 96
WORLD_H = 64
TILE = 10

WORLD_PX_W = WORLD_W * TILE   # 960
WORLD_PX_H = WORLD_H * TILE   # 640

UI_W = 320

CANVAS_W = 1280
CANVAS_H = 720

WORLD_X = 0
WORLD_Y = 40  # center vertically (720-640=80)
WORLD_RECT = pygame.Rect(WORLD_X, WORLD_Y, WORLD_PX_W, WORLD_PX_H)

UI_X = WORLD_PX_W
UI_Y = 0
UI_RECT = pygame.Rect(UI_X, UI_Y, UI_W, CANVAS_H)

FPS = 60
TICK_SECONDS = 0.25  # simulation step length at 1x

SPEED_LEVELS = [0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 25.0, 50.0, 100.0]

REGION_COUNT = 18
NEWS_LINES = 14
MODE_SESSION_SECONDS = 120.0


OVERLAY_ALPHA = 115
BORDER_COLOR = (20, 20, 20)

# Doomsday hub audio (for later SFX + a single looping map track)
DOOMSDAY_ASSETS_DIR = os.path.join(os.path.dirname(__file__), 'assets')
DOOMSDAY_SOUNDS_DIR = os.path.join(DOOMSDAY_ASSETS_DIR, 'sounds')

# ----------------------------
# Holographic UI Theme
# ----------------------------

HOLO_BG = (10, 8, 7)
HOLO_BG_2 = (15, 11, 9)
HOLO_PANEL = (23, 17, 14)
HOLO_ACCENT = (166, 115, 74)
HOLO_ACCENT_2 = (118, 84, 56)
HOLO_TEXT = (228, 214, 191)
HOLO_TEXT_DIM = (158, 142, 121)
HOLO_WARN = (208, 96, 70)

# Army camouflage palette for region/faction colors (muted, readable)
CAMO_BASE_COLORS: List[Tuple[int,int,int]] = [
    (35, 45, 35),   # deep forest
    (52, 69, 49),   # ranger green
    (74, 82, 54),   # olive drab
    (92, 102, 70),  # faded olive
    (64, 76, 66),   # foliage
    (85, 92, 78),   # sage
    (110, 112, 90), # drab khaki
    (124, 116, 86), # tan
    (140, 132, 96), # sand
    (96, 78, 56),   # earth brown
    (114, 90, 60),  # coyote
    (86, 64, 48),   # mud
    (72, 58, 44),   # dark mud
    (58, 54, 42),   # charcoal dirt
    (48, 60, 50),   # gray-green
    (66, 80, 58),   # moss
    (78, 72, 56),   # field khaki
    (98, 92, 72),   # dust
    (108, 98, 74),  # light coyote
    (56, 70, 46),   # woodland
    (70, 88, 60),   # muted green
    (88, 86, 62),   # dry grass
    (104, 84, 58),  # brown sand
    (60, 66, 54),   # slate olive
]

def camo_variant(base: Tuple[int,int,int], rng: random.Random) -> Tuple[int,int,int]:
    """Return a slightly varied camouflage shade for uniqueness while staying muted."""
    # Small brightness and channel jitter; keep within army palette feel.
    k = 0.88 + rng.random() * 0.28  # 0.88..1.16
    j = lambda: rng.randint(-8, 8)
    r = int(clamp(base[0] * k + j(), 0, 255))
    g = int(clamp(base[1] * k + j(), 0, 255))
    b = int(clamp(base[2] * k + j(), 0, 255))
    # Prevent overly saturated / bright outliers
    r = int(clamp(r, 22, 170))
    g = int(clamp(g, 22, 170))
    b = int(clamp(b, 22, 170))
    return (r, g, b)

# RTS economy / war tuning (lightweight)
RES_CAP = 9999.0

BUILD_MIN_DELAY = 80  # ticks (slower macro construction)
BUILD_MAX_DELAY = 200  # ticks (slower macro construction)

CAPITAL_HP_MAX = 420.0
CAPITAL_REGEN = 0.35  # per tick when not sieged

# How much troop surplus is needed before an invasion is attempted
INVASION_BASE_THRESHOLD = 80.0
INVASION_PER_REGION_THRESHOLD = 26.0  # per controlled region

# Frontline capture params
FRONTLINE_STEPS_BASE = 3
FRONTLINE_STEPS_SCALE = 0.03  # steps per troop
CAPTURE_P_BASE = 0.22

RUINS_DECAY = 0.0009  # per tick


# ----------------------------
# Utilities
# ----------------------------

def clamp(x: float, a: float, b: float) -> float:
    return a if x < a else b if x > b else x

def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t

def hsv_to_rgb(h: float, s: float, v: float) -> Tuple[int, int, int]:
    i = int(h * 6.0)
    f = (h * 6.0) - i
    p = v * (1.0 - s)
    q = v * (1.0 - f * s)
    t = v * (1.0 - (1.0 - f) * s)
    i = i % 6
    if i == 0: r, g, b = v, t, p
    elif i == 1: r, g, b = q, v, p
    elif i == 2: r, g, b = p, v, t
    elif i == 3: r, g, b = p, q, v
    elif i == 4: r, g, b = t, p, v
    else: r, g, b = v, p, q
    return (int(r * 255), int(g * 255), int(b * 255))

def grid_neighbors(x: int, y: int, w: int, h: int):
    if x > 0: yield x - 1, y
    if x < w - 1: yield x + 1, y
    if y > 0: yield x, y - 1
    if y < h - 1: yield x, y + 1

def cell_to_px_world(x: int, y: int) -> Tuple[int, int]:
    return WORLD_X + x * TILE, WORLD_Y + y * TILE

def px_to_cell_world(px: int, py: int) -> Tuple[int, int]:
    return (px - WORLD_X) // TILE, (py - WORLD_Y) // TILE

def draw_text(surface: pygame.Surface, font: pygame.font.Font, text: str, x: int, y: int,
              color=(240, 240, 240), shadow: bool = True,
              shadow_col: Tuple[int,int,int] = (0, 0, 0),
              shadow_off: Tuple[int,int] = (1, 1)) -> int:
    """Draw readable text with a subtle shadow; returns next y cursor."""
    if text is None:
        return y
    if shadow:
        try:
            sh = font.render(text, True, shadow_col)
            surface.blit(sh, (x + int(shadow_off[0]), y + int(shadow_off[1])))
        except Exception:
            pass
    img = font.render(text, True, color)
    surface.blit(img, (x, y))
    return y + img.get_height() + 2



def wrap_text_lines(font: pygame.font.Font, text: str, max_width: int) -> List[str]:
    if not text:
        return ['']
    words = str(text).split()
    if not words:
        return ['']
    lines = []
    cur = words[0]
    for word in words[1:]:
        trial = cur + ' ' + word
        if font.size(trial)[0] <= max_width:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    lines.append(cur)
    return lines

def rand_color_distinct(rng: random.Random) -> Tuple[int, int, int]:
    while True:
        r = rng.randint(40, 235)
        g = rng.randint(40, 235)
        b = rng.randint(40, 235)
        if abs(r - g) + abs(g - b) + abs(b - r) > 80:
            return (r, g, b)

def pick_weighted(rng: random.Random, items: List[Tuple[str, float]]) -> str:
    total = sum(w for _, w in items)
    r = rng.random() * total
    acc = 0.0
    for val, w in items:
        acc += w
        if r <= acc:
            return val
    return items[-1][0]

def _stable_hash32(s: str) -> int:
    h = 2166136261
    for ch in s.encode("utf-8"):
        h ^= ch
        h = (h * 16777619) & 0xFFFFFFFF
    return h

def _mul_color(col: Tuple[int, int, int], k: float) -> Tuple[int, int, int]:
    return (int(clamp(col[0] * k, 0, 255)),
            int(clamp(col[1] * k, 0, 255)),
            int(clamp(col[2] * k, 0, 255)))

def _add_color(col: Tuple[int, int, int], add: int) -> Tuple[int, int, int]:
    return (int(clamp(col[0] + add, 0, 255)),
            int(clamp(col[1] + add, 0, 255)),
            int(clamp(col[2] + add, 0, 255)))

def _chamfer_points(w: int, h: int, r: int) -> List[Tuple[int, int]]:
    r = max(1, min(r, min(w, h)//3))
    return [(r, 0), (w-r-1, 0), (w-1, r),
            (w-1, h-r-1), (w-r-1, h-1), (r, h-1),
            (0, h-r-1), (0, r)]

def dist_manh(a: Tuple[int,int], b: Tuple[int,int]) -> int:
    return abs(a[0]-b[0]) + abs(a[1]-b[1])

def deterministic_seed(world_seed: int, *parts) -> int:
    """Deterministic RNG seed helper (varargs)."""
    h = hashlib.blake2b(digest_size=8)
    h.update(str(int(world_seed)).encode('utf-8'))
    for p in parts:
        h.update(b'|')
        h.update(str(p).encode('utf-8'))
    return int.from_bytes(h.digest(), 'little') & 0xFFFFFFFF


# ----------------------------
# Procedural names
# ----------------------------

SYL_A = ["Au", "Ve", "Brine", "Cin", "Thorn", "Sun", "Iron", "Mor", "Hal", "Ob", "Kes", "Rift", "Azu", "Gild", "Frost", "Red", "Sil", "Ward", "Ebon", "Lumen", "Ash", "Sable", "Vara", "Nyx", "Orin", "Kara"]
SYL_B = ["el", "yl", "hold", "der", "wold", "spire", "vale", "row", "cyon", "sid", "trel", "stone", "step", "basin", "wake", "harbor", "auric", "steppe", "marsh", "crest", "reach", "fen", "gate", "strand", "cairn"]
SYL_C = ["Marches", "Dominion", "Compact", "Syndicate", "Covenant", "League", "Protectorate", "Republic", "Reach", "Throne", "Enclave", "Bannerlands", "Consortium", "Concord", "Principality", "Clans", "Order", "Union", "Pact", "Assembly"]

def gen_region_name(rng: random.Random) -> str:
    a = rng.choice(SYL_A)
    b = rng.choice(SYL_B)
    c = rng.choice(SYL_C)
    if a.lower().endswith(b.lower()):
        b = rng.choice(SYL_B)
    return f"{a}{b} {c}"


# ----------------------------
# Data structures
# ----------------------------

@dataclass
class Building:
    kind: str
    gx: int
    gy: int
    tw: int = 2
    th: int = 2
    variant: int = 0
    roof: int = 0

    started: bool = False
    progress: float = 0.0
    build_rate: float = 0.0009

    damage: float = 0.0
    destroyed: bool = False
    burn: float = 0.0  # smoke intensity

@dataclass
class LocalMap:
    seed: int
    theme: str
    style: str
    terrain: List[List[int]]  # 0 water, 1 land
    buildings: List[Building] = field(default_factory=list)
    fx: List[Tuple[float,float,float]] = field(default_factory=list)  # (x,y,life)

@dataclass
class ExplosionFX:
    x: float
    y: float
    radius: float = 2.0
    max_radius: float = 26.0
    life: float = 0.0
    max_life: float = 0.45
    intensity: float = 1.0

    def update(self, dt: float) -> bool:
        self.life += dt
        t = clamp(self.life / self.max_life, 0.0, 1.0)
        self.radius = lerp(2.0, self.max_radius, t)
        return self.life < self.max_life

    def draw(self, surface: pygame.Surface):
        t = clamp(self.life / self.max_life, 0.0, 1.0)
        alpha = int(255 * (1.0 - t))
        col = (255, 210, 120, alpha)
        ring = pygame.Surface((int(self.radius*2+4), int(self.radius*2+4)), pygame.SRCALPHA)
        pygame.draw.circle(ring, col, (ring.get_width()//2, ring.get_height()//2), int(self.radius), 2)
        surface.blit(ring, (self.x - ring.get_width()/2, self.y - ring.get_height()/2))


# ----------------------------
# Air Combat Overlay (TAB)
# ----------------------------

AIR_BULLET_SPEED = 980.0
AIR_BULLET_LIFE = 0.55
AIR_BULLET_DMG = 7.0
AIR_GUN_FIRE_RATE = 14.0  # bullets / second

AIR_ROCKET_SPEED = 340.0
AIR_ROCKET_TURN = 6.0     # radians/sec (homing strength)
AIR_ROCKET_LIFE = 3.2
AIR_ROCKET_DMG = 70.0
AIR_ROCKET_SPLASH = 56.0
AIR_ROCKET_COOLDOWN = 1.35
AIR_JET_SFX_VOLUME = 0.12  # intentionally low


AIR_JET_MAX_HP = 140.0
AIR_JET_THRUST = 520.0
AIR_JET_MAX_SPEED = 320.0
AIR_JET_DAMPING = 3.0

AIR_SHOCKWAVE_MAX_R = 22.0

@dataclass
class AirShockwaveFX:
    x: float
    y: float
    life: float = 0.0
    max_life: float = 0.36
    r: float = 2.0
    max_r: float = AIR_SHOCKWAVE_MAX_R

    def update(self, dt: float) -> bool:
        self.life += dt
        t = clamp(self.life / self.max_life, 0.0, 1.0)
        self.r = lerp(2.0, self.max_r, t)
        return self.life < self.max_life

    def draw(self, surf: pygame.Surface):
        t = clamp(self.life / self.max_life, 0.0, 1.0)
        a = int(220 * (1.0 - t))
        col = (255, 80, 80, a)
        ring = pygame.Surface((int(self.r * 2 + 6), int(self.r * 2 + 6)), pygame.SRCALPHA)
        # filled pulse
        fill_a = int(a * 0.22)
        pygame.draw.circle(ring, (255, 80, 80, fill_a), (ring.get_width() // 2, ring.get_height() // 2), max(1, int(self.r * 0.65)))
        pygame.draw.circle(ring, col, (ring.get_width() // 2, ring.get_height() // 2), int(self.r), 2)
        surf.blit(ring, (self.x - ring.get_width() / 2, self.y - ring.get_height() / 2))


@dataclass
class AirTracer:
    pos: pygame.Vector2
    vel: pygame.Vector2
    team: int
    life: float = 0.0
    max_life: float = AIR_BULLET_LIFE

    def update(self, dt: float) -> bool:
        self.life += dt
        self.pos += self.vel * dt
        return self.life < self.max_life
    def draw(self, surf: pygame.Surface):
        # Render as red broken/dashed tracer streak (laser->tracer look).
        v = self.vel
        sp = v.length()
        if sp < 1e-3:
            return
        n = v / sp

        total = 18.0
        dash = 4.0
        gap = 3.0
        a = int(220 * (1.0 - clamp(self.life / self.max_life, 0.0, 1.0)))
        col = (255, 0, 0, a)

        start = self.pos - n * total
        cur = pygame.Vector2(start)
        remaining = total
        while remaining > 0.0:
            seg = min(dash, remaining)
            p0 = cur
            p1 = cur + n * seg
            pygame.draw.line(surf, col, (p0.x, p0.y), (p1.x, p1.y), 2)
            cur = p1 + n * gap
            remaining -= (seg + gap)


@dataclass
class AirRocket:
    pos: pygame.Vector2
    vel: pygame.Vector2
    team: int
    target_team: Optional[int] = None
    life: float = 0.0
    max_life: float = AIR_ROCKET_LIFE

    def update(self, dt: float, get_target_pos) -> bool:
        self.life += dt
        tgt = get_target_pos(self.team, self.target_team)
        if tgt is not None:
            desired = (tgt - self.pos)
            if desired.length_squared() > 1e-6:
                desired = desired.normalize() * AIR_ROCKET_SPEED
                # Steering: rotate current velocity toward desired.
                cur = self.vel
                if cur.length_squared() < 1e-6:
                    self.vel = desired
                else:
                    cur_n = cur.normalize()
                    des_n = desired.normalize()
                    # Signed angle
                    ang = math.atan2(cur_n.cross(des_n), cur_n.dot(des_n))
                    max_ang = AIR_ROCKET_TURN * dt
                    ang = clamp(ang, -max_ang, max_ang)
                    ca, sa = math.cos(ang), math.sin(ang)
                    nx = cur.x * ca - cur.y * sa
                    ny = cur.x * sa + cur.y * ca
                    self.vel = pygame.Vector2(nx, ny).normalize() * AIR_ROCKET_SPEED

        self.pos += self.vel * dt
        return self.life < self.max_life

    def draw(self, surf: pygame.Surface):
        # Small rocket with faint red trail.
        v = self.vel
        sp = v.length()
        if sp < 1e-3:
            return
        n = v / sp
        tail = 18.0
        a = int(180 * (1.0 - clamp(self.life / self.max_life, 0.0, 1.0)))
        pygame.draw.line(surf, (255, 60, 60, a), (self.pos.x - n.x * tail, self.pos.y - n.y * tail), (self.pos.x, self.pos.y), 3)
        pygame.draw.circle(surf, (235, 235, 235), (int(self.pos.x), int(self.pos.y)), 3)
        pygame.draw.circle(surf, (255, 0, 0), (int(self.pos.x), int(self.pos.y)), 3, 1)


@dataclass
class AirJet:
    team: int
    color: Tuple[int, int, int]
    pos: pygame.Vector2
    vel: pygame.Vector2
    ang: float = 0.0
    hp: float = AIR_JET_MAX_HP
    alive: bool = True
    gun_cd: float = 0.0
    rocket_cd: float = 0.0

    def nose_dir(self) -> pygame.Vector2:
        return pygame.Vector2(math.cos(self.ang), math.sin(self.ang))


class AirCombatOverlay:
    """Lightweight top-down air combat that runs over the world map.

    - One jet per active faction (team == faction id).
    - AI jets dogfight continuously.
    - TAB enters air mode; TAB cycles player control between alive jets.
    - LMB fires red tracers; RMB fires homing rockets.
    """

    def __init__(self, sim: 'WorldSim'):
        self.sim = sim
        self.jets: Dict[int, AirJet] = {}
        self.tracers: List[AirTracer] = []
        self.rockets: List[AirRocket] = []
        self.fx: List[AirShockwaveFX] = []
        self._respawn: Dict[int, float] = {}
        self.control_team: Optional[int] = None
        self._gun_accum = 0.0
        self._rmb_prev = False

        # Jet SFX (optional, low volume). Folder scaffolding is created under assets/sfx/jets/<fid>/{shoot,rocket,explode}/
        self._jet_sfx_files: Dict[tuple[int,str], List[str]] = {}
        self._jet_sfx_last_play: Dict[tuple[int,str], float] = {}
        self._jet_sfx_rescan_t: float = 0.0

        self.ensure_jets_exist()

    def ensure_jets_exist(self):
        # Ensure one jet exists for each active faction.
        for fid, f in self.sim.factions.items():
            if len(f.regions) == 0:
                continue
            if fid not in self.jets:
                px, py = self._spawn_point_for_faction(fid)
                self.jets[fid] = AirJet(team=fid, color=f.color, pos=pygame.Vector2(px, py), vel=pygame.Vector2(0, 0), ang=0.0)
                try:
                    self._ensure_jet_sfx_dirs(fid)
                except Exception:
                    pass

        # Remove jets for eliminated factions.
        for fid in list(self.jets.keys()):
            f = self.sim.factions.get(fid)
            if f is None or len(f.regions) == 0:
                self.jets.pop(fid, None)
                if self.control_team == fid:
                    self.control_team = None

        if self.control_team is None and self.jets:
            # default control is the first available jet
            self.control_team = sorted(self.jets.keys())[0]



    def _jet_sfx_base(self, fid: int) -> str:
        root = _project_root()
        return os.path.join(root, 'assets', 'sfx', 'jets', str(int(fid)))

    def _ensure_jet_sfx_dirs(self, fid: int) -> None:
        base = self._jet_sfx_base(fid)
        try:
            os.makedirs(os.path.join(base, 'shoot'), exist_ok=True)
            os.makedirs(os.path.join(base, 'rocket'), exist_ok=True)
            os.makedirs(os.path.join(base, 'explode'), exist_ok=True)
        except Exception:
            pass

    def _scan_jet_sfx(self, fid: int, kind: str) -> List[str]:
        key = (int(fid), str(kind))
        base = self._jet_sfx_base(fid)
        folder = os.path.join(base, str(kind))
        try:
            files = []
            if os.path.isdir(folder):
                for n in os.listdir(folder):
                    nn = n.lower()
                    if nn.endswith(('.wav', '.ogg', '.mp3')):
                        files.append(os.path.join(folder, n))
            files.sort()
            self._jet_sfx_files[key] = files
            return files
        except Exception:
            self._jet_sfx_files[key] = []
            return []

    def _play_jet_sfx(self, fid: int, kind: str, min_interval: float = 0.10) -> None:
        # Best-effort, low-volume playback; silently ignores missing/invalid files.
        try:
            if not pygame.mixer.get_init():
                return
        except Exception:
            return

        now = time.time()
        key = (int(fid), str(kind))
        last = self._jet_sfx_last_play.get(key, 0.0)
        if (now - last) < float(min_interval):
            return

        files = self._jet_sfx_files.get(key)
        if files is None or (now >= self._jet_sfx_rescan_t):
            # Rescan occasionally to pick up newly-dropped files.
            files = self._scan_jet_sfx(fid, kind)
            self._jet_sfx_rescan_t = now + 2.0

        if not files:
            return

        try:
            fp = random.choice(files)
            snd = pygame.mixer.Sound(fp)
            snd.set_volume(float(AIR_JET_SFX_VOLUME))
            snd.play()
            self._jet_sfx_last_play[key] = now
        except Exception:
            return
    def _spawn_point_for_faction(self, fid: int) -> Tuple[float, float]:
        # Spawn near faction capital (region 1st controlled).
        # If multiple regions, use the earliest region id.
        reg = None
        f = self.sim.factions.get(fid)
        if f and f.regions:
            reg = min(f.regions)
        if reg is None:
            reg = 0
        cx, cy = self.sim.capital_pos[reg]
        wx, wy = cell_to_px_world(cx, cy)
        return (wx + TILE / 2, wy + TILE / 2)

    def cycle_control(self):
        alive = [fid for fid, j in self.jets.items() if j.alive]
        if not alive:
            self.control_team = None
            return
        alive.sort()
        if self.control_team not in alive:
            self.control_team = alive[0]
            return
        i = alive.index(self.control_team)
        self.control_team = alive[(i + 1) % len(alive)]

    def _nearest_enemy(self, team: int) -> Optional[AirJet]:
        me = self.jets.get(team)
        best = None
        best_d2 = 1e18
        if me is None:
            return None
        for fid, j in self.jets.items():
            if not j.alive or fid == team:
                continue
            d2 = (j.pos - me.pos).length_squared()
            if d2 < best_d2:
                best_d2 = d2
                best = j
        return best

    def _get_target_pos(self, team: int, preferred_target_team: Optional[int]) -> Optional[pygame.Vector2]:
        # Preferred target by team id if provided, else nearest enemy.
        if preferred_target_team is not None:
            j = self.jets.get(preferred_target_team)
            if j is not None and j.alive:
                return pygame.Vector2(j.pos)
        e = self._nearest_enemy(team)
        if e is None:
            return None
        return pygame.Vector2(e.pos)

    def _spawn_tracer(self, jet: AirJet, dir_v: pygame.Vector2):
        v = dir_v.normalize() * AIR_BULLET_SPEED
        self.tracers.append(AirTracer(pos=pygame.Vector2(jet.pos), vel=v, team=jet.team))
        try:
            self._play_jet_sfx(jet.team, 'shoot', min_interval=0.12)
        except Exception:
            pass

    def _spawn_rocket(self, jet: AirJet, dir_v: pygame.Vector2):
        v = dir_v.normalize() * AIR_ROCKET_SPEED
        # pick a specific target at launch time (kept as preferred)
        tgt = self._nearest_enemy(jet.team)
        tgt_team = tgt.team if tgt is not None else None
        self.rockets.append(AirRocket(pos=pygame.Vector2(jet.pos), vel=v, team=jet.team, target_team=tgt_team))
        try:
            self._play_jet_sfx(jet.team, 'rocket', min_interval=0.35)
        except Exception:
            pass

    def _damage_jet(self, victim: AirJet, dmg: float):
        if not victim.alive:
            return
        victim.hp -= dmg
        if victim.hp <= 0.0:
            victim.alive = False
            victim.hp = 0.0
            self.fx.append(AirShockwaveFX(victim.pos.x, victim.pos.y))
            try:
                self._play_jet_sfx(victim.team, 'explode', min_interval=0.10)
            except Exception:
                pass
            self._respawn[victim.team] = 2.2

    def update(self, dt: float, air_mode: bool, mouse_world: Optional[Tuple[float, float]]):
        self.ensure_jets_exist()

        # Respawns
        for fid in list(self._respawn.keys()):
            self._respawn[fid] -= dt
            if self._respawn[fid] <= 0.0:
                self._respawn.pop(fid, None)
                f = self.sim.factions.get(fid)
                if f is None or len(getattr(f, 'regions', [])) == 0:
                    continue
                px, py = self._spawn_point_for_faction(fid)
                j = self.jets.get(fid)
                if j is None:
                    self.jets[fid] = AirJet(team=fid, color=f.color, pos=pygame.Vector2(px, py), vel=pygame.Vector2(0, 0), ang=0.0)
                try:
                    self._ensure_jet_sfx_dirs(fid)
                except Exception:
                    pass
                else:
                    j.pos = pygame.Vector2(px, py)
                    j.vel = pygame.Vector2(0, 0)
                    j.ang = 0.0
                    j.hp = AIR_JET_MAX_HP
                    j.alive = True
                    j.gun_cd = 0.0
                    j.rocket_cd = 0.0

        keys = pygame.key.get_pressed()
        lmb, _, rmb = pygame.mouse.get_pressed(3)

        # Update jets
        for fid, j in self.jets.items():
            if not j.alive:
                continue

            j.gun_cd = max(0.0, j.gun_cd - dt)
            j.rocket_cd = max(0.0, j.rocket_cd - dt)

            controlled = air_mode and (self.control_team == fid)

            # Aim target
            if controlled and mouse_world is not None:
                mx, my = mouse_world
                aim = pygame.Vector2(mx, my) - j.pos
                if aim.length_squared() > 1e-6:
                    j.ang = math.atan2(aim.y, aim.x)
            else:
                enemy = self._nearest_enemy(fid)
                if enemy is not None:
                    aim = enemy.pos - j.pos
                    if aim.length_squared() > 1e-6:
                        j.ang = math.atan2(aim.y, aim.x)

            # Thrust control
            thrust = pygame.Vector2(0, 0)
            if controlled:
                if keys[pygame.K_w]:
                    thrust.y -= 1
                if keys[pygame.K_s]:
                    thrust.y += 1
                if keys[pygame.K_a]:
                    thrust.x -= 1
                if keys[pygame.K_d]:
                    thrust.x += 1
                if thrust.length_squared() > 0.0:
                    thrust = thrust.normalize() * AIR_JET_THRUST
            else:
                # Simple AI: seek enemy and maintain lateral motion
                enemy = self._nearest_enemy(fid)
                if enemy is not None:
                    to = enemy.pos - j.pos
                    dist = to.length() + 1e-6
                    # Seek, but avoid over-commit when very close
                    if dist > 80:
                        thrust = to.normalize() * AIR_JET_THRUST
                    else:
                        # strafe around target
                        perp = pygame.Vector2(-to.y, to.x)
                        thrust = perp.normalize() * (AIR_JET_THRUST * 0.75)

            # Physics
            j.vel += thrust * dt
            # Hover/damping
            j.vel -= j.vel * (AIR_JET_DAMPING * dt)
            # Clamp speed
            sp = j.vel.length()
            if sp > AIR_JET_MAX_SPEED:
                j.vel.scale_to_length(AIR_JET_MAX_SPEED)

            j.pos += j.vel * dt

            # Keep inside world rect
            j.pos.x = clamp(j.pos.x, WORLD_RECT.left + 8, WORLD_RECT.right - 8)
            j.pos.y = clamp(j.pos.y, WORLD_RECT.top + 8, WORLD_RECT.bottom - 8)

            # Weapons
            if controlled:
                if lmb and mouse_world is not None:
                    # Fire at a fixed rate
                    self._gun_accum += dt * AIR_GUN_FIRE_RATE
                    dir_v = pygame.Vector2(math.cos(j.ang), math.sin(j.ang))
                    while self._gun_accum >= 1.0:
                        self._gun_accum -= 1.0
                        self._spawn_tracer(j, dir_v)
                else:
                    self._gun_accum = 0.0

                if rmb and (not self._rmb_prev) and j.rocket_cd <= 0.0 and mouse_world is not None:
                    j.rocket_cd = AIR_ROCKET_COOLDOWN
                    dir_v = pygame.Vector2(math.cos(j.ang), math.sin(j.ang))
                    self._spawn_rocket(j, dir_v)

            else:
                enemy = self._nearest_enemy(fid)
                if enemy is not None:
                    to = enemy.pos - j.pos
                    dist = to.length() + 1e-6
                    dir_v = pygame.Vector2(math.cos(j.ang), math.sin(j.ang))
                    # Gun range and chance
                    if dist < 460 and j.gun_cd <= 0.0:
                        j.gun_cd = 1.0 / AIR_GUN_FIRE_RATE
                        self._spawn_tracer(j, dir_v)
                    # Rockets
                    if dist < 720 and j.rocket_cd <= 0.0 and random.random() < 0.25:
                        j.rocket_cd = AIR_ROCKET_COOLDOWN
                        self._spawn_rocket(j, dir_v)

        self._rmb_prev = rmb

        # Update tracers and apply hits
        new_tr = []
        for t in self.tracers:
            alive = t.update(dt)
            if not alive:
                continue
            hit = False
            for fid, j in self.jets.items():
                if not j.alive or j.team == t.team:
                    continue
                if (j.pos - t.pos).length_squared() < (7.5 * 7.5):
                    self._damage_jet(j, AIR_BULLET_DMG)
                    hit = True
                    break
            if not hit:
                new_tr.append(t)
        self.tracers = new_tr

        # Update rockets and apply hits/splash
        new_r = []
        for r in self.rockets:
            if not r.update(dt, self._get_target_pos):
                continue
            # Hit check
            impacted = None
            for fid, j in self.jets.items():
                if not j.alive or j.team == r.team:
                    continue
                if (j.pos - r.pos).length_squared() < (10.5 * 10.5):
                    impacted = j
                    break
            if impacted is not None:
                self.fx.append(AirShockwaveFX(r.pos.x, r.pos.y))
                for fid, j in self.jets.items():
                    if not j.alive or j.team == r.team:
                        continue
                    d = (j.pos - r.pos).length()
                    if d < AIR_ROCKET_SPLASH:
                        self._damage_jet(j, AIR_ROCKET_DMG * (1.0 - d / AIR_ROCKET_SPLASH))
                continue
            new_r.append(r)
        self.rockets = new_r

        # FX
        self.fx = [fx for fx in self.fx if fx.update(dt)]

    def draw(self, surf: pygame.Surface, air_mode: bool, mouse_world: Optional[Tuple[float, float]]):
        # Rockets / tracers under jets
        for t in self.tracers:
            t.draw(surf)
        for r in self.rockets:
            r.draw(surf)

        # Jets
        for fid, j in self.jets.items():
            if not j.alive:
                continue
            d = j.nose_dir()
            left = pygame.Vector2(-d.y, d.x)
            p0 = j.pos + d * 10.0
            p1 = j.pos - d * 8.0 + left * 6.0
            p2 = j.pos - d * 8.0 - left * 6.0
            pts = [(p0.x, p0.y), (p1.x, p1.y), (p2.x, p2.y)]
            pygame.draw.polygon(surf, j.color, pts)
            try:
                base = self.sim.factions.get(fid).color if (fid in self.sim.factions) else (255, 0, 0)
                outline = (min(255, int(base[0] * 1.15 + 20)), min(255, int(base[1] * 1.15 + 20)), min(255, int(base[2] * 1.15 + 20)))
            except Exception:
                outline = (255, 0, 0)
            pygame.draw.polygon(surf, outline, pts, 2)

            # Controlled indicator
            if air_mode and self.control_team == fid:
                pygame.draw.circle(surf, outline, (int(j.pos.x), int(j.pos.y)), 14, 1)

        # Shockwaves on top
        for fx in self.fx:
            fx.draw(surf)

        # Crosshair in air mode
        if air_mode and mouse_world is not None:
            mx, my = mouse_world
            pygame.draw.line(surf, (255, 0, 0), (mx - 8, my), (mx + 8, my), 1)
            pygame.draw.line(surf, (255, 0, 0), (mx, my - 8), (mx, my + 8), 1)
            pygame.draw.circle(surf, (255, 0, 0), (int(mx), int(my)), 10, 1)

@dataclass
class Faction:
    fid: int
    name: str
    color: Tuple[int, int, int]
    style: str

    # RTS core stats
    resources: float
    troops: float

    # macro buildings (completed)
    buildings: Dict[str, int] = field(default_factory=dict)

    # queued builds: list of (kind, remaining_ticks)
    build_queue: List[Tuple[str, int]] = field(default_factory=list)

    # regions controlled (set of region ids)
    regions: Set[int] = field(default_factory=set)


# ----------------------------
# World generation
# ----------------------------

def generate_terrain(rng: random.Random, w: int, h: int) -> List[List[int]]:
    noise = [[rng.random() for _ in range(w)] for _ in range(h)]
    for _ in range(4):
        new = [[0.0 for _ in range(w)] for _ in range(h)]
        for y in range(h):
            for x in range(w):
                acc = 0.0
                cnt = 0
                for ny in range(max(0, y-1), min(h, y+2)):
                    for nx in range(max(0, x-1), min(w, x+2)):
                        acc += noise[ny][nx]
                        cnt += 1
                new[y][x] = acc / cnt
        noise = new

    terrain = [[1 for _ in range(w)] for _ in range(h)]
    for y in range(h):
        for x in range(w):
            edge = min(x, y, w-1-x, h-1-y) / min(w, h)
            v = noise[y][x] + (0.20 - edge * 0.35)
            terrain[y][x] = 1 if v > 0.48 else 0
    return terrain

def generate_regions(rng: random.Random, w: int, h: int, region_count: int) -> Tuple[List[List[int]], List[Tuple[int,int,int]], List[Tuple[int,int]]]:
    seeds = [(rng.randrange(w), rng.randrange(h)) for _ in range(region_count)]
    region_id = [[0 for _ in range(w)] for _ in range(h)]
    for y in range(h):
        for x in range(w):
            best_i = 0
            best_d = 1e9
            for i, (sx, sy) in enumerate(seeds):
                dx = x - sx
                dy = y - sy
                d = dx*dx + dy*dy + rng.random()*0.35
                if d < best_d:
                    best_d = d
                    best_i = i
            region_id[y][x] = best_i

    # Region colors: army camouflage shades (muted). Use a shuffled base palette
    # with slight per-region variation to keep regions distinct but cohesive.
    bases = list(CAMO_BASE_COLORS)
    rng.shuffle(bases)
    colors: List[Tuple[int,int,int]] = []
    used: set[Tuple[int,int,int]] = set()
    for i in range(region_count):
        base = bases[i % len(bases)]
        col = camo_variant(base, rng)
        # ensure uniqueness (best effort)
        for _ in range(64):
            if col not in used:
                break
            col = camo_variant(base, rng)
        used.add(col)
        colors.append(col)

    return region_id, colors, seeds

def find_land_cell_in_region(rng: random.Random, terrain: List[List[int]], region_id: List[List[int]],
                             region: int, w: int, h: int) -> Tuple[int,int]:
    # best effort: random attempts, then fallback scan
    for _ in range(8000):
        x = rng.randrange(w)
        y = rng.randrange(h)
        if region_id[y][x] == region and terrain[y][x] == 1:
            return x, y
    for y in range(h):
        for x in range(w):
            if region_id[y][x] == region and terrain[y][x] == 1:
                return x, y
    return w//2, h//2


# ----------------------------
# Region styles (terrain + architecture variation)
# ----------------------------

REGION_STYLES = [
    "COASTAL", "HIGHLANDS", "DESERT", "TUNDRA", "MARSH", "BADLANDS",
    "FOREST", "VOLCANIC", "STEPPE", "URBAN", "RIVERLAND", "RIDGELINE",
]

STYLE_TERRAIN = {
    "COASTAL":   {"water": (18, 42, 70), "land": (46, 70, 60)},
    "HIGHLANDS": {"water": (18, 36, 60), "land": (54, 66, 58)},
    "DESERT":    {"water": (18, 36, 60), "land": (88, 76, 46)},
    "TUNDRA":    {"water": (16, 30, 55), "land": (70, 74, 82)},
    "MARSH":     {"water": (16, 34, 52), "land": (52, 68, 52)},
    "BADLANDS":  {"water": (16, 30, 50), "land": (78, 56, 48)},
    "FOREST":    {"water": (18, 36, 58), "land": (44, 74, 50)},
    "VOLCANIC":  {"water": (14, 26, 48), "land": (62, 52, 58)},
    "STEPPE":    {"water": (18, 36, 58), "land": (62, 74, 54)},
    "URBAN":     {"water": (18, 36, 58), "land": (48, 60, 56)},
    "RIVERLAND": {"water": (18, 42, 70), "land": (52, 74, 56)},
    "RIDGELINE": {"water": (16, 30, 52), "land": (58, 64, 60)},
}

def style_build_weights(style: str, theme: str) -> List[Tuple[str, float]]:
    # Same structure types as the previous prototype, but with stylistic weighting.
    base_city = [("Housing", 2.5), ("Factory", 1.3), ("Barracks", 1.05), ("Civic", 0.9), ("Lab", 0.9)]
    base_town = [("Housing", 2.2), ("Factory", 1.0), ("Barracks", 0.8), ("Civic", 0.75), ("Lab", 0.6)]
    base_farm = [("Farm", 2.7), ("Silo", 1.2), ("Housing", 0.8), ("Factory", 0.5)]
    base_war =  [("Housing", 1.0), ("Factory", 1.0), ("Barracks", 1.4), ("Civic", 0.45), ("Lab", 0.55)]
    base_ruin = [("Housing", 1.4), ("Factory", 0.9), ("Civic", 0.6), ("Lab", 0.55)]
    base_wild = [("Housing", 1.0), ("Farm", 0.7), ("Silo", 0.4)]

    if theme == "CITY":
        w = base_city
    elif theme == "TOWN":
        w = base_town
    elif theme == "FARM":
        w = base_farm
    elif theme == "WARZONE":
        w = base_war
    elif theme == "RUINS":
        w = base_ruin
    else:
        w = base_wild

    # Style nudges
    if style in ("DESERT", "BADLANDS"):
        w = [(k, (v * 1.15 if k in ("Silo", "Barracks") else v * 0.95)) for k, v in w]
    elif style in ("FOREST", "RIVERLAND", "MARSH"):
        w = [(k, (v * 1.18 if k in ("Farm", "Housing") else v * 0.94)) for k, v in w]
    elif style in ("VOLCANIC", "HIGHLANDS", "RIDGELINE"):
        w = [(k, (v * 1.18 if k in ("Factory", "Lab") else v * 0.95)) for k, v in w]
    elif style == "URBAN":
        w = [(k, (v * 1.22 if k in ("Civic", "Factory") else v * 0.96)) for k, v in w]
    return w

def style_build_palette(style: str, base: Tuple[int,int,int], kind: str) -> Tuple[int,int,int]:
    # Palette modulation: keep faction base color, but vary material "feel" by style + kind.
    if style == "DESERT":
        base = _add_color(_mul_color(base, 0.92), 18)
    elif style == "TUNDRA":
        base = _add_color(_mul_color(base, 0.88), 28)
    elif style == "VOLCANIC":
        base = _mul_color(base, 0.78)
    elif style == "MARSH":
        base = _mul_color(base, 0.85)
    elif style == "URBAN":
        base = _add_color(_mul_color(base, 0.92), 8)

    if kind == "Factory":
        return _mul_color(base, 0.78)
    if kind == "Barracks":
        return _mul_color(base, 0.83)
    if kind == "Civic":
        return _add_color(_mul_color(base, 0.88), 12)
    if kind in ("Farm", "Silo"):
        # maintain readable farm/silo identity with style tint
        if kind == "Farm":
            return _add_color((150, 140, 95), 10 if style in ("DESERT","BADLANDS") else 0)
        return _add_color((135, 138, 145), 10 if style == "TUNDRA" else 0)
    # Housing / Lab
    return _add_color(_mul_color(base, 0.90), 22)


# ----------------------------
# Building meta & rendering
# ----------------------------

def building_meta(local_seed: int, kind: str, gx: int, gy: int) -> Tuple[int, int, int, int]:
    h = local_seed ^ (gx * 92837111) ^ (gy * 689287499) ^ _stable_hash32(kind)
    rng = random.Random(h & 0xFFFFFFFF)

    if kind == "Housing":
        tw = rng.choice([2, 3, 3, 4, 5])
        th = rng.choice([2, 3, 3, 4])
    elif kind == "Factory":
        tw = rng.choice([4, 5, 6])
        th = rng.choice([4, 5, 6])
    elif kind == "Barracks":
        tw = rng.choice([3, 4, 5])
        th = rng.choice([3, 4, 4])
    elif kind == "Civic":
        tw = rng.choice([4, 5, 6])
        th = rng.choice([4, 5, 6])
    elif kind == "Farm":
        tw = rng.choice([4, 5, 6, 7])
        th = rng.choice([2, 3, 3])
    elif kind == "Silo":
        tw = rng.choice([2, 3])
        th = rng.choice([2, 3])
    else:  # Lab
        tw = rng.choice([3, 4, 5])
        th = rng.choice([3, 4, 5])

    variant = rng.randrange(0, 6)
    roof = rng.randrange(0, 3)
    return tw, th, variant, roof

def building_tile_rect(b: Building) -> pygame.Rect:
    left = b.gx - b.tw // 2
    top = b.gy - b.th // 2
    return pygame.Rect(left, top, b.tw, b.th)

_BUILDING_CACHE: Dict[Tuple[str,int,int,int,int,Tuple[int,int,int]], pygame.Surface] = {}

def render_building_base(kind: str, w: int, h: int, variant: int, roof: int,
                         base: Tuple[int, int, int]) -> pygame.Surface:
    key = (kind, w, h, variant, roof, base)
    if key in _BUILDING_CACHE:
        return _BUILDING_CACHE[key]

    s = pygame.Surface((w, h), pygame.SRCALPHA)

    # Shadow
    shadow_pts = [(x+2, y+2) for x, y in _chamfer_points(w, h, 6)]
    pygame.draw.polygon(s, (0, 0, 0, 55), shadow_pts)

    # Roof
    pts = _chamfer_points(w, h, 6)
    pygame.draw.polygon(s, (*base, 235), pts)

    # Shading
    hi = _add_color(base, 30)
    lo = _mul_color(base, 0.78)
    pygame.draw.line(s, (*hi, 220), (pts[0][0], pts[0][1]+1), (pts[1][0], pts[1][1]+1), 2)
    pygame.draw.line(s, (*hi, 220), (pts[6][0]+1, pts[6][1]), (pts[7][0]+1, pts[7][1]), 2)
    pygame.draw.line(s, (*lo, 220), (pts[3][0]-1, pts[3][1]), (pts[4][0]-1, pts[4][1]), 2)
    pygame.draw.line(s, (*lo, 220), (pts[4][0], pts[4][1]-1), (pts[5][0], pts[5][1]-1), 2)

    pygame.draw.polygon(s, (0, 0, 0, 120), pts, 2)

    # Roof accents
    if roof == 1:
        pygame.draw.line(s, (0, 0, 0, 80), (w*0.20, h*0.50), (w*0.80, h*0.50), 3)
        pygame.draw.line(s, (*hi, 160), (w*0.20, h*0.48), (w*0.80, h*0.48), 1)
    elif roof == 2:
        inset = pygame.Rect(int(w*0.18), int(h*0.18), int(w*0.64), int(h*0.64))
        pygame.draw.rect(s, (*_mul_color(base, 0.90), 200), inset, border_radius=6)
        pygame.draw.rect(s, (0, 0, 0, 90), inset, 2, border_radius=6)

    rng = random.Random((w << 16) ^ (h << 1) ^ (variant << 8) ^ _stable_hash32(kind))

    def windows_grid(cols: int, rows: int, margin: int = 6):
        cell_w = max(2, (w - 2*margin) // cols)
        cell_h = max(2, (h - 2*margin) // rows)
        win_w = max(2, int(cell_w * 0.55))
        win_h = max(2, int(cell_h * 0.45))
        for ry in range(rows):
            for cx in range(cols):
                if rng.random() < 0.14:
                    continue
                px = margin + cx*cell_w + (cell_w-win_w)//2
                py = margin + ry*cell_h + (cell_h-win_h)//2
                pygame.draw.rect(s, (20, 20, 30, 120), (px, py, win_w, win_h), border_radius=2)
                pygame.draw.rect(s, (*_add_color(base, 55), 75), (px+1, py+1, max(1, win_w-2), max(1, win_h-2)), border_radius=2)

    if kind in ("Housing",):
        windows_grid(cols=rng.choice([4, 5, 6]), rows=rng.choice([3, 4, 5]), margin=8)
    elif kind == "Factory":
        for _ in range(rng.randint(4, 8)):
            px = rng.randint(8, max(8, w-22))
            py = rng.randint(8, max(8, h-18))
            pygame.draw.rect(s, (*_mul_color(base, 0.65), 210), (px, py, rng.randint(10, 18), 6), border_radius=2)
        for _ in range(rng.randint(1, 3)):
            cx = rng.randint(6, max(6, w-14))
            pygame.draw.rect(s, (*_mul_color(base, 0.60), 235), (cx, 3, 8, rng.randint(10, 18)), border_radius=2)
            pygame.draw.rect(s, (0, 0, 0, 110), (cx, 3, 8, rng.randint(10, 18)), 1, border_radius=2)
    elif kind == "Barracks":
        court = pygame.Rect(int(w*0.22), int(h*0.22), int(w*0.56), int(h*0.56))
        pygame.draw.rect(s, (*_mul_color(base, 0.88), 200), court, border_radius=6)
        pygame.draw.rect(s, (0, 0, 0, 90), court, 2, border_radius=6)
        windows_grid(cols=rng.choice([4, 5]), rows=rng.choice([2, 3]), margin=8)
    elif kind == "Civic":
        r = min(w, h) // 5
        pygame.draw.circle(s, (*_mul_color(base, 0.82), 220), (w//2, h//2), r+4)
        pygame.draw.circle(s, (*_add_color(base, 40), 170), (w//2, h//2), r)
        pygame.draw.circle(s, (0, 0, 0, 100), (w//2, h//2), r+4, 2)
    elif kind == "Farm":
        for i in range(6):
            y = int(h*0.18 + i*(h*0.12))
            pygame.draw.line(s, (0, 0, 0, 40), (8, y), (w-8, y), 2)
    elif kind == "Silo":
        pygame.draw.circle(s, (*_mul_color(base, 0.85), 220), (w//2, h//2), min(w,h)//3)
        pygame.draw.circle(s, (0, 0, 0, 120), (w//2, h//2), min(w,h)//3, 2)
    else:  # Lab
        for _ in range(rng.randint(5, 10)):
            px = rng.randint(8, max(8, w-20))
            py = rng.randint(8, max(8, h-20))
            rw = rng.randint(8, 16)
            rh = rng.randint(6, 10)
            pygame.draw.rect(s, (*_mul_color(base, 0.80), 210), (px, py, rw, rh), border_radius=2)
            pygame.draw.rect(s, (0, 0, 0, 70), (px, py, rw, rh), 1, border_radius=2)
        pygame.draw.line(s, (0, 0, 0, 140), (int(w*0.75), int(h*0.25)), (int(w*0.86), int(h*0.08)), 3)
        pygame.draw.circle(s, (*_add_color(base, 50), 200), (int(w*0.86), int(h*0.08)), 5)

    if variant in (2, 4) and w > 34 and h > 26:
        wing_w = max(14, int(w*0.32))
        wing_h = max(12, int(h*0.28))
        if rng.random() < 0.5:
            wing = pygame.Rect(2, int(h*0.55), wing_w, wing_h)
        else:
            wing = pygame.Rect(int(w*0.62), 2, wing_w, wing_h)
        pygame.draw.rect(s, (*_mul_color(base, 0.92), 230), wing, border_radius=6)
        pygame.draw.rect(s, (0, 0, 0, 90), wing, 2, border_radius=6)

    _BUILDING_CACHE[key] = s
    return s

def draw_construction_overlay(dst: pygame.Surface, progress: float):
    veil = pygame.Surface(dst.get_size(), pygame.SRCALPHA)
    veil.fill((0, 0, 0, int(85 * (1.0 - progress))))
    dst.blit(veil, (0, 0))
    w, h = dst.get_size()
    hatch = pygame.Surface((w, h), pygame.SRCALPHA)
    step = 10
    col = (235, 235, 235, int(70 * (1.0 - progress) + 20))
    for x in range(-h, w, step):
        pygame.draw.line(hatch, col, (x, 0), (x + h, h), 2)
    dst.blit(hatch, (0, 0))

def draw_destroyed_overlay(dst: pygame.Surface, burn: float):
    w, h = dst.get_size()
    rubble = pygame.Surface((w, h), pygame.SRCALPHA)
    rubble.fill((0, 0, 0, 0))
    rng = random.Random((w<<16) ^ (h<<1) ^ int(burn*1000))
    for _ in range(22):
        x = rng.randint(3, w-4)
        y = rng.randint(3, h-4)
        pygame.draw.circle(rubble, (40, 40, 45, 170), (x, y), rng.randint(1, 3))
    dst.blit(rubble, (0, 0))
    if burn > 0.01:
        a = int(clamp(160 * burn, 0, 170))
        for _ in range(3):
            cx = int(w*0.5 + rng.uniform(-0.2, 0.2)*w)
            cy = int(h*0.35 + rng.uniform(-0.2, 0.2)*h)
            pygame.draw.circle(dst, (30, 30, 35, a), (cx, cy), int(min(w,h)*0.22))


# ----------------------------
# Local map generation (Area View)
# ----------------------------

LOCAL_W = 84
LOCAL_H = 84
LOCAL_TILE = 7
LOCAL_PX_W = LOCAL_W * LOCAL_TILE  # 588
LOCAL_PX_H = LOCAL_H * LOCAL_TILE  # 588

AREA_VIEW_RECT = pygame.Rect(
    WORLD_X + (WORLD_PX_W - LOCAL_PX_W)//2,
    WORLD_Y + (WORLD_PX_H - LOCAL_PX_H)//2,
    LOCAL_PX_W,
    LOCAL_PX_H
)

def generate_area_local_map(seed: int, theme: str, style: str) -> LocalMap:
    rng = random.Random(seed)
    terrain = generate_terrain(rng, LOCAL_W, LOCAL_H)

    # Theme-specific land bias (preserved)
    if theme in ("CITY", "TOWN", "FARM"):
        for y in range(LOCAL_H):
            for x in range(LOCAL_W):
                if rng.random() < 0.10:
                    terrain[y][x] = 1
    elif theme == "WARZONE":
        for y in range(LOCAL_H):
            for x in range(LOCAL_W):
                if rng.random() < 0.14:
                    terrain[y][x] = 1
    elif theme == "RUINS":
        for y in range(LOCAL_H):
            for x in range(LOCAL_W):
                if rng.random() < 0.12:
                    terrain[y][x] = 1

    buildings: List[Building] = []
    attempts = 0

    if theme == "CITY":
        lot_count = 60
    elif theme == "TOWN":
        lot_count = 40
    elif theme == "FARM":
        lot_count = 28
    elif theme == "WARZONE":
        lot_count = 34
    elif theme == "RUINS":
        lot_count = 26
    else:
        lot_count = 10

    kind_weights = style_build_weights(style, theme)

    while len(buildings) < lot_count and attempts < 18000:
        attempts += 1
        kind = pick_weighted(rng, kind_weights)
        x = rng.randrange(6, LOCAL_W - 6)
        y = rng.randrange(6, LOCAL_H - 6)
        if terrain[y][x] == 0:
            continue

        tw, th, variant, roof = building_meta(seed, kind, x, y)
        left = x - tw // 2
        top = y - th // 2
        if left < 2 or top < 2 or left + tw >= LOCAL_W - 2 or top + th >= LOCAL_H - 2:
            continue

        new_rect = pygame.Rect(left, top, tw, th).inflate(4, 4)
        if any(new_rect.colliderect(building_tile_rect(ob).inflate(4, 4)) for ob in buildings):
            continue

        rate = 0.00045 + rng.random() * 0.00115
        b = Building(kind=kind, gx=x, gy=y, tw=tw, th=th, variant=variant, roof=roof, started=False, progress=0.0, build_rate=rate)

        # Theme defaults (preserved)
        if theme in ("CITY", "TOWN"):
            if rng.random() < 0.22:
                b.started = True
                b.progress = rng.random() * 0.25
            if rng.random() < (0.08 if theme == "CITY" else 0.05):
                b.started = True
                b.progress = 1.0
        elif theme == "FARM":
            if rng.random() < 0.18:
                b.started = True
                b.progress = rng.random() * 0.2
            if rng.random() < 0.05:
                b.started = True
                b.progress = 1.0
        elif theme == "WARZONE":
            if rng.random() < 0.40:
                b.started = True
                b.progress = rng.random() * 0.2
            if rng.random() < 0.25:
                b.started = True
                b.progress = 1.0
                if rng.random() < 0.35:
                    b.damage = rng.random() * 0.6
            if rng.random() < 0.18:
                b.destroyed = True
                b.burn = rng.random() * 0.9
        elif theme == "RUINS":
            b.started = True
            b.progress = 1.0
            b.destroyed = rng.random() < 0.55
            b.burn = rng.random() * 0.6 if b.destroyed else 0.0
            b.damage = rng.random() * 0.8
        else:
            if rng.random() < 0.10:
                b.started = True
                b.progress = rng.random() * 0.2

        buildings.append(b)

    if theme not in ("RUINS",):
        rng.shuffle(buildings)
        for b in buildings[:max(3, lot_count//12)]:
            b.started = True
            b.progress = max(b.progress, rng.random() * 0.15)

    return LocalMap(seed=seed, theme=theme, style=style, terrain=terrain, buildings=buildings)


# ----------------------------
# Simulation core
# ----------------------------

class WorldSim:
    def __init__(self, seed: Optional[int] = None):
        self.seed = seed if seed is not None else random.randrange(1_000_000_000)
        self.rng = random.Random(self.seed)

        self.terrain = generate_terrain(self.rng, WORLD_W, WORLD_H)
        self.region_id, self.region_colors, self.region_seeds = generate_regions(self.rng, WORLD_W, WORLD_H, REGION_COUNT)

        # Per-tile owner is faction id; -1 means unowned (water)
        self.owner = [[-1 for _ in range(WORLD_W)] for _ in range(WORLD_H)]
        self.ruins = [[0.0 for _ in range(WORLD_W)] for _ in range(WORLD_H)]

        # Factions are persistent entities; region control can transfer
        self.factions: Dict[int, Faction] = {}

        # region -> controlling faction id
        self.region_control: List[int] = [i for i in range(REGION_COUNT)]

        # region capitals
        self.capital_pos: List[Tuple[int,int]] = [(0,0)] * REGION_COUNT
        self.capital_hp: List[float] = [CAPITAL_HP_MAX] * REGION_COUNT

        # Wars: directed wars (attacker -> defender)
        self.wars: Set[Tuple[int,int]] = set()

        # Player faction (selected once at the start of a new game). When set, the macro-sim
        # will strongly prefer (and by default restrict) invasions to involve this faction,
        # so the "enemy you're at war with" remains consistent across modes.
        self.player_fid: Optional[int] = None

        # Player participation bonus: increased odds during invasions for factions you support via micro-modes.
        # Values are 'support points' that decay over time.
        # NOTE: initialized after factions are created in _init_factions_and_ownership().
        self.support: Dict[int, float] = {}

        self.tick = 0
        self.news = deque(maxlen=NEWS_LINES)
        self.fx: List[ExplosionFX] = []

        self.selected_cell: Optional[Tuple[int,int]] = None
        self.inspected_cell: Optional[Tuple[int,int]] = None

        self._init_factions_and_ownership()

    def log(self, msg: str):
        stamp = f"T+{self.tick:05d}"
        self.news.appendleft(f"{stamp}  {msg}")

    def _init_factions_and_ownership(self):
        # Each region starts as its own faction
        used_colors = set()
        for rid in range(REGION_COUNT):
            style = self.rng.choice(REGION_STYLES)
            name = gen_region_name(self.rng)
            # Use the region camouflage color as faction color for cohesion (muted army palette)
            col = self.region_colors[rid]
            # Best-effort uniqueness guard (should already be unique from generation)
            for _ in range(32):
                if col not in used_colors:
                    break
                col = camo_variant(col, self.rng)
            used_colors.add(col)

            # Start with exactly ONE macro building per faction (slow RTS ramp).
            start_weights = style_build_weights(style, "TOWN")
            tweaked = []
            for k, w in start_weights:
                if k == "Barracks":
                    w *= 0.35
                elif k == "Lab":
                    w *= 0.55
                tweaked.append((k, w))
            initial_kind = pick_weighted(self.rng, tweaked)

            f = Faction(
                fid=rid,
                name=name,
                color=col,
                style=style,
                resources=220.0 + self.rng.random()*160.0,
                troops=55.0 + self.rng.random()*55.0,
                buildings={initial_kind: 1},
                build_queue=[],
                regions={rid},
            )
            self.factions[rid] = f

        # Initialize per-faction support values now that factions exist.
        self.support = {fid: 0.0 for fid in self.factions.keys()}

        # Pick a capital per region (on land, in region)
        for rid in range(REGION_COUNT):
            cx, cy = find_land_cell_in_region(self.rng, self.terrain, self.region_id, rid, WORLD_W, WORLD_H)
            self.capital_pos[rid] = (cx, cy)
            self.capital_hp[rid] = CAPITAL_HP_MAX

        # Initialize ownership: land tiles belong to controlling faction of their region; water unowned
        for y in range(WORLD_H):
            for x in range(WORLD_W):
                if self.terrain[y][x] == 0:
                    self.owner[y][x] = -1
                    continue
                rid = self.region_id[y][x]
                self.owner[y][x] = self.region_control[rid]

        self.log("World initialized: regions are AI RTS factions. Borders become battlefronts when invasions begin.")
        self.log("Tip: right-click a tile to inspect, then watch troop and build numbers climb.")

    # ------------ world queries ------------
    def owner_at(self, x: int, y: int) -> int:
        if 0 <= x < WORLD_W and 0 <= y < WORLD_H:
            return self.owner[y][x]
        return -1

    def region_at(self, x: int, y: int) -> int:
        if 0 <= x < WORLD_W and 0 <= y < WORLD_H:
            return self.region_id[y][x]
        return 0

    def ruins_at(self, x: int, y: int) -> float:
        if 0 <= x < WORLD_W and 0 <= y < WORLD_H:
            return self.ruins[y][x]
        return 0.0

    def region_controller(self, rid: int) -> int:
        return self.region_control[rid]

    def region_tile_count(self, rid: int, only_land: bool = True) -> int:
        cnt = 0
        for y in range(WORLD_H):
            for x in range(WORLD_W):
                if self.region_id[y][x] != rid:
                    continue
                if only_land and self.terrain[y][x] == 0:
                    continue
                cnt += 1
        return cnt

    def faction_land_tiles(self, fid: int) -> int:
        cnt = 0
        for y in range(WORLD_H):
            for x in range(WORLD_W):
                if self.owner[y][x] == fid and self.terrain[y][x] == 1:
                    cnt += 1
        return cnt

    def _compute_frontline(self, a: int, b: int) -> List[Tuple[int,int,int,int]]:
        # returns list of (ax,ay,bx,by) where a-owned cell borders b-owned cell
        edges = []
        for y in range(WORLD_H):
            for x in range(WORLD_W):
                if self.owner[y][x] != a:
                    continue
                for nx, ny in grid_neighbors(x, y, WORLD_W, WORLD_H):
                    if self.owner[ny][nx] == b:
                        edges.append((x, y, nx, ny))
        return edges

    def _frontline_here(self, x: int, y: int, owner_id: int) -> bool:
        for nx, ny in grid_neighbors(x, y, WORLD_W, WORLD_H):
            other = self.owner[ny][nx]
            if other >= 0 and other != owner_id and ((owner_id, other) in self.wars or (other, owner_id) in self.wars):
                return True
        return False

    def _spawn_conflict_fx_at_cell(self, x: int, y: int, intensity: float = 1.0):
        px = WORLD_X + x * TILE + TILE/2
        py = WORLD_Y + y * TILE + TILE/2
        self.fx.append(ExplosionFX(px, py, intensity=intensity))

    def _neighbors_by_region_control(self, fid: int) -> Set[int]:
        # Find neighboring controlling factions by scanning borders; use region adjacency implicitly.
        nbors = set()
        for y in range(WORLD_H):
            for x in range(WORLD_W):
                if self.owner[y][x] != fid:
                    continue
                for nx, ny in grid_neighbors(x, y, WORLD_W, WORLD_H):
                    other = self.owner[ny][nx]
                    if other >= 0 and other != fid:
                        nbors.add(other)
        return nbors

    def _maybe_start_invasion(self, attacker: Faction):
        # Only expand when troops exceed threshold; also require some resource buffer.
        controlled = len(attacker.regions)
        threshold = INVASION_BASE_THRESHOLD + INVASION_PER_REGION_THRESHOLD * max(0, controlled - 1)
        if attacker.troops < threshold:
            return
        if attacker.resources < 140.0:
            return

        # Only allow one invasion at a time (global).
        if self.wars:
            return

        # If a player faction has been chosen, keep the global "current invasion"
        # centered on that faction so minigames always have a consistent opponent.
        player = getattr(self, "player_fid", None)
        if player is not None:
            try:
                player = int(player)
            except Exception:
                player = None
        if player is not None:
            # If the player faction has been eliminated, disable the restriction.
            try:
                if player not in self.factions or len(self.factions[player].regions) == 0:
                    player = None
            except Exception:
                player = None

        neighbors = list(self._neighbors_by_region_control(attacker.fid))
        if player is not None:
            if attacker.fid == player:
                candidate_pool = neighbors
            else:
                candidate_pool = [player] if player in neighbors else []
        else:
            candidate_pool = neighbors

        # Choose a neighboring enemy not already at war with attacker
        candidates: List[int] = []
        for other in candidate_pool:
            if (attacker.fid, other) in self.wars or (other, attacker.fid) in self.wars:
                continue
            # avoid suiciding into massive defender advantage
            def_f = self.factions.get(other)
            if def_f and def_f.troops > attacker.troops * 1.45 and self.rng.random() < 0.75:
                continue
            candidates.append(other)

        if not candidates:
            return

        target = self.rng.choice(candidates)
        self.wars.add((attacker.fid, target))
        self.log(f"INVASION: {attacker.name} begins an invasion against {self.factions[target].name}.")

    def _reconcile_regions_sets(self):
        # Rebuild each faction.regions from region_control mapping (cheap at this scale).
        for f in self.factions.values():
            f.regions = set()
        for rid, controller in enumerate(self.region_control):
            if controller in self.factions:
                self.factions[controller].regions.add(rid)

    def _conquer_region(self, winner_id: int, rid: int, loser_id: int):
        winner = self.factions[winner_id]
        loser = self.factions.get(loser_id)

        # Flip control for the region id
        self.region_control[rid] = winner_id

        # Convert ALL land tiles in that region to winner ownership
        for y in range(WORLD_H):
            for x in range(WORLD_W):
                if self.region_id[y][x] != rid:
                    continue
                if self.terrain[y][x] == 0:
                    continue
                self.owner[y][x] = winner_id
                self.ruins[y][x] = max(self.ruins[y][x], 0.10)

        # The region takes the winner's name/color as requested (mapped by controller)
        # (Winner keeps its own name; the region label becomes winner's name in UI)
        self.capital_hp[rid] = CAPITAL_HP_MAX * 0.55
        self._reconcile_regions_sets()

        self.log(f"CONQUEST: {winner.name} destroys the Capital of region {rid}. Region is absorbed and renamed.")

        # Stop wars that were specifically between these two factions (either direction)
        self.wars = {(a, b) for (a, b) in self.wars if not ((a == winner_id and b == loser_id) or (a == loser_id and b == winner_id))}

        # Loser might be eliminated (no regions left)
        if loser is not None and len(loser.regions) == 0:
            self.log(f"ELIMINATED: {loser.name} has lost all regions and collapses as a faction.")
            # keep faction record but set troops/resources to minimal; it will stop acting
            loser.troops = 0.0
            loser.resources = 0.0

    def _tick_economy_and_building(self):
        # Build + recruit for each active faction
        for fid, f in self.factions.items():
            if len(f.regions) == 0:
                continue  # eliminated

            land = self.faction_land_tiles(fid)
            b = f.buildings

            # Income model: tiles + buildings
            income = 0.045 * land
            income += 1.20 * b.get("Factory", 0)
            income += 0.95 * b.get("Farm", 0)
            income += 0.35 * b.get("Silo", 0)
            income += 0.55 * b.get("Civic", 0)
            income += 0.65 * b.get("Lab", 0)

            # Upkeep model: troops + some buildings
            upkeep = 0.020 * f.troops
            upkeep += 0.18 * b.get("Factory", 0)
            upkeep += 0.12 * b.get("Lab", 0)

            f.resources = clamp(f.resources + income - upkeep, 0.0, RES_CAP)

            # Build queue progression
            if f.build_queue:
                kind, remaining = f.build_queue[0]
                remaining -= 1
                if remaining <= 0:
                    f.build_queue.pop(0)
                    f.buildings[kind] = f.buildings.get(kind, 0) + 1
                    self.log(f"BUILD: {f.name} completes a {kind}.")
                else:
                    f.build_queue[0] = (kind, remaining)

            # Decide to start new build if queue is empty and resources allow
            if not f.build_queue:
                # A soft cap: more regions allow more total buildings
                total_b = sum(f.buildings.values())
                cap = 18 + 10 * len(f.regions)
                if total_b < cap and f.resources > 170.0 and self.rng.random() < 0.040:
                    # Choose building based on style and needs
                    # If troop pressure, bias Barracks; if low income, bias Factory/Farm.
                    weights = style_build_weights(f.style, "TOWN")
                    if f.troops < (60 + 22 * len(f.regions)):
                        weights = [(k, (v*1.5 if k == "Barracks" else v)) for k, v in weights]
                    if f.resources < 220:
                        weights = [(k, (v*1.35 if k in ("Factory","Farm") else v)) for k, v in weights]
                    kind = pick_weighted(self.rng, weights)

                    # Cost model
                    cost = {
                        "Housing": 130.0,
                        "Factory": 180.0,
                        "Barracks": 170.0,
                        "Civic": 200.0,
                        "Farm": 140.0,
                        "Silo": 120.0,
                        "Lab": 210.0
                    }.get(kind, 160.0)

                    if f.resources >= cost:
                        f.resources -= cost
                        delay = self.rng.randint(BUILD_MIN_DELAY, BUILD_MAX_DELAY)
                        f.build_queue.append((kind, delay))

            # Recruit troops: driven mostly by Barracks + Civic + some baseline
            recruit_rate = 0.08 + 0.18 * b.get("Barracks", 0) + 0.04 * b.get("Civic", 0) + 0.03 * b.get("Housing", 0)
            # War-time urgency: faster recruitment
            if any(a == fid or d == fid for (a, d) in self.wars):
                recruit_rate *= 1.35

            # Recruit if you can pay for it
            recruit_cost = recruit_rate * 0.80
            if f.resources >= recruit_cost:
                f.resources -= recruit_cost
                f.troops = clamp(f.troops + recruit_rate, 0.0, 99999.0)

            # Natural attrition keeps numbers bounded
            f.troops = max(0.0, f.troops - 0.005 * f.troops)

    def _tick_wars_and_sieges(self):
        # Resolve each war with small "frontline" steps
        wars_list = list(self.wars)
        self.rng.shuffle(wars_list)

        for attacker_id, defender_id in wars_list:
            att = self.factions.get(attacker_id)
            deff = self.factions.get(defender_id)
            if not att or not deff:
                continue
            if len(att.regions) == 0 or len(deff.regions) == 0:
                continue

            frontline = self._compute_frontline(attacker_id, defender_id)
            if not frontline:
                # no direct contact; war effectively paused
                continue

            steps = int(FRONTLINE_STEPS_BASE + FRONTLINE_STEPS_SCALE * att.troops)
            steps = max(1, min(16, steps))
            self.rng.shuffle(frontline)

            for ax, ay, bx, by in frontline[:steps]:
                # Attempt to capture defender tile (bx,by) with probability based on troop ratio
                ratio = (att.troops + 20.0) / max(30.0, deff.troops + 20.0)
                # Apply player support as a small multiplicative advantage.
                # ~+1% capture odds per support point difference (capped).
                s_att = clamp(self.support.get(attacker_id, 0.0), 0.0, 40.0)
                s_def = clamp(self.support.get(defender_id, 0.0), 0.0, 40.0)
                ratio *= (1.0 + 0.01 * s_att) / max(0.75, (1.0 + 0.01 * s_def))
                p_take = clamp(CAPTURE_P_BASE * ratio, 0.04, 0.78)
                # Terrain and ruins add friction
                p_take *= (0.90 - 0.25 * self.ruins[by][bx])

                if self.rng.random() < p_take:
                    self.owner[by][bx] = attacker_id
                    self.ruins[by][bx] = clamp(self.ruins[by][bx] + 0.12, 0.0, 1.0)
                    # casualties
                    att_loss = 0.35 + 0.25*self.rng.random()
                    def_loss = 0.55 + 0.35*self.rng.random()
                    att.troops = max(0.0, att.troops - att_loss)
                    deff.troops = max(0.0, deff.troops - def_loss)
                    self._spawn_conflict_fx_at_cell(bx, by, intensity=1.0)
                else:
                    if self.rng.random() < 0.18:
                        self._spawn_conflict_fx_at_cell(bx, by, intensity=0.7)
                    # small skirmish casualties
                    if self.rng.random() < 0.25:
                        att.troops = max(0.0, att.troops - 0.12)
                        deff.troops = max(0.0, deff.troops - 0.16)

            # Siege logic: if attacker owns defender capital cell, damage capital HP
            for rid in list(deff.regions):
                capx, capy = self.capital_pos[rid]
                if self.owner[capy][capx] == attacker_id:
                    siege = 0.55 + 0.006 * att.troops
                    siege *= (1.0 + 0.10*len(att.regions))
                    self.capital_hp[rid] -= siege
                    self.ruins[capy][capx] = clamp(self.ruins[capy][capx] + 0.24, 0.0, 1.0)
                    if self.rng.random() < 0.35:
                        self._spawn_conflict_fx_at_cell(capx, capy, intensity=1.35)

                    if self.capital_hp[rid] <= 0.0:
                        self._conquer_region(attacker_id, rid, defender_id)
                        break
                else:
                    # Regenerate if not currently sieged
                    self.capital_hp[rid] = min(CAPITAL_HP_MAX, self.capital_hp[rid] + CAPITAL_REGEN)

    def step_tick(self):
        self.tick += 1

        # decay ruins
        for y in range(WORLD_H):
            for x in range(WORLD_W):
                if self.ruins[y][x] > 0.0:
                    self.ruins[y][x] = max(0.0, self.ruins[y][x] - RUINS_DECAY)

        # keep regions sets consistent (in case of conquest)
        self._reconcile_regions_sets()

        # economy & builds
        self._tick_economy_and_building()

        # start invasions (expansion only with troop surplus)
        # Stagger decisions slightly
        for fid in list(self.factions.keys()):
            f = self.factions[fid]
            if len(f.regions) == 0:
                continue
            if self.rng.random() < 0.10:
                self._maybe_start_invasion(f)

        # wars
        if self.wars:
            self._tick_wars_and_sieges()

        # Decay support slowly so bonuses are temporary.
        try:
            for fid in list(self.support.keys()):
                self.support[fid] = max(0.0, self.support.get(fid, 0.0) * 0.985)
        except Exception:
            pass

        # periodic status headline
        if self.tick % 60 == 0:
            active = sum(1 for f in self.factions.values() if len(f.regions) > 0)
            self.log(f"Status: {active} active factions; {len(self.wars)} active invasions.")




# ----------------------------
# Map-integrated Ground Combat (dots-on-map)
# ----------------------------

@dataclass
class DotUnit:
    pos: pygame.Vector2
    vel: pygame.Vector2
    team: int  # 0 = player side, 1 = enemy side (local battle teams)
    hp: float
    cd: float = 0.0


@dataclass
class DotTracer:
    a: pygame.Vector2
    b: pygame.Vector2
    col: Tuple[int, int, int]
    t: float = 0.10


class MapDotGroundCombatSim:
    """A lightweight 1v1 skirmish rendered directly on the main world map.

    - Each side is a swarm of team-colored dots (soldiers).
    - The fight is confined to a battle zone centered near the frontline cell.
    - LMB inside the battle zone: set rally point for your side.
    - RMB: clear rally point.
    - Win/lose feeds into the existing macro outcome pipeline (_apply_ground_outcome).
    """

    def __init__(self, sim: "WorldSim", ctx: dict, player_fid: int):
        self.sim = sim
        self.ctx = ctx

        fid_a = int(ctx.get("fid_a", -1))
        fid_b = int(ctx.get("fid_b", -1))
        if player_fid not in (fid_a, fid_b):
            player_fid = fid_a

        other_fid = fid_b if player_fid == fid_a else fid_a

        # Map to local teams
        self.team_fid = [player_fid, other_fid]  # local team 0,1 -> faction ids
        self.team_name = [
            sim.factions[player_fid].name if player_fid in sim.factions else f"Faction {player_fid}",
            sim.factions[other_fid].name if other_fid in sim.factions else f"Faction {other_fid}",
        ]
        self.team_color = [
            sim.factions[player_fid].color if player_fid in sim.factions else (90, 200, 120),
            sim.factions[other_fid].color if other_fid in sim.factions else (220, 90, 90),
        ]

        # Outcome contract used by Game._apply_ground_outcome
        self.finished: bool = False
        self.decisive: bool = False
        self.winner_fid: Optional[int] = None
        self.loser_fid: Optional[int] = None
        self.casualties: Dict[int, int] = {player_fid: 0, other_fid: 0}
        self.finish_timer: float = 999.0  # counts down after finished

        # Battle parameters (kept intentionally simple + readable)
        self.time_left: float = 55.0
        self.unit_hp: float = 12.0
        self.speed: float = 120.0
        self.turn: float = 9.0
        self.shoot_range: float = 52.0
        self.shoot_cd: float = 0.34
        self.damage: float = 3.2
        self.separation_r: float = 9.0

        # Deterministic RNG so the same war front feels consistent (while still alive)
        cell = ctx.get("cell", (WORLD_W // 2, WORLD_H // 2))
        try:
            cx, cy = int(cell[0]), int(cell[1])
        except Exception:
            cx, cy = WORLD_W // 2, WORLD_H // 2

        self.rng = random.Random(deterministic_seed(sim.seed, cx, cy, fid_a, fid_b, int(ctx.get("nonce", 0)), "DOTGROUND"))

        # Battle zone centered on the frontline cell (clamped to WORLD_RECT)
        px, py = cell_to_px_world(cx, cy)
        center = pygame.Vector2(px + TILE * 0.5, py + TILE * 0.5)
        bw, bh = 460, 300
        rect = pygame.Rect(int(center.x - bw // 2), int(center.y - bh // 2), bw, bh)
        rect.clamp_ip(WORLD_RECT.inflate(-18, -18))
        self.zone = rect

        # Player rally point (canvas/world coords)
        self.player_target: Optional[pygame.Vector2] = None

        self.units: List[DotUnit] = []
        self.tracers: List[DotTracer] = []

        # Spawn counts scale gently with macro troop advantage
        t0 = float(sim.factions[player_fid].troops) if player_fid in sim.factions else 100.0
        t1 = float(sim.factions[other_fid].troops) if other_fid in sim.factions else 100.0
        adv = clamp((t0 - t1) / max(120.0, (t0 + t1)), -0.35, 0.35)

        base = 26
        n0 = int(clamp(base + 14.0 * adv + self.rng.randint(-3, 3), 18, 42))
        n1 = int(clamp(base - 14.0 * adv + self.rng.randint(-3, 3), 18, 42))

        self._spawn_team(0, n0)
        self._spawn_team(1, n1)

    def _spawn_team(self, team: int, n: int) -> None:
        z = self.zone
        inset = 26
        left = z.left + inset
        right = z.right - inset
        top = z.top + inset
        bot = z.bottom - inset
        bias = -0.18 if team == 0 else 0.18
        for _ in range(int(n)):
            x = self.rng.uniform(left, right) + bias * z.w
            y = self.rng.uniform(top, bot)
            x = clamp(x, z.left + 8, z.right - 8)
            y = clamp(y, z.top + 8, z.bottom - 8)
            self.units.append(DotUnit(pos=pygame.Vector2(x, y), vel=pygame.Vector2(0, 0), team=team, hp=self.unit_hp, cd=self.rng.random() * 0.25))

    def handle_event(self, ev: pygame.event.Event, cpos: Optional[Tuple[int, int]]):
        if cpos is None:
            return
        mx, my = cpos
        if ev.type == pygame.MOUSEBUTTONDOWN:
            if ev.button == 1 and self.zone.collidepoint(mx, my):
                self.player_target = pygame.Vector2(mx, my)
            elif ev.button == 3:
                self.player_target = None

    def _nearest_enemy(self, u: DotUnit) -> Tuple[Optional[DotUnit], float]:
        best = None
        best_d2 = 1e18
        for v in self.units:
            if v.team == u.team:
                continue
            d2 = (v.pos.x - u.pos.x) ** 2 + (v.pos.y - u.pos.y) ** 2
            if d2 < best_d2:
                best_d2 = d2
                best = v
        return best, best_d2

    def update(self, dt: float):
        # Tracer decay
        if self.tracers:
            alive_tr: List[DotTracer] = []
            for tr in self.tracers:
                tr.t -= dt
                if tr.t > 0.0:
                    alive_tr.append(tr)
            self.tracers = alive_tr

        if self.finished:
            self.finish_timer = max(0.0, self.finish_timer - dt)
            return

        self.time_left = max(0.0, self.time_left - dt)

        # Quick team counts
        c0 = sum(1 for u in self.units if u.team == 0)
        c1 = sum(1 for u in self.units if u.team == 1)

        # Victory checks
        if c0 <= 0 or c1 <= 0 or self.time_left <= 0.0:
            self.finished = True
            self.finish_timer = 1.35

            # Decide winner
            if c0 > c1:
                win_team = 0
                self.decisive = (c1 == 0)
            elif c1 > c0:
                win_team = 1
                self.decisive = (c0 == 0)
            else:
                # Tie-breaker: total HP
                hp0 = sum(u.hp for u in self.units if u.team == 0)
                hp1 = sum(u.hp for u in self.units if u.team == 1)
                win_team = 0 if hp0 >= hp1 else 1
                self.decisive = False

            self.winner_fid = int(self.team_fid[win_team])
            self.loser_fid = int(self.team_fid[1 - win_team])
            return

        # Compute centroids (simple "where the fight is")
        def centroid(team: int) -> pygame.Vector2:
            pts = [u.pos for u in self.units if u.team == team]
            if not pts:
                return pygame.Vector2(self.zone.centerx, self.zone.centery)
            sx = sum(p.x for p in pts)
            sy = sum(p.y for p in pts)
            return pygame.Vector2(sx / len(pts), sy / len(pts))

        cen0 = centroid(0)
        cen1 = centroid(1)

        # AI target drifts toward the player centroid (keeps fight focused)
        ai_target = cen0 + pygame.Vector2(self.rng.uniform(-18, 18), self.rng.uniform(-12, 12))

        z = self.zone

        # Update units
        # Note: we keep this O(n^2) small; unit counts are capped.
        for u in list(self.units):
            u.cd = max(0.0, u.cd - dt)

            enemy, d2 = self._nearest_enemy(u)
            if enemy is None:
                continue

            d = math.sqrt(max(1e-6, d2))
            dir_enemy = (enemy.pos - u.pos) / d

            # Movement target selection
            if u.team == 0 and self.player_target is not None:
                tgt = self.player_target
            else:
                tgt = cen1 if u.team == 0 else ai_target

            to_tgt = pygame.Vector2(tgt.x - u.pos.x, tgt.y - u.pos.y)
            tl = to_tgt.length()
            if tl > 1e-6:
                to_tgt /= tl
            else:
                to_tgt = pygame.Vector2(0, 0)

            # Separation (same team)
            sep = pygame.Vector2(0, 0)
            for v in self.units:
                if v is u or v.team != u.team:
                    continue
                dx = u.pos.x - v.pos.x
                dy = u.pos.y - v.pos.y
                dd2 = dx * dx + dy * dy
                if 1e-6 < dd2 < (self.separation_r * self.separation_r):
                    inv = 1.0 / max(1e-6, math.sqrt(dd2))
                    sep.x += dx * inv
                    sep.y += dy * inv

            seek_w = 0.62
            chase_w = 0.55 if d < 110.0 else 0.12
            sep_w = 0.34
            desired = (to_tgt * seek_w) + (dir_enemy * chase_w) + (sep * sep_w)

            if desired.length_squared() > 1e-6:
                desired = desired.normalize() * self.speed
            else:
                desired = pygame.Vector2(0, 0)

            # Steering
            u.vel += (desired - u.vel) * min(1.0, self.turn * dt)
            u.pos += u.vel * dt

            # Confine to zone
            if u.pos.x < z.left + 4:
                u.pos.x = z.left + 4
                u.vel.x *= -0.35
            if u.pos.x > z.right - 4:
                u.pos.x = z.right - 4
                u.vel.x *= -0.35
            if u.pos.y < z.top + 4:
                u.pos.y = z.top + 4
                u.vel.y *= -0.35
            if u.pos.y > z.bottom - 4:
                u.pos.y = z.bottom - 4
                u.vel.y *= -0.35

            # Fire
            if u.cd <= 0.0 and d <= self.shoot_range:
                u.cd = self.shoot_cd
                enemy.hp -= self.damage
                self.tracers.append(DotTracer(a=pygame.Vector2(u.pos), b=pygame.Vector2(enemy.pos), col=self.team_color[u.team], t=0.10))

                if enemy.hp <= 0.0:
                    fid_dead = int(self.team_fid[enemy.team])
                    self.casualties[fid_dead] = int(self.casualties.get(fid_dead, 0) + 1)
                    try:
                        self.units.remove(enemy)
                    except ValueError:
                        pass

    def draw(self, canvas: pygame.Surface, font: pygame.font.Font, font_big: pygame.font.Font):
        z = self.zone

        # Zone tint + border
        shade = pygame.Surface((z.w, z.h), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 90))
        canvas.blit(shade, (z.x, z.y))
        pygame.draw.rect(canvas, (40, 40, 54), z, 2)

        # Tracers
        for tr in self.tracers:
            pygame.draw.line(canvas, tr.col, (int(tr.a.x), int(tr.a.y)), (int(tr.b.x), int(tr.b.y)), 2)

        # Units (team-colored dots)
        for u in self.units:
            col = self.team_color[u.team]
            pygame.draw.circle(canvas, col, (int(u.pos.x), int(u.pos.y)), 3)

        # Rally point
        if self.player_target is not None:
            p = self.player_target
            pygame.draw.circle(canvas, (245, 245, 245), (int(p.x), int(p.y)), 6, 1)
            pygame.draw.line(canvas, (245, 245, 245), (int(p.x) - 8, int(p.y)), (int(p.x) + 8, int(p.y)), 1)
            pygame.draw.line(canvas, (245, 245, 245), (int(p.x), int(p.y) - 8), (int(p.x), int(p.y) + 8), 1)

        # HUD
        c0 = sum(1 for u in self.units if u.team == 0)
        c1 = sum(1 for u in self.units if u.team == 1)
        title = f"GROUND SKIRMISH: {self.team_name[0]} vs {self.team_name[1]}"
        info = f"{c0} - {c1}   Time: {self.time_left:0.0f}s   LMB rally | RMB clear | ESC exit"
        canvas.blit(font_big.render(title, True, (250, 250, 250)), (z.x + 10, z.y + 8))
        canvas.blit(font.render(info, True, (220, 220, 220)), (z.x + 10, z.y + 34))

        if self.finished and self.winner_fid is not None:
            w = self.team_name[0] if int(self.winner_fid) == int(self.team_fid[0]) else self.team_name[1]
            msg = f"VICTORY: {w}" if self.decisive else f"WINNER: {w}"
            canvas.blit(font_big.render(msg, True, (255, 245, 210)), (z.x + 10, z.y + 58))


# ----------------------------
# Ground Combat (micro battle, 1v1)
# ----------------------------

GC_TILE = 10
GC_W_TILES = 240
GC_H_TILES = 160
GC_W_PX = GC_TILE * GC_W_TILES
GC_H_PX = GC_TILE * GC_H_TILES

GC_UNIT_SPEED = 125.0
GC_UNIT_HP = 34.0
GC_SHOOT_RANGE = 220.0
GC_SHOOT_COOLDOWN = 0.34
GC_DAMAGE_UNIT = 4.0
GC_DAMAGE_BUILDING = 2.2

GC_MAX_SOLDIERS_PER_SIDE = 80
GC_MIN_SOLDIERS_PER_SIDE = 48

@dataclass
class GCTracerFX:
    a: pygame.Vector2
    b: pygame.Vector2
    color: Tuple[int,int,int] = (255, 225, 170)
    life: float = 0.0
    max_life: float = 0.12

    def update(self, dt: float) -> bool:
        self.life += dt
        return self.life < self.max_life

    def draw(self, surface: pygame.Surface, to_screen):
        t = clamp(self.life / self.max_life, 0.0, 1.0)
        alpha = int(255 * (1.0 - t))
        col = (*self.color, alpha)
        ax, ay = to_screen(self.a)
        bx, by = to_screen(self.b)
        if ax is None or bx is None:
            return
        pygame.draw.line(surface, col, (ax, ay), (bx, by), 2)
        # little "hot tip"
        pygame.draw.circle(surface, (255, 240, 210, alpha), (bx, by), 2)

@dataclass
class GCExplosionFX:
    pos: pygame.Vector2
    life: float = 0.0
    max_life: float = 0.55
    max_radius: float = 28.0
    intensity: float = 1.0

    def update(self, dt: float) -> bool:
        self.life += dt
        return self.life < self.max_life

    def draw(self, surface: pygame.Surface, to_screen):
        t = clamp(self.life / self.max_life, 0.0, 1.0)
        r = lerp(2.0, self.max_radius, t)
        alpha = int(210 * (1.0 - t))
        col = (255, 200, 110, alpha)
        sx, sy = to_screen(self.pos)
        if sx is None:
            return
        ring = pygame.Surface((int(r*2+4), int(r*2+4)), pygame.SRCALPHA)
        pygame.draw.circle(ring, col, (ring.get_width()//2, ring.get_height()//2), int(r), 2)
        surface.blit(ring, (sx - ring.get_width()/2, sy - ring.get_height()/2))

@dataclass
class GCUnit:
    team: int                 # 0 or 1 (local battle side)
    fid: int                  # world faction id
    pos: pygame.Vector2
    target: Optional[pygame.Vector2] = None
    hp: float = GC_UNIT_HP
    hp_max: float = GC_UNIT_HP
    cooldown: float = 0.0
    fire_t: float = 0.0
    order_building: Optional[int] = None  # index into buildings list (enemy)
    selected: bool = False

@dataclass
class GCBld:
    b: Building
    team: int                 # 0 or 1 (local battle side)
    fid: int                  # world faction id
    hp: float
    hp_max: float
    is_command: bool = False

class EmbeddedBattle:
    """Embeds the standalone groundcombat module inside the Doomsday window.

    - Draws the battle into WORLD_RECT (keeps UI sidebar).
    - Translates mouse coordinates from Doomsday canvas-space into battle-space.
    - Exposes a GroundCombatSim-like surface API used by the parent Game.
    """

    BATTLE_W, BATTLE_H = 1280, 720

    def __init__(self, sim: "WorldSim", ctx: dict, player_fid: int):
        self.sim = sim
        self.ctx = ctx
        self.team_fid = [player_fid, ctx["fid_b"] if player_fid == ctx["fid_a"] else ctx["fid_a"]]
        self.winner_fid = None
        self.loser_fid = None
        self.finished = False
        self.decisive = False
        self.casualties = {}  # optional; kept for compatibility with _apply_ground_outcome

        # offscreen surface the battle renders to
        self.surface = pygame.Surface((self.BATTLE_W, self.BATTLE_H))

        # dynamic mapping used for mouse transform
        self._blit_rect = pygame.Rect(WORLD_X, WORLD_Y, WORLD_PX_W, WORLD_PX_H)
        self._scale = 1.0
        self._off_x = 0
        self._off_y = 0

        self._pending_events = []

        self._battle = self._load_battle().RTSGame(
            external_surface=self.surface,
            player_team_name=self._name_for(self.team_fid[0]),
            enemy_team_name=self._name_for(self.team_fid[1]),
            team_colors=[self._color_for(self.team_fid[0]), self._color_for(self.team_fid[1])],
        )

    def _name_for(self, fid: int) -> str:
        f = self.sim.factions.get(fid)
        return f.name if f else f"Faction {fid}"

    def _color_for(self, fid: int) -> tuple[int, int, int]:
        f = self.sim.factions.get(fid)
        return f.color if f else (220, 220, 220)

    def _load_battle(self):
        # Load the battle module by filename so you can keep it as a standalone script too.
        here = os.path.abspath(os.path.dirname(__file__))
        path = os.path.join(here, "groundcombat_combatonly.py")
        spec = importlib.util.spec_from_file_location("groundcombat_combatonly", path)
        mod = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(mod)
        return mod

    def _canvas_to_battle(self, cpos: tuple[int, int]) -> tuple[int, int]:
        # cpos is already in Doomsday canvas space (not window space)
        cx, cy = cpos
        lx = cx - self._blit_rect.x - self._off_x
        ly = cy - self._blit_rect.y - self._off_y
        if self._scale <= 0:
            return (0, 0)
        bx = int(lx / self._scale)
        by = int(ly / self._scale)
        return (max(0, min(self.BATTLE_W - 1, bx)), max(0, min(self.BATTLE_H - 1, by)))

    def handle_event(self, ev, cpos: tuple[int, int] | None):
        # Collect events and translate mouse coords to battle-space.
        if ev.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP, pygame.MOUSEMOTION) and cpos is not None:
            bpos = self._canvas_to_battle(cpos)
            data = dict(ev.dict)
            data["pos"] = bpos
            self._pending_events.append(pygame.event.Event(ev.type, data))
        else:
            self._pending_events.append(ev)

    def update(self, dt: float):
        # Advance the embedded battle one frame.
        exit_requested = self._battle.step(dt, self._pending_events, present=False)
        self._pending_events = []

        # Determine victory (combat-only build sets RTSGame.winner when one side is eliminated)
        win_team = getattr(self._battle, "winner", None)
        if win_team is not None and not self.finished:
            self.finished = True
            self.decisive = True
            self.winner_fid = self.team_fid[int(win_team)]
            self.loser_fid = self.team_fid[1 - int(win_team)]

        # If the battle requests exit, keep state; parent ESC will return anyway.
        if exit_requested and not self.finished:
            # treat as abort (no outcome)
            self.finished = False
            self.decisive = False

    def draw(self, canvas: pygame.Surface, font: pygame.font.Font, font_big: pygame.font.Font):
        # Draw battle inside WORLD_RECT, preserving aspect ratio.
        self._blit_rect = WORLD_RECT.copy()
        rect = self._blit_rect

        sx = rect.w / self.BATTLE_W
        sy = rect.h / self.BATTLE_H
        self._scale = min(sx, sy)
        out_w = max(1, int(self.BATTLE_W * self._scale))
        out_h = max(1, int(self.BATTLE_H * self._scale))
        self._off_x = (rect.w - out_w) // 2
        self._off_y = (rect.h - out_h) // 2

        scaled = pygame.transform.smoothscale(self.surface, (out_w, out_h))
        canvas.fill((10, 12, 16))
        canvas.blit(scaled, (rect.x + self._off_x, rect.y + self._off_y))

        # subtle frame
        pygame.draw.rect(canvas, (40, 40, 50), rect, 2)

# ----------------------------
# Persistent Ground War Layer (always visible on the main map)
# ----------------------------

@dataclass
class GroundLayerDot:
    """A small ground unit rendered on the world map."""
    pos: pygame.Vector2
    vel: pygame.Vector2
    rid: int                 # home region id (for patrol dots); -1 for frontline dots
    fid: int                 # faction id for coloring (updated from tile ownership for patrol dots)
    hp: float
    cd: float = 0.0
    next_turn: float = 0.0
    kind: int = 0            # 0 patrol, 1 frontline


@dataclass
class GroundLayerTracer:
    a: pygame.Vector2
    b: pygame.Vector2
    col: Tuple[int, int, int]
    t: float = 0.10


@dataclass
class GroundFrontGroup:
    key: Tuple[int, int, int, int, int, int]   # (a,b,ax,ay,bx,by)
    a: int
    b: int
    center: pygame.Vector2
    units: List[GroundLayerDot] = field(default_factory=list)
    respawn: float = 0.0


class GroundWarLayer:
    """Always-on ground-war visualization.

    What it does:
    - Spawns small patrol dots across ALL regions (land only) so the map always feels populated.
    - When an invasion is active, spawns extra frontline skirmish dots along sampled border edges.
    - Renders under the air jets (so it feels like a lower "ground layer").

    It is intentionally lightweight and mostly visual (macro war logic stays in WorldSim).
    """

    PATROLS_PER_REGION = 24
    PATROL_SPEED = 24.0

    FRONT_REFRESH_S = 0.90
    FRONT_GROUPS_MAX = 12
    FRONT_UNITS_PER_SIDE = 6
    FRONT_SPEED = 70.0
    FRONT_TURN = 10.0
    FRONT_RANGE = 18.0
    FRONT_CD = 0.22
    FRONT_DMG = 2.4
    FRONT_HP = 7.0
    FRONT_TETHER = 42.0

    def __init__(self, sim: "WorldSim"):
        self.sim = sim
        self.rng = random.Random(deterministic_seed(sim.seed, "GROUND_LAYER"))
        self.patrols: List[GroundLayerDot] = []
        self.tracers: List[GroundLayerTracer] = []
        self.front_groups: Dict[Tuple[int,int,int,int,int,int], GroundFrontGroup] = {}

        self._front_timer: float = 0.0

        self._init_patrols()

    def _random_land_cell_in_region(self, rid: int) -> Tuple[int, int]:
        # Fast random attempts, then fallback to capital, then scan.
        for _ in range(400):
            x = self.rng.randrange(WORLD_W)
            y = self.rng.randrange(WORLD_H)
            if self.sim.terrain[y][x] == 1 and self.sim.region_id[y][x] == rid:
                return x, y
        try:
            cx, cy = self.sim.capital_pos[rid]
            if 0 <= cx < WORLD_W and 0 <= cy < WORLD_H and self.sim.terrain[cy][cx] == 1 and self.sim.region_id[cy][cx] == rid:
                return cx, cy
        except Exception:
            pass
        for y in range(WORLD_H):
            for x in range(WORLD_W):
                if self.sim.terrain[y][x] == 1 and self.sim.region_id[y][x] == rid:
                    return x, y
        return WORLD_W // 2, WORLD_H // 2

    def _spawn_patrol(self, rid: int) -> None:
        x, y = self._random_land_cell_in_region(rid)
        px, py = cell_to_px_world(x, y)
        pos = pygame.Vector2(px + self.rng.uniform(1.0, TILE - 1.0), py + self.rng.uniform(1.0, TILE - 1.0))

        ang = self.rng.random() * math.tau
        sp = self.PATROL_SPEED * (0.55 + 0.70 * self.rng.random())
        vel = pygame.Vector2(math.cos(ang) * sp, math.sin(ang) * sp)

        fid = int(self.sim.owner[y][x]) if 0 <= y < WORLD_H and 0 <= x < WORLD_W else -1
        if fid < 0:
            fid = int(self.sim.region_control[rid]) if 0 <= rid < REGION_COUNT else 0

        self.patrols.append(GroundLayerDot(pos=pos, vel=vel, rid=int(rid), fid=int(fid), hp=6.0 + self.rng.random() * 4.0,
                                           cd=self.rng.random() * 0.2, next_turn=self.rng.uniform(0.4, 1.6), kind=0))

    def _init_patrols(self) -> None:
        self.patrols.clear()
        for rid in range(REGION_COUNT):
            for _ in range(self.PATROLS_PER_REGION):
                self._spawn_patrol(rid)

    def _refresh_front_groups(self):
        # Only show frontline skirmishes when an invasion is active.
        if not getattr(self.sim, 'wars', None):
            self.front_groups.clear()
            return

        # In this sim, invasions are globally limited to one at a time.
        try:
            a, b = next(iter(self.sim.wars))
        except Exception:
            self.front_groups.clear()
            return

        edges = []
        try:
            edges = self.sim._compute_frontline(int(a), int(b))
        except Exception:
            edges = []

        if not edges:
            self.front_groups.clear()
            return

        self.rng.shuffle(edges)
        take = min(self.FRONT_GROUPS_MAX, len(edges))
        desired: Set[Tuple[int,int,int,int,int,int]] = set()

        for i in range(take):
            ax, ay, bx, by = edges[i]
            key = (int(a), int(b), int(ax), int(ay), int(bx), int(by))
            desired.add(key)
            if key not in self.front_groups:
                # Group center is between the two bordering cells.
                apx, apy = cell_to_px_world(int(ax), int(ay))
                bpx, bpy = cell_to_px_world(int(bx), int(by))
                center = pygame.Vector2((apx + bpx) * 0.5 + TILE * 0.5, (apy + bpy) * 0.5 + TILE * 0.5)
                grp = GroundFrontGroup(key=key, a=int(a), b=int(b), center=center, units=[], respawn=0.0)
                self.front_groups[key] = grp
                self._spawn_front_units(grp)

        # Drop stale groups
        for k in list(self.front_groups.keys()):
            if k not in desired:
                del self.front_groups[k]

    def _spawn_front_units(self, grp: GroundFrontGroup):
        grp.units.clear()

        # Spawn around the two cells (attacker side near its cell; defender side near its cell).
        _, _, ax, ay, bx, by = grp.key
        apx, apy = cell_to_px_world(ax, ay)
        bpx, bpy = cell_to_px_world(bx, by)

        a_center = pygame.Vector2(apx + TILE * 0.5, apy + TILE * 0.5)
        b_center = pygame.Vector2(bpx + TILE * 0.5, bpy + TILE * 0.5)

        def spawn_side(fid: int, base: pygame.Vector2):
            for _ in range(self.FRONT_UNITS_PER_SIDE):
                off = pygame.Vector2(self.rng.uniform(-6, 6), self.rng.uniform(-6, 6))
                pos = pygame.Vector2(base.x + off.x, base.y + off.y)
                ang = self.rng.random() * math.tau
                sp = self.FRONT_SPEED * (0.35 + 0.45 * self.rng.random())
                vel = pygame.Vector2(math.cos(ang) * sp, math.sin(ang) * sp)
                grp.units.append(GroundLayerDot(pos=pos, vel=vel, rid=-1, fid=int(fid), hp=self.FRONT_HP,
                                                cd=self.rng.random() * 0.25, next_turn=self.rng.uniform(0.25, 0.9), kind=1))

        spawn_side(grp.a, a_center)
        spawn_side(grp.b, b_center)

    def update(self, dt: float):
        # Patrol dots (all regions)
        for d in self.patrols:
            d.next_turn -= dt
            if d.next_turn <= 0.0:
                ang = self.rng.random() * math.tau
                sp = self.PATROL_SPEED * (0.55 + 0.75 * self.rng.random())
                d.vel = pygame.Vector2(math.cos(ang) * sp, math.sin(ang) * sp)
                d.next_turn = self.rng.uniform(0.45, 1.7)

            d.pos += d.vel * dt

            # Bounce inside the world rect
            if d.pos.x < WORLD_RECT.left + 1:
                d.pos.x = WORLD_RECT.left + 1
                d.vel.x = abs(d.vel.x)
            if d.pos.x > WORLD_RECT.right - 1:
                d.pos.x = WORLD_RECT.right - 1
                d.vel.x = -abs(d.vel.x)
            if d.pos.y < WORLD_RECT.top + 1:
                d.pos.y = WORLD_RECT.top + 1
                d.vel.y = abs(d.vel.y)
            if d.pos.y > WORLD_RECT.bottom - 1:
                d.pos.y = WORLD_RECT.bottom - 1
                d.vel.y = -abs(d.vel.y)

            cx, cy = px_to_cell_world(int(d.pos.x), int(d.pos.y))
            if not (0 <= cx < WORLD_W and 0 <= cy < WORLD_H):
                continue

            # Keep patrols on land and inside their home region; if invalid, teleport back.
            if self.sim.terrain[cy][cx] == 0 or self.sim.region_id[cy][cx] != d.rid:
                tx, ty = self._random_land_cell_in_region(d.rid)
                tpx, tpy = cell_to_px_world(tx, ty)
                d.pos = pygame.Vector2(tpx + self.rng.uniform(1.0, TILE - 1.0), tpy + self.rng.uniform(1.0, TILE - 1.0))
                cx, cy = tx, ty

            # Update faction color source from current tile ownership (captures change color immediately)
            fid = int(self.sim.owner[cy][cx])
            if fid >= 0:
                d.fid = fid

        # Tracer decay
        if self.tracers:
            alive: List[GroundLayerTracer] = []
            for t in self.tracers:
                t.t -= dt
                if t.t > 0.0:
                    alive.append(t)
            self.tracers = alive

        # Frontline groups refresh (low frequency)
        self._front_timer -= dt
        if self._front_timer <= 0.0:
            self._front_timer = self.FRONT_REFRESH_S
            self._refresh_front_groups()

        # Frontline group updates (small groups)
        for grp in list(self.front_groups.values()):
            # Split per side
            a_units = [u for u in grp.units if u.fid == grp.a]
            b_units = [u for u in grp.units if u.fid == grp.b]

            if not a_units or not b_units:
                grp.respawn -= dt
                if grp.respawn <= 0.0:
                    grp.respawn = 0.85
                    self._spawn_front_units(grp)
                continue

            # Update both sides
            def step_side(side: List[GroundLayerDot], enemies: List[GroundLayerDot]):
                for u in side:
                    u.cd = max(0.0, u.cd - dt)

                    # Nearest enemy (group-local)
                    e_best = None
                    best_d2 = 1e18
                    for e in enemies:
                        d2 = (e.pos.x - u.pos.x) ** 2 + (e.pos.y - u.pos.y) ** 2
                        if d2 < best_d2:
                            best_d2 = d2
                            e_best = e

                    if e_best is None:
                        continue

                    d = math.sqrt(max(1e-6, best_d2))
                    dir_e = (e_best.pos - u.pos) / d

                    # Pull slightly toward the group center to keep the skirmish localized.
                    to_c = grp.center - u.pos
                    lc = to_c.length()
                    dir_c = (to_c / lc) if lc > 1e-6 else pygame.Vector2(0, 0)

                    desired = (dir_e * 0.82 + dir_c * 0.26)
                    if desired.length() > 1e-6:
                        desired = desired.normalize()
                    desired *= self.FRONT_SPEED

                    u.vel += (desired - u.vel) * min(1.0, self.FRONT_TURN * dt)
                    u.pos += u.vel * dt

                    # Tether
                    off = u.pos - grp.center
                    lo = off.length()
                    if lo > self.FRONT_TETHER and lo > 1e-6:
                        u.pos = grp.center + (off / lo) * self.FRONT_TETHER
                        u.vel *= 0.25

                    # Fire
                    if u.cd <= 0.0 and d <= self.FRONT_RANGE:
                        u.cd = self.FRONT_CD
                        e_best.hp -= self.FRONT_DMG
                        try:
                            fcol = self.sim.factions[u.fid].color if u.fid in self.sim.factions else (220, 220, 220)
                        except Exception:
                            fcol = (220, 220, 220)
                        col = _add_color(fcol, 110)
                        self.tracers.append(GroundLayerTracer(pygame.Vector2(u.pos.x, u.pos.y), pygame.Vector2(e_best.pos.x, e_best.pos.y), col, 0.10))
                        if e_best.hp <= 0.0:
                            try:
                                grp.units.remove(e_best)
                            except ValueError:
                                pass

            step_side(a_units, b_units)
            step_side(b_units, a_units)

    def draw(self, surface: pygame.Surface):
        # Draw patrols first (ambient presence across all regions)
        for d in self.patrols:
            if d.fid < 0:
                continue
            f = self.sim.factions.get(d.fid)
            if not f:
                continue
            fill = _add_color(f.color, 75)
            outline = _mul_color(f.color, 0.35)
            x, y = int(d.pos.x), int(d.pos.y)
            pygame.draw.circle(surface, outline, (x, y), 3)
            pygame.draw.circle(surface, fill, (x, y), 2)

        # Frontline units (slightly larger)
        for grp in self.front_groups.values():
            for u in grp.units:
                f = self.sim.factions.get(u.fid)
                if not f:
                    continue
                fill = _add_color(f.color, 90)
                outline = _mul_color(f.color, 0.30)
                x, y = int(u.pos.x), int(u.pos.y)
                pygame.draw.circle(surface, outline, (x, y), 4)
                pygame.draw.circle(surface, fill, (x, y), 3)

        # Tracers on top
        for t in self.tracers:
            pygame.draw.line(surface, t.col, (int(t.a.x), int(t.a.y)), (int(t.b.x), int(t.b.y)), 2)

class GroundCombatSim:
    """
    Embedded, top-down ground combat that runs inside the Doomsday RTS loop.

    Control model is intentionally similar to groundcombat.py:
    - LMB drag select
    - RMB move / attack (if right-click enemy building)
    - ENTER is handled by the parent game to enter this sim
    - ESC exits to world map (no outcome if you exit before victory)
    """

    def __init__(self, sim: "WorldSim", ctx: dict, player_fid: int):
        self.sim = sim
        self.ctx = ctx

        fid_a = ctx["fid_a"]
        fid_b = ctx["fid_b"]
        if player_fid not in (fid_a, fid_b):
            player_fid = fid_a

        other_fid = fid_b if player_fid == fid_a else fid_a

        # Map to local teams: 0 = player side, 1 = AI side
        self.team_fid = [player_fid, other_fid]
        self.team_name = [
            sim.factions[player_fid].name if player_fid in sim.factions else f"Faction {player_fid}",
            sim.factions[other_fid].name if other_fid in sim.factions else f"Faction {other_fid}",
        ]
        self.team_color = [
            sim.factions[player_fid].color if player_fid in sim.factions else (90, 200, 120),
            sim.factions[other_fid].color if other_fid in sim.factions else (220, 90, 90),
        ]
        self.team_style = [
            sim.factions[player_fid].style if player_fid in sim.factions else "URBAN",
            sim.factions[other_fid].style if other_fid in sim.factions else "URBAN",
        ]

        self.player_team = 0
        self.ai_team = 1

        self.rng = random.Random(deterministic_seed(sim.seed, ctx["cell"][0], ctx["cell"][1], fid_a, fid_b, ctx.get("nonce", 0), "GROUND"))

        # camera in world pixels
        self.camera = pygame.Vector2(0.0, 0.0)
        self.zoom = 1.0

        # selection drag
        self.dragging = False
        self.drag_start = pygame.Vector2(0, 0)
        self.drag_end = pygame.Vector2(0, 0)

        # units/buildings
        self.units: List[GCUnit] = []
        self.buildings: List[GCBld] = []

        self.tracers: List[GCTracerFX] = []
        self.explosions: List[GCExplosionFX] = []

        # roads / civilians / scenery
        self.roads: List[pygame.Rect] = []
        self.civilians: List[dict] = []  # {'pos':Vector2,'vel':Vector2,'panic':float}

        # outcome
        self.finished = False
        self.aborted = False
        self.winner_fid: Optional[int] = None
        self.loser_fid: Optional[int] = None
        self.decisive = False
        self.casualties: Dict[int, int] = {self.team_fid[0]: 0, self.team_fid[1]: 0}
        self._start_counts: Dict[int, int] = {}

        # auto-exit after victory
        self.finish_timer = 0.0
        self.auto_exit_delay = 2.0

        self._ai_timer = 0.0

        # pre-render terrain
        self._bg = self._make_background()

        self._spawn_bases_and_units()
        self._spawn_roads_and_towns()

        # center camera on player base
        p_cmd = self._command_building(team=0)
        if p_cmd:
            cx, cy = self._building_center_world(p_cmd)
            self.camera = pygame.Vector2(cx - WORLD_RECT.w/2, cy - WORLD_RECT.h/2)
        self._clamp_camera()

    # ---------- geometry helpers

    def _clamp_camera(self):
        max_x = max(0, GC_W_PX - WORLD_RECT.w / self.zoom)
        max_y = max(0, GC_H_PX - WORLD_RECT.h / self.zoom)
        self.camera.x = clamp(self.camera.x, 0, max_x)
        self.camera.y = clamp(self.camera.y, 0, max_y)

    def world_to_screen(self, wpos: pygame.Vector2) -> Tuple[Optional[int], Optional[int]]:
        sx = WORLD_RECT.x + int((wpos.x - self.camera.x) * self.zoom)
        sy = WORLD_RECT.y + int((wpos.y - self.camera.y) * self.zoom)
        if sx < WORLD_RECT.x-50 or sy < WORLD_RECT.y-50 or sx > WORLD_RECT.right+50 or sy > WORLD_RECT.bottom+50:
            # allow drawing a bit offscreen, but quickly reject far away
            return None, None
        return sx, sy

    def screen_to_world(self, spos: Tuple[int,int]) -> pygame.Vector2:
        sx, sy = spos
        wx = (sx - WORLD_RECT.x) / self.zoom + self.camera.x
        wy = (sy - WORLD_RECT.y) / self.zoom + self.camera.y
        return pygame.Vector2(wx, wy)

    def _building_rect_world(self, b: Building) -> pygame.Rect:
        rect_tiles = building_tile_rect(b)
        return pygame.Rect(rect_tiles.x * GC_TILE, rect_tiles.y * GC_TILE, rect_tiles.w * GC_TILE, rect_tiles.h * GC_TILE)

    def _building_center_world(self, gb: GCBld) -> Tuple[float,float]:
        r = self._building_rect_world(gb.b)
        return r.centerx, r.centery

    def _command_building(self, team: int) -> Optional[GCBld]:
        for gb in self.buildings:
            if gb.team == team and gb.is_command and not gb.b.destroyed:
                return gb
        return None

    # ---------- build/spawn

    def _make_background(self) -> pygame.Surface:
        surf = pygame.Surface((GC_W_PX, GC_H_PX))
        # base: dusty ground
        base = (45, 40, 34)
        surf.fill(base)

        # add subtle noise
        noise = pygame.Surface((GC_W_PX, GC_H_PX))
        for _ in range(7000):
            x = self.rng.randrange(GC_W_PX)
            y = self.rng.randrange(GC_H_PX)
            v = self.rng.randrange(20)
            noise.set_at((x, y), (base[0]+v, base[1]+v//2, base[2]+v//3))
        noise.set_alpha(55)
        surf.blit(noise, (0, 0))

        # faint grid
        g = pygame.Surface((GC_W_PX, GC_H_PX), pygame.SRCALPHA)
        step = 40
        for x in range(0, GC_W_PX, step):
            pygame.draw.line(g, (0, 0, 0, 14), (x, 0), (x, GC_H_PX))
        for y in range(0, GC_H_PX, step):
            pygame.draw.line(g, (0, 0, 0, 14), (0, y), (GC_W_PX, y))
        surf.blit(g, (0, 0))
        return surf

    def _place_building_cluster(self, team: int, fid: int, style: str, x_min: int, x_max: int):
        """
        Places a command building + supporting buildings for a team in a tile rectangle.
        """
        occ = [[False for _ in range(GC_W_TILES)] for _ in range(GC_H_TILES)]
        # mark existing buildings in occ
        for gb in self.buildings:
            r = building_tile_rect(gb.b)
            for yy in range(r.y, r.y + r.h):
                for xx in range(r.x, r.x + r.w):
                    if 0 <= xx < GC_W_TILES and 0 <= yy < GC_H_TILES:
                        occ[yy][xx] = True

        def can_place(rx, ry, rw, rh) -> bool:
            if rx < 2 or ry < 2 or rx + rw >= GC_W_TILES-2 or ry + rh >= GC_H_TILES-2:
                return False
            for yy in range(ry-1, ry+rh+1):
                for xx in range(rx-1, rx+rw+1):
                    if occ[yy][xx]:
                        return False
            return True

        def stamp(rx, ry, rw, rh):
            for yy in range(ry-1, ry+rh+1):
                for xx in range(rx-1, rx+rw+1):
                    if 0 <= xx < GC_W_TILES and 0 <= yy < GC_H_TILES:
                        occ[yy][xx] = True

        # command building: a big civic
        cmd_kind = "Civic"
        cmd_tw, cmd_th, _ = building_meta(cmd_kind)
        # enlarge a bit for presence
        cmd_tw = max(cmd_tw, 18)
        cmd_th = max(cmd_th, 14)

        for _ in range(300):
            rx = self.rng.randrange(x_min, x_max - cmd_tw)
            ry = self.rng.randrange(GC_H_TILES//2 - 18, GC_H_TILES//2 + 18)
            if can_place(rx, ry, cmd_tw, cmd_th):
                b = Building(kind=cmd_kind, gx=rx, gy=ry, tw=cmd_tw, th=cmd_th, variant=self.rng.randrange(1000), roof=self.rng.randrange(1000),
                             started=True, progress=1.0, build_rate=0.0, damage=0.0, destroyed=False, burn=0.0)
                hp = 850.0
                self.buildings.append(GCBld(b=b, team=team, fid=fid, hp=hp, hp_max=hp, is_command=True))
                stamp(rx, ry, cmd_tw, cmd_th)
                break

        # supporting buildings
        weights = style_build_weights(style, "TOWN")
        # avoid too many labs/barracks here
        tweaked = []
        for k, w in weights:
            if k == "Civic":
                w *= 0.3
            if k == "Lab":
                w *= 0.5
            tweaked.append((k, w))
        for _ in range(8):
            kind = pick_weighted(self.rng, tweaked)
            tw, th, _ = building_meta(kind)
            tw = max(8, min(20, tw))
            th = max(6, min(16, th))
            placed = False
            for _try in range(260):
                rx = self.rng.randrange(x_min, x_max - tw)
                ry = self.rng.randrange(GC_H_TILES//2 - 22, GC_H_TILES//2 + 22)
                if can_place(rx, ry, tw, th):
                    b = Building(kind=kind, gx=rx, gy=ry, tw=tw, th=th,
                                 variant=self.rng.randrange(1000), roof=self.rng.randrange(1000),
                                 started=True, progress=1.0, build_rate=0.0, damage=0.0, destroyed=False, burn=0.0)
                    hp = 260.0 + 10.0 * (tw + th)
                    self.buildings.append(GCBld(b=b, team=team, fid=fid, hp=hp, hp_max=hp, is_command=False))
                    stamp(rx, ry, tw, th)
                    placed = True
                    break
            if not placed:
                break

    
    def _spawn_bases_and_units(self):
        left_box = (10, GC_W_TILES//2 - 42)
        right_box = (GC_W_TILES//2 + 42, GC_W_TILES - 10)
        self._place_building_cluster(0, self.team_fid[0], self.team_style[0], left_box[0], left_box[1])
        self._place_building_cluster(1, self.team_fid[1], self.team_style[1], right_box[0], right_box[1])
    
        def spawn_formation(team: int, fid: int, anchor: pygame.Vector2, facing: int):
            cols, rows = 6, 5
            spacing = 18.0
            start = pygame.Vector2(anchor.x, anchor.y)
            start.x += facing * 70.0
            start.y -= (rows-1) * spacing * 0.5
            count = 0
            for r in range(rows):
                for c in range(cols):
                    if count >= 30:
                        return
                    p = pygame.Vector2(start.x + c * spacing * facing, start.y + r * spacing)
                    p.x += self.rng.uniform(-2.0, 2.0)
                    p.y += self.rng.uniform(-2.0, 2.0)
                    self.units.append(GCUnit(team=team, fid=fid, pos=p))
                    count += 1
    
        cmd0 = self._command_building(0)
        cmd1 = self._command_building(1)
        a0 = pygame.Vector2(*self._building_center_world(cmd0)) if cmd0 else pygame.Vector2(GC_W_PX*0.20, GC_H_PX*0.50)
        a1 = pygame.Vector2(*self._building_center_world(cmd1)) if cmd1 else pygame.Vector2(GC_W_PX*0.80, GC_H_PX*0.50)
    
        spawn_formation(0, self.team_fid[0], a0, facing=+1)
        spawn_formation(1, self.team_fid[1], a1, facing=-1)
    
        self._start_counts[self.team_fid[0]] = sum(1 for u in self.units if u.team == 0)
        self._start_counts[self.team_fid[1]] = sum(1 for u in self.units if u.team == 1)

    
    def _spawn_roads_and_towns(self):
        """Add roads, extra town buildings, and civilians for visual richness."""
        occ = [[False for _ in range(GC_W_TILES)] for _ in range(GC_H_TILES)]
        for gb in self.buildings:
            r = building_tile_rect(gb.b)
            for yy in range(max(0, r.y-1), min(GC_H_TILES, r.y + r.h + 1)):
                for xx in range(max(0, r.x-1), min(GC_W_TILES, r.x + r.w + 1)):
                    occ[yy][xx] = True
    
        def can_place(rx, ry, rw, rh) -> bool:
            if rx < 2 or ry < 2 or rx + rw >= GC_W_TILES-2 or ry + rh >= GC_H_TILES-2:
                return False
            for yy in range(ry-1, ry+rh+1):
                for xx in range(rx-1, rx+rw+1):
                    if occ[yy][xx]:
                        return False
            return True
    
        def stamp(rx, ry, rw, rh):
            for yy in range(ry-1, ry+rh+1):
                for xx in range(rx-1, rx+rw+1):
                    if 0 <= xx < GC_W_TILES and 0 <= yy < GC_H_TILES:
                        occ[yy][xx] = True
    
        self.roads.clear()
        road_w = 3
        midy = GC_H_TILES//2 + self.rng.randint(-3, 3)
        self.roads.append(pygame.Rect(0, (midy - road_w//2) * GC_TILE, GC_W_PX, road_w * GC_TILE))
    
        for _ in range(4):
            rx = self.rng.randint(18, GC_W_TILES-18)
            branch_h = self.rng.randint(GC_H_TILES//2, GC_H_TILES-8)
            top = self.rng.randint(4, GC_H_TILES - branch_h - 4)
            self.roads.append(pygame.Rect((rx - road_w//2) * GC_TILE, top * GC_TILE, road_w * GC_TILE, branch_h * GC_TILE))
    
        for rr in self.roads:
            tx0 = max(0, rr.x // GC_TILE)
            ty0 = max(0, rr.y // GC_TILE)
            tx1 = min(GC_W_TILES-1, (rr.right-1) // GC_TILE)
            ty1 = min(GC_H_TILES-1, (rr.bottom-1) // GC_TILE)
            for yy in range(ty0, ty1+1):
                for xx in range(tx0, tx1+1):
                    occ[yy][xx] = True
    
        town_centers = []
        for _ in range(5):
            cx = self.rng.randint(22, GC_W_TILES-22)
            cy = midy + self.rng.randint(-10, 10)
            town_centers.append((cx, int(clamp(cy, 10, GC_H_TILES-10))))
    
        def add_building(rx, ry, kind, team, fid):
            tw, th, _ = building_meta(kind)
            tw = int(clamp(tw + self.rng.randint(-1, 2), 6, 20))
            th = int(clamp(th + self.rng.randint(-1, 2), 6, 18))
            if not can_place(rx, ry, tw, th):
                return False
            bld = Building(kind=kind, gx=rx, gy=ry, tw=tw, th=th,
                           material=self.rng.randrange(len(MATERIALS)),
                           variant=self.rng.randrange(1000), roof=self.rng.randrange(1000),
                           started=True, progress=1.0, build_rate=0.0, damage=0.0, destroyed=False, burn=0.0)
            hp = 220.0 + (tw*th)*1.0
            self.buildings.append(GCBld(b=bld, team=team, fid=fid, hp=hp, hp_max=hp, is_command=False))
            stamp(rx, ry, tw, th)
            return True
    
        self.civilians.clear()
        for (cx, cy) in town_centers:
            if cx < GC_W_TILES//2:
                team, fid, style = 0, self.team_fid[0], self.team_style[0]
            else:
                team, fid, style = 1, self.team_fid[1], self.team_style[1]
    
            weights = style_build_weights(style, "TOWN")
            for _ in range(self.rng.randint(6, 10)):
                kind = pick_weighted(self.rng, weights)
                for _try in range(80):
                    rx = cx + self.rng.randint(-10, 10)
                    ry = cy + self.rng.randint(-8, 8)
                    if add_building(rx, ry, kind, team, fid):
                        break
    
            for _ in range(self.rng.randint(8, 14)):
                px = (cx + self.rng.uniform(-8, 8)) * GC_TILE + self.rng.uniform(0, GC_TILE)
                py = (cy + self.rng.uniform(-6, 6)) * GC_TILE + self.rng.uniform(0, GC_TILE)
                v = pygame.Vector2(self.rng.uniform(-30, 30), self.rng.uniform(-30, 30))
                self.civilians.append({"pos": pygame.Vector2(px, py), "vel": v, "panic": self.rng.uniform(0.0, 0.5)})


    def _enemy_command_building_index(self) -> Optional[int]:
        for i, gb in enumerate(self.buildings):
            if gb.team == self.player_team and gb.is_command:
                continue
        # enemy is team 0 from AI perspective if player is 0
        # we want AI to attack player's command
        for i, gb in enumerate(self.buildings):
            if gb.team == self.player_team and gb.is_command:
                return i
        return None

    # ---------- input

    def handle_event(self, ev: pygame.event.Event, canvas_pos: Optional[Tuple[int,int]]):
        if ev.type == pygame.KEYDOWN:
            if ev.key == pygame.K_ESCAPE:
                # abort or exit after conclusion
                if not self.finished:
                    self.aborted = True
                # parent will pop mode
            return

        if ev.type == pygame.MOUSEBUTTONDOWN:
            if canvas_pos is None:
                return
            mx, my = canvas_pos
            if not WORLD_RECT.collidepoint(mx, my):
                return
            if ev.button == 1:
                self.dragging = True
                self.drag_start = pygame.Vector2(mx, my)
                self.drag_end = pygame.Vector2(mx, my)
            elif ev.button == 3:
                self._issue_order((mx, my), shift=bool(pygame.key.get_pressed()[pygame.K_LSHIFT] or pygame.key.get_pressed()[pygame.K_RSHIFT]))

        elif ev.type == pygame.MOUSEBUTTONUP:
            if canvas_pos is None:
                return
            mx, my = canvas_pos
            if ev.button == 1 and self.dragging:
                self.drag_end = pygame.Vector2(mx, my)
                self._select_in_drag()
                self.dragging = False

        elif ev.type == pygame.MOUSEMOTION:
            if canvas_pos is None:
                return
            mx, my = canvas_pos
            if self.dragging:
                self.drag_end = pygame.Vector2(mx, my)

    def _select_in_drag(self):
        rect = pygame.Rect(self.drag_start.x, self.drag_start.y, self.drag_end.x - self.drag_start.x, self.drag_end.y - self.drag_start.y)
        rect.normalize()
        # click select
        if rect.w < 6 and rect.h < 6:
            p = self.screen_to_world((int(self.drag_end.x), int(self.drag_end.y)))
            closest = None
            best_d = 1e9
            for u in self.units:
                if u.team != self.player_team:
                    continue
                d = u.pos.distance_to(p)
                if d < 18 and d < best_d:
                    best_d = d
                    closest = u
            for u in self.units:
                if u.team == self.player_team:
                    u.selected = (u is closest)
            return

        for u in self.units:
            if u.team != self.player_team:
                continue
            sx, sy = self.world_to_screen(u.pos)
            if sx is None:
                u.selected = False
                continue
            u.selected = rect.collidepoint((sx, sy))

    def _issue_order(self, canvas_pos: Tuple[int,int], shift: bool = False):
        world = self.screen_to_world(canvas_pos)
        # determine if clicked enemy building
        bidx = self._enemy_building_at(world)
        selected = [u for u in self.units if u.team == self.player_team and u.selected]
        if not selected:
            return

        if bidx is not None:
            target_gb = self.buildings[bidx]
            tgt = pygame.Vector2(*self._building_center_world(target_gb))
            for i, u in enumerate(selected):
                u.order_building = bidx
                # small spread so they don't stack
                spread = pygame.Vector2((i % 10 - 5) * 10, (i // 10 - 2) * 10)
                u.target = tgt + spread
            return

        # else: move order
        for i, u in enumerate(selected):
            u.order_building = None
            spread = pygame.Vector2((i % 12 - 6) * 12, (i // 12 - 2) * 12)
            u.target = world + spread

    def _enemy_building_at(self, world: pygame.Vector2) -> Optional[int]:
        for i, gb in enumerate(self.buildings):
            if gb.team == self.player_team:
                continue
            if gb.b.destroyed:
                continue
            r = self._building_rect_world(gb.b)
            if r.collidepoint((world.x, world.y)):
                return i
        return None

    # ---------- sim update

    
    def update(self, dt: float):
        if dt <= 0:
            return
    
        keys = pygame.key.get_pressed()
        pan = pygame.Vector2(0, 0)
        if keys[pygame.K_a]:
            pan.x -= 1
        if keys[pygame.K_d]:
            pan.x += 1
        if keys[pygame.K_w]:
            pan.y -= 1
        if keys[pygame.K_s]:
            pan.y += 1
        if pan.length_squared() > 0:
            pan = pan.normalize() * 360.0 * dt
            self.camera += pan
            self._clamp_camera()
    
        if self.finished:
            if self.finish_timer > 0:
                self.finish_timer = max(0.0, self.finish_timer - dt)
            self.tracers = [t for t in self.tracers if t.update(dt)]
            self.explosions = [e for e in self.explosions if e.update(dt)]
            for c in self.civilians:
                if self.rng.random() < 0.02:
                    c["vel"] += pygame.Vector2(self.rng.uniform(-20, 20), self.rng.uniform(-20, 20))
                if c["vel"].length_squared() > 55*55:
                    c["vel"].scale_to_length(55)
                c["pos"] += c["vel"] * dt
                c["pos"].x = clamp(c["pos"].x, 10, GC_W_PX-10)
                c["pos"].y = clamp(c["pos"].y, 10, GC_H_PX-10)
            return
    
        self._ai_timer += dt
        if self._ai_timer > 1.2:
            self._ai_timer = 0.0
            ai_units = [u for u in self.units if u.team == self.ai_team]
            cmd = self._command_building(self.player_team)
            if cmd:
                tgt = pygame.Vector2(*self._building_center_world(cmd))
                bid = None
                for i, gb in enumerate(self.buildings):
                    if gb.team == self.player_team and gb.is_command:
                        bid = i
                        break
                for i, u in enumerate(ai_units):
                    if u.target is None or self.rng.random() < 0.35:
                        u.order_building = bid
                        spread = pygame.Vector2((i % 12 - 6) * 14, (i // 12 - 2) * 14)
                        u.target = tgt + spread
    
        sep = [pygame.Vector2(0, 0) for _ in self.units]
        for i, u in enumerate(self.units):
            for j in range(i+1, len(self.units)):
                v = self.units[j]
                delta = u.pos - v.pos
                d = delta.length()
                if 0 < d < 14:
                    push = delta.normalize() * (14 - d) * 2.5
                    sep[i] += push
                    sep[j] -= push
    
        for i, u in enumerate(self.units):
            if u.fire_t > 0:
                u.fire_t = max(0.0, u.fire_t - dt * 4.0)
            if u.cooldown > 0:
                u.cooldown = max(0.0, u.cooldown - dt)
    
            u.pos += sep[i] * dt
    
            if u.target is not None:
                dvec = u.target - u.pos
                if dvec.length() < 6:
                    u.target = None
                else:
                    step = dvec.normalize() * GC_UNIT_SPEED * dt
                    u.pos += step
    
            u.pos.x = clamp(u.pos.x, 20, GC_W_PX-20)
            u.pos.y = clamp(u.pos.y, 20, GC_H_PX-20)
    
        self._handle_combat(dt)
    
        self.tracers = [t for t in self.tracers if t.update(dt)]
        self.explosions = [e for e in self.explosions if e.update(dt)]
    
        for c in self.civilians:
            if self.rng.random() < 0.02:
                c["vel"] += pygame.Vector2(self.rng.uniform(-20, 20), self.rng.uniform(-20, 20))
            if c["vel"].length_squared() > 55*55:
                c["vel"].scale_to_length(55)
            c["pos"] += c["vel"] * dt
            c["pos"].x = clamp(c["pos"].x, 10, GC_W_PX-10)
            c["pos"].y = clamp(c["pos"].y, 10, GC_H_PX-10)
    
        self._check_victory()

    def _handle_combat(self, dt: float):
        # split teams
        team_units = [[], []]
        for u in self.units:
            team_units[u.team].append(u)

        # per unit: shoot closest enemy in range
        for u in list(self.units):
            if u.cooldown > 0:
                continue

            enemies = team_units[1 - u.team]
            best_enemy = None
            best_d = 1e9
            for e in enemies:
                d = u.pos.distance_to(e.pos)
                if d < GC_SHOOT_RANGE and d < best_d:
                    best_d = d
                    best_enemy = e

            if best_enemy is not None:
                if self.rng.random() < 0.88:  # accuracy
                    best_enemy.hp -= GC_DAMAGE_UNIT
                u.cooldown = GC_SHOOT_COOLDOWN
                u.fire_t = 1.0
                self.tracers.append(GCTracerFX(a=pygame.Vector2(u.pos), b=pygame.Vector2(best_enemy.pos), color=(255, 220, 160) if u.team==0 else (255, 190, 130)))
                continue

            # no enemy in range: shoot ordered building if possible
            if u.order_building is not None and 0 <= u.order_building < len(self.buildings):
                gb = self.buildings[u.order_building]
                if gb.b.destroyed or gb.team == u.team:
                    u.order_building = None
                    continue
                cx, cy = self._building_center_world(gb)
                tgt = pygame.Vector2(cx, cy)
                d = u.pos.distance_to(tgt)
                if d < GC_SHOOT_RANGE:
                    if self.rng.random() < 0.92:
                        gb.hp = max(0.0, gb.hp - GC_DAMAGE_BUILDING)
                        dmg_frac = 1.0 - (gb.hp / max(1.0, gb.hp_max))
                        gb.b.damage = clamp(dmg_frac, 0.0, 1.0)
                        gb.b.burn = clamp(gb.b.burn + 0.04, 0.0, 1.0)
                        if gb.hp <= 0.0 and not gb.b.destroyed:
                            gb.b.destroyed = True
                            gb.b.burn = 1.0
                            self.explosions.append(GCExplosionFX(pos=tgt, max_radius=42.0 if gb.is_command else 28.0))
                    u.cooldown = GC_SHOOT_COOLDOWN
                    u.fire_t = 1.0
                    self.tracers.append(GCTracerFX(a=pygame.Vector2(u.pos), b=tgt, color=(255, 210, 150)))
                else:
                    # move closer
                    if u.target is None and self.rng.random() < 0.25:
                        u.target = tgt + pygame.Vector2(self.rng.uniform(-25,25), self.rng.uniform(-25,25))

        # remove dead
        alive = []
        for u in self.units:
            if u.hp > 0:
                alive.append(u)
            else:
                self.casualties[u.fid] = self.casualties.get(u.fid, 0) + 1
                self.explosions.append(GCExplosionFX(pos=pygame.Vector2(u.pos), max_radius=18.0))
        self.units = alive

    
    def _check_victory(self):
        if self.finished:
            return
        team0_alive = any(u.team == 0 for u in self.units)
        team1_alive = any(u.team == 1 for u in self.units)
    
        if (not team0_alive) and team1_alive:
            self.finished = True
            self.winner_fid = self.team_fid[1]
            self.loser_fid = self.team_fid[0]
            self.decisive = True
            self.finish_timer = self.auto_exit_delay
        elif (not team1_alive) and team0_alive:
            self.finished = True
            self.winner_fid = self.team_fid[0]
            self.loser_fid = self.team_fid[1]
            self.decisive = True
            self.finish_timer = self.auto_exit_delay
        elif (not team0_alive) and (not team1_alive):
            self.finished = True
            self.winner_fid = None
            self.loser_fid = None
            self.decisive = False
            self.finish_timer = self.auto_exit_delay

    # ---------- render
    # ---------- render

    def draw(self, canvas: pygame.Surface, font: pygame.font.Font, font_big: pygame.font.Font):
        # background (screen space)
        view = pygame.Rect(int(self.camera.x), int(self.camera.y), int(WORLD_RECT.w / self.zoom), int(WORLD_RECT.h / self.zoom))
        canvas.blit(self._bg, (WORLD_RECT.x, WORLD_RECT.y), area=view)

        # roads (visual)
        for rr in self.roads:
            p0 = pygame.Vector2(rr.x, rr.y)
            sx, sy = self.world_to_screen(p0)
            if sx is None:
                continue
            rw = int(rr.w * self.zoom)
            rh = int(rr.h * self.zoom)
            pygame.draw.rect(canvas, (32, 32, 36), (sx, sy, rw, rh))
            pygame.draw.rect(canvas, (55, 55, 60), (sx, sy, rw, rh), max(1, int(2*self.zoom)))

        # civilians (visual)
        for c in self.civilians:
            sx, sy = self.world_to_screen(c["pos"])
            if sx is None:
                continue
            pygame.draw.circle(canvas, (220, 220, 220), (sx, sy), max(1, int(2*self.zoom)))


        # alpha layer for tracers/explosions
        layer = pygame.Surface((WORLD_RECT.w, WORLD_RECT.h), pygame.SRCALPHA)

        # buildings
        for gb in self.buildings:
            rect_w = self._building_rect_world(gb.b)
            # cull
            if rect_w.right < self.camera.x or rect_w.left > self.camera.x + WORLD_RECT.w/self.zoom:
                continue
            # sprite
            r = building_tile_rect(gb.b)
            px = int((rect_w.x - self.camera.x) * self.zoom) + WORLD_RECT.x
            py = int((rect_w.y - self.camera.y) * self.zoom) + WORLD_RECT.y
            w = int(rect_w.w * self.zoom)
            h = int(rect_w.h * self.zoom)

            # consistent palette per team/style
            base_col = self.team_color[gb.team]
            pal = style_build_palette(self.team_style[gb.team], gb.b.kind, base_col)
            sprite = render_building_base(gb.b.kind, w, h, gb.b.variant, gb.b.roof, pal)

            canvas.blit(sprite, (px, py))

            # damage overlay
            if gb.b.damage > 0.02 or gb.b.destroyed:
                draw_destroyed_overlay(canvas, pygame.Rect(px, py, w, h), gb.b.damage, gb.b.destroyed)

            # health bar (command building only)
            if gb.is_command and not gb.b.destroyed:
                frac = gb.hp / max(1.0, gb.hp_max)
                bar_w = max(34, int(w * 0.55))
                bar_h = 6
                bx = px + (w - bar_w)//2
                by = py - 10
                pygame.draw.rect(layer, (0, 0, 0, 160), (bx, by, bar_w, bar_h))
                pygame.draw.rect(layer, (200, 240, 120, 220), (bx+1, by+1, int((bar_w-2)*frac), bar_h-2))

        # units
        for u in self.units:
            sx, sy = self.world_to_screen(u.pos)
            if sx is None:
                continue
            # translate to layer coords
            lx = sx - WORLD_RECT.x
            ly = sy - WORLD_RECT.y
            self._draw_soldier(layer, (lx, ly), self.team_color[u.team], selected=(u.team==self.player_team and u.selected), firing=(u.fire_t>0.01))

        # tracers/explosions
        for t in self.tracers:
            t.draw(layer, lambda p: (int((p.x - self.camera.x) * self.zoom), int((p.y - self.camera.y) * self.zoom)))
        for e in self.explosions:
            e.draw(layer, lambda p: (int((p.x - self.camera.x) * self.zoom), int((p.y - self.camera.y) * self.zoom)))

        canvas.blit(layer, (WORLD_RECT.x, WORLD_RECT.y))

        # selection box
        if self.dragging:
            rect = pygame.Rect(self.drag_start.x, self.drag_start.y, self.drag_end.x - self.drag_start.x, self.drag_end.y - self.drag_start.y)
            rect.normalize()
            pygame.draw.rect(canvas, (200, 230, 160), rect, 1)

        # HUD
        title = f"GROUND COMBAT: {self.team_name[0]} vs {self.team_name[1]}"
        draw_text(canvas, font_big, title, WORLD_RECT.x + 12, WORLD_RECT.y + 10, (245, 245, 245))
        draw_text(canvas, font, "LMB drag select | RMB move/attack buildings | WASD pan | ESC exit", WORLD_RECT.x + 12, WORLD_RECT.y + 34, (210, 210, 210))

        left_alive = sum(1 for u in self.units if u.team == 0)
        right_alive = sum(1 for u in self.units if u.team == 1)
        draw_text(canvas, font, f"Soldiers: {left_alive}  -  {right_alive}", WORLD_RECT.x + 12, WORLD_RECT.y + 54, (210, 210, 210))

        if self.finished:
            msg = "VICTORY" if self.winner_fid == self.team_fid[self.player_team] else "DEFEAT"
            panel = pygame.Surface((WORLD_RECT.w, 120), pygame.SRCALPHA)
            panel.fill((0, 0, 0, 180))
            canvas.blit(panel, (WORLD_RECT.x, WORLD_RECT.centery - 60))
            draw_text(canvas, font_big, msg, WORLD_RECT.centerx - 60, WORLD_RECT.centery - 18, (255, 240, 200))
            draw_text(canvas, font, "Press ESC to return to world (outcome applied).", WORLD_RECT.centerx - 180, WORLD_RECT.centery + 10, (235, 235, 235))
        elif self.aborted:
            panel = pygame.Surface((WORLD_RECT.w, 120), pygame.SRCALPHA)
            panel.fill((0, 0, 0, 170))
            canvas.blit(panel, (WORLD_RECT.x, WORLD_RECT.centery - 60))
            draw_text(canvas, font_big, "RETREAT", WORLD_RECT.centerx - 70, WORLD_RECT.centery - 18, (255, 230, 180))
            draw_text(canvas, font, "Press ESC again to return (no outcome applied).", WORLD_RECT.centerx - 190, WORLD_RECT.centery + 10, (235, 235, 235))

    def _draw_soldier(self, surface: pygame.Surface, pos: Tuple[int,int], team_col: Tuple[int,int,int], selected: bool, firing: bool):
        x, y = pos

        # shadow
        pygame.draw.ellipse(surface, (0, 0, 0, 90), (x-6, y-2, 12, 5))

        # legs
        leg_col = _mul_color(team_col, 0.62)
        pygame.draw.line(surface, (*leg_col, 255), (x-2, y+4), (x-4, y+9), 2)
        pygame.draw.line(surface, (*leg_col, 255), (x+2, y+4), (x+4, y+9), 2)

        # body
        body_col = team_col
        pygame.draw.rect(surface, (*body_col, 255), (x-4, y-6, 8, 10), border_radius=2)
        pygame.draw.rect(surface, (15, 15, 15, 210), (x-4, y-6, 8, 10), 1, border_radius=2)

        # head + helmet
        pygame.draw.circle(surface, (210, 185, 165, 255), (x, y-10), 3)
        pygame.draw.arc(surface, (40, 40, 40, 255), (x-4, y-13, 8, 7), math.pi, 2*math.pi, 2)

        # gun
        gun_col = (210, 210, 210, 240)
        pygame.draw.line(surface, gun_col, (x+3, y-4), (x+11, y-2), 2)
        pygame.draw.line(surface, (40, 40, 40, 220), (x+3, y-4), (x+11, y-2), 1)

        # muzzle flash
        if firing:
            pygame.draw.circle(surface, (255, 240, 210, 220), (x+12, y-2), 2)

        # selection ring
        if selected:
            pygame.draw.circle(surface, (200, 230, 140, 220), (x, y+3), 10, 1)

# ----------------------------
# Embedded launcher support
# ----------------------------

@dataclass
class LauncherEntry:
    key: str
    label: str
    rel_path: Optional[str]  # None => Doomsday Map


def _project_root() -> str:
    try:
        return os.path.dirname(os.path.abspath(__file__))
    except Exception:
        return os.getcwd()


@contextlib.contextmanager
def _pushd(path: str):
    prev = os.getcwd()
    try:
        os.chdir(path)
        yield
    finally:
        try:
            os.chdir(prev)
        except Exception:
            pass


class _PygameEmbedGuard:
    """Sandbox a subset of pygame globals so embedded modules cannot steal the window/event queue."""

    def __init__(self, allow_display_surface: Optional[pygame.Surface] = None,
                 mouse_pos: Optional[Tuple[int,int]] = None,
                 mouse_buttons: Optional[Tuple[bool,bool,bool]] = None):
        self.allow_display_surface = allow_display_surface
        self.mouse_pos = tuple(mouse_pos) if mouse_pos is not None else (0, 0)
        self.mouse_buttons = tuple(mouse_buttons) if mouse_buttons is not None else (False, False, False)
        self._orig = {}

    def __enter__(self):
        # Display functions
        self._orig['set_mode'] = pygame.display.set_mode
        self._orig['flip'] = pygame.display.flip
        self._orig['update'] = pygame.display.update
        self._orig['set_caption'] = pygame.display.set_caption

        def safe_set_mode(size, flags=0, depth=0, display=0, vsync=0):
            surf = pygame.display.get_surface()
            if surf is not None:
                return surf
            # Fallback (headless or called before a display exists)
            try:
                return self._orig['set_mode'](size, flags)
            except Exception:
                return pygame.Surface(size)

        pygame.display.set_mode = safe_set_mode
        pygame.display.flip = lambda *a, **k: None
        pygame.display.update = lambda *a, **k: None
        pygame.display.set_caption = lambda *a, **k: None

        # Event access: prevent embedded code from draining the global queue.
        self._orig['event_get'] = pygame.event.get
        self._orig['event_poll'] = pygame.event.poll
        self._orig['event_wait'] = pygame.event.wait

        pygame.event.get = lambda *a, **k: []
        pygame.event.poll = lambda *a, **k: pygame.event.Event(pygame.NOEVENT, {})
        pygame.event.wait = lambda *a, **k: pygame.event.Event(pygame.NOEVENT, {})

        # Mouse functions: expose host-translated local coordinates/buttons.
        self._orig['mouse_get_pos'] = pygame.mouse.get_pos
        self._orig['mouse_get_pressed'] = pygame.mouse.get_pressed
        pygame.mouse.get_pos = lambda *a, **k: tuple(int(v) for v in self.mouse_pos)
        pygame.mouse.get_pressed = lambda *a, **k: tuple(bool(v) for v in self.mouse_buttons)

        return self

    def __exit__(self, exc_type, exc, tb):
        for k, v in self._orig.items():
            if k == 'set_mode':
                pygame.display.set_mode = v
            elif k == 'flip':
                pygame.display.flip = v
            elif k == 'update':
                pygame.display.update = v
            elif k == 'set_caption':
                pygame.display.set_caption = v
            elif k == 'event_get':
                pygame.event.get = v
            elif k == 'event_poll':
                pygame.event.poll = v
            elif k == 'event_wait':
                pygame.event.wait = v
            elif k == 'mouse_get_pos':
                pygame.mouse.get_pos = v
            elif k == 'mouse_get_pressed':
                pygame.mouse.get_pressed = v
        return False


class EmbeddedAppWrapper:
    """Loads and runs another game module *inside* WORLD_RECT.

    This wrapper is defensive by design: missing files, missing entry points, or runtime
    errors will not crash Doomsday; instead it shows an error panel and writes a report.
    """

    def __init__(self, abs_py_path: str, world_rect: pygame.Rect, launch_ctx: Optional[dict] = None):
        self.abs_py_path = abs_py_path
        self.world_rect = world_rect
        self.launch_ctx = dict(launch_ctx or {})
        self.module = None
        self.instance = None
        self.native_size: Tuple[int, int] = (world_rect.w, world_rect.h)
        self.surface = pygame.Surface(self.native_size).convert_alpha()
        self.error: Optional[str] = None
        self.paused: bool = False
        self._frozen_frame: Optional[pygame.Surface] = None
        self._pending_events: List[pygame.event.Event] = []
        self._mouse_pos: Tuple[int, int] = (0, 0)
        self._mouse_buttons: Tuple[bool, bool, bool] = (False, False, False)
        self._return_mode: str = 'keep_true'
        # Rendering strategy:
        # - Many of your embedded games draw directly into the provided external surface
        #   during `step()` (common for simple Pygame apps converted to "embedded" mode).
        # - Some games expose a `draw(surface)` / `render(surface)` method and expect the
        #   host to call it each frame.
        # The host must NOT clear the surface after `step()` or it will wipe the frame.
        self._has_explicit_draw_api: bool = False

    def _write_crash(self, stage: str, exc: BaseException):
        root = _project_root()
        out_path = os.path.join(root, 'crash_report_launcher.txt')
        try:
            with open(out_path, 'a', encoding='utf-8') as f:
                f.write("\n" + '='*78 + "\n")
                f.write(f"EMBEDDED CRASH ({stage})\n")
                f.write(f"FILE: {self.abs_py_path}\n")
                # Diagnostics to debug module import/path issues
                try:
                    _mod_dir = os.path.dirname(self.abs_py_path)
                    f.write(f"CWD: {os.getcwd()}\n")
                    f.write(f"MOD_DIR: {_mod_dir}\n")
                    f.write("SYS_PATH (top 10):\n")
                    for _i, _p in enumerate(sys.path[:10]):
                        f.write(f"  [{_i}] {_p}\n")
                    try:
                        _py = [n for n in os.listdir(_mod_dir) if n.lower().endswith('.py')]
                        _py.sort()
                        f.write("MOD_DIR .py files:\n")
                        for n in _py[:200]:
                            f.write(f"  {n}\n")
                    except Exception:
                        pass
                except Exception:
                    pass
                f.write("TRACEBACK:\n")
                f.write(''.join(traceback.format_exception(type(exc), exc, exc.__traceback__)))
        except Exception:
            pass


    def _native_resolution_from_module(self, mod) -> Tuple[int, int]:
        candidates = [
            ('WIDTH', 'HEIGHT'),
            ('SCREEN_W', 'SCREEN_H'),
            ('DEFAULT_W', 'DEFAULT_H'),
            ('CANVAS_W', 'CANVAS_H'),
        ]
        for wa, ha in candidates:
            try:
                w = int(getattr(mod, wa))
                h = int(getattr(mod, ha))
                if w > 64 and h > 64:
                    return (w, h)
            except Exception:
                pass
        return (self.world_rect.w, self.world_rect.h)

    def _set_native_size(self, size: Tuple[int, int]) -> None:
        w = max(64, int(size[0]))
        h = max(64, int(size[1]))
        self.native_size = (w, h)
        self.surface = pygame.Surface(self.native_size).convert_alpha()

    def set_viewport_rect(self, world_rect: pygame.Rect) -> None:
        self.world_rect = world_rect.copy()

    def local_from_canvas(self, canvas_pos: Tuple[int, int]) -> Optional[Tuple[int, int]]:
        if not self.world_rect.collidepoint(canvas_pos):
            return None
        rx = (canvas_pos[0] - self.world_rect.x) / max(1, self.world_rect.w)
        ry = (canvas_pos[1] - self.world_rect.y) / max(1, self.world_rect.h)
        lx = int(clamp(rx * self.native_size[0], 0, self.native_size[0] - 1))
        ly = int(clamp(ry * self.native_size[1], 0, self.native_size[1] - 1))
        return (lx, ly)

    def _normalize_result(self, raw) -> bool:
        try:
            base = os.path.basename(self.abs_py_path).lower()
        except Exception:
            base = ''
        if base == 'battle.py':
            return not bool(raw)
        if base in ('vehicles.py', 'naval.py'):
            return bool(raw) if raw is not None else True
        return True if raw is None else bool(raw)

    def _translate_mouse_event(self, ev: pygame.event.Event, local_pos: Optional[Tuple[int, int]]):
        if local_pos is None:
            return ev
        try:
            d = ev.dict.copy()
        except Exception:
            d = {}
        d['pos'] = local_pos
        if ev.type == pygame.MOUSEMOTION and 'rel' in d:
            try:
                d['rel'] = (int(d['rel'][0]), int(d['rel'][1]))
            except Exception:
                pass
        return pygame.event.Event(ev.type, d)

    def load(self) -> bool:
        self.error = None
        self.module = None
        self.instance = None

        if not os.path.isfile(self.abs_py_path):
            self.error = f'Missing file: {self.abs_py_path}'
            return False

        mod_dir = os.path.dirname(self.abs_py_path)
        mod_name = 'embedded_' + hex(_stable_hash32(self.abs_py_path))[2:]

        try:
            with _pushd(mod_dir), _PygameEmbedGuard():
                # Ensure the embedded game's folder is importable (supports local imports like `import x_country_fx`).
                if mod_dir and mod_dir not in sys.path:
                    sys.path.insert(0, mod_dir)
                spec = importlib.util.spec_from_file_location(mod_name, self.abs_py_path)
                if spec is None or spec.loader is None:
                    self.error = 'Could not load module spec.'
                    return False
                mod = importlib.util.module_from_spec(spec)
                sys.modules[mod_name] = mod
                spec.loader.exec_module(mod)
                self.module = mod
                self._set_native_size(self._native_resolution_from_module(mod))
                try:
                    base = os.path.basename(self.abs_py_path).lower()
                    self._return_mode = 'done_true' if base == 'battle.py' else 'keep_true'
                except Exception:
                    self._return_mode = 'keep_true'

                # Try common entry points.
                factory_names = ['create_embedded', 'create_game', 'make_game', 'create_app']
                for fn in factory_names:
                    if hasattr(mod, fn) and callable(getattr(mod, fn)):
                        self.instance = self._call_factory(getattr(mod, fn))
                        break

                if self.instance is None:
                    # Try common class names.
                    for cls_name in ['Game', 'App', 'Main', 'Runner', 'RTSGame']:
                        if hasattr(mod, cls_name):
                            cls = getattr(mod, cls_name)
                            if isinstance(cls, type):
                                self.instance = self._construct(cls)
                                break

            # Determine whether we should call a draw API (and thus clear before drawing),
            # or assume the game renders during `step()`.
            try:
                inst = self.instance
                self._has_explicit_draw_api = bool(
                    inst is not None and (
                        (hasattr(inst, 'draw') and callable(getattr(inst, 'draw')))
                        or (hasattr(inst, 'render') and callable(getattr(inst, 'render')))
                        or (hasattr(inst, 'blit_to') and callable(getattr(inst, 'blit_to')))
                    )
                )
            except Exception:
                self._has_explicit_draw_api = False

            if self.instance is None:
                self.error = 'No compatible entry point found (expected create_embedded/create_game or Game/App class).'
                return False

            return True

        except Exception as e:
            self._write_crash('load', e)
            self.error = f'Load failed: {e.__class__.__name__}: {e}'
            return False

    def _call_factory(self, fn):
        # Pass only accepted kwargs.
        kwargs = {
            'external_surface': self.surface,
            'surface': self.surface,
            'screen': self.surface,
            'target_surface': self.surface,
            'viewport_rect': self.world_rect.copy(),
            'rect': self.world_rect.copy(),
            'doomsday_ctx': self.launch_ctx.get('doomsday_ctx'),
            'player_team_name': self.launch_ctx.get('player_team_name'),
            'enemy_team_name': self.launch_ctx.get('enemy_team_name'),
            'team_colors': self.launch_ctx.get('team_colors'),
        }
        try:
            sig = inspect.signature(fn)
            accepted = {}
            for k, v in kwargs.items():
                if k in sig.parameters:
                    accepted[k] = v
            return fn(**accepted)
        except TypeError:
            try:
                return fn(self.surface)
            except Exception:
                return fn()

    def _construct(self, cls):
        kwargs = {
            'external_surface': self.surface,
            'surface': self.surface,
            'screen': self.surface,
            'target_surface': self.surface,
            'viewport_rect': self.world_rect.copy(),
            'rect': self.world_rect.copy(),
            'doomsday_ctx': self.launch_ctx.get('doomsday_ctx'),
            'player_team_name': self.launch_ctx.get('player_team_name'),
            'enemy_team_name': self.launch_ctx.get('enemy_team_name'),
            'team_colors': self.launch_ctx.get('team_colors'),
        }
        try:
            sig = inspect.signature(cls.__init__)
            accepted = {}
            for k, v in kwargs.items():
                if k in sig.parameters:
                    accepted[k] = v
            # Remove 'self' if present
            accepted.pop('self', None)
            return cls(**accepted)
        except TypeError:
            try:
                return cls(self.surface)
            except Exception:
                return cls()

    def stop(self):
        inst = self.instance
        self.instance = None
        self.module = None
        self._pending_events.clear()
        if inst is None:
            return
        try:
            for name in ('shutdown', 'quit', 'close', 'cleanup'):
                if hasattr(inst, name) and callable(getattr(inst, name)):
                    getattr(inst, name)()
                    break
        except Exception:
            pass

    def pause(self):
        """Pause updates for this embedded game (state preserved)."""
        self.paused = True
        try:
            if self._frozen_frame is None:
                self._frozen_frame = self.surface.copy()
        except Exception:
            pass
        inst = self.instance
        if inst is not None:
            for name in ('pause', 'on_pause'):
                try:
                    if hasattr(inst, name) and callable(getattr(inst, name)):
                        getattr(inst, name)()
                        break
                except Exception:
                    pass
            # Best-effort: pause audio globally while this game is inactive.
            try:
                _doomsday_stop_all_audio()
            except Exception:
                pass

    def resume(self):
        """Resume updates for this embedded game."""
        self.paused = False
        self._frozen_frame = None
        inst = self.instance
        if inst is not None:
            for name in ('resume', 'on_resume'):
                try:
                    if hasattr(inst, name) and callable(getattr(inst, name)):
                        getattr(inst, name)()
                        break
                except Exception:
                    pass
            # Subgames manage their own audio; hub does not auto-resume.

    def handle_event(self, ev: pygame.event.Event, local_pos: Optional[Tuple[int,int]] = None):
        if self.instance is None:
            return
        try:
            if local_pos is not None:
                self._mouse_pos = (int(local_pos[0]), int(local_pos[1]))
            if ev.type == pygame.MOUSEBUTTONDOWN:
                btns = list(self._mouse_buttons)
                if 1 <= int(getattr(ev, 'button', 0)) <= 3:
                    btns[int(ev.button) - 1] = True
                self._mouse_buttons = tuple(btns)
            elif ev.type == pygame.MOUSEBUTTONUP:
                btns = list(self._mouse_buttons)
                if 1 <= int(getattr(ev, 'button', 0)) <= 3:
                    btns[int(ev.button) - 1] = False
                self._mouse_buttons = tuple(btns)
            tev = self._translate_mouse_event(ev, local_pos)
            if hasattr(self.instance, 'handle_event') and callable(getattr(self.instance, 'handle_event')):
                self.instance.handle_event(tev, local_pos)
            else:
                self._pending_events.append(tev)
        except Exception as e:
            self._write_crash('handle_event', e)
            self.error = f'Runtime error: {e.__class__.__name__}: {e}'
            self.instance = None
    def update(self, dt: float):
        if self.instance is None:
            return
        if self.paused:
            return
        mod_dir = os.path.dirname(self.abs_py_path)
        try:
            with _pushd(mod_dir), _PygameEmbedGuard(mouse_pos=self._mouse_pos, mouse_buttons=self._mouse_buttons):
                evs = self._pending_events
                self._pending_events = []

                # Preferred API: step(dt, events, present=False)
                if hasattr(self.instance, 'step') and callable(getattr(self.instance, 'step')):
                    try:
                        raw = self.instance.step(dt, evs, present=False)
                    except TypeError:
                        try:
                            raw = self.instance.step(dt, evs)
                        except TypeError:
                            raw = self.instance.step(dt)
                    return self._normalize_result(raw)

                # Common API: update(dt, events)
                if hasattr(self.instance, 'update') and callable(getattr(self.instance, 'update')):
                    try:
                        raw = self.instance.update(dt, evs)
                    except TypeError:
                        raw = self.instance.update(dt)
                    return self._normalize_result(raw)

                # Fallback: tick(dt)
                if hasattr(self.instance, 'tick') and callable(getattr(self.instance, 'tick')):
                    try:
                        raw = self.instance.tick(dt, evs)
                    except TypeError:
                        raw = self.instance.tick(dt)
                    return self._normalize_result(raw)

        except Exception as e:
            self._write_crash('update', e)
            self.error = f'Runtime error: {e.__class__.__name__}: {e}'
            self.instance = None

    def draw(self, target: pygame.Surface):
        # If paused, present the last rendered frame.
        if self.paused and self._frozen_frame is not None and not self.error:
            try:
                target.blit(self._frozen_frame, self.world_rect.topleft)
            except Exception:
                pass
            return

        # Only clear if we will actively call an explicit draw API. If the embedded
        # game rendered during `step()`, clearing here would wipe the frame and
        # result in a black screen.
        if self._has_explicit_draw_api:
            self.surface.fill((0, 0, 0, 0))

        if self.error:
            # Error panel
            panel = pygame.Surface((self.world_rect.w, self.world_rect.h), pygame.SRCALPHA)
            panel.fill((0, 0, 0, 220))
            target.blit(panel, self.world_rect.topleft)
            return

        if self.instance is None:
            panel = pygame.Surface((self.world_rect.w, self.world_rect.h), pygame.SRCALPHA)
            panel.fill((0, 0, 0, 210))
            target.blit(panel, self.world_rect.topleft)
            return

        if self._has_explicit_draw_api:
            mod_dir = os.path.dirname(self.abs_py_path)
            try:
                with _pushd(mod_dir), _PygameEmbedGuard():
                    # Preferred API: draw(surface)
                    if hasattr(self.instance, 'draw') and callable(getattr(self.instance, 'draw')):
                        try:
                            self.instance.draw(self.surface)
                        except TypeError:
                            self.instance.draw()
                    elif hasattr(self.instance, 'render') and callable(getattr(self.instance, 'render')):
                        try:
                            self.instance.render(self.surface)
                        except TypeError:
                            self.instance.render()
                    elif hasattr(self.instance, 'blit_to') and callable(getattr(self.instance, 'blit_to')):
                        self.instance.blit_to(self.surface)

            except Exception as e:
                self._write_crash('draw', e)
                self.error = f'Runtime error: {e.__class__.__name__}: {e}'
                self.instance = None

        # Composite: preserve each game's native resolution and scale it into the map area.
        try:
            if self.surface.get_size() != (self.world_rect.w, self.world_rect.h):
                scaled = pygame.transform.smoothscale(self.surface, (self.world_rect.w, self.world_rect.h))
                target.blit(scaled, self.world_rect.topleft)
            else:
                target.blit(self.surface, self.world_rect.topleft)
        except Exception:
            target.blit(self.surface, self.world_rect.topleft)

class ExternalToolWindowProcess:
    """Manage a sub-game running in a separate, IPC-controlled tool window.

    This is used for modes that must open their own resizable/movable window,
    remain running in the background, and pause/hide on ESC.
    """

    def __init__(self, abs_py_path: str, title: str = 'Apocalyptic Combat'):
        self.abs_py_path = abs_py_path
        self.title = title
        self.port: int | None = None
        self.proc: subprocess.Popen | None = None

    def _alloc_port(self) -> int:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.bind(('127.0.0.1', 0))
            port = int(sock.getsockname()[1])
            sock.close()
            return port
        except Exception:
            # Best-effort fallback
            return 38999

    def is_running(self) -> bool:
        try:
            return self.proc is not None and (self.proc.poll() is None)
        except Exception:
            return False

    def ensure_running(self, start_hidden: bool = False) -> bool:
        if self.is_running() and self.port:
            return True

        if not os.path.isfile(self.abs_py_path):
            return False

        self.port = self._alloc_port()
        cmd = [
            sys.executable,
            self.abs_py_path,
            '--doomsday-toolwindow',
            '--port', str(int(self.port)),
            '--start-hidden', '1' if start_hidden else '0',
            '--hide-taskbar', '1',
            '--title', str(self.title),
        ]
        try:
            self.proc = subprocess.Popen(cmd, cwd=os.path.dirname(self.abs_py_path))
            return True
        except Exception:
            self.proc = None
            return False

    def _send(self, cmd: str):
        if not self.port:
            return
        try:
            with socket.create_connection(('127.0.0.1', int(self.port)), timeout=0.15) as c:
                c.sendall((cmd.strip().upper() + '\n').encode('utf-8'))
        except Exception:
            return

    def show(self):
        if self.ensure_running(start_hidden=False):
            # SHOW then RESUME (order matters when first-launching hidden).
            self._send('SHOW')
            self._send('RESUME')

    def hide(self):
        # Pause first, then hide.
        self._send('PAUSE')
        self._send('HIDE')

    def quit(self):
        # Ask politely, then terminate if needed.
        try:
            self._send('QUIT')
        except Exception:
            pass
        try:
            if self.proc is not None and self.proc.poll() is None:
                self.proc.terminate()
        except Exception:
            pass



class StandaloneModeProcess:
    """Run a mode as a true standalone process (its own pygame window).

    Integration model:
    - Launcher writes a context JSON before launch.
    - Mode may optionally write a result JSON on exit.
    - If no explicit result is provided, the launcher applies a small, time-based skirmish impact
      against the currently active invasion (if any).
    """

    def __init__(self, key: str, abs_py_path: str, title: str):
        self.key = key
        self.abs_py_path = abs_py_path
        self.title = title
        self.proc: subprocess.Popen | None = None
        self.started_at: float | None = None
        self.launch_ctx: dict | None = None

    def is_running(self) -> bool:
        try:
            return self.proc is not None and (self.proc.poll() is None)
        except Exception:
            return False

    def launch(self, ctx: dict | None = None) -> bool:
        if self.is_running():
            return True
        if not os.path.isfile(self.abs_py_path):
            return False
        self.launch_ctx = ctx
        self.started_at = time.time()
        cmd = [sys.executable, self.abs_py_path]
        try:
            self.proc = subprocess.Popen(cmd, cwd=os.path.dirname(self.abs_py_path))
            return True
        except Exception:
            self.proc = None
            return False

    def poll_exit_code(self) -> int | None:
        try:
            if self.proc is None:
                return None
            return self.proc.poll()
        except Exception:
            return None

    def terminate(self):
        try:
            if self.proc is not None and self.proc.poll() is None:
                self.proc.terminate()
        except Exception:
            pass


def build_launcher_entries() -> List[LauncherEntry]:
    """Build launcher entries for the local single-file modes shipped with this project.

    These entries intentionally target the sibling Python files in the current project
    directory so the war map can launch them directly without requiring missing
    subfolders.
    """
    return [
        LauncherEntry('ground', 'Battle', 'battle.py'),
        LauncherEntry('vehicular', 'Vehicles', 'vehicles.py'),
        LauncherEntry('naval', 'Naval', 'naval.py'),
        LauncherEntry('future', 'Air', None),
        LauncherEntry('doomsday', 'Return to Map', None),
    ]



# ----------------------------
# UI / Game
# ----------------------------

class Game:
    MODE_WORLD = 0
    MODE_AREA = 1
    MODE_GROUND_PICK = 2
    MODE_GROUND = 3

    def __init__(self):
        pygame.init()
        # Ensure Doomsday has its own audio folder and a fallback loop.
        _doomsday_ensure_map_audio()
        pygame.display.set_caption("Regions at War (RTS Prototype)")

        self.window = pygame.display.set_mode((CANVAS_W, CANVAS_H), pygame.RESIZABLE)
        self.canvas = pygame.Surface((CANVAS_W, CANVAS_H))
        self.win_size = (CANVAS_W, CANVAS_H)
        self._present = (1.0, 0, 0)  # scale, off_x, off_y

        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont(["georgia", "cambria", "palatinolinotype", "timesnewroman"], 18)
        self.font_small = pygame.font.SysFont(["georgia", "cambria", "palatinolinotype", "timesnewroman"], 15)
        self.font_big = pygame.font.SysFont(["georgia", "cambria", "palatinolinotype", "timesnewroman"], 24, bold=True)
        self.font_huge = pygame.font.SysFont(["georgia", "cambria", "palatinolinotype", "timesnewroman"], 32, bold=True)
        self.sim = WorldSim()
        # Air combat overlay (` key). Runs continuously in the background over the world map.
        self.air_mode = False
        self.air_overlay = AirCombatOverlay(self.sim)
        # Ground war layer (always visible on the world map).
        self.ground_layer = GroundWarLayer(self.sim)

        # Player faction is auto-assigned at startup. TAB cycles through living factions.
        self.player_fid: Optional[int] = None
        self.enemy_fid: Optional[int] = None
        self.team_select_active: bool = False


        self.mode = self.MODE_WORLD
        self.paused = False
        self.speed_index = SPEED_LEVELS.index(2.0)
        self.time_accum = 0.0

        # Area view state
        self.area_cell: Optional[Tuple[int,int]] = None
        self.area_theme: str = "WILDS"
        self.area_owner: int = -1
        self.area_map: Optional[LocalMap] = None

        # Ground combat state
        self.ground_pick: Optional[dict] = None
        self.ground: Optional[GroundCombatSim] = None
        # Launcher modes run embedded inside WORLD_RECT while the sidebar stays visible.
        self.launcher_entries: List[LauncherEntry] = build_launcher_entries()
        self.active_launcher_key: str = 'doomsday'
        # Standalone mode processes (key -> StandaloneModeProcess).
        self.mode_procs: dict[str, StandaloneModeProcess] = {}
        # Per-launch bookkeeping to apply results back to the macro sim.
        self._mode_launch_info: dict[str, dict] = {}

        # Back-compat stubs (embedding removed; kept to avoid stray attribute errors)
        self.embedded = None
        self.embedded_cache = {}

        # External tool windows are unused in the final integrated build.
        self.external_windows: dict[str, ExternalToolWindowProcess] = {}
        self._launcher_clicks: List[Tuple[pygame.Rect, str]] = []

        # Launcher availability: all entries are available from the start.
        # This set exists so future progression systems can lock/unlock entries without
        # changing UI wiring.
        self.unlocked_launcher_keys: Set[str] = set(e.key for e in self.launcher_entries)

        # Mode progression bookkeeping for the final integrated build.
        self.mode_unlock_order = ['ground', 'vehicular', 'naval', 'future']
        self.mode_unlock_interval = 300.0  # seconds
        self.total_mode_play_seconds = 0.0
        self.mode_play_seconds: Dict[str, float] = {k: 0.0 for k in ['ground','vehicular','naval','future']}
        self.apocalypse_unlocked = False

        # Holographic theme cache
        self._holo_cache: dict[tuple[int,int,str], pygame.Surface] = {}
        self._holo_noise_tile: Optional[pygame.Surface] = None

        # UI toast / feedback (short-lived on-screen messages)
        self.toast_msg: str = ""
        self.toast_timer: float = 0.0
        self.feed_scroll: int = 0

        # Start the run already enlisted in a random living faction.
        self._auto_assign_player_faction(randomize=True, announce=False)

    def _entry_enabled(self, key: str) -> bool:
        try:
            return key in getattr(self, 'unlocked_launcher_keys', set())
        except Exception:
            return True

    def _living_faction_ids(self) -> List[int]:
        ids: List[int] = []
        try:
            for fid, f in self.sim.factions.items():
                if len(getattr(f, 'regions', [])) > 0:
                    ids.append(int(fid))
        except Exception:
            return []
        ids.sort()
        return ids

    def _auto_assign_player_faction(self, randomize: bool = True, announce: bool = True) -> bool:
        ids = self._living_faction_ids()
        if not ids:
            return False
        try:
            fid = int(self.sim.rng.choice(ids)) if randomize else int(ids[0])
        except Exception:
            fid = int(ids[0])
        ok = self._set_player_faction(fid)
        if ok and not announce:
            self.toast_msg = ""
            self.toast_timer = 0.0
        return ok

    def _cycle_player_faction(self, step: int = 1) -> bool:
        ids = self._living_faction_ids()
        if not ids:
            return False
        if self.player_fid not in ids:
            return self._auto_assign_player_faction(randomize=False, announce=True)
        try:
            idx = ids.index(int(self.player_fid))
        except Exception:
            idx = 0
        nxt = ids[(idx + int(step)) % len(ids)]
        ok = self._set_player_faction(int(nxt))
        if ok:
            try:
                self.enemy_fid = None
                self.ground_pick = None
            except Exception:
                pass
        return ok

    def restart(self):
        self.sim = WorldSim()

        # Air combat overlay (` key).
        self.air_mode = False
        self.air_overlay = AirCombatOverlay(self.sim)
        # Ground war layer (always visible on the world map).
        self.ground_layer = GroundWarLayer(self.sim)

        # Reset player faction and auto-enlist again for the new run.
        self.player_fid = None
        self.enemy_fid = None
        self.team_select_active = False
        self._auto_assign_player_faction(randomize=True, announce=False)

        self.mode = self.MODE_WORLD
        self.paused = False
        self.speed_index = SPEED_LEVELS.index(2.0)
        self.time_accum = 0.0
        self.area_cell = None
        self.area_theme = "WILDS"
        self.area_owner = -1
        self.area_map = None
        self.ground_pick = None
        self.ground = None
        try:
            if getattr(self, 'embedded', None) is not None:
                self.embedded.stop()
        except Exception:
            pass
        self.embedded = None
        self.embedded_mode_key = None
        self.embedded_started_at = None
        self.embedded_session_limit = None

        # reset launcher: terminate any running standalone mode windows
        try:
            for p in list(getattr(self, 'mode_procs', {}).values()):
                try:
                    p.terminate()
                except Exception:
                    pass
        except Exception:
            pass
        try:
            self._mode_launch_info = {}
        except Exception:
            pass
        self.active_launcher_key = 'doomsday'



        self.toast_msg = ""
        self.toast_timer = 0.0

    def _switch_launcher(self, key: str):
        """Launch a selected mode inside WORLD_RECT while keeping the sidebar visible."""
        self.active_launcher_key = key

        if key == 'doomsday':
            try:
                if getattr(self, 'embedded', None) is not None:
                    self.embedded.stop()
            except Exception:
                pass
            self.embedded = None
            self.embedded_mode_key = None
            self.embedded_started_at = None
            self.embedded_session_limit = None
            self.air_mode = False
            self._set_toast('Switched to Doomsday Map', 1.2)
            return

        if not self._entry_enabled(key):
            self._set_toast('This sequence is unavailable.', 2.0)
            self.active_launcher_key = 'doomsday'
            return

        if self.player_fid is None:
            if not self._auto_assign_player_faction(randomize=True, announce=True):
                self._set_toast('No living factions available.', 2.2)
                self.active_launcher_key = 'doomsday'
                return

        side_ctx = self._get_player_mode_matchup()
        if not side_ctx:
            self._set_toast('No available war matchup.', 2.2)
            self.active_launcher_key = 'doomsday'
            return

        if key == 'apocalypse':
            self.active_launcher_key = 'doomsday'
            self._set_toast('Apocalypse has been removed from this combined build.', 2.4)
            return

        if key == 'future':
            self.air_mode = True
            self.embedded = None
            self.embedded_mode_key = None
            self.embedded_started_at = time.time()
            self.embedded_session_limit = MODE_SESSION_SECONDS
            self._air_session_t0 = self.embedded_started_at
            self._air_session_player_fid = int(side_ctx.get('player_fid', -1))
            self._set_toast('Air sortie engaged.', 1.2)
            return

        try:
            entry = next((e for e in self.launcher_entries if e.key == key), None)
            if not entry or not entry.rel_path:
                raise RuntimeError('Mode entry missing.')
            abs_path = os.path.join(_project_root(), entry.rel_path)
            player_fid = int(side_ctx.get('player_fid', -1))
            enemy_fid = int(side_ctx.get('enemy_fid', -1))
            player_name = self.sim.factions[player_fid].name if player_fid in self.sim.factions else 'Player'
            enemy_name = self.sim.factions[enemy_fid].name if enemy_fid in self.sim.factions else 'Enemy'
            player_color = self.sim.factions[player_fid].color if player_fid in self.sim.factions else (90, 160, 140)
            enemy_color = self.sim.factions[enemy_fid].color if enemy_fid in self.sim.factions else (170, 80, 80)
            launch_ctx = {
                'doomsday_ctx': {
                    'player_fid': player_fid,
                    'enemy_fid': enemy_fid,
                    'player_name': player_name,
                    'enemy_name': enemy_name,
                    'player_color': player_color,
                    'enemy_color': enemy_color,
                    'war_ctx': side_ctx.get('war_ctx', {}) if isinstance(side_ctx, dict) else {},
                },
                'player_team_name': player_name,
                'enemy_team_name': enemy_name,
                'team_colors': [player_color, enemy_color],
            }
            try:
                if getattr(self, 'embedded', None) is not None:
                    self.embedded.stop()
            except Exception:
                pass
            self.air_mode = False
            self.embedded = EmbeddedAppWrapper(abs_path, WORLD_RECT.copy(), launch_ctx=launch_ctx)
            if not self.embedded.load():
                err = getattr(self.embedded, 'error', 'Load failed.')
                self.embedded = None
                self.active_launcher_key = 'doomsday'
                self._set_toast(err, 3.0)
                return
            self.embedded_mode_key = key
            self.embedded_started_at = time.time()
            self.embedded_session_limit = MODE_SESSION_SECONDS
            self._set_toast(f'{entry.label} engaged.', 1.2)
        except Exception:
            self.active_launcher_key = 'doomsday'
            try:
                import traceback
                here = os.path.abspath(os.path.dirname(__file__))
                fp = os.path.join(here, 'crash_report_launcher_mode.txt')
                with open(fp, 'a', encoding='utf-8') as f:
                    f.write("\n" + "="*72 + "\n")
                    f.write("Embedded launcher crash - " + time.strftime("%Y-%m-%d %H:%M:%S") + "\n")
                    f.write(traceback.format_exc())
            except Exception:
                pass
            self._set_toast('Mode crashed (see crash_report_launcher_mode.txt).', 3.0)

    def _side_select_for_current_war(self, mode_key: str) -> Optional[dict]:
        """Side selection screen. Returns a context dict with player_fid/enemy_fid/war_ctx."""
        # Prefer the current focused cell.
        cell = self.sim.selected_cell or self.sim.inspected_cell or self.area_cell or (WORLD_W // 2, WORLD_H // 2)

        ctx = self._frontline_context(cell)
        if not ctx:
            ctx = self._nearest_frontline_context(cell)

        # If there is no invasion at all, fall back to the two strongest factions.
        if not ctx:
            alive = [f for f in self.sim.factions.values() if len(f.regions) > 0]
            alive.sort(key=lambda f: len(f.regions), reverse=True)
            if len(alive) >= 2:
                a, b = alive[0], alive[1]
                ctx = {
                    "cell": cell,
                    "neighbor": cell,
                    "dxdy": (0, 0),
                    "fid_a": a.fid,
                    "fid_b": b.fid,
                    "attacker": a.fid,
                    "defender": b.fid,
                    "invaded_rid": -1,
                }
            else:
                return None

        attacker = int(ctx.get("attacker", ctx.get("fid_a", -1)))
        defender = int(ctx.get("defender", ctx.get("fid_b", -1)))
        if attacker not in self.sim.factions or defender not in self.sim.factions:
            return None

        fa = self.sim.factions[attacker]
        fd = self.sim.factions[defender]

        # Simple modal loop.
        win = pygame.display.get_surface()
        if win is None:
            return None

        clock = pygame.time.Clock()
        selecting = True
        choice = None  # attacker or defender fid
        while selecting:
            dt = clock.tick(60) / 1000.0
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    raise SystemExit
                if ev.type == pygame.KEYDOWN:
                    if ev.key == pygame.K_ESCAPE:
                        return None
                    if ev.key in (pygame.K_1, pygame.K_KP1):
                        choice = attacker
                        selecting = False
                        break
                    if ev.key in (pygame.K_2, pygame.K_KP2):
                        choice = defender
                        selecting = False
                        break
                if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                    mx, my = ev.pos
                    # top half chooses attacker, bottom chooses defender
                    if my < win.get_height() // 2:
                        choice = attacker
                    else:
                        choice = defender
                    selecting = False
                    break

            # render
            win.fill((10, 12, 16))
            title = self.font_big.render(f"{mode_key.upper()} – Select a side", True, (230, 230, 240))
            win.blit(title, (24, 18))

            hint = self.font.render("1 = Attacker (top)   2 = Defender (bottom)   ESC = cancel", True, (170, 175, 190))
            win.blit(hint, (24, 50))

            # attacker panel
            pad = 18
            w, h = win.get_width(), win.get_height()
            top_rect = pygame.Rect(pad, 86, w - pad*2, (h - 110)//2)
            bot_rect = pygame.Rect(pad, 86 + top_rect.h + 12, w - pad*2, (h - 110)//2)
            pygame.draw.rect(win, (*fa.color, 255), top_rect, 0)
            pygame.draw.rect(win, (0, 0, 0), top_rect, 3)

            pygame.draw.rect(win, (*fd.color, 255), bot_rect, 0)
            pygame.draw.rect(win, (0, 0, 0), bot_rect, 3)

            txt_a = self.font_big.render(f"ATTACKER: {fa.name}", True, (10, 10, 12))
            txt_d = self.font_big.render(f"DEFENDER: {fd.name}", True, (10, 10, 12))
            win.blit(txt_a, (top_rect.x + 16, top_rect.y + 16))
            win.blit(txt_d, (bot_rect.x + 16, bot_rect.y + 16))

            sub_a = self.font.render("Play this mode to increase your side's odds in the active invasion.", True, (20, 20, 24))
            sub_d = self.font.render("Play this mode to increase your side's odds in the active invasion.", True, (20, 20, 24))
            win.blit(sub_a, (top_rect.x + 16, top_rect.y + 50))
            win.blit(sub_d, (bot_rect.x + 16, bot_rect.y + 50))

            pygame.display.flip()

        player_fid = int(choice)
        enemy_fid = defender if player_fid == attacker else attacker
        return {
            "player_fid": player_fid,
            "enemy_fid": enemy_fid,
            "war_ctx": {
                "attacker": attacker,
                "defender": defender,
                "invaded_rid": int(ctx.get("invaded_rid", -1)),
            },
        }

    def _run_mode_session(self, mode_key: str, side_ctx: dict) -> None:
        """Run one of the sub-games in-process; ESC returns to the launcher."""
        entry = next((e for e in self.launcher_entries if e.key == mode_key), None)
        if not entry or not entry.rel_path:
            self._set_toast('Mode entry missing.', 2.0)
            return

        root = _project_root()
        abs_path = os.path.join(root, entry.rel_path)

        # Standardize the window backbuffer before handing control over.
        try:
            self.win_size = (CANVAS_W, CANVAS_H)
            self.window = pygame.display.set_mode(self.win_size, pygame.RESIZABLE)
        except Exception:
            pass

        # Load module (cached).
        if not hasattr(self, "_mode_modules"):
            self._mode_modules = {}
        if mode_key not in self._mode_modules:
            import importlib.util
            spec = importlib.util.spec_from_file_location(f"doomsday_mode_{mode_key}", abs_path)
            if spec is None or spec.loader is None:
                self._set_toast('Failed to load mode.', 2.0)
                return
            mod = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = mod
            spec.loader.exec_module(mod)  # type: ignore
            self._mode_modules[mode_key] = mod
        mod = self._mode_modules[mode_key]

        player_fid = int(side_ctx.get("player_fid", -1))
        enemy_fid = int(side_ctx.get("enemy_fid", -1))
        player_name = self.sim.factions[player_fid].name if player_fid in self.sim.factions else "Player"
        enemy_name = self.sim.factions[enemy_fid].name if enemy_fid in self.sim.factions else "Enemy"
        player_color = self.sim.factions[player_fid].color if player_fid in self.sim.factions else (90, 160, 140)
        enemy_color = self.sim.factions[enemy_fid].color if enemy_fid in self.sim.factions else (170, 80, 80)

        # Run
        t0 = time.time()
        clock = pygame.time.Clock()
        screen = pygame.display.get_surface()
        if screen is None:
            return

        app = None
        runner_kind = None

        if mode_key == 'ground':
            app = mod.RTSGame(external_surface=screen, player_team_name=player_name, enemy_team_name=enemy_name, team_colors=[player_color, enemy_color])
            runner_kind = 'step_events'
        elif mode_key == 'vehicular':
            # Best-effort: pass doomsday context if the mode supports it.
            doomsday_ctx = {
                "player_fid": player_fid,
                "enemy_fid": enemy_fid,
                "player_name": player_name,
                "enemy_name": enemy_name,
                "player_color": player_color,
                "enemy_color": enemy_color,
                "war_ctx": side_ctx.get("war_ctx", {}) if isinstance(side_ctx, dict) else {},
            }
            try:
                app = mod.Game(external_surface=screen, doomsday_ctx=doomsday_ctx)
            except TypeError:
                app = mod.Game(external_surface=screen)
            runner_kind = 'step_events'
        elif mode_key == 'naval':
            doomsday_ctx = {
                "player_fid": player_fid,
                "enemy_fid": enemy_fid,
                "player_name": player_name,
                "enemy_name": enemy_name,
                "player_color": player_color,
                "enemy_color": enemy_color,
                "war_ctx": side_ctx.get("war_ctx", {}) if isinstance(side_ctx, dict) else {},
            }
            try:
                app = mod.EmbeddedNavalGame(external_surface=screen, doomsday_ctx=doomsday_ctx)
            except TypeError:
                app = mod.EmbeddedNavalGame(external_surface=screen)
            runner_kind = 'step_events_present'
        elif mode_key == 'future':
            # Future combat remains self-looping; we patch its main() to allow embedded use.
            try:
                mod.main(embedded=True, doomsday_ctx={"player_fid": player_fid, "enemy_fid": enemy_fid})
            except TypeError:
                mod.main()
            dt_play = max(0.0, time.time() - t0)
            self._after_mode_session(mode_key, player_fid, dt_play)
            return
        else:
            self._set_toast('Unknown mode.', 2.0)
            return

        running = True
        while running:
            dt = clock.tick(60) / 1000.0
            events = pygame.event.get()

            for ev in events:
                if ev.type == pygame.QUIT:
                    raise SystemExit
                if ev.type == pygame.VIDEORESIZE:
                    # Keep it simple: modes assume a 16:9 surface; snap back.
                    try:
                        self.win_size = (CANVAS_W, CANVAS_H)
                        self.window = pygame.display.set_mode(self.win_size, pygame.RESIZABLE)
                        screen = pygame.display.get_surface()
                    except Exception:
                        pass
                if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
                    running = False
                    break

            if not running:
                break

            try:
                if runner_kind == 'step_events':
                    raw = app.step(dt, events)  # type: ignore
                    # Ground battle returns True when requesting exit; vehicular returns True while running.
                    if mode_key == 'ground':
                        done = bool(raw)
                    else:
                        done = not bool(raw)
                    if done:
                        running = False
                elif runner_kind == 'step_events_present':
                    raw = app.step(dt, events, present=True)  # type: ignore
                    # Naval returns True while running; False when it wants to close.
                    done = not bool(raw)
                    if done:
                        running = False
                elif runner_kind == 'handle_step':
                    for ev in events:
                        try:
                            app.handle_event(ev)  # type: ignore
                        except Exception:
                            pass
                    done = bool(app.step(dt, events, allow_escape_exit=False))  # type: ignore
                    if done:
                        running = False
            except Exception:
                running = False

            # Overlay: show player team color + current enemy (readable banner)
            try:
                self._draw_minigame_banner(screen, mode_key, player_fid, enemy_fid)
            except Exception:
                pass

            try:
                pygame.display.flip()
            except Exception:
                pass

        dt_play = max(0.0, time.time() - t0)
        self._after_mode_session(mode_key, player_fid, dt_play)

        # Recreate launcher surfaces (modes may have altered display state).
        try:
            pygame.display.set_caption("Regions at War (RTS Prototype)")
            self.window = pygame.display.set_mode(self.win_size, pygame.RESIZABLE)
            self.canvas = pygame.Surface((CANVAS_W, CANVAS_H))
        except Exception:
            pass


    def _check_endgame_unlocks(self) -> None:
        """No extra sequence unlocks in the final integrated build."""
        return

    def _after_mode_session(self, mode_key: str, player_fid: int, seconds_played: float) -> None:
        """Apply meta-progression and macro-sim bonuses after a mode session."""
        try:
            self.mode_play_seconds[mode_key] = self.mode_play_seconds.get(mode_key, 0.0) + float(seconds_played)
            self.total_mode_play_seconds += float(seconds_played)
        except Exception:
            pass

        # Every ~15 seconds grants 1 support point (capped per session).
        gain = clamp(seconds_played / 15.0, 0.0, 15.0)
        try:
            if player_fid in self.sim.support:
                self.sim.support[player_fid] = clamp(self.sim.support.get(player_fid, 0.0) + gain, 0.0, 40.0)
        except Exception:
            pass

        # Unlock progression (every 5 minutes total playtime).
        try:
            for i, k in enumerate(self.mode_unlock_order):
                if i == 0:
                    continue
                if self.total_mode_play_seconds >= i * self.mode_unlock_interval:
                    if k not in self.unlocked_launcher_keys:
                        self.unlocked_launcher_keys.add(k)
                        self._set_toast(f"Unlocked: {next((e.label for e in self.launcher_entries if e.key == k), k)}", 2.2)
        except Exception:
            pass

    def _to_canvas(self, pos: Tuple[int,int]) -> Optional[Tuple[int,int]]:
        mx, my = pos
        scale, off_x, off_y = self._present
        if scale <= 0:
            return None
        cx = int((mx - off_x) / scale)
        cy = int((my - off_y) / scale)
        if 0 <= cx < CANVAS_W and 0 <= cy < CANVAS_H:
            return cx, cy
        return None


    def _event_to_embedded_local(self, ev: pygame.event.Event) -> tuple[pygame.event.Event, Optional[Tuple[int,int]]]:
        if getattr(self, 'embedded', None) is None:
            return ev, None
        if hasattr(ev, 'pos'):
            cpos = self._to_canvas(ev.pos)
            if cpos is None:
                return ev, None
            local = self.embedded.local_from_canvas(cpos)
            if local is None:
                return ev, None
            try:
                data = ev.dict.copy()
            except Exception:
                data = {}
            data['pos'] = local
            if ev.type == pygame.MOUSEMOTION and 'rel' in data:
                try:
                    cpos0 = self._to_canvas((ev.pos[0] - ev.rel[0], ev.pos[1] - ev.rel[1]))
                    if cpos0 is not None:
                        l0 = self.embedded.local_from_canvas(cpos0)
                        if l0 is not None:
                            data['rel'] = (local[0]-l0[0], local[1]-l0[1])
                except Exception:
                    pass
            return pygame.event.Event(ev.type, data), local
        return ev, None

    def _world_rect_in_window(self) -> pygame.Rect:
        # Convert WORLD_RECT (canvas coords) to window coords for clamping mouse.
        try:
            scale, off_x, off_y = getattr(self, '_present', (0.0, 0, 0))
            if not scale or scale <= 0:
                raise ValueError('no present')
        except Exception:
            win_w, win_h = getattr(self, 'win_size', (CANVAS_W, CANVAS_H))
            scale = min(win_w / CANVAS_W, win_h / CANVAS_H)
            out_w = max(1, int(CANVAS_W * scale))
            out_h = max(1, int(CANVAS_H * scale))
            off_x = (win_w - out_w) // 2
            off_y = (win_h - out_h) // 2
        return pygame.Rect(
            int(off_x + WORLD_RECT.x * scale),
            int(off_y + WORLD_RECT.y * scale),
            int(WORLD_RECT.w * scale),
            int(WORLD_RECT.h * scale),
        )

    def _confine_mouse_to_mode(self, active: bool) -> None:
        # When launched from Prototype Lab, never trap the desktop mouse.
        if os.environ.get('GX_DISABLE_MOUSE_CAPTURE') == '1' or os.environ.get('GLITCHED_MATRIX_DISABLE_MOUSE_CAPTURE') == '1':
            active = False
        # When a mode is active, keep cursor inside the mode play window.
        try:
            pygame.event.set_grab(bool(active))
        except Exception:
            pass

        if not active:
            return

        try:
            r = self._world_rect_in_window()
            mx, my = pygame.mouse.get_pos()
            nx = mx
            ny = my
            # Keep within rect (leave 1px margin)
            if nx < r.left + 1:
                nx = r.left + 1
            if nx > r.right - 2:
                nx = r.right - 2
            if ny < r.top + 1:
                ny = r.top + 1
            if ny > r.bottom - 2:
                ny = r.bottom - 2
            if nx != mx or ny != my:
                pygame.mouse.set_pos((nx, ny))
        except Exception:
            pass


    # ----------------------------
    # Standalone mode integration
    # ----------------------------

    def _build_mode_context(self, mode_key: str) -> dict:
        """Build best-effort context for a mode launch.

        This context is written to disk so standalone modes can optionally consume it.
        The launcher also uses it later if the mode provides no explicit result.
        """
        # Determine a reference cell (prefer inspected/selected; otherwise center).
        cell = self.sim.selected_cell or self.sim.inspected_cell or (WORLD_W // 2, WORLD_H // 2)
        x, y = cell
        x = int(clamp(x, 0, WORLD_W - 1))
        y = int(clamp(y, 0, WORLD_H - 1))
        cell = (x, y)

        # If there is an active invasion, pick the nearest frontline context.
        war_ctx = None
        try:
            war_ctx = self._nearest_frontline_context(cell)
        except Exception:
            war_ctx = None

        # Player-side heuristic: owner of the reference cell.
        player_fid = self.sim.owner_at(x, y)

        out = {
            'mode': str(mode_key),
            'timestamp': float(time.time()),
            'cell': [int(cell[0]), int(cell[1])],
            'player_fid_guess': int(player_fid) if player_fid is not None else -1,
            'wars': [[int(a), int(b)] for (a, b) in list(self.sim.wars)][:8],
        }
        if war_ctx:
            out['war_ctx'] = {
                'cell': [int(war_ctx['cell'][0]), int(war_ctx['cell'][1])],
                'neighbor': [int(war_ctx['neighbor'][0]), int(war_ctx['neighbor'][1])],
                'attacker': int(war_ctx['attacker']),
                'defender': int(war_ctx['defender']),
                'invaded_rid': int(war_ctx['invaded_rid']),
                'fid_a': int(war_ctx['fid_a']),
                'fid_b': int(war_ctx['fid_b']),
            }
        return out

    def _write_mode_context_file(self, mode_key: str, ctx: dict) -> None:
        """Write context to a predictable location under the project root."""
        try:
            root = _project_root()
            os.makedirs(root, exist_ok=True)
            fp = os.path.join(root, f'doomsday_mode_context_{mode_key}.json')
            import json
            with open(fp, 'w', encoding='utf-8') as f:
                json.dump(ctx, f, indent=2)
        except Exception:
            pass

    def _read_mode_result_file(self, mode_key: str) -> dict | None:
        """Read a result file if the mode produced one.

        Supported files (first match wins):
        - <project_root>/doomsday_mode_result_<mode>.json
        - <mode_folder>/doomsday_result.json

        Expected schema (best-effort):
        {
          "winner": <fid>,
          "loser": <fid>,
          "decisive": true/false,
          "casualties": {"<fid>": <int>, ...},
          "war_ctx": {"attacker":..., "defender":..., "invaded_rid":...}
        }
        """
        import json
        root = _project_root()
        candidates = []
        candidates.append(os.path.join(root, f'doomsday_mode_result_{mode_key}.json'))
        try:
            if mode_key in self.mode_procs:
                md = os.path.dirname(self.mode_procs[mode_key].abs_py_path)
                candidates.append(os.path.join(md, 'doomsday_result.json'))
        except Exception:
            pass

        for fp in candidates:
            try:
                if os.path.isfile(fp):
                    with open(fp, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    # Optionally remove the project-root result once consumed.
                    if fp.startswith(root):
                        try:
                            os.remove(fp)
                        except Exception:
                            pass
                    return data if isinstance(data, dict) else None
            except Exception:
                continue
        return None

    def _apply_mode_result(self, mode_key: str, result: dict, fallback_ctx: dict | None = None) -> bool:
        """Apply an explicit mode result back into the macro sim."""
        if not isinstance(result, dict):
            return False

        # Pull war context (prefer explicit in result, else fallback).
        war_ctx = result.get('war_ctx') if isinstance(result.get('war_ctx'), dict) else None
        if war_ctx is None and fallback_ctx and isinstance(fallback_ctx.get('war_ctx'), dict):
            war_ctx = fallback_ctx.get('war_ctx')

        winner = result.get('winner', None)
        loser = result.get('loser', None)
        decisive = bool(result.get('decisive', True))
        casualties = result.get('casualties', {})

        try:
            if winner is not None:
                winner = int(winner)
            if loser is not None:
                loser = int(loser)
        except Exception:
            return False

        # Apply casualties if provided.
        if isinstance(casualties, dict):
            for k, v in casualties.items():
                try:
                    fid = int(k)
                    lost = int(v)
                except Exception:
                    continue
                if fid in self.sim.factions:
                    self.sim.factions[fid].troops = max(0.0, self.sim.factions[fid].troops - float(lost))

        if not war_ctx:
            # No war context: apply only troop/resource nudge.
            if winner is not None and winner in self.sim.factions:
                self.sim.factions[winner].resources = min(RES_CAP, self.sim.factions[winner].resources + (60.0 if decisive else 20.0))
            if loser is not None and loser in self.sim.factions:
                self.sim.factions[loser].resources = max(0.0, self.sim.factions[loser].resources - (80.0 if decisive else 25.0))
            return True

        try:
            attacker = int(war_ctx.get('attacker', -1))
            defender = int(war_ctx.get('defender', -1))
            invaded_rid = int(war_ctx.get('invaded_rid', -1))
        except Exception:
            return False

        # Apply decisive outcome similar to ground combat.
        if decisive and winner is not None and loser is not None and invaded_rid >= 0:
            if winner == attacker:
                if attacker in self.sim.factions and defender in self.sim.factions:
                    self.sim._conquer_region(attacker, invaded_rid, defender)
                self.sim.capital_hp[invaded_rid] = 0.0
                if (attacker, defender) in self.sim.wars:
                    try:
                        self.sim.wars.remove((attacker, defender))
                    except Exception:
                        pass
                self.sim.log(f"MODE:{mode_key}: Attacker victory; territory captured.")
            else:
                if (attacker, defender) in self.sim.wars:
                    try:
                        self.sim.wars.remove((attacker, defender))
                    except Exception:
                        pass
                if invaded_rid >= 0:
                    self.sim.capital_hp[invaded_rid] = min(CAPITAL_HP_MAX, self.sim.capital_hp[invaded_rid] + CAPITAL_HP_MAX * 0.15)
                self.sim.log(f"MODE:{mode_key}: Defender victory; invasion repelled.")
            return True

        # Non-decisive: troop swing only.
        if winner is not None and winner in self.sim.factions:
            self.sim.factions[winner].troops = min(99999.0, self.sim.factions[winner].troops + 8.0)
        if loser is not None and loser in self.sim.factions:
            self.sim.factions[loser].troops = max(0.0, self.sim.factions[loser].troops - 8.0)
        self.sim.log(f"MODE:{mode_key}: Skirmish resolved (limited impact).")
        return True

    def _apply_fallback_mode_effect(self, mode_key: str, exit_code: int, launch_info: dict | None) -> bool:
        """If a mode doesn't report a result, apply a small, deterministic impact.

        This prevents "no-op" launches while keeping the outcome conservative.
        """
        if not self.sim.wars:
            return False

        ctx = None
        started_at = None
        if isinstance(launch_info, dict):
            ctx = launch_info.get('ctx') if isinstance(launch_info.get('ctx'), dict) else None
            started_at = launch_info.get('started_at', None)

        # Duration influences impact, but is capped.
        try:
            dur = max(0.0, float(time.time() - float(started_at))) if started_at else 0.0
        except Exception:
            dur = 0.0
        dur = clamp(dur, 0.0, 240.0)

        war_ctx = ctx.get('war_ctx') if ctx and isinstance(ctx.get('war_ctx'), dict) else None
        if not war_ctx:
            # Use the only war (this project enforces 1 invasion at a time).
            try:
                a, b = next(iter(self.sim.wars))
                edges = self.sim._compute_frontline(a, b)
                if edges:
                    ax, ay, bx, by = edges[0]
                    war_ctx = {'attacker': int(a), 'defender': int(b), 'invaded_rid': int(self.sim.region_at(bx, by))}
                else:
                    war_ctx = {'attacker': int(a), 'defender': int(b), 'invaded_rid': -1}
            except Exception:
                war_ctx = None

        if not war_ctx:
            return False

        attacker = int(war_ctx.get('attacker', -1))
        defender = int(war_ctx.get('defender', -1))
        invaded_rid = int(war_ctx.get('invaded_rid', -1))

        # Choose a "player side" guess (owner of ctx cell) to bias impact slightly.
        player_side = -1
        try:
            if ctx and 'cell' in ctx and isinstance(ctx['cell'], list) and len(ctx['cell']) == 2:
                x, y = int(ctx['cell'][0]), int(ctx['cell'][1])
                player_side = int(self.sim.owner_at(x, y))
        except Exception:
            player_side = -1

        # Baseline skirmish losses. Clean exit (code 0) is treated as "better performance".
        bonus = 1.0 if int(exit_code) == 0 else 0.75
        dmg = int(clamp(dur * 0.22 * bonus, 3, 35))
        selfloss = int(clamp(dur * 0.12, 1, 24))

        if player_side == attacker:
            # Player helped attacker
            if defender in self.sim.factions:
                self.sim.factions[defender].troops = max(0.0, self.sim.factions[defender].troops - float(dmg))
            if attacker in self.sim.factions:
                self.sim.factions[attacker].troops = max(0.0, self.sim.factions[attacker].troops - float(selfloss))
            # If attacker clearly "wins" on troops after impact, capture.
            if invaded_rid >= 0 and attacker in self.sim.factions and defender in self.sim.factions:
                if self.sim.factions[defender].troops <= 0.0 or (dur > 140.0 and self.sim.factions[attacker].troops > self.sim.factions[defender].troops):
                    self.sim._conquer_region(attacker, invaded_rid, defender)
                    self.sim.capital_hp[invaded_rid] = 0.0
                    if (attacker, defender) in self.sim.wars:
                        try:
                            self.sim.wars.remove((attacker, defender))
                        except Exception:
                            pass
                    self.sim.log(f"MODE:{mode_key}: Attacker advances (fallback resolution).")
                    return True

        elif player_side == defender:
            # Player helped defender
            if attacker in self.sim.factions:
                self.sim.factions[attacker].troops = max(0.0, self.sim.factions[attacker].troops - float(dmg))
            if defender in self.sim.factions:
                self.sim.factions[defender].troops = max(0.0, self.sim.factions[defender].troops - float(selfloss))
            # If attacker is pushed back, repel invasion.
            if invaded_rid >= 0 and attacker in self.sim.factions and defender in self.sim.factions:
                if self.sim.factions[attacker].troops <= 0.0 or (dur > 140.0 and self.sim.factions[defender].troops >= self.sim.factions[attacker].troops):
                    if (attacker, defender) in self.sim.wars:
                        try:
                            self.sim.wars.remove((attacker, defender))
                        except Exception:
                            pass
                    self.sim.capital_hp[invaded_rid] = min(CAPITAL_HP_MAX, self.sim.capital_hp[invaded_rid] + CAPITAL_HP_MAX * 0.15)
                    self.sim.log(f"MODE:{mode_key}: Defender holds (fallback resolution).")
                    return True
        else:
            # Unknown side; apply symmetric attrition only.
            if attacker in self.sim.factions:
                self.sim.factions[attacker].troops = max(0.0, self.sim.factions[attacker].troops - float(selfloss))
            if defender in self.sim.factions:
                self.sim.factions[defender].troops = max(0.0, self.sim.factions[defender].troops - float(selfloss))

        # Not decisive, but still applied.
        self.sim.log(f"MODE:{mode_key}: Skirmish attrition applied (fallback).")
        return True

    def _poll_mode_processes(self):
        """Check for finished mode windows and apply their outcomes."""
        if not getattr(self, 'mode_procs', None):
            return
        for key, proc in list(self.mode_procs.items()):
            code = proc.poll_exit_code()
            if code is None:
                continue
            # Process exited
            launch_info = self._mode_launch_info.get(key, {}) if hasattr(self, '_mode_launch_info') else {}
            # Try explicit result file
            res = self._read_mode_result_file(key)
            applied = False
            if res is not None:
                try:
                    applied = self._apply_mode_result(key, res, fallback_ctx=launch_info.get('ctx'))
                except Exception:
                    applied = False
            if not applied:
                try:
                    applied = self._apply_fallback_mode_effect(key, int(code), launch_info)
                except Exception:
                    applied = False

            label = next((e.label for e in self.launcher_entries if e.key == key), key)
            if applied:
                self._set_toast(f"{label} ended; macro state updated.", 2.1)
            else:
                self._set_toast(f"{label} ended.", 1.6)

            # Cleanup: remove tracking so the next click will re-launch.
            try:
                proc.proc = None
                proc.started_at = None
                proc.launch_ctx = None
            except Exception:
                pass
            try:
                if key in self._mode_launch_info:
                    del self._mode_launch_info[key]
            except Exception:
                pass
            # If the launcher focus was on this mode, return highlight to map.
            if self.active_launcher_key == key:
                self.active_launcher_key = 'doomsday'

    def _open_area_view(self, cell: Tuple[int,int]):
        x, y = cell
        if not (0 <= x < WORLD_W and 0 <= y < WORLD_H):
            return

        owner = self.sim.owner_at(x, y)
        rid = self.sim.region_at(x, y)

        # Determine theme by war front / proximity to capital
        theme = "WILDS"
        if self.sim.terrain[y][x] == 0:
            theme = "WILDS"
        else:
            r = self.sim.ruins_at(x, y)
            if r > 0.60:
                theme = "RUINS"
            elif owner >= 0:
                cap = self.sim.capital_pos[rid]
                d = dist_manh((x, y), cap)
                if self.sim._frontline_here(x, y, owner):
                    theme = "WARZONE"
                elif d <= 8:
                    theme = "CITY"
                elif d <= 20:
                    theme = "TOWN"
                else:
                    theme = "FARM"
            else:
                theme = "WILDS"

        self.area_cell = (x, y)
        self.area_owner = owner
        self.area_theme = theme

        style = self.sim.factions[owner].style if owner >= 0 and owner in self.sim.factions else "URBAN"
        seed = deterministic_seed(self.sim.seed, x, y, owner, theme, style)
        self.area_map = generate_area_local_map(seed, theme, style)
        self.mode = self.MODE_AREA

        if owner >= 0 and owner in self.sim.factions:
            self.sim.log(f"VIEW: {theme} area in {self.sim.factions[owner].name} territory at ({x},{y}) [{style}].")
        else:
            self.sim.log(f"VIEW: {theme} area at ({x},{y}).")


    # ----------------------------
    # Ground combat entry helpers
    # ----------------------------

    def _set_toast(self, msg: str, seconds: float = 2.2):
        """Show a short on-screen message (in addition to the newsfeed log)."""
        self.toast_msg = msg
        self.toast_timer = seconds

    def _scroll_feed(self, delta: int) -> None:
        try:
            self.feed_scroll = max(0, int(self.feed_scroll) + int(delta))
        except Exception:
            self.feed_scroll = 0


    # ----------------------------
    # Player team selection + matchup resolution
    # ----------------------------

    def _set_player_faction(self, fid: int) -> bool:
        """Set the player's faction for this run."""
        try:
            fid = int(fid)
        except Exception:
            return False
        if fid not in self.sim.factions or len(self.sim.factions[fid].regions) == 0:
            return False

        self.player_fid = fid
        # Tell the sim to keep wars centered on the player's faction.
        try:
            self.sim.player_fid = fid
        except Exception:
            pass

        self.team_select_active = False
        try:
            name = self.sim.factions[fid].name
        except Exception:
            name = f"Faction {fid}"
        try:
            self.enemy_fid = None
        except Exception:
            pass
        self._set_toast(f"Now supporting: {name}", 1.6)
        return True

    def _player_war_pair(self) -> Optional[Tuple[int, int]]:
        """Return (attacker, defender) for the current invasion involving the player, if any."""
        if self.player_fid is None:
            return None
        try:
            for a, b in self.sim.wars:
                if self.player_fid in (a, b):
                    return int(a), int(b)
        except Exception:
            return None
        return None

    def _ensure_player_war_pair(self) -> Optional[Tuple[int, int]]:
        """Ensure the player always has a valid active matchup."""
        pair = self._player_war_pair()
        if pair is not None:
            return pair
        if self.player_fid is None:
            return None
        player = int(self.player_fid)
        candidates: List[int] = []
        try:
            candidates = [int(x) for x in self.sim._neighbors_by_region_control(player)]
        except Exception:
            candidates = []
        candidates = [fid for fid in candidates if fid != player and fid in self.sim.factions and len(self.sim.factions[fid].regions) > 0]
        if not candidates:
            try:
                candidates = [int(fid) for fid, f in self.sim.factions.items() if int(fid) != player and len(getattr(f, 'regions', [])) > 0]
            except Exception:
                candidates = []
        if not candidates:
            return None
        try:
            target = max(candidates, key=lambda fid: (len(self.sim.factions[fid].regions), float(getattr(self.sim.factions[fid], 'troops', 0.0))))
        except Exception:
            target = int(candidates[0])
        try:
            self.sim.wars.add((player, int(target)))
            self.enemy_fid = int(target)
            self.sim.log(f"INVASION: {self.sim.factions[player].name} engages {self.sim.factions[int(target)].name} (player focus).")
        except Exception:
            pass
        return self._player_war_pair()

    def _get_player_mode_matchup(self) -> Optional[dict]:
        """Resolve the player's opponent for launching a minigame."""
        if self.player_fid is None:
            return None

        pair = self._ensure_player_war_pair()
        if pair is None:
            return None

        attacker, defender = pair
        enemy = defender if int(self.player_fid) == int(attacker) else attacker
        self.enemy_fid = int(enemy)

        invaded_rid = -1
        try:
            edges = self.sim._compute_frontline(attacker, defender)
            if edges:
                ax, ay, bx, by = edges[0]
                invaded_rid = int(self.sim.region_at(bx, by))
        except Exception:
            invaded_rid = -1

        return {
            "player_fid": int(self.player_fid),
            "enemy_fid": int(enemy),
            "war_ctx": {"attacker": int(attacker), "defender": int(defender), "invaded_rid": int(invaded_rid)},
        }

    def _render_team_select_overlay(self):
        """Legacy no-op: faction assignment is automatic in the final build."""
        return

        """Overlay prompting the player to select a faction once per new game."""
        if not getattr(self, 'team_select_active', False):
            return

        # Darken world view
        panel = pygame.Surface((WORLD_RECT.w, WORLD_RECT.h), pygame.SRCALPHA)
        panel.fill((0, 0, 0, 175))
        self.canvas.blit(panel, WORLD_RECT.topleft)

        # Center card
        w = min(WORLD_RECT.w - 40, 860)
        h = 210
        card = pygame.Rect(0, 0, w, h)
        card.center = WORLD_RECT.center
        pygame.draw.rect(self.canvas, (12, 14, 18), card, border_radius=14)
        pygame.draw.rect(self.canvas, (*HOLO_ACCENT_2, 160), card, 2, border_radius=14)

        y = card.y + 14
        y = draw_text(self.canvas, self.font_huge, "CHOOSE YOUR SIDE", card.x + 18, y, (245, 245, 245))
        y = draw_text(self.canvas, self.font, "Click any LAND territory on the map to lock your faction for this run.", card.x + 18, y, (230, 230, 235))
        y = draw_text(self.canvas, self.font, "After this, minigames launch instantly (no side prompts).", card.x + 18, y, (230, 230, 235))
        y += 6
        y = draw_text(self.canvas, self.font_small, "Tip: right-click to inspect a tile. Your team will be the owner of the tile you click.", card.x + 18, y, (210, 210, 210))
        y = draw_text(self.canvas, self.font_small, "ESC: quit | R: restart world", card.x + 18, y, (210, 210, 210))

    def _draw_minigame_banner(self, screen: pygame.Surface, mode_key: str, player_fid: int, enemy_fid: int):
        """Draw a readable HUD banner over a running mode showing team colors + current opponent."""
        try:
            fa = self.sim.factions.get(int(player_fid))
            fb = self.sim.factions.get(int(enemy_fid))
            p_name = fa.name if fa else f"Faction {player_fid}"
            e_name = fb.name if fb else f"Faction {enemy_fid}"
            p_col = fa.color if fa else (90, 200, 120)
            e_col = fb.color if fb else (220, 90, 90)
        except Exception:
            p_name, e_name = "Player", "Enemy"
            p_col, e_col = (90, 200, 120), (220, 90, 90)

        sw = screen.get_width()
        bar_h = 44
        bar = pygame.Surface((sw, bar_h), pygame.SRCALPHA)
        bar.fill((0, 0, 0, 170))

        # Color swatches
        pygame.draw.rect(bar, p_col, (12, 10, 26, 24), border_radius=6)
        pygame.draw.rect(bar, e_col, (sw - 12 - 26, 10, 26, 24), border_radius=6)
        pygame.draw.rect(bar, (0, 0, 0), (12, 10, 26, 24), 2, border_radius=6)
        pygame.draw.rect(bar, (0, 0, 0), (sw - 12 - 26, 10, 26, 24), 2, border_radius=6)

        title = f"{mode_key.upper()}  |  {p_name}  vs  {e_name}"
        txt = self.font_big.render(title, True, (245, 245, 245))
        # shadow
        sh = self.font_big.render(title, True, (0, 0, 0))
        bar.blit(sh, (46 + 1, 9 + 1))
        bar.blit(txt, (46, 9))

        # If we have a war pair, show direction (attacker -> defender)
        pair = self._player_war_pair()
        if pair is not None:
            a, d = pair
            a_name = self.sim.factions[a].name if a in self.sim.factions else str(a)
            d_name = self.sim.factions[d].name if d in self.sim.factions else str(d)
            sub = f"INVASION: {a_name} → {d_name}"
            s_img = self.font_small.render(sub, True, (215, 215, 220))
            s_sh = self.font_small.render(sub, True, (0, 0, 0))
            bar.blit(s_sh, (46 + 1, 28 + 1))
            bar.blit(s_img, (46, 28))

        screen.blit(bar, (0, 0))
    def _frontline_context(self, cell: Tuple[int,int]) -> Optional[dict]:
        """
        If the cell is adjacent to an enemy AND there is an active war between the owners,
        return a context dict describing the 1v1 battle pairing.
        """
        x, y = cell
        if not (0 <= x < WORLD_W and 0 <= y < WORLD_H):
            return None

        owner = self.sim.owner_at(x, y)
        if owner < 0 or owner not in self.sim.factions:
            return None

        for nx, ny in grid_neighbors(x, y, WORLD_W, WORLD_H):
            other = self.sim.owner_at(nx, ny)
            if other < 0 or other == owner:
                continue
            if (owner, other) in self.sim.wars or (other, owner) in self.sim.wars:
                dx, dy = nx - x, ny - y
                if (owner, other) in self.sim.wars:
                    attacker, defender = owner, other
                else:
                    attacker, defender = other, owner

                # determine which region is being invaded (defender side of this border)
                if defender == owner:
                    invaded_rid = self.sim.region_at(x, y)
                else:
                    invaded_rid = self.sim.region_at(nx, ny)

                return {
                    "cell": (x, y),
                    "neighbor": (nx, ny),
                    "dxdy": (dx, dy),
                    "fid_a": owner,
                    "fid_b": other,
                    "attacker": attacker,
                    "defender": defender,
                    "invaded_rid": invaded_rid,
                }
        return None

    def _nearest_frontline_context(self, near_cell: Tuple[int,int]) -> Optional[dict]:
        """Fallback: find the nearest active frontline from ANY current invasion.

        This is intentionally more forgiving than _frontline_context(). If the user presses ENTER
        while invasions exist but their current selection is not exactly on the war border,
        we still open a valid 1v1 ground-combat pairing.

        Preference is given to wars involving the owner of near_cell (if any).
        """
        if not self.sim.wars:
            return None

        x0, y0 = near_cell
        prefer_fid = self.sim.owner_at(x0, y0)

        wars_list = list(self.sim.wars)
        # Shuffle so repeated ENTER doesn't always pick the same border when distances tie
        self.sim.rng.shuffle(wars_list)

        best_ctx: Optional[dict] = None
        best_d = 10**9

        def consider(attacker: int, defender: int, ax: int, ay: int, bx: int, by: int):
            nonlocal best_ctx, best_d
            d = min(abs(ax - x0) + abs(ay - y0), abs(bx - x0) + abs(by - y0))
            if d < best_d:
                best_d = d
                best_ctx = {
                    "cell": (ax, ay),
                    "neighbor": (bx, by),
                    "dxdy": (bx - ax, by - ay),
                    # Side labels for the pick menu
                    "fid_a": attacker,
                    "fid_b": defender,
                    # Macro war direction
                    "attacker": attacker,
                    "defender": defender,
                    "invaded_rid": self.sim.region_at(bx, by),
                }

        # Two passes: first prefer wars involving the local owner; then any war.
        for pass_idx in (0, 1):
            for attacker, defender in wars_list:
                if pass_idx == 0 and prefer_fid >= 0 and prefer_fid not in (attacker, defender):
                    continue
                edges = self.sim._compute_frontline(attacker, defender)
                if not edges:
                    continue
                for ax, ay, bx, by in edges:
                    consider(attacker, defender, ax, ay, bx, by)
            if best_ctx is not None:
                return best_ctx

        return best_ctx

    def _begin_ground_pick(self, cell: Tuple[int,int]):
        """Enter the ground-combat side-pick flow.

        Primary behavior: if the current cell is on an active war border, use that border.
        Fallback behavior: if invasions exist elsewhere, jump to the nearest active frontline.
        """
        ctx = self._frontline_context(cell)
        if not ctx:
            # If the player isn't on the exact border tile, be forgiving and find the nearest battle.
            ctx = self._nearest_frontline_context(cell)

        if not ctx:
            self.sim.log("GROUND: No active invasions to join.")
            self._set_toast("No active invasions to join.", 2.4)
            return

        # Point the inspection/selection at the battle so it's obvious what you joined.
        self.sim.inspected_cell = ctx["cell"]
        self.sim.selected_cell = ctx["cell"]

        # If we aren't already viewing the frontline area, load it (background for the pick overlay).
        if self.area_cell != ctx["cell"] or self.area_map is None:
            try:
                self._open_area_view(ctx["cell"])
            except Exception:
                pass

        self.ground_pick = ctx
        self.mode = self.MODE_GROUND_PICK

    def _start_ground(self, player_fid: int):
        if not self.ground_pick:
            return
        ctx = dict(self.ground_pick)

        # Defensive validation: missing/invalid context should not crash the whole sim.
        if "fid_a" not in ctx or "fid_b" not in ctx or "cell" not in ctx:
            self.sim.log("GROUND: Invalid battle context; cannot enter ground combat.")
            self._set_toast("Ground combat unavailable (invalid context).", 2.8)
            self.ground_pick = None
            self.mode = self.MODE_WORLD
            return

        ctx["nonce"] = self.sim.rng.randint(0, 1_000_000_000)

        # Ensure air overlay is not in control mode during ground combat.
        self.air_mode = False

        try:
            self.ground = MapDotGroundCombatSim(self.sim, ctx, player_fid)
        except Exception:
            import traceback, os, time
            # Write a dedicated crash log next to the script.
            try:
                here = os.path.abspath(os.path.dirname(__file__))
                fp = os.path.join(here, "crash_report_ground_combat.txt")
                with open(fp, "a", encoding="utf-8") as f:
                    f.write("\n" + "="*72 + "\n")
                    f.write("Ground combat crash log - " + time.strftime("%Y-%m-%d %H:%M:%S") + "\n")
                    f.write(traceback.format_exc())
            except Exception:
                pass

            self.sim.log("GROUND: Crash entering ground combat (see crash_report_ground_combat.txt).")
            self._set_toast("Crash entering ground combat (see crash_report_ground_combat.txt).", 3.2)
            self.ground = None
            self.ground_pick = None
            self.mode = self.MODE_WORLD
            return

        self.ground_pick = None
        self.mode = self.MODE_GROUND

        fa = self.sim.factions.get(self.ground.team_fid[0])
        fb = self.sim.factions.get(self.ground.team_fid[1])
        an = fa.name if fa else str(self.ground.team_fid[0])
        bn = fb.name if fb else str(self.ground.team_fid[1])
        self.sim.log(f"GROUND: Entered battle ({an} vs {bn}).")

    def _apply_ground_outcome(self, g: GroundCombatSim):
        """
        Apply the result of a completed ground battle to the macro sim.
        """
        if not g.finished or g.winner_fid is None or g.loser_fid is None:
            return
        ctx = g.ctx
        winner = g.winner_fid
        loser = g.loser_fid
        attacker = ctx["attacker"]
        defender = ctx["defender"]
        invaded_rid = ctx["invaded_rid"]
        cell = ctx["cell"]
        neighbor = ctx["neighbor"]

        # translate casualties into macro troop losses (1:1 mapping)
        for fid, lost in g.casualties.items():
            if fid in self.sim.factions:
                self.sim.factions[fid].troops = max(0.0, self.sim.factions[fid].troops - float(lost))

        # decisive result (command building down): bigger swing
        if winner in self.sim.factions and loser in self.sim.factions:
            wname = self.sim.factions[winner].name
            lname = self.sim.factions[loser].name
        else:
            wname = str(winner)
            lname = str(loser)

        if g.decisive:
            if loser in self.sim.factions:
                self.sim.factions[loser].resources = max(0.0, self.sim.factions[loser].resources - 180.0)
                self.sim.factions[loser].troops = max(0.0, self.sim.factions[loser].troops - 40.0)

            if winner in self.sim.factions:
                self.sim.factions[winner].resources = min(RES_CAP, self.sim.factions[winner].resources + 90.0)

            if winner == attacker:
                # Ground victory is defined as wiping out the opposing army.
                # Immediate territory loss for the invaded region.
                if attacker in self.sim.factions and defender in self.sim.factions:
                    self.sim._conquer_region(attacker, invaded_rid, defender)
                self.sim.capital_hp[invaded_rid] = 0.0
                if (attacker, defender) in self.sim.wars:
                    self.sim.wars.remove((attacker, defender))
                self.sim.log(f"GROUND: {wname} wipes out {lname}. Territory is captured.")

            else:
                # defender win: cancel the invasion
                if (attacker, defender) in self.sim.wars:
                    self.sim.wars.remove((attacker, defender))
                self.sim.capital_hp[invaded_rid] = min(CAPITAL_HP_MAX, self.sim.capital_hp[invaded_rid] + CAPITAL_HP_MAX * 0.15)
                self.sim.log(f"GROUND: {wname} defends successfully. Invasion is repelled.")
        else:
            # non-decisive: still a noticeable swing
            if winner in self.sim.factions:
                self.sim.factions[winner].troops = min(99999.0, self.sim.factions[winner].troops + 10.0)
            if loser in self.sim.factions:
                self.sim.factions[loser].troops = max(0.0, self.sim.factions[loser].troops - 10.0)

            self.sim.log(f"GROUND: {wname} wins the skirmish against {lname} (limited impact).")
    def _step_active_area(self):
        if self.mode != self.MODE_AREA or not self.area_map or not self.area_cell:
            return

        lm = self.area_map
        x, y = self.area_cell
        owner = self.sim.owner_at(x, y)

        f = self.sim.factions.get(owner) if owner >= 0 else None
        if f is None or len(f.regions) == 0:
            # decay smoke, slow settling
            for b in lm.buildings:
                if b.burn > 0.0:
                    b.burn = max(0.0, b.burn - 0.012)
            return

        at_war_here = self.sim._frontline_here(x, y, owner) or any(owner in w for w in self.sim.wars)
        losing_local = at_war_here and (f.troops < 40.0)

        # Build power from faction economy (buildings + resources)
        econ_score = 0.6 + 0.02 * f.buildings.get("Factory", 0) + 0.012 * f.buildings.get("Civic", 0) + 0.010 * f.buildings.get("Lab", 0)
        build_power = econ_score * (0.60 + 0.40*clamp(f.resources/260.0, 0, 1))
        build_power = clamp(build_power, 0.18, 2.60)

        inactive = [b for b in lm.buildings if not b.started and not b.destroyed]
        if inactive and self.sim.rng.random() < (0.020 * build_power):
            b = self.sim.rng.choice(inactive)
            b.started = True
            b.progress = 0.01

        in_prog = [b for b in lm.buildings if b.started and b.progress < 1.0 and not b.destroyed]
        self.sim.rng.shuffle(in_prog)
        for b in in_prog[:3]:
            b.progress = clamp(b.progress + b.build_rate * build_power, 0.0, 1.0)

        # war damage & destruction
        if at_war_here and lm.theme in ("CITY", "TOWN", "WARZONE"):
            strike_p = 0.012 + (0.022 if lm.theme == "WARZONE" else 0.0) + (0.030 if losing_local else 0.0)
            if self.sim.rng.random() < strike_p:
                candidates = [b for b in lm.buildings if b.progress >= 1.0 and not b.destroyed]
                if candidates:
                    b = self.sim.rng.choice(candidates)
                    b.damage = clamp(b.damage + self.sim.rng.uniform(0.15, 0.55), 0, 1)
                    b.burn = clamp(b.burn + self.sim.rng.uniform(0.35, 1.0), 0, 1)
                    if losing_local and b.damage > 0.60 and self.sim.rng.random() < 0.65:
                        b.destroyed = True
                        b.burn = 1.0
                    lm.fx.append((b.gx * LOCAL_TILE, b.gy * LOCAL_TILE, 0.0))

        for b in lm.buildings:
            if b.burn > 0.0:
                b.burn = max(0.0, b.burn - 0.010)

        new_fx = []
        for fx in lm.fx:
            fx_x, fx_y, life = fx
            life += 0.05
            if life < 0.55:
                new_fx.append((fx_x, fx_y, life))
        lm.fx = new_fx


    def run(self):
        running = True
        while running:
            # MAP_MUSIC_GUARD
            try:
                if getattr(self, 'active_app', None) is None:
                    _doomsday_play_map_music()
                else:
                    _doomsday_stop_all_audio()
            except Exception:
                pass
            dt = self.clock.tick(FPS) / 1000.0
            events = pygame.event.get()

            # Toast decay (frame-based)
            if self.toast_timer > 0.0:
                self.toast_timer = max(0.0, self.toast_timer - dt)
                if self.toast_timer <= 0.0:
                    self.toast_msg = ''

            # Check for finished standalone mode windows and apply outcomes.
            try:
                self._poll_mode_processes()
            except Exception:
                pass

            # Always handle quit/resize first
            for ev in events:
                if ev.type == pygame.QUIT:
                    running = False
                elif ev.type == pygame.VIDEORESIZE:
                    self.win_size = (max(640, ev.w), max(360, ev.h))
                    self.window = pygame.display.set_mode(self.win_size, pygame.RESIZABLE)
                    try:
                        if getattr(self, 'embedded', None) is not None:
                            self.embedded.set_viewport_rect(WORLD_RECT.copy())
                    except Exception:
                        pass

            # Constrain mouse to the active mode window (WORLD_RECT) when running a game mode.
            # This applies to embedded modes, air overlay mode, and ground combat.
            mode_active = (getattr(self, 'embedded', None) is not None) or getattr(self, 'air_mode', False) or (self.mode in (self.MODE_GROUND, self.MODE_GROUND_PICK))
            self._confine_mouse_to_mode(mode_active)

            # Embedded mode routing first.
            if getattr(self, 'embedded', None) is not None:
                for ev in events:
                    if ev.type == pygame.MOUSEWHEEL:
                        c_mouse = self._to_canvas(pygame.mouse.get_pos())
                        if c_mouse is not None and UI_RECT.collidepoint(*c_mouse):
                            self._scroll_feed(-int(ev.y))
                            continue
                    if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
                        try:
                            self.embedded.stop()
                        except Exception:
                            pass
                        self.embedded = None
                        self.embedded_mode_key = None
                        self.embedded_started_at = None
                        self.embedded_session_limit = None
                        self.active_launcher_key = 'doomsday'
                        break
                    tev, local_pos = self._event_to_embedded_local(ev)
                    if local_pos is not None or ev.type in (pygame.KEYDOWN, pygame.KEYUP, pygame.TEXTINPUT, pygame.MOUSEWHEEL):
                        try:
                            self.embedded.handle_event(tev, local_pos)
                        except Exception:
                            pass
                if getattr(self, 'embedded', None) is not None:
                    keep_running = True
                    try:
                        keep_running = bool(self.embedded.update(dt))
                    except Exception:
                        keep_running = False
                    if self.embedded_session_limit is not None and self.embedded_started_at is not None:
                        if (time.time() - self.embedded_started_at) >= float(self.embedded_session_limit):
                            keep_running = False
                    if not keep_running:
                        try:
                            self.embedded.stop()
                        except Exception:
                            pass
                        self.embedded = None
                        self.embedded_mode_key = None
                        self.embedded_started_at = None
                        self.embedded_session_limit = None
                        self.active_launcher_key = 'doomsday'
                self.render()
                continue

            # Input routing
            for ev in events:

                if ev.type == pygame.KEYDOWN:
                    # Ground combat has priority input handling
                    if self.mode == self.MODE_GROUND:
                        if ev.key == pygame.K_ESCAPE:
                            # Exit back to world map; apply outcome only if battle finished
                            if self.ground and self.ground.finished:
                                self._apply_ground_outcome(self.ground)
                            self.ground = None
                            self.mode = self.MODE_WORLD
                            self.active_launcher_key = 'doomsday'
                        continue

                    if self.mode == self.MODE_GROUND_PICK:
                        if ev.key == pygame.K_ESCAPE:
                            self.ground_pick = None
                            self.mode = self.MODE_WORLD
                            self.active_launcher_key = 'doomsday'
                        elif ev.key in (pygame.K_1, pygame.K_KP1):
                            if self.ground_pick:
                                self._start_ground(self.ground_pick['fid_a'])
                        elif ev.key in (pygame.K_2, pygame.K_KP2):
                            if self.ground_pick:
                                self._start_ground(self.ground_pick['fid_b'])
                        continue

                    if getattr(self, 'air_mode', False):
                        if ev.key == pygame.K_ESCAPE:
                            self.air_mode = False
                            continue
                        # Allow pause/speed keys while in air mode
                        if ev.key == pygame.K_SPACE:
                            self.paused = not self.paused
                            continue
                        if ev.key == pygame.K_LEFTBRACKET:
                            self.speed_index = max(0, self.speed_index - 1)
                            continue
                        if ev.key == pygame.K_RIGHTBRACKET:
                            self.speed_index = min(len(SPEED_LEVELS) - 1, self.speed_index + 1)
                            continue
                    # Normal (world / area) keys
                    if ev.key == pygame.K_ESCAPE:
                        if self.mode == self.MODE_AREA:
                            self.mode = self.MODE_WORLD
                        else:
                            running = False
                    elif ev.key == pygame.K_SPACE:
                        self.paused = not self.paused
                    elif ev.key == pygame.K_r:
                        self.restart()
                    elif ev.key == pygame.K_LEFTBRACKET:
                        self.speed_index = max(0, self.speed_index - 1)
                    elif ev.key == pygame.K_RIGHTBRACKET:
                        self.speed_index = min(len(SPEED_LEVELS) - 1, self.speed_index + 1)
                    elif ev.key == pygame.K_TAB:
                        if self.mode == self.MODE_WORLD and not getattr(self, 'air_mode', False):
                            self._cycle_player_faction(1)
                    elif ev.key == pygame.K_BACKQUOTE:
                        self.air_mode = not getattr(self, 'air_mode', False)
                        self._set_toast('Air overlay engaged.' if self.air_mode else 'Returned to map command.', 1.0)
                    elif ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                        # Ground forces are always rendered on the world map (no separate ground combat mode).
                        self._set_toast('Ground war is always visible on the map.', 1.4)

                elif ev.type == pygame.MOUSEWHEEL:
                    c_mouse = self._to_canvas(pygame.mouse.get_pos())
                    if c_mouse is not None and UI_RECT.collidepoint(*c_mouse):
                        self._scroll_feed(-int(ev.y))
                elif ev.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP, pygame.MOUSEMOTION):
                    cpos = self._to_canvas(ev.pos) if hasattr(ev, 'pos') else None

                    # AIR_MODE_MOUSEROUTE
                    if getattr(self, 'air_mode', False):
                        # In air mode, the sidebar/menu is disabled and the mouse is used for aiming.
                        # Do not process launcher clicks or world-map clicks.
                        continue

                    # Launcher UI click (left mouse)
                    if ev.type == pygame.MOUSEBUTTONDOWN and getattr(ev, 'button', None) == 1 and cpos is not None:
                        mx, my = cpos
                        if UI_RECT.collidepoint(mx, my):
                            for r, key in list(self._launcher_clicks):
                                if r.collidepoint(mx, my):
                                    self._switch_launcher(key)
                                    break
                            continue
                    # Ground combat mouse
                    if self.mode == self.MODE_GROUND:
                        if self.ground:
                            self.ground.handle_event(ev, cpos)
                        continue

                    # Normal world map mouse
                    if ev.type == pygame.MOUSEBUTTONDOWN and cpos is not None:
                        mx, my = cpos
                        if self.mode == self.MODE_WORLD:
                            if ev.button == 1:
                                if WORLD_RECT.collidepoint(mx, my):
                                    cx, cy = px_to_cell_world(mx, my)
                                    if 0 <= cx < WORLD_W and 0 <= cy < WORLD_H:
                                        self._open_area_view((cx, cy))
                            elif ev.button == 3:
                                if WORLD_RECT.collidepoint(mx, my):
                                    cx, cy = px_to_cell_world(mx, my)
                                    if 0 <= cx < WORLD_W and 0 <= cy < WORLD_H:
                                        self.sim.inspected_cell = (cx, cy)
                                        self.sim.selected_cell = (cx, cy)
            # Update sim time
            speed = SPEED_LEVELS[self.speed_index]

            # Macro-sim always updates (even while other games are active), unless paused.
            if not self.paused:
                self.time_accum += dt * speed
                while self.time_accum >= TICK_SECONDS:
                    self.time_accum -= TICK_SECONDS
                    self.sim.step_tick()
                    self._check_endgame_unlocks()
                    self._step_active_area()

            # AIR_OVERLAY_UPDATE
            try:
                if not self.paused:
                    mpos = self._to_canvas(pygame.mouse.get_pos())
                    # mpos is in canvas space; pass through directly (it matches world px coords).
                    self.air_overlay.update(dt, getattr(self, 'air_mode', False), mpos)
            except Exception:
                pass


            # Ground war layer update (always visible on the world map)
            try:
                if not self.paused and hasattr(self, 'ground_layer') and self.ground_layer:
                    self.ground_layer.update(dt)
            except Exception:
                pass

            # Update macro FX
            self.sim.fx = [fx for fx in self.sim.fx if fx.update(dt)]

            # Ground combat runs in the Doomsday map context; keep macro sim running in background.
            if self.mode == self.MODE_GROUND:
                if self.ground:
                    self.ground.update(dt)
                    if self.ground.finished and getattr(self.ground, 'finish_timer', 0.0) <= 0.0:
                        self._apply_ground_outcome(self.ground)
                        self.ground = None
                        self.mode = self.MODE_WORLD
                        self.active_launcher_key = 'doomsday'
            elif self.mode == self.MODE_GROUND_PICK:
                # Choosing sides; macro sim continues in background.
                pass

            self._render()

        pygame.quit()

    def render(self):
        self._render()

    # ----------------------------
    # Rendering
    # ----------------------------

    def _render_ground_pick_overlay(self):
        if not self.ground_pick:
            return
        ctx = self.ground_pick
        fa = self.sim.factions.get(ctx["fid_a"])
        fb = self.sim.factions.get(ctx["fid_b"])
        a_name = fa.name if fa else f"Faction {ctx['fid_a']}"
        b_name = fb.name if fb else f"Faction {ctx['fid_b']}"
        a_col = fa.color if fa else (90, 200, 120)
        b_col = fb.color if fb else (220, 90, 90)

        panel = pygame.Surface((WORLD_RECT.w, 150), pygame.SRCALPHA)
        panel.fill((0, 0, 0, 170))
        self.canvas.blit(panel, (WORLD_RECT.x, WORLD_RECT.y + WORLD_RECT.h//2 - 75))

        draw_text(self.canvas, self.font_big, "ENTER GROUND COMBAT", WORLD_RECT.x + 20, WORLD_RECT.y + WORLD_RECT.h//2 - 60, (245, 245, 245))
        draw_text(self.canvas, self.font, "Choose a side:", WORLD_RECT.x + 20, WORLD_RECT.y + WORLD_RECT.h//2 - 32, (220, 220, 220))
        draw_text(self.canvas, self.font, f"1: {a_name}", WORLD_RECT.x + 20, WORLD_RECT.y + WORLD_RECT.h//2 - 10, a_col)
        draw_text(self.canvas, self.font, f"2: {b_name}", WORLD_RECT.x + 20, WORLD_RECT.y + WORLD_RECT.h//2 + 12, b_col)
        draw_text(self.canvas, self.font_small, "ESC: cancel (back to world)", WORLD_RECT.x + 20, WORLD_RECT.y + WORLD_RECT.h//2 + 42, (200, 200, 200))

    def _render_ground_combat(self):
        # Ground combat is rendered directly on the main map (team-colored dots).
        # Draw the world as a backdrop, then overlay the battle zone.
        self._render_world(draw_air=False)

        try:
            shade = pygame.Surface((WORLD_RECT.w, WORLD_RECT.h), pygame.SRCALPHA)
            shade.fill((0, 0, 0, 70))
            self.canvas.blit(shade, WORLD_RECT.topleft)
        except Exception:
            pass

        if self.ground:
            self.ground.draw(self.canvas, self.font, self.font_big)

    
    def _render_world(self, draw_air: bool = True):
        self.canvas.fill((10, 12, 16))

        # Base region terrain
        for y in range(WORLD_H):
            for x in range(WORLD_W):
                px, py = cell_to_px_world(x, y)
                rid = self.sim.region_id[y][x]
                base = self.sim.region_colors[rid]
                if self.sim.terrain[y][x] == 0:
                    base = _mul_color(base, 0.42)
                pygame.draw.rect(self.canvas, base, (px, py, TILE, TILE))

        # Ownership overlay + ruins
        overlay = pygame.Surface((WORLD_PX_W, WORLD_PX_H), pygame.SRCALPHA)
        for y in range(WORLD_H):
            for x in range(WORLD_W):
                cid = self.sim.owner[y][x]
                if cid >= 0 and cid in self.sim.factions:
                    col = self.sim.factions[cid].color
                    pygame.draw.rect(overlay, (*col, OVERLAY_ALPHA), (x*TILE, y*TILE, TILE, TILE))
                r = self.sim.ruins[y][x]
                if r > 0.02:
                    a = int(clamp(185 * r, 0, 195))
                    pygame.draw.rect(overlay, (70, 70, 78, a), (x*TILE, y*TILE, TILE, TILE))
        self.canvas.blit(overlay, (WORLD_X, WORLD_Y))

        # Borders
        for y in range(WORLD_H):
            for x in range(WORLD_W):
                cid = self.sim.owner[y][x]
                if cid < 0:
                    continue
                for nx, ny in grid_neighbors(x, y, WORLD_W, WORLD_H):
                    if self.sim.owner[ny][nx] != cid:
                        px, py = cell_to_px_world(x, y)
                        pygame.draw.rect(self.canvas, BORDER_COLOR, (px, py, TILE, TILE), 1)
                        break

        # Capitals (by region, but drawn with controller color)
        for rid in range(REGION_COUNT):
            cx, cy = self.sim.capital_pos[rid]
            controller = self.sim.region_control[rid]
            if controller not in self.sim.factions:
                continue
            col = self.sim.factions[controller].color
            px, py = cell_to_px_world(cx, cy)
            pygame.draw.rect(self.canvas, (0, 0, 0), (px+1, py+1, TILE-2, TILE-2))
            pygame.draw.rect(self.canvas, col, (px+2, py+2, TILE-4, TILE-4))

        # Conflict FX
        for fx in self.sim.fx:
            fx.draw(self.canvas)


        # Ground war layer (dots on land beneath the jets)
        try:
            if hasattr(self, 'ground_layer') and self.ground_layer:
                self.ground_layer.draw(self.canvas)
        except Exception:
            pass

        # AIR_OVERLAY_DRAW
        try:
            # Hide system cursor while in air mode; draw our own crosshair.
            pygame.mouse.set_visible(not getattr(self, 'air_mode', False))
        except Exception:
            pass

        if draw_air:
            try:
                mpos = self._to_canvas(pygame.mouse.get_pos())
                self.air_overlay.draw(self.canvas, getattr(self, 'air_mode', False), mpos)
            except Exception:
                pass

        # Selection highlight
        if self.sim.selected_cell:
            sx, sy = self.sim.selected_cell
            px, py = cell_to_px_world(sx, sy)
            pygame.draw.rect(self.canvas, (255, 255, 255), (px, py, TILE, TILE), 2)

        pygame.draw.line(self.canvas, (30, 30, 38), (UI_X, 0), (UI_X, CANVAS_H), 2)

    def _render_area_view(self):
        self._render_world()
        shade = pygame.Surface((WORLD_PX_W, WORLD_PX_H), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 130))
        self.canvas.blit(shade, (WORLD_X, WORLD_Y))

        if not self.area_map or not self.area_cell:
            return

        lm = self.area_map

        panel = pygame.Surface((AREA_VIEW_RECT.w + 40, AREA_VIEW_RECT.h + 40), pygame.SRCALPHA)
        panel.fill((18, 20, 25, 235))
        pygame.draw.rect(panel, (70, 70, 85, 180), panel.get_rect(), 2, border_radius=12)
        self.canvas.blit(panel, (AREA_VIEW_RECT.x - 20, AREA_VIEW_RECT.y - 20))

        # draw terrain with region style palette
        surf = pygame.Surface((AREA_VIEW_RECT.w, AREA_VIEW_RECT.h))
        pal = STYLE_TERRAIN.get(lm.style, STYLE_TERRAIN["URBAN"])
        water_col = pal["water"]
        land_col = pal["land"]

        for y in range(LOCAL_H):
            for x in range(LOCAL_W):
                t = lm.terrain[y][x]
                if t == 0:
                    col = water_col
                else:
                    # theme modulation
                    if lm.theme == "WARZONE":
                        col = _mul_color(land_col, 0.86)
                    elif lm.theme == "RUINS":
                        col = _mul_color(land_col, 0.78)
                    elif lm.theme == "CITY":
                        col = _mul_color(land_col, 0.92)
                    elif lm.theme == "FARM":
                        col = _add_color(_mul_color(land_col, 0.98), 6)
                    else:
                        col = land_col
                pygame.draw.rect(surf, col, (x*LOCAL_TILE, y*LOCAL_TILE, LOCAL_TILE, LOCAL_TILE))

        # minor grid lines (subtle)
        if lm.theme in ("CITY", "TOWN", "FARM"):
            gcol = (0, 0, 0)
            gsurf = pygame.Surface((AREA_VIEW_RECT.w, AREA_VIEW_RECT.h), pygame.SRCALPHA)
            step = LOCAL_TILE * 4
            for x in range(0, AREA_VIEW_RECT.w, step):
                pygame.draw.line(gsurf, (*gcol, 20), (x, 0), (x, AREA_VIEW_RECT.h), 1)
            for y in range(0, AREA_VIEW_RECT.h, step):
                pygame.draw.line(gsurf, (*gcol, 20), (0, y), (AREA_VIEW_RECT.w, y), 1)
            surf.blit(gsurf, (0, 0))

        # draw buildings
        base_color = (150, 170, 160)
        if self.area_owner >= 0 and self.area_owner in self.sim.factions:
            base_color = self.sim.factions[self.area_owner].color

        for b in lm.buildings:
            rect = building_tile_rect(b)
            px = rect.x * LOCAL_TILE
            py = rect.y * LOCAL_TILE
            w = rect.w * LOCAL_TILE
            h = rect.h * LOCAL_TILE
            if w < 6 or h < 6:
                continue

            col = style_build_palette(lm.style, base_color, b.kind)
            sprite = render_building_base(b.kind, w, h, b.variant, b.roof, col).copy()

            if b.destroyed:
                dim = pygame.Surface((w, h), pygame.SRCALPHA)
                dim.fill((0, 0, 0, 120))
                sprite.blit(dim, (0, 0))
                draw_destroyed_overlay(sprite, b.burn)
            else:
                if b.damage > 0.01:
                    dmg = pygame.Surface((w, h), pygame.SRCALPHA)
                    dmg.fill((0, 0, 0, int(110 * b.damage)))
                    sprite.blit(dmg, (0, 0))
                if b.started and b.progress < 1.0:
                    draw_construction_overlay(sprite, b.progress)

            surf.blit(sprite, (px, py))

            if (not b.started) and (not b.destroyed) and lm.theme not in ("RUINS", "WARZONE"):
                pygame.draw.rect(surf, (230, 230, 230), (px+2, py+2, max(1, w-4), max(1, h-4)), 1)

        # local explosions
        if lm.fx:
            for fx_x, fx_y, life in lm.fx:
                t = clamp(life / 0.55, 0, 1)
                rad = lerp(2, 20, t)
                alpha = int(200 * (1 - t))
                ring = pygame.Surface((int(rad*2+4), int(rad*2+4)), pygame.SRCALPHA)
                pygame.draw.circle(ring, (255, 190, 110, alpha), (ring.get_width()//2, ring.get_height()//2), int(rad), 2)
                surf.blit(ring, (fx_x - ring.get_width()/2, fx_y - ring.get_height()/2))

        self.canvas.blit(surf, AREA_VIEW_RECT.topleft)

        header_y = AREA_VIEW_RECT.y - 18
        title = f"AREA VIEW: {lm.theme}  [{lm.style}]"
        self.canvas.blit(self.font_big.render(title, True, (245, 245, 245)), (AREA_VIEW_RECT.x, header_y))

        x, y = self.area_cell
        rid = self.sim.region_at(x, y)
        owner = self.sim.owner_at(x, y)
        info = f"Cell ({x},{y}) | Region {rid}"
        if owner >= 0 and owner in self.sim.factions:
            f = self.sim.factions[owner]
            cap_hp = self.sim.capital_hp[rid]
            info += f"  |  Controller: {f.name}  |  Troops {f.troops:0.0f}  |  Res {f.resources:0.0f}  |  CapitalHP {cap_hp:0.0f}"
        self.canvas.blit(self.font_small.render(info, True, (210, 210, 210)), (AREA_VIEW_RECT.x, AREA_VIEW_RECT.y + AREA_VIEW_RECT.h + 6))
        self.canvas.blit(self.font_small.render("ESC: back", True, (200, 200, 200)), (AREA_VIEW_RECT.x + AREA_VIEW_RECT.w - 90, AREA_VIEW_RECT.y - 18))
        if self.area_cell:
            hint = None
            if self._frontline_context(self.area_cell):
                hint = "ENTER: ground combat (this frontline)"
            elif self.sim.wars:
                hint = "ENTER: ground combat (jump to frontline)"
            if hint:
                self.canvas.blit(self.font_small.render(hint, True, (200, 200, 200)), (AREA_VIEW_RECT.x + 8, AREA_VIEW_RECT.y - 18))
    # ----------------------------
    # Holographic post-processing
    # ----------------------------

    def _holo_get_layer(self, size: Tuple[int,int], kind: str) -> pygame.Surface:
        # Tint-only hologram: no scanlines, grid lines, dot-matrix, or other line work.
        # Kept as a cached helper for future use; currently returns a transparent layer.
        key = (size[0], size[1], kind)
        if key in self._holo_cache:
            return self._holo_cache[key]
        w, h = size
        layer = pygame.Surface((w, h), pygame.SRCALPHA)
        self._holo_cache[key] = layer
        return layer

    def _holo_get_noise_tile(self) -> pygame.Surface:
        if self._holo_noise_tile is not None:
            return self._holo_noise_tile
        rng = random.Random(1337)
        tile = pygame.Surface((160, 160), pygame.SRCALPHA)
        # Sparse noise specks (prebaked). Keep intentionally faint.
        for _ in range(240):
            x = rng.randrange(0, tile.get_width())
            y = rng.randrange(0, tile.get_height())
            a = rng.randrange(2, 6)
            col = HOLO_ACCENT_2 if rng.random() < 0.5 else HOLO_ACCENT
            tile.set_at((x, y), (*col, a))
        # a few brighter glitch streaks
        for _ in range(6):
            y = rng.randrange(0, tile.get_height())
            x0 = rng.randrange(0, tile.get_width() - 30)
            x1 = x0 + rng.randrange(20, 90)
            pygame.draw.line(tile, (*HOLO_ACCENT, 8), (x0, y), (x1, y), 1)
        self._holo_noise_tile = tile
        return tile

    def _holo_blit_noise(self, rect: pygame.Rect, intensity: int = 22) -> None:
        # Disabled (static-only hologram; no flicker / no animation).
        return


    def _holo_postprocess(self) -> None:
        # Apply a subtle, static holographic tint only (no scanlines/grid/noise/brackets).
        # This is intentionally cheap: one multiply pass over WORLD_RECT and UI_RECT.
        # WORLD/map region
        tint_world = pygame.Surface((WORLD_RECT.w, WORLD_RECT.h), pygame.SRCALPHA)
        # Near-white cyan multiply to gently shift hue without darkening aggressively.
        tint_world.fill((238, 248, 255, 255))
        self.canvas.blit(tint_world, WORLD_RECT.topleft, special_flags=pygame.BLEND_RGBA_MULT)

        # UI region
        tint_ui = pygame.Surface((UI_RECT.w, UI_RECT.h), pygame.SRCALPHA)
        tint_ui.fill((238, 248, 255, 255))
        self.canvas.blit(tint_ui, UI_RECT.topleft, special_flags=pygame.BLEND_RGBA_MULT)

    def _holo_corner_brackets(self, rect: pygame.Rect, col: Tuple[int,int,int]) -> None:
        # Tint-only hologram: no corner brackets/line work.
        return


    def _render_ui(self):
        pygame.draw.rect(self.canvas, HOLO_BG, UI_RECT)
        pygame.draw.rect(self.canvas, HOLO_PANEL, UI_RECT.inflate(-10, -10), border_radius=14)
        pygame.draw.rect(self.canvas, (*HOLO_ACCENT_2, 140), UI_RECT.inflate(-10, -10), 1, border_radius=14)

        # Launcher buttons (kept inside sidebar; never overlaps the world view)
        self._launcher_clicks = []
        # AIR_MODE_UI_LOCK
        if getattr(self, 'air_mode', False):
            # Disable launcher interaction while flying.
            self._launcher_clicks = []
        
        y = 10
        y = draw_text(self.canvas, self.font_big, 'SEQUENCES', UI_X + 12, y, HOLO_TEXT)

        btn_h = 26
        btn_w = UI_W - 24
        for e in self.launcher_entries:
            r = pygame.Rect(UI_X + 12, y, btn_w, btn_h)
            enabled = (e.key in getattr(self, 'unlocked_launcher_keys', set([x.key for x in self.launcher_entries])))
            active = (e.key == self.active_launcher_key)

            if not enabled:
                bg = (10, 12, 14)
                label_col = (90, 120, 115)
            else:
                bg = (18, 26, 34) if not active else (10, 60, 70)
                label_col = HOLO_TEXT if active else (170, 230, 220)

            pygame.draw.rect(self.canvas, bg, r, border_radius=8)
            pygame.draw.rect(self.canvas, (*HOLO_ACCENT, 120), r, 1, border_radius=8)
            
            self.canvas.blit(self.font.render(e.label, True, label_col), (r.x + 10, r.y + 5))
            # Quick context swatches: your team (left) vs current enemy (right)
            if enabled and getattr(self, 'player_fid', None) is not None and e.key not in ('doomsday', 'ground'):
                try:
                    pf = self.sim.factions.get(int(self.player_fid))
                    pcol = pf.color if pf else (200, 200, 200)
                    pair = self._player_war_pair()
                    ecol = (120, 120, 120)
                    if pair is not None:
                        a, d = pair
                        enemy = d if int(self.player_fid) == int(a) else a
                        ef = self.sim.factions.get(int(enemy))
                        if ef is not None:
                            ecol = ef.color
                    sx = r.right - 50
                    pygame.draw.rect(self.canvas, pcol, (sx, r.y + 6, 18, 14), border_radius=3)
                    pygame.draw.rect(self.canvas, ecol, (sx + 22, r.y + 6, 18, 14), border_radius=3)
                    pygame.draw.rect(self.canvas, (0, 0, 0), (sx, r.y + 6, 18, 14), 1, border_radius=3)
                    pygame.draw.rect(self.canvas, (0, 0, 0), (sx + 22, r.y + 6, 18, 14), 1, border_radius=3)
                except Exception:
                    pass


            if enabled:
                self._launcher_clicks.append((r, e.key))
            y += btn_h + 6

        y += 8

        y = draw_text(self.canvas, self.font_big, "WORLD STATUS", UI_X + 12, y, (245, 245, 245))

        speed = SPEED_LEVELS[self.speed_index]
        status = "PAUSED" if self.paused else f"{speed:0.2f}x"
        y = draw_text(self.canvas, self.font, f"Time: {status}", UI_X + 12, y)
        y = draw_text(self.canvas, self.font_small, "SPACE pause | [ ] speed | R restart", UI_X + 12, y, (190, 190, 190))
        y += 8

        active = sum(1 for f in self.sim.factions.values() if len(f.regions) > 0)
        y = draw_text(self.canvas, self.font, f"Active factions: {active}", UI_X + 12, y)
        y = draw_text(self.canvas, self.font, f"Active invasions: {len(self.sim.wars)}", UI_X + 12, y)
        if self.sim.wars:
            y = draw_text(self.canvas, self.font_small, "ENTER: join ground combat (auto-jumps to a frontline)", UI_X + 12, y, (190, 190, 190))

        y += 10
        y = draw_text(self.canvas, self.font_big, "TEAM", UI_X + 12, y, (245, 245, 245))

        if getattr(self, 'player_fid', None) is None or getattr(self, 'team_select_active', False):
            y = draw_text(self.canvas, self.font_small, "Not selected. Click a territory on the map.", UI_X + 12, y, (235, 235, 235))
        else:
            pf = self.sim.factions.get(int(self.player_fid))
            if pf is not None:
                y = draw_text(self.canvas, self.font, f"Your faction: {pf.name}", UI_X + 12, y, pf.color)
                # Current enemy (active invasion involving you)
                side_ctx = self._get_player_mode_matchup()
                enemy = side_ctx.get("enemy_fid") if isinstance(side_ctx, dict) else None
                if enemy is not None:
                    ef = self.sim.factions.get(int(enemy))
                    if ef is not None:
                        y = draw_text(self.canvas, self.font_small, f"Enemy: {ef.name}", UI_X + 12, y, ef.color)
                    else:
                        y = draw_text(self.canvas, self.font_small, f"Enemy: Faction {enemy}", UI_X + 12, y, (235, 235, 235))
                else:
                    y = draw_text(self.canvas, self.font_small, "Enemy: seeking opponent", UI_X + 12, y, (210, 210, 210))
                try:
                    sp = float(self.sim.support.get(int(self.player_fid), 0.0))
                    y = draw_text(self.canvas, self.font_small, f"Support: {sp:0.1f}/40", UI_X + 12, y, (210, 210, 210))
                except Exception:
                    pass
                y = draw_text(self.canvas, self.font_small, "TAB: cycle factions", UI_X + 12, y, (210, 210, 210))
            else:
                y = draw_text(self.canvas, self.font_small, "Your faction: —", UI_X + 12, y, (235, 235, 235))

        y += 8
        y = draw_text(self.canvas, self.font_big, "SELECTION", UI_X + 12, y, (245, 245, 245))

        if self.sim.inspected_cell:
            x, ycell = self.sim.inspected_cell
            owner = self.sim.owner_at(x, ycell)
            rid = self.sim.region_at(x, ycell)
            r = self.sim.ruins_at(x, ycell)
            ctrl = self.sim.region_control[rid]
            cap_hp = self.sim.capital_hp[rid]

            y = draw_text(self.canvas, self.font, f"Cell: ({x},{ycell})", UI_X + 12, y)
            y = draw_text(self.canvas, self.font_small, f"Region: {rid}", UI_X + 12, y, (210, 210, 210))
            y = draw_text(self.canvas, self.font_small, f"Ruins: {r:0.2f}", UI_X + 12, y, (210, 210, 210))
            y = draw_text(self.canvas, self.font_small, f"Region controller: {ctrl}", UI_X + 12, y, (210, 210, 210))
            y = draw_text(self.canvas, self.font_small, f"Capital HP: {cap_hp:0.0f}/{CAPITAL_HP_MAX:0.0f}", UI_X + 12, y, (210, 210, 210))

            if owner >= 0 and owner in self.sim.factions:
                f = self.sim.factions[owner]
                y = draw_text(self.canvas, self.font, f"Owner: {f.name}", UI_X + 12, y, (240, 240, 240))
                y = draw_text(self.canvas, self.font_small, f"Style: {f.style}", UI_X + 12, y, (210, 210, 210))
                y = draw_text(self.canvas, self.font_small, f"Troops: {f.troops:0.0f}", UI_X + 12, y, (210, 210, 210))
                y = draw_text(self.canvas, self.font_small, f"Resources: {f.resources:0.0f}", UI_X + 12, y, (210, 210, 210))
                b = f.buildings
                y = draw_text(self.canvas, self.font_small,
                              f"Bld: H{b.get('Housing',0)} F{b.get('Factory',0)} B{b.get('Barracks',0)} C{b.get('Civic',0)}",
                              UI_X + 12, y, (210, 210, 210))
                y = draw_text(self.canvas, self.font_small,
                              f"     Fa{b.get('Farm',0)} S{b.get('Silo',0)} L{b.get('Lab',0)} | Queue {len(f.build_queue)}",
                              UI_X + 12, y, (210, 210, 210))
                y = draw_text(self.canvas, self.font_small,
                              f"Controls regions: {len(f.regions)}",
                              UI_X + 12, y, (210, 210, 210))
            else:
                y = draw_text(self.canvas, self.font, "Owner: —", UI_X + 12, y, (210, 210, 210))
        else:
            y = draw_text(self.canvas, self.font_small, "Right-click a tile to inspect.", UI_X + 12, y, (200, 200, 200))
        y += 10
        y = draw_text(self.canvas, self.font_big, "BATTLE FEED", UI_X + 12, y, (245, 245, 245))
        feed_top = y
        feed_bottom = CANVAS_H - 18
        feed_w = UI_W - 32
        lines: List[str] = []
        for raw in list(self.sim.news):
            lines.extend(wrap_text_lines(self.font_small, raw, feed_w - 8))
            lines.append("")
        if lines and not lines[-1]:
            lines.pop()
        max_visible = max(1, (feed_bottom - feed_top) // (self.font_small.get_height() + 2))
        max_scroll = max(0, len(lines) - max_visible)
        self.feed_scroll = max(0, min(int(self.feed_scroll), max_scroll))
        yy = feed_top
        for line in lines[self.feed_scroll:self.feed_scroll + max_visible]:
            yy = draw_text(self.canvas, self.font_small, line, UI_X + 12, yy, (210, 205, 195))
            if yy > feed_bottom:
                break
        if max_scroll > 0:
            track = pygame.Rect(UI_RECT.right - 10, feed_top, 4, max(18, feed_bottom - feed_top))
            pygame.draw.rect(self.canvas, (52, 40, 32), track, border_radius=3)
            thumb_h = max(18, int(track.h * (max_visible / max(1, len(lines)))))
            thumb_y = track.y + int((track.h - thumb_h) * (self.feed_scroll / max(1, max_scroll)))
            pygame.draw.rect(self.canvas, HOLO_ACCENT, (track.x, thumb_y, track.w, thumb_h), border_radius=3)


    def _render_toast(self):
        if self.toast_timer <= 0.0 or not self.toast_msg:
            return
        # Fade out gently.
        t = clamp(self.toast_timer / 2.4, 0.0, 1.0)
        alpha = int(180 * t)
        panel_h = 34
        panel = pygame.Surface((WORLD_RECT.w, panel_h), pygame.SRCALPHA)
        panel.fill((0, 0, 0, alpha))
        self.canvas.blit(panel, (WORLD_RECT.x, WORLD_RECT.bottom - panel_h))
        self.canvas.blit(self.font.render(self.toast_msg, True, (245, 245, 245)), (WORLD_RECT.x + 10, WORLD_RECT.bottom - panel_h + 8))
    def _render_embedded(self):
        # Draw the embedded game into WORLD_RECT and keep sidebar visible.
        self.canvas.fill((10, 12, 16))
        if self.embedded is not None:
            self.embedded.draw(self.canvas)

        # subtle border around the play area
        pygame.draw.rect(self.canvas, (30, 30, 38), WORLD_RECT, 2)
        pygame.draw.line(self.canvas, (30, 30, 38), (UI_X, 0), (UI_X, CANVAS_H), 2)

        # If embedded has an error, show a readable message in the UI panel
        if self.embedded is not None and self.embedded.error:
            msg = self.embedded.error
            yy = UI_RECT.bottom - 110
            pygame.draw.rect(self.canvas, (30, 10, 10), (UI_X + 10, yy, UI_W - 20, 98), border_radius=6)
            yy += 8
            yy = draw_text(self.canvas, self.font_big, 'LAUNCH ERROR', UI_X + 18, yy, (245, 235, 235))
            for line in (msg[:90], msg[90:180], msg[180:270]):
                if not line:
                    break
                yy = draw_text(self.canvas, self.font_small, line, UI_X + 18, yy, (235, 210, 210))

    def _render(self):
        if getattr(self, "embedded", None) is not None:
            self._render_embedded()
        elif self.mode == self.MODE_GROUND:
            self._render_ground_combat()
        elif self.mode == self.MODE_GROUND_PICK:
            # show the current area view if available; otherwise show world
            if self.area_map and self.area_cell:
                self._render_area_view()
            else:
                self._render_world()
            self._render_ground_pick_overlay()
        elif self.mode == self.MODE_AREA:
            self._render_area_view()
        else:
            self._render_world()

        # If a standalone mode is running, show a small status banner in the world panel.
        try:
            k = getattr(self, 'active_launcher_key', 'doomsday')
            if k != 'doomsday' and k in getattr(self, 'mode_procs', {}):
                p = self.mode_procs.get(k)
                if p is not None and p.is_running():
                    panel = pygame.Surface((WORLD_RECT.w, 46), pygame.SRCALPHA)
                    panel.fill((0, 0, 0, 165))
                    self.canvas.blit(panel, (WORLD_RECT.x, WORLD_RECT.y))
                    self.canvas.blit(self.font.render(f"{p.title} is running in a separate window.", True, (245, 245, 245)), (WORLD_RECT.x + 10, WORLD_RECT.y + 10))
                    self.canvas.blit(self.font_small.render("Close that window to return results to the Doomsday map.", True, (210, 210, 210)), (WORLD_RECT.x + 10, WORLD_RECT.y + 28))
        except Exception:
            pass

        self._render_ui()
        self._render_toast()

        # Holographic postprocess over the map view only.
        if getattr(self, 'active_launcher_key', 'doomsday') == 'doomsday':
            self._holo_postprocess()

        # Present with letterboxing
        win_w, win_h = self.win_size
        scale = min(win_w / CANVAS_W, win_h / CANVAS_H)
        out_w = max(1, int(CANVAS_W * scale))
        out_h = max(1, int(CANVAS_H * scale))
        off_x = (win_w - out_w) // 2
        off_y = (win_h - out_h) // 2
        self._present = (scale, off_x, off_y)

        scaled = pygame.transform.smoothscale(self.canvas, (out_w, out_h))
        self.window.fill((0, 0, 0))
        self.window.blit(scaled, (off_x, off_y))
        pygame.display.flip()


def main():
    Game().run()

if __name__ == "__main__":
    main()