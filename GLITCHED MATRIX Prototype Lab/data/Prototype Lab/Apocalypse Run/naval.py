#!/usr/bin/env python3
"""Naval Combat (Deep Pressure: Submarine Strike)

Embedded-ready single-file Pygame game.

This file supports two execution modes:
1) Standalone: running this file directly opens its own window.
2) Embedded (Doomsday launcher): the launcher imports this module and provides an
   `external_surface` to render into. The game runs inside the launcher and must
   NOT create or own the display.

Embed contract (what the Doomsday launcher expects):
  - A factory function named `create_embedded(...)` (or similar) OR a `Game` class.
  - The instance should implement `step(dt, events, present=False)` OR `update(dt, events)`.
  - The instance may implement `handle_event(ev, local_pos)` to receive localized
    mouse events (recommended for correct cursor coordinate use).
"""

from __future__ import annotations

import math
import os
import random
import struct
import time
import traceback
import wave
from typing import List, Optional, Tuple

import pygame


# ----------------------------
# Standalone defaults (embedded mode uses the provided surface size)
# ----------------------------

DEFAULT_W, DEFAULT_H = 1200, 720
FPS = 60

WORLD_WIDTH = 2400
WORLD_HEIGHT = 1200

SURFACE_Y = 120
SAFE_DEPTH = 650
MAX_DEPTH = 820

SEA_TOP_COLOR = (8, 35, 22)
SEA_DEEP_COLOR = (2, 10, 6)
SEA_SURFACE_COLOR = (40, 120, 70)
SAND_COLOR = (25, 50, 35)
HOLO_GLOW = (120, 255, 180)
HOLO_SOFT = (60, 180, 120)
HOLO_SCAN = (25, 80, 45)
NIGHT_VISION_TINT = (30, 120, 60)
CENTER_CLEAR_RADIUS = 220


def _base_dir() -> str:
    try:
        return os.path.dirname(os.path.abspath(__file__))
    except Exception:
        return os.getcwd()


BASE_DIR = _base_dir()
ASSET_DIR = os.path.join(BASE_DIR, "assets")
GENERATED_DIR = os.path.join(ASSET_DIR, "generated")
SFX_DIR = os.path.join(ASSET_DIR, "sfx")
CRASH_DIR = os.path.join(BASE_DIR, "crash_reports")


def ensure_dirs():
    os.makedirs(GENERATED_DIR, exist_ok=True)
    os.makedirs(SFX_DIR, exist_ok=True)
    os.makedirs(CRASH_DIR, exist_ok=True)
    marker = os.path.join(GENERATED_DIR, "assets_generated.txt")
    if not os.path.exists(marker):
        with open(marker, "w", encoding="utf-8") as handle:
            handle.write(
                "All visuals are generated in code. This folder exists so assets can be replaced if needed.\n"
            )
    generate_placeholder_sfx()


def clamp(value, low, high):
    return max(low, min(high, value))


def lerp(a, b, t):
    return a + (b - a) * t


def draw_vertical_gradient(surface, top_color, bottom_color):
    width, height = surface.get_size()
    if height <= 1:
        surface.fill(top_color)
        return
    for y in range(height):
        t = y / (height - 1)
        color = (
            int(lerp(top_color[0], bottom_color[0], t)),
            int(lerp(top_color[1], bottom_color[1], t)),
            int(lerp(top_color[2], bottom_color[2], t)),
        )
        pygame.draw.line(surface, color, (0, y), (width, y))


def draw_holographic_grid(surface, color, spacing=60, alpha=35):
    overlay = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
    width, height = surface.get_size()
    grid_color = (*color, alpha)
    for x in range(0, width, spacing):
        pygame.draw.line(overlay, grid_color, (x, 0), (x, height))
    for y in range(0, height, spacing):
        pygame.draw.line(overlay, grid_color, (0, y), (width, y))
    surface.blit(overlay, (0, 0))


def draw_scanlines(surface, color, spacing=6, alpha=25):
    overlay = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
    width, height = surface.get_size()
    line_color = (*color, alpha)
    for y in range(0, height, spacing):
        pygame.draw.line(overlay, line_color, (0, y), (width, y))
    surface.blit(overlay, (0, 0))


def draw_night_vision_overlay(surface, tint_color, alpha=60):
    overlay = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
    overlay.fill((*tint_color, alpha))
    surface.blit(overlay, (0, 0))


def generate_placeholder_sfx():
    sounds = {
        "attack": (440, 0.12, 0.4),
        "hit": (220, 0.1, 0.5),
        "implosion": (90, 0.6, 0.8),
        "sonar": (260, 0.4, 0.6),
        "engine": (120, 0.8, 0.3),
        "ambience": (60, 1.6, 0.2),
    }
    for name, (freq, duration, volume) in sounds.items():
        path = os.path.join(SFX_DIR, f"{name}.wav")
        if os.path.exists(path):
            continue
        write_tone_wav(path, freq, duration, volume)


def write_tone_wav(path, frequency, duration, volume):
    sample_rate = 22050
    total_samples = int(sample_rate * duration)
    with wave.open(path, "w") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        for i in range(total_samples):
            t = i / sample_rate
            value = math.sin(2 * math.pi * frequency * t)
            envelope = 1 - min(1, t / duration)
            sample = int(32767 * value * volume * envelope)
            handle.writeframes(struct.pack("<h", sample))


class SoundManager:
    def __init__(self):
        self.sounds = {}
        self.all_sounds = []
        self.engine_channel = None
        self.ambience_channel = None
        self.load_sounds()

    def load_sounds(self):
        try:
            if not os.path.isdir(SFX_DIR):
                return
            for file_name in os.listdir(SFX_DIR):
                if not file_name.lower().endswith((".wav", ".mp3")):
                    continue
                key = os.path.splitext(file_name)[0].lower()
                try:
                    sound = pygame.mixer.Sound(os.path.join(SFX_DIR, file_name))
                    self.sounds[key] = sound
                    self.all_sounds.append((key, sound))
                except pygame.error:
                    continue
        except Exception:
            return

    def resolve_sound(self, name):
        sound = self.sounds.get(name)
        if sound:
            return sound
        for key, loaded in self.all_sounds:
            if name in key:
                return loaded
        if self.all_sounds:
            return self.all_sounds[0][1]
        return None

    def play(self, name, volume=0.6):
        sound = self.resolve_sound(name)
        if sound:
            sound.set_volume(volume)
            sound.play()

    def loop(self, name, volume=0.4):
        sound = self.resolve_sound(name)
        if sound:
            sound.set_volume(volume)
            return sound.play(loops=-1)
        return None

    def start_engine(self):
        if self.engine_channel is None or not self.engine_channel.get_busy():
            self.engine_channel = self.loop("engine", volume=0.3)

    def stop_engine(self):
        if self.engine_channel and self.engine_channel.get_busy():
            self.engine_channel.fadeout(200)

    def start_ambience(self):
        if self.ambience_channel is None or not self.ambience_channel.get_busy():
            self.ambience_channel = self.loop("ambience", volume=0.25)


def create_submarine_surface(scale=4):
    grid = [
        "..................",
        "......111111......",
        "....1111111111....",
        "..11111111111111..",
        ".1111111111111111.",
        "111111111111111111",
        "111111111111111111",
        ".1111111111111111.",
        "..11111111111111..",
        "....1111111111....",
        "......111111......",
        "..................",
    ]
    width = len(grid[0])
    height = len(grid)
    surface = pygame.Surface((width * scale, height * scale), pygame.SRCALPHA)
    hull = (40, 95, 70)
    highlight = (60, 130, 95)
    canopy = (90, 200, 140)
    stripe = (140, 180, 120)

    for y, row in enumerate(grid):
        for x, cell in enumerate(row):
            if cell == "1":
                color = hull
                if 3 <= y <= 5:
                    color = highlight
                pygame.draw.rect(surface, color, (x * scale, y * scale, scale, scale))

    pygame.draw.rect(surface, stripe, (6 * scale, 7 * scale, 6 * scale, scale))
    pygame.draw.rect(surface, canopy, (9 * scale, 3 * scale, 2 * scale, 2 * scale))
    pygame.draw.rect(surface, canopy, (11 * scale, 3 * scale, 2 * scale, 2 * scale))

    return surface


def create_ship_surface(scale=4):
    grid = [
        "....2222....",
        "..22222222..",
        "222222222222",
        "222222222222",
        "222233222222",
        "222222222222",
    ]
    width = len(grid[0])
    height = len(grid)
    surface = pygame.Surface((width * scale, height * scale), pygame.SRCALPHA)
    hull = (40, 110, 80)
    deck = (60, 150, 100)
    tower = (90, 200, 140)

    for y, row in enumerate(grid):
        for x, cell in enumerate(row):
            if cell == "2":
                color = hull
                if y < 2:
                    color = deck
                pygame.draw.rect(surface, color, (x * scale, y * scale, scale, scale))
            elif cell == "3":
                pygame.draw.rect(surface, tower, (x * scale, y * scale, scale, scale * 2))

    return surface


def create_enemy_sub_surface(scale=4):
    grid = [
        "...........",
        "..444444...",
        ".44444444..",
        "4444444444",
        "4444444444",
        ".44444444..",
        "..444444...",
        "...........",
    ]
    width = len(grid[0])
    height = len(grid)
    surface = pygame.Surface((width * scale, height * scale), pygame.SRCALPHA)
    hull = (45, 120, 90)
    highlight = (70, 170, 120)
    eye = (160, 240, 180)

    for y, row in enumerate(grid):
        for x, cell in enumerate(row):
            if cell == "4":
                color = hull
                if 2 <= y <= 3:
                    color = highlight
                pygame.draw.rect(surface, color, (x * scale, y * scale, scale, scale))

    pygame.draw.rect(surface, eye, (7 * scale, 3 * scale, scale, scale))
    return surface


class Particle:
    def __init__(self, pos, velocity, color, radius, lifetime, fade=True, drift=1.0):
        self.pos = pygame.Vector2(pos)
        self.velocity = pygame.Vector2(velocity)
        self.color = color
        self.radius = radius
        self.lifetime = lifetime
        self.age = 0.0
        self.fade = fade
        self.drift = drift

    def update(self, dt):
        self.pos += self.velocity * dt * self.drift
        self.age += dt
        if self.fade:
            self.radius = max(0.0, self.radius - dt * 6)

    def draw(self, surface, offset):
        if self.radius <= 0:
            return
        alpha = 255
        if self.fade:
            alpha = int(255 * clamp(1 - self.age / self.lifetime, 0, 1))
        color = (*self.color, alpha)
        temp = pygame.Surface((self.radius * 2, self.radius * 2), pygame.SRCALPHA)
        pygame.draw.circle(temp, color, (self.radius, self.radius), self.radius)
        surface.blit(temp, (self.pos.x - self.radius - offset.x, self.pos.y - self.radius - offset.y))

    def alive(self):
        return self.age < self.lifetime


class Implosion:
    def __init__(self, pos):
        self.pos = pygame.Vector2(pos)
        self.time = 0.0
        self.duration = 2.5
        self.particles = []
        for _ in range(180):
            angle = random.uniform(0, math.tau)
            speed = random.uniform(30, 240)
            velocity = pygame.Vector2(math.cos(angle), math.sin(angle)) * speed
            color = random.choice([(180, 210, 240), (100, 150, 200), (60, 110, 160)])
            radius = random.uniform(3, 6)
            lifetime = random.uniform(1.4, 2.4)
            self.particles.append(Particle(self.pos, velocity, color, radius, lifetime))

    def update(self, dt):
        self.time += dt
        for particle in self.particles:
            direction = self.pos - particle.pos
            if direction.length() > 0:
                particle.velocity += direction.normalize() * 120 * dt
            particle.velocity *= 0.965
            particle.update(dt)
        self.particles = [p for p in self.particles if p.alive()]

    def draw(self, surface, offset):
        pulse = clamp(self.time / self.duration, 0, 1)
        for ring in range(3):
            radius = 90 + pulse * (240 - ring * 30)
            alpha = int(200 * (1 - pulse))
            ring_color = (120, 190, 255, alpha)
            temp = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
            pygame.draw.circle(temp, ring_color, (radius, radius), radius, 4)
            surface.blit(temp, (self.pos.x - radius - offset.x, self.pos.y - radius - offset.y))
        for particle in self.particles:
            particle.draw(surface, offset)

    def alive(self):
        return self.time < self.duration or bool(self.particles)


class Torpedo:
    def __init__(self, pos, direction):
        self.pos = pygame.Vector2(pos)
        self.velocity = pygame.Vector2(direction).normalize() * 420
        self.size = pygame.Vector2(2, 1)
        self.guided = True
        self.locked_target = None
        self.trail = []

    def update(self, dt, cursor_world):
        if self.guided:
            target = pygame.Vector2(cursor_world)
        else:
            target = pygame.Vector2(self.locked_target)

        direction = target - self.pos
        distance = direction.length()
        if distance > 1:
            self.velocity = direction.normalize() * 420
        self.pos += self.velocity * dt
        self.trail.append(self.pos.copy())
        if len(self.trail) > 8:
            self.trail.pop(0)

    def lock_target(self, target):
        self.guided = False
        self.locked_target = pygame.Vector2(target)

    def draw(self, surface, offset):
        for index, point in enumerate(self.trail):
            alpha = int(160 * (index / max(1, len(self.trail))))
            color = (120, 220, 170, alpha)
            trail_surface = pygame.Surface((2, 2), pygame.SRCALPHA)
            pygame.draw.rect(trail_surface, color, (0, 0, 2, 2))
            surface.blit(trail_surface, (point.x - offset.x, point.y - offset.y))
        pygame.draw.rect(
            surface,
            (200, 255, 210),
            (self.pos.x - offset.x, self.pos.y - offset.y, self.size.x, self.size.y),
        )

    def rect(self):
        return pygame.Rect(self.pos.x, self.pos.y, self.size.x, self.size.y)


class EnemyTorpedo:
    def __init__(self, pos, direction):
        self.pos = pygame.Vector2(pos)
        self.velocity = pygame.Vector2(direction).normalize() * 300
        self.size = pygame.Vector2(2, 1)
        self.trail = []

    def update(self, dt):
        self.pos += self.velocity * dt
        self.trail.append(self.pos.copy())
        if len(self.trail) > 6:
            self.trail.pop(0)

    def draw(self, surface, offset):
        for index, point in enumerate(self.trail):
            alpha = int(140 * (index / max(1, len(self.trail))))
            color = (90, 200, 140, alpha)
            trail_surface = pygame.Surface((2, 2), pygame.SRCALPHA)
            pygame.draw.rect(trail_surface, color, (0, 0, 2, 2))
            surface.blit(trail_surface, (point.x - offset.x, point.y - offset.y))
        pygame.draw.rect(
            surface,
            (140, 255, 190),
            (self.pos.x - offset.x, self.pos.y - offset.y, self.size.x, self.size.y),
        )

    def rect(self):
        return pygame.Rect(self.pos.x, self.pos.y, self.size.x, self.size.y)


class Mine:
    def __init__(self, pos):
        self.pos = pygame.Vector2(pos)
        self.radius = 12
        self.revealed_timer = 0.0

    def draw(self, surface, offset):
        if self.revealed_timer <= 0:
            return
        alpha = 200
        core = pygame.Surface((self.radius * 2, self.radius * 2), pygame.SRCALPHA)
        pygame.draw.circle(core, (80, 180, 120, alpha), (self.radius, self.radius), self.radius)
        surface.blit(core, (self.pos.x - self.radius - offset.x, self.pos.y - self.radius - offset.y))
        for angle in range(0, 360, 45):
            direction = pygame.Vector2(1, 0).rotate(angle)
            end = self.pos + direction * (self.radius + 6)
            spike_surface = pygame.Surface((6, 6), pygame.SRCALPHA)
            pygame.draw.line(spike_surface, (120, 220, 160, alpha), (3, 3), (6, 3), 2)
            surface.blit(spike_surface, (end.x - offset.x - 3, end.y - offset.y - 3))

    def rect(self):
        return pygame.Rect(self.pos.x - self.radius, self.pos.y - self.radius, self.radius * 2, self.radius * 2)


class Ship:
    def __init__(self, pos, direction):
        self.pos = pygame.Vector2(pos)
        self.direction = direction
        self.speed = 30
        self.hp = 3
        self.surface = create_ship_surface()
        self.surface_flipped = pygame.transform.flip(self.surface, True, False)
        self.wave_phase = random.uniform(0, math.tau)

    def update(self, dt):
        self.pos.x += self.direction * self.speed * dt
        self.wave_phase += dt * 1.4
        if self.pos.x < 60:
            self.pos.x = 60
            self.direction = 1
        elif self.pos.x > WORLD_WIDTH - 180:
            self.pos.x = WORLD_WIDTH - 180
            self.direction = -1

    def draw(self, surface, offset):
        bob = math.sin(self.wave_phase) * 3
        sprite = self.surface_flipped if self.direction < 0 else self.surface
        surface.blit(sprite, (self.pos.x - offset.x, self.pos.y - offset.y + bob))

    def rect(self):
        return self.surface.get_rect(topleft=self.pos)


class EnemySubmarine:
    def __init__(self, pos, direction):
        self.pos = pygame.Vector2(pos)
        self.direction = direction
        self.speed = 85
        self.hp = 3
        self.surface = create_enemy_sub_surface()
        self.surface_flipped = pygame.transform.flip(self.surface, True, False)
        self.oscillate = random.uniform(0, math.tau)
        self.fire_cooldown = random.uniform(1.2, 2.2)
        self.revealed_timer = 0.0
        self.spawn_timer = 3.0
        self.discovered = False

    def update(self, dt):
        self.spawn_timer = max(0.0, self.spawn_timer - dt)
        if self.discovered:
            self.pos.x += self.direction * self.speed * dt
            self.oscillate += dt * 2
            self.pos.y += math.sin(self.oscillate) * 8 * dt
        self.fire_cooldown = max(0.0, self.fire_cooldown - dt)
        self.revealed_timer = max(0.0, self.revealed_timer - dt)

    def emit_bubbles(self, particle_pool):
        spawn = self.pos + pygame.Vector2(10 if self.direction > 0 else 70, 20)
        for _ in range(2):
            velocity = pygame.Vector2(random.uniform(-10, 10), random.uniform(-40, -70))
            color = random.choice([(110, 200, 230), (140, 240, 255)])
            particle_pool.append(Particle(spawn, velocity, color, random.uniform(2, 3), 1.0, drift=0.9))

    def try_fire(self, target_pos):
        if self.fire_cooldown > 0 or self.spawn_timer > 0 or not self.discovered:
            return None
        direction = pygame.Vector2(target_pos) - self.pos
        if direction.length() < 1:
            return None
        self.fire_cooldown = random.uniform(1.4, 2.6)
        spawn = self.pos + pygame.Vector2(40, 18)
        return EnemyTorpedo(spawn, direction)

    def draw(self, surface, offset):
        alpha = 70 if self.revealed_timer <= 0 else 220
        sprite = self.surface_flipped if self.direction < 0 else self.surface
        ghost = pygame.Surface(sprite.get_size(), pygame.SRCALPHA)
        ghost.blit(sprite, (0, 0))
        ghost.fill((255, 255, 255, alpha), special_flags=pygame.BLEND_RGBA_MULT)
        surface.blit(ghost, (self.pos.x - offset.x, self.pos.y - offset.y))

    def rect(self):
        return self.surface.get_rect(topleft=self.pos)

    def offscreen(self):
        return self.pos.x < -200 or self.pos.x > WORLD_WIDTH + 200

    def deep_water(self):
        return self.pos.y > SAFE_DEPTH - 120


class Submarine:
    def __init__(self, pos):
        self.pos = pygame.Vector2(pos)
        self.velocity = pygame.Vector2(0, 0)
        self.alive = True
        self.surface = create_submarine_surface()
        self.surface_flipped = pygame.transform.flip(self.surface, True, False)
        self.cooldown = 0.0
        self.torpedo_cooldown = 0.45
        self.boost_timer = 0.0
        self.hull = 3

    def update(self, dt, move_vector):
        if not self.alive:
            return
        if self.boost_timer > 0:
            acceleration = pygame.Vector2(move_vector) * 360
            self.boost_timer = max(0.0, self.boost_timer - dt)
        else:
            acceleration = pygame.Vector2(move_vector) * 260
        self.velocity += acceleration * dt
        self.velocity *= 0.92
        self.velocity.x = clamp(self.velocity.x, -220, 220)
        self.velocity.y = clamp(self.velocity.y, -220, 220)
        self.pos += self.velocity * dt
        self.pos.x = clamp(self.pos.x, 40, WORLD_WIDTH - 160)
        self.pos.y = clamp(self.pos.y, SURFACE_Y + 30, MAX_DEPTH)
        self.cooldown = max(0.0, self.cooldown - dt)

    def boost(self):
        if self.boost_timer <= 0:
            self.boost_timer = 0.6

    def fire(self, direction):
        if self.cooldown > 0 or not self.alive:
            return None
        self.cooldown = self.torpedo_cooldown
        offset_x = 90 if direction.x >= 0 else 10
        spawn = self.pos + pygame.Vector2(offset_x, 20)
        return Torpedo(spawn, direction)

    def emit_bubbles(self, particle_pool):
        if self.velocity.length() < 20:
            return
        if self.velocity.x < 0:
            spawn = self.pos + pygame.Vector2(90, 22)
        else:
            spawn = self.pos + pygame.Vector2(12, 22)
        for _ in range(3):
            velocity = pygame.Vector2(random.uniform(-20, -40), random.uniform(-60, -90))
            color = random.choice([(100, 200, 230), (160, 240, 255)])
            particle_pool.append(Particle(spawn, velocity, color, random.uniform(2, 4), 1.2, drift=0.9))

    def draw(self, surface, offset, warning=False):
        sprite = self.surface_flipped if self.velocity.x < 0 else self.surface
        if warning:
            tinted = pygame.Surface(sprite.get_size(), pygame.SRCALPHA)
            tinted.blit(sprite, (0, 0))
            tinted.fill((255, 120, 120, 200), special_flags=pygame.BLEND_RGBA_MULT)
            surface.blit(tinted, (self.pos.x - offset.x, self.pos.y - offset.y))
        else:
            surface.blit(sprite, (self.pos.x - offset.x, self.pos.y - offset.y))

    def rect(self):
        return self.surface.get_rect(topleft=self.pos)


class EmbeddedNavalGame:
    """Naval game instance that can run standalone or embedded."""

    def __init__(self, external_surface: Optional[pygame.Surface] = None, doomsday_ctx=None):
        self.doomsday_ctx = doomsday_ctx or {}
        try:
            seed = self.doomsday_ctx.get('session_seed')
            if seed is not None:
                random.seed(int(seed))
        except Exception:
            pass
        ensure_dirs()

        # Pygame init is safe even when already initialized.
        pygame.init()
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init()
        except pygame.error:
            pass

        self.external_surface = external_surface
        self.screen = external_surface
        self.standalone = external_surface is None
        if self.standalone:
            self.screen = pygame.display.set_mode((DEFAULT_W, DEFAULT_H))
            pygame.display.set_caption("Deep Pressure: Submarine Strike")

        self.clock = pygame.time.Clock()
        self._events: List[pygame.event.Event] = []
        self.last_mouse_local = pygame.Vector2(self.screen.get_width() // 2, self.screen.get_height() // 2)

        self._rebuild_view_surfaces()

        self.sfx = SoundManager()
        self.sfx.start_ambience()

        self.submarine = Submarine((WORLD_WIDTH / 2, SURFACE_Y + 180))
        self.torpedoes: List[Torpedo] = []
        self.enemy_torpedoes: List[EnemyTorpedo] = []
        self.ships: List[Ship] = []
        self.enemy_subs: List[EnemySubmarine] = []
        self.mines: List[Mine] = []
        self.particles: List[Particle] = []
        self.implosions: List[Implosion] = []
        self.respawn_timer = 0.0
        self.spawn_ships()
        self.spawn_deep_enemies()
        self.spawn_mines()
        self.screen_shake = 0.0
        self.camera = pygame.Vector2(0, 0)
        self.enemy_spawn_timer = random.uniform(6, 12)
        self.sonar_timer = 0.0
        self.sonar_radius = 0.0
        self.sonar_origin = pygame.Vector2(self.submarine.pos)
        self._running = True

    def _rebuild_view_surfaces(self):
        w, h = self.screen.get_size()
        self.background = pygame.Surface((w, h))
        draw_vertical_gradient(self.background, SEA_TOP_COLOR, SEA_DEEP_COLOR)

    # ----------------------------
    # Doomsday embedded API
    # ----------------------------

    def handle_event(self, ev: pygame.event.Event, local_pos: Optional[Tuple[int, int]] = None):
        # Record local mouse position for correct aiming.
        if local_pos is not None:
            try:
                self.last_mouse_local.update(local_pos)
            except Exception:
                pass
        elif hasattr(ev, 'pos'):
            try:
                self.last_mouse_local.update(ev.pos)
            except Exception:
                pass

        # In embedded mode, the host handles QUIT; in standalone we still support it.
        self._events.append(ev)

    def step(self, dt: float, events: Optional[List[pygame.event.Event]] = None, present: bool = False):
        # The launcher will call step() with `events=[]` when we implement handle_event.
        # For safety, accept either source.
        if events:
            self._events.extend(events)

        # Standalone pump
        if self.standalone:
            self._events.extend(pygame.event.get())
            # keep mouse local updated
            try:
                self.last_mouse_local.update(pygame.mouse.get_pos())
            except Exception:
                pass

        # Detect resize (standalone only; embedded surface size is fixed by host)
        if self.standalone:
            for ev in self._events:
                if ev.type == pygame.VIDEORESIZE:
                    self.screen = pygame.display.set_mode((max(640, ev.w), max(360, ev.h)), pygame.RESIZABLE)
                    self._rebuild_view_surfaces()

        # Handle input events
        for ev in self._events:
            if ev.type == pygame.QUIT and self.standalone:
                self._running = False
            if ev.type == pygame.MOUSEBUTTONDOWN:
                if getattr(ev, 'button', None) == 1:
                    mouse_world = pygame.Vector2(getattr(ev, 'pos', self.last_mouse_local)) + self.camera
                    if self.torpedoes:
                        for torpedo in list(self.torpedoes):
                            self.add_explosion(torpedo.pos, True)
                            self.add_holo_spark(torpedo.pos)
                            self.sfx.play("hit", volume=0.5)
                            self.torpedoes.remove(torpedo)
                    else:
                        direction = mouse_world - self.submarine.pos
                        if direction.length() > 0:
                            torpedo = self.submarine.fire(direction)
                            if torpedo:
                                self.torpedoes.append(torpedo)
                                self.sfx.play("attack", volume=0.6)
                if getattr(ev, 'button', None) == 3:
                    self.sonar_timer = 1.2
                    self.sonar_radius = 0.0
                    self.sonar_origin = pygame.Vector2(self.submarine.pos)
                    self.sfx.play("sonar", volume=0.6)

        self._events.clear()

        # Update simulation
        self.update(dt)
        self.draw()

        if self.standalone and present:
            pygame.display.flip()

        return self._running

    # ----------------------------
    # Game logic
    # ----------------------------

    def clear_of_center(self, pos):
        center = pygame.Vector2(WORLD_WIDTH / 2, WORLD_HEIGHT / 2)
        return pygame.Vector2(pos).distance_to(center) > CENTER_CLEAR_RADIUS

    def reset_world(self):
        self.submarine = Submarine((WORLD_WIDTH / 2, SURFACE_Y + 180))
        self.torpedoes.clear()
        self.enemy_torpedoes.clear()
        self.particles.clear()
        self.implosions.clear()
        self.ships.clear()
        self.enemy_subs.clear()
        self.mines.clear()
        self.spawn_ships()
        self.spawn_deep_enemies()
        self.spawn_mines()
        self.enemy_spawn_timer = random.uniform(6, 12)
        self.sonar_timer = 0.0
        self.sonar_radius = 0.0
        self.sonar_origin = pygame.Vector2(self.submarine.pos)
        self.sfx.start_ambience()

    def apply_player_damage(self, amount, impact_pos):
        if not self.submarine.alive:
            return
        self.submarine.hull -= amount
        self.sfx.play("hit", volume=0.5)
        if self.submarine.hull <= 0:
            self.submarine.alive = False
            self.implosions.append(Implosion(impact_pos))
            self.sfx.play("implosion", volume=0.7)
            self.screen_shake = 1.2
            self.respawn_timer = 2.2

    def spawn_ships(self):
        self.ships = []
        for i in range(4):
            x = 200 + i * 420
            direction = 1 if i % 2 == 0 else -1
            pos = pygame.Vector2(x, SURFACE_Y - 30)
            if self.clear_of_center(pos):
                self.ships.append(Ship(pos, direction))

    def spawn_enemy_sub(self):
        side = random.choice([-1, 1])
        x = -120 if side == 1 else WORLD_WIDTH + 120
        y = random.uniform(SURFACE_Y + 140, SAFE_DEPTH - 40)
        direction = 1 if side == 1 else -1
        if self.clear_of_center((x, y)):
            self.enemy_subs.append(EnemySubmarine((x, y), direction))

    def spawn_deep_enemies(self):
        for _ in range(4):
            x = random.uniform(120, WORLD_WIDTH - 120)
            y = random.uniform(SAFE_DEPTH - 100, SAFE_DEPTH - 20)
            if self.clear_of_center((x, y)):
                direction = random.choice([-1, 1])
                self.enemy_subs.append(EnemySubmarine((x, y), direction))

    def spawn_mines(self):
        for _ in range(8):
            x = random.uniform(120, WORLD_WIDTH - 120)
            y = random.uniform(SAFE_DEPTH - 140, MAX_DEPTH - 40)
            if self.clear_of_center((x, y)):
                self.mines.append(Mine((x, y)))

    def add_explosion(self, pos, intense=False):
        for _ in range(34 if intense else 16):
            angle = random.uniform(0, math.tau)
            speed = random.uniform(60, 200 if intense else 130)
            velocity = pygame.Vector2(math.cos(angle), math.sin(angle)) * speed
            color = random.choice([(255, 180, 120), (255, 220, 180), (220, 140, 100)])
            radius = random.uniform(2, 4 if intense else 3)
            lifetime = random.uniform(0.8, 1.4 if intense else 1.0)
            self.particles.append(Particle(pos, velocity, color, radius, lifetime))

    def add_holo_spark(self, pos):
        for _ in range(10):
            angle = random.uniform(0, math.tau)
            speed = random.uniform(40, 140)
            velocity = pygame.Vector2(math.cos(angle), math.sin(angle)) * speed
            color = random.choice([(120, 220, 230), (90, 180, 220)])
            self.particles.append(Particle(pos, velocity, color, random.uniform(1.5, 2.5), 0.8))

    def read_move_input(self):
        keys = pygame.key.get_pressed()
        move_x = keys[pygame.K_d] - keys[pygame.K_a]
        move_y = keys[pygame.K_s] - keys[pygame.K_w]
        if keys[pygame.K_SPACE]:
            self.submarine.boost()
        if move_x != 0 or move_y != 0:
            move = pygame.Vector2(move_x, move_y)
            if move.length() > 0:
                move = move.normalize()
        else:
            move = pygame.Vector2(0, 0)
        return move

    def update(self, dt):
        move_vector = self.read_move_input()
        if self.submarine.alive:
            self.submarine.update(dt, move_vector)
            if self.submarine.velocity.length() > 30:
                self.sfx.start_engine()
            else:
                self.sfx.stop_engine()
        else:
            self.sfx.stop_engine()

        for ship in self.ships:
            ship.update(dt)

        for enemy in self.enemy_subs:
            enemy.update(dt)
            if random.random() < 0.12:
                enemy.emit_bubbles(self.particles)
            if enemy.fire_cooldown <= 0:
                shot = enemy.try_fire(self.submarine.pos)
                if shot:
                    self.enemy_torpedoes.append(shot)

        mouse_world = pygame.Vector2(self.last_mouse_local) + self.camera
        for torpedo in self.torpedoes:
            torpedo.update(dt, mouse_world)

        for torpedo in self.enemy_torpedoes:
            torpedo.update(dt)

        self.enemy_torpedoes = [
            torpedo
            for torpedo in self.enemy_torpedoes
            if -200 < torpedo.pos.x < WORLD_WIDTH + 200 and -200 < torpedo.pos.y < WORLD_HEIGHT + 200
        ]

        self.torpedoes = [
            torpedo
            for torpedo in self.torpedoes
            if -200 < torpedo.pos.x < WORLD_WIDTH + 200 and -200 < torpedo.pos.y < WORLD_HEIGHT + 200
        ]

        for torpedo in list(self.torpedoes):
            for ship in list(self.ships):
                if torpedo.rect().colliderect(ship.rect()):
                    ship.hp -= 1
                    self.add_explosion(torpedo.pos)
                    self.add_holo_spark(torpedo.pos)
                    self.sfx.play("hit", volume=0.5)
                    if ship.hp <= 0:
                        self.add_explosion(ship.pos + pygame.Vector2(50, 20), True)
                        self.sfx.play("implosion", volume=0.6)
                        chain_targets = []
                        for other_ship in self.ships:
                            if other_ship is ship:
                                continue
                            if other_ship.pos.distance_to(ship.pos) < 120:
                                chain_targets.append(other_ship)
                        for other_ship in chain_targets:
                            self.add_explosion(other_ship.pos + pygame.Vector2(50, 20), True)
                            self.sfx.play("implosion", volume=0.6)
                            self.ships.remove(other_ship)
                        if ship in self.ships:
                            self.ships.remove(ship)
                    if torpedo in self.torpedoes:
                        self.torpedoes.remove(torpedo)
                    break

        for torpedo in list(self.torpedoes):
            for enemy in list(self.enemy_subs):
                if torpedo.rect().colliderect(enemy.rect()):
                    enemy.hp -= 1
                    self.add_explosion(torpedo.pos, True)
                    self.add_holo_spark(torpedo.pos)
                    self.sfx.play("hit", volume=0.5)
                    if enemy.hp <= 0:
                        self.add_explosion(enemy.pos + pygame.Vector2(40, 20), True)
                        self.implosions.append(Implosion(enemy.pos + pygame.Vector2(40, 20)))
                        self.sfx.play("implosion", volume=0.6)
                        if enemy in self.enemy_subs:
                            self.enemy_subs.remove(enemy)
                    if torpedo in self.torpedoes:
                        self.torpedoes.remove(torpedo)
                    break

        for torpedo in list(self.enemy_torpedoes):
            if self.submarine.alive and torpedo.rect().colliderect(self.submarine.rect()):
                self.apply_player_damage(1, self.submarine.pos + pygame.Vector2(60, 20))
                if torpedo in self.enemy_torpedoes:
                    self.enemy_torpedoes.remove(torpedo)
                break

        for mine in list(self.mines):
            if self.submarine.alive and mine.rect().colliderect(self.submarine.rect()):
                self.add_explosion(mine.pos, True)
                self.mines.remove(mine)
                self.sfx.play("hit", volume=0.5)
                self.apply_player_damage(1, mine.pos)
                break

        for torpedo in list(self.torpedoes):
            for mine in list(self.mines):
                if torpedo.rect().colliderect(mine.rect()):
                    self.add_explosion(mine.pos, True)
                    self.mines.remove(mine)
                    self.sfx.play("hit", volume=0.5)
                    if torpedo in self.torpedoes:
                        self.torpedoes.remove(torpedo)
                    break

        depth = self.submarine.pos.y
        if self.submarine.alive and depth > SAFE_DEPTH:
            self.apply_player_damage(3, self.submarine.pos + pygame.Vector2(60, 20))

        if not self.ships:
            self.spawn_ships()

        if self.sonar_timer > 0:
            self.sonar_timer -= dt
            self.sonar_radius += dt * 600
            for enemy in self.enemy_subs:
                if enemy.deep_water():
                    distance = enemy.pos.distance_to(self.sonar_origin)
                    if distance <= self.sonar_radius:
                        enemy.revealed_timer = 3.0
                        enemy.discovered = True
            for mine in self.mines:
                distance = mine.pos.distance_to(self.sonar_origin)
                if distance <= self.sonar_radius:
                    mine.revealed_timer = 3.0

        for particle in self.particles:
            particle.update(dt)
        self.particles = [p for p in self.particles if p.alive()]

        for mine in self.mines:
            mine.revealed_timer = max(0.0, mine.revealed_timer - dt)

        for implosion in self.implosions:
            implosion.update(dt)
        self.implosions = [i for i in self.implosions if i.alive()]

        if not self.submarine.alive:
            self.respawn_timer -= dt
            if self.respawn_timer <= 0:
                self.reset_world()
        else:
            if random.random() < 0.18:
                self.submarine.emit_bubbles(self.particles)

        self.enemy_spawn_timer -= dt
        if self.enemy_spawn_timer <= 0:
            self.spawn_enemy_sub()
            self.enemy_spawn_timer = random.uniform(8, 14)

        self.enemy_subs = [enemy for enemy in self.enemy_subs if not enemy.offscreen()]

        self.update_camera()
        self.screen_shake = max(0.0, self.screen_shake - dt)

    def update_camera(self):
        w, h = self.screen.get_size()
        target = self.submarine.pos - pygame.Vector2(w / 2, h / 2)
        target.x = clamp(target.x, 0, WORLD_WIDTH - w)
        target.y = clamp(target.y, 0, WORLD_HEIGHT - h)
        self.camera = target

    def draw(self):
        w, h = self.screen.get_size()
        if self.background.get_size() != (w, h):
            self._rebuild_view_surfaces()

        self.screen.blit(self.background, (0, 0))
        draw_holographic_grid(self.screen, HOLO_SOFT)
        draw_scanlines(self.screen, HOLO_SCAN)
        draw_night_vision_overlay(self.screen, NIGHT_VISION_TINT, alpha=55)

        depth_ratio = clamp((self.submarine.pos.y - SURFACE_Y) / (MAX_DEPTH - SURFACE_Y), 0, 1)
        darkness_alpha = int(140 * depth_ratio)
        darkness = pygame.Surface((w, h), pygame.SRCALPHA)
        darkness.fill((0, 0, 0, darkness_alpha))
        self.screen.blit(darkness, (0, 0))

        surface_line_y = SURFACE_Y - self.camera.y
        surface_height = clamp(surface_line_y, 0, h)
        pygame.draw.rect(self.screen, SEA_SURFACE_COLOR, (0, 0, w, surface_height))
        if 0 <= surface_line_y <= h:
            pygame.draw.line(self.screen, (230, 240, 255), (0, surface_line_y), (w, surface_line_y), 2)
        sand_y = WORLD_HEIGHT - 70 - self.camera.y
        pygame.draw.rect(self.screen, SAND_COLOR, (0, sand_y, w, 90))

        if self.screen_shake > 0:
            offset = pygame.Vector2(
                random.uniform(-6, 6) * self.screen_shake,
                random.uniform(-6, 6) * self.screen_shake,
            )
        else:
            offset = pygame.Vector2(0, 0)

        holo_overlay = pygame.Surface((w, h), pygame.SRCALPHA)

        for ship in self.ships:
            ship.draw(self.screen, self.camera - offset)
        for enemy in self.enemy_subs:
            enemy.draw(self.screen, self.camera - offset)
        for torpedo in self.torpedoes:
            torpedo.draw(self.screen, self.camera - offset)
        for torpedo in self.enemy_torpedoes:
            torpedo.draw(self.screen, self.camera - offset)
        for mine in self.mines:
            mine.draw(self.screen, self.camera - offset)
        if self.submarine.alive:
            warning = self.submarine.pos.y > SAFE_DEPTH - 40
            self.submarine.draw(self.screen, self.camera - offset, warning=warning)
        for particle in self.particles:
            particle.draw(self.screen, self.camera - offset)
        for implosion in self.implosions:
            implosion.draw(self.screen, self.camera - offset)

        if self.sonar_timer > 0:
            radius = max(0, int(self.sonar_radius))
            pygame.draw.circle(
                self.screen,
                (120, 255, 180),
                (int(self.sonar_origin.x - self.camera.x), int(self.sonar_origin.y - self.camera.y)),
                radius,
                2,
            )

        pygame.draw.rect(holo_overlay, (*HOLO_GLOW, 45), (0, 0, w, h), 6)
        self.screen.blit(holo_overlay, (0, 0))


# ----------------------------
# Launcher entry points
# ----------------------------

def create_embedded(external_surface: pygame.Surface = None, **_kwargs):
    """Factory used by the Doomsday launcher."""
    return EmbeddedNavalGame(external_surface=external_surface)


def create_game(external_surface: pygame.Surface = None, **kwargs):
    return create_embedded(external_surface=external_surface, **kwargs)


def run_game():
    game = EmbeddedNavalGame(external_surface=None)
    running = True
    while running:
        dt = game.clock.tick(FPS) / 1000.0
        running = bool(game.step(dt, present=True))


if __name__ == "__main__":
    try:
        run_game()
    except Exception:
        ensure_dirs()
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        crash_path = os.path.join(CRASH_DIR, f"crash_{timestamp}.txt")
        with open(crash_path, "w", encoding="utf-8") as handle:
            handle.write("Deep Pressure crash report\n\n")
            handle.write(traceback.format_exc())
        print(f"A crash occurred. Report saved to {crash_path}")
        raise
