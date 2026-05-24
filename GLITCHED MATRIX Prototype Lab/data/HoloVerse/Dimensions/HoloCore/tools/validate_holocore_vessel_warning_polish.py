"""Static validator for HoloCore vessel ascent readability polish."""
from __future__ import annotations
from pathlib import Path
import re
ROOT = Path(__file__).resolve().parents[1]
main = (ROOT / "main.py").read_text(encoding="utf-8")
vessel = (ROOT / "assets/entities/holo_vessel.py").read_text(encoding="utf-8")
errors: list[str] = []
for token in (
    "_setup_holocore_threat_warning",
    "_update_holocore_threat_warning",
    "PROXIMITY WARNING",
    "SONAR CONTACT",
    "DISTANT MASS",
    "_update_holo_vessel_pilot_camera",
    "HOLOCORE IMPACT",
    "HOLOCORE RECOVERY",
):
    if token not in main:
        errors.append(f"missing-main-token:{token}")
for token in (
    "forward_velocity",
    "vertical_velocity",
    "turn_velocity",
    "bank_angle",
    "pitch_angle",
    "reset_motion",
    "math.exp(-response * dt)",
):
    if token not in vessel:
        errors.append(f"missing-vessel-token:{token}")
if main.count("OnscreenText(") < 3:
    errors.append("threat-warning-onscreentext-not-added")
if "self._update_holocore_threat_warning(dt)" not in main:
    errors.append("threat-warning-not-updated-in-world-loop")
if "threat_warning_visible" not in main or "threat_warning_text" not in main:
    errors.append("vertical-smoke-does-not-report-warning-state")
if errors:
    print("FAIL validate_holocore_vessel_warning_polish")
    for err in errors:
        print(err)
    raise SystemExit(1)
print("PASS validate_holocore_vessel_warning_polish")
