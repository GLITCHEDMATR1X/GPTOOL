# GPTOOL Cleanup Audit

Audit date: 2026-05-25

## Result

```text
Original uploaded tree size: 614.19 MB
Clean GPTOOL core size:      9.54 MB
Reduction:                  604.65 MB
```

## Removed from clean handoff

```text
GLITCHED MATRIX Prototype Lab/
GLITCHED-MATRIX-Prototype-Lab-Website/
VR/
.git/
logs/
reports/
tools/pass_combiner_tool_v5/
clone_attempt.log
dry_run_result.txt
portable_build_fix_v4.zip
fbx_animation_body_pass.patch
drop-in README fragments now represented in docs/
runtime caches and pyc files
nested venvs if present
```

## Preserved

```text
core bridge modules
Patch Gate
App Capsule Bridge
Automation Task Director
validators
diagnostics
runtime hooks
maintenance tools
profiles
task manifests
tests
curated docs
```

## Notes

The uploaded zip still contained managed project folders and a nested virtual environment through the old GX copy. The clean handoff excludes them because those projects now belong beside GPTOOL under `D:/Apps`, not inside GPTOOL source.
