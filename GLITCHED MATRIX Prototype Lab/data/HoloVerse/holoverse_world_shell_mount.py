"""Pass 78 isolated HoloVerse default world mount adapter.

This native extraction from the large standalone `world.py` keeps the hub
authoritative while preloading a bounded HoloVerse world around the observatory.
The default boot path warms every biome ring along the local/player sector and
cardinal hub corridors, then adds lightweight exit gates, transition ribbons,
biome signatures, first-ring ambient props, near-hub ground-continuity lanes,
scale handoff markers, non-authoritative height/collision hint rails, traversal
direction cues, biome-tinted corridor theming, capped light/fog theme handoff,
subtle ambience/audio hook metadata, biome-aware status prompts, and low-cost
animated shell motion, bounded playable traversal, soft boundary feedback, biome-entry prompts, lightweight shell checkpoints, pass45 aqua/flora/fauna infill layer, pass46 calm connected wave surface and green biome polish, pass47 shallow aqua basin/coral floor and hoverboard-ready surface, pass48 Desert/Ice modern vector landmark polish, and a source-bridge path that salvages the real `world.py` world-generation helpers into the Core-owned scene graph. The bridge imports definitions only, never instantiates the standalone ShowBase/window app, replaces the old named-region statue bots with compact filled drone designs, keeps world-object infill enabled through the host, and falls back to the extracted adapter when a helper is unavailable.
"""
from __future__ import annotations

import importlib.util
import json
import math
import random
import sys
import time
import types
from dataclasses import asdict, is_dataclass
from pathlib import Path

from panda3d.core import Vec3, TransparencyAttrib

ADAPTER_ROOT = Path(__file__).resolve().parent
BIOME_SECTOR_COUNT = 48
BIOME_STREAM_SECTOR_RADIUS_DEFAULT = 4
BIOME_HUB_CORRIDOR_DEGREES = (-90.0, 0.0, 90.0, 180.0)
BIOME_DEFAULT_MAX_PRELOADED_SECTORS = 192
BIOME_DEFAULT_SIGNATURE_DENSITY = 2
BIOME_DEFAULT_FIRST_RING_PROP_COUNT = 14
BIOME_DEFAULT_GROUND_BAND_COUNT = 5
BIOME_DEFAULT_DIRECTION_MARKER_COUNT = 6
BIOME_DEFAULT_THEME_HANDOFF_STRENGTH = 0.35
BIOME_DEFAULT_HUB_THEME_MAX_BLEND = 0.18
BIOME_DEFAULT_HUB_THEME_FOG_BLEND = 0.14
BIOME_DEFAULT_HUB_THEME_LIGHT_BLEND = 0.12
BIOME_DEFAULT_AUDIO_HANDOFF_STRENGTH = 0.34
BIOME_DEFAULT_AMBIENCE_RADIUS = 620.0
BIOME_DEFAULT_MOTION_INTENSITY = 0.38
BIOME_DEFAULT_PLAY_RADIUS = 11100.0
BIOME_DEFAULT_PLAY_SPEED_SCALE = 1.10
BIOME_DEFAULT_BOUNDARY_WARNING_DISTANCE = 28.0
BIOME_DEFAULT_CHECKPOINT_COUNT = 12
BIOME_DEFAULT_CHECKPOINT_PICKUP_RADIUS = 4.8
BIOME_DEFAULT_WORLD_PY_SOURCE_BRIDGE = True
BIOME_SOURCE_BRIDGE_METHOD_SKIP = {"__init__", "run", "destroy", "main", "setup_window", "setup_scene", "setup_ui", "setup_input", "setup_gamepad", "setup_audio", "setup_vr", "rebuild_station", "clear_station", "toggle_menu", "open_core_console", "close_core_console", "interact", "teleport_to_hub", "activate_artifact", "activate_default_world_shell", "update_task", "build_io88_flatland_bot", "build_named_region_bot", "build_named_region_bot_network", "update_named_region_bots", "_active_named_region_bot_nodes"}
BIOME_ENTRY_GROUND_START_RADIUS = 30.0
BIOME_ENTRY_GROUND_END_RADIUS = 620.0
BIOME_SCALE_HANDOFF_RADII = (92.0, 180.0, 320.0, 620.0)
BIOME_RINGS = [
    {"key": 1, "name": "FLAT", "label": "FLAT", "r0": 30.0, "r1": 620.0, "kind": "flat", "height": 0.0, "hue": 0.08, "color": (0.78, 0.82, 0.86, 0.34)},
    {"key": 2, "name": "FORESTS", "label": "FORESTS", "r0": 620.0, "r1": 1920.0, "kind": "forest", "height": 4.8, "hue": 0.32, "color": (0.18, 0.95, 0.30, 0.30)},
    {"key": 3, "name": "GREEN HILLS", "label": "GREEN HILLS", "r0": 1920.0, "r1": 3300.0, "kind": "hills", "height": 13.8, "hue": 0.24, "color": (0.48, 1.00, 0.18, 0.38)},
    {"key": 4, "name": "MUSHROOM", "label": "MUSHROOM", "r0": 3300.0, "r1": 4700.0, "kind": "mushroom", "height": 12.4, "hue": 0.88, "color": (1.00, 0.22, 0.82, 0.32)},
    {"key": 5, "name": "DESERT", "label": "DESERT", "r0": 4700.0, "r1": 6100.0, "kind": "desert", "height": 7.4, "hue": 0.12, "color": (1.00, 0.62, 0.22, 0.30)},
    {"key": 6, "name": "ICE", "label": "ICE", "r0": 6100.0, "r1": 7500.0, "kind": "ice", "height": 10.8, "hue": 0.60, "color": (0.66, 0.92, 1.00, 0.32)},
    {"key": 7, "name": "URBAN", "label": "URBAN", "r0": 7500.0, "r1": 9100.0, "kind": "urban", "height": 4.9, "hue": 0.68, "color": (0.115, 0.122, 0.138, 0.58)},
    {"key": 8, "name": "METROPOLIS", "label": "METROPOLIS", "r0": 9100.0, "r1": 11100.0, "kind": "metropolis", "height": 2.6, "hue": 0.76, "color": (0.72, 0.44, 1.00, 0.30)},
]
BIOME_SKY_THEME_RGB = {
    "flat": (0.34, 0.44, 0.64),
    "forest": (0.16, 0.34, 0.28),
    "hills": (0.30, 0.68, 0.18),
    "water": (0.08, 0.24, 0.44),
    "mushroom": (0.34, 0.12, 0.42),
    "desert": (0.44, 0.30, 0.20),
    "ice": (0.22, 0.38, 0.56),
    "urban": (0.62, 0.66, 0.72),
    "metropolis": (0.18, 0.08, 0.30),
}
BIOME_FOG_THEME = {
    "flat": (180.0, 470.0),
    "forest": (110.0, 350.0),
    "hills": (78.0, 300.0),
    "water": (42.0, 160.0),
    "desert": (150.0, 430.0),
    "ice": (120.0, 390.0),
    "urban": (95.0, 315.0),
    "metropolis": (110.0, 380.0),
}
BIOME_AUDIO_HINTS = {
    "flat": {"loop": "hv_hub_command_theme.wav", "tone": "clean command rhythm", "bus": "music"},
    "forest": {"loop": "hv_world_exploration_theme.wav", "tone": "leaf pulse exploration", "bus": "music"},
    "hills": {"loop": "hv_world_exploration_theme.wav", "tone": "open air exploration", "bus": "music"},
    "water": {"loop": "hv_water_depth_theme.wav", "tone": "submerged shimmer bed", "bus": "ambience"},
    "mushroom": {"loop": "hv_world_exploration_theme.wav", "tone": "spore forest rhythm", "bus": "music"},
    "desert": {"loop": "hv_world_exploration_theme.wav", "tone": "warm frontier rhythm", "bus": "music"},
    "ice": {"loop": "hv_space_orbit_theme.wav", "tone": "cold crystal orbit", "bus": "music"},
    "urban": {"loop": "hv_urban_conflict_theme.wav", "tone": "war-zone pulse", "bus": "music"},
    "metropolis": {"loop": "hv_metropolis_neon_theme.wav", "tone": "neon city groove", "bus": "music"},
}
REGION_BOTS = [
    ("IO", 1), ("Vanta", 2), ("Nyx", 3), ("Solace", 4),
    ("Ember", 5), ("Mirror", 6), ("Sable", 7), ("Archivist", 8), ("Orbit", 8),
]


def clamp(value, lo, hi):
    return max(lo, min(hi, value))


def smoothstep01(value):
    t = clamp(float(value), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)



class _WorldPyHost:
    """Host object for salvaged world.py generation methods."""

    def __init__(self, adapter, module):
        self._adapter = adapter
        self._module = module
        self.app = adapter.app
        self.render = getattr(adapter.app, "render", None)
        self.loader = getattr(adapter.app, "loader", None)
        self.camera = getattr(adapter.app, "camera", None)
        self.camLens = getattr(adapter.app, "camLens", None)
        self.win = getattr(adapter.app, "win", None)
        self.clock = getattr(adapter.app, "clock", None)
        self.cfg = self._build_source_cfg(module)
        self.elapsed = float(getattr(adapter.app, "elapsed", 0.0))
        self.player_pos = Vec3(getattr(adapter.app, "player_pos", Vec3(0, -10, getattr(self.cfg, "player_eye_height", 3.95))))
        self.player_yaw = float(getattr(adapter.app, "player_yaw", 0.0))
        self.player_pitch = float(getattr(adapter.app, "player_pitch", -7.0))
        self.hub_radius = float(getattr(adapter.app, "hub_radius", 30.0))
        self.artifact_radius = float(getattr(adapter.app, "artifact_radius", 22.8))
        self.room_bounds = []
        self.terrain_chunks = {}
        self.terrain_chunk_pruned_count = 0
        self.metropolis_chunks = {}
        self.metropolis_preload_radius = int(getattr(module, "METROPOLIS_PRELOAD_RADIUS", 3))
        self.metropolis_overlap_skip_count = 0
        self.metropolis_duplicate_edge_suppression_count = 0
        self.metropolis_hover_vehicle_nodes = []
        self.metropolis_robot_nodes = []
        self.deep_water_creature_nodes = []
        self.deep_water_glow_nodes = []
        self.deep_water_feature_nodes = []
        self.deep_water_sky_creature_nodes = []
        self.deep_water_surface_refresh_time = -999.0
        self.current_water_depth = 0.0
        self.water_region_occlusion_active = False
        self.urban_battle_nodes = []
        self.urban_airstrike_nodes = []
        self.space_layer_root = None
        self.space_layer_star_root = None
        self.space_layer_far_star_root = None
        self.space_layer_asteroid_nodes = []
        self.space_layer_flying_entity_nodes = []
        self.space_layer_initialized = False
        self.space_layer_active = False
        self.salvage_population_nodes = []
        self.salvage_population_pruned_count = 0
        self.named_region_bot_nodes = []
        self.named_region_bot_specs = []
        self.named_region_bot_pruned_count = 0
        self.io88_bot_root = None
        self.artifacts = []
        self.galaxy_nodes = []
        self.nearest_artifact = None
        self.nearest_artifact_dist = 999.0
        self.active_biome_name = "FLAT"
        self.last_biome_travel_key = None
        self.current_bg_rgb = (getattr(self.cfg, "background_value", 0.018),) * 3
        self.current_sky_rgb = self.current_bg_rgb
        self.current_day_factor = 0.0
        self.current_dusk_factor = 0.0
        self.current_sky_biome = "HUB"
        self.sky_ring_nodes = []
        self.celestial_nodes = {}
        self.surface_audit_summary = {}
        self.legacy_sky_background_removed = True
        self.forest_tree_variants = tuple(getattr(module, "FOREST_TREE_VARIANTS", ("spire", "canopy", "split", "tower")))
        self.world_actor_pruned_count = 0
        self.world_actors = []
        self.legacy_runtime_enabled = False
        self.box_model = None
        self.weapon_wire_nodes = []
        self.hybrid_floor_tex = None
        self.hybrid_wall_tex = None
        self.hybrid_shard_tex = None
        self.hybrid_accent_tex = None
        self._make_roots()
        self._bind_methods(module)
        try:
            self.box_model = self.create_unit_box_model()
        except Exception:
            self.box_model = None

    def __getattr__(self, name):
        return getattr(self.app, name)

    def _build_source_cfg(self, module):
        data = {}
        default = getattr(module, "DEFAULT_CONFIG", None)
        try:
            if is_dataclass(default):
                data.update(asdict(default))
            elif hasattr(default, "__dict__"):
                data.update({k: v for k, v in vars(default).items() if not k.startswith("_")})
        except Exception:
            pass
        app_cfg = getattr(self.app, "cfg", None)
        try:
            data.update({k: v for k, v in vars(app_cfg).items() if not k.startswith("_")})
        except Exception:
            pass
        data.setdefault("terrain_render_radius", 3)
        data.setdefault("world_fill_stride", 2)
        data.setdefault("line_thickness", float(getattr(app_cfg, "line_thickness", 2.4) if app_cfg else 2.4))
        data.setdefault("world_anchor_distance", 72.0)
        data.setdefault("world_hub_clear_radius", 46.0)
        data.setdefault("world_corridor_half_width", 7.5)
        data.setdefault("world_ground_match_radius", 24.0)
        data.setdefault("world_ground_match_blend", 18.0)
        data.setdefault("day_night_cycle_seconds", float(getattr(module, "DAY_NIGHT_CYCLE_SECONDS", 720.0)))
        data.setdefault("sky_transition_rate", float(getattr(module, "DAY_NIGHT_SKY_TRANSITION_RATE", 0.20)))
        data.setdefault("player_eye_height", float(getattr(app_cfg, "player_eye_height", 3.95) if app_cfg else 3.95))
        return types.SimpleNamespace(**data)

    def _make_roots(self):
        base = self._adapter.root.attachNewNode("world-py-source-bridge-root")
        self.root_3d = base
        self.surface_root = base.attachNewNode("surface-root")
        self.line_root = base.attachNewNode("line-root")
        self.accent_root = base.attachNewNode("accent-root")
        self.dome_root = base.attachNewNode("dome-root-disabled")
        self.lens_root = base.attachNewNode("lens-root-disabled")
        self.sky_root = base.attachNewNode("sky-root")
        self.atmosphere_root = base.attachNewNode("atmosphere-root")
        self.world_root = base.attachNewNode("world-root")
        self.user_build_root = self.world_root.attachNewNode("user-build-root")
        self.galaxy_root = base.attachNewNode("galaxy-root")
        for node in (self.surface_root, self.line_root, self.accent_root, self.sky_root, self.atmosphere_root, self.world_root, self.user_build_root, self.galaxy_root):
            try:
                node.setTransparency(TransparencyAttrib.MAlpha)
            except Exception:
                pass
        self._source_root = base

    def _bind_methods(self, module):
        cls = getattr(module, "CommandHubApp", None)
        if cls is None:
            return
        for name, value in getattr(cls, "__dict__", {}).items():
            if name in BIOME_SOURCE_BRIDGE_METHOD_SKIP or name.startswith("__"):
                continue
            if callable(value):
                try:
                    setattr(self, name, types.MethodType(value, self))
                except Exception:
                    pass

    def modern_region_bot_anchor(self, spec: dict) -> Vec3:
        """Anchor compact named drones in their home regions without the old statue/HUD setup."""
        angle = math.radians(float(getattr(self._module, "NAMED_REGION_BOT_ANCHOR_ANGLE_DEG", -90.0)))
        kind = str(spec.get("kind", "flat"))
        if kind == "space" or spec.get("ring_key") is None:
            # Space Bot orbits outside the Dyson shell instead of spawning inside it.
            orbit_fn = getattr(self, "dyson_space_bot_orbit_position", None)
            if callable(orbit_fn):
                return Vec3(orbit_fn(0.0))
            anchor = getattr(self._module, "SPACE_DYSON_BOT_ANCHOR", None)
            if anchor is not None:
                return Vec3(anchor.x, anchor.y, anchor.z)
            radius = float(getattr(self._module, "BIOME_OUTER_RADIUS", 11100.0)) + 720.0
            return Vec3(math.cos(angle) * radius, math.sin(angle) * radius, float(getattr(self._module, "SPACE_LAYER_START_Z", 420.0)) + 260.0)
        ring = None
        try:
            fn = getattr(self, "biome_ring_for_key", None)
            if callable(fn):
                ring = fn(spec.get("ring_key"))
        except Exception:
            ring = None
        if ring is None:
            for candidate in getattr(self._module, "BIOME_RINGS", []) or []:
                try:
                    if int(candidate.get("key", -1)) == int(spec.get("ring_key", 1)):
                        ring = candidate
                        break
                except Exception:
                    continue
        ring = ring or (getattr(self._module, "BIOME_RINGS", [{}]) or [{}])[0]
        r0 = float(ring.get("r0", 30.0))
        r1 = float(ring.get("r1", 620.0))
        span = max(1.0, r1 - r0)
        if int(ring.get("key", 1)) == 1:
            radius = min(r1 - 48.0, max(132.0, r0 + span * 0.48))
        else:
            t = clamp(float(spec.get("anchor_t", 0.50)), 0.16, 0.84)
            radius = r0 + span * t
        x = math.cos(angle) * radius
        y = math.sin(angle) * radius
        try:
            if kind == "water" and callable(getattr(self, "deep_water_craft_eye_z", None)):
                z = float(self.deep_water_craft_eye_z(x, y, ring)) + 7.0
            elif callable(getattr(self, "world_height_at", None)):
                z = float(self.world_height_at(x, y)) + 7.2
            else:
                z = float(ring.get("height", 0.0)) + 8.0
        except Exception:
            z = float(ring.get("height", 0.0)) + 8.0
        return Vec3(x, y, z)

    def _drone_box(self, parent, pos, hpr, scale, tint, wire_rgb, alpha=0.96):
        """Filled drone part with wire trim."""
        add_box_model = getattr(self, "add_box_model", None)
        if callable(add_box_model) and getattr(self, "box_model", None) is not None:
            try:
                return add_box_model(parent, pos, hpr, scale, None, tint, wire_rgb=wire_rgb, alpha=alpha)
            except Exception:
                pass
        add_box = getattr(self, "add_box", None)
        if callable(add_box):
            try:
                return add_box(parent, pos, scale, (tint[0], tint[1], tint[2], alpha), 0.36)
            except Exception:
                return None
        return None

    def build_named_region_bot(self, spec: dict):
        """Build a compact modern named drone with no hover pad, halo, label, or HUD frame."""
        name = str(spec.get("name", "Bot"))
        region = str(spec.get("region", "REGION"))
        kind = str(spec.get("kind", region.lower()))
        color = tuple(float(c) for c in spec.get("color", (0.42, 0.72, 1.0)))
        accent = tuple(float(c) for c in spec.get("accent", (0.88, 1.0, 1.0)))
        anchor = self.modern_region_bot_anchor(spec)
        root = self.world_root.attachNewNode(f"named-drone-{name.lower()}-{kind}")
        root.setPos(anchor)
        idx = len(getattr(self, "named_region_bot_nodes", []))
        drone_scale = 2.15 * float(spec.get("scale", 1.0))
        if kind == "space":
            drone_scale *= 1.38
            name = "Space Bot" if not name.strip() or name.lower() == "orbit" else name
        root.setScale(drone_scale)
        root.setTransparency(TransparencyAttrib.MAlpha)
        root.setLightOff(1)
        root.setTextureOff(10)
        root.setTwoSided(True)
        root.setPythonTag("named_region_bot_name", name)
        root.setPythonTag("named_region_bot_region", region)
        root.setPythonTag("named_region_bot_kind", kind)
        root.setPythonTag("named_region_bot_base_x", float(anchor.x))
        root.setPythonTag("named_region_bot_base_y", float(anchor.y))
        root.setPythonTag("named_region_bot_base_z", float(anchor.z))
        root.setPythonTag("named_region_bot_phase", idx * 0.91)
        root.setPythonTag("named_region_bot_roam_radius", 26.0 + 3.5 * (idx % 5))
        root.setPythonTag("named_region_bot_roam_speed", 0.18 + 0.025 * (idx % 4))
        root.setPythonTag("named_region_bot_help_role", "regional guide")
        base_rgba = (clamp(color[0] * 0.82 + 0.035, 0.0, 1.0), clamp(color[1] * 0.82 + 0.035, 0.0, 1.0), clamp(color[2] * 0.82 + 0.035, 0.0, 1.0), 0.96)
        dark_rgba = (clamp(color[0] * 0.24 + 0.035, 0.0, 1.0), clamp(color[1] * 0.24 + 0.035, 0.0, 1.0), clamp(color[2] * 0.24 + 0.045, 0.0, 1.0), 0.98)
        mid_rgba = (clamp(color[0] * 0.58 + accent[0] * 0.26, 0.0, 1.0), clamp(color[1] * 0.58 + accent[1] * 0.26, 0.0, 1.0), clamp(color[2] * 0.58 + accent[2] * 0.26, 0.0, 1.0), 0.95)
        accent_rgba = (clamp(accent[0], 0.0, 1.0), clamp(accent[1], 0.0, 1.0), clamp(accent[2], 0.0, 1.0), 0.98)
        wire = Vec3(min(1.25, accent_rgba[0] * 1.08), min(1.25, accent_rgba[1] * 1.08), min(1.25, accent_rgba[2] * 1.08))
        self._drone_box(root, Vec3(0.0, 0.0, 1.52), Vec3(0.0, 0.0, 0.0), Vec3(0.82, 0.54, 0.34), dark_rgba, wire, 0.98)
        self._drone_box(root, Vec3(0.0, 0.18, 1.70), Vec3(0.0, -4.0, 0.0), Vec3(0.58, 0.22, 0.16), base_rgba, wire, 0.96)
        self._drone_box(root, Vec3(0.0, 0.52, 1.62), Vec3(0.0, 0.0, 0.0), Vec3(0.28, 0.22, 0.20), accent_rgba, wire, 0.98)
        self._drone_box(root, Vec3(-0.62, 0.0, 1.46), Vec3(0.0, 0.0, -8.0), Vec3(0.30, 0.42, 0.24), mid_rgba, wire, 0.94)
        self._drone_box(root, Vec3(0.62, 0.0, 1.46), Vec3(0.0, 0.0, 8.0), Vec3(0.30, 0.42, 0.24), mid_rgba, wire, 0.94)
        self._drone_box(root, Vec3(-0.92, -0.05, 1.34), Vec3(0.0, 0.0, -13.0), Vec3(0.18, 0.30, 0.18), accent_rgba, wire, 0.92)
        self._drone_box(root, Vec3(0.92, -0.05, 1.34), Vec3(0.0, 0.0, 13.0), Vec3(0.18, 0.30, 0.18), accent_rgba, wire, 0.92)
        self._drone_box(root, Vec3(-0.34, -0.48, 1.42), Vec3(0.0, 0.0, 0.0), Vec3(0.16, 0.20, 0.18), accent_rgba, wire, 0.82)
        self._drone_box(root, Vec3(0.34, -0.48, 1.42), Vec3(0.0, 0.0, 0.0), Vec3(0.16, 0.20, 0.18), accent_rgba, wire, 0.82)
        self._drone_box(root, Vec3(0.0, -0.28, 1.92), Vec3(0.0, 0.0, 0.0), Vec3(0.40, 0.18, 0.08), base_rgba, wire, 0.90)
        segments = [
            (Vec3(-0.72, 0.08, 1.86), Vec3(-1.18, 0.28, 2.04)),
            (Vec3(0.72, 0.08, 1.86), Vec3(1.18, 0.28, 2.04)),
            (Vec3(-0.24, -0.36, 1.26), Vec3(-0.44, -0.72, 1.14)),
            (Vec3(0.24, -0.36, 1.26), Vec3(0.44, -0.72, 1.14)),
            (Vec3(0.0, 0.00, 2.02), Vec3(0.0, 0.00, 2.42)),
        ]
        add_line_segments = getattr(self, "add_line_segments", None)
        if callable(add_line_segments):
            try:
                add_line_segments(root, segments, accent_rgba, self.cfg.line_thickness * 0.22, f"{name.lower()}-drone-trim")
            except Exception:
                pass
        if name == "IO":
            self.io88_bot_root = root
        return root

    def build_named_region_bot_network(self):
        for old in list(getattr(self, "named_region_bot_nodes", []) or []):
            try:
                if old is not None and not old.isEmpty():
                    old.removeNode()
            except Exception:
                pass
        self.named_region_bot_nodes = []
        self.named_region_bot_specs = []
        self.named_region_bot_pruned_count = 0
        bot_map = list(getattr(self._module, "NAMED_REGION_BOT_MAP", []) or [])
        max_bots = int(getattr(self._module, "MAX_NAMED_REGION_BOTS", len(bot_map) or 9))
        for spec in bot_map[:max_bots]:
            bot = self.build_named_region_bot(spec)
            if bot is not None:
                self.named_region_bot_nodes.append(bot)
                self.named_region_bot_specs.append({"name": spec.get("name"), "region": spec.get("region"), "kind": spec.get("kind")})
        return self.named_region_bot_nodes

    def update_named_region_bots(self, dt: float):
        del dt
        for idx, node in enumerate(list(getattr(self, "named_region_bot_nodes", []) or [])):
            try:
                if node is None or node.isEmpty():
                    continue
                if bool(node.getPythonTag("named_region_bot_paused")):
                    continue
                bx = float(node.getPythonTag("named_region_bot_base_x") or node.getX())
                by = float(node.getPythonTag("named_region_bot_base_y") or node.getY())
                bz = float(node.getPythonTag("named_region_bot_base_z") or node.getZ())
                phase = float(node.getPythonTag("named_region_bot_phase") or 0.0)
                radius = float(node.getPythonTag("named_region_bot_roam_radius") or 24.0)
                speed = float(node.getPythonTag("named_region_bot_roam_speed") or 0.18)
                kind = str(node.getPythonTag("named_region_bot_kind") or "").lower()
                if kind == "space":
                    orbit_fn = getattr(self, "dyson_space_bot_orbit_position", None)
                    if callable(orbit_fn):
                        pos = Vec3(orbit_fn(float(self.elapsed) + phase * 0.20))
                    else:
                        center = getattr(self._module, "SPACE_DYSON_FOCUS_POS", Vec3(0.0, -12480.0, 1185.0))
                        orbit_radius = float(getattr(self._module, "SPACE_DYSON_BOT_ORBIT_RADIUS", 575.0))
                        ang = float(self.elapsed) * float(getattr(self._module, "SPACE_DYSON_BOT_ORBIT_SPEED", 0.115)) + phase
                        pos = Vec3(center.x + math.cos(ang) * orbit_radius, center.y + math.sin(ang) * orbit_radius, center.z + float(getattr(self._module, "SPACE_DYSON_BOT_ORBIT_HEIGHT", 28.0)))
                    node.setPos(pos)
                    try:
                        node.lookAt(getattr(self._module, "SPACE_DYSON_FOCUS_POS", Vec3(0.0, -12480.0, 1185.0)))
                        node.setH(node.getH() + 180.0)
                    except Exception:
                        pass
                    node.setP(math.sin(float(self.elapsed) * 0.33 + phase) * 5.0)
                    node.setR(math.sin(float(self.elapsed) * 0.57 + phase) * 10.0)
                else:
                    t = float(self.elapsed) * speed + phase
                    x = bx + math.cos(t) * radius + math.sin(t * 0.43 + idx) * radius * 0.18
                    y = by + math.sin(t * 0.82) * radius * 0.52
                    z = bz + math.sin(float(self.elapsed) * 0.92 + phase) * 1.15 + math.sin(t * 1.7) * 0.34
                    node.setPos(x, y, z)
                    dx = -math.sin(t) * radius
                    dy = math.cos(t * 0.82) * radius * 0.52
                    heading = math.degrees(math.atan2(dy, dx)) - 90.0 if abs(dx) + abs(dy) > 0.001 else node.getH()
                    node.setHpr(heading, math.sin(t * 1.2) * 4.5, math.sin(t * 1.6 + idx) * 8.0)
            except Exception:
                continue

    def _active_named_region_bot_nodes(self) -> list:
        out = []
        for node in list(getattr(self, "named_region_bot_nodes", []) or []):
            try:
                if node is not None and not node.isEmpty():
                    out.append(node)
            except Exception:
                pass
        return out

    def sync_from_app(self):
        self.elapsed = float(getattr(self.app, "elapsed", self.elapsed))
        self.player_pos = Vec3(getattr(self.app, "player_pos", self.player_pos))
        self.player_yaw = float(getattr(self.app, "player_yaw", self.player_yaw))
        self.player_pitch = float(getattr(self.app, "player_pitch", self.player_pitch))

    def build_initial_world(self):
        self.sync_from_app()
        completed = []
        failures = []
        for name in ("build_dynamic_sky_guides", "build_flatland_disk", "build_biome_ring_framework", "build_named_region_bot_network", "setup_space_layer"):
            fn = getattr(self, name, None)
            if not callable(fn):
                failures.append(f"{name}:missing")
                continue
            try:
                fn()
                completed.append(name)
            except Exception as exc:
                failures.append(f"{name}:{exc.__class__.__name__}")
        try:
            self.update_world_chunks(force=True)
            completed.append("update_world_chunks")
        except Exception as exc:
            failures.append(f"update_world_chunks:{exc.__class__.__name__}")
        return {"completed": completed, "failures": failures}

    def update_runtime(self, dt=0.0):
        self.sync_from_app()
        completed = []
        failures = []
        holospace_active = False
        try:
            checker = getattr(self.app, "is_holospace_active", None)
            holospace_active = bool(checker()) if callable(checker) else bool(getattr(self.app, "holospace_active", False))
        except Exception:
            holospace_active = bool(getattr(self.app, "holospace_active", False))
        if holospace_active:
            self.active_biome_name = "HOLOSPACE"
            # HoloSpace is not biome 8. Biome 8 is Metropolis, so skip all
            # terrain/city/bot updates and run only the fixed Dyson space layer.
            for list_attr in (
                "metropolis_hover_vehicle_nodes",
                "metropolis_robot_nodes", "deep_water_creature_nodes",
                "deep_water_glow_nodes", "deep_water_feature_nodes",
                "deep_water_sky_creature_nodes", "salvage_population_nodes",
                "urban_battle_nodes", "urban_airstrike_nodes", "world_actors",
                "galaxy_nodes",
            ):
                for node in list(getattr(self, list_attr, []) or []):
                    try:
                        if node is not None and not node.isEmpty():
                            node.hide()
                    except Exception:
                        pass
            for name, args in (("update_space_layer", (dt,)), ("update_named_region_bots", (dt,))):
                fn = getattr(self, name, None)
                if callable(fn):
                    try:
                        fn(*args)
                        completed.append(name)
                    except Exception as exc:
                        failures.append(f"{name}:{exc.__class__.__name__}")
            return {"completed": completed, "failures": failures, "holospace_isolated": True, "space_bot_visible": True}
        # Source-of-truth guard: world.py's Urban helper is deleted. The bridge
        # never drives source-world Urban; Dimensions/Urban Warzone/runtime.py is
        # the only combat/gameplay owner.
        app_warzone_active = bool(getattr(self.app, "urban_warzone_active", False))
        for name, args in (
            ("update_world_chunks", ()),
            ("update_metropolis_air_traffic", (dt,)),
            # Old source-world Urban update is deleted. Runtime-owned Urban Warzone
            # updates on the app host after activation, never through this bridge.
            ("update_deep_water_life", (dt,)),
            ("update_salvage_population", (dt,)),
            ("update_named_region_bots", (dt,)),
            ("update_day_night_sky", (dt,)),
            ("update_space_layer", (dt,)),
        ):
            if app_warzone_active and name == "update_urban_warzone":
                completed.append("skip_source_world_urban_warzone_runtime_owned")
                continue
            fn = getattr(self, name, None)
            if not callable(fn):
                continue
            try:
                fn(*args)
                completed.append(name)
            except Exception as exc:
                failures.append(f"{name}:{exc.__class__.__name__}")
        return {"completed": completed, "failures": failures}

    def report(self):
        return {
            "source_bridge": True,
            "source_world_file": "world.py",
            "source_world_version": str(getattr(self._module, "VERSION", "unknown")),
            "source_world_game_name": str(getattr(self._module, "GAME_NAME", "HoloVerse")),
            "active_biome": ("Hub Region" if str(getattr(self, "active_biome_name", "FLAT")).upper() == "FLAT" else str(getattr(self, "active_biome_name", "FLAT"))),
            "terrain_chunks": len(getattr(self, "terrain_chunks", {}) or {}),
            "metropolis_chunks": len(getattr(self, "metropolis_chunks", {}) or {}),
            "named_region_bots": len(getattr(self, "named_region_bot_nodes", []) or []),
            "salvage_population": len(getattr(self, "salvage_population_nodes", []) or []),
            "space_layer_active": bool(getattr(self, "space_layer_active", False)),
            "surface_audit": getattr(self, "surface_audit_summary", {}) or {},
        }


class HoloVerseWorldShellMount:
    """Bounded streamed HoloVerse world surrounding the existing hub."""

    def __init__(self, app):
        self.app = app
        self.root = None
        self.static_root = None
        self.stream_root = None
        self.nodes = []
        self.sector_nodes: dict[tuple[int, int], object] = {}
        self.active_key = 1
        self.scale = 1.0
        self.detail = "stream"
        self.stream_radius = BIOME_STREAM_SECTOR_RADIUS_DEFAULT
        self.default_preload = False
        self.preload_all_biomes = False
        self.preload_corridors = True
        self.preload_sector_radius = 0
        self.max_preloaded_sectors = BIOME_DEFAULT_MAX_PRELOADED_SECTORS
        self.exit_gate_hints = True
        self.entry_ribbons = True
        self.transition_cues = True
        self.first_ring_props = True
        self.first_ring_prop_count = BIOME_DEFAULT_FIRST_RING_PROP_COUNT
        self.ground_continuity = True
        self.ground_band_count = BIOME_DEFAULT_GROUND_BAND_COUNT
        self.scale_handoff_markers = True
        self.collision_height_hints = True
        self.local_detail_boost = True
        self.biome_signature_density = BIOME_DEFAULT_SIGNATURE_DENSITY
        self.directional_feedback = True
        self.direction_marker_count = BIOME_DEFAULT_DIRECTION_MARKER_COUNT
        self.corridor_theming = True
        self.theme_handoff = True
        self.theme_handoff_strength = BIOME_DEFAULT_THEME_HANDOFF_STRENGTH
        self.hub_theme_influence = True
        self.hub_theme_max_blend = BIOME_DEFAULT_HUB_THEME_MAX_BLEND
        self.hub_theme_fog_blend = BIOME_DEFAULT_HUB_THEME_FOG_BLEND
        self.hub_theme_light_blend = BIOME_DEFAULT_HUB_THEME_LIGHT_BLEND
        self.status_prompts = True
        self.motion_enabled = True
        self.motion_intensity = BIOME_DEFAULT_MOTION_INTENSITY
        self.audio_handoff = True
        self.audio_handoff_strength = BIOME_DEFAULT_AUDIO_HANDOFF_STRENGTH
        self.ambience_radius = BIOME_DEFAULT_AMBIENCE_RADIUS
        self.playable_enabled = True
        self.playable_radius = BIOME_DEFAULT_PLAY_RADIUS
        self.play_speed_scale = BIOME_DEFAULT_PLAY_SPEED_SCALE
        self.play_floor_enabled = True
        self.world_py_source_bridge = BIOME_DEFAULT_WORLD_PY_SOURCE_BRIDGE
        self.source_bridge_active = False
        self.source_runtime = None
        self.source_bridge_status = "not_attempted"
        self.source_bridge_report = {}
        self.pass45_beauty_root = None
        self.pass45_water_surface_nodes = []
        self.pass45_fauna_nodes = []
        self.pass46_water_wave_nodes = []
        self.pass46_water_wave_specs = []
        self.pass46_last_wave_rebuild = -999.0
        self.pass48_motion_nodes = []
        self.boundary_feedback = True
        self.boundary_warning_distance = BIOME_DEFAULT_BOUNDARY_WARNING_DISTANCE
        self.checkpoint_enabled = True
        self.checkpoint_count = BIOME_DEFAULT_CHECKPOINT_COUNT
        self.checkpoint_pickup_radius = BIOME_DEFAULT_CHECKPOINT_PICKUP_RADIUS
        self.checkpoint_nodes: dict[str, object] = {}
        self.checkpoint_data: list[dict] = []
        self.claimed_checkpoints: set[str] = set()
        self.play_state_data = {}
        self.audio_handoff_data = {}
        self.shell_prompt = "HOLOVERSE READY"
        self.motion_nodes = []
        self.play_state_data = {}
        self.theme_handoff_data = {}
        self.default_preloaded = False
        self.retired_water_purge_done = False
        self.status = "READY // FULL-SCALE DEFAULT HOLOVERSE"
        self.last_center_sector = None
        self.last_wanted = set()
        self.force_refresh = True
        self.last_write_at = 0.0
        self.last_report = {}
        self.seed = int(getattr(app.cfg, "world_seed", 10457) or 10457)
        self.read_mount_options()

    def destroy(self):
        runtime = getattr(self, "source_runtime", None)
        if runtime is not None:
            try:
                cleanup = getattr(runtime, "cleanup_obsolete_space_layers", None)
                if callable(cleanup):
                    cleanup()
            except Exception:
                pass
            try:
                source_root = getattr(runtime, "_source_root", None)
                if source_root is not None and not source_root.isEmpty():
                    source_root.removeNode()
            except Exception:
                pass
        if self.root is not None:
            try:
                self.root.removeNode()
            except Exception:
                pass
        # Belt-and-suspenders cleanup for older zips that parented space directly
        # under render instead of the source bridge root.
        try:
            render = getattr(self.app, "render", None)
            if render is not None:
                for pattern in ("**/endless-space-layer", "**/holo-dyson-space-layer", "**/dyson-sphere-build-megastructure", "**/space-layer-asteroid-*", "**/endless-space-stars"):
                    for node in list(render.findAllMatches(pattern)):
                        try:
                            node.removeNode()
                        except Exception:
                            pass
        except Exception:
            pass
        self.root = None
        self.static_root = None
        self.stream_root = None
        self.nodes = []
        self.sector_nodes = {}
        self.source_bridge_active = False
        self.source_runtime = None
        self.source_bridge_status = "destroyed"
        self.source_bridge_report = {}
        self.clear_pass45_beauty_layer()
        self.default_preloaded = False
        self.theme_handoff_data = {}
        self.audio_handoff_data = {}
        self.shell_prompt = "HOLOVERSE DESTROYED"
        self.motion_nodes = []
        self.checkpoint_nodes = {}
        self.checkpoint_data = []
        self.status = "DESTROYED"

    def read_mount_options(self):
        cfg = getattr(self.app, "cfg", object())
        self.active_key = max(1, min(8, int(getattr(cfg, "world_shell_active_biome", self.active_key) or self.active_key)))
        self.scale = max(0.050, min(1.000, float(getattr(cfg, "world_shell_mount_scale", self.scale) or self.scale)))
        self.detail = str(getattr(cfg, "world_shell_mount_detail", self.detail) or self.detail).strip().lower()
        if self.detail not in {"off", "lite", "stream"}:
            self.detail = "stream"
        self.stream_radius = max(1, min(4, int(getattr(cfg, "world_shell_stream_radius", self.stream_radius) or self.stream_radius)))
        self.default_preload = bool(getattr(cfg, "world_shell_default_preload", False))
        self.preload_all_biomes = bool(getattr(cfg, "world_shell_preload_all_biomes", False))
        self.preload_corridors = bool(getattr(cfg, "world_shell_preload_corridors", True))
        self.preload_sector_radius = max(0, min(2, int(getattr(cfg, "world_shell_preload_sector_radius", 0) or 0)))
        self.max_preloaded_sectors = max(12, min(64, int(getattr(cfg, "world_shell_max_preloaded_sectors", 24) or 24)))
        self.exit_gate_hints = bool(getattr(cfg, "world_shell_exit_gate_hints", True))
        self.entry_ribbons = bool(getattr(cfg, "world_shell_entry_ribbons", True))
        self.transition_cues = bool(getattr(cfg, "world_shell_transition_cues", True))
        self.first_ring_props = bool(getattr(cfg, "world_shell_first_ring_props", True))
        self.first_ring_prop_count = max(0, min(32, int(getattr(cfg, "world_shell_first_ring_prop_count", BIOME_DEFAULT_FIRST_RING_PROP_COUNT) or BIOME_DEFAULT_FIRST_RING_PROP_COUNT)))
        self.ground_continuity = bool(getattr(cfg, "world_shell_ground_continuity", True))
        self.ground_band_count = max(2, min(8, int(getattr(cfg, "world_shell_ground_band_count", BIOME_DEFAULT_GROUND_BAND_COUNT) or BIOME_DEFAULT_GROUND_BAND_COUNT)))
        self.scale_handoff_markers = bool(getattr(cfg, "world_shell_scale_handoff_markers", True))
        self.collision_height_hints = bool(getattr(cfg, "world_shell_collision_height_hints", True))
        self.local_detail_boost = bool(getattr(cfg, "world_shell_local_detail_boost", True))
        self.biome_signature_density = max(0, min(3, int(getattr(cfg, "world_shell_biome_signature_density", BIOME_DEFAULT_SIGNATURE_DENSITY) or BIOME_DEFAULT_SIGNATURE_DENSITY)))
        self.directional_feedback = bool(getattr(cfg, "world_shell_directional_feedback", True))
        self.direction_marker_count = max(2, min(10, int(getattr(cfg, "world_shell_direction_marker_count", BIOME_DEFAULT_DIRECTION_MARKER_COUNT) or BIOME_DEFAULT_DIRECTION_MARKER_COUNT)))
        self.corridor_theming = bool(getattr(cfg, "world_shell_corridor_theming", True))
        self.theme_handoff = bool(getattr(cfg, "world_shell_theme_handoff", True))
        self.theme_handoff_strength = max(0.0, min(1.0, float(getattr(cfg, "world_shell_theme_handoff_strength", BIOME_DEFAULT_THEME_HANDOFF_STRENGTH) or BIOME_DEFAULT_THEME_HANDOFF_STRENGTH)))
        self.hub_theme_influence = bool(getattr(cfg, "world_shell_hub_theme_influence", True))
        self.hub_theme_max_blend = max(0.0, min(0.32, float(getattr(cfg, "world_shell_hub_theme_max_blend", BIOME_DEFAULT_HUB_THEME_MAX_BLEND) or BIOME_DEFAULT_HUB_THEME_MAX_BLEND)))
        self.hub_theme_fog_blend = max(0.0, min(0.28, float(getattr(cfg, "world_shell_hub_theme_fog_blend", BIOME_DEFAULT_HUB_THEME_FOG_BLEND) or BIOME_DEFAULT_HUB_THEME_FOG_BLEND)))
        self.hub_theme_light_blend = max(0.0, min(0.24, float(getattr(cfg, "world_shell_hub_theme_light_blend", BIOME_DEFAULT_HUB_THEME_LIGHT_BLEND) or BIOME_DEFAULT_HUB_THEME_LIGHT_BLEND)))
        self.status_prompts = bool(getattr(cfg, "world_shell_status_prompts", True))
        self.motion_enabled = bool(getattr(cfg, "world_shell_motion_enabled", True))
        self.motion_intensity = max(0.0, min(1.0, float(getattr(cfg, "world_shell_motion_intensity", BIOME_DEFAULT_MOTION_INTENSITY) or BIOME_DEFAULT_MOTION_INTENSITY)))
        self.audio_handoff = bool(getattr(cfg, "world_shell_audio_handoff", True))
        self.audio_handoff_strength = max(0.0, min(1.0, float(getattr(cfg, "world_shell_audio_handoff_strength", BIOME_DEFAULT_AUDIO_HANDOFF_STRENGTH) or BIOME_DEFAULT_AUDIO_HANDOFF_STRENGTH)))
        self.ambience_radius = max(112.0, min(1400.0, float(getattr(cfg, "world_shell_ambience_radius", BIOME_DEFAULT_AMBIENCE_RADIUS) or BIOME_DEFAULT_AMBIENCE_RADIUS)))
        self.playable_enabled = bool(getattr(cfg, "world_shell_playable_enabled", True))
        outer_default = max(BIOME_ENTRY_GROUND_END_RADIUS, self.scaled_radius(BIOME_RINGS[-1]["r1"]) + 8.0)
        # Pass 36: full-scale HoloVerse shell. Do not clamp play radius back to the tiny adapter shell.
        requested_radius = float(getattr(cfg, "world_shell_play_radius", outer_default) or outer_default)
        self.playable_radius = max(BIOME_ENTRY_GROUND_END_RADIUS, min(max(outer_default, BIOME_DEFAULT_PLAY_RADIUS), requested_radius))
        self.play_speed_scale = max(0.75, min(1.80, float(getattr(cfg, "world_shell_play_speed_scale", BIOME_DEFAULT_PLAY_SPEED_SCALE) or BIOME_DEFAULT_PLAY_SPEED_SCALE)))
        self.play_floor_enabled = bool(getattr(cfg, "world_shell_play_floor_enabled", True))
        self.world_py_source_bridge = bool(getattr(cfg, "world_shell_use_world_py_source", BIOME_DEFAULT_WORLD_PY_SOURCE_BRIDGE))
        self.boundary_feedback = bool(getattr(cfg, "world_shell_boundary_feedback", True))
        self.boundary_warning_distance = max(8.0, min(72.0, float(getattr(cfg, "world_shell_boundary_warning_distance", BIOME_DEFAULT_BOUNDARY_WARNING_DISTANCE) or BIOME_DEFAULT_BOUNDARY_WARNING_DISTANCE)))
        self.checkpoint_enabled = bool(getattr(cfg, "world_shell_checkpoint_enabled", True))
        self.checkpoint_count = max(0, min(32, int(getattr(cfg, "world_shell_checkpoint_count", BIOME_DEFAULT_CHECKPOINT_COUNT) or BIOME_DEFAULT_CHECKPOINT_COUNT)))
        self.checkpoint_pickup_radius = max(2.0, min(9.5, float(getattr(cfg, "world_shell_checkpoint_pickup_radius", BIOME_DEFAULT_CHECKPOINT_PICKUP_RADIUS) or BIOME_DEFAULT_CHECKPOINT_PICKUP_RADIUS)))
        return self.option_signature()

    def option_signature(self):
        return (
            int(self.active_key), round(float(self.scale), 5), self.detail,
            int(self.stream_radius), bool(self.default_preload), bool(self.preload_all_biomes),
            bool(self.preload_corridors), int(self.preload_sector_radius), int(self.max_preloaded_sectors),
            bool(self.exit_gate_hints), bool(self.entry_ribbons), bool(self.transition_cues),
            bool(self.first_ring_props), int(self.first_ring_prop_count),
            bool(self.ground_continuity), int(self.ground_band_count),
            bool(self.scale_handoff_markers), bool(self.collision_height_hints),
            bool(self.local_detail_boost), int(self.biome_signature_density),
            bool(self.directional_feedback), int(self.direction_marker_count),
            bool(self.corridor_theming), bool(self.theme_handoff), round(float(self.theme_handoff_strength), 3),
            bool(self.hub_theme_influence), round(float(self.hub_theme_max_blend), 3),
            round(float(self.hub_theme_fog_blend), 3), round(float(self.hub_theme_light_blend), 3),
            bool(self.status_prompts), bool(self.motion_enabled), round(float(self.motion_intensity), 3),
            bool(self.audio_handoff), round(float(self.audio_handoff_strength), 3), round(float(self.ambience_radius), 2),
            bool(self.playable_enabled), round(float(self.playable_radius), 2),
            round(float(self.play_speed_scale), 3), bool(self.play_floor_enabled),
            bool(self.world_py_source_bridge),
            bool(self.boundary_feedback), round(float(self.boundary_warning_distance), 2),
            bool(self.checkpoint_enabled), int(self.checkpoint_count), round(float(self.checkpoint_pickup_radius), 2),
        )

    def ring_for_key(self, key):
        for ring in BIOME_RINGS:
            if int(ring["key"]) == int(key):
                return ring
        return None

    def ring_for_radius(self, radius):
        real_radius = max(0.0, float(radius) / max(0.0001, self.scale))
        # Inner-most bug guard: the hub/flat layer owns everything inside its outer radius.
        first = BIOME_RINGS[0]
        if real_radius < float(first.get("r1", 620.0)):
            return first
        for ring in BIOME_RINGS:
            if float(ring["r0"]) <= real_radius < float(ring["r1"]):
                return ring
        return BIOME_RINGS[-1]

    def active_ring(self):
        return self.ring_for_key(self.active_key) or BIOME_RINGS[0]

    def active_biome_name(self):
        try:
            checker = getattr(self.app, "is_holospace_active", None)
            if callable(checker) and checker():
                return "HoloSpace"
        except Exception:
            pass
        return str(self.active_ring().get("name", "FLAT"))

    def scaled_radius(self, value):
        return max(26.0, float(value) * self.scale)

    def points_on_arc(self, radius, a0, a1, z, steps=12):
        return [Vec3(math.cos(a0 + (a1 - a0) * i / max(1, steps)) * radius,
                     math.sin(a0 + (a1 - a0) * i / max(1, steps)) * radius,
                     z) for i in range(steps + 1)]

    def polar_point(self, radius, angle, z=0.0):
        return Vec3(math.cos(angle) * radius, math.sin(angle) * radius, z)

    def polar_frame(self, angle):
        return Vec3(math.cos(angle), math.sin(angle), 0), Vec3(-math.sin(angle), math.cos(angle), 0)

    def poly(self, points, color, thickness=0.40, closed=False, name="world-shell-poly"):
        node = self.app.add_polyline(self.root, points, color, self.app.cfg.line_thickness * thickness, closed, name)
        if node is not None:
            try:
                node.setTransparency(TransparencyAttrib.MAlpha)
            except Exception:
                pass
            self.nodes.append(node)
        return node


    def _load_world_source_module(self):
        """Import definitions from world.py without running its main()."""
        path = ADAPTER_ROOT / "world.py"
        if not path.exists():
            self.source_bridge_status = "world.py missing"
            return None
        module_name = "_holoverse_world_py_source_bridge"
        cached = sys.modules.get(module_name)
        if cached is not None and str(getattr(cached, "__file__", "")) == str(path):
            return cached
        try:
            spec = importlib.util.spec_from_file_location(module_name, path)
            if spec is None or spec.loader is None:
                self.source_bridge_status = "import spec unavailable"
                return None
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
            return module
        except Exception as exc:
            sys.modules.pop(module_name, None)
            self.source_bridge_status = f"import failed: {exc.__class__.__name__}"
            return None

    def try_build_world_py_source_bridge(self):
        """Build the real world.py visual/runtime helpers around the hub."""
        self.source_bridge_active = False
        self.source_runtime = None
        self.source_bridge_report = {}
        if not self.world_py_source_bridge:
            self.source_bridge_status = "disabled"
            return False
        module = self._load_world_source_module()
        if module is None:
            return False
        if getattr(module, "CommandHubApp", None) is None:
            self.source_bridge_status = "CommandHubApp missing"
            return False
        try:
            runtime = _WorldPyHost(self, module)
            report = runtime.build_initial_world()
            completed = set(report.get("completed", [])) if isinstance(report, dict) else set()
            if not ({"build_flatland_disk", "build_biome_ring_framework"} & completed):
                self.source_bridge_status = "source bridge incomplete"
                self.source_bridge_report = report if isinstance(report, dict) else {"error": "unknown"}
                try:
                    runtime._source_root.removeNode()
                except Exception:
                    pass
                return False
            self.source_runtime = runtime
            self.source_bridge_active = True
            self.source_bridge_status = "active"
            self.source_bridge_report = report if isinstance(report, dict) else {}
            # Pass 89: source bridge owns the world visuals. Do not stack the
            # legacy Pass45/46 shell-beauty layer on top of world.py; that was a
            # second world-like overlay and a major source of duplicate infill.
            self.clear_pass45_beauty_layer()
            try:
                self.purge_retired_water_nodes()
            except Exception:
                pass
            self.retired_water_purge_done = True
            self.default_preloaded = True
            self.status = "PRELOADED // SINGLE SOURCE WORLD.PY AUTHORITY"
            self.write_state()
            return True
        except Exception as exc:
            self.source_bridge_status = f"source bridge error: {exc.__class__.__name__}"
            self.source_bridge_report = {"error": str(exc)}
            self.source_runtime = None
            self.source_bridge_active = False
            return False

    def rebuild_static(self):
        self.read_mount_options()
        self.destroy()
        if self.detail == "off":
            self.status = "OFF"
            self.write_state()
            return
        # Attach to the persistent 3D root instead of world_root. world_root is
        # hidden whenever no artifact world is active, which made the default
        # shell disappear during normal hub play.
        parent = getattr(self.app, "root_3d", None) or getattr(self.app, "render", None) or getattr(self.app, "world_root", None) or self.app.render
        self.root = parent.attachNewNode("default-holoverse-full-world-shell-root")
        self.static_root = self.root.attachNewNode("world-shell-static")
        self.stream_root = self.root.attachNewNode("world-shell-stream")
        self.root.setTransparency(TransparencyAttrib.MAlpha)
        try:
            self.root.setBin("background", 14)
        except Exception:
            pass
        if self.try_build_world_py_source_bridge():
            return
        # Ring boundaries from the older shell stay full-circle so the whole world
        # silhouette surrounds the observatory even when detailed sectors are capped.
        for ring in BIOME_RINGS:
            key = int(ring["key"])
            color = list(ring["color"])
            if key == self.active_key:
                color[3] = min(0.78, color[3] + 0.35)
            radius = self.scaled_radius(ring["r1"])
            z = 0.16 + key * 0.055
            self.poly(self.points_on_arc(radius, 0, math.tau, z, 128), tuple(color), 0.34 if key != self.active_key else 0.68, True, f"world-shell-ring-{ring['kind']}")
        for deg in BIOME_HUB_CORRIDOR_DEGREES:
            a = math.radians(deg)
            pts = [Vec3(math.cos(a) * 31.0, math.sin(a) * 31.0, 0.28), Vec3(math.cos(a) * self.scaled_radius(BIOME_RINGS[-1]["r1"]), math.sin(a) * self.scaled_radius(BIOME_RINGS[-1]["r1"]), 0.28)]
            self.poly(pts, (0.64, 0.86, 1.0, 0.18), 0.22, False, "world-shell-corridor")
        for idx, (name, key) in enumerate(REGION_BOTS):
            ring = self.ring_for_key(key)
            if ring is None:
                continue
            rr = (self.scaled_radius(ring["r0"]) + self.scaled_radius(ring["r1"])) * 0.5
            angle = math.radians(-90 + idx * 37)
            pos = Vec3(math.cos(angle) * rr, math.sin(angle) * rr, 1.0 + (idx % 3) * 0.28)
            size = 0.48 if key != self.active_key else 0.80
            try:
                self.app.add_box(self.root, pos, Vec3(size, size, size * 1.6), (ring["color"][0], ring["color"][1], ring["color"][2], 0.42 if key != self.active_key else 0.74), 0.22)
            except Exception:
                pass
        if self.exit_gate_hints:
            self.build_hub_exit_gate_hints()
        if self.entry_ribbons:
            self.build_entry_ribbons()
        if self.transition_cues:
            self.build_transition_cues()
        if self.ground_continuity:
            self.build_entry_ground_continuity()
        if self.scale_handoff_markers:
            self.build_scale_handoff_markers()
        if self.collision_height_hints:
            self.build_collision_height_hints()
        if self.directional_feedback:
            self.build_directional_feedback_guides()
        if self.corridor_theming:
            self.build_biome_corridor_themes()
        if self.first_ring_props:
            self.build_first_ring_ambient_props()
        if self.motion_enabled:
            self.build_motion_guide_nodes()
        if self.boundary_feedback:
            self.build_play_boundary_feedback()
        if self.checkpoint_enabled:
            self.build_shell_checkpoints()
        self.build_pass45_beauty_layer()
        self.force_refresh = True
        self.update_stream(force=True)
        self.update_theme_handoff_data()
        self.default_preloaded = bool(self.default_preload and self.preload_all_biomes and len({k[0] for k in self.sector_nodes}) >= len(BIOME_RINGS))
        self.status = "PRELOADED // HOLOVERSE DEFAULT WORLD READY" if self.default_preloaded else "MOUNTED // FULL-SCALE STREAM READY"
        self.write_state()

    def build_hub_exit_gate_hints(self):
        """Add readable low-cost gates where hub corridors enter each biome ring."""
        if self.root is None:
            return
        for deg in BIOME_HUB_CORRIDOR_DEGREES:
            angle = math.radians(deg)
            radial, tangent = self.polar_frame(angle)
            # A short threshold marker just outside the observatory reinforces that
            # the HoloVerse world is already loaded around the hub.
            near_a = self.polar_point(30.8, angle, 0.72)
            near_b = self.polar_point(37.2, angle, 0.72)
            self.poly([near_a, near_b], (0.78, 0.92, 1.0, 0.44), 0.34, False, "world-shell-hub-threshold")
            for ring in BIOME_RINGS:
                key = int(ring["key"])
                color = ring["color"]
                gate_r = max(35.0, self.scaled_radius(ring["r0"]) + 0.9)
                if key == 1:
                    gate_r = 33.5
                height = 0.72 + key * 0.12
                width = 0.62 + min(1.8, key * 0.12)
                base = self.polar_point(gate_r, angle, 0.72 + key * 0.03)
                left = base + tangent * width
                right = base - tangent * width
                try:
                    self.app.add_box(self.root, left, Vec3(0.24, 0.24, height), (color[0], color[1], color[2], 0.34), 0.12)
                    self.app.add_box(self.root, right, Vec3(0.24, 0.24, height), (color[0], color[1], color[2], 0.34), 0.12)
                except Exception:
                    pass
                top = base + Vec3(0, 0, height + 0.26)
                self.poly([left + Vec3(0, 0, height + 0.10), top, right + Vec3(0, 0, height + 0.10)], (color[0], color[1], color[2], 0.40), 0.18, False, "world-shell-biome-gate-arch")
                if key in {2, 4, 6, 8}:
                    lead0 = base - radial * 2.8
                    lead1 = base + radial * 3.8
                    self.poly([lead0 + tangent * (width * 0.48), lead1 + tangent * (width * 0.48)], (color[0], color[1], color[2], 0.18), 0.12, False, "world-shell-gate-guide")
                    self.poly([lead0 - tangent * (width * 0.48), lead1 - tangent * (width * 0.48)], (color[0], color[1], color[2], 0.18), 0.12, False, "world-shell-gate-guide")

    def build_entry_ribbons(self):
        """Draw low, walkable-looking ribbons from hub exits into the shell.

        These are visual guide lanes only.  They do not change hub collision, but
        they solve the current shell-readability problem where the innermost
        scaled biome can look too thin around the observatory.
        """
        if self.root is None:
            return
        for deg in BIOME_HUB_CORRIDOR_DEGREES:
            angle = math.radians(deg)
            radial, tangent = self.polar_frame(angle)
            for lane_index, side in enumerate((-1, 1)):
                pts = []
                for i in range(8):
                    t = i / 7.0
                    rr = 30.0 + t * 36.0
                    width = 1.0 + t * 3.8
                    lift = 0.42 + t * 0.20 + math.sin(t * math.tau * 1.5 + lane_index) * 0.035
                    pts.append(self.polar_point(rr, angle, lift) + tangent * (side * width))
                self.poly(pts, (0.62, 0.90, 1.0, 0.34), 0.16, False, "world-shell-entry-ribbon-edge")
            center_pts = [self.polar_point(31.0 + i * 5.0, angle, 0.48 + i * 0.015) for i in range(8)]
            self.poly(center_pts, (0.92, 0.98, 1.0, 0.18), 0.10, False, "world-shell-entry-ribbon-center")
            for i in range(4):
                rr = 36.0 + i * 7.0
                half = 0.95 + i * 0.54
                center = self.polar_point(rr, angle, 0.56 + i * 0.035)
                self.poly([center - tangent * half, center + radial * 1.6, center + tangent * half], (0.82, 0.96, 1.0, 0.20), 0.11, False, "world-shell-entry-chevron")

    def build_transition_cues(self):
        """Add compact boundary cues so biome changes read before full traversal."""
        if self.root is None:
            return
        for ring in BIOME_RINGS[1:]:
            color = ring["color"]
            key = int(ring["key"])
            boundary_r = max(36.0 + key * 4.0, self.scaled_radius(ring["r0"]) + 1.5)
            z = 0.66 + key * 0.04
            # Short glow arcs on each cardinal approach, cheaper than full dense rings.
            for deg in BIOME_HUB_CORRIDOR_DEGREES:
                angle = math.radians(deg)
                a0 = angle - 0.032
                a1 = angle + 0.032
                self.poly(self.points_on_arc(boundary_r, a0, a1, z, 5), (color[0], color[1], color[2], 0.34), 0.18, False, "world-shell-biome-transition-arc")
                radial, tangent = self.polar_frame(angle)
                base = self.polar_point(boundary_r, angle, z + 0.06)
                for side in (-1, 1):
                    inner = base + tangent * (side * 1.15) - radial * 1.2
                    outer = base + tangent * (side * 1.95) + radial * 1.1
                    self.poly([inner, base + radial * 1.6, outer], (color[0], color[1], color[2], 0.24), 0.10, False, "world-shell-transition-bracket")

    def build_entry_ground_continuity(self):
        """Draw visual floor continuity from the observatory into the preloaded shell.

        This does not own collision or terrain. It gives the player a readable
        low-altitude surface handoff from the hub floor to the first streamed
        shell sectors while the hub remains authoritative.
        """
        if self.root is None:
            return
        band_count = max(2, min(8, int(self.ground_band_count)))
        start_r = BIOME_ENTRY_GROUND_START_RADIUS
        end_r = BIOME_ENTRY_GROUND_END_RADIUS
        for deg in BIOME_HUB_CORRIDOR_DEGREES:
            angle = math.radians(deg)
            radial, tangent = self.polar_frame(angle)
            lane_edges = (-1.0, 0.0, 1.0)
            for edge in lane_edges:
                pts = []
                for i in range(band_count + 1):
                    t = i / float(band_count)
                    rr = start_r + (end_r - start_r) * t
                    width = 1.1 + t * 5.4
                    z = 0.34 + t * 0.18
                    pts.append(self.polar_point(rr, angle, z) + tangent * (edge * width))
                alpha = 0.26 if edge else 0.17
                thick = 0.12 if edge else 0.08
                self.poly(pts, (0.84, 0.95, 1.0, alpha), thick, False, "world-shell-ground-continuity-spine")
            for i in range(1, band_count + 1):
                t = i / float(band_count)
                rr = start_r + (end_r - start_r) * t
                width = 1.25 + t * 5.4
                z = 0.36 + t * 0.18
                center = self.polar_point(rr, angle, z)
                # Cross ribs and a small forward notch make the lane read as a
                # surface without creating a filled polygon or new collision plane.
                self.poly([center - tangent * width, center + tangent * width], (0.66, 0.90, 1.0, 0.22), 0.10, False, "world-shell-ground-continuity-rib")
                self.poly([center - tangent * (width * 0.44), center + radial * 1.45, center + tangent * (width * 0.44)], (0.96, 0.98, 1.0, 0.14), 0.075, False, "world-shell-ground-continuity-notch")

    def build_scale_handoff_markers(self):
        """Add increasing marker ticks so the shell scale feels connected to the hub."""
        if self.root is None:
            return
        for deg in BIOME_HUB_CORRIDOR_DEGREES:
            angle = math.radians(deg)
            radial, tangent = self.polar_frame(angle)
            for idx, rr in enumerate(BIOME_SCALE_HANDOFF_RADII):
                t = idx / max(1, len(BIOME_SCALE_HANDOFF_RADII) - 1)
                marker_half = 1.2 + t * 2.4
                z = 0.72 + t * 0.22
                alpha = 0.24 + t * 0.10
                center = self.polar_point(rr, angle, z)
                self.poly([center - tangent * marker_half, center + tangent * marker_half], (0.78, 0.94, 1.0, alpha), 0.11 + t * 0.025, False, "world-shell-scale-handoff-tick")
                try:
                    for side in (-1, 1):
                        self.app.add_box(self.root, center + tangent * (side * marker_half), Vec3(0.18 + t * 0.08, 0.18 + t * 0.08, 0.32 + t * 0.32), (0.72, 0.90, 1.0, 0.18 + t * 0.10), 0.05)
                except Exception:
                    pass

    def build_collision_height_hints(self):
        """Draw non-authoritative clearance rails for future collision/height work."""
        if self.root is None:
            return
        eye_h = max(2.0, min(6.0, float(getattr(self.app.cfg, "player_eye_height", 3.95) or 3.95)))
        rail_z = max(0.95, eye_h * 0.34)
        arch_top = max(2.4, eye_h * 0.72)
        for deg in BIOME_HUB_CORRIDOR_DEGREES:
            angle = math.radians(deg)
            radial, tangent = self.polar_frame(angle)
            for side in (-1, 1):
                pts = []
                for rr in (36.0, 50.0, 66.0, 82.0):
                    t = (rr - 36.0) / max(1.0, 82.0 - 36.0)
                    pts.append(self.polar_point(rr, angle, rail_z + t * 0.10) + tangent * (side * (2.5 + t * 3.8)))
                self.poly(pts, (1.0, 0.86, 0.42, 0.20), 0.075, False, "world-shell-height-clearance-rail")
            for rr in (44.0, 68.0, 88.0):
                width = 2.5 + (rr - 44.0) * 0.055
                base = self.polar_point(rr, angle, 0.62)
                left = base - tangent * width
                right = base + tangent * width
                self.poly([left, left + Vec3(0, 0, arch_top), right + Vec3(0, 0, arch_top), right], (1.0, 0.82, 0.32, 0.16), 0.065, False, "world-shell-height-clearance-arch")

    def build_first_ring_ambient_props(self):
        """Populate the nearby default shell with bounded small ambient silhouettes."""
        if self.root is None or self.first_ring_prop_count <= 0:
            return
        rng = random.Random(self.seed + 29029)
        count = max(0, min(32, int(self.first_ring_prop_count)))
        for i in range(count):
            deg = BIOME_HUB_CORRIDOR_DEGREES[i % len(BIOME_HUB_CORRIDOR_DEGREES)] + rng.uniform(-13.0, 13.0)
            angle = math.radians(deg)
            radial, tangent = self.polar_frame(angle)
            rr = rng.uniform(39.0, 72.0)
            p = self.polar_point(rr, angle, 0.74 + rng.uniform(-0.05, 0.16)) + tangent * rng.uniform(-4.0, 4.0)
            family = i % 4
            if family == 0:
                height = rng.uniform(1.0, 1.8)
                self.poly([p, p + Vec3(0, 0, height)], (0.55, 1.0, 0.46, 0.32), 0.12, False, "world-shell-nearby-sapling")
                self.poly([p + Vec3(-0.45, 0, height * 0.70), p + Vec3(0, 0, height), p + Vec3(0.45, 0, height * 0.70)], (0.48, 1.0, 0.40, 0.28), 0.10, False, "world-shell-nearby-canopy")
            elif family == 1:
                self.poly([p - tangent * 0.72, p + tangent * 0.72], (0.20, 0.95, 1.0, 0.30), 0.10, False, "world-shell-nearby-water-rune")
                self.poly([p - radial * 0.46, p + radial * 0.46], (0.20, 0.95, 1.0, 0.22), 0.08, False, "world-shell-nearby-water-rune")
            elif family == 2:
                try:
                    self.app.add_box(self.root, p + Vec3(0, 0, 0.38), Vec3(0.34, 0.34, 0.76), (0.92, 0.96, 1.0, 0.24), 0.06)
                except Exception:
                    pass
                self.poly([p, p + Vec3(0.30, 0.18, 0.96), p + Vec3(-0.22, -0.28, 1.20)], (0.82, 0.96, 1.0, 0.26), 0.08, False, "world-shell-nearby-crystal")
            else:
                try:
                    self.app.add_box(self.root, p + Vec3(0, 0, 0.30), Vec3(0.52, 0.52, 0.60), (0.78, 0.80, 0.84, 0.20), 0.06)
                except Exception:
                    pass
                self.poly([p - tangent * 0.62, p + Vec3(0, 0, 0.78), p + tangent * 0.62], (0.78, 0.80, 0.84, 0.22), 0.08, False, "world-shell-nearby-ruin")

    def ring_at_scaled_radius(self, scaled_radius):
        real_radius = max(0.0, float(scaled_radius) / max(0.0001, self.scale))
        return self.ring_for_radius(real_radius * self.scale)

    def build_directional_feedback_guides(self):
        """Add outward-facing chevrons that make traversal away from the hub readable."""
        if self.root is None:
            return
        count = max(2, min(10, int(self.direction_marker_count)))
        for deg in BIOME_HUB_CORRIDOR_DEGREES:
            angle = math.radians(deg)
            radial, tangent = self.polar_frame(angle)
            for i in range(count):
                t = i / float(max(1, count - 1))
                rr = 38.0 + t * 108.0
                ring = self.ring_for_radius(rr)
                color = ring.get("color", (0.72, 0.90, 1.0, 0.26))
                width = 1.15 + t * 4.35
                reach = 1.60 + t * 2.55
                z = 0.84 + t * 0.36
                center = self.polar_point(rr, angle, z)
                alpha = 0.18 + t * 0.18
                self.poly([center - tangent * width, center + radial * reach, center + tangent * width], (color[0], color[1], color[2], alpha), 0.10 + t * 0.035, False, "world-shell-outward-direction-chevron")
                if i % 2 == 0:
                    tail = center - radial * (reach * 0.70)
                    self.poly([tail, center + radial * (reach * 0.45)], (color[0], color[1], color[2], alpha * 0.72), 0.065, False, "world-shell-outward-direction-tail")

    def build_biome_corridor_themes(self):
        """Tint corridor lanes by biome band so exits preview the surrounding world."""
        if self.root is None:
            return
        for deg in BIOME_HUB_CORRIDOR_DEGREES:
            angle = math.radians(deg)
            radial, tangent = self.polar_frame(angle)
            for ring in BIOME_RINGS:
                key = int(ring["key"])
                color = ring["color"]
                inner = max(32.5 + key * 1.4, self.scaled_radius(ring["r0"]) + 1.0)
                outer = max(inner + 8.0, min(self.scaled_radius(ring["r1"]) - 1.0, inner + 34.0))
                if key == 1:
                    inner, outer = 33.0, 64.0
                samples = 5
                for side in (-1, 1):
                    pts = []
                    for i in range(samples):
                        t = i / float(samples - 1)
                        rr = inner + (outer - inner) * t
                        width = 2.0 + min(5.5, key * 0.42) + t * 1.2
                        z = 0.46 + key * 0.035 + t * 0.04
                        pts.append(self.polar_point(rr, angle, z) + tangent * (side * width))
                    self.poly(pts, (color[0], color[1], color[2], 0.16 + key * 0.012), 0.075 + min(0.05, key * 0.006), False, "world-shell-biome-corridor-theme-rail")
                for t in (0.34, 0.68):
                    rr = inner + (outer - inner) * t
                    center = self.polar_point(rr, angle, 0.60 + key * 0.035)
                    half = 1.35 + min(4.8, key * 0.34)
                    self.poly([center - tangent * half, center + tangent * half], (color[0], color[1], color[2], 0.12 + key * 0.010), 0.060, False, "world-shell-biome-corridor-theme-crossbar")

    def build_motion_guide_nodes(self):
        """Add a few tiny animated guide nodes without increasing sector density."""
        if self.root is None:
            return
        self.motion_nodes = []
        rng = random.Random(self.seed + 33133)
        for idx, deg in enumerate(BIOME_HUB_CORRIDOR_DEGREES):
            angle = math.radians(deg)
            radial, tangent = self.polar_frame(angle)
            for step in range(3):
                rr = 44.0 + step * 18.0
                ring = self.ring_for_radius(rr)
                color = ring.get("color", (0.72, 0.90, 1.0, 0.24))
                center = self.polar_point(rr, angle, 1.05 + step * 0.18)
                flutter = center + tangent * rng.uniform(-2.0, 2.0)
                node = self.app.add_polyline(
                    self.root,
                    [flutter - radial * 0.72, flutter + Vec3(0, 0, 0.42), flutter + radial * 0.72],
                    (color[0], color[1], color[2], 0.20 + step * 0.035),
                    self.app.cfg.line_thickness * (0.06 + step * 0.010),
                    False,
                    "world-shell-motion-guide",
                )
                if node is not None:
                    try:
                        node.setPythonTag("world_shell_motion_phase", idx * 0.73 + step * 0.91)
                        node.setPythonTag("world_shell_motion_base_z", float(flutter.z))
                        node.setPythonTag("world_shell_motion_base_alpha", 0.20 + step * 0.035)
                        node.setPythonTag("world_shell_motion_color", (float(color[0]), float(color[1]), float(color[2])))
                    except Exception:
                        pass
                    self.motion_nodes.append(node)

    def build_play_boundary_feedback(self):
        """Draw a soft edge fence for the playable shell radius.

        The fence is visual-only; the hub still owns the actual movement clamp.
        It gives the player a readable edge before movement is blocked.
        """
        if self.root is None:
            return
        outer = self.playable_outer_radius()
        warn = max(8.0, float(self.boundary_warning_distance))
        inner = max(BIOME_ENTRY_GROUND_END_RADIUS, outer - warn)
        for radius, alpha, thick, z in (
            (inner, 0.18, 0.12, 0.70),
            (outer - warn * 0.48, 0.24, 0.16, 0.84),
            (outer, 0.42, 0.24, 1.02),
        ):
            self.poly(self.points_on_arc(radius, 0, math.tau, z, 144), (0.92, 0.98, 1.0, alpha), thick, True, "world-shell-play-boundary-ring")
        for deg in range(0, 360, 15):
            angle = math.radians(deg)
            radial, tangent = self.polar_frame(angle)
            ring = self.ring_for_radius(outer)
            color = ring.get("color", (0.82, 0.94, 1.0, 0.32))
            base = self.polar_point(outer, angle, 0.92)
            tick_h = 0.42 + (0.28 if deg % 45 == 0 else 0.0)
            self.poly([base - radial * 1.5, base + radial * 1.5], (color[0], color[1], color[2], 0.30), 0.08, False, "world-shell-play-boundary-tick")
            if deg % 45 == 0:
                self.poly([base - tangent * 1.3, base + Vec3(0, 0, tick_h), base + tangent * 1.3], (color[0], color[1], color[2], 0.34), 0.10, False, "world-shell-play-boundary-pillar")

    def build_shell_checkpoints(self):
        """Add lightweight claimable shell checkpoints along hub corridors."""
        if self.root is None or self.checkpoint_count <= 0:
            return
        self.checkpoint_nodes = {}
        self.checkpoint_data = []
        outer = max(BIOME_ENTRY_GROUND_END_RADIUS + 12.0, self.playable_outer_radius() - 22.0)
        start = BIOME_ENTRY_GROUND_END_RADIUS + 8.0
        count = max(0, int(self.checkpoint_count))
        if count <= 0:
            return
        ring_count = ((count - 1) // len(BIOME_HUB_CORRIDOR_DEGREES)) + 1
        for idx in range(count):
            deg = BIOME_HUB_CORRIDOR_DEGREES[idx % len(BIOME_HUB_CORRIDOR_DEGREES)]
            lane = idx // len(BIOME_HUB_CORRIDOR_DEGREES)
            ring_t = (lane + 1) / float(ring_count + 1)
            rr = start + (outer - start) * ring_t
            angle = math.radians(deg + (-4.0 if idx % 2 else 4.0))
            _radial, tangent = self.polar_frame(angle)
            ring = self.ring_for_radius(rr)
            color = ring.get("color", (0.82, 0.96, 1.0, 0.34))
            pos = self.polar_point(rr, angle, 1.28 + (idx % 3) * 0.05) + tangent * (1.4 if idx % 2 else -1.4)
            cid = f"shell-cp-{idx:02d}"
            node = self.root.attachNewNode(cid)
            try:
                self.app.add_polyline(
                    node,
                    [pos + Vec3(0, 0, 0.62), pos + tangent * 1.0, pos + Vec3(0, 0, -0.62), pos - tangent * 1.0],
                    (color[0], color[1], color[2], 0.48),
                    self.app.cfg.line_thickness * 0.16,
                    True,
                    "world-shell-checkpoint-diamond",
                )
                self.app.add_box(node, pos, Vec3(0.72, 0.72, 0.72), (color[0], color[1], color[2], 0.36), 0.10)
                node.setTransparency(TransparencyAttrib.MAlpha)
                node.setPythonTag("world_shell_checkpoint_id", cid)
                if cid in self.claimed_checkpoints:
                    node.hide()
            except Exception:
                pass
            self.checkpoint_nodes[cid] = node
            self.checkpoint_data.append({
                "id": cid,
                "index": idx,
                "position": [round(float(pos.x), 3), round(float(pos.y), 3), round(float(pos.z), 3)],
                "radius": round(float(rr), 2),
                "sector": int(self.sector_for_angle_deg(math.degrees(angle))),
                "biome_key": int(ring.get("key", 1)),
                "biome": str(ring.get("name", "FLAT")),
                "kind": str(ring.get("kind", "flat")),
                "pickup_radius": round(float(self.checkpoint_pickup_radius), 2),
                "claimed": bool(cid in self.claimed_checkpoints),
            })

    def set_checkpoint_claimed(self, checkpoint_id: str, claimed: bool = True):
        cid = str(checkpoint_id or "").strip()
        if not cid:
            return
        if claimed:
            self.claimed_checkpoints.add(cid)
        else:
            self.claimed_checkpoints.discard(cid)
        node = self.checkpoint_nodes.get(cid)
        try:
            if node is not None and not node.isEmpty():
                node.hide() if claimed else node.show()
        except Exception:
            pass
        for item in self.checkpoint_data:
            if item.get("id") == cid:
                item["claimed"] = bool(claimed)

    def checkpoint_payload(self):
        claimed = set(self.claimed_checkpoints)
        out = []
        for item in self.checkpoint_data:
            cp = dict(item)
            cp["claimed"] = bool(cp.get("id") in claimed or cp.get("claimed"))
            out.append(cp)
        return out

    def update_motion_guides(self, dt):
        """Pulse existing shell nodes lightly so the default world feels alive."""
        del dt
        if not self.motion_enabled:
            return
        t = float(getattr(self.app, "elapsed", 0.0))
        intensity = max(0.0, min(1.0, float(self.motion_intensity)))
        if intensity <= 0.001:
            return
        for key, node in list(self.sector_nodes.items()):
            try:
                if node is None or node.isEmpty():
                    continue
                phase = float(node.getPythonTag("world_shell_motion_phase") or 0.0)
                strength = float(node.getPythonTag("world_shell_motion_strength") or 0.25)
                pulse = 1.0 + math.sin(t * 0.80 + phase) * 0.035 * intensity * strength
                alpha = 0.92 + math.sin(t * 0.55 + phase * 1.7) * 0.055 * intensity * strength
                node.setScale(pulse)
                node.setColorScale(1.0, 1.0, 1.0, max(0.72, min(1.0, alpha)))
            except Exception:
                pass
        for node in list(self.motion_nodes):
            try:
                if node is None or node.isEmpty():
                    continue
                phase = float(node.getPythonTag("world_shell_motion_phase") or 0.0)
                base_z = float(node.getPythonTag("world_shell_motion_base_z") or node.getZ())
                base_alpha = float(node.getPythonTag("world_shell_motion_base_alpha") or 0.22)
                color = node.getPythonTag("world_shell_motion_color") or (0.72, 0.90, 1.0)
                bob = math.sin(t * 1.25 + phase) * 0.14 * intensity
                alpha = max(0.05, min(0.52, base_alpha + math.sin(t * 1.5 + phase) * 0.07 * intensity))
                node.setZ(base_z + bob)
                node.setColorScale(float(color[0]), float(color[1]), float(color[2]), alpha)
            except Exception:
                pass

    def update_shell_prompt_data(self):
        """Build a compact status prompt for the hub menu/HUD without adding UI clutter."""
        if not self.status_prompts:
            self.shell_prompt = "HOLOVERSE READY"
            return self.shell_prompt
        radius, _angle, sector = self.player_polar()
        ring = self.ring_for_radius(radius)
        kind = str(ring.get("kind", "flat")).replace("_", " ").upper()
        corridor_sectors = [self.sector_for_angle_deg(deg) for deg in BIOME_HUB_CORRIDOR_DEGREES]
        nearest = min(corridor_sectors, key=lambda c: self.sector_distance(c, sector)) if corridor_sectors else sector
        corridor_delta = self.sector_distance(nearest, sector)
        outer = self.playable_outer_radius()
        if self.boundary_feedback and (outer - radius) <= float(self.boundary_warning_distance):
            prefix = "SHELL EDGE"
        elif radius < BIOME_ENTRY_GROUND_START_RADIUS:
            prefix = "HUB ANCHOR"
        elif corridor_delta <= 1:
            prefix = "EXIT CORRIDOR"
        else:
            prefix = "SHELL FIELD"
        self.shell_prompt = f"{prefix} // {str(ring.get('name', kind)).upper()} // R{int(radius):03d}"
        return self.shell_prompt

    def update_audio_handoff_data(self):
        """Export subtle ambience hints; hub decides whether/how to use them."""
        if not self.audio_handoff:
            self.audio_handoff_data = {"enabled": False, "authority": "disabled"}
            return self.audio_handoff_data
        radius, _angle, sector = self.player_polar()
        ring = self.ring_for_radius(radius)
        kind = str(ring.get("kind", "flat"))
        hint = BIOME_AUDIO_HINTS.get(kind, BIOME_AUDIO_HINTS["flat"])
        corridor_sectors = [self.sector_for_angle_deg(deg) for deg in BIOME_HUB_CORRIDOR_DEGREES]
        nearest = min(corridor_sectors, key=lambda c: self.sector_distance(c, sector)) if corridor_sectors else sector
        corridor_delta = self.sector_distance(nearest, sector)
        corridor_factor = 1.0 - min(1.0, corridor_delta / 3.0)
        radial_factor = smoothstep01((float(radius) - 24.0) / max(1.0, float(self.ambience_radius) - 24.0))
        falloff = 1.0 - smoothstep01(max(0.0, float(radius) - float(self.ambience_radius)) / max(1.0, float(self.ambience_radius)))
        influence = max(0.0, min(1.0, corridor_factor * radial_factor * falloff * float(self.audio_handoff_strength)))
        self.audio_handoff_data = {
            "enabled": True,
            "authority": "data_only_hub_ambience_gain_hint",
            "influence": round(influence, 3),
            "strength": round(float(self.audio_handoff_strength), 3),
            "ambience_radius": round(float(self.ambience_radius), 2),
            "active_key": int(ring["key"]),
            "active_biome": str(ring["name"]),
            "active_kind": kind,
            "sector": int(sector),
            "nearest_corridor_sector": int(nearest),
            "corridor_factor": round(corridor_factor, 3),
            "recommended_loop": str(hint.get("loop", "hv_hub_command_theme.wav")),
            "recommended_bus": str(hint.get("bus", "ambience")),
            "tone": str(hint.get("tone", "ambient hum")),
            "recommended_gain": round(0.48 + influence * 0.18, 3),
            "policy": "subtle_gain_only_no_forced_asset_swap",
        }
        return self.audio_handoff_data

    def update_theme_handoff_data(self):
        """Export light/fog influence data without taking over the hub renderer."""
        if not self.theme_handoff:
            self.theme_handoff_data = {"enabled": False, "authority": "disabled"}
            return self.theme_handoff_data
        radius, angle, sector = self.player_polar()
        ring = self.ring_for_radius(radius)
        kind = str(ring.get("kind", "flat"))
        color = ring.get("color", (0.72, 0.90, 1.0, 0.30))
        sky_rgb = BIOME_SKY_THEME_RGB.get(kind, (color[0], color[1], color[2]))
        fog_near, fog_far = BIOME_FOG_THEME.get(kind, (120.0, 420.0))
        strength = max(0.0, min(1.0, float(self.theme_handoff_strength)))
        distance_from_hub = max(0.0, float(radius) - BIOME_ENTRY_GROUND_START_RADIUS)
        influence = smoothstep01(min(1.0, distance_from_hub / max(1.0, BIOME_ENTRY_GROUND_END_RADIUS - BIOME_ENTRY_GROUND_START_RADIUS))) * strength
        corridor_sectors = [self.sector_for_angle_deg(deg) for deg in BIOME_HUB_CORRIDOR_DEGREES]
        nearest_corridor_sector = min(corridor_sectors, key=lambda c: self.sector_distance(c, sector)) if corridor_sectors else sector
        self.theme_handoff_data = {
            "enabled": True,
            "authority": "data_only_hub_subtle_blend_ready",
            "strength": round(strength, 3),
            "influence": round(influence, 3),
            "hub_theme_influence_enabled": bool(self.hub_theme_influence),
            "hub_theme_max_blend": round(float(self.hub_theme_max_blend), 3),
            "hub_theme_fog_blend": round(float(self.hub_theme_fog_blend), 3),
            "hub_theme_light_blend": round(float(self.hub_theme_light_blend), 3),
            "recommended_visual_blend": round(min(float(self.hub_theme_max_blend), influence), 3),
            "active_key": int(ring["key"]),
            "active_biome": str(ring["name"]),
            "active_kind": kind,
            "sector": int(sector),
            "nearest_corridor_sector": int(nearest_corridor_sector),
            "sky_rgb": [round(float(v), 4) for v in sky_rgb],
            "line_rgb": [round(float(color[i]), 4) for i in range(3)],
            "fog_near": round(float(fog_near), 2),
            "fog_far": round(float(fog_far), 2),
            "hub_safe_radius": float(BIOME_ENTRY_GROUND_START_RADIUS),
            "handoff_radius": float(BIOME_ENTRY_GROUND_END_RADIUS),
        }
        return self.theme_handoff_data

    def sector_span(self, sector):
        width = math.tau / float(BIOME_SECTOR_COUNT)
        a0 = (int(sector) % BIOME_SECTOR_COUNT) * width
        return a0, a0 + width

    def player_polar(self):
        pos = getattr(self.app, "player_pos", Vec3(0, -10, 0))
        radius = math.sqrt(pos.x * pos.x + pos.y * pos.y)
        angle = math.atan2(pos.y, pos.x) % math.tau
        sector = int(angle / (math.tau / BIOME_SECTOR_COUNT)) % BIOME_SECTOR_COUNT
        return radius, angle, sector

    def sector_for_angle_deg(self, angle_deg: float) -> int:
        angle = math.radians(float(angle_deg)) % math.tau
        return int(angle / (math.tau / BIOME_SECTOR_COUNT)) % BIOME_SECTOR_COUNT

    def sector_distance(self, a: int, b: int) -> int:
        diff = abs((int(a) % BIOME_SECTOR_COUNT) - (int(b) % BIOME_SECTOR_COUNT))
        return min(diff, BIOME_SECTOR_COUNT - diff)

    def wanted_sector_keys(self):
        try:
            checker = getattr(self.app, "is_holospace_active", None)
            if callable(checker) and checker():
                self.last_wanted = set()
                return set(), 0
        except Exception:
            pass
        radius, angle, center = self.player_polar()
        active_ring = self.ring_for_radius(radius)
        active_key = int(getattr(self.app.cfg, "world_shell_active_biome", self.active_key) or self.active_key)
        wanted: dict[tuple[int, int], int] = {}

        def add_sector(ring_key, sector, priority):
            key = (int(ring_key), int(sector) % BIOME_SECTOR_COUNT)
            prev = wanted.get(key)
            if prev is None or int(priority) < prev:
                wanted[key] = int(priority)

        # Always stream the true local/player sector plus the selected biome.
        local_ring_keys = {1, active_key, int(active_ring["key"])}
        for ring_key in local_ring_keys:
            for delta in range(-self.stream_radius, self.stream_radius + 1):
                add_sector(ring_key, center + delta, 0)

        # Pass 28 default preload: warm every biome ring around the hub-facing sector.
        if self.default_preload and self.preload_all_biomes:
            preload_radius = self.stream_radius + (1 if self.local_detail_boost else 0)
            for ring in BIOME_RINGS:
                for delta in range(-preload_radius, preload_radius + 1):
                    add_sector(int(ring["key"]), center + delta, 1)

        # Add tiny anchor windows on the four old fast-travel corridors.
        if self.default_preload and self.preload_corridors:
            for deg in BIOME_HUB_CORRIDOR_DEGREES:
                corridor_center = self.sector_for_angle_deg(deg)
                for ring in BIOME_RINGS:
                    for delta in range(-self.preload_sector_radius, self.preload_sector_radius + 1):
                        add_sector(int(ring["key"]), corridor_center + delta, 2)

        if len(wanted) > self.max_preloaded_sectors:
            ordered = sorted(
                wanted.items(),
                key=lambda item: (
                    item[1],
                    0 if item[0][0] == active_key else 1,
                    self.sector_distance(item[0][1], center),
                    item[0][0],
                    item[0][1],
                ),
            )
            wanted = dict(ordered[:self.max_preloaded_sectors])

        keys = set(wanted.keys())
        self.last_wanted = keys
        return keys, center

    def build_sector_node(self, ring, sector):
        node = self.stream_root.attachNewNode(f"world-shell-sector-{ring['key']}-{sector}")
        rng = random.Random(self.seed + int(ring["key"]) * 1009 + int(sector) * 9176)
        a0, a1 = self.sector_span(sector)
        r0 = self.scaled_radius(ring["r0"])
        r1 = self.scaled_radius(ring["r1"])
        z = 0.35 + int(ring["key"]) * 0.08
        color = ring["color"]
        alpha = 0.58 if int(ring["key"]) == int(self.active_key) else 0.34
        outer = self.points_on_arc(r1, a0, a1, z, 7)
        inner = list(reversed(self.points_on_arc(r0, a0, a1, z, 7)))
        self.app.add_polyline(node, outer + inner, (color[0], color[1], color[2], alpha), self.app.cfg.line_thickness * 0.30, True, "shell-sector-boundary")
        mid_r = (r0 + r1) * 0.5
        self.app.add_polyline(node, self.points_on_arc(mid_r, a0, a1, z + 0.08, 7), (color[0], color[1], color[2], min(0.70, alpha + 0.12)), self.app.cfg.line_thickness * 0.22, False, "shell-sector-contour")
        for a in (a0, a1):
            self.app.add_polyline(node, [Vec3(math.cos(a) * r0, math.sin(a) * r0, z), Vec3(math.cos(a) * r1, math.sin(a) * r1, z)], (color[0], color[1], color[2], 0.22), self.app.cfg.line_thickness * 0.16, False, "shell-sector-seam")
        base_count = 1 if self.detail == "lite" else 3
        density_bonus = max(0, int(self.biome_signature_density))
        count = base_count + density_bonus
        if self.local_detail_boost and int(ring["key"]) in {1, 2, int(self.active_key)}:
            count += 1
        count = max(1, min(7, count))
        kind = str(ring.get("kind", "flat"))
        self.build_sector_signature(node, ring, sector, a0, a1, r0, r1, z, rng)
        for _ in range(count):
            t = rng.uniform(0.18, 0.82)
            a = rng.uniform(a0 + 0.015, a1 - 0.015)
            rr = r0 + (r1 - r0) * t
            p = Vec3(math.cos(a) * rr, math.sin(a) * rr, z + rng.uniform(0.35, 1.2))
            if kind in {"forest", "hills", "flat"}:
                h = rng.uniform(1.0, 2.4)
                self.app.add_polyline(node, [p, p + Vec3(0, 0, h)], (0.40, 1.0, 0.34, 0.40), self.app.cfg.line_thickness * 0.16, False, "shell-tree-stem")
                self.app.add_polyline(node, [p + Vec3(-0.7, 0, h * 0.62), p + Vec3(0, 0, h), p + Vec3(0.7, 0, h * 0.62)], (0.52, 1.0, 0.42, 0.34), self.app.cfg.line_thickness * 0.14, False, "shell-canopy")
            elif kind == "water":
                pass
            elif kind == "mushroom":
                cap = p + Vec3(0, 0, rng.uniform(1.1, 2.4))
                self.app.add_polyline(node, [p, cap], (1.0, 0.50, 0.94, 0.42), self.app.cfg.line_thickness * 0.18, False, "shell-mushroom-stem")
                self.app.add_polyline(node, [cap + Vec3(-0.75,0,0), cap + Vec3(-0.28,0,0.36), cap + Vec3(0.28,0,0.36), cap + Vec3(0.75,0,0), cap + Vec3(0.28,0,-0.20), cap + Vec3(-0.28,0,-0.20)], (0.10, 1.0, 1.0, 0.42), self.app.cfg.line_thickness * 0.16, True, "shell-mushroom-cap")
            elif kind == "desert":
                self.app.add_polyline(node, [p, p + Vec3(0, 0, 1.8), p + Vec3(0.55, 0.0, 1.1)], (1.0, 0.78, 0.28, 0.42), self.app.cfg.line_thickness * 0.16, False, "shell-cactus")
            elif kind == "ice":
                self.app.add_box(node, p, Vec3(0.9, 0.9, 1.5), (0.68, 0.94, 1.0, 0.36), 0.12)
            elif kind == "urban":
                self.app.add_box(node, p, Vec3(0.9, 0.9, rng.uniform(2.3, 4.2)), (0.22, 0.24, 0.28, 0.42), 0.12)
                self.app.add_polyline(node, [p + Vec3(-0.7, 0, 1.4), p + Vec3(0.7, 0, 2.6), p + Vec3(-0.4, 0, 3.6)], (0.72, 0.78, 0.86, 0.34), self.app.cfg.line_thickness * 0.11, False, "shell-urban-wire-scaffold")
            elif kind == "metropolis":
                self.app.add_box(node, p, Vec3(1.0, 1.0, rng.uniform(2.4, 4.8)), (0.76, 0.50, 1.0, 0.36), 0.14)
                node.setPythonTag("shell_metropolis_fade_sector", 1)
        try:
            node.setPythonTag("world_shell_motion_phase", (int(ring["key"]) * 0.41 + int(sector) * 0.13) % math.tau)
            node.setPythonTag("world_shell_motion_strength", 0.55 if int(ring["key"]) == int(self.active_key) else 0.28)
        except Exception:
            pass
        try:
            node.setTransparency(TransparencyAttrib.MAlpha)
            node.setPythonTag("world_shell_sector", True)
            node.setPythonTag("biome_key", int(ring["key"]))
            node.setPythonTag("sector", int(sector))
        except Exception:
            pass
        return node

    def build_sector_signature(self, node, ring, sector, a0, a1, r0, r1, z, rng):
        """Draw broader biome-readable silhouettes beyond individual scatter props."""
        kind = str(ring.get("kind", "flat"))
        color = ring["color"]
        density = max(0, min(3, int(self.biome_signature_density)))
        if density <= 0:
            return
        alpha = 0.20 + density * 0.055
        line_thickness = self.app.cfg.line_thickness
        span_mid = (a0 + a1) * 0.5
        mid_r = (r0 + r1) * 0.5

        if kind == "flat":
            for t in (0.28, 0.52, 0.76)[: 1 + density]:
                rr = r0 + (r1 - r0) * t
                self.app.add_polyline(node, self.points_on_arc(rr, a0, a1, z + 0.04, 4), (0.92, 0.96, 1.0, alpha), line_thickness * 0.10, False, "shell-flat-grid-arc")
            for offset in (-0.025, 0.025)[: 1 + min(1, density)]:
                a = span_mid + offset
                self.app.add_polyline(node, [self.polar_point(r0, a, z + 0.02), self.polar_point(r1, a, z + 0.02)], (0.92, 0.96, 1.0, alpha * 0.72), line_thickness * 0.09, False, "shell-flat-grid-rib")
        elif kind in {"forest", "hills"}:
            for t in (0.24, 0.46, 0.68, 0.84)[: 1 + density]:
                rr = r0 + (r1 - r0) * t
                wave = []
                for i in range(6):
                    aa = a0 + (a1 - a0) * i / 5
                    lift = math.sin(i * 1.7 + sector * 0.31 + int(ring["key"])) * (0.12 + 0.06 * density)
                    wave.append(self.polar_point(rr, aa, z + 0.24 + lift))
                self.app.add_polyline(node, wave, (color[0], color[1], color[2], alpha + 0.08), line_thickness * 0.13, False, "shell-green-canopy-ridge")
        elif kind == "water":
            return
        elif kind == "mushroom":
            for t in (0.24, 0.46, 0.68, 0.84)[: 1 + density]:
                rr = r0 + (r1 - r0) * t
                ridge = []
                for i in range(7):
                    aa = a0 + (a1 - a0) * i / 6
                    lift = math.sin(i * 1.35 + sector * 0.52) * (0.16 + density * 0.05)
                    ridge.append(self.polar_point(rr, aa, z + 0.18 + lift))
                self.app.add_polyline(node, ridge, (1.0, 0.25, 0.82, alpha + 0.14), line_thickness * 0.15, False, "shell-mushroom-hill-band")
            for i in range(1 + density):
                aa = a0 + (a1 - a0) * (0.24 + i * 0.18)
                rr = r0 + (r1 - r0) * (0.32 + 0.14 * i)
                p = self.polar_point(rr, aa, z + 0.24)
                self.app.add_polyline(node, [p, p + Vec3(0, 0, 1.6 + i * 0.4)], (1.0, 0.42, 0.96, alpha + 0.16), line_thickness * 0.12, False, "shell-mushroom-stem-ridge")
                self.app.add_polyline(node, [p + Vec3(-0.8,0,1.5), p + Vec3(0,0,2.1+i*0.2), p + Vec3(0.8,0,1.5)], (0.10, 1.0, 1.0, alpha + 0.16), line_thickness * 0.12, False, "shell-mushroom-cap-ridge")
        elif kind == "desert":
            for t in (0.34, 0.58, 0.78)[: 1 + density]:
                rr = r0 + (r1 - r0) * t
                dune = []
                for i in range(5):
                    aa = a0 + (a1 - a0) * i / 4
                    lift = math.sin(i * 1.4 + sector) * 0.16
                    dune.append(self.polar_point(rr, aa, z + 0.18 + lift))
                self.app.add_polyline(node, dune, (1.0, 0.70, 0.30, alpha + 0.10), line_thickness * 0.14, False, "shell-desert-dune-line")
        elif kind == "ice":
            for i in range(1 + density):
                aa = a0 + (a1 - a0) * (0.24 + i * 0.17)
                rr = r0 + (r1 - r0) * (0.32 + 0.12 * i)
                p = self.polar_point(rr, aa, z + 0.35 + i * 0.08)
                try:
                    self.app.add_box(node, p, Vec3(0.42 + i * 0.10, 0.42 + i * 0.10, 1.2 + i * 0.28), (0.72, 0.96, 1.0, alpha + 0.12), 0.08)
                except Exception:
                    pass
                self.app.add_polyline(node, [p + Vec3(0, 0, 0.65), p + Vec3(0.55, 0.18, 1.15), p + Vec3(-0.18, -0.45, 1.42)], (0.86, 0.98, 1.0, alpha + 0.10), line_thickness * 0.09, False, "shell-ice-shard-ridge")
        elif kind == "urban":
            for t in (0.34, 0.62)[: 1 + min(1, density)]:
                rr = r0 + (r1 - r0) * t
                self.app.add_polyline(node, self.points_on_arc(rr, a0, a1, z + 0.16, 5), (0.72, 0.78, 0.86, min(0.58, alpha + 0.18)), line_thickness * 0.15, False, "shell-urban-trench")
            for i in range(2 + density):
                aa = a0 + (a1 - a0) * rng.uniform(0.20, 0.84)
                rr = r0 + (r1 - r0) * rng.uniform(0.25, 0.78)
                p = self.polar_point(rr, aa, z + 0.50)
                try:
                    self.app.add_box(node, p, Vec3(0.70, 0.70, 1.0 + i * 0.32), (0.24, 0.26, 0.30, min(0.56, alpha + 0.18)), 0.08)
                except Exception:
                    pass
        elif kind == "metropolis":
            skyline_count = 2 + density
            for i in range(skyline_count):
                aa = a0 + (a1 - a0) * (i + 1) / (skyline_count + 1)
                rr = mid_r + rng.uniform(-(r1 - r0) * 0.16, (r1 - r0) * 0.16)
                p = self.polar_point(rr, aa, z + 0.62)
                try:
                    self.app.add_box(node, p, Vec3(0.62, 0.62, rng.uniform(1.5, 3.8)), (0.76, 0.50, 1.0, alpha + 0.06), 0.08)
                except Exception:
                    pass

    def clear_pass45_beauty_layer(self):
        node = getattr(self, "pass45_beauty_root", None)
        if node is not None:
            try:
                if not node.isEmpty():
                    node.removeNode()
            except Exception:
                pass
        self.pass45_beauty_root = None
        self.pass45_water_surface_nodes = []
        self.pass45_fauna_nodes = []
        self.pass46_water_wave_nodes = []
        self.pass46_water_wave_specs = []
        self.pass46_last_wave_rebuild = -999.0
        self.pass48_motion_nodes = []

    def _pass45_box(self, parent, pos, size, color, thickness=0.08):
        try:
            self.app.add_box(parent, pos, size, color, thickness)
        except Exception:
            pass

    def _pass45_poly(self, parent, points, color, thickness=0.10, closed=False, name="pass45-line"):
        try:
            return self.app.add_polyline(parent, points, color, self.app.cfg.line_thickness * thickness, closed, name)
        except Exception:
            return None

    def build_pass45_beauty_layer(self):
        """Add a low-cost presentability layer over the salvaged world.py shell.

        This keeps the original source world intact but adds inexpensive filled
        vector silhouettes: more plant/animal variants and a true Retired Ocean
        surface over an underwater volume.
        """
        if self.root is None:
            return
        self.clear_pass45_beauty_layer()
        root = self.root.attachNewNode("pass45-infilled-flora-fauna-aqua-layer")
        root.setTransparency(TransparencyAttrib.MAlpha)
        try:
            root.setLightOff(1)
            root.setTextureOff(10)
        except Exception:
            pass
        self.pass45_beauty_root = root
        rng = random.Random(self.seed + 45045)
        self.build_pass85_mushroom_ground_forest(root, rng)
        self.build_pass45_flora_fauna_variants(root, rng)
        self.build_pass46_green_region_polish(root, rng)
        self.build_pass48_desert_ice_polish(root, rng)

    def build_pass45_deep_water_world(self, root, rng):
        # Pass 85: Retired Ocean has been retired.  Keep this legacy method as a
        # hard no-op so old calls cannot resurrect water cards/wave volumes.
        self.pass45_water_surface_nodes = []
        self.pass46_water_wave_nodes = []
        self.pass46_water_wave_specs = []
        return

    def build_pass85_mushroom_ground_forest(self, root, rng):
        ring = self.ring_for_key(4)
        if ring is None or str(ring.get("kind", "")) != "mushroom":
            return
        r0 = self.scaled_radius(ring["r0"])
        r1 = self.scaled_radius(ring["r1"])
        # Ground-level hill strokes and simple infill ribs for the mounted shell layer.
        for band in range(9):
            rr = r0 + (r1 - r0) * ((band + 0.5) / 9.0)
            pts = []
            for i in range(49):
                a = math.tau * i / 48.0
                z = 0.32 + 0.18 * math.sin(a * 5.0 + band * 0.7)
                pts.append(Vec3(math.cos(a) * rr, math.sin(a) * rr, z))
            self._pass45_poly(root, pts, (1.0, 0.22, 0.84, 0.30), 0.055, True, "pass85-mushroom-hill-ring")
        for idx in range(85):
            a = rng.random() * math.tau
            rr = rng.uniform(r0 + 80.0, r1 - 80.0)
            x = math.cos(a) * rr
            y = math.sin(a) * rr
            base_z = 0.48 + rng.uniform(0.0, 0.28)
            h = rng.uniform(2.4, 7.8)
            cap_r = rng.uniform(1.0, 3.8)
            p = Vec3(x, y, base_z)
            top = Vec3(x, y, base_z + h)
            self._pass45_poly(root, [p, top], (1.0, 0.48, 0.95, 0.42), 0.060, False, "pass85-mushroom-wire-stem")
            cap = []
            upper = []
            for k in range(8):
                aa = math.tau * k / 8.0 + math.radians(22.5)
                cap.append(top + Vec3(math.cos(aa) * cap_r, math.sin(aa) * cap_r, -0.28 * cap_r))
                upper.append(top + Vec3(math.cos(aa) * cap_r * 0.62, math.sin(aa) * cap_r * 0.62, 0.26 * cap_r))
            self._pass45_poly(root, cap, (1.0, 0.14, 0.74, 0.44), 0.070, True, "pass85-mushroom-wire-cap-oct")
            self._pass45_poly(root, upper, (0.12, 1.0, 1.0, 0.34), 0.048, True, "pass85-mushroom-wire-cap-top")
            for k in range(8):
                self._pass45_poly(root, [cap[k], upper[k]], (0.16, 1.0, 1.0, 0.28), 0.034, False, "pass85-mushroom-cap-strut")

    def pass46_water_wave_points(self, r0, r1, t, phase, z):
        rr = r0 + (r1 - r0) * t
        pts = []
        # One connected closed ring with a gentle compound sine. The ring is
        # rebuilt only a few times per second in update_pass46_calm_surface_waves.
        for i in range(161):
            a = math.tau * i / 160.0
            wave = math.sin(a * 12.0 + phase) * 5.5 + math.sin(a * 5.0 - phase * 0.62) * 2.1
            pts.append(Vec3(math.cos(a) * (rr + wave), math.sin(a) * (rr + wave), z + math.sin(a * 4.0 + phase) * 0.10))
        return pts

    def build_pass46_calm_surface_waves(self, root, r0, r1, water_surface_z):
        self.pass46_water_wave_specs = []
        self.pass46_water_wave_nodes = []
        # Rings are intentionally few and long; they look connected while keeping
        # node count and vertex count small.
        for idx, t in enumerate((0.10, 0.22, 0.34, 0.46, 0.58, 0.70, 0.82, 0.94)):
            self.pass46_water_wave_specs.append({
                "t": float(t),
                "phase": idx * 0.58,
                "alpha": 0.34 + (idx % 3) * 0.045,
                "z": water_surface_z + 0.12 + (idx % 2) * 0.05,
            })
        # Add a sparse set of cross-current seams so the surface reads like one
        # sheet instead of separate decorative rings.
        for idx, deg in enumerate(range(0, 360, 30)):
            self.pass46_water_wave_specs.append({
                "cross": True,
                "angle": math.radians(float(deg)),
                "phase": idx * 0.71,
                "alpha": 0.20,
                "z": water_surface_z + 0.13,
                "r0": r0 + 18.0,
                "r1": r1 - 18.0,
            })
        self.rebuild_pass46_calm_surface_waves(force=True)

    def rebuild_pass46_calm_surface_waves(self, force=False):
        root = getattr(self, "pass45_beauty_root", None)
        if root is None or root.isEmpty():
            return
        now = float(getattr(self.app, "elapsed", 0.0))
        if not force and now - float(getattr(self, "pass46_last_wave_rebuild", -999.0)) < 0.22:
            return
        for node in list(getattr(self, "pass46_water_wave_nodes", []) or []):
            try:
                if node is not None and not node.isEmpty():
                    node.removeNode()
            except Exception:
                pass
        self.pass46_water_wave_nodes = []
        phase_base = now * 0.42
        for spec in list(getattr(self, "pass46_water_wave_specs", []) or []):
            phase = phase_base + float(spec.get("phase", 0.0))
            if spec.get("cross"):
                angle = float(spec.get("angle", 0.0))
                normal = Vec3(math.cos(angle), math.sin(angle), 0.0)
                tangent = Vec3(-math.sin(angle), math.cos(angle), 0.0)
                pts = []
                for j in range(18):
                    f = j / 17.0
                    rr = float(spec.get("r0", 0.0)) + (float(spec.get("r1", 0.0)) - float(spec.get("r0", 0.0))) * f
                    side = math.sin(f * math.tau * 3.0 + phase) * 4.0
                    pts.append(normal * rr + tangent * side + Vec3(0, 0, float(spec.get("z", 1.35))))
                node = self._pass45_poly(root, pts, (0.30, 0.98, 1.0, float(spec.get("alpha", 0.20))), 0.038, False, "pass46-calm-cross-wave")
            else:
                t = float(spec.get("t", 0.5))
                ring = self.ring_for_key(4) or {"r0": 3300.0, "r1": 4700.0}
                r0 = self.scaled_radius(ring["r0"])
                r1 = self.scaled_radius(ring["r1"])
                pts = self.pass46_water_wave_points(r0, r1, t, phase, float(spec.get("z", 1.35)))
                node = self._pass45_poly(root, pts, (0.34, 1.0, 1.0, float(spec.get("alpha", 0.36))), 0.052, True, "pass46-calm-connected-wave")
            if node is not None:
                self.pass46_water_wave_nodes.append(node)
        self.pass46_last_wave_rebuild = now

    def build_pass46_green_region_polish(self, root, rng):
        """Modern vector-only flora/fauna pass for Forests and Green Hills.

        Avoids odd organic tree silhouettes by using clean stacked prisms/boxes,
        simple infill, and a few motion-readable animal marks.
        """
        for ring_key, count in ((2, 14), (3, 16)):
            ring = self.ring_for_key(ring_key)
            if ring is None:
                continue
            r0 = self.scaled_radius(ring["r0"])
            r1 = self.scaled_radius(ring["r1"])
            base_z = max(0.0, float(ring.get("height", 0.0)) * 0.28)
            palette = (0.18, 0.92, 0.34, 0.30) if ring_key == 2 else (0.56, 0.96, 0.34, 0.28)
            accent = (0.74, 1.0, 0.38, 0.40) if ring_key == 2 else (1.0, 0.72, 0.42, 0.36)
            for i in range(count):
                a = math.radians(-90.0 + rng.uniform(-76.0, 76.0)) if i < count // 2 else rng.random() * math.tau
                rr = rng.uniform(r0 + 110.0, r1 - 110.0)
                p = Vec3(math.cos(a) * rr, math.sin(a) * rr, base_z)
                variant = rng.choice(["stack_tree", "hex_canopy", "reed_cluster", "runner_pair", "bird_arc"])
                if variant == "stack_tree":
                    h = rng.uniform(7.0, 15.0)
                    self._pass45_box(root, p + Vec3(0,0,h*0.28), Vec3(0.80,0.80,h*0.56), (0.22,0.36,0.18,0.25), 0.040)
                    for tier in range(3):
                        z = h * (0.55 + tier * 0.18)
                        s = 4.2 - tier * 0.85
                        self._pass45_box(root, p + Vec3(0,0,z), Vec3(s, s*0.72, 1.15), palette, 0.050)
                elif variant == "hex_canopy":
                    h = rng.uniform(5.0, 11.0)
                    self._pass45_box(root, p + Vec3(0,0,h*0.42), Vec3(0.55,0.55,h*0.84), (0.20,0.34,0.16,0.22), 0.036)
                    for j in range(3):
                        off = Vec3(math.cos(j*2.1)*2.1, math.sin(j*2.1)*1.3, h + j*0.38)
                        self._pass45_box(root, p + off, Vec3(2.7,1.25,0.85), palette, 0.044)
                elif variant == "reed_cluster":
                    for j in range(5):
                        off = Vec3(rng.uniform(-2.6,2.6), rng.uniform(-1.4,1.4), 0)
                        self._pass45_poly(root, [p+off, p+off+Vec3(rng.uniform(-0.6,0.6),0.2,rng.uniform(3.0,6.8))], accent, 0.045, False, "pass47-vector-reed")
                elif variant == "runner_pair":
                    for j in range(2):
                        q = p + Vec3(j*3.0, rng.uniform(-1.5,1.5), 1.0)
                        self._pass45_box(root, q, Vec3(2.2,0.55,0.85), (0.82,0.94,0.68,0.28), 0.040)
                        self._pass45_poly(root, [q+Vec3(-0.6,0,-0.45), q+Vec3(-1.4,0,-1.15), q+Vec3(0.8,0,-0.45), q+Vec3(1.5,0,-1.05)], (0.92,1.0,0.76,0.34), 0.038, False, "pass47-runner-legs")
                else:
                    q = p + Vec3(0,0,rng.uniform(10.0,18.0))
                    self._pass45_poly(root, [q+Vec3(-3,0,0), q, q+Vec3(3,0,0)], (0.86,1.0,0.90,0.34), 0.050, False, "pass47-bird-arc")

    def _pass48_region_point(self, ring, rng, idx=0, count=1, corridor_bias=True):
        r0 = self.scaled_radius(ring["r0"])
        r1 = self.scaled_radius(ring["r1"])
        if corridor_bias and idx < max(4, count // 2):
            a = math.radians(-90.0 + rng.uniform(-54.0, 54.0))
        else:
            a = rng.random() * math.tau
        rr = rng.uniform(r0 + 120.0, r1 - 120.0)
        z = max(0.0, float(ring.get("height", 0.0)) * 0.28)
        return Vec3(math.cos(a) * rr, math.sin(a) * rr, z), a, rr

    def _pass48_motion_anchor(self, root, name, pos, amp=0.35, speed=0.6, phase=0.0, spin=0.0):
        try:
            node = root.attachNewNode(name)
            node.setPos(pos)
            node.setTransparency(TransparencyAttrib.MAlpha)
            node.setPythonTag("pass48_base_z", float(pos.z))
            node.setPythonTag("pass48_amp", float(amp))
            node.setPythonTag("pass48_speed", float(speed))
            node.setPythonTag("pass48_phase", float(phase))
            node.setPythonTag("pass48_spin", float(spin))
            self.pass48_motion_nodes.append(node)
            return node
        except Exception:
            return root

    def build_pass48_desert_ice_polish(self, root, rng):
        """Modern vector landmarks for Desert and Ice.

        This pass keeps the world in the current vector language: simple solid
        forms, low-alpha infill, crisp line art, and a few animated anchors.
        It avoids organic 2D-looking shapes and builds readable 3D silhouettes.
        """
        self.build_pass48_desert_polish(root, rng)
        self.build_pass48_ice_polish(root, rng)

    def build_pass48_desert_polish(self, root, rng):
        ring = self.ring_for_key(5)
        if ring is None:
            return
        r0 = self.scaled_radius(ring["r0"])
        r1 = self.scaled_radius(ring["r1"])
        sand = (1.00, 0.64, 0.25, 0.30)
        amber = (1.00, 0.42, 0.16, 0.26)
        heat = (1.00, 0.82, 0.38, 0.36)
        green = (0.42, 0.92, 0.38, 0.24)
        # Dune terraces are sparse connected lines, not filled 2D boards.
        for t, alpha in ((0.20, 0.20), (0.36, 0.18), (0.55, 0.16), (0.74, 0.14), (0.88, 0.12)):
            rr = r0 + (r1 - r0) * t
            pts = []
            for i in range(129):
                a = math.tau * i / 128.0
                wobble = math.sin(a * 5.0 + t * 7.0) * 14.0 + math.sin(a * 11.0) * 4.5
                pts.append(Vec3(math.cos(a) * (rr + wobble), math.sin(a) * (rr + wobble), 2.2 + t * 1.8))
            self._pass45_poly(root, pts, (1.0, 0.62, 0.26, alpha), 0.060, True, "pass48-desert-dune-terrace")
        # Tall angular marker towers give the biome scale and depth.
        for i in range(15):
            p, a, _rr = self._pass48_region_point(ring, rng, i, 15, True)
            h = rng.uniform(7.0, 22.0)
            anchor = self._pass48_motion_anchor(root, "pass48-desert-marker-anchor", p, amp=0.10, speed=0.20, phase=i * 0.53, spin=0.0)
            self._pass45_box(anchor, Vec3(0, 0, h * 0.28), Vec3(1.4, 1.4, h * 0.56), amber, 0.042)
            self._pass45_box(anchor, Vec3(0, 0, h * 0.70), Vec3(2.7, 0.72, h * 0.18), sand, 0.040)
            self._pass45_box(anchor, Vec3(0, 0, h * 0.90), Vec3(1.0, 1.0, h * 0.24), heat, 0.045)
            for wing in (-1.0, 1.0):
                self._pass45_poly(anchor, [Vec3(0,0,h*0.74), Vec3(wing*4.2,0,h*0.54), Vec3(wing*2.2,0,h*0.38)], heat, 0.052, False, "pass48-desert-marker-wing")
        # Clean cactus/succulent clusters, geometric rather than organic.
        for i in range(24):
            p, a, _rr = self._pass48_region_point(ring, rng, i, 24, True)
            variant = rng.choice(["cactus_stack", "succulent_fan", "sand_node"])
            if variant == "cactus_stack":
                h = rng.uniform(4.5, 11.0)
                self._pass45_box(root, p + Vec3(0,0,h*0.50), Vec3(0.82,0.82,h), green, 0.038)
                self._pass45_box(root, p + Vec3(1.05,0,h*0.62), Vec3(1.9,0.45,0.78), green, 0.034)
                self._pass45_box(root, p + Vec3(-0.92,0,h*0.40), Vec3(1.4,0.40,0.68), green, 0.032)
            elif variant == "succulent_fan":
                for f in range(7):
                    aa = a + (f - 3) * 0.28
                    self._pass45_poly(root, [p + Vec3(0,0,0.25), p + Vec3(math.cos(aa)*3.6, math.sin(aa)*3.6, rng.uniform(1.2,2.7))], (0.64,1.0,0.46,0.34), 0.056, False, "pass48-desert-succulent-spoke")
                self._pass45_box(root, p + Vec3(0,0,0.7), Vec3(0.9,0.9,0.8), green, 0.032)
            else:
                self._pass45_box(root, p + Vec3(0,0,0.7), Vec3(2.6,0.75,0.55), (1.0,0.52,0.18,0.20), 0.036)
                self._pass45_poly(root, [p+Vec3(-1.6,0,0.2), p+Vec3(0,0,1.2), p+Vec3(1.6,0,0.2)], heat, 0.044, False, "pass48-sand-node")
        # A few hover-skimmer silhouettes add motion without many nodes.
        for i in range(8):
            p, a, _rr = self._pass48_region_point(ring, rng, i, 8, True)
            anchor = self._pass48_motion_anchor(root, "pass48-desert-skimmer", p + Vec3(0,0,rng.uniform(3.0,7.0)), amp=0.42, speed=0.55, phase=i*0.81, spin=3.0)
            self._pass45_box(anchor, Vec3(0,0,0), Vec3(3.8,0.48,0.48), (1.0,0.72,0.30,0.26), 0.038)
            self._pass45_poly(anchor, [Vec3(-2.3,0,0), Vec3(0,0,0.82), Vec3(2.3,0,0)], heat, 0.052, False, "pass48-desert-skimmer-wing")

    def build_pass48_ice_polish(self, root, rng):
        ring = self.ring_for_key(6)
        if ring is None:
            return
        r0 = self.scaled_radius(ring["r0"])
        r1 = self.scaled_radius(ring["r1"])
        ice = (0.62, 0.92, 1.0, 0.30)
        deep = (0.22, 0.58, 1.0, 0.22)
        white = (0.94, 1.0, 1.0, 0.34)
        violet = (0.62, 0.62, 1.0, 0.22)
        # Layered crystalline ground contours.
        for t, alpha in ((0.18,0.18),(0.32,0.16),(0.48,0.14),(0.66,0.13),(0.84,0.12)):
            rr = r0 + (r1 - r0) * t
            pts = []
            for i in range(97):
                a = math.tau * i / 96.0
                facet = (1 if i % 2 == 0 else -1) * (7.0 + t * 5.0)
                pts.append(Vec3(math.cos(a) * (rr + facet), math.sin(a) * (rr + facet), 2.6 + t * 2.6))
            self._pass45_poly(root, pts, (0.70,0.96,1.0,alpha), 0.052, True, "pass48-ice-facet-contour")
        # Tall crystal towers with low-alpha solid faces.
        for i in range(18):
            p, a, _rr = self._pass48_region_point(ring, rng, i, 18, True)
            h = rng.uniform(8.0, 28.0)
            anchor = self._pass48_motion_anchor(root, "pass48-ice-spire-anchor", p, amp=0.16, speed=0.32, phase=i*0.47, spin=0.0)
            self._pass45_box(anchor, Vec3(0,0,h*0.32), Vec3(1.6,1.1,h*0.64), ice, 0.036)
            self._pass45_box(anchor, Vec3(0.9,0.35,h*0.56), Vec3(1.1,0.72,h*0.42), deep, 0.032)
            self._pass45_poly(anchor, [Vec3(-1.6,0,h*0.72), Vec3(0,0,h*1.05), Vec3(1.6,0,h*0.72)], white, 0.048, False, "pass48-ice-spire-cap")
        # Ice arches / bridge ribs: geometric landmarks visible from first person.
        for i in range(8):
            p, a, _rr = self._pass48_region_point(ring, rng, i, 8, True)
            span = rng.uniform(6.0, 12.0)
            h = rng.uniform(5.0, 12.0)
            self._pass45_box(root, p + Vec3(-span*0.5,0,h*0.34), Vec3(0.9,0.9,h*0.68), deep, 0.032)
            self._pass45_box(root, p + Vec3(span*0.5,0,h*0.34), Vec3(0.9,0.9,h*0.68), deep, 0.032)
            arch = [p+Vec3(-span*0.5,0,h*0.80), p+Vec3(-span*0.2,0,h*1.08), p+Vec3(span*0.2,0,h*1.08), p+Vec3(span*0.5,0,h*0.80)]
            self._pass45_poly(root, arch, white, 0.058, False, "pass48-ice-arch")
        # Small crystalline fauna silhouettes.
        for i in range(12):
            p, a, _rr = self._pass48_region_point(ring, rng, i, 12, True)
            anchor = self._pass48_motion_anchor(root, "pass48-ice-fauna", p + Vec3(0,0,1.0), amp=0.20, speed=0.40, phase=i*0.66, spin=1.2)
            self._pass45_box(anchor, Vec3(0,0,0.4), Vec3(2.4,0.70,0.75), violet, 0.034)
            self._pass45_box(anchor, Vec3(1.45,0,0.82), Vec3(0.72,0.55,0.72), white, 0.032)
            for leg in (-0.9, 0.0, 0.9):
                self._pass45_poly(anchor, [Vec3(leg,0,0.1), Vec3(leg+0.35,0,-0.55)], (0.80,1.0,1.0,0.30), 0.032, False, "pass48-ice-fauna-leg")

    def update_pass48_desert_ice_motion(self, dt):
        elapsed = float(getattr(self.app, "elapsed", 0.0))
        for node in list(getattr(self, "pass48_motion_nodes", []) or []):
            try:
                if node is None or node.isEmpty():
                    continue
                base_z = float(node.getPythonTag("pass48_base_z") or 0.0)
                amp = float(node.getPythonTag("pass48_amp") or 0.0)
                speed = float(node.getPythonTag("pass48_speed") or 0.0)
                phase = float(node.getPythonTag("pass48_phase") or 0.0)
                spin = float(node.getPythonTag("pass48_spin") or 0.0)
                node.setZ(base_z + math.sin(elapsed * speed + phase) * amp)
                if spin:
                    node.setH(node.getH() + spin * float(dt))
            except Exception:
                pass

    def build_pass45_flora_fauna_variants(self, root, rng):
        # More varied, filled vector flora/fauna for presentability without high mesh cost.
        ring_keys = [2, 3, 5, 6, 7, 8]
        for ring_key in ring_keys:
            ring = self.ring_for_key(ring_key)
            if ring is None:
                continue
            kind = str(ring.get("kind", "flat"))
            r0 = self.scaled_radius(ring["r0"])
            r1 = self.scaled_radius(ring["r1"])
            for i in range(20 if kind in {"forest", "hills"} else 12):
                a = math.radians(-90.0 + rng.uniform(-72.0, 72.0)) if i < 10 else rng.random() * math.tau
                rr = rng.uniform(r0 + 60.0, r1 - 60.0)
                z = max(0.0, float(ring.get("height", 0.0)) * 0.25)
                p = Vec3(math.cos(a) * rr, math.sin(a) * rr, z)
                if kind in {"forest", "hills"}:
                    variant = rng.choice(["spire_tree", "umbrella_tree", "fern", "grazer"])
                    if variant == "spire_tree":
                        h = rng.uniform(7.0, 16.0)
                        self._pass45_box(root, p + Vec3(0,0,h*0.42), Vec3(0.7,0.7,h), (0.36,0.24,0.12,0.28), 0.05)
                        for n in range(3):
                            self._pass45_box(root, p + Vec3(0,0,h*(0.65+n*0.13)), Vec3(4.8-n*1.1,4.8-n*1.1,1.7), (0.15,0.82,0.25,0.22), 0.05)
                    elif variant == "umbrella_tree":
                        h = rng.uniform(5.0, 11.0)
                        self._pass45_box(root, p+Vec3(0,0,h*0.42), Vec3(0.55,0.55,h), (0.42,0.28,0.14,0.26), 0.045)
                        self._pass45_box(root, p+Vec3(0,0,h+1.2), Vec3(6.5,6.5,1.0), (0.18,0.92,0.32,0.20), 0.045)
                    elif variant == "fern":
                        for f in range(5):
                            aa = a + (f-2)*0.20
                            self._pass45_poly(root, [p+Vec3(0,0,0.1), p+Vec3(math.cos(aa)*4.2, math.sin(aa)*4.2, 1.2+rng.random()*1.4)], (0.35, 1.0, 0.42, 0.44), 0.065, False, "pass45-fern")
                    else:
                        self._pass45_box(root, p+Vec3(0,0,1.1), Vec3(2.6,1.0,1.2), (0.70,0.92,0.42,0.24), 0.055)
                        self._pass45_box(root, p+Vec3(1.55,0,1.45), Vec3(0.85,0.65,0.85), (0.82,1.0,0.52,0.24), 0.045)
                        for leg in (-0.8,0.8):
                            self._pass45_poly(root, [p+Vec3(leg,-0.35,0.55), p+Vec3(leg,-0.65,0.0)], (0.82,1.0,0.52,0.34), 0.04, False, "pass45-grazer-leg")
                elif kind == "desert":
                    variant = rng.choice(["split_cactus", "fan_succulent", "sand_skimmer"])
                    if variant == "split_cactus":
                        h = rng.uniform(4.0, 9.0)
                        self._pass45_box(root, p+Vec3(0,0,h*0.5), Vec3(0.9,0.9,h), (0.35,0.72,0.36,0.24), 0.045)
                        self._pass45_box(root, p+Vec3(1.2,0,h*0.62), Vec3(1.8,0.55,0.75), (0.42,0.82,0.38,0.24), 0.04)
                    elif variant == "fan_succulent":
                        for f in range(6):
                            aa = a + f * math.tau/6
                            self._pass45_poly(root, [p, p+Vec3(math.cos(aa)*3.0, math.sin(aa)*3.0, 1.7)], (0.62,0.94,0.42,0.38), 0.065, False, "pass45-succulent")
                    else:
                        self._pass45_box(root, p+Vec3(0,0,0.8), Vec3(2.2,0.8,0.75), (1.0,0.58,0.22,0.22), 0.045)
                elif kind == "ice":
                    self._pass45_box(root, p+Vec3(0,0,2.2), Vec3(1.4,1.4,rng.uniform(3.0,7.0)), (0.68,0.94,1.0,0.22), 0.04)
                    if i % 3 == 0:
                        self._pass45_box(root, p+Vec3(2.2,0,0.9), Vec3(2.1,0.8,0.9), (0.76,1.0,1.0,0.18), 0.035)
                elif kind == "urban":
                    self._pass45_box(root, p+Vec3(0,0,rng.uniform(1.5,4.0)), Vec3(rng.uniform(1.5,3.2),rng.uniform(1.5,3.2),rng.uniform(3.0,8.0)), (0.66,0.68,0.72,0.18), 0.04)
                elif kind == "metropolis":
                    self._pass45_box(root, p+Vec3(0,0,rng.uniform(5.0,14.0)), Vec3(rng.uniform(1.8,3.6),rng.uniform(1.8,3.6),rng.uniform(10.0,28.0)), (0.62,0.38,1.0,0.18), 0.035)

    def purge_retired_water_nodes(self):
        # Pass 85: region 4 is Mushroom now. Remove any stale mounted-shell
        # water/aqua/ocean/wave nodes, even if they came from an older pass.
        root = getattr(self, "root", None)
        if root is None or root.isEmpty():
            return 0
        patterns = ("*water*", "*Water*", "*aqua*", "*Aqua*", "*ocean*", "*Ocean*", "*wave*", "*Wave*", "*whale*", "*Whale*", "*coral*", "*Coral*", "*kelp*", "*Kelp*")
        removed = 0
        for pattern in patterns:
            try:
                matches = list(root.findAllMatches(f"**/{pattern}"))
            except Exception:
                matches = []
            for node in matches:
                try:
                    if node is not None and not node.isEmpty():
                        node.removeNode()
                        removed += 1
                except Exception:
                    pass
        if removed:
            self.pass45_water_surface_nodes = []
            self.pass46_water_wave_nodes = []
            self.pass46_water_wave_specs = []
        return removed

    def update_pass45_beauty_layer(self, dt):
        root = getattr(self, "pass45_beauty_root", None)
        if root is None or root.isEmpty():
            return
        try:
            phase = math.sin(float(getattr(self.app, "elapsed", 0.0)) * 0.55)
            root.setColorScale(1.0, 1.0, 1.0, 0.92 + phase * 0.035)
        except Exception:
            pass
        elapsed = float(getattr(self.app, "elapsed", 0.0))
        for idx, node in enumerate(list(getattr(self, "pass45_water_surface_nodes", []) or [])):
            try:
                if node is not None and not node.isEmpty():
                    node.setZ(1.25 + math.sin(elapsed * 0.34 + idx * 0.22) * 0.045)
            except Exception:
                pass
        # Pass 85: retired water waves stay disabled.
        self.update_pass48_desert_ice_motion(dt)

    def playable_outer_radius(self):
        outer = self.scaled_radius(BIOME_RINGS[-1]["r1"]) + 8.0
        return max(BIOME_ENTRY_GROUND_END_RADIUS, min(float(self.playable_radius), float(outer)))

    def shell_ground_offset_at(self, x, y):
        """Small visual-floor offset for playable shell traversal.

        This is intentionally gentle: it gives biome bands a readable feel while
        avoiding full terrain authority from the extracted shell.
        """
        if not self.play_floor_enabled:
            return 0.0
        radius = math.sqrt(float(x) * float(x) + float(y) * float(y))
        ring = self.ring_for_radius(radius)
        kind = str(ring.get("kind", "flat"))
        raw_height = float(ring.get("height", 0.0) or 0.0)
        base = raw_height * 0.055
        if kind == "water":
            base = min(base, -0.18)
        elif kind == "mushroom":
            base = max(base, 0.28)
        elif kind == "metropolis":
            base = max(base, 0.18)
        elif kind == "ice":
            base = max(base, 0.34)
        blend = smoothstep01((radius - BIOME_ENTRY_GROUND_START_RADIUS) / max(1.0, BIOME_ENTRY_GROUND_END_RADIUS - BIOME_ENTRY_GROUND_START_RADIUS))
        ripple = math.sin(float(x) * 0.037 + float(y) * 0.021 + self.seed * 0.001) * 0.045 * blend
        return clamp((base + ripple) * blend, -0.42, 0.86)

    def shell_ground_z_at(self, x, y, eye_height=3.95, clearance=0.16):
        # Prefer source world.py terrain authority so Green Hills collision follows
        # the actual rolling hill mesh instead of the retired flat adapter floor.
        runtime = getattr(self, "source_runtime", None)
        if runtime is not None and bool(getattr(self, "source_bridge_active", False)):
            try:
                fn = getattr(runtime, "world_height_at", None)
                if callable(fn):
                    return float(eye_height) + float(clearance) + float(fn(float(x), float(y)))
            except Exception:
                pass
        return float(eye_height) + float(clearance) + self.shell_ground_offset_at(x, y)

    def is_playable_position(self, pos):
        if not self.playable_enabled or self.detail == "off":
            return False
        try:
            radius = math.sqrt(float(pos.x) * float(pos.x) + float(pos.y) * float(pos.y))
        except Exception:
            return False
        return radius <= self.playable_outer_radius()

    def update_play_state_data(self):
        radius, _angle, sector = self.player_polar()
        ring = self.ring_for_radius(radius)
        outer = self.playable_outer_radius()
        warn = max(1.0, float(self.boundary_warning_distance))
        remaining = max(0.0, outer - float(radius))
        boundary_factor = 1.0 - min(1.0, remaining / warn)
        self.play_state_data = {
            "enabled": bool(self.playable_enabled and self.detail != "off"),
            "playable": bool(self.playable_enabled and self.detail != "off"),
            "radius": round(float(radius), 2),
            "outer_radius": round(float(outer), 2),
            "remaining_radius": round(remaining, 2),
            "boundary_feedback": bool(self.boundary_feedback),
            "boundary_warning_distance": round(warn, 2),
            "boundary_warning_factor": round(max(0.0, min(1.0, boundary_factor)), 3),
            "near_boundary": bool(self.boundary_feedback and boundary_factor > 0.01),
            "active_key": int(ring.get("key", self.active_key)),
            "active_biome": str(ring.get("name", "FLAT")),
            "active_kind": str(ring.get("kind", "flat")),
            "sector": int(sector),
            "floor_offset": round(float(self.shell_ground_offset_at(getattr(self.app.player_pos, "x", 0.0), getattr(self.app.player_pos, "y", 0.0))), 3),
            "speed_scale": round(float(self.play_speed_scale), 3),
            "floor_enabled": bool(self.play_floor_enabled),
            "authority": "core_owned_holoverse_default_world_hub_unloads_for_artifacts",
        }
        return self.play_state_data

    def update_stream(self, force=False):
        if self.detail == "off" or self.stream_root is None:
            return
        wanted, center_sector = self.wanted_sector_keys()
        if not force and not self.force_refresh and center_sector == self.last_center_sector and wanted == set(self.sector_nodes.keys()):
            return
        self.force_refresh = False
        self.last_center_sector = center_sector
        for key, node in list(self.sector_nodes.items()):
            if key not in wanted:
                try:
                    node.removeNode()
                except Exception:
                    pass
                self.sector_nodes.pop(key, None)
        for ring_key, sector in sorted(wanted):
            if (ring_key, sector) in self.sector_nodes:
                continue
            ring = self.ring_for_key(ring_key)
            if ring is None:
                continue
            self.sector_nodes[(ring_key, sector)] = self.build_sector_node(ring, sector)
        self.default_preloaded = bool(self.default_preload and self.preload_all_biomes and len({k[0] for k in self.sector_nodes}) >= len(BIOME_RINGS))
        self.status = f"HOLOVERSE PRELOADED {len(self.sector_nodes)} SECTORS" if self.default_preloaded else f"HOLOVERSE STREAMING {len(self.sector_nodes)} SECTORS"
        self.write_state(throttled=True)

    def _sync_active_key_from_player_radius(self):
        """Keep bridge/fallback biome state tied to the live player position.

        Region travel and normal walking both move the Core camera through the
        loaded HoloVerse shell. If active_key is left stale, reports and bridge
        handoff data can describe the idle hub or old ring while the
        camera is elsewhere.
        """
        try:
            radius = math.sqrt(float(self.app.player_pos.x) ** 2 + float(self.app.player_pos.y) ** 2)
            ring = self.ring_for_radius(radius)
            key = int(ring.get("key", self.active_key)) if ring else int(self.active_key)
            if key != int(self.active_key):
                self.active_key = key
                try:
                    self.app.cfg.world_shell_active_biome = key
                except Exception:
                    pass
                self.force_refresh = True
            return ring
        except Exception:
            return self.active_ring()

    def update(self, dt):
        if self.root is None or self.root.isEmpty():
            return
        live_ring = self._sync_active_key_from_player_radius()
        old_signature = self.option_signature()
        new_signature = self.read_mount_options()
        if new_signature != old_signature:
            self.rebuild_static()
            return
        if self.source_bridge_active and self.source_runtime is not None:
            holospace_active = False
            try:
                checker = getattr(self.app, "is_holospace_active", None)
                holospace_active = bool(checker()) if callable(checker) else bool(getattr(self.app, "holospace_active", False))
            except Exception:
                holospace_active = bool(getattr(self.app, "holospace_active", False))
            try:
                self.source_bridge_report = self.source_runtime.update_runtime(dt)
                self.default_preloaded = True
                live_name = str((live_ring or {}).get("name", self.active_biome_name()))
                self.status = "HOLOSPACE // RED OCTAFORGE DYSON" if holospace_active else f"PRELOADED // HOLOVERSE DEFAULT WORLD READY // {live_name.upper()} ACTIVE"
            except Exception as exc:
                self.source_bridge_status = f"runtime update error: {exc.__class__.__name__}"
            if not holospace_active and not bool(getattr(self, "retired_water_purge_done", False)):
                # Pass 90: broad scene-graph water purges are one-time cleanup,
                # not a frame task. Per-frame findAllMatches scans were causing
                # heavy frame-time spikes after water was retired.
                self.purge_retired_water_nodes()
                self.retired_water_purge_done = True
                # Pass 89: no legacy beauty-layer animation while the world.py
                # source bridge is active. One world path only.
            self.update_theme_handoff_data()
            self.update_audio_handoff_data()
            self.update_shell_prompt_data()
            self.update_play_state_data()
            return
        self.update_stream()
        self.update_theme_handoff_data()
        self.update_audio_handoff_data()
        self.update_shell_prompt_data()
        self.update_play_state_data()
        self.update_motion_guides(dt)
        pulse = 0.90 + 0.10 * math.sin(float(getattr(self.app, "elapsed", 0.0)) * 1.2)
        try:
            self.root.setColorScale(1.0, 1.0, 1.0, pulse)
        except Exception:
            pass

    def set_active_biome(self, key, move_player=False):
        key = max(1, min(8, int(key)))
        self.active_key = key
        self.app.cfg.world_shell_active_biome = key
        ring = self.active_ring()
        if move_player:
            rr = (self.scaled_radius(ring["r0"]) + self.scaled_radius(ring["r1"])) * 0.5
            rr = max(34.0, rr)
            self.app.player_pos = Vec3(0.0, -rr, getattr(self.app.cfg, "player_eye_height", 3.95))
            try:
                self.app.camera.setPos(self.app.player_pos)
            except Exception:
                pass
        self.rebuild_static()
        self.write_state()

    def mount_report(self):
        return {
            "schema": "holoverse_world_shell_mount_state_v19_pass48",
            "default_world_role": "core_owned_holoverse_default_world",
            "source_world_file": "world.py",
            "scale_authority": "world_py_ring_scale_preserved",
            "source_bridge_policy": "prefer_world_py_generation_helpers_no_standalone_showbase",
            "world_py_source_bridge": bool(self.world_py_source_bridge),
            "source_bridge_active": bool(self.source_bridge_active),
            "source_bridge_status": str(self.source_bridge_status),
            "source_bridge_report": self.source_runtime.report() if self.source_runtime is not None and hasattr(self.source_runtime, "report") else self.source_bridge_report,
            "pass46_calm_surface_waves": len(getattr(self, "pass46_water_wave_specs", []) or []),
            "pass46_green_polish": True,
            "pass47_shallow_aqua_basin": True,
            "pass47_hoverboard_surface_ready": True,
            "pass48_desert_ice_polish": True,
            "pass48_motion_node_count": len(getattr(self, "pass48_motion_nodes", []) or []),
            "status": self.status,
            "active_key": int(self.active_key),
            "active_biome": self.active_biome_name(),
            "detail": self.detail,
            "scale": self.scale,
            "stream_radius": self.stream_radius,
            "default_preload": bool(self.default_preload),
            "default_preloaded": bool(self.default_preloaded),
            "preload_all_biomes": bool(self.preload_all_biomes),
            "preload_corridors": bool(self.preload_corridors),
            "preload_sector_radius": int(self.preload_sector_radius),
            "max_preloaded_sectors": int(self.max_preloaded_sectors),
            "exit_gate_hints": bool(self.exit_gate_hints),
            "entry_ribbons": bool(self.entry_ribbons),
            "transition_cues": bool(self.transition_cues),
            "first_ring_props": bool(self.first_ring_props),
            "first_ring_prop_count": int(self.first_ring_prop_count),
            "ground_continuity": bool(self.ground_continuity),
            "ground_band_count": int(self.ground_band_count),
            "scale_handoff_markers": bool(self.scale_handoff_markers),
            "collision_height_hints": bool(self.collision_height_hints),
            "ground_hint_radius": float(BIOME_ENTRY_GROUND_END_RADIUS),
            "height_hint_authority": "playable_visual_floor_hub_remains_authoritative",
            "playable_enabled": bool(self.playable_enabled),
            "playable_outer_radius": round(float(self.playable_outer_radius()), 2),
            "play_radius": round(float(self.playable_radius), 2),
            "play_speed_scale": round(float(self.play_speed_scale), 3),
            "play_floor_enabled": bool(self.play_floor_enabled),
            "boundary_feedback": bool(self.boundary_feedback),
            "boundary_warning_distance": round(float(self.boundary_warning_distance), 2),
            "checkpoint_enabled": bool(self.checkpoint_enabled),
            "checkpoint_count": int(self.checkpoint_count),
            "checkpoint_pickup_radius": round(float(self.checkpoint_pickup_radius), 2),
            "checkpoint_claimed_count": len(getattr(self, "claimed_checkpoints", set()) or set()),
            "checkpoints": self.checkpoint_payload(),
            "play_state": self.update_play_state_data(),
            "local_detail_boost": bool(self.local_detail_boost),
            "biome_signature_density": int(self.biome_signature_density),
            "directional_feedback": bool(self.directional_feedback),
            "direction_marker_count": int(self.direction_marker_count),
            "corridor_theming": bool(self.corridor_theming),
            "theme_handoff_enabled": bool(self.theme_handoff),
            "theme_handoff_strength": round(float(self.theme_handoff_strength), 3),
            "hub_theme_influence": bool(self.hub_theme_influence),
            "hub_theme_max_blend": round(float(self.hub_theme_max_blend), 3),
            "hub_theme_fog_blend": round(float(self.hub_theme_fog_blend), 3),
            "hub_theme_light_blend": round(float(self.hub_theme_light_blend), 3),
            "status_prompts": bool(self.status_prompts),
            "shell_prompt": self.update_shell_prompt_data(),
            "motion_enabled": bool(self.motion_enabled),
            "motion_intensity": round(float(self.motion_intensity), 3),
            "motion_node_count": len(getattr(self, "motion_nodes", []) or []),
            "audio_handoff_enabled": bool(self.audio_handoff),
            "audio_handoff_strength": round(float(self.audio_handoff_strength), 3),
            "ambience_radius": round(float(self.ambience_radius), 2),
            "audio_handoff": self.update_audio_handoff_data(),
            "theme_handoff": self.update_theme_handoff_data(),
            "corridor_degrees": list(BIOME_HUB_CORRIDOR_DEGREES),
            "sector_count": int(BIOME_SECTOR_COUNT),
            "ring_count": len(BIOME_RINGS),
            "streamed_sector_count": len(self.sector_nodes),
            "streamed_ring_count": len({int(k[0]) for k in self.sector_nodes.keys()}),
            "streamed_sectors": [list(k) for k in sorted(self.sector_nodes.keys())],
            "adapter": "holoverse_world_shell_mount.py",
            "source_world_file": "world.py",
            "extracted_from": ["BIOME_RINGS", "BIOME_SECTOR_COUNT", "fast-travel biome key model", "cardinal corridor model", "biome signature silhouette model", "near-hub entry ribbon model", "ground continuity lane model", "scale handoff marker model", "visual height clearance model", "traversal direction cue model", "biome corridor theme model", "light fog theme handoff model", "subtle hub renderer influence model", "ambience hook data model", "biome status prompt model", "low-cost sector motion model", "bounded playable traversal model", "visual shell floor model", "soft playable boundary model", "shell checkpoint pickup model"],
            "staged_full_shell_mode": "hidden/not_launched_separately",
            "separate_launcher_hidden": True,
            "runtime_state": "HOLOVERSE_DEFAULT",
            "policy": "pass37_holoverse_default_core_lifecycle_hidden_separate_launcher",
            "rings": [{"key": r["key"], "name": r["name"], "kind": r["kind"], "r0": r["r0"], "r1": r["r1"], "height": r.get("height", 0.0)} for r in BIOME_RINGS],
        }

    def write_state(self, throttled=False):
        if throttled and (time.time() - self.last_write_at) < 1.0:
            return
        self.last_write_at = time.time()
        out = ADAPTER_ROOT / "assets" / "config" / "holoverse_world_shell_mount_state.json"
        try:
            out.parent.mkdir(parents=True, exist_ok=True)
            report = self.mount_report()
            self.last_report = report
            out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        except Exception:
            try:
                self.last_report = self.mount_report()
            except Exception:
                pass
