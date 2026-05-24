"""Same-window source adapter for Holo Conquest.

Mounts Holo Conquest's real Panda3D source into the live HoloVerse window.
The artifact route no longer uses the hosted child-window wrapper. ESC/0 are
left to the host so Core can unmount the mode and restore the hub cleanly.
"""
from __future__ import annotations

import importlib.util
import os
import random
import sys
import time
import traceback
from pathlib import Path

from panda3d.core import ClockObject, NodePath, Vec3, WindowProperties

MODE_TITLE = "Holo Conquest"
MODE_ID = "holo_conquest"
MODE_STATUS = "HOLO CONQUEST // SOURCE-BACKED SAME-WINDOW // ESC / 0 RETURN TO HOLOVERSE // H SHOWS LEGACY UI"

_SOURCE_MODULE = None
_SOURCE_MODULE_ERROR = ""


def _load_source_module(folder: Path):
    """Load Holo Conquest/main.py without running main()."""
    global _SOURCE_MODULE, _SOURCE_MODULE_ERROR
    if _SOURCE_MODULE is not None:
        return _SOURCE_MODULE
    src = Path(folder) / "main.py"
    if not src.exists():
        raise FileNotFoundError(f"Holo Conquest source main.py missing: {src}")
    module_name = f"holo_conquest_source_{int(time.time() * 1000)}"
    spec = importlib.util.spec_from_file_location(module_name, src)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not create import spec for {src}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    old_cwd = os.getcwd()
    try:
        os.chdir(os.fspath(folder))
        spec.loader.exec_module(module)
    except Exception as exc:
        _SOURCE_MODULE_ERROR = f"{exc.__class__.__name__}: {exc}"
        raise
    finally:
        os.chdir(old_cwd)
    _SOURCE_MODULE = module
    return module


class _TaskShim:
    cont = "cont"
    done = "done"


class HoloVerseNativeMode:
    """Holo Conquest mounted into HoloVerse Core's existing ShowBase."""

    def __init__(self, host, mode=None, entry_path=None, label=MODE_TITLE):
        self.host = host
        self.mode = mode or {}
        self.entry_path = Path(entry_path) if entry_path else Path(__file__).resolve().parent / "main.py"
        self.folder = self.entry_path.parent
        self.label = str(label or MODE_TITLE)
        self.source = None
        self.source_error = ""
        self._entered = False
        self.dimension_ui_visible = False
        self._dimension_ui_node_names = ('hud_frame', 'help_frame', 'minimap', 'pause_menu')
        self._owned_roots = []
        self._host_key_names = ("w", "a", "s", "d", "shift", "space", "q", "mouse1")
        self._task_shim = _TaskShim()
        self._saved_camera_parent = None
        self._saved_camera_transform = None
        self._mode_root = None
        self._single_frame_keys = set()

    # ------------------------------------------------------------------
    # Source boot / compatibility surface
    # ------------------------------------------------------------------
    def _bind_source_methods(self):
        cls = getattr(self.source, "WastelandGame", None)
        if cls is None:
            raise AttributeError("Holo Conquest source lacks WastelandGame")
        skip = {
            "__init__", "run", "destroy", "userExit", "accept", "ignore", "ignoreAll",
            "_apply_window_settings", "_bind_inputs", "_auto_exit_task",
        }
        for name, value in cls.__dict__.items():
            if name.startswith("__") or name in skip:
                continue
            if callable(value):
                try:
                    setattr(self, name, value.__get__(self, self.__class__))
                except Exception:
                    pass
            elif name.isupper():
                try:
                    setattr(self, name, value)
                except Exception:
                    pass

    def _host_resources(self):
        self._saved_camera_parent = self.host.camera.getParent()
        self._saved_camera_transform = self.host.camera.getTransform()
        self._mode_root = self.host.render.attachNewNode("holo_conquest_native_root")
        self._owned_roots.append(self._mode_root)

        self.render = self._mode_root
        self.aspect2d = self.host.aspect2d
        self.render2d = getattr(self.host, "render2d", None)
        self.camera = self.host.camera
        self.camLens = self.host.camLens
        self.loader = self.host.loader
        self.win = getattr(self.host, "win", None)
        self.task_mgr = getattr(self.host, "taskMgr", None)
        self.taskMgr = getattr(self.host, "taskMgr", None)
        self.clock = ClockObject.getGlobalClock()
        self.globalClock = self.clock
        self.sfxManagerList = getattr(self.host, "sfxManagerList", [])
        self.musicManager = getattr(self.host, "musicManager", None)
        self.devices = getattr(self.host, "devices", None)
        self.accept = getattr(self.host, "accept", lambda *a, **k: None)
        self.ignore = getattr(self.host, "ignore", lambda *a, **k: None)
        self.ignoreAll = getattr(self.host, "ignoreAll", lambda *a, **k: None)
        self.disableMouse = getattr(self.host, "disableMouse", lambda *a, **k: None)
        self.disable_mouse = self.disableMouse
        self.setBackgroundColor = getattr(self.host, "setBackgroundColor", lambda *a, **k: None)
        self.set_background_color = self.setBackgroundColor
        self.userExit = getattr(self.host, "userExit", lambda *a, **k: None)

        # The source uses ShowBase globals (render/loader/camera/globalClock) in a
        # few places. Point those globals at the same-window resources before any
        # source setup method runs.
        self.source.render = self._mode_root
        self.source.loader = self.loader
        self.source.camera = self.camera
        self.source.globalClock = self.clock
        self.source.base = self.host
        try:
            self.source.taskMgr = self.taskMgr
        except Exception:
            pass
        try:
            # Offscreen validation buffers do not expose pointer APIs. Keep the
            # real game path unchanged for normal windows, but let smoke tests
            # use the source's deterministic SELF_TEST camera branch.
            self.source.SELF_TEST = not hasattr(self.win, "get_pointer")
        except Exception:
            pass

    def _build_embedded_settings(self):
        src = self.source
        video = src.VideoSettings(width=1920, height=1080, fullscreen=False, max_fps=90)
        world = src.WorldSettings(
            seed=int(getattr(src.WorldSettings(), "seed", 24091)),
            world_size=112,
            tile_size=float(getattr(src.WorldSettings(), "tile_size", 2.0)),
            terrain_height=10.0,
            terrain_noise_scale=float(getattr(src.WorldSettings(), "terrain_noise_scale", 0.015)),
            loot_count=52,
            enemy_squads=8,
            tree_count=48,
            foliage_count=180,
        )
        return src.GameSettings(video=video, world=world, squad=src.GameSettings().squad)

    def _init_source_state(self):
        src = self.source
        self.settings = self._build_embedded_settings()
        self.keys = {}
        self.selected_index = 0

        self.world_root = self._mode_root.attach_new_node("world")
        self.fx_root = self.world_root.attach_new_node("fx")
        self._owned_roots.append(self.world_root)

        self.characters = []
        self.enemies = []
        self.loot_nodes = []
        self.projectiles = []
        self.allies = []
        self.dynamic_nodes = []
        self.breakables = []
        self.giant_robots = []

        self.terrain_heights = []
        self.texture_bank = {}
        self.sfx = {}
        self.audio_bus = src.load_shared_audio_bus()
        self.launch_settings = src.load_shared_launch_settings()
        # Keep embedded HoloVerse artifact sessions conservative and inside the
        # existing host window instead of rewriting window state.
        self.launch_settings["width"] = 1920
        self.launch_settings["height"] = 1080
        self.launch_settings["fullscreen"] = False
        self.launch_settings["borderless"] = False
        self.launch_settings["graphics_quality"] = "medium"

        self.render_scale_4k = False
        self.graphics_high = False
        self.day_phase = 0.15
        self.tron_fx_enabled = True
        self.stream_shift_total = src.LVector3f(0, 0, 0)
        self.airstrike_timer = 8.0
        self.bomber_nodes = []
        self.mage_power_profile = {"name": "Arc Lance", "range": 46.0, "mult": 1.0, "fx": src.LColor(0.4, 0.9, 1.0, 1.0), "sfx": "attack"}
        self.melee_power_profile = {"name": "Titan Cleave", "mult": 1.0, "fx": src.LColor(1.0, 0.72, 0.35, 1.0), "sfx": "hit"}
        self.vertical_velocity = 0.0
        self.on_ground = True
        self.jetpack_fuel = 4.0
        self.jetpack_cooldown = 0.0
        self.sprint_multiplier = 1.65
        self.weapon_slot = 0
        self.weapon_fx_index = 0
        self.capture_flags = []
        self.ally_guard_assignment = {}
        self.platform_surfaces = []
        self.terrain_craters = []
        self.distant_flyers = []
        self.pause_open = False
        self.terrain_span = self.settings.world.world_size * self.settings.world.tile_size
        self.weapon_profiles = [
            {"name": "XR-7 Pulse Rifle", "dmg": 14.0, "rate": 0.11, "spread": 0.018, "speed": 68.0, "shape": "needle", "fx": src.LColor(0.4, 0.95, 1.0, 1)},
            {"name": "ARC Coil Carbine", "dmg": 18.0, "rate": 0.20, "spread": 0.026, "speed": 58.0, "shape": "pulse", "fx": src.LColor(0.7, 0.8, 1.0, 1)},
            {"name": "TESLA Scatter", "dmg": 8.0, "rate": 0.08, "spread": 0.06, "speed": 52.0, "shape": "shard", "fx": src.LColor(0.95, 0.75, 1.0, 1)},
        ]

        random.seed(self.settings.world.seed)
        try:
            self.disableMouse()
        except Exception:
            pass
        try:
            self.set_background_color(0.04, 0.05, 0.07, 1.0)
        except Exception:
            pass
        try:
            self.camLens.set_fov(82.0)
            self.camLens.set_near_far(0.08, 900.0)
        except Exception:
            pass

        self._configure_clock()
        self._build_texture_bank()
        self._init_audio_bank()
        self._start_soundtrack()
        # Same-window HoloVerse owns the music bed; keep Conquest SFX but stop
        # the source soundtrack to prevent overlapping songs across dimensions.
        try:
            if getattr(self, "music", None):
                self.music.stop()
            self.music = None
        except Exception:
            pass
        self._setup_lighting()
        self._setup_fog()
        self._build_sky()
        self._build_terrain()
        self._spawn_vegetation()
        self._spawn_battlefield_props()
        self._spawn_giant_mechs_and_ships()
        self._spawn_mountains_and_structures()
        self._spawn_player_squad()
        self._spawn_allied_team()
        self._randomize_powers()
        self._spawn_enemy_squads()
        self._spawn_capture_flags()
        self._spawn_distant_battlecraft()
        self._spawn_loot()
        self._setup_camera()
        self._build_ui()
        self._setup_tron_overlay_shader()
        self._decorate_ui_for_holoverse()

    def _decorate_ui_for_holoverse(self):
        try:
            self.pause_menu.hide()
        except Exception:
            pass
        try:
            # The source help text says ESC opens a pause menu. In HoloVerse,
            # ESC/0 are reserved for the host return contract.
            if getattr(self, "help_frame", None) is not None:
                self.help_frame.hide()
        except Exception:
            pass

    def _write_adapter_log(self, event: str, extra: dict | None = None):
        if str(os.environ.get("HOLOVERSE_NATIVE_ADAPTER_LOGS", "")).strip().lower() not in {"1", "true", "yes", "on"}:
            return
        try:
            log = self.folder / "logs" / "native_adapter_source.log"
            log.parent.mkdir(parents=True, exist_ok=True)
            payload = {"time": time.strftime("%Y-%m-%d %H:%M:%S"), "event": event, "extra": extra or {}}
            with log.open("a", encoding="utf-8") as fh:
                fh.write(str(payload) + "\n")
        except Exception:
            pass

    def _state_summary(self) -> dict:
        return {
            "characters": len(getattr(self, "characters", []) or []),
            "allies": len(getattr(self, "allies", []) or []),
            "enemies": len(getattr(self, "enemies", []) or []),
            "flags": len(getattr(self, "capture_flags", []) or []),
            "loot": len(getattr(self, "loot_nodes", []) or []),
            "terrain_rows": len(getattr(self, "terrain_heights", []) or []),
        }


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
        self._init_source_state()
        self._entered = True
        self._holoverse_initial_enemy_count = len(getattr(self, "enemies", []) or [])
        self._holoverse_initial_flag_count = len(getattr(self, "capture_flags", []) or [])
        self._write_adapter_log("source_enter", self._state_summary())
        self._set_dimension_ui_visible(False)

    def _sync_host_keys(self):
        host_keys = getattr(self.host, "keys", {}) or {}
        for key in ("w", "a", "s", "d", "shift", "space"):
            self.keys[key] = bool(host_keys.get(key, False)) or key in self._single_frame_keys
        for key in ("q", "mouse1"):
            self.keys[key] = bool(host_keys.get(key, False)) or key in self._single_frame_keys

    def on_host_action(self, action: str) -> bool:
        action = str(action or "").lower()
        if not self._entered:
            return False
        if action in {"toggle_dimension_ui", "dimension_ui", "h"}:
            return self.toggle_dimension_ui()
        if action == "mouse1":
            self._single_frame_keys.add("mouse1")
            try:
                self._basic_attack(self._active(), self.clock.get_frame_time())
            except Exception as exc:
                self._write_adapter_log("attack_failed", {"error": f"{exc.__class__.__name__}: {exc}"})
            return True
        if action in {"q_down", "number_2"}:
            try:
                self._ability(self._active(), self.clock.get_frame_time())
            except Exception as exc:
                self._write_adapter_log("ability_failed", {"error": f"{exc.__class__.__name__}: {exc}"})
            return True
        if action in {"tab", "number_1"}:
            self._cycle_weapon_and_fx()
            return True
        if action == "number_3":
            self._switch_character()
            return True
        if action in {"e_down", "space_down"}:
            self._single_frame_keys.add("space")
            return True
        if action in {"escape", "pause", "menu", "number_0", "return", "return_to_core"}:
            # Let the HoloVerse host perform the real unmount and restore Core.
            return False
        return False

    def update(self, dt: float):
        if not self._entered:
            return
        try:
            self._sync_host_keys()
            self._update_task(self._task_shim)
            self._set_dimension_ui_visible(bool(getattr(self, "dimension_ui_visible", False)))
        except Exception as exc:
            self._write_adapter_log("update_failed", {"error": f"{exc.__class__.__name__}: {exc}", "traceback": traceback.format_exc()[-3000:]})
            raise
        finally:
            self._single_frame_keys.clear()

    def get_holoverse_result(self) -> dict:
        flags = list(getattr(self, "capture_flags", []) or [])
        captured = sum(1 for f in flags if isinstance(f, dict) and str(f.get("owner", "")).lower() == "player")
        required = max(1, len(flags) or int(getattr(self, "_holoverse_initial_flag_count", 0) or 0) or 1)
        enemies = list(getattr(self, "enemies", []) or [])
        initial_enemies = max(len(enemies), int(getattr(self, "_holoverse_initial_enemy_count", len(enemies)) or 0))
        defeated = max(0, initial_enemies - sum(1 for e in enemies if float(getattr(e, "health", 0.0) or 0.0) > 0.0))
        score = captured * 250 + defeated * 35
        if score <= 0 and captured <= 0 and defeated <= 0:
            return {}
        completed = bool(captured >= required)
        signal = "HOLO_CONQUEST_FLAGS_SECURED" if completed else "HOLO_CONQUEST_BATTLEFIELD_SAMPLE"
        return {
            "schema": 1,
            "mode": MODE_TITLE,
            "score_delta": int(score),
            "completed": completed,
            "fragments_recovered": captured,
            "fragments_required": required,
            "signal": signal,
            "memory_fragment": signal,
            "gleebs_response": "Conquest returned a secured territory map." if completed else "Conquest returned partial battlefield pressure data.",
        }

    def exit(self):
        self._write_adapter_log("source_exit", self._state_summary())
        try:
            music = getattr(self, "music", None)
            if music:
                music.stop()
        except Exception:
            pass
        for root_name in (
            "hud_frame", "help_frame", "minimap", "pause_menu", "viewmodel_root",
            "world_root", "sky_root", "fx_root",
        ):
            node = getattr(self, root_name, None)
            try:
                if node is not None and hasattr(node, "remove_node"):
                    node.remove_node()
            except Exception:
                pass
        for node in list(self._owned_roots):
            try:
                if node is not None and hasattr(node, "remove_node") and not node.is_empty():
                    node.remove_node()
            except Exception:
                pass
        try:
            if self._saved_camera_parent is not None and not self._saved_camera_parent.is_empty():
                self.camera.reparent_to(self._saved_camera_parent)
                if self._saved_camera_transform is not None:
                    self.camera.setTransform(self._saved_camera_transform)
        except Exception:
            pass
        try:
            props = WindowProperties()
            props.set_cursor_hidden(False)
            if self.win is not None and hasattr(self.win, "request_properties"):
                self.win.request_properties(props)
        except Exception:
            pass
        self._entered = False

    destroy = exit


def create_mode(host, mode=None, entry_path=None, label=MODE_TITLE):
    return HoloVerseNativeMode(host, mode=mode, entry_path=entry_path, label=label)
