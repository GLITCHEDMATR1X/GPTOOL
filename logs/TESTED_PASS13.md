# GPTOOL Pass 13 Tested

Local validation performed during the pass:

- `python bridge.py --version`
- AST syntax check across Python files
- `python bridge.py generate-game` for a fresh Panda3D probe project
- generated `main.py --settings-check`
- generated `main.py` AST syntax check
- Panda3D offscreen `--screenshot-mode --route-proof` screenshot/proof run
- Zip/package integrity check

The generated screenshot path and proof bundle are included in the pass handoff.
