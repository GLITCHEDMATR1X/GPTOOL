#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
APP_DATA = ROOT.parent
LOCAL_DIALOGUE = ROOT / "matrixcore" / "gleebs_dialogue.json"
DATABASE_DIALOGUE_CANDIDATES = (
    ROOT / "database" / "MatrixCore" / "gleebs_dialogue.json",
    APP_DATA / "database" / "MatrixCore" / "gleebs_dialogue.json",
)
LORE_STUDY = ROOT / "matrixcore" / "lore_study.json"
UI_THEME = ROOT / "ui" / "theme.py"
UI_CONTRACT = ROOT / "ui" / "red_ui_contract.json"
UI_MANIFEST = ROOT / "ui" / "ui_manifest.json"

REQUIRED_LORE_KEYS = {
    "Gleebs",
    "MatrixCore",
    "HoloVerse",
    "Utopia",
    "IO-88",
}


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
        try:
            return path.resolve().relative_to(APP_DATA.resolve()).as_posix()
        except Exception:
            return path.as_posix()


def _find_cyan_or_blue_dialogue(value: Any, path: str = "root") -> list[str]:
    hits: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            key_text = str(key).lower()
            next_path = f"{path}.{key}"
            if key_text in {"blue", "cyan"} or key_text.endswith("_blue") or key_text.endswith("_cyan"):
                hits.append(next_path)
            hits.extend(_find_cyan_or_blue_dialogue(child, next_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            hits.extend(_find_cyan_or_blue_dialogue(child, f"{path}[{index}]"))
    elif isinstance(value, str):
        lowered = value.lower()
        if "cyan signal" in lowered or "blue signal" in lowered or "favorite cyan" in lowered or "favorite blue" in lowered:
            hits.append(path)
    return hits


def _dialogue_report(path: Path) -> dict[str, Any]:
    payload = _read_json(path)
    display = payload.get("display_rules") if isinstance(payload.get("display_rules"), dict) else {}
    runtime = payload.get("runtime_contract") if isinstance(payload.get("runtime_contract"), dict) else {}
    lines = payload.get("lines") if isinstance(payload.get("lines"), dict) else {}
    lore_notes = payload.get("lore_notes") if isinstance(payload.get("lore_notes"), list) else []
    combined_lore = "\n".join(str(item) for item in lore_notes) + "\n" + "\n".join(str(v) for v in lines.values())
    missing_lore = sorted([key for key in REQUIRED_LORE_KEYS if key.lower() not in combined_lore.lower()])
    hits = _find_cyan_or_blue_dialogue(payload)
    issues: list[str] = []
    if not payload:
        issues.append("dialogue-json-missing-or-invalid")
    if str(payload.get("voice") or "") != "Gleebs":
        issues.append("voice-not-gleebs")
    if str(display.get("text_color") or "").lower() != "red":
        issues.append("display-text-color-not-red")
    if str(runtime.get("active_dialogue_channel") or "").lower() != "red":
        issues.append("runtime-active-channel-not-red")
    if not bool(runtime.get("single_active_dialogue_surface", False)):
        issues.append("single-active-dialogue-surface-not-declared")
    if not bool(runtime.get("duplicate_suppression", False)):
        issues.append("duplicate-suppression-not-declared")
    if hits:
        issues.append("blue-or-cyan-dialogue-reference:" + ",".join(hits[:8]))
    if missing_lore:
        issues.append("missing-lore-context:" + ",".join(missing_lore))
    return {
        "path": _rel(path),
        "schema_version": payload.get("schema_version"),
        "text_color": display.get("text_color"),
        "active_dialogue_channel": runtime.get("active_dialogue_channel"),
        "single_active_dialogue_surface": runtime.get("single_active_dialogue_surface"),
        "duplicate_suppression": runtime.get("duplicate_suppression"),
        "blue_cyan_hits": hits,
        "missing_lore_context": missing_lore,
        "ok": not issues,
        "issues": issues,
    }


def main() -> int:
    errors: list[str] = []
    warnings: list[str] = []

    reports = [_dialogue_report(LOCAL_DIALOGUE)]
    database_dialogue = next((path for path in DATABASE_DIALOGUE_CANDIDATES if path.exists()), None)
    if database_dialogue is not None:
        reports.append(_dialogue_report(database_dialogue))
    else:
        warnings.append("database-gleebs-dialogue-mirror-not-present-in-this-source-export")

    for report in reports:
        if not report["ok"]:
            errors.append(f"{report['path']}: " + "; ".join(report["issues"]))

    local_payload = _read_json(LOCAL_DIALOGUE)
    database_payload = _read_json(database_dialogue) if database_dialogue is not None else {}
    if local_payload and database_payload and local_payload != database_payload:
        errors.append("gleebs-dialogue-sources-are-not-identical")

    theme_text = UI_THEME.read_text(encoding="utf-8", errors="replace") if UI_THEME.exists() else ""
    if "HOLOVERSE_UI_RED" not in theme_text or "GLEEBS_DIALOGUE_CHANNEL = \"red\"" not in theme_text:
        errors.append("ui-theme-red-channel-missing")
    if "RETIRED_DIALOGUE_CHANNELS" not in theme_text:
        errors.append("ui-theme-retired-channel-list-missing")

    contract = _read_json(UI_CONTRACT)
    if str(contract.get("validator") or "") != "data/HoloVerse/tools/validate_gleebs_red_lore_contract.py":
        errors.append("red-ui-contract-validator-reference-missing")
    if "data/HoloVerse/ui/theme.py" not in json.dumps(contract):
        errors.append("red-ui-contract-theme-reference-missing")

    lore = _read_json(LORE_STUDY)
    lore_text = json.dumps(lore)
    for token in REQUIRED_LORE_KEYS:
        if token.lower() not in lore_text.lower():
            errors.append(f"lore-study-missing:{token}")

    manifest_text = UI_MANIFEST.read_text(encoding="utf-8", errors="replace") if UI_MANIFEST.exists() else ""
    if "data/HoloVerse/ui/theme.py" not in manifest_text:
        warnings.append("ui-manifest-does-not-yet-list-theme-module")
    if "data/HoloVerse/ui/red_ui_contract.json" not in manifest_text:
        warnings.append("ui-manifest-does-not-yet-list-red-ui-contract")

    report = {
        "schema": 1,
        "kind": "gleebs_red_lore_contract_validation",
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "dialogue_reports": reports,
        "theme": _rel(UI_THEME),
        "contract": _rel(UI_CONTRACT),
        "lore_study": _rel(LORE_STUDY),
    }
    print(json.dumps(report, indent=2), flush=True)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
