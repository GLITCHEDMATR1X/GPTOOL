"""HoloUtopia citizen purpose and task queue helpers.

This module stays data-first and runtime-safe:
- authored citizen/schedule/task files are read-only;
- generated queues are JSON-safe snapshots;
- live runtime panels read these queues but do not mutate authored identity data.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any


TASKS_DIR_REL = Path("database/utopia/tasks")
SAVES_DIR_REL = Path("database/utopia/saves")
DEFAULT_CLOCK = "08:00"
ACTIVITY_ALIASES = {
    "leave_home": "commute",
    "work": "work_shift",
    "social_pause": "meal_break",
    "personal_activity": "hobby",
    "seek_nearest_shelter_or_guard_route": "danger_override",
}


@dataclass(frozen=True)
class CitizenTaskSummary:
    citizen_count: int
    queue_count: int
    task_type_count: int
    current_clock: str
    max_queue_depth: int
    authored_files_read_only: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "citizen_count": self.citizen_count,
            "queue_count": self.queue_count,
            "task_type_count": self.task_type_count,
            "current_clock": self.current_clock,
            "max_queue_depth": self.max_queue_depth,
            "authored_files_read_only": self.authored_files_read_only,
        }


def data_root_from_holoverse(holoverse_root: Path | str | None = None) -> Path:
    root = Path(holoverse_root or Path(__file__).resolve().parent).resolve()
    if (root / "database" / "utopia").exists():
        return root
    if (root / "data" / "database" / "utopia").exists():
        return root / "data"
    if (root.parent / "database" / "utopia").exists():
        return root.parent
    return root.parent if root.name.lower() in {"holoverse", "holoutopia"} else root


def read_json(path: Path, fallback: Any) -> Any:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data
    except Exception:
        return fallback


def load_task_catalog(holoverse_root: Path | str | None = None) -> dict[str, Any]:
    data_root = data_root_from_holoverse(holoverse_root)
    return read_json(data_root / TASKS_DIR_REL / "task_type_catalog.json", {"schema": 1, "task_types": {}})


def load_task_rules(holoverse_root: Path | str | None = None) -> dict[str, Any]:
    data_root = data_root_from_holoverse(holoverse_root)
    return read_json(data_root / TASKS_DIR_REL / "citizen_task_rules.json", {"schema": 1, "queue_policy": {}, "purpose_templates": {}})


def load_task_inputs(holoverse_root: Path | str | None = None) -> dict[str, Any]:
    from holoutopia_citizen_simulation import load_simulation_inputs

    sim_inputs = load_simulation_inputs(holoverse_root)
    return {
        **sim_inputs,
        "task_catalog": load_task_catalog(holoverse_root),
        "task_rules": load_task_rules(holoverse_root),
    }


def build_all_citizen_task_queues(
    holoverse_root: Path | str | None = None,
    *,
    clock: str = DEFAULT_CLOCK,
    danger_state: bool = False,
    inputs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a JSON-safe queue snapshot for every authored citizen."""
    from holoutopia_citizen_simulation import simulate_city_at_time

    inputs = inputs if isinstance(inputs, dict) else load_task_inputs(holoverse_root)
    frame = simulate_city_at_time(holoverse_root, clock, danger_state=danger_state, inputs=inputs)
    manifest = inputs.get("citizen_manifest", {}) if isinstance(inputs.get("citizen_manifest"), dict) else {}
    schedules = inputs.get("citizen_schedules", {}).get("schedules", {}) if isinstance(inputs.get("citizen_schedules"), dict) else {}
    relationships = inputs.get("citizen_relationships", {}) if isinstance(inputs.get("citizen_relationships"), dict) else {}
    catalog = inputs.get("task_catalog", {}) if isinstance(inputs.get("task_catalog"), dict) else {}
    rules = inputs.get("task_rules", {}) if isinstance(inputs.get("task_rules"), dict) else {}
    citizens_frame = frame.get("citizens", {}) if isinstance(frame.get("citizens"), dict) else {}
    queues: dict[str, Any] = {}
    for citizen in list(manifest.get("citizens", []) or []):
        if not isinstance(citizen, dict):
            continue
        cid = str(citizen.get("id") or "").strip()
        if not cid:
            continue
        queues[cid] = build_citizen_task_queue(
            citizen,
            schedules.get(cid) if isinstance(schedules, dict) else {},
            relationships,
            catalog,
            rules,
            frame_citizen=citizens_frame.get(cid, {}),
            clock=clock,
            danger_state=danger_state,
        )
    task_type_count = len(catalog.get("task_types", {}) if isinstance(catalog.get("task_types"), dict) else {})
    return {
        "schema": 1,
        "id": "holoutopia_citizen_task_queue_seed_v1",
        "clock": str(clock),
        "danger_state": bool(danger_state),
        "authored_source": "generated_from_citizen_manifest_and_schedules",
        "runtime_writes_allowed": True,
        "authoring_files_read_only": True,
        "citizen_count": len(queues),
        "task_type_count": task_type_count,
        "queues": queues,
    }


def build_citizen_task_queue(
    citizen: dict[str, Any],
    schedule: dict[str, Any] | None,
    relationships: dict[str, Any] | None,
    catalog: dict[str, Any] | None,
    rules: dict[str, Any] | None,
    *,
    frame_citizen: dict[str, Any] | None = None,
    clock: str = DEFAULT_CLOCK,
    danger_state: bool = False,
) -> dict[str, Any]:
    """Build a readable queue for a single citizen from authored schedule data."""
    cid = str(citizen.get("id") or "unknown_citizen")
    schedule = schedule if isinstance(schedule, dict) else {}
    frame_citizen = frame_citizen if isinstance(frame_citizen, dict) else {}
    catalog = catalog if isinstance(catalog, dict) else {}
    rules = rules if isinstance(rules, dict) else {}
    task_types = catalog.get("task_types") if isinstance(catalog.get("task_types"), dict) else {}
    blocks = list(schedule.get("blocks") if isinstance(schedule.get("blocks"), list) else [])
    index = int(frame_citizen.get("schedule_index", _schedule_index_for_clock(blocks, clock)) or 0)
    if blocks:
        index = max(0, min(index, len(blocks) - 1))
    active_block = dict(blocks[index] if blocks else {})
    civic_visit = frame_citizen.get("civic_visit") if isinstance(frame_citizen.get("civic_visit"), dict) else None
    if isinstance(civic_visit, dict) and not danger_state:
        active_block = {
            "time": clock,
            "action": str(civic_visit.get("action") or "district_visit"),
            "target": str(civic_visit.get("target_node") or frame_citizen.get("resolved_node") or ""),
            "activity_id": str(civic_visit.get("activity_id") or "district_errand"),
            "duration_minutes": int(civic_visit.get("duration_minutes") or 45),
            "visibility": "public_schedule",
            "interruptible": True,
            "reason": str(civic_visit.get("reason") or "Civic errand"),
            "destination_display_name": str(civic_visit.get("destination_display_name") or frame_citizen.get("visit_destination") or ""),
        }
    if danger_state and isinstance(schedule.get("danger_override"), dict):
        active_block = dict(schedule.get("danger_override") or {})
        active_block.setdefault("activity_id", "danger_override")
        active_block.setdefault("action", "seek_shelter")
    active_activity = _canonical_activity_id(active_block.get("activity_id") or frame_citizen.get("activity_id") or active_block.get("action") or "district_errand")
    current_task = _task_from_block(
        cid,
        active_block,
        task_types,
        citizen=citizen,
        task_index=0,
        role_context=True,
        clock=clock,
        active=True,
    )
    queued_tasks = []
    if blocks:
        lookahead = _queue_policy_int(rules, "max_visible_next_tasks", 5)
        for offset in range(1, lookahead + 1):
            block = dict(blocks[(index + offset) % len(blocks)])
            queued_tasks.append(_task_from_block(cid, block, task_types, citizen=citizen, task_index=offset, clock=clock, active=False))
    # Make the social/purpose layer explicit even when a schedule has no friend block yet.
    friends = _friend_ids(citizen, relationships)
    if friends and not any(str(item.get("type")) == "visit_friend" for item in queued_tasks):
        friend_id = friends[0]
        queued_tasks.append({
            "task_id": f"{cid}_friend_check_{friend_id}",
            "type": "visit_friend",
            "display_name": "Friend Check",
            "reason": "friend_social_link",
            "target_node": str(frame_citizen.get("resolved_node") or citizen.get("home_node") or "social_node_pending"),
            "target_friend": friend_id,
            "status": "queued",
            "priority": int(_task_type(task_types, "visit_friend").get("default_priority", 50)),
            "interruptible": True,
        })
    energy = _energy_for(citizen, active_activity, danger_state)
    mood = _mood_for(active_activity, energy, danger_state)
    role = str(citizen.get("role") or citizen.get("job", {}).get("title") or "citizen")
    return {
        "citizen_id": cid,
        "display_name": str(citizen.get("display_name") or cid),
        "role": role,
        "purpose": _purpose_for(citizen, rules),
        "district": str(citizen.get("town_id") or "unknown_district"),
        "active_visit_destination": str(civic_visit.get("destination_display_name") or "") if isinstance(civic_visit, dict) else "",
        "active_visit_reason": str(civic_visit.get("reason") or "") if isinstance(civic_visit, dict) else "",
        "home_lot_id": str(citizen.get("home_lot_id") or ""),
        "home_node": str(citizen.get("home_node") or ""),
        "job_title": str((citizen.get("job") or {}).get("title") or role),
        "work_node": str((citizen.get("job") or {}).get("work_node") or ""),
        "clock": str(clock),
        "mood": mood,
        "energy": energy,
        "current_task": current_task,
        "queued_tasks": queued_tasks[: max(1, _queue_policy_int(rules, "max_visible_next_tasks", 5))],
        "friends": friends[:6],
        "recent_activity": _recent_activity_for(blocks, index, task_types, citizen=citizen, clock=clock),
        "current_activity_id": active_activity,
        "current_node": str(frame_citizen.get("resolved_node") or current_task.get("target_node") or ""),
        "route_target": str(current_task.get("target_node") or frame_citizen.get("target_node") or ""),
        "visibility": str(frame_citizen.get("location_mode") or active_block.get("visibility") or "public_schedule"),
        "safe_edit_note": "Runtime task status can be copied into saves; authored citizen identity and schedules stay read-only.",
    }


def citizen_panel_payload(
    holoverse_root: Path | str | None,
    citizen_id: str,
    *,
    clock: str = DEFAULT_CLOCK,
    danger_state: bool = False,
    frame_citizen: dict[str, Any] | None = None,
    inputs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the data shown in the movable in-game citizen inspector panel."""
    inputs = inputs if isinstance(inputs, dict) else load_task_inputs(holoverse_root)
    manifest = inputs.get("citizen_manifest", {}) if isinstance(inputs.get("citizen_manifest"), dict) else {}
    citizens = {str(item.get("id")): item for item in list(manifest.get("citizens", []) or []) if isinstance(item, dict)}
    citizen = citizens.get(str(citizen_id))
    if citizen is None:
        return {"ok": False, "error": f"citizen-not-found:{citizen_id}", "citizen_id": str(citizen_id)}
    schedules = inputs.get("citizen_schedules", {}).get("schedules", {}) if isinstance(inputs.get("citizen_schedules"), dict) else {}
    queue = build_citizen_task_queue(
        citizen,
        schedules.get(str(citizen_id), {}),
        inputs.get("citizen_relationships", {}),
        inputs.get("task_catalog", {}),
        inputs.get("task_rules", {}),
        frame_citizen=frame_citizen,
        clock=clock,
        danger_state=danger_state,
    )
    return {"ok": True, "kind": "citizen_inspector", "queue": queue}


def build_task_summary(holoverse_root: Path | str | None = None, *, clock: str = DEFAULT_CLOCK) -> CitizenTaskSummary:
    inputs = load_task_inputs(holoverse_root)
    snapshot = build_all_citizen_task_queues(holoverse_root, clock=clock, inputs=inputs)
    queues = snapshot.get("queues", {}) if isinstance(snapshot.get("queues"), dict) else {}
    max_depth = max((1 + len((q.get("queued_tasks") or [])) for q in queues.values() if isinstance(q, dict)), default=0)
    task_types = inputs.get("task_catalog", {}).get("task_types", {}) if isinstance(inputs.get("task_catalog"), dict) else {}
    return CitizenTaskSummary(
        citizen_count=int(snapshot.get("citizen_count", 0) or 0),
        queue_count=len(queues),
        task_type_count=len(task_types),
        current_clock=str(clock),
        max_queue_depth=max_depth,
        authored_files_read_only=True,
    )


def write_task_queue_seed(holoverse_root: Path | str | None = None, *, clock: str = DEFAULT_CLOCK) -> Path:
    data_root = data_root_from_holoverse(holoverse_root)
    out = data_root / SAVES_DIR_REL / "citizen_task_queue_seed.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    snapshot = build_all_citizen_task_queues(holoverse_root, clock=clock)
    out.write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")
    return out


def _task_from_block(
    cid: str,
    block: dict[str, Any],
    task_types: dict[str, Any],
    *,
    citizen: dict[str, Any],
    task_index: int,
    clock: str,
    active: bool,
    role_context: bool = False,
) -> dict[str, Any]:
    activity = _canonical_activity_id(block.get("activity_id") or block.get("action") or "district_errand")
    spec = _task_type(task_types, activity)
    action = str(block.get("action") or activity)
    job_title = str((citizen.get("job") or {}).get("title") or citizen.get("role") or "citizen")
    display = str(spec.get("display_name") or action.replace("_", " ").title())
    if role_context and activity == "work_shift" and job_title:
        display = f"{display}: {job_title}"
    if role_context and activity == "district_errand" and block.get("destination_display_name"):
        display = f"{display}: {block.get('destination_display_name')}"
    return {
        "task_id": f"{cid}_{task_index:02d}_{activity}",
        "type": activity,
        "display_name": display,
        "action": action,
        "target_node": str(block.get("target") or ""),
        "status": "active" if active else "queued",
        "priority": int(spec.get("default_priority", 50) or 50) + (8 if active else 0),
        "duration_minutes": int(float(block.get("duration_minutes", 30) or 30)),
        "interruptible": bool(block.get("interruptible", spec.get("interruptible", True))),
        "reason": _reason_for_activity(activity, citizen, block, clock),
        "visibility": str(block.get("visibility") or "public_schedule"),
        "purpose": str(spec.get("purpose") or "Scheduled civic activity."),
    }


def _task_type(task_types: dict[str, Any], activity: str) -> dict[str, Any]:
    if not isinstance(task_types, dict):
        return {}
    return dict(task_types.get(str(activity)) or task_types.get("district_errand") or {})


def _canonical_activity_id(value: Any) -> str:
    raw = str(value or "district_errand")
    return ACTIVITY_ALIASES.get(raw, raw)


def _recent_activity_for(
    blocks: list[dict[str, Any]],
    index: int,
    task_types: dict[str, Any],
    *,
    citizen: dict[str, Any],
    clock: str,
) -> list[dict[str, Any]]:
    if not blocks:
        return []
    recent: list[dict[str, Any]] = []
    for offset in range(3, 0, -1):
        block = dict(blocks[(index - offset) % len(blocks)])
        activity = _canonical_activity_id(block.get("activity_id") or block.get("action") or "district_errand")
        spec = _task_type(task_types, activity)
        recent.append({
            "time": str(block.get("time") or clock),
            "type": activity,
            "display_name": str(spec.get("display_name") or activity.replace("_", " ").title()),
            "target_node": str(block.get("target") or ""),
            "status": "completed_recently",
            "reason": _reason_for_activity(activity, citizen, block, clock),
        })
    return recent


def _purpose_for(citizen: dict[str, Any], rules: dict[str, Any]) -> str:
    role = str(citizen.get("role") or "").lower()
    job_title = str((citizen.get("job") or {}).get("title") or "").lower()
    templates = rules.get("purpose_templates") if isinstance(rules.get("purpose_templates"), dict) else {}
    for token, purpose in templates.items():
        t = str(token).lower()
        if t and (t in role or t in job_title):
            return str(purpose)
    return str(templates.get("default") or "Live a scheduled civic life while supporting the district simulation.")


def _reason_for_activity(activity: str, citizen: dict[str, Any], block: dict[str, Any], clock: str) -> str:
    activity = str(activity).lower()
    if activity == "work_shift":
        return f"job:{(citizen.get('job') or {}).get('title', citizen.get('role', 'citizen'))}"
    if activity in {"commute", "return_home"}:
        return "daily_schedule_route"
    if activity in {"meal_break", "visit_friend"}:
        return "social_and_energy_need"
    if activity == "hobby":
        life = citizen.get("life_profile") if isinstance(citizen.get("life_profile"), dict) else {}
        return f"preferred_activity:{life.get('preferred_activity', 'personal')}; clock:{clock}"
    if activity == "danger_override":
        return "city_alert_override"
    if activity == "district_errand" and block.get("destination_display_name"):
        reason = str(block.get("reason") or "civic_visit")
        return f"{reason}; destination:{block.get('destination_display_name')}"
    return str(block.get("reason") or "authored_schedule")


def _energy_for(citizen: dict[str, Any], activity: str, danger_state: bool) -> int:
    if danger_state:
        return 48
    personality = citizen.get("personality") if isinstance(citizen.get("personality"), dict) else {}
    discipline = float(personality.get("discipline", 0.55) or 0.55)
    ambition = float(personality.get("ambition", 0.50) or 0.50)
    base = 58 + int(discipline * 22) + int(ambition * 12)
    activity = str(activity).lower()
    if activity in {"sleep", "return_home"}:
        base = min(100, base + 8)
    if activity == "work_shift":
        base = max(25, base - 10)
    if activity in {"meal_break", "hobby"}:
        base = min(100, base + 4)
    return max(0, min(100, int(base)))


def _mood_for(activity: str, energy: int, danger_state: bool) -> str:
    if danger_state:
        return "alert"
    activity = str(activity).lower()
    if energy < 35:
        return "tired"
    if activity == "work_shift":
        return "focused"
    if activity in {"meal_break", "visit_friend"}:
        return "social"
    if activity == "hobby":
        return "curious"
    if activity in {"return_home", "sleep"}:
        return "settling"
    if activity == "commute":
        return "in_transit"
    return "steady"


def _friend_ids(citizen: dict[str, Any], relationships: dict[str, Any] | None) -> list[str]:
    friends = []
    for raw in list(citizen.get("friends") or []):
        value = str(raw or "").strip()
        if value and value not in friends:
            friends.append(value)
    if isinstance(relationships, dict):
        rels = relationships.get(str(citizen.get("id")))
        if isinstance(rels, dict):
            for raw in list(rels.get("friends") or rels.get("trusted") or []):
                value = str(raw or "").strip()
                if value and value not in friends:
                    friends.append(value)
    return friends


def _schedule_index_for_clock(blocks: list[dict[str, Any]], clock: str) -> int:
    if not blocks:
        return 0
    target_minutes = _clock_minutes(clock)
    best = 0
    best_minutes = -1
    for idx, block in enumerate(blocks):
        minutes = _clock_minutes(str(block.get("time") or "00:00"))
        if minutes <= target_minutes and minutes >= best_minutes:
            best = idx
            best_minutes = minutes
    return best


def _clock_minutes(clock: str) -> int:
    try:
        hh, mm = [int(part) for part in str(clock or "00:00").split(":", 1)]
        return max(0, min(23 * 60 + 59, hh * 60 + mm))
    except Exception:
        return 0


def _queue_policy_int(rules: dict[str, Any], key: str, default: int) -> int:
    policy = rules.get("queue_policy") if isinstance(rules.get("queue_policy"), dict) else {}
    try:
        return int(float(policy.get(key, default)))
    except Exception:
        return int(default)
