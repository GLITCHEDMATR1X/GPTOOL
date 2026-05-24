#!/usr/bin/env python3
"""Validate HoloUtopia's GPTOOL app-capsule integration contract."""
from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIM_ROOT = ROOT / "Dimensions" / "HoloUtopia"
INDEX = ROOT / "Dimensions" / "dimension_index.json"
APP_MANIFEST = DIM_ROOT / "app_manifest.json"
MODE_MANIFEST = DIM_ROOT / "holoverse_mode_manifest.json"
CAPSULE = DIM_ROOT / "capsule.py"
ADAPTER = DIM_ROOT / "holoverse_native_adapter.py"


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


def parse(path: Path) -> ast.Module | None:
    try:
        return ast.parse(path.read_text(encoding="utf-8", errors="replace"), filename=str(path))
    except Exception:
        return None


def top_classes(tree: ast.Module | None) -> set[str]:
    return {node.name for node in (tree.body if tree else []) if isinstance(node, ast.ClassDef)}


def class_methods(tree: ast.Module | None, class_name: str) -> set[str]:
    for node in (tree.body if tree else []):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return {child.name for child in node.body if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))}
    return set()


def top_functions(tree: ast.Module | None) -> set[str]:
    return {node.name for node in (tree.body if tree else []) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}


def main() -> int:
    errors: list[str] = []
    warnings: list[str] = []
    index = j(INDEX)
    dims = index.get("dimensions") if isinstance(index.get("dimensions"), dict) else {}
    rec = dims.get("holoutopia") if isinstance(dims.get("holoutopia"), dict) else {}
    app = j(APP_MANIFEST)
    mode = j(MODE_MANIFEST)
    cap_text = read(CAPSULE)
    adapter_text = read(ADAPTER)
    cap_tree = parse(CAPSULE)
    adapter_tree = parse(ADAPTER)

    for path, label in ((APP_MANIFEST, "app_manifest"), (CAPSULE, "capsule"), (ADAPTER, "adapter"), (MODE_MANIFEST, "mode_manifest")):
        if not path.exists():
            errors.append(f"missing-{label}:{path.relative_to(ROOT).as_posix()}")

    if rec.get("launch_type") != "native_panda":
        errors.append("dimension_index holoutopia must remain native_panda")
    if rec.get("source_kind") != "app_capsule_panda3d_same_window_life_sim":
        errors.append("dimension_index holoutopia source_kind must identify app capsule life sim")
    if rec.get("adapter_kind") != "thin_capsule_translator":
        errors.append("dimension_index holoutopia adapter_kind must be thin_capsule_translator")
    if rec.get("capsule_entry") != "capsule.py":
        errors.append("dimension_index holoutopia capsule_entry must be capsule.py")
    if rec.get("placeholder_mode") is not False:
        errors.append("HoloUtopia capsule route must not be placeholder")

    if app.get("schema") != "app_capsule.v1":
        errors.append("app_manifest schema must be app_capsule.v1")
    if app.get("id") != "holoutopia":
        errors.append("app_manifest id must be holoutopia")
    if app.get("kind") != "panda3d_same_window":
        errors.append("app_manifest kind must be panda3d_same_window")
    if app.get("entry") != "capsule.py":
        errors.append("app_manifest entry must be capsule.py")
    contract = app.get("contract") if isinstance(app.get("contract"), dict) else {}
    lifecycle = set(contract.get("lifecycle") or [])
    for required in ("prepare", "enter", "update", "exit", "cleanup", "get_result"):
        if required not in lifecycle:
            errors.append(f"app_manifest lifecycle missing {required}")

    if mode.get("app_capsule_entry") != "capsule.py":
        errors.append("holoverse_mode_manifest must point to capsule.py")
    if mode.get("adapter_kind") != "thin_capsule_translator":
        errors.append("holoverse_mode_manifest adapter_kind must be thin_capsule_translator")
    if "app_capsule" not in str(mode.get("host_contract") or ""):
        errors.append("holoverse_mode_manifest host_contract must identify app capsule")

    if "HoloUtopiaCapsule" not in top_classes(cap_tree):
        errors.append("capsule.py missing HoloUtopiaCapsule class")
    methods = class_methods(cap_tree, "HoloUtopiaCapsule")
    for required in ("prepare", "enter", "update", "exit", "cleanup", "get_result"):
        if required not in methods:
            errors.append(f"HoloUtopiaCapsule missing {required}()")
    if "create_capsule" not in top_functions(cap_tree):
        errors.append("capsule.py missing create_capsule()")
    for forbidden in ("ShowBase(", "subprocess", "runpy", "pygame.display.set_mode", "pygame.event.get", "sys.exit"):
        if forbidden in cap_text:
            errors.append(f"capsule.py contains forbidden owner behavior: {forbidden}")
    if "install_holoutopia_runtime" not in cap_text:
        errors.append("capsule.py must install the authored HoloUtopia runtime")

    if "HoloVerseNativeMode" not in top_classes(adapter_tree):
        errors.append("adapter missing HoloVerseNativeMode")
    if "create_mode" not in top_functions(adapter_tree):
        errors.append("adapter missing create_mode")
    if "from capsule import create_capsule" not in adapter_text:
        errors.append("adapter must delegate through capsule.create_capsule")
    if "install_holoutopia_runtime" in adapter_text:
        errors.append("adapter should not install HoloUtopia runtime directly")
    if len(adapter_text.splitlines()) > 150:
        errors.append("adapter should remain thin; too many lines")
    for marker in ("MODE_STATUS", "RETURN TO HOLOVERSE", "H SHOWS LEGACY UI", "dimension_ui_visible = False", "toggle_dimension_ui"):
        if marker not in adapter_text:
            errors.append(f"adapter missing presentation marker {marker}")

    cleanup_text = read(ROOT / "APPLY_PATCH_GATE_CLEANUP.bat") + "\n" + read(ROOT / "apply_PASS92_VectorArena_cleanup.ps1")
    if "Dimensions\\HoloUtopia" in cleanup_text or "Dimensions/HoloUtopia" in cleanup_text:
        errors.append("cleanup scripts must not remove HoloUtopia capsule")

    result = {
        "schema": 1,
        "kind": "holoutopia_capsule_contract_validation",
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "adapter_lines": len(adapter_text.splitlines()),
        "capsule_methods": sorted(methods),
        "dimension_source_kind": rec.get("source_kind"),
    }
    print(json.dumps(result, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
