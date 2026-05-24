"""Safe runtime-cache cleanup for HoloVerse.

This module only removes generated interpreter/runtime cache artifacts. It does
not remove saves, progression, configs, logs, screenshots, generated audio, or
player-created content.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Iterable

SAFE_CACHE_DIR_NAMES = {
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
}

SAFE_CACHE_SUFFIXES = {
    ".pyc",
    ".pyo",
}

SAFE_CACHE_GLOBS = (
    "*_holospace_p2.png",
)

# These trees hold user-facing state or useful diagnostics and must not be
# cleaned by the app-close cache sweeper.
PROTECTED_DIR_NAMES = {
    ".git",
    "config",
    "logs",
    "patch_notes",
    "progression",
    "screenshots",
}


def _is_within_root(root: Path, path: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except Exception:
        return False


def _iter_cache_targets(root: Path) -> Iterable[Path]:
    root = root.resolve()
    for current, dirs, files in os.walk(root):
        current_path = Path(current)
        if not _is_within_root(root, current_path):
            continue

        # Do not recurse into protected data/diagnostic folders.  __pycache__ is
        # still removed wherever it appears because it is always regenerated.
        dirs[:] = [
            name for name in dirs
            if name in SAFE_CACHE_DIR_NAMES or name.lower() not in PROTECTED_DIR_NAMES
        ]

        for name in list(dirs):
            if name in SAFE_CACHE_DIR_NAMES:
                yield current_path / name

        for filename in files:
            path = current_path / filename
            suffix = path.suffix.lower()
            if suffix in SAFE_CACHE_SUFFIXES:
                yield path
                continue
            for pattern in SAFE_CACHE_GLOBS:
                if path.match(pattern):
                    yield path
                    break


def clear_runtime_cache(root: str | Path, *, reason: str = "exit") -> dict:
    """Remove safe generated cache artifacts from a HoloVerse checkout.

    Returns a small report for validators/logging.  All failures are captured in
    the report instead of raising so app shutdown cannot be blocked by cleanup.
    """
    root_path = Path(root).resolve()
    report = {
        "reason": str(reason or "exit"),
        "root": os.fspath(root_path),
        "removed_files": 0,
        "removed_dirs": 0,
        "errors": [],
    }
    if not root_path.exists() or not root_path.is_dir():
        report["errors"].append(f"root-missing:{root_path}")
        return report

    seen: set[Path] = set()
    targets = sorted(set(_iter_cache_targets(root_path)), key=lambda p: len(p.parts), reverse=True)
    for target in targets:
        try:
            target = target.resolve()
            if target in seen or not _is_within_root(root_path, target):
                continue
            seen.add(target)
            if not target.exists():
                continue
            if target.is_dir():
                shutil.rmtree(target)
                report["removed_dirs"] += 1
            elif target.is_file():
                target.unlink()
                report["removed_files"] += 1
        except Exception as exc:
            report["errors"].append(f"{target}:{exc.__class__.__name__}:{exc}")
    return report


if __name__ == "__main__":
    import json
    import sys

    base = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parent
    print(json.dumps(clear_runtime_cache(base, reason="manual"), indent=2))
