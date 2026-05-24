"""Same-window source adapter for Etch-Line.

Pass 56 finishes Etch-Line's artifact route without replacing it with a
placeholder.  The adapter imports Etch-Line's real ``main.py`` systems and
mounts the noir city, chunks, enemies, weapons, HUD, config, generated ink
texture, and update loop into the live HoloVerse Panda3D ShowBase.
"""
from __future__ import annotations

import importlib.util
import os
import sys
import time
import traceback
from pathlib import Path

from panda3d.core import AntialiasAttrib, ClockObject, Filename, TransparencyAttrib, Vec2, Vec3, WindowProperties, TexturePool

MODE_TITLE = "Holo Campaign"
MODE_ID = "holo_campaign"
MODE_STATUS = "HOLO CAMPAIGN // ARCHIVE MISSION SAME-WINDOW // ESC / 0 RETURN TO HOLOVERSE // H SHOWS LEGACY UI"

_SOURCE_MODULE = None
_SOURCE_MODULE_ERROR = ""


def _load_source_module(folder: Path):
    """Load Etch-Line/main.py as source code without running main()."""
    global _SOURCE_MODULE, _SOURCE_MODULE_ERROR
    if _SOURCE_MODULE is not None:
        return _SOURCE_MODULE
    src = Path(folder) / "main.py"
    if not src.exists():
        raise FileNotFoundError(f"Etch-Line source main.py missing: {src}")
    module_name = f"etchline_source_{int(time.time() * 1000)}"
    spec = importlib.util.spec_from_file_location(module_name, src)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not create import spec for {src}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        _SOURCE_MODULE_ERROR = f"{exc.__class__.__name__}: {exc}"
        raise
    _SOURCE_MODULE = module
    return module


class HoloVerseNativeMode:
    """Etch-Line's original source systems mounted into HoloVerse Core."""

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
        self._dimension_ui_node_names = ('hud_root', 'crosshair', 'menu_root', 'work_root', 'mission_overlay_root')
        self._chunk_accum = 0.0
        self._owned_roots = []
        self._host_key_names = ("w", "a", "s", "d", "shift", "space")

    # ------------------------------------------------------------------
    # Source boot / compatibility surface
    # ------------------------------------------------------------------
    def _bind_source_methods(self):
        cls = getattr(self.source, "EtchlineGame", None)
        if cls is None:
            raise AttributeError("Etch-Line source lacks EtchlineGame")
        skip = {
            "__init__", "setup_window", "setup_input", "setup_gamepad",
            "on_device_connect", "on_device_disconnect", "self_test_exit",
            "update_task", "chunk_task", "userExit",
        }
        for name, value in cls.__dict__.items():
            if name.startswith("__") or name in skip:
                continue
            if callable(value):
                try:
                    setattr(self, name, value.__get__(self, self.__class__))
                except Exception:
                    pass

    def _host_resources(self):
        self.render = self.host.render
        self.aspect2d = self.host.aspect2d
        self.camera = self.host.camera
        self.camLens = self.host.camLens
        self.loader = self.host.loader
        self.win = getattr(self.host, "win", None)
        self.taskMgr = getattr(self.host, "taskMgr", None)
        self.devices = getattr(self.host, "devices", None)
        self.clock = ClockObject.getGlobalClock()
        self.accept = getattr(self.host, "accept", lambda *a, **k: None)
        self.ignore = getattr(self.host, "ignore", lambda *a, **k: None)
        self.ignoreAll = getattr(self.host, "ignoreAll", lambda *a, **k: None)
        self.attachInputDevice = getattr(self.host, "attachInputDevice", lambda *a, **k: None)
        self.detachInputDevice = getattr(self.host, "detachInputDevice", lambda *a, **k: None)
        self.disableMouse = getattr(self.host, "disableMouse", lambda *a, **k: None)
        self.setBackgroundColor = getattr(self.host, "setBackgroundColor", lambda *a, **k: None)

    def _init_source_state(self):
        src = self.source
        try:
            src.ensure_dirs()
            src.install_crash_reporter()
            src.generate_blotch_texture_file()
        except Exception:
            pass

        self.game_cfg = src.load_or_create_config()
        # Keep same-window artifact entry bounded so the hidden HoloVerse hub and
        # Etch-Line city do not overdraw too much at once.
        self.game_cfg.active_chunk_radius = min(int(getattr(self.game_cfg, "active_chunk_radius", 4)), 3)
        self.game_cfg.enemy_chunk_radius = min(int(getattr(self.game_cfg, "enemy_chunk_radius", 3)), 2)
        self.game_cfg.max_view_distance = min(float(getattr(self.game_cfg, "max_view_distance", 620.0)), 560.0)
        self.game_cfg.max_enemies = min(int(getattr(self.game_cfg, "max_enemies", 72)), 56)
        self.game_cfg.max_tracers = min(int(getattr(self.game_cfg, "max_tracers", 96)), 72)
        self.game_cfg.max_blotches = min(int(getattr(self.game_cfg, "max_blotches", 80)), 42)
        self.game_cfg.show_help = True
        self.game_cfg.signal_fragments_required = min(max(1, int(getattr(self.game_cfg, "signal_fragments_required", 4))), 4)
        self.game_cfg.objective_wave_size = min(max(1, int(getattr(self.game_cfg, "objective_wave_size", 5))), 5)

        self._shutting_down = False
        self._blotch_texture = None
        try:
            if getattr(src, "BLOTCH_TEXTURE", None) is not None and src.BLOTCH_TEXTURE.exists():
                self._blotch_texture = self.loader.loadTexture(Filename.fromOsSpecific(os.fspath(src.BLOTCH_TEXTURE)))
        except Exception as exc:
            self._write_adapter_log("texture_load_failed", {"error": f"{exc.__class__.__name__}: {exc}"})
            self._blotch_texture = None

        self.elapsed = 0.0
        self.day_phase = 0.0
        self.health = int(getattr(self.game_cfg, "default_health", 100))
        self.vertical_speed = 0.0
        self.on_ground = True
        self.menu_open = False
        self.hud_visible = True
        self.workstation_visible = False
        self.help_visible = bool(getattr(self.game_cfg, "show_help", True))
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
        self.player_pos = Vec3(0, 0, float(getattr(self.game_cfg, "player_height", 1.75)))
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
        self.pitch = -4.0
        self.yaw = 0.0

    def _remember_roots(self):
        for name in (
            "city_root", "entity_root", "effect_root", "hud_root", "crosshair",
            "menu_root", "work_root", "mission_root", "mission_overlay_root",
        ):
            node = getattr(self, name, None)
            if node is not None:
                self._owned_roots.append(node)

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
        try:
            self.disableMouse()
        except Exception:
            pass
        try:
            self.render.setAntialias(AntialiasAttrib.MLine)
            self.render.setTransparency(TransparencyAttrib.MAlpha)
            self.camLens.setNearFar(0.06, float(getattr(self.game_cfg, "max_view_distance", 560.0)))
            self.camLens.setFov(82)
            self.setBackgroundColor(1, 1, 1)
        except Exception:
            pass
        self.setup_scene()
        self.setup_ui()
        try:
            self.help_text["text"] = "WASD move  Shift sprint  LMB fire/recover  TAB weapon  E workstation  ESC/0 return to HoloVerse"
        except Exception:
            pass
        self.generate_next_weapon(first=True)
        self.camera.setPos(self.player_pos)
        self.camera.setHpr(self.yaw, self.pitch, 0)
        self.refresh_ui_text()
        self.refresh_workstation_text()
        self._set_dimension_ui_visible(False)
        self._remember_roots()
        self._entered = True
        self._write_adapter_log("source_enter", self._state_summary())

    def get_holoverse_result(self) -> dict:
        method = getattr(self, "get_holoverse_result", None)
        # If the Etch-Line source method was rebound onto this adapter, call the
        # class implementation directly through the loaded source to avoid this
        # adapter wrapper recursing into itself.
        try:
            src_cls = getattr(getattr(self, "source", None), "EtchlineGame", None)
            src_method = getattr(src_cls, "get_holoverse_result", None) if src_cls is not None else None
            if callable(src_method):
                return dict(src_method(self) or {})
        except Exception:
            pass
        return dict(getattr(self, "holoverse_result", {}) or {})

    def _state_summary(self) -> dict:
        return {
            "chunks": len(getattr(self, "chunks", {}) or {}),
            "enemies": sum(1 for e in getattr(self, "enemies", []) if not getattr(e, "dead", False)),
            "tracers": len(getattr(self, "tracers", []) or []),
            "blotches": len(getattr(self, "blotches", []) or []),
            "signal_effects": len(getattr(self, "signal_effects", []) or []),
            "combat_effects": len(getattr(self, "combat_effects", []) or []),
            "texture_loaded": bool(getattr(self, "_blotch_texture", None) is not None),
            "weapon": str(getattr(getattr(self, "current_weapon", None), "name", "")),
            "score": int(getattr(self, "score", 0) or 0),
            "signal_fragments_recovered": int(getattr(self, "signal_fragments_recovered", 0) or 0),
            "objective_complete": bool(getattr(self, "objective_complete", False)),
        }

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
            self.fire_down = True
            self.fire_hold = True
            try:
                self.shoot()
                self.fire_cooldown = max(float(getattr(self.current_weapon, "fire_interval", 0.15) or 0.15), 0.03) if self.current_weapon else 0.15
            finally:
                self.fire_hold = False
                self.fire_down = False
            return True
        if action in {"tab", "q_down", "number_1"}:
            self.generate_next_weapon()
            return True
        if action in {"number_2"}:
            self.generate_previous_weapon()
            return True
        if action in {"e_down"}:
            self.toggle_workstation()
            return True
        if action in {"space_down"}:
            self.keys["space"] = True
            return True
        if action in {"escape", "pause", "menu", "number_0", "return", "return_to_core"}:
            # Return False so the HoloVerse host performs the actual unmount and
            # restores Core camera/input/HUD state through return_from_native_mode.
            return False
        return False

    def update(self, dt: float):
        if not self._entered:
            return
        dt = max(0.0, min(0.033, float(dt or 0.0)))
        self._sync_host_keys()
        self.elapsed += dt
        self._chunk_accum += dt
        self.update_palette(dt)
        self.update_player(dt)
        self.update_fire(dt)
        self.update_enemies(dt)
        self.update_effects(dt)
        self.update_feedback_overlays(dt)
        if self._chunk_accum >= 0.25:
            self._chunk_accum = 0.0
            self.generate_city_around_player()
            self.enforce_chunk_budget()
            self.prune_runtime_entities()
        self.recolor_scene()
        self.refresh_ui_text()
        self.refresh_workstation_text()
        if self.weapon_banner_time > 0.0 and self.current_weapon:
            self.weapon_banner_time -= dt
            self.center_text["text"] = f"{self.current_weapon.name}"
        elif getattr(self, "objective_banner_time", 0.0) > 0.0:
            self.center_text["text"] = str(getattr(self, "objective_banner", ""))
        else:
            self.center_text["text"] = MODE_STATUS
        try:
            self.holoverse_result = self.get_holoverse_result()
        except Exception:
            pass
        self._set_dimension_ui_visible(bool(getattr(self, "dimension_ui_visible", False)))

    def _safe_cleanup_runtime(self):
        """Clean Etch-Line without touching HoloVerse host tasks/events.

        The standalone Etch-Line cleanup removes generic task names such as
        ``update-task``.  In same-window mode those names belong to HoloVerse,
        so calling the source cleanup can freeze the hub after returning.  This
        cleanup removes only Etch-Line-owned nodes/entities/textures.
        """
        self._shutting_down = True
        for enemy in list(getattr(self, "enemies", []) or []):
            try:
                enemy.dispose()
            except Exception:
                pass
        for tracer in list(getattr(self, "tracers", []) or []):
            try:
                tracer.dispose()
            except Exception:
                pass
        for blotch in list(getattr(self, "blotches", []) or []):
            try:
                blotch.dispose()
            except Exception:
                pass
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
        try:
            self.enemies.clear()
        except Exception:
            self.enemies = []
        try:
            self.tracers.clear()
        except Exception:
            self.tracers = []
        try:
            self.blotches.clear()
        except Exception:
            self.blotches = []
        try:
            self.signal_effects.clear()
        except Exception:
            self.signal_effects = []
        try:
            self.combat_effects.clear()
        except Exception:
            self.combat_effects = []
        for np in list((getattr(self, "chunks", {}) or {}).values()):
            try:
                if np is not None and not np.isEmpty():
                    np.removeNode()
            except Exception:
                pass
        for collection_name in ("chunks", "chunk_obstacles", "chunk_enemy_seeds"):
            try:
                getattr(self, collection_name).clear()
            except Exception:
                setattr(self, collection_name, {})
        for node in reversed(list(getattr(self, "_owned_roots", []) or [])):
            try:
                if node is not None and hasattr(node, "isEmpty") and not node.isEmpty():
                    node.removeNode()
            except Exception:
                pass
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
        try:
            if getattr(self, "extraction_node", None) is not None:
                self.extraction_node.dispose()
        except Exception:
            pass
        self.extraction_node = None
        for attr in ("hud_root", "mission_overlay_root", "crosshair", "menu_root", "work_root", "mission_root", "city_root", "entity_root", "effect_root"):
            node = getattr(self, attr, None)
            try:
                if node is not None and hasattr(node, "isEmpty") and not node.isEmpty():
                    node.removeNode()
            except Exception:
                pass
        try:
            if getattr(self, "render", None) is not None:
                self.render.clearFog()
        except Exception:
            pass

    def exit(self):
        self._write_adapter_log("source_exit_begin", self._state_summary())
        try:
            self._safe_cleanup_runtime()
        except Exception as exc:
            self._write_adapter_log("safe_cleanup_runtime_failed", {"error": f"{exc.__class__.__name__}: {exc}"})
            for node in reversed(self._owned_roots):
                try:
                    if node is not None and not node.isEmpty():
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
        self._owned_roots.clear()
        self._entered = False
        self._write_adapter_log("source_exit_complete", {})

    destroy = exit


def create_mode(host, mode=None, entry_path=None, label=MODE_TITLE):
    try:
        return HoloVerseNativeMode(host, mode=mode, entry_path=entry_path, label=label)
    except Exception:
        # Let HoloVerse's launcher catch and log the real adapter failure; do not
        # silently replace Etch-Line with a placeholder scene.
        traceback.print_exc()
        raise
