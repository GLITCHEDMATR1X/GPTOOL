# GPTOOL Pass 16 Tested

Local validation performed on 2026-05-01:

```bash
python -S -m py_compile bridge.py game_builder\human_asset_importer.py game_builder\template_generator.py validators\asset_validator.py
python -S bridge.py --version
python -S bridge.py scan-human-assets "D:\Apps\BACKUP" --min-score 65 --prefer female male survivor human character idle cranberry panda rig --rigged-only --json
python -S bridge.py generate-game ./GeneratedModelImportPass16 --profile panda3d --command "make a 16:9 gray rigged human model import test world with many local male and female meshes, stress proof, crash diagnostics, and points only" --force
python bridge.py import-human-assets .\GeneratedModelImportPass16 --search-root "D:\Apps\BACKUP" --prefer female male survivor human character idle cranberry panda rig --rigged-only --limit 10 --animation-limit 16 --export-formats glb obj fbx --clean --force --output .\GeneratedModelImportPass16\reports\human_asset_import_pass16.json
python -S .\GeneratedModelImportPass16\main.py --settings-check
python -S - <GeneratedModelImportPass16 main.py AST syntax check>
python .\GeneratedModelImportPass16\main.py --screenshot-mode --route-proof --stress-proof --window-type default --screenshot-path GeneratedModelImportPass16\screenshots\pass16_import_stress_default.png --proof-path GeneratedModelImportPass16\reports\pass16_import_stress_default.json
python -S validators\asset_validator.py .\GeneratedModelImportPass16 --json
python bridge.py full-pass .\GeneratedModelImportPass16 --profile panda3d --runtime system --smoke --entry main.py --require-screenshot --require-proof --screenshot-path screenshots\pass16_fullpass.png --proof-path reports\pass16_fullpass.json --timeout 30 --frames 8 --window-type default
python -S bridge.py package-audit . --json
```

Results:

- Version reports `GPT Game Generation Bridge 0.6.6-pass16`.
- Broad scan found 19 rigged candidates at score 65+ without listing GPTOOL generated proof folders.
- Import copied 10 rigged GLB base assets and 12 FBX animation clips.
- Export summary: 20 OK, 10 expected FBX writer skips.
- GLB exports are rig-safe copies; OBJ exports are static geometry; FBX export remains copy-through only for source FBX assets.
- Generated model import project settings and AST checks passed.
- Stress proof wrote `gptool_simulation_proof.v2`, screenshot proof, and no crash log.
- Both playable simulation characters reported `actor_loaded=True`.
- Full pass delivery was allowed. Remaining limitations were `text_fit_static: warn` and `regression_diff: skipped`.
- Generated proof artifacts and caches were removed before commit.
- Final package audit passed with zero removable cleanup candidates.
