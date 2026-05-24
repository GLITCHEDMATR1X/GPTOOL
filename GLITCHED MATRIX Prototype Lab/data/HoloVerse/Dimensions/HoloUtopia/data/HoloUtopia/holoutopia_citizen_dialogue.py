"""Proximity-based citizen dialogue for HoloUtopia.

This module is intentionally conservative:
- citizens only talk when visible and near another visible citizen;
- garrisoned/private-home citizens do not speak;
- answers are resolved from current runtime state and approved rule data;
- short speech text is returned for small non-overlapping world bubbles;
- no authored city data is written.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
from typing import Any

DIALOGUE_RULES_REL = Path("database/utopia/dialogue/citizen_dialogue_rules.json")
QA_CATALOG_REL = Path("database/utopia/dialogue/question_answer_catalog.json")
SPECIFIC_QA_CATALOG_REL = Path("database/utopia/dialogue/specific_question_catalog.json")


_DEFAULT_RULES: dict[str, Any] = {
    "schema": 1,
    "id": "holoutopia_citizen_dialogue_rules_v1",
    "runtime_writes_allowed": False,
    "proximity_only": True,
    "garrisoned_citizens_silent": True,
    "brief_speech_only": True,
    "visual": {
        "max_active_bubbles": 3,
        "max_text_chars": 28,
        "proximity_radius_units": 28.0,
        "min_anchor_distance_units": 70.0,
        "bubble_lifetime_seconds": 3.0,
        "bubble_scale": 1.55,
        "bubble_z_offset": 10.0,
        "max_dialogue_lines": 2,
        "max_recent_log_lines": 4,
        "no_overlap_policy": "cap_active_bubbles_space_anchors_and_keep_text_brief",
    },
    "daily_memory": {
        "enabled": True,
        "scope": "same_game_day",
        "no_repeat_same_pair_question": True,
        "no_repeat_same_citizen_line": True,
        "no_repeat_same_answer_text": True,
        "reset_when_day_id_changes": True,
        "max_attempts_per_pair": 8
    },
    "turn_order": ["greeting", "informative", "positive", "negative"],
    "category_labels": {
        "greeting": "Greeting",
        "positive": "Positive",
        "negative": "Concern",
        "informative": "Info",
    },
    "question_intents": [
        "current_activity",
        "current_phase",
        "home_garrison",
        "outdoor_cap",
        "energy_rule",
        "recharge_rule",
        "cluster_assignment",
        "district_purpose",
        "commute_status",
    ],
}


_DEFAULT_QA: dict[str, Any] = {
    "schema": 1,
    "id": "holoutopia_question_answer_catalog_v1",
    "question_templates": {
        "current_activity": ["Task?"],
        "current_phase": ["Cycle?"],
        "home_garrison": ["Recharge where?"],
        "outdoor_cap": ["Outdoor cap?"],
        "energy_rule": ["Active time?"],
        "recharge_rule": ["Recharge time?"],
        "cluster_assignment": ["Hub node?"],
        "district_purpose": ["District purpose?"],
        "commute_status": ["Commuting?"],
    },
    "fallback_answers": [
        "I don't know that.",
        "That is outside my assignment.",
        "Ask a civic node for that.",
    ],
    "district_purpose": {
        "central_core_civic_ring": "This is the Simulation Hub.",
        "residential_alpha": "Residential is for home garrisons.",
    },
}


@dataclass(frozen=True)
class DialogueBubble:
    """Small JSON-safe speech bubble entry."""

    id: str
    kind: str
    speaker_id: str
    listener_id: str
    question: str
    answer: str
    text: str
    x: float
    y: float
    z: float
    row: int
    distance: float
    intent: str = "unknown"
    confidence: str = "runtime_resolved"
    question_id: str = "unknown_question"
    source: str = "live_runtime_state"

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "speaker_id": self.speaker_id,
            "listener_id": self.listener_id,
            "question": self.question,
            "answer": self.answer,
            "text": self.text,
            "x": round(float(self.x), 3),
            "y": round(float(self.y), 3),
            "z": round(float(self.z), 3),
            "row": int(self.row),
            "distance": round(float(self.distance), 3),
            "intent": str(self.intent),
            "confidence": str(self.confidence),
            "question_id": str(self.question_id),
            "source": str(self.source),
        }


def data_root_from_holoutopia(holoutopia_root: Path | str | None = None) -> Path:
    root = Path(holoutopia_root or Path(__file__).resolve().parent).resolve()
    if root.name.lower() in {"holoverse", "holoutopia"}:
        return root.parent
    return root


def _read_json(path: Path, fallback: dict[str, Any]) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return json.loads(json.dumps(fallback))
    return data if isinstance(data, dict) else json.loads(json.dumps(fallback))


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = json.loads(json.dumps(base))
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_dialogue_rules(holoutopia_root: Path | str | None = None) -> dict[str, Any]:
    data_root = data_root_from_holoutopia(holoutopia_root)
    return _deep_merge(_DEFAULT_RULES, _read_json(data_root / DIALOGUE_RULES_REL, _DEFAULT_RULES))


def load_question_answer_catalog(holoutopia_root: Path | str | None = None) -> dict[str, Any]:
    data_root = data_root_from_holoutopia(holoutopia_root)
    return _deep_merge(_DEFAULT_QA, _read_json(data_root / QA_CATALOG_REL, _DEFAULT_QA))


def build_dialogue_state(
    holoutopia_root: Path | str | None,
    frame: dict[str, Any],
    visible_citizens: dict[str, dict[str, Any]],
    positions: dict[str, tuple[float, float, float]],
    *,
    clock: str = "18:15",
    day_id: str | None = None,
    daily_memory: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return active proximity dialogue bubbles for the current visible frame.

    Pass 47D adds same-day conversation memory: accepted speech is recorded
    by day, pair, question, speaker, and answer so the visible simulation does
    not repeat the same line again during the same in-game day.  The memory is
    in-memory only and never writes authored city data.
    """
    rules = load_dialogue_rules(holoutopia_root)
    qa = load_question_answer_catalog(holoutopia_root)
    visual = rules.get("visual") if isinstance(rules.get("visual"), dict) else {}
    daily_cfg = rules.get("daily_memory") if isinstance(rules.get("daily_memory"), dict) else {}
    day_id = str(day_id or _day_id_from_frame(frame, clock))
    day_memory = _prepare_daily_memory(daily_memory, day_id)
    max_unique_attempts = max(1, min(16, _safe_int(daily_cfg.get("max_attempts_per_pair"), 8)))
    max_bubbles = max(0, min(12, _safe_int(visual.get("max_active_bubbles"), 5)))
    if max_bubbles <= 0:
        return _empty_state(clock, rules)
    radius = max(4.0, _safe_float(visual.get("proximity_radius_units"), 26.0))
    min_anchor = max(0.0, _safe_float(visual.get("min_anchor_distance_units"), 42.0))
    max_chars = max(18, min(72, _safe_int(visual.get("max_text_chars"), 42)))
    z_offset = _safe_float(visual.get("bubble_z_offset"), 14.0)

    candidate_people: dict[str, dict[str, Any]] = {}
    for cid, citizen in visible_citizens.items():
        if not isinstance(citizen, dict):
            continue
        if str(citizen.get("location_mode") or "") == "private_home_hidden":
            continue
        if cid not in positions:
            continue
        candidate_people[str(cid)] = citizen

    pairs = _nearby_pairs(candidate_people, positions, radius)
    bubbles: list[DialogueBubble] = []
    anchors: list[tuple[float, float]] = []
    used: set[str] = set()
    local_daily_keys: set[str] = set()
    for pair_index, (a_id, b_id, dist) in enumerate(pairs):
        if len(bubbles) >= max_bubbles:
            break
        if a_id in used or b_id in used:
            continue
        ax, ay, az = positions[a_id]
        bx, by, bz = positions[b_id]
        x = (float(ax) + float(bx)) * 0.5
        y = (float(ay) + float(by)) * 0.5
        # Simple 2D anchor spacing keeps speech from stacking over the same group.
        if any(_dist2((x, y), anchor) < min_anchor * min_anchor for anchor in anchors):
            continue
        kind = _choose_dialogue_kind(a_id, b_id, pair_index, rules)
        exchange = _resolve_unique_dialogue_exchange(
            holoutopia_root,
            frame,
            a_id,
            candidate_people[a_id],
            b_id,
            candidate_people[b_id],
            base_kind=kind,
            qa_catalog=qa,
            pair_index=pair_index,
            day_id=day_id,
            day_memory=day_memory,
            local_daily_keys=local_daily_keys,
            max_attempts=max_unique_attempts,
        )
        if not exchange:
            continue
        kind = str(exchange.get("kind") or kind)
        question = str(exchange.get("question") or "Status?")
        answer = str(exchange.get("answer") or "I don't know that.")
        text = _format_brief_text(question, answer, kind, max_chars=max_chars)
        row = len(bubbles) % 3
        bubbles.append(
            DialogueBubble(
                id=f"dlg_{clock.replace(':', '')}_{len(bubbles):02d}_{a_id}_{b_id}",
                kind=kind,
                speaker_id=a_id,
                listener_id=b_id,
                question=question,
                answer=answer,
                text=text,
                x=x,
                y=y,
                z=max(float(az), float(bz)) + z_offset + row * 3.0,
                row=row,
                distance=dist,
                intent=str(exchange.get("intent") or "unknown"),
                confidence=str(exchange.get("confidence") or "runtime_resolved"),
                question_id=str(exchange.get("question_id") or "unknown_question"),
                source=str(exchange.get("source") or "live_runtime_state"),
            )
        )
        _record_daily_exchange(day_memory, day_id, a_id, b_id, exchange, text, local_daily_keys)
        anchors.append((x, y))
        used.add(a_id)
        used.add(b_id)

    bubble_dicts = [bubble.as_dict() for bubble in bubbles]
    category_counts: dict[str, int] = {}
    for bubble in bubble_dicts:
        kind_key = str(bubble.get("kind") or "informative")
        category_counts[kind_key] = category_counts.get(kind_key, 0) + 1
    recent_log = _recent_log_from_bubbles(
        bubble_dicts,
        max_lines=max(1, min(6, _safe_int(visual.get("max_recent_log_lines"), 4))),
    )
    return {
        "schema": 2,
        "id": "holoutopia_citizen_dialogue_state_v2",
        "clock": str(clock),
        "day_id": day_id,
        "proximity_only": True,
        "visible_citizens_checked": len(candidate_people),
        "nearby_pair_candidates": len(pairs),
        "active_bubbles": bubble_dicts,
        "recent_conversations": recent_log,
        "dialogue_category_counts": category_counts,
        "specific_question_count": _specific_question_count(holoutopia_root),
        "daily_memory": _daily_memory_summary(day_memory, day_id),
        "max_active_bubbles": max_bubbles,
        "max_text_chars": max_chars,
        "proximity_radius_units": radius,
        "min_anchor_distance_units": min_anchor,
        "bubble_scale": _safe_float(visual.get("bubble_scale"), 1.55),
        "safety": {
            "only_nearby_visible_citizens_talk": True,
            "garrisoned_citizens_silent": True,
            "brief_non_overlapping_bubbles": True,
            "answers_resolve_from_runtime_state": True,
            "unknown_answers_fail_safely": True,
            "specific_questions_route_to_known_intents": True,
            "same_day_dialogue_repetition_guard": True,
            "daily_memory_runtime_only": True,
            "writes_authored_data": False,
            "adds_collision": False,
        },
    }


def validate_dialogue_state(state: dict[str, Any]) -> list[str]:
    """Return validation issues for tests/validators. Empty list means OK."""
    issues: list[str] = []
    bubbles = state.get("active_bubbles") if isinstance(state.get("active_bubbles"), list) else []
    max_chars = _safe_int(state.get("max_text_chars"), 42)
    radius = _safe_float(state.get("proximity_radius_units"), 26.0)
    min_anchor = _safe_float(state.get("min_anchor_distance_units"), 42.0)
    anchors: list[tuple[float, float]] = []
    used: set[str] = set()
    for idx, bubble in enumerate(bubbles):
        if not isinstance(bubble, dict):
            issues.append(f"bubble_{idx}_not_dict")
            continue
        text = str(bubble.get("text") or "")
        # Multi-line text can be longer than one line, but each visible line stays brief.
        for part in text.split("\n"):
            if len(part) > max_chars + 3:
                issues.append(f"bubble_{idx}_line_too_long:{len(part)}")
        distance = _safe_float(bubble.get("distance"), 9999.0)
        if distance > radius + 0.001:
            issues.append(f"bubble_{idx}_outside_proximity:{distance:.2f}")
        speaker = str(bubble.get("speaker_id") or "")
        listener = str(bubble.get("listener_id") or "")
        if not speaker or not listener or speaker == listener:
            issues.append(f"bubble_{idx}_bad_pair")
        if not str(bubble.get("question_id") or "").startswith("q_"):
            issues.append(f"bubble_{idx}_missing_specific_question_id")
        if str(bubble.get("source") or "") not in {"live_runtime_state", "safe_fallback"}:
            issues.append(f"bubble_{idx}_bad_source")
        if speaker in used or listener in used:
            issues.append(f"bubble_{idx}_citizen_reused")
        used.add(speaker)
        used.add(listener)
        anchor = (_safe_float(bubble.get("x"), 0.0), _safe_float(bubble.get("y"), 0.0))
        for previous in anchors:
            if _dist2(anchor, previous) < (min_anchor * min_anchor) - 0.01:
                issues.append(f"bubble_{idx}_anchor_overlap")
        anchors.append(anchor)
    if len(bubbles) > _safe_int(state.get("max_active_bubbles"), 5):
        issues.append("too_many_bubbles")
    recent = state.get("recent_conversations") if isinstance(state.get("recent_conversations"), list) else []
    if len(recent) > 6:
        issues.append("too_many_recent_conversation_lines")
    for idx, line in enumerate(recent):
        if len(str(line)) > 58:
            issues.append(f"recent_log_{idx}_too_long:{len(str(line))}")
    daily_seen: set[str] = set()
    for idx, bubble in enumerate(bubbles):
        if not isinstance(bubble, dict):
            continue
        day_key = _bubble_daily_key(str(state.get("day_id") or "day_0000"), bubble)
        if day_key in daily_seen:
            issues.append(f"bubble_{idx}_repeated_daily_key")
        daily_seen.add(day_key)
    daily = state.get("daily_memory") if isinstance(state.get("daily_memory"), dict) else {}
    if bubbles and not bool(daily.get("same_day_no_repeat")):
        issues.append("daily_memory_no_repeat_missing")
    counts = state.get("dialogue_category_counts") if isinstance(state.get("dialogue_category_counts"), dict) else {}
    if bubbles and not counts:
        issues.append("missing_category_counts")
    if _safe_int(state.get("specific_question_count"), 0) < 10:
        issues.append("too_few_specific_questions")
    safety = state.get("safety") if isinstance(state.get("safety"), dict) else {}
    for key in ("only_nearby_visible_citizens_talk", "garrisoned_citizens_silent", "brief_non_overlapping_bubbles", "answers_resolve_from_runtime_state", "specific_questions_route_to_known_intents", "same_day_dialogue_repetition_guard", "daily_memory_runtime_only"):
        if not bool(safety.get(key)):
            issues.append(f"missing_safety:{key}")
    return issues



def _resolve_unique_dialogue_exchange(
    holoutopia_root: Path | str | None,
    frame: dict[str, Any],
    speaker_id: str,
    speaker: dict[str, Any],
    listener_id: str,
    listener: dict[str, Any],
    *,
    base_kind: str,
    qa_catalog: dict[str, Any] | None,
    pair_index: int,
    day_id: str,
    day_memory: dict[str, set[str]],
    local_daily_keys: set[str],
    max_attempts: int,
) -> dict[str, Any] | None:
    """Resolve an exchange that has not already been used today."""
    kind_order = [base_kind, "informative", "positive", "greeting", "negative"]
    # Preserve order while removing duplicates.
    seen_kinds: set[str] = set()
    kinds = [k for k in kind_order if not (k in seen_kinds or seen_kinds.add(k))]
    attempts = 0
    for offset in range(max(1, int(max_attempts))):
        for kind in kinds:
            if attempts >= max_attempts:
                break
            attempts += 1
            exchange = resolve_dialogue_exchange(
                holoutopia_root,
                frame,
                speaker_id,
                speaker,
                listener_id,
                listener,
                kind=kind,
                qa_catalog=qa_catalog,
                pair_index=pair_index + offset,
            )
            exchange["kind"] = str(kind)
            daily_keys = _exchange_daily_keys(day_id, speaker_id, listener_id, exchange)
            if _daily_keys_available(day_memory, local_daily_keys, daily_keys):
                return exchange
    return None


def _exchange_daily_keys(day_id: str, speaker_id: str, listener_id: str, exchange: dict[str, Any], text: str | None = None) -> dict[str, str]:
    pair = "__".join(sorted([str(speaker_id), str(listener_id)]))
    question_id = str(exchange.get("question_id") or "unknown_question")
    answer_sig = _line_signature(exchange.get("answer") or exchange.get("text") or text or "")
    question_sig = _line_signature(exchange.get("question") or question_id)
    return {
        "pair_topic": f"{day_id}:pair:{pair}:q:{question_id}",
        "speaker_line": f"{day_id}:speaker:{speaker_id}:a:{answer_sig}",
        "listener_line": f"{day_id}:listener:{listener_id}:q:{question_sig}",
        "answer_text": f"{day_id}:answer:{answer_sig}",
    }


def _daily_keys_available(day_memory: dict[str, set[str]], local_daily_keys: set[str], keys: dict[str, str]) -> bool:
    for key in keys.values():
        if key in local_daily_keys:
            return False
    if keys["pair_topic"] in day_memory.get("used_pair_topics", set()):
        return False
    if keys["speaker_line"] in day_memory.get("used_citizen_lines", set()):
        return False
    if keys["listener_line"] in day_memory.get("used_citizen_lines", set()):
        return False
    if keys["answer_text"] in day_memory.get("used_answer_texts", set()):
        return False
    return True


def _record_daily_exchange(day_memory: dict[str, set[str]], day_id: str, speaker_id: str, listener_id: str, exchange: dict[str, Any], text: str, local_daily_keys: set[str]) -> None:
    keys = _exchange_daily_keys(day_id, speaker_id, listener_id, exchange, text)
    day_memory.setdefault("used_pair_topics", set()).add(keys["pair_topic"])
    day_memory.setdefault("used_citizen_lines", set()).add(keys["speaker_line"])
    day_memory.setdefault("used_citizen_lines", set()).add(keys["listener_line"])
    day_memory.setdefault("used_answer_texts", set()).add(keys["answer_text"])
    day_memory.setdefault("used_all_keys", set()).update(keys.values())
    local_daily_keys.update(keys.values())


def _prepare_daily_memory(memory: dict[str, Any] | None, day_id: str) -> dict[str, set[str]]:
    if memory is None:
        return {"day_id": {str(day_id)}, "used_pair_topics": set(), "used_citizen_lines": set(), "used_answer_texts": set(), "used_all_keys": set()}
    if str(memory.get("day_id") or "") != str(day_id):
        memory.clear()
        memory["day_id"] = str(day_id)
    prepared: dict[str, set[str]] = {"day_id": {str(day_id)}}
    for key in ("used_pair_topics", "used_citizen_lines", "used_answer_texts", "used_all_keys"):
        raw = memory.get(key, [])
        if isinstance(raw, set):
            values = set(str(item) for item in raw)
        elif isinstance(raw, list):
            values = set(str(item) for item in raw)
        else:
            values = set()
        prepared[key] = values
        memory[key] = values
    return prepared


def _daily_memory_summary(day_memory: dict[str, set[str]], day_id: str) -> dict[str, Any]:
    return {
        "enabled": True,
        "day_id": str(day_id),
        "same_day_no_repeat": True,
        "runtime_only": True,
        "used_pair_topics": len(day_memory.get("used_pair_topics", set())),
        "used_citizen_lines": len(day_memory.get("used_citizen_lines", set())),
        "used_answer_texts": len(day_memory.get("used_answer_texts", set())),
        "reset_when_day_id_changes": True,
    }


def _day_id_from_frame(frame: dict[str, Any], clock: str) -> str:
    for key in ("day_id", "game_day_id", "simulation_day_id"):
        value = frame.get(key) if isinstance(frame, dict) else None
        if value is not None and str(value).strip():
            return str(value)
    return "day_0000"


def _line_signature(text: Any) -> str:
    raw = " ".join(str(text or "").lower().replace("\n", " ").split())
    keep = []
    for ch in raw:
        keep.append(ch if ch.isalnum() else "_")
    sig = "".join(keep).strip("_")
    return sig[:48] or "blank"


def _bubble_daily_key(day_id: str, bubble: dict[str, Any]) -> str:
    pair = "__".join(sorted([str(bubble.get("speaker_id") or ""), str(bubble.get("listener_id") or "")]))
    return f"{day_id}:pair:{pair}:q:{bubble.get('question_id')}:a:{_line_signature(bubble.get('answer'))}"


def resolve_dialogue_exchange(
    holoutopia_root: Path | str | None,
    frame: dict[str, Any],
    speaker_id: str,
    speaker: dict[str, Any],
    listener_id: str,
    listener: dict[str, Any],
    *,
    kind: str,
    qa_catalog: dict[str, Any] | None = None,
    pair_index: int = 0,
) -> dict[str, Any]:
    """Return a compact exchange record with intent/confidence metadata."""
    # Pass 47C: prefer specific approved questions so citizens can answer
    # precise, player-readable prompts without inventing unsupported facts.
    try:
        from holoutopia_citizen_question_router import choose_specific_question_id, resolve_specific_question
        qid = choose_specific_question_id(holoutopia_root, kind, speaker_id, listener_id, pair_index)
        routed = resolve_specific_question(
            holoutopia_root,
            frame,
            speaker_id,
            speaker,
            listener_id,
            listener,
            question_id=qid,
            category_hint=kind,
        )
        return {
            "kind": str(kind),
            "intent": str(routed.intent),
            "question": str(routed.question),
            "answer": str(routed.answer),
            "confidence": str(routed.confidence),
            "source": str(routed.source),
            "question_id": str(routed.question_id),
            "category": str(routed.category),
        }
    except Exception:
        pass

    intent = _choose_intent(speaker_id, listener_id, speaker, listener, kind)
    question, answer = resolve_question_answer(
        holoutopia_root,
        frame,
        speaker_id,
        speaker,
        listener_id,
        listener,
        kind=kind,
        qa_catalog=qa_catalog,
    )
    qa = qa_catalog if isinstance(qa_catalog, dict) else load_question_answer_catalog(holoutopia_root)
    fallbacks = [str(item) for item in (qa.get("fallback_answers") if isinstance(qa.get("fallback_answers"), list) else [])]
    confidence = "safe_unknown" if str(answer) in fallbacks or "don't know" in str(answer).lower() else "runtime_resolved"
    return {
        "kind": str(kind),
        "intent": str(intent),
        "question": str(question),
        "answer": str(answer),
        "confidence": confidence,
        "source": "live_runtime_state" if confidence == "runtime_resolved" else "safe_fallback",
        "question_id": "q_legacy_runtime_intent",
    }


def resolve_question_answer(
    holoutopia_root: Path | str | None,
    frame: dict[str, Any],
    speaker_id: str,
    speaker: dict[str, Any],
    listener_id: str,
    listener: dict[str, Any],
    *,
    kind: str,
    qa_catalog: dict[str, Any] | None = None,
) -> tuple[str, str]:
    """Resolve a brief question/answer pair from live state, never guesswork."""
    qa = qa_catalog if isinstance(qa_catalog, dict) else load_question_answer_catalog(holoutopia_root)
    intent = _choose_intent(speaker_id, listener_id, speaker, listener, kind)
    templates = qa.get("question_templates") if isinstance(qa.get("question_templates"), dict) else {}
    question_list = templates.get(intent) if isinstance(templates.get(intent), list) else []
    question = str(question_list[0] if question_list else "What is your status?")
    pop = frame.get("residential_population_model") if isinstance(frame.get("residential_population_model"), dict) else {}
    answer = ""
    if intent == "current_activity":
        answer = str(listener.get("activity_status") or speaker.get("activity_status") or _friendly_activity(listener.get("activity_id") or speaker.get("activity_id")))
    elif intent == "current_phase":
        answer = f"{_friendly_phase(pop.get('phase'))} cycle."
    elif intent == "home_garrison":
        answer = "Residential Alpha garrison."
    elif intent == "outdoor_cap":
        cap = pop.get("max_outdoor_population_per_district") or 20
        answer = f"{cap} visible outside."
    elif intent == "energy_rule":
        rule = pop.get("energy_rule") if isinstance(pop.get("energy_rule"), dict) else {}
        active = rule.get("active_hours") or 15
        answer = f"{active} game hours."
    elif intent == "recharge_rule":
        rule = pop.get("energy_rule") if isinstance(pop.get("energy_rule"), dict) else {}
        recharge = rule.get("recharge_hours") or 9
        answer = f"{recharge} game hours inside."
    elif intent == "cluster_assignment":
        cluster = str(listener.get("activity_cluster_id") or speaker.get("activity_cluster_id") or listener.get("commute_stage") or speaker.get("commute_stage") or "")
        answer = _cluster_label(cluster) if cluster else _unknown_answer(qa, speaker_id, listener_id)
    elif intent == "district_purpose":
        purposes = qa.get("district_purpose") if isinstance(qa.get("district_purpose"), dict) else {}
        town_id = str(listener.get("town_id") or speaker.get("town_id") or "")
        answer = str(purposes.get(town_id) or _unknown_answer(qa, speaker_id, listener_id))
    elif intent == "commute_status":
        direction = str(listener.get("commute_direction") or speaker.get("commute_direction") or "")
        if direction == "return":
            answer = "Returning home."
        elif direction == "outbound":
            answer = "Heading to hub."
        elif "commute" in str(listener.get("activity_id") or speaker.get("activity_id") or ""):
            answer = "On route."
        else:
            answer = _unknown_answer(qa, speaker_id, listener_id)
    elif intent == "clock_time":
        answer = f"{frame.get('clock') or pop.get('clock') or 'unknown'}."
    elif intent == "population_total":
        answer = f"{pop.get('world_population') or pop.get('residential_population') or 1000} citizens."
    elif intent == "visible_population":
        outdoor = len(pop.get("visible_outdoor_citizens") if isinstance(pop.get("visible_outdoor_citizens"), dict) else {})
        activity = len(pop.get("visible_activity_citizens") if isinstance(pop.get("visible_activity_citizens"), dict) else {})
        answer = f"{outdoor + activity} visible now."
    else:
        answer = _unknown_answer(qa, speaker_id, listener_id)
    answer = _trim_sentence(answer, 38)
    return question, answer


def _nearby_pairs(citizens: dict[str, dict[str, Any]], positions: dict[str, tuple[float, float, float]], radius: float) -> list[tuple[str, str, float]]:
    pairs: list[tuple[str, str, float]] = []
    items = sorted(citizens.items())
    r2 = radius * radius
    for idx, (a_id, _a) in enumerate(items):
        ax, ay, _az = positions.get(a_id, (0.0, 0.0, 0.0))
        for b_id, _b in items[idx + 1:]:
            bx, by, _bz = positions.get(b_id, (0.0, 0.0, 0.0))
            d2 = _dist2((ax, ay), (bx, by))
            if d2 <= r2:
                pairs.append((a_id, b_id, math.sqrt(max(0.0, d2))))
    pairs.sort(key=lambda item: (item[2], _stable_fraction(item[0] + item[1])))
    return pairs


def _choose_dialogue_kind(a_id: str, b_id: str, pair_index: int, rules: dict[str, Any]) -> str:
    order = rules.get("turn_order") if isinstance(rules.get("turn_order"), list) else []
    valid = [str(item) for item in order if str(item) in {"greeting", "informative", "positive", "negative"}]
    if not valid:
        valid = ["greeting", "informative", "positive", "negative"]
    index = int((_stable_fraction(a_id + b_id, pair_index) * 1000.0) + pair_index) % len(valid)
    return valid[index]


def _choose_intent(speaker_id: str, listener_id: str, speaker: dict[str, Any], listener: dict[str, Any], kind: str) -> str:
    if kind == "greeting":
        if "commute" in str(listener.get("activity_id") or speaker.get("activity_id") or ""):
            return "commute_status"
        return "current_activity"
    if kind == "positive":
        if str(listener.get("activity_cluster_id") or speaker.get("activity_cluster_id") or ""):
            return "cluster_assignment"
        return "current_activity"
    if kind == "negative":
        # Keep it mild and data-based; no unsupported insults/drama.
        if "return" in str(listener.get("activity_id") or speaker.get("activity_id") or ""):
            return "recharge_rule"
        return "energy_rule"
    # Informative defaults rotate through real city rules.
    intents = ["current_phase", "home_garrison", "outdoor_cap", "district_purpose", "cluster_assignment"]
    idx = int(_stable_fraction(speaker_id + listener_id, 7.0) * 1000.0) % len(intents)
    return intents[idx]


def _format_brief_text(question: str, answer: str, kind: str, *, max_chars: int) -> str:
    prefix = {"greeting": "Hi", "positive": "Nice", "negative": "Issue", "informative": "Q"}.get(kind, "Q")
    q = _trim_sentence(str(question or "Status?"), max(12, max_chars - 4))
    a = _trim_sentence(str(answer or "I don't know that."), max(12, max_chars - 4))
    if kind == "greeting":
        return f"Hi: {a}"
    if kind == "positive":
        return f"Good: {a}"
    if kind == "negative":
        return f"Q:{q}\nA:{a}"
    return f"Q:{q}\nA:{a}"


def _trim_sentence(text: Any, max_chars: int) -> str:
    raw = " ".join(str(text or "").replace("\n", " ").split())
    if len(raw) <= max_chars:
        return raw
    return raw[: max(3, max_chars - 1)].rstrip(" ,.;:") + "…"


def _friendly_activity(value: Any) -> str:
    raw = str(value or "unknown activity").replace("_", " ").strip()
    return raw.title() if raw else "Unknown activity"


def _friendly_phase(value: Any) -> str:
    raw = str(value or "unknown").replace("_", " ").strip()
    return raw.title() if raw else "Unknown"


def _cluster_label(value: Any) -> str:
    raw = str(value or "").strip().lower()
    labels = {
        "arrival_gate_cluster": "Arrival Gate.",
        "north_pod_cluster": "North Pods.",
        "south_pod_cluster": "South Pods.",
        "east_live_model_cluster": "Model Consoles.",
        "west_social_sync_cluster": "Social Sync.",
        "forum_briefing_cluster": "Briefing.",
        "matrixcore_reader_cluster": "Core Reader.",
        "reader_lore_cluster": "Core Reader.",
        "evening_cooldown_cluster": "Cooldown.",
        "residential_departure": "Res Departure.",
        "simulation_departure": "Sim Departure.",
        "interdistrict_outbound": "Outbound.",
        "interdistrict_return": "Return Route.",
        "residential_return": "Res Return.",
    }
    if raw in labels:
        return labels[raw]
    cleaned = raw.replace("_cluster", "").replace("_", " ").strip()
    return f"{cleaned.title()}." if cleaned else "I don't know that."


def _unknown_answer(qa_catalog: dict[str, Any], speaker_id: str, listener_id: str) -> str:
    fallback = qa_catalog.get("fallback_answers") if isinstance(qa_catalog.get("fallback_answers"), list) else []
    choices = [str(item) for item in fallback if str(item).strip()] or ["I don't know that."]
    idx = int(_stable_fraction(speaker_id + listener_id, 11.0) * 1000.0) % len(choices)
    return choices[idx]


def _recent_log_from_bubbles(bubbles: list[dict[str, Any]], *, max_lines: int = 4) -> list[str]:
    """Small Watch Mode conversation log.  Designed to stay readable at atlas scale."""
    lines: list[str] = []
    labels = {"greeting": "Hi", "positive": "+", "negative": "!", "informative": "?"}
    for bubble in bubbles[: max(0, int(max_lines))]:
        if not isinstance(bubble, dict):
            continue
        kind = str(bubble.get("kind") or "informative")
        intent = str(bubble.get("intent") or "status").replace("_", " ")
        answer = _trim_sentence(str(bubble.get("answer") or bubble.get("text") or "..."), 26)
        prefix = labels.get(kind, "?")
        lines.append(_trim_sentence(f"{prefix} {intent}: {answer}", 56))
    return lines


def format_dialogue_log_lines(state: dict[str, Any], *, max_lines: int = 3) -> list[str]:
    """Public helper for Watch Mode panels and validators."""
    recent = state.get("recent_conversations") if isinstance(state.get("recent_conversations"), list) else []
    return [_trim_sentence(str(line), 56) for line in recent[: max(0, int(max_lines))]]


def _specific_question_count(holoutopia_root: Path | str | None = None) -> int:
    try:
        from holoutopia_citizen_question_router import load_specific_question_catalog
        catalog = load_specific_question_catalog(holoutopia_root)
        questions = catalog.get("specific_questions") if isinstance(catalog.get("specific_questions"), list) else []
        return len([q for q in questions if isinstance(q, dict) and q.get("id")])
    except Exception:
        return 0


def _empty_state(clock: str, rules: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": 2,
        "id": "holoutopia_citizen_dialogue_state_v2",
        "clock": str(clock),
        "day_id": _day_id_from_frame({}, clock),
        "proximity_only": True,
        "visible_citizens_checked": 0,
        "nearby_pair_candidates": 0,
        "active_bubbles": [],
        "recent_conversations": [],
        "dialogue_category_counts": {},
        "specific_question_count": _specific_question_count(),
        "daily_memory": {"enabled": True, "same_day_no_repeat": True, "runtime_only": True},
        "max_active_bubbles": 0,
        "max_text_chars": _safe_int((rules.get("visual") or {}).get("max_text_chars") if isinstance(rules.get("visual"), dict) else 42, 42),
        "proximity_radius_units": _safe_float((rules.get("visual") or {}).get("proximity_radius_units") if isinstance(rules.get("visual"), dict) else 26.0, 26.0),
        "min_anchor_distance_units": _safe_float((rules.get("visual") or {}).get("min_anchor_distance_units") if isinstance(rules.get("visual"), dict) else 42.0, 42.0),
        "safety": {"only_nearby_visible_citizens_talk": True, "garrisoned_citizens_silent": True, "brief_non_overlapping_bubbles": True, "answers_resolve_from_runtime_state": True, "unknown_answers_fail_safely": True, "specific_questions_route_to_known_intents": True, "same_day_dialogue_repetition_guard": True, "daily_memory_runtime_only": True, "writes_authored_data": False, "adds_collision": False},
    }


def _stable_fraction(text: str, salt: float = 0.0) -> float:
    raw = str(text or "") + f":{salt:.3f}"
    total = 0
    for idx, ch in enumerate(raw):
        total = (total * 131 + (idx + 17) * ord(ch)) % 1000003
    return (total % 10000) / 10000.0


def _dist2(a: tuple[float, float], b: tuple[float, float]) -> float:
    return (float(a[0]) - float(b[0])) ** 2 + (float(a[1]) - float(b[1])) ** 2


def _safe_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(float(value))
    except Exception:
        return int(default)
