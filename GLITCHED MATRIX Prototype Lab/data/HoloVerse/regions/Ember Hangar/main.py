#!/usr/bin/env python3
"""Ember Hangar dimension entry.

This folder owns the active runtime for Ember Hangar. HoloVerse mounts
`runtime.py` inside the live DESERT region through the shared in-world
route; it does not bounce through a root-level runtime file or launch a second app.
"""
from __future__ import annotations

from pathlib import Path

DIMENSION_ID = 'ember_hangar'
DIMENSION_NAME = 'Ember Hangar'
BOT_OWNER = 'Ember'
REGION_OWNER = 'DESERT'
LAUNCH_TYPE = "in_world_region"
RUNTIME_FILE = "runtime.py"


def runtime_path() -> Path:
    return Path(__file__).resolve().with_name(RUNTIME_FILE)


def main() -> None:
    path = runtime_path()
    status = "ready" if path.exists() else "missing runtime.py"
    print(f"{DIMENSION_NAME} is a {LAUNCH_TYPE} runtime owned by {BOT_OWNER} in {REGION_OWNER}: {status}")


if __name__ == "__main__":
    main()
