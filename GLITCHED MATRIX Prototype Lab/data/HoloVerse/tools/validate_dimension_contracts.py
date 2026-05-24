"""Validate HoloVerse dimension runtime/emulation contracts without importing Panda3D.

This validator separates the supported dimension families:
- in_world_region dimensions must own a real runtime.py and installer.
- native_panda dimensions must own a source-backed same-window adapter.
- embedded_external legacy dimensions must own a real hosted entry file.

The old same_window_mode signal mini-surface is retired; any stale records
should normalize to embedded_external before play. HoloCore is the only
allowed same-window exception because it mounts as the root-level sub-world
inside the live HoloVerse display and forbids child-process fallback.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX_PATH = ROOT / "Dimensions" / "dimension_index.json"


def read_json(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def rel_path(value: object) -> Path | None:
    text = str(value or "").strip().replace("\\", "/")
    if not text:
        return None
    return ROOT / text


def main() -> int:
    payload = read_json(INDEX_PATH)
    dimensions = payload.get("dimensions") if isinstance(payload.get("dimensions"), dict) else {}
    errors: list[str] = []
    warnings: list[str] = []
    counters = {
        "dimensions": len(dimensions),
        "in_world_region": 0,
        "same_window_mode_holocore": 0,
        "same_window_mode_retired": 0,
        "native_panda": 0,
        "embedded_external": 0,
        "placeholder_mode": 0,
    }

    for dim_id, record in dimensions.items():
        if not isinstance(record, dict):
            errors.append(f"{dim_id}: record is not an object")
            continue
        launch_type = str(record.get("launch_type") or "").strip()
        if launch_type == "same_window_mode":
            if str(record.get("id") or dim_id).strip().lower() == "holocore":
                counters["same_window_mode_holocore"] += 1
            else:
                counters["same_window_mode_retired"] += 1
        elif launch_type in counters:
            counters[launch_type] += 1

        folder = rel_path(record.get("folder"))
        entry = rel_path(record.get("entry"))
        runtime = rel_path(record.get("runtime"))
        manifest_path = (folder / "holoverse_mode_manifest.json") if folder else None
        manifest = read_json(manifest_path) if manifest_path and manifest_path.exists() else {}

        if folder is None or not folder.exists():
            errors.append(f"{dim_id}: missing folder {record.get('folder')!r}")
            continue
        if manifest_path is None or not manifest_path.exists():
            warnings.append(f"{dim_id}: missing manifest")

        if launch_type == "in_world_region":
            if entry is None or not entry.exists():
                errors.append(f"{dim_id}: in-world sentinel entry missing {record.get('entry')!r}")
            if runtime is None or not runtime.exists():
                errors.append(f"{dim_id}: in-world runtime missing {record.get('runtime')!r}")
            if not str(record.get("runtime_installer") or "").strip():
                errors.append(f"{dim_id}: in-world runtime_installer missing")
            if runtime is not None and runtime.exists():
                text = runtime.read_text(encoding="utf-8", errors="ignore")
                installer = str(record.get("runtime_installer") or "").strip()
                if installer and f"def {installer}" not in text:
                    errors.append(f"{dim_id}: runtime.py does not define {installer}")
                if "install_in_world_route_aliases(main)" not in text:
                    warnings.append(f"{dim_id}: runtime.py does not call shared install_in_world_route_aliases")

        elif launch_type == "same_window_mode":
            is_holocore = str(record.get("id") or dim_id).strip().lower() == "holocore"
            manifest_same_window_only = bool(manifest.get("same_window_only", False) or manifest.get("forbid_child_process", False))
            if not is_holocore:
                errors.append(f"{dim_id}: retired same_window_mode route should be embedded_external")
            else:
                if entry is None or not entry.exists():
                    errors.append(f"{dim_id}: HoloCore same-window entry missing {record.get('entry')!r}")
                if not manifest_same_window_only:
                    errors.append(f"{dim_id}: HoloCore same-window route must forbid child-process fallback")
                folder_key = str(record.get("folder") or "").replace("\\", "/").strip("/").lower()
                if folder_key not in {"holocore", "dimensions/holocore"}:
                    errors.append(f"{dim_id}: HoloCore same-window folder must be HoloCore or Dimensions/HoloCore, got {record.get('folder')!r}")

        elif launch_type == "native_panda":
            if entry is None or not entry.exists():
                errors.append(f"{dim_id}: native source entry missing {record.get('entry')!r}")
            adapter_name = str(record.get("native_adapter") or manifest.get("native_adapter") or "holoverse_native_adapter.py").strip() or "holoverse_native_adapter.py"
            adapter = (folder / adapter_name) if folder else None
            if adapter is None or not adapter.exists():
                errors.append(f"{dim_id}: native adapter missing {adapter_name!r}")
            else:
                adapter_text = adapter.read_text(encoding="utf-8", errors="ignore")
                if "def create_mode" not in adapter_text and "class HoloVerseNativeMode" not in adapter_text:
                    errors.append(f"{dim_id}: native adapter lacks create_mode or HoloVerseNativeMode")
                if "placeholder" in adapter_text.lower() and "do not" not in adapter_text.lower():
                    warnings.append(f"{dim_id}: native adapter mentions placeholder; verify it is not a generated shell")

        elif launch_type == "embedded_external":
            if entry is None or not entry.exists():
                errors.append(f"{dim_id}: embedded entry missing {record.get('entry')!r}")
            elif entry.name == "holoverse_entry.py":
                entry_text = entry.read_text(encoding="utf-8", errors="ignore")
                if "run_hosted_entry" not in entry_text:
                    errors.append(f"{dim_id}: embedded hosted entry does not call shared run_hosted_entry")

        elif launch_type == "placeholder_mode":
            if not bool(record.get("placeholder_mode", False)):
                errors.append(f"{dim_id}: placeholder launch_type without placeholder_mode=true")
        else:
            warnings.append(f"{dim_id}: unrecognized launch_type {launch_type!r}")

    result = {
        "index": str(INDEX_PATH),
        "counts": counters,
        "errors": errors,
        "warnings": warnings,
        "ok": not errors,
    }
    print(json.dumps(result, indent=2))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
