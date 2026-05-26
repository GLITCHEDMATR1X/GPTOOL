#!/usr/bin/env python3
"""Review/apply GPTOOL workspace cleanup.

Default mode is dry-run. Use --apply --approval APPLY to remove stale notes/logs,
managed project copies, generated reports, caches, and old duplicate tool bundles.
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REMOVE_PATHS = [
    "GLITCHED MATRIX Prototype Lab",
    "GLITCHED-MATRIX-Prototype-Lab-Website",
    "VR",
    "logs",
    "reports",
    "tools/pass_combiner_tool_v5",
    "clone_attempt.log",
    "dry_run_result.txt",
    "portable_build_fix_v4.zip",
    "fbx_animation_body_pass.patch",
    "PATCH_GATE_DROP_IN_README.md",
    "PASS18_APP_CAPSULE_DROP_IN_README.md",
    "PASS19_AUTOMATION_TASK_DROP_IN_README.md",
    "APPLY_PATCH_NOTES.txt",
    "cleanup_optional.txt",
    "README_LOCAL_COPY.md",
]

REMOVE_DIR_NAMES = {
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".venv",
    "venv",
    "env",
    "ENV",
    "crash_reports",
}

REMOVE_FILE_SUFFIXES = {
    ".pyc",
    ".pyo",
    ".log",
}


def iter_candidates() -> list[Path]:
    candidates: list[Path] = []
    for rel in REMOVE_PATHS:
        path = ROOT / rel
        if path.exists():
            candidates.append(path)
    for path in ROOT.rglob("*"):
        try:
            rel = path.relative_to(ROOT)
        except Exception:
            continue
        if ".git" in rel.parts:
            continue
        if path.is_dir() and path.name in REMOVE_DIR_NAMES:
            candidates.append(path)
        elif path.is_file() and path.suffix.lower() in REMOVE_FILE_SUFFIXES:
            candidates.append(path)
    # Remove children before parents and dedupe.
    unique = {str(p.resolve()): p for p in candidates}
    return sorted(unique.values(), key=lambda p: len(p.parts), reverse=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Review/apply GPTOOL cleanup candidates.")
    parser.add_argument("--apply", action="store_true", help="Actually remove candidates.")
    parser.add_argument("--approval", default="", help="Required token APPLY when using --apply.")
    args = parser.parse_args()

    candidates = iter_candidates()
    print(f"GPTOOL cleanup candidates: {len(candidates)}")
    for path in candidates:
        try:
            rel = path.relative_to(ROOT)
        except Exception:
            rel = path
        print(f" - {rel}")

    if not args.apply:
        print("\nDry-run only. Re-run with --apply --approval APPLY to remove candidates.")
        return 0
    if args.approval != "APPLY":
        print("\nBlocked: cleanup apply requires --approval APPLY")
        return 2

    for path in candidates:
        if not path.exists():
            continue
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
    print("\nCleanup applied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
