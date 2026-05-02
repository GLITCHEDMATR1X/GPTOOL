# HoloVerse Fauna + Asset Knowledge Workflow — Pass 17/18/19/20/21

This workflow improves HoloVerse fauna and asset quality with an assets-first loop instead of vibe-coding directly into the main world.

## Goal

Create isolated Panda3D preview scenes for creature silhouettes, region identity, color accents, simple idle motion, imported model candidates, and metadata-first asset knowledge before any asset is promoted into the real HoloVerse project.

## Preview tool

```bash
python tools/holoverse_fauna_preview.py ./previews/holoverse_fauna_pass17 --force
```

Optional focused previews:

```bash
python tools/holoverse_fauna_preview.py ./previews/hills_fauna --region hills --force
python tools/holoverse_fauna_preview.py ./previews/water_fauna --species water_solace_reef_glider --force
python tools/holoverse_fauna_preview.py ./previews/fauna_small_set --limit 3 --force
```

## Resource scanner

Pass 20 adds a resource intake scanner for local backup/model folders. It searches for 3D model files and ranks likely fauna candidates before import.

```bash
python tools/holoverse_fauna_resource_scan.py /path/to/backup/models --output-dir reports/fauna_scan
```

Multiple roots are supported:

```bash
python tools/holoverse_fauna_resource_scan.py D:/Backups/Models D:/Apps/GLITCHED_MATRIX/assets --output-dir reports/fauna_scan
```

Scanned extensions:

```text
.glb .gltf .fbx .obj .dae .blend .bam .egg
```

The scan writes:

```text
reports/fauna_scan/fauna_resource_scan.json
reports/fauna_scan/fauna_resource_scan.md
```

The scanner reports likely fauna score, region hints, glTF animation/skin counts when available, nearby README/LICENSE signals, and known GitHub reference candidates. Local candidates are still not approved until visual proof and license review are done.

## Asset Knowledge Base builder

Pass 21 adds a metadata-first knowledge base builder for Codex/GPTOOL. It does not copy model geometry by default. It builds structured JSON that Codex can use to understand candidate animals, people, structures, and objects.

Build from curated defaults only:

```bash
python tools/holoverse_asset_kb_builder.py --output-dir data/asset_kb
```

Build from one or more scan reports:

```bash
python tools/holoverse_asset_kb_builder.py reports/fauna_scan/fauna_resource_scan.json --output-dir data/asset_kb
```

It writes:

```text
data/asset_kb/assets.json
data/asset_kb/licenses.json
data/asset_kb/rig_profiles.json
data/asset_kb/animation_profiles.json
data/asset_kb/holoverse_region_fit.json
data/asset_kb/codex_training_manifest.json
data/asset_kb/holoverse_asset_kb.json
data/asset_kb/README.md
```

Codex rule: use the KB to choose candidates, write import plans, and build procedural equivalents. Do not copy or promote assets without license/proof gates.

## Known external reference target

The first reference target is `KhronosGroup/glTF-Sample-Models/2.0/Fox`, because it is a low-poly animated fox with Survey, Walk, and Run cycles. The model body is listed as CC0, while the rigging/animation is CC-BY 4.0, so attribution must be preserved before promotion.

The curated default KB also includes reference entries for Cesium Man, Rigged Simple, Sponza, Virtual City, Barramundi Fish, Duck, and Box Textured so Codex can reason about people, structures, objects, and water creatures.

## Generated preview contents

```text
main.py
settings/fauna_preview_settings.json
assets/fauna/fauna_manifest.json
README.md
VALIDATION_COMMANDS.txt
reports/preview_generation_result.json
screenshots/
reports/
logs/
```

## Candidate fauna set

- Green Hills / Nyx: Ridgeback Grazer
- Forests / Vanta: Moss Stag
- Mushroom / Solace: Glowback
- Desert / Ember: Sandrunner
- Ice / Mirror: Crystal Fox
- Urban / Sable: Ash Raven
- Water / Solace: Reef Glider
- Metropolis / Archivist: Sky Moth

## Validation

Settings-only check, works without Panda3D:

```bash
python main.py --settings-check
```

Visual proof when Panda3D is installed:

```bash
python main.py --screenshot-mode --screenshot-path screenshots/fauna_preview.png --proof-path reports/fauna_preview_scene_proof.json
```

## Demo sheet fallback

Pass 19 adds a dependency-free SVG demo sheet so the fauna direction can be shown even before a real Panda3D render is available.

```bash
python tools/holoverse_fauna_demo_sheet.py ./previews/holoverse_fauna_pass17
```

This writes:

```text
reports/fauna_demo_sheet.svg
reports/fauna_demo_sheet_result.json
```

The SVG sheet is only a visual fallback. Panda3D screenshot proof is still required before promotion into HoloVerse.

## Promotion gate

Pass 18 adds a separate promotion gate. It reads a preview manifest, writes a promotion plan, and only writes an approved target manifest when `--apply` is passed.

Dry-run plan, selects nothing:

```bash
python tools/holoverse_fauna_promote.py ./previews/holoverse_fauna_pass17
```

Approve every species into a preview-local approved manifest:

```bash
python tools/holoverse_fauna_promote.py ./previews/holoverse_fauna_pass17 --approve all --apply
```

Approve only selected species into a real HoloVerse fauna manifest:

```bash
python tools/holoverse_fauna_promote.py ./previews/holoverse_fauna_pass17 --approve hill_ridgeback_grazer,forest_vanta_moss_stag --target-manifest ../GX-Prototype-Lab/data/HoloVerse/assets/fauna/fauna_manifest.json --apply
```

Require screenshot/scene proof before promotion:

```bash
python tools/holoverse_fauna_promote.py ./previews/holoverse_fauna_pass17 --approve all --require-proof --apply
```

Promotion writes:

```text
reports/fauna_promotion_plan.json
reports/fauna_promotion_plan.md
```

If `--target-manifest` is not supplied, the approved manifest is written inside the preview reports folder, not into HoloVerse.

## Safety rules

- The generated preview is disposable until approved.
- The preview generator does not modify main HoloVerse files.
- The resource scanner does not import or promote assets automatically.
- The Asset KB builder does not copy geometry by default.
- The demo sheet does not count as Panda3D render proof.
- The promotion gate is dry-run by default.
- `--apply` is required before any target manifest is written.
- Main HoloVerse protected routes remain: Urban/Sable, Metropolis/Archivist, points UI, ESC exit, and screenshots.
- Do not copy an entire preview folder into HoloVerse.
- Promote only approved species definitions, mesh ideas, animation ideas, or region decorator rules after screenshot review.

## Next upgrade

Wire these into `bridge.py` as first-class commands named `fauna-preview`, `fauna-demo-sheet`, `fauna-resource-scan`, `asset-kb-build`, and `promote-fauna-preview`, then add a controlled import pass for the Khronos Fox and any valid local backup-folder candidates.
