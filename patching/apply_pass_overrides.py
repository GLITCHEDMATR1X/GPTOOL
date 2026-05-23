#!/usr/bin/env python3
"""Review/apply staged _pass_overrides candidates safely.

This helper does not auto-apply anything unless --apply is passed.  It makes a
_backup_before_overrides folder before promoting files.
"""
from __future__ import annotations

import argparse
import difflib
import shutil
from pathlib import Path


def read_text(path: Path) -> str | None:
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if b"\x00" in data[:4096]:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("utf-8", errors="replace")


def main() -> int:
    ap = argparse.ArgumentParser(description="Review or apply _pass_overrides candidate files.")
    ap.add_argument("project", nargs="?", default=".", help="Combined project folder")
    ap.add_argument("--override-dir", default="_pass_overrides")
    ap.add_argument("--apply", action="store_true", help="Actually promote override candidates into the project")
    ap.add_argument("--only", help="Apply/review only paths containing this substring")
    args = ap.parse_args()

    root = Path(args.project).resolve()
    override_root = root / args.override_dir
    if not override_root.exists():
        print(f"No override folder found: {override_root}")
        return 0

    candidates = []
    for path in sorted(override_root.rglob("*")):
        if not path.is_file():
            continue
        rel_inside = path.relative_to(override_root)
        parts = rel_inside.parts
        if len(parts) < 2:
            continue
        target_rel = Path(*parts[1:])
        if args.only and args.only not in target_rel.as_posix():
            continue
        candidates.append((path, root / target_rel, target_rel))

    if not candidates:
        print("No override candidates matched.")
        return 0

    backup_root = root / "_backup_before_overrides"
    for source, target, rel in candidates:
        print(f"\n=== {rel.as_posix()} ===")
        before = read_text(target) if target.exists() else ""
        after = read_text(source)
        if before is not None and after is not None:
            diff = difflib.unified_diff(
                before.splitlines(keepends=True),
                after.splitlines(keepends=True),
                fromfile=f"current/{rel.as_posix()}",
                tofile=f"override/{rel.as_posix()}",
            )
            preview = "".join(diff)
            print(preview[:5000] if preview else "identical text")
        else:
            print(f"binary/non-text candidate: {source.stat().st_size} bytes")
        if args.apply:
            if target.exists():
                backup = backup_root / rel
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, backup)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            print("applied")
        else:
            print("dry review only; pass --apply to promote this candidate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
