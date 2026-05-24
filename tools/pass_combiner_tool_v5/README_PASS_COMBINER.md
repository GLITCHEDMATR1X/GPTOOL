# Safe Pass Combiner v4

Safe Pass Combiner combines iterative patch/pass zips without letting a partial file silently overwrite a larger integrated runtime file.

Version 4 adds repo-aware patching features:

- Built-in profiles: `generic`, `gx-prototype-lab`, `holoverse`, `holocore`
- Protected-file guards for launchers, routes, adapters, manifests, build scripts, and runtime files
- Line-ending tolerant diff application before zip overlay
- Drop-in `_pass_overrides/` candidates for blocked or small reviewable updates
- Optional patch-only delta zip and unified diff against the original base
- Optional protected Python symbol regression check
- Optional banned-text scan for route-contract strings
- Validator command hooks with timeouts
- GitHub/repo handoff report for local branch + PR review workflow
- File manifest with sha256 hashes
- `apply_pass_overrides.py` for dry-reviewing and applying staged overrides with backups

## HoloCore example

```powershell
python pass_combiner.py ^
  --profile holocore ^
  --base HoloCore.zip ^
  --order-file holocore_pass_order.txt ^
  --project-root-name HoloCore ^
  --output-dir HoloCore_combined ^
  --output-zip HoloCore_combined.zip ^
  --output-patch-zip HoloCore_combined_PATCH_ONLY.zip ^
  --output-diff HoloCore_combined.diff ^
  --report-dir pass_combiner_reports ^
  --compileall ^
  --validate "python tools/validate_holocore_ocean_space.py" ^
  --validate "python tools/validate_holocore_vertical_strata.py" ^
  --validate "python tools/validate_holocore_vessel.py" ^
  --emit-file-manifest ^
  --emit-symbol-manifest ^
  --fail-on-symbol-removal ^
  --emit-repo-handoff ^
  --repo-name GLITCHEDMATR1X/GX-Prototype-Lab
```

## GX Prototype Lab local repo example

Use this when you want a reviewable patch-only output for the repo rather than a full project zip.

```powershell
python pass_combiner.py ^
  --profile gx-prototype-lab ^
  --base "D:\Apps\GLITCHED MATRIX Prototype Lab" ^
  --patches Some_PASS_PATCH_ONLY.zip Another_PASS_PATCH_ONLY.zip ^
  --project-root-name "GLITCHED MATRIX Prototype Lab" ^
  --output-dir gx_combined_review ^
  --output-patch-zip gx_combined_PATCH_ONLY.zip ^
  --output-diff gx_combined.diff ^
  --report-dir gx_combiner_reports ^
  --compileall ^
  --emit-file-manifest ^
  --emit-symbol-manifest ^
  --fail-on-symbol-removal ^
  --emit-repo-handoff ^
  --repo-name GLITCHEDMATR1X/GX-Prototype-Lab
```

## Small updates as drop-in overrides

```powershell
python pass_combiner.py ... --small-updates-to-overrides --small-update-max-bytes 32768
```

This stages small existing-file changes under:

```text
_pass_overrides/<pass-name>/<original-path>
```

Review staged candidates:

```powershell
python apply_pass_overrides.py HoloCore_combined
```

Apply after review:

```powershell
python apply_pass_overrides.py HoloCore_combined --apply
```

## Exit behavior

The tool returns nonzero when it finds conflicts, review-required overrides, failed validators, failed compile checks, symbol regressions, or banned text hits. By default, final zips and patch-only deltas are not written when the result is not clean.

Use `--write-zip-on-failure` only when intentionally exporting a review bundle.

## V5 repo patch workflow

`repo_patch_tool.py` safely maps a patch-only zip into an existing repository checkout.
It is intended for cases where the combined project output should become a small,
reviewable repo patch instead of replacing a whole project folder.

Example for applying a standalone HoloCore patch into GX Prototype Lab:

```powershell
python repo_patch_tool.py ^
  --repo-root "D:\Apps\GLITCHED MATRIX Prototype Lab" ^
  --patch-zip HoloCore_COMBINED_PASS_COMBINER_V4_PATCH_ONLY.zip ^
  --strip-prefix HoloCore ^
  --target-prefix data/HoloVerse/HoloCore ^
  --profile gx-prototype-lab ^
  --report-dir repo_patch_reports ^
  --emit-manifest
```

Dry-run is the default. Add `--apply` only after reviewing `repo_patch_plan.md`.

Important safety behavior:

- The GX profile refuses to strip a patch folder directly into the repo root.
  Use `--target-prefix` so `HoloCore/main.py` becomes
  `data/HoloVerse/HoloCore/main.py`, not root `main.py`.
- Protected Python files use additive definition merge only. Stale same-symbol
  updates are staged under `_pass_overrides/` instead of replacing the live file.
- Small reviewable updates can be sent to `_pass_overrides/` with
  `--small-updates-to-overrides`.
- Junk paths such as logs, screenshots, `__pycache__`, `.pyc`, crash reports,
  and temporary files are ignored.

Useful review command:

```powershell
python repo_patch_tool.py ^
  --repo-root "D:\Apps\GLITCHED MATRIX Prototype Lab" ^
  --patch-zip HoloCore_COMBINED_PASS_COMBINER_V4_PATCH_ONLY.zip ^
  --strip-prefix HoloCore ^
  --target-prefix data/HoloVerse/HoloCore ^
  --profile gx-prototype-lab ^
  --report-dir repo_patch_reports ^
  --small-updates-to-overrides ^
  --fail-on-warning
```

If warnings appear, check `_pass_overrides/` before applying those files to the
real project.
