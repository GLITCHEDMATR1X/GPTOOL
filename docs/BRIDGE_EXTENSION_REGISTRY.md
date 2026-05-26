# GPTOOL Bridge Extension Registry

Pass 21 makes `bridge.py` extension-driven so new GPTOOL subsystems do not keep growing the master CLI through pasted command blocks.

## Core rule

`bridge.py` owns the base CLI. Feature systems own their own adapter modules.

The registry in `integrations/bridge_extension_registry.py` wires the current first-class systems:

```text
patching.bridge_patch_adapter       -> patch-menu / patch-combine / patch-repo-*
app_capsules.bridge_app_adapter     -> app-menu / app-scan / app-migrate-plan / app-validate
automation_tasks.bridge_task_adapter -> task-menu / task-validate / task-run / task-new
```

Use this command to check which extensions are active:

```bash
python bridge.py extension-status
python bridge.py extension-status --json
```

## Why this exists

GPTOOL is becoming the user's AI-specialized game-engine control layer. Patch Gate, App Capsule Bridge, and Automation Task Director should act like engine modules, not scattered one-off installers.

This keeps `bridge.py` stable while allowing focused systems to evolve independently.

## Local root variables for task manifests

Automation task manifests now support local path variables such as:

```text
${gptool}
${gx_prototype_lab}
${holoverse}
${holocore}
${holoutopia}
```

Copy this template:

```text
project_registry/local_project_roots.template.json
```

to:

```text
project_registry/local_project_roots.json
```

Then adjust paths for your machine. Do not commit personal absolute paths.

You can also pass a root config explicitly:

```bash
python bridge.py task-validate task_manifests/holoverse_artifact_chain.json --root-config project_registry/local_project_roots.json
python bridge.py task-run task_manifests/holoverse_artifact_chain.json --root-config project_registry/local_project_roots.json
```
