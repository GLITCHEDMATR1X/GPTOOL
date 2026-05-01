# RUN ME FIRST — GPT Game Generation Bridge

Pass 9 is a lean source bundle. Heavy generated example worlds are no longer shipped inside the core zip; generate fresh proof projects when needed.

This bundle is a validation and delivery-safety bridge for AI-assisted game/app projects.

## 1. Install core dependencies

```bash
python -m pip install -r requirements.txt
```

For Panda3D source-project rendering, either install Panda3D in your active Python or use a reusable sidecar runtime.

## 2. Run the one-command pass

From inside this folder:

```bash
python bridge.py full-pass . --profile generic_python
```

Against another project:

```bash
python bridge.py full-pass /path/to/project --profile panda3d
```

With runtime smoke and screenshot proof:

```bash
python bridge.py full-pass /path/to/project --profile panda3d --runtime auto --smoke --require-screenshot
```

With a baseline for regression checking:

```bash
python bridge.py full-pass /path/to/candidate --profile panda3d --baseline /path/to/baseline
```

## 3. Choose a Panda3D runtime provider

Check what the bridge will use:

```bash
python bridge.py panda3d-runtimes /path/to/project --runtime auto
```

Use a reusable sidecar runtime:

```bash
python bridge.py full-pass /path/to/project --profile panda3d --runtime portable --runtime-path runtimes/panda3d_py313 --smoke --entry main.py --require-screenshot
```

Test the packaged build directly:

```bash
python bridge.py panda3d-smoke /path/to/project --runtime packaged-exe --exe dist/HoloVerse.exe --require-screenshot
```

Use honest non-render fallback:

```bash
python bridge.py full-pass /path/to/project --profile panda3d --runtime mock --smoke
```

Generated project stress proof:

```bash
python main.py --screenshot-mode --route-proof --stress-proof --screenshot-path screenshots/stress.png --proof-path reports/stress.json
```

Generated templates also write crash diagnostics under `logs/crash_latest.txt`, `logs/runtime_latest.json`, `logs/last_controls_state.json`, and `logs/last_scene_state.json`.

Broader imported-model proof:

```bash
python bridge.py scan-human-assets .. --rigged-only --prefer female male survivor character idle
python bridge.py import-human-assets ./GeneratedModelImportPass16 --search-root .. --rigged-only --limit 10 --animation-limit 16 --export-formats glb obj fbx --clean --force
python ./GeneratedModelImportPass16/main.py --screenshot-mode --route-proof --stress-proof --window-type default --screenshot-path GeneratedModelImportPass16/screenshots/import_stress.png --proof-path GeneratedModelImportPass16/reports/import_stress.json
```

## 4. Read the report

The pass writes:

```text
reports/latest_report.json
reports/latest_report.md
```

The report ends with a delivery decision: allowed or blocked.

## 5. Important rule

Mock display mode is useful for static checks, but it is not visual proof. If screenshot proof matters, use system Python with Panda3D, a portable Panda3D runtime, or packaged EXE mode.

## Pass 4 AI command workflow

Create an AI work order from a plain game-development command:

```bash
python bridge.py plan-command . --profile holoverse --command "remove the fps counter and show only points in the top-right"
```

Run a full pass using that work order:

```bash
python bridge.py full-pass . --profile holoverse --work-order reports/work_order.json --runtime auto --smoke --require-screenshot
```

Verify only command accuracy and changed-file scope:

```bash
python bridge.py verify-command . --work-order reports/work_order.json --changed-files HoloVerse/world.py
```


## Generate a Panda3D-ready template

```bash
python bridge.py generate-game ./GeneratedGame --profile panda3d --command "make a neon vector open world with urban robots"
```

Then inside the generated folder:

```bash
python main.py --settings-check
python -m pip install -r requirements.txt
python main.py
```


## Pass 10 Panda3D headless proof

Use this when the machine has Panda3D installed but no display is available:

```bash
python bridge.py panda3d-smoke ./GeneratedGame --entry main.py --runtime portable --runtime-path /path/to/panda3d_runtime --window-type none --frames 1 --require-proof --proof-path reports/panda3d_scene_proof.json
```

This produces a `panda3d_smoke_proof.v1` JSON file. It proves scene construction, not screenshot framing.
