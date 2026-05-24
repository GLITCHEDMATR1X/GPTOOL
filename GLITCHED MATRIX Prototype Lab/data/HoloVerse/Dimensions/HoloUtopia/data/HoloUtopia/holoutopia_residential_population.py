"""Residential population/garrison rules for HoloUtopia.

This module intentionally does not expand the authored citizen manifest to 1000
rows.  It produces a deterministic virtual population model:
- 1000 default residents live in Residential Alpha;
- homes are represented by garrison wings capped at 50 residents each;
- only a small capped sample of outdoor representatives is rendered;
- energy follows the 15h active / 9h home-recharge rule.

The output is JSON-safe and Panda3D-free so validators and screenshot tools can
use it without importing the runtime.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
from typing import Any, Iterable


RULES_REL = Path("database/utopia/population/residential_population_rules.json")
DEFAULT_RULES: dict[str, Any] = {
    "schema": 1,
    "population": {"default_world_population": 1000, "residential_home_town_id": "residential_alpha", "all_citizens_live_in_residential": True, "work_and_activities_outside_residential": True},
    "timescale": {"real_seconds_per_game_hour": 60, "full_day_seconds": 1440},
    "residential_building_garrison": {"tiers": [10, 20, 40, 50], "max_population_largest_building": 50, "supplemental_garrison_wings_allowed": True},
    "outdoors": {"max_outdoor_population_per_district": 20, "active_district_id": "residential_alpha"},
    "citizen_energy": {"max_energy_percent": 100, "active_energy_lasts_game_hours": 15, "home_recharge_game_hours": 9},
    "daily_windows": {"home_recharge_start": "21:00", "home_recharge_end": "06:00", "work_departure_start": "06:00", "work_shift_start": "08:00", "activity_window_start": "17:00", "return_home_start": "20:00", "home_recharge_lock": "21:00"},
}


@dataclass(frozen=True)
class PopulationRulesSummary:
    world_population: int
    residential_home_town_id: str
    max_outdoor_per_district: int
    day_seconds: int
    energy_active_hours: int
    recharge_hours: int
    garrison_wing_count: int
    garrison_capacity: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "world_population": self.world_population,
            "residential_home_town_id": self.residential_home_town_id,
            "max_outdoor_per_district": self.max_outdoor_per_district,
            "day_seconds": self.day_seconds,
            "energy_active_hours": self.energy_active_hours,
            "recharge_hours": self.recharge_hours,
            "garrison_wing_count": self.garrison_wing_count,
            "garrison_capacity": self.garrison_capacity,
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


def load_population_rules(holoutopia_root: Path | str | None = None) -> dict[str, Any]:
    data_root = data_root_from_holoutopia(holoutopia_root)
    rules = _read_json(data_root / RULES_REL, DEFAULT_RULES)
    if not isinstance(rules, dict):
        return dict(DEFAULT_RULES)
    merged = json.loads(json.dumps(DEFAULT_RULES))
    for key, value in rules.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key].update(value)
        else:
            merged[key] = value
    return merged


def parse_clock_minutes(value: Any) -> int:
    raw = str(value or "00:00").strip()
    if ":" not in raw:
        return 0
    hh, mm = raw.split(":", 1)
    try:
        hour = max(0, min(23, int(hh)))
        minute = max(0, min(59, int(mm)))
        return hour * 60 + minute
    except Exception:
        return 0


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _population_int(rules: dict[str, Any], section: str, key: str, default: int) -> int:
    bucket = rules.get(section) if isinstance(rules.get(section), dict) else {}
    try:
        return int(bucket.get(key, default))
    except Exception:
        return int(default)


def _rules_bool(rules: dict[str, Any], section: str, key: str, default: bool) -> bool:
    bucket = rules.get(section) if isinstance(rules.get(section), dict) else {}
    return bool(bucket.get(key, default))


def _residential_town_id(rules: dict[str, Any]) -> str:
    pop = rules.get("population") if isinstance(rules.get("population"), dict) else {}
    return str(pop.get("residential_home_town_id") or "residential_alpha")


def _building_score(lot: dict[str, Any]) -> tuple[float, str]:
    profile = lot.get("building_profile") if isinstance(lot.get("building_profile"), dict) else {}
    floor_count = float(profile.get("floor_count", 1) or 1)
    height_units = float(profile.get("height_units", 12.0) or 12.0)
    authored_capacity = float(profile.get("residential_capacity", 0) or 0)
    return (floor_count * 1000.0 + height_units * 10.0 + authored_capacity, str(lot.get("id") or ""))


def residential_lots(inputs: dict[str, Any], rules: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    rules = rules if isinstance(rules, dict) else load_population_rules(None)
    town_id = _residential_town_id(rules)
    neighborhoods = inputs.get("neighborhoods", {}) if isinstance(inputs.get("neighborhoods"), dict) else {}
    lots: list[dict[str, Any]] = []
    for neighborhood_id, neighborhood in sorted(neighborhoods.items()):
        if not isinstance(neighborhood, dict) or str(neighborhood.get("town_id")) != town_id:
            continue
        for lot in _as_list(neighborhood.get("lots")):
            if isinstance(lot, dict):
                item = dict(lot)
                item["neighborhood_id"] = str(neighborhood_id)
                lots.append(item)
    return sorted(lots, key=_building_score)


def build_residential_garrison_plan(inputs: dict[str, Any], rules: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build capped garrison wings that can hold the default world population."""
    rules = rules if isinstance(rules, dict) else load_population_rules(None)
    world_population = max(0, _population_int(rules, "population", "default_world_population", 1000))
    town_id = _residential_town_id(rules)
    garrison_rules = rules.get("residential_building_garrison") if isinstance(rules.get("residential_building_garrison"), dict) else {}
    tiers = [int(v) for v in _as_list(garrison_rules.get("tiers")) if int(v) > 0] or [10, 20, 40, 50]
    max_cap = max(1, int(garrison_rules.get("max_population_largest_building", max(tiers))))
    base_lots = residential_lots(inputs, rules)
    garrisons: list[dict[str, Any]] = []
    assigned = 0

    for idx, lot in enumerate(base_lots):
        tier_index = min(idx, len(tiers) - 1)
        capacity = min(max_cap, max(tiers[0], int(tiers[tier_index])))
        resident_count = min(capacity, max(0, world_population - assigned))
        if resident_count <= 0:
            break
        profile = lot.get("building_profile") if isinstance(lot.get("building_profile"), dict) else {}
        anchors = lot.get("anchors") if isinstance(lot.get("anchors"), dict) else {}
        front_door_node = str((anchors.get("front_door") if isinstance(anchors.get("front_door"), dict) else {}).get("id") or lot.get("home_node") or "")
        porch_node = str((anchors.get("porch") if isinstance(anchors.get("porch"), dict) else {}).get("id") or front_door_node)
        garrisons.append({
            "id": f"res_alpha_garrison_{len(garrisons) + 1:02d}",
            "kind": "authored_residential_building",
            "town_id": town_id,
            "neighborhood_id": str(lot.get("neighborhood_id") or ""),
            "lot_id": str(lot.get("id") or ""),
            "home_node": str(lot.get("home_node") or ""),
            "front_door_node": front_door_node,
            "porch_node": porch_node,
            "source_block": str(lot.get("block") or ""),
            "building_type": str(profile.get("building_type") or "residential"),
            "capacity": capacity,
            "resident_start": assigned + 1,
            "resident_end": assigned + resident_count,
            "resident_count": resident_count,
            "virtual_wing": False,
            "rule": "tiered_smallest_to_largest_x2_capped_50",
        })
        assigned += resident_count

    allow_wings = bool(garrison_rules.get("supplemental_garrison_wings_allowed", True))
    anchor_lots = base_lots or [{"id": "res_alpha_virtual_lot", "home_node": "res_alpha_social_plaza_node", "block": "res_alpha_social_plaza", "neighborhood_id": "residential_alpha_neighborhood_01", "building_profile": {"building_type": "virtual_residential_wing"}}]
    while assigned < world_population and allow_wings:
        lot = anchor_lots[len(garrisons) % len(anchor_lots)]
        profile = lot.get("building_profile") if isinstance(lot.get("building_profile"), dict) else {}
        anchors = lot.get("anchors") if isinstance(lot.get("anchors"), dict) else {}
        front_door_node = str((anchors.get("front_door") if isinstance(anchors.get("front_door"), dict) else {}).get("id") or lot.get("home_node") or "")
        porch_node = str((anchors.get("porch") if isinstance(anchors.get("porch"), dict) else {}).get("id") or front_door_node)
        capacity = max_cap
        resident_count = min(capacity, world_population - assigned)
        garrisons.append({
            "id": f"res_alpha_garrison_{len(garrisons) + 1:02d}",
            "kind": "supplemental_garrison_wing",
            "town_id": town_id,
            "neighborhood_id": str(lot.get("neighborhood_id") or ""),
            "lot_id": str(lot.get("id") or ""),
            "home_node": str(lot.get("home_node") or ""),
            "front_door_node": front_door_node,
            "porch_node": porch_node,
            "source_block": str(lot.get("block") or ""),
            "building_type": str(profile.get("building_type") or "residential"),
            "capacity": capacity,
            "resident_start": assigned + 1,
            "resident_end": assigned + resident_count,
            "resident_count": resident_count,
            "virtual_wing": True,
            "rule": "supplemental_wing_capped_50_until_physical_expansion",
        })
        assigned += resident_count

    return {
        "schema": 1,
        "id": "holoutopia_residential_garrison_plan_runtime_v1",
        "town_id": town_id,
        "world_population_target": world_population,
        "resident_count": assigned,
        "total_capacity": sum(int(g.get("capacity", 0) or 0) for g in garrisons),
        "garrison_count": len(garrisons),
        "max_capacity_per_garrison": max_cap,
        "all_garrisons_capped": all(int(g.get("capacity", 0) or 0) <= max_cap for g in garrisons),
        "uses_supplemental_wings": any(bool(g.get("virtual_wing")) for g in garrisons),
        "garrisons": garrisons,
    }


def _clock_phase(minutes: int) -> str:
    if 6 * 60 <= minutes < 8 * 60:
        return "departing_for_work"
    if 8 * 60 <= minutes < 17 * 60:
        return "off_district_work"
    if 17 * 60 <= minutes < 20 * 60:
        return "off_district_activities"
    if 20 * 60 <= minutes < 21 * 60:
        return "returning_home_by_foot"
    return "home_recharge"


def _energy_percent(minutes: int, rules: dict[str, Any]) -> int:
    active_hours = max(1, _population_int(rules, "citizen_energy", "active_energy_lasts_game_hours", 15))
    recharge_hours = max(1, _population_int(rules, "citizen_energy", "home_recharge_game_hours", 9))
    if 6 * 60 <= minutes < 21 * 60:
        elapsed = (minutes - 6 * 60) / 60.0
        return int(round(max(0.0, 100.0 - (elapsed / float(active_hours)) * 100.0)))
    if minutes >= 21 * 60:
        elapsed = (minutes - 21 * 60) / 60.0
    else:
        elapsed = (3 * 60 + minutes) / 60.0
    return int(round(min(100.0, (elapsed / float(recharge_hours)) * 100.0)))


def _outdoor_count_for_phase(phase: str, rules: dict[str, Any], population: int) -> int:
    limit = max(0, _population_int(rules, "outdoors", "max_outdoor_population_per_district", 20))
    if phase in {"departing_for_work", "returning_home_by_foot"}:
        return min(limit, population)
    if phase == "off_district_activities":
        # Residential remains capped and quiet while most activity happens elsewhere.
        return min(max(4, limit // 2), population)
    if phase == "off_district_work":
        return min(max(2, limit // 4), population)
    return 0


def _node_for_garrison(garrison: dict[str, Any], phase: str, slot: int) -> str:
    if phase == "departing_for_work":
        # A mix of porch/door and west-gate points makes the outbound flow readable without placing robots inside buildings.
        if slot % 4 == 0:
            return "res_alpha_west_gate"
        return str(garrison.get("porch_node") or garrison.get("front_door_node") or "res_alpha_social_plaza_node")
    if phase == "returning_home_by_foot":
        if slot % 4 == 0:
            return "res_alpha_west_gate"
        return str(garrison.get("porch_node") or garrison.get("front_door_node") or "res_alpha_social_plaza_node")
    if phase == "off_district_activities":
        return "res_alpha_social_plaza_node" if slot % 2 else "res_alpha_west_gate"
    if phase == "off_district_work":
        return "res_alpha_west_gate"
    return str(garrison.get("home_node") or "res_alpha_social_plaza_node")


def _activity_for_phase(phase: str) -> tuple[str, str, str]:
    if phase == "departing_for_work":
        return "walk_to_transit", "commute", "Walking to work outside Residential"
    if phase == "returning_home_by_foot":
        return "return_home", "return_home", "Returning to home garrison by foot"
    if phase == "off_district_activities":
        return "replenish", "replenish", "Passing through Residential before off-district activities"
    if phase == "off_district_work":
        return "work", "off_district_work", "Working outside Residential"
    return "recharge", "home_recharge", "Recharging inside home garrison"


def build_residential_population_frame(
    holoutopia_root: Path | str | None,
    clock: str,
    *,
    inputs: dict[str, Any] | None = None,
    node_index: dict[str, Any] | None = None,
    rules: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return virtual population state for one game clock."""
    if inputs is None:
        from holoutopia_citizen_simulation import load_simulation_inputs

        inputs = load_simulation_inputs(holoutopia_root)
    rules = rules if isinstance(rules, dict) else load_population_rules(holoutopia_root)
    population = max(0, _population_int(rules, "population", "default_world_population", 1000))
    garrison_plan = build_residential_garrison_plan(inputs, rules)
    minutes = parse_clock_minutes(clock)
    phase = _clock_phase(minutes)
    energy = _energy_percent(minutes, rules)
    outdoor_visible = _outdoor_count_for_phase(phase, rules, population)
    outside_residential = population - outdoor_visible if phase != "home_recharge" else 0
    home_count = population if phase == "home_recharge" else max(0, population - outside_residential - outdoor_visible)
    action, activity_id, readable_task = _activity_for_phase(phase)

    garrisons = list(garrison_plan.get("garrisons") or [])
    visible: dict[str, Any] = {}
    for slot in range(outdoor_visible):
        garrison = garrisons[(slot + minutes // 30) % max(1, len(garrisons))] if garrisons else {}
        seq = ((minutes * 37 + slot * 97) % max(1, population)) + 1
        cid = f"pop_res_{seq:04d}"
        node_id = _node_for_garrison(garrison, phase, slot)
        visible[cid] = {
            "id": cid,
            "display_name": f"Resident {seq:04d}",
            "role": "resident",
            "home_town_id": _residential_town_id(rules),
            "home_lot_id": str(garrison.get("lot_id") or ""),
            "job_title": "Off-district worker",
            "schedule_index": slot,
            "action": action,
            "activity_id": activity_id,
            "target_node": node_id,
            "resolved_node": node_id,
            "target_resolution": "virtual_population_rule",
            "town_id": _residential_town_id(rules),
            "location_mode": "public_visible",
            "visibility": "public_schedule",
            "pathing_policy": "street_safe_no_building_standing",
            "garrison_policy": "home_building_is_virtual_interior_only",
            "friends": [],
            "interruptible": True,
            "energy": energy,
            "garrison_id": str(garrison.get("id") or ""),
            "current_task_readable": readable_task,
            "virtual_population_representative": True,
        }
    district_activity_model: dict[str, Any] = {}
    try:
        from holoutopia_district_activities import build_district_activity_frame

        district_activity_model = build_district_activity_frame(
            holoutopia_root,
            clock,
            world_population=population,
            max_visible_per_district=max(0, _population_int(rules, "outdoors", "max_outdoor_population_per_district", 20)),
            node_index=node_index if isinstance(node_index, dict) else None,
        )
    except Exception as exc:
        district_activity_model = {"error": f"district-activity-model:{exc.__class__.__name__}:{exc}", "visible_activity_citizens": {}}

    return {
        "schema": 1,
        "id": f"holoutopia_residential_population_frame_{str(clock).replace(':', '')}",
        "clock": str(clock),
        "phase": phase,
        "world_population": population,
        "residential_population": population,
        "home_garrison_population": home_count,
        "outside_residential_population": outside_residential,
        "outdoor_population": outdoor_visible,
        "max_outdoor_population_per_district": max(0, _population_int(rules, "outdoors", "max_outdoor_population_per_district", 20)),
        "outdoor_cap_enforced": outdoor_visible <= max(0, _population_int(rules, "outdoors", "max_outdoor_population_per_district", 20)),
        "average_energy_percent": energy,
        "energy_rule": "100% lasts 15 game hours, then 9 game hours at home to fully recharge",
        "daily_motives": list(rules.get("daily_motives") if isinstance(rules.get("daily_motives"), list) else ["work", "activities", "replenish"]),
        "work_and_activities_outside_residential": _rules_bool(rules, "population", "work_and_activities_outside_residential", True),
        "all_citizens_live_in_residential": _rules_bool(rules, "population", "all_citizens_live_in_residential", True),
        "visible_pathing_policy": "Visible people snap to authored streets/activity pads; home garrison occupancy remains virtual indoors.",
        "garrison_plan": garrison_plan,
        "visible_outdoor_citizens": visible,
        "district_activity_model": district_activity_model,
        "visible_activity_citizens": district_activity_model.get("visible_activity_citizens", {}) if isinstance(district_activity_model, dict) else {},
    }


def build_population_rules_summary(holoutopia_root: Path | str | None = None) -> PopulationRulesSummary:
    from holoutopia_citizen_simulation import load_simulation_inputs

    rules = load_population_rules(holoutopia_root)
    inputs = load_simulation_inputs(holoutopia_root)
    plan = build_residential_garrison_plan(inputs, rules)
    return PopulationRulesSummary(
        world_population=max(0, _population_int(rules, "population", "default_world_population", 1000)),
        residential_home_town_id=_residential_town_id(rules),
        max_outdoor_per_district=max(0, _population_int(rules, "outdoors", "max_outdoor_population_per_district", 20)),
        day_seconds=max(1, _population_int(rules, "timescale", "full_day_seconds", 1440)),
        energy_active_hours=max(1, _population_int(rules, "citizen_energy", "active_energy_lasts_game_hours", 15)),
        recharge_hours=max(1, _population_int(rules, "citizen_energy", "home_recharge_game_hours", 9)),
        garrison_wing_count=int(plan.get("garrison_count", 0) or 0),
        garrison_capacity=int(plan.get("total_capacity", 0) or 0),
    )


def virtual_population_panel_payload(citizen_state: dict[str, Any], *, clock: str) -> dict[str, Any]:
    """Return a normal citizen-inspector shaped payload for one sampled resident."""
    cid = str(citizen_state.get("id") or "resident")
    task_type = str(citizen_state.get("activity_id") or "commute")
    current_task = {
        "task_id": f"{cid}_virtual_population_task",
        "type": task_type,
        "display_name": str(citizen_state.get("current_task_readable") or "Residential population activity"),
        "target_node": str(citizen_state.get("resolved_node") or "res_alpha_west_gate"),
        "status": "active",
        "priority": 50,
        "interruptible": True,
    }
    queue = {
        "citizen_id": cid,
        "display_name": str(citizen_state.get("display_name") or cid),
        "role": str(citizen_state.get("role") or "resident"),
        "purpose": "Representative resident from the 1000-person Residential garrison population.",
        "district": "Residential Alpha",
        "home_lot_id": str(citizen_state.get("home_lot_id") or "Residential garrison"),
        "home_node": str(citizen_state.get("target_node") or ""),
        "job_title": "Off-district worker",
        "work_node": "Outside Residential",
        "clock": str(clock),
        "mood": "focused",
        "energy": int(citizen_state.get("energy", 100) or 100),
        "current_task": current_task,
        "queued_tasks": [
            {"task_id": f"{cid}_return_home", "type": "return_home", "display_name": "Return to Home Garrison", "target_node": str(citizen_state.get("home_node") or "Residential"), "status": "queued", "priority": 60, "interruptible": True},
            {"task_id": f"{cid}_recharge", "type": "home_recharge", "display_name": "Recharge for 9 Game Hours", "target_node": str(citizen_state.get("home_node") or "Residential"), "status": "queued", "priority": 40, "interruptible": False},
        ],
        "friends": [],
        "recent_activity": [],
        "current_activity_id": task_type,
        "current_node": str(citizen_state.get("resolved_node") or ""),
        "route_target": str(citizen_state.get("target_node") or ""),
        "visibility": "public_visible",
        "safe_edit_note": "This is a sampled population representative, not an authored identity row.",
    }
    return {"ok": True, "kind": "citizen_inspector", "queue": queue, "citizen_id": cid}
