# HoloUtopia Simulation

Pass 18 adds the first deterministic citizen schedule runner.

The simulation layer is intentionally data-first and safe:

- authored citizen identity stays in `citizens/citizen_manifest.json`
- authored schedules stay in `citizens/citizen_schedules.json`
- authored relationships stay in `citizens/citizen_relationships.json`
- runtime state should be copied/written under `saves/`
- activity history should be append-only JSONL
- HoloVerse `main.py` is not touched by this pass

The current runner answers one simple question cleanly:

> Where should every citizen be at a given city clock time?

Use:

```powershell
cd data\HoloVerse
python tools\simulate_holoutopia_citizen_day.py --sample-times 06:00 08:00 12:00 17:30 21:00
python tools\validate_holoutopia_schedule_runner.py
python tools\render_holoutopia_schedule_preview.py --out ..\..\holoutopia_citizen_schedule_runner_preview.png
```

Future runtime integration should import `holoutopia_citizen_simulation.py` and copy derived state into a real save file instead of mutating authored JSON.
