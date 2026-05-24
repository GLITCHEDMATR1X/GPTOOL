# Pass 86 - Zonez Boot Restore

The Pass 85 embedded fast-boot change was reverted because it changed normal Zonez startup behavior and broke Zones in the player build.

## Restored behavior
- Zonez uses the Pass 84 real SandboxApp adapter again.
- Heavy bootstrap trimming is only used for artifact self-test paths, not normal gameplay entry.
- Zonez remains a real same-window sandbox route, not the old portal-router placeholder.

## Kept from previous passes
- Vector Wars one-adapter cleanup and asset SFX integration remain intact.
- Root HoloVerse audio ownership remains intact.
- Gleebs red/single-surface dialogue contract remains intact.
