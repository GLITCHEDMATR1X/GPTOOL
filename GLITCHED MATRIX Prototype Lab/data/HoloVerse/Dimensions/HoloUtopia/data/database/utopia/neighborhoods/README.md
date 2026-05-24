# HoloUtopia Neighborhoods

Neighborhood files add detailed, safe-edit living spaces inside the even town/district frames.

Pass 10 keeps the Pass 9 neighborhood shell and adds 3D building massing/capacity metadata.

Active neighborhood:

```text
residential_alpha_neighborhood_01.json
```

Rules:

- Keep town `grid_size` stable.
- Add addresses, lots, porches, room anchors, shared spaces, and micro-schedule nodes here.
- Runtime save files should never overwrite these authored files.
- Use `tools/validate_holoutopia_neighborhoods.py` after edits.


## Pass 10: Residential Alpha 3D massing

Residential Alpha lots now define `building_profile` records with:

- `building_type`
- `height_class` (`low`, `mid`, `tall`)
- `floor_count`
- `residential_capacity`
- `current_reserved_capacity`
- `height_units`
- `roof_type`
- `style_variant`

The current starter capacity is **71 residents** across 8 lots. Interiors remain abstract: each building has floor anchors, lobby/core anchors, and roof anchors for future NPC scheduling without building full interiors yet. Runtime resident assignments should be written to save-state files, not these authored neighborhood files.

## Pass 11 — lazy interiors and NPC schedule seed

Residential Alpha lots now reference highlight-only interior blueprint files under `data/database/utopia/interiors/`.
Only the highlighted building should load its abstract interior cutaway. NPC identity, job, daily schedule, and friendship seeds live under `data/database/utopia/npcs/`.

Runtime state should be saved separately under `data/database/utopia/saves/`.


## Pass 12 foundation / visual sanity contract

Residential buildings now carry a `foundation_profile` beside their `building_profile`. The foundation is the ground-contact authority: buildings must sit fully on their pad, the pad masks the underlying district grid, and early massing should use clean outer-perimeter lines only. Do not add decorative roof diagonals, crossing guide lines, or micro-node markers through a building shell unless that building is actively highlighted and its lazy interior is loaded.

Safe edits:

- `foundation_profile.pad_size_blocks` may be increased if the building footprint grows.
- `foundation_profile.visible_ground_pad` may be toggled for diagnostics, but should stay true for normal presentation.
- `building_profile.line_policy.draw_roof_cross_braces` should stay false unless a future archetype has an authored structural reason.

## Pass 13 — Cross-district residential infill

Residential properties are now allowed outside Residential Alpha when they make sense for the district: vendor lofts in Market Crossing, worker dorms in Industrial Yard Alpha, waterfront apartments in Harbor Grid Beta, scholar housing in Archive Quarter Gamma, guard housing in Security Gate, and small civic residences near the Central Core.

Rules:
- Keep every property on its authored foundation pad.
- Do not draw unexplained lines through buildings.
- Interiors stay lazy/highlight-only until a building is selected.
- Capacity is authored data only for now; runtime population assignment comes later.

## Pass 14 structure variants

Town blocks now carry district-specific `structure_variant_id`, `purpose_id`, `activity_affordances`, and `interior_policy` metadata. Residential infill remains capacity/foundation-ready, while non-residential districts now expose their own service, trade, security, production, water, and archive purposes for future NPC schedules.


## Pass 16 residential additions

- `civic_commons_family_housing_01`: family/student/caretaker housing for Civic Commons Delta.
- `glitched_quarantine_recovery_housing_01`: restricted recovery and emergency housing for Glitched Quarantine Epsilon.
