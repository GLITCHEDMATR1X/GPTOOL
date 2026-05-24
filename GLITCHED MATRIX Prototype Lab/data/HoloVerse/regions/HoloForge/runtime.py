"""Fresh in-world HoloForge runtime for the live FLAT HoloVerse region.

HoloForge is no longer a launched dimension. It is a region-mounted tool layer:
enter/activate the FLAT HoloForge layer, edit objects against the real HoloVerse
floor, save into shared data, and unload the tool layer cleanly when closed or
when the player leaves the region.
"""
from __future__ import annotations

import json
import math
import sys
import time
from datetime import datetime
from pathlib import Path

from direct.gui.DirectGui import DirectFrame, DirectLabel
from panda3d.core import TextNode, TransparencyAttrib, Vec3

IN_WORLD_ROUTE = "in_world_region"
FRESH_HOLOFORGE_SCHEMA = 4


def _main_module(cls):
    return sys.modules.get(cls.__module__) or sys.modules.get("__main__")


def install_holoforge_region_runtime(CommandHubApp):
    main = _main_module(CommandHubApp)
    if main is None:
        return

    from holoverse_mode_runtime import resolve_shared_data_root

    ROOT = Path(getattr(main, "ROOT", Path(__file__).resolve().parent))

    # Primary save lives outside the HoloVerse game folder in the shared app data
    # tree. This is the new source of truth for in-world dimensions.
    SHARED_DATA_ROOT = resolve_shared_data_root(main, ROOT)
    SCENE_DIR = SHARED_DATA_ROOT / "holoverse" / "regions" / "flat" / "holoforge"
    SCENE_PATH = SCENE_DIR / "holoforge_scene.json"

    # Compatibility mirrors: old external HoloForge/first-pass files are no
    # longer auto-imported, but we still write a mirror so older tools can show
    # the last current-region state if someone opens them manually.
    LEGACY_BLUEPRINT_DIR = ROOT / "holoforge" / "blueprints"
    LEGACY_BLUEPRINT_PATH = LEGACY_BLUEPRINT_DIR / "autosave_holoforge.json"
    OLD_SHARED_BLUEPRINT_DIR = SHARED_DATA_ROOT / "holoverse" / "holoforge" / "blueprints"
    OLD_SHARED_BLUEPRINT_PATH = OLD_SHARED_BLUEPRINT_DIR / "autosave_holoforge.json"

    # Route helper patches: HoloForge is now a live in-world region route.
    from holoverse_mode_runtime import install_in_world_route_aliases

    install_in_world_route_aliases(main)

    def _ensure_dirs():
        for folder in (SCENE_DIR, LEGACY_BLUEPRINT_DIR, OLD_SHARED_BLUEPRINT_DIR, SHARED_DATA_ROOT / "brain", SHARED_DATA_ROOT / "database"):
            folder.mkdir(parents=True, exist_ok=True)

    def _palette(self):
        return [
            ("cyan", (0.20, 1.00, 1.00, 0.88)),
            ("gold", (1.00, 0.78, 0.22, 0.90)),
            ("red", (1.00, 0.10, 0.16, 0.90)),
            ("green", (0.22, 1.00, 0.36, 0.88)),
            ("purple", (0.74, 0.36, 1.00, 0.88)),
            ("blue", (0.36, 0.62, 1.00, 0.88)),
            ("white", (0.92, 0.98, 1.00, 0.86)),
        ]

    def _prefabs(self):
        return [
            "cube", "platform", "wall", "ramp", "stairs", "bridge",
            "gate", "arch", "pillar", "beacon", "sphere", "cone",
            "crystal", "frame", "totem",
        ]

    def _size_steps(self):
        return [0.50, 0.75, 1.00, 1.25, 1.60, 2.00]

    def _color(self, name="cyan", alpha=None):
        raw = str(name or "cyan").lower().strip()
        for label, col in _palette(self):
            if label == raw:
                return (col[0], col[1], col[2], float(alpha) if alpha is not None else col[3])
        return (0.20, 1.00, 1.00, float(alpha) if alpha is not None else 0.88)

    def _base_size(self, shape):
        shape = str(shape or "cube").lower().strip()
        return {
            "cube": Vec3(4.0, 4.0, 4.0),
            "platform": Vec3(10.0, 10.0, 0.65),
            "wall": Vec3(11.0, 0.85, 5.2),
            "ramp": Vec3(10.0, 6.0, 3.4),
            "stairs": Vec3(9.0, 6.0, 4.8),
            "bridge": Vec3(14.0, 5.0, 1.0),
            "gate": Vec3(9.0, 1.3, 8.0),
            "arch": Vec3(10.0, 1.4, 8.2),
            "pillar": Vec3(2.4, 2.4, 8.4),
            "beacon": Vec3(3.0, 3.0, 9.6),
            "sphere": Vec3(4.6, 4.6, 4.6),
            "cone": Vec3(5.0, 5.0, 5.4),
            "crystal": Vec3(4.0, 4.0, 7.0),
            "frame": Vec3(8.0, 8.0, 7.0),
            "totem": Vec3(4.2, 4.2, 10.0),
        }.get(shape, Vec3(4.0, 4.0, 4.0))

    def _shape_size(self, shape, multiplier=None, raw_size=None):
        if isinstance(raw_size, (list, tuple)) and len(raw_size) >= 3:
            try:
                return Vec3(max(0.25, float(raw_size[0])), max(0.25, float(raw_size[1])), max(0.20, float(raw_size[2])))
            except Exception:
                pass
        mul = 1.0 if multiplier is None else max(0.20, min(3.00, float(multiplier)))
        base = _base_size(self, shape)
        return Vec3(base.x * mul, base.y * mul, base.z * mul)

    def _active_size_multiplier(self):
        steps = _size_steps(self)
        return steps[int(getattr(self, "holoforge_size_index", 2)) % len(steps)]

    def _init_state(self):
        self.holoforge_active = False
        self.holoforge_loaded = False
        self.holoforge_root = None
        self.holoforge_ghost_root = None
        self.holoforge_ui_root = None
        self.holoforge_ui_panel = None
        self.holoforge_ui_title = None
        self.holoforge_ui_tool = None
        self.holoforge_ui_help = None
        self.holoforge_objects = []
        self.holoforge_nodes = []
        self.holoforge_selected_index = -1
        self.holoforge_prefab_index = 0
        self.holoforge_color_index = 0
        self.holoforge_size_index = 2
        self.holoforge_rotation_deg = 0.0
        self.holoforge_height_offset = 0.0
        self.holoforge_snap_enabled = True
        self.holoforge_join_snap_enabled = True
        self.holoforge_grid_step = 2.0
        self.holoforge_snap_threshold = 4.25
        self.holoforge_last_snap_target = None
        self.holoforge_last_ghost_signature = None
        self.holoforge_last_save_at = 0.0
        self.holoforge_dirty = False
        self.holoforge_save_path = SCENE_PATH

    def _is_mode(self, mode):
        data = dict(mode or {})
        manifest = dict(data.get("manifest") or {})
        tokens = " ".join(str(x or "") for x in (
            data.get("name"), data.get("id"), data.get("title"),
            manifest.get("id"), manifest.get("title"), manifest.get("description"),
        )).lower()
        return "holoforge" in tokens or "holoforge" in tokens

    def _flat_allowed(self):
        try:
            if self.is_holospace_active():
                return False
        except Exception:
            pass
        try:
            return int(self.current_holoverse_region_number()) in {0, 9}
        except Exception:
            return True

    def _floor_z(self, x: float, y: float) -> float:
        """Return actual object floor Z, not player-eye grounded Z."""
        mount = getattr(self, "world_shell_mount", None)
        if mount is not None:
            try:
                fn = getattr(mount, "shell_ground_offset_at", None)
                if callable(fn):
                    return float(fn(float(x), float(y)))
            except Exception:
                pass
            try:
                runtime = getattr(mount, "source_runtime", None)
                if runtime is not None and bool(getattr(mount, "source_bridge_active", False)):
                    fn = getattr(runtime, "world_height_at", None)
                    if callable(fn):
                        return float(fn(float(x), float(y)))
            except Exception:
                pass
        try:
            eye = float(getattr(self.cfg, "player_eye_height", 3.95))
            clearance = float(getattr(self.cfg, "terrain_collision_clearance", 0.16))
            grounded = float(self.world_shell_grounded_z(float(x), float(y)))
            return grounded - eye - clearance
        except Exception:
            return 0.0

    def _snap_xy(self, value: float) -> float:
        if not bool(getattr(self, "holoforge_snap_enabled", True)):
            return round(float(value), 3)
        step = max(0.25, float(getattr(self, "holoforge_grid_step", 2.0)))
        return round(round(float(value) / step) * step, 3)

    def _yaw_axes(self, yaw_deg: float):
        rad = math.radians(float(yaw_deg or 0.0))
        axis_x = Vec3(math.cos(rad), math.sin(rad), 0.0)
        axis_y = Vec3(-math.sin(rad), math.cos(rad), 0.0)
        return axis_x, axis_y

    def _extent_along_axis(self, size, yaw_deg: float, axis):
        local_x, local_y = _yaw_axes(self, yaw_deg)
        axis = Vec3(float(axis.x), float(axis.y), 0.0)
        if axis.lengthSquared() <= 0.0001:
            return max(float(size.x), float(size.y)) * 0.5
        axis.normalize()
        return abs(local_x.dot(axis)) * float(size.x) * 0.5 + abs(local_y.dot(axis)) * float(size.y) * 0.5

    def _tool_shape_size_yaw(self):
        idx = int(getattr(self, "holoforge_selected_index", -1))
        if 0 <= idx < len(getattr(self, "holoforge_objects", []) or []):
            rec = dict(self.holoforge_objects[idx])
            shape = str(rec.get("shape") or "cube").lower().strip()
            size = _shape_size(self, shape, raw_size=rec.get("size"))
            try:
                yaw = float((rec.get("rotation") or [getattr(self, "holoforge_rotation_deg", 0.0)])[0])
            except Exception:
                yaw = float(getattr(self, "holoforge_rotation_deg", 0.0))
            return shape, size, yaw
        pref = _prefabs(self)
        shape = pref[int(getattr(self, "holoforge_prefab_index", 0)) % len(pref)]
        size = _shape_size(self, shape, _active_size_multiplier(self))
        return shape, size, float(getattr(self, "holoforge_rotation_deg", 0.0))

    def _side_snap_candidate(self, raw_x: float, raw_y: float, shape: str, size, yaw_deg: float, exclude_idx: int = -1):
        self.holoforge_last_snap_target = None
        if not bool(getattr(self, "holoforge_snap_enabled", True)) or not bool(getattr(self, "holoforge_join_snap_enabled", True)):
            return round(float(raw_x), 3), round(float(raw_y), 3), None
        objects = list(getattr(self, "holoforge_objects", []) or [])
        if not objects:
            return round(float(raw_x), 3), round(float(raw_y), 3), None
        cur_size = Vec3(float(size.x), float(size.y), float(size.z))
        threshold = max(2.25, min(7.5, max(float(cur_size.x), float(cur_size.y)) * 0.35 + float(getattr(self, "holoforge_snap_threshold", 4.25)) * 0.35))
        raw = Vec3(float(raw_x), float(raw_y), 0.0)
        best = None
        for i, item in enumerate(objects):
            if i == int(exclude_idx):
                continue
            try:
                other = _normalize_record(self, item, force_ground=True)
                op = other.get("position", [0.0, 0.0, 0.0])
                osize = Vec3(*[float(v) for v in other.get("size", [4.0, 4.0, 4.0])[:3]])
                oyaw = float((other.get("rotation") or [0.0])[0])
                axis_x, axis_y = _yaw_axes(self, oyaw)
                sides = [
                    ("E", axis_x, osize.x * 0.5),
                    ("W", axis_x * -1.0, osize.x * 0.5),
                    ("N", axis_y, osize.y * 0.5),
                    ("S", axis_y * -1.0, osize.y * 0.5),
                ]
                origin = Vec3(float(op[0]), float(op[1]), 0.0)
                for side_label, axis, other_extent in sides:
                    current_extent = _extent_along_axis(self, cur_size, yaw_deg, axis)
                    candidate = origin + axis * (float(other_extent) + float(current_extent))
                    dist = (candidate - raw).length()
                    if best is None or dist < best[0]:
                        best = (dist, candidate, i, side_label)
            except Exception:
                continue
        if best is not None and best[0] <= threshold:
            _dist, candidate, obj_i, side_label = best
            info = f"JOIN #{obj_i + 1}{side_label}"
            self.holoforge_last_snap_target = info
            return round(float(candidate.x), 3), round(float(candidate.y), 3), info
        self.holoforge_last_snap_target = "GRID"
        return round(float(raw_x), 3), round(float(raw_y), 3), None

    def _placement_xy(self, distance=18.0):
        try:
            forward, _right, _up = self.get_view_basis()
            flat_forward = Vec3(float(forward.x), float(forward.y), 0.0)
            if flat_forward.lengthSquared() <= 0.0001:
                flat_forward = Vec3(0.0, -1.0, 0.0)
            flat_forward.normalize()
            pos = self.head_world_pos() + flat_forward * float(distance)
        except Exception:
            pos = Vec3(float(getattr(self.player_pos, "x", 0.0)), float(getattr(self.player_pos, "y", 0.0)) - float(distance), 0.0)
        x, y = float(pos.x), float(pos.y)
        if bool(getattr(self, "holoforge_snap_enabled", True)):
            x, y = _snap_xy(self, x), _snap_xy(self, y)
        shape, size, yaw = _tool_shape_size_yaw(self)
        idx = int(getattr(self, "holoforge_selected_index", -1))
        x, y, _info = _side_snap_candidate(self, x, y, shape, size, yaw, exclude_idx=idx)
        return x, y

    def _placement(self, distance=18.0, height_offset=None):
        x, y = _placement_xy(self, distance)
        off = float(getattr(self, "holoforge_height_offset", 0.0) if height_offset is None else height_offset)
        return Vec3(float(x), float(y), round(_floor_z(self, x, y) + off, 3))

    def _normalize_record(self, raw, *, force_ground=False):
        raw = dict(raw or {})
        shape = str(raw.get("shape") or raw.get("type") or "cube").lower().strip()
        aliases = {"box": "cube", "floor": "platform", "cylinder": "pillar", "spire": "beacon"}
        shape = aliases.get(shape, shape)
        if shape not in _prefabs(self):
            shape = "cube"
        color = str(raw.get("color") or _palette(self)[int(getattr(self, "holoforge_color_index", 0)) % len(_palette(self))][0]).lower().strip()
        if color not in {name for name, _c in _palette(self)}:
            color = "cyan"
        size = _shape_size(self, shape, raw_size=raw.get("size"))
        pos_raw = raw.get("position") or raw.get("pos") or [0.0, 0.0, 0.0]
        try:
            x = float(pos_raw[0]); y = float(pos_raw[1]); z = float(pos_raw[2])
        except Exception:
            p = _placement(self)
            x, y, z = p.x, p.y, p.z
        if bool(getattr(self, "holoforge_snap_enabled", True)):
            x = _snap_xy(self, x); y = _snap_xy(self, y)
        height_offset = raw.get("height_offset", None)
        if height_offset is None:
            try:
                height_offset = round(float(z) - _floor_z(self, x, y), 3)
            except Exception:
                height_offset = 0.0
        try:
            height_offset = max(-30.0, min(180.0, float(height_offset)))
        except Exception:
            height_offset = 0.0
        ground_locked = bool(raw.get("ground_locked", True))
        if force_ground or ground_locked:
            z = round(_floor_z(self, x, y) + height_offset, 3)
        rot = raw.get("rotation") or raw.get("hpr") or [raw.get("yaw", 0.0), 0.0, 0.0]
        try:
            yaw = float(rot[0]) % 360.0
        except Exception:
            yaw = 0.0
        label = str(raw.get("label") or shape).strip()[:40]
        return {
            "shape": shape,
            "label": label,
            "position": [round(float(x), 3), round(float(y), 3), round(float(z), 3)],
            "rotation": [round(float(yaw), 3), 0.0, 0.0],
            "size": [round(float(size.x), 3), round(float(size.y), 3), round(float(size.z), 3)],
            "color": color,
            "ground_locked": ground_locked,
            "height_offset": round(float(height_offset), 3),
            "wireframe": True,
        }

    def _current_record(self):
        pref = _prefabs(self)
        shape = pref[int(getattr(self, "holoforge_prefab_index", 0)) % len(pref)]
        color = _palette(self)[int(getattr(self, "holoforge_color_index", 0)) % len(_palette(self))][0]
        pos = _placement(self)
        size = _shape_size(self, shape, _active_size_multiplier(self))
        return _normalize_record(self, {
            "shape": shape,
            "label": shape,
            "position": [pos.x, pos.y, pos.z],
            "rotation": [getattr(self, "holoforge_rotation_deg", 0.0), 0.0, 0.0],
            "size": [size.x, size.y, size.z],
            "color": color,
            "ground_locked": True,
            "height_offset": getattr(self, "holoforge_height_offset", 0.0),
        }, force_ground=True)

    def _ensure_root(self):
        if getattr(self, "holoforge_root", None) is None or self.holoforge_root.isEmpty():
            self.holoforge_root = self.root_3d.attachNewNode("holoforge-flat-region-layer")
            self.holoforge_root.setTransparency(TransparencyAttrib.MAlpha)
        if getattr(self, "holoforge_ghost_root", None) is None or self.holoforge_ghost_root.isEmpty():
            self.holoforge_ghost_root = self.root_3d.attachNewNode("holoforge-placement-preview")
            self.holoforge_ghost_root.setTransparency(TransparencyAttrib.MAlpha)
        return self.holoforge_root

    def _ensure_ui(self):
        if getattr(self, "holoforge_ui_root", None) is not None and not self.holoforge_ui_root.isEmpty():
            return
        self.holoforge_ui_root = self.aspect2d.attachNewNode("holoforge-help-hud")
        self.holoforge_ui_panel = DirectFrame(
            parent=self.holoforge_ui_root,
            frameColor=(0.0, 0.0, 0.0, 0.34),
            frameSize=(0.0, 1.08, -0.26, 0.045),
            pos=(-1.34, 0, -0.68),
            relief=None,
        )
        self.holoforge_ui_title = DirectLabel(
            parent=self.holoforge_ui_panel,
            text="HOLOFORGE",
            text_align=TextNode.ALeft,
            text_scale=0.030,
            text_fg=(0.28, 1.0, 1.0, 0.96),
            frameColor=(0, 0, 0, 0),
            pos=(0.025, 0, 0.005),
            textMayChange=True,
        )
        self.holoforge_ui_tool = DirectLabel(
            parent=self.holoforge_ui_panel,
            text="",
            text_align=TextNode.ALeft,
            text_scale=0.023,
            text_fg=(1.0, 0.86, 0.30, 0.94),
            frameColor=(0, 0, 0, 0),
            pos=(0.025, 0, -0.060),
            text_wordwrap=58,
            textMayChange=True,
        )
        self.holoforge_ui_help = DirectLabel(
            parent=self.holoforge_ui_panel,
            text="",
            text_align=TextNode.ALeft,
            text_scale=0.020,
            text_fg=(0.82, 0.96, 1.0, 0.92),
            frameColor=(0, 0, 0, 0),
            pos=(0.025, 0, -0.125),
            text_wordwrap=70,
            textMayChange=True,
        )
        self.holoforge_ui_root.hide()

    def _draw_selection_marker(self, holder, size, color):
        radius = max(2.2, max(float(size.x), float(size.y)) * 0.70)
        z = 0.055
        try:
            self.add_polyline(holder, self.polygon_points(radius, z, 28, 0.0), (1.0, 0.86, 0.22, 0.78), self.cfg.line_thickness * 0.78, True, "holoforge-selected-ring")
            self.add_polyline(holder, self.polygon_points(radius * 1.18, z + 0.02, 28, 10.0), (color[0], color[1], color[2], 0.44), self.cfg.line_thickness * 0.42, True, "holoforge-selected-outer-ring")
        except Exception:
            pass

    def _draw_shape(self, parent, record, ghost=False, selected=False):
        rec = _normalize_record(self, record, force_ground=bool(record.get("ground_locked", True)))
        shape = rec["shape"]
        pos = Vec3(*[float(x) for x in rec["position"][:3]])
        yaw = float((rec.get("rotation") or [0.0])[0])
        size = Vec3(*[float(x) for x in rec["size"][:3]])
        col = _color(self, rec.get("color", "cyan"), 0.30 if ghost else None)
        if selected and not ghost:
            col = (1.0, 0.86, 0.24, 0.96)
        holder = parent.attachNewNode(f"holoforge-{shape}")
        holder.setPos(pos)
        holder.setH(yaw)
        thick = 0.50 if ghost else (1.12 if selected else 0.86)
        if selected and not ghost:
            _draw_selection_marker(self, holder, size, col)
        if shape == "platform":
            self.add_box(holder, Vec3(0, 0, max(0.04, size.z * 0.5)), size, col, thick)
            self.add_surface_card(holder, Vec3(0, 0, size.z + 0.025), Vec3(0, 0, 0), size.x * 1.06, size.y * 1.06, (col[0], col[1], col[2], 0.11), True)
        elif shape == "wall":
            self.add_box(holder, Vec3(0, 0, size.z * 0.5), size, col, thick)
            # Small top rail and bottom feet make the wall read as a placed prop.
            self.add_box(holder, Vec3(0, 0, size.z + 0.12), Vec3(size.x * 1.05, size.y * 1.3, 0.24), col, thick * 0.70)
            self.add_box(holder, Vec3(-size.x * 0.38, 0, 0.10), Vec3(size.x * 0.18, size.y * 2.0, 0.20), col, thick * 0.54)
            self.add_box(holder, Vec3(size.x * 0.38, 0, 0.10), Vec3(size.x * 0.18, size.y * 2.0, 0.20), col, thick * 0.54)
        elif shape == "ramp":
            hx, hy, h = size.x * 0.5, size.y * 0.5, max(0.4, size.z)
            base = [Vec3(-hx, -hy, 0), Vec3(hx, -hy, 0), Vec3(hx, hy, 0), Vec3(-hx, hy, 0)]
            high_a = Vec3(hx, -hy, h)
            high_b = Vec3(hx, hy, h)
            self.add_polyline(holder, base, col, self.cfg.line_thickness * thick, True, "holoforge-ramp-base")
            self.add_polyline(holder, [Vec3(-hx, -hy, 0), high_a, high_b, Vec3(-hx, hy, 0)], col, self.cfg.line_thickness * thick, True, "holoforge-ramp-slope")
            self.add_polyline(holder, [Vec3(hx, -hy, 0), high_a], col, self.cfg.line_thickness * thick, False, "holoforge-ramp-rise")
            self.add_polyline(holder, [Vec3(hx, hy, 0), high_b], col, self.cfg.line_thickness * thick, False, "holoforge-ramp-rise")
            self.add_surface_card(holder, Vec3(0, 0, 0.04), Vec3(0, 0, 0), size.x, size.y, (col[0], col[1], col[2], 0.07), True)
        elif shape == "stairs":
            steps = 5
            step_x = max(0.4, size.x / steps)
            for i in range(steps):
                h = max(0.25, size.z * (i + 1) / steps)
                x = -size.x * 0.5 + step_x * (i + 0.5)
                self.add_box(holder, Vec3(x, 0, h * 0.5), Vec3(step_x * 0.96, size.y, h), col, thick * 0.78)
            rail_z = size.z + 0.35
            self.add_polyline(holder, [Vec3(-size.x * 0.5, -size.y * 0.58, 0.25), Vec3(size.x * 0.5, -size.y * 0.58, rail_z)], col, self.cfg.line_thickness * thick * 0.72, False, "holoforge-stair-rail")
            self.add_polyline(holder, [Vec3(-size.x * 0.5, size.y * 0.58, 0.25), Vec3(size.x * 0.5, size.y * 0.58, rail_z)], col, self.cfg.line_thickness * thick * 0.72, False, "holoforge-stair-rail")
        elif shape == "bridge":
            deck_h = max(0.28, size.z)
            self.add_box(holder, Vec3(0, 0, deck_h * 0.5), Vec3(size.x, size.y, deck_h), col, thick)
            rail_h = max(1.2, deck_h * 2.2)
            self.add_box(holder, Vec3(0, -size.y * 0.55, deck_h + rail_h * 0.5), Vec3(size.x, 0.24, rail_h), col, thick * 0.56)
            self.add_box(holder, Vec3(0, size.y * 0.55, deck_h + rail_h * 0.5), Vec3(size.x, 0.24, rail_h), col, thick * 0.56)
            for x in (-size.x * 0.42, -size.x * 0.14, size.x * 0.14, size.x * 0.42):
                self.add_polyline(holder, [Vec3(x, -size.y * 0.62, deck_h), Vec3(x, size.y * 0.62, deck_h + rail_h)], col, self.cfg.line_thickness * thick * 0.45, False, "holoforge-bridge-cross")
                self.add_polyline(holder, [Vec3(x, size.y * 0.62, deck_h), Vec3(x, -size.y * 0.62, deck_h + rail_h)], col, self.cfg.line_thickness * thick * 0.45, False, "holoforge-bridge-cross")
        elif shape == "arch":
            leg = Vec3(max(0.65, size.x * 0.16), max(0.55, size.y), max(1.0, size.z * 0.78))
            top = Vec3(max(1.0, size.x), max(0.55, size.y), max(0.50, size.z * 0.15))
            self.add_box(holder, Vec3(-size.x * 0.42, 0, leg.z * 0.5), leg, col, thick)
            self.add_box(holder, Vec3(size.x * 0.42, 0, leg.z * 0.5), leg, col, thick)
            self.add_box(holder, Vec3(0, 0, size.z - top.z * 0.5), top, col, thick)
            for yy in (-size.y * 0.60, size.y * 0.60):
                pts = []
                for i in range(17):
                    t = math.pi * i / 16.0
                    pts.append(Vec3(math.cos(t) * size.x * 0.34, yy, leg.z * 0.78 + math.sin(t) * size.z * 0.18))
                self.add_polyline(holder, pts, col, self.cfg.line_thickness * thick * 0.78, False, "holoforge-arch-curve")
        elif shape == "gate":
            leg = Vec3(max(0.65, size.x * 0.18), max(0.55, size.y), max(1.0, size.z))
            top = Vec3(max(1.0, size.x), max(0.55, size.y), max(0.60, size.z * 0.17))
            self.add_box(holder, Vec3(-size.x * 0.42, 0, leg.z * 0.5), leg, col, thick)
            self.add_box(holder, Vec3(size.x * 0.42, 0, leg.z * 0.5), leg, col, thick)
            self.add_box(holder, Vec3(0, 0, size.z - top.z * 0.5), top, col, thick)
        elif shape == "pillar":
            self.add_prism(holder, max(0.5, size.x * 0.5), max(0.6, size.z), col, count=12, thickness_scale=thick)
            self.add_box(holder, Vec3(0, 0, 0.18), Vec3(size.x * 1.35, size.y * 1.35, 0.36), col, thick)
            self.add_box(holder, Vec3(0, 0, size.z + 0.18), Vec3(size.x * 1.18, size.y * 1.18, 0.36), col, thick)
        elif shape == "beacon":
            self.add_box(holder, Vec3(0, 0, 0.28), Vec3(size.x * 1.55, size.y * 1.55, 0.56), col, thick)
            self.add_prism(holder, max(0.35, size.x * 0.26), max(1.0, size.z), col, count=8, thickness_scale=thick)
            for ring_z in (size.z * 0.42, size.z * 0.72, size.z * 1.02):
                self.add_polyline(holder, self.polygon_points(max(0.8, size.x * 0.72), ring_z, 24, 0), (col[0], col[1], col[2], col[3] * 0.68), self.cfg.line_thickness * thick * 0.75, True, "holoforge-beacon-ring")
        elif shape == "sphere":
            r = max(0.55, size.x * 0.5)
            cz = max(r, size.z * 0.5)
            for hpr in (Vec3(0, 0, 0), Vec3(90, 0, 0), Vec3(0, 90, 0)):
                ring = self.add_polyline(holder, [Vec3(math.cos(math.tau * i / 40) * r, math.sin(math.tau * i / 40) * r, cz) for i in range(40)], col, self.cfg.line_thickness * thick, True, "holoforge-sphere-ring")
                ring.setHpr(hpr)
        elif shape == "cone":
            r = max(0.65, size.x * 0.5)
            h = max(0.8, size.z)
            base = self.polygon_points(r, 0.0, 18, 0.0)
            self.add_polyline(holder, base, col, self.cfg.line_thickness * thick, True, "holoforge-cone-base")
            for i, pnt in enumerate(base):
                if i % 2 == 0:
                    self.add_polyline(holder, [pnt, Vec3(0, 0, h)], col, self.cfg.line_thickness * thick, False, "holoforge-cone-side")
        elif shape == "crystal":
            r = max(0.65, size.x * 0.42)
            h = max(1.0, size.z)
            mid = h * 0.52
            base = self.polygon_points(r, 0.0, 6, 30.0)
            belt = self.polygon_points(r * 0.82, mid, 6, 0.0)
            tip = Vec3(0, 0, h)
            self.add_polyline(holder, base, col, self.cfg.line_thickness * thick, True, "holoforge-crystal-base")
            self.add_polyline(holder, belt, col, self.cfg.line_thickness * thick, True, "holoforge-crystal-belt")
            for i, pnt in enumerate(base):
                self.add_polyline(holder, [pnt, belt[i]], col, self.cfg.line_thickness * thick, False, "holoforge-crystal-side")
                self.add_polyline(holder, [belt[i], tip], col, self.cfg.line_thickness * thick, False, "holoforge-crystal-tip")
        elif shape == "frame":
            self.add_box(holder, Vec3(0, 0, size.z * 0.5), size, (col[0], col[1], col[2], max(0.30, col[3] * 0.55)), thick * 0.72)
            self.add_polyline(holder, [Vec3(-size.x * 0.5, -size.y * 0.5, 0), Vec3(size.x * 0.5, -size.y * 0.5, size.z)], col, self.cfg.line_thickness * thick * 0.72, False, "holoforge-frame-brace")
            self.add_polyline(holder, [Vec3(size.x * 0.5, -size.y * 0.5, 0), Vec3(-size.x * 0.5, -size.y * 0.5, size.z)], col, self.cfg.line_thickness * thick * 0.72, False, "holoforge-frame-brace")
            self.add_polyline(holder, [Vec3(-size.x * 0.5, size.y * 0.5, 0), Vec3(size.x * 0.5, size.y * 0.5, size.z)], col, self.cfg.line_thickness * thick * 0.72, False, "holoforge-frame-brace")
            self.add_polyline(holder, [Vec3(size.x * 0.5, size.y * 0.5, 0), Vec3(-size.x * 0.5, size.y * 0.5, size.z)], col, self.cfg.line_thickness * thick * 0.72, False, "holoforge-frame-brace")
        elif shape == "totem":
            levels = 4
            section = max(0.6, size.z / levels)
            for i in range(levels):
                zc = section * (i + 0.5)
                if i % 2 == 0:
                    self.add_box(holder, Vec3(0, 0, zc), Vec3(size.x * (0.84 - i * 0.05), size.y * (0.84 - i * 0.05), section * 0.78), col, thick * 0.78)
                else:
                    sub = holder.attachNewNode("holoforge-totem-prism")
                    sub.setZ(section * i)
                    self.add_prism(sub, max(0.45, size.x * (0.34 - i * 0.025)), section * 0.78, col, count=8, thickness_scale=thick * 0.72)
                self.add_polyline(holder, self.polygon_points(max(0.55, size.x * 0.55), section * (i + 1), 18, i * 12.0), (col[0], col[1], col[2], col[3] * 0.55), self.cfg.line_thickness * thick * 0.52, True, "holoforge-totem-ring")
        else:
            self.add_box(holder, Vec3(0, 0, max(0.05, size.z * 0.5)), size, col, thick)
        return holder

    def _rebuild(self):
        _ensure_root(self)
        for node in list(getattr(self, "holoforge_nodes", []) or []):
            try:
                if node is not None and not node.isEmpty():
                    node.removeNode()
            except Exception:
                pass
        self.holoforge_nodes = []
        clean = []
        for idx, rec in enumerate(list(getattr(self, "holoforge_objects", []) or [])):
            try:
                normalized = _normalize_record(self, rec, force_ground=True)
                clean.append(normalized)
                self.holoforge_nodes.append(_draw_shape(self, self.holoforge_root, normalized, selected=(idx == int(getattr(self, "holoforge_selected_index", -1)))))
            except Exception as exc:
                print(f"holoforge_draw_object_error index={idx} err={exc}")
        self.holoforge_objects = clean

    def _load(self):
        if bool(getattr(self, "holoforge_loaded", False)):
            return
        _ensure_dirs()
        data = {}
        try:
            if SCENE_PATH.exists():
                data = json.loads(SCENE_PATH.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"holoforge_scene_load_error path={SCENE_PATH} err={exc}")
            data = {}
        raw_objects = data.get("objects", []) if isinstance(data, dict) else []
        self.holoforge_objects = [_normalize_record(self, o, force_ground=True) for o in raw_objects if isinstance(o, dict)]
        self.holoforge_loaded = True
        self.holoforge_dirty = False
        _rebuild(self)

    def _scene_payload(self):
        clean = [_normalize_record(self, o, force_ground=True) for o in list(getattr(self, "holoforge_objects", []) or []) if isinstance(o, dict)]
        region_name = "Flat"
        try:
            region_name = self.current_holoverse_region_name()
        except Exception:
            pass
        return {
            "schema": FRESH_HOLOFORGE_SCHEMA,
            "name": "holoforge_flat_region_scene",
            "dimension": "holoforge",
            "tool": "HoloForge",
            "coordinate_space": "holoverse_world_region",
            "region": "flat",
            "region_name": region_name,
            "save_authority": "shared_data_holoverse_region_layer",
            "scene_path": str(SCENE_PATH),
            "created_or_updated_at": datetime.now().isoformat(timespec="seconds"),
            "object_count": len(clean),
            "objects": clean,
        }

    def holoforge_save_blueprint(self):
        if not bool(getattr(self, "holoforge_active", False)) and not bool(getattr(self, "holoforge_loaded", False)):
            return False
        _ensure_dirs()
        payload = _scene_payload(self)
        try:
            text = json.dumps(payload, indent=2) + "\n"
            SCENE_PATH.write_text(text, encoding="utf-8")
            # Mirrors deliberately use the same clean in-world schema; old launch
            # code should not be needed, but this keeps the data visible.
            LEGACY_BLUEPRINT_PATH.write_text(text, encoding="utf-8")
            OLD_SHARED_BLUEPRINT_PATH.write_text(text, encoding="utf-8")
            self.holoforge_last_save_at = time.monotonic()
            self.holoforge_dirty = False
            if getattr(self, "center_hint", None) is not None:
                self.center_hint["text"] = f"HOLOFORGE // SAVED {payload['object_count']} OBJECTS"
            return True
        except Exception as exc:
            print(f"holoforge_scene_save_error err={exc}")
            if getattr(self, "center_hint", None) is not None:
                self.center_hint["text"] = "HOLOFORGE // SAVE FAILED"
            return False

    def activate_holoforge_from_mode(self, mode=None, source="core", route=""):
        if not _flat_allowed(self):
            try:
                self.travel_to_holoverse_region_index(0)
            except Exception:
                pass
        if not _flat_allowed(self):
            self.center_hint["text"] = "HOLOFORGE // FLAT REGION ONLY"
            return False
        _ensure_root(self)
        _ensure_ui(self)
        _load(self)
        self.holoforge_active = True
        self.holoforge_selected_index = -1
        self.holoforge_last_ghost_signature = None
        self.holoforge_root.show()
        self.holoforge_ghost_root.show()
        self.holoforge_ui_root.show()
        try:
            self.close_core_console()
        except Exception:
            pass
        try:
            if getattr(self, "bot_dialogue_open", False):
                self.close_bot_dimension_dialogue("launching")
        except Exception:
            pass
        self.mouse_captured = True
        if not getattr(main, "SELF_TEST", False):
            try:
                self.recenter_mouse(force=True)
            except Exception:
                pass
        label = str((mode or {}).get("name") or "HoloForge")
        try:
            self.core_mode_state["launch_count"] = int(self.core_mode_state.get("launch_count", 0)) + 1
            self.core_mode_state["last_mode"] = label
            self.core_mode_state["last_entry"] = IN_WORLD_ROUTE
            self.core_mode_state["last_launch_type"] = IN_WORLD_ROUTE
            self.core_mode_state["last_launch_source"] = str(source or "core")
            main.save_mode_state(self.core_mode_state)
        except Exception:
            pass
        try:
            self.record_matrixcore_dimension_signal("dimension_launch", label, label=label, route=IN_WORLD_ROUTE, source=str(source or "core"), reason="holoforge_fresh_flat_region_runtime")
            self.record_matrixcore_bot_signal("bot_launch", "IO", "FLAT", "HoloForge", route=IN_WORLD_ROUTE, source="holoforge_region_runtime")
        except Exception:
            pass
        try:
            self._append_mode_gateway_history("holoforge_region_runtime_open", mode=mode, label=label, route=IN_WORLD_ROUTE, extra={"source": source, "object_count": len(self.holoforge_objects), "scene": str(SCENE_PATH)})
        except Exception:
            pass
        self.center_hint["text"] = "HOLOFORGE // BUILDER ACTIVE // GRID + EDGE JOIN SNAP"
        if getattr(self, "audio", None):
            self.audio.play("world_shift.wav", "sfx", 0.58)
        update_holoforge_ui(self)
        return True

    def _hide_holoforge_nodes(self):
        for attr in ("holoforge_ghost_root", "holoforge_ui_root", "holoforge_root"):
            try:
                node = getattr(self, attr, None)
                if node is not None and not node.isEmpty():
                    node.hide()
            except Exception:
                pass

    def _unload_holoforge_nodes(self):
        for attr in ("holoforge_ghost_root", "holoforge_ui_root", "holoforge_root"):
            try:
                node = getattr(self, attr, None)
                if node is not None and not node.isEmpty():
                    node.removeNode()
            except Exception:
                pass
            setattr(self, attr, None)
        self.holoforge_nodes = []
        self.holoforge_last_ghost_signature = None

    def deactivate_holoforge(self, reason="close"):
        if not bool(getattr(self, "holoforge_active", False)):
            return False
        holoforge_save_blueprint(self)
        self.holoforge_active = False
        self.holoforge_selected_index = -1
        if str(reason or "").startswith("left-"):
            _unload_holoforge_nodes(self)
            self.holoforge_loaded = False
        else:
            _hide_holoforge_nodes(self)
        try:
            self.record_matrixcore_dimension_signal("dimension_return", "HoloForge", label="HoloForge", route=IN_WORLD_ROUTE, source="holoforge", reason=reason)
            self._append_mode_gateway_history("holoforge_region_runtime_close", label="HoloForge", route=IN_WORLD_ROUTE, extra={"reason": reason, "object_count": len(self.holoforge_objects), "scene": str(SCENE_PATH)})
        except Exception:
            pass
        self.center_hint["text"] = f"HOLOFORGE // SAVED AND CLOSED // {str(reason).upper()}"
        return True

    def holoforge_place_or_move(self, source="e"):
        if not bool(getattr(self, "holoforge_active", False)):
            return False
        idx = int(getattr(self, "holoforge_selected_index", -1))
        rec = _current_record(self)
        if 0 <= idx < len(self.holoforge_objects):
            current = dict(self.holoforge_objects[idx])
            current["position"] = rec["position"]
            current["rotation"] = [round(float(getattr(self, "holoforge_rotation_deg", 0.0)), 3), 0.0, 0.0]
            current["height_offset"] = round(float(getattr(self, "holoforge_height_offset", 0.0)), 3)
            self.holoforge_objects[idx] = _normalize_record(self, current, force_ground=True)
            msg = f"HOLOFORGE // MOVED OBJECT {idx + 1}"
        else:
            self.holoforge_objects.append(rec)
            msg = f"HOLOFORGE // PLACED {rec['shape'].upper()}"
        self.holoforge_dirty = True
        _rebuild(self)
        holoforge_save_blueprint(self)
        self.holoforge_last_ghost_signature = None
        self.center_hint["text"] = msg
        print(f"holoforge_edit source={source} objects={len(self.holoforge_objects)} selected={self.holoforge_selected_index}")
        update_holoforge_ui(self)
        return True

    def holoforge_cycle_prefab(self):
        if not bool(getattr(self, "holoforge_active", False)):
            return False
        self.holoforge_selected_index = -1
        self.holoforge_prefab_index = (int(getattr(self, "holoforge_prefab_index", 0)) + 1) % len(_prefabs(self))
        self.holoforge_last_ghost_signature = None
        self.center_hint["text"] = f"HOLOFORGE // SHAPE {_prefabs(self)[self.holoforge_prefab_index].upper()}"
        update_holoforge_ui(self)
        return True

    def holoforge_cycle_color(self):
        if not bool(getattr(self, "holoforge_active", False)):
            return False
        self.holoforge_color_index = (int(getattr(self, "holoforge_color_index", 0)) + 1) % len(_palette(self))
        color = _palette(self)[self.holoforge_color_index][0]
        idx = int(getattr(self, "holoforge_selected_index", -1))
        if 0 <= idx < len(self.holoforge_objects):
            self.holoforge_objects[idx]["color"] = color
            self.holoforge_dirty = True
            _rebuild(self)
            holoforge_save_blueprint(self)
        self.holoforge_last_ghost_signature = None
        self.center_hint["text"] = f"HOLOFORGE // COLOR {color.upper()}"
        update_holoforge_ui(self)
        return True

    def holoforge_rotate_tool(self, amount=15.0):
        if not bool(getattr(self, "holoforge_active", False)):
            return False
        self.holoforge_rotation_deg = (float(getattr(self, "holoforge_rotation_deg", 0.0)) + float(amount)) % 360.0
        idx = int(getattr(self, "holoforge_selected_index", -1))
        if 0 <= idx < len(self.holoforge_objects):
            self.holoforge_objects[idx]["rotation"] = [round(self.holoforge_rotation_deg, 3), 0.0, 0.0]
            self.holoforge_dirty = True
            _rebuild(self)
            holoforge_save_blueprint(self)
        self.holoforge_last_ghost_signature = None
        self.center_hint["text"] = f"HOLOFORGE // ROTATE {self.holoforge_rotation_deg:.0f} DEG"
        update_holoforge_ui(self)
        return True

    def holoforge_adjust_size(self, delta=1):
        if not bool(getattr(self, "holoforge_active", False)):
            return False
        steps = _size_steps(self)
        self.holoforge_size_index = (int(getattr(self, "holoforge_size_index", 2)) + int(delta)) % len(steps)
        idx = int(getattr(self, "holoforge_selected_index", -1))
        if 0 <= idx < len(self.holoforge_objects):
            shape = str(self.holoforge_objects[idx].get("shape", "cube"))
            size = _shape_size(self, shape, steps[self.holoforge_size_index])
            self.holoforge_objects[idx]["size"] = [round(size.x, 3), round(size.y, 3), round(size.z, 3)]
            self.holoforge_dirty = True
            _rebuild(self)
            holoforge_save_blueprint(self)
        self.holoforge_last_ghost_signature = None
        self.center_hint["text"] = f"HOLOFORGE // SIZE {steps[self.holoforge_size_index]:.2f}X"
        update_holoforge_ui(self)
        return True

    def holoforge_adjust_height(self, delta=0.5):
        if not bool(getattr(self, "holoforge_active", False)):
            return False
        self.holoforge_height_offset = max(-20.0, min(120.0, float(getattr(self, "holoforge_height_offset", 0.0)) + float(delta)))
        idx = int(getattr(self, "holoforge_selected_index", -1))
        if 0 <= idx < len(self.holoforge_objects):
            rec = dict(self.holoforge_objects[idx])
            rec["height_offset"] = round(self.holoforge_height_offset, 3)
            self.holoforge_objects[idx] = _normalize_record(self, rec, force_ground=True)
            self.holoforge_dirty = True
            _rebuild(self)
            holoforge_save_blueprint(self)
        self.holoforge_last_ghost_signature = None
        self.center_hint["text"] = f"HOLOFORGE // HEIGHT {self.holoforge_height_offset:+.1f}"
        update_holoforge_ui(self)
        return True

    def holoforge_reset_height(self):
        if not bool(getattr(self, "holoforge_active", False)):
            return False
        self.holoforge_height_offset = 0.0
        idx = int(getattr(self, "holoforge_selected_index", -1))
        if 0 <= idx < len(self.holoforge_objects):
            rec = dict(self.holoforge_objects[idx])
            rec["height_offset"] = 0.0
            self.holoforge_objects[idx] = _normalize_record(self, rec, force_ground=True)
            self.holoforge_dirty = True
            _rebuild(self)
            holoforge_save_blueprint(self)
        self.holoforge_last_ghost_signature = None
        self.center_hint["text"] = "HOLOFORGE // HEIGHT RESET TO GROUND"
        update_holoforge_ui(self)
        return True

    def holoforge_toggle_snap(self):
        if not bool(getattr(self, "holoforge_active", False)):
            return False
        self.holoforge_snap_enabled = not bool(getattr(self, "holoforge_snap_enabled", True))
        self.holoforge_last_snap_target = None
        self.holoforge_last_ghost_signature = None
        snap_label = "OFF"
        if self.holoforge_snap_enabled:
            snap_label = "GRID+JOIN" if bool(getattr(self, "holoforge_join_snap_enabled", True)) else "GRID"
        self.center_hint["text"] = f"HOLOFORGE // SNAP {snap_label}"
        update_holoforge_ui(self)
        return True

    def holoforge_toggle_join_snap(self):
        if not bool(getattr(self, "holoforge_active", False)):
            return False
        self.holoforge_join_snap_enabled = not bool(getattr(self, "holoforge_join_snap_enabled", True))
        self.holoforge_last_snap_target = None
        self.holoforge_last_ghost_signature = None
        label = "ON" if bool(getattr(self, "holoforge_join_snap_enabled", True)) else "OFF"
        self.center_hint["text"] = f"HOLOFORGE // EDGE JOIN SNAP {label}"
        update_holoforge_ui(self)
        return True

    def holoforge_select_or_clear(self):
        if not bool(getattr(self, "holoforge_active", False)):
            return False
        if int(getattr(self, "holoforge_selected_index", -1)) >= 0:
            self.holoforge_selected_index = -1
            self.holoforge_last_ghost_signature = None
            _rebuild(self)
            self.center_hint["text"] = "HOLOFORGE // SELECTION CLEARED"
            update_holoforge_ui(self)
            return True
        target = _placement(self)
        best_i = -1
        best_d = 999999.0
        for i, item in enumerate(self.holoforge_objects):
            try:
                p = item.get("position", [0, 0, 0])
                d = math.sqrt((float(p[0]) - target.x) ** 2 + (float(p[1]) - target.y) ** 2)
                if d < best_d:
                    best_i, best_d = i, d
            except Exception:
                pass
        if best_i >= 0 and best_d <= 18.0:
            self.holoforge_selected_index = best_i
            selected = self.holoforge_objects[best_i]
            try:
                self.holoforge_rotation_deg = float((selected.get("rotation") or [0.0])[0])
                self.holoforge_height_offset = float(selected.get("height_offset", 0.0))
            except Exception:
                pass
            self.center_hint["text"] = f"HOLOFORGE // SELECTED OBJECT {best_i + 1} // E MOVES IT"
        else:
            self.center_hint["text"] = "HOLOFORGE // NO OBJECT NEAR PREVIEW"
        self.holoforge_last_ghost_signature = None
        _rebuild(self)
        update_holoforge_ui(self)
        return True

    def holoforge_delete_selected(self):
        if not bool(getattr(self, "holoforge_active", False)):
            return False
        idx = int(getattr(self, "holoforge_selected_index", -1))
        if 0 <= idx < len(self.holoforge_objects):
            removed = self.holoforge_objects.pop(idx)
            self.holoforge_selected_index = -1
            self.holoforge_dirty = True
            _rebuild(self)
            holoforge_save_blueprint(self)
            self.center_hint["text"] = f"HOLOFORGE // DELETED {str(removed.get('shape', 'OBJECT')).upper()}"
        else:
            self.center_hint["text"] = "HOLOFORGE // SELECT OBJECT WITH X FIRST"
        update_holoforge_ui(self)
        return True

    def holoforge_undo_last(self):
        if not bool(getattr(self, "holoforge_active", False)):
            return False
        if self.holoforge_objects:
            removed = self.holoforge_objects.pop()
            self.holoforge_selected_index = -1
            self.holoforge_dirty = True
            _rebuild(self)
            holoforge_save_blueprint(self)
            self.center_hint["text"] = f"HOLOFORGE // UNDID {str(removed.get('shape', 'OBJECT')).upper()}"
        else:
            self.center_hint["text"] = "HOLOFORGE // NOTHING TO UNDO"
        update_holoforge_ui(self)
        return True

    def _update_ghost(self):
        if not bool(getattr(self, "holoforge_active", False)):
            return
        rec = _current_record(self)
        idx = int(getattr(self, "holoforge_selected_index", -1))
        if 0 <= idx < len(self.holoforge_objects):
            selected = self.holoforge_objects[idx]
            rec["shape"] = selected.get("shape", rec["shape"])
            rec["size"] = selected.get("size", rec["size"])
            rec["color"] = selected.get("color", rec["color"])
            rec = _normalize_record(self, rec, force_ground=True)
        sig = json.dumps(rec, sort_keys=True) + f":sel={idx}:snap={getattr(self, 'holoforge_snap_enabled', True)}"
        if sig == getattr(self, "holoforge_last_ghost_signature", None):
            return
        self.holoforge_last_ghost_signature = sig
        try:
            if self.holoforge_ghost_root is not None and not self.holoforge_ghost_root.isEmpty():
                self.holoforge_ghost_root.removeNode()
        except Exception:
            pass
        self.holoforge_ghost_root = self.root_3d.attachNewNode("holoforge-placement-preview")
        self.holoforge_ghost_root.setTransparency(TransparencyAttrib.MAlpha)
        _draw_shape(self, self.holoforge_ghost_root, rec, ghost=True, selected=idx >= 0)

    def update_holoforge_ui(self):
        if not bool(getattr(self, "holoforge_active", False)):
            return
        _ensure_ui(self)
        pref = _prefabs(self)
        shape = pref[int(getattr(self, "holoforge_prefab_index", 0)) % len(pref)]
        color = _palette(self)[int(getattr(self, "holoforge_color_index", 0)) % len(_palette(self))][0]
        selected = int(getattr(self, "holoforge_selected_index", -1))
        mode = f"MOVE #{selected + 1}" if selected >= 0 else "PLACE NEW"
        size_mul = _active_size_multiplier(self)
        height = float(getattr(self, "holoforge_height_offset", 0.0))
        if not bool(getattr(self, "holoforge_snap_enabled", True)):
            snap = "OFF"
        else:
            snap = "GRID+JOIN" if bool(getattr(self, "holoforge_join_snap_enabled", True)) else "GRID"
        snap_target = str(getattr(self, "holoforge_last_snap_target", "") or "")
        if snap_target and snap_target != "GRID":
            snap = f"{snap}→{snap_target}"
        self.holoforge_ui_title["text"] = f"HOLOFORGE // FLAT REGION LAYER // {mode} // {len(self.holoforge_objects)} SAVED"
        self.holoforge_ui_tool["text"] = f"Tool: {shape.upper()}  Color: {color.upper()}  Size: {size_mul:.2f}x  Rotate: {float(getattr(self, 'holoforge_rotation_deg', 0.0)):.0f}°  Height: {height:+.1f}  Snap: {snap}"
        self.holoforge_ui_help["text"] = "E/Click place-move   X select-clear   Q shape   V color   R rotate   [ ] size   PgUp/PgDn height   Home ground   B grid   N edge-join   Del delete   Z undo   G save   Esc close"
        self.holoforge_ui_root.show()

    def update_holoforge(self, dt=0.0):
        if not bool(getattr(self, "holoforge_active", False)):
            return
        if not _flat_allowed(self):
            deactivate_holoforge(self, reason="left-flat-region")
            return
        _ensure_root(self)
        try:
            self.holoforge_root.show()
            self.holoforge_ghost_root.show()
        except Exception:
            pass
        _update_ghost(self)
        update_holoforge_ui(self)

    # Public runtime methods.
    CommandHubApp.is_holoforge_mode = _is_mode
    CommandHubApp.activate_holoforge_from_mode = activate_holoforge_from_mode
    CommandHubApp.deactivate_holoforge = deactivate_holoforge
    CommandHubApp.holoforge_save_blueprint = holoforge_save_blueprint
    CommandHubApp.holoforge_place_or_move = holoforge_place_or_move
    CommandHubApp.holoforge_cycle_prefab = holoforge_cycle_prefab
    CommandHubApp.holoforge_cycle_color = holoforge_cycle_color
    CommandHubApp.holoforge_rotate_tool = holoforge_rotate_tool
    CommandHubApp.holoforge_adjust_size = holoforge_adjust_size
    CommandHubApp.holoforge_adjust_height = holoforge_adjust_height
    CommandHubApp.holoforge_reset_height = holoforge_reset_height
    CommandHubApp.holoforge_toggle_snap = holoforge_toggle_snap
    CommandHubApp.holoforge_toggle_join_snap = holoforge_toggle_join_snap
    CommandHubApp.holoforge_select_or_clear = holoforge_select_or_clear
    CommandHubApp.holoforge_delete_selected = holoforge_delete_selected
    CommandHubApp.holoforge_undo_last = holoforge_undo_last
    CommandHubApp.update_holoforge = update_holoforge
    CommandHubApp.update_holoforge_ui = update_holoforge_ui

    # Lifecycle/input hooks.
    old_init = CommandHubApp.__init__
    def __init__(self, *args, **kwargs):
        _init_state(self)
        old_init(self, *args, **kwargs)
        if not hasattr(self, "holoforge_objects"):
            _init_state(self)
    CommandHubApp.__init__ = __init__

    old_setup_input = CommandHubApp.setup_input
    def setup_input(self, *args, **kwargs):
        result = old_setup_input(self, *args, **kwargs)
        self.accept("x", self.holoforge_select_or_clear)
        self.accept("r", self.holoforge_rotate_tool)
        self.accept("v", self.holoforge_cycle_color)
        self.accept("g", self.holoforge_save_blueprint)
        self.accept("z", self.holoforge_undo_last)
        self.accept("delete", self.holoforge_delete_selected)
        self.accept("[", self.holoforge_adjust_size, [-1])
        self.accept("]", self.holoforge_adjust_size, [1])
        self.accept("page_up", self.holoforge_adjust_height, [0.5])
        self.accept("page_down", self.holoforge_adjust_height, [-0.5])
        self.accept("home", self.holoforge_reset_height)
        self.accept("b", self.holoforge_toggle_snap)
        self.accept("n", self.holoforge_toggle_join_snap)
        return result
    CommandHubApp.setup_input = setup_input

    old_e = CommandHubApp.on_e_down
    def on_e_down(self):
        if bool(getattr(self, "holoforge_active", False)):
            self.set_key("e", True)
            self.holoforge_place_or_move(source="e")
            return
        return old_e(self)
    CommandHubApp.on_e_down = on_e_down

    old_q = CommandHubApp.on_q_down
    def on_q_down(self):
        if bool(getattr(self, "holoforge_active", False)):
            self.set_key("q", True)
            self.holoforge_cycle_prefab()
            return
        return old_q(self)
    CommandHubApp.on_q_down = on_q_down

    old_mouse = CommandHubApp.primary_click_interact
    def primary_click_interact(self):
        if bool(getattr(self, "holoforge_active", False)):
            self.holoforge_place_or_move(source="mouse1")
            return
        return old_mouse(self)
    CommandHubApp.primary_click_interact = primary_click_interact

    old_esc = CommandHubApp.start_escape_hold
    def start_escape_hold(self):
        if bool(getattr(self, "holoforge_active", False)):
            self.deactivate_holoforge(reason="escape")
            return
        return old_esc(self)
    CommandHubApp.start_escape_hold = start_escape_hold

    old_route = CommandHubApp.launch_core_mode_route
    def launch_core_mode_route(self, mode, source="core", extra_env=None, close_core=True):
        if self.is_holoforge_mode(mode):
            return bool(self.activate_holoforge_from_mode(mode, source=source, route=IN_WORLD_ROUTE))
        return old_route(self, mode, source=source, extra_env=extra_env, close_core=close_core)
    CommandHubApp.launch_core_mode_route = launch_core_mode_route

    old_region_ui = CommandHubApp.update_holoverse_region_ui
    def update_holoverse_region_ui(self):
        result = old_region_ui(self)
        if bool(getattr(self, "holoforge_active", False)):
            try:
                if hasattr(self, "region_keymap_root"):
                    self.region_keymap_root.hide()
                if hasattr(self, "region_top_panel"):
                    self.region_top_panel.hide()
            except Exception:
                pass
        return result
    CommandHubApp.update_holoverse_region_ui = update_holoverse_region_ui

    old_update = CommandHubApp.update_task
    def update_task(self, task):
        result = old_update(self, task)
        try:
            if not getattr(self, "external_suspended", False) and getattr(self, "active_native_mode", None) is None:
                self.update_holoforge(0.0)
        except Exception as exc:
            print(f"holoforge_update_error: {exc}")
        return result
    CommandHubApp.update_task = update_task

    setattr(main, "HOLOFORGE_REGION_RUNTIME_INSTALLED", True)
    setattr(main, "HOLOFORGE_SCENE_PATH_RUNTIME", SCENE_PATH)
    setattr(main, "HOLOFORGE_BLUEPRINT_PATH_RUNTIME", SCENE_PATH)
