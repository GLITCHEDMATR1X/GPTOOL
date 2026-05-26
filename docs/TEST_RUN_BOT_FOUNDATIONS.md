# GPTOOL Test Run Bot Foundations

Pass 22 adds the first explicit game-journey input-plan layer for GPTOOL.

This does not pretend to be a full autonomous player yet. It creates the safe foundation:

```text
repeatable input plans
manifest validation
journey smoke environment hooks
screenshot checkpoints
reports that say what would be played
```

## Why this matters

HoloVerse / HoloCore / HoloUtopia patches should eventually be judged by real player journeys, not only syntax checks.

Examples:

```text
enter artifact
move / shoot / interact
capture proof
exit to hub
confirm cleanup
```

## New task actions

```text
write_input_plan       Write a gptool.input_plan.v1 file and Markdown summary.
validate_input_plan    Validate inline or file-based input plans.
screenshot_checkpoint  Check whether a proof screenshot exists and is large enough.
panda3d_journey_smoke  Run bridge.py panda3d-smoke while exposing GPT_BRIDGE_JOURNEY_PLAN and GPT_BRIDGE_JOURNEY_ID.
```

## Input plan schema

Input plans use:

```text
gptool.input_plan.v1
```

Supported input actions:

```text
wait
press
hold_key
release_key
tap_key
mouse_move
mouse_click
hold_mouse
release_mouse
enter_artifact
exit_to_hub
screenshot
assert_state
note
```

## Current limitation

The Panda3D projects still need playback hooks to consume `GPT_BRIDGE_JOURNEY_PLAN`. Until those hooks are added, GPTOOL can generate and validate the exact journey, pass it to smoke runs, and collect reports, but it cannot force gameplay movement in apps that do not read the plan yet.

## Next target

Pass 23 should add HoloVerse-side journey playback hooks so artifact-chain and Vector Arena controls plans can drive real in-window input simulations.
