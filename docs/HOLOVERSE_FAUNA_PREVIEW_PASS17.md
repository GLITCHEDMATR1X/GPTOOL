# HoloVerse Fauna Preview Workflow — Pass 17/18/19

This workflow improves HoloVerse fauna with an assets-first loop instead of vibe-coding directly into the main world.

## Goal

Create isolated Panda3D preview scenes for creature silhouettes, region identity, color accents, and simple idle motion before any fauna is promoted into the real HoloVerse project.

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
- The demo sheet does not count as Panda3D render proof.
- The promotion gate is dry-run by default.
- `--apply` is required before any target manifest is written.
- Main HoloVerse protected routes remain: Urban/Sable, Metropolis/Archivist, points UI, ESC exit, and screenshots.
- Do not copy an entire preview folder into HoloVerse.
- Promote only approved species definitions, mesh ideas, animation ideas, or region decorator rules after screenshot review.

## Next upgrade

Wire these into `bridge.py` as first-class commands named `fauna-preview`, `fauna-demo-sheet`, and `promote-fauna-preview`, then add regression checks against the real HoloVerse project before promotion can write into a main project path.
