from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .path_resolver import expand_value, load_roots, unresolved_tokens

SCHEMA_VERSION = "gptool.task.v1"
ALLOWED_ACTIONS = {
    "note",
    "command",
    "assert_file_exists",
    "assert_dir_exists",
    "assert_text_contains",
    "assert_no_junk",
    "patch_gate_dry_run",
    "patch_gate_apply",
    "panda3d_smoke",
    "capture_expected_artifact",
    "write_input_plan",
    "validate_input_plan",
    "screenshot_checkpoint",
    "panda3d_journey_smoke",
}
JUNK_PART_NAMES = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", "crash_reports"}
JUNK_SUFFIXES = {".pyc", ".pyo", ".tmp", ".bak", ".orig", ".rej"}


def load_manifest(path: str | Path, *, root_config: str | Path | None = None, resolve_roots: bool = True) -> dict[str, Any]:
    p = Path(path).resolve()
    data = json.loads(p.read_text(encoding="utf-8"))
    data.setdefault("schema", SCHEMA_VERSION)
    data.setdefault("steps", [])
    data["_manifest_path"] = str(p)
    if resolve_roots:
        roots, used_config = load_roots(root_config)
        data = expand_value(data, roots)
        data["_resolved_roots"] = roots
        data["_root_config_path"] = used_config
        data["_unresolved_tokens"] = unresolved_tokens(data)
    return data


def validate_manifest(data: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    if data.get("schema") != SCHEMA_VERSION:
        warnings.append(f"schema is {data.get('schema')!r}; expected {SCHEMA_VERSION!r}")
    unresolved = data.get("_unresolved_tokens") or []
    if unresolved:
        errors.append("unresolved root tokens: " + ", ".join(str(item) for item in unresolved))
    if not data.get("id"):
        errors.append("missing id")
    if not isinstance(data.get("steps"), list):
        errors.append("steps must be a list")
        steps = []
    else:
        steps = data.get("steps") or []
    for index, step in enumerate(steps, start=1):
        if not isinstance(step, dict):
            errors.append(f"step {index} is not an object")
            continue
        action = step.get("action")
        if action not in ALLOWED_ACTIONS:
            errors.append(f"step {index} has unsupported action {action!r}")
        if action == "command" and not step.get("cmd"):
            errors.append(f"step {index} command missing cmd")
        if action in {"assert_file_exists", "assert_dir_exists", "assert_no_junk"} and not step.get("path"):
            errors.append(f"step {index} {action} missing path")
        if action == "assert_text_contains" and (not step.get("path") or not step.get("text")):
            errors.append(f"step {index} assert_text_contains missing path/text")
        if action in {"patch_gate_dry_run", "patch_gate_apply"}:
            for key in ("repo_root", "patch_zip"):
                if not step.get(key):
                    errors.append(f"step {index} {action} missing {key}")
            if action == "patch_gate_apply" and not step.get("requires_approval", True):
                warnings.append(f"step {index} patch_gate_apply should require approval")
        if action == "write_input_plan":
            if not step.get("output"):
                errors.append(f"step {index} write_input_plan missing output")
            if not isinstance(step.get("steps"), list):
                errors.append(f"step {index} write_input_plan missing steps list")
        if action == "validate_input_plan" and not (step.get("path") or isinstance(step.get("plan"), dict) or isinstance(step.get("steps"), list)):
            errors.append(f"step {index} validate_input_plan needs path, plan, or steps")
        if action == "screenshot_checkpoint" and not step.get("path"):
            errors.append(f"step {index} screenshot_checkpoint missing path")
        if action == "panda3d_journey_smoke" and not step.get("project"):
            errors.append(f"step {index} panda3d_journey_smoke missing project")
    return {"ok": not errors, "errors": errors, "warnings": warnings, "step_count": len(steps)}


def find_junk(root: str | Path, limit: int = 200) -> list[str]:
    base = Path(root)
    found: list[str] = []
    if not base.exists():
        return [f"missing-root:{base}"]
    for path in base.rglob("*"):
        try:
            rel = path.relative_to(base).as_posix()
        except Exception:
            rel = str(path)
        if any(part in JUNK_PART_NAMES for part in path.parts) or path.suffix.lower() in JUNK_SUFFIXES:
            found.append(rel)
            if len(found) >= limit:
                found.append("...truncated...")
                break
    return found
