# FBX Gib Loader / Unified Mesh World Artifact Manifest

Date: 2026-05-03
Project: GPTOOL / FBX Gib Loader editable mesh-world prototype

## Status

The recovered full-body pass is the current known-good visual baseline. The previous strong pass kept the mesh data but regressed the proof view by tightening the camera/framing too much, which made the character appear cut or lost.

The recovered pass restores the full-body character framing while keeping the unified one-file Panda3D app design:

- Root `main.py` is the single app file.
- Editable character mesh and editable world live together.
- `Idle.glb` imports as editable geometry.
- Character/world targets can be selected and edited.
- `F12` screenshot proof path is present.
- `F11` clean UI toggle is present.
- `--clean-shot` is available for UI-free proof screenshots.

## Artifact inventory from ChatGPT workspace

These files were generated in the ChatGPT environment. They were not committed as binary files because the main zips are approximately 177 MB each, which exceeds normal GitHub repository file handling and this connector does not expose Git LFS or release-asset upload support.

| Artifact | Size bytes | SHA-256 | Notes |
|---|---:|---|---|
| `fbx_gib_loader.zip` | 184,794,630 | `3ccc686a202bc3c4abd14bdb3ca23574cb09d986537370bad1156636b6028a95` | Original uploaded source archive. |
| `fbx_gib_loader_unified_strong_pass.zip` | 184,830,699 | `59e78c3e3f6bb5cd1e85e4c527b3613b7a4a2432542abad797e399e41bb482d8` | Regression: mesh remained valid, but camera/proof framing became too tight. Do not use as baseline. |
| `fbx_gib_loader_recovered_fullbody_pass.zip` | 185,456,871 | `7ad9b088ad2b0e93dd4fef8b3c8e97f1bb6bf9d9ef2276660b9c6c7e2a0e8583` | Current recovered baseline. Use this version for the next pass. |
| `fbx_recovered_final.png` | 147,006 | `d29794651ee6b1a2e9cfa385823e6c69cc0ca5949da28dfdb4f3a8aed0cb66ac` | Full UI screenshot proof. |
| `fbx_recovered_clean.png` | 64,151 | `1b306f38cfd018bd21243e27b26d174337041ab2815226dbbc66c99941630cb9` | Clean proof screenshot. |
| `fbx_recovered_view_wire.png` | 262,258 | `77900e2e9e0a26e027b2453ae7c550740c4d906dda9511f64f683d52ab353286` | Wireframe proof screenshot. |

## Visual regression notes

Known-good screenshot traits:

- Character is visible full-body, not cropped at the edges.
- Ground plane/world remains visible around the mesh.
- UI does not hide the character.
- Character import reports approximately `87,036` vertices and `29,012` triangles.
- Camera should frame the whole figure with margin, not just the torso or upper body.

Bad-pass screenshot traits:

- Character appeared visually lost/cut due to tight camera framing.
- The mesh was still present internally, so this was a view/framing regression rather than a broken GLB import.

## Next recommended pass

1. Keep `fbx_gib_loader_recovered_fullbody_pass.zip` as the baseline.
2. Add a small automated screenshot comparison routine:
   - run app headless
   - save clean screenshot
   - verify non-empty foreground bounds
   - verify full-body margin
   - write a one-page report
3. Improve in-world mesh editing UX without changing the camera baseline:
   - target outline
   - brush radius preview
   - vertex/face count panel
   - save/load edited scene state
4. Treat FBX animation retargeting as a separate pass. Do not fake animation support.

## Binary storage recommendation

For long-term repository tracking, use one of these instead of committing the 177 MB zip directly:

- GitHub Releases with binary assets
- Git LFS for `.zip`, `.fbx`, `.glb`, and screenshots
- A separate artifact bucket with this manifest committed to GPTOOL

Until one of those is available, keep the recovered zip from the ChatGPT handoff and use the SHA-256 above to verify it before continuing work.
