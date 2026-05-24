"""District activity routing for HoloUtopia population representatives.

Pass 39A keeps Residential as the home/garrison district and treats the
Central Core Civic Ring as the lore-facing Simulation Hub.  This module does
not expand the 1000-person population into 1000 Panda3D actors; it produces a
small capped sample of visible activity representatives for the active district.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


RULES_REL = Path("database/utopia/simulation/district_activity_rules.json")
DEFAULT_ACTIVITY_RULES: dict[str, Any] = {
    "schema": 1,
    "id": "holoutopia_district_activity_rules_v1",
    "runtime_writes_allowed": False,
    "lore": {
        "simulation_hub_town_id": "central_core_civic_ring",
        "simulation_hub_display_name": "Central Simulation Hub",
        "residential_home_town_id": "residential_alpha",
        "note": "All citizens live in Residential Alpha. Work, activities, and replenish motives happen outside Residential; Simulation is the central hub."
    },
    "population_caps": {
        "max_visible_activity_representatives_per_district": 20
    },
    "daily_windows": {
        "departure_start": "06:00",
        "work_start": "08:00",
        "activity_start": "17:00",
        "return_home_start": "20:00",
        "home_lock": "21:00"
    },
    "district_activity_nodes": {
        "central_core_civic_ring": [
            {"node_id": "core_plaza_center", "cluster_id": "arrival_gate_cluster", "activity_id": "simulation_hub_arrival", "motive": "activities", "label": "arriving at the Simulation Hub"},
            {"node_id": "portal_ring_north", "cluster_id": "north_pod_cluster", "activity_id": "simulation_pod_session", "motive": "activities", "label": "entering a simulation pod"},
            {"node_id": "portal_ring_south", "cluster_id": "south_pod_cluster", "activity_id": "simulation_pod_session", "motive": "activities", "label": "leaving a simulation pod"},
            {"node_id": "portal_ring_east", "cluster_id": "east_live_model_cluster", "activity_id": "simulation_pod_session", "motive": "work", "label": "testing a live city model"},
            {"node_id": "portal_ring_west", "cluster_id": "west_social_sync_cluster", "activity_id": "simulation_social_sync", "motive": "replenish", "label": "syncing with friends"},
            {"node_id": "civic_forum_south", "cluster_id": "forum_briefing_cluster", "activity_id": "simulation_social_sync", "motive": "activities", "label": "joining a public sim briefing"},
            {"node_id": "matrixcore_reader_west", "cluster_id": "reader_lore_cluster", "activity_id": "matrixcore_lore_review", "motive": "activities", "label": "reviewing MatrixCore lore"},
            {"node_id": "social_plinth_evening", "cluster_id": "evening_cooldown_cluster", "activity_id": "simulation_social_sync", "motive": "replenish", "label": "cooling down after work"}
        ]
    },
    "future_district_order": [
        "market_crossing",
        "civic_commons_delta",
        "industrial_yard_alpha",
        "harbor_grid_beta",
        "archive_quarter_gamma",
        "security_gate",
        "glitched_quarantine_epsilon"
    ]
}


def data_root_from_holoutopia(holoutopia_root: Path | str | None = None) -> Path:
    root = Path(holoutopia_root or Path(__file__).resolve().parent).resolve()
    return root.parent if root.name.lower() in {"holoverse", "holoutopia"} else root


def _read_json(path: Path, fallback: Any) -> Any:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else fallback
    except Exception:
        return fallback


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = json.loads(json.dumps(base))
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_district_activity_rules(holoutopia_root: Path | str | None = None) -> dict[str, Any]:
    data_root = data_root_from_holoutopia(holoutopia_root)
    loaded = _read_json(data_root / RULES_REL, DEFAULT_ACTIVITY_RULES)
    return _deep_merge(DEFAULT_ACTIVITY_RULES, loaded if isinstance(loaded, dict) else {})


def parse_clock_minutes(value: Any) -> int:
    raw = str(value or "00:00").strip()
    if ":" not in raw:
        return 0
    hh, mm = raw.split(":", 1)
    try:
        return max(0, min(23, int(hh))) * 60 + max(0, min(59, int(mm)))
    except Exception:
        return 0


def _stable_index(seed: str, modulo: int) -> int:
    if modulo <= 0:
        return 0
    total = 0
    for idx, ch in enumerate(str(seed)):
        total = (total * 131 + (idx + 11) * ord(ch)) % 10000019
    return total % modulo


def _activity_phase(minutes: int, rules: dict[str, Any]) -> str:
    windows = rules.get("daily_windows") if isinstance(rules.get("daily_windows"), dict) else {}
    departure_start = parse_clock_minutes(windows.get("departure_start", "06:00"))
    work_start = parse_clock_minutes(windows.get("work_start", "08:00"))
    activity_start = parse_clock_minutes(windows.get("activity_start", "17:00"))
    return_home_start = parse_clock_minutes(windows.get("return_home_start", "20:00"))
    home_lock = parse_clock_minutes(windows.get("home_lock", "21:00"))
    if departure_start <= minutes < work_start:
        return "departing_residential"
    if work_start <= minutes < activity_start:
        return "simulation_hub_work"
    if activity_start <= minutes < return_home_start:
        return "simulation_hub_activity"
    if return_home_start <= minutes < home_lock:
        return "returning_to_residential"
    return "residential_garrison"


def _motive_for_phase(phase: str) -> str:
    if phase == "simulation_hub_work":
        return "work"
    if phase == "simulation_hub_activity":
        return "activities"
    if phase == "returning_to_residential":
        return "replenish"
    if phase == "departing_residential":
        return "work"
    return "home"


def _activity_nodes_for_motive(rules: dict[str, Any], town_id: str, motive: str) -> list[dict[str, Any]]:
    district_nodes = rules.get("district_activity_nodes") if isinstance(rules.get("district_activity_nodes"), dict) else {}
    nodes = district_nodes.get(town_id, []) if isinstance(district_nodes.get(town_id), list) else []
    filtered = [node for node in nodes if isinstance(node, dict) and str(node.get("motive") or "") in {motive, "activities", "replenish"}]
    if motive == "work":
        work_nodes = [node for node in nodes if isinstance(node, dict) and str(node.get("motive") or "") == "work"]
        return work_nodes or filtered or [node for node in nodes if isinstance(node, dict)]
    return filtered or [node for node in nodes if isinstance(node, dict)]


def build_district_activity_frame(
    holoutopia_root: Path | str | None,
    clock: str,
    *,
    world_population: int = 1000,
    max_visible_per_district: int | None = None,
    node_index: dict[str, Any] | None = None,
    rules: dict[str, Any] | None = None,
) -> dict[str, Any]:
    rules = rules if isinstance(rules, dict) else load_district_activity_rules(holoutopia_root)
    lore = rules.get("lore") if isinstance(rules.get("lore"), dict) else {}
    caps = rules.get("population_caps") if isinstance(rules.get("population_caps"), dict) else {}
    hub_town_id = str(lore.get("simulation_hub_town_id") or "central_core_civic_ring")
    hub_name = str(lore.get("simulation_hub_display_name") or "Central Simulation Hub")
    minutes = parse_clock_minutes(clock)
    phase = _activity_phase(minutes, rules)
    motive = _motive_for_phase(phase)
    cap = max(0, int(max_visible_per_district if max_visible_per_district is not None else caps.get("max_visible_activity_representatives_per_district", 20)))
    commute_phase = phase in {"departing_residential", "returning_to_residential"}
    active = phase in {"simulation_hub_work", "simulation_hub_activity"} or commute_phase
    visible_count = min(cap, max(0, int(world_population))) if active else 0
    nodes = _activity_nodes_for_motive(rules, hub_town_id, motive)
    service_routing_active = False
    if phase in {"simulation_hub_work", "simulation_hub_activity"}:
        try:
            from holoutopia_service_routing import service_nodes_for_phase
            service_nodes = service_nodes_for_phase(holoutopia_root, phase, motive)
            if service_nodes:
                nodes = service_nodes
                service_routing_active = True
        except Exception:
            service_routing_active = False
    if node_index is not None and not service_routing_active:
        valid_nodes = [node for node in nodes if str(node.get("node_id") or "") in node_index]
        nodes = valid_nodes or nodes
    if commute_phase and not nodes:
        nodes = [{"node_id": "commute_target", "cluster_id": "commute", "activity_id": "commute_departure", "motive": motive, "label": "commuting"}]
    visible: dict[str, Any] = {}
    cluster_counts: dict[str, int] = {}
    schedule_profiles: list[dict[str, Any]] = []
    for slot in range(visible_count):
        if not nodes:
            break
        seq = ((minutes * 53 + slot * 113) % max(1, int(world_population))) + 1
        if commute_phase:
            try:
                from holoutopia_commute_flow import commute_profile_for_visible_slot
                commute = commute_profile_for_visible_slot(holoutopia_root, phase=phase, clock_minutes=minutes, slot=slot, resident_sequence=seq)
            except Exception:
                commute = {"commute_stage": phase, "town_id": "residential_alpha", "grid": (1.0, 3.0), "progress": 0.0, "direction": "outbound" if phase == "departing_residential" else "return", "label": "commuting"}
            schedule_profile = {
                "schedule_profile_id": f"commute_sched_{slot:02d}_{commute.get('commute_stage')}",
                "personal_phase": str(commute.get("commute_stage") or phase),
                "motive": "work" if phase == "departing_residential" else "replenish",
                "preferred_clusters": [],
                "personal_day_offset_minutes": int(float(commute.get("progress", 0.0)) * 60),
            }
            node = {
                "node_id": "",
                "cluster_id": str(commute.get("commute_stage") or phase),
                "activity_id": "commute_departure" if phase == "departing_residential" else "commute_return_home",
                "motive": schedule_profile["motive"],
                "label": str(commute.get("label") or "commuting"),
            }
            node_id = ""
            motive_for_citizen = str(schedule_profile["motive"])
            cluster_id = str(node.get("cluster_id") or "commute")
            cluster_counts[cluster_id] = cluster_counts.get(cluster_id, 0) + 1
        else:
            try:
                from holoutopia_schedule_staggering import choose_distributed_node, schedule_profile_for_representative

                schedule_profile = schedule_profile_for_representative(holoutopia_root, clock_minutes=minutes, slot=slot, resident_sequence=seq, global_phase=phase)
                profile_motive = str(schedule_profile.get("motive") or motive)
                if service_routing_active:
                    try:
                        from holoutopia_service_routing import service_nodes_for_phase
                        profile_nodes = service_nodes_for_phase(holoutopia_root, phase, profile_motive) or nodes
                    except Exception:
                        profile_nodes = nodes
                else:
                    profile_nodes = _activity_nodes_for_motive(rules, hub_town_id, profile_motive) or nodes
                if node_index is not None and not service_routing_active:
                    valid_profile_nodes = [node for node in profile_nodes if str(node.get("node_id") or "") in node_index]
                    profile_nodes = valid_profile_nodes or profile_nodes
                if service_routing_active:
                    try:
                        from holoutopia_service_routing import choose_service_node
                        node = choose_service_node(profile_nodes, slot=slot, resident_sequence=seq, cluster_counts=cluster_counts, phase=phase) or profile_nodes[0]
                    except Exception:
                        node = choose_distributed_node(profile_nodes, schedule_profile, cluster_counts, slot=slot, clock_minutes=minutes) or profile_nodes[0]
                else:
                    node = choose_distributed_node(profile_nodes, schedule_profile, cluster_counts, slot=slot, clock_minutes=minutes) or profile_nodes[0]
                motive_for_citizen = str(node.get("motive") or profile_motive) if service_routing_active else profile_motive
            except Exception:
                schedule_profile = {"schedule_profile_id": f"sim_sched_fallback_{slot:02d}", "motive": motive, "preferred_clusters": []}
                node = nodes[(slot + minutes // 15) % len(nodes)]
                motive_for_citizen = motive
                cluster_key = str(node.get("cluster_id") or "unclustered")
                cluster_counts[cluster_key] = cluster_counts.get(cluster_key, 0) + 1
            node_id = str(node.get("node_id") or "core_plaza_center")
            if node_index is not None and node_id not in node_index and not bool(node.get("functional_service_node")):
                node_id = "core_plaza_center"
            commute = {}
            cluster_id = str(node.get("cluster_id") or "")
        cid = f"act_sim_{seq:04d}"
        activity_id = str(node.get("activity_id") or "simulation_hub_activity")
        label = str(node.get("label") or "using the Simulation Hub")
        if motive_for_citizen == "work":
            activity_stage = "work_shift"
        elif motive_for_citizen == "replenish":
            activity_stage = "cooldown_replenish"
        else:
            activity_stage = "evening_activity" if phase == "simulation_hub_activity" else "arrival"
        if commute_phase:
            activity_stage = str(commute.get("commute_stage") or activity_stage)
        schedule_profiles.append(dict(schedule_profile))
        target_town_id = str(node.get("town_id") or commute.get("town_id") or hub_town_id)
        service_grid = node.get("service_grid") if isinstance(node.get("service_grid"), (list, tuple)) else None
        citizen_payload = {
            "id": cid,
            "display_name": f"Resident {seq:04d}",
            "role": "resident",
            "home_town_id": str(lore.get("residential_home_town_id") or "residential_alpha"),
            "home_lot_id": "Residential garrison",
            "job_title": "Simulation Hub participant" if motive_for_citizen != "work" else "Simulation Hub worker",
            "schedule_index": slot,
            "action": "use_simulation_hub" if motive != "work" else "simulation_work_shift",
            "activity_id": activity_id,
            "activity_cluster_id": cluster_id,
            "activity_stage": activity_stage,
            "target_node": node_id,
            "resolved_node": node_id,
            "target_resolution": "commute_flow_route" if commute_phase else ("functional_service_routing" if bool(node.get("functional_service_node")) else "district_activity_rule"),
            "town_id": target_town_id,
            "position": {"grid_x": float((commute.get("grid") or (4.0, 3.0))[0]), "grid_y": float((commute.get("grid") or (4.0, 3.0))[1])} if commute_phase else ({"grid_x": float(service_grid[0]), "grid_y": float(service_grid[1])} if service_grid else {}),
            "location_mode": "public_commute" if commute_phase else "public_visible",
            "visibility": "public_schedule",
            "pathing_policy": "street_safe_no_building_standing",
            "activity_surface_policy": "activity_cluster_slot_or_street_pad_only",
            "friends": [],
            "interruptible": True,
            "energy": max(0, 100 - int(max(0, minutes - 6 * 60) / (15 * 60) * 100)),
            "garrison_id": "residential_alpha_virtual_garrison",
            "current_task_readable": label,
            "motive": motive_for_citizen,
            "schedule_profile_id": str(schedule_profile.get("schedule_profile_id") or f"sim_sched_{slot:02d}"),
            "personal_clock": str(schedule_profile.get("personal_clock") or clock),
            "personal_phase": str(schedule_profile.get("personal_phase") or activity_stage),
            "personal_day_offset_minutes": int(schedule_profile.get("personal_day_offset_minutes", 0) or 0),
            "work_start": str(schedule_profile.get("work_start") or "08:00"),
            "work_end": str(schedule_profile.get("work_end") or "17:00"),
            "activity_start": str(schedule_profile.get("activity_start") or "17:00"),
            "return_home": str(schedule_profile.get("return_home") or "20:00"),
            "activity_district_display_name": str(node.get("district_display_name") or hub_name),
            "functional_service_assignment": bool(node.get("functional_service_node")),
            "service_building_id": str(node.get("service_building_id") or ""),
            "service_building_name": str(node.get("service_display_name") or ""),
            "service_short_label": str(node.get("service_short_label") or ""),
            "service_role": str(node.get("service_role") or ""),
            "service_type": str(node.get("service_type") or ""),
            "service_capacity": int(node.get("service_capacity", 0) or 0),
            "virtual_population_representative": True,
            "district_activity_representative": True,
            "commute_flow_representative": bool(commute_phase),
            "commute_stage": str(commute.get("commute_stage") or ""),
            "commute_direction": str(commute.get("direction") or ""),
            "commute_progress": round(float(commute.get("progress", 0.0) or 0.0), 3),
        }
        try:
            from holoutopia_activity_behaviors import enrich_activity_citizen
            citizen_payload = enrich_activity_citizen(holoutopia_root, citizen_payload)
        except Exception:
            # Behavior enrichment is visual/panel metadata only. Routing remains valid without it.
            pass
        visible[cid] = citizen_payload
    adventure_state: dict[str, Any] = {}
    try:
        from holoutopia_adventure_simulation import build_adventure_simulation_state
        adventure_state = build_adventure_simulation_state(
            holoutopia_root,
            clock,
            visible_citizens=visible,
            world_population=world_population,
        )
    except Exception as exc:
        adventure_state = {"error": f"adventure-simulation-state:{exc.__class__.__name__}:{exc}", "match_active": False, "observe_available": False}

    return {
        "schema": 1,
        "id": f"holoutopia_district_activity_frame_{str(clock).replace(':', '')}",
        "clock": str(clock),
        "phase": phase,
        "active_district_id": ("city_service_network" if service_routing_active and active else (hub_town_id if active else "residential_alpha")),
        "active_district_display_name": ("City Service Network" if service_routing_active and active else (hub_name if active else "Residential Alpha")),
        "central_simulation_hub": hub_town_id,
        "motive": motive,
        "visible_activity_count": len(visible),
        "max_visible_activity_representatives_per_district": cap,
        "outdoor_cap_enforced": len(visible) <= cap,
        "visible_pathing_policy": "Simulation Hub representatives prefer named activity-cluster standing slots, then authored roads/activity pads; commute phases use street-snapped route targets.",
        "activity_cluster_policy": "citizens group around visible Simulation Hub pods/terminals or functional service buildings without standing on buildings",
        "functional_service_routing": bool(service_routing_active),
        "activity_behavior_policy": "activity representatives carry data-driven tiny-person poses and statuses",
        "schedule_staggering_policy": "visible representatives use unique personal schedule offsets and a per-cluster distribution guard",
        "commute_flow_policy": "06:00-08:00 and 20:00-21:00 citizens are distributed along Residential/Simulation street-safe commute phases",
        "activity_cluster_distribution": dict(sorted(cluster_counts.items())),
        "unique_schedule_profiles": len({str(profile.get("schedule_profile_id") or "") for profile in schedule_profiles}),
        "visible_activity_citizens": visible,
        "adventure_simulation_state": adventure_state,
        "central_hub_adventure_active": bool(adventure_state.get("match_active")) if isinstance(adventure_state, dict) else False,
        "central_hub_observe_available": bool(adventure_state.get("observe_available")) if isinstance(adventure_state, dict) else False,
        "service_assignment_policy": "work/activity/replenish motives route representatives to functional district buildings; final placement is still street-safe snapped",
        "adventure_simulation_policy": "Central Hub can host one 4-player adventure simulation with a replacement queue; clicking/observing is only available while a match has active players.",
        "next_pass_hint": "Build the observer-entry view for the active adventure simulation, then the combat arena prototype.",
    }
