"""Clean HoloCore entry point.

Standalone HoloCore runs still execute ``main.py`` directly.  From HoloVerse,
HoloCore is same-window only and should be mounted by ``HoloCoreSameWindowScene``.
This wrapper refuses HoloVerse child-window launches so a stale route cannot
create a second overlapping HoloCore copy.
"""
from __future__ import annotations

import json
import os
import runpy
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MAIN = ROOT / "main.py"


def _launched_from_holoverse_child_gateway() -> bool:
    transition_mode = str(os.environ.get("HOLOVERSE_TRANSITION_MODE_ID", "")).strip().lower()
    transition_label = str(os.environ.get("HOLOVERSE_TRANSITION_MODE_LABEL", "")).replace(" ", "").strip().lower()
    gateway_source = str(os.environ.get("HOLOVERSE_GATEWAY_SOURCE", "")).strip().lower()
    transition_active = str(os.environ.get("HOLOVERSE_TRANSITION_ACTIVE", "")).strip().lower() in {"1", "true", "yes", "on"}
    return bool(transition_active and (transition_mode == "holocore" or transition_label == "holocore" or gateway_source == "holocore"))


def _write_child_block_report() -> None:
    payload = {
        "kind": "holocore_child_window_launch_blocked",
        "reason": "HoloCore is same-window only from HoloVerse; use HoloCoreSameWindowScene instead of holocore_entry.py.",
        "timestamp": time.time(),
        "argv": list(sys.argv),
        "transition_mode": os.environ.get("HOLOVERSE_TRANSITION_MODE_ID", ""),
        "transition_label": os.environ.get("HOLOVERSE_TRANSITION_MODE_LABEL", ""),
    }
    try:
        logs = ROOT / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        (logs / "holocore_child_window_blocked.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except Exception:
        pass
    print(payload["reason"])


if __name__ == "__main__":
    if _launched_from_holoverse_child_gateway():
        _write_child_block_report()
        raise SystemExit(0)
    runpy.run_path(str(MAIN), run_name="__main__")
