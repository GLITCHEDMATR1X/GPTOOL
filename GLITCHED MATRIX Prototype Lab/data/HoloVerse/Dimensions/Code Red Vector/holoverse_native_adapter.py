"""Same-window source adapter for Code Red Vector.

Code Red Vector ships with a large Panda3D arcade source that normally creates
its own ShowBase/window.  This adapter mounts that source into HoloVerse's live
ShowBase instead: it imports ``main.py``, binds the real arcade scene/simulation
methods, supplies HoloVerse-owned render/camera/UI resources, and keeps the old
hosted wrapper as fallback only.

ESC is reserved for the HoloVerse return contract.
"""
from __future__ import annotations

import importlib.util
import os
import random
import sys
import time
import traceback
from pathlib import Path

from panda3d.core import AmbientLight, ClockObject, DirectionalLight, Fog, NodePath, TransparencyAttrib, Vec2, Vec3, Vec4, WindowProperties

MODE_TITLE = "Code Red Vector"
MODE_ID = "code_red_vector"
MODE_STATUS = "CODE RED VECTOR // LMB LEFT TURRET // RMB RIGHT TURRET // ESC / 0 RETURN TO HOLOVERSE // H SHOWS LEGACY UI"

_SOURCE_MODULE = None


def _load_source_module(folder: Path):
    global _SOURCE_MODULE
    if _SOURCE_MODULE is not None:
        return _SOURCE_MODULE
    src = Path(folder) / "main.py"
    if not src.exists():
        raise FileNotFoundError(f"Code Red Vector source main.py missing: {src}")
    module_name = f"code_red_vector_source_{int(time.time() * 1000)}"
    spec = importlib.util.spec_from_file_location(module_name, src)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not create import spec for {src}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    _SOURCE_MODULE = module
    return module


class _HostSoundRelay:
    """Small Panda3D-safe bridge for Code Red's existing SoundBank calls.

    The original source uses pygame for event SFX.  In same-window HoloVerse the
    host already owns a working audio bus, so this relay preserves the source
    event calls without starting a second mixer or muting the mode.
    """

    def __init__(self, host, folder: Path, label: str = MODE_TITLE):
        self.host = host
        self.folder = Path(folder)
        self.label = str(label or MODE_TITLE)
        self.master_volume = 0.82
        self.sfx_volume = 0.86
        self.last_play: dict[str, float] = {}
        self.status = "host audio relay pending"
        self.sounds: dict[str, Path] = {}
        self._scan()

    def _scan(self):
        prefixes = (
            "fire_left", "fire_right", "hit", "break", "explosion",
            "pickup", "boost", "jump", "land", "engine",
        )
        for prefix in prefixes:
            for ext in (".wav", ".ogg", ".mp3"):
                for path in sorted(self.folder.glob(f"{prefix}*{ext}")):
                    self.sounds[prefix] = path
                    break
                if prefix in self.sounds:
                    break
        count = len(self.sounds)
        self.status = f"host audio relay ready: {count} Code Red SFX" if count else "host audio relay: no Code Red SFX"

    def set_mix(self, master: float = 0.82, sfx: float = 0.86) -> None:
        try:
            self.master_volume = max(0.0, min(1.0, float(master)))
            self.sfx_volume = max(0.0, min(1.0, float(sfx)))
        except Exception:
            pass

    def set_listener(self, *_, **__):
        return None

    def _path_for(self, event: str) -> Path | None:
        event = str(event or "").strip().lower()
        if event in self.sounds:
            return self.sounds[event]
        if event.startswith("fire"):
            return self.sounds.get("fire_left") or self.sounds.get("fire_right")
        if event in {"destroy", "damage"}:
            return self.sounds.get("explosion") or self.sounds.get("hit")
        return self.sounds.get(event.split("_", 1)[0])

    def play(self, event: str, volume: float = 0.72, throttle: float = 0.0, x: float | None = None, y: float | None = None, loud: bool = False) -> None:
        path = self._path_for(event)
        if path is None:
            return
        now = time.monotonic()
        key = f"{event}:{'world' if x is not None or y is not None else 'local'}"
        try:
            if throttle and now - self.last_play.get(key, -999.0) < float(throttle):
                return
        except Exception:
            pass
        self.last_play[key] = now
        audio = getattr(self.host, "audio", None)
        if audio is None:
            return
        try:
            gain = max(0.0, min(1.0, float(volume) * self.master_volume * self.sfx_volume))
            audio.play(os.fspath(path), bus="sfx", volume=gain)
        except Exception:
            pass

    def update_engine(self, speed: float, boosting: bool = False) -> None:
        # Preserve engine feedback without running a permanent source-owned loop.
        try:
            throttle = 0.34 if boosting else 0.55
            volume = max(0.08, min(0.42, 0.10 + abs(float(speed)) / 90.0 * 0.28 + (0.10 if boosting else 0.0)))
            self.play("engine", volume=volume, throttle=throttle)
        except Exception:
            pass

    def stop(self):
        return None


class HoloVerseNativeMode:
    """Code Red Vector mounted inside the live HoloVerse ShowBase."""

    def __init__(self, host, mode=None, entry_path=None, label=MODE_TITLE):
        self.host = host
        self.mode = mode or {}
        self.entry_path = Path(entry_path) if entry_path else Path(__file__).resolve().parent / "main.py"
        self.folder = self.entry_path.parent
        self.label = str(label or MODE_TITLE)
        self.source = None
        self.clock = ClockObject.getGlobalClock()
        self._entered = False
        self.dimension_ui_visible = False
        self._dimension_ui_node_names = ('ui_root',)
        self._source_methods_bound = False
        self._owned_nodes: list[NodePath] = []
        self._new_aspect_children: list[NodePath] = []
        self._saved_camera_parent = None
        self._saved_camera_transform = None
        self._saved_bg = None
        self._single_frame_actions: set[str] = set()
        # Mouse buttons are held-state controls in Code Red Vector.  Earlier
        # native passes treated them as one-frame pulses, which made turret
        # fire feel overridden and swapped.
        self._held_mouse_buttons: set[str] = set()
        self._host_key_names = (
            "w", "a", "s", "d", "arrow_up", "arrow_down", "arrow_left", "arrow_right",
            "shift", "control", "space", "q", "e", "f",
        )

    # ------------------------------------------------------------------
    # Source compatibility layer
    # ------------------------------------------------------------------
    def _bind_source_methods(self):
        cls = getattr(self.source, "PandaArcadeApp", None)
        if cls is None:
            raise AttributeError("Code Red Vector source lacks PandaArcadeApp")
        skip = {
            "__init__", "run", "_bind_controls", "_close", "_on_window_event",
            "_apply_mouse_capture", "_apply_display_settings", "_toggle_fullscreen",
            "_task_update",
        }
        for name, value in cls.__dict__.items():
            if name.startswith("__") or name in skip:
                continue
            if callable(value):
                try:
                    setattr(self, name, value.__get__(self, self.__class__))
                except Exception:
                    pass
        self._source_methods_bound = True

    def _host_resources(self):
        self.base = self.host
        self.Task = getattr(self.source, "Task", None)
        if self.Task is None:
            from direct.task import Task
            self.Task = Task
        from direct.gui.OnscreenText import OnscreenText
        self.OnscreenText = OnscreenText
        self.loader = self.host.loader
        self.win = getattr(self.host, "win", None)
        self.camera = self.host.camera
        self.camLens = self.host.camLens
        self.taskMgr = getattr(self.host, "taskMgr", None)
        self.aspect2d = self.host.aspect2d
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

        self.root = self.host.render.attachNewNode("code_red_vector_native_root")
        self.world_root = self.root.attachNewNode("world")
        self.ui_root = self.aspect2d.attachNewNode("code_red_vector_hud_root")
        self.render = self.world_root
        self._owned_nodes.extend([self.root, self.world_root, self.ui_root])

        try:
            self.disableMouse()
            self.root.setTransparency(TransparencyAttrib.MAlpha)
            self.camLens.setFov(88)
            self.camLens.setNearFar(1.5, 6800)
            self.setBackgroundColor(0.015, 0.018, 0.024, 1)
            if self.win is not None and hasattr(self.win, "requestProperties"):
                props = WindowProperties()
                props.setCursorHidden(True)
                self.win.requestProperties(props)
        except Exception:
            pass

    def _init_arcade_state(self):
        src = self.source
        self.settings_path = self.folder / "runtime" / "arcade_settings.json"
        try:
            self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        self.frame_index = 0
        self.settings_mtime = 0.0
        self.settings = {}
        self.vehicle_values = {}
        self.vehicle_name = "Car01"
        self.vehicle_asset_status = "vehicle asset pending"
        self._vehicle_source_np = None
        self._vehicle_glb_cache = None
        self._vehicle_accessor_cache = {}
        self.player_wheel_phase = 0.0
        self.rival_wheel_phases = [0.0 for _ in range(18)]
        self.scene_dt = 1.0 / 60.0
        self.arcade_options = {}
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
        self.prop_colliders = []
        self.hp = 14.0
        self.max_hp = 14.0
        self.player_parts = src.make_player_parts()
        self.was_boosting = False
        self.ramp_specs = []
        self.score = 0
        self.wave = 1
        self.kills = 0
        self.fire_cooldown = 0.0
        self.missile_cooldown = 0.0
        self.left_flash_timer = 0.0
        self.right_flash_timer = 0.0
        self.boost_heat = 0.0
        self.projectiles = []
        self.rivals = []
        self.pickups = []
        self.pedestrians = []
        self.locked_rival_name = None
        self.splatter_marks = []
        self.explosions = []
        self.muzzle_flashes = []
        self.peers = {}
        self.player_id = f"holoverse-code-red-{os.getpid()}-{random.randint(1000,9999)}"
        self.lan = None
        self.sound = _HostSoundRelay(self.host, self.folder / "assets" / "sfx" / "arcade", self.label)
        self.last_tick = time.monotonic()

    def _install_lighting(self):
        ambient = AmbientLight("code_red_ambient")
        ambient.setColor((0.30, 0.30, 0.33, 1))
        self.ambient_light = ambient
        self.ambient_np = self.world_root.attachNewNode(ambient)
        self.world_root.setLight(self.ambient_np)

        sun = DirectionalLight("code_red_hard_red_sun")
        sun.setColor((0.86, 0.31, 0.22, 1))
        self.sun_light = sun
        self.sun_np = self.world_root.attachNewNode(sun)
        self.sun_np.setHpr(-38, -57, 0)
        self.world_root.setLight(self.sun_np)

        fog = Fog("code_red_haze")
        fog.setColor(0.035, 0.010, 0.014)
        fog.setLinearRange(680, 3300)
        self.fog = fog
        self.world_root.setFog(fog)

    def _apply_display_settings(self, initial: bool = False) -> None:
        try:
            clamp = getattr(self.source, "clamp")
            self.camera_base_fov = clamp(float(self.arcade_options.get("camera_fov", getattr(self, "camera_base_fov", 88.0))), 68.0, 106.0)
            self.camera_zoom = clamp(float(self.arcade_options.get("camera_zoom", getattr(self, "camera_zoom", 1.72))), 0.62, 1.72)
            self._update_camera_lens(force=True)
        except Exception:
            pass

    def _toggle_fullscreen(self) -> None:
        # Same-window dimensions may not resize or take ownership of the host window.
        self.arcade_options["full_windowed"] = False
        self._apply_display_settings(initial=False)

    def _apply_mouse_capture(self, enabled: bool) -> None:
        self.mouse_capture_active = bool(enabled and self.mouse_capture_enabled)
        self._mouse_ignore_next_delta = True
        try:
            if self.win is not None and hasattr(self.win, "requestProperties"):
                props = WindowProperties()
                props.setCursorHidden(self.mouse_capture_active)
                self.win.requestProperties(props)
        except Exception:
            pass

    def _close(self) -> None:
        # Pause-menu EXIT ARCADE returns to HoloVerse, not out of the app.
        try:
            self.host.return_from_native_mode(reason="code_red_exit_button")
        except Exception:
            pass

    def _reparent_source_ui(self):
        for name in (
            "hud_panel", "bottom_panel", "hud", "metal_status", "help_text",
            "pause_text", "credit_text", "pause_panel",
        ):
            node = getattr(self, name, None)
            try:
                if node is not None and not node.isEmpty():
                    node.wrtReparentTo(self.ui_root)
            except Exception:
                try:
                    node.reparentTo(self.ui_root)
                except Exception:
                    pass

    def _sync_host_keys(self):
        host_keys = getattr(self.host, "keys", {}) or {}
        for key in self._host_key_names:
            if bool(host_keys.get(key, False)):
                self.keys.add(key)
            elif key not in self._single_frame_actions:
                self.keys.discard(key)
        # Release momentary actions after one update frame.
        for key in list(self._single_frame_actions):
            if key not in {"mouse1", "mouse3"}:
                self.keys.discard(key)
        mouse_state = set(getattr(self, "_held_mouse_buttons", set()))
        for key in ("mouse1", "mouse3"):
            if key in self._single_frame_actions:
                mouse_state.add(key)
        self.mouse_buttons.clear()
        self.mouse_buttons.update(mouse_state)
        self._single_frame_actions.clear()


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
        self.source = _load_source_module(self.folder)
        self._bind_source_methods()
        self._host_resources()
        self._init_arcade_state()
        self._install_lighting()
        self._load_settings(force=True)
        # Keep the same-window route conservative and responsive.
        self.arcade_options["full_windowed"] = False
        self.arcade_options["rival_count"] = min(int(self.arcade_options.get("rival_count", 4) or 4), 6)
        self.arcade_options["rivals_fire"] = bool(self.arcade_options.get("rivals_fire", True))
        self._apply_display_settings(initial=True)
        self._build_scene()
        self._reparent_source_ui()
        self._spawn_wave(reset=True)
        self._spawn_pickups()
        self._spawn_pedestrians()
        self._set_dimension_ui_visible(False)
        self._entered = True
        try:
            self.center_status_text = MODE_STATUS
            self.help_visible = True
            self._sync_scene()
        except Exception:
            pass

    def on_host_action(self, action: str) -> bool:
        action = str(action or "").lower()
        if not self._entered:
            return False
        if action in {"toggle_dimension_ui", "dimension_ui", "h"}:
            return self.toggle_dimension_ui()
        if action == "escape":
            # Let the host unmount the mode.
            return False
        if action == "mouse1":
            # LMB held = left turret automatic fire.
            self._held_mouse_buttons.add("mouse1")
            return True
        if action == "mouse1_up":
            self._held_mouse_buttons.discard("mouse1")
            return True
        if action == "mouse3":
            # RMB held = right turret automatic fire.
            self._held_mouse_buttons.add("mouse3")
            return True
        if action == "mouse3_up":
            self._held_mouse_buttons.discard("mouse3")
            return True
        if action in {"q_down", "e_down"}:
            self._single_frame_actions.add("mouse1")
            return True
        if action in {"number_1"}:
            self._single_frame_actions.add("mouse3")
            return True
        if action in {"tab", "space_down", "number_2"}:
            try:
                self._cycle_lock_target()
            except Exception:
                pass
            return True
        if action in {"number_3"}:
            try:
                self._toggle_camera_lock()
            except Exception:
                pass
            return True
        if action in {"number_4"}:
            try:
                self._toggle_help()
            except Exception:
                pass
            return True
        if action in {"number_0"}:
            return False
        return False

    def update(self, dt: float):
        if not self._entered:
            return
        try:
            dt = max(0.0, min(float(dt or 0.0), 0.05))
        except Exception:
            dt = 1.0 / 60.0
        self.scene_dt = dt
        self.last_tick = time.monotonic()
        self._sync_host_keys()
        self._load_settings()
        if not self.paused:
            self._update_world(dt)
        self._sync_scene()
        # Patch the source HUD wording for the same-window contract.
        try:
            if getattr(self, "help_visible", False):
                current = self.help_text.getText()
                if "Esc settings" in current or "Esc pause" in current:
                    self.help_text.setText(current.replace("Esc settings", "ESC / 0 return to HoloVerse").replace("Esc pause/settings", "ESC / 0 return to HoloVerse"))
            status = self.metal_status.getText()
            if "Esc settings" in status:
                self.metal_status.setText(status.replace("Esc settings", "ESC / 0 return to HoloVerse"))
        except Exception:
            pass
        self.frame_index += 1
        self._set_dimension_ui_visible(bool(getattr(self, "dimension_ui_visible", False)))

    def get_holoverse_result(self) -> dict:
        score = max(0, int(getattr(self, "score", 0) or 0))
        kills = max(0, int(getattr(self, "kills", 0) or 0))
        wave = max(1, int(getattr(self, "wave", 1) or 1))
        if score <= 0 and kills <= 0 and wave <= 1:
            return {}
        completed = bool(kills >= 5 or wave > 1)
        signal = "CODE_RED_VECTOR_WAVE_STABILIZED" if completed else "CODE_RED_VECTOR_COMBAT_SAMPLE"
        return {
            "schema": 1,
            "mode": MODE_TITLE,
            "score_delta": score,
            "completed": completed,
            "fragments_recovered": kills,
            "fragments_required": 5,
            "signal": signal,
            "memory_fragment": signal,
            "gleebs_response": "Code Red returned a combat-clear vector." if completed else "Code Red returned partial combat telemetry.",
        }

    def exit(self):
        self._entered = False
        try:
            if self.lan:
                self.lan.stop()
        except Exception:
            pass
        try:
            self.sound.stop()
        except Exception:
            pass
        try:
            self.keys.clear()
            self.mouse_buttons.clear()
            self._held_mouse_buttons.clear()
            self.projectiles.clear()
            self.rivals.clear()
            self.pickups.clear()
            self.pedestrians.clear()
            self.explosions.clear()
            self.muzzle_flashes.clear()
            self.prop_colliders.clear()
        except Exception:
            pass
        # Source-created world nodes are children of root/world_root.  Source UI
        # is reparented under ui_root, so removing our roots fully cleans it.
        for node in reversed(self._owned_nodes):
            try:
                if node is not None and not node.isEmpty():
                    node.removeNode()
            except Exception:
                pass
        self._owned_nodes.clear()
        try:
            if self._saved_camera_parent is not None and self._saved_camera_transform is not None and not self._saved_camera_parent.isEmpty():
                self.camera.reparentTo(self._saved_camera_parent)
                self.camera.setTransform(self._saved_camera_transform)
        except Exception:
            pass
        try:
            if self._saved_bg is not None:
                self.setBackgroundColor(self._saved_bg)
        except Exception:
            pass
        try:
            if self.win is not None and hasattr(self.win, "requestProperties"):
                props = WindowProperties()
                props.setCursorHidden(True)
                self.win.requestProperties(props)
        except Exception:
            pass

    destroy = exit


def create_mode(host, mode=None, entry_path=None, label=MODE_TITLE):
    try:
        return HoloVerseNativeMode(host, mode=mode, entry_path=entry_path, label=label)
    except Exception:
        traceback.print_exc()
        raise
