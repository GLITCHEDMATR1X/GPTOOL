"""Functional service behavior states for HoloUtopia citizens.

Pass 50 turns service routing into service performance.  Citizens assigned to
functional buildings now carry a small operation/action payload that describes
what the building is doing, what output it contributes to the city, and which
brief pose/glyph should be shown.  The module is read-only and pure Python so it
can be validated without launching Panda3D.
"""
from __future__ import annotations

import copy
import json
from collections import Counter
from pathlib import Path
from typing import Any

RULES_REL = Path("database/utopia/services/service_behavior_rules.json")

_DEFAULT_RULES: dict[str, Any] = {
    "schema": 1,
    "id": "holoutopia_service_behavior_rules_default",
    "runtime_writes_allowed": False,
    "purpose": "Map functional service buildings to visible citizen service actions and outputs.",
    "rules": {
        "enabled": True,
        "read_only": True,
        "only_for_functional_service_assignments": True,
        "answers_must_use_runtime_service_state": True,
        "service_glyphs_visual_only": True,
        "no_collision_geometry": True,
    },
    "default_behavior": {
        "operation_id": "service_use",
        "action_label": "using service",
        "output_label": "service active",
        "pose": "idle_activity",
        "family": "activity",
        "glyph": "node_tick",
        "status": "using service",
    },
    "building_type_behaviors": {
        "core_pyramid": {"operation_id": "simulate_city", "action_label": "calibrating core", "output_label": "city model stable", "pose": "pod_focus", "family": "pod", "glyph": "pulse_ring", "status": "calibrating Core"},
        "pod_ring": {"operation_id": "run_pod", "action_label": "running pod", "output_label": "simulation active", "pose": "pod_focus", "family": "pod", "glyph": "pulse_ring", "status": "running Pods"},
        "reader": {"operation_id": "read_lore", "action_label": "reading lore", "output_label": "memory context", "pose": "reading_lore", "family": "lore", "glyph": "data_bars", "status": "reading Lore"},
        "forum": {"operation_id": "host_forum", "action_label": "briefing group", "output_label": "civic sync", "pose": "social_sync", "family": "social", "glyph": "signal_arc", "status": "briefing forum"},
        "hall": {"operation_id": "govern_meeting", "action_label": "attending council", "output_label": "city decision", "pose": "briefing_attention", "family": "briefing", "glyph": "signal_arc", "status": "at Council Hall"},
        "office": {"operation_id": "process_permit", "action_label": "processing permit", "output_label": "admin cleared", "pose": "console_work", "family": "work", "glyph": "data_bars", "status": "processing Permit"},
        "stalls": {"operation_id": "food_service", "action_label": "getting food", "output_label": "energy replenished", "pose": "social_sync", "family": "social", "glyph": "market_diamond", "status": "at Food"},
        "kiosk_row": {"operation_id": "trade_goods", "action_label": "trading goods", "output_label": "trade complete", "pose": "console_work", "family": "work", "glyph": "market_diamond", "status": "trading"},
        "plaza": {"operation_id": "social_meet", "action_label": "meeting citizens", "output_label": "morale up", "pose": "social_sync", "family": "social", "glyph": "signal_arc", "status": "socializing"},
        "factory_bay": {"operation_id": "fabricate_parts", "action_label": "fabricating parts", "output_label": "parts made", "pose": "console_work", "family": "work", "glyph": "wrench", "status": "fabricating"},
        "dock": {"operation_id": "repair_service", "action_label": "repairing service", "output_label": "systems repaired", "pose": "console_work", "family": "work", "glyph": "wrench", "status": "repairing"},
        "utility_stack": {"operation_id": "check_power", "action_label": "checking power", "output_label": "power stable", "pose": "console_work", "family": "work", "glyph": "pulse_ring", "status": "checking Power"},
        "control_tower": {"operation_id": "route_cargo", "action_label": "routing cargo", "output_label": "dock flow stable", "pose": "console_work", "family": "work", "glyph": "signal_arc", "status": "routing Dock"},
        "water_plant": {"operation_id": "purify_water", "action_label": "purifying water", "output_label": "water clean", "pose": "cooldown_sway", "family": "cooldown", "glyph": "water_drop", "status": "purifying Water"},
        "waterfront_walk": {"operation_id": "tidal_rest", "action_label": "walking tide", "output_label": "stress reduced", "pose": "cooldown_sway", "family": "cooldown", "glyph": "water_drop", "status": "on Tidal Walk"},
        "archive_stack": {"operation_id": "index_memory", "action_label": "indexing memory", "output_label": "memory indexed", "pose": "reading_lore", "family": "lore", "glyph": "data_bars", "status": "indexing Memory"},
        "lab": {"operation_id": "recover_data", "action_label": "recovering data", "output_label": "data recovered", "pose": "console_work", "family": "work", "glyph": "data_bars", "status": "recovering data"},
        "vault": {"operation_id": "browse_vault", "action_label": "browsing vault", "output_label": "lore found", "pose": "reading_lore", "family": "lore", "glyph": "data_bars", "status": "in Lore Vault"},
        "gatehouse": {"operation_id": "scan_access", "action_label": "scanning access", "output_label": "entry clear", "pose": "briefing_attention", "family": "briefing", "glyph": "shield_scan", "status": "scanning Check"},
        "briefing_room": {"operation_id": "patrol_brief", "action_label": "briefing patrol", "output_label": "patrol ready", "pose": "briefing_attention", "family": "briefing", "glyph": "shield_scan", "status": "briefing patrol"},
        "response_bay": {"operation_id": "ready_response", "action_label": "readying response", "output_label": "response ready", "pose": "console_work", "family": "work", "glyph": "shield_scan", "status": "readying response"},
        "ward": {"operation_id": "stabilize_citizen", "action_label": "stabilizing ward", "output_label": "glitch reduced", "pose": "cooldown_sway", "family": "cooldown", "glyph": "warning_cross", "status": "stabilizing Ward"},
        "monitor_station": {"operation_id": "monitor_glitch", "action_label": "monitoring glitch", "output_label": "glitch tracked", "pose": "console_work", "family": "work", "glyph": "warning_cross", "status": "monitoring glitch"},
        "containment_gate": {"operation_id": "check_containment", "action_label": "checking gate", "output_label": "containment safe", "pose": "briefing_attention", "family": "briefing", "glyph": "warning_cross", "status": "checking containment"}
    }
}


def data_root_from_holoutopia(holoutopia_root: Path | str | None = None) -> Path:
    root = Path(holoutopia_root or Path(__file__).resolve().parent).resolve()
    return root.parent if root.name.lower() in {"holoverse", "holoutopia"} else root


def _read_json(path: Path, fallback: dict[str, Any]) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return copy.deepcopy(fallback)
    return data if isinstance(data, dict) else copy.deepcopy(fallback)


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_service_behavior_rules(holoutopia_root: Path | str | None = None) -> dict[str, Any]:
    data_root = data_root_from_holoutopia(holoutopia_root)
    return _deep_merge(_DEFAULT_RULES, _read_json(data_root / RULES_REL, _DEFAULT_RULES))


def behavior_for_citizen(holoutopia_root: Path | str | None, citizen: dict[str, Any]) -> dict[str, Any]:
    rules = load_service_behavior_rules(holoutopia_root)
    default = rules.get("default_behavior") if isinstance(rules.get("default_behavior"), dict) else {}
    type_map = rules.get("building_type_behaviors") if isinstance(rules.get("building_type_behaviors"), dict) else {}
    service_type = str(citizen.get("service_type") or "").strip()
    behavior = type_map.get(service_type) if isinstance(type_map.get(service_type), dict) else None
    if behavior is None:
        # Fallback to role keyword matching for future service types.
        role_text = f"{citizen.get('service_role', '')} {citizen.get('service_building_name', '')} {citizen.get('service_short_label', '')}".lower()
        for key, candidate in type_map.items():
            if str(key).replace("_", " ") in role_text and isinstance(candidate, dict):
                behavior = candidate
                break
    out = copy.deepcopy(default)
    if isinstance(behavior, dict):
        out.update(behavior)
    out["source"] = "service_behavior_rules"
    out["matched_service_type"] = service_type
    return out


def enrich_service_citizen(holoutopia_root: Path | str | None, citizen: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(citizen)
    if not bool(enriched.get("functional_service_assignment")):
        return enriched
    rules = load_service_behavior_rules(holoutopia_root)
    if not bool((rules.get("rules") or {}).get("enabled", True)):
        return enriched
    behavior = behavior_for_citizen(holoutopia_root, enriched)
    short = str(enriched.get("service_short_label") or enriched.get("service_building_name") or "Service")
    action = _brief(behavior.get("action_label") or "using service", 32)
    output = _brief(behavior.get("output_label") or "service active", 32)
    status = _brief(behavior.get("status") or f"using {short}", 34)
    enriched.update({
        "service_behavior_assignment": True,
        "service_operation_id": str(behavior.get("operation_id") or "service_use"),
        "service_action_label": action,
        "service_output_label": output,
        "service_glyph": str(behavior.get("glyph") or "node_tick"),
        "service_operation_source": "runtime_service_behavior_rules",
        "service_operation_confidence": "runtime_resolved",
        "activity_family": str(behavior.get("family") or enriched.get("activity_family") or "activity"),
        "activity_pose": str(behavior.get("pose") or enriched.get("activity_pose") or "idle_activity"),
        "activity_status": status,
        "current_task_readable": status,
    })
    return enriched


def build_service_operation_summary(citizens: dict[str, Any] | list[dict[str, Any]]) -> dict[str, Any]:
    values = citizens.values() if isinstance(citizens, dict) else citizens
    operations: Counter[str] = Counter()
    outputs: Counter[str] = Counter()
    glyphs: Counter[str] = Counter()
    districts: Counter[str] = Counter()
    total = 0
    for citizen in values:
        if not isinstance(citizen, dict) or not bool(citizen.get("functional_service_assignment")):
            continue
        total += 1
        operations[str(citizen.get("service_action_label") or citizen.get("service_operation_id") or "service active")] += 1
        outputs[str(citizen.get("service_output_label") or "service active")] += 1
        glyphs[str(citizen.get("service_glyph") or "node_tick")] += 1
        districts[str(citizen.get("activity_district_display_name") or citizen.get("town_id") or "District")] += 1
    return {
        "schema": 1,
        "id": "holoutopia_service_operation_summary_v1",
        "service_operation_count": total,
        "top_operations": [{"label": k, "count": v} for k, v in operations.most_common(5)],
        "top_outputs": [{"label": k, "count": v} for k, v in outputs.most_common(5)],
        "glyph_counts": dict(sorted(glyphs.items())),
        "district_counts": dict(sorted(districts.items())),
    }


def validate_service_behaviors(holoutopia_root: Path | str | None = None) -> list[str]:
    rules = load_service_behavior_rules(holoutopia_root)
    errors: list[str] = []
    if not bool((rules.get("rules") or {}).get("read_only", False)):
        errors.append("service_behavior_rules_not_read_only")
    type_map = rules.get("building_type_behaviors") if isinstance(rules.get("building_type_behaviors"), dict) else {}
    if len(type_map) < 18:
        errors.append("too_few_service_type_behaviors")
    required_types = {"core_pyramid", "stalls", "factory_bay", "water_plant", "archive_stack", "gatehouse", "ward"}
    missing = sorted(required_types - set(type_map.keys()))
    if missing:
        errors.append("missing_service_type_behaviors:" + ",".join(missing))
    required_fields = {"operation_id", "action_label", "output_label", "pose", "family", "glyph", "status"}
    for key, behavior in type_map.items():
        if not isinstance(behavior, dict):
            errors.append(f"behavior_{key}_not_object")
            continue
        missing_fields = sorted(required_fields - set(behavior.keys()))
        if missing_fields:
            errors.append(f"behavior_{key}_missing:" + ",".join(missing_fields))
        for field in ("action_label", "output_label", "status"):
            if len(str(behavior.get(field) or "")) > 42:
                errors.append(f"behavior_{key}_{field}_too_long")
    sample = {
        "functional_service_assignment": True,
        "service_type": "water_plant",
        "service_short_label": "Water",
        "service_building_name": "Water Purifier",
        "activity_district_display_name": "Harbor Grid",
    }
    enriched = enrich_service_citizen(holoutopia_root, sample)
    if enriched.get("service_operation_id") != "purify_water":
        errors.append("water_plant_did_not_resolve")
    if not enriched.get("service_behavior_assignment"):
        errors.append("service_behavior_assignment_missing")
    if not str(enriched.get("service_output_label") or ""):
        errors.append("service_output_label_missing")
    return errors


def _brief(value: Any, max_chars: int) -> str:
    raw = " ".join(str(value or "").split())
    if len(raw) <= max_chars:
        return raw
    return raw[: max(3, max_chars - 1)].rstrip(" ,.;:") + "…"
