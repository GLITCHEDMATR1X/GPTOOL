"""Small visible activity behavior states for HoloUtopia citizens.

Pass 39D keeps population simulation conservative while making the visible
Simulation Hub representatives read as people doing different activities.  This
module is data-driven and pure Python so validators can check behavior payloads
without launching Panda3D.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

BEHAVIORS_REL = Path("database/utopia/simulation/simulation_hub_activity_behaviors.json")
CLUSTERS_REL = Path("database/utopia/simulation/simulation_hub_activity_clusters.json")

_DEFAULT_BEHAVIOR = {
    "schema": 1,
    "behavior_families": {
        "activity": {"pose": "idle_activity", "status": "using the Simulation Hub", "animation_speed": 1.4, "animation_amp": 2.5, "face_target": "cluster_center", "priority": 99}
    },
    "cluster_family_overrides": {},
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


def load_activity_behaviors(holoutopia_root: Path | str | None = None) -> dict[str, Any]:
    data_root = data_root_from_holoutopia(holoutopia_root)
    loaded = _read_json(data_root / BEHAVIORS_REL, _DEFAULT_BEHAVIOR)
    merged = copy.deepcopy(_DEFAULT_BEHAVIOR)
    for key, value in loaded.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key].update(value)
        else:
            merged[key] = value
    return merged


def load_cluster_family_map(holoutopia_root: Path | str | None = None) -> dict[str, str]:
    data_root = data_root_from_holoutopia(holoutopia_root)
    clusters = _read_json(data_root / CLUSTERS_REL, {"clusters": []})
    out: dict[str, str] = {}
    for cluster in clusters.get("clusters", []) if isinstance(clusters.get("clusters"), list) else []:
        if not isinstance(cluster, dict):
            continue
        cid = str(cluster.get("cluster_id") or "").strip()
        fam = str(cluster.get("activity_family") or "activity").strip() or "activity"
        if cid:
            out[cid] = fam
    overrides = load_activity_behaviors(holoutopia_root).get("cluster_family_overrides", {})
    if isinstance(overrides, dict):
        for cid, fam in overrides.items():
            if str(cid).strip():
                out[str(cid)] = str(fam or "activity")
    return out


def behavior_for_cluster(holoutopia_root: Path | str | None, cluster_id: str, *, fallback_family: str = "activity") -> dict[str, Any]:
    behaviors = load_activity_behaviors(holoutopia_root)
    family_map = load_cluster_family_map(holoutopia_root)
    family = family_map.get(str(cluster_id), fallback_family or "activity")
    families = behaviors.get("behavior_families") if isinstance(behaviors.get("behavior_families"), dict) else {}
    behavior = families.get(family) if isinstance(families.get(family), dict) else families.get("activity", {})
    result = copy.deepcopy(behavior if isinstance(behavior, dict) else {})
    result.setdefault("pose", "idle_activity")
    result.setdefault("status", "using the Simulation Hub")
    result.setdefault("animation_speed", 1.4)
    result.setdefault("animation_amp", 2.5)
    result.setdefault("face_target", "cluster_center")
    result["activity_family"] = family
    return result


def enrich_activity_citizen(holoutopia_root: Path | str | None, citizen: dict[str, Any]) -> dict[str, Any]:
    """Attach small visible-behavior data to a district activity representative."""
    enriched = dict(citizen)
    cluster_id = str(enriched.get("activity_cluster_id") or "")
    fallback_family = str(enriched.get("activity_family") or "activity")
    if bool(enriched.get("functional_service_assignment")):
        service_type = str(enriched.get("service_type") or "").lower()
        motive = str(enriched.get("motive") or "").lower()
        service_role = str(enriched.get("service_role") or "").lower()
        if motive == "work" or any(token in service_type + service_role for token in ("office", "factory", "dock", "utility", "lab", "monitor", "checkpoint", "bay")):
            fallback_family = "work"
        if any(token in service_type + service_role for token in ("forum", "plaza", "stalls", "walk", "social", "commons")):
            fallback_family = "social"
        if any(token in service_type + service_role for token in ("reader", "vault", "archive", "memory", "research")):
            fallback_family = "lore"
        if any(token in service_type + service_role for token in ("pod", "core", "simulation")):
            fallback_family = "pod"
        if motive == "replenish" or any(token in service_type + service_role for token in ("water", "ward", "recovery", "stabilization")):
            fallback_family = "cooldown"
    behavior = behavior_for_cluster(holoutopia_root, cluster_id, fallback_family=fallback_family)
    enriched["activity_family"] = str(behavior.get("activity_family") or "activity")
    enriched["activity_pose"] = str(behavior.get("pose") or "idle_activity")
    enriched["activity_status"] = str(behavior.get("status") or enriched.get("current_task_readable") or "using the Simulation Hub")
    enriched["activity_face_target"] = str(behavior.get("face_target") or "cluster_center")
    try:
        enriched["activity_animation_speed"] = float(behavior.get("animation_speed", 1.4))
    except Exception:
        enriched["activity_animation_speed"] = 1.4
    try:
        enriched["activity_animation_amp"] = float(behavior.get("animation_amp", 2.5))
    except Exception:
        enriched["activity_animation_amp"] = 2.5
    # Keep the panel text human-readable while preserving the original node label.
    readable = str(enriched.get("current_task_readable") or "").strip()
    status = str(enriched.get("activity_status") or "").strip()
    if bool(enriched.get("functional_service_assignment")):
        service = str(enriched.get("service_short_label") or enriched.get("service_building_name") or "service")
        status = f"using {service}"
        enriched["activity_status"] = status
    if status and status.lower() not in readable.lower():
        enriched["current_task_readable"] = status
    if bool(enriched.get("functional_service_assignment")):
        try:
            from holoutopia_service_behaviors import enrich_service_citizen
            enriched = enrich_service_citizen(holoutopia_root, enriched)
        except Exception:
            # Service behavior is visual/status metadata only; keep routing valid.
            pass
    return enriched


def validate_activity_behaviors(holoutopia_root: Path | str | None = None) -> list[str]:
    data = load_activity_behaviors(holoutopia_root)
    errors: list[str] = []
    families = data.get("behavior_families") if isinstance(data.get("behavior_families"), dict) else {}
    required = {"arrival", "pod", "work", "social", "briefing", "lore", "cooldown", "activity"}
    missing = sorted(required - set(str(k) for k in families.keys()))
    if missing:
        errors.append(f"missing behavior families: {', '.join(missing)}")
    for family, behavior in families.items():
        if not isinstance(behavior, dict):
            errors.append(f"behavior family {family} is not an object")
            continue
        for field in ("pose", "status", "animation_speed", "animation_amp", "face_target"):
            if field not in behavior:
                errors.append(f"behavior family {family} missing {field}")
        try:
            if float(behavior.get("animation_speed", 0)) <= 0:
                errors.append(f"behavior family {family} has non-positive animation_speed")
            if float(behavior.get("animation_amp", 0)) < 0:
                errors.append(f"behavior family {family} has negative animation_amp")
        except Exception:
            errors.append(f"behavior family {family} has invalid animation values")
    cmap = load_cluster_family_map(holoutopia_root)
    if len(cmap) < 6:
        errors.append("expected at least 6 cluster behavior mappings")
    return errors
