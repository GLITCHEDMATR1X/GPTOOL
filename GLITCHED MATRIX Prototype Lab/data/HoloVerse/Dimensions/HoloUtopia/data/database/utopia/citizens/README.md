# HoloUtopia Citizens

Pass 15 starts the city-wide citizen database. These files are authored data, not runtime save state.

- `citizen_manifest.json` stores identity, home, job, personality, traits, activities, and friends.
- `citizen_schedules.json` stores predictable daily cycles.
- `citizen_relationships.json` stores social links.
- `citizen_schema.json` documents required fields.

Runtime should copy active state into `data/database/utopia/saves/` later instead of mutating these source files.


Pass 16 adds the first citizens for `civic_commons_delta` and `glitched_quarantine_epsilon`, completing citizen coverage across all 9 districts.
