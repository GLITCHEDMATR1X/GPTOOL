# HoloUtopia Structure Variants

Pass 14 adds district-specific structure variants and purpose layers for the authored HoloUtopia city grid.

These files are design-time authority only. Runtime state, NPC reservations, and interior load state should not be written here.

Rules:

- Every town block should reference a `structure_variant_id` and a `purpose_id` from its town's `structure_variant_profile`.
- Interiors remain lazy/highlight-only unless a variant explicitly says `exterior_only` or `locked_until_story`.
- The renderer should treat these as purposeful structures on foundations, not decorative random line art.
- Districts should keep their identity: portal/civic, residential, market, security, industrial, harbor, and archive areas should not all use the same building set.
