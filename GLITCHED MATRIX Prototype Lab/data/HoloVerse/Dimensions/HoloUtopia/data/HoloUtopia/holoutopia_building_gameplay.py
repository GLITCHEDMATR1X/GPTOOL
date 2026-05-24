"""Player-facing gameplay state derived from HoloUtopia building inspection records.

This module intentionally stays read-only.  It turns authored building/citizen
inspection data into a small management-game card: current state, pressure,
priority, civic value, and safe local action hooks.  Nothing here writes saves,
logs, authored JSON, collision, or routes.
"""
from __future__ import annotations

from typing import Any


def derive_building_gameplay_state(record: dict[str, Any], *, clock: str = "12:00", danger_state: bool = False) -> dict[str, Any]:
    """Return a compact JSON-safe gameplay state for a selected building."""
    if not isinstance(record, dict):
        record = {}
    kind = str(record.get("highlight_kind") or "building")
    district_type = str(record.get("district_type") or "").lower()
    purpose_id = str(record.get("purpose_id") or "").lower()
    purpose_summary = str(record.get("purpose_summary") or "").lower()
    massing = record.get("massing") if isinstance(record.get("massing"), dict) else {}
    residents = _int(record.get("current_resident_count"))
    capacity = _int(record.get("residential_capacity"))
    workers = _int(record.get("current_worker_count"))
    active = _int(record.get("active_citizen_count"))
    floors = max(1, _int(massing.get("floor_count"), 1))
    open_slots = max(0, capacity - residents)

    building_role = _building_role(kind, district_type, purpose_id, purpose_summary)
    occupancy_ratio = (residents / capacity) if capacity > 0 else 0.0
    activity_ratio = min(1.0, active / max(1.0, workers + residents * 0.35 + 2.0))
    worker_pressure = 0.0
    if kind == "district_block" and workers <= 0:
        worker_pressure = 0.42
    elif workers > 0 and active <= 0:
        worker_pressure = 0.18

    pressure = 0.0
    pressure += 0.34 if danger_state else 0.0
    pressure += max(0.0, occupancy_ratio - 0.82) * 0.75
    pressure += activity_ratio * 0.32
    pressure += worker_pressure
    if "security" in district_type or "guard" in purpose_summary:
        pressure += 0.10 if danger_state else -0.06
    if "quarantine" in district_type or "recovery" in purpose_summary:
        pressure += 0.08
    pressure = max(0.0, min(1.0, pressure))

    priority = _priority_label(pressure)
    state_label = _state_label(kind, danger_state, occupancy_ratio, active, workers, capacity)
    risk_label = _risk_label(danger_state, pressure, district_type, purpose_summary)
    civic_value = max(5, min(100, int(round(24 + residents * 1.1 + workers * 4.0 + active * 6.0 + floors * 2.0 - pressure * 12.0))))
    need_lines = _need_lines(kind, capacity, residents, open_slots, workers, active, danger_state, risk_label)
    action_lines = _action_lines(building_role, priority, risk_label, need_lines)
    story_hook = _story_hook(building_role, state_label, priority, open_slots, workers, active)

    return {
        "schema": 1,
        "id": "holoutopia_building_gameplay_state_v1",
        "clock": str(clock or "12:00"),
        "building_id": str(record.get("id") or ""),
        "role": building_role,
        "state_label": state_label,
        "priority_label": priority,
        "risk_label": risk_label,
        "pressure_percent": int(round(pressure * 100.0)),
        "civic_value": civic_value,
        "resident_count": residents,
        "residential_capacity": capacity,
        "open_residential_slots": open_slots,
        "worker_count": workers,
        "active_citizen_count": active,
        "management_tags": _management_tags(building_role, district_type, purpose_id, kind),
        "needs": need_lines,
        "local_actions": action_lines,
        "story_hook": story_hook,
        "runtime_writes_allowed": False,
    }


def format_building_gameplay_lines(state: dict[str, Any], *, max_actions: int = 4) -> list[str]:
    """Format the gameplay state as readable panel lines."""
    if not isinstance(state, dict):
        state = {}
    tags = [str(t) for t in list(state.get("management_tags") or []) if str(t).strip()]
    needs = [str(t) for t in list(state.get("needs") or []) if str(t).strip()]
    actions = [str(t) for t in list(state.get("local_actions") or []) if str(t).strip()]
    lines = [
        "Site Status",
        f"State: {state.get('state_label', 'Unknown')}  •  Priority: {state.get('priority_label', 'Normal')}",
        f"Risk: {state.get('risk_label', 'Secure')}  •  Pressure: {state.get('pressure_percent', 0)}%  •  Civic Value: {state.get('civic_value', 0)}",
        f"Role: {state.get('role', 'City Site')}",
    ]
    if tags:
        lines.append("Tags: " + ", ".join(tags[:5]))
    lines.extend(["", "Needs"])
    lines.extend(needs[:5] if needs else ["No urgent need detected."])
    lines.extend(["", "Local Actions"])
    lines.extend(actions[:max_actions] if actions else ["No action hooks available."])
    hook = str(state.get("story_hook") or "").strip()
    if hook:
        lines.extend(["", "Story Hook", hook])
    return lines


def validate_building_gameplay_state(state: dict[str, Any]) -> list[str]:
    """Return validation issues for safe, game-facing building state."""
    issues: list[str] = []
    if not isinstance(state, dict):
        return ["state_not_dict"]
    for key in ("state_label", "priority_label", "risk_label", "pressure_percent", "civic_value", "needs", "local_actions"):
        if key not in state:
            issues.append(f"missing:{key}")
    if bool(state.get("runtime_writes_allowed")):
        issues.append("runtime_writes_allowed_true")
    pressure = _int(state.get("pressure_percent"), -1)
    if pressure < 0 or pressure > 100:
        issues.append("pressure_out_of_range")
    civic = _int(state.get("civic_value"), -1)
    if civic < 0 or civic > 100:
        issues.append("civic_value_out_of_range")
    text = "\n".join(str(x) for x in [state.get("state_label"), state.get("priority_label"), state.get("risk_label"), *(state.get("needs") or []), *(state.get("local_actions") or [])])
    if "_" in text or "/" in text:
        issues.append("raw_identifier_leak")
    return issues


def _building_role(kind: str, district_type: str, purpose_id: str, purpose_summary: str) -> str:
    text = f"{kind} {district_type} {purpose_id} {purpose_summary}".lower()
    if "residential" in text or "home" in text or "housing" in text:
        return "Housing"
    if "market" in text or "vendor" in text or "trade" in text:
        return "Commerce"
    if "security" in text or "guard" in text or "gate" in text:
        return "Security"
    if "harbor" in text or "water" in text or "tide" in text:
        return "Infrastructure"
    if "archive" in text or "school" in text or "research" in text or "reader" in text:
        return "Knowledge"
    if "quarantine" in text or "clinic" in text or "recovery" in text or "triage" in text:
        return "Medical"
    if "industrial" in text or "workshop" in text or "forge" in text or "yard" in text:
        return "Industry"
    if "civic" in text or "plaza" in text or "commons" in text or "core" in text:
        return "Civic"
    return "City Site"


def _priority_label(pressure: float) -> str:
    if pressure >= 0.72:
        return "Critical"
    if pressure >= 0.48:
        return "High"
    if pressure >= 0.25:
        return "Watch"
    return "Stable"


def _state_label(kind: str, danger: bool, occupancy_ratio: float, active: int, workers: int, capacity: int) -> str:
    if danger:
        return "Emergency Mode"
    if capacity > 0 and occupancy_ratio >= 0.96:
        return "At Capacity"
    if capacity > 0 and occupancy_ratio <= 0.25:
        return "Underused"
    if active >= 6:
        return "Crowded"
    if active >= 2:
        return "Busy"
    if workers > 0:
        return "Staffed"
    if kind == "district_block":
        return "Quiet"
    return "Calm"


def _risk_label(danger: bool, pressure: float, district_type: str, purpose_summary: str) -> str:
    if danger:
        return "City Alert"
    if pressure >= 0.72:
        return "Unstable"
    if pressure >= 0.48:
        return "Needs Watch"
    if "security" in district_type or "guard" in purpose_summary:
        return "Secured"
    return "Secure"


def _need_lines(kind: str, capacity: int, residents: int, open_slots: int, workers: int, active: int, danger: bool, risk_label: str) -> list[str]:
    needs: list[str] = []
    if danger:
        needs.append("Move civilians toward safe routes and watch posts.")
    if capacity > 0:
        if open_slots <= 0:
            needs.append("Housing is full; expansion or relocation would help.")
        elif residents == 0:
            needs.append("Empty housing could accept new residents.")
        else:
            needs.append(f"Housing has {open_slots} open slots.")
    if kind == "district_block" and workers <= 0:
        needs.append("No assigned workers are attached to this site yet.")
    elif workers > 0 and active <= 0:
        needs.append("Staff exists, but nobody is active here right now.")
    elif active > 0:
        needs.append(f"{active} citizens are using or passing this site now.")
    if risk_label in {"Unstable", "Needs Watch", "City Alert"}:
        needs.append("Mark this site for patrol and service follow-up.")
    return needs[:5]


def _action_lines(role: str, priority: str, risk_label: str, needs: list[str]) -> list[str]:
    actions = ["Track this site on the city view."]
    if priority in {"Critical", "High"} or risk_label in {"Unstable", "Needs Watch", "City Alert"}:
        actions.append("Flag for the next service or guard route.")
    if role == "Housing":
        actions.append("Review residents and future housing capacity.")
    elif role in {"Commerce", "Industry", "Infrastructure"}:
        actions.append("Review assigned workers and activity spots.")
    elif role == "Security":
        actions.append("Review active guards and local threat coverage.")
    elif role in {"Medical", "Knowledge", "Civic"}:
        actions.append("Review public activity and civic support value.")
    if needs:
        actions.append("Open People or Activity tabs for details.")
    return actions[:5]


def _story_hook(role: str, state_label: str, priority: str, open_slots: int, workers: int, active: int) -> str:
    if priority in {"Critical", "High"}:
        return f"This {role.lower()} site is pulling attention from the city simulation."
    if role == "Housing" and open_slots > 0:
        return "This residence can still absorb future population growth."
    if workers > 0 and active > 0:
        return "Workers and citizens are already giving this site visible life."
    if state_label in {"Quiet", "Calm", "Underused"}:
        return "This is a good candidate for a future mission, upgrade, or citizen assignment."
    return "This site can become a mission node once city-management actions are expanded."


def _management_tags(role: str, district_type: str, purpose_id: str, kind: str) -> list[str]:
    tags = [role]
    if kind == "residential_lot":
        tags.append("Inspectable Home")
    else:
        tags.append("District Site")
    district = district_type.replace("_", " ").replace("-", " ").strip().title()
    if district and district not in tags:
        tags.append(district)
    purpose = purpose_id.replace("_", " ").replace("-", " ").strip().title()
    if purpose and purpose not in tags and len(purpose) <= 26:
        tags.append(purpose)
    return tags[:5]


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(round(float(value)))
    except Exception:
        return int(default)
