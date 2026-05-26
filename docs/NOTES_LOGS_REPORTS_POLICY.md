# GPTOOL Notes, Logs, and Reports Policy

## Source-controlled notes

Keep curated, current docs under `docs/`:

```text
docs/CHANGELOG.md
docs/VALIDATION_HISTORY.md
docs/GPTOOL_ENGINE_SCOPE.md
docs/AI_PATCH_GATE_RULES.md
docs/APP_CAPSULE_BRIDGE.md
docs/AUTOMATION_TASK_DIRECTOR.md
```

## Development outputs

Runtime outputs belong under `reports/` or `logs/` only while developing. They should be excluded from clean handoff zips unless explicitly requested.

Examples:

```text
reports/latest_report.json
reports/latest_report.md
reports/automation_tasks/
logs/*.log
smoke screenshots
crash_reports/
```

## Old pass notes

Old `logs/CHANGELOG_PASS*.md` and `logs/TESTED_PASS*.md` were combined into:

```text
docs/CHANGELOG.md
docs/VALIDATION_HISTORY.md
```

Do not keep scattering new pass notes into `logs/`. Add curated notes to the two docs above.

## Release/source zip rule

A GPTOOL handoff zip should not include:

```text
.git/
managed project folders
nested venvs
__pycache__/
*.pyc
*.log
old reports
old screenshots
temporary patch zips
crash reports
```
