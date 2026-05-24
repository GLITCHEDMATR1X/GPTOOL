"""Same-window Vector Wars adapter for HoloVerse.

This is the presentation-safe Vector Wars route used by artifact slot 5.  The
original source is pygame, so it cannot own the HoloVerse Panda3D window
directly; this adapter recreates the Vector Wars dogfight loop in Panda3D with
wire city streaming, enemy ships, target cycling, missiles, mode cycling, cloud
banks, space altitude, and tornado hazards while preserving the original source
file as the standalone fallback.

ESC/0 are reserved for the HoloVerse host return flow.
"""
from __future__ import annotations

import json
import math
import os
import random
import time
import traceback
from dataclasses import dataclass
from pathlib import Path

from direct.gui.OnscreenText import OnscreenText
from panda3d.core import ClockObject, KeyboardButton, LineSegs, MouseButton, NodePath, TextNode, TransparencyAttrib, Vec3, Vec4, WindowProperties

MODE_TITLE = "Vector Wars"
MODE_ID = "vector_wars"
MODE_STATUS = "VECTOR WARS // SAME-WINDOW DOGFIGHT // ESC / 0 RETURN TO HOLOVERSE // H SHOWS LEGACY UI"


@dataclass
class _Projectile:
    node: NodePath
    pos: Vec3
    vel: Vec3
    age: float
    owner: str
    damage: float


@dataclass
class _Enemy:
    node: NodePath
    pos: Vec3
    vel: Vec3
    yaw: float
    hp: float
    seed: int
    fire_timer: float


@dataclass
class _Hazard:
    node: NodePath
    pos: Vec3
    radius: float
    spin: float
    drift: Vec3


@dataclass
class _VectorGate:
    node: NodePath
    pos: Vec3
    radius: float
    spin: float
    cooldown: float = 0.0


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _safe_dt(dt: float) -> float:
    try:
        return _clamp(float(dt), 0.0, 0.06)
    except Exception:
        return 0.016


def _hpr_forward(yaw_deg: float, pitch_deg: float = 0.0) -> Vec3:
    yaw = math.radians(float(yaw_deg))
    pitch = math.radians(float(pitch_deg))
    cp = math.cos(pitch)
    return Vec3(math.sin(yaw) * cp, math.cos(yaw) * cp, math.sin(pitch))


def _line_node(name: str, points: list[Vec3], color: Vec4, thickness: float = 1.25, closed: bool = False) -> NodePath:
    seg = LineSegs(name)
    seg.setThickness(float(thickness))
    seg.setColor(color)
    if not points:
        return NodePath(name)
    seg.moveTo(points[0])
    for p in points[1:]:
        seg.drawTo(p)
    if closed and len(points) > 2:
        seg.drawTo(points[0])
    return NodePath(seg.create())


def _wire_box(name: str, size: Vec3, color: Vec4, thickness: float = 1.0) -> NodePath:
    sx, sy, sz = float(size.x), float(size.y), float(size.z)
    pts = [
        Vec3(-sx, -sy, -sz), Vec3(sx, -sy, -sz), Vec3(sx, sy, -sz), Vec3(-sx, sy, -sz),
        Vec3(-sx, -sy, sz), Vec3(sx, -sy, sz), Vec3(sx, sy, sz), Vec3(-sx, sy, sz),
    ]
    edges = [(0,1),(1,2),(2,3),(3,0),(4,5),(5,6),(6,7),(7,4),(0,4),(1,5),(2,6),(3,7)]
    seg = LineSegs(name)
    seg.setThickness(float(thickness))
    seg.setColor(color)
    for a, b in edges:
        seg.moveTo(pts[a]); seg.drawTo(pts[b])
    return NodePath(seg.create())


def _circle_node(name: str, radius: float, color: Vec4, thickness: float = 1.25, segments: int = 36) -> NodePath:
    pts = []
    for i in range(max(8, int(segments))):
        a = math.tau * i / max(8, int(segments))
        pts.append(Vec3(math.sin(a) * radius, math.cos(a) * radius, 0))
    return _line_node(name, pts, color, thickness, True)


def _ring_stack(name: str, radius: float, color: Vec4, thickness: float = 1.25) -> NodePath:
    root = NodePath(name)
    xy = _circle_node(name + "_xy", radius, color, thickness, 42)
    yz = _circle_node(name + "_yz", radius * 0.72, color, max(0.8, thickness * 0.72), 32)
    xz = _circle_node(name + "_xz", radius * 0.72, color, max(0.8, thickness * 0.72), 32)
    xy.reparentTo(root)
    yz.reparentTo(root); yz.setP(90)
    xz.reparentTo(root); xz.setR(90)
    return root


def _ship_wire(name: str, color: Vec4, scale: float = 1.0) -> NodePath:
    s = float(scale)
    pts = [
        Vec3(0, 4.8*s, 0), Vec3(-2.2*s, -1.7*s, -0.25*s), Vec3(0, -0.8*s, 0.85*s),
        Vec3(2.2*s, -1.7*s, -0.25*s), Vec3(0, 4.8*s, 0), Vec3(0, -2.8*s, -0.45*s),
        Vec3(-2.2*s, -1.7*s, -0.25*s), Vec3(0, -2.8*s, -0.45*s), Vec3(2.2*s, -1.7*s, -0.25*s),
    ]
    root = NodePath(name)
    body = _line_node(name + "_body", pts, color, 1.55, False)
    body.reparentTo(root)
    left_wing = _line_node(name + "_left_wing", [Vec3(-0.65*s, 0.6*s, 0), Vec3(-4.5*s, -1.9*s, -0.2*s), Vec3(-1.1*s, -1.1*s, 0.2*s)], color, 1.15, True)
    right_wing = _line_node(name + "_right_wing", [Vec3(0.65*s, 0.6*s, 0), Vec3(4.5*s, -1.9*s, -0.2*s), Vec3(1.1*s, -1.1*s, 0.2*s)], color, 1.15, True)
    left_wing.reparentTo(root); right_wing.reparentTo(root)
    return root


class HoloVerseNativeMode:
    """Vector Wars mounted in the live HoloVerse ShowBase."""

    def __init__(self, host, mode=None, entry_path=None, label=MODE_TITLE):
        self.host = host
        self.mode = mode or {}
        self.entry_path = Path(entry_path) if entry_path else Path(__file__).resolve().parent / "main.py"
        self.folder = self.entry_path.parent
        self.label = str(label or MODE_TITLE)
        self.clock = ClockObject.getGlobalClock()
        self._entered = False
        self.dimension_ui_visible = False
        self._dimension_ui_node_names = ('hud_root',)
        self._owned: list[NodePath] = []
        self._single_frame: set[str] = set()
        self._saved_camera_parent = None
        self._saved_camera_transform = None
        self._saved_bg = None
        self._rng = random.Random(75051)
        self._elapsed = 0.0

        self.player_pos = Vec3(0, 0, 48)
        self.player_vel = Vec3(0, 68, 0)
        self.player_yaw = 0.0
        self.player_pitch = -3.0
        self.player_roll = 0.0
        self.health = 100.0
        self.score = 0
        self.combat_mode = "AIR"
        self.weapon_mode = "MACHINE GUN"
        self.ship_variant = "INTERCEPTOR"
        self.keys: dict[str, bool] = {}
        self.fire_held = False
        self._mouse1_latched_by_event = False
        self.missile_held = False
        self.fire_cooldown = 0.0
        self.missile_cooldown = 0.0
        self.target_index = 0
        self.mouse_sensitivity = 0.105
        self.camera_distance = 82.0
        self.camera_height = 24.0
        self._last_mouse_sample = (0, 0)
        self._last_control_vector = Vec3(0, 0, 0)
        self.objective_kills = 0
        self.objective_goal = 15

        self.enemies: list[_Enemy] = []
        self.projectiles: list[_Projectile] = []
        self.fx_nodes: list[tuple[NodePath, float]] = []
        self.city_nodes: list[NodePath] = []
        self.star_nodes: list[NodePath] = []
        self.cloud_nodes: list[NodePath] = []
        self.hazards: list[_Hazard] = []
        self.vector_gates: list[_VectorGate] = []
        self.trail_nodes: list[NodePath] = []
        self.trail_history: list[tuple[Vec3, float, float]] = []
        self.target_lock_node: NodePath | None = None
        self.target_lead_node: NodePath | None = None
        self.camera_pos: Vec3 | None = None
        self._boost_flash_timer = 0.0
        self._last_damage_health = self.health

    # ------------------------------------------------------------------
    # Source/config contract
    # ------------------------------------------------------------------
    def _read_source_contract(self) -> dict:
        payload = {"source_entry": self.entry_path.name, "source_kind": "pygame", "lines": 0, "title": MODE_TITLE}
        try:
            text = self.entry_path.read_text(encoding="utf-8", errors="ignore")
            payload["lines"] = text.count("\n") + 1
            for marker in ("Neon Dogfight", "Infinite Wireframe City", "Space + Weather", "tornados", "Player ship variants", "homing missile"):
                if marker.lower() in text.lower():
                    payload[marker.replace(" ", "_").lower()] = True
        except Exception:
            pass
        try:
            profile = json.loads((self.folder / "audio_profile.json").read_text(encoding="utf-8"))
            if isinstance(profile, dict):
                payload["audio_profile"] = profile
        except Exception:
            pass
        return payload

    # ------------------------------------------------------------------
    # Host resources / scene build
    # ------------------------------------------------------------------
    def _host_resources(self):
        self.render = self.host.render
        self.aspect2d = self.host.aspect2d
        self.camera = self.host.camera
        self.camLens = self.host.camLens
        self.loader = self.host.loader
        self.win = getattr(self.host, "win", None)
        self.taskMgr = getattr(self.host, "taskMgr", None)
        self.accept = getattr(self.host, "accept", lambda *a, **k: None)
        self.ignore = getattr(self.host, "ignore", lambda *a, **k: None)
        self.disableMouse = getattr(self.host, "disableMouse", lambda *a, **k: None)
        self.setBackgroundColor = getattr(self.host, "setBackgroundColor", lambda *a, **k: None)

        self._saved_camera_parent = self.camera.getParent()
        self._saved_camera_transform = self.camera.getTransform()
        try:
            self._saved_bg = self.win.getClearColor() if self.win is not None else None
        except Exception:
            self._saved_bg = None

        self.root = self.render.attachNewNode("vector_wars_native_root")
        self.world_root = self.root.attachNewNode("world")
        self.fx_root = self.root.attachNewNode("fx")
        self.hud_root = self.aspect2d.attachNewNode("vector_wars_hud")
        self._owned.extend([self.root, self.world_root, self.fx_root, self.hud_root])

        try:
            self.disableMouse()
            self.camLens.setFov(84)
            self.camLens.setNearFar(0.08, 5000.0)
            self.setBackgroundColor(0, 0, 0)
            self.root.setTransparency(TransparencyAttrib.MAlpha)
            if self.win is not None and hasattr(self.win, "requestProperties"):
                props = WindowProperties()
                props.setCursorHidden(True)
                self.win.requestProperties(props)
                try:
                    cx, cy = self._window_center()
                    if cx > 0 and cy > 0 and hasattr(self.win, "movePointer"):
                        self.win.movePointer(0, cx, cy)
                except Exception:
                    pass
        except Exception:
            pass

    def _build_grid(self):
        grid = LineSegs("vector_wars_ground_grid")
        grid.setThickness(1.0)
        grid.setColor(Vec4(0.05, 1.0, 0.28, 0.36))
        span = 820
        step = 40
        for i in range(-span, span + 1, step):
            grid.moveTo(Vec3(i, -span, 0)); grid.drawTo(Vec3(i, span, 0))
            grid.moveTo(Vec3(-span, i, 0)); grid.drawTo(Vec3(span, i, 0))
        node = NodePath(grid.create())
        node.reparentTo(self.world_root)
        self._owned.append(node)
        self.grid = node

    def _build_stars(self):
        for i in range(90):
            ang = self._rng.uniform(0, math.tau)
            dist = self._rng.uniform(460, 1700)
            z = self._rng.uniform(260, 980)
            p = Vec3(math.sin(ang) * dist, math.cos(ang) * dist, z)
            star = _line_node(f"star_{i}", [Vec3(-0.8, 0, 0), Vec3(0.8, 0, 0), Vec3(0, -0.8, 0), Vec3(0, 0.8, 0)], Vec4(0.65, 0.9, 1.0, 0.6), 0.9)
            star.reparentTo(self.world_root)
            star.setPos(p)
            self.star_nodes.append(star)

    def _build_clouds(self):
        # Low drifting cloud banks from the original Space + Weather source.
        for i in range(34):
            ang = self._rng.uniform(0, math.tau)
            dist = self._rng.uniform(180, 1250)
            z = self._rng.uniform(70, 185)
            radius = self._rng.uniform(9, 28)
            points = []
            for k in range(16):
                a = math.tau * k / 16.0
                wobble = 0.65 + 0.35 * math.sin(k * 1.7 + i)
                points.append(Vec3(math.sin(a) * radius * wobble, math.cos(a) * radius * 0.36 * wobble, 0))
            node = _line_node(f"vw_cloud_bank_{i}", points, Vec4(0.35, 0.72, 1.0, 0.18), 1.1, True)
            node.reparentTo(self.world_root)
            node.setPos(math.sin(ang) * dist, math.cos(ang) * dist, z)
            self.cloud_nodes.append(node)

    def _build_tornadoes(self):
        # Wire helix hazards: visible, moving, and capable of pushing/damaging the player.
        for i in range(4):
            seg = LineSegs(f"vw_tornado_{i}")
            seg.setThickness(1.35)
            seg.setColor(Vec4(0.75, 0.15, 1.0, 0.46))
            steps = 74
            height = 90.0 + i * 11.0
            for k in range(steps):
                a = k * 0.48
                z = height * k / max(1, steps - 1)
                r = 6.0 + 0.14 * z + math.sin(k * 0.37 + i) * 2.0
                p = Vec3(math.sin(a) * r, math.cos(a) * r, z)
                if k == 0:
                    seg.moveTo(p)
                else:
                    seg.drawTo(p)
            node = NodePath(seg.create())
            node.setTransparency(TransparencyAttrib.MAlpha)
            node.reparentTo(self.world_root)
            pos = Vec3(self._rng.uniform(-620, 620), self._rng.uniform(-620, 620), 0)
            node.setPos(pos)
            drift = Vec3(self._rng.uniform(-8, 8), self._rng.uniform(-8, 8), 0)
            self.hazards.append(_Hazard(node=node, pos=pos, radius=60.0, spin=self._rng.uniform(-32, 32), drift=drift))

    def _build_city(self):
        colors = [Vec4(0.05, 0.9, 1.0, 0.42), Vec4(0.8, 0.1, 1.0, 0.35), Vec4(0.1, 1.0, 0.35, 0.34)]
        for ix in range(-5, 6):
            for iy in range(-5, 7):
                if self._rng.random() < 0.38:
                    continue
                h = self._rng.uniform(20, 138)
                sx = self._rng.uniform(5, 15)
                sy = self._rng.uniform(5, 18)
                node = _wire_box("vw_tower", Vec3(sx, sy, h * 0.5), self._rng.choice(colors), 0.8)
                node.reparentTo(self.world_root)
                node.setPos(ix * 95 + self._rng.uniform(-16, 16), iy * 95 + self._rng.uniform(-16, 16), h * 0.5)
                self.city_nodes.append(node)

    def _build_player_ship(self):
        self.player_ship = _ship_wire("vector_wars_player_ship", Vec4(0.2, 1.0, 0.9, 0.95), 1.0)
        self.player_ship.reparentTo(self.world_root)
        self._owned.append(self.player_ship)

    def _build_target_guides(self):
        self.target_lock_node = _ring_stack("vw_target_lock", 22.0, Vec4(1.0, 0.34, 0.1, 0.86), 1.7)
        self.target_lock_node.reparentTo(self.fx_root)
        self.target_lock_node.hide()
        self.target_lead_node = _ring_stack("vw_target_lead", 9.0, Vec4(1.0, 0.92, 0.18, 0.74), 1.25)
        self.target_lead_node.reparentTo(self.fx_root)
        self.target_lead_node.hide()
        self._owned.extend([self.target_lock_node, self.target_lead_node])

    def _build_boost_trail(self):
        for i in range(18):
            radius = 2.2 + i * 0.34
            alpha = max(0.08, 0.52 - i * 0.022)
            node = _circle_node(f"vw_boost_trail_{i}", radius, Vec4(0.12, 0.95, 1.0, alpha), 1.05, 24)
            node.reparentTo(self.fx_root)
            node.hide()
            self.trail_nodes.append(node)

    def _gate_position(self, index: int) -> Vec3:
        forward = _hpr_forward(self.player_yaw + index * 19.0, _clamp(self.player_pitch * 0.25, -10.0, 10.0))
        side = Vec3(forward.y, -forward.x, 0)
        if side.lengthSquared() > 0.01:
            side.normalize()
        distance = 230.0 + (index % 3) * 145.0
        offset = side * ((index - 2.5) * 75.0)
        lift = 8.0 + (index % 2) * 34.0
        return self.player_pos + forward * distance + offset + Vec3(0, 0, lift)

    def _build_vector_gates(self):
        for i in range(6):
            node = _ring_stack(f"vw_speed_gate_{i}", 30.0 + (i % 2) * 5.0, Vec4(0.1, 1.0, 0.55, 0.64), 1.7)
            node.reparentTo(self.world_root)
            pos = self._gate_position(i)
            node.setPos(pos)
            self.vector_gates.append(_VectorGate(node=node, pos=Vec3(pos), radius=37.0, spin=self._rng.uniform(-48.0, 48.0)))

    def _spawn_enemy(self, i: int):
        ang = self._rng.uniform(0, math.tau)
        dist = self._rng.uniform(180, 520)
        z = self._rng.uniform(38, 180)
        pos = self.player_pos + Vec3(math.sin(ang) * dist, math.cos(ang) * dist, z - self.player_pos.z)
        variant = i % 4
        color = [
            Vec4(1.0, 0.22, 0.18, 0.9),
            Vec4(1.0, 0.55, 0.12, 0.88),
            Vec4(0.92, 0.14, 1.0, 0.86),
            Vec4(1.0, 0.08, 0.08, 0.94),
        ][variant]
        scale = [0.92, 1.05, 1.18, 1.34][variant]
        node = _ship_wire(f"vector_wars_enemy_{i}", color, scale)
        node.reparentTo(self.world_root)
        if variant == 3:
            crown = _wire_box(f"vector_wars_enemy_elite_{i}", Vec3(1.8, 1.0, 1.0), Vec4(1.0, 0.05, 0.05, 0.84), 1.15)
            crown.reparentTo(node)
            crown.setPos(0, -1.5 * scale, 1.25 * scale)
        seed = self._rng.randint(0, 1_000_000)
        hp = [45.0, 58.0, 70.0, 105.0][variant]
        enemy = _Enemy(node=node, pos=pos, vel=Vec3(0, 0, 0), yaw=self._rng.uniform(0, 360), hp=hp, seed=seed, fire_timer=self._rng.uniform(0.4, 2.2))
        self.enemies.append(enemy)

    def _build_hud(self):
        self.hud = OnscreenText(
            text="VECTOR WARS",
            parent=self.hud_root,
            pos=(-1.30, 0.88),
            align=TextNode.ALeft,
            scale=0.045,
            fg=(0.55, 1.0, 0.9, 0.92),
            shadow=(0, 0, 0, 0.75),
        )
        self.help = OnscreenText(
            text="Mouse/WASD steer  Q/E roll  Shift boost  Space brake  LMB guns  RMB missile  T target  TAB mode  R weapon  V ship  ESC/0 return",
            parent=self.hud_root,
            pos=(-1.30, -0.92),
            align=TextNode.ALeft,
            scale=0.034,
            fg=(0.75, 0.95, 1.0, 0.82),
            shadow=(0, 0, 0, 0.72),
        )
        self.reticle = OnscreenText(text="+", parent=self.hud_root, pos=(0, 0), align=TextNode.ACenter, scale=0.07, fg=(0.2, 1, 0.85, 0.9), shadow=(0,0,0,0.6))
        self._owned.extend([self.hud, self.help, self.reticle])

    def _build_scene(self):
        self.contract = self._read_source_contract()
        self._build_grid()
        self._build_stars()
        self._build_clouds()
        self._build_tornadoes()
        self._build_city()
        self._build_player_ship()
        self._build_target_guides()
        self._build_boost_trail()
        self._build_vector_gates()
        for i in range(9):
            self._spawn_enemy(i)
        self._build_hud()

    # ------------------------------------------------------------------
    # Gameplay
    # ------------------------------------------------------------------
    def _button_down(self, *buttons) -> bool:
        watcher = getattr(self.host, "mouseWatcherNode", None)
        if watcher is None:
            return False
        for button in buttons:
            try:
                if watcher.isButtonDown(button):
                    return True
            except Exception:
                try:
                    if watcher.is_button_down(button):
                        return True
                except Exception:
                    pass
        return False

    def _keyboard_button(self, name: str):
        name = str(name or "").lower()
        try:
            if len(name) == 1:
                return KeyboardButton.asciiKey(name)
            if name in {"shift", "lshift", "rshift"}:
                return KeyboardButton.shift()
            if name in {"control", "ctrl", "lcontrol", "rcontrol"}:
                return KeyboardButton.control()
            if name == "space":
                return KeyboardButton.space()
            if name == "arrow_left":
                return KeyboardButton.left()
            if name == "arrow_right":
                return KeyboardButton.right()
            if name == "arrow_up":
                return KeyboardButton.up()
            if name == "arrow_down":
                return KeyboardButton.down()
        except Exception:
            return None
        return None

    def _key_down_direct(self, *names: str) -> bool:
        for name in names:
            button = self._keyboard_button(name)
            if button is not None and self._button_down(button):
                return True
        return False

    def _window_center(self) -> tuple[int, int]:
        win = getattr(self.host, "win", None)
        if win is None:
            return (0, 0)
        try:
            props = win.getProperties()
            return (int(props.getXSize() // 2), int(props.getYSize() // 2))
        except Exception:
            pass
        try:
            return (int(win.getXSize() // 2), int(win.getYSize() // 2))
        except Exception:
            return (0, 0)

    def _sample_mouse_delta(self) -> tuple[float, float]:
        win = getattr(self.host, "win", None)
        if win is None or not hasattr(win, "getPointer"):
            return (0.0, 0.0)
        try:
            cx, cy = self._window_center()
            if cx <= 0 or cy <= 0:
                return (0.0, 0.0)
            pointer = win.getPointer(0)
            dx = float(pointer.getX() - cx)
            dy = float(pointer.getY() - cy)
            if abs(dx) > 0.0 or abs(dy) > 0.0:
                try:
                    win.movePointer(0, cx, cy)
                except Exception:
                    pass
            self._last_mouse_sample = (int(dx), int(dy))
            return (dx, dy)
        except Exception:
            return (0.0, 0.0)

    def _sync_host_keys(self):
        host_keys = getattr(self.host, "keys", {}) or {}
        aliases = {
            "a": ("a", "arrow_left"),
            "d": ("d", "arrow_right"),
            "w": ("w", "arrow_up"),
            "s": ("s", "arrow_down"),
            "q": ("q",),
            "e": ("e",),
            "shift": ("shift", "lshift", "rshift"),
            "space": ("space", "control"),
        }
        for key, names in aliases.items():
            held_by_host = any(bool(host_keys.get(name, False)) for name in names)
            held_direct = self._key_down_direct(*names)
            self.keys[key] = bool(held_by_host or held_direct or key in self._single_frame)
        # Direct mouse polling makes the same-window adapter feel responsive even
        # when the host only receives the initial click event.
        try:
            if self._button_down(MouseButton.one()):
                self.fire_held = True
            elif not any(bool(host_keys.get(k, False)) for k in ("mouse1", "fire")):
                self.fire_held = bool(getattr(self, "fire_held", False)) and bool(getattr(self, "_mouse1_latched_by_event", False))
            self.missile_held = self._button_down(MouseButton.three())
        except Exception:
            self.missile_held = False

    def _current_target(self):
        if not self.enemies:
            return None
        try:
            self.target_index = int(self.target_index) % len(self.enemies)
        except Exception:
            self.target_index = 0
        return self.enemies[self.target_index]

    def _cycle_target(self):
        if self.enemies:
            self.target_index = (int(self.target_index) + 1) % len(self.enemies)

    def _fire_player(self, *, missile: bool = False):
        forward = _hpr_forward(self.player_yaw, self.player_pitch)
        target = self._current_target()
        if missile and target is not None:
            to_target = target.pos - self.player_pos
            if to_target.lengthSquared() > 1e-4:
                forward = (forward * 0.58 + to_target.normalized() * 0.42)
                if forward.lengthSquared() > 1e-4:
                    forward.normalize()
        base_pos = self.player_pos + forward * 10.0 + Vec3(0, 0, 1.0)
        if missile:
            speed = 430.0
            damage = 54.0 if self.weapon_mode == "MISSILE BURST" else 42.0
            color = Vec4(1.0, 0.34, 0.08, 0.98)
            shape = [Vec3(0, -3.6, 0), Vec3(0, 10.5, 0), Vec3(-1.2, 2.0, 0), Vec3(1.2, 2.0, 0)]
            name = "vw_player_missile"
            owner = "player_missile"
        else:
            speed = 560.0 if self.weapon_mode == "MACHINE GUN" else 420.0
            damage = 18.0 if self.weapon_mode == "MACHINE GUN" else 30.0
            color = Vec4(0.15, 1.0, 0.72, 0.98) if self.weapon_mode == "MACHINE GUN" else Vec4(1.0, 0.58, 0.08, 0.98)
            shape = [Vec3(0, -2.8, 0), Vec3(0, 7.2, 0)]
            name = "vw_player_shot"
            owner = "player"
        node = _line_node(name, shape, color, 2.35 if missile else 2.0)
        node.reparentTo(self.fx_root)
        node.setPos(base_pos)
        node.setHpr(self.player_yaw, self.player_pitch, 0)
        self.projectiles.append(_Projectile(node=node, pos=Vec3(base_pos), vel=forward * speed + self.player_vel * 0.18, age=0.0, owner=owner, damage=damage))

    def _fire_enemy(self, enemy: _Enemy):
        to_player = self.player_pos - enemy.pos
        if to_player.lengthSquared() <= 1e-4:
            return
        forward = to_player.normalized()
        node = _line_node("vw_enemy_shot", [Vec3(0, -2.0, 0), Vec3(0, 5.5, 0)], Vec4(1.0, 0.18, 0.08, 0.84), 1.65)
        node.reparentTo(self.fx_root)
        node.setPos(enemy.pos + forward * 6.5)
        yaw = math.degrees(math.atan2(forward.x, forward.y))
        pitch = math.degrees(math.atan2(forward.z, max(0.001, math.hypot(forward.x, forward.y))))
        node.setHpr(yaw, pitch, 0)
        self.projectiles.append(_Projectile(node=node, pos=Vec3(enemy.pos + forward * 6.5), vel=forward * 300.0, age=0.0, owner="enemy", damage=7.0))

    def _spawn_hit_fx(self, pos: Vec3, color: Vec4):
        ring = []
        radius = 10.0
        for i in range(18):
            a = math.tau * i / 18.0
            ring.append(Vec3(math.sin(a) * radius, math.cos(a) * radius, 0))
        node = _line_node("vw_hit_ring", ring, color, 1.6, True)
        node.reparentTo(self.fx_root)
        node.setPos(pos)
        self.fx_nodes.append((node, 0.55))

    def _cycle_mode(self):
        order = ["GROUND", "AIR", "OCEAN"]
        self.combat_mode = order[(order.index(self.combat_mode) + 1) % len(order)] if self.combat_mode in order else "AIR"

    def _cycle_weapon(self):
        self.weapon_mode = "MISSILE BURST" if self.weapon_mode == "MACHINE GUN" else "MACHINE GUN"

    def _cycle_ship(self):
        variants = ["INTERCEPTOR", "SPEAR", "HAULER", "UFO"]
        self.ship_variant = variants[(variants.index(self.ship_variant) + 1) % len(variants)] if self.ship_variant in variants else "INTERCEPTOR"

    def _update_player(self, dt: float):
        yaw_rate = 118.0
        pitch_rate = 74.0
        roll_rate = 112.0
        mouse_dx, mouse_dy = self._sample_mouse_delta()
        if abs(mouse_dx) > 0.01:
            self.player_yaw += mouse_dx * self.mouse_sensitivity
        if abs(mouse_dy) > 0.01:
            self.player_pitch -= mouse_dy * self.mouse_sensitivity

        # Left/right are now intuitive: A/Left turns left, D/Right turns right.
        if self.keys.get("a"):
            self.player_yaw -= yaw_rate * dt
            self.player_roll += roll_rate * 0.62 * dt
        if self.keys.get("d"):
            self.player_yaw += yaw_rate * dt
            self.player_roll -= roll_rate * 0.62 * dt
        if self.keys.get("w"):
            self.player_pitch += pitch_rate * dt
        if self.keys.get("s"):
            self.player_pitch -= pitch_rate * dt
        if self.keys.get("q"):
            self.player_roll += roll_rate * dt
        if self.keys.get("e"):
            self.player_roll -= roll_rate * dt
        self.player_pitch = _clamp(self.player_pitch, -58, 48)
        self.player_yaw = (self.player_yaw + 360.0) % 360.0
        self.player_roll = _clamp(self.player_roll, -38.0, 38.0)
        self.player_roll *= max(0.0, 1.0 - dt * 2.25)

        forward = _hpr_forward(self.player_yaw, self.player_pitch)
        cruise_speed = 118.0
        if self.keys.get("shift"):
            cruise_speed = 245.0
        if self.keys.get("space"):
            cruise_speed = 32.0
        # Flight assist reduces the old uncontrollable drift by aligning velocity
        # toward the ship/camera heading while still preserving dogfight momentum.
        desired_vel = forward * cruise_speed
        assist = 3.3 if not self.keys.get("shift") else 2.45
        if self.keys.get("space"):
            assist = 5.5
        blend = _clamp(dt * assist, 0.0, 1.0)
        self.player_vel = self.player_vel * (1.0 - blend) + desired_vel * blend
        self.player_vel += forward * (54.0 if self.keys.get("shift") else 18.0) * dt
        if self.keys.get("space"):
            self.player_vel *= max(0.0, 1.0 - dt * 2.4)
        max_speed = 270.0 if not self.keys.get("shift") else 420.0
        if self.player_vel.length() > max_speed:
            self.player_vel.normalize(); self.player_vel *= max_speed
        self.player_pos += self.player_vel * dt
        self.player_pos.z = _clamp(self.player_pos.z, 16.0, 620.0)
        if abs(self.player_pos.x) > 1600:
            self.player_vel.x *= -0.35
            self.player_pos.x = _clamp(self.player_pos.x, -1600, 1600)
        if abs(self.player_pos.y) > 1600:
            self.player_vel.y *= -0.35
            self.player_pos.y = _clamp(self.player_pos.y, -1600, 1600)

        self._last_control_vector = Vec3(forward)
        self.player_ship.setPos(self.player_pos)
        self.player_ship.setHpr(self.player_yaw, self.player_pitch, self.player_roll)

    def _update_city_stream(self):
        # Keep a local wire city around the player without creating/destroying nodes.
        base_x = round(self.player_pos.x / 95.0) * 95.0
        base_y = round(self.player_pos.y / 95.0) * 95.0
        for idx, node in enumerate(self.city_nodes):
            try:
                xslot = (idx % 11) - 5
                yslot = ((idx // 11) % 12) - 5
                node.setX(base_x + xslot * 95 + math.sin(idx * 12.989) * 13.0)
                node.setY(base_y + yslot * 95 + math.cos(idx * 7.31) * 13.0)
            except Exception:
                pass
        try:
            self.grid.setPos(base_x, base_y, 0)
        except Exception:
            pass

    def _update_enemies(self, dt: float):
        for enemy in list(self.enemies):
            to_player = self.player_pos - enemy.pos
            d = max(to_player.length(), 1.0)
            desired = to_player.normalized() * (95.0 if d > 155 else -35.0)
            swirl = Vec3(-to_player.y, to_player.x, 0)
            if swirl.lengthSquared() > 0.1:
                swirl.normalize(); desired += swirl * (36.0 * math.sin(self._elapsed * 0.7 + enemy.seed))
            enemy.vel = enemy.vel * 0.94 + desired * 0.06
            enemy.pos += enemy.vel * dt
            enemy.yaw = math.degrees(math.atan2(to_player.x, to_player.y))
            enemy.node.setPos(enemy.pos)
            enemy.node.setHpr(enemy.yaw, 0, math.sin(self._elapsed + enemy.seed) * 12.0)
            enemy.fire_timer -= dt
            if enemy.fire_timer <= 0.0 and d < 520:
                self._fire_enemy(enemy)
                enemy.fire_timer = self._rng.uniform(1.0, 2.4)
            if enemy.hp <= 0:
                self.score += 100
                self.objective_kills += 1
                self._spawn_hit_fx(enemy.pos, Vec4(1.0, 0.35, 0.08, 0.85))
                try: enemy.node.removeNode()
                except Exception: pass
                self.enemies.remove(enemy)
        while len(self.enemies) < 9:
            self._spawn_enemy(len(self.enemies) + self.score)

    def _update_projectiles(self, dt: float):
        for shot in list(self.projectiles):
            shot.age += dt
            shot.pos += shot.vel * dt
            shot.node.setPos(shot.pos)
            remove = shot.age > 2.8
            if not remove and shot.owner in {"player", "player_missile"}:
                hit_radius = 34.0 if shot.owner == "player_missile" else 22.0
                for enemy in list(self.enemies):
                    if (enemy.pos - shot.pos).lengthSquared() < hit_radius * hit_radius:
                        enemy.hp -= shot.damage
                        self._spawn_hit_fx(shot.pos, Vec4(0.1, 1.0, 0.72, 0.7))
                        remove = True
                        break
            elif not remove and shot.owner == "enemy":
                if (self.player_pos - shot.pos).lengthSquared() < 18.0 * 18.0:
                    self.health = max(0.0, self.health - shot.damage)
                    self._spawn_hit_fx(self.player_pos, Vec4(1.0, 0.12, 0.05, 0.72))
                    remove = True
            if remove:
                try: shot.node.removeNode()
                except Exception: pass
                self.projectiles.remove(shot)

    def _update_fx(self, dt: float):
        remaining: list[tuple[NodePath, float]] = []
        for node, life in list(self.fx_nodes):
            next_life = float(life) - dt
            try:
                node.setScale(1.0 + (0.55 - next_life) * 2.2)
                node.setHpr(0, 0, self._elapsed * 90.0)
            except Exception:
                pass
            if next_life <= 0:
                try:
                    node.removeNode()
                except Exception:
                    pass
            else:
                remaining.append((node, next_life))
        self.fx_nodes = remaining

    def _update_weather_hazards(self, dt: float):
        for i, node in enumerate(list(self.cloud_nodes)):
            try:
                node.setX(node.getX() + math.sin(self._elapsed * 0.17 + i) * dt * 2.1)
                node.setY(node.getY() + math.cos(self._elapsed * 0.13 + i) * dt * 2.7)
                node.setH(self._elapsed * (1.0 + (i % 5) * 0.15))
            except Exception:
                pass
        for hazard in list(self.hazards):
            try:
                hazard.pos += hazard.drift * dt
                if abs(hazard.pos.x) > 860:
                    hazard.drift.x *= -1
                if abs(hazard.pos.y) > 860:
                    hazard.drift.y *= -1
                hazard.node.setPos(hazard.pos)
                hazard.node.setH(hazard.node.getH() + hazard.spin * dt)
                delta = self.player_pos - (hazard.pos + Vec3(0, 0, 45))
                if delta.lengthSquared() < hazard.radius * hazard.radius:
                    swirl = Vec3(-delta.y, delta.x, 0)
                    if swirl.lengthSquared() > 0.1:
                        swirl.normalize()
                        self.player_vel += swirl * (18.0 * dt) + Vec3(0, 0, 24.0 * dt)
                    self.health = max(0.0, self.health - 7.5 * dt)
            except Exception:
                pass

    def _update_boost_trail(self, dt: float):
        speed = self.player_vel.length()
        should_emit = speed > 135.0 or bool(self.keys.get("shift")) or self._boost_flash_timer > 0.0
        if should_emit:
            self.trail_history.insert(0, (Vec3(self.player_pos), float(self.player_yaw), float(self.player_pitch)))
            del self.trail_history[36:]
        for i, node in enumerate(self.trail_nodes):
            if i < len(self.trail_history):
                pos, yaw, pitch = self.trail_history[min(i, len(self.trail_history) - 1)]
                try:
                    node.show()
                    node.setPos(pos - _hpr_forward(yaw, pitch) * (8.0 + i * 4.3))
                    node.setHpr(yaw, pitch + 90.0, self._elapsed * (60.0 + i * 3.0))
                    node.setScale(max(0.35, 1.0 - i * 0.032))
                except Exception:
                    pass
            else:
                try:
                    node.hide()
                except Exception:
                    pass
        if self._boost_flash_timer > 0.0:
            self._boost_flash_timer = max(0.0, self._boost_flash_timer - dt)

    def _update_vector_gates(self, dt: float):
        for idx, gate in enumerate(list(self.vector_gates)):
            try:
                gate.cooldown = max(0.0, gate.cooldown - dt)
                gate.node.setH(gate.node.getH() + gate.spin * dt)
                gate.node.setP(math.sin(self._elapsed * 0.8 + idx) * 8.0)
                if gate.cooldown > 0.0:
                    gate.node.setScale(0.72 + 0.05 * math.sin(self._elapsed * 9.0))
                else:
                    gate.node.setScale(1.0 + 0.04 * math.sin(self._elapsed * 3.0 + idx))
                delta = self.player_pos - gate.pos
                if gate.cooldown <= 0.0 and delta.lengthSquared() < gate.radius * gate.radius:
                    forward = _hpr_forward(self.player_yaw, self.player_pitch)
                    self.player_vel += forward * 82.0
                    self.score += 75
                    self._boost_flash_timer = 0.75
                    self._spawn_hit_fx(gate.pos, Vec4(0.1, 1.0, 0.55, 0.82))
                    new_pos = self._gate_position(idx + self.objective_kills + int(self.score / 75))
                    gate.pos = Vec3(new_pos)
                    gate.node.setPos(gate.pos)
                    gate.cooldown = 1.4
            except Exception:
                pass

    def _update_target_guides(self):
        target = self._current_target()
        if target is None:
            for node in (self.target_lock_node, self.target_lead_node):
                try:
                    if node is not None:
                        node.hide()
                except Exception:
                    pass
            return
        try:
            if self.target_lock_node is not None:
                self.target_lock_node.show()
                self.target_lock_node.setPos(target.pos)
                self.target_lock_node.setScale(0.9 + 0.08 * math.sin(self._elapsed * 5.5))
                self.target_lock_node.setHpr(self._elapsed * 55.0, self._elapsed * 31.0, self._elapsed * 43.0)
            if self.target_lead_node is not None:
                lead = target.pos + target.vel * 0.38
                self.target_lead_node.show()
                self.target_lead_node.setPos(lead)
                self.target_lead_node.setHpr(self._elapsed * -80.0, 0, self._elapsed * 48.0)
        except Exception:
            pass

    def _update_camera(self):
        forward = _hpr_forward(self.player_yaw, self.player_pitch)
        speed = self.player_vel.length()
        distance = self.camera_distance + _clamp((speed - 120.0) * 0.11, 0.0, 28.0)
        height = self.camera_height + _clamp((speed - 160.0) * 0.025, 0.0, 10.0)
        chase = self.player_pos - forward * distance + Vec3(0, 0, height)
        look = self.player_pos + forward * (150.0 + _clamp(speed * 0.35, 0.0, 120.0)) + Vec3(0, 0, 2.5)
        try:
            if self.camera_pos is None:
                self.camera_pos = Vec3(chase)
            # Smooth the chase position but keep look direction direct enough for control.
            self.camera_pos = self.camera_pos * 0.82 + chase * 0.18
            self.camera.setPos(self.camera_pos)
            self.camera.lookAt(look)
        except Exception:
            pass

    def _update_hud(self):
        try:
            target = self._current_target()
            target_range = int((target.pos - self.player_pos).length()) if target is not None else 0
            objective = "CLEAR" if self.objective_kills >= self.objective_goal else f"{self.objective_kills}/{self.objective_goal}"
            self.hud["text"] = (
                f"VECTOR WARS // {self.combat_mode} // {self.weapon_mode} // {self.ship_variant}\n"
                f"HP {int(self.health):03d}  SCORE {self.score:05d}  TARGETS {len(self.enemies)}  LOCK {target_range:04d}m  SPEED {int(self.player_vel.length()):03d}\n"
                f"OBJECTIVE {objective} ENEMY VECTORS // Gates boost +75 // Mouse/WASD steer"
            )
        except Exception:
            pass


    def _dimension_ui_nodes(self):
        nodes = []
        seen = set()
        for name in getattr(self, "_dimension_ui_node_names", ()): 
            node = getattr(self, name, None)
            if node is None:
                continue
            try:
                key = id(node)
            except Exception:
                key = str(node)
            if key in seen:
                continue
            seen.add(key)
            nodes.append(node)
        return nodes

    def _set_dimension_ui_visible(self, visible: bool) -> None:
        self.dimension_ui_visible = bool(visible)
        for node in self._dimension_ui_nodes():
            try:
                if self.dimension_ui_visible:
                    node.show()
                else:
                    node.hide()
            except Exception:
                try:
                    node.setHidden(not self.dimension_ui_visible)
                except Exception:
                    pass

    def toggle_dimension_ui(self) -> bool:
        self._set_dimension_ui_visible(not bool(getattr(self, "dimension_ui_visible", False)))
        return True

    # ------------------------------------------------------------------
    # Host contract
    # ------------------------------------------------------------------
    def enter(self):
        self._host_resources()
        self._build_scene()
        self._set_dimension_ui_visible(False)
        self._entered = True
        self._write_log("enter", {"contract": self.contract})

    def on_host_action(self, action: str) -> bool:
        action = str(action or "").lower()
        if action in {"toggle_dimension_ui", "dimension_ui", "h"}:
            return self.toggle_dimension_ui()
        if action in {"escape", "pause", "menu", "number_0", "return", "return_to_core"}:
            return False
        if action in {"mouse1", "mouse1_down", "fire"}:
            self.fire_held = True
            self._mouse1_latched_by_event = True
            if self.fire_cooldown <= 0.0:
                self._fire_player(missile=False)
                self.fire_cooldown = 0.085 if self.weapon_mode == "MACHINE GUN" else 0.16
            return True
        if action in {"mouse1_up", "fire_up"}:
            self.fire_held = False
            self._mouse1_latched_by_event = False
            return True
        if action in {"mouse3", "mouse3_down", "right_fire", "missile"}:
            if self.missile_cooldown <= 0.0:
                self._fire_player(missile=True)
                self.missile_cooldown = 0.72
            return True
        if action in {"mouse3_up", "right_fire_up"}:
            return True
        if action in {"tab", "tab_down"}:
            self._cycle_mode()
            return True
        if action in {"r", "r_down", "reload"}:
            self._cycle_weapon()
            return True
        if action in {"t", "t_down", "target"}:
            self._cycle_target()
            return True
        if action in {"v", "v_down"}:
            self._cycle_ship()
            return True
        if action in {"space", "space_down"}:
            self._single_frame.add("space")
            return True
        return False

    def update(self, dt: float):
        if not self._entered:
            return
        dt = _safe_dt(dt)
        self._elapsed += dt
        try:
            self._sync_host_keys()
            self._update_player(dt)
            self._update_city_stream()
            self._update_enemies(dt)
            self.fire_cooldown = max(0.0, self.fire_cooldown - dt)
            self.missile_cooldown = max(0.0, self.missile_cooldown - dt)
            if self.fire_held and self.fire_cooldown <= 0.0:
                self._fire_player(missile=False)
                self.fire_cooldown = 0.085 if self.weapon_mode == "MACHINE GUN" else 0.16
            if bool(getattr(self, "missile_held", False)) and self.missile_cooldown <= 0.0:
                self._fire_player(missile=True)
                self.missile_cooldown = 0.72
            self._update_projectiles(dt)
            self._update_fx(dt)
            self._update_weather_hazards(dt)
            self._update_vector_gates(dt)
            self._update_boost_trail(dt)
            self._update_target_guides()
            self._update_camera()
            self._update_hud()
            self._set_dimension_ui_visible(bool(getattr(self, "dimension_ui_visible", False)))
            if self.health <= 0:
                self.health = 100.0
                self.player_pos = Vec3(0, 0, 70)
                self.player_vel = Vec3(0, 88, 0)
                self._spawn_hit_fx(self.player_pos, Vec4(0.4, 0.9, 1.0, 0.8))
        except Exception as exc:
            self._write_log("update_failed", {"error": f"{exc.__class__.__name__}: {exc}", "traceback": traceback.format_exc()[-2500:]})
            raise
        finally:
            self._single_frame.clear()

    def exit(self):
        self._write_log("exit", {"score": self.score, "enemies": len(self.enemies)})
        for shot in list(self.projectiles):
            try: shot.node.removeNode()
            except Exception: pass
        for enemy in list(self.enemies):
            try: enemy.node.removeNode()
            except Exception: pass
        for hazard in list(self.hazards):
            try: hazard.node.removeNode()
            except Exception: pass
        for gate in list(getattr(self, "vector_gates", [])):
            try: gate.node.removeNode()
            except Exception: pass
        for node in list(getattr(self, "trail_nodes", [])):
            try: node.removeNode()
            except Exception: pass
        for node in list(self.city_nodes) + list(self.star_nodes) + list(self.cloud_nodes):
            try: node.removeNode()
            except Exception: pass
        for node in list(self._owned):
            try:
                if node is not None and hasattr(node, "removeNode") and not node.isEmpty():
                    node.removeNode()
            except Exception:
                pass
        try:
            if self._saved_camera_parent is not None and not self._saved_camera_parent.isEmpty():
                self.camera.reparentTo(self._saved_camera_parent)
                if self._saved_camera_transform is not None:
                    self.camera.setTransform(self._saved_camera_transform)
        except Exception:
            pass
        try:
            if self.win is not None and hasattr(self.win, "requestProperties"):
                props = WindowProperties()
                props.setCursorHidden(False)
                self.win.requestProperties(props)
        except Exception:
            pass
        self._entered = False

    destroy = exit

    def _write_log(self, event: str, extra: dict | None = None):
        if str(os.environ.get("HOLOVERSE_NATIVE_ADAPTER_LOGS", "")).strip().lower() not in {"1", "true", "yes", "on"}:
            return
        try:
            log = self.folder / "logs" / "native_adapter_vector_wars.log"
            log.parent.mkdir(parents=True, exist_ok=True)
            log.write_text("", encoding="utf-8") if log.exists() and log.stat().st_size > 128_000 else None
            with log.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({"time": time.strftime("%Y-%m-%d %H:%M:%S"), "event": event, "extra": extra or {}}, default=str) + "\n")
        except Exception:
            pass


def create_mode(host, mode=None, entry_path=None, label=MODE_TITLE):
    return HoloVerseNativeMode(host, mode=mode, entry_path=entry_path, label=label)

# ---------------------------------------------------------------------------
# Pass 84: integrated profile SFX layer
# ---------------------------------------------------------------------------
# Keep this audio layer in the same adapter file.  Do not split Vector Wars into
# wrapper/base adapters again; split adapters caused packaging regressions where
# the active file existed but the imported base file was missing.
from panda3d.core import Filename as _VWFilename

_VectorWarsDogfightMode = HoloVerseNativeMode


def _vw_read_json(path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _vw_as_list(value):
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(v) for v in value if str(v).strip()]
    return []


class HoloVerseNativeMode(_VectorWarsDogfightMode):
    """Single-file Vector Wars adapter with committed-asset event SFX.

    HoloVerse owns music and ambience for same-window dimensions.  Vector Wars
    only plays event SFX from committed local/shared assets; it never creates or
    reads generated/custom/override SFX folders.
    """

    def __init__(self, host, mode=None, entry_path=None, label=MODE_TITLE):
        super().__init__(host, mode=mode, entry_path=entry_path, label=label)
        self.audio_profile = {}
        self._event_sounds = {}
        self._event_volumes = {}
        self._asset_audio_debug = {}

    def _audio_roots(self):
        try:
            holo = self.folder.parents[1]
            data = holo.parent
        except Exception:
            holo = Path(__file__).resolve().parents[2]
            data = holo.parent
        return [
            self.folder / "assets" / "sfx",
            self.folder / "assets" / "audio" / "sfx",
            holo / "assets" / "audio" / "sfx" / "shared",
            holo / "assets" / "audio" / "source" / "vector_wars",
            data / "assets" / "audio" / "sfx" / "shared",
            data / "assets" / "audio" / "source" / "vector_wars",
        ]

    def _audio_event_spec(self, event):
        events = self.audio_profile.get("events", {}) if isinstance(self.audio_profile.get("events"), dict) else {}
        spec = events.get(str(event), {}) if isinstance(events, dict) else {}
        return spec if isinstance(spec, dict) else {}

    def _find_audio_event_file(self, event):
        spec = self._audio_event_spec(event)
        names = _vw_as_list(spec.get("preferred"))
        cats = _vw_as_list(spec.get("categories", spec.get("category")))
        for root in self._audio_roots():
            for cat in cats:
                clean = str(cat).replace("\\", "/").strip("/")
                for name in names:
                    path = root / clean / str(name)
                    if path.exists() and path.is_file():
                        return path
            for name in names:
                path = root / str(name)
                if path.exists() and path.is_file():
                    return path
            for cat in cats:
                folder = root / str(cat).replace("\\", "/").strip("/")
                if not folder.exists() or not folder.is_dir():
                    continue
                for ext in (".wav", ".ogg", ".mp3", ".WAV", ".OGG", ".MP3"):
                    found = sorted(folder.glob(f"*{ext}"))
                    if found:
                        return found[0]
        return None

    def _load_audio_event(self, path):
        if path is None:
            return None
        try:
            return self.loader.loadSfx(_VWFilename.fromOsSpecific(os.fspath(path.resolve())))
        except Exception:
            try:
                return self.loader.loadSfx(os.fspath(path).replace("\\", "/"))
            except Exception:
                return None

    def _setup_audio_events(self):
        self.audio_profile = _vw_read_json(self.folder / "audio_profile.json")
        events = self.audio_profile.get("events", {}) if isinstance(self.audio_profile.get("events"), dict) else {}
        resolved = {}
        for event in sorted(events):
            path = self._find_audio_event_file(event)
            sound = self._load_audio_event(path)
            if sound is None:
                continue
            self._event_sounds[str(event)] = sound
            try:
                self._event_volumes[str(event)] = max(0.0, min(1.0, float(events[event].get("volume", 1.0))))
            except Exception:
                self._event_volumes[str(event)] = 1.0
            resolved[str(event)] = os.fspath(path)
        self._asset_audio_debug = {
            "policy": "single_adapter_committed_event_sfx_only",
            "profile": os.fspath(self.folder / "audio_profile.json"),
            "resolved_events": resolved,
            "music_owner": "HoloVerse root SharedAudio",
        }
        try:
            self.contract["asset_audio"] = dict(self._asset_audio_debug)
        except Exception:
            pass

    def _play_audio_event(self, event):
        snd = self._event_sounds.get(str(event))
        if snd is None:
            return
        try:
            snd.stop()
            snd.setVolume(self._event_volumes.get(str(event), 1.0))
            snd.play()
        except Exception:
            pass

    def enter(self):
        result = super().enter()
        self._setup_audio_events()
        return result

    def _fire_player(self, *args, **kwargs):
        self._play_audio_event("missile" if bool(kwargs.get("missile", False)) else "fire_primary")
        return super()._fire_player(*args, **kwargs)

    def _fire_enemy(self, *args, **kwargs):
        self._play_audio_event("fire_laser")
        return super()._fire_enemy(*args, **kwargs)

    def _spawn_hit_fx(self, *args, **kwargs):
        self._play_audio_event("hit")
        return super()._spawn_hit_fx(*args, **kwargs)

    def _cycle_target(self):
        self._play_audio_event("ui")
        return super()._cycle_target()

    def _cycle_mode(self):
        self._play_audio_event("ui")
        return super()._cycle_mode()

    def _cycle_weapon(self):
        self._play_audio_event("ui")
        return super()._cycle_weapon()

    def _cycle_ship(self):
        self._play_audio_event("ui")
        return super()._cycle_ship()

    def get_holoverse_result(self) -> dict:
        score = max(0, int(getattr(self, "score", 0) or 0))
        kills = max(0, int(getattr(self, "objective_kills", 0) or 0))
        goal = max(1, int(getattr(self, "objective_goal", 15) or 15))
        if score <= 0 and kills <= 0:
            return {}
        completed = bool(kills >= goal)
        signal = "VECTOR_WARS_DOGFIGHT_CLEAR" if completed else "VECTOR_WARS_TARGET_SAMPLE"
        return {
            "schema": 1,
            "mode": MODE_TITLE,
            "score_delta": score,
            "completed": completed,
            "fragments_recovered": kills,
            "fragments_required": goal,
            "signal": signal,
            "memory_fragment": signal,
            "gleebs_response": "Vector Wars returned a complete dogfight route." if completed else "Vector Wars returned target telemetry.",
        }

    def exit(self):
        for snd in list(getattr(self, "_event_sounds", {}).values()):
            try:
                snd.stop()
            except Exception:
                pass
        self._event_sounds.clear()
        return super().exit()

    destroy = exit


def create_mode(host, mode=None, entry_path=None, label=MODE_TITLE):
    return HoloVerseNativeMode(host, mode=mode, entry_path=entry_path, label=label)
