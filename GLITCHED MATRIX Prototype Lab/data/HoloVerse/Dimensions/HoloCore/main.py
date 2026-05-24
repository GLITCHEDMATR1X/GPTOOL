"""
HoloVerse Hub + Dimension Layer Prototype - Pass 22
Python 3.13.5 / Panda3D 1.10.16

Standalone first-person composition test. No UI. Uses shared/local drop-in dimension biome folders under assets/holocore/biome*/ or the host ../assets/holocore/biome* authority.

Pass 22 structure:
    main.py                         player/camera/app composition
    hub_world.py                    pyramid hub adapter
    dimensions/outer_flat_world.py  streamed infinite-style dimension grid adapter with fade-in/out chunks
    dimensions/dimension_manager.py  active dimension/drop-in biome registry
    world_grid.py                    shared grid/chunk coordinate math + seam-safe smoothed terrain height
    dimensions/surface_placement.py  sparse surface object placement and drop-in loader
    assets/entities/*.py             generated HoloCore creature/vessel entity definitions
    assets/holocore/biome1/*.py      dimension 1 biome object definitions
    assets/holocore/biome2/*.py      dimension 2 biome object definitions, including crystal spike patches
    assets/holocore/biome3/*.py      dimension 3 bubble/lava valley object definitions
    assets/holocore/biome4..7/*.py   expanded biome-band object definitions
    ../assets/holocore/biome*/.py    optional HoloVerse host-level shared biome override

Run locally:
    python main.py

"""
from __future__ import annotations

import json
import math
import os
import random
import re
import subprocess
import sys
import time
import wave
from pathlib import Path

EMBEDDED_MODE = any(os.environ.get(key, "").strip() == "1" for key in (
    "HOLOVERSE_EMBEDDED_MODE",
    "HOLOVERSE_EMBEDDED_CHILD",
    "MATRIX_LAUNCHED_FROM_CORE",
))
EMBEDDED_CHILD_MODE = os.environ.get("HOLOVERSE_EMBEDDED_CHILD", "").strip() == "1" or os.environ.get("HOLOVERSE_WINDOW_MODE", "").strip().lower() == "embedded_child"
RETURN_SIGNAL_PATH = os.environ.get("HOLOVERSE_RETURN_SIGNAL_PATH", "").strip()
HOLOCORE_INTEGRATION_SMOKE = "--integration-smoke" in sys.argv
HOLOCORE_TERRAIN_TRAVEL_SMOKE = "--terrain-travel-smoke" in sys.argv
HOLOCORE_VESSEL_SMOKE = "--vessel-smoke" in sys.argv
HOLOCORE_MERMAID_SMOKE = "--mermaid-smoke" in sys.argv
HOLOCORE_JELLYFISH_SMOKE = "--jellyfish-smoke" in sys.argv
HOLOCORE_OCTOPUS_SMOKE = "--octopus-smoke" in sys.argv
HOLOCORE_BIOME_BAND_SMOKE = "--biome-band-smoke" in sys.argv
HOLOCORE_BIOME_MOTION_SMOKE = "--biome-motion-smoke" in sys.argv
HOLOCORE_BIOME_ENTITY_SMOKE = "--biome-entity-smoke" in sys.argv
HOLOCORE_VERTICAL_STRATA_SMOKE = "--vertical-strata-smoke" in sys.argv
HOLOCORE_OCEAN_SPACE_SMOKE = "--ocean-space-smoke" in sys.argv


def _env_int(keys: tuple[str, ...], default: int) -> int:
    for key in keys:
        raw = os.environ.get(key, "").strip()
        if not raw:
            continue
        try:
            value = int(float(raw))
            if value > 0:
                return value
        except Exception:
            pass
    return int(default)


from panda3d.core import loadPrcFileData

_WINDOW_W = _env_int(("MATRIX_GAME_WIDTH", "HOLOVERSE_WINDOW_WIDTH", "HOLOVERSE_VIRTUAL_WIDTH"), 1600)
_WINDOW_H = _env_int(("MATRIX_GAME_HEIGHT", "HOLOVERSE_WINDOW_HEIGHT", "HOLOVERSE_VIRTUAL_HEIGHT"), 900)

loadPrcFileData("", "window-title HoloCore // HoloVerse Sub-World")
loadPrcFileData("", f"win-size {_WINDOW_W} {_WINDOW_H}")
if HOLOCORE_INTEGRATION_SMOKE or HOLOCORE_TERRAIN_TRAVEL_SMOKE or HOLOCORE_VESSEL_SMOKE or HOLOCORE_MERMAID_SMOKE or HOLOCORE_JELLYFISH_SMOKE or HOLOCORE_OCTOPUS_SMOKE or HOLOCORE_BIOME_BAND_SMOKE or HOLOCORE_BIOME_MOTION_SMOKE or HOLOCORE_BIOME_ENTITY_SMOKE or HOLOCORE_VERTICAL_STRATA_SMOKE or HOLOCORE_OCEAN_SPACE_SMOKE:
    loadPrcFileData("", "window-type offscreen")
    loadPrcFileData("", "load-display p3tinydisplay")
loadPrcFileData("", "fullscreen false")
if EMBEDDED_MODE:
    loadPrcFileData("", "undecorated true")
    loadPrcFileData("", "win-origin 0 0")
    loadPrcFileData("", "cursor-hidden true")
if EMBEDDED_CHILD_MODE:
    loadPrcFileData("", "borderless-fullscreen false")
loadPrcFileData("", "framebuffer-srgb true")
loadPrcFileData("", "multisamples 4")
loadPrcFileData("", "sync-video false")
loadPrcFileData("", "audio-library-name null")
from panda3d.core import AntialiasAttrib, LineSegs, Point3, TextNode, TransparencyAttrib, Vec3, WindowProperties  # noqa: E402
from direct.showbase.ShowBase import ShowBase  # noqa: E402
from direct.task import Task  # noqa: E402
from direct.showbase.ShowBaseGlobal import globalClock  # noqa: E402
from direct.gui.DirectGui import DirectButton, DirectFrame, DirectLabel  # noqa: E402
from direct.gui.OnscreenText import OnscreenText  # noqa: E402

from hub_world import HubWorldAdapter  # noqa: E402
from dimensions.outer_flat_world import FlatOuterWorldAdapter  # noqa: E402
from dimensions.vertical_strata import (  # noqa: E402
    ASCENT_ENCOUNTER_UPDATE_INTERVAL,
    VERTICAL_STRATA,
    VERTICAL_STRATA_LAYER_HEIGHT,
    VERTICAL_STRATA_START_ALTITUDE,
    VERTICAL_STRATA_UPDATE_INTERVAL,
    VERTICAL_STRATA_VISUAL_SMOOTH_SECONDS,
    vertical_stratum_state,
)
from dimensions.ocean_space import (  # noqa: E402
    OCEAN_SPACE_BANDS,
    OCEAN_SPACE_UPDATE_INTERVAL,
    OCEAN_SPACE_VISUAL_SMOOTH_SECONDS,
    ocean_space_state_for_position,
)
try:
    from assets.entities.ascent_entity_registry import ASCENT_ENTITY_SPECS  # noqa: E402
except Exception:  # pragma: no cover - keep static/adapter probes safe.
    ASCENT_ENTITY_SPECS = ()
try:
    from assets.entities.holo_vessel import HoloVessel  # noqa: E402
except Exception:  # pragma: no cover - keep legacy adapter probes safe.
    from holo_vessel import HoloVessel  # noqa: E402

ROOT = Path(__file__).resolve().parent
HOLOCORE_LOG_DIR = ROOT / "logs"
HOLOCORE_INTEGRATION_SMOKE_REPORT = HOLOCORE_LOG_DIR / "holocore_integration_smoke_report.json"
HOLOCORE_INTEGRATION_SMOKE_SCREENSHOT = HOLOCORE_LOG_DIR / "holocore_integration_smoke.png"
HOLOCORE_TERRAIN_TRAVEL_REPORT = HOLOCORE_LOG_DIR / "holocore_terrain_travel_report.json"
HOLOCORE_TERRAIN_TRAVEL_SCREENSHOT = HOLOCORE_LOG_DIR / "holocore_terrain_travel_smoke.png"
HOLOCORE_BIOME_BAND_REPORT = HOLOCORE_LOG_DIR / "holocore_biome_band_smoke_report.json"
HOLOCORE_BIOME_BAND_SCREENSHOT = HOLOCORE_LOG_DIR / "holocore_biome_band_smoke.png"
HOLOCORE_BIOME_MOTION_REPORT = HOLOCORE_LOG_DIR / "holocore_biome_motion_smoke_report.json"
HOLOCORE_BIOME_MOTION_SCREENSHOT = HOLOCORE_LOG_DIR / "holocore_biome_motion_smoke.png"
HOLOCORE_BIOME_ENTITY_REPORT = HOLOCORE_LOG_DIR / "holocore_biome_entity_smoke_report.json"
HOLOCORE_BIOME_ENTITY_SCREENSHOT = HOLOCORE_LOG_DIR / "holocore_biome_entity_smoke.png"
HOLOCORE_VERTICAL_STRATA_REPORT = HOLOCORE_LOG_DIR / "holocore_vertical_strata_smoke_report.json"
HOLOCORE_VERTICAL_STRATA_SCREENSHOT = HOLOCORE_LOG_DIR / "holocore_vertical_strata_smoke.png"
HOLOCORE_OCEAN_SPACE_REPORT = HOLOCORE_LOG_DIR / "holocore_ocean_space_smoke_report.json"
HOLOCORE_OCEAN_SPACE_SCREENSHOT = HOLOCORE_LOG_DIR / "holocore_ocean_space_smoke.png"
HOLOCORE_VESSEL_REPORT = HOLOCORE_LOG_DIR / "holocore_vessel_smoke_report.json"
HOLOCORE_VESSEL_EXTERIOR_SCREENSHOT = HOLOCORE_LOG_DIR / "holocore_vessel_exterior_smoke.png"
HOLOCORE_VESSEL_INTERIOR_SCREENSHOT = HOLOCORE_LOG_DIR / "holocore_vessel_interior_smoke.png"
HOLOCORE_VESSEL_PILOT_SCREENSHOT = HOLOCORE_LOG_DIR / "holocore_vessel_pilot_smoke.png"
HOLOCORE_MERMAID_REPORT = HOLOCORE_LOG_DIR / "holocore_mermaid_smoke_report.json"
HOLOCORE_MERMAID_WORLD_SCREENSHOT = HOLOCORE_LOG_DIR / "holocore_mermaid_world_smoke.png"
HOLOCORE_MERMAID_CLOSE_SCREENSHOT = HOLOCORE_LOG_DIR / "holocore_mermaid_close_smoke.png"
HOLOCORE_JELLYFISH_REPORT = HOLOCORE_LOG_DIR / "holocore_jellyfish_smoke_report.json"
HOLOCORE_JELLYFISH_WORLD_SCREENSHOT = HOLOCORE_LOG_DIR / "holocore_jellyfish_world_smoke.png"
HOLOCORE_JELLYFISH_CLOSE_SCREENSHOT = HOLOCORE_LOG_DIR / "holocore_jellyfish_close_smoke.png"
HOLOCORE_OCTOPUS_REPORT = HOLOCORE_LOG_DIR / "holocore_octopus_smoke_report.json"
HOLOCORE_OCTOPUS_WORLD_SCREENSHOT = HOLOCORE_LOG_DIR / "holocore_octopus_world_smoke.png"
HOLOCORE_OCTOPUS_CLOSE_SCREENSHOT = HOLOCORE_LOG_DIR / "holocore_octopus_close_smoke.png"
HOLOCORE_OCTOPUS_BEHAVIOR_SCREENSHOT = HOLOCORE_LOG_DIR / "holocore_octopus_behavior_smoke.png"

class HoloCoreDimensionAudio:
    """Optional standalone/fallback dimension music using reversed existing HoloVerse WAVs."""

    def __init__(self, root: Path, enabled: bool = True) -> None:
        self.root = Path(root)
        self.audio_root = self.root.parent / "assets" / "audio"
        self.generated_root = self.audio_root / "music" / "generated"
        self.ambient_root = self.audio_root / "music" / "ambient"
        self.reverse_root = self.audio_root / "music" / "reversed"
        self.enabled = False
        self.pygame = None
        self.channel = None
        self.air_channel = None
        self.cache = {}
        self.current_key = None
        if not enabled:
            return
        try:
            import pygame
            if not pygame.mixer.get_init():
                pygame.mixer.pre_init(22050, size=-16, channels=2, buffer=512)
                pygame.mixer.init()
            self.pygame = pygame
            self.enabled = True
            self.reverse_root.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            print(f"holocore_dimension_audio_silent err={exc.__class__.__name__}:{exc}")

    def _resolve(self, name: str) -> Path | None:
        raw = str(name or "").replace("\\", "/").strip("/")
        if not raw:
            return None
        candidates = [
            self.reverse_root / raw,
            self.generated_root / raw,
            self.ambient_root / raw,
            self.audio_root / raw,
            self.root / "assets" / raw,
        ]
        for candidate in candidates:
            try:
                if candidate.exists() and candidate.is_file():
                    return candidate
            except Exception:
                pass
        return None

    def _reversed(self, name: str) -> Path | None:
        source = self._resolve(name)
        if source is None:
            return None
        try:
            if source.suffix.lower() != ".wav":
                return source
            self.reverse_root.mkdir(parents=True, exist_ok=True)
            target = self.reverse_root / f"{source.stem}_reversed.wav"
            if target.exists() and target.stat().st_mtime >= source.stat().st_mtime:
                return target
            with wave.open(str(source), "rb") as src:
                params = src.getparams()
                channels = max(1, int(params.nchannels))
                width = max(1, int(params.sampwidth))
                frames = src.readframes(params.nframes)
            frame_size = max(1, channels * width)
            reversed_frames = bytearray(len(frames))
            out_at = 0
            for at in range(len(frames) - frame_size, -1, -frame_size):
                reversed_frames[out_at:out_at + frame_size] = frames[at:at + frame_size]
                out_at += frame_size
            with wave.open(str(target), "wb") as dst:
                dst.setparams(params)
                dst.writeframes(bytes(reversed_frames[:out_at]))
            return target
        except Exception as exc:
            print(f"holocore_reverse_audio_failed source={source.name} err={exc.__class__.__name__}:{exc}")
            return source

    def _sound(self, path: Path):
        if not self.enabled or self.pygame is None or path is None:
            return None
        key = str(path)
        try:
            if key not in self.cache:
                self.cache[key] = self.pygame.mixer.Sound(key)
            return self.cache[key]
        except Exception as exc:
            print(f"holocore_audio_load_failed file={path.name} err={exc.__class__.__name__}:{exc}")
            return None

    def _profile(self, dimension_id: int, dimension_name: str = "") -> tuple[str, str, str, float, float]:
        name = str(dimension_name or "").lower()
        if int(dimension_id or 1) == 1 or any(token in name for token in ("sonar", "ocean", "water")):
            return ("dim1", "hv_water_depth_theme.wav", "hv_hub_room_air.wav", 0.42, 0.12)
        if int(dimension_id or 1) == 2 or any(token in name for token in ("crystal", "reef")):
            return ("dim2", "hv_space_orbit_theme.wav", "hv_hub_room_air.wav", 0.44, 0.10)
        if int(dimension_id or 1) == 3 or any(token in name for token in ("bubble", "lava", "valley")):
            return ("dim3", "hv_urban_conflict_theme.wav", "hv_hub_room_air.wav", 0.38, 0.10)
        return (f"dim{int(dimension_id or 1)}", "hv_world_exploration_theme.wav", "hv_hub_room_air.wav", 0.40, 0.10)

    def play_dimension(self, dimension_id: int, dimension_name: str = "", force: bool = False) -> None:
        if not self.enabled:
            return
        key, music, air, music_volume, air_volume = self._profile(dimension_id, dimension_name)
        if not force and key == self.current_key:
            return
        self.current_key = key
        music_path = self._reversed(music)
        air_path = self._reversed(air)
        music_sound = self._sound(music_path) if music_path else None
        air_sound = self._sound(air_path) if air_path else None
        try:
            if self.channel:
                self.channel.stop()
            if self.air_channel:
                self.air_channel.stop()
            self.channel = None
            self.air_channel = None
            if music_sound:
                self.channel = music_sound.play(loops=-1)
                if self.channel:
                    self.channel.set_volume(max(0.0, min(1.0, music_volume)))
            if air_sound:
                self.air_channel = air_sound.play(loops=-1)
                if self.air_channel:
                    self.air_channel.set_volume(max(0.0, min(1.0, air_volume)))
            print(f"holocore_dimension_audio active={key} music={(music_path.name if music_path else 'missing')} reversed=1")
        except Exception as exc:
            print(f"holocore_dimension_audio_play_failed err={exc.__class__.__name__}:{exc}")

    def stop(self) -> None:
        for channel in (self.channel, self.air_channel):
            try:
                if channel:
                    channel.stop()
            except Exception:
                pass
        self.channel = None
        self.air_channel = None
        self.current_key = None


class HoloVerseWorldPrototype(ShowBase):
    def __init__(self) -> None:
        super().__init__()
        self.disableMouse()
        self.setBackgroundColor(0.0, 0.0, 0.0025, 1.0)
        self.render.setAntialias(AntialiasAttrib.MAuto)
        self.embedded_mode = EMBEDDED_MODE
        self.return_signal_path = RETURN_SIGNAL_PATH
        # HoloCore owns its local input contract.  This replaces the old
        # holocore_entry/sitecustomize import-hook guard with direct bindings so
        # ESC/E/Tab cannot regress when the parent HoloVerse UI changes.
        self.accept("escape", self._handle_escape)
        self.accept("e", self._handle_e_interaction)
        self.accept("0", self._request_matrixcore_return)
        self.accept("tab", self._cycle_dimension)
        for gate_index in range(9):
            self.accept(str(gate_index + 1), self._handle_dimension_gate_number, [gate_index])

        self.key_map: dict[str, bool] = {
            "w": False,
            "a": False,
            "s": False,
            "d": False,
            "arrow_up": False,
            "arrow_left": False,
            "arrow_down": False,
            "arrow_right": False,
            "shift": False,
            "space": False,
            "c": False,
            "page_up": False,
            "page_down": False,
        }
        self.heading = 0.0
        self.pitch = 0.0
        self._last_applied_heading = None
        self._last_applied_pitch = None
        self.mouse_sensitivity = 0.105
        self.walk_speed = 24.0
        self.sprint_speed = 46.0
        self.dimension_gate_root = None
        self.dimension_gate_buttons = []
        self.dimension_gate_modes = []
        self.dimension_gate_status = None
        self.dimension_gate_pending = None
        self.dimension_gate_pending_started_at = 0.0
        # Core-height first-person body/camera. The outer terrain owns player
        # footing outside the hub; the eye height remains relative to that solid
        # surface so distant biome transitions do not de-sync collision.
        self.eye_height = 13.0
        self._last_dimension_audio_id = None
        self.dimension_audio = HoloCoreDimensionAudio(ROOT, enabled=not (HOLOCORE_INTEGRATION_SMOKE or HOLOCORE_BIOME_BAND_SMOKE or HOLOCORE_BIOME_MOTION_SMOKE or HOLOCORE_BIOME_ENTITY_SMOKE or HOLOCORE_VERTICAL_STRATA_SMOKE))

        self.hub = HubWorldAdapter().build(self)
        self.outer_world = FlatOuterWorldAdapter(floor_z=self.hub.floor_z, stream_radius=3).build(self, self.hub)
        self.holo_vessel_boarded = False
        self.holo_vessel_piloting = False
        self.holo_vessel = None
        self._build_holo_vessel_outside_pyramid()
        self.vertical_strata_state = vertical_stratum_state(0.0)
        self._vertical_strata_update_elapsed = 0.0
        self._vertical_strata_smoothed_tint = tuple(float(v) for v in self.vertical_strata_state.tint)
        self._vertical_strata_smoothed_background = tuple(float(v) for v in self.vertical_strata_state.background)
        self.ocean_space_state = ocean_space_state_for_position(0.0, 0.0, 0.0)
        self._ocean_space_update_elapsed = 0.0
        self._ocean_space_smoothed_tint = tuple(float(v) for v in self.ocean_space_state.tint)
        self._ocean_space_smoothed_background = tuple(float(v) for v in self.ocean_space_state.background)
        self.ascent_entity_root = self.render.attachNewNode("holocore_ascent_entity_root")
        self.ascent_entity_mobs = {}
        self._ascent_entity_update_elapsed = 0.0
        self._last_ascent_entity_cell = None
        self.leviathan_ambient_root = self.render.attachNewNode("holocore_leviathan_expanse_ambient_root")
        self.leviathan_ambient_nodes = []
        self._setup_leviathan_expanse_ambient()
        self.ocean_space_ambient_root = self.render.attachNewNode("holocore_ocean_space_ambient_root")
        self.ocean_space_ambient_nodes = []
        self._setup_ocean_space_ambient()
        self.holocore_rescue_pending = False
        self.holocore_rescue_started_at = 0.0
        self.holocore_rescue_reset_done = False
        self.holocore_rescue_attacker = ""
        self.holocore_threat_level = 0.0
        self.holocore_threat_entity = ""
        self.holocore_threat_distance = 0.0
        self._holocore_threat_warning_text = None
        self._holocore_threat_warning_visible = False
        self._vertical_strata_last_layer_id = str(getattr(self.vertical_strata_state, "layer_id", "safe_reef_layer"))
        self._vertical_strata_discovered_layers = {self._vertical_strata_last_layer_id}
        self._ocean_space_last_band_id = str(getattr(self.ocean_space_state, "band_id", "safe_core_sea"))
        self._ocean_space_discovered_bands = {self._ocean_space_last_band_id}
        self._holocore_layer_notice_text = None
        self._holocore_layer_notice_visible = False
        self._holocore_layer_notice_started_at = 0.0
        self._holocore_layer_notice_duration = 0.0
        self._holo_vessel_camera_smooth_pos = None
        self._holo_vessel_camera_smooth_look = None

        self.return_transition_pending = False
        self.return_transition_started_at = 0.0
        self.return_transition_signal_written = False
        self._return_prompt_text = None
        self._return_prompt_visible = None
        self._bridge_transition_visible = None
        self._bridge_transition_rendered_alpha = None
        self._setup_first_person_controller()
        self._setup_return_prompt()
        self._setup_holo_vessel_prompt()
        self._setup_holocore_threat_warning()
        self._setup_holocore_layer_notice()
        # No permanent Dimension Gates panel here; the host draws the shared menu.
        self._setup_bridge_transition_overlay()
        self._sync_dimension_music(force=True)
        self.taskMgr.add(self._update_worlds, "update-world-adapters")
        self.taskMgr.add(self._update_first_person, "update-first-person")
        if HOLOCORE_INTEGRATION_SMOKE:
            self.taskMgr.doMethodLater(0.25, self._integration_smoke_setup, "holocore-integration-smoke-setup")
            self.taskMgr.doMethodLater(0.85, self._integration_smoke_exit, "holocore-integration-smoke-exit")
        if HOLOCORE_TERRAIN_TRAVEL_SMOKE:
            self.taskMgr.doMethodLater(0.25, self._terrain_travel_smoke_setup, "holocore-terrain-travel-smoke-setup")
            self.taskMgr.doMethodLater(1.05, self._terrain_travel_smoke_exit, "holocore-terrain-travel-smoke-exit")
        if HOLOCORE_BIOME_BAND_SMOKE:
            self.taskMgr.doMethodLater(0.28, self._biome_band_smoke_setup, "holocore-biome-band-smoke-setup")
            self.taskMgr.doMethodLater(1.20, self._biome_band_smoke_exit, "holocore-biome-band-smoke-exit")
        if HOLOCORE_BIOME_MOTION_SMOKE:
            self.taskMgr.doMethodLater(0.30, self._biome_motion_smoke_setup, "holocore-biome-motion-smoke-setup")
            self.taskMgr.doMethodLater(1.35, self._biome_motion_smoke_exit, "holocore-biome-motion-smoke-exit")
        if HOLOCORE_BIOME_ENTITY_SMOKE:
            self.taskMgr.doMethodLater(0.32, self._biome_entity_smoke_setup, "holocore-biome-entity-smoke-setup")
            self.taskMgr.doMethodLater(1.45, self._biome_entity_smoke_exit, "holocore-biome-entity-smoke-exit")
        if HOLOCORE_VERTICAL_STRATA_SMOKE:
            self.taskMgr.doMethodLater(0.34, self._vertical_strata_smoke_setup, "holocore-vertical-strata-smoke-setup")
            self.taskMgr.doMethodLater(1.75, self._vertical_strata_smoke_exit, "holocore-vertical-strata-smoke-exit")
        if HOLOCORE_OCEAN_SPACE_SMOKE:
            self.taskMgr.doMethodLater(0.36, self._ocean_space_smoke_setup, "holocore-ocean-space-smoke-setup")
            self.taskMgr.doMethodLater(1.75, self._ocean_space_smoke_exit, "holocore-ocean-space-smoke-exit")
        if HOLOCORE_VESSEL_SMOKE:
            self.taskMgr.doMethodLater(0.28, self._vessel_smoke_setup, "holocore-vessel-smoke-setup")
            self.taskMgr.doMethodLater(1.18, self._vessel_smoke_exit, "holocore-vessel-smoke-exit")
        if HOLOCORE_MERMAID_SMOKE:
            self.taskMgr.doMethodLater(0.32, self._mermaid_smoke_setup, "holocore-mermaid-smoke-setup")
            self.taskMgr.doMethodLater(1.25, self._mermaid_smoke_exit, "holocore-mermaid-smoke-exit")
        if HOLOCORE_JELLYFISH_SMOKE:
            self.taskMgr.doMethodLater(0.36, self._jellyfish_smoke_setup, "holocore-jellyfish-smoke-setup")
            self.taskMgr.doMethodLater(1.32, self._jellyfish_smoke_exit, "holocore-jellyfish-smoke-exit")
        if HOLOCORE_OCTOPUS_SMOKE:
            self.taskMgr.doMethodLater(0.40, self._octopus_smoke_setup, "holocore-octopus-smoke-setup")
            self.taskMgr.doMethodLater(1.55, self._octopus_smoke_exit, "holocore-octopus-smoke-exit")

    def _integration_smoke_setup(self, task: Task) -> int:
        """Exercise HoloCore's local input/menu contract without launching child modes."""
        self.integration_smoke_steps = []
        try:
            self.key_map["w"] = True
            self.key_map["shift"] = True
            self._handle_e_interaction()
            self.integration_smoke_steps.append({
                "step": "e_does_not_open_gate_panel",
                "panel_visible": bool(self._dimension_gate_panel_visible()),
                "movement_preserved": bool(self.key_map.get("w")) and bool(self.key_map.get("shift")),
            })
            opened = self._open_dimension_gate_panel()
            self.integration_smoke_steps.append({
                "step": "open_gate_panel_direct_only",
                "opened": bool(opened),
                "visible": bool(self._dimension_gate_panel_visible()),
                "movement_reset": not any(bool(v) for v in self.key_map.values()),
                "gate_mode_count": int(len(getattr(self, "dimension_gate_modes", []) or [])),
                "button_count": int(len(getattr(self, "dimension_gate_buttons", []) or [])),
            })
            before_dim = self._active_dimension_info()
            self._cycle_dimension(immediate=True)
            after_dim = self._active_dimension_info()
            self.integration_smoke_steps.append({
                "step": "tab_cycle_closes_panel",
                "panel_visible": bool(self._dimension_gate_panel_visible()),
                "before_dimension_id": int(before_dim[0]),
                "after_dimension_id": int(after_dim[0]),
                "dimension_changed": int(before_dim[0]) != int(after_dim[0]) or str(before_dim[1]) != str(after_dim[1]),
            })
            self._handle_dimension_gate_number(0)
            self.integration_smoke_steps.append({
                "step": "number_ignored_when_panel_closed",
                "pending_is_none": self.dimension_gate_pending is None,
                "panel_visible": bool(self._dimension_gate_panel_visible()),
            })
            self._open_dimension_gate_panel()
            self._handle_escape()
            self.integration_smoke_steps.append({
                "step": "escape_closes_panel_first",
                "panel_visible": bool(self._dimension_gate_panel_visible()),
                "return_transition_pending": bool(getattr(self, "return_transition_pending", False)),
            })
        except Exception as exc:
            self.integration_smoke_steps.append({"step": "exception", "error": f"{exc.__class__.__name__}:{exc}"})
        return Task.done

    def _terrain_travel_smoke_setup(self, task: Task) -> int:
        """Walk the controller across biome-band distances without key input."""
        self.terrain_travel_smoke_steps = []
        try:
            from world_grid import BIOME_DISTANCE_STRIDE, FLAT_WORLD_RADIUS, sonar_height_at

            route = [
                ("spawn", Vec3(0, -58, 0)),
                ("flat_edge", Vec3(FLAT_WORLD_RADIUS + 22.0, 0, 0)),
                ("first_auto_band", Vec3(FLAT_WORLD_RADIUS + BIOME_DISTANCE_STRIDE + 24.0, 0, 0)),
                ("second_auto_band", Vec3(FLAT_WORLD_RADIUS + BIOME_DISTANCE_STRIDE * 2.0 + 24.0, 0, 0)),
            ]
            for label, requested in route:
                before_id, before_name = self._active_dimension_info()
                self.player.setPos(requested)
                self.outer_world.sync_around(self.player.getPos(self.render), force=True, immediate=True)
                clamped = self.outer_world.clamp_position(self.player.getPos(self.render))
                self.player.setPos(clamped)
                self.outer_world.sync_around(clamped, force=True, immediate=True)
                after_id, after_name = self._active_dimension_info()
                expected_z = float(sonar_height_at(clamped.x, clamped.y))
                active_chunks = getattr(self.outer_world, "active_chunks", {}) or {}
                surface_objects = getattr(self.outer_world, "surface_objects", None)
                surface_layers = getattr(surface_objects, "chunk_layers", {}) if surface_objects is not None else {}
                fading_layers = getattr(surface_objects, "fading_layers", []) if surface_objects is not None else []
                self.terrain_travel_smoke_steps.append({
                    "step": label,
                    "requested": [round(float(requested.x), 3), round(float(requested.y), 3), round(float(requested.z), 3)],
                    "position": [round(float(clamped.x), 3), round(float(clamped.y), 3), round(float(clamped.z), 6)],
                    "expected_ground_z": round(expected_z, 6),
                    "ground_delta": round(abs(float(clamped.z) - expected_z), 8),
                    "before_dimension_id": int(before_id),
                    "before_dimension_name": str(before_name),
                    "after_dimension_id": int(after_id),
                    "after_dimension_name": str(after_name),
                    "active_chunk_count": int(len(active_chunks)),
                    "build_queue_count": int(len(getattr(self.outer_world, "build_queue", []) or [])),
                    "grid_refresh_queue_count": int(len(getattr(self.outer_world, "grid_refresh_queue", []) or [])),
                    "biome_refresh_queue_count": int(len(getattr(self.outer_world, "biome_refresh_queue", []) or [])),
                    "surface_layer_count": int(len(surface_layers)),
                    "fading_layer_count": int(len(fading_layers)),
                })
            self._look_player_at(Vec3(0, 0, 35.0))
        except Exception as exc:
            self.terrain_travel_smoke_steps.append({"step": "exception", "error": f"{exc.__class__.__name__}:{exc}"})
        return Task.done

    def _collect_terrain_travel_smoke_report(self) -> dict:
        steps = list(getattr(self, "terrain_travel_smoke_steps", []) or [])
        errors: list[str] = []
        if not steps:
            errors.append("no-terrain-travel-steps-recorded")
        if any(str(item.get("step")) == "exception" for item in steps if isinstance(item, dict)):
            errors.append("exception-during-terrain-travel-smoke")
        by_step = {str(item.get("step")): item for item in steps if isinstance(item, dict)}
        for name, step in by_step.items():
            if float(step.get("ground_delta", 0.0) or 0.0) > 0.0001:
                errors.append(f"ground-mismatch:{name}")
            if int(step.get("build_queue_count", 0) or 0) != 0:
                errors.append(f"stream-build-queue-not-settled:{name}")
            if int(step.get("active_chunk_count", 0) or 0) > 55:
                errors.append(f"active-chunk-budget-high:{name}")
        first = by_step.get("first_auto_band", {})
        second = by_step.get("second_auto_band", {})
        if int(first.get("after_dimension_id", 1) or 1) <= 1:
            errors.append("first-auto-band-did-not-advance-dimension")
        if int(second.get("after_dimension_id", 1) or 1) <= int(first.get("after_dimension_id", 1) or 1):
            errors.append("second-auto-band-did-not-advance-dimension")
        return {
            "schema": 1,
            "kind": "holocore_terrain_travel_smoke",
            "status": "PASS" if not errors else "FAIL",
            "errors": errors,
            "steps": steps,
            "screenshot_path": str(HOLOCORE_TERRAIN_TRAVEL_SCREENSHOT),
        }

    def _terrain_travel_smoke_exit(self, task: Task) -> int:
        report = self._collect_terrain_travel_smoke_report()
        try:
            HOLOCORE_LOG_DIR.mkdir(parents=True, exist_ok=True)
            HOLOCORE_TERRAIN_TRAVEL_REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        except Exception as exc:
            report.setdefault("errors", []).append(f"report-write-error:{exc.__class__.__name__}:{exc}")
        try:
            if self.win is not None:
                self.win.saveScreenshot(str(HOLOCORE_TERRAIN_TRAVEL_SCREENSHOT))
        except Exception as exc:
            report.setdefault("errors", []).append(f"screenshot-error:{exc.__class__.__name__}:{exc}")
            try:
                HOLOCORE_TERRAIN_TRAVEL_REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            except Exception:
                pass
        print(json.dumps(report, indent=2))
        try:
            self.dimension_audio.stop()
        except Exception:
            pass
        self.userExit()
        try:
            sys.stdout.flush(); sys.stderr.flush()
        except Exception:
            pass
        os._exit(0 if report.get("status") == "PASS" else 2)
        return Task.done


    def _biome_band_smoke_setup(self, task: Task) -> int:
        """Travel directly through the expanded biome bands and inspect asset loading."""
        self.biome_band_smoke_steps = []
        try:
            from world_grid import BIOME_DISTANCE_STRIDE, FLAT_WORLD_RADIUS, sonar_height_at

            route = [
                ("abyssal_kelp_forest", 7),
                ("mirror_glass_shoals", 8),
                ("archive_ruins_reef", 9),
                ("storm_current_trench", 10),
            ]
            for label, expected_id in route:
                requested = Vec3(FLAT_WORLD_RADIUS + BIOME_DISTANCE_STRIDE * (expected_id - 1) + 34.0, 0, 0)
                self.player.setPos(requested)
                self.outer_world.sync_around(self.player.getPos(self.render), force=True, immediate=True)
                clamped = self.outer_world.clamp_position(self.player.getPos(self.render))
                self.player.setPos(clamped)
                self.outer_world.sync_around(clamped, force=True, immediate=True)
                after_id, after_name = self._active_dimension_info()
                expected_z = float(sonar_height_at(clamped.x, clamped.y))
                surface_objects = getattr(self.outer_world, "surface_objects", None)
                asset_dir = getattr(surface_objects, "asset_dir", None) if surface_objects is not None else None
                assets = list(getattr(surface_objects, "assets", []) or []) if surface_objects is not None else []
                active_chunks = getattr(self.outer_world, "active_chunks", {}) or {}
                surface_layers = getattr(surface_objects, "chunk_layers", {}) if surface_objects is not None else {}
                self.biome_band_smoke_steps.append({
                    "step": label,
                    "expected_dimension_id": int(expected_id),
                    "after_dimension_id": int(after_id),
                    "after_dimension_name": str(after_name),
                    "asset_dir": str(asset_dir.name if asset_dir is not None else ""),
                    "asset_ids": [str(getattr(asset, "asset_id", "")) for asset in assets],
                    "position": [round(float(clamped.x), 3), round(float(clamped.y), 3), round(float(clamped.z), 6)],
                    "expected_ground_z": round(expected_z, 6),
                    "ground_delta": round(abs(float(clamped.z) - expected_z), 8),
                    "active_chunk_count": int(len(active_chunks)),
                    "surface_layer_count": int(len(surface_layers)),
                    "build_queue_count": int(len(getattr(self.outer_world, "build_queue", []) or [])),
                    "grid_refresh_queue_count": int(len(getattr(self.outer_world, "grid_refresh_queue", []) or [])),
                    "biome_refresh_queue_count": int(len(getattr(self.outer_world, "biome_refresh_queue", []) or [])),
                })
            self._look_player_at(Vec3(FLAT_WORLD_RADIUS + BIOME_DISTANCE_STRIDE * 9.0 + 34.0, 120.0, 22.0))
        except Exception as exc:
            self.biome_band_smoke_steps.append({"step": "exception", "error": f"{exc.__class__.__name__}:{exc}"})
        return Task.done

    def _collect_biome_band_smoke_report(self) -> dict:
        steps = list(getattr(self, "biome_band_smoke_steps", []) or [])
        errors: list[str] = []
        expected_assets = {
            7: {"abyssal_kelp_column", "glow_frond_cluster"},
            8: {"mirror_glass_plate", "prism_shard_cluster"},
            9: {"archive_pillar_ruin", "data_relay_stone", "broken_holo_arch"},
            10: {"storm_current_pylon", "charged_anemone", "current_ring_marker"},
        }
        if not steps:
            errors.append("no-biome-band-steps-recorded")
        for step in steps:
            if str(step.get("step")) == "exception":
                errors.append("exception-during-biome-band-smoke")
                continue
            expected_id = int(step.get("expected_dimension_id", 0) or 0)
            actual_id = int(step.get("after_dimension_id", 0) or 0)
            if actual_id != expected_id:
                errors.append(f"dimension-id-mismatch:{step.get('step')}:{actual_id}!={expected_id}")
            if float(step.get("ground_delta", 0.0) or 0.0) > 0.0001:
                errors.append(f"ground-mismatch:{step.get('step')}")
            if int(step.get("build_queue_count", 0) or 0) != 0:
                errors.append(f"stream-build-queue-not-settled:{step.get('step')}")
            if int(step.get("active_chunk_count", 0) or 0) > 55:
                errors.append(f"active-chunk-budget-high:{step.get('step')}")
            found_assets = set(str(name) for name in step.get("asset_ids", []) or [])
            missing = expected_assets.get(expected_id, set()) - found_assets
            if missing:
                errors.append(f"expected-assets-missing:{step.get('step')}:{sorted(missing)}")
        return {
            "schema": 1,
            "kind": "holocore_expanded_biome_band_smoke",
            "status": "PASS" if not errors else "FAIL",
            "errors": errors,
            "steps": steps,
            "screenshot_path": str(HOLOCORE_BIOME_BAND_SCREENSHOT),
        }

    def _biome_band_smoke_exit(self, task: Task) -> int:
        report = self._collect_biome_band_smoke_report()
        try:
            HOLOCORE_LOG_DIR.mkdir(parents=True, exist_ok=True)
            HOLOCORE_BIOME_BAND_REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        except Exception as exc:
            report.setdefault("errors", []).append(f"report-write-error:{exc.__class__.__name__}:{exc}")
        try:
            if self.win is not None:
                self.win.saveScreenshot(str(HOLOCORE_BIOME_BAND_SCREENSHOT))
        except Exception as exc:
            report.setdefault("errors", []).append(f"screenshot-error:{exc.__class__.__name__}:{exc}")
            try:
                HOLOCORE_BIOME_BAND_REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            except Exception:
                pass
        print(json.dumps(report, indent=2))
        try:
            self.dimension_audio.stop()
        except Exception:
            pass
        self.userExit()
        try:
            sys.stdout.flush(); sys.stderr.flush()
        except Exception:
            pass
        os._exit(0 if report.get("status") == "PASS" else 2)
        return Task.done

    def _biome_motion_smoke_setup(self, task: Task) -> int:
        """Inspect the expanded-biome ambience tags and capture a storm biome view."""
        self.biome_motion_smoke_steps = []
        try:
            from world_grid import BIOME_DISTANCE_STRIDE, FLAT_WORLD_RADIUS

            route = [("mirror_glass_shoals", 8), ("archive_ruins_reef", 9), ("storm_current_trench", 10)]
            combined_kinds: dict[str, int] = {}
            for label, expected_id in route:
                requested = Vec3(FLAT_WORLD_RADIUS + BIOME_DISTANCE_STRIDE * (expected_id - 1) + 92.0, 96.0, 0)
                self.player.setPos(requested)
                self.outer_world.sync_around(self.player.getPos(self.render), force=True, immediate=True)
                clamped = self.outer_world.clamp_position(self.player.getPos(self.render))
                self.player.setPos(clamped)
                self.outer_world.sync_around(clamped, force=True, immediate=True)
                surface_objects = getattr(self.outer_world, "surface_objects", None)
                animated_nodes = list(getattr(surface_objects, "animated_nodes", []) or []) if surface_objects is not None else []
                kind_counts: dict[str, int] = {}
                for node in animated_nodes:
                    if node.isEmpty():
                        continue
                    kind = str(node.getPythonTag("ambient_motion_kind") or "sway")
                    kind_counts[kind] = kind_counts.get(kind, 0) + 1
                    combined_kinds[kind] = combined_kinds.get(kind, 0) + 1
                if surface_objects is not None:
                    for sample_time in (0.35, 1.25, 2.75):
                        class _FakeTask:
                            dt = 1.0 / 30.0
                            time = sample_time
                        surface_objects.update(_FakeTask())
                after_id, after_name = self._active_dimension_info()
                self.biome_motion_smoke_steps.append({
                    "step": label,
                    "expected_dimension_id": int(expected_id),
                    "after_dimension_id": int(after_id),
                    "after_dimension_name": str(after_name),
                    "animated_node_count": int(len(animated_nodes)),
                    "motion_kind_counts": kind_counts,
                    "active_chunk_count": int(len(getattr(self.outer_world, "active_chunks", {}) or {})),
                    "build_queue_count": int(len(getattr(self.outer_world, "build_queue", []) or [])),
                    "biome_refresh_queue_count": int(len(getattr(self.outer_world, "biome_refresh_queue", []) or [])),
                })
            self.biome_motion_combined_kinds = combined_kinds
            focus = Vec3(FLAT_WORLD_RADIUS + BIOME_DISTANCE_STRIDE * 9.0 + 92.0, 96.0, 16.0)
            self._capture_holocore_smoke_screenshot(
                HOLOCORE_BIOME_MOTION_SCREENSHOT,
                Point3(focus.x - 94.0, focus.y - 160.0, focus.z + 58.0),
                Point3(focus.x + 18.0, focus.y + 22.0, focus.z + 8.0),
                58.0,
            )
        except Exception as exc:
            self.biome_motion_smoke_steps.append({"step": "exception", "error": f"{exc.__class__.__name__}:{exc}"})
        return Task.done

    def _collect_biome_motion_smoke_report(self) -> dict:
        steps = list(getattr(self, "biome_motion_smoke_steps", []) or [])
        errors: list[str] = []
        if not steps:
            errors.append("no-biome-motion-steps-recorded")
        for step in steps:
            if str(step.get("step")) == "exception":
                errors.append("exception-during-biome-motion-smoke")
                continue
            if int(step.get("expected_dimension_id", 0) or 0) != int(step.get("after_dimension_id", 0) or 0):
                errors.append(f"dimension-id-mismatch:{step.get('step')}")
            if int(step.get("build_queue_count", 0) or 0) != 0:
                errors.append(f"stream-build-queue-not-settled:{step.get('step')}")
            if int(step.get("animated_node_count", 0) or 0) <= 0:
                errors.append(f"no-animated-nodes:{step.get('step')}")
        combined = dict(getattr(self, "biome_motion_combined_kinds", {}) or {})
        for kind in ("signal_pulse", "electric_flicker", "orbit_spin"):
            if int(combined.get(kind, 0) or 0) <= 0:
                errors.append(f"motion-kind-not-seen:{kind}")
        return {
            "schema": 1,
            "kind": "holocore_biome_motion_smoke",
            "status": "PASS" if not errors else "FAIL",
            "errors": errors,
            "steps": steps,
            "combined_motion_kinds": combined,
            "screenshot_path": str(HOLOCORE_BIOME_MOTION_SCREENSHOT),
        }

    def _biome_motion_smoke_exit(self, task: Task) -> int:
        report = self._collect_biome_motion_smoke_report()
        try:
            HOLOCORE_LOG_DIR.mkdir(parents=True, exist_ok=True)
            HOLOCORE_BIOME_MOTION_REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        except Exception as exc:
            report.setdefault("errors", []).append(f"report-write-error:{exc.__class__.__name__}:{exc}")
        print(json.dumps(report, indent=2))
        try:
            self.dimension_audio.stop()
        except Exception:
            pass
        self.userExit()
        try:
            sys.stdout.flush(); sys.stderr.flush()
        except Exception:
            pass
        os._exit(0 if report.get("status") == "PASS" else 2)
        return Task.done



    def _biome_entity_smoke_setup(self, task: Task) -> int:
        """Build the biome-specific creatures in one scene and capture them."""
        self.biome_entity_smoke_steps = []
        self.biome_entity_smoke_roots = []
        try:
            from assets.entities.biome_entity_registry import BIOME_ENTITY_SPECS
            from world_grid import FLAT_WORLD_RADIUS, BIOME_DISTANCE_STRIDE, sonar_height_at

            focus = Vec3(FLAT_WORLD_RADIUS + BIOME_DISTANCE_STRIDE * 6.0 + 180.0, 120.0, 24.0)
            self.player.setPos(Vec3(focus.x, focus.y - 36.0, sonar_height_at(focus.x, focus.y - 36.0)))
            self.outer_world.sync_around(self.player.getPos(self.render), force=True, immediate=True)
            positions = [
                Vec3(focus.x - 78.0, focus.y - 32.0, focus.z + 30.0),
                Vec3(focus.x - 20.0, focus.y + 34.0, focus.z + 16.0),
                Vec3(focus.x + 42.0, focus.y - 18.0, focus.z + 8.0),
                Vec3(focus.x + 96.0, focus.y + 28.0, focus.z + 46.0),
            ]
            for idx, (folder, spec) in enumerate(sorted(BIOME_ENTITY_SPECS.items())):
                seed = spec.seed_func((140 + idx, 88 - idx), int(spec.seed_salt) ^ 0x5150)
                mob = spec.mob_class(seed=seed, surface_height_offset=float(spec.height_offset)).build(
                    self.render,
                    positions[idx % len(positions)],
                    scale=(float(spec.scale_min) + float(spec.scale_max)) * 0.5,
                    heading=25.0 + idx * 48.0,
                )
                for sample_time in (0.2, 0.8, 1.4):
                    mob.update_pose(sample_time)
                    mob.update_surface_lock(lambda sx, sy, base_z=positions[idx % len(positions)].z, tier=float((getattr(spec, "height_tiers", ()) or (spec.height_offset,))[0]): base_z - tier)
                mob.set_visibility_alpha(1.0)
                self.biome_entity_smoke_roots.append(mob)
                root_name = mob.root.getName() if getattr(mob, "root", None) is not None else "missing_root"
                self.biome_entity_smoke_steps.append({
                    "biome_folder": str(folder),
                    "entity_id": str(spec.entity_id),
                    "root_name": str(root_name),
                    "spawn_chance": float(spec.spawn_chance),
                    "update_interval": float(spec.update_interval),
                    "spacing_chunks": int(getattr(spec, "spacing_chunks", 1)),
                    "height_tiers": [float(v) for v in getattr(spec, "height_tiers", ())],
                    "behavior_id": str(getattr(spec, "behavior_id", "")),
                    "habitat_note": str(getattr(spec, "habitat_note", "")),
                })
            self._capture_holocore_smoke_screenshot(
                HOLOCORE_BIOME_ENTITY_SCREENSHOT,
                Point3(focus.x - 86.0, focus.y - 118.0, focus.z + 58.0),
                Point3(focus.x + 10.0, focus.y + 4.0, focus.z + 7.0),
                54.0,
            )
        except Exception as exc:
            self.biome_entity_smoke_steps.append({"step": "exception", "error": f"{exc.__class__.__name__}:{exc}"})
        return Task.done

    def _collect_biome_entity_smoke_report(self) -> dict:
        steps = list(getattr(self, "biome_entity_smoke_steps", []) or [])
        errors: list[str] = []
        expected = {"biome4", "biome5", "biome6", "biome7"}
        seen = {str(step.get("biome_folder")) for step in steps if step.get("biome_folder")}
        if not steps:
            errors.append("no-biome-entity-steps-recorded")
        for step in steps:
            if str(step.get("step")) == "exception":
                errors.append("exception-during-biome-entity-smoke")
        missing = sorted(expected - seen)
        if missing:
            errors.append(f"biome-entity-folders-not-seen:{missing}")
        for step in steps:
            if not str(step.get("root_name", "")).startswith("holo_"):
                errors.append(f"invalid-entity-root:{step}")
            if int(step.get("spacing_chunks", 0) or 0) < 3:
                errors.append(f"biome-entity-spacing-too-tight:{step}")
            if len(step.get("height_tiers", []) or []) < 3:
                errors.append(f"biome-entity-height-tiers-missing:{step}")
            if not str(step.get("behavior_id", "")):
                errors.append(f"biome-entity-behavior-missing:{step}")
        return {
            "schema": 1,
            "kind": "holocore_biome_entity_smoke",
            "status": "PASS" if not errors else "FAIL",
            "errors": errors,
            "steps": steps,
            "screenshot_path": str(HOLOCORE_BIOME_ENTITY_SCREENSHOT),
        }

    def _biome_entity_smoke_exit(self, task: Task) -> int:
        report = self._collect_biome_entity_smoke_report()
        try:
            HOLOCORE_LOG_DIR.mkdir(parents=True, exist_ok=True)
            HOLOCORE_BIOME_ENTITY_REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        except Exception as exc:
            report.setdefault("errors", []).append(f"report-write-error:{exc.__class__.__name__}:{exc}")
        print(json.dumps(report, indent=2))
        for mob in list(getattr(self, "biome_entity_smoke_roots", []) or []):
            try:
                mob.destroy()
            except Exception:
                pass
        try:
            self.dimension_audio.stop()
        except Exception:
            pass
        self.userExit()
        try:
            sys.stdout.flush(); sys.stderr.flush()
        except Exception:
            pass
        os._exit(0 if report.get("status") == "PASS" else 2)
        return Task.done

    def _collect_integration_smoke_report(self) -> dict:
        steps = list(getattr(self, "integration_smoke_steps", []) or [])
        errors: list[str] = []
        if not steps:
            errors.append("no-smoke-steps-recorded")
        by_step = {str(item.get("step")): item for item in steps if isinstance(item, dict)}
        e_step = by_step.get("e_does_not_open_gate_panel", {})
        open_step = by_step.get("open_gate_panel_direct_only", {})
        tab_step = by_step.get("tab_cycle_closes_panel", {})
        number_step = by_step.get("number_ignored_when_panel_closed", {})
        esc_step = by_step.get("escape_closes_panel_first", {})
        if bool(e_step.get("panel_visible", True)):
            errors.append("e-opened-dimension-gate-panel")
        if not bool(e_step.get("movement_preserved", False)):
            errors.append("e-reset-movement-without-local-interaction")
        if not bool(open_step.get("opened")) or not bool(open_step.get("visible")):
            errors.append("gate-panel-direct-open-failed")
        parent_dims_root = ROOT.parent / "Dimensions"
        expects_gate_routes = parent_dims_root.exists() and parent_dims_root.is_dir()
        if expects_gate_routes and int(open_step.get("gate_mode_count", 0) or 0) <= 0:
            errors.append("gate-mode-count-zero")
        if not bool(open_step.get("movement_reset")):
            errors.append("movement-keys-not-reset-on-panel-open")
        if bool(tab_step.get("panel_visible", True)):
            errors.append("tab-did-not-close-panel")
        if not bool(tab_step.get("dimension_changed", False)):
            errors.append("tab-did-not-cycle-dimension")
        if not bool(number_step.get("pending_is_none", False)):
            errors.append("number-key-started-gate-with-panel-closed")
        if bool(esc_step.get("panel_visible", True)):
            errors.append("escape-did-not-close-panel")
        if bool(esc_step.get("return_transition_pending", False)):
            errors.append("escape-started-return-while-closing-panel")
        if any(str(item.get("step")) == "exception" for item in steps if isinstance(item, dict)):
            errors.append("exception-during-smoke")
        active_id, active_name = self._active_dimension_info()
        return {
            "schema": 1,
            "kind": "holocore_integration_smoke",
            "status": "PASS" if not errors else "FAIL",
            "errors": errors,
            "embedded_mode": bool(self.embedded_mode),
            "direct_input_owned_by_holocore": True,
            "gate_panel_visible_at_capture": bool(self._dimension_gate_panel_visible()),
            "gate_mode_count": int(len(getattr(self, "dimension_gate_modes", []) or [])),
            "gate_button_count": int(len(getattr(self, "dimension_gate_buttons", []) or [])),
            "active_dimension_id": int(active_id),
            "active_dimension_name": str(active_name),
            "steps": steps,
            "screenshot_path": str(HOLOCORE_INTEGRATION_SMOKE_SCREENSHOT),
        }

    def _integration_smoke_exit(self, task: Task) -> int:
        report = self._collect_integration_smoke_report()
        try:
            HOLOCORE_LOG_DIR.mkdir(parents=True, exist_ok=True)
            HOLOCORE_INTEGRATION_SMOKE_REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        except Exception as exc:
            report.setdefault("errors", []).append(f"report-write-error:{exc.__class__.__name__}:{exc}")
        try:
            if self.win is not None:
                self.win.saveScreenshot(str(HOLOCORE_INTEGRATION_SMOKE_SCREENSHOT))
        except Exception as exc:
            report.setdefault("errors", []).append(f"screenshot-error:{exc.__class__.__name__}:{exc}")
            try:
                HOLOCORE_INTEGRATION_SMOKE_REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            except Exception:
                pass
        print(json.dumps(report, indent=2))
        try:
            self.dimension_audio.stop()
        except Exception:
            pass
        self.userExit()
        try:
            sys.stdout.flush(); sys.stderr.flush()
        except Exception:
            pass
        os._exit(0 if report.get("status") == "PASS" else 2)
        return Task.done


    def _current_vessel_altitude(self) -> float:
        vessel = getattr(self, "holo_vessel", None)
        if vessel is None:
            return 0.0
        try:
            return max(0.0, float(getattr(vessel, "flight_altitude", 0.0) or 0.0))
        except Exception:
            return 0.0

    def _current_ocean_space_position(self) -> Vec3:
        """Return the position that drives horizontal ocean-space progression."""
        vessel = getattr(self, "holo_vessel", None)
        root = getattr(vessel, "root", None)
        try:
            if root is not None and not root.isEmpty():
                return root.getPos(self.render)
        except Exception:
            pass
        try:
            return self.player.getPos(self.render)
        except Exception:
            return Vec3(0, 0, 0)

    def _current_ocean_space_distance(self) -> float:
        pos = self._current_ocean_space_position()
        return math.hypot(float(pos.x), float(pos.y))

    def _setup_ocean_space_ambient(self) -> None:
        """Build low-cost far-field signal/silhouette nodes for outward travel.

        These nodes make HoloCore feel like an ocean-space without filling the
        screen.  They are a fixed pool of LineSegs parented to one root; only
        transforms and alpha update during the existing slow visual interval.
        """
        root = getattr(self, "ocean_space_ambient_root", None)
        if root is None or root.isEmpty():
            return
        root.hide()
        nodes = []
        for idx in range(7):
            segs = LineSegs(f"ocean_space_distant_signal_bloom_{idx}")
            segs.setThickness(0.82)
            segs.setColor(0.62, 0.96, 1.0, 0.16)
            radius = 18.0 + idx * 3.5
            points = 24
            for step in range(points + 1):
                a = math.tau * step / points
                wobble = 1.0 + math.sin(a * 5.0 + idx) * 0.11
                p = Point3(math.cos(a) * radius * wobble, math.sin(a) * radius * wobble, math.sin(a * 2.0 + idx) * 4.5)
                if step == 0:
                    segs.moveTo(p)
                else:
                    segs.drawTo(p)
            node = root.attachNewNode(segs.create())
            node.setTransparency(TransparencyAttrib.MAlpha)
            node.setPythonTag("ocean_space_kind", "signal_bloom")
            node.setPythonTag("ocean_space_phase", idx * 0.91 + 0.4)
            node.setPythonTag("ocean_space_base_distance", 760.0 + idx * 420.0)
            nodes.append(node)
        for idx in range(5):
            segs = LineSegs(f"ocean_space_far_reef_silhouette_{idx}")
            segs.setThickness(1.0)
            segs.setColor(0.76, 0.74, 1.0, 0.09)
            height = 180.0 + idx * 48.0
            width = 92.0 + idx * 30.0
            pts = [
                Point3(-width, 0.0, -height * 0.35),
                Point3(-width * 0.42, 0.0, height * 0.15),
                Point3(-width * 0.16, 0.0, height * 0.52),
                Point3(width * 0.22, 0.0, height * 0.30),
                Point3(width * 0.55, 0.0, -height * 0.18),
                Point3(width, 0.0, -height * 0.45),
            ]
            for step, p in enumerate(pts):
                if step == 0:
                    segs.moveTo(p)
                else:
                    segs.drawTo(p)
            node = root.attachNewNode(segs.create())
            node.setTransparency(TransparencyAttrib.MAlpha)
            node.setPythonTag("ocean_space_kind", "far_silhouette")
            node.setPythonTag("ocean_space_phase", idx * 1.17 + 2.1)
            node.setPythonTag("ocean_space_base_distance", 1500.0 + idx * 820.0)
            nodes.append(node)
        for idx in range(4):
            segs = LineSegs(f"ocean_space_migration_arc_{idx}")
            segs.setThickness(0.78)
            segs.setColor(1.0, 0.58, 0.92, 0.10)
            radius_x = 180.0 + idx * 52.0
            radius_z = 60.0 + idx * 18.0
            for step in range(17):
                a = math.pi * step / 16.0
                p = Point3(math.cos(a) * radius_x, 0.0, math.sin(a) * radius_z)
                if step == 0:
                    segs.moveTo(p)
                else:
                    segs.drawTo(p)
            node = root.attachNewNode(segs.create())
            node.setTransparency(TransparencyAttrib.MAlpha)
            node.setPythonTag("ocean_space_kind", "migration_arc")
            node.setPythonTag("ocean_space_phase", idx * 1.41 + 4.7)
            node.setPythonTag("ocean_space_base_distance", 2600.0 + idx * 1350.0)
            nodes.append(node)
        self.ocean_space_ambient_nodes = nodes

    def _update_ocean_space_ambient(self, state, time_value: float) -> None:
        root = getattr(self, "ocean_space_ambient_root", None)
        nodes = list(getattr(self, "ocean_space_ambient_nodes", []) or [])
        if root is None or root.isEmpty() or not nodes:
            return
        pos = self._current_ocean_space_position()
        distance = float(getattr(state, "distance", 0.0) or 0.0)
        fade = max(0.0, min(1.0, (distance - 1800.0) / 7000.0))
        if fade <= 0.015:
            root.hide()
            return
        root.show()
        root.setPos(pos)
        t = float(time_value or 0.0)
        distance_mult = max(1.0, float(getattr(state, "entity_distance_multiplier", 1.0) or 1.0))
        scale_mult = max(1.0, float(getattr(state, "entity_scale_multiplier", 1.0) or 1.0))
        for idx, node in enumerate(nodes):
            if node is None or node.isEmpty():
                continue
            phase = float(node.getPythonTag("ocean_space_phase") or 0.0)
            kind = str(node.getPythonTag("ocean_space_kind") or "")
            base_distance = float(node.getPythonTag("ocean_space_base_distance") or 1200.0) * min(3.4, 0.75 + distance_mult * 0.62)
            angle = phase + t * (0.006 + idx * 0.0009)
            z = math.sin(t * 0.018 + phase) * (92.0 + idx * 9.0)
            if kind == "signal_bloom":
                node.setPos(math.cos(angle) * base_distance, math.sin(angle) * base_distance, z + 80.0)
                node.setScale(1.0 + min(2.8, scale_mult * 0.16) + math.sin(t * 0.08 + phase) * 0.035)
                node.setH((math.degrees(angle) + 28.0 * idx) % 360.0)
                node.setP(64.0 + math.sin(t * 0.016 + phase) * 9.0)
                node.setColorScale(1.0, 1.0, 1.0, fade * (0.28 + 0.16 * math.sin(t * 0.045 + phase)))
            elif kind == "far_silhouette":
                node.setPos(math.cos(angle) * base_distance, math.sin(angle) * base_distance, z - 120.0)
                node.setScale(1.3 + min(4.2, scale_mult * 0.30))
                node.setH((math.degrees(angle) + 90.0) % 360.0)
                node.setP(82.0 + math.sin(t * 0.013 + phase) * 4.0)
                node.setColorScale(1.0, 1.0, 1.0, fade * (0.18 + 0.06 * math.sin(t * 0.021 + phase)))
            else:
                node.setPos(math.cos(angle) * base_distance, math.sin(angle) * base_distance, z + 240.0)
                node.setScale(1.0 + min(3.6, scale_mult * 0.22))
                node.setH((math.degrees(angle) + 150.0 + idx * 9.0) % 360.0)
                node.setR(math.sin(t * 0.015 + phase) * 8.0)
                node.setColorScale(1.0, 1.0, 1.0, fade * (0.22 + 0.09 * math.sin(t * 0.026 + phase)))

    def _update_ocean_space_discovery(self, state) -> None:
        band_id = str(getattr(state, "band_id", "safe_core_sea") or "safe_core_sea")
        previous = str(getattr(self, "_ocean_space_last_band_id", "") or "")
        self._ocean_space_last_band_id = band_id
        if band_id == previous or not bool(getattr(self, "holo_vessel_piloting", False)):
            return
        discovered = set(getattr(self, "_ocean_space_discovered_bands", set()) or set())
        first_discovery = band_id not in discovered
        discovered.add(band_id)
        self._ocean_space_discovered_bands = discovered
        band_map = {str(getattr(band, "band_id", "")): band for band in tuple(OCEAN_SPACE_BANDS or ())}
        band = band_map.get(band_id)
        note = str(getattr(band, "signal_note", "") or "")
        prefix = "OCEAN-SPACE DISCOVERED" if first_discovery else "OCEAN-SPACE SHIFT"
        self._show_holocore_layer_notice(prefix, f"{getattr(state, 'band_name', band_id).upper()} // {note.upper()}", duration=4.2 if first_discovery else 2.8)

    def _update_ocean_space_effects(self, dt: float, force: bool = False):
        self._ocean_space_update_elapsed = float(getattr(self, "_ocean_space_update_elapsed", 0.0) or 0.0) + max(0.0, float(dt or 0.0))
        if not force and self._ocean_space_update_elapsed < OCEAN_SPACE_UPDATE_INTERVAL:
            return getattr(self, "ocean_space_state", ocean_space_state_for_position(0.0, 0.0, 0.0))
        elapsed = max(self._ocean_space_update_elapsed, max(0.0, float(dt or 0.0)))
        self._ocean_space_update_elapsed = 0.0
        pos = self._current_ocean_space_position()
        state = ocean_space_state_for_position(float(pos.x), float(pos.y), self._current_vessel_altitude())
        self.ocean_space_state = state
        current_tint = tuple(float(v) for v in getattr(self, "_ocean_space_smoothed_tint", state.tint))
        current_bg = tuple(float(v) for v in getattr(self, "_ocean_space_smoothed_background", state.background))
        self._ocean_space_smoothed_tint = self._smooth_triplet(current_tint, tuple(state.tint), elapsed, OCEAN_SPACE_VISUAL_SMOOTH_SECONDS)
        self._ocean_space_smoothed_background = self._smooth_triplet(current_bg, tuple(state.background), elapsed, OCEAN_SPACE_VISUAL_SMOOTH_SECONDS)
        try:
            self._update_ocean_space_discovery(state)
        except Exception as exc:
            print(f"holocore_ocean_space_discovery_silent err={exc.__class__.__name__}:{exc}")
        try:
            self._update_ocean_space_ambient(state, globalClock.getFrameTime())
        except Exception as exc:
            print(f"holocore_ocean_space_ambient_silent err={exc.__class__.__name__}:{exc}")
        return state

    def _setup_leviathan_expanse_ambient(self) -> None:
        """Build a low-cost high-strata veil field once, then only move it.

        The Leviathan Expanse should feel volumetric and special, but this must
        stay cheap: no particles, no chunk rebuild, no new per-node tasks.  A
        handful of line loops/spines are parented to one root and transformed
        during the existing vertical-strata update interval.
        """
        root = getattr(self, "leviathan_ambient_root", None)
        if root is None or root.isEmpty():
            return
        root.hide()
        nodes = []
        for idx in range(9):
            segs = LineSegs(f"leviathan_expanse_aurora_veil_{idx}")
            segs.setThickness(1.0 + (idx % 3) * 0.22)
            segs.setColor(0.72, 0.96, 1.0, 0.12)
            radius_x = 240.0 + idx * 48.0
            radius_y = 92.0 + idx * 23.0
            z = -180.0 + idx * 54.0
            points = 28
            for step in range(points + 1):
                a = math.tau * step / points
                ripple = 1.0 + math.sin(a * 3.0 + idx * 0.71) * 0.10
                point = Point3(math.cos(a) * radius_x * ripple, math.sin(a) * radius_y, z + math.sin(a * 2.0 + idx) * 18.0)
                if step == 0:
                    segs.moveTo(point)
                else:
                    segs.drawTo(point)
            node = root.attachNewNode(segs.create())
            node.setTransparency(TransparencyAttrib.MAlpha)
            node.setPythonTag("leviathan_ambient_kind", "aurora_veil")
            node.setPythonTag("leviathan_phase", idx * 0.47)
            node.setPythonTag("leviathan_base_distance", 440.0 + idx * 88.0)
            nodes.append(node)
        for idx in range(7):
            segs = LineSegs(f"leviathan_expanse_current_spine_{idx}")
            segs.setThickness(0.85)
            segs.setColor(1.0, 0.42, 0.86, 0.11)
            height = 620.0 + idx * 70.0
            steps = 9
            for step in range(steps):
                t = step / max(1, steps - 1)
                point = Point3(math.sin(t * math.tau * 1.5 + idx) * 40.0, (t - 0.5) * 180.0, (t - 0.5) * height)
                if step == 0:
                    segs.moveTo(point)
                else:
                    segs.drawTo(point)
            node = root.attachNewNode(segs.create())
            node.setTransparency(TransparencyAttrib.MAlpha)
            node.setPythonTag("leviathan_ambient_kind", "distant_current_spine")
            node.setPythonTag("leviathan_phase", idx * 0.63 + 1.7)
            node.setPythonTag("leviathan_base_distance", 580.0 + idx * 120.0)
            nodes.append(node)
        for idx in range(4):
            segs = LineSegs(f"leviathan_expanse_far_wake_shadow_{idx}")
            segs.setThickness(1.05)
            segs.setColor(0.74, 0.86, 1.0, 0.09)
            radius_x = 240.0 + idx * 55.0
            radius_z = 55.0 + idx * 12.0
            points = 18
            for step in range(points + 1):
                a = math.tau * step / points
                if step > points * 0.64:
                    continue
                taper = 1.0 - 0.22 * math.sin(a * 2.0 + idx)
                point = Point3(math.cos(a) * radius_x * taper, math.sin(a) * 24.0, math.sin(a) * radius_z)
                if step == 0:
                    segs.moveTo(point)
                else:
                    segs.drawTo(point)
            node = root.attachNewNode(segs.create())
            node.setTransparency(TransparencyAttrib.MAlpha)
            node.setPythonTag("leviathan_ambient_kind", "far_wake_shadow")
            node.setPythonTag("leviathan_phase", idx * 0.92 + 3.4)
            node.setPythonTag("leviathan_base_distance", 980.0 + idx * 210.0)
            nodes.append(node)
        self.leviathan_ambient_nodes = nodes

    def _update_leviathan_expanse_ambient(self, state, time_value: float) -> None:
        root = getattr(self, "leviathan_ambient_root", None)
        nodes = list(getattr(self, "leviathan_ambient_nodes", []) or [])
        vessel = getattr(self, "holo_vessel", None)
        vessel_root = getattr(vessel, "root", None)
        if root is None or root.isEmpty() or vessel_root is None or vessel_root.isEmpty() or not nodes:
            return
        altitude = self._current_vessel_altitude()
        layer_h = max(1.0, float(VERTICAL_STRATA_LAYER_HEIGHT))
        start_h = float(VERTICAL_STRATA_START_ALTITUDE)
        # Begin the veil late in Storm Abyss and fully open inside Leviathan Expanse.
        fade = max(0.0, min(1.0, (altitude - (start_h + layer_h * 4.55)) / (layer_h * 0.85)))
        if fade <= 0.015:
            root.hide()
            return
        root.show()
        vessel_pos = vessel_root.getPos(self.render)
        root.setPos(vessel_pos)
        t = float(time_value or 0.0)
        distance_mult = max(1.0, float(getattr(state, "creature_distance_multiplier", 1.0) or 1.0))
        for idx, node in enumerate(nodes):
            if node is None or node.isEmpty():
                continue
            phase = float(node.getPythonTag("leviathan_phase") or 0.0)
            kind = str(node.getPythonTag("leviathan_ambient_kind") or "")
            base_distance = float(node.getPythonTag("leviathan_base_distance") or 520.0) * min(2.4, distance_mult * 0.54)
            angle = phase + t * (0.010 + idx * 0.0018)
            if kind == "far_wake_shadow":
                node.setPos(math.cos(angle) * base_distance, math.sin(angle) * base_distance, -260.0 + math.sin(t * 0.018 + phase) * 95.0)
                node.setH((math.degrees(angle) + 90.0 + idx * 11.0) % 360.0)
                node.setP(8.0 + math.sin(t * 0.015 + phase) * 4.0)
                node.setR(math.sin(t * 0.017 + phase) * 5.0)
                node.setScale(1.0 + min(2.6, float(getattr(state, "creature_scale_multiplier", 1.0)) * 0.08))
                node.setColorScale(1.0, 1.0, 1.0, fade * (0.18 + 0.10 * math.sin(t * 0.026 + phase)))
                continue
            node.setPos(math.cos(angle) * base_distance, math.sin(angle) * base_distance, math.sin(t * 0.035 + phase) * 180.0)
            node.setH((math.degrees(angle) + idx * 17.0) % 360.0)
            node.setP(62.0 + math.sin(t * 0.021 + phase) * 8.0)
            node.setR(math.sin(t * 0.027 + phase) * 12.0)
            node.setColorScale(1.0, 1.0, 1.0, fade * (0.34 + 0.18 * math.sin(t * 0.045 + phase)))

    @staticmethod
    def _smooth_triplet(current: tuple[float, float, float], target: tuple[float, float, float], dt: float, seconds: float) -> tuple[float, float, float]:
        seconds = max(0.1, float(seconds or 0.1))
        blend = min(1.0, max(0.0, float(dt or 0.0)) / seconds)
        # Exponential-style small step: slow, stable, and independent from chunk generation.
        blend = 1.0 - pow(1.0 - blend, 1.35)
        return (
            float(current[0]) + (float(target[0]) - float(current[0])) * blend,
            float(current[1]) + (float(target[1]) - float(current[1])) * blend,
            float(current[2]) + (float(target[2]) - float(current[2])) * blend,
        )

    def _update_vertical_strata_effects(self, dt: float, force: bool = False) -> None:
        """Apply cheap altitude-strata visuals without rebuilding streamed chunks."""
        self._vertical_strata_update_elapsed = float(getattr(self, "_vertical_strata_update_elapsed", 0.0) or 0.0) + max(0.0, float(dt or 0.0))
        if not force and self._vertical_strata_update_elapsed < VERTICAL_STRATA_UPDATE_INTERVAL:
            return
        elapsed = max(self._vertical_strata_update_elapsed, max(0.0, float(dt or 0.0)))
        self._vertical_strata_update_elapsed = 0.0
        state = vertical_stratum_state(self._current_vessel_altitude())
        self.vertical_strata_state = state
        ocean_state = self._update_ocean_space_effects(elapsed, force=force)
        current_tint = tuple(float(v) for v in getattr(self, "_vertical_strata_smoothed_tint", state.tint))
        current_bg = tuple(float(v) for v in getattr(self, "_vertical_strata_smoothed_background", state.background))
        self._vertical_strata_smoothed_tint = self._smooth_triplet(current_tint, tuple(state.tint), elapsed, VERTICAL_STRATA_VISUAL_SMOOTH_SECONDS)
        self._vertical_strata_smoothed_background = self._smooth_triplet(current_bg, tuple(state.background), elapsed, VERTICAL_STRATA_VISUAL_SMOOTH_SECONDS)
        ocean_bg = tuple(float(v) for v in getattr(self, "_ocean_space_smoothed_background", getattr(ocean_state, "background", (0.0, 0.0, 0.0))))
        bg = (
            self._vertical_strata_smoothed_background[0] * 0.72 + ocean_bg[0] * 0.28,
            self._vertical_strata_smoothed_background[1] * 0.72 + ocean_bg[1] * 0.28,
            self._vertical_strata_smoothed_background[2] * 0.72 + ocean_bg[2] * 0.28,
        )
        try:
            self.setBackgroundColor(bg[0], bg[1], bg[2], 1.0)
        except Exception:
            pass
        try:
            root = getattr(getattr(self, "outer_world", None), "root", None)
            if root is not None and not root.isEmpty():
                tint = self._vertical_strata_smoothed_tint
                ocean_tint = tuple(float(v) for v in getattr(self, "_ocean_space_smoothed_tint", (1.0, 1.0, 1.0)))
                root.setColorScale(
                    max(0.35, tint[0] * (0.78 + ocean_tint[0] * 0.22)),
                    max(0.35, tint[1] * (0.78 + ocean_tint[1] * 0.22)),
                    max(0.35, tint[2] * (0.78 + ocean_tint[2] * 0.22)),
                    1.0,
                )
        except Exception:
            pass
        try:
            self._update_holocore_layer_discovery(state)
        except Exception as exc:
            print(f"holocore_layer_discovery_silent err={exc.__class__.__name__}:{exc}")
        try:
            self._update_leviathan_expanse_ambient(state, globalClock.getFrameTime())
        except Exception as exc:
            print(f"holocore_leviathan_ambient_silent err={exc.__class__.__name__}:{exc}")

    def _vertical_strata_definition_map(self) -> dict[str, object]:
        return {str(getattr(layer, "layer_id", "")): layer for layer in tuple(VERTICAL_STRATA or ())}

    def _update_holocore_layer_discovery(self, state) -> None:
        layer_id = str(getattr(state, "layer_id", "safe_reef_layer") or "safe_reef_layer")
        previous = str(getattr(self, "_vertical_strata_last_layer_id", "") or "")
        self._vertical_strata_last_layer_id = layer_id
        if layer_id == previous:
            return
        if not bool(getattr(self, "holo_vessel_piloting", False)):
            return
        discovered = set(getattr(self, "_vertical_strata_discovered_layers", set()) or set())
        first_discovery = layer_id not in discovered
        discovered.add(layer_id)
        self._vertical_strata_discovered_layers = discovered
        layer_map = self._vertical_strata_definition_map()
        definition = layer_map.get(layer_id)
        note = str(getattr(definition, "particle_note", "") or "").strip()
        title = str(getattr(state, "layer_name", layer_id.replace("_", " ").title()) or "Unknown Layer").upper()
        prefix = "LAYER DISCOVERED" if first_discovery else "LAYER SHIFT"
        detail = note.upper() if note else "STRATA STABILIZING"
        self._show_holocore_layer_notice(f"{prefix} // {title}", detail)

    def _ascent_entity_key_for_spec(self, spec, altitude: float, vessel_pos: Point3 | Vec3) -> tuple[int, int, int]:
        spacing = max(100.0, float(getattr(spec, "altitude_spacing", 2000.0) or 2000.0))
        altitude_cell = int(math.floor(max(0.0, float(altitude or 0.0)) / spacing))
        # Use coarse horizontal cells so encounters are far apart and stable as the vessel moves.
        horizontal_cell = 1800.0
        return (
            int(math.floor(float(vessel_pos.x) / horizontal_cell)),
            int(math.floor(float(vessel_pos.y) / horizontal_cell)),
            altitude_cell,
        )

    def _ascent_spawn_position(self, spec, key: tuple[int, int, int], vessel_pos: Point3 | Vec3, state) -> tuple[Vec3, float, float] | None:
        try:
            seed_func = getattr(spec, "seed_func")
            seed = int(seed_func((key[0] ^ key[2], key[1] + key[2] * 17), int(getattr(spec, "seed_salt", 0xA5CE))))
            rng = random.Random(seed)
            ocean_state = getattr(self, "ocean_space_state", None)
            ocean_rarity = max(1.0, float(getattr(ocean_state, "entity_rarity_multiplier", 1.0) or 1.0))
            rarity = max(1.0, float(getattr(state, "creature_rarity_multiplier", 1.0) or 1.0)) * ocean_rarity
            chance = max(0.008, min(0.85, float(getattr(spec, "spawn_chance", 0.1)) / rarity))
            # Keep at least one deterministic selected cell in smoke/test altitude ranges by using stable cells,
            # but normal play remains sparse because altitude cells are large and chance shrinks upward.
            if rng.random() >= chance:
                return None
            ocean_distance = max(1.0, float(getattr(ocean_state, "entity_distance_multiplier", 1.0) or 1.0))
            distance = float(getattr(spec, "base_distance", 520.0)) * max(1.0, float(getattr(state, "creature_distance_multiplier", 1.0) or 1.0)) * ocean_distance
            distance *= rng.uniform(0.88, 1.26)
            angle = rng.uniform(0.0, math.tau)
            z_offset = rng.uniform(float(getattr(spec, "vertical_offset_min", -100.0)), float(getattr(spec, "vertical_offset_max", 100.0)))
            pos = Vec3(
                float(vessel_pos.x) + math.cos(angle) * distance,
                float(vessel_pos.y) + math.sin(angle) * distance,
                float(vessel_pos.z) + z_offset,
            )
            ocean_scale = max(1.0, float(getattr(ocean_state, "entity_scale_multiplier", 1.0) or 1.0))
            scale = rng.uniform(float(getattr(spec, "scale_min", 1.0)), float(getattr(spec, "scale_max", 1.0))) * max(1.0, float(getattr(state, "creature_scale_multiplier", 1.0) or 1.0)) * ocean_scale
            heading = math.degrees(angle + math.pi + rng.uniform(-0.45, 0.45))
            return pos, scale, heading
        except Exception as exc:
            print(f"holocore_ascent_spawn_calc_silent entity={getattr(spec, 'entity_id', 'unknown')} err={exc.__class__.__name__}:{exc}")
            return None

    def _clear_ascent_entities(self) -> None:
        for mob in list(getattr(self, "ascent_entity_mobs", {}).values()):
            try:
                mob.destroy()
            except Exception:
                pass
        self.ascent_entity_mobs = {}

    def _build_ascent_entity(self, spec, key: tuple[int, int, int], vessel_pos: Point3 | Vec3, state, force_near: bool = False) -> object | None:
        if getattr(self, "ascent_entity_root", None) is None:
            return None
        spawn = self._ascent_spawn_position(spec, key, vessel_pos, state)
        if spawn is None and force_near:
            spawn = (Vec3(float(vessel_pos.x) + 42.0, float(vessel_pos.y), float(vessel_pos.z) + 8.0), float(getattr(spec, "scale_min", 1.0)) * 1.25, 90.0)
        if spawn is None:
            return None
        pos, scale, heading = spawn
        try:
            seed_func = getattr(spec, "seed_func")
            seed = seed_func((key[0] ^ key[2], key[1] + key[2] * 17), int(getattr(spec, "seed_salt", 0xA5CE)) ^ 0xBEE7)
            mob = getattr(spec, "mob_class")(seed=seed).build(self.ascent_entity_root, pos, scale=scale, heading=heading)
            setattr(mob, "_holocore_ascent_entity_id", str(getattr(spec, "entity_id", "ascent_entity")))
            setattr(mob, "_holocore_ascent_cell", tuple(key))
            setattr(mob, "_holocore_ascent_behavior", str(getattr(spec, "behavior_id", "")))
            setattr(mob, "_holocore_contact_radius", float(getattr(spec, "contact_radius", 50.0)) * max(1.0, float(scale) * 0.28))
            return mob
        except Exception as exc:
            print(f"holocore_ascent_entity_spawn_silent entity={getattr(spec, 'entity_id', 'unknown')} err={exc.__class__.__name__}:{exc}")
            return None

    def _update_ascent_entities(self, time_value: float, dt: float) -> None:
        vessel = getattr(self, "holo_vessel", None)
        root = getattr(vessel, "root", None)
        if vessel is None or root is None or root.isEmpty():
            return
        self._ascent_entity_update_elapsed = float(getattr(self, "_ascent_entity_update_elapsed", 0.0) or 0.0) + max(0.0, float(dt or 0.0))
        if self._ascent_entity_update_elapsed < ASCENT_ENCOUNTER_UPDATE_INTERVAL:
            return
        self._ascent_entity_update_elapsed = 0.0
        state = getattr(self, "vertical_strata_state", vertical_stratum_state(self._current_vessel_altitude()))
        altitude = self._current_vessel_altitude()
        vessel_pos = root.getPos(self.render)
        if altitude < 4000.0:
            self._clear_ascent_entities()
            self.holocore_threat_level = max(0.0, float(getattr(self, "holocore_threat_level", 0.0) or 0.0) - 0.18)
            self.holocore_threat_entity = ""
            self.holocore_threat_distance = 0.0
            return
        alive: dict[str, object] = {}
        best_threat_level = max(0.0, float(getattr(self, "holocore_threat_level", 0.0) or 0.0) - 0.08)
        best_threat_entity = str(getattr(self, "holocore_threat_entity", "") or "")
        best_threat_distance = float(getattr(self, "holocore_threat_distance", 0.0) or 0.0)
        for spec in tuple(ASCENT_ENTITY_SPECS or ()):  # sparse, usually 0-2 entries
            entity_id = str(getattr(spec, "entity_id", "ascent_entity"))
            if altitude < float(getattr(spec, "min_altitude", 0.0)):
                old = getattr(self, "ascent_entity_mobs", {}).get(entity_id)
                if old is not None:
                    try:
                        old.destroy()
                    except Exception:
                        pass
                continue
            key = self._ascent_entity_key_for_spec(spec, altitude, vessel_pos)
            mob = getattr(self, "ascent_entity_mobs", {}).get(entity_id)
            if mob is not None and getattr(mob, "_holocore_ascent_cell", None) != tuple(key):
                try:
                    mob.destroy()
                except Exception:
                    pass
                mob = None
            if mob is None:
                mob = self._build_ascent_entity(spec, key, vessel_pos, state)
            if mob is None:
                continue
            try:
                mob.update_pose(float(time_value or 0.0))
                mob.set_visibility_alpha(0.72)
                mob_root = getattr(mob, "root", None)
                if mob_root is None or mob_root.isEmpty():
                    continue
                mob_pos = mob_root.getPos(self.render)
                planar = math.hypot(float(mob_pos.x - vessel_pos.x), float(mob_pos.y - vessel_pos.y))
                vertical = abs(float(mob_pos.z - vessel_pos.z))
                contact_radius = float(getattr(mob, "_holocore_contact_radius", getattr(mob, "contact_radius", 50.0)) or 50.0)
                warning_radius = max(contact_radius * 5.75, float(getattr(spec, "base_distance", 700.0)) * 0.42)
                vertical_factor = 1.0 if vertical <= contact_radius * 2.8 else max(0.0, 1.0 - (vertical - contact_radius * 2.8) / max(contact_radius * 8.0, 1.0))
                if planar <= warning_radius and vertical_factor > 0.0:
                    near = 1.0 - max(0.0, min(1.0, (planar - contact_radius) / max(1.0, warning_radius - contact_radius)))
                    threat = max(0.0, min(1.0, near * vertical_factor))
                    if threat > best_threat_level:
                        best_threat_level = threat
                        best_threat_entity = entity_id
                        best_threat_distance = planar
                if planar <= contact_radius and vertical <= contact_radius * 0.55:
                    self.holocore_threat_level = 1.0
                    self.holocore_threat_entity = entity_id
                    self.holocore_threat_distance = planar
                    self._begin_holocore_rescue(entity_id)
                    alive[entity_id] = mob
                    break
                # Far-away cleanup keeps old high-altitude encounters from lingering forever.
                if planar > max(2600.0, float(getattr(spec, "base_distance", 700.0)) * 5.0):
                    mob.destroy()
                    continue
                alive[entity_id] = mob
            except Exception as exc:
                print(f"holocore_ascent_entity_update_silent entity={entity_id} err={exc.__class__.__name__}:{exc}")
        self.ascent_entity_mobs = alive
        if not bool(getattr(self, "holocore_rescue_pending", False)):
            self.holocore_threat_level = max(0.0, min(1.0, best_threat_level))
            self.holocore_threat_entity = best_threat_entity
            self.holocore_threat_distance = max(0.0, float(best_threat_distance or 0.0))

    def _begin_holocore_rescue(self, attacker: str) -> None:
        if bool(getattr(self, "holocore_rescue_pending", False)):
            return
        self.holocore_rescue_pending = True
        self.holocore_rescue_started_at = time.monotonic()
        self.holocore_rescue_reset_done = False
        self.holocore_rescue_attacker = str(attacker or "unknown_ascent_entity")
        self._reset_movement_keys()
        label = str(attacker or "unknown_ascent_entity").replace("holo_", "").replace("_", " ").upper()
        self._show_bridge_transition("HOLOCORE IMPACT", f"{label} CONTACT // CORE RECOVERY", target=1.0)

    def _reset_holocore_rescue_to_start(self) -> None:
        vessel = getattr(self, "holo_vessel", None)
        if vessel is None or getattr(vessel, "root", None) is None:
            return
        try:
            ground = float(self.outer_world.collision_ground_z_at(0.0, -212.0))
        except Exception:
            ground = 0.0
        vessel.flight_altitude = 0.0
        vessel.base_ground_z = ground
        try:
            vessel.reset_motion()
        except Exception:
            pass
        vessel.root.setPos(0.0, -212.0, ground)
        vessel.root.setH(180.0)
        self.holo_vessel_boarded = False
        self.holo_vessel_piloting = False
        self.player.setPos(vessel.exit_world_position(ground))
        self.heading = 180.0
        self.pitch = -4.0
        self.player.setH(self.heading)
        self.camera.reparentTo(self.player)
        self.camera.setPos(0, 0, self.eye_height)
        self.camera.setHpr(0, self.pitch, 0)
        self._last_applied_heading = self.heading
        self._last_applied_pitch = self.pitch
        self._clear_ascent_entities()
        self.holocore_threat_level = 0.0
        self.holocore_threat_entity = ""
        self.holocore_threat_distance = 0.0
        self._set_holocore_threat_warning(None)
        self._holo_vessel_camera_smooth_pos = None
        self._holo_vessel_camera_smooth_look = None
        if getattr(self, "holocore_layer_notice", None) is not None:
            self.holocore_layer_notice.hide()
            self._holocore_layer_notice_visible = False
            self._holocore_layer_notice_text = None
        self._update_vertical_strata_effects(1.0, force=True)
        try:
            self.outer_world.sync_around(self.player.getPos(self.render), force=True, immediate=True)
        except Exception:
            pass

    def _update_holocore_rescue(self) -> None:
        if not bool(getattr(self, "holocore_rescue_pending", False)):
            return
        elapsed = time.monotonic() - float(getattr(self, "holocore_rescue_started_at", time.monotonic()) or time.monotonic())
        if elapsed >= 0.55 and not bool(getattr(self, "holocore_rescue_reset_done", False)):
            self._reset_holocore_rescue_to_start()
            self.holocore_rescue_reset_done = True
            self._show_bridge_transition("HOLOCORE RECOVERY", "VESSEL PARKED AT SAFE ANCHOR", target=1.0)
        if elapsed >= 1.08:
            self._show_bridge_transition("HOLOCORE RECOVERY", "VESSEL PARKED AT SAFE ANCHOR", target=0.0)
        if elapsed >= 1.82:
            self.holocore_rescue_pending = False
            self.holocore_rescue_started_at = 0.0
            self.holocore_rescue_reset_done = False
            self.holocore_rescue_attacker = ""



    def _build_holo_vessel_outside_pyramid(self) -> None:
        """Spawn the walkable crescent vessel outside the pyramid, terrain-locked."""
        try:
            ground = float(self.outer_world.collision_ground_z_at(0.0, -212.0))
        except Exception:
            ground = 0.0
        self.holo_vessel = HoloVessel().build(self, Vec3(0.0, -212.0, ground), heading=180.0)

    def _setup_holo_vessel_prompt(self) -> None:
        self.holo_vessel_prompt = OnscreenText(
            text="",
            pos=(0.0, -0.805),
            scale=0.037,
            fg=(0.60, 1.0, 0.86, 0.96),
            shadow=(0.0, 0.0, 0.0, 0.78),
            mayChange=True,
        )
        self.holo_vessel_prompt.hide()
        self._holo_vessel_prompt_text = None
        self._holo_vessel_prompt_visible = False

    def _holo_vessel_keepout_allows(self, x: float, y: float) -> bool:
        """Keep the piloted vessel outside the pyramid shell buffer."""
        try:
            return not self.hub.is_inside_hub(float(x), float(y), margin=52.0)
        except Exception:
            return True

    def _set_holo_vessel_prompt(self, text: str | None) -> None:
        prompt = getattr(self, "holo_vessel_prompt", None)
        if prompt is None:
            return
        text = str(text or "").strip()
        if not text:
            if self._holo_vessel_prompt_visible is not False:
                prompt.hide()
                self._holo_vessel_prompt_visible = False
            return
        if self._holo_vessel_prompt_text != text:
            prompt.setText(text)
            self._holo_vessel_prompt_text = text
        if self._holo_vessel_prompt_visible is not True:
            prompt.show()
            self._holo_vessel_prompt_visible = True

    def _setup_holocore_threat_warning(self) -> None:
        self.holocore_threat_warning = OnscreenText(
            text="",
            pos=(0.0, 0.78),
            scale=0.043,
            fg=(0.90, 0.96, 1.0, 0.0),
            shadow=(0.0, 0.0, 0.0, 0.70),
            align=TextNode.ACenter,
            mayChange=True,
        )
        self.holocore_threat_warning.hide()

    def _set_holocore_threat_warning(self, text: str | None, alpha: float = 0.0) -> None:
        warning = getattr(self, "holocore_threat_warning", None)
        if warning is None:
            return
        text = str(text or "").strip()
        alpha = max(0.0, min(0.86, float(alpha or 0.0)))
        if not text or alpha <= 0.025:
            if bool(getattr(self, "_holocore_threat_warning_visible", False)):
                warning.hide()
                self._holocore_threat_warning_visible = False
            self._holocore_threat_warning_text = None
            return
        if self._holocore_threat_warning_text != text:
            warning.setText(text)
            self._holocore_threat_warning_text = text
        warning.setFg((0.84, 0.98, 1.0, alpha))
        if not bool(getattr(self, "_holocore_threat_warning_visible", False)):
            warning.show()
            self._holocore_threat_warning_visible = True

    def _setup_holocore_layer_notice(self) -> None:
        self.holocore_layer_notice = OnscreenText(
            text="",
            pos=(0.0, 0.675),
            scale=0.034,
            fg=(0.72, 0.94, 1.0, 0.0),
            shadow=(0.0, 0.0, 0.0, 0.62),
            align=TextNode.ACenter,
            mayChange=True,
        )
        self.holocore_layer_notice.hide()

    def _show_holocore_layer_notice(self, title: str, detail: str = "", duration: float = 4.25) -> None:
        notice = getattr(self, "holocore_layer_notice", None)
        if notice is None:
            return
        title = str(title or "").strip()
        detail = str(detail or "").strip()
        if not title:
            return
        text = title if not detail else f"{title}\n{detail[:86]}"
        if self._holocore_layer_notice_text != text:
            notice.setText(text)
            self._holocore_layer_notice_text = text
        self._holocore_layer_notice_started_at = time.monotonic()
        self._holocore_layer_notice_duration = max(1.0, float(duration or 4.25))
        self._holocore_layer_notice_visible = True
        notice.setFg((0.72, 0.94, 1.0, 0.70))
        notice.show()

    def _update_holocore_layer_notice(self) -> None:
        notice = getattr(self, "holocore_layer_notice", None)
        if notice is None or not bool(getattr(self, "_holocore_layer_notice_visible", False)):
            return
        elapsed = time.monotonic() - float(getattr(self, "_holocore_layer_notice_started_at", 0.0) or 0.0)
        duration = max(1.0, float(getattr(self, "_holocore_layer_notice_duration", 4.25) or 4.25))
        if elapsed >= duration:
            notice.hide()
            self._holocore_layer_notice_visible = False
            self._holocore_layer_notice_text = None
            return
        fade_start = duration * 0.58
        if elapsed <= fade_start:
            alpha = 0.70
        else:
            alpha = 0.70 * max(0.0, 1.0 - (elapsed - fade_start) / max(0.001, duration - fade_start))
        notice.setFg((0.72, 0.94, 1.0, max(0.0, min(0.70, alpha))))

    def _update_holocore_threat_warning(self, dt: float) -> None:
        if not bool(getattr(self, "holo_vessel_piloting", False)) or bool(getattr(self, "holocore_rescue_pending", False)):
            self.holocore_threat_level = max(0.0, float(getattr(self, "holocore_threat_level", 0.0) or 0.0) - max(0.0, float(dt or 0.0)) * 0.9)
        level = max(0.0, min(1.0, float(getattr(self, "holocore_threat_level", 0.0) or 0.0)))
        if level <= 0.035:
            self._set_holocore_threat_warning(None)
            return
        entity = str(getattr(self, "holocore_threat_entity", "") or "large_mass")
        label = "MASSIVE ENTITY"
        if "dragon" in entity:
            label = "DRAGON WHALE"
        elif "serpent" in entity:
            label = "STORM SERPENT"
        distance = max(0.0, float(getattr(self, "holocore_threat_distance", 0.0) or 0.0))
        if level >= 0.70:
            prefix = "PROXIMITY WARNING"
        elif level >= 0.38:
            prefix = "SONAR CONTACT"
        else:
            prefix = "DISTANT MASS"
        self._set_holocore_threat_warning(f"{prefix} // {label} // {distance:.0f}m", alpha=0.22 + level * 0.48)

    def _update_holo_vessel_prompt(self) -> None:
        vessel = getattr(self, "holo_vessel", None)
        if vessel is None or getattr(self, "player", None) is None:
            self._set_holo_vessel_prompt(None)
            return
        if bool(getattr(self, "holocore_rescue_pending", False)):
            self._set_holo_vessel_prompt("HOLOCORE RESCUE // VESSEL RECOVERED TO SAFE ANCHOR")
            return
        if bool(getattr(self, "holo_vessel_piloting", False)):
            state = getattr(self, "vertical_strata_state", vertical_stratum_state(self._current_vessel_altitude()))
            ocean = getattr(self, "ocean_space_state", ocean_space_state_for_position(0.0, 0.0, 0.0))
            self._set_holo_vessel_prompt(f"HOLO VESSEL // ASCENT {self._current_vessel_altitude():.0f} // {state.layer_name} // {ocean.band_name} // SPACE UP // C DOWN // E LEAVE")
            return
        pos = self.player.getPos(self.render)
        if bool(getattr(self, "holo_vessel_boarded", False)):
            if vessel.is_near_pilot(pos):
                self._set_holo_vessel_prompt("HOLO VESSEL // E PILOT SEAT")
            elif vessel.is_near_exit(pos):
                self._set_holo_vessel_prompt("HOLO VESSEL // E EXIT TO TERRAIN")
            else:
                self._set_holo_vessel_prompt("HOLO VESSEL // WALKABLE CABIN // FIND SEAT OR REAR EXIT")
            return
        if vessel.is_near_entry(pos):
            self._set_holo_vessel_prompt("HOLO VESSEL // E BOARD CRESCENT RUNNER")
        else:
            self._set_holo_vessel_prompt(None)

    def _board_holo_vessel(self) -> bool:
        vessel = getattr(self, "holo_vessel", None)
        if vessel is None:
            return False
        self._close_dimension_gate_panel()
        self._reset_movement_keys()
        self.holo_vessel_boarded = True
        self.holo_vessel_piloting = False
        self.player.setPos(vessel.board_spawn_world_position())
        self.heading = float(vessel.root.getH(self.render)) if vessel.root is not None else self.heading
        self.pitch = -3.0
        self.player.setH(self.heading)
        self.camera.reparentTo(self.player)
        self.camera.setPos(0, 0, self.eye_height)
        self.camera.setHpr(0, self.pitch, 0)
        self._last_applied_heading = self.heading
        self._last_applied_pitch = self.pitch
        self._lock_mouse()
        return True

    def _exit_holo_vessel_to_terrain(self) -> bool:
        vessel = getattr(self, "holo_vessel", None)
        if vessel is None:
            return False
        self._reset_movement_keys()
        self.holo_vessel_piloting = False
        self.holo_vessel_boarded = False
        entry = vessel.entry_world_position()
        try:
            terrain_z = float(self.outer_world.collision_ground_z_at(float(entry.x), float(entry.y)))
        except Exception:
            terrain_z = float(entry.z)
        self.player.setPos(vessel.exit_world_position(terrain_z))
        self.camera.reparentTo(self.player)
        self.camera.setPos(0, 0, self.eye_height)
        self.pitch = max(-18.0, min(12.0, float(getattr(self, "pitch", -4.0) or -4.0)))
        self.camera.setHpr(0, self.pitch, 0)
        self._holo_vessel_camera_smooth_pos = None
        self._holo_vessel_camera_smooth_look = None
        self._last_applied_pitch = self.pitch
        self.outer_world.sync_around(self.player.getPos(self.render), force=True, immediate=True)
        self._lock_mouse()
        return True

    def _enter_holo_vessel_pilot_seat(self) -> bool:
        vessel = getattr(self, "holo_vessel", None)
        if vessel is None:
            return False
        self._close_dimension_gate_panel()
        self._reset_movement_keys()
        self.holo_vessel_boarded = True
        self.holo_vessel_piloting = True
        self.player.setPos(vessel.pilot_seat_world_position())
        self.camera.reparentTo(self.render)
        self._holo_vessel_camera_smooth_pos = None
        self._holo_vessel_camera_smooth_look = None
        self._update_holo_vessel_pilot_camera(immediate=True)
        self._lock_mouse()
        return True

    def _leave_holo_vessel_pilot_seat(self) -> bool:
        vessel = getattr(self, "holo_vessel", None)
        if vessel is None:
            return False
        self._reset_movement_keys()
        self.holo_vessel_piloting = False
        self.holo_vessel_boarded = True
        self.player.setPos(vessel.pilot_seat_world_position())
        self.heading = float(vessel.root.getH(self.render)) if vessel.root is not None else self.heading
        self.pitch = -4.0
        self.player.setH(self.heading)
        self.camera.reparentTo(self.player)
        self.camera.setPos(0, 0, self.eye_height)
        self.camera.setHpr(0, self.pitch, 0)
        self._holo_vessel_camera_smooth_pos = None
        self._holo_vessel_camera_smooth_look = None
        self._last_applied_heading = self.heading
        self._last_applied_pitch = self.pitch
        self._lock_mouse()
        return True

    def _try_holo_vessel_interaction(self) -> bool:
        vessel = getattr(self, "holo_vessel", None)
        if vessel is None or getattr(self, "player", None) is None:
            return False
        if bool(getattr(self, "holo_vessel_piloting", False)):
            return self._leave_holo_vessel_pilot_seat()
        pos = self.player.getPos(self.render)
        if bool(getattr(self, "holo_vessel_boarded", False)):
            if vessel.is_near_pilot(pos):
                return self._enter_holo_vessel_pilot_seat()
            if vessel.is_near_exit(pos):
                return self._exit_holo_vessel_to_terrain()
            return False
        if vessel.is_near_entry(pos):
            return self._board_holo_vessel()
        return False

    def _handle_e_interaction(self) -> None:
        # E is now reserved for local HoloCore interactions such as boarding,
        # exiting, and piloting the vessel.  Dimension menu access belongs back
        # in MatrixCore/Core so boarding cannot be stolen by a gate panel.
        if self._dimension_gate_panel_visible():
            return
        if self._try_holo_vessel_interaction():
            return

    def _holo_vessel_ground_z(self, x: float, y: float) -> float:
        try:
            return float(self.outer_world.collision_ground_z_at(float(x), float(y)))
        except Exception:
            return 0.0

    def _update_holo_vessel_pilot_camera(self, dt: float = 0.0, immediate: bool = False) -> None:
        vessel = getattr(self, "holo_vessel", None)
        if vessel is None:
            return
        desired_pos = Point3(vessel.pilot_camera_world_position())
        desired_look = Point3(vessel.pilot_look_world_position())
        if immediate or self._holo_vessel_camera_smooth_pos is None or self._holo_vessel_camera_smooth_look is None:
            self._holo_vessel_camera_smooth_pos = Point3(desired_pos)
            self._holo_vessel_camera_smooth_look = Point3(desired_look)
        else:
            blend = 1.0 - math.exp(-max(0.0, float(dt or 0.0)) * 4.2)
            blend = max(0.0, min(1.0, blend))
            old_pos = Point3(self._holo_vessel_camera_smooth_pos)
            old_look = Point3(self._holo_vessel_camera_smooth_look)
            self._holo_vessel_camera_smooth_pos = Point3(old_pos + (desired_pos - old_pos) * blend)
            self._holo_vessel_camera_smooth_look = Point3(old_look + (desired_look - old_look) * blend)
        self.camera.setPos(self._holo_vessel_camera_smooth_pos)
        self.camera.lookAt(self._holo_vessel_camera_smooth_look)

    def _update_holo_vessel_piloting(self, dt: float) -> None:
        vessel = getattr(self, "holo_vessel", None)
        if vessel is None:
            return
        forward_axis = 0.0
        if self.key_map.get("w") or self.key_map.get("arrow_up"):
            forward_axis += 1.0
        if self.key_map.get("s") or self.key_map.get("arrow_down"):
            forward_axis -= 1.0
        turn_axis = 0.0
        if self.key_map.get("a") or self.key_map.get("arrow_left"):
            turn_axis += 1.0
        if self.key_map.get("d") or self.key_map.get("arrow_right"):
            turn_axis -= 1.0
        vertical_axis = 0.0
        if self.key_map.get("space") or self.key_map.get("page_up"):
            vertical_axis += 1.0
        if self.key_map.get("c") or self.key_map.get("page_down"):
            vertical_axis -= 1.0
        moved = vessel.move_piloted(
            dt,
            forward_axis=forward_axis,
            turn_axis=turn_axis,
            vertical_axis=vertical_axis,
            terrain_height_func=self._holo_vessel_ground_z,
            keepout_func=self._holo_vessel_keepout_allows,
        )
        self.player.setPos(vessel.pilot_seat_world_position())
        self._update_holo_vessel_pilot_camera(dt=dt, immediate=False)
        self._update_vertical_strata_effects(dt, force=bool(moved))
        if moved:
            try:
                self.outer_world.sync_around(self.player.getPos(self.render), force=False, immediate=False)
            except Exception:
                pass

    def _clamp_player_with_holo_vessel(self, old_pos: Vec3, new_pos: Vec3) -> Vec3:
        vessel = getattr(self, "holo_vessel", None)
        if vessel is None:
            return self.outer_world.clamp_position(new_pos)
        if bool(getattr(self, "holo_vessel_boarded", False)):
            return Vec3(vessel.clamp_interior_position(new_pos))
        terrain_pos = self.outer_world.clamp_position(new_pos)
        return Vec3(vessel.push_outside_around_hull(old_pos, terrain_pos))

    def _capture_holocore_smoke_screenshot(self, path: Path, camera_pos: Point3 | Vec3, look_at: Point3 | Vec3, fov: float = 72.0) -> bool:
        try:
            self.camera.reparentTo(self.render)
            self.camera.setPos(camera_pos)
            self.camera.lookAt(look_at)
            self.camLens.setFov(float(fov))
            for _ in range(5):
                self.graphicsEngine.renderFrame()
            path.parent.mkdir(parents=True, exist_ok=True)
            return bool(self.win is not None and self.win.saveScreenshot(str(path)))
        except Exception as exc:
            print(f"holocore_vessel_screenshot_failed path={path.name} err={exc.__class__.__name__}:{exc}")
            return False

    def _vessel_smoke_setup(self, task: Task) -> int:
        self.vessel_smoke_steps = []
        try:
            vessel = getattr(self, "holo_vessel", None)
            if vessel is None:
                self.vessel_smoke_steps.append({"step": "spawn", "ok": False, "error": "missing-vessel"})
                return Task.done
            names = []
            try:
                for np in vessel.root.findAllMatches("**"):
                    names.append(np.getName())
            except Exception:
                pass
            physical_room_size = [round(float(value), 3) for value in vessel.physical_room_size()]
            no_platform = not any("landing_pad" in name.lower() or "platform" in name.lower() for name in names)
            root_pos = vessel.root.getPos(self.render)
            outside_pyramid = not self.hub.is_inside_hub(float(root_pos.x), float(root_pos.y), margin=0.0)
            self.vessel_smoke_steps.append({
                "step": "spawn_outside_pyramid",
                "ok": bool(outside_pyramid and no_platform),
                "vessel_position": [round(float(root_pos.x), 3), round(float(root_pos.y), 3), round(float(root_pos.z), 3)],
                "outside_pyramid": bool(outside_pyramid),
                "rectangle_platform_absent": bool(no_platform),
                "vessel_world_scale": round(float(getattr(vessel, "world_scale", 1.0) or 1.0), 3),
                "physical_room_size": physical_room_size,
            })
            self.outer_world.sync_around(root_pos, force=True, immediate=True)
            self._capture_holocore_smoke_screenshot(
                HOLOCORE_VESSEL_EXTERIOR_SCREENSHOT,
                vessel.local_point(78.0, -104.0, 58.0),
                vessel.local_point(0.0, 2.0, 10.5),
                63.0,
            )
            self.player.setPos(vessel.entry_world_position())
            entry_ground = self.outer_world.clamp_position(self.player.getPos(self.render))
            self.player.setPos(entry_ground)
            boarded = self._try_holo_vessel_interaction()
            local_after_board = vessel.world_to_local(self.player.getPos(self.render))
            self.vessel_smoke_steps.append({
                "step": "board_with_e",
                "ok": bool(boarded and self.holo_vessel_boarded and vessel.is_inside_room(self.player.getPos(self.render))),
                "boarded": bool(self.holo_vessel_boarded),
                "local_position": [round(float(local_after_board.x), 3), round(float(local_after_board.y), 3), round(float(local_after_board.z), 3)],
            })
            self._capture_holocore_smoke_screenshot(
                HOLOCORE_VESSEL_INTERIOR_SCREENSHOT,
                vessel.local_point(0.0, -27.0, 14.0),
                vessel.local_point(0.0, 25.0, 12.0),
                76.0,
            )
            forced = vessel.local_point(40.0, 0.0, 25.0)
            clamped = vessel.clamp_interior_position(forced)
            clamped_local = vessel.world_to_local(clamped)
            self.vessel_smoke_steps.append({
                "step": "interior_collision_clamp",
                "ok": abs(float(clamped_local.x)) <= vessel.room_max_x + 0.001 and abs(float(clamped_local.y)) <= vessel.room_max_y + 0.001,
                "forced_local": [40.0, 0.0, 25.0],
                "clamped_local": [round(float(clamped_local.x), 3), round(float(clamped_local.y), 3), round(float(clamped_local.z), 3)],
            })
            self.player.setPos(vessel.pilot_seat_world_position())
            piloted = self._try_holo_vessel_interaction()
            old_pos = vessel.root.getPos(self.render)
            old_h = float(vessel.root.getH(self.render))
            old_altitude = float(getattr(vessel, "flight_altitude", 0.0))
            self.key_map["w"] = True
            self.key_map["a"] = True
            self.key_map["space"] = True
            for _ in range(24):
                self._update_holo_vessel_piloting(0.08)
            self.key_map["w"] = False
            self.key_map["a"] = False
            self.key_map["space"] = False
            climb_pos = vessel.root.getPos(self.render)
            climb_h = float(vessel.root.getH(self.render))
            climb_altitude = float(getattr(vessel, "flight_altitude", 0.0))
            self.key_map["c"] = True
            for _ in range(36):
                self._update_holo_vessel_piloting(0.08)
            self.key_map["c"] = False
            new_pos = vessel.root.getPos(self.render)
            new_altitude = float(getattr(vessel, "flight_altitude", 0.0))
            terrain_z = self._holo_vessel_ground_z(float(new_pos.x), float(new_pos.y))
            expected_z = terrain_z + new_altitude
            self.vessel_smoke_steps.append({
                "step": "pilot_seat_flight_controls",
                "ok": bool(
                    piloted
                    and self.holo_vessel_piloting
                    and (climb_pos - old_pos).lengthSquared() > 0.001
                    and abs(climb_h - old_h) > 0.01
                    and climb_altitude > old_altitude
                    and 0.0 <= new_altitude < climb_altitude
                    and new_altitude <= float(getattr(vessel, "max_flight_altitude", 0.0))
                    and abs(float(new_pos.z) - expected_z) < 0.001
                ),
                "piloting": bool(self.holo_vessel_piloting),
                "moved_distance": round(float((climb_pos - old_pos).length()), 4),
                "yaw_delta": round(float(climb_h - old_h), 4),
                "climb_altitude": round(float(climb_altitude), 4),
                "descended_altitude": round(float(new_altitude), 4),
                "vessel_z": round(float(new_pos.z), 6),
                "terrain_z": round(float(terrain_z), 6),
                "expected_surface_offset_z": round(float(expected_z), 6),
            })
            self._capture_holocore_smoke_screenshot(
                HOLOCORE_VESSEL_PILOT_SCREENSHOT,
                vessel.pilot_camera_world_position(),
                vessel.pilot_look_world_position(),
                77.0,
            )
            self._leave_holo_vessel_pilot_seat()
            self.player.setPos(vessel.local_point(0.0, -29.0, vessel.floor_local_z))
            exited = self._try_holo_vessel_interaction()
            player_pos = self.player.getPos(self.render)
            expected_z = self._holo_vessel_ground_z(float(player_pos.x), float(player_pos.y))
            self.vessel_smoke_steps.append({
                "step": "exit_to_terrain_surface",
                "ok": bool(exited and not self.holo_vessel_boarded and abs(float(player_pos.z) - expected_z) < 0.001),
                "boarded": bool(self.holo_vessel_boarded),
                "player_position": [round(float(player_pos.x), 3), round(float(player_pos.y), 3), round(float(player_pos.z), 6)],
                "terrain_z": round(float(expected_z), 6),
            })
        except Exception as exc:
            self.vessel_smoke_steps.append({"step": "exception", "ok": False, "error": f"{exc.__class__.__name__}:{exc}"})
        return Task.done

    def _collect_vessel_smoke_report(self) -> dict:
        steps = list(getattr(self, "vessel_smoke_steps", []) or [])
        errors: list[str] = []
        if not steps:
            errors.append("no-vessel-smoke-steps-recorded")
        for step in steps:
            if isinstance(step, dict) and not bool(step.get("ok", False)):
                errors.append(f"failed:{step.get('step', 'unknown')}")
        if any(str(item.get("step")) == "exception" for item in steps if isinstance(item, dict)):
            errors.append("exception-during-vessel-smoke")
        return {
            "schema": 1,
            "kind": "holocore_holo_vessel_smoke",
            "status": "PASS" if not errors else "FAIL",
            "errors": errors,
            "vessel_name": "Holo Vessel // Cylindrical Crescent Runner",
            "controls": {
                "outside_entry": "E near rear ramp boards the vessel",
                "inside_pilot": "E at pilot seat enters pilot mode",
                "pilot_move": "W/S thrust, A/D yaw, Space/PageUp climb, C/PageDown descend, surface-limited hover",
                "inside_exit": "E at rear exit returns to terrain",
            },
            "collision_contract": {
                "central_room_aabb_local": [24.4, 62.0, 14.0],
                "central_room_aabb_world_scaled": [33.184, 84.32, 19.04],
                "side_blades_visual_only": True,
                "outside_hull_blocks_on_foot": True,
                "terrain_surface_tracking": True,
                "flight_altitude_surface_offset": True,
                "rectangle_platform_imported": False,
                "rounded_cylindrical_fuselage": True,
                "rounded_engine_pods": True,
            },
            "steps": steps,
            "screenshots": {
                "exterior": str(HOLOCORE_VESSEL_EXTERIOR_SCREENSHOT),
                "interior": str(HOLOCORE_VESSEL_INTERIOR_SCREENSHOT),
                "pilot": str(HOLOCORE_VESSEL_PILOT_SCREENSHOT),
            },
        }

    def _vessel_smoke_exit(self, task: Task) -> int:
        report = self._collect_vessel_smoke_report()
        try:
            HOLOCORE_LOG_DIR.mkdir(parents=True, exist_ok=True)
            HOLOCORE_VESSEL_REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        except Exception as exc:
            report.setdefault("errors", []).append(f"report-write-error:{exc.__class__.__name__}:{exc}")
        print(json.dumps(report, indent=2))
        try:
            self.dimension_audio.stop()
        except Exception:
            pass
        self.userExit()
        try:
            sys.stdout.flush(); sys.stderr.flush()
        except Exception:
            pass
        os._exit(0 if report.get("status") == "PASS" else 2)
        return Task.done


    def _ocean_space_smoke_setup(self, task: Task) -> int:
        self.ocean_space_smoke_steps = []
        try:
            from dimensions.ocean_space import ocean_space_debug_samples
            samples = ocean_space_debug_samples()
            self.ocean_space_smoke_steps.append({
                "step": "distance_field_samples",
                "ok": bool(samples[0]["band_id"] == "safe_core_sea" and samples[-1]["band_id"] == "deep_ocean_space" and samples[-1]["entity_rarity_multiplier"] > samples[0]["entity_rarity_multiplier"]),
                "samples": samples,
            })
            vessel = getattr(self, "holo_vessel", None)
            if vessel is None or getattr(vessel, "root", None) is None:
                self.ocean_space_smoke_steps.append({"step": "vessel", "ok": False, "error": "missing-vessel"})
                return Task.done
            self.holo_vessel_piloting = True
            far_x = 96000.0
            far_y = 14500.0
            altitude = float(VERTICAL_STRATA_START_ALTITUDE + VERTICAL_STRATA_LAYER_HEIGHT * 5.10)
            try:
                ground = float(self.outer_world.collision_ground_z_at(far_x, far_y))
            except Exception:
                ground = 0.0
            vessel.flight_altitude = altitude
            vessel.base_ground_z = ground
            vessel.root.setPos(far_x, far_y, ground + altitude)
            vessel.root.setH(222.0)
            self._vertical_strata_last_layer_id = "leviathan_expanse"
            self._ocean_space_last_band_id = "void_current_sea"
            self._update_vertical_strata_effects(1.0, force=True)
            ocean = getattr(self, "ocean_space_state", ocean_space_state_for_position(far_x, far_y, altitude))
            strata = getattr(self, "vertical_strata_state", vertical_stratum_state(altitude))
            vessel_pos = vessel.root.getPos(self.render)
            visual_ids = []
            for index, spec in enumerate(tuple(ASCENT_ENTITY_SPECS or ())):
                try:
                    eid = str(getattr(spec, "entity_id", "ascent_entity"))
                    seed_func = getattr(spec, "seed_func")
                    seed = seed_func((91 + index * 19, 407 + index * 37), int(getattr(spec, "seed_salt", 0xA5CE)) ^ 0x0CEA5)
                    visual_pos = Vec3(
                        float(vessel_pos.x) + 1500.0 + index * 1250.0,
                        float(vessel_pos.y) + (-760.0 + index * 960.0),
                        float(vessel_pos.z) + 220.0 + index * 420.0,
                    )
                    visual_scale = max(1.0, float(getattr(spec, "scale_min", 1.0)) * max(1.0, float(getattr(strata, "creature_scale_multiplier", 1.0))) * max(1.0, float(getattr(ocean, "entity_scale_multiplier", 1.0))) * 0.82)
                    mob = getattr(spec, "mob_class")(seed=seed).build(self.ascent_entity_root, visual_pos, scale=visual_scale, heading=215.0 - index * 38.0)
                    mob.set_visibility_alpha(0.72)
                    self.ascent_entity_mobs[eid] = mob
                    visual_ids.append(eid)
                except Exception as exc:
                    print(f"holocore_ocean_space_visual_spawn_silent entity={getattr(spec, 'entity_id', 'unknown')} err={exc.__class__.__name__}:{exc}")
            self.holocore_threat_level = 0.45
            self.holocore_threat_entity = visual_ids[0] if visual_ids else "holo_storm_serpent"
            self.holocore_threat_distance = 2420.0
            self._update_holocore_threat_warning(0.25)
            self._update_ocean_space_ambient(ocean, task.time + 144.0)
            self._update_leviathan_expanse_ambient(strata, task.time + 144.0)
            screenshot_ok = self._capture_holocore_smoke_screenshot(
                HOLOCORE_OCEAN_SPACE_SCREENSHOT,
                Point3(float(vessel_pos.x) + 880.0, float(vessel_pos.y) - 2100.0, float(vessel_pos.z) + 520.0),
                Point3(float(vessel_pos.x) + 1560.0, float(vessel_pos.y) + 120.0, float(vessel_pos.z) + 220.0),
                fov=66.0,
            )
            self.ocean_space_smoke_steps.append({
                "step": "far_ocean_space_visual_proof",
                "ok": bool(screenshot_ok and str(ocean.band_id) == "deep_ocean_space" and float(ocean.distance) > 90000.0),
                "screenshot_ok": bool(screenshot_ok),
                "distance": round(float(ocean.distance), 3),
                "band_id": str(ocean.band_id),
                "band_name": str(ocean.band_name),
                "layer_id": str(strata.layer_id),
                "layer_name": str(strata.layer_name),
                "vessel_position": [round(float(vessel_pos.x), 3), round(float(vessel_pos.y), 3), round(float(vessel_pos.z), 3)],
                "visual_entity_ids": visual_ids,
                "ocean_ambient_nodes": len(list(getattr(self, "ocean_space_ambient_nodes", []) or [])),
                "leviathan_ambient_nodes": len(list(getattr(self, "leviathan_ambient_nodes", []) or [])),
                "warning_text": str(getattr(self, "_holocore_threat_warning_text", "") or ""),
                "notice_text": str(getattr(self, "_holocore_layer_notice_text", "") or ""),
                "discovered_ocean_bands": sorted(str(x) for x in set(getattr(self, "_ocean_space_discovered_bands", set()) or set())),
            })
        except Exception as exc:
            self.ocean_space_smoke_steps.append({"step": "exception", "ok": False, "error": f"{exc.__class__.__name__}:{exc}"})
        return Task.done

    def _collect_ocean_space_smoke_report(self) -> dict:
        steps = list(getattr(self, "ocean_space_smoke_steps", []) or [])
        errors: list[str] = []
        if not steps:
            errors.append("no-ocean-space-smoke-steps-recorded")
        for step in steps:
            if isinstance(step, dict) and not bool(step.get("ok", False)):
                errors.append(f"step-failed:{step.get('step', 'unknown')}")
        return {
            "schema": 1,
            "kind": "holocore_ocean_space_smoke",
            "status": "PASS" if not errors else "FAIL",
            "errors": errors,
            "screenshot_path": str(HOLOCORE_OCEAN_SPACE_SCREENSHOT),
            "steps": steps,
        }

    def _ocean_space_smoke_exit(self, task: Task) -> int:
        report = self._collect_ocean_space_smoke_report()
        try:
            HOLOCORE_LOG_DIR.mkdir(parents=True, exist_ok=True)
            HOLOCORE_OCEAN_SPACE_REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        except Exception as exc:
            report.setdefault("errors", []).append(f"report-write-error:{exc.__class__.__name__}:{exc}")
        print(json.dumps(report, indent=2))
        try:
            self.dimension_audio.stop()
        except Exception:
            pass
        self.userExit()
        try:
            sys.stdout.flush(); sys.stderr.flush()
        except Exception:
            pass
        os._exit(0 if report.get("status") == "PASS" else 2)
        return Task.done

    def _vertical_strata_smoke_setup(self, task: Task) -> int:
        self.vertical_strata_smoke_steps = []
        try:
            vessel = getattr(self, "holo_vessel", None)
            if vessel is None or getattr(vessel, "root", None) is None:
                self.vertical_strata_smoke_steps.append({"step": "vessel", "ok": False, "error": "missing-vessel"})
                return Task.done
            samples = []
            layer_h = float(VERTICAL_STRATA_LAYER_HEIGHT)
            start_h = float(VERTICAL_STRATA_START_ALTITUDE)
            for altitude in (
                0.0,
                max(0.0, start_h - 1.0),
                start_h,
                start_h + layer_h * 0.50,
                start_h + layer_h - 20.0,
                start_h + layer_h + 5.0,
                start_h + layer_h * 2.50,
                start_h + layer_h * 5.10,
            ):
                vessel.flight_altitude = float(altitude)
                vessel.update_ground_lock(self._holo_vessel_ground_z)
                self._update_vertical_strata_effects(1.0, force=True)
                state = getattr(self, "vertical_strata_state", vertical_stratum_state(float(altitude)))
                samples.append({
                    "altitude": round(float(altitude), 3),
                    "layer_id": str(state.layer_id),
                    "next_layer_id": str(state.next_layer_id),
                    "blend_alpha": round(float(state.blend_alpha), 4),
                    "scale_multiplier": round(float(state.creature_scale_multiplier), 4),
                    "distance_multiplier": round(float(state.creature_distance_multiplier), 4),
                    "rarity_multiplier": round(float(state.creature_rarity_multiplier), 4),
                })
            self.vertical_strata_smoke_steps.append({
                "step": "gradual_vertical_samples",
                "ok": bool(samples[0]["layer_id"] == "safe_reef_layer" and samples[1]["blend_alpha"] == 0.0 and samples[-1]["scale_multiplier"] > samples[0]["scale_multiplier"]),
                "samples": samples,
            })
            encounter_altitude = start_h + layer_h * 5.10

            # Visual proof must be captured while actually ascended.  Earlier smoke
            # shots captured after the rescue reset, which made the strata system look
            # like a ground-level effect even though the math was being sampled.
            self.holo_vessel_piloting = True
            self._vertical_strata_last_layer_id = "storm_abyss_layer"
            vessel.flight_altitude = encounter_altitude
            vessel.update_ground_lock(self._holo_vessel_ground_z)
            self._update_vertical_strata_effects(1.0, force=True)
            state = getattr(self, "vertical_strata_state", vertical_stratum_state(encounter_altitude))
            vessel_pos = vessel.root.getPos(self.render)
            visual_ids = []
            for index, spec in enumerate(tuple(ASCENT_ENTITY_SPECS or ())):
                try:
                    eid = str(getattr(spec, "entity_id", "ascent_entity"))
                    seed_func = getattr(spec, "seed_func")
                    seed = seed_func((33 + index * 11, 71 + index * 23), int(getattr(spec, "seed_salt", 0xA5CE)) ^ 0x51A7A)
                    visual_pos = Vec3(
                        float(vessel_pos.x) + 980.0 + index * 780.0,
                        float(vessel_pos.y) + (-360.0 + index * 520.0),
                        float(vessel_pos.z) + 180.0 + index * 260.0,
                    )
                    visual_scale = max(1.0, float(getattr(spec, "scale_min", 1.0)) * max(1.0, float(getattr(state, "creature_scale_multiplier", 1.0))) * 0.92)
                    mob = getattr(spec, "mob_class")(seed=seed).build(self.ascent_entity_root, visual_pos, scale=visual_scale, heading=232.0 - index * 42.0)
                    mob.set_visibility_alpha(0.78)
                    self.ascent_entity_mobs[eid] = mob
                    visual_ids.append(eid)
                except Exception as exc:
                    print(f"holocore_ascent_visual_spawn_silent entity={getattr(spec, 'entity_id', 'unknown')} err={exc.__class__.__name__}:{exc}")
            self.holocore_threat_level = 0.62
            self.holocore_threat_entity = visual_ids[0] if visual_ids else "holo_storm_serpent"
            self.holocore_threat_distance = 1380.0
            self._update_holocore_threat_warning(0.25)
            self._update_leviathan_expanse_ambient(state, task.time + 88.0)
            screenshot_ok = self._capture_holocore_smoke_screenshot(
                HOLOCORE_VERTICAL_STRATA_SCREENSHOT,
                Point3(float(vessel_pos.x) + 560.0, float(vessel_pos.y) - 1320.0, float(vessel_pos.z) + 420.0),
                Point3(float(vessel_pos.x) + 760.0, float(vessel_pos.y) + 80.0, float(vessel_pos.z) + 280.0),
                fov=64.0,
            )
            self.vertical_strata_smoke_steps.append({
                "step": "ascended_visual_proof",
                "ok": bool(screenshot_ok and encounter_altitude > 10000.0 and float(vessel_pos.z) > 10000.0),
                "screenshot_taken_before_rescue_reset": True,
                "screenshot_ok": bool(screenshot_ok),
                "altitude": round(float(encounter_altitude), 3),
                "vessel_position": [round(float(vessel_pos.x), 3), round(float(vessel_pos.y), 3), round(float(vessel_pos.z), 3)],
                "layer_id": str(state.layer_id),
                "layer_name": str(state.layer_name),
                "blend_alpha": round(float(state.blend_alpha), 4),
                "visual_entity_ids": visual_ids,
                "threat_warning_visible": bool(getattr(self, "_holocore_threat_warning_visible", False)),
                "threat_warning_text": str(getattr(self, "_holocore_threat_warning_text", "") or ""),
                "layer_notice_visible": bool(getattr(self, "_holocore_layer_notice_visible", False)),
                "layer_notice_text": str(getattr(self, "_holocore_layer_notice_text", "") or ""),
                "discovered_layers": sorted(str(x) for x in set(getattr(self, "_vertical_strata_discovered_layers", set()) or set())),
                "leviathan_ambient_nodes": len(list(getattr(self, "leviathan_ambient_nodes", []) or [])),
            })

            self._clear_ascent_entities()
            vessel.flight_altitude = encounter_altitude
            vessel.update_ground_lock(self._holo_vessel_ground_z)
            self._update_vertical_strata_effects(1.0, force=True)
            state = getattr(self, "vertical_strata_state", vertical_stratum_state(encounter_altitude))
            vessel_pos = vessel.root.getPos(self.render)
            built_ids = []
            for spec in tuple(ASCENT_ENTITY_SPECS or ()):
                key = self._ascent_entity_key_for_spec(spec, encounter_altitude, vessel_pos)
                mob = self._build_ascent_entity(spec, key, vessel_pos, state, force_near=True)
                if mob is not None:
                    eid = str(getattr(spec, "entity_id", "ascent_entity"))
                    self.ascent_entity_mobs[eid] = mob
                    built_ids.append(eid)
            self._update_ascent_entities(task.time, 0.35)
            rescue_started = bool(getattr(self, "holocore_rescue_pending", False))
            self.holocore_rescue_started_at = time.monotonic() - 0.70
            self._update_holocore_rescue()
            reset_done = bool(getattr(self, "holocore_rescue_reset_done", False))
            reset_altitude = float(getattr(vessel, "flight_altitude", -1.0))
            reset_pos = vessel.root.getPos(self.render)
            self.holocore_rescue_started_at = time.monotonic() - 2.0
            self._update_holocore_rescue()
            self.vertical_strata_smoke_steps.append({
                "step": "encounter_contact_rescue",
                "ok": bool(built_ids and rescue_started and reset_done and abs(reset_altitude) < 0.001 and abs(float(reset_pos.x)) < 0.01 and abs(float(reset_pos.y) + 212.0) < 0.01),
                "built_ids": built_ids,
                "rescue_started": rescue_started,
                "reset_done": reset_done,
                "reset_altitude": round(reset_altitude, 4),
                "reset_position": [round(float(reset_pos.x), 3), round(float(reset_pos.y), 3), round(float(reset_pos.z), 3)],
                "ship_parked": bool(not self.holo_vessel_boarded and not self.holo_vessel_piloting),
            })
        except Exception as exc:
            self.vertical_strata_smoke_steps.append({"step": "exception", "ok": False, "error": f"{exc.__class__.__name__}:{exc}"})
        return Task.done

    def _collect_vertical_strata_smoke_report(self) -> dict:
        steps = list(getattr(self, "vertical_strata_smoke_steps", []) or [])
        errors: list[str] = []
        if not steps:
            errors.append("no-vertical-strata-smoke-steps-recorded")
        for step in steps:
            if not bool(step.get("ok", False)):
                errors.append(f"step-failed:{step.get('step', 'unknown')}")
            if step.get("error"):
                errors.append(str(step.get("error")))
        state = getattr(self, "vertical_strata_state", vertical_stratum_state(self._current_vessel_altitude()))
        return {
            "schema": 1,
            "kind": "holocore_vertical_strata_smoke",
            "status": "PASS" if not errors else "FAIL",
            "transition_policy": "altitude tint/background smoothing only; no chunk rebuilds on ascent",
            "layer_notice_policy": "single temporary layer-discovery line only; no persistent HUD stack",
            "current_layer": str(state.layer_id),
            "current_layer_name": str(state.layer_name),
            "current_altitude": round(float(self._current_vessel_altitude()), 3),
            "encounter_entities": [str(getattr(spec, "entity_id", "unknown")) for spec in tuple(ASCENT_ENTITY_SPECS or ())],
            "rescue_contract": "major creature contact fades to black, resets and parks vessel at safe anchor",
            "steps": steps,
            "screenshot_path": str(HOLOCORE_VERTICAL_STRATA_SCREENSHOT),
            "errors": errors,
        }

    def _vertical_strata_smoke_exit(self, task: Task) -> int:
        report = self._collect_vertical_strata_smoke_report()
        try:
            HOLOCORE_LOG_DIR.mkdir(parents=True, exist_ok=True)
            HOLOCORE_VERTICAL_STRATA_REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        except Exception as exc:
            report.setdefault("errors", []).append(f"report-write-error:{exc.__class__.__name__}:{exc}")
        print(json.dumps(report, indent=2))
        try:
            self.dimension_audio.stop()
        except Exception:
            pass
        self.userExit()
        try:
            sys.stdout.flush(); sys.stderr.flush()
        except Exception:
            pass
        os._exit(0 if report.get("status") == "PASS" else 2)
        return Task.done


    def _find_mermaid_smoke_target(self) -> tuple[tuple[int, int], Vec3] | None:
        outer = getattr(self, "outer_world", None)
        if outer is None or not hasattr(outer, "mermaid_candidate_position"):
            return None
        # Search outward from the hub so the smoke always finds a deterministic
        # 10%-selected chunk without forcing a spawn or changing normal density.
        for radius in range(1, 10):
            for cx in range(-radius, radius + 1):
                for cy in range(-radius, radius + 1):
                    if max(abs(cx), abs(cy)) != radius:
                        continue
                    key = (cx, cy)
                    try:
                        pos = outer.mermaid_candidate_position(key)
                    except Exception:
                        pos = None
                    if pos is not None:
                        return key, pos
        return None

    def _mermaid_smoke_setup(self, task: Task) -> int:
        self.mermaid_smoke_steps = []
        try:
            target = self._find_mermaid_smoke_target()
            if target is None:
                self.mermaid_smoke_steps.append({"step": "find_spawn_chunk", "ok": False, "error": "no-selected-chunk-in-search"})
                return Task.done
            key, pos = target
            self.player.setPos(pos)
            self.outer_world.sync_around(pos, force=True, immediate=True)
            for _ in range(4):
                self.outer_world.update_mermaid_mobs(globalClock.getFrameTime(), 0.05)
                self.graphicsEngine.renderFrame()
            mobs = dict(getattr(self.outer_world, "mermaid_mobs", {}) or {})
            mob = mobs.get(key) or (next(iter(mobs.values())) if mobs else None)
            spawn_chance = float(getattr(self.outer_world, "mermaid_spawn_chance", -1.0))
            active_chunks = int(len(getattr(self.outer_world, "active_chunks", {}) or {}))
            mermaid_count = int(len(mobs))
            one_per_chunk = mermaid_count == len(set(mobs.keys()))
            self.mermaid_smoke_steps.append({
                "step": "deterministic_sparse_spawn",
                "ok": bool(mob is not None and abs(spawn_chance - 0.10) < 0.0001 and one_per_chunk and mermaid_count <= active_chunks),
                "target_chunk": list(key),
                "active_chunks": active_chunks,
                "mermaid_count": mermaid_count,
                "spawn_chance": round(spawn_chance, 4),
                "one_per_chunk": bool(one_per_chunk),
            })
            if mob is None:
                return Task.done
            root = getattr(mob, "root", None)
            names = []
            try:
                for np in root.findAllMatches("**"):
                    names.append(np.getName())
            except Exception:
                pass
            no_rectangle_debris = not any(("platform" in name.lower() or "landing_pad" in name.lower()) for name in names)
            root_pos = root.getPos(self.render)
            terrain_z = float(self.outer_world.collision_ground_z_at(float(root_pos.x), float(root_pos.y)))
            height_offset = float(getattr(mob, "surface_height_offset", 0.0))
            self.mermaid_smoke_steps.append({
                "step": "surface_locked_holo_mermaid",
                "ok": bool(no_rectangle_debris and abs(float(root_pos.z) - (terrain_z + height_offset)) < 0.002),
                "root_position": [round(float(root_pos.x), 3), round(float(root_pos.y), 3), round(float(root_pos.z), 3)],
                "terrain_z": round(float(terrain_z), 6),
                "height_offset": round(float(height_offset), 3),
                "rectangle_preview_debris_absent": bool(no_rectangle_debris),
            })
            self._capture_holocore_smoke_screenshot(
                HOLOCORE_MERMAID_WORLD_SCREENSHOT,
                Point3(float(root_pos.x) + 95.0, float(root_pos.y) - 135.0, float(root_pos.z) + 72.0),
                Point3(float(root_pos.x), float(root_pos.y), float(root_pos.z) + 5.0),
                60.0,
            )
            self._capture_holocore_smoke_screenshot(
                HOLOCORE_MERMAID_CLOSE_SCREENSHOT,
                Point3(float(root_pos.x) + 32.0, float(root_pos.y) - 47.0, float(root_pos.z) + 29.0),
                Point3(float(root_pos.x), float(root_pos.y), float(root_pos.z) + 4.0),
                47.0,
            )
        except Exception as exc:
            self.mermaid_smoke_steps.append({"step": "exception", "ok": False, "error": f"{exc.__class__.__name__}:{exc}"})
        return Task.done

    def _collect_mermaid_smoke_report(self) -> dict:
        steps = list(getattr(self, "mermaid_smoke_steps", []) or [])
        errors = [str(step.get("error")) for step in steps if step.get("error")]
        if not steps:
            errors.append("no-mermaid-smoke-steps-recorded")
        for step in steps:
            if not bool(step.get("ok", False)):
                errors.append(f"step-failed:{step.get('step', 'unknown')}")
        return {
            "kind": "holocore_mermaid_spawn_smoke",
            "status": "PASS" if not errors else "FAIL",
            "spawn_policy": "deterministic 10% chance, maximum one mermaid per streamed chunk",
            "preview_import_geometry": "generated only; no rectangle preview base imported",
            "steps": steps,
            "screenshots": {
                "world": str(HOLOCORE_MERMAID_WORLD_SCREENSHOT),
                "close": str(HOLOCORE_MERMAID_CLOSE_SCREENSHOT),
            },
            "errors": errors,
        }

    def _mermaid_smoke_exit(self, task: Task) -> int:
        report = self._collect_mermaid_smoke_report()
        try:
            HOLOCORE_LOG_DIR.mkdir(parents=True, exist_ok=True)
            HOLOCORE_MERMAID_REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        except Exception as exc:
            report.setdefault("errors", []).append(f"report-write-error:{exc.__class__.__name__}:{exc}")
        print(json.dumps(report, indent=2))
        try:
            self.dimension_audio.stop()
        except Exception:
            pass
        self.userExit()
        try:
            sys.stdout.flush(); sys.stderr.flush()
        except Exception:
            pass
        os._exit(0 if report.get("status") == "PASS" else 2)
        return Task.done

    def _find_jellyfish_smoke_target(self) -> tuple[tuple[int, int], Vec3] | None:
        outer = getattr(self, "outer_world", None)
        if outer is None or not hasattr(outer, "jellyfish_candidate_position"):
            return None
        # Search outward from the hub so the smoke always finds a deterministic
        # 20%-selected chunk without forcing a spawn or changing normal density.
        for radius in range(1, 10):
            for cx in range(-radius, radius + 1):
                for cy in range(-radius, radius + 1):
                    if max(abs(cx), abs(cy)) != radius:
                        continue
                    key = (cx, cy)
                    try:
                        pos = outer.jellyfish_candidate_position(key)
                    except Exception:
                        pos = None
                    if pos is not None:
                        return key, pos
        return None

    def _jellyfish_smoke_setup(self, task: Task) -> int:
        self.jellyfish_smoke_steps = []
        try:
            target = self._find_jellyfish_smoke_target()
            if target is None:
                self.jellyfish_smoke_steps.append({"step": "find_spawn_chunk", "ok": False, "error": "no-selected-chunk-in-search"})
                return Task.done
            key, pos = target
            self.player.setPos(pos)
            self.outer_world.sync_around(pos, force=True, immediate=True)
            for _ in range(4):
                self.outer_world.update_jellyfish_mobs(globalClock.getFrameTime(), 0.05)
                self.graphicsEngine.renderFrame()
            mobs = dict(getattr(self.outer_world, "jellyfish_mobs", {}) or {})
            mob = mobs.get(key) or (next(iter(mobs.values())) if mobs else None)
            spawn_chance = float(getattr(self.outer_world, "jellyfish_spawn_chance", -1.0))
            active_chunks = int(len(getattr(self.outer_world, "active_chunks", {}) or {}))
            jellyfish_count = int(len(mobs))
            one_per_chunk = jellyfish_count == len(set(mobs.keys()))
            variant_names = sorted({str(getattr(getattr(item, "variant", None), "name", "unknown")) for item in mobs.values()})
            self.jellyfish_smoke_steps.append({
                "step": "deterministic_variant_spawn",
                "ok": bool(mob is not None and spawn_chance >= 0.20 and one_per_chunk and jellyfish_count <= active_chunks),
                "target_chunk": list(key),
                "active_chunks": active_chunks,
                "jellyfish_count": jellyfish_count,
                "spawn_chance": round(spawn_chance, 4),
                "one_per_chunk": bool(one_per_chunk),
                "variant_names": variant_names,
            })
            if mob is None:
                return Task.done
            root = getattr(mob, "root", None)
            names = []
            try:
                for np in root.findAllMatches("**"):
                    names.append(np.getName())
            except Exception:
                pass
            no_rectangle_debris = not any(("platform" in name.lower() or "landing_pad" in name.lower() or "preview_floor" in name.lower()) for name in names)
            root_pos = root.getPos(self.render)
            terrain_z = float(self.outer_world.collision_ground_z_at(float(root_pos.x), float(root_pos.y)))
            height_offset = float(getattr(mob, "surface_height_offset", 0.0))
            self.jellyfish_smoke_steps.append({
                "step": "surface_locked_holo_jellyfish",
                "ok": bool(no_rectangle_debris and abs(float(root_pos.z) - (terrain_z + height_offset)) < 0.002),
                "root_position": [round(float(root_pos.x), 3), round(float(root_pos.y), 3), round(float(root_pos.z), 3)],
                "terrain_z": round(float(terrain_z), 6),
                "height_offset": round(float(height_offset), 3),
                "rectangle_preview_debris_absent": bool(no_rectangle_debris),
            })
            self._capture_holocore_smoke_screenshot(
                HOLOCORE_JELLYFISH_WORLD_SCREENSHOT,
                Point3(float(root_pos.x) + 85.0, float(root_pos.y) - 125.0, float(root_pos.z) + 70.0),
                Point3(float(root_pos.x), float(root_pos.y), float(root_pos.z) + 1.5),
                58.0,
            )
            self._capture_holocore_smoke_screenshot(
                HOLOCORE_JELLYFISH_CLOSE_SCREENSHOT,
                Point3(float(root_pos.x) + 25.0, float(root_pos.y) - 39.0, float(root_pos.z) + 20.0),
                Point3(float(root_pos.x), float(root_pos.y), float(root_pos.z) - 3.0),
                45.0,
            )
        except Exception as exc:
            self.jellyfish_smoke_steps.append({"step": "exception", "ok": False, "error": f"{exc.__class__.__name__}:{exc}"})
        return Task.done

    def _collect_jellyfish_smoke_report(self) -> dict:
        steps = list(getattr(self, "jellyfish_smoke_steps", []) or [])
        errors = [str(step.get("error")) for step in steps if step.get("error")]
        if not steps:
            errors.append("no-jellyfish-smoke-steps-recorded")
        for step in steps:
            if not bool(step.get("ok", False)):
                errors.append(f"step-failed:{step.get('step', 'unknown')}")
        return {
            "kind": "holocore_jellyfish_spawn_smoke",
            "status": "PASS" if not errors else "FAIL",
            "spawn_policy": "deterministic at-least-20% chance, maximum one jellyfish per streamed chunk",
            "variant_policy": "deterministic color and size variants: aqua, violet, rose, gold / tiny through large",
            "preview_import_geometry": "generated only; no rectangle preview base imported",
            "steps": steps,
            "screenshots": {
                "world": str(HOLOCORE_JELLYFISH_WORLD_SCREENSHOT),
                "close": str(HOLOCORE_JELLYFISH_CLOSE_SCREENSHOT),
            },
            "errors": errors,
        }

    def _jellyfish_smoke_exit(self, task: Task) -> int:
        report = self._collect_jellyfish_smoke_report()
        try:
            HOLOCORE_LOG_DIR.mkdir(parents=True, exist_ok=True)
            HOLOCORE_JELLYFISH_REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        except Exception as exc:
            report.setdefault("errors", []).append(f"report-write-error:{exc.__class__.__name__}:{exc}")
        print(json.dumps(report, indent=2))
        try:
            self.dimension_audio.stop()
        except Exception:
            pass
        self.userExit()
        try:
            sys.stdout.flush(); sys.stderr.flush()
        except Exception:
            pass
        os._exit(0 if report.get("status") == "PASS" else 2)
        return Task.done

    def _find_octopus_smoke_target(self) -> tuple[tuple[int, int], Vec3] | None:
        outer = getattr(self, "outer_world", None)
        if outer is None or not hasattr(outer, "octopus_candidate_position"):
            return None
        # Rare 3% mob: search farther than mermaid/jellyfish smoke without
        # forcing density or changing normal spawn policy.
        for radius in range(1, 24):
            for cx in range(-radius, radius + 1):
                for cy in range(-radius, radius + 1):
                    if max(abs(cx), abs(cy)) != radius:
                        continue
                    key = (cx, cy)
                    try:
                        pos = outer.octopus_candidate_position(key)
                    except Exception:
                        pos = None
                    if pos is not None:
                        return key, pos
        return None

    def _octopus_smoke_setup(self, task: Task) -> int:
        self.octopus_smoke_steps = []
        try:
            target = self._find_octopus_smoke_target()
            if target is None:
                self.octopus_smoke_steps.append({"step": "find_spawn_chunk", "ok": False, "error": "no-selected-rare-chunk-in-search"})
                return Task.done
            key, pos = target
            self.player.setPos(pos)
            self.outer_world.sync_around(pos, force=True, immediate=True)
            for _ in range(7):
                self.outer_world.update_mermaid_mobs(globalClock.getFrameTime(), 0.05)
                self.outer_world.update_jellyfish_mobs(globalClock.getFrameTime(), 0.05)
                self.outer_world.update_octopus_mobs(globalClock.getFrameTime(), 0.12)
                self.graphicsEngine.renderFrame()
            mobs = dict(getattr(self.outer_world, "octopus_mobs", {}) or {})
            mob = mobs.get(key) or (next(iter(mobs.values())) if mobs else None)
            spawn_chance = float(getattr(self.outer_world, "octopus_spawn_chance", -1.0))
            active_chunks = int(len(getattr(self.outer_world, "active_chunks", {}) or {}))
            octopus_count = int(len(mobs))
            one_per_chunk = octopus_count == len(set(mobs.keys()))
            self.octopus_smoke_steps.append({
                "step": "deterministic_rare_spawn",
                "ok": bool(mob is not None and 0.0 < spawn_chance <= 0.03 and one_per_chunk and octopus_count <= active_chunks),
                "target_chunk": list(key),
                "active_chunks": active_chunks,
                "octopus_count": octopus_count,
                "spawn_chance": round(spawn_chance, 4),
                "one_per_chunk": bool(one_per_chunk),
            })
            if mob is None:
                return Task.done
            root = getattr(mob, "root", None)
            names = []
            try:
                for np in root.findAllMatches("**"):
                    names.append(np.getName())
            except Exception:
                pass
            no_rectangle_debris = not any(("platform" in name.lower() or "landing_pad" in name.lower() or "preview_floor" in name.lower()) for name in names)
            root_pos = root.getPos(self.render)
            terrain_z = float(self.outer_world.collision_ground_z_at(float(root_pos.x), float(root_pos.y)))
            height_offset = float(getattr(mob, "surface_height_offset", 0.0))
            self.octopus_smoke_steps.append({
                "step": "surface_locked_rare_holo_octopus",
                "ok": bool(no_rectangle_debris and height_offset >= 3.0 and abs(float(root_pos.z) - (terrain_z + height_offset)) < 0.002),
                "root_position": [round(float(root_pos.x), 3), round(float(root_pos.y), 3), round(float(root_pos.z), 3)],
                "terrain_z": round(float(terrain_z), 6),
                "height_offset": round(float(height_offset), 3),
                "minimum_clearance": 3.0,
                "rectangle_preview_debris_absent": bool(no_rectangle_debris),
            })
            # Synthetic nearby entity anchors exercise curiosity/caution behavior
            # without forcing mermaid/jellyfish density around the rare target.
            mermaid_anchor = Vec3(float(root_pos.x) + 84.0, float(root_pos.y) - 24.0, float(root_pos.z))
            jelly_anchor = Vec3(float(root_pos.x) + 58.0, float(root_pos.y) + 20.0, float(root_pos.z))
            try:
                mob.update_behavior([mermaid_anchor], [], 0.12)
                mob.update_surface_lock(self.outer_world.collision_ground_z_at)
                mob.update_pose(globalClock.getFrameTime() + 1.0, force=True)
                curious_state = str(getattr(mob, "behavior_state", ""))
                mob.update_behavior([], [jelly_anchor], 0.12)
                mob.update_surface_lock(self.outer_world.collision_ground_z_at)
                mob.update_pose(globalClock.getFrameTime() + 2.0, force=True)
                cautious_state = str(getattr(mob, "behavior_state", ""))
            except Exception as exc:
                curious_state = "error"
                cautious_state = f"error:{exc.__class__.__name__}:{exc}"
            self.octopus_smoke_steps.append({
                "step": "intelligent_neighbor_behavior",
                "ok": bool(curious_state == "curious_mermaid" and cautious_state == "cautious_jellyfish"),
                "curious_state": curious_state,
                "cautious_state": cautious_state,
                "keeps_distance_policy": "curious approaches only to keep ring; jellyfish caution backs away",
                "color_blend_policy": "chromatophore colors are rebuilt by behavior/time phase",
            })
            self._capture_holocore_smoke_screenshot(
                HOLOCORE_OCTOPUS_WORLD_SCREENSHOT,
                Point3(float(root_pos.x) + 105.0, float(root_pos.y) - 155.0, float(root_pos.z) + 82.0),
                Point3(float(root_pos.x), float(root_pos.y), float(root_pos.z) + 4.0),
                60.0,
            )
            self._capture_holocore_smoke_screenshot(
                HOLOCORE_OCTOPUS_CLOSE_SCREENSHOT,
                Point3(float(root_pos.x) + 31.0, float(root_pos.y) - 48.0, float(root_pos.z) + 25.0),
                Point3(float(root_pos.x), float(root_pos.y), float(root_pos.z) - 1.0),
                46.0,
            )
            self._capture_holocore_smoke_screenshot(
                HOLOCORE_OCTOPUS_BEHAVIOR_SCREENSHOT,
                Point3(float(root_pos.x) + 42.0, float(root_pos.y) - 55.0, float(root_pos.z) + 27.0),
                Point3(float(root_pos.x), float(root_pos.y), float(root_pos.z) + 0.5),
                48.0,
            )
        except Exception as exc:
            self.octopus_smoke_steps.append({"step": "exception", "ok": False, "error": f"{exc.__class__.__name__}:{exc}"})
        return Task.done

    def _collect_octopus_smoke_report(self) -> dict:
        steps = list(getattr(self, "octopus_smoke_steps", []) or [])
        errors = [str(step.get("error")) for step in steps if step.get("error")]
        if not steps:
            errors.append("no-octopus-smoke-steps-recorded")
        for step in steps:
            if not bool(step.get("ok", False)):
                errors.append(f"step-failed:{step.get('step', 'unknown')}")
        return {
            "kind": "holocore_octopus_spawn_behavior_smoke",
            "status": "PASS" if not errors else "FAIL",
            "spawn_policy": "deterministic very rare 3% chance, maximum one octopus per streamed chunk",
            "height_policy": "all chunk mobs use varied hover offsets with at least 3.0 units above terrain",
            "fade_policy": "chunk fade plus distance alpha fade prevents far mob pop-in",
            "behavior_policy": "octopus watches mermaid/jellyfish anchors, stays distant, and blends colors",
            "preview_import_geometry": "generated only; no rectangle preview base imported",
            "steps": steps,
            "screenshots": {
                "world": str(HOLOCORE_OCTOPUS_WORLD_SCREENSHOT),
                "close": str(HOLOCORE_OCTOPUS_CLOSE_SCREENSHOT),
                "behavior": str(HOLOCORE_OCTOPUS_BEHAVIOR_SCREENSHOT),
            },
            "errors": errors,
        }

    def _octopus_smoke_exit(self, task: Task) -> int:
        report = self._collect_octopus_smoke_report()
        try:
            HOLOCORE_LOG_DIR.mkdir(parents=True, exist_ok=True)
            HOLOCORE_OCTOPUS_REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        except Exception as exc:
            report.setdefault("errors", []).append(f"report-write-error:{exc.__class__.__name__}:{exc}")
        print(json.dumps(report, indent=2))
        try:
            self.dimension_audio.stop()
        except Exception:
            pass
        self.userExit()
        try:
            sys.stdout.flush(); sys.stderr.flush()
        except Exception:
            pass
        os._exit(0 if report.get("status") == "PASS" else 2)
        return Task.done

    def _setup_return_prompt(self) -> None:
        self.return_prompt = OnscreenText(
            text="",
            pos=(0.0, -0.88),
            scale=0.045,
            fg=(0.82, 1.0, 1.0, 0.94),
            shadow=(0.0, 0.0, 0.0, 0.75),
            mayChange=True,
        )
        self.return_prompt.hide()

    def _clean_gate_label(self, value: str, fallback: str = "DIMENSION") -> str:
        text = re.sub(r"[\\/]+", " ", str(value or fallback))
        text = re.sub(r"[_\-]+", " ", text)
        text = re.sub(r"\s+", " ", text).strip() or fallback
        return text[:28].upper()

    def _gate_lookup_key(self, value: object) -> str:
        return re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")

    def _project_entry(self, raw: object) -> Path | None:
        text = str(raw or "").replace("\\", "/").strip("/")
        if not text:
            return None
        path = Path(text)
        if path.is_absolute():
            return path
        return ROOT.parent / text

    def _infer_runtime_installer(self, runtime: Path | None) -> str:
        if runtime is None or not runtime.exists():
            return ""
        try:
            text = runtime.read_text(encoding="utf-8", errors="ignore")[:36000]
            match = re.search(r"def\s+(install_[A-Za-z0-9_]+)\s*\(", text)
            return match.group(1) if match else ""
        except Exception:
            return ""

    def _record_from_dimension_folder(self, folder: Path) -> dict | None:
        try:
            folder = Path(folder)
            if not folder.exists() or not folder.is_dir() or folder.name.startswith("."):
                return None
            mode_id = self._gate_lookup_key(folder.name)
            if not mode_id or mode_id == "holocore":
                return None
            manifest_path = folder / "holoverse_mode_manifest.json"
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
            except Exception:
                manifest = {}
            if not isinstance(manifest, dict):
                manifest = {}
            manifest_entry_name = str(manifest.get("entry") or "main.py").replace("\\", "/").strip("/") or "main.py"
            entry = folder / manifest_entry_name
            if not entry.exists():
                entry = folder / "main.py"
            runtime = folder / "runtime.py"
            runtime_installer = str(manifest.get("runtime_installer") or self._infer_runtime_installer(runtime)).strip()
            source_kind = str(manifest.get("source_kind") or "auto").strip()
            launch_type = str(manifest.get("launch_type") or ("in_world_region" if runtime_installer else ("embedded_external" if entry.exists() else "placeholder_mode"))).strip()
            return {
                "id": mode_id,
                "title": str(manifest.get("title") or folder.name).upper(),
                "name": folder.name,
                "folder": f"Dimensions/{folder.name}",
                "entry": f"Dimensions/{folder.name}/{entry.name}" if entry.exists() else "",
                "runtime": f"Dimensions/{folder.name}/runtime.py" if runtime.exists() else "",
                "runtime_installer": runtime_installer,
                "launch_type": launch_type,
                "source_kind": source_kind,
                "enabled": True,
                "available": bool(entry.exists() or runtime_installer),
                "placeholder_mode": launch_type == "placeholder_mode",
                "status": "auto_configured" if (entry.exists() or runtime_installer) else "needs_config",
            }
        except Exception as exc:
            print(f"holocore_gate_folder_scan_silent err={exc.__class__.__name__}:{exc}")
            return None

    def _load_dimension_gate_modes(self) -> list[dict]:
        modes: list[dict] = []
        known: set[str] = set()
        records: list[dict] = []
        index_path = ROOT.parent / "Dimensions" / "dimension_index.json"
        try:
            if index_path.exists():
                payload = json.loads(index_path.read_text(encoding="utf-8"))
                indexed = payload.get("dimensions") if isinstance(payload, dict) else {}
                if isinstance(indexed, dict):
                    for dim_id, record in indexed.items():
                        if not isinstance(record, dict):
                            continue
                        key = self._gate_lookup_key(record.get("id") or dim_id or record.get("name") or record.get("folder"))
                        if not key or key == "holocore" or bool(record.get("enabled", True)) is False:
                            continue
                        known.add(key)
                        records.append(dict(record))
        except Exception as exc:
            print(f"holocore_gate_index_silent err={exc.__class__.__name__}:{exc}")
        try:
            dims_root = ROOT.parent / "Dimensions"
            if dims_root.exists() and dims_root.is_dir():
                for folder in sorted([child for child in dims_root.iterdir() if child.is_dir()], key=lambda child: child.name.lower()):
                    key = self._gate_lookup_key(folder.name)
                    if not key or key in known or key == "holocore":
                        continue
                    record = self._record_from_dimension_folder(folder)
                    if record:
                        known.add(key)
                        records.append(record)
        except Exception as exc:
            print(f"holocore_gate_scan_silent err={exc.__class__.__name__}:{exc}")
        for record in sorted(records, key=lambda item: str(item.get("title") or item.get("name") or item.get("id") or "").lower()):
            entry_raw = str(record.get("entry") or "").replace("\\", "/").strip("/")
            folder_raw = str(record.get("folder") or "").replace("\\", "/").strip("/")
            folder = self._project_entry(folder_raw) if folder_raw else None
            manifest = {}
            try:
                manifest_path = folder / "holoverse_mode_manifest.json" if folder is not None else None
                if manifest_path is not None and manifest_path.exists():
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                    if not isinstance(manifest, dict):
                        manifest = {}
            except Exception:
                manifest = {}
            manifest_entry_raw = str(manifest.get("entry") or "").replace("\\", "/").strip("/")
            manifest_entry = (folder / manifest_entry_raw) if folder is not None and manifest_entry_raw else None
            if manifest_entry is not None and manifest_entry.exists() and manifest_entry.name.lower() != "main.py":
                entry = manifest_entry
            else:
                entry = self._project_entry(entry_raw) if entry_raw else None
            if entry is None or not entry.exists():
                entry = folder / "main.py" if folder is not None else None
            runtime = self._project_entry(record.get("runtime")) if record.get("runtime") else None
            runtime_installer = str(record.get("runtime_installer") or self._infer_runtime_installer(runtime)).strip()
            title = self._clean_gate_label(record.get("title") or record.get("name") or record.get("id") or "DIMENSION")
            can_signal_host = bool(self.return_signal_path and runtime_installer)
            available = bool(((entry is not None and entry.exists()) or can_signal_host) and not record.get("placeholder_mode", False))
            route = str(record.get("launch_type") or record.get("route") or ("in_world_region" if runtime_installer else "configured"))
            modes.append({
                "id": str(record.get("id") or self._gate_lookup_key(title)),
                "title": title,
                "entry": entry,
                "runtime_installer": runtime_installer,
                "route": route,
                "available": available,
                "record": dict(record),
                "auto": str(record.get("status") or "").lower() == "auto_configured",
            })
        return modes

    def _setup_dimension_gate_panel(self) -> None:
        self.dimension_gate_modes = self._load_dimension_gate_modes()
        self.dimension_gate_buttons = []
        try:
            self.dimension_gate_root = self.aspect2d.attachNewNode("holocore-dimension-gate-panel")
            self.dimension_gate_root.setBin("fixed", 72)
            panel_height = min(0.80, 0.15 + 0.064 * max(1, min(9, len(self.dimension_gate_modes))))
            DirectFrame(parent=self.dimension_gate_root, frameColor=(0.0, 0.018, 0.035, 0.50), frameSize=(-0.43, 0.43, -panel_height, 0.07), pos=(1.305, 0, 0.42))
            DirectLabel(parent=self.dimension_gate_root, text="DIMENSION GATES", text_align=TextNode.ACenter, text_scale=0.032, text_fg=(0.72, 1.0, 1.0, 0.96), frameColor=(0, 0, 0, 0), pos=(1.305, 0, 0.465))
            self.dimension_gate_status = DirectLabel(parent=self.dimension_gate_root, text="1-9 GATES // AUTO-SCAN ON", text_align=TextNode.ACenter, text_scale=0.020, text_fg=(0.62, 0.92, 1.0, 0.78), frameColor=(0, 0, 0, 0), pos=(1.305, 0, 0.405), textMayChange=True)
            y = 0.337
            for idx, mode in enumerate(self.dimension_gate_modes[:9], start=1):
                available = bool(mode.get("available"))
                label = str(mode.get("title") or f"DIMENSION {idx}")
                badge = " // AUTO" if bool(mode.get("auto")) and available else ""
                text = f"{idx}. {label}{badge}" if available else f"{idx}. {label} // CONFIG"
                btn = DirectButton(
                    parent=self.dimension_gate_root,
                    text=text[:36],
                    text_align=TextNode.ALeft,
                    text_scale=0.023,
                    text_fg=(0.80, 1.0, 1.0, 0.94) if available else (0.92, 0.72, 0.44, 0.86),
                    text_pos=(-0.355, -0.008),
                    frameColor=(0.02, 0.12, 0.17, 0.58) if available else (0.16, 0.10, 0.04, 0.46),
                    frameSize=(-0.38, 0.38, -0.023, 0.029),
                    relief=1,
                    pos=(1.305, 0, y),
                    command=self._request_dimension_gate_by_index,
                    extraArgs=[idx - 1],
                )
                self.dimension_gate_buttons.append(btn)
                y -= 0.058
            if not self.dimension_gate_modes:
                self.dimension_gate_status.setText("NO DIMENSION ROUTES FOUND")
            elif len(self.dimension_gate_modes) > 9:
                self.dimension_gate_status.setText("FIRST 9 GATES SHOWN")
        except Exception as exc:
            self.dimension_gate_root = None
            print(f"holocore_gate_panel_silent err={exc.__class__.__name__}:{exc}")

    def _dimension_gate_panel_visible(self) -> bool:
        root = getattr(self, "dimension_gate_root", None)
        if root is None:
            return False
        try:
            if root.isEmpty():
                return False
        except Exception:
            return False
        try:
            return not root.isHidden()
        except Exception:
            return True

    def _reset_movement_keys(self) -> None:
        key_map = getattr(self, "key_map", None)
        if isinstance(key_map, dict):
            for key in list(key_map.keys()):
                key_map[key] = False

    def _set_dimension_gate_cursor_locked(self, locked: bool) -> None:
        try:
            props = WindowProperties()
            props.setCursorHidden(bool(locked))
            if self.win is not None and hasattr(self.win, "requestProperties"):
                self.win.requestProperties(props)
        except Exception:
            pass
        if locked:
            try:
                self._center_mouse_pointer()
            except Exception:
                pass

    def _open_dimension_gate_panel(self) -> bool:
        if bool(getattr(self, "return_transition_pending", False)):
            return False
        root = getattr(self, "dimension_gate_root", None)
        try:
            needs_build = root is None or root.isEmpty()
        except Exception:
            needs_build = True
        if needs_build:
            self._setup_dimension_gate_panel()
            root = getattr(self, "dimension_gate_root", None)
        if root is None:
            return False
        try:
            root.show()
        except Exception:
            pass
        self._reset_movement_keys()
        self._set_dimension_gate_cursor_locked(False)
        try:
            status = getattr(self, "dimension_gate_status", None)
            if status is not None:
                if self.dimension_gate_modes:
                    status.setText("ESC CLOSES // TAB CYCLES // 1-9 OPEN")
                else:
                    status.setText("NO DIMENSION ROUTES FOUND")
        except Exception:
            pass
        return True

    def _close_dimension_gate_panel(self) -> bool:
        if not self._dimension_gate_panel_visible():
            return False
        root = getattr(self, "dimension_gate_root", None)
        try:
            root.hide()
        except Exception:
            pass
        self._reset_movement_keys()
        self._set_dimension_gate_cursor_locked(True)
        try:
            status = getattr(self, "dimension_gate_status", None)
            if status is not None:
                status.setText("DIMENSION GATES CLOSED")
        except Exception:
            pass
        return True

    def _toggle_dimension_gate_panel(self) -> None:
        if self._dimension_gate_panel_visible():
            self._close_dimension_gate_panel()
        else:
            self._open_dimension_gate_panel()

    def _handle_escape(self) -> None:
        if bool(getattr(self, "holo_vessel_piloting", False)):
            self._leave_holo_vessel_pilot_seat()
            return
        if self._close_dimension_gate_panel():
            return
        self._request_matrixcore_return()

    def _handle_dimension_gate_number(self, index: int) -> None:
        if not self._dimension_gate_panel_visible():
            return
        self._request_dimension_gate_by_index(index)

    def _request_dimension_gate_by_index(self, index: int) -> None:
        try:
            mode = self.dimension_gate_modes[int(index)]
        except Exception:
            return
        self._request_dimension_gate(mode)

    def _request_dimension_gate(self, mode: dict) -> None:
        if self.dimension_gate_pending is not None:
            return
        title = str(mode.get("title") or "DIMENSION")
        if not bool(mode.get("available")):
            if self.dimension_gate_status is not None:
                self.dimension_gate_status.setText(f"{title} // NEEDS CONFIG"[:38])
            return
        self.dimension_gate_pending = dict(mode)
        self.dimension_gate_pending_started_at = time.monotonic()
        for btn in list(self.dimension_gate_buttons):
            try:
                btn["state"] = "disabled"
            except Exception:
                pass
        if self.dimension_gate_status is not None:
            self.dimension_gate_status.setText(f"OPENING {title}"[:38])
        self._show_bridge_transition("HOLOCORE GATE", f"OPENING {title}", target=1.0)

    def _write_dimension_launch_signal(self, mode: dict) -> None:
        if not self.return_signal_path:
            return
        try:
            target = Path(self.return_signal_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "request": "launch_dimension",
                "reason": "holocore_gate",
                "mode": str(mode.get("title") or "DIMENSION"),
                "dimension_id": str(mode.get("id") or ""),
                "route": str(mode.get("route") or ""),
                "gate": "holocore_button",
                "pid": os.getpid(),
            }
            target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        except Exception as exc:
            print(f"holocore_gate_signal_failed err={exc.__class__.__name__}:{exc}")

    def _dispatch_dimension_gate(self) -> None:
        mode = self.dimension_gate_pending
        if mode is None:
            return
        if time.monotonic() - float(self.dimension_gate_pending_started_at or 0.0) < 0.42:
            return
        self.dimension_gate_pending = None
        entry = mode.get("entry")
        title = str(mode.get("title") or "DIMENSION")
        self._write_dimension_launch_signal(mode)
        if entry is not None and Path(entry).exists():
            try:
                env = dict(os.environ)
                env["HOLOVERSE_GATEWAY_SOURCE"] = "HoloCore"
                env["HOLOVERSE_GATEWAY_BUTTON"] = title
                env["HOLOVERSE_TRANSITION_ACTIVE"] = "1"
                env["HOLOVERSE_TRANSITION_SOURCE"] = "holocore_button"
                subprocess.Popen([sys.executable, str(entry)], cwd=str(Path(entry).parent), env=env)
            except Exception as exc:
                if self.dimension_gate_status is not None:
                    self.dimension_gate_status.setText(f"{title} // NEEDS CONFIG"[:38])
                print(f"holocore_gate_launch_failed err={exc.__class__.__name__}:{exc}")
                return
        try:
            self.dimension_audio.stop()
        except Exception:
            pass
        self.userExit()

    def _setup_bridge_transition_overlay(self) -> None:
        self.bridge_transition_root = self.aspect2d.attachNewNode("holocore-transition-root")
        self.bridge_transition_root.setBin("fixed", 96)
        self.bridge_transition_root.setDepthTest(False)
        self.bridge_transition_root.setDepthWrite(False)
        self.bridge_transition_panel = DirectFrame(parent=self.bridge_transition_root, frameColor=(0.0, 0.006, 0.012, 0.0), frameSize=(-2.2, 2.2, -1.25, 1.25), pos=(0, 0, 0))
        self.bridge_transition_label = DirectLabel(parent=self.bridge_transition_root, text="HOLOCORE LINK ONLINE", text_align=TextNode.ACenter, text_scale=0.058, text_fg=(0.74, 1.0, 1.0, 0.0), frameColor=(0, 0, 0, 0), pos=(0, 0, 0.035), textMayChange=True)
        self.bridge_transition_subtitle = DirectLabel(parent=self.bridge_transition_root, text="PYRAMID SUB-WORLD SYNCHRONIZED", text_align=TextNode.ACenter, text_scale=0.026, text_fg=(0.46, 0.94, 1.0, 0.0), frameColor=(0, 0, 0, 0), pos=(0, 0, -0.060), textMayChange=True)
        self.bridge_transition_alpha = 1.0 if self.embedded_mode else 0.0
        self.bridge_transition_target = 0.0
        self._set_bridge_transition_alpha(self.bridge_transition_alpha)

    def _set_bridge_transition_alpha(self, alpha: float) -> None:
        alpha = max(0.0, min(1.0, float(alpha or 0.0)))
        self.bridge_transition_alpha = alpha
        root = getattr(self, "bridge_transition_root", None)
        if root is None:
            return
        visible = not (alpha <= 0.002 and float(getattr(self, "bridge_transition_target", 0.0) or 0.0) <= 0.0)
        if self._bridge_transition_visible == visible and self._bridge_transition_rendered_alpha is not None and abs(self._bridge_transition_rendered_alpha - alpha) < 0.004:
            return
        if alpha <= 0.002 and float(getattr(self, "bridge_transition_target", 0.0) or 0.0) <= 0.0:
            if self._bridge_transition_visible is not False:
                root.hide()
                self._bridge_transition_visible = False
            self._bridge_transition_rendered_alpha = alpha
            return
        if self._bridge_transition_visible is not True:
            root.show()
            self._bridge_transition_visible = True
        try:
            self.bridge_transition_panel["frameColor"] = (0.0, 0.006, 0.012, 0.86 * alpha)
            self.bridge_transition_label["text_fg"] = (0.74, 1.0, 1.0, 0.95 * alpha)
            self.bridge_transition_subtitle["text_fg"] = (0.46, 0.94, 1.0, 0.82 * alpha)
            self._bridge_transition_rendered_alpha = alpha
        except Exception:
            pass

    def _show_bridge_transition(self, title: str, subtitle: str, target: float = 1.0) -> None:
        try:
            self.bridge_transition_label["text"] = str(title or "HOLOCORE")
            self.bridge_transition_subtitle["text"] = str(subtitle or "SAME-SCREEN GATEWAY")
        except Exception:
            pass
        self.bridge_transition_target = max(0.0, min(1.0, float(target or 0.0)))
        if float(getattr(self, "bridge_transition_alpha", 0.0) or 0.0) <= 0.002:
            self._set_bridge_transition_alpha(0.025)

    def _update_bridge_transition_overlay(self, dt: float) -> None:
        alpha = float(getattr(self, "bridge_transition_alpha", 0.0) or 0.0)
        target = float(getattr(self, "bridge_transition_target", 0.0) or 0.0)
        speed = 5.2 if target > alpha else 2.7
        blend = min(1.0, max(0.0, float(dt or 0.0)) * speed)
        if abs(target - alpha) <= 0.004:
            alpha = target
        else:
            alpha += (target - alpha) * blend
        self._set_bridge_transition_alpha(alpha)

    def _active_dimension_info(self) -> tuple[int, str]:
        try:
            manager = getattr(self.outer_world, "dimension_manager", None)
            active = getattr(manager, "active", None)
            dim_id = int(getattr(active, "dimension_id", 1) or 1)
            dim_name = str(getattr(active, "name", "HoloCore Dimension") or "HoloCore Dimension")
            return dim_id, dim_name
        except Exception:
            return 1, "HoloCore Dimension"

    def _sync_dimension_music(self, force: bool = False) -> None:
        dim_id, dim_name = self._active_dimension_info()
        if not force and dim_id == getattr(self, "_last_dimension_audio_id", None):
            return
        self._last_dimension_audio_id = dim_id
        try:
            self.dimension_audio.play_dimension(dim_id, dim_name, force=True)
        except Exception as exc:
            print(f"holocore_dimension_audio_sync_failed err={exc.__class__.__name__}:{exc}")

    def _near_pyramid_return_gate(self) -> bool:
        try:
            pos = self.player.getPos(self.render)
            return (float(pos.x) * float(pos.x) + float(pos.y) * float(pos.y)) <= (86.0 * 86.0)
        except Exception:
            return True

    def _update_return_prompt(self) -> None:
        prompt = getattr(self, "return_prompt", None)
        if prompt is None:
            return
        if not bool(getattr(self, "embedded_mode", False)):
            if self._return_prompt_visible is not False:
                prompt.hide()
                self._return_prompt_visible = False
            return
        if bool(getattr(self, "return_transition_pending", False)):
            text = "RETURNING TO MATRIXCORE"
        elif self._near_pyramid_return_gate():
            text = "PYRAMID CORE // 0 MATRIXCORE // E LOCAL INTERACT"
        else:
            text = "PYRAMID CORE // WALK BACK FOR 0 MATRIXCORE"
        if self._return_prompt_text != text:
            prompt.setText(text)
            self._return_prompt_text = text
        if self._return_prompt_visible is not True:
            prompt.show()
            self._return_prompt_visible = True

    def _write_gate_menu_signal(self) -> None:
        path = str(getattr(self, "return_signal_path", "") or "").strip()
        if not path:
            return
        try:
            target = Path(path)
            target.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "request": "open_gate_menu",
                "reason": "holocore_pyramid_gates",
                "mode": "HoloCore",
                "gate": "pyramid",
                "pid": os.getpid(),
            }
            target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        except Exception as exc:
            print(f"holocore_gate_menu_signal_failed err={exc}")

    def _request_pyramid_gate_menu(self) -> None:
        if not bool(getattr(self, "embedded_mode", False)):
            return
        if bool(getattr(self, "return_transition_pending", False)):
            return
        if not self._near_pyramid_return_gate():
            self._update_return_prompt()
            return
        self.return_transition_pending = True
        self.return_transition_started_at = time.monotonic()
        self.return_transition_signal_written = False
        self._pending_return_request = "open_gate_menu"
        self._show_bridge_transition("HOLOCORE PYRAMID", "OPENING SHARED DIMENSION GATES", target=1.0)
        self._update_return_prompt()

    def _write_return_signal(self, reason: str = "pyramid_return") -> None:
        path = str(getattr(self, "return_signal_path", "") or "").strip()
        if not path:
            return
        try:
            target = Path(path)
            target.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "request": "return_to_core",
                "reason": str(reason or "pyramid_return"),
                "mode": "HoloCore",
                "gate": "pyramid",
                "pid": os.getpid(),
            }
            target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        except Exception as exc:
            print(f"holocore_return_signal_failed err={exc}")

    def _request_matrixcore_return(self) -> None:
        if not bool(getattr(self, "embedded_mode", False)):
            try:
                self.dimension_audio.stop()
            except Exception:
                pass
            self.userExit()
            return
        if bool(getattr(self, "return_transition_pending", False)):
            return
        if not self._near_pyramid_return_gate():
            self._update_return_prompt()
            return
        self.return_transition_pending = True
        self.return_transition_started_at = time.monotonic()
        self.return_transition_signal_written = False
        self._pending_return_request = "return_to_core"
        self._show_bridge_transition("HOLOCORE -> MATRIXCORE", "PYRAMID RETURN GATE // RESTORING OBSERVATORY", target=1.0)
        self._update_return_prompt()

    def _setup_first_person_controller(self) -> None:
        self.player = self.render.attachNewNode("first_person_player")
        self.camera.reparentTo(self.player)
        self.camera.setPos(0, 0, self.eye_height)
        self.camera.setHpr(0, 0, 0)
        self.camLens.setFov(72)
        self.camLens.setNearFar(0.18, 2400)
        self._bind_first_person_keys()
        self._reset_player()
        self._lock_mouse()

    def _bind_first_person_keys(self) -> None:
        for key in ("w", "a", "s", "d", "arrow_up", "arrow_left", "arrow_down", "arrow_right", "space", "c", "page_up", "page_down"):
            self.accept(key, self._set_key, [key, True])
            self.accept(f"{key}-up", self._set_key, [key, False])
        for key in ("shift", "lshift", "rshift"):
            self.accept(key, self._set_key, ["shift", True])
            self.accept(f"{key}-up", self._set_key, ["shift", False])
        self.accept("r", self._reset_player)

    def _set_key(self, key: str, value: bool) -> None:
        self.key_map[key] = value

    def _reset_player(self) -> None:
        self.player.setPos(self.hub.get_spawn_position())
        self._look_player_at(self.hub.get_spawn_target())

    def _lock_mouse(self) -> None:
        props = WindowProperties()
        props.setCursorHidden(True)
        if self.win is not None and hasattr(self.win, "requestProperties"):
            self.win.requestProperties(props)
        self._center_mouse_pointer()

    def _center_mouse_pointer(self) -> None:
        if not self.win or not hasattr(self.win, "movePointer") or not hasattr(self.win, "getProperties"):
            return
        props = self.win.getProperties()
        cx = props.getXSize() // 2
        cy = props.getYSize() // 2
        if cx > 0 and cy > 0:
            self.win.movePointer(0, cx, cy)

    def _look_player_at(self, target: Vec3) -> None:
        world_pos = self.player.getPos(self.render) + Vec3(0, 0, self.eye_height)
        self.camera.reparentTo(self.render)
        self.camera.setPos(world_pos)
        self.camera.lookAt(target)
        h, p, _ = self.camera.getHpr(self.render)
        self.heading = h
        self.pitch = max(-78.0, min(78.0, p))
        self.player.setH(self.heading)
        self._last_applied_heading = self.heading
        self.camera.reparentTo(self.player)
        self.camera.setPos(0, 0, self.eye_height)
        self.camera.setHpr(0, self.pitch, 0)
        self._last_applied_pitch = self.pitch

    def _update_worlds(self, task: Task) -> int:
        dt = min(globalClock.getDt(), 0.05)
        self.hub.update(task)
        self.outer_world.update(task)
        try:
            if getattr(self, "holo_vessel", None) is not None and not bool(getattr(self, "holo_vessel_piloting", False)):
                self.holo_vessel.update_ground_lock(self._holo_vessel_ground_z)
        except Exception as exc:
            print(f"holocore_vessel_ground_lock_silent err={exc.__class__.__name__}:{exc}")
        self._update_vertical_strata_effects(dt)
        try:
            self._update_ascent_entities(task.time, dt)
        except Exception as exc:
            print(f"holocore_ascent_entities_silent err={exc.__class__.__name__}:{exc}")
        self._update_holocore_rescue()
        self._update_bridge_transition_overlay(dt)
        self._sync_dimension_music(force=False)
        try:
            self._dispatch_dimension_gate()
        except Exception as exc:
            print(f"holocore_gate_dispatch_silent err={exc.__class__.__name__}:{exc}")
        if bool(getattr(self, "return_transition_pending", False)):
            elapsed = time.monotonic() - float(getattr(self, "return_transition_started_at", time.monotonic()) or time.monotonic())
            if elapsed >= 0.42 and not bool(getattr(self, "return_transition_signal_written", False)):
                if str(getattr(self, "_pending_return_request", "return_to_core") or "return_to_core") == "open_gate_menu":
                    self._write_gate_menu_signal()
                else:
                    self._write_return_signal("holocore_pyramid_return")
                self.return_transition_signal_written = True
            if elapsed >= 0.48:
                try:
                    self.dimension_audio.stop()
                except Exception:
                    pass
                self.userExit()
                return Task.done
        self._update_return_prompt()
        self._update_holo_vessel_prompt()
        self._update_holocore_threat_warning(dt)
        self._update_holocore_layer_notice()
        return Task.cont

    def _update_first_person(self, task: Task) -> int:
        dt = min(globalClock.getDt(), 0.05)
        if bool(getattr(self, "return_transition_pending", False)) or bool(getattr(self, "holocore_rescue_pending", False)):
            return Task.cont
        if self._dimension_gate_panel_visible():
            return Task.cont
        if bool(getattr(self, "holo_vessel_piloting", False)):
            self._update_holo_vessel_piloting(dt)
            return Task.cont

        if self.win and hasattr(self.win, "getProperties") and hasattr(self.win, "getPointer"):
            props = self.win.getProperties()
            cx = props.getXSize() // 2
            cy = props.getYSize() // 2
            pointer = self.win.getPointer(0)
            dx = pointer.getX() - cx
            dy = pointer.getY() - cy
            if abs(dx) > 0 or abs(dy) > 0:
                self.heading -= dx * self.mouse_sensitivity
                self.pitch -= dy * self.mouse_sensitivity
                self.pitch = max(-78.0, min(78.0, self.pitch))
                self._center_mouse_pointer()

        if self._last_applied_heading is None or abs(float(self._last_applied_heading) - self.heading) > 0.0001:
            self.player.setH(self.heading)
            self._last_applied_heading = self.heading
        if self._last_applied_pitch is None or abs(float(self._last_applied_pitch) - self.pitch) > 0.0001:
            self.camera.setHpr(0, self.pitch, 0)
            self._last_applied_pitch = self.pitch

        moving_forward = self.key_map["w"] or self.key_map["arrow_up"]
        moving_back = self.key_map["s"] or self.key_map["arrow_down"]
        moving_right = self.key_map["d"] or self.key_map["arrow_right"]
        moving_left = self.key_map["a"] or self.key_map["arrow_left"]
        if not (moving_forward or moving_back or moving_right or moving_left):
            return Task.cont

        move = Vec3(0, 0, 0)
        quat = self.player.getQuat(self.render)
        forward = quat.getForward()
        right = quat.getRight()
        forward.setZ(0)
        right.setZ(0)
        if forward.lengthSquared() > 0:
            forward.normalize()
        if right.lengthSquared() > 0:
            right.normalize()

        if moving_forward:
            move += forward
        if moving_back:
            move -= forward
        if moving_right:
            move += right
        if moving_left:
            move -= right

        if move.lengthSquared() > 0:
            move.normalize()
            speed = self.sprint_speed if self.key_map["shift"] else self.walk_speed
            old_pos = self.player.getPos(self.render)
            self.player.setPos(old_pos + move * speed * dt)
            self.player.setPos(self._clamp_player_with_holo_vessel(old_pos, self.player.getPos(self.render)))

        return Task.cont

    def _cycle_dimension(self, immediate: bool = False) -> None:
        self._close_dimension_gate_panel()
        if hasattr(self, "outer_world"):
            self.outer_world.cycle_dimension(immediate=immediate)
            self._sync_dimension_music(force=True)

if __name__ == "__main__":
    app = HoloVerseWorldPrototype()
    app.run()
