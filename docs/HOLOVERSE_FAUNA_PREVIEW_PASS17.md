# HoloVerse Fauna Preview Workflow — Pass 17

This pass adds an assets-first workflow for improving HoloVerse fauna without vibe-coding directly into the main world.

## Goal

Create isolated Panda3D preview scenes for creature silhouettes, region identity, color accents, and simple idle motion before any fauna is promoted into the real HoloVerse project.

## New tool

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

## Safety rules

- The generated preview is disposable until approved.
- The preview generator does not modify main HoloVerse files.
- Main HoloVerse protected routes remain: Urban/Sable, Metropolis/Archivist, points UI, ESC exit, and screenshots.
- Do not copy an entire preview folder into HoloVerse.
- Promote only approved species definitions, mesh ideas, animation ideas, or region decorator rules after screenshot review.

## Next upgrade

Wire this into `bridge.py` as a first-class command named `fauna-preview`, then add a later `promote-fauna-preview` pass that copies only approved manifest entries into the HoloVerse asset database after regression checks.
