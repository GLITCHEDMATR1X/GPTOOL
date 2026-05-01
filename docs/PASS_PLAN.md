# GPT Tool Pass Plan

## Critical first
1. Clean release baseline. **Done in 0.5.1-pass1.**
2. One-command CLI core. **Started in 0.5.1-pass1.**
3. Trust and gate fixes. **Started in 0.5.1-pass1.**

## High value next
4. Panda3D runtime harness. **Started in 0.5.2-pass2.**
5. Portable Panda3D runtime/display providers. **Started in 0.5.3-pass3.**
6. AI command accuracy / work-order layer.
7. Screenshot intelligence upgrade.
8. Asset and manifest awareness.
9. Baseline/candidate workspace flow.

## Expansion
10. Project profiles.
11. Report/delivery receipt upgrade.
12. Interactive triage mode.
13. Packaging/distribution checks.

## Later
14. Generator/scaffold layer.

## North-star command

```bash
python bridge.py full-pass . --profile panda3d --runtime auto --smoke --require-screenshot --baseline ../baseline
```

The target result is a clear delivery decision: blocked or allowed, with prioritized repair notes.

## Runtime-provider target

```bash
python bridge.py panda3d-runtimes . --runtime auto
```

The bridge should choose the strongest available player-proof route:

1. Packaged executable.
2. Portable sidecar Python with Panda3D.
3. System Python with Panda3D.
4. Mock display fallback with visual proof marked unverified.


---

# Pass 5 — Command > Settings > Generate
**Priority:** Critical-New  
**Status:** Implemented first version in `0.5.5-pass5`.

## Purpose
Make the bridge produce a Panda3D-ready game template from the user's natural-language command.

## Pipeline

```text
user command → editable settings → generated Panda3D template → bridge validation
```

## Added Commands

```bash
python bridge.py plan-game . --profile panda3d --command "make a neon vector open world with urban robots"
python bridge.py generate-template ./GeneratedGame --settings reports/game_settings.json
python bridge.py generate-game ./GeneratedGame --profile panda3d --command "make a neon vector open world with urban robots"
```

## Generated Template Includes
- `main.py`
- `settings/game_settings.json`
- `bridge_project.json`
- `data/regions/*.json`
- `data/characters/*.json`
- `README.md`
- `requirements.txt`
- `VALIDATION_COMMANDS.txt`
- `reports/`, `logs/`, and `screenshots/` folders
- built-in screenshot hook using `GPT_BRIDGE_SCREENSHOT_PATH`

## Standards Added
- safe spawn hub
- procedural-first assets
- no FPS counter by default
- points UI in the top-right
- clear non-placeholder character silhouettes
- region metadata and navigation rules
- smoke/screenshot validation path

