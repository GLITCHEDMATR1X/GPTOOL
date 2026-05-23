# GPTOOL Pass 17 — AI Patch Gate Drop-In

This drop-in turns GPTOOL into the approval gate for AI-made update passes across the GX / HoloVerse / HoloCore project family.

## Main rule

Patches do **not** blindly overwrite protected files.

They are reviewed, combined, validated, staged when risky, and applied only after approval.

## Install

Copy these files/folders into the root of your local `GPTOOL` directory:

```text
patching/
docs/
START_PATCH_GATE.bat
RUN_PATCH_GATE_SELFTESTS.bat
INSTALL_BRIDGE_PATCH_GATE_DRY_RUN.bat
INSTALL_BRIDGE_PATCH_GATE_APPLY.bat
PATCH_GATE_DROP_IN_README.md
```

Then double-click:

```text
START_PATCH_GATE.bat
```

The menu stays open. It does not flash and close.

## Optional bridge.py integration

The patch gate works without editing `bridge.py`.

If you want bridge commands like `python bridge.py patch-menu`, run:

```text
INSTALL_BRIDGE_PATCH_GATE_DRY_RUN.bat
```

Review the plan. Then run:

```text
INSTALL_BRIDGE_PATCH_GATE_APPLY.bat
```

That installer creates:

```text
bridge.py.patch_gate.bak
```

before modifying `bridge.py`.

## Intended workflow

```text
1. Review/combine pass zips
2. Produce patch-only zip + diff + approval report
3. Dry-run patch-only zip into GX/app repo
4. Review repo_patch_plan.md
5. Apply only if clean and approved
6. Run validators / Panda3D smoke through GPTOOL
7. Package clean output only
```

## Approval statuses

```text
clean
  Safe to apply after review. No blocked conflicts, overrides, or failed validators.

review-required
  Patch has staged overrides, risky protected-file edits, or non-blocking warnings.

failed
  Syntax, validator, protected-symbol, mapping, or forbidden-content checks failed.
```

## Protected-file behavior

For protected Python files, the patch gate tries additive merge:

```text
new imports
new constants
new top-level functions
new classes
new class methods
```

It does not auto-replace existing protected function or method bodies. Those are staged in:

```text
_pass_overrides/<pass-name>/<target-path>
```

## Notes/logs cleanup rule

The patch gate treats notes/logs as part of update hygiene:

```text
Keep curated docs and handoffs.
Combine scattered pass notes when approved.
Move dry-run/validator output to reports.
Do not ship raw logs, crash reports, smoke screenshots, __pycache__, or .pyc.
```
