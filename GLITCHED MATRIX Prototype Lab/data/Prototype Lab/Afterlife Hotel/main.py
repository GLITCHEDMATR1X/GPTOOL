
from __future__ import annotations

import json
import importlib.util
import math
import os
import traceback
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from random import Random
from typing import Any, Dict, List, Optional, Set, Tuple

from direct.gui.DirectGui import DirectButton, DirectFrame, DirectLabel, DirectSlider
from direct.gui.OnscreenText import OnscreenText
from direct.showbase.ShowBase import ShowBase
from direct.task import Task

try:
    from direct.filter.CommonFilters import CommonFilters
except Exception:
    CommonFilters = None

from panda3d.core import (
    AmbientLight,
    CardMaker,
    DirectionalLight,
    Filename,
    Fog,
    NodePath,
    PNMImage,
    PointLight,
    TextNode,
    Texture,
    TextureStage,
    TransparencyAttrib,
    Vec3,
    Vec4,
    WindowProperties,
)



# ----------------------------
# Tunables
# ----------------------------
CELL = 2.55
MODULE_CELLS = 12
MODULE_SIZE = CELL * MODULE_CELLS
LOAD_RADIUS = 2
UNLOAD_RADIUS = 4

WALL_H = 4.4
PLAYER_EYE_H = 1.62
PLAYER_RADIUS = 0.28
COLLISION_SHRINK = 0.07

MOVE_SPEED = 4.9
WATER_MOVE_MULT = 0.68
SPRINT_MULT = 1.42
FAST_LOCK_MULT = 1.88
MOUSE_SENS = 0.32
NIGHTVISION_DURATION = 3.0
NIGHTVISION_COOLDOWN = 3.0
SETTINGS_FILE = "poolrooms_settings.json"

SHADOW_NPC_HEIGHT = 2.22
SHADOW_NPC_WIDTH = 0.94
SHADOW_NPC_MIN_DIST = 14.0
SHADOW_NPC_MAX_DIST = MODULE_SIZE * max(2, LOAD_RADIUS)
SHADOW_NPC_HIT_RADIUS = 0.72
SHADOW_NPC_DARK_RADIUS = 7.5
SHADOW_NPC_AUDIO_RADIUS = 28.0


DECK_Z = 0.0
WATER_FLOOR_Z = -0.88
WATER_SURFACE_Z = 0.12
COPING_H = 0.10

FOG_COLOR = Vec4(0.50, 0.58, 0.54, 1.0)
FOG_START = 6.5
FOG_END = 46.0

SOLID = 0
DECK = 1
WATER = 2

HUB_LEVEL = 0
HUB_NAME = "Poltergeist Hotel"
HUB_DOOR_USE_RADIUS = 2.35
LEVEL_RETURN_TIME = 60.0

STYLE_NAMES = {
    0: "Grand Hall",
    1: "Maze Canals",
    2: "Arcade Basin",
    3: "Sanctum",
    4: "Gallery",
    5: HUB_NAME,
}


# ----------------------------
# Helpers
# ----------------------------
def clamp(v: float, lo: float, hi: float) -> float:
    return lo if v < lo else hi if v > hi else v


def now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def hash_u32(*vals: int) -> int:
    h = 2166136261
    for v in vals:
        h = (h ^ (int(v) & 0xFFFFFFFF)) * 16777619
        h &= 0xFFFFFFFF
    return h


def install_crash_logger() -> None:
    logs_dir = Path(__file__).resolve().parent / "crash_logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    def excepthook(exc_type, exc, tb):
        try:
            fname = logs_dir / f"crash_{now_stamp()}.txt"
            with open(fname, "w", encoding="utf-8") as f:
                f.write("Poolrooms Art Prototype — Crash Log\n")
                f.write("=" * 72 + "\n\n")
                f.write(f"Time: {datetime.now().isoformat()}\n")
                f.write(f"Python: {os.sys.version}\n")
                f.write(f"Platform: {os.name} / {os.sys.platform}\n\n")
                f.write("Traceback:\n")
                f.write("".join(traceback.format_exception(exc_type, exc, tb)))
            print(f"[CrashLog] Wrote: {fname}")
        except Exception as log_exc:
            print("[CrashLog] Failed:", log_exc)
        traceback.print_exception(exc_type, exc, tb)

    os.sys.excepthook = excepthook


@dataclass
class ModuleData:
    grid: List[List[int]]
    style_id: int


@dataclass
class ModuleChunk:
    mx: int
    my: int
    root: NodePath
    water_root: NodePath
    style_name: str


class PoolroomsArtGame(ShowBase):
    def __init__(self) -> None:
        super().__init__()
        self.disableMouse()

        self.base_dir = Path(__file__).resolve().parent
        self.assets_root = self.base_dir / "assets"
        self.halls_assets_root = self.assets_root / "halls"
        self.levels_root = self.base_dir / "levels"
        self.levels_assets_root = self.levels_root
        self.shared_sfx_root = self.assets_root / "sfx"
        self.weapon_sfx_root = self.shared_sfx_root / "weapons" / "dark_rifle"
        self.transition_sfx_root = self.halls_assets_root / "sfx" / "transitions"
        self._configure_asset_context(HUB_LEVEL)
        self.config_path = self.base_dir / SETTINGS_FILE
        self.settings = self._load_settings()
        self.asset_overrides: Dict[str, str] = dict(self.settings.get("asset_overrides", {}))
        self.asset_sources: Dict[str, str] = {}
        self.asset_labels: Dict[str, DirectLabel] = {}
        self.value_labels: Dict[str, DirectLabel] = {}
        self.sliders: Dict[str, DirectSlider] = {}
        self._syncing_ui = False

        self.menu_open = False
        self.mouse_captured = False
        self.window_foreground = True
        self.is_fullscreen = bool(self.settings.get("fullscreen", False))
        self.help_on = bool(self.settings.get("help_on", True))
        self.hud_visible = False
        self.relative_mouse_mode = False
        self._ignore_mouse_frames = 0
        self.esc_quit_armed = False
        self.ambience_t = 0.0
        self.toast_t = 0.0
        self.nightvision_on = False
        self.nightvision_time_left = 0.0
        self.nightvision_cooldown_left = 0.0
        self.speed_lock = False
        self.frame_counter = 0
        self.ui_refresh_t = 0.0
        self.shots_fired = 0
        self.active_projectiles: List[Dict[str, Any]] = []

        self.deck_surfaces: List[NodePath] = []
        self.water_surfaces: List[NodePath] = []
        self.water_surface_cards: List[NodePath] = []
        self.deck_reflection_overlays: List[Tuple[NodePath, float, float]] = []
        self.water_reflection_overlays: List[Tuple[NodePath, float, float]] = []
        self.water_detail_overlays: List[Tuple[NodePath, float, float]] = []
        self.deck_gloss_overlays: List[Tuple[NodePath, float, float]] = []

        self.filters = None
        self.filter_backend = "none"
        self.music_loop = None
        self.shadow_music_loop = None
        self.shadow_music_mix = 0.0
        self.weapon_sfx: Dict[str, Any] = {}
        self.transition_sfx = None
        self.audio_debug: Dict[str, str] = {}
        self.runtime_random = Random()
        self.shadow_npc_root: Optional[NodePath] = None
        self.shadow_npc_base_alpha = 0.58
        self.shadow_npc_spawn_count = 0
        self.shadow_darkness_mix = 0.0
        self.current_level = HUB_LEVEL
        self.level_entries: Dict[int, Dict[str, Any]] = {}
        self.level_registry_signature: Tuple[str, ...] = ()
        self.level_cycle_queue: List[int] = []
        self.level_cycle_history: List[int] = []
        self.available_level_indices = self._refresh_available_levels()
        self.hub_cycle_level = self.available_level_indices[0] if self.available_level_indices else 1
        self.hub_cycle_max = max(1, len(self.available_level_indices))
        self.hub_doors: List[Vec3] = []
        self.hub_nearby_door_index: Optional[int] = None
        self.pending_external_hub_link: Optional[str] = None
        self.shadow_npc_revealed = False
        self.shadow_npc_max_health = 3
        self.shadow_npc_health = self.shadow_npc_max_health
        self.return_to_halls_unlocked = False
        self.external_level_modules: Dict[int, Any] = {}
        self.external_level_settings_cache: Dict[int, Dict[str, Any]] = {}
        self.level_runtime_state: Dict[str, Any] = {}
        self.level_time_limit = LEVEL_RETURN_TIME
        self.level_time_remaining = 0.0
        self.last_non_hub_level: Optional[int] = None

        self._configure_window()
        self._configure_lens()

        self.world_root = self.render.attachNewNode("world_root")
        self.module_nodes: Dict[Tuple[int, int], ModuleChunk] = {}
        self.module_data_cache: Dict[Tuple[int, int], ModuleData] = {}

        self.wall_tex = self._make_wall_texture()
        self.floor_tex = self._make_floor_texture()
        self.water_floor_tex = self._make_water_floor_texture()
        self.water_tex = self._make_water_surface_texture()
        self.water_detail_tex = self._make_water_detail_texture()
        self.deck_gloss_tex = self._make_deck_gloss_texture()
        self.ceiling_tex = self._make_ceiling_texture()
        self.light_tex = self._make_light_texture()
        self.beam_tex = self._make_beam_texture()
        self.window_pattern_tex = self._make_window_pattern_texture()
        self.coping_tex = self._make_coping_texture()
        self.reflection_tex = self._make_reflection_texture()
        self.shadow_npc_tex = self._make_shadow_npc_texture()
        self.shadow_eye_tex = self._make_shadow_eye_texture()
        self.shadow_npc_outline_tex = self._make_shadow_npc_outline_texture()
        self.shadow_aura_tex = self._make_shadow_aura_texture()
        self.weapon_body_tex = self._make_weapon_body_texture()
        self.weapon_black_tex = self._make_weapon_black_texture()
        self.weapon_indicator_tex = self._make_weapon_indicator_texture()
        self.hub_wall_tex = self._make_hub_wall_texture()
        self.hub_trim_tex = self._make_hub_trim_texture()
        self.hub_carpet_tex = self._make_hub_carpet_texture()
        self.hub_door_tex = self._make_hub_door_texture()

        self.wall_stage = TextureStage.getDefault()
        self.water_stage = TextureStage("water_stage")
        self.water_detail_stage = TextureStage("water_detail_stage")
        self.gloss_stage = TextureStage("gloss_stage")

        self.dynamic_lights: List[Tuple[NodePath, Vec4, float, float]] = []
        self.sun_beams: List[Tuple[NodePath, float, float]] = []
        self.pattern_overlays: List[Tuple[NodePath, float, float, Vec4]] = []
        self.module_sun_lights: List[NodePath] = []

        self._ensure_asset_dirs()
        self._register_asset_slots()
        self._apply_asset_overrides()
        self._load_audio_assets()
        self._setup_lighting()
        self._setup_fog()
        self._setup_filters()
        self._setup_weapon_viewmodel()

        self.pitch = 0.0
        self.yaw = 0.0

        self.player_pos = Vec3(MODULE_SIZE * 0.5, CELL * 1.6, 0.0)
        self.keys = {"w": False, "a": False, "s": False, "d": False, "shift": False}

        self._stream_modules(force=True)
        self._spawn_shadow_npc(force=True)
        self._setup_ui()
        self._bind_inputs()
        self._apply_all_settings(initial=True)
        self._refresh_level_features()
        self._refresh_asset_labels()
        self._print_assets()
        self._update_mouse_capture(force=True)
        self.taskMgr.add(self._update, "update")

    # ----------------------------
    # Window / input
    # ----------------------------
    def _default_settings(self) -> Dict[str, Any]:
        return {
            "mouse_sensitivity": MOUSE_SENS,
            "fog_density": 1.0,
            "fov": 66.0,
            "dof_strength": 0.0,
            "music_volume": 0.72,
            "sound_volume": 0.92,
            "water_reflections": 0.0,
            "tile_reflections": 0.0,
            "fullscreen": False,
            "help_on": True,
            "quality_preset": "Low",
            "asset_overrides": {},
        }

    def _normalize_quality_preset(self, preset: Any) -> str:
        label = str(preset or "Low").strip().lower()
        aliases = {
            "performance": "Low",
            "low": "Low",
            "balanced": "Medium",
            "medium": "Medium",
            "quality": "High",
            "high": "High",
            "custom": "Custom",
        }
        return aliases.get(label, "Custom")

    def _load_settings(self) -> Dict[str, Any]:
        defaults = self._default_settings()
        if not self.config_path.exists():
            return defaults
        try:
            data = json.loads(self.config_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return defaults
        except Exception:
            return defaults

        merged = dict(defaults)
        for key in ("mouse_sensitivity", "fog_density", "fov", "dof_strength", "music_volume", "sound_volume", "water_reflections", "tile_reflections"):
            value = data.get(key)
            if isinstance(value, (int, float)):
                merged[key] = float(value)
        for key in ("fullscreen", "help_on"):
            value = data.get(key)
            if isinstance(value, bool):
                merged[key] = value
        preset = data.get("quality_preset")
        if isinstance(preset, str) and preset:
            merged["quality_preset"] = self._normalize_quality_preset(preset)
        overrides = data.get("asset_overrides")
        if isinstance(overrides, dict):
            merged["asset_overrides"] = {str(k): str(v) for k, v in overrides.items() if isinstance(v, str)}
        return merged

    def _save_settings(self) -> None:
        self.settings["fullscreen"] = bool(self.is_fullscreen)
        self.settings["help_on"] = bool(self.help_on)
        self.settings["asset_overrides"] = dict(self.asset_overrides)
        payload = {
            "mouse_sensitivity": round(float(self.settings.get("mouse_sensitivity", MOUSE_SENS)), 4),
            "fog_density": round(float(self.settings.get("fog_density", 1.0)), 4),
            "fov": round(float(self.settings.get("fov", 68.0)), 3),
            "dof_strength": round(float(self.settings.get("dof_strength", 0.0)), 4),
            "music_volume": round(float(self.settings.get("music_volume", 0.72)), 4),
            "sound_volume": round(float(self.settings.get("sound_volume", 0.92)), 4),
            "water_reflections": round(float(self.settings.get("water_reflections", 0.0)), 4),
            "tile_reflections": round(float(self.settings.get("tile_reflections", 0.0)), 4),
            "fullscreen": bool(self.settings.get("fullscreen", False)),
            "help_on": bool(self.settings.get("help_on", True)),
            "quality_preset": str(self._normalize_quality_preset(self.settings.get("quality_preset", "Low"))),
            "asset_overrides": dict(self.asset_overrides),
        }
        try:
            self.config_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            print(f"[Settings] Saved: {self.config_path}")
        except Exception as exc:
            print(f"[Settings] Save failed: {exc}")

    def _configure_window(self) -> None:
        props = WindowProperties()
        props.setTitle("Poolrooms Art Prototype")
        props.setSize(*self._pick_window_size())
        props.setFullscreen(self.is_fullscreen)
        if hasattr(props, "setFixedSize"):
            props.setFixedSize(False)
        if hasattr(props, "setUndecorated"):
            props.setUndecorated(False)
        self.win.requestProperties(props)

    def _pick_window_size(self) -> Tuple[int, int]:
        w = 1600
        h = int(w * 9 / 16)
        return w, h

    def _center_mouse(self) -> None:
        if self.win is None:
            return
        try:
            w = max(1, self.win.getXSize())
            h = max(1, self.win.getYSize())
            self.win.movePointer(0, w // 2, h // 2)
        except Exception:
            pass

    def _request_mouse_mode(self, captured: bool) -> None:
        props = WindowProperties()
        if hasattr(props, "setCursorHidden"):
            props.setCursorHidden(captured)
        if hasattr(props, "setMouseMode"):
            if captured:
                try:
                    props.setMouseMode(WindowProperties.M_confined)
                except Exception:
                    pass
            else:
                try:
                    props.setMouseMode(WindowProperties.M_absolute)
                except Exception:
                    pass
        self.win.requestProperties(props)
        self.mouse_captured = captured
        self.relative_mouse_mode = False
        self._ignore_mouse_frames = 3 if captured else 0
        if captured:
            self._center_mouse()

    def _window_has_focus(self) -> bool:
        try:
            props = self.win.getProperties()
            if hasattr(props, "getForeground"):
                return bool(props.getForeground())
        except Exception:
            pass
        return True

    def _update_mouse_capture(self, force: bool = False) -> None:
        should_capture = (not self.menu_open) and self._window_has_focus()
        if force or should_capture != self.mouse_captured:
            self._request_mouse_mode(should_capture)

    def _on_window_event(self, _window=None) -> None:
        self.window_foreground = self._window_has_focus()
        self._update_mouse_capture(force=True)

    def _configure_lens(self) -> None:
        lens = getattr(self, "camLens", None)
        if lens is None and hasattr(self, "cam") and self.cam is not None:
            try:
                lens = self.cam.node().getLens()
            except Exception:
                lens = None
        if lens is not None:
            lens.setFov(float(self.settings.get("fov", 68.0)))

    def _is_hub_level(self) -> bool:
        return int(self.current_level) == HUB_LEVEL

    def _weapon_enabled_for_level(self, level_index: Optional[int] = None) -> bool:
        level_index = self.current_level if level_index is None else int(level_index)
        return level_index > HUB_LEVEL

    def _shadow_enabled_for_level(self, level_index: Optional[int] = None) -> bool:
        level_index = self.current_level if level_index is None else int(level_index)
        return level_index > HUB_LEVEL

    def _vec4_from_value(self, value: Any, default: Vec4) -> Vec4:
        if isinstance(value, Vec4):
            return Vec4(value)
        if isinstance(value, (list, tuple)) and len(value) >= 3:
            alpha = float(value[3]) if len(value) > 3 else 1.0
            return Vec4(float(value[0]), float(value[1]), float(value[2]), alpha)
        return Vec4(default)

    def _ensure_levels_root(self) -> None:
        self.levels_root.mkdir(parents=True, exist_ok=True)
        self._write_text_if_missing(
            self.levels_root / "README.txt",
            (
                "Put level Python files in this folder.\n"
                "Any .py file here becomes a launchable level in sorted filename order.\n"
                "For a level file named example_level.py, put optional assets in levels/example_level/assets/.\n"
            ),
        )

    def _sanitize_level_slug(self, raw: str) -> str:
        slug = "".join(ch if (ch.isalnum() or ch == "_") else "_" for ch in str(raw).strip().lower())
        while "__" in slug:
            slug = slug.replace("__", "_")
        return slug.strip("_") or "level"

    def _discover_level_entries(self) -> Dict[int, Dict[str, Any]]:
        self._ensure_levels_root()
        paths = [
            p
            for p in sorted(self.levels_root.glob("*.py"))
            if p.is_file() and p.name != "__init__.py" and not p.name.startswith("_")
        ]
        entries: Dict[int, Dict[str, Any]] = {}
        for idx, level_path in enumerate(paths, start=1):
            slug = self._sanitize_level_slug(level_path.stem)
            entries[idx] = {
                "id": idx,
                "path": level_path,
                "slug": slug,
                "asset_root": self.levels_root / slug / "assets",
                "display_name": level_path.stem.replace("_", " ").strip() or f"Level {idx}",
            }
        return entries

    def _level_entry(self, level_index: Optional[int] = None) -> Optional[Dict[str, Any]]:
        level_index = self.current_level if level_index is None else int(level_index)
        return dict(self.level_entries.get(level_index, {})) or None

    def _fallback_level_asset_root(self, level_index: int) -> Path:
        return self.levels_root / f"level_{int(level_index):02d}" / "assets"

    def _external_level_module(self, level_index: Optional[int] = None) -> Any:
        level_index = self.current_level if level_index is None else int(level_index)
        if level_index <= HUB_LEVEL:
            return None
        if level_index in self.external_level_modules:
            return self.external_level_modules[level_index]
        entry = self._level_entry(level_index)
        if not entry:
            self.external_level_modules[level_index] = None
            return None
        path = Path(entry["path"])
        if not path.exists():
            self.external_level_modules[level_index] = None
            return None
        try:
            module_slug = self._sanitize_level_slug(entry.get("slug") or path.stem)
            module_name = f"poolrooms_level_{level_index}_{module_slug}"
            spec = importlib.util.spec_from_file_location(module_name, path)
            if spec is None or spec.loader is None:
                raise RuntimeError(f"No import spec for {path.name}")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            self.external_level_modules[level_index] = module
            return module
        except Exception as exc:
            print(f"[LevelLoader] Failed to import {path.name}: {exc}")
            self.external_level_modules[level_index] = None
            return None

    def _external_level_settings(self, level_index: Optional[int] = None) -> Dict[str, Any]:
        level_index = self.current_level if level_index is None else int(level_index)
        if level_index <= HUB_LEVEL:
            return {}
        if level_index in self.external_level_settings_cache:
            return dict(self.external_level_settings_cache[level_index])
        settings: Dict[str, Any] = {}
        module = self._external_level_module(level_index)
        if module is not None and hasattr(module, "get_level_settings"):
            try:
                raw = module.get_level_settings(self)
                if isinstance(raw, dict):
                    settings = dict(raw)
            except Exception as exc:
                print(f"[LevelLoader] get_level_settings failed for level {level_index}: {exc}")
        self.external_level_settings_cache[level_index] = dict(settings)
        return dict(settings)

    def _level_move_speed(self, level_index: Optional[int] = None) -> float:
        level_index = self.current_level if level_index is None else int(level_index)
        speed = MOVE_SPEED
        if level_index == 1:
            speed *= 1.34
        settings = self._external_level_settings(level_index)
        if settings:
            speed *= float(settings.get("move_speed_mult", 1.0))
        return speed

    def _level_uses_static_water_by_default(self, level_index: Optional[int] = None) -> bool:
        level_index = self.current_level if level_index is None else int(level_index)
        preset = self._normalize_quality_preset(self.settings.get("quality_preset", "Low"))
        settings = self._external_level_settings(level_index)
        if settings and "static_water_default" in settings:
            return bool(settings.get("static_water_default"))
        return level_index == 1 and preset != "High"

    def _level_allows_hall_return(self, level_index: Optional[int] = None) -> bool:
        level_index = self.current_level if level_index is None else int(level_index)
        return level_index > HUB_LEVEL and bool(self.return_to_halls_unlocked)

    def _return_to_halls_prompt(self) -> str:
        return "Press E to Return to Halls"

    def _asset_area_root(self, level_index: Optional[int] = None) -> Path:
        level_index = self.current_level if level_index is None else int(level_index)
        if level_index <= HUB_LEVEL:
            return self.halls_assets_root
        entry = self._level_entry(level_index)
        if entry:
            return Path(entry["asset_root"])
        return self._fallback_level_asset_root(level_index)

    def _configure_asset_context(self, level_index: Optional[int] = None) -> None:
        area_root = self._asset_area_root(level_index)
        self.asset_area_root = area_root
        self.texture_root = area_root / "textures" / "poolrooms"
        self.music_loop_root = area_root / "music" / "loops"
        self.shadow_loop_root = self.music_loop_root / "shadow_enemy"
        self.sfx_root = area_root / "sfx"
        if hasattr(self, "asset_slots"):
            self.default_asset_paths = self._default_asset_paths()

    def _level_display_name(self, level_index: Optional[int] = None) -> str:
        level_index = self.current_level if level_index is None else int(level_index)
        if level_index == HUB_LEVEL:
            return HUB_NAME
        settings = self._external_level_settings(level_index)
        if settings.get("display_name"):
            return str(settings["display_name"])
        entry = self._level_entry(level_index)
        if entry:
            return str(entry.get("display_name") or f"Level {level_index}").strip()
        return f"Level {level_index}"

    def _discover_level_indices(self) -> List[int]:
        self.level_entries = self._discover_level_entries()
        if self.level_entries:
            return sorted(self.level_entries.keys())
        return [1]

    def _refresh_available_levels(self) -> List[int]:
        entries = self._discover_level_entries()
        signature = tuple(f"{idx}:{Path(entry['path']).resolve()}" for idx, entry in sorted(entries.items()))
        if signature != getattr(self, "level_registry_signature", ()):
            if hasattr(self, "external_level_modules"):
                self.external_level_modules.clear()
            if hasattr(self, "external_level_settings_cache"):
                self.external_level_settings_cache.clear()
            self.level_cycle_queue = []
            self.level_cycle_history = []
        self.level_entries = entries
        self.level_registry_signature = signature
        available = sorted(entries.keys()) if entries else [1]
        available_set = set(available)
        self.available_level_indices = available
        self.hub_cycle_max = max(1, len(available))
        self.hub_cycle_level = available[0] if available else 1
        self.level_cycle_queue = [level for level in self.level_cycle_queue if level in available_set]
        self.level_cycle_history = [level for level in self.level_cycle_history if level in available_set][-16:]
        return list(self.available_level_indices)

    def _ensure_level_cycle_queue(self) -> List[int]:
        available = self._refresh_available_levels()
        if not self.level_cycle_queue:
            self.level_cycle_queue = list(available)
        return self.level_cycle_queue

    def _hub_target_level(self) -> int:
        return self._choose_random_level(exclude_current=True)

    def _choose_random_level(self, exclude_current: bool = False) -> int:
        available = self._refresh_available_levels()
        if not available:
            return 1
        choices = list(available)
        if len(choices) > 1:
            blocked: Set[int] = set()
            if self.last_non_hub_level is not None:
                blocked.add(int(self.last_non_hub_level))
            if exclude_current and self.current_level > HUB_LEVEL:
                blocked.add(int(self.current_level))
            filtered = [level for level in choices if level not in blocked]
            if filtered:
                choices = filtered
        pick = int(self.runtime_random.choice(choices))
        self.hub_cycle_level = pick
        return pick

    def _next_hub_level(self) -> int:
        level_index = self._choose_random_level(exclude_current=False)
        self.last_non_hub_level = level_index
        self.level_cycle_history.append(level_index)
        self.level_cycle_history = self.level_cycle_history[-16:]
        return level_index

    def _next_ordered_level(self, from_level: Optional[int] = None) -> int:
        return self._choose_random_level(exclude_current=True)

    def _trigger_next_level(self) -> None:
        if self.menu_open:
            return
        if self._is_hub_level():
            target_level = self._next_hub_level()
        else:
            target_level = self._next_ordered_level(self.current_level)
        self.pending_external_hub_link = None
        self._play_transition_sfx()
        self._load_level(target_level)
        self._toast(self._level_display_name(target_level), duration=1.9)

    def _hub_door_link_id(self, idx: int) -> str:
        if idx < 0 or idx >= len(self.hub_doors):
            return f"hotel_door_{idx:03d}"
        pos = self.hub_doors[idx]
        mx, my = self._module_of_pos(pos.x, pos.y)
        local_y = pos.y - my * MODULE_SIZE
        lane = "west" if pos.x < MODULE_SIZE * 0.5 else "east"
        slot = max(0, int(round((local_y - CELL * 1.55) / max(CELL * 2.55, 0.001))))
        room_no = 200 + ((abs(my) * 8 + slot * 2 + (0 if lane == "west" else 1)) % 80)
        return f"hotel_{lane}_{room_no:03d}_m{my:+d}"

    def _hub_door_prompt(self, idx: int) -> str:
        return "Press E to Open"

    def _refresh_level_features(self) -> None:
        if hasattr(self, "weapon_root") and self.weapon_root is not None and not self.weapon_root.isEmpty():
            if self._weapon_enabled_for_level():
                self.weapon_root.show()
            else:
                self.weapon_root.hide()
        if not self._shadow_enabled_for_level():
            self._despawn_shadow_npc()

    def _nearest_hub_door(self) -> Tuple[Optional[int], float]:
        if not self._is_hub_level() or not self.hub_doors:
            return None, 1e9
        best_idx: Optional[int] = None
        best_dist = 1e9
        player = Vec3(self.player_pos.x, self.player_pos.y, 0.0)
        for idx, pos in enumerate(self.hub_doors):
            dist = (Vec3(pos.x, pos.y, 0.0) - player).length()
            if dist < best_dist:
                best_idx = idx
                best_dist = dist
        return best_idx, best_dist

    def _update_hub_interact_prompt(self) -> None:
        if not hasattr(self, "ui_interact"):
            return
        if self.menu_open:
            self.hub_nearby_door_index = None
            self.ui_interact.setText("")
            return
        if self._is_hub_level():
            idx, dist = self._nearest_hub_door()
            if idx is not None and dist <= HUB_DOOR_USE_RADIUS:
                self.hub_nearby_door_index = idx
                self.ui_interact.setText(self._hub_door_prompt(idx))
            else:
                self.hub_nearby_door_index = None
                self.ui_interact.setText("")
            return
        self.hub_nearby_door_index = None
        if self._level_allows_hall_return():
            self.ui_interact.setText(self._return_to_halls_prompt())
        elif self._shadow_enabled_for_level():
            self.ui_interact.setText("Defeat the shadow to reopen the halls")
        else:
            self.ui_interact.setText("")

    def _enter_hub_door(self) -> None:
        if not self._is_hub_level():
            return
        idx, dist = self._nearest_hub_door()
        if idx is None or dist > HUB_DOOR_USE_RADIUS:
            return
        self.pending_external_hub_link = self._hub_door_link_id(idx)
        self._trigger_next_level()

    def _return_to_halls(self) -> None:
        if not self._level_allows_hall_return():
            return
        self._play_transition_sfx()
        self._load_level(HUB_LEVEL)
        self._toast("Returned to the halls", duration=1.9)

    def _on_interact(self) -> None:
        if self.menu_open:
            return
        if self._is_hub_level():
            self._enter_hub_door()
        elif self._level_allows_hall_return():
            self._return_to_halls()

    def _write_text_if_missing(self, path: Path, content: str) -> None:
        if path.exists():
            return
        try:
            path.write_text(content, encoding="utf-8")
        except Exception:
            pass

    def _ensure_asset_dirs(self) -> None:
        self._ensure_levels_root()
        available = self._refresh_available_levels()
        area_roots = {self._asset_area_root(HUB_LEVEL), self.asset_area_root}
        for level_index in available:
            area_roots.add(self._asset_area_root(level_index))

        for area_root in area_roots:
            (area_root / "textures" / "poolrooms").mkdir(parents=True, exist_ok=True)
            music_root = area_root / "music" / "loops"
            music_root.mkdir(parents=True, exist_ok=True)
            (music_root / "shadow_enemy").mkdir(parents=True, exist_ok=True)
            (area_root / "sfx" / "transitions").mkdir(parents=True, exist_ok=True)

        self.weapon_sfx_root.mkdir(parents=True, exist_ok=True)
        self.transition_sfx_root.mkdir(parents=True, exist_ok=True)

        self._write_text_if_missing(
            self.halls_assets_root / "music" / "loops" / "PLACE_MP3_LOOPS_HERE.txt",
            "Put hall music loops here. Supported formats: .mp3 .wav .ogg .flac\n",
        )
        self._write_text_if_missing(
            self.halls_assets_root / "textures" / "poolrooms" / "README.txt",
            "Optional hall texture overrides go here: wall.png floor.png water_floor.png water_surface.png ceiling.png light.png beam.png coping.png shadow_npc.png\n",
        )

        for level_index in available:
            entry = self._level_entry(level_index)
            level_name = self._level_display_name(level_index)
            area_root = self._asset_area_root(level_index)
            if entry:
                self._write_text_if_missing(
                    Path(entry["asset_root"]).parent / "README.txt",
                    (
                        f"Assets for {level_name}.\n"
                        "Use textures/poolrooms, music/loops, music/loops/shadow_enemy, and sfx/transitions here.\n"
                    ),
                )
            self._write_text_if_missing(
                area_root / "music" / "loops" / "PLACE_MP3_LOOPS_HERE.txt",
                f"Put {level_name} music loops here. Supported formats: .mp3 .wav .ogg .flac\n",
            )
            self._write_text_if_missing(
                area_root / "music" / "loops" / "shadow_enemy" / "PLACE_ENEMY_LOOPS_HERE.txt",
                f"Optional enemy loops for {level_name} go here. Supported formats: .mp3 .wav .ogg .flac\n",
            )
            self._write_text_if_missing(
                area_root / "textures" / "poolrooms" / "README.txt",
                (
                    f"Optional texture overrides for {level_name} go here: "
                    "wall.png floor.png water_floor.png water_surface.png ceiling.png light.png beam.png coping.png shadow_npc.png\n"
                ),
            )

    def _default_asset_paths(self) -> Dict[str, Path]:
        return {
            "wall": self.texture_root / "wall.png",
            "floor": self.texture_root / "floor.png",
            "water_floor": self.texture_root / "water_floor.png",
            "water_surface": self.texture_root / "water_surface.png",
            "ceiling": self.texture_root / "ceiling.png",
            "light": self.texture_root / "light.png",
            "beam": self.texture_root / "beam.png",
            "coping": self.texture_root / "coping.png",
            "shadow_npc": self.texture_root / "shadow_npc.png",
        }

    def _display_asset_source(self, source: str) -> str:
        if source == "generated":
            return source
        try:
            path = Path(source)
            if path.is_absolute():
                return path.relative_to(self.base_dir).as_posix()
        except Exception:
            pass
        return source.replace(chr(92), "/")

    def _music_loop_files(self) -> List[Path]:
        if not self.music_loop_root.exists():
            return []
        return sorted(
            [
                path
                for path in self.music_loop_root.iterdir()
                if path.is_file() and path.suffix.lower() in {".wav", ".ogg", ".mp3", ".flac"}
            ]
        )

    def _shadow_loop_files(self) -> List[Path]:
        found: List[Path] = []
        stems = ("shadow_enemy", "shadow_npc", "enemy_shadow")
        for stem in stems:
            for ext in (".wav", ".ogg", ".mp3", ".flac"):
                candidate = self.music_loop_root / f"{stem}{ext}"
                if candidate.exists():
                    found.append(candidate)
                    break
        if self.shadow_loop_root.exists():
            found.extend(
                sorted(
                    [
                        path
                        for path in self.shadow_loop_root.iterdir()
                        if path.is_file() and path.suffix.lower() in {".wav", ".ogg", ".mp3", ".flac"}
                    ]
                )
            )
        unique: List[Path] = []
        seen = set()
        for path in found:
            key = str(path.resolve())
            if key in seen:
                continue
            seen.add(key)
            unique.append(path)
        return unique

    def _weapon_sfx_files(self) -> Dict[str, Path]:
        found: Dict[str, Path] = {}
        for slot in ("fire", "nightvision_on", "nightvision_off"):
            for ext in (".mp3", ".wav", ".ogg", ".flac"):
                candidate = self.weapon_sfx_root / f"{slot}{ext}"
                if candidate.exists():
                    found[slot] = candidate
                    break
        return found

    def _transition_sfx_file(self) -> Optional[Path]:
        search_roots = (self.transition_sfx_root, self.sfx_root, self.halls_assets_root / "sfx" / "transitions")
        search_names = ("door_transition", "transition", "door_open", "door")
        for root in search_roots:
            for stem in search_names:
                for ext in (".wav", ".mp3", ".ogg", ".flac"):
                    candidate = root / f"{stem}{ext}"
                    if candidate.exists():
                        return candidate
        return None

    def _load_sound_any(self, path: Path, label: str):
        filename = Filename.fromOsSpecific(str(path))
        loaders = (("loadSfx", self.loader.loadSfx), ("loadMusic", self.loader.loadMusic))
        last_error = ""
        for loader_name, loader in loaders:
            try:
                sound = loader(filename)
            except Exception as exc:
                last_error = f"{loader_name}: {exc}"
                continue
            if sound is not None:
                self.audio_debug[label] = f"loaded via {loader_name}"
                return sound
        if last_error:
            self.audio_debug[label] = last_error
        else:
            self.audio_debug[label] = "loader returned None"
        return None

    def _stop_sound(self, sound: Any) -> None:
        if sound is None:
            return
        try:
            sound.stop()
        except Exception:
            pass

    def _reload_level_music(self) -> None:
        self._stop_sound(self.music_loop)
        self._stop_sound(self.shadow_music_loop)
        self.music_loop = None
        self.shadow_music_loop = None

        loop_files = self._music_loop_files()
        if loop_files:
            music = self._load_sound_any(loop_files[0], f"music:{loop_files[0].name}")
            if music is not None:
                try:
                    music.setLoop(True)
                except Exception:
                    pass
                try:
                    music.play()
                    self.music_loop = music
                except Exception as exc:
                    self.audio_debug[f"music:{loop_files[0].name}"] = f"play failed: {exc}"
                    print(f"[Audio] Failed to play music loop {loop_files[0].name}: {exc}")

        shadow_loop_files = self._shadow_loop_files()
        if shadow_loop_files:
            music = self._load_sound_any(shadow_loop_files[0], f"shadow_music:{shadow_loop_files[0].name}")
            if music is not None:
                try:
                    music.setLoop(True)
                except Exception:
                    pass
                try:
                    music.play()
                    self.shadow_music_loop = music
                except Exception as exc:
                    self.audio_debug[f"shadow_music:{shadow_loop_files[0].name}"] = f"play failed: {exc}"
                    print(f"[Audio] Failed to play shadow loop {shadow_loop_files[0].name}: {exc}")
        self.shadow_music_mix = 0.0
        self._apply_audio_settings()

    def _load_audio_assets(self) -> None:
        self.weapon_sfx.clear()
        self.audio_debug.clear()
        try:
            if hasattr(self, "enableAllAudio"):
                self.enableAllAudio()
        except Exception:
            pass

        for slot, path in self._weapon_sfx_files().items():
            sound = self._load_sound_any(path, f"weapon:{slot}")
            if sound is not None:
                try:
                    sound.setLoop(False)
                except Exception:
                    pass
                try:
                    sound.setVolume(1.0)
                except Exception:
                    pass
                self.weapon_sfx[slot] = sound

        self.transition_sfx = None
        transition_path = self._transition_sfx_file()
        if transition_path is not None:
            sound = self._load_sound_any(transition_path, f"transition:{transition_path.name}")
            if sound is not None:
                try:
                    sound.setLoop(False)
                except Exception:
                    pass
                try:
                    sound.setVolume(1.0)
                except Exception:
                    pass
                self.transition_sfx = sound

        self._reload_level_music()

    def _play_weapon_sfx(self, slot: str) -> None:
        sfx = self.weapon_sfx.get(slot)
        if sfx is None:
            return
        try:
            sfx.stop()
        except Exception:
            pass
        try:
            sfx.play()
        except Exception as exc:
            print(f"[Audio] Failed to play {slot}: {exc}")

    def _play_transition_sfx(self) -> None:
        if self.transition_sfx is None:
            return
        try:
            self.transition_sfx.stop()
        except Exception:
            pass
        try:
            self.transition_sfx.play()
        except Exception as exc:
            print(f"[Audio] Failed to play transition: {exc}")

    # ----------------------------
    # Procedural textures
    # ----------------------------
    def _finish_tex(self, tex: Texture, clamp_mode: bool = False) -> Texture:
        if hasattr(tex, "setMagfilter"):
            tex.setMagfilter(Texture.FTLinear)
        if hasattr(tex, "setMinfilter"):
            tex.setMinfilter(Texture.FTLinearMipmapLinear)
        if clamp_mode:
            if hasattr(tex, "setWrapU"):
                tex.setWrapU(Texture.WMClamp)
            if hasattr(tex, "setWrapV"):
                tex.setWrapV(Texture.WMClamp)
        return tex

    def _make_wall_texture(self) -> Texture:
        img = PNMImage(512, 512, 4)
        tile = 34
        for y in range(512):
            for x in range(512):
                tx = x % tile
                ty = y % tile
                grout = tx < 2 or ty < 2
                subtle = ((x * 3 + y * 5) % 23) / 1600.0
                stain = (
                    math.sin(x * 0.015) * 0.015
                    + math.cos(y * 0.022) * 0.012
                    + math.sin((x + y) * 0.011) * 0.010
                )
                base = 0.91 - subtle + stain
                if grout:
                    r, g, b = 0.58, 0.61, 0.57
                else:
                    r = clamp(base * 1.01, 0, 1)
                    g = clamp(base * 1.03, 0, 1)
                    b = clamp(base * 0.98, 0, 1)
                img.setXelA(x, y, r, g, b, 1.0)
        tex = Texture("wall_tex")
        tex.load(img)
        return self._finish_tex(tex)

    def _make_floor_texture(self) -> Texture:
        img = PNMImage(512, 512, 4)
        tile = 28
        for y in range(512):
            for x in range(512):
                tx = x % tile
                ty = y % tile
                grout = tx < 2 or ty < 2
                soft = ((x * 7 + y * 11) % 19) / 1800.0
                base = 0.93 - soft
                if grout:
                    r, g, b = 0.50, 0.53, 0.50
                else:
                    r = base
                    g = base * 1.01
                    b = base * 0.97
                img.setXelA(x, y, clamp(r, 0, 1), clamp(g, 0, 1), clamp(b, 0, 1), 1.0)
        tex = Texture("floor_tex")
        tex.load(img)
        return self._finish_tex(tex)

    def _make_water_floor_texture(self) -> Texture:
        img = PNMImage(512, 512, 4)
        tile = 28
        for y in range(512):
            for x in range(512):
                tx = x % tile
                ty = y % tile
                grout = tx < 2 or ty < 2
                ripple = math.sin(x * 0.040) * 0.015 + math.cos(y * 0.033) * 0.015
                base = 0.76 + ripple
                if grout:
                    r, g, b = 0.44, 0.58, 0.58
                else:
                    r = base * 0.80
                    g = base * 1.02
                    b = base * 1.05
                img.setXelA(x, y, clamp(r, 0, 1), clamp(g, 0, 1), clamp(b, 0, 1), 1.0)
        tex = Texture("water_floor_tex")
        tex.load(img)
        return self._finish_tex(tex)

    def _make_water_surface_texture(self) -> Texture:
        img = PNMImage(512, 512, 4)
        for y in range(512):
            for x in range(512):
                ripple = (
                    math.sin(x * 0.09)
                    + math.cos(y * 0.11)
                    + math.sin((x + y) * 0.035)
                ) * 0.025
                sheen = (math.sin((x - y) * 0.021) + 1.0) * 0.050
                r = 0.24 + ripple * 0.35 + sheen * 0.10
                g = 0.68 + ripple * 0.60 + sheen * 0.16
                b = 0.76 + ripple * 0.78 + sheen * 0.19
                a = 0.50 + sheen * 0.10
                img.setXelA(x, y, clamp(r, 0, 1), clamp(g, 0, 1), clamp(b, 0, 1), clamp(a, 0, 1))
        tex = Texture("water_tex")
        tex.load(img)
        return self._finish_tex(tex)

    def _make_water_detail_texture(self) -> Texture:
        img = PNMImage(512, 512, 4)
        for y in range(512):
            fy = y / 511.0
            for x in range(512):
                fx = x / 511.0
                wave_a = math.sin((fx * 13.0 + fy * 8.0) * math.tau)
                wave_b = math.cos((fx * 7.0 - fy * 11.0) * math.tau)
                wave_c = math.sin((fx * 19.0 + fy * 3.0) * math.tau)
                bright = clamp(0.5 + wave_a * 0.25 + wave_b * 0.18 + wave_c * 0.12, 0.0, 1.0)
                alpha = clamp((bright - 0.58) * 1.2, 0.0, 1.0)
                img.setXelA(x, y, 0.92 + bright * 0.08, 0.98, 1.0, alpha * 0.70)
        tex = Texture("water_detail_tex")
        tex.load(img)
        return self._finish_tex(tex)

    def _make_deck_gloss_texture(self) -> Texture:
        img = PNMImage(512, 512, 4)
        for y in range(512):
            fy = y / 511.0
            for x in range(512):
                fx = x / 511.0
                streak = clamp(1.0 - abs(math.sin((fx * 4.0 + fy * 1.35) * math.tau)) * 1.5, 0.0, 1.0)
                haze = clamp(1.0 - abs(fy - 0.5) * 1.8, 0.0, 1.0)
                alpha = clamp((streak ** 2.8) * haze * 0.65, 0.0, 1.0)
                img.setXelA(x, y, 0.98, 0.99, 1.0, alpha)
        tex = Texture("deck_gloss_tex")
        tex.load(img)
        return self._finish_tex(tex, clamp_mode=True)



    def _shadow_npc_alpha_field(self, w: int, h: int) -> List[List[float]]:
        field = [[0.0 for _ in range(w)] for __ in range(h)]
        for y in range(h):
            fy = y / max(1, h - 1)
            head = math.exp(-(((fy - 0.15) / 0.09) ** 2))
            shoulder = math.exp(-(((fy - 0.36) / 0.13) ** 2))
            torso = math.exp(-(((fy - 0.56) / 0.26) ** 2))
            taper = math.exp(-(((fy - 0.84) / 0.18) ** 2))
            half_width = 0.07 + head * 0.06 + shoulder * 0.12 + torso * 0.09 + taper * 0.03
            if 0.42 <= fy <= 0.78:
                arm = math.sin((fy - 0.42) / 0.36 * math.pi)
                half_width = max(half_width, 0.19 + arm * 0.045)
            for x in range(w):
                fx = x / max(1, w - 1)
                dist = abs(fx - 0.5)
                core = math.exp(-((dist / max(half_width, 1e-4)) ** 2.4))
                soft = math.exp(-((dist / max(half_width * 1.52, 1e-4)) ** 2.0))
                vertical = 0.42 + math.exp(-(((fy - 0.58) / 0.38) ** 2)) * 0.58
                noise = (math.sin((x * 0.045) + fy * 8.7) + math.cos((y * 0.031) - fx * 9.1)) * 0.018
                alpha = clamp(core * 0.70 + soft * 0.28 + noise, 0.0, 1.0) * vertical
                floor_fade = clamp((1.0 - fy) / 0.10, 0.0, 1.0)
                alpha *= floor_fade if fy > 0.90 else 1.0
                alpha *= 1.0 - clamp((0.02 - fx) * 18.0, 0.0, 1.0) * 0.08
                alpha *= 1.0 - clamp((fx - 0.98) * 18.0, 0.0, 1.0) * 0.08
                field[h - 1 - y][x] = alpha
        return field

    def _make_shadow_npc_texture(self) -> Texture:
        w, h = 320, 640
        field = self._shadow_npc_alpha_field(w, h)
        img = PNMImage(w, h, 4)
        for y in range(h):
            for x in range(w):
                alpha = field[y][x]
                img.setXelA(x, y, 0.015, 0.015, 0.018, alpha)
        tex = Texture("shadow_npc_tex")
        tex.load(img)
        return self._finish_tex(tex, clamp_mode=True)

    def _make_shadow_npc_outline_texture(self) -> Texture:
        img = PNMImage(64, 64, 4)
        for y in range(64):
            for x in range(64):
                img.setXelA(x, y, 1.0, 1.0, 1.0, 0.0)
        tex = Texture("shadow_npc_outline_tex")
        tex.load(img)
        return self._finish_tex(tex, clamp_mode=True)

    def _make_shadow_aura_texture(self) -> Texture:
        img = PNMImage(64, 64, 4)
        for y in range(64):
            for x in range(64):
                img.setXelA(x, y, 0.0, 0.0, 0.0, 0.0)
        tex = Texture("shadow_aura_tex")
        tex.load(img)
        return self._finish_tex(tex, clamp_mode=True)

    def _make_shadow_eye_texture(self) -> Texture:
        img = PNMImage(96, 48, 4)
        for y in range(48):
            fy = y / 47.0
            for x in range(96):
                fx = x / 95.0
                left = math.exp(-(((fx - 0.34) / 0.09) ** 2 + ((fy - 0.52) / 0.18) ** 2))
                right = math.exp(-(((fx - 0.66) / 0.09) ** 2 + ((fy - 0.52) / 0.18) ** 2))
                glow = clamp((left + right) * 0.95, 0.0, 1.0)
                core = clamp((left ** 1.6) + (right ** 1.6), 0.0, 1.0)
                img.setXelA(x, y, 0.80 + core * 0.20, 1.0, 0.78 + core * 0.22, glow * 0.90)
        tex = Texture("shadow_eye_tex")
        tex.load(img)
        return self._finish_tex(tex, clamp_mode=True)

    def _make_ceiling_texture(self) -> Texture:
        img = PNMImage(512, 512, 4)
        tile = 48
        for y in range(512):
            for x in range(512):
                tx = x % tile
                ty = y % tile
                grout = tx < 2 or ty < 2
                dust = ((x * 17 + y * 13) % 61) / 4200.0
                base = 0.84 - dust
                if grout:
                    r, g, b = 0.66, 0.68, 0.65
                else:
                    r = base
                    g = base * 1.01
                    b = base * 0.99
                img.setXelA(x, y, clamp(r, 0, 1), clamp(g, 0, 1), clamp(b, 0, 1), 1.0)
        tex = Texture("ceiling_tex")
        tex.load(img)
        return self._finish_tex(tex)

    def _make_light_texture(self) -> Texture:
        img = PNMImage(256, 256, 4)
        for y in range(256):
            for x in range(256):
                nx = (x / 255.0) * 2.0 - 1.0
                ny = (y / 255.0) * 2.0 - 1.0
                d = max(abs(nx), abs(ny))
                glow = clamp(1.0 - d * 1.25, 0.0, 1.0)
                alpha = glow * glow
                img.setXelA(x, y, 0.98, 0.99, 0.92, alpha)
        tex = Texture("light_tex")
        tex.load(img)
        return self._finish_tex(tex, clamp_mode=True)

    def _make_beam_texture(self) -> Texture:
        img = PNMImage(256, 256, 4)
        for y in range(256):
            fy = y / 255.0
            for x in range(256):
                fx = x / 255.0
                edge = clamp(1.0 - abs(fx * 2.0 - 1.0) * 1.8, 0.0, 1.0)
                fade = clamp((1.0 - fy) ** 1.7, 0.0, 1.0)
                alpha = clamp(edge * fade * 0.74, 0.0, 1.0)
                img.setXelA(x, y, 0.99, 0.97, 0.88, alpha)
        tex = Texture("beam_tex")
        tex.load(img)
        return self._finish_tex(tex, clamp_mode=True)

    def _make_coping_texture(self) -> Texture:
        img = PNMImage(256, 128, 4)
        for y in range(128):
            for x in range(256):
                top = 0.88 if y < 24 else 0.95
                noise = ((x * 7 + y * 13) % 17) / 2000.0
                img.setXelA(x, y, top - noise, top - noise * 0.9, top + 0.02 - noise * 0.6, 1.0)
        tex = Texture("coping_tex")
        tex.load(img)
        return self._finish_tex(tex)


    def _make_reflection_texture(self) -> Texture:
        img = PNMImage(256, 256, 4)
        for y in range(256):
            fy = y / 255.0
            for x in range(256):
                fx = x / 255.0
                band = clamp(1.0 - abs(fx * 2.0 - 1.0) * 1.35, 0.0, 1.0)
                fade = clamp((1.0 - fy) ** 1.8, 0.0, 1.0)
                ripple = (math.sin((x + y) * 0.055) + math.cos((x - y) * 0.030)) * 0.08
                alpha = clamp((band * fade * 0.42) + ripple * 0.10, 0.0, 1.0)
                img.setXelA(x, y, 0.96, 0.98, 1.00, alpha)
        tex = Texture("reflection_tex")
        tex.load(img)
        return self._finish_tex(tex, clamp_mode=True)

    def _make_window_pattern_texture(self) -> Texture:
        img = PNMImage(384, 384, 4)
        for y in range(384):
            fy = y / 383.0
            for x in range(384):
                fx = x / 383.0
                bar = 0.0
                if x < 18 or x > 365 or y < 18 or y > 365:
                    bar = 1.0
                if 118 <= x <= 136 or 248 <= x <= 266:
                    bar = 1.0
                if 180 <= y <= 198:
                    bar = 1.0
                pane_x = clamp(1.0 - abs(fx * 2.0 - 1.0) * 0.95, 0.0, 1.0)
                pane_y = clamp(1.0 - abs(fy * 2.0 - 1.0) * 0.90, 0.0, 1.0)
                falloff = (pane_x ** 1.4) * (pane_y ** 1.2)
                streaks = 0.84 + math.sin((x + y) * 0.035) * 0.08 + math.cos((x - y) * 0.021) * 0.05
                alpha = clamp(falloff * streaks * 0.95 - bar * 0.92, 0.0, 1.0)
                img.setXelA(x, y, 1.0, 0.96, 0.86, alpha)
        tex = Texture("window_pattern_tex")
        tex.load(img)
        return self._finish_tex(tex, clamp_mode=True)

    def _make_weapon_body_texture(self) -> Texture:
        img = PNMImage(512, 512, 4)
        for y in range(512):
            fy = y / 511.0
            for x in range(512):
                fx = x / 511.0
                noise = ((x * 17 + y * 31) % 37) / 4000.0
                panel_line = 0.0
                if x % 84 < 3 or y % 92 < 3:
                    panel_line = 0.16
                bevel = (math.sin(fx * math.tau * 3.3) + math.cos(fy * math.tau * 2.7)) * 0.018
                r = 0.86 + bevel - noise
                g = 0.82 + bevel * 0.92 - noise * 0.9
                b = 0.75 + bevel * 0.74 - noise * 0.8
                if 114 <= x <= 398 and 48 <= y <= 110:
                    r, g, b = 0.93, 0.94, 0.95
                if 36 <= x <= 476 and 210 <= y <= 248:
                    r, g, b = 0.16, 0.17, 0.19
                if 204 <= x <= 308 and 128 <= y <= 386:
                    r, g, b = 0.95, 0.96, 0.97
                img.setXelA(x, y, clamp(r - panel_line, 0.0, 1.0), clamp(g - panel_line, 0.0, 1.0), clamp(b - panel_line, 0.0, 1.0), 1.0)
        tex = Texture("weapon_body_tex")
        tex.load(img)
        return self._finish_tex(tex)

    def _make_weapon_black_texture(self) -> Texture:
        img = PNMImage(256, 256, 4)
        for y in range(256):
            for x in range(256):
                ridge = 0.10 if x % 24 < 5 else 0.0
                grain = ((x * 11 + y * 7) % 19) / 2200.0
                sheen = math.sin((x + y) * 0.075) * 0.012
                base = 0.10 + ridge + sheen - grain
                r = clamp(base * 0.92, 0.0, 1.0)
                g = clamp(base * 0.97, 0.0, 1.0)
                b = clamp(base * 1.05, 0.0, 1.0)
                if 96 <= y <= 160 and x % 48 < 10:
                    r, g, b = 0.20, 0.21, 0.24
                img.setXelA(x, y, r, g, b, 1.0)
        tex = Texture("weapon_black_tex")
        tex.load(img)
        return self._finish_tex(tex)

    def _make_weapon_indicator_texture(self) -> Texture:
        img = PNMImage(256, 64, 4)
        for y in range(64):
            fy = y / 63.0
            for x in range(256):
                fx = x / 255.0
                band = clamp(1.0 - abs(fx * 2.0 - 1.0) * 1.35, 0.0, 1.0)
                glow = clamp(1.0 - abs(fy * 2.0 - 1.0) * 1.75, 0.0, 1.0)
                scan = 0.75 + math.sin(x * 0.28) * 0.12
                alpha = clamp((band ** 1.6) * (glow ** 1.8) * scan, 0.0, 1.0)
                img.setXelA(x, y, 1.0, 1.0, 1.0, alpha)
        tex = Texture("weapon_indicator_tex")
        tex.load(img)
        return self._finish_tex(tex, clamp_mode=True)

    def _make_hub_wall_texture(self) -> Texture:
        img = PNMImage(512, 512, 4)
        for y in range(512):
            fy = y / 511.0
            band = math.sin(fy * math.tau * 0.72 + 0.35) * 0.008
            for x in range(512):
                fx = x / 511.0
                roller = math.sin(x * 0.010 + y * 0.003) * 0.006
                stipple = (((x * 11 + y * 23) % 67) / 67.0 - 0.5) * 0.010
                peel = math.sin(x * 0.13) * math.sin(y * 0.19) * 0.003
                gloss = math.exp(-((fx - 0.48) / 0.30) ** 2) * 0.024
                base = 0.84 + band + roller + stipple + peel + gloss
                r = clamp(base * 1.04, 0.0, 1.0)
                g = clamp(base * 1.01, 0.0, 1.0)
                b = clamp(base * 0.97, 0.0, 1.0)
                if y % 128 < 2:
                    r, g, b = 0.73, 0.70, 0.66
                img.setXelA(x, y, r, g, b, 1.0)
        tex = Texture("hub_wall_tex")
        tex.load(img)
        return self._finish_tex(tex)
    def _make_hub_trim_texture(self) -> Texture:
        img = PNMImage(512, 256, 4)
        for y in range(256):
            fy = y / 255.0
            for x in range(512):
                grain = math.sin(x * 0.086 + y * 0.012) * 0.05 + math.cos(x * 0.032 - y * 0.028) * 0.03
                pore = (((x * 17 + y * 29) % 41) / 41.0 - 0.5) * 0.026
                sheen = math.exp(-((fy - 0.48) / 0.24) ** 2) * 0.035
                base = 0.15 + grain + pore + sheen
                r = clamp(base * 1.10, 0.0, 1.0)
                g = clamp(base * 0.68, 0.0, 1.0)
                b = clamp(base * 0.34, 0.0, 1.0)
                if y % 64 < 2:
                    r, g, b = 0.05, 0.035, 0.025
                img.setXelA(x, y, r, g, b, 1.0)
        tex = Texture("hub_trim_tex")
        tex.load(img)
        return self._finish_tex(tex)
    def _make_hub_carpet_texture(self) -> Texture:
        img = PNMImage(512, 512, 4)
        cell = 92.0
        row_h = cell * 0.86
        for y in range(512):
            row = int(y / row_h)
            for x in range(512):
                best = 1e9
                best_dx = 0.0
                best_dy = 0.0
                for rr in (row - 1, row, row + 1):
                    rr_center = rr * row_h + row_h * 0.5
                    rr_offset = (cell * 0.5) if (rr & 1) else 0.0
                    cc = int((x - rr_offset) / cell)
                    for c2 in (cc - 1, cc, cc + 1):
                        cx = c2 * cell + rr_offset + cell * 0.5
                        dx = x - cx
                        dy = y - rr_center
                        d = dx * dx + dy * dy
                        if d < best:
                            best = d
                            best_dx = dx
                            best_dy = dy
                ang = math.atan2(best_dy, best_dx)
                radius = math.sqrt(best)
                hex_metric = radius * (1.0 + 0.16 * math.cos(6.0 * ang))
                weave = (((x * 9 + y * 13) % 31) / 31.0 - 0.5) * 0.030
                r = 0.18 + weave * 0.20
                g = 0.07 + weave * 0.10
                b = 0.04 + weave * 0.08
                if hex_metric < 39.0:
                    r, g, b = 0.74 + weave * 0.22, 0.30 + weave * 0.10, 0.08 + weave * 0.06
                if 24.0 < hex_metric < 30.5:
                    r, g, b = 0.17 + weave * 0.12, 0.07 + weave * 0.08, 0.04 + weave * 0.06
                if hex_metric < 15.2:
                    r, g, b = 0.46 + weave * 0.16, 0.08 + weave * 0.06, 0.08 + weave * 0.05
                if abs(y - 24) < 7 or abs(y - 488) < 7:
                    r, g, b = 0.08, 0.04, 0.03
                img.setXelA(x, y, clamp(r, 0.0, 1.0), clamp(g, 0.0, 1.0), clamp(b, 0.0, 1.0), 1.0)
        tex = Texture("hub_carpet_tex")
        tex.load(img)
        return self._finish_tex(tex)
    def _make_hub_door_texture(self) -> Texture:
        img = PNMImage(256, 512, 4)
        for y in range(512):
            for x in range(256):
                fx = x / 255.0
                grain = math.sin(y * 0.030 + x * 0.016) * 0.04 + math.cos(y * 0.012 - x * 0.034) * 0.025
                gloss = math.exp(-((fx - 0.52) / 0.18) ** 2) * 0.040
                pore = (((x * 13 + y * 5) % 37) / 37.0 - 0.5) * 0.018
                base = 0.13 + grain + gloss + pore
                r = clamp(base * 1.08, 0.0, 1.0)
                g = clamp(base * 0.64, 0.0, 1.0)
                b = clamp(base * 0.31, 0.0, 1.0)
                if x < 8 or x > 247 or y < 8 or y > 503:
                    r, g, b = 0.03, 0.025, 0.02
                if 110 < x < 146 and 58 < y < 82:
                    r, g, b = 0.72, 0.58, 0.18
                if 182 < x < 214 and 246 < y < 278:
                    r, g, b = 0.72, 0.58, 0.18
                img.setXelA(x, y, r, g, b, 1.0)
        tex = Texture("hub_door_tex")
        tex.load(img)
        return self._finish_tex(tex)
    def _setup_weapon_viewmodel(self) -> None:
        self.weapon_base_pos = Vec3(0.01, 1.26, -0.48)
        self.weapon_base_hpr = Vec3(0.0, -5.2, 0.0)
        self.weapon_root = self.camera.attachNewNode("weapon_root")
        self.weapon_root.setPos(self.weapon_base_pos)
        self.weapon_root.setHpr(self.weapon_base_hpr)
        self.weapon_root.setScale(0.40, 0.56, 0.42)
        self.weapon_root.setLightOff()
        self.weapon_root.setShaderOff()
        self.weapon_root.setDepthTest(False)
        self.weapon_root.setDepthWrite(False)
        self.weapon_root.setBin("fixed", 25)
        self.weapon_root.setTransparency(TransparencyAttrib.MAlpha)
        self.weapon_indicator_nodes: List[Tuple[NodePath, Vec4, float]] = []
        self._build_weapon_viewmodel(self.weapon_root)

    def _add_weapon_indicator(self, parent: NodePath, center: Vec3, width: float, depth: float, color: Vec4, phase: float) -> None:
        bezel = self._add_box(parent, center + Vec3(0.0, 0.0, -0.010), Vec3(width + 0.045, depth + 0.040, 0.024), self.weapon_black_tex)
        bezel.setColorScale(0.05, 0.06, 0.07, 1.0)
        glow = self._add_plane(parent, center + Vec3(0.0, 0.0, 0.006), width, depth, (0, -90, 0), self.weapon_indicator_tex, 1.0, 1.0, True)
        glow.setColorScale(color.x, color.y, color.z, 0.95)
        self.weapon_indicator_nodes.append((glow, color, phase))

    def _build_weapon_viewmodel(self, parent: NodePath) -> None:
        rifle = parent.attachNewNode("dark_rifle")
        stock = self._add_box(rifle, Vec3(0.0, -1.02, -0.03), Vec3(0.54, 0.86, 0.30), self.weapon_body_tex)
        stock.setColorScale(0.92, 0.90, 0.84, 1.0)
        rear_cap = self._add_box(rifle, Vec3(0.0, -1.38, -0.01), Vec3(0.38, 0.20, 0.24), self.weapon_black_tex)
        rear_cap.setColorScale(0.07, 0.08, 0.09, 1.0)
        receiver = self._add_box(rifle, Vec3(0.0, -0.02, 0.0), Vec3(0.72, 1.98, 0.46), self.weapon_body_tex)
        receiver.setColorScale(0.96, 0.93, 0.84, 1.0)
        upper_spine = self._add_box(rifle, Vec3(0.0, 0.06, 0.24), Vec3(0.44, 1.46, 0.16), self.weapon_body_tex)
        upper_spine.setColorScale(0.97, 0.98, 1.00, 1.0)
        plasma_belly = self._add_box(rifle, Vec3(0.0, 0.22, -0.26), Vec3(0.40, 1.18, 0.26), self.weapon_body_tex)
        plasma_belly.setColorScale(0.84, 0.86, 0.89, 1.0)
        vent_left = self._add_box(rifle, Vec3(-0.34, 0.05, 0.04), Vec3(0.05, 1.24, 0.22), self.weapon_black_tex)
        vent_left.setColorScale(0.08, 0.09, 0.10, 1.0)
        vent_right = self._add_box(rifle, Vec3(0.34, 0.05, 0.04), Vec3(0.05, 1.24, 0.22), self.weapon_black_tex)
        vent_right.setColorScale(0.08, 0.09, 0.10, 1.0)
        front_shroud = self._add_box(rifle, Vec3(0.0, 1.12, 0.02), Vec3(0.58, 0.72, 0.42), self.weapon_body_tex)
        front_shroud.setColorScale(0.92, 0.92, 0.95, 1.0)
        front_collar = self._add_box(rifle, Vec3(0.0, 1.50, 0.01), Vec3(0.44, 0.18, 0.32), self.weapon_black_tex)
        front_collar.setColorScale(0.07, 0.08, 0.09, 1.0)
        barrel_core = self._add_box(rifle, Vec3(0.0, 1.95, 0.0), Vec3(0.18, 0.98, 0.18), self.weapon_black_tex)
        barrel_core.setColorScale(0.05, 0.06, 0.07, 1.0)
        for seg_y in (1.64, 1.82, 2.00, 2.18):
            ring = self._add_box(rifle, Vec3(0.0, seg_y, 0.0), Vec3(0.30, 0.08, 0.30), self.weapon_black_tex)
            ring.setColorScale(0.10, 0.11, 0.13, 1.0)
        muzzle = self._add_box(rifle, Vec3(0.0, 2.46, 0.0), Vec3(0.38, 0.28, 0.38), self.weapon_black_tex)
        muzzle.setColorScale(0.07, 0.08, 0.10, 1.0)
        inner_core = self._add_box(rifle, Vec3(0.0, 2.52, 0.0), Vec3(0.12, 0.12, 0.12), self.weapon_indicator_tex)
        inner_core.setColorScale(0.18, 0.92, 1.00, 0.85)
        inner_core.setTransparency(TransparencyAttrib.MAlpha)
        for side in (-1.0, 1.0):
            side_root = rifle.attachNewNode(f"muzzle_gills_{int(side)}")
            side_root.setPos(side * 0.235, 2.22, 0.0)
            for idx, y_off in enumerate((-0.12, -0.02, 0.08, 0.18)):
                fin = self._add_box(side_root, Vec3(0.0, y_off, 0.0), Vec3(0.05, 0.17, 0.10), self.weapon_black_tex)
                fin.setColorScale(0.03, 0.04, 0.05, 1.0)
                fin.setP(-26.0 + idx * 2.5)
                fin.setR(18.0 * side)
        carry_nose = self._add_box(rifle, Vec3(0.0, 0.88, 0.30), Vec3(0.22, 0.58, 0.12), self.weapon_body_tex)
        carry_nose.setColorScale(0.96, 0.98, 1.00, 1.0)
        grip = self._add_box(rifle, Vec3(0.0, -0.28, -0.48), Vec3(0.22, 0.24, 0.72), self.weapon_black_tex)
        grip.setColorScale(0.10, 0.11, 0.12, 1.0)
        grip.setP(16.0)
        trigger_guard = self._add_box(rifle, Vec3(0.0, -0.04, -0.36), Vec3(0.20, 0.24, 0.08), self.weapon_black_tex)
        trigger_guard.setColorScale(0.05, 0.06, 0.07, 1.0)
        offhand_guard = self._add_box(rifle, Vec3(0.0, 0.64, -0.34), Vec3(0.28, 0.46, 0.12), self.weapon_black_tex)
        offhand_guard.setColorScale(0.10, 0.11, 0.13, 1.0)
        cheek_plate_left = self._add_box(rifle, Vec3(-0.22, -0.30, 0.16), Vec3(0.08, 0.94, 0.18), self.weapon_body_tex)
        cheek_plate_left.setColorScale(0.98, 0.99, 1.00, 1.0)
        cheek_plate_right = self._add_box(rifle, Vec3(0.22, -0.30, 0.16), Vec3(0.08, 0.94, 0.18), self.weapon_body_tex)
        cheek_plate_right.setColorScale(0.98, 0.99, 1.00, 1.0)
        self._add_weapon_indicator(rifle, Vec3(0.0, -0.20, 0.33), 0.10, 0.32, Vec4(0.24, 0.82, 1.00, 1.0), 0.0)
        self._add_weapon_indicator(rifle, Vec3(0.0, 0.10, 0.33), 0.10, 0.26, Vec4(0.28, 1.00, 0.40, 1.0), 1.2)
        self._add_weapon_indicator(rifle, Vec3(0.0, 0.36, 0.33), 0.10, 0.22, Vec4(1.00, 0.28, 0.28, 1.0), 2.4)
        side_energy = self._add_plane(rifle, Vec3(-0.215, 0.56, -0.02), 0.30, 0.10, (90, 0, 0), self.weapon_indicator_tex, 1.0, 1.0, True)
        side_energy.setColorScale(0.18, 0.88, 1.00, 0.84)
        self.weapon_indicator_nodes.append((side_energy, Vec4(0.18, 0.88, 1.00, 1.0), 0.65))

    def _update_weapon_viewmodel(self, dt: float, dx: float, dy: float, moving: bool, in_water: bool) -> None:
        if not hasattr(self, "weapon_root") or self.weapon_root.isEmpty() or not self._weapon_enabled_for_level():
            return
        bob_speed = 7.0 if moving else 2.0
        bob = math.sin(self.ambience_t * bob_speed) * (0.012 + (0.010 if moving else 0.0))
        sway_x = clamp(-dx * 0.00008, -0.012, 0.012)
        sway_z = clamp(dy * 0.00008, -0.010, 0.010)
        level_settings = self._external_level_settings()
        extra_sink = float(level_settings.get("weapon_sink", 0.0)) if level_settings else 0.0
        water_sink = (-0.018 if in_water else 0.0) + extra_sink
        self.weapon_root.setPos(
            self.weapon_base_pos.x + sway_x + bob * 0.16,
            self.weapon_base_pos.y,
            self.weapon_base_pos.z + sway_z + bob * 0.62 + water_sink,
        )
        self.weapon_root.setHpr(
            self.weapon_base_hpr.x + clamp(-dx * 0.010, -1.6, 1.6),
            self.weapon_base_hpr.y + clamp(dy * 0.008, -1.2, 1.2),
            self.weapon_base_hpr.z + bob * 4.0,
        )
        if (not self.nightvision_on) and level_settings.get("weapon_color_scale") is not None:
            tint = self._vec4_from_value(level_settings.get("weapon_color_scale"), Vec4(1.0, 1.0, 1.0, 1.0))
            pulse_strength = float(level_settings.get("weapon_pulse_strength", 0.0))
            pulse = 1.0 + math.sin(self.ambience_t * 1.6 + 0.4) * pulse_strength + math.sin(self.ambience_t * 4.3 + 1.2) * (pulse_strength * 0.42)
            self.weapon_root.setColorScale(tint.x * pulse, tint.y * pulse, tint.z * pulse, tint.w)
        alive: List[Tuple[NodePath, Vec4, float]] = []
        indicator_tint = level_settings.get("weapon_indicator_tint")
        tint_vec = self._vec4_from_value(indicator_tint, Vec4(1.0, 1.0, 1.0, 1.0)) if indicator_tint is not None else None
        for np, color, phase in self.weapon_indicator_nodes:
            if np.isEmpty():
                continue
            pulse = 0.74 + math.sin(self.ambience_t * 3.6 + phase) * 0.18 + math.sin(self.ambience_t * 8.2 + phase * 1.7) * 0.06
            if tint_vec is not None and not self.nightvision_on:
                np.setColorScale(tint_vec.x * pulse, tint_vec.y * pulse, tint_vec.z * pulse, clamp(0.68 + pulse * 0.24, 0.0, 1.0))
            else:
                np.setColorScale(color.x * pulse, color.y * pulse, color.z * pulse, clamp(0.70 + pulse * 0.22, 0.0, 1.0))
            alive.append((np, color, phase))
        self.weapon_indicator_nodes = alive

    # ----------------------------
    # Render setup
    # ----------------------------
    def _setup_lighting(self) -> None:
        self.setBackgroundColor(0.09, 0.11, 0.12, 1.0)

        if hasattr(self.render, "setShaderAuto"):
            try:
                self.render.setShaderAuto()
            except Exception:
                pass

        amb = AmbientLight("amb")
        amb.setColor(Vec4(0.05, 0.055, 0.06, 1.0))
        self.amb_np = self.render.attachNewNode(amb)
        self.render.setLight(self.amb_np)

        sun = DirectionalLight("sun")
        sun.setColor(Vec4(0.13, 0.14, 0.12, 1.0))
        self.sun_np = self.render.attachNewNode(sun)
        self.sun_np.setHpr(45, -28, 0)
        self.render.setLight(self.sun_np)

        fill = DirectionalLight("fill")
        fill.setColor(Vec4(0.018, 0.020, 0.024, 1.0))
        self.fill_np = self.render.attachNewNode(fill)
        self.fill_np.setHpr(-105, -12, 0)
        self.render.setLight(self.fill_np)

        lift = DirectionalLight("lift")
        lift.setColor(Vec4(0.024, 0.026, 0.028, 1.0))
        self.lift_np = self.render.attachNewNode(lift)
        self.lift_np.setHpr(18, 78, 0)
        self.render.setLight(self.lift_np)

        self._default_bg_color = Vec4(0.09, 0.11, 0.12, 1.0)
        self._default_fog_color = Vec4(FOG_COLOR)
        self._default_amb_color = Vec4(0.05, 0.055, 0.06, 1.0)
        self._default_sun_color = Vec4(0.13, 0.14, 0.12, 1.0)
        self._default_fill_color = Vec4(0.018, 0.020, 0.024, 1.0)
        self._default_lift_color = Vec4(0.024, 0.026, 0.028, 1.0)

    def _setup_fog(self) -> None:
        self.scene_fog = Fog("poolrooms_fog")
        self.scene_fog.setColor(FOG_COLOR)
        self.scene_fog.setLinearRange(FOG_START, FOG_END)
        self.render.setFog(self.scene_fog)

    def _setup_filters(self) -> None:
        self.filters = None
        self.filter_backend = "none"

    def _ensure_filters(self) -> bool:
        if self.filters is not None:
            return True
        if CommonFilters is None:
            return False
        try:
            self.filters = CommonFilters(self.win, self.cam)
            self.filter_backend = "CommonFilters"
            return True
        except Exception as exc:
            print(f"[Filters] Disabled: {exc}")
            self.filters = None
            self.filter_backend = "none"
            return False

    # ----------------------------
    # UI / controls
    # ----------------------------
    def _setup_ui(self) -> None:
        self.ui_status = OnscreenText(
            text="",
            pos=(-1.18, 0.90),
            scale=0.040,
            fg=(0.85, 0.88, 0.83, 0.92),
            align=TextNode.ALeft,
            wordwrap=26.0,
            mayChange=True,
        )
        self.ui_help = OnscreenText(
            text=self._help_text(),
            pos=(0.0, -0.84),
            scale=0.035,
            fg=(0.84, 0.88, 0.84, 0.82),
            align=TextNode.ACenter,
            wordwrap=34.0,
            mayChange=True,
        )
        self.ui_toast = OnscreenText(
            text="",
            pos=(0.0, 0.82),
            scale=0.046,
            fg=(0.95, 0.98, 0.95, 0.94),
            align=TextNode.ACenter,
            wordwrap=26.0,
            mayChange=True,
        )
        self.ui_cursor = OnscreenText(
            text="+",
            pos=(0.0, 0.0),
            scale=0.048,
            fg=(0.94, 0.98, 0.95, 0.55),
        )
        self.ui_interact = OnscreenText(
            text="",
            pos=(0.0, -0.72),
            scale=0.046,
            fg=(0.94, 0.96, 0.90, 0.94),
            align=TextNode.ACenter,
            wordwrap=22.0,
            mayChange=True,
        )
        self.nv_overlay = DirectFrame(
            parent=self.aspect2d,
            frameSize=(-1.78, 1.78, -1.02, 1.02),
            frameColor=(0.08, 0.30, 0.10, 0.12),
            relief=None,
            sortOrder=2,
        )
        self.nv_overlay.hide()
        self.nv_scan = OnscreenText(
            text="",
            pos=(0.0, 0.90),
            scale=0.030,
            fg=(0.60, 1.00, 0.66, 0.74),
            align=TextNode.ACenter,
            wordwrap=30.0,
            mayChange=True,
        )
        self.nv_scan.hide()

        self.menu_root = DirectFrame(
            parent=self.aspect2d,
            frameSize=(-1.34, 1.34, -0.92, 0.92),
            frameColor=(0.03, 0.04, 0.05, 0.92),
            relief=None,
        )
        DirectLabel(
            parent=self.menu_root,
            text="Poolrooms Settings",
            text_scale=0.070,
            text_fg=(0.94, 0.96, 0.98, 1.0),
            relief=None,
            pos=(-1.16, 0, 0.84),
            text_align=TextNode.ALeft,
        )
        self.menu_preset_label = DirectLabel(
            parent=self.menu_root,
            text="Preset: Custom",
            text_scale=0.040,
            text_fg=(0.72, 0.78, 0.84, 1.0),
            relief=None,
            pos=(-1.16, 0, 0.76),
            text_align=TextNode.ALeft,
        )
        DirectButton(
            parent=self.menu_root,
            text="Resume",
            text_scale=0.045,
            frameSize=(-0.16, 0.16, -0.05, 0.05),
            frameColor=(0.16, 0.19, 0.22, 0.95),
            text_fg=(0.95, 0.97, 0.99, 1.0),
            pos=(0.83, 0, 0.84),
            command=self._toggle_menu,
        )
        DirectButton(
            parent=self.menu_root,
            text="Save + Quit",
            text_scale=0.042,
            frameSize=(-0.20, 0.20, -0.05, 0.05),
            frameColor=(0.26, 0.12, 0.12, 0.95),
            text_fg=(1.0, 0.96, 0.96, 1.0),
            pos=(0.98, 0, 0.84),
            command=self._save_and_quit,
        )

        DirectLabel(
            parent=self.menu_root,
            text="Presets",
            text_scale=0.050,
            text_fg=(0.90, 0.93, 0.96, 1.0),
            relief=None,
            pos=(-1.10, 0, 0.66),
            text_align=TextNode.ALeft,
        )
        preset_specs = [("Low", -0.92), ("Medium", -0.66), ("High", -0.40)]
        for label, x in preset_specs:
            DirectButton(
                parent=self.menu_root,
                text=label,
                text_scale=0.040,
                frameSize=(-0.11, 0.11, -0.04, 0.04),
                frameColor=(0.12, 0.15, 0.18, 0.95),
                text_fg=(0.92, 0.95, 0.98, 1.0),
                pos=(x, 0, 0.66),
                command=lambda preset=label: self._apply_quality_preset(preset),
            )

        DirectLabel(
            parent=self.menu_root,
            text="Audio",
            text_scale=0.050,
            text_fg=(0.90, 0.93, 0.96, 1.0),
            relief=None,
            pos=(-1.10, 0, 0.54),
            text_align=TextNode.ALeft,
        )
        self._add_menu_slider("music_volume", "Music volume", -1.10, 0.44, 0.0, 1.0)
        self._add_menu_slider("sound_volume", "Sound volume", -1.10, 0.32, 0.0, 1.0)

        DirectLabel(
            parent=self.menu_root,
            text="Graphics + camera",
            text_scale=0.050,
            text_fg=(0.90, 0.93, 0.96, 1.0),
            relief=None,
            pos=(-1.10, 0, 0.20),
            text_align=TextNode.ALeft,
        )
        self._add_menu_slider("mouse_sensitivity", "Mouse sensitivity", -1.10, 0.10, 0.08, 0.40)
        self._add_menu_slider("fog_density", "Fog amount", -1.10, -0.02, 0.40, 1.60)
        self._add_menu_slider("fov", "Field of view", -1.10, -0.14, 55.0, 95.0)
        self._add_menu_slider("dof_strength", "DOF / blur", -1.10, -0.26, 0.0, 1.0)
        self._add_menu_slider("water_reflections", "Water reflections", -1.10, -0.38, 0.0, 1.0)
        self._add_menu_slider("tile_reflections", "Tile reflections", -1.10, -0.50, 0.0, 1.0)

        DirectButton(
            parent=self.menu_root,
            text="Toggle fullscreen",
            text_scale=0.040,
            frameSize=(-0.17, 0.17, -0.04, 0.04),
            frameColor=(0.12, 0.15, 0.18, 0.95),
            text_fg=(0.92, 0.95, 0.98, 1.0),
            pos=(-0.90, 0, -0.74),
            command=self._toggle_fullscreen,
        )
        DirectButton(
            parent=self.menu_root,
            text="Print assets",
            text_scale=0.040,
            frameSize=(-0.13, 0.13, -0.04, 0.04),
            frameColor=(0.12, 0.15, 0.18, 0.95),
            text_fg=(0.92, 0.95, 0.98, 1.0),
            pos=(-0.56, 0, -0.74),
            command=self._print_assets,
        )
        DirectButton(
            parent=self.menu_root,
            text="Save settings",
            text_scale=0.040,
            frameSize=(-0.14, 0.14, -0.04, 0.04),
            frameColor=(0.12, 0.15, 0.18, 0.95),
            text_fg=(0.92, 0.95, 0.98, 1.0),
            pos=(-0.25, 0, -0.74),
            command=self._save_settings,
        )

        DirectLabel(
            parent=self.menu_root,
            text="Asset slots (replace live)",
            text_scale=0.050,
            text_fg=(0.90, 0.93, 0.96, 1.0),
            relief=None,
            pos=(0.08, 0, 0.66),
            text_align=TextNode.ALeft,
        )
        asset_y = 0.56
        for slot in ("wall", "floor", "water_floor", "water_surface", "ceiling", "light", "beam", "coping", "shadow_npc"):
            self._add_asset_row(slot, 0.10, asset_y)
            asset_y -= 0.11

        self.menu_root.hide()
        self._apply_hud_visibility()

    def _add_menu_slider(self, key: str, label: str, x: float, z: float, min_value: float, max_value: float) -> None:
        DirectLabel(
            parent=self.menu_root,
            text=label,
            text_scale=0.038,
            text_fg=(0.88, 0.90, 0.92, 1.0),
            relief=None,
            pos=(x, 0, z + 0.035),
            text_align=TextNode.ALeft,
        )
        slider = DirectSlider(
            parent=self.menu_root,
            range=(min_value, max_value),
            value=float(self.settings.get(key, min_value)),
            pageSize=(max_value - min_value) / 100.0,
            frameColor=(0.10, 0.12, 0.14, 0.95),
            thumb_frameColor=(0.82, 0.86, 0.90, 1.0),
            frameSize=(-0.34, 0.34, -0.020, 0.020),
            pos=(x + 0.54, 0, z),
            scale=0.65,
            command=lambda setting_key=key: self._on_slider_changed(setting_key),
        )
        value_label = DirectLabel(
            parent=self.menu_root,
            text="",
            text_scale=0.035,
            text_fg=(0.78, 0.84, 0.90, 1.0),
            relief=None,
            pos=(x + 0.95, 0, z + 0.010),
            text_align=TextNode.ALeft,
        )
        self.sliders[key] = slider
        self.value_labels[key] = value_label

    def _add_asset_row(self, slot: str, x: float, z: float) -> None:
        DirectLabel(
            parent=self.menu_root,
            text=slot.replace("_", " ").title(),
            text_scale=0.038,
            text_fg=(0.88, 0.90, 0.92, 1.0),
            relief=None,
            pos=(x, 0, z),
            text_align=TextNode.ALeft,
        )
        label = DirectLabel(
            parent=self.menu_root,
            text="generated",
            text_scale=0.030,
            text_fg=(0.70, 0.78, 0.84, 1.0),
            relief=None,
            pos=(x + 0.36, 0, z),
            text_align=TextNode.ALeft,
        )
        DirectButton(
            parent=self.menu_root,
            text="Replace",
            text_scale=0.034,
            frameSize=(-0.09, 0.09, -0.032, 0.032),
            frameColor=(0.12, 0.15, 0.18, 0.95),
            text_fg=(0.92, 0.95, 0.98, 1.0),
            pos=(1.06, 0, z),
            command=lambda asset_slot=slot: self._replace_asset(asset_slot),
        )
        self.asset_labels[slot] = label

    def _help_text(self) -> str:
        return (
            "WASD Move • Shift Sprint • Ctrl Speed Lock • E Interact • Tab Next Level • H HUD\n"
            "LMB Fire in levels • RMB or N Night Vision • Esc Menu • F11 Fullscreen"
        )

    def _apply_hud_visibility(self) -> None:
        hud_active = bool(self.hud_visible and not self.menu_open)
        for node in (self.ui_status, self.ui_help, self.ui_toast, self.ui_cursor, self.ui_interact, self.nv_scan):
            if hud_active:
                node.show()
            else:
                node.hide()
        if hud_active:
            self.ui_help.setText(self._help_text() if self.help_on else "")
            if not self.help_on:
                self.ui_help.hide()
            if self.toast_t <= 0.0 or not self.ui_toast.getText().strip():
                self.ui_toast.hide()
            if not (self.nightvision_on or self.nightvision_cooldown_left > 0.0):
                self.nv_scan.hide()
        else:
            self.ui_toast.hide()
            self.nv_scan.hide()

    def _toggle_hud(self) -> None:
        self.hud_visible = not self.hud_visible
        self._apply_hud_visibility()
        if self.hud_visible:
            self._toast("HUD on", duration=1.0)
            self._apply_hud_visibility()

    def _toast(self, msg: str, duration: float = 1.6) -> None:
        self.ui_toast.setText(msg)
        self.toast_t = duration
        if self.hud_visible and not self.menu_open:
            self.ui_toast.show()

    def _bind_inputs(self) -> None:
        self.accept("escape", self._on_escape_pressed)
        self.accept("shift-escape", self._save_and_quit)
        self.accept("f1", self._toggle_help)
        self.accept("h", self._toggle_hud)
        self.accept("f11", self._toggle_fullscreen)
        self.accept("f5", self._save_settings)
        self.accept("tab", self._trigger_next_level)
        self.accept("e", self._on_interact)
        self.accept("mouse1", self._fire_weapon)
        self.accept("mouse3", self._toggle_nightvision)
        self.accept("n", self._toggle_nightvision)
        self.accept("window-event", self._on_window_event)
        for key in ("w", "a", "s", "d"):
            self.accept(key, self._set_key, [key, True])
            self.accept(f"{key}-up", self._set_key, [key, False])
        self.accept("shift", self._set_key, ["shift", True])
        self.accept("shift-up", self._set_key, ["shift", False])
        self.accept("control", self._toggle_speed_lock)
        self.accept("lcontrol", self._toggle_speed_lock)
        self.accept("rcontrol", self._toggle_speed_lock)

    def _toggle_nightvision(self) -> None:
        if self.menu_open:
            return
        if self.nightvision_on:
            return
        if self.nightvision_cooldown_left > 0.0:
            self._toast(f"Night vision cooldown {self.nightvision_cooldown_left:.1f}s")
            return
        self.nightvision_on = True
        self.nightvision_time_left = NIGHTVISION_DURATION
        self.nightvision_cooldown_left = 0.0
        self._apply_nightvision_state()
        self._play_weapon_sfx("nightvision_on")
        self._toast(f"Night vision on {NIGHTVISION_DURATION:.0f}s")

    def _set_nightvision_enabled(self, enabled: bool, *, start_cooldown: bool = False) -> None:
        enabled = bool(enabled)
        if self.nightvision_on == enabled and not start_cooldown:
            return
        self.nightvision_on = enabled
        if enabled:
            self.nightvision_time_left = NIGHTVISION_DURATION
            self.nightvision_cooldown_left = 0.0
            self._play_weapon_sfx("nightvision_on")
        else:
            self.nightvision_time_left = 0.0
            if start_cooldown:
                self.nightvision_cooldown_left = NIGHTVISION_COOLDOWN
                self._play_weapon_sfx("nightvision_off")
        self._apply_nightvision_state()

    def _toggle_speed_lock(self) -> None:
        if self.menu_open:
            return
        self.speed_lock = not self.speed_lock
        self._toast("Speed lock on" if self.speed_lock else "Speed lock off", duration=1.2)

    def _apply_environment_mood(self) -> None:
        mix = clamp(float(getattr(self, "shadow_darkness_mix", 0.0)), 0.0, 1.0)
        density = clamp(float(self.settings.get("fog_density", 1.0)), 0.40, 1.60)
        is_hub = self._is_hub_level()
        level_settings = {} if is_hub else self._external_level_settings()
        if self.nightvision_on:
            bg = Vec4(0.02, 0.08, 0.03, 1.0)
            fog = Vec4(0.08, 0.22, 0.10, 1.0)
            amb = Vec4(0.22, 0.34, 0.20, 1.0)
            sun = Vec4(0.10, 0.16, 0.10, 1.0)
            fill = Vec4(0.08, 0.18, 0.10, 1.0)
            lift = Vec4(0.11, 0.24, 0.12, 1.0)
            dark_bg = Vec4(0.0, 0.025, 0.01, 1.0)
            dark_fog = Vec4(0.03, 0.09, 0.04, 1.0)
            dark_amb = Vec4(0.08, 0.12, 0.07, 1.0)
            dark_sun = Vec4(0.035, 0.055, 0.03, 1.0)
            dark_fill = Vec4(0.025, 0.050, 0.028, 1.0)
            dark_lift = Vec4(0.03, 0.06, 0.03, 1.0)
            self.ui_cursor.setFg((0.74, 1.0, 0.76, 0.82))
            self.nv_overlay.show()
            if self.hud_visible and not self.menu_open:
                self.nv_scan.show()
            if hasattr(self, "weapon_root") and self.weapon_root is not None and not self.weapon_root.isEmpty():
                self.weapon_root.setColorScale(0.82, 1.10, 0.86, 1.0)
        else:
            if is_hub:
                bg = Vec4(0.042, 0.036, 0.033, 1.0)
                fog = Vec4(0.105, 0.096, 0.090, 1.0)
                amb = Vec4(0.14, 0.126, 0.114, 1.0)
                sun = Vec4(0.030, 0.026, 0.024, 1.0)
                fill = Vec4(0.020, 0.017, 0.016, 1.0)
                lift = Vec4(0.032, 0.028, 0.026, 1.0)
                dark_bg = Vec4(0.014, 0.012, 0.012, 1.0)
                dark_fog = Vec4(0.050, 0.044, 0.040, 1.0)
                dark_amb = Vec4(0.050, 0.044, 0.040, 1.0)
                dark_sun = Vec4(0.014, 0.012, 0.012, 1.0)
                dark_fill = Vec4(0.010, 0.009, 0.009, 1.0)
                dark_lift = Vec4(0.019, 0.017, 0.016, 1.0)
            else:
                bg = self._vec4_from_value(level_settings.get("bg_color"), self._default_bg_color)
                fog = self._vec4_from_value(level_settings.get("fog_color"), self._default_fog_color)
                amb = self._vec4_from_value(level_settings.get("ambient_light"), self._default_amb_color)
                sun = self._vec4_from_value(level_settings.get("sun_light"), self._default_sun_color)
                fill = self._vec4_from_value(level_settings.get("fill_light"), self._default_fill_color)
                lift = self._vec4_from_value(level_settings.get("lift_light"), self._default_lift_color)
                dark_bg = self._vec4_from_value(level_settings.get("dark_bg_color"), Vec4(0.015, 0.017, 0.019, 1.0))
                dark_fog = self._vec4_from_value(level_settings.get("dark_fog_color"), Vec4(0.085, 0.09, 0.10, 1.0))
                dark_amb = self._vec4_from_value(level_settings.get("dark_ambient_light"), Vec4(0.016, 0.018, 0.020, 1.0))
                dark_sun = self._vec4_from_value(level_settings.get("dark_sun_light"), Vec4(0.042, 0.044, 0.047, 1.0))
                dark_fill = self._vec4_from_value(level_settings.get("dark_fill_light"), Vec4(0.010, 0.011, 0.013, 1.0))
                dark_lift = self._vec4_from_value(level_settings.get("dark_lift_light"), Vec4(0.013, 0.014, 0.016, 1.0))
            self.ui_cursor.setFg((0.94, 0.98, 0.95, 0.55))
            self.nv_overlay.hide()
            if self.nightvision_cooldown_left <= 0.0:
                self.nv_scan.hide()
            if hasattr(self, "weapon_root") and self.weapon_root is not None and not self.weapon_root.isEmpty():
                self.weapon_root.clearColorScale()

        def blend(a: Vec4, b: Vec4, t: float) -> Vec4:
            return Vec4(a.x + (b.x - a.x) * t, a.y + (b.y - a.y) * t, a.z + (b.z - a.z) * t, 1.0)

        self.setBackgroundColor(blend(bg, dark_bg, mix))
        self.scene_fog.setColor(blend(fog, dark_fog, mix))
        self.amb_np.node().setColor(blend(amb, dark_amb, mix))
        self.sun_np.node().setColor(blend(sun, dark_sun, mix))
        self.fill_np.node().setColor(blend(fill, dark_fill, mix))
        self.lift_np.node().setColor(blend(lift, dark_lift, mix))

        if is_hub:
            extra_density = 0.95 + mix * 0.65
            start = max(4.0, 10.0 / (density * extra_density))
            end = max(start + 8.0, 64.0 / (density * (1.0 + mix * 0.85)))
        else:
            fog_start = float(level_settings.get("fog_start", FOG_START))
            fog_end = float(level_settings.get("fog_end", FOG_END))
            dark_fog_start = float(level_settings.get("dark_fog_start", max(0.6, fog_start * 0.55)))
            dark_fog_end = float(level_settings.get("dark_fog_end", max(dark_fog_start + 2.0, fog_end * 0.42)))
            base_start = fog_start + (dark_fog_start - fog_start) * mix
            base_end = fog_end + (dark_fog_end - fog_end) * mix
            start = max(0.02, base_start / density)
            end = max(start + 1.2, base_end / density)
        self.scene_fog.setLinearRange(start, end)

    def _apply_nightvision_state(self) -> None:
        self._apply_environment_mood()

    def _fire_weapon(self) -> None:
        if self.menu_open or self._is_hub_level() or not hasattr(self, "weapon_root") or self.weapon_root.isEmpty():
            return
        self.shots_fired += 1
        self._play_weapon_sfx("fire")
        cam_quat = self.camera.getQuat(self.render)
        forward = cam_quat.getForward()
        right = cam_quat.getRight()
        up = cam_quat.getUp()
        spawn = self.camera.getPos(self.render) + forward * 1.35 + right * 0.04 + up * -0.10
        root = self.render.attachNewNode(f"shockwave_{self.shots_fired}")
        root.setPos(spawn)
        root.setQuat(cam_quat)
        root.setLightOff()
        root.setShaderOff()
        root.setTransparency(TransparencyAttrib.MAlpha)
        root.setDepthWrite(False)
        root.setBin("fixed", 18)
        core = self._add_box(root, Vec3(0.0, 0.95, 0.0), Vec3(0.07, 1.90, 0.07), self.weapon_indicator_tex)
        core.setColorScale(0.28, 0.95, 1.00, 0.94)
        halo_a = self._add_plane(root, Vec3(0.0, 0.88, 0.0), 0.42, 1.60, (0, 0, 0), self.weapon_indicator_tex, 1.0, 1.0, True)
        halo_a.setColorScale(0.10, 0.90, 1.00, 0.30)
        halo_b = self._add_plane(root, Vec3(0.0, 0.88, 0.0), 0.42, 1.60, (90, 0, 0), self.weapon_indicator_tex, 1.0, 1.0, True)
        halo_b.setColorScale(0.10, 0.90, 1.00, 0.30)
        ring = self._add_plane(root, Vec3(0.0, 0.28, 0.0), 0.26, 0.26, (0, -90, 0), self.weapon_indicator_tex, 1.0, 1.0, True)
        ring.setColorScale(0.18, 1.00, 0.92, 0.70)
        flash = self._add_plane(root, Vec3(0.0, 0.10, 0.0), 0.36, 0.24, (0, -90, 0), self.weapon_indicator_tex, 1.0, 1.0, True)
        flash.setColorScale(0.52, 1.00, 0.92, 0.34)
        self.active_projectiles.append({"root": root, "core": core, "ring": ring, "flash": flash, "halos": [halo_a, halo_b], "vel": forward * 58.0, "life": 0.0, "ttl": 0.34})
        self._hit_shadow_npc(self.camera.getPos(self.render), forward)
        self.weapon_root.setZ(self.weapon_root.getZ() - 0.010)

    def _update_projectiles(self, dt: float) -> None:
        if not self.active_projectiles:
            return
        alive: List[Dict[str, Any]] = []
        for proj in self.active_projectiles:
            root = proj.get("root")
            if root is None or root.isEmpty():
                continue
            proj["life"] += dt
            life = float(proj["life"])
            ttl = float(proj["ttl"])
            root.setPos(root.getPos() + proj["vel"] * dt)
            pos = root.getPos(self.render)
            if self._cell_kind_at_pos(pos.x, pos.y) == SOLID or life >= ttl:
                root.removeNode()
                continue
            fade = clamp(1.0 - life / ttl, 0.0, 1.0)
            for idx, halo in enumerate(proj.get("halos", [])):
                if halo is not None and not halo.isEmpty():
                    halo.setColorScale(0.10, 0.90, 1.00, 0.30 * fade * (1.0 - idx * 0.10))
            ring = proj.get("ring")
            if ring is not None and not ring.isEmpty():
                ring_scale = 1.0 + life * 5.0
                ring.setScale(ring_scale)
                ring.setColorScale(0.18, 1.00, 0.92, 0.72 * fade)
            flash = proj.get("flash")
            if flash is not None and not flash.isEmpty():
                flash.setColorScale(0.52, 1.00, 0.92, max(0.0, 0.34 - life * 4.2))
            core = proj.get("core")
            if core is not None and not core.isEmpty():
                core.setColorScale(0.28, 0.95, 1.00, 0.95 * fade)
            alive.append(proj)
        self.active_projectiles = alive

    def _on_escape_pressed(self) -> None:
        if not self.menu_open:
            self.esc_quit_armed = True
            self._toggle_menu()
            self._toast("Menu open • Press Esc again to quit")
            return
        self._save_and_quit()

    def _toggle_help(self) -> None:
        self.help_on = not self.help_on
        self.settings["help_on"] = self.help_on
        self._apply_hud_visibility()

    def _toggle_menu(self) -> None:
        self.menu_open = not self.menu_open
        if self.menu_open:
            self.menu_root.show()
            self._refresh_asset_labels()
            self._print_assets()
        else:
            self.menu_root.hide()
            self.esc_quit_armed = False
        self._apply_hud_visibility()
        self._update_mouse_capture(force=True)

    def _toggle_fullscreen(self) -> None:
        self.is_fullscreen = not self.is_fullscreen
        self.settings["fullscreen"] = self.is_fullscreen
        props = WindowProperties()
        props.setFullscreen(self.is_fullscreen)
        self.win.requestProperties(props)
        self._toast("Fullscreen" if self.is_fullscreen else "Windowed")

    def _set_key(self, key: str, value: bool) -> None:
        self.keys[key] = value

    def _register_asset_slots(self) -> None:
        self.asset_slots = {
            "wall": self.wall_tex,
            "floor": self.floor_tex,
            "water_floor": self.water_floor_tex,
            "water_surface": self.water_tex,
            "ceiling": self.ceiling_tex,
            "light": self.light_tex,
            "beam": self.beam_tex,
            "coping": self.coping_tex,
            "shadow_npc": self.shadow_npc_tex,
        }
        self.asset_slot_clamp = {
            "wall": False,
            "floor": False,
            "water_floor": False,
            "water_surface": False,
            "ceiling": False,
            "light": True,
            "beam": True,
            "coping": False,
            "shadow_npc": True,
        }
        self.default_asset_paths = self._default_asset_paths()
        self.asset_sources = {
            slot: str(self.default_asset_paths[slot]) if self.default_asset_paths[slot].exists() else "generated"
            for slot in self.asset_slots
        }

    def _apply_asset_overrides(self) -> None:
        for slot, tex in self.asset_slots.items():
            override_path = self.asset_overrides.get(slot)
            default_path = self.default_asset_paths.get(slot)
            if override_path and self._load_texture_from_path(tex, override_path, self.asset_slot_clamp.get(slot, False)):
                self.asset_sources[slot] = override_path
                continue
            if default_path and default_path.exists() and self._load_texture_from_path(tex, str(default_path), self.asset_slot_clamp.get(slot, False)):
                self.asset_sources[slot] = str(default_path)
                continue
            self.asset_sources[slot] = "generated"

    def _load_texture_from_path(self, tex: Texture, path: str, clamp_mode: bool = False) -> bool:
        try:
            img = PNMImage()
            if not img.read(Filename.fromOsSpecific(path)):
                print(f"[Assets] Failed to read: {path}")
                return False
            tex.load(img)
            self._finish_tex(tex, clamp_mode=clamp_mode)
            return True
        except Exception as exc:
            print(f"[Assets] Failed to apply {path}: {exc}")
            return False

    def _replace_asset(self, slot: str) -> None:
        try:
            import tkinter as tk
            from tkinter import filedialog
        except Exception as exc:
            self._toast("tkinter is unavailable on this system")
            print(f"[Assets] tkinter unavailable: {exc}")
            return

        root = tk.Tk()
        root.withdraw()
        try:
            root.attributes("-topmost", True)
        except Exception:
            pass
        path = filedialog.askopenfilename(
            title=f"Replace {slot}",
            initialdir=str(self.texture_root),
            filetypes=[("Image Files", "*.png *.jpg *.jpeg *.bmp *.tga"), ("All Files", "*.*")],
        )
        root.destroy()
        if not path:
            return

        if self._load_texture_from_path(self.asset_slots[slot], path, self.asset_slot_clamp.get(slot, False)):
            self.asset_overrides[slot] = path
            self.asset_sources[slot] = path
            self.settings["asset_overrides"] = dict(self.asset_overrides)
            self._refresh_asset_labels()
            self._print_assets()
            self._toast(f"Replaced {slot.replace('_', ' ')}")
        else:
            self._toast(f"Could not load {Path(path).name}")

    def _refresh_asset_labels(self) -> None:
        for slot, label in self.asset_labels.items():
            source = self._display_asset_source(self.asset_sources.get(slot, "generated"))
            if source == "generated":
                display = "generated"
            else:
                display = source
                if len(display) > 26:
                    display = display[:23] + "..."
            label["text"] = display

    def _print_assets(self) -> None:
        print("\n[Assets] Current texture slots")
        print("-" * 56)
        print(f"texture folder : {self.texture_root}")
        print(f"music loops    : {self.music_loop_root}")
        print(f"shadow loops   : {self.shadow_loop_root}")
        for slot in ("wall", "floor", "water_floor", "water_surface", "ceiling", "light", "beam", "coping", "shadow_npc"):
            print(f"{slot:14s}: {self._display_asset_source(self.asset_sources.get(slot, 'generated'))}")
        loop_files = self._music_loop_files()
        if loop_files:
            print("[Music] Loop files")
            for path in loop_files:
                print(f"  - {path.name}")
        else:
            print("[Music] No loop files found yet. Put .wav/.ogg/.mp3 files into music/loops")
        shadow_loop_files = self._shadow_loop_files()
        if shadow_loop_files:
            print("[Music] Shadow enemy loop files")
            for path in shadow_loop_files:
                print(f"  - {path.name}")
        else:
            print("[Music] Put shadow enemy loops into music/loops/shadow_enemy or use shadow_enemy.wav/.ogg/.mp3 in music/loops")
        weapon_sfx = self._weapon_sfx_files()
        if weapon_sfx:
            print("[SFX] Dark rifle")
            for slot, path in weapon_sfx.items():
                status = self.audio_debug.get(f"weapon:{slot}", "not loaded yet")
                print(f"  - {slot}: {path.name} [{status}]")
        else:
            print(f"[SFX] Put weapon .mp3/.wav/.ogg files into {self.weapon_sfx_root}")
        if self.audio_debug:
            print("[Audio] Status")
            for key in sorted(self.audio_debug):
                print(f"  - {key}: {self.audio_debug[key]}")

    def _format_setting(self, key: str, value: float) -> str:
        if key == "mouse_sensitivity":
            return f"{value:.2f}"
        if key in {"music_volume", "sound_volume", "water_reflections", "tile_reflections", "dof_strength"}:
            return f"{int(round(value * 100.0))}%"
        if key == "fog_density":
            return f"{value:.2f}x"
        if key == "fov":
            return f"{value:.0f}°"
        return f"{value:.2f}"

    def _sync_sliders_from_settings(self) -> None:
        self._syncing_ui = True
        try:
            for key, slider in self.sliders.items():
                slider["value"] = float(self.settings.get(key, slider["range"][0]))
        finally:
            self._syncing_ui = False
        self._refresh_value_labels()

    def _refresh_value_labels(self) -> None:
        for key, label in self.value_labels.items():
            label["text"] = self._format_setting(key, float(self.settings.get(key, 0.0)))
        self.menu_preset_label["text"] = f"Preset: {self.settings.get('quality_preset', 'Custom')}"

    def _on_slider_changed(self, key: str, value: Optional[float] = None) -> None:
        if value is None:
            slider = self.sliders.get(key)
            if slider is None:
                return
            try:
                value = float(slider["value"])
            except Exception:
                return
        self.settings[key] = float(value)
        if not self._syncing_ui:
            self.settings["quality_preset"] = "Custom"
        self._apply_all_settings()

    def _apply_quality_preset(self, preset: str) -> None:
        preset = self._normalize_quality_preset(preset)
        presets = {
            "Low": {
                "mouse_sensitivity": 0.34,
                "fog_density": 0.82,
                "fov": 66.0,
                "dof_strength": 0.0,
                "water_reflections": 0.0,
                "tile_reflections": 0.0,
            },
            "Medium": {
                "mouse_sensitivity": 0.36,
                "fog_density": 1.00,
                "fov": 68.0,
                "dof_strength": 0.0,
                "water_reflections": 0.30,
                "tile_reflections": 0.18,
            },
            "High": {
                "mouse_sensitivity": 0.40,
                "fog_density": 1.08,
                "fov": 70.0,
                "dof_strength": 0.30,
                "water_reflections": 0.65,
                "tile_reflections": 0.42,
            },
        }
        for key, value in presets.get(preset, presets["Low"]).items():
            self.settings[key] = value
        self.settings["quality_preset"] = preset
        self._sync_sliders_from_settings()
        self._apply_all_settings()
        self._toast(f"{preset} preset applied")

    def _apply_all_settings(self, initial: bool = False) -> None:
        self.settings["quality_preset"] = self._normalize_quality_preset(self.settings.get("quality_preset", "Low"))
        self._apply_lens_settings()
        self._apply_fog_settings()
        self._apply_audio_settings()
        self._apply_dof_settings()
        self._apply_reflection_settings()
        self._apply_water_quality_settings()
        self._refresh_value_labels()
        self._apply_nightvision_state()
        if initial:
            self._apply_hud_visibility()

    def _apply_lens_settings(self) -> None:
        lens = getattr(self, "camLens", None)
        if lens is None and hasattr(self, "cam") and self.cam is not None:
            try:
                lens = self.cam.node().getLens()
            except Exception:
                lens = None
        if lens is not None:
            lens.setFov(float(self.settings.get("fov", 68.0)))

    def _apply_fog_settings(self) -> None:
        self._apply_environment_mood()

    def _apply_audio_settings(self) -> None:
        music_volume = clamp(float(self.settings.get("music_volume", 0.72)), 0.0, 1.0)
        sound_volume = clamp(float(self.settings.get("sound_volume", 0.92)), 0.0, 1.0)
        try:
            if getattr(self, "musicManager", None) is not None:
                self.musicManager.setVolume(music_volume)
        except Exception:
            pass
        try:
            if getattr(self, "music_loop", None) is not None:
                base_music = music_volume * (1.0 - 0.46 * clamp(getattr(self, "shadow_music_mix", 0.0), 0.0, 1.0))
                self.music_loop.setVolume(base_music)
        except Exception:
            pass
        try:
            if getattr(self, "shadow_music_loop", None) is not None:
                enemy_music = music_volume * clamp(getattr(self, "shadow_music_mix", 0.0), 0.0, 1.0) * 0.92
                self.shadow_music_loop.setVolume(enemy_music)
        except Exception:
            pass
        try:
            if getattr(self, "sfxManagerList", None):
                for manager in self.sfxManagerList:
                    if manager is not None:
                        manager.setVolume(sound_volume)
        except Exception:
            pass
        for slot, sound in list(self.weapon_sfx.items()):
            if sound is None:
                continue
            base = 1.0 if slot == "fire" else 0.82
            try:
                sound.setVolume(base * sound_volume)
            except Exception:
                pass
        if getattr(self, "transition_sfx", None) is not None:
            try:
                self.transition_sfx.setVolume(0.90 * sound_volume)
            except Exception:
                pass

    def _apply_water_quality_settings(self) -> None:
        preset = str(self.settings.get("quality_preset", "Custom"))
        water_strength = clamp(float(self.settings.get("water_reflections", 0.0)), 0.0, 1.0)
        tile_strength = clamp(float(self.settings.get("tile_reflections", 0.0)), 0.0, 1.0)
        if self._level_uses_static_water_by_default():
            water_strength = 0.0
            tile_strength = 0.0
        realistic = preset != "Low" or water_strength >= 0.18

        for surf in self.water_surface_cards:
            if surf.isEmpty():
                continue
            alpha = 0.46 if not realistic else 0.64 + water_strength * 0.12
            surf.setColorScale(0.92, 0.98, 1.02, clamp(alpha, 0.0, 1.0))

        for np, _, _ in self.water_detail_overlays:
            if np.isEmpty():
                continue
            if realistic:
                np.show()
                np.setColorScale(0.96, 1.0, 1.0, 0.18 + water_strength * 0.30)
            else:
                np.hide()

        for np, _, _ in self.deck_gloss_overlays:
            if np.isEmpty():
                continue
            if tile_strength <= 0.001:
                np.hide()
            else:
                np.show()
                np.setColorScale(0.97, 0.99, 1.0, 0.12 + tile_strength * 0.22)

    def _apply_dof_settings(self) -> None:
        strength = clamp(float(self.settings.get("dof_strength", 0.0)), 0.0, 1.0)
        if self.filters is None:
            return
        try:
            if hasattr(self.filters, "setBlurSharpen"):
                if strength <= 0.001:
                    if hasattr(self.filters, "delBlurSharpen"):
                        self.filters.delBlurSharpen()
                    else:
                        self.filters.setBlurSharpen(1.0)
                else:
                    blur_amount = clamp(1.0 - strength * 0.85, 0.15, 1.0)
                    self.filters.setBlurSharpen(blur_amount)
            elif hasattr(self.filters, "setDepthOfField"):
                try:
                    if strength > 0.001:
                        self.filters.setDepthOfField(focus=0.55, blur=0.04 + strength * 0.08, maxBlur=0.006 + strength * 0.02)
                    else:
                        self.filters.setDepthOfField(focus=0.55, blur=0.0, maxBlur=0.0)
                except TypeError:
                    pass
        except Exception as exc:
            print(f"[Filters] DOF update failed: {exc}")

    def _apply_reflection_settings(self) -> None:
        tile_strength = clamp(float(self.settings.get("tile_reflections", 0.0)), 0.0, 1.0)
        water_strength = clamp(float(self.settings.get("water_reflections", 0.0)), 0.0, 1.0)
        if self._level_uses_static_water_by_default():
            tile_strength = 0.0
            water_strength = 0.0

        for np, _, _ in self.deck_reflection_overlays:
            if np.isEmpty():
                continue
            if tile_strength <= 0.001:
                np.hide()
            else:
                np.show()
                np.setColorScale(0.92, 0.96, 1.0, 0.52 * tile_strength)
        for np, _, _ in self.water_reflection_overlays:
            if np.isEmpty():
                continue
            if water_strength <= 0.001:
                np.hide()
            else:
                np.show()
                np.setColorScale(0.96, 0.99, 1.0, 0.74 * water_strength)

    def _save_and_quit(self) -> None:
        self._save_settings()
        self.userExit()

    def userExit(self) -> None:
        self._save_settings()
        super().userExit()

    def _clear_runtime_world(self) -> None:
        for proj in self.active_projectiles:
            root = proj.get("root")
            if root is not None and not root.isEmpty():
                root.removeNode()
        self.active_projectiles = []
        self._despawn_shadow_npc()

        if hasattr(self, "world_root") and self.world_root is not None and not self.world_root.isEmpty():
            self.world_root.removeNode()
        self.world_root = self.render.attachNewNode("world_root")

        self.module_nodes.clear()
        self.module_data_cache.clear()
        self.deck_surfaces.clear()
        self.water_surfaces.clear()
        self.water_surface_cards.clear()
        self.deck_reflection_overlays.clear()
        self.water_reflection_overlays.clear()
        self.water_detail_overlays.clear()
        self.deck_gloss_overlays.clear()
        self.dynamic_lights.clear()
        self.sun_beams.clear()
        self.pattern_overlays.clear()
        self.module_sun_lights.clear()
        self.hub_doors.clear()
        self.hub_nearby_door_index = None
        self.pending_external_hub_link = None
        self.shadow_darkness_mix = 0.0
        self.shadow_music_mix = 0.0
        self.level_runtime_state.clear()
        self._apply_environment_mood()
        self._apply_audio_settings()

    def _load_level(self, level_index: int) -> None:
        self._refresh_available_levels()
        level_index = max(HUB_LEVEL, int(level_index))
        if level_index != HUB_LEVEL and level_index not in self.available_level_indices:
            level_index = self.available_level_indices[0] if self.available_level_indices else 1
        if level_index == self.current_level:
            return
        self.current_level = level_index
        if level_index > HUB_LEVEL:
            self.last_non_hub_level = level_index
            self.level_time_remaining = float(self.level_time_limit)
        else:
            self.level_time_remaining = 0.0
        self.external_level_settings_cache.pop(level_index, None)
        self._configure_asset_context(level_index)
        self._ensure_asset_dirs()
        self.shadow_npc_revealed = False
        self.shadow_npc_health = self.shadow_npc_max_health
        self.return_to_halls_unlocked = level_index > HUB_LEVEL and not self._shadow_enabled_for_level(level_index)
        if self._is_hub_level():
            self.player_pos = Vec3(MODULE_SIZE * 0.5, CELL * 1.6, 0.0)
            self.yaw = 0.0
            self.pitch = 0.0
        else:
            self.player_pos = Vec3(MODULE_SIZE * 0.5, MODULE_SIZE * 0.5, 0.0)
        self.pending_external_hub_link = None
        self._clear_runtime_world()
        self._apply_asset_overrides()
        self._refresh_asset_labels()
        self._reload_level_music()
        module = self._external_level_module(level_index)
        if module is not None and hasattr(module, "on_level_load"):
            try:
                module.on_level_load(self)
            except Exception as exc:
                print(f"[LevelLoader] on_level_load failed for level {level_index}: {exc}")
        self._stream_modules(force=True)
        if self._shadow_enabled_for_level():
            self._spawn_shadow_npc(force=True)
        self._refresh_level_features()
        self._update_hub_interact_prompt()
        self._toast(self._level_display_name())

    # ----------------------------
    # World generation
    # ----------------------------
    def _module_seed(self, mx: int, my: int) -> int:
        return hash_u32(mx, my, self.current_level, 0x5A17BEEF)

    def _edge_openings(self, ax: int, ay: int, always_open: bool) -> Set[int]:
        rnd = Random(hash_u32(ax, ay, 0xA47C))
        rows: Set[int] = set()
        if always_open or rnd.random() < 0.76:
            spans = 1 + (1 if rnd.random() < 0.28 else 0)
            for _ in range(spans):
                width = 2 + (1 if rnd.random() < 0.34 else 0)
                start = 1 + rnd.randrange(max(1, MODULE_CELLS - width - 2))
                for i in range(start, min(MODULE_CELLS - 1, start + width)):
                    rows.add(i)
        if not rows and always_open:
            mid = MODULE_CELLS // 2
            rows.update({mid, max(1, mid - 1)})
        return rows

    def _module_portals(self, mx: int, my: int) -> Dict[str, Set[int]]:
        return {
            "west": self._edge_openings(mx, my, True),
            "east": self._edge_openings(mx + 1, my, True),
            "south": self._edge_openings(my, mx, False),
            "north": self._edge_openings(my + 1, mx, False),
        }

    def _module_data(self, mx: int, my: int) -> ModuleData:
        key = (mx, my)
        if key in self.module_data_cache:
            return self.module_data_cache[key]

        if self._is_hub_level():
            grid = [[SOLID for _ in range(MODULE_CELLS)] for __ in range(MODULE_CELLS)]
            if mx == 0:
                for y in range(MODULE_CELLS):
                    for x in range(4, 8):
                        grid[y][x] = DECK
            data = ModuleData(grid=grid, style_id=5)
            self.module_data_cache[key] = data
            return data

        module = self._external_level_module()
        if module is not None and hasattr(module, "build_module_data"):
            try:
                raw = module.build_module_data(self, mx, my)
                if isinstance(raw, ModuleData):
                    data = raw
                elif isinstance(raw, dict) and isinstance(raw.get("grid"), list):
                    data = ModuleData(grid=raw["grid"], style_id=int(raw.get("style_id", 0)))
                else:
                    data = None
                if data is not None:
                    self.module_data_cache[key] = data
                    return data
            except Exception as exc:
                print(f"[LevelLoader] build_module_data failed for level {self.current_level}: {exc}")

        portals = self._module_portals(mx, my)
        style_id = self._module_seed(mx, my) % len(STYLE_NAMES)
        rnd = Random(self._module_seed(mx, my) ^ 0xC0FFEE)
        grid = [[SOLID for _ in range(MODULE_CELLS)] for __ in range(MODULE_CELLS)]
        protected: Set[Tuple[int, int]] = set()

        def carve(x: int, y: int, kind: int = DECK, protect: bool = False) -> None:
            if 0 <= x < MODULE_CELLS and 0 <= y < MODULE_CELLS:
                if kind > grid[y][x]:
                    grid[y][x] = kind
                elif grid[y][x] == SOLID:
                    grid[y][x] = kind
                if protect:
                    protected.add((x, y))

        def carve_room(x0: int, y0: int, x1: int, y1: int, kind: int = DECK, protect: bool = False) -> None:
            for y in range(max(0, y0), min(MODULE_CELLS, y1 + 1)):
                for x in range(max(0, x0), min(MODULE_CELLS, x1 + 1)):
                    carve(x, y, kind, protect)

        def carve_line(x0: int, y0: int, x1: int, y1: int, width: int = 1, kind: int = DECK, protect: bool = False) -> None:
            if x0 == x1:
                lo, hi = sorted((y0, y1))
                for y in range(lo, hi + 1):
                    for dx in range(-width + 1, width):
                        carve(x0 + dx, y, kind, protect)
            elif y0 == y1:
                lo, hi = sorted((x0, x1))
                for x in range(lo, hi + 1):
                    for dy in range(-width + 1, width):
                        carve(x, y0 + dy, kind, protect)

        def carve_corridor(a: Tuple[int, int], b: Tuple[int, int], width: int = 1, protect: bool = False) -> None:
            ax, ay = a
            bx, by = b
            if hash_u32(mx, my, ax, ay, bx, by) & 1:
                carve_line(ax, ay, bx, ay, width, DECK, protect)
                carve_line(bx, ay, bx, by, width, DECK, protect)
            else:
                carve_line(ax, ay, ax, by, width, DECK, protect)
                carve_line(ax, by, bx, by, width, DECK, protect)

        seeds: List[Tuple[int, int]] = []
        for row in sorted(portals["west"]):
            carve(0, row, DECK, True)
            carve(1, row, DECK, True)
            seeds.append((1, row))
        for row in sorted(portals["east"]):
            carve(MODULE_CELLS - 1, row, DECK, True)
            carve(MODULE_CELLS - 2, row, DECK, True)
            seeds.append((MODULE_CELLS - 2, row))
        for col in sorted(portals["south"]):
            carve(col, 0, DECK, True)
            carve(col, 1, DECK, True)
            seeds.append((col, 1))
        for col in sorted(portals["north"]):
            carve(col, MODULE_CELLS - 1, DECK, True)
            carve(col, MODULE_CELLS - 2, DECK, True)
            seeds.append((col, MODULE_CELLS - 2))

        center = (MODULE_CELLS // 2, MODULE_CELLS // 2)
        carve(center[0], center[1], DECK, True)
        if not seeds:
            seeds = [center]
        for seed in seeds:
            carve_corridor(seed, center, 1, True)
        for i in range(1, len(seeds)):
            carve_corridor(seeds[i - 1], seeds[i], 1, True)

        # Style passes
        if style_id == 0:  # Grand Hall
            carve_room(1, 1, MODULE_CELLS - 2, MODULE_CELLS - 2, DECK)
            mid = MODULE_CELLS // 2
            for x in range(2, MODULE_CELLS - 2):
                if x in (mid - 1, mid, mid + 1):
                    continue
                carve(x, mid - 3, WATER)
                carve(x, mid + 3, WATER)
            for y in range(2, MODULE_CELLS - 2):
                for x in (2, MODULE_CELLS - 3):
                    if (x, y) not in protected and y % 4 != 1:
                        grid[y][x] = SOLID

        elif style_id == 1:  # Maze Canals
            for seed in seeds + [center]:
                x, y = seed
                for _ in range(6):
                    length = 3 + rnd.randrange(6)
                    dx, dy = [(1, 0), (-1, 0), (0, 1), (0, -1)][rnd.randrange(4)]
                    wx, wy = x, y
                    for _ in range(length):
                        carve(wx, wy, DECK)
                        if rnd.random() < 0.24:
                            carve(wx, wy, WATER)
                        if rnd.random() < 0.32:
                            dx, dy = [(1, 0), (-1, 0), (0, 1), (0, -1)][rnd.randrange(4)]
                        wx = int(clamp(wx + dx, 1, MODULE_CELLS - 2))
                        wy = int(clamp(wy + dy, 1, MODULE_CELLS - 2))
                        carve(wx, wy, DECK)
            for _ in range(10):
                x = 1 + rnd.randrange(MODULE_CELLS - 2)
                y = 1 + rnd.randrange(MODULE_CELLS - 2)
                if grid[y][x] != SOLID:
                    carve_room(x - 1, y - 1, x + 1, y + 1, DECK)

        elif style_id == 2:  # Arcade Basin
            dominant_vertical = len(portals["north"]) + len(portals["south"]) > len(portals["west"]) + len(portals["east"])
            mid = MODULE_CELLS // 2
            if dominant_vertical:
                carve_room(mid - 1, 0, mid + 1, MODULE_CELLS - 1, DECK, True)
                carve_room(1, 2, MODULE_CELLS - 2, MODULE_CELLS - 3, DECK)
                carve_room(3, 3, MODULE_CELLS - 4, MODULE_CELLS - 4, WATER)
                carve_line(mid, 1, mid, MODULE_CELLS - 2, 1, DECK, True)
            else:
                carve_room(0, mid - 1, MODULE_CELLS - 1, mid + 1, DECK, True)
                carve_room(2, 1, MODULE_CELLS - 3, MODULE_CELLS - 2, DECK)
                carve_room(3, 3, MODULE_CELLS - 4, MODULE_CELLS - 4, WATER)
                carve_line(1, mid, MODULE_CELLS - 2, mid, 1, DECK, True)
            for x in range(2, MODULE_CELLS - 2, 3):
                for y in range(2, MODULE_CELLS - 2, 3):
                    if (x, y) not in protected and rnd.random() < 0.35:
                        grid[y][x] = SOLID

        elif style_id == 3:  # Sanctum
            carve_room(1, 1, MODULE_CELLS - 2, MODULE_CELLS - 2, DECK)
            carve_room(3, 3, MODULE_CELLS - 4, MODULE_CELLS - 4, WATER)
            mid = MODULE_CELLS // 2
            carve_line(1, mid, MODULE_CELLS - 2, mid, 1, DECK, True)
            carve_line(mid, 1, mid, MODULE_CELLS - 2, 1, DECK, True)
            for x in (2, MODULE_CELLS - 3):
                for y in (2, MODULE_CELLS - 3):
                    if (x, y) not in protected:
                        grid[y][x] = SOLID

        else:  # Gallery
            carve_room(1, 1, MODULE_CELLS - 2, MODULE_CELLS - 2, DECK)
            for x in range(2, MODULE_CELLS - 2):
                if x % 3 == 1:
                    carve_line(x, 2, x, MODULE_CELLS - 3, 1, WATER)
            for y in range(2, MODULE_CELLS - 2, 3):
                if rnd.random() < 0.75:
                    carve_room(2, y, MODULE_CELLS - 3, y, DECK)
            mid = MODULE_CELLS // 2
            carve_line(1, mid, MODULE_CELLS - 2, mid, 1, DECK, True)

        reachable = self._flood_walkable(grid, list(seeds) if seeds else [center])
        for y in range(MODULE_CELLS):
            for x in range(MODULE_CELLS):
                if grid[y][x] != SOLID and (x, y) not in reachable:
                    grid[y][x] = SOLID

        for row in portals["west"]:
            carve(1, row, DECK, True)
        for row in portals["east"]:
            carve(MODULE_CELLS - 2, row, DECK, True)
        for col in portals["south"]:
            carve(col, 1, DECK, True)
        for col in portals["north"]:
            carve(col, MODULE_CELLS - 2, DECK, True)

        data = ModuleData(grid=grid, style_id=style_id)
        self.module_data_cache[key] = data
        return data

    def _flood_walkable(self, grid: List[List[int]], starts: List[Tuple[int, int]]) -> Set[Tuple[int, int]]:
        q = [(x, y) for x, y in starts if 0 <= x < MODULE_CELLS and 0 <= y < MODULE_CELLS and grid[y][x] != SOLID]
        seen = set(q)
        i = 0
        while i < len(q):
            x, y = q[i]
            i += 1
            for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if not (0 <= nx < MODULE_CELLS and 0 <= ny < MODULE_CELLS):
                    continue
                if grid[ny][nx] == SOLID or (nx, ny) in seen:
                    continue
                seen.add((nx, ny))
                q.append((nx, ny))
        return seen

    def _world_cell_kind(self, gx: int, gy: int) -> int:
        mx = math.floor(gx / MODULE_CELLS)
        my = math.floor(gy / MODULE_CELLS)
        lx = gx - mx * MODULE_CELLS
        ly = gy - my * MODULE_CELLS
        return self._module_data(mx, my).grid[ly][lx]

    def _module_of_pos(self, x: float, y: float) -> Tuple[int, int]:
        return math.floor(x / MODULE_SIZE), math.floor(y / MODULE_SIZE)

    def _world_cell_from_pos(self, x: float, y: float) -> Tuple[int, int]:
        return math.floor(x / CELL), math.floor(y / CELL)


    def _line_walk_clear(self, start: Vec3, end: Vec3) -> bool:
        dx = end.x - start.x
        dy = end.y - start.y
        distance = math.sqrt(dx * dx + dy * dy)
        steps = max(8, int(distance / max(0.18, CELL * 0.18)))
        for i in range(1, steps):
            t = i / steps
            px = start.x + dx * t
            py = start.y + dy * t
            if self._cell_kind_at_pos(px, py) == SOLID:
                return False
        return True

    def _shadow_presence_mix_for_pos(self, pos: Vec3) -> float:
        if self._module_of_pos(self.player_pos.x, self.player_pos.y) != self._module_of_pos(pos.x, pos.y):
            return 0.0
        eye = Vec3(self.player_pos.x, self.player_pos.y, 0.0)
        target = Vec3(pos.x, pos.y, 0.0)
        if not self._line_walk_clear(eye, target):
            return 0.0
        planar_dist = (target - eye).length()
        return clamp(1.0 - max(0.0, planar_dist - 2.0) / max(2.0, SHADOW_NPC_DARK_RADIUS * 1.25), 0.0, 1.0)

    def _shadow_wall_anchor(self, world: Vec3) -> Optional[Tuple[Vec3, Tuple[float, float, float]]]:
        gx, gy = self._world_cell_from_pos(world.x, world.y)
        options: List[Tuple[Vec3, Tuple[float, float, float]]] = []
        inset = 0.065
        jitter = (((hash_u32(gx, gy, self.shadow_npc_spawn_count + 1) >> 8) & 255) / 255.0 - 0.5) * CELL * 0.18
        if self._world_cell_kind(gx + 1, gy) == SOLID:
            options.append((Vec3((gx + 1) * CELL - inset, gy * CELL + CELL * 0.5 + jitter, 0.0), (90.0, 0.0, 0.0)))
        if self._world_cell_kind(gx - 1, gy) == SOLID:
            options.append((Vec3(gx * CELL + inset, gy * CELL + CELL * 0.5 + jitter, 0.0), (-90.0, 0.0, 0.0)))
        if self._world_cell_kind(gx, gy + 1) == SOLID:
            options.append((Vec3(gx * CELL + CELL * 0.5 + jitter, (gy + 1) * CELL - inset, 0.0), (180.0, 0.0, 0.0)))
        if self._world_cell_kind(gx, gy - 1) == SOLID:
            options.append((Vec3(gx * CELL + CELL * 0.5 + jitter, gy * CELL + inset, 0.0), (0.0, 0.0, 0.0)))
        if not options:
            return None
        pick = (hash_u32(gx, gy, self.shadow_npc_spawn_count + 17) >> 3) % len(options)
        return options[pick]

    def _stream_radii(self) -> Tuple[int, int]:
        if self._is_hub_level():
            preset = self._normalize_quality_preset(self.settings.get("quality_preset", "Low"))
            if preset == "Low":
                return 2, 3
            if preset == "Medium":
                return 3, 4
            return 4, 5
        preset = self._normalize_quality_preset(self.settings.get("quality_preset", "Low"))
        if preset == "Low":
            return 1, 2
        if preset == "Medium":
            return 2, 4
        if preset == "High":
            return 2, 5
        return LOAD_RADIUS, UNLOAD_RADIUS

    def _stream_modules(self, force: bool = False) -> None:
        pmx, pmy = self._module_of_pos(self.player_pos.x, self.player_pos.y)
        load_radius, unload_radius = self._stream_radii()
        built_any = False
        if self._is_hub_level():
            wanted = {(0, my) for my in range(pmy - load_radius, pmy + load_radius + 1)}
        else:
            wanted = {
                (mx, my)
                for my in range(pmy - load_radius, pmy + load_radius + 1)
                for mx in range(pmx - load_radius, pmx + load_radius + 1)
            }
        for mx, my in sorted(wanted):
            if force or (mx, my) not in self.module_nodes:
                self.module_nodes[(mx, my)] = self._build_module(mx, my)
                built_any = True

        stale: List[Tuple[int, int]] = []
        for mx, my in list(self.module_nodes.keys()):
            if self._is_hub_level():
                if mx != 0 or abs(my - pmy) > unload_radius:
                    stale.append((mx, my))
            elif abs(mx - pmx) > unload_radius or abs(my - pmy) > unload_radius:
                stale.append((mx, my))
        for key in stale:
            chunk = self.module_nodes.pop(key)
            chunk.root.removeNode()

        if self._is_hub_level() and self.hub_doors:
            kept: List[Vec3] = []
            for pos in self.hub_doors:
                dmx, dmy = self._module_of_pos(pos.x, pos.y)
                if dmx == 0 and abs(dmy - pmy) <= unload_radius:
                    kept.append(pos)
            self.hub_doors = kept
        if built_any or force:
            self._apply_reflection_settings()
            self._apply_water_quality_settings()

    def _build_module(self, mx: int, my: int) -> ModuleChunk:
        data = self._module_data(mx, my)
        root = self.world_root.attachNewNode(f"module_{mx}_{my}")
        root.setPos(mx * MODULE_SIZE, my * MODULE_SIZE, 0)
        water_root = root.attachNewNode("water_root")

        if self._is_hub_level():
            self._build_hub_module(root, mx, my, data.grid)
            return ModuleChunk(mx, my, root, water_root, STYLE_NAMES[data.style_id])

        module = self._external_level_module()
        settings = self._external_level_settings()
        if module is not None and hasattr(module, "build_module"):
            try:
                module.build_module(self, root, water_root, mx, my, data)
                style_name = str(settings.get("style_name") or settings.get("display_name") or f"Level {self.current_level}")
                return ModuleChunk(mx, my, root, water_root, style_name)
            except Exception as exc:
                print(f"[LevelLoader] build_module failed for level {self.current_level}: {exc}")

        self._build_cell_floors(root, data.grid)
        self._build_cell_waters(water_root, data.grid)
        self._build_ceiling(root, data.style_id)
        self._build_boundary_walls(root, mx, my, data.grid)
        self._build_columns(root, data.grid)
        self._build_pool_walls(root, mx, my, data.grid)
        self._build_pool_edges(root, mx, my, data.grid)
        self._build_light_strips(root, data.style_id)
        self._build_sun_windows(root, mx, my, data.grid, data.style_id)

        style_name = STYLE_NAMES[data.style_id] if 0 <= data.style_id < len(STYLE_NAMES) else f"Level {self.current_level}"
        return ModuleChunk(mx, my, root, water_root, style_name)

    def _build_hub_module(self, parent: NodePath, mx: int, my: int, grid: List[List[int]]) -> None:
        if mx != 0:
            return
        center_x = MODULE_SIZE * 0.5
        corridor_half_w = CELL * 1.28
        corridor_x0 = center_x - corridor_half_w
        corridor_x1 = center_x + corridor_half_w
        corridor_w = corridor_x1 - corridor_x0
        center_y = MODULE_SIZE * 0.5
        length = MODULE_SIZE
        upper_z = WALL_H * 0.5

        carpet = self._add_plane(parent, Vec3(center_x, center_y, DECK_Z + 0.012), corridor_w, length, (0, -90, 0), self.hub_carpet_tex, 1.0, 4.0)
        carpet.setColorScale(1.0, 0.98, 0.96, 1.0)
        self.deck_surfaces.append(carpet)

        left_wall = self._add_plane(parent, Vec3(corridor_x0, center_y, upper_z), length, WALL_H, (-90, 0, 0), self.hub_wall_tex, 2.3, 1.1)
        right_wall = self._add_plane(parent, Vec3(corridor_x1, center_y, upper_z), length, WALL_H, (90, 0, 0), self.hub_wall_tex, 2.3, 1.1)
        left_wall.setColorScale(1.02, 1.01, 0.99, 1.0)
        right_wall.setColorScale(1.02, 1.01, 0.99, 1.0)

        ceiling = self._add_plane(parent, Vec3(center_x, center_y, WALL_H), corridor_w, length, (0, -90, 0), self.hub_wall_tex, 1.0, 3.2)
        ceiling.setColorScale(0.82, 0.75, 0.68, 1.0)

        left_base = self._add_box(parent, Vec3(corridor_x0 + 0.030, center_y, 0.10), Vec3(0.06, length, 0.20), self.hub_trim_tex)
        right_base = self._add_box(parent, Vec3(corridor_x1 - 0.030, center_y, 0.10), Vec3(0.06, length, 0.20), self.hub_trim_tex)
        left_base.setColorScale(0.05, 0.035, 0.025, 1.0)
        right_base.setColorScale(0.05, 0.035, 0.025, 1.0)

        left_crown = self._add_box(parent, Vec3(corridor_x0 + 0.035, center_y, WALL_H - 0.08), Vec3(0.07, length, 0.15), self.hub_trim_tex)
        right_crown = self._add_box(parent, Vec3(corridor_x1 - 0.035, center_y, WALL_H - 0.08), Vec3(0.07, length, 0.15), self.hub_trim_tex)
        left_crown.setColorScale(0.78, 0.74, 0.70, 1.0)
        right_crown.setColorScale(0.78, 0.74, 0.70, 1.0)

        light_step = CELL * 2.0
        light_y = CELL * 0.78
        idx = 0
        while light_y < length - CELL * 0.40:
            housing = self._add_box(parent, Vec3(center_x, light_y, WALL_H - 0.07), Vec3(0.62, 0.36, 0.09), self.hub_trim_tex)
            housing.setColorScale(0.44, 0.35, 0.26, 1.0)
            fixture = self._add_plane(parent, Vec3(center_x, light_y, WALL_H - 0.025), 0.52, 0.30, (0, -90, 0), self.light_tex, 1.0, 1.0, True)
            fixture.setColorScale(1.0, 0.98, 0.94, 0.84)
            self._add_point_light(parent, Vec3(center_x, light_y, WALL_H - 0.22), Vec4(0.60, 0.48, 0.34, 1.0), Vec3(1.0, 0.0, 0.07), phase=idx * 0.40 + my * 0.10, pulse=0.0035)
            light_y += light_step
            idx += 1

        door_w = 1.10
        door_h = 3.04
        door_depth = 0.06
        frame_depth = 0.08
        frame_w = door_w + 0.16
        frame_h = door_h + 0.16
        door_step = CELL * 2.0
        first_y = CELL * 0.95
        door_positions: List[float] = []
        y = first_y
        while y < length - CELL * 0.70:
            door_positions.append(y)
            y += door_step

        for y in door_positions:
            for side, wall_x, inward in ((-1, corridor_x0, 1.0), (1, corridor_x1, -1.0)):
                recess = self._add_box(parent, Vec3(wall_x + inward * 0.010, y, 1.66), Vec3(0.020, frame_w + 0.10, frame_h + 0.18), self.hub_trim_tex)
                recess.setColorScale(0.02, 0.015, 0.012, 1.0)

                frame = self._add_box(parent, Vec3(wall_x + inward * (frame_depth * 0.5 + 0.001), y, 1.68), Vec3(frame_depth, frame_w, frame_h), self.hub_trim_tex)
                frame.setColorScale(0.07, 0.045, 0.032, 1.0)

                door = self._add_box(parent, Vec3(wall_x + inward * (door_depth * 0.5 + 0.003), y, 1.64), Vec3(door_depth, door_w, door_h), self.hub_door_tex)
                door.setColorScale(0.28, 0.18, 0.11, 1.0)

                plate = self._add_box(parent, Vec3(wall_x + inward * (door_depth + 0.014), y, 2.68), Vec3(0.020, 0.15, 0.09), self.light_tex)
                knob = self._add_box(parent, Vec3(wall_x + inward * (door_depth + 0.015), y + 0.24, 1.36), Vec3(0.020, 0.06, 0.06), self.light_tex)
                plate.setColorScale(0.78, 0.64, 0.22, 1.0)
                knob.setColorScale(0.76, 0.62, 0.20, 1.0)

                self.hub_doors.append(Vec3(mx * MODULE_SIZE + center_x + side * (corridor_half_w - 0.16), my * MODULE_SIZE + y, 0.0))
    def _apply_texture(self, np: NodePath, tex: Texture, scale_u: float, scale_v: float, stage: Optional[TextureStage] = None) -> None:
        stage = stage or self.wall_stage
        np.setTexture(stage, tex)
        np.setTexScale(stage, scale_u, scale_v)

    def _add_plane(
        self,
        parent: NodePath,
        center: Vec3,
        width: float,
        height: float,
        hpr: Tuple[float, float, float],
        tex: Texture,
        scale_u: float,
        scale_v: float,
        transparent: bool = False,
    ) -> NodePath:
        cm = CardMaker("plane")
        cm.setFrame(-width * 0.5, width * 0.5, -height * 0.5, height * 0.5)
        np = parent.attachNewNode(cm.generate())
        np.setPos(center)
        np.setHpr(*hpr)
        np.setTwoSided(True)
        if transparent:
            np.setTransparency(TransparencyAttrib.MAlpha)
            np.setDepthWrite(False)
        self._apply_texture(np, tex, scale_u, scale_v)
        return np

    def _add_box(self, parent: NodePath, center: Vec3, scale: Vec3, tex: Texture) -> NodePath:
        root = parent.attachNewNode("box")
        sx, sy, sz = scale.x * 0.5, scale.y * 0.5, scale.z * 0.5
        self._add_plane(root, Vec3(sx, 0, 0), scale.y, scale.z, (90, 0, 0), tex, max(1.0, scale.y * 0.33), max(1.0, scale.z * 0.33))
        self._add_plane(root, Vec3(-sx, 0, 0), scale.y, scale.z, (-90, 0, 0), tex, max(1.0, scale.y * 0.33), max(1.0, scale.z * 0.33))
        self._add_plane(root, Vec3(0, sy, 0), scale.x, scale.z, (180, 0, 0), tex, max(1.0, scale.x * 0.33), max(1.0, scale.z * 0.33))
        self._add_plane(root, Vec3(0, -sy, 0), scale.x, scale.z, (0, 0, 0), tex, max(1.0, scale.x * 0.33), max(1.0, scale.z * 0.33))
        self._add_plane(root, Vec3(0, 0, sz), scale.x, scale.y, (0, -90, 0), tex, max(1.0, scale.x * 0.33), max(1.0, scale.y * 0.33))
        self._add_plane(root, Vec3(0, 0, -sz), scale.x, scale.y, (0, 90, 0), tex, max(1.0, scale.x * 0.33), max(1.0, scale.y * 0.33))
        root.setPos(center)
        return root

    def _add_round_column(self, parent: NodePath, center: Vec3, radius: float, height: float, tex: Texture) -> None:
        self._add_box(parent, center, Vec3(radius * 1.34, radius * 1.34, height), tex)
        for ang in (0, 45, 90, 135):
            arm = self._add_box(parent, center, Vec3(radius * 0.78, radius * 1.88, height), tex)
            arm.setH(ang)

    def _add_point_light(
        self,
        parent: NodePath,
        center: Vec3,
        color: Vec4,
        attenuation: Vec3,
        phase: float,
        pulse: float,
    ) -> None:
        plight = PointLight("module_point_light")
        plight.setColor(color)
        plight.setAttenuation(attenuation)
        np = parent.attachNewNode(plight)
        np.setPos(center)
        parent.setLight(np)
        self.dynamic_lights.append((np, color, phase, pulse))

    def _add_window_projection_set(self, parent: NodePath, center: Vec3, inward: Vec3, beam_len: float, glow: Vec4) -> None:
        if abs(inward.x) > 0:
            floor_center = Vec3(center.x + inward.x * (beam_len * 0.58), center.y, DECK_Z + 0.018)
            floor = self._add_plane(parent, floor_center, beam_len, CELL * 0.92, (0, -90, 0), self.window_pattern_tex, 1.0, 1.0, True)
            ceiling_center = Vec3(center.x + inward.x * (beam_len * 0.40), center.y, WALL_H - 0.030)
            ceiling = self._add_plane(parent, ceiling_center, beam_len * 0.80, CELL * 0.74, (0, -90, 0), self.window_pattern_tex, 1.0, 1.0, True)
            wall_center = Vec3(center.x + inward.x * (beam_len * 0.86), center.y, WALL_H * 0.70)
            wall = self._add_plane(parent, wall_center, CELL * 0.92, WALL_H * 0.34, (90 if inward.x > 0 else -90, 0, 0), self.window_pattern_tex, 1.0, 1.0, True)
        else:
            floor_center = Vec3(center.x, center.y + inward.y * (beam_len * 0.58), DECK_Z + 0.018)
            floor = self._add_plane(parent, floor_center, CELL * 0.92, beam_len, (0, -90, 0), self.window_pattern_tex, 1.0, 1.0, True)
            ceiling_center = Vec3(center.x, center.y + inward.y * (beam_len * 0.40), WALL_H - 0.030)
            ceiling = self._add_plane(parent, ceiling_center, CELL * 0.74, beam_len * 0.80, (0, -90, 0), self.window_pattern_tex, 1.0, 1.0, True)
            wall_center = Vec3(center.x, center.y + inward.y * (beam_len * 0.86), WALL_H * 0.70)
            wall = self._add_plane(parent, wall_center, CELL * 0.92, WALL_H * 0.34, (180 if inward.y > 0 else 0, 0, 0), self.window_pattern_tex, 1.0, 1.0, True)
        for np, phase in ((floor, 0.0), (ceiling, 0.85), (wall, 1.7)):
            np.setDepthWrite(False)
            np.setBin("transparent", 22)
            np.setColorScale(glow.x, glow.y, glow.z, 0.0)
            self.pattern_overlays.append((np, phase, 0.045, glow))

    def _horizontal_runs(self, grid: List[List[int]], target: int, y: int) -> List[Tuple[int, int]]:
        runs: List[Tuple[int, int]] = []
        x = 0
        while x < MODULE_CELLS:
            while x < MODULE_CELLS and grid[y][x] != target:
                x += 1
            if x >= MODULE_CELLS:
                break
            start = x
            while x < MODULE_CELLS and grid[y][x] == target:
                x += 1
            runs.append((start, x))
        return runs

    def _build_cell_floors(self, parent: NodePath, grid: List[List[int]]) -> None:
        for y in range(MODULE_CELLS):
            for start, end in self._horizontal_runs(grid, DECK, y):
                width = (end - start) * CELL
                center = Vec3(start * CELL + width * 0.5, y * CELL + CELL * 0.5, DECK_Z)
                floor = self._add_plane(parent, center, width, CELL, (0, -90, 0), self.floor_tex, max(1.0, width * 0.34), 1.0)
                self.deck_surfaces.append(floor)
                overlay = self._add_plane(parent, center + Vec3(0, 0, 0.012), width, CELL, (0, -90, 0), self.reflection_tex, max(1.0, width * 0.20), 1.0, True)
                overlay.setColorScale(0.92, 0.96, 1.0, 0.0)
                overlay.hide()
                self.deck_reflection_overlays.append((overlay, (center.x + center.y) * 0.021, (center.x - center.y) * 0.013))
                gloss = self._add_plane(parent, center + Vec3(0, 0, 0.018), width, CELL, (0, -90, 0), self.deck_gloss_tex, max(1.0, width * 0.18), 1.0, True)
                gloss.setColorScale(0.97, 0.99, 1.0, 0.0)
                gloss.hide()
                self.deck_gloss_overlays.append((gloss, (center.x + center.y) * 0.017, (center.x - center.y) * 0.010))
            for start, end in self._horizontal_runs(grid, WATER, y):
                width = (end - start) * CELL
                center = Vec3(start * CELL + width * 0.5, y * CELL + CELL * 0.5, WATER_FLOOR_Z)
                floor = self._add_plane(parent, center, width, CELL, (0, -90, 0), self.water_floor_tex, max(1.0, width * 0.34), 1.0)
                self.water_surfaces.append(floor)

    def _build_cell_waters(self, water_root: NodePath, grid: List[List[int]]) -> None:
        for y in range(MODULE_CELLS):
            for start, end in self._horizontal_runs(grid, WATER, y):
                width = (end - start) * CELL
                center = Vec3(start * CELL + width * 0.5, y * CELL + CELL * 0.5, WATER_SURFACE_Z)
                surf = self._add_plane(water_root, center, width, CELL, (0, -90, 0), self.water_tex, max(1.0, width * 0.30), 1.0, True)
                surf.setColorScale(0.92, 0.98, 1.02, 0.72)
                surf.setTexture(self.water_stage, self.water_tex, 1)
                surf.setTexScale(self.water_stage, max(1.0, width * 0.30), 1.0)
                self.water_surfaces.append(surf)
                self.water_surface_cards.append(surf)
                detail = self._add_plane(water_root, center + Vec3(0, 0, 0.014), width, CELL, (0, -90, 0), self.water_detail_tex, max(1.0, width * 0.42), 1.25, True)
                detail.setTexture(self.water_detail_stage, self.water_detail_tex, 1)
                detail.setTexScale(self.water_detail_stage, max(1.0, width * 0.42), 1.25)
                detail.setColorScale(0.96, 1.0, 1.0, 0.0)
                detail.hide()
                self.water_detail_overlays.append((detail, (center.x + center.y) * 0.032, (center.x - center.y) * 0.019))
                overlay = self._add_plane(water_root, center + Vec3(0, 0, 0.020), width, CELL, (0, -90, 0), self.reflection_tex, max(1.0, width * 0.24), 1.0, True)
                overlay.setColorScale(0.95, 0.98, 1.0, 0.0)
                overlay.hide()
                self.water_reflection_overlays.append((overlay, (center.x + center.y) * 0.026, (center.x - center.y) * 0.016))

    def _build_ceiling(self, parent: NodePath, style_id: int) -> None:
        center = Vec3(MODULE_SIZE * 0.5, MODULE_SIZE * 0.5, WALL_H)
        ceiling = self._add_plane(parent, center, MODULE_SIZE, MODULE_SIZE, (0, -90, 0), self.ceiling_tex, MODULE_CELLS * 0.55, MODULE_CELLS * 0.55)
        ceiling.setColorScale(0.88, 0.90, 0.87, 1.0)

    def _build_boundary_walls(self, parent: NodePath, mx: int, my: int, grid: List[List[int]]) -> None:
        wall_z = WALL_H * 0.5
        for y in range(MODULE_CELLS):
            for x in range(MODULE_CELLS):
                if grid[y][x] == SOLID:
                    continue
                wx = x * CELL
                wy = y * CELL
                gx = mx * MODULE_CELLS + x
                gy = my * MODULE_CELLS + y
                for dx, dy, cx, cy, hpr in (
                    (1, 0, wx + CELL, wy + CELL * 0.5, (90, 0, 0)),
                    (-1, 0, wx, wy + CELL * 0.5, (-90, 0, 0)),
                    (0, 1, wx + CELL * 0.5, wy + CELL, (180, 0, 0)),
                    (0, -1, wx + CELL * 0.5, wy, (0, 0, 0)),
                ):
                    if self._world_cell_kind(gx + dx, gy + dy) != SOLID:
                        continue
                    face = self._add_plane(
                        parent,
                        Vec3(cx, cy, wall_z),
                        CELL,
                        WALL_H,
                        hpr,
                        self.wall_tex,
                        1.5,
                        max(1.0, WALL_H * 0.40),
                    )
                    face.setColorScale(1.0, 1.0, 1.0, 1.0)

    def _build_columns(self, parent: NodePath, grid: List[List[int]]) -> None:
        wall_z = WALL_H * 0.5
        for y in range(MODULE_CELLS):
            for x in range(MODULE_CELLS):
                if not self._is_isolated_column(grid, x, y):
                    continue
                center = Vec3(x * CELL + CELL * 0.5, y * CELL + CELL * 0.5, wall_z)
                self._add_round_column(parent, center, CELL * 0.30, WALL_H, self.wall_tex)

    def _is_isolated_column(self, grid: List[List[int]], x: int, y: int) -> bool:
        if grid[y][x] != SOLID:
            return False
        open_neighbors = 0
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if 0 <= nx < MODULE_CELLS and 0 <= ny < MODULE_CELLS and grid[ny][nx] != SOLID:
                open_neighbors += 1
        return open_neighbors >= 3

    def _build_pool_walls(self, parent: NodePath, mx: int, my: int, grid: List[List[int]]) -> None:
        wall_h = WATER_SURFACE_Z + COPING_H - WATER_FLOOR_Z
        wall_z = WATER_FLOOR_Z + wall_h * 0.5
        for y in range(MODULE_CELLS):
            for x in range(MODULE_CELLS):
                if grid[y][x] != WATER:
                    continue
                wx = x * CELL
                wy = y * CELL
                gx = mx * MODULE_CELLS + x
                gy = my * MODULE_CELLS + y
                for dx, dy, cx, cy, hpr in (
                    (1, 0, wx + CELL, wy + CELL * 0.5, (90, 0, 0)),
                    (-1, 0, wx, wy + CELL * 0.5, (-90, 0, 0)),
                    (0, 1, wx + CELL * 0.5, wy + CELL, (180, 0, 0)),
                    (0, -1, wx + CELL * 0.5, wy, (0, 0, 0)),
                ):
                    if self._world_cell_kind(gx + dx, gy + dy) == WATER:
                        continue
                    face = self._add_plane(
                        parent,
                        Vec3(cx, cy, wall_z),
                        CELL,
                        wall_h,
                        hpr,
                        self.wall_tex,
                        1.25,
                        max(1.0, wall_h * 0.40),
                    )
                    face.setColorScale(0.94, 0.96, 0.94, 1.0)

    def _build_pool_edges(self, parent: NodePath, mx: int, my: int, grid: List[List[int]]) -> None:
        rim_z = WATER_SURFACE_Z + COPING_H * 0.5
        for y in range(MODULE_CELLS):
            for x in range(MODULE_CELLS):
                if grid[y][x] != WATER:
                    continue
                wx = x * CELL
                wy = y * CELL
                gx = mx * MODULE_CELLS + x
                gy = my * MODULE_CELLS + y
                neighbors = (
                    (gx + 1, gy, Vec3(wx + CELL, wy + CELL * 0.5, rim_z), Vec3(0.12, CELL, COPING_H)),
                    (gx - 1, gy, Vec3(wx, wy + CELL * 0.5, rim_z), Vec3(0.12, CELL, COPING_H)),
                    (gx, gy + 1, Vec3(wx + CELL * 0.5, wy + CELL, rim_z), Vec3(CELL, 0.12, COPING_H)),
                    (gx, gy - 1, Vec3(wx + CELL * 0.5, wy, rim_z), Vec3(CELL, 0.12, COPING_H)),
                )
                for ngx, ngy, center, scale in neighbors:
                    if self._world_cell_kind(ngx, ngy) == WATER:
                        continue
                    rim = self._add_box(parent, center, scale, self.coping_tex)
                    rim.setColorScale(0.97, 0.98, 1.00, 1.0)

    def _build_light_strips(self, parent: NodePath, style_id: int) -> None:
        strip_positions: List[Tuple[Vec3, Tuple[float, float, float], float, float]] = []
        if style_id in (0, 4):
            for y in range(2, MODULE_CELLS - 2, 4):
                strip_positions.append((Vec3(CELL * 0.18, y * CELL + CELL * 0.5, WALL_H * 0.66), (90, 0, 0), WALL_H * 0.54, CELL * 0.18))
                strip_positions.append((Vec3(MODULE_SIZE - CELL * 0.18, y * CELL + CELL * 0.5, WALL_H * 0.66), (-90, 0, 0), WALL_H * 0.54, CELL * 0.18))
        elif style_id == 3:
            for x in range(3, MODULE_CELLS - 3, 5):
                strip_positions.append((Vec3(x * CELL + CELL * 0.5, CELL * 0.18, WALL_H * 0.68), (0, 0, 0), WALL_H * 0.58, CELL * 0.18))
        else:
            return

        for idx, (center, hpr, height, width) in enumerate(strip_positions):
            strip = self._add_plane(parent, center, width, height, hpr, self.light_tex, 1.0, 1.0, True)
            strip.setColorScale(1.0, 0.98, 0.92, 0.12)
            if idx % 2 == 0:
                self._add_point_light(
                    parent,
                    Vec3(center.x, center.y, min(WALL_H - 0.28, center.z + 0.06)),
                    Vec4(0.08, 0.08, 0.07, 1.0),
                    Vec3(1.0, 0.0, 0.085),
                    phase=(center.x + center.y) * 0.07,
                    pulse=0.025,
                )

    def _build_sun_windows(self, parent: NodePath, mx: int, my: int, grid: List[List[int]], style_id: int) -> None:
        if style_id not in (0, 2, 3, 4):
            return
        if hash_u32(mx, my, 0xB347) % 100 >= 54:
            return

        rnd = Random(hash_u32(mx, my, 0x7A11))
        candidates: List[Tuple[Vec3, Tuple[float, float, float], Vec3]] = []
        for y in range(1, MODULE_CELLS - 1):
            for x in range(1, MODULE_CELLS - 1):
                if grid[y][x] != DECK:
                    continue
                wx = x * CELL
                wy = y * CELL
                gx = mx * MODULE_CELLS + x
                gy = my * MODULE_CELLS + y
                specs = (
                    (1, 0, Vec3(wx + CELL - 0.03, wy + CELL * 0.5, WALL_H * 0.72), (90, 0, 0), Vec3(-1, 0, 0)),
                    (-1, 0, Vec3(wx + 0.03, wy + CELL * 0.5, WALL_H * 0.72), (-90, 0, 0), Vec3(1, 0, 0)),
                    (0, 1, Vec3(wx + CELL * 0.5, wy + CELL - 0.03, WALL_H * 0.72), (180, 0, 0), Vec3(0, -1, 0)),
                    (0, -1, Vec3(wx + CELL * 0.5, wy + 0.03, WALL_H * 0.72), (0, 0, 0), Vec3(0, 1, 0)),
                )
                for dx, dy, center, hpr, inward in specs:
                    if self._world_cell_kind(gx + dx, gy + dy) != SOLID:
                        continue
                    candidates.append((center, hpr, inward))

        if not candidates:
            return

        rnd.shuffle(candidates)
        picked: List[Tuple[Vec3, Tuple[float, float, float], Vec3]] = []
        for cand in candidates:
            if all((cand[0] - other[0]).lengthSquared() > (CELL * 4.4) ** 2 for other in [p[0] for p in picked]):
                picked.append(cand)
            if len(picked) >= (1 if style_id in (2, 3) else 2):
                break

        for idx, (center, hpr, inward) in enumerate(picked):
            window = self._add_plane(parent, center, CELL * 0.24, WALL_H * 0.42, hpr, self.light_tex, 1.0, 1.0, True)
            window.setColorScale(1.0, 0.98, 0.90, 0.76)

            beam_len = CELL * (4.5 + rnd.random() * 2.5)
            beam_h = WALL_H * 0.54
            beam_center = center + inward * (beam_len * 0.48) + Vec3(0, 0, -beam_h * 0.34)
            beam_hpr = (0 if inward.x > 0 else 180, 16, 0) if abs(inward.x) > 0 else (90 if inward.y < 0 else -90, 16, 0)
            beam = self._add_plane(parent, beam_center, beam_len, beam_h, beam_hpr, self.beam_tex, 1.0, 1.0, True)
            beam.setColorScale(1.0, 0.95, 0.82, 0.42)
            beam.setDepthWrite(False)
            self.sun_beams.append((beam, rnd.random() * math.tau, 0.030 + rnd.random() * 0.018))

            glow = Vec4(1.00, 0.93, 0.78, 1.0)
            self._add_window_projection_set(parent, center, inward, beam_len, glow)

            outside_pos = center - inward * (CELL * 0.70) + Vec3(0.0, 0.0, WALL_H * 0.18)
            target = center + inward * (beam_len * 0.90) + Vec3(0.0, 0.0, -WALL_H * 0.26)
            local_sun = DirectionalLight(f"module_sun_{mx}_{my}_{idx}")
            local_sun.setColor(Vec4(0.54, 0.47, 0.34, 1.0))
            sun_np = parent.attachNewNode(local_sun)
            sun_np.setPos(outside_pos)
            sun_np.lookAt(target)
            parent.setLight(sun_np)
            self.module_sun_lights.append(sun_np)

            self._add_point_light(
                parent,
                center + inward * 0.55 + Vec3(0, 0, 0.18),
                Vec4(0.50, 0.44, 0.30, 1.0),
                Vec3(1.0, 0.0, 0.020),
                phase=(center.x + center.y) * 0.05 + rnd.random(),
                pulse=0.05,
            )

    def _shadow_cards(self) -> List[NodePath]:
        if self.shadow_npc_root is None or self.shadow_npc_root.isEmpty():
            return []
        return [child for child in self.shadow_npc_root.findAllMatches("**/=shadow_role=body")]

    def _shadow_eye_cards(self) -> List[NodePath]:
        if self.shadow_npc_root is None or self.shadow_npc_root.isEmpty():
            return []
        return [child for child in self.shadow_npc_root.findAllMatches("**/=shadow_role=eyes")]

    def _shadow_outline_cards(self) -> List[NodePath]:
        if self.shadow_npc_root is None or self.shadow_npc_root.isEmpty():
            return []
        return [child for child in self.shadow_npc_root.findAllMatches("**/=shadow_role=outline")]

    def _shadow_aura_nodes(self) -> List[NodePath]:
        if self.shadow_npc_root is None or self.shadow_npc_root.isEmpty():
            return []
        return [child for child in self.shadow_npc_root.findAllMatches("**/=shadow_role=aura")]

    def _shadow_state_text(self) -> str:
        if self._is_hub_level():
            return "hotel"
        if not self._shadow_enabled_for_level():
            return "cleared"
        if self.shadow_npc_root is None or self.shadow_npc_root.isEmpty():
            return "hunting"
        if self.shadow_npc_revealed:
            return f"revealed {self.shadow_npc_health}/{self.shadow_npc_max_health}"
        return "hidden"

    def _build_shadow_npc(self, pos: Vec3, wall_hpr: Tuple[float, float, float]) -> None:
        if self.shadow_npc_root is not None and not self.shadow_npc_root.isEmpty():
            self.shadow_npc_root.removeNode()
        root = self.render.attachNewNode(f"shadow_npc_{self.shadow_npc_spawn_count}")
        root.setPos(pos.x, pos.y, DECK_Z)
        root.setHpr(*wall_hpr)
        root.setTransparency(TransparencyAttrib.MAlpha)
        root.setDepthWrite(False)
        root.setLightOff()
        root.setShaderOff()

        body = self._add_plane(
            root,
            Vec3(0.0, 0.0, SHADOW_NPC_HEIGHT * 0.52),
            SHADOW_NPC_WIDTH,
            SHADOW_NPC_HEIGHT,
            (0.0, 0.0, 0.0),
            self.shadow_npc_tex,
            1.0,
            1.0,
            True,
        )
        body.setTag("shadow_role", "body")
        body.setColorScale(0.012, 0.012, 0.014, self.shadow_npc_base_alpha)
        body.setBin("transparent", 30)
        body.setDepthWrite(False)

        soft = self._add_plane(
            root,
            Vec3(0.0, -0.010, SHADOW_NPC_HEIGHT * 0.52),
            SHADOW_NPC_WIDTH * 1.08,
            SHADOW_NPC_HEIGHT * 1.03,
            (0.0, 0.0, 0.0),
            self.shadow_npc_tex,
            1.0,
            1.0,
            True,
        )
        soft.setTag("shadow_role", "body")
        soft.setColorScale(0.01, 0.01, 0.012, self.shadow_npc_base_alpha * 0.38)
        soft.setBin("transparent", 29)
        soft.setDepthWrite(False)

        eyes = self._add_plane(
            root,
            Vec3(0.0, -0.014, SHADOW_NPC_HEIGHT * 0.67),
            SHADOW_NPC_WIDTH * 0.28,
            SHADOW_NPC_HEIGHT * 0.055,
            (0.0, 0.0, 0.0),
            self.shadow_eye_tex,
            1.0,
            1.0,
            True,
        )
        eyes.setTag("shadow_role", "eyes")
        eyes.setBin("transparent", 32)
        eyes.setDepthWrite(False)
        eyes.hide()

        self.shadow_npc_root = root

    def _spawn_shadow_npc(self, force: bool = False) -> None:
        if not self._shadow_enabled_for_level():
            return
        if not force and self.shadow_npc_root is not None and not self.shadow_npc_root.isEmpty():
            return
        self.shadow_npc_revealed = False
        self.shadow_npc_health = self.shadow_npc_max_health
        candidates: List[Tuple[Vec3, Tuple[float, float, float]]] = []
        for (mx, my), chunk in self.module_nodes.items():
            data = self._module_data(mx, my)
            for y in range(MODULE_CELLS):
                for x in range(MODULE_CELLS):
                    if data.grid[y][x] == SOLID:
                        continue
                    world = Vec3(mx * MODULE_SIZE + x * CELL + CELL * 0.5, my * MODULE_SIZE + y * CELL + CELL * 0.5, 0.0)
                    dist = (Vec3(world.x, world.y, 0.0) - Vec3(self.player_pos.x, self.player_pos.y, 0.0)).length()
                    if dist < SHADOW_NPC_MIN_DIST or dist > max(SHADOW_NPC_MAX_DIST, SHADOW_NPC_MIN_DIST + 4.0):
                        continue
                    if self._collides(world):
                        continue
                    anchor = self._shadow_wall_anchor(world)
                    if anchor is None:
                        continue
                    candidates.append(anchor)
        if not candidates:
            return
        pos, wall_hpr = candidates[self.runtime_random.randrange(len(candidates))]
        self.shadow_npc_spawn_count += 1
        self._build_shadow_npc(pos, wall_hpr)

    def _despawn_shadow_npc(self) -> None:
        if self.shadow_npc_root is not None and not self.shadow_npc_root.isEmpty():
            self.shadow_npc_root.removeNode()
        self.shadow_npc_root = None

    def _hit_shadow_npc(self, origin: Vec3, forward: Vec3) -> bool:
        if not self._shadow_enabled_for_level():
            return False
        if self.shadow_npc_root is None or self.shadow_npc_root.isEmpty():
            return False
        root_pos = self.shadow_npc_root.getPos(self.render)
        target = Vec3(root_pos.x, root_pos.y, DECK_Z + SHADOW_NPC_HEIGHT * 0.58)
        to_target = target - origin
        distance = to_target.length()
        if distance <= 0.001 or distance > 46.0:
            return False
        forward_n = Vec3(forward)
        if forward_n.lengthSquared() <= 0.0:
            return False
        forward_n.normalize()
        along = to_target.dot(forward_n)
        if along < 0.0 or along > distance + 0.8:
            return False
        closest = origin + forward_n * along
        miss = (target - closest).length()
        if miss <= SHADOW_NPC_HIT_RADIUS:
            if not self.shadow_npc_revealed:
                self.shadow_npc_revealed = True
                self._toast("Shadow revealed")
            self.shadow_npc_health = max(0, self.shadow_npc_health - 1)
            if self.shadow_npc_health <= 0:
                self._despawn_shadow_npc()
                self.shadow_music_mix = 0.0
                self.return_to_halls_unlocked = True
                self._apply_audio_settings()
                self._update_hub_interact_prompt()
                self._toast("Shadow destroyed — Return to the halls")
            else:
                self._toast(f"Shadow hit {self.shadow_npc_health}/{self.shadow_npc_max_health}")
            return True
        return False

    def _update_shadow_npc(self, dt: float = 0.0) -> None:
        previous_darkness = float(self.shadow_darkness_mix)
        previous_music = float(self.shadow_music_mix)
        if not self._shadow_enabled_for_level():
            if self.shadow_npc_root is not None and not self.shadow_npc_root.isEmpty():
                self._despawn_shadow_npc()
            self.shadow_darkness_mix += (0.0 - self.shadow_darkness_mix) * clamp(dt * 4.0, 0.0, 1.0)
            self.shadow_music_mix = max(0.0, self.shadow_music_mix - dt * 2.0)
            if abs(self.shadow_darkness_mix - previous_darkness) > 0.003:
                self._apply_environment_mood()
            if abs(self.shadow_music_mix - previous_music) > 0.003:
                self._apply_audio_settings()
            return
        if self.shadow_npc_root is None or self.shadow_npc_root.isEmpty():
            self._spawn_shadow_npc()
            self.shadow_darkness_mix = 0.0
            self.shadow_music_mix = max(0.0, self.shadow_music_mix - dt * 2.0)
            if abs(self.shadow_darkness_mix - previous_darkness) > 0.003:
                self._apply_environment_mood()
            if abs(self.shadow_music_mix - previous_music) > 0.003:
                self._apply_audio_settings()
            return

        pos = self.shadow_npc_root.getPos(self.render)
        planar_dist = math.sqrt((self.player_pos.x - pos.x) ** 2 + (self.player_pos.y - pos.y) ** 2)
        room_mix = self._shadow_presence_mix_for_pos(pos)

        pulse = 0.95 + math.sin(self.ambience_t * 0.85 + pos.x * 0.04 + pos.y * 0.03) * 0.05
        reveal_mix = 1.0 if self.shadow_npc_revealed else 0.0
        for idx, child in enumerate(self._shadow_cards()):
            hidden_alpha = self.shadow_npc_base_alpha * (0.84 - idx * 0.30) * pulse * (0.72 + room_mix * 0.28)
            revealed_alpha = self.shadow_npc_base_alpha * (1.08 - idx * 0.18) * pulse * (0.88 + room_mix * 0.30)
            alpha = hidden_alpha + (revealed_alpha - hidden_alpha) * reveal_mix
            scale = 1.0 + idx * 0.04 + math.sin(self.ambience_t * 0.65 + idx * 1.3) * 0.01 - reveal_mix * idx * 0.025
            child.setScale(scale)
            tone = 0.010 + reveal_mix * 0.060
            child.setColorScale(tone, tone, tone * 1.04, clamp(alpha, 0.0, 1.0))

        eye_visible = self.nightvision_on
        eye_alpha = clamp((0.48 + room_mix * 0.30) * (0.82 + math.sin(self.ambience_t * 6.2 + planar_dist * 0.05) * 0.18), 0.0, 1.0)
        for eyes in self._shadow_eye_cards():
            if eye_visible:
                eyes.show()
                eyes.setScale(1.0 + math.sin(self.ambience_t * 4.8) * 0.03)
                eyes.setColorScale(0.78, 1.0, 0.76, eye_alpha)
            else:
                eyes.hide()

        darkness_target = room_mix * (0.82 if self.shadow_npc_revealed else 1.0)
        self.shadow_darkness_mix += (darkness_target - self.shadow_darkness_mix) * clamp(dt * 3.6, 0.0, 1.0)
        if abs(self.shadow_darkness_mix - previous_darkness) > 0.003:
            self._apply_environment_mood()

        audio_dist = clamp(1.0 - max(0.0, planar_dist - 4.0) / max(1.0, SHADOW_NPC_AUDIO_RADIUS - 4.0), 0.0, 1.0)
        music_target = room_mix * audio_dist * (1.0 if self.shadow_npc_revealed else 0.82)
        self.shadow_music_mix += (music_target - self.shadow_music_mix) * clamp(dt * 2.1, 0.0, 1.0)
        if abs(self.shadow_music_mix - previous_music) > 0.003:
            self._apply_audio_settings()

    # ----------------------------
    # Collision / movement
    # ----------------------------
    # ----------------------------
    # Collision / movement
    # ----------------------------
    def _cell_kind_at_pos(self, x: float, y: float) -> int:
        gx, gy = self._world_cell_from_pos(x, y)
        return self._world_cell_kind(gx, gy)

    def _move_player(self, delta: Vec3) -> None:
        new_x = self.player_pos.x + delta.x
        new_y = self.player_pos.y + delta.y

        cand = Vec3(new_x, self.player_pos.y, 0)
        if not self._collides(cand):
            self.player_pos.x = cand.x

        cand = Vec3(self.player_pos.x, new_y, 0)
        if not self._collides(cand):
            self.player_pos.y = cand.y

    def _collides(self, pos: Vec3) -> bool:
        gx = math.floor(pos.x / CELL)
        gy = math.floor(pos.y / CELL)
        for oy in (-1, 0, 1):
            for ox in (-1, 0, 1):
                tx = gx + ox
                ty = gy + oy
                if self._world_cell_kind(tx, ty) != SOLID:
                    continue
                min_x = tx * CELL + COLLISION_SHRINK
                max_x = (tx + 1) * CELL - COLLISION_SHRINK
                min_y = ty * CELL + COLLISION_SHRINK
                max_y = (ty + 1) * CELL - COLLISION_SHRINK
                px = clamp(pos.x, min_x, max_x)
                py = clamp(pos.y, min_y, max_y)
                if (pos.x - px) ** 2 + (pos.y - py) ** 2 < PLAYER_RADIUS ** 2:
                    return True
        return False

    def _handle_level_timer(self, dt: float) -> None:
        if self._is_hub_level():
            self.level_time_remaining = 0.0
            return
        self.level_time_remaining = max(0.0, float(self.level_time_remaining) - dt)
        if self.level_time_remaining > 0.0:
            return
        self.level_time_remaining = 0.0
        self.pending_external_hub_link = None
        self._play_transition_sfx()
        self._load_level(HUB_LEVEL)
        self._toast("Time expired — back to the hotel", duration=2.2)


    # ----------------------------
    # Update loop
    # ----------------------------
    def _update(self, task: Task):
        dt = clamp(globalClock.getDt(), 0.0, 0.033)
        self.ambience_t += dt
        self.frame_counter += 1
        self._update_mouse_capture()

        dx = 0.0
        dy = 0.0
        if self.mouse_captured and not self.menu_open and self.win is not None and self._window_has_focus():
            w = max(1, self.win.getXSize())
            h = max(1, self.win.getYSize())
            cx = w // 2
            cy = h // 2
            md = self.win.getPointer(0)
            dx = float(md.getX() - cx)
            dy = float(md.getY() - cy)
            self.win.movePointer(0, cx, cy)

            if self._ignore_mouse_frames > 0:
                dx = 0.0
                dy = 0.0
                self._ignore_mouse_frames -= 1
            else:
                if abs(dx) <= 1.0:
                    dx = 0.0
                if abs(dy) <= 1.0:
                    dy = 0.0
            dx = clamp(dx, -500.0, 500.0)
            dy = clamp(dy, -500.0, 500.0)

        mouse_sens = float(self.settings.get("mouse_sensitivity", MOUSE_SENS))
        yaw_step = mouse_sens * 0.0048
        pitch_step = mouse_sens * 0.0048
        self.yaw -= dx * yaw_step
        self.pitch = clamp(self.pitch - dy * pitch_step, -1.16, 1.16)

        if self.nightvision_on:
            self.nightvision_time_left = max(0.0, self.nightvision_time_left - dt)
            if self.nightvision_time_left <= 0.0:
                self._set_nightvision_enabled(False, start_cooldown=True)
                self._toast(f"Night vision cooldown {NIGHTVISION_COOLDOWN:.0f}s")
        elif self.nightvision_cooldown_left > 0.0:
            self.nightvision_cooldown_left = max(0.0, self.nightvision_cooldown_left - dt)

        move = Vec3(0, 0, 0)
        if not self.menu_open:
            if self.keys["w"]:
                move.y += 1
            if self.keys["s"]:
                move.y -= 1
            if self.keys["a"]:
                move.x -= 1
            if self.keys["d"]:
                move.x += 1

        in_water = self._cell_kind_at_pos(self.player_pos.x, self.player_pos.y) == WATER
        if move.lengthSquared() > 0:
            move.normalize()
            speed = self._level_move_speed()
            if self.speed_lock:
                speed *= FAST_LOCK_MULT
            if self.keys["shift"]:
                speed *= SPRINT_MULT
            if in_water:
                speed *= WATER_MOVE_MULT
            quat = self.camera.getQuat(self.render)
            fwd = quat.getForward()
            right = quat.getRight()
            wish = right * move.x + fwd * move.y
            wish.z = 0
            if wish.lengthSquared() > 0:
                wish.normalize()
            self._move_player(wish * speed * dt)

        if in_water and not self.menu_open:
            current = Vec3(
                math.sin(self.player_pos.y * 0.075 + self.ambience_t * 0.85),
                math.cos(self.player_pos.x * 0.068 - self.ambience_t * 0.72),
                0.0,
            ) * 0.26
            self._move_player(current * dt)
            cam_z = PLAYER_EYE_H - 0.08
        else:
            cam_z = PLAYER_EYE_H

        self.camera.setHpr(math.degrees(self.yaw), math.degrees(self.pitch), 0.0)
        self.camera.setPos(self.player_pos.x, self.player_pos.y, cam_z)
        self._update_weapon_viewmodel(dt, dx, dy, move.lengthSquared() > 0.0, in_water)
        self._update_projectiles(dt)
        self._handle_level_timer(dt)
        self._stream_modules()
        self._refresh_level_features()
        self._update_shadow_npc(dt)

        shadow_room_mix = clamp(self.shadow_darkness_mix, 0.0, 1.0)
        alive_lights: List[Tuple[NodePath, Vec4, float, float]] = []
        for np, base, phase, pulse in self.dynamic_lights:
            if np.isEmpty():
                continue
            strength = 1.0 + math.sin(self.ambience_t * 0.55 + phase) * pulse + math.sin(self.ambience_t * 2.1 + phase * 2.3) * (pulse * 0.35)
            dark_factor = 1.0 - shadow_room_mix * 0.54
            np.node().setColor(Vec4(base.x * strength * dark_factor, base.y * strength * dark_factor, base.z * strength * dark_factor, 1.0))
            alive_lights.append((np, base, phase, pulse))
        self.dynamic_lights = alive_lights

        alive_beams: List[Tuple[NodePath, float, float]] = []
        for beam, phase, pulse in self.sun_beams:
            if beam.isEmpty():
                continue
            alpha = 0.34 + math.sin(self.ambience_t * 0.32 + phase) * pulse
            beam.setColorScale(1.0, 0.95, 0.82, clamp(alpha, 0.24, 0.44))
            alive_beams.append((beam, phase, pulse))
        self.sun_beams = alive_beams

        alive_patterns: List[Tuple[NodePath, float, float, Vec4]] = []
        for np, phase, pulse, color in self.pattern_overlays:
            if np.isEmpty():
                continue
            alpha = 0.20 + math.sin(self.ambience_t * 0.28 + phase) * pulse
            np.setColorScale(color.x, color.y, color.z, clamp(alpha, 0.12, 0.28))
            alive_patterns.append((np, phase, pulse, color))
        self.pattern_overlays = alive_patterns

        animate_secondary = (not self._level_uses_static_water_by_default()) and (self._normalize_quality_preset(self.settings.get("quality_preset", "Low")) != "Low" or (self.frame_counter % 2 == 0))
        if animate_secondary:
            for chunk in self.module_nodes.values():
                chunk.water_root.setTexOffset(self.water_stage, self.ambience_t * 0.016 + chunk.mx * 0.03, self.ambience_t * 0.007 + chunk.my * 0.02)
                bob = math.sin(self.ambience_t * 1.8 + (chunk.mx * 3 + chunk.my * 5)) * 0.008
                chunk.water_root.setZ(bob)

            for np, phase_u, phase_v in self.deck_reflection_overlays:
                if not np.isEmpty() and not np.isHidden():
                    np.setTexOffset(self.wall_stage, self.ambience_t * 0.010 + phase_u, self.ambience_t * 0.004 + phase_v)
            for np, phase_u, phase_v in self.deck_gloss_overlays:
                if not np.isEmpty() and not np.isHidden():
                    np.setTexOffset(self.wall_stage, self.ambience_t * 0.016 + phase_u, self.ambience_t * 0.006 + phase_v)
            for np, phase_u, phase_v in self.water_reflection_overlays:
                if not np.isEmpty() and not np.isHidden():
                    np.setTexOffset(self.wall_stage, self.ambience_t * 0.022 + phase_u, self.ambience_t * 0.010 + phase_v)
            for np, phase_u, phase_v in self.water_detail_overlays:
                if not np.isEmpty() and not np.isHidden():
                    np.setTexOffset(self.wall_stage, self.ambience_t * 0.030 + phase_u, self.ambience_t * 0.015 + phase_v)
                    np.setTexOffset(self.water_detail_stage, self.ambience_t * -0.024 + phase_v, self.ambience_t * 0.020 + phase_u)

        if self.nightvision_on:
            self.nv_scan.setText(f"NIGHT VISION {self.nightvision_time_left:0.1f}s // SHOTS {self.shots_fired:03d} // {int(self.ambience_t * 10) % 1000:03d}")
        elif self.nightvision_cooldown_left > 0.0:
            if self.hud_visible and not self.menu_open:
                self.nv_scan.show()
            self.nv_scan.setText(f"NIGHT VISION COOLDOWN {self.nightvision_cooldown_left:0.1f}s")
        else:
            self.nv_scan.setText("")

        self.ui_refresh_t -= dt
        if self.ui_refresh_t <= 0.0:
            self.ui_refresh_t = 0.12
            self._update_ui()

        self._update_hub_interact_prompt()
        if self.toast_t > 0:
            self.toast_t -= dt
            if self.toast_t <= 0:
                self.ui_toast.setText("")
                self.ui_toast.hide()

        return Task.cont

    def _update_ui(self) -> None:
        pmx, pmy = self._module_of_pos(self.player_pos.x, self.player_pos.y)
        gx, gy = self._world_cell_from_pos(self.player_pos.x, self.player_pos.y)
        style = self.module_nodes[(pmx, pmy)].style_name if (pmx, pmy) in self.module_nodes else "..."
        medium = "water" if self._cell_kind_at_pos(self.player_pos.x, self.player_pos.y) == WATER else "deck"
        preset = self._normalize_quality_preset(self.settings.get("quality_preset", "Low"))
        shadow_state = self._shadow_state_text()
        timer_text = f" • Timer {max(0, int(math.ceil(self.level_time_remaining)))}s" if not self._is_hub_level() else ""
        self.ui_status.setText(
            f"{self._level_display_name()} • Grid {gx},{gy} • Module {pmx},{pmy}{timer_text}\n"
            f"Style {style} • {medium.title()} • Shadow {shadow_state} • Chunks {len(self.module_nodes)} • {preset}"
        )
        self._apply_hud_visibility()


def main() -> None:
    install_crash_logger()
    game = PoolroomsArtGame()
    game.run()


if __name__ == "__main__":
    main()
