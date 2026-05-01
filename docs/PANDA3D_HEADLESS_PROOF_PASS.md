# Panda3D Headless Scene Proof Pass

GPTOOL can now validate a generated Panda3D template in a display-less environment without pretending that a screenshot was captured.

## New command pattern

```bash
python bridge.py panda3d-smoke ./GeneratedGame \
  --entry main.py \
  --runtime portable \
  --runtime-path /path/to/panda3d_runtime \
  --window-type none \
  --frames 1 \
  --require-proof \
  --proof-path reports/panda3d_scene_proof.json
```

## What the proof means

The JSON proof confirms that:

- the selected Python runtime can import Panda3D,
- the generated Panda3D app entered smoke mode,
- `ShowBase(windowType="none")` was able to construct the scene,
- render/UI node counts were collected,
- the app exited without a crash.

## What it does not mean

Headless scene proof is not the same as visual screenshot proof. Use `--require-screenshot` on a display/offscreen-capable machine or packaged EXE route when final visual framing must be proven.
