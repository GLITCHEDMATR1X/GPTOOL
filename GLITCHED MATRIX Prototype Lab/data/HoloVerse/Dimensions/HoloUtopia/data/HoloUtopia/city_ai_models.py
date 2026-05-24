"""HoloUtopia city AI model loader.

Pass 30 updates:
- Keeps the Pass 29 model API stable.
- Uses stable SHA-based seeding instead of Python's randomized hash().
- Adds safe helpers for mood clamping and player-facing labels.

This module is pure-data and deterministic. It performs no external AI calls and
should not write files during frame updates.
"""

from __future__ import annotations

import hashlib
import json
import random
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_RAW_ID_PREFIXES = (
    "citizen_",
    "district_",
    "node_",
    "task_",
    "route_",
    "res_",
    "work_",
    "home_",
)


@dataclass(frozen=True)
class CityAIModels:
    archetypes: dict[str, Any]
    districts: dict[str, Any]
    thoughts: list[dict[str, Any]]
    fallback_thought: dict[str, Any]
    cadence: dict[str, Any]
    mood_axes: dict[str, Any]


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_city_ai_models(project_root: Path) -> CityAIModels:
    """Load the authored HoloUtopia AI model catalog from project root."""
    ai_dir = project_root / "data" / "database" / "utopia" / "ai"
    archetype_catalog = _read_json(ai_dir / "citizen_archetype_catalog.json")
    district_model = _read_json(ai_dir / "district_pressure_model.json")
    thought_catalog = _read_json(ai_dir / "thought_template_catalog.json")
    return CityAIModels(
        archetypes=dict(archetype_catalog.get("archetype_models", {})),
        districts=dict(district_model.get("districts", {})),
        thoughts=list(thought_catalog.get("templates", [])),
        fallback_thought=dict(thought_catalog.get("fallback", {"text": "I am watching the city move.", "mood_delta": {}})),
        cadence=dict(archetype_catalog.get("cadence", {})),
        mood_axes=dict(archetype_catalog.get("mood_axes", {})),
    )


def stable_seed(*parts: Any) -> int:
    """Return a process-stable integer seed for deterministic citizen choices."""
    joined = "|".join(str(part) for part in parts)
    digest = hashlib.sha256(joined.encode("utf-8", errors="replace")).hexdigest()
    return int(digest[:16], 16)


def _safe_display(value: Any, fallback: str = "Unknown") -> str:
    """Convert internal IDs into conservative player-facing labels.

    This is intentionally simple and local. Proper names supplied by authored data
    are preserved; raw snake_case IDs are converted to Title Case words.
    """
    text = str(value or "").strip()
    if not text:
        return fallback
    raw_lower = text.lower()
    looks_like_id = text.startswith(_RAW_ID_PREFIXES) or "_" in text or re.search(r"\d{2,}$", text) is not None
    if looks_like_id:
        text = text.replace("_", " ")
        text = re.sub(r"\b\d{2,}\b", "", text)
        text = " ".join(part.capitalize() for part in text.split())
        for prefix in _RAW_ID_PREFIXES:
            prefix_words = prefix.rstrip("_").replace("_", " ").title()
            if text.startswith(prefix_words + " "):
                text = text[len(prefix_words) + 1 :]
                break
        return text or fallback
    if raw_lower == text:
        return " ".join(part.capitalize() for part in text.split())
    return text


def clamp_mood_value(name: str, value: Any, models: CityAIModels) -> int:
    axis = models.mood_axes.get(name, {})
    lo = int(axis.get("min", 0))
    hi = int(axis.get("max", 100))
    default = int(axis.get("default", 50))
    try:
        number = int(round(float(value)))
    except (TypeError, ValueError):
        number = default
    return max(lo, min(hi, number))


def default_mood(models: CityAIModels) -> dict[str, int]:
    return {name: clamp_mood_value(name, axis.get("default", 50), models) for name, axis in models.mood_axes.items()}


def apply_mood_delta(mood: dict[str, Any], delta: dict[str, Any], models: CityAIModels) -> dict[str, int]:
    out = default_mood(models)
    for name in out:
        out[name] = clamp_mood_value(name, mood.get(name, out[name]), models)
    for name, amount in (delta or {}).items():
        if name in out:
            out[name] = clamp_mood_value(name, out[name] + float(amount), models)
    return out


def _citizen_archetype_id(citizen: dict[str, Any]) -> str:
    return str(citizen.get("archetype") or citizen.get("role") or "").strip().lower()


def _citizen_id(citizen: dict[str, Any]) -> str:
    return str(citizen.get("id") or citizen.get("citizen_id") or citizen.get("name") or "citizen").strip()


def choose_thought(
    citizen: dict[str, Any],
    district_id: str,
    models: CityAIModels,
    *,
    now: float | None = None,
    friend_name: str = "a friend",
) -> dict[str, Any]:
    """Choose one deterministic thought from archetype and district tags.

    Call when a citizen panel opens or when the thought cadence expires. Do not
    call every frame for visible text changes.
    """
    now = time.time() if now is None else float(now)
    cadence = max(1, int(models.cadence.get("thought_update_seconds", 18)))
    slot = int(now // cadence)

    archetype_id = _citizen_archetype_id(citizen)
    archetype = models.archetypes.get(archetype_id, {})
    tags = set(archetype.get("thought_tags", []))
    tags.update(str(item) for item in citizen.get("thought_tags", []) or [])

    district = models.districts.get(district_id, {})
    tags.update(district.get("pressure_tags", []))

    candidates = []
    for item in models.thoughts:
        item_tags = set(item.get("tags", []))
        if tags and item_tags.intersection(tags):
            candidates.append(item)

    if not candidates:
        selected = dict(models.fallback_thought)
    else:
        seed = stable_seed(_citizen_id(citizen), archetype_id, district_id, slot)
        rng = random.Random(seed)
        selected = dict(rng.choice(candidates))

    text = str(selected.get("text") or models.fallback_thought["text"])
    text = text.format(friend_name=_safe_display(friend_name, "a friend"))
    selected["text"] = text
    selected["cadence_slot"] = slot
    return selected


def build_citizen_ai_snapshot(
    citizen: dict[str, Any],
    district_id: str,
    models: CityAIModels,
    *,
    debug: bool = False,
    now: float | None = None,
    thought: dict[str, Any] | None = None,
    mood_override: dict[str, Any] | None = None,
    recent_memories: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    archetype_id = _citizen_archetype_id(citizen)
    archetype = models.archetypes.get(archetype_id, {})
    district = models.districts.get(district_id, {})

    if thought is None:
        thought = choose_thought(citizen, district_id, models, now=now, friend_name=str(citizen.get("friend_name") or "a friend"))

    base_mood = default_mood(models)
    for name in base_mood:
        base_mood[name] = clamp_mood_value(name, citizen.get(name, base_mood[name]), models)
    if mood_override:
        for name in base_mood:
            base_mood[name] = clamp_mood_value(name, mood_override.get(name, base_mood[name]), models)

    preferred_tasks = list(archetype.get("preferred_tasks") or ["observe_city"])
    intent_hint = _safe_display(preferred_tasks[0], "Observe City")

    snapshot = {
        "name": str(citizen.get("display_name") or citizen.get("name") or _safe_display(_citizen_id(citizen), "Citizen")),
        "role": str(archetype.get("label") or _safe_display(citizen.get("role"), "Citizen")),
        "district": str(district.get("display") or _safe_display(district_id, "Unknown District")),
        "mood": base_mood,
        "current_thought": thought["text"],
        "thought_id": thought.get("id", "fallback"),
        "intent_hint": intent_hint,
        "district_status": str(district.get("player_facing_status") or ""),
        "strengths": [_safe_display(item) for item in list(archetype.get("strengths", []))[:3]],
        "weaknesses": [_safe_display(item) for item in list(archetype.get("weaknesses", []))[:2]],
        "recent_memories": list(recent_memories or [])[:5],
    }
    if debug:
        snapshot["debug"] = {
            "citizen_id": citizen.get("id") or citizen.get("citizen_id"),
            "archetype_id": archetype_id,
            "district_id": district_id,
            "thought_id": thought.get("id"),
            "cadence_slot": thought.get("cadence_slot"),
        }
    return snapshot
