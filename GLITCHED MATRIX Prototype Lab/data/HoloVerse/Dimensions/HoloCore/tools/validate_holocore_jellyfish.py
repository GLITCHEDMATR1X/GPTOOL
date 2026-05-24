"""Validate the HoloCore sparse jellyfish mob import contract."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "logs" / "holocore_jellyfish_validation_report.json"


def main() -> int:
    errors: list[str] = []
    holo = ROOT / "assets" / "entities" / "holo_jellyfish.py"
    shim = ROOT / "holo_jellyfish.py"
    outer = ROOT / "dimensions" / "outer_flat_world.py"
    smoke = ROOT / "logs" / "holocore_jellyfish_smoke_report.json"
    holo_text = holo.read_text(encoding="utf-8", errors="ignore") if holo.exists() else ""
    outer_text = outer.read_text(encoding="utf-8", errors="ignore") if outer.exists() else ""
    main_text = (ROOT / "main.py").read_text(encoding="utf-8", errors="ignore")
    if not holo.exists():
        errors.append("assets/entities/holo_jellyfish.py-missing")
    if not shim.exists():
        errors.append("holo_jellyfish.py-compat-shim-missing")
    else:
        shim_text = shim.read_text(encoding="utf-8", errors="ignore")
        if "assets.entities.holo_jellyfish" not in shim_text:
            errors.append("holo_jellyfish.py-shim-not-routing-to-assets-entities")
    if not outer.exists():
        errors.append("outer_flat_world.py-missing")
    for term in [
        "class HoloJellyfishMob",
        "JELLYFISH_SPAWN_CHANCE = 0.20",
        "JELLYFISH_VARIANTS",
        "aqua_medium",
        "violet_small",
        "rose_large",
        "gold_tiny",
        "update_surface_lock",
        "make_bell",
        "make_ribbon",
        "rectangle/platform",
    ]:
        if term not in holo_text:
            errors.append(f"jellyfish-missing:{term}")
    for bad in ["landing_pad", "preview_floor", "rectangle_base"]:
        if bad in holo_text:
            errors.append(f"preview-debris-term-present:{bad}")
    for term in [
        "jellyfish_candidate_position",
        "_build_chunk_jellyfish",
        "update_jellyfish_mobs",
        "self._build_chunk_jellyfish(chunk_np, rect, (cx, cy))",
        "self.update_jellyfish_mobs(task.time, dt)",
    ]:
        if term not in outer_text:
            errors.append(f"outer-world-missing:{term}")
    for term in ["--jellyfish-smoke", "_jellyfish_smoke_setup", "HOLOCORE_JELLYFISH_REPORT"]:
        if term not in main_text:
            errors.append(f"main-missing:{term}")
    chance_match = re.search(r"JELLYFISH_SPAWN_CHANCE\s*=\s*(\d+(?:\.\d+)?)", holo_text)
    chance = float(chance_match.group(1)) if chance_match else -1.0
    if chance < 0.20:
        errors.append(f"spawn-chance-below-20-percent:{chance}")
    if smoke.exists():
        try:
            data = json.loads(smoke.read_text(encoding="utf-8"))
            if data.get("status") != "PASS":
                errors.append("jellyfish-smoke-not-pass")
            steps = data.get("steps") or []
            spawn_step = next((step for step in steps if str(step.get("step")) == "deterministic_variant_spawn"), None)
            if not spawn_step:
                errors.append("jellyfish-smoke-missing-spawn-step")
            else:
                if float(spawn_step.get("spawn_chance", 0.0) or 0.0) < 0.20:
                    errors.append("jellyfish-smoke-spawn-chance-below-20")
                if not bool(spawn_step.get("one_per_chunk", False)):
                    errors.append("jellyfish-smoke-not-one-per-chunk")
            if not any(str(step.get("step")) == "surface_locked_holo_jellyfish" for step in steps):
                errors.append("jellyfish-smoke-missing-surface-step")
        except Exception as exc:
            errors.append(f"jellyfish-smoke-json-error:{exc.__class__.__name__}:{exc}")
    else:
        pass  # Smoke report is optional in clean/portable patch packages.
    report = {
        "kind": "holocore_jellyfish_validation",
        "status": "PASS" if not errors else "FAIL",
        "spawn_chance": chance,
        "errors": errors,
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
