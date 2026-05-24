"""Inspector presentation helpers for HoloUtopia city AI snapshots.

This file does not depend on Panda3D UI classes. It returns plain strings and
small dictionaries so it can be adapted to the current movable/snappable panel
system without a broad UI rewrite.
"""

from __future__ import annotations

import re
from typing import Any

_RAW_ID_PATTERNS = (
    re.compile(r"\bcitizen_[a-z0-9_]+\b", re.IGNORECASE),
    re.compile(r"\bnode_[a-z0-9_]+\b", re.IGNORECASE),
    re.compile(r"\btask_[a-z0-9_]+\b", re.IGNORECASE),
    re.compile(r"\broute_[a-z0-9_]+\b", re.IGNORECASE),
)


def clean_player_text(value: Any, fallback: str = "Unknown") -> str:
    text = str(value or "").strip()
    if not text:
        return fallback
    for pattern in _RAW_ID_PATTERNS:
        text = pattern.sub(lambda m: m.group(0).replace("_", " ").title(), text)
    text = text.replace("Citizen ", "") if text.startswith("Citizen ") else text
    return text


def _bar(value: Any, width: int = 10) -> str:
    try:
        number = max(0, min(100, int(round(float(value)))))
    except (TypeError, ValueError):
        number = 50
    filled = round((number / 100) * width)
    return "#" * filled + "-" * (width - filled) + f" {number}%"


def format_memory_line(memory: dict[str, Any], *, debug: bool = False) -> str:
    kind = clean_player_text(memory.get("kind"), "Memory")
    summary = clean_player_text(memory.get("summary"), "Something changed.")
    if debug:
        return f"{kind}: {summary} [{memory.get('event_id', 'no-id')}]"
    return f"{kind}: {summary}"


def build_inspector_tabs(snapshot: dict[str, Any], *, debug: bool = False) -> dict[str, list[str]]:
    mood = dict(snapshot.get("mood") or {})
    memories = list(snapshot.get("recent_memories") or [])

    overview = [
        clean_player_text(snapshot.get("name"), "Citizen"),
        clean_player_text(snapshot.get("role"), "Resident"),
        f"District: {clean_player_text(snapshot.get('district'), 'Unknown District')}",
        f"Intent: {clean_player_text(snapshot.get('intent_hint'), 'Observe City')}",
        "",
        "Current Thought",
        clean_player_text(snapshot.get("current_thought"), "Watching the city."),
    ]

    mood_lines = [
        f"Focus  {_bar(mood.get('focus', 55))}",
        f"Energy {_bar(mood.get('energy', 72))}",
        f"Trust  {_bar(mood.get('trust', 64))}",
        f"Stress {_bar(mood.get('stress', 28))}",
        f"Wonder {_bar(mood.get('curiosity', 48))}",
    ]

    thoughts = [
        "City Pressure",
        clean_player_text(snapshot.get("district_status"), "The city is calm."),
        "",
        "Recent Memories",
    ]
    if memories:
        thoughts.extend(format_memory_line(memory, debug=debug) for memory in memories[:5])
    else:
        thoughts.append("No major memory fragments yet.")

    social = ["Strengths"]
    social.extend(f"• {clean_player_text(item)}" for item in snapshot.get("strengths", [])[:3])
    social.append("")
    social.append("Weaknesses")
    social.extend(f"• {clean_player_text(item)}" for item in snapshot.get("weaknesses", [])[:2])

    tabs = {
        "Overview": overview,
        "Mood": mood_lines,
        "Thoughts": thoughts,
        "Social": social,
    }
    if debug and snapshot.get("debug"):
        debug_data = dict(snapshot["debug"])
        tabs["Debug"] = [f"{key}: {value}" for key, value in debug_data.items()]
    return tabs


def flatten_tabs_for_legacy_panel(tabs: dict[str, list[str]]) -> list[str]:
    """Flatten tab content for older single-column panels."""
    lines: list[str] = []
    for tab_name, tab_lines in tabs.items():
        lines.append(f"[{tab_name}]")
        lines.extend(tab_lines)
        lines.append("")
    while lines and lines[-1] == "":
        lines.pop()
    return lines


def assert_no_raw_ids_in_player_tabs(tabs: dict[str, list[str]]) -> None:
    joined = "\n".join(line for key, values in tabs.items() if key != "Debug" for line in values)
    for pattern in _RAW_ID_PATTERNS:
        match = pattern.search(joined)
        if match:
            raise AssertionError(f"Raw internal ID leaked into player UI: {match.group(0)}")
