# Pass 13 — Smoother Playable Controls

This pass upgrades generated Panda3D simulation templates from instant position stepping to a small third-person controller suitable for testing generated player edits.

## Added

- Smoothed acceleration and friction for WASD / arrow movement.
- Shift sprint using the generated settings file.
- Space jump with gravity and safe ground return.
- Mouse-wheel camera zoom.
- `R` camera reset.
- Smoother camera follow and distance interpolation.
- Proof JSON fields describing the controller model.

## Control map

```text
WASD / Arrow keys  movement
Shift              sprint
Space              jump
Q/E or ←/→         rotate camera
Mouse wheel        zoom
R                  reset camera
Tab                swap playable tester
C                  cycle imported Actor animation
F12                backup screenshot
Esc                exit
```

## Validation

Use the generated template command:

```bash
python main.py --screenshot-mode --route-proof --screenshot-path screenshots/pass13_controls.png --proof-path reports/pass13_controls.json
```
