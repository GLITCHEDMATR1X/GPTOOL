# GX Machine Process Plan

## Problem
The system is not proving its range yet. Instead of generating clearly different game structures, it keeps collapsing into the same 2D side-scroller pattern.

## Core Diagnosis
The likely issue is not the generator by itself. The larger issue is source routing and donor selection:

- donor sources are not being classified into the right pools
- some important folders are effectively excluded from generation
- the cache of source profiles is empty or underpopulated
- the generator is falling back to generic profile behavior

That means requests for new types of games are not being grounded in real donor examples.

## Goal
Prove that GX Machine can generate clearly different game archetypes, not just variations of one side-scroller template.

---

## Stage 1 — Restore Source Visibility
Fix the source-routing layer before touching the generator logic heavily.

### Tasks
- confirm how `Prototype Lab` is classified
- confirm how `GX-Machine` is classified
- allow intended donor pools to participate in generation
- rebuild source profile cache
- verify donor records are nonzero

### Must Remain Unchanged
- directory structure where possible
- existing workstation and bridge tooling
- stable runtime behavior outside the source-pool fix

### Success Condition
The system can see real donor projects again and reports them correctly.

---

## Stage 2 — Add Generation Proof
Make the machine explain what it is doing each time it generates.

### Add a visible proof panel showing
- requested game type
- selected pool
- chosen donor sources
- rejected donors and why
- fallback reason if fallback was used

### Success Condition
Every generation attempt is explainable instead of opaque.

---

## Stage 3 — Split Donors into Lanes
Do not treat all donor games as one blended pool.

### Example lane logic
- **structure / interior lane**: projects strong at spaces and level form
- **movement lane**: projects strong at locomotion and traversal
- **surface / deformation lane**: projects strong at terrain, materials, and visual distortion
- **combat / encounter lane**: projects strong at action loops
- **simulation / systems lane**: projects strong at management, AI, or emergent behavior

### Success Condition
Generation can pull from different strengths instead of averaging everything into the same result.

---

## Stage 4 — Enforce Archetype Contracts
Each requested archetype needs minimum required rules.

### 3D First-Person must include
- real 3D camera
- grounded movement
- readable 3D spaces
- no side-view fallback

### 3D Third-Person must include
- chase or orbit camera
- visible player body
- readable depth and traversal
- no side-view fallback

### Isometric must include
- angled fixed camera
- diagonal spatial readability
- no side-view fallback

### Top-Down must include
- overhead framing
- top-down interaction logic
- no side-view fallback

### Side-Scroller
- only use when explicitly requested

### Success Condition
Requesting a 3D or top-down result can no longer collapse into a side-scroller.

---

## Stage 5 — Build Proof-of-Potential Slices
Use the repaired machine to generate a few clearly different benchmark slices.

### Target slices
1. 3D interior slice
2. 3D third-person traversal/combat slice
3. isometric slice
4. top-down systems slice

These do not need to be finished games. They need to prove range.

### Success Condition
The machine can output multiple distinct spatial grammars.

---

## Stage 6 — Validate Every Pass
Use the bridge pipeline after edits.

### Required validation
- Panda3D bootstrap
- environment probe
- syntax validation
- import validation
- runtime smoke test
- asset validation
- UI bounds validation
- text fit validation
- regression check
- crash parsing
- screenshot review
- pre-submit gate

### Success Condition
Only validated results count as progress.

---

## Recommended First Patch
Do this first:

### Patch 1
- repair source-pool resolution
- rebuild source profile cache
- add generation proof panel

Do **not** start with a large generator rewrite.

## Why
If the machine cannot see and explain its donor sources, every later generation pass will remain unreliable.

---

## Simple Outcome Target
After Patch 1, GX Machine should be able to show:

- real donor projects detected
- donor counts by archetype
- which donors are being used for a request
- when and why fallback happens

Once that works, the next pass should force a **3D third-person proof slice** and validate it.

---

## Immediate Development Order
1. fix source visibility
2. add proof/explanation panel
3. rebuild donor cache
4. enforce archetype rules
5. generate 4 benchmark slices
6. validate every pass through the bridge

## Final Principle
Do not keep asking the generator for better results while its donor-routing and archetype enforcement are still broken. Fix the machine’s decision path first, then test its range.

---

# GX Machine Menu Makeover Direction

## Core Idea
The GX Machine should stop behaving like a loose tool pile and start behaving like a **prototype director**.

The main menu should focus on only the choices needed to define a prototype clearly and quickly. Anything secondary, overflow, diagnostic, or advanced should move into **Ops**.

## Main Menu Structure

### Left Rail
- GX Machine identity / title
- current build state
- quick status light for donor availability and cache health

### Center Builder Column
This is the main prototype definition flow:
- **Game Type**
- **Genre**
- **Player**
- **World**
- **Controls**
- **Settings**

This is the correct center stack because it matches how a prototype is mentally formed:
1. what camera/form it is
2. what kind of game it is
3. who or what the player is
4. what world it lives in
5. how it is controlled
6. what technical and presentation settings apply

### Right Action Column
- framework/runtime selector such as **Pygame / Panda3D**
- camera/form tags such as **Top / Side / FPS / TPS / Custom**
- genre/action tags such as **Action / Adventure / RPG / Sandbox / Text / Fight / Simulation / Custom**
- **Generate Prototype**
- **Random**
- **Play**

This is strong because it separates:
- definition in the center
- execution on the right

## Move These Into Ops
Anything that does not need to be in the fast prototype flow should live in **Ops**.

### Ops should contain
- donor/source browser
- source-pool health
- cache rebuild
- extraction logs
- code block inspector
- validator tools
- bridge launch tools
- runtime smoke tools
- crash logs
- screenshot review tools
- asset audit
- import/export utilities
- profile editor
- advanced archetype rules
- fallback policy editor

## Recommended Improvement Over the Mockup
The mockup idea is correct, but the center categories should become **expandable cards** instead of static labels.

### Example
Selecting **Game Type** opens a compact panel with:
- FPS
- TPS
- Side
- Top
- Isometric
- Text
- Custom

Selecting **Genre** opens:
- action
- adventure
- RPG
- sandbox
- sim
- fight
- puzzle
- survival
- custom

This keeps the screen clean and prevents clutter.

## Best Functional Layout

### Tier 1 — Main prototype flow
Only show:
- Game Type
- Genre
- Player
- World
- Controls
- Settings
- Generate
- Random
- Play

### Tier 2 — Context drawer
When one category is selected, open a side drawer or inset panel with its options.

### Tier 3 — Ops
All overflow and technical systems go there.

## Why This Works
This structure helps in four ways:

1. **reduces clutter**
   The user sees only the key prototype decisions first.

2. **prevents regression pressure**
   Advanced systems are not mixed into the main generation path.

3. **matches prototype thinking**
   Users think in terms of type, genre, player, world, then controls.

4. **gives Ops a real job**
   Ops becomes the machine room, not a junk drawer.

## Strong Recommended Field Model

### Game Type
Defines spatial form:
- side
- top
- isometric
- FPS
- TPS
- text
- custom

### Genre
Defines gameplay loop:
- action
- adventure
- RPG
- sandbox
- simulation
- fight
- puzzle
- strategy
- custom

### Player
Defines embodiment:
- human
- vehicle
- creature
- ship
- cursor/entity
- multiple party
- none / abstract
- custom

### World
Defines environment logic:
- dungeon
- city
- wilderness
- planet surface
- space
- facility
- ocean
- procedural abstract
- custom

### Controls
Defines input model:
- keyboard/mouse
- controller
- twin-stick
- point-and-click
- text parser
- touch-friendly
- custom

### Settings
Only keep the high-value items here:
- graphics / performance
- custom UI / assets
- difficulty
- editor
- help

## Additional Smart Upgrade
Add a **Prototype Summary Box** near the Generate button.

Example:
- Panda3D
- TPS
- action adventure
- player: armored wanderer
- world: ruined city
- controls: keyboard + controller

This would let the user confirm the build before generation.

## Best Rule for the New Menu
If an option is needed often to define the prototype, it belongs in the main GX Machine flow.
If it is diagnostic, technical, repair-focused, or secondary, it belongs in Ops.

## Immediate Menu Direction
The best next menu version should be:
- left status rail
- center prototype builder cards
- right execution column
- all overflow and advanced tools moved to Ops
- compact expandable selectors instead of trying to show every option at once

This should become the menu baseline for the GX Machine makeover.

---

# Detailed Menu Spec — Recommended Input

## Design Goal
The menu should feel like a **clean prototype assembly station**, not a dashboard full of equal-weight controls.

The user should be able to do this quickly:
1. define the prototype
2. confirm the summary
3. generate
4. test
5. move into Ops only if deeper control is needed

---

## Recommended Screen Zones

### Zone A — Left Status Rail
Purpose: identity, state, and confidence.

Show:
- GX Machine title
- current build label
- donor availability status
- cache health status
- engine readiness status
- small indicator for last validation result

Do not overload this rail. It should act like a system heartbeat, not a toolbox.

### Zone B — Center Builder Stack
Purpose: define the prototype.

These are the main builder cards:
- Game Type
- Genre
- Player
- World
- Controls
- Settings

Each card should:
- show the currently selected value
- open a selector when clicked
- support a Custom option
- remain readable at 1280x720 and 1920x1080

### Zone C — Right Action Column
Purpose: execution and confirmation.

Show:
- engine selector
- key tags
- Prototype Summary
- Generate Prototype
- Random
- Play
- Open Ops

This column should never become a dumping ground. Keep it to decision confirmation and action.

---

## Recommended Card Behavior

### 1. Game Type Card
This is the most important card and should drive downstream filtering.

Options:
- Side
- Top
- Isometric
- FPS
- TPS
- Text
- Custom

Behavior:
- selecting one filters donor candidates
- selecting one changes recommended control presets
- selecting one changes world and player suggestions
- selecting one locks out invalid fallback unless user allows it

### 2. Genre Card
Options:
- Action
- Adventure
- RPG
- Sandbox
- Simulation
- Fight
- Puzzle
- Strategy
- Survival
- Custom

Behavior:
- can allow one primary genre and one secondary genre
- influences goal structures, combat, pacing, and UI defaults

### 3. Player Card
Options:
- Human
- Vehicle
- Creature
- Ship
- Party
- Cursor / Abstract Entity
- No embodied player
- Custom

Behavior:
- defines camera assumptions
- defines movement assumptions
- defines animation or control needs

### 4. World Card
Options:
- Dungeon
- City
- Wilderness
- Facility
- Space
- Ocean
- Planet Surface
- Arena
- Abstract Procedural
- Custom

Behavior:
- influences level generator and donor filtering
- influences asset palette and interaction density

### 5. Controls Card
Options:
- Keyboard + Mouse
- Controller
- Twin-Stick
- Point-and-Click
- Text Input
- Touch-Friendly
- Custom

Behavior:
- should recommend defaults based on game type
- should not silently break archetype expectations

### 6. Settings Card
Keep this one shallow in the main menu.

Show only:
- Graphics / Performance
- Custom UI / Assets
- Difficulty
- Editor
- Help

Anything more advanced should link to Ops.

---

## Prototype Summary Box
This is one of the most important additions.

It should show a live sentence or stacked summary like:
- Panda3D
- TPS
- Action / Adventure
- Player: armored scout
- World: ruined facility
- Controls: keyboard + controller

This box should update instantly as selections change.

It should also display:
- donor confidence
- fallback risk
- missing requirement warnings

Example warnings:
- no valid TPS donors found
- using generic movement fallback
- world type not strongly represented in current sources

---

## Generate Button Logic
The Generate button should not be blind.

Before generation, it should run a quick preflight:
- game type selected
- genre selected
- player selected or default assigned
- world selected or default assigned
- valid engine selected
- donor pool available

If something is missing, show a compact warning instead of generating weak output silently.

---

## Random Button Logic
Random should still respect archetype integrity.

Modes recommended:
- Random Everything
- Random Within Current Game Type
- Random Genre Only
- Surprise Me but Keep 3D

This prevents random from constantly dropping into the same side-scroller fallback.

---

## Play Button Logic
Play should only activate when a valid prototype exists.

If no valid prototype exists:
- disable the button
- or show a compact message explaining why

If a prototype exists:
- load latest generated candidate
- show build label
- allow return to menu cleanly

---

## Ops Structure
Ops should be divided clearly into sections.

### Ops / Sources
- donor browser
- source pool routing
- source classification
- donor confidence view
- profile cache rebuild

### Ops / Validation
- syntax check
- import check
- runtime smoke test
- asset validation
- UI bounds
- text fit
- regression check
- crash parser
- screenshot review

### Ops / Extraction
- extracted code blocks
- merge candidates
- patch candidates
- preserved systems viewer
- diff summaries

### Ops / Generator Rules
- fallback policies
- archetype contract editor
- donor weighting
- lane priority
- prompt/profile templates

### Ops / Assets and Tools
- asset audit
- import/export utilities
- editor tools
- replaceable asset manager
- path diagnostics

This keeps Ops useful instead of chaotic.

---

## Donor-Driven Flow Recommendation
The new menu should support this logic:

1. user selects game type
2. system narrows valid donors
3. user selects genre
4. system refines donor lanes
5. user selects player/world/controls
6. system builds a summary and confidence estimate
7. user generates
8. system shows why the prototype came out that way

This is better than asking the generator to invent structure from nothing.

---

## What Must Not Happen
The new menu should explicitly prevent these behaviors:
- all archetypes collapsing into the same side-scroller
- hidden fallback with no explanation
- advanced machine controls mixed into the main build flow
- giant always-open option lists cluttering the screen
- weak generation from missing donors without warning
- Play loading stale or mismatched builds silently

---

## Recommended Visual Style
- dark professional styling
- strong panel separation
- minimal center clutter
- compact typography hierarchy
- large action buttons only where action matters
- category cards with selected-value subtitles
- subtle status colors only for warnings and pass/fail states

Avoid trying to make the menu look like a wall of tools.

---

## Strong Baseline Version
If this were reduced to the cleanest stable first version, it should be:

### Left
- title
- build state
- donor/cache/validation indicators

### Center
- 6 builder cards

### Right
- engine selector
- key tags
- summary box
- Generate
- Random
- Play
- Ops

That is the best foundation before adding anything else.

---

## Best Immediate Next Step
Turn this into a real implementation checklist with:
- exact fields
- exact open/close behavior
- exact items moved into Ops
- summary box content
- preflight warnings
- generate/play state rules

This should become the actionable menu spec for the next GX Machine UI pass.

---

# Additional System Features to Add

## Shared Player Identity Feature
A strong unique feature for GX Machine is **cross-prototype player continuity**.

The machine should optionally allow the user to:
- reuse the same player across different generated prototypes
- save a recent player setup and apply it to the next game
- customize the player before generation
- keep a library of saved player presets

This is valuable because it makes the machine feel like a connected creation system instead of unrelated demos.

## Recommended Player Modes

### Mode 1 — One-Off Player
Use a unique player only for the current prototype.

### Mode 2 — Reuse Recent Player
Reuse the most recently used player automatically.

### Mode 3 — Saved Player Preset
Choose from saved player presets.

### Mode 4 — Generate New Player
Create a new player from current prototype selections.

## Player Data That Should Persist
- player name or label
- embodiment type
- silhouette/archetype
- movement style
- control mapping preference
- color/theme accents
- selected asset set when relevant
- camera preference when relevant

Keep this flexible enough for different game types, but compact enough to survive across multiple prototype formats.

## Menu Placement Recommendation
Add a **Player Memory / Preset** subsection inside the Player card.

Possible quick controls:
- New Player
- Reuse Recent
- Load Preset
- Save Preset
- Edit Current

This keeps the feature visible without cluttering the main menu.

---

## Save / Load / Autosave Feature
This should be an **optional game capability layer**, not forced on every generated prototype.

Some games should support save systems and some should remain arcade-clean.

## Recommended Save Modes

### Mode 1 — No Save
For quick arcade, toy, or disposable prototypes.

### Mode 2 — Manual Save / Load
User can save and load from menus.

### Mode 3 — Autosave + Manual Save
User gets autosave support plus manual slots.

### Mode 4 — Checkpoint Style
For progression-based games that do not need full manual state saving.

## Where This Belongs
This should appear in the **Settings** card as a compact game-state option, with deeper controls inside Ops.

### Main menu visibility
- Save System: Off / Manual / Auto + Manual / Checkpoint

### Ops depth controls
- slot count
- autosave frequency
- save-on-exit behavior
- checkpoint rules
- persistence scope
- profile compatibility rules

---

## Save-System Design Rule
The save system should be treated as a **prototype capability toggle**, not a universal assumption.

That means:
- side arcade prototypes may default to no save
- adventure/RPG/sim prototypes may default to manual or autosave
- sandbox/systemic prototypes may need robust persistence
- text or branching prototypes may use state snapshots

## Autosave Requirements
If autosave is enabled, define clearly:
- when it triggers
- what it writes
- how many rolling autosaves are kept
- whether it warns before overwriting
- whether prototype version mismatches invalidate older saves

## Important Safety Rule
The machine should not silently attach save systems that do not fit the requested prototype.

Example:
- a short arcade fight prototype should not automatically get heavy persistence
- a longer RPG or sim prototype should not launch with no persistence options at all

---

## Recommended Summary Additions
The Prototype Summary box should also show:
- Player Mode: New / Recent / Preset
- Save Mode: Off / Manual / Auto / Checkpoint

Example:
- Panda3D
- TPS
- Action / Adventure
- Player: saved armored scout preset
- World: ruined facility
- Controls: keyboard + controller
- Save Mode: autosave + manual

This makes the prototype state clearer before generation.

---

## Best Rule for These New Features
- **Player continuity** is a GX Machine identity feature.
- **Save/load/autosave** is a prototype capability feature.

Those are related, but should stay separate in the system design.

## Updated Main Flow
1. pick Game Type
2. pick Genre
3. pick Player
4. choose Player Memory mode
5. pick World
6. pick Controls
7. pick Save Mode in Settings
8. review Summary
9. generate
10. play

This should be folded into the next implementation checklist.


---

# Prototype Lab Tags, Flags, and Code Extraction Direction

## Why This Matters
The updated Prototype Lab inventory is exactly the kind of metadata GX Machine needs.

It already contains useful structure such as:
- format buckets like `2D - Hybrid`, `2D - Isometric`, `2D - Side`, `2D - Top`, `3D - First Person`, and `3D - Third Person`
- candidate markers
- per-file notes
- gameplay tags such as `action`, `adventure`, `simulation`, `sandbox`, `fight`, `proc gen`, `logic`, `characters`, `sprites`, `flight`, and `arena`

This metadata should become a first-class donor-ranking layer, not just human notes.

## Best Use of the Tags
The tags should help GX Machine do two jobs:

### 1. Rank top donor candidates
When the user chooses options such as:
- TPS
- simulation
- city
- flight
- sandbox

GX Machine should rank Prototype Lab projects using matching tags and category alignment.

### 2. Extract targeted code blocks
After choosing the top donors, GX Machine should extract only the most relevant code sections for the requested prototype instead of trying to merge whole projects blindly.

## Recommended Metadata Model
Each prototype entry should be normalized into structured fields.

### Required fields
- title
- category
- candidate flag
- file path
- file role
- tags
- quality/confidence notes
- warnings

### Important rule
Do not treat all tags equally.

Use:
- **hard filters** for archetype, camera form, engine compatibility, and embodiment
- **soft rankers** for tags like adventure, simulation, proc gen, logic, arena, characters, sprites, interiors
- **penalty flags** for notes like slow, laggy, older version, needs work, untested, or not finished

This lets the machine prefer relevant donors without trusting weak donors too much. The inventory already exposes many of these useful cues, including category buckets, candidate markers, and file summaries. fileciteturn4file0 fileciteturn4file1 fileciteturn4file2 fileciteturn4file3

## Candidate Ranking Recommendation
Use a layered score:

### Layer 1 — category match
Example:
- if user selects TPS, then `3D - Third Person` gets a major score boost
- if user selects isometric, then `2D - Isometric` gets a major score boost

### Layer 2 — tag match
Example:
- user selects simulation + colony = boost `Distant Colonies`
- user selects FPS + interiors + sandbox = boost `Afterlife Hotel`
- user selects TPS + flight = boost `The Anti-Heroes`

### Layer 3 — file note match
Use description notes like:
- `resourceful for interiors`
- `city resources`
- `good line rendering style`
- `full ai colony simulator`
- `worlds made of blocks`

### Layer 4 — penalty pass
Reduce ranking for notes such as:
- `needs work`
- `slow`
- `laggy`
- `not finished`
- `never been tested`

### Layer 5 — candidate boost
Entries marked `Candidate` should get a modest bonus, not automatic priority.

## File-Level Extraction Rule
Once donors are ranked, the machine should not just copy `main.py` by default.

It should classify files by role first.

### File roles to infer
- runtime entry
- player controller
- camera
- world generator
- combat logic
- simulation logic
- UI/workstation
- effects/SFX
- data/database
- tools/editor
- experimental material/system

The inventory already points toward this because some projects expose distinct subsystem files like `battle.py`, `map.py`, `vehicles.py`, `war_database.py`, `octo.py`, `sound_handler.py`, `sfx.py`, and `surf.py` rather than only `main.py`. fileciteturn4file0 fileciteturn4file1

## Extraction Strategy
GX Machine should use a selective extraction pipeline.

### Step 1
Choose top donor projects using category + tag scoring.

### Step 2
Choose top donor files by role.

### Step 3
Extract relevant code blocks only:
- classes
- functions
- systems
- constants
- helper modules
- data structures
- asset/path helpers when needed

### Step 4
Classify the extracted pieces into build lanes:
- player lane
- camera lane
- world lane
- combat lane
- simulation lane
- UI lane
- audio/effects lane
- save/load lane

### Step 5
Merge into a **custom prototype scaffold** rather than blending donor projects directly.

This is important. GX Machine should not try to stitch whole games together. It should:
- build a fresh scaffold
- insert selected donor systems into the right lane
- resolve naming conflicts
- keep extracted systems traceable

## What Should Be Added Beyond the Tags
The inventory already gives category, tags, and notes, but GX Machine should infer a few more useful fields automatically.

### Additional inferred fields
- engine guess
- camera mode
- player embodiment
- world style
- system strengths
- reuse safety level
- extraction priority
- merge risk
- runtime confidence

## Good extraction targets
- camera controllers
- movement controllers
- world/chunk generators
- AI loops
- spawn systems
- effect systems
- UI modules
- editor tools
- save/load helpers
- data models
- sound generation helpers

## Bad extraction targets
- donor-specific branding
- brittle one-off menu wiring
- hardcoded project-specific paths
- giant unbounded scene scripts
- unfinished experimental code with no isolation

## Suggested Confidence Labels
Each donor and each extracted file should get a confidence label.

### Recommended labels
- Strong Match
- Useful Support
- Experimental
- High Risk
- Blocked

## Suggested Ops Panels for This Feature
### Ops / Candidate Ranking
Show:
- top donor projects
- why they ranked high
- penalties applied
- excluded donors and why

### Ops / File Extraction
Show:
- selected donor files
- inferred file role
- extraction confidence
- merge lane destination

### Ops / Merge Plan
Show:
- scaffold modules to create
- donor systems to insert
- naming conflicts
- dependency warnings
- save/load compatibility warnings

### Ops / Traceability
Show:
- which generated module came from which donor
- what was copied
- what was adapted
- what was newly generated

## Important Safety Boundaries
- do not import an entire donor game just because it has the right tags
- do not let soft tag matches override hard archetype mismatch
- do not ignore warning notes
- do not merge unresolved engine mismatches silently

The current bridge already has useful foundations for this direction, including source-pool root scanning, priority donor file selection, and quick Python/code analysis, so this is an extension of the current donor-selection path rather than a brand new subsystem. fileciteturn4file6 fileciteturn4file13 fileciteturn4file16

## Missing Pieces Worth Adding
- penalty tags, not just positive tags
- file-role inference
- merge lane assignment
- traceability for extracted pieces
- confidence and risk labels
- hard archetype guardrails
- save/load donor awareness
- shared-player compatibility markers

## Final Rule
Tags and notes should decide **which donors and files are most relevant**.

But the final prototype should still be built through:
- archetype contracts
- scaffold assembly
- selective code extraction
- lane-based merge rules
- validation checks

---

# Long-Term Note — Holoverse VR Compatibility

VR prototype compatibility should be treated as a **late-stage feature** after Holoverse is considered stable and well-validated.

## Priority rule
Do not let VR requirements distort the current GX Machine and Holoverse foundation work.

## Recommended placement
Track this under last-priority roadmap items.

## Intended future scope
When Holoverse is mature enough, add optional VR prototype compatibility for supported prototype types, but only after:
- standard input/control flows are stable
- camera behavior is proven
- performance is acceptable
- save/load and player continuity systems are already coherent
- the non-VR prototype pipeline is reliable

VR should be an expansion layer, not an early dependency.

---

# Preprogrammed Donor Manifest System

## Core Direction
GX Machine should use a **preprogrammed manifest system** so it assembles prototypes from approved code parts instead of trying to reinterpret whole donor games live.

This makes the process:
- more stable
- easier to curate
- easier to debug
- easier to expand over time

## Design Goal
The machine should be able to build a custom prototype even when the final game does not already exist as a complete donor.

That means:
- donor projects provide reusable systems
- manifests decide what is allowed
- the scaffold assembles the required parts
- imports and dependencies are resolved deliberately

## Compact Manifest Format
The format should stay readable and low-clutter.

### Recommended format: one compact block per file
```yaml
file: Prototype Lab/2D - Hybrid/Apocalypse Run - Candidate/main.py
category: 2d_hybrid
status: candidate
engine: pygame
roles: [runtime, vehicle, combat, inventory, road_world, pit_mode, audio]
keep:
  - PlayerVehicle
  - Inventory
  - Bullet
  - AudioManager
  - PitStopSession
  - AssetLogger
adapt:
  - main_loop
  - UI_text
  - constants
  - mode_switching
avoid:
  - title_text
  - donor_specific_branding
  - hardcoded_window_title
  - one_off_menu_flow
risk_flags: [medium_size]
notes: health ammo fuel loop, road + pit structure, useful donor
```

This is compact enough to read quickly and structured enough for the machine.

## Minimal Required Fields
Every donor file should have:
- `file`
- `category`
- `status`
- `engine`
- `roles`
- `keep`
- `adapt`
- `avoid`
- `risk_flags`
- `notes`

## Optional Useful Fields
Add these only where needed:
- `imports`
- `depends_on`
- `provides`
- `lane`
- `save_compatible`
- `player_compatible`
- `camera_form`
- `world_type`

That keeps clutter low while still allowing deeper control when a file gets more important.

---

## Import and Dependency Awareness
GX Machine should absolutely know about imports and dependency flow.

It should not just grab code blocks. It should also build a dependency picture.

## Required import/dependency pass
For each donor file, the machine should detect:
- standard library imports
- third-party imports
- local helper dependencies
- asset/path helpers
- globals/constants used by extracted systems
- classes/functions referenced across sections
- initialization order requirements

## Example from the uploaded Pygame file
The current uploaded `main.py` is not a tiny arcade script. It is a multi-system Pygame donor with:
- base imports like `pygame`, `random`, `sys`, `math`, `os`, and `datetime`
- asset path and resolver helpers
- an `AudioManager`
- an `Inventory`
- shared combat/projectile logic
- vehicle systems
- weather
- pit-stop session systems
- a standalone `main()` runtime
- an embedded wrapper path for external tool-window style use. fileciteturn8file2 fileciteturn8file3 fileciteturn8file19

That is exactly why GX Machine needs dependency-aware extraction instead of naive copy/paste.

## What the machine should build per donor file
For each file, generate a compact internal map:

### Import map
- what the file imports
- which are required for extracted pieces
- which are optional

### Symbol map
- classes
- functions
- constants
- top-level globals
- helper utilities

### Dependency map
- which kept symbols rely on which helpers/constants/imports
- which kept symbols depend on update order or init order

### Runtime map
- what must run first
- what can be modularized safely
- what should stay out of shared scaffolds

---

## Keep / Adapt / Avoid Rule
This is the most important rule.

### Keep
Use as-is or near as-is because it is stable and reusable.

### Adapt
Use the idea/system, but rewrite or wrap it for the new scaffold.

### Avoid
Do not bring it into the scaffold unless explicitly forced.

This is better than a simple keep/discard split because many useful systems need light adaptation, not pure reuse.

---

## Lanes the Machine Should Compile Into
Approved pieces should flow into known scaffold lanes:
- runtime lane
- player lane
- camera lane
- world lane
- combat lane
- simulation lane
- UI lane
- audio lane
- save/load lane
- tools/editor lane

The machine should know which lane each kept symbol belongs to before assembly.

---

## Prototype Assembly Rule
When building a custom prototype, GX Machine should:
1. choose top donor files by category and tags
2. read their manifests
3. pull only approved `keep` and `adapt` entries
4. pull required imports/helpers/constants automatically
5. place each piece into scaffold lanes
6. generate glue code between lanes
7. validate imports and runtime flow

That is how it can build a game from parts even when the final game does not already exist.

---

## Easy-to-Read Organization Recommendation
To avoid clutter, use three levels only.

### Level 1 — Project card
Shows:
- project name
- category
- candidate status
- top roles
- quick risk color

### Level 2 — File manifest row
Shows:
- file path
- roles
- keep/adapt/avoid counts
- confidence

### Level 3 — Expand only on demand
Shows the exact kept symbols and dependency details.

This keeps the main view readable.

---

## Suggested Status Values
For files:
- candidate
- stable
- experimental
- blocked

For symbol entries:
- keep
- adapt
- avoid
- blocked

For risk:
- low
- medium
- high

That is enough. Do not overcomplicate the first version.

---

## Machine Knowledge Rule
The machine should not need the whole finished game to exist.

It only needs:
- a scaffold target
- approved donor manifests
- dependency maps
- archetype rules
- assembly lanes
- validation checks

That is the system that allows "build the game from parts." 

---

## Relationship to Existing GX Bridge
This fits the current bridge direction well because the bridge already does:
- source scanning
- profile caching
- donor selection
- source-pool rules
- prototype lab inventory loading. fileciteturn8file7 fileciteturn8file1

So the next layer is not a total reinvention. It is a manifest-and-dependency layer on top of the current donor selection system.

---

## Best Immediate Next Step
Define the first **Donor File Manifest template** and keep it intentionally small:
- compact YAML or JSON
- keep/adapt/avoid
- roles
- imports
- depends_on
- risk flags
- notes

That should become the first curated training format for candidate files.

---

# Human-Light Manifest Workflow

## Core Rule
The user should **not** be expected to define every manifest field by hand.

GX Machine should generate a draft manifest automatically, then let the user:
- approve it
- correct a few fields
- mark a few keep/adapt/avoid items
- move on quickly

## Best Division of Labor

### Machine should infer automatically
- engine
- imports
- top-level classes and functions
- likely file role
- likely lane
- likely camera form
- likely world type
- likely player type
- dependency list
- risk hints
- candidate confidence

### User should only decide manually when needed
- what absolutely must be kept
- what definitely should be avoided
- what deserves candidate priority
- which systems are especially valuable
- whether an experimental donor is allowed

## Best Low-Effort Review Format
Instead of a full big manifest form, show a compact review card.

### Example review card
- file: `main.py`
- engine: `pygame`
- guessed roles: `runtime, combat, inventory, vehicle, audio`
- guessed risk: `medium`
- suggested keep: `PlayerVehicle, Inventory, AudioManager, Bullet`
- suggested adapt: `main loop, UI text, constants`
- suggested avoid: `branding, window title`

Then give only a few quick actions:
- Approve
- Edit Keep
- Edit Avoid
- Mark Experimental
- Skip

That is much better than forcing the user to fill every field manually.

## Suggested Approval Modes

### Mode 1 — Quick Approve
User accepts the auto-generated manifest with no edits.

### Mode 2 — Light Edit
User changes only keep/adapt/avoid lists.

### Mode 3 — Advanced Edit
User opens dependency and lane details.

Default should always be Quick Approve.

## Strong Recommendation
For candidate files where almost nothing should be discarded, the UI should support:
- `Approve Mostly As-Is`

That one action should mean:
- keep most reusable systems
- adapt entry/runtime glue
- avoid only obvious donor-specific branding and brittle one-off wiring

## Minimal User Input Version
If you want the lowest-friction workflow, the only things the user may need to provide are:
- candidate or not
- keep mostly as-is or not
- anything definitely avoid
- any important notes

Everything else should be machine-drafted.

## Best First-Version Manifest Strategy
Use a **two-layer format**.

### Layer 1 — Auto manifest
Machine writes the full internal structured manifest.

### Layer 2 — Human review summary
User only sees a condensed readable summary.

That way the system stays powerful without making the user do database work by hand.

## Final Rule
The machine should do the tedious classification work.
The user should only make the important decisions.
