import json
import math
import random
import shutil
import sys
import traceback
from array import array
from tkinter import Tk
from tkinter import filedialog, simpledialog
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import pygame

ASSET_DIR = Path("assets")
GENERATED_DIR = ASSET_DIR / "generated"
REPLACEMENT_DIR = ASSET_DIR / "replacements"
BIOME_ASSET_DIR = ASSET_DIR / "biomes"
CRASH_DIR = Path("crash_reports")
SAVE_DIR = Path("saves")
CONFIG_PATH = SAVE_DIR / "config.json"

BASE_TILE_TYPES = [
    "water",
    "dirt",
    "topsoil",
    "subsoil",
    "grass",
    "stone",
    "stone_deep",
    "stone_dark",
    "understone",
    "obsidian",
    "ashen",
    "cavern",
    "mineral",
    "gem",
    "hellstone",
    "hell_cave",
    "magma",
    "lava",
    "snow",
    "sand",
    "clay",
    "mud",
    "swamp",
    "ice",
    "tundra",
    "ruins",
]
OBJECT_TILE_TYPES = [
    "rock",
    "tree",
    "bush",
    "flower",
    "plant",
    "tall_grass",
    "grass_patch",
    "reed",
    "pine",
    "palm",
    "cactus",
    "oak",
    "spruce",
    "willow",
    "baobab",
    "mangrove",
    "acacia",
    "cedar",
    "hell_tree",
    "moon_pillar",
    "mesa_spire",
    "jungle_tree",
    "pyramid_obelisk",
    "canyon_pine",
    "ghost_tree",
    "toxic_bloom",
    "crater_spire",
    "candy_tree",
]
TREE_TYPES = {
    "tree",
    "pine",
    "palm",
    "cactus",
    "oak",
    "spruce",
    "willow",
    "baobab",
    "mangrove",
    "acacia",
    "cedar",
    "hell_tree",
    "moon_pillar",
    "mesa_spire",
    "jungle_tree",
    "pyramid_obelisk",
    "canyon_pine",
    "ghost_tree",
    "toxic_bloom",
    "crater_spire",
    "candy_tree",
}
ANIMAL_TILE_TYPES = [
    "horse",
    "dog",
    "cat",
    "cow",
    "rabbit",
    "bird",
    "fish",
    "deer",
    "fox",
    "boar",
    "monkey",
    "bat",
    "lunar_hare",
    "hawk",
    "scarab",
    "eagle",
    "raven",
    "lizard",
    "mole",
    "unicorn",
    "shark",
    "civilian",
    "goat",
    "elephant",
]
MOB_TILE_TYPES = [
    "slime",
    "goblin",
    "alien",
    "bandit",
    "wolf",
    "golem",
    "wisp",
    "serpent",
    "beetle",
    "phantom",
    "demon",
    "android",
    "guardian",
    "stalker",
    "mummy",
    "harpy",
    "specter",
    "mutant",
    "crawler",
    "gummy",
]

LOOT_TABLE = {
    "slime": ["gel", "shard"],
    "goblin": ["coin", "cloth"],
    "alien": ["crystal", "alloy"],
    "bandit": ["coin", "cloth"],
    "wolf": ["cloth"],
    "golem": ["shard", "mineral"],
    "wisp": ["crystal", "shard"],
    "serpent": ["cloth", "shard"],
    "beetle": ["mineral"],
    "phantom": ["crystal"],
    "demon": ["shard", "crystal"],
    "android": ["alloy", "crystal"],
    "guardian": ["mineral", "shard"],
    "stalker": ["cloth", "coin"],
    "mummy": ["cloth", "coin"],
    "harpy": ["coin", "cloth"],
    "specter": ["crystal"],
    "mutant": ["shard", "gel"],
    "crawler": ["mineral", "shard"],
    "gummy": ["gel", "crystal"],
}


WEAPON_RARITIES = ["common", "uncommon", "rare", "epic", "legendary"]
WEAPON_RARITY_WEIGHTS = {
    "common": 62,
    "uncommon": 22,
    "rare": 10,
    "epic": 5,
    "legendary": 1,
}
WEAPON_RARITY_COLORS = {
    "common": (200, 200, 200),
    "uncommon": (120, 220, 140),
    "rare": (120, 170, 255),
    "epic": (210, 120, 255),
    "legendary": (255, 210, 80),
}

WEAPON_ARCHETYPES = [
    # --- Melee (common mob drops) ---
    {"type": "sword", "name": "Sword", "behavior": "melee", "base_damage": 2, "range": 1.55, "cooldown": 0.55},
    {"type": "dagger", "name": "Dagger", "behavior": "melee", "base_damage": 1, "range": 1.25, "cooldown": 0.36},
    {"type": "axe", "name": "Axe", "behavior": "melee", "base_damage": 3, "range": 1.45, "cooldown": 0.70},
    {"type": "hammer", "name": "Hammer", "behavior": "melee", "base_damage": 4, "range": 1.35, "cooldown": 0.88},
    {"type": "spear", "name": "Spear", "behavior": "melee", "base_damage": 2, "range": 2.10, "cooldown": 0.66},
    {"type": "mace", "name": "Mace", "behavior": "melee", "base_damage": 3, "range": 1.40, "cooldown": 0.76},

    # --- Ranged / magic (rare outside aliens; kept for future loot tables) ---
    {"type": "bow", "name": "Bow", "behavior": "shoot", "base_damage": 2, "range": 7.0, "cooldown": 0.45,
     "projectile": {"speed": 9.0, "lifetime": 1.1, "pierce": 0, "homing": False}},
    {"type": "wand", "name": "Wand", "behavior": "shoot", "base_damage": 2, "range": 7.5, "cooldown": 0.50,
     "projectile": {"speed": 8.0, "lifetime": 1.2, "pierce": 0, "homing": False}},
    {"type": "staff", "name": "Staff", "behavior": "burst", "base_damage": 2, "range": 7.0, "cooldown": 0.75,
     "projectile": {"speed": 8.0, "lifetime": 1.0, "pierce": 0, "homing": False, "burst": 3, "spread": 0.28}},
    {"type": "orb_launcher", "name": "Orb Launcher", "behavior": "orb", "base_damage": 3, "range": 6.5, "cooldown": 0.80,
     "projectile": {"speed": 6.2, "lifetime": 1.4, "pierce": 0, "homing": False, "explode_radius": 1.8}},
    {"type": "seeker_wand", "name": "Seeker Wand", "behavior": "shoot", "base_damage": 2, "range": 7.5, "cooldown": 0.65,
     "projectile": {"speed": 7.0, "lifetime": 1.6, "pierce": 0, "homing": True}},
]


WEAPON_PREFIXES = [
    ("Swift", {"cooldown_mult": 0.85}),
    ("Heavy", {"damage_mult": 1.20, "cooldown_mult": 1.10}),
    ("Keen", {"crit_bonus": 0.10}),
    ("Savage", {"damage_mult": 1.15}),
]

WEAPON_SUFFIXES = [
    ("of Embers", {"on_hit": "burn"}),
    ("of Frost", {"on_hit": "slow"}),
    ("of Blasting", {"on_hit": "explode"}),
    ("of Seeking", {"homing": True, "cooldown_mult": 1.05}),
]


MELEE_WEAPON_TYPES = {"sword", "dagger", "axe", "hammer", "spear", "mace"}

ALIEN_WEAPON_ARCHETYPES = [
    {"type": "alien_laser", "name": "Laser Rifle", "behavior": "shoot", "base_damage": 3, "range": 9.5, "cooldown": 0.22,
     "uses_ammo": True, "ammo_max": 60,
     "projectile": {"speed": 22.0, "lifetime": 0.40, "pierce": 0, "homing": False, "color": (80, 240, 255)}},
    {"type": "alien_plasma", "name": "Plasma Caster", "behavior": "shoot", "base_damage": 4, "range": 8.5, "cooldown": 0.35,
     "uses_ammo": True, "ammo_max": 45,
     "projectile": {"speed": 10.0, "lifetime": 1.15, "pierce": 0, "homing": False, "explode_radius": 2.2, "color": (170, 120, 255)}},
    {"type": "alien_seeker", "name": "Seeker Blaster", "behavior": "shoot", "base_damage": 3, "range": 9.0, "cooldown": 0.30,
     "uses_ammo": True, "ammo_max": 40,
     "projectile": {"speed": 9.5, "lifetime": 1.35, "pierce": 0, "homing": True, "color": (120, 255, 160)}},
    {"type": "alien_burst", "name": "Pulse Carbine", "behavior": "burst", "base_damage": 2, "range": 8.0, "cooldown": 0.55,
     "uses_ammo": True, "ammo_max": 70,
     "projectile": {"speed": 12.0, "lifetime": 0.95, "pierce": 0, "homing": False, "burst": 4, "spread": 0.20, "color": (255, 120, 120)}},
]

def _weighted_choice(rng: random.Random, weighted: Dict[str, int]) -> str:
    total = sum(weighted.values())
    roll = rng.uniform(0, total)
    acc = 0.0
    for k, w in weighted.items():
        acc += w
        if roll <= acc:
            return k
    return list(weighted.keys())[0]

def roll_weapon_rarity(rng: random.Random, tier: int) -> str:
    # Higher tier slightly increases odds of rare+.
    weighted = dict(WEAPON_RARITY_WEIGHTS)
    bump = max(0, tier - 1)
    weighted["common"] = max(8, weighted["common"] - bump * 6)
    weighted["uncommon"] = max(6, weighted["uncommon"] - bump * 2)
    weighted["rare"] += bump * 3
    weighted["epic"] += bump * 2
    weighted["legendary"] += bump * 1
    return _weighted_choice(rng, weighted)

def generate_weapon(seed: int, tier: int, biome: str = "", allowed_types: Optional[Set[str]] = None) -> Dict:
    rng = random.Random(seed)
    pool = WEAPON_ARCHETYPES
    if allowed_types:
        pool = [a for a in WEAPON_ARCHETYPES if a.get("type") in allowed_types]
        if not pool:
            pool = WEAPON_ARCHETYPES
    archetype = rng.choice(pool)
    rarity = roll_weapon_rarity(rng, tier)
    rarity_index = WEAPON_RARITIES.index(rarity)
    base = archetype["base_damage"] + tier + rarity_index
    dmg = int(round(base * rng.uniform(0.9, 1.2)))
    cooldown = max(0.18, archetype["cooldown"] * rng.uniform(0.92, 1.08))
    w: Dict = {
        "id": f"w{seed & 0xFFFFFFFF:08x}{rng.randrange(0, 9999):04d}",
        "type": archetype["type"],
        "rarity": rarity,
        "name_base": archetype["name"],
        "behavior": archetype["behavior"],
        "stats": {
            "damage": dmg,
            "range": float(archetype.get("range", 1.5)),
            "cooldown": float(cooldown),
            "crit": 0.05,
        },
        "projectile": None,
        "on_hit": None,
        # Ammo system (used primarily for alien weapons)
        "uses_ammo": bool(archetype.get("uses_ammo", False)),
        "ammo_item": str(archetype.get("ammo_item", "ammo")),
        "ammo_max": int(archetype.get("ammo_max", 0)),
        "ammo": int(archetype.get("ammo_max", 0)),
    }
    if "projectile" in archetype:
        w["projectile"] = dict(archetype["projectile"])
    # Roll 0-3 affixes depending on rarity.
    affix_count = 0
    if rarity in ("uncommon",):
        affix_count = 1
    elif rarity in ("rare",):
        affix_count = 2
    elif rarity in ("epic",):
        affix_count = 3
    elif rarity in ("legendary",):
        affix_count = 4
    prefix = None
    suffix = None
    # Apply at most one prefix and one suffix first (keeps names readable)
    if affix_count >= 1 and rng.random() < 0.85:
        prefix = rng.choice(WEAPON_PREFIXES)
    if affix_count >= 2 and rng.random() < 0.75:
        suffix = rng.choice(WEAPON_SUFFIXES)
    def apply_mod(mod: Dict) -> None:
        if "damage_mult" in mod:
            w["stats"]["damage"] = int(round(w["stats"]["damage"] * mod["damage_mult"]))
        if "cooldown_mult" in mod:
            w["stats"]["cooldown"] = max(0.15, w["stats"]["cooldown"] * mod["cooldown_mult"])
        if "crit_bonus" in mod:
            w["stats"]["crit"] = min(0.5, w["stats"]["crit"] + mod["crit_bonus"])
        if mod.get("homing") and w.get("projectile"):
            w["projectile"]["homing"] = True
        if "on_hit" in mod:
            w["on_hit"] = mod["on_hit"]
    if prefix:
        apply_mod(prefix[1])
    if suffix:
        apply_mod(suffix[1])
    # Additional affixes (beyond prefix/suffix) become subtle stat nudges
    for _ in range(max(0, affix_count - 2)):
        if rng.random() < 0.5:
            w["stats"]["damage"] += 1
        else:
            w["stats"]["cooldown"] = max(0.15, w["stats"]["cooldown"] * 0.95)
    parts = []
    if prefix:
        parts.append(prefix[0])
    parts.append(w["name_base"])
    if suffix:
        parts.append(suffix[0])
    w["name"] = " ".join(parts)
    # Signature for duplicate detection.
    w["sig"] = f"{w.get('type','')}|{w.get('rarity','')}|{w.get('name','')}"
    # Seed ammo for ammo-based weapons.
    if w.get('uses_ammo') and int(w.get('ammo_max', 0)) > 0:
        mx = int(w.get('ammo_max', 0))
        w['ammo'] = max(1, int(round(mx * rng.uniform(0.35, 0.75))))
    else:
        w['ammo'] = int(w.get('ammo', 0))
        w['ammo_max'] = int(w.get('ammo_max', 0))
    return w

def generate_alien_weapon(seed: int, tier: int) -> Dict:
    rng = random.Random(seed)
    archetype = rng.choice(ALIEN_WEAPON_ARCHETYPES)
    # Aliens skew rarer.
    rarity = roll_weapon_rarity(rng, max(3, tier + 2))
    if rarity in ("common", "uncommon"):
        rarity = "rare"
    rarity_index = WEAPON_RARITIES.index(rarity)
    base = archetype["base_damage"] + tier + rarity_index
    dmg = int(round(base * rng.uniform(1.05, 1.35)))
    cooldown = max(0.14, archetype["cooldown"] * rng.uniform(0.85, 1.05))
    w: Dict = {
        "id": f"w{seed & 0xFFFFFFFF:08x}{rng.randrange(0, 9999):04d}",
        "type": archetype["type"],
        "rarity": rarity,
        "name_base": archetype["name"],
        "behavior": archetype["behavior"],
        "stats": {
            "damage": dmg,
            "range": float(archetype.get("range", 8.0)),
            "cooldown": float(cooldown),
            "crit": 0.08,
        },
        "projectile": dict(archetype.get("projectile", {})),
        "on_hit": None,
        "uses_ammo": True,
        "ammo_item": "ammo",
        "ammo_max": int(archetype.get("ammo_max", 40)),
        "ammo": 0,
    }
    w["name"] = f"{w['name_base']}"
    w["sig"] = f"{w.get('type','')}|{w.get('rarity','')}|{w.get('name','')}"
    mx = int(w.get("ammo_max", 40))
    w["ammo"] = max(3, int(round(mx * rng.uniform(0.35, 0.65))))
    # A small chance to add seeking to non-seeker alien guns via suffix logic.
    if rng.random() < 0.18 and w.get("projectile"):
        w["projectile"]["homing"] = True
        w["name"] = f"Seeking {w['name']}"
        w["sig"] = f"{w.get('type','')}|{w.get('rarity','')}|{w.get('name','')}"
    return w


ITEM_COLORS = {
    "ammo": (220, 220, 255),
    "gel": (120, 200, 150),
    "shard": (140, 220, 200),
    "coin": (240, 200, 80),
    "cloth": (180, 140, 120),
    "crystal": (140, 210, 255),
    "alloy": (170, 180, 200),
    "mineral": (120, 150, 170),
    "gem": (170, 120, 210),
}

DEFAULT_COLORS = {
    "water": (50, 110, 200),
    "dirt": (120, 85, 60),
    "topsoil": (110, 78, 58),
    "subsoil": (90, 65, 50),
    "grass": (60, 140, 70),
    "stone": (110, 110, 120),
    "stone_deep": (80, 80, 90),
    "stone_dark": (60, 60, 70),
    "understone": (70, 80, 90),
    "obsidian": (45, 45, 55),
    "ashen": (70, 60, 60),
    "cavern": (35, 35, 45),
    "mineral": (100, 130, 150),
    "gem": (140, 90, 180),
    "hellstone": (140, 50, 40),
    "hell_cave": (50, 20, 20),
    "magma": (190, 70, 40),
    "lava": (220, 80, 30),
    "snow": (230, 230, 240),
    "sand": (210, 190, 120),
    "clay": (170, 120, 90),
    "mud": (90, 70, 50),
    "swamp": (50, 90, 60),
    "ice": (180, 220, 240),
    "tundra": (190, 200, 190),
    "ruins": (130, 130, 140),
    "rock": (90, 90, 95),
    "tree": (60, 120, 70),
    "bush": (40, 110, 60),
    "flower": (200, 80, 140),
    "plant": (80, 160, 90),
    "tall_grass": (70, 150, 80),
    "grass_patch": (90, 170, 90),
    "reed": (80, 130, 90),
    "pine": (40, 90, 60),
    "palm": (80, 140, 90),
    "cactus": (70, 130, 90),
    "oak": (70, 130, 80),
    "spruce": (40, 90, 60),
    "willow": (60, 140, 90),
    "baobab": (150, 120, 80),
    "mangrove": (70, 120, 70),
    "acacia": (160, 130, 70),
    "cedar": (60, 100, 70),
    "hell_tree": (140, 60, 50),
    "moon_pillar": (150, 150, 170),
    "mesa_spire": (170, 120, 80),
    "jungle_tree": (50, 140, 80),
    "pyramid_obelisk": (200, 180, 120),
    "canyon_pine": (90, 110, 80),
    "ghost_tree": (130, 130, 160),
    "toxic_bloom": (90, 180, 120),
    "crater_spire": (120, 120, 130),
    "candy_tree": (200, 140, 180),
    "horse": (140, 110, 80),
    "dog": (170, 140, 110),
    "cat": (190, 170, 140),
    "cow": (120, 100, 90),
    "rabbit": (220, 200, 180),
    "bird": (160, 180, 200),
    "fish": (80, 140, 200),
    "deer": (150, 120, 90),
    "fox": (200, 120, 80),
    "boar": (120, 90, 70),
    "monkey": (140, 110, 80),
    "bat": (100, 100, 120),
    "lunar_hare": (200, 200, 220),
    "hawk": (170, 150, 110),
    "scarab": (90, 120, 140),
    "eagle": (190, 160, 120),
    "raven": (60, 60, 80),
    "lizard": (120, 160, 100),
    "mole": (120, 100, 90),
    "unicorn": (220, 190, 240),
    "shark": (80, 110, 140),
    "civilian": (200, 180, 150),
    "goat": (160, 150, 140),
    "elephant": (120, 120, 130),
    "slime": (80, 200, 120),
    "goblin": (90, 160, 90),
    "alien": (120, 220, 180),
    "bandit": (140, 110, 90),
    "wolf": (150, 150, 160),
    "golem": (120, 120, 140),
    "wisp": (140, 180, 240),
    "serpent": (90, 150, 110),
    "beetle": (120, 80, 60),
    "phantom": (150, 130, 180),
    "demon": (170, 70, 60),
    "android": (130, 160, 190),
    "guardian": (120, 130, 150),
    "stalker": (90, 140, 90),
    "mummy": (190, 170, 120),
    "harpy": (160, 130, 90),
    "specter": (160, 150, 200),
    "mutant": (110, 180, 100),
    "crawler": (120, 90, 80),
    "gummy": (200, 120, 160),
}

TILE_WIDTH = 32
TILE_HEIGHT = 16
CUBE_HEIGHT = 16

MAX_HEIGHT = 100
MIN_HEIGHT = -100
# Keep oceans within a sane range so regeneration can't create absurdly deep
# water that makes the rest of the world look like it's sitting on a pillar.
MIN_WATER_LEVEL = -12
SURFACE_TOPSOIL_DEPTH = -1
SURFACE_SUBSOIL_DEPTH = -3
CAVERN_DEPTH = 20
CAVERN_TOP = -4
CAVERN_BOTTOM = CAVERN_TOP - (CAVERN_DEPTH - 1)
UNDERWORLD_START = CAVERN_BOTTOM - 3
UNDERWORLD_MID = UNDERWORLD_START - 6
UNDERWORLD_DEEP = UNDERWORLD_MID - 6
HELL_START = UNDERWORLD_DEEP - 6
MAGMA_START = HELL_START - 8
LAVA_START = MAGMA_START - 6

FPS = 60

BIOME_PRESETS = [
    {
        "name": "temperate",
        "water_level": -1,
        "river_amp": 2.0,
        "ravine_amp": 1.0,
        "cave_amp": 1.4,
        "canyon_amp": 2.5,
        "mountain_amp": 4.0,
        "holes": 0.03,
        "tree_type": "oak",
        "animal_type": "deer",
        "mob_type": "bandit",
        "water_color": (70, 130, 210),
        "fog_color": (80, 100, 90),
        "surface_tile": "grass",
        "mid_tile": "dirt",
        "high_tile": "stone",
    },
    {
        "name": "grassy",
        "water_level": -1,
        "river_amp": 1.6,
        "ravine_amp": 1.0,
        "cave_amp": 1.2,
        "canyon_amp": 2.2,
        "mountain_amp": 3.6,
        "holes": 0.03,
        "tree_type": "oak",
        "animal_type": "rabbit",
        "extra_animals": ["elephant"],
        "mob_type": "bandit",
        "water_color": (70, 140, 210),
        "fog_color": (90, 110, 100),
        "surface_tile": "grass",
        "mid_tile": "dirt",
        "high_tile": "stone",
    },
    {
        "name": "lush",
        "water_level": 0,
        "river_amp": 2.2,
        "ravine_amp": 0.9,
        "cave_amp": 1.3,
        "canyon_amp": 2.0,
        "mountain_amp": 3.2,
        "holes": 0.03,
        "tree_type": "jungle_tree",
        "animal_type": "deer",
        "mob_type": "slime",
        "water_color": (60, 150, 190),
        "fog_color": (80, 120, 90),
        "surface_tile": "grass",
        "mid_tile": "mud",
        "high_tile": "clay",
    },
    {
        "name": "forests",
        "water_level": -1,
        "river_amp": 1.6,
        "ravine_amp": 1.3,
        "cave_amp": 1.4,
        "canyon_amp": 2.4,
        "mountain_amp": 3.8,
        "holes": 0.03,
        "tree_type": "cedar",
        "animal_type": "deer",
        "mob_type": "wolf",
        "water_color": (70, 130, 200),
        "fog_color": (80, 100, 90),
        "surface_tile": "grass",
        "mid_tile": "dirt",
        "high_tile": "stone",
    },
    {
        "name": "swamps",
        "water_level": 1,
        "river_amp": 2.0,
        "ravine_amp": 0.6,
        "cave_amp": 1.2,
        "canyon_amp": 1.6,
        "mountain_amp": 2.8,
        "holes": 0.02,
        "tree_type": "willow",
        "animal_type": "cow",
        "mob_type": "serpent",
        "water_color": (60, 130, 150),
        "fog_color": (70, 100, 80),
        "surface_tile": "swamp",
        "mid_tile": "mud",
        "high_tile": "clay",
    },
    {
        "name": "jungles",
        "water_level": 0,
        "river_amp": 2.6,
        "ravine_amp": 1.0,
        "cave_amp": 1.4,
        "canyon_amp": 2.2,
        "mountain_amp": 3.4,
        "holes": 0.03,
        "tree_type": "jungle_tree",
        "animal_type": "monkey",
        "mob_type": "stalker",
        "water_color": (60, 150, 190),
        "fog_color": (70, 120, 90),
        "surface_tile": "grass",
        "mid_tile": "mud",
        "high_tile": "clay",
    },
    {
        "name": "tundras",
        "water_level": -2,
        "river_amp": 1.1,
        "ravine_amp": 1.6,
        "cave_amp": 1.3,
        "canyon_amp": 2.4,
        "mountain_amp": 4.4,
        "holes": 0.03,
        "tree_type": "spruce",
        "animal_type": "lunar_hare",
        "mob_type": "phantom",
        "water_color": (70, 150, 210),
        "fog_color": (90, 110, 130),
        "surface_tile": "tundra",
        "mid_tile": "ice",
        "high_tile": "snow",
    },
    {
        "name": "rain_forests",
        "water_level": 0,
        "river_amp": 2.5,
        "ravine_amp": 0.9,
        "cave_amp": 1.3,
        "canyon_amp": 2.0,
        "mountain_amp": 3.2,
        "holes": 0.03,
        "tree_type": "jungle_tree",
        "animal_type": "bird",
        "mob_type": "slime",
        "water_color": (60, 140, 200),
        "fog_color": (70, 120, 90),
        "surface_tile": "grass",
        "mid_tile": "mud",
        "high_tile": "clay",
    },
    {
        "name": "tropical_islands",
        "water_level": 0,
        "river_amp": 1.8,
        "ravine_amp": 0.8,
        "cave_amp": 1.1,
        "canyon_amp": 1.8,
        "mountain_amp": 3.0,
        "holes": 0.02,
        "tree_type": "palm",
        "animal_type": "cat",
        "mob_type": "wisp",
        "water_color": (60, 160, 210),
        "fog_color": (90, 120, 130),
        "surface_tile": "sand",
        "mid_tile": "grass",
        "high_tile": "stone",
    },
    {
        "name": "woods",
        "water_level": -1,
        "river_amp": 1.4,
        "ravine_amp": 1.2,
        "cave_amp": 1.4,
        "canyon_amp": 2.3,
        "mountain_amp": 3.6,
        "holes": 0.03,
        "tree_type": "oak",
        "animal_type": "deer",
        "mob_type": "wolf",
        "water_color": (70, 130, 200),
        "fog_color": (80, 110, 100),
        "surface_tile": "grass",
        "mid_tile": "dirt",
        "high_tile": "stone",
    },
    {
        "name": "drylands",
        "water_level": -5,
        "river_amp": 0.6,
        "ravine_amp": 1.8,
        "cave_amp": 1.2,
        "canyon_amp": 3.0,
        "mountain_amp": 4.5,
        "holes": 0.05,
        "tree_type": "acacia",
        "animal_type": "boar",
        "extra_animals": ["elephant"],
        "mob_type": "golem",
        "water_color": (80, 120, 190),
        "fog_color": (90, 90, 80),
        "surface_tile": "sand",
        "mid_tile": "clay",
        "high_tile": "stone",
    },
    {
        "name": "highlands",
        "water_level": -3,
        "river_amp": 1.2,
        "ravine_amp": 2.4,
        "cave_amp": 1.6,
        "canyon_amp": 3.2,
        "mountain_amp": 5.2,
        "holes": 0.04,
        "tree_type": "cedar",
        "animal_type": "rabbit",
        "mob_type": "wolf",
        "water_color": (60, 120, 200),
        "fog_color": (70, 80, 90),
        "surface_tile": "tundra",
        "mid_tile": "stone",
        "high_tile": "snow",
    },
    {
        "name": "wetlands",
        "water_level": 1,
        "river_amp": 2.6,
        "ravine_amp": 0.6,
        "cave_amp": 1.1,
        "canyon_amp": 1.8,
        "mountain_amp": 3.2,
        "holes": 0.02,
        "tree_type": "mangrove",
        "animal_type": "fish",
        "mob_type": "serpent",
        "water_color": (60, 140, 170),
        "fog_color": (60, 90, 80),
        "surface_tile": "swamp",
        "mid_tile": "mud",
        "high_tile": "clay",
    },
    {
        "name": "arid",
        "water_level": -999,
        "river_amp": 0.0,
        "ravine_amp": 2.0,
        "cave_amp": 1.8,
        "canyon_amp": 3.4,
        "mountain_amp": 4.0,
        "holes": 0.06,
        "tree_type": "cactus",
        "animal_type": "fox",
        "mob_type": "beetle",
        "water_color": (90, 130, 180),
        "fog_color": (100, 90, 70),
        "surface_tile": "sand",
        "mid_tile": "sand",
        "high_tile": "stone",
    },
    {
        "name": "frostbound",
        "water_level": -2,
        "river_amp": 1.0,
        "ravine_amp": 1.6,
        "cave_amp": 1.3,
        "canyon_amp": 2.4,
        "mountain_amp": 4.8,
        "holes": 0.03,
        "tree_type": "pine",
        "animal_type": "wolf",
        "mob_type": "phantom",
        "water_color": (70, 150, 210),
        "fog_color": (80, 100, 120),
        "surface_tile": "snow",
        "mid_tile": "ice",
        "high_tile": "stone",
    },
    {
        "name": "rainforest",
        "water_level": 0,
        "river_amp": 2.4,
        "ravine_amp": 0.9,
        "cave_amp": 1.2,
        "canyon_amp": 2.2,
        "mountain_amp": 3.4,
        "holes": 0.04,
        "tree_type": "tree",
        "animal_type": "bird",
        "mob_type": "slime",
        "water_color": (60, 130, 200),
        "fog_color": (70, 110, 90),
        "surface_tile": "grass",
        "mid_tile": "mud",
        "high_tile": "clay",
    },
    {
        "name": "savanna",
        "water_level": -2,
        "river_amp": 1.4,
        "ravine_amp": 1.1,
        "cave_amp": 1.1,
        "canyon_amp": 2.6,
        "mountain_amp": 3.8,
        "holes": 0.03,
        "tree_type": "baobab",
        "animal_type": "horse",
        "extra_animals": ["elephant"],
        "mob_type": "alien",
        "water_color": (80, 140, 190),
        "fog_color": (90, 100, 80),
        "surface_tile": "grass",
        "mid_tile": "dirt",
        "high_tile": "stone",
    },
    {
        "name": "marsh",
        "water_level": 1,
        "river_amp": 1.9,
        "ravine_amp": 0.7,
        "cave_amp": 1.0,
        "canyon_amp": 1.6,
        "mountain_amp": 3.0,
        "holes": 0.02,
        "tree_type": "willow",
        "animal_type": "cow",
        "mob_type": "goblin",
        "water_color": (70, 120, 160),
        "fog_color": (70, 90, 70),
        "surface_tile": "mud",
        "mid_tile": "swamp",
        "high_tile": "clay",
    },
    {
        "name": "coastal",
        "water_level": -1,
        "river_amp": 1.8,
        "ravine_amp": 1.2,
        "cave_amp": 1.1,
        "canyon_amp": 2.2,
        "mountain_amp": 3.6,
        "holes": 0.03,
        "tree_type": "palm",
        "animal_type": "cat",
        "mob_type": "wisp",
        "water_color": (60, 150, 210),
        "fog_color": (90, 110, 120),
        "surface_tile": "sand",
        "mid_tile": "grass",
        "high_tile": "stone",
    },
    {
        "name": "hellish",
        "clamp_water": True,
        "disable_beach_sand": True,
        "water_level": -999,
        "river_amp": 0.0,
        "ravine_amp": 2.4,
        "cave_amp": 2.1,
        "canyon_amp": 3.8,
        "mountain_amp": 3.6,
        "holes": 0.08,
        "tree_type": "hell_tree",
        "animal_type": "bat",
        "mob_type": "demon",
        "water_color": (160, 70, 60),
        "fog_color": (90, 40, 40),
        "surface_tile": "hellstone",
        "mid_tile": "stone_dark",
        "high_tile": "lava",
    },
    {
        "name": "moonscape",
        "clamp_water": True,
        "disable_beach_sand": True,
        "water_level": -999,
        "river_amp": 0.2,
        "ravine_amp": 1.4,
        "cave_amp": 1.6,
        "canyon_amp": 2.0,
        "mountain_amp": 2.8,
        "holes": 0.05,
        "tree_type": "moon_pillar",
        "animal_type": "lunar_hare",
        "mob_type": "android",
        "water_color": (120, 140, 180),
        "fog_color": (110, 110, 130),
        "surface_tile": "stone",
        "mid_tile": "stone",
        "high_tile": "ice",
    },
    {
        "name": "monument_valleys",
        "water_level": -3,
        "river_amp": 0.8,
        "ravine_amp": 2.6,
        "cave_amp": 1.2,
        "canyon_amp": 4.2,
        "mountain_amp": 4.6,
        "holes": 0.04,
        "tree_type": "mesa_spire",
        "animal_type": "hawk",
        "mob_type": "guardian",
        "water_color": (90, 120, 170),
        "fog_color": (120, 100, 80),
        "surface_tile": "stone",
        "mid_tile": "sand",
        "high_tile": "stone",
    },
    {
        "name": "tropical_jungle",
        "water_level": 0,
        "river_amp": 2.8,
        "ravine_amp": 1.1,
        "cave_amp": 1.4,
        "canyon_amp": 2.0,
        "mountain_amp": 3.4,
        "holes": 0.04,
        "tree_type": "jungle_tree",
        "animal_type": "monkey",
        "mob_type": "stalker",
        "water_color": (60, 150, 190),
        "fog_color": (70, 120, 90),
        "surface_tile": "grass",
        "mid_tile": "mud",
        "high_tile": "clay",
    },
    {
        "name": "pyramid_deserts",
        "water_level": -4,
        "river_amp": 0.4,
        "ravine_amp": 1.8,
        "cave_amp": 1.1,
        "canyon_amp": 2.6,
        "mountain_amp": 3.2,
        "holes": 0.03,
        "tree_type": "pyramid_obelisk",
        "animal_type": "scarab",
        "mob_type": "mummy",
        "water_color": (100, 130, 170),
        "fog_color": (140, 120, 90),
        "surface_tile": "sand",
        "mid_tile": "sand",
        "high_tile": "stone",
    },
    {
        "name": "ghost_towns",
        "water_level": -2,
        "river_amp": 0.6,
        "ravine_amp": 1.3,
        "cave_amp": 1.5,
        "canyon_amp": 2.4,
        "mountain_amp": 2.8,
        "holes": 0.03,
        "tree_type": "ghost_tree",
        "animal_type": "raven",
        "mob_type": "specter",
        "water_color": (80, 120, 160),
        "fog_color": (120, 120, 140),
        "surface_tile": "ruins",
        "mid_tile": "stone",
        "high_tile": "stone",
    },
    {
        "name": "toxic_lands",
        "water_level": -1,
        "river_amp": 1.6,
        "ravine_amp": 1.0,
        "cave_amp": 1.6,
        "canyon_amp": 2.2,
        "mountain_amp": 3.0,
        "holes": 0.05,
        "tree_type": "toxic_bloom",
        "animal_type": "lizard",
        "mob_type": "mutant",
        "water_color": (70, 160, 120),
        "fog_color": (90, 130, 100),
        "surface_tile": "mud",
        "mid_tile": "swamp",
        "high_tile": "stone",
    },
    {
        "name": "candyland",
        "water_level": -1,
        "river_amp": 1.4,
        "ravine_amp": 1.0,
        "cave_amp": 1.2,
        "canyon_amp": 2.0,
        "mountain_amp": 3.0,
        "holes": 0.02,
        "tree_type": "candy_tree",
        "animal_type": "unicorn",
        "mob_type": "gummy",
        "water_color": (120, 150, 220),
        "fog_color": (170, 140, 190),
        "surface_tile": "clay",
        "mid_tile": "sand",
        "high_tile": "snow",
    },
    {
        "name": "island_flats",
        "water_level": -2,
        "river_amp": 1.0,
        "ravine_amp": 0.4,
        "cave_amp": 1.1,
        "canyon_amp": 1.2,
        "mountain_amp": 2.6,
        "holes": 0.02,
        "tree_type": "oak",
        "animal_type": "deer",
        "mob_type": "bandit",
        "water_color": (60, 150, 210),
        "fog_color": (90, 120, 130),
        "surface_tile": "grass",
        "mid_tile": "dirt",
        "high_tile": "stone",
        "landform": "flat",
    },
    {
        "name": "island_mountains",
        "water_level": -2,
        "river_amp": 1.2,
        "ravine_amp": 0.6,
        "cave_amp": 1.4,
        "canyon_amp": 1.4,
        "mountain_amp": 5.0,
        "holes": 0.03,
        "tree_type": "pine",
        "animal_type": "goat",
        "mob_type": "golem",
        "water_color": (60, 140, 210),
        "fog_color": (100, 120, 130),
        "surface_tile": "grass",
        "mid_tile": "stone",
        "high_tile": "snow",
        "landform": "mountain",
    },
    {
        "name": "island_cliffs",
        "water_level": -2,
        "river_amp": 1.0,
        "ravine_amp": 0.4,
        "cave_amp": 1.2,
        "canyon_amp": 1.0,
        "mountain_amp": 3.6,
        "holes": 0.02,
        "tree_type": "cedar",
        "animal_type": "eagle",
        "mob_type": "harpy",
        "water_color": (60, 150, 210),
        "fog_color": (90, 120, 130),
        "surface_tile": "stone",
        "mid_tile": "stone",
        "high_tile": "stone",
        "landform": "cliff",
    },
    {
        "name": "stone_towns",
        "water_level": -2,
        "river_amp": 0.8,
        "ravine_amp": 0.4,
        "cave_amp": 1.1,
        "canyon_amp": 1.0,
        "mountain_amp": 3.0,
        "holes": 0.02,
        "tree_type": "oak",
        "animal_type": "civilian",
        "mob_type": "goblin",
        "water_color": (70, 140, 200),
        "fog_color": (110, 110, 120),
        "surface_tile": "stone",
        "mid_tile": "stone",
        "high_tile": "stone",
        "settlement_density": 0.6,
        "civilian_count": 12,
        "landform": "flat",
    },
    {
        "name": "coastal_cities",
        "water_level": -2,
        "river_amp": 1.2,
        "ravine_amp": 0.6,
        "cave_amp": 1.0,
        "canyon_amp": 1.0,
        "mountain_amp": 3.2,
        "holes": 0.02,
        "tree_type": "palm",
        "animal_type": "civilian",
        "mob_type": "bandit",
        "water_color": (60, 150, 210),
        "fog_color": (100, 120, 140),
        "surface_tile": "sand",
        "mid_tile": "stone",
        "high_tile": "stone",
        "settlement_density": 0.8,
        "civilian_count": 18,
        "landform": "flat",
    },
]


@dataclass
class TileStyle:
    base_color: Tuple[int, int, int]
    brightness: float = 1.0
    contrast: float = 1.0
    tint: Tuple[int, int, int] = (0, 0, 0)
    darkness: float = 0.0
    texture_seed: int = 0

    def apply(self, color: Tuple[int, int, int]) -> Tuple[int, int, int]:
        r, g, b = color
        r = int(r * self.brightness)
        g = int(g * self.brightness)
        b = int(b * self.brightness)
        r = int((r - 128) * self.contrast + 128)
        g = int((g - 128) * self.contrast + 128)
        b = int((b - 128) * self.contrast + 128)
        r = int(r - self.darkness * 255)
        g = int(g - self.darkness * 255)
        b = int(b - self.darkness * 255)
        r = max(0, min(255, r + self.tint[0]))
        g = max(0, min(255, g + self.tint[1]))
        b = max(0, min(255, b + self.tint[2]))
        return r, g, b


@dataclass
class Tile:
    height: int
    tile_type: str
    texture_override: Optional[str] = None
    rotation: int = 0
    flip_x: bool = False
    texture_tint: Tuple[int, int, int] = (255, 255, 255)
    texture_scale: float = 1.0


@dataclass
class Player:
    x: float
    y: float
    height: int
    mode: str = "smooth"
    speed: float = 4.0
    swim_speed: float = 2.5
    acceleration: float = 10.0
    velocity_x: float = 0.0
    velocity_y: float = 0.0
    direction: Tuple[int, int] = (0, 1)
    is_swimming: bool = False
    step_timer: float = 0.0
    step_delay: float = 0.25
    vertical_step_timer: float = 0.0
    vertical_step_delay: float = 0.18
    animation_time: float = 0.0
    health: int = 5
    attack_timer: float = 0.0
    attack_direction: Tuple[int, int] = (0, 1)
    inventory: Dict[str, int] = field(default_factory=dict)
    weapons: List[Dict] = field(default_factory=list)
    equipped_weapon_id: Optional[str] = None
    weapon_bindings: Dict[int, str] = field(default_factory=dict)  # 1-9 hotkeys
    step_sound_timer: float = 0.0


@dataclass
class Mob:
    x: float
    y: float
    height: int
    mob_type: str
    health: int = 3
    attack_cooldown: float = 0.0
    weapon: str = "sword"
    wander_timer: float = 0.0
    direction: Tuple[float, float] = (0.0, 0.0)
    variant_color: Tuple[int, int, int] = (140, 60, 60)
    accent_color: Tuple[int, int, int] = (200, 40, 40)
    animation_time: float = 0.0
    aggression: float = 0.0


@dataclass
class Animal:
    x: float
    y: float
    height: int
    animal_type: str
    hunger: float = 0.0
    wander_timer: float = 0.0
    direction: Tuple[float, float] = (0.0, 0.0)
    animation_time: float = 0.0
    terrain_affinity: Dict[str, float] = field(default_factory=dict)
    sound_timer: float = 0.0


@dataclass
class Projectile:
    x: float
    y: float
    height: int
    vx: float
    vy: float
    damage: int
    lifetime: float
    homing: bool = False
    target: Optional[Mob] = None
    pierce: int = 0
    on_hit: Optional[str] = None
    timer: float = 0.0
    color: Tuple[int, int, int] = (240, 240, 240)

@dataclass
class World:
    width: int
    height: int
    tiles: Dict[Tuple[int, int], Tile] = field(default_factory=dict)

    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height

    def get_tile(self, x: int, y: int) -> Optional[Tile]:
        return self.tiles.get((x, y))

    def set_tile(self, x: int, y: int, tile_type: str, height: int) -> None:
        height = max(MIN_HEIGHT, min(MAX_HEIGHT, height))
        if not self.in_bounds(x, y):
            return
        self.tiles[(x, y)] = Tile(height=height, tile_type=tile_type)

    def clear_tile(self, x: int, y: int) -> None:
        self.tiles.pop((x, y), None)

    def raise_tile(self, x: int, y: int, tile_type: str) -> None:
        tile = self.get_tile(x, y)
        if tile is None:
            self.set_tile(x, y, tile_type, 0)
            return
        if tile.tile_type != tile_type:
            tile.tile_type = tile_type
        tile.height = max(MIN_HEIGHT, min(MAX_HEIGHT, tile.height + 1))

    def lower_tile(self, x: int, y: int) -> None:
        tile = self.get_tile(x, y)
        if tile is None:
            self.set_tile(x, y, "dirt", -1)
            return
        tile.height = max(MIN_HEIGHT, min(MAX_HEIGHT, tile.height - 1))

    def paint_tile(self, x: int, y: int, tile_type: str, bump: bool = True) -> None:
        tile = self.get_tile(x, y)
        if tile is None:
            self.set_tile(x, y, tile_type, 0)
            return
        if bump:
            tile.height = max(MIN_HEIGHT, min(MAX_HEIGHT, tile.height + 1))
        tile.tile_type = tile_type
        tile.texture_override = None
        tile.rotation = 0
        tile.flip_x = False
        tile.texture_tint = (255, 255, 255)
        tile.texture_scale = 1.0

    def to_dict(self) -> Dict:
        return {
            "width": self.width,
            "height": self.height,
            "tiles": [
                {
                    "x": x,
                    "y": y,
                    "height": tile.height,
                    "tile_type": tile.tile_type,
                    "texture_override": tile.texture_override,
                    "rotation": tile.rotation,
                    "flip_x": tile.flip_x,
                    "texture_tint": tile.texture_tint,
                    "texture_scale": tile.texture_scale,
                }
                for (x, y), tile in self.tiles.items()
            ],
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "World":
        world = cls(width=data["width"], height=data["height"])
        for entry in data.get("tiles", []):
            world.set_tile(entry["x"], entry["y"], entry["tile_type"], entry["height"])
            tile = world.get_tile(entry["x"], entry["y"])
            if tile is not None:
                tile.texture_override = entry.get("texture_override")
                tile.rotation = entry.get("rotation", 0)
                tile.flip_x = entry.get("flip_x", False)
                tile.texture_tint = tuple(entry.get("texture_tint", (255, 255, 255)))
                tile.texture_scale = float(entry.get("texture_scale", 1.0))
        return world


@dataclass
class UndoAction:
    positions: List[Tuple[int, int]]
    previous_tiles: List[Optional[Tile]]


class CrashReporter:
    def __init__(self, crash_dir: Path) -> None:
        self.crash_dir = crash_dir
        self.crash_dir.mkdir(parents=True, exist_ok=True)

    def report(self, exc: BaseException) -> None:
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        path = self.crash_dir / f"crash_{timestamp}.txt"
        with path.open("w", encoding="utf-8") as handle:
            handle.write("Isometric World Engine Crash Report\n")
            handle.write(f"Time (UTC): {timestamp}\n")
            handle.write(f"Python: {sys.version}\n")
            handle.write(f"Platform: {sys.platform}\n")
            handle.write(f"Exception: {repr(exc)}\n\n")
            handle.write("Traceback:\n")
            handle.write("".join(traceback.format_tb(exc.__traceback__)))
        print(f"Crash report saved to {path}")


class AudioManager:
    def __init__(self, settings: Dict[str, object]) -> None:
        self.settings = settings
        self.sample_rate = 22050
        self.enabled = bool(settings.get("audio_enabled", True))
        self.volume = float(settings.get("audio_volume", 0.6))
        if self.enabled:
            try:
                pygame.mixer.pre_init(self.sample_rate, -16, 1, 512)
                pygame.mixer.init()
            except pygame.error:
                self.enabled = False
        self.sounds: Dict[str, pygame.mixer.Sound] = {}
        self._build_sound_bank()

    def _build_sound_bank(self) -> None:
        if not self.enabled:
            return
        self.sounds["footstep"] = self._noise_burst(0.12, 0.4, 0.8)
        self.sounds["attack"] = self._noise_burst(0.16, 0.7, 1.0)
        self.sounds["monster"] = self._tone_burst(0.25, 120, 0.5, 0.9)
        self.sounds["animal"] = self._tone_burst(0.22, 240, 0.4, 0.8)
        self.sounds["bird"] = self._tone_burst(0.18, 480, 0.3, 0.7)
        self.sounds["water"] = self._noise_burst(0.4, 0.2, 0.4)

    def _noise_burst(self, duration: float, low: float, high: float) -> pygame.mixer.Sound:
        total_samples = int(self.sample_rate * duration)
        samples = array("h")
        for i in range(total_samples):
            envelope = 1 - (i / total_samples)
            value = int(random.uniform(-1.0, 1.0) * envelope * 32767)
            filtered = int(value * random.uniform(low, high))
            samples.append(max(-32767, min(32767, filtered)))
        return pygame.mixer.Sound(buffer=samples.tobytes())

    def _tone_burst(self, duration: float, freq: float, low: float, high: float) -> pygame.mixer.Sound:
        total_samples = int(self.sample_rate * duration)
        samples = array("h")
        for i in range(total_samples):
            envelope = 1 - (i / total_samples)
            phase = 2 * math.pi * freq * (i / self.sample_rate)
            harmonic = math.sin(phase) * 0.7 + math.sin(phase * 1.8) * 0.3
            value = int(harmonic * envelope * 32767 * random.uniform(low, high))
            samples.append(max(-32767, min(32767, value)))
        return pygame.mixer.Sound(buffer=samples.tobytes())

    def play_at(
        self,
        name: str,
        source: Tuple[float, float],
        listener: Tuple[float, float],
        max_range: float,
        volume_scale: float = 1.0,
    ) -> None:
        if not self.enabled:
            return
        if pygame.mixer.get_init() is None:
            try:
                pygame.mixer.init()
            except pygame.error:
                self.enabled = False
                return
            self._build_sound_bank()
        sound = self.sounds.get(name)
        if sound is None:
            return
        dx = source[0] - listener[0]
        dy = source[1] - listener[1]
        dist = math.hypot(dx, dy)
        if dist > max_range:
            return
        falloff = max(0.0, 1 - dist / max_range)
        volume = max(0.0, min(1.0, self.volume * volume_scale * falloff))
        sound.set_volume(volume)
        sound.play()

@dataclass
class Button:
    label: str
    rect: pygame.Rect
    callback: callable
    toggle: bool = False
    toggled: bool = False

    def draw(self, surface: pygame.Surface, font: pygame.font.Font, offset: Tuple[int, int] = (0, 0)) -> None:
        rect = self.rect.move(-offset[0], -offset[1])
        base_color = (70, 70, 90)
        if self.toggle and self.toggled:
            base_color = (110, 120, 80)
        pygame.draw.rect(surface, base_color, rect, border_radius=4)
        pygame.draw.rect(surface, (20, 20, 30), rect, 2, border_radius=4)
        text_surface = font.render(self.label, True, (230, 230, 230))
        text_rect = text_surface.get_rect(center=rect.center)
        surface.blit(text_surface, text_rect)

    def handle_click(self, pos: Tuple[int, int]) -> bool:
        if self.rect.collidepoint(pos):
            if self.toggle:
                self.toggled = not self.toggled
            self.callback()
            return True
        return False


@dataclass
class PanelSection:
    title: str
    expanded: bool = True
    buttons: List[Button] = field(default_factory=list)
    rect: pygame.Rect = field(default_factory=lambda: pygame.Rect(0, 0, 0, 0))


class AssetManager:
    def __init__(self, styles: Dict[str, TileStyle], tile_types: List[str]) -> None:
        self.styles = styles
        self.tile_types = tile_types
        ASSET_DIR.mkdir(exist_ok=True)
        GENERATED_DIR.mkdir(parents=True, exist_ok=True)
        REPLACEMENT_DIR.mkdir(parents=True, exist_ok=True)
        BIOME_ASSET_DIR.mkdir(parents=True, exist_ok=True)
        self.ensure_biome_dirs([biome["name"] for biome in BIOME_PRESETS])

    @staticmethod
    def biome_key(name: str) -> str:
        return name.strip().lower().replace(" ", "_")

    def get_biome_dir(self, biome_name: str) -> Path:
        return BIOME_ASSET_DIR / self.biome_key(biome_name)

    def get_biome_replacement_dir(self, biome_name: str) -> Path:
        return self.get_biome_dir(biome_name) / "replacements"

    def ensure_biome_dirs(self, biome_names: List[str]) -> None:
        for name in biome_names:
            self.get_biome_replacement_dir(name).mkdir(parents=True, exist_ok=True)

    def generate_tile_texture(self, tile_type: str) -> pygame.Surface:
        style = self.styles[tile_type]
        rng = random.Random(style.texture_seed)
        surface = pygame.Surface((TILE_WIDTH, TILE_HEIGHT), pygame.SRCALPHA)
        base_color = style.apply(style.base_color)
        for y in range(TILE_HEIGHT):
            for x in range(TILE_WIDTH):
                noise = rng.randint(-8, 8)
                color = (
                    max(0, min(255, base_color[0] + noise)),
                    max(0, min(255, base_color[1] + noise)),
                    max(0, min(255, base_color[2] + noise)),
                )
                surface.set_at((x, y), color)
        if tile_type == "ruins":
            crack_color = style.apply(
                (
                    max(0, base_color[0] - 30),
                    max(0, base_color[1] - 30),
                    max(0, base_color[2] - 30),
                )
            )
            for _ in range(6):
                x = rng.randint(2, TILE_WIDTH - 3)
                y = rng.randint(2, TILE_HEIGHT - 3)
                length = rng.randint(4, 8)
                for i in range(length):
                    cx = max(1, min(TILE_WIDTH - 2, x + i))
                    cy = max(1, min(TILE_HEIGHT - 2, y + rng.randint(-1, 1)))
                    surface.set_at((cx, cy), crack_color)
            for _ in range(3):
                x = rng.randint(2, TILE_WIDTH - 6)
                y = rng.randint(2, TILE_HEIGHT - 6)
                pygame.draw.rect(surface, crack_color, (x, y, 2, 2))
        return surface

    def save_generated_assets(self) -> None:
        for tile_type in self.tile_types:
            surface = self.generate_tile_texture(tile_type)
            pygame.image.save(surface, GENERATED_DIR / f"{tile_type}.png")

    def generate_replacement_placeholders(self, replacement_dir: Optional[Path] = None) -> None:
        target_dir = replacement_dir or REPLACEMENT_DIR
        target_dir.mkdir(parents=True, exist_ok=True)
        for tile_type in self.tile_types:
            if tile_type in TREE_TYPES:
                continue
            target_path = target_dir / f"{tile_type}_replace.png"
            if target_path.exists():
                continue
            surface = pygame.Surface((TILE_WIDTH, TILE_HEIGHT), pygame.SRCALPHA)
            base = DEFAULT_COLORS[tile_type]
            for y in range(TILE_HEIGHT):
                for x in range(TILE_WIDTH):
                    shade = 20 if (x + y) % 2 == 0 else -10
                    color = (
                        max(0, min(255, base[0] + shade)),
                        max(0, min(255, base[1] + shade)),
                        max(0, min(255, base[2] + shade)),
                    )
                    surface.set_at((x, y), color)
            pygame.image.save(surface, target_path)

    def ensure_biome_replacements(self, biome_name: str) -> Path:
        replacement_dir = self.get_biome_replacement_dir(biome_name)
        replacement_dir.mkdir(parents=True, exist_ok=True)
        return replacement_dir

    def generate_object_assets(self) -> None:
        for tile_type in OBJECT_TILE_TYPES:
            if tile_type in TREE_TYPES:
                continue
            surface = pygame.Surface((TILE_WIDTH, TILE_HEIGHT), pygame.SRCALPHA)
            color = DEFAULT_COLORS[tile_type]
            if tile_type == "rock":
                pygame.draw.polygon(
                    surface,
                    color,
                    [
                        (TILE_WIDTH // 2, 2),
                        (TILE_WIDTH - 6, TILE_HEIGHT // 2),
                        (TILE_WIDTH // 2, TILE_HEIGHT - 2),
                        (6, TILE_HEIGHT // 2),
                    ],
                )
            elif tile_type == "tree":
                pygame.draw.rect(surface, (90, 60, 30), (TILE_WIDTH // 2 - 3, TILE_HEIGHT // 2 - 1, 6, 8))
                pygame.draw.circle(surface, color, (TILE_WIDTH // 2, TILE_HEIGHT // 2 - 4), 7)
            elif tile_type == "bush":
                pygame.draw.circle(surface, color, (TILE_WIDTH // 2 - 4, TILE_HEIGHT // 2), 5)
                pygame.draw.circle(surface, color, (TILE_WIDTH // 2 + 4, TILE_HEIGHT // 2), 5)
                pygame.draw.circle(surface, color, (TILE_WIDTH // 2, TILE_HEIGHT // 2 - 3), 6)
            elif tile_type == "flower":
                pygame.draw.circle(surface, color, (TILE_WIDTH // 2, TILE_HEIGHT // 2 - 2), 3)
                pygame.draw.circle(surface, (250, 230, 80), (TILE_WIDTH // 2, TILE_HEIGHT // 2 - 2), 1)
                pygame.draw.line(surface, (60, 120, 70), (TILE_WIDTH // 2, TILE_HEIGHT // 2 + 2), (TILE_WIDTH // 2, TILE_HEIGHT - 2), 2)
            elif tile_type == "plant":
                pygame.draw.polygon(
                    surface,
                    color,
                    [
                        (TILE_WIDTH // 2, 2),
                        (TILE_WIDTH // 2 + 4, TILE_HEIGHT - 2),
                        (TILE_WIDTH // 2, TILE_HEIGHT // 2),
                        (TILE_WIDTH // 2 - 4, TILE_HEIGHT - 2),
                    ],
                )
            elif tile_type == "tall_grass":
                pygame.draw.line(surface, color, (TILE_WIDTH // 2, TILE_HEIGHT - 2), (TILE_WIDTH // 2, 4), 2)
                pygame.draw.line(surface, color, (TILE_WIDTH // 2 - 4, TILE_HEIGHT - 2), (TILE_WIDTH // 2 - 2, 6), 2)
                pygame.draw.line(surface, color, (TILE_WIDTH // 2 + 4, TILE_HEIGHT - 2), (TILE_WIDTH // 2 + 2, 6), 2)
            elif tile_type == "grass_patch":
                pygame.draw.ellipse(surface, color, (6, 8, 20, 6))
                pygame.draw.line(surface, (50, 120, 60), (8, 12), (12, 6), 2)
            elif tile_type == "reed":
                pygame.draw.line(surface, color, (TILE_WIDTH // 2 - 2, TILE_HEIGHT - 2), (TILE_WIDTH // 2 - 2, 4), 2)
                pygame.draw.line(surface, color, (TILE_WIDTH // 2 + 2, TILE_HEIGHT - 2), (TILE_WIDTH // 2 + 2, 4), 2)
                pygame.draw.circle(surface, (200, 180, 100), (TILE_WIDTH // 2 - 2, 4), 2)
                pygame.draw.circle(surface, (200, 180, 100), (TILE_WIDTH // 2 + 2, 4), 2)
            elif tile_type == "pine":
                pygame.draw.rect(surface, (80, 60, 30), (TILE_WIDTH // 2 - 2, TILE_HEIGHT // 2, 4, 6))
                pygame.draw.polygon(
                    surface,
                    color,
                    [
                        (TILE_WIDTH // 2, 2),
                        (TILE_WIDTH // 2 + 6, TILE_HEIGHT // 2),
                        (TILE_WIDTH // 2 - 6, TILE_HEIGHT // 2),
                    ],
                )
            elif tile_type == "palm":
                pygame.draw.rect(surface, (90, 70, 40), (TILE_WIDTH // 2 - 1, TILE_HEIGHT // 2 - 1, 2, 7))
                pygame.draw.line(surface, color, (TILE_WIDTH // 2, 4), (TILE_WIDTH // 2 - 6, 6), 2)
                pygame.draw.line(surface, color, (TILE_WIDTH // 2, 4), (TILE_WIDTH // 2 + 6, 6), 2)
                pygame.draw.line(surface, color, (TILE_WIDTH // 2, 4), (TILE_WIDTH // 2, 8), 2)
            elif tile_type == "cactus":
                pygame.draw.rect(surface, color, (TILE_WIDTH // 2 - 2, 4, 4, 10))
                pygame.draw.rect(surface, color, (TILE_WIDTH // 2 - 6, 8, 4, 4))
                pygame.draw.rect(surface, color, (TILE_WIDTH // 2 + 2, 6, 4, 4))
            generated_path = GENERATED_DIR / f"{tile_type}.png"
            replacement_path = REPLACEMENT_DIR / f"{tile_type}_replace.png"
            if not generated_path.exists():
                pygame.image.save(surface, generated_path)
            if not replacement_path.exists():
                pygame.image.save(surface, replacement_path)

    def generate_animal_assets(self) -> None:
        for tile_type in ANIMAL_TILE_TYPES:
            generated_path = GENERATED_DIR / f"{tile_type}.png"
            replacement_path = REPLACEMENT_DIR / f"{tile_type}_replace.png"
            if generated_path.exists() and replacement_path.exists():
                continue
            surface = pygame.Surface((TILE_WIDTH, TILE_HEIGHT), pygame.SRCALPHA)
            color = DEFAULT_COLORS[tile_type]
            if tile_type == "rabbit":
                pygame.draw.circle(surface, color, (TILE_WIDTH // 2, TILE_HEIGHT // 2), 4)
                pygame.draw.rect(surface, color, (TILE_WIDTH // 2 - 1, TILE_HEIGHT // 2 - 6, 2, 4))
            elif tile_type == "horse":
                pygame.draw.rect(surface, color, (8, 7, 16, 6))
                pygame.draw.rect(surface, color, (20, 5, 4, 4))
            elif tile_type == "dog":
                pygame.draw.rect(surface, color, (9, 8, 12, 5))
                pygame.draw.rect(surface, color, (19, 7, 3, 3))
            elif tile_type == "cat":
                pygame.draw.rect(surface, color, (10, 8, 10, 5))
                pygame.draw.rect(surface, color, (18, 7, 3, 3))
            elif tile_type == "cow":
                pygame.draw.rect(surface, color, (8, 7, 16, 7))
                pygame.draw.rect(surface, (240, 240, 240), (10, 8, 5, 3))
            elif tile_type == "bird":
                pygame.draw.polygon(surface, color, [(12, 8), (20, 6), (18, 12)])
            elif tile_type == "fish":
                pygame.draw.ellipse(surface, color, (10, 8, 12, 6))
                pygame.draw.polygon(surface, color, [(10, 11), (6, 9), (6, 13)])
            elif tile_type == "elephant":
                pygame.draw.ellipse(surface, color, (6, 6, 20, 10))
                pygame.draw.ellipse(surface, color, (18, 6, 8, 8))
                pygame.draw.rect(surface, color, (24, 9, 4, 6))
                pygame.draw.polygon(surface, (230, 230, 220), [(24, 12), (28, 11), (27, 13)])
            else:
                self._draw_generic_animal(surface, color)
            if not generated_path.exists():
                pygame.image.save(surface, generated_path)
            if not replacement_path.exists():
                pygame.image.save(surface, replacement_path)

    def generate_mob_assets(self) -> None:
        for tile_type in MOB_TILE_TYPES:
            generated_path = GENERATED_DIR / f"{tile_type}.png"
            replacement_path = REPLACEMENT_DIR / f"{tile_type}_replace.png"
            if generated_path.exists() and replacement_path.exists():
                continue
            surface = pygame.Surface((TILE_WIDTH, TILE_HEIGHT), pygame.SRCALPHA)
            color = DEFAULT_COLORS[tile_type]
            if tile_type == "slime":
                pygame.draw.ellipse(surface, color, (6, 6, 20, 10))
                pygame.draw.circle(surface, (20, 30, 20), (14, 9), 1)
                pygame.draw.circle(surface, (20, 30, 20), (18, 9), 1)
            elif tile_type == "goblin":
                pygame.draw.rect(surface, color, (10, 6, 12, 10))
                pygame.draw.rect(surface, (40, 60, 40), (12, 8, 3, 3))
                pygame.draw.rect(surface, (40, 60, 40), (17, 8, 3, 3))
            elif tile_type == "alien":
                pygame.draw.ellipse(surface, color, (8, 5, 16, 10))
                pygame.draw.circle(surface, (20, 40, 20), (14, 9), 2)
                pygame.draw.circle(surface, (20, 40, 20), (18, 9), 2)
                pygame.draw.line(surface, color, (16, 5), (16, 1), 2)
            if not generated_path.exists():
                pygame.image.save(surface, generated_path)
            if not replacement_path.exists():
                pygame.image.save(surface, replacement_path)

    def _draw_generic_animal(self, surface: pygame.Surface, color: Tuple[int, int, int]) -> None:
        pygame.draw.ellipse(surface, color, (8, 8, 16, 6))
        pygame.draw.circle(surface, color, (20, 10), 3)


class IsoRenderer:
    def __init__(self, screen: pygame.Surface, styles: Dict[str, TileStyle]) -> None:
        self.screen = screen
        self.styles = styles
        self.cache: Dict[str, pygame.Surface] = {}
        self.texture_cache: Dict[str, pygame.Surface] = {}
        self.raw_texture_cache: Dict[str, pygame.Surface] = {}
        # Mild pixelation for tall tree sprites so high-res images match the game's pixel-art theme.
        # This is applied at load time (cached), so it has negligible runtime cost.
        self.tree_pixelate_ratio = 0.28  # 0.25..0.35 tends to look good

    def _pixelate(self, surface: pygame.Surface, ratio: float) -> pygame.Surface:
        """Return a pixelated copy of surface via downscale+upscale using nearest-neighbor."""
        if ratio >= 0.99:
            return surface
        w, h = surface.get_size()
        small_w = max(1, int(w * max(0.05, min(0.95, ratio))))
        small_h = max(1, int(h * max(0.05, min(0.95, ratio))))
        # Keep some minimum detail so tiny sprites don't become unreadable.
        small_w = max(8, min(w, small_w))
        small_h = max(8, min(h, small_h))
        # pygame.transform.scale uses nearest-neighbor sampling.
        down = pygame.transform.scale(surface, (small_w, small_h))
        up = pygame.transform.scale(down, (w, h))
        return up

    def iso_to_screen(self, x: int, y: int, height: int, offset: Tuple[int, int]) -> Tuple[int, int]:
        screen_x = (x - y) * (TILE_WIDTH // 2) + offset[0]
        screen_y = (x + y) * (TILE_HEIGHT // 2) + offset[1] - height * CUBE_HEIGHT
        return screen_x, screen_y

    @staticmethod
    def point_in_diamond(point: Tuple[int, int], top_left: Tuple[int, int]) -> bool:
        px, py = point
        tx, ty = top_left
        cx = tx + TILE_WIDTH / 2
        cy = ty + TILE_HEIGHT / 2
        dx = abs(px - cx) / (TILE_WIDTH / 2)
        dy = abs(py - cy) / (TILE_HEIGHT / 2)
        return dx + dy <= 1

    def draw_tile(self, tile: Tile, x: int, y: int, offset: Tuple[int, int]) -> None:
        style = self.styles[tile.tile_type]
        override_key = ""
        override_surface = None
        if tile.texture_override and not self.is_tree_override(tile.texture_override):
            override_surface = self._load_override_texture(
                tile.texture_override,
                tile.rotation,
                tile.flip_x,
                tile.texture_tint,
                tile.texture_scale,
            )
            override_key = (
                f"override_{tile.texture_override}_{tile.rotation}_"
                f"{tile.flip_x}_{tile.texture_tint}_{tile.texture_scale:.2f}"
            )
        key = (
            f"{tile.tile_type}_{style.brightness}_{style.contrast}_{style.darkness}_{style.tint}_{style.texture_seed}_"
            f"{override_key}"
        )
        if key not in self.cache:
            self.cache[key] = self._create_tile_surface(tile.tile_type, override_surface)
        surface = self.cache[key]
        screen_x, screen_y = self.iso_to_screen(x, y, tile.height, offset)
        self.screen.blit(surface, (screen_x, screen_y))

    def is_tree_override(self, path: str) -> bool:
        # Trees are rendered as tall sprites (not as top-face textures).
        # User rule: if the filename includes "tree" inside a replacements folder,
        # treat it as a tree, even if it doesn't match a known TREE_TYPES key.
        stem = Path(path).stem.lower()
        if "tree" in stem:
            return True
        return stem.replace("_replace", "") in TREE_TYPES

    def _load_override_texture(
        self,
        path: str,
        rotation: int,
        flip_x: bool,
        tint: Tuple[int, int, int],
        scale: float,
    ) -> Optional[pygame.Surface]:
        cache_key = f"{path}_{rotation}_{flip_x}_{tint}_{scale:.2f}"
        if cache_key in self.texture_cache:
            return self.texture_cache[cache_key]
        if path in self.raw_texture_cache:
            base = self.raw_texture_cache[path]
        else:
            texture_path = Path(path)
            if not texture_path.exists():
                return None
            base = pygame.image.load(str(texture_path)).convert_alpha()
            self.raw_texture_cache[path] = base
        surface = base.copy()
        if flip_x:
            surface = pygame.transform.flip(surface, True, False)
        if rotation:
            surface = pygame.transform.rotate(surface, rotation)
        target_w = max(1, int(TILE_WIDTH * max(0.6, min(1.6, scale))))
        target_h = max(1, int(TILE_HEIGHT * max(0.6, min(1.6, scale))))
        surface = pygame.transform.smoothscale(surface, (target_w, target_h))
        if (target_w, target_h) != (TILE_WIDTH, TILE_HEIGHT):
            framed = pygame.Surface((TILE_WIDTH, TILE_HEIGHT), pygame.SRCALPHA)
            offset_x = (TILE_WIDTH - target_w) // 2
            offset_y = (TILE_HEIGHT - target_h) // 2
            framed.blit(surface, (offset_x, offset_y))
            surface = framed
        tint_surface = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        tint_surface.fill((*tint, 255))
        surface.blit(tint_surface, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        self.texture_cache[cache_key] = surface
        return surface

    def load_sprite(
        self,
        path: str,
        flip_x: bool,
        tint: Tuple[int, int, int],
        scale: float,
    ) -> Optional[pygame.Surface]:
        cache_key = f"sprite_{path}_{flip_x}_{tint}_{scale:.2f}"
        if cache_key in self.texture_cache:
            return self.texture_cache[cache_key]
        is_tree = self.is_tree_override(path)
        texture_path = Path(path)
        if not texture_path.exists():
            return None
        if path in self.raw_texture_cache:
            base = self.raw_texture_cache[path]
        else:
            base = pygame.image.load(str(texture_path)).convert_alpha()
            self.raw_texture_cache[path] = base
        surface = base.copy()
        if flip_x:
            surface = pygame.transform.flip(surface, True, False)
        if scale != 1.0:
            target_w = max(1, int(surface.get_width() * max(0.5, min(2.0, scale))))
            target_h = max(1, int(surface.get_height() * max(0.5, min(2.0, scale))))
            # Keep tree sprites crisp; other sprites can be smoothed.
            if is_tree:
                surface = pygame.transform.scale(surface, (target_w, target_h))
            else:
                surface = pygame.transform.smoothscale(surface, (target_w, target_h))
        if is_tree and self.tree_pixelate_ratio > 0:
            surface = self._pixelate(surface, self.tree_pixelate_ratio)
        tint_surface = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        tint_surface.fill((*tint, 255))
        surface.blit(tint_surface, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        self.texture_cache[cache_key] = surface
        return surface

    def _apply_top_texture(self, target: pygame.Surface, texture: pygame.Surface, style: TileStyle) -> None:
        top_mask = pygame.Surface((TILE_WIDTH, TILE_HEIGHT), pygame.SRCALPHA)
        top = [
            (TILE_WIDTH // 2, 0),
            (TILE_WIDTH - 1, TILE_HEIGHT // 2),
            (TILE_WIDTH // 2, TILE_HEIGHT - 1),
            (0, TILE_HEIGHT // 2),
        ]
        pygame.draw.polygon(top_mask, (255, 255, 255, 255), top)
        textured = texture.copy()
        tint = style.apply((255, 255, 255))
        tint_surface = pygame.Surface(textured.get_size(), pygame.SRCALPHA)
        tint_surface.fill((*tint, 255))
        textured.blit(tint_surface, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        textured.blit(top_mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        target.blit(textured, (0, 0))

    def _create_tile_surface(self, tile_type: str, texture_override: Optional[pygame.Surface] = None) -> pygame.Surface:
        style = self.styles[tile_type]
        top_color = style.apply(style.base_color)
        left_color = style.apply(tuple(max(0, c - 30) for c in style.base_color))
        right_color = style.apply(tuple(max(0, c - 15) for c in style.base_color))
        tile_surface = pygame.Surface((TILE_WIDTH, TILE_HEIGHT + CUBE_HEIGHT), pygame.SRCALPHA)
        top = [
            (TILE_WIDTH // 2, 0),
            (TILE_WIDTH - 1, TILE_HEIGHT // 2),
            (TILE_WIDTH // 2, TILE_HEIGHT - 1),
            (0, TILE_HEIGHT // 2),
        ]
        left = [
            (0, TILE_HEIGHT // 2),
            (TILE_WIDTH // 2, TILE_HEIGHT - 1),
            (TILE_WIDTH // 2, TILE_HEIGHT - 1 + CUBE_HEIGHT),
            (0, TILE_HEIGHT // 2 + CUBE_HEIGHT),
        ]
        right = [
            (TILE_WIDTH // 2, TILE_HEIGHT - 1),
            (TILE_WIDTH - 1, TILE_HEIGHT // 2),
            (TILE_WIDTH - 1, TILE_HEIGHT // 2 + CUBE_HEIGHT),
            (TILE_WIDTH // 2, TILE_HEIGHT - 1 + CUBE_HEIGHT),
        ]
        pygame.draw.polygon(tile_surface, top_color, top)
        if texture_override is not None:
            self._apply_top_texture(tile_surface, texture_override, style)
        pygame.draw.polygon(tile_surface, left_color, left)
        pygame.draw.polygon(tile_surface, right_color, right)
        return tile_surface

    def draw_vertical_face(
        self,
        x: int,
        y: int,
        height: int,
        neighbor_height: int,
        tile_type: str,
        offset: Tuple[int, int],
    ) -> None:
        if neighbor_height >= height:
            return
        style = self.styles[tile_type]
        face_color = style.apply(tuple(max(0, c - 40) for c in style.base_color))
        screen_x, screen_y = self.iso_to_screen(x, y, height, offset)
        diff = height - neighbor_height
        face_height = diff * CUBE_HEIGHT
        left_face = [
            (screen_x, screen_y + TILE_HEIGHT // 2),
            (screen_x + TILE_WIDTH // 2, screen_y + TILE_HEIGHT),
            (screen_x + TILE_WIDTH // 2, screen_y + TILE_HEIGHT + face_height),
            (screen_x, screen_y + TILE_HEIGHT // 2 + face_height),
        ]
        right_face = [
            (screen_x + TILE_WIDTH // 2, screen_y + TILE_HEIGHT),
            (screen_x + TILE_WIDTH, screen_y + TILE_HEIGHT // 2),
            (screen_x + TILE_WIDTH, screen_y + TILE_HEIGHT // 2 + face_height),
            (screen_x + TILE_WIDTH // 2, screen_y + TILE_HEIGHT + face_height),
        ]
        pygame.draw.polygon(self.screen, face_color, left_face)
        pygame.draw.polygon(self.screen, face_color, right_face)


class IsoApp:
    def __init__(self, world_size: Tuple[int, int]) -> None:
        pygame.init()
        pygame.display.set_caption("Isometric World Engine")
        self.fullscreen = False
        self.base_day_speed = 1 / 600.0
        self.day_speed = self.base_day_speed
        self.settings = {
            "water_reflections": True,
            "show_stars": True,
            "day_night_cycle": True,
            "high_quality": True,
            "day_speed_multiplier": 1.0,
            "subsurface_depth": 6,
            "vsync": True,
            "audio_enabled": True,
            "audio_volume": 0.6,
            "tree_cluster_density": 0.55,
            "tree_cluster_min_sep": 2,
        }
        self.load_settings()
        self.screen = self.create_display((1280, 720))
        self.clock = pygame.time.Clock()
        self.ui_font = pygame.font.SysFont("consolas", 16)
        self.ui_small_font = pygame.font.SysFont("consolas", 14)
        self.info_font = pygame.font.SysFont("consolas", 16)
        self.zoom_levels = [0.8, 1.0, 1.25]
        self.zoom_index = 1
        # Zoom rendering optimization state
        self._zoom_world_surface: Optional[pygame.Surface] = None
        self._zoom_smooth_next = True
        self._last_zoom_index = self.zoom_index
        self._last_screen_size = self.screen.get_size()
        self.audio = AudioManager(self.settings)
        self.tile_types = list(BASE_TILE_TYPES)
        self.object_tile_types = list(OBJECT_TILE_TYPES)
        self.animal_tile_types = list(ANIMAL_TILE_TYPES)
        self.mob_tile_types = list(MOB_TILE_TYPES)
        self.styles = {
            tile_type: TileStyle(base_color=DEFAULT_COLORS[tile_type], texture_seed=i)
            for i, tile_type in enumerate(self.tile_types)
        }
        self.asset_manager = AssetManager(
            self.styles,
            self.tile_types + self.object_tile_types + self.animal_tile_types + self.mob_tile_types,
        )
        self.world = World(width=world_size[0], height=world_size[1])
        self.renderer = IsoRenderer(self.screen, self.styles)
        self.offset = (self.screen.get_width() // 2, 120)
        self.selected_tile_type = "grass"
        self.current_tool = "raise"
        self.brush_size = 1
        self.undo_stack: List[UndoAction] = []
        self.redo_stack: List[UndoAction] = []
        self.show_help = False
        self.buttons: List[Button] = []
        self.tool_buttons: Dict[str, Button] = {}
        self.tile_buttons: Dict[str, Button] = {}
        self.last_paint_time = 0
        self.drag_interval_ms = 120
        self.ui_rect = pygame.Rect(self.screen.get_width() - 260, 10, 250, self.screen.get_height() - 20)
        self.texture_list_rect = pygame.Rect(0, 0, 0, 0)
        self.texture_area_rect = self.texture_list_rect.copy()
        self.texture_list_collapsed = False
        self.texture_list_header_rect = pygame.Rect(0, 0, 0, 0)
        self.replacement_images: List[Path] = []
        self.hidden_replacement_images: List[Path] = []
        self.hidden_replacement_by_type: Dict[str, Path] = {}
        self.replacement_index = 0
        self.replacement_rotation = 0
        self.world_seed = random.randint(0, 999999)
        self.biome_cycle: List[Dict[str, float]] = []
        self.reset_biome_cycle()
        self.generation_params = self.build_generation_params(self.world_seed)
        self.current_biome = self.generation_params.get("biome", BIOME_PRESETS[0])
        self.last_directory = self.load_last_directory()
        self.last_image_directory = self.load_last_image_directory()
        self.replacement_order = self.load_replacement_order()
        self.panel_scroll = 0
        self.texture_scroll = 0
        self.texture_scroll_speed = 24
        self.texture_item_height = 36
        self.texture_sidebar_width = 8
        self.player_mode = False
        self.player: Optional[Player] = None
        self.mobs: List[Mob] = []
        self.animals: List[Animal] = []
        self.loot: List[Tuple[float, float, str]] = []
        self.texture_thumbs: Dict[str, pygame.Surface] = {}
        self.sections: List[PanelSection] = []
        self.section_states: Dict[str, bool] = {}
        self.day_time = 0.25
        self.water_timer = 0.0
        self.settings_visible = False
        self.settings_button_rect = pygame.Rect(10, 10, 110, 28)
        self.player_button_rect = pygame.Rect(10, 46, 110, 28)
        self.settings_panel_rect = pygame.Rect(10, 82, 340, 360)
        self.day_speed_dragging = False
        self.subsurface_dragging = False
        self.audio_dragging = False
        self.palette_visible = False
        self.palette_panel_rect = pygame.Rect(10, 82, 320, 360)
        self.palette_tab = "tiles"
        self.palette_scroll = 0
        self.menu_visible = False
        self.menu_button_rects: Dict[str, pygame.Rect] = {}
        self.active_menu = ""
        self.menu_panel_rect = pygame.Rect(130, 82, 260, 320)
        self.inventory_visible = False
        self.inventory_panel_rect = pygame.Rect(0, 0, 520, 420)
        self.inventory_scroll = 0
        self.inventory_item_height = 28
        self.selected_inventory_item: Optional[str] = None
        self.selected_weapon_id: Optional[str] = None
        self.projectiles: List[Projectile] = []
        self.manual_target: Optional[Mob] = None
        self.manual_target_timer: float = 0.0
        self.exit_prompt_timer = 0.0
        self.exit_prompt_duration = 2.0
        self.last_escape_time = 0.0
        self.weather_particles: List[Dict[str, float]] = []
        self.weather_type = "clear"
        self.fog_offset = 0.0
        self.weather_timer = 0.0
        self.weather_duration = 0.0
        self.lightning_flash = 0.0
        self.invasion_timer = random.uniform(60.0, 110.0)
        self.invasion_notice_timer = 0.0
        self.audio_cooldowns = {"water": 0.0, "bird": 0.0, "ambient": 0.0}
        self.death_effects: List[Dict[str, float]] = []
        self.cavern_open_tiles: Set[Tuple[int, int]] = set()
        self.mineral_tiles: Set[Tuple[int, int]] = set()
        self.gem_tiles: Set[Tuple[int, int]] = set()
        self.star_positions = self.generate_stars(120)
        self.build_ui()
        self.update_layout()
        self.load_replacement_images()
        self.asset_manager.generate_object_assets()
        self.asset_manager.generate_animal_assets()
        self.asset_manager.generate_mob_assets()
        self.generate_world()

    def build_ui(self) -> None:
        self.buttons.clear()
        self.tool_buttons.clear()
        self.tile_buttons.clear()
        self.sections.clear()
        x = self.ui_rect.x + 10
        button_w = self.ui_rect.width - 20
        button_h = 26
        gap = 6

        def add_section(title: str, expanded: bool = True) -> PanelSection:
            expanded = self.section_states.get(title, expanded)
            section = PanelSection(title=title, expanded=expanded)
            self.sections.append(section)
            return section

        def add_button(section: PanelSection, label: str, callback: callable, toggle: bool = False) -> Button:
            rect = pygame.Rect(x, 0, button_w, button_h)
            button = Button(label=label, rect=rect, callback=callback, toggle=toggle)
            section.buttons.append(button)
            self.buttons.append(button)
            return button

        tool_section = add_section("Editor")
        add_button(tool_section, "Undo", lambda: self.apply_undo(self.undo_stack, self.redo_stack))
        add_button(tool_section, "Redo", lambda: self.apply_undo(self.redo_stack, self.undo_stack))
        add_button(tool_section, "Toggle Help", self.toggle_help)
        add_button(tool_section, "Palette: Toggle", self.toggle_palette_menu)
        add_button(tool_section, "World: Regenerate", self.generate_world)
        add_button(tool_section, "World: Smooth Heights", self.smooth_heights)
        add_button(tool_section, "World: Flatten", self.flatten_world)
        add_button(tool_section, "World: Center Camera", self.center_camera)
        tool_buttons = [
            ("Tool: Raise", "raise"),
            ("Tool: Lower", "lower"),
            ("Tool: Paint", "paint"),
            ("Tool: Erase", "erase"),
            ("Tool: Pick", "pick"),
            ("Tool: Replace Texture", "replace_texture"),
            ("Tool: Remove Texture", "remove_texture"),
        ]
        for label, tool in tool_buttons:
            button = add_button(tool_section, label, lambda t=tool: self.set_tool(t), toggle=True)
            self.tool_buttons[tool] = button
        add_button(tool_section, "Brush: Smaller", self.decrease_brush)
        add_button(tool_section, "Brush: Larger", self.increase_brush)
        add_button(tool_section, "Texture: Rotate 90", self.rotate_replacement)
        add_button(tool_section, "Texture: Clear Tile", lambda: self.set_tool("remove_texture"))
        add_button(tool_section, "Shader: Generate", self.generate_shader_styles)
        add_button(tool_section, "Export PNG", self.export_world_dialog)
        add_button(tool_section, "Create Tile Type", self.create_tile_type)

        self.section_states = {section.title: section.expanded for section in self.sections}
        self.refresh_button_states()

    def refresh_button_states(self) -> None:
        for tool, button in self.tool_buttons.items():
            button.toggled = tool == self.current_tool
        for tile_type, button in self.tile_buttons.items():
            button.toggled = tile_type == self.selected_tile_type
        for button in self.buttons:
            if button.label == "Player":
                button.toggled = self.player_mode

    def set_tool(self, tool: str) -> None:
        self.current_tool = tool
        self.refresh_button_states()

    def set_tile_type(self, tile_type: str) -> None:
        self.selected_tile_type = tile_type
        self.refresh_button_states()

    def toggle_help(self) -> None:
        self.show_help = not self.show_help

    def toggle_palette_menu(self) -> None:
        self.palette_visible = not self.palette_visible
        if self.palette_visible:
            self.settings_visible = False
            self.menu_visible = False
            self.inventory_visible = False

    def center_camera(self) -> None:
        self.center_camera_on_world()

    def center_camera_on_world(self) -> None:
        center_x = self.world.width // 2
        center_y = self.world.height // 2
        tile = self.world.get_tile(center_x, center_y)
        height = tile.height if tile else 0
        screen_x, screen_y = self.renderer.iso_to_screen(center_x, center_y, height, (0, 0))
        self.offset = (
            self.screen.get_width() // 2 - screen_x - TILE_WIDTH // 2,
            self.screen.get_height() // 2 - screen_y - TILE_HEIGHT // 2,
        )

    def increase_brush(self) -> None:
        self.brush_size = min(6, self.brush_size + 1)

    def decrease_brush(self) -> None:
        self.brush_size = max(1, self.brush_size - 1)

    def shuffle_texture(self) -> None:
        style = self.styles[self.selected_tile_type]
        style.texture_seed = random.randint(0, 9999)
        self.renderer.cache.clear()

    def reset_style(self) -> None:
        self.styles[self.selected_tile_type] = TileStyle(
            base_color=DEFAULT_COLORS[self.selected_tile_type],
            texture_seed=self.tile_types.index(self.selected_tile_type),
        )
        self.renderer.styles = self.styles
        self.renderer.cache.clear()

    def generate_shader_styles(self) -> None:
        rng = random.Random(random.randint(0, 999999))
        base_brightness = rng.uniform(0.85, 1.25)
        base_contrast = rng.uniform(0.85, 1.35)
        base_darkness = rng.uniform(0.0, 0.25)
        tint_shift = (rng.randint(-12, 12), rng.randint(-12, 12), rng.randint(-12, 12))
        for tile_type in self.tile_types:
            style = self.styles[tile_type]
            style.brightness = max(0.4, min(1.8, base_brightness + rng.uniform(-0.08, 0.08)))
            style.contrast = max(0.6, min(1.8, base_contrast + rng.uniform(-0.08, 0.08)))
            style.darkness = max(0.0, min(0.5, base_darkness + rng.uniform(-0.05, 0.05)))
            style.tint = (
                max(-40, min(40, tint_shift[0] + rng.randint(-6, 6))),
                max(-40, min(40, tint_shift[1] + rng.randint(-6, 6))),
                max(-40, min(40, tint_shift[2] + rng.randint(-6, 6))),
            )
            style.texture_seed = rng.randint(0, 9999)
        self.renderer.cache.clear()

    def toggle_player_mode(self) -> None:
        self.player_mode = not self.player_mode
        if self.player_mode and self.player is None:
            self.spawn_player()
        self.refresh_button_states()

    def generate_stars(self, count: int) -> List[Tuple[int, int, int]]:
        stars = []
        rng = random.Random(42)
        for _ in range(count):
            x = rng.randint(0, self.screen.get_width() - 1)
            y = rng.randint(0, self.screen.get_height() // 2)
            size = rng.choice([1, 2])
            stars.append((x, y, size))
        return stars

    def set_player_mode(self, mode: str) -> None:
        if self.player is None:
            self.spawn_player()
        if self.player:
            self.player.mode = mode
        self.refresh_button_states()

    def read_config(self) -> Dict:
        if CONFIG_PATH.exists():
            try:
                return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                return {}
        return {}

    def write_config(self, data: Dict) -> None:
        SAVE_DIR.mkdir(exist_ok=True)
        CONFIG_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def load_last_directory(self) -> Path:
        data = self.read_config()
        path = data.get("last_directory")
        if path:
            return Path(path)
        return Path.cwd()

    def load_last_image_directory(self) -> Path:
        data = self.read_config()
        path = data.get("last_image_directory")
        if path:
            return Path(path)
        return Path.cwd()

    def current_biome_key(self) -> str:
        biome_name = "default"
        if self.current_biome:
            biome_name = self.current_biome.get("name", "default")
        return self.asset_manager.biome_key(biome_name)

    def get_biome_replacement_dir(self) -> Path:
        biome_name = "default"
        if self.current_biome:
            biome_name = self.current_biome.get("name", "default")
        return self.asset_manager.get_biome_replacement_dir(biome_name)

    def update_replacement_order_payload(self, data: Dict) -> None:
        order_by_biome = data.get("replacement_order_by_biome")
        if not isinstance(order_by_biome, dict):
            order_by_biome = {}
        order_by_biome[self.current_biome_key()] = self.replacement_order
        data["replacement_order_by_biome"] = order_by_biome
        data["replacement_order"] = self.replacement_order

    def save_last_directory(self, path: Path) -> None:
        data = self.read_config()
        self.update_replacement_order_payload(data)
        data.update(
            {
                "last_directory": str(path),
                "last_image_directory": str(self.last_image_directory),
                "settings": self.settings,
            }
        )
        self.write_config(data)
        self.last_directory = path

    def save_last_image_directory(self, path: Path) -> None:
        data = self.read_config()
        self.update_replacement_order_payload(data)
        data.update(
            {
                "last_directory": str(self.last_directory),
                "last_image_directory": str(path),
                "settings": self.settings,
            }
        )
        self.write_config(data)
        self.last_image_directory = path

    def load_replacement_order(self) -> List[str]:
        data = self.read_config()
        order_by_biome = data.get("replacement_order_by_biome")
        if isinstance(order_by_biome, dict):
            order = order_by_biome.get(self.current_biome_key())
            if isinstance(order, list):
                return order
        order = data.get("replacement_order")
        if isinstance(order, list):
            return order
        return []

    def save_replacement_order(self) -> None:
        data = self.read_config()
        self.update_replacement_order_payload(data)
        data.update(
            {
                "last_directory": str(self.last_directory),
                "last_image_directory": str(self.last_image_directory),
                "settings": self.settings,
            }
        )
        self.write_config(data)

    def load_settings(self) -> None:
        data = self.read_config()
        settings = data.get("settings")
        if isinstance(settings, dict):
            self.settings.update(settings)
        multiplier = float(self.settings.get("day_speed_multiplier", 1.0))
        multiplier = max(0.05, min(6.0, multiplier))
        self.settings["day_speed_multiplier"] = multiplier
        self.day_speed = self.base_day_speed * multiplier
        subsurface_depth = int(self.settings.get("subsurface_depth", 6))
        self.settings["subsurface_depth"] = max(2, min(16, subsurface_depth))
        self.settings["vsync"] = bool(self.settings.get("vsync", True))
        self.settings["audio_enabled"] = bool(self.settings.get("audio_enabled", True))
        volume = float(self.settings.get("audio_volume", 0.6))
        self.settings["audio_volume"] = max(0.0, min(1.0, volume))

    def save_settings(self) -> None:
        data = self.read_config()
        data["settings"] = self.settings
        data["last_directory"] = str(self.last_directory)
        data["last_image_directory"] = str(self.last_image_directory)
        self.update_replacement_order_payload(data)
        self.write_config(data)

    def load_replacement_images(self) -> None:
        replacement_dir = self.get_biome_replacement_dir()
        replacement_dir.mkdir(parents=True, exist_ok=True)
        images = list(replacement_dir.glob("*.png"))
        if not images:
            biome_name = self.current_biome.get("name", "default") if self.current_biome else "default"
            self.asset_manager.ensure_biome_replacements(biome_name)
        # Any image whose filename includes "tree" is treated as a tree sprite asset.
        # If a biome has zero such files, that biome is considered "no trees".
        tree_assets = [path for path in images if "tree" in path.stem.lower()]
        self.detected_tree_types = []

        hidden_names = {
            f"{name}_replace.png"
            for name in self.object_tile_types + self.animal_tile_types + self.mob_tile_types
        }
        hidden_paths: Set[Path] = {path for path in images if path.name in hidden_names}
        hidden_paths.update(tree_assets)

        self.hidden_replacement_images = [path for path in images if path in hidden_paths]
        visible_images = [path for path in images if path not in hidden_paths]
        if self.replacement_order:
            ordered = []
            remaining = {str(path): path for path in visible_images}
            for entry in self.replacement_order:
                path = remaining.pop(entry, None)
                if path:
                    ordered.append(path)
            ordered.extend(sorted(remaining.values()))
            self.replacement_images = ordered
        else:
            self.replacement_images = sorted(visible_images)
        self.replacement_index = 0
        self.texture_thumbs.clear()
        self.renderer.texture_cache.clear()
        self.renderer.raw_texture_cache.clear()
        self.renderer.cache.clear()
        # Map hidden replacement images to types.
        # - Standard hidden assets use "<type>_replace.png" and map to "<type>".
        # - Tree assets can be named freely as long as the filename includes "tree".
        self.hidden_replacement_by_type = {}

        # Standard hidden assets.
        for path in images:
            if path.name not in hidden_names:
                continue
            key = path.stem.replace("_replace", "")
            self.hidden_replacement_by_type[key] = path

        # Tree assets: create stable, unique keys from the filename stem.
        used = set(self.hidden_replacement_by_type.keys())
        for path in tree_assets:
            base_key = path.stem.lower().replace("_replace", "")
            key = base_key
            suffix = 2
            while key in used and self.hidden_replacement_by_type.get(key) != path:
                key = f"{base_key}_{suffix}"
                suffix += 1
            used.add(key)
            self.hidden_replacement_by_type[key] = path
            if key not in self.detected_tree_types:
                self.detected_tree_types.append(key)

    def current_replacement(self) -> Optional[Path]:
        if not self.replacement_images:
            return None
        return self.replacement_images[self.replacement_index % len(self.replacement_images)]

    def current_replacement_name(self) -> str:
        replacement = self.current_replacement()
        if replacement is None:
            return "None"
        return replacement.name

    def load_replacement_image(self) -> None:
        path = self.open_file_dialog("Select replacement image", [("PNG files", "*.png")], use_image_dir=True)
        if path is None:
            return
        replacement_dir = self.get_biome_replacement_dir()
        replacement_dir.mkdir(parents=True, exist_ok=True)
        destination = replacement_dir / path.name
        shutil.copy2(path, destination)
        if destination not in self.replacement_images:
            self.replacement_images.append(destination)
        self.replacement_order = [str(p) for p in self.replacement_images]
        self.save_replacement_order()
        self.replacement_index = self.replacement_images.index(destination)
        self.texture_thumbs.pop(str(destination), None)

    def open_file_dialog(
        self,
        title: str,
        filetypes: List[Tuple[str, str]],
        use_image_dir: bool = False,
    ) -> Optional[Path]:
        root = Tk()
        root.withdraw()
        initial_dir = self.last_image_directory if use_image_dir else self.last_directory
        path = filedialog.askopenfilename(
            title=title,
            filetypes=filetypes,
            initialdir=initial_dir,
        )
        root.destroy()
        if not path:
            return None
        chosen = Path(path)
        if chosen.parent:
            if use_image_dir:
                self.save_last_image_directory(chosen.parent)
            else:
                self.save_last_directory(chosen.parent)
        return chosen

    def save_file_dialog(self, title: str, default_name: str, filetypes: List[Tuple[str, str]]) -> Optional[Path]:
        root = Tk()
        root.withdraw()
        path = filedialog.asksaveasfilename(
            title=title,
            defaultextension=filetypes[0][1],
            filetypes=filetypes,
            initialdir=self.last_directory,
            initialfile=default_name,
        )
        root.destroy()
        if not path:
            return None
        chosen = Path(path)
        if chosen.parent:
            self.save_last_directory(chosen.parent)
        return chosen

    def save_world_dialog(self) -> None:
        path = self.save_file_dialog("Save world", "world.json", [("JSON files", "*.json")])
        if path is None:
            return
        self.save_world(path)

    def load_world_dialog(self) -> None:
        path = self.open_file_dialog("Load world", [("JSON files", "*.json")])
        if path is None:
            return
        self.load_world(path)

    def export_world_dialog(self) -> None:
        path = self.save_file_dialog("Export PNG", "world_export.png", [("PNG files", "*.png")])
        if path is None:
            return
        self.export_for_pygame(path)

    def create_tile_type(self) -> None:
        root = Tk()
        root.withdraw()
        name = simpledialog.askstring("New Tile", "Tile name:", parent=root)
        root.destroy()
        if not name:
            return
        sanitized = name.strip().lower().replace(" ", "_")
        if not sanitized or sanitized in self.tile_types:
            return
        image_path = self.open_file_dialog(
            "Select tile image (optional)",
            [("PNG files", "*.png")],
            use_image_dir=True,
        )
        rotation = 0
        if image_path is not None:
            root = Tk()
            root.withdraw()
            rotation = simpledialog.askinteger(
                "Rotate Tile Image",
                "Rotation (0, 90, 180, 270):",
                initialvalue=0,
                minvalue=0,
                maxvalue=270,
                parent=root,
            )
            root.destroy()
            rotation = rotation or 0
            rotation = int(round(rotation / 90) * 90) % 360
        color = (
            random.randint(40, 220),
            random.randint(40, 220),
            random.randint(40, 220),
        )
        if image_path is not None:
            image_surface = pygame.image.load(str(image_path)).convert_alpha()
            image_surface = pygame.transform.rotate(image_surface, rotation)
            image_surface = pygame.transform.smoothscale(image_surface, (TILE_WIDTH, TILE_HEIGHT))
            avg_color = self.average_color(image_surface)
            color = avg_color
            replacement_dir = self.get_biome_replacement_dir()
            replacement_dir.mkdir(parents=True, exist_ok=True)
            destination = replacement_dir / f"{sanitized}{image_path.suffix}"
            pygame.image.save(image_surface, destination)
            self.replacement_images.append(destination)
            self.replacement_order = [str(p) for p in self.replacement_images]
            self.save_replacement_order()
            if destination in self.replacement_images:
                self.replacement_index = self.replacement_images.index(destination)
        self.tile_types.append(sanitized)
        DEFAULT_COLORS[sanitized] = color
        self.styles[sanitized] = TileStyle(base_color=color, texture_seed=len(self.tile_types))
        self.asset_manager.tile_types = (
            self.tile_types + self.object_tile_types + self.animal_tile_types + self.mob_tile_types
        )
        self.build_ui()
        self.set_tile_type(sanitized)

    def average_color(self, surface: pygame.Surface) -> Tuple[int, int, int]:
        width, height = surface.get_size()
        total_r = total_g = total_b = count = 0
        for y in range(height):
            for x in range(width):
                r, g, b, a = surface.get_at((x, y))
                if a == 0:
                    continue
                total_r += r
                total_g += g
                total_b += b
                count += 1
        if count == 0:
            return (120, 120, 120)
        return (total_r // count, total_g // count, total_b // count)

    def scatter_objects(self, rng: random.Random, chance: float = 0.12) -> None:
        tree_choices = self.get_biome_tree_choices()
        for (x, y), tile in self.world.tiles.items():
            if not self.should_render_tile(tile):
                continue
            if tile.tile_type == "water":
                continue
            if tile.height <= CAVERN_TOP:
                continue
            if tile.texture_override:
                continue
            if rng.random() < chance:
                choice = self.choose_object_for_tile(tile.tile_type, rng, tree_choices)
                replacement = self.hidden_replacement_by_type.get(choice)
                if replacement:
                    tile.texture_override = str(replacement)
                    is_tree = self.is_tree_key(choice)
                    tile.rotation = 0 if is_tree else rng.choice([0, 90, 180, 270])
                    if is_tree:
                        self.apply_tree_variation(tile, rng)
                        tile.height = min(MAX_HEIGHT, tile.height + rng.randint(2, 4))
                    else:
                        tile.flip_x = False
                        tile.texture_tint = (255, 255, 255)
                        tile.texture_scale = 1.0

    def scatter_forests(self, rng: random.Random) -> None:
        cluster_count = max(8, (self.world.width * self.world.height) // 350)
        tree_choices = self.get_biome_tree_choices()
        if not tree_choices:
            return
        for _ in range(cluster_count):
            center_x = rng.randint(2, self.world.width - 3)
            center_y = rng.randint(2, self.world.height - 3)
            tile = self.world.get_tile(center_x, center_y)
            if tile is None or tile.tile_type == "water" or tile.height <= CAVERN_TOP:
                continue
            cluster_type = rng.choice(tree_choices)
            radius = rng.randint(4, 8)
            # Make clusters less dense and space trees apart.
            cluster_density = float(self.settings.get("tree_cluster_density", 0.45))
            cluster_density = max(0.1, min(0.95, cluster_density))
            tree_min_sep = int(self.settings.get("tree_cluster_min_sep", 3))
            tree_min_sep = max(1, min(6, tree_min_sep))
            placed_trees: Set[Tuple[int, int]] = set()
            for dx in range(-radius, radius + 1):
                for dy in range(-radius, radius + 1):
                    if abs(dx) + abs(dy) > radius + rng.randint(0, 2):
                        continue
                    # Reduce density so trees are not packed shoulder-to-shoulder.
                    if rng.random() > cluster_density:
                        continue
                    x = center_x + dx
                    y = center_y + dy
                    if not self.world.in_bounds(x, y):
                        continue
                    target = self.world.get_tile(x, y)
                    if target is None or target.tile_type == "water" or target.height <= CAVERN_TOP:
                        continue
                    if target.texture_override:
                        continue
                    if rng.random() < 0.15:
                        choice = rng.choice(["rock", "bush", "flower"])
                    else:
                        choice = cluster_type
                    replacement = self.hidden_replacement_by_type.get(choice)
                    if replacement:
                        target.texture_override = str(replacement)
                        is_tree = self.is_tree_key(choice)
                        target.rotation = 0 if is_tree else rng.choice([0, 90, 180, 270])
                        if is_tree:
                            # Enforce minimum spacing between trees within this cluster.
                            too_close = False
                            # Use Chebyshev distance (square neighborhood) so spacing
                            # feels more even than Manhattan-only spacing.
                            for ox in range(-tree_min_sep, tree_min_sep + 1):
                                for oy in range(-tree_min_sep, tree_min_sep + 1):
                                    if max(abs(ox), abs(oy)) > tree_min_sep:
                                        continue
                                    if (x + ox, y + oy) in placed_trees:
                                        too_close = True
                                        break
                                if too_close:
                                    break
                            if too_close:
                                # Undo the placement if it violates spacing.
                                target.texture_override = None
                                target.rotation = 0
                                target.flip_x = False
                                target.texture_tint = (255, 255, 255)
                                target.texture_scale = 1.0
                                continue
                            placed_trees.add((x, y))
                            self.apply_tree_variation(target, rng)
                            target.height = min(MAX_HEIGHT, target.height + rng.randint(2, 4))
                        else:
                            target.flip_x = False
                            target.texture_tint = (255, 255, 255)
                            target.texture_scale = 1.0

    def apply_tree_variation(self, tile: Tile, rng: random.Random) -> None:
        tile.flip_x = rng.random() < 0.5
        shade = rng.uniform(0.85, 1.15)
        tint_value = int(max(180, min(255, 255 * shade)))
        tile.texture_tint = (tint_value, tint_value, tint_value)
        tile.texture_scale = rng.uniform(0.85, 1.15)

    @staticmethod
    def is_tree_key(choice: str) -> bool:
        # Dynamic tree assets may not match a canonical TREE_TYPES key.
        # Treat anything containing "tree" as a tree (plus the known TREE_TYPES).
        lowered = (choice or "").lower()
        return (choice in TREE_TYPES) or ("tree" in lowered)

    def get_biome_tree_choices(self) -> List[str]:
        # Biome rule (requested):
        # - If the current biome replacement folder has at least one PNG whose filename includes "tree",
        #   those files become the tree options for scattering.
        # - If there are none, the biome is considered to have no trees.
        detected = getattr(self, "detected_tree_types", None)
        if isinstance(detected, list) and detected:
            return list(detected)
        return []

    def choose_object_for_tile(self, tile_type: str, rng: random.Random, tree_choices: List[str]) -> str:
        # If the biome has no detected tree assets, don't place trees at all.
        if not tree_choices:
            if tile_type == "sand":
                return rng.choice(["cactus", "grass_patch"])
            if tile_type == "swamp":
                return rng.choice(["reed", "bush"])
            if tile_type == "tundra":
                return rng.choice(["rock", "tall_grass"])
            if tile_type == "grass":
                return rng.choice(["bush", "tall_grass", "grass_patch"])
            if tile_type == "mud":
                return rng.choice(["grass_patch", "bush"])
            if tile_type == "stone":
                return "rock"
            return rng.choice(["bush", "grass_patch"])

        tree_choice = rng.choice(tree_choices)
        if tile_type == "sand":
            return rng.choices([tree_choice, "cactus", "grass_patch"], weights=[0.5, 0.3, 0.2], k=1)[0]
        if tile_type == "swamp":
            return rng.choices(["reed", "bush", tree_choice], weights=[0.5, 0.3, 0.2], k=1)[0]
        if tile_type == "tundra":
            return rng.choices([tree_choice, "rock", "tall_grass"], weights=[0.5, 0.3, 0.2], k=1)[0]
        if tile_type == "grass":
            return rng.choices(
                [tree_choice, "bush", "tall_grass", "grass_patch"],
                weights=[0.4, 0.2, 0.2, 0.2],
                k=1,
            )[0]
        if tile_type == "mud":
            return rng.choices(["grass_patch", "bush", tree_choice], weights=[0.4, 0.3, 0.3], k=1)[0]
        if tile_type == "stone":
            return rng.choices(["rock", tree_choice], weights=[0.7, 0.3], k=1)[0]
        return rng.choice([tree_choice, "bush", "grass_patch"])

    def scatter_animals(
        self,
        rng: random.Random,
        count_each: int = 2,
        animal_type: Optional[str] = None,
        clear_existing: bool = True,
    ) -> None:
        land_positions = [
            (x, y)
            for (x, y), tile in self.world.tiles.items()
            if tile.tile_type != "water"
        ]
        water_positions = [
            (x, y)
            for (x, y), tile in self.world.tiles.items()
            if tile.tile_type == "water"
        ]
        rng.shuffle(land_positions)
        rng.shuffle(water_positions)
        if clear_existing:
            self.animals.clear()
        animals = [animal_type] if animal_type else list(self.animal_tile_types)
        for animal in animals:
            for _ in range(count_each):
                positions = water_positions if animal == "fish" else land_positions
                if not positions:
                    break
                x, y = positions.pop()
                tile = self.world.get_tile(x, y)
                if tile is None:
                    continue
                self.animals.append(Animal(x=float(x), y=float(y), height=tile.height, animal_type=animal))

        self.spawn_sharks(rng, water_positions)

    def spawn_sharks(self, rng: random.Random, water_positions: List[Tuple[int, int]]) -> None:
        if not water_positions:
            return
        if rng.random() > 0.35:
            return
        count = rng.randint(1, 2)
        for _ in range(count):
            if not water_positions:
                break
            x, y = water_positions.pop()
            tile = self.world.get_tile(x, y)
            if tile is None:
                continue
            self.animals.append(Animal(x=float(x), y=float(y), height=tile.height, animal_type="shark"))

    def scatter_mobs(
        self,
        rng: random.Random,
        chance: float = 0.02,
        max_count: int = 5,
        mob_type: Optional[str] = None,
    ) -> None:
        positions = [
            (x, y)
            for (x, y), tile in self.world.tiles.items()
            if tile.tile_type != "water"
        ]
        rng.shuffle(positions)
        count = 0
        for x, y in positions:
            if count >= max_count:
                break
            if rng.random() > chance:
                continue
            tile = self.world.get_tile(x, y)
            if tile is None:
                continue
            spawn_type = mob_type or rng.choice(self.mob_tile_types)
            biome_base = self.mob_variant_base(tile.tile_type, rng)
            base = DEFAULT_COLORS.get(spawn_type, biome_base)
            tint = rng.randint(-30, 30)
            variant = (
                max(40, min(220, base[0] + tint)),
                max(40, min(220, base[1] + tint)),
                max(40, min(220, base[2] + tint)),
            )
            accent = (
                max(60, min(255, variant[0] + rng.randint(10, 40))),
                max(20, min(120, variant[1] - rng.randint(10, 40))),
                max(20, min(120, variant[2] - rng.randint(10, 40))),
            )
            self.mobs.append(
                Mob(
                    x=float(x),
                    y=float(y),
                    height=tile.height,
                    mob_type=spawn_type,
                    variant_color=variant,
                    accent_color=accent,
                )
            )
            count += 1

    def mob_variant_base(self, tile_type: str, rng: random.Random) -> Tuple[int, int, int]:
        biome_colors = {
            "sand": [(180, 120, 60), (140, 90, 50)],
            "swamp": [(60, 120, 70), (80, 140, 90)],
            "tundra": [(140, 150, 160), (120, 130, 150)],
            "ice": [(160, 190, 210), (130, 160, 190)],
            "mud": [(110, 80, 70), (90, 60, 50)],
            "stone": [(120, 120, 130), (100, 110, 120)],
            "ruins": [(130, 120, 110), (150, 130, 120)],
            "cavern": [(70, 70, 90), (60, 60, 80)],
            "hellstone": [(170, 60, 50), (140, 50, 40)],
        }
        choices = biome_colors.get(tile_type)
        if choices:
            return rng.choice(choices)
        return (140, 60, 60)

    def generate_animals(self) -> None:
        rng = random.Random(random.randint(0, 999999))
        count_each = max(4, (self.world.width * self.world.height) // 750)
        animal_type = None
        if self.current_biome:
            animal_type = self.current_biome.get("animal_type")
        self.scatter_animals(rng, count_each=count_each, animal_type=animal_type, clear_existing=True)
        if self.current_biome:
            extra_animals = self.current_biome.get("extra_animals", [])
            for extra in extra_animals:
                self.scatter_animals(
                    rng,
                    count_each=max(1, count_each // 4),
                    animal_type=extra,
                    clear_existing=False,
                )
        if self.current_biome and self.current_biome.get("civilian_count"):
            self.scatter_animals(
                rng,
                count_each=int(self.current_biome.get("civilian_count", 0)),
                animal_type="civilian",
                clear_existing=False,
            )

    def generate_mobs(self) -> None:
        rng = random.Random(random.randint(0, 999999))
        mob_type = None
        if self.current_biome:
            mob_type = self.current_biome.get("mob_type")
        self.scatter_mobs(rng, chance=0.5, max_count=5, mob_type=mob_type)

    def spawn_player(self) -> None:
        center_x = self.world.width // 2
        center_y = self.world.height // 2
        tile = self.world.get_tile(center_x, center_y)
        height = tile.height if tile else 0
        old = self.player
        inventory = old.inventory if old else {}
        weapons = list(old.weapons) if old else []
        bindings = dict(old.weapon_bindings) if old else {}
        equipped = old.equipped_weapon_id if old else None
        self.player = Player(
            x=float(center_x),
            y=float(center_y),
            height=height,
            inventory=inventory,
            weapons=weapons,
            weapon_bindings=bindings,
            equipped_weapon_id=equipped,
        )
        self.player.animation_time = 0.0
        self.player.velocity_x = 0.0
        self.player.velocity_y = 0.0
        self.player.health = max(1, self.player.health)
        # Starter weapon if needed
        if not self.player.weapons:
            starter = generate_weapon(self.world_seed ^ 0xA5A5A5, tier=1, biome=str(self.current_biome.get("name", "")))
            if starter is None:
                # Safety fallback: should never happen, but avoids a hard crash if weapon generation is modified.
                starter = {
                    "id": f"w{(self.world_seed ^ 0xA5A5A5) & 0xFFFFFFFF:08x}0000",
                    "type": "sword",
                    "rarity": "common",
                    "name_base": "Sword",
                    "name": "Starter Sword",
                    "behavior": "melee",
                    "stats": {"damage": 2, "range": 1.5, "cooldown": 0.55, "crit": 0.05},
                    "projectile": None,
                    "on_hit": None,
                    "uses_ammo": False,
                    "ammo_item": "ammo",
                    "ammo_max": 0,
                    "ammo": 0,
                    "sig": "sword|common|Starter Sword",
                }

            starter["rarity"] = "common"
            starter["name"] = "Starter Sword"
            starter["behavior"] = "melee"
            starter["type"] = "sword"
            starter["stats"]["range"] = 1.5
            self.player.weapons.append(starter)
            self.player.equipped_weapon_id = starter["id"]


    def update_player(self, dt: float, keys: pygame.key.ScancodeWrapper) -> None:
        if not self.player_mode or self.player is None:
            return
        player = self.player
        player.animation_time += dt
        player.step_sound_timer = max(0.0, player.step_sound_timer - dt)
        raw_move_x = (
            int(keys[pygame.K_d])
            - int(keys[pygame.K_a])
            + int(keys[pygame.K_RIGHT])
            - int(keys[pygame.K_LEFT])
        )
        raw_move_y = int(keys[pygame.K_s]) - int(keys[pygame.K_w])
        move_x = float(raw_move_x)
        move_y = float(raw_move_y)
        length = math.hypot(move_x, move_y)
        if length > 0:
            move_x /= length
            move_y /= length
            player.direction = (int(round(move_x)), int(round(move_y)))
        current_tile = self.world.get_tile(int(round(player.x)), int(round(player.y)))
        player.is_swimming = current_tile is not None and current_tile.tile_type == "water"
        player.step_timer = max(0.0, player.step_timer - dt)
        player.vertical_step_timer = max(0.0, player.vertical_step_timer - dt)
        if player.mode == "smooth":
            max_speed = player.swim_speed if player.is_swimming else player.speed
            accel = player.acceleration
            if length > 0:
                player.velocity_x += (move_x * max_speed - player.velocity_x) * min(1.0, accel * dt)
                player.velocity_y += (move_y * max_speed - player.velocity_y) * min(1.0, accel * dt)
            else:
                damping = max(0.0, 1 - dt * 6)
                player.velocity_x *= damping
                player.velocity_y *= damping
            target_x = player.x + player.velocity_x * dt
            target_y = player.y + player.velocity_y * dt
            self.try_move_player(target_x, target_y)
            if length > 0 and player.step_sound_timer <= 0 and self.audio:
                self.audio.play_at("footstep", (player.x, player.y), (player.x, player.y), 10, 0.6)
                player.step_sound_timer = 0.35
        else:
            player.velocity_x = 0.0
            player.velocity_y = 0.0
            step_x = 0 if raw_move_x == 0 else int(raw_move_x / abs(raw_move_x))
            step_y = 0 if raw_move_y == 0 else int(raw_move_y / abs(raw_move_y))
            if (step_x != 0 or step_y != 0) and player.step_timer <= 0:
                target_x = player.x + step_x
                target_y = player.y + step_y
                self.try_move_player(target_x, target_y)
                player.step_timer = player.step_delay
                if self.audio:
                    self.audio.play_at("footstep", (player.x, player.y), (player.x, player.y), 10, 0.6)
        current_tile = self.world.get_tile(int(round(player.x)), int(round(player.y)))
        if player.is_swimming and current_tile is not None:
            vertical_input = int(keys[pygame.K_UP]) - int(keys[pygame.K_DOWN])
            if vertical_input != 0 and player.vertical_step_timer <= 0:
                target_height = player.height + vertical_input
                if vertical_input > 0:
                    target_height = min(target_height, current_tile.height)
                player.height = max(MIN_HEIGHT, min(MAX_HEIGHT, target_height))
                player.vertical_step_timer = player.vertical_step_delay
            if player.height > current_tile.height:
                player.height = current_tile.height
        elif current_tile is not None:
            player.height = current_tile.height
        self.update_camera_follow()

    def update_layout(self) -> None:
        width, height = self.screen.get_size()
        self.ui_rect = pygame.Rect(width - 260, 10, 250, height - 20)
        self.settings_button_rect = pygame.Rect(10, 10, 110, 28)
        self.player_button_rect = pygame.Rect(10, 46, 110, 28)
        self.settings_panel_rect = pygame.Rect(10, 82, 340, 360)
        self.palette_panel_rect = pygame.Rect(10, 82, 320, 360)
        self.menu_panel_rect = pygame.Rect(130, 10, 260, height - 20)
        inv_w = min(700, max(460, int(width * 0.62)))
        inv_h = min(640, max(380, int(height * 0.72)))
        self.inventory_panel_rect = pygame.Rect((width - inv_w) // 2, (height - inv_h) // 2, inv_w, inv_h)

    def create_display(self, size: Tuple[int, int]) -> pygame.Surface:
        flags = pygame.RESIZABLE
        if self.fullscreen:
            flags |= pygame.FULLSCREEN
        vsync = 1 if self.settings.get("vsync", True) else 0
        try:
            return pygame.display.set_mode(size, flags, vsync=vsync)
        except TypeError:
            return pygame.display.set_mode(size, flags)

    def resize_screen(self, width: int, height: int) -> None:
        if width <= 0 or height <= 0:
            return
        target_width = width
        target_height = int(width * 9 / 16)
        if target_height > height:
            target_height = height
            target_width = int(height * 16 / 9)
        self.screen = self.create_display((target_width, target_height))
        self.renderer.screen = self.screen
        self._last_screen_size = self.screen.get_size()
        self._zoom_world_surface = None
        self._zoom_smooth_next = True
        self.update_layout()

    def toggle_fullscreen(self) -> None:
        self.fullscreen = not self.fullscreen
        size = self.screen.get_size()
        self.resize_screen(size[0], size[1])

    def toggle_zoom(self) -> None:
        self.zoom_index = (self.zoom_index + 1) % len(self.zoom_levels)
        self._zoom_smooth_next = True

    def adjust_mouse_for_zoom(self, mouse_pos: Tuple[int, int]) -> Optional[Tuple[int, int]]:
        zoom = self.zoom_levels[self.zoom_index]
        if zoom == 1.0:
            return mouse_pos
        width, height = self.screen.get_size()
        scaled_w = int(width * zoom)
        scaled_h = int(height * zoom)
        origin_x = (width - scaled_w) // 2
        origin_y = (height - scaled_h) // 2
        if mouse_pos[0] < origin_x or mouse_pos[0] > origin_x + scaled_w:
            return None
        if mouse_pos[1] < origin_y or mouse_pos[1] > origin_y + scaled_h:
            return None
        adjusted_x = int((mouse_pos[0] - origin_x) / zoom)
        adjusted_y = int((mouse_pos[1] - origin_y) / zoom)
        return adjusted_x, adjusted_y

    def update_day_cycle(self, dt: float) -> None:
        self.day_time = (self.day_time + dt * self.day_speed) % 1.0

    def update_water_physics(self, dt: float) -> None:
        self.water_timer += dt
        if self.water_timer < 0.4:
            return
        self.water_timer = 0.0
        # Some biomes intentionally have no oceans.
        if self.generation_params.get("no_ocean"):
            return
        water_tiles = [
            (x, y, tile)
            for (x, y), tile in self.world.tiles.items()
            if tile.tile_type == "water"
        ]
        if not water_tiles:
            return
        rng = random.Random(self.world_seed + int(self.day_time * 1000))
        rng.shuffle(water_tiles)
        water_level = int(self.generation_params.get("water_level", -1))
        # Hard clamp so a bad/sentinel value can't drive water far below the
        # rest of the terrain (the "giant pillar" look).
        water_level = max(MIN_WATER_LEVEL, min(MAX_HEIGHT, water_level))
        wave_time = pygame.time.get_ticks() / 1000.0
        for x, y, tile in water_tiles[:120]:
            wave_phase = (x + y) * 0.15 - wave_time * 2.2
            if math.sin(wave_phase) > 0.6:
                tile.height = water_level + 1
            else:
                tile.height = water_level
            neighbors = [
                (x - 1, y),
                (x + 1, y),
                (x, y - 1),
                (x, y + 1),
            ]
            rng.shuffle(neighbors)
            for nx, ny in neighbors:
                if not self.world.in_bounds(nx, ny):
                    continue
                neighbor = self.world.get_tile(nx, ny)
                if neighbor is None:
                    continue
                if neighbor.height < tile.height - 1 and neighbor.tile_type != "water":
                    neighbor.tile_type = "water"
                    neighbor.height = max(MIN_HEIGHT, max(tile.height - 1, water_level))
                    break

    def get_daylight(self) -> float:
        if not self.settings.get("day_night_cycle", True):
            return 1.0
        t = self.day_time * 2 * math.pi
        raw_daylight = (math.sin(t - math.pi / 2) + 1) / 2
        daylight = raw_daylight * raw_daylight * (3 - 2 * raw_daylight)
        return daylight

    def draw_sky(self) -> None:
        daylight = self.get_daylight()
        sky_r = int(30 + daylight * 90)
        sky_g = int(50 + daylight * 130)
        sky_b = int(80 + daylight * 150)
        self.screen.fill((sky_r, sky_g, sky_b))
        self.draw_stars(daylight)

    def draw_stars(self, daylight: float) -> None:
        if not self.settings.get("show_stars", True):
            return
        if daylight > 0.6:
            return
        alpha = int((1 - daylight) * 200)
        for x, y, size in self.star_positions:
            color = (220, 220, 255, alpha)
            star = pygame.Surface((size, size), pygame.SRCALPHA)
            star.fill(color)
            self.screen.blit(star, (x, y))

    def apply_day_night_overlay(self) -> None:
        if not self.settings.get("day_night_cycle", True):
            return
        daylight = self.get_daylight()
        dusk_factor = max(0.0, 1 - abs(daylight - 0.5) * 4)
        night_alpha = int((1 - daylight) * 180)
        dusk_alpha = int(dusk_factor * 90)
        overlay = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
        if night_alpha > 0:
            overlay.fill((20, 30, 60, night_alpha))
        if dusk_alpha > 0:
            overlay.fill((200, 120, 80, dusk_alpha), special_flags=pygame.BLEND_RGBA_ADD)
        self.screen.blit(overlay, (0, 0))

    def get_biome_weather_options(self) -> List[str]:
        biome_name = ""
        if self.current_biome:
            biome_name = self.current_biome.get("name", "")
        biome_weather = {
            "tundras": ["snow", "wind", "clear"],
            "frostbound": ["snow", "wind", "clear"],
            "highlands": ["snow", "wind", "clear"],
            "swamps": ["fog", "rain", "clear"],
            "wetlands": ["fog", "rain", "clear"],
            "marsh": ["fog", "rain", "clear"],
            "jungles": ["rain", "storm", "fog", "clear"],
            "rain_forests": ["rain", "storm", "fog", "clear"],
            "rainforest": ["rain", "storm", "fog", "clear"],
            "tropical_jungle": ["rain", "storm", "clear"],
            "coastal": ["rain", "wind", "clear"],
            "tropical_islands": ["rain", "wind", "clear"],
            "island_flats": ["rain", "wind", "clear"],
            "island_mountains": ["wind", "rain", "clear"],
            "island_cliffs": ["wind", "clear"],
            "drylands": ["dust", "wind", "clear"],
            "arid": ["dust", "wind", "clear"],
            "pyramid_deserts": ["dust", "wind", "clear"],
            "monument_valleys": ["dust", "wind", "clear"],
            "savanna": ["wind", "rain", "clear"],
            "ghost_towns": ["fog", "wind", "clear"],
            "candyland": ["wind", "rain", "clear"],
            "hellish": ["wind", "dust", "clear"],
            "moonscape": ["wind", "clear"],
        }
        return biome_weather.get(biome_name, ["rain", "wind", "clear"])

    def roll_weather(self, options: List[str]) -> str:
        choices: List[Tuple[str, float]] = [("clear", 4.0)]
        weights = {
            "rain": 1.4,
            "storm": 0.6,
            "snow": 1.2,
            "dust": 1.0,
            "fog": 0.9,
            "wind": 0.8,
        }
        for option in options:
            if option == "clear":
                continue
            choices.append((option, weights.get(option, 1.0)))
        total = sum(weight for _, weight in choices)
        pick = random.random() * total
        running = 0.0
        for weather, weight in choices:
            running += weight
            if pick <= running:
                return weather
        return "clear"

    def update_weather(self, dt: float) -> None:
        self.weather_timer = max(0.0, self.weather_timer - dt)
        if self.weather_timer <= 0.0:
            options = self.get_biome_weather_options()
            self.weather_type = self.roll_weather(options)
            self.weather_particles.clear()
            self.fog_offset = 0.0
            self.lightning_flash = 0.0
        if self.weather_type == "clear":
            self.weather_duration = random.uniform(24, 48)
        else:
            self.weather_duration = random.uniform(10, 20)
        self.weather_timer = self.weather_duration
        width, height = self.screen.get_size()
        if self.weather_type == "rain":
            spawn = int(140 * dt)
            for _ in range(spawn):
                self.weather_particles.append(
                    {
                        "x": random.uniform(0, width),
                        "y": random.uniform(-40, 0),
                        "vy": random.uniform(380, 520),
                    }
                )
            for particle in list(self.weather_particles):
                particle["y"] += particle["vy"] * dt
                if particle["y"] > height + 20:
                    self.weather_particles.remove(particle)
        elif self.weather_type == "storm":
            spawn = int(200 * dt)
            for _ in range(spawn):
                self.weather_particles.append(
                    {
                        "x": random.uniform(0, width),
                        "y": random.uniform(-40, 0),
                        "vy": random.uniform(520, 760),
                    }
                )
            for particle in list(self.weather_particles):
                particle["y"] += particle["vy"] * dt
                if particle["y"] > height + 20:
                    self.weather_particles.remove(particle)
            if random.random() < 0.015:
                self.lightning_flash = 0.2
        elif self.weather_type == "snow":
            spawn = int(120 * dt)
            for _ in range(spawn):
                self.weather_particles.append(
                    {
                        "x": random.uniform(0, width),
                        "y": random.uniform(-20, 0),
                        "vy": random.uniform(40, 80),
                        "vx": random.uniform(-20, 20),
                    }
                )
            for particle in list(self.weather_particles):
                particle["x"] += particle["vx"] * dt
                particle["y"] += particle["vy"] * dt
                if particle["y"] > height + 20:
                    self.weather_particles.remove(particle)
        elif self.weather_type == "dust":
            spawn = int(90 * dt)
            for _ in range(spawn):
                self.weather_particles.append(
                    {
                        "x": random.uniform(-20, width),
                        "y": random.uniform(0, height),
                        "vx": random.uniform(50, 90),
                        "vy": random.uniform(-10, 10),
                    }
                )
            for particle in list(self.weather_particles):
                particle["x"] += particle["vx"] * dt
                particle["y"] += particle["vy"] * dt
                if particle["x"] > width + 20:
                    self.weather_particles.remove(particle)
        elif self.weather_type == "wind":
            spawn = int(80 * dt)
            for _ in range(spawn):
                self.weather_particles.append(
                    {
                        "x": random.uniform(-40, width),
                        "y": random.uniform(0, height),
                        "vx": random.uniform(120, 180),
                        "vy": random.uniform(-30, 30),
                    }
                )
            for particle in list(self.weather_particles):
                particle["x"] += particle["vx"] * dt
                particle["y"] += particle["vy"] * dt
                if particle["x"] > width + 40:
                    self.weather_particles.remove(particle)
        elif self.weather_type == "fog":
            self.fog_offset = (self.fog_offset + dt * 12) % width
        if self.lightning_flash > 0.0:
            self.lightning_flash = max(0.0, self.lightning_flash - dt * 1.2)

    def draw_weather(self) -> None:
        if self.weather_type == "rain":
            overlay = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
            for particle in self.weather_particles:
                start = (int(particle["x"]), int(particle["y"]))
                end = (int(particle["x"] + 2), int(particle["y"] + 10))
                pygame.draw.line(overlay, (170, 200, 220, 110), start, end, 1)
            self.screen.blit(overlay, (0, 0))
        elif self.weather_type == "storm":
            overlay = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
            for particle in self.weather_particles:
                start = (int(particle["x"]), int(particle["y"]))
                end = (int(particle["x"] + 3), int(particle["y"] + 14))
                pygame.draw.line(overlay, (150, 180, 210, 140), start, end, 1)
            self.screen.blit(overlay, (0, 0))
            if self.lightning_flash > 0:
                flash = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
                alpha = int(120 * min(1.0, self.lightning_flash * 3))
                flash.fill((220, 220, 255, alpha))
                self.screen.blit(flash, (0, 0))
        elif self.weather_type == "snow":
            for particle in self.weather_particles:
                pygame.draw.circle(self.screen, (230, 230, 240), (int(particle["x"]), int(particle["y"])), 2)
        elif self.weather_type == "dust":
            for particle in self.weather_particles:
                pygame.draw.line(
                    self.screen,
                    (180, 150, 110),
                    (int(particle["x"]), int(particle["y"])),
                    (int(particle["x"] + 6), int(particle["y"] - 2)),
                    1,
                )
        elif self.weather_type == "wind":
            for particle in self.weather_particles:
                pygame.draw.line(
                    self.screen,
                    (200, 210, 220),
                    (int(particle["x"]), int(particle["y"])),
                    (int(particle["x"] + 12), int(particle["y"] - 2)),
                    1,
                )
        elif self.weather_type == "fog":
            overlay = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
            fog_color = (80, 90, 80)
            biome = getattr(self, "current_biome", None)
            if biome:
                fog_color = biome.get("fog_color", fog_color)
            overlay.fill((*fog_color, 70))
            self.screen.blit(overlay, (0, 0))

    def spawn_mob_at(self, x: int, y: int, mob_type: str) -> None:
        tile = self.world.get_tile(x, y)
        if tile is None:
            return
        biome_base = self.mob_variant_base(tile.tile_type, random.Random(x * 31 + y * 17))
        base = DEFAULT_COLORS.get(mob_type, biome_base)
        tint = random.randint(-30, 30)
        variant = (
            max(40, min(220, base[0] + tint)),
            max(40, min(220, base[1] + tint)),
            max(40, min(220, base[2] + tint)),
        )
        accent = (
            max(60, min(255, variant[0] + random.randint(10, 40))),
            max(20, min(120, variant[1] - random.randint(10, 40))),
            max(20, min(120, variant[2] - random.randint(10, 40))),
        )
        self.mobs.append(
            Mob(
                x=float(x),
                y=float(y),
                height=tile.height,
                mob_type=mob_type,
                variant_color=variant,
                accent_color=accent,
            )
        )

    def spawn_alien_invasion(self) -> None:
        positions = [
            (x, y)
            for (x, y), tile in self.world.tiles.items()
            if tile.tile_type != "water"
        ]
        if not positions:
            return
        random.shuffle(positions)
        count = min(len(positions), random.randint(6, 10))
        for _ in range(count):
            x, y = positions.pop()
            self.spawn_mob_at(x, y, "alien")
        self.invasion_notice_timer = 6.0

    def update_invasions(self, dt: float) -> None:
        self.invasion_timer = max(0.0, self.invasion_timer - dt)
        self.invasion_notice_timer = max(0.0, self.invasion_notice_timer - dt)
        if self.invasion_timer <= 0.0:
            self.spawn_alien_invasion()
            self.invasion_timer = random.uniform(90.0, 150.0)

    def update_audio_ambient(self, dt: float) -> None:
        if not self.player or not self.audio:
            return
        for key in self.audio_cooldowns:
            self.audio_cooldowns[key] = max(0.0, self.audio_cooldowns[key] - dt)
        if self.audio_cooldowns["water"] <= 0:
            tile = self.world.get_tile(int(round(self.player.x)), int(round(self.player.y)))
            if tile and tile.tile_type == "water":
                self.audio.play_at("water", (self.player.x, self.player.y), (self.player.x, self.player.y), 18, 0.5)
                self.audio_cooldowns["water"] = 5.0
        if self.audio_cooldowns["ambient"] <= 0:
            self.audio.play_at("monster", (self.player.x + 8, self.player.y + 6), (self.player.x, self.player.y), 20, 0.2)
            self.audio_cooldowns["ambient"] = random.uniform(12.0, 20.0)

    def update_mobs(self, dt: float) -> None:
        if self.player is None:
            return
        player = self.player
        player.attack_timer = max(0.0, player.attack_timer - dt)
        self.manual_target_timer = max(0.0, self.manual_target_timer - dt)
        if self.manual_target_timer <= 0.0:
            self.manual_target = None
        elif self.manual_target is not None and self.manual_target not in self.mobs:
            self.manual_target = None
            self.manual_target_timer = 0.0
        for mob in list(self.mobs):
            mob.attack_cooldown = max(0.0, mob.attack_cooldown - dt)
            mob.wander_timer = max(0.0, mob.wander_timer - dt)
            mob.animation_time += dt
            mob.aggression = max(0.0, mob.aggression - dt * 0.2)
            dx = player.x - mob.x
            dy = player.y - mob.y
            distance = math.hypot(dx, dy)
            if distance <= 10 or mob.aggression > 0.3:
                if distance > 1:
                    aggression_boost = 1.0 + min(1.5, mob.aggression * 0.4)
                    step_x = dx / max(distance, 0.001) * dt * 1.4 * aggression_boost
                    step_y = dy / max(distance, 0.001) * dt * 1.4 * aggression_boost
                    mob.x += step_x
                    mob.y += step_y
                    mob.direction = (step_x, step_y)
                    tile = self.world.get_tile(int(round(mob.x)), int(round(mob.y)))
                    if tile is not None:
                        mob.height = tile.height
                if distance <= 1.2 and mob.attack_cooldown <= 0:
                    player.health = max(0, player.health - 1)
                    mob.attack_cooldown = 1.0
                    if self.audio:
                        self.audio.play_at("attack", (mob.x, mob.y), (player.x, player.y), 12, 0.8)
            else:
                if mob.wander_timer <= 0:
                    mob.direction = (
                        random.uniform(-1.0, 1.0),
                        random.uniform(-1.0, 1.0),
                    )
                    mob.wander_timer = random.uniform(1.2, 2.5)
                self.try_move_creature(mob, mob.direction[0] * dt, mob.direction[1] * dt, avoid_water=True)
            weapon = self.get_equipped_weapon()
            attack_range = 1.5
            if weapon is not None:
                try:
                    attack_range = float(weapon.get("stats", {}).get("range", attack_range))
                except Exception:
                    attack_range = 1.5
            if distance <= attack_range and player.health > 0 and player.attack_timer <= 0:
                self.player_attack(mob)
                mob.aggression = min(3.0, mob.aggression + 1.0)
            if mob.health <= 0:
                self.death_effects.append(
                    {
                        "x": mob.x,
                        "y": mob.y,
                        "height": mob.height,
                        "timer": 0.6,
                        "duration": 0.6,
                    }
                )
                self.drop_loot(mob.x, mob.y, mob.mob_type)
                player.health += 1
                self.mobs.remove(mob)

    def update_animals(self, dt: float) -> None:
        for animal in self.animals:
            animal.hunger = min(10.0, animal.hunger + dt * 0.2)
            animal.wander_timer = max(0.0, animal.wander_timer - dt)
            animal.animation_time += dt
            animal.sound_timer = max(0.0, animal.sound_timer - dt)
            tile = self.world.get_tile(int(round(animal.x)), int(round(animal.y)))
            prefers_water = animal.animal_type in {"fish", "shark"}
            if tile:
                delta = 0.15 if tile.tile_type == "water" and prefers_water else 0.1
                if tile.tile_type == "water" and not prefers_water:
                    delta = -0.2
                if tile.tile_type != "water" and prefers_water:
                    delta = -0.15
                current = animal.terrain_affinity.get(tile.tile_type, 0.0)
                animal.terrain_affinity[tile.tile_type] = max(-1.0, min(2.0, current + delta))
            if animal.wander_timer <= 0:
                best_score = -999.0
                best_dir = (random.uniform(-1.0, 1.0), random.uniform(-1.0, 1.0))
                for _ in range(5):
                    cand = (random.uniform(-1.0, 1.0), random.uniform(-1.0, 1.0))
                    probe_x = int(round(animal.x + cand[0]))
                    probe_y = int(round(animal.y + cand[1]))
                    probe_tile = self.world.get_tile(probe_x, probe_y)
                    if probe_tile is None:
                        continue
                    affinity = animal.terrain_affinity.get(probe_tile.tile_type, 0.0)
                    score = affinity + random.uniform(-0.2, 0.2)
                    if score > best_score:
                        best_score = score
                        best_dir = cand
                animal.direction = best_dir
                animal.wander_timer = random.uniform(1.5, 3.0)
            speed = {
                "rabbit": 0.7,
                "bird": 0.9,
                "horse": 0.6,
                "cow": 0.45,
                "boar": 0.5,
                "deer": 0.6,
                "elephant": 0.3,
                "shark": 0.7,
                "fish": 0.5,
            }.get(animal.animal_type, 0.4)
            dx = animal.direction[0] * dt * speed
            dy = animal.direction[1] * dt * speed
            if self.player and animal.sound_timer <= 0:
                sound_type = "bird" if animal.animal_type == "bird" else "animal"
                self.audio.play_at(
                    sound_type,
                    (animal.x, animal.y),
                    (self.player.x, self.player.y),
                    14,
                    0.4,
                )
                animal.sound_timer = random.uniform(6.0, 12.0)
            if animal.animal_type == "bird":
                self.try_move_creature(animal, dx, dy, avoid_water=False, require_water=False)
                continue
            if animal.animal_type == "shark" and self.player is not None:
                player = self.player
                if player.is_swimming:
                    chase_dx = player.x - animal.x
                    chase_dy = player.y - animal.y
                    dist = math.hypot(chase_dx, chase_dy)
                    if dist > 0.2:
                        steer_x = chase_dx / dist * dt * 1.1
                        steer_y = chase_dy / dist * dt * 1.1
                        self.try_move_creature(animal, steer_x, steer_y, avoid_water=False, require_water=True)
                    if dist <= 1.1:
                        player.health = max(0, player.health - 1)
                continue
            avoid_water = animal.animal_type != "fish"
            self.try_move_creature(animal, dx, dy, avoid_water=avoid_water, require_water=not avoid_water)

    def update_loot(self) -> None:
        if self.player is None:
            return
        player = self.player
        for loot in list(self.loot):
            lx, ly, item = loot
            if math.hypot(player.x - lx, player.y - ly) <= 1.2:
                if isinstance(item, dict) and item.get("id", "").startswith("w"):
                    self.add_weapon_to_inventory(item)
                else:
                    self.add_inventory_item(str(item))
                self.loot.remove(loot)


    def update_death_effects(self, dt: float) -> None:
        for effect in list(self.death_effects):
            effect["timer"] = max(0.0, effect["timer"] - dt)
            if effect["timer"] <= 0:
                self.death_effects.remove(effect)

    def draw_death_effects(self) -> None:
        if not self.death_effects:
            return
        overlay = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
        for effect in self.death_effects:
            progress = 1 - (effect["timer"] / max(0.01, effect["duration"]))
            radius = int(6 + progress * 10)
            alpha = int(200 * (1 - progress))
            screen_x, screen_y = self.renderer.iso_to_screen(
                int(round(effect["x"])),
                int(round(effect["y"])),
                int(effect["height"]),
                self.offset,
            )
            center = (screen_x + TILE_WIDTH // 2, screen_y + TILE_HEIGHT // 2)
            pygame.draw.circle(overlay, (220, 80, 80, alpha), center, radius, 2)
        self.screen.blit(overlay, (0, 0))

    def drop_loot(self, x: float, y: float, mob_type: str) -> None:
        choices = LOOT_TABLE.get(mob_type, [])
        # Regular material drop
        if choices and random.random() < 0.8:
            item = random.choice(choices)
            self.loot.append((x, y, item))
        # Weapon drops (gameplay-focused)
        # Regular mobs: always drop a melee weapon.
        # Alien invasions: drop special ammo-based energy weapons + extra ammo.
        try:
            mob_tier_map = {
                "slime": 1, "goblin": 1, "bandit": 2, "wolf": 2,
                "beetle": 2, "mummy": 2, "harpy": 3, "serpent": 3,
                "wisp": 3, "phantom": 3, "specter": 4, "crawler": 4,
                "mutant": 4, "demon": 5, "stalker": 5, "guardian": 6,
                "android": 6, "alien": 6, "gummy": 3, "golem": 4,
            }
            tier = int(mob_tier_map.get(mob_type, 2))
        except Exception:
            tier = 2
        tier = max(1, min(6, tier))
        biome_name = ""
        try:
            biome_name = str(self.current_biome.get("name", ""))
        except Exception:
            biome_name = ""

        seed = (self.world_seed * 92821) ^ (int(x * 997) << 4) ^ (int(y * 911) << 2) ^ random.randrange(0, 1 << 20)

        if mob_type == "alien":
            weapon = generate_alien_weapon(seed, tier)
            self.loot.append((x, y, weapon))
            # Extra ammo drops so the invasion feels rewarding.
            self.loot.append((x + random.uniform(-0.2, 0.2), y + random.uniform(-0.2, 0.2), "ammo"))
            if random.random() < 0.55:
                self.loot.append((x + random.uniform(-0.3, 0.3), y + random.uniform(-0.3, 0.3), "ammo"))
        else:
            weapon = generate_weapon(seed, tier, biome_name, allowed_types=MELEE_WEAPON_TYPES)
            self.loot.append((x, y, weapon))


    def draw_mobs(self) -> None:
        screen_w, screen_h = self.screen.get_size()
        margin = 80
        for mob in self.mobs:
            screen_x, screen_y = self.renderer.iso_to_screen(
                int(round(mob.x)),
                int(round(mob.y)),
                mob.height,
                self.offset,
            )
            if screen_x < -margin or screen_x > screen_w + margin or screen_y < -margin or screen_y > screen_h + margin:
                continue
            center = (screen_x + TILE_WIDTH // 2, screen_y + TILE_HEIGHT // 2)
            body = mob.variant_color
            accent = mob.accent_color
            outline = (15, 10, 15)
            sway = math.sin(mob.animation_time * 6) * 2
            torso = pygame.Rect(center[0] - 4, center[1] - 6, 8, 10)
            head = pygame.Rect(center[0] - 3, center[1] - 13, 6, 6)
            left_arm = pygame.Rect(center[0] - 7, center[1] - 6, 3, 8).move(0, int(sway))
            right_arm = pygame.Rect(center[0] + 4, center[1] - 6, 3, 8).move(0, int(-sway))
            left_leg = pygame.Rect(center[0] - 4, center[1] + 4, 3, 6).move(0, int(-sway))
            right_leg = pygame.Rect(center[0] + 1, center[1] + 4, 3, 6).move(0, int(sway))
            for rect in [head, torso, left_arm, right_arm, left_leg, right_leg]:
                pygame.draw.rect(self.screen, outline, rect.inflate(2, 2))
                pygame.draw.rect(self.screen, body, rect)
            pygame.draw.rect(self.screen, accent, pygame.Rect(center[0] - 2, center[1] - 12, 2, 2))
            pygame.draw.rect(self.screen, accent, pygame.Rect(center[0] + 1, center[1] - 12, 2, 2))
            pygame.draw.polygon(
                self.screen,
                accent,
                [
                    (center[0] - 2, center[1] - 14),
                    (center[0] - 6, center[1] - 18),
                    (center[0] - 1, center[1] - 16),
                ],
            )
            pygame.draw.polygon(
                self.screen,
                accent,
                [
                    (center[0] + 2, center[1] - 14),
                    (center[0] + 6, center[1] - 18),
                    (center[0] + 1, center[1] - 16),
                ],
            )

    def draw_animals(self) -> None:
        screen_w, screen_h = self.screen.get_size()
        margin = 80
        for animal in self.animals:
            screen_x, screen_y = self.renderer.iso_to_screen(
                int(round(animal.x)),
                int(round(animal.y)),
                animal.height,
                self.offset,
            )
            if screen_x < -margin or screen_x > screen_w + margin or screen_y < -margin or screen_y > screen_h + margin:
                continue
            center = (screen_x + TILE_WIDTH // 2, screen_y + TILE_HEIGHT // 2)
            base_color = DEFAULT_COLORS.get(animal.animal_type, (180, 180, 180))
            accent = tuple(min(255, int(c + 30)) for c in base_color)
            outline = (20, 20, 30)
            scale = {
                "elephant": 2.0,
                "horse": 1.4,
                "cow": 1.4,
                "deer": 1.3,
                "boar": 1.25,
                "goat": 1.2,
                "shark": 1.5,
            }.get(animal.animal_type, 1.0)
            bob = math.sin(animal.animation_time * 5) * 2
            step = math.sin(animal.animation_time * 7) * 2
            shadow_rect = pygame.Rect(
                center[0] - int(6 * scale),
                center[1] + int(6 * scale),
                int(12 * scale),
                int(5 * scale),
            )
            pygame.draw.ellipse(self.screen, (20, 20, 30), shadow_rect)
            if animal.animal_type == "bird":
                flight = math.sin(animal.animation_time * 6) * 6 - 10
                screen_y += int(flight)
                center = (screen_x + TILE_WIDTH // 2, screen_y + TILE_HEIGHT // 2)
                wing_span = int(8 * scale)
                body = pygame.Rect(center[0] - 3, center[1] - 2, 6, 4)
                pygame.draw.ellipse(self.screen, base_color, body)
                pygame.draw.polygon(
                    self.screen,
                    accent,
                    [
                        (center[0], center[1]),
                        (center[0] - wing_span, center[1] - int(4 + step)),
                        (center[0] - 2, center[1] - 1),
                    ],
                )
                pygame.draw.polygon(
                    self.screen,
                    accent,
                    [
                        (center[0], center[1]),
                        (center[0] + wing_span, center[1] - int(4 - step)),
                        (center[0] + 2, center[1] - 1),
                    ],
                )
                pygame.draw.circle(self.screen, outline, (center[0] + 2, center[1] - 1), 1)
                continue
            if animal.animal_type in {"fish", "shark"}:
                body = pygame.Rect(center[0] - int(7 * scale), center[1] - int(3 * scale), int(14 * scale), int(6 * scale))
                pygame.draw.ellipse(self.screen, base_color, body)
                tail = [
                    (body.left, body.centery),
                    (body.left - int(6 * scale), body.centery - int(3 * scale)),
                    (body.left - int(6 * scale), body.centery + int(3 * scale)),
                ]
                pygame.draw.polygon(self.screen, base_color, tail)
                fin = [
                    (body.centerx, body.top),
                    (body.centerx - int(2 * scale), body.top - int(4 * scale)),
                    (body.centerx + int(2 * scale), body.top - int(3 * scale)),
                ]
                pygame.draw.polygon(self.screen, accent, fin)
                pygame.draw.circle(self.screen, outline, (body.right - int(2 * scale), body.centery - int(1 * scale)), 1)
                continue
            if animal.animal_type == "elephant":
                body = pygame.Rect(
                    center[0] - int(12 * scale),
                    center[1] - int(6 * scale + bob * 0.2),
                    int(24 * scale),
                    int(12 * scale),
                )
                head = pygame.Rect(
                    body.right - int(8 * scale),
                    body.top + int(2 * scale),
                    int(10 * scale),
                    int(8 * scale),
                )
                ear = pygame.Rect(
                    body.right - int(14 * scale),
                    body.top + int(1 * scale),
                    int(8 * scale),
                    int(8 * scale),
                )
                pygame.draw.ellipse(self.screen, outline, body.inflate(2, 2))
                pygame.draw.ellipse(self.screen, base_color, body)
                pygame.draw.ellipse(self.screen, accent, ear)
                pygame.draw.ellipse(self.screen, base_color, head)
                trunk = [
                    (head.right - int(2 * scale), head.bottom - int(2 * scale)),
                    (head.right + int(4 * scale), head.bottom + int(4 * scale)),
                    (head.right + int(2 * scale), head.bottom + int(6 * scale)),
                    (head.right - int(2 * scale), head.bottom + int(2 * scale)),
                ]
                pygame.draw.polygon(self.screen, base_color, trunk)
                tusk = [
                    (head.right, head.centery),
                    (head.right + int(4 * scale), head.centery + int(2 * scale)),
                    (head.right + int(2 * scale), head.centery + int(3 * scale)),
                ]
                pygame.draw.polygon(self.screen, (220, 210, 200), tusk)
                leg_offset = int(4 * scale)
                for lx in (-leg_offset, 0, leg_offset):
                    leg = pygame.Rect(center[0] + lx, body.bottom - int(2 * scale), int(3 * scale), int(6 * scale))
                    pygame.draw.rect(self.screen, base_color, leg)
                pygame.draw.circle(self.screen, outline, (head.right - int(1 * scale), head.centery), 1)
                continue
            body_rect = pygame.Rect(
                center[0] - int(7 * scale),
                center[1] - int(3 * scale + bob * 0.2),
                int(14 * scale),
                int(7 * scale),
            )
            head_rect = pygame.Rect(
                center[0] + int(4 * scale),
                center[1] - int(5 * scale + bob * 0.2),
                int(5 * scale),
                int(5 * scale),
            )
            pygame.draw.ellipse(self.screen, outline, body_rect.inflate(2, 2))
            pygame.draw.ellipse(self.screen, base_color, body_rect)
            pygame.draw.ellipse(self.screen, base_color, head_rect)
            for leg_dx in (-int(4 * scale), 0, int(3 * scale)):
                leg = pygame.Rect(
                    center[0] + leg_dx,
                    center[1] + int(2 * scale + (step if leg_dx == 0 else -step) * 0.2),
                    int(3 * scale),
                    int(5 * scale),
                )
                pygame.draw.rect(self.screen, base_color, leg)
            pygame.draw.circle(self.screen, outline, (head_rect.centerx + 1, head_rect.centery - 1), 1)

    def draw_loot(self) -> None:
        for lx, ly, item in self.loot:
            tile = self.world.get_tile(int(round(lx)), int(round(ly)))
            if tile is None:
                continue
            screen_x, screen_y = self.renderer.iso_to_screen(
                int(round(lx)),
                int(round(ly)),
                tile.height,
                self.offset,
            )
            center = (screen_x + TILE_WIDTH // 2, screen_y + TILE_HEIGHT // 2)
            if isinstance(item, dict) and item.get("id", "").startswith("w"):
                rarity = item.get("rarity", "common")
                color = WEAPON_RARITY_COLORS.get(rarity, (220, 220, 220))
                pygame.draw.circle(self.screen, (10, 10, 18), center, 7)
                pygame.draw.circle(self.screen, color, center, 6, 2)
                pygame.draw.rect(self.screen, color, pygame.Rect(center[0] - 3, center[1] - 3, 6, 6))
            else:
                color = ITEM_COLORS.get(str(item), (200, 200, 200))
                pygame.draw.circle(self.screen, (20, 20, 30), center, 3)
                pygame.draw.circle(self.screen, color, center, 2)


    def try_move_player(self, target_x: float, target_y: float) -> None:
        if self.player is None:
            return
        next_x = int(round(target_x))
        next_y = int(round(target_y))
        if not self.world.in_bounds(next_x, next_y):
            direction = (
                -1 if next_x < 0 else (1 if next_x >= self.world.width else 0),
                -1 if next_y < 0 else (1 if next_y >= self.world.height else 0),
            )
            self.handle_world_edge_transition(direction)
            return
        next_tile = self.world.get_tile(next_x, next_y)
        current_tile = self.world.get_tile(int(round(self.player.x)), int(round(self.player.y)))
        next_height = next_tile.height if next_tile else 0
        self.player.x = target_x
        self.player.y = target_y
        self.player.height = next_height

    def should_render_tile(self, tile: Tile) -> bool:
        if not self.player_mode or self.player is None:
            return True
        if self.player.height < -1 or self.player.is_swimming:
            depth = int(self.settings.get("subsurface_depth", 6))
            depth += int(abs(self.player.height) * 0.5)
            if self.player.is_swimming:
                depth += 10
            return tile.height <= self.player.height + depth
        return True

    def handle_world_edge_transition(self, direction: Tuple[int, int]) -> None:
        if self.player is None:
            return
        new_size = 100
        self.world = World(width=new_size, height=new_size)
        self.world_seed = random.randint(0, 999999)
        self.generation_params = self.build_generation_params(self.world_seed)
        self.current_biome = self.generation_params.get("biome", getattr(self, "current_biome", BIOME_PRESETS[0]))
        self.generate_world(keep_seed=True)
        if self.player is None:
            return
        fallback_x = int(round(self.player.x))
        fallback_y = int(round(self.player.y))
        fallback_x = max(1, min(new_size - 2, fallback_x))
        fallback_y = max(1, min(new_size - 2, fallback_y))
        if direction[0] < 0:
            new_x = new_size - 2
        elif direction[0] > 0:
            new_x = 1
        else:
            new_x = fallback_x
        if direction[1] < 0:
            new_y = new_size - 2
        elif direction[1] > 0:
            new_y = 1
        else:
            new_y = fallback_y
        tile = self.world.get_tile(new_x, new_y)
        self.player.x = float(new_x)
        self.player.y = float(new_y)
        self.player.height = tile.height if tile else 0
        self.player.direction = direction
        self.update_camera_follow()

    def try_move_creature(
        self,
        creature: object,
        dx: float,
        dy: float,
        avoid_water: bool = False,
        require_water: bool = False,
    ) -> None:
        target_x = creature.x + dx
        target_y = creature.y + dy
        next_x = int(round(target_x))
        next_y = int(round(target_y))
        if not self.world.in_bounds(next_x, next_y):
            return
        next_tile = self.world.get_tile(next_x, next_y)
        current_tile = self.world.get_tile(int(round(creature.x)), int(round(creature.y)))
        next_height = next_tile.height if next_tile else 0
        current_height = current_tile.height if current_tile else 0
        if next_height - current_height > 1:
            return
        if next_tile is None:
            return
        if avoid_water and next_tile.tile_type == "water":
            return
        if require_water and next_tile.tile_type != "water":
            return
        creature.x = target_x
        creature.y = target_y
        creature.height = next_height


    def update_camera_follow(self) -> None:
        if not self.player_mode or self.player is None:
            return
        center_x = self.screen.get_width() // 2
        center_y = self.screen.get_height() // 2
        iso_x = (self.player.x - self.player.y) * (TILE_WIDTH // 2)
        iso_y = (self.player.x + self.player.y) * (TILE_HEIGHT // 2) - self.player.height * CUBE_HEIGHT
        self.offset = (center_x - int(iso_x), center_y - int(iso_y))

    def jump_player(self, override_direction: Optional[Tuple[int, int]] = None) -> None:
        """Jump one tile in the movement direction.

        - If movement keys are held, jump uses that direction.
        - If not moving, jump uses the most recent non-zero direction.

        (No longer jumps to cursor; that behavior was confusing in play.)
        """
        if self.player is None:
            return
        dx, dy = self.player.direction
        if override_direction is not None and override_direction != (0, 0):
            dx, dy = override_direction
            self.player.direction = override_direction
        if dx == 0 and dy == 0:
            return
        target_x = int(round(self.player.x + dx))
        target_y = int(round(self.player.y + dy))
        if not self.world.in_bounds(target_x, target_y):
            return
        next_tile = self.world.get_tile(target_x, target_y)
        current_tile = self.world.get_tile(int(round(self.player.x)), int(round(self.player.y)))
        next_height = next_tile.height if next_tile else 0
        current_height = current_tile.height if current_tile else 0
        if next_height - current_height <= 1:
            self.player.x = float(target_x)
            self.player.y = float(target_y)
            self.player.height = next_height

    def mine_ahead(self) -> None:
        if self.player is None:
            return
        dx, dy = self.player.direction
        target_x = int(round(self.player.x + dx))
        target_y = int(round(self.player.y + dy))
        self.mine_tile_at(target_x, target_y)

    def mine_tile_at(self, x: int, y: int) -> None:
        tile = self.world.get_tile(x, y)
        if tile is None:
            return
        self.collect_tile_resources(tile)
        tile.height -= 1
        if tile.height < MIN_HEIGHT:
            self.world.clear_tile(x, y)
            return
        self.apply_depth_material(tile, x, y)
        if self.player and int(round(self.player.x)) == x and int(round(self.player.y)) == y:
            self.player.height = tile.height

    def collect_tile_resources(self, tile: Tile) -> None:
        if self.player is None:
            return
        self.add_inventory_item(tile.tile_type)
        if tile.texture_override:
            resource = Path(tile.texture_override).stem
            self.add_inventory_item(resource)

    def dig_clicked_tile(self, grid_pos: Tuple[int, int]) -> None:
        if self.player is None:
            return
        dx = grid_pos[0] - int(round(self.player.x))
        dy = grid_pos[1] - int(round(self.player.y))
        if max(abs(dx), abs(dy)) > 5:
            return
        direction = (
            int(math.copysign(1, dx)) if dx != 0 else 0,
            int(math.copysign(1, dy)) if dy != 0 else 0,
        )
        if direction != (0, 0):
            self.player.direction = direction
        self.mine_tile_at(grid_pos[0], grid_pos[1])

    def place_inventory_item(self, grid_pos: Tuple[int, int]) -> None:
        if self.player is None:
            return
        selected = self.selected_inventory_item
        if not selected:
            return
        dx = grid_pos[0] - int(round(self.player.x))
        dy = grid_pos[1] - int(round(self.player.y))
        direction = (
            int(math.copysign(1, dx)) if dx != 0 else 0,
            int(math.copysign(1, dy)) if dy != 0 else 0,
        )
        if direction != (0, 0):
            self.player.direction = direction
        if selected in self.tile_types:
            tile = self.world.get_tile(grid_pos[0], grid_pos[1])
            if tile is None:
                self.world.set_tile(grid_pos[0], grid_pos[1], selected, self.player.height)
                tile = self.world.get_tile(grid_pos[0], grid_pos[1])
            if tile:
                if grid_pos == (int(round(self.player.x)), int(round(self.player.y))):
                    tile.height = min(MAX_HEIGHT, tile.height + 1)
                    self.player.height = tile.height
                tile.tile_type = selected
                tile.texture_override = None
                tile.rotation = 0
                tile.flip_x = False
                tile.texture_tint = (255, 255, 255)
                tile.texture_scale = 1.0
            self.remove_inventory_item(selected)
        elif selected in self.object_tile_types:
            tile = self.world.get_tile(grid_pos[0], grid_pos[1])
            if tile is None and grid_pos == (int(round(self.player.x)), int(round(self.player.y))):
                self.world.set_tile(grid_pos[0], grid_pos[1], "dirt", self.player.height)
                tile = self.world.get_tile(grid_pos[0], grid_pos[1])
            if tile is None:
                self.world.set_tile(grid_pos[0], grid_pos[1], "dirt", self.player.height)
                tile = self.world.get_tile(grid_pos[0], grid_pos[1])
            if tile:
                replacement = self.hidden_replacement_by_type.get(selected)
                if replacement:
                    tile.texture_override = str(replacement)
                    tile.rotation = 0
                    tile.flip_x = False
                    tile.texture_tint = (255, 255, 255)
                    tile.texture_scale = 1.0
                self.remove_inventory_item(selected)
        else:
            # Any other inventory item can be placed as a dropped item on the ground.
            # This makes all pickups "placeable" without forcing them into tile types.
            self.loot.append((float(grid_pos[0]), float(grid_pos[1]), selected))
            self.remove_inventory_item(selected)

    def apply_depth_material(self, tile: Tile, x: int, y: int) -> None:
        if tile.tile_type == "water":
            return
        if tile.height <= LAVA_START:
            tile.tile_type = "lava"
            return
        if tile.height <= MAGMA_START:
            tile.tile_type = "magma"
            return
        if tile.height <= HELL_START:
            tile.tile_type = "hellstone"
            cave_noise = math.sin((x + self.world_seed) * 0.25) + math.cos((y - self.world_seed) * 0.25)
            if cave_noise > 0.35:
                tile.tile_type = "hell_cave"
            return
        if tile.height <= UNDERWORLD_DEEP:
            tile.tile_type = "ashen"
            return
        if tile.height <= UNDERWORLD_MID:
            tile.tile_type = "obsidian"
            return
        if tile.height <= UNDERWORLD_START:
            tile.tile_type = "understone"
            return
        if tile.height <= SURFACE_TOPSOIL_DEPTH and tile.height > SURFACE_SUBSOIL_DEPTH:
            tile.tile_type = "dirt"
            return
        if tile.height <= SURFACE_SUBSOIL_DEPTH and tile.height > CAVERN_TOP:
            tile.tile_type = "stone"
            return
        if tile.height < CAVERN_BOTTOM:
            if tile.height <= CAVERN_BOTTOM - 6:
                tile.tile_type = "stone_dark"
            else:
                tile.tile_type = "stone_deep"
            return
        if CAVERN_BOTTOM <= tile.height <= CAVERN_TOP:
            if (x, y) in self.cavern_open_tiles:
                tile.tile_type = "cavern"
            elif (x, y) in self.gem_tiles:
                tile.tile_type = "gem"
            elif (x, y) in self.mineral_tiles:
                tile.tile_type = "mineral"
            else:
                tile.tile_type = "stone_dark"
            return
        if tile.height <= SURFACE_SUBSOIL_DEPTH:
            tile.tile_type = "subsoil"
        elif tile.height <= SURFACE_TOPSOIL_DEPTH:
            tile.tile_type = "topsoil"

    def next_replacement(self) -> None:
        if self.replacement_images:
            self.replacement_index = (self.replacement_index + 1) % len(self.replacement_images)

    def prev_replacement(self) -> None:
        if self.replacement_images:
            self.replacement_index = (self.replacement_index - 1) % len(self.replacement_images)

    def rotate_replacement(self) -> None:
        self.replacement_rotation = (self.replacement_rotation + 90) % 360

    def apply_texture_override(self, x: int, y: int) -> None:
        tile = self.world.get_tile(x, y)
        if tile is None:
            self.world.set_tile(x, y, self.selected_tile_type, 0)
            tile = self.world.get_tile(x, y)
        if tile is None:
            return
        replacement = self.current_replacement()
        if replacement is None:
            return
        tile.texture_override = str(replacement)
        tile.rotation = self.replacement_rotation
        tile.flip_x = False
        tile.texture_tint = (255, 255, 255)
        tile.texture_scale = 1.0

    def remove_texture_override(self, x: int, y: int) -> None:
        tile = self.world.get_tile(x, y)
        if tile is None:
            return
        tile.texture_override = None
        tile.rotation = 0
        tile.flip_x = False
        tile.texture_tint = (255, 255, 255)
        tile.texture_scale = 1.0

    def generate_world(self, keep_seed: bool = False) -> None:
        if not keep_seed:
            self.world_seed = random.randint(0, 999999)
            self.generation_params = self.build_generation_params(self.world_seed)
        else:
            # Ensure generation parameters match the current world dimensions.
            # This prevents rare regeneration artifacts (e.g., extreme pillars / off sea-level) after transitions.
            params = getattr(self, "generation_params", None) or {}
            if (
                not params
                or params.get("world_width") != self.world.width
                or params.get("world_height") != self.world.height
            ):
                self.generation_params = self.build_generation_params(self.world_seed)
            # Keep current_biome in sync for animal/mob spawns and UI label.
            self.current_biome = self.generation_params.get(
                "biome",
                getattr(self, "current_biome", BIOME_PRESETS[0]),
            )
        self.apply_biome_styles()
        water_level = int(self.generation_params.get("water_level", -1))
        no_ocean = bool(self.generation_params.get("no_ocean"))
        self.world.tiles.clear()
        rng = random.Random(self.world_seed)
        volcanic_map: Dict[Tuple[int, int], bool] = {}
        for y in range(self.world.height):
            for x in range(self.world.width):
                base_height, volcanic = self.natural_height(x, y, self.world_seed)
                tile_type = self.pick_tile_type(x, y, base_height, rng, volcanic)
                if no_ocean:
                    height = base_height
                else:
                    height = max(base_height, water_level + 1)
                    if tile_type == "water":
                        height = water_level
                self.world.set_tile(x, y, tile_type, height)
                volcanic_map[(x, y)] = volcanic
        self.smooth_heightmap()
        self.refresh_surface_tiles(volcanic_map, rng)
        self.enforce_island_shape(water_level)
        self.apply_beach_sand()
        self.normalize_water_levels()
        self.generate_cavern_maps()
        self.scatter_forests(rng)
        self.scatter_objects(rng)
        self.generate_ruins(rng)
        self.generate_settlements(rng)
        self.animals.clear()
        self.mobs.clear()
        self.generate_animals()
        self.generate_mobs()
        self.loot.clear()
        self.center_camera_on_world()
        self.spawn_player()

    def randomize_world(self) -> None:
        seed = random.randint(0, 999999)
        rng = random.Random(seed)
        self.world_seed = seed
        self.generation_params = self.build_generation_params(seed)
        self.apply_biome_styles()
        water_level = int(self.generation_params.get("water_level", -1))
        no_ocean = bool(self.generation_params.get("no_ocean"))
        volcanic_map: Dict[Tuple[int, int], bool] = {}
        for y in range(self.world.height):
            for x in range(self.world.width):
                height, volcanic = self.natural_height(x, y, seed)
                tile_type = self.pick_tile_type(x, y, height, rng, volcanic)
                if no_ocean:
                    final_height = height
                else:
                    final_height = max(height, water_level + 1)
                    if tile_type == "water":
                        final_height = water_level
                self.world.set_tile(x, y, tile_type, final_height)
                volcanic_map[(x, y)] = volcanic
        self.smooth_heightmap()
        self.refresh_surface_tiles(volcanic_map, rng)
        self.enforce_island_shape(water_level)
        self.apply_beach_sand()
        self.normalize_water_levels()
        self.generate_cavern_maps()
        self.scatter_forests(rng)
        self.scatter_objects(rng)
        self.generate_ruins(rng)
        self.generate_settlements(rng)
        self.animals.clear()
        self.mobs.clear()
        self.generate_animals()
        self.generate_mobs()
        self.loot.clear()
        self.center_camera_on_world()
        self.spawn_player()

    def apply_beach_sand(self) -> None:
        biome = self.generation_params.get('biome', {})
        if self.generation_params.get("no_ocean"):
            return
        if biome.get('disable_beach_sand'):
            return
        to_sand = []
        for (x, y), tile in self.world.tiles.items():
            if tile.tile_type == "water":
                continue
            if tile.height > 1:
                continue
            neighbors = [
                self.world.get_tile(x - 1, y),
                self.world.get_tile(x + 1, y),
                self.world.get_tile(x, y - 1),
                self.world.get_tile(x, y + 1),
            ]
            if any(neighbor and neighbor.tile_type == "water" for neighbor in neighbors):
                to_sand.append((x, y))
        for x, y in to_sand:
            tile = self.world.get_tile(x, y)
            if tile is not None:
                tile.tile_type = "sand"

    def enforce_island_shape(self, water_level: int) -> None:
        # If this biome is meant to have no oceans, don't force an ocean ring
        # at the map edge (that was the source of the "world on a pillar" look).
        if self.generation_params.get("no_ocean"):
            self.clamp_world_heights()
            return
        water_level = max(MIN_HEIGHT, min(MAX_HEIGHT, int(water_level)))
        for (x, y), tile in self.world.tiles.items():
            continent = self.continent_factor(x, y, self.world_seed)
            if continent < 0.18:
                tile.tile_type = "water"
                tile.height = water_level
            elif continent < 0.28 and tile.tile_type != "water":
                tile.height = max(water_level, tile.height - int((0.28 - continent) * 6))
        self.clamp_world_heights()
    def clamp_world_heights(self) -> None:
        """Clamp all tile heights to the engine's safe range.

        This prevents extreme water-level settings (e.g., -999) from creating
        gigantic vertical pillars/cliffs when worlds are regenerated.
        """
        for tile in self.world.tiles.values():
            tile.height = max(MIN_HEIGHT, min(MAX_HEIGHT, tile.height))



    def normalize_water_levels(self) -> None:
        if self.generation_params.get("no_ocean"):
            return
        water_level = int(self.generation_params.get("water_level", -1))
        # Keep water within safe bounds to avoid giant cliff faces.
        water_level = max(MIN_WATER_LEVEL, min(MAX_HEIGHT, water_level))
        for tile in self.world.tiles.values():
            if tile.tile_type == "water":
                tile.height = water_level

        self.clamp_world_heights()

    def carve_surface_holes(self, rng: random.Random) -> None:
        return

    def smooth_heightmap(self) -> None:
        new_tiles: Dict[Tuple[int, int], Tile] = {}
        for y in range(self.world.height):
            for x in range(self.world.width):
                tile = self.world.get_tile(x, y)
                if tile is None:
                    continue
                neighbors = [
                    self.world.get_tile(nx, ny)
                    for nx, ny in [(x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)]
                ]
                heights = [tile.height] + [n.height for n in neighbors if n is not None]
                avg_height = int(round(sum(heights) / len(heights)))
                new_tiles[(x, y)] = Tile(
                    avg_height,
                    tile.tile_type,
                    tile.texture_override,
                    tile.rotation,
                    tile.flip_x,
                    tile.texture_tint,
                    tile.texture_scale,
                )
        self.world.tiles.update(new_tiles)

    def refresh_surface_tiles(self, volcanic_map: Dict[Tuple[int, int], bool], rng: random.Random) -> None:
        for (x, y), tile in self.world.tiles.items():
            volcanic = volcanic_map.get((x, y), False)
            tile.tile_type = self.pick_tile_type(x, y, tile.height, rng, volcanic)
            tile.texture_override = None
            tile.rotation = 0
            tile.flip_x = False
            tile.texture_tint = (255, 255, 255)
            tile.texture_scale = 1.0

    def smooth_heightmap_for_positions(self, positions: List[Tuple[int, int]]) -> None:
        new_tiles: Dict[Tuple[int, int], Tile] = {}
        for x, y in positions:
            tile = self.world.get_tile(x, y)
            if tile is None:
                continue
            neighbors = [
                self.world.get_tile(nx, ny)
                for nx, ny in [(x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)]
            ]
            heights = [tile.height] + [n.height for n in neighbors if n is not None]
            avg_height = int(round(sum(heights) / len(heights)))
            new_tiles[(x, y)] = Tile(
                avg_height,
                tile.tile_type,
                tile.texture_override,
                tile.rotation,
                tile.flip_x,
                tile.texture_tint,
                tile.texture_scale,
            )
        self.world.tiles.update(new_tiles)

    def refresh_surface_tiles_for_positions(
        self,
        positions: List[Tuple[int, int]],
        volcanic_map: Dict[Tuple[int, int], bool],
        rng: random.Random,
    ) -> None:
        for x, y in positions:
            tile = self.world.get_tile(x, y)
            if tile is None:
                continue
            volcanic = volcanic_map.get((x, y), False)
            tile.tile_type = self.pick_tile_type(x, y, tile.height, rng, volcanic)
            tile.texture_override = None
            tile.rotation = 0
            tile.flip_x = False
            tile.texture_tint = (255, 255, 255)
            tile.texture_scale = 1.0

    def generate_cavern_maps(self) -> None:
        self.cavern_open_tiles = set()
        self.mineral_tiles = set()
        self.gem_tiles = set()
        rng = random.Random(self.world_seed + 4242)
        for y in range(self.world.height):
            for x in range(self.world.width):
                roll = rng.random()
                if roll < 0.006:
                    self.gem_tiles.add((x, y))
                elif roll < 0.03:
                    self.mineral_tiles.add((x, y))

    def generate_ruins(self, rng: random.Random) -> None:
        count = rng.randint(3, 6)
        for _ in range(count):
            center_x = rng.randint(5, self.world.width - 6)
            center_y = rng.randint(5, self.world.height - 6)
            width = rng.randint(5, 9)
            height = rng.randint(5, 9)
            rooms = rng.randint(2, 4)
            room_rects = []
            for _ in range(rooms):
                room_w = rng.randint(3, max(4, width - 1))
                room_h = rng.randint(3, max(4, height - 1))
                room_x = center_x + rng.randint(-width + 1, width - room_w)
                room_y = center_y + rng.randint(-height + 1, height - room_h)
                room_rects.append((room_x, room_y, room_w, room_h))
            for dx in range(-width, width + 1):
                for dy in range(-height, height + 1):
                    if rng.random() < 0.15:
                        continue
                    x = center_x + dx
                    y = center_y + dy
                    if not self.world.in_bounds(x, y):
                        continue
                    tile = self.world.get_tile(x, y)
                    if tile is None:
                        continue
                    is_wall = abs(dx) in (width, width - 1) or abs(dy) in (height, height - 1)
                    for room_x, room_y, room_w, room_h in room_rects:
                        if room_x <= x <= room_x + room_w and room_y <= y <= room_y + room_h:
                            if x in (room_x, room_x + room_w) or y in (room_y, room_y + room_h):
                                is_wall = True
                    if is_wall:
                        tile.tile_type = "ruins"
                        tile.height = min(MAX_HEIGHT, tile.height + rng.randint(1, 4))
                    else:
                        if rng.random() < 0.2:
                            tile.tile_type = "ruins"
                        tile.height = max(MIN_HEIGHT, tile.height - rng.randint(0, 1))
            for room_x, room_y, room_w, room_h in room_rects:
                door_x = room_x + rng.randint(1, max(1, room_w - 1))
                door_y = room_y
                door_tile = self.world.get_tile(door_x, door_y)
                if door_tile:
                    door_tile.tile_type = "ruins"
                    door_tile.height = max(MIN_HEIGHT, door_tile.height - 1)

    def generate_settlements(self, rng: random.Random) -> None:
        biome = self.generation_params.get("biome", {})
        density = float(biome.get("settlement_density", 0.0))
        if density <= 0:
            return
        count = max(2, int(6 * density))
        for _ in range(count):
            center_x = rng.randint(6, self.world.width - 7)
            center_y = rng.randint(6, self.world.height - 7)
            radius = rng.randint(2, 4)
            for dx in range(-radius, radius + 1):
                for dy in range(-radius, radius + 1):
                    x = center_x + dx
                    y = center_y + dy
                    if not self.world.in_bounds(x, y):
                        continue
                    if abs(dx) + abs(dy) > radius + rng.randint(0, 1):
                        continue
                    tile = self.world.get_tile(x, y)
                    if tile is None:
                        continue
                    tile.tile_type = "ruins"
                    tile.height = min(MAX_HEIGHT, tile.height + rng.randint(1, 3))

    def build_generation_params(self, seed: int) -> Dict[str, float]:
        rng = random.Random(seed)
        biome = self.choose_biome(rng)
        width = self.world.width
        height = self.world.height
        center_x = width / 2
        center_y = height / 2
        continent_count = int(biome.get("continent_count", 1))
        continent_scale = float(biome.get("continent_scale", rng.uniform(0.42, 0.48)))
        continent_jitter = float(biome.get("continent_jitter", rng.uniform(0.08, 0.16)))
        radius = min(width, height) * continent_scale
        continent_centers: List[Tuple[float, float]] = []
        if continent_count <= 1:
            continent_centers.append((center_x, center_y))
        else:
            spread = radius * 0.4
            for _ in range(continent_count):
                continent_centers.append(
                    (
                        center_x + rng.uniform(-spread, spread),
                        center_y + rng.uniform(-spread, spread),
                    )
                )
        # Some biomes (hellish/moonscape) use a sentinel water_level (e.g. -999)
        # to mean "no ocean". If we clamp that to MIN_HEIGHT, the island-shape
        # pass will create an ultra-deep ocean ring and the land looks like it's
        # perched on a gigantic pillar. Treat sentinel values as "no_ocean".
        raw_water_level = int(biome.get("water_level", -1))
        no_ocean = raw_water_level <= -900
        water_level = raw_water_level
        if not no_ocean:
            if water_level > -5:
                water_level -= 1
            water_level = max(MIN_WATER_LEVEL, min(MAX_HEIGHT, int(water_level)))
        else:
            # Keep an internal water level for any incidental "water" tiles,
            # but generation will avoid creating oceans entirely.
            water_level = -5
        return {
            "freq_a": rng.uniform(0.1, 0.2),
            "freq_b": rng.uniform(0.07, 0.14),
            "ridge_freq": rng.uniform(0.04, 0.08),
            "offset_x": rng.uniform(-12, 12),
            "offset_y": rng.uniform(-12, 12),
            "mountain_amp": biome["mountain_amp"] + rng.uniform(-0.4, 0.4),
            "canyon_amp": 0.0,
            "cave_amp": biome["cave_amp"] + rng.uniform(-0.3, 0.3),
            "river_amp": biome["river_amp"] + rng.uniform(-0.2, 0.2),
            "ravine_amp": 0.0,
            "water_level": water_level,
            "no_ocean": no_ocean,
            "holes": biome["holes"],
            "biome": biome,
            "continent_centers": continent_centers,
            "continent_radius": radius,
            "continent_jitter": continent_jitter,
            "world_width": width,
            "world_height": height,
            "landform": biome.get("landform", "mixed"),
        }

    def reset_biome_cycle(self) -> None:
        self.biome_cycle = list(BIOME_PRESETS)
        random.shuffle(self.biome_cycle)

    def choose_biome(self, rng: random.Random) -> Dict[str, float]:
        if not self.biome_cycle:
            self.reset_biome_cycle()
        choice = self.biome_cycle.pop(0)
        if getattr(self, "current_biome", None) and choice["name"] == self.current_biome.get("name"):
            if not self.biome_cycle:
                self.reset_biome_cycle()
            choice = self.biome_cycle.pop(0)
        self.current_biome = choice
        return choice

    def apply_biome_styles(self) -> None:
        biome = self.generation_params.get("biome", self.current_biome)
        if biome is None:
            return
        water_style = self.styles.get("water")
        if water_style:
            water_style.base_color = biome.get("water_color", DEFAULT_COLORS.get("water", (50, 110, 200)))
        tint = self.biome_tint(biome.get("name", ""))
        for key_name, tile_key in (
            ("surface_tile", biome.get("surface_tile")),
            ("mid_tile", biome.get("mid_tile")),
            ("high_tile", biome.get("high_tile")),
        ):
            if not tile_key or tile_key not in self.styles:
                continue
            base = DEFAULT_COLORS.get(tile_key, self.styles[tile_key].base_color)
            self.styles[tile_key].base_color = self.blend_color(base, tint, 0.25)
        self.renderer.cache.clear()
        self.replacement_order = self.load_replacement_order()
        self.load_replacement_images()

    def biome_tint(self, name: str) -> Tuple[int, int, int]:
        seed = sum(ord(ch) for ch in name)
        rng = random.Random(seed)
        return (
            rng.randint(-25, 25),
            rng.randint(-25, 25),
            rng.randint(-25, 25),
        )

    def blend_color(self, base: Tuple[int, int, int], tint: Tuple[int, int, int], ratio: float) -> Tuple[int, int, int]:
        return (
            max(0, min(255, int(base[0] + tint[0] * ratio * 4))),
            max(0, min(255, int(base[1] + tint[1] * ratio * 4))),
            max(0, min(255, int(base[2] + tint[2] * ratio * 4))),
        )

    def continent_factor(self, x: int, y: int, seed: int) -> float:
        params = self.generation_params
        centers = params.get("continent_centers")
        if not centers:
            centers = [(self.world.width / 2, self.world.height / 2)]
        radius = params.get("continent_radius", min(self.world.width, self.world.height) * 0.45)
        jitter = params.get("continent_jitter", 0.1)
        best = 0.0
        for center_x, center_y in centers:
            dist = math.hypot(x - center_x, y - center_y)
            base = max(0.0, 1.0 - dist / max(radius, 1.0))
            smooth = base * base * (3 - 2 * base)
            best = max(best, smooth)
        coast_noise = (math.sin((x + seed) * 0.12) + math.cos((y - seed) * 0.12)) * 0.5
        return max(0.0, min(1.0, best + coast_noise * jitter))

    def natural_height(self, x: int, y: int, seed: int) -> Tuple[int, bool]:
        params = self.generation_params
        base = math.sin((x + params["offset_x"]) * params["freq_a"]) * 2.2
        base += math.cos((y + params["offset_y"]) * params["freq_b"]) * 2.1
        ridge = math.sin((x + y) * params["ridge_freq"]) * 1.7
        noise = math.sin((x * 0.9 + seed) * 0.2) + math.cos((y * 0.7 + seed) * 0.25)
        canyon = -abs(math.sin((x + seed) * 0.045) + math.cos((y - seed) * 0.05)) * params["canyon_amp"]
        ravine = -abs(math.sin((x - seed) * 0.065) + math.cos((y + seed) * 0.06)) * params["ravine_amp"]
        river = -abs(math.sin((x + seed) * 0.032) + math.cos((y - seed) * 0.031)) * params["river_amp"]
        mountain = math.sin((x * 0.03 + y * 0.02) + seed * 0.00015) * params["mountain_amp"]
        cave = -abs(math.sin((x * 0.16 + y * 0.12 + seed) * 0.45)) * params["cave_amp"]
        volcanic_mask = math.sin((x * 0.01 + seed) * 0.35) + math.cos((y * 0.01 - seed) * 0.28)
        volcanic = volcanic_mask > 1.6
        volcano_cone = 5 if volcanic else 0
        landform = params.get("landform", "mixed")
        if landform == "flat":
            mountain *= 0.4
            ridge *= 0.5
        elif landform == "cliff":
            ridge *= 1.6
            canyon *= 0.4
        elif landform == "mountain":
            mountain *= 1.2
        continent = self.continent_factor(x, y, seed)
        height = base + ridge + noise + canyon + ravine + river + mountain + cave + volcano_cone
        height *= 0.45 + 0.55 * continent
        if continent < 0.25:
            height -= (0.25 - continent) * 10
        return int(round(height)), volcanic

    def biome_factors(self, x: int, y: int, seed: int) -> Tuple[float, float]:
        temp = (math.sin((x + seed) * 0.04) + math.cos((y - seed) * 0.03)) * 0.5 + 0.5
        moisture = (math.sin((x - seed) * 0.03) + math.cos((y + seed) * 0.04)) * 0.5 + 0.5
        return max(0.0, min(1.0, temp)), max(0.0, min(1.0, moisture))

    def pick_tile_type(self, x: int, y: int, height: int, rng: random.Random, volcanic: bool) -> str:
        if volcanic and height >= 4:
            return "lava"
        # Some biomes use a sentinel water_level to mean "no ocean".
        if not self.generation_params.get("no_ocean"):
            water_level = int(self.generation_params.get("water_level", -1))
            water_level = max(MIN_WATER_LEVEL, min(MAX_HEIGHT, water_level))
            if height <= water_level:
                return "water"
        biome = self.generation_params.get("biome", {})
        surface_tile = biome.get("surface_tile", "grass")
        mid_tile = biome.get("mid_tile", surface_tile)
        high_tile = biome.get("high_tile", "stone")
        if height <= 1:
            return surface_tile
        if height <= 3:
            return mid_tile
        return high_tile
    def smooth_heights(self) -> None:
        positions = [(x, y) for y in range(self.world.height) for x in range(self.world.width)]
        self.record_undo(positions)
        new_tiles: Dict[Tuple[int, int], Tile] = {}
        for x, y in positions:
            tile = self.world.get_tile(x, y)
            if tile is None:
                continue
            neighbors = [
                self.world.get_tile(nx, ny)
                for nx, ny in [(x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)]
            ]
            heights = [tile.height] + [n.height for n in neighbors if n is not None]
            avg_height = int(round(sum(heights) / len(heights)))
            new_tiles[(x, y)] = Tile(
                avg_height,
                tile.tile_type,
                tile.texture_override,
                tile.rotation,
                tile.flip_x,
                tile.texture_tint,
                tile.texture_scale,
            )
        self.world.tiles.update(new_tiles)

    def flatten_world(self) -> None:
        positions = [(x, y) for y in range(self.world.height) for x in range(self.world.width)]
        self.record_undo(positions)
        for x, y in positions:
            tile = self.world.get_tile(x, y)
            if tile is None:
                self.world.set_tile(x, y, self.selected_tile_type, 0)
            else:
                tile.height = 0
                tile.tile_type = self.selected_tile_type

    def save_world(self, path: Path) -> None:
        SAVE_DIR.mkdir(exist_ok=True)
        data = self.world.to_dict()
        data["tile_types"] = self.tile_types
        data["styles"] = {
            tile_type: {
                "base_color": self.styles[tile_type].base_color,
                "brightness": self.styles[tile_type].brightness,
                "contrast": self.styles[tile_type].contrast,
                "tint": self.styles[tile_type].tint,
                "darkness": self.styles[tile_type].darkness,
                "texture_seed": self.styles[tile_type].texture_seed,
            }
            for tile_type in self.tile_types
        }
        with path.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)

    def load_world(self, path: Path) -> None:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        tile_types = data.get("tile_types")
        if tile_types:
            self.tile_types = list(tile_types)
        styles_data = data.get("styles", {})
        for tile_type in self.tile_types:
            if tile_type in styles_data:
                style = styles_data[tile_type]
                self.styles[tile_type] = TileStyle(
                    base_color=tuple(style.get("base_color", DEFAULT_COLORS.get(tile_type, (120, 120, 120)))),
                    brightness=style.get("brightness", 1.0),
                    contrast=style.get("contrast", 1.0),
                    tint=tuple(style.get("tint", (0, 0, 0))),
                    darkness=style.get("darkness", 0.0),
                    texture_seed=style.get("texture_seed", 0),
                )
        self.world = World.from_dict(data)
        self.asset_manager.tile_types = self.tile_types
        self.renderer = IsoRenderer(self.screen, self.styles)
        self.build_ui()
        self.generate_cavern_maps()
        self.center_camera_on_world()

    def export_for_pygame(self, path: Path) -> None:
        surface = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
        original_screen = self.screen
        self.screen = surface
        self.render()
        pygame.image.save(surface, path)
        self.screen = original_screen

    def get_world_coords(self, mouse_pos: Tuple[int, int]) -> Optional[Tuple[int, int]]:
        adjusted = self.adjust_mouse_for_zoom(mouse_pos)
        if adjusted is None:
            return None
        return self.get_tile_at_screen(adjusted)

    def get_tile_at_screen(self, mouse_pos: Tuple[int, int]) -> Optional[Tuple[int, int]]:
        best_tile: Optional[Tuple[int, int]] = None
        best_height = -10**6
        best_screen_y = 10**6
        target_height = None
        if self.player_mode and self.player is not None and (self.player.height < 0 or self.player.is_swimming):
            target_height = self.player.height
        closest_height_delta = 10**6
        for (x, y), tile in self.world.tiles.items():
            screen_x, screen_y = self.renderer.iso_to_screen(x, y, tile.height, self.offset)
            if not IsoRenderer.point_in_diamond(mouse_pos, (screen_x, screen_y)):
                continue
            if target_height is not None:
                delta = abs(tile.height - target_height)
                if delta < closest_height_delta or (delta == closest_height_delta and screen_y < best_screen_y):
                    best_tile = (x, y)
                    closest_height_delta = delta
                    best_screen_y = screen_y
            else:
                if tile.height > best_height or (tile.height == best_height and screen_y < best_screen_y):
                    best_tile = (x, y)
                    best_height = tile.height
                    best_screen_y = screen_y
        return best_tile

    def record_undo(self, positions: List[Tuple[int, int]]) -> None:
        previous_tiles = [self.world.get_tile(x, y) for x, y in positions]
        copied_tiles: List[Optional[Tile]] = []
        for tile in previous_tiles:
            if tile is None:
                copied_tiles.append(None)
            else:
                copied_tiles.append(
                    Tile(
                        tile.height,
                        tile.tile_type,
                        tile.texture_override,
                        tile.rotation,
                        tile.flip_x,
                        tile.texture_tint,
                        tile.texture_scale,
                    )
                )
        self.undo_stack.append(UndoAction(positions, copied_tiles))
        self.redo_stack.clear()

    def apply_undo(self, stack_from: List[UndoAction], stack_to: List[UndoAction]) -> None:
        if not stack_from:
            return
        action = stack_from.pop()
        current_tiles = [self.world.get_tile(x, y) for x, y in action.positions]
        current_copy: List[Optional[Tile]] = []
        for tile in current_tiles:
            if tile is None:
                current_copy.append(None)
            else:
                current_copy.append(
                    Tile(
                        tile.height,
                        tile.tile_type,
                        tile.texture_override,
                        tile.rotation,
                        tile.flip_x,
                        tile.texture_tint,
                        tile.texture_scale,
                    )
                )
        for (x, y), tile in zip(action.positions, action.previous_tiles):
            if tile is None:
                self.world.clear_tile(x, y)
            else:
                self.world.set_tile(x, y, tile.tile_type, tile.height)
                restored = self.world.get_tile(x, y)
                if restored is not None:
                    restored.texture_override = tile.texture_override
                    restored.rotation = tile.rotation
                    restored.flip_x = tile.flip_x
                    restored.texture_tint = tile.texture_tint
                    restored.texture_scale = tile.texture_scale
        stack_to.append(UndoAction(action.positions, current_copy))

    def paint_at(self, grid_pos: Tuple[int, int], add_action: bool = True) -> None:
        x, y = grid_pos
        positions = []
        for dy in range(-self.brush_size + 1, self.brush_size):
            for dx in range(-self.brush_size + 1, self.brush_size):
                tx, ty = x + dx, y + dy
                if self.world.in_bounds(tx, ty):
                    positions.append((tx, ty))
        self.record_undo(positions)
        tool = self.current_tool
        if not add_action:
            tool = self.inverse_tool(tool)
        for tx, ty in positions:
            if tool == "raise":
                self.world.raise_tile(tx, ty, self.selected_tile_type)
            elif tool == "lower":
                self.world.lower_tile(tx, ty)
                lowered_tile = self.world.get_tile(tx, ty)
                if lowered_tile:
                    self.apply_depth_material(lowered_tile, tx, ty)
            elif tool == "paint":
                self.world.paint_tile(tx, ty, self.selected_tile_type, bump=False)
            elif tool == "erase":
                tile = self.world.get_tile(tx, ty)
                if tile is None:
                    continue
                if tile.height <= MIN_HEIGHT:
                    self.world.clear_tile(tx, ty)
                else:
                    self.world.lower_tile(tx, ty)
                    lowered_tile = self.world.get_tile(tx, ty)
                    if lowered_tile:
                        self.apply_depth_material(lowered_tile, tx, ty)
            elif tool == "pick":
                picked = self.world.get_tile(tx, ty)
                if picked:
                    self.set_tile_type(picked.tile_type)
                return
            elif tool == "replace_texture":
                self.apply_texture_override(tx, ty)
            elif tool == "remove_texture":
                self.remove_texture_override(tx, ty)

    def inverse_tool(self, tool: str) -> str:
        if tool == "raise":
            return "lower"
        if tool == "lower":
            return "raise"
        if tool == "paint":
            return "erase"
        if tool == "erase":
            return "paint"
        if tool == "replace_texture":
            return "remove_texture"
        if tool == "remove_texture":
            return "replace_texture"
        return tool

    def adjust_style(self, tile_type: str, brightness: float = 0.0, contrast: float = 0.0, darkness: float = 0.0) -> None:
        style = self.styles[tile_type]
        style.brightness = max(0.2, min(2.0, style.brightness + brightness))
        style.contrast = max(0.5, min(2.0, style.contrast + contrast))
        style.darkness = max(0.0, min(0.8, style.darkness + darkness))
        self.renderer.cache.clear()

    def shift_tint(self, tile_type: str, r: int, g: int, b: int) -> None:
        style = self.styles[tile_type]
        tint = (
            max(-80, min(80, style.tint[0] + r)),
            max(-80, min(80, style.tint[1] + g)),
            max(-80, min(80, style.tint[2] + b)),
        )
        style.tint = tint
        self.renderer.cache.clear()

    def handle_input(self) -> bool:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    if self.close_open_panels():
                        continue
                    now = pygame.time.get_ticks() / 1000.0
                    if now - self.last_escape_time <= self.exit_prompt_duration:
                        return False
                    self.last_escape_time = now
                    self.exit_prompt_timer = self.exit_prompt_duration
                    continue
                if event.key == pygame.K_h:
                    self.toggle_help()
                if event.key == pygame.K_t:
                    self.texture_list_collapsed = not self.texture_list_collapsed
                if event.key == pygame.K_p:
                    self.toggle_player_mode()
                if event.key == pygame.K_i:
                    self.inventory_visible = not self.inventory_visible
                    if self.inventory_visible:
                        self.update_layout()
                if event.key == pygame.K_SPACE:
                    # Jump should follow the movement input (WASD). If no movement input is
                    # held, fall back to the most recent direction stored on the player.
                    keys = pygame.key.get_pressed()
                    raw_x = int(keys[pygame.K_d]) - int(keys[pygame.K_a])
                    raw_y = int(keys[pygame.K_s]) - int(keys[pygame.K_w])
                    step_x = 0 if raw_x == 0 else int(raw_x / abs(raw_x))
                    step_y = 0 if raw_y == 0 else int(raw_y / abs(raw_y))
                    override = (step_x, step_y) if (step_x != 0 or step_y != 0) else None
                    self.jump_player(override)
                if event.key == pygame.K_m:
                    self.mine_ahead()
                if event.key == pygame.K_u:
                    self.apply_undo(self.undo_stack, self.redo_stack)
                if event.key == pygame.K_y:
                    self.apply_undo(self.redo_stack, self.undo_stack)
                if event.key == pygame.K_r:
                    self.generate_world()
                if event.key == pygame.K_g:
                    self.generate_world()
                if event.key == pygame.K_s:
                    self.save_world(SAVE_DIR / "world.json")
                if event.key == pygame.K_l:
                    self.load_world(SAVE_DIR / "world.json")
                if event.key == pygame.K_e:
                    self.export_for_pygame(SAVE_DIR / "world_export.png")
                if event.key == pygame.K_z:
                    self.toggle_zoom()
                # Hotkey weapons (player mode) / bind weapons (inventory open) / tile-type shortcuts (editor)
                if pygame.K_1 <= event.key <= pygame.K_9:
                    slot = event.key - pygame.K_1 + 1
                    if self.inventory_visible and self.selected_weapon_id:
                        self.bind_weapon_to_slot(self.selected_weapon_id, slot)
                        continue
                    if self.player_mode and self.player is not None and slot in self.player.weapon_bindings:
                        self.equip_weapon(self.player.weapon_bindings[slot])
                        continue
                if (not self.player_mode) and pygame.K_1 <= event.key <= pygame.K_6:
                    index = event.key - pygame.K_1
                    if index < len(self.tile_types):
                        self.set_tile_type(self.tile_types[index])
                if not self.player_mode:
                    if event.key == pygame.K_RIGHT:
                        self.offset = (self.offset[0] - 20, self.offset[1])
                    if event.key == pygame.K_LEFT:
                        self.offset = (self.offset[0] + 20, self.offset[1])
                    if event.key == pygame.K_UP:
                        self.offset = (self.offset[0], self.offset[1] + 20)
                    if event.key == pygame.K_DOWN:
                        self.offset = (self.offset[0], self.offset[1] - 20)
                if event.key == pygame.K_9:
                    self.decrease_brush()
                if event.key == pygame.K_0:
                    self.increase_brush()
                if event.key == pygame.K_F11:
                    self.toggle_fullscreen()
            if event.type == pygame.MOUSEBUTTONDOWN and event.button in (1, 3):
                if self.handle_ui_click(event.pos):
                    continue
                adjusted = self.adjust_mouse_for_zoom(event.pos)
                grid_pos = self.get_world_coords(event.pos)
                if self.player_mode:
                    if event.button == 1 and adjusted is not None:
                        mob = self.get_mob_at_screen(adjusted)
                        if mob is not None:
                            self.manual_target = mob
                            self.manual_target_timer = 2.0
                            self.player_attack(mob, force=True)
                            continue
                    if grid_pos:
                        if event.button == 1:
                            self.dig_clicked_tile(grid_pos)
                        elif event.button == 3:
                            self.place_inventory_item(grid_pos)
                        continue
                if not self.player_mode and grid_pos:
                    self.paint_at(grid_pos, add_action=event.button == 1)
            if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                self.day_speed_dragging = False
                self.subsurface_dragging = False
                self.audio_dragging = False
            if event.type == pygame.MOUSEMOTION and self.day_speed_dragging:
                self.update_day_speed_from_mouse(event.pos[0])
            if event.type == pygame.MOUSEMOTION and self.subsurface_dragging:
                self.update_subsurface_depth_from_mouse(event.pos[0])
            if event.type == pygame.MOUSEMOTION and self.audio_dragging:
                self.update_audio_volume_from_mouse(event.pos[0])
            if event.type == pygame.MOUSEWHEEL:
                mouse_pos = pygame.mouse.get_pos()
                if self.palette_visible and self.palette_panel_rect.collidepoint(mouse_pos):
                    self.scroll_palette(-event.y * self.texture_scroll_speed)
                elif self.menu_visible and self.menu_panel_rect.collidepoint(mouse_pos):
                    self.scroll_menu(-event.y * self.texture_scroll_speed)
                elif self.inventory_visible and self.inventory_panel_rect.collidepoint(mouse_pos):
                    self.scroll_inventory_selection(-event.y)
                elif self.player_mode and not self.is_over_ui(mouse_pos):
                    self.scroll_inventory_selection(-event.y)
            if event.type == pygame.VIDEORESIZE:
                self.resize_screen(event.w, event.h)
        mouse_pressed = pygame.mouse.get_pressed()
        now = pygame.time.get_ticks()
        if mouse_pressed[0] or mouse_pressed[2]:
            if now - self.last_paint_time > self.drag_interval_ms:
                self.last_paint_time = now
                if not self.is_over_ui(pygame.mouse.get_pos()):
                    grid_pos = self.get_world_coords(pygame.mouse.get_pos())
                    if grid_pos:
                        if self.player_mode:
                            if mouse_pressed[0]:
                                self.dig_clicked_tile(grid_pos)
                            if mouse_pressed[2]:
                                self.place_inventory_item(grid_pos)
                        else:
                            self.paint_at(grid_pos, add_action=mouse_pressed[0])
        return True

    def close_open_panels(self) -> bool:
        closed = False
        if self.settings_visible:
            self.settings_visible = False
            self.day_speed_dragging = False
            self.subsurface_dragging = False
            self.audio_dragging = False
            closed = True
        if self.palette_visible:
            self.palette_visible = False
            closed = True
        if self.menu_visible:
            self.menu_visible = False
            closed = True
        if self.inventory_visible:
            self.inventory_visible = False
            closed = True
        if self.show_help:
            self.show_help = False
            closed = True
        return closed

    def handle_ui_click(self, pos: Tuple[int, int]) -> bool:
        if (self.settings_visible or self.palette_visible or self.menu_visible or self.inventory_visible) and not self.is_over_ui(pos):
            self.close_open_panels()
            return True
            if self.settings_visible and not (
                self.settings_panel_rect.collidepoint(pos) or self.settings_button_rect.collidepoint(pos)
            ):
                self.settings_visible = False
                self.day_speed_dragging = False
                self.subsurface_dragging = False
                self.audio_dragging = False
        if self.palette_visible and not self.palette_panel_rect.collidepoint(pos):
            self.palette_visible = False
        if self.menu_visible and not (
            self.menu_panel_rect.collidepoint(pos)
            or any(rect.collidepoint(pos) for rect in self.menu_button_rects.values())
        ):
            self.menu_visible = False
        if self.inventory_visible and not self.inventory_panel_rect.collidepoint(pos):
            self.inventory_visible = False
        if not self.is_over_ui(pos):
            return False
        if self.settings_button_rect.collidepoint(pos):
            self.settings_visible = not self.settings_visible
            if self.settings_visible:
                self.palette_visible = False
                self.menu_visible = False
                self.inventory_visible = False
            return True
        if self.player_button_rect.collidepoint(pos):
            self.toggle_player_mode()
            return True
        if self.handle_menu_button_click(pos):
            return True
        if self.handle_settings_click(pos):
            return True
        if self.handle_palette_click(pos):
            return True
        if self.handle_inventory_click(pos):
            return True
        if self.handle_menu_click(pos):
            self.refresh_button_states()
            return True
        return True

    def handle_settings_click(self, pos: Tuple[int, int]) -> bool:
        if not self.settings_visible:
            return False
        if not self.settings_panel_rect.collidepoint(pos):
            return False
        slider = self.get_day_speed_slider_rect()
        if slider.collidepoint(pos):
            self.day_speed_dragging = True
            self.update_day_speed_from_mouse(pos[0])
            return True
        subsurface_slider = self.get_subsurface_slider_rect()
        if subsurface_slider.collidepoint(pos):
            self.subsurface_dragging = True
            self.update_subsurface_depth_from_mouse(pos[0])
            return True
        audio_slider = self.get_audio_slider_rect()
        if audio_slider.collidepoint(pos):
            self.audio_dragging = True
            self.update_audio_volume_from_mouse(pos[0])
            return True
        local_x = pos[0] - self.settings_panel_rect.x
        local_y = pos[1] - self.settings_panel_rect.y
        start_y = 34
        option_height = 28
        for idx, (_, action) in enumerate(self.settings_actions()):
            action_rect = pygame.Rect(10, start_y + idx * option_height, self.settings_panel_rect.width - 20, 24)
            if action_rect.collidepoint((local_x, local_y)):
                action()
                return True
        start_y = self.settings_option_start()
        for idx, (key, _) in enumerate(self.settings_options()):
            option_rect = pygame.Rect(10, start_y + idx * option_height, self.settings_panel_rect.width - 20, 24)
            if option_rect.collidepoint((local_x, local_y)):
                self.settings[key] = not self.settings.get(key, False)
                if key == "high_quality":
                    self.texture_thumbs.clear()
                if key == "vsync":
                    size = self.screen.get_size()
                    self.screen = self.create_display(size)
                    self.renderer.screen = self.screen
                    self.update_layout()
                if key == "audio_enabled":
                    self.audio.enabled = bool(self.settings.get("audio_enabled", True))
                self.save_settings()
                return True
        return True

    def handle_palette_click(self, pos: Tuple[int, int]) -> bool:
        if not self.palette_visible:
            return False
        if not self.palette_panel_rect.collidepoint(pos):
            return False
        local_x = pos[0] - self.palette_panel_rect.x
        local_y = pos[1] - self.palette_panel_rect.y
        tab_height = 28
        if local_y <= tab_height:
            if local_x < self.palette_panel_rect.width / 2:
                self.palette_tab = "tiles"
            else:
                self.palette_tab = "textures"
            self.palette_scroll = 0
            return True
        list_top = tab_height + 10
        item_height = 26
        index = (local_y - list_top + self.palette_scroll) // item_height
        if index < 0:
            return True
        if self.palette_tab == "tiles":
            if 0 <= index < len(self.tile_types):
                self.set_tile_type(self.tile_types[int(index)])
                self.palette_visible = False
                return True
        else:
            if 0 <= index < len(self.replacement_images):
                self.replacement_index = int(index)
                self.set_tool("replace_texture")
                self.palette_visible = False
                return True
        return True

    def handle_inventory_click(self, pos: Tuple[int, int]) -> bool:
        if not self.inventory_visible:
            return False
        if not self.inventory_panel_rect.collidepoint(pos):
            return False
        local_y = pos[1] - self.inventory_panel_rect.y
        list_top = 36
        if local_y < list_top:
            return True
        index = (local_y - list_top + self.inventory_scroll) // self.inventory_item_height
        entries = self.get_inventory_display_entries()
        if 0 <= index < len(entries):
            entry = entries[int(index)]
            kind = entry.get("kind")
            if kind == "item":
                self.selected_inventory_item = entry.get("name")
                self.selected_weapon_id = None
            elif kind == "weapon":
                w = entry.get("weapon") or {}
                self.selected_weapon_id = w.get("id")
                self.selected_inventory_item = None
        return True


    def handle_menu_button_click(self, pos: Tuple[int, int]) -> bool:
        for title, rect in self.menu_button_rects.items():
            if rect.collidepoint(pos):
                if self.menu_visible and title != self.active_menu:
                    return True
                if self.active_menu == title and self.menu_visible:
                    self.menu_visible = False
                    return True
                self.active_menu = title
                self.menu_visible = True
                self.panel_scroll = 0
                self.palette_visible = False
                self.settings_visible = False
                self.inventory_visible = False
                return True
        return False

    def handle_menu_click(self, pos: Tuple[int, int]) -> bool:
        if not self.menu_visible:
            return False
        if not self.menu_panel_rect.collidepoint(pos):
            return False
        section = next((sec for sec in self.sections if sec.title == self.active_menu), None)
        if section is None:
            return False
        local_y = pos[1] - self.menu_panel_rect.y
        item_height = 28
        index = (local_y + self.panel_scroll) // item_height
        if 0 <= index < len(section.buttons):
            button = section.buttons[int(index)]
            if button.toggle:
                button.toggled = not button.toggled
            button.callback()
            return True
        return True

    def handle_button_click(self, button: Button, pos: Tuple[int, int]) -> bool:
        if button.rect.collidepoint(pos):
            if button.toggle:
                button.toggled = not button.toggled
            button.callback()
            return True
        return False

    def handle_section_click(self, pos: Tuple[int, int]) -> bool:
        for section in self.sections:
            if section.rect.collidepoint(pos):
                section.expanded = not section.expanded
                self.section_states[section.title] = section.expanded
                return True
        return False

    def scroll_panel(self, delta: int) -> None:
        max_scroll = max(0, self.total_button_height() - (self.ui_rect.height - 20))
        self.panel_scroll = max(0, min(max_scroll, self.panel_scroll + delta))

    def scroll_palette(self, delta: int) -> None:
        item_height = 26
        list_top = 28 + 10
        list_height = self.palette_panel_rect.height - list_top - 10
        if self.palette_tab == "tiles":
            total_items = len(self.tile_types)
        else:
            total_items = len(self.replacement_images)
        total_height = total_items * item_height
        max_scroll = max(0, total_height - list_height)
        self.palette_scroll = max(0, min(max_scroll, self.palette_scroll + delta))

    def scroll_menu(self, delta: int) -> None:
        if not self.menu_visible:
            return
        section = next((sec for sec in self.sections if sec.title == self.active_menu), None)
        if section is None:
            return
        item_height = 28
        total_height = len(section.buttons) * item_height
        visible_height = self.menu_panel_rect.height
        max_scroll = max(0, total_height - visible_height)
        self.panel_scroll = max(0, min(max_scroll, self.panel_scroll + delta))

    def get_inventory_items(self) -> List[Tuple[str, int]]:
        if self.player is None:
            return []
        items = [(name, count) for name, count in self.player.inventory.items() if count > 0]
        items.sort(key=lambda entry: entry[0])
        return items
    def get_weapon_items(self) -> List[Dict]:
        if self.player is None:
            return []
        def sort_key(w: Dict) -> Tuple[int, str]:
            rarity = w.get("rarity", "common")
            rarity_rank = WEAPON_RARITIES.index(rarity) if rarity in WEAPON_RARITIES else 0
            return (rarity_rank, w.get("name", ""))
        weapons = list(self.player.weapons)
        weapons.sort(key=sort_key, reverse=True)
        return weapons
    def get_inventory_display_entries(self) -> List[Dict]:
        entries: List[Dict] = []
        entries.append({"kind": "header", "label": "Items"})
        for name, count in self.get_inventory_items():
            entries.append({"kind": "item", "name": name, "count": count})
        entries.append({"kind": "header", "label": "Weapons"})
        for w in self.get_weapon_items():
            entries.append({"kind": "weapon", "weapon": w})
        return entries



    def get_weapon_by_id(self, weapon_id: str) -> Optional[Dict]:
        if self.player is None:
            return None
        for w in self.player.weapons:
            if w.get("id") == weapon_id:
                return w
        return None

    def weapon_is_bound(self, weapon_id: str) -> bool:
        if self.player is None:
            return False
        return weapon_id in self.player.weapon_bindings.values()

    def equip_weapon(self, weapon_id: str) -> None:
        if self.player is None:
            return
        if self.get_weapon_by_id(weapon_id) is None:
            return
        self.player.equipped_weapon_id = weapon_id
        self.selected_weapon_id = weapon_id

    def bind_weapon_to_slot(self, weapon_id: str, slot: int) -> None:
        if self.player is None:
            return
        if slot < 1 or slot > 9:
            return
        if self.get_weapon_by_id(weapon_id) is None:
            return
        # Unbind any weapon already on this slot.
        if slot in self.player.weapon_bindings:
            self.player.weapon_bindings.pop(slot, None)
        # Remove previous binding of this weapon, if any.
        for s, wid in list(self.player.weapon_bindings.items()):
            if wid == weapon_id:
                self.player.weapon_bindings.pop(s, None)
        self.player.weapon_bindings[slot] = weapon_id

    

    def add_weapon_to_inventory(self, weapon: Dict) -> None:
        if self.player is None:
            return
        # Ensure id + signature are present.
        if not weapon.get("id"):
            weapon["id"] = f"w{random.randrange(0, 1<<30):08x}"
        if not weapon.get("sig"):
            weapon["sig"] = f"{weapon.get('type','')}|{weapon.get('rarity','')}|{weapon.get('name', weapon.get('name_base','Weapon'))}"
        # Duplicate weapons convert into ammo (or refill ammo for ammo-based weapons).
        for existing in self.player.weapons:
            if existing.get("sig") == weapon.get("sig"):
                # If it's an ammo weapon, refill that weapon first.
                if bool(existing.get("uses_ammo")) or int(existing.get("ammo_max", 0)) > 0:
                    mx = int(existing.get("ammo_max", 0))
                    if mx <= 0:
                        mx = int(weapon.get("ammo_max", 0))
                        existing["ammo_max"] = mx
                    gain = int(weapon.get("ammo", 0))
                    if gain <= 0:
                        gain = max(4, mx // 5) if mx > 0 else 6
                    existing["ammo"] = min(mx, int(existing.get("ammo", 0)) + gain) if mx > 0 else int(existing.get("ammo", 0)) + gain
                else:
                    # Melee duplicates become generic ammo pickups for future guns.
                    self.add_inventory_item("ammo", max(3, int(weapon.get("stats", {}).get("damage", 1)) + 2))
                return

        # New weapon acquired.
        # Normalize ammo fields if present.
        weapon["uses_ammo"] = bool(weapon.get("uses_ammo", False))
        weapon["ammo_item"] = str(weapon.get("ammo_item", "ammo"))
        weapon["ammo_max"] = int(weapon.get("ammo_max", 0))
        weapon["ammo"] = int(weapon.get("ammo", 0))
        self.player.weapons.append(weapon)
        if self.selected_weapon_id is None:
            self.selected_weapon_id = weapon["id"]

        # Auto-equip unless the current equipped weapon is bound.
        current = self.player.equipped_weapon_id
        current_is_bound = bool(current) and self.weapon_is_bound(current)
        if current is None or not current_is_bound:
            self.equip_weapon(weapon["id"])


    def get_equipped_weapon(self) -> Optional[Dict]:
        if self.player is None:
            return None
        if self.player.equipped_weapon_id:
            return self.get_weapon_by_id(self.player.equipped_weapon_id)
        return None

    def get_mob_at_screen(self, screen_pos: Tuple[int, int]) -> Optional[Mob]:
        # screen_pos must already be adjusted for zoom.
        best = None
        best_dist = 1e9
        for mob in self.mobs:
            screen_x, screen_y = self.renderer.iso_to_screen(
                int(round(mob.x)),
                int(round(mob.y)),
                mob.height,
                self.offset,
            )
            cx = screen_x + TILE_WIDTH // 2
            cy = screen_y + TILE_HEIGHT // 2 - 6
            dx = screen_pos[0] - cx
            dy = screen_pos[1] - cy
            d = dx * dx + dy * dy
            if d < best_dist and d <= (16 * 16):
                best = mob
                best_dist = d
        return best

    def player_attack(self, target: Optional[Mob], force: bool = False) -> None:
        if self.player is None:
            return
        player = self.player
        if player.health <= 0:
            return
        if player.attack_timer > 0 and not force:
            return
        weapon = self.get_equipped_weapon()
        if weapon is None:
            # Fallback: basic melee punch.
            weapon = {
                "behavior": "melee",
                "stats": {"damage": 1, "range": 1.5, "cooldown": 0.6, "crit": 0.05},
                "projectile": None,
                "on_hit": None,
                "rarity": "common",
            }
        stats = weapon.get("stats", {})
        damage = int(stats.get("damage", 1))
        rng_range = float(stats.get("range", 1.5))
        cooldown = float(stats.get("cooldown", 0.6))
        behavior = weapon.get("behavior", "melee")
        on_hit = weapon.get("on_hit", None)
        # Determine aim direction
        aim_dx, aim_dy = player.direction
        if target is not None:
            dx = target.x - player.x
            dy = target.y - player.y
            dist = math.hypot(dx, dy)
            if dist > 0.001:
                aim_dx = dx / dist
                aim_dy = dy / dist
                player.attack_direction = player.direction
        # Melee
        if behavior == "melee":
            if target is not None:
                if math.hypot(target.x - player.x, target.y - player.y) <= rng_range:
                    target.health -= damage
                    player.attack_timer = cooldown
                    if self.audio:
                        self.audio.play_at("attack", (player.x, player.y), (player.x, player.y), 12, 0.75)
            return

        # Ranged / projectile behaviors
        proj = weapon.get("projectile") or {}
        speed = float(proj.get("speed", 8.0))
        lifetime = float(proj.get("lifetime", 1.0))
        pierce = int(proj.get("pierce", 0))
        homing = bool(proj.get("homing", False))
        burst = int(proj.get("burst", 1)) if behavior in ("burst",) else 1
        spread = float(proj.get("spread", 0.0))
        explode_radius = float(proj.get("explode_radius", 0.0))

        # If target is too far, still allow firing toward direction.
        if target is not None and math.hypot(target.x - player.x, target.y - player.y) > rng_range:
            target = None

        base_angle = math.atan2(aim_dy, aim_dx)
        shots = max(1, burst)

        # Ammo handling (energy weapons, etc.)
        if bool(weapon.get("uses_ammo")) or int(weapon.get("ammo_max", 0)) > 0:
            ammo_item = str(weapon.get("ammo_item", "ammo"))
            mx = int(weapon.get("ammo_max", 0))
            # Auto-reload from inventory ammo if empty.
            if int(weapon.get("ammo", 0)) <= 0 and mx > 0:
                available = int(player.inventory.get(ammo_item, 0))
                if available > 0:
                    take = min(mx, available)
                    weapon["ammo"] = int(weapon.get("ammo", 0)) + take
                    self.remove_inventory_item(ammo_item, take)
            if int(weapon.get("ammo", 0)) <= 0:
                # Out of ammo.
                return
            # Clamp shots to available ammo.
            shots = min(shots, int(weapon.get("ammo", 0)))
            weapon["ammo"] = max(0, int(weapon.get("ammo", 0)) - shots)

        for i in range(shots):
            ang = base_angle
            if shots > 1:
                center = (shots - 1) / 2.0
                ang += (i - center) * spread
            vx = math.cos(ang) * speed
            vy = math.sin(ang) * speed
            p = Projectile(
                x=player.x,
                y=player.y,
                height=player.height,
                vx=vx,
                vy=vy,
                damage=damage,
                lifetime=lifetime,
                homing=homing,
                target=target if homing else None,
                pierce=pierce,
                on_hit=on_hit,
                color=tuple(proj.get("color", WEAPON_RARITY_COLORS.get(weapon.get("rarity", "common"), (240, 240, 240)))),
            )
            # stash explode radius in on_hit tag for now (lightweight)
            if explode_radius > 0 and p.on_hit is None:
                p.on_hit = f"explode:{explode_radius:.2f}"
            self.projectiles.append(p)
        player.attack_timer = cooldown
        if self.audio:
            self.audio.play_at("attack", (player.x, player.y), (player.x, player.y), 12, 0.6)

    def update_projectiles(self, dt: float) -> None:
        if self.player is None:
            return
        for p in list(self.projectiles):
            p.timer += dt
            if p.timer >= p.lifetime:
                self.projectiles.remove(p)
                continue
            # Homing steer
            if p.homing and p.target is not None and p.target in self.mobs:
                dx = p.target.x - p.x
                dy = p.target.y - p.y
                dist = math.hypot(dx, dy)
                if dist > 0.001:
                    desired_vx = dx / dist * math.hypot(p.vx, p.vy)
                    desired_vy = dy / dist * math.hypot(p.vx, p.vy)
                    turn = min(8.0 * dt, 1.0)
                    p.vx = p.vx * (1 - turn) + desired_vx * turn
                    p.vy = p.vy * (1 - turn) + desired_vy * turn
            # Move
            p.x += p.vx * dt
            p.y += p.vy * dt
            # Collide with mobs
            hit_mob = None
            for mob in self.mobs:
                if math.hypot(mob.x - p.x, mob.y - p.y) <= 0.55:
                    hit_mob = mob
                    break
            if hit_mob is not None:
                hit_mob.health -= p.damage
                # On-hit effects (minimal set)
                if p.on_hit:
                    if p.on_hit == "burn":
                        hit_mob.aggression = min(3.0, hit_mob.aggression + 0.6)
                        hit_mob.health -= 1
                    elif p.on_hit == "slow":
                        hit_mob.aggression = max(0.0, hit_mob.aggression - 0.8)
                    elif p.on_hit.startswith("explode:"):
                        try:
                            radius = float(p.on_hit.split(":", 1)[1])
                        except Exception:
                            radius = 1.5
                        for other in self.mobs:
                            if other is hit_mob:
                                continue
                            if math.hypot(other.x - p.x, other.y - p.y) <= radius:
                                other.health -= max(1, int(p.damage * 0.6))
                if p.pierce <= 0:
                    if p in self.projectiles:
                        self.projectiles.remove(p)
                else:
                    p.pierce -= 1

    def draw_projectiles(self) -> None:
        screen_w, screen_h = self.screen.get_size()
        margin = 120
        for p in self.projectiles:
            tile = self.world.get_tile(int(round(p.x)), int(round(p.y)))
            if tile is None:
                continue
            screen_x, screen_y = self.renderer.iso_to_screen(
                int(round(p.x)),
                int(round(p.y)),
                tile.height,
                self.offset,
            )
            cx = screen_x + TILE_WIDTH // 2
            cy = screen_y + TILE_HEIGHT // 2 - 8
            if cx < -margin or cx > screen_w + margin or cy < -margin or cy > screen_h + margin:
                continue
            pygame.draw.circle(self.screen, (10, 10, 20), (cx, cy), 3)
            pygame.draw.circle(self.screen, p.color, (cx, cy), 2)



    def scroll_inventory_selection(self, delta: int) -> None:
        items = self.get_inventory_items()
        if not items:
            self.selected_inventory_item = None
            return
        names = [name for name, _ in items]
        if self.selected_inventory_item not in names:
            self.selected_inventory_item = names[0]
            return
        index = names.index(self.selected_inventory_item)
        index = (index + delta) % len(names)
        self.selected_inventory_item = names[index]
        visible = (self.inventory_panel_rect.height - 40) // self.inventory_item_height
        min_scroll = max(0, index - visible + 1)
        self.inventory_scroll = min_scroll * self.inventory_item_height

    def add_inventory_item(self, item: str, count: int = 1) -> None:
        if self.player is None:
            return
        self.player.inventory[item] = self.player.inventory.get(item, 0) + count
        # Do not steal the current selection when picking up new items.
        if self.selected_inventory_item is None and self.selected_weapon_id is None:
            self.selected_inventory_item = item

    def remove_inventory_item(self, item: str, count: int = 1) -> None:
        if self.player is None:
            return
        current = self.player.inventory.get(item, 0)
        new_count = max(0, current - count)
        if new_count == 0:
            self.player.inventory.pop(item, None)
            if self.selected_inventory_item == item:
                self.selected_inventory_item = None
        else:
            self.player.inventory[item] = new_count

    def total_button_height(self) -> int:
        if not self.sections:
            return 0
        header_height = 24
        spacing = 6
        button_height = 26
        total = 10
        for section in self.sections:
            total += header_height + spacing
            if section.expanded:
                total += len(section.buttons) * (button_height + spacing)
        return total

    def scroll_texture_list(self, delta: int) -> None:
        total_height = len(self.replacement_images) * self.texture_item_height
        visible = self.texture_list_rect.height - 22
        max_scroll = max(0, total_height - visible)
        self.texture_scroll = max(0, min(max_scroll, self.texture_scroll + delta))

    def handle_texture_click(self, pos: Tuple[int, int]) -> bool:
        if self.texture_list_header_rect.collidepoint(pos):
            self.texture_list_collapsed = not self.texture_list_collapsed
            return True
        if self.texture_list_collapsed:
            return True
        local_y = pos[1] - self.texture_list_rect.top + self.texture_scroll - 22
        if local_y < 0:
            return True
        index = local_y // self.texture_item_height
        if 0 <= index < len(self.replacement_images):
            self.replacement_index = int(index)
            return True
        return False

    def is_over_ui(self, pos: Tuple[int, int]) -> bool:
        return (
            self.settings_button_rect.collidepoint(pos)
            or self.player_button_rect.collidepoint(pos)
            or (self.settings_visible and self.settings_panel_rect.collidepoint(pos))
            or (self.palette_visible and self.palette_panel_rect.collidepoint(pos))
            or any(rect.collidepoint(pos) for rect in self.menu_button_rects.values())
            or (self.menu_visible and self.menu_panel_rect.collidepoint(pos))
            or (self.inventory_visible and self.inventory_panel_rect.collidepoint(pos))
            or self.get_selected_tile_panel_rect().collidepoint(pos)
        )

    def render_grid(self) -> None:
        for y in range(self.world.height):
            for x in range(self.world.width):
                tile = self.world.get_tile(x, y)
                if tile is None:
                    continue
                neighbor_heights = [
                    self.world.get_tile(x - 1, y),
                    self.world.get_tile(x + 1, y),
                    self.world.get_tile(x, y - 1),
                    self.world.get_tile(x, y + 1),
                ]
                for neighbor in neighbor_heights:
                    neighbor_height = neighbor.height if neighbor else min(tile.height, 0)
                    self.renderer.draw_vertical_face(
                        x,
                        y,
                        tile.height,
                        neighbor_height,
                        tile.tile_type,
                        self.offset,
                    )
        for y in range(self.world.height):
            for x in range(self.world.width):
                tile = self.world.get_tile(x, y)
                if tile and self.should_render_tile(tile):
                    self.renderer.draw_tile(tile, x, y, self.offset)

    def draw_tree_overlays(self) -> None:
        screen_w, screen_h = self.screen.get_size()
        margin = 160
        for (x, y), tile in self.world.tiles.items():
            if not tile.texture_override:
                continue
            if not self.renderer.is_tree_override(tile.texture_override):
                continue
            if not self.should_render_tile(tile):
                continue
            screen_x, screen_y = self.renderer.iso_to_screen(x, y, tile.height, self.offset)
            if screen_x < -margin or screen_x > screen_w + margin or screen_y < -margin or screen_y > screen_h + margin:
                continue
            sprite = self.renderer.load_sprite(
                tile.texture_override,
                tile.flip_x,
                tile.texture_tint,
                tile.texture_scale,
            )
            if sprite is None:
                continue
            base_x = screen_x + TILE_WIDTH // 2
            base_y = screen_y + TILE_HEIGHT // 2
            dest_x = base_x - sprite.get_width() // 2
            dest_y = base_y - sprite.get_height()
            self.screen.blit(sprite, (dest_x, dest_y))

    def draw_water_reflections(self) -> None:
        shimmer = (math.sin(self.day_time * math.pi * 2) + 1) / 2
        alpha = int(60 + shimmer * 70)
        for (x, y), tile in self.world.tiles.items():
            if tile.tile_type != "water":
                continue
            if (x + y) % 3 != 0:
                continue
            screen_x, screen_y = self.renderer.iso_to_screen(x, y, tile.height, self.offset)
            line_rect = pygame.Rect(screen_x + 6, screen_y + 5, 10, 2)
            highlight = pygame.Surface(line_rect.size, pygame.SRCALPHA)
            highlight.fill((200, 220, 255, alpha))
            self.screen.blit(highlight, line_rect.topleft)

    def draw_help(self) -> None:
        if not self.show_help:
            return
        lines = [
            "Controls:",
            "Left Click: apply tool (add) | Right Click: opposite (subtract)",
            "1-6: select tile | 9/0: brush size",
            "Palette: use Editor > Palette Toggle to pick tiles/textures",
            "Menus: use category buttons for editor tools",
            "Player: button/P toggle, WASD move, Space jump forward, M mine",
            "Player: I inventory, Scroll select item, RMB place, LMB dig (range 5)",
            "Player: Arrow up/down swim vertically, Arrow left/right strafe",
            "Weather: dynamic rain, storms, snow, fog, dust, wind by biome",
            "Events: alien invasions can occur over time",
            "Audio: footsteps, wildlife, water, and combat sounds (range-based)",
            "Shaders: use Editor > Shader: Generate to refresh shading",
            "U/Y: undo/redo",
            "R/G: regenerate",
            "S/L: save/load | E: export image | Settings: Save/Load buttons",
            "Arrows: pan camera (edit mode) | Z: zoom toggle | H: toggle help | Esc: close menus, Esc x2 exit",
            "F11: toggle fullscreen",
        ]
        padding = 8
        rect_height = len(lines) * 20 + padding * 2
        overlay = pygame.Surface((420, rect_height), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 150))
        for i, line in enumerate(lines):
            text_surface = self.ui_font.render(line, True, (240, 240, 240))
            overlay.blit(text_surface, (padding, padding + i * 20))
        hud_x, hud_y = self.get_hud_position()
        self.screen.blit(overlay, (10, hud_y + 80))

    def draw_biome_label(self) -> None:
        name = "Unknown"
        if self.current_biome:
            name = self.current_biome.get("name", "Unknown").replace("_", " ").title()
        label = self.ui_font.render(f"Biome: {name}", True, (230, 230, 230))
        padding = 8
        rect = label.get_rect()
        rect.top = 10
        rect.right = self.screen.get_width() - 10
        panel = pygame.Surface((rect.width + padding * 2, rect.height + padding * 2), pygame.SRCALPHA)
        panel.fill((0, 0, 0, 150))
        panel.blit(label, (padding, padding))
        self.screen.blit(panel, (rect.left - padding, rect.top - padding))

    def get_item_color(self, item: str) -> Tuple[int, int, int]:
        if item in ITEM_COLORS:
            return ITEM_COLORS[item]
        if item in DEFAULT_COLORS:
            return DEFAULT_COLORS[item]
        return (200, 200, 200)
    def render_clipped_text(self, font: pygame.font.Font, text: str, color: Tuple[int, int, int], max_width: int) -> pygame.Surface:
        s = str(text)
        if max_width <= 0:
            return font.render('', True, color)
        if font.size(s)[0] <= max_width:
            return font.render(s, True, color)
        ell = '...'
        base = s
        while base and font.size(base + ell)[0] > max_width:
            base = base[:-1]
        if not base:
            return font.render(ell, True, color)
        return font.render(base + ell, True, color)

    def draw_inventory_menu(self) -> None:
        if not self.inventory_visible:
            return
        rect = self.inventory_panel_rect
        panel = pygame.Surface(rect.size, pygame.SRCALPHA)
        panel.fill((25, 25, 40, 230))
        pygame.draw.rect(panel, (10, 10, 20), panel.get_rect(), 2)
        header = self.ui_font.render("Inventory", True, (230, 230, 230))
        panel.blit(header, (10, 6))

        list_top = 36
        entries = self.get_inventory_display_entries()
        start_index = max(0, self.inventory_scroll // self.inventory_item_height)
        visible_count = (rect.height - list_top - 10) // self.inventory_item_height + 1
        end_index = min(len(entries), start_index + visible_count)

        bindings: Dict[int, str] = {}
        if self.player is not None:
            bindings = dict(self.player.weapon_bindings)

        for idx in range(start_index, end_index):
            entry = entries[idx]
            item_y = list_top + (idx - start_index) * self.inventory_item_height
            item_rect = pygame.Rect(10, item_y, rect.width - 20, self.inventory_item_height - 4)

            kind = entry.get("kind")
            if kind == "header":
                label = self.ui_font.render(str(entry.get("label", "")).upper(), True, (180, 190, 210))
                panel.blit(label, (item_rect.x, item_rect.y + 2))
                continue

            pygame.draw.rect(panel, (50, 60, 80), item_rect, border_radius=4)

            if kind == "item":
                name = entry.get("name", "")
                count = int(entry.get("count", 0))
                if name == self.selected_inventory_item:
                    pygame.draw.rect(panel, (90, 110, 150), item_rect, 2, border_radius=4)
                color = self.get_item_color(name)
                pygame.draw.rect(panel, color, pygame.Rect(item_rect.x + 6, item_rect.y + 4, 14, 14))
                count_label = self.ui_font.render(str(count), True, (200, 200, 210))
                count_x = rect.width - 10 - count_label.get_width()
                panel.blit(count_label, (count_x, item_rect.y + 2))
                max_name_w = max(40, count_x - (item_rect.x + 26) - 10)
                label = self.render_clipped_text(self.ui_font, name.title(), (230, 230, 230), max_name_w)
                panel.blit(label, (item_rect.x + 26, item_rect.y + 2))
            elif kind == "weapon":
                w = entry.get("weapon") or {}
                wid = w.get("id", "")
                if wid == self.selected_weapon_id:
                    pygame.draw.rect(panel, (120, 140, 190), item_rect, 2, border_radius=4)
                rarity = w.get("rarity", "common")
                color = WEAPON_RARITY_COLORS.get(rarity, (220, 220, 220))
                pygame.draw.rect(panel, color, pygame.Rect(item_rect.x + 6, item_rect.y + 4, 14, 14))
                name = str(w.get("name", "Weapon"))
                dmg = int(w.get("stats", {}).get("damage", 1))
                label = self.ui_font.render(f"{name}", True, (235, 235, 235))
                panel.blit(label, (item_rect.x + 26, item_rect.y + 2))

                slot_label = ""
                for slot, bound_id in bindings.items():
                    if bound_id == wid:
                        slot_label = f"[{slot}]"
                        break
                # right side: slot + dmg
                ammo_txt = ""
                if bool(w.get("uses_ammo")) or int(w.get("ammo_max", 0)) > 0:
                    ammo_txt = f" {int(w.get('ammo',0))}/{int(w.get('ammo_max',0))}"
                right_text = f"{slot_label} {dmg} dmg{ammo_txt}".strip()
                right = self.ui_font.render(right_text, True, (205, 210, 225))
                right_x = rect.width - 10 - right.get_width()
                panel.blit(right, (right_x, item_rect.y + 2))
                max_name_w = max(60, right_x - (item_rect.x + 26) - 10)
                label = self.render_clipped_text(self.ui_font, f"{name}", (235, 235, 235), max_name_w)
                panel.blit(label, (item_rect.x + 26, item_rect.y + 2))

        hint = "Click weapon + press 1-9 to bind"
        hint_surf = getattr(self, 'ui_small_font', self.ui_font).render(hint, True, (190, 190, 200))
        panel.blit(hint_surf, (10, rect.height - 18))

        self.screen.blit(panel, rect.topleft)


    def draw_selected_tile_panel(self) -> None:
        rect = self.get_selected_tile_panel_rect()
        panel = pygame.Surface(rect.size, pygame.SRCALPHA)
        panel.fill((20, 20, 30, 210))
        pygame.draw.rect(panel, (10, 10, 20), panel.get_rect(), 2)
        label = self.ui_font.render("Selected", True, (230, 230, 230))
        panel.blit(label, (10, 6))
        selected = self.selected_inventory_item if self.player_mode and self.selected_inventory_item else self.selected_tile_type
        color = self.get_item_color(selected)
        pygame.draw.rect(panel, color, pygame.Rect(10, 28, 18, 18))
        name_label = self.ui_font.render(selected.title(), True, (230, 230, 230))
        panel.blit(name_label, (36, 28))
        if self.player_mode and self.selected_inventory_item and self.player:
            count = self.player.inventory.get(self.selected_inventory_item, 0)
            count_label = self.ui_font.render(f"x{count}", True, (200, 200, 210))
            panel.blit(count_label, (rect.width - 40, 28))
        self.screen.blit(panel, rect.topleft)

    def get_selected_tile_panel_rect(self) -> pygame.Rect:
        rect = pygame.Rect(10, self.screen.get_height() - 80, 210, 60)
        if self.inventory_visible and rect.colliderect(self.inventory_panel_rect):
            rect = rect.move(0, -self.inventory_panel_rect.height - 10)
        return rect

    def draw_exit_prompt(self) -> None:
        if self.exit_prompt_timer <= 0:
            return
        message = "Press Esc again to exit."
        text = self.ui_font.render(message, True, (240, 240, 240))
        padding = 10
        rect = text.get_rect()
        rect.inflate_ip(padding * 2, padding * 2)
        rect.centerx = self.screen.get_width() // 2
        rect.top = 10
        panel = pygame.Surface(rect.size, pygame.SRCALPHA)
        panel.fill((0, 0, 0, 170))
        panel.blit(text, (padding, padding))
        self.screen.blit(panel, rect.topleft)

    def draw_invasion_notice(self) -> None:
        if self.invasion_notice_timer <= 0:
            return
        message = "Alien invasion incoming!"
        text = self.ui_font.render(message, True, (240, 240, 240))
        padding = 10
        rect = text.get_rect()
        rect.inflate_ip(padding * 2, padding * 2)
        rect.centerx = self.screen.get_width() // 2
        rect.top = 48
        panel = pygame.Surface(rect.size, pygame.SRCALPHA)
        panel.fill((30, 20, 40, 180))
        panel.blit(text, (padding, padding))
        self.screen.blit(panel, rect.topleft)

    def get_hud_position(self) -> Tuple[int, int]:
        base_bottom = self.settings_button_rect.bottom
        base_bottom = max(base_bottom, self.player_button_rect.bottom)
        if self.settings_visible:
            base_bottom = max(base_bottom, self.settings_panel_rect.bottom)
        if self.palette_visible:
            base_bottom = max(base_bottom, self.palette_panel_rect.bottom)
        if self.menu_visible:
            base_bottom = max(base_bottom, self.menu_panel_rect.bottom)
        if self.inventory_visible:
            base_bottom = max(base_bottom, self.inventory_panel_rect.bottom)
        return 10, base_bottom + 10

    def draw_hud(self) -> None:
        if self.player is None:
            return
        panel_width = 220
        panel_height = 70
        panel = pygame.Surface((panel_width, panel_height), pygame.SRCALPHA)
        panel.fill((20, 20, 30, 200))
        header = self.info_font.render("Player", True, (230, 230, 230))
        panel.blit(header, (10, 6))
        for i in range(self.player.health):
            pygame.draw.rect(panel, (200, 60, 60), pygame.Rect(10 + i * 16, 26, 12, 10))
        items = list(self.player.inventory.items())[:5]
        for idx, (item, count) in enumerate(items):
            color = ITEM_COLORS.get(item, (200, 200, 200))
            pygame.draw.rect(panel, color, pygame.Rect(10 + idx * 18, 44, 12, 12))
            text = self.info_font.render(str(count), True, (230, 230, 230))
            panel.blit(text, (10 + idx * 18 + 12, 44))
        panel_pos = self.get_hud_position()
        self.screen.blit(panel, panel_pos)

    def draw_player(self) -> None:
        if not self.player_mode or self.player is None:
            return
        player = self.player
        screen_x, screen_y = self.renderer.iso_to_screen(
            int(round(player.x)),
            int(round(player.y)),
            player.height,
            self.offset,
        )
        center = (screen_x + TILE_WIDTH // 2, screen_y + TILE_HEIGHT // 2)
        body_color = (60, 180, 220) if player.is_swimming else (240, 200, 120)
        outline = (30, 30, 40)
        shadow = (10, 10, 15, 120)
        shadow_surface = pygame.Surface((22, 12), pygame.SRCALPHA)
        pygame.draw.ellipse(shadow_surface, shadow, shadow_surface.get_rect())
        self.screen.blit(shadow_surface, (center[0] - 11, center[1] + 8))
        bob = math.sin(player.animation_time * 4) * 1.5
        torso = pygame.Rect(center[0] - 4, center[1] - 6 + int(bob), 8, 10)
        head = pygame.Rect(center[0] - 3, center[1] - 13 + int(bob), 6, 6)
        left_arm = pygame.Rect(center[0] - 6, center[1] - 6, 2, 8)
        right_arm = pygame.Rect(center[0] + 4, center[1] - 6, 2, 8)
        left_leg = pygame.Rect(center[0] - 4, center[1] + 4, 3, 6)
        right_leg = pygame.Rect(center[0] + 1, center[1] + 4, 3, 6)
        animation = math.sin(player.animation_time * 6) * 2
        attack_offset = -3 if player.attack_timer > 0 else 0
        left_arm = left_arm.move(0, int(animation))
        right_arm = right_arm.move(0, int(-animation) + attack_offset)
        left_leg = left_leg.move(0, int(-animation))
        right_leg = right_leg.move(0, int(animation))
        for rect in [head, torso, left_arm, right_arm, left_leg, right_leg]:
            pygame.draw.rect(self.screen, outline, rect.inflate(2, 2))
            pygame.draw.rect(self.screen, body_color, rect)
        highlight = pygame.Rect(torso.x + 1, torso.y + 1, max(2, torso.width - 2), max(2, torso.height - 4))
        pygame.draw.rect(self.screen, (255, 220, 160), highlight, 1)
        pygame.draw.rect(self.screen, (250, 250, 250), pygame.Rect(center[0] - 1, center[1] - 11, 2, 2))
        if player.attack_timer > 0:
            stab_progress = 1 - min(1.0, player.attack_timer / 0.6)
            dx, dy = player.attack_direction
            length = 10 + stab_progress * 8
            base_angle = math.atan2(dy, dx) if dx != 0 or dy != 0 else 0
            start = (center[0], center[1] - 2)
            end = (
                start[0] + math.cos(base_angle) * length,
                start[1] + math.sin(base_angle) * length,
            )
            pygame.draw.line(self.screen, (240, 220, 180), start, end, 2)
            perp = base_angle + math.pi / 2
            tip_left = (
                end[0] + math.cos(perp) * 2,
                end[1] + math.sin(perp) * 2,
            )
            tip_right = (
                end[0] - math.cos(perp) * 2,
                end[1] - math.sin(perp) * 2,
            )
            point = (
                end[0] + math.cos(base_angle) * 4,
                end[1] + math.sin(base_angle) * 4,
            )
            pygame.draw.polygon(self.screen, (255, 230, 200), [tip_left, tip_right, point])

    def draw_texture_list(self) -> None:
        rect = self.texture_list_rect
        self.texture_list_header_rect = pygame.Rect(rect.x, rect.y, rect.width, 24)
        view = pygame.Surface(rect.size, pygame.SRCALPHA)
        view.fill((15, 15, 25, 200))
        pygame.draw.rect(view, (10, 10, 20), view.get_rect(), 1)
        header_label = "Textures [+]" if self.texture_list_collapsed else "Textures [-]"
        header = self.ui_font.render(header_label, True, (220, 220, 230))
        view.blit(header, (6, 4))
        list_offset = 22
        if self.texture_list_collapsed:
            self.screen.blit(view, rect.topleft)
            return
        start_index = max(0, self.texture_scroll // self.texture_item_height)
        end_index = min(
            len(self.replacement_images),
            start_index + (rect.height - list_offset) // self.texture_item_height + 2,
        )
        for idx in range(start_index, end_index):
            image_path = self.replacement_images[idx]
            item_y = idx * self.texture_item_height - self.texture_scroll + list_offset
            item_rect = pygame.Rect(0, item_y, rect.width - self.texture_sidebar_width - 4, self.texture_item_height)
            if idx == self.replacement_index:
                pygame.draw.rect(view, (60, 90, 130), item_rect)
            thumb = self.get_texture_thumb(image_path)
            view.blit(thumb, (6, item_y + 6))
            label = self.ui_font.render(image_path.stem, True, (220, 220, 230))
            view.blit(label, (36, item_y + 8))
        self.draw_texture_scrollbar(view)
        self.screen.blit(view, rect.topleft)

    def get_texture_thumb(self, path: Path) -> pygame.Surface:
        key = str(path)
        if key in self.texture_thumbs:
            return self.texture_thumbs[key]
        surface = pygame.image.load(str(path)).convert_alpha()
        scaler = pygame.transform.smoothscale if self.settings.get("high_quality", True) else pygame.transform.scale
        thumb = scaler(surface, (24, 24))
        self.texture_thumbs[key] = thumb
        return thumb

    def draw_texture_scrollbar(self, surface: pygame.Surface) -> None:
        total_height = len(self.replacement_images) * self.texture_item_height
        if total_height <= 0:
            return
        visible = self.texture_list_rect.height - 22
        if total_height <= visible:
            return
        bar_height = max(20, int(visible * (visible / total_height)))
        scroll_ratio = self.texture_scroll / (total_height - visible)
        bar_y = int(22 + scroll_ratio * (visible - bar_height))
        bar_rect = pygame.Rect(
            surface.get_width() - self.texture_sidebar_width,
            bar_y,
            self.texture_sidebar_width - 2,
            bar_height,
        )
        pygame.draw.rect(surface, (70, 90, 120), bar_rect)

    def settings_options(self) -> List[Tuple[str, str]]:
        return [
            ("water_reflections", "Water reflections"),
            ("show_stars", "Show stars"),
            ("day_night_cycle", "Day/night cycle"),
            ("high_quality", "High quality"),
            ("vsync", "Vsync"),
            ("audio_enabled", "Audio"),
        ]

    def settings_actions(self) -> List[Tuple[str, callable]]:
        return [
            ("Save World", self.save_world_dialog),
            ("Load World", self.load_world_dialog),
        ]

    def settings_option_start(self) -> int:
        return 34 + len(self.settings_actions()) * 28 + 6

    def settings_slider_start(self) -> int:
        return self.settings_option_start() + len(self.settings_options()) * 28 + 12

    def get_day_speed_slider_rect(self) -> pygame.Rect:
        slider_y = self.settings_panel_rect.y + self.settings_slider_start()
        return pygame.Rect(self.settings_panel_rect.x + 20, slider_y, 260, 10)

    def get_subsurface_slider_rect(self) -> pygame.Rect:
        slider_y = self.settings_panel_rect.y + self.settings_slider_start() + 34
        return pygame.Rect(self.settings_panel_rect.x + 20, slider_y, 260, 10)

    def get_audio_slider_rect(self) -> pygame.Rect:
        slider_y = self.settings_panel_rect.y + self.settings_slider_start() + 68
        return pygame.Rect(self.settings_panel_rect.x + 20, slider_y, 260, 10)

    def update_day_speed_from_mouse(self, mouse_x: int) -> None:
        slider = self.get_day_speed_slider_rect()
        ratio = (mouse_x - slider.x) / slider.width
        ratio = max(0.0, min(1.0, ratio))
        multiplier = 0.05 + ratio * 5.95
        self.settings["day_speed_multiplier"] = round(multiplier, 2)
        self.day_speed = self.base_day_speed * self.settings["day_speed_multiplier"]
        self.save_settings()

    def update_subsurface_depth_from_mouse(self, mouse_x: int) -> None:
        slider = self.get_subsurface_slider_rect()
        ratio = (mouse_x - slider.x) / slider.width
        ratio = max(0.0, min(1.0, ratio))
        depth = int(round(2 + ratio * 14))
        self.settings["subsurface_depth"] = depth
        self.save_settings()

    def update_audio_volume_from_mouse(self, mouse_x: int) -> None:
        slider = self.get_audio_slider_rect()
        ratio = (mouse_x - slider.x) / slider.width
        ratio = max(0.0, min(1.0, ratio))
        self.settings["audio_volume"] = round(ratio, 2)
        if self.audio:
            self.audio.volume = float(self.settings["audio_volume"])
        self.save_settings()

    def draw_settings_button(self) -> None:
        rect = self.settings_button_rect
        pygame.draw.rect(self.screen, (45, 55, 75), rect, border_radius=6)
        pygame.draw.rect(self.screen, (15, 20, 30), rect, 2, border_radius=6)
        label = self.ui_font.render("Settings", True, (230, 230, 230))
        self.screen.blit(label, label.get_rect(center=rect.center))

    def draw_player_button(self) -> None:
        rect = self.player_button_rect
        base_color = (110, 120, 80) if self.player_mode else (45, 55, 75)
        pygame.draw.rect(self.screen, base_color, rect, border_radius=6)
        pygame.draw.rect(self.screen, (15, 20, 30), rect, 2, border_radius=6)
        label = self.ui_font.render("Player", True, (230, 230, 230))
        self.screen.blit(label, label.get_rect(center=rect.center))

    def draw_settings_menu(self) -> None:
        if not self.settings_visible:
            return
        rect = self.settings_panel_rect
        panel = pygame.Surface(rect.size, pygame.SRCALPHA)
        panel.fill((25, 25, 40, 230))
        pygame.draw.rect(panel, (10, 10, 20), panel.get_rect(), 2)
        header = self.ui_font.render("Settings", True, (230, 230, 230))
        panel.blit(header, (10, 8))
        start_y = 34
        option_height = 28
        for idx, (label, _) in enumerate(self.settings_actions()):
            action_rect = pygame.Rect(10, start_y + idx * option_height, rect.width - 20, 24)
            pygame.draw.rect(panel, (60, 70, 90), action_rect, border_radius=4)
            pygame.draw.rect(panel, (20, 25, 35), action_rect, 1, border_radius=4)
            text = self.ui_font.render(label, True, (220, 220, 230))
            panel.blit(text, (action_rect.x + 8, action_rect.y + 4))
        start_y = self.settings_option_start()
        for idx, (key, label) in enumerate(self.settings_options()):
            option_rect = pygame.Rect(10, start_y + idx * option_height, rect.width - 20, 24)
            box_rect = pygame.Rect(option_rect.x, option_rect.y + 4, 16, 16)
            pygame.draw.rect(panel, (60, 70, 90), option_rect, border_radius=4)
            pygame.draw.rect(panel, (20, 25, 35), option_rect, 1, border_radius=4)
            pygame.draw.rect(panel, (30, 35, 45), box_rect, border_radius=3)
            if self.settings.get(key):
                pygame.draw.rect(panel, (110, 180, 120), box_rect.inflate(-4, -4))
            text = self.ui_font.render(label, True, (220, 220, 230))
            panel.blit(text, (option_rect.x + 24, option_rect.y + 4))
        day_slider = self.get_day_speed_slider_rect()
        day_slider_local = day_slider.move(-rect.x, -rect.y)
        pygame.draw.rect(panel, (60, 70, 90), day_slider_local, border_radius=4)
        pygame.draw.rect(panel, (20, 25, 35), day_slider_local, 1, border_radius=4)
        ratio = (self.settings.get("day_speed_multiplier", 1.0) - 0.05) / 5.95
        knob_x = day_slider_local.x + int(max(0.0, min(1.0, ratio)) * day_slider_local.width)
        pygame.draw.circle(panel, (180, 200, 220), (knob_x, day_slider_local.centery), 6)
        speed_label = self.ui_font.render("Day speed", True, (220, 220, 230))
        panel.blit(speed_label, (20, day_slider_local.y - 16))
        value_label = self.ui_font.render(
            f"{self.settings.get('day_speed_multiplier', 1.0):.2f}x",
            True,
            (220, 220, 230),
        )
        panel.blit(value_label, (rect.width - 70, day_slider_local.y - 16))
        subsurface_slider = self.get_subsurface_slider_rect()
        subsurface_local = subsurface_slider.move(-rect.x, -rect.y)
        pygame.draw.rect(panel, (60, 70, 90), subsurface_local, border_radius=4)
        pygame.draw.rect(panel, (20, 25, 35), subsurface_local, 1, border_radius=4)
        depth_ratio = (self.settings.get("subsurface_depth", 6) - 2) / 14
        depth_x = subsurface_local.x + int(max(0.0, min(1.0, depth_ratio)) * subsurface_local.width)
        pygame.draw.circle(panel, (180, 200, 220), (depth_x, subsurface_local.centery), 6)
        subsurface_label = self.ui_font.render("Underground view", True, (220, 220, 230))
        panel.blit(subsurface_label, (20, subsurface_local.y - 16))
        depth_value = self.ui_font.render(
            f"{self.settings.get('subsurface_depth', 6)} layers",
            True,
            (220, 220, 230),
        )
        panel.blit(depth_value, (rect.width - 120, subsurface_local.y - 16))
        audio_slider = self.get_audio_slider_rect()
        audio_local = audio_slider.move(-rect.x, -rect.y)
        pygame.draw.rect(panel, (60, 70, 90), audio_local, border_radius=4)
        pygame.draw.rect(panel, (20, 25, 35), audio_local, 1, border_radius=4)
        volume_ratio = float(self.settings.get("audio_volume", 0.6))
        audio_x = audio_local.x + int(max(0.0, min(1.0, volume_ratio)) * audio_local.width)
        pygame.draw.circle(panel, (180, 200, 220), (audio_x, audio_local.centery), 6)
        audio_label = self.ui_font.render("Audio volume", True, (220, 220, 230))
        panel.blit(audio_label, (20, audio_local.y - 16))
        volume_text = self.ui_font.render(
            f"{int(volume_ratio * 100)}%",
            True,
            (220, 220, 230),
        )
        panel.blit(volume_text, (rect.width - 80, audio_local.y - 16))
        self.screen.blit(panel, rect.topleft)

    def draw_palette_menu(self) -> None:
        if not self.palette_visible:
            return
        rect = self.palette_panel_rect
        panel = pygame.Surface(rect.size, pygame.SRCALPHA)
        panel.fill((25, 25, 40, 230))
        pygame.draw.rect(panel, (10, 10, 20), panel.get_rect(), 2)
        tab_height = 28
        tile_tab = pygame.Rect(10, 6, rect.width // 2 - 14, tab_height)
        texture_tab = pygame.Rect(rect.width // 2 + 4, 6, rect.width // 2 - 14, tab_height)
        pygame.draw.rect(panel, (60, 70, 90), tile_tab, border_radius=4)
        pygame.draw.rect(panel, (60, 70, 90), texture_tab, border_radius=4)
        active_tab = tile_tab if self.palette_tab == "tiles" else texture_tab
        pygame.draw.rect(panel, (90, 110, 150), active_tab, border_radius=4)
        tile_label = self.ui_font.render("Tiles", True, (230, 230, 230))
        texture_label = self.ui_font.render("Textures", True, (230, 230, 230))
        panel.blit(tile_label, tile_label.get_rect(center=tile_tab.center))
        panel.blit(texture_label, texture_label.get_rect(center=texture_tab.center))
        list_top = tab_height + 10
        item_height = 26
        if self.palette_tab == "tiles":
            items = self.tile_types
        else:
            items = [path.stem for path in self.replacement_images]
        start_index = max(0, self.palette_scroll // item_height)
        visible_count = (rect.height - list_top - 10) // item_height + 1
        end_index = min(len(items), start_index + visible_count)
        for idx in range(start_index, end_index):
            item_y = list_top + idx * item_height - self.palette_scroll
            item_rect = pygame.Rect(10, item_y, rect.width - 20, item_height - 4)
            pygame.draw.rect(panel, (50, 60, 80), item_rect, border_radius=4)
            if self.palette_tab == "tiles":
                color = DEFAULT_COLORS.get(items[idx], (120, 120, 120))
                pygame.draw.rect(panel, color, pygame.Rect(item_rect.x + 6, item_rect.y + 4, 16, 16))
                label = self.ui_font.render(items[idx].title(), True, (230, 230, 230))
                panel.blit(label, (item_rect.x + 28, item_rect.y + 4))
            else:
                thumb = self.get_texture_thumb(self.replacement_images[idx])
                panel.blit(thumb, (item_rect.x + 6, item_rect.y + 2))
                label = self.ui_font.render(items[idx], True, (230, 230, 230))
                panel.blit(label, (item_rect.x + 32, item_rect.y + 4))
        self.screen.blit(panel, rect.topleft)

    def draw_ui(self) -> None:
        start_x = 10
        start_y = max(self.settings_button_rect.bottom, self.player_button_rect.bottom) + 8
        button_height = 26
        spacing = 6
        self.menu_button_rects.clear()
        for index, section in enumerate(self.sections):
            rect = pygame.Rect(start_x, start_y + index * (button_height + spacing), 110, button_height)
            self.menu_button_rects[section.title] = rect
            pygame.draw.rect(self.screen, (45, 55, 75), rect, border_radius=6)
            pygame.draw.rect(self.screen, (15, 20, 30), rect, 2, border_radius=6)
            label = self.ui_font.render(section.title, True, (230, 230, 230))
            self.screen.blit(label, label.get_rect(center=rect.center))
        self.menu_panel_rect.y = 10
        self.menu_panel_rect.x = start_x + 120
        self.menu_panel_rect.height = self.screen.get_height() - 20
        self.draw_menu_panel()

    def draw_panel_scrollbar(self) -> None:
        total_height = self.total_button_height()
        visible = self.ui_rect.height - 20
        if total_height <= visible:
            return
        bar_height = max(24, int(visible * (visible / total_height)))
        scroll_ratio = self.panel_scroll / max(1, total_height - visible)
        bar_y = int(10 + scroll_ratio * (visible - bar_height))
        bar_rect = pygame.Rect(self.ui_rect.right - 6, self.ui_rect.y + bar_y, 4, bar_height)
        pygame.draw.rect(self.screen, (70, 90, 120), bar_rect)

    def draw_menu_panel(self) -> None:
        if not self.menu_visible:
            return
        section = next((sec for sec in self.sections if sec.title == self.active_menu), None)
        if section is None:
            return
        rect = self.menu_panel_rect
        panel = pygame.Surface(rect.size, pygame.SRCALPHA)
        panel.fill((25, 25, 40, 230))
        pygame.draw.rect(panel, (10, 10, 20), panel.get_rect(), 2)
        item_height = 28
        start_index = max(0, self.panel_scroll // item_height)
        visible_count = rect.height // item_height + 1
        end_index = min(len(section.buttons), start_index + visible_count)
        for idx in range(start_index, end_index):
            item_y = idx * item_height - self.panel_scroll
            item_rect = pygame.Rect(8, item_y + 4, rect.width - 16, item_height - 6)
            pygame.draw.rect(panel, (50, 60, 80), item_rect, border_radius=4)
            button = section.buttons[idx]
            label = self.ui_font.render(button.label, True, (230, 230, 230))
            panel.blit(label, (item_rect.x + 6, item_rect.y + 4))
        self.screen.blit(panel, rect.topleft)

    def render(self) -> None:
        zoom = self.zoom_levels[self.zoom_index]
        if self.zoom_index != self._last_zoom_index:
            self._last_zoom_index = self.zoom_index
            self._zoom_smooth_next = True
        if zoom != 1.0:
            size = self.screen.get_size()
            if self._zoom_world_surface is None or self._zoom_world_surface.get_size() != size:
                self._zoom_world_surface = pygame.Surface(size, pygame.SRCALPHA)
                self._zoom_smooth_next = True
            world_surface = self._zoom_world_surface
            world_surface.fill((0, 0, 0, 0))
            original_screen = self.screen
            self.screen = world_surface
            self.renderer.screen = world_surface
            self.draw_world()
            self.screen = original_screen
            self.renderer.screen = original_screen
            width, height = size
            scaled_w = int(width * zoom)
            scaled_h = int(height * zoom)
            if self.settings.get("high_quality", True) and self._zoom_smooth_next:
                scaler = pygame.transform.smoothscale
                self._zoom_smooth_next = False
            else:
                scaler = pygame.transform.scale
            scaled = scaler(world_surface, (scaled_w, scaled_h))
            origin_x = (width - scaled_w) // 2
            origin_y = (height - scaled_h) // 2
            self.screen.fill((0, 0, 0))
            self.screen.blit(scaled, (origin_x, origin_y))
        else:
            self.draw_world()
        # HUD intentionally hidden per UI requirements.
        self.draw_ui()
        self.draw_settings_button()
        self.draw_player_button()
        self.draw_settings_menu()
        self.draw_palette_menu()
        self.draw_inventory_menu()
        self.draw_help()
        self.draw_biome_label()
        self.draw_selected_tile_panel()
        self.draw_invasion_notice()
        self.draw_exit_prompt()

    def draw_world(self) -> None:
        self.draw_sky()
        self.render_grid()
        if self.settings.get("water_reflections", True):
            self.draw_water_reflections()
        self.draw_tree_overlays()
        self.draw_animals()
        self.draw_loot()
        self.draw_player()
        self.draw_mobs()
        self.draw_projectiles()
        self.draw_death_effects()
        self.draw_weather()
        self.apply_day_night_overlay()

    def run(self) -> None:
        running = True
        while running:
            running = self.handle_input()
            dt = self.clock.get_time() / 1000.0
            self.update_player(dt, pygame.key.get_pressed())
            self.update_animals(dt)
            self.update_invasions(dt)
            self.update_audio_ambient(dt)
            self.update_mobs(dt)
            self.update_projectiles(dt)
            self.update_loot()
            self.update_death_effects(dt)
            self.update_day_cycle(dt)
            self.update_water_physics(dt)
            self.update_weather(dt)
            self.exit_prompt_timer = max(0.0, self.exit_prompt_timer - dt)
            self.render()
            pygame.display.flip()
            self.clock.tick(FPS)


def parse_world_size() -> Tuple[int, int]:
    if len(sys.argv) >= 3:
        try:
            width = int(sys.argv[1])
            height = int(sys.argv[2])
            size = max(width, height)
            size = max(1, min(1000, size))
            return size, size
        except ValueError:
            pass
    return 100, 100


def main() -> None:
    world_size = parse_world_size()
    app = IsoApp(world_size)
    app.run()


if __name__ == "__main__":
    crash_reporter = CrashReporter(CRASH_DIR)
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        crash_reporter.report(exc)
        pygame.quit()
        raise
