# GPT Game Generation Bridge v0.6.6-pass16

Private AI-facing validation harness for more disciplined game and app generation.

This lean Pass 9 bundle removes heavyweight generated proof worlds from the core zip and adds maintenance commands to audit and prevent package bloat.

This release keeps the one-command workflow and adds a Panda3D runtime provider layer so AI agents can test games through the best available display path without reinstalling Panda3D for every project.

## What it does now

- Scans project trees.
- Validates Python syntax across files or folders.
- Validates imports with local project-package awareness.
- Scans discoverable Python asset references.
- Runs heuristic UI bounds checks.
- Runs heuristic text-fit checks.
- Compares candidate/current folders against a baseline.
- Produces machine-readable JSON and human-readable Markdown reports.
- Returns nonzero exit codes when critical gates fail.
- Runs Panda3D smoke checks through selectable runtime providers.
- Falls back honestly to mock display mode when no real renderer is available.
- Scans/imports rigged human mesh candidates from the surrounding asset library.
- Generated Panda3D templates can load imported human Actor assets from `assets/characters/humans/human_manifest.json`.
- Human preview templates open as a 16:9 gray studio viewer with mesh and animation cycling.
- Imported human assets can write export bundles for GLB, OBJ, and FBX copy-through where supported.
- Human import supports `--prefer`, `--require`, `--rigged-only`, and `--clean` for targeted, uncluttered builds.
- Generated human projects now include camera-relative third-person movement and a streaming procedural gray grid for open-world traversal tests.
- Audits GPTOOL bundle size and identifies safe cleanup candidates before packaging.
- Builds lean source zips without optional examples, caches, build output, or old generated run reports.

## Main command

```bash
python bridge.py full-pass /path/to/project --profile panda3d --runtime auto --smoke --require-screenshot
```

The command writes:

```text
reports/latest_report.json
reports/latest_report.md
```

## Panda3D runtime providers

```text
auto            Prefer packaged EXE, then portable Python, then system Python, then mock display.
system_python   Use the Python interpreter running bridge.py.
portable_python Use a sidecar Python runtime with Panda3D already installed.
packaged_exe    Run the built game executable directly.
mock_display    Run non-render/static checks only; visual proof remains unverified.
```

Useful runtime commands:

```bash
python bridge.py panda3d-runtimes . --runtime auto
python bridge.py panda3d-smoke . --runtime portable --runtime-path runtimes/panda3d_py313 --entry main.py --require-screenshot
python bridge.py panda3d-smoke . --runtime packaged-exe --exe dist/HoloVerse.exe --require-screenshot
python bridge.py full-pass . --profile panda3d --runtime mock --smoke
```

## Portable runtime setup

The bridge does not ship Panda3D binaries. Put a reusable runtime here or point to one:

```text
runtimes/panda3d_py313/python.exe
runtimes/panda3d_py313/Scripts/python.exe
runtimes/panda3d_py313/bin/python
```

Then run:

```bash
python bridge.py full-pass . --profile panda3d --runtime portable --runtime-path runtimes/panda3d_py313 --smoke --entry main.py --require-screenshot
```

You can also set:

```text
GPT_BRIDGE_PANDA3D_PYTHON=C:\Tools\panda3d_py313\python.exe
GPT_BRIDGE_PANDA3D_RUNTIME=C:\Tools\panda3d_py313
GPT_BRIDGE_PACKAGED_EXE=dist\HoloVerse.exe
```

## General commands

```bash
python bridge.py --version
python bridge.py package-audit .
python bridge.py clean-package .
python bridge.py package-lean-zip GPTOOL_lean.zip
python bridge.py scan /path/to/project
python bridge.py validate /path/to/project --profile generic_python
python bridge.py full-pass /path/to/project --profile panda3d
python bridge.py regression /path/to/candidate /path/to/baseline
python bridge.py report reports/latest_report.json
python bridge.py scan-human-assets ..
python bridge.py import-human-assets /path/to/generated_project --search-root .. --prefer female survivor --require female --rigged-only --clean --limit 8 --export-formats glb obj fbx
```

## Install

```bash
python -m pip install -r requirements.txt
```

Core screenshot-review features need `numpy` and `Pillow`.

For source-level Panda3D rendering, use either your system Panda3D install or a sidecar runtime. For final builds, prefer packaged EXE mode.

## Specialist tools still included

```bash
python diagnostics/env_probe.py --json
python scanners/project_scanner.py /path/to/project --json
python validators/syntax_validator.py /path/to/project --json
python validators/import_validator.py /path/to/project --project-root /path/to/project --json
python validators/asset_validator.py /path/to/project --json
python validators/ui_bounds_validator.py /path/to/main.py --json
python validators/text_fit_validator.py /path/to/main.py --json
python diagnostics/regression_checker.py /path/to/current /path/to/baseline --json
python reviewers/screenshot_reviewer.py --image path/to/image.png --layout-profile gameplay --output logs/screenshot_review.json
python diagnostics/pre_submit_gate.py --review logs/screenshot_review.json --output logs/pre_submit_gate.json
```

## Screenshot hook

Screenshot proof is strongest when the target Panda3D app installs the included hook after ShowBase creation:

```python
from runtime_hooks.panda3d_smoke_hook import install_from_env
install_from_env(base)
```

The hook only activates when the bridge sets `GPT_BRIDGE_SMOKE=1`.

## Current limits

- Asset validation is still static and mainly string-discoverable.
- UI bounds and text-fit checks are conservative static heuristics, not rendered measurements.
- Mock display mode is not visual proof.
- Imported FBX clips are optional runtime sources and only animate when their skeleton matches the selected Actor mesh.
- Real route-specific gameplay checks still need project-specific hooks/work orders.

## AI command accuracy workflow

Pass 4 adds an AI-facing work-order layer. Use it before asking an AI agent to edit a game project.

```bash
python bridge.py plan-command . --profile holoverse --command "remove the fps counter and show only points in the top-right"
```

Then run validation against that exact command:

```bash
python bridge.py full-pass . --profile holoverse --work-order reports/work_order.json --runtime auto --smoke --require-screenshot
```

The work order is written to `reports/work_order.json` and `reports/work_order.md`.


## Pass 5 — Command > Settings > Generate

The bridge can now generate a Panda3D-ready starter template from a natural-language game request.

```bash
python bridge.py generate-game ./GeneratedGame --profile panda3d --command "make a neon vector open world with urban robots"
```

Editable settings only:

```bash
python bridge.py plan-game . --profile panda3d --command "make a desert robot arena"
```

Generate from settings:

```bash
python bridge.py generate-template ./GeneratedGame --settings reports/game_settings.json
```

Import local rigged human meshes after generation:

```bash
python bridge.py import-human-assets ./GeneratedGame --search-root .. --prefer female survivor --require female --rigged-only --clean --limit 4
```

The importer prefers unique GLB/GLTF files with detected skin data, copies optional FBX animation clips, writes `assets/characters/humans/human_manifest.json`, and updates `settings/game_settings.json` when present. At runtime, generated templates try Panda3D `Actor` first and fall back to static `loadModel` if the active runtime cannot bind the asset.

Preview controls in generated human projects:

```text
WASD   camera-relative third-person movement
Q/E    rotate third-person camera
Shift  sprint
[ / ]  cycle imported human meshes
Tab    swap active simulation character (male/female)
C      cycle embedded Actor animations when exposed by the rig
Esc    exit
```

The gray platform streams in procedural chunks around the controlled player, so movement can continue outward for open-world testing without a fixed floor edge.

Exports are written under `assets/characters/humans/exports/`. GLB copies from rigged GLB sources preserve the rig. OBJ exports are static geometry. FBX export is copy-through only when the imported source is already FBX; GLB-to-FBX writing is reported as skipped because this Python pipeline does not have a rig-safe FBX writer.

## Pass 9 — Lean package maintenance

The previous core zip was huge because generated example worlds and copied human asset proof folders were bundled with the tool itself. Those are useful as evidence, but they are not required for the bridge to run.

Use these commands before handing the tool to another agent or packaging it for backup:

```bash
python bridge.py package-audit .
python bridge.py clean-package .
python bridge.py clean-package . --apply
python bridge.py package-lean-zip ../GPT_Tool_pass9_lean.zip
```

Cleanup rules are conservative:

- `examples/` is treated as optional proof/demo output by default.
- `__pycache__`, `.pytest_cache`, build output, and OS cache files are removed.
- Generated JSON/TXT/log run artifacts are removed while changelog and tested notes are kept.
- Core source, docs, profiles, validators, runtime hooks, and samples are preserved.

If a pass intentionally needs example projects inside the zip, use `--include-examples`.


## Pass 10 Panda3D headless proof

Use this when the machine has Panda3D installed but no display is available:

```bash
python bridge.py panda3d-smoke ./GeneratedGame --entry main.py --runtime portable --runtime-path /path/to/panda3d_runtime --window-type none --frames 1 --require-proof --proof-path reports/panda3d_scene_proof.json
```

This produces a `panda3d_smoke_proof.v1` JSON file. It proves scene construction, not screenshot framing.


## Pass 12 — Simulation route proof

Generated Panda3D templates now support a deterministic route-proof test for playable simulation mode.

```bash
python main.py --screenshot-mode --route-proof --screenshot-path screenshots/simulation_mode_backup.png --proof-path reports/simulation_mode_scene_proof.json
```

This automatically moves the male tester, simulates a Tab swap, moves the female tester, drops visible route markers, writes scene-proof JSON, and captures one backup screenshot.

## Pass 13 — Smoother playable controls

Generated Panda3D simulation templates now use a stronger third-person test controller:

```text
WASD / Arrow keys  smoothed movement
Shift              sprint
Space              jump with gravity return
Q/E or ←/→         rotate camera
Mouse wheel        zoom camera in/out
R                  reset camera
Tab                swap male/female tester
F12                backup screenshot
```

The generated proof JSON records the controller model, camera distance, active character, and playable character state so AI edits can be checked without relying only on visual inspection.

## Pass 14 — Local crash fix

Fixed a generated-template crash found during route-proof testing: proof JSON could read the player jump state before `jump_was_down` had been initialized. The generated player controller now initializes that state and proof reporting reads it safely.

Retest command:

```bash
python main.py --screenshot-mode --route-proof --screenshot-path screenshots/route.png --proof-path reports/route.json
```

## Pass 15 - Crash diagnostics and stress proof

Generated Panda3D templates now write crash and runtime diagnostics without hiding the original error:

```text
logs/crash_latest.txt
logs/runtime_latest.json
logs/last_controls_state.json
logs/last_scene_state.json
```

Use stress proof to exercise movement, sprint, jump, Tab swapping, camera zoom/reset, route markers, proof JSON, and screenshot capture in one deterministic desktop run:

```bash
python main.py --screenshot-mode --route-proof --stress-proof --screenshot-path screenshots/stress.png --proof-path reports/stress.json
```

The stress proof writes `gptool_simulation_proof.v2`. CI now includes a Panda3D generated-proof job that uploads the generated screenshot, proof JSON, and diagnostics artifacts.

## Pass 16 - Broader model import proof

Human asset scans now skip GPTOOL generated proof/output folders when scanning a broad backup root, so import tests do not re-ingest their own copied models or export bundles.

Generated playable simulation characters now try imported human Actor meshes from `assets/characters/humans/human_manifest.json` before falling back to procedural bodies. Scene proof JSON reports `actor_loaded` for each playable character.

The asset validator ignores known runtime-generated screenshot/proof/log outputs, avoiding false blockers for filenames produced by screenshot and diagnostics modes.

## Repository baseline

This tree is source-control-ready. Generated worlds, screenshots, release zips, local Panda3D runtimes, and build outputs are intentionally ignored. Use GitHub Releases for proof bundles and zipped pass deliveries. See `docs/REPOSITORY_SETUP.md` and `docs/GITHUB_RELEASE_GUIDE.md`.
