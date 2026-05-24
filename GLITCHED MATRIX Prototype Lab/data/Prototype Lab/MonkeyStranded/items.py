"""
items.py — Item & Inventory module for Monkeys Island

This module holds:
- Item IDs + definitions
- Simple icon renderer (tiny pixel sprites)
- Inventory model
- World item model (for dropped/pickup objects)

Imported by monkeys_island.py
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional


# -------------------------
# Item IDs
# -------------------------
COCONUT = "coconut"
PINK_FLOWER = "pink_flower"
FISH = "fish"
ROCK = "rock"
BONE = "bone"
SAND = "sand"
GRASS = "grass"
WOOD = "wood"
FLOWER_SEEDS = "flower_seeds"
GRASS_SEEDS = "grass_seeds"
DIRT = "dirt"
SOIL = "soil"
WORM = "worm"
ANT = "ant"
FEATHER = "feather"
POULTRY = "poultry"

CRAB_MEAT = "crab_meat"
REPTILE_MEAT = "reptile_meat"

PALM_LEAF = "palm_leaf"
SEAWEED = "seaweed"
RAFT = "raft"
# -------------------------
# Definitions
# -------------------------
@dataclass(frozen=True)
class ItemDef:
    id: str
    name: str
    stack_limit: int
    colors: Tuple[Tuple[int, int, int], ...]  # icon palette (c0, c1, c2)


ITEMS: Dict[str, ItemDef] = {
    COCONUT: ItemDef(COCONUT, "Coconut", 20, ((120, 92, 56), (90, 70, 44), (235, 245, 250))),
    PINK_FLOWER: ItemDef(PINK_FLOWER, "Pink Flower", 30, ((238, 120, 175), (250, 230, 120), (58, 150, 78))),
    FISH: ItemDef(FISH, "Fish", 20, ((190, 210, 235), (120, 150, 190), (30, 40, 60))),
    ROCK: ItemDef(ROCK, "Rock", 30, ((140, 142, 150), (95, 98, 110), (235, 245, 250))),
    BONE: ItemDef(BONE, "Bone", 30, ((235, 235, 220), (200, 200, 185), (120, 122, 130))),
    SAND: ItemDef(SAND, "Sand", 50, ((232, 216, 152), (220, 200, 130), (235, 245, 250))),
    GRASS: ItemDef(GRASS, "Grass", 50, ((92, 182, 98), (75, 160, 82), (30, 90, 45))),
    WOOD: ItemDef(WOOD, "Wood", 50, ((166, 132, 80), (140, 110, 66), (90, 70, 44))),
    FLOWER_SEEDS: ItemDef(FLOWER_SEEDS, "Flower Seeds", 99, ((238, 120, 175), (250, 230, 120), (58, 150, 78))),
    GRASS_SEEDS: ItemDef(GRASS_SEEDS, "Grass Seeds", 99, ((92, 182, 98), (75, 160, 82), (58, 150, 78))),
    DIRT: ItemDef(DIRT, "Dirt", 50, ((140, 116, 80), (120, 98, 66), (235, 245, 250))),
    SOIL: ItemDef(SOIL, "Soil", 50, ((118, 108, 88), (95, 98, 110), (235, 245, 250))),
    WORM: ItemDef(WORM, "Worm", 50, ((210, 120, 120), (160, 80, 80), (235, 245, 250))),
    ANT: ItemDef(ANT, "Ant", 50, ((60, 40, 20), (15, 10, 5), (200, 180, 120))),

    FEATHER: ItemDef(FEATHER, "Feather", 99, ((235, 245, 250), (200, 210, 220), (120, 130, 145))),
    POULTRY: ItemDef(POULTRY, "Poultry", 20, ((235, 210, 190), (190, 150, 130), (30, 40, 60))),
    CRAB_MEAT: ItemDef(CRAB_MEAT, "Crab Meat", 20, ((210, 95, 80), (165, 65, 55), (235, 245, 250))),
    REPTILE_MEAT: ItemDef(REPTILE_MEAT, "Reptile Meat", 20, ((140, 90, 85), (110, 65, 60), (235, 245, 250))),
    PALM_LEAF: ItemDef(PALM_LEAF, "Palm Leaf", 50, ((58, 150, 78), (38, 120, 58), (235, 245, 250))),
    SEAWEED: ItemDef(SEAWEED, "Seaweed", 50, ((48, 135, 80), (30, 100, 60), (235, 245, 250))),
    RAFT: ItemDef(RAFT, "Raft", 5, ((170, 130, 85), (120, 90, 60), (235, 245, 250))),

}


# -------------------------
# Models
# -------------------------
@dataclass
class WorldItem:
    item_id: str
    x: float
    y: float
    qty: int = 1
    bob_phase: float = 0.0  # used for floating items; some items may ignore it


@dataclass
class InvSlot:
    item_id: str
    qty: int


class Inventory:
    def __init__(self, max_slots: int = 12):
        self.max_slots = max_slots
        self.slots: List[Optional[InvSlot]] = [None for _ in range(max_slots)]
        self.selected: int = 0

    def cycle_selected(self, delta: int):
        self.selected = (self.selected + delta) % self.max_slots

    def selected_stack(self) -> Optional[InvSlot]:
        return self.slots[self.selected]

    def add(self, item_id: str, qty: int) -> int:
        """Adds up to qty; returns number actually added."""
        if item_id not in ITEMS or qty <= 0:
            return 0
        limit = ITEMS[item_id].stack_limit

        remaining = qty

        # Fill existing stacks first
        for i in range(self.max_slots):
            s = self.slots[i]
            if s and s.item_id == item_id and s.qty < limit and remaining > 0:
                can = min(limit - s.qty, remaining)
                s.qty += can
                remaining -= can

        # Fill empty slots
        for i in range(self.max_slots):
            if remaining <= 0:
                break
            if self.slots[i] is None:
                can = min(limit, remaining)
                self.slots[i] = InvSlot(item_id=item_id, qty=can)
                remaining -= can

        return qty - remaining

    def remove_from_selected(self, qty: int) -> int:
        """Removes from selected stack; returns removed."""
        if qty <= 0:
            return 0
        s = self.slots[self.selected]
        if not s:
            return 0
        rm = min(qty, s.qty)
        s.qty -= rm
        if s.qty <= 0:
            self.slots[self.selected] = None
        return rm

    def count_item(self, item_id: str) -> int:
        """Total quantity of item_id across the entire inventory."""
        total = 0
        for s in self.slots:
            if s and s.item_id == item_id:
                total += int(s.qty)
        return total

    def has(self, item_id: str, qty: int) -> bool:
        """True if inventory has at least qty of item_id."""
        if qty <= 0:
            return True
        return self.count_item(item_id) >= qty

    def remove(self, item_id: str, qty: int) -> int:
        """Remove up to qty of item_id across all slots; returns removed."""
        if qty <= 0:
            return 0
        remaining = qty
        for i in range(self.max_slots):
            if remaining <= 0:
                break
            s = self.slots[i]
            if not s or s.item_id != item_id:
                continue
            rm = min(int(s.qty), remaining)
            s.qty -= rm
            remaining -= rm
            if s.qty <= 0:
                self.slots[i] = None
        return qty - remaining


# -------------------------
# Icon drawing
# -------------------------
def draw_icon(pygame, surface, x: int, y: int, item_id: str, scale: int = 1):
    """
    Draws a small 10x10 pixel icon at (x, y).
    The caller passes pygame so this module stays import-light.
    """
    if item_id not in ITEMS:
        return
    c0, c1, c2 = ITEMS[item_id].colors

    def px(ix, iy, col):
        surface.fill(col, (x + ix * scale, y + iy * scale, scale, scale))

    # Clear area (transparent not used; caller draws bg). Light outline only where needed.

    if item_id == COCONUT:
        # round brown nut with highlight
        for iy in range(3, 8):
            for ix in range(3, 8):
                if (ix-5)**2 + (iy-5)**2 <= 6:
                    px(ix, iy, c0)
        px(4,4,c1); px(5,4,c2); px(6,5,c1); px(4,6,c1)
    elif item_id == WOOD:
        # plank
        pygame.draw.rect(surface, c0, (x + 2*scale, y + 3*scale, 6*scale, 4*scale))
        pygame.draw.rect(surface, c1, (x + 2*scale, y + 3*scale, 6*scale, 1*scale))
        px(3,5,c2); px(6,6,c2)
    elif item_id == PINK_FLOWER:
        # stem + petals + center
        px(5,8,(58,150,78))
        px(5,7,(58,150,78))
        px(4,6,c0); px(6,6,c0); px(5,5,c0); px(5,7,c0)
        px(5,6,c1)
    elif item_id == FISH:
        # simple fish
        for (ix, iy) in [(4,5),(5,5),(6,5),(3,6),(4,6),(5,6),(6,6),(7,6),(4,7),(5,7),(6,7)]:
            px(ix, iy, c0)
        px(3,6,c1); px(7,6,c1)
        px(6,5,c2); px(5,6,c2)
        px(2,6,c1); px(2,5,c1)  # tail hint
    elif item_id == ROCK:
        for (ix, iy) in [(4,4),(5,4),(6,4),(3,5),(4,5),(5,5),(6,5),(7,5),(3,6),(4,6),(5,6),(6,6),(7,6),(4,7),(5,7),(6,7)]:
            px(ix, iy, c0)
        px(4,5,c1); px(6,6,c1); px(5,6,c2)
    elif item_id == BONE:
        # bone
        for (ix, iy) in [(4,5),(5,5),(6,5),(4,6),(5,6),(6,6)]:
            px(ix, iy, c0)
        px(3,5,c1); px(7,5,c1); px(3,6,c1); px(7,6,c1)
        px(2,5,c2); px(8,5,c2)
    elif item_id in (SAND, DIRT, SOIL):
        # small pile
        for (ix, iy) in [(4,6),(5,6),(6,6),(3,7),(4,7),(5,7),(6,7),(7,7),(4,8),(5,8),(6,8)]:
            px(ix, iy, c0)
        px(4,7,c1); px(6,7,c1); px(5,6,c2)
    elif item_id == GRASS:
        for (ix, iy) in [(4,8),(5,8),(6,8),(4,7),(6,7),(5,6),(4,6),(6,6)]:
            px(ix, iy, c0)
        px(5,7,c1); px(5,6,c2)
    elif item_id == FEATHER:
        # feather
        for (ix, iy) in [(5,3),(5,4),(5,5),(5,6),(5,7),(4,4),(6,5),(4,6),(6,7)]:
            px(ix, iy, c0)
        px(6,4,c1); px(4,5,c1); px(6,6,c1)
        px(5,8,c2)
    elif item_id == POULTRY:
        # drumstick-like
        for (ix, iy) in [(4,5),(5,5),(6,5),(4,6),(5,6),(6,6),(5,7),(6,7)]:
            px(ix, iy, c0)
        px(6,5,c1); px(6,6,c1); px(5,5,c2)
        px(3,6,(235,235,220)); px(3,7,(235,235,220)); px(2,6,(200,200,185))
    elif item_id == FLOWER_SEEDS:
        # little seed dots
        for (ix, iy) in [(4,6),(6,6),(5,5),(5,7)]:
            px(ix, iy, c0)
        px(5,6, c2)
        px(5,8, (58,150,78))
    elif item_id == GRASS_SEEDS:
        for (ix, iy) in [(4,6),(6,6),(5,5),(5,7)]:
            px(ix, iy, c0)
        px(5,6, c1)
        px(5,8, (58,150,78))
    elif item_id == CRAB_MEAT:
        # small red meat chunk
        for (ix, iy) in [(4,6),(5,6),(6,6),(3,7),(4,7),(5,7),(6,7),(7,7),(4,8),(5,8),(6,8)]:
            px(ix, iy, c0)
        px(4,7,c1); px(6,7,c1); px(5,6,c2)
    elif item_id == REPTILE_MEAT:
        # darker meat strip
        for (ix, iy) in [(4,5),(5,5),(6,5),(3,6),(4,6),(5,6),(6,6),(7,6),(4,7),(5,7),(6,7)]:
            px(ix, iy, c0)
        px(4,6,c1); px(6,6,c1); px(5,5,c2)
    elif item_id == PALM_LEAF:
        # fan-like frond (more strands)
        # stem
        for iy in range(2, 10):
            px(5, iy, c1)
        # fan ribs
        for dx in range(-4, 5):
            px(5 + dx, 2, c0)
        for step in range(1, 6):
            px(5 - step, 2 + step//2, c0)
            px(5 + step, 2 + step//2, c0)
        # strands
        for dx in range(-4, 5, 2):
            for step in range(1, 6):
                px(5 + dx + (step//3), 2 + step, c0)
        px(5, 1, c2)
    elif item_id == SEAWEED:
        # wavy strands
        for (ix, iy) in [(4,8),(4,7),(5,6),(4,5),(5,4),(4,3),(5,2)]:
            px(ix, iy, c0)
        for (ix, iy) in [(6,8),(6,7),(5,6),(6,5),(5,4),(6,3),(5,2)]:
            px(ix, iy, c1)
        px(5,9, c2)
    else:
        # fallback square
        pygame.draw.rect(surface, c0, (x + 2*scale, y + 2*scale, 6*scale, 6*scale))
        pygame.draw.rect(surface, c2, (x + 3*scale, y + 3*scale, 4*scale, 4*scale))
