# HoloVerse Roadmap Status

Version: 0.10.75-dimension-presentation-contract
Source: HoloVerse double check.zip + Pass 74 cleanup + Pass 75 presentation contract
Purpose: one current project status log; runtime/test/crash logs are excluded from clean pass packages.

## Current artifact geometry

| Slot | Dimension | Route | Status |
|---:|---|---|---|
| 0 | Code Red Vector | native_panda | playable_candidate |
| 1 | Etch-Line | native_panda | playable_candidate |
| 2 | Fractured Dimension | native_panda | playable_candidate |
| 3 | Holo Campaign | native_panda | playable_candidate |
| 4 | Holo Conquest | native_panda | playable_candidate |
| 5 | Vector Wars | native_panda | playable_candidate |
| 6 | Zonez | native_panda | playable_candidate |
| 7 | HoloCore | same_window_mode | playable_candidate |

Artifact rule: all eight geometric artifact slots stay same-window. No active artifact route should use embedded_external or child-window fallback.

## Current route counts

- in_world_region: 8
- native_panda: 7
- same_window_mode_holocore: 1
- embedded_external: 0
- placeholder_mode: 0

## Region / bot routes

| Bot | Region | Dimension | Route |
|---|---|---|---|
| Archivist | METROPOLIS | Metropolis Robot Lab | in_world_region |
| Ember | DESERT / PYRAMID CRAFT | Ember Hangar | in_world_region |
| IO | FLAT | HoloForge | in_world_region |
| Mirror | ICE | Frost Circuit | in_world_region |
| Nyx | GREEN HILLS | Hills of Life | in_world_region |
| Orbit | SPACE / HoloSpace | HoloCore | same_window_mode |
| Sable | URBAN | Urban Warzone | in_world_region |
| Solace | MUSHROOM | Oddities | in_world_region |
| Vanta | FORESTS | Forest Growth | in_world_region |

## Stabilization passes captured

- Pass 55: Holo Campaign source-backed native embed.
- Pass 56: Etch-Line source-backed native embed.
- Pass 57: Etch-Line ESC/0 return contract.
- Pass 58: Fractured Dimension native embed.
- Pass 59: Holo Conquest native embed.
- Pass 60: Vector Wars native Panda adapter.
- Pass 61: Zonez native adapter and placeholder route removal.
- Pass 62: Fractured Dimension Panda audio path fix.
- Pass 63: Fractured Dimension cleanup: camera weapon/projectile leakage.
- Pass 64: Code Red Vector native adapter.
- Pass 65: Core artifact-chain cleanup guard.
- Pass 66: Native window/focus isolation for artifact modes.
- Pass 67: Aircraft unlock + clean HoloSpace boundary loop.
- Pass 68: TAB / flight input isolation.
- Pass 69: HoloCore ESC/0 return, UI authority, shared holocore asset path.
- Pass 70: Native audio bed + Etch-Line return-freeze fix.
- Pass 71: Dimension UI H-toggle defaults hidden; Zonez excluded.
- Pass 72: Zonez connection repair + Vector Wars gameplay polish.
- Pass 73: Code Red Vector held LMB/RMB turret controls.
- Pass 74: Presentation source hygiene: duplicate HoloCore assets removed, adapter logs gated, stale launch validator retired.
- Pass 75: Dimension presentation contract: normalized native artifact status/help text, fixed Holo Campaign copy/paste status, and added a static validator for HoloVerse return/H-toggle rules.

## Current gameplay-loop decisions

- Number-key region travel is player-hidden by default; Shift+F9 toggles development-only region travel.
- TAB air travel requires a saved Ember aircraft. Starter fallback craft does not unlock flight.
- Flying into outer world-shell/space boundaries transitions through clean HoloSpace flow and allows return to hub without number keys.
- H toggles universal HUD in the hub. Inside native dimensions, H toggles only that dimension's old/source UI. Zonez keeps its game UI visible.
- ESC or 0 returns from artifact dimensions and HoloCore to the HoloVerse hub.

## Packaging rule

Ship clean packages without stale logs, smoke screenshots, crash remnants, __pycache__, pass backups, or generated diagnostics. Runtime logs may be recreated locally during real testing. Adapter-specific logs are disabled unless `HOLOVERSE_NATIVE_ADAPTER_LOGS=1` is set.

## Presentation priorities remaining

1. Full artifact chain test: enter, play/move, exit, enter the next artifact forward and backward through all 8 slots.
2. Confirm no camera children, HUD nodes, music/SFX, input handlers, tasks, collision nodes, or render roots leak between dimensions.
3. Confirm Windows screen recording captures the current native artifact view, not the hub starting point.
4. Continue normalizing any deeper legacy UI panels if H toggled content still shows old source-only wording.
5. Continue region/TAB/world-authority polishing separately from artifact dimensions.
