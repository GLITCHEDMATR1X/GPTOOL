#!/usr/bin/env python3
"""Validate that default HoloVerse terrain is owned by world.py, not main.py.

The root main.py still contains legacy artifact-world terrain code, but that
code must be gated so the default world.py biome terrain does not stack with a
second main.py terrain during normal play.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
WORLD = ROOT / "world.py"
MOUNT = ROOT / "holoverse_world_shell_mount.py"


def methods_for_class(path: Path, class_name: str) -> dict[str, ast.FunctionDef]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return {item.name: item for item in node.body if isinstance(item, ast.FunctionDef)}
    return {}


def method_source(path: Path, method: ast.FunctionDef) -> str:
    lines = path.read_text(encoding="utf-8").splitlines()
    return "\n".join(lines[method.lineno - 1 : method.end_lineno or method.lineno])


def main() -> int:
    errors: list[str] = []
    warnings: list[str] = []

    if not MAIN.exists():
        errors.append("main.py missing")
    if not WORLD.exists():
        errors.append("world.py missing")
    if not MOUNT.exists():
        errors.append("holoverse_world_shell_mount.py missing")
    if errors:
        print(json.dumps({"status": "FAIL", "errors": errors}, indent=2))
        return 1

    main_methods = methods_for_class(MAIN, "CommandHubApp")
    world_methods = methods_for_class(WORLD, "CommandHubApp")
    required_main_guards = [
        "world_py_source_active",
        "legacy_world_chunks_active",
        "should_stream_legacy_world_chunks",
        "update_world_chunks",
    ]
    for name in required_main_guards:
        if name not in main_methods:
            errors.append(f"main.py CommandHubApp.{name} missing")

    for name in ("build_biome_terrain_chunk", "update_world_chunks", "audit_surface_authority"):
        if name not in world_methods:
            errors.append(f"world.py CommandHubApp.{name} missing")

    if "update_world_chunks" in main_methods:
        src = method_source(MAIN, main_methods["update_world_chunks"])
        if "should_stream_legacy_world_chunks" not in src:
            errors.append("main.py update_world_chunks is not gated by should_stream_legacy_world_chunks")
        if "normal HoloVerse terrain is owned by world.py" not in src:
            warnings.append("main.py update_world_chunks lacks single-authority comment")

    main_src = MAIN.read_text(encoding="utf-8")
    if "self.mount_world_shell_adapter()\n        self.update_world_chunks(force=True)" in main_src:
        errors.append("rebuild_station still force-builds main.py terrain immediately after mounting world.py shell")
    if "self.update_player(dt)\n        self.update_world_chunks()\n        self.update_world_shell_mount(dt)" in main_src:
        errors.append("main loop still streams main.py terrain unconditionally before shell update")
    if "if self.should_stream_legacy_world_chunks():\n            self.update_world_chunks()" not in main_src:
        errors.append("main loop does not gate update_world_chunks with should_stream_legacy_world_chunks")

    mount_src = MOUNT.read_text(encoding="utf-8")
    if "if self.try_build_world_py_source_bridge():\n            return" not in mount_src:
        errors.append("world shell mount does not return immediately after world.py source bridge succeeds")
    if "SINGLE SOURCE WORLD.PY AUTHORITY" not in mount_src:
        warnings.append("world shell mount lacks explicit single-source world.py status")

    # Redundant names are allowed only as legacy gated helpers in main.py. Report them.
    duplicate_world_names = sorted(
        set(main_methods).intersection(world_methods).intersection(
            {
                "terrain_height_at",
                "current_world_spec",
                "chunk_axis_positions",
                "clear_world_actors",
                "clear_world_chunks",
                "apply_world_theme",
                "world_height_at",
                "add_world_actor",
                "create_world_chunk",
                "update_world_chunks",
                "adjust_terrain_height",
                "adjust_background",
                "update_world_actors",
            }
        )
    )

    result = {
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "warnings": warnings,
        "world_py_default_authority": True,
        "legacy_main_world_helpers_gated": not errors,
        "duplicate_world_method_names_kept_as_legacy_artifact_helpers": duplicate_world_names,
    }
    print(json.dumps(result, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
