#!/usr/bin/env python3
"""
Code Red Arcade
External vehicle-combat testbed for Code RED Tuner settings.

The tuner writes runtime/arcade_settings.json. This app watches that file and
applies vehicle tune changes without needing the embedded tuner renderer to run.
It is intentionally dependency-light: Tkinter is the fallback renderer, while the
settings format drives the Panda3D renderer first, with Tkinter kept as the safe fallback.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import queue
import random
import socket
import struct
import sys
import threading
import time
import wave
import tkinter as tk
from dataclasses import dataclass, field
from pathlib import Path
from tkinter import ttk

APP_NAME = "Code Red Arcade"
APP_VERSION = "0.9.6-final"
DEFAULT_PORT = 47777

KEY_UP = {"w", "up"}
KEY_DOWN = {"s", "down"}
KEY_LEFT = {"a", "left"}
KEY_RIGHT = {"d", "right"}
KEY_BOOST = {"shift", "shift_l", "shift_r"}
KEY_FIRE = {"f", "control_l", "control_r"}
KEY_MISSILE = {"q", "e"}


def app_dir() -> Path:
    return Path(__file__).resolve().parent


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def angle_wrap(a: float) -> float:
    while a > math.pi:
        a -= math.tau
    while a < -math.pi:
        a += math.tau
    return a


def safe_float(data: dict, key: str, default: float) -> float:
    try:
        return float(data.get(key, default))
    except Exception:
        return default


@dataclass
class Projectile:
    x: float
    y: float
    vx: float
    vy: float
    owner: str
    ttl: float = 2.0
    damage: float = 1.0
    radius: float = 3.0
    color: str = "#ffdf6e"
    side: str = "center"


@dataclass
class TargetPart:
    name: str
    lx: float
    ly: float
    radius: float
    hp: float = 1.0
    destroyed: bool = False


def make_target_parts() -> list[TargetPart]:
    # Local vehicle coordinates use +X forward and +/-Y left/right. These are
    # small targetable chunks, not a giant shared health pool, so hits pop armor
    # off the car instead of deleting the whole target immediately.
    return [
        TargetPart("nose", 34.0, 0.0, 13.0, 1.35),
        TargetPart("hood", 20.0, 0.0, 15.0, 1.55),
        TargetPart("left_door", 3.0, -17.5, 12.0, 1.25),
        TargetPart("right_door", 3.0, 17.5, 12.0, 1.25),
        TargetPart("left_rear", -19.0, -17.5, 12.0, 1.25),
        TargetPart("right_rear", -19.0, 17.5, 12.0, 1.25),
        TargetPart("roof", -2.0, 0.0, 14.0, 1.65),
        TargetPart("tail", -34.0, 0.0, 13.0, 1.35),
    ]


def make_player_parts() -> list[TargetPart]:
    parts = make_target_parts()
    # Player vehicle survives longer; the body falls apart piece-by-piece before
    # a reset, instead of vanishing after a few hits.
    for part in parts:
        part.hp *= 3.10
        part.radius *= 1.08
    return parts


class SoundBank:
    """Replaceable arcade SFX loader.

    Drop replacement .wav/.ogg/.mp3 files into assets/sfx/arcade and name them
    with one of the event prefixes below, for example fire_left.wav or
    explosion_custom.ogg. Missing sounds never stop the game.
    """

    SUPPORTED_EXTS = (".wav", ".ogg", ".mp3")
    EVENTS = (
        "fire_left", "fire_right", "hit", "break", "explosion",
        "pickup", "boost", "jump", "land", "engine",
    )

    def __init__(self, folder: Path, enabled: bool = True):
        self.folder = Path(folder)
        self.enabled = bool(enabled)
        self.ready = False
        self.status = "audio off" if not enabled else "audio pending"
        self.sounds: dict[str, list[object]] = {}
        self.last_play: dict[str, float] = {}
        self.listener_x = 0.0
        self.listener_y = 0.0
        self.listener_heading = 0.0
        self.master_volume = 0.82
        self.sfx_volume = 0.86
        self.spatial_range = 1350.0
        self.engine_channel = None
        self._start()

    def _start(self) -> None:
        if not self.enabled:
            return
        try:
            self.folder.mkdir(parents=True, exist_ok=True)
            import pygame
            try:
                if not pygame.mixer.get_init():
                    pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
                try:
                    pygame.mixer.set_num_channels(24)
                except Exception:
                    pass
            except Exception:
                # In headless validation there may be no audio device. Runtime on
                # Windows still works when pygame can open the default device.
                self.status = "audio unavailable: no mixer device"
                return
            for event in self.EVENTS:
                loaded = []
                patterns = [f"{event}*{ext}" for ext in self.SUPPORTED_EXTS]
                for pattern in patterns:
                    for path in sorted(self.folder.glob(pattern)):
                        try:
                            loaded.append(pygame.mixer.Sound(str(path)))
                        except Exception:
                            continue
                if loaded:
                    self.sounds[event] = loaded
            count = sum(len(v) for v in self.sounds.values())
            self.ready = count > 0
            self.status = f"audio ready: {count} replaceable SFX" if count else f"audio ready: add SFX to {self.folder.name}"
        except Exception as exc:
            self.status = f"audio unavailable: {exc}"

    def set_listener(self, x: float, y: float, heading: float) -> None:
        self.listener_x = float(x)
        self.listener_y = float(y)
        self.listener_heading = float(heading)

    def set_mix(self, master: float = 0.82, sfx: float = 0.86) -> None:
        self.master_volume = clamp(float(master), 0.0, 1.0)
        self.sfx_volume = clamp(float(sfx), 0.0, 1.0)

    def _stereo_for(self, x: float | None, y: float | None, volume: float, loud: bool = False) -> tuple[float, float]:
        base = clamp(float(volume), 0.0, 1.0) * self.master_volume * self.sfx_volume
        if x is None or y is None:
            return base, base
        dx = float(x) - self.listener_x
        dy = float(y) - self.listener_y
        dist = math.hypot(dx, dy)
        if loud:
            falloff = clamp(1.0 - dist / (self.spatial_range * 2.15), 0.18, 1.0)
        else:
            falloff = clamp(1.0 - (dist / self.spatial_range) ** 1.18, 0.0, 1.0)
        right_x = -math.sin(self.listener_heading)
        right_y = math.cos(self.listener_heading)
        lateral = 0.0 if dist < 0.001 else clamp((dx * right_x + dy * right_y) / max(dist, 1.0), -1.0, 1.0)
        pan = lateral * 0.72
        left = base * falloff * clamp(1.0 - pan, 0.18, 1.0)
        right = base * falloff * clamp(1.0 + pan, 0.18, 1.0)
        return left, right

    def play(self, event: str, volume: float = 0.72, throttle: float = 0.0, x: float | None = None, y: float | None = None, loud: bool = False) -> None:
        if not self.ready:
            return
        now = time.monotonic()
        key = f"{event}:{'world' if x is not None or y is not None else 'local'}"
        if throttle and now - self.last_play.get(key, -999.0) < throttle:
            return
        choices = self.sounds.get(event) or self.sounds.get(event.split("_", 1)[0])
        if not choices:
            return
        self.last_play[key] = now
        try:
            snd = random.choice(choices)
            channel = snd.play()
            if channel is not None:
                left, right = self._stereo_for(x, y, volume, loud=loud)
                try:
                    channel.set_volume(left, right)
                except TypeError:
                    channel.set_volume((left + right) * 0.5)
        except Exception:
            pass

    def update_engine(self, speed: float, boosting: bool = False) -> None:
        if not self.ready or not self.sounds.get("engine"):
            return
        try:
            target = clamp(0.10 + abs(float(speed)) / 90.0 * 0.34 + (0.18 if boosting else 0.0), 0.06, 0.58) * self.master_volume * self.sfx_volume
            if self.engine_channel is None or not self.engine_channel.get_busy():
                self.engine_channel = random.choice(self.sounds["engine"]).play(loops=-1)
            if self.engine_channel is not None:
                self.engine_channel.set_volume(target, target)
        except Exception:
            pass


@dataclass
class Rival:
    x: float
    y: float
    heading: float
    speed: float = 0.0
    hp: float = 1.0
    cooldown: float = 0.0
    color: str = "#db3b32"
    name: str = "Rival"
    parts: list[TargetPart] = field(default_factory=make_target_parts)


@dataclass
class Pickup:
    x: float
    y: float
    kind: str
    pulse: float = 0.0


@dataclass
class Pedestrian:
    x: float
    y: float
    vx: float = 0.0
    vy: float = 0.0
    pulse: float = 0.0
    alive: bool = True
    respawn_timer: float = 0.0
    name: str = "ped"


@dataclass
class PropCollider:
    x: float
    y: float
    radius: float
    mass: float
    damage_scale: float
    name: str
    kind: str = "solid"
    hp: float = 6.0
    node: object | None = None


@dataclass
class PeerState:
    player_id: str
    x: float
    y: float
    heading: float
    hp: float
    vehicle: str
    updated: float = field(default_factory=time.monotonic)


class LanGhostBridge:
    """Tiny UDP peer broadcaster for LAN ghost clients.

    This is deliberately lightweight and optional. It lets separate machines on
    the same LAN see each other's arcade cars without changing the single-player
    sim loop. If networking fails, the arcade continues offline.
    """

    def __init__(self, player_id: str, port: int = DEFAULT_PORT):
        self.player_id = player_id
        self.port = int(port)
        self.inbox: "queue.Queue[dict]" = queue.Queue(maxsize=128)
        self.running = False
        self.sock: socket.socket | None = None
        self.thread: threading.Thread | None = None
        self.last_send = 0.0
        self.status = "offline"

    def start(self) -> None:
        if self.running:
            return
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("", self.port))
            sock.settimeout(0.2)
            self.sock = sock
            self.running = True
            self.thread = threading.Thread(target=self._recv_loop, name="CodeRedArcadeLAN", daemon=True)
            self.thread.start()
            self.status = f"LAN ghosts on UDP {self.port}"
        except Exception as exc:
            self.running = False
            self.status = f"LAN disabled: {exc}"

    def stop(self) -> None:
        self.running = False
        if self.sock is not None:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None

    def _recv_loop(self) -> None:
        while self.running and self.sock is not None:
            try:
                raw, _addr = self.sock.recvfrom(4096)
                if not raw.startswith(b"CRARCADE1\0"):
                    continue
                payload = json.loads(raw.split(b"\0", 1)[1].decode("utf-8", "replace"))
                if payload.get("id") == self.player_id:
                    continue
                try:
                    self.inbox.put_nowait(payload)
                except queue.Full:
                    pass
            except socket.timeout:
                continue
            except OSError:
                break
            except Exception:
                continue

    def send_state(self, state: dict) -> None:
        if not self.running or self.sock is None:
            return
        now = time.monotonic()
        if now - self.last_send < 0.10:
            return
        self.last_send = now
        try:
            payload = dict(state)
            payload["id"] = self.player_id
            packet = b"CRARCADE1\0" + json.dumps(payload, separators=(",", ":")).encode("utf-8")
            self.sock.sendto(packet, ("255.255.255.255", self.port))
        except Exception:
            pass

    def drain(self) -> list[dict]:
        out: list[dict] = []
        while True:
            try:
                out.append(self.inbox.get_nowait())
            except queue.Empty:
                return out


class ArcadeApp(tk.Tk):
    def __init__(self, settings_path: Path, lan: bool = False, port: int = DEFAULT_PORT):
        super().__init__()
        self.settings_path = settings_path
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        self.settings_mtime = 0.0
        self.settings: dict = {}
        self.vehicle_values: dict[str, float] = {}
        self.vehicle_name = "Car01"
        self.vehicle_asset_status = "vehicle asset pending"
        self._vehicle_source_np = None
        self._vehicle_glb_cache = None
        self._vehicle_accessor_cache = {}
        self.player_wheel_phase = 0.0
        self.rival_wheel_phases = [0.0 for _ in range(8)]
        self.scene_dt = 1.0 / 60.0
        self.arcade_options: dict = {}
        self.seed = random.randint(10000, 999999)
        self.running = True
        self.paused = False
        self.keys: set[str] = set()
        self.mouse_buttons: set[int] = set()
        self.mouse_x = 0
        self.mouse_y = 0
        self.focused = True
        self.last_tick = time.monotonic()
        self.frame_accum = 0.0
        self.fps = 0
        self.frame_counter = 0
        self.last_fps_time = time.monotonic()
        self.x = 0.0
        self.y = 0.0
        self.vx = 0.0
        self.vy = 0.0
        self.heading = 0.0
        self.hp = 6.0
        self.max_hp = 6.0
        self.score = 0
        self.wave = 1
        self.kills = 0
        self.fire_cooldown = 0.0
        self.missile_cooldown = 0.0
        self.left_flash_timer = 0.0
        self.right_flash_timer = 0.0
        self.boost_heat = 0.0
        self.projectiles: list[Projectile] = []
        self.rivals: list[Rival] = []
        self.pickups: list[Pickup] = []
        self.pedestrians: list[Pedestrian] = []
        self.locked_rival_name: str | None = None
        self.splatter_marks: list[tuple[float, float, float, float]] = []
        self.explosions: list[tuple[float, float, float, float]] = []
        self.muzzle_flashes: list[tuple[float, float, float, str]] = []
        self.peers: dict[str, PeerState] = {}
        self.status_var: tk.StringVar | None = None
        self.player_id = f"arcade-{os.getpid()}-{random.randint(1000,9999)}"
        self.lan = LanGhostBridge(self.player_id, port) if lan else None
        if self.lan:
            self.lan.start()
        self.sound = SoundBank(app_dir() / "assets" / "sfx" / "arcade", enabled=True)
        self._load_settings(force=True)
        self._init_ui()
        self._spawn_wave(reset=True)
        self._spawn_pickups()
        self._spawn_pedestrians()
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.bind("<FocusIn>", lambda _e: self._set_focus(True))
        self.bind("<FocusOut>", lambda _e: self._set_focus(False))
        self.after(16, self._tick)

    def _init_ui(self) -> None:
        self.title(f"{APP_NAME} {APP_VERSION}")
        self.geometry("1920x1080")
        self.minsize(1280, 720)
        self.configure(bg="#090305")
        top = ttk.Frame(self, padding=(10, 8))
        top.pack(fill="x")
        ttk.Label(top, text="Code Red Arcade", font=("Segoe UI", 14, "bold")).pack(side="left")
        ttk.Label(top, text="external open-world vehicle combat tune test", foreground="#b78b92").pack(side="left", padx=12)
        ttk.Button(top, text="Close App", command=self._close).pack(side="right")
        ttk.Button(top, text="Reset Run", command=self._reset_run).pack(side="right", padx=(0, 8))
        self.status_var = tk.StringVar(value=f"{self.vehicle_name} settings loaded • {self.settings_path.name}")
        ttk.Label(top, textvariable=self.status_var, foreground="#9aa6b2").pack(side="right", padx=(0, 10))
        self.canvas = tk.Canvas(self, bg="#090305", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.focus_set()
        self.canvas.bind("<KeyPress>", self._key_down)
        self.canvas.bind("<KeyRelease>", self._key_up)
        self.canvas.bind("<ButtonPress>", self._mouse_down)
        self.canvas.bind("<ButtonRelease>", self._mouse_up)
        self.canvas.bind("<Motion>", self._mouse_move)
        self.canvas.bind("<Leave>", lambda _e: self.mouse_buttons.clear())

    def _set_focus(self, focused: bool) -> None:
        self.focused = focused
        if focused:
            self.canvas.focus_set()
        else:
            # Release controls so it never keeps driving/firing in the background.
            self.keys.clear()
            self.mouse_buttons.clear()

    def _close(self) -> None:
        self.running = False
        if self.lan:
            self.lan.stop()
        self.destroy()

    def _key_down(self, event) -> None:
        key = str(event.keysym).lower()
        if key in ("escape", "p"):
            self.paused = not self.paused
            return
        if key == "space":
            self._cycle_lock_target()
            return
        if key == "f":
            try:
                self.attributes("-fullscreen", not bool(self.attributes("-fullscreen")))
            except Exception:
                pass
            return
        self.keys.add(key)

    def _key_up(self, event) -> None:
        self.keys.discard(str(event.keysym).lower())

    def _mouse_down(self, event) -> None:
        self.canvas.focus_set()
        self.mouse_buttons.add(int(getattr(event, "num", 1)))
        self._mouse_move(event)

    def _mouse_up(self, event) -> None:
        self.mouse_buttons.discard(int(getattr(event, "num", 1)))

    def _mouse_move(self, event) -> None:
        self.mouse_x = int(event.x)
        self.mouse_y = int(event.y)

    def _load_settings(self, force: bool = False) -> None:
        try:
            mtime = self.settings_path.stat().st_mtime
        except FileNotFoundError:
            if not self.settings:
                self.settings = self._fallback_settings()
                self.vehicle_values = self.settings["vehicles"]["Car01"]
            return
        if not force and mtime <= self.settings_mtime:
            return
        self.settings_mtime = mtime
        try:
            data = json.loads(self.settings_path.read_text(encoding="utf-8"))
        except Exception:
            return
        self.settings = data if isinstance(data, dict) else self._fallback_settings()
        self.vehicle_name = str(self.settings.get("active_vehicle", "Car01"))
        vehicles = self.settings.get("vehicles", {}) if isinstance(self.settings.get("vehicles"), dict) else {}
        values = vehicles.get(self.vehicle_name) if isinstance(vehicles.get(self.vehicle_name), dict) else None
        if not values:
            values = self._fallback_settings()["vehicles"]["Car01"]
        self.vehicle_values = {str(k): float(v) for k, v in values.items() if isinstance(v, (int, float))}
        self.arcade_options = self.settings.get("arcade", {}) if isinstance(self.settings.get("arcade"), dict) else {}
        if hasattr(self, "base"):
            self._apply_display_settings(initial=False)
        if hasattr(self, "sound"):
            self.sound.set_mix(float(self.arcade_options.get("master_volume", 0.82)), float(self.arcade_options.get("sfx_volume", 0.86)))
        old_seed = self.seed
        self.seed = int(self.arcade_options.get("world_seed", self.seed or 1) or 1)
        if self.seed != old_seed:
            self._spawn_wave(reset=True)
            self._spawn_pickups()
            self._spawn_pedestrians()
        if self.status_var is not None:
            self.status_var.set(f"{self.vehicle_name} settings loaded • {self.settings_path.name}")

    def _fallback_settings(self) -> dict:
        return {
            "active_vehicle": "Car01",
            "vehicles": {"Car01": {
                "mass": 2350, "horsepower": 210, "boost_torque": 70, "boost_duration": 1.2,
                "high_mph": 52, "front_static": 2.1, "rear_static": 2.1,
                "front_slide": 1.95, "rear_slide": 1.95, "front_steer": 0.62,
                "aero_drag": 1.05, "offroad_drag": 0.0, "downforce": 0.35,
                "handbrake": 0.28, "com_z": -0.72,
            }},
            "arcade": {"rival_count": 4, "world_seed": self.seed, "terrain_quality": "Balanced", "weapons_enabled": True, "camera_fov": 88.0, "camera_zoom": 1.72, "rivals_fire": True},
        }

    def _stat_block(self) -> dict[str, float]:
        v = self.vehicle_values
        mass = max(safe_float(v, "mass", 2350.0), 500.0)
        hp = safe_float(v, "horsepower", 210.0)
        high_mph = safe_float(v, "high_mph", 52.0)
        grip = (safe_float(v, "front_static", 2.0) + safe_float(v, "rear_static", 2.0) + safe_float(v, "front_slide", 1.8) + safe_float(v, "rear_slide", 1.8)) / 4.0
        steer = safe_float(v, "front_steer", 0.6)
        drag = safe_float(v, "aero_drag", 1.0) + safe_float(v, "offroad_drag", 0.0) * 0.4
        down = safe_float(v, "downforce", 0.35)
        boost = safe_float(v, "boost_torque", 70.0) * max(0.2, safe_float(v, "boost_duration", 1.0))
        com_z = safe_float(v, "com_z", -0.7)
        accel = clamp((hp + boost * 0.08) / mass * 92.0, 3.0, 34.0)
        max_speed = clamp(high_mph * 0.82 + hp / mass * 92.0, 18.0, 92.0)
        turn_rate = clamp(steer * (1.72 + grip * 0.24), 0.45, 3.75)
        friction = clamp(0.965 + grip * 0.006 + down * 0.002 - drag * 0.005, 0.90, 0.992)
        stability = clamp(0.72 + (-com_z) * 0.16 + grip * 0.035, 0.35, 1.15)
        return {"accel": accel, "max_speed": max_speed, "turn_rate": turn_rate, "friction": friction, "stability": stability, "grip": grip, "drag": drag}

    def _reset_run(self) -> None:
        self.x = 0.0
        self.y = 0.0
        self.vx = 0.0
        self.vy = 0.0
        self.heading = 0.0
        self.hp = self.max_hp
        self.score = 0
        self.wave = 1
        self.kills = 0
        self.projectiles.clear()
        self.explosions.clear()
        self.muzzle_flashes.clear()
        self.splatter_marks.clear()
        self.locked_rival_name = None
        self._spawn_wave(reset=True)
        self._spawn_pickups()
        self._spawn_pedestrians()

    def _spawn_wave(self, reset: bool = False) -> None:
        rng = random.Random(self.seed + self.wave * 177)
        base_count = int(clamp(float(self.arcade_options.get("rival_count", 4)), 0, 10))
        count = int(clamp(base_count + max(0, self.wave - 1), 0, 16))
        if reset:
            self.rivals.clear()
        while len(self.rivals) < count:
            dist = rng.uniform(260, 520)
            ang = rng.uniform(-math.pi, math.pi)
            self.rivals.append(Rival(
                self.x + math.cos(ang) * dist,
                self.y + math.sin(ang) * dist,
                rng.uniform(-math.pi, math.pi),
                hp=2.5 + self.wave * 0.45,
                color=rng.choice(["#e4573f", "#d13fd1", "#ff8e2b", "#c83434"]),
                name=f"Rival {len(self.rivals) + 1}",
            ))

    def _spawn_pickups(self) -> None:
        rng = random.Random(self.seed + 411)
        self.pickups = []
        for i in range(28):
            self.pickups.append(Pickup(rng.uniform(-2200, 2200), rng.uniform(-2200, 2200), rng.choice(["repair", "score", "boost"])))

    def _spawn_pedestrians(self) -> None:
        rng = random.Random(self.seed + 9121)
        self.pedestrians = []
        for i in range(18):
            ang = rng.uniform(-math.pi, math.pi)
            dist = rng.uniform(260, 1850)
            self.pedestrians.append(Pedestrian(self.x + math.cos(ang) * dist, self.y + math.sin(ang) * dist, rng.uniform(-0.32, 0.32), rng.uniform(-0.32, 0.32), name=f"ped_{i+1}"))

    def _locked_rival(self) -> Rival | None:
        live = [r for r in self.rivals if not self._rival_destroyed(r)]
        if not live:
            self.locked_rival_name = None
            return None
        if self.locked_rival_name:
            for r in live:
                if r.name == self.locked_rival_name:
                    return r
        nearest = min(live, key=lambda r: (r.x - self.x) ** 2 + (r.y - self.y) ** 2)
        self.locked_rival_name = nearest.name
        return nearest

    def _cycle_lock_target(self) -> None:
        live = sorted([r for r in self.rivals if not self._rival_destroyed(r)], key=lambda r: math.atan2(r.y - self.y, r.x - self.x))
        if not live:
            self.locked_rival_name = None
            return
        names = [r.name for r in live]
        if self.locked_rival_name in names:
            self.locked_rival_name = names[(names.index(self.locked_rival_name) + 1) % len(names)]
        else:
            nearest = min(live, key=lambda r: (r.x - self.x) ** 2 + (r.y - self.y) ** 2)
            self.locked_rival_name = nearest.name

    def _burst_fx(self, x: float, y: float, size: float = 36.0, count: int = 5) -> None:
        for i in range(max(1, count)):
            a = math.tau * (i / max(1, count)) + random.uniform(-0.20, 0.20)
            d = random.uniform(4.0, size * 0.42)
            self.explosions.append((x + math.cos(a) * d, y + math.sin(a) * d, 0.0, size * random.uniform(0.38, 0.82)))

    def _update_pedestrians(self, dt: float) -> None:
        rng = random.Random(int(time.time() * 3) + self.seed)
        speed = math.hypot(self.vx, self.vy)
        for ped in list(self.pedestrians):
            if not ped.alive:
                ped.respawn_timer -= dt
                if ped.respawn_timer <= 0:
                    ang = rng.uniform(-math.pi, math.pi); dist = rng.uniform(750, 2200)
                    ped.x = self.x + math.cos(ang) * dist; ped.y = self.y + math.sin(ang) * dist
                    ped.vx = rng.uniform(-0.35, 0.35); ped.vy = rng.uniform(-0.35, 0.35); ped.alive = True
                continue
            ped.pulse += dt
            if rng.random() < 0.018:
                ped.vx += rng.uniform(-0.10, 0.10); ped.vy += rng.uniform(-0.10, 0.10)
            ped.vx = clamp(ped.vx, -0.62, 0.62); ped.vy = clamp(ped.vy, -0.62, 0.62)
            ped.x += ped.vx; ped.y += ped.vy
            if (ped.x - self.x) ** 2 + (ped.y - self.y) ** 2 < 35 ** 2 and speed > 4.0:
                ped.alive = False; ped.respawn_timer = rng.uniform(3.0, 6.5)
                self.score += 15 + int(min(speed, 60))
                self.splatter_marks.append((ped.x, ped.y, 0.0, 42.0))
                self._burst_fx(ped.x, ped.y, 32.0, 4)
                if hasattr(self, "sound"):
                    self.sound.play("hit", 0.55, throttle=0.04, loud=True)
        self.splatter_marks = [(x, y, age + dt, size) for x, y, age, size in self.splatter_marks if age < 5.5][-48:]

    def _tick(self) -> None:
        if not self.running:
            return
        now = time.monotonic()
        dt = clamp(now - self.last_tick, 0.001, 0.05)
        self.last_tick = now
        self.scene_dt = dt
        self._load_settings()
        if self.focused and not self.paused:
            self._update_world(dt)
            target_ms = 16
        else:
            target_ms = 110
        self._draw()
        self.after(target_ms, self._tick)

    def _update_world(self, dt: float) -> None:
        s = self._stat_block()
        accelerating = bool(self.keys & KEY_UP)
        braking = bool(self.keys & KEY_DOWN)
        left = bool(self.keys & KEY_LEFT)
        right = bool(self.keys & KEY_RIGHT)
        boosting = bool(self.keys & KEY_BOOST) and self.boost_heat < 1.0
        speed = math.hypot(self.vx, self.vy)
        # Controls are intentionally inverted from the first prototype pass so A/Left
        # and D/Right match the visual steering in the Panda3D vehicle rig.
        steer_sign = (1 if left else 0) + (-1 if right else 0)
        if steer_sign:
            self.heading += steer_sign * s["turn_rate"] * dt * (0.82 + min(speed / max(s["max_speed"], 1.0), 1.55))
        ax = math.cos(self.heading)
        ay = math.sin(self.heading)
        if accelerating:
            power = s["accel"] * (1.65 if boosting else 1.0)
            self.vx += ax * power * dt
            self.vy += ay * power * dt
        if braking:
            self.vx -= ax * s["accel"] * 0.62 * dt
            self.vy -= ay * s["accel"] * 0.62 * dt
        if boosting:
            if not self.was_boosting:
                self.sound.play("boost", 0.70, throttle=0.35, loud=True)
            self.boost_heat = min(1.0, self.boost_heat + dt * 0.42)
        else:
            self.boost_heat = max(0.0, self.boost_heat - dt * 0.20)
        self.was_boosting = boosting
        # Open-world terrain roughness. No one-way guide track: everything is based
        # on procedural terrain under the car.
        rough = self._terrain_roughness(self.x, self.y)
        friction = s["friction"] - rough * 0.025
        self.vx *= friction
        self.vy *= friction
        speed = math.hypot(self.vx, self.vy)
        max_speed = s["max_speed"] * (1.18 if boosting else 1.0) * (1.0 - rough * 0.08)
        if speed > max_speed:
            scale = max_speed / max(speed, 0.0001)
            self.vx *= scale
            self.vy *= scale
        self.x += self.vx
        self.y += self.vy
        # LMB drives the left turret; RMB drives the right turret.
        # Keyboard aliases stay readable for fallback controls.
        if 1 in self.mouse_buttons or bool(self.keys & KEY_FIRE):
            self._fire("left")
        if 3 in self.mouse_buttons or bool(self.keys & KEY_MISSILE):
            self._fire("right")
        self.fire_cooldown = max(0.0, self.fire_cooldown - dt)
        self.missile_cooldown = max(0.0, self.missile_cooldown - dt)
        self.left_flash_timer = max(0.0, self.left_flash_timer - dt)
        self.right_flash_timer = max(0.0, self.right_flash_timer - dt)
        self._update_projectiles(dt)
        self._update_rivals(dt)
        self._update_pickups(dt)
        self._update_pedestrians(dt)
        self._update_peers()
        if not self.rivals:
            self.wave += 1
            self._spawn_wave(reset=True)
        self.frame_counter += 1
        if time.monotonic() - self.last_fps_time >= 1.0:
            self.fps = self.frame_counter
            self.frame_counter = 0
            self.last_fps_time = time.monotonic()

    def _terrain_roughness(self, x: float, y: float) -> float:
        return clamp((math.sin(x * 0.006 + self.seed) + math.cos(y * 0.005 - self.seed * 0.3) + math.sin((x + y) * 0.002)) / 6.0 + 0.28, 0.0, 0.75)

    def _aim_angle(self) -> float:
        w = max(self.canvas.winfo_width(), 1)
        h = max(self.canvas.winfo_height(), 1)
        return math.atan2(self.mouse_y - h * 0.5, self.mouse_x - w * 0.5)

    def _muzzle_world(self, base_x: float, base_y: float, heading: float, side: str) -> tuple[float, float, float]:
        # Side turrets are mounted outside the doors and fire straight forward.
        local_y = -24.0 if side == "left" else 24.0
        local_x = 43.0
        wx = base_x + math.cos(heading) * local_x - math.sin(heading) * local_y
        wy = base_y + math.sin(heading) * local_x + math.cos(heading) * local_y
        return wx, wy, heading

    def _apply_rival_part_damage(self, rival: Rival, hit_x: float, hit_y: float, damage: float) -> TargetPart | None:
        live_parts = [p for p in rival.parts if not p.destroyed]
        if not live_parts:
            return None
        dx = hit_x - rival.x
        dy = hit_y - rival.y
        ch = math.cos(rival.heading)
        sh = math.sin(rival.heading)
        lx = ch * dx + sh * dy
        ly = -sh * dx + ch * dy
        part = min(live_parts, key=lambda p: (p.lx - lx) ** 2 + (p.ly - ly) ** 2)
        part.hp -= max(0.15, damage)
        if part.hp <= 0.0:
            part.destroyed = True
            self.score += 45
        live_left = [p for p in rival.parts if not p.destroyed]
        rival.hp = max(0.0, len(live_left) / max(1, len(rival.parts)))
        return part

    def _rival_destroyed(self, rival: Rival) -> bool:
        return all(p.destroyed for p in rival.parts)

    def _fire(self, side: str = "left") -> None:
        if not bool(self.arcade_options.get("weapons_enabled", True)):
            return
        side = "right" if side == "right" else "left"
        if side == "left":
            if self.fire_cooldown > 0:
                return
            self.fire_cooldown = 0.095
            self.left_flash_timer = 0.08
            color = "#ffdf6e"
        else:
            if self.missile_cooldown > 0:
                return
            self.missile_cooldown = 0.135
            self.right_flash_timer = 0.08
            color = "#67d7ff"
        speed = 20.0
        dmg = 0.52
        radius = 2.8
        locked = self._locked_rival()
        if locked is not None:
            aim = math.atan2(locked.y - self.y, locked.x - self.x)
        else:
            aim = self.heading + angle_wrap(self._aim_angle()) * 0.20
        px, py, _ = self._muzzle_world(self.x, self.y, aim, side)
        self.muzzle_flashes.append((px, py, 0.0, side))
        self.projectiles.append(Projectile(px, py, self.vx * 0.30 + math.cos(aim) * speed, self.vy * 0.30 + math.sin(aim) * speed, "player", ttl=1.45, damage=dmg, radius=radius, color=color, side=side))

    def _update_projectiles(self, dt: float) -> None:
        survivors: list[Projectile] = []
        for p in self.projectiles:
            p.x += p.vx
            p.y += p.vy
            p.ttl -= dt
            if p.ttl <= 0:
                continue
            hit = False
            if p.owner == "player":
                for r in list(self.rivals):
                    if (r.x - p.x) ** 2 + (r.y - p.y) ** 2 < (34 + p.radius) ** 2:
                        part = self._apply_rival_part_damage(r, p.x, p.y, p.damage)
                        self.explosions.append((p.x, p.y, 0.0, 30 + p.radius * 4))
                        if part is not None and part.destroyed:
                            ox = r.x + math.cos(r.heading) * part.lx - math.sin(r.heading) * part.ly
                            oy = r.y + math.sin(r.heading) * part.lx + math.cos(r.heading) * part.ly
                            self.explosions.append((ox, oy, 0.0, 30))
                        hit = True
                        if self._rival_destroyed(r):
                            self.rivals.remove(r)
                            self.kills += 1
                            self.score += 250 + self.wave * 25
                            self.explosions.append((r.x, r.y, 0.0, 78))
                        break
            else:
                if (self.x - p.x) ** 2 + (self.y - p.y) ** 2 < (18 + p.radius) ** 2:
                    self.hp -= p.damage
                    self.explosions.append((p.x, p.y, 0.0, 44))
                    hit = True
                    if self.hp <= 0:
                        self.score = max(0, self.score - 500)
                        self.hp = self.max_hp
                        self.x *= 0.7
                        self.y *= 0.7
                        self.vx = self.vy = 0.0
                        self.explosions.append((self.x, self.y, 0.0, 120))
            if not hit:
                survivors.append(p)
        self.projectiles = survivors[-96:]
        self.explosions = [(x, y, age + dt, size) for x, y, age, size in self.explosions if age < 0.75]
        self.muzzle_flashes = [(x, y, age + dt, side) for x, y, age, side in self.muzzle_flashes if age < 0.18]

    def _update_rivals(self, dt: float) -> None:
        s = self._stat_block()
        for idx, r in enumerate(list(self.rivals)):
            dx = self.x - r.x
            dy = self.y - r.y
            dist = max(1.0, math.hypot(dx, dy))
            desired = math.atan2(dy, dx)
            if dist < 125:
                desired += math.pi * 0.62
            # avoid clumping by steering away from each other
            for j, other in enumerate(self.rivals):
                if j == idx:
                    continue
                ox = r.x - other.x
                oy = r.y - other.y
                od = math.hypot(ox, oy)
                if 0.1 < od < 95:
                    desired = math.atan2(oy, ox)
                    break
            r.heading += clamp(angle_wrap(desired - r.heading), -1.9 * dt, 1.9 * dt)
            target_speed = clamp(s["max_speed"] * (0.55 + self.wave * 0.035), 14, 50)
            if dist > 220:
                r.speed = min(target_speed, r.speed + s["accel"] * 0.45 * dt)
            elif dist < 115:
                r.speed = max(-target_speed * 0.25, r.speed - s["accel"] * 0.42 * dt)
            else:
                r.speed *= 0.992
            r.x += math.cos(r.heading) * r.speed
            r.y += math.sin(r.heading) * r.speed
            r.speed *= 0.972
            r.cooldown = max(0.0, r.cooldown - dt)
            if dist < 540 and r.cooldown <= 0.0 and bool(self.arcade_options.get("rivals_fire", True)):
                r.cooldown = random.uniform(0.48, 1.2)
                lead = math.atan2(dy + self.vy * 10, dx + self.vx * 10)
                side = "left" if random.random() < 0.5 else "right"
                px, py, _ = self._muzzle_world(r.x, r.y, r.heading, side)
                self.projectiles.append(Projectile(px, py, math.cos(lead) * 12 + r.speed * 0.1, math.sin(lead) * 12 + r.speed * 0.1, "rival", ttl=2.0, damage=0.55, radius=2.8, color="#ff4a4a", side=side))

    def _update_pickups(self, dt: float) -> None:
        for p in list(self.pickups):
            p.pulse += dt
            if (self.x - p.x) ** 2 + (self.y - p.y) ** 2 < 32 ** 2:
                if p.kind == "repair":
                    self.hp = min(self.max_hp, self.hp + 1.5)
                    self.score += 50
                elif p.kind == "boost":
                    self.boost_heat = max(0.0, self.boost_heat - 0.45)
                    self.score += 75
                else:
                    self.score += 150
                self.explosions.append((p.x, p.y, 0.0, 52))
                self.pickups.remove(p)
        if len(self.pickups) < 12:
            rng = random.Random(int(time.time()) + self.seed + len(self.pickups))
            for _ in range(4):
                ang = rng.uniform(-math.pi, math.pi)
                dist = rng.uniform(650, 1800)
                self.pickups.append(Pickup(self.x + math.cos(ang) * dist, self.y + math.sin(ang) * dist, rng.choice(["repair", "score", "boost"])))

    def _update_peers(self) -> None:
        if not self.lan:
            return
        self.lan.send_state({"x": self.x, "y": self.y, "heading": self.heading, "hp": self.hp, "vehicle": self.vehicle_name})
        for payload in self.lan.drain():
            try:
                pid = str(payload.get("id"))
                self.peers[pid] = PeerState(pid, float(payload.get("x", 0)), float(payload.get("y", 0)), float(payload.get("heading", 0)), float(payload.get("hp", 0)), str(payload.get("vehicle", "peer")))
            except Exception:
                pass
        stale = time.monotonic() - 4.0
        self.peers = {pid: ps for pid, ps in self.peers.items() if ps.updated >= stale}

    def _world_to_screen(self, x: float, y: float) -> tuple[float, float]:
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        return (w * 0.5 + (x - self.x), h * 0.5 + (y - self.y))

    def _draw(self) -> None:
        c = self.canvas
        w = max(c.winfo_width(), 1)
        h = max(c.winfo_height(), 1)
        c.delete("all")
        self._draw_world(c, w, h)
        for p in self.pickups:
            sx, sy = self._world_to_screen(p.x, p.y)
            if -40 < sx < w + 40 and -40 < sy < h + 40:
                col = {"repair": "#58e084", "boost": "#42b7ff", "score": "#ffe16a"}.get(p.kind, "#ffffff")
                r = 7 + math.sin(p.pulse * 6) * 2
                c.create_oval(sx - r, sy - r, sx + r, sy + r, outline=col, width=2)
                c.create_line(sx - r - 3, sy, sx + r + 3, sy, fill=col)
                c.create_line(sx, sy - r - 3, sx, sy + r + 3, fill=col)
        for p in self.projectiles:
            sx, sy = self._world_to_screen(p.x, p.y)
            if -60 < sx < w + 60 and -60 < sy < h + 60:
                c.create_oval(sx - p.radius, sy - p.radius, sx + p.radius, sy + p.radius, fill=p.color, outline="")
        for x, y, age, size in self.splatter_marks:
            sx, sy = self._world_to_screen(x, y); t = clamp(age / 5.5, 0, 1); r = size * (1.0 - t) * 0.20
            if r > 1 and -60 < sx < w + 60 and -60 < sy < h + 60:
                c.create_oval(sx-r, sy-r, sx+r, sy+r, outline="#8b1111", width=2)
        for ped in self.pedestrians:
            if not ped.alive:
                continue
            sx, sy = self._world_to_screen(ped.x, ped.y)
            if -30 < sx < w + 30 and -30 < sy < h + 30:
                c.create_oval(sx-4, sy-4, sx+4, sy+4, fill="#caa079", outline="#2c1812")
                c.create_line(sx, sy+4, sx, sy+10, fill="#caa079", width=2)
        for r in self.rivals:
            if r.name == self.locked_rival_name:
                sx, sy = self._world_to_screen(r.x, r.y); c.create_oval(sx-48, sy-48, sx+48, sy+48, outline="#67d7ff", width=2)
            self._draw_car(c, r.x, r.y, r.heading, r.color, max(0.0, r.hp / max(3.0, 2.5 + self.wave * 0.45)), label=r.name)
        for peer in self.peers.values():
            self._draw_car(c, peer.x, peer.y, peer.heading, "#5bc7ff", clamp(peer.hp / self.max_hp, 0, 1), label=peer.vehicle)
        self._draw_car(c, self.x, self.y, self.heading, "#e22d24", clamp(self.hp / self.max_hp, 0, 1), label="YOU", player=True)
        for x, y, age, size in self.explosions:
            sx, sy = self._world_to_screen(x, y)
            t = clamp(age / 0.75, 0, 1)
            rad = size * t
            c.create_oval(sx - rad, sy - rad, sx + rad, sy + rad, outline="#ff9a34", width=max(1, int(4 * (1 - t))))
        for x, y, age, side in self.muzzle_flashes:
            sx, sy = self._world_to_screen(x, y)
            rad = 10 * (1.0 - clamp(age / 0.18, 0, 1))
            col = "#ffdf6e" if side == "left" else "#67d7ff"
            c.create_oval(sx-rad, sy-rad, sx+rad, sy+rad, outline=col, width=2)
        self._draw_hud(c, w, h)

    def _draw_world(self, c: tk.Canvas, w: int, h: int) -> None:
        # Terrain tiles around camera, deterministic by world coordinate.
        quality = str(self.arcade_options.get("terrain_quality", "Balanced"))
        step = 120 if quality == "Fast" else 90 if quality == "Balanced" else 68
        base_x = math.floor((self.x - w // 2) / step) * step
        base_y = math.floor((self.y - h // 2) / step) * step
        for gx in range(int(base_x), int(self.x + w // 2 + step), step):
            for gy in range(int(base_y), int(self.y + h // 2 + step), step):
                sx, sy = self._world_to_screen(gx, gy)
                rough = self._terrain_roughness(gx, gy)
                if rough > 0.55:
                    fill = "#1b1511"
                elif rough > 0.38:
                    fill = "#181a16"
                else:
                    fill = "#101721"
                c.create_rectangle(sx, sy, sx + step + 1, sy + step + 1, fill=fill, outline="#111922")
                if quality != "Fast" and rough > 0.42:
                    c.create_line(sx + 12, sy + step * 0.65, sx + step * 0.85, sy + 18, fill="#263033")
        # radar/cross roads are ambience only, not one-way tracks.
        for line in range(-4000, 4001, 800):
            sx1, sy1 = self._world_to_screen(line, -4000)
            sx2, sy2 = self._world_to_screen(line, 4000)
            if -80 < sx1 < w + 80:
                c.create_line(sx1, sy1, sx2, sy2, fill="#1f2a35", width=2)
            sx1, sy1 = self._world_to_screen(-4000, line)
            sx2, sy2 = self._world_to_screen(4000, line)
            if -80 < sy1 < h + 80:
                c.create_line(sx1, sy1, sx2, sy2, fill="#1f2a35", width=2)

    def _draw_car(self, c: tk.Canvas, x: float, y: float, heading: float, color: str, health_ratio: float, label: str = "", player: bool = False) -> None:
        sx, sy = self._world_to_screen(x, y)
        w = c.winfo_width()
        h = c.winfo_height()
        if not (-80 < sx < w + 80 and -80 < sy < h + 80):
            return
        length = 42 if player else 36
        width = 22 if player else 19
        pts = []
        for lx, ly in [(length/2, 0), (length*0.12, width/2), (-length/2, width*0.45), (-length*0.42, 0), (-length/2, -width*0.45), (length*0.12, -width/2)]:
            px = sx + math.cos(heading) * lx - math.sin(heading) * ly
            py = sy + math.sin(heading) * lx + math.cos(heading) * ly
            pts.extend([px, py])
        c.create_polygon(*pts, fill=color, outline="#f4f4f4" if player else "#2a2d31", width=2 if player else 1)
        nose_x = sx + math.cos(heading) * (length/2 + 14)
        nose_y = sy + math.sin(heading) * (length/2 + 14)
        c.create_line(sx, sy, nose_x, nose_y, fill="#ffef9f" if player else "#ff9a9a", width=2)
        if label:
            c.create_text(sx, sy - 30, text=label, fill="#cbd5e1", font=("Segoe UI", 8))
        bar_w = 36
        c.create_rectangle(sx - bar_w/2, sy + 28, sx + bar_w/2, sy + 32, outline="#000000", fill="#2b1111")
        c.create_rectangle(sx - bar_w/2, sy + 28, sx - bar_w/2 + bar_w * clamp(health_ratio, 0, 1), sy + 32, outline="", fill="#49df6d")

    def _draw_hud(self, c: tk.Canvas, w: int, h: int) -> None:
        s = self._stat_block()
        speed = math.hypot(self.vx, self.vy)
        lan_status = self.lan.status if self.lan else "LAN ghosts off"
        lines = [
            f"{APP_NAME}  •  {self.vehicle_name}",
            f"Score {self.score}   Wave {self.wave}   Kills {self.kills}   Rivals {len(self.rivals)}   Peers {len(self.peers)}",
            f"Speed {speed:04.1f}/{s['max_speed']:04.1f}   HP {self.hp:.1f}/{self.max_hp:.1f}   Boost heat {self.boost_heat:.0%}",
            f"Tune accel {s['accel']:.1f}  grip {s['grip']:.2f}  turn {s['turn_rate']:.2f}  terrain {self.arcade_options.get('terrain_quality', 'Balanced')}",
            f"WASD/Arrows drive • Shift boost • Space lock target • LMB/F left turret • RMB/Q right turret • P pause • Esc closes • {lan_status}",
        ]
        x, y = 14, 14
        c.create_rectangle(8, 8, 760, 134, fill="#070203", outline="#6e1118")
        for line in lines:
            c.create_text(x, y, text=line, anchor="nw", fill="#f4e9ea", font=("Consolas", 10))
            y += 23
        c.create_text(w - 14, h - 18, text="by GLITCHED MATRIX Prototype Lab", anchor="se", fill="#633038", font=("Segoe UI", 8))
        if self.paused:
            c.create_rectangle(w/2 - 170, h/2 - 60, w/2 + 170, h/2 + 60, fill="#090305", outline="#ff3434", width=2)
            c.create_text(w/2, h/2 - 10, text="PAUSED", fill="#ff4242", font=("Segoe UI", 24, "bold"))
            c.create_text(w/2, h/2 + 26, text="Esc/P resume • F fullscreen", fill="#f4e9ea", font=("Segoe UI", 11))



class PandaArcadeApp:
    """Panda3D renderer for Code Red Arcade.

    This keeps the arcade as an external child process, but upgrades the actual
    play window to a low-poly 3D combat sandbox. The simulation intentionally
    mirrors the Tk fallback: it watches the same runtime settings file, applies
    tuner changes while running, and exits cleanly when the window is closed.
    """

    def __init__(self, settings_path: Path, lan: bool = False, port: int = DEFAULT_PORT):
        from panda3d.core import loadPrcFileData

        self.settings_path = settings_path
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        self.frame_index = 0
        self.settings_mtime = 0.0
        self.settings: dict = {}
        self.vehicle_values: dict[str, float] = {}
        self.vehicle_name = "Car01"
        self.vehicle_asset_status = "vehicle asset pending"
        self._vehicle_source_np = None
        self._vehicle_glb_cache = None
        self._vehicle_accessor_cache = {}
        self.player_wheel_phase = 0.0
        self.rival_wheel_phases = [0.0 for _ in range(8)]
        self.scene_dt = 1.0 / 60.0
        self.arcade_options: dict = {}
        self.seed = random.randint(10000, 999999)
        self.keys: set[str] = set()
        self.mouse_buttons: set[str] = set()
        self.mouse_look_yaw = 0.0
        self.mouse_look_pitch = 0.0
        self.camera_zoom = 1.72
        self.camera_base_fov = 88.0
        self.camera_lock_enabled = False
        self._last_dynamic_fov = None
        self.mouse_capture_enabled = True
        self.mouse_capture_active = False
        self._mouse_ignore_next_delta = True
        self._mouse_capture_error = ""
        self._last_mouse_delta = (0.0, 0.0)
        self.mouse_sensitivity = 0.0049
        self.mouse_pitch_sensitivity = 0.0039
        self.help_visible = False
        self.metal_hud_visible = True
        self.world_clock = random.random() * 100.0
        self.display_fov = 88.0
        self.paused = False
        self.x = 0.0
        self.y = 0.0
        self.z = 6.0
        self.hover_height = 6.1
        self.vx = 0.0
        self.vy = 0.0
        self.vz = 0.0
        self.heading = 0.0
        self.airborne = False
        self.last_ground_z = 0.0
        self.collision_cooldown = 0.0
        self.prop_colliders: list[PropCollider] = []
        self.hp = 14.0
        self.max_hp = 14.0
        self.player_parts: list[TargetPart] = make_player_parts()
        self.was_boosting = False
        self.ramp_specs: list[dict[str, float]] = []
        self.score = 0
        self.wave = 1
        self.kills = 0
        self.fire_cooldown = 0.0
        self.missile_cooldown = 0.0
        self.left_flash_timer = 0.0
        self.right_flash_timer = 0.0
        self.boost_heat = 0.0
        self.projectiles: list[Projectile] = []
        self.rivals: list[Rival] = []
        self.pickups: list[Pickup] = []
        self.pedestrians: list[Pedestrian] = []
        self.locked_rival_name: str | None = None
        self.splatter_marks: list[tuple[float, float, float, float]] = []
        self.explosions: list[tuple[float, float, float, float]] = []
        self.muzzle_flashes: list[tuple[float, float, float, str]] = []
        self.peers: dict[str, PeerState] = {}
        self.player_id = f"arcade-{os.getpid()}-{random.randint(1000,9999)}"
        self.lan = LanGhostBridge(self.player_id, port) if lan else None
        if self.lan:
            self.lan.start()

        # The user-facing default is a normal window.
        loadPrcFileData("", f"window-title {APP_NAME}")
        loadPrcFileData("", "win-size 1920 1080")
        loadPrcFileData("", "framebuffer-alpha true")
        loadPrcFileData("", "sync-video false")
        loadPrcFileData("", "show-frame-rate-meter false")
        loadPrcFileData("", "textures-power-2 none")
        # Sound is handled by the replaceable pygame SFX bank, so Panda's own
        # audio backend stays disabled to avoid device errors on headless systems.
        loadPrcFileData("", "audio-library-name null")
        loadPrcFileData("", "gl-coordinate-system default")
        from direct.showbase.ShowBase import ShowBase
        from direct.task import Task
        from panda3d.core import AmbientLight, DirectionalLight, Fog, WindowProperties
        from direct.gui.OnscreenText import OnscreenText

        self.Task = Task
        self.OnscreenText = OnscreenText
        self.base = ShowBase()
        self.base.disableMouse()
        try:
            self.base.camLens.setFov(90)
            self.base.camLens.setNearFar(2, 6200)
        except Exception:
            pass
        self.base.setBackgroundColor(0.015, 0.018, 0.024, 1)
        props = WindowProperties()
        props.setTitle(APP_NAME)
        if hasattr(self.base.win, "requestProperties"):
            self.base.win.requestProperties(props)
        self.render = self.base.render
        self.loader = self.base.loader

        ambient = AmbientLight("ambient")
        ambient.setColor((0.30, 0.30, 0.33, 1))
        self.ambient_light = ambient
        ambient_np = self.render.attachNewNode(ambient)
        self.ambient_np = ambient_np
        self.render.setLight(ambient_np)
        sun = DirectionalLight("hard-red-sun")
        sun.setColor((0.86, 0.31, 0.22, 1))
        self.sun_light = sun
        sun_np = self.render.attachNewNode(sun)
        self.sun_np = sun_np
        sun_np.setHpr(-38, -57, 0)
        self.render.setLight(sun_np)
        fog = Fog("red-haze")
        fog.setColor(0.035, 0.010, 0.014)
        fog.setLinearRange(680, 3300)
        self.fog = fog
        self.render.setFog(fog)

        self._load_settings(force=True)
        self._apply_display_settings(initial=True)
        self.sound = SoundBank(app_dir() / "assets" / "sfx" / "arcade", enabled=True)
        self.sound.set_mix(float(self.arcade_options.get("master_volume", 0.82)), float(self.arcade_options.get("sfx_volume", 0.86)))
        self._build_scene()
        self._bind_controls()
        self._spawn_wave(reset=True)
        self._spawn_pickups()
        self._spawn_pedestrians()
        self.last_tick = time.monotonic()
        self.base.taskMgr.add(self._task_update, "CodeRedArcadeUpdate")
        self.base.accept("window-event", self._on_window_event)
        self._apply_mouse_capture(True)

    def run(self) -> None:
        self.base.run()

    def _close(self) -> None:
        self._apply_mouse_capture(False)
        if self.lan:
            self.lan.stop()
        try:
            self.base.userExit()
        except Exception:
            pass

    def _on_window_event(self, window) -> None:
        # Release controls if focus is gone, preventing background driving/firing.
        try:
            foreground = bool(window and window.getProperties().getForeground())
            if not foreground:
                self.keys.clear()
                self.mouse_buttons.clear()
                self._apply_mouse_capture(False)
            elif not self.paused:
                self._apply_mouse_capture(True)
        except Exception:
            pass

    def _apply_mouse_capture(self, enabled: bool) -> None:
        enabled = bool(enabled and self.mouse_capture_enabled)
        try:
            from panda3d.core import WindowProperties
            props = WindowProperties()
            props.setCursorHidden(enabled)
            # Prefer Panda3D's true relative mode when available. Some builds only
            # expose confined/absolute modes, so the centered-pointer fallback below
            # still prevents the desktop-edge escape either way.
            try:
                if hasattr(props, "setMouseMode"):
                    if enabled and hasattr(WindowProperties, "M_relative"):
                        props.setMouseMode(WindowProperties.M_relative)
                    elif enabled and hasattr(WindowProperties, "M_confined"):
                        props.setMouseMode(WindowProperties.M_confined)
                    elif (not enabled) and hasattr(WindowProperties, "M_absolute"):
                        props.setMouseMode(WindowProperties.M_absolute)
            except Exception:
                pass
            if hasattr(self.base.win, "requestProperties"):
                self.base.win.requestProperties(props)
            self.mouse_capture_active = enabled
            self._mouse_ignore_next_delta = True
            self._center_pointer()
            self._mouse_capture_error = ""
        except Exception as exc:
            self.mouse_capture_active = False
            self._mouse_capture_error = str(exc)[:80]

    def _center_pointer(self) -> None:
        try:
            if not self.base.win:
                return
            props = self.base.win.getProperties()
            cx = max(1, int(props.getXSize() * 0.5))
            cy = max(1, int(props.getYSize() * 0.5))
            if hasattr(self.base.win, "movePointer"):
                self.base.win.movePointer(0, cx, cy)
        except Exception:
            pass

    def _read_mouse_delta(self) -> tuple[float, float]:
        if self.paused:
            return 0.0, 0.0
        try:
            win = self.base.win
            if not win:
                return 0.0, 0.0
            props = win.getProperties()
            if hasattr(props, "getForeground") and not props.getForeground():
                return 0.0, 0.0
            w = max(2, int(props.getXSize()))
            h = max(2, int(props.getYSize()))
            cx = w // 2
            cy = h // 2
            pointer = win.getPointer(0)
            px = int(pointer.getX())
            py = int(pointer.getY())
            dx = float(px - cx)
            dy = float(py - cy)
            if self._mouse_ignore_next_delta:
                dx = dy = 0.0
                self._mouse_ignore_next_delta = False
            # Filter the giant one-frame jumps that can occur after alt-tab, window
            # resize, or when a platform reports a stale desktop-space coordinate.
            if abs(dx) > w * 0.35 or abs(dy) > h * 0.35:
                dx = dy = 0.0
            if hasattr(win, "movePointer"):
                win.movePointer(0, cx, cy)
            self._last_mouse_delta = (dx, dy)
            return dx, dy
        except Exception as exc:
            self._mouse_capture_error = str(exc)[:80]
            return 0.0, 0.0

    def _bind_controls(self) -> None:
        # Panda reports shifted keyboard/mouse combos as distinct events on some
        # systems. Binding those combo names back to their canonical controls
        # keeps Shift as a speed boost instead of blocking steering/fire.
        controls = [
            "w", "a", "s", "d", "arrow_up", "arrow_down", "arrow_left", "arrow_right",
            "shift", "space", "control", "f", "q", "e", "f12", "mouse1", "mouse3",
        ]
        aliases: dict[str, str] = {key: key for key in controls}
        for key in ["w", "a", "s", "d", "arrow_up", "arrow_down", "arrow_left", "arrow_right", "control", "f", "q", "e", "mouse1", "mouse3", "space", "f12"]:
            aliases[f"shift-{key}"] = key
        # A few keyboard layouts/systems surface capital letters while Shift is down.
        for key in ("w", "a", "s", "d", "f", "q", "e"):
            aliases[key.upper()] = key
            aliases[f"shift-{key.upper()}"] = key
        for event, canonical in aliases.items():
            self.base.accept(event, self._key_down, [canonical])
            self.base.accept(event + "-up", self._key_up, [canonical])
        self.base.accept("escape", self._toggle_pause)
        self.base.accept("shift-escape", self._close)
        self.base.accept("p", self._toggle_pause)
        self.base.accept("h", self._toggle_help)
        self.base.accept("f1", self._toggle_help)
        self.base.accept("f", self._toggle_fullscreen)
        self.base.accept("f11", self._toggle_fullscreen)
        self.base.accept("wheel_up", self._mouse_wheel_zoom, [-1])
        self.base.accept("wheel_down", self._mouse_wheel_zoom, [1])

    def _toggle_pause(self) -> None:
        self.paused = not self.paused
        self._apply_mouse_capture(not self.paused)
        self._set_pause_menu_visible(self.paused)

    def _toggle_help(self) -> None:
        self.help_visible = not self.help_visible

    def _toggle_camera_lock(self) -> None:
        self.camera_lock_enabled = not bool(getattr(self, "camera_lock_enabled", False))
        if self.camera_lock_enabled:
            self.mouse_look_yaw *= 0.35
            self.mouse_look_pitch *= 0.35

    def _mouse_wheel_zoom(self, direction: int) -> None:
        # Wheel up zooms in, wheel down zooms out. FOV is locked to zoom below.
        self.camera_zoom = clamp(float(getattr(self, "camera_zoom", 1.72)) + float(direction) * 0.10, 0.62, 1.72)
        self.arcade_options["camera_zoom"] = self.camera_zoom
        self._update_camera_lens(force=True)

    def _set_fov_delta(self, delta: float) -> None:
        self.camera_base_fov = clamp(float(getattr(self, "camera_base_fov", 88.0)) + float(delta), 68.0, 106.0)
        self.arcade_options["camera_fov"] = self.camera_base_fov
        self._update_camera_lens(force=True)

    def _toggle_fullscreen(self) -> None:
        self.arcade_options["full_windowed"] = not bool(self.arcade_options.get("full_windowed", False))
        self._apply_display_settings(initial=False)

    def _dynamic_fov(self) -> float:
        # Zoom and FOV move together: farther camera = wider FOV, closer camera = tighter FOV.
        base = clamp(float(getattr(self, "camera_base_fov", self.arcade_options.get("camera_fov", 88.0))), 68.0, 106.0)
        zoom = clamp(float(getattr(self, "camera_zoom", 1.72)), 0.62, 1.72)
        return clamp(base + (zoom - 1.0) * 24.0, 58.0, 116.0)

    def _update_camera_lens(self, force: bool = False) -> None:
        try:
            fov = self._dynamic_fov()
            if force or self._last_dynamic_fov is None or abs(float(self._last_dynamic_fov) - fov) > 0.15:
                self.base.camLens.setFov(fov)
                self.base.camLens.setNearFar(1.5, 6800)
                self._last_dynamic_fov = fov
            self.display_fov = fov
        except Exception:
            pass

    def _apply_display_settings(self, initial: bool = False) -> None:
        try:
            from panda3d.core import WindowProperties
            self.camera_base_fov = clamp(float(self.arcade_options.get("camera_fov", getattr(self, "camera_base_fov", 88.0))), 68.0, 106.0)
            self.camera_zoom = clamp(float(self.arcade_options.get("camera_zoom", getattr(self, "camera_zoom", 1.72))), 0.62, 1.72)
            self._update_camera_lens(force=True)
            props = WindowProperties()
            props.setTitle(APP_NAME + " — Arcade")
            props.setSize(1920, 1080)
            try:
                props.setFullscreen(bool(self.arcade_options.get("full_windowed", False)))
            except Exception:
                pass
            if hasattr(props, "setUndecorated") and bool(self.arcade_options.get("full_windowed", False)):
                try:
                    props.setUndecorated(True)
                except Exception:
                    pass
            if hasattr(props, "setFixedSize"):
                try:
                    props.setFixedSize(False)
                except Exception:
                    pass
            self.base.win.requestProperties(props)
        except Exception:
            pass

    def _key_down(self, key: str) -> None:
        if key == "space" and key not in self.keys:
            self._cycle_lock_target()
            self.keys.add(key)
            return
        if key == "f" and key not in self.keys:
            self._toggle_fullscreen()
            self.keys.add(key)
            return
        self.keys.add(key)
        if key.startswith("mouse"):
            self.mouse_buttons.add(key)

    def _key_up(self, key: str) -> None:
        self.keys.discard(key)
        self.mouse_buttons.discard(key)

    def _load_settings(self, force: bool = False) -> None:
        try:
            mtime = self.settings_path.stat().st_mtime
        except FileNotFoundError:
            if not self.settings:
                self.settings = self._fallback_settings()
                self.vehicle_values = self.settings["vehicles"]["Car01"]
            return
        if not force and mtime <= self.settings_mtime:
            return
        self.settings_mtime = mtime
        try:
            data = json.loads(self.settings_path.read_text(encoding="utf-8"))
        except Exception:
            return
        self.settings = data if isinstance(data, dict) else self._fallback_settings()
        self.vehicle_name = str(self.settings.get("active_vehicle", "Car01"))
        vehicles = self.settings.get("vehicles", {}) if isinstance(self.settings.get("vehicles"), dict) else {}
        values = vehicles.get(self.vehicle_name) if isinstance(vehicles.get(self.vehicle_name), dict) else None
        if not values:
            values = self._fallback_settings()["vehicles"]["Car01"]
        self.vehicle_values = {str(k): float(v) for k, v in values.items() if isinstance(v, (int, float))}
        self.arcade_options = self.settings.get("arcade", {}) if isinstance(self.settings.get("arcade"), dict) else {}
        if hasattr(self, "base"):
            self._apply_display_settings(initial=False)
        if hasattr(self, "sound"):
            self.sound.set_mix(float(self.arcade_options.get("master_volume", 0.82)), float(self.arcade_options.get("sfx_volume", 0.86)))
        old_seed = self.seed
        self.seed = int(self.arcade_options.get("world_seed", self.seed or 1) or 1)
        if old_seed != self.seed and hasattr(self, "rivals"):
            self._spawn_wave(reset=True)
            self._spawn_pickups()
            self._spawn_pedestrians()

    def _fallback_settings(self) -> dict:
        return {
            "active_vehicle": "Car01",
            "vehicles": {"Car01": {
                "mass": 2350, "horsepower": 210, "boost_torque": 70, "boost_duration": 1.2,
                "high_mph": 52, "front_static": 2.1, "rear_static": 2.1,
                "front_slide": 1.95, "rear_slide": 1.95, "front_steer": 0.62,
                "aero_drag": 1.05, "offroad_drag": 0.0, "downforce": 0.35,
                "handbrake": 0.28, "com_z": -0.72,
            }},
            "arcade": {"rival_count": 4, "world_seed": self.seed, "terrain_quality": "Balanced", "weapons_enabled": True, "rivals_fire": True, "master_volume": 0.82, "sfx_volume": 0.86, "camera_fov": 88.0, "camera_zoom": 1.72, "full_windowed": False},
        }

    def _stat_block(self) -> dict[str, float]:
        v = self.vehicle_values
        mass = max(safe_float(v, "mass", 2350.0), 500.0)
        hp = safe_float(v, "horsepower", 210.0)
        high_mph = safe_float(v, "high_mph", 52.0)
        grip = (safe_float(v, "front_static", 2.0) + safe_float(v, "rear_static", 2.0) + safe_float(v, "front_slide", 1.8) + safe_float(v, "rear_slide", 1.8)) / 4.0
        steer = safe_float(v, "front_steer", 0.6)
        drag = safe_float(v, "aero_drag", 1.0) + safe_float(v, "offroad_drag", 0.0) * 0.4
        down = safe_float(v, "downforce", 0.35)
        boost = safe_float(v, "boost_torque", 70.0) * max(0.2, safe_float(v, "boost_duration", 1.0))
        com_z = safe_float(v, "com_z", -0.7)
        accel = clamp((hp + boost * 0.08) / mass * 92.0, 3.0, 34.0)
        max_speed = clamp(high_mph * 0.82 + hp / mass * 92.0, 18.0, 92.0)
        turn_rate = clamp(steer * (1.72 + grip * 0.24), 0.45, 3.75)
        friction = clamp(0.965 + grip * 0.006 + down * 0.002 - drag * 0.005, 0.90, 0.992)
        stability = clamp(0.72 + (-com_z) * 0.16 + grip * 0.035, 0.35, 1.15)
        return {"accel": accel, "max_speed": max_speed, "turn_rate": turn_rate, "friction": friction, "stability": stability, "grip": grip, "drag": drag}

    def _terrain_roughness(self, x: float, y: float) -> float:
        return clamp((math.sin(x * 0.006 + self.seed) + math.cos(y * 0.005 - self.seed * 0.3) + math.sin((x + y) * 0.002)) / 6.0 + 0.28, 0.0, 0.75)

    def _terrain_height(self, x: float, y: float) -> float:
        # Cheap procedural hills plus authored ramp influence. The vehicles ride
        # this same function, so ramps are visual and physical instead of fake props.
        quality = str(self.arcade_options.get("terrain_quality", "Balanced"))
        # v2.4.2 regression repair: hills are intentionally visible again.
        # Earlier hotfix builds had a rolling height function, but the amplitude
        # was too low at the max zoom-out camera, so the world read as flat.
        amp = 24.0 if quality.lower().startswith("fast") else (44.0 if quality.lower().startswith("balanced") else 66.0)
        h = (
            math.sin(x * 0.0034 + self.seed * 0.013) * amp * 0.62 +
            math.cos(y * 0.0030 - self.seed * 0.017) * amp * 0.48 +
            math.sin((x + y) * 0.0018 + 1.7) * amp * 0.34 +
            math.cos((x - y) * 0.00235 + self.seed * 0.009) * amp * 0.22
        )
        for spec in getattr(self, "ramp_specs", []):
            try:
                dx = x - spec["x"]; dy = y - spec["y"]; a = -spec["h"]
                lx = math.cos(a) * dx - math.sin(a) * dy
                ly = math.sin(a) * dx + math.cos(a) * dy
                half_l = spec["length"] * 0.5; half_w = spec["width"] * 0.5
                if -half_l <= lx <= half_l and abs(ly) <= half_w:
                    edge = clamp(1.0 - abs(ly) / max(1.0, half_w), 0.0, 1.0)
                    surf = spec["z"] + ((lx + half_l) / max(1.0, spec["length"])) * spec["height"] * (0.65 + edge * 0.35)
                    h = max(h, surf)
            except Exception:
                continue
        return h

    def _terrain_slope(self, x: float, y: float, spread: float = 54.0) -> tuple[float, float]:
        hx1 = self._terrain_height(x + spread, y); hx0 = self._terrain_height(x - spread, y)
        hy1 = self._terrain_height(x, y + spread); hy0 = self._terrain_height(x, y - spread)
        return (hx1 - hx0) / (spread * 2.0), (hy1 - hy0) / (spread * 2.0)

    def _spawn_wave(self, reset: bool = False) -> None:
        rng = random.Random(self.seed + self.wave * 177)
        base_count = int(clamp(float(self.arcade_options.get("rival_count", 4)), 0, 10))
        count = int(clamp(base_count + max(0, self.wave - 1), 0, 18))
        if reset:
            self.rivals.clear()
        # First wave opens in front of the chase camera so the external arcade
        # immediately reads as a combat sandbox instead of an empty test plane.
        if reset and self.wave == 1 and count > 0:
            anchors = [(260, -120), (330, 105), (470, -35), (555, 160), (610, -190), (730, 25), (820, 190), (900, -140)]
            for ax, ay in anchors[:count]:
                self.rivals.append(Rival(self.x + ax, self.y + ay, math.atan2(-ay, -ax), hp=2.5 + self.wave * 0.45, color=rng.choice(["#e4573f", "#d13fd1", "#ff8e2b", "#c83434"]), name=f"Rival {len(self.rivals) + 1}"))
        while len(self.rivals) < count:
            dist = rng.uniform(220, 560)
            ang = rng.uniform(-math.pi, math.pi)
            self.rivals.append(Rival(
                self.x + math.cos(ang) * dist,
                self.y + math.sin(ang) * dist,
                rng.uniform(-math.pi, math.pi),
                hp=2.5 + self.wave * 0.45,
                color=rng.choice(["#e4573f", "#d13fd1", "#ff8e2b", "#c83434"]),
                name=f"Rival {len(self.rivals) + 1}",
            ))

    def _spawn_pickups(self) -> None:
        rng = random.Random(self.seed + 411)
        self.pickups = []
        for _ in range(34):
            self.pickups.append(Pickup(rng.uniform(-2600, 2600), rng.uniform(-2600, 2600), rng.choice(["repair", "score", "boost"])))

    def _spawn_pedestrians(self) -> None:
        rng = random.Random(self.seed + 9121)
        self.pedestrians = []
        for i in range(26):
            ang = rng.uniform(-math.pi, math.pi)
            dist = rng.uniform(320, 2450)
            self.pedestrians.append(Pedestrian(self.x + math.cos(ang) * dist, self.y + math.sin(ang) * dist, rng.uniform(-0.38, 0.38), rng.uniform(-0.38, 0.38), name=f"ped_{i+1}"))

    def _locked_rival(self) -> Rival | None:
        live = [r for r in self.rivals if not self._rival_destroyed(r)]
        if not live:
            self.locked_rival_name = None
            return None
        if self.locked_rival_name:
            for r in live:
                if r.name == self.locked_rival_name:
                    return r
        nearest = min(live, key=lambda r: (r.x - self.x) ** 2 + (r.y - self.y) ** 2)
        self.locked_rival_name = nearest.name
        return nearest

    def _cycle_lock_target(self) -> None:
        live = sorted([r for r in self.rivals if not self._rival_destroyed(r)], key=lambda r: math.atan2(r.y - self.y, r.x - self.x))
        if not live:
            self.locked_rival_name = None
            return
        names = [r.name for r in live]
        if self.locked_rival_name in names:
            self.locked_rival_name = names[(names.index(self.locked_rival_name) + 1) % len(names)]
        else:
            nearest = min(live, key=lambda r: (r.x - self.x) ** 2 + (r.y - self.y) ** 2)
            self.locked_rival_name = nearest.name

    def _burst_fx(self, x: float, y: float, size: float = 42.0, count: int = 6) -> None:
        for i in range(max(1, count)):
            a = math.tau * (i / max(1, count)) + random.uniform(-0.25, 0.25)
            d = random.uniform(5.0, size * 0.48)
            self.explosions.append((x + math.cos(a) * d, y + math.sin(a) * d, 0.0, size * random.uniform(0.35, 0.85)))

    def _make_stylized_mesh_np(self, parent, name: str, verts, faces, color: tuple[float, float, float, float],
                                wire_color: tuple[float, float, float, float] | None = None, thickness: float = 1.0):
        """Build a single-material mesh with an outer wire skin.

        This is the shared visual language for Code Red Arcade: one cheap flat
        surface/material per object, then a thin exact-shape wire casing on top.
        It avoids the old placeholder-box look while staying much lighter than
        texture-heavy props.
        """
        from panda3d.core import (
            Geom, GeomNode, GeomTriangles, GeomVertexData, GeomVertexFormat,
            GeomVertexWriter, LineSegs,
        )
        wire_color = wire_color or (min(color[0] + 0.20, 1.0), min(color[1] + 0.20, 1.0), min(color[2] + 0.20, 1.0), 1.0)
        root = parent.attachNewNode(name + "_meshroot")
        try:
            if color[3] < 1.0 or wire_color[3] < 1.0:
                root.setTransparency(True)
        except Exception:
            pass
        fmt = GeomVertexFormat.getV3c4()
        data = GeomVertexData(name + "_surface", fmt, Geom.UHStatic)
        vw = GeomVertexWriter(data, "vertex")
        cw = GeomVertexWriter(data, "color")
        for vx, vy, vz in verts:
            vw.addData3f(float(vx), float(vy), float(vz))
            cw.addData4f(*color)
        tris = GeomTriangles(Geom.UHStatic)
        edges: set[tuple[int, int]] = set()
        for face in faces:
            if len(face) < 3:
                continue
            base = int(face[0])
            for i in range(1, len(face) - 1):
                a, b, c = base, int(face[i]), int(face[i + 1])
                tris.addVertices(a, b, c)
            for i, a in enumerate(face):
                b = face[(i + 1) % len(face)]
                key = (int(a), int(b)) if int(a) < int(b) else (int(b), int(a))
                edges.add(key)
        geom = Geom(data); geom.addPrimitive(tris)
        node = GeomNode(name + "_surface"); node.addGeom(geom)
        surf = root.attachNewNode(node)
        surf.setTwoSided(True)
        surf.setLightOff(10)
        segs = LineSegs(name + "_wire")
        segs.setThickness(thickness)
        segs.setColor(*wire_color)
        for a, b in sorted(edges):
            segs.moveTo(*verts[a]); segs.drawTo(*verts[b])
        wire = root.attachNewNode(segs.create())
        wire.setTwoSided(True)
        wire.setLightOff(10)
        return root

    def _make_box_np(self, parent, name: str, sx: float, sy: float, sz: float, color: tuple[float, float, float, float]):
        # Keep this as a compatibility helper, but it now produces a single flat
        # material plus exact outer-wire casing instead of a bare placeholder box.
        x, y, z = sx / 2.0, sy / 2.0, sz / 2.0
        verts = [(-x,-y,-z), (x,-y,-z), (x,y,-z), (-x,y,-z), (-x,-y,z), (x,-y,z), (x,y,z), (-x,y,z)]
        faces = [(0,1,2,3), (4,7,6,5), (0,4,5,1), (1,5,6,2), (2,6,7,3), (3,7,4,0)]
        return self._make_stylized_mesh_np(parent, name, verts, faces, color, thickness=0.95)

    def _make_tile_np(self, parent, name: str, size: float, color: tuple[float, float, float, float]):
        # v2.4.2: actual raised terrain plates instead of flat hex cards.
        # The whole tile still streams cheaply, but every plate has visible
        # ridge geometry so max-zoom views show hills/valleys again.
        rng = random.Random(sum(ord(ch) for ch in name) + self.seed * 17)
        half = size * 0.56
        steps = 5
        amp = size * 0.070
        verts = []
        for iy in range(steps + 1):
            yy = -half + (size * 1.12) * (iy / steps)
            for ix in range(steps + 1):
                xx = -half + (size * 1.12) * (ix / steps)
                dist = math.hypot(xx, yy) / max(1.0, half)
                edge_fade = clamp(1.0 - max(0.0, dist - 0.72) / 0.34, 0.0, 1.0)
                ridge = (
                    math.sin(xx * 0.035 + rng.random() * 0.5) * 0.52 +
                    math.cos(yy * 0.031 + rng.random() * 0.5) * 0.38 +
                    math.sin((xx + yy) * 0.022) * 0.25
                )
                z = ridge * amp * edge_fade
                verts.append((xx, yy, z))
        faces = []
        for iy in range(steps):
            for ix in range(steps):
                a = iy * (steps + 1) + ix
                faces.append((a, a + 1, a + steps + 2, a + steps + 1))
        root = self._make_stylized_mesh_np(parent, name, verts, faces, color, wire_color=(0.20, 0.08, 0.09, 0.88), thickness=0.55)
        return root

    def _make_octahedron_np(self, parent, name: str, radius: float, height: float, color: tuple[float, float, float, float]):
        r = radius
        h = height * 0.5
        verts = [(0,0,h), (r,0,0), (0,r,0), (-r,0,0), (0,-r,0), (0,0,-h)]
        faces = [(0,1,2), (0,2,3), (0,3,4), (0,4,1), (5,2,1), (5,3,2), (5,4,3), (5,1,4)]
        return self._make_stylized_mesh_np(parent, name, verts, faces, color, thickness=0.9)

    def _make_wreck_np(self, parent, name: str, sx: float, sy: float, sz: float, color: tuple[float, float, float, float], seed: int = 0):
        # Irregular arena debris: exact low-poly mass, not a cube.  The top and
        # bottom share one flat material, then the outer mesh wires show the form.
        rng = random.Random(self.seed * 131 + seed)
        pts = []
        for i in range(7):
            a = math.tau * i / 7.0 + rng.uniform(-0.14, 0.14)
            rr = rng.uniform(0.72, 1.06)
            pts.append((math.cos(a) * sx * 0.5 * rr, math.sin(a) * sy * 0.5 * rr))
        bottom = [(x, y, -sz * 0.5) for x, y in pts]
        top = [(x * rng.uniform(0.72, 1.02), y * rng.uniform(0.72, 1.02), sz * rng.uniform(0.34, 0.58)) for x, y in pts]
        verts = bottom + top
        n = len(pts)
        faces = [tuple(range(n)), tuple(range(n*2-1, n-1, -1))]
        for i in range(n):
            faces.append((i, (i+1)%n, n+(i+1)%n, n+i))
        return self._make_stylized_mesh_np(parent, name, verts, faces, color, wire_color=(0.35, 0.24, 0.20, 0.95), thickness=0.8)

    def _vehicle_baked_path(self) -> Path:
        return app_dir() / "assets" / "vehicles" / "concept_vehicle_baked_wire.json"

    def _make_baked_wire_np(self, parent, name: str, vertices, segments, color: tuple[float, float, float, float], thickness: float):
        from panda3d.core import Geom, GeomNode, GeomLines, GeomVertexData, GeomVertexFormat, GeomVertexWriter
        if not vertices or not segments:
            return None
        fmt = GeomVertexFormat.getV3c4()
        data = GeomVertexData(name + "_wiredata", fmt, Geom.UHStatic)
        vw = GeomVertexWriter(data, "vertex")
        cw = GeomVertexWriter(data, "color")
        for x, y, z in vertices:
            vw.addData3f(float(x), float(y), float(z))
            cw.addData4f(*color)
        lines = GeomLines(Geom.UHStatic)
        for a, b in segments:
            lines.addVertices(int(a), int(b))
        geom = Geom(data); geom.addPrimitive(lines)
        node = GeomNode(name + "_baked_wire"); node.addGeom(geom)
        np = parent.attachNewNode(node)
        np.setTwoSided(True)
        np.setLightOff(10)
        np.setRenderModeThickness(thickness)
        return np

    def _add_vehicle_design_shell(self, root, color: tuple[float, float, float, float], player: bool, data: dict | None = None) -> None:
        # The source GLB has now been baked into a lightweight arcade design. This
        # shell is procedural, measured from the original bounds, and gives the car
        # a deliberate single-material body underneath the thin wiremesh instead of
        # depending on the runtime model file.
        try:
            bounds = (data or {}).get("design", {}).get("body_bounds") or {}
            mn = bounds.get("min", [-41.0, -15.5, 2.0])
            mx = bounds.get("max", [41.0, 15.5, 18.0])
            x0, x1 = float(mn[0]), float(mx[0])
            half_w = max(abs(float(mn[1])), abs(float(mx[1])))
            z0, z1 = float(mn[2]), float(mx[2])
        except Exception:
            x0, x1, half_w, z0, z1 = -41.0, 41.0, 15.5, 2.0, 18.0
        shell_col = (min(color[0] * 0.46 + 0.035, 1.0), min(color[1] * 0.42 + 0.035, 1.0), min(color[2] * 0.42 + 0.040, 1.0), 0.34)
        wire_col = (min(color[0] + 0.25, 1.0), min(color[1] + 0.24, 1.0), min(color[2] + 0.24, 1.0), 0.95)
        sections = [
            (x0, half_w * 0.70, z0 + 1.1, z0 + 7.4),
            (x0 + (x1-x0) * 0.24, half_w * 0.98, z0 + 1.5, z0 + 10.6),
            (x0 + (x1-x0) * 0.50, half_w * 0.86, z0 + 2.0, z1 + 1.1),
            (x0 + (x1-x0) * 0.72, half_w * 0.76, z0 + 2.2, z0 + 12.0),
            (x1, half_w * 0.60, z0 + 3.0, z0 + 7.7),
        ]
        verts = []
        for x, hw, zl, zh in sections:
            verts.extend([(x, -hw, zl), (x, hw, zl), (x, -hw * 0.78, zh), (x, hw * 0.78, zh)])
        faces = []
        for i in range(len(sections)-1):
            a = i*4; b = (i+1)*4
            faces.extend([
                (a, b, b+2, a+2),       # left flank
                (a+1, a+3, b+3, b+1),   # right flank
                (a+2, b+2, b+3, a+3),   # roof/deck surface
                (a, a+1, b+1, b),       # under/belt surface
            ])
        faces.append((0, 2, 3, 1)); last = (len(sections)-1)*4; faces.append((last, last+1, last+3, last+2))
        shell = self._make_stylized_mesh_np(root, "baked_design_shell", verts, faces, shell_col, wire_color=wire_col, thickness=0.28 if player else 0.20)
        try:
            shell.setTransparency(True)
        except Exception:
            pass
        # Add design accent lines: center spine, side sweeps, and wheel arches,
        # all generated from the baked source dimensions rather than the source model.
        from panda3d.core import LineSegs
        segs = LineSegs("baked_vehicle_design_accents")
        segs.setThickness(0.72 if player else 0.48)
        accent = (min(color[0] + 0.42, 1.0), min(color[1] + 0.28, 1.0), min(color[2] + 0.20, 1.0), 1.0)
        segs.setColor(*accent)
        # top spine and hood/deck strokes
        for y in (0.0, -half_w*0.42, half_w*0.42):
            segs.moveTo(x0 + 6.0, y, z0 + 9.0); segs.drawTo(x1 - 6.0, y * 0.70, z0 + 9.8)
        for y in (-half_w*0.92, half_w*0.92):
            segs.moveTo(x0 + 8.0, y, z0 + 6.3); segs.drawTo(x1 - 10.0, y * 0.78, z0 + 7.0)
        centers = ((data or {}).get("design", {}).get("wheel_centers") or {})
        for _role, ctr in centers.items():
            try:
                cx, cy, cz = float(ctr[0]), float(ctr[1]), float(ctr[2])
            except Exception:
                continue
            side_y = -half_w * 1.012 if cy < 0 else half_w * 1.012
            r = 8.5
            last = None
            for i in range(13):
                a = math.pi * (1.0 - i / 12.0)
                pt = (cx + math.cos(a) * r, side_y, cz + 1.2 + math.sin(a) * r)
                if last is not None:
                    segs.moveTo(*last); segs.drawTo(*pt)
                last = pt
        accents = root.attachNewNode(segs.create())
        accents.setLightOff(10)

    def _load_baked_vehicle_into(self, root, color: tuple[float, float, float, float], player: bool = False) -> bool:
        asset_path = self._vehicle_baked_path()
        if not asset_path.exists():
            self.vehicle_asset_status = f"baked vehicle missing: {asset_path.name}"
            return False
        try:
            data = json.loads(asset_path.read_text(encoding="utf-8"))
            roles = data.get("roles", []) if isinstance(data, dict) else []
            self._add_vehicle_design_shell(root, color, player, data)
            spin_nodes = []
            front_steers = []
            wheel_radii = []
            thickness = 0.54 if player else 0.36
            for entry in roles:
                role = str(entry.get("role", "body"))
                translation = entry.get("translation", [0.0, 0.0, 0.0])
                vertices = entry.get("vertices", [])
                segments = entry.get("segments", [])
                if role.startswith("wheel_"):
                    if "front" in role:
                        steer_np = root.attachNewNode(role + "_steer")
                        steer_np.setPos(float(translation[0]), float(translation[1]), float(translation[2]))
                        front_steers.append(steer_np)
                        spin_np = steer_np.attachNewNode(role + "_spin")
                    else:
                        spin_np = root.attachNewNode(role + "_spin")
                        spin_np.setPos(float(translation[0]), float(translation[1]), float(translation[2]))
                    self._make_baked_wire_np(spin_np, role + "_wire", vertices, segments, color, thickness * 0.88)
                    if vertices:
                        xs = [v[0] for v in vertices]; zs = [v[2] for v in vertices]
                        wheel_radii.append(max(max(xs) - min(xs), max(zs) - min(zs)) * 0.5)
                    spin_nodes.append(spin_np)
                else:
                    part_np = root.attachNewNode(role + "_baked_node")
                    part_np.setPos(float(translation[0]), float(translation[1]), float(translation[2]))
                    self._make_baked_wire_np(part_np, role + "_wire", vertices, segments, color, thickness)
            if not spin_nodes:
                raise ValueError("baked vehicle loaded but wheel rig nodes were not found")
            root.setPythonTag("wheel_spin_nodes", spin_nodes)
            root.setPythonTag("front_steer_nodes", front_steers)
            root.setPythonTag("wheel_radius", max(1.0, sum(wheel_radii) / max(1, len(wheel_radii))))
            root.setPythonTag("wheel_phase", 0.0)
            root.setPythonTag("vehicle_asset_status", "baked concept vehicle wiremesh: no runtime GLB required")
            self.vehicle_asset_status = "baked concept vehicle wiremesh: no runtime GLB required"
            return True
        except Exception as exc:
            self.vehicle_asset_status = f"baked vehicle import failed: {exc}"
            return False

    def _make_cylinder_np(self, parent, name: str, radius: float, length: float, color: tuple[float, float, float, float], segments: int = 14, wire_thickness: float | None = None):
        # Cylinders now follow the same single-material + exact wire-casing rule
        # as the world and vehicles. No raw render-mode wireframe artifacts.
        half = length * 0.5
        verts = []
        for x in (-half, half):
            for i in range(segments):
                a = math.tau * i / segments
                verts.append((x, math.cos(a) * radius, math.sin(a) * radius))
        left_center = len(verts); verts.append((-half, 0, 0))
        right_center = len(verts); verts.append((half, 0, 0))
        faces = []
        for i in range(segments):
            j = (i + 1) % segments
            faces.append((i, j, segments + j, segments + i))
            faces.append((left_center, j, i))
            faces.append((right_center, segments + i, segments + j))
        wire = (min(color[0] + 0.26, 1.0), min(color[1] + 0.20, 1.0), min(color[2] + 0.16, 1.0), 1.0)
        thickness = 0.82 if wire_thickness is None else float(wire_thickness)
        return self._make_stylized_mesh_np(parent, name, verts, faces, color, wire_color=wire, thickness=thickness)

    def _add_side_turrets(self, root, color: tuple[float, float, float, float], player: bool = False) -> None:
        # Final-polish articulated seeker turrets.  Earlier arms were readable but
        # oversized; this pass keeps the same behavior while slimming the hinges,
        # arms, barrels, and muzzle FX so the GLB vehicle shape stays dominant.
        turret_color = (1.0, 0.13, 0.07, 1.0) if player else (1.0, 0.30, 0.12, 1.0)
        arm_color = (0.88, 0.10, 0.07, 1.0) if player else (0.82, 0.21, 0.11, 1.0)
        hinge_color = (1.0, 0.42, 0.16, 1.0) if player else (0.86, 0.32, 0.12, 1.0)
        flash_color = (1.0, 0.72, 0.18, 0.72)
        scale = 1.0 if player else 0.86
        base_nodes = {}
        shoulder_nodes = {}
        elbow_nodes = {}
        wrist_nodes = {}
        turret_nodes = {}
        muzzle_nodes = {}
        flash_nodes = {}
        rest_x = {}
        # Local +X faces forward. +/-Y are the vehicle sides.
        for side, y in (("left", -18.4), ("right", 18.4)):
            side_sign = -1.0 if side == "left" else 1.0
            base = root.attachNewNode(f"{side}_turret_base_hinge")
            base.setPos(1.6, y, 14.7)
            base.setR(side_sign * 1.6)
            shoulder = base.attachNewNode(f"{side}_turret_shoulder")
            # Compact welded boss at the vehicle mass.
            pivot = self._make_cylinder_np(shoulder, f"{side}_turret_shoulder_pivot", 0.92 * scale, 1.90 * scale, hinge_color, 12, 0.42)
            pivot.setR(90)
            upper = self._make_cylinder_np(shoulder, f"{side}_turret_upper_arm", 0.25 * scale, 9.9 * scale, arm_color, 10, 0.34)
            upper.setX(5.35 * scale)
            elbow = shoulder.attachNewNode(f"{side}_turret_elbow")
            elbow.setPos(10.9 * scale, 0.0, 0.0)
            elbow_pivot = self._make_cylinder_np(elbow, f"{side}_turret_elbow_pivot", 0.72 * scale, 1.38 * scale, hinge_color, 10, 0.38)
            elbow_pivot.setR(90)
            forearm = self._make_cylinder_np(elbow, f"{side}_turret_forearm", 0.23 * scale, 9.8 * scale, arm_color, 10, 0.32)
            forearm.setX(4.80 * scale)
            wrist = elbow.attachNewNode(f"{side}_turret_wrist")
            wrist.setPos(9.9 * scale, 0.0, 0.0)
            wrist_pivot = self._make_cylinder_np(wrist, f"{side}_turret_wrist_pivot", 0.58 * scale, 1.05 * scale, hinge_color, 10, 0.34)
            wrist_pivot.setR(90)
            barrel = self._make_cylinder_np(wrist, f"{side}_turret_barrel", 0.40 * scale, 13.8 * scale, turret_color, 12, 0.34)
            barrel.setX(6.65 * scale)
            muzzle = wrist.attachNewNode(f"{side}_muzzle")
            muzzle.setPos(14.80 * scale, 0.0, 0.0)
            ring = self._make_cylinder_np(muzzle, f"{side}_muzzle_ring", 0.62 * scale, 0.58 * scale, flash_color, 12, 0.30)
            ring.setScale(1.0, 1.0, 1.0)
            ring.hide()
            base_nodes[side] = base
            shoulder_nodes[side] = shoulder
            elbow_nodes[side] = elbow
            wrist_nodes[side] = wrist
            turret_nodes[side] = barrel
            muzzle_nodes[side] = muzzle
            flash_nodes[side] = ring
            rest_x[side] = 6.65 * scale
        root.setPythonTag("turret_base_nodes", base_nodes)
        root.setPythonTag("turret_shoulder_nodes", shoulder_nodes)
        root.setPythonTag("turret_elbow_nodes", elbow_nodes)
        root.setPythonTag("turret_wrist_nodes", wrist_nodes)
        root.setPythonTag("turret_nodes", turret_nodes)
        root.setPythonTag("muzzle_nodes", muzzle_nodes)
        root.setPythonTag("muzzle_flash_nodes", flash_nodes)
        root.setPythonTag("turret_barrel_rest_x", rest_x)
        root.setPythonTag("turret_aim_angles", {"left": -0.34, "right": 0.34})
        root.setPythonTag("turret_target_names", {"left": "scan", "right": "scan"})
        root.setPythonTag("turret_local_muzzles", {"left": (40.0, -18.4, 14.7), "right": (40.0, 18.4, 14.7)})

    def _make_damage_shard_np(self, parent, name: str, sx: float, sy: float, color: tuple[float, float, float, float]):
        # Final-polish target plates: small, flush, low-alpha shards. They still
        # provide part-by-part damage feedback without becoming bulky add-on boxes.
        x = sx * 0.5
        y = sy * 0.5
        verts = [
            (-x, -y * 0.64, 0),
            (x * 0.42, -y * 0.78, 0),
            (x, y * 0.10, 0),
            (x * 0.12, y, 0),
            (-x * 0.78, y * 0.44, 0),
        ]
        faces = [(0, 1, 2, 3, 4)]
        return self._make_stylized_mesh_np(parent, name, verts, faces, (color[0], color[1], color[2], 0.74), wire_color=(1.0, 0.22, 0.08, 0.68), thickness=0.22)

    def _add_target_part_nodes(self, root, color: tuple[float, float, float, float], player: bool = False) -> None:
        # Armor chunks stay separate for damage simulation, but the visual overlay
        # is now small/flush and sits close to the body mesh. On the player, the
        # same nodes hide as panels break so the vehicle visibly falls apart.
        specs = {
            "nose": (31, 0, 15.2, 4.8, 5.4, 0),
            "hood": (18, 0, 18.4, 6.8, 6.7, 0),
            "left_door": (2, -17.2, 13.0, 5.7, 3.3, -90),
            "right_door": (2, 17.2, 13.0, 5.7, 3.3, 90),
            "left_rear": (-17, -17.2, 12.5, 5.0, 3.2, -90),
            "right_rear": (-17, 17.2, 12.5, 5.0, 3.2, 90),
            "roof": (-3, 0, 22.2, 6.8, 4.8, 0),
            "tail": (-31, 0, 13.2, 4.6, 4.8, 180),
        }
        nodes = {}
        for name, (x, y, z, sx, sy, h) in specs.items():
            shard_col = (1.0, 0.22, 0.08, 0.54) if player else (1.0, 0.28, 0.06, 0.76)
            n = self._make_damage_shard_np(root, f"target_shard_{name}", sx * (0.82 if player else 1.0), sy * (0.82 if player else 1.0), shard_col)
            n.setPos(x, y, z)
            n.setH(h)
            if "door" in name or "rear" in name:
                n.setP(90)
            else:
                n.setP(0)
            nodes[name] = n
        root.setPythonTag("target_part_nodes", nodes)

    def _build_vehicle_wire_fallback(self, root, name: str, color: tuple[float, float, float, float], player: bool = False):
        # Last-resort wire outline only. The previous solid box vehicle placeholder
        # is intentionally gone; if baked vehicle data fails, the game still shows a cheap
        # non-box rig silhouette with animated wheel control nodes.
        from panda3d.core import LineSegs
        length, width, height = (84.0, 31.0, 24.0) if player else (80.0, 29.0, 22.0)
        x, y, z = length / 2, width / 2, height
        segs = LineSegs(name + "_wire_silhouette")
        segs.setThickness(1.8 if player else 1.2)
        segs.setColor(*color)
        frame = [(-x,-y,0),(x,-y,0),(x,y,0),(-x,y,0),(-x,-y,0),(-x,-y,z),(x,-y,z*0.82),(x,y,z*0.82),(-x,y,z),(-x,-y,z)]
        segs.moveTo(*frame[0])
        for point in frame[1:]:
            segs.drawTo(*point)
        for a, b in [((x,-y,0),(x,-y,z*0.82)), ((x,y,0),(x,y,z*0.82)), ((-x,y,0),(-x,y,z))]:
            segs.moveTo(*a); segs.drawTo(*b)
        root.attachNewNode(segs.create())
        spin_nodes = []
        front_steers = []
        for wx, wy, role in [(28,y,"front_left"),(28,-y,"front_right"),(-27,y,"rear_left"),(-27,-y,"rear_right")]:
            parent = root
            if role.startswith("front"):
                parent = root.attachNewNode("wheel_" + role + "_steer")
                parent.setPos(wx, wy, 6.5)
                front_steers.append(parent)
                spin = parent.attachNewNode("wheel_" + role + "_spin")
            else:
                spin = root.attachNewNode("wheel_" + role + "_spin")
                spin.setPos(wx, wy, 6.5)
            wheel = LineSegs("wheel_" + role + "_fallback")
            wheel.setThickness(1.15)
            wheel.setColor(*color)
            r = 6.5
            for i in range(18):
                a = math.tau * i / 18
                b = math.tau * (i + 1) / 18
                wheel.moveTo(math.cos(a)*r, 0, math.sin(a)*r)
                wheel.drawTo(math.cos(b)*r, 0, math.sin(b)*r)
            spin.attachNewNode(wheel.create())
            spin_nodes.append(spin)
        root.setPythonTag("wheel_spin_nodes", spin_nodes)
        root.setPythonTag("front_steer_nodes", front_steers)
        root.setPythonTag("wheel_radius", 6.5)
        root.setPythonTag("wheel_phase", 0.0)
        root.setPythonTag("vehicle_asset_status", self.vehicle_asset_status)

    def _build_vehicle(self, name: str, color: tuple[float, float, float, float], player: bool = False):
        root = self.render.attachNewNode(name)
        if not self._load_baked_vehicle_into(root, color, player):
            self._build_vehicle_wire_fallback(root, name, color, player)
        self._add_side_turrets(root, color, player)
        self._add_target_part_nodes(root, color, player=player)
        root.setPythonTag("vehicle_asset_status", self.vehicle_asset_status)
        return root

    def _rival_part_world_point(self, rival: Rival, part: TargetPart | None = None) -> tuple[float, float, float]:
        if part is None:
            live = [p for p in rival.parts if not p.destroyed]
            part = live[0] if live else TargetPart("center", 0, 0, 10, 1.0, True)
        wx = rival.x + math.cos(rival.heading) * part.lx - math.sin(rival.heading) * part.ly
        wy = rival.y + math.sin(rival.heading) * part.lx + math.cos(rival.heading) * part.ly
        wz = 15.0 + clamp(abs(part.ly) * 0.10, 0.0, 5.0)
        return wx, wy, wz

    def _player_turret_target_points(self) -> dict[str, tuple[float, float, float, str] | None]:
        live = [r for r in self.rivals if not self._rival_destroyed(r)]
        if not live:
            self.locked_rival_name = None
            return {"left": None, "right": None}
        locked = self._locked_rival() if self.locked_rival_name else None
        if locked is not None:
            live_parts = [p for p in locked.parts if not p.destroyed]
            out: dict[str, tuple[float, float, float, str] | None] = {"left": None, "right": None}
            if live_parts:
                left_part = live_parts[0]
                right_part = live_parts[min(1, len(live_parts)-1)]
                px, py, pz = self._rival_part_world_point(locked, left_part); out["left"] = (px, py, pz, locked.name + " LOCK")
                px, py, pz = self._rival_part_world_point(locked, right_part); out["right"] = (px, py, pz, locked.name + " LOCK")
            else:
                out["left"] = (locked.x, locked.y, 15.0, locked.name + " LOCK")
                out["right"] = (locked.x, locked.y, 15.0, locked.name + " LOCK")
            return out
        ranked = []
        for r in live:
            dx = r.x - self.x
            dy = r.y - self.y
            dist = math.hypot(dx, dy)
            local_y = -math.sin(self.heading) * dx + math.cos(self.heading) * dy
            ranked.append((r, dist, local_y))
        assignments: dict[str, Rival | None] = {"left": None, "right": None}
        left_candidates = sorted(ranked, key=lambda t: t[1] + (0.0 if t[2] <= 0 else 110.0))
        right_candidates = sorted(ranked, key=lambda t: t[1] + (0.0 if t[2] >= 0 else 110.0))
        if left_candidates:
            assignments["left"] = left_candidates[0][0]
        for r, _dist, _local_y in right_candidates:
            if r is not assignments["left"]:
                assignments["right"] = r
                break
        if assignments["right"] is None and len(live) >= 2:
            for r, _dist, _local_y in ranked:
                if r is not assignments["left"]:
                    assignments["right"] = r
                    break
        out: dict[str, tuple[float, float, float, str] | None] = {"left": None, "right": None}
        for side, rival in assignments.items():
            if rival is None:
                continue
            live_parts = [p for p in rival.parts if not p.destroyed]
            if live_parts:
                # Aim at different intact pieces on each chosen target so the
                # side weapons chew separate armor chunks instead of focusing a
                # single center point.
                idx = 0 if side == "left" else min(1, len(live_parts) - 1)
                px, py, pz = self._rival_part_world_point(rival, live_parts[idx])
            else:
                px, py, pz = rival.x, rival.y, 15.0
            out[side] = (px, py, pz, rival.name)
        return out

    def _update_vehicle_turret_seekers(self, vehicle_np, base_x: float, base_y: float, heading: float,
                                       target_points: dict[str, tuple[float, float, float, str] | None],
                                       dt: float, player: bool = False) -> None:
        try:
            base_nodes = vehicle_np.getPythonTag("turret_base_nodes") or {}
            shoulder_nodes = vehicle_np.getPythonTag("turret_shoulder_nodes") or {}
            elbow_nodes = vehicle_np.getPythonTag("turret_elbow_nodes") or {}
            wrist_nodes = vehicle_np.getPythonTag("turret_wrist_nodes") or {}
            angles = dict(vehicle_np.getPythonTag("turret_aim_angles") or {"left": -0.38, "right": 0.38})
            names = {}
            now = time.monotonic()
            for side in ("left", "right"):
                side_sign = -1.0 if side == "left" else 1.0
                target = target_points.get(side) if isinstance(target_points, dict) else None
                if target is not None:
                    tx, ty, _tz, label = target
                    base_node = base_nodes.get(side) if isinstance(base_nodes, dict) else None
                    if base_node is not None:
                        pos = base_node.getPos(self.render)
                        sx, sy = pos.getX(), pos.getY()
                    else:
                        sx = base_x + math.cos(heading) * 4.0 - math.sin(heading) * (22.0 * side_sign)
                        sy = base_y + math.sin(heading) * 4.0 + math.cos(heading) * (22.0 * side_sign)
                    desired = angle_wrap(math.atan2(ty - sy, tx - sx) - heading)
                    desired = clamp(desired, -1.15, 1.15)
                    names[side] = str(label)
                    slew = 4.4 if player else 2.6
                else:
                    desired = side_sign * (0.55 + math.sin(now * 1.35 + (0.0 if side == "left" else 1.9)) * 0.30)
                    names[side] = "scan"
                    slew = 1.4
                cur = float(angles.get(side, side_sign * 0.38))
                cur += clamp(angle_wrap(desired - cur), -slew * dt, slew * dt)
                cur = clamp(cur, -1.25, 1.25)
                angles[side] = cur
                base_node = base_nodes.get(side) if isinstance(base_nodes, dict) else None
                shoulder = shoulder_nodes.get(side) if isinstance(shoulder_nodes, dict) else None
                elbow = elbow_nodes.get(side) if isinstance(elbow_nodes, dict) else None
                wrist = wrist_nodes.get(side) if isinstance(wrist_nodes, dict) else None
                # Distribute the yaw through the arm like a robotic appendage so
                # it feels hinged rather than a single barrel rotating in place.
                if base_node is not None:
                    base_node.setH(math.degrees(cur * 0.22))
                    base_node.setP(math.sin(now * 2.2 + side_sign) * 1.2)
                    base_node.setR(side_sign * (3.0 + abs(cur) * 2.0))
                if shoulder is not None:
                    shoulder.setH(math.degrees(cur * 0.34))
                    shoulder.setP(-2.0 + abs(cur) * 3.0)
                if elbow is not None:
                    elbow.setH(math.degrees(cur * 0.28))
                    elbow.setP(2.5 + math.sin(now * 3.1 + side_sign * 0.4) * 0.8)
                if wrist is not None:
                    wrist.setH(math.degrees(cur * 0.16))
                    wrist.setP(-1.5 + abs(cur) * 1.6)
            vehicle_np.setPythonTag("turret_aim_angles", angles)
            vehicle_np.setPythonTag("turret_target_names", names)
        except Exception:
            pass

    def _current_turret_aim_angle(self, vehicle_np, heading: float, side: str) -> float:
        try:
            angles = vehicle_np.getPythonTag("turret_aim_angles") or {}
            return heading + float(angles.get(side, 0.0))
        except Exception:
            return heading

    def _make_ramp_np(self, parent, name: str, length: float, width: float, height: float, color: tuple[float, float, float, float]):
        half_l = length * 0.5; half_w = width * 0.5
        verts = [
            (-half_l, -half_w, 0), (-half_l, half_w, 0), (half_l, -half_w, height), (half_l, half_w, height),
            (-half_l, -half_w, -1.2), (-half_l, half_w, -1.2), (half_l, -half_w, -1.2), (half_l, half_w, -1.2),
        ]
        faces = [(0, 2, 3, 1), (4, 5, 7, 6), (0, 4, 6, 2), (1, 3, 7, 5), (0, 1, 5, 4), (2, 6, 7, 3)]
        return self._make_stylized_mesh_np(parent, name, verts, faces, color, wire_color=(0.45, 0.12, 0.12, 0.88), thickness=0.46)

    def _animate_vehicle_controls(self, vehicle_np, speed: float, steer_amount: float, dt: float) -> None:
        try:
            spin_nodes = vehicle_np.getPythonTag("wheel_spin_nodes") or []
            steer_nodes = vehicle_np.getPythonTag("front_steer_nodes") or []
            radius = float(vehicle_np.getPythonTag("wheel_radius") or 6.5)
            phase = float(vehicle_np.getPythonTag("wheel_phase") or 0.0)
            phase -= (float(speed) / max(radius, 0.5)) * max(dt, 0.001) * 58.0
            vehicle_np.setPythonTag("wheel_phase", phase)
            for spin in spin_nodes:
                # Wheels are modeled with axle along local Y, so Panda roll gives
                # the visible spin while preserving the wireframe performance path.
                spin.setR(phase)
            steer = clamp(float(steer_amount), -1.0, 1.0) * 29.0
            for steer_np in steer_nodes:
                # Front control nodes yaw around local Z for steering.
                steer_np.setH(steer)
            turret_nodes = vehicle_np.getPythonTag("turret_nodes") or {}
            flash_nodes = vehicle_np.getPythonTag("muzzle_flash_nodes") or {}
            for side in ("left", "right"):
                timer_name = f"{side}_recoil"
                timer = max(0.0, float(vehicle_np.getPythonTag(timer_name) or 0.0) - dt * 8.0)
                vehicle_np.setPythonTag(timer_name, timer)
                barrel = turret_nodes.get(side) if isinstance(turret_nodes, dict) else None
                rest_map = vehicle_np.getPythonTag("turret_barrel_rest_x") or {}
                if barrel is not None:
                    recoil = -2.2 * timer
                    rest = float(rest_map.get(side, 6.65)) if isinstance(rest_map, dict) else 6.65
                    barrel.setX(rest + recoil)
                    barrel.setP(math.sin(time.monotonic() * 11.0 + (0 if side == "left" else 2.1)) * 1.2 * timer)
                flash = flash_nodes.get(side) if isinstance(flash_nodes, dict) else None
                if flash is not None:
                    if timer > 0.05:
                        flash.show(); flash.setScale(0.72 + timer * 1.35)
                    else:
                        flash.hide()
        except Exception:
            pass

    def _build_scene(self) -> None:
        from direct.gui.OnscreenText import OnscreenText
        from direct.gui.DirectGui import DirectFrame, DirectButton
        from panda3d.core import LineSegs, TextNode

        self.tile_root = self.render.attachNewNode("terrain_tiles")
        self.tiles = []
        tile_count = 13
        for ix in range(tile_count):
            for iy in range(tile_count):
                tile = self._make_tile_np(self.tile_root, f"tile_{ix}_{iy}", 180.0, (0.045, 0.047, 0.052, 1))
                tile.setZ(-0.8)
                self.tiles.append((ix - tile_count//2, iy - tile_count//2, tile))

        lines = LineSegs("open_world_grid")
        lines.setThickness(1.4)
        lines.setColor(0.25, 0.045, 0.050, 0.82)
        for line in range(-4200, 4201, 400):
            lines.moveTo(line, -4200, 0.2); lines.drawTo(line, 4200, 0.2)
            lines.moveTo(-4200, line, 0.2); lines.drawTo(4200, line, 0.2)
        self.grid_np = self.render.attachNewNode(lines.create())

        self.prop_root = self.render.attachNewNode("arena_props")
        rng = random.Random(self.seed + 2301)
        self.props = []
        self.prop_colliders = []
        # Purpose-built ramps ride on the same heightmap used by vehicle physics.
        self.ramp_specs = []
        ramp_templates = [
            (260, -60, 0.18, 185, 58, 32),
            (520, 210, -0.45, 220, 70, 42),
            (-360, 260, 0.72, 190, 64, 34),
            (920, -240, 0.05, 260, 76, 48),
            (-780, -330, -0.62, 230, 72, 40),
        ]
        for i, (rx, ry, rh, rl, rw, rz) in enumerate(ramp_templates):
            spec = {"x": float(rx), "y": float(ry), "h": float(rh), "length": float(rl), "width": float(rw), "height": float(rz), "z": self._terrain_height(rx, ry)}
            self.ramp_specs.append(spec)
            ramp = self._make_ramp_np(self.prop_root, f"rideable_ramp_{i}", rl, rw, rz, (0.065, 0.065, 0.070, 0.92))
            ramp.setPos(rx, ry, spec["z"]); ramp.setH(math.degrees(rh)); ramp.setTransparency(True); self.props.append(ramp)
            self._register_prop_collider(ramp, rx, ry, max(rl, rw) * 0.42, 9999.0, 0.0, f"rideable_ramp_{i}", hp=9999.0, kind="ramp")
        showcase_props = [
            (180, 190, 72, 38, 22), (310, -190, 86, 34, 31), (455, 210, 64, 88, 18),
            (610, -50, 46, 46, 38), (-170, 150, 70, 30, 24), (120, -260, 98, 42, 18),
        ]
        for i, (px, py, sx, sy, sz) in enumerate(showcase_props):
            n = self._make_wreck_np(self.prop_root, f"spawn_wreck_{i}", sx, sy, sz, (0.115, 0.115, 0.122, 1.0), seed=100+i)
            n.setPos(px, py, self._terrain_height(px, py) + sz/2); n.setH(rng.uniform(0, 360)); self.props.append(n)
            self._register_prop_collider(n, px, py, max(sx, sy) * 0.48, 850.0, 0.24, f"spawn_wreck_{i}", hp=5.5)
        # Cleaner battlefield: fewer props, no rectangular crate spam. Every prop
        # is a shaped single-material mesh with an exact wire casing.
        for i in range(30):
            sx = rng.uniform(30, 104); sy = rng.uniform(24, 86); sz = rng.uniform(10, 48)
            col = rng.choice([(0.060,0.060,0.066,1.0), (0.090,0.090,0.098,1.0), (0.125,0.125,0.136,1.0), (0.045,0.045,0.052,1.0)])
            n = self._make_wreck_np(self.prop_root, f"wreck_{i}", sx, sy, sz, col, seed=i)
            px = rng.uniform(-2600, 2600); py = rng.uniform(-2600, 2600)
            n.setPos(px, py, self._terrain_height(px, py) + sz/2)
            n.setH(rng.uniform(0, 360))
            self.props.append(n)
            self._register_prop_collider(n, px, py, max(sx, sy) * 0.46, 720.0, 0.20, f"wreck_{i}", hp=4.0 + sz * 0.035)

        self.player_np = self._build_vehicle("player_car", (0.82, 0.03, 0.02, 1), True)
        self.rival_nps = [self._build_vehicle(f"rival_{i}", (0.8, 0.15, 0.10, 1), False) for i in range(18)]
        self.pickup_nps = [self._make_octahedron_np(self.render, f"pickup_{i}", 8.0, 15.0, (0.2, 0.85, 0.55, 1.0)) for i in range(44)]
        self.pedestrian_nps = [self._make_octahedron_np(self.render, f"pedestrian_{i}", 3.8, 13.0, (0.78, 0.60, 0.46, 1.0)) for i in range(32)]
        self.projectile_nps = [self._make_octahedron_np(self.render, f"shot_{i}", 2.2, 6.0, (1.0, 0.86, 0.25, 1.0)) for i in range(128)]
        self.explosion_nps = [self._make_octahedron_np(self.render, f"boom_{i}", 5.4, 13.0, (1.0, 0.40, 0.08, 1.0)) for i in range(96)]
        self.muzzle_flash_nps = [self._make_cylinder_np(self.render, f"muzzle_flash_{i}", 2.4, 3.6, (1.0, 0.82, 0.24, 1.0), 10, 0.32) for i in range(32)]
        for n in self.rival_nps + self.pickup_nps + self.pedestrian_nps + self.projectile_nps + self.explosion_nps + self.muzzle_flash_nps:
            n.hide()
        for n in self.pedestrian_nps + self.projectile_nps + self.explosion_nps + self.muzzle_flash_nps:
            try:
                n.setTransparency(True)
                n.setDepthWrite(False)
            except Exception:
                pass

        self.hud_panel = DirectFrame(frameColor=(0.035, 0.006, 0.008, 0.74), frameSize=(-1.35, -0.13, 0.67, 0.985), pos=(0, 0, 0))
        self.hud_panel.setTransparency(True)
        self.bottom_panel = DirectFrame(frameColor=(0.030, 0.006, 0.008, 0.58), frameSize=(-1.22, 1.22, -0.985, -0.855), pos=(0, 0, 0))
        self.bottom_panel.setTransparency(True)
        self.hud = OnscreenText(text="", pos=(-1.28, 0.92), scale=0.038, fg=(0.96, 0.90, 0.88, 1), align=TextNode.ALeft, mayChange=True)
        self.metal_status = OnscreenText(text="", pos=(-1.28, 0.70), scale=0.033, fg=(1.0, 0.32, 0.22, 1), align=TextNode.ALeft, mayChange=True)
        self.help_text = OnscreenText(text="", pos=(0.0, -0.93), scale=0.032, fg=(0.90, 0.84, 0.82, 1), align=TextNode.ACenter, mayChange=True)
        self.pause_text = OnscreenText(text="", pos=(0, 0.04), scale=0.10, fg=(1.0, 0.14, 0.10, 1), align=TextNode.ACenter, mayChange=True)
        self.credit_text = OnscreenText(text="by GLITCHED MATRIX Prototype Lab", pos=(1.29, -0.985), scale=0.023, fg=(0.62, 0.28, 0.32, 0.62), align=TextNode.ARight, mayChange=False)
        self._build_pause_menu()

    def _build_pause_menu(self) -> None:
        from direct.gui.DirectGui import DirectFrame, DirectButton
        from direct.gui.OnscreenText import OnscreenText
        from panda3d.core import TextNode
        self.pause_panel = DirectFrame(
            frameColor=(0.045, 0.006, 0.010, 0.94),
            frameSize=(-0.74, 0.74, -0.50, 0.58),
            pos=(0, 0, 0.02),
        )
        self.pause_panel.setTransparency(True)
        self.pause_panel.hide()
        self.pause_menu_title = OnscreenText(text="CODE RED ARCADE SETTINGS", pos=(0, 0.49), scale=0.047, fg=(1.0, 0.26, 0.17, 1), align=TextNode.ACenter, mayChange=True, parent=self.pause_panel)
        self.pause_menu_status = OnscreenText(text="", pos=(0, 0.37), scale=0.034, fg=(0.90, 0.88, 0.80, 1), align=TextNode.ACenter, mayChange=True, parent=self.pause_panel)
        def button(label, z, cmd):
            b = DirectButton(
                parent=self.pause_panel, text=label, pos=(0, 0, z), scale=0.047, command=cmd,
                frameColor=(0.18, 0.025, 0.035, 0.92),
                text_fg=(0.98, 0.91, 0.88, 1),
                frameSize=(-5.2, 5.2, -0.55, 0.55),
                relief=1,
            )
            b.setTransparency(True)
            return b
        self.pause_buttons = [
            button("RESUME", 0.24, self._toggle_pause),
            button("ZOOM IN  /  TIGHTER FOV", 0.12, lambda: self._mouse_wheel_zoom(-1)),
            button("ZOOM OUT / WIDER FOV", 0.00, lambda: self._mouse_wheel_zoom(1)),
            button("BASE FOV -", -0.12, lambda: self._set_fov_delta(-2.0)),
            button("BASE FOV +", -0.24, lambda: self._set_fov_delta(2.0)),
            button("TOGGLE FULLSCREEN", -0.36, self._toggle_fullscreen),
            button("EXIT ARCADE", -0.48, self._close),
        ]

    def _set_pause_menu_visible(self, visible: bool) -> None:
        try:
            if visible:
                self.pause_panel.show()
            else:
                self.pause_panel.hide()
        except Exception:
            pass

    def _task_update(self, task):
        now = time.monotonic()
        dt = clamp(now - self.last_tick, 0.001, 0.05)
        self.last_tick = now
        self.scene_dt = dt
        self._load_settings()
        if not self.paused:
            self._update_world(dt)
        self._sync_scene()
        self.frame_index += 1
        return self.Task.cont

    def _muzzle_world(self, base_x: float, base_y: float, heading: float, side: str, vehicle_np=None) -> tuple[float, float, float]:
        if vehicle_np is not None:
            try:
                muzzle_nodes = vehicle_np.getPythonTag("muzzle_nodes") or {}
                muzzle = muzzle_nodes.get(side) if isinstance(muzzle_nodes, dict) else None
                if muzzle is not None:
                    pos = muzzle.getPos(self.render)
                    return pos.getX(), pos.getY(), self._current_turret_aim_angle(vehicle_np, heading, side)
            except Exception:
                pass
        local_y = -22.0 if side == "left" else 22.0
        local_x = 56.0
        aim = heading
        wx = base_x + math.cos(aim) * local_x - math.sin(aim) * local_y
        wy = base_y + math.sin(aim) * local_x + math.cos(aim) * local_y
        return wx, wy, aim

    def _apply_rival_part_damage(self, rival: Rival, hit_x: float, hit_y: float, damage: float) -> TargetPart | None:
        live_parts = [p for p in rival.parts if not p.destroyed]
        if not live_parts:
            return None
        dx = hit_x - rival.x; dy = hit_y - rival.y
        ch = math.cos(rival.heading); sh = math.sin(rival.heading)
        lx = ch * dx + sh * dy
        ly = -sh * dx + ch * dy
        part = min(live_parts, key=lambda p: (p.lx - lx) ** 2 + (p.ly - ly) ** 2)
        part.hp -= max(0.15, damage)
        if part.hp <= 0.0:
            part.destroyed = True
            self.score += 45
        live_left = [p for p in rival.parts if not p.destroyed]
        rival.hp = max(0.0, len(live_left) / max(1, len(rival.parts)))
        return part

    def _apply_player_part_damage(self, hit_x: float, hit_y: float, damage: float) -> TargetPart | None:
        live_parts = [p for p in self.player_parts if not p.destroyed]
        if not live_parts:
            return None
        dx = hit_x - self.x; dy = hit_y - self.y
        ch = math.cos(self.heading); sh = math.sin(self.heading)
        lx = ch * dx + sh * dy
        ly = -sh * dx + ch * dy
        part = min(live_parts, key=lambda p: (p.lx - lx) ** 2 + (p.ly - ly) ** 2)
        part.hp -= max(0.12, damage)
        if part.hp <= 0.0:
            part.destroyed = True
            self.score = max(0, self.score - 60)
            self.sound.play("break", 0.70, throttle=0.04, loud=True)
        else:
            self.sound.play("hit", 0.52, throttle=0.05, loud=True)
        live_left = [p for p in self.player_parts if not p.destroyed]
        self.hp = max(0.0, self.max_hp * len(live_left) / max(1, len(self.player_parts)))
        return part

    def _reset_player_vehicle(self) -> None:
        self.score = max(0, self.score - 500)
        self.player_parts = make_player_parts()
        self.hp = self.max_hp
        self.x *= 0.7; self.y *= 0.7; self.z = self._terrain_height(self.x, self.y) + self._hover_clearance()
        self.vx = self.vy = self.vz = 0.0
        self.airborne = False
        self.explosions.append((self.x, self.y, 0.0, 120))
        self.sound.play("explosion", 0.85, throttle=0.10, loud=True)

    def _rival_destroyed(self, rival: Rival) -> bool:
        return all(p.destroyed for p in rival.parts)

    def _hover_clearance(self) -> float:
        # Keeps the wire-body visibly floating above terrain and ramp faces so it
        # no longer looks half-submerged in the height mesh.
        return float(getattr(self, "hover_height", 6.1))

    def _register_prop_collider(self, node, x: float, y: float, radius: float, mass: float, damage_scale: float, name: str, hp: float = 6.0, kind: str = "solid") -> None:
        try:
            node.setPythonTag("collider_radius", float(radius))
            node.setPythonTag("collider_hp", float(hp))
            node.setPythonTag("collider_kind", kind)
        except Exception:
            pass
        self.prop_colliders.append(PropCollider(float(x), float(y), float(radius), float(mass), float(damage_scale), name, kind, float(hp), node))

    def _ramp_launch_hint(self, prev_x: float, prev_y: float, x: float, y: float, speed: float) -> float:
        # Detect riding through the raised lip of a ramp. Ramps remain passable
        # terrain, not blockers; this just hands the vertical solver extra takeoff.
        best = 0.0
        for spec in getattr(self, "ramp_specs", []):
            try:
                a = -float(spec["h"])
                half_l = float(spec["length"]) * 0.5
                half_w = float(spec["width"]) * 0.5
                def local(px, py):
                    dx = px - float(spec["x"]); dy = py - float(spec["y"])
                    return math.cos(a) * dx - math.sin(a) * dy, math.sin(a) * dx + math.cos(a) * dy
                lx0, ly0 = local(prev_x, prev_y)
                lx1, ly1 = local(x, y)
                inside_y = abs(ly1) <= half_w * 1.08
                moving_up_ramp = lx1 > lx0 and lx1 > half_l * 0.18
                near_lip = half_l * 0.38 <= lx1 <= half_l * 1.25
                if inside_y and moving_up_ramp and near_lip and speed > 9.0:
                    edge = clamp(1.0 - abs(ly1) / max(1.0, half_w), 0.0, 1.0)
                    best = max(best, float(spec["height"]) * (0.13 + edge * 0.17) + speed * 0.055)
            except Exception:
                continue
        return best

    def _apply_collision_impulse_to_player(self, hit_x: float, hit_y: float, force: float) -> None:
        if force <= 0.02:
            return
        dmg = clamp(force * 0.020, 0.05, 1.25)
        part = self._apply_player_part_damage(hit_x, hit_y, dmg)
        if part is not None:
            self.explosions.append((hit_x, hit_y, 0.0, 18 + force * 0.55))

    def _apply_collision_impulse_to_rival(self, rival: Rival, hit_x: float, hit_y: float, force: float) -> None:
        if force <= 0.02:
            return
        part = self._apply_rival_part_damage(rival, hit_x, hit_y, clamp(force * 0.018, 0.04, 1.10))
        if part is not None:
            self.explosions.append((hit_x, hit_y, 0.0, 16 + force * 0.42))

    def _damage_prop_collider(self, col: PropCollider, force: float) -> None:
        if col.kind != "solid" or col.hp <= 0.0:
            return
        col.hp -= max(0.02, force * col.damage_scale)
        node = col.node
        if node is not None:
            try:
                node.setPythonTag("collider_hp", col.hp)
                fade = clamp(col.hp / 6.0, 0.10, 1.0)
                node.setAlphaScale(0.30 + fade * 0.70)
                node.setScale(0.92 + fade * 0.08)
                if col.hp <= 0.0:
                    node.hide()
            except Exception:
                pass
        if col.hp <= 0.0:
            self.score += 25
            self.sound.play("break", 0.55, throttle=0.06, x=col.x, y=col.y)
            self.explosions.append((col.x, col.y, 0.0, 42 + col.radius * 0.20))

    def _resolve_circle_collision(self, ax: float, ay: float, ar: float, bx: float, by: float, br: float) -> tuple[float, float, float] | None:
        dx = ax - bx; dy = ay - by
        dist = math.hypot(dx, dy)
        min_d = max(0.1, ar + br)
        if dist >= min_d:
            return None
        if dist < 0.001:
            return 1.0, 0.0, min_d
        return dx / dist, dy / dist, min_d - dist

    def _apply_world_collisions(self, prev_x: float, prev_y: float, dt: float) -> None:
        # Lightweight arcade collision layer: props, rivals, and the player all
        # have physical radii, bounce response, and gradual armor/object damage.
        player_radius = 31.0
        speed = math.hypot(self.vx, self.vy)
        for col in list(getattr(self, "prop_colliders", [])):
            if col.kind != "solid" or col.hp <= 0.0:
                continue
            res = self._resolve_circle_collision(self.x, self.y, player_radius, col.x, col.y, col.radius)
            if not res:
                continue
            nx, ny, depth = res
            self.x += nx * depth * 0.92
            self.y += ny * depth * 0.92
            inward = self.vx * nx + self.vy * ny
            force = max(0.0, -inward) + speed * clamp(depth / max(1.0, col.radius), 0.0, 1.0) * 0.35
            if inward < 0.0:
                self.vx -= nx * inward * 1.22
                self.vy -= ny * inward * 1.22
            self.vx *= 0.82; self.vy *= 0.82
            if force > 2.0:
                self._apply_collision_impulse_to_player(col.x, col.y, force)
                self._damage_prop_collider(col, force * 0.055)
        # Player <-> rival vehicle contact. Both sides separate and lose chunks
        # progressively rather than exploding as a whole target.
        for r in list(self.rivals):
            if self._rival_destroyed(r):
                continue
            res = self._resolve_circle_collision(self.x, self.y, player_radius, r.x, r.y, 30.0)
            if not res:
                continue
            nx, ny, depth = res
            self.x += nx * depth * 0.52; self.y += ny * depth * 0.52
            r.x -= nx * depth * 0.48; r.y -= ny * depth * 0.48
            rel_vx = self.vx - math.cos(r.heading) * r.speed
            rel_vy = self.vy - math.sin(r.heading) * r.speed
            force = abs(rel_vx * nx + rel_vy * ny) + depth * 0.30
            self.vx += nx * force * 0.26; self.vy += ny * force * 0.26
            r.speed *= 0.62
            if force > 2.0:
                hx = (self.x + r.x) * 0.5; hy = (self.y + r.y) * 0.5
                self._apply_collision_impulse_to_player(hx, hy, force)
                self._apply_collision_impulse_to_rival(r, hx, hy, force)
                self.sound.play("hit", 0.50, throttle=0.06, x=hx, y=hy)
        # Rival <-> prop contact so the whole arena has collision, not just the
        # player.  This keeps AI vehicles from visually driving through objects.
        for r in list(self.rivals):
            for col in list(getattr(self, "prop_colliders", [])):
                if col.kind != "solid" or col.hp <= 0.0:
                    continue
                res = self._resolve_circle_collision(r.x, r.y, 29.0, col.x, col.y, col.radius)
                if not res:
                    continue
                nx, ny, depth = res
                r.x += nx * depth * 0.78; r.y += ny * depth * 0.78
                impact = max(0.0, r.speed) * clamp(depth / max(1.0, col.radius), 0.0, 1.0)
                r.speed *= -0.22
                if impact > 2.0:
                    self._apply_collision_impulse_to_rival(r, col.x, col.y, impact)
                    self._damage_prop_collider(col, impact * 0.035)
        # Rival <-> rival separation.
        for i, a in enumerate(self.rivals):
            for b in self.rivals[i+1:]:
                res = self._resolve_circle_collision(a.x, a.y, 28.0, b.x, b.y, 28.0)
                if not res:
                    continue
                nx, ny, depth = res
                a.x += nx * depth * 0.5; a.y += ny * depth * 0.5
                b.x -= nx * depth * 0.5; b.y -= ny * depth * 0.5
                a.speed *= 0.72; b.speed *= 0.72

    def _update_world(self, dt: float) -> None:
        s = self._stat_block()
        accelerating = bool({"w", "arrow_up"} & self.keys)
        braking = bool({"s", "arrow_down"} & self.keys)
        left = bool({"a", "arrow_left"} & self.keys)
        right = bool({"d", "arrow_right"} & self.keys)
        boosting = bool({"shift"} & self.keys) and self.boost_heat < 1.0
        speed = math.hypot(self.vx, self.vy)
        # Steering was visually reversed after the vehicle rig pass, so this intentionally
        # swaps left/right input while also tightening the turning radius.
        steer_sign = (1 if left else 0) + (-1 if right else 0)
        if steer_sign:
            drift = clamp(1.34 - s["stability"] * 0.16, 0.74, 1.40)
            low_speed_grab = 1.28 if speed < s["max_speed"] * 0.32 else 1.0
            self.heading += steer_sign * s["turn_rate"] * drift * low_speed_grab * dt * (1.08 + min(speed / max(s["max_speed"], 1.0), 1.85))
        ax = math.cos(self.heading); ay = math.sin(self.heading)
        if accelerating:
            power = s["accel"] * (1.75 if boosting else 1.0)
            self.vx += ax * power * dt; self.vy += ay * power * dt
        if braking:
            self.vx -= ax * s["accel"] * 0.68 * dt; self.vy -= ay * s["accel"] * 0.68 * dt
        if boosting:
            if not self.was_boosting:
                self.sound.play("boost", 0.70, throttle=0.35, loud=True)
            self.boost_heat = min(1.0, self.boost_heat + dt * 0.42)
        else:
            self.boost_heat = max(0.0, self.boost_heat - dt * 0.20)
        self.was_boosting = boosting
        if hasattr(self, "sound"):
            self.sound.update_engine(math.hypot(self.vx, self.vy), boosting)
        rough = self._terrain_roughness(self.x, self.y)
        friction = s["friction"] - rough * 0.022
        self.vx *= friction; self.vy *= friction
        speed = math.hypot(self.vx, self.vy)
        max_speed = s["max_speed"] * (1.22 if boosting else 1.0) * (1.0 - rough * 0.08)
        if speed > max_speed:
            scale = max_speed / max(speed, 0.0001)
            self.vx *= scale; self.vy *= scale
        prev_ground = getattr(self, "last_ground_z", self._terrain_height(self.x, self.y))
        prev_x, prev_y = self.x, self.y
        self.x += self.vx; self.y += self.vy
        self._apply_world_collisions(prev_x, prev_y, dt)
        ground = self._terrain_height(self.x, self.y)
        speed = math.hypot(self.vx, self.vy)
        hover = self._hover_clearance()
        drop = ground - prev_ground
        ramp_kick = self._ramp_launch_hint(prev_x, prev_y, self.x, self.y, speed)
        if self.airborne:
            # Per-frame vertical velocity is kept compatible with the existing
            # arcade solver, but gravity is stronger and visible now.
            self.vz -= 38.0 * dt
            self.z += self.vz
            if self.z <= ground + hover:
                self.z = ground + hover
                self.vz = 0.0
                self.airborne = False
                self.sound.play("land", 0.45, throttle=0.10, loud=True)
        else:
            # Leave ramp lips and steep downhill breaks with real vertical motion.
            if speed > 10.0 and (drop < -1.05 or ramp_kick > 0.1):
                self.airborne = True
                self.vz = clamp(abs(drop) * 0.76 + speed * 0.070 + ramp_kick, 6.0, 34.0)
                self.z = max(self.z, ground + hover) + self.vz * 0.08
                self.sound.play("jump", 0.72, throttle=0.25, loud=True)
            else:
                self.z += ((ground + hover) - self.z) * clamp(13.0 * dt, 0.0, 1.0)
                self.vz = 0.0
        self.last_ground_z = ground
        # LMB drives the left turret; RMB drives the right turret.
        # Keyboard fallbacks stay grouped by side.
        if {"control", "mouse1"} & (self.keys | self.mouse_buttons):
            self._fire("left")
        if {"q", "e", "mouse3"} & (self.keys | self.mouse_buttons):
            self._fire("right")
        self.fire_cooldown = max(0.0, self.fire_cooldown - dt)
        self.missile_cooldown = max(0.0, self.missile_cooldown - dt)
        self.left_flash_timer = max(0.0, self.left_flash_timer - dt)
        self.right_flash_timer = max(0.0, self.right_flash_timer - dt)
        self._update_projectiles(dt)
        self._update_rivals(dt)
        self._update_pickups(dt)
        self._update_pedestrians(dt)
        self._update_peers()
        if not self.rivals:
            self.wave += 1
            self._spawn_wave(reset=True)

    def _fire(self, side: str = "left") -> None:
        if not bool(self.arcade_options.get("weapons_enabled", True)):
            return
        side = "right" if side == "right" else "left"
        if side == "left":
            if self.fire_cooldown > 0: return
            self.fire_cooldown = 0.095
            self.left_flash_timer = 0.08
            color = "#ffdf6e"
            self.sound.play("fire_left", 0.58, throttle=0.025, loud=True)
        else:
            if self.missile_cooldown > 0: return
            self.missile_cooldown = 0.135
            self.right_flash_timer = 0.08
            color = "#67d7ff"
            self.sound.play("fire_right", 0.58, throttle=0.025, loud=True)
        speed = 21.0; dmg = 0.54; radius = 2.8
        vehicle_np = getattr(self, "player_np", None)
        px, py, aim = self._muzzle_world(self.x, self.y, self.heading, side, vehicle_np)
        self.muzzle_flashes.append((px, py, 0.0, side))
        try:
            if vehicle_np is not None:
                vehicle_np.setPythonTag(f"{side}_recoil", 1.0)
        except Exception:
            pass
        self.projectiles.append(Projectile(px, py, self.vx * 0.32 + math.cos(aim) * speed, self.vy * 0.32 + math.sin(aim) * speed, "player", ttl=1.45, damage=dmg, radius=radius, color=color, side=side))

    def _update_projectiles(self, dt: float) -> None:
        survivors: list[Projectile] = []
        for p in self.projectiles:
            p.x += p.vx; p.y += p.vy; p.ttl -= dt
            if p.ttl <= 0: continue
            hit = False
            if p.owner == "player":
                for r in list(self.rivals):
                    if (r.x - p.x) ** 2 + (r.y - p.y) ** 2 < (34 + p.radius) ** 2:
                        part = self._apply_rival_part_damage(r, p.x, p.y, p.damage)
                        self.sound.play("hit", 0.50, throttle=0.03, x=p.x, y=p.y)
                        self.explosions.append((p.x, p.y, 0.0, 30 + p.radius * 4)); self._burst_fx(p.x, p.y, 24 + p.radius * 4, 3); hit = True
                        if part is not None and part.destroyed:
                            ox = r.x + math.cos(r.heading) * part.lx - math.sin(r.heading) * part.ly
                            oy = r.y + math.sin(r.heading) * part.lx + math.cos(r.heading) * part.ly
                            self.sound.play("break", 0.72, throttle=0.04, x=ox, y=oy)
                            self.explosions.append((ox, oy, 0.0, 46)); self._burst_fx(ox, oy, 36, 4)
                        if self._rival_destroyed(r):
                            self.sound.play("explosion", 0.82, throttle=0.06, x=r.x, y=r.y, loud=True)
                            self.rivals.remove(r); self.kills += 1; self.score += 250 + self.wave * 25; self.explosions.append((r.x, r.y, 0.0, 96)); self._burst_fx(r.x, r.y, 70, 9)
                        break
            else:
                if (self.x - p.x) ** 2 + (self.y - p.y) ** 2 < (22 + p.radius) ** 2:
                    part = self._apply_player_part_damage(p.x, p.y, p.damage)
                    self.explosions.append((p.x, p.y, 0.0, 44)); hit = True
                    if part is not None and part.destroyed:
                        ox = self.x + math.cos(self.heading) * part.lx - math.sin(self.heading) * part.ly
                        oy = self.y + math.sin(self.heading) * part.lx + math.cos(self.heading) * part.ly
                        self.explosions.append((ox, oy, 0.0, 52))
                    if self.hp <= 0 or not [pt for pt in self.player_parts if not pt.destroyed]:
                        self._reset_player_vehicle()
            if not hit:
                survivors.append(p)
        self.projectiles = survivors[-128:]
        self.explosions = [(x, y, age + dt, size) for x, y, age, size in self.explosions if age < 0.75]
        self.muzzle_flashes = [(x, y, age + dt, side) for x, y, age, side in self.muzzle_flashes if age < 0.18]

    def _update_rivals(self, dt: float) -> None:
        s = self._stat_block()
        for idx, r in enumerate(list(self.rivals)):
            dx = self.x - r.x; dy = self.y - r.y; dist = max(1.0, math.hypot(dx, dy)); desired = math.atan2(dy, dx)
            if dist < 140:
                desired += math.pi * 0.68
            for j, other in enumerate(self.rivals):
                if j == idx: continue
                ox = r.x - other.x; oy = r.y - other.y; od = math.hypot(ox, oy)
                if 0.1 < od < 105:
                    desired = math.atan2(oy, ox); break
            r.heading += clamp(angle_wrap(desired - r.heading), -2.2 * dt, 2.2 * dt)
            target_speed = clamp(s["max_speed"] * (0.56 + self.wave * 0.035), 14, 56)
            if dist > 240:
                r.speed = min(target_speed, r.speed + s["accel"] * 0.48 * dt)
            elif dist < 125:
                r.speed = max(-target_speed * 0.25, r.speed - s["accel"] * 0.45 * dt)
            else:
                r.speed *= 0.992
            r.x += math.cos(r.heading) * r.speed; r.y += math.sin(r.heading) * r.speed; r.speed *= 0.972
            r.cooldown = max(0.0, r.cooldown - dt)
            if dist < 620 and r.cooldown <= 0.0 and bool(self.arcade_options.get("rivals_fire", True)):
                r.cooldown = random.uniform(0.55, 1.35)
                lead = math.atan2(dy + self.vy * 10, dx + self.vx * 10)
                side = "left" if random.random() < 0.5 else "right"
                vehicle_np = self.rival_nps[idx] if hasattr(self, "rival_nps") and idx < len(self.rival_nps) else None
                px, py, aim = self._muzzle_world(r.x, r.y, r.heading, side, vehicle_np)
                # Rivals still lead the player, but the projectile now leaves from
                # the animated seeker muzzle instead of the old fixed side slot.
                aim = angle_wrap(lead - aim) * 0.35 + aim
                self.projectiles.append(Projectile(px, py, math.cos(aim) * 12 + r.speed * 0.1, math.sin(aim) * 12 + r.speed * 0.1, "rival", ttl=2.0, damage=0.55, radius=2.8, color="#ff4a4a", side=side))

    def _update_pickups(self, dt: float) -> None:
        for p in list(self.pickups):
            p.pulse += dt
            if (self.x - p.x) ** 2 + (self.y - p.y) ** 2 < 34 ** 2:
                if p.kind == "repair":
                    self.hp = min(self.max_hp, self.hp + 2.0); self.score += 50
                    for part in self.player_parts:
                        if part.destroyed:
                            part.destroyed = False; part.hp = max(part.hp, 0.75); break
                elif p.kind == "boost": self.boost_heat = max(0.0, self.boost_heat - 0.45); self.score += 75
                else: self.score += 150
                self.sound.play("pickup", 0.62, throttle=0.08, x=p.x, y=p.y)
                self.explosions.append((p.x, p.y, 0.0, 52)); self.pickups.remove(p)
        if len(self.pickups) < 14:
            rng = random.Random(int(time.time()) + self.seed + len(self.pickups))
            for _ in range(4):
                ang = rng.uniform(-math.pi, math.pi); dist = rng.uniform(700, 1900)
                self.pickups.append(Pickup(self.x + math.cos(ang) * dist, self.y + math.sin(ang) * dist, rng.choice(["repair", "score", "boost"])))

    def _update_pedestrians(self, dt: float) -> None:
        rng = random.Random(int(time.time() * 3) + self.seed)
        speed = math.hypot(self.vx, self.vy)
        for ped in list(self.pedestrians):
            if not ped.alive:
                ped.respawn_timer -= dt
                if ped.respawn_timer <= 0:
                    ang = rng.uniform(-math.pi, math.pi); dist = rng.uniform(900, 2600)
                    ped.x = self.x + math.cos(ang) * dist; ped.y = self.y + math.sin(ang) * dist
                    ped.vx = rng.uniform(-0.42, 0.42); ped.vy = rng.uniform(-0.42, 0.42); ped.alive = True
                continue
            ped.pulse += dt
            if rng.random() < 0.015:
                ped.vx += rng.uniform(-0.11, 0.11); ped.vy += rng.uniform(-0.11, 0.11)
            ped.vx = clamp(ped.vx, -0.68, 0.68); ped.vy = clamp(ped.vy, -0.68, 0.68)
            ped.x += ped.vx; ped.y += ped.vy
            splat = False
            if (ped.x - self.x) ** 2 + (ped.y - self.y) ** 2 < 35 ** 2 and speed > 4.0:
                splat = True
            else:
                for r in self.rivals:
                    if (ped.x - r.x) ** 2 + (ped.y - r.y) ** 2 < 33 ** 2 and abs(r.speed) > 4.0:
                        splat = True; break
            if splat:
                ped.alive = False; ped.respawn_timer = rng.uniform(3.2, 7.0)
                self.score += 15 + int(min(max(speed, 12.0), 60.0))
                self.splatter_marks.append((ped.x, ped.y, 0.0, 45.0))
                self._burst_fx(ped.x, ped.y, 34.0, 5)
                self.sound.play("hit", 0.58, throttle=0.04, x=ped.x, y=ped.y)
        self.splatter_marks = [(x, y, age + dt, size) for x, y, age, size in self.splatter_marks if age < 6.0][-64:]

    def _update_peers(self) -> None:
        if not self.lan: return
        self.lan.send_state({"x": self.x, "y": self.y, "heading": self.heading, "hp": self.hp, "vehicle": self.vehicle_name})
        for payload in self.lan.drain():
            try:
                pid = str(payload.get("id")); self.peers[pid] = PeerState(pid, float(payload.get("x", 0)), float(payload.get("y", 0)), float(payload.get("heading", 0)), float(payload.get("hp", 0)), str(payload.get("vehicle", "peer")))
            except Exception:
                pass
        stale = time.monotonic() - 4.0
        self.peers = {pid: ps for pid, ps in self.peers.items() if ps.updated >= stale}

    def _color_for_roughness(self, rough: float) -> tuple[float, float, float, float]:
        # Greys and blacks keep the world in the same clean wire-industrial style
        # as the vehicles while the slow red sky supplies the color mood.
        if rough > 0.55:
            return (0.105, 0.105, 0.110, 1.0)
        if rough > 0.38:
            return (0.070, 0.072, 0.078, 1.0)
        return (0.035, 0.037, 0.043, 1.0)

    def _sync_dynamic_environment(self, dt: float) -> None:
        # Slow red day/night cycle.  Terrain stays grey/black; the sky, fog, and
        # lighting carry the red Code Red atmosphere without recoloring every mesh.
        self.world_clock += max(0.0, float(dt))
        phase = self.world_clock * 0.0065 + self.seed * 0.0003
        day = (math.sin(phase) + 1.0) * 0.5
        sky = (0.025 + 0.075 * day, 0.004 + 0.018 * day, 0.009 + 0.017 * day, 1.0)
        fog = (0.030 + 0.055 * day, 0.006 + 0.015 * day, 0.010 + 0.016 * day)
        try:
            self.base.setBackgroundColor(*sky)
            self.fog.setColor(*fog)
            self.sun_light.setColor((0.42 + day * 0.52, 0.12 + day * 0.22, 0.10 + day * 0.14, 1))
            self.ambient_light.setColor((0.18 + day * 0.18, 0.18 + day * 0.14, 0.19 + day * 0.12, 1))
            self.sun_np.setHpr(-38 + math.sin(phase * 0.7) * 30, -42 - day * 32, 0)
        except Exception:
            pass

    def _sync_scene(self) -> None:
        self._sync_dynamic_environment(getattr(self, "scene_dt", 1/60))
        if hasattr(self, "sound"):
            self.sound.set_listener(self.x, self.y, self.heading + self.mouse_look_yaw)
        # Terrain tile pool follows the player. This keeps draw calls bounded while
        # making the world feel much larger than the visible arena.
        step = 180.0
        base_x = math.floor(self.x / step) * step
        base_y = math.floor(self.y / step) * step
        for ix, iy, tile in self.tiles:
            wx = base_x + ix * step; wy = base_y + iy * step
            th = self._terrain_height(wx, wy)
            tile.setPos(wx, wy, th - 1.2)
            sx, sy = self._terrain_slope(wx, wy, 82.0)
            tile.setP(math.degrees(math.atan2(-sx, 1.0)) * 0.45)
            tile.setR(math.degrees(math.atan2(sy, 1.0)) * 0.45)
            rough = self._terrain_roughness(wx, wy)
            tile.setColor(*self._color_for_roughness(rough))

        self.player_np.setPos(self.x, self.y, self.z)
        self.player_np.setH(math.degrees(self.heading))
        sx, sy = self._terrain_slope(self.x, self.y, 42.0)
        self.player_np.setP(clamp(math.degrees(math.atan2(-sx, 1.0)) * 1.15, -18, 18))
        self.player_np.setR(clamp(math.degrees(math.atan2(sy, 1.0)) * 1.15 - self.vy * 0.035, -16, 16))
        player_steer = (1 if ("a" in self.keys or "arrow_left" in self.keys) else 0) + (-1 if ("d" in self.keys or "arrow_right" in self.keys) else 0)
        scene_dt = getattr(self, "scene_dt", 1/60)
        self._update_vehicle_turret_seekers(self.player_np, self.x, self.y, self.heading, self._player_turret_target_points(), scene_dt, True)
        if self.left_flash_timer > 0:
            self.player_np.setPythonTag("left_recoil", max(float(self.player_np.getPythonTag("left_recoil") or 0.0), self.left_flash_timer * 12.0))
        if self.right_flash_timer > 0:
            self.player_np.setPythonTag("right_recoil", max(float(self.player_np.getPythonTag("right_recoil") or 0.0), self.right_flash_timer * 12.0))
        self._animate_vehicle_controls(self.player_np, math.hypot(self.vx, self.vy), player_steer, scene_dt)
        player_part_nodes = self.player_np.getPythonTag("target_part_nodes") or {}
        if isinstance(player_part_nodes, dict):
            for part in self.player_parts:
                node = player_part_nodes.get(part.name)
                if node is not None:
                    if part.destroyed:
                        node.hide()
                    else:
                        node.show(); node.setAlphaScale(clamp(0.24 + part.hp * 0.22, 0.24, 0.82))
        for np, rival in zip(self.rival_nps, self.rivals):
            rz = self._terrain_height(rival.x, rival.y) + self._hover_clearance()
            np.show(); np.setPos(rival.x, rival.y, rz); np.setH(math.degrees(rival.heading)); np.setScale(0.96)
            rsx, rsy = self._terrain_slope(rival.x, rival.y, 40.0)
            np.setP(clamp(math.degrees(math.atan2(-rsx, 1.0)) * 0.9, -14, 14)); np.setR(clamp(math.degrees(math.atan2(rsy, 1.0)) * 0.9, -14, 14))
            # Rival side arms independently track different parts of the player
            # silhouette, giving the whole vehicle-combat layer visible motion.
            px_l = self.x - math.sin(self.heading) * 18.0
            py_l = self.y + math.cos(self.heading) * 18.0
            px_r = self.x + math.sin(self.heading) * 18.0
            py_r = self.y - math.cos(self.heading) * 18.0
            self._update_vehicle_turret_seekers(np, rival.x, rival.y, rival.heading, {"left": (px_l, py_l, 16.0, "player-left"), "right": (px_r, py_r, 16.0, "player-right")}, scene_dt, False)
            self._animate_vehicle_controls(np, abs(rival.speed), clamp(rival.speed / 40.0, -0.45, 0.45), scene_dt)
            part_nodes = np.getPythonTag("target_part_nodes") or {}
            if isinstance(part_nodes, dict):
                for part in rival.parts:
                    node = part_nodes.get(part.name)
                    if node is not None:
                        if part.destroyed:
                            node.hide()
                        else:
                            node.show(); node.setAlphaScale(clamp(0.35 + part.hp * 0.65, 0.35, 1.0))
        for np in self.rival_nps[len(self.rivals):]:
            np.hide()
        for np, p in zip(self.pickup_nps, self.pickups):
            np.show(); np.setPos(p.x, p.y, self._terrain_height(p.x, p.y) + 8 + math.sin(p.pulse * 5) * 2); np.setH((p.pulse * 75) % 360)
            if p.kind == "repair": np.setColor(0.26, 0.90, 0.48, 1)
            elif p.kind == "boost": np.setColor(0.16, 0.58, 1.0, 1)
            else: np.setColor(1.0, 0.82, 0.22, 1)
        for np in self.pickup_nps[len(self.pickups):]:
            np.hide()
        for np, ped in zip(getattr(self, "pedestrian_nps", []), self.pedestrians):
            if ped.alive:
                np.show(); np.setPos(ped.x, ped.y, self._terrain_height(ped.x, ped.y) + 6.5 + math.sin(ped.pulse * 5.0) * 0.7); np.setScale(0.82 + math.sin(ped.pulse * 7.0) * 0.05); np.setColor(0.78, 0.58, 0.42, 1)
            else:
                np.hide()
        for np in getattr(self, "pedestrian_nps", [])[len(self.pedestrians):]:
            np.hide()
        # Splatter marks are tracked for scoring/effects; burst FX is emitted at impact time.
        for np, pr in zip(self.projectile_nps, self.projectiles):
            np.show(); np.setPos(pr.x, pr.y, self._terrain_height(pr.x, pr.y) + 8.0); np.setScale(1.0 + pr.radius * 0.06)
            if pr.owner == "player": np.setColor(1.0, 0.80, 0.24, 1)
            else: np.setColor(1.0, 0.16, 0.12, 1)
        for np in self.projectile_nps[len(self.projectiles):]:
            np.hide()
        for np, ex in zip(self.explosion_nps, self.explosions):
            x, y, age, size = ex; t = clamp(age / 0.75, 0, 1)
            np.show(); np.setPos(x, y, self._terrain_height(x, y) + 12 + size * 0.05); np.setScale(max(0.8, size * 0.025 * (0.4 + t)))
            np.setColor(1.0, 0.42 * (1-t) + 0.18, 0.06, 0.50 * (1-t))
        for np in self.explosion_nps[len(self.explosions):]:
            np.hide()
        for np, flash in zip(self.muzzle_flash_nps, self.muzzle_flashes):
            x, y, age, side = flash
            t = clamp(age / 0.18, 0, 1)
            np.show(); np.setPos(x, y, self._terrain_height(x, y) + 12.5); np.setScale(0.55 + (1.0 - t) * 0.86)
            np.setH(math.degrees(self.heading))
            if side == "left": np.setColor(1.0, 0.82, 0.24, 1.0 - t)
            else: np.setColor(0.30, 0.80, 1.0, 1.0 - t)
        for np in self.muzzle_flash_nps[len(self.muzzle_flashes):]:
            np.hide()

        # Camera: smooth orbit + vertical look. Mouse controls camera only; it
        # does not interrupt steering, boost, weapon locks, or the pause/settings UI.
        speed = math.hypot(self.vx, self.vy)
        self._update_camera_lens()
        if not self.mouse_capture_active and not self.paused:
            self._apply_mouse_capture(True)
        dx, dy = self._read_mouse_delta()
        if self.camera_lock_enabled:
            self.mouse_look_yaw *= max(0.0, 1.0 - 8.0 * scene_dt)
            self.mouse_look_pitch *= max(0.0, 1.0 - 8.0 * scene_dt)
        elif dx or dy:
            self.mouse_look_yaw = angle_wrap(self.mouse_look_yaw + dx * self.mouse_sensitivity)
            self.mouse_look_pitch = clamp(self.mouse_look_pitch - dy * self.mouse_pitch_sensitivity, -1.05, 1.22)
        zoom = clamp(float(getattr(self, "camera_zoom", 1.72)), 0.62, 1.72)
        back = (154 + min(speed * 2.10, 175)) * zoom
        look_ahead = 84 + 20 * zoom
        cam_z = 126 + min(speed * 0.75, 58) + 46 * zoom + self.mouse_look_pitch * 92.0
        orbit_yaw = 0.0 if self.camera_lock_enabled else self.mouse_look_yaw
        target_z_bias = self.mouse_look_pitch * 76.0
        cam_heading = self.heading + orbit_yaw
        cam_x = self.x - math.cos(cam_heading) * back
        cam_y = self.y - math.sin(cam_heading) * back
        self.base.camera.setPos(cam_x, cam_y, cam_z + self.z * 0.34)
        target_z = clamp(self.z + 26 + target_z_bias, self.z - 18, self.z + 150)
        self.base.camera.lookAt(self.x + math.cos(self.heading) * look_ahead, self.y + math.sin(self.heading) * look_ahead, target_z)

        s = self._stat_block(); lan_status = self.lan.status if self.lan else "LAN ghosts off"
        mode = "FULL 16:9" if bool(self.arcade_options.get("full_windowed", False)) else "WINDOWED 16:9"
        self.hud.setText(
            f"{APP_NAME}  •  METAL HUD  •  {self.vehicle_name}\n"
            f"SCORE {self.score}    WAVE {self.wave}    KILLS {self.kills}    RIVALS {len(self.rivals)}    PEERS {len(self.peers)}\n"
            f"SPD {math.hypot(self.vx, self.vy):04.1f}/{s['max_speed']:04.1f}    ARMOR {self.hp:.1f}/{self.max_hp:.1f}    BOOST {self.boost_heat:.0%}    AIR {'YES' if self.airborne else 'NO'}\n"
            f"FOV {self.display_fov:.0f}    ZOOM {self.camera_zoom:.2f}x    {mode}    DAY/NIGHT RED SKY    TERRAIN {self.arcade_options.get('terrain_quality', 'Balanced')}"
        )
        self.metal_status.setText(
            f"AUDIO {getattr(self.sound, 'status', 'audio off')}\n"
            f"TUNE accel {s['accel']:.1f}  grip {s['grip']:.2f}  turn {s['turn_rate']:.2f}  hover {self._hover_clearance():.1f}\n"
            f"Mouse {'LOCKED' if self.mouse_capture_active else 'RELEASED'}  Space target-lock  Esc settings  F fullscreen  {lan_status}"
        )
        locks = ""
        try:
            names = self.player_np.getPythonTag("turret_target_names") or {}
            locks = f" • seekers L:{names.get('left', 'scan')} R:{names.get('right', 'scan')}"
        except Exception:
            pass
        if self.help_visible:
            self.help_text.setText("WASD/Arrows drive • Shift boost • mouse look up/down/orbit • wheel zoom+FOV • Space target lock • LMB/Ctrl left turret • RMB/Q/E right turret • ramps/jumps/collisions • Esc settings • F fullscreen • H/F1 hide help" + locks)
        else:
            self.help_text.setText("H/F1 help • Esc pause/settings • wheel zoom+FOV • Space target lock • F fullscreen" + locks)
        self.pause_text.setText("" if not self.paused else "PAUSED — use mouse settings")
        try:
            if self.paused:
                self.pause_menu_status.setText(f"Zoom {self.camera_zoom:.2f}x  •  FOV {self.display_fov:.0f}  •  {'fullscreen' if bool(self.arcade_options.get('full_windowed', False)) else 'windowed 1080p'}")
        except Exception:
            pass


def run_selftest(settings_path: Path) -> int:
    """Validate launch inputs without opening a renderer window."""
    log_dir = app_dir() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    report = log_dir / "arcade_selftest_latest.txt"
    errors: list[str] = []
    if not settings_path.exists():
        errors.append(f"settings missing: {settings_path}")
        data = {}
    else:
        try:
            data = json.loads(settings_path.read_text(encoding="utf-8"))
        except Exception as exc:
            errors.append(f"settings JSON failed: {exc}")
            data = {}
    vehicles = data.get("vehicles") if isinstance(data.get("vehicles"), dict) else {}
    active = str(data.get("active_vehicle", "Car01"))
    if active not in vehicles:
        errors.append(f"active vehicle not present in settings vehicles: {active}")
    arcade = data.get("arcade") if isinstance(data.get("arcade"), dict) else {}
    for key in ("camera_fov", "camera_zoom", "rival_count", "renderer_preference"):
        if key not in arcade:
            errors.append(f"arcade setting missing: {key}")
    sfx_dir = app_dir() / "assets" / "sfx" / "arcade"
    if not sfx_dir.exists():
        errors.append(f"arcade SFX folder missing: {sfx_dir}")
    vehicle_wire = app_dir() / "assets" / "vehicles" / "concept_vehicle_baked_wire.json"
    if not vehicle_wire.exists():
        errors.append(f"vehicle wire data missing: {vehicle_wire}")
    text = [
        f"{APP_NAME} {APP_VERSION} selftest",
        f"settings: {settings_path}",
        f"active_vehicle: {active}",
        f"renderer_preference: {arcade.get('renderer_preference', 'auto')}",
        f"errors: {len(errors)}",
    ]
    text.extend(f"- {err}" for err in errors)
    report.write_text("\n".join(text) + "\n", encoding="utf-8")
    print("\n".join(text))
    print(f"report: {report}")
    return 0 if not errors else 1


def _write_crash_log(exc_type, exc, tb) -> None:
    try:
        import traceback
        log_dir = app_dir() / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        path = log_dir / "arcade_crash.log"
        text = "".join(traceback.format_exception(exc_type, exc, tb))
        path.write_text(f"{APP_NAME} {APP_VERSION} crash\n{time.strftime('%Y-%m-%d %H:%M:%S')}\n\n{text}", encoding="utf-8")
    except Exception:
        pass

def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=APP_NAME)
    parser.add_argument("--settings", default=str(app_dir() / "runtime" / "arcade_settings.json"), help="Tuner-written arcade settings JSON.")
    parser.add_argument("--lan", action="store_true", help="Enable lightweight UDP LAN ghost clients.")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="UDP port for LAN ghost clients.")
    parser.add_argument("--renderer", choices=("panda", "auto", "tk"), default="panda", help="Preferred renderer. Panda is default; auto may use Tk fallback only if Panda3D is unavailable.")
    parser.add_argument("--selftest", action="store_true", help="Validate settings/assets and exit without opening a renderer.")
    if any(arg in {"-h", "--help"} for arg in argv):
        parser.print_help()
        try:
            sys.stdout.flush(); sys.stderr.flush()
        finally:
            os._exit(0)
    return parser.parse_args(argv)


def _can_use_panda3d() -> tuple[bool, str]:
    try:
        import panda3d  # noqa: F401
        import direct  # noqa: F401
        return True, "Panda3D available"
    except Exception as exc:
        return False, str(exc)


def main(argv: list[str] | None = None) -> int:
    sys.excepthook = _write_crash_log
    ns = parse_args(sys.argv[1:] if argv is None else argv)
    settings = Path(ns.settings)
    if bool(getattr(ns, "selftest", False)):
        code = run_selftest(settings)
        try:
            sys.stdout.flush(); sys.stderr.flush()
        finally:
            os._exit(int(code))
    renderer = str(ns.renderer)
    if renderer in ("auto", "panda"):
        ok, reason = _can_use_panda3d()
        if ok:
            app = PandaArcadeApp(settings, lan=bool(ns.lan), port=int(ns.port))
            app.run()
            return 0
        if renderer == "panda":
            print(f"Panda3D renderer unavailable: {reason}", file=sys.stderr)
            return 2
        print(f"Panda3D renderer unavailable; falling back to Tkinter: {reason}", file=sys.stderr)
    app = ArcadeApp(settings, lan=bool(ns.lan), port=int(ns.port))
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
