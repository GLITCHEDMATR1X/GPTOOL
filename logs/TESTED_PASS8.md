# Tested Pass 8

Date: 2026-04-30

## Commands Run

```bash
python -m py_compile bridge.py game_builder\human_asset_importer.py game_builder\template_generator.py
python bridge.py scan-human-assets "D:\Apps\BACKUP" --prefer female woman girl survivor --min-score 70 --json
python bridge.py generate-game examples\female_human_openworld_smoke --profile panda3d --command "make a 16:9 gray third person open world test editor for female rigged human meshes" --force
python bridge.py import-human-assets examples\female_human_openworld_smoke --search-root "D:\Apps\BACKUP" --require female --prefer female woman girl survivor --rigged-only --limit 6 --animation-limit 8 --export-formats glb obj fbx --clean --force
python examples\female_human_openworld_smoke\main.py --settings-check
python -m py_compile examples\female_human_openworld_smoke\main.py
python bridge.py panda3d-smoke examples\female_human_openworld_smoke --runtime system --entry main.py --require-screenshot --screenshot-path screenshots\female_openworld_pass8.png --timeout 30 --frames 8
python bridge.py full-pass examples\female_human_openworld_smoke --profile panda3d --runtime system --smoke --entry main.py --require-screenshot --screenshot-path screenshots\female_openworld_fullpass_pass8.png --timeout 30 --frames 8
```

## Results

- Female-focused scan found rigged female source candidates without importing prior GPTOOL example output.
- Clean import produced only:
  - `models/female_survivor_1.glb`
  - `models/female_survivor_2.glb`
  - `animations/fidle.fbx`
  - GLB and OBJ exports for both female survivor meshes
  - `human_manifest.json`
- Import report: 2 base assets, 1 animation source, 4 successful exports, 2 expected FBX skips.
- Runtime smoke passed with screenshot proof at `examples/female_human_openworld_smoke/screenshots/female_openworld_pass8.png`.
- Full pass delivery was allowed with all enabled validations passing.
