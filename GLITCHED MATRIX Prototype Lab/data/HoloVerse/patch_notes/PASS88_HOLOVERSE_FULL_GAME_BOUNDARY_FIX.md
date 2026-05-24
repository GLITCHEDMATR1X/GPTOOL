# Pass 88 — HoloVerse Full-Game Boundary Fix

This pass corrects the architectural regressions reported after Pass 87.

## Decisions

- Vector Wars no longer launches the pygame `main.py` as an embedded/external child window. That route caused a tiny window behind HoloVerse and could close the host.
- Vector Wars is restored to the same-window Panda3D adapter route. The pygame `main.py` remains preserved as source/fallback, but a true main.py experience inside HoloVerse requires a real Panda3D port rather than process embedding.
- HoloVerse root soundscape is gated while native/external modes own the scene so hub music cannot restart over dimension music.
- Native/external returns now force walking hub control state, disable flight/cockpit/HoloSpace flags, reset velocity, reload the default shell, and place the player at the hub anchor.
- Shared `database/` and `brain/` are moved outside the HoloVerse folder and resolved through `APP_DATA_DIR` / `HOLOVERSE_APP_DATA_DIR`.
- HoloVerse HUD readability is shifted away from thin cyan over white surfaces to red text with darker backing panels.

## Validated

- Route validators pass with Vector Wars as `native_panda`.
- Generated asset path validator passes.
- Gleebs red lore contract validator passes using sibling `database/MatrixCore`.
- Targeted Panda3D offscreen checks passed for Vector Wars, Zonez, and HoloCore.
