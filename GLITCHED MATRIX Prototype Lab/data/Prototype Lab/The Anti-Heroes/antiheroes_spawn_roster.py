#!/usr/bin/env python3
"""Character spawn roster for Anti-Heroes imported GPTOOL assets.

The manifest bridge imports models. The animation registry understands clips.
The runtime adapter can spawn one manifest character. This file adds the next
layer: a small data-driven roster that assigns imported models to world roles.

Commands from the Anti-Heroes folder:

    python antiheroes_spawn_roster.py --init-default
    python antiheroes_spawn_roster.py --validate

Outputs:

    data/characters/antiheroes_spawn_roster.json
    reports/antiheroes_spawn_roster_report.json
    reports/antiheroes_spawn_roster_report.md

The live runtime can later read this roster and call
AntiHeroesCharacterRuntime.spawn_manifest_character for each active entry.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
HUMAN_MANIFEST = ROOT / "assets" / "characters" / "humans" / "human_manifest.json"
ROSTER_PATH = ROOT / "data" / "characters" / "antiheroes_spawn_roster.json"
REPORT_JSON = ROOT / "reports" / "antiheroes_spawn_roster_report.json"
REPORT_MD = ROOT / "reports" / "antiheroes_spawn_roster_report.md"

DEFAULT_DISTRICTS = ("Spawn Plaza", "Contract Row", "Safehouse South", "Vendor East", "Rearm West")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _manifest_asset_ids() -> list[str]:
    if not HUMAN_MANIFEST.exists():
        return []
    try:
        data = _load_json(HUMAN_MANIFEST)
    except Exception:
        return []
    ids: list[str] = []
    for item in data.get("base_assets", []):
        if isinstance(item, dict):
            value = str(item.get("id") or item.get("label") or "").strip()
            if value:
                ids.append(value)
    return ids


def _select_model(asset_ids: list[str], index: int, fallback: str) -> str:
    if asset_ids:
        return asset_ids[index % len(asset_ids)]
    return fallback


def build_default_roster() -> dict[str, Any]:
    asset_ids = _manifest_asset_ids()
    entries = [
        {
            "id": "player_primary",
            "enabled": True,
            "role": "player",
            "model_id": _select_model(asset_ids, 0, "manifest_model_0"),
            "district": "Spawn Plaza",
            "spawn_pos": [0.0, 0.0, 0.05],
            "spawn_hpr": [180.0, 0.0, 0.0],
            "scale": 1.0,
            "initial_motion": "idle",
            "stance": "neutral",
            "faction": "antiheroes",
            "notes": "Primary controllable character. Keep this first for runtime fallback.",
        },
        {
            "id": "ally_contract_contact",
            "enabled": True,
            "role": "ally_contact",
            "model_id": _select_model(asset_ids, 1, "manifest_model_1"),
            "district": "Contract Row",
            "spawn_pos": [4.0, 8.0, 0.05],
            "spawn_hpr": [215.0, 0.0, 0.0],
            "scale": 0.95,
            "initial_motion": "idle",
            "stance": "mercenary",
            "faction": "contract_board",
            "notes": "Future contract-board NPC. No combat pressure yet.",
        },
        {
            "id": "safehouse_guardian",
            "enabled": True,
            "role": "safehouse_guardian",
            "model_id": _select_model(asset_ids, 2, "manifest_model_2"),
            "district": "Safehouse South",
            "spawn_pos": [-3.5, -9.0, 0.05],
            "spawn_hpr": [25.0, 0.0, 0.0],
            "scale": 1.05,
            "initial_motion": "idle",
            "stance": "protector",
            "faction": "safehouse",
            "notes": "Service anchor NPC for save/recover/upgrades.",
        },
        {
            "id": "vendor_specialist",
            "enabled": True,
            "role": "vendor",
            "model_id": _select_model(asset_ids, 3, "manifest_model_3"),
            "district": "Vendor East",
            "spawn_pos": [9.0, 1.5, 0.05],
            "spawn_hpr": [270.0, 0.0, 0.0],
            "scale": 0.9,
            "initial_motion": "idle",
            "stance": "neutral",
            "faction": "vendor",
            "notes": "Future rearm/vendor NPC. Keep non-hostile.",
        },
    ]
    return {
        "schema_version": "antiheroes_spawn_roster.v1",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_manifest": str(HUMAN_MANIFEST),
        "districts": list(DEFAULT_DISTRICTS),
        "entries": entries,
        "runtime_contract": {
            "spawn_order": "player first, then enabled service/contact NPCs",
            "loader": "AntiHeroesCharacterRuntime.spawn_manifest_character",
            "motion": "AntiHeroesCharacterRuntime.set_motion_state",
            "missing_model_policy": "warn and skip NPC; player may use runtime fallback",
        },
    }


def validate_roster(roster_path: Path = ROSTER_PATH) -> dict[str, Any]:
    report: dict[str, Any] = {
        "schema_version": "antiheroes_spawn_roster_report.v1",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "roster_path": str(roster_path),
        "manifest_path": str(HUMAN_MANIFEST),
        "ok": False,
        "warnings": [],
        "entries": [],
    }
    asset_ids = set(_manifest_asset_ids())
    report["manifest_exists"] = HUMAN_MANIFEST.exists()
    report["manifest_asset_ids"] = sorted(asset_ids)
    if not roster_path.exists():
        report["warnings"].append("Spawn roster does not exist. Run --init-default first.")
        return report
    try:
        roster = _load_json(roster_path)
    except Exception as exc:
        report["warnings"].append(f"Spawn roster parse failed: {type(exc).__name__}: {exc}")
        return report

    seen: set[str] = set()
    entries = roster.get("entries", [])
    if not isinstance(entries, list) or not entries:
        report["warnings"].append("Spawn roster has no entries.")
        return report

    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            report["warnings"].append(f"Entry {index} is not an object.")
            continue
        entry_id = str(entry.get("id") or f"entry_{index}")
        model_id = str(entry.get("model_id") or "")
        enabled = bool(entry.get("enabled", True))
        pos = entry.get("spawn_pos")
        entry_report = {
            "id": entry_id,
            "enabled": enabled,
            "role": str(entry.get("role") or "npc"),
            "model_id": model_id,
            "model_found": model_id in asset_ids if asset_ids else False,
            "district": str(entry.get("district") or ""),
            "spawn_pos": pos,
            "warnings": [],
        }
        if entry_id in seen:
            entry_report["warnings"].append("Duplicate entry id.")
        seen.add(entry_id)
        if not model_id:
            entry_report["warnings"].append("Missing model_id.")
        elif asset_ids and model_id not in asset_ids:
            entry_report["warnings"].append("model_id is not present in human_manifest.json.")
        if not isinstance(pos, list) or len(pos) != 3:
            entry_report["warnings"].append("spawn_pos must be [x, y, z].")
        report["entries"].append(entry_report)

    entry_warnings = [warning for item in report["entries"] for warning in item.get("warnings", [])]
    if not HUMAN_MANIFEST.exists():
        report["warnings"].append("human_manifest.json missing; model_id validation is limited.")
    if entry_warnings:
        report["warnings"].append("One or more roster entries have warnings.")
    report["enabled_count"] = len([item for item in report["entries"] if item.get("enabled")])
    report["ok"] = bool(report["entries"]) and not entry_warnings
    if not asset_ids:
        # A roster can still be structurally OK before model import.
        report["ok"] = bool(report["entries"]) and not entry_warnings
    return report


def render_md(report: dict[str, Any]) -> str:
    lines = [
        "# Anti-Heroes Spawn Roster Report",
        "",
        f"- OK: **{'YES' if report.get('ok') else 'NO'}**",
        f"- Roster: `{report.get('roster_path')}`",
        f"- Manifest exists: `{report.get('manifest_exists')}`",
        f"- Enabled entries: `{report.get('enabled_count', 0)}`",
        "",
        "## Warnings",
        "",
    ]
    warnings = report.get("warnings") or []
    if warnings:
        for warning in warnings:
            lines.append(f"- {warning}")
    else:
        lines.append("- None")
    lines.extend(["", "## Entries", ""])
    for item in report.get("entries", []):
        status = "ok" if not item.get("warnings") else "warn"
        lines.append(f"- `{status}` **{item.get('id')}** role=`{item.get('role')}` model=`{item.get('model_id')}` district=`{item.get('district')}`")
        for warning in item.get("warnings", []):
            lines.append(f"  - {warning}")
    return "\n".join(lines) + "\n"


def write_report(report: dict[str, Any]) -> None:
    _write_json(REPORT_JSON, report)
    REPORT_MD.parent.mkdir(parents=True, exist_ok=True)
    REPORT_MD.write_text(render_md(report), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Manage Anti-Heroes character spawn roster.")
    parser.add_argument("--init-default", action="store_true", help="Create/update default spawn roster.")
    parser.add_argument("--validate", action="store_true", help="Validate spawn roster and write reports.")
    args = parser.parse_args(argv)

    if args.init_default:
        roster = build_default_roster()
        _write_json(ROSTER_PATH, roster)
    report = validate_roster(ROSTER_PATH)
    write_report(report)
    print(json.dumps(report, indent=2, default=str))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
