# GPTOOL Pass 15 Changelog - Crash Diagnostics and Stress Proof

- Bumped bridge version to `0.6.5-pass15`.
- Bumped generated template version to `panda3d_playable_simulation_template.v6`.
- Added generated crash diagnostics:
  - `logs/crash_latest.txt`
  - `logs/runtime_latest.json`
  - `logs/last_controls_state.json`
  - `logs/last_scene_state.json`
- Added generated `--stress-proof` mode with `gptool_simulation_proof.v2`.
- Added generated `--force-crash-test` for controlled diagnostics validation.
- Fixed missing generated camera zoom/reset callbacks used by mouse wheel and `R`.
- Added a Panda3D generated stress-proof CI job with artifact upload.
- Updated README, run notes, release notes, and Pass 15 diagnostics docs.
