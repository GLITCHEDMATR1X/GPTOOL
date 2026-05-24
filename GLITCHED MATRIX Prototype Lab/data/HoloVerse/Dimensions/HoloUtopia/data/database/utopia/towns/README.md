# HoloUtopia town blocks

This folder is the authored, safe-to-edit town layout lane for the living-world Utopia city.

Current towns:

- `central_core_civic_ring.json` — the portal-hub district, with the central artifact/portal ring, civic blocks, starter home blocks, vendor/social blocks, future expansion pads, schedule nodes, and one guard patrol loop.
- `residential_alpha.json` — the first living-neighborhood district connected to the Central Core through a west gate, with editable home clusters, social plaza, service nodes, gardens, shelter behavior, starter NPC slots, and a guard patrol loop.
- `market_crossing.json` — the first social-commerce district, with vendor lanes, courier exchange, plaza gathering nodes, service counters, guard patrols, evening events, and market alert/shelter hooks.
- `security_gate.json` — the first controlled-access district, with gate checkpoints, watch towers, guard barracks, scanner arrays, shelters, command nodes, convoy clearance, and lockdown hooks.
- `industrial_yard_alpha.json` — the first fabrication/service district, with power, repair, cargo, robotics, night-shift, and production schedule nodes.
- `harbor_grid_beta.json` — the first water/coastal district, with boardwalks, ferries, docks, storm gates, ocean scanners, public markets, shelters, and harbor patrol loops.
- `archive_quarter_gamma.json` — the first MatrixCore/archive district, with public lore halls, memory pools, research labs, restricted vaults, courier data routes, archive guards, shelters, and lore-pulse event hooks.

Rules:

- Authored town files describe identity, geometry, schedules, portals/anchors, and block ownership.
- Runtime systems should write save state somewhere else, not back into these files.
- NPCs should reference `schedule_nodes` and block ids instead of hardcoded coordinates.
- New towns should be added one at a time, then validated with `data/HoloVerse/tools/validate_holoutopia_towns.py`.
- Central/portal towns use `portal_hub`; normal towns use `district_anchor` and `neighbor_towns`.
- Security towns should define patrol loops and shelter/alert event hooks before NPC combat or AI authority is attached.

## Pass 5 - Industrial Yard Alpha

Adds the first fabrication/service district for engineers, builders, couriers, repair techs, guard support, night shifts, and future vehicle/robot production schedules. Keep authored identity and runtime state outside these town files.

## Pass 6 - Harbor Grid Beta

Adds the first waterfront/water-service district for ferries, docks, tide power, public boardwalks, ocean-edge scans, storm warnings, cargo transfer, and future water traversal schedules. Keep ocean cells explicit so later water rendering and NPC routing can disagree safely instead of overwriting authored town data.
## Pass 7 - Archive Quarter Gamma

Adds the first MatrixCore/archive district for public lore access, memory witness events, research/simulation labs, restricted vaults, data courier movement, archive guard patrols, and future narrative schedule hooks. Keep authored identity here and runtime memory/save changes in separate state/log files.


## Pass 8 — Grid parity / city atlas

All current district JSON files now share the same canonical district frame:

```text
10 columns x 8 rows
64 world units per block
alignment_id: utopia_even_10x8_v1
```

The city-level placement authority is now:

```text
data/database/utopia/city_grid_atlas.json
```

Use that atlas to place full districts around the Central Core. Use the town JSON files to add local blocks, homes, schedule nodes, patrol routes, and future NPC spawn slots. The next neighborhood-detail pass should start with `residential_alpha` without changing artifact routes or `main.py`.


## Pass 9 — Residential Alpha neighborhood buildout

The first real neighborhood detail layer now lives at:

```text
data/database/utopia/neighborhoods/residential_alpha_neighborhood_01.json
```

This file adds safe-edit addresses, lots, front doors, porches, mailboxes, room anchors, shared spaces, and micro-schedule nodes. Town files remain the district-frame/block authority; neighborhood files are the living-world detail layer.


## Pass 15 — 3D district massing

Every town block now has `structure_massing_profile`. This makes district structures render as purposeful 3D exterior volumes while keeping interiors highlight-only and avoiding arbitrary lines through buildings.


## Pass 16 — Complete 3x3 district frame

Two new authored districts complete the 3x3 atlas:

- `civic_commons_delta`: southwest education, parks, recreation, civic service, culture, and family/student housing.
- `glitched_quarantine_epsilon`: northeast restricted anomaly containment, recovery housing, research, decontamination, and signal-dampening.

All nine districts use the same 10x8 frame, have 3D structure massing profiles, and remain safe-edit JSON.
