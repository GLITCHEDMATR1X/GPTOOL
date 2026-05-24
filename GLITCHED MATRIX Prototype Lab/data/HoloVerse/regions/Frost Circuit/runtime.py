"""Frost Circuit in-world runtime for the live ICE HoloVerse region.

Mirror turns the ICE ring into a starter hovercraft race: player vs bot racers,
third-person chase camera, waypoint laps around the ring, safe unload on ESC,
TAB, teleport, or leaving the ICE region. It is intentionally simple and stable
so the region has a complete first playable layer without external launch paths.
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
from panda3d.core import AntialiasAttrib, LineSegs, TextNode, TransparencyAttrib, Vec3

IN_WORLD_ROUTE = "in_world_region"
FROST_CIRCUIT_SCHEMA = 1
ICE_REGION_NUMBER = 5
ICE_R0 = 6100.0
ICE_R1 = 7500.0
ICE_TRACK_RADIUS = (ICE_R0 + ICE_R1) * 0.5
ICE_TRACK_WAYPOINTS = 28
ICE_REQUIRED_LAPS = 1
ICE_LEAVE_MARGIN = 100.0
ICE_OBSTACLE_COUNT = 22
ICE_LOOP_GATE_COUNT = 5
ICE_WAYPOINT_SCORE = 35
ICE_LOOP_SCORE = 260
ICE_FINISH_SCORE = 750
ICE_SPEED_SCORE_PER_SECOND = 5
ICE_HOVER_BASE_CLEARANCE = 8.2
ICE_HOVER_SPEED_LIFT = 6.4
ICE_SCORE_CRYSTAL_COUNT = 24
ICE_CRYSTAL_SCORE = 120
ICE_CLEAN_STREAK_SCORE = 65
ICE_OVERTAKE_SCORE = 90
ICE_DRIFT_SCORE_PER_SECOND = 18
ICE_BOOST_SCORE_PER_SECOND = 12
ICE_CRAFT_VISUAL_SCALE = 2.25
ICE_PLAYER_MAX_SPEED = 134.0
ICE_PLAYER_BOOST_MULTIPLIER = 1.34
ICE_PLAYER_ACCEL = 88.0
ICE_TRACK_CENTERING_ASSIST = 0.92
BOT_RACERS = ("IO", "Vanta", "Nyx", "Solace", "Ember", "Sable", "Archivist")


def _main_module(cls):
    return sys.modules.get(cls.__module__) or sys.modules.get("__main__")


def install_frost_circuit_runtime(CommandHubApp):
    main = _main_module(CommandHubApp)
    if main is None:
        return

    from holoverse_mode_runtime import resolve_shared_data_root

    ROOT = Path(getattr(main, "ROOT", Path(__file__).resolve().parent))
    SHARED_DATA_ROOT = resolve_shared_data_root(main, ROOT)
    STATE_DIR = SHARED_DATA_ROOT / "holoverse" / "regions" / "ice" / "races"
    STATE_PATH = STATE_DIR / "frost_circuit_state.json"
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

    def _ice_allowed(self):
        try:
            if self.is_holospace_active():
                return False
        except Exception:
            pass
        try:
            return int(self.current_holoverse_region_number()) == ICE_REGION_NUMBER
        except Exception:
            return True

    def _angle_from_xy(x: float, y: float) -> float:
        return math.atan2(float(y), float(x))

    def _wrap_deg(v: float) -> float:
        while v > 180.0:
            v -= 360.0
        while v < -180.0:
            v += 360.0
        return v

    def _heading_vec(yaw_deg: float) -> Vec3:
        rad = math.radians(float(yaw_deg))
        return Vec3(math.sin(rad), math.cos(rad), 0.0)

    def _yaw_to_target(src: Vec3, target: Vec3) -> float:
        dx = float(target.x - src.x)
        dy = float(target.y - src.y)
        # Panda-style heading: 0 faces +Y, 90 faces +X.
        return math.degrees(math.atan2(dx, dy))

    def _dist2d(a: Vec3, b: Vec3) -> float:
        dx = float(a.x - b.x)
        dy = float(a.y - b.y)
        return math.sqrt(dx * dx + dy * dy)

    def _hovercraft_color(name: str):
        table = {
            "Player": (0.72, 1.00, 1.00, 0.98),
            "IO": (0.82, 0.86, 0.92, 0.95),
            "Vanta": (0.20, 1.00, 0.36, 0.95),
            "Nyx": (0.72, 0.48, 1.00, 0.95),
            "Solace": (0.32, 1.00, 0.92, 0.95),
            "Ember": (1.00, 0.54, 0.18, 0.95),
            "Sable": (0.70, 0.74, 0.78, 0.95),
            "Archivist": (0.82, 0.36, 1.00, 0.95),
        }
        return table.get(str(name), (0.66, 0.86, 1.0, 0.95))

    def _init_state(self):
        self.frost_circuit_active = False
        self.frost_circuit_root = None
        self.frost_circuit_track_root = None
        self.frost_circuit_ui_root = None
        self.frost_circuit_ui_panel = None
        self.frost_circuit_ui_title = None
        self.frost_circuit_ui_status = None
        self.frost_circuit_ui_help = None
        self.frost_circuit_racers = []
        self.frost_circuit_waypoints = []
        self.frost_circuit_obstacles = []
        self.frost_circuit_loop_gates = []
        self.frost_circuit_started_at = 0.0
        self.frost_circuit_finished = False
        self.frost_circuit_exit_prompt_until = 0.0
        self.frost_circuit_last_save_at = 0.0
        self.frost_circuit_best_time = None
        self.frost_circuit_wins = 0
        self.frost_circuit_races_completed = 0
        self.frost_circuit_last_results = []
        self.frost_circuit_state_path = STATE_PATH
        self.frost_circuit_player_saved_pos = None
        self.frost_circuit_player_saved_hpr = None
        self.frost_circuit_obstacles = []
        self.frost_circuit_loop_gates = []
        self.frost_circuit_score = 0
        self.frost_circuit_points_this_run = 0
        self.frost_circuit_total_score = 0
        self.frost_circuit_best_score = 0
        self.frost_circuit_obstacle_hits = 0
        self.frost_circuit_loops_cleared = 0
        self.frost_circuit_last_score_tick = 0.0
        self.frost_circuit_ai_avoidance_events = 0
        self.frost_circuit_score_crystals = []
        self.frost_circuit_crystals_collected = 0
        self.frost_circuit_clean_waypoint_streak = 0
        self.frost_circuit_last_player_rank = None
        self.frost_circuit_rank_bonus_count = 0
        self.frost_circuit_drift_score_bank = 0.0
        self.frost_circuit_boost_score_bank = 0.0
        self.frost_circuit_camera_mode = "far_chase"
        self.frost_circuit_camera_distance = 86.0
        self.frost_circuit_camera_height = 33.0
        self.frost_circuit_camera_lookahead = 58.0
        self.frost_circuit_camera_smooth_pos = None
        self.frost_circuit_camera_smooth_target = None

    def _is_frost_circuit_mode(self, mode):
        data = dict(mode or {})
        manifest = dict(data.get("manifest") or {})
        tokens = " ".join(str(x or "") for x in (
            data.get("name"), data.get("id"), data.get("title"),
            manifest.get("id"), manifest.get("title"), manifest.get("description"),
            manifest.get("host_contract"), manifest.get("preferred_display"),
        )).lower()
        return (
            "frost circuit" in tokens
            or "ice circuit" in tokens
            or "ring race" in tokens
            or "ice race" in tokens
            or str(manifest.get("id") or data.get("id") or "").lower() == "frost_circuit"
            or str(data.get("name") or "").lower() == "frost circuit"
        )

    def _load_state() -> dict:
        _ensure_dirs()
        try:
            if STATE_PATH.exists():
                data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
        except Exception:
            pass
        return {"schema": FROST_CIRCUIT_SCHEMA, "kind": "holoverse_frost_circuit_state", "best_time": None, "wins": 0, "races_completed": 0, "last_results": [], "score_total": 0, "best_score": 0, "last_score": 0, "points_this_run": 0, "loops_cleared": 0, "obstacle_hits": 0, "crystals_collected": 0, "clean_waypoint_streak": 0, "rank_bonus_count": 0}

    def load_frost_circuit_state(self):
        data = _load_state()
        try:
            best = data.get("best_time")
            self.frost_circuit_best_time = None if best in (None, "") else float(best)
        except Exception:
            self.frost_circuit_best_time = None
        try:
            self.frost_circuit_wins = int(data.get("wins") or 0)
        except Exception:
            self.frost_circuit_wins = 0
        try:
            self.frost_circuit_races_completed = int(data.get("races_completed") or 0)
        except Exception:
            self.frost_circuit_races_completed = 0
        self.frost_circuit_last_results = list(data.get("last_results") or [])[:12]
        try:
            self.frost_circuit_total_score = int(data.get("score_total") or data.get("total_score") or 0)
        except Exception:
            self.frost_circuit_total_score = 0
        try:
            self.frost_circuit_best_score = int(data.get("best_score") or 0)
        except Exception:
            self.frost_circuit_best_score = 0
        try:
            self.frost_circuit_loops_cleared = int(data.get("loops_cleared") or 0)
        except Exception:
            self.frost_circuit_loops_cleared = 0
        try:
            self.frost_circuit_obstacle_hits = int(data.get("obstacle_hits") or 0)
        except Exception:
            self.frost_circuit_obstacle_hits = 0
        try:
            self.frost_circuit_crystals_collected = int(data.get("crystals_collected") or 0)
        except Exception:
            self.frost_circuit_crystals_collected = 0
        try:
            self.frost_circuit_rank_bonus_count = int(data.get("rank_bonus_count") or 0)
        except Exception:
            self.frost_circuit_rank_bonus_count = 0
        return data

    def _mirror_progress(self):
        payload = {
            "schema": FROST_CIRCUIT_SCHEMA,
            "best_time": getattr(self, "frost_circuit_best_time", None),
            "wins": int(getattr(self, "frost_circuit_wins", 0) or 0),
            "races_completed": int(getattr(self, "frost_circuit_races_completed", 0) or 0),
            "last_results": list(getattr(self, "frost_circuit_last_results", []) or [])[:8],
            "score_total": int(getattr(self, "frost_circuit_total_score", 0) or 0),
            "best_score": int(getattr(self, "frost_circuit_best_score", 0) or 0),
            "last_score": int(getattr(self, "frost_circuit_score", 0) or 0),
            "points_this_run": int(getattr(self, "frost_circuit_points_this_run", 0) or 0),
            "loops_cleared": int(getattr(self, "frost_circuit_loops_cleared", 0) or 0),
            "obstacle_hits": int(getattr(self, "frost_circuit_obstacle_hits", 0) or 0),
            "crystals_collected": int(getattr(self, "frost_circuit_crystals_collected", 0) or 0),
            "clean_waypoint_streak": int(getattr(self, "frost_circuit_clean_waypoint_streak", 0) or 0),
            "rank_bonus_count": int(getattr(self, "frost_circuit_rank_bonus_count", 0) or 0),
            "ai_avoidance_events": int(getattr(self, "frost_circuit_ai_avoidance_events", 0) or 0),
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
                ice = regions.setdefault("ice", {})
                ice["frost_circuit"] = payload
                data.setdefault("dimension_progress", {})["frost_circuit"] = payload
                score_total = int(getattr(self, "frost_circuit_total_score", 0) or 0)
                data["holoverse_score"] = max(int(data.get("holoverse_score") or 0), score_total)
                data["updated_at"] = datetime.now().isoformat(timespec="seconds")
                path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
            except Exception as exc:
                print(f"frost_circuit_progress_mirror_error:{path}:{exc}")

    def save_frost_circuit_state(self, reason="manual"):
        _ensure_dirs()
        payload = {
            "schema": FROST_CIRCUIT_SCHEMA,
            "kind": "holoverse_frost_circuit_state",
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "reason": str(reason),
            "save_path": str(STATE_PATH),
            "best_time": getattr(self, "frost_circuit_best_time", None),
            "wins": int(getattr(self, "frost_circuit_wins", 0) or 0),
            "races_completed": int(getattr(self, "frost_circuit_races_completed", 0) or 0),
            "last_results": list(getattr(self, "frost_circuit_last_results", []) or [])[:12],
            "score_total": int(getattr(self, "frost_circuit_total_score", 0) or 0),
            "best_score": int(getattr(self, "frost_circuit_best_score", 0) or 0),
            "last_score": int(getattr(self, "frost_circuit_score", 0) or 0),
            "points_this_run": int(getattr(self, "frost_circuit_points_this_run", 0) or 0),
            "loops_cleared": int(getattr(self, "frost_circuit_loops_cleared", 0) or 0),
            "obstacle_hits": int(getattr(self, "frost_circuit_obstacle_hits", 0) or 0),
            "crystals_collected": int(getattr(self, "frost_circuit_crystals_collected", 0) or 0),
            "clean_waypoint_streak": int(getattr(self, "frost_circuit_clean_waypoint_streak", 0) or 0),
            "rank_bonus_count": int(getattr(self, "frost_circuit_rank_bonus_count", 0) or 0),
            "ai_avoidance_events": int(getattr(self, "frost_circuit_ai_avoidance_events", 0) or 0),
            "track": {
                "region": "ICE",
                "r0": ICE_R0,
                "r1": ICE_R1,
                "radius": ICE_TRACK_RADIUS,
                "waypoints": ICE_TRACK_WAYPOINTS,
                "laps": ICE_REQUIRED_LAPS,
            },
        }
        try:
            STATE_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            self.frost_circuit_last_save_at = time.time()
            _mirror_progress(self)
        except Exception as exc:
            print(f"frost_circuit_save_error:{exc}")
        return payload

    def _generate_waypoints(self):
        origin = Vec3(getattr(self, "player_pos", Vec3(ICE_TRACK_RADIUS, 0, 0)))
        start = _angle_from_xy(origin.x, origin.y)
        # Start at the closest track angle but offset half a segment so the first
        # waypoint is ahead of the grid, not directly under the player.
        step = (math.pi * 2.0) / float(ICE_TRACK_WAYPOINTS)
        start = round(start / step) * step
        points = []
        for i in range(ICE_TRACK_WAYPOINTS):
            ang = start + i * step
            x = math.cos(ang) * ICE_TRACK_RADIUS
            y = math.sin(ang) * ICE_TRACK_RADIUS
            floor = _floor_z(self, x, y)
            points.append(Vec3(x, y, floor + 2.2))
        self.frost_circuit_waypoints = points
        return points

    def _frost_runtime_parent(self):
        """Visible parent for Frost Circuit race geometry.

        The default HoloVerse shell can hide world_root while normal numbered
        regions are active.  Frost Circuit must draw into the same visible route
        as the Ice region itself, so race rings and hovercrafts live under render
        instead of the hidden artifact-world root.
        """
        try:
            return self.render
        except Exception:
            return self.world_root

    def _ensure_root(self):
        parent = _frost_runtime_parent(self)
        root = getattr(self, "frost_circuit_root", None)
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
            self.frost_circuit_root = parent.attachNewNode("frost-circuit-runtime")
            self.frost_circuit_root.setTransparency(TransparencyAttrib.MAlpha)
            try:
                self.frost_circuit_root.setPythonTag("frost_circuit_visible_parent", "render")
            except Exception:
                pass
        return self.frost_circuit_root

    def _destroy_visuals(self):
        for attr in ("frost_circuit_root", "frost_circuit_track_root", "frost_circuit_ui_root"):
            try:
                node = getattr(self, attr, None)
                if node is not None and not node.isEmpty():
                    node.removeNode()
            except Exception:
                pass
            setattr(self, attr, None)
        self.frost_circuit_ui_panel = None
        self.frost_circuit_ui_title = None
        self.frost_circuit_ui_status = None
        self.frost_circuit_ui_help = None

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

    def _draw_waypoint_ring(parent, center: Vec3, radius: float, color, name: str, height=0.0):
        pts = []
        for i in range(25):
            a = (math.pi * 2.0) * (i / 24.0)
            pts.append(Vec3(center.x + math.cos(a) * radius, center.y + math.sin(a) * radius, center.z + height))
        return _line_node(parent, name, color, pts, closed=True, thickness=1.28)

    def _add_runtime_box(self, parent, center: Vec3, size: Vec3, color, thickness=0.38, name="frost-box"):
        holder = parent.attachNewNode(str(name))
        try:
            if hasattr(self, "add_box"):
                self.add_box(holder, Vec3(center), Vec3(size), color, float(thickness))
            else:
                raise RuntimeError("host_add_box_unavailable")
        except Exception:
            segs = LineSegs(str(name) + "-fallback")
            segs.setThickness(max(1.0, float(getattr(self.cfg, "line_thickness", 1.6)) * float(thickness)))
            segs.setColor(*color)
            hx, hy, hz = size.x * 0.5, size.y * 0.5, size.z * 0.5
            corners = [
                Vec3(center.x-hx, center.y-hy, center.z-hz), Vec3(center.x+hx, center.y-hy, center.z-hz),
                Vec3(center.x+hx, center.y+hy, center.z-hz), Vec3(center.x-hx, center.y+hy, center.z-hz),
                Vec3(center.x-hx, center.y-hy, center.z+hz), Vec3(center.x+hx, center.y-hy, center.z+hz),
                Vec3(center.x+hx, center.y+hy, center.z+hz), Vec3(center.x-hx, center.y+hy, center.z+hz),
            ]
            for a, b in ((0,1),(1,2),(2,3),(3,0),(4,5),(5,6),(6,7),(7,4),(0,4),(1,5),(2,6),(3,7)):
                segs.moveTo(corners[a]); segs.drawTo(corners[b])
            fallback = holder.attachNewNode(segs.create())
            try:
                fallback.setAntialias(AntialiasAttrib.MLine)
                fallback.setTransparency(TransparencyAttrib.MAlpha)
            except Exception:
                pass
        return holder

    def _add_frost_score(self, amount: int, reason="race"):
        amount = max(0, int(amount or 0))
        if amount <= 0:
            return 0
        self.frost_circuit_score = int(getattr(self, "frost_circuit_score", 0) or 0) + amount
        self.frost_circuit_points_this_run = int(getattr(self, "frost_circuit_points_this_run", 0) or 0) + amount
        self.frost_circuit_total_score = int(getattr(self, "frost_circuit_total_score", 0) or 0) + amount
        self.frost_circuit_best_score = max(int(getattr(self, "frost_circuit_best_score", 0) or 0), int(getattr(self, "frost_circuit_score", 0) or 0))
        self.frost_circuit_last_score_reason = str(reason)
        return amount

    def _course_axes(center: Vec3):
        radial = Vec3(center.x, center.y, 0.0)
        if radial.lengthSquared() > 0.0001:
            radial.normalize()
        else:
            radial = Vec3(1.0, 0.0, 0.0)
        tangent = Vec3(-radial.y, radial.x, 0.0)
        if tangent.lengthSquared() > 0.0001:
            tangent.normalize()
        return radial, tangent

    def _build_loop_gate(app, parent, spec: dict):
        center = Vec3(spec.get("center", Vec3()))
        radial = Vec3(spec.get("radial", Vec3(1, 0, 0)))
        radius = float(spec.get("radius", 34.0))
        color = tuple(spec.get("color") or (0.78, 0.50, 1.0, 0.82))
        accent = tuple(spec.get("accent") or (0.18, 1.0, 1.0, 0.72))
        pts_outer, pts_inner = [], []
        for i in range(73):
            a = math.tau * i / 72.0
            pts_outer.append(center + radial * (math.cos(a) * radius) + Vec3(0, 0, math.sin(a) * radius))
            pts_inner.append(center + radial * (math.cos(a) * radius * 0.70) + Vec3(0, 0, math.sin(a) * radius * 0.70))
        _line_node(parent, f"frost-loop-outer-{spec.get('id','x')}", color, pts_outer, closed=True, thickness=2.3)
        _line_node(parent, f"frost-loop-inner-{spec.get('id','x')}", accent, pts_inner, closed=True, thickness=1.4)
        foot_z = center.z - radius
        for side in (-1, 1):
            base = center + radial * side * (radius * 0.88)
            _add_runtime_box(app, parent, Vec3(base.x, base.y, foot_z + radius * 0.30), Vec3(5.2, 5.2, radius * 0.60), accent, 0.32, f"frost-loop-post-{spec.get('id','x')}-{side}")

    def _build_score_crystal(app, parent, spec: dict):
        center = Vec3(spec.get("center", Vec3()))
        radius = float(spec.get("radius", 16.0))
        color = tuple(spec.get("color") or (0.52, 1.0, 1.0, 0.78))
        hot = tuple(spec.get("hot") or (1.0, 1.0, 1.0, 0.88))
        holder = parent.attachNewNode(f"frost-score-crystal-{spec.get('id','x')}")
        holder.setTransparency(TransparencyAttrib.MAlpha)
        spec["node"] = holder
        # Floating diamond body.  It sits well above the surface so it reads as a pickup,
        # not another ground obstacle.
        top = center + Vec3(0, 0, radius * 0.62)
        bottom = center - Vec3(0, 0, radius * 0.62)
        left = center + Vec3(-radius * 0.55, 0, 0)
        right = center + Vec3(radius * 0.55, 0, 0)
        front = center + Vec3(0, radius * 0.55, 0)
        back = center + Vec3(0, -radius * 0.55, 0)
        diamond = LineSegs(f"frost-score-crystal-wire-{spec.get('id','x')}")
        diamond.setThickness(2.1)
        diamond.setColor(*hot)
        for a, b in ((top,left),(top,right),(top,front),(top,back),(bottom,left),(bottom,right),(bottom,front),(bottom,back),(left,front),(front,right),(right,back),(back,left)):
            diamond.moveTo(a); diamond.drawTo(b)
        node = holder.attachNewNode(diamond.create())
        try:
            node.setAntialias(AntialiasAttrib.MLine)
            node.setTransparency(TransparencyAttrib.MAlpha)
        except Exception:
            pass
        _draw_waypoint_ring(holder, center, radius * 0.92, color, f"frost-score-crystal-ring-{spec.get('id','x')}", height=-radius * 0.54)
        return holder

    def _generate_score_crystals(self):
        wps = list(getattr(self, "frost_circuit_waypoints", []) or [])
        if not wps:
            self.frost_circuit_score_crystals = []
            return []
        rng = random.Random(884021 + int(time.time()) % 997)
        crystals = []
        slots = []
        step = max(1, len(wps) // max(1, ICE_SCORE_CRYSTAL_COUNT))
        for i in range(ICE_SCORE_CRYSTAL_COUNT):
            slots.append((1 + i * step + (i % 3)) % len(wps))
        for idx, slot in enumerate(slots[:ICE_SCORE_CRYSTAL_COUNT]):
            wp = Vec3(wps[slot])
            radial, tangent = _course_axes(wp)
            offset = rng.choice([-1.0, 1.0]) * rng.uniform(22.0, 76.0)
            drift = rng.uniform(-20.0, 22.0)
            center_xy = wp + radial * offset + tangent * drift
            floor = _floor_z(self, center_xy.x, center_xy.y)
            color = (0.36 + rng.random() * 0.22, 0.86 + rng.random() * 0.12, 1.0, 0.76)
            hot = (0.92, 1.0, 1.0, 0.92) if idx % 3 else (1.0, 0.76, 1.0, 0.90)
            crystals.append({
                "id": idx,
                "center": Vec3(center_xy.x, center_xy.y, floor + ICE_HOVER_BASE_CLEARANCE + 4.8),
                "radius": rng.uniform(12.0, 17.0),
                "value": ICE_CRYSTAL_SCORE + (idx % 4) * 15,
                "active": True,
                "color": color,
                "hot": hot,
            })
        self.frost_circuit_score_crystals = crystals
        return crystals

    def _build_score_crystal_visuals(self, parent):
        crystal_root = parent.attachNewNode("frost-circuit-score-crystals")
        crystal_root.setTransparency(TransparencyAttrib.MAlpha)
        for spec in _generate_score_crystals(self):
            _build_score_crystal(self, crystal_root, spec)
        return crystal_root

    def _update_score_crystals(self, racer):
        if not bool(racer.get("is_player", False)):
            return
        pos = Vec3(racer.get("pos", Vec3()))
        for spec in list(getattr(self, "frost_circuit_score_crystals", []) or []):
            if not bool(spec.get("active", True)):
                continue
            center = Vec3(spec.get("center", Vec3()))
            dxy = math.sqrt((pos.x - center.x) ** 2 + (pos.y - center.y) ** 2)
            dz = abs(pos.z - center.z)
            radius = float(spec.get("radius", 15.0)) + 13.0
            if dxy <= radius and dz <= max(18.0, radius * 1.45):
                spec["active"] = False
                node = spec.get("node")
                try:
                    if node is not None and not node.isEmpty():
                        node.hide()
                except Exception:
                    pass
                self.frost_circuit_crystals_collected = int(getattr(self, "frost_circuit_crystals_collected", 0) or 0) + 1
                gained = _add_frost_score(self, int(spec.get("value", ICE_CRYSTAL_SCORE)), reason="ice_crystal")
                try:
                    self.center_hint["text"] = f"FROST CIRCUIT // ICE CHARGE +{gained} SAVED TO RUN"
                except Exception:
                    pass

    def _build_cube_formation(app, parent, spec: dict):
        center = Vec3(spec.get("center", Vec3()))
        rng = random.Random(int(spec.get("seed", 1)))
        base = tuple(spec.get("color") or (0.56, 0.92, 1.0, 0.42))
        accent = tuple(spec.get("accent") or (0.76, 0.50, 1.0, 0.48))
        hot = tuple(spec.get("hot") or (0.12, 1.0, 1.0, 0.52))
        height = float(spec.get("height", 42.0))
        width = float(spec.get("width", 26.0))
        _add_runtime_box(app, parent, center + Vec3(0, 0, height * 0.22), Vec3(width, width, height * 0.44), base, 0.44, f"ice-obstacle-base-{spec.get('id','x')}")
        _add_runtime_box(app, parent, center + Vec3(width * 0.18, -width * 0.16, height * 0.64), Vec3(width * 0.74, width * 0.74, height * 0.42), accent, 0.38, f"ice-obstacle-cap-{spec.get('id','x')}")
        if rng.random() < 0.72:
            _add_runtime_box(app, parent, center + Vec3(-width * 0.46, width * 0.24, height * 0.40), Vec3(width * 0.38, width * 0.38, height * 0.36), hot, 0.30, f"ice-obstacle-side-{spec.get('id','x')}")
        _line_node(parent, f"ice-obstacle-neon-brace-{spec.get('id','x')}", hot, [center + Vec3(-width*0.62, -width*0.62, height*0.10), center + Vec3(width*0.58, width*0.38, height*1.02)], closed=False, thickness=1.25)

    def _generate_course_features(self):
        wps = list(getattr(self, "frost_circuit_waypoints", []) or [])
        if not wps:
            self.frost_circuit_obstacles = []
            self.frost_circuit_loop_gates = []
            return [], []
        start_ang = _angle_from_xy(wps[0].x, wps[0].y)
        rng = random.Random(513507 + int(start_ang * 1000.0))
        obstacles = []
        colors = [
            ((0.52, 0.96, 1.0, 0.42), (0.76, 0.50, 1.0, 0.48), (0.16, 1.0, 1.0, 0.56)),
            ((0.70, 0.84, 1.0, 0.38), (1.0, 0.42, 0.92, 0.44), (0.96, 1.0, 1.0, 0.52)),
            ((0.48, 0.78, 1.0, 0.40), (0.90, 0.64, 1.0, 0.44), (0.30, 1.0, 0.82, 0.54)),
        ]
        seeded_slots = [2, 4, 6, 8, 11, 13, 15, 18, 20, 23, 25, 27]
        while len(seeded_slots) < ICE_OBSTACLE_COUNT:
            v = rng.randrange(1, max(2, len(wps)))
            if v not in seeded_slots:
                seeded_slots.append(v)
        for idx, slot in enumerate(seeded_slots[:ICE_OBSTACLE_COUNT]):
            wp = Vec3(wps[slot % len(wps)])
            radial, tangent = _course_axes(wp)
            offset = rng.choice([-1.0, 1.0]) * rng.uniform(58.0, 136.0)
            if idx < 4:
                offset = [-86.0, 112.0, -138.0, 72.0][idx]
            center_xy = wp + radial * offset + tangent * rng.uniform(-38.0, 42.0)
            floor = _floor_z(self, center_xy.x, center_xy.y)
            width = rng.uniform(22.0, 42.0)
            height = rng.uniform(28.0, 68.0)
            color, accent, hot = colors[idx % len(colors)]
            obstacles.append({"id": idx, "center": Vec3(center_xy.x, center_xy.y, floor), "radius": width * 0.90, "width": width, "height": height, "seed": rng.randint(1000, 999999), "color": color, "accent": accent, "hot": hot})
        gates = []
        for idx, slot in enumerate([3, 8, 14, 19, 24][:ICE_LOOP_GATE_COUNT]):
            wp = Vec3(wps[slot % len(wps)])
            radial, tangent = _course_axes(wp)
            floor = _floor_z(self, wp.x, wp.y)
            gates.append({"id": idx, "center": Vec3(wp.x, wp.y, floor + 24.0), "normal": tangent, "radial": radial, "radius": 38.0, "scored": False, "color": (0.78, 0.50, 1.0, 0.84), "accent": (0.12, 1.0, 1.0, 0.76)})
        self.frost_circuit_obstacles = obstacles
        self.frost_circuit_loop_gates = gates
        return obstacles, gates

    def _build_course_feature_visuals(self):
        root = getattr(self, "frost_circuit_track_root", None) or _ensure_root(self)
        obstacles, gates = _generate_course_features(self)
        feature_root = root.attachNewNode("frost-circuit-obstacles-and-loops")
        feature_root.setTransparency(TransparencyAttrib.MAlpha)
        for spec in obstacles:
            _build_cube_formation(self, feature_root, spec)
        for spec in gates:
            _build_loop_gate(self, feature_root, spec)
        _build_score_crystal_visuals(self, feature_root)
        try:
            feature_root.setPythonTag("frost_obstacle_count", len(obstacles))
            feature_root.setPythonTag("frost_loop_gate_count", len(gates))
        except Exception:
            pass
        return feature_root

    def _obstacle_avoidance(self, pos: Vec3, yaw: float, lookahead: float = 190.0):
        forward = _heading_vec(yaw)
        right = Vec3(math.cos(math.radians(yaw)), -math.sin(math.radians(yaw)), 0.0)
        steer = 0.0
        slow = 1.0
        threat_count = 0
        for spec in list(getattr(self, "frost_circuit_obstacles", []) or []):
            center = Vec3(spec.get("center", Vec3()))
            rel = center - pos
            rel.z = 0.0
            along = rel.dot(forward)
            if along < -18.0 or along > lookahead:
                continue
            lateral = rel.dot(right)
            clearance = float(spec.get("radius", 28.0)) + 48.0
            if abs(lateral) < clearance:
                away = -1.0 if lateral >= 0.0 else 1.0
                strength = (clearance - abs(lateral)) / max(1.0, clearance)
                steer += away * strength
                slow = min(slow, 0.66 - min(0.28, strength * 0.30))
                threat_count += 1
        return max(-1.0, min(1.0, steer)), max(0.34, min(1.0, slow)), threat_count

    def _keep_racer_on_track(self, racer):
        pos = Vec3(racer.get("pos", Vec3()))
        radius = math.sqrt(pos.x * pos.x + pos.y * pos.y)
        if radius <= 0.001:
            return
        if radius < ICE_R0 + 45.0 or radius > ICE_R1 - 45.0:
            target_r = max(ICE_R0 + 90.0, min(ICE_R1 - 90.0, radius))
            radial = Vec3(pos.x / radius, pos.y / radius, 0.0)
            pos.x = radial.x * target_r
            pos.y = radial.y * target_r
            racer["pos"] = pos
            racer["speed"] = float(racer.get("speed", 0.0)) * 0.82

    def _apply_obstacle_collision(self, racer, is_player=False):
        pos = Vec3(racer.get("pos", Vec3()))
        for spec in list(getattr(self, "frost_circuit_obstacles", []) or []):
            center = Vec3(spec.get("center", Vec3()))
            dx = pos.x - center.x
            dy = pos.y - center.y
            dist = math.sqrt(dx * dx + dy * dy)
            limit = float(spec.get("radius", 28.0)) + (12.0 if is_player else 10.0)
            if dist <= 0.001 or dist >= limit:
                continue
            push = Vec3(dx / dist, dy / dist, 0.0)
            pos.x = center.x + push.x * limit
            pos.y = center.y + push.y * limit
            racer["pos"] = pos
            racer["speed"] = -abs(float(racer.get("speed", 0.0))) * (0.18 if is_player else 0.10)
            if is_player:
                self.frost_circuit_obstacle_hits = int(getattr(self, "frost_circuit_obstacle_hits", 0) or 0) + 1
                self.frost_circuit_clean_waypoint_streak = 0
                try:
                    self.center_hint["text"] = "FROST CIRCUIT // OBSTACLE HIT - DRIVE AROUND THE ICE FORMATIONS"
                except Exception:
                    pass
            return True
        return False

    def _update_loop_gate_score(self, racer):
        if not bool(racer.get("is_player", False)):
            return
        pos = Vec3(racer.get("pos", Vec3()))
        for spec in list(getattr(self, "frost_circuit_loop_gates", []) or []):
            if bool(spec.get("scored", False)):
                continue
            center = Vec3(spec.get("center", Vec3()))
            normal = Vec3(spec.get("normal", Vec3(0, 1, 0)))
            radial = Vec3(spec.get("radial", Vec3(1, 0, 0)))
            rel = pos - center
            plane_dist = abs(rel.dot(normal))
            lateral = rel.dot(radial)
            vertical = rel.z
            radius = float(spec.get("radius", 38.0))
            if plane_dist < 28.0 and (lateral * lateral + vertical * vertical) <= (radius * 0.82) ** 2:
                spec["scored"] = True
                self.frost_circuit_loops_cleared = int(getattr(self, "frost_circuit_loops_cleared", 0) or 0) + 1
                gained = _add_frost_score(self, ICE_LOOP_SCORE, reason="loop_gate")
                try:
                    self.center_hint["text"] = f"FROST CIRCUIT // LOOP CLEAN +{gained}"
                except Exception:
                    pass

    def _build_track_visuals(self):
        root = _ensure_root(self)
        try:
            if getattr(self, "frost_circuit_track_root", None) is not None and not self.frost_circuit_track_root.isEmpty():
                self.frost_circuit_track_root.removeNode()
        except Exception:
            pass
        track = root.attachNewNode("frost-circuit-track")
        track.setTransparency(TransparencyAttrib.MAlpha)
        self.frost_circuit_track_root = track
        wps = list(getattr(self, "frost_circuit_waypoints", []) or [])
        if not wps:
            return
        _line_node(track, "frost-racing-line", (0.32, 0.84, 1.0, 0.55), wps, closed=True, thickness=max(1.0, float(getattr(self.cfg, "line_thickness", 1.6)) * 0.7))
        for idx, wp in enumerate(wps):
            if idx == 0:
                color = (1.0, 1.0, 1.0, 0.9)
                radius = 34.0
            elif idx % 4 == 0:
                color = (0.36, 0.95, 1.0, 0.68)
                radius = 22.0
            else:
                color = (0.24, 0.68, 1.0, 0.38)
                radius = 13.0
            _draw_waypoint_ring(track, wp, radius, color, f"frost-waypoint-{idx}")
        # Finish gate posts at waypoint 0.
        start = wps[0]
        tangent = Vec3(-start.y, start.x, 0)
        if tangent.lengthSquared() > 0:
            tangent.normalize()
        left = start + tangent * 42.0
        right = start - tangent * 42.0
        gate_pts = [left, left + Vec3(0, 0, 42), right + Vec3(0, 0, 42), right]
        _line_node(track, "frost-finish-gate", (1.0, 1.0, 1.0, 0.92), gate_pts, closed=False, thickness=max(1.0, float(getattr(self.cfg, "line_thickness", 1.6)) * 1.2))
        _build_course_feature_visuals(self)

    def _build_hovercraft_node(self, parent, racer):
        """Build a larger arcade hovercraft silhouette instead of a small box stack.

        The earlier craft read as small wire boxes from the race camera.  This
        version keeps the same lightweight line/box helpers, but scales the body
        up into a clear sled shape with outriggers, nose wedge, engine glow, and
        speed fins so it reads as a vehicle at full ice-ring distance.
        """
        rng = random.Random(int(racer.get("seed", 1)))
        name = str(racer.get("name") or "Racer")
        is_player = bool(racer.get("is_player", False))
        color = tuple(racer.get("color") or _hovercraft_color(name))
        accent = (min(1.0, color[0] + 0.20), min(1.0, color[1] + 0.20), min(1.0, color[2] + 0.20), 0.90)
        hot = (0.16, 1.0, 1.0, 0.88) if is_player else (1.0, 0.36 + rng.random() * 0.34, 1.0, 0.78)
        scale = ICE_CRAFT_VISUAL_SCALE * (1.14 if is_player else rng.uniform(0.94, 1.06))
        width = (7.6 + rng.random() * 1.8) * scale
        length = (16.8 + rng.random() * 3.8) * scale
        height = 1.75 * scale
        root = parent.attachNewNode(f"frost-hovercraft-3d-{name}")
        root.setTransparency(TransparencyAttrib.MAlpha)
        # Main sled: long hull, raised cockpit, broad rear engine, and outriggers.
        _add_runtime_box(self, root, Vec3(0.0, 0.0, 0.20 * scale), Vec3(width * 1.28, length * 0.92, height), color, 0.58, f"craft-hull-{name}")
        _add_runtime_box(self, root, Vec3(0.0, length * 0.20, 1.08 * scale), Vec3(width * 0.62, length * 0.32, height * 0.86), accent, 0.46, f"craft-cockpit-{name}")
        _add_runtime_box(self, root, Vec3(0.0, -length * 0.48, 0.76 * scale), Vec3(width * 1.04, length * 0.24, height * 0.72), hot, 0.40, f"craft-engine-{name}")
        _add_runtime_box(self, root, Vec3(0.0, length * 0.55, 0.34 * scale), Vec3(width * 0.52, length * 0.18, height * 0.42), accent, 0.34, f"craft-nose-core-{name}")
        for sx in (-1, 1):
            _add_runtime_box(self, root, Vec3(sx * width * 0.86, -length * 0.04, -0.64 * scale), Vec3(width * 0.22, length * 0.86, height * 0.30), accent, 0.34, f"craft-hover-rail-{name}-{sx}")
            _add_runtime_box(self, root, Vec3(sx * width * 0.74, length * 0.42, 0.56 * scale), Vec3(width * 0.22, length * 0.34, height * 0.82), color, 0.32, f"craft-front-fin-{name}-{sx}")
            _add_runtime_box(self, root, Vec3(sx * width * 0.66, -length * 0.58, 1.08 * scale), Vec3(width * 0.23, length * 0.22, height * 1.08), hot, 0.30, f"craft-tail-fin-{name}-{sx}")
            _add_runtime_box(self, root, Vec3(sx * width * 1.07, -length * 0.20, 0.18 * scale), Vec3(width * 0.18, length * 0.28, height * 0.44), hot, 0.28, f"craft-side-thruster-{name}-{sx}")
        # Wedge silhouette: this gives the craft a nose and readable forward direction.
        segs = LineSegs(f"craft-wire-{name}")
        segs.setThickness(max(1.0, float(getattr(self.cfg, "line_thickness", 1.6)) * (1.18 if is_player else 1.02)))
        segs.setColor(*hot)
        nose = Vec3(0, length * 0.72, 0.90 * scale)
        left = Vec3(-width * 1.02, length * 0.05, 0.06 * scale)
        right = Vec3(width * 1.02, length * 0.05, 0.06 * scale)
        tail = Vec3(0, -length * 0.76, 0.28 * scale)
        crown = Vec3(0, length * 0.12, 2.28 * scale)
        for a, b in ((nose,left),(left,tail),(tail,right),(right,nose),(left,right),(nose,tail),(left,crown),(crown,right),(crown,nose)):
            segs.moveTo(a); segs.drawTo(b)
        glow = root.attachNewNode(segs.create())
        try:
            glow.setAntialias(AntialiasAttrib.MLine)
            glow.setTransparency(TransparencyAttrib.MAlpha)
        except Exception:
            pass
        # Readable player crown and bot ID marker, but no solid UI box.
        marker = LineSegs(f"craft-crown-{name}")
        marker.setThickness(max(1.0, float(getattr(self.cfg, "line_thickness", 1.6)) * (0.88 if is_player else 0.66)))
        marker.setColor(*(hot if is_player else accent))
        marker_z = 2.95 * scale
        marker.moveTo(-width * 0.36, -0.04 * length, marker_z); marker.drawTo(0, length * 0.12, marker_z + 1.18 * scale); marker.drawTo(width * 0.36, -0.04 * length, marker_z)
        cn = root.attachNewNode(marker.create())
        try:
            cn.setAntialias(AntialiasAttrib.MLine)
            cn.setTransparency(TransparencyAttrib.MAlpha)
        except Exception:
            pass
        # Hover shadow/glow and long engine streaks make motion more fun from the chase camera.
        hover = LineSegs(f"craft-hover-glow-{name}")
        hover.setThickness(max(1.0, float(getattr(self.cfg, "line_thickness", 1.6)) * 0.92))
        hover.setColor(0.48, 0.96, 1.0, 0.46 if is_player else 0.34)
        for i in range(73):
            a = math.tau * i / 72.0
            p = Vec3(math.cos(a) * width * 1.16, math.sin(a) * length * 0.42, -1.34 * scale)
            if i == 0:
                hover.moveTo(p)
            else:
                hover.drawTo(p)
        hnp = root.attachNewNode(hover.create())
        try:
            hnp.setAntialias(AntialiasAttrib.MLine)
            hnp.setTransparency(TransparencyAttrib.MAlpha)
        except Exception:
            pass
        stream = LineSegs(f"craft-speed-stream-{name}")
        stream.setThickness(max(1.0, float(getattr(self.cfg, "line_thickness", 1.6)) * (0.78 if is_player else 0.52)))
        stream.setColor(*hot)
        for sx in (-0.52, 0.0, 0.52):
            y0 = -length * 0.62
            z0 = -0.02 * scale + abs(sx) * 0.16 * scale
            stream.moveTo(Vec3(width * sx, y0, z0))
            stream.drawTo(Vec3(width * sx * 1.08, y0 - length * 0.82, z0 - 0.10 * scale))
            stream.drawTo(Vec3(width * sx * 0.74, y0 - length * 1.28, z0 - 0.22 * scale))
        snp = root.attachNewNode(stream.create())
        try:
            snp.setAntialias(AntialiasAttrib.MLine)
            snp.setTransparency(TransparencyAttrib.MAlpha)
        except Exception:
            pass
        racer["node"] = root
        racer["visual_scale"] = scale
        racer["collision_radius"] = max(width * 0.72, length * 0.46)
        return root

    def _update_hovercraft_node(self, racer):
        node = racer.get("node")
        if node is None or node.isEmpty():
            node = _build_hovercraft_node(self, _ensure_root(self), racer)
        pos = Vec3(racer.get("pos", Vec3(0, 0, 0)))
        try:
            node.setPos(pos)
            speed = abs(float(racer.get("speed", 0.0)))
            bank = max(-22.0, min(22.0, float(racer.get("steer_bank", 0.0))))
            pitch = max(-9.0, min(13.0, speed * 0.030))
            node.setHpr(float(racer.get("yaw", 0.0)), pitch, bank)
        except Exception:
            pass

    def _setup_racers(self):
        wps = list(getattr(self, "frost_circuit_waypoints", []) or _generate_waypoints(self))
        start = Vec3(wps[0])
        target = Vec3(wps[1]) if len(wps) > 1 else start + Vec3(0, 100, 0)
        base_yaw = _yaw_to_target(start, target)
        tangent = _heading_vec(base_yaw)
        radial = Vec3(start.x, start.y, 0)
        if radial.lengthSquared() > 0:
            radial.normalize()
        else:
            radial = Vec3(1, 0, 0)
        names = ["Player"] + list(BOT_RACERS)
        racers = []
        for idx, name in enumerate(names):
            lane = (idx - (len(names) - 1) * 0.5) * 24.0
            row = (idx // 4) * -38.0
            pos = start + radial * lane + tangent * row
            floor = _floor_z(self, pos.x, pos.y)
            seed = random.randint(10000, 999999999)
            max_speed = ICE_PLAYER_MAX_SPEED if name == "Player" else random.uniform(92.0, 122.0)
            accel = ICE_PLAYER_ACCEL if name == "Player" else random.uniform(54.0, 72.0)
            handling = 1.34 if name == "Player" else random.uniform(0.94, 1.20)
            racer = {
                "name": name,
                "is_player": name == "Player",
                "seed": seed,
                "color": _hovercraft_color(name),
                "pos": Vec3(pos.x, pos.y, floor + ICE_HOVER_BASE_CLEARANCE),
                "yaw": base_yaw,
                "speed": 0.0,
                "max_speed": max_speed,
                "accel": accel,
                "handling": handling,
                "current_wp": 1,
                "lap": 0,
                "finished": False,
                "finish_time": None,
                "steer_bank": 0.0,
                "last_wp_time": time.time(),
            }
            racers.append(racer)
        self.frost_circuit_racers = racers
        for racer in racers:
            _build_hovercraft_node(self, _ensure_root(self), racer)
        return racers

    def _advance_racer_waypoint(self, racer, now):
        if bool(racer.get("finished", False)):
            return
        wps = list(getattr(self, "frost_circuit_waypoints", []) or [])
        if not wps:
            return
        idx = int(racer.get("current_wp", 0)) % len(wps)
        target = wps[idx]
        dist = _dist2d(Vec3(racer.get("pos", Vec3())), target)
        if dist > 115.0:
            return
        is_player = bool(racer.get("is_player", False))
        if is_player:
            speed_bonus = int(max(0.0, abs(float(racer.get("speed", 0.0)))) * 0.10)
            base_gain = _add_frost_score(self, ICE_WAYPOINT_SCORE + speed_bonus, reason="waypoint")
            hit_total = int(getattr(self, "frost_circuit_obstacle_hits", 0) or 0)
            last_hit_total = int(racer.get("last_waypoint_hit_total", hit_total))
            if hit_total == last_hit_total:
                self.frost_circuit_clean_waypoint_streak = int(getattr(self, "frost_circuit_clean_waypoint_streak", 0) or 0) + 1
                if self.frost_circuit_clean_waypoint_streak >= 3:
                    streak_bonus = ICE_CLEAN_STREAK_SCORE + min(260, (self.frost_circuit_clean_waypoint_streak - 3) * 18)
                    _add_frost_score(self, streak_bonus, reason="clean_waypoint_streak")
                    try:
                        self.center_hint["text"] = f"FROST CIRCUIT // CLEAN STREAK x{self.frost_circuit_clean_waypoint_streak} +{streak_bonus}"
                    except Exception:
                        pass
            else:
                self.frost_circuit_clean_waypoint_streak = 0
            racer["last_waypoint_hit_total"] = hit_total
        idx += 1
        if idx >= len(wps):
            idx = 0
            racer["lap"] = int(racer.get("lap", 0)) + 1
            if is_player:
                _add_frost_score(self, 220, reason="lap_checkpoint")
        racer["current_wp"] = idx
        racer["last_wp_time"] = now
        if int(racer.get("lap", 0)) >= ICE_REQUIRED_LAPS and idx == 0:
            racer["finished"] = True
            racer["finish_time"] = max(0.0, now - float(getattr(self, "frost_circuit_started_at", now)))

    def _update_racer_height(self, racer, dt):
        pos = Vec3(racer.get("pos", Vec3()))
        floor = _floor_z(self, pos.x, pos.y)
        speed = abs(float(racer.get("speed", 0.0)))
        bob = math.sin(time.time() * 4.0 + int(racer.get("seed", 0)) * 0.01) * 0.18
        lift = ICE_HOVER_BASE_CLEARANCE + min(ICE_HOVER_SPEED_LIFT, speed * 0.034) + bob
        # Keep the craft visibly above the ice.  The vehicle mesh has rails below
        # its origin, so the origin needs real clearance or the body appears to
        # sink through uneven ice tiles.
        target_z = floor + lift
        pos.z += (target_z - pos.z) * min(1.0, dt * 7.0)
        racer["pos"] = pos

    def _update_player_racer(self, racer, dt):
        keys = getattr(self, "keys", {})
        accel = 0.0
        if keys.get("w") or keys.get("arrow_up"):
            accel += 1.0
        if keys.get("s") or keys.get("arrow_down"):
            accel -= 0.55
        boost = bool(keys.get("shift")) and accel > 0.0
        brake = bool(keys.get("space"))
        max_speed = float(racer.get("max_speed", ICE_PLAYER_MAX_SPEED)) * (ICE_PLAYER_BOOST_MULTIPLIER if boost else 1.0)
        speed = float(racer.get("speed", 0.0))
        speed += accel * float(racer.get("accel", ICE_PLAYER_ACCEL)) * (1.48 if boost else 1.0) * dt
        if brake:
            speed *= max(0.0, 1.0 - dt * 1.55)
        else:
            # Lower drag makes the hovercraft feel like a fast sled instead of a box
            # that stops fighting the player between key taps.
            speed *= max(0.0, 1.0 - dt * 0.14)
        speed = max(-26.0, min(max_speed, speed))
        steer_input = (1.0 if (keys.get("d") or keys.get("arrow_right")) else 0.0) - (1.0 if (keys.get("a") or keys.get("arrow_left")) else 0.0)
        if boost and speed > 82.0:
            self.frost_circuit_boost_score_bank = float(getattr(self, "frost_circuit_boost_score_bank", 0.0) or 0.0) + dt
            if self.frost_circuit_boost_score_bank >= 1.0:
                seconds = int(self.frost_circuit_boost_score_bank)
                self.frost_circuit_boost_score_bank -= seconds
                _add_frost_score(self, ICE_BOOST_SCORE_PER_SECOND * seconds, reason="boost_chain")
        if brake and abs(steer_input) > 0.35 and abs(speed) > 42.0:
            self.frost_circuit_drift_score_bank = float(getattr(self, "frost_circuit_drift_score_bank", 0.0) or 0.0) + dt
            if self.frost_circuit_drift_score_bank >= 1.0:
                seconds = int(self.frost_circuit_drift_score_bank)
                self.frost_circuit_drift_score_bank -= seconds
                _add_frost_score(self, ICE_DRIFT_SCORE_PER_SECOND * seconds, reason="drift_chain")
        else:
            self.frost_circuit_drift_score_bank = max(0.0, float(getattr(self, "frost_circuit_drift_score_bank", 0.0) or 0.0) - dt * 0.35)
        avoid, slow, _threats = _obstacle_avoidance(self, Vec3(racer.get("pos", Vec3())), float(racer.get("yaw", 0.0)), lookahead=128.0)
        if abs(avoid) > 0.15 and abs(steer_input) < 0.1:
            steer_input += avoid * 0.20
            speed *= min(1.0, 0.94 + slow * 0.06)
        handling = float(racer.get("handling", 1.34) or 1.34)
        low_speed_help = 0.68 + min(0.92, abs(speed) / 122.0)
        turn_rate = 132.0 * handling * low_speed_help
        if brake:
            turn_rate *= 1.46
        if boost and abs(speed) > 96.0:
            turn_rate *= 0.88
        # Smooth steering avoids the old twitchy box-on-ice feeling while keeping
        # enough authority for ring turns and recovery.
        prev_steer = float(racer.get("steer_input_smooth", 0.0) or 0.0)
        steer_smooth = prev_steer + (steer_input - prev_steer) * min(1.0, dt * 8.4)
        racer["steer_input_smooth"] = steer_smooth
        yaw = float(racer.get("yaw", 0.0)) + steer_smooth * turn_rate * dt
        forward = _heading_vec(yaw)
        pos = Vec3(racer.get("pos", Vec3())) + forward * speed * dt
        radius = math.sqrt(pos.x * pos.x + pos.y * pos.y)
        if radius > 0.001:
            radial = Vec3(pos.x / radius, pos.y / radius, 0.0)
            track_error = radius - ICE_TRACK_RADIUS
            # Gentle centerline pull keeps the race readable and fun without
            # replacing steering. It mainly prevents wide spin-outs from becoming
            # tedious wall scrapes.
            if abs(track_error) > 85.0 and not brake:
                correction = max(-42.0, min(42.0, track_error * ICE_TRACK_CENTERING_ASSIST * dt))
                pos -= radial * correction
        racer["yaw"] = yaw % 360.0
        racer["speed"] = speed
        racer["pos"] = pos
        racer["steer_bank"] = -steer_smooth * min(22.0, abs(speed) * 0.18)
        _keep_racer_on_track(self, racer)
        _apply_obstacle_collision(self, racer, is_player=True)
        _update_loop_gate_score(self, racer)
        _update_score_crystals(self, racer)
        _update_racer_height(self, racer, dt)

    def _update_bot_racer(self, racer, dt):
        if bool(racer.get("finished", False)):
            racer["speed"] = float(racer.get("speed", 0.0)) * max(0.0, 1.0 - dt * 1.2)
            _update_racer_height(self, racer, dt)
            return
        wps = list(getattr(self, "frost_circuit_waypoints", []) or [])
        if not wps:
            return
        idx = int(racer.get("current_wp", 0)) % len(wps)
        target = Vec3(wps[idx])
        next_target = Vec3(wps[(idx + 1) % len(wps)])
        pos = Vec3(racer.get("pos", Vec3()))
        dist = _dist2d(pos, target)
        look_blend = max(0.0, min(0.42, (190.0 - dist) / 330.0))
        target = target * (1.0 - look_blend) + next_target * look_blend
        desired = _yaw_to_target(pos, target)
        current_yaw = float(racer.get("yaw", 0.0))
        avoid, slow, threats = _obstacle_avoidance(self, pos, current_yaw, lookahead=190.0 + abs(float(racer.get("speed", 0.0))) * 1.15)
        if threats:
            self.frost_circuit_ai_avoidance_events = int(getattr(self, "frost_circuit_ai_avoidance_events", 0) or 0) + int(threats)
            desired += avoid * 48.0
        for other in list(getattr(self, "frost_circuit_racers", []) or []):
            if other is racer:
                continue
            other_pos = Vec3(other.get("pos", Vec3()))
            sep = other_pos - pos
            sep.z = 0.0
            d2 = sep.lengthSquared()
            if 1.0 < d2 < 48.0 * 48.0:
                side = 1.0 if (int(racer.get("seed", 0)) + int(other.get("seed", 0))) % 2 else -1.0
                desired += side * 16.0 * (1.0 - math.sqrt(d2) / 48.0)
        diff = _wrap_deg(desired - current_yaw)
        handling = float(racer.get("handling", 1.0))
        max_turn = (82.0 + handling * 32.0) * dt
        turn = max(-max_turn, min(max_turn, diff))
        yaw = (current_yaw + turn) % 360.0
        speed = float(racer.get("speed", 0.0))
        max_speed = float(racer.get("max_speed", 88.0))
        rankings = _race_rankings(self)
        try:
            rank = rankings.index(racer) + 1
        except Exception:
            rank = len(rankings)
        catchup = 1.0 + max(0, rank - 3) * 0.035
        corner_slow = 1.0 - min(0.50, abs(diff) / 150.0)
        target_speed = max_speed * catchup * corner_slow * slow
        if threats and abs(diff) < 45.0:
            target_speed *= 0.82
        elif (int(time.time() * 2.0 + int(racer.get("seed", 0))) % 17) == 0 and abs(diff) < 18.0:
            target_speed *= 1.09
        speed_blend = min(1.0, dt * (2.05 if not threats else 2.85))
        speed = speed * (1.0 - speed_blend) + target_speed * speed_blend
        forward = _heading_vec(yaw)
        pos = pos + forward * speed * dt
        racer["yaw"] = yaw
        racer["speed"] = speed
        racer["pos"] = pos
        racer["steer_bank"] = -max(-1.0, min(1.0, turn / max(max_turn, 0.001))) * min(16.0, abs(speed) * 0.16)
        _keep_racer_on_track(self, racer)
        _apply_obstacle_collision(self, racer, is_player=False)
        _update_racer_height(self, racer, dt)

    def _racer_progress(self, racer):
        wps = list(getattr(self, "frost_circuit_waypoints", []) or [])
        if not wps:
            return 0.0
        if bool(racer.get("finished", False)):
            return 999999.0 - float(racer.get("finish_time") or 9999.0)
        idx = int(racer.get("current_wp", 0)) % len(wps)
        dist = _dist2d(Vec3(racer.get("pos", Vec3())), wps[idx])
        segment = (math.pi * 2.0 * ICE_TRACK_RADIUS) / max(1, len(wps))
        return int(racer.get("lap", 0)) * len(wps) + idx - min(0.99, dist / max(1.0, segment))

    def _race_rankings(self):
        racers = list(getattr(self, "frost_circuit_racers", []) or [])
        return sorted(racers, key=lambda r: _racer_progress(self, r), reverse=True)

    def _complete_player_race(self, player):
        if bool(getattr(self, "frost_circuit_finished", False)):
            return
        self.frost_circuit_finished = True
        rankings = _race_rankings(self)
        results = []
        for i, racer in enumerate(rankings, start=1):
            ft = racer.get("finish_time")
            results.append({
                "rank": i,
                "name": str(racer.get("name") or "Racer"),
                "time": None if ft is None else round(float(ft), 3),
                "lap": int(racer.get("lap", 0)),
                "waypoint": int(racer.get("current_wp", 0)),
            })
        finish_time = float(player.get("finish_time") or (time.time() - float(getattr(self, "frost_circuit_started_at", time.time()))))
        player_rank = next((r["rank"] for r in results if r.get("name") == "Player"), len(results) or 1)
        rank_bonus = max(125, ICE_FINISH_SCORE - max(0, int(player_rank) - 1) * 105)
        speed_finish_bonus = max(0, int(220 - finish_time * 2.0))
        _add_frost_score(self, rank_bonus + speed_finish_bonus, reason="finish")
        old_best = getattr(self, "frost_circuit_best_time", None)
        if old_best is None or finish_time < float(old_best):
            self.frost_circuit_best_time = round(finish_time, 3)
        if results and results[0].get("name") == "Player":
            self.frost_circuit_wins = int(getattr(self, "frost_circuit_wins", 0) or 0) + 1
        self.frost_circuit_races_completed = int(getattr(self, "frost_circuit_races_completed", 0) or 0) + 1
        self.frost_circuit_last_results = results[:12]
        save_frost_circuit_state(self, reason="race_finished")
        try:
            rank = next((r["rank"] for r in results if r.get("name") == "Player"), "?")
            self.center_hint["text"] = f"FROST CIRCUIT // FINISHED #{rank} // {finish_time:0.1f}s // ESC/TAB TO EXIT"
        except Exception:
            pass

    def _update_camera(self, player, dt=0.016):
        pos = Vec3(player.get("pos", Vec3()))
        yaw = float(player.get("yaw", 0.0))
        forward = _heading_vec(yaw)
        speed = abs(float(player.get("speed", 0.0) or 0.0))
        mode = str(getattr(self, "frost_circuit_camera_mode", "far_chase") or "far_chase")
        base_distance = float(getattr(self, "frost_circuit_camera_distance", 86.0) or 86.0)
        base_height = float(getattr(self, "frost_circuit_camera_height", 33.0) or 33.0)
        lookahead = float(getattr(self, "frost_circuit_camera_lookahead", 58.0) or 58.0)
        if mode == "overhead":
            distance = max(22.0, base_distance * 0.50)
            height = max(48.0, base_height * 2.75)
            lookahead = max(8.0, lookahead * 0.45)
        elif mode == "cinematic":
            distance = max(64.0, base_distance * 1.18 + speed * 0.065)
            height = max(32.0, base_height * 1.14 + speed * 0.035)
            lookahead = max(58.0, lookahead * 1.18)
        else:
            distance = max(52.0, base_distance + speed * 0.052)
            height = max(22.0, base_height + speed * 0.026)
        target_camera_pos = pos - forward * distance + Vec3(0, 0, height)
        target_look = pos + forward * lookahead + Vec3(0, 0, 4.2)
        smooth = max(0.08, min(1.0, float(dt or 0.016) * 5.8))
        old_pos = getattr(self, "frost_circuit_camera_smooth_pos", None)
        old_target = getattr(self, "frost_circuit_camera_smooth_target", None)
        if old_pos is None:
            camera_pos = Vec3(target_camera_pos)
        else:
            camera_pos = Vec3(old_pos) + (target_camera_pos - Vec3(old_pos)) * smooth
        if old_target is None:
            look_target = Vec3(target_look)
        else:
            look_target = Vec3(old_target) + (target_look - Vec3(old_target)) * min(1.0, smooth * 1.35)
        self.frost_circuit_camera_smooth_pos = Vec3(camera_pos)
        self.frost_circuit_camera_smooth_target = Vec3(look_target)
        # Keep the player position in the world shell near the camera so region
        # systems, teleport safety, and UI tracking remain coherent
        # while the actual race state is owned by the hovercraft record.
        self.player_pos = Vec3(camera_pos)
        try:
            self.camera.setPos(camera_pos)
            self.camera.lookAt(look_target)
        except Exception:
            try:
                self.camera.setPos(camera_pos)
                self.camera.setHpr(yaw, -12.0, 0.0)
            except Exception:
                pass
        try:
            self.player_yaw = yaw
            self.player_pitch = -14.0 if mode != "overhead" else -54.0
        except Exception:
            pass

    def adjust_frost_circuit_camera(self, distance_delta=0.0, height_delta=0.0, lookahead_delta=0.0):
        if not bool(getattr(self, "frost_circuit_active", False)):
            return False
        def clamp(v, lo, hi):
            return max(float(lo), min(float(hi), float(v)))
        self.frost_circuit_camera_distance = clamp(float(getattr(self, "frost_circuit_camera_distance", 86.0) or 86.0) + float(distance_delta or 0.0), 48.0, 150.0)
        self.frost_circuit_camera_height = clamp(float(getattr(self, "frost_circuit_camera_height", 33.0) or 33.0) + float(height_delta or 0.0), 18.0, 96.0)
        self.frost_circuit_camera_lookahead = clamp(float(getattr(self, "frost_circuit_camera_lookahead", 58.0) or 58.0) + float(lookahead_delta or 0.0), 18.0, 125.0)
        try:
            self.center_hint["text"] = f"FROST CAMERA // DIST {self.frost_circuit_camera_distance:.0f} HEIGHT {self.frost_circuit_camera_height:.0f}"
        except Exception:
            pass
        return True

    def cycle_frost_circuit_camera(self):
        if not bool(getattr(self, "frost_circuit_active", False)):
            return False
        modes = ["far_chase", "cinematic", "overhead"]
        current = str(getattr(self, "frost_circuit_camera_mode", "far_chase") or "far_chase")
        try:
            idx = modes.index(current)
        except ValueError:
            idx = 0
        self.frost_circuit_camera_mode = modes[(idx + 1) % len(modes)]
        self.frost_circuit_camera_smooth_pos = None
        self.frost_circuit_camera_smooth_target = None
        try:
            self.center_hint["text"] = f"FROST CAMERA // {self.frost_circuit_camera_mode.upper().replace('_', ' ')}"
        except Exception:
            pass
        return True

    def create_frost_circuit_ui(self):
        if getattr(self, "frost_circuit_ui_root", None) is not None:
            return
        self.frost_circuit_ui_root = self.aspect2d.attachNewNode("frost-circuit-ui")
        self.frost_circuit_ui_panel = DirectFrame(
            parent=self.frost_circuit_ui_root,
            frameColor=(0.010, 0.018, 0.035, 0.42),
            frameSize=(-1.13, 1.13, -0.145, 0.145),
            pos=(0.0, 0, -0.812),
        )
        self.frost_circuit_ui_title = DirectLabel(
            parent=self.frost_circuit_ui_panel, text="FROST CIRCUIT", text_align=TextNode.ALeft,
            text_fg=(0.66, 0.94, 1.0, 1), text_shadow=(0, 0, 0, 0.82), frameColor=(0, 0, 0, 0),
            scale=0.034, pos=(-1.06, 0, 0.088),
        )
        self.frost_circuit_ui_status = DirectLabel(
            parent=self.frost_circuit_ui_panel, text="", text_align=TextNode.ALeft,
            text_fg=(1.0, 1.0, 1.0, 0.96), text_shadow=(0, 0, 0, 0.82), frameColor=(0, 0, 0, 0),
            scale=0.022, pos=(-1.06, 0, 0.020),
        )
        self.frost_circuit_ui_help = DirectLabel(
            parent=self.frost_circuit_ui_panel, text="", text_align=TextNode.ALeft,
            text_fg=(0.82, 0.92, 1.0, 0.92), text_shadow=(0, 0, 0, 0.78), frameColor=(0, 0, 0, 0),
            scale=0.018, pos=(-1.06, 0, -0.066),
        )

    def update_frost_circuit_ui(self):
        if not bool(getattr(self, "frost_circuit_active", False)):
            return
        create_frost_circuit_ui(self)
        racers = list(getattr(self, "frost_circuit_racers", []) or [])
        player = racers[0] if racers else None
        rankings = _race_rankings(self)
        rank = "?"
        for i, r in enumerate(rankings, start=1):
            if r is player:
                rank = str(i)
                break
        elapsed = max(0.0, time.time() - float(getattr(self, "frost_circuit_started_at", time.time()) or time.time()))
        if player:
            wp = int(player.get("current_wp", 0))
            lap = min(ICE_REQUIRED_LAPS, int(player.get("lap", 0)) + 1)
            spd = abs(float(player.get("speed", 0.0)))
            best = getattr(self, "frost_circuit_best_time", None)
            best_txt = "--" if best is None else f"{float(best):0.1f}s"
            score = int(getattr(self, "frost_circuit_score", 0) or 0)
            total = int(getattr(self, "frost_circuit_total_score", 0) or 0)
            loops = int(sum(1 for g in list(getattr(self, "frost_circuit_loop_gates", []) or []) if bool(g.get("scored", False))))
            crystals = int(sum(1 for c in list(getattr(self, "frost_circuit_score_crystals", []) or []) if not bool(c.get("active", True))))
            crystal_total = len(getattr(self, "frost_circuit_score_crystals", []) or [])
            streak = int(getattr(self, "frost_circuit_clean_waypoint_streak", 0) or 0)
            status = f"R {rank}/{len(racers)}  L {lap}/{ICE_REQUIRED_LAPS}  WP {wp:02d}/{ICE_TRACK_WAYPOINTS}  SPD {spd:03.0f}  RUN {score}  SAVED {total}  CHG {crystals}/{crystal_total}  STRK x{streak}  BEST {best_txt}"
        else:
            status = "Race ready"
        leaders = ", ".join(str(r.get("name")) for r in rankings[:3]) if rankings else "--"
        help_text = "Arcade sled handling.  W/S or arrows drive  A/D steer  Shift boost  Space drift  R reset  V camera  Esc exit  Top: " + leaders
        try:
            self.frost_circuit_ui_status["text"] = status
            self.frost_circuit_ui_help["text"] = help_text
        except Exception:
            pass

    def reset_player_to_last_waypoint(self):
        if not bool(getattr(self, "frost_circuit_active", False)):
            return
        racers = list(getattr(self, "frost_circuit_racers", []) or [])
        wps = list(getattr(self, "frost_circuit_waypoints", []) or [])
        if not racers or not wps:
            return
        player = racers[0]
        idx = max(0, (int(player.get("current_wp", 1)) - 1) % len(wps))
        pos = Vec3(wps[idx])
        target = wps[int(player.get("current_wp", 0)) % len(wps)]
        player["pos"] = Vec3(pos.x, pos.y, _floor_z(self, pos.x, pos.y) + ICE_HOVER_BASE_CLEARANCE)
        player["yaw"] = _yaw_to_target(player["pos"], target)
        player["speed"] = 0.0
        self.center_hint["text"] = "FROST CIRCUIT // RESET TO LAST WAYPOINT"

    def activate_frost_circuit_from_mode(self, mode=None, source="core", route=""):
        if not _ice_allowed(self):
            self.center_hint["text"] = "FROST CIRCUIT // ENTER ICE REGION TO RACE"
            return False
        try:
            if getattr(self, "holoforge_active", False): self.deactivate_holoforge(reason="switch_to_frost_circuit")
            if getattr(self, "forest_growth_active", False): self.deactivate_forest_growth(reason="switch_to_frost_circuit")
            if getattr(self, "hills_life_active", False): self.deactivate_hills_life(reason="switch_to_frost_circuit")
            if getattr(self, "oddities_active", False): self.deactivate_oddities(reason="switch_to_frost_circuit")
            if getattr(self, "desert_ships_active", False): self.deactivate_desert_ships(reason="switch_to_frost_circuit")
            if getattr(self, "shell_flight_craft_active", False): self.toggle_shell_flight_craft()
        except Exception:
            pass
        _ensure_dirs()
        load_frost_circuit_state(self)
        self.frost_circuit_active = True
        self.frost_circuit_finished = False
        self.frost_circuit_exit_prompt_until = 0.0
        self.frost_circuit_score = 0
        self.frost_circuit_points_this_run = 0
        self.frost_circuit_crystals_collected = 0
        self.frost_circuit_clean_waypoint_streak = 0
        self.frost_circuit_last_player_rank = None
        self.frost_circuit_drift_score_bank = 0.0
        self.frost_circuit_boost_score_bank = 0.0
        self.frost_circuit_last_score_tick = time.time()
        self.frost_circuit_player_saved_pos = Vec3(getattr(self, "player_pos", Vec3(0, 0, 0)))
        try:
            self.frost_circuit_player_saved_hpr = self.camera.getHpr()
        except Exception:
            self.frost_circuit_player_saved_hpr = None
        _ensure_root(self)
        _generate_waypoints(self)
        _build_track_visuals(self)
        _setup_racers(self)
        try:
            if self.frost_circuit_racers:
                _update_camera(self, self.frost_circuit_racers[0], 0.20)
        except Exception:
            pass
        self.frost_circuit_started_at = time.time()
        create_frost_circuit_ui(self)
        update_frost_circuit_ui(self)
        self.center_hint["text"] = "FROST CIRCUIT // ARCADE HOVERCRAFT RACE // BIGGER SLEDS, BOOSTS, ICE CHARGES"
        label = str((mode or {}).get("name") or "Frost Circuit")
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
            self._append_mode_gateway_history("frost_circuit_runtime_open", mode=mode, label=label, route=IN_WORLD_ROUTE, extra={"source": source, "state": str(STATE_PATH), "racers": len(self.frost_circuit_racers)})
        except Exception:
            pass
        return True

    def deactivate_frost_circuit(self, reason="closed"):
        if not bool(getattr(self, "frost_circuit_active", False)):
            return
        # Drop the player at the current hovercraft location so quitting the race
        # does not snap them back to the old camera or leave them floating high.
        try:
            racers = list(getattr(self, "frost_circuit_racers", []) or [])
            if racers:
                craft_pos = Vec3(racers[0].get("pos", self.frost_circuit_player_saved_pos or Vec3(0, 0, 0)))
                self.player_pos = Vec3(craft_pos.x, craft_pos.y, _eye_z(self, craft_pos.x, craft_pos.y))
                self.camera.setPos(self.player_pos)
                self.camera.setHpr(float(racers[0].get("yaw", 0.0)), -8.0, 0.0)
            elif self.frost_circuit_player_saved_pos is not None:
                self.player_pos = Vec3(self.frost_circuit_player_saved_pos)
                self.camera.setPos(self.player_pos)
        except Exception:
            pass
        save_frost_circuit_state(self, reason=reason)
        self.frost_circuit_active = False
        _destroy_visuals(self)
        self.frost_circuit_racers = []
        self.frost_circuit_waypoints = []
        self.center_hint["text"] = f"FROST CIRCUIT // SAVED + CLOSED ({str(reason).upper()})"
        try:
            self._append_mode_gateway_history("frost_circuit_runtime_close", label="Frost Circuit", route=IN_WORLD_ROUTE, extra={"reason": reason, "state": str(STATE_PATH)})
        except Exception:
            pass

    def update_frost_circuit(self, dt=0.0):
        if not bool(getattr(self, "frost_circuit_active", False)):
            return
        dt = max(0.001, min(0.05, float(dt or 0.016)))
        racers = list(getattr(self, "frost_circuit_racers", []) or [])
        if not racers:
            deactivate_frost_circuit(self, reason="empty_race")
            return
        player = racers[0]
        # Unload if player physically exits the ice ring. Teleport and TAB also
        # unload through wrappers below.
        p = Vec3(player.get("pos", Vec3()))
        radius = math.sqrt(float(p.x) * float(p.x) + float(p.y) * float(p.y))
        if radius < ICE_R0 - ICE_LEAVE_MARGIN or radius > ICE_R1 + ICE_LEAVE_MARGIN:
            deactivate_frost_circuit(self, reason="left_ice_region")
            return
        _update_player_racer(self, player, dt)
        now = time.time()
        last_tick = float(getattr(self, "frost_circuit_last_score_tick", 0.0) or 0.0)
        if now - last_tick >= 1.0 and not bool(getattr(self, "frost_circuit_finished", False)):
            spd_bonus = ICE_SPEED_SCORE_PER_SECOND + int(min(18.0, abs(float(player.get("speed", 0.0))) / 18.0))
            _add_frost_score(self, spd_bonus, reason="speed_tick")
            self.frost_circuit_last_score_tick = now
            if now - float(getattr(self, "frost_circuit_last_save_at", 0.0) or 0.0) > 12.0:
                save_frost_circuit_state(self, reason="active_score_tick")
        for racer in racers[1:]:
            _update_bot_racer(self, racer, dt)
        for racer in racers:
            _advance_racer_waypoint(self, racer, now)
            _update_hovercraft_node(self, racer)
        rankings_now = _race_rankings(self)
        try:
            player_rank = rankings_now.index(player) + 1
        except Exception:
            player_rank = len(rankings_now) or 1
        last_rank = getattr(self, "frost_circuit_last_player_rank", None)
        if last_rank is None:
            self.frost_circuit_last_player_rank = player_rank
        elif player_rank < int(last_rank) and not bool(getattr(self, "frost_circuit_finished", False)):
            passes = max(1, int(last_rank) - int(player_rank))
            gained = _add_frost_score(self, ICE_OVERTAKE_SCORE * passes, reason="overtake")
            self.frost_circuit_rank_bonus_count = int(getattr(self, "frost_circuit_rank_bonus_count", 0) or 0) + passes
            self.frost_circuit_last_player_rank = player_rank
            try:
                self.center_hint["text"] = f"FROST CIRCUIT // OVERTAKE +{gained}"
            except Exception:
                pass
        elif player_rank > int(last_rank):
            self.frost_circuit_last_player_rank = player_rank
        _update_camera(self, player, dt)
        if bool(player.get("finished", False)):
            _complete_player_race(self, player)
        update_frost_circuit_ui(self)

    # Public runtime API.
    CommandHubApp.is_frost_circuit_mode = _is_frost_circuit_mode
    CommandHubApp.activate_frost_circuit_from_mode = activate_frost_circuit_from_mode
    CommandHubApp.deactivate_frost_circuit = deactivate_frost_circuit
    CommandHubApp.load_frost_circuit_state = load_frost_circuit_state
    CommandHubApp.save_frost_circuit_state = save_frost_circuit_state
    CommandHubApp.update_frost_circuit = update_frost_circuit
    CommandHubApp.reset_player_to_last_waypoint = reset_player_to_last_waypoint
    CommandHubApp.adjust_frost_circuit_camera = adjust_frost_circuit_camera
    CommandHubApp.cycle_frost_circuit_camera = cycle_frost_circuit_camera

    old_init = CommandHubApp.__init__
    def __init__(self, *args, **kwargs):
        old_init(self, *args, **kwargs)
        _init_state(self)
    CommandHubApp.__init__ = __init__

    old_setup_input = CommandHubApp.setup_input
    def setup_input(self, *args, **kwargs):
        # Keep prior runtime key bindings intact. R already routes through
        # holoforge_rotate_tool in the shared builder controls; we intercept that
        # method below only while Frost Circuit is active.
        result = old_setup_input(self, *args, **kwargs)
        self.accept("wheel_up", self.adjust_frost_circuit_camera, [-6.0, 0.0, -2.0])
        self.accept("wheel_down", self.adjust_frost_circuit_camera, [6.0, 0.0, 2.0])
        self.accept("[", self.adjust_frost_circuit_camera, [-6.0, 0.0, -2.0])
        self.accept("]", self.adjust_frost_circuit_camera, [6.0, 0.0, 2.0])
        self.accept("page_up", self.adjust_frost_circuit_camera, [0.0, 5.0, 0.0])
        self.accept("page_down", self.adjust_frost_circuit_camera, [0.0, -5.0, 0.0])
        self.accept("v", self.cycle_frost_circuit_camera)
        return result
    CommandHubApp.setup_input = setup_input


    old_r_rotate = getattr(CommandHubApp, "holoforge_rotate_tool", None)
    if callable(old_r_rotate):
        def holoforge_rotate_tool(self, amount=15.0):
            if bool(getattr(self, "frost_circuit_active", False)):
                return self.reset_player_to_last_waypoint()
            return old_r_rotate(self, amount)
        CommandHubApp.holoforge_rotate_tool = holoforge_rotate_tool

    old_start_escape_hold = CommandHubApp.start_escape_hold
    def start_escape_hold(self):
        if bool(getattr(self, "frost_circuit_active", False)):
            now = time.monotonic()
            until = float(getattr(self, "frost_circuit_exit_prompt_until", 0.0) or 0.0)
            if now <= until:
                self.deactivate_frost_circuit(reason="escape_confirmed")
            else:
                self.frost_circuit_exit_prompt_until = now + 2.2
                self.center_hint["text"] = "FROST CIRCUIT // PRESS ESC AGAIN TO EXIT RACE"
            return
        return old_start_escape_hold(self)
    CommandHubApp.start_escape_hold = start_escape_hold

    old_route = CommandHubApp.launch_core_mode_route
    def launch_core_mode_route(self, mode, source="core", extra_env=None, close_core=True):
        if self.is_frost_circuit_mode(mode):
            return bool(self.activate_frost_circuit_from_mode(mode, source=source, route=IN_WORLD_ROUTE))
        return old_route(self, mode, source=source, extra_env=extra_env, close_core=close_core)
    CommandHubApp.launch_core_mode_route = launch_core_mode_route

    old_update_player = CommandHubApp.update_player
    def update_player(self, dt):
        if bool(getattr(self, "frost_circuit_active", False)):
            self.update_frost_circuit(dt)
            return
        return old_update_player(self, dt)
    CommandHubApp.update_player = update_player

    old_handle_tab = CommandHubApp.handle_tab_action
    def handle_tab_action(self):
        if bool(getattr(self, "frost_circuit_active", False)):
            self.deactivate_frost_circuit(reason="tab_exit")
            return
        return old_handle_tab(self)
    CommandHubApp.handle_tab_action = handle_tab_action

    old_number = CommandHubApp.handle_number_action
    def handle_number_action(self, number):
        if bool(getattr(self, "frost_circuit_active", False)):
            self.deactivate_frost_circuit(reason="teleport_exit")
        return old_number(self, number)
    CommandHubApp.handle_number_action = handle_number_action

    old_region_ui = CommandHubApp.update_holoverse_region_ui
    def update_holoverse_region_ui(self):
        result = old_region_ui(self)
        if bool(getattr(self, "frost_circuit_active", False)):
            try:
                if hasattr(self, "region_keymap_root"):
                    self.region_keymap_root.hide()
                if hasattr(self, "region_top_panel"):
                    self.region_top_panel.hide()
            except Exception:
                pass
        return result
    CommandHubApp.update_holoverse_region_ui = update_holoverse_region_ui

    setattr(main, "FROST_CIRCUIT_RUNTIME_INSTALLED", True)
    setattr(main, "FROST_CIRCUIT_STATE_PATH_RUNTIME", STATE_PATH)
