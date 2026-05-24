"""Runtime bridge for HoloUtopia citizen AI thoughts and memories.

Pass 30 goal:
Turn the Pass 29 model catalogs into a small live simulation layer that can be
called by the citizen inspector or schedule/task code without rewriting the city.

Design rules:
- Deterministic local logic only; no online AI calls.
- No per-frame disk writes.
- Safe to use even if the rest of the game has older citizen dict shapes.
- Normal UI remains player-facing; debug IDs stay behind debug=True.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

try:  # support both package-style and flat script imports
    from .city_ai_models import (
        CityAIModels,
        apply_mood_delta,
        build_citizen_ai_snapshot,
        choose_thought,
        default_mood,
        load_city_ai_models,
        stable_seed,
    )
except ImportError:  # pragma: no cover - drop-in fallback for direct execution
    from city_ai_models import (  # type: ignore
        CityAIModels,
        apply_mood_delta,
        build_citizen_ai_snapshot,
        choose_thought,
        default_mood,
        load_city_ai_models,
        stable_seed,
    )

MemoryWriter = Callable[[dict[str, Any]], None]


@dataclass
class CitizenAIState:
    citizen_id: str
    mood: dict[str, int]
    current_thought: dict[str, Any] = field(default_factory=dict)
    last_thought_time: float = 0.0
    memories: list[dict[str, Any]] = field(default_factory=list)
    dirty: bool = False


class CityAIRuntime:
    """Small stateful manager for citizen thoughts, memories, and mood."""

    def __init__(
        self,
        project_root: Path,
        *,
        models: CityAIModels | None = None,
        state_path: Path | None = None,
        auto_load_state: bool = True,
    ) -> None:
        self.project_root = Path(project_root)
        self.models = models or load_city_ai_models(self.project_root)
        self.state_path = state_path or self.project_root / "data" / "database" / "utopia" / "runtime" / "citizen_ai_state.json"
        self.states: dict[str, CitizenAIState] = {}
        self.last_save_time = 0.0
        self.save_interval_seconds = 15.0
        self.memory_writer: MemoryWriter | None = None
        if auto_load_state:
            self.load_state()

    @property
    def thought_update_seconds(self) -> int:
        return max(1, int(self.models.cadence.get("thought_update_seconds", 18)))

    @property
    def max_memories_per_citizen(self) -> int:
        return max(1, int(self.models.cadence.get("max_memories_per_citizen", 12)))

    def _citizen_id(self, citizen: dict[str, Any]) -> str:
        return str(citizen.get("id") or citizen.get("citizen_id") or citizen.get("name") or "citizen").strip()

    def get_or_create_state(self, citizen: dict[str, Any]) -> CitizenAIState:
        citizen_id = self._citizen_id(citizen)
        if citizen_id not in self.states:
            self.states[citizen_id] = CitizenAIState(citizen_id=citizen_id, mood=default_mood(self.models))
        return self.states[citizen_id]

    def refresh_thought_if_needed(
        self,
        citizen: dict[str, Any],
        district_id: str,
        *,
        now: float | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        now = time.time() if now is None else float(now)
        state = self.get_or_create_state(citizen)
        expired = (now - state.last_thought_time) >= self.thought_update_seconds
        if force or not state.current_thought or expired:
            thought = choose_thought(
                citizen,
                district_id,
                self.models,
                now=now,
                friend_name=str(citizen.get("friend_name") or "a friend"),
            )
            state.current_thought = thought
            state.last_thought_time = now
            state.mood = apply_mood_delta(state.mood, thought.get("mood_delta", {}), self.models)
            state.dirty = True
            self._maybe_add_thought_memory(citizen, district_id, thought, now=now)
        return state.current_thought

    def _maybe_add_thought_memory(
        self,
        citizen: dict[str, Any],
        district_id: str,
        thought: dict[str, Any],
        *,
        now: float,
    ) -> None:
        importance = float(thought.get("importance", 0.25))
        if importance < 0.2:
            return
        summary = str(thought.get("memory_summary") or thought.get("text") or "A thought passed through their mind.")
        self.remember_event(
            citizen,
            kind="system",
            summary=summary,
            location_id=district_id,
            importance=importance,
            mood_delta=thought.get("mood_delta", {}),
            debug_source_id=str(thought.get("id") or "thought"),
            now=now,
        )

    def remember_event(
        self,
        citizen: dict[str, Any] | str,
        *,
        kind: str,
        summary: str,
        location_id: str = "",
        related_citizen_ids: list[str] | None = None,
        mood_delta: dict[str, Any] | None = None,
        importance: float = 0.5,
        debug_source_id: str = "",
        now: float | None = None,
    ) -> dict[str, Any]:
        now = time.time() if now is None else float(now)
        if isinstance(citizen, str):
            citizen_id = citizen
            fake_citizen = {"id": citizen_id}
        else:
            citizen_id = self._citizen_id(citizen)
            fake_citizen = citizen
        state = self.get_or_create_state(fake_citizen)
        event_id = f"mem_{stable_seed(citizen_id, kind, summary, location_id, int(now * 10)):016x}"[-24:]
        event = {
            "version": "0.2.0-pass30",
            "citizen_id": citizen_id,
            "event_id": event_id,
            "timestamp": now,
            "kind": kind,
            "summary": str(summary).strip()[:180] or "Something changed in the city.",
            "location_id": str(location_id or ""),
            "related_citizen_ids": list(related_citizen_ids or []),
            "mood_delta": dict(mood_delta or {}),
            "importance": max(0.0, min(1.0, float(importance))),
        }
        if debug_source_id:
            event["debug_source_id"] = debug_source_id
        state.memories.insert(0, event)
        del state.memories[self.max_memories_per_citizen :]
        state.mood = apply_mood_delta(state.mood, event["mood_delta"], self.models)
        state.dirty = True
        if self.memory_writer is not None:
            self.memory_writer(event)
        return event

    def get_recent_memories(self, citizen: dict[str, Any] | str, limit: int = 5) -> list[dict[str, Any]]:
        if isinstance(citizen, str):
            state = self.states.get(citizen)
        else:
            state = self.get_or_create_state(citizen)
        if state is None:
            return []
        return list(state.memories[: max(0, int(limit))])

    def build_snapshot(
        self,
        citizen: dict[str, Any],
        district_id: str,
        *,
        debug: bool = False,
        now: float | None = None,
        force_thought: bool = False,
    ) -> dict[str, Any]:
        now = time.time() if now is None else float(now)
        state = self.get_or_create_state(citizen)
        thought = self.refresh_thought_if_needed(citizen, district_id, now=now, force=force_thought)
        return build_citizen_ai_snapshot(
            citizen,
            district_id,
            self.models,
            debug=debug,
            now=now,
            thought=thought,
            mood_override=state.mood,
            recent_memories=state.memories,
        )

    def load_state(self) -> None:
        if not self.state_path.exists():
            return
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        except Exception:
            return
        for item in payload.get("citizens", []):
            citizen_id = str(item.get("citizen_id") or "").strip()
            if not citizen_id:
                continue
            self.states[citizen_id] = CitizenAIState(
                citizen_id=citizen_id,
                mood=apply_mood_delta(default_mood(self.models), item.get("mood", {}), self.models),
                current_thought=dict(item.get("current_thought") or {}),
                last_thought_time=float(item.get("last_thought_time") or 0.0),
                memories=list(item.get("memories") or [])[: self.max_memories_per_citizen],
                dirty=False,
            )

    def to_json_payload(self) -> dict[str, Any]:
        return {
            "version": "0.2.0-pass30",
            "citizens": [
                {
                    "citizen_id": state.citizen_id,
                    "mood": state.mood,
                    "current_thought": state.current_thought,
                    "last_thought_time": state.last_thought_time,
                    "memories": state.memories[: self.max_memories_per_citizen],
                }
                for state in sorted(self.states.values(), key=lambda item: item.citizen_id)
            ],
        }

    def save_state(self, *, force: bool = False, now: float | None = None) -> bool:
        now = time.time() if now is None else float(now)
        dirty = any(state.dirty for state in self.states.values())
        if not force and not dirty:
            return False
        if not force and (now - self.last_save_time) < self.save_interval_seconds:
            return False
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(self.to_json_payload(), indent=2, sort_keys=True), encoding="utf-8")
        for state in self.states.values():
            state.dirty = False
        self.last_save_time = now
        return True


def build_city_ai_runtime(project_root: Path, *, state_path: Path | None = None) -> CityAIRuntime:
    return CityAIRuntime(Path(project_root), state_path=state_path)
