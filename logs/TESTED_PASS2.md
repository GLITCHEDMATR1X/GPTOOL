# TESTED — Pass 2

Environment used for packaging tests:

- Python: 3.13.5 via `/usr/bin/python3`
- Panda3D: not installed in this container, intentionally verified as a reported warning/failure condition

## Commands run

```bash
/usr/bin/python3 -m compileall -q .
/usr/bin/python3 bridge.py --version
/usr/bin/python3 bridge.py scan .
/usr/bin/python3 bridge.py panda3d-doctor . --json
/usr/bin/python3 bridge.py panda3d-smoke /mnt/data/gpt_panda_fake_project --entry main.py --require-screenshot --screenshot-path reports/smoke.png
/usr/bin/python3 bridge.py full-pass /mnt/data/gpt_panda_fake_project --profile panda3d --smoke-command '/usr/bin/python3 main.py' --require-screenshot --screenshot-path reports/smoke2.png --report-dir /mnt/data/gpt_panda_fake_project/reports/fullpass
```

## Results

- Compile check passed.
- Bridge version reports `0.5.2-pass2`.
- Project scan command works.
- Panda3D doctor command reports missing Panda3D honestly in this environment.
- Direct Panda3D smoke adapter test passed against a fake project that honored `GPT_BRIDGE_SCREENSHOT_PATH`.
- Full-pass Panda3D smoke integration passed against the fake project with screenshot proof.

## Important limit

This container does not have Panda3D installed, so a real Panda3D app launch could not be proven here. The adapter is designed to run on the user's local game machine where `panda3d` and `direct` are installed.
