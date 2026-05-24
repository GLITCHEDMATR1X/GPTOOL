# HoloUtopia NPC Registry

Safe-edit NPC seed data for the living-world schedule system.

Pass 11 adds identity, home, job, schedule, activity, and friendship data for the first Residential Alpha residents.

Rules:

- `npc_manifest.json` contains stable authored identities.
- `npc_schedules.json` contains editable schedule plans.
- `npc_relationships.json` contains social links.
- Runtime mood, pathing, inventory, and current action should be saved under `data/database/utopia/saves/` and must not overwrite these authored files.
