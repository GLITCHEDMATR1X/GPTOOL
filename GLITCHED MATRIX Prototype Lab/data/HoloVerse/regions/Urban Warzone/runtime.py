"""Urban Warzone in-world runtime for the live URBAN HoloVerse region.

Sable turns Urban into the built-in arena/combat simulator.  This runtime does
not launch the old legacy arena as a second app; it salvages the arena systems
into the current URBAN region: distributed arena pockets, role silhouettes,
cover/collision blocks, bot allies, robots, mechs, drones, and clean unload on
ESC/TAB/teleport or region exit.
"""
from __future__ import annotations

import importlib.util
import json
import math
import random
import sys
import time
from datetime import datetime
from pathlib import Path

from direct.gui.DirectGui import DirectFrame, DirectLabel
from panda3d.core import (
    AntialiasAttrib, Geom, GeomNode, GeomTriangles, GeomVertexData,
    GeomVertexFormat, GeomVertexWriter, LineSegs, TextNode,
    TransparencyAttrib, Vec3,
)

IN_WORLD_ROUTE = "in_world_region"
URBAN_WARZONE_SCHEMA = 6
URBAN_REGION_NUMBER = 6
ROUTE_TRUTH_MARKER = "URBAN WARZONE WORLD ROUTE ACTIVE"
ROUTE_TRUTH_OWNER = "Dimensions/Urban Warzone/runtime.py mounted into live HoloVerse Urban region"
# Urban endgame combat deploys the eight battle bots except IO.
# IO stays the neutral Flat/HoloForge guide instead of becoming a combat pet.
# Sable is special: the real named Urban bot is reused as the battle commander
# with mounted beams.  The runtime must not spawn a second Sable actor.
BOT_ALLIES = ("Sable", "Vanta", "Nyx", "Solace", "Ember", "Mirror", "Archivist", "Orbit")
SABLE_BATTLE_OWNER = "Sable"
BATTLE_REINFORCEMENT_BOTS = tuple(bot for bot in BOT_ALLIES if bot != SABLE_BATTLE_OWNER)
# The former standalone arena is now a buried activity layer inside the live
# Urban terrain. The Urban biome still renders the city; this layer sits just
# below it so the old arena reads as embedded infrastructure instead of a new
# debug world stapled in front of the player.
# Keep the salvaged arena as a visible underlay: just under the Urban floor,
# not a full meter below where it reads like a faint debug trace.
ARENA_LAYER_DEPTH = 0.22
ARENA_STRUCTURE_SINK_RATIO = 0.36
# Existing HoloVerse friend bots are the only allied faction in Urban Warzone.
# They can be called in as arena support instead of creating random good-guy units.
STARTER_ALLY_COUNT = len(BATTLE_REINFORCEMENT_BOTS)
MAX_ALLIES = len(BOT_ALLIES)
DIFFICULTY_PROFILES = {
    "RECRUIT": {"enemy_scale": 0.85, "hp_scale": 0.85, "damage_scale": 0.80, "score_scale": 0.90},
    "STANDARD": {"enemy_scale": 1.00, "hp_scale": 1.00, "damage_scale": 1.00, "score_scale": 1.00},
    "HARD": {"enemy_scale": 1.18, "hp_scale": 1.15, "damage_scale": 1.12, "score_scale": 1.20},
    "NIGHTMARE": {"enemy_scale": 1.38, "hp_scale": 1.34, "damage_scale": 1.25, "score_scale": 1.45},
}
CHALLENGE_TITLES = {
    "frontline": "Frontline Push",
    "capture_lock": "Capture Lockdown",
    "bomb_run": "Bomb Run",
    "hunter_pack": "Hunter Pack",
    "drone_storm": "Drone Storm",
    "mech_pressure": "Mech Pressure",
    "colossus": "Colossus Warning",
}
ENEMY_POINT_VALUES = {"robot": 100, "drone": 150, "mech": 550}
BOT_ROLE_MAP = {
    "Sable": "sentinel",
    "Vanta": "hunter",
    "Nyx": "acrobat",
    "Solace": "survivor",
    "Ember": "breaker",
    "Mirror": "sniper",
    "Archivist": "flanker",
    "Orbit": "sniper",
}

ARENA_WEAPON_PROFILES = {
    "pulse_rifle": {"title": "PULSE RIFLE", "damage_scale": 1.00, "color": (0.34, 0.92, 1.0, 0.92)},
    "arc_lance": {"title": "ARC LANCE", "damage_scale": 0.82, "splash": 28.0, "color": (0.70, 0.36, 1.0, 0.92)},
    "mech_breaker": {"title": "MECH BREAKER", "damage_scale": 1.18, "mech_scale": 1.80, "color": (1.0, 0.68, 0.16, 0.95)},
}
CAPTURE_POST_RADIUS = 34.0
CAPTURE_POST_COUNT_FALLBACK = 6
BOMB_ARM_RADIUS = 42.0
BOMB_BLAST_RADIUS = 46.0

# Urban Warzone AI awareness. This is intentionally lightweight steering rather
# than a heavy navmesh: each actor keeps personal space, checks firing lanes,
# avoids visible arena objects, and uses a short jetpack/boost hop when blocked
# or when high ground gives a cleaner shot.
AI_PERSONAL_SPACE = {"ally": 23.0, "robot": 16.0, "drone": 24.0, "mech": 38.0}
AI_OBJECT_BUFFER = 9.0
AI_LINE_OF_SIGHT_WIDTH = 4.8
AI_AIM_CONE_DOT = 0.58
AI_MAX_OBSTACLE_CHECKS = 80
AI_JETPACK_COOLDOWN = {"ally": 3.4, "robot": 4.2, "mech": 6.2}
AI_JETPACK_HEIGHT = {"ally": 16.0, "robot": 10.0, "mech": 22.0}

# Ambient Urban should feel like an active warfront before the formal Sable
# match starts, but it must remain cheap. Keep the always-on layer small,
# spaced out, and mostly line/box driven so normal region traversal stays fast.
AMBIENT_BATTLE_MAX_ACTORS = 10
AMBIENT_BATTLE_MAX_EVENTS = 4
AMBIENT_BATTLE_EVENT_MIN_INTERVAL = 4.8
AMBIENT_BATTLE_EVENT_MAX_INTERVAL = 8.8
AMBIENT_BATTLE_SFX_MIN_INTERVAL = 2.4

# Endgame boss + enemy family pass. Bosses are still mechs under the hood so the
# existing arena weapons, scoring, LoS, beams, and AI steering keep working.
# The visible body rig decides whether it reads as a rex, spider walker, or tank.
BOSS_COOLDOWN_SECONDS = 10.0
BOSS_VARIANTS = {"rex_boss", "spider_boss", "colossus"}
MECH_DINO_VARIANTS = {"raptor", "rex", "rex_boss"}
MECH_SPIDER_VARIANTS = {"spider", "spider_boss"}
ROBOT_VARIANTS = ("skeletal", "assault", "crawler", "shield", "stalker", "bomber", "sniper")
DRONE_VARIANTS = ("scout", "gunship", "jammer", "bomber", "repair_hunter")
MECH_VARIANTS = ("walker", "siege", "hunter", "raptor", "rex", "spider")


def _safe_tuple_color(value, fallback=(0.92, 0.96, 1.0, 0.86)):
    try:
        if value is None:
            return fallback
        vals = list(value)[:4]
        while len(vals) < 4:
            vals.append(1.0)
        return tuple(float(v) for v in vals)
    except Exception:
        return fallback



def _main_module(cls):
    return sys.modules.get(cls.__module__) or sys.modules.get("__main__")


def _load_arena_blueprint():
    """Load the dimension-local arena blueprint without adding a route/import dependency.

    The old legacy arena remains conceptually salvaged, but this module is safe:
    no ShowBase subclass, no window, no native adapter, no second process.
    """
    path = Path(__file__).resolve().with_name("arena_blueprint.py")
    if not path.exists():
        return None
    try:
        spec = importlib.util.spec_from_file_location("holoverse_urban_arena_blueprint", path)
        if spec is None or spec.loader is None:
            return None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    except Exception as exc:
        print(f"urban_arena_blueprint_load_error:{exc}")
        return None


def install_urban_warzone_runtime(CommandHubApp):
    main = _main_module(CommandHubApp)
    if main is None:
        return

    from holoverse_mode_runtime import resolve_shared_data_root

    ROOT = Path(getattr(main, "ROOT", Path(__file__).resolve().parent))
    ARENA_BLUEPRINT = _load_arena_blueprint()
    SHARED_DATA_ROOT = resolve_shared_data_root(main, ROOT)
    STATE_DIR = SHARED_DATA_ROOT / "holoverse" / "regions" / "urban" / "warzone"
    STATE_PATH = STATE_DIR / "urban_warzone_state.json"
    METROBOT_ARENA_EXPORT_PATH = SHARED_DATA_ROOT / "holoverse" / "regions" / "metropolis" / "robot_lab" / "arena_robot_allies.json"
    ROOT_PROGRESS_PATH = ROOT / "progression" / "progression_state.json"
    SHARED_PROGRESS_PATH = SHARED_DATA_ROOT / "holoverse" / "progression" / "progression_state.json"

    from holoverse_mode_runtime import install_in_world_route_aliases

    install_in_world_route_aliases(main)

    def _ensure_dirs():
        for folder in (STATE_DIR, ROOT_PROGRESS_PATH.parent, SHARED_PROGRESS_PATH.parent, SHARED_DATA_ROOT / "brain", SHARED_DATA_ROOT / "database"):
            folder.mkdir(parents=True, exist_ok=True)

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

    def _eye_z(self, x: float, y: float) -> float:
        try:
            return float(self.world_shell_grounded_z(float(x), float(y)))
        except Exception:
            return _floor_z(self, x, y) + float(getattr(self.cfg, "player_eye_height", 3.95)) + 0.16

    def _arena_underlay_z(self, x: float, y: float, lift: float = 0.0) -> float:
        """Shared z-position for the reused arena layer.

        This deliberately sits slightly below the Urban terrain/grid. It keeps
        the existing arena geometry visible as buried infrastructure without
        creating a separate room, proof tableau, or invisible wall maze above the
        player.
        """
        try:
            return _floor_z(self, float(x), float(y)) - float(ARENA_LAYER_DEPTH) + float(lift)
        except Exception:
            return -float(ARENA_LAYER_DEPTH) + float(lift)

    def _urban_allowed(self) -> bool:
        try:
            if self.is_holospace_active():
                return False
        except Exception:
            pass
        try:
            return int(self.current_holoverse_region_number()) == URBAN_REGION_NUMBER
        except Exception:
            return True

    def _is_warzone_mode(self, mode) -> bool:
        data = dict(mode or {})
        manifest = dict(data.get("manifest") or {})
        tokens = " ".join(str(x or "") for x in (
            data.get("name"), data.get("id"), data.get("title"),
            manifest.get("id"), manifest.get("title"), manifest.get("description"),
            manifest.get("host_contract"), manifest.get("preferred_display"),
        )).lower()
        return (
            "urban warzone" in tokens
            or "machine war" in tokens
            or "sable warzone" in tokens
            or str(manifest.get("id") or data.get("id") or "").lower() == "urban_warzone"
            or str(data.get("name") or "").lower() == "urban warzone"
        )

    def _difficulty_for_wave(wave: int) -> str:
        wave = int(wave or 1)
        if wave >= 9:
            return "NIGHTMARE"
        if wave >= 6:
            return "HARD"
        if wave >= 3:
            return "STANDARD"
        return "RECRUIT"

    def _challenge_for_wave(wave: int) -> str:
        wave = int(wave or 1)
        if wave > 0 and wave % 7 == 0:
            return "bomb_run"
        if wave > 0 and wave % 6 == 0:
            return "capture_lock"
        if wave > 0 and wave % 5 == 0:
            return "colossus"
        if wave > 0 and wave % 4 == 0:
            return "drone_storm"
        if wave > 0 and wave % 3 == 0:
            return "hunter_pack"
        if wave > 0 and wave % 2 == 0:
            return "mech_pressure"
        return "frontline"

    def _difficulty_profile(name: str) -> dict:
        return dict(DIFFICULTY_PROFILES.get(str(name or "STANDARD").upper(), DIFFICULTY_PROFILES["STANDARD"]))

    def _alive_allies(self):
        return [a for a in list(getattr(self, "urban_warzone_allies", []) or []) if float(a.get("hp", 0.0)) > 0.0]

    def _alive_enemies(self):
        return [e for e in list(getattr(self, "urban_warzone_enemies", []) or []) if float(e.get("hp", 0.0)) > 0.0]

    def _ally_cap_for_wave(self, wave: int | None = None) -> int:
        wave = int(getattr(self, "urban_warzone_wave", 0) or 0) if wave is None else int(wave or 0)
        score = int(getattr(self, "urban_warzone_score", 0) or 0)
        # Sable is the existing Urban guide bot, not a spawned duplicate.  Count
        # her as one combat ally when the mode is active, but only spawn the
        # remaining battle bots as runtime actors.
        base = STARTER_ALLY_COUNT + 1
        return max(base, min(MAX_ALLIES, base + max(0, wave // 2) + max(0, score // 4500)))

    def _register_score(self, enemy: dict, source: str = "player") -> int:
        kind = str(enemy.get("kind") or "robot")
        wave = int(getattr(self, "urban_warzone_wave", 1) or 1)
        difficulty = str(getattr(self, "urban_warzone_difficulty", _difficulty_for_wave(wave)) or "STANDARD")
        profile = _difficulty_profile(difficulty)
        challenge = str(getattr(self, "urban_warzone_challenge", "frontline") or "frontline")
        now = time.time()
        last = float(getattr(self, "urban_warzone_last_kill_at", 0.0) or 0.0)
        if now - last <= 3.0:
            self.urban_warzone_combo = min(12, int(getattr(self, "urban_warzone_combo", 0) or 0) + 1)
        else:
            self.urban_warzone_combo = 1
        self.urban_warzone_last_kill_at = now
        base = ENEMY_POINT_VALUES.get(kind, 100)
        variant = str(enemy.get("variant") or "")
        if variant == "colossus":
            base = 1400
        elif variant == "rex_boss":
            base = 1750
        elif variant == "spider_boss":
            base = 1900
        elif variant in {"rex", "spider"}:
            base = max(base, 850)
        elif variant == "raptor":
            base = max(base, 650)
        role_bonus = 35 if str(enemy.get("role") or "") in {"sniper", "breaker", "hunter"} else 0
        challenge_bonus = 75 if challenge != "frontline" else 0
        combo = int(getattr(self, "urban_warzone_combo", 1) or 1)
        points = int((base + role_bonus + challenge_bonus + wave * 12) * float(profile.get("score_scale", 1.0)) + combo * 18)
        if source == "ally":
            points = int(points * 0.70)
        self.urban_warzone_score = int(getattr(self, "urban_warzone_score", 0) or 0) + max(1, points)
        self.urban_warzone_points_this_run = int(getattr(self, "urban_warzone_points_this_run", 0) or 0) + max(1, points)
        self.urban_warzone_best_score = max(int(getattr(self, "urban_warzone_best_score", 0) or 0), int(getattr(self, "urban_warzone_score", 0) or 0))
        return points

    def _load_state() -> dict:
        _ensure_dirs()
        try:
            if STATE_PATH.exists():
                raw = json.loads(STATE_PATH.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    return raw
        except Exception:
            pass
        return {
            "schema": URBAN_WARZONE_SCHEMA,
            "kind": "holoverse_urban_warzone_state",
            "best_wave": 0,
            "runs_completed": 0,
            "robots_destroyed": 0,
            "mechs_destroyed": 0,
            "drones_destroyed": 0,
            "ally_assists": 0,
            "best_score": 0,
            "score": 0,
            "points_this_run": 0,
            "last_difficulty": "RECRUIT",
            "last_challenge": "frontline",
            "last_wave": 0,
        }

    def load_urban_warzone_state(self):
        data = _load_state()
        self.urban_warzone_best_wave = int(data.get("best_wave") or 0)
        self.urban_warzone_runs_completed = int(data.get("runs_completed") or 0)
        self.urban_warzone_total_kills = int(data.get("robots_destroyed") or 0)
        self.urban_warzone_total_mechs = int(data.get("mechs_destroyed") or 0)
        self.urban_warzone_total_drones = int(data.get("drones_destroyed") or 0)
        self.urban_warzone_ally_assists = int(data.get("ally_assists") or 0)
        self.urban_warzone_best_score = int(data.get("best_score") or data.get("score") or 0)
        self.urban_warzone_score = int(data.get("score") or 0)
        self.urban_warzone_points_this_run = int(data.get("points_this_run") or 0)
        self.urban_warzone_difficulty = str(data.get("last_difficulty") or "RECRUIT")
        self.urban_warzone_challenge = str(data.get("last_challenge") or "frontline")
        return data

    def _mirror_progress(self):
        payload = {
            "schema": URBAN_WARZONE_SCHEMA,
            "best_wave": int(getattr(self, "urban_warzone_best_wave", 0) or 0),
            "runs_completed": int(getattr(self, "urban_warzone_runs_completed", 0) or 0),
            "robots_destroyed": int(getattr(self, "urban_warzone_total_kills", 0) or 0),
            "mechs_destroyed": int(getattr(self, "urban_warzone_total_mechs", 0) or 0),
            "drones_destroyed": int(getattr(self, "urban_warzone_total_drones", 0) or 0),
            "ally_assists": int(getattr(self, "urban_warzone_ally_assists", 0) or 0),
            "capture_score": int(getattr(self, "urban_warzone_capture_score", 0) or 0),
            "bombs_detonated": int(getattr(self, "urban_warzone_bombs_detonated", 0) or 0),
            "last_weapon_mode": str(getattr(self, "urban_warzone_weapon_mode", "pulse_rifle") or "pulse_rifle"),
            "best_score": int(getattr(self, "urban_warzone_best_score", 0) or 0),
            "score": int(getattr(self, "urban_warzone_score", 0) or 0),
            "points_this_run": int(getattr(self, "urban_warzone_points_this_run", 0) or 0),
            "last_difficulty": str(getattr(self, "urban_warzone_difficulty", "RECRUIT") or "RECRUIT"),
            "last_challenge": str(getattr(self, "urban_warzone_challenge", "frontline") or "frontline"),
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "state_path": str(STATE_PATH),
        }
        for path in (ROOT_PROGRESS_PATH, SHARED_PROGRESS_PATH):
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                data = {}
                if path.exists():
                    raw = json.loads(path.read_text(encoding="utf-8"))
                    if isinstance(raw, dict):
                        data = raw
                regions = data.setdefault("regions", {})
                urban = regions.setdefault("urban", {})
                urban["warzone"] = payload
                data.setdefault("dimension_progress", {})["urban_warzone"] = payload
                data["updated_at"] = datetime.now().isoformat(timespec="seconds")
                path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
            except Exception as exc:
                print(f"urban_warzone_progress_mirror_error:{path}:{exc}")

    def save_urban_warzone_state(self, reason="manual"):
        _ensure_dirs()
        payload = {
            "schema": URBAN_WARZONE_SCHEMA,
            "kind": "holoverse_urban_warzone_state",
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "reason": str(reason),
            "save_path": str(STATE_PATH),
            "best_wave": int(getattr(self, "urban_warzone_best_wave", 0) or 0),
            "runs_completed": int(getattr(self, "urban_warzone_runs_completed", 0) or 0),
            "last_wave": int(getattr(self, "urban_warzone_wave", 0) or 0),
            "robots_destroyed": int(getattr(self, "urban_warzone_total_kills", 0) or 0),
            "mechs_destroyed": int(getattr(self, "urban_warzone_total_mechs", 0) or 0),
            "drones_destroyed": int(getattr(self, "urban_warzone_total_drones", 0) or 0),
            "ally_assists": int(getattr(self, "urban_warzone_ally_assists", 0) or 0),
            "capture_score": int(getattr(self, "urban_warzone_capture_score", 0) or 0),
            "bombs_detonated": int(getattr(self, "urban_warzone_bombs_detonated", 0) or 0),
            "last_weapon_mode": str(getattr(self, "urban_warzone_weapon_mode", "pulse_rifle") or "pulse_rifle"),
            "best_score": int(getattr(self, "urban_warzone_best_score", 0) or 0),
            "score": int(getattr(self, "urban_warzone_score", 0) or 0),
            "points_this_run": int(getattr(self, "urban_warzone_points_this_run", 0) or 0),
            "last_difficulty": str(getattr(self, "urban_warzone_difficulty", "RECRUIT") or "RECRUIT"),
            "last_challenge": str(getattr(self, "urban_warzone_challenge", "frontline") or "frontline"),
            "notes": "Endgame Urban: legacy arena reused as a buried whole-region activity layer with capture posts, evenly distributed bomb sites, 4D teleport wave effects, arena weapon pickups, eight non-IO battle-bot allies, scoring, challenge waves, robots, drones, and enemy mechs. No external arena launch or native adapter.",
        }
        try:
            STATE_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            _mirror_progress(self)
        except Exception as exc:
            print(f"urban_warzone_save_error:{exc}")
        return payload

    def _line_node(parent, name: str, color, pts, closed=False, thickness=1.0):
        segs = LineSegs(name)
        segs.setThickness(float(thickness))
        segs.setColor(*color)
        if pts:
            segs.moveTo(pts[0])
            for p in pts[1:]:
                segs.drawTo(p)
            if closed and len(pts) > 2:
                segs.drawTo(pts[0])
        np = parent.attachNewNode(segs.create())
        try:
            np.setAntialias(AntialiasAttrib.MLine)
            np.setTransparency(TransparencyAttrib.MAlpha)
        except Exception:
            pass
        return np

    def _box_segments(center: Vec3, size: Vec3):
        hx, hy, hz = float(size.x) * 0.5, float(size.y) * 0.5, float(size.z) * 0.5
        pts = [
            Vec3(center.x - hx, center.y - hy, center.z - hz), Vec3(center.x + hx, center.y - hy, center.z - hz),
            Vec3(center.x + hx, center.y + hy, center.z - hz), Vec3(center.x - hx, center.y + hy, center.z - hz),
            Vec3(center.x - hx, center.y - hy, center.z + hz), Vec3(center.x + hx, center.y - hy, center.z + hz),
            Vec3(center.x + hx, center.y + hy, center.z + hz), Vec3(center.x - hx, center.y + hy, center.z + hz),
        ]
        idx = [(0,1),(1,2),(2,3),(3,0),(4,5),(5,6),(6,7),(7,4),(0,4),(1,5),(2,6),(3,7)]
        out = []
        for a, b in idx:
            out.append((pts[a], pts[b]))
        return out

    def _add_box(parent, name: str, center: Vec3, size: Vec3, color, thickness=0.45):
        segs = []
        for a, b in _box_segments(center, size):
            segs.append(a); segs.append(b)
        ls = LineSegs(name)
        ls.setThickness(max(1.0, 1.6 * thickness))
        ls.setColor(*color)
        for i in range(0, len(segs), 2):
            ls.moveTo(segs[i]); ls.drawTo(segs[i+1])
        np = parent.attachNewNode(ls.create())
        try:
            np.setAntialias(AntialiasAttrib.MLine)
            np.setTransparency(TransparencyAttrib.MAlpha)
        except Exception:
            pass
        return np

    def _collider_from_box(center: Vec3, size: Vec3, label="cover"):
        return {
            "label": label,
            "minx": float(center.x - size.x * 0.5),
            "maxx": float(center.x + size.x * 0.5),
            "miny": float(center.y - size.y * 0.5),
            "maxy": float(center.y + size.y * 0.5),
            "minz": float(center.z - size.z * 0.5),
            "maxz": float(center.z + size.z * 0.5),
        }


    def _clamped_rgba(color, alpha=None, glow=1.0):
        vals = list(color or (1.0, 1.0, 1.0, 1.0))[:4]
        while len(vals) < 4:
            vals.append(1.0)
        r, g, b, a = [float(v) for v in vals]
        if alpha is not None:
            a = float(alpha)
        return (
            max(0.0, min(1.0, r * float(glow))),
            max(0.0, min(1.0, g * float(glow))),
            max(0.0, min(1.0, b * float(glow))),
            max(0.0, min(1.0, a)),
        )

    def _add_solid_box(parent, name: str, center: Vec3, size: Vec3, color, alpha=None):
        """Small untextured cuboid mesh used for readable war machines."""
        sx, sy, sz = max(0.05, float(size.x)), max(0.05, float(size.y)), max(0.05, float(size.z))
        hx, hy, hz = sx * 0.5, sy * 0.5, sz * 0.5
        verts = [
            (-hx, -hy, -hz), ( hx, -hy, -hz), ( hx,  hy, -hz), (-hx,  hy, -hz),
            (-hx, -hy,  hz), ( hx, -hy,  hz), ( hx,  hy,  hz), (-hx,  hy,  hz),
        ]
        tris = [
            (0, 1, 2), (0, 2, 3), (4, 6, 5), (4, 7, 6),
            (0, 4, 5), (0, 5, 1), (1, 5, 6), (1, 6, 2),
            (2, 6, 7), (2, 7, 3), (3, 7, 4), (3, 4, 0),
        ]
        fmt = GeomVertexFormat.getV3c4()
        vdata = GeomVertexData(name, fmt, Geom.UHStatic)
        vdata.setNumRows(8)
        vw = GeomVertexWriter(vdata, 'vertex')
        cw = GeomVertexWriter(vdata, 'color')
        rgba = _clamped_rgba(color, alpha)
        for x, y, z in verts:
            vw.addData3f(x, y, z)
            cw.addData4f(*rgba)
        prim = GeomTriangles(Geom.UHStatic)
        for a, b, c in tris:
            prim.addVertices(a, b, c)
        prim.closePrimitive()
        geom = Geom(vdata)
        geom.addPrimitive(prim)
        node = GeomNode(name)
        node.addGeom(geom)
        np = parent.attachNewNode(node)
        np.setPos(center)
        try:
            np.setTwoSided(True)
            np.setLightOff(1)
            np.setTransparency(TransparencyAttrib.MAlpha)
        except Exception:
            pass
        return np

    def _machine_box(parent, name: str, center: Vec3, size: Vec3, color, alpha=0.72, edge=0.28, glow=1.0):
        fill = _clamped_rgba(color, alpha, glow)
        edge_color = _clamped_rgba(color, min(0.98, max(alpha, 0.86)), min(1.35, glow * 1.12))
        _add_solid_box(parent, f"{name}-solid", center, size, fill)
        return _add_box(parent, f"{name}-edge", center, size, edge_color, edge)

    def _add_world_label(parent, name: str, text: str, pos: Vec3, color=(1, 1, 1, 1), scale=4.0):
        try:
            tn = TextNode(name)
            tn.setText(str(text))
            tn.setAlign(TextNode.ACenter)
            tn.setTextColor(*color)
            tn.setShadow(0.06, 0.06)
            tn.setShadowColor(0, 0, 0, min(1.0, float(color[3]) if len(color) > 3 else 1.0))
            node = parent.attachNewNode(tn)
            node.setPos(pos)
            node.setScale(float(scale))
            try:
                node.setBillboardPointEye()
                node.setLightOff(1)
            except Exception:
                pass
            return node
        except Exception:
            return None

    def _clear_screen_tableau(self):
        try:
            node = getattr(self, "urban_warzone_intro_root", None)
            if node is not None and not node.isEmpty():
                node.removeNode()
        except Exception:
            pass
        self.urban_warzone_intro_root = None
        self.urban_warzone_visual_proof_nodes = 0

    def _build_screen_tableau(self, p: Vec3, f: Vec3, r: Vec3):
        """Retired proof tableau.

        Urban Warzone now reuses the arena as a buried layer occupying the live
        Urban terrain. This function intentionally leaves no labels, giant debug
        statues, or duplicated proof scene behind.
        """
        _clear_screen_tableau(self)
        self.urban_warzone_visual_proof_nodes = 0
        return None

    def _init_state(self):
        self.urban_cover_root = None
        self.urban_cover_center_key = None
        self.urban_cover_colliders = []
        self.urban_jump_velocity = 0.0
        self.urban_on_cover_ground = False
        self.urban_warzone_active = False
        self.urban_battlefield_root = None
        self.urban_battlefield_center_key = None
        self.urban_battlefield_focus_pos = None
        self.urban_battlefield_active = False
        self.urban_battlefield_actors = []
        self.urban_battlefield_events = []
        self.urban_battlefield_next_event_at = 0.0
        self.urban_battlefield_next_sfx_at = 0.0
        self.urban_battlefield_event_seed = 0
        self.urban_metrobot_ambient_node = None
        self.urban_metrobot_ambient_id = ""
        self.urban_metrobot_ambient_status = "none"
        self.urban_warzone_root = None
        self.urban_warzone_ui_root = None
        self.urban_warzone_ui_panel = None
        self.urban_warzone_ui_title = None
        self.urban_warzone_ui_status = None
        self.urban_warzone_ui_help = None
        self.urban_warzone_intro_root = None
        self.urban_warzone_visual_proof_nodes = 0
        self.urban_warzone_arena_layer_nodes = 0
        self.urban_warzone_layer_mode = "buried_urban_underlay"
        self.urban_warzone_route_truth = "inactive"
        self.urban_warzone_route_marker = ""
        self.urban_warzone_route_owner = ROUTE_TRUTH_OWNER
        self.urban_warzone_wave = 0
        self.urban_warzone_player_hp = 100.0
        self.urban_warzone_kills_this_run = 0
        self.urban_warzone_score = 0
        self.urban_warzone_best_score = 0
        self.urban_warzone_points_this_run = 0
        self.urban_warzone_combo = 0
        self.urban_warzone_last_kill_at = 0.0
        self.urban_warzone_difficulty = "RECRUIT"
        self.urban_warzone_challenge = "frontline"
        self.urban_warzone_summon_index = 0
        self.urban_warzone_summon_cooldown = 0.0
        self.urban_warzone_next_wave_at = 0.0
        self.urban_warzone_exit_prompt_until = 0.0
        self.urban_warzone_enemies = []
        self.urban_warzone_allies = []
        self.urban_warzone_beams = []
        self.urban_warzone_spawn_anchors = []
        self.urban_warzone_power_nodes = []
        self.urban_warzone_pockets = []
        self.urban_warzone_capture_posts = []
        self.urban_warzone_bomb_sites = []
        self.urban_warzone_weapon_nodes = []
        self.urban_warzone_spawn_anchors = []
        self.urban_warzone_power_nodes = []
        self.urban_warzone_pockets = []
        self.urban_warzone_capture_posts = []
        self.urban_warzone_bomb_sites = []
        self.urban_warzone_weapon_nodes = []
        self.urban_warzone_capture_posts = []
        self.urban_warzone_bomb_sites = []
        self.urban_warzone_weapon_nodes = []
        self.urban_warzone_capture_score = 0
        self.urban_warzone_bombs_detonated = 0
        self.urban_warzone_weapon_mode = "pulse_rifle"
        self.urban_warzone_weapon_until = 0.0
        # State initialization must not activate the Urban route.
        # Activation is latched only by activate_urban_warzone_from_mode(...).
        _mark_urban_route_truth(self, False, source="state_init")
        self.urban_warzone_state_path = STATE_PATH
        self.urban_warzone_best_wave = 0
        self.urban_warzone_runs_completed = 0
        self.urban_warzone_total_kills = 0
        self.urban_warzone_total_mechs = 0
        self.urban_warzone_total_drones = 0
        self.urban_warzone_ally_assists = 0
        self.urban_warzone_capture_posts = []
        self.urban_warzone_bomb_sites = []
        self.urban_warzone_weapon_nodes = []
        self.urban_ai_obstacles = []
        self.urban_ai_los_checks = 0
        self.urban_ai_blocked_shots = 0
        self.urban_ai_clear_shots = 0
        self.urban_ai_boosts = 0
        self.urban_ai_spacing_corrections = 0
        self.urban_ai_obstacle_avoidance = 0
        self.urban_warzone_boss_active = None
        self.urban_warzone_last_boss_at = 0.0
        self.urban_warzone_last_boss_defeated_at = 0.0
        self.urban_warzone_player_down_penalty = 0
        self.urban_warzone_sable_uses_existing_bot = True
        self.urban_warzone_midwave_respawns = False
        self.urban_warzone_metrobot_allies = []
        self.urban_warzone_metrobot_ally_count = 0
        self.urban_warzone_metrobot_export_path = METROBOT_ARENA_EXPORT_PATH
        self.urban_metrobot_ambient_node = None
        self.urban_metrobot_ambient_id = ""
        self.urban_metrobot_ambient_status = "none"

    def _urban_runtime_parent(self):
        """Parent Urban runtime visuals to the visible HoloVerse shell.

        The default HoloVerse regions use the world-shell mount while world_root
        is hidden.  Old Urban failed because runtime geometry was built under
        the hidden artifact-world root.  Use the shell root whenever it exists.
        """
        try:
            # Keep Urban runtime visuals outside world_root because the default
            # HoloVerse shell hides world_root while walking normal regions.
            # render is the stable visible owner for in-world battlefield geometry.
            return self.render
        except Exception:
            return self.world_root

    def _destroy_cover(self):
        try:
            root = getattr(self, "urban_cover_root", None)
            if root is not None and not root.isEmpty():
                root.removeNode()
        except Exception:
            pass
        self.urban_cover_root = None
        self.urban_cover_center_key = None
        self.urban_cover_colliders = []
        self.urban_warzone_spawn_anchors = []
        self.urban_warzone_power_nodes = []
        self.urban_warzone_pockets = []
        self.urban_warzone_capture_posts = []
        self.urban_warzone_bomb_sites = []
        self.urban_warzone_weapon_nodes = []
        self.urban_ai_obstacles = []

    def _register_ai_obstacle(self, pos: Vec3, radius: float, height: float = 8.0, kind: str = "cover"):
        """Record visible Urban/arena objects so tactical AI can steer and aim around them.

        These are not collision walls. They are awareness volumes: bots keep distance
        from them and refuse blocked shots through them, which makes combat read as
        intelligent without turning the cleaned route back into a physics maze.
        """
        try:
            if not hasattr(self, "urban_ai_obstacles") or self.urban_ai_obstacles is None:
                self.urban_ai_obstacles = []
            p = Vec3(pos)
            self.urban_ai_obstacles.append({
                "pos": p,
                "radius": max(2.0, float(radius)),
                "height": max(1.0, float(height)),
                "kind": str(kind or "cover"),
            })
        except Exception:
            pass

    def _build_salvaged_arena_pockets(self, root, cx: float, cy: float, rng, colliders: list):
        """Translate the old legacy arena idea into world-owned urban pockets.

        The important part: this is not a launched arena. It is geometry + spawn
        rules mounted into the live Urban biome. The pockets are spaced apart so
        the whole biome feels repopulated instead of becoming one boxed room.
        """
        if ARENA_BLUEPRINT is None:
            return
        try:
            blueprint = ARENA_BLUEPRINT.generate_arena_blueprint(cx, cy, seed=(int(cx) * 31 + int(cy) * 17 + 0x51A5) & 0xFFFFFFFF)
        except Exception as exc:
            print(f"urban_arena_blueprint_generate_error:{exc}")
            return
        self.urban_warzone_pockets = list(blueprint.get("pockets") or [])
        self.urban_warzone_spawn_anchors = []
        self.urban_warzone_power_nodes = []
        grid_color = (0.00, 0.92, 1.00, 0.72)
        violet_color = (0.74, 0.25, 1.00, 0.70)
        red_color = (1.00, 0.18, 0.10, 0.78)
        amber_color = (1.00, 0.62, 0.08, 0.74)
        for pocket in list(blueprint.get("pockets") or []):
            px = float(pocket.get("x", cx)); py = float(pocket.get("y", cy))
            # Slight lift keeps the old arena infrastructure visible as embedded
            # circuit/road geometry instead of hiding it below the grey terrain.
            floor = _arena_underlay_z(self, px, py, 0.22)
            radius = float(pocket.get("radius", 62.0))
            _line_node(root, f"urban-vector-pocket-ring-{pocket.get('id', 'p')}", grid_color, [
                Vec3(px + math.cos(a) * radius, py + math.sin(a) * radius, floor + 0.28)
                for a in [i * math.tau / 48.0 for i in range(49)]
            ], False, max(1.0, getattr(self.cfg, "line_thickness", 1.6) * 0.38))
            _line_node(root, f"urban-vector-pocket-cross-{pocket.get('id', 'p')}", violet_color, [
                Vec3(px - radius, py, floor + 0.34), Vec3(px + radius, py, floor + 0.34),
                Vec3(px, py - radius, floor + 0.34), Vec3(px, py + radius, floor + 0.34),
            ], False, max(1.0, getattr(self.cfg, "line_thickness", 1.6) * 0.30))
        lane_color = (0.20, 0.86, 1.00, 0.68)
        trench_color = (1.00, 0.24, 0.10, 0.70)
        for idx, lane in enumerate(list(blueprint.get("lanes") or [])):
            typ = str(lane.get("type") or "assault_lane")
            ax = float(lane.get("ax", cx)); ay = float(lane.get("ay", cy))
            bx = float(lane.get("bx", cx)); by = float(lane.get("by", cy))
            az = _arena_underlay_z(self, ax, ay, float(lane.get("z", 0.48)) * 0.30)
            bz = _arena_underlay_z(self, bx, by, float(lane.get("z", 0.48)) * 0.30)
            color = trench_color if typ == "trench_line" else lane_color
            _line_node(root, f"urban-vector-{typ}-{idx}", color, [Vec3(ax, ay, az), Vec3(bx, by, bz)], False, max(1.0, getattr(self.cfg, "line_thickness", 1.6) * float(lane.get("width", 1.0)) * 0.34))
            # Low translucent pads make the reused arena roads visible in normal
            # gameplay views without creating collision or a separate room.
            try:
                mx, my = (ax + bx) * 0.5, (ay + by) * 0.5
                length_x = max(6.0, abs(bx - ax))
                length_y = max(6.0, abs(by - ay))
                pad_width = 5.5 if typ == "trench_line" else 7.5
                if length_x >= length_y:
                    _add_solid_box(root, f"urban-vector-{typ}-buried-pad-{idx}", Vec3(mx, my, min(az, bz) - 0.04), Vec3(length_x, pad_width, 0.10), color, alpha=0.20)
                else:
                    _add_solid_box(root, f"urban-vector-{typ}-buried-pad-{idx}", Vec3(mx, my, min(az, bz) - 0.04), Vec3(pad_width, length_y, 0.10), color, alpha=0.20)
            except Exception:
                pass

        all_structures = list(blueprint.get("landmarks") or []) + list(blueprint.get("structures") or [])
        sky_types = {"platform", "roof_platform", "skyway", "skyway_x", "skyway_y"}
        tower_types = {"tower", "watch_tower", "drone_spire", "relay_core", "command_spine", "frontline_beacon"}
        heavy_types = {"mech_hangar", "spawn_bunker"}
        collider_types = tower_types | sky_types | heavy_types | {"cover"}
        for idx, item in enumerate(all_structures):
            typ = str(item.get("type") or "cover")
            x = float(item.get("x", cx)); y = float(item.get("y", cy))
            sx = float(item.get("sx", 12.0)); sy = float(item.get("sy", 12.0)); sz = float(item.get("sz", 8.0))
            floor = _arena_underlay_z(self, x, y, 0.0)
            base_z = floor + float(item.get("z", 0.0)) * 0.45
            if typ in sky_types:
                color = grid_color
            elif typ in tower_types:
                color = violet_color if typ not in {"frontline_beacon"} else red_color
            elif typ in heavy_types:
                color = (0.90, 0.18, 0.12, 0.60)
            else:
                color = amber_color
            if typ == "gate":
                yaw = math.radians(float(item.get("yaw", 0.0) or 0.0))
                dx = math.cos(yaw + math.pi * 0.5) * sx * 0.5
                dy = math.sin(yaw + math.pi * 0.5) * sx * 0.5
                _line_node(root, f"urban-vector-gate-{idx}", red_color, [Vec3(x, y, base_z + 1.0), Vec3(x, y, base_z + sz)], False, max(1.0, getattr(self.cfg, "line_thickness", 1.6) * 0.42))
                _line_node(root, f"urban-vector-gate-top-{idx}", red_color, [Vec3(x - dx, y - dy, base_z + sz), Vec3(x + dx, y + dy, base_z + sz)], False, max(1.0, getattr(self.cfg, "line_thickness", 1.6) * 0.34))
                continue
            buried_size = Vec3(sx, sy, max(1.0, sz * 0.58))
            center = Vec3(x, y, base_z + buried_size.z * (0.5 - ARENA_STRUCTURE_SINK_RATIO * 0.42))
            thickness = 0.20 if typ in tower_types else (0.24 if typ in heavy_types else 0.26)
            # Solid translucent mass + neon edge: same arena data, but finally
            # readable as buried warzone infrastructure in gameplay.
            _machine_box(root, f"urban-vector-buried-{typ}-{idx}", center, buried_size, color, alpha=(0.20 if typ in heavy_types else 0.15), edge=thickness, glow=1.05)
            _register_ai_obstacle(self, Vec3(x, y, _floor_z(self, x, y)), max(sx, sy) * (0.50 if typ in tower_types else 0.40), max(4.0, sz * 0.58), typ)
            if typ in {"command_spine", "frontline_beacon", "relay_core", "drone_spire"}:
                _line_node(root, f"urban-vector-{typ}-mast-{idx}", color, [Vec3(x, y, base_z + buried_size.z), Vec3(x, y, base_z + buried_size.z + 8.0)], False, max(1.0, getattr(self.cfg, "line_thickness", 1.6) * 0.20))
            # Buried arena visuals do not create collision. The active fight uses actors,
            # not invisible walls hidden below the Urban terrain.
        for idx, node in enumerate(list(blueprint.get("power_nodes") or [])):
            x = float(node.get("x", cx)); y = float(node.get("y", cy)); z = _arena_underlay_z(self, x, y, float(node.get("z", 4.0)) * 0.35)
            self.urban_warzone_power_nodes.append(Vec3(x, y, z))
            _line_node(root, f"urban-vector-power-node-{idx}", amber_color, [Vec3(x-4,y,z), Vec3(x+4,y,z), Vec3(x,y-4,z), Vec3(x,y+4,z), Vec3(x,y,z-4), Vec3(x,y,z+4)], False, max(1.0, getattr(self.cfg, "line_thickness", 1.6) * 0.26))

        self.urban_warzone_capture_posts = []
        self.urban_warzone_bomb_sites = []
        self.urban_warzone_weapon_nodes = []
        capture_posts = list(blueprint.get("capture_posts") or [])
        if not capture_posts:
            capture_posts = [{"x": p.get("x", cx), "y": p.get("y", cy), "radius": CAPTURE_POST_RADIUS, "id": p.get("id", f"post_{i}")} for i, p in enumerate(list(blueprint.get("pockets") or [])[:CAPTURE_POST_COUNT_FALLBACK])]
        for idx, post in enumerate(capture_posts):
            x = float(post.get("x", cx)); y = float(post.get("y", cy))
            z = _arena_underlay_z(self, x, y, 1.1)
            radius = float(post.get("radius", CAPTURE_POST_RADIUS) or CAPTURE_POST_RADIUS)
            self.urban_warzone_capture_posts.append({"id": str(post.get("id") or f"capture_{idx}"), "pos": Vec3(x, y, _floor_z(self, x, y) + 0.8), "radius": radius, "capture": 0.0, "owner": "neutral", "scored": False})
            _line_node(root, f"urban-capture-post-ring-{idx}", (0.10, 1.00, 0.88, 0.74), [Vec3(x + math.cos(a) * radius, y + math.sin(a) * radius, z) for a in [n * math.tau / 44.0 for n in range(45)]], False, max(1.0, getattr(self.cfg, "line_thickness", 1.6) * 0.30))
            _machine_box(root, f"urban-capture-post-core-{idx}", Vec3(x, y, z + 2.6), Vec3(8.0, 8.0, 5.2), (0.08, 0.92, 0.82, 0.46), 0.26, 0.24, 1.15)
            _register_ai_obstacle(self, Vec3(x, y, _floor_z(self, x, y)), 8.0, 18.0, "capture_post")
            _line_node(root, f"urban-capture-post-spire-{idx}", (0.10, 1.00, 0.88, 0.78), [Vec3(x, y, z + 1.0), Vec3(x, y, z + 16.0)], False, max(1.0, getattr(self.cfg, "line_thickness", 1.6) * 0.26))
        for idx, bomb in enumerate(list(blueprint.get("bomb_sites") or [])):
            x = float(bomb.get("x", cx)); y = float(bomb.get("y", cy))
            z = _arena_underlay_z(self, x, y, 0.75)
            self.urban_warzone_bomb_sites.append({"id": str(bomb.get("id") or f"bomb_{idx}"), "pos": Vec3(x, y, _floor_z(self, x, y) + 0.9), "armed": True, "cooldown": 0.0, "radius": float(bomb.get("radius", BOMB_BLAST_RADIUS) or BOMB_BLAST_RADIUS)})
            _machine_box(root, f"urban-bomb-site-{idx}", Vec3(x, y, z + 1.7), Vec3(8.5, 8.5, 3.4), (1.0, 0.16, 0.05, 0.58), 0.32, 0.22, 1.10)
            _register_ai_obstacle(self, Vec3(x, y, _floor_z(self, x, y)), 7.5, 5.0, "bomb_site")
            _line_node(root, f"urban-bomb-site-warning-{idx}", (1.0, 0.18, 0.04, 0.72), [Vec3(x + math.cos(a) * 15.0, y + math.sin(a) * 15.0, z + 0.4) for a in [n * math.tau / 32.0 for n in range(33)]], False, max(1.0, getattr(self.cfg, "line_thickness", 1.6) * 0.22))
        for idx, weapon in enumerate(list(blueprint.get("weapon_nodes") or [])):
            x = float(weapon.get("x", cx)); y = float(weapon.get("y", cy)); mode = str(weapon.get("weapon") or "pulse_rifle")
            z = _arena_underlay_z(self, x, y, 1.3)
            color = ARENA_WEAPON_PROFILES.get(mode, ARENA_WEAPON_PROFILES["pulse_rifle"]).get("color", (0.34, 0.92, 1.0, 0.92))
            self.urban_warzone_weapon_nodes.append({"id": str(weapon.get("id") or f"weapon_{idx}"), "pos": Vec3(x, y, _floor_z(self, x, y) + 0.8), "weapon": mode, "radius": 30.0})
            _machine_box(root, f"urban-weapon-node-{idx}-{mode}", Vec3(x, y, z + 1.8), Vec3(10.0, 10.0, 3.6), color, 0.30, 0.24, 1.15)
            _register_ai_obstacle(self, Vec3(x, y, _floor_z(self, x, y)), 7.0, 7.0, "weapon_node")
            _line_node(root, f"urban-weapon-node-icon-{idx}", color, [Vec3(x-8, y, z+5.8), Vec3(x+8, y, z+5.8), Vec3(x, y-8, z+5.8), Vec3(x, y+8, z+5.8)], False, max(1.0, getattr(self.cfg, "line_thickness", 1.6) * 0.30))

        for anchor in list(blueprint.get("spawn_anchors") or []):
            try:
                self.urban_warzone_spawn_anchors.append({
                    "pos": Vec3(float(anchor.get("x", cx)), float(anchor.get("y", cy)), _floor_z(self, float(anchor.get("x", cx)), float(anchor.get("y", cy))) + float(anchor.get("z", 0.8))),
                    "kind": str(anchor.get("kind") or "mixed"),
                    "role": str(anchor.get("role") or "duelist"),
                    "pocket": str(anchor.get("pocket") or ""),
                })
            except Exception:
                pass

    def _build_urban_cover_layer(self):
        _destroy_cover(self)
        player = Vec3(getattr(self, "player_pos", Vec3(0, 0, 0)))
        # Rebuild on a coarse grid so the cover district follows the player when
        # crossing the huge urban ring, but remains deterministic and lightweight.
        grid = 420.0
        cx = round(float(player.x) / grid) * grid
        cy = round(float(player.y) / grid) * grid
        key = (int(cx), int(cy))
        self.urban_cover_center_key = key
        root = _urban_runtime_parent(self).attachNewNode("urban-warzone-buried-arena-layer")
        root.setTransparency(TransparencyAttrib.MAlpha)
        self.urban_cover_root = root
        rng = random.Random((key[0] * 928371 + key[1] * 364479 + 2417) & 0xFFFFFFFF)
        colliders = []
        self.urban_ai_obstacles = []
        line_color = (0.72, 0.75, 0.78, 0.72)
        ruin_color = (0.94, 0.24, 0.16, 0.58)
        cover_color = (0.88, 0.92, 0.95, 0.68)
        road_color = (0.48, 0.52, 0.58, 0.38)
        # Buried street/grid lanes: the arena occupies the Urban biome below the visible terrain.
        for lane in range(-3, 4):
            x = cx + lane * 70.0
            y0, y1 = cy - 290.0, cy + 290.0
            z0 = _arena_underlay_z(self, x, cy, 0.10)
            _line_node(root, f"urban-war-road-x-{lane}", road_color, [Vec3(x, y0, z0), Vec3(x, y1, z0)], False, max(1.0, getattr(self.cfg, "line_thickness", 1.6) * 0.36))
            y = cy + lane * 70.0
            x0, x1 = cx - 290.0, cx + 290.0
            z1 = _arena_underlay_z(self, cx, y, 0.10)
            _line_node(root, f"urban-war-road-y-{lane}", road_color, [Vec3(x0, y, z1), Vec3(x1, y, z1)], False, max(1.0, getattr(self.cfg, "line_thickness", 1.6) * 0.36))
        # Buildings: lower than Metropolis, longer blocks, with combat gaps.
        spots = []
        for gx in range(-3, 4):
            for gy in range(-3, 4):
                if abs(gx) <= 1 and abs(gy) <= 1:
                    continue
                if rng.random() < 0.62:
                    spots.append((gx, gy))
        for idx, (gx, gy) in enumerate(spots[:26]):
            x = cx + gx * 70.0 + rng.uniform(-13.0, 13.0)
            y = cy + gy * 70.0 + rng.uniform(-13.0, 13.0)
            floor = _arena_underlay_z(self, x, y, 0.0)
            long_axis = rng.choice((0, 1))
            sx = rng.uniform(22.0, 38.0) if not long_axis else rng.uniform(48.0, 92.0)
            sy = rng.uniform(22.0, 38.0) if long_axis else rng.uniform(48.0, 92.0)
            sz = rng.uniform(10.0, 42.0) * (0.70 if rng.random() < 0.45 else 1.0)
            size = Vec3(sx, sy, max(2.0, sz * 0.46))
            center = Vec3(x, y, floor + size.z * 0.22)
            _machine_box(root, f"urban-buried-arena-ruin-{idx}", center, size, line_color, alpha=0.18, edge=0.36, glow=1.0)
            _register_ai_obstacle(self, Vec3(x, y, _floor_z(self, x, y)), max(sx, sy) * 0.42, max(5.0, sz * 0.50), "ruin")
            # Broken top line and red damage seam.
            _line_node(root, f"urban-cover-broken-roof-{idx}", ruin_color, [Vec3(x - sx*0.5, y - sy*0.5, floor + size.z * 0.58), Vec3(x + sx*0.1, y + sy*0.55, floor + size.z * 0.38), Vec3(x + sx*0.5, y - sy*0.1, floor + size.z * 0.58)], False, max(1.0, getattr(self.cfg, "line_thickness", 1.6) * 0.26))
            # Underlay ruins are visual only; no hidden collider wall.
        # Cover barricades/mech wreck chunks around open intersections.
        for idx in range(34):
            x = cx + rng.uniform(-285.0, 285.0)
            y = cy + rng.uniform(-285.0, 285.0)
            if abs(x - player.x) < 20.0 and abs(y - player.y) < 20.0:
                continue
            floor = _arena_underlay_z(self, x, y, 0.0)
            sx = rng.uniform(5.0, 14.0)
            sy = rng.uniform(4.0, 18.0)
            sz = rng.uniform(2.8, 8.0)
            size = Vec3(sx, sy, max(1.4, sz * 0.54))
            center = Vec3(x, y, floor + size.z * 0.28)
            _machine_box(root, f"urban-buried-arena-barricade-{idx}", center, size, cover_color, alpha=0.22, edge=0.28, glow=1.0)
            _register_ai_obstacle(self, Vec3(x, y, _floor_z(self, x, y)), max(sx, sy) * 0.65, max(2.0, sz * 0.60), "barricade")
            # Underlay cover is visual only; live actors provide the combat.
        # Ramps/low roof access as stepped visual + top collider.
        for idx in range(6):
            x = cx + rng.uniform(-240.0, 240.0)
            y = cy + rng.uniform(-240.0, 240.0)
            floor = _arena_underlay_z(self, x, y, 0.0)
            sx, sy, sz = 28.0, 12.0, 8.0
            center = Vec3(x, y, floor + sz * 0.22)
            _machine_box(root, f"urban-buried-arena-ramp-base-{idx}", center, Vec3(sx, sy, max(1.4, sz * 0.45)), (0.78, 0.82, 0.86, 0.50), alpha=0.16, edge=0.24, glow=1.0)
            _register_ai_obstacle(self, Vec3(x, y, _floor_z(self, x, y)), max(sx, sy) * 0.38, max(4.0, sz * 0.72), "ramp")
            _line_node(root, f"urban-cover-ramp-slope-{idx}", (0.98, 0.40, 0.18, 0.62), [Vec3(x - sx*0.5, y - sy*0.5, floor + 0.05), Vec3(x + sx*0.5, y + sy*0.5, floor + sz * 0.42)], False, max(1.0, getattr(self.cfg, "line_thickness", 1.6) * 0.34))
            # Underlay ramp is visual only.
        _build_salvaged_arena_pockets(self, root, cx, cy, rng, colliders)
        self.urban_cover_colliders = []
        try:
            self.urban_warzone_arena_layer_nodes = int(root.getNumChildren())
        except Exception:
            self.urban_warzone_arena_layer_nodes = 0

    def _resolve_urban_cover_collision(self, dt: float):
        if not _urban_allowed(self):
            self.urban_jump_velocity = 0.0
            return
        eye = float(getattr(self.cfg, "player_eye_height", 3.95))
        clearance = float(getattr(self.cfg, "terrain_collision_clearance", 0.16))
        pos = Vec3(getattr(self, "player_pos", Vec3(0, 0, 0)))
        terrain_eye = _eye_z(self, pos.x, pos.y)
        foot_z = float(pos.z) - eye
        on_top_z = None
        radius = 1.35
        for col in list(getattr(self, "urban_cover_colliders", []) or []):
            inside_xy = (col["minx"] - radius <= pos.x <= col["maxx"] + radius and col["miny"] - radius <= pos.y <= col["maxy"] + radius)
            if not inside_xy:
                continue
            # Allow roof standing when landing on top or walking across it.
            # old_update_player grounds the camera before this runtime patch, so
            # keep roof contact alive if the previous frame was already on cover.
            top = float(col["maxz"])
            already_on_cover = bool(getattr(self, "urban_on_cover_ground", False))
            if foot_z >= top - 1.15 or already_on_cover:
                on_top_z = max(on_top_z or -999999.0, top + eye + clearance)
                continue
            if foot_z <= top + 0.4:
                # Push out on the shallowest side so buildings work as cover.
                left = abs(pos.x - (col["minx"] - radius))
                right = abs((col["maxx"] + radius) - pos.x)
                down = abs(pos.y - (col["miny"] - radius))
                up = abs((col["maxy"] + radius) - pos.y)
                m = min(left, right, down, up)
                if m == left:
                    pos.x = col["minx"] - radius
                elif m == right:
                    pos.x = col["maxx"] + radius
                elif m == down:
                    pos.y = col["miny"] - radius
                else:
                    pos.y = col["maxy"] + radius
        # Lightweight jump/gravity for Urban only. Old world movement keeps the
        # camera grounded first; this pass then lifts it onto cover/roofs.
        on_ground = False
        target_eye = on_top_z if on_top_z is not None else terrain_eye
        if pos.z <= target_eye + 0.05:
            pos.z = target_eye
            self.urban_jump_velocity = 0.0
            on_ground = True
        if self.keys.get("space") and on_ground:
            self.urban_jump_velocity = 15.5
            on_ground = False
        if not on_ground:
            self.urban_jump_velocity = float(getattr(self, "urban_jump_velocity", 0.0)) - 42.0 * max(0.001, min(0.05, dt))
            pos.z += float(getattr(self, "urban_jump_velocity", 0.0)) * max(0.001, min(0.05, dt))
            if pos.z <= target_eye:
                pos.z = target_eye
                self.urban_jump_velocity = 0.0
                on_ground = True
        self.urban_on_cover_ground = bool(on_ground and on_top_z is not None)
        self.player_pos = pos
        try:
            self.camera.setPos(self.player_pos)
        except Exception:
            pass

    def update_urban_cover_layer(self, dt=0.0):
        if not _urban_allowed(self):
            _destroy_cover(self)
            return
        player = Vec3(getattr(self, "player_pos", Vec3(0, 0, 0)))
        grid = 420.0
        key = (int(round(float(player.x) / grid) * grid), int(round(float(player.y) / grid) * grid))
        if getattr(self, "urban_cover_root", None) is None or self.urban_cover_root.isEmpty() or key != getattr(self, "urban_cover_center_key", None):
            _build_urban_cover_layer(self)
        _resolve_urban_cover_collision(self, float(dt or 0.016))

    def _destroy_urban_battlefield_runtime(self):
        try:
            node = getattr(self, "urban_battlefield_root", None)
            if node is not None and not node.isEmpty():
                node.removeNode()
        except Exception:
            pass
        self.urban_battlefield_root = None
        self.urban_battlefield_center_key = None
        self.urban_battlefield_focus_pos = None
        self.urban_battlefield_active = False
        self.urban_battlefield_actors = []
        self.urban_battlefield_events = []

    def ensure_urban_battlefield_runtime(self, dt=0.0, source="world_update"):
        """Keep Urban visually a battlefield without starting the Sable match.

        Urban has one owner now: this runtime.  Region entry mounts the ambient
        battlefield layer, while Sable only flips the formal arena rules on
        (points, waves, objectives, bosses, bot roster).
        """
        if not _urban_allowed(self):
            if not bool(getattr(self, "urban_warzone_active", False)):
                _destroy_urban_battlefield_runtime(self)
            _destroy_cover(self)
            return False
        update_urban_cover_layer(self, dt)
        if bool(getattr(self, "urban_warzone_active", False)):
            _destroy_urban_battlefield_runtime(self)
            return True
        player = Vec3(getattr(self, "player_pos", Vec3(0, 0, 0)))
        grid = 420.0
        key = (int(round(float(player.x) / grid) * grid), int(round(float(player.y) / grid) * grid))
        root = getattr(self, "urban_battlefield_root", None)
        if root is not None and not root.isEmpty() and key == getattr(self, "urban_battlefield_center_key", None):
            try:
                _update_urban_battlefield_ambient(self, dt, root)
            except Exception as exc:
                print(f"urban_battlefield_ambient_update_warning:{exc}")
            try:
                _sync_ambient_metropolis_robot_ally(self, root, reason=source)
            except Exception as exc:
                print(f"urban_metrobot_ambient_sync_warning:{exc}")
            return True
        _destroy_urban_battlefield_runtime(self)
        root = _urban_runtime_parent(self).attachNewNode("urban-warzone-ambient-battlefield")
        root.setTransparency(TransparencyAttrib.MAlpha)
        self.urban_battlefield_root = root
        self.urban_battlefield_center_key = key
        try:
            yaw = math.radians(float(getattr(self, "player_yaw", 0.0)))
        except Exception:
            yaw = 0.0
        forward = Vec3(math.sin(yaw), math.cos(yaw), 0.0)
        if forward.lengthSquared() < 0.001:
            forward = Vec3(0, -1, 0)
        forward.normalize()
        right = Vec3(forward.y, -forward.x, 0.0)
        focus = player + forward * 82.0
        focus.z = _floor_z(self, focus.x, focus.y) + 12.0
        self.urban_battlefield_focus_pos = Vec3(focus)
        specs = [
            ("ally", "Vanta", "hunter", "support", 48.0, -48.0, 0.8, 18.0),
            ("ally", "Nyx", "acrobat", "support", 66.0, 38.0, 0.8, -12.0),
            ("ally", "Ember", "breaker", "support", 96.0, -72.0, 0.8, 28.0),
            ("ally", "Mirror", "sniper", "support", 138.0, 72.0, 0.8, -18.0),
            ("mech", "ambient_mech_rex", "breaker", "rex", 104.0, -18.0, 0.9, 180.0),
            ("mech", "ambient_mech_spider", "sentinel", "spider", 156.0, 48.0, 0.9, 205.0),
            ("robot", "ambient_robot_skeletal", "duelist", "skeletal", 76.0, 18.0, 0.7, 160.0),
            ("robot", "ambient_robot_assault", "flanker", "assault", 118.0, -58.0, 0.7, 190.0),
            ("drone", "ambient_drone_gunship", "sniper", "gunship", 132.0, -4.0, 26.0, 180.0),
            ("drone", "ambient_drone_scout", "hunter", "scout", 174.0, 84.0, 20.0, 215.0),
        ]
        actors = []
        for idx, (kind, name, role, variant, fd, lat, zoff, yaw_offset) in enumerate(specs[:AMBIENT_BATTLE_MAX_ACTORS]):
            pos = player + forward * fd + right * lat
            pos.z = _floor_z(self, pos.x, pos.y) + zoff
            actor = {
                "kind": kind, "variant": variant, "role": role, "name": name,
                "seed": 9100 + idx, "pos": Vec3(pos), "home": Vec3(pos),
                "yaw": float(getattr(self, "player_yaw", 0.0)) + yaw_offset,
                "faction": "ally" if kind == "ally" else "enemy",
                "cooldown": 0.35 + idx * 0.22,
                "speed": 14.0 if kind == "ally" else (12.0 if kind == "robot" else (16.0 if kind == "drone" else 6.0)),
                "ambient": True,
            }
            try:
                _build_actor_node(self, root, actor)
                _set_actor_pos(actor)
                actors.append(actor)
            except Exception as exc:
                print(f"urban_battlefield_ambient_actor_warning:{exc}")
        try:
            _sync_ambient_metropolis_robot_ally(self, root, reason=source)
        except Exception as exc:
            print(f"urban_metrobot_ambient_sync_warning:{exc}")
        try:
            if len(actors) >= 4:
                pairs = [(2, 0), (3, 1), (4, 0), (5, 1), (0, 3)]
                colors = [(1.0, 0.12, 0.04, 0.72), (1.0, 0.36, 0.08, 0.62), (0.15, 0.92, 1.0, 0.58), (1.0, 0.10, 0.04, 0.70), (1.0, 0.04, 0.02, 0.74)]
                for n, ((a_idx, b_idx), color) in enumerate(zip(pairs, colors)):
                    apos = Vec3(actors[a_idx].get("pos", Vec3())) + Vec3(0, 0, 5.5 if actors[a_idx].get("kind") != "drone" else 0.0)
                    bpos = Vec3(actors[b_idx].get("pos", Vec3())) + Vec3(0, 0, 11.0 if actors[b_idx].get("kind") == "mech" else 5.0)
                    _line_node(root, f"urban-ambient-crossfire-{n}", color, [apos, bpos], False, max(1.0, getattr(self.cfg, "line_thickness", 1.6) * 0.30))
        except Exception as exc:
            print(f"urban_battlefield_ambient_beam_warning:{exc}")
        self.urban_battlefield_actors = actors
        self.urban_battlefield_events = []
        self.urban_battlefield_event_seed = int(getattr(self, "urban_battlefield_event_seed", 0) or 0) + 1
        try:
            _update_urban_battlefield_ambient(self, 0.033, root)
        except Exception as exc:
            print(f"urban_battlefield_ambient_boot_warning:{exc}")
        self.urban_battlefield_active = True
        self.urban_warzone_layer_mode = "ambient_battlefield"
        self.runtime_world_signature = "URBAN WARZONE // AMBIENT BATTLEFIELD ONLINE"
        try:
            if getattr(self, "center_hint", None) is not None and source in {"region_shot", "entry", "world_update"}:
                self.center_hint["text"] = "URBAN BATTLEFIELD // TALK TO SABLE TO START THE MATCH"
        except Exception:
            pass
        try:
            if hasattr(self, "update_perf_hud"):
                self.update_perf_hud(force=True)
        except Exception:
            pass
        return True

    def _actor_color(kind: str, name: str = "", role: str = ""):
        if kind == "ally":
            table = {
                "Sable": (0.92, 0.20, 0.16, 0.94), "Vanta": (0.26, 1.00, 0.42, 0.92),
                "Nyx": (0.72, 0.52, 1.00, 0.92), "Solace": (0.38, 1.00, 0.92, 0.92),
                "Ember": (1.00, 0.55, 0.18, 0.92), "Mirror": (0.46, 0.78, 1.00, 0.92),
                "Archivist": (0.86, 0.42, 1.00, 0.92), "Orbit": (0.60, 0.72, 1.00, 0.94),
            }
            return table.get(name, (0.75, 0.9, 1.0, 0.9))
        if ARENA_BLUEPRINT is not None:
            try:
                style = ARENA_BLUEPRINT.role_style(role or "duelist")
                if style:
                    return _safe_tuple_color(style.get("color"), (0.92, 0.96, 1.0, 0.86))
            except Exception:
                pass
        if kind == "mech":
            return (1.0, 0.22, 0.12, 0.94)
        if kind == "drone":
            return (1.0, 0.48, 0.18, 0.90)
        return (0.92, 0.96, 1.0, 0.86)

    def _role_dims(role: str):
        if ARENA_BLUEPRINT is not None:
            try:
                style = ARENA_BLUEPRINT.role_style(role or "duelist")
                if style:
                    return (
                        tuple(style.get("torso", (2.0, 1.2, 3.0))),
                        tuple(style.get("head", (1.3, 1.0, 1.0))),
                        float(style.get("weapon_len", 2.4)),
                    )
            except Exception:
                pass
        return (2.0, 1.2, 3.0), (1.3, 1.0, 1.0), 2.4

    def _build_role_actor(root, kind: str, color, role: str, variant: str = "standard"):
        torso, head, weapon_len = _role_dims(role)
        tx, ty, tz = torso
        hx, hy, hz = head
        enemy = kind != "ally"
        robot_scale = 1.18 if enemy else 1.05
        if str(variant) == "crawler":
            robot_scale = 0.92
        elif str(variant) == "shield":
            robot_scale = 1.28
        elif str(variant) == "assault":
            robot_scale = 1.34
        tx = max(2.9, tx * 1.35) * robot_scale
        ty = max(1.8, ty * 1.40) * robot_scale
        tz = max(3.8, tz * 1.18) * robot_scale
        hx = max(1.55, hx * 1.22) * robot_scale
        hy = max(1.35, hy * 1.18) * robot_scale
        hz = max(1.25, hz * 1.05) * robot_scale
        if not enemy:
            tx *= 0.92; ty *= 0.92; tz *= 0.94
        base_alpha = 0.58 if enemy else 0.50
        hot = (1.0, 0.08, 0.03, 0.92) if enemy else color
        zbase = 0.15
        _machine_box(root, f"{role}-{variant}-pelvis", Vec3(0, 0, zbase + 1.55 * robot_scale), Vec3(tx * 0.78, ty * 0.82, 1.15 * robot_scale), color, base_alpha, 0.24)
        _machine_box(root, f"{role}-{variant}-torso", Vec3(0, 0, zbase + 3.95 * robot_scale), Vec3(tx, ty, tz), color, base_alpha + 0.07, 0.28)
        _machine_box(root, f"{role}-{variant}-head", Vec3(0, -0.08 * robot_scale, zbase + 4.15 * robot_scale + tz * 0.55 + hz * 0.55), Vec3(hx, hy, hz), color, base_alpha + 0.12, 0.24)
        visor = hot if enemy else _clamped_rgba(color, 0.86, 1.25)
        _machine_box(root, f"{role}-{variant}-visor", Vec3(0, -hy * 0.54, zbase + 4.15 * robot_scale + tz * 0.55 + hz * 0.60), Vec3(hx * 0.82, 0.18 * robot_scale, hz * 0.22), visor, 0.88, 0.16, 1.25)
        arm_z = zbase + 3.85 * robot_scale
        for side in (-1, 1):
            _machine_box(root, f"{role}-{variant}-shoulder-{side}", Vec3(side * (tx * 0.67), 0, arm_z + 0.9 * robot_scale), Vec3(0.92 * robot_scale, ty * 0.86, 1.05 * robot_scale), color, base_alpha, 0.20)
            _machine_box(root, f"{role}-{variant}-forearm-{side}", Vec3(side * (tx * 0.86), -0.08 * robot_scale, arm_z - 0.65 * robot_scale), Vec3(0.76 * robot_scale, ty * 0.66, 1.75 * robot_scale), color, base_alpha, 0.20)
            _machine_box(root, f"{role}-{variant}-thigh-{side}", Vec3(side * (tx * 0.24), 0, zbase + 0.30 * robot_scale), Vec3(0.85 * robot_scale, ty * 0.60, 1.90 * robot_scale), color, base_alpha, 0.20)
            _machine_box(root, f"{role}-{variant}-shin-{side}", Vec3(side * (tx * 0.33), 0, zbase - 1.40 * robot_scale), Vec3(0.68 * robot_scale, ty * 0.52, 1.85 * robot_scale), color, base_alpha, 0.20)
            _machine_box(root, f"{role}-{variant}-foot-{side}", Vec3(side * (tx * 0.38), -0.18 * robot_scale, zbase - 2.42 * robot_scale), Vec3(1.15 * robot_scale, ty * 0.95, 0.36 * robot_scale), color, base_alpha, 0.18)
        if enemy:
            if str(variant) == "shield":
                _machine_box(root, "shield-riot-plate", Vec3(0, -ty * 0.98, zbase + 2.95 * robot_scale), Vec3(tx * 1.22, 0.42 * robot_scale, 4.2 * robot_scale), (1.0, 0.28, 0.06, 0.72), 0.42, 0.26)
            elif str(variant) == "crawler":
                for side in (-1, 1):
                    for off in (-0.9, 0.9):
                        _machine_box(root, f"crawler-leg-{side}-{off}", Vec3(side * (tx * 0.72), off * ty, zbase - 0.70 * robot_scale), Vec3(1.75 * robot_scale, 0.35 * robot_scale, 0.55 * robot_scale), color, 0.50, 0.16)
                _machine_box(root, "crawler-low-spine", Vec3(0, 0.85 * robot_scale, zbase + 1.75 * robot_scale), Vec3(tx * 1.20, ty * 0.42, 0.65 * robot_scale), hot, 0.55, 0.18)
            elif str(variant) == "assault":
                for side in (-1, 1):
                    _machine_box(root, f"assault-back-pack-{side}", Vec3(side * (tx * 0.42), ty * 0.72, zbase + 5.15 * robot_scale), Vec3(0.92 * robot_scale, 0.76 * robot_scale, 2.7 * robot_scale), hot, 0.52, 0.18)
            weapon_side = 1 if role not in {"flanker", "acrobat"} else -1
            _machine_box(root, "hostile-rifle-block", Vec3(weapon_side * (tx * 0.82), -ty * 1.18, zbase + 2.95 * robot_scale), Vec3(0.48 * robot_scale, max(2.8, weapon_len * 1.45), 0.48 * robot_scale), hot, 0.66, 0.18, 1.15)
            _line_node(root, f"{role}-hostile-range-beam", (1.0, 0.12, 0.03, 0.45), [Vec3(weapon_side * (tx * 0.82), -ty * 1.25, zbase + 2.95 * robot_scale), Vec3(weapon_side * (tx * 0.82), -ty * 1.25 - max(5.0, weapon_len * 2.0), zbase + 2.95 * robot_scale)], False, max(1.0, 1.6 * 0.16))
        else:
            _machine_box(root, "ally-core", Vec3(0, ty * 0.68, zbase + 4.05 * robot_scale), Vec3(tx * 0.42, 0.36 * robot_scale, tz * 0.64), _clamped_rgba(color, 0.78, 1.28), 0.62, 0.16, 1.22)
            _line_node(root, "ally-support-ring", _clamped_rgba(color, 0.78, 1.18), [Vec3(math.cos(a) * 4.8 * robot_scale, math.sin(a) * 4.8 * robot_scale, zbase - 2.25 * robot_scale) for a in [i * math.tau / 32.0 for i in range(33)]], False, max(1.0, 1.6 * 0.17))

    def _build_actor_node(self, parent, actor: dict):
        kind = str(actor.get("kind") or "robot")
        name = str(actor.get("name") or kind)
        role = str(actor.get("role") or (BOT_ROLE_MAP.get(name) if kind == "ally" else "duelist") or "duelist")
        variant = str(actor.get("variant") or ("support" if kind == "ally" else "standard"))
        color = _actor_color("ally" if kind == "ally" else kind, name, role)
        root = parent.attachNewNode(f"urban-warzone-{kind}-{variant}-{role}-{name}-{int(actor.get('seed', 0))}")
        root.setTransparency(TransparencyAttrib.MAlpha)

        blueprint = actor.get("metropolis_robot_blueprint")
        if isinstance(blueprint, dict):
            _build_metropolis_blueprint_actor(root, actor, blueprint, color)
            actor["node"] = root
            actor["role"] = role
            actor["variant"] = variant
            return root

        if kind == "drone":
            scale = 1.0
            if variant == "gunship":
                scale = 1.24
            elif variant == "jammer":
                scale = 1.12
            hot = (1.0, 0.12, 0.04, 0.92)
            _machine_box(root, f"drone-{variant}-core", Vec3(0, 0, 0), Vec3(5.8 * scale, 3.2 * scale, 1.8 * scale), color, 0.62, 0.24)
            _machine_box(root, f"drone-{variant}-nose", Vec3(0, -2.55 * scale, 0.02), Vec3(2.2 * scale, 2.4 * scale, 1.25 * scale), hot, 0.58, 0.18, 1.14)
            _machine_box(root, f"drone-{variant}-left-wing", Vec3(-6.1 * scale, 0, -0.08), Vec3(6.8 * scale, 1.10 * scale, 0.38 * scale), color, 0.50, 0.16)
            _machine_box(root, f"drone-{variant}-right-wing", Vec3(6.1 * scale, 0, -0.08), Vec3(6.8 * scale, 1.10 * scale, 0.38 * scale), color, 0.50, 0.16)
            for sx in (-1, 1):
                for sy in (-1, 1):
                    _machine_box(root, f"drone-{variant}-rotor-{sx}-{sy}", Vec3(sx * 7.0 * scale, sy * 3.8 * scale, 0.15), Vec3(2.4 * scale, 2.4 * scale, 0.32 * scale), (1.0, 0.26, 0.08, 0.56), 0.36, 0.14)
            if variant == "jammer":
                _line_node(root, "drone-jammer-ring", (1.0, 0.10, 0.16, 0.72), [Vec3(math.cos(a) * 8.0 * scale, math.sin(a) * 8.0 * scale, -0.45) for a in [i * math.tau / 32.0 for i in range(33)]], False, max(1.0, getattr(self.cfg, "line_thickness", 1.6) * 0.18))
            else:
                _line_node(root, "drone-scan-cone", (1.0, 0.16, 0.08, 0.44), [Vec3(0, 0, -0.5), Vec3(-4.0 * scale, -1.8 * scale, -12.0), Vec3(0, 0, -0.5), Vec3(4.0 * scale, -1.8 * scale, -12.0)], False, max(1.0, getattr(self.cfg, "line_thickness", 1.6) * 0.16))
            if variant == "gunship":
                _machine_box(root, "drone-gunship-cannon-left", Vec3(-2.6 * scale, -4.4 * scale, -0.45 * scale), Vec3(0.52 * scale, 3.4 * scale, 0.52 * scale), hot, 0.70, 0.17, 1.2)
                _machine_box(root, "drone-gunship-cannon-right", Vec3(2.6 * scale, -4.4 * scale, -0.45 * scale), Vec3(0.52 * scale, 3.4 * scale, 0.52 * scale), hot, 0.70, 0.17, 1.2)

        elif kind == "mech":
            scale = 1.0
            if variant == "siege":
                scale = 1.28
            elif variant == "hunter":
                scale = 0.98
            elif variant == "colossus":
                scale = 1.72
            elif variant == "raptor":
                scale = 1.06
            elif variant == "rex":
                scale = 1.44
            elif variant == "rex_boss":
                scale = 1.88
            elif variant == "spider":
                scale = 1.38
            elif variant == "spider_boss":
                scale = 2.10
            hot = (1.0, 0.10, 0.03, 0.96)
            armor = _clamped_rgba(color, 0.66, 1.0)
            if variant in MECH_DINO_VARIANTS:
                # Dino/rex war machine: pitched torso, long head, tail ballast, huge legs.
                _machine_box(root, f"mech-{variant}-hips", Vec3(0, 0.9 * scale, 5.2 * scale), Vec3(7.2 * scale, 5.0 * scale, 4.4 * scale), armor, 0.66, 0.30)
                _machine_box(root, f"mech-{variant}-rib-core", Vec3(0, -1.8 * scale, 9.6 * scale), Vec3(8.8 * scale, 7.4 * scale, 6.2 * scale), armor, 0.68, 0.30)
                _machine_box(root, f"mech-{variant}-neck", Vec3(0, -6.0 * scale, 12.0 * scale), Vec3(3.8 * scale, 5.8 * scale, 3.4 * scale), armor, 0.62, 0.24)
                _machine_box(root, f"mech-{variant}-rex-head", Vec3(0, -10.8 * scale, 13.1 * scale), Vec3(5.8 * scale, 7.0 * scale, 3.2 * scale), armor, 0.72, 0.30)
                _machine_box(root, f"mech-{variant}-jaw", Vec3(0, -14.2 * scale, 11.7 * scale), Vec3(5.2 * scale, 3.0 * scale, 1.15 * scale), hot, 0.62, 0.16, 1.18)
                _machine_box(root, f"mech-{variant}-eye-strip", Vec3(0, -14.48 * scale, 13.85 * scale), Vec3(4.8 * scale, 0.38 * scale, 0.56 * scale), hot, 0.90, 0.14, 1.25)
                _machine_box(root, f"mech-{variant}-tail-a", Vec3(0, 7.8 * scale, 8.0 * scale), Vec3(3.8 * scale, 9.2 * scale, 2.0 * scale), armor, 0.52, 0.20)
                _machine_box(root, f"mech-{variant}-tail-b", Vec3(0, 15.2 * scale, 6.4 * scale), Vec3(2.2 * scale, 7.6 * scale, 1.4 * scale), hot, 0.42, 0.16)
                for side in (-1, 1):
                    _machine_box(root, f"rex-thigh-{side}", Vec3(side * 3.2 * scale, 0.6 * scale, 1.8 * scale), Vec3(2.6 * scale, 3.4 * scale, 6.2 * scale), armor, 0.60, 0.24)
                    _machine_box(root, f"rex-shin-{side}", Vec3(side * 3.9 * scale, -1.2 * scale, -3.1 * scale), Vec3(2.0 * scale, 2.6 * scale, 5.2 * scale), armor, 0.58, 0.22)
                    _machine_box(root, f"rex-claw-foot-{side}", Vec3(side * 4.2 * scale, -4.4 * scale, -6.1 * scale), Vec3(3.8 * scale, 6.2 * scale, 0.8 * scale), armor, 0.56, 0.18)
                    _machine_box(root, f"rex-arm-{side}", Vec3(side * 5.8 * scale, -6.2 * scale, 7.6 * scale), Vec3(1.2 * scale, 3.8 * scale, 1.1 * scale), hot, 0.50, 0.15)
                if variant == "rex_boss":
                    _line_node(root, "rex-boss-spine-crown", (1.0, 0.05, 0.02, 0.86), [Vec3(math.sin(i*.65)*4.7*scale, 2.8*scale - i*1.5*scale, 14.0*scale + math.sin(i*.9)*1.2*scale) for i in range(17)], False, max(1.0, getattr(self.cfg, "line_thickness", 1.6) * 0.28))
                    _machine_box(root, "rex-boss-chest-core", Vec3(0, -5.6 * scale, 9.0 * scale), Vec3(3.2 * scale, 1.0 * scale, 3.8 * scale), hot, 0.82, 0.18, 1.30)
            elif variant in MECH_SPIDER_VARIANTS:
                # Giant spider walker: wide armored body, eight walking legs, death beam array.
                _machine_box(root, f"spider-{variant}-abdomen", Vec3(0, 3.8 * scale, 7.0 * scale), Vec3(10.8 * scale, 8.8 * scale, 4.2 * scale), armor, 0.66, 0.30)
                _machine_box(root, f"spider-{variant}-thorax", Vec3(0, -3.8 * scale, 7.6 * scale), Vec3(9.2 * scale, 7.6 * scale, 4.8 * scale), armor, 0.70, 0.32)
                _machine_box(root, f"spider-{variant}-head", Vec3(0, -9.2 * scale, 7.5 * scale), Vec3(6.8 * scale, 4.6 * scale, 3.2 * scale), armor, 0.74, 0.28)
                _machine_box(root, "spider-death-eye", Vec3(0, -11.9 * scale, 8.05 * scale), Vec3(5.4 * scale, 0.42 * scale, 0.74 * scale), hot, 0.94, 0.16, 1.40)
                _machine_box(root, "spider-death-beam-cannon", Vec3(0, -14.4 * scale, 7.4 * scale), Vec3(1.3 * scale, 6.4 * scale, 1.3 * scale), hot, 0.82, 0.20, 1.25)
                for side in (-1, 1):
                    for n, yoff in enumerate((-6.2, -2.4, 1.6, 5.4)):
                        hip = Vec3(side * 4.9 * scale, yoff * scale, 5.8 * scale)
                        knee = Vec3(side * (9.8 + n*0.8) * scale, (yoff + (0.8 if n % 2 else -0.8)) * scale, 1.4 * scale)
                        foot = Vec3(side * (14.0 + n*1.0) * scale, (yoff + (2.2 if n % 2 else -2.2)) * scale, -3.3 * scale)
                        _machine_box(root, f"spider-leg-upper-{side}-{n}", (hip+knee)*0.5, Vec3(1.2*scale, 5.0*scale, 1.0*scale), armor, 0.50, 0.16)
                        _machine_box(root, f"spider-leg-lower-{side}-{n}", (knee+foot)*0.5, Vec3(1.0*scale, 5.8*scale, 0.88*scale), armor, 0.50, 0.16)
                        _line_node(root, f"spider-leg-joint-line-{side}-{n}", _clamped_rgba(color, 0.72, 1.05), [hip, knee, foot], False, max(1.0, getattr(self.cfg, "line_thickness", 1.6) * 0.22))
                if variant == "spider_boss":
                    for ring_r, zoff in ((13.5, 13.8), (8.5, 16.2)):
                        _line_node(root, f"spider-boss-death-ring-{ring_r}", (1.0, 0.04, 0.02, 0.82), [Vec3(math.cos(a)*ring_r*scale, math.sin(a)*ring_r*scale, zoff*scale) for a in [i*math.tau/48 for i in range(49)]], False, max(1.0, getattr(self.cfg, "line_thickness", 1.6) * 0.26))
            else:
                _machine_box(root, f"mech-{variant}-pelvis", Vec3(0, 0, 4.2 * scale), Vec3(6.6 * scale, 4.2 * scale, 3.2 * scale), armor, 0.62, 0.28)
                _machine_box(root, f"mech-{variant}-core", Vec3(0, 0, 9.6 * scale), Vec3(8.4 * scale, 5.4 * scale, 8.8 * scale), armor, 0.70, 0.32)
                _machine_box(root, f"mech-{variant}-head", Vec3(0, -0.35 * scale, 15.2 * scale), Vec3(5.6 * scale, 3.9 * scale, 2.5 * scale), armor, 0.72, 0.28)
                _machine_box(root, "mech-red-visor", Vec3(0, -2.45 * scale, 15.35 * scale), Vec3(4.4 * scale, 0.32 * scale, 0.62 * scale), hot, 0.88, 0.16, 1.2)
                _machine_box(root, "mech-reactor", Vec3(0, -2.95 * scale, 9.5 * scale), Vec3(2.5 * scale, 0.78 * scale, 3.2 * scale), hot, 0.76, 0.18, 1.2)
                for side in (-1, 1):
                    _machine_box(root, f"mech-shoulder-{side}", Vec3(side * 5.7 * scale, 0, 11.9 * scale), Vec3(2.4 * scale, 4.4 * scale, 2.5 * scale), armor, 0.60, 0.24)
                    _machine_box(root, f"mech-upper-arm-{side}", Vec3(side * 7.0 * scale, -0.20 * scale, 8.7 * scale), Vec3(1.6 * scale, 2.2 * scale, 4.2 * scale), armor, 0.56, 0.22)
                    _machine_box(root, f"mech-forearm-{side}", Vec3(side * 7.4 * scale, -0.52 * scale, 5.0 * scale), Vec3(1.9 * scale, 2.2 * scale, 3.9 * scale), armor, 0.56, 0.22)
                    _machine_box(root, f"mech-thigh-{side}", Vec3(side * 2.7 * scale, 0, 1.6 * scale), Vec3(2.1 * scale, 2.3 * scale, 4.4 * scale), armor, 0.58, 0.22)
                    _machine_box(root, f"mech-shin-{side}", Vec3(side * 3.5 * scale, 0, -2.2 * scale), Vec3(1.9 * scale, 2.0 * scale, 4.2 * scale), armor, 0.58, 0.22)
                    _machine_box(root, f"mech-foot-{side}", Vec3(side * 3.9 * scale, -0.35 * scale, -4.55 * scale), Vec3(3.5 * scale, 4.2 * scale, 0.75 * scale), armor, 0.55, 0.18)
                _machine_box(root, "mech-main-cannon", Vec3(0, -7.0 * scale, 10.8 * scale), Vec3(1.25 * scale, 10.0 * scale, 1.25 * scale), hot, 0.76, 0.20, 1.2)
                _machine_box(root, "mech-shoulder-rack-left", Vec3(-4.9 * scale, -1.1 * scale, 16.9 * scale), Vec3(3.2 * scale, 3.6 * scale, 1.1 * scale), hot, 0.55, 0.18)
                _machine_box(root, "mech-shoulder-rack-right", Vec3(4.9 * scale, -1.1 * scale, 16.9 * scale), Vec3(3.2 * scale, 3.6 * scale, 1.1 * scale), hot, 0.55, 0.18)
                if variant == "siege":
                    _machine_box(root, "siege-back-turret", Vec3(0, 3.4 * scale, 15.2 * scale), Vec3(4.8 * scale, 2.2 * scale, 3.2 * scale), hot, 0.52, 0.20)
                elif variant == "hunter":
                    for side in (-1, 1):
                        _machine_box(root, f"hunter-blade-{side}", Vec3(side * 9.3 * scale, -1.8 * scale, 6.8 * scale), Vec3(0.72 * scale, 5.4 * scale, 0.72 * scale), hot, 0.62, 0.16)
                if variant == "colossus":
                    _line_node(root, "colossus-warning-crown", (1.0, 0.05, 0.02, 0.84), [Vec3(math.cos(a) * 9.2 * scale, math.sin(a) * 9.2 * scale, 23.0 * scale) for a in [i * math.tau / 40.0 for i in range(41)]], False, max(1.0, getattr(self.cfg, "line_thickness", 1.6) * 0.24))
        else:
            _build_role_actor(root, kind, color, role, variant)
            if kind != "ally":
                _line_node(root, "hostile-eye", (1.0, 0.18, 0.08, 0.84), [Vec3(-0.8, 0, 5.15), Vec3(0.8, 0, 5.15)], False, max(1.0, getattr(self.cfg, "line_thickness", 1.6) * 0.22))
                if variant == "crawler":
                    _line_node(root, "crawler-extra-legs", color, [Vec3(-2.2, 0.6, 0.6), Vec3(-4.4, 1.7, -0.8), Vec3(2.2, 0.6, 0.6), Vec3(4.4, 1.7, -0.8), Vec3(-2.2, -0.6, 0.6), Vec3(-4.4, -1.7, -0.8), Vec3(2.2, -0.6, 0.6), Vec3(4.4, -1.7, -0.8)], False, max(1.0, getattr(self.cfg, "line_thickness", 1.6) * 0.18))
                elif variant == "shield":
                    _line_node(root, "shield-frame", (1.0, 0.38, 0.12, 0.62), [Vec3(-2.6, -1.8, 1.0), Vec3(2.6, -1.8, 1.0), Vec3(2.6, -1.8, 5.8), Vec3(-2.6, -1.8, 5.8)], True, max(1.0, getattr(self.cfg, "line_thickness", 1.6) * 0.20))
                elif variant == "assault":
                    _line_node(root, "assault-back-rig", (1.0, 0.18, 0.08, 0.78), [Vec3(-1.8, 0.7, 4.8), Vec3(-3.6, 1.1, 6.8), Vec3(1.8, 0.7, 4.8), Vec3(3.6, 1.1, 6.8)], False, max(1.0, getattr(self.cfg, "line_thickness", 1.6) * 0.20))
            else:
                _line_node(root, "ally-id-halo", _clamped_rgba(color, 0.64, 1.2), [Vec3(math.cos(a) * 5.2, math.sin(a) * 5.2, 6.4) for a in [i * math.tau / 28.0 for i in range(29)]], False, max(1.0, getattr(self.cfg, "line_thickness", 1.6) * 0.14))
        actor["node"] = root
        actor["role"] = role
        actor["variant"] = variant
        return root

    def _set_actor_pos(actor: dict):
        node = actor.get("node")
        if node is None or node.isEmpty():
            return
        if bool(actor.get("uses_existing_world_bot", False)):
            # Sable is the live region bot.  Do not move or duplicate her model;
            # just read her current node position for beam aiming.
            try:
                actor["pos"] = Vec3(node.getPos())
            except Exception:
                pass
            return
        pos = Vec3(actor.get("pos", Vec3()))
        node.setPos(pos)
        try:
            node.setH(float(actor.get("yaw", 0.0)))
        except Exception:
            pass

    def _urban_play_battle_sfx(self, cue: str = "fire", volume: float = 0.18, cooldown: float = AMBIENT_BATTLE_SFX_MIN_INTERVAL):
        """Low-duty battlefield SFX relay using HoloVerse-owned audio.

        The runtime intentionally does not own a mixer.  It asks the shared
        audio manager to play event cues so the global volume sliders, cleanup,
        and Vector Wars fallback SFX from the previous audio pass continue to
        work for Urban without adding new generated assets.
        """
        now = time.time()
        if now < float(getattr(self, "urban_battlefield_next_sfx_at", 0.0) or 0.0):
            return False
        audio = getattr(self, "audio", None)
        if audio is None:
            return False
        cue = str(cue or "fire").lower()
        filename = "fire.mp3"
        if cue in {"rocket", "missile", "airstrike", "drop"}:
            filename = "rocketfire.mp3"
        elif cue in {"hit", "impact", "destroy", "explosion"}:
            filename = "hit.mp3"
        try:
            audio.play(filename, bus="sfx", volume=max(0.02, min(0.42, float(volume))))
            self.urban_battlefield_next_sfx_at = now + max(0.6, float(cooldown))
            return True
        except Exception:
            return False

    def _cleanup_urban_battlefield_events(self, dt: float):
        events = []
        for ev in list(getattr(self, "urban_battlefield_events", []) or []):
            ttl = float(ev.get("ttl", 0.0)) - max(0.001, float(dt or 0.016))
            nodes = list(ev.get("nodes", []) or [])
            if ttl <= 0.0:
                for node in nodes:
                    try:
                        if node is not None and not node.isEmpty():
                            node.removeNode()
                    except Exception:
                        pass
            else:
                ev["ttl"] = ttl
                events.append(ev)
        self.urban_battlefield_events = events[-AMBIENT_BATTLE_MAX_EVENTS:]

    def _spawn_ambient_battlefield_event(self, root, now: float):
        if root is None or root.isEmpty():
            return False
        if len(list(getattr(self, "urban_battlefield_events", []) or [])) >= AMBIENT_BATTLE_MAX_EVENTS:
            return False
        seed = int(getattr(self, "urban_battlefield_event_seed", 0) or 0) + 1
        self.urban_battlefield_event_seed = seed
        rng = random.Random(0xA11CE + seed * 113)
        player = Vec3(getattr(self, "player_pos", Vec3(0, 0, 0)))
        focus = Vec3(getattr(self, "urban_battlefield_focus_pos", player + Vec3(0, 120, 12)))
        try:
            yaw = math.radians(float(getattr(self, "player_yaw", 0.0)))
        except Exception:
            yaw = 0.0
        forward = Vec3(math.sin(yaw), math.cos(yaw), 0.0)
        if forward.lengthSquared() < 0.001:
            forward = Vec3(0, 1, 0)
        forward.normalize()
        right = Vec3(forward.y, -forward.x, 0.0)
        # Push events away from the player's feet and into separate street pockets.
        center = focus + forward * rng.uniform(18.0, 120.0) + right * rng.choice((-1.0, 1.0)) * rng.uniform(80.0, 190.0)
        center.z = _floor_z(self, center.x, center.y) + 1.2
        kind = rng.choice(("airstrike", "drop", "emp"))
        nodes = []
        if kind == "airstrike":
            for lane in range(3):
                off = right * ((lane - 1) * 18.0) + forward * rng.uniform(-22.0, 22.0)
                start = center + off + Vec3(rng.uniform(-20.0, 20.0), rng.uniform(-20.0, 20.0), 84.0)
                end = center + off + Vec3(0, 0, 2.5)
                nodes.append(_line_node(root, f"urban-ambient-airstrike-{seed}-{lane}", (1.0, 0.20, 0.04, 0.72), [start, end], False, max(1.0, getattr(self.cfg, "line_thickness", 1.6) * 0.42)))
            nodes.append(_line_node(root, f"urban-ambient-airstrike-ground-{seed}", (1.0, 0.45, 0.12, 0.48), [center + Vec3(math.cos(a) * 26.0, math.sin(a) * 26.0, 0.5) for a in [i * math.tau / 32 for i in range(33)]], False, max(1.0, getattr(self.cfg, "line_thickness", 1.6) * 0.18)))
            _urban_play_battle_sfx(self, "airstrike", 0.22, 3.2)
            ttl = 1.85
        elif kind == "drop":
            pod = root.attachNewNode(f"urban-ambient-drop-pod-{seed}")
            pod.setTransparency(TransparencyAttrib.MAlpha)
            nodes.append(pod)
            _machine_box(pod, "drop-pod-core", Vec3(0, 0, 7.5), Vec3(7.5, 7.5, 15.0), (1.0, 0.18, 0.06, 0.64), 0.52, 0.20)
            _machine_box(pod, "drop-pod-hot-core", Vec3(0, -3.9, 7.8), Vec3(3.4, 0.75, 9.0), (1.0, 0.05, 0.02, 0.82), 0.70, 0.18, 1.20)
            pod.setPos(center + Vec3(0, 0, -0.2))
            nodes.append(_line_node(root, f"urban-ambient-drop-ring-{seed}", (1.0, 0.12, 0.04, 0.62), [center + Vec3(math.cos(a) * 34.0, math.sin(a) * 34.0, 0.65) for a in [i * math.tau / 40 for i in range(41)]], False, max(1.0, getattr(self.cfg, "line_thickness", 1.6) * 0.22)))
            _urban_play_battle_sfx(self, "drop", 0.18, 3.8)
            ttl = 3.2
        else:
            for ring_r, zoff in ((24.0, 3.0), (42.0, 7.0), (62.0, 12.5)):
                nodes.append(_line_node(root, f"urban-ambient-emp-{seed}-{ring_r}", (0.18, 0.92, 1.0, 0.48), [center + Vec3(math.cos(a) * ring_r, math.sin(a) * ring_r, zoff + math.sin(a * 3.0) * 2.5) for a in [i * math.tau / 48 for i in range(49)]], False, max(1.0, getattr(self.cfg, "line_thickness", 1.6) * 0.17)))
            for n in range(5):
                a = rng.random() * math.tau
                p0 = center + Vec3(math.cos(a) * rng.uniform(12.0, 44.0), math.sin(a) * rng.uniform(12.0, 44.0), rng.uniform(4.0, 10.0))
                p1 = center + Vec3(math.cos(a + 0.8) * rng.uniform(30.0, 68.0), math.sin(a + 0.8) * rng.uniform(30.0, 68.0), rng.uniform(10.0, 22.0))
                nodes.append(_line_node(root, f"urban-ambient-emp-arc-{seed}-{n}", (0.34, 0.95, 1.0, 0.62), [p0, p1], False, max(1.0, getattr(self.cfg, "line_thickness", 1.6) * 0.18)))
            _urban_play_battle_sfx(self, "hit", 0.14, 3.0)
            ttl = 2.6
        self.urban_battlefield_events = list(getattr(self, "urban_battlefield_events", []) or []) + [{"nodes": nodes, "ttl": ttl, "kind": kind}]
        self.urban_battlefield_next_event_at = now + rng.uniform(AMBIENT_BATTLE_EVENT_MIN_INTERVAL, AMBIENT_BATTLE_EVENT_MAX_INTERVAL)
        return True

    def _update_urban_battlefield_ambient(self, dt=0.0, root=None):
        if bool(getattr(self, "urban_warzone_active", False)):
            return
        if root is None:
            root = getattr(self, "urban_battlefield_root", None)
        if root is None or root.isEmpty():
            return
        dt = max(0.001, min(0.05, float(dt or 0.016)))
        now = time.time()
        actors = [a for a in list(getattr(self, "urban_battlefield_actors", []) or []) if a.get("node") is not None and not a.get("node").isEmpty()]
        if not actors:
            return
        player = Vec3(getattr(self, "player_pos", Vec3(0, 0, 0)))
        focus = Vec3(getattr(self, "urban_battlefield_focus_pos", player + Vec3(0, 96, 8)))
        enemies = [a for a in actors if str(a.get("faction")) == "enemy"]
        allies = [a for a in actors if str(a.get("faction")) == "ally"]
        for actor in actors:
            pos = Vec3(actor.get("pos", focus))
            faction = str(actor.get("faction") or "enemy")
            opponents = enemies if faction == "ally" else allies
            target = min(opponents, key=lambda e: (Vec3(e.get("pos", focus)) - pos).lengthSquared()) if opponents else None
            home = Vec3(actor.get("home", focus))
            seed = float(actor.get("seed", 0.0) or 0.0)
            desired = home + Vec3(math.sin(now * 0.36 + seed) * 24.0, math.cos(now * 0.31 + seed * 0.37) * 24.0, 0.0)
            if target is not None:
                tpos = Vec3(target.get("pos", focus))
                away = pos - tpos
                away.z = 0
                if away.lengthSquared() > 0.001:
                    away.normalize()
                hold = 70.0 if str(actor.get("role")) == "sniper" else (52.0 if str(actor.get("kind")) == "mech" else 38.0)
                desired = tpos + away * hold
            # Keep ambient actors spaced in the street pocket and away from the player.
            to_focus = desired - focus
            to_focus.z = 0
            if to_focus.length() > 190.0:
                to_focus.normalize()
                desired = focus + to_focus * 190.0
            from_player = desired - player
            from_player.z = 0
            if from_player.length() < 46.0 and from_player.lengthSquared() > 0.001:
                from_player.normalize()
                desired = player + from_player * 46.0
            move = desired - pos
            move.z = 0
            if move.length() > 2.0:
                move.normalize()
                pos += move * float(actor.get("speed", 10.0) or 10.0) * dt
            floor = _floor_z(self, pos.x, pos.y)
            if str(actor.get("kind")) == "drone":
                pos.z = floor + 22.0 + math.sin(now * 1.1 + seed) * 5.5
            else:
                pos.z = floor + (0.9 if str(actor.get("kind")) == "mech" else 0.75)
            if target is not None:
                tpos = Vec3(target.get("pos", focus))
                direction = tpos - pos
                direction.z = 0
                if direction.lengthSquared() > 0.001:
                    direction.normalize()
                    actor["yaw"] = math.degrees(math.atan2(direction.x, direction.y))
                cd = float(actor.get("cooldown", 0.0) or 0.0) - dt
                if cd <= 0.0 and (tpos - pos).length() < 230.0:
                    start = pos + Vec3(0, 0, _actor_aim_height(actor))
                    end = tpos + Vec3(0, 0, _actor_aim_height(target))
                    color = _actor_color("ally", str(actor.get("name", "")), str(actor.get("role", ""))) if faction == "ally" else (1.0, 0.12, 0.04, 0.58)
                    node = _line_node(root, f"urban-ambient-live-shot-{int(seed)}-{int(now * 10)}", color, [start, end], False, max(1.0, getattr(self.cfg, "line_thickness", 1.6) * (0.25 if faction == "ally" else 0.30)))
                    self.urban_battlefield_events = list(getattr(self, "urban_battlefield_events", []) or []) + [{"nodes": [node], "ttl": 0.22, "kind": "crossfire"}]
                    _urban_play_battle_sfx(self, "fire", 0.10 if faction == "ally" else 0.13, 1.1)
                    actor["cooldown"] = 1.05 + (seed % 7.0) * 0.18
                else:
                    actor["cooldown"] = cd
            actor["pos"] = pos
            actor["ai_state"] = "ambient_live_crossfire"
            _set_actor_pos(actor)
        _cleanup_urban_battlefield_events(self, dt)
        if now >= float(getattr(self, "urban_battlefield_next_event_at", 0.0) or 0.0):
            _spawn_ambient_battlefield_event(self, root, now)

    def _warzone_root(self):
        parent = _urban_runtime_parent(self)
        root = getattr(self, "urban_warzone_root", None)
        recreate = root is None or root.isEmpty()
        if not recreate:
            try:
                recreate = root.getParent() != parent
            except Exception:
                recreate = False
        if recreate:
            try:
                if root is not None and not root.isEmpty():
                    root.removeNode()
            except Exception:
                pass
            self.urban_warzone_root = parent.attachNewNode("urban-warzone-arena-runtime")
            self.urban_warzone_root.setTransparency(TransparencyAttrib.MAlpha)
        return self.urban_warzone_root

    def _find_named_region_bot_node(self, bot_name: str):
        wanted = str(bot_name or "").strip().lower()
        for node in list(getattr(self, "named_region_bot_nodes", []) or []):
            try:
                if node is not None and not node.isEmpty() and str(node.getPythonTag("named_region_bot_name") or "").strip().lower() == wanted:
                    return node
            except Exception:
                continue
        return None

    def _attach_sable_mounted_beams(self, node):
        if node is None or node.isEmpty():
            return
        try:
            if bool(node.getPythonTag("urban_warzone_sable_beams_mounted")):
                return
        except Exception:
            pass
        try:
            mount = node.attachNewNode("sable-mounted-beam-rig")
            mount.setTransparency(TransparencyAttrib.MAlpha)
            hot = (1.0, 0.10, 0.04, 0.92)
            glow = (1.0, 0.26, 0.12, 0.68)
            # Local-space shoulder emitters: mounted to the existing Sable guide,
            # not a new duplicate model.
            for side in (-1.0, 1.0):
                _machine_box(mount, f"sable-mounted-emitter-{side:+.0f}", Vec3(side * 1.15, -0.42, 5.35), Vec3(0.32, 0.42, 0.54), hot, 0.70, 0.18, 1.25)
                _line_node(mount, f"sable-mounted-ready-beam-{side:+.0f}", glow, [Vec3(side * 1.15, -0.72, 5.35), Vec3(side * 1.15, -4.80, 5.35)], False, max(1.0, getattr(self.cfg, "line_thickness", 1.6) * 0.20))
            node.setPythonTag("urban_warzone_sable_beams_mounted", True)
            node.setPythonTag("urban_warzone_combat_actor", True)
        except Exception as exc:
            print(f"urban_warzone_sable_beam_mount_warning:{exc}")

    def _sync_sable_battle_actor(self, create: bool = False):
        node = _find_named_region_bot_node(self, SABLE_BATTLE_OWNER)
        if node is None or node.isEmpty():
            return None
        _attach_sable_mounted_beams(self, node)
        try:
            pos = node.getPos(self.render)
        except Exception:
            pos = node.getPos()
        allies = list(getattr(self, "urban_warzone_allies", []) or [])
        for ally in allies:
            if str(ally.get("name")) == SABLE_BATTLE_OWNER:
                ally["node"] = node
                ally["pos"] = Vec3(pos)
                ally["uses_existing_world_bot"] = True
                ally["hp"] = max(float(ally.get("hp", 0.0) or 0.0), 1.0)
                ally["max_hp"] = max(float(ally.get("max_hp", 150.0) or 150.0), 150.0)
                return ally
        if not create:
            return None
        actor = {
            "kind": "ally", "name": SABLE_BATTLE_OWNER, "role": BOT_ROLE_MAP.get(SABLE_BATTLE_OWNER, "sentinel"),
            "variant": "mounted_world_bot", "pos": Vec3(pos), "hp": 150.0, "max_hp": 150.0,
            "cooldown": 0.15, "seed": 7011, "yaw": 0.0, "summoned": False,
            "faction": "ally", "uses_existing_world_bot": True, "node": node,
            "ai_boost_until": 0.0, "ai_boost_cd": 0.0, "ai_perch_until": 0.0, "ai_target_z": 0.0,
            "ai_state": "sable_mounted_beams",
        }
        allies.insert(0, actor)
        self.urban_warzone_allies = allies
        return actor

    def _ally_spawn_position(self, bot: str, idx: int):
        p = Vec3(getattr(self, "player_pos", Vec3()))
        anchors = list(getattr(self, "urban_warzone_spawn_anchors", []) or [])
        if anchors:
            # Use distributed arena anchors so the friend bots enter around the
            # battlefield instead of stacking on the player or on Sable.
            ranked = []
            for anchor in anchors:
                try:
                    pos = Vec3(anchor.get("pos", Vec3()))
                    pos.z = _floor_z(self, pos.x, pos.y) + 0.8
                    dist = (pos - p).length()
                    if 35.0 <= dist <= 260.0:
                        ranked.append((dist, pos))
                except Exception:
                    continue
            if ranked:
                ranked.sort(key=lambda item: item[0])
                return Vec3(ranked[(idx * 3 + len(str(bot))) % len(ranked)][1])
        ang = math.tau * (idx / max(1, len(BATTLE_REINFORCEMENT_BOTS))) + 0.34
        radius = 38.0 + (idx % 4) * 13.0
        pos = Vec3(p.x + math.cos(ang) * radius, p.y + math.sin(ang) * radius, _floor_z(self, p.x, p.y) + 0.8)
        return pos

    def _reset_allies_for_wave_clear(self, reason: str = "wave_clear"):
        _sync_sable_battle_actor(self, create=True)
        allies = list(getattr(self, "urban_warzone_allies", []) or [])
        existing = {str(a.get("name")): a for a in allies}
        for bot in BATTLE_REINFORCEMENT_BOTS:
            ally = existing.get(bot)
            if ally is None:
                ally = _spawn_ally(self, bot, len(allies))
                allies.append(ally)
                existing[bot] = ally
            else:
                try:
                    node = ally.get("node")
                    if node is None or node.isEmpty():
                        _build_actor_node(self, _warzone_root(self), ally)
                except Exception:
                    _build_actor_node(self, _warzone_root(self), ally)
                ally["hp"] = float(ally.get("max_hp", 110.0) or 110.0)
                ally["pos"] = _ally_spawn_position(self, bot, len(allies))
                ally["cooldown"] = 0.35
                ally["ai_state"] = str(reason)
                _set_actor_pos(ally)
        self.urban_warzone_allies = allies

    def _destroy_warzone_visuals(self):
        for attr in ("urban_warzone_root", "urban_warzone_ui_root", "urban_warzone_intro_root"):
            try:
                node = getattr(self, attr, None)
                if node is not None and not node.isEmpty():
                    node.removeNode()
            except Exception:
                pass
            setattr(self, attr, None)
        self.urban_warzone_ui_panel = None
        self.urban_warzone_ui_title = None
        self.urban_warzone_ui_status = None
        self.urban_warzone_ui_help = None
        self.urban_warzone_enemies = []
        self.urban_warzone_allies = []
        self.urban_warzone_beams = []
        self.urban_warzone_spawn_anchors = []
        self.urban_warzone_power_nodes = []
        self.urban_warzone_pockets = []
        self.urban_warzone_capture_posts = []
        self.urban_warzone_bomb_sites = []
        self.urban_warzone_weapon_nodes = []

    def _pick_spawn_anchor(self, kind: str, idx: int, wave: int, min_dist: float = 72.0):
        anchors = list(getattr(self, "urban_warzone_spawn_anchors", []) or [])
        if not anchors:
            return None
        p = Vec3(getattr(self, "player_pos", Vec3()))
        ranked = []
        for a in anchors:
            pos = Vec3(a.get("pos", Vec3()))
            d = (pos - p).length()
            score = d + (35.0 if str(a.get("kind")) in {kind, "mixed"} else 0.0)
            if d >= min_dist:
                ranked.append((score, a))
        if not ranked:
            ranked = [((Vec3(a.get("pos", Vec3())) - p).length(), a) for a in anchors]
        ranked.sort(key=lambda x: x[0], reverse=True)
        return ranked[(idx + wave * 3) % max(1, len(ranked))][1]


    def _draw_4d_spawn_effect(self, pos: Vec3, kind: str = "robot", idx: int = 0, wave: int = 1):
        root = _warzone_root(self)
        base = Vec3(pos)
        color = (1.0, 0.12, 0.04, 0.86) if kind != "drone" else (1.0, 0.50, 0.12, 0.82)
        if kind == "mech":
            color = (1.0, 0.04, 0.02, 0.94)
        r = 9.0 if kind == "robot" else (12.0 if kind == "drone" else 20.0)
        z = base.z + (2.4 if kind != "drone" else -10.0)
        ring1 = [Vec3(base.x + math.cos(a) * r, base.y + math.sin(a) * r, z + math.sin(a * 2.0) * 2.0) for a in [n * math.tau / 36.0 for n in range(37)]]
        ring2 = [Vec3(base.x + math.cos(a) * r * 0.62, base.y + math.sin(a) * r * 0.62, z + 7.0 + math.cos(a * 3.0) * 1.6) for a in [n * math.tau / 32.0 for n in range(33)]]
        _line_node(root, f"urban-4d-teleport-ring-a-{wave}-{idx}-{kind}", color, ring1, False, max(1.0, getattr(self.cfg, "line_thickness", 1.6) * 0.34))
        _line_node(root, f"urban-4d-teleport-ring-b-{wave}-{idx}-{kind}", color, ring2, False, max(1.0, getattr(self.cfg, "line_thickness", 1.6) * 0.28))
        _line_node(root, f"urban-4d-teleport-slice-{wave}-{idx}-{kind}", color, [base + Vec3(-r, 0, 2), base + Vec3(r, 0, 11), base + Vec3(0, -r, 5), base + Vec3(0, r, 8), base + Vec3(-r*.6, -r*.6, 14), base + Vec3(r*.6, r*.6, 1)], False, max(1.0, getattr(self.cfg, "line_thickness", 1.6) * 0.30))
        self.urban_warzone_beams.append({"node": root.getChild(root.getNumChildren()-1) if root.getNumChildren() else None, "ttl": 1.15})

    def _nearest_bomb_to_ray(self, start: Vec3, forward: Vec3):
        if forward.lengthSquared() > 0.001:
            forward.normalize()
        best = None; best_score = 999999.0
        for bomb in list(getattr(self, "urban_warzone_bomb_sites", []) or []):
            if not bool(bomb.get("armed", True)):
                continue
            pos = Vec3(bomb.get("pos", Vec3()))
            to = pos - start
            dist = to.length()
            if dist <= 0.001 or dist > 220.0:
                continue
            aim = Vec3(to); aim.normalize()
            dot = aim.dot(forward)
            if dot < 0.92:
                continue
            score = dist * (1.0 + (1.0 - dot) * 10.0)
            if score < best_score:
                best_score = score; best = bomb
        return best

    def _detonate_bomb_site(self, bomb: dict, source: str = "arena"):
        if not bool(bomb.get("armed", True)):
            return False
        now = time.time()
        if now < float(bomb.get("cooldown", 0.0) or 0.0):
            return False
        pos = Vec3(bomb.get("pos", Vec3()))
        radius = float(bomb.get("radius", BOMB_BLAST_RADIUS) or BOMB_BLAST_RADIUS)
        root = _warzone_root(self)
        _line_node(root, f"urban-bomb-blast-ring-{int(now*10)}", (1.0, 0.20, 0.04, 0.88), [Vec3(pos.x + math.cos(a) * radius, pos.y + math.sin(a) * radius, pos.z + 1.5) for a in [n * math.tau / 48.0 for n in range(49)]], False, max(1.0, getattr(self.cfg, "line_thickness", 1.6) * 0.48))
        damaged = 0
        for enemy in list(getattr(self, "urban_warzone_enemies", []) or []):
            if float(enemy.get("hp", 0.0)) <= 0.0:
                continue
            epos = Vec3(enemy.get("pos", Vec3()))
            d = (epos - pos).length()
            if d <= radius:
                scale = 1.0 - min(0.92, d / max(1.0, radius))
                dmg = 70.0 + 130.0 * scale
                if str(enemy.get("kind")) == "mech":
                    dmg *= 1.35
                enemy["hp"] = float(enemy.get("hp", 0.0)) - dmg
                enemy["last_damage_source"] = str(source or "bomb")
                _add_beam(self, pos + Vec3(0,0,3.0), epos + Vec3(0,0,5.0), (1.0, 0.32, 0.06, 0.74), 0.22, "bomb-frag")
                damaged += 1
        p = Vec3(getattr(self, "player_pos", Vec3()))
        if (p - pos).length() <= radius * 0.55:
            self.urban_warzone_player_hp = max(0.0, float(getattr(self, "urban_warzone_player_hp", 100.0)) - 8.0)
        bomb["armed"] = False
        bomb["cooldown"] = now + 14.0
        self.urban_warzone_bombs_detonated = int(getattr(self, "urban_warzone_bombs_detonated", 0) or 0) + 1
        bonus = 90 + damaged * 65
        self.urban_warzone_score = int(getattr(self, "urban_warzone_score", 0) or 0) + bonus
        self.urban_warzone_points_this_run = int(getattr(self, "urban_warzone_points_this_run", 0) or 0) + bonus
        self.center_hint["text"] = f"URBAN WARZONE // BOMB DETONATED // {damaged} TARGETS +{bonus}"
        return True

    def _update_capture_posts(self, dt: float):
        posts = list(getattr(self, "urban_warzone_capture_posts", []) or [])
        if not posts:
            return
        player = Vec3(getattr(self, "player_pos", Vec3()))
        allies = [Vec3(a.get("pos", Vec3())) for a in _alive_allies(self)]
        enemies = [Vec3(e.get("pos", Vec3())) for e in _alive_enemies(self)]
        for post in posts:
            pos = Vec3(post.get("pos", Vec3()))
            radius = float(post.get("radius", CAPTURE_POST_RADIUS) or CAPTURE_POST_RADIUS)
            ally_presence = 1 if (player - pos).length() <= radius else 0
            ally_presence += sum(1 for a in allies if (a - pos).length() <= radius)
            enemy_presence = sum(1 for e in enemies if (e - pos).length() <= radius)
            progress = float(post.get("capture", 0.0) or 0.0)
            if ally_presence and enemy_presence == 0:
                progress = min(1.0, progress + dt * (0.10 + 0.035 * ally_presence))
            elif enemy_presence and ally_presence == 0:
                progress = max(0.0, progress - dt * (0.08 + 0.035 * enemy_presence))
            post["capture"] = progress
            if progress >= 1.0 and post.get("owner") != "ally":
                post["owner"] = "ally"
                self.urban_warzone_capture_score = int(getattr(self, "urban_warzone_capture_score", 0) or 0) + 1
                bonus = 350 + int(getattr(self, "urban_warzone_wave", 1) or 1) * 40
                self.urban_warzone_score = int(getattr(self, "urban_warzone_score", 0) or 0) + bonus
                self.urban_warzone_points_this_run = int(getattr(self, "urban_warzone_points_this_run", 0) or 0) + bonus
                self.center_hint["text"] = f"URBAN WARZONE // CAPTURE POST SECURED +{bonus}"
                _add_beam(self, pos + Vec3(0,0,2), pos + Vec3(0,0,30), (0.12, 1.0, 0.82, 0.92), 0.7, "capture-secure")

    def _update_bomb_sites(self, dt: float):
        now = time.time()
        player = Vec3(getattr(self, "player_pos", Vec3()))
        for bomb in list(getattr(self, "urban_warzone_bomb_sites", []) or []):
            if not bool(bomb.get("armed", True)):
                if now >= float(bomb.get("cooldown", 0.0) or 0.0):
                    bomb["armed"] = True
                continue
            pos = Vec3(bomb.get("pos", Vec3()))
            if (player - pos).length() < 16.0:
                continue
            near_enemies = [e for e in _alive_enemies(self) if (Vec3(e.get("pos", Vec3())) - pos).length() <= BOMB_ARM_RADIUS]
            if len(near_enemies) >= 3:
                _detonate_bomb_site(self, bomb, source="bomb")

    def _update_arena_weapons(self, dt: float):
        now = time.time()
        player = Vec3(getattr(self, "player_pos", Vec3()))
        for node in list(getattr(self, "urban_warzone_weapon_nodes", []) or []):
            pos = Vec3(node.get("pos", Vec3()))
            if (player - pos).length() <= float(node.get("radius", 30.0) or 30.0):
                mode = str(node.get("weapon") or "pulse_rifle")
                if mode in ARENA_WEAPON_PROFILES:
                    self.urban_warzone_weapon_mode = mode
                    self.urban_warzone_weapon_until = now + 18.0
                    title = ARENA_WEAPON_PROFILES[mode].get("title", mode.upper())
                    self.center_hint["text"] = f"URBAN WARZONE // ARENA WEAPON ONLINE: {title}"
                break
        if now > float(getattr(self, "urban_warzone_weapon_until", 0.0) or 0.0):
            self.urban_warzone_weapon_mode = "pulse_rifle"

    def _current_weapon_profile(self):
        mode = str(getattr(self, "urban_warzone_weapon_mode", "pulse_rifle") or "pulse_rifle")
        return dict(ARENA_WEAPON_PROFILES.get(mode, ARENA_WEAPON_PROFILES["pulse_rifle"]))

    def _flat_len(vec: Vec3) -> float:
        try:
            return math.sqrt(float(vec.x) * float(vec.x) + float(vec.y) * float(vec.y))
        except Exception:
            return 0.0

    def _flat_norm(vec: Vec3) -> Vec3:
        v = Vec3(float(vec.x), float(vec.y), 0.0)
        if v.lengthSquared() > 0.0001:
            v.normalize()
        return v

    def _actor_aim_height(actor: dict) -> float:
        kind = str(actor.get("kind") or "robot")
        variant = str(actor.get("variant") or "")
        if kind == "mech":
            if variant == "spider_boss": return 16.0
            if variant == "rex_boss": return 20.0
            if variant == "colossus": return 17.0
            if variant in {"rex", "raptor"}: return 15.5
            if variant == "spider": return 12.5
            return 11.5
        if kind == "drone":
            return 0.2
        if kind == "ally":
            return 5.0
        return 4.6

    def _actor_forward(actor: dict) -> Vec3:
        yaw = math.radians(float(actor.get("yaw", 0.0) or 0.0))
        f = Vec3(math.sin(yaw), math.cos(yaw), 0.0)
        if f.lengthSquared() > 0.001:
            f.normalize()
        return f

    def _segment_distance_2d(a: Vec3, b: Vec3, p: Vec3):
        ax, ay = float(a.x), float(a.y)
        bx, by = float(b.x), float(b.y)
        px, py = float(p.x), float(p.y)
        vx, vy = bx - ax, by - ay
        wx, wy = px - ax, py - ay
        denom = vx * vx + vy * vy
        if denom <= 0.0001:
            return math.sqrt((px - ax) ** 2 + (py - ay) ** 2), 0.0
        t = max(0.0, min(1.0, (wx * vx + wy * vy) / denom))
        qx, qy = ax + vx * t, ay + vy * t
        return math.sqrt((px - qx) ** 2 + (py - qy) ** 2), t

    def _ai_obstacles(self):
        items = []
        try:
            items.extend(list(getattr(self, "urban_ai_obstacles", []) or []))
        except Exception:
            pass
        try:
            for post in list(getattr(self, "urban_warzone_capture_posts", []) or []):
                items.append({"pos": Vec3(post.get("pos", Vec3())), "radius": 8.0, "height": 18.0, "kind": "capture_post"})
            for bomb in list(getattr(self, "urban_warzone_bomb_sites", []) or []):
                if bool(bomb.get("armed", True)):
                    items.append({"pos": Vec3(bomb.get("pos", Vec3())), "radius": 7.0, "height": 5.0, "kind": "bomb_site"})
            for node in list(getattr(self, "urban_warzone_weapon_nodes", []) or []):
                items.append({"pos": Vec3(node.get("pos", Vec3())), "radius": 7.0, "height": 7.0, "kind": "weapon_node"})
        except Exception:
            pass
        return items[:AI_MAX_OBSTACLE_CHECKS]

    def _has_clean_firing_lane(self, shooter: dict, target_pos: Vec3, *, friends=None, enemies=None, ignore=None) -> bool:
        """Return True when the aim lane is believable, not shooting through props/allies."""
        try:
            self.urban_ai_los_checks = int(getattr(self, "urban_ai_los_checks", 0) or 0) + 1
        except Exception:
            pass
        ignore = ignore or set()
        start = Vec3(shooter.get("pos", Vec3())) + Vec3(0, 0, _actor_aim_height(shooter))
        end = Vec3(target_pos)
        lane_len = (end - start).length()
        if lane_len < 0.01:
            return False
        # The actor turns before firing. If the current aim cone is too far off,
        # it can reposition but should not instantly shoot backward.
        flat_to = Vec3(end.x - start.x, end.y - start.y, 0.0)
        if flat_to.lengthSquared() > 0.001:
            flat_to.normalize()
            if _actor_forward(shooter).dot(flat_to) < AI_AIM_CONE_DOT:
                try: self.urban_ai_blocked_shots = int(getattr(self, "urban_ai_blocked_shots", 0) or 0) + 1
                except Exception: pass
                shooter["last_los_clear"] = False
                shooter["ai_state"] = "turning"
                return False
        start_floor = _floor_z(self, start.x, start.y)
        # Visible urban objects block believable fire lanes, unless the shot is clearly above them.
        for obs in _ai_obstacles(self):
            op = Vec3(obs.get("pos", Vec3()))
            d, t = _segment_distance_2d(start, end, op)
            if t <= 0.08 or t >= 0.94:
                continue
            radius = float(obs.get("radius", 6.0) or 6.0) + AI_LINE_OF_SIGHT_WIDTH
            if d > radius:
                continue
            height = float(obs.get("height", 8.0) or 8.0)
            # If both start and end are high above the obstacle, a jetpack/perch shot is legal.
            los_z = float(start.z) + (float(end.z) - float(start.z)) * t
            if los_z > float(op.z) + height + 3.5:
                continue
            try: self.urban_ai_blocked_shots = int(getattr(self, "urban_ai_blocked_shots", 0) or 0) + 1
            except Exception: pass
            shooter["last_los_clear"] = False
            shooter["ai_state"] = "blocked_los"
            return False
        # Friend/own-faction bodies in the lane block smart fire. This prevents ally dogpiles.
        blockers = []
        if friends:
            blockers.extend(friends)
        if enemies and str(shooter.get("faction")) == "enemy":
            blockers.extend(enemies)
        for actor in blockers:
            if actor is shooter or id(actor) in ignore or float(actor.get("hp", 0.0)) <= 0.0:
                continue
            ap = Vec3(actor.get("pos", Vec3()))
            d, t = _segment_distance_2d(start, end, ap)
            if 0.10 < t < 0.90 and d < (8.0 if str(actor.get("kind")) == "mech" else 4.5):
                try: self.urban_ai_blocked_shots = int(getattr(self, "urban_ai_blocked_shots", 0) or 0) + 1
                except Exception: pass
                shooter["last_los_clear"] = False
                shooter["ai_state"] = "friendly_in_lane" if str(shooter.get("faction")) == "ally" else "unit_in_lane"
                return False
        try: self.urban_ai_clear_shots = int(getattr(self, "urban_ai_clear_shots", 0) or 0) + 1
        except Exception: pass
        shooter["last_los_clear"] = True
        return True

    def _ai_separation_vector(self, actor: dict, friends, enemies, target_pos: Vec3) -> Vec3:
        pos = Vec3(actor.get("pos", Vec3()))
        kind = str(actor.get("kind") or "robot")
        personal = AI_PERSONAL_SPACE.get(kind if kind in AI_PERSONAL_SPACE else ("ally" if kind == "ally" else "robot"), 18.0)
        out = Vec3(0, 0, 0)
        correction = 0
        for other in list(friends or []) + list(enemies or []):
            if other is actor or float(other.get("hp", 0.0)) <= 0.0:
                continue
            op = Vec3(other.get("pos", Vec3()))
            delta = pos - op
            delta.z = 0
            d = delta.length()
            other_space = AI_PERSONAL_SPACE.get(str(other.get("kind") or "robot"), 16.0)
            want = personal + other_space * 0.45
            if 0.01 < d < want:
                delta.normalize()
                out += delta * ((want - d) / max(1.0, want)) * 1.35
                correction += 1
        # Keep off objective cores and ruins; they can use them as reference points, not stand inside them.
        avoided = 0
        for obs in _ai_obstacles(self):
            op = Vec3(obs.get("pos", Vec3()))
            delta = pos - op
            delta.z = 0
            d = delta.length()
            want = float(obs.get("radius", 6.0) or 6.0) + AI_OBJECT_BUFFER + (6.0 if kind == "mech" else 0.0)
            if 0.01 < d < want:
                delta.normalize()
                out += delta * ((want - d) / max(1.0, want)) * 1.75
                avoided += 1
        if correction:
            try: self.urban_ai_spacing_corrections = int(getattr(self, "urban_ai_spacing_corrections", 0) or 0) + correction
            except Exception: pass
        if avoided:
            try: self.urban_ai_obstacle_avoidance = int(getattr(self, "urban_ai_obstacle_avoidance", 0) or 0) + avoided
            except Exception: pass
        # If blocked, slide across the target line instead of always backing up.
        if not bool(actor.get("last_los_clear", True)):
            to = target_pos - pos
            to.z = 0
            if to.lengthSquared() > 0.001:
                to.normalize()
                side = Vec3(to.y, -to.x, 0.0)
                sign = -1.0 if (float(actor.get("seed", 0)) % 2.0) < 1.0 else 1.0
                out += side * sign * 0.90
        return out

    def _maybe_ai_boost(self, actor: dict, target_pos: Vec3, now: float, reason: str = "blocked"):
        kind = str(actor.get("kind") or "robot")
        if kind == "drone":
            return False
        variant = str(actor.get("variant") or "")
        if variant in {"siege", "colossus"}:
            return False
        if now < float(actor.get("ai_boost_cd", 0.0) or 0.0):
            return False
        role = str(actor.get("role") or "")
        # Not every ground unit should jump constantly. Prefer mobile roles and friend bots.
        allowed = kind == "ally" or role in {"flanker", "acrobat", "hunter", "sniper"} or variant in {"hunter", "assault"}
        if not allowed:
            return False
        pos = Vec3(actor.get("pos", Vec3()))
        height = AI_JETPACK_HEIGHT.get(kind if kind in AI_JETPACK_HEIGHT else "robot", 12.0)
        if role in {"sniper", "flanker"} or str(actor.get("name")) in {"Orbit", "Archivist", "Nyx"}:
            height += 8.0
        if kind == "mech":
            height += 8.0
        actor["ai_boost_until"] = now + 0.72
        actor["ai_perch_until"] = now + (2.2 if kind != "mech" else 1.35)
        actor["ai_target_z"] = _floor_z(self, pos.x, pos.y) + height
        actor["ai_boost_cd"] = now + AI_JETPACK_COOLDOWN.get(kind if kind in AI_JETPACK_COOLDOWN else "robot", 4.0) + (float(actor.get("seed", 0)) % 7) * 0.09
        actor["ai_state"] = "jetpack_" + str(reason or "boost")
        try:
            self.urban_ai_boosts = int(getattr(self, "urban_ai_boosts", 0) or 0) + 1
            _add_beam(self, pos + Vec3(0,0,0.5), pos + Vec3(0,0, min(30.0, height)), _actor_color("ally" if kind == "ally" else kind, str(actor.get("name", "")), str(actor.get("role", ""))), 0.34, "ai-jetpack")
        except Exception:
            pass
        return True

    def _apply_ai_vertical(self, actor: dict, pos: Vec3, dt: float, now: float) -> Vec3:
        kind = str(actor.get("kind") or "robot")
        if kind == "drone":
            pos.z = _floor_z(self, pos.x, pos.y) + 26.0 + math.sin(now * 2.4 + float(actor.get("seed", 0))) * 4.5
            return pos
        base = _floor_z(self, pos.x, pos.y) + (0.8 if kind == "ally" else (0.2 if kind == "mech" else 0.7))
        target = base
        if now < float(actor.get("ai_boost_until", 0.0) or 0.0) or now < float(actor.get("ai_perch_until", 0.0) or 0.0):
            target = max(base, float(actor.get("ai_target_z", base) or base))
        lift_rate = 36.0 if kind != "mech" else 24.0
        fall_rate = 44.0 if kind != "mech" else 28.0
        if pos.z < target:
            pos.z = min(target, pos.z + lift_rate * dt)
        else:
            pos.z = max(target, pos.z - fall_rate * dt)
        if target <= base + 0.1:
            pos.z = base
        return pos


    def _is_boss_enemy(enemy: dict) -> bool:
        return str((enemy or {}).get("variant") or "") in BOSS_VARIANTS or bool((enemy or {}).get("boss", False))

    def _active_bosses(self):
        return [e for e in list(getattr(self, "urban_warzone_enemies", []) or []) if float(e.get("hp", 0.0)) > 0.0 and _is_boss_enemy(e)]

    def _boss_cooldown_remaining(self, now: float | None = None) -> float:
        now = time.time() if now is None else float(now)
        return max(0.0, BOSS_COOLDOWN_SECONDS - (now - float(getattr(self, "urban_warzone_last_boss_defeated_at", 0.0) or 0.0)))

    def _can_spawn_boss(self, now: float | None = None) -> bool:
        if _active_bosses(self):
            return False
        return _boss_cooldown_remaining(self, now) <= 0.0

    def _apply_player_down_penalty(self, reason: str = "player_down") -> int:
        score = int(getattr(self, "urban_warzone_score", 0) or 0)
        if score <= 0:
            self.urban_warzone_player_down_penalty = 0
            return 0
        wave = int(getattr(self, "urban_warzone_wave", 1) or 1)
        penalty = min(score, max(250, int(score * 0.25) + wave * 75))
        self.urban_warzone_score = max(0, score - penalty)
        self.urban_warzone_points_this_run = max(0, int(getattr(self, "urban_warzone_points_this_run", 0) or 0) - penalty)
        self.urban_warzone_combo = 0
        self.urban_warzone_player_down_penalty = penalty
        try:
            self.center_hint["text"] = f"URBAN WARZONE // DOWNED -{penalty} POINTS"
        except Exception:
            pass
        return penalty

    def _boss_variant_for_wave(wave: int, challenge: str) -> str:
        wave = int(wave or 1)
        challenge = str(challenge or "")
        if challenge == "colossus" and wave >= 10:
            return "spider_boss" if (wave // 5) % 2 else "rex_boss"
        if challenge == "colossus":
            return "rex_boss" if wave % 10 else "spider_boss"
        if wave > 0 and wave % 9 == 0:
            return "spider_boss"
        if wave > 0 and wave % 5 == 0:
            return "rex_boss"
        return "colossus"


    def _load_metropolis_robot_arena_allies(self):
        """Read the single bound Metropolis Robot Selector robot for Urban support."""
        try:
            path = METROBOT_ARENA_EXPORT_PATH
            if not path.exists():
                self.urban_warzone_metrobot_allies = []
                self.urban_warzone_metrobot_ally_count = 0
                return []
            data = json.loads(path.read_text(encoding="utf-8"))
            allies = []
            if isinstance(data, dict) and int(data.get("schema", 0) or 0) >= 2:
                active = data.get("active_ally")
                if isinstance(active, dict) and not bool(active.get("destroyed", False)) and bool(active.get("alive", True)):
                    if isinstance(active.get("urban_actor_template"), dict) or active.get("role") or active.get("variant"):
                        allies = [active]
            else:
                # Legacy compatibility only: old saved blueprints can still load,
                # but the new Metropolis runtime writes a single active ally.
                raw_allies = data.get("arena_allies", []) if isinstance(data, dict) else []
                allies = [a for a in list(raw_allies or []) if isinstance(a, dict) and int(a.get("part_count", 0) or len(a.get("parts", []) or [])) > 0]
            clean = [dict(a) for a in list(allies or []) if isinstance(a, dict)]
            self.urban_warzone_metrobot_allies = clean[:1]
            self.urban_warzone_metrobot_ally_count = len(self.urban_warzone_metrobot_allies)
            return list(self.urban_warzone_metrobot_allies)
        except Exception as exc:
            print(f"urban_metrobot_load_warning:{exc}")
            self.urban_warzone_metrobot_allies = []
            self.urban_warzone_metrobot_ally_count = 0
            return []

    def _clear_ambient_metropolis_robot_ally(self):
        try:
            node = getattr(self, "urban_metrobot_ambient_node", None)
            if node is not None and not node.isEmpty():
                node.removeNode()
        except Exception:
            pass
        self.urban_metrobot_ambient_node = None
        self.urban_metrobot_ambient_id = ""

    def _sync_ambient_metropolis_robot_ally(self, root=None, reason: str = "urban_spawn"):
        """Show the selected Metropolis robot in Urban without starting a builder.

        The saved Metropolis selection is a single persistent Urban ally.  It is
        displayed whenever the player is in Urban, disappears when the saved
        export marks it destroyed, and refreshes when Archivist binds a new one.
        """
        if not _urban_allowed(self) or bool(getattr(self, "urban_warzone_active", False)):
            _clear_ambient_metropolis_robot_ally(self)
            return False
        root = root or getattr(self, "urban_battlefield_root", None)
        if root is None or root.isEmpty():
            _clear_ambient_metropolis_robot_ally(self)
            return False
        blueprints = _load_metropolis_robot_arena_allies(self)
        blueprint = blueprints[0] if blueprints else None
        if not isinstance(blueprint, dict):
            _clear_ambient_metropolis_robot_ally(self)
            self.urban_metrobot_ambient_status = "no_active_selection"
            return False
        ally_id = str(blueprint.get("id") or blueprint.get("active_ally_id") or blueprint.get("name") or "")
        if not ally_id:
            _clear_ambient_metropolis_robot_ally(self)
            self.urban_metrobot_ambient_status = "missing_id"
            return False
        existing = getattr(self, "urban_metrobot_ambient_node", None)
        if existing is not None and not existing.isEmpty() and str(getattr(self, "urban_metrobot_ambient_id", "")) != ally_id:
            _clear_ambient_metropolis_robot_ally(self)
            existing = None
        if getattr(self, "urban_metrobot_ambient_node", None) is None or self.urban_metrobot_ambient_node.isEmpty():
            try:
                node = root.attachNewNode(f"urban-selected-metropolis-robot-{ally_id[:18]}")
                node.setTransparency(TransparencyAttrib.MAlpha)
                template = blueprint.get("urban_actor_template") if isinstance(blueprint.get("urban_actor_template"), dict) else {}
                role = str(template.get("role") or blueprint.get("role") or "duelist")
                variant = str(template.get("variant") or blueprint.get("variant") or "standard")
                actor = {
                    "kind": "ally", "name": f"MetroBot:{str(blueprint.get('name') or blueprint.get('class_label') or 'Selected')[:22]}",
                    "role": role, "variant": variant, "pos": Vec3(0, 0, 0), "yaw": 0.0,
                    "metropolis_robot_blueprint": blueprint, "metropolis_bound_ally_id": ally_id,
                }
                _build_actor_node(self, node, actor)
                self.urban_metrobot_ambient_node = node
                self.urban_metrobot_ambient_id = ally_id
            except Exception as exc:
                print(f"urban_metrobot_ambient_build_warning:{exc}")
                _clear_ambient_metropolis_robot_ally(self)
                self.urban_metrobot_ambient_status = "build_failed"
                return False
        try:
            yaw = math.radians(float(getattr(self, "player_yaw", 0.0)))
        except Exception:
            yaw = 0.0
        forward = Vec3(math.sin(yaw), math.cos(yaw), 0.0)
        if forward.lengthSquared() < 0.001:
            forward = Vec3(0, -1, 0)
        forward.normalize()
        right = Vec3(forward.y, -forward.x, 0.0)
        player = Vec3(getattr(self, "player_pos", Vec3(0, 0, 0)))
        pos = player - forward * 12.0 + right * 7.5
        pos.z = _floor_z(self, pos.x, pos.y) + 0.72 + math.sin(time.time() * 2.6) * 0.10
        try:
            node = self.urban_metrobot_ambient_node
            node.setPos(pos)
            node.setH(float(getattr(self, "player_yaw", 0.0)) + 180.0)
        except Exception:
            pass
        self.urban_metrobot_ambient_status = "active"
        return True

    def _build_metropolis_blueprint_actor(root, actor: dict, blueprint: dict, color):
        template = (blueprint or {}).get("urban_actor_template") if isinstance(blueprint, dict) else None
        if isinstance(template, dict):
            role = str(template.get("role") or blueprint.get("role") or actor.get("role") or "duelist")
            variant = str(template.get("variant") or blueprint.get("variant") or actor.get("variant") or "standard")
            bot_color = _safe_tuple_color(template.get("color") or blueprint.get("color"), color)
            _build_role_actor(root, "ally", bot_color, role, variant)
            accent = _safe_tuple_color(template.get("accent") or blueprint.get("accent"), _clamped_rgba(bot_color, 0.82, 1.25))
            _line_node(root, "metropolis-bound-ally-crown", accent, [Vec3(math.cos(a) * 6.2, math.sin(a) * 6.2, 8.7) for a in [i * math.tau / 36.0 for i in range(37)]], False, max(1.0, 1.6 * 0.18))
            _line_node(root, "metropolis-bound-ally-floor-id", accent, [Vec3(math.cos(a) * 7.6, math.sin(a) * 7.6, -2.35) for a in [i * math.tau / 40.0 for i in range(41)]], False, max(1.0, 1.6 * 0.20))
            return
        parts = list((blueprint or {}).get("parts", []) or [])
        if not parts:
            _build_role_actor(root, "ally", color, "construct", "support")
            return
        # Legacy saved offsets are local to body/parent tree.  For arena use, draw
        # the same attached hierarchy as absolute local offsets; this keeps older
        # robots readable while the new Metropolis Robot Selector writes Urban-class bots.
        for idx, part in enumerate(parts[:32]):
            try:
                size = part.get("size") or [3.0, 2.2, 3.0]
                sx, sy, sz = max(0.25, float(size[0])), max(0.25, float(size[1])), max(0.25, float(size[2]))
                off = part.get("offset") or [0, 0, 0]
                center = Vec3(float(off[0]), float(off[1]), float(off[2]))
                part_color = color
                cname = str(part.get("color") or "").lower()
                palette = {
                    "cyan": (0.16, 0.95, 1.0, 0.88), "violet": (0.70, 0.36, 1.0, 0.88),
                    "magenta": (1.0, 0.22, 0.82, 0.88), "gold": (1.0, 0.76, 0.18, 0.88),
                    "green": (0.22, 1.0, 0.44, 0.88), "white": (0.90, 0.98, 1.0, 0.86),
                    "red": (1.0, 0.18, 0.14, 0.88),
                }
                part_color = palette.get(cname, part_color)
                alpha = 0.58 if idx else 0.70
                edge = 0.20 if idx else 0.30
                _machine_box(root, f"metrobot-{idx:02d}-{part.get('role','part')}", center, Vec3(sx, sy, sz), part_color, alpha, edge, 1.10 if idx == 0 else 1.0)
                if bool(part.get("limb")):
                    _line_node(root, f"metrobot-limb-ring-{idx}", (1.0, 0.82, 0.20, 0.68), [Vec3(center.x + math.cos(a)*max(sx,sy)*0.75, center.y + math.sin(a)*max(sx,sy)*0.75, center.z + sz*0.62) for a in [i*math.tau/24 for i in range(25)]], False, max(1.0, 1.6*0.16))
            except Exception:
                continue
        _line_node(root, "metrobot-ally-halo", _clamped_rgba(color, 0.72, 1.25), [Vec3(math.cos(a)*6.4, math.sin(a)*6.4, 8.2) for a in [i*math.tau/32 for i in range(33)]], False, max(1.0, 1.6*0.18))

    def _spawn_metropolis_robot_ally(self, blueprint: dict, idx: int):
        pos = _ally_spawn_position(self, "Archivist", idx + 3) + Vec3((idx - 0.5) * 10.0, 0, 0)
        p = Vec3(getattr(self, "player_pos", Vec3()))
        delta = pos - p
        yaw = math.degrees(math.atan2(delta.x, delta.y)) if delta.lengthSquared() > 0.001 else 0.0
        label = str(blueprint.get("name") or blueprint.get("class_label") or blueprint.get("id") or idx)[:26]
        template = blueprint.get("urban_actor_template") if isinstance(blueprint.get("urban_actor_template"), dict) else {}
        role = str(template.get("role") or blueprint.get("role") or "duelist")
        variant = str(template.get("variant") or blueprint.get("variant") or "standard")
        stats = blueprint.get("stats") if isinstance(blueprint.get("stats"), dict) else {}
        hp = 115.0 + float(stats.get("armor", 5) or 5) * 7.0
        actor = {
            "kind": "ally",
            "name": f"MetroBot:{label}",
            "role": role,
            "variant": variant,
            "pos": pos,
            "hp": hp,
            "max_hp": hp,
            "cooldown": max(0.30, 0.62 - float(stats.get("speed", 5) or 5) * 0.025),
            "seed": 91000 + idx * 131 + abs(hash(str(blueprint.get("id") or label))) % 9000,
            "yaw": yaw,
            "summoned": True,
            "faction": "ally",
            "ai_boost_until": 0.0,
            "ai_boost_cd": 0.0,
            "ai_perch_until": 0.0,
            "ai_target_z": 0.0,
            "ai_state": "metropolis_bound_ally",
            "metropolis_robot_blueprint": blueprint,
            "metropolis_bound_ally_id": str(blueprint.get("id") or ""),
            "metropolis_single_use_ally": True,
        }
        _build_actor_node(self, _warzone_root(self), actor)
        _set_actor_pos(actor)
        return actor

    def _mark_metropolis_robot_ally_destroyed(self, ally: dict, reason: str = "destroyed"):
        if not isinstance(ally, dict) or not bool(ally.get("metropolis_single_use_ally", False)):
            return False
        blueprint = ally.get("metropolis_robot_blueprint") if isinstance(ally.get("metropolis_robot_blueprint"), dict) else {}
        ally_id = str(ally.get("metropolis_bound_ally_id") or blueprint.get("id") or "")
        if not ally_id:
            return False
        if bool(ally.get("metropolis_death_recorded", False)):
            return False
        ally["metropolis_death_recorded"] = True
        try:
            path = METROBOT_ARENA_EXPORT_PATH
            path.parent.mkdir(parents=True, exist_ok=True)
            data = {}
            if path.exists():
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                except Exception:
                    data = {}
            if not isinstance(data, dict):
                data = {}
            active = data.get("active_ally") if isinstance(data.get("active_ally"), dict) else dict(blueprint)
            if isinstance(active, dict):
                active["alive"] = False
                active["destroyed"] = True
                active["destroyed_at"] = datetime.now().isoformat(timespec="seconds")
                active["destroyed_reason"] = str(reason or "destroyed")
            data.update({
                "schema": max(2, int(data.get("schema", 2) or 2)),
                "tool": "Metropolis Robot Selector",
                "active_ally": active if isinstance(active, dict) else None,
                "active_ally_id": ally_id,
                "arena_allies": [],
                "requires_new_selection": True,
                "death_rule": "Metropolis ally was destroyed in Urban Warzone. Return to Archivist to bind a new robot.",
                "updated_at": datetime.now().isoformat(timespec="seconds"),
                "reason": str(reason or "destroyed"),
            })
            path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
            self.urban_warzone_metrobot_allies = []
            self.urban_warzone_metrobot_ally_count = 0
            try:
                self.center_hint["text"] = "URBAN WARZONE // METROPOLIS ALLY DESTROYED - RETURN TO ARCHIVIST"
            except Exception:
                pass
            return True
        except Exception as exc:
            print(f"urban_metrobot_death_mark_warning:{exc}")
            return False

    def _deploy_metropolis_robot_allies(self, reason: str = "wave_start"):
        blueprints = _load_metropolis_robot_arena_allies(self)
        if not blueprints:
            return 0
        allies = list(getattr(self, "urban_warzone_allies", []) or [])
        names = {str(a.get("name")) for a in allies}
        added = 0
        for idx, bp in enumerate(blueprints[:4]):
            name = f"MetroBot:{str(bp.get('name') or bp.get('id') or idx)[:22]}"
            if name in names:
                continue
            actor = _spawn_metropolis_robot_ally(self, bp, len(allies) + idx)
            if actor is not None:
                allies.append(actor); names.add(name); added += 1
        self.urban_warzone_allies = allies
        self.urban_warzone_metrobot_ally_count = len(blueprints[:4])
        if added:
            try:
                self._append_mode_gateway_history("urban_metropolis_robot_allies_deployed", label="Urban Warzone", route=IN_WORLD_ROUTE, extra={"reason": reason, "added": added, "available": len(blueprints)})
            except Exception:
                pass
        return added

    def _spawn_ally(self, bot: str, idx: int):
        if str(bot) == SABLE_BATTLE_OWNER:
            return _sync_sable_battle_actor(self, create=True)
        pos = _ally_spawn_position(self, bot, idx)
        p = Vec3(getattr(self, "player_pos", Vec3()))
        delta = pos - p
        yaw = math.degrees(math.atan2(delta.x, delta.y)) if delta.lengthSquared() > 0.001 else 0.0
        role = BOT_ROLE_MAP.get(bot, "duelist")
        actor = {"kind": "ally", "name": bot, "role": role, "variant": "support", "pos": pos, "hp": 110.0, "max_hp": 110.0, "cooldown": 0.3 + idx * 0.13, "seed": idx * 101 + 11, "yaw": yaw, "summoned": True, "faction": "ally", "ai_boost_until": 0.0, "ai_boost_cd": 0.0, "ai_perch_until": 0.0, "ai_target_z": 0.0, "ai_state": "deploying"}
        _build_actor_node(self, _warzone_root(self), actor)
        _set_actor_pos(actor)
        if bool(actor.get("boss", False)):
            self.urban_warzone_boss_active = str(actor.get("name", "boss"))
            self.urban_warzone_last_boss_at = time.time()
        return actor

    def _camera_forward_spawn_basis(self):
        p = Vec3(getattr(self, "player_pos", Vec3()))
        f = None
        try:
            f = self.camera.getQuat(self.render).getForward()
            f = Vec3(float(f.x), float(f.y), 0.0)
        except Exception:
            f = None
        if f is None or f.length() < 0.001:
            try:
                h = math.radians(float(getattr(self, "player_yaw", 0.0) or 0.0))
                f = Vec3(math.sin(h), math.cos(h), 0.0)
            except Exception:
                f = Vec3(0.0, -1.0, 0.0)
        if f.length() < 0.001:
            f = Vec3(0.0, -1.0, 0.0)
        f.normalize()
        r = Vec3(f.y, -f.x, 0.0)
        if r.length() < 0.001:
            r = Vec3(1.0, 0.0, 0.0)
        r.normalize()
        return p, f, r

    def _near_stage_enemy_position(self, kind: str, idx: int, wave: int):
        # First impression matters: early Urban waves must spawn in the actual
        # player view, not on distant generated anchors. Later waves can use the
        # wider district once the player understands the activity is active.
        if int(wave or 1) > 3:
            return None
        p, f, r = _camera_forward_spawn_basis(self)
        if kind == "mech":
            forward = 82.0 + (idx % 2) * 28.0
            lateral = (-32.0 if idx % 2 == 0 else 32.0) + ((idx // 2) % 2) * 14.0
        elif kind == "drone":
            forward = 58.0 + (idx % 3) * 18.0
            lateral = [-34.0, 0.0, 34.0][idx % 3]
        else:
            forward = 44.0 + (idx % 4) * 13.0
            lateral = [-28.0, -10.0, 12.0, 30.0][idx % 4] + ((idx // 4) * 9.0)
        pos = p + f * forward + r * lateral
        pos.z = _floor_z(self, pos.x, pos.y) + (30.0 if kind == "drone" else 0.7)
        return pos

    def summon_urban_warzone_ally(self, source="manual", force=False):
        if not bool(getattr(self, "urban_warzone_active", False)):
            return False
        _sync_sable_battle_actor(self, create=True)
        now = time.time()
        force = bool(force)
        active = _alive_allies(self)
        cap = _ally_cap_for_wave(self)
        if not force and len(active) >= cap:
            self.center_hint["text"] = f"URBAN WARZONE // ALLY CAP {len(active)}/{cap} - CLEAR WAVES FOR RESET"
            return False
        cd = float(getattr(self, "urban_warzone_summon_cooldown", 0.0) or 0.0)
        if not force and now < cd:
            self.center_hint["text"] = f"URBAN WARZONE // SUPPORT LOCKED {max(0.0, cd - now):.1f}s"
            return False
        all_allies = list(getattr(self, "urban_warzone_allies", []) or [])
        all_names = {str(a.get("name")) for a in all_allies}
        roster = list(BATTLE_REINFORCEMENT_BOTS)
        start = int(getattr(self, "urban_warzone_summon_index", 0) or 0)
        chosen = None
        for off in range(len(roster)):
            bot = roster[(start + off) % len(roster)]
            if bot not in all_names:
                chosen = bot
                self.urban_warzone_summon_index = (start + off + 1) % max(1, len(roster))
                break
        if chosen is None:
            # No mid-wave respawns. Dead allies stay down until wave clear or
            # full reset so battles have stakes and roster state is readable.
            down = [a for a in all_allies if str(a.get("name")) != SABLE_BATTLE_OWNER and float(a.get("hp", 0.0)) <= 0.0]
            if down:
                self.center_hint["text"] = "URBAN WARZONE // FRIEND BOTS DOWN - RESET ON WAVE CLEAR"
            else:
                self.center_hint["text"] = "URBAN WARZONE // ALL FRIEND BOTS DEPLOYED"
            return False
        ally = _spawn_ally(self, chosen, len(all_allies))
        if ally is not None:
            self.urban_warzone_allies.append(ally)
        if not force:
            self.urban_warzone_summon_cooldown = now + 8.0
        self.center_hint["text"] = f"URBAN WARZONE // {chosen} DEPLOYED AROUND THE BATTLEFIELD"
        return True

    def _spawn_enemy(self, kind: str, idx: int, wave: int):
        p = Vec3(getattr(self, "player_pos", Vec3()))
        rng = random.Random(int(wave) * 5003 + idx * 971 + {"robot": 1, "drone": 2, "mech": 3}.get(kind, 4))
        role_cycle = ["duelist", "flanker", "sniper", "breaker", "hunter", "acrobat", "survivor"]
        challenge = str(getattr(self, "urban_warzone_challenge", _challenge_for_wave(wave)) or "frontline")
        difficulty = str(getattr(self, "urban_warzone_difficulty", _difficulty_for_wave(wave)) or "STANDARD")
        profile = _difficulty_profile(difficulty)
        if kind == "robot":
            variants = list(ROBOT_VARIANTS)
            variant = variants[(idx + wave) % len(variants)]
            if challenge == "hunter_pack":
                variant = "stalker" if idx % 3 == 0 else ("crawler" if idx % 2 else "assault")
            elif challenge == "bomb_run" and idx % 4 == 0:
                variant = "bomber"
        elif kind == "drone":
            variants = list(DRONE_VARIANTS)
            variant = variants[(idx + wave) % len(variants)]
            if challenge == "drone_storm":
                variant = "gunship" if idx % 3 else "jammer"
            elif challenge == "bomb_run" and idx % 2 == 0:
                variant = "bomber"
        else:
            variants = list(MECH_VARIANTS)
            variant = variants[(idx + wave) % len(variants)]
            if wave == 1 and idx == 0:
                variant = "rex"
            elif wave == 1 and idx == 1:
                variant = "spider"
            elif challenge == "colossus" and idx == 0 and _can_spawn_boss(self):
                variant = _boss_variant_for_wave(wave, challenge)
            elif challenge == "mech_pressure":
                variant = "rex" if idx % 3 == 0 else ("spider" if idx % 3 == 1 else "hunter")
            elif wave >= 4 and idx % 4 == 0:
                variant = "raptor"

        staged = _near_stage_enemy_position(self, kind, idx, wave)
        if staged is not None:
            role = role_cycle[(idx + wave) % len(role_cycle)]
            x, y = staged.x, staged.y
        else:
            anchor = _pick_spawn_anchor(self, kind, idx, wave, min_dist=92.0 if kind != "mech" else 130.0)
            if anchor is not None:
                base = Vec3(anchor.get("pos", Vec3()))
                role = str(anchor.get("role") or role_cycle[(idx + wave) % len(role_cycle)])
                jitter = Vec3(rng.uniform(-22.0, 22.0), rng.uniform(-22.0, 22.0), 0)
                x, y = base.x + jitter.x, base.y + jitter.y
            else:
                role = role_cycle[(idx + wave) % len(role_cycle)]
                ang = rng.random() * math.tau
                dist = rng.uniform(90.0, 155.0) + min(85.0, wave * 5.5)
                x = p.x + math.cos(ang) * dist
                y = p.y + math.sin(ang) * dist

        z = _floor_z(self, x, y) + (30.0 if kind == "drone" else 0.7)
        hp = 48.0 if kind == "robot" else (38.0 if kind == "drone" else 185.0 + wave * 24.0)
        speed = 18.0 if kind == "robot" else (25.0 if kind == "drone" else 8.5)
        boss = variant in BOSS_VARIANTS
        if role == "breaker":
            hp *= 1.22; speed *= 0.88
        elif role == "flanker":
            speed *= 1.20
        elif role == "sniper":
            hp *= 0.86
        if variant in {"assault", "gunship", "hunter", "stalker"}:
            hp *= 1.12; speed *= 1.08
        elif variant in {"crawler", "scout", "raptor"}:
            speed *= 1.18
        elif variant in {"shield", "siege", "rex", "spider"}:
            hp *= 1.32; speed *= 0.86
        elif variant in {"bomber", "repair_hunter"}:
            hp *= 0.92; speed *= 1.10
        elif variant == "jammer":
            hp *= 0.95; speed *= 1.06
        elif variant == "colossus":
            hp *= 2.65; speed *= 0.72
        elif variant == "rex_boss":
            hp *= 3.15; speed *= 0.68
        elif variant == "spider_boss":
            hp *= 3.45; speed *= 0.62
        hp *= float(profile.get("hp_scale", 1.0))
        speed *= max(0.70, min(1.45, float(profile.get("enemy_scale", 1.0))))
        actor = {
            "kind": kind,
            "name": f"{kind}_{variant}_{role}_{wave}_{idx}",
            "role": role,
            "variant": variant,
            "pos": Vec3(x, y, z),
            "hp": hp,
            "max_hp": hp,
            "speed": speed,
            "damage_scale": float(profile.get("damage_scale", 1.0)),
            "points": ENEMY_POINT_VALUES.get(kind, 100),
            "boss": bool(boss),
            "death_beam": bool(variant in MECH_SPIDER_VARIANTS),
            "seed": wave * 1000 + idx,
            "cooldown": 0.8 + rng.random(),
            "yaw": math.degrees(math.atan2(x - p.x, y - p.y)) + 180.0,
            "faction": "enemy",
            "ai_boost_until": 0.0,
            "ai_boost_cd": 0.0,
            "ai_perch_until": 0.0,
            "ai_target_z": 0.0,
            "ai_state": "teleporting",
            "last_los_clear": False,
        }
        _build_actor_node(self, _warzone_root(self), actor)
        _set_actor_pos(actor)
        if bool(actor.get("boss", False)):
            self.urban_warzone_boss_active = str(actor.get("name", "boss"))
            self.urban_warzone_last_boss_at = time.time()
        try:
            _draw_4d_spawn_effect(self, Vec3(actor.get("pos", Vec3())), kind, idx, wave)
        except Exception as exc:
            print(f"urban_warzone_spawn_fx_error:{exc}")
        return actor

    def spawn_urban_warzone_wave(self):
        self.urban_warzone_wave = int(getattr(self, "urban_warzone_wave", 0) or 0) + 1
        wave = int(self.urban_warzone_wave)
        self.urban_warzone_difficulty = _difficulty_for_wave(wave)
        self.urban_warzone_challenge = _challenge_for_wave(wave)
        profile = _difficulty_profile(self.urban_warzone_difficulty)
        _warzone_root(self)
        # Ensure the distributed arena pockets exist before placing enemies.
        try:
            update_urban_cover_layer(self, 0.016)
        except Exception as exc:
            print(f"urban_warzone_pre_spawn_cover_error:{exc}")
        for e in list(getattr(self, "urban_warzone_enemies", []) or []):
            try:
                node = e.get("node")
                if node is not None and not node.isEmpty():
                    node.removeNode()
            except Exception:
                pass
        enemies = []
        # Wave composition now has named challenge rules instead of random clumps.
        scale = float(profile.get("enemy_scale", 1.0))
        challenge = str(getattr(self, "urban_warzone_challenge", "frontline") or "frontline")
        robot_count = int(min(14, round((4 + wave * 0.90) * scale)))
        drone_count = int(min(9, round((1 + wave * 0.35) * scale)))
        # Wave 1 must already read as urban warfare. A visible enemy mech is
        # staged immediately instead of waiting until wave 2. Boss-class mechs are
        # limited to one active boss at a time with a 10 second cooldown.
        boss_due = bool(challenge == "colossus" or (wave > 0 and wave % 5 == 0)) and _can_spawn_boss(self)
        mech_count = (2 if wave == 1 else (1 if wave >= 1 else 0))
        if wave >= 5 and not boss_due:
            mech_count += 1
        if challenge == "capture_lock":
            robot_count += 3
            drone_count += 1
        elif challenge == "bomb_run":
            robot_count += 2
            drone_count += 2
        elif challenge == "hunter_pack":
            robot_count += 4
            drone_count = max(1, drone_count - 1)
        elif challenge == "drone_storm":
            drone_count += 4
            robot_count = max(4, robot_count - 2)
        elif challenge == "mech_pressure":
            mech_count += 1
        elif challenge == "colossus":
            mech_count = 1 if boss_due else max(1, mech_count)
            robot_count += 2
            drone_count += 1
        for i in range(max(1, robot_count)):
            enemies.append(_spawn_enemy(self, "robot", i, wave))
        for i in range(max(0, drone_count)):
            enemies.append(_spawn_enemy(self, "drone", i, wave))
        for i in range(max(0, mech_count)):
            enemies.append(_spawn_enemy(self, "mech", i, wave))
        # One boss at a time, enforced after all wave variants are chosen.
        boss_seen = False
        for enemy in enemies:
            if _is_boss_enemy(enemy):
                if boss_seen:
                    enemy["variant"] = "rex" if str(enemy.get("variant")) == "rex_boss" else "spider"
                    enemy["boss"] = False
                    enemy["death_beam"] = bool(str(enemy.get("variant")) in MECH_SPIDER_VARIANTS)
                else:
                    boss_seen = True
        self.urban_warzone_enemies = enemies
        self.urban_warzone_next_wave_at = 0.0
        # Sable is the existing Urban bot; the other battle bots persist for the
        # full wave and do not respawn until wave clear/reset.
        _sync_sable_battle_actor(self, create=True)
        challenge_name = CHALLENGE_TITLES.get(challenge, challenge.title())
        self.center_hint["text"] = f"URBAN WARZONE // WAVE {wave} {self.urban_warzone_difficulty} // {challenge_name}"

    def force_urban_warzone_frontline_tableau(self):
        # First activation stage: use the real wave actors near the player while
        # the reused arena layer stays buried under the Urban terrain. No proof
        # labels or duplicate tableau objects are created.
        try:
            p, f, r = _camera_forward_spawn_basis(self)
            enemies = [e for e in list(getattr(self, "urban_warzone_enemies", []) or []) if float(e.get("hp", 0.0)) > 0.0]
            allies = [a for a in list(getattr(self, "urban_warzone_allies", []) or []) if float(a.get("hp", 0.0)) > 0.0]
            mechs = [e for e in enemies if str(e.get("kind")) == "mech"]
            if not mechs:
                mech = _spawn_enemy(self, "mech", 99, max(1, int(getattr(self, "urban_warzone_wave", 1) or 1)))
                enemies.append(mech)
                self.urban_warzone_enemies = enemies
                mechs = [mech]
            layout = []
            # Centerpiece enemy mech: close, tall, unmistakable.
            layout.append((mechs[0], 56.0, 0.0, 0.7))
            robots = [e for e in enemies if str(e.get("kind")) == "robot"]
            drones = [e for e in enemies if str(e.get("kind")) == "drone"]
            for n, e in enumerate(robots[:4]):
                layout.append((e, 34.0 + n * 7.0, [-24.0, -9.0, 11.0, 27.0][n], 0.7))
            for n, e in enumerate(drones[:3]):
                layout.append((e, 48.0 + n * 8.0, [-30.0, 0.0, 30.0][n], 30.0))
            for actor, forward, lateral, zoff in layout:
                pos = p + f * forward + r * lateral
                pos.z = _floor_z(self, pos.x, pos.y) + zoff
                actor["pos"] = pos
                actor["yaw"] = math.degrees(math.atan2(pos.x - p.x, pos.y - p.y)) + 180.0
                _set_actor_pos(actor)
            for n, ally in enumerate(allies[:3]):
                pos = p + f * (18.0 + n * 4.0) + r * ([-16.0, 16.0, 0.0][n])
                pos.z = _floor_z(self, pos.x, pos.y) + 0.7
                ally["pos"] = pos
                ally["yaw"] = math.degrees(math.atan2((p + f * 56.0).x - pos.x, (p + f * 56.0).y - pos.y))
                _set_actor_pos(ally)
            # Make the proof/game opening show the new AI without debug labels: a few
            # bots immediately boost to high sightlines while others hold spacing.
            try:
                proof_now = time.time()
                for actor in (allies[:2] + robots[:1]):
                    _maybe_ai_boost(self, actor, Vec3(mechs[0].get("pos", p + f * 56.0)) if mechs else p + f * 56.0, proof_now, reason="high_ground")
            except Exception:
                pass
            # Large, persistent-looking laser lanes so combat reads immediately.
            try:
                if mechs and allies:
                    mpos = Vec3(mechs[0].get("pos", Vec3()))
                    for n, ally in enumerate(allies[:2]):
                        apos = Vec3(ally.get("pos", Vec3()))
                        _spawn_beam(self, apos + Vec3(0,0,6.0), mpos + Vec3(0,0,14.0), (0.15, 0.95, 1.0, 0.92), ttl=2.8, name=f"ally-opening-{n}")
                    for n, robot in enumerate(robots[:2]):
                        rpos = Vec3(robot.get("pos", Vec3()))
                        _spawn_beam(self, rpos + Vec3(0,0,5.0), p + Vec3(0,0,2.0), (1.0, 0.10, 0.03, 0.82), ttl=2.8, name=f"enemy-opening-{n}")
            except Exception:
                pass

        except Exception as exc:
            print(f"urban_warzone_frontline_tableau_error:{exc}")

    def stage_urban_warzone_intro_view(self):
        # Make the first activation prove itself in the player's actual view.
        try:
            force_urban_warzone_frontline_tableau(self)
            enemies = [e for e in list(getattr(self, "urban_warzone_enemies", []) or []) if float(e.get("hp", 0.0)) > 0.0]
            if not enemies:
                return
            enemies.sort(key=lambda e: (0 if str(e.get("kind")) == "mech" else 1, (Vec3(e.get("pos", Vec3())) - Vec3(getattr(self, "player_pos", Vec3()))).length()))
            target = Vec3(enemies[0].get("pos", Vec3()))
            target.z += 13.0 if str(enemies[0].get("kind")) == "mech" else 6.0
            self.camera.lookAt(target)
            hpr = self.camera.getHpr(self.render)
            self.player_yaw = float(hpr.x)
            self.player_pitch = float(hpr.y)
            self.camera.setHpr(self.player_yaw, self.player_pitch, 0)
            # Advance several tactical frames so opening spacing, line-of-sight
            # decisions, boosts, and ally fire are live instead of spawn poses.
            try:
                for _ in range(12):
                    update_urban_warzone(self, 0.033)
            except Exception as sim_exc:
                print(f"urban_warzone_intro_ai_warmup_warning:{sim_exc}")
            self.center_hint["text"] = "URBAN WARZONE // AI AWARENESS ONLINE"
        except Exception as exc:
            print(f"urban_warzone_intro_view_error:{exc}")

    def _mark_urban_route_truth(self, active: bool, source=""):
        """Latch the one true Urban route into visible/game state.

        The old failure mode was a proof/runtime route saying it worked while the
        player was still looking at world.py's ambient Urban shell. This marker is
        intentionally explicit so testing happens from the real player route.
        """
        if bool(active):
            self.urban_warzone_route_truth = "active"
            self.urban_warzone_route_marker = ROUTE_TRUTH_MARKER
            self.urban_warzone_route_owner = ROUTE_TRUTH_OWNER
            self.runtime_world_signature = ROUTE_TRUTH_MARKER
            try:
                self.center_hint["text"] = f"{ROUTE_TRUTH_MARKER} // SABLE ROUTE"
            except Exception:
                pass
        else:
            self.urban_warzone_route_truth = "inactive"
            self.urban_warzone_route_marker = ""
            try:
                if str(getattr(self, "runtime_world_signature", "")) == ROUTE_TRUTH_MARKER:
                    self.runtime_world_signature = "HOLOVERSE DEFAULT // URBAN ROUTE UNMOUNTED"
            except Exception:
                pass

    def create_urban_warzone_ui(self):
        try:
            if getattr(self, "urban_warzone_ui_root", None) is not None and not self.urban_warzone_ui_root.isEmpty():
                self.urban_warzone_ui_root.removeNode()
        except Exception:
            pass
        root = self.aspect2d.attachNewNode("urban-warzone-ui")
        self.urban_warzone_ui_root = root
        kw = {}
        try:
            font = self.load_core_ui_font()
            if font is not None:
                kw["text_font"] = font
        except Exception:
            pass
        # Compact combat strip. The old panel covered the scene and made proof
        # captures look like a debug menu instead of a warzone. This pass widens
        # the strip just enough to carry the route-truth marker without becoming
        # another modal panel.
        panel = DirectFrame(parent=root, frameColor=(0.012, 0.010, 0.012, 0.42), frameSize=(-0.74, 0.74, -0.108, 0.052), pos=(0.0, 0, 0.858), relief=1)
        panel.setTransparency(TransparencyAttrib.MAlpha)
        self.urban_warzone_ui_panel = panel
        self.urban_warzone_ui_title = DirectLabel(parent=panel, text=ROUTE_TRUTH_MARKER, text_align=TextNode.ACenter, text_fg=(1.0, 0.24, 0.16, 0.98), frameColor=(0,0,0,0), pos=(0.0, 0, 0.020), scale=0.025, **kw)
        self.urban_warzone_ui_route = DirectLabel(parent=panel, text="SOURCE: DIMENSION RUNTIME MOUNTED INTO LIVE URBAN REGION", text_align=TextNode.ACenter, text_fg=(0.96, 0.78, 0.30, 0.92), frameColor=(0,0,0,0), pos=(0.0, 0, -0.020), scale=0.016, **kw)
        self.urban_warzone_ui_status = DirectLabel(parent=panel, text="", text_align=TextNode.ACenter, text_fg=(0.92, 0.98, 1.0, 0.92), frameColor=(0,0,0,0), pos=(0.0, 0, -0.064), scale=0.019, **kw)
        self.urban_warzone_ui_help = DirectLabel(parent=root, text="", text_align=TextNode.ARight, text_fg=(0.72, 0.82, 0.86, 0.80), frameColor=(0,0,0,0), pos=(1.28, 0, -0.91), scale=0.020, **kw)
        try:
            # Keep the normal Core/HoloVerse corner panels from fighting the combat HUD.
            if getattr(self, "top_panel", None) is not None:
                self.top_panel.hide()
            if getattr(self, "region_top_panel", None) is not None:
                self.region_top_panel.hide()
        except Exception:
            pass

    def update_urban_warzone_ui(self):
        if getattr(self, "urban_warzone_ui_status", None) is None:
            return
        enemies = _alive_enemies(self)
        allies = _alive_allies(self)
        hp = max(0.0, float(getattr(self, "urban_warzone_player_hp", 100.0)))
        wave = int(getattr(self, 'urban_warzone_wave', 0) or 0)
        diff = str(getattr(self, "urban_warzone_difficulty", _difficulty_for_wave(wave)) or "RECRUIT")
        challenge = str(getattr(self, "urban_warzone_challenge", "frontline") or "frontline")
        challenge_name = CHALLENGE_TITLES.get(challenge, challenge.title())
        score = int(getattr(self, "urban_warzone_score", 0) or 0)
        combo = int(getattr(self, "urban_warzone_combo", 0) or 0)
        captures = sum(1 for p in list(getattr(self, "urban_warzone_capture_posts", []) or []) if str(p.get("owner")) == "ally")
        total_posts = len(getattr(self, "urban_warzone_capture_posts", []) or [])
        bombs = sum(1 for b in list(getattr(self, "urban_warzone_bomb_sites", []) or []) if bool(b.get("armed", True)))
        weapon = str(_current_weapon_profile(self).get("title", "PULSE RIFLE"))
        boosts = int(getattr(self, "urban_ai_boosts", 0) or 0)
        blocked = int(getattr(self, "urban_ai_blocked_shots", 0) or 0)
        bosses = len(_active_bosses(self))
        boss_cd = _boss_cooldown_remaining(self)
        boss_text = "BOSS LIVE" if bosses else ("BOSS READY" if boss_cd <= 0.0 else f"BOSS {boss_cd:02.0f}s")
        self.urban_warzone_ui_status["text"] = f"W{wave} {diff} | {challenge_name} | ARMOR {hp:03.0f} | E {len(enemies)} A {len(allies)}/{_ally_cap_for_wave(self)} M{int(getattr(self, 'urban_warzone_metrobot_ally_count', 0) or 0)} | CP {captures}/{total_posts} B {bombs} | {boss_text} | POINTS {score} x{combo}"
        try:
            if getattr(self, "urban_warzone_ui_route", None) is not None:
                self.urban_warzone_ui_route["text"] = "SOURCE: DIMENSION RUNTIME MOUNTED INTO LIVE URBAN REGION"
        except Exception:
            pass
        pockets = len(getattr(self, "urban_warzone_pockets", []) or [])
        cd = max(0.0, float(getattr(self, "urban_warzone_summon_cooldown", 0.0) or 0.0) - time.time())
        summon = "READY" if cd <= 0.0 else f"{cd:.0f}s"
        self.urban_warzone_ui_help["text"] = f"LMB {weapon}  |  Sable mounted beams + friend bots  |  no respawn until wave clear  |  death costs points  |  TAB exit"

    def _add_beam(self, start: Vec3, end: Vec3, color, ttl=0.10, name="beam"):
        root = _warzone_root(self)
        node = _line_node(root, f"urban-warzone-{name}-{len(getattr(self, 'urban_warzone_beams', []))}", color, [start, end], False, max(1.0, getattr(self.cfg, "line_thickness", 1.6) * 0.44))
        self.urban_warzone_beams.append({"node": node, "ttl": float(ttl)})

    def _nearest_enemy_to_ray(self, start: Vec3, forward: Vec3):
        if forward.lengthSquared() > 0.001:
            forward.normalize()
        best = None
        best_score = 999999.0
        for enemy in list(getattr(self, "urban_warzone_enemies", []) or []):
            if float(enemy.get("hp", 0.0)) <= 0.0:
                continue
            pos = Vec3(enemy.get("pos", Vec3()))
            to = pos - start
            dist = to.length()
            if dist <= 0.001 or dist > 260.0:
                continue
            aim = Vec3(to)
            aim.normalize()
            dot = aim.dot(forward)
            if dot < 0.88:
                continue
            score = dist * (1.0 + (1.0 - dot) * 8.0)
            if score < best_score:
                best_score = score
                best = enemy
        return best

    def urban_warzone_fire(self):
        if not bool(getattr(self, "urban_warzone_active", False)):
            return False
        try:
            quat = self.camera.getQuat(self.render)
            forward = quat.getForward()
        except Exception:
            forward = Vec3(0, 1, 0)
        start = Vec3(getattr(self, "player_pos", Vec3()))
        target = _nearest_enemy_to_ray(self, start, Vec3(forward))
        bomb_target = _nearest_bomb_to_ray(self, start, Vec3(forward))
        if target is None and bomb_target is not None:
            pos = Vec3(bomb_target.get("pos", Vec3()))
            _add_beam(self, start, pos + Vec3(0,0,2.5), (1.0, 0.40, 0.08, 0.84), 0.12, "bomb-shot")
            _urban_play_battle_sfx(self, "rocket", 0.24, 0.18)
            _detonate_bomb_site(self, bomb_target, source="player")
            return True
        if target is None:
            end = start + Vec3(forward) * 120.0
            _add_beam(self, start, end, (0.32, 0.88, 1.0, 0.65), 0.07, "miss")
            _urban_play_battle_sfx(self, "fire", 0.18, 0.14)
            return True
        pos = Vec3(target.get("pos", Vec3())) + Vec3(0, 0, 4.0 if target.get("kind") != "drone" else 0.0)
        weapon_profile = _current_weapon_profile(self)
        beam_color = tuple(weapon_profile.get("color", (0.34, 0.92, 1.0, 0.92)))
        _add_beam(self, start, pos, beam_color, 0.12, "player-shot")
        _urban_play_battle_sfx(self, "fire", 0.22, 0.14)
        kind = str(target.get("kind") or "robot")
        variant = str(target.get("variant") or "")
        damage = 48.0 if kind != "mech" else 38.0
        if kind == "drone":
            damage = 54.0
        if variant in {"shield", "siege", "colossus"}:
            damage *= 0.78
        elif variant in {"crawler", "scout"}:
            damage *= 1.12
        damage *= float(weapon_profile.get("damage_scale", 1.0) or 1.0)
        if kind == "mech":
            damage *= float(weapon_profile.get("mech_scale", 1.0) or 1.0)
        capture_bonus = 1.0 + min(0.45, 0.06 * sum(1 for p in list(getattr(self, "urban_warzone_capture_posts", []) or []) if str(p.get("owner")) == "ally"))
        damage *= capture_bonus
        target["hp"] = float(target.get("hp", 0.0)) - damage
        if float(weapon_profile.get("splash", 0.0) or 0.0) > 0.0:
            splash = float(weapon_profile.get("splash", 0.0) or 0.0)
            for other in list(getattr(self, "urban_warzone_enemies", []) or []):
                if other is target or float(other.get("hp", 0.0)) <= 0.0:
                    continue
                opos = Vec3(other.get("pos", Vec3()))
                if (opos - pos).length() <= splash:
                    other["hp"] = float(other.get("hp", 0.0)) - damage * 0.34
                    other["last_damage_source"] = "player"
                    _add_beam(self, pos, opos + Vec3(0,0,4.0), beam_color, 0.10, "arc-chain")
        target["last_damage_source"] = "player"
        left = max(0.0, float(target.get("hp", 0.0)))
        max_hp = max(1.0, float(target.get("max_hp", 1.0) or 1.0))
        self.center_hint["text"] = f"URBAN WARZONE // HIT {variant.upper()} {kind.upper()} // {left/max_hp:.0%} ARMOR"
        return True

    def _enemy_target(self, enemy: dict):
        candidates = [("player", Vec3(getattr(self, "player_pos", Vec3())), float(getattr(self, "urban_warzone_player_hp", 100.0)))]
        for ally in list(getattr(self, "urban_warzone_allies", []) or []):
            if float(ally.get("hp", 0.0)) > 0:
                candidates.append(("ally", Vec3(ally.get("pos", Vec3())), float(ally.get("hp", 0.0))))
        ep = Vec3(enemy.get("pos", Vec3()))
        best = candidates[0]
        best_d = 999999.0
        for c in candidates:
            d = (c[1] - ep).lengthSquared()
            if d < best_d:
                best_d = d
                best = c
        return best

    def _update_enemy(self, enemy: dict, dt: float, now: float):
        kind = str(enemy.get("kind") or "robot")
        pos = Vec3(enemy.get("pos", Vec3()))
        target_type, target_pos, _hp = _enemy_target(self, enemy)
        target_pos = Vec3(target_pos)
        to = target_pos - pos
        if kind != "drone":
            to.z = 0.0
        dist = to.length()
        role = str(enemy.get("role") or "duelist")
        variant = str(enemy.get("variant") or "standard")
        friends = [e for e in list(getattr(self, "urban_warzone_enemies", []) or []) if float(e.get("hp", 0.0)) > 0.0]
        enemies = [a for a in list(getattr(self, "urban_warzone_allies", []) or []) if float(a.get("hp", 0.0)) > 0.0]
        target_aim = Vec3(target_pos)
        target_aim.z += 4.0 if target_type != "player" else 2.0
        can_see = _has_clean_firing_lane(self, enemy, target_aim, friends=friends, enemies=enemies, ignore={id(enemy)})
        if dist > 0.001:
            direction = Vec3(to)
            direction.normalize()
            speed = float(enemy.get("speed", 12.0))
            if role in {"flanker", "acrobat"} or variant in {"raptor", "rex", "rex_boss"}:
                stride = 2.4 if variant in {"raptor", "rex", "rex_boss"} else 1.7
                strafe = Vec3(direction.y, -direction.x, 0) * math.sin(now * stride + float(enemy.get("seed", 0)))
                direction = direction * (0.86 if variant in MECH_DINO_VARIANTS else 0.72) + strafe * (0.34 if variant in MECH_DINO_VARIANTS else 0.54)
                if direction.lengthSquared() > 0.001:
                    direction.normalize()
            desired_range = 54.0 if role == "sniper" else (20.0 if role == "breaker" else (34.0 if kind == "drone" else 15.0))
            if variant in {"gunship", "jammer", "siege", "colossus", "spider", "spider_boss"}:
                desired_range += 34.0
            elif variant in {"crawler", "hunter", "raptor", "rex", "rex_boss"}:
                desired_range = max(10.0, desired_range - 8.0)
            steering = Vec3(0, 0, 0)
            if dist > desired_range:
                steering += direction
            elif role in {"sniper", "flanker"} and dist < desired_range * 0.78:
                steering -= direction * 0.90
            elif not can_see:
                steering += Vec3(direction.y, -direction.x, 0.0) * (1.0 if int(enemy.get("seed", 0)) % 2 else -1.0)
            steering += _ai_separation_vector(self, enemy, friends, enemies, target_pos) * 1.10
            if steering.lengthSquared() > 0.001:
                steering.normalize()
                pos += steering * speed * dt
                enemy["yaw"] = math.degrees(math.atan2((target_pos - pos).x, (target_pos - pos).y)) if (target_pos - pos).lengthSquared() > 0.001 else enemy.get("yaw", 0.0)
            # If it cannot see its target while in range, it can hop/boost for high ground or over rubble.
            if not can_see and dist < 165.0:
                _maybe_ai_boost(self, enemy, target_pos, now, reason="los")
        pos = _apply_ai_vertical(self, enemy, pos, dt, now)
        enemy["pos"] = pos
        cd = float(enemy.get("cooldown", 0.0)) - dt
        attack_range = 128.0 if role == "sniper" else (105.0 if kind in {"drone", "mech"} else 32.0)
        if variant in {"gunship", "jammer", "siege", "colossus", "spider", "spider_boss"}:
            attack_range += 34.0
        if variant in {"rex", "rex_boss", "raptor"}:
            attack_range = max(42.0, attack_range - 12.0)
        aim_to = target_aim - (pos + Vec3(0, 0, _actor_aim_height(enemy)))
        aim_ok = True
        if aim_to.lengthSquared() > 0.001:
            aim_flat = Vec3(aim_to.x, aim_to.y, 0.0)
            if aim_flat.lengthSquared() > 0.001:
                aim_flat.normalize()
                aim_ok = _actor_forward(enemy).dot(aim_flat) >= AI_AIM_CONE_DOT
                enemy["yaw"] = math.degrees(math.atan2(aim_flat.x, aim_flat.y))
        if cd <= 0.0 and dist < attack_range and can_see and aim_ok:
            damage = 4.0 if kind == "robot" else (6.0 if kind == "drone" else 11.0)
            if role == "breaker":
                damage *= 1.35
            elif role == "sniper":
                damage *= 1.25
            if variant in {"assault", "gunship", "siege", "stalker"}:
                damage *= 1.20
            elif variant == "colossus":
                damage *= 1.65
            elif variant in {"rex", "spider"}:
                damage *= 1.35
            elif variant == "rex_boss":
                damage *= 1.85
            elif variant == "spider_boss":
                damage *= 2.05
            elif variant in {"crawler", "scout", "raptor"}:
                damage *= 0.92
            damage *= float(enemy.get("damage_scale", 1.0) or 1.0)
            if target_type == "player":
                self.urban_warzone_player_hp = max(0.0, float(getattr(self, "urban_warzone_player_hp", 100.0)) - damage)
                beam_width = 0.18 if bool(enemy.get("death_beam", False)) else 0.08
                beam_ttl = 0.18 if bool(enemy.get("death_beam", False)) else 0.08
                _add_beam(self, pos + Vec3(0, 0, _actor_aim_height(enemy)), Vec3(getattr(self, "player_pos", Vec3())), (1.0, 0.04, 0.02, 0.84) if bool(enemy.get("death_beam", False)) else (1.0, 0.18, 0.08, 0.68), beam_ttl, "death-beam" if bool(enemy.get("death_beam", False)) else "enemy-shot")
            else:
                for ally in self.urban_warzone_allies:
                    if (Vec3(ally.get("pos", Vec3())) - target_pos).lengthSquared() < 1.0:
                        ally["hp"] = max(0.0, float(ally.get("hp", 0.0)) - damage * 1.4)
                        break
                beam_ttl = 0.18 if bool(enemy.get("death_beam", False)) else 0.08
                _add_beam(self, pos + Vec3(0, 0, _actor_aim_height(enemy)), target_aim, (1.0, 0.04, 0.02, 0.84) if bool(enemy.get("death_beam", False)) else (1.0, 0.18, 0.08, 0.68), beam_ttl, "death-beam" if bool(enemy.get("death_beam", False)) else "enemy-shot")
            _urban_play_battle_sfx(self, "fire", 0.12 if kind != "mech" else 0.18, 0.82)
            enemy["ai_state"] = "firing"
            enemy["cooldown"] = (1.7 if role == "sniper" else 1.4) if kind == "robot" else (1.1 if kind == "drone" else 2.0)
            if variant == "colossus":
                enemy["cooldown"] = 2.35
            elif variant == "rex_boss":
                enemy["cooldown"] = 1.75
            elif variant == "spider_boss":
                enemy["cooldown"] = 1.35
            elif variant in {"spider", "rex"}:
                enemy["cooldown"] *= 0.92
            elif variant in {"assault", "gunship", "hunter", "stalker", "raptor"}:
                enemy["cooldown"] *= 0.82
        else:
            enemy["cooldown"] = cd
        _set_actor_pos(enemy)

    def _update_ally(self, ally: dict, dt: float, now: float):
        p = Vec3(getattr(self, "player_pos", Vec3()))
        if bool(ally.get("uses_existing_world_bot", False)):
            node = ally.get("node")
            try:
                if node is not None and not node.isEmpty():
                    ally["pos"] = Vec3(node.getPos(self.render))
            except Exception:
                pass
        pos = Vec3(ally.get("pos", p))
        alive_enemies = [e for e in list(getattr(self, "urban_warzone_enemies", []) or []) if float(e.get("hp", 0.0)) > 0.0]
        target = None
        if alive_enemies:
            target = min(alive_enemies, key=lambda e: (Vec3(e.get("pos", Vec3())) - pos).lengthSquared())
        role = str(ally.get("role") or "sentinel")
        friends = [a for a in list(getattr(self, "urban_warzone_allies", []) or []) if float(a.get("hp", 0.0)) > 0.0]
        desired = p + Vec3(math.sin(now * 0.7 + float(ally.get("seed", 0))) * 28.0, math.cos(now * 0.6 + float(ally.get("seed", 0))) * 28.0, 0)
        can_see = False
        if target is not None:
            tpos_preview = Vec3(target.get("pos", Vec3()))
            away = pos - tpos_preview
            away.z = 0
            if away.lengthSquared() > 0.001:
                away.normalize()
            hold_range = 72.0 if role == "sniper" else (46.0 if role in {"survivor", "sentinel"} else 32.0)
            desired = tpos_preview + away * hold_range
            if (desired - p).length() > 155.0:
                desired = p + (desired - p) * 0.46
            target_aim = tpos_preview + Vec3(0, 0, 8.0 if str(target.get("kind")) == "mech" else 4.0)
            can_see = _has_clean_firing_lane(self, ally, target_aim, friends=friends, enemies=alive_enemies, ignore={id(ally), id(target)})
            if not can_see:
                _maybe_ai_boost(self, ally, tpos_preview, now, reason="clean_shot")
        move = desired - pos
        move.z = 0
        steering = Vec3(0, 0, 0)
        if move.length() > 4.0:
            move.normalize()
            steering += move
        if target is not None:
            steering += _ai_separation_vector(self, ally, friends, alive_enemies, Vec3(target.get("pos", Vec3()))) * 1.18
        else:
            steering += _ai_separation_vector(self, ally, friends, [], p) * 1.0
        if not bool(ally.get("uses_existing_world_bot", False)):
            if steering.lengthSquared() > 0.001:
                steering.normalize()
                ally_name = str(ally.get("name"))
                base_speed = 22.0 if ally_name in {"Nyx", "Vanta"} else (18.0 if target is not None else 16.0)
                pos += steering * base_speed * dt
            pos = _apply_ai_vertical(self, ally, pos, dt, now)
            ally["pos"] = pos
        else:
            ally["ai_state"] = "sable_mounted_beams"
        if target is not None:
            tpos = Vec3(target.get("pos", Vec3()))
            direction = tpos - pos
            if direction.lengthSquared() > 0.001:
                flat = Vec3(direction.x, direction.y, 0.0)
                if flat.lengthSquared() > 0.001:
                    flat.normalize()
                    ally["yaw"] = math.degrees(math.atan2(flat.x, flat.y))
            cd = float(ally.get("cooldown", 0.0)) - dt
            aim_ok = True
            if direction.lengthSquared() > 0.001:
                flat = Vec3(direction.x, direction.y, 0.0)
                if flat.lengthSquared() > 0.001:
                    flat.normalize()
                    aim_ok = _actor_forward(ally).dot(flat) >= AI_AIM_CONE_DOT
            if cd <= 0.0 and direction.length() < 185.0 and can_see and aim_ok:
                dmg = 18.0
                ally_name = str(ally.get("name"))
                if ally_name == "Ember": dmg = 28.0
                if ally_name == "Mirror": dmg = 24.0
                if ally_name == "Archivist": dmg = 21.0
                if ally_name == "Sable": dmg = 25.0
                if ally_name == "Orbit": dmg = 26.0
                if str(target.get("kind")) == "mech" and ally_name in {"Ember", "Sable", "Orbit"}:
                    dmg *= 1.25
                target["hp"] = float(target.get("hp", 0.0)) - dmg
                target["last_damage_source"] = "ally"
                ally["ai_state"] = "cover_fire"
                self.urban_warzone_ally_assists = int(getattr(self, "urban_warzone_ally_assists", 0) or 0) + 1
                _add_beam(self, pos + Vec3(0, 0, _actor_aim_height(ally)), tpos + Vec3(0, 0, 3.0), _actor_color("ally", str(ally.get("name")), str(ally.get("role", "duelist"))), 0.08, "ally-shot")
                _urban_play_battle_sfx(self, "fire", 0.12, 0.72)
                ally["cooldown"] = 0.90 + (float(ally.get("seed", 0)) % 5) * 0.05
            else:
                ally["cooldown"] = cd
        _set_actor_pos(ally)

    def _cleanup_dead(self):
        alive = []
        for e in list(getattr(self, "urban_warzone_enemies", []) or []):
            if float(e.get("hp", 0.0)) <= 0.0:
                kind = str(e.get("kind") or "robot")
                self.urban_warzone_kills_this_run = int(getattr(self, "urban_warzone_kills_this_run", 0) or 0) + 1
                self.urban_warzone_total_kills = int(getattr(self, "urban_warzone_total_kills", 0) or 0) + 1
                if kind == "mech":
                    self.urban_warzone_total_mechs = int(getattr(self, "urban_warzone_total_mechs", 0) or 0) + 1
                    if _is_boss_enemy(e):
                        self.urban_warzone_boss_active = None
                        self.urban_warzone_last_boss_defeated_at = time.time()
                if kind == "drone":
                    self.urban_warzone_total_drones = int(getattr(self, "urban_warzone_total_drones", 0) or 0) + 1
                source = str(e.get("last_damage_source") or "player")
                points = _register_score(self, e, source=source)
                variant = str(e.get("variant") or kind).upper()
                self.center_hint["text"] = f"URBAN WARZONE // {variant} {kind.upper()} DOWN +{points}"
                _urban_play_battle_sfx(self, "hit", 0.18 if kind != "mech" else 0.28, 0.50)
                try:
                    node = e.get("node")
                    if node is not None and not node.isEmpty():
                        node.removeNode()
                except Exception:
                    pass
            else:
                alive.append(e)
        self.urban_warzone_enemies = alive
        beams = []
        for b in list(getattr(self, "urban_warzone_beams", []) or []):
            ttl = float(b.get("ttl", 0.0)) - 0.016
            node = b.get("node")
            if ttl <= 0.0:
                try:
                    if node is not None and not node.isEmpty():
                        node.removeNode()
                except Exception:
                    pass
            else:
                b["ttl"] = ttl
                beams.append(b)
        self.urban_warzone_beams = beams

    def activate_urban_warzone_from_mode(self, mode=None, source="core", route=""):
        if not _urban_allowed(self):
            # Core-deck launches used to silently do nothing unless the player was
            # already standing in the Urban sector. That made it look like the
            # updated dimension folder was a duplicate. Route directly to the
            # owned Urban region, then mount this runtime in the live world.
            try:
                self.world_unlocked = False
                self.active_artifact = None
                self.active_artifact_id = None
                self.transition_target = 0.0
                self.transition_progress = 0.0
                self.holospace_active = False
                if hasattr(self, "activate_default_world_shell"):
                    self.activate_default_world_shell()
                if hasattr(self, "travel_to_holoverse_region_index"):
                    self.travel_to_holoverse_region_index(URBAN_REGION_NUMBER)
                if hasattr(self, "update_world_chunks"):
                    self.update_world_chunks()
            except Exception as exc:
                print(f"urban_warzone_auto_region_route_error:{exc}")
        if not _urban_allowed(self):
            self.center_hint["text"] = "URBAN WARZONE // ROUTE FAILED: URBAN REGION NOT ACTIVE"
            return False
        try:
            if getattr(self, "holoforge_active", False): self.deactivate_holoforge(reason="switch_to_urban_warzone")
            if getattr(self, "forest_growth_active", False): self.deactivate_forest_growth(reason="switch_to_urban_warzone")
            if getattr(self, "hills_life_active", False): self.deactivate_hills_life(reason="switch_to_urban_warzone")
            if getattr(self, "oddities_active", False): self.deactivate_oddities(reason="switch_to_urban_warzone")
            if getattr(self, "desert_ships_active", False): self.deactivate_desert_ships(reason="switch_to_urban_warzone")
            if getattr(self, "frost_circuit_active", False): self.deactivate_frost_circuit(reason="switch_to_urban_warzone")
            if getattr(self, "shell_flight_craft_active", False): self.toggle_shell_flight_craft()
        except Exception:
            pass
        _ensure_dirs()
        load_urban_warzone_state(self)
        _destroy_urban_battlefield_runtime(self)
        _clear_ambient_metropolis_robot_ally(self)
        update_urban_cover_layer(self, 0.016)
        self.urban_warzone_active = True
        self.urban_warzone_wave = 0
        self.urban_warzone_player_hp = 100.0
        self.urban_warzone_kills_this_run = 0
        self.urban_warzone_score = 0
        self.urban_warzone_points_this_run = 0
        self.urban_warzone_combo = 0
        self.urban_warzone_last_kill_at = 0.0
        self.urban_warzone_difficulty = "RECRUIT"
        self.urban_warzone_challenge = "frontline"
        self.urban_warzone_summon_index = 0
        self.urban_warzone_summon_cooldown = 0.0
        self.urban_warzone_exit_prompt_until = 0.0
        self.urban_warzone_capture_score = 0
        self.urban_warzone_bombs_detonated = 0
        self.urban_warzone_weapon_mode = "pulse_rifle"
        self.urban_warzone_weapon_until = 0.0
        self.urban_ai_los_checks = 0
        self.urban_ai_blocked_shots = 0
        self.urban_ai_clear_shots = 0
        self.urban_ai_boosts = 0
        self.urban_ai_spacing_corrections = 0
        self.urban_ai_obstacle_avoidance = 0
        self.urban_warzone_boss_active = None
        self.urban_warzone_last_boss_at = 0.0
        self.urban_warzone_last_boss_defeated_at = 0.0
        self.urban_warzone_player_down_penalty = 0
        self.urban_warzone_allies = []
        _sync_sable_battle_actor(self, create=True)
        for bot in BATTLE_REINFORCEMENT_BOTS:
            if str(bot) not in {str(a.get("name")) for a in list(getattr(self, "urban_warzone_allies", []) or [])}:
                ally = _spawn_ally(self, bot, len(list(getattr(self, "urban_warzone_allies", []) or [])))
                if ally is not None:
                    self.urban_warzone_allies.append(ally)
        _deploy_metropolis_robot_allies(self, reason="activation")
        create_urban_warzone_ui(self)
        spawn_urban_warzone_wave(self)
        stage_urban_warzone_intro_view(self)
        _mark_urban_route_truth(self, True, source=source)
        update_urban_warzone_ui(self)
        label = str((mode or {}).get("name") or "Urban Warzone")
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
            self._append_mode_gateway_history("urban_warzone_runtime_open", mode=mode, label=label, route=IN_WORLD_ROUTE, extra={"source": source, "state": str(STATE_PATH), "summon_roster": list(BOT_ALLIES), "starter_allies": STARTER_ALLY_COUNT})
        except Exception:
            pass
        return True

    def deactivate_urban_warzone(self, reason="closed"):
        if not bool(getattr(self, "urban_warzone_active", False)):
            return
        self.urban_warzone_runs_completed = int(getattr(self, "urban_warzone_runs_completed", 0) or 0) + 1
        self.urban_warzone_best_wave = max(int(getattr(self, "urban_warzone_best_wave", 0) or 0), int(getattr(self, "urban_warzone_wave", 0) or 0))
        self.urban_warzone_best_score = max(int(getattr(self, "urban_warzone_best_score", 0) or 0), int(getattr(self, "urban_warzone_score", 0) or 0))
        save_urban_warzone_state(self, reason=reason)
        self.urban_warzone_active = False
        _mark_urban_route_truth(self, False, source=reason)
        _destroy_warzone_visuals(self)
        try:
            if getattr(self, "top_panel", None) is not None:
                self.top_panel.show()
            if getattr(self, "region_top_panel", None) is not None:
                self.region_top_panel.show()
        except Exception:
            pass
        self.center_hint["text"] = f"URBAN WARZONE // SAVED + CLOSED ({str(reason).upper()})"
        try:
            if _urban_allowed(self):
                ensure_urban_battlefield_runtime(self, 0.016, source="match_closed")
        except Exception as exc:
            print(f"urban_warzone_rebuild_ambient_warning:{exc}")
        try:
            self._append_mode_gateway_history("urban_warzone_runtime_close", label="Urban Warzone", route=IN_WORLD_ROUTE, extra={"reason": reason, "state": str(STATE_PATH)})
        except Exception:
            pass

    def update_urban_warzone(self, dt=0.0):
        if not bool(getattr(self, "urban_warzone_active", False)):
            return
        if not _urban_allowed(self):
            deactivate_urban_warzone(self, reason="left_urban_region")
            return
        dt = max(0.001, min(0.05, float(dt or 0.016)))
        now = time.time()
        if float(getattr(self, "urban_warzone_player_hp", 100.0)) <= 0.0:
            penalty = _apply_player_down_penalty(self, reason="player_down")
            self.center_hint["text"] = f"URBAN WARZONE // ARMOR BROKEN -{penalty} POINTS - RUN SAVED"
            deactivate_urban_warzone(self, reason="player_down")
            return
        for ally in list(getattr(self, "urban_warzone_allies", []) or []):
            if str(ally.get("name")) == SABLE_BATTLE_OWNER and bool(ally.get("uses_existing_world_bot", False)):
                ally["hp"] = max(float(ally.get("hp", 1.0) or 1.0), 1.0)
            if float(ally.get("hp", 0.0)) <= 0.0:
                try:
                    _mark_metropolis_robot_ally_destroyed(self, ally, reason="ally_down")
                except Exception:
                    pass
                try:
                    node = ally.get("node")
                    if node is not None and not node.isEmpty() and not bool(ally.get("uses_existing_world_bot", False)):
                        node.removeNode()
                except Exception:
                    pass
                ally["node"] = None
                ally["ai_state"] = "down_until_wave_clear"
                continue
            _update_ally(self, ally, dt, now)
        for enemy in list(getattr(self, "urban_warzone_enemies", []) or []):
            if float(enemy.get("hp", 0.0)) > 0.0:
                _update_enemy(self, enemy, dt, now)
        _update_capture_posts(self, dt)
        _update_bomb_sites(self, dt)
        _update_arena_weapons(self, dt)
        _cleanup_dead(self)
        if not getattr(self, "urban_warzone_enemies", []):
            if float(getattr(self, "urban_warzone_next_wave_at", 0.0) or 0.0) <= 0.0:
                self.urban_warzone_next_wave_at = now + 2.5
                wave = int(getattr(self, "urban_warzone_wave", 0) or 0)
                clear_bonus = 250 + wave * 65
                if str(getattr(self, "urban_warzone_challenge", "frontline")) != "frontline":
                    clear_bonus += 220
                self.urban_warzone_score = int(getattr(self, "urban_warzone_score", 0) or 0) + clear_bonus
                self.urban_warzone_points_this_run = int(getattr(self, "urban_warzone_points_this_run", 0) or 0) + clear_bonus
                self.urban_warzone_best_score = max(int(getattr(self, "urban_warzone_best_score", 0) or 0), int(getattr(self, "urban_warzone_score", 0) or 0))
                self.center_hint["text"] = f"URBAN WARZONE // WAVE CLEAR +{clear_bonus} // FRIEND BOTS RESET"
                self.urban_warzone_best_wave = max(int(getattr(self, "urban_warzone_best_wave", 0) or 0), wave)
                _reset_allies_for_wave_clear(self, reason="wave_clear")
                save_urban_warzone_state(self, reason="wave_clear")
            elif now >= float(self.urban_warzone_next_wave_at):
                spawn_urban_warzone_wave(self)
        update_urban_warzone_ui(self)

    # Runtime API
    CommandHubApp.is_urban_warzone_mode = _is_warzone_mode
    CommandHubApp.activate_urban_warzone_from_mode = activate_urban_warzone_from_mode
    CommandHubApp.deactivate_urban_warzone = deactivate_urban_warzone
    CommandHubApp.load_urban_warzone_state = load_urban_warzone_state
    CommandHubApp.save_urban_warzone_state = save_urban_warzone_state
    CommandHubApp.update_urban_warzone = update_urban_warzone
    CommandHubApp.force_urban_warzone_frontline_tableau = force_urban_warzone_frontline_tableau
    CommandHubApp.stage_urban_warzone_intro_view = stage_urban_warzone_intro_view
    CommandHubApp.update_urban_cover_layer = update_urban_cover_layer
    CommandHubApp.ensure_urban_battlefield_runtime = ensure_urban_battlefield_runtime
    CommandHubApp.destroy_urban_battlefield_runtime = _destroy_urban_battlefield_runtime
    CommandHubApp.urban_warzone_fire = urban_warzone_fire
    CommandHubApp.summon_urban_warzone_ally = summon_urban_warzone_ally
    CommandHubApp._mark_urban_route_truth = _mark_urban_route_truth

    # Region-bot hard route: Sable must never fall through to a missing
    # standalone app, proof scene, native adapter, or external launch. If the
    # bot dialogue says Urban Warzone, confirm mounts this runtime directly.
    old_confirm_bot_dimension_dialogue = getattr(CommandHubApp, "confirm_bot_dimension_dialogue", None)
    if callable(old_confirm_bot_dimension_dialogue):
        def confirm_bot_dimension_dialogue(self):
            try:
                ctx = dict(getattr(self, "bot_dialogue_context", {}) or {})
                bot_name = str(ctx.get("bot") or getattr(self, "bot_dialogue_bot", "")).strip().lower()
                mode_title = str(ctx.get("mode") or getattr(self, "bot_dialogue_mode", "")).strip().lower()
                if bot_name == "sable" or "urban warzone" in mode_title or mode_title == "urban":
                    mode = None
                    finder = getattr(self, "find_core_mode_by_title", None)
                    if callable(finder):
                        try:
                            mode = finder("Urban Warzone", bot_name="Sable")
                        except Exception:
                            mode = None
                    if mode is None:
                        mode = {
                            "name": "Urban Warzone",
                            "folder": str(ROOT / "Dimensions" / "Urban Warzone"),
                            "manifest": {
                                "id": "urban_warzone",
                                "title": "Urban Warzone",
                                "launch_type": IN_WORLD_ROUTE,
                                "runtime": "runtime.py",
                                "region_owner": "URBAN",
                                "bot_owner": "Sable",
                            },
                        }
                    try:
                        self.bot_dialogue_launch_in_progress = True
                        if getattr(self, "bot_dialogue_root", None) is not None:
                            self.bot_dialogue_root.hide()
                    except Exception:
                        pass
                    try:
                        if hasattr(self, "close_bot_dimension_dialogue"):
                            self.close_bot_dimension_dialogue("launching")
                    except Exception:
                        pass
                    ok = bool(self.activate_urban_warzone_from_mode(mode, source="region_bot:Sable", route=IN_WORLD_ROUTE))
                    if not ok:
                        try:
                            self.center_hint["text"] = "URBAN WARZONE // SABLE ROUTE FAILED"
                        except Exception:
                            pass
                    return ok
            except Exception as exc:
                print(f"urban_warzone_sable_confirm_bypass_error:{exc}")
            return old_confirm_bot_dimension_dialogue(self)
        CommandHubApp.confirm_bot_dimension_dialogue = confirm_bot_dimension_dialogue

    old_setup_input = CommandHubApp.setup_input
    def setup_input(self):
        result = old_setup_input(self)
        try:
            self.accept("r", self.summon_urban_warzone_ally, ["manual", False])
        except Exception:
            pass
        return result
    CommandHubApp.setup_input = setup_input

    old_init = CommandHubApp.__init__
    def __init__(self, *args, **kwargs):
        old_init(self, *args, **kwargs)
        _init_state(self)
    CommandHubApp.__init__ = __init__

    old_route = CommandHubApp.launch_core_mode_route
    def launch_core_mode_route(self, mode, source="core", extra_env=None, close_core=True):
        if self.is_urban_warzone_mode(mode):
            return bool(self.activate_urban_warzone_from_mode(mode, source=source, route=IN_WORLD_ROUTE))
        return old_route(self, mode, source=source, extra_env=extra_env, close_core=close_core)
    CommandHubApp.launch_core_mode_route = launch_core_mode_route

    old_update_player = CommandHubApp.update_player
    def update_player(self, dt):
        prev_z = 0.0
        preserve_vertical = False
        try:
            prev_z = float(getattr(self, "player_pos", Vec3()).z)
            preserve_vertical = _urban_allowed(self) and (
                abs(float(getattr(self, "urban_jump_velocity", 0.0) or 0.0)) > 0.01
                or bool(getattr(self, "urban_on_cover_ground", False))
            )
        except Exception:
            preserve_vertical = False
        result = old_update_player(self, dt)
        try:
            # The base world movement intentionally snaps normal walking to the
            # terrain floor. Urban Warzone needs jump/roof traversal, so preserve
            # the previous vertical state before the cover-collision resolver runs.
            if preserve_vertical and _urban_allowed(self):
                p = Vec3(getattr(self, "player_pos", Vec3()))
                p.z = max(float(p.z), prev_z)
                self.player_pos = p
                try:
                    self.camera.setPos(self.player_pos)
                except Exception:
                    pass
            self.ensure_urban_battlefield_runtime(dt, source="world_update")
            if bool(getattr(self, "urban_warzone_active", False)):
                self.update_urban_warzone(dt)
        except Exception as exc:
            print(f"urban_warzone_update_error:{exc}")
        return result
    CommandHubApp.update_player = update_player

    old_click = CommandHubApp.primary_click_interact
    def primary_click_interact(self):
        if bool(getattr(self, "urban_warzone_active", False)):
            return self.urban_warzone_fire()
        return old_click(self)
    CommandHubApp.primary_click_interact = primary_click_interact

    old_start_escape_hold = CommandHubApp.start_escape_hold
    def start_escape_hold(self):
        if bool(getattr(self, "urban_warzone_active", False)):
            now = time.monotonic()
            until = float(getattr(self, "urban_warzone_exit_prompt_until", 0.0) or 0.0)
            if now <= until:
                self.deactivate_urban_warzone(reason="escape_confirmed")
            else:
                self.urban_warzone_exit_prompt_until = now + 2.4
                self.center_hint["text"] = "URBAN WARZONE // PRESS ESC AGAIN TO EXIT"
            return
        return old_start_escape_hold(self)
    CommandHubApp.start_escape_hold = start_escape_hold

    old_handle_tab = CommandHubApp.handle_tab_action
    def handle_tab_action(self):
        if bool(getattr(self, "urban_warzone_active", False)):
            self.deactivate_urban_warzone(reason="tab_exit")
            return
        return old_handle_tab(self)
    CommandHubApp.handle_tab_action = handle_tab_action

    old_number = CommandHubApp.handle_number_action
    def handle_number_action(self, number):
        if bool(getattr(self, "urban_warzone_active", False)):
            self.deactivate_urban_warzone(reason="teleport_exit")
        return old_number(self, number)
    CommandHubApp.handle_number_action = handle_number_action

    old_region_ui = CommandHubApp.update_holoverse_region_ui
    def update_holoverse_region_ui(self):
        result = old_region_ui(self)
        if bool(getattr(self, "urban_warzone_active", False)):
            try:
                if hasattr(self, "region_keymap_root"):
                    self.region_keymap_root.hide()
                if hasattr(self, "region_top_panel"):
                    self.region_top_panel.hide()
            except Exception:
                pass
        return result
    CommandHubApp.update_holoverse_region_ui = update_holoverse_region_ui

    setattr(main, "URBAN_WARZONE_RUNTIME_INSTALLED", True)
    setattr(main, "URBAN_WARZONE_STATE_PATH_RUNTIME", STATE_PATH)
