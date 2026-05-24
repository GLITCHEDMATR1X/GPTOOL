from __future__ import annotations
import json
import math
import os
import random
import sys
import time
from pathlib import Path
from dataclasses import dataclass
from typing import List, Tuple, Optional

import pygame

try:
    _HV_RUNTIME_ROOT = None
    for _hv_parent in Path(__file__).resolve().parents:
        if (_hv_parent / "holoverse_mode_runtime.py").exists():
            _HV_RUNTIME_ROOT = _hv_parent
            break
    if _HV_RUNTIME_ROOT is not None and str(_HV_RUNTIME_ROOT) not in sys.path:
        sys.path.insert(0, str(_HV_RUNTIME_ROOT))
    import holoverse_mode_runtime as hv_runtime
except Exception:
    hv_runtime = None

HOLOVERSE_EMBEDDED = bool(hv_runtime.embedded_mode()) if hv_runtime else False
HOLOVERSE_SETTINGS = hv_runtime.load_settings() if hv_runtime else {}
SHARED_SFX_ROOT = hv_runtime.shared_sfx_root() if hv_runtime else (Path(__file__).resolve().parent.parent / "assets" / "shared_sfx")
AUDIO_PROFILE = hv_runtime.load_audio_profile(Path(__file__).resolve().parent) if hv_runtime else {}

UNIVERSAL_PROFILE = hv_runtime.visual_profile() if hv_runtime else {"ui_scale": 1.0, "brightness": 1.0, "contrast": 1.0, "gamma": 1.0}

def holoverse_embedded_escape(default_handler=None):
    if hv_runtime is not None:
        return hv_runtime.embedded_escape_pressed(default_handler)
    if callable(default_handler):
        return default_handler()
    return None

def holoverse_return_signal_requested():
    try:
        return bool(HOLOVERSE_EMBEDDED and hv_runtime is not None and hv_runtime.should_return_to_core())
    except Exception:
        return False

WIDTH, HEIGHT = (hv_runtime.virtual_canvas((1920, 1080)) if hv_runtime else (1920, 1080))
WINDOW_WIDTH, WINDOW_HEIGHT = (hv_runtime.resolution((WIDTH, HEIGHT)) if hv_runtime else (WIDTH, HEIGHT))
FPS = hv_runtime.fps_cap(60) if hv_runtime else int(HOLOVERSE_SETTINGS.get("fps_cap", 60) or 60) if HOLOVERSE_SETTINGS else 60

# Clinical lab palette
BG = (5, 11, 15)
BG_2 = (8, 17, 23)
GRID_DARK = (14, 27, 34)
PANEL = (12, 25, 32)
PANEL_2 = (15, 31, 39)
PANEL_3 = (19, 40, 49)
PANEL_4 = (23, 50, 60)
BORDER = (70, 121, 132)
TEXT = (224, 235, 237)
MUTED = (132, 157, 164)
WHITE = (241, 247, 248)
SHADOW = (2, 6, 8)
CYAN = (92, 214, 214)
TEAL = (71, 178, 167)
MINT = (146, 218, 170)
LIME = (176, 219, 110)
AMBER = (226, 179, 94)
RED = (214, 98, 105)
VIOLET = (167, 130, 226)
ICE = (188, 230, 236)

def _env_int(name: str, default: int) -> int:
    try:
        return int(float(os.environ.get(name, default)))
    except Exception:
        return default

if not hv_runtime:
    WINDOW_WIDTH = max(640, min(3840, _env_int("MATRIX_GAME_WIDTH", WINDOW_WIDTH)))
    WINDOW_HEIGHT = max(360, min(2160, _env_int("MATRIX_GAME_HEIGHT", WINDOW_HEIGHT)))

pygame.init()
pygame.display.set_caption("Helix Biogenics // HoloVerse Hosted")
_display = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.RESIZABLE)
if HOLOVERSE_EMBEDDED:
    try:
        pygame.event.set_grab(False)
        pygame.mouse.set_visible(True)
    except Exception:
        pass
screen = pygame.Surface((WIDTH, HEIGHT)).convert()
_scaled_frame = None
clock = pygame.time.Clock()


def _letterbox(window_size=None):
    if window_size is None:
        window_size = _display.get_size()
    if hv_runtime:
        return hv_runtime.compute_letterbox(window_size, (WIDTH, HEIGHT))
    win_w, win_h = window_size
    scale = min(win_w / WIDTH, win_h / HEIGHT)
    view_w = max(1, int(WIDTH * scale))
    view_h = max(1, int(HEIGHT * scale))
    return scale, (view_w, view_h), ((win_w - view_w) // 2, (win_h - view_h) // 2)


def _window_to_canvas(pos):
    if hv_runtime:
        return hv_runtime.window_to_canvas(pos, _display.get_size(), (WIDTH, HEIGHT))
    scale, _view, offset = _letterbox(_display.get_size())
    x = int((pos[0] - offset[0]) / max(scale, 1e-6))
    y = int((pos[1] - offset[1]) / max(scale, 1e-6))
    return max(0, min(WIDTH - 1, x)), max(0, min(HEIGHT - 1, y))


def _map_mouse_event(event):
    if hasattr(event, "pos"):
        try:
            if hv_runtime and event.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
                if not hv_runtime.point_in_view(event.pos, _display.get_size(), (WIDTH, HEIGHT)):
                    return None
        except Exception:
            pass
        data = dict(getattr(event, "dict", {}) or {})
        data["pos"] = _window_to_canvas(event.pos)
        try:
            return pygame.event.Event(event.type, data)
        except Exception:
            return event
    return event


def present_frame():
    global _scaled_frame
    win_w, win_h = _display.get_size()
    _display.fill((0, 0, 0))
    _scale, view_size, offset = _letterbox((win_w, win_h))
    if view_size == (WIDTH, HEIGHT) and offset == (0, 0):
        _display.blit(screen, (0, 0))
    else:
        if _scaled_frame is None or _scaled_frame.get_size() != view_size:
            _scaled_frame = pygame.Surface(view_size).convert()
        pygame.transform.smoothscale(screen, view_size, _scaled_frame)
        _display.blit(_scaled_frame, offset)
    pygame.display.flip()

FONT = pygame.font.SysFont("consolas", 20)
SMALL = pygame.font.SysFont("consolas", 16)
TITLE = pygame.font.SysFont("arial", 34, bold=True)
HEADER = pygame.font.SysFont("arial", 24, bold=True)
MICRO = pygame.font.SysFont("consolas", 13)


def clamp(v, a, b):
    return max(a, min(b, v))


def lerp(a, b, t):
    return a + (b - a) * t


def draw_text(surf, text, font, color, pos, anchor="topleft"):
    img = font.render(text, True, color)
    rect = img.get_rect()
    setattr(rect, anchor, pos)
    surf.blit(img, rect)
    return rect


def wrap_text(text: str, font, max_width: int) -> list[str]:
    words = str(text or "").split()
    if not words:
        return [""]
    lines: list[str] = []
    current = ""
    for word in words:
        trial = word if not current else current + " " + word
        if font.size(trial)[0] <= max_width or not current:
            current = trial
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def set_action_message(message: str, ms: int = 2200):
    global ACTION_MESSAGE, ACTION_MESSAGE_UNTIL
    ACTION_MESSAGE = str(message or "")
    ACTION_MESSAGE_UNTIL = pygame.time.get_ticks() + int(ms)


def load_biolog_entries(limit: int = 8) -> list[dict]:
    entries: list[dict] = []
    try:
        if BIOLOG_LOG_PATH.exists():
            data = json.loads(BIOLOG_LOG_PATH.read_text(encoding="utf-8"))
            raw = data.get("entries", []) if isinstance(data, dict) else []
            if isinstance(raw, list):
                entries.extend(item for item in raw if isinstance(item, dict))
    except Exception:
        entries = []
    if not entries:
        entries = [
            {"time": "LAB", "kind": "SYSTEM", "text": "Biolog online. Press E to record a specimen scan."},
            {"time": "LAB", "kind": "CONTROL", "text": "Core settings override display, HUD, and input behavior while hosted."},
        ]
    return entries[-max(1, int(limit)):]


def append_biolog_entry(kind: str, text: str, exp: Experiment | None = None) -> None:
    entry = {
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "kind": str(kind or "NOTE").upper(),
        "text": str(text or ""),
    }
    if exp is not None:
        entry.update({
            "code": exp.code,
            "name": exp.name,
            "state": exp.state,
            "vitality": round(float(exp.vitality), 2),
            "mutation": round(float(exp.mutation), 2),
            "threat": round(float(exp.threat), 2),
            "breakthrough": round(float(exp.breakthrough), 2),
        })
    try:
        data = {"schema": 1, "title": "HELIX BIOLOG", "mode_id": "helix_biogenics", "entries": []}
        if BIOLOG_LOG_PATH.exists():
            loaded = json.loads(BIOLOG_LOG_PATH.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                data.update(loaded)
        entries = data.get("entries", [])
        if not isinstance(entries, list):
            entries = []
        entries.append(entry)
        data["entries"] = entries[-80:]
        data["updated_at"] = entry["time"]
        BIOLOG_LOG_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception:
        pass


def record_specimen_scan() -> None:
    exp = experiments[selected]
    note = f"Scan captured for {exp.code} {exp.name}: {exp.state}; mutation {int(exp.mutation)}%, threat {int(exp.threat)}%."
    SESSION_SCANS.append({"code": exp.code, "name": exp.name, "state": exp.state, "tick": pygame.time.get_ticks()})
    alert_log.insert(0, note)
    del alert_log[5:]
    append_biolog_entry("SCAN", note, exp)
    set_action_message(f"SPECIMEN SCAN SAVED · {exp.code} {exp.name}")
    try:
        HELIX_AUDIO.play("scan", 1.0)
    except Exception:
        pass


def gradient_fill(surf, rect, c1, c2, vertical=True):
    if rect.w <= 0 or rect.h <= 0:
        return
    grad = pygame.Surface((rect.w, rect.h))
    steps = rect.h if vertical else rect.w
    for i in range(steps):
        t = i / max(1, steps - 1)
        col = tuple(int(lerp(a, b, t)) for a, b in zip(c1, c2))
        if vertical:
            pygame.draw.line(grad, col, (0, i), (rect.w, i))
        else:
            pygame.draw.line(grad, col, (i, 0), (i, rect.h))
    surf.blit(grad, rect.topleft)


def panel(surf, rect, title=None, tint=PANEL):
    pygame.draw.rect(surf, SHADOW, rect.inflate(8, 8), border_radius=12)
    gradient_fill(surf, rect, tint, tone(tint, 8))
    pygame.draw.rect(surf, BORDER, rect, 1, border_radius=12)
    if title:
        title_rect = pygame.Rect(rect.x, rect.y, rect.w, 40)
        gradient_fill(surf, title_rect, PANEL_3, PANEL_2)
        pygame.draw.line(surf, BORDER, (rect.x, rect.y + 40), (rect.right, rect.y + 40), 1)
        draw_text(surf, title, HEADER, WHITE, (rect.x + 14, rect.y + 8))



class HelixAudio:
    """Tiny shared-SFX player for the low-power Helix companion panel."""
    def __init__(self):
        self.enabled = False
        self.cache = {}
        self.bus = 0.55
        try:
            if hv_runtime:
                self.bus = hv_runtime.sfx_bus_gain("sfx", 0.55)
        except Exception:
            self.bus = 0.55
        try:
            if pygame.mixer.get_init() is None:
                pygame.mixer.init(frequency=22050, size=-16, channels=2, buffer=256)
            self.enabled = True
        except Exception:
            self.enabled = False

    def _path(self, name: str):
        try:
            if hv_runtime:
                profile_files = hv_runtime.profile_sfx_files(name, profile=AUDIO_PROFILE)
                if profile_files:
                    return profile_files[0]
        except Exception:
            pass
        try:
            aliases = {
                "scan": ["scan_confirm", "sm_bio_scan_01"],
                "select": ["scan_select", "sm_ui_select_01"],
                "biolog_open": ["biolog_open", "menu_open"],
                "biolog_close": ["biolog_close", "menu_close"],
                "hud_toggle": ["sm_ui_select_01"],
                "pause": ["menu_open"],
                "resume": ["menu_close"],
                "return_core": ["sm_core_return_01"],
            }
            names = aliases.get(name, [name])
            for item in names:
                for folder in ("science", "ui"):
                    p = SHARED_SFX_ROOT / folder / f"{item}.wav"
                    if p.exists():
                        return p
        except Exception:
            pass
        return None

    def start_music(self):
        if not self.enabled or not hv_runtime or not hv_runtime.soundtrack_enabled(True):
            return
        try:
            music_path = hv_runtime.next_profile_music_path(getattr(self, "current_music_path", ""), profile=AUDIO_PROFILE)
            if music_path and music_path.exists():
                self.current_music_path = str(music_path)
                self.next_music_rotate_t = time.time() + hv_runtime.profile_music_rotation_seconds(60.0, profile=AUDIO_PROFILE)
                pygame.mixer.music.set_volume(hv_runtime.music_bus_gain(hv_runtime.profile_music_volume(0.34, profile=AUDIO_PROFILE), bus="ambience"))
                pygame.mixer.music.load(str(music_path))
                pygame.mixer.music.play(-1)
        except Exception:
            pass

    def update_music_rotation(self):
        if not self.enabled or not hv_runtime or not hv_runtime.soundtrack_enabled(True):
            return
        if time.time() >= float(getattr(self, "next_music_rotate_t", 0.0) or 0.0):
            self.start_music()

    def play(self, name: str, volume: float = 1.0):
        if not self.enabled:
            return
        path = self._path(name)
        if path is None:
            return
        try:
            snd = self.cache.get(str(path))
            if snd is None:
                snd = pygame.mixer.Sound(str(path))
                self.cache[str(path)] = snd
            snd.set_volume(max(0.0, min(1.0, self.bus * float(volume))))
            snd.play()
        except Exception:
            pass

HELIX_AUDIO = HelixAudio()
HELIX_AUDIO.start_music()

@dataclass
class Experiment:
    code: str
    name: str
    state: str
    vitality: float
    biomass: float
    pollen: float
    toxin: float
    mutation: float
    breakthrough: float
    threat: float
    hue: Tuple[int, int, int]
    takeover: float = 0.0
    growth_phase: float = 0.0
    incident: str = ""
    species_mix: float = 0.0
    humidity: float = 0.0
    nutrients: float = 0.0
    stability: float = 0.0

    def update(self, dt: float):
        self.growth_phase += dt * (0.12 + self.vitality * 0.001)
        drift = math.sin(self.growth_phase * 0.6 + hash(self.code) % 7) * 0.2
        self.biomass = clamp(self.biomass + dt * (2.0 + drift - self.threat * 0.02), 0, 100)
        self.pollen = clamp(self.pollen + dt * (0.7 + math.sin(self.growth_phase * 1.7) * 0.6), 0, 100)
        self.mutation = clamp(self.mutation + dt * (0.3 + self.species_mix * 0.8 + self.takeover * 0.15), 0, 100)
        self.breakthrough = clamp(self.breakthrough + dt * (0.06 + self.mutation * 0.004 - self.toxin * 0.0015), 0, 100)
        self.threat = clamp(self.threat + dt * (0.18 + self.pollen * 0.008 + self.toxin * 0.006 + self.takeover * 0.04), 0, 100)
        self.vitality = clamp(self.vitality + dt * (0.8 - self.toxin * 0.01 - self.threat * 0.008), 0, 100)
        self.humidity = 45 + math.sin(self.growth_phase * 0.7 + self.seed) * 18 + self.pollen * 0.2
        self.nutrients = clamp(58 + math.cos(self.growth_phase * 0.5 + self.seed) * 16 - self.biomass * 0.08, 0, 100)
        self.stability = clamp(100 - (self.mutation * 0.7 + self.threat * 0.55 + self.takeover * 0.8), 0, 100)
        if self.takeover > 28 or self.threat > 70:
            self.state = "Breach Risk"
            self.incident = "Containment flexion rising"
        elif self.mutation > 44:
            self.state = "Hybrid Active"
            self.incident = "Hybridization detected"
        elif self.biomass > 60:
            self.state = "Blooming"
            self.incident = "Peak flowering window"
        else:
            self.state = "Stable"
            self.incident = "Controlled growth"

    @property
    def seed(self):
        return sum(ord(c) for c in (self.code + self.name))



@dataclass
class PipWindow:
    exp_index: int
    rect: pygame.Rect
    mode: str = "LIVE"
    dragging: bool = False
    drag_off: Tuple[int, int] = (0, 0)


experiments: List[Experiment] = [
    Experiment("A-01", "Verdant-9", "Stable", 84, 28, 20, 6, 9, 12, 11, (121, 214, 153), species_mix=0.08, takeover=3),
    Experiment("A-02", "Sable Bloom", "Stress", 76, 42, 31, 18, 21, 16, 27, (208, 148, 123), species_mix=0.15, takeover=6),
    Experiment("B-03", "Bloom Arc", "Hybrid Active", 80, 55, 48, 14, 26, 18, 34, (169, 217, 108), species_mix=0.26, takeover=11),
    Experiment("B-04", "Null Fern", "Stable", 88, 38, 14, 5, 8, 7, 6, (111, 201, 170), species_mix=0.05, takeover=2),
    Experiment("C-02", "Ash Vine", "Breach Risk", 69, 63, 52, 29, 33, 22, 58, (184, 132, 106), takeover=22, species_mix=0.21),
]
selected = 2
pinned = [1, 2, 4]
pips = [
    PipWindow(1, pygame.Rect(1170, 82, 240, 154), "BIO"),
    PipWindow(4, pygame.Rect(1188, 260, 230, 148), "CHEM"),
]
alert_log = [
    "Mutation alert: hybridization detected in B-03.",
    "New compound discovered: lumina extract.",
    "Sector C root intrusion probability increased.",
]
view_mode = "LIVE"
sim_speed = 4
screen_mode = "OVERVIEW"
SHOW_HUD = bool(HOLOVERSE_SETTINGS.get("hud_enabled", True)) if HOLOVERSE_SETTINGS else True
SHOW_BIOLOG = False
SESSION_SCANS: list[dict] = []
ACTION_MESSAGE = ""
ACTION_MESSAGE_UNTIL = 0
BIOLOG_LOG_PATH = Path(__file__).resolve().parent / "helix_biolog_log.json"


def tone(color, amt):
    return tuple(clamp(int(c + amt), 0, 255) for c in color)


def tint_mix(c1, c2, t):
    return tuple(int(lerp(a, b, t)) for a, b in zip(c1, c2))


def draw_lab_grid(surf, rect):
    for i in range(0, rect.w, 28):
        x = rect.x + i
        pygame.draw.line(surf, GRID_DARK, (x, rect.y), (x, rect.bottom), 1)
    for i in range(0, rect.h, 28):
        y = rect.y + i
        pygame.draw.line(surf, GRID_DARK, (rect.x, y), (rect.right, y), 1)


def draw_capsule_frame(surf, chamber):
    shell = pygame.Rect(chamber.x, chamber.y, chamber.w, chamber.h)
    pygame.draw.rect(surf, (18, 31, 37), shell, border_radius=max(26, shell.w // 7))
    pygame.draw.rect(surf, BORDER, shell, 2, border_radius=max(26, shell.w // 7))
    top_ring = pygame.Rect(shell.x + 18, shell.y + 10, shell.w - 36, 16)
    bot_ring = pygame.Rect(shell.x + 14, shell.bottom - 22, shell.w - 28, 14)
    pygame.draw.rect(surf, (28, 52, 60), top_ring, border_radius=8)
    pygame.draw.rect(surf, (28, 52, 60), bot_ring, border_radius=8)
    glass = pygame.Surface(shell.size, pygame.SRCALPHA)
    pygame.draw.rect(glass, (180, 236, 244, 20), glass.get_rect(), border_radius=max(26, shell.w // 7))
    pygame.draw.rect(glass, (205, 245, 250, 18), (shell.w * 0.12, 0, shell.w * 0.16, shell.h), border_radius=18)
    pygame.draw.rect(glass, (205, 245, 250, 9), (shell.w * 0.72, 0, shell.w * 0.07, shell.h), border_radius=12)
    surf.blit(glass, shell.topleft)


def generate_plant_columns(exp: Experiment, width_px: int, height_px: int):
    rng = random.Random(exp.seed)
    cols = []
    stem_count = 10 + int(exp.biomass // 6)
    max_h = int(height_px * (0.25 + 0.0065 * exp.biomass))
    for i in range(stem_count):
        base_x = int((i + 0.7) / (stem_count + 1) * width_px)
        base_x += rng.randint(-9, 9)
        stem_h = rng.randint(int(max_h * 0.45), max_h)
        bend = rng.uniform(-0.5, 0.5) + math.sin(exp.growth_phase * 0.8 + i * 0.7) * 0.25
        nodes = 4 + rng.randint(0, 4) + int(exp.mutation // 30)
        cols.append((base_x, stem_h, bend, nodes, rng.randint(0, 999999)))
    return cols


def draw_pixel_cluster(surface, x, y, color, cell, alpha=255):
    r = pygame.Rect(int(x), int(y), cell, cell)
    if alpha >= 255:
        pygame.draw.rect(surface, color, r)
    else:
        s = pygame.Surface((cell, cell), pygame.SRCALPHA)
        s.fill((*color, alpha))
        surface.blit(s, r.topleft)


def draw_procedural_ecosystem(surf, rect, exp: Experiment, mode: str):
    chamber_margin = 18
    cell = max(3, min(8, rect.w // 70))
    grid_w = max(12, (rect.w - chamber_margin * 2) // cell)
    grid_h = max(16, (rect.h - 18) // cell)
    origin_x = rect.x + chamber_margin + ((rect.w - chamber_margin * 2) - grid_w * cell) // 2
    origin_y = rect.y + 10
    cols = generate_plant_columns(exp, grid_w, grid_h)
    base_y = grid_h - 2

    # substrate / runoff
    for gx in range(grid_w):
        for gy in range(base_y + 1, grid_h):
            shade = 16 + ((gx * 7 + gy * 5 + exp.seed) % 14)
            col = (24 + shade, 42 + shade, 34 + shade // 2)
            if exp.takeover > 15 and (gx + gy + exp.seed) % 9 == 0:
                col = tint_mix(col, RED, 0.25)
            draw_pixel_cluster(surf, origin_x + gx * cell, origin_y + gy * cell, col, cell)

    # roots
    for base_x, stem_h, bend, nodes, seed in cols:
        rr = random.Random(seed)
        y = base_y
        x = int(base_x)
        for _ in range(8 + rr.randint(0, 10)):
            x += rr.choice([-1, 0, 1])
            y += 1
            if 0 <= x < grid_w and y < grid_h:
                root_color = tint_mix((94, 76, 52), exp.hue, 0.12)
                if exp.takeover > 16 and rr.random() < 0.22:
                    root_color = tint_mix(root_color, RED, 0.35)
                draw_pixel_cluster(surf, origin_x + x * cell, origin_y + y * cell, root_color, cell)
                if rr.random() < 0.35:
                    bx = x + rr.choice([-1, 1])
                    if 0 <= bx < grid_w:
                        draw_pixel_cluster(surf, origin_x + bx * cell, origin_y + y * cell, tone(root_color, 8), cell)

    dominant = exp.hue
    leaf_hi = tone(exp.hue, 28)
    leaf_lo = tone(exp.hue, -32)
    blossom = tint_mix(exp.hue, AMBER, 0.55)
    hybrid = tint_mix(exp.hue, VIOLET, min(0.45, exp.mutation / 130))
    invasive = tint_mix(exp.hue, RED, min(0.45, exp.takeover / 60))

    for idx, (base_x, stem_h, bend, nodes, seed) in enumerate(cols):
        rr = random.Random(seed)
        x = float(base_x)
        y = float(base_y)
        target_y = max(4, base_y - stem_h)
        dx = bend * 0.38
        stem_points = []
        while y > target_y:
            stem_points.append((int(round(x)), int(round(y))))
            x += dx + math.sin((base_y - y) * 0.18 + exp.growth_phase * 0.9 + idx * 0.4) * 0.07
            y -= 1
        for sx, sy in stem_points:
            if 0 <= sx < grid_w and 0 <= sy < grid_h:
                stem_col = tint_mix(leaf_lo, dominant, sy / grid_h)
                if exp.takeover > 12 and rr.random() < 0.07:
                    stem_col = invasive
                draw_pixel_cluster(surf, origin_x + sx * cell, origin_y + sy * cell, stem_col, cell)
                if rr.random() < 0.18 and sx + 1 < grid_w:
                    draw_pixel_cluster(surf, origin_x + (sx + 1) * cell, origin_y + sy * cell, stem_col, cell)

        for n in range(nodes):
            t = n / max(1, nodes - 1)
            anchor = stem_points[int((1 - t) * (len(stem_points) - 1))]
            ax, ay = anchor
            spread = 2 + int(2 + exp.biomass / 28 + rr.random() * 3)
            for side in (-1, 1):
                for i in range(spread):
                    lx = ax + side * (1 + i)
                    ly = ay + i // 2 + rr.randint(-1, 1)
                    if 0 <= lx < grid_w and 0 <= ly < grid_h:
                        leaf_col = leaf_hi if i % 2 == 0 else dominant
                        if rr.random() < 0.13:
                            leaf_col = hybrid
                        if exp.takeover > 16 and rr.random() < 0.15:
                            leaf_col = invasive
                        draw_pixel_cluster(surf, origin_x + lx * cell, origin_y + ly * cell, leaf_col, cell)
                        if i > 1 and rr.random() < 0.55 and ly - 1 >= 0:
                            draw_pixel_cluster(surf, origin_x + lx * cell, origin_y + (ly - 1) * cell, leaf_lo, cell)

            if rr.random() < 0.45 + exp.breakthrough / 200:
                bloom_size = 2 + rr.randint(0, 2) + int(exp.breakthrough // 35)
                for ox in range(-bloom_size, bloom_size + 1):
                    for oy in range(-bloom_size, bloom_size + 1):
                        if abs(ox) + abs(oy) <= bloom_size + rr.randint(0, 1):
                            px = ax + ox
                            py = ay - 1 + oy
                            if 0 <= px < grid_w and 0 <= py < grid_h:
                                c = blossom if (ox + oy) % 2 == 0 else tone(blossom, 18)
                                if exp.mutation > 40 and rr.random() < 0.25:
                                    c = hybrid
                                draw_pixel_cluster(surf, origin_x + px * cell, origin_y + py * cell, c, cell)

    overlay = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
    for i in range(16):
        px = int((math.sin(exp.growth_phase * 0.7 + i * 2.1) * 0.5 + 0.5) * rect.w)
        py = int((math.cos(exp.growth_phase * 1.1 + i * 1.3) * 0.5 + 0.5) * rect.h)
        if mode == "CHEM":
            col = (*AMBER, 40)
        elif mode == "BIO":
            col = (*MINT, 34)
        elif mode == "GENE":
            col = (*VIOLET, 36)
        elif mode == "STRUCT":
            col = (*RED, 24)
        else:
            col = (*CYAN, 18)
        pygame.draw.circle(overlay, col, (px, py), 8 + (i % 3) * 3)
    surf.blit(overlay, rect.topleft)

    if exp.takeover > 10:
        tendril = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
        for i in range(5):
            sx = rect.w * (0.08 + i * 0.17)
            points = []
            for j in range(8):
                px = int(sx + math.sin(exp.growth_phase * 0.6 + i + j * 0.8) * 18 + j * 12)
                py = int(rect.h * 0.12 + j * (rect.h * 0.1))
                points.append((px, py))
            pygame.draw.lines(tendril, (*RED, 70), False, points, 2)
        surf.blit(tendril, rect.topleft)

    headers = {
        "BIO": ("BIO SCAN · ACTIVE TISSUE / STRESS / REPRODUCTIVE FRONT", CYAN),
        "CHEM": ("CHEMISTRY · POLLEN / VAPOR / NUTRIENT CLOUDS", AMBER),
        "GENE": ("GENETICS · LINEAGE CLUSTERS / DRIFT / HYBRID TISSUE", VIOLET),
        "TIME": ("TIME-LAPSE · GROWTH ARC PLAYBACK", WHITE),
        "STRUCT": ("STRUCTURE · ROOT PRESSURE / VENT CONTACT / GLASS LOAD", RED),
    }
    if mode in headers:
        text, col = headers[mode]
        draw_text(surf, text, SMALL, col, (rect.x + 12, rect.y + 10))
    if mode == "BIO":
        for i in range(0, rect.w, 42):
            pygame.draw.line(surf, (46, 130, 110), (rect.x + i, rect.y), (rect.x + i, rect.bottom), 1)
    elif mode == "CHEM":
        chem = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
        for i in range(4):
            pygame.draw.ellipse(chem, (226, 179, 94, 16), (20 + i * 70, 20 + i * 28, rect.w * 0.28, rect.h * 0.24), 0)
            pygame.draw.ellipse(chem, (214, 98, 105, 13), (30 + i * 95, rect.h * 0.32 + i * 18, rect.w * 0.24, rect.h * 0.19), 0)
        surf.blit(chem, rect.topleft)
    elif mode == "GENE":
        gene = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
        for i in range(7):
            x = 18 + i * (rect.w // 7)
            pygame.draw.line(gene, (118, 164, 240, 58), (x, 20), (x + 40, rect.h - 34), 2)
            for j in range(5):
                pygame.draw.circle(gene, (176, 208, 255, 76), (x + (j % 2) * 12, 50 + j * 42), 4)
        surf.blit(gene, rect.topleft)
    elif mode == "TIME":
        pygame.draw.line(surf, CYAN, (rect.x + 20, rect.bottom - 18), (rect.right - 20, rect.bottom - 18), 2)
        knob_x = int(lerp(rect.x + 20, rect.right - 20, (math.sin(exp.growth_phase * 0.3) + 1) * 0.5))
        pygame.draw.circle(surf, WHITE, (knob_x, rect.bottom - 18), 6)
    elif mode == "STRUCT":
        for i in range(6):
            rx = rect.x + 10 + i * rect.w // 6
            pygame.draw.line(surf, (205, 90, 95), (rx, rect.y + 18), (rx + 12, rect.bottom - 18), 1)


def draw_lab_canvas(surf, rect, exp: Experiment, mode: str):
    panel(surf, rect, f"CHAMBER {exp.code} · {exp.name.upper()} · {exp.state.upper()}")
    inner = rect.inflate(-18, -68)
    gradient_fill(surf, inner, (7, 15, 20), (10, 22, 28))
    draw_lab_grid(surf, inner)
    horizon_y = inner.y + int(inner.h * 0.48)
    pygame.draw.rect(surf, (8, 18, 22), (inner.x, horizon_y, inner.w, inner.bottom - horizon_y))

    for i in range(7):
        rack = pygame.Rect(inner.x + 18 + i * int(inner.w / 7.4), inner.y + 60 + (i % 2) * 18, int(inner.w * 0.09), int(inner.h * 0.64))
        pygame.draw.rect(surf, (12, 26, 31), rack, border_radius=8)
        pygame.draw.rect(surf, (28, 59, 68), rack, 1, border_radius=8)

    chamber = pygame.Rect(inner.x + int(inner.w * 0.18), inner.y + int(inner.h * 0.08), int(inner.w * 0.50), int(inner.h * 0.80))
    draw_capsule_frame(surf, chamber)
    eco_rect = chamber.inflate(-28, -36)
    eco_rect = pygame.Rect(eco_rect.x, eco_rect.y + 8, eco_rect.w, eco_rect.h - 18)
    draw_procedural_ecosystem(surf, eco_rect, exp, mode)

    for side in (-1, 1):
        px = chamber.centerx + side * (chamber.w // 2 + 28)
        column = pygame.Rect(px - 10, chamber.y + 20, 20, chamber.h - 40)
        pygame.draw.rect(surf, (16, 37, 44), column, border_radius=8)
        pygame.draw.rect(surf, BORDER, column, 1, border_radius=8)
        for i in range(4):
            yy = column.y + 30 + i * 68
            pygame.draw.rect(surf, CYAN if i != 2 else AMBER, (column.x + 3, yy, 14, 10), border_radius=3)

    glow = pygame.Surface((240, 240), pygame.SRCALPHA)
    alpha = int(clamp(18 + exp.breakthrough * 0.65, 20, 78))
    pygame.draw.circle(glow, (*exp.hue, alpha), (120, 120), 118)
    surf.blit(glow, (chamber.centerx - 120, chamber.centery - 68), special_flags=pygame.BLEND_PREMULTIPLIED)


def draw_bar(surf, x, y, w, val, color, label, suffix="%"):
    pygame.draw.rect(surf, PANEL_2, (x, y, w, 14), border_radius=7)
    pygame.draw.rect(surf, color, (x, y, int(w * clamp(val / 100, 0, 1)), 14), border_radius=7)
    draw_text(surf, label, SMALL, MUTED, (x, y - 18))
    draw_text(surf, f"{int(val)}{suffix}", SMALL, WHITE, (x + w, y - 18), "topright")


def draw_analytics(surf, rect, exp: Experiment, detail=False):
    panel(surf, rect, "ANALYTICS" if not detail else "CHAMBER DETAIL", tint=(13, 27, 33))
    x = rect.x + 16
    y = rect.y + 56
    draw_text(surf, exp.name.upper(), FONT, WHITE, (x, y))
    y += 28
    draw_text(surf, f"STATUS: {exp.state}", FONT, CYAN if exp.state == "Stable" else AMBER if "Hybrid" in exp.state else RED, (x, y))
    y += 36
    metrics = [
        ("Vitality", exp.vitality, MINT),
        ("Biomass", exp.biomass, TEAL),
        ("Pollen", exp.pollen, AMBER),
        ("Toxic Vapor", exp.toxin, RED),
        ("Mutation Rate", exp.mutation, VIOLET),
        ("Breakthrough", exp.breakthrough, CYAN),
    ]
    if detail:
        metrics += [("Humidity", exp.humidity, ICE), ("Nutrients", exp.nutrients, LIME), ("Stability", exp.stability, MINT)]
    for label, val, color in metrics:
        draw_bar(surf, x, y, rect.w - 32, val, color, label)
        y += 44

    if detail:
        y += 6
        summary_box = pygame.Rect(x, y, rect.w - 32, 96)
        pygame.draw.rect(surf, PANEL_2, summary_box, border_radius=8)
        pygame.draw.rect(surf, BORDER, summary_box, 1, border_radius=8)
        draw_text(surf, "LAB NOTES", FONT, WHITE, (summary_box.x + 10, summary_box.y + 8))
        draw_text(surf, "- Adaptive canopy pressure detected", SMALL, MUTED, (summary_box.x + 10, summary_box.y + 38))
        draw_text(surf, "- Cross-chamber chemistry resonance rising", SMALL, MUTED, (summary_box.x + 10, summary_box.y + 58))
        draw_text(surf, "- Flower morphology diverging from seed line", SMALL, MUTED, (summary_box.x + 10, summary_box.y + 78))
        y += 112

    actions = ["Observe", "Isolate", "Crossbreed", "Sterilize", "Purge Air"]
    for idx, action in enumerate(actions):
        btn = pygame.Rect(x, y, rect.w - 32, 38)
        pygame.draw.rect(surf, PANEL_2 if idx < 4 else (28, 26, 28), btn, border_radius=8)
        pygame.draw.rect(surf, BORDER if idx < 4 else RED, btn, 1, border_radius=8)
        draw_text(surf, action.upper(), SMALL, WHITE, btn.center, "center")
        y += 44


def draw_left_roster(surf, rect, experiments, selected):
    panel(surf, rect, "CHAMBER ROSTER", tint=(11, 24, 30))
    y = rect.y + 52
    row_h = 84
    for i, exp in enumerate(experiments):
        row = pygame.Rect(rect.x + 10, y + i * row_h, rect.w - 20, 74)
        color = PANEL_3 if i == selected else PANEL_2
        pygame.draw.rect(surf, color, row, border_radius=8)
        pygame.draw.rect(surf, CYAN if i == selected else BORDER, row, 1, border_radius=8)
        pygame.draw.rect(surf, exp.hue, (row.x + 10, row.y + 12, 10, 48), border_radius=5)
        draw_text(surf, exp.code, FONT, WHITE, (row.x + 30, row.y + 10))
        draw_text(surf, exp.name, FONT, WHITE, (row.x + 96, row.y + 10))
        draw_text(surf, exp.state, SMALL, MUTED, (row.x + 30, row.y + 40))
        tag = pygame.Rect(row.right - 78, row.y + 14, 28, 24)
        pygame.draw.rect(surf, (16, 33, 38), tag, border_radius=4)
        pygame.draw.rect(surf, BORDER, tag, 1, border_radius=4)
        draw_text(surf, "PIP", SMALL, CYAN, tag.center, "center")
        tag2 = pygame.Rect(row.right - 44, row.y + 14, 28, 24)
        pygame.draw.rect(surf, (16, 33, 38), tag2, border_radius=4)
        pygame.draw.rect(surf, BORDER, tag2, 1, border_radius=4)
        draw_text(surf, "+", SMALL, WHITE, tag2.center, "center")
        pygame.draw.rect(surf, PANEL, (row.x + 30, row.bottom - 18, row.w - 60, 8), border_radius=4)
        fill_col = RED if exp.threat > 55 else AMBER if exp.threat > 30 else MINT
        pygame.draw.rect(surf, fill_col, (row.x + 30, row.bottom - 18, int((row.w - 60) * exp.vitality / 100), 8), border_radius=4)

    event_box = pygame.Rect(rect.x + 10, rect.bottom - 132, rect.w - 20, 112)
    pygame.draw.rect(surf, PANEL_2, event_box, border_radius=8)
    pygame.draw.rect(surf, BORDER, event_box, 1, border_radius=8)
    draw_text(surf, "RECENT EVENTS", FONT, WHITE, (event_box.x + 10, event_box.y + 8))
    draw_text(surf, experiments[selected].incident, SMALL, CYAN, (event_box.x + 10, event_box.y + 42))
    draw_text(surf, "Cross-sector biology pressure increasing.", SMALL, MUTED, (event_box.x + 10, event_box.y + 66))


def draw_topbar(surf, rect):
    gradient_fill(surf, rect, PANEL_2, PANEL_4, vertical=False)
    pygame.draw.line(surf, BORDER, (rect.x, rect.bottom - 1), (rect.right, rect.bottom - 1), 1)
    host = "HOLOVERSE HOSTED" if HOLOVERSE_EMBEDDED else "STANDALONE"
    txt = f"HELIX BIOGENICS // DAY 42 // {sim_speed}X SIM // POWER 97% // ALERTS {len(alert_log)} // {host}"
    draw_text(surf, txt, FONT, WHITE, rect.center, "center")


def draw_pip(surf, rect, exp: Experiment, mode="LIVE", active=False, floating=False):
    pygame.draw.rect(surf, SHADOW, rect.inflate(8, 8), border_radius=10)
    gradient_fill(surf, rect, PANEL, PANEL_2)
    pygame.draw.rect(surf, CYAN if active else BORDER, rect, 1, border_radius=10)
    header = pygame.Rect(rect.x, rect.y, rect.w, 24)
    gradient_fill(surf, header, PANEL_3, PANEL_2, vertical=False)
    draw_text(surf, f"{exp.code}  {exp.name.upper()}", MICRO, WHITE, (rect.x + 8, rect.y + 4))
    draw_text(surf, mode, MICRO, CYAN, (rect.right - 8, rect.y + 4), "topright")
    viewport = pygame.Rect(rect.x + 8, rect.y + 28, rect.w - 16, rect.h - 52)
    pygame.draw.rect(surf, (8, 14, 18), viewport, border_radius=6)
    draw_procedural_ecosystem(surf, viewport, exp, mode)
    draw_text(surf, exp.state.upper(), SMALL, CYAN if active else MUTED, (rect.x + 8, rect.bottom - 18))
    draw_text(surf, f"RISK {int(exp.threat)}%", SMALL, WHITE, (rect.right - 8, rect.bottom - 18), "topright")
    if floating:
        pygame.draw.circle(surf, AMBER if exp.threat > 35 else CYAN, (rect.right - 14, rect.y + 12), 4)


def draw_floating_pips(surf):
    for pw in pips:
        draw_pip(surf, pw.rect, experiments[pw.exp_index], pw.mode, active=(pw.exp_index == selected), floating=True)


def draw_overview(surf):
    w, h = surf.get_size()
    top_h = 52
    left_w = int(w * 0.19)
    right_w = int(w * 0.21)
    dock_h = 165
    margin = 16
    draw_topbar(surf, pygame.Rect(0, 0, w, top_h))
    left = pygame.Rect(margin, top_h + margin, left_w, h - top_h - dock_h - margin * 3)
    center = pygame.Rect(left.right + margin, top_h + margin, w - left_w - right_w - margin * 4, h - top_h - dock_h - margin * 3)
    right = pygame.Rect(center.right + margin, top_h + margin, right_w, h - top_h - dock_h - margin * 3)
    dock = pygame.Rect(margin, h - dock_h - margin, w - margin * 2, dock_h)

    draw_left_roster(surf, left, experiments, selected)
    draw_lab_canvas(surf, center, experiments[selected], view_mode)
    draw_analytics(surf, right, experiments[selected])

    panel(surf, dock, None, tint=(10, 22, 28))
    pip_w = 250
    for idx, exp_index in enumerate(pinned):
        pip_rect = pygame.Rect(dock.x + 12 + idx * (pip_w + 12), dock.y + 10, pip_w, dock.h - 22)
        draw_pip(surf, pip_rect, experiments[exp_index], "LIVE", active=(exp_index == selected))

    log_x = dock.x + 12 + len(pinned) * (pip_w + 12) + 8
    if SHOW_HUD and log_x < dock.right - 240:
        draw_text(surf, "LAB EVENT LOG", FONT, WHITE, (log_x, dock.y + 10))
        for i, line in enumerate(alert_log[:4]):
            c = CYAN if "scan" in line.lower() or "discovered" in line.lower() else AMBER if i == 1 else WHITE
            draw_text(surf, f"› {line}", SMALL, c, (log_x, dock.y + 46 + i * 28))
    tabs = ["LIVE", "BIO", "CHEM", "GENE", "TIME", "STRUCT"]
    tx = center.x + 18
    ty = center.bottom - 28
    for tab in tabs:
        color = CYAN if tab == view_mode else MUTED
        draw_text(surf, tab, FONT, color, (tx, ty))
        tx += 82

    draw_floating_pips(surf)
    if SHOW_HUD:
        draw_text(surf, "TAB mode · ENTER detail · E scan · Q biolog · H HUD · ESC pause/return", SMALL, MUTED, (center.x + 14, top_h + 6))


def draw_detail_view(surf):
    w, h = surf.get_size()
    top_h = 52
    margin = 16
    draw_topbar(surf, pygame.Rect(0, 0, w, top_h))
    exp = experiments[selected]
    header = pygame.Rect(margin, top_h + margin, w - margin * 2, 52)
    panel(surf, header, None, tint=PANEL_3)
    draw_text(surf, f"<- LAB    CHAMBER {exp.code} // {exp.name.upper()} // {exp.state.upper()} // DETAIL VIEW", FONT, WHITE, (header.x + 14, header.y + 15))

    main_rect = pygame.Rect(margin, header.bottom + margin, int(w * 0.66), h - header.bottom - margin * 2)
    side_rect = pygame.Rect(main_rect.right + margin, header.bottom + margin, w - main_rect.right - margin * 2, h - header.bottom - margin * 2)
    panel(surf, main_rect, "LIVE CHAMBER / ANALYSIS")
    viewport = main_rect.inflate(-20, -92)
    viewport.h -= 24
    gradient_fill(surf, viewport, (8, 15, 18), (12, 22, 28))
    draw_capsule_frame(surf, pygame.Rect(viewport.x + 60, viewport.y + 24, viewport.w - 120, viewport.h - 60))
    eco = pygame.Rect(viewport.x + 88, viewport.y + 56, viewport.w - 176, viewport.h - 126)
    draw_procedural_ecosystem(surf, eco, exp, view_mode)
    tab_y = main_rect.bottom - 48
    for i, tab in enumerate(["LIVE", "BIO", "CHEM", "GENE", "TIME", "STRUCT"]):
        tx = main_rect.x + 22 + i * 92
        draw_text(surf, tab, FONT, CYAN if tab == view_mode else MUTED, (tx, tab_y))

    draw_analytics(surf, side_rect, exp, detail=True)
    draw_floating_pips(surf)


def render_frame(save_path: Optional[str] = None):
    w, h = screen.get_size()
    gradient_fill(screen, pygame.Rect(0, 0, w, h), BG, BG_2)
    if screen_mode == "OVERVIEW":
        draw_overview(screen)
    else:
        draw_detail_view(screen)
    if SHOW_BIOLOG:
        draw_biolog_overlay()
    draw_holoverse_hud()
    if save_path:
        pygame.image.save(screen, save_path)


def handle_mouse(event):
    global selected
    if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
        mx, my = event.pos
        for pw in reversed(pips):
            if pw.rect.collidepoint(mx, my):
                pw.dragging = True
                pw.drag_off = (mx - pw.rect.x, my - pw.rect.y)
                pips.remove(pw)
                pips.append(pw)
                selected = pw.exp_index
                return
    elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
        for pw in pips:
            pw.dragging = False
    elif event.type == pygame.MOUSEMOTION:
        mx, my = event.pos
        for pw in pips:
            if pw.dragging:
                pw.rect.x = mx - pw.drag_off[0]
                pw.rect.y = my - pw.drag_off[1]



def draw_holoverse_hud():
    if not SHOW_HUD:
        return
    ribbon = pygame.Rect(18, HEIGHT - 42, WIDTH - 36, 28)
    shade = pygame.Surface((ribbon.w, ribbon.h), pygame.SRCALPHA)
    shade.fill((4, 12, 16, 190))
    screen.blit(shade, ribbon.topleft)
    pygame.draw.rect(screen, (41, 94, 104), ribbon, 1, border_radius=8)
    left = "ESC Pause/Return   H HUD   Q Biolog   E Scan   TAB Lens   ENTER Detail   1-5 Sim Speed"
    draw_text(screen, left, SMALL, CYAN, (ribbon.x + 12, ribbon.y + 6))
    right = f"Canvas {WIDTH}x{HEIGHT} · scans {len(SESSION_SCANS)}"
    draw_text(screen, right, SMALL, MUTED, (ribbon.right - 12, ribbon.y + 6), "topright")
    if ACTION_MESSAGE and pygame.time.get_ticks() < ACTION_MESSAGE_UNTIL:
        badge = pygame.Rect(WIDTH // 2 - 280, 70, 560, 44)
        pulse = 0.5 + 0.5 * math.sin(pygame.time.get_ticks() * 0.012)
        pygame.draw.rect(screen, (9, 26, 29), badge, border_radius=12)
        pygame.draw.rect(screen, tint_mix(CYAN, WHITE, pulse * 0.25), badge, 2, border_radius=12)
        draw_text(screen, ACTION_MESSAGE, FONT, WHITE, badge.center, "center")


def draw_biolog_overlay():
    shade = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    shade.fill((0, 0, 0, 105))
    screen.blit(shade, (0, 0))
    panel_rect = pygame.Rect(WIDTH - 610, 78, 570, HEIGHT - 156)
    pygame.draw.rect(screen, (6, 17, 22), panel_rect, border_radius=16)
    pygame.draw.rect(screen, CYAN, panel_rect, 2, border_radius=16)
    draw_text(screen, "HELIX BIOLOG", TITLE, WHITE, (panel_rect.x + 24, panel_rect.y + 22))
    draw_text(screen, "Q close · E record selected specimen scan", SMALL, MUTED, (panel_rect.right - 24, panel_rect.y + 32), "topright")
    exp = experiments[selected]
    summary = pygame.Rect(panel_rect.x + 24, panel_rect.y + 78, panel_rect.w - 48, 126)
    pygame.draw.rect(screen, PANEL_2, summary, border_radius=10)
    pygame.draw.rect(screen, BORDER, summary, 1, border_radius=10)
    draw_text(screen, f"SELECTED: {exp.code} // {exp.name.upper()}", FONT, CYAN, (summary.x + 16, summary.y + 14))
    draw_text(screen, f"STATE {exp.state} · VITALITY {int(exp.vitality)}% · MUTATION {int(exp.mutation)}% · THREAT {int(exp.threat)}%", SMALL, WHITE, (summary.x + 16, summary.y + 50))
    draw_text(screen, f"INCIDENT: {exp.incident}", SMALL, MUTED, (summary.x + 16, summary.y + 78))
    y = summary.bottom + 26
    draw_text(screen, "RECENT BIOLOG ENTRIES", FONT, WHITE, (panel_rect.x + 24, y))
    y += 36
    entries = load_biolog_entries(9)
    for entry in reversed(entries):
        kind = str(entry.get("kind", "NOTE"))[:10]
        stamp = str(entry.get("time", ""))[-8:] if entry.get("time") else "LAB"
        line = str(entry.get("text", ""))
        row = pygame.Rect(panel_rect.x + 24, y, panel_rect.w - 48, 58)
        pygame.draw.rect(screen, (8, 23, 29), row, border_radius=8)
        pygame.draw.rect(screen, (35, 74, 82), row, 1, border_radius=8)
        draw_text(screen, f"{kind} · {stamp}", SMALL, AMBER if kind == "SCAN" else CYAN, (row.x + 12, row.y + 8))
        wrapped = wrap_text(line, SMALL, row.w - 24)
        draw_text(screen, wrapped[0][:92], SMALL, TEXT, (row.x + 12, row.y + 30))
        y += 66
        if y > panel_rect.bottom - 60:
            break


def draw_holoverse_pause_overlay():
    shade = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    shade.fill((0, 0, 0, 165))
    screen.blit(shade, (0, 0))
    panel = pygame.Rect(WIDTH // 2 - 310, HEIGHT // 2 - 130, 620, 260)
    pygame.draw.rect(screen, (9, 20, 27), panel, border_radius=16)
    pygame.draw.rect(screen, CYAN, panel, 2, border_radius=16)
    draw_text(screen, "HELIX PAUSED", TITLE, WHITE, (panel.centerx, panel.y + 44), "center")
    draw_text(screen, "Real Helix mode is running inside the HoloVerse display.", FONT, TEXT, (panel.centerx, panel.y + 92), "center")
    draw_text(screen, "ENTER / ESC  Return to HoloVerse Core", FONT, CYAN, (panel.centerx, panel.y + 142), "center")
    draw_text(screen, "BACKSPACE / P  Resume Helix", FONT, MUTED, (panel.centerx, panel.y + 178), "center")
    draw_text(screen, "H toggles HUD · Q opens Biolog · E records scan", SMALL, MUTED, (panel.centerx, panel.y + 216), "center")

def main():
    global selected, view_mode, sim_speed, screen, screen_mode, _display, _scaled_frame, SHOW_HUD, SHOW_BIOLOG
    running = True
    pause_overlay = False
    modes = ["LIVE", "BIO", "CHEM", "GENE", "TIME", "STRUCT"]
    while running:
        if hv_runtime is not None:
            hv_runtime.poll_embedded_escape_hold()
        try:
            HELIX_AUDIO.update_music_rotation()
        except Exception:
            pass
        if holoverse_return_signal_requested():
            running = False
            break
        dt = clock.tick(FPS) / 1000.0 * sim_speed
        for e in experiments:
            e.update(dt)
        for event in pygame.event.get():
            if hv_runtime is not None and hv_runtime.pygame_embedded_escape_event(event):
                continue
            if event.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP, pygame.MOUSEMOTION):
                event = _map_mouse_event(event)
                if event is None:
                    continue
            if not pause_overlay and not SHOW_BIOLOG:
                handle_mouse(event)
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_h:
                    SHOW_HUD = not SHOW_HUD
                    set_action_message("HUD ON" if SHOW_HUD else "HUD OFF", 1200)
                    try: HELIX_AUDIO.play("hud_toggle", 0.8)
                    except Exception: pass
                    continue
                if event.key == pygame.K_q:
                    SHOW_BIOLOG = not SHOW_BIOLOG
                    set_action_message("BIOLOG OPEN" if SHOW_BIOLOG else "BIOLOG CLOSED", 1200)
                    try: HELIX_AUDIO.play("biolog_open" if SHOW_BIOLOG else "biolog_close", 0.9)
                    except Exception: pass
                    continue
                if event.key == pygame.K_e and not pause_overlay:
                    record_specimen_scan()
                    continue
                if pause_overlay:
                    if event.key in (pygame.K_ESCAPE, pygame.K_RETURN, pygame.K_KP_ENTER):
                        try: HELIX_AUDIO.play("return_core", 0.9)
                        except Exception: pass
                        running = False
                    elif event.key in (pygame.K_BACKSPACE, pygame.K_p):
                        try: HELIX_AUDIO.play("resume", 0.8)
                        except Exception: pass
                        pause_overlay = False
                    continue
                if SHOW_BIOLOG:
                    if event.key in (pygame.K_ESCAPE, pygame.K_BACKSPACE):
                        SHOW_BIOLOG = False
                    continue
                if event.key == pygame.K_ESCAPE:
                    if HOLOVERSE_EMBEDDED:
                        pause_overlay = True
                        try: HELIX_AUDIO.play("pause", 0.8)
                        except Exception: pass
                    elif screen_mode == "DETAIL":
                        screen_mode = "OVERVIEW"
                    else:
                        running = False
                elif event.key == pygame.K_RETURN:
                    screen_mode = "DETAIL" if screen_mode == "OVERVIEW" else "OVERVIEW"
                elif event.key == pygame.K_DOWN:
                    selected = (selected + 1) % len(experiments)
                    try: HELIX_AUDIO.play("select", 0.7)
                    except Exception: pass
                elif event.key == pygame.K_UP:
                    selected = (selected - 1) % len(experiments)
                    try: HELIX_AUDIO.play("select", 0.7)
                    except Exception: pass
                elif event.key == pygame.K_TAB:
                    view_mode = modes[(modes.index(view_mode) + 1) % len(modes)]
                elif event.key in (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4, pygame.K_5):
                    sim_speed = int(event.unicode)
            elif event.type == pygame.VIDEORESIZE:
                new_w = max(640, int(getattr(event, "w", event.size[0] if hasattr(event, "size") else WINDOW_WIDTH)))
                new_h = max(360, int(getattr(event, "h", event.size[1] if hasattr(event, "size") else WINDOW_HEIGHT)))
                _display = pygame.display.set_mode((new_w, new_h), pygame.RESIZABLE)
                _scaled_frame = None
        render_frame()
        if pause_overlay:
            draw_holoverse_pause_overlay()
        present_frame()
    pygame.quit()


if __name__ == "__main__":
    main()
