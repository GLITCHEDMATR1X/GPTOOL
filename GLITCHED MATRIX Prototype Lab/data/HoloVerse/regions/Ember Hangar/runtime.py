"""Ember Hangar in-world runtime for the live DESERT HoloVerse region.

Ember Forge is now a vehicle showroom, not a player object editor.  Each mission
confirmation generates one fresh Fighter, Speeder, Hauler, and UFO variant in a
clean forge lineup.  Clicking or pressing E while aiming at a vehicle binds it
as the player's saved HoloVerse TAB craft, replaces the previous active vehicle,
and enters/pilots it immediately.
"""
from __future__ import annotations

import json
import math
import random
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

from direct.gui.DirectGui import DirectFrame, DirectLabel
from panda3d.core import (
    AntialiasAttrib, Geom, GeomNode, GeomTriangles, GeomVertexData,
    GeomVertexFormat, GeomVertexWriter, LineSegs, NodePath, TextNode,
    TransparencyAttrib, Vec3,
)

IN_WORLD_ROUTE = "in_world_region"
DESERT_SHIPS_SCHEMA = 1
DESERT_REGION_NUMBER = 4
MAX_DESERT_SHIPS = 4
FORGE_LINEUP_COUNT = 4
DEFAULT_CLASSES = ("fighter", "speeder", "hauler", "ufo")


def _main_module(cls):
    return sys.modules.get(cls.__module__) or sys.modules.get("__main__")


def install_desert_ships_runtime(CommandHubApp):
    main = _main_module(CommandHubApp)
    if main is None:
        return

    from holoverse_mode_runtime import resolve_shared_data_root

    ROOT = Path(getattr(main, "ROOT", Path(__file__).resolve().parent))
    SHARED_DATA_ROOT = resolve_shared_data_root(main, ROOT)
    STATE_DIR = SHARED_DATA_ROOT / "holoverse" / "regions" / "desert" / "ships"
    STATE_PATH = STATE_DIR / "desert_ship_state.json"
    LOG_DIR = ROOT / "logs"
    ERROR_LOG = LOG_DIR / "ember_hangar_runtime_error.txt"
    ROOT_PROGRESS_PATH = ROOT / "progression" / "progression_state.json"
    SHARED_PROGRESS_PATH = SHARED_DATA_ROOT / "holoverse" / "progression" / "progression_state.json"

    from holoverse_mode_runtime import install_in_world_route_aliases

    install_in_world_route_aliases(main)

    def _ensure_dirs():
        for folder in (STATE_DIR, LOG_DIR, ROOT_PROGRESS_PATH.parent, SHARED_PROGRESS_PATH.parent, SHARED_DATA_ROOT / "brain", SHARED_DATA_ROOT / "database"):
            folder.mkdir(parents=True, exist_ok=True)

    def _log_runtime_error(self, label: str, exc: Exception | None = None, detail: str = ""):
        """Write Ember failures without taking down the whole HoloVerse app."""
        try:
            _ensure_dirs()
            lines = [
                f"[{datetime.now().isoformat(timespec='seconds')}] {str(label or 'ember_runtime_error')}",
                f"detail: {str(detail or '')}",
            ]
            if exc is not None:
                lines.append(f"error: {exc.__class__.__name__}: {exc}")
                lines.append(traceback.format_exc())
            with ERROR_LOG.open("a", encoding="utf-8") as fh:
                fh.write("\n".join(lines).rstrip() + "\n---\n")
        except Exception:
            pass
        try:
            if exc is not None:
                print(f"ember_hangar_runtime_error:{label}:{exc.__class__.__name__}:{exc}")
            else:
                print(f"ember_hangar_runtime_notice:{label}:{detail}")
        except Exception:
            pass

    def _set_center_hint(self, text: str):
        try:
            self.center_hint["text"] = str(text or "")
        except Exception:
            pass

    def _to_float(value, default=0.0, *, clamp_abs=None):
        try:
            out = float(value)
            if math.isnan(out) or math.isinf(out):
                return float(default)
            if clamp_abs is not None:
                cap = abs(float(clamp_abs))
                out = max(-cap, min(cap, out))
            return out
        except Exception:
            return float(default)

    def _ship_catalog(self):
        return [
            {
                "id": "fighter",
                "label": "Fighter",
                "color": (1.00, 0.34, 0.16, 0.92),
                "accent": (1.00, 0.92, 0.30, 0.98),
                "spacing": 12.0,
                "stats": {"speed": 7, "boost": 7, "handling": 7, "cargo": 1, "stability": 4},
                "description": "sharp combat ship with forward nose, wings, and engine prongs",
            },
            {
                "id": "speeder",
                "label": "Speeder",
                "color": (0.18, 0.96, 1.00, 0.92),
                "accent": (0.68, 1.00, 0.96, 0.98),
                "spacing": 10.0,
                "stats": {"speed": 9, "boost": 9, "handling": 8, "cargo": 0, "stability": 3},
                "description": "slender high-speed craft with long fins and small hull mass",
            },
            {
                "id": "hauler",
                "label": "Hauler",
                "color": (1.00, 0.72, 0.22, 0.92),
                "accent": (0.95, 0.42, 0.12, 0.98),
                "spacing": 16.0,
                "stats": {"speed": 4, "boost": 4, "handling": 3, "cargo": 9, "stability": 8},
                "description": "large heavy carrier with cargo ribs and wide engine pods",
            },
            {
                "id": "ufo",
                "label": "UFO",
                "color": (0.78, 0.36, 1.00, 0.92),
                "accent": (0.24, 1.00, 0.74, 0.98),
                "spacing": 13.0,
                "stats": {"speed": 6, "boost": 6, "handling": 9, "cargo": 2, "stability": 7},
                "description": "round alien hover craft with ring lights and smooth vertical lift feel",
            },
        ]

    def _catalog_entry(self, ship_class=None):
        catalog = _ship_catalog(self)
        raw = str(ship_class or catalog[int(getattr(self, "desert_ships_class_index", 0)) % len(catalog)]["id"]).strip().lower()
        aliases = {"fighters": "fighter", "speeders": "speeder", "haulers": "hauler", "ufos": "ufo", "saucer": "ufo"}
        raw = aliases.get(raw, raw)
        for entry in catalog:
            if entry["id"] == raw:
                return entry
        return catalog[0]

    def _init_state(self):
        self.desert_ships_active = False
        self.desert_ships_loaded = False
        self.desert_ships_root = None
        self.desert_ships_ui_root = None
        self.desert_ships_ui_panel = None
        self.desert_ships_ui_title = None
        self.desert_ships_ui_tool = None
        self.desert_ships_ui_help = None
        self.desert_ships = []  # current four-vehicle forge lineup only
        self.desert_ship_nodes = []
        self.desert_ships_selected_index = -1
        self.desert_ships_default_id = ""
        self.desert_active_ship_data = None
        self.desert_forge_generation = 0
        self.desert_ships_last_save_at = 0.0
        self.desert_ships_dirty = False
        self.desert_ship_state_path = STATE_PATH
        self.desert_ship_voxel_box_model = None
        self.desert_ship_forge_pad_root = None
        self.desert_ship_ambient_seeded = False
        self.desert_ship_visual_style = "filled_voxel_3d_showroom"
        self.shell_flight_craft_data = None
        self.shell_flight_craft_visual_root = None
        self.shell_flight_craft_visual_signature = ""
        self.shell_flight_craft_default_loaded_at = 0.0

    def _is_desert_ships_mode(self, mode):
        data = dict(mode or {})
        manifest = dict(data.get("manifest") or {})
        tokens = " ".join(str(x or "") for x in (
            data.get("name"), data.get("id"), data.get("title"),
            manifest.get("id"), manifest.get("title"), manifest.get("description"),
            manifest.get("host_contract"), manifest.get("preferred_display"),
        )).lower()
        return (
            "ember hangar" in tokens
            or "desert ships" in tokens
            or "duneworks" in tokens
            or "ship forge" in tokens
            or "ship generation" in tokens
            or str(manifest.get("id") or data.get("id") or "").lower() == "ember_hangar"
            or str(data.get("name") or "").lower() == "ember hangar"
        )

    def _desert_allowed(self):
        try:
            if self.is_holospace_active():
                return False
        except Exception:
            pass
        try:
            return int(self.current_holoverse_region_number()) == DESERT_REGION_NUMBER
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

    def _flat_basis_from_view(self):
        try:
            forward, right, _up = self.get_view_basis()
        except Exception:
            forward, right = Vec3(0, 1, 0), Vec3(1, 0, 0)
        forward = Vec3(float(forward.x), float(forward.y), 0.0)
        if forward.lengthSquared() <= 0.001:
            yaw = math.radians(float(getattr(self, "player_yaw", 0.0)))
            forward = Vec3(-math.sin(yaw), math.cos(yaw), 0.0)
        if forward.lengthSquared() <= 0.001:
            forward = Vec3(0.0, 1.0, 0.0)
        forward.normalize()
        right = Vec3(float(right.x), float(right.y), 0.0)
        if right.lengthSquared() <= 0.001:
            right = Vec3(forward.y, -forward.x, 0.0)
        if right.lengthSquared() <= 0.001:
            right = Vec3(1.0, 0.0, 0.0)
        right.normalize()
        yaw_deg = math.degrees(math.atan2(-forward.x, forward.y))
        return forward, right, yaw_deg

    def _forge_center_point(self):
        try:
            base = Vec3(getattr(self, "player_pos", Vec3(0, 0, 0)))
        except Exception:
            base = Vec3(0, 0, 0)
        forward, _right, _yaw = _flat_basis_from_view(self)
        center = base + forward * 34.0
        center.z = _floor_z(self, center.x, center.y) + 5.8
        return center

    def _forge_lineup_position(self, slot_index: int):
        center = _forge_center_point(self)
        _forward, right, _yaw = _flat_basis_from_view(self)
        offset = (float(slot_index) - 1.5) * 15.5
        pos = center + right * offset
        pos.z = _floor_z(self, pos.x, pos.y) + 5.8
        return pos

    def _class_label(self, ship_class=None):
        return str(_catalog_entry(self, ship_class).get("label") or ship_class or "Ship")

    def _ship_name(self, ship_class, seed):
        label = _class_label(self, ship_class).replace(" ", "")
        return f"{label}-{int(seed) % 100000:05d}"

    def _safe_rgba(value, fallback):
        raw = value if isinstance(value, (list, tuple)) else fallback
        try:
            parts = [float(v) for v in list(raw)[:4]]
        except Exception:
            parts = [float(v) for v in list(fallback)[:4]]
        while len(parts) < 4:
            parts.append(1.0)
        return tuple(max(0.0, min(1.0, v)) for v in parts[:4])

    def _variant_colors(self, entry, seed):
        rng = random.Random(int(seed) ^ 0xE47B3)
        base = _safe_rgba(entry.get("color", (1.0, 0.55, 0.18, 0.94)), (1.0, 0.55, 0.18, 0.94))
        accent = _safe_rgba(entry.get("accent", (1.0, 0.95, 0.35, 0.98)), (1.0, 0.95, 0.35, 0.98))
        shift = rng.uniform(-0.18, 0.22)
        warmth = rng.uniform(0.00, 0.24)
        cool = rng.uniform(0.00, 0.16)
        color = (
            max(0.05, min(1.0, base[0] + shift + warmth * 0.35)),
            max(0.05, min(1.0, base[1] - shift * 0.35 + cool * 0.30)),
            max(0.05, min(1.0, base[2] + cool - warmth * 0.20)),
            base[3],
        )
        accent2 = (
            max(0.10, min(1.0, accent[0] + rng.uniform(-0.10, 0.16))),
            max(0.10, min(1.0, accent[1] + rng.uniform(-0.10, 0.18))),
            max(0.10, min(1.0, accent[2] + rng.uniform(-0.10, 0.20))),
            accent[3],
        )
        return color, accent2

    def _new_forge_vehicle(self, ship_class=None, *, slot_index=0, pos=None, rotation=None):
        entry = _catalog_entry(self, ship_class)
        generation = int(getattr(self, "desert_forge_generation", 0) or 0)
        seed = random.randint(10000, 999999999)
        pos = Vec3(pos if pos is not None else _forge_lineup_position(self, int(slot_index)))
        _forward, _right, yaw_default = _flat_basis_from_view(self)
        yaw = float(rotation if rotation is not None else yaw_default)
        color, accent = _variant_colors(self, entry, seed)
        ship = {
            "id": f"ember_vehicle_{entry['id']}_{generation}_{int(time.time() * 1000)}_{seed % 10000:04d}",
            "class": entry["id"],
            "seed": int(seed),
            "name": f"Ember {_ship_name(self, entry['id'], seed)}",
            "position": [round(float(pos.x), 3), round(float(pos.y), 3), round(float(pos.z), 3)],
            "rotation": round(float(yaw), 3),
            "stats": dict(entry.get("stats") or {}),
            "color": [round(float(v), 4) for v in color],
            "accent": [round(float(v), 4) for v in accent],
            "forge_lineup_index": int(slot_index),
            "forge_generation": generation,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "is_default": False,
        }
        rng = random.Random(seed ^ 0x51AB)
        for key in ("speed", "boost", "handling", "cargo", "stability"):
            try:
                base = int(ship["stats"].get(key, 5))
                ship["stats"][key] = max(0, min(10, base + rng.choice((-1, 0, 0, 1))))
            except Exception:
                pass
        return ship

    def _default_starter_ship(self):
        return {
            "id": "starter_holocraft",
            "class": "fighter",
            "seed": 271828,
            "name": "Starter HoloCraft",
            "position": [0.0, 0.0, 8.0],
            "rotation": 0.0,
            "stats": {"speed": 6, "boost": 6, "handling": 6, "cargo": 1, "stability": 5},
            "is_default": True,
            "starter": True,
        }

    def _load_payload() -> dict:
        _ensure_dirs()
        try:
            if STATE_PATH.exists():
                data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
        except Exception as exc:
            try:
                backup = STATE_PATH.with_suffix(f".bad_{int(time.time())}.json")
                STATE_PATH.replace(backup)
                _log_runtime_error(None, "state_backup", exc, detail=f"Moved unreadable state to {backup}")
            except Exception:
                try:
                    _log_runtime_error(None, "state_load", exc, detail=str(STATE_PATH))
                except Exception:
                    pass
        return {"schema": DESERT_SHIPS_SCHEMA, "kind": "holoverse_desert_ship_state", "ships": [], "default_ship_id": ""}

    def _normalize_ship(self, raw) -> dict | None:
        if not isinstance(raw, dict):
            return None
        entry = _catalog_entry(self, raw.get("class"))
        try:
            seed = int(raw.get("seed") or random.randint(10000, 999999999))
        except Exception:
            seed = random.randint(10000, 999999999)
        pos = raw.get("position") or [0, 0, 5]
        if not isinstance(pos, (list, tuple)) or len(pos) < 3:
            pos = [0, 0, 5]
        stats = dict(entry.get("stats") or {})
        if isinstance(raw.get("stats"), dict):
            for key, value in raw.get("stats", {}).items():
                try:
                    stats[str(key)] = int(value)
                except Exception:
                    pass
        color = _safe_rgba(raw.get("color"), entry.get("color", (1.0, 0.55, 0.18, 0.94)))
        accent = _safe_rgba(raw.get("accent"), entry.get("accent", (1.0, 0.95, 0.35, 0.98)))
        ship_id = str(raw.get("id") or f"ship_{seed}").strip() or f"ship_{seed}"
        name = str(raw.get("name") or _ship_name(self, entry["id"], seed)).strip() or _ship_name(self, entry["id"], seed)
        return {
            "id": ship_id[:96],
            "class": entry["id"],
            "seed": seed,
            "name": name[:96],
            "position": [_to_float(pos[0], 0.0, clamp_abs=25000), _to_float(pos[1], 0.0, clamp_abs=25000), _to_float(pos[2], 5.0, clamp_abs=2500)],
            "rotation": _to_float(raw.get("rotation"), 0.0, clamp_abs=3600) % 360.0,
            "stats": stats,
            "color": [round(float(v), 4) for v in color],
            "accent": [round(float(v), 4) for v in accent],
            "forge_lineup_index": int(raw.get("forge_lineup_index", 0) or 0),
            "forge_generation": int(raw.get("forge_generation", 0) or 0),
            "created_at": str(raw.get("created_at") or datetime.now().isoformat(timespec="seconds")),
            "updated_at": str(raw.get("updated_at") or datetime.now().isoformat(timespec="seconds")),
            "is_default": bool(raw.get("is_default", False)),
        }

    def load_desert_ships(self):
        payload = _load_payload()
        ships = []
        skipped = 0
        for raw in list(payload.get("ships") or []):
            try:
                norm = _normalize_ship(self, raw)
                if norm is not None:
                    ships.append(norm)
            except Exception as exc:
                skipped += 1
                _log_runtime_error(self, "normalize_ship", exc, detail=str(raw)[:500])
        self.desert_ships = ships[:MAX_DESERT_SHIPS]
        default_id = str(payload.get("default_ship_id") or "").strip()
        if default_id and any(s.get("id") == default_id for s in self.desert_ships):
            self.desert_ships_default_id = default_id
        else:
            marked = next((s for s in self.desert_ships if bool(s.get("is_default"))), None)
            self.desert_ships_default_id = str(marked.get("id")) if marked else ""
        for ship in self.desert_ships:
            ship["is_default"] = bool(ship.get("id") == self.desert_ships_default_id)
        active = next((s for s in self.desert_ships if bool(s.get("is_default"))), None)
        self.desert_active_ship_data = dict(active) if active else None
        self.desert_ships_loaded = True
        if skipped:
            _set_center_hint(self, f"EMBER HANGAR // SKIPPED {skipped} BAD SHIP RECORDS")
        return self.desert_ships

    def _state_payload(self):
        default_id = str(getattr(self, "desert_ships_default_id", "") or "")
        lineup = list(getattr(self, "desert_ships", []) or [])
        default_ship = next((s for s in lineup if s.get("id") == default_id), None)
        if default_ship is None and isinstance(getattr(self, "desert_active_ship_data", None), dict):
            default_ship = dict(getattr(self, "desert_active_ship_data") or {})
            default_id = str(default_ship.get("id") or default_id)
        saved_ship = None
        if default_ship:
            saved_ship = dict(default_ship)
            saved_ship["is_default"] = True
            saved_ship["updated_at"] = datetime.now().isoformat(timespec="seconds")
        return {
            "schema": DESERT_SHIPS_SCHEMA,
            "kind": "holoverse_ember_vehicle_state",
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "save_path": str(STATE_PATH),
            "default_ship_id": default_id if saved_ship else "",
            "default_ship_class": str(saved_ship.get("class") if saved_ship else ""),
            "default_ship_name": str(saved_ship.get("name") if saved_ship else ""),
            "ships": [saved_ship] if saved_ship else [],
            "active_vehicle": saved_ship,
            "ship_classes": list(DEFAULT_CLASSES),
            "forge_lineup_count": FORGE_LINEUP_COUNT,
            "tab_craft_rule": "selected_ember_vehicle_replaces_previous_global_tab_craft",
        }

    def _mirror_progress(self):
        default_id = str(getattr(self, "desert_ships_default_id", "") or "")
        default_ship = next((s for s in list(getattr(self, "desert_ships", []) or []) if s.get("id") == default_id), None)
        if default_ship is None and isinstance(getattr(self, "desert_active_ship_data", None), dict):
            default_ship = dict(getattr(self, "desert_active_ship_data") or {})
        class_counts = {key: 0 for key in DEFAULT_CLASSES}
        lineup = list(getattr(self, "desert_ships", []) or [])
        for ship in lineup:
            cls = str(ship.get("class") or "")
            if cls in class_counts:
                class_counts[cls] += 1
        for path in (ROOT_PROGRESS_PATH, SHARED_PROGRESS_PATH):
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                data = {}
                if path.exists():
                    raw = json.loads(path.read_text(encoding="utf-8"))
                    if isinstance(raw, dict):
                        data = raw
                regions = data.setdefault("regions", {})
                desert = regions.setdefault("desert", {})
                desert["ember_hangar"] = {
                    "schema": DESERT_SHIPS_SCHEMA,
                    "mode": "vehicle_showroom",
                    "lineup_count": len(lineup),
                    "class_counts": class_counts,
                    "default_ship_id": default_id,
                    "default_ship_class": str(default_ship.get("class") if default_ship else ""),
                    "default_ship_name": str(default_ship.get("name") if default_ship else ""),
                    "updated_at": datetime.now().isoformat(timespec="seconds"),
                    "state_path": str(STATE_PATH),
                }
                data.setdefault("dimension_progress", {})["ember_hangar"] = desert["ember_hangar"]
                data["updated_at"] = datetime.now().isoformat(timespec="seconds")
                path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
            except Exception as exc:
                print(f"desert_ships_progress_mirror_error:{path}:{exc}")

    def save_desert_ships(self, reason="manual"):
        _ensure_dirs()
        try:
            payload = _state_payload(self)
            STATE_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            self.desert_ships_last_save_at = time.time()
            self.desert_ships_dirty = False
            _mirror_progress(self)
            if reason == "manual":
                self.center_hint["text"] = "EMBER FORGE // ACTIVE VEHICLE SAVED"
            return True
        except Exception as exc:
            print(f"desert_ships_save_error:{exc}")
            self.center_hint["text"] = "EMBER HANGAR // SAVE ERROR"
            return False

    def _set_default_ship(self, ship_id: str, *, announce=True):
        ship_id = str(ship_id or "").strip()
        if not ship_id:
            return False
        found = None
        for idx, ship in enumerate(list(getattr(self, "desert_ships", []) or [])):
            is_match = str(ship.get("id")) == ship_id
            ship["is_default"] = bool(is_match)
            if is_match:
                found = dict(ship)
                self.desert_ships_selected_index = idx
        if found is None:
            return False
        found["is_default"] = True
        found["updated_at"] = datetime.now().isoformat(timespec="seconds")
        self.desert_ships_default_id = ship_id
        self.desert_active_ship_data = dict(found)
        self.shell_flight_craft_data = dict(found)
        self.desert_ships_dirty = True
        save_desert_ships(self, reason="default")
        if announce:
            self.center_hint["text"] = f"EMBER VEHICLE BOUND // {str(found.get('name') or '').upper()} // TAB TO FLY"
        return True

    def _current_default_ship(self):
        if not getattr(self, "desert_ships_loaded", False):
            load_desert_ships(self)
        default_id = str(getattr(self, "desert_ships_default_id", "") or "")
        for ship in list(getattr(self, "desert_ships", []) or []):
            if str(ship.get("id")) == default_id:
                return dict(ship)
        active = getattr(self, "desert_active_ship_data", None)
        if isinstance(active, dict) and active.get("id"):
            return dict(active)
        if list(getattr(self, "desert_ships", []) or []):
            return dict(getattr(self, "desert_ships", [])[0])
        return _default_starter_ship(self)

    def _line(segs, a, b):
        segs.moveTo(float(a[0]), float(a[1]), float(a[2])); segs.drawTo(float(b[0]), float(b[1]), float(b[2]))

    def _circle(segs, radius_x, radius_y, z, points=28):
        last = None
        first = None
        for i in range(points + 1):
            t = (math.pi * 2.0) * (i / float(points))
            p = (math.cos(t) * radius_x, math.sin(t) * radius_y, z)
            if last is not None:
                _line(segs, last, p)
            else:
                first = p
            last = p
        if first is not None and last is not None:
            _line(segs, last, first)

    def _voxel_box_model(self):
        model = getattr(self, "desert_ship_voxel_box_model", None)
        if model is not None and not model.isEmpty():
            return model
        fmt = GeomVertexFormat.getV3()
        vdata = GeomVertexData("desert-voxel-unit-box", fmt, Geom.UHStatic)
        vw = GeomVertexWriter(vdata, "vertex")
        verts = [
            (-0.5, -0.5, -0.5), (0.5, -0.5, -0.5), (0.5, 0.5, -0.5), (-0.5, 0.5, -0.5),
            (-0.5, -0.5, 0.5), (0.5, -0.5, 0.5), (0.5, 0.5, 0.5), (-0.5, 0.5, 0.5),
        ]
        for vx, vy, vz in verts:
            vw.addData3f(vx, vy, vz)
        tris = GeomTriangles(Geom.UHStatic)
        for a, b, c in (
            (0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7),
            (0, 1, 5), (0, 5, 4), (1, 2, 6), (1, 6, 5),
            (2, 3, 7), (2, 7, 6), (3, 0, 4), (3, 4, 7),
        ):
            tris.addVertices(a, b, c)
        geom = Geom(vdata); geom.addPrimitive(tris)
        node = GeomNode("desert-voxel-unit-box"); node.addGeom(geom)
        model = NodePath(node)
        model.setTextureOff(10); model.setLightOff(1); model.setTwoSided(False)
        self.desert_ship_voxel_box_model = model
        return model

    def _add_voxel_box(self, parent, name, pos, scale, color, *, alpha=None, hpr=None, edge=True):
        base = _voxel_box_model(self)
        node = base.copyTo(parent)
        node.setName(str(name))
        node.setPos(pos)
        if hpr is not None:
            node.setHpr(hpr)
        node.setScale(scale)
        rgba = tuple(float(v) for v in color)
        if len(rgba) < 4:
            rgba = (rgba[0], rgba[1], rgba[2], 1.0)
        a = max(0.0, min(1.0, float(rgba[3] if alpha is None else alpha)))
        node.setColorScale(rgba[0], rgba[1], rgba[2], a)
        if a < 0.999:
            node.setTransparency(TransparencyAttrib.MAlpha)
        else:
            node.setTransparency(TransparencyAttrib.MNone)
            node.setDepthWrite(True); node.setDepthTest(True)
        if edge:
            wire = base.copyTo(node)
            wire.setName(f"{name}-wire")
            wire.setScale(1.035)
            wire.setRenderModeWireframe()
            wire.setLightOff(1); wire.setTextureOff(10)
            wire.setColorScale(min(1.8, rgba[0] + 0.42), min(1.8, rgba[1] + 0.34), min(1.8, rgba[2] + 0.30), min(0.92, a + 0.08))
            wire.setTransparency(TransparencyAttrib.MAlpha)
            try:
                wire.setAntialias(AntialiasAttrib.MLine)
            except Exception:
                pass
        return node

    def _ship_heading_hpr(ship):
        try:
            return Vec3(float(ship.get("rotation") or 0.0), 0.0, 0.0)
        except Exception:
            return Vec3(0.0, 0.0, 0.0)

    def _build_ship_node(self, parent, ship, *, selected=False, ghost=False, tab_visual=False):
        entry = _catalog_entry(self, ship.get("class"))
        seed = int(ship.get("seed") or 0)
        rng = random.Random(seed)
        root = parent.attachNewNode(f"desert-ship-{ship.get('id', seed)}")
        col = _safe_rgba(ship.get("color"), entry.get("color", (1, 0.8, 0.2, 0.9)))
        acc = _safe_rgba(ship.get("accent"), entry.get("accent", (1, 1, 1, 0.95)))
        if ghost:
            col = (col[0], col[1], col[2], 0.32)
            acc = (acc[0], acc[1], acc[2], 0.44)
        elif selected:
            col = (min(1.0, col[0] + 0.18), min(1.0, col[1] + 0.18), min(1.0, col[2] + 0.18), 1.0)
        cls = entry["id"]
        alpha = 0.36 if ghost else (1.0 if selected else 0.94)
        # Filled 3D voxel hulls: solid color mass plus vector edges, so the
        # Desert hangar no longer looks like flat wire sketches.
        if cls == "fighter":
            nose = 3.8 + rng.random() * 0.8
            wing = 4.8 + rng.random() * 1.2
            _add_voxel_box(self, root, "fighter-core", Vec3(0, 1.4, 0.25), Vec3(2.2, 7.8, 1.05), col, alpha=alpha, edge=True)
            _add_voxel_box(self, root, "fighter-nose", Vec3(0, 6.2 + nose * 0.10, 0.38), Vec3(1.15, 3.5, 0.78), acc, alpha=alpha, edge=True)
            _add_voxel_box(self, root, "fighter-left-wing", Vec3(-wing * 0.72, 0.4, -0.05), Vec3(wing, 2.0, 0.34), col, alpha=alpha, hpr=Vec3(0, 0, 13), edge=True)
            _add_voxel_box(self, root, "fighter-right-wing", Vec3(wing * 0.72, 0.4, -0.05), Vec3(wing, 2.0, 0.34), col, alpha=alpha, hpr=Vec3(0, 0, -13), edge=True)
            for x in (-1.35, 1.35):
                _add_voxel_box(self, root, "fighter-engine", Vec3(x, -4.35, -0.10), Vec3(0.82, 2.15, 0.72), acc, alpha=alpha, edge=True)
        elif cls == "speeder":
            length = 11.4 + rng.random() * 2.0
            _add_voxel_box(self, root, "speeder-spine", Vec3(0, 0.8, 0.18), Vec3(1.2, length, 0.72), col, alpha=alpha, edge=True)
            _add_voxel_box(self, root, "speeder-cockpit", Vec3(0, 3.35, 0.86), Vec3(1.65, 2.0, 0.88), acc, alpha=alpha, edge=True)
            for x in (-2.05, 2.05):
                _add_voxel_box(self, root, "speeder-side-pod", Vec3(x, -0.75, -0.04), Vec3(0.86, length * 0.68, 0.52), col, alpha=alpha, edge=True)
                _add_voxel_box(self, root, "speeder-fin", Vec3(x * 1.25, -4.4, 0.55), Vec3(0.42, 2.7, 1.2), acc, alpha=alpha, edge=True)
        elif cls == "hauler":
            length = 10.8 + rng.random() * 2.4
            width = 6.6 + rng.random() * 1.4
            _add_voxel_box(self, root, "hauler-cargo-block", Vec3(0, -0.4, 0.18), Vec3(width, length, 1.55), col, alpha=alpha, edge=True)
            _add_voxel_box(self, root, "hauler-cabin", Vec3(0, length * 0.42, 1.12), Vec3(width * 0.56, 2.8, 1.18), acc, alpha=alpha, edge=True)
            for x in (-width * 0.62, width * 0.62):
                _add_voxel_box(self, root, "hauler-engine-pod", Vec3(x, -length * 0.48, -0.05), Vec3(1.28, 2.6, 1.0), acc, alpha=alpha, edge=True)
            for y in (-3.0, 0.0, 3.0):
                _add_voxel_box(self, root, "hauler-cargo-rib", Vec3(0, y, 1.08), Vec3(width * 1.06, 0.42, 0.45), acc, alpha=alpha * 0.92, edge=True)
        else:  # ufo
            _add_voxel_box(self, root, "ufo-center-core", Vec3(0, 0, 0.10), Vec3(5.6, 5.6, 0.88), col, alpha=alpha, edge=True)
            _add_voxel_box(self, root, "ufo-dome", Vec3(0, 0, 1.05), Vec3(3.2, 3.2, 1.18), acc, alpha=alpha, edge=True)
            for idx in range(8):
                t = math.tau * idx / 8.0
                pos = Vec3(math.cos(t) * 4.2, math.sin(t) * 4.2, -0.08)
                _add_voxel_box(self, root, "ufo-ring-block", pos, Vec3(1.5, 1.5, 0.42), col if idx % 2 else acc, alpha=alpha, hpr=Vec3(math.degrees(t), 0, 0), edge=True)
        segs2 = LineSegs(f"ship-accent-{seed}")
        segs2.setThickness(4.0 if selected else 2.2)
        segs2.setColor(*acc)
        if bool(ship.get("is_default")) or selected:
            _circle(segs2, 9.5, 9.5, 0.05, points=36)
            _line(segs2, (0, 0, 1.4), (0, 0, 7.6))
        else:
            _line(segs2, (-1.2, -5.8, -0.4), (-1.2, -7.4, -0.4))
            _line(segs2, (1.2, -5.8, -0.4), (1.2, -7.4, -0.4))
        acc_node = root.attachNewNode(segs2.create())
        try:
            acc_node.setAntialias(AntialiasAttrib.MLine)
            acc_node.setTransparency(TransparencyAttrib.MAlpha)
        except Exception:
            pass
        if not tab_visual:
            pos = ship.get("position") or [0, 0, 5]
            root.setPos(float(pos[0]), float(pos[1]), float(pos[2]))
            root.setHpr(float(ship.get("rotation") or 0.0), 0, 0)
        else:
            root.setScale(0.52)
        root.setPythonTag("desert_ship_3d_voxel", True)
        root.setPythonTag("desert_ship_class", str(cls))
        return root

    def _ensure_root(self):
        root = getattr(self, "desert_ships_root", None)
        if root is None or root.isEmpty():
            parent = getattr(self, "render", None) or getattr(self, "world_root", None)
            if parent is None:
                raise RuntimeError("No render/world root available for Ember Hangar")
            self.desert_ships_root = parent.attachNewNode("ember-hangar-desert-ships-visible")
            self.desert_ships_root.setPythonTag("desert_runtime_visible_root", True)
        return self.desert_ships_root

    def _pad_ring(segs, radius, z, points=64, start_deg=0.0, span=360.0):
        first = None
        last = None
        for i in range(points + 1):
            t = math.radians(float(start_deg) + float(span) * (i / float(points)))
            p = (math.cos(t) * radius, math.sin(t) * radius, z)
            if first is None:
                first = p
                segs.moveTo(*p)
            else:
                segs.drawTo(*p)
            last = p
        if abs(float(span)) >= 359.0 and first is not None and last is not None:
            segs.drawTo(*first)

    def ensure_desert_ship_forge_pad(self):
        root = _ensure_root(self)
        pad = getattr(self, "desert_ship_forge_pad_root", None)
        if pad is not None and not pad.isEmpty():
            return pad
        pad = root.attachNewNode("ember-ship-forge-pad")
        try:
            base = Vec3(getattr(self, "player_pos", Vec3(0, 0, 0)))
            base.z = _floor_z(self, base.x, base.y) + 0.20
        except Exception:
            base = Vec3(0, 0, 0.2)
        pad.setPos(base)
        # A readable in-world forge marker: ring, radial build lanes, and hot
        # amber pylons.  This gives Ember's event an obvious tool space without
        # launching a separate prototype.
        try:
            for name, radius, thick, color, spin in (
                ("outer-ring", 38.0, 4.4, (1.0, 0.36, 0.10, 0.78), 0.0),
                ("mid-ring", 25.0, 3.0, (1.0, 0.74, 0.24, 0.70), 15.0),
                ("core-ring", 10.5, 2.4, (0.30, 1.0, 0.96, 0.52), 30.0),
            ):
                segs = LineSegs(f"ember-forge-{name}")
                segs.setThickness(thick)
                segs.setColor(*color)
                _pad_ring(segs, radius, 0.08, 80, spin, 360.0)
                node = pad.attachNewNode(segs.create())
                node.setTransparency(TransparencyAttrib.MAlpha)
                try:
                    node.setAntialias(AntialiasAttrib.MLine)
                except Exception:
                    pass
            lanes = LineSegs("ember-forge-radial-lanes")
            lanes.setThickness(2.0)
            lanes.setColor(1.0, 0.66, 0.18, 0.50)
            for idx in range(12):
                t = math.tau * idx / 12.0
                lanes.moveTo(math.cos(t) * 7.5, math.sin(t) * 7.5, 0.10)
                lanes.drawTo(math.cos(t) * 38.0, math.sin(t) * 38.0, 0.10)
            lane_node = pad.attachNewNode(lanes.create())
            lane_node.setTransparency(TransparencyAttrib.MAlpha)
            try:
                lane_node.setAntialias(AntialiasAttrib.MLine)
            except Exception:
                pass
            for idx in range(8):
                t = math.tau * idx / 8.0
                p = Vec3(math.cos(t) * 34.5, math.sin(t) * 34.5, 2.9)
                _add_voxel_box(self, pad, "ember-forge-pylon", p, Vec3(1.0, 1.0, 5.6), (1.0, 0.46, 0.10, 0.42), alpha=0.42, edge=True)
        except Exception as exc:
            _log_runtime_error(self, "forge_pad_draw", exc)
        self.desert_ship_forge_pad_root = pad
        return pad

    def update_desert_ship_forge_pad(self, dt=0.0):
        pad = getattr(self, "desert_ship_forge_pad_root", None)
        if pad is None or pad.isEmpty():
            return
        try:
            pad.setH(float(getattr(self, "elapsed", time.monotonic())) * 3.5)
        except Exception:
            pass

    def _clear_nodes(self):
        for node in list(getattr(self, "desert_ship_nodes", []) or []):
            try:
                if node is not None and not node.isEmpty(): node.removeNode()
            except Exception:
                pass
        self.desert_ship_nodes = []

    def redraw_desert_ships(self):
        root = _ensure_root(self)
        _clear_nodes(self)
        selected = int(getattr(self, "desert_ships_selected_index", -1))
        for idx, ship in enumerate(list(getattr(self, "desert_ships", []) or [])):
            node = _build_ship_node(self, root, ship, selected=(idx == selected), ghost=False)
            try:
                node.setPythonTag("ember_forge_vehicle_index", idx)
                node.setPythonTag("ember_forge_vehicle_id", str(ship.get("id") or ""))
            except Exception:
                pass
            self.desert_ship_nodes.append(node)
        update_desert_ships_ui(self)

    def create_desert_ship_ui(self):
        if getattr(self, "desert_ships_ui_root", None) is not None:
            return
        self.desert_ships_ui_root = self.aspect2d.attachNewNode("ember-hangar-ui")
        # Centered compact panel. The old panel was anchored far left, which
        # caused the live EXE view to crop the forge controls offscreen.
        self.desert_ships_ui_panel = DirectFrame(
            parent=self.desert_ships_ui_root,
            frameColor=(0.020, 0.018, 0.026, 0.76),
            frameSize=(-1.18, 1.18, -0.145, 0.145),
            pos=(0.0, 0, -0.80),
        )
        self.desert_ships_ui_title = DirectLabel(
            parent=self.desert_ships_ui_panel, text="EMBER VEHICLE FORGE // DESERT HANGAR", text_align=TextNode.ACenter,
            text_fg=(1.0, 0.78, 0.28, 1), text_shadow=(0, 0, 0, 0.82), frameColor=(0, 0, 0, 0),
            scale=0.039, pos=(0.0, 0, 0.090),
        )
        self.desert_ships_ui_tool = DirectLabel(
            parent=self.desert_ships_ui_panel, text="", text_align=TextNode.ACenter,
            text_fg=(0.78, 1.0, 1.0, 1), text_shadow=(0, 0, 0, 0.78), frameColor=(0, 0, 0, 0),
            scale=0.030, pos=(0.0, 0, 0.022),
        )
        self.desert_ships_ui_help = DirectLabel(
            parent=self.desert_ships_ui_panel, text="", text_align=TextNode.ACenter,
            text_fg=(0.95, 0.96, 1.0, 0.94), text_shadow=(0, 0, 0, 0.82), frameColor=(0, 0, 0, 0),
            scale=0.024, pos=(0.0, 0, -0.068),
        )

    def destroy_desert_ship_ui(self):
        try:
            if getattr(self, "desert_ships_ui_root", None) is not None:
                self.desert_ships_ui_root.removeNode()
        except Exception:
            pass
        self.desert_ships_ui_root = None
        self.desert_ships_ui_panel = None
        self.desert_ships_ui_title = None
        self.desert_ships_ui_tool = None
        self.desert_ships_ui_help = None

    def update_desert_ships_ui(self):
        if not bool(getattr(self, "desert_ships_active", False)):
            return
        create_desert_ship_ui(self)
        selected_idx = int(getattr(self, "desert_ships_selected_index", -1))
        selected = None
        lineup = list(getattr(self, "desert_ships", []) or [])
        if 0 <= selected_idx < len(lineup):
            selected = lineup[selected_idx]
        active = getattr(self, "desert_active_ship_data", None)
        active_name = str((active or {}).get("name") or "none") if isinstance(active, dict) else "none"
        if selected:
            stats = selected.get("stats", {})
            tool = f"SELECTED {selected.get('name')}  //  SPD {stats.get('speed')}  BOOST {stats.get('boost')}  HND {stats.get('handling')}"
        else:
            tool = f"SHOWROOM READY // {len(lineup)}/4 NEW VEHICLE VARIANTS // ACTIVE {active_name}"
        help_text = "AIM + CLICK/E TO PILOT + AUTO-SAVE  |  CLICK YES AGAIN TO REROLL ALL 4  |  TAB RECALLS SAVED VEHICLE  |  ESC CLOSE"
        try:
            self.desert_ships_ui_tool["text"] = tool
            self.desert_ships_ui_help["text"] = help_text
        except Exception:
            pass

    def generate_ember_forge_lineup(self, reason="mission_yes"):
        if not _desert_allowed(self):
            _set_center_hint(self, "EMBER FORGE // ENTER DESERT REGION")
            return False
        try:
            if not getattr(self, "desert_ships_loaded", False):
                load_desert_ships(self)
            self.desert_forge_generation = int(getattr(self, "desert_forge_generation", 0) or 0) + 1
            _ensure_root(self)
            ensure_desert_ship_forge_pad(self)
            _clear_nodes(self)
            self.desert_ships = []
            self.desert_ships_selected_index = -1
            _forward, _right, yaw = _flat_basis_from_view(self)
            for idx, cls in enumerate(DEFAULT_CLASSES):
                pos = _forge_lineup_position(self, idx)
                ship = _new_forge_vehicle(self, cls, slot_index=idx, pos=pos, rotation=yaw)
                ship["is_default"] = False
                self.desert_ships.append(ship)
            self.desert_ships_dirty = False
            redraw_desert_ships(self)
            _set_center_hint(self, "EMBER FORGE // FOUR NEW VEHICLE VARIANTS GENERATED")
            return True
        except Exception as exc:
            _log_runtime_error(self, "generate_ember_forge_lineup", exc, detail=str(reason or "mission_yes"))
            _set_center_hint(self, "EMBER FORGE // LINEUP ERROR // SEE LOG")
            return False

    def _find_forge_vehicle_index_from_view(self):
        lineup = list(getattr(self, "desert_ships", []) or [])
        if not lineup:
            return -1
        try:
            origin = Vec3(getattr(self, "player_pos", Vec3(0, 0, 0)))
            forward, _right, _up = self.get_view_basis()
            forward = Vec3(forward)
            if forward.lengthSquared() <= 0.001:
                forward = Vec3(0, 1, 0)
            forward.normalize()
        except Exception:
            origin = Vec3(0, 0, 0); forward = Vec3(0, 1, 0)
        best_idx = -1
        best_score = 999999.0
        nearest_idx = -1
        nearest_dist = 999999.0
        for idx, ship in enumerate(lineup):
            try:
                p = ship.get("position") or [0, 0, 0]
                target = Vec3(float(p[0]), float(p[1]), float(p[2]) + 1.8)
                vec = target - origin
                dist = max(0.01, vec.length())
                if dist < nearest_dist:
                    nearest_dist = dist; nearest_idx = idx
                axis = vec.dot(forward)
                if axis < -3.0:
                    continue
                lateral = (vec - forward * axis).length()
                cone = max(10.0, min(24.0, dist * 0.26))
                if lateral <= cone and axis <= 150.0:
                    score = lateral + axis * 0.015
                    if score < best_score:
                        best_score = score; best_idx = idx
            except Exception:
                pass
        if best_idx >= 0:
            return best_idx
        if nearest_idx >= 0 and nearest_dist <= 85.0:
            return nearest_idx
        return -1

    def enter_bound_ember_vehicle(self, ship=None):
        ship = dict(ship or _current_default_ship(self))
        self.shell_flight_craft_data = dict(ship)
        if not bool(getattr(self, "shell_flight_craft_active", False)):
            try:
                self.toggle_shell_flight_craft()
            except Exception as exc:
                _log_runtime_error(self, "enter_bound_ember_vehicle", exc)
        else:
            try:
                _ensure_tab_ship_visual(self)
            except Exception:
                pass
        try:
            self.center_hint["text"] = f"PILOTING SAVED EMBER VEHICLE // {str(ship.get('name') or '').upper()} // TAB TO LAND"
        except Exception:
            pass

    def ember_forge_select_vehicle(self, source="click"):
        if not bool(getattr(self, "desert_ships_active", False)):
            return False
        idx = _find_forge_vehicle_index_from_view(self)
        lineup = list(getattr(self, "desert_ships", []) or [])
        if idx < 0 or idx >= len(lineup):
            _set_center_hint(self, "EMBER FORGE // AIM AT A VEHICLE TO PILOT IT")
            return False
        ship = lineup[idx]
        self.desert_ships_selected_index = idx
        if not _set_default_ship(self, str(ship.get("id")), announce=True):
            return False
        redraw_desert_ships(self)
        enter_bound_ember_vehicle(self, ship)
        try:
            self._append_mode_gateway_history("ember_vehicle_bound", label="Ember Hangar", route=IN_WORLD_ROUTE, extra={"source": source, "vehicle": ship.get("name"), "class": ship.get("class")})
        except Exception:
            pass
        return True

    def activate_desert_ships_from_mode(self, mode=None, source="core", route=""):
        try:
            if not _desert_allowed(self):
                _set_center_hint(self, "EMBER FORGE // ENTER DESERT REGION TO CHOOSE A VEHICLE")
                return False
            try:
                if getattr(self, "holoforge_active", False): self.deactivate_holoforge(reason="switch_to_ember_hangar")
                if getattr(self, "forest_growth_active", False): self.deactivate_forest_growth(reason="switch_to_ember_hangar")
                if getattr(self, "hills_life_active", False): self.deactivate_hills_life(reason="switch_to_ember_hangar")
                if getattr(self, "oddities_active", False): self.deactivate_oddities(reason="switch_to_ember_hangar")
                if getattr(self, "frost_circuit_active", False): self.deactivate_frost_circuit(reason="switch_to_ember_hangar")
            except Exception as exc:
                _log_runtime_error(self, "deactivate_other_runtime", exc)
            _ensure_dirs()
            if not getattr(self, "desert_ships_loaded", False):
                load_desert_ships(self)
            self.desert_ships_active = True
            _ensure_root(self)
            ensure_desert_ship_forge_pad(self)
            create_desert_ship_ui(self)
            generate_ember_forge_lineup(self, reason="mission_yes")
            label = str((mode or {}).get("name") or "Ember Hangar")
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
                self._append_mode_gateway_history("ember_forge_showroom_open", mode=mode, label=label, route=IN_WORLD_ROUTE, extra={"source": source, "lineup": len(self.desert_ships), "state": str(STATE_PATH), "forge_pad": True})
            except Exception:
                pass
            return True
        except Exception as exc:
            _log_runtime_error(self, "activate_desert_ships_from_mode", exc, detail=str(source or "core"))
            _set_center_hint(self, "EMBER FORGE // ERROR CAUGHT // SEE logs/ember_hangar_runtime_error.txt")
            return False

    def deactivate_desert_ships(self, reason="closed"):
        if not bool(getattr(self, "desert_ships_active", False)):
            return
        save_desert_ships(self, reason=reason)
        self.desert_ships_active = False
        destroy_desert_ship_ui(self)
        try:
            if getattr(self, "desert_ships_root", None) is not None and not self.desert_ships_root.isEmpty():
                self.desert_ships_root.removeNode()
        except Exception:
            pass
        self.desert_ships_root = None
        self.desert_ship_nodes = []
        self.desert_ship_forge_pad_root = None
        _set_center_hint(self, "EMBER FORGE // CLOSED")
        try:
            self._append_mode_gateway_history("ember_forge_showroom_close", label="Ember Hangar", route=IN_WORLD_ROUTE, extra={"reason": reason, "ships": len(self.desert_ships), "state": str(STATE_PATH)})
        except Exception:
            pass

    def update_desert_ships(self, dt=0.0):
        if not bool(getattr(self, "desert_ships_active", False)):
            return
        if not _desert_allowed(self):
            deactivate_desert_ships(self, reason="left_desert_region")
            return
        update_desert_ship_forge_pad(self, dt)
        if bool(getattr(self, "desert_ships_dirty", False)) and (time.time() - float(getattr(self, "desert_ships_last_save_at", 0.0))) > 16.0:
            save_desert_ships(self, reason="autosave")

    def _destroy_tab_ship_visual(self):
        node = getattr(self, "shell_flight_craft_visual_root", None)
        try:
            if node is not None and not node.isEmpty(): node.removeNode()
        except Exception:
            pass
        self.shell_flight_craft_visual_root = None
        self.shell_flight_craft_visual_signature = ""

    def _ensure_tab_ship_visual(self):
        if not bool(getattr(self, "shell_flight_craft_active", False)):
            _destroy_tab_ship_visual(self); return None
        ship = getattr(self, "shell_flight_craft_data", None) or _current_default_ship(self)
        self.shell_flight_craft_data = dict(ship)
        sig = f"{ship.get('class')}:{ship.get('seed')}:{ship.get('id')}"
        node = getattr(self, "shell_flight_craft_visual_root", None)
        if node is None or node.isEmpty() or sig != getattr(self, "shell_flight_craft_visual_signature", ""):
            _destroy_tab_ship_visual(self)
            self.shell_flight_craft_visual_root = _build_ship_node(self, self.world_root, ship, selected=True, tab_visual=True)
            self.shell_flight_craft_visual_signature = sig
        return self.shell_flight_craft_visual_root

    def update_shell_flight_ship_visual(self, dt=0.0):
        if not bool(getattr(self, "shell_flight_craft_active", False)):
            _destroy_tab_ship_visual(self); return
        node = _ensure_tab_ship_visual(self)
        if node is None or node.isEmpty():
            return
        try:
            forward, right, up = self.get_view_basis()
            if forward.lengthSquared() <= 0.0001: forward = Vec3(0, 1, 0)
            else:
                forward = Vec3(forward); forward.normalize()
            if right.lengthSquared() <= 0.0001: right = Vec3(1, 0, 0)
            else:
                right = Vec3(right); right.normalize()
            # Keep the craft visible as a small wireframe nose/chassis ahead of the camera.
            pos = Vec3(self.player_pos + forward * 8.5 + right * 0.0 + Vec3(0, 0, -1.25))
            node.setPos(pos)
            pitch = max(-38.0, min(38.0, float(getattr(self, "player_pitch", 0.0)))) * 0.22
            roll = 0.0
            try:
                roll = max(-14.0, min(14.0, float(getattr(self, "shell_flight_craft_velocity", Vec3()).dot(right)) * -0.018))
            except Exception:
                pass
            node.setHpr(float(getattr(self, "player_yaw", 0.0)), pitch, roll)
        except Exception as exc:
            print(f"tab_ship_visual_update_error:{exc}")

    def ember_forge_recall_saved_vehicle(self):
        ship = _current_default_ship(self)
        enter_bound_ember_vehicle(self, ship)

    # Public runtime API.
    CommandHubApp.is_desert_ships_mode = _is_desert_ships_mode
    CommandHubApp.activate_desert_ships_from_mode = activate_desert_ships_from_mode
    CommandHubApp.deactivate_desert_ships = deactivate_desert_ships
    CommandHubApp.load_desert_ships = load_desert_ships
    CommandHubApp.save_desert_ships = save_desert_ships
    CommandHubApp.redraw_desert_ships = redraw_desert_ships
    CommandHubApp.update_desert_ships = update_desert_ships
    CommandHubApp.ensure_desert_ship_forge_pad = ensure_desert_ship_forge_pad
    CommandHubApp.update_desert_ship_forge_pad = update_desert_ship_forge_pad
    CommandHubApp.update_desert_ships_ui = update_desert_ships_ui
    CommandHubApp.generate_ember_forge_lineup = generate_ember_forge_lineup
    CommandHubApp.ember_forge_select_vehicle = ember_forge_select_vehicle
    CommandHubApp.enter_bound_ember_vehicle = enter_bound_ember_vehicle
    CommandHubApp.ember_forge_recall_saved_vehicle = ember_forge_recall_saved_vehicle
    CommandHubApp.update_shell_flight_ship_visual = update_shell_flight_ship_visual
    CommandHubApp.current_default_desert_ship = _current_default_ship

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
        if bool(getattr(self, "desert_ships_active", False)):
            self.set_key("e", True)
            self.ember_forge_select_vehicle(source="e")
            return
        return old_e(self)
    CommandHubApp.on_e_down = on_e_down

    old_primary = CommandHubApp.primary_click_interact
    def primary_click_interact(self):
        if bool(getattr(self, "desert_ships_active", False)):
            self.ember_forge_select_vehicle(source="mouse1")
            return
        return old_primary(self)
    CommandHubApp.primary_click_interact = primary_click_interact

    old_start_escape_hold = CommandHubApp.start_escape_hold
    def start_escape_hold(self):
        if bool(getattr(self, "desert_ships_active", False)):
            self.deactivate_desert_ships(reason="escape")
            return
        return old_start_escape_hold(self)
    CommandHubApp.start_escape_hold = start_escape_hold

    # Ember Forge no longer intercepts HoloForge editing controls.
    # Delete/save/snap/rotate/place style controls stay with HoloForge only,
    # preventing old object-editor behavior from leaking into Ember's showroom.

    old_route = CommandHubApp.launch_core_mode_route
    def launch_core_mode_route(self, mode, source="core", extra_env=None, close_core=True):
        if self.is_desert_ships_mode(mode):
            return bool(self.activate_desert_ships_from_mode(mode, source=source, route=IN_WORLD_ROUTE))
        return old_route(self, mode, source=source, extra_env=extra_env, close_core=close_core)
    CommandHubApp.launch_core_mode_route = launch_core_mode_route

    old_can_use = CommandHubApp.can_use_shell_flight_craft_at
    def can_use_shell_flight_craft_at(self, pos=None):
        if bool(getattr(CommandHubApp, "tab_cinematic_flycam_owns_shell_flight", False)):
            return old_can_use(self, pos)
        pos = pos if pos is not None else self.player_pos
        if getattr(self, "active_native_mode", None) is not None or getattr(self, "external_process", None) is not None:
            return False
        if not self.world_shell_playable_active() or self.world_unlocked or self.transition_target > 0.0:
            return False
        try:
            if self.is_holospace_active() or self.is_holospace_traveling():
                return False
        except Exception:
            pass
        try:
            has_saved = getattr(self, "has_saved_shell_flight_craft", None)
            if callable(has_saved) and not bool(has_saved()):
                return False
        except Exception:
            return False
        try:
            r = math.sqrt(float(pos.x) * float(pos.x) + float(pos.y) * float(pos.y))
            return r <= self.world_shell_play_radius_limit()
        except Exception:
            return old_can_use(self, pos)
    CommandHubApp.can_use_shell_flight_craft_at = can_use_shell_flight_craft_at

    old_toggle_craft = CommandHubApp.toggle_shell_flight_craft
    def toggle_shell_flight_craft(self):
        if bool(getattr(CommandHubApp, "tab_cinematic_flycam_owns_shell_flight", False)):
            return old_toggle_craft(self)
        was_active = bool(getattr(self, "shell_flight_craft_active", False))
        if not was_active:
            try:
                has_saved = getattr(self, "has_saved_shell_flight_craft", None)
                if callable(has_saved) and not bool(has_saved()):
                    self.center_hint["text"] = "AIRCRAFT LOCKED // BUILD ONE WITH EMBER"
                    return False
                self.load_desert_ships()
                self.shell_flight_craft_data = self.current_default_desert_ship()
            except Exception:
                self.center_hint["text"] = "AIRCRAFT LOCKED // BUILD ONE WITH EMBER"
                return False
        result = old_toggle_craft(self)
        if was_active:
            _destroy_tab_ship_visual(self)
        elif bool(getattr(self, "shell_flight_craft_active", False)):
            ship = getattr(self, "shell_flight_craft_data", None) or _default_starter_ship(self)
            self.center_hint["text"] = f"TAB CRAFT // {str(ship.get('name') or 'STARTER HOLOCRAFT').upper()} ONLINE"
            _ensure_tab_ship_visual(self)
        return result
    CommandHubApp.toggle_shell_flight_craft = toggle_shell_flight_craft

    old_handle_tab = CommandHubApp.handle_tab_action
    def handle_tab_action(self):
        if bool(getattr(CommandHubApp, "tab_cinematic_flycam_owns_shell_flight", False)):
            return old_handle_tab(self)
        """Keep TAB as aircraft activation without stealing TAB from other modes.

        Ember owns the saved global aircraft, but it must not regress the shared
        HoloVerse input contract.  Native artifact adapters, HoloCore, menus, and
        external/fallback routes keep priority.  Only the default HoloVerse world
        gets the Ember craft toggle.
        """
        if self.core_console_open:
            self.core_toggle_console_page()
            return
        if getattr(self, "active_native_mode", None) is not None:
            self.dispatch_native_action("tab")
            return
        if self.menu_open or getattr(self, "external_process", None) is not None:
            return
        if self.world_unlocked or getattr(self, "transition_target", 0.0) > 0.0:
            try:
                self.center_hint["text"] = "TAB CRAFT // DEFAULT HOLOVERSE ONLY"
            except Exception:
                pass
            return
        if self.is_holospace_active():
            self.center_hint["text"] = "HOLOSPACE // FREE FLIGHT ACTIVE"
            return
        # Ember ships are the global TAB craft; no region-specific lock after a
        # real saved craft exists.  toggle_shell_flight_craft still enforces the
        # saved-craft requirement and shows the player-facing locked prompt.
        self.toggle_shell_flight_craft()
    CommandHubApp.handle_tab_action = handle_tab_action

    old_region_ui = CommandHubApp.update_holoverse_region_ui
    def update_holoverse_region_ui(self):
        result = old_region_ui(self)
        if bool(getattr(self, "desert_ships_active", False)):
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
                self.update_desert_ships(0.0)
                self.update_shell_flight_ship_visual(0.0)
        except Exception as exc:
            print(f"desert_ships_update_error: {exc}")
        return result
    CommandHubApp.update_task = update_task

    setattr(main, "DESERT_SHIPS_RUNTIME_INSTALLED", True)
    setattr(main, "DESERT_SHIPS_STATE_PATH_RUNTIME", STATE_PATH)
