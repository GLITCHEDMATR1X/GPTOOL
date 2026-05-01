# GPTOOL Pass 14 Changelog — Local Crash Fix

- Bumped bridge version to `0.6.4-pass14`.
- Fixed generated route-proof crash caused by `jump_was_down` not existing before proof JSON was written.
- Initialized player jump state during generated app startup.
- Made proof-state serialization safe with `getattr` fallback.
- Bumped generated template version to `panda3d_playable_simulation_template.v5`.
