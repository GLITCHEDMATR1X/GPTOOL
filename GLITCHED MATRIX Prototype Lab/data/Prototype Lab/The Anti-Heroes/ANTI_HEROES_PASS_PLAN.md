# The Anti-Heroes — One-Pass Improvement Plan

This file is a source-of-truth handoff for Anti-Heroes implementation passes.

## Current target

The Anti-Heroes should become the third-person city sandbox flagship inside GX Prototype Lab.

Primary loop:

```text
spawn in readable city -> choose stance/contract -> travel street route -> district state changes -> return to service anchor -> upgrade/continue
```

## Must preserve

- existing `main.py` runtime if present;
- existing combat/editor/menu code;
- imported NPC/body assets;
- launchability from GX Prototype Lab;
- third-person movement/camera;
- ESC/pause/exit behavior;
- crash logs and screenshots.

## First code pass goals

Implement only if the matching runtime files are found:

1. Add a lightweight `antiheroes_state.json` or equivalent runtime state payload.
2. Track active district, stance, reputation, district heat, contract availability, and service anchors.
3. Add small edge HUD text for district, stance, and active contract.
4. Add city readability anchors: spawn plaza label, four district directions, and route spine markers.
5. Add proof output under `reports/` and screenshots under `screenshots/`.

## One-command review pipeline

`antiheroes_gptool_pipeline.py` ties the bridge, registry, manifest sync helper, spawn roster, and runtime adapter together for review.

Static review command:

```bash
python antiheroes_gptool_pipeline.py --static
```

Visual review command, when Panda3D is installed:

```bash
python antiheroes_gptool_pipeline.py --visual
```

Outputs:

```text
reports/antiheroes_gptool_pipeline_report.json
reports/antiheroes_gptool_pipeline_report.md
```

Static mode checks Python syntax, manifest readability, animation registry output, manifest sync dry-run when a manifest exists, spawn roster validation, and runtime adapter state output. Visual mode also attempts the asset bridge screenshot probe and per-role animation screenshot probe.

## GPTOOL manifest sync

`antiheroes_manifest_sync.py` is the safe copy/rewrite tool between GPTOOL's exported human manifest and the Anti-Heroes city folder.

Preview command:

```bash
python antiheroes_manifest_sync.py --source-manifest path/to/human_manifest.json --dry-run
```

Apply command:

```bash
python antiheroes_manifest_sync.py --source-manifest path/to/human_manifest.json --apply
```

Outputs:

```text
assets/characters/humans/human_manifest.json
assets/characters/humans/antiheroes_manifest_lock.json
reports/antiheroes_manifest_sync_report.json
reports/antiheroes_manifest_sync_report.md
```

The sync helper copies model and animation files into the Anti-Heroes asset tree, rewrites manifest relative paths so the city runtime can read them, and writes a lock file for traceability. Always run `--dry-run` before `--apply`.

## Spawn roster

`antiheroes_spawn_roster.py` assigns synced manifest models to city roles and spawn positions.

Commands:

```bash
python antiheroes_spawn_roster.py --init-default
python antiheroes_spawn_roster.py --validate
```

Outputs:

```text
data/characters/antiheroes_spawn_roster.json
reports/antiheroes_spawn_roster_report.json
reports/antiheroes_spawn_roster_report.md
```

The default roster creates entries for the player, contract contact, safehouse guardian, and vendor specialist. It stores model id, role, district, spawn position, heading, scale, initial motion, stance, and faction. The live runtime can later read this roster and call `AntiHeroesCharacterRuntime.spawn_manifest_character(...)` for each enabled entry.

## GPTOOL model and animation bridge

`antiheroes_asset_bridge.py` reads GPTOOL-exported character assets from:

```text
assets/characters/humans/human_manifest.json
```

It selects a base model, tries Panda3D `Actor` first, binds compatible animation clips by role, then falls back to static `loadModel` without crashing if the rig or animation set cannot bind.

Direct visual probe command:

```bash
python antiheroes_asset_bridge.py --visual-probe
```

Outputs:

```text
screenshots/progress/antiheroes_asset_probe_before.png
screenshots/progress/antiheroes_asset_probe_after.png
screenshots/progress/antiheroes_asset_probe_diff_notes.json
reports/antiheroes_asset_bridge_proof.json
```

## Animation registry and role probes

`antiheroes_animation_registry.py` lets Anti-Heroes understand animation clips before the live runtime depends on them.

Commands:

```bash
python antiheroes_animation_registry.py --write-registry
python antiheroes_animation_registry.py --role-probe
```

Outputs:

```text
reports/antiheroes_animation_registry.json
reports/antiheroes_animation_role_probe.json
screenshots/progress/animation_roles/
```

The registry normalizes clips into stable roles: `idle`, `walk`, `run`, `jump`, `attack`, `hit`, `fall`, `death`, `get_up`, and `block`. Missing clips are warnings, not launch blockers.

## Runtime character adapter

`antiheroes_character_runtime_adapter.py` is the safe seam for the live game. It does not construct `ShowBase` and does not edit the existing game loop. The live runtime can import it after its Panda3D scene exists.

Example:

```python
from pathlib import Path
from antiheroes_character_runtime_adapter import AntiHeroesCharacterRuntime

character_runtime = AntiHeroesCharacterRuntime(project_root=Path(__file__).parent)
node, state = character_runtime.spawn_manifest_character(
    loader=base.loader,
    parent=render,
    role="player",
    pos=(0, 0, 0.05),
    scale=1.0,
)

character_runtime.set_motion_state("walk", speed=4.0)
character_runtime.set_motion_state("run", speed=8.0)
```

Runtime proof output:

```text
reports/antiheroes_character_runtime_state.json
```

The adapter records model id, Actor/static load status, movement state, animation role, animation name, available animations, missing roles, fallback reason, and last error. Missing clips should not crash Anti-Heroes.

State-only proof command:

```bash
python antiheroes_character_runtime_adapter.py --state-only
```

## Do not do yet

- Do not add more random enemy waves until the city route is readable.
- Do not make flight the default movement mode.
- Do not remove existing systems to simplify implementation.
- Do not create a second unrelated Anti-Heroes copy.
- Do not claim visual proof if only static validation ran.

## Suggested proof command through GPTOOL

From the GPTOOL repo after cloning both repos side by side:

```bash
python tools/run_antiheroes_pass.py --gx-root ../GX-Prototype-Lab --runtime auto
```

For static-only validation:

```bash
python tools/run_antiheroes_pass.py --gx-root ../GX-Prototype-Lab --runtime mock_display --no-smoke
```

## Acceptance checklist

- Anti-Heroes launches from its existing path.
- The player starts facing a readable route.
- City has at least four clear district directions or markers.
- HUD remains edge-oriented and does not cover gameplay.
- Stance/district/contract state exists in proof data or logs.
- No unrelated prototypes are modified.
- GPTOOL report is written after the pass.
- `antiheroes_gptool_pipeline.py --static` writes JSON and Markdown pipeline reports.
- `antiheroes_gptool_pipeline.py --visual` writes screenshot progress paths when Panda3D is available.
- `antiheroes_manifest_sync.py --dry-run` previews manifest copy/rewrite actions before importing assets.
- `antiheroes_manifest_sync.py --apply` writes Anti-Heroes manifest and lock file only after the dry run is clean.
- `antiheroes_spawn_roster.py --init-default` creates player/service/contact city role assignments.
- `antiheroes_spawn_roster.py --validate` writes spawn roster validation reports.
- `antiheroes_asset_bridge.py --visual-probe` writes before/after screenshots to `screenshots/progress`.
- `antiheroes_animation_registry.py --write-registry` writes role coverage and missing-file warnings.
- `antiheroes_animation_registry.py --role-probe` writes per-role screenshots under `screenshots/progress/animation_roles` when Panda3D is available.
- `antiheroes_character_runtime_adapter.py --state-only` writes a runtime state proof file.
- The live runtime can call `spawn_manifest_character` and `set_motion_state` without taking a hard dependency on GPTOOL internals.
