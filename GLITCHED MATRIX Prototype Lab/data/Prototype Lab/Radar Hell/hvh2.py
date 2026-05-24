#!/usr/bin/env python3
"""
Heaven vs Hell RTS (Side-View, Pixel Art)
Bosch-inspired ancient cosmic battlefield with replaceable assets.

Features
- 50 angels vs 50 demons in realtime combat
- Neutral purgatory center band
- Procedurally generated tiny pixel sprites with per-pixel shading
- Replaceable assets folder (backgrounds, overlays, sprites, sfx)
- Angels fire golden arrows; demons cast fireballs
- Attack SFX + ambient background loop
- 16:9 pipeline from 1080p to 4K (fullscreen/windowed/resizable)
- Crash reporter, help menu (H), graphics/performance/audio controls
"""

from __future__ import annotations

import argparse
import math
import random
import sys
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Tuple, Dict

import pygame

# -----------------------------
# Crash reporting
# -----------------------------


def setup_crash_reporter() -> None:
    """Install a global crash reporter to persist uncaught exceptions."""

    def _hook(exc_type, exc_value, exc_tb):
        stamp = time.strftime("%Y%m%d_%H%M%S")
        report_dir = Path("crash_reports")
        report_dir.mkdir(exist_ok=True)
        report_path = report_dir / f"crash_{stamp}.log"
        with report_path.open("w", encoding="utf-8") as file:
            file.write("Heaven vs Hell RTS Crash Report\n")
            file.write(f"Timestamp: {time.ctime()}\n")
            file.write(f"Python: {sys.version}\n")
            file.write(f"Platform: {sys.platform}\n")
            file.write("\nTraceback:\n")
            traceback.print_exception(exc_type, exc_value, exc_tb, file=file)
        print(f"\n[CRASH] Unhandled exception. Report written to: {report_path}", file=sys.stderr)
        traceback.print_exception(exc_type, exc_value, exc_tb)

    sys.excepthook = _hook


# -----------------------------
# Configuration
# -----------------------------

BASE_W, BASE_H = 3840, 2160
TARGET_ASPECT = 16 / 9
INITIAL_UNITS_PER_SIDE = 50
SPAWN_MARGIN_X = 90
PURGATORY_BAND = 150
DEFAULT_SPRITE_SIZE = (16, 16)
DEFAULT_BOSS_SPRITE_SIZE = (22, 22)
BOSSES_PER_SIDE = 14

TEAM_HEAVEN = "heaven"
TEAM_HELL = "hell"

TEXT_COLOR = (238, 231, 215)
PANEL_BG = (16, 12, 10, 220)

ASSETS_ROOT = Path("assets")
BACKGROUND_PATH = ASSETS_ROOT / "backgrounds" / "battle_background.png"
OVERLAY_PATH = ASSETS_ROOT / "overlays" / "battle_overlay.png"
ANGEL_SPRITE_DIR = ASSETS_ROOT / "sprites" / "angels"
ANGEL_BOSS_SPRITE_DIR = ANGEL_SPRITE_DIR / "bosses"
DEMON_SPRITE_DIR = ASSETS_ROOT / "sprites" / "demons"
DEMON_BOSS_SPRITE_DIR = DEMON_SPRITE_DIR / "bosses"
SFX_DIR = ASSETS_ROOT / "sfx"
ANGEL_SHOT_MP3 = SFX_DIR / "angel_arrow.mp3"
DEMON_SHOT_MP3 = SFX_DIR / "demon_fireball.mp3"
AMBIENCE_MP3 = SFX_DIR / "ambient_loop.mp3"
ANGEL_POWER_MP3 = SFX_DIR / "angel_power.mp3"
DEMON_POWER_MP3 = SFX_DIR / "demon_power.mp3"
BOSS_RING_MP3 = SFX_DIR / "boss_ring.mp3"
ANGEL_LIGHTNING_MP3 = SFX_DIR / "angel_lightning.mp3"
DEMON_BAT_MP3 = SFX_DIR / "demon_bat_swarm.mp3"
EFFECTS_DIR = ASSETS_ROOT / "effects"
LIGHTNING_FX_PNG = EFFECTS_DIR / "lightning_fork.png"
BAT_FX_PNG = EFFECTS_DIR / "bat_swarm.png"
RING_FX_PNG = EFFECTS_DIR / "light_ring.png"
SHADOW_FX_PNG = EFFECTS_DIR / "shadow_boost.png"
ANGEL_ULTIMATE_FX_PNG = EFFECTS_DIR / "angel_ultimate.png"
DEMON_ULTIMATE_FX_PNG = EFFECTS_DIR / "demon_ultimate.png"
ANGEL_DEATH_FX_PNG = EFFECTS_DIR / "angel_death.png"
DEMON_DEATH_FX_PNG = EFFECTS_DIR / "demon_death.png"
GOD_DEATH_FX_PNG = EFFECTS_DIR / "god_death.png"
ANGEL_ULTIMATE_MP3 = SFX_DIR / "angel_ultimate.mp3"
DEMON_ULTIMATE_MP3 = SFX_DIR / "demon_ultimate.mp3"
MONSTERS_DIR = ASSETS_ROOT / "monsters"
SATAN_PNG = MONSTERS_DIR / "satan.png"
GOD_PNG = MONSTERS_DIR / "god.png"
SATAN_LOOP_MP3 = SFX_DIR / "satan_loop.mp3"
GOD_LIGHTNING_MP3 = SFX_DIR / "god_lightning.mp3"
ANGEL_DEATH_MP3 = SFX_DIR / "angel_death.mp3"
DEMON_DEATH_MP3 = SFX_DIR / "demon_death.mp3"
GOD_DEATH_MP3 = SFX_DIR / "god_death.mp3"
SATAN_DEATH_MP3 = SFX_DIR / "satan_death.mp3"
UI_DIR = ASSETS_ROOT / "ui"
EARTH_ICON_PNG = UI_DIR / "earth_icon.png"
ASSET_README = ASSETS_ROOT / "README.txt"


# -----------------------------
# Utility
# -----------------------------


def clamp(value: float, low: float, high: float) -> float:
    return low if value < low else high if value > high else value


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def draw_vertical_gradient(
    surface: pygame.Surface,
    rect: pygame.Rect,
    top: Tuple[int, int, int],
    bottom: Tuple[int, int, int],
) -> None:
    height = max(1, rect.height)
    for y_off in range(height):
        t = y_off / (height - 1) if height > 1 else 0.0
        color = (
            int(lerp(top[0], bottom[0], t)),
            int(lerp(top[1], bottom[1], t)),
            int(lerp(top[2], bottom[2], t)),
        )
        y = rect.top + y_off
        pygame.draw.line(surface, color, (rect.left, y), (rect.right, y))


def shade_rgb(color: Tuple[int, int, int], amount: int) -> Tuple[int, int, int]:
    return tuple(int(clamp(c + amount, 0, 255)) for c in color)


# -----------------------------
# Entities
# -----------------------------


@dataclass
class Projectile:
    x: float
    y: float
    vx: float
    vy: float
    damage: float
    team: str
    radius: int
    color: Tuple[int, int, int]
    ttl: float
    kind: str = "basic"
    homing: float = 0.0
    health: float = 1.0

    def update(self, dt: float) -> bool:
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.ttl -= dt
        return self.ttl > 0


@dataclass
class VisualEffect:
    points: Tuple[Tuple[int, int], ...]
    color: Tuple[int, int, int]
    ttl: float
    texture_key: str = "ring"
    pos: Tuple[int, int] = (0, 0)
    radius: int = 18
    shadow: bool = False



@dataclass
class UnitAIStats:
    shots: int = 0
    hits: int = 0
    aggression: float = 0.5
    aim_jitter: float = 0.14

    def learn(self) -> None:
        if self.shots >= 8:
            hit_rate = self.hits / max(1, self.shots)
            if hit_rate > 0.45:
                self.aggression = clamp(self.aggression + 0.03, 0.2, 0.95)
                self.aim_jitter = clamp(self.aim_jitter - 0.01, 0.03, 0.25)
            else:
                self.aggression = clamp(self.aggression - 0.02, 0.2, 0.95)
                self.aim_jitter = clamp(self.aim_jitter + 0.008, 0.03, 0.25)
            self.shots = 0
            self.hits = 0


@dataclass
class Unit:
    uid: int
    team: str
    x: float
    y: float
    hp: float
    max_hp: float
    speed: float
    attack_range: float
    cooldown: float
    projectile_speed: float
    damage: float
    sprite_right: pygame.Surface
    sprite_left: pygame.Surface
    ai: UnitAIStats = field(default_factory=UnitAIStats)
    shoot_timer: float = 0.0
    ability_timer: float = 0.0
    ultimate_timer: float = 0.0
    neutral: bool = True
    facing_right: bool = True
    is_boss: bool = False

    def is_alive(self) -> bool:
        return self.hp > 0


# -----------------------------
# Main game
# -----------------------------


class HeavenHellRTS:
    def __init__(
        self,
        window_size: tuple[int, int] | None = None,
        fullscreen: bool = False,
        host_mode: bool = False,
        return_to_host_on_escape: bool = False,
        return_to_host_on_battle_end: bool = False,
        vsync: int = 1,
    ) -> None:
        pygame.init()
        pygame.display.set_caption("Heaven vs Hell RTS - Ancient Pixel War")

        self.host_mode = bool(host_mode)
        self.return_to_host_on_escape = bool(return_to_host_on_escape)
        self.return_to_host_on_battle_end = bool(return_to_host_on_battle_end)
        self.fullscreen = bool(fullscreen)
        self.vsync = int(vsync)
        self.pixel_scale = 2
        self.max_fps = 120
        self.show_help = True
        self.show_ui = True
        self.help_auto_hide = True
        self.audio_enabled = True
        self.zoom = 1.0
        self.camera_x = 0.0
        self.camera_y = 0.0
        self.camera_track_uid: int | None = None
        self.overlay_scroll = 0.0

        self.window_size = tuple(window_size or (1920, 1080))
        if self.fullscreen:
            self.screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN, vsync=self.vsync)
        else:
            self.screen = pygame.display.set_mode(self.window_size, pygame.RESIZABLE, vsync=self.vsync)

        self.internal_surface = pygame.Surface((BASE_W // self.pixel_scale, BASE_H // self.pixel_scale)).convert_alpha()
        self.background_surface = pygame.Surface(self.internal_surface.get_size()).convert_alpha()
        self.overlay_surface = pygame.Surface(self.internal_surface.get_size(), pygame.SRCALPHA)
        self.effect_surface = pygame.Surface(self.internal_surface.get_size(), pygame.SRCALPHA)

        self.clock = pygame.time.Clock()
        self.font_small = pygame.font.SysFont("consolas", 16)
        self.font_medium = pygame.font.SysFont("consolas", 22, bold=True)

        self.units: List[Unit] = []
        self.projectiles: List[Projectile] = []
        self.effects: List[VisualEffect] = []
        self.fallen_angels: List[Unit] = []
        self.fallen_demons: List[Unit] = []
        self.fallen_angel_bosses: List[Unit] = []
        self.fallen_demon_bosses: List[Unit] = []
        self.boss_respawn_queue: List[Tuple[float, Unit]] = []
        self.next_uid = 1

        self.last_fps = 0.0
        self.last_frame_time = 0.0
        self.start_time = time.time()
        self.last_sfx_time = 0.0

        self.angel_sprite_bank: List[pygame.Surface] = []
        self.angel_boss_sprite_bank: List[pygame.Surface] = []
        self.demon_sprite_bank: List[pygame.Surface] = []
        self.demon_boss_sprite_bank: List[pygame.Surface] = []

        self.angel_shot_sound: pygame.mixer.Sound | None = None
        self.demon_shot_sound: pygame.mixer.Sound | None = None
        self.ambient_sound: pygame.mixer.Sound | None = None
        self.angel_power_sound: pygame.mixer.Sound | None = None
        self.demon_power_sound: pygame.mixer.Sound | None = None
        self.boss_ring_sound: pygame.mixer.Sound | None = None
        self.angel_lightning_sound: pygame.mixer.Sound | None = None
        self.demon_bat_sound: pygame.mixer.Sound | None = None
        self.angel_ultimate_sound: pygame.mixer.Sound | None = None
        self.demon_ultimate_sound: pygame.mixer.Sound | None = None
        self.vfx_textures: Dict[str, pygame.Surface] = {}
        self.winner: str | None = None
        self.satan_sprite = pygame.Surface((560, 460), pygame.SRCALPHA)
        self.satan_sound: pygame.mixer.Sound | None = None
        self.god_power_sound: pygame.mixer.Sound | None = None
        self.angel_death_sound: pygame.mixer.Sound | None = None
        self.demon_death_sound: pygame.mixer.Sound | None = None
        self.god_death_sound: pygame.mixer.Sound | None = None
        self.satan_death_sound: pygame.mixer.Sound | None = None
        self.satan_x = 0.0
        self.satan_dir = 1.0
        self.satan_timer = 0.0
        self.satan_meteor_mode = False
        self.satan_meteor_timer = 0.0
        self.final_boss_mode = False
        self.satan_boss_hp = 0.0
        self.satan_boss_max_hp = 0.0
        self.god_hp = 0.0
        self.god_max_hp = 0.0
        self.god_x = 0.0
        self.god_y = 0.0
        self.god_attack_timer = 0.0
        self.satan_attack_timer = 0.0
        self.god_ultimate_timer = 0.0
        self.satan_ultimate_timer = 0.0
        self.final_boss_timer = 0.0
        self.screen_shake_timer = 0.0
        self.screen_shake_intensity = 0.0
        self.ai_level = 1.0
        self.heaven_wrath_timer = 0.0
        self.earth_icon = pygame.Surface((84, 84), pygame.SRCALPHA)
        self.god_sprite = pygame.Surface((160, 160), pygame.SRCALPHA)
        self.round_reset_timer = 0.0
        self.regular_respawn_timer = 0.0
        self.host_fade_alpha = 0.0
        self.pending_host_return = False

        self._init_audio()
        self.ensure_assets_exist()
        self.reload_assets()
        self.reset_battle()

    @property
    def world_size(self) -> Tuple[int, int]:
        return self.internal_surface.get_size()

    # ---------- setup ----------

    def _init_audio(self) -> None:
        try:
            pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
            pygame.mixer.set_num_channels(16)
        except pygame.error:
            self.audio_enabled = False

    def _uid(self) -> int:
        uid = self.next_uid
        self.next_uid += 1
        return uid

    def reset_battle(self) -> None:
        self.units.clear()
        self.projectiles.clear()
        self.effects.clear()
        self.fallen_angels.clear()
        self.fallen_demons.clear()
        self.fallen_angel_bosses.clear()
        self.fallen_demon_bosses.clear()
        self.boss_respawn_queue.clear()
        self.winner = None
        self.next_uid = 1
        self.camera_track_uid = None
        self.camera_x = 0.0
        self.camera_y = 0.0
        self.show_help = True
        self.help_auto_hide = True

        world_w, world_h = self.world_size
        center_y = world_h / 2

        heaven_regular_count = len(self.angel_sprite_bank) if self.angel_sprite_bank else 14
        hell_regular_count = len(self.demon_sprite_bank) if self.demon_sprite_bank else 14
        self.units.extend(self._spawn_team(TEAM_HEAVEN, heaven_regular_count, 36, center_y - PURGATORY_BAND / 2 - 30))
        self.units.extend(self._spawn_team(TEAM_HELL, hell_regular_count, center_y + PURGATORY_BAND / 2 + 30, world_h - 36))

        # Boss ranks spawn behind their faction formations.
        heaven_boss_count = len(self.angel_boss_sprite_bank) if self.angel_boss_sprite_bank else BOSSES_PER_SIDE
        hell_boss_count = len(self.demon_boss_sprite_bank) if self.demon_boss_sprite_bank else BOSSES_PER_SIDE
        self.units.extend(self._spawn_boss_team(TEAM_HEAVEN, heaven_boss_count, 10, max(14, center_y - PURGATORY_BAND / 2 - 130)))
        self.units.extend(self._spawn_boss_team(TEAM_HELL, hell_boss_count, min(world_h - 14, center_y + PURGATORY_BAND / 2 + 130), world_h - 10))

        self.satan_x = world_w * 0.5
        self.satan_dir = 1.0
        self.satan_timer = 0.0
        self.satan_meteor_mode = False
        self.satan_meteor_timer = 0.0
        self.heaven_wrath_timer = 0.0
        self.round_reset_timer = 0.0
        self.regular_respawn_timer = 0.0
        self.final_boss_mode = False
        self.satan_boss_max_hp = 620.0
        self.satan_boss_hp = self.satan_boss_max_hp
        self.god_max_hp = 620.0
        self.god_hp = self.god_max_hp
        self.god_attack_timer = 0.0
        self.satan_attack_timer = 0.0
        self.god_ultimate_timer = 0.0
        self.satan_ultimate_timer = 0.0
        self.final_boss_timer = 0.0
        self.screen_shake_timer = 0.0
        self.screen_shake_intensity = 0.0
        self.god_x = world_w * 0.5
        self.god_y = center_y - 130

    def _tint_demon_sprite(self, sprite: pygame.Surface) -> pygame.Surface:
        """Apply a subtle demon tint without coloring transparent square padding."""
        tinted = sprite.copy()
        # Multiply keeps transparent pixels transparent (no red square bleed).
        tinted.fill((232, 170, 170, 255), special_flags=pygame.BLEND_RGBA_MULT)
        # Small additive warmth to preserve demon identity while keeping true sprite silhouette.
        tinted.fill((18, 0, 0, 0), special_flags=pygame.BLEND_RGBA_ADD)
        return tinted

    def _apply_ai_level(self, unit: Unit) -> None:
        lvl = max(1.0, self.ai_level)
        base_aggression = 0.58
        unit.ai.aggression = clamp(base_aggression + (lvl - 1.0) * 0.16, 0.25, 0.98)
        unit.ai.aim_jitter = clamp(0.12 - (lvl - 1.0) * 0.015, 0.02, 0.25)

    def _spawn_team(self, team: str, count: int, y_min: float, y_max: float) -> List[Unit]:
        world_w, _ = self.world_size
        spawned: List[Unit] = []
        sprite_bank = self.angel_sprite_bank if team == TEAM_HEAVEN else self.demon_sprite_bank
        for i in range(count):
            x = random.uniform(SPAWN_MARGIN_X, world_w - SPAWN_MARGIN_X)
            y = random.uniform(y_min, y_max)
            if team == TEAM_HEAVEN:
                sprite = sprite_bank[i % len(sprite_bank)] if sprite_bank else self._generate_angel_sprite()
                unit = Unit(
                    uid=self._uid(),
                    team=team,
                    x=x,
                    y=y,
                    hp=170,
                    max_hp=170,
                    speed=random.uniform(68, 90),
                    attack_range=random.uniform(210, 258),
                    cooldown=random.uniform(0.80, 1.08),
                    projectile_speed=430,
                    damage=random.uniform(5.0, 8.0),
                    sprite_right=sprite,
                    sprite_left=pygame.transform.flip(sprite, True, False),
                )
            else:
                sprite = sprite_bank[i % len(sprite_bank)] if sprite_bank else self._generate_demon_sprite()
                sprite = self._tint_demon_sprite(sprite)
                unit = Unit(
                    uid=self._uid(),
                    team=team,
                    x=x,
                    y=y,
                    hp=170,
                    max_hp=170,
                    speed=random.uniform(68, 90),
                    attack_range=random.uniform(210, 258),
                    cooldown=random.uniform(0.80, 1.08),
                    projectile_speed=430,
                    damage=random.uniform(5.0, 8.0),
                    sprite_right=sprite,
                    sprite_left=pygame.transform.flip(sprite, True, False),
                )
            self._apply_ai_level(unit)
            spawned.append(unit)
        return spawned

    def _spawn_boss_team(self, team: str, count: int, y_min: float, y_max: float) -> List[Unit]:
        world_w, _ = self.world_size
        spawned: List[Unit] = []

        sprite_bank = self.angel_boss_sprite_bank if team == TEAM_HEAVEN else self.demon_boss_sprite_bank
        fallback = self._generate_angel_boss_sprite if team == TEAM_HEAVEN else self._generate_demon_boss_sprite

        for i in range(count):
            x = (i + 1) * (world_w / (count + 1))
            y = random.uniform(y_min, y_max)
            sprite = sprite_bank[i % len(sprite_bank)] if sprite_bank else fallback()
            if team == TEAM_HELL:
                sprite = self._tint_demon_sprite(sprite)

            if team == TEAM_HEAVEN:
                unit = Unit(
                    uid=self._uid(),
                    team=team,
                    x=x,
                    y=y,
                    hp=360,
                    max_hp=360,
                    speed=random.uniform(46, 60),
                    attack_range=random.uniform(270, 320),
                    cooldown=random.uniform(0.68, 0.92),
                    projectile_speed=500,
                    damage=random.uniform(10.0, 14.0),
                    sprite_right=sprite,
                    sprite_left=pygame.transform.flip(sprite, True, False),
                    is_boss=True,
                )
            else:
                unit = Unit(
                    uid=self._uid(),
                    team=team,
                    x=x,
                    y=y,
                    hp=360,
                    max_hp=360,
                    speed=random.uniform(46, 60),
                    attack_range=random.uniform(270, 320),
                    cooldown=random.uniform(0.68, 0.92),
                    projectile_speed=500,
                    damage=random.uniform(10.0, 14.0),
                    sprite_right=sprite,
                    sprite_left=pygame.transform.flip(sprite, True, False),
                    is_boss=True,
                )
            self._apply_ai_level(unit)
            spawned.append(unit)
        return spawned

    # ---------- asset management ----------

    def _ensure_placeholder_mp3(self, path: Path) -> None:
        """Write a minimal placeholder MP3-like file if missing so users can replace it later."""
        if path.exists():
            return
        # lightweight placeholder with ID3 header bytes; runtime loader tolerates invalid audio gracefully.
        path.write_bytes(b"ID3\x04\x00\x00\x00\x00\x00\x15TIT2\x00\x00\x00\x05\x00\x00demo")

    def ensure_assets_exist(self) -> None:
        """Create default assets only when missing. Never overwrite user replacements."""
        for directory in [ASSETS_ROOT, ASSETS_ROOT / "backgrounds", ASSETS_ROOT / "overlays", ANGEL_SPRITE_DIR, ANGEL_BOSS_SPRITE_DIR, DEMON_SPRITE_DIR, DEMON_BOSS_SPRITE_DIR, SFX_DIR, EFFECTS_DIR, MONSTERS_DIR, UI_DIR]:
            directory.mkdir(parents=True, exist_ok=True)

        if not ASSET_README.exists():
            ASSET_README.write_text(
                "Assets are generated once and never overwritten.\n"
                "Replace files to customize visuals/audio:\n"
                "- backgrounds/battle_background.png\n"
                "- overlays/battle_overlay.png\n"
                "- sprites/angels/*.png\n"
                "- sprites/angels/bosses/*.png\n"
                "- sprites/demons/*.png\n"
                "- sprites/demons/bosses/*.png\n"
                "- sfx/angel_arrow.mp3\n"
                "- sfx/demon_fireball.mp3\n"
                "- sfx/ambient_loop.mp3\n"
                "- sfx/angel_power.mp3\n"
                "- sfx/demon_power.mp3\n"
                "- sfx/boss_ring.mp3\n"
                "- sfx/angel_lightning.mp3\n"
                "- sfx/demon_bat_swarm.mp3\n"
                "- effects/lightning_fork.png\n"
                "- effects/bat_swarm.png\n"
                "- effects/light_ring.png\n"
                "- effects/shadow_boost.png\n"
                "- effects/angel_ultimate.png\n"
                "- effects/demon_ultimate.png\n"
                "- effects/angel_death.png\n"
                "- effects/demon_death.png\n"
                "- effects/god_death.png\n"
                "- monsters/satan.png\n"
                "- monsters/god.png\n"
                "- ui/earth_icon.png\n"
                "- sfx/satan_loop.mp3\n"
                "- sfx/god_lightning.mp3\n"
                "- sfx/angel_death.mp3\n"
                "- sfx/demon_death.mp3\n"
                "- sfx/god_death.mp3\n"
                "- sfx/satan_death.mp3\n"
                "- sfx/angel_ultimate.mp3\n"
                "- sfx/demon_ultimate.mp3\n"
                "Press L in-game to reload replaced assets.\n",
                encoding="utf-8",
            )

        if not BACKGROUND_PATH.exists():
            pygame.image.save(self._generate_background_surface(self.world_size), str(BACKGROUND_PATH))
        if not OVERLAY_PATH.exists():
            pygame.image.save(self._generate_overlay_surface(self.world_size), str(OVERLAY_PATH))

        for idx in range(14):
            sprite_path = ANGEL_SPRITE_DIR / f"angel_{idx:02d}.png"
            if not sprite_path.exists():
                pygame.image.save(self._generate_angel_sprite(), str(sprite_path))
        for idx in range(14):
            sprite_path = DEMON_SPRITE_DIR / f"demon_{idx:02d}.png"
            if not sprite_path.exists():
                pygame.image.save(self._generate_demon_sprite(), str(sprite_path))

        for idx in range(14):
            sprite_path = ANGEL_BOSS_SPRITE_DIR / f"archangel_{idx:02d}.png"
            if not sprite_path.exists():
                pygame.image.save(self._generate_angel_boss_sprite(), str(sprite_path))
        for idx in range(14):
            sprite_path = DEMON_BOSS_SPRITE_DIR / f"hell_lord_{idx:02d}.png"
            if not sprite_path.exists():
                pygame.image.save(self._generate_demon_boss_sprite(), str(sprite_path))

        if not LIGHTNING_FX_PNG.exists():
            pygame.image.save(self._generate_vfx_sprite((64, 64), (185, 220, 255), "lightning"), str(LIGHTNING_FX_PNG))
        if not BAT_FX_PNG.exists():
            pygame.image.save(self._generate_vfx_sprite((64, 64), (100, 65, 65), "bat"), str(BAT_FX_PNG))
        if not RING_FX_PNG.exists():
            pygame.image.save(self._generate_vfx_sprite((80, 80), (240, 210, 140), "ring"), str(RING_FX_PNG))
        if not SHADOW_FX_PNG.exists():
            pygame.image.save(self._generate_vfx_sprite((64, 32), (28, 28, 32), "shadow"), str(SHADOW_FX_PNG))
        if not ANGEL_ULTIMATE_FX_PNG.exists():
            pygame.image.save(self._generate_vfx_sprite((92, 92), (210, 240, 255), "ring"), str(ANGEL_ULTIMATE_FX_PNG))
        if not DEMON_ULTIMATE_FX_PNG.exists():
            pygame.image.save(self._generate_vfx_sprite((92, 92), (255, 110, 70), "ring"), str(DEMON_ULTIMATE_FX_PNG))
        if not ANGEL_DEATH_FX_PNG.exists():
            pygame.image.save(self._generate_vfx_sprite((72, 72), (210, 232, 255), "ring"), str(ANGEL_DEATH_FX_PNG))
        if not DEMON_DEATH_FX_PNG.exists():
            pygame.image.save(self._generate_vfx_sprite((72, 72), (235, 90, 70), "ring"), str(DEMON_DEATH_FX_PNG))
        if not GOD_DEATH_FX_PNG.exists():
            pygame.image.save(self._generate_vfx_sprite((96, 96), (246, 236, 188), "ring"), str(GOD_DEATH_FX_PNG))

        if not SATAN_PNG.exists():
            pygame.image.save(self._generate_satan_sprite(), str(SATAN_PNG))
        if not GOD_PNG.exists():
            pygame.image.save(self._generate_god_sprite(), str(GOD_PNG))
        if not EARTH_ICON_PNG.exists():
            pygame.image.save(self._generate_earth_icon(), str(EARTH_ICON_PNG))

        for sfx_path in [ANGEL_SHOT_MP3, DEMON_SHOT_MP3, AMBIENCE_MP3, ANGEL_POWER_MP3, DEMON_POWER_MP3, BOSS_RING_MP3, ANGEL_LIGHTNING_MP3, DEMON_BAT_MP3, ANGEL_ULTIMATE_MP3, DEMON_ULTIMATE_MP3, SATAN_LOOP_MP3, GOD_LIGHTNING_MP3, ANGEL_DEATH_MP3, DEMON_DEATH_MP3, GOD_DEATH_MP3, SATAN_DEATH_MP3]:
            self._ensure_placeholder_mp3(sfx_path)

    def reload_assets(self) -> None:
        """Load background, overlays, sprite sheets, and sounds from user-replaceable assets."""
        world_size = self.world_size

        try:
            raw_bg = pygame.image.load(str(BACKGROUND_PATH)).convert_alpha()
        except pygame.error:
            raw_bg = self._generate_background_surface(world_size)
        self.background_surface = pygame.transform.smoothscale(raw_bg, world_size)

        try:
            raw_overlay = pygame.image.load(str(OVERLAY_PATH)).convert_alpha()
        except pygame.error:
            raw_overlay = self._generate_overlay_surface(world_size)
        self.overlay_surface = pygame.transform.smoothscale(raw_overlay, world_size)

        self.angel_sprite_bank = self._load_sprite_bank(ANGEL_SPRITE_DIR, fallback=self._generate_angel_sprite, max_size=DEFAULT_SPRITE_SIZE)
        self.angel_boss_sprite_bank = self._load_sprite_bank(ANGEL_BOSS_SPRITE_DIR, fallback=self._generate_angel_boss_sprite, max_size=DEFAULT_BOSS_SPRITE_SIZE)
        self.demon_sprite_bank = self._load_sprite_bank(DEMON_SPRITE_DIR, fallback=self._generate_demon_sprite, max_size=DEFAULT_SPRITE_SIZE)
        self.demon_boss_sprite_bank = self._load_sprite_bank(DEMON_BOSS_SPRITE_DIR, fallback=self._generate_demon_boss_sprite, max_size=DEFAULT_BOSS_SPRITE_SIZE)

        if self.audio_enabled:
            self.angel_shot_sound = self._try_load_sound(ANGEL_SHOT_MP3, 0.22)
            self.demon_shot_sound = self._try_load_sound(DEMON_SHOT_MP3, 0.26)
            self.ambient_sound = self._try_load_sound(AMBIENCE_MP3, 0.20)
            self.angel_power_sound = self._try_load_sound(ANGEL_POWER_MP3, 0.33)
            self.demon_power_sound = self._try_load_sound(DEMON_POWER_MP3, 0.33)
            self.boss_ring_sound = self._try_load_sound(BOSS_RING_MP3, 0.38)
            self.angel_lightning_sound = self._try_load_sound(ANGEL_LIGHTNING_MP3, 0.36)
            self.demon_bat_sound = self._try_load_sound(DEMON_BAT_MP3, 0.36)
            self.angel_ultimate_sound = self._try_load_sound(ANGEL_ULTIMATE_MP3, 0.42)
            self.demon_ultimate_sound = self._try_load_sound(DEMON_ULTIMATE_MP3, 0.42)
            self.satan_sound = self._try_load_sound(SATAN_LOOP_MP3, 0.28)
            self.god_power_sound = self._try_load_sound(GOD_LIGHTNING_MP3, 0.44)
            self.angel_death_sound = self._try_load_sound(ANGEL_DEATH_MP3, 0.40)
            self.demon_death_sound = self._try_load_sound(DEMON_DEATH_MP3, 0.40)
            self.god_death_sound = self._try_load_sound(GOD_DEATH_MP3, 0.46)
            self.satan_death_sound = self._try_load_sound(SATAN_DEATH_MP3, 0.46)
            if self.ambient_sound is not None:
                self.ambient_sound.play(loops=-1)
            if self.satan_sound is not None:
                self.satan_sound.play(loops=-1)

        self.satan_sprite = self._try_load_image(SATAN_PNG)
        self.god_sprite = self._try_load_image(GOD_PNG)
        self.earth_icon = self._try_load_image(EARTH_ICON_PNG)

        self.vfx_textures = {
            "lightning": self._try_load_image(LIGHTNING_FX_PNG),
            "bat": self._try_load_image(BAT_FX_PNG),
            "ring": self._try_load_image(RING_FX_PNG),
            "shadow": self._try_load_image(SHADOW_FX_PNG),
            "ultimate_angel": self._try_load_image(ANGEL_ULTIMATE_FX_PNG),
            "ultimate_demon": self._try_load_image(DEMON_ULTIMATE_FX_PNG),
            "death_angel": self._try_load_image(ANGEL_DEATH_FX_PNG),
            "death_demon": self._try_load_image(DEMON_DEATH_FX_PNG),
            "death_god": self._try_load_image(GOD_DEATH_FX_PNG),
        }

    def _normalize_sprite_size(self, image: pygame.Surface, max_size: Tuple[int, int]) -> pygame.Surface:
        """Normalize custom sprites into a square canvas without cropping/stretching."""
        max_w, max_h = max_size
        box = min(max_w, max_h)
        src_w, src_h = image.get_size()

        scale = min(1.0, box / max(1, src_w), box / max(1, src_h))
        new_w = max(1, int(src_w * scale))
        new_h = max(1, int(src_h * scale))
        resized = image if (new_w, new_h) == (src_w, src_h) else pygame.transform.smoothscale(image, (new_w, new_h))

        square = pygame.Surface((box, box), pygame.SRCALPHA)
        ox = (box - new_w) // 2
        oy = (box - new_h) // 2
        square.blit(resized, (ox, oy))
        return square

    def _load_sprite_bank(self, directory: Path, fallback, max_size: Tuple[int, int]) -> List[pygame.Surface]:
        sprites: List[pygame.Surface] = []
        files = sorted(directory.rglob("*.png"))
        for file_path in files:
            try:
                image = pygame.image.load(str(file_path)).convert_alpha()
                sprites.append(self._normalize_sprite_size(image, max_size=max_size))
            except pygame.error:
                continue
        if not sprites:
            sprites = [fallback() for _ in range(8)]
        return sprites

    def _try_load_sound(self, path: Path, volume: float) -> pygame.mixer.Sound | None:
        if not path.exists() or not self.audio_enabled:
            return None
        try:
            sound = pygame.mixer.Sound(str(path))
            sound.set_volume(volume)
            return sound
        except pygame.error:
            return None

    def _try_load_image(self, path: Path) -> pygame.Surface:
        try:
            return pygame.image.load(str(path)).convert_alpha()
        except pygame.error:
            fallback = pygame.Surface((32, 32), pygame.SRCALPHA)
            pygame.draw.circle(fallback, (255, 255, 255, 120), (16, 16), 10)
            return fallback

    def _generate_vfx_sprite(self, size: Tuple[int, int], color: Tuple[int, int, int], kind: str) -> pygame.Surface:
        surf = pygame.Surface(size, pygame.SRCALPHA)
        w, h = size
        if kind == "ring":
            pygame.draw.circle(surf, (*color, 170), (w // 2, h // 2), min(w, h) // 2 - 4, 3)
        elif kind == "shadow":
            pygame.draw.ellipse(surf, (*color, 140), (2, h // 4, w - 4, h // 2))
        elif kind == "bat":
            pygame.draw.polygon(surf, (*color, 180), [(8, h // 2), (w // 2, h // 3), (w - 8, h // 2), (w // 2, h // 2 + 6)])
        else:
            pygame.draw.line(surf, (*color, 200), (w // 2, 4), (w // 2, h - 4), 3)
            pygame.draw.line(surf, (*color, 170), (w // 2, h // 3), (w // 2 - 10, h // 2), 2)
            pygame.draw.line(surf, (*color, 170), (w // 2, h // 2), (w // 2 + 12, h // 2 + 8), 2)
        return surf

    def _play_shot_sfx(self, team: str) -> None:
        if not self.audio_enabled:
            return
        if time.time() - self.last_sfx_time < 0.025:
            return
        self.last_sfx_time = time.time()
        if team == TEAM_HEAVEN and self.angel_shot_sound is not None:
            self.angel_shot_sound.play()
        elif team == TEAM_HELL and self.demon_shot_sound is not None:
            self.demon_shot_sound.play()

    # ---------- procedural pixel art generators ----------

    def _pixel_lit_shade(self, surface: pygame.Surface, x: int, y: int, base: Tuple[int, int, int], light_dir: Tuple[float, float]) -> None:
        nx = (x - surface.get_width() * 0.5) / max(1, surface.get_width())
        ny = (y - surface.get_height() * 0.5) / max(1, surface.get_height())
        light = clamp(-(nx * light_dir[0] + ny * light_dir[1]), -1.0, 1.0)
        shaded = shade_rgb(base, int(light * 26))
        surface.set_at((x, y), (*shaded, 255))

    def _generate_angel_sprite(self) -> pygame.Surface:
        sprite = pygame.Surface((16, 16), pygame.SRCALPHA)
        skin = random.choice([(245, 210, 178), (232, 190, 156), (220, 175, 146)])
        robe = random.choice([(232, 226, 214), (218, 212, 228), (204, 198, 184)])
        wing = random.choice([(220, 214, 192), (198, 198, 208), (236, 230, 212)])
        gild = random.choice([(243, 190, 84), (228, 170, 70), (255, 209, 98)])

        # Wings with pixel shading.
        wing_points = [(1, 6, 5, 6), (10, 6, 5, 6)]
        for wx, wy, ww, wh in wing_points:
            for py in range(wy, wy + wh):
                for px in range(wx, wx + ww):
                    self._pixel_lit_shade(sprite, px, py, wing, light_dir=(0.8, -0.4))

        # Robe
        for py in range(5, 14):
            for px in range(5, 11):
                self._pixel_lit_shade(sprite, px, py, robe, light_dir=(1.0, -1.0))

        # Head
        for py in range(2, 5):
            for px in range(6, 10):
                self._pixel_lit_shade(sprite, px, py, skin, light_dir=(1.0, -0.8))

        # Halo and trim
        for px in range(5, 11):
            sprite.set_at((px, 1), (*gild, 255))
        sprite.set_at((7, 7), (255, 247, 196, 255))
        sprite.set_at((6, 8), (255, 247, 196, 255))
        sprite.set_at((8, 8), (255, 247, 196, 255))
        return sprite

    def _generate_demon_sprite(self) -> pygame.Surface:
        sprite = pygame.Surface((16, 16), pygame.SRCALPHA)
        skin = random.choice([(146, 40, 28), (120, 26, 20), (90, 15, 24), (101, 38, 64)])
        armor = random.choice([(62, 48, 42), (56, 56, 60), (70, 35, 26)])
        horn = random.choice([(183, 151, 96), (159, 130, 84), (130, 105, 72)])

        # Horns
        for px in range(5, 7):
            for py in range(1, 3):
                self._pixel_lit_shade(sprite, px, py, horn, light_dir=(-0.3, -0.9))
        for px in range(9, 11):
            for py in range(1, 3):
                self._pixel_lit_shade(sprite, px, py, horn, light_dir=(0.4, -0.8))

        # Head + body shading
        for py in range(3, 7):
            for px in range(5, 11):
                self._pixel_lit_shade(sprite, px, py, skin, light_dir=(0.6, -0.4))
        for py in range(7, 14):
            for px in range(5, 11):
                self._pixel_lit_shade(sprite, px, py, armor, light_dir=(0.4, -0.5))

        eye = random.choice([(255, 82, 52), (255, 132, 38), (232, 54, 64)])
        sprite.set_at((6, 4), (*eye, 255))
        sprite.set_at((9, 4), (*eye, 255))
        sprite.set_at((11, 11), (255, 120, 30, 255))
        return sprite

    def _generate_angel_boss_sprite(self) -> pygame.Surface:
        sprite = pygame.Surface(DEFAULT_BOSS_SPRITE_SIZE, pygame.SRCALPHA)
        robe = random.choice([(236, 230, 220), (226, 220, 236), (214, 210, 198)])
        gold = random.choice([(255, 214, 132), (238, 190, 92), (221, 176, 80)])
        wing = random.choice([(224, 220, 204), (212, 208, 224), (238, 232, 214)])

        for py in range(7, 21):
            for px in range(7, 15):
                self._pixel_lit_shade(sprite, px, py, robe, light_dir=(0.9, -0.9))

        for px in range(2, 7):
            for py in range(8, 18):
                self._pixel_lit_shade(sprite, px, py, wing, light_dir=(0.7, -0.3))
        for px in range(15, 20):
            for py in range(8, 18):
                self._pixel_lit_shade(sprite, px, py, wing, light_dir=(0.7, -0.3))

        for px in range(8, 14):
            sprite.set_at((px, 2), (*gold, 255))
        pygame.draw.rect(sprite, gold, (9, 4, 4, 1))
        pygame.draw.rect(sprite, (255, 248, 200), (10, 10, 2, 2))
        return sprite

    def _generate_demon_boss_sprite(self) -> pygame.Surface:
        sprite = pygame.Surface(DEFAULT_BOSS_SPRITE_SIZE, pygame.SRCALPHA)
        armor = random.choice([(84, 44, 34), (72, 58, 52), (90, 38, 30)])
        skin = random.choice([(150, 48, 32), (126, 30, 26), (112, 32, 58)])
        horn = random.choice([(190, 156, 112), (170, 130, 88), (145, 115, 76)])

        for py in range(6, 12):
            for px in range(7, 15):
                self._pixel_lit_shade(sprite, px, py, skin, light_dir=(0.5, -0.4))
        for py in range(12, 22):
            for px in range(6, 16):
                self._pixel_lit_shade(sprite, px, py, armor, light_dir=(0.4, -0.5))

        pygame.draw.rect(sprite, horn, (6, 1, 3, 3))
        pygame.draw.rect(sprite, horn, (13, 1, 3, 3))
        sprite.set_at((9, 8), (255, 82, 52, 255))
        sprite.set_at((12, 8), (255, 82, 52, 255))
        sprite.set_at((17, 16), (250, 130, 40, 255))
        return sprite

    def _generate_background_surface(self, size: Tuple[int, int]) -> pygame.Surface:
        w, h = size
        bg = pygame.Surface((w, h), pygame.SRCALPHA)
        center_y = h // 2

        sky_top = (8, 10, 18)
        sky_bottom = (25, 33, 60)
        hell_top = (54, 18, 16)
        hell_bottom = (16, 4, 5)

        draw_vertical_gradient(bg, pygame.Rect(0, 0, w, center_y), sky_top, sky_bottom)
        draw_vertical_gradient(bg, pygame.Rect(0, center_y, w, h - center_y), hell_top, hell_bottom)

        radius = int(min(w, h) * 0.45)
        center = (w // 2, h // 2)
        pygame.draw.circle(bg, (176, 128, 92), center, radius, 2)

        rnd = random.Random(2026)
        for _ in range(max(420, (w * h) // 18000)):
            x = rnd.randrange(0, w)
            y = rnd.randrange(0, h)
            if y < center_y:
                col = rnd.choice([(210, 206, 180), (168, 156, 131), (120, 140, 166)])
            else:
                col = rnd.choice([(124, 67, 45), (160, 80, 52), (92, 38, 30)])
            bg.set_at((x, y), (*col, 255))

        band_top = int(center_y - PURGATORY_BAND / 2)
        pygame.draw.rect(bg, (120, 100, 84), (0, band_top, w, PURGATORY_BAND))
        pygame.draw.line(bg, (188, 172, 144), (0, band_top), (w, band_top), 1)
        pygame.draw.line(bg, (86, 66, 56), (0, band_top + PURGATORY_BAND), (w, band_top + PURGATORY_BAND), 1)

        heaven_peak = [(w // 2 - 120, band_top - 8), (w // 2 + 120, band_top - 8), (w // 2, band_top - 140)]
        pygame.draw.polygon(bg, (132, 98, 78), heaven_peak)
        pygame.draw.polygon(bg, (166, 130, 96), [(w // 2 - 30, band_top - 8), (w // 2 + 30, band_top - 8), (w // 2, band_top - 65)])
        pygame.draw.line(bg, (248, 200, 92), (w // 2, band_top - 20), (w // 2, band_top - 130), 2)

        for i in range(7):
            fx = int((i + 0.5) * (w / 7))
            fh = 46 + (i % 3) * 18
            flame = [(fx - 28, band_top + PURGATORY_BAND + 8), (fx + 28, band_top + PURGATORY_BAND + 8), (fx, band_top + PURGATORY_BAND + fh)]
            pygame.draw.polygon(bg, (170, 72, 34), flame)

        vignette = pygame.Surface((w, h), pygame.SRCALPHA)
        for y in range(0, h, 2):
            for x in range(0, w, 2):
                nx = (x - w * 0.5) / (w * 0.5)
                ny = (y - h * 0.5) / (h * 0.5)
                d = clamp(math.sqrt(nx * nx + ny * ny), 0.0, 1.0)
                alpha = int((d ** 1.65) * 155)
                vignette.fill((0, 0, 0, alpha), (x, y, 2, 2))
        bg.blit(vignette, (0, 0))
        return bg

    def _generate_overlay_surface(self, size: Tuple[int, int]) -> pygame.Surface:
        w, h = size
        overlay = pygame.Surface((w, h), pygame.SRCALPHA)

        # Replaceable transparent motif layer (glyphs, arcs, circles).
        for i in range(6):
            x = int(w * (0.12 + i * 0.13))
            y = int(h * (0.18 + (i % 2) * 0.05))
            pygame.draw.circle(overlay, (220, 180, 110, 22), (x, y), 22 + i * 2, 1)

        for i in range(8):
            x1 = int(w * (0.10 + i * 0.1))
            x2 = int(w * (0.18 + i * 0.1))
            y1 = int(h * (0.12 + 0.028 * (i % 2)))
            y2 = int(h * (0.54 + 0.02 * (i % 3)))
            pygame.draw.aaline(overlay, (200, 130, 90, 60), (x1, y1), (x2, y2))

        return overlay

    def _generate_earth_icon(self) -> pygame.Surface:
        surf = pygame.Surface((96, 96), pygame.SRCALPHA)
        pygame.draw.circle(surf, (26, 28, 34), (48, 48), 43)
        pygame.draw.circle(surf, (196, 176, 132), (48, 48), 43, 2)
        pygame.draw.circle(surf, (42, 78, 128), (48, 48), 30)
        pygame.draw.arc(surf, (210, 196, 154), (14, 16, 68, 64), 0.2, 2.7, 2)
        pygame.draw.arc(surf, (210, 196, 154), (20, 26, 56, 50), 3.4, 5.6, 1)
        return surf

    def _generate_god_sprite(self) -> pygame.Surface:
        surf = pygame.Surface((220, 220), pygame.SRCALPHA)
        robe = (232, 234, 242)
        glow = (196, 218, 255)
        pygame.draw.ellipse(surf, (80, 100, 136, 90), (34, 160, 152, 36))
        pygame.draw.polygon(surf, robe, [(110, 28), (74, 86), (84, 168), (136, 168), (146, 86)])
        pygame.draw.circle(surf, (246, 232, 212), (110, 62), 20)
        pygame.draw.circle(surf, (255, 248, 190, 170), (110, 24), 26, 3)
        pygame.draw.line(surf, glow, (110, 88), (110, 176), 4)
        pygame.draw.line(surf, glow, (74, 126), (146, 126), 3)
        return surf

    def _generate_satan_sprite(self) -> pygame.Surface:
        surf = pygame.Surface((560, 520), pygame.SRCALPHA)
        body = (95, 26, 24)
        shadow = (48, 10, 12)
        horn = (170, 130, 90)
        pygame.draw.ellipse(surf, body, (40, 220, 500, 260))
        pygame.draw.ellipse(surf, shadow, (50, 340, 480, 130))
        pygame.draw.ellipse(surf, body, (220, 90, 170, 180))
        pygame.draw.polygon(surf, horn, [(250, 40), (275, 0), (300, 40)])
        pygame.draw.polygon(surf, horn, [(310, 40), (335, 0), (360, 40)])
        pygame.draw.circle(surf, (255, 90, 50), (280, 105), 7)
        pygame.draw.circle(surf, (255, 90, 50), (330, 105), 7)
        return surf

    # ---------- simulation ----------

    def _cast_secondary_power(self, unit: Unit, enemies: List[Unit]) -> None:
        if unit.is_boss:
            ring_radius = 90 if unit.team == TEAM_HEAVEN else 95
            ring_color = (220, 240, 255) if unit.team == TEAM_HEAVEN else (255, 112, 76)
            self.effects.append(
                VisualEffect(
                    points=tuple((int(unit.x + math.cos(a) * ring_radius), int(unit.y + math.sin(a) * ring_radius)) for a in [i * (math.pi / 8) for i in range(16)]),
                    color=ring_color,
                    ttl=0.32,
                    texture_key="ring",
                    pos=(int(unit.x), int(unit.y)),
                    radius=ring_radius,
                    shadow=True,
                )
            )
            if self.audio_enabled and self.boss_ring_sound is not None:
                self.boss_ring_sound.play()
            for enemy in enemies:
                if enemy.is_alive() and (enemy.x - unit.x) ** 2 + (enemy.y - unit.y) ** 2 <= ring_radius ** 2:
                    self._apply_damage(enemy, 14.0 if unit.team == TEAM_HEAVEN else 16.0, unit.team)
            return

        if unit.team == TEAM_HEAVEN:
            targets = sorted(enemies, key=lambda enemy: (enemy.x - unit.x) ** 2 + (enemy.y - unit.y) ** 2)[:3]
            if self.audio_enabled and self.angel_lightning_sound is not None:
                self.angel_lightning_sound.play()
            elif self.audio_enabled and self.angel_power_sound is not None:
                self.angel_power_sound.play()
            for target in targets:
                dx = target.x - unit.x
                dy = target.y - unit.y
                dist = math.hypot(dx, dy) + 1e-6
                speed = 250.0
                self.projectiles.append(
                    Projectile(
                        x=unit.x,
                        y=unit.y,
                        vx=(dx / dist) * speed,
                        vy=(dy / dist) * speed,
                        damage=9.0,
                        team=unit.team,
                        radius=2,
                        color=(200, 232, 255),
                        ttl=2.2,
                        kind="lightning",
                        homing=2.8,
                    )
                )
                mx = int((unit.x + target.x) * 0.5 + random.uniform(-12, 12))
                points = (
                    (int(unit.x), int(unit.y)),
                    (mx, int((unit.y + target.y) * 0.5 + random.uniform(-10, 10))),
                    (int(target.x), int(target.y)),
                )
                self.effects.append(VisualEffect(points=points, color=(185, 220, 255), ttl=0.18, texture_key="lightning", pos=(int(target.x), int(target.y)), radius=24, shadow=True))
        else:
            targets = sorted(enemies, key=lambda enemy: (enemy.x - unit.x) ** 2 + (enemy.y - unit.y) ** 2)[:2]
            if self.audio_enabled and self.demon_bat_sound is not None:
                self.demon_bat_sound.play()
            elif self.audio_enabled and self.demon_power_sound is not None:
                self.demon_power_sound.play()
            for target in targets:
                dx = target.x - unit.x
                dy = target.y - unit.y
                dist = math.hypot(dx, dy) + 1e-6
                speed = 230.0
                self.projectiles.append(
                    Projectile(
                        x=unit.x,
                        y=unit.y,
                        vx=(dx / dist) * speed,
                        vy=(dy / dist) * speed,
                        damage=6.0,
                        team=unit.team,
                        radius=2,
                        color=(70, 40, 40),
                        ttl=2.4,
                        kind="bat",
                        homing=2.2,
                    )
                )
            self.effects.append(VisualEffect(points=((int(unit.x), int(unit.y)),), color=(110, 70, 60), ttl=0.30, texture_key="bat", pos=(int(unit.x), int(unit.y)), radius=28, shadow=True))

    def _queue_fallen(self, unit: Unit) -> None:
        if unit.team == TEAM_HEAVEN:
            if unit.is_boss:
                self.fallen_angel_bosses.append(unit)
            else:
                self.fallen_angels.append(unit)
        else:
            if unit.is_boss:
                self.fallen_demon_bosses.append(unit)
            else:
                self.fallen_demons.append(unit)

    def _respawn_from_side_queue(self, team: str) -> None:
        world_w, world_h = self.world_size
        center_y = world_h / 2

        if team == TEAM_HEAVEN:
            if self.fallen_angels:
                unit = self.fallen_angels.pop(0)
                unit.hp = unit.max_hp
                unit.ability_timer = 6.0
                unit.ultimate_timer = 8.0
                unit.x = random.uniform(24, world_w - 24)
                unit.y = random.uniform(12, max(14, center_y - PURGATORY_BAND / 2 - 20))
                self.units.append(unit)
            if self.fallen_angel_bosses:
                unit = self.fallen_angel_bosses.pop(0)
                unit.hp = unit.max_hp
                unit.ability_timer = 6.0
                unit.ultimate_timer = 8.0
                unit.x = random.uniform(24, world_w - 24)
                unit.y = random.uniform(12, max(14, center_y - PURGATORY_BAND / 2 - 120))
                self.units.append(unit)
        else:
            if self.fallen_demons:
                unit = self.fallen_demons.pop(0)
                unit.hp = unit.max_hp
                unit.ability_timer = 6.0
                unit.ultimate_timer = 8.0
                unit.x = random.uniform(24, world_w - 24)
                unit.y = random.uniform(min(world_h - 14, center_y + PURGATORY_BAND / 2 + 20), world_h - 12)
                self.units.append(unit)
            if self.fallen_demon_bosses:
                unit = self.fallen_demon_bosses.pop(0)
                unit.hp = unit.max_hp
                unit.ability_timer = 6.0
                unit.ultimate_timer = 8.0
                unit.x = random.uniform(24, world_w - 24)
                unit.y = random.uniform(min(world_h - 14, center_y + PURGATORY_BAND / 2 + 120), world_h - 12)
                self.units.append(unit)

    def _cast_boss_ultimate(self, unit: Unit, enemies: List[Unit]) -> None:
        radius = 150 if unit.team == TEAM_HEAVEN else 165
        if unit.team == TEAM_HEAVEN:
            if self.audio_enabled and self.angel_ultimate_sound is not None:
                self.angel_ultimate_sound.play()
            key = "ultimate_angel"
            col = (210, 240, 255)
            dmg = 26.0
        else:
            if self.audio_enabled and self.demon_ultimate_sound is not None:
                self.demon_ultimate_sound.play()
            key = "ultimate_demon"
            col = (255, 110, 70)
            dmg = 30.0

        self.effects.append(
            VisualEffect(
                points=((int(unit.x), int(unit.y)),),
                color=col,
                ttl=0.55,
                texture_key=key,
                pos=(int(unit.x), int(unit.y)),
                radius=radius,
                shadow=True,
            )
        )

        for enemy in enemies:
            if (enemy.x - unit.x) ** 2 + (enemy.y - unit.y) ** 2 <= radius ** 2:
                self._apply_damage(enemy, dmg, unit.team)

    def _apply_damage(self, victim: Unit, amount: float, killer_team: str) -> None:
        if not victim.is_alive():
            return
        victim.hp -= amount
        if victim.hp > 0:
            return

        victim.hp = 0
        death_key = "death_demon" if victim.team == TEAM_HELL else "death_angel"
        death_col = (255, 140, 96) if victim.team == TEAM_HELL else (210, 228, 255)
        self.effects.append(
            VisualEffect(
                points=((int(victim.x), int(victim.y)),),
                color=death_col,
                ttl=0.45,
                texture_key=death_key,
                pos=(int(victim.x), int(victim.y)),
                radius=34,
                shadow=True,
            )
        )
        if self.audio_enabled:
            if victim.team == TEAM_HELL and self.demon_death_sound is not None:
                self.demon_death_sound.play()
            elif victim.team == TEAM_HEAVEN and self.angel_death_sound is not None:
                self.angel_death_sound.play()
        self._queue_fallen(victim)

        if victim.team == TEAM_HEAVEN and killer_team == TEAM_HELL:
            self.heaven_wrath_timer = 8.0
            for ally in self.units:
                if ally.team == TEAM_HEAVEN and ally.is_alive():
                    ally.neutral = False

    def _respawn_bosses_if_ready(self) -> None:
        if not self.boss_respawn_queue:
            return
        world_w, world_h = self.world_size
        center_y = world_h * 0.5
        now = time.time()
        remaining: List[Tuple[float, Unit]] = []
        for when, unit in self.boss_respawn_queue:
            if now < when:
                remaining.append((when, unit))
                continue
            if unit in self.units:
                continue
            unit.hp = unit.max_hp
            unit.ability_timer = 6.0
            unit.ultimate_timer = 8.0
            unit.neutral = False
            unit.x = random.uniform(24, world_w - 24)
            if unit.team == TEAM_HEAVEN:
                unit.y = random.uniform(12, max(14, center_y - PURGATORY_BAND / 2 - 120))
                if unit in self.fallen_angel_bosses:
                    self.fallen_angel_bosses.remove(unit)
            else:
                unit.y = random.uniform(min(world_h - 14, center_y + PURGATORY_BAND / 2 + 120), world_h - 12)
                if unit in self.fallen_demon_bosses:
                    self.fallen_demon_bosses.remove(unit)
            self.units.append(unit)
        self.boss_respawn_queue = remaining

    def _respawn_regular_units(self, dt: float) -> None:
        self.regular_respawn_timer = max(0.0, self.regular_respawn_timer - dt)
        if self.regular_respawn_timer > 0.0:
            return
        self.regular_respawn_timer = 1.25

        world_w, world_h = self.world_size
        center_y = world_h * 0.5

        if self.fallen_angels:
            unit = self.fallen_angels.pop(0)
            unit.hp = unit.max_hp
            unit.ability_timer = 4.0
            unit.ultimate_timer = 6.0
            unit.neutral = False
            unit.x = random.uniform(24, world_w - 24)
            unit.y = random.uniform(12, max(14, center_y - PURGATORY_BAND / 2 - 20))
            self.units.append(unit)

        if self.fallen_demons:
            unit = self.fallen_demons.pop(0)
            unit.hp = unit.max_hp
            unit.ability_timer = 4.0
            unit.ultimate_timer = 6.0
            unit.neutral = False
            unit.x = random.uniform(24, world_w - 24)
            unit.y = random.uniform(min(world_h - 14, center_y + PURGATORY_BAND / 2 + 20), world_h - 12)
            self.units.append(unit)

    def _enter_final_boss_mode(self) -> None:
        if self.final_boss_mode:
            return
        world_w, world_h = self.world_size
        self.final_boss_mode = True
        self.satan_meteor_mode = False
        self.effects.clear()
        # Keep battlefield entities; God eliminates demons before focusing Satan.
        self.satan_boss_max_hp = max(self.satan_boss_max_hp, 620.0 + self.ai_level * 80.0)
        self.satan_boss_hp = self.satan_boss_max_hp
        self.god_max_hp = max(self.god_max_hp, 620.0 + self.ai_level * 80.0)
        self.god_hp = self.god_max_hp
        self.god_x = world_w * 0.5
        self.god_y = world_h * 0.5 - 130
        self.god_attack_timer = 0.0
        self.satan_attack_timer = 0.0
        self.god_ultimate_timer = 2.4
        self.satan_ultimate_timer = 3.0
        self.final_boss_timer = 20.0

    def _update_final_boss_mode(self, dt: float) -> None:
        self.god_attack_timer = max(0.0, self.god_attack_timer - dt)
        self.satan_attack_timer = max(0.0, self.satan_attack_timer - dt)
        self.god_ultimate_timer = max(0.0, self.god_ultimate_timer - dt)
        self.satan_ultimate_timer = max(0.0, self.satan_ultimate_timer - dt)
        self.final_boss_timer = max(0.0, self.final_boss_timer - dt)
        self.satan_timer += dt
        world_w, world_h = self.world_size
        self.satan_x += self.satan_dir * dt * 10.0
        if self.satan_x < world_w * 0.10:
            self.satan_x = world_w * 0.10
            self.satan_dir = 1.0
        elif self.satan_x > world_w * 0.90:
            self.satan_x = world_w * 0.90
            self.satan_dir = -1.0

        sx = int(self.satan_x)
        sy = int(world_h - self.satan_sprite.get_height() * 0.30)  # center/lower mass target
        gx = int(self.god_x)
        gy = int(self.god_y)

        # God clears demons first.
        demon_units = [u for u in self.units if u.team == TEAM_HELL and u.is_alive()]
        if demon_units:
            target = min(demon_units, key=lambda u: (u.x - self.god_x) ** 2 + (u.y - self.god_y) ** 2)
            tx, ty = int(target.x), int(target.y)
        else:
            tx, ty = sx, sy

        if self.god_attack_timer <= 0.0:
            self.god_attack_timer = 0.38
            if self.audio_enabled and self.god_power_sound is not None:
                self.god_power_sound.play()
            self.screen_shake_timer = 0.20
            self.screen_shake_intensity = 14.0
            bolt_points = ((gx, gy - 14), (int((gx + tx) * 0.5), int((gy + ty) * 0.5 - 16)), (tx, ty))
            self.effects.append(VisualEffect(points=bolt_points, color=(205, 236, 255), ttl=0.20, texture_key="lightning", pos=(tx, ty), radius=44, shadow=True))
            if demon_units:
                self._apply_damage(target, 30.0 + self.ai_level * 3.0, TEAM_HEAVEN)
            else:
                self.satan_boss_hp = max(0.0, self.satan_boss_hp - (18.0 + self.ai_level * 2.6))

        # Satan defense meteors during duel.
        if self.satan_attack_timer <= 0.0:
            self.satan_attack_timer = 0.80
            dx = self.god_x - self.satan_x
            dy = self.god_y - sy
            dist = math.hypot(dx, dy) + 1e-6
            self.projectiles.append(
                Projectile(
                    x=self.satan_x,
                    y=sy,
                    vx=(dx / dist) * 190.0,
                    vy=(dy / dist) * 190.0,
                    damage=16.0,
                    team=TEAM_HELL,
                    radius=5,
                    color=(255, 118, 70),
                    ttl=4.0,
                    kind="meteor",
                    homing=1.5,
                    health=3.0,
                )
            )

        if self.god_ultimate_timer <= 0.0:
            self.god_ultimate_timer = 5.2
            self.effects.append(VisualEffect(points=((tx, ty),), color=(225, 244, 255), ttl=0.34, texture_key="ultimate_angel", pos=(tx, ty), radius=112, shadow=True))
            if demon_units:
                for d in demon_units[:6]:
                    self._apply_damage(d, 32.0 + self.ai_level * 3.0, TEAM_HEAVEN)
            else:
                self.satan_boss_hp = max(0.0, self.satan_boss_hp - (34.0 + self.ai_level * 3.2))

        if self.satan_ultimate_timer <= 0.0 and not demon_units:
            self.satan_ultimate_timer = 6.2
            self.effects.append(VisualEffect(points=((gx, gy),), color=(255, 122, 80), ttl=0.34, texture_key="ultimate_demon", pos=(gx, gy), radius=116, shadow=True))
            self.god_hp = max(0.0, self.god_hp - (34.0 + self.ai_level * 3.2))

        for proj in self.projectiles:
            if proj.team == TEAM_HELL and (proj.x - self.god_x) ** 2 + (proj.y - self.god_y) ** 2 <= 330 ** 2 and proj.kind != "meteor":
                proj.health = 0.0
                proj.ttl = 0.0

        if self.final_boss_timer <= 0.0 and self.god_hp > 0.0 and self.satan_boss_hp > 0.0:
            if self.god_hp >= self.satan_boss_hp:
                self.satan_boss_hp = 0.0
            else:
                self.god_hp = 0.0

        if self.god_hp <= 0.0:
            self.effects.append(VisualEffect(points=((gx, gy),), color=(255, 232, 188), ttl=0.55, texture_key="death_god", pos=(gx, gy), radius=58, shadow=True))
            if self.audio_enabled and self.god_death_sound is not None:
                self.god_death_sound.play()
            self.winner = TEAM_HELL
            self.round_reset_timer = 2.0
            self.final_boss_mode = False
        elif self.satan_boss_hp <= 0.0:
            self.effects.append(VisualEffect(points=((sx, sy),), color=(255, 110, 70), ttl=0.55, texture_key="death_demon", pos=(sx, sy), radius=62, shadow=True))
            if self.audio_enabled and self.satan_death_sound is not None:
                self.satan_death_sound.play()
            self.winner = TEAM_HEAVEN
            self.round_reset_timer = 2.0
            self.final_boss_mode = False

    def _trigger_satan_meteors(self) -> None:
        if self.satan_meteor_mode:
            return
        self.satan_meteor_mode = True
        self.satan_meteor_timer = 14.0
        for i in range(8):
            ang = (i / 8.0) * math.tau + random.uniform(-0.16, 0.16)
            speed = 88.0
            self.projectiles.append(
                Projectile(
                    x=self.satan_x + random.uniform(-40, 40),
                    y=self.world_size[1] - self.satan_sprite.get_height() * 0.58 + random.uniform(-50, 40),
                    vx=math.cos(ang) * speed,
                    vy=-abs(math.sin(ang)) * speed * 0.8,
                    damage=26.0,
                    team=TEAM_HELL,
                    radius=6,
                    color=(255, 116, 54),
                    ttl=18.0,
                    kind="meteor",
                    homing=0.75,
                    health=4.0,
                )
            )

    def update(self, dt: float) -> None:
        if self.winner is not None:
            self.round_reset_timer = max(0.0, self.round_reset_timer - dt)
            if self.round_reset_timer <= 0.0:
                if self.return_to_host_on_battle_end:
                    self.pending_host_return = True
                else:
                    self.ai_level = min(3.2, self.ai_level + 0.06)
                    self.reset_battle()
            return

        world_w, world_h = self.world_size

        if self.final_boss_mode:
            self._update_final_boss_mode(dt)
            return

        self.overlay_scroll = (self.overlay_scroll + dt * 2.0) % max(1, world_w)
        self.heaven_wrath_timer = max(0.0, self.heaven_wrath_timer - dt)
        self._respawn_bosses_if_ready()
        self._respawn_regular_units(dt)
        self.satan_timer += dt
        self.satan_x += self.satan_dir * dt * 12.0
        if self.satan_x < world_w * 0.10:
            self.satan_x = world_w * 0.10
            self.satan_dir = 1.0
        elif self.satan_x > world_w * 0.90:
            self.satan_x = world_w * 0.90
            self.satan_dir = -1.0
        center_y = world_h / 2

        heaven_units = [u for u in self.units if u.team == TEAM_HEAVEN and u.is_alive()]
        hell_units = [u for u in self.units if u.team == TEAM_HELL and u.is_alive()]
        heaven_bosses_alive = [u for u in heaven_units if u.is_boss]
        hell_bosses_alive = [u for u in hell_units if u.is_boss]

        if not heaven_bosses_alive or not hell_bosses_alive:
            self._enter_final_boss_mode()
            return

        for unit in self.units:
            if not unit.is_alive():
                continue

            enemies = hell_units if unit.team == TEAM_HEAVEN else heaven_units
            if not enemies:
                continue

            target = min(enemies, key=lambda enemy: (enemy.x - unit.x) ** 2 + (enemy.y - unit.y) ** 2)
            dx = target.x - unit.x
            if abs(dx) > 0.25:
                unit.facing_right = dx >= 0
            dy = target.y - unit.y
            if unit.team == TEAM_HEAVEN and self.heaven_wrath_timer > 0.0:
                dy += 120.0
            dist = math.hypot(dx, dy) + 1e-6

            if unit.neutral:
                if unit.team == TEAM_HEAVEN and unit.y > center_y + PURGATORY_BAND / 2:
                    unit.neutral = False
                elif unit.team == TEAM_HELL and unit.y < center_y - PURGATORY_BAND / 2:
                    unit.neutral = False

            desired_range = unit.attack_range * (0.82 + 0.36 * (1.0 - unit.ai.aggression))
            if dist > desired_range:
                step = min(unit.speed * dt, dist)
                unit.x += (dx / dist) * step
                unit.y += (dy / dist) * step
            elif unit.team == TEAM_HELL:
                # Demons pressure forward instead of retreating.
                step = min(unit.speed * 0.20 * dt, dist)
                unit.x += (dx / dist) * step
                unit.y += (dy / dist) * step
            elif dist < desired_range * 0.62:
                step = min(unit.speed * 0.5 * dt, dist)
                unit.x -= (dx / dist) * step
                unit.y -= (dy / dist) * step

            # Simple local separation to find open lanes and avoid clumping.
            sep_x = 0.0
            sep_y = 0.0
            neighbors = 0
            for ally in self.units:
                if ally is unit or ally.team != unit.team or not ally.is_alive():
                    continue
                adx = unit.x - ally.x
                ady = unit.y - ally.y
                ad2 = adx * adx + ady * ady
                if 0.0 < ad2 < 26.0 * 26.0:
                    inv = 1.0 / (math.sqrt(ad2) + 1e-6)
                    sep_x += adx * inv
                    sep_y += ady * inv
                    neighbors += 1
            if neighbors > 0:
                unit.x += (sep_x / neighbors) * dt * 28.0
                unit.y += (sep_y / neighbors) * dt * 28.0

            unit.x = clamp(unit.x, 8, world_w - 8)
            unit.y = clamp(unit.y, 8, world_h - 8)

            unit.shoot_timer -= dt
            unit.ability_timer = max(0.0, unit.ability_timer - dt)
            unit.ultimate_timer = max(0.0, unit.ultimate_timer - dt)
            if unit.is_boss and unit.hp <= unit.max_hp * 0.35 and unit.ultimate_timer <= 0.0:
                self._cast_boss_ultimate(unit, enemies)
                unit.ultimate_timer = 24.0

            if unit.hp <= unit.max_hp * 0.5 and unit.ability_timer <= 0.0:
                self._cast_secondary_power(unit, enemies)
                unit.ability_timer = 10.0

            if dist <= unit.attack_range and unit.shoot_timer <= 0:
                jitter = unit.ai.aim_jitter * (0.45 if (unit.team == TEAM_HEAVEN and unit.is_boss) else 1.0)
                aim_dx = dx + random.uniform(-jitter, jitter) * dist
                aim_dy = dy + random.uniform(-jitter, jitter) * dist
                aim_len = math.hypot(aim_dx, aim_dy) + 1e-6

                vx = (aim_dx / aim_len) * unit.projectile_speed
                vy = (aim_dy / aim_len) * unit.projectile_speed

                if unit.team == TEAM_HEAVEN:
                    color = random.choice([(248, 196, 80), (236, 176, 66), (255, 220, 120)])
                    radius = 2
                    ttl = 1.3
                else:
                    color = random.choice([(232, 80, 30), (255, 110, 28), (206, 44, 20)])
                    radius = 3
                    ttl = 1.1

                self.projectiles.append(
                    Projectile(
                        x=unit.x,
                        y=unit.y,
                        vx=vx,
                        vy=vy,
                        damage=unit.damage,
                        team=unit.team,
                        radius=radius,
                        color=color,
                        ttl=ttl,
                        kind="basic",
                        homing=1.2 if (unit.team == TEAM_HEAVEN and unit.is_boss) else 0.0,
                    )
                )

                self._play_shot_sfx(unit.team)
                unit.ai.shots += 1
                unit.ai.learn()
                unit.shoot_timer = unit.cooldown * (1.1 - 0.35 * unit.ai.aggression)

        next_effects: List[VisualEffect] = []

        for effect in self.effects:
            effect.ttl -= dt
            if effect.ttl > 0:
                next_effects.append(effect)
        self.effects = next_effects

        survivors: List[Projectile] = []
        for projectile in self.projectiles:
            if projectile.homing > 0.0:
                enemies = hell_units if projectile.team == TEAM_HEAVEN else heaven_units
                if enemies:
                    target = min(enemies, key=lambda enemy: (enemy.x - projectile.x) ** 2 + (enemy.y - projectile.y) ** 2)
                    dx = target.x - projectile.x
                    dy = target.y - projectile.y
                    dist = math.hypot(dx, dy) + 1e-6
                    speed = math.hypot(projectile.vx, projectile.vy)
                    desired_vx = (dx / dist) * speed
                    desired_vy = (dy / dist) * speed
                    blend = clamp(projectile.homing * dt, 0.0, 1.0)
                    projectile.vx = lerp(projectile.vx, desired_vx, blend)
                    projectile.vy = lerp(projectile.vy, desired_vy, blend)

            if not projectile.update(dt):
                continue
            if projectile.x < 0 or projectile.y < 0 or projectile.x >= world_w or projectile.y >= world_h:
                continue

            enemies = hell_units if projectile.team == TEAM_HEAVEN else heaven_units
            hit = False

            if projectile.kind != "meteor":
                enemy_meteors = [m for m in self.projectiles if m.kind == "meteor" and m.team != projectile.team]
                for meteor in enemy_meteors:
                    if (meteor.x - projectile.x) ** 2 + (meteor.y - projectile.y) ** 2 <= (meteor.radius + projectile.radius + 2) ** 2:
                        meteor.health -= max(1.0, projectile.damage * 0.35)
                        hit = True
                        break

            for enemy in enemies:
                if not enemy.is_alive():
                    continue
                if (enemy.x - projectile.x) ** 2 + (enemy.y - projectile.y) ** 2 <= (8 + projectile.radius) ** 2:
                    self._apply_damage(enemy, projectile.damage, projectile.team)
                    hit = True
                    friendlies = [u for u in self.units if u.team == projectile.team and u.is_alive()]
                    if friendlies:
                        random.choice(friendlies).ai.hits += 1
                    break

            if not hit and projectile.health > 0:
                survivors.append(projectile)

        self.projectiles = survivors
        alive_units = [u for u in self.units if u.is_alive()]

        heaven_alive = [u for u in alive_units if u.team == TEAM_HEAVEN]
        hell_alive = [u for u in alive_units if u.team == TEAM_HELL]

        if self.satan_meteor_mode:
            self.satan_meteor_timer -= dt
            if self.satan_meteor_timer <= 0.0:
                self._smite_satan()

        self.units = alive_units

        if self.camera_track_uid is not None:
            tracked = next((u for u in self.units if u.uid == self.camera_track_uid and u.is_alive()), None)
            if tracked is None:
                self.camera_track_uid = None
            else:
                tx = tracked.x - world_w * 0.5
                ty = tracked.y - world_h * 0.5
                deadzone_x = world_w * 0.18
                deadzone_y = world_h * 0.18
                if abs((tracked.x - self.camera_x) - world_w * 0.5) > deadzone_x:
                    self.camera_x = lerp(self.camera_x, tx, 0.10)
                if abs((tracked.y - self.camera_y) - world_h * 0.5) > deadzone_y:
                    self.camera_y = lerp(self.camera_y, ty, 0.10)

    # ---------- rendering ----------

    def _draw_fallen_queues(self, surf: pygame.Surface) -> None:
        # Always-on queue panels, independent of UI/help toggle.
        top_panel = pygame.Surface((176, 52), pygame.SRCALPHA)
        top_panel.fill((18, 16, 18, 168))
        top_panel.blit(self.font_small.render("Fallen Angels", True, (210, 220, 255)), (8, 4))
        surf.blit(top_panel, (8, 58))

        bottom_panel = pygame.Surface((176, 52), pygame.SRCALPHA)
        bottom_panel.fill((18, 12, 10, 168))
        bottom_panel.blit(self.font_small.render("Fallen Demons", True, (255, 180, 160)), (8, 4))
        surf.blit(bottom_panel, (8, surf.get_height() - 64))

        for i in range(10):
            pygame.draw.rect(surf, (160, 170, 186, 95), (12 + i * 16, 80, 14, 14), 1)
            pygame.draw.rect(surf, (180, 120, 110, 95), (12 + i * 16, surf.get_height() - 42, 14, 14), 1)

        for i, unit in enumerate(self.fallen_angels[:10]):
            icon = pygame.transform.smoothscale(unit.sprite_right, (14, 14))
            surf.blit(icon, (12 + i * 16, 80))
        for i, unit in enumerate(self.fallen_demons[:10]):
            icon = pygame.transform.smoothscale(unit.sprite_right, (14, 14))
            surf.blit(icon, (12 + i * 16, surf.get_height() - 42))

        for i, unit in enumerate(self.fallen_angel_bosses[:8]):
            icon = pygame.transform.smoothscale(unit.sprite_right, (18, 18))
            surf.blit(icon, (surf.get_width() - 28 - (i % 2) * 20, 70 + i * 18))
        for i, unit in enumerate(self.fallen_demon_bosses[:8]):
            icon = pygame.transform.smoothscale(unit.sprite_right, (18, 18))
            surf.blit(icon, (surf.get_width() - 28 - (i % 2) * 20, surf.get_height() - 90 - i * 18))

    def _draw_earth_balance(self, surf: pygame.Surface) -> None:
        heaven_alive = sum(1 for unit in self.units if unit.team == TEAM_HEAVEN)
        hell_alive = sum(1 for unit in self.units if unit.team == TEAM_HELL)
        total = max(1, heaven_alive + hell_alive)
        hell_ratio = hell_alive / total

        earth = pygame.transform.smoothscale(self.earth_icon, (82, 82))
        ex = surf.get_width() // 2 - earth.get_width() // 2
        ey = surf.get_height() // 2 - earth.get_height() // 2

        fill_mask = pygame.Surface(earth.get_size(), pygame.SRCALPHA)
        pygame.draw.circle(fill_mask, (255, 255, 255, 255), (earth.get_width() // 2, earth.get_height() // 2), 26)
        fill_layer = pygame.Surface(earth.get_size(), pygame.SRCALPHA)
        red_h = int(52 * hell_ratio)
        if red_h > 0:
            pygame.draw.rect(fill_layer, (186, 42, 42, 190), (earth.get_width() // 2 - 26, earth.get_height() // 2 + 26 - red_h, 52, red_h))
        fill_layer.blit(fill_mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)

        surf.blit(earth, (ex, ey))
        surf.blit(fill_layer, (ex, ey))

    def _smite_satan(self) -> None:
        world_h = self.world_size[1]
        sx = int(self.satan_x)
        sy = int(world_h - self.satan_sprite.get_height() * 0.56)
        points = ((sx, 0), (sx + random.randint(-12, 12), sy // 2), (sx, sy))
        self.effects.append(VisualEffect(points=points, color=(208, 236, 255), ttl=0.45, texture_key="lightning", pos=(sx, sy), radius=60, shadow=False))
        self.projectiles = [p for p in self.projectiles if p.kind != "meteor"]
        self.satan_meteor_mode = False
        self.winner = TEAM_HEAVEN
        self.round_reset_timer = 2.0

    def draw_world(self) -> None:
        surf = self.internal_surface
        surf.blit(self.background_surface, (0, 0))
        self._draw_earth_balance(surf)

        ow = self.overlay_surface.get_width()
        ox = int(self.overlay_scroll)
        surf.blit(self.overlay_surface, (-ox, 0))
        surf.blit(self.overlay_surface, (ow - ox, 0))

        self.effect_surface.fill((0, 0, 0, 0))
        now = time.time()

        for unit in self.units:
            bob = math.sin((now * 4.8) + (unit.uid * 0.38)) * 1.1
            sprite = unit.sprite_right if unit.facing_right else unit.sprite_left
            ux = int(unit.x - sprite.get_width() // 2)
            uy = int(unit.y - sprite.get_height() // 2 + bob)
            direction = -1 if unit.facing_right else 1
            trail = sprite.copy()
            trail.fill((255, 255, 255, 90), special_flags=pygame.BLEND_RGBA_MULT)
            surf.blit(trail, (ux + direction * 4, uy), special_flags=pygame.BLEND_ALPHA_SDL2)
            surf.blit(sprite, (ux, uy))

        if self.final_boss_mode:
            god = self.god_sprite
            gx = int(self.god_x - god.get_width() * 0.5)
            gy = int(self.god_y - god.get_height() * 0.5)
            surf.blit(god, (gx, gy))

        satan_base = self.satan_sprite if self.satan_dir >= 0 else pygame.transform.flip(self.satan_sprite, True, False)
        satan_y = surf.get_height() - int(satan_base.get_height() * 0.52) + int(math.sin(self.satan_timer * 0.9) * 14)
        satan_x = int(self.satan_x - satan_base.get_width() * 0.5)
        # slight blur by layered draws
        for i, a in enumerate((70, 45, 25)):
            layer = satan_base.copy()
            layer.fill((255, 255, 255, a), special_flags=pygame.BLEND_RGBA_MULT)
            surf.blit(layer, (satan_x - i * 2, satan_y + i), special_flags=pygame.BLEND_ALPHA_SDL2)

        if self.camera_track_uid is not None:
            tracked = next((u for u in self.units if u.uid == self.camera_track_uid), None)
            if tracked is not None:
                pygame.draw.circle(surf, (255, 240, 170), (int(tracked.x), int(tracked.y)), 14, 2)

        for effect in self.effects:
            if len(effect.points) > 1:
                pygame.draw.lines(surf, effect.color, False, effect.points, 2)

            tex = self.vfx_textures.get(effect.texture_key)
            if tex is not None:
                scaled = pygame.transform.smoothscale(tex, (effect.radius * 2, effect.radius * 2))
                cx, cy = effect.pos
                layer = scaled.copy()
                layer.fill((255, 255, 255, 160), special_flags=pygame.BLEND_RGBA_MULT)
                surf.blit(layer, (cx - effect.radius, cy - effect.radius), special_flags=pygame.BLEND_ALPHA_SDL2)
            if effect.shadow:
                shadow_tex = self.vfx_textures.get("shadow")
                if shadow_tex is not None:
                    sh = pygame.transform.smoothscale(shadow_tex, (max(20, effect.radius * 2), max(10, effect.radius)))
                    sh.fill((255, 255, 255, 90), special_flags=pygame.BLEND_RGBA_MULT)
                    surf.blit(sh, (effect.pos[0] - sh.get_width() // 2, effect.pos[1] + 10), special_flags=pygame.BLEND_ALPHA_SDL2)

        for projectile in self.projectiles:
            px = int(projectile.x)
            py = int(projectile.y)
            if projectile.kind == "bat":
                pygame.draw.polygon(surf, projectile.color, [(px - 3, py), (px, py - 2), (px + 3, py), (px, py + 2)])
            else:
                pygame.draw.circle(surf, projectile.color, (px, py), projectile.radius)
            tx = int(projectile.x - projectile.vx * 0.022)
            ty = int(projectile.y - projectile.vy * 0.022)
            pygame.draw.line(surf, projectile.color, (px, py), (tx, ty), 1)

            glow_alpha = 55 if projectile.team == TEAM_HEAVEN else 65
            glow_col = (*projectile.color, glow_alpha)
            pygame.draw.circle(self.effect_surface, glow_col, (px, py), projectile.radius + 2)

        surf.blit(self.effect_surface, (0, 0))
        if self.show_ui:
            self._draw_hud(surf)
        self._draw_fallen_queues(surf)

    def _draw_hud(self, surf: pygame.Surface) -> None:
        heaven_alive = sum(1 for unit in self.units if unit.team == TEAM_HEAVEN)
        hell_alive = sum(1 for unit in self.units if unit.team == TEAM_HELL)
        heaven_bosses = sum(1 for unit in self.units if unit.team == TEAM_HEAVEN and unit.is_boss)
        hell_bosses = sum(1 for unit in self.units if unit.team == TEAM_HELL and unit.is_boss)
        elapsed = time.time() - self.start_time

        total_strength = max(1.0, (heaven_alive + hell_alive) + 2.0 * (heaven_bosses + hell_bosses))
        heaven_strength = heaven_alive + 2.0 * heaven_bosses
        heaven_prob = clamp(heaven_strength / total_strength, 0.0, 1.0)
        hell_prob = 1.0 - heaven_prob

        info = [
            f"Heaven: {heaven_alive}",
            f"Hell: {hell_alive}",
            f"Bosses (H/Hell): {heaven_bosses}/{hell_bosses}",
            f"Projectiles: {len(self.projectiles)}",

            f"Pixel scale: {self.pixel_scale}x",
            f"AI Ascendancy: {self.ai_level:.2f}x",
            f"Zoom: {self.zoom:.2f}x",
            f"Audio: {'On' if self.audio_enabled else 'Off'}",
            f"Fallen (A/D): {len(self.fallen_angels)}/{len(self.fallen_demons)}",
            f"Elapsed: {elapsed:5.1f}s",
            f"Win Odds H/Hell: {heaven_prob*100:4.1f}%/{hell_prob*100:4.1f}%",
        ]
        if self.final_boss_mode:
            info.append(f"Final Duel HP (God/Satan): {self.god_hp:4.0f}/{self.satan_boss_hp:4.0f}")
            info.append(f"Final Duel Timer: {self.final_boss_timer:4.1f}s")

        panel = pygame.Surface((360, 220), pygame.SRCALPHA)
        panel.fill(PANEL_BG)
        for index, text in enumerate(info):
            panel.blit(self.font_small.render(text, True, TEXT_COLOR), (10, 8 + index * 20))
        surf.blit(panel, (10, 10))

        if self.winner is not None:
            msg = "HEAVEN WINS" if self.winner == TEAM_HEAVEN else "HELL WINS"
            banner = self.font_medium.render(msg, True, (255, 230, 180))
            surf.blit(banner, (surf.get_width() // 2 - banner.get_width() // 2, 16))

        if self.show_help:
            if self.help_auto_hide and elapsed >= 4.0:
                self.show_help = False
            help_lines = [
                "I. LEX BELLI — Controls",
                "H: Reveal/Conceal Codex",
                "Mouse Wheel: Zoom",
                "Arrow Keys: Pan",
                "Click Soul: Follow",
                "Click Void / Pan: Release Follow",
                "F11: Fullscreen",
                "V: VSync",
                "1..6: Pixel Scale",
                "M: Mute",
                "L: Reload Relics",
                "R: Reset Realm",
                "ESC: Quit",
                "",
                "II. ORDO CELESTIS ET INFERNI",
                "All angelic and demonic forms from folders spawn.",
                "Archangel deaths queue at upper-left until demon boss falls.",
                "Demon deaths queue at lower-left until archangel falls.",
                "Bosses respawn 60s after death.",
                "Infernal meteors awaken if all demons fall.",
                "Cloud veil drifts slowly; Satan paces the abyss.",
                "When any faction loses all bosses, gods descend and duel (~20s).",
            ]
            w, h = surf.get_size()
            help_panel = pygame.Surface((760, 470), pygame.SRCALPHA)
            help_panel.fill((18, 14, 12, 236))
            if self.help_auto_hide:
                fade = clamp(4.0 - elapsed, 0.0, 1.0)
                help_panel.set_alpha(int(255 * fade))
            title = self.font_medium.render("SANCTUM TABULA", True, (246, 224, 180))
            help_panel.blit(title, (help_panel.get_width()//2 - title.get_width()//2, 16))
            for index, line in enumerate(help_lines):
                help_panel.blit(self.font_small.render(line, True, TEXT_COLOR), (24, 56 + index * 21))
            surf.blit(help_panel, (w//2 - help_panel.get_width()//2, h//2 - help_panel.get_height()//2))

    # ---------- display pipeline ----------

    def present(self) -> None:
        win_w, win_h = self.screen.get_size()
        target_w, target_h = win_w, win_h

        render_w = max(target_w, int(target_w * self.zoom))
        render_h = max(target_h, int(target_h * self.zoom))
        scaled = pygame.transform.scale(self.internal_surface, (render_w, render_h))
        cam_px_x = int(self.camera_x * self.zoom)
        cam_px_y = int(self.camera_y * self.zoom)
        shake_x = 0
        shake_y = 0
        if self.screen_shake_timer > 0.0:
            self.screen_shake_timer = max(0.0, self.screen_shake_timer - (1.0 / max(30, self.max_fps)))
            shake_x = random.randint(-int(self.screen_shake_intensity), int(self.screen_shake_intensity))
            shake_y = random.randint(-int(self.screen_shake_intensity), int(self.screen_shake_intensity))
            self.screen_shake_intensity *= 0.86

        draw_x = - (render_w - target_w) // 2 - cam_px_x + shake_x
        draw_y = - (render_h - target_h) // 2 - cam_px_y + shake_y

        self.screen.fill((0, 0, 0))
        self.screen.blit(scaled, (draw_x, draw_y))
        pygame.display.flip()

    def _rebuild_internal_surface(self) -> None:
        self.internal_surface = pygame.Surface((BASE_W // self.pixel_scale, BASE_H // self.pixel_scale)).convert_alpha()
        self.background_surface = pygame.Surface(self.internal_surface.get_size()).convert_alpha()
        self.overlay_surface = pygame.Surface(self.internal_surface.get_size(), pygame.SRCALPHA)
        self.effect_surface = pygame.Surface(self.internal_surface.get_size(), pygame.SRCALPHA)
        self.reload_assets()
        self.reset_battle()

    def _toggle_fullscreen(self) -> None:
        self.fullscreen = not self.fullscreen
        flags = pygame.FULLSCREEN if self.fullscreen else pygame.RESIZABLE
        if self.fullscreen:
            self.screen = pygame.display.set_mode((0, 0), flags, vsync=self.vsync)
        else:
            self.screen = pygame.display.set_mode(self.window_size, flags, vsync=self.vsync)

    def _toggle_vsync(self) -> None:
        self.vsync = 0 if self.vsync else 1
        flags = pygame.FULLSCREEN if self.fullscreen else pygame.RESIZABLE
        size = (0, 0) if self.fullscreen else self.window_size
        self.screen = pygame.display.set_mode(size, flags, vsync=self.vsync)

    def _toggle_audio(self) -> None:
        if not self.audio_enabled:
            return
        if pygame.mixer.get_busy():
            pygame.mixer.pause()
        else:
            pygame.mixer.unpause()

    # ---------- helpers ----------

    def _screen_to_world(self, sx: int, sy: int) -> Tuple[float, float]:
        win_w, win_h = self.screen.get_size()
        if win_w <= 0 or win_h <= 0:
            return 0.0, 0.0

        nx = sx / win_w
        ny = sy / win_h
        wx = nx * self.world_size[0] + self.camera_x
        wy = ny * self.world_size[1] + self.camera_y
        return wx, wy

    def save_current_frame(self, output_path: str) -> None:
        self.draw_world()
        pygame.image.save(self.internal_surface, output_path)

    def _draw_host_fade(self, alpha: float) -> None:
        if alpha <= 0.0:
            return
        overlay = pygame.Surface(self.internal_surface.get_size(), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, int(clamp(alpha, 0.0, 1.0) * 255)))
        self.internal_surface.blit(overlay, (0, 0))

    def _fade_back_to_host(self) -> str:
        for step in range(18):
            alpha = (step + 1) / 18.0
            self.draw_world()
            self._draw_host_fade(alpha)
            self.present()
            self.clock.tick(60)
        self.pending_host_return = False
        return "return_to_host"

    # ---------- loop ----------

    def run(self) -> str:
        running = True
        while running:
            raw_dt = self.clock.tick(self.max_fps) / 1000.0
            self.last_fps = self.clock.get_fps()
            self.last_frame_time = raw_dt
            dt = min(raw_dt, 1.0 / 20.0)

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.VIDEORESIZE and not self.fullscreen:
                    self.window_size = (max(640, event.w), max(360, event.h))
                    self.screen = pygame.display.set_mode(self.window_size, pygame.RESIZABLE, vsync=self.vsync)
                elif event.type == pygame.MOUSEWHEEL:
                    self.zoom = clamp(self.zoom + (0.08 * event.y), 1.0, 2.5)
                    if event.y != 0:
                        self.camera_track_uid = None
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    wx, wy = self._screen_to_world(event.pos[0], event.pos[1])
                    hit = None
                    for unit in self.units:
                        if (unit.x - wx) ** 2 + (unit.y - wy) ** 2 <= 14 ** 2:
                            hit = unit
                            break
                    if hit is not None:
                        self.camera_track_uid = hit.uid
                    else:
                        self.camera_track_uid = None
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        if self.host_mode and self.return_to_host_on_escape:
                            self.pending_host_return = True
                            running = False
                        else:
                            running = False
                    elif event.key == pygame.K_h:
                        self.show_help = not self.show_help
                        self.show_ui = self.show_help
                        self.help_auto_hide = False
                    elif event.key == pygame.K_F11:
                        self._toggle_fullscreen()
                    elif event.key == pygame.K_v:
                        self._toggle_vsync()
                    elif event.key == pygame.K_r:
                        self.reset_battle()
                    elif event.key == pygame.K_m:
                        self._toggle_audio()
                    elif event.key == pygame.K_q:
                        self.zoom = clamp(self.zoom + 0.1, 1.0, 2.5)
                        self.camera_track_uid = None
                    elif event.key == pygame.K_e:
                        self.zoom = clamp(self.zoom - 0.1, 1.0, 2.5)
                        self.camera_track_uid = None
                    elif event.key == pygame.K_LEFT:
                        self.camera_x -= 35
                        self.camera_track_uid = None
                    elif event.key == pygame.K_RIGHT:
                        self.camera_x += 35
                        self.camera_track_uid = None
                    elif event.key == pygame.K_UP:
                        self.camera_y -= 35
                        self.camera_track_uid = None
                    elif event.key == pygame.K_DOWN:
                        self.camera_y += 35
                        self.camera_track_uid = None
                    elif event.key == pygame.K_l:
                        self.reload_assets()
                        self.reset_battle()
                    elif event.key == pygame.K_1:
                        self.pixel_scale = 1
                        self._rebuild_internal_surface()
                    elif event.key == pygame.K_2:
                        self.pixel_scale = 2
                        self._rebuild_internal_surface()
                    elif event.key == pygame.K_3:
                        self.pixel_scale = 3
                        self._rebuild_internal_surface()
                    elif event.key == pygame.K_4:
                        self.pixel_scale = 4
                        self._rebuild_internal_surface()
                    elif event.key == pygame.K_5:
                        self.pixel_scale = 5
                        self._rebuild_internal_surface()
                    elif event.key == pygame.K_6:
                        self.pixel_scale = 6
                        self._rebuild_internal_surface()

            self.update(dt)
            self.draw_world()
            if self.pending_host_return:
                self._draw_host_fade(0.55)
            self.present()
            if self.pending_host_return:
                return self._fade_back_to_host()

        if not self.host_mode:
            pygame.quit()
        return "quit"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Heaven vs Hell RTS")
    parser.add_argument("--capture-frame", metavar="PNG_PATH", help="Render one frame and save PNG, then exit.")
    return parser.parse_args()


def main(
    host_mode: bool = False,
    return_to_host_on_escape: bool = False,
    return_to_host_on_battle_end: bool = False,
    start_window_size: tuple[int, int] | None = None,
    start_fullscreen: bool = False,
    capture_frame: str | None = None,
) -> str | None:
    setup_crash_reporter()
    args = parse_args() if not host_mode else None

    random.seed()
    game = HeavenHellRTS(
        window_size=start_window_size,
        fullscreen=start_fullscreen,
        host_mode=host_mode,
        return_to_host_on_escape=return_to_host_on_escape,
        return_to_host_on_battle_end=return_to_host_on_battle_end,
    )

    frame_path = capture_frame or (args.capture_frame if args else None)
    if frame_path:
        game.save_current_frame(frame_path)
        if not host_mode:
            pygame.quit()
        return frame_path

    return game.run()


if __name__ == "__main__":
    main()
