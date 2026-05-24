#!/usr/bin/env python3
"""Urban Warzone dimension entry.

This folder owns the active runtime for Urban Warzone. HoloVerse mounts
`runtime.py` inside the live URBAN region through the shared in-world
route. The former legacy arena design is salvaged through `arena_blueprint.py`,
so it becomes distributed in-world combat instead of a second app.
"""
from __future__ import annotations

from pathlib import Path

DIMENSION_ID = 'urban_warzone'
DIMENSION_NAME = 'Urban Warzone'
BOT_OWNER = 'Sable'
REGION_OWNER = 'URBAN'
LAUNCH_TYPE = "in_world_region"
RUNTIME_FILE = "runtime.py"
BLUEPRINT_FILE = "arena_blueprint.py"


def runtime_path() -> Path:
    return Path(__file__).resolve().with_name(RUNTIME_FILE)


def main() -> None:
    path = runtime_path()
    blueprint = path.with_name(BLUEPRINT_FILE)
    status = "ready" if path.exists() and blueprint.exists() else "missing runtime.py or arena_blueprint.py"
    print(f"{DIMENSION_NAME} is a {LAUNCH_TYPE} runtime owned by {BOT_OWNER} in {REGION_OWNER}: {status}")


if __name__ == "__main__":
    main()
