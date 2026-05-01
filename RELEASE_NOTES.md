# Release Notes

## v0.6.6-pass16 - Broader Model Import Proof

- Human asset scanning skips GPTOOL generated proof/output folders during broad-root scans.
- Generated playable simulation characters now use imported human Actor meshes when a human manifest is present.
- Scene proof JSON reports whether each playable character loaded an imported actor.
- Asset validation ignores known runtime-generated screenshot/proof/log outputs.
- Validated a broad import of 10 rigged GLB models and 12 FBX animation clips from the local backup tree.

## v0.6.5-pass15 - Crash Diagnostics and Stress Proof

- Generated Panda3D templates write crash and runtime diagnostics under `logs/`.
- Added `--stress-proof` for deterministic movement, sprint, jump, Tab swap, camera zoom/reset, route markers, proof JSON, and screenshot capture.
- Added `gptool_simulation_proof.v2` proof output.
- Fixed missing generated camera zoom/reset callbacks that could break mouse wheel or `R` controls.
- CI now includes a Panda3D generated stress-proof job with artifact upload.

## v0.6.4-pass14 — Simulation Route Proof

This repository baseline comes from the tested Pass 12 GPTOOL package.

- Lean source package suitable for GitHub.
- Generated Panda3D templates include two playable simulation testers.
- `Tab` swaps active control between the male and female tester.
- Route proof mode simulates movement, swapping, route markers, score change, scene proof JSON, and screenshot capture.
- Package cleanup tooling keeps generated proof worlds and build clutter out of the source repository.
- CI workflow added for version, source syntax, package audit, template generation, settings check, and generated project syntax.
