# Tested Pass 7

Date: 2026-04-30

## Commands Run

```bash
python -m py_compile bridge.py game_builder\human_asset_importer.py game_builder\template_generator.py
python bridge.py generate-game examples\human_import_smoke --profile panda3d --command "make a 16:9 gray studio editor for rigged human survivor meshes with export options" --force
python bridge.py import-human-assets examples\human_import_smoke --search-root "D:\Apps\BACKUP" --limit 8 --animation-limit 8 --export-formats glb obj fbx --force
python examples\human_import_smoke\main.py --settings-check
python -m py_compile examples\human_import_smoke\main.py
python bridge.py panda3d-smoke examples\human_import_smoke --runtime system --entry main.py --require-screenshot --screenshot-path screenshots\human_import_smoke_pass7_viewer.png --timeout 30 --frames 8
python bridge.py full-pass examples\human_import_smoke --profile panda3d --runtime system --smoke --entry main.py --require-screenshot --screenshot-path screenshots\human_import_fullpass_pass7.png --timeout 30 --frames 8
```

## Results

- Imported 8 rigged human base meshes:
  - `idle`
  - `female_survivor_1`
  - `female_survivor_2`
  - `male_survivor_1`
  - `male_survivor_2`
  - `fidle`
  - `midle`
  - `male_sitting_pose_converted`
- Imported 8 optional FBX animation clips.
- Export bundle wrote 16 successful exports: 8 rig-safe GLB copies and 8 static OBJ exports.
- FBX exports were correctly reported as skipped for GLB sources because GLB-to-FBX is not rig-safe in this Python pipeline.
- Panda3D smoke passed with screenshot proof:
  - `examples/human_import_smoke/screenshots/human_import_smoke_pass7_viewer.png`
  - `examples/human_import_smoke/screenshots/human_import_fullpass_pass7.png`
- Full pass delivery was allowed with all enabled validations passing.
