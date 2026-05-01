# Panda3D Runtime / Screenshot Adapter

Pass 2 adds a conservative Panda3D adapter. It does not pretend to prove gameplay semantics by itself; it verifies the launch route, captures process output, discovers likely entry points, looks for fresh logs, and can require screenshot proof when the target game cooperates.

## Quick commands

```bash
python bridge.py panda3d-doctor .
python bridge.py panda3d-smoke . --entry main.py --require-screenshot
python bridge.py full-pass . --profile panda3d --smoke --entry main.py --require-screenshot
```

## How screenshot proof works

The bridge sets these environment variables during smoke tests:

```text
GPT_BRIDGE_TEST_MODE=1
GPT_BRIDGE_SMOKE=1
GPT_BRIDGE_SCREENSHOT_PATH=<path>
GPT_BRIDGE_SMOKE_FRAMES=<frames>
GPT_BRIDGE_EXIT_AFTER_SCREENSHOT=1
```

A Panda3D game can honor that directly, or it can install the included hook after ShowBase creation:

```python
from runtime_hooks.panda3d_smoke_hook import install_from_env
install_from_env(base)
```

The hook is inactive during normal play unless the bridge smoke environment is present.

## What this adapter proves

- Panda3D dependency discoverability.
- Likely Panda3D entry point.
- Launch process return code.
- Timeout vs clean exit.
- stdout/stderr crash signatures.
- Fresh crash/runtime logs.
- Screenshot existence when requested.

## What it does not prove alone

- That the player selected the right bot.
- That a specific in-game route was activated.
- That combat AI behaves correctly.
- That UI text is semantically correct.

For those, add project-specific smoke hooks or visible route markers, then make screenshot rules require those markers.
