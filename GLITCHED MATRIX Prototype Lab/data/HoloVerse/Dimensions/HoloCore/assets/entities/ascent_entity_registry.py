"""Registry for altitude-strata HoloCore encounter entities."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Type

from assets.entities.holo_dragon_whale import (
    DRAGON_WHALE_BEHAVIOR,
    DRAGON_WHALE_CONTACT_RADIUS,
    DRAGON_WHALE_MIN_ALTITUDE,
    DRAGON_WHALE_UPDATE_INTERVAL,
    HoloDragonWhaleMob,
    stable_dragon_whale_seed,
)
from assets.entities.holo_storm_serpent import (
    STORM_SERPENT_BEHAVIOR,
    STORM_SERPENT_CONTACT_RADIUS,
    STORM_SERPENT_MIN_ALTITUDE,
    STORM_SERPENT_UPDATE_INTERVAL,
    HoloStormSerpentMob,
    stable_storm_serpent_seed,
)


@dataclass(frozen=True)
class AscentEntitySpec:
    entity_id: str
    mob_class: Type
    seed_func: Callable[[tuple[int, int], int], int]
    seed_salt: int
    min_altitude: float
    altitude_spacing: float
    spawn_chance: float
    scale_min: float
    scale_max: float
    base_distance: float
    vertical_offset_min: float
    vertical_offset_max: float
    contact_radius: float
    update_interval: float
    behavior_id: str
    habitat_note: str


ASCENT_ENTITY_SPECS: tuple[AscentEntitySpec, ...] = (
    AscentEntitySpec(
        entity_id="holo_storm_serpent",
        mob_class=HoloStormSerpentMob,
        seed_func=stable_storm_serpent_seed,
        seed_salt=0x57E4FEA7,
        min_altitude=STORM_SERPENT_MIN_ALTITUDE,
        altitude_spacing=2600.0,
        spawn_chance=0.21,
        scale_min=5.6,
        scale_max=8.4,
        base_distance=880.0,
        vertical_offset_min=-260.0,
        vertical_offset_max=420.0,
        contact_radius=STORM_SERPENT_CONTACT_RADIUS,
        update_interval=STORM_SERPENT_UPDATE_INTERVAL,
        behavior_id=STORM_SERPENT_BEHAVIOR,
        habitat_note="rare cathedral-scale storm serpent; farther apart, higher vertical offsets, warning flash before vertical dash",
    ),
    AscentEntitySpec(
        entity_id="holo_dragon_whale",
        mob_class=HoloDragonWhaleMob,
        seed_func=stable_dragon_whale_seed,
        seed_salt=0xD6A90A1E,
        min_altitude=DRAGON_WHALE_MIN_ALTITUDE,
        altitude_spacing=3800.0,
        spawn_chance=0.14,
        scale_min=7.8,
        scale_max=12.5,
        base_distance=1280.0,
        vertical_offset_min=-360.0,
        vertical_offset_max=620.0,
        contact_radius=DRAGON_WHALE_CONTACT_RADIUS,
        update_interval=DRAGON_WHALE_UPDATE_INTERVAL,
        behavior_id=DRAGON_WHALE_BEHAVIOR,
        habitat_note="colossal Leviathan Expanse dragon whale with shadow escorts, huge spacing, slow sonar breach",
    ),
)
