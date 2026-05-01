# CHANGELOG PASS 5 — Command > Settings > Generate

Version: `0.5.5-pass5`

## Added
- Added `game_builder/` package.
- Added `plan-game` command for turning natural-language game ideas into editable `game_settings.json`.
- Added `generate-template` command for producing a Panda3D-ready project from settings.
- Added `generate-game` command for the complete one-command flow: command → settings → generated Panda3D template.
- Added procedural-first Panda3D template output:
  - `main.py`
  - `settings/game_settings.json`
  - `bridge_project.json`
  - region JSON files
  - character JSON files
  - README
  - requirements
  - validation commands
  - reports/screenshot/log folders
- Added world/character starter standards:
  - safe spawn hub
  - non-placeholder character rule
  - generated region rules
  - no FPS counter by default
  - top-right points display
  - smoke screenshot environment hook inside generated `main.py`

## Main Commands

```bash
python bridge.py plan-game . --command "make a neon vector open world with urban robots"
python bridge.py generate-template ./GeneratedGame --settings reports/game_settings.json
python bridge.py generate-game ./GeneratedGame --command "make a neon vector open world with urban robots"
```

## Notes
This is a generator foundation, not a full production game creator. It creates a clean Panda3D-ready starting point that an AI agent can then modify through work orders and validation passes.
