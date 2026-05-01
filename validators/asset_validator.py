from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

ASSET_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".wav", ".ogg", ".mp3", ".flac", ".glb", ".gltf", ".bam", ".egg", ".obj", ".mtl"}
STRING_RE = re.compile(r'["\']([^"\']+\.[A-Za-z0-9]{2,5})["\']')
RUNTIME_OUTPUT_TOKENS = ("screenshot", "backup", "proof", "crash_latest", "runtime_latest", "last_controls_state", "last_scene_state")

def _extract_asset_strings(text: str) -> set[str]:
    return {m.group(1) for m in STRING_RE.finditer(text)}

def _is_runtime_output_reference(asset_ref: str) -> bool:
    normalized = asset_ref.replace("\\", "/").lower()
    if "{" in normalized or "}" in normalized:
        return True
    parts = [part for part in normalized.split("/") if part]
    if any(part in {"screenshots", "reports", "logs"} for part in parts[:-1]):
        return True
    name = Path(normalized).name
    return any(token in name for token in RUNTIME_OUTPUT_TOKENS)

def validate_assets(project_root: Path) -> dict[str, Any]:
    project_root = project_root.resolve()
    referenced: list[dict[str, str]] = []
    missing: list[dict[str, str]] = []
    existing: list[dict[str, str]] = []

    for py_path in project_root.rglob("*.py"):
        try:
            text = py_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        for asset_ref in sorted(_extract_asset_strings(text)):
            ext = Path(asset_ref).suffix.lower()
            if ext not in ASSET_EXTS:
                continue
            normalized = asset_ref.replace("\\", "/")
            if _is_runtime_output_reference(normalized):
                continue
            if normalized.startswith(("./", "../")):
                target = (py_path.parent / normalized).resolve()
            else:
                target = (project_root / normalized).resolve()
            record = {"source_file": str(py_path.relative_to(project_root)).replace("\\", "/"), "asset_ref": normalized}
            referenced.append(record)
            if target.exists():
                existing.append(record | {"resolved_path": str(target)})
            else:
                missing.append(record | {"expected_path": str(target)})

    return {
        "project_root": str(project_root),
        "ok": len(missing) == 0,
        "referenced_asset_count": len(referenced),
        "existing_asset_count": len(existing),
        "missing_asset_count": len(missing),
        "missing_assets": missing[:200],
        "notes": [
            "This validator only checks string-discoverable asset references in Python source.",
            "Runtime-generated paths and non-Python asset manifests are not fully covered.",
            "Known screenshot/proof/log output paths are ignored because they are produced at runtime."
        ],
    }

def main() -> int:
    parser = argparse.ArgumentParser(description="Check discoverable Python asset references against the project tree.")
    parser.add_argument("project_root", help="Project root to scan.")
    parser.add_argument("--json", action="store_true", help="Emit JSON.")
    args = parser.parse_args()

    report = validate_assets(Path(args.project_root))
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        status = "PASS" if report["ok"] else "FAIL"
        print(f"[{status}] referenced={report['referenced_asset_count']} missing={report['missing_asset_count']}")
        for item in report["missing_assets"][:20]:
            print(f"- {item['source_file']}: {item['asset_ref']}")
    return 0 if report["ok"] else 1

if __name__ == "__main__":
    raise SystemExit(main())
