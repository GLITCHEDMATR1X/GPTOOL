"""Registry for HoloCore biome-specific generated entities.

These are deliberately chunk-owned and update through the same outer-world
lifecycle as mermaids, jellyfish, and octopus mobs. They are not routed
HoloVerse dimensions and do not add tasks of their own.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Type

from assets.entities.holo_archive_turtle import (
    ARCHIVE_TURTLE_BEHAVIOR,
    ARCHIVE_TURTLE_HEIGHT_OFFSET,
    ARCHIVE_TURTLE_HEIGHT_TIERS,
    ARCHIVE_TURTLE_HEIGHT_VARIANCE,
    ARCHIVE_TURTLE_MIN_DISTANCE_FROM_HUB,
    ARCHIVE_TURTLE_SPAWN_CHANCE,
    ARCHIVE_TURTLE_UPDATE_INTERVAL,
    HoloArchiveTurtleMob,
    stable_archive_turtle_seed,
)
from assets.entities.holo_glass_fish import (
    GLASS_FISH_BEHAVIOR,
    GLASS_FISH_HEIGHT_OFFSET,
    GLASS_FISH_HEIGHT_TIERS,
    GLASS_FISH_HEIGHT_VARIANCE,
    GLASS_FISH_MIN_DISTANCE_FROM_HUB,
    GLASS_FISH_SPAWN_CHANCE,
    GLASS_FISH_UPDATE_INTERVAL,
    HoloGlassFishSwarm,
    stable_glass_fish_seed,
)
from assets.entities.holo_kelp_ray import (
    KELP_RAY_BEHAVIOR,
    KELP_RAY_HEIGHT_OFFSET,
    KELP_RAY_HEIGHT_TIERS,
    KELP_RAY_HEIGHT_VARIANCE,
    KELP_RAY_MIN_DISTANCE_FROM_HUB,
    KELP_RAY_SPAWN_CHANCE,
    KELP_RAY_UPDATE_INTERVAL,
    HoloKelpRayMob,
    stable_kelp_ray_seed,
)
from assets.entities.holo_storm_eel import (
    STORM_EEL_BEHAVIOR,
    STORM_EEL_HEIGHT_OFFSET,
    STORM_EEL_HEIGHT_TIERS,
    STORM_EEL_HEIGHT_VARIANCE,
    STORM_EEL_MIN_DISTANCE_FROM_HUB,
    STORM_EEL_SPAWN_CHANCE,
    STORM_EEL_UPDATE_INTERVAL,
    HoloStormEelMob,
    stable_storm_eel_seed,
)


@dataclass(frozen=True)
class BiomeEntitySpec:
    biome_folder: str
    entity_id: str
    mob_class: Type
    seed_func: Callable[[tuple[int, int], int], int]
    spawn_chance: float
    height_offset: float
    height_variance: float
    min_distance_from_hub: float
    update_interval: float
    scale_min: float
    scale_max: float
    seed_salt: int
    spacing_chunks: int
    height_tiers: tuple[float, ...]
    behavior_id: str
    habitat_note: str


BIOME_ENTITY_SPECS: dict[str, BiomeEntitySpec] = {
    "biome4": BiomeEntitySpec(
        biome_folder="biome4",
        entity_id="holo_kelp_ray",
        mob_class=HoloKelpRayMob,
        seed_func=stable_kelp_ray_seed,
        spawn_chance=KELP_RAY_SPAWN_CHANCE,
        height_offset=KELP_RAY_HEIGHT_OFFSET,
        height_variance=KELP_RAY_HEIGHT_VARIANCE,
        min_distance_from_hub=KELP_RAY_MIN_DISTANCE_FROM_HUB,
        update_interval=KELP_RAY_UPDATE_INTERVAL,
        scale_min=1.9,
        scale_max=2.8,
        seed_salt=0x4B315244,
        spacing_chunks=4,
        height_tiers=tuple(float(v) for v in KELP_RAY_HEIGHT_TIERS),
        behavior_id=KELP_RAY_BEHAVIOR,
        habitat_note="wide-spaced canopy gliders above the Abyssal Kelp Forest",
    ),
    "biome5": BiomeEntitySpec(
        biome_folder="biome5",
        entity_id="holo_glass_fish_swarm",
        mob_class=HoloGlassFishSwarm,
        seed_func=stable_glass_fish_seed,
        spawn_chance=GLASS_FISH_SPAWN_CHANCE,
        height_offset=GLASS_FISH_HEIGHT_OFFSET,
        height_variance=GLASS_FISH_HEIGHT_VARIANCE,
        min_distance_from_hub=GLASS_FISH_MIN_DISTANCE_FROM_HUB,
        update_interval=GLASS_FISH_UPDATE_INTERVAL,
        scale_min=1.6,
        scale_max=2.4,
        seed_salt=0x61455F19,
        spacing_chunks=3,
        height_tiers=tuple(float(v) for v in GLASS_FISH_HEIGHT_TIERS),
        behavior_id=GLASS_FISH_BEHAVIOR,
        habitat_note="scattered mirror shoals that flash, fan outward, and reform",
    ),
    "biome6": BiomeEntitySpec(
        biome_folder="biome6",
        entity_id="holo_archive_turtle",
        mob_class=HoloArchiveTurtleMob,
        seed_func=stable_archive_turtle_seed,
        spawn_chance=ARCHIVE_TURTLE_SPAWN_CHANCE,
        height_offset=ARCHIVE_TURTLE_HEIGHT_OFFSET,
        height_variance=ARCHIVE_TURTLE_HEIGHT_VARIANCE,
        min_distance_from_hub=ARCHIVE_TURTLE_MIN_DISTANCE_FROM_HUB,
        update_interval=ARCHIVE_TURTLE_UPDATE_INTERVAL,
        scale_min=1.9,
        scale_max=2.9,
        seed_salt=0xA2C417E6,
        spacing_chunks=5,
        height_tiers=tuple(float(v) for v in ARCHIVE_TURTLE_HEIGHT_TIERS),
        behavior_id=ARCHIVE_TURTLE_BEHAVIOR,
        habitat_note="rare low-mid archive sentinels that pause to scan ruins",
    ),
    "biome7": BiomeEntitySpec(
        biome_folder="biome7",
        entity_id="holo_storm_eel",
        mob_class=HoloStormEelMob,
        seed_func=stable_storm_eel_seed,
        spawn_chance=STORM_EEL_SPAWN_CHANCE,
        height_offset=STORM_EEL_HEIGHT_OFFSET,
        height_variance=STORM_EEL_HEIGHT_VARIANCE,
        min_distance_from_hub=STORM_EEL_MIN_DISTANCE_FROM_HUB,
        update_interval=STORM_EEL_UPDATE_INTERVAL,
        scale_min=2.1,
        scale_max=3.2,
        seed_salt=0x5702E17,
        spacing_chunks=4,
        height_tiers=tuple(float(v) for v in STORM_EEL_HEIGHT_TIERS),
        behavior_id=STORM_EEL_BEHAVIOR,
        habitat_note="high storm-trench hunters with charged vertical dashes",
    ),
}
