# GPTOOL Automation Task Director

Pass 19 adds a local Codex-style task layer for the user's own game-engine workflow.

It does not replace the Patch Gate or App Capsule Bridge. It orchestrates them.

## Core idea

A task manifest describes a repeatable workflow:

```text
inspect
patch gate dry-run
validate
smoke test
screenshot/proof check
cleanup check
approval-required apply
report
```

Dry-run is the default. Steps that can write to a project or apply a patch require explicit `--apply` and, for patch apply steps, the approval token `APPLY`.

## Why this exists

HoloVerse / HoloCore / HoloUtopia updates need more than syntax checks. They need repeatable journeys:

```text
enter artifact
move/shoot/interact
capture proof
return to hub
check no leaked tasks/UI/audio/mouse lock
```

Pass 19 is the foundation for those journeys. Later passes can add real Panda3D input bots and rendered screenshot comparison.

## Commands after bridge integration

```bash
python bridge.py task-menu
python bridge.py task-validate task_manifests/holoverse_artifact_chain.json
python bridge.py task-run task_manifests/holoverse_artifact_chain.json
python bridge.py task-run task_manifests/holoverse_artifact_chain.json --apply
python bridge.py task-new --id my_test --title "My test" --project . --output task_manifests/my_test.json
```

## Rules

- Dry-run first.
- Do not silently apply patch zips.
- Do not hide failed validators.
- Write JSON and Markdown reports for every run.
- Keep logs/reports out of release patch zips unless explicitly requested.
- Approval-required steps must require an explicit approval token.
