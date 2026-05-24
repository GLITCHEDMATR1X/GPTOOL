from __future__ import annotations

"""Keeps standalone Holo Conquest cwd-relative output under assets."""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SAFE_CWD = ROOT / "assets"

try:
    SAFE_CWD.mkdir(parents=True, exist_ok=True)
    if str(os.environ.get("HOLO_CONQUEST_KEEP_LAUNCH_CWD", "")).strip().lower() not in {"1", "true", "yes", "on"}:
        os.chdir(os.fspath(SAFE_CWD))
except Exception:
    pass
