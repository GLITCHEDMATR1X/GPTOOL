"""Hosted HoloVerse entry stub for VECTOR WARS."""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from holoverse_hosted_entry import run_hosted_entry


if __name__ == "__main__":
    run_hosted_entry(Path(__file__).resolve().parent, "VECTOR WARS")
