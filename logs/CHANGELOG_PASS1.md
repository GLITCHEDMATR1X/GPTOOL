# Pass 1 Changelog — Clean Release + One-Command Foundation

## Added
- `bridge.py` master CLI.
- `RUN_ME_FIRST.md` setup guide.
- `requirements.txt` with core screenshot-review dependencies.
- `profiles/generic_python.json`.
- `docs/PASS_PLAN.md`.
- Markdown report generation at `reports/latest_report.md`.

## Improved
- Import validator now understands local packages inside the project root.
- Syntax and import validators can accept folders as well as direct files.
- Master validation pass writes a current JSON and Markdown report.
- CLI returns nonzero when delivery is blocked.

## Fixed
- `diagnostics/pre_submit_gate.py` now exits with code `1` on failed gates.
- `mechanics/acceptance_gate_runner.py` now exits with code `1` on failed acceptance.
- Removed stale generated logs from the clean top-level release.
- Removed Python cache folders from the release bundle.

## Not done yet
- Panda3D smoke launch and screenshot capture adapters.
- Deeper manifest/config asset validation.
- Project-specific visual text rules.
- Candidate workspace promotion flow.
