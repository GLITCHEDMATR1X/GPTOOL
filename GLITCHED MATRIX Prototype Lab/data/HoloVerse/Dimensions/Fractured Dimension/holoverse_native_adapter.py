"""Same-window source adapter for Fractured Dimension.

This mounts Fractured Dimension's real Panda3D source into the live HoloVerse
window.  It avoids the hosted child-window wrapper, keeps the artifact route
same-window, and provides the normal ESC/0 return contract.
"""
from __future__ import annotations

import importlib.util
import os
import sys
import time
import traceback
from pathlib import Path

from panda3d.core import ClockObject, NodePath, TransparencyAttrib, Vec3, Vec4, WindowProperties

MODE_TITLE = "Fractured Dimension"
MODE_ID = "fractured_dimension"
MODE_STATUS = "FRACTURED DIMENSION // SOURCE-BACKED SAME-WINDOW // ESC / 0 RETURN TO HOLOVERSE // H SHOWS LEGACY UI"

_SOURCE_MODULE = None
_SOURCE_MODULE_ERROR = ""


def _load_source_module(folder: Path):
    """Load Fractured Dimension/main.py without running run_app()."""
    global _SOURCE_MODULE, _SOURCE_MODULE_ERROR
    if _SOURCE_MODULE is not None:
        return _SOURCE_MODULE
    src = Path(folder) / "main.py"
    if not src.exists():
        raise FileNotFoundError(f"Fractured Dimension source main.py missing: {src}")
    module_name = f"fractured_dimension_source_{int(time.time() * 1000)}"
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


class HoloVerseNativeMode:
    """Fractured Dimension mounted into HoloVerse Core's ShowBase."""

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
        self._dimension_ui_node_names = ('_aspect_root', '_render2d_root')
        self._owned_roots = []
        self._host_key_names = ("w", "a", "s", "d", "shift", "q", "e")
        self._task_shim = _TaskShim()
        self._previous_cwd = None
        self._saved_camera_parent = None
        self._saved_camera_transform = None
        self._mode_root = None
        self._aspect_root = None
        self._render2d_root = None
        self._saved_camera_child_nodes = set()

    # ------------------------------------------------------------------
    # Source boot / compatibility surface
    # ------------------------------------------------------------------
    def _bind_source_methods(self):
        cls = getattr(self.source, "FracturedWorld", None)
        if cls is None:
            raise AttributeError("Fractured Dimension source lacks FracturedWorld")
        skip = {
            "__init__", "accept", "ignore", "ignoreAll", "run", "destroy",
            "userExit", "update",
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
        self.host_render = self.host.render
        self._mode_root = self.host.render.attachNewNode("fractured_dimension_native_root")
        self._aspect_root = self.host.aspect2d.attachNewNode("fractured_dimension_native_aspect2d")
        self._render2d_root = self.host.render2d.attachNewNode("fractured_dimension_native_render2d")
        self._owned_roots.extend([self._mode_root, self._aspect_root, self._render2d_root])

        self.render = self._mode_root
        self.aspect2d = self._aspect_root
        self.render2d = self._render2d_root
        self.camera = self.host.camera
        self.camLens = self.host.camLens
        self.loader = self.host.loader
        self.win = getattr(self.host, "win", None)
        self.taskMgr = getattr(self.host, "taskMgr", None)
        self.sfxManagerList = getattr(self.host, "sfxManagerList", [])
        self.musicManager = getattr(self.host, "musicManager", None)
        self.devices = getattr(self.host, "devices", None)
        self.clock = ClockObject.getGlobalClock()
        self.globalClock = self.clock
        try:
            self.source.globalClock = self.clock
        except Exception:
            pass
        self.accept = getattr(self.host, "accept", lambda *a, **k: None)
        self.ignore = getattr(self.host, "ignore", lambda *a, **k: None)
        self.ignoreAll = getattr(self.host, "ignoreAll", lambda *a, **k: None)
        self.disableMouse = getattr(self.host, "disableMouse", lambda *a, **k: None)
        self.setBackgroundColor = getattr(self.host, "setBackgroundColor", lambda *a, **k: None)
        self.userExit = getattr(self.host, "userExit", lambda *a, **k: None)

    def _init_source_state(self):
        src = self.source
        self.box_model = self.loader.loadModel("models/box")
        self.box_model.clearModelNodes()
        self.box_model.setTwoSided(False)

        self.floor_tex = self._make_glitch_texture(
            "floor", 128,
            bg=(0.02, 0.02, 0.03),
            c1=(0.10, 0.22, 0.30),
            c2=(0.65, 0.18, 0.76),
            lines=(0.16, 0.90, 1.00),
        )
        self.wall_tex = self._make_glitch_texture(
            "wall", 128,
            bg=(0.01, 0.01, 0.02),
            c1=(0.06, 0.08, 0.15),
            c2=(0.48, 0.10, 0.70),
            lines=(0.28, 0.95, 1.00),
        )
        self.shard_tex = self._make_glitch_texture(
            "shard", 64,
            bg=(0.02, 0.01, 0.03),
            c1=(0.12, 0.08, 0.18),
            c2=(0.75, 0.25, 0.90),
            lines=(0.10, 0.95, 0.95),
        )
        self.accent_tex = self._make_glitch_texture(
            "accent", 64,
            bg=(0.03, 0.01, 0.04),
            c1=(0.18, 0.06, 0.25),
            c2=(0.10, 0.95, 1.00),
            lines=(1.00, 0.20, 0.85),
        )
        self.storm_tex = self._make_glitch_texture(
            "storm", 128,
            bg=(0.03, 0.00, 0.00),
            c1=(0.14, 0.01, 0.02),
            c2=(0.52, 0.02, 0.08),
            lines=(1.00, 0.10, 0.12),
        )
        self.lightning_tex = self._make_lightning_texture(128, 320)
        self.overlay_tex = self._make_overlay_texture(256)
        self.red_flash_strength = 0.0
        self.next_lightning_time = 0.8
        self.storm_rng = src.random.Random(55331) if hasattr(src, "random") else __import__("random").Random(55331)
        self.hyper_explosions = []
        self.shrink_deletions = []
        self.fx_rng = src.random.Random(948211) if hasattr(src, "random") else __import__("random").Random(948211)

        self.audio3d = None
        self.loaded_sound_cache = {}
        # Same-window artifact mode keeps audio conservative.  Existing source
        # sound pools are still populated, but 3D audio is optional so headless
        # and host-return paths stay reliable.
        if getattr(self, "sfxManagerList", None):
            try:
                self.audio3d = src.Audio3DManager(self.sfxManagerList[0], self.camera)
                self.audio3d.setDropOffFactor(0.14)
                self.audio3d.setDistanceFactor(1.0)
                self.audio3d.setDopplerFactor(0.25)
            except Exception:
                self.audio3d = None

        self._setup_scene()
        self._setup_player()
        self._setup_weapons()
        self._setup_ui()
        self._setup_audio()
        self._setup_titans()

        self.shield_active = False
        self.shield_charges = 0
        self.shield_time = 0.0
        self.shield_max_time = 6.0
        self.shield_radius = 3.1
        self.keys = {k: False for k in self._host_key_names}
        self.mouse_locked = True
        self.center_x = 0
        self.center_y = 0
        self._refresh_center()
        self._apply_mouse_lock()
        self.chunks = {}
        self.ensure_chunks((0, 0))
        self.time_accum = 0.0
        self.walk_cycle = 0.0
        self.last_speed = 0.0
        self.player_velocity = Vec3(0, 0, 0)
        self.player_knockback = Vec3(0, 0, 0)
        self.active_titan_index = 0

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
            "chunks": len(getattr(self, "chunks", {}) or {}),
            "titans": len(getattr(self, "titans", []) or []),
            "projectiles": len(getattr(self, "weapon_projectiles", []) or []),
            "camera_children": self._camera_child_count(),
            "hyper_fx": len(getattr(self, "hyper_explosions", []) or []),
            "shield_charges": int(getattr(self, "shield_charges", 0) or 0),
        }

    def _camera_child_count(self) -> int:
        try:
            if self.camera is None or self.camera.isEmpty():
                return 0
            return len(list(self.camera.getChildren()))
        except Exception:
            return 0

    def _snapshot_camera_children(self):
        self._saved_camera_child_nodes = set()
        try:
            if self.camera is None or self.camera.isEmpty():
                return
            for child in self.camera.getChildren():
                try:
                    self._saved_camera_child_nodes.add(child.node())
                except Exception:
                    pass
        except Exception:
            pass

    def _remove_new_camera_children(self):
        """Remove viewmodel/camera children created by this mode.

        Fractured builds the dual weapon viewmodel under the shared HoloVerse
        camera.  That node is not below the removable mode root, so it must be
        cleaned explicitly before another dimension mounts.
        """
        try:
            if self.camera is None or self.camera.isEmpty():
                return
            keep = self._saved_camera_child_nodes or set()
            for child in list(self.camera.getChildren()):
                try:
                    if child.node() not in keep:
                        child.removeNode()
                except Exception:
                    pass
        except Exception:
            pass

    def _remove_node_attr(self, attr_name: str):
        node = getattr(self, attr_name, None)
        try:
            if node is not None and hasattr(node, "isEmpty") and not node.isEmpty():
                node.removeNode()
        except Exception:
            pass
        try:
            setattr(self, attr_name, None)
        except Exception:
            pass

    def _stop_and_clear_sounds(self):
        for attr_name in ("music",):
            snd = getattr(self, attr_name, None)
            try:
                if snd is not None:
                    snd.stop()
            except Exception:
                pass
            try:
                setattr(self, attr_name, None)
            except Exception:
                pass

        pools = []
        try:
            pools.extend((getattr(self, "weapon_shot_sounds", {}) or {}).values())
        except Exception:
            pass
        try:
            pools.extend((getattr(self, "loaded_sound_cache", {}) or {}).values())
        except Exception:
            pass
        for pool in pools:
            for snd in list(pool or []):
                try:
                    snd.stop()
                except Exception:
                    pass
                try:
                    if self.audio3d:
                        self.audio3d.detachSound(snd)
                except Exception:
                    pass
        try:
            self.weapon_shot_sounds = {"left": [], "right": []}
        except Exception:
            pass
        try:
            self.loaded_sound_cache = {}
        except Exception:
            pass

    def _cleanup_fractured_runtime_nodes(self):
        # Fired weapon pieces may be reparented away from the camera into the
        # Fractured render root. Remove them explicitly before the root is torn
        # down so stale slots cannot update removed nodes on a later mount.
        for entry in list(getattr(self, "weapon_projectiles", []) or []):
            try:
                proj = entry.get("projectile") if isinstance(entry, dict) else None
                node = getattr(proj, "node", None)
                if node is not None and not node.isEmpty():
                    node.removeNode()
            except Exception:
                pass
            try:
                slot = entry.get("slot") if isinstance(entry, dict) else None
                if slot is not None:
                    slot["projectile"] = None
            except Exception:
                pass
        try:
            self.weapon_projectiles = []
        except Exception:
            pass

        for slot in list(getattr(self, "weapon_detachable_parts", []) or []):
            for key in ("node", "replacement_node"):
                try:
                    node = slot.get(key)
                    if node is not None and not node.isEmpty():
                        node.removeNode()
                    slot[key] = None
                except Exception:
                    pass
            try:
                slot["projectile"] = None
            except Exception:
                pass

        for attr_name in (
            "weapon_root", "left_weapon", "right_weapon",
            "crosshair_root", "shield_root", "player",
            "city_shell", "sky_root", "red_storm_root", "overlay_root",
        ):
            self._remove_node_attr(attr_name)

        for list_name in (
            "weapon_wire_nodes", "weapon_energy_parts", "weapon_detachable_parts",
            "hyper_explosions", "shrink_deletions", "titans",
            "crosshair_reticles", "crosshair_frame_bars", "shield_shells",
        ):
            try:
                setattr(self, list_name, [])
            except Exception:
                pass
        try:
            self.chunks = {}
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
        self.source = _load_source_module(self.folder)
        self._bind_source_methods()
        self._host_resources()
        self._previous_cwd = os.getcwd()
        self._saved_camera_parent = self.camera.getParent()
        self._saved_camera_transform = (self.camera.getPos(), self.camera.getHpr(), self.camera.getScale())
        self._snapshot_camera_children()
        os.chdir(os.fspath(self.folder))
        try:
            self.disableMouse()
        except Exception:
            pass
        try:
            self.render.setTransparency(TransparencyAttrib.MAlpha)
            self.camLens.setNearFar(0.06, 760.0)
            self.camLens.setFov(82)
            self.setBackgroundColor(0.0, 0.0, 0.0, 1.0)
        except Exception:
            pass
        self._init_source_state()
        self._entered = True
        self._write_adapter_log("source_enter", self._state_summary())
        self._set_dimension_ui_visible(False)

    def _sync_host_keys(self):
        host_keys = getattr(self.host, "keys", {}) or {}
        for key in self._host_key_names:
            self.keys[key] = bool(host_keys.get(key, False))

    def on_host_action(self, action: str) -> bool:
        action = str(action or "").lower()
        if not self._entered:
            return False
        if action in {"toggle_dimension_ui", "dimension_ui", "h"}:
            return self.toggle_dimension_ui()
        if action == "mouse1":
            try:
                self.fire_weapon_click()
            except Exception as exc:
                self._write_adapter_log("fire_failed", {"error": f"{exc.__class__.__name__}: {exc}"})
            return True
        if action == "mouse3":
            self.activate_shield()
            return True
        if action in {"tab", "number_1", "q_down"}:
            self.fire_random_weapon_part()
            return True
        if action in {"e_down", "number_2"}:
            self.activate_shield()
            return True
        if action in {"escape", "pause", "menu", "number_0", "return", "return_to_core"}:
            # Let the host perform the real unmount and restore Core camera/HUD.
            return False
        return False

    def update(self, dt: float):
        if not self._entered:
            return
        self._sync_host_keys()
        dt = max(0.0, min(0.033, float(dt or 0.0)))
        self.time_accum += dt

        try:
            if self.win and (self.win.getXSize() // 2 != self.center_x or self.win.getYSize() // 2 != self.center_y):
                self._refresh_center()
            self.handle_mouse_look(dt)
            self.move_player(dt)
            center = self.current_chunk()
            self.ensure_chunks(center)

            for coord, chunk in list(self.chunks.items()):
                chunk.update(dt, self.time_accum, center)
                if getattr(chunk, "dead", False):
                    del self.chunks[coord]

            self.update_red_storm(dt, self.time_accum, center)
            self.update_overlay(self.time_accum)
            self.update_sky_fragments(self.time_accum)
            self.update_city_shell(center, self.time_accum)
            self.update_comets(dt, self.time_accum, center)
            self.update_weapon_viewmodels(dt, self.time_accum)
            self.update_shield(dt, self.time_accum)
            self.update_shrink_deletions(dt, self.time_accum)
            self.update_hyper_explosions(dt, self.time_accum)
            self.update_titans(dt)
            if self.audio3d:
                try:
                    self.audio3d.update()
                except Exception:
                    pass
            self._set_dimension_ui_visible(bool(getattr(self, "dimension_ui_visible", False)))
        except Exception as exc:
            self._write_adapter_log("update_failed", {"error": f"{exc.__class__.__name__}: {exc}"})
            raise

    def get_holoverse_result(self) -> dict:
        titans = list(getattr(self, "titans", []) or [])
        defeated = sum(1 for t in titans if str(getattr(t, "state", "")).lower() == "defeated")
        destroyed_pieces = 0
        total_pieces = 0
        for titan in titans:
            pieces = list(getattr(titan, "pieces", []) or [])
            total_pieces += len(pieces)
            destroyed_pieces += sum(1 for p in pieces if bool(getattr(p, "destroyed", False)))
        score = defeated * 650 + destroyed_pieces * 45
        if score <= 0 and destroyed_pieces <= 0 and defeated <= 0:
            return {}
        required = max(1, len(titans) or 1)
        completed = bool(defeated >= required)
        signal = "FRACTURED_TITAN_ROUTE_STABILIZED" if completed else "FRACTURED_TITAN_SHARD_SAMPLE"
        return {
            "schema": 1,
            "mode": MODE_TITLE,
            "score_delta": int(score),
            "completed": completed,
            "fragments_recovered": defeated if defeated else destroyed_pieces,
            "fragments_required": required if defeated else max(1, total_pieces),
            "signal": signal,
            "memory_fragment": signal,
            "gleebs_response": "Fractured returned a stabilized titan route." if completed else "Fractured returned shard impact telemetry.",
        }

    def exit(self):
        self._write_adapter_log("source_exit_begin", self._state_summary())
        self._entered = False
        self._stop_and_clear_sounds()
        self._cleanup_fractured_runtime_nodes()
        self._remove_new_camera_children()
        try:
            if self.camera is not None and not self.camera.isEmpty():
                parent = self._saved_camera_parent if isinstance(self._saved_camera_parent, NodePath) and not self._saved_camera_parent.isEmpty() else self.host.render
                pos, hpr, scale = self._saved_camera_transform or (Vec3(0, 0, 0), Vec3(0, 0, 0), Vec3(1, 1, 1))
                self.camera.reparentTo(parent)
                self.camera.setPos(pos)
                self.camera.setHpr(hpr)
                self.camera.setScale(scale)
        except Exception:
            try:
                self.camera.reparentTo(self.host.render)
            except Exception:
                pass
        self._remove_new_camera_children()
        for root in reversed(self._owned_roots):
            try:
                if root is not None and not root.isEmpty():
                    root.removeNode()
            except Exception:
                pass
        self._owned_roots.clear()
        try:
            if self.win and hasattr(self.win, "requestProperties"):
                props = WindowProperties()
                props.setCursorHidden(False)
                if hasattr(WindowProperties, "M_absolute"):
                    props.setMouseMode(WindowProperties.M_absolute)
                self.win.requestProperties(props)
        except Exception:
            pass
        try:
            if self._previous_cwd:
                os.chdir(self._previous_cwd)
        except Exception:
            pass
        self._write_adapter_log("source_exit_complete", {"camera_children_after": self._camera_child_count()})

    destroy = exit


def create_mode(host, mode=None, entry_path=None, label=MODE_TITLE):
    try:
        return HoloVerseNativeMode(host, mode=mode, entry_path=entry_path, label=label)
    except Exception:
        traceback.print_exc()
        raise
