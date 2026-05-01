# ChamelionPixels XR OpenXR Lab

This package is a focused fork of the uploaded `panda3d-openxr` source. It keeps the lightweight Panda3D + OpenXR bridge, then adds the missing testing spine needed for Quest Link / PCVR prototyping:

- semantic action system for buttons, triggers, thumbsticks, poses, and haptics
- grip and aim pose anchors for both controllers
- tracking-space fallback from `Stage` to `Local`
- desktop mirror-window support for debugging
- runtime diagnostics snapshot helpers
- workstation-style sample app in `main.py`
- crash logs and patch notes generation in the sample app

## What changed

The upstream repository describes itself as preliminary and says it supports rendering, camera tracking, and hand tracking, while pose, action, and advanced rendering are still limited or future work. This fork fills the practical gap for testing-oriented development by adding a declarative action layer, haptic output hook, diagnostics, and a controlled sample harness.

## Intended target

- Panda3D on desktop
- OpenXR runtime active on the PC
- Quest 2 / Quest Link or similar PCVR workflow using OpenXR-compatible runtimes. OpenXR defines the action model for poses, buttons, analog controls, and haptics, which is why this fork centers on semantic actions instead of device-specific button code.

## Quick start

1. Install dependencies from `requirements.txt`
2. Ensure an OpenXR runtime is active on the machine
3. Connect the headset in PCVR mode
4. Run `python main.py`

## Controls

- `Esc` toggles the settings/workstation panel
- `H` toggles HUD text
- `R` resets the room decorations to their initial colors
- left/right controller trigger pulses local haptics in the sample scene

## Deliverables in this fork

- `p3dopenxr/` upgraded runtime bridge
- `main.py` workstation scene
- `patch_notes/` release note file
- `logs/` runtime/crash output folder (created at runtime)
