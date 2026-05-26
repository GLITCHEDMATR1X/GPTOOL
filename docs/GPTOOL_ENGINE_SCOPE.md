# GPTOOL Engine Scope

GPTOOL is the AI-specialized control layer for the user's own game ecosystem. It should stay small, strategic, and reusable.

## Core responsibility

GPTOOL should handle:

```text
AI work-order planning
safe patch intake and approval
protected-file merge/review
app capsule scans and migration plans
automation task runs
Panda3D runtime smoke tests
screenshot/proof checks
package and release cleanliness
```

## Core folders

Keep these inside GPTOOL:

```text
bridge.py
adapters/
app_capsules/
automation_tasks/
command_bridge/
diagnostics/
docs/
extensions/
game_builder/
maintenance/
patching/
profiles/
reviewers/
runtime_hooks/
scanners/
task_manifests/
tests/
validators/
```

## Managed projects should live beside GPTOOL

Do not keep full projects inside the GPTOOL source tree. Keep them as sibling folders such as:

```text
D:/Apps/GPTOOL
D:/Apps/GLITCHED MATRIX Prototype Lab
D:/Apps/GLITCHED-MATRIX-Prototype-Lab-Website
D:/Apps/VR
```

GPTOOL should point to them through `project_registry/local_project_roots.json`, not carry full copies.

## Current cleanup rule

The following are development outputs or managed projects, not GPTOOL source:

```text
GLITCHED MATRIX Prototype Lab/
GLITCHED-MATRIX-Prototype-Lab-Website/
VR/
logs/
reports/
__pycache__/
*.pyc
*.log
*.zip
*.patch
.venv/
crash_reports/
```

## Next scope pass

Recommended next implementation pass:

```text
GPTOOL Pass 20 - Core Cleanup + Extension Registry
```

Goals:

```text
wire Patch Gate, App Capsule Bridge, and Automation Tasks into bridge.py through one extension registry
add local project root config loading
upgrade package-audit to classify managed projects separately from core source
keep release/source zips clean by default
```
