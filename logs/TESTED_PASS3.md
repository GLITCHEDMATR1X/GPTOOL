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
