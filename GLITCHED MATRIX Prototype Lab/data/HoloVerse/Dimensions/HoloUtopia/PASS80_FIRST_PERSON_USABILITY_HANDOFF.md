# HoloUtopia Pass 80 — First-Person Usability

Built on Pass 79 first-person scaffold.

## Goals

- Make first-person mode feel like a ground-level town walk instead of an overhead camera.
- Keep Town Focus simulation state connected and read-only.
- Keep first-person local to the isolated town only.
- Preserve return to tilt-shift Town Focus.

## Changes

- First-person start state now uses visible focused-town bounds and true lower-bound ground estimate.
- Bad overhead camera memory from older first-person saves is ignored and replaced with a safe ground-level town entry spawn.
- Spawn looks inward toward the selected town center.
- First-person eye height is locked to a conservative human-readable level.
- FOV is set to 60 for a closer but still playable first-person view.
- Walk/jog speeds were reduced for inspection.
- Crosshair prompt now shows a non-mutating target hint: event, activity, citizen, building, or open space.
- E interaction prioritizes nearby citizens before broad building center hits.
- Large Town Focus labels/need beacons/health labels are hidden while walking and restored on exit.

## Preserved

- No HoloVerse route changes.
- No HoloCore changes.
- No artifact routing changes.
- No authored schedule mutation.
- No full-city NPC simulation in first-person.
- No runtime_state file in the patch.
