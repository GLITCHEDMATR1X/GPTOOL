# TESTED PASS 10 — Panda3D Headless Scene Proof

Version tested: `0.6.0-pass10`

## Environment

- Python used for bridge static checks: `python3 -S`
- Portable Panda3D runtime: `/mnt/data/gptool_py313_panda3d_env/bin/python`
- Panda3D version detected by runtime probe: `1.10.16`

## Commands run

```bash
python3 -S bridge.py --version
```

Observed:

```text
GPT Game Generation Bridge 0.6.0-pass10
```

```bash
python3 -S bridge.py generate-game /mnt/data/gptool_pass10_proof/GeneratedProofWorld --profile panda3d --command "make a neon vector open world with green hills animals, urban robots, desert pyramids, ice hovercraft track, metropolis robot lab, space dyson sphere, and points only in the top right" --force
```

Observed: generated project PASS with `main.py`, settings, region metadata, reports, launch scripts, and validation commands.

```bash
/mnt/data/panda3d_py /mnt/data/gptool_pass10_proof/GeneratedProofWorld/main.py --settings-check
```

Observed: settings check passed.

```bash
python3 -S bridge.py panda3d-smoke /mnt/data/gptool_pass10_proof/GeneratedProofWorld --entry main.py --runtime portable --runtime-path /mnt/data/gptool_py313_panda3d_env --window-type none --frames 1 --require-proof --proof-path reports/pass10_scene_proof.json --output /mnt/data/gptool_pass10_proof/panda3d_smoke_report.json --timeout 30
```

Observed:

```text
Panda3D smoke: PASS
Screenshot: /mnt/data/gptool_pass10_proof/GeneratedProofWorld/reports/panda3d_smoke.png exists=False
- Runtime smoke completed without adapter-detected blockers.
```

## Proof values

- Smoke report `ok`: `True`
- Runtime provider: `portable_python`
- Runtime ready: `True`
- Return code: `0`
- Visual proof mode: `headless_scene_verified`
- Proof schema: `panda3d_smoke_proof.v1`
- Proof status: `headless_scene_built`
- Proof Panda3D version: `1.10.16`
- Window type hint: `none`
- Has window: `False`
- Render child count: `15`
- aspect2d child count: `20`

## Static check

```bash
find . -name '*.py' -not -path '*/__pycache__/*' -print0 | xargs -0 python3 -S -m py_compile
```

Observed: `PY_COMPILE_PASS`

## Known limit

This environment has no real display/audio device. The pass proves real Panda3D import and scene construction in headless mode. Screenshot proof is still expected to be performed on a display/offscreen-capable machine or packaged EXE route.
