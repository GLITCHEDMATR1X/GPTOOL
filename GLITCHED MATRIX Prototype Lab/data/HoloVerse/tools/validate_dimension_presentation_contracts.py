#!/usr/bin/env python3
"""Validate presentation-facing native artifact UI/return contracts.

This validator is static and intentionally does not launch Panda3D, create
windows, take screenshots, or write logs.  It checks the rules that matter for
presentation cleanup:
- native artifacts must advertise ESC / 0 return to HoloVerse, not Core/quit;
- non-Zonez native dimensions default legacy/source UI hidden and expose H toggle;
- Zonez is explicitly excluded from default hidden legacy UI because its UI is
  part of the game mode;
- Holo Campaign must not carry Etch-Line copy/paste status text.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "Dimensions" / "dimension_index.json"
ZONEZ_ID = "zonez"


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except Exception:
        return path.as_posix()


def _status_line(text: str) -> str:
    match = re.search(r'^\s*MODE_STATUS\s*=\s*(["\'])(.*?)\1', text, re.MULTILINE)
    return match.group(2) if match else ""


def _native_adapter_path(dim: dict[str, Any]) -> Path:
    folder = ROOT / str(dim.get("folder", "")).replace("\\", "/")
    manifest = _read_json(folder / "holoverse_mode_manifest.json")
    name = str(dim.get("native_adapter") or manifest.get("native_adapter") or "holoverse_native_adapter.py")
    return folder / name


def main() -> int:
    payload = _read_json(INDEX)
    dimensions = payload.get("dimensions") if isinstance(payload.get("dimensions"), dict) else {}
    errors: list[str] = []
    warnings: list[str] = []
    checked: list[dict[str, Any]] = []

    for dim_id, raw in sorted(dimensions.items()):
        dim = raw if isinstance(raw, dict) else {}
        launch_type = str(dim.get("launch_type") or "")
        if launch_type != "native_panda":
            continue
        name = str(dim.get("name") or dim_id)
        adapter = _native_adapter_path(dim)
        item = {"id": dim_id, "name": name, "adapter": _rel(adapter), "ok": True, "issues": []}
        if not adapter.exists():
            item["issues"].append("adapter-missing")
        else:
            text = adapter.read_text(encoding="utf-8", errors="replace")
            status = _status_line(text)
            item["mode_status"] = status
            status_upper = status.upper()
            if "RETURN TO HOLOVERSE" not in status_upper:
                item["issues"].append("mode-status-missing-return-to-holoverse")
            if "RETURN TO CORE" in status_upper or "QUIT" in status_upper or "FULLSCREEN" in status_upper:
                item["issues"].append("mode-status-contains-misleading-core-quit-fullscreen-text")
            if dim_id == "holo_campaign" and "ETCH" in status_upper:
                item["issues"].append("holo-campaign-status-copied-from-etchline")
            if dim_id == ZONEZ_ID:
                if "GAME UI ALWAYS VISIBLE" not in status_upper:
                    item["issues"].append("zonez-must-state-game-ui-always-visible")
            else:
                if "dimension_ui_visible = False" not in text:
                    item["issues"].append("legacy-dimension-ui-not-default-hidden")
                if "toggle_dimension_ui" not in text:
                    item["issues"].append("h-toggle-handler-missing")
                if "H SHOWS LEGACY UI" not in status_upper:
                    item["issues"].append("mode-status-missing-h-legacy-ui-hint")
        item["ok"] = not item["issues"]
        if item["issues"]:
            errors.append(f"{name}: " + ", ".join(item["issues"]))
        checked.append(item)

    report = {
        "schema": 1,
        "kind": "dimension_presentation_contract_validation",
        "native_dimensions_checked": len(checked),
        "ok_count": sum(1 for item in checked if item["ok"]),
        "errors": errors,
        "warnings": warnings,
        "ok": not errors,
        "dimensions": checked,
    }
    print(json.dumps(report, indent=2), flush=True)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
