# Pass 8 - Female Rig Validation and Third-Person Open World Testbed

## Added

- `scan-human-assets` and `import-human-assets` now support:
  - `--prefer` for ranking preferred source tokens.
  - `--require` for filtering to a target source family.
  - `--rigged-only` for base meshes with detected skin data.
  - `--clean` to clear only `assets/characters/humans` before importing.
- Generated human projects now use the imported Actor as the controlled third-person player.
- Added camera-relative WASD movement, Q/E camera rotation, sprint, mesh cycling, and animation cycling.
- Added procedural streaming gray platform chunks around the player for open-world traversal testing.

## Improved

- Female-only import can now stay clean and avoid male survivor or prior generated smoke assets.
- The preview camera backs off and normalizes human scale more conservatively so female rigs fit in 16:9 screenshots.
- GPTOOL-generated example output is ignored during broad asset scans to avoid self-import clutter.

## Notes

- Female rig validation used the two rigged `Female Survivor` GLBs plus one female idle FBX source clip.
- FBX export remains honest: GLB-to-FBX is skipped because this pipeline does not have a rig-safe FBX writer.
