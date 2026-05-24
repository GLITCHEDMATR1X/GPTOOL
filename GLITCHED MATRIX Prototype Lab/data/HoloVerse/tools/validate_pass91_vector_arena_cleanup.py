#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

CHECK_FILES = [
    ROOT / "main.py",
    ROOT / "Dimensions" / "dimension_index.json",
    ROOT / "Dimensions" / "Vector Arena" / "holoverse_mode_manifest.json",
    ROOT / "Dimensions" / "Vector Arena" / "holoverse_native_adapter.py",
    ROOT / "progression" / "progression_state.json",
]

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

def main() -> int:
    errors: list[str] = []
    warnings: list[str] = []
    index = j(ROOT / "Dimensions" / "dimension_index.json")
    dims = index.get("dimensions") if isinstance(index.get("dimensions"), dict) else {}
    if "holoutopia" in dims:
        errors.append("dimension_index still contains holoutopia")
    if "vector_arena" not in dims:
        errors.append("dimension_index missing vector_arena")
    else:
        rec = dims.get("vector_arena") or {}
        if rec.get("launch_type") != "native_panda":
            errors.append("vector_arena launch_type must be native_panda")
        if rec.get("folder") != "Dimensions\\Vector Arena":
            errors.append("vector_arena folder must be Dimensions\\Vector Arena")
        if rec.get("placeholder_mode") is not False:
            errors.append("vector_arena must not be a placeholder")
    if (ROOT / "Dimensions" / "HoloUtopia").exists():
        errors.append("Dimensions/HoloUtopia folder still exists")
    manifest = j(ROOT / "Dimensions" / "Vector Arena" / "holoverse_mode_manifest.json")
    if manifest.get("id") != "vector_arena":
        errors.append("Vector Arena manifest id mismatch")
    if manifest.get("launch_type") != "native_panda":
        errors.append("Vector Arena manifest must be native_panda")
    adapter = read(ROOT / "Dimensions" / "Vector Arena" / "holoverse_native_adapter.py")
    for marker in ("MODE_ID = \"vector_arena\"", "ESC / 0 RETURN TO HOLOVERSE", "H SHOWS LEGACY UI", "dimension_ui_visible = False", "toggle_dimension_ui", "def create_mode"):
        if marker not in adapter:
            errors.append(f"Vector Arena adapter missing marker: {marker}")
    main_py = read(ROOT / "main.py")
    if '"vector_arena"' not in main_py or '"holoutopia"' in main_py:
        errors.append("main.py artifact route was not cleanly replaced")
    disallowed = []
    for path in CHECK_FILES:
        text = read(path)
        if "holoutopia" in text.lower() or "holoutopia" in path.as_posix().lower() or "HoloUtopia" in text:
            disallowed.append(path.relative_to(ROOT).as_posix())
    if disallowed:
        errors.append("HoloUtopia token remains in active route/state files: " + ", ".join(disallowed))
    for log_name in ("latest.log", "mode_gateway_audit.json", "mode_gateway_history.json"):
        if (ROOT / "logs" / log_name).exists():
            errors.append(f"runtime log was not cleaned: logs/{log_name}")
    report = {"schema": 1, "kind": "pass91_vector_arena_cleanup", "ok": not errors, "errors": errors, "warnings": warnings}
    print(json.dumps(report, indent=2))
    return 0 if not errors else 1

if __name__ == "__main__":
    raise SystemExit(main())
