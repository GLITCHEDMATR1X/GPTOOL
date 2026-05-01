# Pass 6 - Rigged Human Asset Import

## Added

- Added `scan-human-assets` to inspect the surrounding asset library for human/character mesh candidates.
- Added `import-human-assets` to copy selected rigged human assets into generated Panda3D projects.
- Added static GLB/GLTF skin and animation introspection for candidate scoring.
- Generated templates now read `assets/characters/humans/human_manifest.json` and try Panda3D `Actor` loading before falling back to static `loadModel`.
- Generated templates now use the shared Panda3D smoke hook when available and honor both `GPT_BRIDGE_SMOKE_FRAMES` and `GPT_BRIDGE_SCREENSHOT_FRAMES`.

## Notes

- GLB/GLTF with detected skin data is preferred for runtime use.
- FBX clips are imported as optional external animation sources and remain skeleton-compatibility dependent.
- Import scans ignore assets already inside the target project so repeated imports do not self-copy generated output.
