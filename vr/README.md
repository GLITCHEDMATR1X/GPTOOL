# Panda XR Builder

Panda XR Builder is the GPTOOL VR creation lane. It starts as a stable Panda3D builder shell with a desktop fallback and a VR-ready control/action model.

The goal is not only to view a world in VR. The goal is to create, place, save, export, and validate build objects from inside the scene.

## Current pass: pass18-vr-builder-core

This pass adds the first clean builder core under `vr/`:

- Panda3D-first entry point: `main.py`
- Desktop fallback controls for testing without a headset
- VR-mode flag and OpenXR readiness fields
- Build tool state: select primitive, place object, undo, save, export, screenshot/proof
- Scene manifest save/load under `projects/`
- Scene export as JSON, OBJ, and MTL under `exports/`
- Settings check mode for CI and non-Panda3D validation
- Deterministic proof mode for AI validation
- Crash-safe log folders

## Run

```bash
python -m pip install -r vr/requirements.txt
python vr/main.py
```

## Settings check

```bash
python vr/main.py --settings-check
```

## Proof run

```bash
python vr/main.py --proof-mode --save-project --export-scene --screenshot-path vr/screenshots/pass18_builder.png --proof-path vr/reports/pass18_builder_proof.json
```

## Controls

```text
WASD / Arrow keys  Move builder rig
Q / E              Rotate builder rig
Mouse wheel        Zoom desktop camera
1                  Cube tool
2                  Wall tool
3                  Floor tile tool
4                  Marker tool
Space / Enter      Place selected object
Z                  Undo last placed object
S                  Save scene manifest
X                  Export scene OBJ/MTL/JSON
F12                Screenshot
Esc                Exit
```

## VR direction

This pass keeps the app runnable on normal machines first. VR support should be layered in this order:

1. Keep desktop fallback working at all times.
2. Add OpenXR runtime detection without failing when no headset is connected.
3. Add headset/camera rig support.
4. Add controller ray pointers.
5. Map grab/place/delete/save/export to controller actions.
6. Add in-world tool palette panels.
7. Add GPTOOL bridge commands for `vr-check`, `vr-proof`, and `generate-vr-template`.

## Design rules

- Do not make VR the only way to test the project.
- Do not hide build failures behind placeholders.
- Every edit tool needs a saved scene manifest and proof JSON path.
- Every generated asset needs clean export metadata.
- Desktop fallback must remain useful for ChatGPT/Codex/Panda3D validation.
