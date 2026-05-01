from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

STATE_LAST_KNOWN_GOOD = "last_known_good"
STATE_CANDIDATE = "candidate"
STATE_FAILED_TEST = "failed_test"
STATE_PASSED_TEST = "passed_test"

def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def build_snapshot(project_root: Path) -> dict[str, str]:
    snapshot: dict[str, str] = {}
    for path in sorted(project_root.rglob("*")):
        if path.is_file():
            rel = str(path.relative_to(project_root)).replace("\\", "/")
            snapshot[rel] = _sha256(path)
    return snapshot

def compare_snapshots(current_root: Path, baseline_root: Path, allowed_edit_targets: list[str] | None = None) -> dict[str, Any]:
    current = build_snapshot(current_root)
    baseline = build_snapshot(baseline_root)

    added = sorted(set(current) - set(baseline))
    removed = sorted(set(baseline) - set(current))
    changed = sorted(rel for rel in set(current).intersection(baseline) if current[rel] != baseline[rel])

    allowed_targets = [target.replace('\\', '/').strip('/') for target in (allowed_edit_targets or []) if str(target).strip()]
    out_of_scope_changed = []
    if allowed_targets:
        for rel in changed + added + removed:
            normalized = rel.replace('\\', '/')
            if not any(normalized == target or normalized.startswith(target + '/') for target in allowed_targets):
                out_of_scope_changed.append(rel)

    return {
        "current_root": str(current_root.resolve()),
        "baseline_root": str(baseline_root.resolve()),
        "added_files": added,
        "removed_files": removed,
        "changed_files": changed,
        "candidate_state": STATE_CANDIDATE,
        "authoritative_state": STATE_LAST_KNOWN_GOOD,
        "out_of_scope_changes": sorted(out_of_scope_changed),
        "summary": {
            "added_count": len(added),
            "removed_count": len(removed),
            "changed_count": len(changed),
            "regression_risk": "high" if removed or out_of_scope_changed else ("medium" if changed else "low"),
        },
        "notes": [
            "File-level hashing detects structural drift but not semantic intent.",
            "Any removed authoritative runtime file should be treated as a manual review event.",
            "Pair this diff report with blocking step-gate receipts before candidate promotion."
        ],
    }

def main() -> int:
    parser = argparse.ArgumentParser(description="Compare current project files against a baseline snapshot directory.")
    parser.add_argument("current_root")
    parser.add_argument("baseline_root")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--allow", nargs='*', default=None, help="Optional allowed edit targets relative to the current root. Files outside these targets are flagged as out-of-scope changes.")
    args = parser.parse_args()

    report = compare_snapshots(Path(args.current_root), Path(args.baseline_root), allowed_edit_targets=args.allow)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(json.dumps(report["summary"], indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
