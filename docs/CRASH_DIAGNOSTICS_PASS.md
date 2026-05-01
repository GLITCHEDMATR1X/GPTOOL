# Pass 15 - Crash Diagnostics and Stress Proof

Pass 15 upgrades generated Panda3D templates with diagnostics that are useful when a proof run fails.

Generated templates now write:

- `logs/crash_latest.txt`
- `logs/runtime_latest.json`
- `logs/last_controls_state.json`
- `logs/last_scene_state.json`

The writers are guarded so diagnostics failures do not mask the original runtime exception. In screenshot/proof mode, a crash writes diagnostics and exits nonzero. In normal interactive mode, the crash log path is printed and the original exception is re-raised.

Stress proof can be run from a generated project:

```bash
python main.py --screenshot-mode --route-proof --stress-proof --screenshot-path screenshots/stress.png --proof-path reports/stress.json
```

The proof JSON uses `gptool_simulation_proof.v2` and records movement, sprint, jump, Tab swap, camera zoom/reset, route marker, point, screenshot, crash-log, and diagnostics-file status.
