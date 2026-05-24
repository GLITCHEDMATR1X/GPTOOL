"""Oddities in-world runtime for the live MUSHROOM HoloVerse region.

Oddities replaces the old mushroom/deep-water association with a strange
procedural experiment layer: floating behavior objects and weird plants that
save into shared data, grow one stage per real day, and unload cleanly when the
player leaves the mushroom region.
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
from panda3d.core import LineSegs, TextNode, TransparencyAttrib, Vec3

IN_WORLD_ROUTE = "in_world_region"
ODDITIES_SCHEMA = 1
MUSHROOM_REGION_NUMBER = 3
MAX_ODDITIES = 48


def _main_module(cls):
    return sys.modules.get(cls.__module__) or sys.modules.get("__main__")


def install_oddities_runtime(CommandHubApp):
    main = _main_module(CommandHubApp)
    if main is None:
        return

    from holoverse_mode_runtime import resolve_accidental_nested_data_root, resolve_shared_data_root

    ROOT = Path(getattr(main, "ROOT", Path(__file__).resolve().parent))
    SHARED_DATA_ROOT = resolve_shared_data_root(main, ROOT)
    LEGACY_SHARED_DATA_ROOT = resolve_accidental_nested_data_root(ROOT)
    STATE_DIR = SHARED_DATA_ROOT / "holoverse" / "regions" / "mushroom" / "oddities"
    STATE_PATH = STATE_DIR / "oddities_state.json"
    LEGACY_STATE_PATH = LEGACY_SHARED_DATA_ROOT / "holoverse" / "regions" / "mushroom" / "oddities" / "oddities_state.json"
    LIBRARY_PATH = SHARED_DATA_ROOT / "holoverse" / "libraries" / "oddities_blueprint_library.json"
    MATRIXCORE_LIBRARY_PATH = SHARED_DATA_ROOT / "database" / "matrixcore" / "oddities_blueprint_library.json"
    ROOT_PROGRESS_PATH = ROOT / "progression" / "progression_state.json"
    SHARED_PROGRESS_PATH = SHARED_DATA_ROOT / "holoverse" / "progression" / "progression_state.json"

    from holoverse_mode_runtime import install_in_world_route_aliases

    install_in_world_route_aliases(main)

    def _ensure_dirs():
        for folder in (STATE_DIR, LIBRARY_PATH.parent, MATRIXCORE_LIBRARY_PATH.parent, ROOT_PROGRESS_PATH.parent, SHARED_PROGRESS_PATH.parent, SHARED_DATA_ROOT / "brain", SHARED_DATA_ROOT / "database"):
            folder.mkdir(parents=True, exist_ok=True)

    def _today_key() -> str:
        return date.today().isoformat()

    def _safe_days_since(day_text: str) -> int:
        try:
            created = date.fromisoformat(str(day_text or "")[:10])
            return max(0, int((date.today() - created).days))
        except Exception:
            return 0

    def _stage_for_oddity(raw) -> int:
        try:
            if raw.get("force_stage"):
                return max(1, min(3, int(raw.get("stage", 1))))
        except Exception:
            pass
        return max(1, min(3, 1 + _safe_days_since(str(raw.get("created_day") or raw.get("created_at") or _today_key()))))

    def _catalog(self):
        return [
            {
                "id": "floating_object",
                "label": "Floating Objects",
                "single": "Floating Oddity",
                "gift": "levitation_shard",
                "color": (0.20, 1.00, 1.00, 0.88),
                "accent": (1.00, 0.20, 0.94, 0.95),
                "spacing": 7.0,
                "kind": "object",
                "description": "unpredictable floating objects with bob, spin, orbit, or jitter behavior",
            },
            {
                "id": "weird_plant",
                "label": "Weird Plants",
                "single": "Weird Plant",
                "gift": "odd_fruit",
                "color": (1.00, 0.18, 0.72, 0.90),
                "accent": (0.22, 1.00, 0.82, 0.96),
                "spacing": 6.0,
                "kind": "plant",
                "description": "procedural plants with randomized branching patterns and strange fruit",
            },
            {
                "id": "spore_totem",
                "label": "Spore Totems",
                "single": "Spore Totem",
                "gift": "spore_logic",
                "color": (0.85, 0.34, 1.00, 0.90),
                "accent": (0.08, 1.00, 1.00, 0.96),
                "spacing": 8.0,
                "kind": "object",
                "description": "stacked fungal machines that pulse like unsafe research equipment",
            },
            {
                "id": "glitch_growth",
                "label": "Glitch Growths",
                "single": "Glitch Growth",
                "gift": "unstable_pattern",
                "color": (1.00, 0.78, 0.20, 0.90),
                "accent": (0.72, 0.30, 1.00, 0.96),
                "spacing": 7.0,
                "kind": "plant",
                "description": "angular growths with impossible geometry and unstable movement",
            },
        ]

    def _catalog_entry(self, oddity_type=None):
        catalog = _catalog(self)
        raw = str(oddity_type or catalog[int(getattr(self, "oddities_type_index", 0)) % len(catalog)]["id"]).strip().lower()
        aliases = {
            "floating": "floating_object", "floating_objects": "floating_object", "object": "floating_object", "objects": "floating_object",
            "plant": "weird_plant", "plants": "weird_plant", "weird_plants": "weird_plant",
            "totem": "spore_totem", "spore": "spore_totem", "spore_totems": "spore_totem",
            "glitch": "glitch_growth", "glitch_growths": "glitch_growth",
        }
        raw = aliases.get(raw, raw)
        for entry in catalog:
            if entry["id"] == raw:
                return entry
        return catalog[0]

    def _init_state(self):
        self.oddities_active = False
        self.oddities_loaded = False
        self.oddities_root = None
        self.oddities_ghost_root = None
        self.oddities_ui_root = None
        self.oddities_ui_panel = None
        self.oddities_ui_title = None
        self.oddities_ui_tool = None
        self.oddities_ui_help = None
        self.oddities_items = []
        self.oddities_nodes = []
        self.oddities_selected_index = -1
        self.oddities_type_index = 0
        self.oddities_snap_enabled = True
        self.oddities_grid_step = 4.0
        self.oddities_last_day = _today_key()
        self.oddities_last_save_at = 0.0
        self.oddities_last_anim_at = 0.0
        self.oddities_dirty = False
        self.oddities_inventory = {}
        self.oddities_last_ghost_signature = None
        self.oddities_state_path = STATE_PATH

    def _is_oddities_mode(self, mode):
        data = dict(mode or {})
        manifest = dict(data.get("manifest") or {})
        tokens = " ".join(str(x or "") for x in (
            data.get("name"), data.get("id"), data.get("title"),
            manifest.get("id"), manifest.get("title"), manifest.get("description"),
            manifest.get("host_contract"), manifest.get("preferred_display"),
            manifest.get("region_owner"), manifest.get("bot_owner"),
        )).lower()
        return (
            "oddities" in tokens
            or "mushroom experiment" in tokens
            or "mycolab" in tokens
            or ("solace" in tokens and "mushroom" in tokens)
            or str(manifest.get("id") or data.get("id") or "").lower() == "oddities"
            or str(data.get("name") or "").lower() == "oddities"
        )

    def _mushroom_allowed(self):
        try:
            if self.is_holospace_active():
                return False
        except Exception:
            pass
        try:
            return int(self.current_holoverse_region_number()) == MUSHROOM_REGION_NUMBER
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
        if not bool(getattr(self, "oddities_snap_enabled", True)):
            return round(float(value), 3)
        step = max(1.0, float(getattr(self, "oddities_grid_step", 4.0)))
        return round(round(float(value) / step) * step, 3)

    def _placement_xy(self, distance=11.0):
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

    def _oddity_rolls(entry, seed_value=None, existing=None):
        if isinstance(existing, dict) and existing:
            out = dict(existing)
        else:
            rng = random.Random(str(seed_value or f"{entry['id']}:{time.time()}"))
            out = {
                "weirdness": rng.randint(5, 10),
                "stability": rng.randint(2, 9),
                "energy": rng.randint(3, 10),
                "pattern": rng.choice(["spiral", "fork", "stack", "scatter", "lattice", "curl"]),
                "behavior": rng.choice(["bob", "spin", "orbit", "jitter", "drift"]),
                "variant": rng.choice(["orb", "cube", "shard", "ring", "cap", "fork"]),
            }
        for k in ("weirdness", "stability", "energy"):
            try:
                out[k] = max(1, min(10, int(round(float(out.get(k, 5))))))
            except Exception:
                out[k] = 5
        return out

    def _normalize_oddity(self, raw, *, force_ground=True):
        raw = dict(raw or {})
        entry = _catalog_entry(self, raw.get("type") or raw.get("oddity_type"))
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
        if bool(getattr(self, "oddities_snap_enabled", True)) and not bool(raw.get("moving_runtime")):
            x, y = _snap_xy(self, x), _snap_xy(self, y)
        floor = _floor_z(self, x, y)
        if force_ground and entry["kind"] == "plant":
            z = floor
        created_day = str(raw.get("created_day") or raw.get("created_at") or _today_key())[:10]
        try:
            date.fromisoformat(created_day)
        except Exception:
            created_day = _today_key()
        oddity_id = str(raw.get("id") or f"odd_{int(time.time() * 1000)}_{len(getattr(self, 'oddities_items', [])) + 1}")
        seed_value = str(raw.get("seed") or oddity_id)
        stage = _stage_for_oddity({**raw, "created_day": created_day})
        rolls = _oddity_rolls(entry, seed_value=seed_value, existing=raw.get("traits") or raw.get("properties"))
        home = raw.get("home_position") or raw.get("home") or [x, y, floor]
        try:
            hx, hy, hz = float(home[0]), float(home[1]), float(home[2])
        except Exception:
            hx, hy, hz = x, y, floor
        # Floating object families hover above the true ground; plant families root to it.
        base_float = 6.0 + rolls["energy"] * 0.35 if entry["kind"] == "object" else 0.0
        if not bool(raw.get("moving_runtime")) and entry["kind"] == "object":
            z = floor + base_float
        name = str(raw.get("name") or f"{entry['single'].replace(' ', '_')}_{str(oddity_id)[-4:]}")
        return {
            "id": oddity_id,
            "name": name,
            "type": entry["id"],
            "label": entry["single"],
            "position": [round(float(x), 3), round(float(y), 3), round(float(z), 3)],
            "home_position": [round(float(hx), 3), round(float(hy), 3), round(float(hz), 3)],
            "rotation": [round(float((raw.get("rotation") or [0.0])[0] if isinstance(raw.get("rotation"), list) else raw.get("yaw", 0.0)) % 360.0, 3), 0.0, 0.0],
            "created_day": created_day,
            "created_at": str(raw.get("created_at") or datetime.now().isoformat(timespec="seconds")),
            "stage": int(stage),
            "properties": rolls,
            "description": entry["description"],
            "gift": entry["gift"],
            "last_collected_day": str(raw.get("last_collected_day") or "")[:10],
            "seed": seed_value,
            "phase": float(raw.get("phase", 0.0) or 0.0),
        }

    def _current_oddity_record(self):
        entry = _catalog_entry(self)
        x, y = _placement_xy(self)
        odd_id = f"odd_{int(time.time() * 1000)}_{len(getattr(self, 'oddities_items', [])) + 1}"
        return _normalize_oddity(self, {
            "id": odd_id,
            "name": f"{entry['single'].replace(' ', '_')}_{len(getattr(self, 'oddities_items', [])) + 1:03d}",
            "type": entry["id"],
            "position": [x, y, _floor_z(self, x, y)],
            "home_position": [x, y, _floor_z(self, x, y)],
            "created_day": _today_key(),
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "seed": odd_id,
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
                print(f"oddities_state_read_error {path}: {exc}")
        return {"items": [], "inventory": {}}

    def _write_json(path: Path, payload: dict):
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(path)

    def _sync_progression_save(self, reason="save"):
        items = list(getattr(self, "oddities_items", []) or [])
        summary = {
            "schema": ODDITIES_SCHEMA,
            "state_path": str(STATE_PATH),
            "region": "mushroom",
            "owner_bot": "Solace",
            "mode": "Oddities",
            "dimension": "Oddities",
            "total_oddities": len(items),
            "mature_oddities": sum(1 for a in items if _stage_for_oddity(a) >= 3),
            "inventory": dict(getattr(self, "oddities_inventory", {}) or {}),
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
                data.setdefault("dimension_blueprints", {})["oddities"] = {
                    "owner_bot": "Solace",
                    "status": "playable_in_world_region",
                    "tool": "Oddities",
                    "state": str(STATE_PATH),
                }
                data.setdefault("oddities", {}).update(summary)
                visits = data.setdefault("dimension_visits", {})
                odd = visits.setdefault("Oddities", {})
                odd["count"] = int(odd.get("count", 0)) + (1 if reason == "activate" else 0)
                odd["last_at"] = datetime.now().isoformat(timespec="seconds")
                odd["route"] = IN_WORLD_ROUTE
                odd["reason"] = "oddities_region_runtime"
                odd["source"] = "region_bot:Solace"
                _write_json(path, data)
            except Exception as exc:
                print(f"oddities_progression_sync_error {path}: {exc}")
        return summary

    def export_oddities_library(self, reason="save"):
        items = list(getattr(self, "oddities_items", []) or [])
        payload_items = []
        for raw in items:
            try:
                rec = _normalize_oddity(self, {**raw, "moving_runtime": True}, force_ground=True)
                props = dict(rec.get("properties") or {})
                payload_items.append({
                    "id": rec.get("id"),
                    "name": rec.get("name"),
                    "type": rec.get("type"),
                    "label": rec.get("label"),
                    "stage": int(_stage_for_oddity(rec)),
                    "position": list(rec.get("position") or [0, 0, 0]),
                    "rotation": list(rec.get("rotation") or [0, 0, 0]),
                    "color_family": _catalog_entry(self, rec.get("type")).get("id"),
                    "traits": props,
                    "gift": rec.get("gift"),
                    "description": rec.get("description"),
                    "reuse_contract": "oddities_study_specimen_can_be_mounted_in_other_worlds",
                    "spawn_hint": {
                        "attach_to": "render_or_region_runtime_root",
                        "ground_policy": "plant_on_floor_object_hover",
                        "visual_scale": 1.0 + int(_stage_for_oddity(rec)) * 0.22,
                    },
                })
            except Exception as exc:
                print(f"oddities_export_item_error:{exc}")
        payload = {
            "schema": ODDITIES_SCHEMA,
            "kind": "holoverse_oddities_reuse_library",
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "reason": str(reason or "save"),
            "region": "mushroom",
            "owner_bot": "Solace",
            "total_blueprints": len(payload_items),
            "blueprints": payload_items,
            "notes": "Reusable weird life/object study records created in the Mushroom/Oddities region.",
        }
        for path in (LIBRARY_PATH, MATRIXCORE_LIBRARY_PATH):
            try:
                _write_json(path, payload)
            except Exception as exc:
                print(f"oddities_library_export_error {path}: {exc}")
        self.oddities_library_path = LIBRARY_PATH
        self.oddities_matrixcore_library_path = MATRIXCORE_LIBRARY_PATH
        return payload

    def _seed_starter_oddities(self):
        if getattr(self, "oddities_items", None):
            return False
        # Four readable study specimens make Mushroom/Oddities look alive the
        # first time the mode opens, while still keeping population under player
        # control afterward.
        base_x, base_y = _placement_xy(self, distance=12.0)
        catalog_ids = ["floating_object", "weird_plant", "spore_totem", "glitch_growth"]
        offsets = [(-6.0, 0.0), (5.5, 2.0), (0.0, 8.0), (8.0, -5.0)]
        seeded = []
        for idx, oid in enumerate(catalog_ids):
            ox, oy = offsets[idx]
            x, y = _snap_xy(self, base_x + ox), _snap_xy(self, base_y + oy)
            seed = f"starter_mushroom_{oid}_{idx}_{int(time.time())}"
            entry = _catalog_entry(self, oid)
            rec = _normalize_oddity(self, {
                "id": f"starter_{oid}_{idx}",
                "name": f"Study_{entry['single'].replace(' ', '_')}_{idx+1:02d}",
                "type": oid,
                "position": [x, y, _floor_z(self, x, y)],
                "home_position": [x, y, _floor_z(self, x, y)],
                "force_stage": True,
                "stage": 2 if idx < 3 else 3,
                "seed": seed,
                "properties": {"weirdness": 8 + (idx % 3), "stability": 4 + idx, "energy": 6 + idx, "pattern": ["spiral", "fork", "stack", "lattice"][idx], "behavior": ["orbit", "bob", "spin", "jitter"][idx], "variant": ["orb", "cap", "tower", "shard"][idx]},
            })
            seeded.append(rec)
        self.oddities_items = seeded[:MAX_ODDITIES]
        self.oddities_selected_index = 0 if seeded else -1
        self.oddities_dirty = True
        return bool(seeded)

    def save_oddities(self, reason="manual"):
        _ensure_dirs()
        items = []
        for raw in list(getattr(self, "oddities_items", []) or []):
            rec = _normalize_oddity(self, {**raw, "moving_runtime": True}, force_ground=True)
            rec["stage"] = _stage_for_oddity(rec)
            items.append(rec)
        self.oddities_items = items
        payload = {
            "schema": ODDITIES_SCHEMA,
            "kind": "holoverse_oddities_state",
            "save_authority": "shared_data_holoverse_region_layer",
            "region": "mushroom",
            "region_number": MUSHROOM_REGION_NUMBER,
            "owner_bot": "Solace",
            "mode": "Oddities",
            "growth_rule": "one_stage_per_real_calendar_day_stage_3_mature_unpredictable",
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "today": _today_key(),
            "oddity_types": [e["id"] for e in _catalog(self)],
            "population_cap": MAX_ODDITIES,
            "inventory": dict(getattr(self, "oddities_inventory", {}) or {}),
            "items": items,
            "summary": {
                "total_oddities": len(items),
                "stage_1": sum(1 for a in items if int(a.get("stage", 1)) == 1),
                "stage_2": sum(1 for a in items if int(a.get("stage", 1)) == 2),
                "stage_3": sum(1 for a in items if int(a.get("stage", 1)) >= 3),
            },
        }
        try:
            _write_json(STATE_PATH, payload)
            # Do not mirror saves into the old accidental <app>/data/data lane.
            export_oddities_library(self, reason=str(reason or "save"))
            self.oddities_dirty = False
            self.oddities_last_save_at = time.time()
            _sync_progression_save(self, reason=str(reason or "save"))
            try:
                self.center_hint["text"] = f"ODDITIES // SAVED {len(items)} EXPERIMENTS"
            except Exception:
                pass
        except Exception as exc:
            try:
                self.center_hint["text"] = f"ODDITIES // SAVE FAILED // {exc}"
            except Exception:
                pass
            print(f"oddities_save_error: {exc}")
        return True

    def load_oddities(self):
        data = _read_state(self)
        inv = data.get("inventory", {}) if isinstance(data, dict) else {}
        self.oddities_inventory = dict(inv) if isinstance(inv, dict) else {}
        items = []
        for raw in list((data or {}).get("items", []) or []):
            if isinstance(raw, dict):
                items.append(_normalize_oddity(self, raw, force_ground=True))
        self.oddities_items = items[:MAX_ODDITIES]
        self.oddities_loaded = True
        self.oddities_last_day = _today_key()
        return items

    def _oddities_runtime_parent(self):
        """Visible parent for Mushroom/Oddities geometry.

        The HoloVerse shell can hide root_3d/world_root while region streaming is
        active. Created oddities must live under render so the real Mushroom view
        and saved study specimens both see the same objects.
        """
        try:
            return self.render
        except Exception:
            return getattr(self, "root_3d", None) or self.world_root

    def _ensure_runtime_nodes(self):
        parent = _oddities_runtime_parent(self)
        if getattr(self, "oddities_root", None) is None or self.oddities_root.isEmpty():
            self.oddities_root = parent.attachNewNode("oddities-region-visible-layer")
            self.oddities_root.setPythonTag("oddities_root_parent", "render")
        else:
            try:
                self.oddities_root.reparentTo(parent)
            except Exception:
                pass
        if getattr(self, "oddities_ghost_root", None) is None or self.oddities_ghost_root.isEmpty():
            self.oddities_ghost_root = parent.attachNewNode("oddities-region-preview-layer")
            self.oddities_ghost_root.setPythonTag("oddities_root_parent", "render")
        else:
            try:
                self.oddities_ghost_root.reparentTo(parent)
            except Exception:
                pass
        if getattr(self, "oddities_ui_root", None) is None or self.oddities_ui_root.isEmpty():
            ui_parent = getattr(self, "hud_root", None) or getattr(self, "aspect2d", None)
            self.oddities_ui_root = ui_parent.attachNewNode("oddities-region-runtime-ui")
            self.oddities_ui_panel = DirectFrame(parent=self.oddities_ui_root, frameColor=(0.02, 0.00, 0.04, 0.32), frameSize=(-0.62, 0.62, -0.15, 0.19), pos=(-0.66, 0, -0.78))
            self.oddities_ui_title = DirectLabel(parent=self.oddities_ui_panel, text="ODDITIES ACTIVE", text_align=TextNode.ALeft, text_scale=0.030, text_fg=(0.20, 1.0, 1.0, 1), frameColor=(0, 0, 0, 0), pos=(-0.58, 0, 0.120))
            self.oddities_ui_tool = DirectLabel(parent=self.oddities_ui_panel, text="", text_align=TextNode.ALeft, text_scale=0.022, text_fg=(1.0, 0.70, 1.0, 1), frameColor=(0, 0, 0, 0), pos=(-0.58, 0, 0.040), text_wordwrap=54)
            self.oddities_ui_help = DirectLabel(parent=self.oddities_ui_panel, text="", text_align=TextNode.ALeft, text_scale=0.018, text_fg=(0.76, 0.96, 1.0, 0.92), frameColor=(0, 0, 0, 0), pos=(-0.58, 0, -0.075), text_wordwrap=58)
        return True

    def _line_node(parent, name, segments, color, thickness=1.4):
        segs = LineSegs()
        segs.setThickness(float(thickness))
        segs.setColor(*color)
        for a, b in segments:
            segs.moveTo(float(a[0]), float(a[1]), float(a[2]))
            segs.drawTo(float(b[0]), float(b[1]), float(b[2]))
        node = parent.attachNewNode(segs.create(name))
        node.setTransparency(TransparencyAttrib.MAlpha)
        return node

    def _circle_segments(radius=1.0, z=0.0, axis="xy", count=24):
        pts = []
        for i in range(count + 1):
            a = math.tau * i / max(3, count)
            if axis == "xy":
                pts.append((math.cos(a) * radius, math.sin(a) * radius, z))
            elif axis == "xz":
                pts.append((math.cos(a) * radius, 0.0, math.sin(a) * radius + z))
            else:
                pts.append((0.0, math.cos(a) * radius, math.sin(a) * radius + z))
        return list(zip(pts[:-1], pts[1:]))

    def _cube_segments(sx=1.0, sy=1.0, sz=1.0):
        x, y, z = sx * 0.5, sy * 0.5, sz * 0.5
        pts = [(-x,-y,-z),(x,-y,-z),(x,y,-z),(-x,y,-z),(-x,-y,z),(x,-y,z),(x,y,z),(-x,y,z)]
        edges = [(0,1),(1,2),(2,3),(3,0),(4,5),(5,6),(6,7),(7,4),(0,4),(1,5),(2,6),(3,7)]
        return [(pts[a], pts[b]) for a,b in edges]

    def _draw_weird_plant(root, rec, stage, entry, selected=False):
        props = rec.get("properties", {}) if isinstance(rec.get("properties"), dict) else {}
        rng = random.Random(str(rec.get("seed", rec.get("id", "odd"))))
        weird = float(props.get("weirdness", 7))
        energy = float(props.get("energy", 5))
        base_h = 2.0 + stage * (1.25 + weird * 0.22)
        stalks = max(1, stage + int(weird > 7))
        segments = []
        fruit_segments = []
        for s in range(stalks):
            angle = math.tau * s / max(1, stalks) + rng.uniform(-0.45, 0.45)
            offset = rng.uniform(0.0, 0.65 + stage * 0.10)
            x0 = math.cos(angle) * offset
            y0 = math.sin(angle) * offset
            top = (x0 + math.cos(angle + rng.uniform(-1.4,1.4)) * (0.35 + stage * 0.22), y0 + math.sin(angle + rng.uniform(-1.4,1.4)) * (0.35 + stage * 0.22), base_h * rng.uniform(0.75, 1.15))
            segments.append(((x0, y0, 0.0), top))
            branches = stage * 2 + int(weird)
            for b in range(branches):
                t = rng.uniform(0.22, 0.92)
                start = (x0 + (top[0]-x0)*t, y0 + (top[1]-y0)*t, top[2]*t)
                ba = angle + rng.uniform(-2.2, 2.2)
                length = rng.uniform(0.55, 1.6 + stage * 0.38)
                end = (start[0] + math.cos(ba)*length, start[1] + math.sin(ba)*length, start[2] + rng.uniform(-0.25, 0.9))
                segments.append((start, end))
                if stage >= 3 and rng.random() < 0.42:
                    rr = 0.12 + rng.random() * 0.18
                    fruit_segments.extend(_circle_segments(rr, z=end[2], axis="xy", count=10))
                    # fruit circle generated at origin; translate it around branch end
                    fruit_segments[-10:] = [((a[0]+end[0], a[1]+end[1], a[2]), (b2[0]+end[0], b2[1]+end[1], b2[2])) for a,b2 in fruit_segments[-10:]]
        _line_node(root, "oddities_plant_stems", segments, entry["color"], 1.7 if selected else 1.2)
        if fruit_segments:
            _line_node(root, "oddities_plant_fruit", fruit_segments, entry["accent"], 1.4)
        _line_node(root, "oddities_plant_base", _circle_segments(1.0 + stage*0.28, 0.04, "xy", 22), (0.08, 1.0, 1.0, 0.52), 1.0)

    def _draw_floating_object(root, rec, stage, entry, selected=False):
        props = rec.get("properties", {}) if isinstance(rec.get("properties"), dict) else {}
        variant = str(props.get("variant", "orb"))
        weird = float(props.get("weirdness", 7))
        size = 1.3 + stage * 0.65 + weird * 0.08
        segments = []
        if variant in {"cube", "shard"}:
            segments.extend(_cube_segments(size * 1.4, size * 1.1, size * 1.2))
        else:
            segments.extend(_circle_segments(size, 0.0, "xy", 30))
            segments.extend(_circle_segments(size * 0.86, 0.0, "xz", 30))
            segments.extend(_circle_segments(size * 0.72, 0.0, "yz", 30))
        rng = random.Random(str(rec.get("seed", "odd")) + ":spikes")
        for i in range(stage * 4 + int(weird)):
            a = rng.random() * math.tau
            z = rng.uniform(-size * 0.7, size * 0.7)
            r1 = size * rng.uniform(0.35, 0.9)
            r2 = r1 + rng.uniform(0.45, 1.4)
            segments.append(((math.cos(a)*r1, math.sin(a)*r1, z), (math.cos(a)*r2, math.sin(a)*r2, z + rng.uniform(-0.35, 0.35))))
        _line_node(root, "oddities_float_core", segments, entry["color"], 1.6 if selected else 1.15)
        rings = []
        for i in range(1, stage + 2):
            rings.extend(_circle_segments(size + i * 0.55, z=-size * 0.55 + i * 0.34, axis="xy", count=32))
        _line_node(root, "oddities_float_rings", rings, entry["accent"], 0.95)

    def _draw_spore_totem(root, rec, stage, entry, selected=False):
        props = rec.get("properties", {}) if isinstance(rec.get("properties"), dict) else {}
        weird = float(props.get("weirdness", 8))
        height = 3.0 + stage * 2.5 + weird * 0.30
        rings = []
        for i in range(stage + 3):
            z = 0.35 + i * (height / max(2, stage + 2))
            radius = 0.9 + (i % 2) * 0.42 + stage * 0.18
            rings.extend(_circle_segments(radius, z, "xy", 18))
        _line_node(root, "oddities_spore_totem_rings", rings, entry["color"], 1.8 if selected else 1.2)
        ribs = []
        for i in range(8):
            a = math.tau * i / 8.0
            ribs.append(((math.cos(a)*0.7, math.sin(a)*0.7, 0.0), (math.cos(a)*1.25, math.sin(a)*1.25, height)))
        _line_node(root, "oddities_spore_totem_ribs", ribs, entry["accent"], 1.15)
        cloud = []
        for i in range(6 + stage * 2):
            a = math.tau * i / max(1, 6 + stage * 2)
            cloud.extend(_circle_segments(0.22 + 0.04 * stage, height + math.sin(a)*0.35, "xy", 10))
            cloud[-10:] = [((p.x + math.cos(a)*1.85, p.y + math.sin(a)*1.85, p.z), (q.x + math.cos(a)*1.85, q.y + math.sin(a)*1.85, q.z)) if hasattr(p, 'x') else ((p[0] + math.cos(a)*1.85, p[1] + math.sin(a)*1.85, p[2]), (q[0] + math.cos(a)*1.85, q[1] + math.sin(a)*1.85, q[2])) for p, q in cloud[-10:]]
        if cloud:
            _line_node(root, "oddities_spore_cloud", cloud, (0.20, 1.0, 1.0, 0.62), 0.85)

    def _draw_glitch_growth(root, rec, stage, entry, selected=False):
        rng = random.Random(str(rec.get("seed", "glitch")))
        shards = []
        for i in range(5 + stage * 5):
            a = rng.random() * math.tau
            r = rng.uniform(0.2, 1.2 + stage * 0.6)
            h = rng.uniform(1.5, 3.0 + stage * 2.4)
            base = (math.cos(a)*r, math.sin(a)*r, 0.0)
            tip = (math.cos(a + rng.uniform(-0.5, 0.5))*(r + rng.uniform(0.4, 1.8)), math.sin(a + rng.uniform(-0.5, 0.5))*(r + rng.uniform(0.4, 1.8)), h)
            shards.append((base, tip))
            shards.append((tip, (base[0]*0.4, base[1]*0.4, max(0.2, h*0.34))))
        _line_node(root, "oddities_glitch_shards", shards, entry["color"], 1.8 if selected else 1.22)
        halos = []
        for k in range(1, stage + 3):
            halos.extend(_circle_segments(0.85 + k * 0.58, k * 0.85, "xy", 20))
        _line_node(root, "oddities_glitch_halos", halos, entry["accent"], 0.95)

    def _draw_study_marker(root, rec, stage, entry, selected=False):
        height = 3.4 + stage * 2.1
        marker_color = (1.0, 1.0, 1.0, 0.82) if selected else (0.20, 1.0, 1.0, 0.48)
        _line_node(root, "oddities_visibility_mast", [((0, 0, 0.1), (0, 0, height))], marker_color, 1.15 if selected else 0.72)
        _line_node(root, "oddities_visibility_crown", _circle_segments(0.75 + stage * 0.28, height, "xy", 18), entry["accent"], 1.05)
        try:
            label_node = TextNode("oddities-study-label")
            label_node.setText(f"{str(rec.get('label','ODD')).upper()} S{stage}")
            label_node.setAlign(TextNode.ACenter)
            label_node.setTextColor(0.72, 1.0, 1.0, 0.86)
            np = root.attachNewNode(label_node)
            np.setScale(0.52)
            np.setPos(0, 0, height + 0.55)
            np.setBillboardPointEye()
            np.setTransparency(TransparencyAttrib.MAlpha)
        except Exception:
            pass

    def _draw_oddity_node(self, rec, index=0, ghost=False):
        entry = _catalog_entry(self, rec.get("type"))
        stage = _stage_for_oddity(rec)
        selected = int(index) == int(getattr(self, "oddities_selected_index", -1)) and not ghost
        parent = self.oddities_ghost_root if ghost else self.oddities_root
        root = parent.attachNewNode(f"oddity_{rec.get('id', index)}")
        pos = rec.get("position") or [0, 0, 0]
        try:
            root.setPos(float(pos[0]), float(pos[1]), float(pos[2]))
        except Exception:
            pass
        try:
            rot = rec.get("rotation") or [0,0,0]
            root.setHpr(float(rot[0]), float(rot[1]), float(rot[2]))
        except Exception:
            pass
        if ghost:
            root.setAlphaScale(0.42)
            root.setTransparency(TransparencyAttrib.MAlpha)
        if entry["id"] == "spore_totem":
            _draw_spore_totem(root, rec, stage, entry, selected=selected)
        elif entry["id"] == "glitch_growth":
            _draw_glitch_growth(root, rec, stage, entry, selected=selected)
        elif entry["kind"] == "plant":
            _draw_weird_plant(root, rec, stage, entry, selected=selected)
        else:
            _draw_floating_object(root, rec, stage, entry, selected=selected)
        _draw_study_marker(root, rec, stage, entry, selected=selected)
        try:
            root.setPythonTag("oddities_visual_stage", int(stage))
            root.setPythonTag("oddities_visual_type", str(entry["id"]))
        except Exception:
            pass
        if selected:
            _line_node(root, "oddities_selected_ring", _circle_segments(3.2, 0.08, "xy", 36), (1.0, 1.0, 1.0, 0.82), 2.2)
        return root

    def redraw_oddities(self):
        _ensure_runtime_nodes(self)
        try:
            self.oddities_root.node().removeAllChildren()
        except Exception:
            pass
        nodes = []
        for idx, rec in enumerate(list(getattr(self, "oddities_items", []) or [])):
            try:
                rec["stage"] = _stage_for_oddity(rec)
                nodes.append(_draw_oddity_node(self, rec, idx, ghost=False))
            except Exception as exc:
                print(f"oddities_draw_error: {exc}")
        self.oddities_nodes = nodes
        update_oddities_ui(self)
        return nodes

    def update_oddities_ghost(self):
        if not bool(getattr(self, "oddities_active", False)):
            return
        _ensure_runtime_nodes(self)
        try:
            rec = _current_oddity_record(self)
            sig = (rec.get("type"), tuple(rec.get("position") or []), rec.get("seed"), int(getattr(self, "oddities_type_index", 0)))
            if sig == getattr(self, "oddities_last_ghost_signature", None):
                return
            self.oddities_last_ghost_signature = sig
            self.oddities_ghost_root.node().removeAllChildren()
            _draw_oddity_node(self, rec, -1, ghost=True)
        except Exception as exc:
            print(f"oddities_ghost_error: {exc}")

    def update_oddities_ui(self):
        if not bool(getattr(self, "oddities_active", False)):
            return
        try:
            entry = _catalog_entry(self)
            items = list(getattr(self, "oddities_items", []) or [])
            mature = sum(1 for p in items if _stage_for_oddity(p) >= 3)
            ready = sum(1 for p in items if _stage_for_oddity(p) >= 3 and str(p.get("last_collected_day") or "")[:10] != _today_key())
            sel = int(getattr(self, "oddities_selected_index", -1))
            selected_text = "NONE"
            if 0 <= sel < len(items):
                rec = items[sel]
                props = rec.get("properties", {}) if isinstance(rec.get("properties"), dict) else {}
                selected_text = f"{str(rec.get('name', 'ODD')).upper()} S{_stage_for_oddity(rec)} W{props.get('weirdness', '?')}"
            snap = "ON" if bool(getattr(self, "oddities_snap_enabled", True)) else "OFF"
            if self.oddities_ui_tool is not None:
                self.oddities_ui_tool["text"] = f"Type {entry['label']} | Saved {len(items)}/{MAX_ODDITIES} | Mature {mature} | Ready {ready} | Selected {selected_text}"
            if self.oddities_ui_help is not None:
                self.oddities_ui_help["text"] = "LMB/E create saved specimen | Q type | X study | H collect | Del remove | G save | Esc save+exit"
        except Exception as exc:
            print(f"oddities_ui_error: {exc}")

    def activate_oddities_from_mode(self, mode=None, source="core", route=""):
        for attr, close_reason in (("holoforge_active", "oddities-open"), ("forest_growth_active", "oddities-open"), ("hills_life_active", "oddities-open")):
            try:
                if bool(getattr(self, attr, False)):
                    fn_name = {"holoforge_active": "deactivate_holoforge", "forest_growth_active": "deactivate_forest_growth", "hills_life_active": "deactivate_hills_life"}[attr]
                    fn = getattr(self, fn_name, None)
                    if callable(fn):
                        fn(reason=close_reason)
            except Exception:
                pass
        if not _mushroom_allowed(self):
            try:
                self.travel_to_holoverse_region_index(MUSHROOM_REGION_NUMBER)
            except Exception:
                pass
        _ensure_dirs()
        _ensure_runtime_nodes(self)
        if not bool(getattr(self, "oddities_loaded", False)):
            load_oddities(self)
        if not list(getattr(self, "oddities_items", []) or []):
            if _seed_starter_oddities(self):
                save_oddities(self, reason="starter-seed")
        self.oddities_active = True
        self.oddities_root.show(); self.oddities_ghost_root.show(); self.oddities_ui_root.show()
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
        label = str((mode or {}).get("name") or "Oddities")
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
            self.record_matrixcore_dimension_signal("dimension_launch", label, label=label, route=IN_WORLD_ROUTE, source=str(source or "core"), reason="oddities_region_runtime")
            self.record_matrixcore_bot_signal("bot_launch", "Solace", "MUSHROOM", "Oddities", route=IN_WORLD_ROUTE, source="oddities_runtime")
        except Exception:
            pass
        try:
            self._append_mode_gateway_history("oddities_runtime_open", mode=mode, label=label, route=IN_WORLD_ROUTE, extra={"source": source, "oddity_count": len(self.oddities_items), "state": str(STATE_PATH)})
        except Exception:
            pass
        _sync_progression_save(self, reason="activate")
        redraw_oddities(self)
        self.center_hint["text"] = "ODDITIES // LMB CREATES SAVED MUSHROOM SPECIMENS"
        if getattr(self, "audio", None):
            self.audio.play("world_shift.wav", "sfx", 0.52)
        return True

    def deactivate_oddities(self, reason="closed"):
        if not bool(getattr(self, "oddities_active", False)):
            return False
        save_oddities(self, reason=reason)
        self.oddities_active = False
        for attr in ("oddities_ghost_root", "oddities_ui_root", "oddities_root"):
            try:
                node = getattr(self, attr, None)
                if node is not None and not node.isEmpty():
                    node.hide()
            except Exception:
                pass
        try:
            self._append_mode_gateway_history("oddities_runtime_close", label="Oddities", route=IN_WORLD_ROUTE, extra={"reason": reason, "oddity_count": len(self.oddities_items), "state": str(STATE_PATH)})
        except Exception:
            pass
        self.center_hint["text"] = "ODDITIES // SAVED + CLOSED"
        return True

    def oddities_cycle_type(self, direction=1):
        if not bool(getattr(self, "oddities_active", False)):
            return False
        catalog = _catalog(self)
        self.oddities_type_index = (int(getattr(self, "oddities_type_index", 0)) + int(direction or 1)) % len(catalog)
        self.oddities_last_ghost_signature = None
        update_oddities_ghost(self)
        update_oddities_ui(self)
        self.center_hint["text"] = f"ODDITIES // TYPE {catalog[self.oddities_type_index]['label'].upper()}"
        return True

    def oddities_toggle_snap(self):
        if not bool(getattr(self, "oddities_active", False)):
            return False
        self.oddities_snap_enabled = not bool(getattr(self, "oddities_snap_enabled", True))
        self.oddities_last_ghost_signature = None
        update_oddities_ui(self)
        self.center_hint["text"] = f"ODDITIES // SNAP {'ON' if self.oddities_snap_enabled else 'OFF'}"
        return True

    def oddities_place(self, source="key"):
        if not bool(getattr(self, "oddities_active", False)):
            return False
        if len(getattr(self, "oddities_items", []) or []) >= MAX_ODDITIES:
            self.center_hint["text"] = f"ODDITIES // POPULATION CAP {MAX_ODDITIES}"
            return False
        rec = _current_oddity_record(self)
        self.oddities_items.append(rec)
        self.oddities_selected_index = len(self.oddities_items) - 1
        self.oddities_dirty = True
        self.oddities_last_ghost_signature = None
        redraw_oddities(self)
        save_oddities(self, reason="place")
        self.center_hint["text"] = f"ODDITIES // CREATED + SAVED {str(rec.get('label', 'ODDITY')).upper()}"
        return True

    def oddities_inspect_nearest(self):
        if not bool(getattr(self, "oddities_active", False)):
            return False
        items = list(getattr(self, "oddities_items", []) or [])
        if not items:
            self.oddities_selected_index = -1
            self.center_hint["text"] = "ODDITIES // NOTHING TO INSPECT"
            return False
        try:
            px, py = float(self.player_pos.x), float(self.player_pos.y)
        except Exception:
            px, py = 0.0, 0.0
        best_idx, best_dist = -1, 999999.0
        for idx, rec in enumerate(items):
            try:
                pos = rec.get("position") or [0, 0, 0]
                dist = math.hypot(float(pos[0]) - px, float(pos[1]) - py)
                if dist < best_dist:
                    best_idx, best_dist = idx, dist
            except Exception:
                continue
        if best_idx < 0:
            return False
        if int(getattr(self, "oddities_selected_index", -1)) == best_idx:
            self.oddities_selected_index = -1
            self.center_hint["text"] = "ODDITIES // SELECTION CLEARED"
        else:
            self.oddities_selected_index = best_idx
            rec = items[best_idx]
            props = rec.get("properties", {}) if isinstance(rec.get("properties"), dict) else {}
            self.center_hint["text"] = f"ODDITIES // {str(rec.get('name','ODD')).upper()} // STAGE {_stage_for_oddity(rec)} // {props.get('behavior','?').upper()} W{props.get('weirdness','?')} S{props.get('stability','?')}"
        redraw_oddities(self)
        update_oddities_ui(self)
        return True

    def oddities_collect_selected(self):
        if not bool(getattr(self, "oddities_active", False)):
            # Preserve H on Hills Life / Forest Growth when Oddities is inactive.
            for fn_name in ("hills_life_collect_selected", "forest_growth_harvest_selected"):
                fn = getattr(self, fn_name, None)
                if callable(fn):
                    try:
                        return fn()
                    except TypeError:
                        return fn(self)
            return False
        items = list(getattr(self, "oddities_items", []) or [])
        idx = int(getattr(self, "oddities_selected_index", -1))
        if idx < 0 or idx >= len(items):
            self.center_hint["text"] = "ODDITIES // SELECT A MATURE ODDITY FIRST"
            return False
        rec = items[idx]
        if _stage_for_oddity(rec) < 3:
            self.center_hint["text"] = "ODDITIES // NOT MATURE YET"
            return False
        if str(rec.get("last_collected_day") or "")[:10] == _today_key():
            self.center_hint["text"] = "ODDITIES // ALREADY COLLECTED TODAY"
            return False
        gift = str(rec.get("gift") or _catalog_entry(self, rec.get("type"))["gift"])
        inv = dict(getattr(self, "oddities_inventory", {}) or {})
        inv[gift] = int(inv.get(gift, 0)) + 1
        self.oddities_inventory = inv
        rec["last_collected_day"] = _today_key()
        items[idx] = rec
        self.oddities_items = items
        self.oddities_dirty = True
        save_oddities(self, reason="collect")
        update_oddities_ui(self)
        self.center_hint["text"] = f"ODDITIES // COLLECTED {gift.upper().replace('_', ' ')}"
        return True

    def oddities_delete_selected(self):
        if not bool(getattr(self, "oddities_active", False)):
            return False
        items = list(getattr(self, "oddities_items", []) or [])
        idx = int(getattr(self, "oddities_selected_index", -1))
        if idx < 0 or idx >= len(items):
            self.center_hint["text"] = "ODDITIES // SELECT FIRST"
            return False
        rec = items.pop(idx)
        self.oddities_items = items
        self.oddities_selected_index = -1
        self.oddities_dirty = True
        redraw_oddities(self)
        save_oddities(self, reason="remove")
        self.center_hint["text"] = f"ODDITIES // REMOVED {str(rec.get('name', rec.get('label', 'ODDITY'))).upper()}"
        return True

    def _update_oddity_motion(self, now, dt):
        items = list(getattr(self, "oddities_items", []) or [])
        nodes = list(getattr(self, "oddities_nodes", []) or [])
        changed = False
        for idx, rec in enumerate(items):
            if idx >= len(nodes):
                continue
            node = nodes[idx]
            if node is None or node.isEmpty():
                continue
            try:
                props = rec.get("properties", {}) if isinstance(rec.get("properties"), dict) else {}
                behavior = str(props.get("behavior", "bob"))
                stage = _stage_for_oddity(rec)
                pos = rec.get("position") or [0,0,0]
                home = rec.get("home_position") or pos
                x, y, z = float(pos[0]), float(pos[1]), float(pos[2])
                hx, hy = float(home[0]), float(home[1])
                phase = float(rec.get("phase", 0.0)) + max(0.01, dt) * (0.9 + float(props.get("energy", 5))*0.08)
                rec["phase"] = phase
                if _catalog_entry(self, rec.get("type"))["kind"] == "object":
                    amp = 0.45 + float(props.get("weirdness", 6)) * 0.13
                    zz = z + math.sin(phase) * amp
                    if behavior == "orbit":
                        rad = 1.2 + stage * 0.55
                        node.setPos(hx + math.cos(phase*0.7)*rad, hy + math.sin(phase*0.7)*rad, zz)
                    elif behavior == "jitter":
                        node.setPos(x + math.sin(phase*3.1)*0.25, y + math.cos(phase*2.4)*0.25, zz)
                    elif behavior == "drift":
                        node.setPos(hx + math.sin(phase*0.28)*1.6, hy + math.cos(phase*0.31)*1.2, zz)
                    else:
                        node.setPos(x, y, zz)
                    node.setH((float((rec.get("rotation") or [0])[0]) + phase * (18.0 if behavior == "spin" else 5.0)) % 360.0)
                    node.setP(math.sin(phase*0.7) * (4.0 + stage))
                else:
                    # Plants don't walk; they pulse and lean according to their unstable pattern.
                    node.setH((float((rec.get("rotation") or [0])[0]) + math.sin(phase*0.2)*2.0) % 360.0)
                    node.setR(math.sin(phase*0.55) * (1.5 + stage * 0.4))
                changed = True
            except Exception as exc:
                print(f"oddities_motion_error: {exc}")
        if changed:
            self.oddities_items = items
            self.oddities_dirty = True
        return changed

    def update_oddities(self, dt=0.0):
        if not bool(getattr(self, "oddities_active", False)):
            return
        if not _mushroom_allowed(self):
            deactivate_oddities(self, reason="left-mushroom-region")
            return
        today = _today_key()
        if today != getattr(self, "oddities_last_day", today):
            self.oddities_last_day = today
            self.oddities_dirty = True
            redraw_oddities(self)
            save_oddities(self, reason="new-day-growth")
            try:
                self.center_hint["text"] = "ODDITIES // NEW DAY // PATTERNS MUTATED"
            except Exception:
                pass
        update_oddities_ghost(self)
        now = time.time()
        if (now - float(getattr(self, "oddities_last_anim_at", 0.0))) >= 0.08:
            elapsed = min(0.25, max(0.04, now - float(getattr(self, "oddities_last_anim_at", now))))
            self.oddities_last_anim_at = now
            _update_oddity_motion(self, now, elapsed)
            update_oddities_ui(self)
        if bool(getattr(self, "oddities_dirty", False)) and (time.time() - float(getattr(self, "oddities_last_save_at", 0.0))) > 18.0:
            save_oddities(self, reason="autosave")

    # Attach runtime API.
    CommandHubApp.is_oddities_mode = _is_oddities_mode
    CommandHubApp.activate_oddities_from_mode = activate_oddities_from_mode
    CommandHubApp.deactivate_oddities = deactivate_oddities
    CommandHubApp.save_oddities = save_oddities
    CommandHubApp.export_oddities_library = export_oddities_library
    CommandHubApp.load_oddities = load_oddities
    CommandHubApp.redraw_oddities = redraw_oddities
    CommandHubApp.update_oddities = update_oddities
    CommandHubApp.update_oddities_ui = update_oddities_ui
    CommandHubApp.oddities_cycle_type = oddities_cycle_type
    CommandHubApp.oddities_toggle_snap = oddities_toggle_snap
    CommandHubApp.oddities_place = oddities_place
    CommandHubApp.oddities_inspect_nearest = oddities_inspect_nearest
    CommandHubApp.oddities_collect_selected = oddities_collect_selected
    CommandHubApp.oddities_delete_selected = oddities_delete_selected

    old_init = CommandHubApp.__init__
    def __init__(self, *args, **kwargs):
        old_init(self, *args, **kwargs)
        _init_state(self)
    CommandHubApp.__init__ = __init__

    old_setup_input = CommandHubApp.setup_input
    def setup_input(self, *args, **kwargs):
        result = old_setup_input(self, *args, **kwargs)
        self.accept("h", self.oddities_collect_selected)
        return result
    CommandHubApp.setup_input = setup_input

    old_e = CommandHubApp.on_e_down
    def on_e_down(self):
        if bool(getattr(self, "oddities_active", False)):
            self.set_key("e", True)
            self.oddities_place(source="e")
            return
        return old_e(self)
    CommandHubApp.on_e_down = on_e_down

    old_q = CommandHubApp.on_q_down
    def on_q_down(self):
        if bool(getattr(self, "oddities_active", False)):
            self.set_key("q", True)
            self.oddities_cycle_type(1)
            return
        return old_q(self)
    CommandHubApp.on_q_down = on_q_down

    old_primary = CommandHubApp.primary_click_interact
    def primary_click_interact(self):
        if bool(getattr(self, "oddities_active", False)):
            self.oddities_place(source="mouse1")
            return
        return old_primary(self)
    CommandHubApp.primary_click_interact = primary_click_interact

    old_start_escape_hold = CommandHubApp.start_escape_hold
    def start_escape_hold(self):
        if bool(getattr(self, "oddities_active", False)):
            self.deactivate_oddities(reason="escape")
            return
        return old_start_escape_hold(self)
    CommandHubApp.start_escape_hold = start_escape_hold

    old_delete = getattr(CommandHubApp, "holoforge_delete_selected", None)
    if callable(old_delete):
        def holoforge_delete_selected(self):
            if bool(getattr(self, "oddities_active", False)):
                return self.oddities_delete_selected()
            return old_delete(self)
        CommandHubApp.holoforge_delete_selected = holoforge_delete_selected

    old_g_save = getattr(CommandHubApp, "holoforge_save_blueprint", None)
    if callable(old_g_save):
        def holoforge_save_blueprint(self):
            if bool(getattr(self, "oddities_active", False)):
                return self.save_oddities(reason="manual")
            return old_g_save(self)
        CommandHubApp.holoforge_save_blueprint = holoforge_save_blueprint

    old_x_select = getattr(CommandHubApp, "holoforge_select_or_clear", None)
    if callable(old_x_select):
        def holoforge_select_or_clear(self):
            if bool(getattr(self, "oddities_active", False)):
                return self.oddities_inspect_nearest()
            return old_x_select(self)
        CommandHubApp.holoforge_select_or_clear = holoforge_select_or_clear

    old_b_snap = getattr(CommandHubApp, "holoforge_toggle_snap", None)
    if callable(old_b_snap):
        def holoforge_toggle_snap(self):
            if bool(getattr(self, "oddities_active", False)):
                return self.oddities_toggle_snap()
            return old_b_snap(self)
        CommandHubApp.holoforge_toggle_snap = holoforge_toggle_snap

    old_route = CommandHubApp.launch_core_mode_route
    def launch_core_mode_route(self, mode, source="core", extra_env=None, close_core=True):
        if self.is_oddities_mode(mode):
            return bool(self.activate_oddities_from_mode(mode, source=source, route=IN_WORLD_ROUTE))
        return old_route(self, mode, source=source, extra_env=extra_env, close_core=close_core)
    CommandHubApp.launch_core_mode_route = launch_core_mode_route

    old_region_ui = CommandHubApp.update_holoverse_region_ui
    def update_holoverse_region_ui(self):
        result = old_region_ui(self)
        if bool(getattr(self, "oddities_active", False)):
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
                self.update_oddities(0.0)
        except Exception as exc:
            print(f"oddities_update_error: {exc}")
        return result
    CommandHubApp.update_task = update_task

    setattr(main, "ODDITIES_RUNTIME_INSTALLED", True)
    setattr(main, "ODDITIES_STATE_PATH_RUNTIME", STATE_PATH)
