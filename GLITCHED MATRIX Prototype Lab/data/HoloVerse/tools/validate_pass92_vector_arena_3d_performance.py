#!/usr/bin/env python3
"""Validate Pass 92 Vector Arena route/performance contracts without launching Panda3D."""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIM = ROOT / "Dimensions"


def read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def j(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def literal_constant(source: str, name: str, default=None):
    try:
        tree = ast.parse(source)
    except Exception:
        return default
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    try:
                        return ast.literal_eval(node.value)
                    except Exception:
                        return default
    return default


def main() -> int:
    errors: list[str] = []
    warnings: list[str] = []
    index = j(DIM / "dimension_index.json")
    dims = index.get("dimensions") if isinstance(index.get("dimensions"), dict) else {}
    routes_text = read(ROOT / "main.py")
    arena = dims.get("vector_arena") if isinstance(dims.get("vector_arena"), dict) else {}
    manifest = j(DIM / "Vector Arena" / "holoverse_mode_manifest.json")
    adapter_path = DIM / "Vector Arena" / "holoverse_native_adapter.py"
    adapter = read(adapter_path)

    if "holoutopia" in routes_text.lower():
        warnings.append("main.py still mentions HoloUtopia only in cleanup/comment context; verify no active route")
    if "\"holoutopia\"" in routes_text.lower() or "'holoutopia'" in routes_text.lower():
        errors.append("main.py still has an active holoutopia route literal")
    if "etch_line" in dims:
        errors.append("dimension_index still contains missing etch_line route")
    if not arena:
        errors.append("dimension_index missing vector_arena")
    else:
        if arena.get("launch_type") != "native_panda":
            errors.append("vector_arena must be native_panda")
        folder_norm = str(arena.get("folder") or "").replace("\\", "/")
        if folder_norm != "Dimensions/Vector Arena":
            errors.append("vector_arena folder mismatch")
        if arena.get("native_adapter") != "holoverse_native_adapter.py":
            errors.append("vector_arena native adapter mismatch")
        if arena.get("placeholder_mode"):
            errors.append("vector_arena must not be placeholder_mode")
    if not adapter_path.exists():
        errors.append("Vector Arena native adapter missing")
    if manifest.get("id") != "vector_arena" or manifest.get("launch_type") != "native_panda":
        errors.append("Vector Arena manifest id/launch_type invalid")
    perf = manifest.get("performance_contract") if isinstance(manifest.get("performance_contract"), dict) else {}
    if int(perf.get("enemy_cap", 0) or 0) > 24:
        errors.append("enemy cap too high for built-in arena pass")
    if int(perf.get("projectile_pool", 0) or 0) < 32:
        errors.append("projectile pool missing/too small")
    if not bool(perf.get("ui_default_hidden")):
        errors.append("Vector Arena UI should default hidden for presentation contract")

    enemy_cap = literal_constant(adapter, "ENEMY_CAP", 0)
    projectile_cap = literal_constant(adapter, "PROJECTILE_CAP", 0)
    impact_cap = literal_constant(adapter, "IMPACT_CAP", 0)
    if not (8 <= int(enemy_cap or 0) <= 24):
        errors.append(f"unexpected ENEMY_CAP={enemy_cap!r}")
    if not (32 <= int(projectile_cap or 0) <= 96):
        errors.append(f"unexpected PROJECTILE_CAP={projectile_cap!r}")
    if not (16 <= int(impact_cap or 0) <= 64):
        errors.append(f"unexpected IMPACT_CAP={impact_cap!r}")
    for required in ("_build_projectile_pool", "_build_enemy_pool", "_update_projectiles", "get_result", "toggle_dimension_ui"):
        if f"def {required}" not in adapter:
            errors.append(f"adapter missing {required}")
    if "LineSegs" not in adapter or "CardMaker" not in adapter:
        errors.append("adapter should use lightweight Panda3D geometry primitives")
    if re.search(r"append\(_Projectile\(|append\(_Impact\(", adapter.split("def _build_projectile_pool", 1)[-1].split("def _build_hud", 1)[0]) is None:
        errors.append("projectile/impact pools not built in setup section")
    # HoloUtopia is allowed as a sorted native dimension/source folder. Vector
    # Arena still owns its artifact slot; the presence of HoloUtopia is not a
    # Vector Arena performance regression as long as it is not a placeholder.
    holoutopia = dims.get("holoutopia") if isinstance(dims.get("holoutopia"), dict) else {}
    if holoutopia and holoutopia.get("placeholder_mode"):
        errors.append("HoloUtopia route exists as a placeholder")

    report = {
        "schema": 1,
        "kind": "pass92_vector_arena_3d_performance_validation",
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "enemy_cap": enemy_cap,
        "projectile_cap": projectile_cap,
        "impact_cap": impact_cap,
        "route": arena,
    }
    print(json.dumps(report, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
