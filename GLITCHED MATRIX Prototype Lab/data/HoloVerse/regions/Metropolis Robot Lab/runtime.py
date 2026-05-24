"""Metropolis Robot Lab in-world runtime for the live METROPOLIS HoloVerse region.

Archivist no longer opens a player construction editor.  Metropolis is now a
clean robot selector: four prebuilt Urban-class frames stand in the live
METROPOLIS region.  Aim at a robot and click or press E to bind it as the
single saved Urban Warzone team ally.  Selecting a new robot replaces the
previous one.  The selected robot loads when the player enters Urban until it
is destroyed or another Metropolis robot is selected.
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
from panda3d.core import TextNode, TransparencyAttrib, Vec3

IN_WORLD_ROUTE = "in_world_region"
METROBOT_SCHEMA = 2
METROPOLIS_REGION_NUMBER = 7
ROBOT_CLASSES = (
    {
        "id": "duelist_standard",
        "label": "Duelist",
        "role": "duelist",
        "variant": "standard",
        "description": "balanced street fighter frame",
        "stats": {"armor": 5, "damage": 5, "speed": 6, "range": 4},
    },
    {
        "id": "crawler_acrobat",
        "label": "Crawler",
        "role": "acrobat",
        "variant": "crawler",
        "description": "low agile runner with extra leg rigs",
        "stats": {"armor": 3, "damage": 4, "speed": 9, "range": 3},
    },
    {
        "id": "shield_survivor",
        "label": "Shield",
        "role": "survivor",
        "variant": "shield",
        "description": "guard frame with riot plating",
        "stats": {"armor": 9, "damage": 3, "speed": 3, "range": 4},
    },
    {
        "id": "assault_breaker",
        "label": "Assault",
        "role": "breaker",
        "variant": "assault",
        "description": "heavy attack frame with back rigs",
        "stats": {"armor": 6, "damage": 8, "speed": 4, "range": 6},
    },
)
PALETTE = (
    ("cyan", (0.16, 0.95, 1.00, 0.94)),
    ("violet", (0.70, 0.36, 1.00, 0.94)),
    ("magenta", (1.00, 0.22, 0.82, 0.94)),
    ("gold", (1.00, 0.76, 0.18, 0.94)),
    ("green", (0.22, 1.00, 0.44, 0.92)),
    ("white", (0.90, 0.98, 1.00, 0.90)),
    ("red", (1.00, 0.20, 0.15, 0.92)),
    ("blue", (0.30, 0.62, 1.00, 0.92)),
)


def _main_module(cls):
    return sys.modules.get(cls.__module__) or sys.modules.get("__main__")


def install_metropolis_robot_lab_runtime(CommandHubApp):
    main = _main_module(CommandHubApp)
    if main is None:
        return

    from holoverse_mode_runtime import install_in_world_route_aliases

    install_in_world_route_aliases(main)

    from holoverse_mode_runtime import resolve_shared_data_root

    ROOT = Path(getattr(main, "ROOT", Path(__file__).resolve().parents[2]))
    SHARED_DATA_ROOT = resolve_shared_data_root(main, ROOT)
    STATE_DIR = SHARED_DATA_ROOT / "holoverse" / "regions" / "metropolis" / "robot_lab"
    BLUEPRINT_PATH = STATE_DIR / "robot_blueprints.json"
    ARENA_EXPORT_PATH = STATE_DIR / "arena_robot_allies.json"

    def _ensure_dirs():
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        (ROOT / "PROOF").mkdir(parents=True, exist_ok=True)

    def _set_hint(self, text: str):
        try:
            self.center_hint["text"] = str(text or "")
        except Exception:
            pass

    def _rgba_tuple(value, default=(0.75, 0.9, 1.0, 0.92)):
        try:
            if isinstance(value, (list, tuple)) and len(value) >= 3:
                r = max(0.0, min(1.0, float(value[0])))
                g = max(0.0, min(1.0, float(value[1])))
                b = max(0.0, min(1.0, float(value[2])))
                a = max(0.0, min(1.0, float(value[3]) if len(value) > 3 else default[3]))
                return (r, g, b, a)
        except Exception:
            pass
        return tuple(default)

    def _brighten(color, amount=1.18, lift=0.04):
        c = _rgba_tuple(color)
        return (min(1.0, c[0] * amount + lift), min(1.0, c[1] * amount + lift), min(1.0, c[2] * amount + lift), c[3])

    def _floor_z(self, x: float, y: float) -> float:
        try:
            return float(self.world_shell_grounded_z(float(x), float(y))) - float(getattr(self.cfg, "player_eye_height", 3.95)) - float(getattr(self.cfg, "terrain_collision_clearance", 0.16))
        except Exception:
            try:
                mount = getattr(self, "world_shell_mount", None)
                runtime = getattr(mount, "source_runtime", None)
                if runtime is not None and hasattr(runtime, "world_height_at"):
                    return float(runtime.world_height_at(float(x), float(y)))
            except Exception:
                pass
        return 0.0

    def _metropolis_allowed(self):
        try:
            return int(self.current_holoverse_region_number()) == METROPOLIS_REGION_NUMBER
        except Exception:
            return True

    def _flat_basis_from_view(self):
        try:
            f, r, _u = self.get_view_basis()
            f = Vec3(float(f.x), float(f.y), 0.0)
            r = Vec3(float(r.x), float(r.y), 0.0)
            if f.lengthSquared() <= 0.001:
                f = Vec3(0, -1, 0)
            if r.lengthSquared() <= 0.001:
                r = Vec3(1, 0, 0)
            f.normalize(); r.normalize()
            yaw = math.degrees(math.atan2(f.x, f.y))
            return f, r, yaw
        except Exception:
            return Vec3(0, -1, 0), Vec3(1, 0, 0), 180.0

    def _lineup_position(self, idx: int):
        f, r, _yaw = _flat_basis_from_view(self)
        base = Vec3(getattr(self, "player_pos", Vec3())) + f * 42.0
        offsets = (-30.0, -10.0, 10.0, 30.0)
        pos = base + r * offsets[int(idx) % len(offsets)]
        pos.z = _floor_z(self, pos.x, pos.y) + 0.6
        return pos

    def _init_state(self):
        self.metrobot_active = False
        self.metrobot_loaded = False
        self.metrobot_root = None
        self.metrobot_lineup_root = None
        self.metrobot_ui_root = None
        self.metrobot_ui_title = None
        self.metrobot_ui_status = None
        self.metrobot_ui_help = None
        self.metrobot_lineup = []
        self.metrobot_robot_nodes_by_id = {}
        self.metrobot_selected_id = ""
        self.metrobot_generation = 0
        self.metrobot_last_save_at = 0.0
        self.metrobot_state_path = BLUEPRINT_PATH
        self.metrobot_arena_export_path = ARENA_EXPORT_PATH
        self.metrobot_arena_export_count = 0
        self.metrobot_arena_export_active_id = ""
        self.metrobot_follow_phase = 0.0

    def _ensure_root(self):
        parent = getattr(self, "render", None) or getattr(self, "root_3d", None)
        if getattr(self, "metrobot_root", None) is None or self.metrobot_root.isEmpty():
            self.metrobot_root = parent.attachNewNode("metropolis-robot-selector-runtime")
            self.metrobot_root.setTransparency(TransparencyAttrib.MAlpha)
        if getattr(self, "metrobot_lineup_root", None) is None or self.metrobot_lineup_root.isEmpty():
            self.metrobot_lineup_root = self.metrobot_root.attachNewNode("metropolis-robot-selector-lineup")
            self.metrobot_lineup_root.setTransparency(TransparencyAttrib.MAlpha)
        return self.metrobot_root

    def _ensure_ui(self):
        if getattr(self, "metrobot_ui_root", None) is not None and not self.metrobot_ui_root.isEmpty():
            return
        self.metrobot_ui_root = self.aspect2d.attachNewNode("metropolis-robot-selector-hud")
        panel = DirectFrame(
            parent=self.metrobot_ui_root,
            frameColor=(0.02, 0.00, 0.05, 0.55),
            frameSize=(0.0, 1.50, -0.42, 0.07),
            pos=(-1.35, 0, 0.44),
            relief=None,
        )
        self.metrobot_ui_title = DirectLabel(
            parent=panel,
            text="METROPOLIS ROBOT SELECTOR",
            text_align=TextNode.ALeft,
            text_scale=0.030,
            text_fg=(0.78, 0.44, 1.00, 0.98),
            frameColor=(0, 0, 0, 0),
            pos=(0.030, 0, 0.020),
            textMayChange=True,
        )
        self.metrobot_ui_status = DirectLabel(
            parent=panel,
            text="",
            text_align=TextNode.ALeft,
            text_scale=0.020,
            text_fg=(1.0, 0.86, 0.30, 0.96),
            frameColor=(0, 0, 0, 0),
            pos=(0.030, 0, -0.075),
            text_wordwrap=75,
            textMayChange=True,
        )
        self.metrobot_ui_help = DirectLabel(
            parent=panel,
            text="",
            text_align=TextNode.ALeft,
            text_scale=0.018,
            text_fg=(0.84, 0.96, 1.0, 0.94),
            frameColor=(0, 0, 0, 0),
            pos=(0.030, 0, -0.205),
            text_wordwrap=82,
            textMayChange=True,
        )
        self.metrobot_ui_root.hide()

    def _palette_pick(rng: random.Random, slot: int):
        base = PALETTE[(slot + rng.randrange(len(PALETTE))) % len(PALETTE)]
        accent = PALETTE[(slot + rng.randrange(len(PALETTE)) + 3) % len(PALETTE)]
        return base, accent

    def _new_robot(self, spec: dict, slot_index: int, pos: Vec3, yaw: float):
        rng_seed = int(time.time() * 1000) + int(getattr(self, "metrobot_generation", 0) or 0) * 1009 + int(slot_index) * 733
        rng = random.Random(rng_seed)
        color_name, color = _palette_pick(rng, slot_index)[0]
        accent_name, accent = _palette_pick(rng, slot_index + 11)[1]
        scale = round(rng.uniform(0.92, 1.18), 3)
        shoulder = round(rng.uniform(0.88, 1.28), 3)
        core = round(rng.uniform(0.88, 1.22), 3)
        weapon = round(rng.uniform(0.90, 1.35), 3)
        rid = f"metro_{spec['id']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{slot_index}_{rng.randrange(1000,9999)}"
        return {
            "schema": METROBOT_SCHEMA,
            "id": rid,
            "name": f"{spec['label']} {color_name.upper()}-{rng.randrange(10,99)}",
            "source_dimension": "Metropolis Robot Lab",
            "purpose": "urban_warzone_single_helper_ally",
            "class_id": spec["id"],
            "class_label": spec["label"],
            "role": spec["role"],
            "variant": spec["variant"],
            "description": spec.get("description", "metropolis ally frame"),
            "color_name": color_name,
            "accent_name": accent_name,
            "color": list(color),
            "accent": list(accent),
            "appearance": {"scale": scale, "shoulder": shoulder, "core": core, "weapon": weapon, "visor": rng.choice(["thin", "wide", "split"]), "antenna": bool(rng.randrange(2))},
            "stats": dict(spec.get("stats") or {}),
            "position": [round(float(pos.x), 3), round(float(pos.y), 3), round(float(pos.z), 3)],
            "rotation": round(float(yaw), 3),
            "alive": True,
            "destroyed": False,
            "requires_replacement_if_destroyed": True,
            "part_count": 1,
            "urban_actor_template": {"kind": "ally", "role": spec["role"], "variant": spec["variant"], "color": list(color), "accent": list(accent)},
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }

    def _current_bound_robot(self):
        selected = str(getattr(self, "metrobot_selected_id", "") or "")
        if selected:
            for robot in list(getattr(self, "metrobot_lineup", []) or []):
                if str(robot.get("id")) == selected:
                    return robot
        try:
            if ARENA_EXPORT_PATH.exists():
                data = json.loads(ARENA_EXPORT_PATH.read_text(encoding="utf-8"))
                active = data.get("active_ally") if isinstance(data, dict) else None
                if isinstance(active, dict) and not bool(active.get("destroyed", False)):
                    return active
        except Exception:
            pass
        return None

    def _save_state(self, *, reason="save"):
        _ensure_dirs()
        lineup = [dict(r) for r in list(getattr(self, "metrobot_lineup", []) or []) if isinstance(r, dict)]
        selected = _current_bound_robot(self)
        active_alive = isinstance(selected, dict) and not bool(selected.get("destroyed", False)) and bool(selected.get("alive", True))
        now = datetime.now().isoformat(timespec="seconds")
        library_payload = {
            "schema": METROBOT_SCHEMA,
            "tool": "Metropolis Robot Selector",
            "dimension": "metropolis_robot_lab",
            "save_authority": "shared_data_holoverse_region_layer",
            "mode": "single_ally_selector",
            "lineup": lineup,
            "active_ally": dict(selected) if isinstance(selected, dict) else None,
            "active_ally_id": str((selected or {}).get("id") or "") if isinstance(selected, dict) else "",
            "urban_rule": "single selected robot joins Urban Warzone; death clears the export and requires a new Metropolis selection",
            "updated_at": now,
            "reason": str(reason or "save"),
        }
        export_payload = {
            "schema": METROBOT_SCHEMA,
            "tool": "Metropolis Robot Selector",
            "dimension": "metropolis_robot_lab",
            "mode": "single_ally_selector",
            "active_ally": dict(selected) if active_alive else None,
            "active_ally_id": str((selected or {}).get("id") or "") if active_alive and isinstance(selected, dict) else "",
            "arena_allies": [dict(selected)] if active_alive and isinstance(selected, dict) else [],
            "requires_new_selection": not active_alive,
            "death_rule": "If this ally dies in Urban Warzone, return to Archivist and bind a new robot.",
            "updated_at": now,
            "reason": str(reason or "save"),
        }
        BLUEPRINT_PATH.write_text(json.dumps(library_payload, indent=2) + "\n", encoding="utf-8")
        ARENA_EXPORT_PATH.write_text(json.dumps(export_payload, indent=2) + "\n", encoding="utf-8")
        self.metrobot_arena_export_count = len(export_payload.get("arena_allies", []) or [])
        self.metrobot_arena_export_active_id = str(export_payload.get("active_ally_id") or "")
        self.metrobot_last_save_at = time.monotonic()
        return export_payload

    def _load_state(self):
        if bool(getattr(self, "metrobot_loaded", False)):
            return
        _ensure_dirs()
        self.metrobot_lineup = []
        self.metrobot_selected_id = ""
        try:
            if BLUEPRINT_PATH.exists():
                data = json.loads(BLUEPRINT_PATH.read_text(encoding="utf-8"))
                if isinstance(data, dict) and int(data.get("schema", 0) or 0) >= 2:
                    self.metrobot_lineup = [dict(r) for r in list(data.get("lineup", []) or []) if isinstance(r, dict)]
                    self.metrobot_selected_id = str(data.get("active_ally_id") or "")
        except Exception as exc:
            print(f"metrobot_selector_load_warning:{exc}")
        try:
            if ARENA_EXPORT_PATH.exists():
                data = json.loads(ARENA_EXPORT_PATH.read_text(encoding="utf-8"))
                active = data.get("active_ally") if isinstance(data, dict) else None
                if isinstance(data, dict):
                    self.metrobot_arena_export_count = len(list(data.get("arena_allies", []) or []))
                    self.metrobot_arena_export_active_id = str(data.get("active_ally_id") or "")
                requires_new = bool(data.get("requires_new_selection", False)) if isinstance(data, dict) else False
                if isinstance(active, dict) and (requires_new or bool(active.get("destroyed", False)) or not bool(active.get("alive", True))):
                    dead_id = str(active.get("id") or data.get("active_ally_id") or "")
                    for robot in self.metrobot_lineup:
                        if dead_id and str(robot.get("id")) == dead_id:
                            robot["alive"] = False
                            robot["destroyed"] = True
                    if dead_id and self.metrobot_selected_id == dead_id:
                        self.metrobot_selected_id = ""
                elif isinstance(active, dict):
                    self.metrobot_selected_id = str(active.get("id") or self.metrobot_selected_id)
                    if self.metrobot_selected_id and not any(str(r.get("id")) == self.metrobot_selected_id for r in self.metrobot_lineup):
                        self.metrobot_lineup.append(dict(active))
        except Exception as exc:
            print(f"metrobot_selector_export_load_warning:{exc}")
        self.metrobot_loaded = True

    def _draw_ring(self, parent, radius: float, z: float, color, name="metrobot-ring", thickness=0.22):
        try:
            pts = [Vec3(math.cos(math.tau * i / 40.0) * radius, math.sin(math.tau * i / 40.0) * radius, z) for i in range(41)]
            self.add_polyline(parent, pts, color, max(1.0, getattr(self.cfg, "line_thickness", 1.6) * thickness), False, name)
        except Exception:
            pass

    def _box(self, parent, name, center, size, color, alpha=0.50):
        try:
            node = self.add_box(parent, Vec3(center), Vec3(size), color, alpha)
            try:
                node.setName(str(name))
            except Exception:
                pass
            return node
        except Exception:
            return None

    def _draw_robot_model(self, parent, robot: dict, *, selected=False, following=False):
        color = _rgba_tuple(robot.get("color"))
        accent = _rgba_tuple(robot.get("accent"), _brighten(color, 1.25, 0.06))
        variant = str(robot.get("variant") or "standard")
        role = str(robot.get("role") or "duelist")
        app = robot.get("appearance") if isinstance(robot.get("appearance"), dict) else {}
        scale = max(0.72, min(1.38, float(app.get("scale", 1.0) or 1.0)))
        shoulder = max(0.75, min(1.45, float(app.get("shoulder", 1.0) or 1.0)))
        core = max(0.75, min(1.35, float(app.get("core", 1.0) or 1.0)))
        weapon = max(0.75, min(1.55, float(app.get("weapon", 1.0) or 1.0)))
        glow = _brighten(accent, 1.10 if selected else 0.98, 0.02)
        base_alpha = 0.62 if selected else 0.48
        if following:
            base_alpha = 0.72
        _draw_ring(self, parent, 7.0 * scale, -2.20 * scale, glow if selected else color, name="metrobot-bound-ring" if selected else "metrobot-class-ring", thickness=0.24 if selected else 0.16)
        _box(self, parent, f"{role}-{variant}-pelvis", Vec3(0, 0, 1.55 * scale), Vec3(3.7 * scale, 2.9 * scale, 1.15 * scale), color, base_alpha)
        _box(self, parent, f"{role}-{variant}-torso", Vec3(0, 0, 4.15 * scale), Vec3(4.5 * shoulder * scale, 3.0 * scale, 4.4 * core * scale), color, base_alpha + 0.10)
        _box(self, parent, f"{role}-{variant}-head", Vec3(0, -0.15 * scale, 7.35 * scale), Vec3(2.25 * scale, 1.75 * scale, 1.55 * scale), color, base_alpha + 0.16)
        visor_w = 1.95 if str(app.get("visor")) != "thin" else 1.35
        if str(app.get("visor")) == "split":
            _box(self, parent, "split-visor-left", Vec3(-0.55 * scale, -1.06 * scale, 7.56 * scale), Vec3(0.70 * scale, 0.20 * scale, 0.32 * scale), glow, 0.90)
            _box(self, parent, "split-visor-right", Vec3(0.55 * scale, -1.06 * scale, 7.56 * scale), Vec3(0.70 * scale, 0.20 * scale, 0.32 * scale), glow, 0.90)
        else:
            _box(self, parent, "visor", Vec3(0, -1.06 * scale, 7.56 * scale), Vec3(visor_w * scale, 0.20 * scale, 0.34 * scale), glow, 0.90)
        for side in (-1, 1):
            _box(self, parent, f"shoulder-{side}", Vec3(side * 3.10 * shoulder * scale, 0, 5.0 * scale), Vec3(0.92 * scale, 2.3 * scale, 1.15 * scale), color, base_alpha)
            _box(self, parent, f"forearm-{side}", Vec3(side * 3.85 * shoulder * scale, -0.08 * scale, 3.15 * scale), Vec3(0.72 * scale, 1.62 * scale, 1.95 * scale), color, base_alpha)
            _box(self, parent, f"thigh-{side}", Vec3(side * 1.05 * scale, 0, 0.18 * scale), Vec3(0.90 * scale, 1.55 * scale, 2.25 * scale), color, base_alpha)
            _box(self, parent, f"shin-{side}", Vec3(side * 1.35 * scale, 0, -1.92 * scale), Vec3(0.72 * scale, 1.35 * scale, 2.00 * scale), color, base_alpha)
            _box(self, parent, f"foot-{side}", Vec3(side * 1.55 * scale, -0.22 * scale, -3.05 * scale), Vec3(1.36 * scale, 2.40 * scale, 0.42 * scale), color, base_alpha - 0.08)
        if variant == "shield":
            _box(self, parent, "ally-shield-riot-plate", Vec3(0, -3.05 * scale, 3.60 * scale), Vec3(6.0 * scale, 0.40 * scale, 4.6 * scale), accent, 0.46)
        elif variant == "crawler":
            for side in (-1, 1):
                for off in (-1.0, 1.0):
                    _box(self, parent, f"crawler-extra-leg-{side}-{off}", Vec3(side * 4.2 * scale, off * 1.8 * scale, 0.12 * scale), Vec3(2.65 * scale, 0.38 * scale, 0.56 * scale), color, 0.48)
            _box(self, parent, "crawler-low-spine", Vec3(0, 1.75 * scale, 2.15 * scale), Vec3(5.2 * scale, 0.52 * scale, 0.86 * scale), accent, 0.54)
        elif variant == "assault":
            for side in (-1, 1):
                _box(self, parent, f"assault-back-rig-{side}", Vec3(side * 1.45 * scale, 2.35 * scale, 6.3 * scale), Vec3(0.86 * scale, 0.86 * scale, 3.2 * scale), accent, 0.56)
            _box(self, parent, "assault-cannon", Vec3(2.85 * scale, -3.25 * scale, 3.65 * scale), Vec3(0.52 * scale, 4.0 * weapon * scale, 0.52 * scale), accent, 0.72)
        else:
            _box(self, parent, "standard-rifle", Vec3(2.70 * scale, -2.95 * scale, 3.50 * scale), Vec3(0.48 * scale, 3.2 * weapon * scale, 0.48 * scale), accent, 0.66)
        if bool(app.get("antenna")):
            try:
                self.add_polyline(parent, [Vec3(0.85 * scale, 0.10 * scale, 8.2 * scale), Vec3(1.6 * scale, 0.25 * scale, 10.4 * scale)], glow, max(1.0, getattr(self.cfg, "line_thickness", 1.6) * 0.14), False, "metrobot-antenna")
            except Exception:
                pass
        if selected:
            _draw_ring(self, parent, 4.8 * scale, 9.2 * scale, glow, name="metrobot-selected-crown", thickness=0.20)

    def _clear_lineup_nodes(self):
        try:
            if getattr(self, "metrobot_lineup_root", None) is not None and not self.metrobot_lineup_root.isEmpty():
                self.metrobot_lineup_root.removeNode()
        except Exception:
            pass
        self.metrobot_lineup_root = None
        self.metrobot_robot_nodes_by_id = {}
        _ensure_root(self)

    def redraw_metropolis_robot_lineup(self):
        _ensure_root(self)
        _clear_lineup_nodes(self)
        self.metrobot_lineup_root = self.metrobot_root.attachNewNode("metropolis-robot-selector-lineup")
        self.metrobot_lineup_root.setTransparency(TransparencyAttrib.MAlpha)
        self.metrobot_robot_nodes_by_id = {}
        for idx, robot in enumerate(list(getattr(self, "metrobot_lineup", []) or [])):
            try:
                p = robot.get("position") or [0, 0, 0]
                holder = self.metrobot_lineup_root.attachNewNode(f"metrobot-selector-{idx}-{robot.get('class_id','robot')}")
                holder.setTransparency(TransparencyAttrib.MAlpha)
                holder.setPos(float(p[0]), float(p[1]), float(p[2]))
                holder.setH(float(robot.get("rotation", 0.0) or 0.0))
                holder.setPythonTag("metropolis_robot_id", str(robot.get("id") or ""))
                selected = str(robot.get("id")) == str(getattr(self, "metrobot_selected_id", "") or "")
                _draw_robot_model(self, holder, robot, selected=selected, following=selected)
                self.metrobot_robot_nodes_by_id[str(robot.get("id") or idx)] = holder
            except Exception as exc:
                print(f"metrobot_redraw_robot_warning:{exc}")
        update_metropolis_robot_lab_ui(self)

    def update_metropolis_robot_lab_ui(self):
        if getattr(self, "metrobot_ui_status", None) is None:
            return
        lineup = list(getattr(self, "metrobot_lineup", []) or [])
        active = _current_bound_robot(self)
        if isinstance(active, dict) and not bool(active.get("destroyed", False)):
            stats = active.get("stats", {}) if isinstance(active.get("stats"), dict) else {}
            status = f"BOUND ALLY: {active.get('name')} // {active.get('class_label')}  ARM {stats.get('armor','-')} DMG {stats.get('damage','-')} SPD {stats.get('speed','-')}"
        else:
            status = f"NO URBAN ALLY BOUND // {len(lineup)}/4 CLASS VARIANTS READY"
        help_text = "AIM + CLICK/E SELECTS ONE PREBUILT ROBOT. SELECTING ANOTHER REPLACES THE URBAN ALLY. IT LOADS IN URBAN UNTIL DESTROYED."
        try:
            self.metrobot_ui_status["text"] = status
            self.metrobot_ui_help["text"] = help_text
        except Exception:
            pass

    def generate_metropolis_robot_lineup(self, reason="mission_yes"):
        if not _metropolis_allowed(self):
            try:
                self.travel_to_holoverse_region_index(METROPOLIS_REGION_NUMBER)
            except Exception:
                pass
        try:
            if not getattr(self, "metrobot_loaded", False):
                _load_state(self)
            self.metrobot_generation = int(getattr(self, "metrobot_generation", 0) or 0) + 1
            _ensure_root(self)
            self.metrobot_lineup = []
            f, _r, yaw = _flat_basis_from_view(self)
            for idx, spec in enumerate(ROBOT_CLASSES):
                pos = _lineup_position(self, idx)
                robot = _new_robot(self, spec, idx, pos, yaw)
                self.metrobot_lineup.append(robot)
            redraw_metropolis_robot_lineup(self)
            _save_state(self, reason=f"lineup_{reason}")
            _set_hint(self, "METROPOLIS ROBOT SELECTOR // FOUR PREBUILT ROBOT CLASSES READY")
            return True
        except Exception as exc:
            print(f"metrobot_generate_lineup_warning:{exc}")
            _set_hint(self, "METROPOLIS ROBOT SELECTOR // LINEUP ERROR")
            return False

    def _find_robot_index_from_view(self):
        lineup = list(getattr(self, "metrobot_lineup", []) or [])
        if not lineup:
            return -1
        try:
            origin = Vec3(getattr(self, "player_pos", Vec3(0, 0, 0)))
            forward, _right, _up = self.get_view_basis()
            forward = Vec3(forward)
            if forward.lengthSquared() <= 0.001:
                forward = Vec3(0, -1, 0)
            forward.normalize()
        except Exception:
            origin = Vec3(0, 0, 0); forward = Vec3(0, -1, 0)
        best_idx = -1
        best_score = 999999.0
        nearest_idx = -1
        nearest_dist = 999999.0
        for idx, robot in enumerate(lineup):
            try:
                p = robot.get("position") or [0, 0, 0]
                target = Vec3(float(p[0]), float(p[1]), float(p[2]) + 4.8)
                vec = target - origin
                dist = max(0.01, vec.length())
                if dist < nearest_dist:
                    nearest_dist = dist; nearest_idx = idx
                axis = vec.dot(forward)
                if axis < -3.0:
                    continue
                lateral = (vec - forward * axis).length()
                cone = max(12.0, min(28.0, dist * 0.30))
                if lateral <= cone and axis <= 165.0:
                    score = lateral + axis * 0.012
                    if score < best_score:
                        best_score = score; best_idx = idx
            except Exception:
                pass
        if best_idx >= 0:
            return best_idx
        if nearest_idx >= 0 and nearest_dist <= 90.0:
            return nearest_idx
        return -1

    def bind_metropolis_robot_ally(self, source="click", force_index=None):
        if not bool(getattr(self, "metrobot_active", False)) and force_index is None:
            return False
        lineup = list(getattr(self, "metrobot_lineup", []) or [])
        if not lineup:
            generate_metropolis_robot_lineup(self, reason="empty_bind")
            lineup = list(getattr(self, "metrobot_lineup", []) or [])
        idx = int(force_index) if force_index is not None else _find_robot_index_from_view(self)
        if idx < 0 or idx >= len(lineup):
            _set_hint(self, "METROPOLIS ROBOT SELECTOR // AIM AT A ROBOT TO BIND IT")
            return False
        robot = dict(lineup[idx])
        robot["alive"] = True
        robot["destroyed"] = False
        robot["bound_at"] = datetime.now().isoformat(timespec="seconds")
        lineup[idx] = robot
        self.metrobot_lineup = lineup
        self.metrobot_selected_id = str(robot.get("id") or "")
        payload = _save_state(self, reason=f"bind_{source}")
        redraw_metropolis_robot_lineup(self)
        _set_hint(self, f"METROPOLIS ROBOT SELECTOR // {str(robot.get('name') or 'ROBOT').upper()} SELECTED FOR URBAN")
        try:
            self._append_mode_gateway_history("metropolis_robot_ally_bound", label="Metropolis Robot Lab", route=IN_WORLD_ROUTE, extra={"source": source, "robot": robot.get("name"), "class": robot.get("class_label"), "export": str(ARENA_EXPORT_PATH), "arena_allies": len(payload.get("arena_allies", []))})
        except Exception:
            pass
        return True

    def _update_following_robot(self, dt: float):
        active = _current_bound_robot(self)
        if not isinstance(active, dict):
            return
        rid = str(active.get("id") or "")
        node = dict(getattr(self, "metrobot_robot_nodes_by_id", {}) or {}).get(rid)
        if node is None or node.isEmpty():
            return
        try:
            f, r, yaw = _flat_basis_from_view(self)
            p = Vec3(getattr(self, "player_pos", Vec3())) - f * 10.0 + r * 6.0
            p.z = _floor_z(self, p.x, p.y) + 0.8 + math.sin(time.monotonic() * 4.0) * 0.16
            node.setPos(p)
            node.setH(yaw + math.sin(time.monotonic() * 2.2) * 6.0)
            active["position"] = [round(float(p.x), 3), round(float(p.y), 3), round(float(p.z), 3)]
        except Exception:
            pass

    def activate_metropolis_robot_lab_from_mode(self, mode=None, source="core", route=""):
        if not _metropolis_allowed(self):
            try:
                self.travel_to_holoverse_region_index(METROPOLIS_REGION_NUMBER)
            except Exception:
                pass
        _ensure_dirs(); _ensure_root(self); _ensure_ui(self); _load_state(self)
        self.metrobot_active = True
        self.metrobot_root.show(); self.metrobot_ui_root.show()
        if not getattr(self, "metrobot_lineup", []):
            generate_metropolis_robot_lineup(self, reason=str(source or "open"))
        else:
            redraw_metropolis_robot_lineup(self)
        try:
            if getattr(self, "bot_dialogue_open", False):
                self.close_bot_dimension_dialogue("launching")
        except Exception:
            pass
        try:
            self.close_core_console()
        except Exception:
            pass
        self.mouse_captured = True
        label = str((mode or {}).get("name") or "Metropolis Robot Lab")
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
            self.record_matrixcore_dimension_signal("dimension_launch", label, label=label, route=IN_WORLD_ROUTE, source=str(source or "core"), reason="metropolis_robot_selector_runtime")
            self.record_matrixcore_bot_signal("bot_launch", "Archivist", "METROPOLIS", label, route=IN_WORLD_ROUTE, source="metropolis_robot_selector_runtime")
            self._append_mode_gateway_history("metropolis_robot_selector_open", mode=mode, label=label, route=IN_WORLD_ROUTE, extra={"source": source, "state": str(BLUEPRINT_PATH), "export": str(ARENA_EXPORT_PATH), "lineup": len(getattr(self, "metrobot_lineup", []) or [])})
        except Exception:
            pass
        _set_hint(self, "METROPOLIS ROBOT SELECTOR // AIM + CLICK/E TO SELECT ONE ROBOT FOR URBAN")
        update_metropolis_robot_lab_ui(self)
        return True

    def deactivate_metropolis_robot_lab(self, reason="close"):
        if not bool(getattr(self, "metrobot_active", False)):
            return False
        try:
            _save_state(self, reason=f"close_{reason}")
        except Exception:
            pass
        self.metrobot_active = False
        for attr in ("metrobot_root", "metrobot_ui_root"):
            try:
                node = getattr(self, attr, None)
                if node is not None and not node.isEmpty():
                    node.hide()
            except Exception:
                pass
        _set_hint(self, f"METROPOLIS ROBOT SELECTOR // CLOSED // {str(reason).upper()}")
        return True

    def update_metropolis_robot_lab(self, dt: float = 0.0):
        if not bool(getattr(self, "metrobot_active", False)):
            return
        if not _metropolis_allowed(self):
            deactivate_metropolis_robot_lab(self, reason="left_metropolis")
            return
        _update_following_robot(self, float(dt or 0.016))
        update_metropolis_robot_lab_ui(self)

    # Lightweight compatibility/proof APIs. These are showroom actions only,
    # not the removed placement editor controls.
    def metrobot_generate_lineup(self, reason="manual"):
        return generate_metropolis_robot_lineup(self, reason=reason)

    def metrobot_bind_index(self, index=0, source="proof"):
        return bind_metropolis_robot_ally(self, source=source, force_index=int(index))

    old_update_task = getattr(CommandHubApp, "update_task", None)
    def update_task_with_metrobot(self, task):
        result = old_update_task(self, task) if callable(old_update_task) else task.cont
        try:
            update_metropolis_robot_lab(self, min(0.033, getattr(getattr(main, "globalClock", None), "getDt", lambda: 0.016)()))
        except Exception as exc:
            print(f"metrobot_selector_update_warning:{exc}")
        return result
    if callable(old_update_task) and not getattr(CommandHubApp, "_metrobot_update_patched", False):
        CommandHubApp.update_task = update_task_with_metrobot
        CommandHubApp._metrobot_update_patched = True

    old_init = getattr(CommandHubApp, "__init__", None)
    def __init_with_metrobot__(self, *args, **kwargs):
        old_init(self, *args, **kwargs)
        try:
            _init_state(self)
        except Exception as exc:
            print(f"metrobot_selector_init_warning:{exc}")
    if callable(old_init) and not getattr(CommandHubApp, "_metrobot_init_patched", False):
        CommandHubApp.__init__ = __init_with_metrobot__
        CommandHubApp._metrobot_init_patched = True

    old_e = getattr(CommandHubApp, "on_e_down", None)
    def on_e_down_with_metrobot(self):
        if bool(getattr(self, "metrobot_active", False)):
            try:
                self.set_key("e", True)
            except Exception:
                pass
            bind_metropolis_robot_ally(self, source="e")
            return
        if callable(old_e):
            return old_e(self)
    if callable(old_e) and not getattr(CommandHubApp, "_metrobot_e_patched", False):
        CommandHubApp.on_e_down = on_e_down_with_metrobot
        CommandHubApp._metrobot_e_patched = True

    old_primary = getattr(CommandHubApp, "primary_click_interact", None)
    def primary_click_interact_with_metrobot(self):
        if bool(getattr(self, "metrobot_active", False)):
            bind_metropolis_robot_ally(self, source="mouse1")
            return
        if callable(old_primary):
            return old_primary(self)
    if callable(old_primary) and not getattr(CommandHubApp, "_metrobot_primary_patched", False):
        CommandHubApp.primary_click_interact = primary_click_interact_with_metrobot
        CommandHubApp._metrobot_primary_patched = True

    old_start_escape_hold = getattr(CommandHubApp, "start_escape_hold", None)
    def start_escape_hold_with_metrobot(self):
        if bool(getattr(self, "metrobot_active", False)):
            deactivate_metropolis_robot_lab(self, reason="escape")
            return
        if callable(old_start_escape_hold):
            return old_start_escape_hold(self)
    if callable(old_start_escape_hold) and not getattr(CommandHubApp, "_metrobot_escape_patched", False):
        CommandHubApp.start_escape_hold = start_escape_hold_with_metrobot
        CommandHubApp._metrobot_escape_patched = True

    CommandHubApp.activate_metropolis_robot_lab_from_mode = activate_metropolis_robot_lab_from_mode
    CommandHubApp.deactivate_metropolis_robot_lab = deactivate_metropolis_robot_lab
    CommandHubApp.update_metropolis_robot_lab = update_metropolis_robot_lab
    CommandHubApp.generate_metropolis_robot_lineup = generate_metropolis_robot_lineup
    CommandHubApp.redraw_metropolis_robot_lineup = redraw_metropolis_robot_lineup
    CommandHubApp.update_metropolis_robot_lab_ui = update_metropolis_robot_lab_ui
    CommandHubApp.bind_metropolis_robot_ally = bind_metropolis_robot_ally
    CommandHubApp.current_bound_metropolis_robot = _current_bound_robot
    CommandHubApp.metrobot_generate_lineup = metrobot_generate_lineup
    CommandHubApp.metrobot_bind_index = metrobot_bind_index
    setattr(main, "METROPOLIS_ROBOT_LAB_BLUEPRINT_PATH", BLUEPRINT_PATH)
    setattr(main, "METROPOLIS_ROBOT_LAB_ARENA_EXPORT_PATH", ARENA_EXPORT_PATH)
