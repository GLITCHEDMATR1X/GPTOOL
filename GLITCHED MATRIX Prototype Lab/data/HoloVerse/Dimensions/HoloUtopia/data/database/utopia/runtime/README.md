# HoloUtopia runtime bridge

This folder contains runtime-facing configuration for showing HoloUtopia inside the HoloVerse hub/world.

Rules:

- Authored city/citizen data remains read-only.
- The runtime bridge renders visual layers only.
- It does not write logs, mutate citizen schedules, touch artifact routes, or add collision.
- Interiors remain highlight/selection only.
- Citizen markers are generated from the schedule runner at the current city clock.

The bridge is installed by `data/HoloVerse/holoutopia_game_runtime.py` and can be hooked into `main.py` using `tools/install_holoutopia_runtime_hook.py`.

## Pass 24 robot civilians

Citizen markers are no longer flat/cross glyphs.  Runtime citizens are tiny collisionless wire robots with:

- torso/head/feet contact pad;
- a forward visor/antenna so the facing direction is visible;
- light bobbing and limb swing from the current schedule activity;
- stable same-node spread so plaza/work crowds do not collapse into one marker;
- color driven by activity state and danger override.

The robots are still visual-only.  They do not add collisions, path blockers, runtime logs, or authored-data writes.
