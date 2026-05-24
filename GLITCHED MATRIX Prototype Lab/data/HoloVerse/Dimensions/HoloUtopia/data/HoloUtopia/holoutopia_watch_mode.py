"""Watch/Director mode helpers for HoloUtopia.

This pass keeps the original goal in view: a living AI city that can be
watched from above before the player later joins it from street level.  The
panel is read-only, collisionless, and derived from runtime simulation state.
It does not write logs or authored city data.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any


def build_watch_snapshot(holoverse_root: Path | str | None = None, clock: str = "18:15", *, frame: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return a compact, JSON-safe city oversight snapshot."""
    if frame is None:
        from holoutopia_citizen_simulation import simulate_city_at_time
        frame = simulate_city_at_time(holoverse_root, clock)
    clock_text = str(frame.get("clock") or clock or "00:00")
    pop_model = frame.get("residential_population_model") if isinstance(frame.get("residential_population_model"), dict) else {}
    activity_model = pop_model.get("district_activity_model") if isinstance(pop_model.get("district_activity_model"), dict) else {}
    activity_people = pop_model.get("visible_activity_citizens") if isinstance(pop_model.get("visible_activity_citizens"), dict) else {}
    residential_people = pop_model.get("visible_outdoor_citizens") if isinstance(pop_model.get("visible_outdoor_citizens"), dict) else {}
    visible_people: dict[str, Any] = {**residential_people, **activity_people}
    dialogue_state = frame.get("citizen_dialogue_state") if isinstance(frame.get("citizen_dialogue_state"), dict) else {}
    dialogue_bubbles = dialogue_state.get("active_bubbles") if isinstance(dialogue_state.get("active_bubbles"), list) else []
    try:
        from holoutopia_citizen_dialogue import format_dialogue_log_lines
        recent_talk = format_dialogue_log_lines(dialogue_state, max_lines=3) if dialogue_state else []
    except Exception:
        recent_talk = []
    dialogue_counts = dialogue_state.get("dialogue_category_counts") if isinstance(dialogue_state.get("dialogue_category_counts"), dict) else {}

    cluster_counts: Counter[str] = Counter()
    motive_counts: Counter[str] = Counter()
    stage_counts: Counter[str] = Counter()
    pose_counts: Counter[str] = Counter()
    commute_count = 0
    work_count = 0
    activity_count = 0
    # Cluster/state readouts focus on public district activity reps so home/commute
    # samples do not pollute the panel with unknown/unassigned labels.
    panel_people = activity_people if activity_people else visible_people
    for citizen in panel_people.values():
        if not isinstance(citizen, dict):
            continue
        cluster = str(citizen.get("activity_cluster_id") or citizen.get("commute_stage") or "unassigned")
        cluster_counts[cluster] += 1
        motive = str(citizen.get("motive") or "unknown")
        motive_counts[motive] += 1
        stage = str(citizen.get("activity_stage") or citizen.get("personal_phase") or "unknown")
        stage_counts[stage] += 1
        pose = str(citizen.get("activity_pose") or "default")
        pose_counts[pose] += 1
        if bool(citizen.get("commute_flow_representative")):
            commute_count += 1
        if motive == "work":
            work_count += 1
        if motive in {"activity", "replenish"}:
            activity_count += 1

    top_clusters = [
        {"id": cid, "label": _friendly_cluster_label(cid), "count": count}
        for cid, count in cluster_counts.most_common(5)
    ]
    top_stages = [
        {"id": sid, "label": _friendly_stage_label(sid), "count": count}
        for sid, count in stage_counts.most_common(4)
    ]
    service_counts: Counter[str] = Counter()
    district_service_counts: Counter[str] = Counter()
    for citizen in panel_people.values():
        if not isinstance(citizen, dict) or not bool(citizen.get("functional_service_assignment")):
            continue
        service_counts[str(citizen.get("service_short_label") or citizen.get("service_building_name") or "Service")] += 1
        district_service_counts[str(citizen.get("activity_district_display_name") or citizen.get("town_id") or "District")] += 1
    top_services = [
        {"label": label, "count": count}
        for label, count in service_counts.most_common(4)
    ]
    top_service_districts = [
        {"label": label, "count": count}
        for label, count in district_service_counts.most_common(4)
    ]
    try:
        from holoutopia_service_behaviors import build_service_operation_summary
        service_operation_summary = build_service_operation_summary(panel_people)
    except Exception:
        service_operation_summary = {"service_operation_count": 0, "top_operations": [], "top_outputs": []}
    adventure_state = activity_model.get("adventure_simulation_state") if isinstance(activity_model.get("adventure_simulation_state"), dict) else {}
    if not adventure_state:
        try:
            from holoutopia_adventure_simulation import build_adventure_simulation_state
            adventure_state = build_adventure_simulation_state(holoverse_root, clock_text, visible_citizens=activity_people, world_population=_safe_int(pop_model.get("world_population"), 1000))
        except Exception:
            adventure_state = {"match_active": False, "observe_available": False, "watch_line": "Adventure: unavailable"}
    join_target = _choose_join_target(pop_model, top_clusters, commute_count)
    if bool(adventure_state.get("observe_available")):
        join_target = {"label": "Active Core Ring Adventure", "mode": "observe_embedded_core_ring_adventure"}
    focus_target: dict[str, Any] = {}
    try:
        from holoutopia_watch_focus import build_watch_focus_state
        focus_state = build_watch_focus_state(holoverse_root, clock_text, frame=frame)
        focus_citizen = focus_state.get("focus_citizen") if isinstance(focus_state.get("focus_citizen"), dict) else {}
        focus_cluster = focus_state.get("focus_cluster") if isinstance(focus_state.get("focus_cluster"), dict) else {}
        focus_target = {
            "representative_label": str(focus_citizen.get("representative_label") or "Representative"),
            "activity_label": str(focus_citizen.get("activity_label") or "observing city"),
            "cluster_label": str(focus_cluster.get("label") or "Central Simulation Hub"),
            "street_safe": bool(focus_citizen.get("street_safe", True)),
        }
    except Exception:
        focus_target = {"representative_label": "Representative", "activity_label": "watching city", "cluster_label": "Central Simulation Hub", "street_safe": True}
    flow_state = _resolve_flow_state(str(pop_model.get("phase") or ""), commute_count, work_count, activity_count)
    world_population = _safe_int(pop_model.get("world_population"), _safe_int(frame.get("world_population"), 0))
    max_visible = _safe_int(activity_model.get("max_visible_activity_representatives_per_district"), _safe_int(pop_model.get("max_outdoor_population_per_district"), 20))
    visible_total = len(visible_people)
    active_district = str(activity_model.get("active_district_id") or pop_model.get("activity_district_id") or "central_core_civic_ring")
    return {
        "schema": 1,
        "id": "holoutopia_watch_snapshot_v1",
        "clock": clock_text,
        "mode": "watch_over_city",
        "initial_goal": "watch_over_living_ai_city_then_join_in_later",
        "watch_mode_active": True,
        "join_hook_ready": True,
        "join_mode_active": False,
        "active_district_id": active_district,
        "active_district_label": _friendly_district_label(active_district),
        "world_population": world_population,
        "visible_total": visible_total,
        "visible_cap": max_visible,
        "activity_visible_count": len(activity_people),
        "outdoor_population": _safe_int(pop_model.get("outdoor_population"), 0),
        "average_energy_percent": _safe_int(pop_model.get("average_energy_percent"), 0),
        "phase": str(pop_model.get("phase") or "unknown"),
        "phase_label": _friendly_stage_label(str(pop_model.get("phase") or "unknown")),
        "flow_state": flow_state,
        "counts": {
            "commuting": commute_count,
            "working": work_count,
            "activity_or_replenish": activity_count,
            "home_garrison_virtual": max(0, world_population - visible_total),
        },
        "top_clusters": top_clusters,
        "top_stages": top_stages,
        "motive_counts": dict(sorted(motive_counts.items())),
        "pose_counts": dict(sorted(pose_counts.items())),
        "join_target": join_target,
        "watch_focus_target": focus_target,
        "dialogue_active_count": len(dialogue_bubbles),
        "dialogue_recent_lines": recent_talk,
        "dialogue_category_counts": dialogue_counts,
        "service_activity_count": sum(service_counts.values()),
        "top_services": top_services,
        "top_service_districts": top_service_districts,
        "service_operation_summary": service_operation_summary,
        "top_service_operations": service_operation_summary.get("top_operations", []) if isinstance(service_operation_summary, dict) else [],
        "top_service_outputs": service_operation_summary.get("top_outputs", []) if isinstance(service_operation_summary, dict) else [],
        "adventure_simulation": adventure_state,
        "adventure_active": bool(adventure_state.get("match_active")) if isinstance(adventure_state, dict) else False,
        "adventure_observe_available": bool(adventure_state.get("observe_available")) if isinstance(adventure_state, dict) else False,
        "safety": {
            "read_only": True,
            "collisionless_panel": True,
            "no_authored_data_writes": True,
            "no_route_changes": True,
            "visible_citizens_street_safe": True,
            "garrison_inside_buildings_is_virtual": True,
        },
    }


def format_watch_lines(snapshot: dict[str, Any], *, max_lines: int = 10) -> list[str]:
    """Return readable panel lines with no raw debug IDs."""
    counts = snapshot.get("counts") if isinstance(snapshot.get("counts"), dict) else {}
    clusters = snapshot.get("top_clusters") if isinstance(snapshot.get("top_clusters"), list) else []
    stages = snapshot.get("top_stages") if isinstance(snapshot.get("top_stages"), list) else []
    cluster_text = ", ".join(f"{str(c.get('label'))}: {int(c.get('count') or 0)}" for c in clusters[:3] if isinstance(c, dict) and str(c.get('label') or "").lower() != "unassigned") or "activity clusters distributed"
    stage_text = ", ".join(f"{str(s.get('label'))}: {int(s.get('count') or 0)}" for s in stages[:2] if isinstance(s, dict) and str(s.get('label') or "").lower() != "unknown") or "settled"
    target = snapshot.get("join_target") if isinstance(snapshot.get("join_target"), dict) else {}
    focus = snapshot.get("watch_focus_target") if isinstance(snapshot.get("watch_focus_target"), dict) else {}
    focus_line = f"Focus cam: {focus.get('representative_label', 'Representative')} @ {focus.get('cluster_label', 'Central Simulation Hub')}"
    talk_lines = snapshot.get("dialogue_recent_lines") if isinstance(snapshot.get("dialogue_recent_lines"), list) else []
    talk_text = " | ".join(str(line) for line in talk_lines[:2]) if talk_lines else "quiet / no nearby pair"
    services = snapshot.get("top_services") if isinstance(snapshot.get("top_services"), list) else []
    service_text = ", ".join(f"{str(s.get('label'))}: {int(s.get('count') or 0)}" for s in services[:3] if isinstance(s, dict)) or "services routing idle"
    operations = snapshot.get("top_service_operations") if isinstance(snapshot.get("top_service_operations"), list) else []
    operation_text = ", ".join(f"{str(o.get('label'))}: {int(o.get('count') or 0)}" for o in operations[:2] if isinstance(o, dict)) or "service actions idle"
    adventure = snapshot.get("adventure_simulation") if isinstance(snapshot.get("adventure_simulation"), dict) else {}
    adventure_text = str(adventure.get("watch_line") or "Adventure: idle")
    click_text = "Goal: watch over now -> click Core: observe Core Ring action" if bool(adventure.get("observe_available")) else "Goal: watch over now -> click Core: no active Core Ring action"
    lines = [
        "HOLOUTOPIA WATCH MODE",
        f"Clock {snapshot.get('clock')} | Pop {snapshot.get('world_population')} | Visible {snapshot.get('visible_total')} | Activity {snapshot.get('activity_visible_count')}/{snapshot.get('visible_cap')}",
        f"Focus: {snapshot.get('active_district_label')} | {snapshot.get('flow_state')}",
        f"Phase: {snapshot.get('phase_label')} | Energy {snapshot.get('average_energy_percent')}%",
        f"Flow: commute {counts.get('commuting', 0)} | work {counts.get('working', 0)} | activity {counts.get('activity_or_replenish', 0)}",
        adventure_text,
        f"Talk: {talk_text}",
        f"Services: {service_text}",
        f"Ops: {operation_text}",
        click_text,
        focus_line,
    ]
    return lines[: max(1, int(max_lines if max_lines is not None else 10))]


def attach_watch_mode_panel(parent: Any, holoverse_root: Path | str | None, frame: dict[str, Any], *, clock: str | None = None) -> Any | None:
    """Attach a collisionless 3D Director/Watch panel to the integrated city root."""
    try:
        from panda3d.core import LineSegs, TextNode
    except Exception:
        return None
    snapshot = build_watch_snapshot(holoverse_root, clock or str(frame.get("clock") or "00:00"), frame=frame)
    lines = format_watch_lines(snapshot)
    root = parent.attachNewNode("holoutopia_watch_mode_panel")
    root.setPythonTag("holoutopia_watch_mode_panel", True)
    root.setPythonTag("holoutopia_watch_snapshot", snapshot)
    root.setLightOff(True)
    root.setTransparency(True)
    # Local city coordinates.  With the integrated city scale/anchor this lands
    # above the central city view rather than off-camera.
    root.setPos(500.0, 260.0, 165.0)
    try:
        root.setBillboardPointEye()
    except Exception:
        root.setHpr(0.0, -57.0, 0.0)

    # Minimal neon frame, deliberately non-opaque so it feels like the player is
    # watching the city, not reading a menu screen.
    seg = LineSegs("holoutopia_watch_panel_frame")
    seg.setThickness(2.2)
    seg.setColor(0.20, 0.92, 1.0, 0.82)
    w = 135.0
    h = 74.0
    seg.moveTo(-w, 0.0, h)
    seg.drawTo(w, 0.0, h)
    seg.drawTo(w, 0.0, -h)
    seg.drawTo(-w, 0.0, -h)
    seg.drawTo(-w, 0.0, h)
    # Subtle divider lines, not traffic-style stripes.
    for z in (42.0, -20.0):
        seg.moveTo(-w + 8.0, 0.0, z)
        seg.drawTo(w - 8.0, 0.0, z)
    frame_node = root.attachNewNode(seg.create())
    frame_node.setLightOff(True)

    for idx, line in enumerate(lines):
        text = TextNode(f"holoutopia_watch_line_{idx:02d}")
        text.setAlign(TextNode.ALeft)
        if idx == 0:
            text.setTextColor(0.78, 1.0, 1.0, 0.98)
            scale = 8.2
        elif idx in {2, 7, 8}:
            text.setTextColor(0.98, 0.78, 1.0, 0.94)
            scale = 5.4
        else:
            text.setTextColor(0.82, 0.94, 1.0, 0.90)
            scale = 5.1
        text.setText(str(line))
        node = root.attachNewNode(text)
        node.setScale(scale)
        node.setPos(-124.0, -0.2, 55.0 - idx * 14.0)
        node.setLightOff(True)
    return root


def _choose_join_target(pop_model: dict[str, Any], clusters: list[dict[str, Any]], commute_count: int) -> dict[str, Any]:
    phase = str(pop_model.get("phase") or "")
    if "return" in phase:
        return {"label": "Residential return route", "mode": "future_follow_commuter"}
    if "depart" in phase or commute_count > 0:
        return {"label": "Residential departure route", "mode": "future_follow_commuter"}
    if clusters:
        top = clusters[0]
        return {"label": str(top.get("label") or "Simulation Hub cluster"), "mode": "future_enter_activity_cluster"}
    return {"label": "Central Simulation Hub", "mode": "future_street_entry"}


def _resolve_flow_state(phase: str, commute_count: int, work_count: int, activity_count: int) -> str:
    p = str(phase or "").lower()
    if commute_count > 0 or "return" in p or "depart" in p:
        return "citizens are moving through commute routes"
    if work_count >= activity_count and work_count > 0:
        return "citizens are spread across work clusters"
    if activity_count > 0:
        return "citizens are using activity clusters"
    if "recharge" in p or "home" in p:
        return "citizens are recharging in home garrisons"
    return "city is running live schedules"


def _friendly_cluster_label(value: str) -> str:
    raw = str(value or "unassigned").strip().lower()
    replacements = {
        "arrival_gate_cluster": "Arrival Gate",
        "north_pod_cluster": "North Pods",
        "south_pod_cluster": "South Pods",
        "east_console_cluster": "Work Consoles",
        "west_social_cluster": "Social Sync",
        "forum_briefing_cluster": "Briefing Forum",
        "matrixcore_reader_cluster": "MatrixCore Readers",
        "evening_cooldown_cluster": "Cooldown Ring",
        "residential_departure": "Residential Departure",
        "simulation_departure": "Simulation Departure",
        "interdistrict_outbound": "Outbound Route",
        "interdistrict_return": "Return Route",
        "residential_return": "Residential Return",
    }
    if raw in replacements:
        return replacements[raw]
    cleaned = raw.replace("_cluster", "").replace("_", " ").strip()
    return cleaned.title() if cleaned else "Unassigned"


def _friendly_stage_label(value: str) -> str:
    raw = str(value or "unknown").strip().lower()
    replacements = {
        "departing_for_work": "Departing For Work",
        "off_district_work": "Off-District Work",
        "off_district_activities": "Off-District Activities",
        "returning_home_by_foot": "Returning Home By Foot",
        "home_recharge": "Home Recharge",
        "work_shift": "Work Shift",
        "cooldown_replenish": "Cooldown / Replenish",
        "residential_departure": "Residential Departure",
        "simulation_arrival": "Simulation Arrival",
        "interdistrict_outbound": "Outbound Route",
        "interdistrict_return": "Return Route",
        "simulation_departure": "Simulation Departure",
        "residential_return": "Residential Return",
    }
    if raw in replacements:
        return replacements[raw]
    return raw.replace("_", " ").strip().title() or "Unknown"


def _friendly_district_label(value: str) -> str:
    raw = str(value or "central_core_civic_ring").strip().lower()
    if raw == "central_core_civic_ring":
        return "Central Simulation Hub"
    if raw == "residential_alpha":
        return "Residential Alpha"
    if raw == "city_service_network":
        return "City Service Network"
    return raw.replace("_", " ").title()


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(float(value))
    except Exception:
        return int(default)
