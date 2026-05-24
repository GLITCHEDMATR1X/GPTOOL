"""Clean generated artifacts from a HoloVerse source/export tree.

This is a manual source hygiene tool, not the app-close runtime cache sweeper.
It removes files that should not be shipped in a clean source zip: interpreter
caches, stale logs/crash reports, stale split-adapter source files, and pass-backup scratch files.

Usage:
    python tools/clean_holoverse_source_export.py --dry-run
    python tools/clean_holoverse_source_export.py --clean
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
from pathlib import Path
from typing import Iterable

CACHE_DIR_NAMES = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
CACHE_SUFFIXES = {".pyc", ".pyo"}
BACKUP_SUFFIX_PATTERNS = (".passbak",)
PASS_BACKUP_RE = re.compile(r"\.pass\d+bak$", re.IGNORECASE)
LOG_FILE_SUFFIXES = {".log", ".json", ".png"}
LOG_FILE_NAMES = {
    "crash.log",
    "latest.log",
    "holoverse_last_boot.txt",
    "holoverse_last_boot_crash.txt",
    "mode_gateway_audit.json",
    "mode_gateway_history.json",
    "mode_gateway_self_test.json",
    "self_test_report.json",
}
LOG_PREFIXES = (
    "embedded_return_signal_",
    "mode_process_",
)
STALE_SOURCE_EXPORT_FILES = {
    Path("Dimensions/Vector Wars/holoverse_native_adapter_base.py"),
    Path("Dimensions/Vector Wars/holoverse_native_adapter_wrapper.py"),
}
STALE_SOURCE_EXPORT_DIRS = {
    Path("HoloCore/assets"),
}
DIAGNOSTIC_DIR_NAMES = {"logs", "crash_reports"}
# Only skip repository metadata.  We still traverse assets/config/etc. because
# interpreter caches can appear there, but deletion remains limited to explicit
# trash patterns below.
PROTECTED_DIR_NAMES = {".git"}


def _is_within_root(root: Path, path: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except Exception:
        return False


def _is_pass_backup(path: Path) -> bool:
    name = path.name.lower()
    return any(name.endswith(pattern) for pattern in BACKUP_SUFFIX_PATTERNS) or bool(PASS_BACKUP_RE.search(name))


def _is_stale_log(path: Path, root: Path) -> bool:
    try:
        rel = path.resolve().relative_to(root.resolve())
    except Exception:
        return False
    parts = {part.lower() for part in rel.parts}
    if not parts.intersection(DIAGNOSTIC_DIR_NAMES):
        return False
    name = path.name
    lower = name.lower()
    if "crash_reports" in parts:
        return lower != ".gitkeep"
    if lower in LOG_FILE_NAMES or path.suffix.lower() in LOG_FILE_SUFFIXES:
        return True
    return any(lower.startswith(prefix) for prefix in LOG_PREFIXES)


def _is_stale_source_export_file(path: Path, root: Path) -> bool:
    try:
        rel = path.resolve().relative_to(root.resolve())
    except Exception:
        return False
    return rel in STALE_SOURCE_EXPORT_FILES


def iter_source_trash(root: Path) -> Iterable[Path]:
    root = root.resolve()
    for current, dirs, files in os.walk(root):
        current_path = Path(current)
        if not _is_within_root(root, current_path):
            continue
        # Keep user-facing content trees intact.  Cache dirs are still removed
        # wherever they appear because Python regenerates them safely.
        dirs[:] = [
            name for name in dirs
            if name in CACHE_DIR_NAMES or name.lower() not in PROTECTED_DIR_NAMES
        ]
        for name in list(dirs):
            candidate = current_path / name
            if name in CACHE_DIR_NAMES:
                yield candidate
                continue
            try:
                rel_dir = candidate.resolve().relative_to(root.resolve())
            except Exception:
                rel_dir = None
            if rel_dir in STALE_SOURCE_EXPORT_DIRS:
                yield candidate
        for filename in files:
            path = current_path / filename
            if path.suffix.lower() in CACHE_SUFFIXES:
                yield path
            elif _is_pass_backup(path):
                yield path
            elif _is_stale_source_export_file(path, root):
                yield path
            elif _is_stale_log(path, root):
                yield path


def clean_source_export(root: str | Path, *, dry_run: bool = True) -> dict:
    root_path = Path(root).resolve()
    report = {
        "schema": 2,
        "kind": "holoverse_source_export_cleanup",
        "root": os.fspath(root_path),
        "dry_run": bool(dry_run),
        "removed_files": 0,
        "removed_dirs": 0,
        "would_remove_files": 0,
        "would_remove_dirs": 0,
        "targets": [],
        "errors": [],
    }
    if not root_path.exists() or not root_path.is_dir():
        report["errors"].append(f"root-missing:{root_path}")
        return report

    targets = sorted(set(iter_source_trash(root_path)), key=lambda item: len(item.parts), reverse=True)
    for target in targets:
        try:
            target = target.resolve()
            if not _is_within_root(root_path, target) or not target.exists():
                continue
            kind = "dir" if target.is_dir() else "file"
            report["targets"].append({"kind": kind, "path": os.fspath(target.relative_to(root_path))})
            if dry_run:
                if target.is_dir():
                    report["would_remove_dirs"] += 1
                elif target.is_file():
                    report["would_remove_files"] += 1
                continue
            if target.is_dir():
                shutil.rmtree(target)
                report["removed_dirs"] += 1
            elif target.is_file():
                target.unlink()
                report["removed_files"] += 1
        except Exception as exc:
            report["errors"].append(f"{target}:{exc.__class__.__name__}:{exc}")

    # After file cleanup, remove empty diagnostic log folders from source zips.
    # This is source-export hygiene only; the running app recreates these folders
    # when it writes logs/screenshots.
    empty_log_dirs: list[Path] = []
    for current, dirs, _files in os.walk(root_path, topdown=False):
        current_path = Path(current)
        try:
            rel_parts = [part.lower() for part in current_path.resolve().relative_to(root_path).parts]
        except Exception:
            continue
        if not set(rel_parts).intersection(DIAGNOSTIC_DIR_NAMES):
            continue
        try:
            if current_path.exists() and current_path.is_dir() and not any(current_path.iterdir()):
                empty_log_dirs.append(current_path)
        except Exception:
            pass
    for target in sorted(set(empty_log_dirs), key=lambda item: len(item.parts), reverse=True):
        try:
            target = target.resolve()
            if not _is_within_root(root_path, target) or not target.exists() or not target.is_dir():
                continue
            if any(target.iterdir()):
                continue
            report["targets"].append({"kind": "empty-diagnostic-dir", "path": os.fspath(target.relative_to(root_path))})
            if dry_run:
                report["would_remove_dirs"] += 1
            else:
                target.rmdir()
                report["removed_dirs"] += 1
        except Exception as exc:
            report["errors"].append(f"{target}:{exc.__class__.__name__}:{exc}")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Clean HoloVerse source/export artifacts.")
    parser.add_argument("root", nargs="?", default=Path(__file__).resolve().parents[1], help="HoloVerse root directory")
    parser.add_argument("--json-report", default="", help="optional path to write the cleanup report JSON")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--clean", action="store_true", help="delete matching generated artifacts")
    mode.add_argument("--dry-run", action="store_true", help="only report matching generated artifacts")
    args = parser.parse_args()
    report = clean_source_export(args.root, dry_run=not args.clean)
    if args.json_report:
        report_path = Path(args.json_report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 1 if report.get("errors") else 0


if __name__ == "__main__":
    raise SystemExit(main())
