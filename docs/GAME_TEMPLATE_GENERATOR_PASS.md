# Game Template Generator Pass

## Goal
Make the bridge useful to AI agents as a game creation starting point:

```text
command → settings → generate → Panda3D-ready template
```

## Commands

### Plan settings only

```bash
python bridge.py plan-game . --profile panda3d --command "make a neon vector open world with urban robots"
```

Outputs:

```text
reports/game_settings.json
reports/game_settings.md
```

### Generate from settings

```bash
python bridge.py generate-template ./GeneratedGame --settings reports/game_settings.json
```

### One-command generation

```bash
python bridge.py generate-game ./GeneratedGame --profile panda3d --command "make a neon vector open world with urban robots"
```

## Generated Project Contents

```text
GeneratedGame/
  main.py
  settings/game_settings.json
  bridge_project.json
  README.md
  requirements.txt
  VALIDATION_COMMANDS.txt
  generated_template_manifest.json
  data/regions/*.json
  data/characters/*.json
  assets/models/
  assets/textures/
  assets/sfx/
  assets/music/
  logs/
  reports/
  screenshots/
```

## Design Defaults
- Procedural-first geometry.
- Safe spawn hub.
- Points in the top-right corner.
- No FPS counter by default.
- No required external assets.
- Smoke screenshot hook via `GPT_BRIDGE_SCREENSHOT_PATH`.
- Editable settings are the source of truth.

## Next Work
The next upgrade should deepen the settings layer into reusable world and character standard libraries, with richer templates for:
- hub worlds
- FPS arenas
- biome rings
- character/NPC kits
- vehicle/craft kits
- objectives and rulesets
