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
