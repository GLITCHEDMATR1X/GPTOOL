"""In-world Forest Growth runtime for the live FORESTS HoloVerse region.

Vanta's forest mode is now a simple planter/showcase layer: the player aims at
forest ground and places one random full-grown plant per click.  It saves up to
50 grounded plants and intentionally does not expose seed growth, harvesting,
snap grids, or plant-type editing.
"""
from __future__ import annotations

import json
import math
import random
import sys
import time
from datetime import datetime
from pathlib import Path

from direct.gui.DirectGui import DirectFrame, DirectLabel
from panda3d.core import TextNode, Vec3

IN_WORLD_ROUTE = "in_world_region"
FOREST_GROWTH_SCHEMA = 4
FOREST_REGION_NUMBER = 1
FOREST_MAX_PLANTS = 50


def _main_module(cls):
    return sys.modules.get(cls.__module__) or sys.modules.get("__main__")


def install_forest_growth_runtime(CommandHubApp):
    main = _main_module(CommandHubApp)
    if main is None:
        return

    from holoverse_mode_runtime import resolve_shared_data_root

    ROOT = Path(getattr(main, "ROOT", Path(__file__).resolve().parent))
    SHARED_DATA_ROOT = resolve_shared_data_root(main, ROOT)
    STATE_DIR = SHARED_DATA_ROOT / "holoverse" / "regions" / "forest" / "growth"
    STATE_PATH = STATE_DIR / "forest_growth_state.json"
    ROOT_PROGRESS_PATH = ROOT / "progression" / "progression_state.json"
    SHARED_PROGRESS_PATH = SHARED_DATA_ROOT / "holoverse" / "progression" / "progression_state.json"

    from holoverse_mode_runtime import install_in_world_route_aliases

    install_in_world_route_aliases(main)

    def _ensure_dirs():
        for folder in (STATE_DIR, ROOT_PROGRESS_PATH.parent, SHARED_PROGRESS_PATH.parent, SHARED_DATA_ROOT / "brain", SHARED_DATA_ROOT / "database"):
            folder.mkdir(parents=True, exist_ok=True)

    def _write_json(path: Path, payload: dict):
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(path)

    def _plant_catalog():
        return [
            {
                "id": "berry_bush",
                "label": "Berry Bush",
                "color": (0.15, 0.88, 0.34, 0.95),
                "accent": (1.00, 0.18, 0.34, 0.98),
                "trunk": (0.35, 0.18, 0.09, 0.88),
                "radius": 2.4,
            },
            {
                "id": "garden_greens",
                "label": "Garden Greens",
                "color": (0.42, 1.00, 0.32, 0.94),
                "accent": (1.00, 0.72, 0.20, 0.98),
                "trunk": (0.24, 0.38, 0.12, 0.82),
                "radius": 2.8,
            },
            {
                "id": "forest_tree",
                "label": "Forest Tree",
                "color": (0.17, 0.78, 0.30, 0.96),
                "accent": (0.72, 1.00, 0.36, 0.92),
                "trunk": (0.38, 0.20, 0.10, 0.90),
                "radius": 3.6,
            },
            {
                "id": "fruit_tree",
                "label": "Fruit Tree",
                "color": (0.20, 0.86, 0.40, 0.96),
                "accent": (1.00, 0.38, 0.13, 0.98),
                "trunk": (0.42, 0.22, 0.12, 0.90),
                "radius": 3.8,
            },
        ]

    def _catalog_entry(plant_type=None):
        catalog = _plant_catalog()
        aliases = {
            "berry_bushes": "berry_bush", "berries": "berry_bush", "bush": "berry_bush",
            "vegetables": "garden_greens", "veg": "garden_greens", "vegetable": "garden_greens",
            "forest_trees": "forest_tree", "tree": "forest_tree", "trees": "forest_tree",
            "fruit_trees": "fruit_tree", "fruit": "fruit_tree",
        }
        raw = aliases.get(str(plant_type or "").strip().lower(), str(plant_type or "").strip().lower())
        for entry in catalog:
            if entry["id"] == raw:
                return entry
        return catalog[0]

    def _is_forest_mode(self, mode):
        data = dict(mode or {})
        manifest = dict(data.get("manifest") or {})
        tokens = " ".join(str(x or "") for x in (
            data.get("name"), data.get("id"), data.get("title"),
            manifest.get("id"), manifest.get("title"), manifest.get("description"),
            manifest.get("host_contract"), manifest.get("preferred_display"),
        )).lower()
        return (
            "forest growth" in tokens
            or "living forest" in tokens
            or "vanta" in tokens
            or ("forest" in tokens and "science" in tokens)
            or str(manifest.get("id") or data.get("id") or "").lower() == "science"
            or str(data.get("name") or "").lower() == "science"
        )

    def _forest_allowed(self):
        try:
            if self.is_holospace_active():
                return False
        except Exception:
            pass
        try:
            return int(self.current_holoverse_region_number()) == FOREST_REGION_NUMBER
        except Exception:
            return True

    def _floor_z(self, x: float, y: float) -> float:
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

    def _aim_ground_xy(self, fallback_distance=22.0):
        try:
            origin = self.head_world_pos()
            forward, _right, _up = self.get_view_basis()
            f = Vec3(float(forward.x), float(forward.y), float(forward.z))
            if f.lengthSquared() <= 0.0001:
                f = Vec3(0.0, -1.0, -0.20)
            f.normalize()
            floor_here = _floor_z(self, float(origin.x), float(origin.y))
            if f.z < -0.035:
                t = (floor_here + 0.08 - float(origin.z)) / float(f.z)
                t = max(7.0, min(66.0, float(t)))
                pos = origin + f * t
            else:
                flat = Vec3(f.x, f.y, 0.0)
                if flat.lengthSquared() <= 0.0001:
                    flat = Vec3(0.0, -1.0, 0.0)
                flat.normalize()
                pos = origin + flat * float(fallback_distance)
        except Exception:
            pos = Vec3(float(getattr(self.player_pos, "x", 0.0)), float(getattr(self.player_pos, "y", 0.0)) - float(fallback_distance), 0.0)
        return round(float(pos.x), 3), round(float(pos.y), 3)

    def _normalize_plant(self, raw, *, force_ground=True):
        raw = dict(raw or {})
        entry = _catalog_entry(raw.get("type") or raw.get("plant_type"))
        pos_raw = raw.get("position") or raw.get("pos")
        if pos_raw is None:
            x, y = _aim_ground_xy(self)
            z = _floor_z(self, x, y)
        else:
            try:
                x = float(pos_raw[0]); y = float(pos_raw[1]); z = float(pos_raw[2])
            except Exception:
                x, y = _aim_ground_xy(self)
                z = _floor_z(self, x, y)
        if force_ground:
            z = _floor_z(self, x, y)
        rot = raw.get("rotation") if isinstance(raw.get("rotation"), list) else [raw.get("yaw", 0.0), 0.0, 0.0]
        try:
            yaw = float(rot[0]) % 360.0
        except Exception:
            yaw = 0.0
        plant_id = str(raw.get("id") or f"plant_{int(time.time() * 1000)}_{len(getattr(self, 'forest_growth_plants', []) or []) + 1}")
        return {
            "id": plant_id,
            "type": entry["id"],
            "label": entry["label"],
            "position": [round(float(x), 3), round(float(y), 3), round(float(z), 3)],
            "rotation": [round(yaw, 3), 0.0, 0.0],
            "placed_at": str(raw.get("placed_at") or raw.get("planted_at") or datetime.now().isoformat(timespec="seconds")),
            "stage": 3,
            "full_grown": True,
        }

    def _random_plant_record(self):
        rng = random.Random(time.time_ns() ^ (len(getattr(self, "forest_growth_plants", []) or []) * 8191))
        entry = rng.choice(_plant_catalog())
        x, y = _aim_ground_xy(self)
        return _normalize_plant(self, {
            "id": f"plant_{int(time.time() * 1000)}_{len(getattr(self, 'forest_growth_plants', []) or []) + 1}",
            "type": entry["id"],
            "position": [x, y, _floor_z(self, x, y)],
            "rotation": [rng.uniform(0.0, 360.0), 0.0, 0.0],
            "placed_at": datetime.now().isoformat(timespec="seconds"),
        })

    def _init_state(self):
        self.forest_growth_active = False
        self.forest_growth_loaded = False
        self.forest_growth_root = None
        self.forest_growth_ui_root = None
        self.forest_growth_ui_panel = None
        self.forest_growth_ui_title = None
        self.forest_growth_ui_tool = None
        self.forest_growth_ui_help = None
        self.forest_growth_plants = []
        self.forest_growth_nodes = []
        self.forest_growth_selected_index = -1
        self.forest_growth_last_save_at = 0.0
        self.forest_growth_dirty = False
        self.forest_growth_state_path = STATE_PATH

    def _read_state():
        _ensure_dirs()
        if not STATE_PATH.exists():
            return {"plants": []}
        try:
            data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception as exc:
            print(f"forest_planter_state_read_error: {exc}")
        return {"plants": []}

    def _sync_progression_save(self, reason="save"):
        plants = list(getattr(self, "forest_growth_plants", []) or [])[-FOREST_MAX_PLANTS:]
        summary = {
            "schema": FOREST_GROWTH_SCHEMA,
            "state_path": str(STATE_PATH),
            "region": "forest",
            "owner_bot": "Vanta",
            "mode": "Forest Planter",
            "dimension": "Forest Growth",
            "total_plants": len(plants),
            "full_grown_plants": len(plants),
            "max_plants": FOREST_MAX_PLANTS,
            "remaining_slots": max(0, FOREST_MAX_PLANTS - len(plants)),
            "last_saved_at": datetime.now().isoformat(timespec="seconds"),
            "last_save_reason": str(reason or "save"),
        }
        for path in (ROOT_PROGRESS_PATH, SHARED_PROGRESS_PATH):
            try:
                data = {}
                if path.exists():
                    try:
                        loaded = json.loads(path.read_text(encoding="utf-8"))
                        if isinstance(loaded, dict):
                            data = loaded
                    except Exception:
                        data = {}
                data.setdefault("dimension_blueprints", {})["science"] = {
                    "owner_bot": "Vanta",
                    "status": "playable_in_world_region",
                    "tool": "Forest Planter",
                    "state": str(STATE_PATH),
                }
                data.setdefault("forest_growth", {}).update(summary)
                visits = data.setdefault("dimension_visits", {})
                sci = visits.setdefault("Forest Growth", {})
                sci["count"] = int(sci.get("count", 0)) + (1 if reason == "activate" else 0)
                sci["last_at"] = datetime.now().isoformat(timespec="seconds")
                sci["route"] = IN_WORLD_ROUTE
                sci["reason"] = "forest_planter_region_runtime"
                sci["source"] = "region_bot:Vanta"
                _write_json(path, data)
            except Exception as exc:
                print(f"forest_planter_progression_sync_error {path}: {exc}")
        return summary

    def save_forest_growth(self, reason="manual"):
        _ensure_dirs()
        plants = []
        for raw in list(getattr(self, "forest_growth_plants", []) or [])[-FOREST_MAX_PLANTS:]:
            plants.append(_normalize_plant(self, raw, force_ground=True))
        self.forest_growth_plants = plants
        payload = {
            "schema": FOREST_GROWTH_SCHEMA,
            "kind": "holoverse_forest_planter_state",
            "save_authority": "shared_data_holoverse_region_layer",
            "region": "forest",
            "region_number": FOREST_REGION_NUMBER,
            "owner_bot": "Vanta",
            "mode": "Forest Planter",
            "placement_rule": "lmb_random_full_grown_grounded_plant",
            "max_plants": FOREST_MAX_PLANTS,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "plant_types": [e["id"] for e in _plant_catalog()],
            "plants": plants,
            "summary": {
                "total_plants": len(plants),
                "full_grown": len(plants),
                "remaining_slots": max(0, FOREST_MAX_PLANTS - len(plants)),
            },
        }
        try:
            _write_json(STATE_PATH, payload)
            self.forest_growth_dirty = False
            self.forest_growth_last_save_at = time.time()
            _sync_progression_save(self, reason=str(reason or "save"))
            try:
                self.center_hint["text"] = f"FOREST PLANTER // SAVED {len(plants)}/{FOREST_MAX_PLANTS}"
            except Exception:
                pass
        except Exception as exc:
            try:
                self.center_hint["text"] = f"FOREST PLANTER // SAVE FAILED // {exc}"
            except Exception:
                pass
            print(f"forest_planter_save_error: {exc}")
        return True

    def load_forest_growth(self):
        data = _read_state()
        plants = []
        for raw in list((data or {}).get("plants", []) or []):
            if isinstance(raw, dict):
                plants.append(_normalize_plant(self, raw, force_ground=True))
        self.forest_growth_plants = plants[-FOREST_MAX_PLANTS:]
        self.forest_growth_loaded = True
        return self.forest_growth_plants

    def _ensure_runtime_nodes(self):
        if getattr(self, "forest_growth_root", None) is None or self.forest_growth_root.isEmpty():
            self.forest_growth_root = self.root_3d.attachNewNode("forest-planter-region-layer")
        if getattr(self, "forest_growth_ui_root", None) is None or self.forest_growth_ui_root.isEmpty():
            self.forest_growth_ui_root = self.hud_root.attachNewNode("forest-planter-ui")
            self.forest_growth_ui_panel = DirectFrame(
                parent=self.forest_growth_ui_root,
                frameColor=(0.0, 0.035, 0.018, 0.46),
                frameSize=(0.0, 1.30, -0.24, 0.05),
                pos=(-1.36, 0, -0.40),
                relief=None,
            )
            self.forest_growth_ui_title = DirectLabel(
                parent=self.forest_growth_ui_panel,
                text="FOREST PLANTER",
                text_align=TextNode.ALeft,
                text_scale=0.030,
                text_fg=(0.46, 1.0, 0.48, 0.96),
                frameColor=(0, 0, 0, 0),
                pos=(0.025, 0, 0.007),
                textMayChange=True,
            )
            self.forest_growth_ui_tool = DirectLabel(
                parent=self.forest_growth_ui_panel,
                text="",
                text_align=TextNode.ALeft,
                text_scale=0.023,
                text_fg=(1.0, 0.88, 0.38, 0.94),
                frameColor=(0, 0, 0, 0),
                pos=(0.025, 0, -0.060),
                text_wordwrap=72,
                textMayChange=True,
            )
            self.forest_growth_ui_help = DirectLabel(
                parent=self.forest_growth_ui_panel,
                text="",
                text_align=TextNode.ALeft,
                text_scale=0.020,
                text_fg=(0.82, 1.0, 0.88, 0.92),
                frameColor=(0, 0, 0, 0),
                pos=(0.025, 0, -0.124),
                text_wordwrap=78,
                textMayChange=True,
            )
        try:
            self.forest_growth_root.show()
            self.forest_growth_ui_root.show()
        except Exception:
            pass

    def _remove_drawn_nodes(self):
        for node in list(getattr(self, "forest_growth_nodes", []) or []):
            try:
                if node is not None and not node.isEmpty():
                    node.removeNode()
            except Exception:
                pass
        self.forest_growth_nodes = []

    def _ring(app, holder, radius, color, selected=False):
        try:
            a = 0.84 if selected else 0.46
            col = (1.0, 0.86, 0.24, a) if selected else (color[0], color[1], color[2], 0.34)
            app.add_polyline(holder, app.polygon_points(float(radius), 0.045, 28, 0.0), col, app.cfg.line_thickness * (0.78 if selected else 0.48), True, "forest-planter-ground-ring")
        except Exception:
            pass

    def _marker(app, holder, center, radius, color, name="marker"):
        try:
            cx, cy, cz = float(center.x), float(center.y), float(center.z)
            pts = [Vec3(cx + p.x, cy + p.y, cz + p.z) for p in app.polygon_points(float(radius), 0.0, 10, 0.0)]
            app.add_polyline(holder, pts, color, app.cfg.line_thickness * 0.44, True, name)
            app.add_polyline(holder, [Vec3(cx - radius, cy, cz), Vec3(cx + radius, cy, cz)], color, app.cfg.line_thickness * 0.24, False, name + "-x")
            app.add_polyline(holder, [Vec3(cx, cy - radius, cz), Vec3(cx, cy + radius, cz)], color, app.cfg.line_thickness * 0.24, False, name + "-y")
        except Exception:
            pass

    def _draw_bush(app, holder, entry, selected=False):
        col, fruit = entry["color"], entry["accent"]
        _ring(app, holder, 2.45, col, selected)
        for i in range(7):
            ang = math.tau * i / 7.0 + 0.16
            start = Vec3(math.cos(ang) * 0.25, math.sin(ang) * 0.25, 0.06)
            end = Vec3(math.cos(ang) * 1.35, math.sin(ang) * 1.35, 1.25 + (0.12 if i % 2 else 0.0))
            app.add_polyline(holder, [start, end], col, app.cfg.line_thickness * 0.62, False, "bush-stem")
        for rz, rad, alpha in ((0.78, 1.45, 0.72), (1.18, 1.25, 0.94), (1.50, 0.82, 0.78)):
            app.add_polyline(holder, app.polygon_points(rad, rz, 14, rz * 19), (col[0], col[1], col[2], alpha), app.cfg.line_thickness * 0.56, True, "bush-canopy")
        for i in range(8):
            ang = math.tau * i / 8.0
            _marker(app, holder, Vec3(math.cos(ang) * 1.05, math.sin(ang) * 1.05, 1.25 + (0.16 if i % 2 else -0.04)), 0.18, fruit, "berry")

    def _draw_greens(app, holder, entry, selected=False):
        col, accent = entry["color"], entry["accent"]
        _ring(app, holder, 2.85, col, selected)
        for row in (-0.95, 0.0, 0.95):
            pts = []
            for i in range(7):
                x = -2.05 + i * 0.68
                pts.append(Vec3(x, row, 0.10 + (0.06 if i % 2 else 0.0)))
            app.add_polyline(holder, pts, (col[0], col[1], col[2], 0.76), app.cfg.line_thickness * 0.48, False, "green-row")
            for i in range(5):
                x = -1.35 + i * 0.68
                app.add_polyline(holder, [Vec3(x, row, 0.10), Vec3(x - 0.28, row + 0.22, 0.84)], col, app.cfg.line_thickness * 0.45, False, "green-leaf-l")
                app.add_polyline(holder, [Vec3(x, row, 0.10), Vec3(x + 0.28, row - 0.22, 0.92)], col, app.cfg.line_thickness * 0.45, False, "green-leaf-r")
                if i % 2 == 0:
                    _marker(app, holder, Vec3(x, row, 0.26), 0.20, accent, "green-produce")

    def _draw_tree(app, holder, entry, selected=False, fruit_tree=False):
        col, accent, trunk = entry["color"], entry["accent"], entry["trunk"]
        height = 7.8 if fruit_tree else 8.6
        canopy_r = 2.8 if fruit_tree else 3.1
        _ring(app, holder, canopy_r * 1.15, col, selected)
        app.add_prism(holder, 0.44, height * 0.70, trunk, count=7, thickness_scale=0.70)
        branch_z = height * 0.42
        for i in range(8):
            ang = math.tau * i / 8.0 + (0.12 if fruit_tree else 0.0)
            end = Vec3(math.cos(ang) * canopy_r * 0.86, math.sin(ang) * canopy_r * 0.86, height * 0.76 + (0.18 if i % 2 else -0.08))
            app.add_polyline(holder, [Vec3(0, 0, branch_z + (i % 3) * 0.16), end], (col[0] * 0.74, col[1] * 0.82, col[2] * 0.74, 0.78), app.cfg.line_thickness * 0.46, False, "tree-branch")
        for j, (rad, alpha) in enumerate(((canopy_r, 0.72), (canopy_r * 0.74, 0.95), (canopy_r * 0.48, 0.80))):
            app.add_polyline(holder, app.polygon_points(rad, height * 0.72 + j * 0.62, 16, j * 15), (col[0], col[1], col[2], alpha), app.cfg.line_thickness * 0.58, True, "tree-canopy")
        app.add_polyline(holder, app.polygon_points(canopy_r * 0.36, height * 1.02, 12, 8), accent if not fruit_tree else (col[0] * 1.18, min(1.0, col[1] * 1.06), col[2] * 1.12, 0.80), app.cfg.line_thickness * 0.42, True, "tree-highlight")
        if fruit_tree:
            for i in range(7):
                ang = math.tau * i / 7.0 + 0.25
                _marker(app, holder, Vec3(math.cos(ang) * canopy_r * 0.58, math.sin(ang) * canopy_r * 0.58, height * 0.78 + (0.24 if i % 2 else -0.02)), 0.21, accent, "fruit")

    def draw_forest_growth_plant(self, parent, raw, *, selected=False):
        rec = _normalize_plant(self, raw, force_ground=True)
        entry = _catalog_entry(rec["type"])
        pos = Vec3(*[float(v) for v in rec["position"][:3]])
        yaw = float((rec.get("rotation") or [0.0])[0])
        holder = parent.attachNewNode(f"forest-planter-{rec['type']}")
        holder.setPos(pos)
        holder.setH(yaw)
        try:
            if rec["type"] == "berry_bush":
                _draw_bush(self, holder, entry, selected)
            elif rec["type"] == "garden_greens":
                _draw_greens(self, holder, entry, selected)
            elif rec["type"] == "fruit_tree":
                _draw_tree(self, holder, entry, selected, fruit_tree=True)
            else:
                _draw_tree(self, holder, entry, selected, fruit_tree=False)
        except Exception as exc:
            print(f"forest_planter_draw_error: {exc}")
        return holder

    def redraw_forest_growth(self):
        _ensure_runtime_nodes(self)
        _remove_drawn_nodes(self)
        plants = []
        nodes = []
        for idx, raw in enumerate(list(getattr(self, "forest_growth_plants", []) or [])[-FOREST_MAX_PLANTS:]):
            try:
                rec = _normalize_plant(self, raw, force_ground=True)
                plants.append(rec)
                nodes.append(draw_forest_growth_plant(self, self.forest_growth_root, rec, selected=(idx == int(getattr(self, "forest_growth_selected_index", -1)))))
            except Exception as exc:
                print(f"forest_planter_redraw_plant_error: {exc}")
        self.forest_growth_plants = plants
        self.forest_growth_nodes = nodes
        update_forest_growth_ui(self)

    def update_forest_growth_ui(self):
        if not bool(getattr(self, "forest_growth_active", False)):
            return
        try:
            plants = list(getattr(self, "forest_growth_plants", []) or [])
            selected = int(getattr(self, "forest_growth_selected_index", -1))
            selected_text = "none"
            if 0 <= selected < len(plants):
                selected_text = _catalog_entry(plants[selected].get("type"))["label"]
            remaining = max(0, FOREST_MAX_PLANTS - len(plants))
            if self.forest_growth_ui_tool is not None:
                self.forest_growth_ui_tool["text"] = f"Random full-grown plants  |  Placed: {len(plants)}/{FOREST_MAX_PLANTS}  |  Slots left: {remaining}  |  Selected: {selected_text}"
            if self.forest_growth_ui_help is not None:
                self.forest_growth_ui_help["text"] = "LMB places one random plant where you aim at the ground.  E also places.  X inspect nearest.  Del removes selected.  G saves.  Esc saves + exits."
        except Exception as exc:
            print(f"forest_planter_ui_error: {exc}")

    def forest_growth_place_random_plant(self, source="mouse1"):
        if not bool(getattr(self, "forest_growth_active", False)):
            return False
        plants = list(getattr(self, "forest_growth_plants", []) or [])[-FOREST_MAX_PLANTS:]
        if len(plants) >= FOREST_MAX_PLANTS:
            self.forest_growth_plants = plants
            self.center_hint["text"] = f"FOREST PLANTER // LIMIT REACHED ({FOREST_MAX_PLANTS}) // DELETE ONE TO PLACE MORE"
            update_forest_growth_ui(self)
            return True
        rec = _random_plant_record(self)
        for old in plants:
            try:
                dx = float(old["position"][0]) - float(rec["position"][0])
                dy = float(old["position"][1]) - float(rec["position"][1])
                if math.sqrt(dx * dx + dy * dy) < 0.75:
                    self.center_hint["text"] = "FOREST PLANTER // MOVE AIM SLIGHTLY BEFORE PLACING ANOTHER"
                    return True
            except Exception:
                pass
        plants.append(rec)
        self.forest_growth_plants = plants
        self.forest_growth_selected_index = len(plants) - 1
        self.forest_growth_dirty = True
        redraw_forest_growth(self)
        self.center_hint["text"] = f"FOREST PLANTER // PLACED {rec['label'].upper()} // {len(plants)}/{FOREST_MAX_PLANTS}"
        if getattr(self, "audio", None):
            self.audio.play("artifact_link.wav", "sfx", 0.34)
        return True

    def forest_growth_find_nearest(self, max_distance=28.0):
        try:
            origin = self.head_world_pos()
        except Exception:
            origin = Vec3(float(getattr(self.player_pos, "x", 0.0)), float(getattr(self.player_pos, "y", 0.0)), 0.0)
        best_idx, best_dist = -1, 999999.0
        for idx, raw in enumerate(list(getattr(self, "forest_growth_plants", []) or [])):
            try:
                p = raw.get("position") or [0, 0, 0]
                dist = math.sqrt((float(p[0]) - float(origin.x)) ** 2 + (float(p[1]) - float(origin.y)) ** 2)
                if dist < best_dist and dist <= float(max_distance):
                    best_idx, best_dist = idx, dist
            except Exception:
                pass
        return best_idx, best_dist

    def forest_growth_inspect_nearest(self):
        if not bool(getattr(self, "forest_growth_active", False)):
            return False
        idx, _dist = forest_growth_find_nearest(self)
        if idx < 0:
            self.forest_growth_selected_index = -1
            redraw_forest_growth(self)
            self.center_hint["text"] = "FOREST PLANTER // NO PLANT NEARBY"
            return True
        self.forest_growth_selected_index = idx
        rec = self.forest_growth_plants[idx]
        entry = _catalog_entry(rec.get("type"))
        redraw_forest_growth(self)
        self.center_hint["text"] = f"{entry['label'].upper()} // FULL GROWN // GROUNDED"
        return True

    def forest_growth_delete_selected(self):
        if not bool(getattr(self, "forest_growth_active", False)):
            return False
        idx = int(getattr(self, "forest_growth_selected_index", -1))
        if idx < 0 or idx >= len(getattr(self, "forest_growth_plants", []) or []):
            idx, _dist = forest_growth_find_nearest(self)
        if idx < 0 or idx >= len(getattr(self, "forest_growth_plants", []) or []):
            self.center_hint["text"] = "FOREST PLANTER // NO PLANT SELECTED"
            return True
        rec = self.forest_growth_plants.pop(idx)
        self.forest_growth_selected_index = -1
        self.forest_growth_dirty = True
        redraw_forest_growth(self)
        self.center_hint["text"] = f"FOREST PLANTER // REMOVED {str(rec.get('label', 'PLANT')).upper()}"
        return True

    def activate_forest_growth_from_mode(self, mode=None, source="core", route=""):
        if bool(getattr(self, "holoforge_active", False)):
            try:
                self.deactivate_holoforge(reason="forest-planter-open")
            except Exception:
                pass
        if not _forest_allowed(self):
            try:
                self.travel_to_holoverse_region_index(FOREST_REGION_NUMBER)
            except Exception:
                pass
        _ensure_dirs()
        _ensure_runtime_nodes(self)
        if not bool(getattr(self, "forest_growth_loaded", False)):
            load_forest_growth(self)
        self.forest_growth_active = True
        self.forest_growth_root.show()
        self.forest_growth_ui_root.show()
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
        label = str((mode or {}).get("name") or "Forest Growth")
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
            self.record_matrixcore_dimension_signal("dimension_launch", label, label=label, route=IN_WORLD_ROUTE, source=str(source or "core"), reason="forest_planter_region_runtime")
            self.record_matrixcore_bot_signal("bot_launch", "Vanta", "FORESTS", "Forest Growth", route=IN_WORLD_ROUTE, source="forest_planter_runtime")
        except Exception:
            pass
        try:
            self._append_mode_gateway_history("forest_planter_runtime_open", mode=mode, label=label, route=IN_WORLD_ROUTE, extra={"source": source, "plant_count": len(self.forest_growth_plants), "state": str(STATE_PATH)})
        except Exception:
            pass
        _sync_progression_save(self, reason="activate")
        redraw_forest_growth(self)
        self.center_hint["text"] = f"FOREST PLANTER // LMB RANDOM FULL-GROWN PLANT // {FOREST_MAX_PLANTS} MAX"
        if getattr(self, "audio", None):
            self.audio.play("world_shift.wav", "sfx", 0.52)
        return True

    def deactivate_forest_growth(self, reason="closed"):
        if not bool(getattr(self, "forest_growth_active", False)):
            return False
        save_forest_growth(self, reason=reason)
        self.forest_growth_active = False
        for attr in ("forest_growth_ui_root", "forest_growth_root"):
            try:
                node = getattr(self, attr, None)
                if node is not None and not node.isEmpty():
                    node.hide()
            except Exception:
                pass
        try:
            self._append_mode_gateway_history("forest_planter_runtime_close", label="Forest Growth", route=IN_WORLD_ROUTE, extra={"reason": reason, "plant_count": len(self.forest_growth_plants), "state": str(STATE_PATH)})
        except Exception:
            pass
        try:
            self.center_hint["text"] = "FOREST PLANTER // SAVED + CLOSED"
        except Exception:
            pass
        return True

    def update_forest_growth(self, dt=0.0):
        if not bool(getattr(self, "forest_growth_active", False)):
            return
        if not _forest_allowed(self):
            deactivate_forest_growth(self, reason="left-forest-region")
            return
        if bool(getattr(self, "forest_growth_dirty", False)) and (time.time() - float(getattr(self, "forest_growth_last_save_at", 0.0))) > 18.0:
            save_forest_growth(self, reason="autosave")

    CommandHubApp.is_forest_growth_mode = _is_forest_mode
    CommandHubApp.activate_forest_growth_from_mode = activate_forest_growth_from_mode
    CommandHubApp.deactivate_forest_growth = deactivate_forest_growth
    CommandHubApp.save_forest_growth = save_forest_growth
    CommandHubApp.load_forest_growth = load_forest_growth
    CommandHubApp.redraw_forest_growth = redraw_forest_growth
    CommandHubApp.update_forest_growth = update_forest_growth
    CommandHubApp.update_forest_growth_ui = update_forest_growth_ui
    CommandHubApp.forest_growth_place_random_plant = forest_growth_place_random_plant
    CommandHubApp.forest_growth_inspect_nearest = forest_growth_inspect_nearest
    CommandHubApp.forest_growth_delete_selected = forest_growth_delete_selected

    old_init = CommandHubApp.__init__
    def __init__(self, *args, **kwargs):
        old_init(self, *args, **kwargs)
        _init_state(self)
    CommandHubApp.__init__ = __init__

    old_setup_input = CommandHubApp.setup_input
    def setup_input(self, *args, **kwargs):
        return old_setup_input(self, *args, **kwargs)
    CommandHubApp.setup_input = setup_input

    old_e = CommandHubApp.on_e_down
    def on_e_down(self):
        if bool(getattr(self, "forest_growth_active", False)):
            self.set_key("e", True)
            self.forest_growth_place_random_plant(source="e")
            return
        return old_e(self)
    CommandHubApp.on_e_down = on_e_down

    old_q = CommandHubApp.on_q_down
    def on_q_down(self):
        if bool(getattr(self, "forest_growth_active", False)):
            self.set_key("q", True)
            self.center_hint["text"] = "FOREST PLANTER // TYPES ARE RANDOM NOW"
            return
        return old_q(self)
    CommandHubApp.on_q_down = on_q_down

    old_primary = CommandHubApp.primary_click_interact
    def primary_click_interact(self):
        if bool(getattr(self, "forest_growth_active", False)):
            self.forest_growth_place_random_plant(source="mouse1")
            return
        return old_primary(self)
    CommandHubApp.primary_click_interact = primary_click_interact

    old_start_escape_hold = CommandHubApp.start_escape_hold
    def start_escape_hold(self):
        if bool(getattr(self, "forest_growth_active", False)):
            self.deactivate_forest_growth(reason="escape")
            return
        return old_start_escape_hold(self)
    CommandHubApp.start_escape_hold = start_escape_hold

    old_delete = getattr(CommandHubApp, "holoforge_delete_selected", None)
    if callable(old_delete):
        def holoforge_delete_selected(self):
            if bool(getattr(self, "forest_growth_active", False)):
                return self.forest_growth_delete_selected()
            return old_delete(self)
        CommandHubApp.holoforge_delete_selected = holoforge_delete_selected

    old_g_save = getattr(CommandHubApp, "holoforge_save_blueprint", None)
    if callable(old_g_save):
        def holoforge_save_blueprint(self):
            if bool(getattr(self, "forest_growth_active", False)):
                return self.save_forest_growth(reason="manual")
            return old_g_save(self)
        CommandHubApp.holoforge_save_blueprint = holoforge_save_blueprint

    old_x_select = getattr(CommandHubApp, "holoforge_select_or_clear", None)
    if callable(old_x_select):
        def holoforge_select_or_clear(self):
            if bool(getattr(self, "forest_growth_active", False)):
                return self.forest_growth_inspect_nearest()
            return old_x_select(self)
        CommandHubApp.holoforge_select_or_clear = holoforge_select_or_clear

    old_b_snap = getattr(CommandHubApp, "holoforge_toggle_snap", None)
    if callable(old_b_snap):
        def holoforge_toggle_snap(self):
            if bool(getattr(self, "forest_growth_active", False)):
                self.center_hint["text"] = "FOREST PLANTER // SNAP GRID REMOVED"
                return True
            return old_b_snap(self)
        CommandHubApp.holoforge_toggle_snap = holoforge_toggle_snap

    old_route = CommandHubApp.launch_core_mode_route
    def launch_core_mode_route(self, mode, source="core", extra_env=None, close_core=True):
        if self.is_forest_growth_mode(mode):
            return bool(self.activate_forest_growth_from_mode(mode, source=source, route=IN_WORLD_ROUTE))
        return old_route(self, mode, source=source, extra_env=extra_env, close_core=close_core)
    CommandHubApp.launch_core_mode_route = launch_core_mode_route

    old_region_ui = CommandHubApp.update_holoverse_region_ui
    def update_holoverse_region_ui(self):
        result = old_region_ui(self)
        if bool(getattr(self, "forest_growth_active", False)):
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
                self.update_forest_growth(0.0)
        except Exception as exc:
            print(f"forest_planter_update_error: {exc}")
        return result
    CommandHubApp.update_task = update_task

    setattr(main, "FOREST_GROWTH_RUNTIME_INSTALLED", True)
    setattr(main, "FOREST_GROWTH_STATE_PATH_RUNTIME", STATE_PATH)
