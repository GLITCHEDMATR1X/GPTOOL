"""Schedule staggering for Simulation Hub activity representatives.

Pass 39E keeps the 1000-resident population virtual, but gives the 20 visible
Simulation Hub representatives different personal schedules and cluster
preferences.  This prevents the capped outdoor population from stacking into one
activity area while preserving the Residential garrison rules.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

STAGGER_REL = Path("database/utopia/simulation/simulation_hub_schedule_staggering.json")
_DEFAULT_STAGGER: dict[str, Any] = {
    "schema": 1,
    "rules": {
        "unique_visible_schedule_profiles": 20,
        "personal_day_offset_minutes_step": 7,
        "personal_day_offset_minutes_jitter": 19,
        "max_representatives_per_activity_cluster": 4,
        "use_cluster_distribution_guard": True,
        "preserve_visible_cap": True,
    },
    "phase_mix": {
        "simulation_hub_work": ["east_live_model_cluster", "north_pod_cluster", "south_pod_cluster", "forum_briefing_cluster", "reader_lore_cluster", "arrival_gate_cluster"],
        "simulation_hub_activity": ["north_pod_cluster", "south_pod_cluster", "west_social_sync_cluster", "forum_briefing_cluster", "reader_lore_cluster", "evening_cooldown_cluster", "arrival_gate_cluster"],
        "returning_to_residential": ["evening_cooldown_cluster", "arrival_gate_cluster", "west_social_sync_cluster"],
    },
    "schedule_archetypes": [
        {"id": "early_model_worker", "work_start": "07:40", "work_end": "15:40", "activity_start": "16:10", "return_home": "20:00", "preferred_clusters": ["east_live_model_cluster", "north_pod_cluster", "reader_lore_cluster"]},
        {"id": "pod_operator", "work_start": "08:00", "work_end": "16:20", "activity_start": "17:00", "return_home": "20:20", "preferred_clusters": ["north_pod_cluster", "south_pod_cluster", "west_social_sync_cluster"]},
        {"id": "briefing_attendee", "work_start": "08:20", "work_end": "17:00", "activity_start": "17:25", "return_home": "20:40", "preferred_clusters": ["forum_briefing_cluster", "arrival_gate_cluster", "reader_lore_cluster"]},
        {"id": "lore_reviewer", "work_start": "09:00", "work_end": "17:30", "activity_start": "18:00", "return_home": "20:55", "preferred_clusters": ["reader_lore_cluster", "forum_briefing_cluster", "evening_cooldown_cluster"]},
        {"id": "social_sync_worker", "work_start": "09:20", "work_end": "16:50", "activity_start": "17:10", "return_home": "20:15", "preferred_clusters": ["west_social_sync_cluster", "south_pod_cluster", "evening_cooldown_cluster"]},
    ],
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


def load_schedule_staggering(holoutopia_root: Path | str | None = None) -> dict[str, Any]:
    data_root = data_root_from_holoutopia(holoutopia_root)
    loaded = _read_json(data_root / STAGGER_REL, _DEFAULT_STAGGER)
    return _deep_merge(_DEFAULT_STAGGER, loaded)


def parse_clock_minutes(value: Any) -> int:
    raw = str(value or "00:00").strip()
    if ":" not in raw:
        return 0
    hh, mm = raw.split(":", 1)
    try:
        return max(0, min(23, int(hh))) * 60 + max(0, min(59, int(mm)))
    except Exception:
        return 0


def _clock_text(minutes: int) -> str:
    minutes = int(minutes) % (24 * 60)
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _stable_int(seed: str, modulo: int) -> int:
    if modulo <= 0:
        return 0
    digest = hashlib.sha256(str(seed).encode("utf-8", "ignore")).digest()
    return int.from_bytes(digest[:8], "big") % modulo


def schedule_profile_for_representative(
    holoutopia_root: Path | str | None,
    *,
    clock_minutes: int,
    slot: int,
    resident_sequence: int,
    global_phase: str,
) -> dict[str, Any]:
    """Return a deterministic personal schedule profile for one visible citizen.

    The profile deliberately varies start/end times and cluster preferences, but
    does not create extra visible citizens beyond the district cap.
    """
    data = load_schedule_staggering(holoutopia_root)
    rules = data.get("rules") if isinstance(data.get("rules"), dict) else {}
    archetypes = data.get("schedule_archetypes") if isinstance(data.get("schedule_archetypes"), list) else []
    archetypes = [a for a in archetypes if isinstance(a, dict)] or list(_DEFAULT_STAGGER["schedule_archetypes"])
    archetype = archetypes[(int(slot) + _stable_int(f"resident:{resident_sequence}", len(archetypes))) % len(archetypes)]
    step = int(rules.get("personal_day_offset_minutes_step", 7) or 7)
    jitter_max = max(0, int(rules.get("personal_day_offset_minutes_jitter", 19) or 0))
    jitter = _stable_int(f"jitter:{resident_sequence}:{slot}", jitter_max + 1) if jitter_max else 0
    personal_offset = (int(slot) * step + jitter) % 120
    personal_minutes = (int(clock_minutes) - personal_offset) % (24 * 60)

    work_start = (parse_clock_minutes(archetype.get("work_start", "08:00")) + personal_offset // 3) % (24 * 60)
    work_end = (parse_clock_minutes(archetype.get("work_end", "17:00")) + personal_offset // 2) % (24 * 60)
    activity_start = (parse_clock_minutes(archetype.get("activity_start", "17:00")) + personal_offset // 4) % (24 * 60)
    return_home = (parse_clock_minutes(archetype.get("return_home", "20:00")) + personal_offset // 5) % (24 * 60)

    # For visible Simulation Hub representatives, use the global city phase as
    # the hard gate, then vary cluster preference within that gate.  This keeps
    # screenshots populated while still making each citizen's daily profile unique.
    if str(global_phase) == "simulation_hub_work":
        personal_phase = "work_shift"
        motive = "work"
    elif str(global_phase) == "simulation_hub_activity":
        if personal_minutes < activity_start and (slot % 5 in {0, 3}):
            personal_phase = "late_work_shift"
            motive = "work"
        elif personal_minutes >= return_home or slot % 7 == 0:
            personal_phase = "cooldown_replenish"
            motive = "replenish"
        else:
            personal_phase = "evening_activity"
            motive = "activities"
    elif str(global_phase) == "returning_to_residential":
        personal_phase = "returning_home"
        motive = "replenish"
    else:
        personal_phase = "home_garrison"
        motive = "home"

    phase_mix = data.get("phase_mix") if isinstance(data.get("phase_mix"), dict) else {}
    phase_clusters = phase_mix.get(str(global_phase), []) if isinstance(phase_mix.get(str(global_phase)), list) else []
    preferred = [str(v) for v in archetype.get("preferred_clusters", []) if str(v).strip()]
    if phase_clusters:
        # Interleave personal preference with the phase-wide palette.
        phase_clusters = [str(v) for v in phase_clusters if str(v).strip()]
        rotated = phase_clusters[int(slot) % len(phase_clusters):] + phase_clusters[:int(slot) % len(phase_clusters)]
        preferred = list(dict.fromkeys(preferred + rotated))
    return {
        "schedule_profile_id": f"sim_sched_{int(slot):02d}_{str(archetype.get('id') or 'resident')}",
        "schedule_archetype": str(archetype.get("id") or "resident"),
        "personal_day_offset_minutes": personal_offset,
        "personal_clock": _clock_text(personal_minutes),
        "personal_phase": personal_phase,
        "motive": motive,
        "work_start": _clock_text(work_start),
        "work_end": _clock_text(work_end),
        "activity_start": _clock_text(activity_start),
        "return_home": _clock_text(return_home),
        "preferred_clusters": preferred,
        "max_representatives_per_activity_cluster": int(rules.get("max_representatives_per_activity_cluster", 4) or 4),
    }


def order_nodes_for_schedule(nodes: list[dict[str, Any]], profile: dict[str, Any], *, slot: int, clock_minutes: int) -> list[dict[str, Any]]:
    if not nodes:
        return []
    preferred = [str(v) for v in profile.get("preferred_clusters", []) if str(v).strip()]
    pref_index = {cid: idx for idx, cid in enumerate(preferred)}
    def node_key(node: dict[str, Any]) -> tuple[int, int, str]:
        cid = str(node.get("cluster_id") or "")
        pref = pref_index.get(cid, 999)
        stable = _stable_int(f"{clock_minutes}:{slot}:{cid}:{node.get('node_id')}", 10000)
        return (pref, stable, str(node.get("node_id") or ""))
    ordered = sorted([n for n in nodes if isinstance(n, dict)], key=node_key)
    if ordered:
        start = (int(slot) + int(clock_minutes) // 30) % len(ordered)
        ordered = ordered[start:] + ordered[:start]
    return ordered


def choose_distributed_node(
    nodes: list[dict[str, Any]],
    profile: dict[str, Any],
    cluster_counts: dict[str, int],
    *,
    slot: int,
    clock_minutes: int,
) -> dict[str, Any] | None:
    ordered = order_nodes_for_schedule(nodes, profile, slot=slot, clock_minutes=clock_minutes)
    if not ordered:
        return None
    max_per = max(1, int(profile.get("max_representatives_per_activity_cluster", 4) or 4))
    for node in ordered:
        cid = str(node.get("cluster_id") or "unclustered")
        if cluster_counts.get(cid, 0) < max_per:
            cluster_counts[cid] = cluster_counts.get(cid, 0) + 1
            return node
    # If every preferred cluster is full, choose the least crowded instead of piling onto the first.
    least = min(ordered, key=lambda n: (cluster_counts.get(str(n.get("cluster_id") or "unclustered"), 0), str(n.get("node_id") or "")))
    cid = str(least.get("cluster_id") or "unclustered")
    cluster_counts[cid] = cluster_counts.get(cid, 0) + 1
    return least


def validate_schedule_staggering(holoutopia_root: Path | str | None = None) -> list[str]:
    data = load_schedule_staggering(holoutopia_root)
    errors: list[str] = []
    rules = data.get("rules") if isinstance(data.get("rules"), dict) else {}
    if int(rules.get("unique_visible_schedule_profiles", 0) or 0) < 20:
        errors.append("unique_visible_schedule_profiles must be at least 20")
    if int(rules.get("max_representatives_per_activity_cluster", 0) or 0) <= 0:
        errors.append("max_representatives_per_activity_cluster must be positive")
    if not isinstance(data.get("schedule_archetypes"), list) or len(data.get("schedule_archetypes", [])) < 5:
        errors.append("expected at least 5 schedule archetypes")
    for phase in ("simulation_hub_work", "simulation_hub_activity"):
        clusters = ((data.get("phase_mix") or {}).get(phase) if isinstance(data.get("phase_mix"), dict) else [])
        if not isinstance(clusters, list) or len(set(str(v) for v in clusters)) < 5:
            errors.append(f"{phase} should distribute across at least 5 clusters")
    profiles = [schedule_profile_for_representative(holoutopia_root, clock_minutes=18 * 60 + 15, slot=i, resident_sequence=200 + i, global_phase="simulation_hub_activity") for i in range(20)]
    profile_ids = {p.get("schedule_profile_id") for p in profiles}
    offsets = {p.get("personal_day_offset_minutes") for p in profiles}
    if len(profile_ids) != 20:
        errors.append("visible representative schedule profile ids are not unique")
    if len(offsets) < 12:
        errors.append("expected at least 12 distinct personal schedule offsets")
    return errors
