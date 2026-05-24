"""Residential <-> Simulation Hub commute staging for visible citizens.

Pass 39F does not expand the real population into hundreds of actors.  It
adds a deterministic commute layer for the capped visible representatives so
citizens leave Residential, walk through safe street targets, arrive at the
Central Simulation Hub, and later return home without piling onto one node.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

COMMUTE_REL = Path("database/utopia/simulation/simulation_hub_commute_flow.json")

_DEFAULT_COMMUTE: dict[str, Any] = {
    "schema": 1,
    "id": "holoutopia_simulation_hub_commute_flow_v1",
    "runtime_writes_allowed": False,
    "home_town_id": "residential_alpha",
    "destination_town_id": "central_core_civic_ring",
    "visible_commute_cap": 20,
    "rules": {
        "departure_window": ["06:00", "08:00"],
        "return_window": ["20:00", "21:00"],
        "personal_departure_spread_minutes": 88,
        "personal_return_spread_minutes": 42,
        "commute_lane_count": 4,
        "safe_target_policy": "target_grid_is_snapped_against_authored_streets_before_rendering",
    },
    "route_targets": {
        "outbound_residential": [[1.10, 3.00], [2.20, 3.00], [3.40, 3.00], [4.80, 3.00], [6.10, 3.00], [7.60, 3.00], [8.05, 3.10]],
        "outbound_simulation": [[1.15, 3.00], [2.35, 3.00], [3.25, 3.00], [4.00, 3.00]],
        "return_simulation": [[4.00, 3.00], [3.20, 3.00], [2.30, 3.00], [1.20, 3.00]],
        "return_residential": [[8.05, 3.10], [7.15, 3.00], [6.05, 3.00], [4.80, 3.00], [3.60, 3.00], [2.20, 3.00], [1.10, 3.00]],
    },
    "stage_labels": {
        "residential_departure": "walking from home garrison to Residential west gate",
        "interdistrict_outbound": "crossing from Residential toward the Central Simulation Hub",
        "simulation_arrival": "arriving at the Central Simulation Hub",
        "simulation_departure": "leaving the Central Simulation Hub",
        "interdistrict_return": "crossing back toward Residential",
        "residential_return": "returning to home garrison"
    }
}


def _data_root_from_holoutopia(holoutopia_root: Path | str | None = None) -> Path:
    root = Path(holoutopia_root or Path(__file__).resolve().parent).resolve()
    return root.parent if root.name.lower() in {"holoverse", "holoutopia"} else root


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


def load_commute_flow(holoutopia_root: Path | str | None = None) -> dict[str, Any]:
    data_root = _data_root_from_holoutopia(holoutopia_root)
    return _deep_merge(_DEFAULT_COMMUTE, _read_json(data_root / COMMUTE_REL, _DEFAULT_COMMUTE))


def parse_clock_minutes(value: Any) -> int:
    raw = str(value or "00:00").strip()
    if ":" not in raw:
        return 0
    hh, mm = raw.split(":", 1)
    try:
        return max(0, min(23, int(hh))) * 60 + max(0, min(59, int(mm)))
    except Exception:
        return 0


def _stable_fraction(seed: str) -> float:
    digest = hashlib.sha256(str(seed).encode("utf-8", "ignore")).digest()
    return int.from_bytes(digest[:8], "big") / float(2**64 - 1)


def _lerp_path(points: list[list[float]], progress: float, *, lane: int = 0, lane_count: int = 4) -> tuple[float, float]:
    if not points:
        return (4.0, 3.0)
    if len(points) == 1:
        return (float(points[0][0]), float(points[0][1]))
    progress = max(0.0, min(1.0, float(progress)))
    scaled = progress * (len(points) - 1)
    idx = min(len(points) - 2, int(scaled))
    local_t = scaled - idx
    ax, ay = float(points[idx][0]), float(points[idx][1])
    bx, by = float(points[idx + 1][0]), float(points[idx + 1][1])
    x = ax + (bx - ax) * local_t
    y = ay + (by - ay) * local_t
    # Small lane offset keeps multiple citizens separated while staying on the same dark street slab.
    lane_count = max(1, int(lane_count))
    lane_norm = (int(lane) % lane_count) - (lane_count - 1) * 0.5
    dx, dy = bx - ax, by - ay
    length = max(0.001, (dx * dx + dy * dy) ** 0.5)
    nx, ny = -dy / length, dx / length
    offset = lane_norm * 0.085
    return (x + nx * offset, y + ny * offset)


def commute_profile_for_visible_slot(
    holoutopia_root: Path | str | None,
    *,
    phase: str,
    clock_minutes: int,
    slot: int,
    resident_sequence: int,
) -> dict[str, Any]:
    data = load_commute_flow(holoutopia_root)
    rules = data.get("rules") if isinstance(data.get("rules"), dict) else {}
    routes = data.get("route_targets") if isinstance(data.get("route_targets"), dict) else {}
    labels = data.get("stage_labels") if isinstance(data.get("stage_labels"), dict) else {}
    home_town = str(data.get("home_town_id") or "residential_alpha")
    dest_town = str(data.get("destination_town_id") or "central_core_civic_ring")
    lane_count = max(1, int(rules.get("commute_lane_count", 4) or 4))
    lane = int(slot) % lane_count
    if phase == "departing_residential":
        start = parse_clock_minutes((rules.get("departure_window") or ["06:00", "08:00"])[0])
        end = parse_clock_minutes((rules.get("departure_window") or ["06:00", "08:00"])[1])
        span = max(1, end - start)
        spread = max(1, int(rules.get("personal_departure_spread_minutes", 88) or 88))
        personal_delay = int(_stable_fraction(f"dep:{resident_sequence}:{slot}") * spread)
        p = max(0.0, min(1.0, (int(clock_minutes) - start - personal_delay) / float(max(1, span - spread * 0.35))))
        if p < 0.56:
            local = p / 0.56
            grid = _lerp_path(routes.get("outbound_residential", []), local, lane=lane, lane_count=lane_count)
            return {"commute_stage": "residential_departure", "town_id": home_town, "grid": grid, "progress": p, "direction": "outbound", "label": labels.get("residential_departure", "departing Residential")}
        elif p < 0.76:
            local = (p - 0.56) / 0.20
            grid = _lerp_path(routes.get("outbound_residential", []), 1.0, lane=lane, lane_count=lane_count)
            return {"commute_stage": "interdistrict_outbound", "town_id": home_town, "grid": grid, "progress": p, "direction": "outbound", "label": labels.get("interdistrict_outbound", "crossing to Simulation")}
        else:
            local = (p - 0.76) / 0.24
            grid = _lerp_path(routes.get("outbound_simulation", []), local, lane=lane, lane_count=lane_count)
            return {"commute_stage": "simulation_arrival", "town_id": dest_town, "grid": grid, "progress": p, "direction": "outbound", "label": labels.get("simulation_arrival", "arriving at Simulation")}
    # Return home phase.
    start = parse_clock_minutes((rules.get("return_window") or ["20:00", "21:00"])[0])
    end = parse_clock_minutes((rules.get("return_window") or ["20:00", "21:00"])[1])
    span = max(1, end - start)
    spread = max(1, int(rules.get("personal_return_spread_minutes", 42) or 42))
    personal_delay = int(_stable_fraction(f"ret:{resident_sequence}:{slot}") * spread)
    p = max(0.0, min(1.0, (int(clock_minutes) - start - personal_delay) / float(max(1, span - spread * 0.30))))
    if p < 0.30:
        grid = _lerp_path(routes.get("return_simulation", []), p / 0.30, lane=lane, lane_count=lane_count)
        return {"commute_stage": "simulation_departure", "town_id": dest_town, "grid": grid, "progress": p, "direction": "return", "label": labels.get("simulation_departure", "leaving Simulation")}
    elif p < 0.52:
        grid = _lerp_path(routes.get("return_simulation", []), 1.0, lane=lane, lane_count=lane_count)
        return {"commute_stage": "interdistrict_return", "town_id": dest_town, "grid": grid, "progress": p, "direction": "return", "label": labels.get("interdistrict_return", "crossing back to Residential")}
    else:
        grid = _lerp_path(routes.get("return_residential", []), (p - 0.52) / 0.48, lane=lane, lane_count=lane_count)
        return {"commute_stage": "residential_return", "town_id": home_town, "grid": grid, "progress": p, "direction": "return", "label": labels.get("residential_return", "returning to home garrison")}


def validate_commute_flow(holoutopia_root: Path | str | None = None) -> list[str]:
    data = load_commute_flow(holoutopia_root)
    errors: list[str] = []
    if data.get("home_town_id") != "residential_alpha":
        errors.append("home_town_id must remain residential_alpha")
    if data.get("destination_town_id") != "central_core_civic_ring":
        errors.append("destination_town_id must remain central_core_civic_ring")
    routes = data.get("route_targets") if isinstance(data.get("route_targets"), dict) else {}
    for key in ("outbound_residential", "outbound_simulation", "return_simulation", "return_residential"):
        values = routes.get(key)
        if not isinstance(values, list) or len(values) < 4:
            errors.append(f"route {key} needs at least 4 points")
    dep_stages = {commute_profile_for_visible_slot(holoutopia_root, phase="departing_residential", clock_minutes=7*60+15, slot=i, resident_sequence=100+i).get("commute_stage") for i in range(20)}
    ret_stages = {commute_profile_for_visible_slot(holoutopia_root, phase="returning_to_residential", clock_minutes=20*60+35, slot=i, resident_sequence=200+i).get("commute_stage") for i in range(20)}
    if len(dep_stages) < 2:
        errors.append("departure commute should distribute across at least 2 visual stages")
    if len(ret_stages) < 2:
        errors.append("return commute should distribute across at least 2 visual stages")
    return errors
