"""Validate the HoloCore rare fluid octopus mob import contract."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "logs" / "holocore_octopus_validation_report.json"


def main() -> int:
    errors: list[str] = []
    octo = ROOT / "assets" / "entities" / "holo_octopus.py"
    shim = ROOT / "holo_octopus.py"
    outer = ROOT / "dimensions" / "outer_flat_world.py"
    main_py = ROOT / "main.py"
    smoke = ROOT / "logs" / "holocore_octopus_smoke_report.json"
    for path in (octo, outer, main_py):
        if not path.exists():
            errors.append(f"missing:{path}")
    if not shim.exists():
        errors.append("holo_octopus.py-compat-shim-missing")
    else:
        shim_text = shim.read_text(encoding="utf-8", errors="ignore")
        if "assets.entities.holo_octopus" not in shim_text:
            errors.append("holo_octopus.py-shim-not-routing-to-assets-entities")
    octo_text = octo.read_text(encoding="utf-8") if octo.exists() else ""
    outer_text = outer.read_text(encoding="utf-8") if outer.exists() else ""
    main_text = main_py.read_text(encoding="utf-8") if main_py.exists() else ""
    for term in [
        "OCTOPUS_SPAWN_CHANCE = 0.03",
        "class HoloOctopusMob",
        "update_behavior",
        "curious_mermaid",
        "cautious_jellyfish",
        "camouflage",
        "set_visibility_alpha",
        "stable_octopus_seed",
    ]:
        if term not in octo_text:
            errors.append(f"octopus-missing:{term}")
    for term in [
        "octopus_mobs",
        "octopus_candidate_position",
        "_build_chunk_octopus",
        "update_octopus_mobs",
        "self._build_chunk_octopus(chunk_np, rect, (cx, cy))",
        "self.update_octopus_mobs(task.time, dt)",
        "MOB_MIN_SURFACE_CLEARANCE = 3.0",
        "MOB_FADE_START_DISTANCE",
        "_mob_visibility_alpha",
        "_mob_height_offset",
    ]:
        if term not in outer_text:
            errors.append(f"outer-missing:{term}")
    for term in ["--octopus-smoke", "_octopus_smoke_setup", "HOLOCORE_OCTOPUS_REPORT"]:
        if term not in main_text:
            errors.append(f"main-missing:{term}")
    if smoke.exists():
        try:
            data = json.loads(smoke.read_text(encoding="utf-8"))
            if data.get("status") != "PASS":
                errors.append("octopus-smoke-not-pass")
            steps = data.get("steps") or []
            spawn_steps = [step for step in steps if str(step.get("step")) == "deterministic_rare_spawn"]
            if not spawn_steps:
                errors.append("octopus-smoke-missing-spawn-step")
            else:
                step = spawn_steps[0]
                if float(step.get("spawn_chance", 1.0)) > 0.03:
                    errors.append("octopus-smoke-not-rare")
                if not bool(step.get("one_per_chunk")):
                    errors.append("octopus-smoke-not-one-per-chunk")
            surface_steps = [step for step in steps if str(step.get("step")) == "surface_locked_rare_holo_octopus"]
            if not surface_steps:
                errors.append("octopus-smoke-missing-surface-step")
            else:
                if float(surface_steps[0].get("height_offset", 0.0)) < 3.0:
                    errors.append("octopus-smoke-height-below-min")
            behavior_steps = [step for step in steps if str(step.get("step")) == "intelligent_neighbor_behavior"]
            if not behavior_steps:
                errors.append("octopus-smoke-missing-behavior-step")
            elif behavior_steps[0].get("curious_state") != "curious_mermaid" or behavior_steps[0].get("cautious_state") != "cautious_jellyfish":
                errors.append("octopus-smoke-behavior-state-mismatch")
        except Exception as exc:
            errors.append(f"octopus-smoke-json-error:{exc.__class__.__name__}:{exc}")
    else:
        pass  # Smoke report is optional in clean/portable patch packages.
    report = {
        "kind": "holocore_octopus_validation",
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
