# Pass 3 — Portable Runtime Provider

## Purpose
Let the GPT Game Generation Bridge run Panda3D smoke/screenshot checks without reinstalling Panda3D for every project.

## Runtime providers

```text
auto            Prefer packaged EXE, then portable Python, then system Python, then mock display.
system_python   Use the Python interpreter running bridge.py.
portable_python Use a sidecar Python runtime with Panda3D already installed.
packaged_exe    Run the built game executable directly.
mock_display    Run non-render/static checks only; visual proof remains unverified.
```

## Main commands

Resolve the runtime the bridge would use:

```bash
python bridge.py panda3d-runtimes . --runtime auto
```

Use a sidecar runtime:

```bash
python bridge.py full-pass . --profile panda3d --runtime portable --runtime-path runtimes/panda3d_py313 --smoke --entry main.py --require-screenshot
```

Test the player-visible packaged build:

```bash
python bridge.py panda3d-smoke . --runtime packaged-exe --exe dist/HoloVerse.exe --require-screenshot
```

Fallback to honest non-render checks:

```bash
python bridge.py full-pass . --profile panda3d --runtime mock --smoke
```

## Screenshot rule
Mock display mode must never claim visual proof. If `--require-screenshot` is used with mock mode, the pass blocks delivery even if a stale screenshot file exists.

## Recommended AI behavior
- Use `packaged_exe` for final/Steam-build proof when an EXE exists.
- Use `portable_python` for source-project iteration when a sidecar runtime exists.
- Use `system_python` only when the user's active Python is known to have Panda3D.
- Use `mock_display` only to keep static checks moving while clearly marking visual proof as unverified.
