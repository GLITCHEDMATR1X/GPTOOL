from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from holoutopia_watch_focus import build_watch_focus_state, validate_watch_focus


def main() -> int:
    errors = validate_watch_focus(ROOT)
    if errors:
        print("[FAIL] HoloUtopia Watch Focus validation failed")
        for err in errors:
            print(f" - {err}")
        return 1
    clocks = ["06:45", "12:45", "18:15", "20:35"]
    states = [build_watch_focus_state(ROOT, clock) for clock in clocks]
    print("[OK] HoloUtopia Watch Focus validated")
    for state in states:
        citizen = state.get("focus_citizen", {})
        cluster = state.get("focus_cluster", {})
        print(f"[OK] {state.get('clock')} target={citizen.get('representative_label')} cluster={cluster.get('label')} street_safe={citizen.get('street_safe')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
