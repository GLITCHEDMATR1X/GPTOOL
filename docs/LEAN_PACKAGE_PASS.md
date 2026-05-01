# Lean Package Pass

Goal: keep GPTOOL small enough for AI agents to inspect quickly without losing the ability to generate Panda3D projects.

## Core package keeps

- Bridge CLI and validation pipeline
- Panda3D runtime adapter
- Template generator
- Command planner/verifier
- Human asset scanner/importer
- Runtime smoke hook
- Validators, reviewers, mechanics, profiles, docs, and small samples

## Core package excludes by default

- Generated example worlds
- Copied proof assets
- `__pycache__` folders
- Build/dist folders
- Generated JSON/TXT/log run artifacts
- Latest reports that should be regenerated per project

## Commands

```bash
python bridge.py package-audit .
python bridge.py clean-package .
python bridge.py clean-package . --apply
python bridge.py package-lean-zip ../GPT_Tool_pass9_lean.zip
```

Use `--include-examples` only when you deliberately want demo projects bundled into the zip.
