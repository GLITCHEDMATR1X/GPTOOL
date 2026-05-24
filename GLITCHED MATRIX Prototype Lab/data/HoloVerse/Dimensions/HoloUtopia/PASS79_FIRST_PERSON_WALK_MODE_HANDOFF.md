# HoloUtopia Pass 79 - First-Person Walk Mode Handoff

Pass 79 adds the first playable walking layer inside the existing Town Focus system.

## Current loop

1. Start in Full City Overview.
2. Click a district signal or building to enter Town Focus.
3. Press `Enter` or `P` to enter first-person walk mode inside the isolated town.
4. Walk with `WASD`, hold `Shift` to jog, and use RMB drag for mouse look.
5. Press `E` to interact with the crosshair target.
6. Press `ESC` to return to the tilt-shift Town Focus view.
7. Press `ESC`, `Backspace`, or `0` again to return to the full city overview.

## Interaction stack

First-person `E` reuses the existing Town Focus selection stack:

- local event diamonds
- activity clusters
- route/flow trails
- buildings
- citizens

It does not create a second disconnected interaction system.

## State policy

First-person player/camera position is stored per town in runtime state under:

`first_person_player_memory`

This is runtime/session memory only. It does not mutate authored schedules, town JSON, citizen schedules, HoloVerse routes, HoloCore routes, or artifact adapters.

## Performance rule

First-person mode only works inside the selected isolated Town Focus district. It does not enable full-city visible NPC simulation.

## Known next polish

- Better spawn point tuning per district.
- Better line-of-sight / nearest-target prompt.
- More readable first-person NPC movement.
- Optional low wall/building avoidance if needed later.
