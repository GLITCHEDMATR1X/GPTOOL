from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def build_snapshot(project_root: Path) -> dict[str, str]:
    snapshot: dict[str, str] = {}
    for path in sorted(project_root.rglob("*")):
        if path.is_file():
            rel = str(path.relative_to(project_root)).replace("\\", "/")
            snapshot[rel] = _sha256(path)
    return snapshot

def compare_snapshots(current_root: Path, baseline_root: Path) -> dict[str, Any]:
    current = build_snapshot(current_root)
    baseline = build_snapshot(baseline_root)

    added = sorted(set(current) - set(baseline))
    removed = sorted(set(baseline) - set(current))
    changed = sorted(rel for rel in set(current).intersection(baseline) if current[rel] != baseline[rel])

    return {
        "current_root": str(current_root.resolve()),
        "baseline_root": str(baseline_root.resolve()),
        "added_files": added,
        "removed_files": removed,
        "changed_files": changed,
        "summary": {
            "added_count": len(added),
            "removed_count": len(removed),
            "changed_count": len(changed),
            "regression_risk": "high" if removed else ("medium" if changed else "low"),
        },
        "notes": [
            "File-level hashing detects structural drift but not semantic intent.",
            "Any removed authoritative runtime file should be treated as a manual review event."
        ],
    }

def main() -> int:
    parser = argparse.ArgumentParser(description="Compare current project files against a baseline snapshot directory.")
    parser.add_argument("current_root")
    parser.add_argument("baseline_root")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = compare_snapshots(Path(args.current_root), Path(args.baseline_root))
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(json.dumps(report["summary"], indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
