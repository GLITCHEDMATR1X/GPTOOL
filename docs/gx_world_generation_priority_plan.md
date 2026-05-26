# GX World Generation Priority Plan

## Core Direction
Build the world-generation system **one thing at a time**.

Do not try to solve every game type at once.
Do not blend all donors at once.
Do not let the machine invent structure blindly.

Start with one world type, one archetype, one donor lane, and improve the logic from there.

---

## Main Rule
The machine should generate the **world scaffold first**.

Then, only after the world logic is coherent, layer in:
- player systems
- camera systems
- combat
- simulation
- save/load
- UI
- audio

This keeps the core stable.

---

## Practical Starting Strategy
You will tag world candidates for the type you want to start on.

GX Machine should then use those candidate tags to:
1. rank world donors
2. extract world-relevant systems only
3. build a fresh world scaffold
4. validate that scaffold
5. improve the generator logic from results

This is the correct order.

---

## Priority Build Structure

### Phase 1 — Pick One World Family
Start with only one of these at a time:
- city
- wilderness
- dungeon/facility
- colony
- planet surface
- block zone
- arena
- ocean/island
- space/orbit
- abstract procedural

Only one should be active as the main development target.

### Phase 2 — Lock One Archetype
For that world family, lock one game type:
- side
- top-down
- isometric
- first-person
- third-person

This avoids design drift.

### Phase 3 — Tag World Candidates
Mark donor files/projects that are valuable specifically for:
- terrain/world generation
- level layout
- chunk logic
- structure placement
- landmark generation
- traversal spaces
- world materials and visual identity

Do not worry yet about combat, menus, or other unrelated systems unless they are tightly tied to the world.

### Phase 4 — Extract World Lanes Only
For the first pass, focus only on these lanes:
- world layout lane
- terrain lane
- structure/POI lane
- pathing/traversal lane
- world palette/atmosphere lane

Everything else should stay secondary for now.

### Phase 5 — Build the First Scaffold
Generate a fresh world scaffold that can:
- spawn the world shape
- place structures/landmarks
- expose the playable area
- support traversal
- remain stable even before the full game exists

This scaffold should be the first proof target.

### Phase 6 — Improve Logic From Results
After the first scaffold works, improve:
- donor ranking
- structure placement rules
- world variation
- tag interpretation
- import/dependency handling
- lane merge rules

This should be iterative.

---

## Important Rule About Assets
Assets should be treated as persistent reusable output.

That means:
- generated or extracted assets can be saved and reused later
- world logic can improve independently of the asset library
- the machine should not depend on the final asset pack being complete before world logic is tested

So even if the game is not fully assembled yet, saved assets and saved world parts still matter.

---

## Best First-Version Goal
The first goal is **not** a finished game.

The first goal is:
- one clear world type
- one matching archetype
- one stable world scaffold
- one readable donor-selection path
- one repeatable generation result

That is enough to prove the system.

---

## Recommended First-Candidate Tag Types
When tagging world candidates, prioritize tags like:
- world_gen
- terrain
- chunking
- layout
- structures
- interiors
- city
- wilderness
- dungeon
- colony
- zone
- atmosphere
- materials
- traversal
- pathing
- landmark
- biome
- proc_gen

Second-priority tags:
- combat
- inventory
- UI
- audio
- save/load

Those can matter later, but should not dominate world selection at the beginning.

---

## Best Review Lens for World Candidates
When reviewing a donor, ask:

### 1. Does it help create world shape?
Examples:
- terrain mesh
- chunk map
- room layout
- block layout
- path network

### 2. Does it help create world identity?
Examples:
- biome feel
- city feel
- ruin/facility feel
- atmosphere
- material style

### 3. Does it help traversal?
Examples:
- roads
- corridors
- open traversal zones
- verticality
- flight spaces
- walkable routes

### 4. Is it stable enough to reuse?
Examples:
- not too laggy
- not too brittle
- not too dependent on unrelated systems

This is the right filter.

---

## Recommended Separate Candidate Groups
When you begin tagging, sort candidates into these world-focused groups:

### Group A — Core world donors
Best for direct world scaffold extraction.

### Group B — Support donors
Useful for atmosphere, landmarks, materials, traversal, or side systems.

### Group C — Experimental donors
Interesting ideas, but not safe enough to dominate the scaffold.

### Group D — Blocked for now
Too unfinished, too messy, too off-target, or too risky for the current pass.

This keeps the process organized.

---

## Strong Recommendation for the First Pass
For the first world-generation priority pass:
- use mostly candidate donors
- keep the lane focus narrow
- do not merge too many systems
- prefer stable structure over feature count
- validate world generation before adding game complexity

---

## Suggested Priority UI/Logic for This Track
The world-generation track should eventually have its own focused controls:
- World Family
- Archetype
- World Candidates
- Donor Rank
- World Scaffold Build
- Validate World

That is enough for the early phase.

---

## What Success Looks Like
Success for this separate track means:
- you tag a set of world candidates
- GX Machine ranks them clearly
- it extracts world-relevant systems only
- it creates a fresh scaffold for the chosen world type
- the scaffold runs and shows a real playable/generated space
- then the logic improves from test results

---

## Immediate Next Step
You tag the world candidates for the starting type.

Then the next implementation step should be:
**build the first world-donor ranking checklist and world-lane extraction checklist for that chosen type.**

## Final Rule
Start narrow.
Prove one world type properly.
Then expand.
That is how the world-generation system becomes reliable.

---

# Reorganized World-Candidate Tagging Model

## Verification Note
I verified the uploaded GX Prototype zip still contains:
- `data/Prototype Lab/info.txt`
- `data/brain/generation_bridge.py`
- `data/GX-Machine/...`

That matters because the inventory and bridge are still connected in the current project structure.

## Important Structural Finding
The current bridge already force-maps these Prototype Lab category folders into profiles:
- `2D - Side` -> `side_scroller`
- `2D - Isometric` -> `isometric`
- `2D - Top` -> `top_down`
- `3D - First Person` -> `first_person_3d`
- `3D - Third Person` -> `third_person_3d`

But `2D - Hybrid` does not have its own clear category profile in that mapping.

That means the updated tags should not rely on folder names alone for hybrid entries.

## Better Organization Rule
Separate these into different layers:

### Layer 1 — Folder Category
This is only where the donor currently lives.
Examples:
- `2D - Hybrid`
- `2D - Isometric`
- `2D - Side`
- `2D - Top`
- `3D - First Person`
- `3D - Third Person`

### Layer 2 — Primary World/Archetype Tags
These should describe what the donor is actually useful for.
Examples:
- `side_world`
- `top_world`
- `isometric_world`
- `first_person_world`
- `third_person_world`
- `space_world`
- `city_world`
- `aquatic_world`
- `interiors`
- `wilderness_world`
- `block_world`

### Layer 3 — Support/System Tags
These should describe useful supporting traits.
Examples:
- `proc_gen`
- `simulation`
- `vehicles`
- `flight`
- `ui`
- `logic`
- `characters`
- `arena`
- `sprites`
- `combat`
- `audio`
- `text`

### Layer 4 — Risk / Penalty Tags
These should remain separate so they do not get confused with useful traits.
Examples:
- `needs_work`
- `slow`
- `laggy`
- `untested`
- `not_finished`
- `optimize_performance`
- `older_version`

This is the cleanest structure.

---

## Best Reorganization of the Updated Tags

### Use normalized tag shapes
Instead of mixed phrases like:
- `top world`
- `side world`
- `2D aquatic world`
- `(optimize performance)`

use normalized forms like:
- `top_world`
- `side_world`
- `aquatic_world`
- `performance_risk`

This makes machine ranking easier and reduces ambiguity.

## Strong Recommended Tag Buckets
Each donor should ideally have these compact fields:

### `world_tags`
What kind of world it helps generate.

### `system_tags`
What systems it contributes.

### `risk_tags`
What may go wrong.

### `candidate_level`
How strongly it should be considered.
Values:
- `core`
- `support`
- `experimental`
- `blocked`

That is enough for the first world-generation pass.

---

## Suggested Reorganization of Current Examples

### Apocalypse Run
Current idea:
- side world
- top world
- vehicles
- proc gen

Recommended:
- `world_tags: [side_world, top_world, road_world]`
- `system_tags: [vehicles, combat, fuel_system, proc_gen, adventure]`
- `risk_tags: []`
- `candidate_level: support`

### Doomsday Battle
Current idea:
- isometric world
- ui
- top world
- side world
- vehicles
- text

Recommended:
- `world_tags: [isometric_world, top_world, side_world]`
- `system_tags: [ui, vehicles, map_sim, text, combat]`
- `risk_tags: []`
- `candidate_level: support`

### Radar Hell
Current idea:
- 2.5d interiors

Recommended:
- `world_tags: [interiors, hybrid_world]`
- `system_tags: [combat, effects, weapons]`
- `risk_tags: []`
- `candidate_level: support`

### Isometric World Machine
Current idea:
- candidate for isometric worlds

Recommended:
- `world_tags: [isometric_world, world_gen]`
- `system_tags: [editor, proc_gen, traversal]`
- `risk_tags: [needs_fixes]`
- `candidate_level: core`

### Duck n Cover
Current idea:
- 2d side world
- optimize performance

Recommended:
- `world_tags: [side_world]`
- `system_tags: [flight, proc_gen, effects]`
- `risk_tags: [performance_risk]`
- `candidate_level: support`

### Octo Evolve
Current idea:
- 2D aquatic world

Recommended:
- `world_tags: [aquatic_world, side_world]`
- `system_tags: [simulation, proc_gen, animation, creature_physics]`
- `risk_tags: []`
- `candidate_level: support`

### Split Time
Current idea:
- 2d side world
- optimize performance

Recommended:
- `world_tags: [side_world, timeline_world]`
- `system_tags: [sandbox, logic, sprites, adventure]`
- `risk_tags: [laggy, performance_risk]`
- `candidate_level: support`

### Distant Colonies / Mewtants / MonkeyStranded
Recommended shared structure:
- `world_tags: [top_world]`
- then specific secondary tags like `colony_world`, `dungeon_world`, `survival_world`

### Afterlife Hotel
Recommended:
- `world_tags: [first_person_world, interiors, cubic_world]`
- `system_tags: [sandbox, logic, characters, image_to_3d]`
- `risk_tags: []`
- `candidate_level: core`

### Lost Forests
Recommended:
- `world_tags: [first_person_world, wilderness_world, block_world]`
- `system_tags: [world_gen, traversal]`
- `risk_tags: []`
- `candidate_level: core`

### Ghost City / Storm Block
Recommended:
- `world_tags: [third_person_world, city_world]`
- `system_tags: [traversal, landmarks]`
- `risk_tags: []`
- `candidate_level: support`

### The Anti-Heroes
Recommended:
- `world_tags: [third_person_world, city_world, flight_world]`
- `system_tags: [flight, proc_gen, combat, characters]`
- `risk_tags: []`
- `candidate_level: core`

### Zonez
Recommended:
- `world_tags: [third_person_world, block_world, biome_world]`
- `system_tags: [world_gen, tasks, traversal, npc_support]`
- `risk_tags: []`
- `candidate_level: core`

---

## Best New Candidate Groups
To make the inventory easier to use for world-first generation, reorganize candidates conceptually into these groups:

### Core World Donors
Best direct world scaffold sources.
Examples likely include:
- `Isometric World Machine`
- `Distant Colonies`
- `Afterlife Hotel`
- `Lost Forests`
- `The Anti-Heroes`
- `Zonez`

### World Support Donors
Useful for special world traits, but not the main scaffold.
Examples likely include:
- `Apocalypse Run`
- `Doomsday Battle`
- `Radar Hell`
- `Ghost City`
- `Storm Block`
- `Octo Evolve`

### Experimental World Donors
Interesting but should not dominate the first scaffold pass.
Examples likely include:
- `Entropy`
- `Glitch TV`
- `Liquid Mercury 4D`
- `Fractured`

### Penalty / Review Donors
Usable only with caution because the tags themselves imply performance or finish risk.
Examples include files explicitly marked with:
- `needs work`
- `slow`
- `laggy`
- `not finished`
- `optimize performance`

---

## Best Rule for Hybrid Folder Entries
For `2D - Hybrid`, do not treat the folder as a final archetype.

Instead, require at least one explicit `world_tag` such as:
- `side_world`
- `top_world`
- `isometric_world`
- `interiors`
- `space_world`
- `hybrid_world`

This prevents hybrid projects from being too vague for ranking.

---

## Recommended Minimal Tag Template Going Forward
For each donor, the smallest good format is:

```yaml
folder_category: 2D - Hybrid
candidate_level: support
world_tags: [side_world, top_world, road_world]
system_tags: [vehicles, combat, proc_gen]
risk_tags: []
notes: useful for road traversal and mode switching
```

That is compact, readable, and much better for machine scoring.

---

## Best Immediate Next Step After This Reorganization
Once you finish retagging with this structure, the next implementation step should be:
- update the bridge ranking logic so it prefers `world_tags` first
- use `system_tags` as support scoring
- use `risk_tags` as penalties
- treat `candidate_level` as a ranking boost

That is the cleanest path to better world-first donor selection.

---

# 2D World Start Set — Top and Side Candidates

## Focus Rule
Start the first 2D world-generation pass with only:
- **top-down world donors**
- **side-world donors**
- one hybrid support donor when it clearly helps bridge the two

Do not let this pass drift into combat, menus, or unrelated feature extraction.

---

## Recommended First Top-Down World Donors

### Core
- **Distant Colonies** — strongest top-world colony simulator base
- **MonkeyStranded** — strong top-world terrain and surface-from-code donor

### Support
- **Mewtants** — biome dressing, chunk flavor, floor/wall texture generation

### Optional thematic extension
- **Alien Colonies** can be treated as a thematic derivative layer built on top of the `Distant Colonies` world logic rather than needing a separate donor first.

That means:
- use `Distant Colonies` for colony world systems
- then apply alien biome/material/population flavoring later

---

## Recommended First Side-World Donors

### Core
- **Split Time / earth.py** — strongest side-world biome chunk layering donor

### Support
- **Duck n Cover** — side-world pacing and endless strip logic support
- **Apocalypse Run** — side/top hybrid support for strip-based world generation and palette variation
- **Octo Evolve** — optional aquatic-world support, not first priority
- **Pixelquest** — later support for wilderness/simulation flavor

---

## Best Candidate Grouping for This Start

### Top-Down Core World Donors
- `Distant Colonies`
- `MonkeyStranded`

### Top-Down Support Donors
- `Mewtants`

### Side Core World Donors
- `Split Time / earth.py`

### Side Support Donors
- `Duck n Cover`
- `Apocalypse Run`

### Later / Secondary
- `Octo Evolve`
- `Pixelquest`
- `Sky and Ground`

This is the narrowest useful starting set.

---

## Exact Terrain / World Texture Code Seeds to Preserve

These should be treated as exact donor seeds for the world-generation lane.

### Distant Colonies — tile generation and biome selection
```python
    def _generate_tile(self, tx: int, ty: int) -> Tile:
        noise = self._height_noise(tx, ty)
        heat = self._heat_noise(tx, ty)
        moisture = self._moisture_noise(tx, ty)
        rng = random.Random((tx * 73856093) ^ (ty * 19349663) ^ self._seed)
        biome = self._pick_biome(noise, heat, moisture)
        tile = Tile(
            height=noise,
            clutter=rng.random(),
            rock=noise > 0.75 and rng.random() > 0.4,
            biome=biome,
        )
        tile.foliage = max(0.0, (moisture - 0.5) * 1.4) if biome in ("bog", "oasis") else max(0.0, moisture - 0.7)
        tile.river = moisture > 0.78 and noise < 0.45
```

```python
    def _height_noise(self, x: int, y: int) -> float:
        s = math.sin(x * 0.08) + math.cos(y * 0.06)
        l = math.sin((x + y) * 0.03)
        r = self._coord_random(x, y, 0.3)
        return max(0.0, min(1.0, (s + l) * 0.3 + 0.5 + r))

    def _heat_noise(self, x: int, y: int) -> float:
        s = math.sin(x * 0.05) + math.cos(y * 0.04)
        r = self._coord_random(x + 99, y - 37, 0.4)
        return max(0.0, min(1.0, 0.5 + s * 0.2 + r))

    def _moisture_noise(self, x: int, y: int) -> float:
        s = math.sin(x * 0.04 + y * 0.02)
        r = self._coord_random(x - 43, y + 58, 0.35)
        return max(0.0, min(1.0, 0.5 + s * 0.25 + r))
```

```python
    def _pick_biome(self, height: float, heat: float, moisture: float) -> str:
        if height > 0.8:
            return "ridge"
        if heat > 0.7 and moisture < 0.35:
            return "dune"
        if moisture > 0.65 and heat < 0.5:
            return "bog"
        if moisture > 0.6 and heat > 0.6:
            return "oasis"
        if heat < 0.35:
            return "glacier"
        return "waste"
```

These are strong top-world seed rules because they separate:
- height
- heat
- moisture
- biome selection
- tile identity

---

### MonkeyStranded — simple sand/dirt hill world fill
```python
def build_world_with_hills() -> List[List[Tuple[int,int,int]]]:
    w = [[AIR for _ in range(HEIGHT)] for _ in range(WIDTH)]
    for x in range(WIDTH):
        top_y = surface_y_at(x)
        if top_y < 1:
            top_y = 1
        if top_y > SURFACE_Y:
            top_y = SURFACE_Y
        for y in range(top_y, HEIGHT):
            # SAND near the surface, DIRT deeper down
            if y >= top_y + DIRT_DEPTH:
                w[x][y] = DIRT
            else:
                w[x][y] = SAND
    return w
```

This is useful because it is very readable and easy to adapt into a simpler top-world terrain scaffold.

---

### Mewtants — biome dressing and generated tile textures
```python
        self.floor_tile = pygame.Surface((TILE, TILE))
        self.wall_tile = pygame.Surface((TILE, TILE))
        # Brighter dungeon tiles for visibility
        self.floor_tile.fill((26, 26, 32))
        # Bright walls so the maze reads clearly
        self.wall_tile.fill((78, 66, 108))
        for i in range(50):
            x = (i * 13) % TILE
            y = (i * 29) % TILE
            self.floor_tile.set_at((x, y), (34, 34, 44))
        for i in range(70):
            x = (i * 11) % TILE
            y = (i * 23) % TILE
            self.wall_tile.set_at((x, y), (98, 84, 132))
        # Add a few darker pits to give depth (still bright overall)
        for i in range(35):
            x = (i * 7) % TILE
            y = (i * 19) % TILE
            self.wall_tile.set_at((x, y), (56, 48, 82))
```

This is useful as a texture-generation donor, not as the main top-world scaffold.

---

### Split Time / earth.py — side-world biome and terrain layering
```python
BIOMES = [
    Biome("Emerald Plains", GRASS, DIRT, STONE, WOOD,
          fog_rgb=(28, 40, 32),
          sky_top_rgb=(92, 172, 255), sky_bottom_rgb=(182, 224, 255),
          cloud_rgb=(255, 255, 255),
          bg_far_rgb=(44, 74, 64), bg_near_rgb=(34, 64, 54),
          tree_chance=0.07, has_water=True),

    Biome("Sunblight Dunes", SAND, SAND, STONE, CRYSTAL,
          fog_rgb=(48, 38, 22),
          sky_top_rgb=(255, 184, 112), sky_bottom_rgb=(255, 232, 176),
          cloud_rgb=(255, 248, 235),
          bg_far_rgb=(114, 84, 52), bg_near_rgb=(92, 62, 40),
          tree_chance=0.02, has_water=False),
```

```python
        for lx in range(CHUNK_W):
            sy = surface_y[lx]
            for ty in range(WORLD_H):
                if ty >= FORTRESS_Y0:
                    tile = FORTRESS_BRICK
                elif ty < sy:
                    tile = AIR
                else:
                    depth = ty - sy
                    if depth == 0:
                        tile = biome.surface_tile
                    elif depth < 7:
                        tile = biome.sub_tile
                    elif depth < 42:
                        tile = biome.deep_tile
                    else:
                        deep_noise = value_noise_2d((cx*CHUNK_W+lx) * 0.7, ty * 0.9, self.seed ^ 0xDEED, 18)
                        tile = OBSIDIAN if deep_noise > 0.72 else biome.deep_tile
                ch.tiles[lx][ty] = tile
```

```python
        if max_cave_y > 8:
            for lx in range(CHUNK_W):
                wx = cx * CHUNK_W + lx
                sy = surface_y[lx]
                y_start = sy + 10
                if y_start >= max_cave_y:
                    continue
                span = max(1, (max_cave_y - (sy + 12)))
                for ty in range(y_start, max_cave_y):
                    t = (ty - (sy + 10)) / span
                    nA = value_noise_2d(wx, ty, self.seed ^ 0xCA7E, 16)
                    nB = value_noise_2d(wx + 311, ty + 97, self.seed ^ 0xCA72, 7)
                    v = (nA * 0.75 + nB * 0.25)
                    threshold = mix(0.78, 0.88, t)
                    if v > threshold:
                        ch.tiles[lx][ty] = AIR
```

This is the strongest current side-world terrain donor because it already separates:
- biome palette
- surface/sub/deep layers
- chunk generation
- cave carving
- depth-based material switching

---

### Apocalypse Run — side/top hybrid strip textures and surface palette variation
```python
        self.ground_band = pygame.Surface((STRIP_W, 120))
        base = GROUND_TINT[biome]
        self.ground_band.fill(base)
        dither_fill(
            self.ground_band,
            (clamp(base[0] + 8, 0, 255), clamp(base[1] + 8, 0, 255), clamp(base[2] + 8, 0, 255)),
            (clamp(base[0] - 8, 0, 255), clamp(base[1] - 8, 0, 255), clamp(base[2] - 8, 0, 255)),
            step=2
        )
```

```python
    city_pal = {
        "sky_top": jitter_color(SKY_TOP, rng, amount=20),
        "sky_bot": jitter_color(SKY_BOT, rng, amount=22),
        "sun": jitter_color(SUN, rng, amount=26),
        "haze": jitter_color(HAZE, rng, amount=18),
        "road": jitter_color(ROAD, rng, amount=10),
        "road_dark": jitter_color(ROAD_DARK, rng, amount=10),
        "road_edge": jitter_color(ROAD_EDGE, rng, amount=12),
        "lane": jitter_color(LANE, rng, amount=14),
    }
```

This should be treated as side/hybrid support for strip-based world generation and palette drift, not the main side-world terrain donor.

---

## Best Build Recommendation From These Donors

### Top-Down 2D world track
Use:
- `Distant Colonies` as the main world-rule donor
- `MonkeyStranded` as the simple terrain-fill donor
- `Mewtants` as the biome dressing and tile texture donor

### Side 2D world track
Use:
- `Split Time / earth.py` as the main terrain-layer and biome donor
- `Apocalypse Run` for strip/palette support
- `Duck n Cover` later for pacing and endless-world support

### Alien colony variant
Build it as:
- `Distant Colonies` core logic
- alien-biome palette and population layer added on top
- optional texture/dressing support from `Mewtants`

---

## Immediate Next Step for This 2D Start
Create two separate ranking checklists:

### Checklist A — Top-Down World Scaffold
- colony world logic
- biome selection
- tile generation
- terrain fill
- tile texture generation
- world population hooks

### Checklist B — Side World Scaffold
- biome definitions
- surface/sub/deep layers
- cave carving
- chunk generation
- palette/background rules
- traversal readability

That should be the first real implementation split for the 2D world-generation pass.

