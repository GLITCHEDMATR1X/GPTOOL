"""Altitude-driven HoloCore volumetric strata.

This module is intentionally Panda-free so validators and adapters can inspect
vertical layer math without launching a renderer.  HoloCore still keeps its
horizontal biome bands; these strata add a slow, infinite, altitude-based tint
and encounter progression for the sea vessel.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

VERTICAL_STRATA_START_ALTITUDE = 100.0
VERTICAL_STRATA_LAYER_HEIGHT = 3200.0
VERTICAL_STRATA_BLEND_HEIGHT = 1400.0
VERTICAL_STRATA_VISUAL_SMOOTH_SECONDS = 18.0
VERTICAL_STRATA_UPDATE_INTERVAL = 0.20
ASCENT_ENCOUNTER_UPDATE_INTERVAL = 0.25


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def smoothstep(value: float) -> float:
    value = _clamp01(value)
    return value * value * (3.0 - 2.0 * value)


@dataclass(frozen=True)
class VerticalStratumDefinition:
    layer_id: str
    name: str
    altitude_min: float
    tint: tuple[float, float, float]
    background: tuple[float, float, float]
    particle_note: str
    encounter_note: str


@dataclass(frozen=True)
class VerticalStratumState:
    altitude: float
    cycle: int
    layer_index: int
    layer_id: str
    layer_name: str
    next_layer_id: str
    next_layer_name: str
    layer_progress: float
    blend_alpha: float
    intensity: float
    tint: tuple[float, float, float]
    background: tuple[float, float, float]
    creature_scale_multiplier: float
    creature_distance_multiplier: float
    creature_rarity_multiplier: float


VERTICAL_STRATA: tuple[VerticalStratumDefinition, ...] = (
    VerticalStratumDefinition(
        "safe_reef_layer",
        "Safe Reef Layer",
        VERTICAL_STRATA_START_ALTITUDE,
        (0.55, 0.86, 1.00),
        (0.0000, 0.0060, 0.0120),
        "fine blue plankton and calm sonar haze",
        "small familiar wildlife only",
    ),
    VerticalStratumDefinition(
        "kelp_canopy_layer",
        "Kelp Canopy Layer",
        VERTICAL_STRATA_START_ALTITUDE + VERTICAL_STRATA_LAYER_HEIGHT * 1,
        (0.34, 1.00, 0.72),
        (0.0000, 0.0100, 0.0090),
        "long green-blue vertical drift strands",
        "rays and larger canopy grazers begin appearing",
    ),
    VerticalStratumDefinition(
        "glass_current_layer",
        "Glass Current Layer",
        VERTICAL_STRATA_START_ALTITUDE + VERTICAL_STRATA_LAYER_HEIGHT * 2,
        (0.72, 0.96, 1.00),
        (0.0040, 0.0060, 0.0160),
        "mirror shimmer and pale refraction currents",
        "rare glass fish and prism silhouettes",
    ),
    VerticalStratumDefinition(
        "archive_drift_layer",
        "Archive Drift Layer",
        VERTICAL_STRATA_START_ALTITUDE + VERTICAL_STRATA_LAYER_HEIGHT * 3,
        (0.80, 0.62, 1.00),
        (0.0060, 0.0025, 0.0170),
        "purple archive dust and distant signal glyphs",
        "ancient turtles, data shells, first leviathan shadows",
    ),
    VerticalStratumDefinition(
        "storm_abyss_layer",
        "Storm Abyss Layer",
        VERTICAL_STRATA_START_ALTITUDE + VERTICAL_STRATA_LAYER_HEIGHT * 4,
        (0.42, 0.78, 1.00),
        (0.0020, 0.0040, 0.0200),
        "electric fog, broken current rings, sparse lightning",
        "storm serpents patrol far apart",
    ),
    VerticalStratumDefinition(
        "leviathan_expanse",
        "Leviathan Expanse",
        VERTICAL_STRATA_START_ALTITUDE + VERTICAL_STRATA_LAYER_HEIGHT * 5,
        (1.00, 0.58, 0.92),
        (0.0100, 0.0015, 0.0140),
        "open black-water glow with enormous distant bodies",
        "dragon whales and elder serpents, rare and dangerous",
    ),
)


def _lerp_tuple(a: tuple[float, float, float], b: tuple[float, float, float], t: float) -> tuple[float, float, float]:
    t = _clamp01(t)
    return (
        float(a[0]) + (float(b[0]) - float(a[0])) * t,
        float(a[1]) + (float(b[1]) - float(a[1])) * t,
        float(a[2]) + (float(b[2]) - float(a[2])) * t,
    )


def vertical_stratum_state(altitude: float) -> VerticalStratumState:
    """Return the infinite vertical layer state for a vessel altitude.

    Layers repeat forever, but intensity keeps climbing.  Blend starts only in
    the upper blend-height of each layer, keeping transitions slow and gradual.
    """
    altitude = max(0.0, float(altitude or 0.0))
    ascent_altitude = max(0.0, altitude - float(VERTICAL_STRATA_START_ALTITUDE))
    layer_count = max(1, len(VERTICAL_STRATA))
    layer_height = max(1.0, float(VERTICAL_STRATA_LAYER_HEIGHT))
    blend_height = max(1.0, min(float(VERTICAL_STRATA_BLEND_HEIGHT), layer_height - 1.0))
    absolute_layer = int(math.floor(ascent_altitude / layer_height))
    cycle = absolute_layer // layer_count
    layer_index = absolute_layer % layer_count
    next_index = (layer_index + 1) % layer_count
    local_altitude = ascent_altitude - absolute_layer * layer_height
    progress = _clamp01(local_altitude / layer_height)
    blend_start = max(0.0, layer_height - blend_height)
    raw_blend = (local_altitude - blend_start) / blend_height
    blend = smoothstep(raw_blend)
    layer = VERTICAL_STRATA[layer_index]
    next_layer = VERTICAL_STRATA[next_index]
    intensity = max(0.0, absolute_layer / max(1.0, float(layer_count)))
    return VerticalStratumState(
        altitude=altitude,
        cycle=cycle,
        layer_index=layer_index,
        layer_id=layer.layer_id,
        layer_name=layer.name,
        next_layer_id=next_layer.layer_id,
        next_layer_name=next_layer.name,
        layer_progress=progress,
        blend_alpha=blend,
        intensity=float(intensity),
        tint=_lerp_tuple(layer.tint, next_layer.tint, blend),
        background=_lerp_tuple(layer.background, next_layer.background, blend),
        creature_scale_multiplier=1.0 + min(6.0, intensity * 0.72 + absolute_layer * 0.10),
        creature_distance_multiplier=1.0 + min(5.5, intensity * 0.55 + absolute_layer * 0.075),
        creature_rarity_multiplier=1.0 + min(8.0, intensity * 0.85 + absolute_layer * 0.16),
    )


def ascent_debug_samples() -> list[dict[str, object]]:
    """Small deterministic sample table for validators and tuning."""
    samples: list[dict[str, object]] = []
    sample_points = (
        0,
        VERTICAL_STRATA_START_ALTITUDE - 1,
        VERTICAL_STRATA_START_ALTITUDE,
        VERTICAL_STRATA_START_ALTITUDE + VERTICAL_STRATA_LAYER_HEIGHT * 0.50,
        VERTICAL_STRATA_START_ALTITUDE + VERTICAL_STRATA_LAYER_HEIGHT - 20,
        VERTICAL_STRATA_START_ALTITUDE + VERTICAL_STRATA_LAYER_HEIGHT + 2,
        VERTICAL_STRATA_START_ALTITUDE + VERTICAL_STRATA_LAYER_HEIGHT * 2.5,
        VERTICAL_STRATA_START_ALTITUDE + VERTICAL_STRATA_LAYER_HEIGHT * 5.1,
        VERTICAL_STRATA_START_ALTITUDE + VERTICAL_STRATA_LAYER_HEIGHT * 9.0,
    )
    for altitude in sample_points:
        state = vertical_stratum_state(float(altitude))
        samples.append({
            "altitude": float(altitude),
            "layer_id": state.layer_id,
            "layer_name": state.layer_name,
            "next_layer_id": state.next_layer_id,
            "blend_alpha": round(float(state.blend_alpha), 4),
            "intensity": round(float(state.intensity), 4),
            "creature_scale_multiplier": round(float(state.creature_scale_multiplier), 4),
            "creature_distance_multiplier": round(float(state.creature_distance_multiplier), 4),
            "creature_rarity_multiplier": round(float(state.creature_rarity_multiplier), 4),
        })
    return samples
