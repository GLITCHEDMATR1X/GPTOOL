import json
import math
import os
import random
import sys
import textwrap
import time
import traceback
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path

SELF_TEST = "--self-test" in sys.argv
RUNTIME_SMOKE = "--runtime-smoke" in sys.argv
HEADLESS_TEST = SELF_TEST or RUNTIME_SMOKE

from panda3d.core import loadPrcFileData

PRC = f"""
window-title Holo Campaign: Archive Mission
win-size 1600 900
show-frame-rate-meter 0
sync-video 1
framebuffer-multisample 1
multisamples 4
cursor-hidden 0
textures-power-2 up
texture-anisotropic-degree 8
notify-level-glgsg warning
notify-level-display warning
want-pstats 0
model-path ./assets
audio-library-name null
"""
if SELF_TEST:
    PRC += "\nwindow-type none\n"
elif RUNTIME_SMOKE:
    PRC += "\nwindow-type offscreen\nload-display p3tinydisplay\n"
loadPrcFileData("", PRC)

from direct.showbase.ShowBase import ShowBase
from direct.gui.DirectGui import DirectButton, DirectFrame, DirectLabel
from direct.task import Task
from direct.filter.CommonFilters import CommonFilters
from panda3d.core import (
    AmbientLight,
    AntialiasAttrib,
    BillboardEffect,
    CardMaker,
    ClockObject,
    CollisionNode,
    CollisionSphere,
    Fog,
    GeomNode,
    InputDevice,
    KeyboardButton,
    LColor,
    LineSegs,
    NodePath,
    Point2,
    Point3,
    TextNode,
    TexturePool,
    TransparencyAttrib,
    Vec2,
    Vec3,
    WindowProperties,
    Filename,
)

try:
    from PIL import Image, ImageDraw
except Exception:
    Image = None
    ImageDraw = None

VERSION = "0.1.4-pass97-etchline-combat-feedback"
GAME_NAME = "Holo Campaign: Archive Mission"
ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"
CONFIG_DIR = ASSETS / "config"
GENERATED_DIR = ASSETS / "generated"
LOG_DIR = ROOT / "logs"
PATCH_DIR = ROOT / "patch_notes"
CRASH_DIR = LOG_DIR / "crash_reports"
BLOTCH_TEXTURE = GENERATED_DIR / "ink_blotch.png"
CONFIG_PATH = CONFIG_DIR / "game_config.json"


def ensure_dirs():
    for p in [ASSETS, CONFIG_DIR, GENERATED_DIR, LOG_DIR, PATCH_DIR, CRASH_DIR]:
        p.mkdir(parents=True, exist_ok=True)


def install_crash_reporter():
    def _hook(exc_type, exc, tb):
        ensure_dirs()
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = CRASH_DIR / f"crash_{stamp}.log"
        with path.open("w", encoding="utf-8") as f:
            f.write(f"{GAME_NAME} {VERSION}\n")
            f.write(f"Timestamp: {datetime.now().isoformat()}\n\n")
            traceback.print_exception(exc_type, exc, tb, file=f)
        traceback.print_exception(exc_type, exc, tb)
    sys.excepthook = _hook


@dataclass
class GameConfig:
    day_length_seconds: float = 600.0
    transition_length_seconds: float = 120.0
    chunk_size: int = 64
    active_chunk_radius: int = 4
    enemy_chunk_radius: int = 3
    max_view_distance: float = 620.0
    fog_start_ratio: float = 0.52
    mouse_sensitivity: float = 0.11
    controller_look_sensitivity: float = 110.0
    walk_speed: float = 18.0
    sprint_speed: float = 30.0
    jump_speed: float = 8.2
    player_height: float = 1.75
    player_radius: float = 0.42
    gravity: float = 20.0
    line_thickness: float = 1.45
    line_jitter: float = 0.05
    default_health: int = 100
    max_enemies: int = 72
    max_tracers: int = 96
    max_blotches: int = 80
    max_chunks_loaded: int = 81
    patch_notes_on_launch: bool = False
    enemy_retire_distance: float = 360.0
    effect_retire_distance: float = 420.0
    invert_background: bool = True
    music_volume: float = 0.0
    show_help: bool = True
    world_seed: int = 74219
    signal_fragments_required: int = 4
    signal_recovery_radius: float = 5.25
    extraction_radius: float = 7.0
    objective_score_per_fragment: int = 175
    objective_completion_bonus: int = 800
    objective_wave_size: int = 5
    objective_pulse_budget: int = 18
    objective_beacon_height: float = 14.0
    extraction_beacon_height: float = 22.0
    max_combat_effects: int = 28
    enemy_kill_score: int = 25
    enemy_spawn_warning_seconds: float = 0.55
    enemy_contact_damage: int = 10


DEFAULT_CONFIG = GameConfig()


def load_or_create_config() -> GameConfig:
    ensure_dirs()
    if CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            merged = asdict(DEFAULT_CONFIG)
            merged.update({k: v for k, v in data.items() if k in merged})
            cfg = GameConfig(**merged)
        except Exception:
            cfg = DEFAULT_CONFIG
    else:
        cfg = DEFAULT_CONFIG
    CONFIG_PATH.write_text(json.dumps(asdict(cfg), indent=2), encoding="utf-8")
    return cfg


def write_patch_notes(version: str):
    ensure_dirs()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    note = textwrap.dedent(
        f"""
        {GAME_NAME}
        Version: {version}
        Generated: {datetime.now().isoformat()}

        Patch Notes
        - Added a first-person monochrome line-art cyber-noir shooter foundation.
        - Procedural far-distance city chunk generation with fade fog and full collision boxes.
        - Ten-minute day/night inversion cycle with long dawn and dusk transitions.
        - Endless procedural weapon cycling on TAB.
        - Scary intact line-render enemies with chase behavior and ink-blood drips.
        - Minimal professional HUD, ESC settings panel, H HUD toggle, F10 workstation.
        - Built-in asset/config folders, patch notes generation, and crash logs.
        - Self-test path for offscreen validation.
        - Pass 27: explicit entity/effect roots, launch-safe patch notes, and runtime budget smoke proof.
        """
    ).strip()
    (PATCH_DIR / f"patch_{stamp}.txt").write_text(note + "\n", encoding="utf-8")


def generate_blotch_texture_file():
    ensure_dirs()
    if BLOTCH_TEXTURE.exists() or Image is None:
        return
    img = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx = cy = 128
    rng = random.Random(771)
    for _ in range(56):
        rx = rng.randint(16, 64)
        ry = rng.randint(12, 58)
        ox = rng.randint(-56, 56)
        oy = rng.randint(-44, 64)
        alpha = rng.randint(18, 70)
        draw.ellipse((cx + ox - rx, cy + oy - ry, cx + ox + rx, cy + oy + ry), fill=(255, 255, 255, alpha))
    for _ in range(12):
        x = cx + rng.randint(-50, 50)
        y = cy + rng.randint(10, 50)
        w = rng.randint(8, 18)
        h = rng.randint(38, 92)
        draw.rounded_rectangle((x - w, y, x + w, y + h), radius=w // 2, fill=(255, 255, 255, rng.randint(22, 88)))
    img.save(BLOTCH_TEXTURE)


def run_lightweight_self_test():
    ensure_dirs()
    install_crash_reporter()
    cfg = load_or_create_config()
    write_patch_notes(VERSION)
    generate_blotch_texture_file()
    report = {
        "game": GAME_NAME,
        "version": VERSION,
        "config_loaded": True,
        "day_length_seconds": cfg.day_length_seconds,
        "chunk_size": cfg.chunk_size,
        "line_thickness": cfg.line_thickness,
        "blotch_texture_exists": BLOTCH_TEXTURE.exists(),
        "max_chunks_loaded": cfg.max_chunks_loaded,
        "patch_notes_on_launch": cfg.patch_notes_on_launch,
        "patch_notes_dir": str(PATCH_DIR),
        "logs_dir": str(LOG_DIR),
    }
    (LOG_DIR / "self_test_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))



@dataclass
class Weapon:
    index: int
    name: str
    damage: float
    fire_interval: float
    spread: float
    range: float
    projectiles: int
    tracer_time: float
    recoil: float


@dataclass
class BoxBounds:
    min_v: Vec3
    max_v: Vec3
    normal_hint: Vec3


class SignalNode:
    """A lightweight Etch-Line objective marker made from live line geometry."""

    def __init__(self, app, index: int, pos: Vec3, label: str, kind: str = "fragment"):
        self.app = app
        self.index = int(index)
        self.pos = Vec3(pos)
        self.label = str(label)
        self.kind = str(kind or "fragment")
        self.completed = False
        self.active = self.kind != "extraction"
        self.age = 0.0
        self.radius = float(getattr(app.game_cfg, "extraction_radius", 7.0) if self.kind == "extraction" else getattr(app.game_cfg, "signal_recovery_radius", 5.25))
        parent = getattr(app, "mission_root", None) or getattr(app, "effect_root", app.render)
        self.root = parent.attachNewNode(f"etchline-signal-{self.kind}-{self.index}")
        self.root.setPos(self.pos)
        self.root.setTransparency(TransparencyAttrib.MAlpha)
        self.visual = self.root.attachNewNode(self._build_visual())
        self.visual.setAntialias(AntialiasAttrib.MLine)
        self.visual.setTransparency(TransparencyAttrib.MAlpha)
        self.beacon = self.root.attachNewNode(self._build_beacon_visual())
        self.beacon.setAntialias(AntialiasAttrib.MLine)
        self.beacon.setTransparency(TransparencyAttrib.MAlpha)
        self.label_np = self._build_world_label()
        if not self.active:
            self.root.hide()

    def _draw_ring_xy(self, segs: LineSegs, radius: float, z: float, segments: int = 28) -> None:
        first = None
        last = None
        for i in range(segments):
            ang = math.tau * i / max(3, segments)
            p = Vec3(math.cos(ang) * radius, math.sin(ang) * radius, z)
            if first is None:
                first = p
            if last is not None:
                segs.moveTo(last)
                segs.drawTo(p)
            last = p
        if first is not None and last is not None:
            segs.moveTo(last)
            segs.drawTo(first)

    def _build_visual(self):
        segs = LineSegs(f"etchline-signal-lines-{self.index}")
        thickness = max(1.0, float(getattr(self.app.game_cfg, "line_thickness", 1.45)) * (1.35 if self.kind == "extraction" else 1.1))
        segs.setThickness(thickness)
        segs.setColor(*self.app.current_line_color(alpha=0.96))
        height = 9.5 if self.kind == "extraction" else 6.25
        base = 1.45 if self.kind == "extraction" else 1.0
        top = Vec3(0, 0, height)
        corners = [Vec3(base, 0, 0.15), Vec3(0, base, 0.15), Vec3(-base, 0, 0.15), Vec3(0, -base, 0.15)]
        for corner in corners:
            segs.moveTo(corner)
            segs.drawTo(top)
        for a, b in zip(corners, corners[1:] + corners[:1]):
            segs.moveTo(a)
            segs.drawTo(b)
        for z, r in ((1.2, base * 1.4), (3.1, base * 1.9), (height - 1.15, base * 1.2)):
            self._draw_ring_xy(segs, r, z, 28)
        # Inner glyph / route signature.
        glyph_z = height * 0.55
        glyph = [Vec3(-1.0, 0, glyph_z), Vec3(0, 0, glyph_z + 1.25), Vec3(1.0, 0, glyph_z), Vec3(0, 0, glyph_z - 1.25)]
        for a, b in zip(glyph, glyph[1:] + glyph[:1]):
            segs.moveTo(a)
            segs.drawTo(b)
        if self.kind == "extraction":
            for arm in range(8):
                ang = math.tau * arm / 8
                inner = Vec3(math.cos(ang) * 2.0, math.sin(ang) * 2.0, 2.4)
                outer = Vec3(math.cos(ang) * 5.4, math.sin(ang) * 5.4, 2.4)
                segs.moveTo(inner)
                segs.drawTo(outer)
        return segs.create()

    def _build_beacon_visual(self):
        segs = LineSegs(f"etchline-signal-beacon-{self.index}")
        segs.setThickness(max(1.8, float(getattr(self.app.game_cfg, "line_thickness", 1.45)) * (1.85 if self.kind == "extraction" else 1.45)))
        segs.setColor(*self.app.signal_accent_color(alpha=0.86 if self.kind == "extraction" else 0.72))
        height = float(getattr(self.app.game_cfg, "extraction_beacon_height", 22.0) if self.kind == "extraction" else getattr(self.app.game_cfg, "objective_beacon_height", 14.0))
        core_radius = 0.34 if self.kind != "extraction" else 0.55
        for arm in range(4):
            ang = math.tau * arm / 4 + math.pi * 0.25
            offset = Vec3(math.cos(ang) * core_radius, math.sin(ang) * core_radius, 0)
            segs.moveTo(offset.x, offset.y, 0.15)
            segs.drawTo(offset.x * 0.25, offset.y * 0.25, height)
        for z, radius, segments in ((0.08, self.radius, 48), (height * 0.44, 1.45 if self.kind != "extraction" else 2.3, 32), (height * 0.82, 0.72 if self.kind != "extraction" else 1.3, 28)):
            first = last = None
            for i in range(segments):
                ang = math.tau * i / max(3, segments)
                p = Vec3(math.cos(ang) * radius, math.sin(ang) * radius, z)
                if first is None:
                    first = p
                if last is not None:
                    segs.moveTo(last)
                    segs.drawTo(p)
                last = p
            if first is not None and last is not None:
                segs.moveTo(last)
                segs.drawTo(first)
        if self.kind == "extraction":
            for side in (-1, 1):
                x = side * 2.2
                segs.moveTo(x, -1.6, 0.2)
                segs.drawTo(x, -1.6, height * 0.68)
                segs.drawTo(x * 0.45, 0.0, height)
        return segs.create()

    def _build_world_label(self):
        try:
            text = TextNode(f"etchline-signal-label-{self.index}")
            short = "RETURN" if self.kind == "extraction" else f"F{self.index}"
            text.setText(short)
            text.setAlign(TextNode.ACenter)
            text.setTextColor(*self.app.signal_accent_color(alpha=0.88))
            text.setShadow(0.045, 0.045)
            text.setShadowColor(0, 0, 0, 0.75)
            np = self.root.attachNewNode(text)
            height = float(getattr(self.app.game_cfg, "extraction_beacon_height", 22.0) if self.kind == "extraction" else getattr(self.app.game_cfg, "objective_beacon_height", 14.0))
            np.setPos(0, 0, height + 1.2)
            np.setScale(1.05 if self.kind == "extraction" else 0.78)
            np.setBillboardAxis()
            np.setTransparency(TransparencyAttrib.MAlpha)
            return np
        except Exception:
            return None

    def set_active(self, active: bool) -> None:
        self.active = bool(active)
        try:
            self.root.show() if self.active else self.root.hide()
        except Exception:
            pass

    def mark_completed(self) -> None:
        self.completed = True
        self.active = False if self.kind == "fragment" else True
        try:
            if self.kind == "fragment" and getattr(self, "label_np", None) is not None:
                self.label_np.hide()
        except Exception:
            pass

    def dispose(self) -> None:
        try:
            if getattr(self, "root", None) is not None and not self.root.isEmpty():
                self.root.removeNode()
        except Exception:
            pass

    def update(self, dt: float, player_pos: Vec3) -> None:
        if not self.active and not self.completed:
            return
        self.age += max(0.0, float(dt or 0.0))
        pulse = 0.5 + 0.5 * math.sin(self.age * (4.2 if self.kind == "extraction" else 3.4) + self.index)
        base_scale = 1.0 + pulse * (0.11 if self.kind == "extraction" else 0.07)
        try:
            self.root.setScale(base_scale)
        except Exception:
            pass
        alpha = 0.28 if self.completed and self.kind == "fragment" else (0.72 + pulse * 0.24)
        try:
            self.visual.setColorScale(*self.app.current_line_color(alpha=alpha))
            beacon_alpha = 0.18 if self.completed and self.kind == "fragment" else (0.56 + pulse * (0.34 if self.kind == "extraction" else 0.24))
            self.beacon.setColorScale(*self.app.signal_accent_color(alpha=beacon_alpha))
            if getattr(self, "label_np", None) is not None:
                self.label_np.setColorScale(*self.app.signal_accent_color(alpha=0.65 + pulse * 0.28))
        except Exception:
            pass

    def player_inside(self, player_pos: Vec3) -> bool:
        delta = Vec3(player_pos.x - self.pos.x, player_pos.y - self.pos.y, 0)
        return delta.lengthSquared() <= self.radius * self.radius

    def ray_hit(self, origin: Vec3, direction: Vec3, max_range: float) -> tuple[float, Vec3] | None:
        if not self.active or self.completed:
            return None
        center = self.pos + Vec3(0, 0, 3.0 if self.kind != "extraction" else 4.5)
        to_center = center - origin
        t = to_center.dot(direction)
        if t < 0.1 or t > max_range:
            return None
        closest = origin + direction * t
        radius = 2.6 if self.kind == "extraction" else 2.1
        if (closest - center).lengthSquared() <= radius * radius:
            return t, center
        return None


class SignalPulseEffect:
    """Bounded objective feedback pulse for recovered fragments and return routes."""

    def __init__(self, app, pos: Vec3, label: str = "signal", radius: float = 1.0, life: float = 1.25, height: float = 0.10):
        self.app = app
        self.pos = Vec3(pos)
        self.label = str(label or "signal")
        self.base_radius = max(0.5, float(radius or 1.0))
        self.life = max(0.2, float(life or 1.25))
        self.height = float(height or 0.10)
        self.age = 0.0
        parent = getattr(app, "effect_root", app.render)
        self.root = parent.attachNewNode(f"etchline-signal-pulse-{self.label}")
        self.root.setPos(self.pos)
        self.root.setTransparency(TransparencyAttrib.MAlpha)
        self.visual = self.root.attachNewNode(self._build_visual())
        self.visual.setTransparency(TransparencyAttrib.MAlpha)
        self.visual.setAntialias(AntialiasAttrib.MLine)

    def _build_visual(self):
        segs = LineSegs(f"etchline-pulse-lines-{self.label}")
        segs.setThickness(max(1.4, float(getattr(self.app.game_cfg, "line_thickness", 1.45)) * 1.35))
        segs.setColor(*self.app.signal_accent_color(alpha=0.78))
        for z, radius_mul, segments in ((self.height, 1.0, 36), (self.height + 0.08, 1.45, 44), (self.height + 0.16, 1.9, 52)):
            first = last = None
            radius = self.base_radius * radius_mul
            for i in range(segments):
                ang = math.tau * i / max(3, segments)
                p = Vec3(math.cos(ang) * radius, math.sin(ang) * radius, z)
                if first is None:
                    first = p
                if last is not None:
                    segs.moveTo(last)
                    segs.drawTo(p)
                last = p
            if first is not None and last is not None:
                segs.moveTo(last)
                segs.drawTo(first)
        for arm in range(8):
            ang = math.tau * arm / 8
            inner = Vec3(math.cos(ang) * self.base_radius * 0.35, math.sin(ang) * self.base_radius * 0.35, self.height + 0.2)
            outer = Vec3(math.cos(ang) * self.base_radius * 2.25, math.sin(ang) * self.base_radius * 2.25, self.height + 0.2)
            segs.moveTo(inner)
            segs.drawTo(outer)
        return segs.create()

    def dispose(self) -> None:
        try:
            if getattr(self, "root", None) is not None and not self.root.isEmpty():
                self.root.removeNode()
        except Exception:
            pass

    def update(self, dt: float) -> bool:
        self.age += max(0.0, float(dt or 0.0))
        t = min(1.0, self.age / self.life)
        ease = t * t * (3.0 - 2.0 * t)
        try:
            self.root.setScale(1.0 + ease * 2.3)
            self.root.setZ(self.pos.z + ease * 1.7)
            self.visual.setColorScale(*self.app.signal_accent_color(alpha=max(0.0, 0.78 * (1.0 - t))))
        except Exception:
            return False
        if self.age >= self.life:
            self.dispose()
            return False
        return True


class CombatFeedbackEffect:
    """Short-lived combat pulse used for spawn warnings, hits, and enemy deaths."""

    def __init__(self, app, pos: Vec3, label: str = "hit", radius: float = 1.0, life: float = 0.55, height: float = 0.24, warning: bool = True):
        self.app = app
        self.pos = Vec3(pos)
        self.label = str(label or "hit")
        self.base_radius = max(0.25, float(radius or 1.0))
        self.life = max(0.12, float(life or 0.55))
        self.height = float(height or 0.24)
        self.warning = bool(warning)
        self.age = 0.0
        parent = getattr(app, "effect_root", app.render)
        self.root = parent.attachNewNode(f"etchline-combat-feedback-{self.label}")
        self.root.setPos(self.pos)
        self.root.setTransparency(TransparencyAttrib.MAlpha)
        self.visual = self.root.attachNewNode(self._build_visual())
        self.visual.setTransparency(TransparencyAttrib.MAlpha)
        self.visual.setAntialias(AntialiasAttrib.MLine)

    def _color(self, alpha: float = 1.0):
        if self.warning:
            return self.app.warning_accent_color(alpha=alpha)
        return self.app.signal_accent_color(alpha=alpha)

    def _build_visual(self):
        segs = LineSegs(f"etchline-combat-lines-{self.label}")
        segs.setThickness(max(1.2, float(getattr(self.app.game_cfg, "line_thickness", 1.45)) * 1.55))
        segs.setColor(*self._color(alpha=0.90))
        rings = 2 if self.label != "death" else 3
        for r_i in range(rings):
            radius = self.base_radius * (1.0 + r_i * 0.48)
            z = self.height + r_i * 0.08
            first = last = None
            segments = 26 + r_i * 8
            for i in range(segments):
                ang = math.tau * i / max(3, segments)
                p = Vec3(math.cos(ang) * radius, math.sin(ang) * radius, z)
                if first is None:
                    first = p
                if last is not None:
                    segs.moveTo(last)
                    segs.drawTo(p)
                last = p
            if first is not None and last is not None:
                segs.moveTo(last)
                segs.drawTo(first)
        arm_count = 6 if self.label == "spawn" else 8
        for arm in range(arm_count):
            ang = math.tau * arm / max(1, arm_count)
            inner = Vec3(math.cos(ang) * self.base_radius * 0.28, math.sin(ang) * self.base_radius * 0.28, self.height + 0.18)
            outer = Vec3(math.cos(ang) * self.base_radius * (1.9 if self.label == "death" else 1.45), math.sin(ang) * self.base_radius * (1.9 if self.label == "death" else 1.45), self.height + 0.18)
            segs.moveTo(inner)
            segs.drawTo(outer)
        if self.label == "spawn":
            for side in (-1, 1):
                segs.moveTo(side * self.base_radius, 0, 0.05)
                segs.drawTo(0, 0, self.height + self.base_radius * 1.8)
        elif self.label == "hit":
            segs.moveTo(-self.base_radius * 0.75, 0, self.height + self.base_radius * 0.75)
            segs.drawTo(self.base_radius * 0.75, 0, self.height - self.base_radius * 0.15)
            segs.moveTo(self.base_radius * 0.75, 0, self.height + self.base_radius * 0.75)
            segs.drawTo(-self.base_radius * 0.75, 0, self.height - self.base_radius * 0.15)
        return segs.create()

    def dispose(self) -> None:
        try:
            if getattr(self, "root", None) is not None and not self.root.isEmpty():
                self.root.removeNode()
        except Exception:
            pass

    def update(self, dt: float) -> bool:
        self.age += max(0.0, float(dt or 0.0))
        t = min(1.0, self.age / self.life)
        ease = t * t * (3.0 - 2.0 * t)
        try:
            self.root.setScale(0.72 + ease * (2.0 if self.label == "death" else 1.35))
            self.root.setZ(self.pos.z + ease * (1.3 if self.label == "death" else 0.55))
            self.visual.setColorScale(*self._color(alpha=max(0.0, 0.92 * (1.0 - t))))
        except Exception:
            return False
        if self.age >= self.life:
            self.dispose()
            return False
        return True


class TracerEffect:
    def __init__(self, app, start: Vec3, end: Vec3, ttl: float = 0.05):
        self.app = app
        self.ttl = ttl
        self.age = 0.0
        segs = LineSegs("tracer")
        segs.setThickness(max(1.0, app.game_cfg.line_thickness * 0.9))
        c = app.current_line_color(alpha=1.0)
        segs.setColor(c)
        segs.moveTo(start)
        segs.drawTo(end)
        parent = getattr(app, "effect_root", app.render)
        self.np = parent.attachNewNode(segs.create())
        self.np.setAntialias(AntialiasAttrib.MLine)
        self.np.setTransparency(TransparencyAttrib.MAlpha)
        self.np.setBin("fixed", 10)

    def dispose(self) -> None:
        try:
            if getattr(self, "np", None) is not None and not self.np.isEmpty():
                self.np.removeNode()
        except Exception:
            pass

    def update(self, dt: float):
        self.age += dt
        t = max(0.0, 1.0 - self.age / max(0.001, self.ttl))
        try:
            self.np.setColorScale(1, 1, 1, t)
        except Exception:
            return False
        if self.age >= self.ttl:
            self.dispose()
            return False
        return True


class InkBlotch:
    def __init__(self, app, pos: Vec3, normal: Vec3):
        self.app = app
        self.age = 0.0
        self.life = 6.0 + random.random() * 6.0
        parent = getattr(app, "effect_root", app.render)
        self.root = parent.attachNewNode("ink-blotch")
        self.root.setPos(pos + normal * 0.03)
        self.root.setTransparency(TransparencyAttrib.MAlpha)

        if abs(normal.z) < 0.75:
            h = math.degrees(math.atan2(normal.x, -normal.y))
            p = -math.degrees(math.asin(max(-1.0, min(1.0, normal.z))))
            self.root.setHpr(h, p, 0)
        else:
            self.root.lookAt(pos + normal)

        card = CardMaker("blotch-card")
        size = 0.45 + random.random() * 0.65
        card.setFrame(-size, size, -size, size)
        self.base = self.root.attachNewNode(card.generate())
        texture = getattr(app, "_blotch_texture", None)
        if texture is not None:
            self.base.setTexture(texture)
        self.base.setBillboardAxis()
        self.base.setTransparency(TransparencyAttrib.MAlpha)
        self.base.setDepthWrite(False)

        self.drips = []
        for _ in range(random.randint(3, 6)):
            drip = LineSegs("drip")
            drip.setThickness(max(1.0, app.game_cfg.line_thickness * 0.65))
            drip.setColor(app.current_line_color(alpha=0.95))
            drip.moveTo(0, 0, 0)
            initial = Vec3(random.uniform(-0.03, 0.03), random.uniform(-0.03, 0.03), -random.uniform(0.05, 0.16))
            drip.drawTo(initial)
            np = self.root.attachNewNode(drip.create())
            np.setTransparency(TransparencyAttrib.MAlpha)
            tangent = Vec3(random.uniform(-1, 1), random.uniform(-1, 1), random.uniform(-0.4, 0.2))
            if tangent.lengthSquared() < 0.001:
                tangent = Vec3(1, 0, -0.3)
            tangent.normalize()
            tangent -= normal * tangent.dot(normal)
            if tangent.lengthSquared() < 0.001:
                tangent = Vec3(1, 0, 0)
            tangent.normalize()
            tangent += Vec3(0, 0, -0.25)
            tangent.normalize()
            self.drips.append({"np": np, "dir": tangent, "len": initial.length()})

    def update(self, dt: float):
        self.age += dt
        scale = 0.75 + min(1.0, self.age * 1.1)
        self.base.setScale(scale)
        fade = 1.0 if self.age < self.life * 0.7 else max(0.0, 1.0 - (self.age - self.life * 0.7) / (self.life * 0.3))
        tint = self.app.current_line_color(alpha=0.9 * fade)
        self.base.setColor(tint)
        for drip_info in self.drips:
            drip_info["len"] += dt * random.uniform(0.08, 0.25)
            segs = LineSegs("drip-update")
            segs.setThickness(max(1.0, self.app.game_cfg.line_thickness * 0.65))
            segs.setColor(self.app.current_line_color(alpha=0.92 * fade))
            segs.moveTo(0, 0, 0)
            segs.drawTo(drip_info["dir"] * drip_info["len"])
            new_np = self.root.attachNewNode(segs.create())
            new_np.setTransparency(TransparencyAttrib.MAlpha)
            drip_info["np"].removeNode()
            drip_info["np"] = new_np
        if self.age >= self.life:
            self.dispose()
            return False
        return True

    def dispose(self) -> None:
        try:
            if getattr(self, "root", None) is not None and not self.root.isEmpty():
                self.root.removeNode()
        except Exception:
            pass
        self.drips = []


class Enemy:
    def __init__(self, app, pos: Vec3, seed: int, chunk_key: tuple[int, int] | None = None):
        self.app = app
        parent = getattr(app, "entity_root", app.render)
        self.root = parent.attachNewNode("enemy")
        self.root.setPos(pos)
        self.seed = seed
        self.chunk_key = chunk_key
        self.rng = random.Random(seed)
        self.speed = 3.7 + self.rng.random() * 2.0
        self.health = 55 + self.rng.randint(0, 45)
        self.max_health = float(self.health)
        self.radius = 0.6
        self.height = 2.8 + self.rng.random() * 1.1
        self.phase = self.rng.random() * math.tau
        self.wander_timer = self.rng.random() * 2.0
        self.direction = Vec3(self.rng.uniform(-1, 1), self.rng.uniform(-1, 1), 0)
        if self.direction.lengthSquared() < 0.1:
            self.direction = Vec3(1, 0, 0)
        self.direction.normalize()
        self.dead = False
        self.spawn_age = 0.0
        self.spawn_delay = max(0.0, float(getattr(app.game_cfg, "enemy_spawn_warning_seconds", 0.55)))
        self.hit_flash = 0.0
        self.stagger_timer = 0.0
        self.contact_cooldown = 0.0
        self.build_model()

    def build_model(self):
        self.body = self.root.attachNewNode("body")
        color = self.app.current_line_color(alpha=0.98)
        self.body.setColor(color)
        self.body.setTransparency(TransparencyAttrib.MAlpha)
        self.body.setAntialias(AntialiasAttrib.MLine)

        torso = self.make_box_wire((0, 0, self.height * 0.56), (0.55, 0.4, 0.85))
        head = self.make_ring((0, 0, self.height * 0.88), 0.24, 0.38, 10)
        jaw = self.make_box_wire((0, 0.02, self.height * 0.78), (0.42, 0.25, 0.22))
        rib_l = self.make_box_wire((-0.36, 0.02, self.height * 0.56), (0.16, 0.18, 0.56))
        rib_r = self.make_box_wire((0.36, 0.02, self.height * 0.56), (0.16, 0.18, 0.56))
        spine = self.make_line([(0, 0, self.height * 0.18), (0, 0, self.height * 0.9)])
        arm_l = self.make_line([(-0.32, 0, self.height * 0.68), (-0.88, 0.04, self.height * 0.38), (-1.06, 0.06, self.height * 0.1)])
        arm_r = self.make_line([(0.32, 0, self.height * 0.68), (0.88, 0.04, self.height * 0.38), (1.06, 0.06, self.height * 0.1)])
        leg_l = self.make_line([(-0.12, 0, self.height * 0.18), (-0.22, 0.02, self.height * 0.02), (-0.34, 0.1, -0.05)])
        leg_r = self.make_line([(0.12, 0, self.height * 0.18), (0.22, 0.02, self.height * 0.02), (0.34, 0.1, -0.05)])
        claw_l = self.make_line([(-1.06, 0.06, self.height * 0.1), (-1.22, -0.08, -0.08), (-1.14, 0.1, -0.02)])
        claw_r = self.make_line([(1.06, 0.06, self.height * 0.1), (1.22, -0.08, -0.08), (1.14, 0.1, -0.02)])
        for np in [torso, head, jaw, rib_l, rib_r, spine, arm_l, arm_r, leg_l, leg_r, claw_l, claw_r]:
            np.reparentTo(self.body)
        cnode = CollisionNode("enemy-hit")
        cnode.addSolid(CollisionSphere(0, 0, self.height * 0.55, 0.9))
        self.body.attachNewNode(cnode)

    def make_line(self, pts):
        segs = LineSegs("enemy-line")
        segs.setThickness(max(1.0, self.app.game_cfg.line_thickness * 0.95))
        segs.setColor(self.app.current_line_color(alpha=0.97))
        first = True
        for p in pts:
            if first:
                segs.moveTo(*p)
                first = False
            else:
                segs.drawTo(*p)
        np = NodePath(segs.create())
        np.setAntialias(AntialiasAttrib.MLine)
        return np

    def make_ring(self, pos, inner_r, outer_r, segments):
        segs = LineSegs("enemy-ring")
        segs.setThickness(max(1.0, self.app.game_cfg.line_thickness * 0.9))
        segs.setColor(self.app.current_line_color(alpha=0.95))
        for radius in [inner_r, outer_r]:
            for i in range(segments + 1):
                angle = math.tau * i / segments
                x = pos[0] + math.cos(angle) * radius
                y = pos[1]
                z = pos[2] + math.sin(angle) * radius
                if i == 0:
                    segs.moveTo(x, y, z)
                else:
                    segs.drawTo(x, y, z)
        np = NodePath(segs.create())
        np.setAntialias(AntialiasAttrib.MLine)
        return np

    def make_box_wire(self, pos, size):
        cx, cy, cz = pos
        sx, sy, sz = size
        x0, x1 = cx - sx * 0.5, cx + sx * 0.5
        y0, y1 = cy - sy * 0.5, cy + sy * 0.5
        z0, z1 = cz - sz * 0.5, cz + sz * 0.5
        edges = [
            ((x0, y0, z0), (x1, y0, z0)), ((x1, y0, z0), (x1, y1, z0)), ((x1, y1, z0), (x0, y1, z0)), ((x0, y1, z0), (x0, y0, z0)),
            ((x0, y0, z1), (x1, y0, z1)), ((x1, y0, z1), (x1, y1, z1)), ((x1, y1, z1), (x0, y1, z1)), ((x0, y1, z1), (x0, y0, z1)),
            ((x0, y0, z0), (x0, y0, z1)), ((x1, y0, z0), (x1, y0, z1)), ((x1, y1, z0), (x1, y1, z1)), ((x0, y1, z0), (x0, y1, z1)),
        ]
        segs = LineSegs("enemy-box")
        segs.setThickness(max(1.0, self.app.game_cfg.line_thickness * 0.9))
        segs.setColor(self.app.current_line_color(alpha=0.95))
        for a, b in edges:
            segs.moveTo(*a)
            segs.drawTo(*b)
        np = NodePath(segs.create())
        np.setAntialias(AntialiasAttrib.MLine)
        return np

    def hit(self, damage: float, point: Vec3, normal: Vec3):
        if self.dead:
            return
        self.health -= damage
        self.hit_flash = 0.22
        self.stagger_timer = max(self.stagger_timer, 0.18)
        try:
            self.app.add_combat_feedback(point, label="hit", radius=0.9, life=0.42, warning=True)
        except Exception:
            pass
        for _ in range(random.randint(2, 4)):
            self.app.blotches.append(InkBlotch(self.app, point + Vec3(random.uniform(-0.07, 0.07), random.uniform(-0.07, 0.07), random.uniform(-0.07, 0.07)), normal))
        if self.health <= 0:
            try:
                self.app.register_enemy_kill(self, point)
            except Exception:
                pass
            self.dispose()

    def dispose(self) -> None:
        self.dead = True
        try:
            if getattr(self, "root", None) is not None and not self.root.isEmpty():
                self.root.removeNode()
        except Exception:
            pass

    def update(self, dt: float, player_pos: Vec3):
        if self.dead:
            return False
        self.spawn_age += max(0.0, float(dt or 0.0))
        self.hit_flash = max(0.0, self.hit_flash - dt)
        self.stagger_timer = max(0.0, self.stagger_timer - dt)
        self.contact_cooldown = max(0.0, self.contact_cooldown - dt)
        if self.spawn_age < self.spawn_delay:
            t = self.spawn_age / max(0.001, self.spawn_delay)
            pulse = 0.5 + 0.5 * math.sin((self.spawn_age * 18.0) + self.phase)
            try:
                self.root.setScale(0.25 + 0.75 * t)
                self.body.setColor(*self.app.warning_accent_color(alpha=0.42 + pulse * 0.42))
                self.body.setP(math.sin(self.spawn_age * 20.0 + self.phase) * 3.0)
            except Exception:
                pass
            return True
        else:
            try:
                self.root.setScale(1.0)
            except Exception:
                pass
        to_player = player_pos - self.root.getPos()
        to_player.z = 0
        dist = to_player.length()
        if dist < 120.0 and dist > 0.001:
            to_player.normalize()
            desired = to_player
        else:
            self.wander_timer -= dt
            if self.wander_timer <= 0.0:
                self.wander_timer = 1.0 + self.rng.random() * 2.2
                self.direction = Vec3(self.rng.uniform(-1, 1), self.rng.uniform(-1, 1), 0)
                if self.direction.lengthSquared() < 0.05:
                    self.direction = Vec3(1, 0, 0)
                self.direction.normalize()
            desired = self.direction
        speed_mul = 0.25 if self.stagger_timer > 0.0 else 1.0
        step = desired * self.speed * speed_mul * dt
        candidate = self.root.getPos() + step
        candidate.z = 0
        if not self.app.point_hits_obstacle(candidate, radius=self.radius, height=self.height):
            self.root.setPos(candidate)
        else:
            self.direction *= -1
        if dist > 0.001:
            self.root.setH(math.degrees(math.atan2(-desired.x, desired.y)))
        swing = math.sin(self.app.elapsed * 6.0 + self.phase) * 12.0
        self.body.setP(swing * 0.15)
        self.body.setR(math.sin(self.app.elapsed * 3.0 + self.phase) * 2.0)
        if self.hit_flash > 0.0:
            pulse = self.hit_flash / 0.22
            tint = self.app.warning_accent_color(alpha=0.72 + pulse * 0.22)
        else:
            tint = self.app.current_line_color(alpha=0.98)
        self.body.setColor(tint)
        return True

    def bounds(self):
        pos = self.root.getPos()
        return BoxBounds(pos + Vec3(-0.9, -0.9, -0.1), pos + Vec3(0.9, 0.9, self.height + 0.2), Vec3(0, 0, 1))


class EtchlineGame(ShowBase):
    def __init__(self):
        ensure_dirs()
        install_crash_reporter()
        self.game_cfg = load_or_create_config()
        if bool(getattr(self.game_cfg, "patch_notes_on_launch", False)):
            write_patch_notes(VERSION)
        self.create_blotch_texture()
        super().__init__()
        self._shutting_down = False
        self._blotch_texture = self.loader.loadTexture(Filename.fromOsSpecific(os.fspath(BLOTCH_TEXTURE))) if BLOTCH_TEXTURE.exists() else None
        self.disableMouse()
        self.elapsed = 0.0
        self.day_phase = 0.0
        self.health = self.game_cfg.default_health
        self.vertical_speed = 0.0
        self.on_ground = True
        self.menu_open = False
        self.hud_visible = True
        self.workstation_visible = False
        self.help_visible = self.game_cfg.show_help
        self.fire_down = False
        self.fire_hold = False
        self.fire_cooldown = 0.0
        self.last_shot_time = 0.0
        self.current_weapon_seed = 0
        self.weapons = []
        self.current_weapon = None
        self.weapon_banner_time = 0.0
        self.tracers = []
        self.blotches = []
        self.combat_effects = []
        self.chunks = {}
        self.chunk_obstacles = {}
        self.chunk_enemy_seeds = {}
        self.enemies = []
        self.keys = {}
        self.gamepad = None
        self.gamepad_fire_prev = False
        self.gamepad_tab_prev = False
        self.noise_offset = Vec2(0.0, 0.0)
        self.player_pos = Vec3(0, 0, self.game_cfg.player_height)
        self.score = 0
        self.signal_fragments_recovered = 0
        self.signal_fragments_required = max(1, int(getattr(self.game_cfg, "signal_fragments_required", 4)))
        self.objective_nodes = []
        self.signal_effects = []
        self.return_trail = None
        self.extraction_node = None
        self.extraction_active = False
        self.objective_complete = False
        self.objective_banner = "ETCH-LINE // RECOVER THE LOST SIGNAL FRAGMENTS"
        self.objective_banner_time = 4.0
        self.damage_feedback_time = 0.0
        self.hit_feedback_time = 0.0
        self.holoverse_result = {}

        self.render.setAntialias(AntialiasAttrib.MLine)
        self.render.setTransparency(TransparencyAttrib.MAlpha)
        self.setBackgroundColor(1, 1, 1)
        self.clock = ClockObject.getGlobalClock()
        self.clock.setMode(ClockObject.MNormal)

        self.setup_window()
        self.setup_scene()
        self.setup_ui()
        self.setup_input()
        self.setup_gamepad()
        self.generate_next_weapon(first=True)
        self.accept("window-event", self.on_window_event)
        self.taskMgr.add(self.update_task, "update-task")
        self.taskMgr.doMethodLater(0.25, self.chunk_task, "chunk-task")

        self.camera.setPos(self.player_pos)
        self.pitch = -4.0
        self.yaw = 0.0
        self.recenter_mouse(force=True)

        if SELF_TEST:
            self.taskMgr.doMethodLater(0.6, self.self_test_exit, "self-test-exit")

    def setup_window(self):
        props = WindowProperties()
        props.setTitle(GAME_NAME)
        if not HEADLESS_TEST:
            props.setCursorHidden(True)
        if hasattr(self.win, "requestProperties"):
            self.win.requestProperties(props)

    def setup_scene(self):
        self.city_root = self.render.attachNewNode("city-root")
        self.entity_root = self.render.attachNewNode("entity-root")
        self.effect_root = self.render.attachNewNode("effect-root")
        self.camLens.setNearFar(0.06, self.game_cfg.max_view_distance)
        self.camLens.setFov(82)

        self.fog = Fog("distance-fog")
        self.fog.setExpDensity(0.0)
        self.fog.setLinearRange(self.game_cfg.max_view_distance * self.game_cfg.fog_start_ratio, self.game_cfg.max_view_distance)
        self.render.setFog(self.fog)

        ambient = AmbientLight("ambient")
        ambient.setColor((1, 1, 1, 1))
        self.render.setLight(self.render.attachNewNode(ambient))

        self.filters = None

        self.day_night_mix = 0.0
        self.update_palette(0.0)
        self.generate_city_around_player(force=True)
        self.setup_objectives()

    def setup_ui(self):
        label_style = dict(scale=0.045, fg=(0.95, 0.95, 0.95, 1), align=TextNode.ALeft, mayChange=True)
        shadow_style = dict(shadow=(0, 0, 0, 1), shadowOffset=(0.04, 0.04))

        self.hud_root = self.aspect2d.attachNewNode("hud-root")
        self.hud_frame = DirectFrame(parent=self.hud_root, frameColor=(0.02, 0.02, 0.02, 0.72), frameSize=(-0.64, 0.14, -0.19, 0.18), pos=(-1.18, 0, 0.84))
        self.hud_text = DirectLabel(parent=self.hud_frame, text="", text_scale=0.045, text_align=TextNode.ALeft, text_fg=(1, 1, 1, 1), frameColor=(0, 0, 0, 0), pos=(-0.6, 0, 0.08), textMayChange=True)
        self.help_text = DirectLabel(parent=self.hud_root, text="", text_scale=0.038, text_align=TextNode.ARight, text_fg=(0.95, 0.95, 0.95, 0.78), frameColor=(0, 0, 0, 0), pos=(1.25, 0, -0.9), textMayChange=True)
        self.center_text = DirectLabel(parent=self.hud_root, text="", text_scale=0.05, text_align=TextNode.ACenter, text_fg=(0.96, 0.96, 0.96, 1), frameColor=(0, 0, 0, 0), pos=(0, 0, -0.72), textMayChange=True)

        # Presentation overlay stays visible in HoloVerse native mode; the old/source HUD still obeys H.
        self.mission_overlay_root = self.aspect2d.attachNewNode("etchline-artifact-objective-overlay")
        self.mission_title = DirectLabel(parent=self.mission_overlay_root, text="ETCH-LINE SIGNAL RUN", text_scale=0.047, text_align=TextNode.ACenter, text_fg=(0.97, 0.97, 0.97, 0.92), frameColor=(0, 0, 0, 0), pos=(0, 0, 0.91), textMayChange=True)
        self.mission_text = DirectLabel(parent=self.mission_overlay_root, text="", text_scale=0.036, text_align=TextNode.ACenter, text_fg=(0.95, 0.95, 0.95, 0.84), frameColor=(0, 0, 0, 0), pos=(0, 0, 0.84), textMayChange=True)

        self.crosshair = self.aspect2d.attachNewNode("crosshair")
        self.crosshair_lines = []
        for a, b in [((-.015, 0, 0), (-.005, 0, 0)), ((.015, 0, 0), (.005, 0, 0)), ((0, 0, -.015), (0, 0, -.005)), ((0, 0, .015), (0, 0, .005))]:
            segs = LineSegs("cross")
            segs.setThickness(1.6)
            segs.setColor(0, 0, 0, 0.9)
            segs.moveTo(*a)
            segs.drawTo(*b)
            np = self.crosshair.attachNewNode(segs.create())
            np.setDepthTest(False)
            np.setDepthWrite(False)
            np.setBin("fixed", 100)
            self.crosshair_lines.append(np)
        self.crosshair.setScale(1.0)

        self.menu_root = self.aspect2d.attachNewNode("menu-root")
        self.menu_root.hide()
        self.menu_backdrop = DirectFrame(parent=self.menu_root, frameColor=(0.02, 0.02, 0.02, 0.88), frameSize=(-0.82, 0.82, -0.58, 0.58), pos=(0, 0, 0))
        self.menu_title = DirectLabel(parent=self.menu_root, text="SETTINGS", text_scale=0.072, text_fg=(0.96, 0.96, 0.96, 1), frameColor=(0, 0, 0, 0), pos=(0, 0, 0.44))
        self.menu_info = DirectLabel(parent=self.menu_root, text="", text_scale=0.046, text_align=TextNode.ALeft, text_fg=(0.92, 0.92, 0.92, 1), frameColor=(0, 0, 0, 0), pos=(-0.72, 0, 0.18), textMayChange=True)
        self.btn_resume = DirectButton(parent=self.menu_root, text="Resume", scale=0.065, frameColor=(0.12, 0.12, 0.12, 0.96), text_fg=(0.95, 0.95, 0.95, 1), command=self.toggle_menu, pos=(0, 0, -0.12))
        self.btn_distance = DirectButton(parent=self.menu_root, text="More Draw Distance", scale=0.055, frameColor=(0.12, 0.12, 0.12, 0.96), text_fg=(0.95, 0.95, 0.95, 1), command=self.adjust_view_distance, extraArgs=[60.0], pos=(0, 0, -0.25))
        self.btn_lines = DirectButton(parent=self.menu_root, text="Thicker Lines", scale=0.055, frameColor=(0.12, 0.12, 0.12, 0.96), text_fg=(0.95, 0.95, 0.95, 1), command=self.adjust_line_thickness, extraArgs=[0.12], pos=(0, 0, -0.36))
        self.btn_sensitivity = DirectButton(parent=self.menu_root, text="More Mouse Sensitivity", scale=0.055, frameColor=(0.12, 0.12, 0.12, 0.96), text_fg=(0.95, 0.95, 0.95, 1), command=self.adjust_sensitivity, extraArgs=[0.01], pos=(0, 0, -0.47))

        self.work_root = self.aspect2d.attachNewNode("work-root")
        self.work_root.hide()
        self.work_frame = DirectFrame(parent=self.work_root, frameColor=(0.03, 0.03, 0.03, 0.82), frameSize=(-0.63, 0.63, -0.35, 0.35), pos=(0.5, 0, 0.58))
        self.work_title = DirectLabel(parent=self.work_root, text="WORKSTATION", text_scale=0.05, text_fg=(0.95, 0.95, 0.95, 1), frameColor=(0, 0, 0, 0), pos=(0.5, 0, 0.83))
        self.work_text = DirectLabel(parent=self.work_root, text="", text_scale=0.038, text_align=TextNode.ALeft, text_fg=(0.93, 0.93, 0.93, 1), frameColor=(0, 0, 0, 0), pos=(-0.06, 0, 0.66), textMayChange=True)

        self.refresh_ui_text()

    def setup_input(self):
        for key in ["w", "a", "s", "d", "shift", "space"]:
            self.accept(key, self.set_key, [key, True])
            self.accept(f"{key}-up", self.set_key, [key, False])
        self.accept("mouse1", self.set_fire, [True])
        self.accept("mouse1-up", self.set_fire, [False])
        self.accept("tab", self.generate_next_weapon)
        self.accept("shift-tab", self.generate_previous_weapon)
        self.accept("gamepad-rshoulder", self.generate_next_weapon)
        self.accept("gamepad-lshoulder", self.generate_previous_weapon)
        self.accept("h", self.toggle_hud)
        self.accept("f10", self.toggle_workstation)
        self.accept("escape", self.toggle_menu)

    def setup_gamepad(self):
        devices = self.devices.getDevices(InputDevice.DeviceClass.gamepad)
        if devices:
            self.attachInputDevice(devices[0], prefix="gamepad")
            self.gamepad = devices[0]
        self.accept("connect-device", self.on_device_connect)
        self.accept("disconnect-device", self.on_device_disconnect)

    def on_device_connect(self, device):
        if device.device_class == InputDevice.DeviceClass.gamepad and self.gamepad is None:
            self.attachInputDevice(device, prefix="gamepad")
            self.gamepad = device

    def on_device_disconnect(self, device):
        if self.gamepad == device:
            self.detachInputDevice(device)
            self.gamepad = None

    def set_key(self, key, value):
        self.keys[key] = value

    def set_fire(self, value):
        self.fire_hold = value
        if value:
            self.fire_down = True

    def toggle_hud(self):
        self.hud_visible = not self.hud_visible
        if self.hud_visible:
            self.hud_root.show()
            self.crosshair.show()
        else:
            self.hud_root.hide()
            self.crosshair.hide()

    def toggle_workstation(self):
        self.workstation_visible = not self.workstation_visible
        if self.workstation_visible:
            self.work_root.show()
        else:
            self.work_root.hide()

    def toggle_menu(self):
        self.menu_open = not self.menu_open
        if self.menu_open:
            self.menu_root.show()
            props = WindowProperties()
            props.setCursorHidden(False)
            if hasattr(self.win, "requestProperties"):
                self.win.requestProperties(props)
        else:
            self.menu_root.hide()
            if not HEADLESS_TEST:
                props = WindowProperties()
                props.setCursorHidden(True)
                if hasattr(self.win, "requestProperties"):
                    self.win.requestProperties(props)
                self.recenter_mouse(force=True)

    def on_window_event(self, window):
        if not SELF_TEST and window is not None:
            self.recenter_mouse(force=True)

    def recenter_mouse(self, force=False):
        if HEADLESS_TEST or self.menu_open or not self.win:
            return
        if not self.win.getProperties().getForeground() and not force:
            return
        cx = self.win.getXSize() // 2
        cy = self.win.getYSize() // 2
        self.win.movePointer(0, cx, cy)

    def refresh_ui_text(self):
        weapon = self.current_weapon.name if self.current_weapon else "-"
        self.hud_text["text"] = (
            f"{GAME_NAME}\n"
            f"Weapon: {weapon}\n"
            f"Health: {self.health:03d}\n"
            f"Signal: {self.signal_fragments_recovered}/{self.signal_fragments_required}\n"
            f"Score: {self.score}\n"
            f"Cycle: {self.day_label()}"
        )
        self.help_text["text"] = "WASD move  Shift sprint  LMB fire/recover  TAB weapon  H HUD  ESC settings  F10 workstation"
        self.refresh_mission_text()
        self.menu_info["text"] = (
            f"Draw Distance: {int(self.game_cfg.max_view_distance)}\n"
            f"Line Thickness: {self.game_cfg.line_thickness:.2f}\n"
            f"Mouse Sensitivity: {self.game_cfg.mouse_sensitivity:.2f}\n"
            f"Day Length: {self.game_cfg.day_length_seconds / 60:.1f} min\n"
            f"Logs: {LOG_DIR.name}/\n"
            f"Config: {CONFIG_PATH.name}"
        )

    def refresh_workstation_text(self):
        self.work_text["text"] = (
            f"Version: {VERSION}\n"
            f"Chunks: {len(self.chunks)}\n"
            f"Enemies: {sum(not e.dead for e in self.enemies)}\n"
            f"Weapon Index: {self.current_weapon.index if self.current_weapon else 0}\n"
            f"Signal Fragments: {self.signal_fragments_recovered}/{self.signal_fragments_required}\n"
            f"Score: {self.score}\n"
            f"View Distance: {int(self.game_cfg.max_view_distance)}\n"
            f"Palette: {self.day_label()}\n"
            f"Config File: {CONFIG_PATH}\n"
            f"Patch Notes: {PATCH_DIR}\n"
            f"Crash Logs: {CRASH_DIR}\n"
            f"F10 toggle  TAB weapon"
        )

    def setup_objectives(self):
        self.mission_root = self.effect_root.attachNewNode("etchline-signal-objectives")
        self.objective_nodes = []
        self.signal_effects = []
        if getattr(self, "return_trail", None) is not None:
            try:
                if not self.return_trail.isEmpty():
                    self.return_trail.removeNode()
            except Exception:
                pass
        self.return_trail = None
        self.signal_fragments_recovered = 0
        self.extraction_active = False
        self.objective_complete = False
        self.score = int(getattr(self, "score", 0) or 0)
        self.holoverse_result = self.get_holoverse_result()
        base_positions = [
            Vec3(96, 56, 0),
            Vec3(-128, 72, 0),
            Vec3(80, -132, 0),
            Vec3(-116, -112, 0),
            Vec3(168, -24, 0),
            Vec3(-32, 168, 0),
        ]
        required = max(1, min(len(base_positions), int(getattr(self.game_cfg, "signal_fragments_required", 4))))
        self.signal_fragments_required = required
        for i, pos in enumerate(base_positions[:required]):
            self.objective_nodes.append(SignalNode(self, i + 1, pos, f"FRAGMENT {i + 1}", kind="fragment"))
        self.extraction_node = SignalNode(self, 0, Vec3(0, -188, 0), "RETURN LATTICE", kind="extraction")
        self.set_objective_banner("ETCH-LINE // Recover signal fragments, then reach the return lattice.", 4.0)

    def set_objective_banner(self, text: str, duration: float = 2.4) -> None:
        self.objective_banner = str(text or "")
        self.objective_banner_time = max(float(getattr(self, "objective_banner_time", 0.0) or 0.0), float(duration or 0.0))

    def refresh_mission_text(self):
        if not hasattr(self, "mission_text"):
            return
        if getattr(self, "objective_complete", False):
            line = f"SIGNAL COMPLETE // SCORE {self.score} // ESC / 0 RETURN"
        elif getattr(self, "extraction_active", False):
            meters = self.distance_to_node(getattr(self, "extraction_node", None))
            dist = f" // {meters}m" if meters is not None else ""
            line = f"RETURN LATTICE OPEN{dist} // SCORE {self.score}"
        else:
            meters = self.distance_to_nearest_fragment()
            dist = f" // NEAREST {meters}m" if meters is not None else ""
            line = f"FRAGMENTS {self.signal_fragments_recovered}/{self.signal_fragments_required}{dist} // SCORE {self.score}"
        try:
            self.mission_text["text"] = line
        except Exception:
            pass

    def distance_to_node(self, node) -> int | None:
        try:
            if node is None or not getattr(node, "active", False):
                return None
            player = getattr(self, "player_pos", Vec3(0, 0, 0))
            delta = Vec3(node.pos.x - player.x, node.pos.y - player.y, 0)
            return max(0, int(round(delta.length())))
        except Exception:
            return None

    def distance_to_nearest_fragment(self) -> int | None:
        best = None
        try:
            for node in list(getattr(self, "objective_nodes", []) or []):
                if getattr(node, "completed", False) or not getattr(node, "active", False):
                    continue
                d = self.distance_to_node(node)
                if d is not None and (best is None or d < best):
                    best = d
        except Exception:
            return None
        return best

    def add_signal_pulse(self, pos: Vec3, label: str = "signal", radius: float = 4.0, life: float = 1.2, height: float = 0.10) -> None:
        try:
            budget = max(0, int(getattr(self.game_cfg, "objective_pulse_budget", 18)))
            self.signal_effects.append(SignalPulseEffect(self, pos, label=label, radius=radius, life=life, height=height))
            overflow = len(self.signal_effects) - budget
            if overflow > 0:
                for effect in self.signal_effects[:overflow]:
                    try:
                        effect.dispose()
                    except Exception:
                        pass
                self.signal_effects = self.signal_effects[overflow:]
        except Exception:
            pass

    def add_combat_feedback(self, pos: Vec3, label: str = "hit", radius: float = 1.0, life: float = 0.5, warning: bool = True) -> None:
        try:
            budget = max(0, int(getattr(self.game_cfg, "max_combat_effects", 28)))
            self.combat_effects.append(CombatFeedbackEffect(self, pos, label=label, radius=radius, life=life, warning=warning))
            overflow = len(self.combat_effects) - budget
            if overflow > 0:
                for effect in self.combat_effects[:overflow]:
                    try:
                        effect.dispose()
                    except Exception:
                        pass
                self.combat_effects = self.combat_effects[overflow:]
        except Exception:
            pass

    def register_enemy_kill(self, enemy, point: Vec3) -> None:
        gain = max(0, int(getattr(self.game_cfg, "enemy_kill_score", 25)))
        self.score += gain
        self.hit_feedback_time = max(float(getattr(self, "hit_feedback_time", 0.0) or 0.0), 0.18)
        try:
            self.add_combat_feedback(point, label="death", radius=1.45, life=0.62, warning=True)
        except Exception:
            pass

    def apply_enemy_contact_damage(self, enemy, amount: int | None = None) -> None:
        if getattr(enemy, "dead", False):
            return
        damage = max(1, int(amount if amount is not None else getattr(self.game_cfg, "enemy_contact_damage", 10)))
        self.health = max(0, int(getattr(self, "health", self.game_cfg.default_health)) - damage)
        self.damage_feedback_time = max(float(getattr(self, "damage_feedback_time", 0.0) or 0.0), 0.75)
        try:
            pos = enemy.root.getPos()
            self.add_combat_feedback(pos, label="contact", radius=1.8, life=0.55, warning=True)
        except Exception:
            pass

    def build_return_trail(self) -> None:
        if getattr(self, "return_trail", None) is not None:
            try:
                if not self.return_trail.isEmpty():
                    self.return_trail.removeNode()
            except Exception:
                pass
        try:
            target = getattr(self, "extraction_node", None)
            if target is None:
                return
            segs = LineSegs("etchline-return-trail")
            segs.setThickness(max(2.0, float(getattr(self.game_cfg, "line_thickness", 1.45)) * 1.75))
            segs.setColor(*self.signal_accent_color(alpha=0.68))
            start = Vec3(0, 0, 0.08)
            end = Vec3(target.pos.x, target.pos.y, 0.08)
            segs.moveTo(start)
            segs.drawTo(end)
            steps = 14
            for i in range(1, steps):
                t = i / steps
                y = start.y * (1.0 - t) + end.y * t
                x = start.x * (1.0 - t) + end.x * t
                half = 1.2 + 0.5 * math.sin(i * 0.9)
                segs.moveTo(x - half, y, 0.10)
                segs.drawTo(x + half, y, 0.10)
            self.return_trail = self.mission_root.attachNewNode(segs.create())
            self.return_trail.setTransparency(TransparencyAttrib.MAlpha)
            self.return_trail.setAntialias(AntialiasAttrib.MLine)
        except Exception:
            self.return_trail = None

    def spawn_signal_wave(self, origin: Vec3) -> None:
        budget = max(0, int(getattr(self.game_cfg, "max_enemies", 56)) - len(getattr(self, "enemies", []) or []))
        count = min(max(0, int(getattr(self.game_cfg, "objective_wave_size", 5))), budget)
        if count <= 0:
            return
        self.add_signal_pulse(origin, label="wave", radius=7.5, life=1.65, height=0.16)
        self.set_objective_banner("SIGNAL PRESSURE WAVE // HOSTILE LINES INBOUND", 2.2)
        seed = self.hashed_seed(int(origin.x), int(origin.y), self.signal_fragments_recovered + 700)
        rng = random.Random(seed)
        for i in range(count):
            angle = math.tau * (i / max(1, count)) + rng.uniform(-0.35, 0.35)
            radius = rng.uniform(18, 34)
            pos = Vec3(origin.x + math.cos(angle) * radius, origin.y + math.sin(angle) * radius, 0)
            if self.point_hits_obstacle(pos, radius=1.3, height=3.2):
                continue
            self.add_combat_feedback(pos, label="spawn", radius=2.4, life=max(0.42, float(getattr(self.game_cfg, "enemy_spawn_warning_seconds", 0.55)) + 0.18), warning=True)
            self.enemies.append(Enemy(self, pos, self.hashed_seed(int(pos.x), int(pos.y), i + 901), chunk_key=None))

    def recover_signal_node(self, node: SignalNode, method: str = "touch") -> None:
        if node is None or getattr(node, "completed", False) or getattr(node, "kind", "fragment") != "fragment":
            return
        node.mark_completed()
        self.signal_fragments_recovered = min(self.signal_fragments_required, self.signal_fragments_recovered + 1)
        gain = int(getattr(self.game_cfg, "objective_score_per_fragment", 175))
        self.score += gain
        self.add_signal_pulse(node.pos, label=f"fragment-{node.index}", radius=max(4.0, node.radius), life=1.55, height=0.18)
        self.spawn_signal_wave(node.pos)
        self.set_objective_banner(f"{node.label} RECOVERED // +{gain} // {self.signal_fragments_recovered}/{self.signal_fragments_required}", 2.8)
        if self.signal_fragments_recovered >= self.signal_fragments_required:
            self.activate_extraction()
        self.holoverse_result = self.get_holoverse_result()

    def activate_extraction(self) -> None:
        if getattr(self, "extraction_active", False):
            return
        self.extraction_active = True
        if getattr(self, "extraction_node", None) is not None:
            self.extraction_node.set_active(True)
            self.add_signal_pulse(self.extraction_node.pos, label="return-lattice", radius=8.5, life=2.2, height=0.2)
        self.build_return_trail()
        self.set_objective_banner("RETURN LATTICE OPEN // FOLLOW THE CYAN TRAIL", 4.0)

    def complete_objective(self) -> None:
        if getattr(self, "objective_complete", False):
            return
        self.objective_complete = True
        bonus = int(getattr(self.game_cfg, "objective_completion_bonus", 800))
        self.score += bonus
        if getattr(self, "extraction_node", None) is not None:
            self.add_signal_pulse(self.extraction_node.pos, label="complete", radius=10.0, life=2.4, height=0.28)
        self.set_objective_banner(f"ETCH-LINE STABILIZED // +{bonus} // RETURN SIGNAL READY", 5.0)
        self.holoverse_result = self.get_holoverse_result()

    def update_signal_objectives(self, dt: float) -> None:
        player = getattr(self, "player_pos", Vec3(0, 0, 0))
        for node in list(getattr(self, "objective_nodes", []) or []):
            node.update(dt, player)
            if not node.completed and node.player_inside(player):
                self.recover_signal_node(node, method="touch")
        gate = getattr(self, "extraction_node", None)
        if gate is not None:
            gate.update(dt, player)
            if getattr(self, "extraction_active", False) and not getattr(self, "objective_complete", False) and gate.player_inside(player):
                self.complete_objective()
        if getattr(self, "objective_banner_time", 0.0) > 0.0:
            self.objective_banner_time = max(0.0, self.objective_banner_time - dt)

    def check_objective_shot(self, origin: Vec3, direction: Vec3, max_range: float):
        best = None
        for node in list(getattr(self, "objective_nodes", []) or []):
            hit = node.ray_hit(origin, direction, max_range)
            if hit is None:
                continue
            if best is None or hit[0] < best[0]:
                best = (hit[0], hit[1], node)
        return best

    def get_holoverse_result(self) -> dict:
        recovered = int(getattr(self, "signal_fragments_recovered", 0) or 0)
        required = int(getattr(self, "signal_fragments_required", 4) or 4)
        completed = bool(getattr(self, "objective_complete", False))
        signal = "ETCHLINE_RETURN_LATTICE_STABILIZED" if completed else ("ETCHLINE_SIGNAL_FRAGMENT" if recovered else "")
        return {
            "schema": 1,
            "mode": GAME_NAME,
            "score_delta": int(getattr(self, "score", 0) or 0),
            "completed": completed,
            "fragments_recovered": recovered,
            "fragments_required": required,
            "signal": signal,
            "memory_fragment": signal,
            "gleebs_response": "Etch-Line returned a clean route lattice." if completed else "Etch-Line returned a partial signal trace.",
        }

    def day_label(self):
        labels = ["Dawn", "Day", "Dusk", "Night"]
        t = (self.elapsed % self.game_cfg.day_length_seconds) / self.game_cfg.day_length_seconds
        if t < 0.2:
            return labels[0]
        if t < 0.5:
            return labels[1]
        if t < 0.7:
            return labels[2]
        return labels[3]

    def current_line_color(self, alpha=1.0):
        v = self.palette_value()
        return (v, v, v, alpha)

    def signal_accent_color(self, alpha=1.0):
        # Cyan-blue objective accent stays readable across Etch-Line's day/night inversion.
        day = float(getattr(self, "day_night_mix", 0.0) or 0.0)
        return (0.10 + 0.10 * day, 0.82 - 0.22 * day, 1.0 - 0.16 * day, alpha)

    def warning_accent_color(self, alpha=1.0):
        day = float(getattr(self, "day_night_mix", 0.0) or 0.0)
        return (1.0 - 0.20 * day, 0.28 + 0.08 * day, 0.18 + 0.04 * day, alpha)

    def palette_value(self):
        return 1.0 - self.day_night_mix

    def update_palette(self, dt: float):
        day_len = max(60.0, self.game_cfg.day_length_seconds)
        self.day_phase = (self.elapsed % day_len) / day_len
        transition = max(10.0, self.game_cfg.transition_length_seconds) / day_len
        def smooth_band(x, center):
            d = abs((x - center + 0.5) % 1.0 - 0.5)
            if d >= transition * 0.5:
                return 0.0
            y = 1.0 - d / (transition * 0.5)
            return y * y * (3 - 2 * y)
        dawn = smooth_band(self.day_phase, 0.10)
        dusk = smooth_band(self.day_phase, 0.60)
        day_base = 1.0 if 0.10 <= self.day_phase < 0.60 else 0.0
        day_amount = max(day_base, dawn)
        day_amount = min(day_amount, 1.0 - dusk * (1.0 - day_amount))
        self.day_night_mix = day_amount
        bg = day_amount
        fg = 1.0 - bg
        self.setBackgroundColor(bg, bg, bg)
        self.fog.setColor(bg, bg, bg)
        for np in getattr(self, "crosshair_lines", []):
            np.setColor(fg, fg, fg, 0.96)
        if self.filters and self.win is not None and hasattr(self.win, "setClearColorActive"):
            try:
                self.win.setClearColorActive(True)
            except Exception:
                pass

    def create_blotch_texture(self):
        generate_blotch_texture_file()

    def hashed_seed(self, x: int, y: int, salt: int = 0) -> int:
        return (x * 92837111 ^ y * 689287499 ^ self.game_cfg.world_seed ^ salt * 334214459) & 0xFFFFFFFF

    def generate_chunk_geometry(self, cx: int, cy: int):
        chunk_seed = self.hashed_seed(cx, cy)
        rng = random.Random(chunk_seed)
        origin_x = cx * self.game_cfg.chunk_size
        origin_y = cy * self.game_cfg.chunk_size
        np = self.city_root.attachNewNode(f"chunk-{cx}-{cy}")
        segs = LineSegs(f"chunk-lines-{cx}-{cy}")
        segs.setThickness(self.game_cfg.line_thickness)
        segs.setColor(*self.current_line_color(alpha=0.94))
        obstacles = []
        enemy_spawns = []

        grid_step = 8
        for gx in range(0, self.game_cfg.chunk_size + 1, grid_step):
            x = origin_x + gx
            segs.moveTo(x, origin_y, 0)
            segs.drawTo(x, origin_y + self.game_cfg.chunk_size, 0)
        for gy in range(0, self.game_cfg.chunk_size + 1, grid_step):
            y = origin_y + gy
            segs.moveTo(origin_x, y, 0)
            segs.drawTo(origin_x + self.game_cfg.chunk_size, y, 0)

        building_count = 7 + rng.randint(0, 6)
        for i in range(building_count):
            bx = origin_x + rng.uniform(8, self.game_cfg.chunk_size - 8)
            by = origin_y + rng.uniform(8, self.game_cfg.chunk_size - 8)
            w = rng.uniform(6, 14)
            d = rng.uniform(6, 14)
            h = rng.uniform(16, 90)
            tiers = rng.randint(1, 4)
            base_x = bx
            base_y = by
            base_h = 0.0
            cur_w = w
            cur_d = d
            cur_h = h
            for t in range(tiers):
                center = Vec3(base_x, base_y, base_h + cur_h * 0.5)
                size = Vec3(cur_w, cur_d, cur_h)
                self.draw_box_edges(segs, center, size)
                obstacles.append(BoxBounds(center - size * 0.5, center + size * 0.5, Vec3(0, 0, 1)))
                if rng.random() < 0.44:
                    bridge_len = rng.uniform(6, 18)
                    dir_sign = -1 if rng.random() < 0.5 else 1
                    bridge_center = center + Vec3(dir_sign * (cur_w * 0.5 + bridge_len * 0.5), 0, rng.uniform(-cur_h * 0.15, cur_h * 0.22))
                    bridge_size = Vec3(bridge_len, rng.uniform(2.0, 4.5), rng.uniform(2.0, 4.0))
                    self.draw_box_edges(segs, bridge_center, bridge_size)
                    obstacles.append(BoxBounds(bridge_center - bridge_size * 0.5, bridge_center + bridge_size * 0.5, Vec3(0, 0, 1)))
                base_x += rng.uniform(-3.5, 3.5)
                base_y += rng.uniform(-3.5, 3.5)
                base_h += cur_h
                cur_w = max(3.2, cur_w * rng.uniform(0.55, 0.82))
                cur_d = max(3.2, cur_d * rng.uniform(0.55, 0.82))
                cur_h = max(7.0, cur_h * rng.uniform(0.35, 0.62))

            if rng.random() < 0.45:
                mech_x = bx + rng.uniform(-10, 10)
                mech_y = by + rng.uniform(-10, 10)
                mech_z = rng.uniform(8, 24)
                self.draw_mechanical_cluster(segs, Vec3(mech_x, mech_y, mech_z), rng)

        stair_runs = rng.randint(1, 3)
        for _ in range(stair_runs):
            sx = origin_x + rng.uniform(4, self.game_cfg.chunk_size - 20)
            sy = origin_y + rng.uniform(4, self.game_cfg.chunk_size - 20)
            steps = rng.randint(5, 9)
            step_w = rng.uniform(4, 7)
            step_h = rng.uniform(0.7, 1.4)
            for i in range(steps):
                center = Vec3(sx + i * step_w * 0.7, sy, i * step_h + step_h * 0.5)
                size = Vec3(step_w, 4.2, step_h)
                self.draw_box_edges(segs, center, size)
                obstacles.append(BoxBounds(center - size * 0.5, center + size * 0.5, Vec3(0, 0, 1)))

        enemy_count = rng.randint(1, 3)
        for i in range(enemy_count):
            px = origin_x + rng.uniform(8, self.game_cfg.chunk_size - 8)
            py = origin_y + rng.uniform(8, self.game_cfg.chunk_size - 8)
            if not self.point_hits_obstacle(Vec3(px, py, 0), radius=1.3, height=3.2, obstacles=obstacles):
                enemy_spawns.append((px, py, self.hashed_seed(cx, cy, i + 91)))

        geom = segs.create()
        visual_np = np.attachNewNode(geom)
        visual_np.setAntialias(AntialiasAttrib.MLine)
        visual_np.setTransparency(TransparencyAttrib.MAlpha)
        return np, obstacles, enemy_spawns

    def draw_box_edges(self, segs: LineSegs, center: Vec3, size: Vec3):
        hx, hy, hz = size.x * 0.5, size.y * 0.5, size.z * 0.5
        x0, x1 = center.x - hx, center.x + hx
        y0, y1 = center.y - hy, center.y + hy
        z0, z1 = center.z - hz, center.z + hz
        edges = [
            ((x0, y0, z0), (x1, y0, z0)), ((x1, y0, z0), (x1, y1, z0)), ((x1, y1, z0), (x0, y1, z0)), ((x0, y1, z0), (x0, y0, z0)),
            ((x0, y0, z1), (x1, y0, z1)), ((x1, y0, z1), (x1, y1, z1)), ((x1, y1, z1), (x0, y1, z1)), ((x0, y1, z1), (x0, y0, z1)),
            ((x0, y0, z0), (x0, y0, z1)), ((x1, y0, z0), (x1, y0, z1)), ((x1, y1, z0), (x1, y1, z1)), ((x0, y1, z0), (x0, y1, z1)),
        ]
        jitter = self.game_cfg.line_jitter
        for a, b in edges:
            j = Vec3(random.uniform(-jitter, jitter), random.uniform(-jitter, jitter), random.uniform(-jitter, jitter))
            segs.moveTo(a[0] + j.x, a[1] + j.y, a[2] + j.z)
            segs.drawTo(b[0] + j.x, b[1] + j.y, b[2] + j.z)

    def draw_mechanical_cluster(self, segs: LineSegs, pos: Vec3, rng: random.Random):
        rings = rng.randint(2, 5)
        for i in range(rings):
            radius = rng.uniform(2.0, 5.5)
            z = pos.z + i * rng.uniform(1.2, 3.8)
            x = pos.x + rng.uniform(-6, 6)
            y = pos.y + rng.uniform(-6, 6)
            self.draw_ring(segs, Vec3(x, y, z), radius, 16)
            rod_len = rng.uniform(4, 12)
            segs.moveTo(x, y - rod_len * 0.5, z)
            segs.drawTo(x, y + rod_len * 0.5, z)

    def draw_ring(self, segs: LineSegs, center: Vec3, radius: float, segments: int):
        last = None
        first = None
        for i in range(segments):
            ang = math.tau * i / segments
            p = Vec3(center.x + math.cos(ang) * radius, center.y, center.z + math.sin(ang) * radius)
            if first is None:
                first = p
            if last is not None:
                segs.moveTo(last)
                segs.drawTo(p)
            last = p
        if last is not None and first is not None:
            segs.moveTo(last)
            segs.drawTo(first)

    def generate_city_around_player(self, force=False):
        csize = self.game_cfg.chunk_size
        px = int(math.floor(self.player_pos.x / csize))
        py = int(math.floor(self.player_pos.y / csize))
        required = set()
        radius = self.game_cfg.active_chunk_radius
        for cx in range(px - radius, px + radius + 1):
            for cy in range(py - radius, py + radius + 1):
                required.add((cx, cy))
                if (cx, cy) not in self.chunks:
                    np, obstacles, spawns = self.generate_chunk_geometry(cx, cy)
                    self.chunks[(cx, cy)] = np
                    self.chunk_obstacles[(cx, cy)] = obstacles
                    self.chunk_enemy_seeds[(cx, cy)] = spawns
                    for ex, ey, seed in spawns:
                        if len(self.enemies) < max(1, int(self.game_cfg.max_enemies)):
                            self.enemies.append(Enemy(self, Vec3(ex, ey, 0), seed, chunk_key=(cx, cy)))
        for key in list(self.chunks.keys()):
            if key not in required:
                self.retire_chunk(key)
        self.enforce_chunk_budget(required, center=(px, py))
        self.prune_runtime_entities()

    def retire_chunk(self, chunk_key):
        self.retire_chunk_enemies(chunk_key)
        node = self.chunks.pop(chunk_key, None)
        if node is not None:
            try:
                node.removeNode()
            except Exception:
                pass
        self.chunk_obstacles.pop(chunk_key, None)
        self.chunk_enemy_seeds.pop(chunk_key, None)

    def retire_chunk_enemies(self, chunk_key):
        kept = []
        for enemy in self.enemies:
            if getattr(enemy, "chunk_key", None) == chunk_key:
                enemy.dispose()
            else:
                kept.append(enemy)
        self.enemies = kept

    def enforce_chunk_budget(self, required=None, center=None):
        max_chunks = max(1, int(getattr(self.game_cfg, "max_chunks_loaded", 81)))
        if len(self.chunks) <= max_chunks:
            return
        required = set(required or [])
        if center is None:
            csize = self.game_cfg.chunk_size
            center = (int(math.floor(self.player_pos.x / csize)), int(math.floor(self.player_pos.y / csize)))
        cx0, cy0 = center
        candidates = []
        for key in self.chunks.keys():
            if key in required and len(required) <= max_chunks:
                continue
            dx = key[0] - cx0
            dy = key[1] - cy0
            candidates.append((dx * dx + dy * dy, key))
        candidates.sort(reverse=True)
        for _dist, key in candidates:
            if len(self.chunks) <= max_chunks:
                break
            self.retire_chunk(key)

    def runtime_budget_report(self) -> dict:
        chunk_nodes = len(getattr(self, "chunks", {}) or {})
        live_enemies = sum(1 for e in getattr(self, "enemies", []) if not getattr(e, "dead", False))
        report = {
            "game": GAME_NAME,
            "version": VERSION,
            "chunks": chunk_nodes,
            "chunk_obstacle_sets": len(getattr(self, "chunk_obstacles", {}) or {}),
            "chunk_enemy_seed_sets": len(getattr(self, "chunk_enemy_seeds", {}) or {}),
            "enemies": len(getattr(self, "enemies", []) or []),
            "live_enemies": live_enemies,
            "score": int(getattr(self, "score", 0) or 0),
            "signal_fragments_recovered": int(getattr(self, "signal_fragments_recovered", 0) or 0),
            "signal_fragments_required": int(getattr(self, "signal_fragments_required", 0) or 0),
            "objective_complete": bool(getattr(self, "objective_complete", False)),
            "tracers": len(getattr(self, "tracers", []) or []),
            "blotches": len(getattr(self, "blotches", []) or []),
            "signal_effects": len(getattr(self, "signal_effects", []) or []),
            "combat_effects": len(getattr(self, "combat_effects", []) or []),
            "max_chunks_loaded": int(getattr(self.game_cfg, "max_chunks_loaded", 81)),
            "max_enemies": int(getattr(self.game_cfg, "max_enemies", 72)),
            "max_tracers": int(getattr(self.game_cfg, "max_tracers", 96)),
            "max_blotches": int(getattr(self.game_cfg, "max_blotches", 80)),
            "within_budget": (
                chunk_nodes <= int(getattr(self.game_cfg, "max_chunks_loaded", 81))
                and len(getattr(self, "enemies", []) or []) <= int(getattr(self.game_cfg, "max_enemies", 72))
                and len(getattr(self, "tracers", []) or []) <= int(getattr(self.game_cfg, "max_tracers", 96))
                and len(getattr(self, "blotches", []) or []) <= int(getattr(self.game_cfg, "max_blotches", 80))
                and len(getattr(self, "signal_effects", []) or []) <= int(getattr(self.game_cfg, "objective_pulse_budget", 18))
                and len(getattr(self, "combat_effects", []) or []) <= int(getattr(self.game_cfg, "max_combat_effects", 28))
            ),
        }
        for attr, key in (
            ("entity_root", "entity_root_children"),
            ("effect_root", "effect_root_children"),
            ("city_root", "city_root_children"),
        ):
            node = getattr(self, attr, None)
            try:
                if node is not None and hasattr(node, "isEmpty") and not node.isEmpty():
                    report[key] = node.getNumChildren()
                else:
                    report[key] = 0
            except Exception:
                report[key] = 0
        return report

    def point_hits_obstacle(self, pos: Vec3, radius: float = 0.42, height: float = 1.8, obstacles=None):
        obs = obstacles
        if obs is None:
            obs = []
            csize = self.game_cfg.chunk_size
            px = int(math.floor(pos.x / csize))
            py = int(math.floor(pos.y / csize))
            for cx in range(px - 1, px + 2):
                for cy in range(py - 1, py + 2):
                    obs.extend(self.chunk_obstacles.get((cx, cy), []))
        test_min = Vec3(pos.x - radius, pos.y - radius, 0)
        test_max = Vec3(pos.x + radius, pos.y + radius, height)
        for box in obs:
            if (test_min.x <= box.max_v.x and test_max.x >= box.min_v.x and
                test_min.y <= box.max_v.y and test_max.y >= box.min_v.y and
                test_min.z <= box.max_v.z and test_max.z >= box.min_v.z):
                return True
        return False

    def generate_next_weapon(self, first=False):
        idx = self.current_weapon_seed
        if not first:
            idx += 1
            self.current_weapon_seed = idx
        name_pool_a = ["Bone", "Static", "Night", "Hex", "Velvet", "Chrome", "Abyss", "Shard", "Etch", "Cipher", "Null", "Pale"]
        name_pool_b = ["Howler", "Needle", "Ripper", "Scatter", "Prism", "Sever", "Breaker", "Lattice", "Screecher", "Arc", "Talon", "Revenant"]
        rng = random.Random(idx * 991)
        archetypes = [
            ("pistol", 26, 0.18, 0.5, 160, 1, 0.05, 0.2),
            ("smg", 12, 0.08, 1.2, 140, 1, 0.04, 0.35),
            ("rifle", 34, 0.22, 0.35, 200, 1, 0.06, 0.3),
            ("scatter", 11, 0.42, 4.0, 78, 8, 0.08, 0.55),
            ("slug", 62, 0.65, 0.18, 220, 1, 0.1, 0.65),
            ("needle", 7, 0.035, 1.6, 165, 1, 0.025, 0.18),
        ]
        arch = archetypes[idx % len(archetypes)]
        name = f"{name_pool_a[rng.randrange(len(name_pool_a))]} {name_pool_b[rng.randrange(len(name_pool_b))]} {idx + 1:03d}"
        self.current_weapon = Weapon(
            index=idx,
            name=name,
            damage=arch[1] * rng.uniform(0.92, 1.18),
            fire_interval=max(0.03, arch[2] * rng.uniform(0.9, 1.14)),
            spread=max(0.03, arch[3] * rng.uniform(0.85, 1.25)),
            range=arch[4] * rng.uniform(0.9, 1.08),
            projectiles=int(arch[5]),
            tracer_time=arch[6],
            recoil=arch[7] * rng.uniform(0.85, 1.2),
        )
        self.weapon_banner_time = 2.4
        self.refresh_ui_text()

    def generate_previous_weapon(self):
        self.current_weapon_seed = max(0, self.current_weapon_seed - 1)
        self.generate_next_weapon(first=True)
        self.current_weapon.index = self.current_weapon_seed
        self.weapon_banner_time = 2.4
        self.refresh_ui_text()

    def adjust_view_distance(self, delta):
        self.game_cfg.max_view_distance = max(200.0, min(1200.0, self.game_cfg.max_view_distance + delta))
        self.camLens.setNearFar(0.06, self.game_cfg.max_view_distance)
        self.fog.setLinearRange(self.game_cfg.max_view_distance * self.game_cfg.fog_start_ratio, self.game_cfg.max_view_distance)
        CONFIG_PATH.write_text(json.dumps(asdict(self.game_cfg), indent=2), encoding="utf-8")
        self.refresh_ui_text()

    def adjust_line_thickness(self, delta):
        self.game_cfg.line_thickness = max(0.8, min(3.2, self.game_cfg.line_thickness + delta))
        CONFIG_PATH.write_text(json.dumps(asdict(self.game_cfg), indent=2), encoding="utf-8")
        self.rebuild_chunks()
        self.refresh_ui_text()

    def adjust_sensitivity(self, delta):
        self.game_cfg.mouse_sensitivity = max(0.02, min(0.4, self.game_cfg.mouse_sensitivity + delta))
        CONFIG_PATH.write_text(json.dumps(asdict(self.game_cfg), indent=2), encoding="utf-8")
        self.refresh_ui_text()

    def rebuild_chunks(self):
        for key in list(self.chunks.keys()):
            self.retire_chunk(key)
        for enemy in list(self.enemies):
            enemy.dispose()
        for tracer in list(self.tracers):
            tracer.dispose()
        for blotch in list(self.blotches):
            blotch.dispose()
        for effect in list(getattr(self, "combat_effects", []) or []):
            try:
                effect.dispose()
            except Exception:
                pass
        self.enemies.clear()
        self.tracers.clear()
        self.blotches.clear()
        try:
            self.combat_effects.clear()
        except Exception:
            self.combat_effects = []
        self.chunks.clear()
        self.chunk_obstacles.clear()
        self.chunk_enemy_seeds.clear()
        self.generate_city_around_player(force=True)

    def self_test_exit(self, task):
        self.userExit()
        return Task.done

    def get_move_input(self):
        move = Vec2(0, 0)
        if self.keys.get("w"):
            move.y += 1
        if self.keys.get("s"):
            move.y -= 1
        if self.keys.get("a"):
            move.x -= 1
        if self.keys.get("d"):
            move.x += 1
        if self.gamepad:
            lx = self.gamepad.findAxis(InputDevice.Axis.left_x)
            ly = self.gamepad.findAxis(InputDevice.Axis.left_y)
            if lx:
                move.x += lx.value
            if ly:
                move.y += -ly.value
        if move.lengthSquared() > 1.0:
            move.normalize()
        return move

    def handle_look(self, dt):
        if self.menu_open or HEADLESS_TEST:
            return
        if self.win is None or self.win.getXSize() <= 0 or self.win.getYSize() <= 0:
            return
        if not hasattr(self.win, "getPointer"):
            return
        cx = self.win.getXSize() // 2
        cy = self.win.getYSize() // 2
        md = self.win.getPointer(0)
        dx = md.getX() - cx
        dy = md.getY() - cy
        self.yaw -= dx * self.game_cfg.mouse_sensitivity
        self.pitch = max(-85.0, min(85.0, self.pitch - dy * self.game_cfg.mouse_sensitivity))
        if self.gamepad:
            rx = self.gamepad.findAxis(InputDevice.Axis.right_x)
            ry = self.gamepad.findAxis(InputDevice.Axis.right_y)
            gx = rx.value if rx else 0.0
            gy = ry.value if ry else 0.0
            if abs(gx) > 0.12:
                self.yaw -= gx * self.game_cfg.controller_look_sensitivity * dt
            if abs(gy) > 0.12:
                self.pitch = max(-85.0, min(85.0, self.pitch + gy * self.game_cfg.controller_look_sensitivity * dt))
        self.camera.setHpr(self.yaw, self.pitch, 0)
        self.recenter_mouse()

    def shoot(self):
        if not self.current_weapon:
            return
        start = self.camera.getPos(self.render)
        forward = self.camera.getQuat(self.render).getForward()
        best_dist = self.current_weapon.range
        hit_enemy = None
        hit_box = None
        hit_point = start + forward * best_dist
        hit_normal = Vec3(0, 0, 1)

        for _ in range(self.current_weapon.projectiles):
            spread_x = math.radians(random.uniform(-self.current_weapon.spread, self.current_weapon.spread))
            spread_y = math.radians(random.uniform(-self.current_weapon.spread, self.current_weapon.spread))
            direction = Vec3(forward)
            direction += self.camera.getQuat(self.render).getRight() * math.tan(spread_x)
            direction += self.camera.getQuat(self.render).getUp() * math.tan(spread_y)
            direction.normalize()
            pellet_best = self.current_weapon.range
            pellet_enemy = None
            pellet_box = None
            pellet_point = start + direction * pellet_best
            pellet_normal = Vec3(0, 0, 1)

            for enemy in self.enemies:
                if enemy.dead:
                    continue
                bounds = enemy.bounds()
                t = self.ray_box_intersection(start, direction, bounds)
                if t is not None and t < pellet_best:
                    pellet_best = t
                    pellet_enemy = enemy
                    pellet_box = None
                    pellet_point = start + direction * t
                    pellet_normal = -direction

            objective_hit = self.check_objective_shot(start, direction, pellet_best)
            objective_node = None
            if objective_hit is not None:
                pellet_best, pellet_point, objective_node = objective_hit
                pellet_enemy = None
                pellet_box = None
                pellet_normal = -direction

            nearby_boxes = []
            csize = self.game_cfg.chunk_size
            px = int(math.floor(start.x / csize))
            py = int(math.floor(start.y / csize))
            for cx in range(px - 5, px + 6):
                for cy in range(py - 5, py + 6):
                    nearby_boxes.extend(self.chunk_obstacles.get((cx, cy), []))
            for box in nearby_boxes:
                t = self.ray_box_intersection(start, direction, box)
                if t is not None and 0.1 < t < pellet_best:
                    pellet_best = t
                    pellet_enemy = None
                    pellet_box = box
                    pellet_point = start + direction * t
                    pellet_normal = self.estimate_box_normal(pellet_point, box)

            self.tracers.append(TracerEffect(self, start + self.camera.getQuat(self.render).getRight() * 0.12 - self.camera.getQuat(self.render).getUp() * 0.08, pellet_point, self.current_weapon.tracer_time))
            if objective_node is not None:
                self.recover_signal_node(objective_node, method="fire")
            elif pellet_enemy:
                pellet_enemy.hit(self.current_weapon.damage, pellet_point, pellet_normal)
            elif pellet_box and random.random() < 0.2:
                self.blotches.append(InkBlotch(self, pellet_point, pellet_normal))

            if pellet_best < best_dist:
                best_dist = pellet_best
                hit_enemy = pellet_enemy
                hit_box = pellet_box
                hit_point = pellet_point
                hit_normal = pellet_normal

        self.pitch = max(-85.0, min(85.0, self.pitch + self.current_weapon.recoil * 0.18))
        self.camera.setP(self.pitch)

    def estimate_box_normal(self, point: Vec3, box: BoxBounds):
        eps = 0.15
        candidates = [
            (abs(point.x - box.min_v.x), Vec3(-1, 0, 0)),
            (abs(point.x - box.max_v.x), Vec3(1, 0, 0)),
            (abs(point.y - box.min_v.y), Vec3(0, -1, 0)),
            (abs(point.y - box.max_v.y), Vec3(0, 1, 0)),
            (abs(point.z - box.min_v.z), Vec3(0, 0, -1)),
            (abs(point.z - box.max_v.z), Vec3(0, 0, 1)),
        ]
        candidates.sort(key=lambda item: item[0])
        return candidates[0][1] if candidates else box.normal_hint

    def ray_box_intersection(self, origin: Vec3, direction: Vec3, box: BoxBounds):
        tmin = -1e9
        tmax = 1e9
        for axis in range(3):
            o = origin[axis]
            d = direction[axis]
            mn = box.min_v[axis]
            mx = box.max_v[axis]
            if abs(d) < 1e-6:
                if o < mn or o > mx:
                    return None
                continue
            inv = 1.0 / d
            t1 = (mn - o) * inv
            t2 = (mx - o) * inv
            if t1 > t2:
                t1, t2 = t2, t1
            tmin = max(tmin, t1)
            tmax = min(tmax, t2)
            if tmin > tmax:
                return None
        if tmax < 0:
            return None
        return tmin if tmin >= 0 else tmax

    def update_player(self, dt):
        move = self.get_move_input()
        if not self.menu_open:
            self.handle_look(dt)
        quat = self.camera.getQuat(self.render)
        forward = quat.getForward()
        right = quat.getRight()
        forward.z = 0
        right.z = 0
        if forward.lengthSquared() > 0:
            forward.normalize()
        if right.lengthSquared() > 0:
            right.normalize()
        move_vec = (forward * move.y + right * move.x)
        if move_vec.lengthSquared() > 1.0:
            move_vec.normalize()
        speed = self.game_cfg.sprint_speed if self.keys.get("shift") else self.game_cfg.walk_speed
        candidate = Vec3(self.player_pos)
        candidate.x += move_vec.x * speed * dt
        if not self.point_hits_obstacle(candidate, self.game_cfg.player_radius, self.game_cfg.player_height):
            self.player_pos.x = candidate.x
        candidate = Vec3(self.player_pos)
        candidate.y += move_vec.y * speed * dt
        if not self.point_hits_obstacle(candidate, self.game_cfg.player_radius, self.game_cfg.player_height):
            self.player_pos.y = candidate.y

        if self.on_ground and self.keys.get("space"):
            self.vertical_speed = self.game_cfg.jump_speed
            self.on_ground = False
        self.vertical_speed -= self.game_cfg.gravity * dt
        self.player_pos.z += self.vertical_speed * dt
        if self.player_pos.z <= self.game_cfg.player_height:
            self.player_pos.z = self.game_cfg.player_height
            self.vertical_speed = 0.0
            self.on_ground = True

        self.camera.setPos(self.player_pos)

    def update_fire(self, dt):
        if self.gamepad:
            trigger = self.gamepad.findAxis(InputDevice.Axis.right_trigger)
            fire = trigger.value > 0.35 if trigger else False
            if fire and not self.gamepad_fire_prev:
                self.fire_down = True
            self.fire_hold = self.fire_hold or fire
            self.gamepad_fire_prev = fire
        self.fire_cooldown -= dt
        if (self.fire_hold or self.fire_down) and self.fire_cooldown <= 0.0 and not self.menu_open:
            self.shoot()
            self.fire_cooldown = self.current_weapon.fire_interval if self.current_weapon else 0.15
        self.fire_down = False
        if self.current_weapon and self.current_weapon.fire_interval > 0.16:
            self.fire_hold = False

    def update_enemies(self, dt):
        player_pos = Vec3(self.player_pos.x, self.player_pos.y, 0)
        for enemy in list(self.enemies):
            alive = enemy.update(dt, player_pos)
            if not alive:
                self.enemies.remove(enemy)
                continue
            dist = (enemy.root.getPos() - player_pos).length()
            if dist < 1.8 and getattr(enemy, "contact_cooldown", 0.0) <= 0.0:
                self.apply_enemy_contact_damage(enemy)
                enemy.contact_cooldown = 0.72
        if self.health <= 0:
            self.health = self.game_cfg.default_health
            self.player_pos = Vec3(0, 0, self.game_cfg.player_height)
            self.center_text["text"] = "You were consumed by the linework. Resetting position."
            self.weapon_banner_time = max(self.weapon_banner_time, 2.0)

    def recolor_scene(self):
        color = self.current_line_color(alpha=0.95)
        for chunk in self.chunks.values():
            chunk.setColor(*color)
        for enemy in self.enemies:
            if not enemy.dead:
                if getattr(enemy, "hit_flash", 0.0) > 0.0 or getattr(enemy, "spawn_age", 1.0) < getattr(enemy, "spawn_delay", 0.0):
                    continue
                enemy.body.setColor(*self.current_line_color(alpha=0.98))
        for blotch in self.blotches:
            blotch.base.setColor(*self.current_line_color(alpha=0.9))
        try:
            if getattr(self, "return_trail", None) is not None and not self.return_trail.isEmpty():
                pulse = 0.56 + 0.18 * math.sin(float(getattr(self, "elapsed", 0.0)) * 4.0)
                self.return_trail.setColorScale(*self.signal_accent_color(alpha=pulse))
        except Exception:
            pass

    def update_effects(self, dt):
        active_tracers = []
        for tracer in self.tracers:
            if tracer.update(dt):
                active_tracers.append(tracer)
        self.tracers = active_tracers
        active_blotches = []
        for blotch in self.blotches:
            if blotch.update(dt):
                active_blotches.append(blotch)
        self.blotches = active_blotches
        active_signal_effects = []
        for effect in list(getattr(self, "signal_effects", []) or []):
            try:
                if effect.update(dt):
                    active_signal_effects.append(effect)
            except Exception:
                try:
                    effect.dispose()
                except Exception:
                    pass
        self.signal_effects = active_signal_effects
        active_combat_effects = []
        for effect in list(getattr(self, "combat_effects", []) or []):
            try:
                if effect.update(dt):
                    active_combat_effects.append(effect)
            except Exception:
                try:
                    effect.dispose()
                except Exception:
                    pass
        self.combat_effects = active_combat_effects
        self.prune_runtime_entities()

    def prune_runtime_entities(self):
        def cap_list(items, max_count):
            max_count = max(0, int(max_count))
            overflow = len(items) - max_count
            if overflow <= 0:
                return items
            for item in items[:overflow]:
                dispose = getattr(item, "dispose", None)
                if callable(dispose):
                    dispose()
            return items[overflow:]

        self.tracers = cap_list(self.tracers, self.game_cfg.max_tracers)
        self.blotches = cap_list(self.blotches, self.game_cfg.max_blotches)
        self.signal_effects = cap_list(list(getattr(self, "signal_effects", []) or []), getattr(self.game_cfg, "objective_pulse_budget", 18))
        self.combat_effects = cap_list(list(getattr(self, "combat_effects", []) or []), getattr(self.game_cfg, "max_combat_effects", 28))

        player_xy = Vec3(self.player_pos.x, self.player_pos.y, 0)
        enemy_retire_sq = float(self.game_cfg.enemy_retire_distance) ** 2
        kept_enemies = []
        for enemy in self.enemies:
            if enemy.dead:
                enemy.dispose()
                continue
            try:
                enemy_xy = enemy.root.getPos()
                enemy_xy.z = 0
                if (enemy_xy - player_xy).lengthSquared() > enemy_retire_sq:
                    enemy.dispose()
                    continue
            except Exception:
                enemy.dispose()
                continue
            kept_enemies.append(enemy)
        if len(kept_enemies) > self.game_cfg.max_enemies:
            kept_enemies.sort(key=lambda e: (e.root.getPos() - player_xy).lengthSquared())
            for enemy in kept_enemies[int(self.game_cfg.max_enemies):]:
                enemy.dispose()
            kept_enemies = kept_enemies[:int(self.game_cfg.max_enemies)]
        self.enemies = kept_enemies

        effect_retire_sq = float(self.game_cfg.effect_retire_distance) ** 2
        kept_blotches = []
        for blotch in self.blotches:
            try:
                blotch_xy = blotch.root.getPos()
                blotch_xy.z = 0
                if (blotch_xy - player_xy).lengthSquared() > effect_retire_sq:
                    blotch.dispose()
                    continue
            except Exception:
                blotch.dispose()
                continue
            kept_blotches.append(blotch)
        self.blotches = kept_blotches

    def update_feedback_overlays(self, dt: float) -> None:
        self.damage_feedback_time = max(0.0, float(getattr(self, "damage_feedback_time", 0.0) or 0.0) - dt)
        self.hit_feedback_time = max(0.0, float(getattr(self, "hit_feedback_time", 0.0) or 0.0) - dt)
        try:
            if self.damage_feedback_time > 0.0:
                alpha = 0.68 + 0.22 * math.sin(self.elapsed * 34.0)
                color = self.warning_accent_color(alpha=max(0.35, min(0.95, alpha)))
                scale = 1.28
            elif self.hit_feedback_time > 0.0:
                color = self.signal_accent_color(alpha=0.90)
                scale = 1.16
            else:
                color = self.current_line_color(alpha=0.88)
                scale = 1.0
            self.crosshair.setScale(scale)
            for line in getattr(self, "crosshair_lines", []) or []:
                line.setColor(*color)
        except Exception:
            pass

    def chunk_task(self, task):
        self.generate_city_around_player()
        return Task.again

    def update_task(self, task):
        if getattr(self, "_shutting_down", False):
            return Task.done
        dt = min(0.033, globalClock.getDt())
        self.elapsed += dt
        self.update_palette(dt)
        self.update_player(dt)
        self.update_fire(dt)
        self.update_enemies(dt)
        self.update_signal_objectives(dt)
        self.update_effects(dt)
        self.update_feedback_overlays(dt)
        self.recolor_scene()
        self.refresh_ui_text()
        self.refresh_workstation_text()
        if self.weapon_banner_time > 0.0 and self.current_weapon:
            self.weapon_banner_time -= dt
            self.center_text["text"] = f"{self.current_weapon.name}"
        elif getattr(self, "objective_banner_time", 0.0) > 0.0:
            self.center_text["text"] = str(getattr(self, "objective_banner", ""))
        else:
            self.center_text["text"] = ""
        return Task.cont

    def cleanup_runtime(self):
        if getattr(self, "_shutting_down", False):
            return
        self._shutting_down = True
        for task_name in ("update-task", "chunk-task", "self-test-exit"):
            try:
                self.taskMgr.remove(task_name)
            except Exception:
                pass
        for enemy in list(getattr(self, "enemies", [])):
            enemy.dispose()
        for tracer in list(getattr(self, "tracers", [])):
            tracer.dispose()
        for blotch in list(getattr(self, "blotches", [])):
            blotch.dispose()
        for effect in list(getattr(self, "signal_effects", []) or []):
            try:
                effect.dispose()
            except Exception:
                pass
        for effect in list(getattr(self, "combat_effects", []) or []):
            try:
                effect.dispose()
            except Exception:
                pass
        self.enemies.clear()
        self.tracers.clear()
        self.blotches.clear()
        try:
            self.signal_effects.clear()
        except Exception:
            self.signal_effects = []
        try:
            self.combat_effects.clear()
        except Exception:
            self.combat_effects = []
        for np in list(getattr(self, "chunks", {}).values()):
            try:
                np.removeNode()
            except Exception:
                pass
        self.chunks.clear()
        self.chunk_obstacles.clear()
        self.chunk_enemy_seeds.clear()
        if getattr(self, "return_trail", None) is not None:
            try:
                if not self.return_trail.isEmpty():
                    self.return_trail.removeNode()
            except Exception:
                pass
            self.return_trail = None
        for node in list(getattr(self, "objective_nodes", []) or []):
            try:
                node.dispose()
            except Exception:
                pass
        try:
            self.objective_nodes.clear()
        except Exception:
            self.objective_nodes = []
        for node in (getattr(self, "extraction_node", None),):
            try:
                if node is not None:
                    node.dispose()
            except Exception:
                pass
        self.extraction_node = None
        for attr in ("hud_root", "mission_overlay_root", "crosshair", "menu_root", "work_root", "mission_root", "city_root", "entity_root", "effect_root"):
            node = getattr(self, attr, None)
            try:
                if node is not None:
                    if hasattr(node, "destroy"):
                        node.destroy()
                    elif hasattr(node, "removeNode") and not node.isEmpty():
                        node.removeNode()
            except Exception:
                pass
        try:
            texture = getattr(self, "_blotch_texture", None)
            if texture is not None:
                TexturePool.releaseTexture(texture)
            self._blotch_texture = None
        except Exception:
            pass

    def userExit(self):
        self.cleanup_runtime()
        try:
            return super().userExit()
        except Exception:
            raise SystemExit(0)


def run_runtime_smoke():
    ensure_dirs()
    app = EtchlineGame()
    report = {"schema": 2, "kind": "etchline_runtime_budget_smoke", "phase": "start", "status": "RUNNING", "initial": app.runtime_budget_report()}
    try:
        # Exercise chunk streaming, shooting, effect aging, menu pause, and cleanup
        # without relying on a visible window. This proves resource counts stay
        # under budget after movement and effect churn.
        path_points = [
            Vec3(0, 0, app.game_cfg.player_height),
            Vec3(96, 0, app.game_cfg.player_height),
            Vec3(160, 80, app.game_cfg.player_height),
            Vec3(-128, 64, app.game_cfg.player_height),
            Vec3(0, 0, app.game_cfg.player_height),
        ]
        for point in path_points:
            app.player_pos = Vec3(point)
            app.camera.setPos(app.player_pos)
            app.generate_city_around_player(force=True)
            for _ in range(4):
                app.fire_down = True
                app.update_fire(0.12)
                app.update_effects(0.12)
                app.taskMgr.step()
        app.toggle_menu()
        for _ in range(3):
            app.taskMgr.step()
        report["menu_open_after_toggle"] = bool(app.menu_open)
        app.toggle_menu()
        for _ in range(24):
            app.update_effects(0.25)
            app.prune_runtime_entities()
            app.taskMgr.step()
        report["after_churn"] = app.runtime_budget_report()
        try:
            from panda3d.core import Filename
            shot_path = LOG_DIR / "etchline_runtime_smoke.png"
            for _ in range(2):
                app.graphicsEngine.renderFrame()
            ok = app.win.saveScreenshot(Filename(str(shot_path))) if app.win is not None else False
            report["screenshot_saved"] = bool(ok and shot_path.exists())
            report["screenshot"] = str(shot_path)
        except Exception as exc:
            report["screenshot_saved"] = False
            report["screenshot_error"] = f"{exc.__class__.__name__}:{exc}"
        report["phase"] = "complete"
        report["within_budget"] = bool(report["after_churn"].get("within_budget"))
        report["status"] = "PASS" if report.get("within_budget") and report.get("screenshot_saved") else "FAIL"
    finally:
        app.cleanup_runtime()
        for _ in range(2):
            try:
                app.taskMgr.step()
            except Exception:
                break
        report["after_cleanup"] = app.runtime_budget_report()
        try:
            app.destroy()
        except Exception:
            pass
    report_path = LOG_DIR / "runtime_budget_smoke_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    if report.get("status") != "PASS":
        raise SystemExit(2)


def main():
    if SELF_TEST:
        run_lightweight_self_test()
        return
    if RUNTIME_SMOKE:
        run_runtime_smoke()
        return
    app = EtchlineGame()
    app.run()


if __name__ == "__main__":
    main()
