#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "tools" / "validate_holoutopia_capsule_contract.py"
raise SystemExit(subprocess.call([sys.executable, str(SCRIPT)]))
