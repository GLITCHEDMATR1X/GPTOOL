# TESTED PASS 4

Environment used for this package pass:

```text
Python 3.13.5
```

## Checks run

```bash
python -S -m py_compile bridge.py command_bridge/*.py
```

Result: passed.

```bash
python -S bridge.py --version
```

Result: `GPT Game Generation Bridge 0.5.4-pass4`.

```bash
python -S bridge.py plan-command /tmp/gptbridge_test --profile holoverse --command "remove the fps counter and show points only small in the top-right, no UI background box, keep UI on screen"
```

Result: created `work_order.json` and `work_order.md` with expected must-do / must-not-do items.

```bash
python -S bridge.py verify-command /tmp/gptbridge_test --work-order /tmp/gptbridge_test/reports/work_order.json --changed-files main.py
```

Result: command verification ran and produced warnings for static FPS references, as expected.

```bash
python -S bridge.py full-pass /tmp/gptbridge_test --profile holoverse --runtime mock --work-order /tmp/gptbridge_test/reports/work_order.json --changed-files main.py
```

Result: full-pass included AI work-order loading and AI command verification.

## Note about `python -S`

The test container's default Python site startup can hang after printing output. The bridge code itself exits normally when launched in a normal Python environment, but tests here used `python -S` to avoid that container-specific site startup issue.
