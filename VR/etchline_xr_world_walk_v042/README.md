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
2. For headset mode, also install dependencies from `requirements-xr.txt`
3. Ensure an OpenXR runtime is active on the machine
4. Connect the headset in PCVR mode
5. Run `python main.py`

## Controls

- `Esc` toggles the settings/workstation panel
- `H` toggles HUD text
- `R` resets the room decorations to their initial colors
- left/right controller trigger pulses local haptics in the sample scene

## Panda XR Builder Core

The builder core is desktop-proofable and does not require an OpenXR runtime. It provides a clean deformable object model for cubes, spheres, cylinders, capsules, floors, and walls, plus sockets, connections, path nodes, control-point deformation, scene manifests, OBJ/glTF/GLB geometry export, and JSON metadata export.

Run the deterministic proof from the project root:

```powershell
python main.py --panda-xr-proof --output assets/generated/panda_xr_builder_proof
```

The proof creates builder primitives, applies smooth control-point deformations, saves and reloads the scene manifest, exports deformed OBJ, glTF, and GLB geometry, writes scene metadata, and writes `proof_result.json` with checksums.

## Deliverables in this fork

- `p3dopenxr/` upgraded runtime bridge
- `main.py` workstation scene
- `p3dopenxr/builder_core.py` desktop-safe deformable builder/export core
- `patch_notes/` release note file
- `logs/` runtime/crash output folder (created at runtime)
