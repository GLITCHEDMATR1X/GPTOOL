from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

TEXT_EXTS = {".py", ".json", ".md", ".txt", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".glsl", ".vert", ".frag"}
ASSET_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".wav", ".ogg", ".mp3", ".flac", ".glb", ".gltf", ".bam", ".egg", ".obj", ".mtl"}
CODE_EXTS = {".py"}
VISUAL_HINTS = {"main.py", "app.py", "game.py"}

def scan_project(path: Path, max_files: int = 5000) -> dict[str, Any]:
    path = path.resolve()
    files: list[dict[str, Any]] = []
    by_ext: dict[str, int] = {}
    visual_candidates: list[str] = []
    file_count = 0

    for root, dirnames, filenames in os.walk(path):
        dirnames[:] = [d for d in dirnames if d not in {".git", "__pycache__", ".mypy_cache", ".pytest_cache", "node_modules"}]
        for filename in filenames:
            full = Path(root) / filename
            rel = full.relative_to(path)
            ext = full.suffix.lower()
            file_count += 1
            by_ext[ext] = by_ext.get(ext, 0) + 1
            if len(files) < max_files:
                kind = "other"
                if ext in CODE_EXTS:
                    kind = "code"
                elif ext in TEXT_EXTS:
                    kind = "text"
                elif ext in ASSET_EXTS:
                    kind = "asset"
                files.append({
                    "path": str(rel).replace("\\", "/"),
                    "kind": kind,
                    "size_bytes": full.stat().st_size,
                })
            if filename.lower() in VISUAL_HINTS:
                visual_candidates.append(str(rel).replace("\\", "/"))

    asset_count = sum(count for ext, count in by_ext.items() if ext in ASSET_EXTS)
    code_count = sum(count for ext, count in by_ext.items() if ext in CODE_EXTS)
    likely_profile = "generic_python_tool"
    if ".py" in by_ext:
        likely_profile = "python_project"
    if ".bam" in by_ext or ".egg" in by_ext or ".gltf" in by_ext or ".glb" in by_ext:
        likely_profile = "panda3d_candidate"

    return {
        "project_root": str(path),
        "summary": {
            "file_count": file_count,
            "code_file_count": code_count,
            "asset_file_count": asset_count,
            "extensions": dict(sorted(by_ext.items())),
            "visual_entry_candidates": visual_candidates[:20],
            "likely_profile": likely_profile,
        },
        "files": files,
    }

def main() -> int:
    parser = argparse.ArgumentParser(description="Scan a project tree into a bridge-readable inventory.")
    parser.add_argument("path", help="Project root to scan.")
    parser.add_argument("--max-files", type=int, default=5000, help="Maximum detailed files to include.")
    parser.add_argument("--json", action="store_true", help="Emit JSON.")
    parser.add_argument("--out", help="Optional output JSON path.")
    args = parser.parse_args()

    report = scan_project(Path(args.path), max_files=args.max_files)
    if args.out:
        out_path = Path(args.out).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    if args.json or not args.out:
        print(json.dumps(report, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
