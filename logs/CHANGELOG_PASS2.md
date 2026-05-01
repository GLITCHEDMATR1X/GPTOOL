# CHANGELOG — Pass 2 Panda3D Runtime Adapter

## Added
- `adapters/panda3d_adapter.py` for Panda3D environment probing, entry discovery, smoke launch, screenshot verification, and fresh log collection.
- `runtime_hooks/panda3d_smoke_hook.py`, an optional frame-delayed screenshot/exit hook for Panda3D ShowBase apps.
- `bridge.py panda3d-doctor` command.
- `bridge.py panda3d-smoke` command.
- `--profile panda3d --smoke` integration for `validate` and `full-pass`.
- `docs/PANDA3D_RUNTIME_PASS.md`.
- `examples/panda3d_smoke_project/main.py` showing where the hook belongs.

## Improved
- Bridge version bumped to `0.5.2-pass2`.
- Panda3D checks now distinguish dependency readiness, project discovery, runtime launch, and screenshot proof.
- Full-pass can now block delivery when Panda3D smoke or required screenshot proof fails.

## Limits
- Automatic screenshot capture requires the game to use the included hook or otherwise honor `GPT_BRIDGE_SCREENSHOT_PATH`.
- Deep gameplay correctness still needs project-specific route markers or custom test hooks.
