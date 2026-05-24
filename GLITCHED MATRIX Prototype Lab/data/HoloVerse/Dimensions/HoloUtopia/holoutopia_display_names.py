"""Player-facing display-name helpers for HoloUtopia UI panels.

The resolver is data-driven from data/database/utopia/ui plus the authored
citizen, town, neighborhood, and task resources. Runtime panels can keep raw
IDs in their payloads while rendering normal text through this module.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any


UI_DIR_REL = Path("database/utopia/ui")
RAW_ID_PATTERN = re.compile(r"\b(?:npc|citizen|res|core|market|industrial|harbor|archive|security|civic|glitch)[a-z0-9]*_[a-z0-9_]+\b", re.IGNORECASE)
PATH_PATTERN = re.compile(r"(?i)(?:^|\b)(?:data[\\/]|[a-z0-9_. -]+[\\/][a-z0-9_. -]+|[a-z0-9_.-]+\.(?:json|py))")


@dataclass(frozen=True)
class PlayerTextValidation:
    ok: bool
    issues: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "issues": list(self.issues)}


def data_root_from_holoverse(holoverse_root: Path | str | None = None) -> Path:
    root = Path(holoverse_root or Path(__file__).resolve().parent).resolve()
    return root.parent if root.name.lower() in {"holoverse", "holoutopia"} else root


def read_json(path: Path, fallback: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def load_display_name_catalog(holoverse_root: Path | str | None = None) -> dict[str, Any]:
    data_root = data_root_from_holoverse(holoverse_root)
    return read_json(data_root / UI_DIR_REL / "display_name_catalog.json", {"schema": 1, "entities": {}, "labels": {}})


def load_panel_layout(holoverse_root: Path | str | None = None) -> dict[str, Any]:
    data_root = data_root_from_holoverse(holoverse_root)
    return read_json(data_root / UI_DIR_REL / "citizen_panel_layout.json", {"schema": 1, "tabs": ["overview", "tasks", "social"]})


def validate_player_panel_text(text: str) -> PlayerTextValidation:
    issues: list[str] = []
    for match in PATH_PATTERN.finditer(str(text or "")):
        value = match.group(0).strip()
        if value:
            issues.append(f"path-or-filename:{value}")
    for match in RAW_ID_PATTERN.finditer(str(text or "")):
        value = match.group(0).strip()
        if value:
            issues.append(f"raw-id:{value}")
    return PlayerTextValidation(ok=not issues, issues=issues)


class DisplayNameResolver:
    """Resolve internal HoloUtopia IDs to text suitable for normal game UI."""

    def __init__(self, holoverse_root: Path | str | None = None) -> None:
        self.data_root = data_root_from_holoverse(holoverse_root)
        self.catalog = load_display_name_catalog(self.data_root)
        self.names: dict[str, str] = {}
        self.labels: dict[str, dict[str, str]] = {}
        self._load_catalog()
        self._load_authored_resources()

    def resolve(self, value: Any, *, kind: str = "entity", fallback: str = "") -> str:
        raw = str(value or "").strip()
        if not raw:
            return str(fallback or "")
        exact = self.names.get(raw)
        if exact:
            return exact
        labels = self.labels.get(kind, {})
        if raw in labels:
            return labels[raw]
        if kind != "entity":
            entity = self.names.get(raw)
            if entity:
                return entity
        return _humanize_identifier(raw)

    def citizen(self, citizen_id: Any, fallback: str = "") -> str:
        raw = str(citizen_id or "").strip()
        return self.resolve(raw, kind="citizen", fallback=fallback or raw)

    def role(self, role: Any) -> str:
        return self.resolve(role, kind="role")

    def mood(self, mood: Any) -> str:
        return self.resolve(mood, kind="mood")

    def task(self, task_type_or_name: Any, fallback: str = "") -> str:
        return self.resolve(task_type_or_name, kind="task", fallback=fallback)

    def place(self, place_id: Any, fallback: str = "") -> str:
        return self.resolve(place_id, kind="place", fallback=fallback)

    def _load_catalog(self) -> None:
        entities = self.catalog.get("entities") if isinstance(self.catalog.get("entities"), dict) else {}
        for group in entities.values():
            if isinstance(group, dict):
                for raw, label in group.items():
                    self._remember(raw, label)
        labels = self.catalog.get("labels") if isinstance(self.catalog.get("labels"), dict) else {}
        for kind, group in labels.items():
            if not isinstance(group, dict):
                continue
            bucket = self.labels.setdefault(str(kind), {})
            for raw, label in group.items():
                text = str(label or "").strip()
                if text:
                    bucket[str(raw)] = text

    def _load_authored_resources(self) -> None:
        self._load_citizens()
        self._load_task_catalog()
        for folder in ("towns", "neighborhoods", "interiors", "structure_variants"):
            base = self.data_root / "database" / "utopia" / folder
            for path in sorted(base.glob("*.json")):
                self._scan_named_resource(read_json(path, {}))

    def _load_citizens(self) -> None:
        manifest = read_json(self.data_root / "database" / "utopia" / "citizens" / "citizen_manifest.json", {})
        for citizen in list(manifest.get("citizens") or []):
            if not isinstance(citizen, dict):
                continue
            cid = citizen.get("id")
            self._remember(cid, citizen.get("display_name"))
            self._remember(citizen.get("home_lot_id"), _residence_label(citizen))
            self._remember(citizen.get("home_node"), _residence_label(citizen))
            job = citizen.get("job") if isinstance(citizen.get("job"), dict) else {}
            work_title = str(job.get("title") or citizen.get("role") or "").strip()
            if work_title:
                self._remember(job.get("work_node"), work_title)

    def _load_task_catalog(self) -> None:
        catalog = read_json(self.data_root / "database" / "utopia" / "tasks" / "task_type_catalog.json", {})
        task_types = catalog.get("task_types") if isinstance(catalog.get("task_types"), dict) else {}
        bucket = self.labels.setdefault("task", {})
        for task_id, spec in task_types.items():
            if isinstance(spec, dict):
                label = str(spec.get("display_name") or "").strip()
                if label:
                    bucket[str(task_id)] = label
                    self._remember(task_id, label)

    def _scan_named_resource(self, data: Any) -> None:
        if isinstance(data, dict):
            raw_id = data.get("id")
            label = data.get("display_name") or data.get("name") or data.get("address")
            self._remember(raw_id, label)
            block_map = {}
            for block in list(data.get("town_blocks") or []):
                if isinstance(block, dict):
                    block_id = str(block.get("id") or "")
                    block_label = block.get("display_name") or block.get("purpose_summary") or block.get("type")
                    if block_id:
                        block_map[block_id] = _humanize_identifier(str(block_label or block_id))
                        self._remember(block_id, block_map[block_id])
            for node in list(data.get("schedule_nodes") or []) + list(data.get("micro_schedule_nodes") or []):
                if isinstance(node, dict):
                    node_id = node.get("id")
                    label = node.get("display_name") or block_map.get(str(node.get("block") or "")) or node.get("kind")
                    self._remember(node_id, label)
            for key in ("lots", "shared_spaces", "activity_nodes", "rooms", "floor_anchors", "resident_unit_slots"):
                for item in list(data.get(key) or []):
                    if isinstance(item, dict):
                        self._scan_named_resource(item)
            for value in data.values():
                if isinstance(value, (dict, list)):
                    self._scan_named_resource(value)
        elif isinstance(data, list):
            for item in data:
                self._scan_named_resource(item)

    def _remember(self, raw: Any, label: Any) -> None:
        key = str(raw or "").strip()
        text = str(label or "").strip()
        if key and text and key not in self.names:
            self.names[key] = _humanize_identifier(text)


def build_citizen_panel_tabs(
    queue: dict[str, Any],
    *,
    holoverse_root: Path | str | None = None,
    debug_raw_ids: bool = False,
) -> dict[str, Any]:
    """Build a player-facing citizen inspector payload with clean tab text."""
    resolver = DisplayNameResolver(holoverse_root)
    layout = load_panel_layout(holoverse_root)
    tab_order = [str(item) for item in list(layout.get("tabs") or ["overview", "tasks", "social"])]
    current = queue.get("current_task") if isinstance(queue.get("current_task"), dict) else {}
    queued = [item for item in list(queue.get("queued_tasks") or []) if isinstance(item, dict)]
    recent = [item for item in list(queue.get("recent_activity") or []) if isinstance(item, dict)]
    friends = [resolver.citizen(item) for item in list(queue.get("friends") or []) if str(item or "").strip()]
    role = resolver.role(queue.get("role")) or "Citizen"
    job = _title_case_phrase(queue.get("job_title") or queue.get("role") or "Citizen")
    citizen_name = resolver.citizen(queue.get("citizen_id"), fallback=str(queue.get("display_name") or "Citizen"))
    title = f"{citizen_name} — {role}"
    home = resolver.place(queue.get("home_lot_id") or queue.get("home_node")) or "Unassigned home"
    work = resolver.place(queue.get("work_node")) if queue.get("work_node") else job
    current_task = current.get("display_name") or current.get("type") or "Task"
    current_target = resolver.place(current.get("target_node") or queue.get("current_node") or queue.get("route_target")) or "City route"
    visit_reason = str(queue.get("active_visit_reason") or "").strip()
    visit_destination = str(queue.get("active_visit_destination") or "").strip()
    visit_reason_line = f"Reason: {visit_reason}" if visit_reason else ""
    visit_destination_line = f"Visiting: {visit_destination}" if visit_destination else ""
    mood = resolver.mood(queue.get("mood")) or "Neutral"
    energy = _safe_percent(queue.get("energy"))
    purpose = _sentence(queue.get("purpose") or "Living a scheduled civic life.")

    bodies: dict[str, str] = {
        "overview": "\n".join([
            f"{citizen_name}",
            f"{role}  •  Energy {energy}%  •  Mood: {mood}",
            "",
            "Current Focus",
            f"{resolver.task(current_task)}",
            f"at {current_target}",
            *([visit_destination_line] if visit_destination_line else []),
            *([visit_reason_line] if visit_reason_line else []),
            "",
            "Life Setup",
            f"Home: {home}",
            f"Work: {job} at {work}",
            "",
            f"Purpose: {purpose}",
        ]),
        "tasks": _tasks_text(resolver, current, queued),
        "social": _social_text(resolver, friends, recent),
    }
    if debug_raw_ids:
        debug_lines = [
            "",
            "Debug IDs",
            f"citizen_id: {queue.get('citizen_id', '')}",
            f"district: {queue.get('district', '')}",
            f"home_node: {queue.get('home_node', '')}",
            f"work_node: {queue.get('work_node', '')}",
            f"current_node: {queue.get('current_node', '')}",
        ]
        bodies = {key: f"{value}\n" + "\n".join(debug_lines) for key, value in bodies.items()}
    ordered = {tab: bodies[tab] for tab in tab_order if tab in bodies}
    for tab, body in bodies.items():
        ordered.setdefault(tab, body)
    return {
        "title": title,
        "tabs": ordered,
        "default_tab": str(layout.get("default_tab") or "overview"),
        "debug_raw_ids": bool(debug_raw_ids),
    }


def build_building_panel_tabs(
    building: dict[str, Any],
    *,
    holoverse_root: Path | str | None = None,
    debug_raw_ids: bool = False,
) -> dict[str, Any]:
    """Build player-facing Overview / Status / People / Activity tabs for a selected building."""
    from holoutopia_building_gameplay import derive_building_gameplay_state, format_building_gameplay_lines

    resolver = DisplayNameResolver(holoverse_root)
    record = building.get("building") if isinstance(building.get("building"), dict) else building
    if not isinstance(record, dict):
        record = {}
    massing = record.get("massing") if isinstance(record.get("massing"), dict) else {}
    policy = record.get("inspection_policy") if isinstance(record.get("inspection_policy"), dict) else {}
    display_name = resolver.place(record.get("id"), fallback=str(record.get("display_name") or "Building"))
    if not display_name or display_name == _humanize_identifier(str(record.get("id") or "")):
        display_name = _humanize_identifier(str(record.get("display_name") or record.get("address") or record.get("id") or "Building"))
    district = resolver.place(record.get("town_id"), fallback=str(record.get("town_display_name") or "District"))
    purpose = _sentence(record.get("purpose_summary") or record.get("purpose_id") or "City building")
    building_type = _title_case_phrase(massing.get("building_type") or record.get("highlight_kind") or "Structure")
    height = _title_case_phrase(massing.get("height_class") or "low")
    floors = int(massing.get("floor_count", 1) or 1)
    residents = [item for item in list(record.get("residents") or []) if isinstance(item, dict)]
    workers = [item for item in list(record.get("workers") or []) if isinstance(item, dict)]
    active = [item for item in list(record.get("active_citizens") or []) if isinstance(item, dict)]
    schedule_nodes = [item for item in list(record.get("schedule_nodes") or []) if isinstance(item, dict)]
    micro_nodes = [item for item in list(record.get("micro_schedule_nodes") or []) if isinstance(item, dict)]
    affordances = [resolver.task(item) for item in list(record.get("activity_affordances") or []) if str(item or "").strip()]
    interior_policy = str(policy.get("interior_load_policy") or record.get("interior_policy") or "exterior_only").replace("_", " ").title()
    gameplay = derive_building_gameplay_state(record, clock=str(building.get("clock") or "12:00"), danger_state=bool(building.get("danger_state")))
    title = f"{_short_panel_title(display_name, 34)} — {gameplay.get('role', 'Building')}"
    bodies: dict[str, str] = {
        "overview": "\n".join([
            f"{display_name}",
            f"{district}",
            "",
            "Current Site State",
            f"{gameplay.get('state_label', 'Unknown')}  •  {gameplay.get('priority_label', 'Stable')} Priority",
            f"Risk: {gameplay.get('risk_label', 'Secure')}  •  Pressure {gameplay.get('pressure_percent', 0)}%",
            "",
            "Purpose",
            purpose,
            "",
            "Structure",
            f"{building_type}  •  {height}  •  {floors} floors",
            f"Interior: {interior_policy}",
            "",
            "Occupancy",
            f"Residents: {record.get('current_resident_count', 0)} of {record.get('residential_capacity', 0)}",
            f"Workers: {record.get('current_worker_count', 0)}  •  Active now: {record.get('active_citizen_count', 0)}",
        ]),
        "status": "\n".join(format_building_gameplay_lines(gameplay)),
        "people": "\n".join([
            "Residents",
            _people_line(resolver, residents, "No residents assigned."),
            "",
            "Workers",
            _people_line(resolver, workers, "No workers assigned."),
            "",
            "Inside or nearby now",
            _people_line(resolver, active, "Nobody is currently active here."),
        ]),
        "activity": _building_activity_text(resolver, affordances, schedule_nodes, micro_nodes, gameplay),
    }
    if debug_raw_ids:
        debug_lines = [
            "",
            "Debug IDs",
            f"building_id: {record.get('id', '')}",
            f"town_id: {record.get('town_id', '')}",
            f"block_id: {record.get('block_id', '')}",
            f"lot_id: {record.get('lot_id', '')}",
            f"structure_variant_id: {record.get('structure_variant_id', '')}",
        ]
        bodies = {key: f"{value}\n" + "\n".join(debug_lines) for key, value in bodies.items()}
    return {
        "title": title,
        "tabs": bodies,
        "default_tab": "overview",
        "debug_raw_ids": bool(debug_raw_ids),
        "gameplay_state": gameplay,
    }


def _short_panel_title(value: Any, limit: int = 36) -> str:
    text = str(value or "Building").strip()
    if len(text) <= limit:
        return text
    return text[: max(8, limit - 3)].rstrip() + "..."


def _safe_percent(value: Any) -> int:
    try:
        return max(0, min(100, int(round(float(value)))))
    except Exception:
        return 0


def _people_line(resolver: DisplayNameResolver, people: list[dict[str, Any]], fallback: str) -> str:
    if not people:
        return fallback
    names: list[str] = []
    for person in people[:6]:
        name = resolver.citizen(person.get("id"), fallback=str(person.get("display_name") or "Citizen"))
        role = resolver.role(person.get("role") or person.get("job_title"))
        if role:
            names.append(f"{name} ({role})")
        else:
            names.append(name)
    if len(people) > 6:
        names.append(f"+{len(people) - 6} more")
    return ", ".join(names)


def _building_activity_text(
    resolver: DisplayNameResolver,
    affordances: list[str],
    schedule_nodes: list[dict[str, Any]],
    micro_nodes: list[dict[str, Any]],
    gameplay_state: dict[str, Any] | None = None,
) -> str:
    lines = ["Building Activity"]
    if affordances:
        lines.append(", ".join(_title_case_phrase(item) for item in affordances[:8]))
    else:
        lines.append("No authored activity tags yet.")
    lines.extend(["", "Usable Spots"])
    nodes = schedule_nodes + micro_nodes
    if not nodes:
        lines.append("No specific activity spots are exposed.")
    else:
        for node in nodes[:7]:
            name = resolver.place(node.get("id"), fallback=str(node.get("kind") or "Activity Spot"))
            kind = _title_case_phrase(node.get("kind") or "spot")
            lines.append(f"{kind}: {name}")
        if len(nodes) > 7:
            lines.append(f"+{len(nodes) - 7} more spots")
    actions = []
    if isinstance(gameplay_state, dict):
        actions = [str(item) for item in list(gameplay_state.get("local_actions") or []) if str(item).strip()]
    lines.extend(["", "Gameplay Hooks"])
    if actions:
        lines.extend(actions[:4])
    else:
        lines.append("Clicking buildings opens a readable management card for future jobs, upgrades, ownership, and missions.")
    return "\n".join(lines)

def _tasks_text(resolver: DisplayNameResolver, current: dict[str, Any], queued: list[dict[str, Any]]) -> str:
    lines = [
        "Current Task",
        f"{resolver.task(current.get('display_name') or current.get('type') or 'Task')}",
        f"Place: {resolver.place(current.get('target_node'))}",
        f"Why: {_sentence(current.get('purpose') or current.get('reason') or 'Scheduled city routine.')}",
        "",
        "Next Tasks",
    ]
    if not queued:
        lines.append("No queued task is visible.")
        return "\n".join(lines)
    for idx, task in enumerate(queued[:5], start=1):
        label = resolver.task(task.get("display_name") or task.get("type") or "Task")
        target = resolver.place(task.get("target_node"))
        lines.append(f"{idx}. {label} -> {target}")
    return "\n".join(lines)


def _social_text(resolver: DisplayNameResolver, friends: list[str], recent: list[dict[str, Any]]) -> str:
    lines = ["Friends", ", ".join(friends[:6]) if friends else "No friends logged yet.", "", "Recent Activity"]
    if not recent:
        lines.append("No recent activity has been recorded.")
        return "\n".join(lines)
    for item in recent[:5]:
        task = resolver.task(item.get("display_name") or item.get("type") or item.get("activity") or "Activity")
        place = resolver.place(item.get("target_node") or item.get("place"))
        clock = str(item.get("time") or "").strip()
        prefix = f"{clock} - " if clock else ""
        lines.append(f"{prefix}{task} at {place}")
    return "\n".join(lines)


def _humanize_identifier(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = text.replace("/", " or ").replace("-", " ").replace("_", " ")
    text = re.sub(r"\b(?:id|node|json|py)\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip()
    return text.title() if text else ""


def _title_case_phrase(value: Any) -> str:
    text = str(value or "").replace("_", " ").replace("-", " ").strip()
    return text[:1].upper() + text[1:] if text else ""


def _sentence(value: Any) -> str:
    text = str(value or "").replace("/", " or ").replace("_", " ").strip()
    return text[:1].upper() + text[1:] if text else ""


def _residence_label(citizen: dict[str, Any]) -> str:
    name = str(citizen.get("display_name") or "").strip()
    address = str(citizen.get("home_address") or "").strip()
    if name and address:
        return f"{name} Residence"
    if name:
        return f"{name} Residence"
    return address
