# Pass 12 — Simulation Route Proof

This pass makes the generated Panda3D simulation mode more testable.

## Added

- `--route-proof` for generated `main.py`.
- Automatic male tester movement, simulated Tab swap, female tester movement, route markers, scene proof JSON, and one backup screenshot.
- Proof state now records start/end positions, swap count, marker count, and route events.

## Intended use

```bash
python main.py --screenshot-mode --route-proof --screenshot-path screenshots/simulation_mode_backup.png --proof-path reports/simulation_mode_scene_proof.json
```

This is for validating playable edit-test mode without relying on manual keyboard input.
