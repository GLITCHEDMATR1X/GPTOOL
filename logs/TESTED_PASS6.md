# Tested Pass 6

Date: 2026-04-30

## Commands Run

```bash
python -m py_compile bridge.py game_builder\human_asset_importer.py game_builder\template_generator.py game_builder\settings_planner.py
python bridge.py scan-human-assets "D:\Apps\BACKUP" --min-score 70 --output reports\human_asset_scan.json
python bridge.py generate-game examples\human_import_smoke --profile panda3d --command "make a human survivor test scene with rigged imported human meshes" --force
python bridge.py import-human-assets examples\human_import_smoke --search-root "D:\Apps\BACKUP" --limit 3 --animation-limit 6 --force
python examples\human_import_smoke\main.py --settings-check
python -m py_compile examples\human_import_smoke\main.py
python bridge.py panda3d-smoke examples\human_import_smoke --runtime system --entry main.py --require-screenshot --screenshot-path screenshots\human_import_smoke.png --timeout 30 --frames 8
python bridge.py full-pass examples\human_import_smoke --profile panda3d --runtime system --smoke --entry main.py --require-screenshot --screenshot-path screenshots\human_import_fullpass.png --timeout 30 --frames 8
```

## Results

- Human scan found 51 candidates at the tested threshold before the smoke project import, including 19 rigged GLB/GLTF candidates.
- The smoke project imported 3 base human assets and 6 optional FBX animation clips.
- Runtime smoke passed with screenshot proof at `examples/human_import_smoke/screenshots/human_import_smoke.png`.
- Full pass on the smoke project was allowed with all enabled validations passing.
