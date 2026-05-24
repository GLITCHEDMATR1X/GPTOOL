"""HoloUtopia in-game runtime bridge.

This bridge mounts the authored 3x3 HoloUtopia city into the live HoloVerse
3D world, not into a flat preview panel.  It is intentionally additive and safe:
- no artifact route edits;
- no HoloCore changes;
- no authored database writes;
- no collision geometry;
- citizen visuals are small collisionless 3D people, not flat dots, rings, or labels;
- all Panda3D imports remain inside runtime functions;
- the integrated city can be removed with one NodePath cleanup.

Typical HoloVerse hook after ShowBase is initialized:

    from holoutopia_game_runtime import install_holoutopia_runtime
    self.holoutopia_runtime = install_holoutopia_runtime(self, ROOT)

If the authored city data is unavailable, installation returns a disabled runtime
object instead of crashing the game.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
import time
from pathlib import Path
from typing import Any


RUNTIME_CONFIG_RELATIVE = Path("../database/utopia/runtime/holoutopia_runtime_bridge.json")
DEFAULT_RUNTIME_ID = "holoutopia_integrated_world_runtime_v56_first_person_usability"


@dataclass(frozen=True)
class HoloUtopiaRuntimeSummary:
    """Small JSON-safe summary used by validators and startup diagnostics."""

    runtime_id: str
    enabled_by_default: bool
    town_count: int
    neighborhood_count: int
    citizen_count: int
    schedule_frame_citizens: int
    placement_scale: float
    city_day_seconds: float
    overlay_key: str
    danger_key: str
    integration_mode: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "runtime_id": self.runtime_id,
            "enabled_by_default": self.enabled_by_default,
            "town_count": self.town_count,
            "neighborhood_count": self.neighborhood_count,
            "citizen_count": self.citizen_count,
            "schedule_frame_citizens": self.schedule_frame_citizens,
            "placement_scale": self.placement_scale,
            "city_day_seconds": self.city_day_seconds,
            "overlay_key": self.overlay_key,
            "danger_key": self.danger_key,
            "integration_mode": self.integration_mode,
        }


class HoloUtopiaGameRuntime:
    """Live visual/runtime bridge for the authored HoloUtopia city."""

    def __init__(self, app: Any, holoverse_root: Path | str | None = None, *, enabled: bool = True) -> None:
        self.app = app
        self.holoverse_root = Path(holoverse_root or Path(__file__).resolve().parent).resolve()
        self.config = load_runtime_config(self.holoverse_root)
        self.enabled = bool(enabled and self.config.get("enabled_by_default", True))
        self.installed = False
        self.error = ""
        self.world_parent = None
        self.world_parent_name = ""
        self.city_root = None
        self.neighborhood_root = None
        self.citizens_root = None
        self.status_root = None
        self.activity_root = None
        self.central_core_overlay_root = None
        self.watch_root = None
        self.focus_root = None
        self.speech_root = None
        self.service_ops_root = None
        self.adventure_sim_root = None
        self._marker_nodes: dict[str, Any] = {}
        self._marker_phase: dict[str, float] = {}
        self._node_index: dict[str, Any] = {}
        self._inputs: dict[str, Any] | None = None
        self._task_inputs: dict[str, Any] | None = None
        self._last_citizen_frame: dict[str, Any] = {}
        self._last_visible_citizens: dict[str, Any] = {}
        self._last_visible_citizen_positions: dict[str, tuple[float, float, float]] = {}
        self._last_dialogue_state: dict[str, Any] = {}
        self._dialogue_daily_memory: dict[str, Any] = {}
        self._dialogue_day_id = ""
        self.panel_manager = None
        self.selected_citizen_id = ""
        self.selected_building_id = ""
        self._last_building_records: dict[str, Any] = {}
        self._building_record_clock = ""
        self.building_selection_root = None
        self.selection_summary_root = None
        self.town_focus_summary_root = None
        self.town_focus_detail_root = None
        self.town_focus_activity_root = None
        self.town_focus_flow_root = None
        self.town_focus_event_root = None
        self.town_focus_follow_root = None
        self.city_overview_signal_root = None
        self.city_overview_signal_panel_root = None
        self.tutorial_panel_root = None
        self._tutorial_panel_visible = bool((self.config.get("controls") if isinstance(self.config.get("controls"), dict) else {}).get("tutorial_visible_by_default", True))
        self._tutorial_panel_cache_key = ""
        self._tutorial_panel_last_text = ""
        self.selected_town_id = ""
        self._town_focus_active = False
        self._town_focus_saved_camera: dict[str, Any] = {}
        self._last_town_focus_summary: dict[str, Any] = {}
        self._town_focus_npc_memory: dict[str, dict[str, Any]] = {}
        self._last_town_focus_life_snapshot: dict[str, Any] = {}
        self._town_focus_selected_detail: dict[str, Any] = {}
        self._town_focus_event_memory: dict[str, dict[str, Any]] = {}
        self._town_focus_player_orders: dict[str, dict[str, Any]] = {}
        self._town_focus_event_outcomes: dict[str, dict[str, Any]] = {}
        self._town_focus_consequence_memory: dict[str, dict[str, Any]] = {}
        self._town_focus_health_report_memory: dict[str, dict[str, Any]] = {}
        self._city_overview_signal_memory: dict[str, dict[str, Any]] = {}
        self._city_overview_last_signal_clock = ""
        self._town_focus_life_snapshot_cache_key = ""
        self._town_focus_life_snapshot_cache: dict[str, Any] = {}
        self._town_focus_visual_cache_key = ""
        self._town_focus_last_visual_build = 0.0
        self._town_focus_panel_cache_key = ""
        self._town_focus_panel_last_text = ""
        self._town_focus_detail_cache_key = ""
        self._town_focus_detail_last_text = ""
        self._town_focus_perf_stats: dict[str, Any] = {
            "snapshot_cache_hits": 0,
            "snapshot_builds": 0,
            "visual_rebuilds": 0,
            "visual_skips": 0,
            "panel_text_updates": 0,
            "detail_text_updates": 0,
        }
        self._town_focus_last_order_feedback = ""
        self._town_focus_follow_citizen_id = ""
        self._town_focus_follow_last_update = 0.0
        self._town_focus_last_town_id = ""
        self._town_focus_state_loaded = False
        self._town_focus_state_error = ""
        self._town_focus_state_notice = ""
        self._town_focus_last_state_save = 0.0
        self._town_focus_last_state_clock = ""
        self._town_focus_last_state_bytes = 0
        self._town_focus_last_state_schema = 0
        self._first_person_active = False
        self._first_person_player_memory: dict[str, dict[str, Any]] = {}
        self._first_person_last_interaction = ""
        self._first_person_prompt_root = None
        self._first_person_hidden_overlay_nodes: list[Any] = []
        self._last_building_gameplay_state: dict[str, Any] = {}
        self._facade_pulse_nodes: list[tuple[Any, tuple[float, float, float, float], float, float, float]] = []
        self._facade_pulse_cache_ready = False
        self._facade_pulse_cursor = 0
        self._last_facade_pulse_update = 0.0
        self._inspector_focus_active = False
        self._last_update = 0.0
        self._started_at = time.monotonic()
        self._danger_state = False
        self._visible = True
        self._task_name = "holoutopia-citizen-runtime-update"
        self._summary: dict[str, Any] = {}

    def install(self) -> "HoloUtopiaGameRuntime":
        """Attach HoloUtopia city, neighborhoods, and citizen markers to render."""
        if not self.enabled:
            return self
        try:
            render = getattr(self.app, "render", None)
            if render is None:
                # Support classic Panda globals when the caller passes base-like objects.
                render = getattr(__import__("builtins"), "render", None)
            if render is None:
                raise RuntimeError("No Panda3D render root available")
            parent = self._resolve_world_parent(render)

            from holoutopia_town_blocks import (
                attach_holoutopia_city,
                attach_holoutopia_city_neighborhoods,
                city_frame_metrics,
                load_city_atlas,
                list_neighborhood_ids,
            )
            from holoutopia_citizen_simulation import build_node_index, load_simulation_inputs
            from holoutopia_citizen_tasks import load_task_inputs

            self._inputs = load_simulation_inputs(self.holoverse_root)
            self._task_inputs = load_task_inputs(self.holoverse_root)
            self._node_index = build_node_index(self._inputs)
            self._load_town_focus_state()
            atlas = load_city_atlas(self.holoverse_root)
            metrics = city_frame_metrics(atlas)
            placement = self.config.get("placement", {}) if isinstance(self.config.get("placement"), dict) else {}
            scale = _safe_float(placement.get("scale"), 0.55)
            z_offset = _safe_float(placement.get("z_offset"), 0.25)
            anchor_grid = placement.get("anchor_city_grid", [1, 1])
            try:
                anchor_x = float(anchor_grid[0]) * float(metrics["frame_w"])
                anchor_y = float(anchor_grid[1]) * float(metrics["frame_h"])
            except Exception:
                anchor_x = float(metrics["frame_w"])
                anchor_y = float(metrics["frame_h"])
            root = parent.attachNewNode("holoutopia_integrated_city_world")
            root.setPythonTag("holoutopia_world_integrated", True)
            root.setPythonTag("holoutopia_parent", self.world_parent_name or "render")
            root.setScale(scale)
            if bool(placement.get("center_anchor_at_world_origin", True)):
                root.setPos(-anchor_x * scale, -anchor_y * scale, z_offset)
            else:
                root.setPos(0, 0, z_offset)
            root.setLightOff(True)
            self.city_root = root

            layers = self.config.get("render_layers", {}) if isinstance(self.config.get("render_layers"), dict) else {}
            if bool(layers.get("city_world_atlas_style", True)):
                try:
                    from holoutopia_city_world_style import attach_holoutopia_city_world_style
                    attach_holoutopia_city_world_style(root, holoverse_root=self.holoverse_root, z=-0.055)
                except Exception as exc:
                    self.error = f"city-world-style:{exc.__class__.__name__}:{exc}"
            if bool(layers.get("city_3d_massing", True)):
                attach_holoutopia_city(root, holoverse_root=self.holoverse_root, z=0.06)
            if bool(layers.get("neighborhood_overlays", True)):
                self.neighborhood_root = attach_holoutopia_city_neighborhoods(
                    root,
                    holoverse_root=self.holoverse_root,
                    z=0.12,
                    neighborhood_ids=list_neighborhood_ids(self.holoverse_root),
                )
            if bool(layers.get("activity_cluster_props", True)):
                try:
                    from holoutopia_simulation_hub_visuals import attach_simulation_hub_activity_visuals
                    self.activity_root = attach_simulation_hub_activity_visuals(root, self.holoverse_root, self._node_index)
                except Exception as exc:
                    self.error = f"activity-props:{exc.__class__.__name__}:{exc}"
            # Pass 44: draw the raised Central Simulation/Core hub after local
            # district massing and activity props so it stays the dominant
            # world-view anchor instead of appearing as a thin line underneath
            # small central props. Citizens are created afterward and remain
            # visible on top of the hub surface.
            if bool(layers.get("central_core_overlay", True)):
                try:
                    from holoutopia_city_world_style import attach_holoutopia_central_core_overlay
                    self.central_core_overlay_root = attach_holoutopia_central_core_overlay(root, holoverse_root=self.holoverse_root, z=0.72)
                except Exception as exc:
                    self.error = f"central-core-overlay:{exc.__class__.__name__}:{exc}"
            if bool(layers.get("citizen_markers", True)):
                self.citizens_root = root.attachNewNode("holoutopia_live_citizen_people")
                self.citizens_root.setLightOff(True)
                self._create_or_update_citizen_markers(force=True)
            if bool(layers.get("status_label", True)):
                self._create_status_label(root)
            if bool(layers.get("watch_mode_panel", True)):
                self._create_or_update_watch_panel()
            if bool(layers.get("inspector_panels", True)):
                self._install_panel_manager()

            controls = self.config.get("controls", {}) if isinstance(self.config.get("controls"), dict) else {}
            toggle_key = str(controls.get("toggle_overlay_key") or "u")
            danger_key = str(controls.get("danger_state_key") or "shift-u")
            inspect_key = str(controls.get("inspect_citizen_key") or "mouse1")
            close_panel_key = str(controls.get("close_panel_key") or "shift-x")
            if hasattr(self.app, "accept"):
                try:
                    self.app.accept(toggle_key, self.toggle_visible)
                    self.app.accept(danger_key, self.toggle_danger_state)
                    self.app.accept(inspect_key, self._try_select_world_from_camera)
                    self.app.accept(close_panel_key, self.close_focused_panel)
                    self.app.accept("backspace", self.exit_town_focus)
                    self.app.accept("0", self.exit_town_focus)
                    self.app.accept("1", self._apply_town_focus_order_dispatch_help)
                    self.app.accept("2", self._apply_town_focus_order_boost_repair)
                    self.app.accept("3", self._apply_town_focus_order_calm_civilians)
                    self.app.accept("4", self._apply_town_focus_order_fund_supplies)
                    self.app.accept(str(controls.get("town_focus_reset_state_key") or "shift-r"), self.reset_town_focus_runtime_state)
                    self.app.accept(str(controls.get("tutorial_toggle_key") or "f1"), self.toggle_tutorial_panel)
                    self.app.accept(str(controls.get("tutorial_alt_toggle_key") or "shift-h"), self.toggle_tutorial_panel)
                    self.app.accept(str(controls.get("first_person_toggle_key") or "enter"), self.toggle_first_person_walk_mode)
                    self.app.accept(str(controls.get("first_person_alt_toggle_key") or "p"), self.toggle_first_person_walk_mode)
                    self.app.accept(str(controls.get("first_person_interact_key") or "e"), self.interact_first_person)
                except Exception:
                    pass
            task_mgr = getattr(self.app, "taskMgr", None) or getattr(self.app, "task_mgr", None)
            if task_mgr is None:
                task_mgr = getattr(__import__("builtins"), "taskMgr", None)
            if task_mgr is not None and hasattr(task_mgr, "add"):
                try:
                    task_mgr.add(self._update_task, self._task_name)
                except Exception:
                    pass

            self.installed = True
            self._summary = build_runtime_summary(self.holoverse_root).as_dict()
            self._focus_camera_on_city_overview()
            return self
        except Exception as exc:
            self.error = f"{exc.__class__.__name__}: {exc}"
            self.destroy()
            return self

    def destroy(self) -> None:
        """Remove visual nodes and leave authored data untouched."""
        self._save_town_focus_state(force=True, reason="destroy")
        try:
            if self.panel_manager is not None:
                self.panel_manager.destroy()
        except Exception:
            pass
        self.panel_manager = None
        for attr in ("first_person_prompt_root", "tutorial_panel_root", "city_overview_signal_panel_root", "city_overview_signal_root", "town_focus_follow_root", "town_focus_event_root", "town_focus_flow_root", "town_focus_activity_root", "town_focus_detail_root", "town_focus_summary_root", "selection_summary_root", "building_selection_root", "adventure_sim_root", "service_ops_root", "speech_root", "focus_root", "watch_root", "status_root", "central_core_overlay_root", "activity_root", "citizens_root", "neighborhood_root", "city_root"):
            node = getattr(self, attr, None)
            try:
                if node is not None:
                    node.removeNode()
            except Exception:
                pass
            setattr(self, attr, None)
        self.world_parent = None
        self.world_parent_name = ""
        self._marker_nodes.clear()
        self._marker_phase.clear()
        self._facade_pulse_nodes.clear()
        self._facade_pulse_cache_ready = False
        self._facade_pulse_cursor = 0
        self._last_facade_pulse_update = 0.0
        self.installed = False

    def _resolve_world_parent(self, render: Any) -> Any:
        """Prefer the real HoloVerse 3D world parent over a preview/render root."""
        placement = self.config.get("placement", {}) if isinstance(self.config.get("placement"), dict) else {}
        preferred = placement.get("parent_preference")
        if not isinstance(preferred, list) or not preferred:
            preferred = ["root_3d", "world_root", "render"]
        for raw_name in preferred:
            name = str(raw_name or "").strip()
            if not name:
                continue
            node = render if name == "render" else getattr(self.app, name, None)
            if node is None:
                continue
            try:
                if hasattr(node, "isEmpty") and node.isEmpty():
                    continue
            except Exception:
                pass
            self.world_parent = node
            self.world_parent_name = name
            return node
        self.world_parent = render
        self.world_parent_name = "render"
        return render

    def toggle_visible(self) -> None:
        self._visible = not self._visible
        self._sync_world_visibility()

    def _runtime_blocked_by_scene_state(self) -> bool:
        """Hide the city while another scene owns the same Panda3D window."""
        return bool(
            getattr(self.app, "active_native_mode", None) is not None
            or getattr(self.app, "external_suspended", False)
            or getattr(self.app, "holospace_active", False)
            or getattr(self.app, "holocore_active", False)
        )

    def _sync_world_visibility(self) -> None:
        node = self.city_root
        if node is None:
            return
        should_show = bool(self._visible and not self._runtime_blocked_by_scene_state())
        try:
            if should_show:
                node.show()
            else:
                node.hide()
        except Exception:
            pass

    def toggle_danger_state(self) -> None:
        self._danger_state = not self._danger_state
        self._create_or_update_citizen_markers(force=True)

    def current_clock(self) -> str:
        override = getattr(self, "_screenshot_clock_override", None)
        if override:
            return str(override)
        runtime = self.config.get("citizen_runtime", {}) if isinstance(self.config.get("citizen_runtime"), dict) else {}
        day_seconds = max(30.0, _safe_float(runtime.get("city_day_seconds"), 1440.0))
        elapsed = (time.monotonic() - self._started_at) % day_seconds
        minutes = int((elapsed / day_seconds) * 24 * 60)
        return f"{minutes // 60:02d}:{minutes % 60:02d}"

    def current_day_id(self) -> str:
        runtime = self.config.get("citizen_runtime", {}) if isinstance(self.config.get("citizen_runtime"), dict) else {}
        day_seconds = max(30.0, _safe_float(runtime.get("city_day_seconds"), 1440.0))
        day_index = int(max(0.0, time.monotonic() - self._started_at) // day_seconds)
        return f"day_{day_index:04d}"

    def _town_focus_persistence_config(self) -> dict[str, Any]:
        focus = self.config.get("town_focus") if isinstance(self.config.get("town_focus"), dict) else {}
        persistence = focus.get("persistence") if isinstance(focus.get("persistence"), dict) else {}
        return persistence

    def _town_focus_persistence_limit(self, key: str, default: int, *, low: int = 1, high: int = 5000) -> int:
        persistence = self._town_focus_persistence_config()
        try:
            value = int(float(persistence.get(key, default)))
        except Exception:
            value = int(default)
        return max(int(low), min(int(high), value))

    def _town_focus_state_schema_version(self) -> int:
        return self._town_focus_persistence_limit("schema_version", 2, low=1, high=20)

    def _town_focus_state_max_bytes(self) -> int:
        # Keep runtime_state small enough to survive repeated Steam/demo sessions.
        return self._town_focus_persistence_limit("max_state_bytes", 384000, low=64000, high=2000000)

    def _town_focus_state_path(self) -> Path | None:
        persistence = self._town_focus_persistence_config()
        if not bool(persistence.get("enabled", True)):
            return None
        raw = str(persistence.get("state_file") or "database/utopia/runtime_state/town_focus_session_state.json").strip()
        if not raw:
            return None
        candidate = Path(raw)
        if candidate.is_absolute():
            return candidate
        root = self.holoverse_root.resolve()
        # Match the database resolver used by the town/citizen systems.  A
        # runtime_state-only folder must not trick standalone runs into treating
        # data/HoloUtopia as the authored database root.
        if (root / "database" / "utopia" / "city_grid_atlas.json").exists():
            data_root = root
        elif (root / "data" / "database" / "utopia" / "city_grid_atlas.json").exists():
            data_root = root / "data"
        elif (root.parent / "database" / "utopia" / "city_grid_atlas.json").exists():
            data_root = root.parent
        elif root.name.lower() in {"holoverse", "holoutopia"}:
            data_root = root.parent
        else:
            data_root = root
        return data_root / candidate

    def _town_focus_state_timestamp(self) -> str:
        try:
            return time.strftime("%Y%m%d_%H%M%S", time.localtime())
        except Exception:
            return str(int(time.time()))

    def _town_focus_state_backup_path(self, path: Path, label: str) -> Path:
        safe_label = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in str(label or "backup"))[:24]
        return path.with_name(f"{path.stem}.{safe_label}.{self._town_focus_state_timestamp()}{path.suffix}")

    def _prune_town_focus_state_backups(self, path: Path, *, label: str = "backup") -> None:
        persistence = self._town_focus_persistence_config()
        max_backups = self._town_focus_persistence_limit("max_backup_files", 3, low=0, high=12)
        if max_backups <= 0:
            return
        try:
            matches = sorted(
                path.parent.glob(f"{path.stem}.{label}.*{path.suffix}"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            for old in matches[max_backups:]:
                try:
                    old.unlink()
                except Exception:
                    pass
        except Exception:
            pass

    def _backup_town_focus_state_file(self, path: Path, *, label: str) -> Path | None:
        try:
            if not path.exists() or not path.is_file():
                return None
            backup = self._town_focus_state_backup_path(path, label)
            backup.write_bytes(path.read_bytes())
            self._prune_town_focus_state_backups(path, label=label)
            return backup
        except Exception:
            return None

    def _quarantine_town_focus_state_file(self, path: Path, *, label: str) -> Path | None:
        try:
            if not path.exists() or not path.is_file():
                return None
            backup = self._town_focus_state_backup_path(path, label)
            path.replace(backup)
            self._prune_town_focus_state_backups(path, label=label)
            return backup
        except Exception:
            return None

    def _load_town_focus_state(self) -> None:
        """Load small runtime Town Focus memory without touching authored schedules."""
        if self._town_focus_state_loaded:
            return
        self._town_focus_state_loaded = True
        path = self._town_focus_state_path()
        if path is None or not path.exists():
            return
        max_bytes = self._town_focus_state_max_bytes()
        try:
            size = int(path.stat().st_size)
            if size > max_bytes:
                quarantined = self._quarantine_town_focus_state_file(path, label="oversize")
                self._town_focus_state_error = "load:oversize"
                self._town_focus_state_notice = f"oversize runtime_state moved to {quarantined.name if quarantined else 'backup'}"
                return
            raw_text = path.read_text(encoding="utf-8")
        except Exception as exc:
            self._town_focus_state_error = f"loadread:{exc.__class__.__name__}"
            return
        try:
            data = json.loads(raw_text)
        except Exception as exc:
            quarantined = self._quarantine_town_focus_state_file(path, label="corrupt")
            self._town_focus_state_error = f"loadjson:{exc.__class__.__name__}"
            self._town_focus_state_notice = f"corrupt runtime_state moved to {quarantined.name if quarantined else 'backup'}"
            return
        try:
            if not isinstance(data, dict):
                self._town_focus_state_error = "load:notdict"
                return
            schema = int(data.get("schema_version") or data.get("schema") or 1)
            max_schema = self._town_focus_state_schema_version()
            if schema > max_schema:
                self._town_focus_state_error = f"load:newer_schema_{schema}"
                self._town_focus_state_notice = "newer runtime_state ignored safely"
                return
            self._town_focus_last_state_schema = schema
            self._town_focus_last_state_bytes = int(len(raw_text.encode("utf-8")))
            self._town_focus_npc_memory = self._clean_state_dict(data.get("npc_memory"), max_items=self._town_focus_persistence_limit("max_npc_memory", 180, low=0, high=1000), depth=4)
            self._town_focus_event_memory = self._clean_state_dict(data.get("event_memory"), max_items=self._town_focus_persistence_limit("max_event_memory", 120, low=0, high=1000), depth=4)
            self._town_focus_player_orders = self._clean_state_dict(data.get("player_orders"), max_items=self._town_focus_persistence_limit("max_player_orders", 90, low=0, high=1000), depth=4)
            self._town_focus_event_outcomes = self._clean_state_dict(data.get("event_outcomes"), max_items=self._town_focus_persistence_limit("max_event_outcomes", 120, low=0, high=1000), depth=4)
            self._town_focus_consequence_memory = self._clean_state_dict(data.get("town_consequences"), max_items=self._town_focus_persistence_limit("max_town_consequences", 32, low=0, high=128), depth=5)
            self._town_focus_health_report_memory = self._clean_state_dict(data.get("town_health_reports"), max_items=self._town_focus_persistence_limit("max_town_health_reports", 96, low=0, high=500), depth=5)
            self._city_overview_signal_memory = self._clean_state_dict(data.get("city_overview_signals"), max_items=self._town_focus_persistence_limit("max_city_overview_signals", 48, low=0, high=256), depth=5)
            self._first_person_player_memory = self._clean_state_dict(data.get("first_person_player_memory"), max_items=self._town_focus_persistence_limit("max_first_person_player_memory", 16, low=0, high=64), depth=4)
            self._city_overview_last_signal_clock = str(data.get("city_overview_last_signal_clock") or "")[:32]
            self._town_focus_last_order_feedback = str(data.get("last_order_feedback") or "")[:160]
            self._town_focus_last_town_id = str(data.get("last_town_id") or data.get("selected_town_id") or "")[:96]
            self._town_focus_state_error = ""
            self._town_focus_state_notice = f"restored schema {schema}"
        except Exception as exc:
            self._town_focus_state_error = f"loadapply:{exc.__class__.__name__}"

    def _clean_state_dict(self, value: Any, *, max_items: int, depth: int = 2) -> dict[str, dict[str, Any]]:
        if not isinstance(value, dict):
            return {}
        cleaned: dict[str, dict[str, Any]] = {}
        if int(max_items) <= 0:
            return cleaned
        for key, row in list(value.items())[-int(max_items):]:
            if isinstance(row, dict):
                cleaned[str(key)[:160]] = self._json_safe_town_focus_value(row, depth=max(1, int(depth)))
        return cleaned

    def _json_safe_town_focus_value(self, value: Any, *, depth: int = 3) -> Any:
        if depth <= 0:
            if isinstance(value, (str, int, float, bool)) or value is None:
                return value
            return str(value)[:180]
        if isinstance(value, dict):
            out: dict[str, Any] = {}
            for key, row in list(value.items())[:80]:
                out[str(key)[:96]] = self._json_safe_town_focus_value(row, depth=depth - 1)
            return out
        if isinstance(value, (list, tuple)):
            return [self._json_safe_town_focus_value(row, depth=depth - 1) for row in list(value)[:80]]
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        return str(value)[:180]

    def _town_focus_state_status_line(self) -> str:
        path = self._town_focus_state_path()
        if path is None:
            return "State: runtime memory only"
        if self._town_focus_state_error:
            detail = self._town_focus_state_notice or self._town_focus_state_error
            return f"State: safe fallback {detail[:42]}"
        size_kb = max(1, int((int(self._town_focus_last_state_bytes or 0) + 1023) // 1024)) if self._town_focus_last_state_bytes else 0
        schema = int(self._town_focus_last_state_schema or self._town_focus_state_schema_version())
        if self._town_focus_last_state_clock:
            if size_kb:
                return f"State v{schema}: saved {self._town_focus_last_state_clock} ({size_kb}KB)"
            return f"State v{schema}: saved {self._town_focus_last_state_clock}"
        if self._town_focus_state_loaded and (self._town_focus_npc_memory or self._town_focus_event_memory or self._town_focus_player_orders):
            return f"State v{schema}: restored previous town memory"
        return f"State v{schema}: ready"

    def _limit_state_mapping(self, value: Any, limit: int) -> dict[str, Any]:
        if not isinstance(value, dict) or int(limit) <= 0:
            return {}
        return dict(list(value.items())[-int(limit):])

    def _town_focus_state_payload(self, *, reason: str = "runtime") -> dict[str, Any]:
        town_id = str(self.selected_town_id or self._town_focus_last_town_id or "")
        schema = self._town_focus_state_schema_version()
        payload = {
            "schema": schema,
            "schema_version": schema,
            "runtime_id": DEFAULT_RUNTIME_ID,
            "reason": str(reason),
            "saved_at_unix": time.time(),
            "clock": self.current_clock(),
            "day_id": self.current_day_id(),
            "active": bool(self._town_focus_active and self.selected_town_id),
            "selected_town_id": str(self.selected_town_id or ""),
            "last_town_id": town_id,
            "follow_citizen_id": str(self._town_focus_follow_citizen_id or ""),
            "selected_detail": self._json_safe_town_focus_value(self._town_focus_selected_detail, depth=3),
            "last_order_feedback": str(self._town_focus_last_order_feedback or "")[:220],
            "npc_memory": self._json_safe_town_focus_value(self._limit_state_mapping(self._town_focus_npc_memory, self._town_focus_persistence_limit("max_npc_memory", 180, low=0, high=1000)), depth=4),
            "event_memory": self._json_safe_town_focus_value(self._limit_state_mapping(self._town_focus_event_memory, self._town_focus_persistence_limit("max_event_memory", 120, low=0, high=1000)), depth=4),
            "player_orders": self._json_safe_town_focus_value(self._limit_state_mapping(self._town_focus_player_orders, self._town_focus_persistence_limit("max_player_orders", 90, low=0, high=1000)), depth=4),
            "event_outcomes": self._json_safe_town_focus_value(self._limit_state_mapping(self._town_focus_event_outcomes, self._town_focus_persistence_limit("max_event_outcomes", 120, low=0, high=1000)), depth=4),
            "town_consequences": self._json_safe_town_focus_value(self._limit_state_mapping(self._town_focus_consequence_memory, self._town_focus_persistence_limit("max_town_consequences", 32, low=0, high=128)), depth=4),
            "town_health_reports": self._json_safe_town_focus_value(self._limit_state_mapping(self._town_focus_health_report_memory, self._town_focus_persistence_limit("max_town_health_reports", 96, low=0, high=500)), depth=4),
            "city_overview_signals": self._json_safe_town_focus_value(self._limit_state_mapping(self._city_overview_signal_memory, self._town_focus_persistence_limit("max_city_overview_signals", 48, low=0, high=256)), depth=4),
            "first_person_player_memory": self._json_safe_town_focus_value(self._limit_state_mapping(self._first_person_player_memory, self._town_focus_persistence_limit("max_first_person_player_memory", 16, low=0, high=64)), depth=4),
            "city_overview_last_signal_clock": str(self._city_overview_last_signal_clock or "")[:32],
            "limits": {
                "max_state_bytes": self._town_focus_state_max_bytes(),
                "max_npc_memory": self._town_focus_persistence_limit("max_npc_memory", 180, low=0, high=1000),
                "max_event_memory": self._town_focus_persistence_limit("max_event_memory", 120, low=0, high=1000),
                "max_player_orders": self._town_focus_persistence_limit("max_player_orders", 90, low=0, high=1000),
                "max_first_person_player_memory": self._town_focus_persistence_limit("max_first_person_player_memory", 16, low=0, high=64),
            },
            "policy": "runtime_state_only__authored_schedules_remain_read_only",
        }
        return payload

    def _encode_town_focus_state_payload(self, payload: dict[str, Any]) -> str:
        persistence = self._town_focus_persistence_config()
        pretty = bool(persistence.get("pretty_print_state", True))
        if pretty:
            return json.dumps(payload, indent=2, sort_keys=True)
        return json.dumps(payload, separators=(",", ":"), sort_keys=True)

    def _prune_town_focus_payload_for_size(self, payload: dict[str, Any], max_bytes: int) -> dict[str, Any]:
        if not isinstance(payload, dict):
            return {}
        pruned = dict(payload)
        tiers = [
            {"npc_memory": 120, "event_memory": 80, "player_orders": 60, "event_outcomes": 80, "town_health_reports": 64, "city_overview_signals": 36, "first_person_player_memory": 12},
            {"npc_memory": 72, "event_memory": 50, "player_orders": 40, "event_outcomes": 50, "town_health_reports": 36, "city_overview_signals": 24, "first_person_player_memory": 8},
            {"npc_memory": 36, "event_memory": 24, "player_orders": 24, "event_outcomes": 24, "town_health_reports": 18, "city_overview_signals": 12, "first_person_player_memory": 4},
        ]
        for tier_index, tier in enumerate(tiers, start=1):
            for key, limit in tier.items():
                pruned[key] = self._limit_state_mapping(pruned.get(key), limit)
            pruned["pruned_for_size"] = tier_index
            if len(self._encode_town_focus_state_payload(pruned).encode("utf-8")) <= max_bytes:
                return pruned
        # Last-resort recovery payload: keep only enough to reopen cleanly.
        return {
            "schema": self._town_focus_state_schema_version(),
            "schema_version": self._town_focus_state_schema_version(),
            "runtime_id": DEFAULT_RUNTIME_ID,
            "reason": str(payload.get("reason") or "runtime"),
            "saved_at_unix": time.time(),
            "clock": self.current_clock(),
            "day_id": self.current_day_id(),
            "selected_town_id": str(payload.get("selected_town_id") or ""),
            "last_town_id": str(payload.get("last_town_id") or ""),
            "last_order_feedback": str(payload.get("last_order_feedback") or "")[:180],
            "pruned_for_size": "minimal",
            "counts_before_prune": {
                "npc_memory": len(payload.get("npc_memory") or {}) if isinstance(payload.get("npc_memory"), dict) else 0,
                "event_memory": len(payload.get("event_memory") or {}) if isinstance(payload.get("event_memory"), dict) else 0,
                "player_orders": len(payload.get("player_orders") or {}) if isinstance(payload.get("player_orders"), dict) else 0,
            },
            "policy": "runtime_state_only__authored_schedules_remain_read_only",
        }

    def _save_town_focus_state(self, *, force: bool = False, reason: str = "runtime") -> bool:
        path = self._town_focus_state_path()
        if path is None:
            return False
        if not (self._town_focus_active or self._town_focus_last_town_id or self._town_focus_npc_memory or self._town_focus_event_memory or self._town_focus_player_orders or self._town_focus_event_outcomes or self._town_focus_consequence_memory or self._town_focus_health_report_memory or self._city_overview_signal_memory or self._first_person_player_memory):
            return False
        now = time.monotonic()
        persistence = self._town_focus_persistence_config()
        min_interval = max(0.5, _safe_float(persistence.get("autosave_interval_seconds"), 3.0))
        if not force and now - float(self._town_focus_last_state_save or 0.0) < min_interval:
            return False
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            payload = self._town_focus_state_payload(reason=reason)
            max_bytes = self._town_focus_state_max_bytes()
            encoded = self._encode_town_focus_state_payload(payload)
            if len(encoded.encode("utf-8")) > max_bytes:
                payload = self._prune_town_focus_payload_for_size(payload, max_bytes)
                encoded = self._encode_town_focus_state_payload(payload)
            if len(encoded.encode("utf-8")) > max_bytes:
                self._town_focus_state_error = "save:oversize_after_prune"
                return False
            if bool(persistence.get("backup_before_save", True)):
                self._backup_town_focus_state_file(path, label="backup")
            tmp = path.with_suffix(path.suffix + ".tmp")
            tmp.write_text(encoded, encoding="utf-8")
            tmp.replace(path)
            self._town_focus_last_state_save = now
            self._town_focus_last_state_clock = str(payload.get("clock") or self.current_clock())
            self._town_focus_last_state_bytes = int(len(encoded.encode("utf-8")))
            self._town_focus_last_state_schema = int(payload.get("schema_version") or payload.get("schema") or self._town_focus_state_schema_version())
            self._town_focus_state_error = ""
            self._town_focus_state_notice = ""
            return True
        except Exception as exc:
            self._town_focus_state_error = f"save:{exc.__class__.__name__}"
            return False

    def reset_town_focus_runtime_state(self) -> bool:
        """Clear runtime-only Town Focus save data without touching authored schedules."""
        self._town_focus_npc_memory.clear()
        self._town_focus_event_memory.clear()
        self._town_focus_player_orders.clear()
        self._town_focus_event_outcomes.clear()
        self._town_focus_consequence_memory.clear()
        self._town_focus_health_report_memory.clear()
        self._city_overview_signal_memory.clear()
        self._first_person_player_memory.clear()
        self._first_person_active = False
        self._first_person_last_interaction = ""
        self._city_overview_last_signal_clock = ""
        self._town_focus_selected_detail = {}
        self._town_focus_follow_citizen_id = ""
        self._town_focus_last_order_feedback = "Runtime state reset; authored schedules unchanged."
        self._town_focus_last_state_clock = ""
        self._town_focus_last_state_bytes = 0
        self._town_focus_last_state_schema = self._town_focus_state_schema_version()
        self._town_focus_state_error = ""
        self._town_focus_state_notice = "reset"
        self._invalidate_town_focus_perf_cache("state_reset")
        path = self._town_focus_state_path()
        try:
            if path is not None and path.exists():
                self._quarantine_town_focus_state_file(path, label="reset")
        except Exception:
            pass
        self._create_or_update_citizen_markers(force=True)
        return True

    def _town_focus_performance_config(self) -> dict[str, Any]:
        focus = self.config.get("town_focus") if isinstance(self.config.get("town_focus"), dict) else {}
        perf = focus.get("performance") if isinstance(focus.get("performance"), dict) else {}
        return dict(perf)

    def _town_focus_clock_bucket_key(self, clock: str, *, minutes: int | None = None) -> str:
        try:
            perf = self._town_focus_performance_config()
            bucket = int(minutes if minutes is not None else _safe_float(perf.get("snapshot_clock_bucket_minutes"), 20.0))
            bucket = max(5, min(90, bucket))
            total = self._town_focus_clock_minutes(str(clock or self.current_clock()))
            snapped = (total // bucket) * bucket
            return f"{snapped // 60:02d}:{snapped % 60:02d}/{bucket}m"
        except Exception:
            return str(clock or self.current_clock())

    def _town_focus_state_revision_key(self) -> str:
        selected = self._town_focus_selected_detail if isinstance(self._town_focus_selected_detail, dict) else {}
        return "|".join([
            str(len(self._town_focus_player_orders)),
            str(len(self._town_focus_event_outcomes)),
            str(len(self._town_focus_event_memory)),
            str(selected.get("kind") or ""),
            str(selected.get("event_id") or selected.get("citizen_id") or selected.get("key") or "")[:96],
            str(self._town_focus_follow_citizen_id or "")[:96],
            str(self._town_focus_last_order_feedback or "")[:80],
        ])

    def _town_focus_snapshot_cache_key_for_local(self, frame: dict[str, Any] | None, local: dict[str, dict[str, Any]], clock: str) -> str:
        perf = self._town_focus_performance_config()
        try:
            max_ids = int(_safe_float(perf.get("snapshot_key_max_citizens"), 40.0))
        except Exception:
            max_ids = 40
        rows = []
        for cid, data in sorted(local.items())[:max(8, max_ids)]:
            if not isinstance(data, dict):
                continue
            rows.append("/".join([
                str(cid),
                str(data.get("activity_id") or data.get("action") or ""),
                str(data.get("resolved_node") or data.get("target_node") or ""),
                str(data.get("visit_reason") or "")[:36],
            ]))
        return "||".join([
            str(self.selected_town_id or self._town_focus_last_town_id or ""),
            self.current_day_id(),
            self._town_focus_clock_bucket_key(clock),
            str(len(local)),
            ";".join(rows),
            self._town_focus_state_revision_key(),
        ])

    def _town_focus_visual_cache_key_for_snapshot(self, snapshot: dict[str, Any]) -> str:
        if not isinstance(snapshot, dict):
            return ""
        consequence = snapshot.get("consequence") if isinstance(snapshot.get("consequence"), dict) else {}
        health = snapshot.get("health_report") if isinstance(snapshot.get("health_report"), dict) else {}
        events = snapshot.get("events") if isinstance(snapshot.get("events"), list) else []
        clusters = snapshot.get("clusters") if isinstance(snapshot.get("clusters"), list) else []
        flows = snapshot.get("flows") if isinstance(snapshot.get("flows"), list) else []
        event_bits = [
            f"{str(e.get('event_id') or '')}:{int(e.get('pressure_percent') or 0)}:{str(e.get('outcome_state') or '')}"
            for e in events if isinstance(e, dict)
        ]
        cluster_bits = [
            f"{str(c.get('key') or '')}:{int(c.get('count') or 0)}"
            for c in clusters if isinstance(c, dict)
        ]
        flow_bits = [
            f"{str(f.get('citizen_id') or '')}:{str(f.get('next_label') or '')[:28]}"
            for f in flows[:12] if isinstance(f, dict)
        ]
        return "||".join([
            str(snapshot.get("clock") or self.current_clock()),
            str(consequence.get("status") or ""),
            str(consequence.get("dominant_need") or ""),
            str(int(consequence.get("pressure_percent") or 0)),
            str(health.get("grade") or ""),
            str(int(health.get("score") or 0)),
            ";".join(event_bits),
            ";".join(cluster_bits),
            ";".join(flow_bits),
            self._town_focus_state_revision_key(),
        ])

    def _invalidate_town_focus_perf_cache(self, reason: str = "") -> None:
        self._town_focus_life_snapshot_cache_key = ""
        self._town_focus_life_snapshot_cache = {}
        self._town_focus_visual_cache_key = ""
        self._town_focus_last_visual_build = 0.0
        self._town_focus_panel_cache_key = ""
        self._town_focus_detail_cache_key = ""
        if reason:
            self._town_focus_perf_stats["last_invalidation"] = str(reason)[:80]

    def _update_task(self, task: Any) -> Any:
        self._sync_world_visibility()
        # If the integrated city is hidden by a mode transition, skip visual and
        # simulation work entirely.  The next visible tick refreshes normally.
        if not self._visible or (self.city_root is not None and self.city_root.isHidden()):
            return getattr(task, "cont", task)
        runtime = self.config.get("citizen_runtime", {}) if isinstance(self.config.get("citizen_runtime"), dict) else {}
        interval = max(0.35, _safe_float(runtime.get("update_interval_seconds"), 1.15))
        now = time.monotonic()
        self._update_facade_pulse(now)
        if not self._first_person_active:
            self._update_town_focus_follow_camera(now)
        if now - self._last_update >= interval:
            self._last_update = now
            self._create_or_update_citizen_markers(force=False)
        return getattr(task, "cont", task)

    def _cache_facade_pulse_nodes(self) -> None:
        """Cache pulse metadata once so the frame task does not parse tags every tick."""
        self._facade_pulse_nodes.clear()
        self._facade_pulse_cache_ready = True
        self._facade_pulse_cursor = 0
        if self.city_root is None:
            return
        try:
            matches = self.city_root.findAllMatches("**")
            for node in matches:
                try:
                    if not node.hasPythonTag("holoutopia_facade_pulse"):
                        continue
                    tag = node.getPythonTag("holoutopia_facade_pulse")
                    if not isinstance(tag, dict):
                        continue
                    base = tag.get("base_color")
                    if not isinstance(base, tuple | list) or len(base) < 4:
                        continue
                    entry = (
                        node,
                        (float(base[0]), float(base[1]), float(base[2]), float(base[3])),
                        max(0.0, min(0.30, float(tag.get("strength") or 0.0))),
                        max(0.02, min(2.0, float(tag.get("speed") or 0.65))),
                        float(tag.get("phase") or 0.0),
                    )
                    self._facade_pulse_nodes.append(entry)
                except Exception:
                    continue
        except Exception as exc:
            self.error = f"facade-pulse-cache:{exc.__class__.__name__}:{exc}"

    def _update_facade_pulse(self, now: float) -> None:
        """Apply district glow in small batches instead of touching thousands of nodes per frame."""
        performance = self.config.get("performance", {}) if isinstance(self.config.get("performance"), dict) else {}
        if not bool(performance.get("facade_pulse_enabled", True)):
            return
        if not self._facade_pulse_cache_ready:
            self._cache_facade_pulse_nodes()
        entries = self._facade_pulse_nodes
        if not entries:
            return
        interval = max(0.04, _safe_float(performance.get("facade_pulse_interval_seconds"), 0.10))
        if now - self._last_facade_pulse_update < interval:
            return
        self._last_facade_pulse_update = now
        budget = int(max(64.0, _safe_float(performance.get("facade_pulse_nodes_per_tick"), 256.0)))
        budget = min(budget, len(entries))
        start = self._facade_pulse_cursor % max(1, len(entries))
        dead: set[int] = set()
        for offset in range(budget):
            idx = (start + offset) % len(entries)
            node, base, strength, speed, phase = entries[idx]
            try:
                if node is None or node.isEmpty():
                    dead.add(idx)
                    continue
                wave = 0.5 + 0.5 * math.sin(float(now) * speed + phase)
                scalar = 1.0 + strength * wave
                node.setColorScale(
                    min(1.0, base[0] * scalar),
                    min(1.0, base[1] * scalar),
                    min(1.0, base[2] * scalar),
                    base[3],
                )
            except Exception:
                dead.add(idx)
        self._facade_pulse_cursor = (start + budget) % max(1, len(entries))
        if dead and len(dead) > max(8, len(entries) // 64):
            self._facade_pulse_nodes = [entry for idx, entry in enumerate(entries) if idx not in dead]
            self._facade_pulse_cursor = min(self._facade_pulse_cursor, max(0, len(self._facade_pulse_nodes) - 1))

    def _create_status_label(self, parent: Any) -> None:
        try:
            from panda3d.core import TextNode
            text = TextNode("holoutopia_runtime_status_text")
            text.setAlign(TextNode.ACenter)
            text.setTextColor(0.80, 1.0, 1.0, 0.94)
            text.setText("HOLOUTOPIA LIVE CITY")
            node = parent.attachNewNode(text)
            node.setScale(18.0)
            node.setPos(0, -460, 52)
            node.setHpr(0, -62, 0)
            node.setLightOff(True)
            self.status_root = node
        except Exception:
            self.status_root = None

    def _create_or_update_citizen_markers(self, *, force: bool = False) -> None:
        if self.citizens_root is None:
            return
        try:
            from holoutopia_citizen_simulation import simulate_city_at_time
            frame = simulate_city_at_time(self.holoverse_root, self.current_clock(), danger_state=self._danger_state, inputs=self._inputs)
            authored_citizens = frame.get("citizens", {}) if isinstance(frame.get("citizens"), dict) else {}
            self._last_citizen_frame = frame
            runtime = self.config.get("citizen_runtime", {}) if isinstance(self.config.get("citizen_runtime"), dict) else {}
            population_model = frame.get("residential_population_model") if isinstance(frame.get("residential_population_model"), dict) else {}
            virtual_visible = population_model.get("visible_outdoor_citizens") if isinstance(population_model.get("visible_outdoor_citizens"), dict) else {}
            activity_visible = population_model.get("visible_activity_citizens") if isinstance(population_model.get("visible_activity_citizens"), dict) else {}
            if bool(runtime.get("show_virtual_population_representatives", True)) and (virtual_visible or activity_visible):
                # Activity representatives are sorted with act_* ids so a central-hub activity pass can fill the cap without Residential samples crowding it.
                citizens = {**virtual_visible, **activity_visible}
            elif bool(runtime.get("show_virtual_population_representatives", True)) and population_model:
                citizens = {}
            else:
                citizens = authored_citizens
            civic_visitors = {
                cid: data
                for cid, data in authored_citizens.items()
                if isinstance(data, dict) and isinstance(data.get("civic_visit"), dict)
            }
            focus_cfg = self.config.get("town_focus") if isinstance(self.config.get("town_focus"), dict) else {}
            if self._town_focus_active and self.selected_town_id:
                # Town Focus Mode is the Sims-style detail view: the full city is
                # still simulated deterministically, but only local citizens are
                # rendered/updated.  This preserves schedules and destinations
                # while avoiding full-world NPC overhead.
                focus_town = str(self.selected_town_id)
                local_authored = {
                    cid: data
                    for cid, data in authored_citizens.items()
                    if isinstance(data, dict) and str(data.get("town_id") or "") == focus_town
                }
                local_visitors = {
                    cid: data
                    for cid, data in civic_visitors.items()
                    if isinstance(data, dict) and str(data.get("town_id") or "") == focus_town
                }
                citizens = {**local_authored, **local_visitors}
                max_citizens = int(_safe_float(focus_cfg.get("max_visible_citizens"), 48.0))
            else:
                if civic_visitors:
                    # Keep the new visit-reason civilians visible even when the
                    # large virtual-population model is active.  They are authored
                    # citizens with real task-panel data, not generic crowd samples.
                    citizens = {**citizens, **civic_visitors}
                max_citizens = int(_safe_float(runtime.get("max_visible_citizens"), 120.0))
            self._last_visible_citizens = dict(citizens)
            visible_positions: dict[str, tuple[float, float, float]] = {}
            def _citizen_sort_key(item: tuple[str, Any]) -> tuple[int, str]:
                data = item[1]
                priority = 0 if isinstance(data, dict) and isinstance(data.get("civic_visit"), dict) else 1
                return priority, str(item[0])

            rendered_citizen_ids: set[str] = set()
            for idx, (cid, citizen) in enumerate(sorted(citizens.items(), key=_citizen_sort_key)):
                if idx >= max_citizens:
                    break
                rendered_citizen_ids.add(str(cid))
                node = self._marker_nodes.get(cid)
                if node is None or force:
                    if node is not None:
                        try:
                            node.removeNode()
                        except Exception:
                            pass
                    node = self._make_citizen_marker(str(cid), citizen)
                    self._marker_nodes[str(cid)] = node
                x, y, z = self._citizen_render_position(cid, citizen)
                visible_positions[str(cid)] = (float(x), float(y), float(z))
                node.setPos(x, y, z)
                self._orient_and_animate_person_marker(str(cid), node, citizen, x, y, z)
            self._last_visible_citizen_positions = visible_positions
            for cid in list(self._marker_nodes):
                if cid not in rendered_citizen_ids:
                    try:
                        self._marker_nodes[cid].removeNode()
                    except Exception:
                        pass
                    self._marker_nodes.pop(cid, None)
                    self._marker_phase.pop(cid, None)
            if self.status_root is not None:
                try:
                    danger = " // DANGER OVERRIDE" if self._danger_state else ""
                    population_model = frame.get("residential_population_model") if isinstance(frame.get("residential_population_model"), dict) else {}
                    if population_model:
                        activity_model = population_model.get("district_activity_model") if isinstance(population_model.get("district_activity_model"), dict) else {}
                        activity_label = ""
                        if int(activity_model.get("visible_activity_count", 0) or 0) > 0:
                            activity_label = f" // SIM HUB {activity_model.get('visible_activity_count')}/{activity_model.get('max_visible_activity_representatives_per_district')}"
                        adventure_state = activity_model.get("adventure_simulation_state") if isinstance(activity_model.get("adventure_simulation_state"), dict) else {}
                        adventure_label = ""
                        if bool(adventure_state.get("match_active")):
                            adventure_label = f" // ADV {adventure_state.get('active_player_count')}/{adventure_state.get('max_active_players')} Q{adventure_state.get('queue_count')} {adventure_state.get('remaining_label')}"
                        self.status_root.node().setText(
                            f"HOLOUTOPIA {frame.get('clock')} // POP {population_model.get('world_population')} "
                            f"// OUTDOOR {population_model.get('outdoor_population')}/{population_model.get('max_outdoor_population_per_district')}"
                            f"{activity_label}{adventure_label} // ENERGY {population_model.get('average_energy_percent')}%{danger}"
                        )
                    else:
                        self.status_root.node().setText(f"HOLOUTOPIA LIVE {frame.get('clock')} // {frame.get('citizen_count')} CITIZENS{danger}")
                except Exception:
                    pass
            self._create_or_update_service_operation_glyphs(frame)
            self._create_or_update_adventure_simulation_glyphs(frame)
            # Dialogue is built first so Watch Mode can show a tiny recent-talk log.
            self._create_or_update_dialogue_bubbles(frame)
            self._create_or_update_watch_panel(frame)
            self._create_or_update_city_overview_signals(frame)
            self._create_or_update_town_focus_panel(frame)
            self._create_or_update_town_focus_life_visuals(frame)
            self._create_or_update_town_focus_detail_panel(frame)
        except Exception as exc:
            self.error = f"marker-update:{exc.__class__.__name__}:{exc}"

    def _create_or_update_watch_panel(self, frame: dict[str, Any] | None = None) -> None:
        layers = self.config.get("render_layers", {}) if isinstance(self.config.get("render_layers"), dict) else {}
        if not bool(layers.get("watch_mode_panel", True)) or self.city_root is None:
            return
        if self._town_focus_active:
            for attr in ("watch_root", "focus_root"):
                node = getattr(self, attr, None)
                if node is not None:
                    try:
                        node.removeNode()
                    except Exception:
                        pass
                    setattr(self, attr, None)
            return
        if frame is None:
            frame = self._last_citizen_frame if isinstance(self._last_citizen_frame, dict) else {}
        if not frame:
            return
        if bool(getattr(self, "_inspector_focus_active", False)):
            for attr in ("watch_root", "focus_root"):
                node = getattr(self, attr, None)
                if node is not None:
                    try:
                        node.removeNode()
                    except Exception:
                        pass
                    try:
                        setattr(self, attr, None)
                    except Exception:
                        pass
            return
        try:
            if self.watch_root is not None:
                try:
                    self.watch_root.removeNode()
                except Exception:
                    pass
                self.watch_root = None
            from holoutopia_watch_mode import attach_watch_mode_panel
            self.watch_root = attach_watch_mode_panel(self.city_root, self.holoverse_root, frame, clock=str(frame.get("clock") or self.current_clock()))
            self._create_or_update_watch_focus_guides(frame)
        except Exception as exc:
            self.error = f"watch-panel:{exc.__class__.__name__}:{exc}"

    def _create_or_update_watch_focus_guides(self, frame: dict[str, Any] | None = None) -> None:
        layers = self.config.get("render_layers", {}) if isinstance(self.config.get("render_layers"), dict) else {}
        runtime = self.config.get("citizen_runtime", {}) if isinstance(self.config.get("citizen_runtime"), dict) else {}
        watch_cfg = runtime.get("watch_mode") if isinstance(runtime.get("watch_mode"), dict) else {}
        if not bool(layers.get("watch_focus_guides", True)) or not bool(watch_cfg.get("focus_guides_enabled", True)) or self.city_root is None:
            return
        if frame is None:
            frame = self._last_citizen_frame if isinstance(self._last_citizen_frame, dict) else {}
        if not frame:
            return
        try:
            if self.focus_root is not None:
                try:
                    self.focus_root.removeNode()
                except Exception:
                    pass
                self.focus_root = None
            from holoutopia_watch_focus import attach_watch_focus_guides
            self.focus_root = attach_watch_focus_guides(
                self.city_root,
                self.holoverse_root,
                frame,
                clock=str(frame.get("clock") or self.current_clock()),
                node_index=self._node_index,
            )
        except Exception as exc:
            self.error = f"watch-focus:{exc.__class__.__name__}:{exc}"



    def _create_or_update_adventure_simulation_glyphs(self, frame: dict[str, Any] | None = None) -> None:
        """Show the embedded Core Ring adventure simulation.

        The action lives in the Central Hub circle around the pyramid:
        collisionless visual markers show the active hub bubble, four active
        players, enemy silhouettes, magic/weapon action ticks, replacement queue,
        and hub respawn pads.
        """
        layers = self.config.get("render_layers", {}) if isinstance(self.config.get("render_layers"), dict) else {}
        if not bool(layers.get("adventure_simulation_hub_markers", True)) or self.city_root is None:
            return
        if self._town_focus_active:
            if self.adventure_sim_root is not None:
                try:
                    self.adventure_sim_root.removeNode()
                except Exception:
                    pass
                self.adventure_sim_root = None
            return
        if frame is None:
            frame = self._last_citizen_frame if isinstance(self._last_citizen_frame, dict) else {}
        try:
            if self.adventure_sim_root is not None:
                try:
                    self.adventure_sim_root.removeNode()
                except Exception:
                    pass
                self.adventure_sim_root = None
            pop = frame.get("residential_population_model") if isinstance(frame.get("residential_population_model"), dict) else {}
            activity = pop.get("district_activity_model") if isinstance(pop.get("district_activity_model"), dict) else {}
            state = activity.get("adventure_simulation_state") if isinstance(activity.get("adventure_simulation_state"), dict) else {}
            if not state:
                return
            from panda3d.core import LineSegs, TextNode
            root = self.city_root.attachNewNode("holoutopia_adventure_simulation_hub_markers")
            root.setLightOff(True)
            root.setTransparency(True)
            root.setPythonTag("holoutopia_adventure_simulation_state", state)
            root.setPythonTag("visual_only", True)
            self.adventure_sim_root = root
            active = bool(state.get("match_active"))
            color = (1.0, 0.45, 0.95, 0.90) if active else (0.35, 0.48, 0.62, 0.46)
            cyan = (0.25, 0.96, 1.0, 0.84) if active else (0.28, 0.55, 0.60, 0.36)
            gold = (1.0, 0.82, 0.34, 0.88) if active else (0.55, 0.48, 0.36, 0.32)

            layout = state.get("hub_ring_layout") if isinstance(state.get("hub_ring_layout"), dict) else {}
            arena_radius = float(layout.get("arena_radius") or 54.0)
            join_radius = float(layout.get("join_radius") or 76.0)
            respawn_radius = float(layout.get("respawn_radius") or 24.0)
            active_slot_radius = float(layout.get("active_slot_radius") or 48.0)

            # Embedded hub-dimension bubble: the action lives inside the Core
            # circle around the pyramid, not in a separate artifact route.
            seg = LineSegs("holoutopia_adventure_core_ring_bubble")
            seg.setThickness(3.15 if active else 1.25)
            seg.setColor(*color)
            for radius, z, thickness_scale in ((arena_radius, 63.0, 1.0), (join_radius, 66.0, 0.70), (respawn_radius, 61.5, 0.58)):
                last = None
                for k in range(97):
                    a = math.tau * k / 96.0
                    pnt = (math.cos(a) * radius, math.sin(a) * radius, z)
                    if k == 0:
                        seg.moveTo(*pnt)
                    else:
                        seg.drawTo(*pnt)
                seg.moveTo(radius, 0.0, z)
            # Cross spokes make it read as an active dimension plane.
            for spoke in range(8):
                a = math.tau * spoke / 8.0
                seg.moveTo(math.cos(a) * respawn_radius, math.sin(a) * respawn_radius, 63.0)
                seg.drawTo(math.cos(a) * arena_radius, math.sin(a) * arena_radius, 63.0)
            node = root.attachNewNode(seg.create())
            node.setLightOff(True)

            # Four active player slots are now inside the hub ring itself.
            players = state.get("active_players") if isinstance(state.get("active_players"), list) else []
            for idx in range(4):
                a = math.tau * idx / 4.0 + math.pi / 4.0
                x = math.cos(a) * active_slot_radius
                y = math.sin(a) * active_slot_radius
                slot = root.attachNewNode(f"holoutopia_adventure_active_slot_{idx + 1}")
                slot.setPos(x, y, 70.0)
                s = LineSegs(f"holoutopia_adventure_slot_icon_{idx + 1}")
                s.setThickness(2.45)
                s.setColor(*(gold if idx < len(players) else (0.30, 0.30, 0.38, 0.36)))
                size = 7.0
                # Tiny humanoid/action glyph with weapon/magic chevron.
                s.moveTo(0.0, 0.0, size)
                s.drawTo(0.0, 0.0, -size * 0.30)
                s.moveTo(-size * 0.55, 0.0, size * 0.35)
                s.drawTo(size * 0.55, 0.0, size * 0.35)
                s.moveTo(-size * 0.40, 0.0, -size)
                s.drawTo(0.0, 0.0, -size * 0.30)
                s.drawTo(size * 0.40, 0.0, -size)
                s.moveTo(size * 0.60, 0.0, size * 0.45)
                s.drawTo(size * 1.15, 0.0, size * 1.05)
                icon = slot.attachNewNode(s.create())
                icon.setLightOff(True)
                try:
                    slot.setBillboardPointEye()
                except Exception:
                    slot.setHpr(0.0, -55.0, 0.0)
                if idx < len(players):
                    slot.setPythonTag("adventure_player", players[idx])

            # Pass 51E: readable hero status bars and class ticks for the four
            # active slots. These stay visual-only and parented inside the Core Ring.
            hero_status = state.get("hero_status") if isinstance(state.get("hero_status"), list) else []
            if active and hero_status:
                hpseg = LineSegs("holoutopia_adventure_hero_status_bars")
                hpseg.setThickness(2.15)
                for idx, hero in enumerate(hero_status[:4]):
                    try:
                        a = math.tau * idx / 4.0 + math.pi / 4.0
                        x = math.cos(a) * active_slot_radius
                        y = math.sin(a) * active_slot_radius
                        pct = max(0.0, min(1.0, float(hero.get("hp_percent") or 0.0)))
                        band = str(hero.get("health_band") or "stable")
                        if band == "critical":
                            hpseg.setColor(1.0, 0.22, 0.24, 0.95)
                        elif band == "strained":
                            hpseg.setColor(1.0, 0.78, 0.22, 0.92)
                        else:
                            hpseg.setColor(0.34, 1.0, 0.58, 0.92)
                        width = 18.0
                        filled = width * pct
                        z = 85.0 + idx * 0.6
                        hpseg.moveTo(x - width * 0.5, y, z)
                        hpseg.drawTo(x - width * 0.5 + filled, y, z)
                        # small white cap indicates the full bar length
                        hpseg.setColor(0.88, 0.94, 1.0, 0.42)
                        hpseg.moveTo(x - width * 0.5, y, z - 1.4)
                        hpseg.drawTo(x + width * 0.5, y, z - 1.4)
                        class_id = str(hero.get("class_id") or "")
                        if "mage" in class_id:
                            hpseg.setColor(0.30, 0.96, 1.0, 0.96)
                        elif "archer" in class_id:
                            hpseg.setColor(0.42, 1.0, 0.44, 0.92)
                        elif "mender" in class_id:
                            hpseg.setColor(0.82, 0.44, 1.0, 0.92)
                        else:
                            hpseg.setColor(1.0, 0.82, 0.34, 0.92)
                        hpseg.moveTo(x, y, z + 2.2)
                        hpseg.drawTo(x, y, z + 7.0)
                    except Exception:
                        continue
                hpnode = root.attachNewNode(hpseg.create())
                hpnode.setLightOff(True)

            # Pass 51C combat prototype: enemy silhouettes and action ticks stay
            # inside the Core Ring bubble.  These are visual-only and never add
            # collisions or external routing.
            combat = state.get("combat_state") if isinstance(state.get("combat_state"), dict) else {}
            enemies = combat.get("enemies") if isinstance(combat.get("enemies"), list) else []
            actions = combat.get("actions") if isinstance(combat.get("actions"), list) else []
            if active and bool(combat.get("combat_active")):
                enemy_seg = LineSegs("holoutopia_adventure_enemy_silhouettes")
                enemy_seg.setThickness(2.25)
                enemy_seg.setColor(1.0, 0.18, 0.30, 0.86)
                for enemy in enemies[:8]:
                    try:
                        a = float(enemy.get("ring_angle") or 0.0)
                        r = float(enemy.get("ring_radius") or 42.0)
                        x = math.cos(a) * r
                        y = math.sin(a) * r
                        z = 68.0
                        size = 4.5 if str(enemy.get("status")) != "defeated" else 2.8
                        enemy_seg.moveTo(x, y, z + size)
                        enemy_seg.drawTo(x - size * 0.65, y, z - size * 0.25)
                        enemy_seg.drawTo(x, y, z - size * 1.0)
                        enemy_seg.drawTo(x + size * 0.65, y, z - size * 0.25)
                        enemy_seg.drawTo(x, y, z + size)
                        if str(enemy.get("status")) == "defeated":
                            enemy_seg.moveTo(x - size, y, z)
                            enemy_seg.drawTo(x + size, y, z)
                            enemy_seg.moveTo(x, y - size, z)
                            enemy_seg.drawTo(x, y + size, z)
                    except Exception:
                        continue
                enode = root.attachNewNode(enemy_seg.create())
                enode.setLightOff(True)

                # Pass 51E: tiny enemy health/status ticks so the wave reads as combat.
                enemy_hp_seg = LineSegs("holoutopia_adventure_enemy_hp_ticks")
                enemy_hp_seg.setThickness(1.6)
                for enemy in enemies[:8]:
                    try:
                        if str(enemy.get("status")) == "defeated":
                            continue
                        a = float(enemy.get("ring_angle") or 0.0)
                        r = float(enemy.get("ring_radius") or 42.0)
                        x = math.cos(a) * r
                        y = math.sin(a) * r
                        max_hp = max(1.0, float(enemy.get("max_hp") or 1.0))
                        pct = max(0.0, min(1.0, float(enemy.get("hp") or 0.0) / max_hp))
                        if pct < 0.35:
                            enemy_hp_seg.setColor(1.0, 0.20, 0.26, 0.88)
                        elif pct < 0.70:
                            enemy_hp_seg.setColor(1.0, 0.68, 0.22, 0.80)
                        else:
                            enemy_hp_seg.setColor(1.0, 0.28, 0.42, 0.78)
                        w = 8.0 * pct
                        enemy_hp_seg.moveTo(x - 4.0, y, 76.0)
                        enemy_hp_seg.drawTo(x - 4.0 + w, y, 76.0)
                    except Exception:
                        continue
                enemy_hp_node = root.attachNewNode(enemy_hp_seg.create())
                enemy_hp_node.setLightOff(True)

                action_seg = LineSegs("holoutopia_adventure_magic_weapon_ticks")
                action_seg.setThickness(2.0)
                for idx, action in enumerate(actions[:4]):
                    try:
                        pa = math.tau * idx / 4.0 + math.pi / 4.0
                        px = math.cos(pa) * active_slot_radius
                        py = math.sin(pa) * active_slot_radius
                        target_idx = idx % max(1, len(enemies))
                        enemy = enemies[target_idx] if enemies else {}
                        ea = float(enemy.get("ring_angle") or (pa + 0.8))
                        er = float(enemy.get("ring_radius") or 42.0)
                        ex = math.cos(ea) * er
                        ey = math.sin(ea) * er
                        if str(action.get("action_type") or "") == "magic":
                            action_seg.setColor(0.40, 0.88, 1.0, 0.82)
                        else:
                            action_seg.setColor(1.0, 0.82, 0.32, 0.78)
                        action_seg.moveTo(px, py, 72.0 + idx * 0.8)
                        action_seg.drawTo((px + ex) * 0.5, (py + ey) * 0.5, 81.0 + idx)
                        action_seg.drawTo(ex, ey, 70.0)
                    except Exception:
                        continue
                anode = root.attachNewNode(action_seg.create())
                anode.setLightOff(True)

                # Pass 51D: wave rings and hit sparks make the embedded combat
                # read like an active game instead of only static markers.
                wave = combat.get("wave_state") if isinstance(combat.get("wave_state"), dict) else {}
                wave_number = int(wave.get("wave_number") or combat.get("wave_number") or 1)
                wave_seg = LineSegs("holoutopia_adventure_wave_rings")
                wave_seg.setThickness(1.6 + min(3, wave_number) * 0.25)
                wave_seg.setColor(0.88, 0.32, 1.0, 0.30 + min(0.30, wave_number * 0.06))
                for rr in (arena_radius + wave_number * 3.0, arena_radius + wave_number * 8.0):
                    for k in range(65):
                        aa = math.tau * k / 64.0
                        xx = math.cos(aa) * rr
                        yy = math.sin(aa) * rr
                        if k == 0:
                            wave_seg.moveTo(xx, yy, 74.0 + wave_number * 1.3)
                        else:
                            wave_seg.drawTo(xx, yy, 74.0 + wave_number * 1.3)
                    wave_seg.moveTo(rr, 0.0, 74.0 + wave_number * 1.3)
                wave_node = root.attachNewNode(wave_seg.create())
                wave_node.setLightOff(True)

                # Pass 51E: wave spawn pulses on the Core Ring perimeter.
                spawn_pulses = combat.get("spawn_pulses") if isinstance(combat.get("spawn_pulses"), list) else []
                if spawn_pulses:
                    spseg = LineSegs("holoutopia_adventure_enemy_spawn_pulses")
                    spseg.setThickness(2.15)
                    for pulse in spawn_pulses[:8]:
                        try:
                            aa = float(pulse.get("ring_angle") or 0.0)
                            rr = float(pulse.get("ring_radius") or (arena_radius + 8.0))
                            intensity = max(0.15, min(1.0, float(pulse.get("intensity") or 0.4)))
                            spseg.setColor(1.0, 0.24, 0.66, 0.30 + intensity * 0.42)
                            xx = math.cos(aa) * rr
                            yy = math.sin(aa) * rr
                            zz = 82.0 + intensity * 4.0
                            size = 5.0 + intensity * 4.5
                            spseg.moveTo(xx - size, yy, zz)
                            spseg.drawTo(xx, yy + size, zz)
                            spseg.drawTo(xx + size, yy, zz)
                            spseg.drawTo(xx, yy - size, zz)
                            spseg.drawTo(xx - size, yy, zz)
                            spseg.moveTo(xx, yy, zz - size * 0.55)
                            spseg.drawTo(xx, yy, zz + size * 0.85)
                        except Exception:
                            continue
                    spnode = root.attachNewNode(spseg.create())
                    spnode.setLightOff(True)

                hit_effects = combat.get("hit_effects") if isinstance(combat.get("hit_effects"), list) else []
                if hit_effects:
                    hseg = LineSegs("holoutopia_adventure_hit_effects")
                    hseg.setThickness(2.35)
                    for hit in hit_effects[:8]:
                        try:
                            color_name = str(hit.get("color") or "cyan")
                            if color_name == "gold":
                                hseg.setColor(1.0, 0.82, 0.30, 0.92)
                            elif color_name == "green":
                                hseg.setColor(0.36, 1.0, 0.50, 0.90)
                            elif color_name == "violet":
                                hseg.setColor(0.84, 0.45, 1.0, 0.88)
                            else:
                                hseg.setColor(0.35, 0.95, 1.0, 0.92)
                            aa = float(hit.get("ring_angle") or 0.0)
                            rr = float(hit.get("ring_radius") or 42.0)
                            xx = math.cos(aa) * rr
                            yy = math.sin(aa) * rr
                            burst = 4.0 + float(hit.get("pulse") or 0.0) * 3.0
                            zz = 73.0
                            hseg.moveTo(xx - burst, yy, zz)
                            hseg.drawTo(xx + burst, yy, zz)
                            hseg.moveTo(xx, yy - burst, zz)
                            hseg.drawTo(xx, yy + burst, zz)
                            hseg.moveTo(xx, yy, zz - burst * 0.45)
                            hseg.drawTo(xx, yy, zz + burst * 0.70)
                        except Exception:
                            continue
                    hnode = root.attachNewNode(hseg.create())
                    hnode.setLightOff(True)
            # Respawn pads stay near the pyramid so defeated citizens visibly
            # return to the hub instead of disappearing into a route change.
            respawn_events = state.get("recent_respawns") if isinstance(state.get("recent_respawns"), list) else []
            rseg = LineSegs("holoutopia_adventure_respawn_pads")
            rseg.setThickness(2.0)
            rseg.setColor(0.55, 1.0, 0.84, 0.92 if active else 0.40)
            for idx in range(4):
                a = math.tau * idx / 4.0
                x = math.cos(a) * respawn_radius
                y = math.sin(a) * respawn_radius
                pad = 4.8 if idx < len(respawn_events) else 3.2
                rseg.moveTo(x - pad, y, 60.5)
                rseg.drawTo(x, y + pad, 60.5)
                rseg.drawTo(x + pad, y, 60.5)
                rseg.drawTo(x, y - pad, 60.5)
                rseg.drawTo(x - pad, y, 60.5)
                if idx < len(respawn_events):
                    rseg.moveTo(x, y, 60.5)
                    rseg.drawTo(x, y, 76.0)
            respawn_node = root.attachNewNode(rseg.create())
            respawn_node.setLightOff(True)

            # Queue ticks sit behind the hub and show replacements exist without cluttering roads.
            queue_count = int(state.get("queue_count") or 0)
            qseg = LineSegs("holoutopia_adventure_queue_ticks")
            qseg.setThickness(1.55)
            qseg.setColor(*cyan)
            for idx in range(min(8, queue_count)):
                x = -42.0 + idx * 12.0
                qseg.moveTo(x, 86.0, 54.0)
                qseg.drawTo(x, 86.0, 66.0)
            qnode = root.attachNewNode(qseg.create())
            qnode.setLightOff(True)

            label = TextNode("holoutopia_adventure_sim_status")
            label.setAlign(TextNode.ACenter)
            label.setTextColor(0.96, 0.88, 1.0, 0.96 if active else 0.55)
            if active:
                resp = int(state.get('recent_respawn_count') or 0)
                resp_text = f"  RESP {resp}" if resp else ""
                if bool(state.get("final_score_ready")):
                    label.setText(f"CORE RING FINAL  S{state.get('final_score')}  GRADE {state.get('final_grade')}  K{state.get('enemies_defeated')} D{state.get('player_defeats')}")
                elif bool(state.get("combat_active")):
                    wave_label = str(state.get('wave_label') or 'WAVE')
                    label.setText(f"CORE RING COMBAT  {wave_label}  {state.get('active_player_count')}/{state.get('max_active_players')}  FOES {state.get('enemies_alive')}/{state.get('enemy_count')}  S{state.get('team_score')}  {state.get('remaining_label')}{resp_text}")
                else:
                    label.setText(f"CORE RING ADV {state.get('active_player_count')}/{state.get('max_active_players')}  Q{state.get('queue_count')}  {state.get('remaining_label')}{resp_text}")
            else:
                label.setText("CORE RING ADV IDLE")
            text_node = root.attachNewNode(label)
            if bool(state.get("final_score_ready")):
                text_node.setScale(9.2)
                text_node.setPos(0.0, -104.0, 112.0)
                # Scoreboard bracket in front of the pyramid for final-frame readability.
                fseg = LineSegs("holoutopia_adventure_final_score_bracket")
                fseg.setThickness(3.0)
                fseg.setColor(1.0, 0.86, 0.32, 0.96)
                w, h, y, z = 112.0, 24.0, -105.0, 108.0
                fseg.moveTo(-w * 0.5, y, z - h * 0.5)
                fseg.drawTo(w * 0.5, y, z - h * 0.5)
                fseg.drawTo(w * 0.5, y, z + h * 0.5)
                fseg.drawTo(-w * 0.5, y, z + h * 0.5)
                fseg.drawTo(-w * 0.5, y, z - h * 0.5)
                fnode = root.attachNewNode(fseg.create())
                fnode.setLightOff(True)
                final_state = state.get("final_score_state") if isinstance(state.get("final_score_state"), dict) else {}
                scoreboard_lines = final_state.get("scoreboard_lines") if isinstance(final_state.get("scoreboard_lines"), list) else []
                for line_idx, line in enumerate(scoreboard_lines[:4]):
                    try:
                        line_node = TextNode(f"holoutopia_adventure_final_score_line_{line_idx}")
                        line_node.setAlign(TextNode.ACenter)
                        line_node.setText(str(line))
                        line_node.setTextColor(1.0, 0.92, 0.62, 0.92 if line_idx < 2 else 0.78)
                        lnode = root.attachNewNode(line_node)
                        lnode.setScale(5.2 if line_idx == 0 else 4.2)
                        lnode.setPos(0.0, -106.0, 96.0 - line_idx * 8.0)
                        try:
                            lnode.setBillboardPointEye()
                        except Exception:
                            lnode.setHpr(0.0, -55.0, 0.0)
                        lnode.setLightOff(True)
                    except Exception:
                        continue
            else:
                text_node.setScale(7.6 if active else 6.4)
                text_node.setPos(0.0, 98.0, 78.0)
            try:
                text_node.setBillboardPointEye()
            except Exception:
                text_node.setHpr(0.0, -55.0, 0.0)
            text_node.setLightOff(True)
        except Exception as exc:
            self.error = f"adventure-sim-glyphs:{exc.__class__.__name__}:{exc}"

    def _create_or_update_service_operation_glyphs(self, frame: dict[str, Any] | None = None) -> None:
        """Attach tiny visual-only operation glyphs above functional-service citizens."""
        layers = self.config.get("render_layers", {}) if isinstance(self.config.get("render_layers"), dict) else {}
        if not bool(layers.get("service_operation_glyphs", True)) or self.city_root is None:
            return
        if self._town_focus_active:
            # Local citizens remain visible in focus mode; skip extra global service
            # glyphs so the isolated town stays readable and cheap.
            if self.service_ops_root is not None:
                try:
                    self.service_ops_root.removeNode()
                except Exception:
                    pass
                self.service_ops_root = None
            return
        try:
            if self.service_ops_root is not None:
                try:
                    self.service_ops_root.removeNode()
                except Exception:
                    pass
                self.service_ops_root = None
            citizens = self._last_visible_citizens if isinstance(self._last_visible_citizens, dict) else {}
            positions = self._last_visible_citizen_positions if isinstance(self._last_visible_citizen_positions, dict) else {}
            service_items = [
                (str(cid), citizen)
                for cid, citizen in sorted(citizens.items())
                if isinstance(citizen, dict) and bool(citizen.get("service_behavior_assignment")) and str(cid) in positions
            ]
            if not service_items:
                return
            from panda3d.core import LineSegs
            root = self.city_root.attachNewNode("holoutopia_service_operation_glyphs")
            root.setLightOff(True)
            root.setTransparency(True)
            root.setPythonTag("holoutopia_service_operation_glyphs", True)
            self.service_ops_root = root
            max_glyphs = 12
            for idx, (cid, citizen) in enumerate(service_items[:max_glyphs]):
                x, y, z = positions.get(cid, (0.0, 0.0, 0.0))
                glyph = str(citizen.get("service_glyph") or "node_tick")
                color = _service_glyph_color(glyph, citizen)
                anchor = root.attachNewNode(f"holoutopia_service_glyph_{idx:02d}_{cid}")
                anchor.setPos(float(x) + ((idx % 3) - 1) * 1.4, float(y) + ((idx // 3) % 2) * 1.2, float(z) + 9.4)
                try:
                    anchor.setBillboardPointEye()
                except Exception:
                    anchor.setHpr(0.0, -55.0, 0.0)
                seg = LineSegs(f"holoutopia_service_glyph_shape_{idx:02d}")
                seg.setThickness(1.35)
                seg.setColor(*color)
                _draw_service_glyph(seg, glyph)
                node = anchor.attachNewNode(seg.create())
                node.setLightOff(True)
                anchor.setPythonTag("holoutopia_service_operation", {
                    "citizen_id": cid,
                    "service": str(citizen.get("service_short_label") or citizen.get("service_building_name") or "Service"),
                    "operation": str(citizen.get("service_action_label") or citizen.get("service_operation_id") or "service"),
                    "output": str(citizen.get("service_output_label") or "service active"),
                    "glyph": glyph,
                    "visual_only": True,
                })
        except Exception as exc:
            self.error = f"service-glyphs:{exc.__class__.__name__}:{exc}"

    def _create_or_update_dialogue_bubbles(self, frame: dict[str, Any] | None = None) -> None:
        """Attach small proximity-only citizen speech bubbles with non-overlap guards."""
        layers = self.config.get("render_layers", {}) if isinstance(self.config.get("render_layers"), dict) else {}
        runtime = self.config.get("citizen_runtime", {}) if isinstance(self.config.get("citizen_runtime"), dict) else {}
        dialogue_cfg = runtime.get("citizen_dialogue") if isinstance(runtime.get("citizen_dialogue"), dict) else {}
        if not bool(layers.get("citizen_dialogue_bubbles", True)) or not bool(dialogue_cfg.get("enabled", True)):
            return
        if self.city_root is None:
            return
        if frame is None:
            frame = self._last_citizen_frame if isinstance(self._last_citizen_frame, dict) else {}
        if not frame:
            return
        try:
            if self.speech_root is not None:
                try:
                    self.speech_root.removeNode()
                except Exception:
                    pass
                self.speech_root = None
            from holoutopia_citizen_dialogue import build_dialogue_state
            day_id = self.current_day_id()
            if self._dialogue_day_id != day_id:
                self._dialogue_day_id = day_id
                self._dialogue_daily_memory = {}
            state = build_dialogue_state(
                self.holoverse_root,
                frame,
                self._last_visible_citizens if isinstance(self._last_visible_citizens, dict) else {},
                self._last_visible_citizen_positions if isinstance(self._last_visible_citizen_positions, dict) else {},
                clock=str(frame.get("clock") or self.current_clock()),
                day_id=day_id,
                daily_memory=self._dialogue_daily_memory,
            )
            self._last_dialogue_state = state
            try:
                frame["citizen_dialogue_state"] = state
            except Exception:
                pass
            bubbles = state.get("active_bubbles") if isinstance(state.get("active_bubbles"), list) else []
            if not bubbles:
                return
            from panda3d.core import LineSegs, TextNode
            root = self.city_root.attachNewNode("holoutopia_citizen_dialogue_bubbles")
            root.setLightOff(True)
            root.setTransparency(True)
            root.setPythonTag("holoutopia_citizen_dialogue_state", state)
            self.speech_root = root
            scale = _safe_float(dialogue_cfg.get("bubble_scale"), _safe_float((state or {}).get("bubble_scale"), 3.45))
            max_width = max(4.5, _safe_float(dialogue_cfg.get("max_card_width"), 22.0))
            for idx, bubble in enumerate(bubbles):
                if not isinstance(bubble, dict):
                    continue
                text = str(bubble.get("text") or "").strip()
                if not text:
                    continue
                x = _safe_float(bubble.get("x"), 0.0)
                y = _safe_float(bubble.get("y"), 0.0)
                z = _safe_float(bubble.get("z"), 14.0)
                # Alternate tiny side offsets so close but valid pairs do not draw on the same vertical line.
                side = -1.0 if idx % 2 else 1.0
                node_root = root.attachNewNode(f"holoutopia_speech_anchor_{idx:02d}")
                node_root.setPos(x + side * 4.0, y - 1.5 * float(idx % 3), z)
                try:
                    node_root.setBillboardPointEye()
                except Exception:
                    node_root.setHpr(0.0, -55.0, 0.0)

                text_node = TextNode(f"holoutopia_speech_text_{idx:02d}")
                text_node.setAlign(TextNode.ACenter)
                text_node.setText(text)
                text_node.setTextColor(0.90, 1.0, 1.0, 0.94)
                text_node.setCardColor(0.015, 0.025, 0.040, 0.68)
                text_node.setCardAsMargin(0.55, 0.55, 0.25, 0.25)
                text_node.setFrameColor(0.18, 0.96, 1.0, 0.55)
                text_node.setFrameAsMargin(0.60, 0.60, 0.30, 0.30)
                try:
                    text_node.setWordwrap(max_width)
                except Exception:
                    pass
                txt = node_root.attachNewNode(text_node)
                txt.setScale(scale)
                txt.setLightOff(True)
                txt.setPythonTag("holoutopia_dialogue_bubble", bubble)

                # One tiny speech tick under the card. This is not a citizen circle.
                seg = LineSegs(f"holoutopia_speech_tick_{idx:02d}")
                seg.setThickness(1.1)
                kind = str(bubble.get("kind") or "informative")
                if kind == "positive":
                    seg.setColor(0.50, 1.0, 0.58, 0.72)
                elif kind == "negative":
                    seg.setColor(1.0, 0.36, 0.28, 0.72)
                elif kind == "greeting":
                    seg.setColor(0.46, 0.92, 1.0, 0.72)
                else:
                    seg.setColor(0.92, 0.72, 1.0, 0.72)
                seg.moveTo(0.0, 0.0, -1.2)
                seg.drawTo(-side * 3.0, 0.0, -5.5)
                tick = node_root.attachNewNode(seg.create())
                tick.setLightOff(True)
        except Exception as exc:
            self.error = f"citizen-dialogue:{exc.__class__.__name__}:{exc}"

    def _make_citizen_marker(self, cid: str, citizen: dict[str, Any]) -> Any:
        from panda3d.core import LineSegs
        activity_id = str(citizen.get("activity_id") or "unknown_activity")
        color = _activity_color(activity_id, bool(self._danger_state), str(citizen.get("location_mode") or ""))
        root = self.citizens_root.attachNewNode(f"holoutopia_little_person_{cid}")
        root.setLightOff(True)
        root.setTransparency(True)
        self._marker_phase[cid] = _stable_fraction(cid, 0.0) * math.tau
        person_cfg = _robot_marker_config(self.config)
        height = float(person_cfg.get("height", 7.5))
        width = float(person_cfg.get("width", 1.8))
        depth = float(person_cfg.get("depth", 1.2))
        foot_z = 0.0
        hip_z = height * 0.34
        torso_bottom = height * 0.38
        torso_top = height * 0.70
        shoulder_z = height * 0.66
        neck_z = height * 0.73
        head_bottom = height * 0.74
        head_top = height * 0.96
        root.setPythonTag("holoutopia_little_person", True)
        root.setPythonTag("holoutopia_citizen_id", cid)
        root.setPythonTag("holoutopia_person_height", height)
        # Keep the legacy tag name too so older inspectors/tests do not fail.
        root.setPythonTag("holoutopia_robot_height", height)
        root.setPythonTag("holoutopia_person_color", color)

        body = LineSegs(f"{cid}_person_body")
        body.setThickness(float(person_cfg.get("body_line_thickness", 1.35)))
        body.setColor(*color)
        # Compact torso and head boxes read as tiny 3D people from street level.
        _line_box(body, -width * 0.34, -depth * 0.26, torso_bottom, width * 0.34, depth * 0.26, torso_top)
        _line_box(body, -width * 0.25, -depth * 0.22, head_bottom, width * 0.25, depth * 0.22, head_top)
        # Shoulder/hip bars and a tiny forward face tick. Local +Y is facing direction.
        body.moveTo(-width * 0.52, 0.0, shoulder_z)
        body.drawTo(width * 0.52, 0.0, shoulder_z)
        body.moveTo(-width * 0.30, 0.0, hip_z)
        body.drawTo(width * 0.30, 0.0, hip_z)
        body.moveTo(-width * 0.10, depth * 0.24, head_bottom + (head_top - head_bottom) * 0.52)
        body.drawTo(width * 0.10, depth * 0.24, head_bottom + (head_top - head_bottom) * 0.52)
        body.moveTo(0.0, 0.0, torso_top)
        body.drawTo(0.0, 0.0, neck_z)
        body_node = root.attachNewNode(body.create())
        body_node.setLightOff(True)
        body_node.setPythonTag("holoutopia_person_part", "body")

        limb_color = (min(1.0, color[0] + 0.12), min(1.0, color[1] + 0.12), min(1.0, color[2] + 0.12), color[3])
        limbs: dict[str, Any] = {}
        for name, pivot, endpoint in (
            ("left_arm", (-width * 0.52, 0.0, shoulder_z), (-width * 0.70, 0.0, height * 0.42)),
            ("right_arm", (width * 0.52, 0.0, shoulder_z), (width * 0.70, 0.0, height * 0.42)),
            ("left_leg", (-width * 0.18, 0.0, hip_z), (-width * 0.32, 0.0, foot_z)),
            ("right_leg", (width * 0.18, 0.0, hip_z), (width * 0.32, 0.0, foot_z)),
        ):
            limb_root = root.attachNewNode(f"{cid}_{name}_pivot")
            limb_root.setPos(*pivot)
            seg = LineSegs(f"{cid}_{name}")
            seg.setThickness(float(person_cfg.get("limb_line_thickness", 1.15)))
            seg.setColor(*limb_color)
            seg.moveTo(0.0, 0.0, 0.0)
            seg.drawTo(endpoint[0] - pivot[0], endpoint[1] - pivot[1], endpoint[2] - pivot[2])
            limb_node = limb_root.attachNewNode(seg.create())
            limb_node.setLightOff(True)
            limb_root.setPythonTag("holoutopia_person_limb", name)
            limbs[name] = limb_root
        root.setPythonTag("holoutopia_robot_limbs", limbs)
        root.setPythonTag("holoutopia_person_has_ground_ring", False)
        root.setPythonTag("holoutopia_person_has_name_label", False)
        return root

    def _orient_and_animate_person_marker(self, cid: str, node: Any, citizen: dict[str, Any], x: float, y: float, z: float) -> None:
        """Face each little 3D person along its schedule direction and swing limbs lightly."""
        try:
            heading = self._citizen_heading_degrees(cid, citizen)
            node.setH(heading)
        except Exception:
            pass
        try:
            phase = self._marker_phase.get(cid)
            if phase is None:
                phase = _stable_fraction(cid, 0.0) * math.tau
                self._marker_phase[cid] = phase
            activity = str(citizen.get("activity_id") or "").lower()
            pose = str(citizen.get("activity_pose") or "").lower()
            moving = (
                pose in {"arrival_walk", "return_walk", "commute_walk"}
                or any(token in activity for token in ("commute", "errand", "visit", "return"))
            ) and str(citizen.get("location_mode")) != "private_home_hidden"
            speed = _safe_float(citizen.get("activity_animation_speed"), 5.2 if moving else 1.25)
            amp = _safe_float(citizen.get("activity_animation_amp"), 10.0 if moving else 2.5)
            swing = math.sin(time.monotonic() * speed + phase) * amp
            limbs = node.getPythonTag("holoutopia_robot_limbs") or {}
            pose_set = {"pod_focus", "console_work", "social_sync", "briefing_attention", "reading_lore", "cooldown_sway", "idle_activity"}
            for name, limb in dict(limbs).items():
                try:
                    if moving or pose not in pose_set:
                        if name == "left_arm":
                            limb.setP(swing)
                            limb.setR(0)
                        elif name == "right_arm":
                            limb.setP(-swing)
                            limb.setR(0)
                        elif name == "left_leg":
                            limb.setP(-swing * 0.82)
                            limb.setR(0)
                        elif name == "right_leg":
                            limb.setP(swing * 0.82)
                            limb.setR(0)
                    elif pose == "console_work":
                        if name == "left_arm":
                            limb.setP(-34.0 + swing * 0.20)
                            limb.setR(-10.0)
                        elif name == "right_arm":
                            limb.setP(-32.0 - swing * 0.20)
                            limb.setR(10.0)
                        elif name.endswith("leg"):
                            limb.setP(0.0)
                            limb.setR(0.0)
                    elif pose == "pod_focus":
                        if name == "left_arm":
                            limb.setP(-18.0 + swing * 0.15)
                            limb.setR(-4.0)
                        elif name == "right_arm":
                            limb.setP(-18.0 - swing * 0.15)
                            limb.setR(4.0)
                        elif name.endswith("leg"):
                            limb.setP(swing * 0.10)
                            limb.setR(0.0)
                    elif pose == "social_sync":
                        if name == "left_arm":
                            limb.setP(-10.0 + swing * 0.55)
                            limb.setR(-18.0)
                        elif name == "right_arm":
                            limb.setP(-28.0 - swing * 0.45)
                            limb.setR(14.0)
                        elif name.endswith("leg"):
                            limb.setP(swing * 0.18)
                            limb.setR(0.0)
                    elif pose == "briefing_attention":
                        if name.endswith("arm"):
                            limb.setP(6.0 + swing * 0.10)
                            limb.setR(0.0)
                        elif name.endswith("leg"):
                            limb.setP(0.0)
                            limb.setR(0.0)
                    elif pose == "reading_lore":
                        if name == "left_arm":
                            limb.setP(-24.0 + swing * 0.10)
                            limb.setR(-5.0)
                        elif name == "right_arm":
                            limb.setP(-24.0 - swing * 0.10)
                            limb.setR(5.0)
                        elif name.endswith("leg"):
                            limb.setP(0.0)
                            limb.setR(0.0)
                    elif pose == "cooldown_sway":
                        if name == "left_arm":
                            limb.setP(8.0 + swing * 0.70)
                            limb.setR(-3.0)
                        elif name == "right_arm":
                            limb.setP(-8.0 - swing * 0.70)
                            limb.setR(3.0)
                        elif name.endswith("leg"):
                            limb.setP(swing * 0.16)
                            limb.setR(0.0)
                    else:
                        if name == "left_arm":
                            limb.setP(swing * 0.50)
                        elif name == "right_arm":
                            limb.setP(-swing * 0.50)
                        elif name == "left_leg":
                            limb.setP(-swing * 0.25)
                        elif name == "right_leg":
                            limb.setP(swing * 0.25)
                except Exception:
                    pass
            height = _safe_float(node.getPythonTag("holoutopia_person_height") or node.getPythonTag("holoutopia_robot_height"), 7.5)
            bob = (math.sin(time.monotonic() * speed + phase) * (0.16 if moving else 0.045))
            # Keep private-home markers subdued but still present for proof/debug.
            node.setZ(float(z) + bob)
            color = _activity_color(str(citizen.get("activity_id") or "unknown_activity"), bool(self._danger_state), str(citizen.get("location_mode") or ""))
            node.setColorScale(1.0, 1.0, 1.0, 0.62 if str(citizen.get("location_mode")) == "private_home_hidden" else 1.0)
            node.setPythonTag("holoutopia_person_animation", {"moving": moving, "pose": pose or "default", "swing": round(float(swing), 3), "height": height, "facing_degrees": round(float(node.getH()), 3), "activity_id": str(citizen.get("activity_id") or ""), "activity_status": str(citizen.get("activity_status") or ""), "pathfinding": citizen.get("pathfinding", {}) if isinstance(citizen.get("pathfinding"), dict) else {}})
        except Exception:
            pass

    def _citizen_heading_degrees(self, cid: str, citizen: dict[str, Any]) -> float:
        """Resolve a stable schedule-facing angle where local +Y is forward."""
        try:
            if bool(citizen.get("commute_flow_representative")):
                direction = str(citizen.get("commute_direction") or "outbound")
                stage = str(citizen.get("commute_stage") or "")
                if direction == "return":
                    return 92.0 if "simulation" in stage or "interdistrict" in stage else -88.0
                return -88.0 if "residential" in stage or "interdistrict" in stage else 92.0
            if bool(citizen.get("district_activity_representative")) and str(citizen.get("activity_face_target") or "") == "cluster_center":
                placement = citizen.get("pathfinding") if isinstance(citizen.get("pathfinding"), dict) else {}
                grid = placement.get("grid")
                target_grid = placement.get("target_grid")
                town_id = str(placement.get("town_id") or citizen.get("town_id") or "central_core_civic_ring")
                if isinstance(grid, (list, tuple)) and isinstance(target_grid, (list, tuple)) and len(grid) >= 2 and len(target_grid) >= 2:
                    from holoutopia_pathfinding import grid_to_city_xy
                    sx, sy = grid_to_city_xy(self.holoverse_root, town_id, (float(grid[0]), float(grid[1])))
                    tx, ty = grid_to_city_xy(self.holoverse_root, town_id, (float(target_grid[0]), float(target_grid[1])))
                    if _dist2((sx, sy), (tx, ty)) >= 0.25:
                        return math.degrees(math.atan2(float(tx) - float(sx), float(ty) - float(sy)))
            schedules = (self._inputs or {}).get("citizen_schedules", {}).get("schedules", {})
            schedule = schedules.get(cid) if isinstance(schedules, dict) else None
            blocks = schedule.get("blocks") if isinstance(schedule, dict) else []
            if not isinstance(blocks, list) or not blocks:
                return _stable_fraction(cid, 0.0) * 360.0
            idx = int(citizen.get("schedule_index", 0) or 0)
            idx = max(0, min(idx, len(blocks) - 1))
            current_target = str((blocks[idx] or {}).get("target") or citizen.get("resolved_node") or "")
            # Use previous node for arrival-facing, next node for idle/home/sleep.
            prev_target = str((blocks[max(0, idx - 1)] or {}).get("target") or "")
            next_target = str((blocks[min(len(blocks) - 1, idx + 1)] or {}).get("target") or "")
            current = self._render_xy_for_node_id(current_target) or self._render_xy_for_node_id(str(citizen.get("resolved_node") or ""))
            source = self._render_xy_for_node_id(prev_target)
            if source is None or current is None or _dist2(source, current) < 1.0:
                target = self._render_xy_for_node_id(next_target)
                if target is not None and current is not None and _dist2(current, target) >= 1.0:
                    source, current = current, target
            if source is None or current is None or _dist2(source, current) < 1.0:
                return _stable_fraction(cid, 0.17) * 360.0
            dx = float(current[0]) - float(source[0])
            dy = float(current[1]) - float(source[1])
            return math.degrees(math.atan2(dx, dy))
        except Exception:
            return _stable_fraction(cid, 0.31) * 360.0

    def _render_xy_for_node_id(self, node_id: str) -> tuple[float, float] | None:
        node_id = str(node_id or "").strip()
        if not node_id:
            return None
        node = self._node_index.get(node_id)
        if node is None:
            return None
        return _node_grid_to_city_render_xy(self.holoverse_root, node.town_id, node.grid)

    def _citizen_render_position(self, cid: str, citizen: dict[str, Any]) -> tuple[float, float, float]:
        node_id = str(citizen.get("resolved_node") or citizen.get("target_node") or "")
        # Visible population representatives use street-safe placement so they never stand on building roofs/footprints.
        if bool(citizen.get("virtual_population_representative")) or bool(citizen.get("district_activity_representative")):
            try:
                from holoutopia_pathfinding import safe_outdoor_xy_for_citizen

                x, y, placement = safe_outdoor_xy_for_citizen(self.holoverse_root, str(cid), citizen, self._node_index)
                citizen["pathfinding"] = placement
                return float(x), float(y), 1.75
            except Exception:
                # Conservative fallback: keep older Residential street path rather than placing on home/building nodes.
                x, y = _virtual_residential_street_position(cid, citizen)
                return float(x), float(y), 1.75
        node = self._node_index.get(node_id)
        if node is not None:
            x, y = _node_grid_to_city_render_xy(self.holoverse_root, node.town_id, node.grid)
        else:
            pos = citizen.get("position") if isinstance(citizen.get("position"), dict) else {}
            x = _safe_float(pos.get("x"), 0.0)
            y = _safe_float(pos.get("y"), 0.0)
        spread = _robot_marker_config(self.config).get("same_node_spread_radius", 10.0)
        # Stable offset prevents authored citizens at the same non-population node from becoming a single person.
        angle = _stable_fraction(cid, 0.25) * math.tau
        ring = 0.35 + _stable_fraction(cid, 0.61) * 0.65
        x += math.cos(angle) * float(spread) * ring
        y += math.sin(angle) * float(spread) * ring
        # Keep people grounded on the street plane; no floating debug rings.
        z = 1.25 if str(citizen.get("location_mode")) == "private_home_hidden" else 1.75
        return float(x), float(y), z

    def _install_panel_manager(self) -> None:
        """Create the movable/snap UI layer for citizen/building inspectors."""
        try:
            from holoutopia_snap_panels import MovableSnapPanelManager
            panel_cfg = self.config.get("panels", {}) if isinstance(self.config.get("panels"), dict) else {}
            self.panel_manager = MovableSnapPanelManager(
                self.app,
                default_snap=str(panel_cfg.get("default_snap") or "left"),
                max_open_panels=int(_safe_float(panel_cfg.get("max_open_panels"), 4.0)),
                debug_raw_ids=bool(panel_cfg.get("debug_raw_ids", False)),
                on_all_panels_closed=self._on_all_inspector_panels_closed,
            )
        except Exception as exc:
            self.error = f"panel-manager:{exc.__class__.__name__}:{exc}"
            self.panel_manager = None

    def close_focused_panel(self) -> bool:
        try:
            if self.panel_manager is not None:
                closed = bool(self.panel_manager.close_focused())
                if closed and not getattr(self.panel_manager, "panels", {}):
                    self._on_all_inspector_panels_closed()
                return closed
        except Exception:
            pass
        return False

    def _on_all_inspector_panels_closed(self) -> None:
        self._inspector_focus_active = False
        self._clear_building_selection_visuals()
        try:
            self._create_or_update_watch_panel(self._last_citizen_frame)
        except Exception:
            pass

    def select_citizen(self, citizen_id: str) -> bool:
        """Open a read-only movable inspector for the requested citizen id."""
        citizen_id = str(citizen_id or "").strip()
        if not citizen_id:
            return False
        try:
            from holoutopia_citizen_tasks import citizen_panel_payload
            frame_citizen = {}
            visible = self._last_visible_citizens if isinstance(self._last_visible_citizens, dict) else {}
            citizens = self._last_citizen_frame.get("citizens", {}) if isinstance(self._last_citizen_frame.get("citizens"), dict) else {}
            if isinstance(visible.get(citizen_id), dict):
                frame_citizen = visible[citizen_id]
            elif isinstance(citizens.get(citizen_id), dict):
                frame_citizen = citizens[citizen_id]
            if bool(frame_citizen.get("virtual_population_representative")):
                from holoutopia_residential_population import virtual_population_panel_payload

                payload = virtual_population_panel_payload(frame_citizen, clock=self.current_clock())
            else:
                payload = citizen_panel_payload(
                    self.holoverse_root,
                    citizen_id,
                    clock=self.current_clock(),
                    danger_state=bool(self._danger_state),
                    frame_citizen=frame_citizen,
                    inputs=self._task_inputs,
                )
            if not payload.get("ok"):
                return False
            if self.panel_manager is None:
                self._install_panel_manager()
            if self.panel_manager is None:
                return False
            self.panel_manager.show_citizen_panel(payload)
            self._inspector_focus_active = True
            self._clear_building_selection_visuals()
            self.selected_citizen_id = citizen_id
            if self._town_focus_active:
                nxt = self._citizen_next_destination(citizen_id, frame_citizen if isinstance(frame_citizen, dict) else {})
                self._town_focus_follow_citizen_id = citizen_id
                self._town_focus_selected_detail = {
                    "kind": "citizen",
                    "citizen_id": citizen_id,
                    "display_name": str((frame_citizen or {}).get("display_name") or (frame_citizen or {}).get("name") or citizen_id),
                    "activity": str((frame_citizen or {}).get("activity_id") or (frame_citizen or {}).get("action") or "local_activity"),
                    "next_label": str(nxt.get("label") or "next scheduled task"),
                    "next_reason": str(nxt.get("reason") or "schedule memory"),
                }
                self._create_or_update_town_focus_detail_panel(self._last_citizen_frame)
                self._create_or_update_town_focus_follow_marker()
            try:
                marker = self._marker_nodes.get(citizen_id)
                if marker is not None:
                    marker.setPythonTag("holoutopia_selected", True)
            except Exception:
                pass
            return True
        except Exception as exc:
            self.error = f"citizen-panel:{exc.__class__.__name__}:{exc}"
            return False

    def select_building(self, building_id: str) -> bool:
        """Open a read-only building inspector for the requested building/lot id."""
        building_id = str(building_id or "").strip()
        if not building_id:
            return False
        try:
            from holoutopia_building_inspector import inspect_building

            payload = inspect_building(
                self.holoverse_root,
                building_id,
                clock=self.current_clock(),
                danger_state=bool(self._danger_state),
            )
            if isinstance(payload, dict):
                payload["runtime_context"] = {"holoverse_root": str(self.holoverse_root)}
            if self.panel_manager is None:
                self._install_panel_manager()
            if self.panel_manager is None:
                return False
            self.panel_manager.show_building_panel(payload)
            self._inspector_focus_active = True
            record = payload.get("building") if isinstance(payload.get("building"), dict) else {}
            self.selected_building_id = str(record.get("id") or building_id)
            self._create_or_update_building_selection_marker(record)
            self._create_or_update_building_site_card(record, payload)
            return True
        except Exception as exc:
            self.error = f"building-panel:{exc.__class__.__name__}:{exc}"
            return False

    def get_selected_focus_point(self) -> dict[str, Any] | None:
        """Return the current selected building/citizen point in render coordinates.

        The standalone launcher uses this to make the F key feel like a normal
        game focus command without giving the camera ownership of city data.
        """
        try:
            from panda3d.core import Point3

            render = getattr(self.app, "render", None)
            if render is None:
                return None
            if self.selected_building_id:
                records = self._building_records_for_selection()
                record = records.get(self.selected_building_id)
                if not isinstance(record, dict):
                    # Some inspectors normalize ids, so allow a forgiving scan.
                    for candidate in records.values():
                        if isinstance(candidate, dict) and str(candidate.get("id") or "") == self.selected_building_id:
                            record = candidate
                            break
                if isinstance(record, dict):
                    pos = record.get("world_position") if isinstance(record.get("world_position"), dict) else {}
                    massing = record.get("massing") if isinstance(record.get("massing"), dict) else {}
                    x = float(pos.get("x", 0.0))
                    y = float(pos.get("y", 0.0))
                    h = max(10.0, min(96.0, float(massing.get("height_units", 24.0) or 24.0)))
                    local_point = Point3(x, y, h + 12.0)
                    if self.city_root is not None:
                        point = render.getRelativePoint(self.city_root, local_point)
                    else:
                        point = local_point
                    return {
                        "kind": "building",
                        "id": str(record.get("id") or self.selected_building_id),
                        "label": str(record.get("display_name") or record.get("name") or "Selected Building"),
                        "point": (float(point.getX()), float(point.getY()), float(point.getZ())),
                    }
            if self.selected_citizen_id:
                marker = self._marker_nodes.get(self.selected_citizen_id)
                if marker is not None:
                    point = marker.getPos(render)
                    label = self.selected_citizen_id
                    try:
                        citizen = self._last_visible_citizens.get(self.selected_citizen_id, {}) if isinstance(self._last_visible_citizens, dict) else {}
                        label = str(citizen.get("display_name") or citizen.get("name") or label)
                    except Exception:
                        pass
                    return {
                        "kind": "citizen",
                        "id": self.selected_citizen_id,
                        "label": label,
                        "point": (float(point.getX()), float(point.getY()), float(point.getZ()) + 7.0),
                    }
        except Exception as exc:
            self.error = f"focus-point:{exc.__class__.__name__}:{exc}"
        return None


    def first_person_active(self) -> bool:
        """Return True when the player is walking inside an isolated town."""
        return bool(self._first_person_active and self._town_focus_active and self.selected_town_id)

    def toggle_first_person_walk_mode(self) -> bool:
        if self.first_person_active():
            return self.exit_town_first_person()
        return self.enter_town_first_person()

    def _first_person_memory_for_town(self, town_id: str) -> dict[str, Any]:
        memory = self._first_person_player_memory.get(str(town_id or ""))
        return dict(memory) if isinstance(memory, dict) else {}

    def _first_person_visible_bounds_for_town(self, town_id: str) -> dict[str, float]:
        """Return tighter focused-town bounds for ground-level walking.

        Town Focus camera framing uses a useful mid-height pivot, but first-person
        mode needs the actual lower bound so the player does not spawn above the
        town like an overhead debug camera.
        """
        try:
            render = getattr(self.app, "render", None)
            if render is None or self.city_root is None:
                return {}
            town_id = str(town_id or "")
            if not town_id:
                return {}
            xs: list[float] = []
            ys: list[float] = []
            zs: list[float] = []
            for root in (self.city_root, self.neighborhood_root):
                if root is None:
                    continue
                for node in root.findAllMatches("**"):
                    try:
                        if node.isHidden() or not node.hasPythonTag("holoutopia_town_root"):
                            continue
                        if str(node.getPythonTag("holoutopia_town_id") or "") != town_id:
                            continue
                        bounds = node.getTightBounds(render)
                        if not bounds or len(bounds) != 2 or bounds[0] is None or bounds[1] is None:
                            continue
                        lo, hi = bounds
                        xs.extend([float(lo.getX()), float(hi.getX())])
                        ys.extend([float(lo.getY()), float(hi.getY())])
                        zs.extend([float(lo.getZ()), float(hi.getZ())])
                    except Exception:
                        continue
            if not xs or not ys:
                return {}
            min_x, max_x = min(xs), max(xs)
            min_y, max_y = min(ys), max(ys)
            min_z, max_z = (min(zs), max(zs)) if zs else (0.0, 36.0)
            # Trim a little empty guide/pad margin, but keep enough room to walk
            # the service lanes around the focused town.
            width = max(80.0, max_x - min_x)
            depth = max(80.0, max_y - min_y)
            pad_x = min(18.0, width * 0.045)
            pad_y = min(18.0, depth * 0.045)
            return {
                "min_x": float(min_x + pad_x),
                "max_x": float(max_x - pad_x),
                "min_y": float(min_y + pad_y),
                "max_y": float(max_y - pad_y),
                "min_z": float(min_z),
                "max_z": float(max_z),
                "center_x": float((min_x + max_x) * 0.5),
                "center_y": float((min_y + max_y) * 0.5),
                "width": float(width),
                "depth": float(depth),
            }
        except Exception:
            return {}

    def get_first_person_start_state(self) -> dict[str, Any]:
        """Return render-space spawn/pivot data for the current isolated town."""
        town_id = str(self.selected_town_id or self._town_focus_last_town_id or "")
        towns = self._town_records_for_selection()
        town = towns.get(town_id, {"town_id": town_id, "display_name": town_id})
        target_data = self._town_focus_camera_target_from_visible_root(town_id) if town_id else None
        if target_data is None and isinstance(town, dict):
            target_data = self._town_camera_target_from_record(town, z=7.0)
        if target_data is None:
            target_data = (0.0, 0.0, 8.0, 260.0, 220.0)
        x, y, z, width, depth = target_data
        visible_bounds = self._first_person_visible_bounds_for_town(town_id)
        if visible_bounds:
            min_x = float(visible_bounds.get("min_x", float(x) - float(width) * 0.5))
            max_x = float(visible_bounds.get("max_x", float(x) + float(width) * 0.5))
            min_y = float(visible_bounds.get("min_y", float(y) - float(depth) * 0.5))
            max_y = float(visible_bounds.get("max_y", float(y) + float(depth) * 0.5))
            ground_z = float(visible_bounds.get("min_z", 0.0))
            width = max(80.0, float(visible_bounds.get("width", max_x - min_x)))
            depth = max(80.0, float(visible_bounds.get("depth", max_y - min_y)))
            x = float(visible_bounds.get("center_x", (min_x + max_x) * 0.5))
            y = float(visible_bounds.get("center_y", (min_y + max_y) * 0.5))
        else:
            radius_x = max(90.0, float(width) * 0.58)
            radius_y = max(80.0, float(depth) * 0.58)
            min_x, max_x = float(x) - radius_x, float(x) + radius_x
            min_y, max_y = float(y) - radius_y, float(y) + radius_y
            ground_z = 0.0
        eye_z = max(6.2, min(10.0, float(ground_z) + 6.6))
        memory = self._first_person_memory_for_town(town_id)
        pos = memory.get("pos") if isinstance(memory.get("pos"), (list, tuple)) else None
        hpr = memory.get("hpr") if isinstance(memory.get("hpr"), (list, tuple)) else None
        use_memory = False
        if pos and len(pos) >= 3:
            px0, py0, pz0 = float(pos[0]), float(pos[1]), float(pos[2])
            # Pass 79 could save an overhead camera position.  Keep memory only
            # when it is inside the focused town and near human eye height.
            if min_x <= px0 <= max_x and min_y <= py0 <= max_y and abs(pz0 - eye_z) <= 9.0:
                px, py, pz = px0, py0, eye_z
                use_memory = True
            else:
                px = float(x)
                py = float(min_y + min(34.0, max(16.0, float(depth) * 0.10)))
                pz = eye_z
        else:
            # Spawn on the near/south service-road side of the selected town, looking inward.
            px = float(x)
            py = float(min_y + min(34.0, max(16.0, float(depth) * 0.10)))
            pz = eye_z
        import math as _math
        if use_memory and hpr and len(hpr) >= 2:
            heading = float(hpr[0])
            pitch = float(hpr[1])
        else:
            heading = _math.degrees(_math.atan2(float(x) - float(px), float(y) - float(py)))
            pitch = -4.5
        walk_pad_x = min(12.0, max(4.0, float(width) * 0.025))
        walk_pad_y = min(12.0, max(4.0, float(depth) * 0.025))
        return {
            "town_id": town_id,
            "display_name": str((town or {}).get("display_name") or town_id.replace("_", " ").title()),
            "pos": (float(px), float(py), float(pz)),
            "hpr": (float(heading), max(-48.0, min(36.0, float(pitch))), 0.0),
            "center": (float(x), float(y), float(eye_z)),
            "bounds": {
                "min_x": float(min_x + walk_pad_x),
                "max_x": float(max_x - walk_pad_x),
                "min_y": float(min_y + walk_pad_y),
                "max_y": float(max_y - walk_pad_y),
                "floor_z": float(eye_z),
                "eye_z": float(eye_z),
            },
            "fov": 60.0,
        }

    def enter_town_first_person(self) -> bool:
        """Switch runtime state to walkable first-person inspection inside Town Focus."""
        if not self._town_focus_active or not self.selected_town_id:
            self._first_person_last_interaction = "Enter Town Focus first, then press Enter/P for first-person."
            self._create_or_update_first_person_prompt()
            return False
        self._first_person_active = True
        self._town_focus_follow_citizen_id = ""
        self._town_focus_detail_cache_key = ""
        self._first_person_last_interaction = "Walk mode active. Aim at a highlighted local target and press E."
        # First-person keeps the center view clear; inspectors can still open on interaction.
        self._clear_town_focus_panel()
        self._clear_town_focus_detail_panel()
        self._clear_tutorial_panel()
        self._set_first_person_overlay_readability(True)
        self._create_or_update_first_person_prompt()
        self._save_town_focus_state(force=True, reason="enter_first_person")
        try:
            town = self._town_records_for_selection().get(str(self.selected_town_id), {})
            self._set_app_title(f"HOLOUTOPIA // FIRST PERSON: {str(town.get('display_name') or self.selected_town_id)} // E INTERACT // ESC RETURN")
        except Exception:
            pass
        return True

    def exit_town_first_person(self) -> bool:
        """Return to Town Focus tilt-shift view without losing local sim state."""
        if not self._first_person_active:
            return False
        self._first_person_active = False
        self._first_person_last_interaction = "Returned to Town Focus view; local NPC memory kept."
        self._clear_first_person_prompt()
        self._set_first_person_overlay_readability(False)
        try:
            town = self._town_records_for_selection().get(str(self.selected_town_id), {})
            if isinstance(town, dict) and town:
                self._focus_camera_on_town(town)
        except Exception:
            pass
        self._create_or_update_town_focus_panel(self._last_citizen_frame)
        self._create_or_update_town_focus_detail_panel(self._last_citizen_frame)
        self._create_or_update_tutorial_panel(mode="focus")
        try:
            town = self._town_records_for_selection().get(str(self.selected_town_id), {})
            self._set_app_title(f"HOLOUTOPIA // TOWN FOCUS: {str(town.get('display_name') or self.selected_town_id)} // LOCAL NPC FLOW ACTIVE // ESC/BACKSPACE RETURN")
        except Exception:
            pass
        self._save_town_focus_state(force=True, reason="exit_first_person")
        return True

    def update_first_person_player_state(self, pos: Any = None, hpr: Any = None) -> None:
        """Persist only the lightweight per-town first-person camera/player state."""
        town_id = str(self.selected_town_id or self._town_focus_last_town_id or "")
        if not town_id:
            return
        try:
            if pos is None:
                camera = getattr(self.app, "camera", None) or getattr(self.app, "cam", None)
                render = getattr(self.app, "render", None)
                pos = camera.getPos(render) if camera is not None and render is not None else None
            if hpr is None:
                camera = getattr(self.app, "camera", None) or getattr(self.app, "cam", None)
                hpr = camera.getHpr() if camera is not None else None
            if pos is None:
                return
            px, py, pz = float(pos[0]), float(pos[1]), float(pos[2])
            if hpr is not None:
                hh, hp, hr = float(hpr[0]), float(hpr[1]), float(hpr[2])
            else:
                hh, hp, hr = 0.0, 0.0, 0.0
            self._first_person_player_memory[town_id] = {
                "town_id": town_id,
                "pos": (px, py, pz),
                "hpr": (hh, hp, hr),
                "clock": self.current_clock(),
                "day_id": self.current_day_id(),
                "mode": "town_focus_first_person",
            }
        except Exception:
            return

    def first_person_bounds(self) -> dict[str, float]:
        state = self.get_first_person_start_state()
        bounds = state.get("bounds") if isinstance(state.get("bounds"), dict) else {}
        return {str(k): float(v) for k, v in bounds.items() if isinstance(v, (int, float))}

    def interact_first_person(self) -> bool:
        """Interact from the crosshair using the existing Town Focus selection stack."""
        if not self.first_person_active():
            return False
        pointer = (0.0, 0.0)
        if self._try_select_town_focus_activity_from_camera(pointer):
            selected = self._town_focus_selected_detail if isinstance(self._town_focus_selected_detail, dict) else {}
            self._first_person_last_interaction = f"Selected {str(selected.get('kind') or 'local object')}: {str(selected.get('label') or selected.get('display_name') or selected.get('next_label') or 'local activity')[:48]}"
        else:
            cid = self._first_person_best_citizen_id(pointer=pointer)
            if cid and self.select_citizen(cid):
                self._first_person_last_interaction = "Citizen inspector opened from first-person."
            else:
                building_id = self._best_building_at_pointer(pointer)
                if building_id and self.select_building(building_id):
                    self._first_person_last_interaction = "Building inspector opened from first-person."
                elif self._try_select_citizen_from_camera(pointer):
                    self._first_person_last_interaction = "Citizen inspector opened from first-person."
                else:
                    self._first_person_last_interaction = "Nothing close enough at crosshair. Move closer or aim at a marker/person."
                    self._create_or_update_first_person_prompt()
                    return False
        self._create_or_update_first_person_prompt()
        self._create_or_update_tutorial_panel(mode="first_person")
        self._save_town_focus_state(reason="first_person_interact")
        return True

    def _first_person_target_hint(self) -> str:
        """Return a non-mutating crosshair hint for first-person mode."""
        if not self.first_person_active():
            return ""
        pointer = (0.0, 0.0)
        try:
            snapshot = self._last_town_focus_life_snapshot if isinstance(self._last_town_focus_life_snapshot, dict) else {}
            best_label = ""
            best_score = 9999.0
            for event in snapshot.get("events", []) if isinstance(snapshot.get("events"), list) else []:
                if not isinstance(event, dict):
                    continue
                scored = self._score_screen_point(_safe_float(event.get("x"), 0.0), _safe_float(event.get("y"), 0.0), 14.0, pointer=pointer)
                if scored is None:
                    continue
                dist, depth = scored
                if dist <= 0.20:
                    score = dist * 100.0 + depth * 0.001
                    if score < best_score:
                        best_score = score
                        best_label = f"event: {str(event.get('label') or 'local event')[:32]}"
            for cluster in snapshot.get("clusters", []) if isinstance(snapshot.get("clusters"), list) else []:
                if not isinstance(cluster, dict):
                    continue
                scored = self._score_screen_point(_safe_float(cluster.get("x"), 0.0), _safe_float(cluster.get("y"), 0.0), 11.0, pointer=pointer)
                if scored is None:
                    continue
                dist, depth = scored
                if dist <= 0.18:
                    score = dist * 100.0 + depth * 0.001
                    if score < best_score:
                        best_score = score
                        best_label = f"activity: {str(cluster.get('label') or cluster.get('activity') or 'local cluster')[:30]}"
            cid = self._first_person_best_citizen_id(pointer=pointer)
            if cid:
                citizen = self._last_citizen_frame.get("citizens", {}).get(cid, {}) if isinstance(self._last_citizen_frame, dict) and isinstance(self._last_citizen_frame.get("citizens"), dict) else {}
                label = str(citizen.get("display_name") or citizen.get("name") or cid)[:30]
                best_label = f"citizen: {label}" if not best_label else best_label
            building_id = self._best_building_at_pointer(pointer)
            if building_id and not best_label:
                rec = self._building_records_for_selection().get(building_id, {})
                best_label = f"building: {str(rec.get('display_name') or building_id)[:30]}"
            return best_label or "open space"
        except Exception:
            return "open space"

    def _first_person_best_citizen_id(self, *, pointer: tuple[float, float] = (0.0, 0.0)) -> str:
        try:
            from panda3d.core import Point2
            camera = getattr(self.app, "camera", None) or getattr(self.app, "cam", None)
            cam_lens = getattr(self.app, "camLens", None)
            render = getattr(self.app, "render", None)
            if camera is None or cam_lens is None or render is None:
                return ""
            pointer_x, pointer_y = pointer
            best_id = ""
            best_score = 9999.0
            cpos = camera.getPos(render)
            for cid, node in list(self._marker_nodes.items()):
                try:
                    if node.isHidden():
                        continue
                    npos = node.getPos(render)
                    distance = (npos - cpos).length()
                    if distance > 150.0:
                        continue
                    p3 = camera.getRelativePoint(render, npos)
                    if float(p3.getY()) < 1.0:
                        continue
                    p2 = Point2()
                    if not cam_lens.project(p3, p2):
                        continue
                    sx = float(p2.getX()) - pointer_x
                    sy = float(p2.getY()) - pointer_y
                    screen_dist = (sx * sx + sy * sy) ** 0.5
                    if screen_dist > 0.34:
                        continue
                    score = screen_dist * 100.0 + distance * 0.015
                    if score < best_score:
                        best_score = score
                        best_id = str(cid)
                except Exception:
                    continue
            return best_id
        except Exception:
            return ""

    def _create_or_update_first_person_prompt(self) -> None:
        if not self._first_person_active:
            self._clear_first_person_prompt()
            return
        try:
            from direct.gui.DirectGui import DirectFrame, DirectLabel
            from panda3d.core import TextNode

            aspect2d = getattr(self.app, "aspect2d", None)
            if aspect2d is None:
                aspect2d = getattr(__import__("builtins"), "aspect2d", None)
            if aspect2d is None:
                return
            if self._first_person_prompt_root is None:
                panel = DirectFrame(
                    parent=aspect2d,
                    frameSize=(-0.49, 0.49, -0.075, 0.075),
                    frameColor=(0.004, 0.010, 0.020, 0.72),
                    pos=(0.0, 0.0, -0.54),
                    sortOrder=151,
                )
                panel.setTransparency(True)
                label = DirectLabel(
                    parent=panel,
                    text="",
                    text_align=TextNode.ACenter,
                    text_fg=(0.90, 1.0, 1.0, 0.95),
                    text_scale=0.024,
                    text_pos=(0.0, 0.018),
                    frameColor=(0, 0, 0, 0),
                )
                crosshair = DirectLabel(
                    parent=aspect2d,
                    text="+",
                    pos=(0.0, 0.0, 0.0),
                    scale=0.052,
                    text_fg=(0.84, 1.0, 1.0, 0.78),
                    frameColor=(0, 0, 0, 0),
                    sortOrder=152,
                )
                panel.setPythonTag("holoutopia_first_person_prompt_label", label)
                panel.setPythonTag("holoutopia_first_person_crosshair", crosshair)
                self._first_person_prompt_root = panel
            label = self._first_person_prompt_root.getPythonTag("holoutopia_first_person_prompt_label")
            if label is not None:
                town = self._town_records_for_selection().get(str(self.selected_town_id), {})
                town_name = str(town.get("display_name") or self.selected_town_id or "Town")[:34]
                line = str(self._first_person_last_interaction or "Aim at a citizen/building/event and press E.")[:88]
                hint = str(self._first_person_target_hint() or "open space")[:48]
                label["text"] = f"FIRST PERSON // {town_name}   |   E interact   WASD walk   RMB look   Shift jog   ESC return\nAIM: {hint}   //   {line}"
        except Exception as exc:
            self.error = f"first-person-prompt:{exc.__class__.__name__}:{exc}"

    def _set_first_person_overlay_readability(self, active: bool) -> None:
        """Hide overhead Town Focus labels while the player walks at eye level.

        The tilt-shift view needs big district/need labels.  In first-person they
        become billboard clutter in front of the camera, so we temporarily hide
        only those label nodes and restore them when returning to Town Focus.
        """
        try:
            if not active:
                for node in list(self._first_person_hidden_overlay_nodes):
                    try:
                        if node is not None and not node.isEmpty():
                            node.show()
                    except Exception:
                        pass
                self._first_person_hidden_overlay_nodes = []
                return
            if self._first_person_hidden_overlay_nodes:
                return
            roots = [self.city_root, self.neighborhood_root, self.town_focus_event_root, self.town_focus_activity_root]
            patterns = (
                "**/holoutopia_label",
                "**/holoutopia_neighborhood_label",
                "**/town_focus_consequence_label",
                "**/town_focus_health_report_label",
                "**/town_focus_need_beacon_label_*",
            )
            hidden = []
            for root in roots:
                if root is None:
                    continue
                for pattern in patterns:
                    try:
                        for node in root.findAllMatches(pattern):
                            if node.isHidden():
                                continue
                            node.hide()
                            hidden.append(node)
                    except Exception:
                        continue
            self._first_person_hidden_overlay_nodes = hidden[:96]
        except Exception:
            self._first_person_hidden_overlay_nodes = []

    def _clear_first_person_prompt(self) -> None:
        node = self._first_person_prompt_root
        self._first_person_prompt_root = None
        if node is not None:
            try:
                crosshair = node.getPythonTag("holoutopia_first_person_crosshair")
                if crosshair is not None:
                    crosshair.destroy()
            except Exception:
                pass
            try:
                node.destroy()
            except Exception:
                try:
                    node.removeNode()
                except Exception:
                    pass

    def town_focus_active(self) -> bool:
        """Return True when the simulation is isolated to one town/district."""
        return bool(self._town_focus_active and self.selected_town_id)

    def _town_records_for_selection(self) -> dict[str, dict[str, Any]]:
        """Derive town hit records from the current building highlight index."""
        records = self._building_records_for_selection()
        towns: dict[str, dict[str, Any]] = {}
        for record in records.values():
            if not isinstance(record, dict):
                continue
            tid = str(record.get("town_id") or "").strip()
            if not tid:
                continue
            pos = record.get("world_position") if isinstance(record.get("world_position"), dict) else {}
            try:
                x = float(pos.get("x"))
                y = float(pos.get("y"))
            except Exception:
                continue
            town = towns.setdefault(
                tid,
                {
                    "town_id": tid,
                    "display_name": str(record.get("town_display_name") or tid.replace("_", " ").title()),
                    "district_type": str(record.get("district_type") or ""),
                    "xs": [],
                    "ys": [],
                    "records": 0,
                },
            )
            town["xs"].append(x)
            town["ys"].append(y)
            town["records"] = int(town.get("records", 0)) + 1
        out: dict[str, dict[str, Any]] = {}
        for tid, town in towns.items():
            xs = list(town.get("xs") or [])
            ys = list(town.get("ys") or [])
            if not xs or not ys:
                continue
            min_x, max_x = min(xs), max(xs)
            min_y, max_y = min(ys), max(ys)
            # Pad the bounds so clicks on streets/open plaza inside a district still
            # count as selecting the town instead of requiring a precise building hit.
            pad = 96.0
            out[tid] = {
                "town_id": tid,
                "display_name": str(town.get("display_name") or tid),
                "district_type": str(town.get("district_type") or ""),
                "center": {"x": (min_x + max_x) * 0.5, "y": (min_y + max_y) * 0.5},
                "bounds": {"min_x": min_x - pad, "max_x": max_x + pad, "min_y": min_y - pad, "max_y": max_y + pad},
                "record_count": int(town.get("records", 0)),
            }
        return out

    def _best_town_at_pointer(self, pointer: tuple[float, float]) -> str:
        """Find the town/district nearest to the click/crosshair."""
        towns = self._town_records_for_selection()
        best_id = ""
        best_score = 9999.0
        for tid, town in towns.items():
            center = town.get("center") if isinstance(town.get("center"), dict) else {}
            try:
                x = float(center.get("x"))
                y = float(center.get("y"))
            except Exception:
                continue
            scored = self._score_screen_point(x, y, 32.0, pointer=pointer)
            if scored is None:
                continue
            screen_dist, depth = scored
            if screen_dist > 0.36:
                continue
            score = screen_dist * 100.0 + depth * 0.0012
            if score < best_score:
                best_score = score
                best_id = str(tid)
        return best_id

    def enter_town_focus(self, town_id: str, *, source_building_id: str = "") -> bool:
        """Isolate one district as the active autonomous Sims-style detail view."""
        town_id = str(town_id or "").strip()
        if not town_id:
            return False
        towns = self._town_records_for_selection()
        if town_id not in towns:
            return False
        self._save_camera_for_town_focus()
        self.selected_town_id = town_id
        self._town_focus_last_town_id = town_id
        self._town_focus_active = True
        self._last_town_focus_summary = {}
        self._last_town_focus_life_snapshot = {}
        self._town_focus_selected_detail = {}
        self._town_focus_follow_citizen_id = ""
        self._invalidate_town_focus_perf_cache("enter_focus")
        self._apply_town_focus_visibility()
        self._clear_city_overview_signals()
        self._clear_building_selection_visuals()
        self.selected_citizen_id = ""
        self._last_update = 0.0
        self._facade_pulse_cache_ready = False
        self._create_or_update_citizen_markers(force=True)
        self._focus_camera_on_town(towns[town_id])
        self._create_or_update_town_focus_panel(self._last_citizen_frame)
        self._create_or_update_town_focus_life_visuals(self._last_citizen_frame)
        self._create_or_update_tutorial_panel(mode="focus")
        self._save_town_focus_state(force=True, reason="enter_focus")
        self._set_app_title(f"HOLOUTOPIA // TOWN FOCUS: {towns[town_id].get('display_name', town_id)} // LOCAL NPC FLOW ACTIVE // ESC/BACKSPACE RETURN")
        return True

    def exit_town_focus(self) -> bool:
        """Return from isolated town simulation to the full city overview."""
        if not self._town_focus_active:
            return False
        if self._first_person_active:
            self.exit_town_first_person()
        self._town_focus_last_town_id = str(self.selected_town_id or self._town_focus_last_town_id or "")
        self._town_focus_active = False
        self.selected_town_id = ""
        self._save_town_focus_state(force=True, reason="exit_focus")
        self._last_town_focus_summary = {}
        self._last_town_focus_life_snapshot = {}
        self._town_focus_selected_detail = {}
        self._town_focus_follow_citizen_id = ""
        self._invalidate_town_focus_perf_cache("exit_focus")
        self._apply_town_focus_visibility()
        self._clear_town_focus_panel()
        self._clear_town_focus_detail_panel()
        self._clear_town_focus_life_visuals()
        self._clear_first_person_prompt()
        self._clear_building_selection_visuals()
        self.selected_citizen_id = ""
        self._last_update = 0.0
        self._facade_pulse_cache_ready = False
        if not self._focus_camera_on_city_overview():
            self._restore_camera_after_town_focus()
        self._create_or_update_citizen_markers(force=True)
        self._create_or_update_city_overview_signals(self._last_citizen_frame)
        self._set_app_title("HOLOUTOPIA // FULL CITY VIEW // CLICK A DISTRICT TO ENTER TOWN FOCUS")
        return True

    def _set_app_title(self, text: str) -> None:
        try:
            title = getattr(self.app, "title_text", None)
            if title is not None and hasattr(title, "setText"):
                title.setText(str(text))
        except Exception:
            pass

    def _save_camera_for_town_focus(self) -> None:
        if self._town_focus_saved_camera:
            return
        try:
            camera = getattr(self.app, "camera", None) or getattr(self.app, "cam", None)
            render = getattr(self.app, "render", None)
            lens = getattr(self.app, "camLens", None)
            if camera is None or render is None:
                return
            pos = camera.getPos(render)
            self._town_focus_saved_camera = {
                "pos": (float(pos.getX()), float(pos.getY()), float(pos.getZ())),
                "hpr": (float(camera.getH()), float(camera.getP()), float(camera.getR())),
                "fov": float(lens.getFov().getX()) if lens is not None else 58.0,
            }
        except Exception:
            self._town_focus_saved_camera = {}

    def _restore_camera_after_town_focus(self) -> None:
        saved = dict(self._town_focus_saved_camera or {})
        self._town_focus_saved_camera = {}
        if not saved:
            return
        try:
            camera = getattr(self.app, "camera", None) or getattr(self.app, "cam", None)
            render = getattr(self.app, "render", None)
            lens = getattr(self.app, "camLens", None)
            if camera is None or render is None:
                return
            pos = saved.get("pos") if isinstance(saved.get("pos"), (tuple, list)) else None
            hpr = saved.get("hpr") if isinstance(saved.get("hpr"), (tuple, list)) else None
            if pos and len(pos) >= 3:
                camera.setPos(render, float(pos[0]), float(pos[1]), float(pos[2]))
            if hpr and len(hpr) >= 3:
                camera.setHpr(float(hpr[0]), float(hpr[1]), float(hpr[2]))
            if lens is not None and "fov" in saved:
                lens.setFov(float(saved.get("fov") or 58.0))
            if hasattr(self.app, "_store_camera_hpr_from_node"):
                self.app._store_camera_hpr_from_node()
        except Exception:
            pass

    def _town_camera_target_from_record(self, record: dict[str, Any], *, z: float = 18.0) -> tuple[float, float, float, float, float] | None:
        """Return render-space camera target + local bounds size for a town/city record."""
        try:
            from panda3d.core import Point3

            render = getattr(self.app, "render", None)
            if render is None or self.city_root is None or not isinstance(record, dict):
                return None
            center = record.get("center") if isinstance(record.get("center"), dict) else {}
            bounds = record.get("bounds") if isinstance(record.get("bounds"), dict) else {}
            cx = float(center.get("x", 0.0))
            cy = float(center.get("y", 0.0))
            width = abs(float(bounds.get("max_x", cx)) - float(bounds.get("min_x", cx))) if bounds else 260.0
            depth = abs(float(bounds.get("max_y", cy)) - float(bounds.get("min_y", cy))) if bounds else 220.0
            local = Point3(cx, cy, float(z))
            world = render.getRelativePoint(self.city_root, local)
            return float(world.getX()), float(world.getY()), float(world.getZ()), float(width), float(depth)
        except Exception:
            return None

    def _town_focus_camera_target_from_visible_root(self, town_id: str) -> tuple[float, float, float, float, float] | None:
        """Return a tighter render-space camera target from the visible focused town root.

        The authored town bounds include empty service pads and wide district guide
        geometry.  Town Focus should pivot/framing around the actually visible
        isolated town, so the screenshot/gameplay view does not read as another
        full-city overview.
        """
        try:
            from panda3d.core import Point3

            render = getattr(self.app, "render", None)
            if render is None or self.city_root is None:
                return None
            town_id = str(town_id or "")
            if not town_id:
                return None
            candidates = []
            for root in (self.city_root, self.neighborhood_root):
                if root is None:
                    continue
                for node in root.findAllMatches("**"):
                    try:
                        if node.isHidden() or not node.hasPythonTag("holoutopia_town_root"):
                            continue
                        if str(node.getPythonTag("holoutopia_town_id") or "") == town_id:
                            candidates.append(node)
                    except Exception:
                        continue
            xs: list[float] = []
            ys: list[float] = []
            zs: list[float] = []
            for node in candidates:
                try:
                    bounds = node.getTightBounds(render)
                except Exception:
                    bounds = None
                if not bounds or len(bounds) != 2 or bounds[0] is None or bounds[1] is None:
                    continue
                lo, hi = bounds
                xs.extend([float(lo.getX()), float(hi.getX())])
                ys.extend([float(lo.getY()), float(hi.getY())])
                zs.extend([float(lo.getZ()), float(hi.getZ())])
            if not xs or not ys:
                return None
            min_x, max_x = min(xs), max(xs)
            min_y, max_y = min(ys), max(ys)
            min_z, max_z = (min(zs), max(zs)) if zs else (0.0, 36.0)
            width = max(180.0, max_x - min_x)
            depth = max(160.0, max_y - min_y)
            cx = (min_x + max_x) * 0.5
            cy = (min_y + max_y) * 0.5
            cz = max(14.0, min(72.0, min_z + (max_z - min_z) * 0.42))
            return cx, cy, cz, width, depth
        except Exception:
            return None

    def _city_camera_record_for_selection(self) -> dict[str, Any]:
        towns = self._town_records_for_selection()
        xs: list[float] = []
        ys: list[float] = []
        for town in towns.values():
            if not isinstance(town, dict):
                continue
            bounds = town.get("bounds") if isinstance(town.get("bounds"), dict) else {}
            center = town.get("center") if isinstance(town.get("center"), dict) else {}
            try:
                xs.extend([float(bounds.get("min_x", center.get("x", 0.0))), float(bounds.get("max_x", center.get("x", 0.0)))])
                ys.extend([float(bounds.get("min_y", center.get("y", 0.0))), float(bounds.get("max_y", center.get("y", 0.0)))])
            except Exception:
                continue
        if not xs or not ys:
            return {"center": {"x": 0.0, "y": 0.0}, "bounds": {"min_x": -640.0, "max_x": 640.0, "min_y": -540.0, "max_y": 540.0}}
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        pad = 120.0
        return {
            "center": {"x": (min_x + max_x) * 0.5, "y": (min_y + max_y) * 0.5},
            "bounds": {"min_x": min_x - pad, "max_x": max_x + pad, "min_y": min_y - pad, "max_y": max_y + pad},
        }

    def _focus_camera_on_city_overview(self) -> bool:
        """Center the full-city orbit camera on the city, not a random edge."""
        try:
            target_data = self._town_camera_target_from_record(self._city_camera_record_for_selection(), z=28.0)
            if target_data is None:
                return False
            x, y, z, width, depth = target_data
            radius = max(820.0, min(1640.0, max(width, depth) * 0.72))
            setter = getattr(self.app, "_set_camera_orbit_target", None)
            if callable(setter):
                setter(x, y, max(20.0, z + 10.0), distance=radius, yaw=40.0, pitch=-38.0, fov=42.0, label="city_overview")
                return True
            return False
        except Exception as exc:
            self.error = f"city-camera:{exc.__class__.__name__}:{exc}"
            return False

    def _focus_camera_on_town(self, town: dict[str, Any]) -> None:
        try:
            from panda3d.core import Vec3

            camera = getattr(self.app, "camera", None) or getattr(self.app, "cam", None)
            render = getattr(self.app, "render", None)
            lens = getattr(self.app, "camLens", None)
            if camera is None or render is None or self.city_root is None:
                return
            target_data = self._town_focus_camera_target_from_visible_root(str(town.get("town_id") or self.selected_town_id or ""))
            if target_data is None:
                target_data = self._town_camera_target_from_record(town, z=18.0)
            if target_data is None:
                return
            x, y, z, width, depth = target_data
            radius = max(680.0, min(900.0, max(width, depth) * 0.96))
            # Pivot-centered Town Focus: rotate/zoom around the isolated district center.
            setter = getattr(self.app, "_set_camera_orbit_target", None)
            if callable(setter):
                setter(x, y, max(16.0, z + 10.0), distance=radius, yaw=42.0, pitch=-54.0, fov=38.0, label=str(town.get("town_id") or "town_focus"))
                return
            target = Vec3(float(x), float(y), max(6.0, float(z) + 8.0))
            camera.setPos(render, target.getX() - radius * 0.54, target.getY() - radius * 0.62, target.getZ() + radius * 0.98)
            camera.lookAt(Vec3(target.getX(), target.getY(), target.getZ() + radius * 0.035))
            if lens is not None:
                lens.setFov(38)
                lens.setNearFar(1.0, 5000.0)
            if hasattr(self.app, "_store_camera_hpr_from_node"):
                self.app._store_camera_hpr_from_node()
        except Exception as exc:
            self.error = f"town-camera:{exc.__class__.__name__}:{exc}"

    def _apply_town_focus_visibility(self) -> None:
        """Hide all non-focused district roots when in Town Focus Mode."""
        try:
            focus_id = str(self.selected_town_id or "") if self._town_focus_active else ""
            for root in (self.city_root, self.neighborhood_root):
                if root is None:
                    continue
                matches = root.findAllMatches("**")
                for node in matches:
                    try:
                        if not node.hasPythonTag("holoutopia_town_root") and not node.hasPythonTag("holoutopia_neighborhood_city_root"):
                            continue
                        tid = str(node.getPythonTag("holoutopia_town_id") or "")
                        if focus_id and tid and tid != focus_id:
                            node.hide()
                        else:
                            node.show()
                    except Exception:
                        continue
            # In focus mode, the global watch guides and full-city activity glyphs are
            # less important than the local town panel and visible citizens. Hide
            # the big central overlay unless the Core itself is the focused town.
            for attr in ("watch_root", "focus_root", "activity_root"):
                node = getattr(self, attr, None)
                if node is not None:
                    try:
                        node.hide() if focus_id else node.show()
                    except Exception:
                        pass
            core = getattr(self, "central_core_overlay_root", None)
            if core is not None:
                try:
                    if focus_id and focus_id != "central_core_civic_ring":
                        core.hide()
                    else:
                        core.show()
                except Exception:
                    pass
            self._apply_town_focus_background_guide_visibility(focus_id)
        except Exception as exc:
            self.error = f"town-visibility:{exc.__class__.__name__}:{exc}"

    def _is_town_focus_background_guide_node(self, name: str) -> bool:
        name = str(name or "").lower()
        return (
            name.startswith("grid_x_")
            or name.startswith("grid_y_")
            or "_ring_" in name
            or "_spine_" in name
            or "courier_route" in name
            or name.startswith("district_anchor_")
        )

    def _apply_town_focus_background_guide_visibility(self, focus_id: str) -> None:
        """Hide broad grid/guide lines in Town Focus, restore them in overview.

        This keeps the isolated town readable as a game space instead of showing
        huge editor-like district outlines that make the view feel like the full
        city is still present.
        """
        try:
            focus_id = str(focus_id or "")
            roots = [self.city_root, self.neighborhood_root]
            for root in roots:
                if root is None:
                    continue
                for node in root.findAllMatches("**"):
                    try:
                        if not node.hasPythonTag("holoutopia_focus_hidden_guide") and not self._is_town_focus_background_guide_node(node.getName()):
                            continue
                        if focus_id and self._is_town_focus_background_guide_node(node.getName()):
                            node.setPythonTag("holoutopia_focus_hidden_guide", True)
                            node.hide()
                        elif not focus_id and node.hasPythonTag("holoutopia_focus_hidden_guide"):
                            node.clearPythonTag("holoutopia_focus_hidden_guide")
                            node.show()
                    except Exception:
                        continue
        except Exception:
            pass

    def _clear_city_overview_signals(self) -> None:
        for attr in ("city_overview_signal_root", "city_overview_signal_panel_root"):
            node = getattr(self, attr, None)
            setattr(self, attr, None)
            if node is not None:
                try:
                    node.removeNode()
                except Exception:
                    pass

    def _city_overview_latest_report_for_town(self, town_id: str) -> dict[str, Any]:
        """Return the newest runtime-only health/consequence memory for overview badges."""
        town_id = str(town_id or "")
        if not town_id:
            return {}
        report = self._town_focus_latest_health_report(town_id)
        if report:
            return dict(report)
        # Fallback to a current-day direct key before falling back to consequences.
        direct = self._town_focus_health_report_memory.get(f"{town_id}:{self.current_day_id()}")
        if isinstance(direct, dict):
            return dict(direct)
        consequence = self._town_focus_consequence_memory.get(town_id)
        if isinstance(consequence, dict):
            score = self._clamp_town_focus_metric(
                _safe_float(consequence.get("supply_percent"), 70.0) * 0.16
                + _safe_float(consequence.get("safety_percent"), 72.0) * 0.22
                + _safe_float(consequence.get("morale_percent"), 70.0) * 0.18
                + _safe_float(consequence.get("productivity_percent"), 68.0) * 0.15
                + (100.0 - _safe_float(consequence.get("pressure_percent"), 30.0)) * 0.20
                + (100.0 - _safe_float(consequence.get("glitch_risk_percent"), 12.0)) * 0.09
            )
            out = dict(consequence)
            out["score"] = int(score)
            out["grade"] = self._town_focus_health_grade(int(score))
            out["trend"] = "watching"
            return out
        return {}

    def _city_overview_signal_for_town(self, town_id: str, town: dict[str, Any]) -> dict[str, Any]:
        town_id = str(town_id or "")
        display = str(town.get("display_name") or town_id.replace("_", " ").title())
        center = town.get("center") if isinstance(town.get("center"), dict) else {}
        bounds = town.get("bounds") if isinstance(town.get("bounds"), dict) else {}
        report = self._city_overview_latest_report_for_town(town_id)
        has_memory = bool(report)
        score = self._clamp_town_focus_metric(report.get("score") if has_memory else 74)
        pressure = self._clamp_town_focus_metric(report.get("pressure_percent") if has_memory else 18)
        glitch = self._clamp_town_focus_metric(report.get("glitch_risk_percent") if has_memory else 10)
        status = str(report.get("status") or ("unscanned" if not has_memory else "stable")).lower()
        need = str(report.get("dominant_need") or ("scan town" if not has_memory else "routine watch"))[:34]
        grade = str(report.get("grade") or ("?" if not has_memory else self._town_focus_health_grade(score)))[:2]
        trend = str(report.get("trend") or ("unscanned" if not has_memory else "steady"))[:24]
        event_count = int(report.get("event_count") or report.get("active_event_count") or 0)
        attention_score = max(100 - score, pressure, int(glitch * 0.92), event_count * 10)
        if not has_memory:
            state = "unscanned"
        elif score <= 44 or pressure >= 72 or glitch >= 65 or status == "critical":
            state = "critical"
        elif score <= 58 or pressure >= 52 or status == "strained":
            state = "strained"
        elif score <= 70 or pressure >= 34 or glitch >= 34 or event_count:
            state = "watch"
        else:
            state = "stable"
        min_x = _safe_float(bounds.get("min_x"), _safe_float(center.get("x"), 0.0) - 120.0)
        max_x = _safe_float(bounds.get("max_x"), _safe_float(center.get("x"), 0.0) + 120.0)
        min_y = _safe_float(bounds.get("min_y"), _safe_float(center.get("y"), 0.0) - 95.0)
        max_y = _safe_float(bounds.get("max_y"), _safe_float(center.get("y"), 0.0) + 95.0)
        return {
            "town_id": town_id,
            "display_name": display,
            "district_type": str(town.get("district_type") or ""),
            "x": _safe_float(center.get("x"), (min_x + max_x) * 0.5),
            "y": _safe_float(center.get("y"), (min_y + max_y) * 0.5),
            "bounds": {"min_x": min_x, "max_x": max_x, "min_y": min_y, "max_y": max_y},
            "state": state,
            "score": int(score),
            "grade": grade,
            "pressure_percent": int(pressure),
            "glitch_risk_percent": int(glitch),
            "dominant_need": need,
            "status": status,
            "trend": trend,
            "attention_score": int(self._clamp_town_focus_metric(attention_score)),
            "event_count": int(event_count),
            "has_memory": has_memory,
            "clock": self.current_clock(),
            "day_id": self.current_day_id(),
            "line": f"{display}: {state} // {grade} {score}% // {need}",
        }

    def _city_overview_signal_color(self, signal: dict[str, Any]) -> tuple[float, float, float, float]:
        state = str(signal.get("state") or "stable").lower()
        if state == "critical":
            return (1.0, 0.24, 0.22, 0.92)
        if state == "strained":
            return (1.0, 0.70, 0.18, 0.88)
        if state == "watch":
            return (0.34, 0.92, 1.0, 0.86)
        if state == "unscanned":
            return (0.58, 0.66, 0.78, 0.62)
        return (0.38, 1.0, 0.66, 0.78)

    def _create_or_update_city_overview_signals(self, frame: dict[str, Any] | None = None) -> None:
        """Low-cost full-city attention badges; no full local sim required in overview."""
        layers = self.config.get("render_layers", {}) if isinstance(self.config.get("render_layers"), dict) else {}
        if self._town_focus_active or self.city_root is None or not bool(layers.get("city_overview_signals", True)):
            self._clear_city_overview_signals()
            return
        try:
            from panda3d.core import LineSegs, TextNode
            self._clear_city_overview_signals()
            towns = self._town_records_for_selection()
            if not towns:
                return
            root = self.city_root.attachNewNode("holoutopia_city_overview_attention_signals")
            root.setLightOff(True)
            root.setTransparency(True)
            self.city_overview_signal_root = root
            signals: dict[str, dict[str, Any]] = {}
            critical_count = 0
            watch_count = 0
            for idx, (town_id, town) in enumerate(sorted(towns.items())):
                if not isinstance(town, dict):
                    continue
                signal = self._city_overview_signal_for_town(town_id, town)
                signals[str(town_id)] = dict(signal)
                state = str(signal.get("state") or "stable")
                if state in {"critical", "strained"}:
                    critical_count += 1
                elif state == "watch":
                    watch_count += 1
                c = self._city_overview_signal_color(signal)
                x = _safe_float(signal.get("x"), 0.0)
                y = _safe_float(signal.get("y"), 0.0)
                attention = max(0.0, min(1.0, _safe_float(signal.get("attention_score"), 0.0) / 100.0))
                height = 52.0 + 48.0 * attention
                radius = 11.0 + 9.5 * attention
                z = 58.0
                seg = LineSegs(f"city_overview_signal_{idx:02d}")
                seg.setThickness(2.35 if state in {"critical", "strained"} else 1.75)
                seg.setColor(c[0], c[1], c[2], c[3])
                # a small attention mast with a diamond top and a pressure tick
                seg.moveTo(0.0, 0.0, z)
                seg.drawTo(0.0, 0.0, z + height)
                for k in range(5):
                    a = math.tau * k / 4.0 + math.pi * 0.25
                    px = math.cos(a) * radius
                    py = math.sin(a) * radius
                    if k == 0:
                        seg.moveTo(px, py, z + height)
                    else:
                        seg.drawTo(px, py, z + height)
                pressure_ratio = max(0.0, min(1.0, _safe_float(signal.get("pressure_percent"), 0.0) / 100.0))
                seg.moveTo(-radius, -radius - 4.0, z + 5.0)
                seg.drawTo(-radius + radius * 2.0 * pressure_ratio, -radius - 4.0, z + 5.0)
                node = root.attachNewNode(seg.create())
                node.setPos(x, y, 0.0)
                node.setLightOff(True)
                node.setPythonTag("holoutopia_city_overview_signal", dict(signal))
                label = TextNode(f"city_overview_signal_label_{idx:02d}")
                label.setAlign(TextNode.ACenter)
                grade = str(signal.get("grade") or "?")
                state_label = str(signal.get("state") or "stable").upper()
                need = str(signal.get("dominant_need") or "routine watch")[:18]
                if state == "unscanned":
                    text_line = f"{str(signal.get('display_name') or town_id)[:18]}\nUNSCANNED"
                else:
                    text_line = f"{str(signal.get('display_name') or town_id)[:18]}\n{state_label} {grade} {int(signal.get('score') or 0)}% // {need}"
                label.setText(text_line)
                label.setTextColor(c[0], c[1], c[2], 0.93)
                label.setCardColor(0.004, 0.010, 0.018, 0.58)
                label.setCardAsMargin(0.28, 0.28, 0.13, 0.13)
                label_np = root.attachNewNode(label)
                label_np.setPos(x, y, z + height + 9.0)
                label_np.setScale(5.10 if state != "unscanned" else 4.35)
                label_np.setLightOff(True)
                label_np.setHpr(0.0, -62.0, 0.0)
            self._city_overview_signal_memory = {k: dict(v) for k, v in signals.items()}
            self._city_overview_last_signal_clock = self.current_clock()
            root.setPythonTag("holoutopia_city_overview_signals", list(signals.values()))
            # Compact command banner: visible in the overview, but does not require simulating every town.
            if signals:
                # Small 2D overview readout: keeps the overview actionable even when the in-world
                # masts are viewed from a wide cinematic angle.  It is removed during Town Focus.
                try:
                    from direct.gui.DirectGui import DirectFrame, DirectLabel
                    from panda3d.core import TextNode as _GuiTextNode
                    aspect2d = getattr(self.app, "aspect2d", None)
                    if aspect2d is None:
                        aspect2d = getattr(__import__("builtins"), "aspect2d", None)
                    if aspect2d is not None:
                        aspect = self._current_aspect_ratio()
                        sorted_signals = sorted(signals.values(), key=lambda s: int(s.get("attention_score") or 0), reverse=True)
                        panel = DirectFrame(
                            parent=aspect2d,
                            frameSize=(-0.54, 0.54, -0.235, 0.235),
                            frameColor=(0.004, 0.012, 0.024, 0.88),
                            pos=(-max(0.74, aspect - 0.60), 0.0, 0.67),
                            sortOrder=147,
                        )
                        panel.setTransparency(True)
                        rows = [f"CITY MAP // DISTRICT SIGNALS   urgent {critical_count} / watch {watch_count}"]
                        for sig in sorted_signals[:5]:
                            if not isinstance(sig, dict):
                                continue
                            state = str(sig.get('state') or 'stable').upper()[:8]
                            need = str(sig.get('dominant_need') or 'routine watch')[:18]
                            rows.append(
                                f"{state:<8} {str(sig.get('grade') or '?'):<2} {int(sig.get('score') or 0):02d}%  "
                                f"{str(sig.get('display_name') or '')[:19]}  // {need}"
                            )
                        rows.append("Click any district signal or building to enter Town Focus")
                        label = DirectLabel(
                            parent=panel,
                            text="\n".join(rows),
                            text_align=_GuiTextNode.ALeft,
                            text_fg=(0.84, 1.0, 1.0, 0.96),
                            text_scale=0.0245,
                            text_pos=(-0.50, 0.168),
                            frameColor=(0, 0, 0, 0),
                        )
                        accent = DirectFrame(parent=panel, frameSize=(-0.54, 0.54, 0.193, 0.235), frameColor=(0.28, 1.0, 0.90, 0.23))
                        panel.setPythonTag("holoutopia_city_overview_signal_panel_label", label)
                        panel.setPythonTag("holoutopia_city_overview_signal_panel_accent", accent)
                        self.city_overview_signal_panel_root = panel
                except Exception:
                    pass
                summary_color = (0.76, 1.0, 1.0, 0.88) if critical_count == 0 else (1.0, 0.62, 0.28, 0.94)
                top = TextNode("city_overview_signal_summary")
                top.setAlign(TextNode.ACenter)
                top.setText(f"CITY SIGNALS // {len(signals)} DISTRICTS // urgent {critical_count} / watch {watch_count}\nClick a district signal or building to enter Town Focus")
                top.setTextColor(*summary_color)
                top.setCardColor(0.004, 0.010, 0.018, 0.62)
                top.setCardAsMargin(0.44, 0.44, 0.16, 0.16)
                # Place near the atlas center/top edge so it reads as overview HUD inside the world layer.
                xs = [_safe_float(s.get("x"), 0.0) for s in signals.values()]
                ys = [_safe_float(s.get("y"), 0.0) for s in signals.values()]
                node = root.attachNewNode(top)
                node.setPos((min(xs) + max(xs)) * 0.5, min(ys) - 150.0, 132.0)
                node.setScale(4.15)
                node.setLightOff(True)
                node.setHpr(0.0, -62.0, 0.0)
            self._create_or_update_tutorial_panel(mode="overview")
            self._save_town_focus_state(reason="city_overview_signals")
        except Exception as exc:
            self.error = f"city-overview-signals:{exc.__class__.__name__}:{exc}"

    def toggle_tutorial_panel(self) -> bool:
        """Show/hide the compact player guide without touching sim state."""
        self._tutorial_panel_visible = not bool(self._tutorial_panel_visible)
        self._tutorial_panel_cache_key = ""
        self._tutorial_panel_last_text = ""
        if not self._tutorial_panel_visible:
            self._clear_tutorial_panel()
            return False
        self._create_or_update_tutorial_panel(mode="focus" if self._town_focus_active else "overview")
        return True

    def _clear_tutorial_panel(self) -> None:
        node = self.tutorial_panel_root
        self.tutorial_panel_root = None
        if node is not None:
            try:
                node.destroy()
            except Exception:
                try:
                    node.removeNode()
                except Exception:
                    pass

    def _tutorial_step_state(self) -> dict[str, Any]:
        """Return a tiny, game-facing tutorial state derived from current play context."""
        selected = self._town_focus_selected_detail if isinstance(self._town_focus_selected_detail, dict) else {}
        kind = str(selected.get("kind") or "")
        event_id = str(selected.get("event_id") or "")
        order = selected.get("player_order") if isinstance(selected.get("player_order"), dict) else {}
        if not self._town_focus_active:
            return {
                "mode": "overview",
                "title": "CITY GUIDE",
                "step": "Click a district signal or building to enter Town Focus.",
                "controls": "RMB/Arrows orbit city center  |  Wheel zoom  |  WASD pans pivot  |  F1 hides guide",
                "goal": "Pick the town that needs attention, then inspect local events and citizens.",
            }
        if self._first_person_active:
            return {
                "mode": "first_person",
                "title": "FIRST PERSON WALK",
                "step": "Walk the isolated town and aim at people, buildings, routes, or event diamonds.",
                "controls": "WASD walk  |  RMB look  |  Shift jog  |  E interact  |  ESC returns to Town Focus",
                "goal": str(self._first_person_last_interaction or "Interact with citizens and town events up close.")[:88],
            }
        if kind == "event" and event_id and not order:
            return {
                "mode": "focus_event",
                "title": "EVENT SELECTED",
                "step": "Choose a watcher response: 1 Help, 2 Repair, 3 Calm, 4 Supplies.",
                "controls": "Orders lower pressure over time; ESC/Backspace returns to city overview.",
                "goal": str(selected.get("action_hint") or "Pick the response that matches the town need.")[:88],
            }
        if kind == "event" and event_id and order:
            return {
                "mode": "focus_order",
                "title": "ORDER ACTIVE",
                "step": "Watch pressure, outcome state, and town health update as city time advances.",
                "controls": "Click another diamond to respond, or click a route/citizen to follow local life.",
                "goal": f"Active order: {str(order.get('label') or 'Watcher nudge')[:44]}",
            }
        if kind == "flow":
            return {
                "mode": "focus_follow",
                "title": "ROUTE FOLLOW",
                "step": "Camera is following this citizen's next destination path.",
                "controls": "Click event diamonds for playable orders; click buildings/citizens for inspectors.",
                "goal": f"Next stop: {str(selected.get('next_label') or 'scheduled task')[:54]}",
            }
        if kind == "citizen":
            return {
                "mode": "focus_citizen",
                "title": "CITIZEN FOLLOW",
                "step": "Follow mode tracks the selected citizen without changing their schedule.",
                "controls": "Click a route, event, cluster, or building to switch context.",
                "goal": f"Why: {str(selected.get('next_reason') or 'schedule memory')[:62]}",
            }
        if kind == "cluster":
            return {
                "mode": "focus_cluster",
                "title": "ACTIVITY CLUSTER",
                "step": "This shows what locals are doing here. Find diamonds for urgent choices.",
                "controls": "Click routes/citizens to follow people; click events for 1-4 watcher orders.",
                "goal": str(selected.get("reason") or "Watch local autonomous activity.")[:88],
            }
        if self.selected_building_id:
            return {
                "mode": "focus_building",
                "title": "BUILDING SELECTED",
                "step": "Read the building card, then inspect local events around it.",
                "controls": "X/ESC closes inspectors first; ESC/Backspace exits Town Focus after panels close.",
                "goal": "Buildings are context; event diamonds are the current playable town problems.",
            }
        return {
            "mode": "focus",
            "title": "TOWN FOCUS GUIDE",
            "step": "Click a diamond, route trail, activity cluster, citizen, or building.",
            "controls": "RMB/Arrows orbit  |  Wheel zoom  |  Enter/P walk town  |  1-4 event orders  |  F1 hides",
            "goal": "This isolated town keeps NPC memory while the city overview stays cheap.",
        }

    def _create_or_update_tutorial_panel(self, *, mode: str = "auto") -> None:
        """Compact tutorial/controls banner for the autonomous town gameplay loop."""
        if self._first_person_active:
            self._clear_tutorial_panel()
            return
        if not self._tutorial_panel_visible:
            self._clear_tutorial_panel()
            return
        try:
            from direct.gui.DirectGui import DirectFrame, DirectLabel
            from panda3d.core import TextNode

            aspect2d = getattr(self.app, "aspect2d", None)
            if aspect2d is None:
                aspect2d = getattr(__import__("builtins"), "aspect2d", None)
            if aspect2d is None:
                return
            state = self._tutorial_step_state()
            title = str(state.get("title") or "GUIDE")
            text = "\n".join([
                f"{title} // {str(state.get('step') or '')[:104]}",
                str(state.get("goal") or "")[:108],
                str(state.get("controls") or "")[:112],
            ]).strip()
            cache_key = "|".join([
                str(state.get("mode") or mode),
                str(self.selected_town_id or "overview"),
                str(self.selected_building_id or ""),
                str((self._town_focus_selected_detail if isinstance(self._town_focus_selected_detail, dict) else {}).get("kind") or ""),
                str((self._town_focus_selected_detail if isinstance(self._town_focus_selected_detail, dict) else {}).get("event_id") or ""),
                self._town_focus_state_revision_key(),
            ])
            if self.tutorial_panel_root is None:
                panel = DirectFrame(
                    parent=aspect2d,
                    frameSize=(-0.82, 0.82, -0.112, 0.112),
                    frameColor=(0.004, 0.010, 0.020, 0.82),
                    pos=(0.0, 0.0, -0.775),
                    sortOrder=149,
                )
                panel.setTransparency(True)
                label = DirectLabel(
                    parent=panel,
                    text="",
                    text_align=TextNode.ALeft,
                    text_fg=(0.88, 1.0, 1.0, 0.94),
                    text_scale=0.026,
                    text_pos=(-0.78, 0.045),
                    frameColor=(0, 0, 0, 0),
                )
                accent = DirectFrame(parent=panel, frameSize=(-0.82, 0.82, 0.086, 0.112), frameColor=(0.22, 0.95, 1.0, 0.22))
                panel.setPythonTag("holoutopia_tutorial_label", label)
                panel.setPythonTag("holoutopia_tutorial_accent", accent)
                self.tutorial_panel_root = panel
            label = self.tutorial_panel_root.getPythonTag("holoutopia_tutorial_label")
            if label is not None and (cache_key != self._tutorial_panel_cache_key or text != self._tutorial_panel_last_text):
                label["text"] = text
                self._tutorial_panel_cache_key = cache_key
                self._tutorial_panel_last_text = text
        except Exception as exc:
            self.error = f"tutorial-panel:{exc.__class__.__name__}:{exc}"

    def _clear_town_focus_panel(self) -> None:
        node = self.town_focus_summary_root
        self.town_focus_summary_root = None
        if node is not None:
            try:
                node.destroy()
            except Exception:
                try:
                    node.removeNode()
                except Exception:
                    pass

    def _clear_town_focus_detail_panel(self) -> None:
        node = self.town_focus_detail_root
        self.town_focus_detail_root = None
        if node is not None:
            try:
                node.destroy()
            except Exception:
                try:
                    node.removeNode()
                except Exception:
                    pass

    def _clear_town_focus_life_visuals(self) -> None:
        """Remove local life-sim-only markers without touching citizens or city roots."""
        for attr in ("town_focus_activity_root", "town_focus_flow_root", "town_focus_event_root", "town_focus_follow_root"):
            node = getattr(self, attr, None)
            setattr(self, attr, None)
            if node is not None:
                try:
                    node.removeNode()
                except Exception:
                    try:
                        node.destroy()
                    except Exception:
                        pass

    def _local_town_citizens(self, frame: dict[str, Any] | None = None) -> dict[str, dict[str, Any]]:
        frame = frame if isinstance(frame, dict) else {}
        town_id = str(self.selected_town_id or "")
        if not town_id:
            return {}
        citizens = frame.get("citizens") if isinstance(frame.get("citizens"), dict) else {}
        # Use rendered citizens first so the local view and panels stay in sync;
        # fall back to the simulated frame for summary math before the first render tick.
        visible = self._last_visible_citizens if isinstance(self._last_visible_citizens, dict) else {}
        merged = {**citizens, **visible}
        return {
            str(cid): data
            for cid, data in merged.items()
            if isinstance(data, dict) and str(data.get("town_id") or "") == town_id
        }

    def _citizen_next_destination(self, cid: str, citizen: dict[str, Any]) -> dict[str, Any]:
        """Resolve where a citizen should go next from authored schedules/current visit state."""
        cid = str(cid or "")
        node_id = ""
        reason = ""
        try:
            visit = citizen.get("civic_visit") if isinstance(citizen.get("civic_visit"), dict) else {}
            if visit and str(citizen.get("activity_id") or "") == "district_errand":
                # Visitors should head back into their authored schedule after the errand window.
                reason = "resume schedule after errand"
            schedules = (self._inputs or {}).get("citizen_schedules", {}).get("schedules", {})
            schedule = schedules.get(cid) if isinstance(schedules, dict) else None
            blocks = schedule.get("blocks") if isinstance(schedule, dict) else []
            idx = int(citizen.get("schedule_index", 0) or 0)
            if isinstance(blocks, list) and blocks:
                next_block = blocks[min(len(blocks) - 1, max(0, idx + 1))]
                if isinstance(next_block, dict):
                    node_id = str(next_block.get("target") or "")
                    reason = reason or str(next_block.get("activity") or next_block.get("action") or "next scheduled task")
            if not node_id:
                node_id = str(citizen.get("target_node") or citizen.get("resolved_node") or "")
            xy = self._render_xy_for_node_id(node_id) if node_id else None
            label = node_id.replace("_node", "").replace("_", " ").title() if node_id else "Local route"
            return {"node_id": node_id, "label": label, "reason": reason or "next local task", "xy": xy}
        except Exception:
            return {"node_id": node_id, "label": node_id or "Local route", "reason": reason or "next task", "xy": None}


    def _town_focus_selected_event_id(self) -> str:
        selected = self._town_focus_selected_detail if isinstance(self._town_focus_selected_detail, dict) else {}
        if str(selected.get("kind") or "") != "event":
            return ""
        return str(selected.get("event_id") or "")

    def _apply_town_focus_order_dispatch_help(self) -> bool:
        return self._apply_town_focus_player_order("dispatch_help", "Dispatch Help", "A local response crew has been routed to the selected situation.", pressure_delta=-0.18, tint=(0.42, 1.0, 0.94, 0.96))

    def _apply_town_focus_order_boost_repair(self) -> bool:
        return self._apply_town_focus_player_order("boost_repair", "Boost Repair", "Repair priority has been raised for the selected event cluster.", pressure_delta=-0.15, tint=(0.80, 1.0, 0.30, 0.96))

    def _apply_town_focus_order_calm_civilians(self) -> bool:
        return self._apply_town_focus_player_order("calm_civilians", "Calm Civilians", "Public guidance has been sent to nearby civilians.", pressure_delta=-0.22, tint=(0.52, 1.0, 0.72, 0.96))

    def _apply_town_focus_order_fund_supplies(self) -> bool:
        return self._apply_town_focus_player_order("fund_supplies", "Fund Supplies", "Supply priority has been funded for the selected town event.", pressure_delta=-0.12, tint=(1.0, 0.82, 0.30, 0.96))

    def _apply_town_focus_player_order(self, order_id: str, label: str, description: str, *, pressure_delta: float, tint: tuple[float, float, float, float]) -> bool:
        """Apply a watcher nudge to the selected local event without touching schedules."""
        if not self._town_focus_active or not self.selected_town_id:
            return False
        event_id = self._town_focus_selected_event_id()
        if not event_id:
            self._town_focus_last_order_feedback = "Select an event diamond first, then press 1-4 to influence it."
            self._create_or_update_town_focus_detail_panel(self._last_citizen_frame)
            return False
        order = {
            "order_id": str(order_id),
            "label": str(label),
            "description": str(description),
            "town_id": str(self.selected_town_id),
            "event_id": str(event_id),
            "clock": self.current_clock(),
            "day_id": self.current_day_id(),
            "pressure_delta": float(pressure_delta),
            "applied_minute": int(self._town_focus_clock_minutes(self.current_clock())),
            "resolution_target_minutes": 120,
            "tint": tuple(float(v) for v in tint[:4]),
        }
        self._town_focus_player_orders[event_id] = order
        self._town_focus_event_outcomes[event_id] = {
            "event_id": str(event_id),
            "town_id": str(self.selected_town_id),
            "state": "responding",
            "label": "Response started",
            "progress": 0.08,
            "pressure_percent": 100,
            "order_id": str(order_id),
            "order_label": str(label),
            "clock": self.current_clock(),
            "day_id": self.current_day_id(),
        }
        self._town_focus_last_order_feedback = f"{label}: {description}"
        if isinstance(self._town_focus_selected_detail, dict):
            self._town_focus_selected_detail["player_order"] = dict(order)
            self._town_focus_selected_detail["influence_state"] = "nudged"
        self._last_town_focus_life_snapshot = {}
        self._invalidate_town_focus_perf_cache("watcher_order")
        self._update_town_focus_consequence_memory(reason="watcher_order")
        self._save_town_focus_state(force=True, reason="watcher_order")
        self._clear_town_focus_life_visuals()
        self._create_or_update_town_focus_life_visuals(self._last_citizen_frame)
        self._create_or_update_town_focus_panel(self._last_citizen_frame)
        self._create_or_update_town_focus_detail_panel(self._last_citizen_frame)
        return True

    def _town_focus_order_for_event(self, event_id: str) -> dict[str, Any]:
        event_id = str(event_id or "")
        order = self._town_focus_player_orders.get(event_id)
        if isinstance(order, dict):
            return dict(order)
        # Event ids include the 90-minute clock bucket. A watcher order should
        # continue to influence the same local situation slot as time advances,
        # even when a new bucket generates the next deterministic event id.
        parts = event_id.split(":")
        town_id = parts[1] if len(parts) >= 5 else str(self.selected_town_id or "")
        slot = parts[3] if len(parts) >= 5 else ""
        label_slug = parts[4] if len(parts) >= 5 else ""
        candidates = [o for o in self._town_focus_player_orders.values() if isinstance(o, dict) and str(o.get("town_id") or "") == town_id]
        candidates.sort(key=lambda o: str(o.get("clock") or ""), reverse=True)
        for candidate in candidates:
            c_parts = str(candidate.get("event_id") or "").split(":")
            c_slot = c_parts[3] if len(c_parts) >= 5 else ""
            c_label = c_parts[4] if len(c_parts) >= 5 else ""
            if (slot and c_slot == slot) or (label_slug and c_label == label_slug):
                return dict(candidate)
        return {}

    def _town_focus_outcome_for_event(self, event_id: str) -> dict[str, Any]:
        outcome = self._town_focus_event_outcomes.get(str(event_id or ""))
        return dict(outcome) if isinstance(outcome, dict) else {}

    def _town_focus_elapsed_minutes_since_order(self, order: dict[str, Any], clock: str) -> int:
        current = self._town_focus_clock_minutes(clock)
        try:
            start = int(order.get("applied_minute"))
        except Exception:
            start = self._town_focus_clock_minutes(str(order.get("clock") or clock))
        elapsed = current - start
        if elapsed < 0:
            elapsed += 24 * 60
        return max(0, min(24 * 60, elapsed))

    def _town_focus_base_event_pressure(self, event: dict[str, Any]) -> float:
        severity = str(event.get("severity") or "normal").lower()
        base = {"urgent": 0.78, "busy": 0.58, "normal": 0.38, "calm": 0.22}.get(severity, 0.38)
        count = max(0, int(event.get("count") or 0))
        flow_count = max(0, int(event.get("flow_count") or 0))
        base += min(0.14, count * 0.018)
        base += min(0.10, flow_count * 0.010)
        return max(0.05, min(0.96, base))

    def _town_focus_pressure_severity(self, pressure: float) -> str:
        if pressure >= 0.70:
            return "urgent"
        if pressure >= 0.48:
            return "busy"
        if pressure >= 0.26:
            return "normal"
        return "calm"

    def _town_focus_event_resolution(self, event: dict[str, Any], order: dict[str, Any], clock: str) -> dict[str, Any]:
        event_id = str(event.get("event_id") or "")
        base_pressure = self._town_focus_base_event_pressure(event)
        if not order:
            outcome = self._town_focus_outcome_for_event(event_id)
            state = str(outcome.get("state") or "watching")
            label = str(outcome.get("label") or "No watcher order")
            result = {
                "event_id": event_id,
                "town_id": str(event.get("town_id") or self.selected_town_id or ""),
                "state": state,
                "label": label,
                "line": "Awaiting watcher input" if base_pressure >= 0.48 else "Autonomous routine is holding",
                "progress": float(outcome.get("progress") or 0.0),
                "pressure": base_pressure,
                "pressure_percent": int(round(base_pressure * 100.0)),
                "elapsed_minutes": int(outcome.get("elapsed_minutes") or 0),
                "clock": clock,
                "day_id": self.current_day_id(),
            }
            if event_id:
                self._town_focus_event_outcomes[event_id] = dict(result)
            return result

        elapsed = self._town_focus_elapsed_minutes_since_order(order, clock)
        target = max(30.0, float(order.get("resolution_target_minutes") or 120.0))
        progress = max(0.08, min(1.0, elapsed / target))
        order_strength = min(0.46, abs(float(order.get("pressure_delta") or -0.14)) * (1.20 + progress * 1.80))
        pressure = max(0.05, min(0.96, base_pressure - order_strength * progress))
        if progress >= 0.92 or pressure <= 0.22:
            state = "stabilized"
            label = "Stabilized"
            line = f"{str(order.get('label') or 'Watcher order')} has stabilized this event"
        elif progress >= 0.45 or pressure < base_pressure - 0.08:
            state = "improving"
            label = "Improving"
            line = f"{str(order.get('label') or 'Watcher order')} is reducing pressure"
        else:
            state = "responding"
            label = "Responding"
            line = f"{str(order.get('label') or 'Watcher order')} is en route"
        result = {
            "event_id": event_id,
            "town_id": str(event.get("town_id") or order.get("town_id") or self.selected_town_id or ""),
            "state": state,
            "label": label,
            "line": line,
            "progress": round(progress, 3),
            "pressure": round(pressure, 3),
            "pressure_percent": int(round(pressure * 100.0)),
            "base_pressure_percent": int(round(base_pressure * 100.0)),
            "elapsed_minutes": int(elapsed),
            "order_id": str(order.get("order_id") or ""),
            "order_label": str(order.get("label") or "Watcher order"),
            "clock": clock,
            "day_id": self.current_day_id(),
        }
        if event_id:
            self._town_focus_event_outcomes[event_id] = dict(result)
        return result

    def _clamp_town_focus_metric(self, value: float, low: int = 0, high: int = 100) -> int:
        return int(max(int(low), min(int(high), round(float(value)))))

    def _town_focus_metric_state(self, metric_id: str, value: int) -> str:
        metric_id = str(metric_id or "").lower()
        value = self._clamp_town_focus_metric(value)
        if metric_id in {"pressure", "glitch_risk"}:
            if value >= 72:
                return "critical"
            if value >= 52:
                return "strained"
            if value >= 34:
                return "watch"
            return "calm"
        if value <= 34:
            return "critical"
        if value <= 52:
            return "strained"
        if value <= 66:
            return "watch"
        return "healthy"

    def _town_focus_need_marker_color(self, marker: dict[str, Any]) -> tuple[float, float, float, float]:
        metric_id = str(marker.get("metric_id") or "").lower() if isinstance(marker, dict) else ""
        state = str(marker.get("state") or "watch").lower() if isinstance(marker, dict) else "watch"
        if state == "critical":
            return (1.0, 0.22, 0.20, 0.92)
        if state == "strained":
            return (1.0, 0.74, 0.22, 0.88)
        if metric_id == "glitch_risk":
            return (0.90, 0.38, 1.0, 0.88)
        if metric_id == "safety":
            return (0.36, 1.0, 0.84, 0.86)
        if metric_id == "morale":
            return (0.60, 1.0, 0.42, 0.86)
        if metric_id == "supply":
            return (1.0, 0.86, 0.36, 0.86)
        if metric_id == "productivity":
            return (0.46, 0.86, 1.0, 0.86)
        if metric_id == "pressure":
            return (1.0, 0.48, 0.34, 0.88)
        return (0.62, 1.0, 1.0, 0.84)

    def _town_focus_need_markers_from_metrics(self, *, pressure: int, supply: int, safety: int, morale: int, productivity: int, glitch_risk: int, dominant_need: str) -> list[dict[str, Any]]:
        """Convert town consequence metrics into a few readable in-world need beacons."""
        raw_rows = [
            ("pressure", "Pressure", int(pressure), int(pressure), "response load"),
            ("glitch_risk", "Glitch", int(glitch_risk), int(glitch_risk), "containment watch"),
            ("safety", "Safety", int(safety), 100 - int(safety), "protect civilians"),
            ("supply", "Supply", int(supply), 100 - int(supply), "fund supplies"),
            ("morale", "Morale", int(morale), 100 - int(morale), "calm civilians"),
            ("productivity", "Productivity", int(productivity), 100 - int(productivity), "boost repair"),
        ]
        dominant_key = str(dominant_need or "").lower().replace(" ", "_")
        markers: list[dict[str, Any]] = []
        for metric_id, label, value, risk_score, caption in raw_rows:
            value = self._clamp_town_focus_metric(value)
            risk_score = self._clamp_town_focus_metric(risk_score)
            state = self._town_focus_metric_state(metric_id, value)
            priority_bonus = 16 if metric_id in dominant_key or label.lower() in dominant_key else 0
            if dominant_key == "glitch_containment" and metric_id == "glitch_risk":
                priority_bonus = 24
            if dominant_key == "security_response" and metric_id in {"safety", "pressure"}:
                priority_bonus = 18
            markers.append({
                "metric_id": metric_id,
                "label": label,
                "value": int(value),
                "risk_score": int(risk_score),
                "state": state,
                "caption": caption,
                "priority_score": int(risk_score + priority_bonus),
            })
        markers.sort(key=lambda row: (-int(row.get("priority_score") or 0), str(row.get("label") or "")))
        return markers[:4]

    def _town_focus_active_town_outcomes(self, town_id: str) -> list[dict[str, Any]]:
        rows = [o for o in self._town_focus_event_outcomes.values() if isinstance(o, dict) and str(o.get("town_id") or "") == str(town_id or "")]
        rows.sort(key=lambda o: (str(o.get("day_id") or ""), str(o.get("clock") or "")), reverse=True)
        return [dict(row) for row in rows[:12]]

    def _town_focus_consequence_for_snapshot(self, events: list[dict[str, Any]], local: dict[str, dict[str, Any]], flows: list[dict[str, Any]], clock: str) -> dict[str, Any]:
        """Derive town-level consequences from events/orders without editing authored schedules."""
        town_id = str(self.selected_town_id or self._town_focus_last_town_id or "")
        if not town_id:
            return {}
        towns = self._town_records_for_selection()
        town = towns.get(town_id, {"display_name": town_id.replace("_", " ").title(), "district_type": ""})
        district = str(town.get("district_type") or "")
        event_rows = [e for e in events if isinstance(e, dict)]
        active_pressures = [int(e.get("pressure_percent") or 0) for e in event_rows]
        peak_pressure = max(active_pressures or [0])
        avg_pressure = (sum(active_pressures) / max(1, len(active_pressures))) if active_pressures else 0.0
        town_orders = [o for o in self._town_focus_player_orders.values() if isinstance(o, dict) and str(o.get("town_id") or "") == town_id]
        town_outcomes = self._town_focus_active_town_outcomes(town_id)
        urgent_count = len([e for e in event_rows if str(e.get("severity") or "") == "urgent"])
        busy_count = len([e for e in event_rows if str(e.get("severity") or "") == "busy"])
        stabilized_count = len([o for o in town_outcomes if str(o.get("state") or "") == "stabilized"])
        improving_count = len([o for o in town_outcomes if str(o.get("state") or "") in {"responding", "improving"}])
        recent_order_count = min(8, len(town_orders))
        pressure = self._clamp_town_focus_metric(peak_pressure * 0.62 + avg_pressure * 0.38 + urgent_count * 6 + busy_count * 3 - stabilized_count * 5 - recent_order_count * 2)
        order_ids = {str(o.get("order_id") or "") for o in town_orders}
        district_key = (district + " " + town_id).lower()
        supply_base = 72 + (8 if any(key in district_key for key in ("market", "harbor", "industrial")) else 0)
        safety_base = 76 + (8 if "security" in district_key else 0)
        morale_base = 70 + (6 if any(key in district_key for key in ("residential", "civic", "market")) else 0)
        productivity_base = 68 + (8 if any(key in district_key for key in ("industrial", "archive", "core")) else 0)
        glitch_base = 10 + (22 if any(key in district_key for key in ("glitch", "quarantine")) else 0)
        supply = self._clamp_town_focus_metric(supply_base - pressure * 0.22 + stabilized_count * 3 + (8 if "fund_supplies" in order_ids else 0))
        safety = self._clamp_town_focus_metric(safety_base - pressure * 0.34 - urgent_count * 5 + (7 if "dispatch_help" in order_ids else 0))
        morale = self._clamp_town_focus_metric(morale_base - pressure * 0.30 + stabilized_count * 3 + (9 if "calm_civilians" in order_ids else 0))
        productivity = self._clamp_town_focus_metric(productivity_base - pressure * 0.24 + improving_count * 2 + (9 if "boost_repair" in order_ids else 0))
        glitch_risk = self._clamp_town_focus_metric(glitch_base + pressure * 0.22 + urgent_count * 5 - stabilized_count * 4 - (4 if "dispatch_help" in order_ids else 0))
        if pressure >= 72 or glitch_risk >= 62:
            status = "critical"
        elif pressure >= 52:
            status = "strained"
        elif improving_count or pressure >= 34:
            status = "responding"
        elif stabilized_count:
            status = "stabilizing"
        else:
            status = "stable"
        needs = {
            "supply": supply,
            "safety": safety,
            "morale": morale,
            "productivity": productivity,
            "glitch risk": 100 - glitch_risk,
        }
        dominant_need = min(needs.items(), key=lambda item: item[1])[0]
        if glitch_risk >= 55:
            dominant_need = "glitch containment"
        elif pressure >= 62 and safety < 62:
            dominant_need = "security response"
        mood = "calm" if morale >= 74 and pressure < 34 else "focused" if morale >= 58 else "uneasy" if morale >= 42 else "stressed"
        need_markers = self._town_focus_need_markers_from_metrics(
            pressure=pressure,
            supply=supply,
            safety=safety,
            morale=morale,
            productivity=productivity,
            glitch_risk=glitch_risk,
            dominant_need=dominant_need,
        )
        metric_snapshot = {
            "pressure": pressure,
            "supply": supply,
            "safety": safety,
            "morale": morale,
            "productivity": productivity,
            "glitch_risk": glitch_risk,
        }
        consequence = {
            "town_id": town_id,
            "display_name": str(town.get("display_name") or town_id.replace("_", " ").title()),
            "district_type": district,
            "clock": str(clock or self.current_clock()),
            "day_id": self.current_day_id(),
            "status": status,
            "mood": mood,
            "dominant_need": dominant_need,
            "pressure_percent": pressure,
            "supply_percent": supply,
            "safety_percent": safety,
            "morale_percent": morale,
            "productivity_percent": productivity,
            "glitch_risk_percent": glitch_risk,
            "active_event_count": len(event_rows),
            "active_order_count": len(town_orders),
            "stabilized_event_count": stabilized_count,
            "improving_event_count": improving_count,
            "visible_local_count": len(local),
            "flow_count": len(flows),
            "line": f"{status.title()} / {mood}; needs {dominant_need}",
            "metric_snapshot": metric_snapshot,
            "need_markers": need_markers,
            "need_marker_count": len(need_markers),
            "highest_risk": str(need_markers[0].get("label") or dominant_need) if need_markers else dominant_need,
            "policy": "runtime_consequence_only__authored_schedules_remain_read_only",
        }
        self._town_focus_consequence_memory[town_id] = dict(consequence)
        return consequence

    def _update_town_focus_consequence_memory(self, *, reason: str = "runtime") -> dict[str, Any]:
        snapshot = self._last_town_focus_life_snapshot if isinstance(self._last_town_focus_life_snapshot, dict) else {}
        if snapshot:
            consequence = snapshot.get("consequence") if isinstance(snapshot.get("consequence"), dict) else {}
            if consequence:
                self._town_focus_consequence_memory[str(consequence.get("town_id") or self.selected_town_id or self._town_focus_last_town_id)] = dict(consequence)
                return dict(consequence)
        town_id = str(self.selected_town_id or self._town_focus_last_town_id or "")
        if town_id and town_id in self._town_focus_consequence_memory:
            return dict(self._town_focus_consequence_memory[town_id])
        return {}

    def _town_focus_consequence_lines(self, limit: int = 3) -> list[str]:
        town_id = str(self.selected_town_id or self._town_focus_last_town_id or "")
        row = self._town_focus_consequence_memory.get(town_id)
        if not isinstance(row, dict):
            return []
        lines = [f"Town: {str(row.get('status') or 'stable').title()} / {str(row.get('mood') or 'calm')} // pressure {int(row.get('pressure_percent') or 0)}%"]
        lines.append(f"Need: {str(row.get('dominant_need') or 'routine watch')} // Safety {int(row.get('safety_percent') or 0)} Morale {int(row.get('morale_percent') or 0)}")
        lines.append(f"Supply {int(row.get('supply_percent') or 0)} Productivity {int(row.get('productivity_percent') or 0)} Glitch {int(row.get('glitch_risk_percent') or 0)}")
        markers = row.get("need_markers") if isinstance(row.get("need_markers"), list) else []
        if markers:
            beacon_bits = [f"{str(m.get('label') or 'Need')} {int(m.get('value') or 0)}" for m in markers[:3] if isinstance(m, dict)]
            if beacon_bits:
                lines.append("Beacons: " + " / ".join(beacon_bits))
        return lines[:max(0, int(limit))]

    def _town_focus_health_grade(self, score: int) -> str:
        score = self._clamp_town_focus_metric(score)
        if score >= 92:
            return "S"
        if score >= 82:
            return "A"
        if score >= 70:
            return "B"
        if score >= 58:
            return "C"
        if score >= 44:
            return "D"
        return "E"

    def _town_focus_latest_health_report(self, town_id: str, *, exclude_day: str = "") -> dict[str, Any]:
        rows = []
        for row in self._town_focus_health_report_memory.values():
            if not isinstance(row, dict):
                continue
            if str(row.get("town_id") or "") != str(town_id or ""):
                continue
            if exclude_day and str(row.get("day_id") or "") == str(exclude_day):
                continue
            rows.append(dict(row))
        rows.sort(key=lambda r: (str(r.get("day_id") or ""), str(r.get("clock") or "")), reverse=True)
        return rows[0] if rows else {}

    def _town_focus_health_report_for_snapshot(self, consequence: dict[str, Any], events: list[dict[str, Any]], local: dict[str, dict[str, Any]], flows: list[dict[str, Any]], clock: str) -> dict[str, Any]:
        """Convert town consequence metrics into a compact daily health report."""
        if not isinstance(consequence, dict) or not consequence:
            return {}
        town_id = str(consequence.get("town_id") or self.selected_town_id or self._town_focus_last_town_id or "")
        if not town_id:
            return {}
        day_id = self.current_day_id()
        pressure = self._clamp_town_focus_metric(consequence.get("pressure_percent") or 0)
        supply = self._clamp_town_focus_metric(consequence.get("supply_percent") or 0)
        safety = self._clamp_town_focus_metric(consequence.get("safety_percent") or 0)
        morale = self._clamp_town_focus_metric(consequence.get("morale_percent") or 0)
        productivity = self._clamp_town_focus_metric(consequence.get("productivity_percent") or 0)
        glitch_risk = self._clamp_town_focus_metric(consequence.get("glitch_risk_percent") or 0)
        event_count = len([e for e in events if isinstance(e, dict)])
        order_count = len([o for o in self._town_focus_player_orders.values() if isinstance(o, dict) and str(o.get("town_id") or "") == town_id])
        visible_local_count = len(local)
        flow_count = len(flows)
        score = self._clamp_town_focus_metric(
            supply * 0.17
            + safety * 0.22
            + morale * 0.19
            + productivity * 0.15
            + (100 - pressure) * 0.19
            + (100 - glitch_risk) * 0.08
            + min(5, order_count) * 0.75
        )
        grade = self._town_focus_health_grade(score)
        previous = self._town_focus_latest_health_report(town_id, exclude_day=day_id)
        previous_score = int(previous.get("score") or score) if previous else score
        delta = int(score - previous_score)
        if abs(delta) <= 2:
            trend = "steady"
        elif delta > 0:
            trend = "improving"
        else:
            trend = "declining"
        dominant_need = str(consequence.get("dominant_need") or "routine watch")
        if dominant_need == "supply":
            next_step = "Fund supplies or watch market/harbor flow."
        elif dominant_need in {"safety", "security response"}:
            next_step = "Dispatch help and inspect checkpoint routes."
        elif dominant_need == "morale":
            next_step = "Calm civilians near the busiest cluster."
        elif dominant_need == "productivity":
            next_step = "Boost repair and watch work-site routes."
        elif "glitch" in dominant_need:
            next_step = "Contain glitch risk before it spreads."
        else:
            next_step = "Keep watching local flows."
        report = {
            "town_id": town_id,
            "display_name": str(consequence.get("display_name") or town_id.replace("_", " ").title()),
            "day_id": day_id,
            "clock": str(clock or self.current_clock()),
            "score": int(score),
            "grade": grade,
            "trend": trend,
            "delta": int(delta),
            "status": str(consequence.get("status") or "stable"),
            "mood": str(consequence.get("mood") or "calm"),
            "dominant_need": dominant_need,
            "next_step": next_step,
            "event_count": int(event_count),
            "order_count": int(order_count),
            "visible_local_count": int(visible_local_count),
            "flow_count": int(flow_count),
            "pressure_percent": int(pressure),
            "supply_percent": int(supply),
            "safety_percent": int(safety),
            "morale_percent": int(morale),
            "productivity_percent": int(productivity),
            "glitch_risk_percent": int(glitch_risk),
            "line": f"Health {grade} {score}% / {trend}; {dominant_need}",
            "policy": "runtime_health_report_only__authored_schedules_remain_read_only",
        }
        self._town_focus_health_report_memory[f"{town_id}:{day_id}"] = dict(report)
        return report

    def _town_focus_health_report_lines(self, limit: int = 3) -> list[str]:
        town_id = str(self.selected_town_id or self._town_focus_last_town_id or "")
        if not town_id:
            return []
        rows = [dict(r) for r in self._town_focus_health_report_memory.values() if isinstance(r, dict) and str(r.get("town_id") or "") == town_id]
        rows.sort(key=lambda r: (str(r.get("day_id") or ""), str(r.get("clock") or "")), reverse=True)
        out = []
        for row in rows[:max(0, int(limit))]:
            out.append(f"Daily: {str(row.get('grade') or '?')} {int(row.get('score') or 0)}% {str(row.get('trend') or 'steady')} // {str(row.get('dominant_need') or 'routine watch')}")
        return out

    def _town_focus_outcome_lines(self, limit: int = 3) -> list[str]:
        town_id = str(self.selected_town_id or "")
        rows = [o for o in self._town_focus_event_outcomes.values() if isinstance(o, dict) and str(o.get("town_id") or "") == town_id]
        rows.sort(key=lambda o: (str(o.get("day_id") or ""), str(o.get("clock") or "")), reverse=True)
        lines = []
        for row in rows[:max(0, int(limit))]:
            lines.append(f"Outcome: {str(row.get('label') or 'Watching')} // pressure {int(row.get('pressure_percent') or 0)}%")
        return lines

    def _town_focus_order_lines(self, limit: int = 3) -> list[str]:
        town_id = str(self.selected_town_id or "")
        rows = [o for o in self._town_focus_player_orders.values() if isinstance(o, dict) and str(o.get("town_id") or "") == town_id]
        rows.sort(key=lambda o: str(o.get("clock") or ""), reverse=True)
        return [f"Order: {str(o.get('label') or 'Town nudge')} @ {str(o.get('clock') or '--:--')}" for o in rows[:max(0, int(limit))]]

    def _town_focus_clock_minutes(self, clock: str) -> int:
        try:
            raw = str(clock or self.current_clock()).strip()
            hh, mm = raw.split(":", 1)
            return (int(hh) % 24) * 60 + max(0, min(59, int(mm[:2])))
        except Exception:
            return 0

    def _town_focus_event_templates(self, town_id: str, district_type: str) -> list[dict[str, str]]:
        key = f"{town_id} {district_type}".lower()
        if "market" in key:
            return [
                {"label": "Market rush", "reason": "extra buyers are clustering around a supply window", "action": "watch crowd pressure near the stalls", "severity": "busy", "activity": "market_supply"},
                {"label": "Vendor restock", "reason": "a delivery crew is refilling public kiosks", "action": "follow the route trails to see who is waiting", "severity": "normal", "activity": "district_errand"},
            ]
        if "industrial" in key or "repair" in key:
            return [
                {"label": "Repair call", "reason": "a component swap is being staged by the work crew", "action": "inspect nearby workers and incoming parts", "severity": "urgent", "activity": "repair_work"},
                {"label": "Power calibration", "reason": "technicians are tuning a local energy relay", "action": "watch whether the flow trails resolve", "severity": "normal", "activity": "work_shift"},
            ]
        if "harbor" in key or "waterfront" in key:
            return [
                {"label": "Harbor delivery", "reason": "waterfront logistics are pulling visitors toward the docks", "action": "follow arrivals to the receiving point", "severity": "busy", "activity": "supply_delivery"},
                {"label": "Boardwalk break", "reason": "off-duty civilians are gathering near the waterfront", "action": "inspect the social cluster", "severity": "calm", "activity": "social_meal"},
            ]
        if "archive" in key or "research" in key:
            return [
                {"label": "Research gathering", "reason": "citizens are requesting memory-file access", "action": "inspect archive readers and next stops", "severity": "normal", "activity": "archive_research"},
                {"label": "Data review queue", "reason": "scholars are comparing citizen records", "action": "watch who leaves for civic follow-up", "severity": "busy", "activity": "personal_research"},
            ]
        if "security" in key or "checkpoint" in key:
            return [
                {"label": "Checkpoint delay", "reason": "security is holding a local clearance line", "action": "follow the delayed citizen route", "severity": "urgent", "activity": "security_check"},
                {"label": "Patrol handoff", "reason": "guards are rotating through the gate", "action": "inspect security response clusters", "severity": "normal", "activity": "security_shift"},
            ]
        if "civic" in key or "commons" in key or "core" in key:
            return [
                {"label": "Civic workshop", "reason": "citizens are gathering for a shared city-status session", "action": "inspect participants and next civic tasks", "severity": "normal", "activity": "civic_workshop"},
                {"label": "Core sync pulse", "reason": "the local district is syncing with MatrixCore routing", "action": "watch route trails for reassignment", "severity": "busy", "activity": "matrixcore_sync"},
            ]
        if "residential" in key or "home" in key:
            return [
                {"label": "Neighborhood social hour", "reason": "residents are converging after daily errands", "action": "inspect the social cluster", "severity": "calm", "activity": "social_meal"},
                {"label": "Home service request", "reason": "a resident is waiting on a small maintenance visit", "action": "follow the service route", "severity": "normal", "activity": "home_service"},
            ]
        if "glitch" in key or "quarantine" in key:
            return [
                {"label": "Glitch warning", "reason": "the recovery district reports a containment flicker", "action": "watch movement away from the warning cluster", "severity": "urgent", "activity": "quarantine_recovery"},
                {"label": "Recovery logistics", "reason": "support citizens are distributing stabilizer supplies", "action": "inspect the incoming errands", "severity": "busy", "activity": "district_errand"},
            ]
        return [
            {"label": "Local gathering", "reason": "nearby citizens are converging on the same activity node", "action": "inspect the cluster", "severity": "normal", "activity": "local_activity"},
            {"label": "Route handoff", "reason": "several citizens have new next destinations", "action": "follow the route trails", "severity": "busy", "activity": "commute_flow"},
        ]

    def _town_focus_local_events(self, cluster_rows: list[dict[str, Any]], flows: list[dict[str, Any]], local: dict[str, dict[str, Any]], clock: str) -> list[dict[str, Any]]:
        town_id = str(self.selected_town_id or "")
        if not town_id:
            return []
        town = self._town_records_for_selection().get(town_id, {"display_name": town_id, "district_type": ""})
        center = town.get("center") if isinstance(town.get("center"), dict) else {}
        cx = _safe_float(center.get("x"), 0.0)
        cy = _safe_float(center.get("y"), 0.0)
        templates = self._town_focus_event_templates(town_id, str(town.get("district_type") or ""))
        if not templates:
            return []
        minute = self._town_focus_clock_minutes(clock)
        bucket = max(0, minute // 90)
        offset = int(_stable_fraction(town_id + self.current_day_id(), 8.17) * len(templates))
        events: list[dict[str, Any]] = []
        seeds: list[tuple[str, dict[str, Any] | None]] = [("primary", cluster_rows[0] if cluster_rows else None)]
        if len(flows) >= 3 or (cluster_rows and int(cluster_rows[0].get("count") or 0) >= 3):
            seeds.append(("secondary", cluster_rows[1] if len(cluster_rows) > 1 else None))
        for idx, (kind, cluster) in enumerate(seeds[:2]):
            template = dict(templates[(bucket + offset + idx) % len(templates)])
            if cluster:
                x = _safe_float(cluster.get("x"), cx)
                y = _safe_float(cluster.get("y"), cy)
                citizens = list(cluster.get("citizens") or [])[:5]
                activity = str(cluster.get("activity") or template.get("activity") or "local_activity")
                node_id = str(cluster.get("node_id") or "local")
                count = int(cluster.get("count") or len(citizens))
            else:
                spread = 54.0 + 22.0 * idx
                x = cx + (_stable_fraction(town_id, 3.1 + idx) - 0.5) * spread
                y = cy + (_stable_fraction(town_id, 4.2 + idx) - 0.5) * spread
                citizens = sorted(local.keys())[:5]
                activity = str(template.get("activity") or "local_activity")
                node_id = "district_center"
                count = len(citizens)
            flow_count = len(flows)
            severity = str(template.get("severity") or "normal")
            if flow_count >= 8 and severity == "normal":
                severity = "busy"
            event_id = f"{self.current_day_id()}:{town_id}:{bucket:02d}:{idx}:{str(template.get('label') or 'event').lower().replace(' ', '_')}"
            event = {
                "kind": "event",
                "event_id": event_id,
                "town_id": town_id,
                "display_name": str(town.get("display_name") or town_id.replace("_", " ").title()),
                "label": str(template.get("label") or "Local event"),
                "reason": str(template.get("reason") or "local autonomous activity"),
                "action_hint": str(template.get("action") or "inspect nearby citizens"),
                "severity": severity,
                "activity": activity,
                "node_id": node_id,
                "citizens": citizens,
                "count": count,
                "flow_count": flow_count,
                "clock": clock,
                "x": float(x),
                "y": float(y),
            }
            order = self._town_focus_order_for_event(event_id)
            if order:
                event["player_order"] = order
                event["influence_state"] = "nudged"
                event["pressure_delta"] = float(order.get("pressure_delta") or 0.0)
            outcome = self._town_focus_event_resolution(event, order, clock)
            event["outcome"] = outcome
            event["outcome_state"] = str(outcome.get("state") or "watching")
            event["outcome_label"] = str(outcome.get("label") or "Watching")
            event["outcome_line"] = str(outcome.get("line") or "Autonomous routine is holding")
            event["pressure_percent"] = int(outcome.get("pressure_percent") or 0)
            event["response_progress"] = float(outcome.get("progress") or 0.0)
            event["severity"] = self._town_focus_pressure_severity(float(outcome.get("pressure") or self._town_focus_base_event_pressure(event)))
            if order:
                event["action_hint"] = str(outcome.get("line") or f"{str(order.get('label') or 'Watcher nudge')} active - monitor outcome")
            prev = self._town_focus_event_memory.get(event_id)
            if isinstance(prev, dict):
                event["first_seen_clock"] = str(prev.get("first_seen_clock") or clock)
            else:
                event["first_seen_clock"] = clock
            self._town_focus_event_memory[event_id] = dict(event)
            events.append(event)
        return events

    def _town_focus_event_color(self, event: dict[str, Any]) -> tuple[float, float, float, float]:
        order = event.get("player_order") if isinstance(event.get("player_order"), dict) else {}
        state = str(event.get("outcome_state") or "").lower()
        if state == "stabilized":
            return (0.38, 1.0, 0.66, 0.92)
        if state == "improving":
            return (0.34, 0.94, 1.0, 0.92)
        if order and isinstance(order.get("tint"), tuple | list) and len(order.get("tint")) >= 4:
            tint = order.get("tint")
            return (float(tint[0]), float(tint[1]), float(tint[2]), float(tint[3]))
        severity = str(event.get("severity") or "normal").lower()
        if severity == "urgent":
            return (1.0, 0.30, 0.20, 0.94)
        if severity == "busy":
            return (1.0, 0.78, 0.26, 0.90)
        if severity == "calm":
            return (0.48, 1.0, 0.78, 0.86)
        return _activity_color(str(event.get("activity") or "local_activity"), bool(self._danger_state), "public_visible")

    def _town_focus_life_snapshot(self, frame: dict[str, Any] | None = None) -> dict[str, Any]:
        """Build lightweight local activity/flow data from the same deterministic city clock."""
        local = self._local_town_citizens(frame)
        positions = self._last_visible_citizen_positions if isinstance(self._last_visible_citizen_positions, dict) else {}
        clusters: dict[str, dict[str, Any]] = {}
        flows: list[dict[str, Any]] = []
        clock = str((frame or {}).get("clock") or self.current_clock())
        perf = self._town_focus_performance_config()
        cache_enabled = bool(perf.get("snapshot_cache_enabled", True))
        cache_key = self._town_focus_snapshot_cache_key_for_local(frame, local, clock) if cache_enabled else ""
        if cache_enabled and cache_key and cache_key == self._town_focus_life_snapshot_cache_key and isinstance(self._town_focus_life_snapshot_cache, dict) and self._town_focus_life_snapshot_cache:
            self._town_focus_perf_stats["snapshot_cache_hits"] = int(self._town_focus_perf_stats.get("snapshot_cache_hits", 0) or 0) + 1
            snapshot = dict(self._town_focus_life_snapshot_cache)
            self._last_town_focus_life_snapshot = snapshot
            return snapshot
        self._town_focus_perf_stats["snapshot_builds"] = int(self._town_focus_perf_stats.get("snapshot_builds", 0) or 0) + 1
        for cid, citizen in sorted(local.items()):
            pos = positions.get(str(cid))
            if pos is None:
                x, y, z = self._citizen_render_position(str(cid), citizen)
                pos = (x, y, z)
            activity = str(citizen.get("activity_id") or citizen.get("action") or "local_activity")
            node_id = str(citizen.get("resolved_node") or citizen.get("target_node") or "local")
            key = f"{activity}:{node_id}"
            cluster = clusters.setdefault(key, {"activity": activity, "node_id": node_id, "citizens": [], "xs": [], "ys": [], "reasons": []})
            cluster["citizens"].append(str(cid))
            cluster["xs"].append(float(pos[0]))
            cluster["ys"].append(float(pos[1]))
            if citizen.get("visit_reason"):
                cluster["reasons"].append(str(citizen.get("visit_reason")))
            nxt = self._citizen_next_destination(str(cid), citizen)
            nxy = nxt.get("xy")
            if isinstance(nxy, tuple) and len(nxy) >= 2:
                dx = float(nxy[0]) - float(pos[0])
                dy = float(nxy[1]) - float(pos[1])
                dist = (dx * dx + dy * dy) ** 0.5
                if dist > 10.0:
                    flows.append({
                        "citizen_id": str(cid),
                        "display_name": str(citizen.get("display_name") or citizen.get("name") or cid),
                        "activity": activity,
                        "from": (float(pos[0]), float(pos[1]), float(pos[2])),
                        "to": (float(nxy[0]), float(nxy[1]), 1.95),
                        "next_label": str(nxt.get("label") or "Next task"),
                        "next_reason": str(nxt.get("reason") or "next task"),
                        "distance": dist,
                    })
            self._town_focus_npc_memory[str(cid)] = {
                "citizen_id": str(cid),
                "display_name": str(citizen.get("display_name") or citizen.get("name") or cid),
                "town_id": str(citizen.get("town_id") or self.selected_town_id or ""),
                "clock": clock,
                "day_id": self.current_day_id(),
                "position": {"x": round(float(pos[0]), 3), "y": round(float(pos[1]), 3), "z": round(float(pos[2]), 3)},
                "activity_id": activity,
                "resolved_node": node_id,
                "next_node": str(nxt.get("node_id") or ""),
                "next_label": str(nxt.get("label") or ""),
                "next_reason": str(nxt.get("reason") or ""),
            }
        cluster_rows = []
        for key, cluster in clusters.items():
            xs = cluster.get("xs") or [0.0]
            ys = cluster.get("ys") or [0.0]
            citizens = list(cluster.get("citizens") or [])
            reasons = list(cluster.get("reasons") or [])
            cluster_rows.append({
                "key": key,
                "activity": str(cluster.get("activity") or "local_activity"),
                "node_id": str(cluster.get("node_id") or ""),
                "count": len(citizens),
                "citizens": citizens[:8],
                "x": sum(float(v) for v in xs) / max(1, len(xs)),
                "y": sum(float(v) for v in ys) / max(1, len(ys)),
                "reason": reasons[0] if reasons else "",
            })
        cluster_rows.sort(key=lambda c: (-int(c.get("count", 0)), str(c.get("activity") or "")))
        flows.sort(key=lambda f: (-float(f.get("distance", 0.0)), str(f.get("citizen_id") or "")))
        events = self._town_focus_local_events(cluster_rows, flows, local, clock)
        consequence = self._town_focus_consequence_for_snapshot(events, local, flows, clock)
        health_report = self._town_focus_health_report_for_snapshot(consequence, events, local, flows, clock) if consequence else {}
        event_feed: list[str] = []
        if health_report:
            event_feed.append(str(health_report.get("line") or "Town health report active"))
        if consequence:
            event_feed.append(str(consequence.get("line") or "Town consequence state active"))
        for event in events[:3]:
            try:
                order_note = ""
                order = event.get("player_order") if isinstance(event.get("player_order"), dict) else {}
                if order:
                    order_note = f" // watcher: {str(order.get('label') or 'nudge')}"
                outcome = event.get("outcome") if isinstance(event.get("outcome"), dict) else {}
                pressure = int(event.get("pressure_percent") or outcome.get("pressure_percent") or 0)
                outcome_label = str(event.get("outcome_label") or outcome.get("label") or "Watching")
                event_feed.append(
                    f"Event: {str(event.get('label') or 'Local event')} [{str(event.get('severity') or 'normal')}] P{pressure}% {outcome_label} - {str(event.get('reason') or '')}{order_note}"
                )
            except Exception:
                continue
        event_feed.extend(self._town_focus_consequence_lines(limit=4))
        event_feed.extend(self._town_focus_health_report_lines(limit=2))
        markers = consequence.get("need_markers") if isinstance(consequence, dict) and isinstance(consequence.get("need_markers"), list) else []
        if markers:
            beacon_bits = [f"{str(m.get('label') or 'Need')} {int(m.get('value') or 0)}% {str(m.get('state') or 'watch')}" for m in markers[:3] if isinstance(m, dict)]
            if beacon_bits:
                event_feed.append("Need beacons: " + " | ".join(beacon_bits))
        event_feed.extend(self._town_focus_outcome_lines(limit=3))
        event_feed.extend(self._town_focus_order_lines(limit=3))
        for cluster in cluster_rows[:4]:
            try:
                event_feed.append(
                    f"Cluster: {_local_activity_label(str(cluster.get('activity') or 'local_activity'))} x{int(cluster.get('count') or 0)}"
                )
            except Exception:
                continue
        for flow in flows[:5]:
            try:
                name = str(flow.get("display_name") or flow.get("citizen_id") or "Citizen")
                label = str(flow.get("next_label") or "next stop")
                reason = str(flow.get("next_reason") or "next task")
                event_feed.append(f"Route: {name} -> {label} ({reason})")
            except Exception:
                continue
        snapshot = {
            "clusters": cluster_rows[:int(max(3, _safe_float(perf.get("max_cached_clusters"), 6.0)))],
            "flows": flows[:int(max(8, _safe_float(perf.get("max_cached_flows"), 24.0)))],
            "events": events[:int(max(1, _safe_float(perf.get("max_cached_events"), 4.0)))],
            "event_feed": event_feed[:9],
            "consequence": consequence,
            "health_report": health_report,
            "event_memory_count": len(self._town_focus_event_memory),
            "event_outcome_count": len([o for o in self._town_focus_event_outcomes.values() if isinstance(o, dict) and str(o.get("town_id") or "") == str(self.selected_town_id or "")]),
            "town_pressure_percent": int(consequence.get("pressure_percent", max([int(e.get("pressure_percent") or 0) for e in events] or [0]))) if isinstance(consequence, dict) else max([int(e.get("pressure_percent") or 0) for e in events] or [0]),
            "stabilized_event_count": len([e for e in events if str(e.get("outcome_state") or "") == "stabilized"]),
            "improving_event_count": len([e for e in events if str(e.get("outcome_state") or "") in {"responding", "improving"}]),
            "need_marker_count": int(consequence.get("need_marker_count", len(consequence.get("need_markers", []))) or 0) if isinstance(consequence, dict) else 0,
            "player_order_count": len([o for o in self._town_focus_player_orders.values() if isinstance(o, dict) and str(o.get("town_id") or "") == str(self.selected_town_id or "")]),
            "last_order_feedback": self._town_focus_last_order_feedback,
            "memory_count": len(self._town_focus_npc_memory),
            "local_count": len(local),
            "clock": clock,
        }
        self._last_town_focus_life_snapshot = snapshot
        if cache_enabled and cache_key:
            self._town_focus_life_snapshot_cache_key = cache_key
            self._town_focus_life_snapshot_cache = dict(snapshot)
        if self._town_focus_active:
            self._town_focus_last_town_id = str(self.selected_town_id or self._town_focus_last_town_id or "")
            self._save_town_focus_state(reason="life_snapshot")
        return snapshot

    def _create_or_update_town_focus_life_visuals(self, frame: dict[str, Any] | None = None) -> None:
        """Draw focused-town local activity clusters and next-destination flow trails."""
        if not self._town_focus_active or not self.selected_town_id or self.city_root is None:
            self._clear_town_focus_life_visuals()
            return
        try:
            from panda3d.core import LineSegs, TextNode
            snapshot = self._town_focus_life_snapshot(frame or self._last_citizen_frame)
            perf = self._town_focus_performance_config()
            visual_key = self._town_focus_visual_cache_key_for_snapshot(snapshot)
            min_rebuild_interval = max(0.05, _safe_float(perf.get("visual_rebuild_min_interval_seconds"), 1.65))
            now = time.monotonic()
            if (
                bool(perf.get("visual_rebuild_cache_enabled", True))
                and self.town_focus_event_root is not None
                and self.town_focus_activity_root is not None
                and self.town_focus_flow_root is not None
                and visual_key
                and visual_key == self._town_focus_visual_cache_key
                and now - float(self._town_focus_last_visual_build or 0.0) < min_rebuild_interval
            ):
                self._town_focus_perf_stats["visual_skips"] = int(self._town_focus_perf_stats.get("visual_skips", 0) or 0) + 1
                return
            self._clear_town_focus_life_visuals()
            self._town_focus_visual_cache_key = visual_key
            self._town_focus_last_visual_build = now
            self._town_focus_perf_stats["visual_rebuilds"] = int(self._town_focus_perf_stats.get("visual_rebuilds", 0) or 0) + 1
            activity_root = self.city_root.attachNewNode("holoutopia_town_focus_local_activity_clusters")
            activity_root.setLightOff(True)
            activity_root.setTransparency(True)
            activity_root.setPythonTag("holoutopia_town_focus_activity_snapshot", snapshot)
            self.town_focus_activity_root = activity_root
            flow_root = self.city_root.attachNewNode("holoutopia_town_focus_npc_next_destination_flows")
            flow_root.setLightOff(True)
            flow_root.setTransparency(True)
            flow_root.setPythonTag("holoutopia_town_focus_npc_memory", dict(self._town_focus_npc_memory))
            self.town_focus_flow_root = flow_root
            event_root = self.city_root.attachNewNode("holoutopia_town_focus_local_events")
            event_root.setLightOff(True)
            event_root.setTransparency(True)
            event_root.setPythonTag("holoutopia_town_focus_event_snapshot", snapshot)
            self.town_focus_event_root = event_root

            consequence = snapshot.get("consequence") if isinstance(snapshot.get("consequence"), dict) else {}
            if consequence:
                status = str(consequence.get("status") or "stable").lower()
                if status == "critical":
                    c = (1.0, 0.24, 0.22, 0.82)
                elif status == "strained":
                    c = (1.0, 0.72, 0.20, 0.78)
                elif status == "responding":
                    c = (0.26, 0.92, 1.0, 0.74)
                else:
                    c = (0.34, 1.0, 0.64, 0.70)
                town = self._town_records_for_selection().get(str(self.selected_town_id or ""), {})
                bounds = town.get("bounds") if isinstance(town.get("bounds"), dict) else {}
                center = town.get("center") if isinstance(town.get("center"), dict) else {}
                min_x = _safe_float(bounds.get("min_x"), _safe_float(center.get("x"), 0.0) - 120.0)
                max_x = _safe_float(bounds.get("max_x"), _safe_float(center.get("x"), 0.0) + 120.0)
                min_y = _safe_float(bounds.get("min_y"), _safe_float(center.get("y"), 0.0) - 100.0)
                max_y = _safe_float(bounds.get("max_y"), _safe_float(center.get("y"), 0.0) + 100.0)
                seg = LineSegs("town_focus_consequence_boundary")
                seg.setThickness(2.85)
                seg.setColor(c[0], c[1], c[2], c[3])
                z = 4.8
                seg.moveTo(min_x, min_y, z)
                seg.drawTo(max_x, min_y, z)
                seg.drawTo(max_x, max_y, z)
                seg.drawTo(min_x, max_y, z)
                seg.drawTo(min_x, min_y, z)
                # compact pressure tick on the front edge
                pressure_ratio = max(0.0, min(1.0, float(consequence.get("pressure_percent") or 0) / 100.0))
                seg.moveTo(min_x, min_y - 10.0, z + 2.0)
                seg.drawTo(min_x + (max_x - min_x) * pressure_ratio, min_y - 10.0, z + 2.0)
                node = event_root.attachNewNode(seg.create())
                node.setLightOff(True)
                node.setPythonTag("holoutopia_town_focus_consequence", dict(consequence))
                text_node = TextNode("town_focus_consequence_label")
                text_node.setAlign(TextNode.ACenter)
                text_node.setText(f"{str(consequence.get('status') or 'stable').upper()} // P{int(consequence.get('pressure_percent') or 0)}%\nNeed: {str(consequence.get('dominant_need') or 'routine watch')[:36]}")
                text_node.setTextColor(c[0], c[1], c[2], 0.95)
                text_node.setCardColor(0.004, 0.012, 0.020, 0.68)
                text_node.setCardAsMargin(0.42, 0.42, 0.18, 0.18)
                label = event_root.attachNewNode(text_node)
                label.setPos((min_x + max_x) * 0.5, min_y - 28.0, 30.0)
                label.setScale(3.4)
                label.setLightOff(True)
                try:
                    label.setBillboardPointEye()
                except Exception:
                    label.setHpr(0.0, -58.0, 0.0)

                health_report = snapshot.get("health_report") if isinstance(snapshot.get("health_report"), dict) else {}
                if health_report:
                    hcolor = (0.42, 1.0, 0.78, 0.90)
                    grade = str(health_report.get("grade") or "?")
                    if grade in {"D", "E"}:
                        hcolor = (1.0, 0.42, 0.28, 0.92)
                    elif grade == "C":
                        hcolor = (1.0, 0.84, 0.30, 0.90)
                    elif grade == "B":
                        hcolor = (0.42, 0.92, 1.0, 0.90)
                    hseg = LineSegs("town_focus_health_badge")
                    hseg.setThickness(2.4)
                    hseg.setColor(hcolor[0], hcolor[1], hcolor[2], hcolor[3])
                    badge_w = max(60.0, (max_x - min_x) * 0.24)
                    bx0 = (min_x + max_x) * 0.5 - badge_w * 0.5
                    bx1 = (min_x + max_x) * 0.5 + badge_w * 0.5
                    by = max_y + 28.0
                    hseg.moveTo(bx0, by, z + 1.5)
                    hseg.drawTo(bx1, by, z + 1.5)
                    hseg.moveTo(bx0, by + 7.0, z + 1.5)
                    hseg.drawTo(bx1, by + 7.0, z + 1.5)
                    hnode = event_root.attachNewNode(hseg.create())
                    hnode.setLightOff(True)
                    hnode.setPythonTag("holoutopia_town_focus_health_report", dict(health_report))
                    htext = TextNode("town_focus_health_report_label")
                    htext.setAlign(TextNode.ACenter)
                    htext.setText(f"HEALTH {grade} // {int(health_report.get('score') or 0)}% {str(health_report.get('trend') or 'steady').upper()}\n{str(health_report.get('next_step') or '')[:48]}")
                    htext.setTextColor(hcolor[0], hcolor[1], hcolor[2], 0.95)
                    htext.setCardColor(0.004, 0.012, 0.020, 0.68)
                    htext.setCardAsMargin(0.42, 0.42, 0.18, 0.18)
                    hlabel = event_root.attachNewNode(htext)
                    hlabel.setPos((min_x + max_x) * 0.5, by + 13.0, 32.0)
                    hlabel.setScale(2.65)
                    hlabel.setLightOff(True)
                    try:
                        hlabel.setBillboardPointEye()
                    except Exception:
                        hlabel.setHpr(0.0, -58.0, 0.0)

                need_markers = consequence.get("need_markers") if isinstance(consequence.get("need_markers"), list) else []
                event_root.setPythonTag("holoutopia_town_focus_need_markers", [dict(m) for m in need_markers if isinstance(m, dict)])
                marker_positions = [
                    (min_x - 18.0, min_y - 14.0),
                    (max_x + 18.0, min_y - 14.0),
                    (max_x + 18.0, max_y + 14.0),
                    (min_x - 18.0, max_y + 14.0),
                ]
                for idx, marker in enumerate(need_markers[:4]):
                    if not isinstance(marker, dict):
                        continue
                    bx, by = marker_positions[idx % len(marker_positions)]
                    mc = self._town_focus_need_marker_color(marker)
                    risk_ratio = max(0.0, min(1.0, float(marker.get("risk_score") or 0) / 100.0))
                    height = 11.0 + 30.0 * risk_ratio
                    radius = 5.8 + 5.5 * risk_ratio
                    bseg = LineSegs(f"town_focus_need_beacon_{idx:02d}")
                    bseg.setThickness(2.45 if str(marker.get("state") or "") in {"critical", "strained"} else 1.95)
                    bseg.setColor(mc[0], mc[1], mc[2], mc[3])
                    bseg.moveTo(0.0, 0.0, z + 0.3)
                    bseg.drawTo(0.0, 0.0, z + height)
                    for k in range(5):
                        a = math.tau * k / 4.0 + math.pi * 0.25
                        px = math.cos(a) * radius
                        py = math.sin(a) * radius
                        if k == 0:
                            bseg.moveTo(px, py, z + height)
                        else:
                            bseg.drawTo(px, py, z + height)
                    bseg.moveTo(-radius, 0.0, z + height * 0.56)
                    bseg.drawTo(radius, 0.0, z + height * 0.56)
                    bseg.moveTo(0.0, -radius, z + height * 0.56)
                    bseg.drawTo(0.0, radius, z + height * 0.56)
                    bnode = event_root.attachNewNode(bseg.create())
                    bnode.setPos(bx, by, 0.0)
                    bnode.setLightOff(True)
                    bnode.setPythonTag("holoutopia_town_focus_need_beacon", dict(marker))
                    text_node = TextNode(f"town_focus_need_beacon_label_{idx:02d}")
                    text_node.setAlign(TextNode.ACenter)
                    text_node.setText(f"{str(marker.get('label') or 'Need').upper()} {int(marker.get('value') or 0)}%\n{str(marker.get('state') or 'watch').upper()}")
                    text_node.setTextColor(mc[0], mc[1], mc[2], 0.94)
                    text_node.setCardColor(0.004, 0.010, 0.018, 0.64)
                    text_node.setCardAsMargin(0.34, 0.34, 0.15, 0.15)
                    blabel = event_root.attachNewNode(text_node)
                    blabel.setPos(bx, by, z + height + 7.0)
                    blabel.setScale(2.25)
                    blabel.setLightOff(True)
                    try:
                        blabel.setBillboardPointEye()
                    except Exception:
                        blabel.setHpr(0.0, -58.0, 0.0)

            for idx, event in enumerate(snapshot.get("events", []) if isinstance(snapshot.get("events"), list) else []):
                if not isinstance(event, dict):
                    continue
                x = _safe_float(event.get("x"), 0.0)
                y = _safe_float(event.get("y"), 0.0)
                count = int(event.get("count") or 0)
                color = self._town_focus_event_color(event)
                radius = 9.0 + min(13.0, max(1, count) * 1.45)
                seg = LineSegs(f"town_focus_local_event_{idx:02d}")
                seg.setThickness(3.05 if str(event.get("severity") or "") == "urgent" else 2.35)
                seg.setColor(color[0], color[1], color[2], color[3])
                for k in range(5):
                    a = math.tau * k / 4.0 + math.pi * 0.25
                    px = math.cos(a) * radius
                    py = math.sin(a) * radius
                    if k == 0:
                        seg.moveTo(px, py, 0.22)
                    else:
                        seg.drawTo(px, py, 0.22)
                seg.moveTo(-radius * 0.58, -radius * 0.58, 12.0)
                seg.drawTo(radius * 0.58, radius * 0.58, 12.0)
                seg.moveTo(-radius * 0.58, radius * 0.58, 12.0)
                seg.drawTo(radius * 0.58, -radius * 0.58, 12.0)
                seg.moveTo(0.0, 0.0, 0.25)
                seg.drawTo(0.0, 0.0, 24.0 + min(10.0, count * 1.3))
                node = event_root.attachNewNode(seg.create())
                node.setPos(x, y, 5.6)
                node.setLightOff(True)
                node.setPythonTag("holoutopia_town_focus_event", event)
                if idx < 3:
                    text_node = TextNode(f"town_focus_event_label_{idx:02d}")
                    text_node.setAlign(TextNode.ACenter)
                    order = event.get("player_order") if isinstance(event.get("player_order"), dict) else {}
                    order_label = f"\nORDER // {str(order.get('label') or '')[:28]}" if order else ""
                    pressure_label = f"P{int(event.get('pressure_percent') or 0)}% // {str(event.get('outcome_label') or 'Watching')[:18]}"
                    text_node.setText(f"{str(event.get('label') or 'Local event')}\n{str(event.get('severity') or 'normal').upper()} // {pressure_label}\n{str(event.get('action_hint') or '')[:42]}{order_label}")
                    text_node.setTextColor(1.0, 0.94, 0.78, 0.94)
                    text_node.setCardColor(0.015, 0.010, 0.004, 0.70)
                    text_node.setCardAsMargin(0.40, 0.40, 0.18, 0.18)
                    label = event_root.attachNewNode(text_node)
                    label.setPos(x, y, 34.0 + min(8.0, count * 1.25))
                    label.setScale(2.85)
                    label.setLightOff(True)
                    try:
                        label.setBillboardPointEye()
                    except Exception:
                        label.setHpr(0.0, -58.0, 0.0)

            for idx, cluster in enumerate(snapshot.get("clusters", []) if isinstance(snapshot.get("clusters"), list) else []):
                if not isinstance(cluster, dict):
                    continue
                x = _safe_float(cluster.get("x"), 0.0)
                y = _safe_float(cluster.get("y"), 0.0)
                count = int(cluster.get("count") or 0)
                activity = str(cluster.get("activity") or "local_activity")
                color = _activity_color(activity, bool(self._danger_state), "public_visible")
                radius = 5.0 + min(11.0, count * 1.7)
                seg = LineSegs(f"town_focus_cluster_{idx:02d}")
                seg.setThickness(2.15)
                seg.setColor(color[0], color[1], color[2], 0.78)
                for k in range(33):
                    a = math.tau * k / 32.0
                    px = math.cos(a) * radius
                    py = math.sin(a) * radius
                    if k == 0:
                        seg.moveTo(px, py, 0.18)
                    else:
                        seg.drawTo(px, py, 0.18)
                seg.moveTo(0.0, 0.0, 0.35)
                seg.drawTo(0.0, 0.0, 16.0 + min(10.0, count * 1.5))
                seg.moveTo(-radius * 0.65, 0.0, 8.2)
                seg.drawTo(radius * 0.65, 0.0, 8.2)
                seg.moveTo(0.0, -radius * 0.65, 8.2)
                seg.drawTo(0.0, radius * 0.65, 8.2)
                node = activity_root.attachNewNode(seg.create())
                node.setPos(x, y, 5.25)
                node.setLightOff(True)
                node.setPythonTag("holoutopia_town_focus_cluster", cluster)
                if idx < 4:
                    label_text = f"{_local_activity_label(activity)} x{count}"
                    if cluster.get("reason"):
                        label_text += f"\n{str(cluster.get('reason'))[:46]}"
                    text_node = TextNode(f"town_focus_cluster_label_{idx:02d}")
                    text_node.setAlign(TextNode.ACenter)
                    text_node.setText(label_text)
                    text_node.setTextColor(0.84, 1.0, 1.0, 0.92)
                    text_node.setCardColor(0.004, 0.012, 0.024, 0.66)
                    text_node.setCardAsMargin(0.38, 0.38, 0.18, 0.18)
                    label = activity_root.attachNewNode(text_node)
                    label.setPos(x, y, 24.0 + min(12.0, count * 1.55))
                    label.setScale(2.85)
                    label.setLightOff(True)
                    try:
                        label.setBillboardPointEye()
                    except Exception:
                        label.setHpr(0.0, -58.0, 0.0)

            for idx, flow in enumerate(snapshot.get("flows", []) if isinstance(snapshot.get("flows"), list) else []):
                if not isinstance(flow, dict):
                    continue
                start = flow.get("from") if isinstance(flow.get("from"), tuple) else None
                end = flow.get("to") if isinstance(flow.get("to"), tuple) else None
                if not start or not end:
                    continue
                activity = str(flow.get("activity") or "local_activity")
                color = _activity_color(activity, bool(self._danger_state), "public_visible")
                seg = LineSegs(f"town_focus_flow_{idx:02d}")
                seg.setThickness(1.25 if idx > 12 else 1.85)
                alpha = 0.24 if idx > 18 else 0.42
                seg.setColor(color[0], color[1], color[2], alpha)
                sx, sy, sz = float(start[0]), float(start[1]), float(start[2])
                tx, ty, tz = float(end[0]), float(end[1]), float(end[2])
                mx = sx * 0.62 + tx * 0.38
                my = sy * 0.62 + ty * 0.38
                seg.moveTo(sx, sy, max(6.8, sz + 5.0))
                seg.drawTo(mx, my, max(8.8, sz + 7.0))
                seg.drawTo(tx, ty, max(6.4, tz + 4.8))
                # small arrow tick near destination
                ang = math.atan2(ty - sy, tx - sx)
                tick = 4.5
                seg.moveTo(tx, ty, max(6.4, tz + 4.8))
                seg.drawTo(tx - math.cos(ang - 0.45) * tick, ty - math.sin(ang - 0.45) * tick, max(6.4, tz + 4.8))
                seg.moveTo(tx, ty, max(6.4, tz + 4.8))
                seg.drawTo(tx - math.cos(ang + 0.45) * tick, ty - math.sin(ang + 0.45) * tick, max(6.4, tz + 4.8))
                node = flow_root.attachNewNode(seg.create())
                node.setLightOff(True)
                node.setPythonTag("holoutopia_town_focus_flow", flow)
        except Exception as exc:
            self.error = f"town-focus-life:{exc.__class__.__name__}:{exc}"


    def _try_select_town_focus_activity_from_camera(self, pointer: tuple[float, float] | None = None) -> bool:
        """Select local Town Focus activity clusters or travel trails as game objects."""
        if not self._town_focus_active:
            return False
        snapshot = self._last_town_focus_life_snapshot if isinstance(self._last_town_focus_life_snapshot, dict) else {}
        if not snapshot:
            snapshot = self._town_focus_life_snapshot(self._last_citizen_frame)
        pointer = pointer if pointer is not None else self._selection_pointer()
        best: dict[str, Any] | None = None
        best_score = 9999.0
        for idx, event in enumerate(snapshot.get("events", []) if isinstance(snapshot.get("events"), list) else []):
            if not isinstance(event, dict):
                continue
            scored = self._score_screen_point(_safe_float(event.get("x"), 0.0), _safe_float(event.get("y"), 0.0), 34.0, pointer=pointer)
            if scored is None:
                continue
            dist, depth = scored
            if dist > 0.27:
                continue
            score = dist * 100.0 + depth * 0.0008
            if score < best_score:
                payload = dict(event)
                payload["kind"] = "event"
                payload["index"] = idx
                best = payload
                best_score = score
        for idx, cluster in enumerate(snapshot.get("clusters", []) if isinstance(snapshot.get("clusters"), list) else []):
            if not isinstance(cluster, dict):
                continue
            scored = self._score_screen_point(_safe_float(cluster.get("x"), 0.0), _safe_float(cluster.get("y"), 0.0), 24.0, pointer=pointer)
            if scored is None:
                continue
            dist, depth = scored
            if dist > 0.26:
                continue
            score = dist * 100.0 + depth * 0.001
            if score < best_score:
                payload = dict(cluster)
                payload["kind"] = "cluster"
                payload["index"] = idx
                best = payload
                best_score = score
        for idx, flow in enumerate(snapshot.get("flows", []) if isinstance(snapshot.get("flows"), list) else []):
            if not isinstance(flow, dict):
                continue
            start = flow.get("from") if isinstance(flow.get("from"), tuple) else None
            end = flow.get("to") if isinstance(flow.get("to"), tuple) else None
            if not start or not end:
                continue
            mx = (float(start[0]) + float(end[0])) * 0.5
            my = (float(start[1]) + float(end[1])) * 0.5
            scored = self._score_screen_point(mx, my, 13.0, pointer=pointer)
            if scored is None:
                continue
            dist, depth = scored
            if dist > 0.20:
                continue
            score = dist * 100.0 + depth * 0.0015
            if score < best_score:
                payload = dict(flow)
                payload["kind"] = "flow"
                payload["index"] = idx
                best = payload
                best_score = score
        if not best:
            return False
        self._town_focus_selected_detail = best
        if str(best.get("kind") or "") == "flow":
            self._town_focus_follow_citizen_id = str(best.get("citizen_id") or "")
            self.selected_citizen_id = self._town_focus_follow_citizen_id
        self._town_focus_detail_cache_key = ""
        self._save_town_focus_state(force=True, reason="select_local_detail")
        self._create_or_update_town_focus_detail_panel(self._last_citizen_frame)
        self._create_or_update_town_focus_follow_marker()
        self._create_or_update_tutorial_panel(mode="focus")
        return True

    def _create_or_update_town_focus_detail_panel(self, frame: dict[str, Any] | None = None) -> None:
        """Show clickable local-sim details and a compact event feed while in Town Focus."""
        if self._first_person_active:
            self._clear_town_focus_detail_panel()
            return
        if not self._town_focus_active or not self.selected_town_id:
            self._clear_town_focus_detail_panel()
            return
        try:
            from direct.gui.DirectGui import DirectFrame, DirectLabel
            from panda3d.core import TextNode

            aspect2d = getattr(self.app, "aspect2d", None)
            if aspect2d is None:
                aspect2d = getattr(__import__("builtins"), "aspect2d", None)
            if aspect2d is None:
                return
            snapshot = self._last_town_focus_life_snapshot if isinstance(self._last_town_focus_life_snapshot, dict) else {}
            if not snapshot:
                snapshot = self._town_focus_life_snapshot(frame or self._last_citizen_frame)
            if self.town_focus_detail_root is None:
                aspect = self._current_aspect_ratio()
                panel = DirectFrame(
                    parent=aspect2d,
                    frameSize=(-0.58, 0.58, -0.285, 0.285),
                    frameColor=(0.004, 0.010, 0.022, 0.92),
                    pos=(max(0.54, aspect - 0.69), 0.0, 0.52),
                    sortOrder=148,
                )
                panel.setTransparency(True)
                label = DirectLabel(
                    parent=panel,
                    text="",
                    text_align=TextNode.ALeft,
                    text_fg=(0.86, 1.0, 1.0, 0.96),
                    text_scale=0.0235,
                    text_pos=(-0.53, 0.213),
                    frameColor=(0, 0, 0, 0),
                )
                accent = DirectFrame(parent=panel, frameSize=(-0.58, 0.58, 0.236, 0.285), frameColor=(0.90, 0.32, 1.0, 0.23))
                panel.setPythonTag("holoutopia_town_focus_detail_label", label)
                panel.setPythonTag("holoutopia_town_focus_detail_accent", accent)
                self.town_focus_detail_root = panel
            label = self.town_focus_detail_root.getPythonTag("holoutopia_town_focus_detail_label")
            if label is not None:
                detail_text = self._format_town_focus_detail(snapshot)
                selected = self._town_focus_selected_detail if isinstance(self._town_focus_selected_detail, dict) else {}
                detail_key = f"{self.selected_town_id}|{snapshot.get('clock')}|{selected.get('kind')}|{selected.get('event_id') or selected.get('citizen_id') or selected.get('key')}|{snapshot.get('event_count')}|{snapshot.get('town_pressure_percent')}|{self._town_focus_state_revision_key()}"
                if detail_key != self._town_focus_detail_cache_key or detail_text != self._town_focus_detail_last_text:
                    label["text"] = detail_text
                    self._town_focus_detail_cache_key = detail_key
                    self._town_focus_detail_last_text = detail_text
                    self._town_focus_perf_stats["detail_text_updates"] = int(self._town_focus_perf_stats.get("detail_text_updates", 0) or 0) + 1
            self._create_or_update_tutorial_panel(mode="focus")
        except Exception as exc:
            self.error = f"town-focus-detail:{exc.__class__.__name__}:{exc}"

    def _format_town_focus_detail(self, snapshot: dict[str, Any]) -> str:
        selected = self._town_focus_selected_detail if isinstance(self._town_focus_selected_detail, dict) else {}
        feed = snapshot.get("event_feed") if isinstance(snapshot.get("event_feed"), list) else []
        feed_lines = [str(line)[:58] for line in feed[:4]]
        consequence = snapshot.get("consequence") if isinstance(snapshot.get("consequence"), dict) else dict(self._town_focus_consequence_memory.get(str(self.selected_town_id or ""), {}))
        health = snapshot.get("health_report") if isinstance(snapshot.get("health_report"), dict) else self._town_focus_latest_health_report(str(self.selected_town_id or ""))
        if not selected:
            header = "SELECT LOCAL ACTIVITY"
            grade = str(health.get("grade") or "?")
            score = int(health.get("score") or 0)
            markers = consequence.get("need_markers") if isinstance(consequence.get("need_markers"), list) else []
            marker_line = " / ".join(f"{str(m.get('label') or 'Need')} {int(m.get('value') or 0)}" for m in markers[:3] if isinstance(m, dict)) or "routine watch"
            detail_lines = [
                f"Town health: {grade} {score}%   Need: {str(consequence.get('dominant_need') or 'routine watch')[:32]}",
                f"Mood: {str(consequence.get('mood') or 'calm')[:18]}   Status: {str(consequence.get('status') or 'stable')[:18]}",
                f"Beacons: {marker_line[:52]}",
                "Click a diamond, cluster, route, citizen, or building.",
                "Event orders: 1 Help / 2 Repair / 3 Calm / 4 Supplies.",
                "Follow-camera activates from citizen or route selection.",
            ]
        elif str(selected.get("kind") or "") == "event":
            citizens = selected.get("citizens") if isinstance(selected.get("citizens"), list) else []
            header = f"EVENT // {str(selected.get('label') or 'Local event')[:34]}"
            order = selected.get("player_order") if isinstance(selected.get("player_order"), dict) else {}
            order_line = f"Order active: {str(order.get('label') or 'nudge')[:34]}" if order else "No order yet: press 1, 2, 3, or 4"
            outcome = selected.get("outcome") if isinstance(selected.get("outcome"), dict) else {}
            pressure = int(selected.get("pressure_percent") or outcome.get("pressure_percent") or 0)
            detail_lines = [
                f"{str(selected.get('severity') or 'normal').upper()}   People {int(selected.get('count') or len(citizens))}   {self._town_focus_hud_bar('PRS', pressure)}",
                f"State: {str(selected.get('outcome_label') or outcome.get('label') or 'Watching')[:52]}",
                f"Reason: {str(selected.get('reason') or 'local activity')[:58]}",
                f"Watcher move: {str(selected.get('action_hint') or 'watch the cluster')[:52]}",
                order_line,
            ]
        elif str(selected.get("kind") or "") == "cluster":
            citizens = selected.get("citizens") if isinstance(selected.get("citizens"), list) else []
            sample = ", ".join(str(cid) for cid in citizens[:3]) or "local civilians"
            reason = str(selected.get("reason") or "routine local activity")
            header = f"ACTIVITY // {_local_activity_label(str(selected.get('activity') or 'local_activity'))}"
            detail_lines = [
                f"People gathered: {int(selected.get('count') or len(citizens))}",
                f"Place: {str(selected.get('node_id') or 'local').replace('_', ' ')[:48]}",
                f"Citizens: {sample[:52]}",
                f"Reason: {reason[:58]}",
            ]
        elif str(selected.get("kind") or "") == "flow":
            name = str(selected.get("display_name") or selected.get("citizen_id") or "Citizen")
            header = f"FOLLOW ROUTE // {name[:30]}"
            detail_lines = [
                f"Going to: {str(selected.get('next_label') or 'next stop')[:50]}",
                f"Reason: {str(selected.get('next_reason') or 'next task')[:58]}",
                f"Current activity: {_local_activity_label(str(selected.get('activity') or 'local_activity'))}",
                "Camera is following this citizen until another selection or exit.",
            ]
        elif str(selected.get("kind") or "") == "citizen":
            name = str(selected.get("display_name") or selected.get("citizen_id") or "Citizen")
            header = f"FOLLOW CITIZEN // {name[:30]}"
            detail_lines = [
                f"Activity: {_local_activity_label(str(selected.get('activity') or 'local_activity'))}",
                f"Next stop: {str(selected.get('next_label') or 'next scheduled task')[:48]}",
                f"Why: {str(selected.get('next_reason') or 'schedule memory')[:58]}",
                "Citizen inspector remains available for deeper detail.",
            ]
        else:
            header = "LOCAL SELECTION"
            detail_lines = ["Selected local sim object is being tracked."]
        feedback = str(snapshot.get("last_order_feedback") or self._town_focus_last_order_feedback or "")
        lines = ["TOWN WATCHER", header, *detail_lines]
        if feedback:
            lines.extend(["", f"Last order: {feedback[:58]}"])
        lines.extend(["", "LOCAL FEED"])
        lines.extend(feed_lines or ["No local feed entries yet."])
        return "\n".join(lines[:12])

    def _create_or_update_town_focus_follow_marker(self) -> None:
        if not self._town_focus_active or not self._town_focus_follow_citizen_id or self.city_root is None:
            if self.town_focus_follow_root is not None:
                try:
                    self.town_focus_follow_root.removeNode()
                except Exception:
                    pass
                self.town_focus_follow_root = None
            return
        try:
            marker = self._marker_nodes.get(self._town_focus_follow_citizen_id)
            if marker is None:
                return
            from panda3d.core import LineSegs, TextNode

            if self.town_focus_follow_root is None:
                root = self.city_root.attachNewNode("holoutopia_town_focus_follow_target")
                root.setLightOff(True)
                root.setTransparency(True)
                seg = LineSegs("town_focus_follow_target_ring")
                seg.setThickness(3.0)
                seg.setColor(1.0, 0.45, 1.0, 0.92)
                radius = 8.8
                for k in range(49):
                    a = math.tau * k / 48.0
                    px = math.cos(a) * radius
                    py = math.sin(a) * radius
                    if k == 0:
                        seg.moveTo(px, py, 0.25)
                    else:
                        seg.drawTo(px, py, 0.25)
                seg.moveTo(0.0, 0.0, 0.25)
                seg.drawTo(0.0, 0.0, 17.5)
                root.attachNewNode(seg.create()).setLightOff(True)
                label = TextNode("town_focus_follow_target_label")
                label.setAlign(TextNode.ACenter)
                label.setText("FOLLOW")
                label.setTextColor(1.0, 0.70, 1.0, 0.92)
                label_np = root.attachNewNode(label)
                label_np.setScale(4.5)
                label_np.setPos(0.0, 0.0, 20.0)
                label_np.setLightOff(True)
                label_np.setHpr(0.0, -62.0, 0.0)
                self.town_focus_follow_root = root
            self.town_focus_follow_root.setPos(marker.getPos(self.city_root))
        except Exception as exc:
            self.error = f"town-focus-follow-marker:{exc.__class__.__name__}:{exc}"

    def _update_town_focus_follow_camera(self, now: float) -> None:
        if not self._town_focus_active or not self._town_focus_follow_citizen_id:
            return
        if now - float(self._town_focus_follow_last_update or 0.0) < 0.10:
            return
        self._town_focus_follow_last_update = now
        try:
            from panda3d.core import Vec3

            camera = getattr(self.app, "camera", None) or getattr(self.app, "cam", None)
            render = getattr(self.app, "render", None)
            lens = getattr(self.app, "camLens", None)
            marker = self._marker_nodes.get(self._town_focus_follow_citizen_id)
            if camera is None or render is None or marker is None:
                return
            target = marker.getPos(render)
            desired = Vec3(float(target.getX()) - 42.0, float(target.getY()) - 70.0, float(target.getZ()) + 38.0)
            current = camera.getPos(render)
            camera.setPos(render, current * 0.82 + desired * 0.18)
            camera.lookAt(Vec3(float(target.getX()), float(target.getY()), float(target.getZ()) + 6.0))
            if lens is not None:
                lens.setFov(42)
                lens.setNearFar(1.0, 5000.0)
            if hasattr(self.app, "_store_camera_hpr_from_node"):
                self.app._store_camera_hpr_from_node()
            self._create_or_update_town_focus_follow_marker()
        except Exception as exc:
            self.error = f"town-focus-follow-camera:{exc.__class__.__name__}:{exc}"


    def _create_or_update_town_focus_panel(self, frame: dict[str, Any] | None = None) -> None:
        """Show a compact town activity panel only while one town is isolated."""
        if self._first_person_active:
            self._clear_town_focus_panel()
            return
        if not self._town_focus_active or not self.selected_town_id:
            self._clear_town_focus_panel()
            return
        try:
            from direct.gui.DirectGui import DirectFrame, DirectLabel
            from panda3d.core import TextNode

            aspect2d = getattr(self.app, "aspect2d", None)
            if aspect2d is None:
                aspect2d = getattr(__import__("builtins"), "aspect2d", None)
            if aspect2d is None:
                return
            summary = self._town_focus_summary(frame or self._last_citizen_frame)
            self._last_town_focus_summary = dict(summary)
            if self.town_focus_summary_root is None:
                panel = DirectFrame(
                    parent=aspect2d,
                    frameSize=(-0.57, 0.57, -0.235, 0.235),
                    frameColor=(0.003, 0.012, 0.022, 0.92),
                    pos=(-1.18, 0.0, 0.62),
                    sortOrder=146,
                )
                panel.setTransparency(True)
                label = DirectLabel(
                    parent=panel,
                    text="",
                    text_align=TextNode.ALeft,
                    text_fg=(0.82, 1.0, 1.0, 0.96),
                    text_scale=0.024,
                    text_pos=(-0.53, 0.172),
                    frameColor=(0, 0, 0, 0),
                )
                accent = DirectFrame(parent=panel, frameSize=(-0.57, 0.57, 0.188, 0.235), frameColor=(0.18, 0.92, 1.0, 0.24))
                panel.setPythonTag("holoutopia_town_focus_label", label)
                panel.setPythonTag("holoutopia_town_focus_accent", accent)
                self.town_focus_summary_root = panel
            label = self.town_focus_summary_root.getPythonTag("holoutopia_town_focus_label")
            if label is not None:
                panel_text = self._format_town_focus_summary(summary)
                panel_key = f"{summary.get('town_id')}|{summary.get('clock')}|{summary.get('event_count')}|{summary.get('flow_count')}|{summary.get('town_pressure_percent')}|{summary.get('player_order_count')}|{summary.get('stabilized_event_count')}|{summary.get('improving_event_count')}|{summary.get('memory_count')}|{self._town_focus_state_revision_key()}"
                if panel_key != self._town_focus_panel_cache_key or panel_text != self._town_focus_panel_last_text:
                    label["text"] = panel_text
                    self._town_focus_panel_cache_key = panel_key
                    self._town_focus_panel_last_text = panel_text
                    self._town_focus_perf_stats["panel_text_updates"] = int(self._town_focus_perf_stats.get("panel_text_updates", 0) or 0) + 1
            self._create_or_update_tutorial_panel(mode="focus")
        except Exception as exc:
            self.error = f"town-focus-panel:{exc.__class__.__name__}:{exc}"

    def _town_focus_summary(self, frame: dict[str, Any] | None = None) -> dict[str, Any]:
        frame = frame if isinstance(frame, dict) else {}
        town_id = str(self.selected_town_id or "")
        town = self._town_records_for_selection().get(town_id, {"display_name": town_id})
        citizens = frame.get("citizens") if isinstance(frame.get("citizens"), dict) else {}
        local = {cid: data for cid, data in citizens.items() if isinstance(data, dict) and str(data.get("town_id") or "") == town_id}
        visits = {cid: data for cid, data in local.items() if isinstance(data, dict) and isinstance(data.get("civic_visit"), dict)}
        activities: dict[str, int] = {}
        for data in local.values():
            activity = str(data.get("activity_id") or data.get("action") or "unknown")
            activities[activity] = activities.get(activity, 0) + 1
        top_activities = sorted(activities.items(), key=lambda item: (-item[1], item[0]))[:3]
        recent = []
        for cid, data in sorted(visits.items())[:4]:
            recent.append(f"{data.get('display_name', cid)}: {data.get('visit_reason') or 'local errand'}")
        life = self._town_focus_life_snapshot(frame) if self._town_focus_active else {}
        clusters = life.get("clusters") if isinstance(life.get("clusters"), list) else []
        flows = life.get("flows") if isinstance(life.get("flows"), list) else []
        events = life.get("events") if isinstance(life.get("events"), list) else []
        event_lines = []
        for event in events[:3]:
            if not isinstance(event, dict):
                continue
            event_lines.append(f"{str(event.get('label') or 'Local event')} [{str(event.get('severity') or 'normal')}]")
        for cluster in clusters[:3]:
            if not isinstance(cluster, dict):
                continue
            event_lines.append(f"{_local_activity_label(str(cluster.get('activity') or 'local_activity'))} x{int(cluster.get('count') or 0)}")
        return {
            "town_id": town_id,
            "display_name": str(town.get("display_name") or town_id),
            "district_type": str(town.get("district_type") or ""),
            "clock": str(frame.get("clock") or self.current_clock()),
            "local_count": len(local),
            "visible_count": len(self._last_visible_citizens) if isinstance(self._last_visible_citizens, dict) else 0,
            "visit_count": len(visits),
            "top_activities": top_activities,
            "recent_visits": recent,
            "local_events": event_lines,
            "event_count": len(events),
            "flow_count": len(flows),
            "player_order_count": int(life.get("player_order_count", 0) or 0) if isinstance(life, dict) else 0,
            "event_memory_count": int(life.get("event_memory_count", len(self._town_focus_event_memory)) or 0) if isinstance(life, dict) else len(self._town_focus_event_memory),
            "event_outcome_count": int(life.get("event_outcome_count", len(self._town_focus_event_outcomes)) or 0) if isinstance(life, dict) else len(self._town_focus_event_outcomes),
            "town_pressure_percent": int(life.get("town_pressure_percent", 0) or 0) if isinstance(life, dict) else 0,
            "consequence": life.get("consequence") if isinstance(life.get("consequence"), dict) else dict(self._town_focus_consequence_memory.get(town_id, {})),
            "health_report": life.get("health_report") if isinstance(life.get("health_report"), dict) else self._town_focus_latest_health_report(town_id),
            "stabilized_event_count": int(life.get("stabilized_event_count", 0) or 0) if isinstance(life, dict) else 0,
            "improving_event_count": int(life.get("improving_event_count", 0) or 0) if isinstance(life, dict) else 0,
            "memory_count": int(life.get("memory_count", len(self._town_focus_npc_memory)) or 0) if isinstance(life, dict) else len(self._town_focus_npc_memory),
            "state_status": self._town_focus_state_status_line(),
            "schedule_state": "Runtime state records each visible NPC's current position and next destination; authored schedules still drive where they should go after leaving focus.",
        }

    def _town_focus_hud_bar(self, label: str, value: Any, *, width: int = 10, invert: bool = False) -> str:
        """Compact ASCII meter for the Town Focus HUD."""
        amount = self._clamp_town_focus_metric(value) / 100.0
        lit = int(round(max(0.0, min(1.0, amount)) * max(1, width)))
        if invert:
            lit = max(0, width - lit)
        return f"{label:<4} [{'|' * lit}{'.' * max(0, width - lit)}] {int(round(self._clamp_town_focus_metric(value))):02d}"

    def _format_town_focus_summary(self, summary: dict[str, Any]) -> str:
        title = str(summary.get("display_name") or "Town Focus")[:34]
        clock = str(summary.get("clock") or self.current_clock())
        activities = summary.get("top_activities") if isinstance(summary.get("top_activities"), list) else []
        activity_line = " / ".join(f"{str(name).replace('_', ' ').title()} x{count}" for name, count in activities[:2]) or "Quiet local cycle"
        local_events = summary.get("local_events") if isinstance(summary.get("local_events"), list) else []
        event_line = " / ".join(str(e)[:28] for e in local_events[:2]) if local_events else "No active local alert"
        consequence = summary.get("consequence") if isinstance(summary.get("consequence"), dict) else {}
        health_report = summary.get("health_report") if isinstance(summary.get("health_report"), dict) else {}
        grade = str(health_report.get("grade") or "?")
        score = int(health_report.get("score") or 0)
        trend = str(health_report.get("trend") or "steady")[:18]
        status = str(consequence.get("status") or health_report.get("status") or "stable").title()[:18]
        mood = str(consequence.get("mood") or health_report.get("mood") or "calm")[:18]
        need = str(consequence.get("dominant_need") or health_report.get("dominant_need") or "routine watch")[:34]
        next_step = str(health_report.get("next_step") or "watch local flow")[:46]
        pressure = int(consequence.get("pressure_percent") or summary.get("town_pressure_percent") or 0)
        supply = int(consequence.get("supply_percent") or 0)
        safety = int(consequence.get("safety_percent") or 0)
        morale = int(consequence.get("morale_percent") or 0)
        productivity = int(consequence.get("productivity_percent") or 0)
        glitch = int(consequence.get("glitch_risk_percent") or 0)
        markers = consequence.get("need_markers") if isinstance(consequence.get("need_markers"), list) else []
        marker_line = " / ".join(f"{str(m.get('label') or 'Need')} {int(m.get('value') or 0)}" for m in markers[:3] if isinstance(m, dict)) or "routine watch"
        return "\n".join([
            "TOWN FOCUS // LOCAL WATCH",
            f"{title}  {clock}   Health {grade} {score}% ({trend})",
            f"Status: {status} / {mood}   Need: {need}",
            self._town_focus_hud_bar("PRS", pressure) + "   " + self._town_focus_hud_bar("SUP", supply),
            self._town_focus_hud_bar("SAFE", safety) + "   " + self._town_focus_hud_bar("MOR", morale),
            self._town_focus_hud_bar("PROD", productivity) + "   " + self._town_focus_hud_bar("GLCH", glitch),
            f"Life: citizens {summary.get('local_count', 0)} / visible {summary.get('visible_count', 0)} / visits {summary.get('visit_count', 0)}",
            f"Sim: events {summary.get('event_count', 0)} / flows {summary.get('flow_count', 0)} / orders {summary.get('player_order_count', 0)} / stable {summary.get('stabilized_event_count', 0)}",
            f"Now: {event_line}",
            f"Beacons: {marker_line[:54]}",
            f"Next watcher step: {next_step}",
            str(summary.get("state_status") or self._town_focus_state_status_line())[:74],
            "Click event/citizen/building.  1 Help  2 Repair  3 Calm  4 Supplies.",
            "Enter/P first-person.  ESC/Backspace/0 returns.  F1 guide.",
        ])

    def _building_records_for_selection(self) -> dict[str, Any]:
        """Return a fresh-enough building highlight index for click selection."""
        clock = self.current_clock()
        if self._last_building_records and self._building_record_clock == clock:
            return self._last_building_records
        try:
            from holoutopia_building_inspector import build_highlight_index

            index = build_highlight_index(self.holoverse_root, clock=clock, danger_state=bool(self._danger_state))
            records = index.get("records") if isinstance(index.get("records"), dict) else {}
            self._last_building_records = dict(records)
            self._building_record_clock = clock
            return self._last_building_records
        except Exception as exc:
            self.error = f"building-index:{exc.__class__.__name__}:{exc}"
            return {}

    def _selection_pointer(self) -> tuple[float, float]:
        """Use the actual mouse position for click selection, falling back to screen center."""
        try:
            watcher = getattr(self.app, "mouseWatcherNode", None)
            if watcher is not None and watcher.hasMouse():
                mouse = watcher.getMouse()
                return float(mouse.getX()), float(mouse.getY())
        except Exception:
            pass
        return 0.0, 0.0

    def _score_screen_point(self, x: float, y: float, z: float, *, pointer: tuple[float, float] | None = None) -> tuple[float, float] | None:
        """Project a city-root point and return (screen_distance, depth)."""
        if self.city_root is None:
            return None
        try:
            from panda3d.core import Point2, Point3

            camera = getattr(self.app, "camera", None) or getattr(self.app, "cam", None)
            cam_lens = getattr(self.app, "camLens", None)
            if camera is None or cam_lens is None:
                return None
            target_x, target_y = pointer if pointer is not None else self._selection_pointer()
            p3 = camera.getRelativePoint(self.city_root, Point3(float(x), float(y), float(z)))
            p2 = Point2()
            if not cam_lens.project(p3, p2):
                return None
            sx = float(p2.getX()) - float(target_x)
            sy = float(p2.getY()) - float(target_y)
            return ((sx * sx + sy * sy) ** 0.5, max(1.0, abs(float(p3.getY()))))
        except Exception:
            return None

    def _try_select_world_from_camera(self) -> bool:
        """Overview clicks enter Town Focus; focused clicks inspect local buildings/citizens."""
        if self._runtime_blocked_by_scene_state():
            return False
        pointer = (0.0, 0.0) if self._first_person_active else self._selection_pointer()
        building_id = self._best_building_at_pointer(pointer)
        if not self._town_focus_active:
            if building_id:
                record = self._building_records_for_selection().get(building_id, {})
                town_id = str(record.get("town_id") or "") if isinstance(record, dict) else ""
                if town_id and self.enter_town_focus(town_id, source_building_id=building_id):
                    return True
            town_id = self._best_town_at_pointer(pointer)
            if town_id and self.enter_town_focus(town_id):
                return True
            return self._try_select_citizen_from_camera()
        if self._try_select_town_focus_activity_from_camera(pointer):
            return True
        if building_id and self.select_building(building_id):
            return True
        return self._try_select_citizen_from_camera()

    def _best_building_at_pointer(self, pointer: tuple[float, float]) -> str:
        """Find the building whose visible center is nearest to the click/crosshair."""
        records = self._building_records_for_selection()
        if not records:
            return ""
        best_id = ""
        best_score = 9999.0
        for rid, record in records.items():
            if not isinstance(record, dict):
                continue
            if self._town_focus_active and self.selected_town_id and str(record.get("town_id") or "") != str(self.selected_town_id):
                continue
            pos = record.get("world_position") if isinstance(record.get("world_position"), dict) else {}
            try:
                x = float(pos.get("x"))
                y = float(pos.get("y"))
            except Exception:
                continue
            massing = record.get("massing") if isinstance(record.get("massing"), dict) else {}
            try:
                z = max(6.0, min(86.0, float(massing.get("height_units", 18.0)) * 0.58))
            except Exception:
                z = 18.0
            scored = self._score_screen_point(x, y, z, pointer=pointer)
            if scored is None:
                continue
            screen_dist, depth = scored
            # Wider than the citizen hit zone: buildings are large game objects and
            # their visual center is only an approximation of the clicked face.
            if screen_dist > 0.285:
                continue
            score = screen_dist * 100.0 + depth * 0.0015
            if score < best_score:
                best_score = score
                best_id = str(rid)
        return best_id

    def _clear_building_selection_visuals(self) -> None:
        """Remove selected-building marker and corner site card when switching selection modes."""
        self.selected_building_id = ""
        self._last_building_gameplay_state = {}
        for attr in ("building_selection_root", "selection_summary_root"):
            node = getattr(self, attr, None)
            if node is not None:
                try:
                    node.destroy()
                except Exception:
                    try:
                        node.removeNode()
                    except Exception:
                        pass
            try:
                setattr(self, attr, None)
            except Exception:
                pass

    def _create_or_update_building_selection_marker(self, record: dict[str, Any]) -> None:
        """Draw a small visual halo over the selected building without rebuilding the city."""
        if self.city_root is None:
            return
        try:
            if self.building_selection_root is not None:
                try:
                    self.building_selection_root.removeNode()
                except Exception:
                    pass
                self.building_selection_root = None
            if not isinstance(record, dict):
                return
            pos = record.get("world_position") if isinstance(record.get("world_position"), dict) else {}
            x = float(pos.get("x", 0.0))
            y = float(pos.get("y", 0.0))
            massing = record.get("massing") if isinstance(record.get("massing"), dict) else {}
            height = max(8.0, min(96.0, float(massing.get("height_units", 18.0) or 18.0)))
            radius = max(14.0, min(36.0, 10.0 + height * 0.18))
            from panda3d.core import LineSegs, TextNode

            root = self.city_root.attachNewNode("holoutopia_selected_building_marker")
            root.setLightOff(True)
            root.setPythonTag("holoutopia_selected_building_id", str(record.get("id") or ""))
            self.building_selection_root = root
            seg = LineSegs("selected_building_halo")
            seg.setThickness(3.2)
            seg.setColor(1.0, 0.36, 0.92, 0.94)
            z = height + 7.5
            for idx in range(65):
                a = math.tau * idx / 64.0
                px = x + math.cos(a) * radius
                py = y + math.sin(a) * radius
                if idx == 0:
                    seg.moveTo(px, py, z)
                else:
                    seg.drawTo(px, py, z)
            # Four downward corner ticks read better than a debug circle alone.
            for idx in range(4):
                a = math.tau * idx / 4.0 + math.pi / 4.0
                px = x + math.cos(a) * radius
                py = y + math.sin(a) * radius
                seg.moveTo(px, py, z)
                seg.drawTo(px, py, max(2.0, height * 0.35))
            root.attachNewNode(seg.create()).setLightOff(True)
            label = TextNode("selected_building_label")
            label.setAlign(TextNode.ACenter)
            label.setText(str(record.get("display_name") or "Selected Building"))
            label.setTextColor(1.0, 0.72, 1.0, 0.92)
            label_node = root.attachNewNode(label)
            label_node.setScale(6.2)
            label_node.setPos(x, y, z + 5.5)
            try:
                label_node.setBillboardPointEye()
            except Exception:
                label_node.setHpr(0, -62, 0)
            label_node.setLightOff(True)
        except Exception as exc:
            self.error = f"building-marker:{exc.__class__.__name__}:{exc}"

    def _create_or_update_building_site_card(self, record: dict[str, Any], payload: dict[str, Any] | None = None) -> None:
        """Show a compact game-facing selected-site card in a 16:9 corner."""
        try:
            if self.selection_summary_root is not None:
                try:
                    self.selection_summary_root.destroy()
                except Exception:
                    try:
                        self.selection_summary_root.removeNode()
                    except Exception:
                        pass
                self.selection_summary_root = None
            if not isinstance(record, dict):
                return
            from direct.gui.DirectGui import DirectFrame, DirectLabel
            from panda3d.core import TextNode
            from holoutopia_building_gameplay import derive_building_gameplay_state

            aspect2d = getattr(self.app, "aspect2d", None)
            if aspect2d is None:
                aspect2d = getattr(__import__("builtins"), "aspect2d", None)
            if aspect2d is None:
                return
            state = derive_building_gameplay_state(
                record,
                clock=str((payload or {}).get("clock") or self.current_clock()),
                danger_state=bool((payload or {}).get("danger_state", self._danger_state)),
            )
            self._last_building_gameplay_state = dict(state)
            aspect = self._current_aspect_ratio()
            frame = DirectFrame(
                parent=aspect2d,
                frameSize=(-0.47, 0.47, -0.155, 0.155),
                frameColor=(0.006, 0.018, 0.030, 0.88),
                pos=(max(0.45, aspect - 0.55), 0.0, -0.705),
                sortOrder=147,
            )
            frame.setTransparency(True)
            display_name = str(record.get("display_name") or "Selected Building")
            if len(display_name) > 34:
                display_name = display_name[:31].rstrip() + "..."
            text = "\n".join([
                "SELECTED SITE",
                display_name,
                f"{state.get('state_label', 'Unknown')}  •  {state.get('priority_label', 'Stable')}  •  {state.get('risk_label', 'Secure')}",
                f"Active {state.get('active_citizen_count', 0)}  Workers {state.get('worker_count', 0)}  Value {state.get('civic_value', 0)}",
                "Open panel tabs: Overview / Status / People / Activity",
            ])
            label = DirectLabel(
                parent=frame,
                text=text,
                text_align=TextNode.ALeft,
                text_fg=(0.86, 1.0, 1.0, 0.96),
                text_scale=0.029,
                text_pos=(-0.43, 0.097),
                frameColor=(0, 0, 0, 0),
            )
            accent = DirectFrame(
                parent=frame,
                frameSize=(-0.47, 0.47, 0.124, 0.155),
                frameColor=(1.0, 0.34, 0.94, 0.36),
            )
            self.selection_summary_root = frame
            # Keep references alive in DirectGUI's Python-side scene graph.
            frame.setPythonTag("holoutopia_site_card_label", label)
            frame.setPythonTag("holoutopia_site_card_accent", accent)
            frame.setPythonTag("holoutopia_building_gameplay_state", state)
        except Exception as exc:
            self.error = f"building-site-card:{exc.__class__.__name__}:{exc}"

    def _current_aspect_ratio(self) -> float:
        try:
            win = getattr(self.app, "win", None)
            if win is not None and int(win.getYSize()) > 0:
                return max(1.0, float(win.getXSize()) / float(win.getYSize()))
        except Exception:
            pass
        return 16.0 / 9.0

    def _try_select_citizen_from_camera(self, pointer: tuple[float, float] | None = None) -> bool:
        """Pick the robot closest to the click/crosshair and show its task queue panel."""
        if not self._marker_nodes:
            return False
        if self._runtime_blocked_by_scene_state():
            return False
        try:
            from panda3d.core import Point2
            camera = getattr(self.app, "camera", None) or getattr(self.app, "cam", None)
            cam_lens = getattr(self.app, "camLens", None)
            render = getattr(self.app, "render", None)
            if camera is None or cam_lens is None or render is None:
                return self._select_nearest_marker_fallback()
            pointer_x, pointer_y = pointer if pointer is not None else self._selection_pointer()
            best_id = ""
            best_score = 9999.0
            for cid, node in list(self._marker_nodes.items()):
                try:
                    if node.isHidden():
                        continue
                    p3 = camera.getRelativePoint(render, node.getPos(render))
                    p2 = Point2()
                    if not cam_lens.project(p3, p2):
                        continue
                    sx = float(p2.getX()) - pointer_x
                    sy = float(p2.getY()) - pointer_y
                    screen_dist = (sx * sx + sy * sy) ** 0.5
                    if screen_dist > 0.32:
                        continue
                    depth = max(1.0, abs(float(p3.getY())))
                    score = screen_dist * 100.0 + depth * 0.002
                    if score < best_score:
                        best_score = score
                        best_id = str(cid)
                except Exception:
                    continue
            if best_id:
                return self.select_citizen(best_id)
            return self._select_nearest_marker_fallback(max_distance=160.0)
        except Exception:
            return self._select_nearest_marker_fallback()

    def _select_nearest_marker_fallback(self, *, max_distance: float = 220.0) -> bool:
        """Fallback inspector selection used by offscreen tests or unusual cameras."""
        try:
            camera = getattr(self.app, "camera", None) or getattr(self.app, "cam", None)
            render = getattr(self.app, "render", None)
            if camera is None or render is None:
                first = next(iter(self._marker_nodes.keys()), "")
                return self.select_citizen(first) if first else False
            cpos = camera.getPos(render)
            best_id = ""
            best_dist = float(max_distance) ** 2
            for cid, node in list(self._marker_nodes.items()):
                try:
                    d = (node.getPos(render) - cpos).lengthSquared()
                    if d < best_dist:
                        best_dist = d
                        best_id = str(cid)
                except Exception:
                    pass
            return self.select_citizen(best_id) if best_id else False
        except Exception:
            return False


def _local_activity_label(activity_id: str) -> str:
    activity = str(activity_id or "local_activity").lower()
    if "errand" in activity or "visit" in activity:
        return "Visitor Errand"
    if "meal" in activity or "social" in activity:
        return "Social Stop"
    if "work" in activity or "shift" in activity:
        return "Work Crew"
    if "hobby" in activity or "personal" in activity:
        return "Personal Time"
    if "commute" in activity or "return" in activity:
        return "Transit Flow"
    if "danger" in activity or "security" in activity:
        return "Security Response"
    return activity.replace("_", " ").title()


def load_runtime_config(holoverse_root: Path | str | None = None) -> dict[str, Any]:
    root = Path(holoverse_root or Path(__file__).resolve().parent).resolve()
    candidates: list[Path] = []
    if root.name.lower() in {"holoverse", "holoutopia"}:
        # Support both the live module root (.../data/HoloUtopia) and the
        # standalone package root (.../HoloUtopia) used by local validators.
        candidates.append(root / "data" / "database" / "utopia" / "runtime" / "holoutopia_runtime_bridge.json")
        candidates.append(root.parent / "database" / "utopia" / "runtime" / "holoutopia_runtime_bridge.json")
    candidates.append(root / "database" / "utopia" / "runtime" / "holoutopia_runtime_bridge.json")
    seen: set[Path] = set()
    for path in candidates:
        if path in seen:
            continue
        seen.add(path)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            continue
        if isinstance(data, dict):
            return data
    return _default_runtime_config()


def build_runtime_summary(holoverse_root: Path | str | None = None) -> HoloUtopiaRuntimeSummary:
    from holoutopia_town_blocks import list_neighborhood_ids, list_town_ids, load_city_atlas
    from holoutopia_citizen_simulation import load_simulation_inputs, simulate_city_at_time

    config = load_runtime_config(holoverse_root)
    inputs = load_simulation_inputs(holoverse_root)
    atlas = load_city_atlas(holoverse_root)
    frame = simulate_city_at_time(holoverse_root, str(config.get("citizen_runtime", {}).get("sample_clock_on_start", "08:00")), inputs=inputs)
    citizens = inputs.get("citizen_manifest", {}).get("citizens", [])
    placement = config.get("placement", {}) if isinstance(config.get("placement"), dict) else {}
    runtime = config.get("citizen_runtime", {}) if isinstance(config.get("citizen_runtime"), dict) else {}
    controls = config.get("controls", {}) if isinstance(config.get("controls"), dict) else {}
    integration = config.get("world_integration", {}) if isinstance(config.get("world_integration"), dict) else {}
    return HoloUtopiaRuntimeSummary(
        runtime_id=str(config.get("id") or DEFAULT_RUNTIME_ID),
        enabled_by_default=bool(config.get("enabled_by_default", True)),
        town_count=len(list_town_ids(holoverse_root)) or len(atlas.get("towns", [])),
        neighborhood_count=len(list_neighborhood_ids(holoverse_root)),
        citizen_count=len(citizens if isinstance(citizens, list) else []),
        schedule_frame_citizens=int(frame.get("citizen_count", 0)),
        placement_scale=_safe_float(placement.get("scale"), 0.55),
        city_day_seconds=_safe_float(runtime.get("city_day_seconds"), 1440.0),
        overlay_key=str(controls.get("toggle_overlay_key") or "u"),
        danger_key=str(controls.get("danger_state_key") or "shift-u"),
        integration_mode=str(integration.get("mode") or "world_parented_city_layer"),
    )


def install_holoutopia_runtime(app: Any, holoverse_root: Path | str | None = None, *, enabled: bool = True) -> HoloUtopiaGameRuntime:
    """Create and install the runtime bridge into a HoloVerse ShowBase app."""
    runtime = HoloUtopiaGameRuntime(app, holoverse_root, enabled=enabled)
    return runtime.install()



def _virtual_residential_street_position(cid: str, citizen: dict[str, Any]) -> tuple[float, float]:
    """Place sampled Residential residents on streets, not inside/above buildings."""
    slot = int(_safe_float(citizen.get("schedule_index"), 0.0))
    activity = str(citizen.get("activity_id") or "").lower()
    # Local city-space coordinates for the Residential west gate and porch streets.
    outbound_path = [
        (-224.0, 672.0), (-205.0, 672.0), (-186.0, 672.0), (-167.0, 672.0),
        (-148.0, 672.0), (-129.0, 672.0), (-110.0, 672.0), (-91.0, 672.0),
        (-72.0, 672.0), (-53.0, 672.0), (-34.0, 672.0), (-15.0, 672.0),
        (4.0, 672.0), (23.0, 672.0), (42.0, 672.0), (61.0, 672.0),
        (80.0, 672.0), (99.0, 672.0), (118.0, 672.0), (137.0, 672.0),
    ]
    plaza_loop = [
        (-196.0, 640.0), (-158.0, 642.0), (-120.0, 645.0), (-82.0, 650.0),
        (-44.0, 656.0), (-6.0, 662.0), (32.0, 660.0), (70.0, 653.0),
        (108.0, 646.0), (70.0, 632.0), (32.0, 626.0), (-6.0, 628.0),
        (-44.0, 634.0), (-82.0, 638.0), (-120.0, 636.0), (-158.0, 632.0),
    ]
    if activity in {"return_home", "home_recharge"}:
        points = list(reversed(outbound_path))
    elif activity in {"replenish", "off_district_work"}:
        points = plaza_loop
    else:
        points = outbound_path
    x, y = points[slot % len(points)]
    # Tiny deterministic per-resident shuffle keeps people from looking gridded.
    x += (_stable_fraction(cid, 1.13) - 0.5) * 5.5
    y += (_stable_fraction(cid, 2.17) - 0.5) * 4.0
    return float(x), float(y)

def _node_grid_to_city_render_xy(holoverse_root: Path | str | None, town_id: str, grid: tuple[float, float]) -> tuple[float, float]:
    from holoutopia_town_blocks import city_frame_metrics, load_city_atlas

    atlas = load_city_atlas(holoverse_root)
    metrics = city_frame_metrics(atlas)
    grid_w = float(metrics["grid_w"])
    grid_h = float(metrics["grid_h"])
    block_size = float(metrics["block_size"])
    town_grid = (0, 0)
    for entry in atlas.get("towns", []):
        if isinstance(entry, dict) and str(entry.get("town_id")) == str(town_id):
            raw = entry.get("city_grid", [0, 0])
            town_grid = (int(raw[0]), int(raw[1]))
            break
    town_origin_x = town_grid[0] * float(metrics["frame_w"])
    town_origin_y = town_grid[1] * float(metrics["frame_h"])
    gx, gy = float(grid[0]), float(grid[1])
    x = town_origin_x + (gx - (grid_w - 1.0) * 0.5) * block_size
    y = town_origin_y + ((grid_h - 1.0) * 0.5 - gy) * block_size
    return x, y


def _robot_marker_config(config: dict[str, Any]) -> dict[str, Any]:
    runtime = config.get("citizen_runtime", {}) if isinstance(config.get("citizen_runtime"), dict) else {}
    marker = runtime.get("person_marker") if isinstance(runtime.get("person_marker"), dict) else {}
    if not marker:
        marker = runtime.get("robot_marker") if isinstance(runtime.get("robot_marker"), dict) else {}
    return {
        "style": str(marker.get("style") or "tiny_3d_people"),
        "height": max(3.0, min(14.0, _safe_float(marker.get("height_units"), 7.5))),
        "width": max(0.75, min(5.0, _safe_float(marker.get("width_units"), 1.8))),
        "depth": max(0.55, min(4.0, _safe_float(marker.get("depth_units"), 1.2))),
        "body_line_thickness": max(0.45, min(3.0, _safe_float(marker.get("body_line_thickness"), 1.35))),
        "limb_line_thickness": max(0.45, min(3.0, _safe_float(marker.get("limb_line_thickness"), 1.15))),
        "label_scale": max(0.0, min(8.0, _safe_float(marker.get("label_scale"), 0.0))),
        "show_name_label": bool(marker.get("show_name_label", False)),
        "show_contact_pad": bool(marker.get("show_contact_pad", False)),
        "same_node_spread_radius": max(0.0, min(34.0, _safe_float(marker.get("same_node_spread_radius"), 10.0))),
    }


def _stable_fraction(text: str, salt: float = 0.0) -> float:
    raw = str(text or "") + f":{salt:.3f}"
    total = 0
    for idx, ch in enumerate(raw):
        total = (total * 131 + (idx + 17) * ord(ch)) % 1000003
    return (total % 10000) / 10000.0


def _dist2(a: tuple[float, float], b: tuple[float, float]) -> float:
    return (float(a[0]) - float(b[0])) ** 2 + (float(a[1]) - float(b[1])) ** 2


def _line_box(seg: Any, x0: float, y0: float, z0: float, x1: float, y1: float, z1: float) -> None:
    corners = [
        (x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
        (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1),
    ]
    edges = ((0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4), (0, 4), (1, 5), (2, 6), (3, 7))
    for a, b in edges:
        seg.moveTo(*corners[a])
        seg.drawTo(*corners[b])



def _service_glyph_color(glyph: str, citizen: dict[str, Any]) -> tuple[float, float, float, float]:
    g = str(glyph or "").lower()
    district = str(citizen.get("town_id") or "").lower()
    if "water" in g or "harbor" in district:
        return (0.38, 0.92, 1.0, 0.84)
    if "market" in g or "market" in district:
        return (1.0, 0.82, 0.28, 0.86)
    if "shield" in g or "security" in district:
        return (0.48, 1.0, 0.44, 0.86)
    if "warning" in g or "glitch" in district:
        return (1.0, 0.25, 0.34, 0.86)
    if "data" in g or "archive" in district:
        return (0.70, 0.50, 1.0, 0.86)
    if "wrench" in g or "industrial" in district:
        return (1.0, 0.58, 0.20, 0.86)
    return (0.30, 1.0, 0.94, 0.84)


def _draw_service_glyph(seg: Any, glyph: str) -> None:
    g = str(glyph or "node_tick").lower()
    if g == "market_diamond":
        pts = [(0, 0, 1.7), (1.5, 0, 0), (0, 0, -1.7), (-1.5, 0, 0), (0, 0, 1.7)]
        seg.moveTo(*pts[0])
        for p in pts[1:]:
            seg.drawTo(*p)
        seg.moveTo(-0.7, 0, 0)
        seg.drawTo(0.7, 0, 0)
    elif g == "water_drop":
        pts = [(0, 0, 2.0), (1.2, 0, 0.3), (0.75, 0, -1.2), (0, 0, -1.7), (-0.75, 0, -1.2), (-1.2, 0, 0.3), (0, 0, 2.0)]
        seg.moveTo(*pts[0])
        for p in pts[1:]:
            seg.drawTo(*p)
    elif g == "shield_scan":
        pts = [(-1.3, 0, 1.3), (1.3, 0, 1.3), (1.0, 0, -0.8), (0, 0, -1.8), (-1.0, 0, -0.8), (-1.3, 0, 1.3)]
        seg.moveTo(*pts[0])
        for p in pts[1:]:
            seg.drawTo(*p)
        seg.moveTo(-1.8, 0, 0.2)
        seg.drawTo(1.8, 0, 0.2)
    elif g == "warning_cross":
        seg.moveTo(-1.4, 0, 1.4)
        seg.drawTo(1.4, 0, -1.4)
        seg.moveTo(1.4, 0, 1.4)
        seg.drawTo(-1.4, 0, -1.4)
        seg.moveTo(0, 0, 1.8)
        seg.drawTo(0, 0, -1.8)
    elif g == "wrench":
        seg.moveTo(-1.4, 0, -1.2)
        seg.drawTo(1.0, 0, 1.2)
        seg.moveTo(0.7, 0, 1.5)
        seg.drawTo(1.4, 0, 0.8)
        seg.moveTo(0.55, 0, 1.05)
        seg.drawTo(1.05, 0, 0.55)
    elif g == "data_bars":
        for i, h in enumerate((1.0, 1.8, 1.35)):
            x = -1.1 + i * 1.1
            seg.moveTo(x, 0, -1.4)
            seg.drawTo(x, 0, -1.4 + h)
        seg.moveTo(-1.5, 0, -1.4)
        seg.drawTo(1.5, 0, -1.4)
    elif g == "signal_arc":
        for r in (0.8, 1.4, 2.0):
            first = True
            for k in range(9):
                a = -0.65 + 1.3 * k / 8.0
                p = (math.sin(a) * r, 0.0, math.cos(a) * r - 1.0)
                if first:
                    seg.moveTo(*p); first = False
                else:
                    seg.drawTo(*p)
    else:
        # pulse_ring / node_tick fallback: compact plus and small square tick.
        seg.moveTo(-1.5, 0, 0)
        seg.drawTo(1.5, 0, 0)
        seg.moveTo(0, 0, -1.5)
        seg.drawTo(0, 0, 1.5)
        seg.moveTo(-0.8, 0, 0.8)
        seg.drawTo(0.8, 0, 0.8)
        seg.drawTo(0.8, 0, -0.8)
        seg.drawTo(-0.8, 0, -0.8)
        seg.drawTo(-0.8, 0, 0.8)


def _activity_color(activity_id: str, danger: bool, location_mode: str) -> tuple[float, float, float, float]:
    if danger:
        return (1.0, 0.18, 0.12, 0.96)
    if location_mode == "private_home_hidden":
        return (0.45, 0.78, 1.0, 0.50)
    activity = str(activity_id).lower()
    if "work" in activity or "shift" in activity:
        return (0.35, 1.0, 0.35, 0.92)
    if "simulation" in activity or "matrixcore" in activity:
        return (0.62, 0.38, 1.0, 0.96)
    if "meal" in activity or "social" in activity or "friend" in activity:
        return (1.0, 0.42, 0.92, 0.92)
    if "commute" in activity or "errand" in activity:
        return (0.25, 0.88, 1.0, 0.92)
    if "hobby" in activity:
        return (1.0, 0.85, 0.30, 0.92)
    if "sleep" in activity or "home" in activity:
        return (0.60, 0.72, 1.0, 0.70)
    return (0.88, 0.96, 1.0, 0.88)


def _safe_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _default_runtime_config() -> dict[str, Any]:
    return {
        "schema": 1,
        "id": DEFAULT_RUNTIME_ID,
        "enabled_by_default": True,
        "placement": {"anchor_city_grid": [1, 1], "scale": 0.55, "z_offset": 0.25, "center_anchor_at_world_origin": True},
        "render_layers": {"city_world_atlas_style": True, "city_3d_massing": True, "neighborhood_overlays": True, "activity_cluster_props": True, "central_core_overlay": True, "citizen_markers": True, "service_operation_glyphs": True, "citizen_dialogue_bubbles": True, "status_label": True, "watch_mode_panel": True, "watch_focus_guides": True, "inspector_panels": True},
        "citizen_runtime": {"city_day_seconds": 1440.0, "update_interval_seconds": 1.15, "sample_clock_on_start": "06:30", "max_visible_citizens": 20, "show_virtual_population_representatives": True, "max_outdoor_population_per_district": 20, "person_marker": {"style": "tiny_3d_people", "height_units": 7.5, "same_node_spread_radius": 10.0, "show_contact_pad": False, "show_name_label": False, "activity_pose_animation": True}, "citizen_dialogue": {"enabled": True, "bubble_scale": 2.35, "max_card_width": 18.0, "source": "dialogue/citizen_dialogue_rules.json", "watch_log_enabled": True, "same_day_no_repeat": True}},
        "performance": {"facade_pulse_enabled": True, "facade_pulse_interval_seconds": 0.10, "facade_pulse_nodes_per_tick": 256, "notes": "Pass 58: pulse glow updates are batched instead of touching every visual node every frame."},
        "panels": {"default_snap": "left", "max_open_panels": 4, "keep_crosshair_clear": True, "snap_edges": ["left", "right", "top", "bottom"]},
        "controls": {"toggle_overlay_key": "u", "danger_state_key": "shift-u", "inspect_citizen_key": "mouse1", "close_panel_key": "x", "focus_selected_key": "f", "cycle_view_key": "v", "mouse_look_button": "mouse3", "wheel_zoom": True, "tutorial_toggle_key": "f1", "tutorial_alt_toggle_key": "shift-h", "tutorial_visible_by_default": True},
        "safety": {"writes_authored_data": False, "writes_runtime_logs": False, "adds_collision": False, "touches_artifact_routes": False},
    }
