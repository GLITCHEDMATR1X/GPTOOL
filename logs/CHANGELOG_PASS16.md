# GPTOOL Pass 16 Changelog - Broader Model Import Proof

- Bumped bridge version to `0.6.6-pass16`.
- Hardened human asset scanning so broad scans skip GPTOOL generated proof/output folders.
- Updated generated playable simulation characters to load imported human Actor meshes from `human_manifest.json` before falling back to procedural bodies.
- Added `actor_loaded` and `asset_manifest_id` to generated scene proof character state.
- Disabled Panda3D audio consistently in generated templates to avoid desktop proof cleanup noise.
- Updated asset validation to ignore known runtime-generated screenshot/proof/log output names.
- Validated a broad local import test with 10 rigged GLB base models, 12 FBX animation clips, GLB/OBJ/FBX export reporting, and stress-proof runtime validation.
