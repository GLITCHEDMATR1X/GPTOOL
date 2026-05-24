"""Compatibility shim for assets.entities.holo_octopus.

The implementation moved to assets/entities/holo_octopus.py so HoloCore assets
are grouped under the asset folder. This shim preserves old HoloVerse adapter
imports such as from holo_octopus import ....
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from assets.entities.holo_octopus import *  # noqa: F401,F403,E402
