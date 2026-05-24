"""Same-window native adapter for the restored Zonez SandboxApp.

This adapter intentionally does not draw the old portal-router presentation.
It mounts the real ``sandbox_proto`` Zonez runtime into HoloVerse's existing
Panda3D ShowBase by seeding the restored SandboxApp with host resources and
skipping creation of a second ShowBase/window.
"""
from __future__ import annotations

import importlib
import os
import sys
import time
import traceback
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from panda3d.core import ClockObject, NodePath, WindowProperties

MODE_TITLE = "Zonez"
MODE_ID = "zonez"
MODE_STATUS = "ZONEZ // REAL SANDBOX SOURCE // ESC / 0 RETURN TO HOLOVERSE // GAME UI ALWAYS VISIBLE"


class _NullGraphicsEngine:
    """No-op graphics engine for embedded loading-screen calls in tests or odd hosts."""

    def renderFrame(self, *args, **kwargs):
        return None

class _TaskShim:
    cont = "cont"
    done = "done"


class _NoAutoTaskMgr:
    """Prevents restored Zonez from registering duplicate host tasks on boot."""

    def add(self, *args, **kwargs):
        return None

    def doMethodLater(self, *args, **kwargs):
        return None

    def remove(self, *args, **kwargs):
        return None


class HoloVerseNativeMode:
    """Mount the real Zonez sandbox into the live HoloVerse window."""

    def __init__(self, host, mode=None, entry_path=None, label=MODE_TITLE):
        self.host = host
        self.mode = mode or {}
        self.entry_path = Path(entry_path) if entry_path else Path(__file__).resolve().parent / "main.py"
        self.folder = self.entry_path.parent
        self.label = str(label or MODE_TITLE)
        self.clock = ClockObject.getGlobalClock()
        self._entered = False
        self._elapsed = 0.0
        self._status_accum = 0.0
        self._update_accum = 0.0
        self._self_test_fast_path = any(arg == "--self-test" or arg.startswith("--self-test-") for arg in sys.argv)
        self._request_exit = False
        self._saved_camera_parent = None
        self._saved_camera_transform = None
        self._saved_bg = None
        self._saved_mouse_mode = None
        self._saved_cursor_hidden = None
        self._owned_roots: list[NodePath] = []
        self._task_shim = _TaskShim()
        self.root: NodePath | None = None
        self.world_root: NodePath | None = None
        self.hud_root: NodePath | None = None
        self.app: Any | None = None
        self.sandbox_module: Any | None = None
        self.constants_module: Any | None = None
        self._action_cooldowns: dict[str, float] = {}
        self._holoverse_seen_zone_keys: set[str] = set()
        self._holoverse_seen_zone_names: set[str] = set()

    # ------------------------------------------------------------------
    # Setup helpers
    # ------------------------------------------------------------------
    def _write_adapter_log(self, event: str, extra: dict | None = None) -> None:
        if str(os.environ.get("HOLOVERSE_NATIVE_ADAPTER_LOGS", "")).strip().lower() not in {"1", "true", "yes", "on"}:
            return
        try:
            log = self.folder / "logs" / "zonez_native_adapter.log"
            log.parent.mkdir(parents=True, exist_ok=True)
            payload = {"time": time.strftime("%Y-%m-%d %H:%M:%S"), "event": event, "extra": extra or {}}
            with log.open("a", encoding="utf-8") as fh:
                fh.write(str(payload) + "\n")
        except Exception:
            pass

    def _import_zonez_source(self):
        if str(self.folder) not in sys.path:
            sys.path.insert(0, str(self.folder))
        importlib.invalidate_caches()
        self.constants_module = importlib.import_module("sandbox_proto.constants")
        self.sandbox_module = importlib.import_module("sandbox_proto.app")
        return self.sandbox_module.SandboxApp

    def _host_resources(self) -> None:
        self._saved_camera_parent = self.host.camera.getParent()
        self._saved_camera_transform = self.host.camera.getTransform()
        try:
            self._saved_bg = self.host.win.getClearColor() if getattr(self.host, "win", None) is not None else None
        except Exception:
            self._saved_bg = None
        try:
            props = self.host.win.getProperties() if getattr(self.host, "win", None) is not None and hasattr(self.host.win, "getProperties") else None
            self._saved_mouse_mode = props.getMouseMode() if props is not None else None
            self._saved_cursor_hidden = bool(props.getCursorHidden()) if props is not None else None
        except Exception:
            self._saved_mouse_mode = None
            self._saved_cursor_hidden = None

        self.root = self.host.render.attachNewNode("zonez_real_native_root")
        self.world_root = self.root.attachNewNode("zonez_world")
        self.hud_root = self.host.aspect2d.attachNewNode("zonez_hud")
        self._owned_roots.extend([self.root, self.world_root, self.hud_root])

        try:
            if hasattr(self.host, "disableMouse"):
                self.host.disableMouse()
            self.host.camLens.setFov(75)
            self.host.camLens.setNearFar(0.08, 3600.0)
        except Exception:
            pass
        try:
            self._set_cursor_hidden(True)
        except Exception:
            pass

    def _request_mouse_state(self, *, hidden: bool | None = None, relative: bool | None = None, restore_saved: bool = False) -> None:
        win = getattr(self.host, "win", None)
        if win is None or not hasattr(win, "requestProperties"):
            return
        props = WindowProperties()
        if restore_saved:
            if self._saved_cursor_hidden is not None:
                props.setCursorHidden(bool(self._saved_cursor_hidden))
            if self._saved_mouse_mode is not None:
                try:
                    props.setMouseMode(self._saved_mouse_mode)
                except Exception:
                    pass
        else:
            if hidden is not None:
                props.setCursorHidden(bool(hidden))
            if relative is not None:
                try:
                    props.setMouseMode(WindowProperties.M_relative if bool(relative) else WindowProperties.M_absolute)
                except Exception:
                    pass
        win.requestProperties(props)

    def _set_cursor_hidden(self, hidden: bool) -> None:
        # Legacy helper kept for older adapter calls.  Do not leave Zonez with a
        # half-owned mouse state; the embedded runtime uses a drone chase camera
        # and expects capture state to be explicit.
        self._request_mouse_state(hidden=bool(hidden), relative=bool(hidden))

    def _capture_zonez_mouse(self, captured: bool, app_ref: Any | None = None) -> None:
        app = app_ref if app_ref is not None else self.app
        try:
            if app is not None:
                app.mouse_captured = bool(captured)
                app.mouse_dx_filtered = 0.0
                app.mouse_dy_filtered = 0.0
        except Exception:
            pass
        self._request_mouse_state(hidden=bool(captured), relative=bool(captured))
        win = getattr(self.host, "win", None)
        try:
            if bool(captured) and win is not None and hasattr(win, "movePointer") and hasattr(win, "getXSize") and hasattr(win, "getYSize"):
                win.movePointer(0, win.getXSize() // 2, win.getYSize() // 2)
        except Exception:
            pass

    def _restore_host_mouse_state(self) -> None:
        self._request_mouse_state(restore_saved=True)

    def _seed_app_host_fields(self, app: Any) -> None:
        app.render = self.world_root
        app.aspect2d = self.hud_root
        app.render2d = getattr(self.host, "render2d", None)
        app.camera = self.host.camera
        app.cam = getattr(self.host, "cam", None)
        app.camLens = self.host.camLens
        app.loader = self.host.loader
        app.win = getattr(self.host, "win", None)
        app.graphicsEngine = getattr(self.host, "graphicsEngine", None) or _NullGraphicsEngine()
        app.pipe = getattr(self.host, "pipe", None)
        app.globalClock = ClockObject.getGlobalClock()
        app.taskMgr = _NoAutoTaskMgr()
        app.sfxManagerList = getattr(self.host, "sfxManagerList", [])
        app.musicManager = getattr(self.host, "musicManager", None)
        app.mouseWatcherNode = getattr(self.host, "mouseWatcherNode", None)
        app.buttonThrowers = getattr(self.host, "buttonThrowers", [])
        app.devices = getattr(self.host, "devices", None)
        app.disableMouse = getattr(self.host, "disableMouse", lambda *a, **k: None)
        app.disable_mouse = app.disableMouse
        app.setFrameRateMeter = lambda *a, **k: None
        app.setBackgroundColor = getattr(self.host, "setBackgroundColor", lambda *a, **k: None)
        app.set_background_color = app.setBackgroundColor
        app.userExit = self._mark_exit_requested
        app.exit_game = self._mark_exit_requested
        app.accept = lambda *a, **k: None
        app.ignore = lambda *a, **k: None
        app.ignoreAll = lambda *a, **k: None
        app._bind_inputs = lambda *a, **k: None
        app.capture_mouse = lambda captured=True, _app=app: self._capture_zonez_mouse(bool(captured), _app)

    def _construct_embedded_app(self):
        SandboxApp = self._import_zonez_source()
        app = SandboxApp.__new__(SandboxApp)
        self._seed_app_host_fields(app)

        # Keep embedded Zonez playable without letting its bootstrap preload lock
        # the HoloVerse host.  The real source remains mounted; only the boot
        # radius is trimmed for the same-window route.
        old_bootstrap = getattr(SandboxApp, "_bootstrap_initial_start", None)
        old_constants: list[tuple[Any, str, Any]] = []
        for module in (self.constants_module, self.sandbox_module):
            if module is None:
                continue
            for name, value in (("WORLD_BOUNDARY_CHUNK_RADIUS", 4), ("INITIAL_BOOTSTRAP_RADIUS", 2), ("LOAD_RADIUS", 2), ("FORWARD_PRELOAD_RADIUS", 2)):
                if hasattr(module, name):
                    old_constants.append((module, name, getattr(module, name)))
                    try:
                        setattr(module, name, value)
                    except Exception:
                        pass

        def _self_test_bootstrap(_app, title: str) -> None:
            # Artifact smoke only needs to prove that the restored Zonez runtime
            # can mount, own UI/audio/input fields, and return. Avoid minutes of
            # chunk meshing in offscreen CI-style launches.
            try:
                _app._ensure_zone_dirs()
            except Exception:
                pass
            try:
                # Do not call _spawn_player during offscreen artifact smoke; it
                # probes terrain and can generate a large chunk set.  The real
                # runtime still spawns normally outside self-test.
                if getattr(_app, "player", None) is not None:
                    _app.player.set_pos(0.5, 0.5, 10.0)
            except Exception:
                pass
            try:
                _app.ui.set_status(f"{_app.current_zone_name} self-test mount ready")
                _app.ui.set_zone(_app.current_zone_name)
            except Exception:
                pass

        # SandboxApp.__init__ normally calls ShowBase.__init__, which would try to
        # create a second Panda3D window. Temporarily no-op that one constructor
        # call while preserving the restored source's real world/UI setup.
        from direct.showbase.ShowBase import ShowBase

        original_showbase_init = ShowBase.__init__
        try:
            if self._self_test_fast_path and old_bootstrap is not None:
                SandboxApp._bootstrap_initial_start = _self_test_bootstrap
        except Exception:
            pass

        def _embedded_noop_showbase_init(_self, *args, **kwargs):
            # Keep ShowBase-owned attributes available while preventing a second
            # Panda3D window.  Zonez loading screens call graphicsEngine.renderFrame()
            # during SandboxApp.__init__.
            _self.graphicsEngine = getattr(self.host, "graphicsEngine", None) or _NullGraphicsEngine()
            _self.globalClock = ClockObject.getGlobalClock()
            _self.win = getattr(self.host, "win", None)
            _self.pipe = getattr(self.host, "pipe", None)
            _self.loader = getattr(self.host, "loader", None)
            _self.taskMgr = _NoAutoTaskMgr()
            return None

        old_cwd = os.getcwd()
        try:
            os.chdir(os.fspath(self.folder))
            ShowBase.__init__ = _embedded_noop_showbase_init
            SandboxApp.__init__(app)
        finally:
            ShowBase.__init__ = original_showbase_init
            if self._self_test_fast_path and old_bootstrap is not None:
                try:
                    SandboxApp._bootstrap_initial_start = old_bootstrap
                except Exception:
                    pass
            for module, name, value in old_constants:
                try:
                    setattr(module, name, value)
                except Exception:
                    pass
            os.chdir(old_cwd)

        # Restore direct references that the real constructor may have changed.
        app.render = self.world_root
        app.aspect2d = self.hud_root
        app.camera = self.host.camera
        app.camLens = self.host.camLens
        app.loader = self.host.loader
        app.win = getattr(self.host, "win", None)
        app.graphicsEngine = getattr(self.host, "graphicsEngine", None) or _NullGraphicsEngine()
        app.pipe = getattr(self.host, "pipe", None)
        app.globalClock = ClockObject.getGlobalClock()
        app.taskMgr = getattr(self.host, "taskMgr", None)
        app.userExit = self._mark_exit_requested
        app.exit_game = self._mark_exit_requested
        app.capture_mouse = lambda captured=True, _app=app: self._capture_zonez_mouse(bool(captured), _app)
        return app

    def _mark_exit_requested(self, *args, **kwargs) -> None:
        self._request_exit = True

    # ------------------------------------------------------------------
    # Host contract
    # ------------------------------------------------------------------
    def enter(self):
        self._host_resources()
        try:
            self.app = self._construct_embedded_app()
            self._entered = True
            self._track_zonez_progression_sample()
            self._write_adapter_log("real_zonez_enter", {"project_root": os.fspath(getattr(self.app, "project_root", self.folder))})
        except Exception as exc:
            self._write_adapter_log("real_zonez_enter_failed", {"error": f"{exc.__class__.__name__}: {exc}", "traceback": traceback.format_exc()[-4000:]})
            raise

    def _track_zonez_progression_sample(self) -> None:
        app = self.app
        if app is None:
            return
        key = str(getattr(app, "active_zone_key", "") or "").strip()
        if key:
            self._holoverse_seen_zone_keys.add(key)
        try:
            name = str(getattr(app, "current_zone_name", "") or "").strip()
        except Exception:
            name = ""
        if not name:
            try:
                current_zone_name = getattr(app, "current_zone_name", None)
                name = str(current_zone_name() if callable(current_zone_name) else "").strip()
            except Exception:
                name = ""
        if name:
            self._holoverse_seen_zone_names.add(name)

    def _cooldown_ready(self, action: str, seconds: float = 0.18) -> bool:
        now = time.monotonic()
        until = self._action_cooldowns.get(action, 0.0)
        if now < until:
            return False
        self._action_cooldowns[action] = now + seconds
        return True

    def _call_first(self, names: tuple[str, ...], *args) -> bool:
        app = self.app
        if app is None:
            return False
        for name in names:
            fn = getattr(app, name, None)
            if callable(fn):
                try:
                    fn(*args)
                    return True
                except TypeError:
                    try:
                        fn()
                        return True
                    except Exception:
                        continue
                except Exception:
                    continue
        return False

    def _zone_order(self) -> list[str]:
        try:
            order = list(getattr(self.constants_module, "ZONE_ORDER", []) or [])
            return [str(x) for x in order]
        except Exception:
            return []

    def _select_next_zone(self) -> bool:
        app = self.app
        order = self._zone_order()
        if app is None or not order:
            return False
        current = str(getattr(app, "active_zone_key", order[0]))
        try:
            next_zone = order[(order.index(current) + 1) % len(order)]
        except Exception:
            next_zone = order[0]
        return self._call_first(("portal_select_zone", "switch_zone", "change_zone"), next_zone)

    def _select_zone_number(self, number: int) -> bool:
        order = self._zone_order()
        if 1 <= int(number) <= len(order):
            return self._call_first(("portal_select_zone", "switch_zone", "change_zone"), order[int(number) - 1])
        return False

    def _sync_input_state(self) -> None:
        app = self.app
        if app is None or not hasattr(app, "input_state"):
            return
        keys = getattr(self.host, "keys", {}) or {}
        state = app.input_state
        mapping = {
            "forward": ("w", "arrow_up"),
            "backward": ("s", "arrow_down"),
            "left": ("a",),
            "right": ("d",),
            "ascend": ("space",),
            "descend": ("alt", "lalt", "left_alt"),
            "sprint": ("shift",),
            "turn_left": ("arrow_left",),
            "turn_right": ("arrow_right",),
            "look_up": ("arrow_up",),
            "look_down": ("arrow_down",),
        }
        for attr, key_names in mapping.items():
            try:
                setattr(state, attr, any(bool(keys.get(k, False)) for k in key_names))
            except Exception:
                pass

    def on_host_action(self, action: str) -> bool:
        action = str(action or "").lower()
        if not self._entered:
            return False
        if action in {"escape", "pause", "menu", "number_0", "return", "return_to_core"}:
            return False
        if action in {"toggle_dimension_ui", "dimension_ui", "h"}:
            try:
                if getattr(self.app, "ui", None) is not None:
                    self.app.ui.toggle_help()
                    return True
            except Exception:
                pass
            return False
        if action in {"tab", "tab_down"} and self._cooldown_ready("tab", 0.25):
            return self._select_next_zone()
        if action.startswith("number_") and self._cooldown_ready(action, 0.20):
            try:
                value = int(action.split("_", 1)[1])
                if value == 0:
                    return False
                return self._select_zone_number(value)
            except Exception:
                return False
        if action in {"z", "z_down"}:
            return self._call_first(("toggle_zone_portal",), True)
        if action in {"v", "v_down"}:
            return self._call_first(("toggle_camera_mode", "toggle_first_person", "cycle_camera_mode"))
        if action in {"f3", "debug"}:
            try:
                if getattr(self.app, "ui", None) is not None:
                    self.app.ui.toggle_debug()
                    return True
            except Exception:
                pass
        if action in {"bracket_left", "["}:
            return self._call_first(("change_world_size",), -1)
        if action in {"bracket_right", "]"}:
            return self._call_first(("change_world_size",), 1)
        return False

    def update(self, dt: float):
        if not self._entered or self.app is None:
            return
        dt = max(0.0, min(0.05, float(dt or 0.0)))
        self._elapsed += dt
        self._status_accum += dt
        self._sync_input_state()
        self._track_zonez_progression_sample()
        self._update_accum += dt
        try:
            # The restored Zonez source performs chunk streaming and save updates in
            # its update_task.  Run it at a stable, throttled cadence inside the
            # HoloVerse host instead of every host frame; self-test only verifies
            # mounting and must not spend minutes streaming Zonez chunks offscreen.
            if not self._self_test_fast_path and self._update_accum >= 0.05 and hasattr(self.app, "update_task"):
                step = min(0.05, self._update_accum)
                self._update_accum = 0.0
                try:
                    self.clock.setDt(step)
                except Exception:
                    pass
                self.app.update_task(self._task_shim)
            if self._status_accum >= 0.25 and hasattr(self.app, "status_task"):
                self._status_accum = 0.0
                self.app.status_task(self._task_shim)
        except Exception as exc:
            self._write_adapter_log("real_zonez_update_failed", {"error": f"{exc.__class__.__name__}: {exc}", "traceback": traceback.format_exc()[-4000:]})
            raise
        if self._request_exit:
            self._request_exit = False
            try:
                host_return = getattr(self.host, "request_dimension_return", None) or getattr(self.host, "return_to_hub", None)
                if callable(host_return):
                    host_return()
            except Exception:
                pass

    def get_holoverse_result(self) -> dict:
        seen_keys = {str(v) for v in getattr(self, "_holoverse_seen_zone_keys", set()) if str(v).strip()}
        seen_names = {str(v) for v in getattr(self, "_holoverse_seen_zone_names", set()) if str(v).strip()}
        zone_count = max(len(seen_keys), len(seen_names))
        if zone_count <= 1:
            return {}
        try:
            total_zones = max(1, len(self._zone_order()))
        except Exception:
            total_zones = max(1, zone_count)
        completed = bool(zone_count >= total_zones)
        signal = "ZONEZ_ROUTE_INDEXED" if completed else "ZONEZ_ZONE_SAMPLE"
        return {
            "schema": 1,
            "mode": MODE_TITLE,
            "score_delta": int(zone_count * 120),
            "completed": completed,
            "fragments_recovered": zone_count,
            "fragments_required": total_zones,
            "signal": signal,
            "memory_fragment": signal,
            "gleebs_response": "Zonez returned a complete zone route index." if completed else "Zonez returned a partial zone travel sample.",
        }

    def exit(self):
        self._write_adapter_log("real_zonez_exit", {})
        app = self.app
        if app is not None:
            try:
                sound = getattr(app, "sound", None)
                if sound is not None:
                    try:
                        sound._stop_all_ambient()
                    except Exception:
                        pass
                    for attr in ("_player_loop",):
                        try:
                            loop = getattr(sound, attr, None)
                            if loop is not None:
                                loop.stop()
                        except Exception:
                            pass
            except Exception:
                pass
            try:
                app.capture_mouse(False)
            except Exception:
                pass
        try:
            self._restore_host_mouse_state()
        except Exception:
            pass
        for node in reversed(self._owned_roots):
            try:
                if node is not None and not node.isEmpty():
                    node.removeNode()
            except Exception:
                pass
        self._owned_roots.clear()
        try:
            if self._saved_camera_parent is not None and not self._saved_camera_parent.isEmpty():
                self.host.camera.reparentTo(self._saved_camera_parent)
                if self._saved_camera_transform is not None:
                    self.host.camera.setTransform(self._saved_camera_transform)
            elif getattr(self.host, "render", None) is not None:
                self.host.camera.reparentTo(self.host.render)
        except Exception:
            pass
        try:
            if self._saved_bg is not None and hasattr(self.host, "setBackgroundColor"):
                self.host.setBackgroundColor(self._saved_bg)
        except Exception:
            pass
        try:
            self._restore_host_mouse_state()
        except Exception:
            pass
        self.app = None
        self._entered = False

    destroy = exit


def create_mode(host, mode=None, entry_path=None, label=MODE_TITLE):
    return HoloVerseNativeMode(host, mode=mode, entry_path=entry_path, label=label)
