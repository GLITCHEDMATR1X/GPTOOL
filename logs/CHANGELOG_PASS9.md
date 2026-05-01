# CHANGELOG_PASS9 — Lean Core Cleanup

- Bumped bridge version to `0.5.9-pass9`.
- Removed heavyweight generated example/proof worlds from the core delivery package.
- Removed Python caches and old generated run output from the working source bundle.
- Added `maintenance/package_cleaner.py` for repeatable package audits, safe cleanups, and lean zip creation.
- Added bridge CLI commands:
  - `package-audit`
  - `clean-package`
  - `package-lean-zip`
- Updated README/RUN_ME_FIRST with lean-package workflow notes.

Result: the core tool is back to a small AI-facing source bridge instead of a zip dominated by generated proof assets.
