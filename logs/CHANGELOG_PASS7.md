# Pass 7 - Human Mesh Viewer and Export Robustness

## Added

- Generated Panda3D human projects now open as a 16:9 gray studio viewer.
- Imported human meshes are centered and camera-framed for screenshot proof.
- Added preview controls:
  - `[ / ]` cycles imported human meshes.
  - `Tab` cycles embedded Actor animations when available.
- `import-human-assets` now supports `--export-formats glb obj fbx`.
- Imported base assets now include export records in `human_manifest.json`.

## Improved

- Human import selection now avoids duplicate base signatures so the importer pulls in survivor variants and other rigged human meshes instead of repeated `Idle.glb` copies.
- GLB exports from GLB sources are rig-safe copy-through exports.
- OBJ exports are generated as static geometry via `trimesh` when possible.
- FBX export is explicitly reported as copy-through only for FBX sources; GLB-to-FBX is marked skipped instead of pretending to be rig-safe.

## Notes

- External FBX animation clips remain skeleton-compatibility dependent.
- The generated viewer prefers embedded Actor animations before attempting external clip libraries.
