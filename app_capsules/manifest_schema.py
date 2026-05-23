from __future__ import annotations
import json
from pathlib import Path
from typing import Any

CONTRACT = "app_capsule.v1"
ALLOWED_KINDS = {"panda3d_same_window", "panda3d_standalone", "pygame_legacy", "tkinter_tool", "subprocess_app", "data_module", "legacy_quarantine"}
REQUIRED_FIELDS = {"id": str, "title": str, "kind": str, "entry": str, "contract": str}
DEFAULT_OWNS = {"camera": False, "audio": False, "window": False, "mouse_lock": False, "ui_layer": True, "tasks": True}

def default_manifest(app_id: str, title: str, kind: str = "legacy_quarantine", entry: str = "capsule.py") -> dict[str, Any]:
    return {"id": app_id, "title": title, "kind": kind, "entry": entry, "contract": CONTRACT, "owns": dict(DEFAULT_OWNS), "exit_keys": ["escape", "0"], "return_mode": "host_hub", "validators": [], "notes": []}

def validate_manifest(data: dict[str, Any], *, root: Path | None = None) -> list[str]:
    errors: list[str] = []
    for field, typ in REQUIRED_FIELDS.items():
        if field not in data:
            errors.append(f"missing required field: {field}")
        elif not isinstance(data[field], typ):
            errors.append(f"field {field!r} must be {typ.__name__}")
    if data.get("kind") not in ALLOWED_KINDS:
        errors.append(f"kind {data.get('kind')!r} is not allowed")
    if data.get("contract") != CONTRACT:
        errors.append(f"contract must be {CONTRACT!r}")
    owns = data.get("owns", {})
    if owns and not isinstance(owns, dict):
        errors.append("owns must be an object")
    elif bool(owns.get("window")) and data.get("kind") == "panda3d_same_window":
        errors.append("panda3d_same_window capsules may not own the window")
    if root is not None and data.get("entry") and not (root / str(data["entry"])).exists():
        errors.append(f"entry file is missing: {data['entry']}")
    return errors

def read_manifest(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))

def write_manifest(path: str | Path, data: dict[str, Any]) -> Path:
    p = Path(path); p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return p
