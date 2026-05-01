# GPTOOL Pass 15 Tested

Local validation performed on 2026-05-01:

```bash
python -S bridge.py --version
python -S bridge.py package-audit . --json
python -S -m py_compile bridge.py game_builder\settings_planner.py game_builder\template_generator.py
python -S - <source AST syntax check>
python -S bridge.py generate-game ./GeneratedProbe --profile panda3d --command "make a playable simulation with two testers, smoother controls, crash diagnostics, stress proof, and points only"
python -S ./GeneratedProbe/main.py --settings-check
python -S - <Generated main.py AST syntax check>
python ./GeneratedProbe/main.py --screenshot-mode --route-proof --stress-proof --screenshot-path GeneratedProbe\screenshots\pass15_stress.png --proof-path GeneratedProbe\reports\pass15_stress.json
python ./GeneratedProbe/main.py --screenshot-mode --force-crash-test --screenshot-path GeneratedProbe\screenshots\forced_crash.png --proof-path GeneratedProbe\reports\forced_crash.json
```

Results:

- Version reports `GPT Game Generation Bridge 0.6.5-pass15`.
- Package audit passed.
- Source syntax passed for the changed source files and AST passed for 42 Python files.
- Generated probe settings check passed.
- Generated `main.py` AST syntax passed.
- Stress proof wrote `GeneratedProbe\reports\pass15_stress.json` with schema `gptool_simulation_proof.v2`.
- Stress proof set Tab swap, jump, sprint, camera zoom, camera reset, and screenshot flags to true.
- Stress proof wrote `GeneratedProbe\screenshots\pass15_stress.png`.
- Normal stress proof had no crash log.
- Forced crash test wrote `GeneratedProbe\logs\crash_latest.txt` plus runtime, controls, and scene diagnostics JSON.
- Generated probe artifacts were removed before commit cleanup.
- Final package audit passed with zero removable cleanup candidates.
