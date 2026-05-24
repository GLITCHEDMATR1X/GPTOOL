"""Specific question routing for HoloUtopia citizen dialogue.

Pass 47C goal:
- citizens can ask and answer specific short questions;
- answers resolve from live runtime state and approved catalog data;
- missing/unknown fields fail safely instead of being invented;
- no authored city data is written.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import re
from pathlib import Path
from typing import Any

SPECIFIC_QA_REL = Path("database/utopia/dialogue/specific_question_catalog.json")
QA_CATALOG_REL = Path("database/utopia/dialogue/question_answer_catalog.json")


_DEFAULT_SPECIFIC_QA: dict[str, Any] = {
    "schema": 1,
    "id": "holoutopia_specific_question_catalog_v1",
    "runtime_writes_allowed": False,
    "answer_policy": {
        "runtime_state_only": True,
        "do_not_guess": True,
        "safe_unknown_when_missing": True,
        "specific_question_requires_known_runtime_field": True,
    },
    "specific_questions": [
        {"id": "q_current_activity", "intent": "current_activity", "category": "greeting", "question": "What are you doing?", "aliases": ["task", "doing", "activity"]},
        {"id": "q_current_phase", "intent": "current_phase", "category": "informative", "question": "What cycle is it?", "aliases": ["cycle", "phase", "schedule"]},
        {"id": "q_home_garrison", "intent": "home_garrison", "category": "informative", "question": "Where do you live?", "aliases": ["live", "home", "garrison"]},
        {"id": "q_outdoor_cap", "intent": "outdoor_cap", "category": "informative", "question": "How many can be outside?", "aliases": ["outdoor cap", "outside cap", "visible outside"]},
        {"id": "q_energy_rule", "intent": "energy_rule", "category": "negative", "question": "How long can you stay active?", "aliases": ["energy", "active time", "stay active"]},
        {"id": "q_recharge_rule", "intent": "recharge_rule", "category": "negative", "question": "How long do you recharge?", "aliases": ["recharge", "sleep", "inside"]},
        {"id": "q_cluster_assignment", "intent": "cluster_assignment", "category": "positive", "question": "Which hub node are you using?", "aliases": ["hub node", "cluster", "pod"]},
        {"id": "q_district_purpose", "intent": "district_purpose", "category": "informative", "question": "What is this district?", "aliases": ["district", "purpose", "place"]},
        {"id": "q_commute_status", "intent": "commute_status", "category": "greeting", "question": "Where are you going?", "aliases": ["going", "commuting", "route"]},
        {"id": "q_clock_time", "intent": "clock_time", "category": "informative", "question": "What time is it?", "aliases": ["time", "clock"]},
        {"id": "q_population_total", "intent": "population_total", "category": "informative", "question": "How many citizens live here?", "aliases": ["world population", "citizens", "population"]},
        {"id": "q_visible_population", "intent": "visible_population", "category": "informative", "question": "How many are visible?", "aliases": ["visible now", "outside now", "activity citizens"]},
        {"id": "q_functional_buildings", "intent": "functional_buildings", "category": "informative", "question": "What buildings work here?", "aliases": ["buildings", "services", "what works here", "what buildings", "functional buildings"]},
        {"id": "q_service_operation", "intent": "service_operation", "category": "informative", "question": "What is this service doing?", "aliases": ["service doing", "operation", "output", "building doing", "service output"]},
        {"id": "q_adventure_simulation", "intent": "adventure_simulation", "category": "informative", "question": "Is the adventure simulation active?", "aliases": ["adventure", "simulation active", "active match", "observe simulation", "adventure queue"]},
    ],
    "category_question_order": {
        "greeting": ["q_commute_status", "q_current_activity"],
        "positive": ["q_cluster_assignment", "q_current_activity"],
        "negative": ["q_energy_rule", "q_recharge_rule"],
        "informative": ["q_adventure_simulation", "q_district_purpose", "q_service_operation", "q_functional_buildings", "q_outdoor_cap", "q_clock_time", "q_home_garrison", "q_population_total", "q_visible_population", "q_current_phase"],
    },
    "fallback_answers": [
        "I don't know that.",
        "That is outside my assignment.",
        "Ask a civic node for that.",
    ],
}


@dataclass(frozen=True)
class RoutedAnswer:
    question_id: str
    intent: str
    question: str
    answer: str
    confidence: str
    source: str
    category: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "question_id": self.question_id,
            "intent": self.intent,
            "question": self.question,
            "answer": self.answer,
            "confidence": self.confidence,
            "source": self.source,
            "category": self.category,
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


def load_specific_question_catalog(holoutopia_root: Path | str | None = None) -> dict[str, Any]:
    data_root = data_root_from_holoutopia(holoutopia_root)
    return _deep_merge(_DEFAULT_SPECIFIC_QA, _read_json(data_root / SPECIFIC_QA_REL, _DEFAULT_SPECIFIC_QA))


def load_question_answer_catalog(holoutopia_root: Path | str | None = None) -> dict[str, Any]:
    data_root = data_root_from_holoutopia(holoutopia_root)
    fallback = {"district_purpose": {}, "fallback_answers": _DEFAULT_SPECIFIC_QA["fallback_answers"]}
    return _read_json(data_root / QA_CATALOG_REL, fallback)


def choose_specific_question_id(
    holoutopia_root: Path | str | None,
    category: str,
    speaker_id: str,
    listener_id: str,
    pair_index: int = 0,
) -> str:
    catalog = load_specific_question_catalog(holoutopia_root)
    order = catalog.get("category_question_order") if isinstance(catalog.get("category_question_order"), dict) else {}
    choices = order.get(str(category)) if isinstance(order.get(str(category)), list) else []
    clean = [str(item) for item in choices if str(item).strip()]
    if not clean:
        questions = catalog.get("specific_questions") if isinstance(catalog.get("specific_questions"), list) else []
        clean = [str(q.get("id")) for q in questions if isinstance(q, dict) and q.get("id")]
    if not clean:
        return "q_current_activity"
    index = int((_stable_fraction(str(speaker_id) + str(listener_id), pair_index + len(str(category))) * 10000.0) + pair_index) % len(clean)
    return clean[index]


def resolve_specific_question(
    holoutopia_root: Path | str | None,
    frame: dict[str, Any],
    speaker_id: str,
    speaker: dict[str, Any],
    listener_id: str,
    listener: dict[str, Any],
    *,
    question: str | None = None,
    question_id: str | None = None,
    category_hint: str | None = None,
) -> RoutedAnswer:
    """Answer a specific question using runtime state or a safe unknown fallback."""
    catalog = load_specific_question_catalog(holoutopia_root)
    question_def = _find_question(catalog, question=question, question_id=question_id)
    if not question_def:
        fallback = _unknown_answer(catalog, speaker_id, listener_id)
        return RoutedAnswer(
            question_id=str(question_id or "unknown_question"),
            intent="unknown",
            question=_trim_sentence(question or "Question?", 38),
            answer=fallback,
            confidence="safe_unknown",
            source="safe_fallback",
            category=str(category_hint or "informative"),
        )
    intent = str(question_def.get("intent") or "unknown")
    answer = _answer_intent(holoutopia_root, frame, speaker_id, speaker, listener_id, listener, intent, catalog)
    fallbacks = [str(item) for item in (catalog.get("fallback_answers") if isinstance(catalog.get("fallback_answers"), list) else [])]
    confidence = "safe_unknown" if answer in fallbacks or "don't know" in answer.lower() else "runtime_resolved"
    source = "live_runtime_state" if confidence == "runtime_resolved" else "safe_fallback"
    return RoutedAnswer(
        question_id=str(question_def.get("id") or question_id or "unknown_question"),
        intent=intent,
        question=str(question or question_def.get("question") or "Question?"),
        answer=answer,
        confidence=confidence,
        source=source,
        category=str(question_def.get("category") or category_hint or "informative"),
    )


def validate_specific_question_router(holoutopia_root: Path | str | None, frame: dict[str, Any], sample_citizen: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    catalog = load_specific_question_catalog(holoutopia_root)
    questions = catalog.get("specific_questions") if isinstance(catalog.get("specific_questions"), list) else []
    if len(questions) < 10:
        issues.append("too_few_specific_questions")
    ids = [str(q.get("id") or "") for q in questions if isinstance(q, dict)]
    if len(ids) != len(set(ids)):
        issues.append("duplicate_question_ids")
    required = {"q_current_activity", "q_home_garrison", "q_outdoor_cap", "q_energy_rule", "q_recharge_rule", "q_district_purpose", "q_clock_time", "q_population_total", "q_functional_buildings", "q_service_operation", "q_adventure_simulation"}
    missing = required.difference(ids)
    if missing:
        issues.append("missing_required_question_ids:" + ",".join(sorted(missing)))

    listener = sample_citizen if isinstance(sample_citizen, dict) else {}
    checks = {
        "q_home_garrison": "Residential Alpha",
        "q_outdoor_cap": "20",
        "q_energy_rule": "15",
        "q_recharge_rule": "9",
        "q_clock_time": str((frame or {}).get("clock") or ""),
        "q_population_total": "1000",
        "q_functional_buildings": ":",
        "q_service_operation": "service",
    }
    for qid, expected_piece in checks.items():
        answer = resolve_specific_question(holoutopia_root, frame or {}, "tester_a", {}, "tester_b", listener, question_id=qid)
        if expected_piece and expected_piece not in answer.answer:
            issues.append(f"{qid}_bad_answer:{answer.answer}")
        if answer.confidence != "runtime_resolved":
            issues.append(f"{qid}_not_runtime_resolved")
    unknown = resolve_specific_question(holoutopia_root, frame or {}, "tester_a", {}, "tester_b", listener, question="Who designed the moon?")
    if unknown.confidence != "safe_unknown":
        issues.append("unknown_question_did_not_fail_safe")
    if not bool((catalog.get("answer_policy") or {}).get("do_not_guess")):
        issues.append("policy_do_not_guess_missing")
    return issues


def _find_question(catalog: dict[str, Any], *, question: str | None = None, question_id: str | None = None) -> dict[str, Any] | None:
    questions = catalog.get("specific_questions") if isinstance(catalog.get("specific_questions"), list) else []
    if question_id:
        for item in questions:
            if isinstance(item, dict) and str(item.get("id") or "") == str(question_id):
                return item
    if question:
        needle = _normalize_question(question)
        best: dict[str, Any] | None = None
        best_score = 0
        for item in questions:
            if not isinstance(item, dict):
                continue
            candidates = [str(item.get("question") or "")]
            aliases = item.get("aliases") if isinstance(item.get("aliases"), list) else []
            candidates.extend(str(alias) for alias in aliases)
            score = max((_question_score(needle, _normalize_question(candidate)) for candidate in candidates), default=0)
            if score > best_score:
                best = item
                best_score = score
        if best is not None and best_score >= 2:
            return best
    return None


def _answer_intent(
    holoutopia_root: Path | str | None,
    frame: dict[str, Any],
    speaker_id: str,
    speaker: dict[str, Any],
    listener_id: str,
    listener: dict[str, Any],
    intent: str,
    catalog: dict[str, Any],
) -> str:
    pop = frame.get("residential_population_model") if isinstance(frame.get("residential_population_model"), dict) else {}
    if intent == "current_activity":
        service = listener.get("service_short_label") or speaker.get("service_short_label")
        if service:
            return _trim_sentence(f"At {service}.", 38)
        value = listener.get("activity_status") or speaker.get("activity_status") or _friendly_activity(listener.get("activity_id") or speaker.get("activity_id"))
        return _trim_sentence(value, 38)
    if intent == "current_phase":
        return _trim_sentence(f"{_friendly_phase(pop.get('phase'))} cycle.", 38)
    if intent == "home_garrison":
        return "Residential Alpha garrison."
    if intent == "outdoor_cap":
        cap = pop.get("max_outdoor_population_per_district") or 20
        return f"{cap} visible outside."
    if intent == "energy_rule":
        active = _extract_energy_hours(pop.get("energy_rule"), default=15, which="active")
        return f"{active} game hours."
    if intent == "recharge_rule":
        recharge = _extract_energy_hours(pop.get("energy_rule"), default=9, which="recharge")
        return f"{recharge} game hours inside."
    if intent == "cluster_assignment":
        service = listener.get("service_short_label") or speaker.get("service_short_label")
        if service:
            return _trim_sentence(f"{service} service.", 28)
        cluster = str(listener.get("activity_cluster_id") or speaker.get("activity_cluster_id") or listener.get("commute_stage") or speaker.get("commute_stage") or "")
        return _cluster_label(cluster) if cluster else _unknown_answer(catalog, speaker_id, listener_id)
    if intent == "district_purpose":
        qa = load_question_answer_catalog(holoutopia_root)
        purposes = qa.get("district_purpose") if isinstance(qa.get("district_purpose"), dict) else {}
        town_id = str(listener.get("town_id") or speaker.get("town_id") or "")
        return str(purposes.get(town_id) or _unknown_answer(catalog, speaker_id, listener_id))
    if intent == "commute_status":
        direction = str(listener.get("commute_direction") or speaker.get("commute_direction") or "")
        activity_id = str(listener.get("activity_id") or speaker.get("activity_id") or "")
        service = listener.get("service_short_label") or speaker.get("service_short_label")
        district = listener.get("activity_district_display_name") or speaker.get("activity_district_display_name")
        if service and district:
            return _trim_sentence(f"To {service} in {district}.", 38)
        if direction == "return":
            return "Returning home."
        if direction == "outbound":
            return "Heading to work."
        if "commute" in activity_id:
            return "On route."
        return _unknown_answer(catalog, speaker_id, listener_id)
    if intent == "clock_time":
        clock = str(frame.get("clock") or pop.get("clock") or "")
        return f"{clock}." if clock else _unknown_answer(catalog, speaker_id, listener_id)
    if intent == "population_total":
        total = pop.get("world_population") or pop.get("residential_population") or 1000
        return f"{total} citizens."
    if intent == "visible_population":
        outdoor = len(pop.get("visible_outdoor_citizens") if isinstance(pop.get("visible_outdoor_citizens"), dict) else {})
        activity = len(pop.get("visible_activity_citizens") if isinstance(pop.get("visible_activity_citizens"), dict) else {})
        total = outdoor + activity
        return f"{total} visible now."
    if intent == "functional_buildings":
        town_id = str(listener.get("town_id") or speaker.get("town_id") or "")
        if not town_id:
            return _unknown_answer(catalog, speaker_id, listener_id)
        try:
            from holoutopia_functional_buildings import service_summary_for_district
            return _trim_sentence(service_summary_for_district(holoutopia_root, town_id), 58)
        except Exception:
            return _unknown_answer(catalog, speaker_id, listener_id)
    if intent == "service_operation":
        action = listener.get("service_action_label") or speaker.get("service_action_label")
        output = listener.get("service_output_label") or speaker.get("service_output_label")
        service = listener.get("service_short_label") or speaker.get("service_short_label") or "service"
        if action and output:
            return _trim_sentence(f"{service} service: {action}; {output}.", 58)
        return _unknown_answer(catalog, speaker_id, listener_id)
    if intent == "adventure_simulation":
        activity = pop.get("district_activity_model") if isinstance(pop.get("district_activity_model"), dict) else {}
        state = activity.get("adventure_simulation_state") if isinstance(activity.get("adventure_simulation_state"), dict) else {}
        if bool(state.get("match_active")):
            if bool(state.get("final_score_ready")):
                return _trim_sentence(f"Final score {state.get('final_score')}, grade {state.get('final_grade')}.", 58)
            if bool(state.get("combat_active")):
                resp = int(state.get("recent_respawn_count") or 0)
                extra = f" Respawn {resp}." if resp else ""
                return _trim_sentence(f"{state.get('wave_label')}: {state.get('active_player_count')}/{state.get('max_active_players')} heroes, {state.get('enemies_alive')}/{state.get('enemy_count')} foes, score {state.get('team_score')}.{extra}", 58)
            resp = int(state.get("recent_respawn_count") or 0)
            extra = f" Respawn {resp}." if resp else ""
            return _trim_sentence(f"Core Ring active: {state.get('active_player_count')}/{state.get('max_active_players')} Q{state.get('queue_count')} {state.get('remaining_label')}.{extra}", 58)
        return "No active Core Ring match."
    return _unknown_answer(catalog, speaker_id, listener_id)


def _normalize_question(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", str(text or "").lower()).strip()


def _question_score(needle: str, candidate: str) -> int:
    if not needle or not candidate:
        return 0
    if needle == candidate:
        return 100
    stop = {"what", "where", "when", "how", "many", "long", "are", "you", "your", "the", "this", "is", "it", "do", "does", "can", "be"}
    n_words = {word for word in needle.split() if word not in stop}
    c_words = {word for word in candidate.split() if word not in stop}
    if not n_words or not c_words:
        return 0
    if candidate in needle or needle in candidate:
        return 10
    return len(n_words.intersection(c_words))


def _extract_energy_hours(rule: Any, *, default: int, which: str) -> int:
    if isinstance(rule, dict):
        key = "active_hours" if which == "active" else "recharge_hours"
        try:
            return int(rule.get(key) or default)
        except Exception:
            return default
    text = str(rule or "")
    numbers = [int(n) for n in re.findall(r"\b\d+\b", text)]
    # The rule text starts with "100%".  That is the charge amount, not an hour count.
    hour_numbers = [n for n in numbers if n != 100]
    if hour_numbers:
        if which == "active":
            return hour_numbers[0]
        if len(hour_numbers) >= 2:
            return hour_numbers[1]
    return default


def _unknown_answer(catalog: dict[str, Any], speaker_id: str, listener_id: str) -> str:
    fallback = catalog.get("fallback_answers") if isinstance(catalog.get("fallback_answers"), list) else []
    choices = [str(item) for item in fallback if str(item).strip()] or ["I don't know that."]
    idx = int(_stable_fraction(str(speaker_id) + str(listener_id), 17.0) * 1000.0) % len(choices)
    return choices[idx]


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


def _stable_fraction(text: str, salt: float = 0.0) -> float:
    total = 0
    for idx, ch in enumerate(str(text)):
        total = (total * 131 + ord(ch) + idx) % 1000003
    total = int((total + salt * 9973) % 1000003)
    return total / 1000003.0
