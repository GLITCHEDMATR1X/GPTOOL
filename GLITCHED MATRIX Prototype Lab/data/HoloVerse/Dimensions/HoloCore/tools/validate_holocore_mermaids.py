"""Validate the HoloCore sparse mermaid mob import contract."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "logs" / "holocore_mermaid_validation_report.json"


def main() -> int:
    errors: list[str] = []
    holo = ROOT / "assets" / "entities" / "holo_mermaid.py"
    shim = ROOT / "holo_mermaid.py"
    outer = ROOT / "dimensions" / "outer_flat_world.py"
    smoke = ROOT / "logs" / "holocore_mermaid_smoke_report.json"
    holo_text = holo.read_text(encoding="utf-8", errors="ignore") if holo.exists() else ""
    outer_text = outer.read_text(encoding="utf-8", errors="ignore") if outer.exists() else ""
    if not holo.exists():
        errors.append("assets/entities/holo_mermaid.py-missing")
    if not shim.exists():
        errors.append("holo_mermaid.py-compat-shim-missing")
    else:
        shim_text = shim.read_text(encoding="utf-8", errors="ignore")
        if "assets.entities.holo_mermaid" not in shim_text:
            errors.append("holo_mermaid.py-shim-not-routing-to-assets-entities")
    if not outer.exists():
        errors.append("outer_flat_world.py-missing")
    for term in [
        "class HoloMermaidMob",
        "MERMAID_SPAWN_CHANCE = 0.10",
        "update_surface_lock",
        "make_ribbon_surface",
        "tail_crystal_segment",
        "rectangle/platform",
    ]:
        if term not in holo_text:
            errors.append(f"mermaid-missing:{term}")
    for bad in ["landing_pad", "preview_floor", "rectangle_base"]:
        if bad in holo_text:
            errors.append(f"preview-debris-term-present:{bad}")
    for term in [
        "mermaid_candidate_position",
        "_build_chunk_mermaid",
        "update_mermaid_mobs",
        "self._build_chunk_mermaid(chunk_np, rect, (cx, cy))",
        "self.update_mermaid_mobs(task.time, dt)",
    ]:
        if term not in outer_text:
            errors.append(f"outer-world-missing:{term}")
    chance_match = re.search(r"MERMAID_SPAWN_CHANCE\s*=\s*(\d+(?:\.\d+)?)", holo_text)
    chance = float(chance_match.group(1)) if chance_match else -1.0
    if abs(chance - 0.10) > 0.0001:
        errors.append(f"spawn-chance-not-10-percent:{chance}")
    if smoke.exists():
        try:
            data = json.loads(smoke.read_text(encoding="utf-8"))
            if data.get("status") != "PASS":
                errors.append("mermaid-smoke-not-pass")
            steps = data.get("steps") or []
            if not any(str(step.get("step")) == "deterministic_sparse_spawn" for step in steps):
                errors.append("mermaid-smoke-missing-spawn-step")
            if not any(str(step.get("step")) == "surface_locked_holo_mermaid" for step in steps):
                errors.append("mermaid-smoke-missing-surface-step")
        except Exception as exc:
            errors.append(f"mermaid-smoke-json-error:{exc.__class__.__name__}:{exc}")
    else:
        pass  # Smoke report is optional in clean/portable patch packages.
    report = {
        "kind": "holocore_mermaid_validation",
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
