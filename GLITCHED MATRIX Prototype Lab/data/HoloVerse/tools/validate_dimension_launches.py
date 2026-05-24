#!/usr/bin/env python3
"""Validate active HoloVerse dimension launch contracts without stale child-window probes.

Pass 74 retires the old hosted/embedded subprocess smoke path for native
artifact routes.  The active presentation contract is:
- native_panda artifacts must have a source entry plus holoverse_native_adapter.py
  with create_mode() or HoloVerseNativeMode.
- HoloCore remains the only same_window_mode exception.
- in_world_region routes validate their runtime installer statically.

This tool is intentionally static by default so running it does not recreate
logs, child windows, wrapper processes, screenshots, or stale diagnostics.
Set HOLOVERSE_WRITE_VALIDATION_REPORTS=1 to also write the JSON report to logs/.
"""
from __future__ import annotations

import ast
import json
import os
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "Dimensions" / "dimension_index.json"


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _norm_path(value: object) -> Path:
    text = str(value or "").replace("\\", "/").strip()
    return (ROOT / text).resolve() if text else ROOT.resolve()


def _rel(path: Path) -> str:
    try:
        return os.fspath(path.resolve().relative_to(ROOT.resolve()))
    except Exception:
        return os.fspath(path)


def _parse_file(path: Path) -> tuple[bool, str, ast.Module | None]:
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source, filename=os.fspath(path))
        compile(tree, os.fspath(path), "exec")
        return True, "", tree
    except SyntaxError as exc:
        return False, f"SyntaxError:{exc.msg}:line{exc.lineno}", None
    except Exception as exc:
        return False, f"{exc.__class__.__name__}:{exc}", None


def _defines_function(tree: ast.Module | None, name: str) -> bool:
    if tree is None:
        return False
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return True
    return False


def _defines_class(tree: ast.Module | None, name: str) -> bool:
    if tree is None:
        return False
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == name:
            return True
    return False


def _record_issue(item: dict[str, Any], issue: str) -> None:
    item.setdefault("issues", []).append(issue)


def main() -> int:
    payload = _read_json(INDEX)
    dimensions = payload.get("dimensions") if isinstance(payload.get("dimensions"), dict) else {}
    errors: list[str] = []
    warnings: list[str] = []
    records: list[dict[str, Any]] = []
    counts = {
        "dimensions": 0,
        "in_world_region": 0,
        "native_panda": 0,
        "same_window_mode_holocore": 0,
        "embedded_external": 0,
        "placeholder_mode": 0,
    }

    for dim_id, raw in sorted(dimensions.items()):
        record = raw if isinstance(raw, dict) else {}
        name = str(record.get("name") or record.get("title") or dim_id)
        folder = _norm_path(record.get("folder"))
        manifest_path = folder / "holoverse_mode_manifest.json"
        manifest = _read_json(manifest_path)
        launch_type = str(record.get("launch_type") or manifest.get("launch_type") or "").strip()
        entry_value = record.get("entry") or (str(record.get("folder") or "") + "/" + str(manifest.get("entry") or "main.py"))
        entry = _norm_path(entry_value)
        item: dict[str, Any] = {
            "id": dim_id,
            "name": name,
            "launch_type": launch_type,
            "folder": _rel(folder),
            "manifest": _rel(manifest_path),
            "entry": _rel(entry),
            "ok": True,
            "issues": [],
        }
        counts["dimensions"] += 1
        if launch_type in counts:
            counts[launch_type] += 1
        elif launch_type == "same_window_mode" and dim_id == "holocore":
            counts["same_window_mode_holocore"] += 1

        if not folder.exists():
            _record_issue(item, "folder-missing")
        if not manifest_path.exists():
            _record_issue(item, "manifest-missing")
        if not entry.exists():
            _record_issue(item, "entry-missing")
        elif entry.suffix.lower() == ".py":
            ok, issue, _tree = _parse_file(entry)
            if not ok:
                _record_issue(item, f"entry-parse:{issue}")

        if launch_type == "native_panda":
            adapter_name = str(record.get("native_adapter") or manifest.get("native_adapter") or "holoverse_native_adapter.py").strip() or "holoverse_native_adapter.py"
            adapter = folder / adapter_name
            item["adapter"] = _rel(adapter)
            if not adapter.exists():
                _record_issue(item, "native-adapter-missing")
            else:
                ok, issue, tree = _parse_file(adapter)
                if not ok:
                    _record_issue(item, f"native-adapter-parse:{issue}")
                elif not (_defines_function(tree, "create_mode") or _defines_class(tree, "HoloVerseNativeMode")):
                    _record_issue(item, "native-adapter-factory-missing")
            if str(manifest.get("launch_type") or launch_type).strip() != "native_panda":
                _record_issue(item, "manifest-launch-type-not-native-panda")
            if str(record.get("preferred_display") or manifest.get("preferred_display") or "").strip() != "same_window_native":
                warnings.append(f"{name}: preferred_display is not same_window_native")

        elif launch_type == "same_window_mode":
            if dim_id != "holocore":
                _record_issue(item, "retired-same-window-route")
            if not bool(manifest.get("same_window_only") or manifest.get("forbid_child_process")):
                _record_issue(item, "holocore-must-forbid-child-process")

        elif launch_type == "in_world_region":
            runtime = _norm_path(record.get("runtime") or (str(record.get("folder") or "") + "/" + str(manifest.get("runtime") or "runtime.py")))
            installer = str(record.get("runtime_installer") or manifest.get("runtime_installer") or "").strip()
            item["runtime"] = _rel(runtime)
            item["runtime_installer"] = installer
            if not runtime.exists():
                _record_issue(item, "runtime-missing")
            else:
                ok, issue, tree = _parse_file(runtime)
                if not ok:
                    _record_issue(item, f"runtime-parse:{issue}")
                elif installer and not _defines_function(tree, installer):
                    _record_issue(item, "runtime-installer-missing-from-file")
            if not installer:
                _record_issue(item, "runtime-installer-missing")

        elif launch_type == "embedded_external":
            # Vector Wars is the one deliberate exception: its real source is a
            # large pygame main.py. Until that code is fully ported to Panda3D,
            # presentation safety means launching the real source through the
            # Windows embedded-child route instead of showing a placeholder-like
            # Panda3D approximation.
            if dim_id == "vector_wars" and bool(manifest.get("pass87_real_main_py_route")):
                item["embedded_child_full_source"] = True
            else:
                _record_issue(item, "embedded-external-not-presentation-safe")

        elif launch_type == "placeholder_mode":
            _record_issue(item, "placeholder-mode-not-presentation-safe")

        elif launch_type:
            warnings.append(f"{name}: unrecognized launch_type {launch_type!r}")
        else:
            _record_issue(item, "launch-type-missing")

        item["ok"] = not item["issues"]
        if item["issues"]:
            errors.append(f"{name}: " + ", ".join(item["issues"]))
        records.append(item)

    report = {
        "schema": 2,
        "kind": "holoverse_dimension_launch_contract_validation",
        "index": _rel(INDEX),
        "counts": counts,
        "ok_count": sum(1 for item in records if item.get("ok")),
        "errors": errors,
        "warnings": warnings,
        "ok": not errors,
        "dimensions": records,
    }
    if str(os.environ.get("HOLOVERSE_WRITE_VALIDATION_REPORTS", "")).strip().lower() in {"1", "true", "yes", "on"}:
        report_path = ROOT / "logs" / "dimension_launch_validation_report.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2), flush=True)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
