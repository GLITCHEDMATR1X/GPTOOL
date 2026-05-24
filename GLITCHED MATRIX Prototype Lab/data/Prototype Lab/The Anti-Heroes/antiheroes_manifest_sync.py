#!/usr/bin/env python3
"""Sync a GPTOOL-exported human manifest into Anti-Heroes.

This is the handoff tool between GPTOOL's asset exporter and the Anti-Heroes
city/runtime bridge.

Typical flow:

    # Preview only; copies nothing.
    python antiheroes_manifest_sync.py --source-manifest path/to/human_manifest.json --dry-run

    # Copy model/animation files and rewrite the manifest for Anti-Heroes.
    python antiheroes_manifest_sync.py --source-manifest path/to/human_manifest.json --apply

Outputs:

    assets/characters/humans/human_manifest.json
    assets/characters/humans/antiheroes_manifest_lock.json
    reports/antiheroes_manifest_sync_report.json
    reports/antiheroes_manifest_sync_report.md
"""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
TARGET_MANIFEST = ROOT / "assets" / "characters" / "humans" / "human_manifest.json"
TARGET_LOCK = ROOT / "assets" / "characters" / "humans" / "antiheroes_manifest_lock.json"
REPORT_JSON = ROOT / "reports" / "antiheroes_manifest_sync_report.json"
REPORT_MD = ROOT / "reports" / "antiheroes_manifest_sync_report.md"

ASSET_KEYS = ("base_assets", "animations")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _rel(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve())).replace("\\", "/")
    except Exception:
        return str(path).replace("\\", "/")


def infer_source_root(manifest_path: Path, explicit_root: Path | None = None) -> Path:
    if explicit_root:
        return explicit_root.resolve()
    parts = [part.lower() for part in manifest_path.parts]
    # Common GPTOOL layout: <project>/assets/characters/humans/human_manifest.json
    for idx in range(len(parts) - 3):
        if parts[idx : idx + 3] == ["assets", "characters", "humans"]:
            parent_count = len(parts) - idx
            root = manifest_path
            for _ in range(parent_count - idx):
                pass
    try:
        humans = manifest_path.parent
        characters = humans.parent
        assets = characters.parent
        if humans.name.lower() == "humans" and characters.name.lower() == "characters" and assets.name.lower() == "assets":
            return assets.parent.resolve()
    except Exception:
        pass
    return manifest_path.parent.resolve()


def _resolve_source_path(source_root: Path, value: str | None) -> Path | None:
    if not value:
        return None
    raw = Path(str(value))
    if raw.is_absolute():
        return raw
    return (source_root / raw).resolve()


def _safe_destination_for(source: Path, source_root: Path, original_rel: str | None, kind: str) -> tuple[Path, str]:
    # Preserve GPTOOL relative paths when possible. External absolute files are
    # copied into a stable imported bucket inside Anti-Heroes.
    if original_rel:
        raw = Path(str(original_rel))
        if not raw.is_absolute() and ".." not in raw.parts:
            dest_rel = str(raw).replace("\\", "/")
            return (ROOT / dest_rel).resolve(), dest_rel
    try:
        rel = source.resolve().relative_to(source_root.resolve())
        dest_rel = str(rel).replace("\\", "/")
        if ".." not in rel.parts:
            return (ROOT / dest_rel).resolve(), dest_rel
    except Exception:
        pass
    bucket = "animations" if kind == "animations" else "models"
    dest_rel = f"assets/characters/humans/imported/{bucket}/{source.name}"
    return (ROOT / dest_rel).resolve(), dest_rel


def _copy_or_plan(source: Path | None, dest: Path, apply: bool) -> dict[str, Any]:
    record = {
        "source": str(source) if source else "",
        "target": str(dest),
        "source_exists": bool(source and source.exists()),
        "target_exists_before": dest.exists(),
        "copied": False,
        "status": "missing_source",
    }
    if not source or not source.exists():
        return record
    if apply:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)
        record["copied"] = True
        record["status"] = "copied"
    else:
        record["status"] = "planned"
    return record


def _process_items(data: dict[str, Any], source_root: Path, apply: bool) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    rewritten = json.loads(json.dumps(data))
    file_records: list[dict[str, Any]] = []
    for key in ASSET_KEYS:
        items = rewritten.get(key, [])
        if not isinstance(items, list):
            rewritten[key] = []
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            original_rel = item.get("relative_path")
            source = _resolve_source_path(source_root, str(original_rel or ""))
            if source is None or not source.exists():
                # Some manifests keep source_path for traceability.
                source = _resolve_source_path(source_root, str(item.get("source_path") or ""))
            if source:
                dest, dest_rel = _safe_destination_for(source, source_root, str(original_rel or ""), key)
            else:
                dest, dest_rel = _safe_destination_for(Path(str(original_rel or "missing_asset")), source_root, str(original_rel or ""), key)
            file_record = _copy_or_plan(source, dest, apply)
            file_record["kind"] = key
            file_record["id"] = str(item.get("id") or item.get("label") or Path(dest_rel).stem)
            file_records.append(file_record)
            item["relative_path"] = dest_rel
            item["antiheroes_synced"] = True
            item["source_path_original"] = str(source) if source else str(original_rel or "")
    rewritten["antiheroes_sync"] = {
        "schema_version": "antiheroes_manifest_sync.v1",
        "synced_at": datetime.now().isoformat(timespec="seconds"),
        "source_root": str(source_root),
        "target_root": str(ROOT),
    }
    return rewritten, file_records


def build_sync_report(source_manifest: Path, source_root: Path | None, apply: bool) -> dict[str, Any]:
    source_manifest = source_manifest.resolve()
    inferred_root = infer_source_root(source_manifest, source_root)
    report: dict[str, Any] = {
        "schema_version": "antiheroes_manifest_sync_report.v1",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "mode": "apply" if apply else "dry_run",
        "source_manifest": str(source_manifest),
        "source_root": str(inferred_root),
        "target_manifest": str(TARGET_MANIFEST),
        "target_lock": str(TARGET_LOCK),
        "ok": False,
        "warnings": [],
        "files": [],
    }
    if not source_manifest.exists():
        report["warnings"].append("Source manifest does not exist.")
        return report
    try:
        data = _load_json(source_manifest)
    except Exception as exc:
        report["warnings"].append(f"Source manifest parse failed: {type(exc).__name__}: {exc}")
        return report

    rewritten, files = _process_items(data, inferred_root, apply)
    missing = [item for item in files if not item.get("source_exists")]
    planned_or_copied = [item for item in files if item.get("status") in {"planned", "copied"}]
    report.update({
        "ok": bool(planned_or_copied) and not missing,
        "base_asset_count": len([x for x in rewritten.get("base_assets", []) if isinstance(x, dict)]),
        "animation_asset_count": len([x for x in rewritten.get("animations", []) if isinstance(x, dict)]),
        "missing_file_count": len(missing),
        "files": files,
    })
    if missing:
        report["warnings"].append("One or more source asset files are missing; manifest was not considered clean.")
    if not planned_or_copied:
        report["warnings"].append("No asset files were planned or copied.")

    if apply:
        TARGET_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
        TARGET_MANIFEST.write_text(json.dumps(rewritten, indent=2, default=str) + "\n", encoding="utf-8")
        lock = {
            "schema_version": "antiheroes_manifest_lock.v1",
            "locked_at": datetime.now().isoformat(timespec="seconds"),
            "source_manifest": str(source_manifest),
            "source_root": str(inferred_root),
            "target_manifest": str(TARGET_MANIFEST),
            "base_asset_count": report.get("base_asset_count", 0),
            "animation_asset_count": report.get("animation_asset_count", 0),
            "files": files,
        }
        _write_json(TARGET_LOCK, lock)
    return report


def render_md(report: dict[str, Any]) -> str:
    lines = [
        "# Anti-Heroes Manifest Sync Report",
        "",
        f"- Mode: `{report.get('mode')}`",
        f"- OK: **{'YES' if report.get('ok') else 'NO'}**",
        f"- Source manifest: `{report.get('source_manifest')}`",
        f"- Target manifest: `{report.get('target_manifest')}`",
        f"- Base assets: `{report.get('base_asset_count', 0)}`",
        f"- Animation assets: `{report.get('animation_asset_count', 0)}`",
        f"- Missing files: `{report.get('missing_file_count', 0)}`",
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
    lines.extend(["", "## File actions", ""])
    for item in report.get("files", [])[:80]:
        lines.append(f"- `{item.get('status')}` {item.get('kind')} `{item.get('id')}` -> `{item.get('target')}`")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sync a GPTOOL human manifest into Anti-Heroes.")
    parser.add_argument("--source-manifest", required=True, help="Path to GPTOOL-exported human_manifest.json")
    parser.add_argument("--source-root", default=None, help="Optional source project root. Auto-detected when omitted.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Preview copy/rewrite actions without changing assets.")
    mode.add_argument("--apply", action="store_true", help="Copy files and write Anti-Heroes manifest/lock.")
    args = parser.parse_args(argv)

    source_manifest = Path(args.source_manifest).resolve()
    source_root = Path(args.source_root).resolve() if args.source_root else None
    apply = bool(args.apply)
    report = build_sync_report(source_manifest, source_root, apply)
    _write_json(REPORT_JSON, report)
    REPORT_MD.parent.mkdir(parents=True, exist_ok=True)
    REPORT_MD.write_text(render_md(report), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
