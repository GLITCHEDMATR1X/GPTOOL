"""Distance-driven HoloCore ocean-space field.

This Panda-free module gives HoloCore its second exploration axis: horizontal
travel away from the safe anchor.  Vertical strata still decide the altitude
layer; ocean-space decides how the black-water world mutates as the vessel
ventures outward into a sea as vast as outer space.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

OCEAN_SPACE_DISTANCE_OFFSET = 0.0
OCEAN_SPACE_BLEND_WIDTH = 5200.0
OCEAN_SPACE_VISUAL_SMOOTH_SECONDS = 24.0
OCEAN_SPACE_UPDATE_INTERVAL = 0.25


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def smoothstep(value: float) -> float:
    value = _clamp01(value)
    return value * value * (3.0 - 2.0 * value)


@dataclass(frozen=True)
class OceanSpaceBandDefinition:
    band_id: str
    name: str
    distance_min: float
    tint: tuple[float, float, float]
    background: tuple[float, float, float]
    signal_note: str
    entity_note: str


@dataclass(frozen=True)
class OceanSpaceState:
    distance: float
    band_index: int
    band_id: str
    band_name: str
    next_band_id: str
    next_band_name: str
    band_progress: float
    blend_alpha: float
    intensity: float
    tint: tuple[float, float, float]
    background: tuple[float, float, float]
    signal_spacing: float
    signal_rarity_multiplier: float
    entity_scale_multiplier: float
    entity_distance_multiplier: float
    entity_rarity_multiplier: float


OCEAN_SPACE_BANDS: tuple[OceanSpaceBandDefinition, ...] = (
    OceanSpaceBandDefinition(
        "safe_core_sea",
        "Safe Core Sea",
        0.0,
        (0.62, 0.92, 1.00),
        (0.000, 0.006, 0.012),
        "near-anchor calm sonar glows",
        "small familiar wildlife and safe low-value signals",
    ),
    OceanSpaceBandDefinition(
        "outer_reef_drift",
        "Outer Reef Drift",
        8000.0,
        (0.36, 1.00, 0.80),
        (0.000, 0.010, 0.010),
        "faint drifting reef pulses and distant soft bloom clusters",
        "larger rays, turtles, and occasional strange silhouettes",
    ),
    OceanSpaceBandDefinition(
        "archive_expanse",
        "Archive Expanse",
        20000.0,
        (0.86, 0.70, 1.00),
        (0.005, 0.003, 0.018),
        "ancient relay sparks and broken memory-shell signals",
        "archive turtles, glass fish, rare vessel echoes",
    ),
    OceanSpaceBandDefinition(
        "void_current_sea",
        "Void Current Sea",
        45000.0,
        (0.44, 0.78, 1.00),
        (0.002, 0.002, 0.022),
        "deep current arcs and sparse navigation anomalies",
        "storm eels, high-risk current hunters, far leviathan traces",
    ),
    OceanSpaceBandDefinition(
        "deep_ocean_space",
        "Deep Ocean-Space",
        90000.0,
        (1.00, 0.58, 0.92),
        (0.010, 0.001, 0.014),
        "rare star-sea blooms and leviathan migration markers",
        "elder whale shadows and serpent-scale silhouettes far apart",
    ),
)


def _lerp_tuple(a: tuple[float, float, float], b: tuple[float, float, float], t: float) -> tuple[float, float, float]:
    t = _clamp01(t)
    return (
        float(a[0]) + (float(b[0]) - float(a[0])) * t,
        float(a[1]) + (float(b[1]) - float(a[1])) * t,
        float(a[2]) + (float(b[2]) - float(a[2])) * t,
    )


def _band_index_for_distance(distance: float) -> int:
    distance = max(0.0, float(distance or 0.0) - float(OCEAN_SPACE_DISTANCE_OFFSET))
    index = 0
    for idx, band in enumerate(OCEAN_SPACE_BANDS):
        if distance >= float(band.distance_min):
            index = idx
    return index


def ocean_space_state(distance: float, altitude: float = 0.0) -> OceanSpaceState:
    """Return the horizontal ocean-space state for a distance from safe anchor.

    The final band is infinite.  It does not hard-reset; intensity keeps rising
    slowly so very far travel can continue to make creatures rarer/larger and
    signals farther apart without requiring new authored zones.
    """
    distance = max(0.0, float(distance or 0.0))
    altitude = max(0.0, float(altitude or 0.0))
    bands = tuple(OCEAN_SPACE_BANDS)
    index = _band_index_for_distance(distance)
    band = bands[index]
    next_index = min(index + 1, len(bands) - 1)
    next_band = bands[next_index]
    start = float(band.distance_min)
    end = float(next_band.distance_min) if next_index != index else max(start + 90000.0, distance + 1.0)
    span = max(1.0, end - start)
    local = max(0.0, distance - start)
    progress = _clamp01(local / span)
    blend_width = max(1.0, min(float(OCEAN_SPACE_BLEND_WIDTH), span - 1.0))
    blend_start = max(0.0, span - blend_width)
    blend = smoothstep((local - blend_start) / blend_width) if next_index != index else 0.0
    far_bonus = max(0.0, (distance - float(bands[-1].distance_min)) / 90000.0)
    altitude_bonus = max(0.0, altitude / 22000.0) * 0.25
    intensity = float(index) / max(1.0, float(len(bands) - 1)) + min(3.0, far_bonus) * 0.45 + altitude_bonus
    # Signals get rarer/farther out; this is why the ocean-space stays vast.
    signal_spacing = 1800.0 + index * 1250.0 + min(9000.0, far_bonus * 3000.0)
    return OceanSpaceState(
        distance=distance,
        band_index=index,
        band_id=band.band_id,
        band_name=band.name,
        next_band_id=next_band.band_id,
        next_band_name=next_band.name,
        band_progress=progress,
        blend_alpha=blend,
        intensity=float(intensity),
        tint=_lerp_tuple(band.tint, next_band.tint, blend),
        background=_lerp_tuple(band.background, next_band.background, blend),
        signal_spacing=float(signal_spacing),
        signal_rarity_multiplier=1.0 + index * 0.55 + min(4.0, far_bonus * 1.2),
        entity_scale_multiplier=1.0 + index * 0.20 + min(4.0, far_bonus * 0.55) + altitude_bonus * 0.80,
        entity_distance_multiplier=1.0 + index * 0.30 + min(4.8, far_bonus * 0.95),
        entity_rarity_multiplier=1.0 + index * 0.70 + min(6.0, far_bonus * 1.65),
    )


def ocean_space_state_for_position(x: float, y: float, altitude: float = 0.0) -> OceanSpaceState:
    return ocean_space_state(math.hypot(float(x or 0.0), float(y or 0.0)), altitude=altitude)


def ocean_space_debug_samples() -> list[dict[str, object]]:
    samples: list[dict[str, object]] = []
    for distance in (0.0, 4200.0, 8000.0, 15500.0, 20000.0, 44500.0, 45000.0, 90000.0, 145000.0):
        state = ocean_space_state(distance, altitude=16420.0 if distance >= 90000.0 else 0.0)
        samples.append({
            "distance": round(float(distance), 3),
            "band_id": state.band_id,
            "band_name": state.band_name,
            "next_band_id": state.next_band_id,
            "blend_alpha": round(float(state.blend_alpha), 4),
            "intensity": round(float(state.intensity), 4),
            "signal_spacing": round(float(state.signal_spacing), 3),
            "entity_scale_multiplier": round(float(state.entity_scale_multiplier), 4),
            "entity_distance_multiplier": round(float(state.entity_distance_multiplier), 4),
            "entity_rarity_multiplier": round(float(state.entity_rarity_multiplier), 4),
        })
    return samples
