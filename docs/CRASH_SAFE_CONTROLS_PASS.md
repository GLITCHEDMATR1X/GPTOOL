# Pass 14 — Local Crash Fix

This pass fixes the generated-template crash found while retesting the player-control pass.

## Fixed

- `jump_was_down` is initialized before any proof/screenshot route can read player-controller state.
- Proof JSON now uses a safe fallback when reading jump state.
- The generated template version is now `panda3d_playable_simulation_template.v5`.

## Retest

```bash
python main.py --screenshot-mode --route-proof --screenshot-path screenshots/route.png --proof-path reports/route.json
```
