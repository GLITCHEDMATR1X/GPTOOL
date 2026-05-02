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

## Proof Command

```powershell
python bridge.py panda-xr-proof --output reports/panda_xr_vr_builder_proof --json
python bridge.py panda-xr-quality reports/panda_xr_vr_builder_proof/scene.manifest.json --json
```

The proof creates builder primitives, simulates VR edits, saves/reloads the scene, exports files, validates scene quality, validates export integrity, and writes `proof_result.json`.

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
- stroke point/radial segment performance budgets
- mesh generation, finite vertices, and face index ranges
- operation history sequencing
- VR-facing performance metrics
