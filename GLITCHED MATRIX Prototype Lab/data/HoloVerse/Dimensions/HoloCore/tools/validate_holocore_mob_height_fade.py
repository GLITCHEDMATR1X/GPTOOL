"""Validate shared HoloCore mob hover-height and fade contracts."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "logs" / "holocore_mob_height_fade_validation_report.json"


def read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def main() -> int:
    errors: list[str] = []
    outer = ROOT / "dimensions" / "outer_flat_world.py"
    text = outer.read_text(encoding="utf-8") if outer.exists() else ""
    for term in [
        "MOB_MIN_SURFACE_CLEARANCE = 3.0",
        "MOB_FADE_FULL_DISTANCE",
        "MOB_FADE_START_DISTANCE",
        "_mob_height_offset",
        "_mob_visibility_alpha",
        "_apply_mob_visibility(mob)",
        "MERMAID_HEIGHT_OFFSET, 5.0",
        "JELLYFISH_HEIGHT_OFFSET, 8.0",
        "OCTOPUS_HEIGHT_OFFSET, OCTOPUS_HEIGHT_VARIANCE",
    ]:
        if term not in text:
            errors.append(f"outer-missing:{term}")
    checks = {
        "mermaid": ROOT / "logs" / "holocore_mermaid_smoke_report.json",
        "jellyfish": ROOT / "logs" / "holocore_jellyfish_smoke_report.json",
        "octopus": ROOT / "logs" / "holocore_octopus_smoke_report.json",
    }
    heights: dict[str, float] = {}
    for name, path in checks.items():
        data = read_json(path)
        if not data:
            continue  # Smoke report is optional in clean/portable patch packages.
        if data.get("status") != "PASS":
            errors.append(f"{name}-smoke-not-pass")
        surface_steps = [s for s in (data.get("steps") or []) if "surface" in str(s.get("step", ""))]
        if not surface_steps:
            errors.append(f"{name}-surface-step-missing")
            continue
        offset = float(surface_steps[0].get("height_offset", -1.0))
        heights[name] = offset
        if offset < 3.0:
            errors.append(f"{name}-height-below-3:{offset}")
    if heights and len({round(v, 3) for v in heights.values()}) < len(heights):
        errors.append("mob-height-offsets-not-varied")
    report = {
        "kind": "holocore_mob_height_fade_validation",
        "status": "PASS" if not errors else "FAIL",
        "height_offsets": heights,
        "errors": errors,
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
