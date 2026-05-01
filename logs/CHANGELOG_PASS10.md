# CHANGELOG PASS 10 — Panda3D Headless Scene Proof

Version: `0.6.0-pass10`

## Added

- Added a required scene-proof path for Panda3D smoke tests via `--proof-path` and `--require-proof`.
- Added `GPT_BRIDGE_SMOKE_PROOF_PATH` support to the Panda3D adapter.
- Added a `panda3d_smoke_proof.v1` JSON proof file from the smoke hook.
- Added headless Panda3D smoke support for generated templates using `--window-type none`.
- Fixed portable runtime discovery so virtualenv Python symlinks are not resolved away from their `pyvenv.cfg`.

## Fixed

- Generated templates no longer crash in `ShowBase(windowType="none")` when no camera/window exists.
- The smoke hook now writes scene proof before ordinary update tasks by using early task priority.
- Generated templates include a fallback proof writer if the bridge hook is unavailable.

## Result

A generated Panda3D project can now prove that real Panda3D imported, the scene graph built, UI nodes attached, and the app exited cleanly in a display-less environment. Screenshot proof still requires a real display/offscreen-capable runtime.
