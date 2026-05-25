# GPTOOL Pass 19 — Automation Task Director Drop-In

Copy these files into your GPTOOL folder.

Start here:

```text
START_AUTOMATION_TASKS.bat
```

Optional bridge integration:

```text
INSTALL_BRIDGE_AUTOMATION_DRY_RUN.bat
INSTALL_BRIDGE_AUTOMATION_APPLY.bat
```

After bridge integration:

```bash
python bridge.py task-menu
python bridge.py task-validate task_manifests/holoverse_artifact_chain.json
python bridge.py task-run task_manifests/holoverse_artifact_chain.json
```

This pass adds a local Codex-style task runner for your own projects. It is designed to orchestrate GPTOOL Patch Gate, App Capsule Bridge, validators, Panda3D smoke tests, and cleanup checks.
