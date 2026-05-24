"""In-world Hills Life runtime for the live GREEN HILLS HoloVerse region.

Nyx/Hills of Life no longer opens a placeholder panel for this route. It mounts an
animal-life layer inside the current hills region, lets the player create smart
animals as full-grown lifeforms, saves every animal into shared
HoloVerse data, and mirrors progress into the player progression save.
"""
from __future__ import annotations

import json
import math
import random
import sys
import time
from datetime import date, datetime
from pathlib import Path

from direct.gui.DirectGui import DirectFrame, DirectLabel
from panda3d.core import TextNode, Vec3

IN_WORLD_ROUTE = "in_world_region"
HILLS_LIFE_SCHEMA = 1
HILLS_REGION_NUMBER = 2
MAX_HILLS_LIFEFORMS = 40


def _main_module(cls):
    return sys.modules.get(cls.__module__) or sys.modules.get("__main__")


def install_hills_life_runtime(CommandHubApp):
    main = _main_module(CommandHubApp)
    if main is None:
        return

    from holoverse_mode_runtime import resolve_accidental_nested_data_root, resolve_shared_data_root

    ROOT = Path(getattr(main, "ROOT", Path(__file__).resolve().parent))
    SHARED_DATA_ROOT = resolve_shared_data_root(main, ROOT)
    LEGACY_SHARED_DATA_ROOT = resolve_accidental_nested_data_root(ROOT)
    STATE_DIR = SHARED_DATA_ROOT / "holoverse" / "regions" / "hills" / "life"
    STATE_PATH = STATE_DIR / "hills_life_state.json"
    LEGACY_STATE_PATH = LEGACY_SHARED_DATA_ROOT / "holoverse" / "regions" / "hills" / "life" / "hills_life_state.json"
    ROOT_PROGRESS_PATH = ROOT / "progression" / "progression_state.json"
    SHARED_PROGRESS_PATH = SHARED_DATA_ROOT / "holoverse" / "progression" / "progression_state.json"

    from holoverse_mode_runtime import install_in_world_route_aliases

    install_in_world_route_aliases(main)

    def _ensure_dirs():
        for folder in (STATE_DIR, ROOT_PROGRESS_PATH.parent, SHARED_PROGRESS_PATH.parent, SHARED_DATA_ROOT / "brain", SHARED_DATA_ROOT / "database"):
            folder.mkdir(parents=True, exist_ok=True)

    def _today_key() -> str:
        return date.today().isoformat()

    def _safe_days_since(day_text: str) -> int:
        try:
            created = date.fromisoformat(str(day_text or "")[:10])
            return max(0, int((date.today() - created).days))
        except Exception:
            return 0

    def _stage_for_life(raw) -> int:
        # Current Hills mode places full-grown animals immediately.
        # The old egg/young daily-growth stages are intentionally bypassed so
        # every animal reads as an animal the moment the player creates it.
        return 3

    def _clamp_trait(value, default=5) -> int:
        try:
            return max(1, min(10, int(round(float(value)))))
        except Exception:
            return int(default)

    def _life_catalog(self):
        return [
            {
                "id": "cat",
                "label": "Cats",
                "single": "Cat",
                "gift": "feline_insight",
                "yield": 1,
                "color": (0.94, 0.82, 0.48, 0.92),
                "accent": (1.00, 0.96, 0.70, 0.96),
                "spacing": 6.0,
                "trait_base": {"curiosity": 9, "loyalty": 3, "mischief": 6, "bravery": 5, "intelligence": 7},
                "personality": "curious, independent, sneaky",
            },
            {
                "id": "dog",
                "label": "Dogs",
                "single": "Dog",
                "gift": "loyalty_spark",
                "yield": 1,
                "color": (0.72, 0.92, 1.00, 0.92),
                "accent": (1.00, 1.00, 0.86, 0.96),
                "spacing": 7.0,
                "trait_base": {"curiosity": 6, "loyalty": 10, "mischief": 3, "bravery": 7, "intelligence": 6},
                "personality": "loyal, social, protective",
            },
            {
                "id": "ape",
                "label": "Apes",
                "single": "Ape",
                "gift": "tool_memory",
                "yield": 1,
                "color": (0.78, 0.58, 0.36, 0.92),
                "accent": (1.00, 0.78, 0.44, 0.96),
                "spacing": 8.0,
                "trait_base": {"curiosity": 8, "loyalty": 5, "mischief": 6, "bravery": 7, "intelligence": 10},
                "personality": "clever, playful, tool-using",
            },
            {
                "id": "crow",
                "label": "Crows",
                "single": "Crow",
                "gift": "sky_memory",
                "yield": 1,
                "color": (0.28, 0.34, 0.46, 0.92),
                "accent": (0.80, 0.92, 1.00, 0.96),
                "spacing": 7.0,
                "trait_base": {"curiosity": 8, "loyalty": 4, "mischief": 9, "bravery": 6, "intelligence": 9},
                "personality": "observant, mischievous, strategic",
            },
        ]

    def _catalog_entry(self, animal_type=None):
        catalog = _life_catalog(self)
        raw = str(animal_type or catalog[int(getattr(self, "hills_life_type_index", 0)) % len(catalog)]["id"]).strip().lower()
        aliases = {
            "cats": "cat", "kitten": "cat", "kittens": "cat",
            "dogs": "dog", "puppy": "dog", "puppies": "dog",
            "apes": "ape", "monkey": "ape", "monkeys": "ape",
            "crows": "crow", "bird": "crow", "birds": "crow",
        }
        raw = aliases.get(raw, raw)
        for entry in catalog:
            if entry["id"] == raw:
                return entry
        return catalog[0]

    def _init_state(self):
        self.hills_life_active = False
        self.hills_life_loaded = False
        self.hills_life_root = None
        self.hills_life_ghost_root = None
        self.hills_life_ui_root = None
        self.hills_life_ui_panel = None
        self.hills_life_ui_title = None
        self.hills_life_ui_tool = None
        self.hills_life_ui_help = None
        self.hills_life_animals = []
        self.hills_life_nodes = []
        self.hills_life_selected_index = -1
        self.hills_life_type_index = 0
        self.hills_life_snap_enabled = True
        self.hills_life_grid_step = 4.0
        self.hills_life_last_day = _today_key()
        self.hills_life_last_save_at = 0.0
        self.hills_life_last_move_at = 0.0
        self.hills_life_dirty = False
        self.hills_life_inventory = {}
        self.hills_life_state_path = STATE_PATH

    def _is_hills_life_mode(self, mode):
        data = dict(mode or {})
        manifest = dict(data.get("manifest") or {})
        tokens = " ".join(str(x or "") for x in (
            data.get("name"), data.get("id"), data.get("title"),
            manifest.get("id"), manifest.get("title"), manifest.get("description"),
            manifest.get("host_contract"), manifest.get("preferred_display"),
            manifest.get("region_owner"), manifest.get("bot_owner"),
        )).lower()
        return (
            "hills life" in tokens or "hills of life" in tokens
            or "smart animal" in tokens
            or "nyx" in tokens and "life" in tokens
            or "green hills" in tokens and "hills_of_life" in tokens
            or str(manifest.get("id") or data.get("id") or "").lower() == "hills_of_life"
            or str(data.get("name") or "").lower() == "hills_of_life"
        )

    def _hills_allowed(self):
        try:
            if self.is_holospace_active():
                return False
        except Exception:
            pass
        try:
            return int(self.current_holoverse_region_number()) == HILLS_REGION_NUMBER
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

    def _snap_xy(self, value: float) -> float:
        if not bool(getattr(self, "hills_life_snap_enabled", True)):
            return round(float(value), 3)
        step = max(1.0, float(getattr(self, "hills_life_grid_step", 4.0)))
        return round(round(float(value) / step) * step, 3)

    def _placement_xy(self, distance=12.0):
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
        return _snap_xy(self, x), _snap_xy(self, y)

    def _trait_roll(entry, seed_value=None, existing=None):
        if isinstance(existing, dict) and existing:
            return {k: _clamp_trait(existing.get(k), default=v) for k, v in entry["trait_base"].items()}
        rng = random.Random(str(seed_value or f"{entry['id']}:{time.time()}"))
        traits = {}
        for key, base in entry["trait_base"].items():
            traits[key] = _clamp_trait(int(base) + rng.choice([-2, -1, 0, 0, 1, 2]), default=int(base))
        return traits

    def _normalize_life(self, raw, *, force_ground=True):
        raw = dict(raw or {})
        entry = _catalog_entry(self, raw.get("type") or raw.get("animal_type"))
        pos_raw = raw.get("position") or raw.get("pos") or None
        if pos_raw is None:
            x, y = _placement_xy(self)
            z = _floor_z(self, x, y)
        else:
            try:
                x = float(pos_raw[0]); y = float(pos_raw[1]); z = float(pos_raw[2])
            except Exception:
                x, y = _placement_xy(self)
                z = _floor_z(self, x, y)
        if bool(getattr(self, "hills_life_snap_enabled", True)) and not bool(raw.get("moving_runtime")):
            x, y = _snap_xy(self, x), _snap_xy(self, y)
        if force_ground:
            z = _floor_z(self, x, y)
        created_day = str(raw.get("created_day") or raw.get("created_at") or _today_key())[:10]
        try:
            date.fromisoformat(created_day)
        except Exception:
            created_day = _today_key()
        animal_id = str(raw.get("id") or f"life_{int(time.time() * 1000)}_{len(getattr(self, 'hills_life_animals', [])) + 1}")
        seed_value = raw.get("seed") or animal_id
        stage = _stage_for_life({**raw, "created_day": created_day})
        last_collected_day = str(raw.get("last_collected_day") or "")[:10]
        traits = _trait_roll(entry, seed_value=seed_value, existing=raw.get("traits"))
        home = raw.get("home_position") or raw.get("home") or [x, y, z]
        try:
            hx, hy, hz = float(home[0]), float(home[1]), float(home[2])
        except Exception:
            hx, hy, hz = x, y, z
        name = str(raw.get("name") or f"{entry['single']}_{str(animal_id)[-4:]}")
        return {
            "id": animal_id,
            "name": name,
            "type": entry["id"],
            "label": entry["single"],
            "position": [round(float(x), 3), round(float(y), 3), round(float(z), 3)],
            "home_position": [round(float(hx), 3), round(float(hy), 3), round(float(hz), 3)],
            "rotation": [round(float(raw.get("yaw", (raw.get("rotation") or [0.0])[0] if isinstance(raw.get("rotation"), list) else 0.0)) % 360.0, 3), 0.0, 0.0],
            "created_day": created_day,
            "created_at": str(raw.get("created_at") or datetime.now().isoformat(timespec="seconds")),
            "stage": int(stage),
            "traits": traits,
            "personality": entry["personality"],
            "gift": entry["gift"],
            "yield": int(entry["yield"]),
            "last_collected_day": last_collected_day if last_collected_day else "",
            "seed": str(seed_value),
            "wander_angle": float(raw.get("wander_angle", 0.0) or 0.0),
        }

    def _current_life_record(self):
        entry = _catalog_entry(self)
        x, y = _placement_xy(self)
        animal_id = f"life_{int(time.time() * 1000)}_{len(getattr(self, 'hills_life_animals', [])) + 1}"
        return _normalize_life(self, {
            "id": animal_id,
            "name": f"{entry['single']}_{len(getattr(self, 'hills_life_animals', [])) + 1:03d}",
            "type": entry["id"],
            "position": [x, y, _floor_z(self, x, y)],
            "home_position": [x, y, _floor_z(self, x, y)],
            "created_day": _today_key(),
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "force_stage": True,
            "stage": 3,
            "last_collected_day": "",
            "seed": animal_id,
        })

    def _read_state(self):
        _ensure_dirs()
        for path in (STATE_PATH, LEGACY_STATE_PATH):
            if path == LEGACY_STATE_PATH and not path.exists():
                continue
            try:
                if path.exists():
                    data = json.loads(path.read_text(encoding="utf-8"))
                    if isinstance(data, dict):
                        return data
            except Exception as exc:
                print(f"hills_life_state_read_error {path}: {exc}")
        return {"animals": [], "inventory": {}}

    def _write_json(path: Path, payload: dict):
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(path)

    def _sync_progression_save(self, reason="save"):
        animals = list(getattr(self, "hills_life_animals", []) or [])
        summary = {
            "schema": HILLS_LIFE_SCHEMA,
            "state_path": str(STATE_PATH),
            "region": "green_hills",
            "owner_bot": "Nyx",
            "mode": "Hills of Life",
            "dimension": "Hills of Life",
            "total_animals": len(animals),
            "mature_animals": sum(1 for a in animals if _stage_for_life(a) >= 3),
            "inventory": dict(getattr(self, "hills_life_inventory", {}) or {}),
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
                data.setdefault("dimension_blueprints", {})["hills_of_life"] = {
                    "owner_bot": "Nyx",
                    "status": "playable_in_world_region",
                    "tool": "Hills of Life",
                    "state": str(STATE_PATH),
                }
                data.setdefault("hills_life", {}).update(summary)
                visits = data.setdefault("dimension_visits", {})
                puzzle = visits.setdefault("Hills of Life", {})
                puzzle["count"] = int(puzzle.get("count", 0)) + (1 if reason == "activate" else 0)
                puzzle["last_at"] = datetime.now().isoformat(timespec="seconds")
                puzzle["route"] = IN_WORLD_ROUTE
                puzzle["reason"] = "hills_life_region_runtime"
                puzzle["source"] = "region_bot:Nyx"
                _write_json(path, data)
            except Exception as exc:
                print(f"hills_life_progression_sync_error {path}: {exc}")
        return summary

    def save_hills_life(self, reason="manual"):
        _ensure_dirs()
        animals = []
        for raw in list(getattr(self, "hills_life_animals", []) or []):
            rec = _normalize_life(self, {**raw, "moving_runtime": True}, force_ground=True)
            rec["stage"] = _stage_for_life(rec)
            animals.append(rec)
        self.hills_life_animals = animals
        payload = {
            "schema": HILLS_LIFE_SCHEMA,
            "kind": "holoverse_hills_life_state",
            "save_authority": "shared_data_holoverse_region_layer",
            "region": "green_hills",
            "region_number": HILLS_REGION_NUMBER,
            "owner_bot": "Nyx",
            "mode": "Hills of Life",
            "growth_rule": "full_grown_on_placement",
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "today": _today_key(),
            "animal_types": [e["id"] for e in _life_catalog(self)],
            "population_cap": MAX_HILLS_LIFEFORMS,
            "inventory": dict(getattr(self, "hills_life_inventory", {}) or {}),
            "animals": animals,
            "summary": {
                "total_animals": len(animals),
                "stage_1": 0,
                "stage_2": 0,
                "stage_3": len(animals),
            },
        }
        try:
            _write_json(STATE_PATH, payload)
            # Do not mirror saves into the old accidental <app>/data/data lane.
            self.hills_life_dirty = False
            self.hills_life_last_save_at = time.time()
            _sync_progression_save(self, reason=str(reason or "save"))
            try:
                self.center_hint["text"] = f"HILLS LIFE // SAVED {len(animals)} ANIMALS"
            except Exception:
                pass
        except Exception as exc:
            try:
                self.center_hint["text"] = f"HILLS LIFE // SAVE FAILED // {exc}"
            except Exception:
                pass
            print(f"hills_life_save_error: {exc}")
        return True

    def load_hills_life(self):
        data = _read_state(self)
        inv = data.get("inventory", {}) if isinstance(data, dict) else {}
        self.hills_life_inventory = dict(inv) if isinstance(inv, dict) else {}
        animals = []
        for raw in list((data or {}).get("animals", []) or []):
            if isinstance(raw, dict):
                animals.append(_normalize_life(self, raw, force_ground=True))
        self.hills_life_animals = animals[:MAX_HILLS_LIFEFORMS]
        self.hills_life_loaded = True
        self.hills_life_last_day = _today_key()
        return animals

    def _hills_runtime_parent(self):
        """Visible parent for Hills Life animals.

        The HoloVerse shell can stash/hide root_3d while normal regions are
        being streamed.  Spawned animals must live under render so the same
        first-person region route that shows Green Hills also shows the life
        runtime.
        """
        try:
            return self.render
        except Exception:
            return self.root_3d

    def _ensure_runtime_nodes(self):
        parent = _hills_runtime_parent(self)
        if getattr(self, "hills_life_root", None) is None or self.hills_life_root.isEmpty():
            self.hills_life_root = parent.attachNewNode("hills-life-region-layer")
        else:
            try:
                self.hills_life_root.reparentTo(parent)
            except Exception:
                pass
        if getattr(self, "hills_life_ghost_root", None) is None or self.hills_life_ghost_root.isEmpty():
            self.hills_life_ghost_root = parent.attachNewNode("hills-life-preview-layer")
        else:
            try:
                self.hills_life_ghost_root.reparentTo(parent)
            except Exception:
                pass
        if getattr(self, "hills_life_ui_root", None) is None or self.hills_life_ui_root.isEmpty():
            self.hills_life_ui_root = self.hud_root.attachNewNode("hills-life-ui")
            self.hills_life_ui_panel = DirectFrame(
                parent=self.hills_life_ui_root,
                frameColor=(0.025, 0.018, 0.040, 0.30),
                frameSize=(0.0, 1.02, -0.22, 0.045),
                pos=(-1.24, 0, -0.36),
                relief=None,
            )
            self.hills_life_ui_title = DirectLabel(
                parent=self.hills_life_ui_panel,
                text="HILLS LIFE",
                text_align=TextNode.ALeft,
                text_scale=0.030,
                text_fg=(0.90, 0.76, 1.0, 0.96),
                frameColor=(0, 0, 0, 0),
                pos=(0.025, 0, 0.004),
                textMayChange=True,
            )
            self.hills_life_ui_tool = DirectLabel(
                parent=self.hills_life_ui_panel,
                text="",
                text_align=TextNode.ALeft,
                text_scale=0.023,
                text_fg=(1.0, 0.86, 0.34, 0.94),
                frameColor=(0, 0, 0, 0),
                pos=(0.025, 0, -0.060),
                text_wordwrap=48,
                textMayChange=True,
            )
            self.hills_life_ui_help = DirectLabel(
                parent=self.hills_life_ui_panel,
                text="",
                text_align=TextNode.ALeft,
                text_scale=0.020,
                text_fg=(0.88, 1.0, 0.82, 0.92),
                frameColor=(0, 0, 0, 0),
                pos=(0.025, 0, -0.122),
                text_wordwrap=52,
                textMayChange=True,
            )
        try:
            self.hills_life_root.show(); self.hills_life_ghost_root.show(); self.hills_life_ui_root.show()
        except Exception:
            pass

    def _remove_drawn_nodes(self):
        for node in list(getattr(self, "hills_life_nodes", []) or []):
            try:
                if node is not None and not node.isEmpty():
                    node.removeNode()
            except Exception:
                pass
        self.hills_life_nodes = []
        try:
            if getattr(self, "hills_life_ghost_root", None) is not None:
                self.hills_life_ghost_root.getChildren().detach()
        except Exception:
            pass

    def _color_for(entry, alpha=None):
        c = tuple(entry.get("color", (0.8, 0.8, 0.8, 0.9)))
        return (c[0], c[1], c[2], float(alpha) if alpha is not None else c[3])

    def _accent_for(entry, alpha=None):
        c = tuple(entry.get("accent", (1.0, 1.0, 1.0, 0.96)))
        return (c[0], c[1], c[2], float(alpha) if alpha is not None else c[3])

    def _gift_ready(rec) -> bool:
        return _stage_for_life(rec) >= 3 and str(rec.get("last_collected_day") or "")[:10] != _today_key()

    def _draw_marker_ring(self, holder, radius, col, selected=False, ready=False):
        try:
            z = 0.07
            width = self.cfg.line_thickness * (0.92 if selected else 0.50)
            if selected:
                ring_col = (1.0, 0.84, 0.22, 0.92)
            elif ready:
                ring_col = (0.55, 1.0, 0.25, 0.72)
            else:
                ring_col = (col[0], col[1], col[2], 0.34)
            self.add_polyline(holder, self.polygon_points(radius, z, 28, 0.0), ring_col, width, True, "hills-life-ring")
        except Exception:
            pass

    def _draw_life_spark(self, holder, stage, entry, ghost=False, selected=False, ready=False):
        col = _color_for(entry, 0.40 if ghost else None)
        acc = _accent_for(entry, 0.46 if ghost else None)
        scale = [0.75, 1.0, 1.2][max(1, stage) - 1]
        _draw_marker_ring(self, holder, 1.75 * scale, col, selected, ready)
        self.add_box(holder, Vec3(0, 0, 0.36 * scale), Vec3(0.42, 0.42, 0.52) * scale, acc, 0.58)
        for i in range(4):
            a = math.tau * i / 4.0 + math.radians(45)
            self.add_polyline(holder, [Vec3(0, 0, 0.35 * scale), Vec3(math.cos(a) * 0.95 * scale, math.sin(a) * 0.95 * scale, 0.62 * scale)], col, self.cfg.line_thickness * 0.46, False, "life-spark")

    def _draw_visibility_beacon(self, holder, stage, entry, ghost=False, selected=False, ready=False):
        if ghost:
            return
        col = _color_for(entry, 0.86)
        acc = _accent_for(entry, 0.95)
        mast_h = 4.2 if stage <= 1 else (5.0 if stage == 2 else 6.2)
        width = max(1.0, self.cfg.line_thickness * (0.60 if stage <= 1 else 0.46))
        self.add_polyline(holder, [Vec3(0, 0, 0.12), Vec3(0, 0, mast_h)], col, width, False, "hills-life-visible-mast")
        self.add_box(holder, Vec3(0, 0, mast_h + 0.18), Vec3(0.58, 0.58, 0.58), acc if (selected or ready or stage <= 1) else col, 0.72)
        self.add_polyline(holder, self.polygon_points(0.56, mast_h + 0.18, 16, 0.0), acc, max(1.0, self.cfg.line_thickness * 0.34), True, "hills-life-visible-crown")

    def _draw_cat(self, holder, stage, entry, ghost=False, selected=False, ready=False):
        col = _color_for(entry, 0.40 if ghost else None)
        acc = _accent_for(entry, 0.46 if ghost else None)
        scale = 1.18 if stage <= 1 else (1.55 if stage == 2 else 1.95)
        _draw_marker_ring(self, holder, 2.15 * scale, col, selected, ready)
        self.add_box(holder, Vec3(0.0, 0.0, 0.58 * scale), Vec3(1.35, 0.60, 0.46) * scale, col, 0.64)
        self.add_box(holder, Vec3(0.82 * scale, 0.0, 0.82 * scale), Vec3(0.52, 0.48, 0.46) * scale, col, 0.62)
        # ears, legs, whiskers, tail
        self.add_polyline(holder, [Vec3(0.66 * scale, -0.14 * scale, 1.08 * scale), Vec3(0.78 * scale, -0.18 * scale, 1.42 * scale), Vec3(0.92 * scale, -0.06 * scale, 1.08 * scale)], acc, self.cfg.line_thickness * 0.54, True, "cat-ear")
        self.add_polyline(holder, [Vec3(0.66 * scale, 0.14 * scale, 1.08 * scale), Vec3(0.78 * scale, 0.18 * scale, 1.42 * scale), Vec3(0.92 * scale, 0.06 * scale, 1.08 * scale)], acc, self.cfg.line_thickness * 0.54, True, "cat-ear")
        for x in (-0.42, 0.34):
            for y in (-0.22, 0.22):
                self.add_polyline(holder, [Vec3(x * scale, y * scale, 0.38 * scale), Vec3((x + 0.05) * scale, y * scale, 0.10 * scale)], col, self.cfg.line_thickness * 0.46, False, "cat-leg")
        self.add_polyline(holder, [Vec3(-0.72 * scale, 0, 0.72 * scale), Vec3(-1.25 * scale, 0.22 * scale, 1.05 * scale), Vec3(-1.45 * scale, 0.12 * scale, 1.34 * scale)], acc, self.cfg.line_thickness * 0.54, False, "cat-tail")
        for y in (-0.32, 0.32):
            self.add_polyline(holder, [Vec3(1.05 * scale, 0, 0.88 * scale), Vec3(1.42 * scale, y * scale, 0.93 * scale)], acc, self.cfg.line_thickness * 0.34, False, "cat-whisker")

    def _draw_dog(self, holder, stage, entry, ghost=False, selected=False, ready=False):
        col = _color_for(entry, 0.40 if ghost else None)
        acc = _accent_for(entry, 0.46 if ghost else None)
        scale = 1.20 if stage <= 1 else (1.58 if stage == 2 else 2.04)
        _draw_marker_ring(self, holder, 2.35 * scale, col, selected, ready)
        self.add_box(holder, Vec3(0.0, 0.0, 0.64 * scale), Vec3(1.70, 0.68, 0.58) * scale, col, 0.64)
        self.add_box(holder, Vec3(0.98 * scale, 0.0, 0.92 * scale), Vec3(0.58, 0.54, 0.54) * scale, col, 0.62)
        self.add_box(holder, Vec3(1.34 * scale, 0.0, 0.82 * scale), Vec3(0.34, 0.36, 0.32) * scale, acc, 0.48)
        for y in (-0.30, 0.30):
            self.add_polyline(holder, [Vec3(0.84 * scale, y * scale, 1.08 * scale), Vec3(0.68 * scale, y * scale, 0.70 * scale)], acc, self.cfg.line_thickness * 0.48, False, "dog-ear")
        for x in (-0.55, 0.48):
            for y in (-0.24, 0.24):
                self.add_polyline(holder, [Vec3(x * scale, y * scale, 0.38 * scale), Vec3((x + 0.05) * scale, y * scale, 0.10 * scale)], col, self.cfg.line_thickness * 0.50, False, "dog-leg")
        self.add_polyline(holder, [Vec3(-0.90 * scale, 0, 0.84 * scale), Vec3(-1.32 * scale, 0.12 * scale, 1.12 * scale)], acc, self.cfg.line_thickness * 0.58, False, "dog-tail")

    def _draw_ape(self, holder, stage, entry, ghost=False, selected=False, ready=False):
        col = _color_for(entry, 0.40 if ghost else None)
        acc = _accent_for(entry, 0.46 if ghost else None)
        scale = 1.14 if stage <= 1 else (1.50 if stage == 2 else 1.96)
        _draw_marker_ring(self, holder, 2.45 * scale, col, selected, ready)
        self.add_box(holder, Vec3(0, 0, 1.02 * scale), Vec3(0.92, 0.72, 1.25) * scale, col, 0.66)
        self.add_box(holder, Vec3(0.06 * scale, 0, 1.86 * scale), Vec3(0.72, 0.62, 0.58) * scale, acc, 0.58)
        for y in (-0.42, 0.42):
            self.add_polyline(holder, [Vec3(0.0, y * scale, 1.44 * scale), Vec3(-0.68 * scale, y * 1.18 * scale, 0.64 * scale), Vec3(-0.52 * scale, y * 1.24 * scale, 0.24 * scale)], col, self.cfg.line_thickness * 0.64, False, "ape-arm")
            self.add_polyline(holder, [Vec3(0.18 * scale, y * 0.42, 0.42 * scale), Vec3(0.48 * scale, y * 0.55, 0.10 * scale)], col, self.cfg.line_thickness * 0.54, False, "ape-leg")
        self.add_polyline(holder, [Vec3(-0.44 * scale, 0, 1.95 * scale), Vec3(0.50 * scale, 0, 1.95 * scale)], col, self.cfg.line_thickness * 0.34, False, "ape-brow")

    def _draw_crow(self, holder, stage, entry, ghost=False, selected=False, ready=False):
        col = _color_for(entry, 0.40 if ghost else None)
        acc = _accent_for(entry, 0.48 if ghost else None)
        scale = 1.12 if stage <= 1 else (1.46 if stage == 2 else 1.86)
        _draw_marker_ring(self, holder, 2.25 * scale, col, selected, ready)
        self.add_box(holder, Vec3(0, 0, 0.78 * scale), Vec3(0.82, 0.50, 0.54) * scale, col, 0.62)
        self.add_box(holder, Vec3(0.52 * scale, 0, 0.98 * scale), Vec3(0.38, 0.34, 0.34) * scale, col, 0.56)
        self.add_polyline(holder, [Vec3(0.72 * scale, 0, 1.00 * scale), Vec3(1.14 * scale, 0, 0.90 * scale)], acc, self.cfg.line_thickness * 0.50, False, "crow-beak")
        self.add_polyline(holder, [Vec3(-0.10 * scale, -0.25 * scale, 0.88 * scale), Vec3(-0.76 * scale, -1.10 * scale, 1.26 * scale), Vec3(0.08 * scale, -0.36 * scale, 0.70 * scale)], col, self.cfg.line_thickness * 0.58, True, "crow-wing")
        self.add_polyline(holder, [Vec3(-0.10 * scale, 0.25 * scale, 0.88 * scale), Vec3(-0.76 * scale, 1.10 * scale, 1.26 * scale), Vec3(0.08 * scale, 0.36 * scale, 0.70 * scale)], col, self.cfg.line_thickness * 0.58, True, "crow-wing")
        self.add_polyline(holder, [Vec3(-0.48 * scale, 0, 0.74 * scale), Vec3(-0.92 * scale, 0, 0.58 * scale)], acc, self.cfg.line_thickness * 0.48, False, "crow-tail")

    def draw_hills_life_animal(self, parent, raw, *, ghost=False, selected=False):
        rec = _normalize_life(self, raw, force_ground=True)
        entry = _catalog_entry(self, rec["type"])
        stage = _stage_for_life(rec)
        rec["stage"] = stage
        pos = Vec3(*[float(v) for v in rec["position"][:3]])
        # Adult/young crows get a small visual flight offset while saving their ground anchor.
        if rec["type"] == "crow" and stage >= 2 and not ghost:
            pos.z += 2.4 if stage == 2 else 4.6
        yaw = float((rec.get("rotation") or [0.0])[0])
        holder = parent.attachNewNode(f"hills-life-{rec['type']}-s{stage}")
        holder.setPos(pos)
        holder.setH(yaw)
        ready = _gift_ready(rec)
        try:
            if rec["type"] == "dog":
                _draw_dog(self, holder, stage, entry, ghost=ghost, selected=selected, ready=ready)
            elif rec["type"] == "ape":
                _draw_ape(self, holder, stage, entry, ghost=ghost, selected=selected, ready=ready)
            elif rec["type"] == "crow":
                _draw_crow(self, holder, stage, entry, ghost=ghost, selected=selected, ready=ready)
            else:
                _draw_cat(self, holder, stage, entry, ghost=ghost, selected=selected, ready=ready)
            _draw_visibility_beacon(self, holder, stage, entry, ghost=ghost, selected=selected, ready=ready)
            if stage >= 3 and ready:
                self.add_polyline(holder, self.polygon_points(2.8, 0.14, 24, 0), (0.55, 1.0, 0.28, 0.70), self.cfg.line_thickness * 0.58, True, "gift-ready-ring")
        except Exception as exc:
            print(f"hills_life_draw_error: {exc}")
        return holder

    def redraw_hills_life(self):
        _ensure_runtime_nodes(self)
        _remove_drawn_nodes(self)
        nodes = []
        for idx, raw in enumerate(list(getattr(self, "hills_life_animals", []) or [])):
            try:
                rec = _normalize_life(self, {**raw, "moving_runtime": True}, force_ground=True)
                rec["force_stage"] = True
                rec["stage"] = 3
                self.hills_life_animals[idx] = rec
                nodes.append(draw_hills_life_animal(self, self.hills_life_root, rec, selected=(idx == int(getattr(self, "hills_life_selected_index", -1)))))
            except Exception as exc:
                print(f"hills_life_redraw_animal_error: {exc}")
        self.hills_life_nodes = nodes
        update_hills_life_ui(self)

    def update_hills_life_ghost(self):
        if not bool(getattr(self, "hills_life_active", False)):
            return
        try:
            if getattr(self, "hills_life_ghost_root", None) is None or self.hills_life_ghost_root.isEmpty():
                return
            self.hills_life_ghost_root.getChildren().detach()
            rec = _current_life_record(self)
            rec["force_stage"] = True
            rec["stage"] = 3
            draw_hills_life_animal(self, self.hills_life_ghost_root, rec, ghost=True, selected=False)
        except Exception as exc:
            print(f"hills_life_ghost_error: {exc}")

    def update_hills_life_ui(self):
        if not bool(getattr(self, "hills_life_active", False)):
            return
        try:
            entry = _catalog_entry(self)
            animals = list(getattr(self, "hills_life_animals", []) or [])
            mature = sum(1 for a in animals if _stage_for_life(a) >= 3)
            ready = sum(1 for a in animals if _gift_ready(a))
            selected = int(getattr(self, "hills_life_selected_index", -1))
            selected_text = "none"
            if 0 <= selected < len(animals):
                a = animals[selected]
                tr = a.get("traits", {}) if isinstance(a.get("traits"), dict) else {}
                selected_text = f"{a.get('name', _catalog_entry(self, a.get('type'))['single'])} S{_stage_for_life(a)} I{tr.get('intelligence', '?')}"
                if _gift_ready(a):
                    selected_text += " GIFT"
            snap = "ON" if bool(getattr(self, "hills_life_snap_enabled", True)) else "OFF"
            if self.hills_life_ui_tool is not None:
                self.hills_life_ui_tool["text"] = f"Type {entry['label']} | Animals {len(animals)}/{MAX_HILLS_LIFEFORMS} | Grown {mature} | Gifts {ready} | Selected {selected_text}"
            if self.hills_life_ui_help is not None:
                self.hills_life_ui_help["text"] = "LMB/E place grown animal | Q type | X inspect | H gift | Del remove | G save | Esc save+exit"
        except Exception as exc:
            print(f"hills_life_ui_error: {exc}")

    def activate_hills_life_from_mode(self, mode=None, source="core", route=""):
        if bool(getattr(self, "holoforge_active", False)):
            try:
                self.deactivate_holoforge(reason="hills-life-open")
            except Exception:
                pass
        if bool(getattr(self, "forest_growth_active", False)):
            try:
                self.deactivate_forest_growth(reason="hills-life-open")
            except Exception:
                pass
        if not _hills_allowed(self):
            try:
                self.travel_to_holoverse_region_index(HILLS_REGION_NUMBER)
            except Exception:
                pass
        _ensure_dirs()
        _ensure_runtime_nodes(self)
        if not bool(getattr(self, "hills_life_loaded", False)):
            load_hills_life(self)
        self.hills_life_active = True
        self.hills_life_root.show(); self.hills_life_ghost_root.show(); self.hills_life_ui_root.show()
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
        label = str((mode or {}).get("name") or "Hills of Life")
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
            self.record_matrixcore_dimension_signal("dimension_launch", label, label=label, route=IN_WORLD_ROUTE, source=str(source or "core"), reason="hills_life_region_runtime")
            self.record_matrixcore_bot_signal("bot_launch", "Nyx", "GREEN HILLS", "Hills of Life", route=IN_WORLD_ROUTE, source="hills_life_runtime")
        except Exception:
            pass
        try:
            self._append_mode_gateway_history("hills_life_runtime_open", mode=mode, label=label, route=IN_WORLD_ROUTE, extra={"source": source, "animal_count": len(self.hills_life_animals), "state": str(STATE_PATH)})
        except Exception:
            pass
        _sync_progression_save(self, reason="activate")
        redraw_hills_life(self)
        self.center_hint["text"] = "HILLS LIFE // LMB PLACES FULL-GROWN ANIMALS // AUTOSAVES"
        if getattr(self, "audio", None):
            self.audio.play("world_shift.wav", "sfx", 0.52)
        return True

    def deactivate_hills_life(self, reason="closed"):
        if not bool(getattr(self, "hills_life_active", False)):
            return False
        save_hills_life(self, reason=reason)
        self.hills_life_active = False
        for attr in ("hills_life_ghost_root", "hills_life_ui_root", "hills_life_root"):
            try:
                node = getattr(self, attr, None)
                if node is not None and not node.isEmpty():
                    node.hide()
            except Exception:
                pass
        try:
            self._append_mode_gateway_history("hills_life_runtime_close", label="Hills of Life", route=IN_WORLD_ROUTE, extra={"reason": reason, "animal_count": len(self.hills_life_animals), "state": str(STATE_PATH)})
        except Exception:
            pass
        try:
            self.center_hint["text"] = "HILLS LIFE // SAVED + CLOSED"
        except Exception:
            pass
        return True

    def hills_life_cycle_type(self, direction=1):
        if not bool(getattr(self, "hills_life_active", False)):
            return False
        catalog = _life_catalog(self)
        self.hills_life_type_index = (int(getattr(self, "hills_life_type_index", 0)) + int(direction)) % len(catalog)
        update_hills_life_ui(self)
        update_hills_life_ghost(self)
        try:
            self.center_hint["text"] = f"HILLS LIFE // {catalog[self.hills_life_type_index]['label'].upper()} // {catalog[self.hills_life_type_index]['personality'].upper()}"
        except Exception:
            pass
        return True

    def hills_life_toggle_snap(self):
        if not bool(getattr(self, "hills_life_active", False)):
            return False
        self.hills_life_snap_enabled = not bool(getattr(self, "hills_life_snap_enabled", True))
        update_hills_life_ui(self)
        update_hills_life_ghost(self)
        self.center_hint["text"] = "HILLS LIFE // SNAP ON" if self.hills_life_snap_enabled else "HILLS LIFE // SNAP OFF"
        return True

    def hills_life_place_seed(self, source="key"):
        if not bool(getattr(self, "hills_life_active", False)):
            return False
        animals = list(getattr(self, "hills_life_animals", []) or [])
        if len(animals) >= MAX_HILLS_LIFEFORMS:
            self.center_hint["text"] = f"HILLS LIFE // POPULATION CAP {MAX_HILLS_LIFEFORMS} // REMOVE ONE FIRST"
            return True
        rec = _current_life_record(self)
        animals.append(rec)
        self.hills_life_animals = animals
        self.hills_life_selected_index = len(animals) - 1
        self.hills_life_dirty = True
        redraw_hills_life(self)
        update_hills_life_ghost(self)
        self.center_hint["text"] = f"CREATED GROWN {rec['name'].upper()} // SAVED"
        save_hills_life(self, reason="create")
        if getattr(self, "audio", None):
            self.audio.play("artifact_link.wav", "sfx", 0.38)
        return True

    def hills_life_find_nearest(self, max_dist=18.0):
        try:
            px, py = float(self.player_pos.x), float(self.player_pos.y)
        except Exception:
            return -1, 999999.0
        best_idx, best_dist = -1, 999999.0
        for idx, rec in enumerate(getattr(self, "hills_life_animals", []) or []):
            try:
                pos = rec.get("position") or [0, 0, 0]
                d = math.hypot(float(pos[0]) - px, float(pos[1]) - py)
                if d < best_dist:
                    best_idx, best_dist = idx, d
            except Exception:
                pass
        if best_dist <= float(max_dist):
            return best_idx, best_dist
        return -1, best_dist

    def hills_life_inspect_nearest(self):
        if not bool(getattr(self, "hills_life_active", False)):
            return False
        idx, dist = hills_life_find_nearest(self)
        self.hills_life_selected_index = idx
        if idx < 0:
            redraw_hills_life(self)
            self.center_hint["text"] = "HILLS LIFE // NO ANIMAL NEARBY"
            return True
        rec = self.hills_life_animals[idx]
        entry = _catalog_entry(self, rec.get("type"))
        stage = _stage_for_life(rec)
        traits = rec.get("traits", {}) if isinstance(rec.get("traits"), dict) else {}
        days_left = max(0, 3 - stage)
        status = "GIFT READY" if _gift_ready(rec) else ("COLLECTED TODAY" if stage >= 3 else f"{days_left} DAY(S) TO ADULT")
        redraw_hills_life(self)
        self.center_hint["text"] = f"{rec.get('name', entry['single']).upper()} // {entry['personality'].upper()} // I{traits.get('intelligence','?')} L{traits.get('loyalty','?')} // {status}"
        return True

    def hills_life_collect_selected(self):
        if not bool(getattr(self, "hills_life_active", False)):
            # H is shared with Forest Growth after this runtime installs.
            if bool(getattr(self, "forest_growth_active", False)) and hasattr(self, "forest_growth_harvest_selected"):
                return self.forest_growth_harvest_selected()
            return False
        idx = int(getattr(self, "hills_life_selected_index", -1))
        if idx < 0 or idx >= len(getattr(self, "hills_life_animals", []) or []):
            idx, _dist = hills_life_find_nearest(self)
            self.hills_life_selected_index = idx
        if idx < 0 or idx >= len(getattr(self, "hills_life_animals", []) or []):
            self.center_hint["text"] = "HILLS LIFE // SELECT AN ADULT ANIMAL FIRST"
            return True
        rec = self.hills_life_animals[idx]
        entry = _catalog_entry(self, rec.get("type"))
        stage = _stage_for_life(rec)
        if stage < 3:
            self.center_hint["text"] = f"{entry['single'].upper()} // STAGE {stage}/3 // NOT ADULT YET"
            return True
        if str(rec.get("last_collected_day") or "")[:10] == _today_key():
            self.center_hint["text"] = f"{entry['single'].upper()} // GIFT ALREADY COLLECTED TODAY"
            return True
        gift = str(entry.get("gift") or "life_gift")
        amount = int(entry.get("yield", 1))
        inv = dict(getattr(self, "hills_life_inventory", {}) or {})
        inv[gift] = int(inv.get(gift, 0)) + amount
        self.hills_life_inventory = inv
        rec["last_collected_day"] = _today_key()
        rec["stage"] = 3
        self.hills_life_animals[idx] = rec
        self.hills_life_dirty = True
        save_hills_life(self, reason="collect")
        redraw_hills_life(self)
        self.center_hint["text"] = f"{rec.get('name', entry['single']).upper()} GIFT // +{amount} {gift.upper()} // SAVED"
        if getattr(self, "audio", None):
            self.audio.play("artifact_link.wav", "sfx", 0.42)
        return True

    def hills_life_delete_selected(self):
        if not bool(getattr(self, "hills_life_active", False)):
            return False
        idx = int(getattr(self, "hills_life_selected_index", -1))
        if idx < 0 or idx >= len(getattr(self, "hills_life_animals", []) or []):
            idx, _dist = hills_life_find_nearest(self)
        if idx < 0 or idx >= len(getattr(self, "hills_life_animals", []) or []):
            self.center_hint["text"] = "HILLS LIFE // NO ANIMAL SELECTED"
            return True
        rec = self.hills_life_animals.pop(idx)
        self.hills_life_selected_index = -1
        self.hills_life_dirty = True
        redraw_hills_life(self)
        save_hills_life(self, reason="remove")
        self.center_hint["text"] = f"HILLS LIFE // REMOVED {str(rec.get('name', rec.get('label', 'ANIMAL'))).upper()}"
        return True

    def _update_animal_motion(self, now, dt):
        animals = list(getattr(self, "hills_life_animals", []) or [])
        nodes = list(getattr(self, "hills_life_nodes", []) or [])
        if not animals:
            return False
        changed = False
        try:
            player_x, player_y = float(self.player_pos.x), float(self.player_pos.y)
        except Exception:
            player_x, player_y = 0.0, 0.0
        for idx, rec in enumerate(animals):
            try:
                stage = _stage_for_life(rec)
                if stage < 2:
                    continue
                entry = _catalog_entry(self, rec.get("type"))
                traits = rec.get("traits", {}) if isinstance(rec.get("traits"), dict) else {}
                pos = rec.get("position") or [0, 0, 0]
                home = rec.get("home_position") or pos
                x, y = float(pos[0]), float(pos[1])
                hx, hy = float(home[0]), float(home[1])
                seed = abs(hash(str(rec.get("seed") or rec.get("id") or idx))) % 10000
                base_speed = {"cat": 1.15, "dog": 1.30, "ape": 0.82, "crow": 2.10}.get(rec.get("type"), 1.0)
                speed = base_speed * (0.45 if stage == 2 else 1.0) * max(0.25, min(1.5, float(dt)))
                angle = float(rec.get("wander_angle", 0.0)) + (0.32 + (seed % 7) * 0.018) * max(0.25, min(1.25, float(dt)))
                rec["wander_angle"] = angle
                # Home orbit is the safety leash. Personality biases where the orbit wants to go.
                radius = 7.0 + float(traits.get("curiosity", 5)) * 1.25 + (3.0 if rec.get("type") == "crow" else 0.0)
                target_x = hx + math.cos(angle + seed * 0.001) * radius
                target_y = hy + math.sin(angle * 0.91 + seed * 0.0017) * radius
                if rec.get("type") == "dog" and math.hypot(player_x - x, player_y - y) < 90.0:
                    loyalty = float(traits.get("loyalty", 5)) / 10.0
                    target_x = target_x * (1.0 - loyalty) + player_x * loyalty
                    target_y = target_y * (1.0 - loyalty) + player_y * loyalty
                elif rec.get("type") == "cat" and math.hypot(player_x - x, player_y - y) < 8.0:
                    # Cats are curious but not clingy.
                    target_x = x + (x - player_x) * 1.5
                    target_y = y + (y - player_y) * 1.5
                elif rec.get("type") == "ape":
                    # Apes orbit home structures slower, like they are inspecting the hill.
                    target_x = hx + math.cos(angle * 0.55 + seed) * (radius * 0.68)
                    target_y = hy + math.sin(angle * 0.50 + seed) * (radius * 0.68)
                dx, dy = target_x - x, target_y - y
                length = math.hypot(dx, dy)
                if length > 0.001:
                    step = min(length, speed)
                    x += dx / length * step
                    y += dy / length * step
                    z = _floor_z(self, x, y)
                    rec["position"] = [round(x, 3), round(y, 3), round(z, 3)]
                    rec["rotation"] = [round(math.degrees(math.atan2(dx, dy)) % 360.0, 3), 0.0, 0.0]
                    changed = True
                    if idx < len(nodes):
                        node = nodes[idx]
                        if node is not None and not node.isEmpty():
                            visual_z = z + (2.4 if rec.get("type") == "crow" and stage == 2 else 4.6 if rec.get("type") == "crow" and stage >= 3 else 0.0)
                            node.setPos(x, y, visual_z)
                            node.setH(float(rec["rotation"][0]))
            except Exception as exc:
                print(f"hills_life_motion_error: {exc}")
        if changed:
            self.hills_life_animals = animals
            self.hills_life_dirty = True
        return changed

    def update_hills_life(self, dt=0.0):
        if not bool(getattr(self, "hills_life_active", False)):
            return
        if not _hills_allowed(self):
            deactivate_hills_life(self, reason="left-green-hills-region")
            return
        today = _today_key()
        if today != getattr(self, "hills_life_last_day", today):
            self.hills_life_last_day = today
            self.hills_life_dirty = True
            redraw_hills_life(self)
            save_hills_life(self, reason="new-day-persistence-check")
        update_hills_life_ghost(self)
        now = time.time()
        if (now - float(getattr(self, "hills_life_last_move_at", 0.0))) >= 0.20:
            elapsed = min(0.35, max(0.05, now - float(getattr(self, "hills_life_last_move_at", now))))
            self.hills_life_last_move_at = now
            _update_animal_motion(self, now, elapsed)
            update_hills_life_ui(self)
        if bool(getattr(self, "hills_life_dirty", False)) and (time.time() - float(getattr(self, "hills_life_last_save_at", 0.0))) > 18.0:
            save_hills_life(self, reason="autosave")

    # Attach runtime API.
    CommandHubApp.is_hills_life_mode = _is_hills_life_mode
    CommandHubApp.activate_hills_life_from_mode = activate_hills_life_from_mode
    CommandHubApp.deactivate_hills_life = deactivate_hills_life
    CommandHubApp.save_hills_life = save_hills_life
    CommandHubApp.load_hills_life = load_hills_life
    CommandHubApp.redraw_hills_life = redraw_hills_life
    CommandHubApp.update_hills_life = update_hills_life
    CommandHubApp.update_hills_life_ui = update_hills_life_ui
    CommandHubApp.hills_life_cycle_type = hills_life_cycle_type
    CommandHubApp.hills_life_toggle_snap = hills_life_toggle_snap
    CommandHubApp.hills_life_place_seed = hills_life_place_seed
    CommandHubApp.hills_life_inspect_nearest = hills_life_inspect_nearest
    CommandHubApp.hills_life_collect_selected = hills_life_collect_selected
    CommandHubApp.hills_life_delete_selected = hills_life_delete_selected

    old_init = CommandHubApp.__init__
    def __init__(self, *args, **kwargs):
        old_init(self, *args, **kwargs)
        _init_state(self)
    CommandHubApp.__init__ = __init__

    old_setup_input = CommandHubApp.setup_input
    def setup_input(self, *args, **kwargs):
        result = old_setup_input(self, *args, **kwargs)
        self.accept("h", self.hills_life_collect_selected)
        return result
    CommandHubApp.setup_input = setup_input

    old_e = CommandHubApp.on_e_down
    def on_e_down(self):
        if bool(getattr(self, "hills_life_active", False)):
            self.set_key("e", True)
            self.hills_life_place_seed(source="e")
            return
        return old_e(self)
    CommandHubApp.on_e_down = on_e_down

    old_q = CommandHubApp.on_q_down
    def on_q_down(self):
        if bool(getattr(self, "hills_life_active", False)):
            self.set_key("q", True)
            self.hills_life_cycle_type(1)
            return
        return old_q(self)
    CommandHubApp.on_q_down = on_q_down

    old_primary = CommandHubApp.primary_click_interact
    def primary_click_interact(self):
        if bool(getattr(self, "hills_life_active", False)):
            self.hills_life_place_seed(source="mouse1")
            return
        return old_primary(self)
    CommandHubApp.primary_click_interact = primary_click_interact

    old_start_escape_hold = CommandHubApp.start_escape_hold
    def start_escape_hold(self):
        if bool(getattr(self, "hills_life_active", False)):
            self.deactivate_hills_life(reason="escape")
            return
        return old_start_escape_hold(self)
    CommandHubApp.start_escape_hold = start_escape_hold

    old_delete = getattr(CommandHubApp, "holoforge_delete_selected", None)
    if callable(old_delete):
        def holoforge_delete_selected(self):
            if bool(getattr(self, "hills_life_active", False)):
                return self.hills_life_delete_selected()
            return old_delete(self)
        CommandHubApp.holoforge_delete_selected = holoforge_delete_selected

    old_g_save = getattr(CommandHubApp, "holoforge_save_blueprint", None)
    if callable(old_g_save):
        def holoforge_save_blueprint(self):
            if bool(getattr(self, "hills_life_active", False)):
                return self.save_hills_life(reason="manual")
            return old_g_save(self)
        CommandHubApp.holoforge_save_blueprint = holoforge_save_blueprint

    old_x_select = getattr(CommandHubApp, "holoforge_select_or_clear", None)
    if callable(old_x_select):
        def holoforge_select_or_clear(self):
            if bool(getattr(self, "hills_life_active", False)):
                return self.hills_life_inspect_nearest()
            return old_x_select(self)
        CommandHubApp.holoforge_select_or_clear = holoforge_select_or_clear

    old_b_snap = getattr(CommandHubApp, "holoforge_toggle_snap", None)
    if callable(old_b_snap):
        def holoforge_toggle_snap(self):
            if bool(getattr(self, "hills_life_active", False)):
                return self.hills_life_toggle_snap()
            return old_b_snap(self)
        CommandHubApp.holoforge_toggle_snap = holoforge_toggle_snap

    old_route = CommandHubApp.launch_core_mode_route
    def launch_core_mode_route(self, mode, source="core", extra_env=None, close_core=True):
        if self.is_hills_life_mode(mode):
            return bool(self.activate_hills_life_from_mode(mode, source=source, route=IN_WORLD_ROUTE))
        return old_route(self, mode, source=source, extra_env=extra_env, close_core=close_core)
    CommandHubApp.launch_core_mode_route = launch_core_mode_route

    old_region_ui = CommandHubApp.update_holoverse_region_ui
    def update_holoverse_region_ui(self):
        result = old_region_ui(self)
        if bool(getattr(self, "hills_life_active", False)):
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
                self.update_hills_life(0.0)
        except Exception as exc:
            print(f"hills_life_update_error: {exc}")
        return result
    CommandHubApp.update_task = update_task

    setattr(main, "HILLS_LIFE_RUNTIME_INSTALLED", True)
    setattr(main, "HILLS_LIFE_STATE_PATH_RUNTIME", STATE_PATH)
