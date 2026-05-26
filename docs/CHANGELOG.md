# GPTOOL Changelog

> Curated from the old `logs/CHANGELOG_PASS*.md` files during the notes/log cleanup pass. The old `logs/` folder is development history and should not live in release/source zips.


---

# Pass 1 Changelog — Clean Release + One-Command Foundation

## Added
- `bridge.py` master CLI.
- `RUN_ME_FIRST.md` setup guide.
- `requirements.txt` with core screenshot-review dependencies.
- `profiles/generic_python.json`.
- `docs/PASS_PLAN.md`.
- Markdown report generation at `reports/latest_report.md`.

## Improved
- Import validator now understands local packages inside the project root.
- Syntax and import validators can accept folders as well as direct files.
- Master validation pass writes a current JSON and Markdown report.
- CLI returns nonzero when delivery is blocked.

## Fixed
- `diagnostics/pre_submit_gate.py` now exits with code `1` on failed gates.
- `mechanics/acceptance_gate_runner.py` now exits with code `1` on failed acceptance.
- Removed stale generated logs from the clean top-level release.
- Removed Python cache folders from the release bundle.

## Not done yet
- Panda3D smoke launch and screenshot capture adapters.
- Deeper manifest/config asset validation.
- Project-specific visual text rules.
- Candidate workspace promotion flow.



---

# CHANGELOG — Pass 2 Panda3D Runtime Adapter

## Added
- `adapters/panda3d_adapter.py` for Panda3D environment probing, entry discovery, smoke launch, screenshot verification, and fresh log collection.
- `runtime_hooks/panda3d_smoke_hook.py`, an optional frame-delayed screenshot/exit hook for Panda3D ShowBase apps.
- `bridge.py panda3d-doctor` command.
- `bridge.py panda3d-smoke` command.
- `--profile panda3d --smoke` integration for `validate` and `full-pass`.
- `docs/PANDA3D_RUNTIME_PASS.md`.
- `examples/panda3d_smoke_project/main.py` showing where the hook belongs.

## Improved
- Bridge version bumped to `0.5.2-pass2`.
- Panda3D checks now distinguish dependency readiness, project discovery, runtime launch, and screenshot proof.
- Full-pass can now block delivery when Panda3D smoke or required screenshot proof fails.

## Limits
- Automatic screenshot capture requires the game to use the included hook or otherwise honor `GPT_BRIDGE_SCREENSHOT_PATH`.
- Deep gameplay correctness still needs project-specific route markers or custom test hooks.



---

# CHANGELOG — 0.5.3-pass3

## Added
- Runtime provider resolver for Panda3D testing.
- `bridge.py panda3d-runtimes` command.
- `--runtime` selector for Panda3D smoke/full-pass commands.
- `--runtime-path` for sidecar/portable Python runtimes.
- `--exe` for packaged executable smoke tests.
- Auto provider order: packaged EXE, portable Python, system Python, mock display.
- Honest `mock_display` fallback for non-render checks when Panda3D is unavailable.
- Runtime docs and placeholder `runtimes/panda3d_py313/` folder.

## Changed
- Panda3D full-pass now reports `panda3d_runtime_provider` separately from import dependency probing.
- Packaged EXE mode skips bridge-Python Panda3D import requirements.
- Smoke environment now sets `GPT_BRIDGE_RUNTIME_PROVIDER` and adds the bridge root to `PYTHONPATH` so projects can import the included smoke hook.

## Safety rule
Mock mode cannot satisfy required visual proof. If `--require-screenshot` is supplied, delivery stays blocked until a real runtime or packaged EXE produces screenshot proof.



---

# CHANGELOG PASS 4 — AI Command Accuracy Layer

Bridge version: `0.5.4-pass4`

## Added

- Added `command_bridge/` package for deterministic AI work-order planning and verification.
- Added `bridge.py plan-command` to convert a natural-language game-development request into:
  - `must_do`
  - `must_not_do`
  - `do_not_touch`
  - affected areas
  - visual tests
  - static checks
  - runtime checks
  - regression risks
  - AI agent instructions
- Added `bridge.py verify-command` to verify a project/report against a generated work order.
- Added `--work-order` support to `validate` and `full-pass`.
- Added `--changed-files` support for command scope checks.
- Added `--strict-static` mode so remaining forbidden static terms can become blockers when desired.
- Added Markdown output for work orders and command verification reports.
- Extended `latest_report.json` / `latest_report.md` with `work_order` and `command_verification` sections.

## New commands

```bash
python bridge.py plan-command . --profile holoverse --command "remove the fps counter and show only points in the top-right"
```

```bash
python bridge.py verify-command . --work-order reports/work_order.json --changed-files HoloVerse/world.py
```

```bash
python bridge.py full-pass . --profile panda3d --work-order reports/work_order.json --runtime auto --smoke --require-screenshot
```

## Why this pass matters

This pass makes the bridge more useful for AI agents before any code is edited. It gives the AI a strict interpretation of the user's command, then checks whether the final pass stayed inside that request.

The bridge is now better at catching common AI mistakes:

- changing the wrong route,
- adding features before fixing the requested bug,
- leaving forbidden debug/FPS UI behind,
- touching unrelated files,
- skipping visual proof,
- claiming delivery without matching the original command.



---

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



---

# Pass 6 - Rigged Human Asset Import

## Added

- Added `scan-human-assets` to inspect the surrounding asset library for human/character mesh candidates.
- Added `import-human-assets` to copy selected rigged human assets into generated Panda3D projects.
- Added static GLB/GLTF skin and animation introspection for candidate scoring.
- Generated templates now read `assets/characters/humans/human_manifest.json` and try Panda3D `Actor` loading before falling back to static `loadModel`.
- Generated templates now use the shared Panda3D smoke hook when available and honor both `GPT_BRIDGE_SMOKE_FRAMES` and `GPT_BRIDGE_SCREENSHOT_FRAMES`.

## Notes

- GLB/GLTF with detected skin data is preferred for runtime use.
- FBX clips are imported as optional external animation sources and remain skeleton-compatibility dependent.
- Import scans ignore assets already inside the target project so repeated imports do not self-copy generated output.



---

# Pass 7 - Human Mesh Viewer and Export Robustness

## Added

- Generated Panda3D human projects now open as a 16:9 gray studio viewer.
- Imported human meshes are centered and camera-framed for screenshot proof.
- Added preview controls:
  - `[ / ]` cycles imported human meshes.
  - `Tab` cycles embedded Actor animations when available.
- `import-human-assets` now supports `--export-formats glb obj fbx`.
- Imported base assets now include export records in `human_manifest.json`.

## Improved

- Human import selection now avoids duplicate base signatures so the importer pulls in survivor variants and other rigged human meshes instead of repeated `Idle.glb` copies.
- GLB exports from GLB sources are rig-safe copy-through exports.
- OBJ exports are generated as static geometry via `trimesh` when possible.
- FBX export is explicitly reported as copy-through only for FBX sources; GLB-to-FBX is marked skipped instead of pretending to be rig-safe.

## Notes

- External FBX animation clips remain skeleton-compatibility dependent.
- The generated viewer prefers embedded Actor animations before attempting external clip libraries.



---

# Pass 8 - Female Rig Validation and Third-Person Open World Testbed

## Added

- `scan-human-assets` and `import-human-assets` now support:
  - `--prefer` for ranking preferred source tokens.
  - `--require` for filtering to a target source family.
  - `--rigged-only` for base meshes with detected skin data.
  - `--clean` to clear only `assets/characters/humans` before importing.
- Generated human projects now use the imported Actor as the controlled third-person player.
- Added camera-relative WASD movement, Q/E camera rotation, sprint, mesh cycling, and animation cycling.
- Added procedural streaming gray platform chunks around the player for open-world traversal testing.

## Improved

- Female-only import can now stay clean and avoid male survivor or prior generated smoke assets.
- The preview camera backs off and normalizes human scale more conservatively so female rigs fit in 16:9 screenshots.
- GPTOOL-generated example output is ignored during broad asset scans to avoid self-import clutter.

## Notes

- Female rig validation used the two rigged `Female Survivor` GLBs plus one female idle FBX source clip.
- FBX export remains honest: GLB-to-FBX is skipped because this pipeline does not have a rig-safe FBX writer.



---

# CHANGELOG_PASS9 — Lean Core Cleanup

- Bumped bridge version to `0.5.9-pass9`.
- Removed heavyweight generated example/proof worlds from the core delivery package.
- Removed Python caches and old generated run output from the working source bundle.
- Added `maintenance/package_cleaner.py` for repeatable package audits, safe cleanups, and lean zip creation.
- Added bridge CLI commands:
  - `package-audit`
  - `clean-package`
  - `package-lean-zip`
- Updated README/RUN_ME_FIRST with lean-package workflow notes.

Result: the core tool is back to a small AI-facing source bridge instead of a zip dominated by generated proof assets.



---

# CHANGELOG PASS 10 — Panda3D Headless Scene Proof

Version: `0.6.0-pass10`

## Added

- Added a required scene-proof path for Panda3D smoke tests via `--proof-path` and `--require-proof`.
- Added `GPT_BRIDGE_SMOKE_PROOF_PATH` support to the Panda3D adapter.
- Added a `panda3d_smoke_proof.v1` JSON proof file from the smoke hook.
- Added headless Panda3D smoke support for generated templates using `--window-type none`.
- Fixed portable runtime discovery so virtualenv Python symlinks are not resolved away from their `pyvenv.cfg`.

## Fixed

- Generated templates no longer crash in `ShowBase(windowType="none")` when no camera/window exists.
- The smoke hook now writes scene proof before ordinary update tasks by using early task priority.
- Generated templates include a fallback proof writer if the bridge hook is unavailable.

## Result

A generated Panda3D project can now prove that real Panda3D imported, the scene graph built, UI nodes attached, and the app exited cleanly in a display-less environment. Screenshot proof still requires a real display/offscreen-capable runtime.



---

# CHANGELOG — Pass 11 Playable Simulation Characters

- Bumped bridge version to `0.6.1-pass11`.
- Generated templates now include a playable simulation mode with two test characters.
- Added male/female procedural character spawns for edit validation.
- Added `Tab` swapping between active characters.
- Moved optional embedded Actor animation cycling to `C` so it no longer conflicts with character swap.
- Added `--screenshot-mode` to generated `main.py` for backup screenshot capture.
- Added F12 manual screenshot shortcut.
- Extended smoke proof JSON with generated app state.
- Updated docs, validation commands, and template metadata.



---

# Changelog — Pass 12

- Bumped bridge version to `0.6.2-pass12`.
- Added generated-template `--route-proof` simulation mode.
- Route proof automatically moves the male tester, simulates a Tab swap, moves the female tester, and drops visible route markers.
- Scene proof now records route start/end positions, swap count, route marker count, and events.
- Updated validation commands so backup screenshot proof can exercise actual playable controls.
- Made the Panda3D smoke hook exit deterministic after proof capture in headless/offscreen runs.
- Changed generated screenshot mode default window hint to `default` so Panda3D can choose the working fallback display path.
- Generated test/screenshot mode now manually steps Panda3D tasks so proof capture does not depend on an onscreen event loop.
- Added synchronous route-proof execution for generated screenshot mode so movement/swap proof does not depend on realtime task-loop progress.
- Route proof saves the current offscreen buffer directly to avoid blocking render loops in display-less containers.
- Generated automated proof modes use `os._exit(0)` after proof writing to avoid interpreter-finalization hangs in this container.
- Restored two explicit `renderFrame()` calls before route screenshots now that automated proof exits with `os._exit(0)`.



---

# GPTOOL Pass 13 Changelog — Smoother Playable Controls

- Bumped bridge version to `0.6.3-pass13`.
- Upgraded generated Panda3D playable simulation controls.
- Added smoothed acceleration/friction movement.
- Added Space jump with gravity.
- Added mouse-wheel camera zoom and `R` camera reset.
- Added smoother camera follow interpolation.
- Added controller-model metadata to proof JSON.
- Updated generated README/control notes.



---

# GPTOOL Pass 14 Changelog — Local Crash Fix

- Bumped bridge version to `0.6.4-pass14`.
- Fixed generated route-proof crash caused by `jump_was_down` not existing before proof JSON was written.
- Initialized player jump state during generated app startup.
- Made proof-state serialization safe with `getattr` fallback.
- Bumped generated template version to `panda3d_playable_simulation_template.v5`.



---

# GPTOOL Pass 15 Changelog - Crash Diagnostics and Stress Proof

- Bumped bridge version to `0.6.5-pass15`.
- Bumped generated template version to `panda3d_playable_simulation_template.v6`.
- Added generated crash diagnostics:
  - `logs/crash_latest.txt`
  - `logs/runtime_latest.json`
  - `logs/last_controls_state.json`
  - `logs/last_scene_state.json`
- Added generated `--stress-proof` mode with `gptool_simulation_proof.v2`.
- Added generated `--force-crash-test` for controlled diagnostics validation.
- Fixed missing generated camera zoom/reset callbacks used by mouse wheel and `R`.
- Added a Panda3D generated stress-proof CI job with artifact upload.
- Updated README, run notes, release notes, and Pass 15 diagnostics docs.



---

# GPTOOL Pass 16 Changelog - Broader Model Import Proof

- Bumped bridge version to `0.6.6-pass16`.
- Hardened human asset scanning so broad scans skip GPTOOL generated proof/output folders.
- Updated generated playable simulation characters to load imported human Actor meshes from `human_manifest.json` before falling back to procedural bodies.
- Added `actor_loaded` and `asset_manifest_id` to generated scene proof character state.
- Disabled Panda3D audio consistently in generated templates to avoid desktop proof cleanup noise.
- Updated asset validation to ignore known runtime-generated screenshot/proof/log output names.
- Validated a broad local import test with 10 rigged GLB base models, 12 FBX animation clips, GLB/OBJ/FBX export reporting, and stress-proof runtime validation.



---

# GPTOOL Pass 17 Changelog - AI Patch Gate

- Added `patching/` safe pass combiner and repo patch tools.
- Added no-silent-overwrite rules for protected files.
- Added Patch Gate launcher and documentation.
- Added override staging for review-required patch content.


---

# GPTOOL Pass 18 Changelog - App Capsule Bridge

- Added `app_capsules/` framework classifier, migration planner, and capsule validator.
- Added shared app capsule contract: prepare, enter, update, exit, cleanup, get_result.
- Added pygame-to-Panda3D migration rules and adapter audit direction.


---

# GPTOOL Pass 19 Changelog - Automation Task Director

- Added `automation_tasks/` Codex-style local task runner.
- Added task manifests for HoloVerse, HoloCore, and HoloUtopia test workflows.
- Added approval-gated patch apply steps, command steps, smoke steps, junk checks, and JSON/Markdown task reports.

---

# PASS 21 — Core Extension Registry

## Added

- Added `integrations/bridge_extension_registry.py` as the single registration point for bridge extensions.
- Added `python bridge.py extension-status` and `--json` status output.
- Registered Patch Gate commands through `patching.bridge_patch_adapter`:
  - `patch-menu`
  - `patch-rules`
  - `patch-combine`
  - `patch-repo-dry-run`
  - `patch-repo-apply`
- Registered App Capsule Bridge commands through `app_capsules.bridge_app_adapter`:
  - `app-menu`
  - `app-scan`
  - `app-migrate-plan`
  - `app-adapter-audit`
  - `app-validate`
- Registered Automation Task Director commands through `automation_tasks.bridge_task_adapter`:
  - `task-menu`
  - `task-validate`
  - `task-run`
  - `task-new`
- Added `automation_tasks/path_resolver.py` for local project-root variable expansion in task manifests.
- Updated task manifests to use `${holoverse}`, `${holocore}`, and `${holoutopia}` instead of hardcoded absolute paths.
- Added `docs/BRIDGE_EXTENSION_REGISTRY.md`.

## Why

The bridge should not become another adapter cluster. Feature systems now register through one stable extension registry.


---

# PASS 22 — Test Run Bot Foundations

## Added

- Added `automation_tasks/input_script.py` with `gptool.input_plan.v1` validation and Markdown rendering.
- Added task actions for `write_input_plan`, `validate_input_plan`, `screenshot_checkpoint`, and `panda3d_journey_smoke`.
- Added Vector Arena controls/SFX and artifact-chain input-plan manifests.
- Added `docs/TEST_RUN_BOT_FOUNDATIONS.md`.
- Added `tests/selftest_test_run_bot.py`.

## Why

GPTOOL test runs now have explicit game-journey plans instead of only generic command smoke steps. Real Panda3D projects can later consume `GPT_BRIDGE_JOURNEY_PLAN` for in-window bot playback.

## Pass 23 - Test Run Director hardening

- Task reports now distinguish blocking failures from non-blocking warnings.
- `panda3d_journey_smoke` can forward `window_type`, proof paths, frame counts, and extra environment hints to `bridge.py panda3d-smoke`.
- Vector Arena journey manifest now requests offscreen smoke mode where supported.
