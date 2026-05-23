# GPTOOL Pass 18 — App Capsule Bridge Drop-In

Copy this drop-in into your local GPTOOL folder.

## Start here

Double-click:

```text
START_APP_CAPSULE_BRIDGE.bat
```

## Main commands after optional bridge install

```bash
python bridge.py app-menu
python bridge.py app-scan ./SomeGame
python bridge.py app-migrate-plan ./SomePygameGame --target panda3d_same_window --write-sample-capsule
python bridge.py app-adapter-audit ./data/HoloVerse
python bridge.py app-validate ./data/HoloVerse/HoloCore
```

## Optional bridge.py integration

Run dry-run first:

```text
INSTALL_BRIDGE_APP_CAPSULES_DRY_RUN.bat
```

Then apply only after reviewing the report:

```text
INSTALL_BRIDGE_APP_CAPSULES_APPLY.bat
```

This creates a bridge.py backup before editing.

## What this pass does

- Scans Python apps and classifies frameworks.
- Detects pygame / Panda3D / tkinter / subprocess patterns.
- Builds migration plans for pygame to Panda3D capsules.
- Audits adapter/bridge/wrapper files for host-ownership risk.
- Validates app_manifest.json and capsule lifecycle objects.
- Adds a Windows menu that does not instantly close.

## What it does not do yet

It does not automatically convert a pygame game into Panda3D. It creates the plan and safe capsule target first, so we can approve the architecture before generated code rewrites anything.
