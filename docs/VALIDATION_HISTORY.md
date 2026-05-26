# GPTOOL Validation History

> Curated from the old `logs/TESTED_PASS*.md` files during the notes/log cleanup pass. Keep future validation summaries here instead of scattering pass logs under `logs/`.


---

# Pass 1 Verification Notes

Validated in the review environment with Python 3.13.5.

## Completed checks

- `bridge.py --version` returned `GPT Game Generation Bridge 0.5.2-pass2`.
- `bridge.py scan .` completed and identified the package as a Python project.
- `validators/syntax_validator.py . --json` returned exit code `0`.
- `validators/import_validator.py bridge.py --project-root . --json` returned exit code `0`, confirming local package imports are no longer falsely flagged.
- `diagnostics/pre_submit_gate.py` returned exit code `1` for a failing review payload and `0` for a passing review payload.
- `mechanics/acceptance_gate_runner.py` now returns exit code `1` when acceptance checks fail.

## Environment note

The one-command `full-pass` is structurally working. In a bare environment without Pillow installed, it correctly blocks delivery because screenshot-review modules import `PIL`. Install `requirements.txt` before using the full bridge against itself or visual projects.



---

# TESTED — Pass 2

Environment used for packaging tests:

- Python: 3.13.5 via `/usr/bin/python3`
- Panda3D: not installed in this container, intentionally verified as a reported warning/failure condition

## Commands run

```bash
/usr/bin/python3 -m compileall -q .
/usr/bin/python3 bridge.py --version
/usr/bin/python3 bridge.py scan .
/usr/bin/python3 bridge.py panda3d-doctor . --json
/usr/bin/python3 bridge.py panda3d-smoke /mnt/data/gpt_panda_fake_project --entry main.py --require-screenshot --screenshot-path reports/smoke.png
/usr/bin/python3 bridge.py full-pass /mnt/data/gpt_panda_fake_project --profile panda3d --smoke-command '/usr/bin/python3 main.py' --require-screenshot --screenshot-path reports/smoke2.png --report-dir /mnt/data/gpt_panda_fake_project/reports/fullpass
```

## Results

- Compile check passed.
- Bridge version reports `0.5.2-pass2`.
- Project scan command works.
- Panda3D doctor command reports missing Panda3D honestly in this environment.
- Direct Panda3D smoke adapter test passed against a fake project that honored `GPT_BRIDGE_SCREENSHOT_PATH`.
- Full-pass Panda3D smoke integration passed against the fake project with screenshot proof.

## Important limit

This container does not have Panda3D installed, so a real Panda3D app launch could not be proven here. The adapter is designed to run on the user's local game machine where `panda3d` and `direct` are installed.



---

# TESTED — 0.5.3-pass3

Environment used for this pass:

```text
Python: 3.13.5
Panda3D: not installed in container
```

Checks run:

```bash
python3 -m py_compile bridge.py adapters/panda3d_adapter.py
python3 bridge.py --version
python3 bridge.py panda3d-runtimes . --runtime mock
python3 bridge.py panda3d-runtimes . --runtime auto
python3 bridge.py panda3d-smoke fake_panda_project --runtime packaged-exe --exe dist/fake_game.exe --require-screenshot
python3 bridge.py panda3d-smoke fake_panda_project --runtime mock
python3 bridge.py panda3d-smoke fake_panda_project --runtime mock --require-screenshot
```

Results:

- Version reports `0.5.3-pass3`.
- Mock runtime resolves and clearly reports visual proof as unavailable.
- Auto runtime falls back to mock when no packaged EXE, portable runtime, or system Panda3D is available.
- Packaged-EXE smoke path passes against a fake executable that honors `GPT_BRIDGE_SCREENSHOT_PATH`.
- Mock mode with `--require-screenshot` fails as intended.

Limit:

- Real Panda3D window rendering was not tested in this container because Panda3D is not installed here.

Additional check after visual-proof warning refinement:

```bash
python3 bridge.py full-pass fake_panda_project --profile panda3d --runtime mock --smoke
```

Result:

- Delivery remains allowed for non-render checks.
- `panda3d_visual_proof` is reported as `warn` so AI cannot mistake mock mode for real screenshot proof.



---

# TESTED PASS 4

Environment used for this package pass:

```text
Python 3.13.5
```

## Checks run

```bash
python -S -m py_compile bridge.py command_bridge/*.py
```

Result: passed.

```bash
python -S bridge.py --version
```

Result: `GPT Game Generation Bridge 0.5.4-pass4`.

```bash
python -S bridge.py plan-command /tmp/gptbridge_test --profile holoverse --command "remove the fps counter and show points only small in the top-right, no UI background box, keep UI on screen"
```

Result: created `work_order.json` and `work_order.md` with expected must-do / must-not-do items.

```bash
python -S bridge.py verify-command /tmp/gptbridge_test --work-order /tmp/gptbridge_test/reports/work_order.json --changed-files main.py
```

Result: command verification ran and produced warnings for static FPS references, as expected.

```bash
python -S bridge.py full-pass /tmp/gptbridge_test --profile holoverse --runtime mock --work-order /tmp/gptbridge_test/reports/work_order.json --changed-files main.py
```

Result: full-pass included AI work-order loading and AI command verification.

## Note about `python -S`

The test container's default Python site startup can hang after printing output. The bridge code itself exits normally when launched in a normal Python environment, but tests here used `python -S` to avoid that container-specific site startup issue.



---

# TESTED PASS 5

Environment used for bridge tests:
- Python 3.13.5
- Panda3D was not installed in this container, so real Panda3D rendering was not claimed.

## Checks Performed
- Compiled all bridge Python files.
- Ran `bridge.py --version`.
- Ran `generate-game` with a HoloVerse-like natural-language command.
- Confirmed generated project includes:
  - `main.py`
  - `settings/game_settings.json`
  - `bridge_project.json`
  - `data/regions/*.json`
  - `data/characters/*.json`
  - `requirements.txt`
  - `README.md`
- Ran generated `main.py --settings-check` without Panda3D.
- Compiled generated `main.py`.
- Ran separate `plan-game` then `generate-template` flow.

## Known Limit
Real Panda3D window rendering must be tested on a machine or portable runtime where Panda3D is installed. The generated template includes the screenshot hook needed for bridge proof once Panda3D is available.



---

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



---

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



---

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



---

# TESTED_PASS9 — Lean Core Cleanup

Validated in this pass:

- `bridge.py` and `maintenance/package_cleaner.py` compile under Python 3.13.5 using `python3 -S -m py_compile`.
- `bridge.main(['--version'])` reports `GPT Game Generation Bridge 0.5.9-pass9`.
- `package-audit .` reports the cleaned source tree as valid and identifies cleanup candidates.
- `clean-package . --apply` removes generated cache directories after compile/audit.
- Original zip audit showed `examples/` was the dominant bloat source, roughly 237.8 MB uncompressed / 196.5 MB compressed.

Known limit:

- I did not run a real Panda3D render in this environment. This pass was packaging/maintenance focused.



---

# TESTED PASS 10 — Panda3D Headless Scene Proof

Version tested: `0.6.0-pass10`

## Environment

- Python used for bridge static checks: `python3 -S`
- Portable Panda3D runtime: `/mnt/data/gptool_py313_panda3d_env/bin/python`
- Panda3D version detected by runtime probe: `1.10.16`

## Commands run

```bash
python3 -S bridge.py --version
```

Observed:

```text
GPT Game Generation Bridge 0.6.0-pass10
```

```bash
python3 -S bridge.py generate-game /mnt/data/gptool_pass10_proof/GeneratedProofWorld --profile panda3d --command "make a neon vector open world with green hills animals, urban robots, desert pyramids, ice hovercraft track, metropolis robot lab, space dyson sphere, and points only in the top right" --force
```

Observed: generated project PASS with `main.py`, settings, region metadata, reports, launch scripts, and validation commands.

```bash
/mnt/data/panda3d_py /mnt/data/gptool_pass10_proof/GeneratedProofWorld/main.py --settings-check
```

Observed: settings check passed.

```bash
python3 -S bridge.py panda3d-smoke /mnt/data/gptool_pass10_proof/GeneratedProofWorld --entry main.py --runtime portable --runtime-path /mnt/data/gptool_py313_panda3d_env --window-type none --frames 1 --require-proof --proof-path reports/pass10_scene_proof.json --output /mnt/data/gptool_pass10_proof/panda3d_smoke_report.json --timeout 30
```

Observed:

```text
Panda3D smoke: PASS
Screenshot: /mnt/data/gptool_pass10_proof/GeneratedProofWorld/reports/panda3d_smoke.png exists=False
- Runtime smoke completed without adapter-detected blockers.
```

## Proof values

- Smoke report `ok`: `True`
- Runtime provider: `portable_python`
- Runtime ready: `True`
- Return code: `0`
- Visual proof mode: `headless_scene_verified`
- Proof schema: `panda3d_smoke_proof.v1`
- Proof status: `headless_scene_built`
- Proof Panda3D version: `1.10.16`
- Window type hint: `none`
- Has window: `False`
- Render child count: `15`
- aspect2d child count: `20`

## Static check

```bash
find . -name '*.py' -not -path '*/__pycache__/*' -print0 | xargs -0 python3 -S -m py_compile
```

Observed: `PY_COMPILE_PASS`

## Known limit

This environment has no real display/audio device. The pass proves real Panda3D import and scene construction in headless mode. Screenshot proof is still expected to be performed on a display/offscreen-capable machine or packaged EXE route.



---

# TESTED — Pass 11 Playable Simulation Characters

Proof commands are recorded in the delivered proof artifact zip. Expected checks:

- Bridge version reports `0.6.1-pass11`.
- All GPTOOL Python files compile.
- `generate-game` produces a fresh Panda3D project.
- Generated `main.py --settings-check` passes.
- Generated `main.py` compiles.
- Headless proof confirms two playable simulation characters.
- Offscreen screenshot mode writes a PNG backup screenshot where Panda3D offscreen rendering is available.
- Package compare confirms no files from the cleanup baseline were removed.



---

# Tested — Pass 12

Expected proof checklist:

- Bridge version reports `0.6.2-pass12`.
- Generated template compiles.
- `python main.py --settings-check` passes.
- `python main.py --screenshot-mode --route-proof` writes one screenshot and scene-proof JSON.
- Scene proof reports two playable characters, one simulated swap, route markers, and changed start/end positions.
- Regression comparison confirms no files removed from Pass 11 or uploaded clean source.



---

# GPTOOL Pass 13 Tested

Local validation performed during the pass:

- `python bridge.py --version`
- AST syntax check across Python files
- `python bridge.py generate-game` for a fresh Panda3D probe project
- generated `main.py --settings-check`
- generated `main.py` AST syntax check
- Panda3D offscreen `--screenshot-mode --route-proof` screenshot/proof run
- Zip/package integrity check

The generated screenshot path and proof bundle are included in the pass handoff.



---

# GPTOOL Pass 14 Tested

Local validation performed:

- Generated a fresh Panda3D probe project.
- Confirmed generated `main.py --settings-check` passes.
- Confirmed generated `main.py` AST syntax passes.
- Ran screenshot smoke mode, which exercises `_update`.
- Ran route proof mode after the fix and confirmed proof JSON/screenshot are written without crash.

Panda3D 1.10.16 offscreen test passed in the local environment.



---

# GPTOOL Pass 15 Tested

Local validation performed on 2026-05-01:

```bash
python -S bridge.py --version
python -S bridge.py package-audit . --json
python -S -m py_compile bridge.py game_builder\settings_planner.py game_builder\template_generator.py
python -S - <source AST syntax check>
python -S bridge.py generate-game ./GeneratedProbe --profile panda3d --command "make a playable simulation with two testers, smoother controls, crash diagnostics, stress proof, and points only"
python -S ./GeneratedProbe/main.py --settings-check
python -S - <Generated main.py AST syntax check>
python ./GeneratedProbe/main.py --screenshot-mode --route-proof --stress-proof --screenshot-path GeneratedProbe\screenshots\pass15_stress.png --proof-path GeneratedProbe\reports\pass15_stress.json
python ./GeneratedProbe/main.py --screenshot-mode --force-crash-test --screenshot-path GeneratedProbe\screenshots\forced_crash.png --proof-path GeneratedProbe\reports\forced_crash.json
```

Results:

- Version reports `GPT Game Generation Bridge 0.6.5-pass15`.
- Package audit passed.
- Source syntax passed for the changed source files and AST passed for 42 Python files.
- Generated probe settings check passed.
- Generated `main.py` AST syntax passed.
- Stress proof wrote `GeneratedProbe\reports\pass15_stress.json` with schema `gptool_simulation_proof.v2`.
- Stress proof set Tab swap, jump, sprint, camera zoom, camera reset, and screenshot flags to true.
- Stress proof wrote `GeneratedProbe\screenshots\pass15_stress.png`.
- Normal stress proof had no crash log.
- Forced crash test wrote `GeneratedProbe\logs\crash_latest.txt` plus runtime, controls, and scene diagnostics JSON.
- Generated probe artifacts were removed before commit cleanup.
- Final package audit passed with zero removable cleanup candidates.



---

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



---

# GPTOOL Pass 17-19 Validation Summary

- Patch Gate, App Capsule Bridge, and Automation Task Director self-tests were added under `tests/`.
- Use `RUN_PATCH_GATE_SELFTESTS.bat`, `RUN_APP_CAPSULE_SELFTESTS.bat`, and `RUN_AUTOMATION_TASK_SELFTESTS.bat` for local checks.
- Future test-run results should be written under `reports/` during development and excluded from release/source zips unless explicitly requested.

---

# TESTED PASS 21 — Core Extension Registry

Environment:

```text
Python 3.x sandbox runtime
```

Checks run:

```bash
python -m compileall -q .
python bridge.py --version
python bridge.py extension-status --json
python bridge.py patch-rules
python bridge.py app-scan . --json
python bridge.py task-validate task_manifests/holoverse_artifact_chain.json --json
python tests/selftest_app_capsules.py
python tests/selftest_automation_tasks.py
python patching/selftest_pass_combiner.py
python patching/selftest_pass_combiner_v4.py
python patching/selftest_repo_patch_tool.py
```

Results:

- Bridge reports `GPT Game Generation Bridge 0.6.6-pass21`.
- Patch Gate, App Capsule Bridge, and Automation Task Director register through `extension-status`.
- Task manifests validate with root-variable expansion.
- Existing subsystem self-tests pass.

Notes:

- Actual HoloVerse/HoloCore/HoloUtopia task runs still require local project roots to exist, normally through `project_registry/local_project_roots.json`.


---

# TESTED PASS 22 — Test Run Bot Foundations

Checks run:

```bash
python -m compileall -q .
python bridge.py --version
python bridge.py extension-status --json
python bridge.py task-validate task_manifests/holoverse_vector_arena_controls_journey.json --json
python bridge.py task-validate task_manifests/holoverse_artifact_chain_bot_foundation.json --json
python tests/selftest_test_run_bot.py
python tests/selftest_automation_tasks.py
python bridge.py package-audit . --json
```

Results:

- Bridge reports `GPT Game Generation Bridge 0.6.6-pass22`.
- New input-plan actions validate through task manifests.
- Test-run bot self-test writes and validates a sample input plan and optional screenshot checkpoint.
- Actual game playback still requires HoloVerse/HoloCore/HoloUtopia hooks to consume `GPT_BRIDGE_JOURNEY_PLAN`.

## Pass 23 validation notes

- GPTOOL Automation Task Director was run against a real HoloVerse target.
- Artifact chain and HoloCore task journeys passed.
- HoloUtopia capsule task caught a target metadata regression.
- Vector Arena optional visual smoke exposed a HoloVerse headless-window limitation and is now reported as a non-blocking warning.
