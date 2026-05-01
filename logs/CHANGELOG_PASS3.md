# CHANGELOG — 0.5.3-pass3

## Added
- Runtime provider resolver for Panda3D testing.
- `bridge.py panda3d-runtimes` command.
- `--runtime` selector for Panda3D smoke/full-pass commands.
- `--runtime-path` for sidecar/portable Python runtimes.
- `--exe` for packaged executable smoke tests.
- Auto provider order: packaged EXE, portable Python, system Python, mock display.
- Honest `mock_display` fallback for non-render checks when Panda3D is unavailable.
- Runtime docs and placeholder `runtimes/panda3d_py313/` folder.

## Changed
- Panda3D full-pass now reports `panda3d_runtime_provider` separately from import dependency probing.
- Packaged EXE mode skips bridge-Python Panda3D import requirements.
- Smoke environment now sets `GPT_BRIDGE_RUNTIME_PROVIDER` and adds the bridge root to `PYTHONPATH` so projects can import the included smoke hook.

## Safety rule
Mock mode cannot satisfy required visual proof. If `--require-screenshot` is supplied, delivery stays blocked until a real runtime or packaged EXE produces screenshot proof.
