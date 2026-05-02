# Panda XR VR Builder Extension

This extension brings the successful Panda XR builder features into GPTOOL as an isolated plugin-style package. It does not import or mutate the original `VR/` prototype.

## Goals

- Keep desktop fallback and proof mode dependency-light.
- Preserve VR-compatible edit semantics without requiring a headset for validation.
- Save every edit to a deterministic manifest.
- Export game-ready OBJ, glTF, GLB, and JSON metadata.
- Preserve deformation, socket connections, path nodes, animation metadata, collision metadata, and operation history.
- Support Oculus Medium-style hand-drawn 3D strokes as real tube meshes.
- Recolor and shade objects through serializable materials that export into glTF/GLB.
- Program runtime behavior through a safe dataflow model instead of arbitrary Python.
- Keep VR performance predictable with stroke-point budgets, radial segment limits, and performance summaries.
- Place editor panels as world-locked AR surfaces so tools, grid settings, and materials can be moved in the scene.
- Maintain a persistent 3D grid with cell-size, dimensions, proximity radius, major lines, snap state, and fill-cell metadata.

## Proof Command

```powershell
python bridge.py panda-xr-proof --output reports/panda_xr_vr_builder_proof --json
python bridge.py panda-xr-quality reports/panda_xr_vr_builder_proof/scene.manifest.json --json
python bridge.py panda-xr-visual-proof --output reports/panda_xr_vr_visual_proof --width 1600 --height 900 --seconds 3 --json
```

The proof creates builder primitives, simulates VR edits, saves/reloads the scene, exports files, validates scene quality, validates export integrity, and writes `proof_result.json`.

`panda-xr-visual-proof` runs a desktop-safe VR simulation, draws a new 3D spiral stroke object from simulated hand points, renders a few seconds at 16:9 with Panda3D offscreen when available, and writes `panda_xr_vr_visual_proof.png` plus `visual_proof_report.json`. It falls back to a deterministic software projection if offscreen rendering is unavailable.

## AR Panels And 3D Grid

The scene manifest now stores `editor_panels` and `grid` at the scene level. Panels are regular world-placed editor surfaces with a transform, size, opacity, content payload, and controls list. The grid stores a persistent lattice origin, cell size, dimensions, proximity radius, major-line interval, snap state, and render strategy.

Snapped grid objects store `metadata.grid` with their cell, filled cell volume, snap group, and batch key. This lets the editor create voxel/pixel-art style objects or room blocks that fill the current grid gap exactly while still giving runtime exporters enough metadata to batch connected snapped objects instead of treating every filled cell as a separate expensive live object.

## Edit Operations

The operation layer is designed to map cleanly to desktop controls or VR controller input later:

- `create_object`
- `two_hand_resize`
- `two_hand_twist`
- `squeeze_morph`
- `begin_stroke`
- `draw_stroke_points`
- `smooth_stroke`
- `grab_move`
- `smooth_grab_resize`
- `set_material`
- `program_behavior`
- `connect_sockets`
- `add_path_node`

OpenXR controller plumbing should call these operations instead of editing Panda3D nodes directly. That keeps save/export behavior deterministic.

## Behavior Programs

Realtime behavior is stored as data, not live code. Supported behavior types are:

- `spin`
- `bob`
- `pulse_color`
- `follow_path`
- `orbit`

The proof writes a `behavior_preview_t1` block so CI can validate deterministic runtime behavior without launching Panda3D or OpenXR.

## Quality Gate

`panda-xr-quality` validates:

- unique object, socket, connection, path node, and behavior ids
- socket connection references
- path node links and behavior targets
- material color/shade data
- editor panel ids, transforms, sizes, and opacity
- persistent 3D grid settings, visible line budget, snapped cell placement, and occupied-cell budget
- stroke point/radial segment performance budgets
- mesh generation, finite vertices, and face index ranges
- operation history sequencing
- VR-facing performance metrics
