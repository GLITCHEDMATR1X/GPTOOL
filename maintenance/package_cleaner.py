from __future__ import annotations

import argparse
import json
import os
import shutil
import zipfile
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Iterable

CORE_REQUIRED = (
    "bridge.py",
    "requirements.txt",
    "README.md",
    "profiles/panda3d.json",
    "game_builder/template_generator.py",
    "game_builder/settings_planner.py",
    "validators/syntax_validator.py",
    "validators/import_validator.py",
)

CACHE_DIR_NAMES = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
BUILD_DIR_NAMES = {"build", "dist"}
OPTIONAL_HEAVY_DIR_NAMES = {"examples"}
GENERATED_REPORT_NAMES = {
    "latest_report.json",
    "latest_report.md",
    "human_asset_scan.json",
}
KEEP_LOG_NAMES = {"README.md"}
KEEP_LOG_PREFIXES = ("CHANGELOG_", "TESTED_")

TEXT_SUMMARY_LIMIT = 12


@dataclass(frozen=True)
class Candidate:
    path: str
    category: str
    reason: str
    size_bytes: int
    file_count: int


def _safe_rel(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except Exception:
        return path.as_posix()


def _path_size(path: Path) -> tuple[int, int]:
    if not path.exists():
        return 0, 0
    if path.is_file():
        try:
            return path.stat().st_size, 1
        except OSError:
            return 0, 1
    total = 0
    count = 0
    for child in path.rglob("*"):
        if child.is_file():
            count += 1
            try:
                total += child.stat().st_size
            except OSError:
                pass
    return total, count


def _is_generated_log(path: Path, root: Path) -> bool:
    try:
        rel = path.relative_to(root)
    except ValueError:
        return False
    if not rel.parts or rel.parts[0] != "logs":
        return False
    if path.is_dir():
        return False
    name = path.name
    if name in KEEP_LOG_NAMES:
        return False
    if any(name.startswith(prefix) for prefix in KEEP_LOG_PREFIXES):
        return False
    return path.suffix.lower() in {".json", ".txt", ".log"}


def _is_generated_report(path: Path, root: Path) -> bool:
    try:
        rel = path.relative_to(root)
    except ValueError:
        return False
    return bool(rel.parts and rel.parts[0] == "reports" and path.name in GENERATED_REPORT_NAMES)


def _is_candidate_file(path: Path, root: Path, *, include_generated_logs: bool) -> tuple[str, str] | None:
    name = path.name.lower()
    if name.endswith((".pyc", ".pyo")):
        return "python_cache", "compiled Python cache is regenerated automatically"
    if name in {"thumbs.db", ".ds_store"}:
        return "os_cache", "operating-system cache is not part of the bridge"
    if not include_generated_logs and _is_generated_log(path, root):
        return "generated_log", "old run output clutters the delivery bundle"
    if _is_generated_report(path, root):
        return "generated_report", "latest report output should be regenerated per project"
    return None


def _walk_candidates(root: Path, *, include_examples: bool, include_generated_logs: bool) -> list[Candidate]:
    root = root.resolve()
    candidates: list[Candidate] = []
    seen: set[Path] = set()

    for child in root.rglob("*"):
        if child in seen:
            continue
        if child.is_dir():
            if child.name in CACHE_DIR_NAMES:
                size, count = _path_size(child)
                candidates.append(Candidate(_safe_rel(child, root), "cache_dir", "tool/runtime cache directory", size, count))
                seen.update(p for p in child.rglob("*"))
                continue
            if child.name in BUILD_DIR_NAMES:
                size, count = _path_size(child)
                candidates.append(Candidate(_safe_rel(child, root), "build_output", "generated build output should not ship in source bridge", size, count))
                seen.update(p for p in child.rglob("*"))
                continue
            if child.name in OPTIONAL_HEAVY_DIR_NAMES and not include_examples:
                size, count = _path_size(child)
                candidates.append(Candidate(_safe_rel(child, root), "optional_examples", "proof/demo worlds and copied assets are optional artifacts", size, count))
                seen.update(p for p in child.rglob("*"))
                continue
        elif child.is_file():
            marker = _is_candidate_file(child, root, include_generated_logs=include_generated_logs)
            if marker:
                category, reason = marker
                size, count = _path_size(child)
                candidates.append(Candidate(_safe_rel(child, root), category, reason, size, count))
    return sorted(candidates, key=lambda item: (item.size_bytes, item.file_count), reverse=True)


def _directory_totals(root: Path) -> list[dict[str, Any]]:
    totals: dict[str, dict[str, Any]] = {}
    root = root.resolve()
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        try:
            rel = path.relative_to(root)
        except ValueError:
            continue
        key = rel.parts[0] if rel.parts else path.name
        info = totals.setdefault(key, {"path": key, "size_bytes": 0, "file_count": 0})
        info["file_count"] += 1
        try:
            info["size_bytes"] += path.stat().st_size
        except OSError:
            pass
    return sorted(totals.values(), key=lambda item: item["size_bytes"], reverse=True)


def analyze_package(root: Path, *, include_examples: bool = False, include_generated_logs: bool = False) -> dict[str, Any]:
    root = root.resolve()
    total_bytes, total_files = _path_size(root)
    candidates = _walk_candidates(root, include_examples=include_examples, include_generated_logs=include_generated_logs)
    removable_bytes = sum(item.size_bytes for item in candidates)
    removable_files = sum(item.file_count for item in candidates)
    missing = [rel for rel in CORE_REQUIRED if not (root / rel).exists()]
    return {
        "schema_version": "gptool_package_audit.v1",
        "root": str(root),
        "ok": root.exists() and not missing,
        "total_size_bytes": total_bytes,
        "total_file_count": total_files,
        "removable_size_bytes": removable_bytes,
        "removable_file_count": removable_files,
        "required_core_missing": missing,
        "largest_directories": _directory_totals(root)[:20],
        "candidates": [asdict(item) for item in candidates],
        "policy": {
            "examples_are_core": bool(include_examples),
            "generated_logs_are_core": bool(include_generated_logs),
            "default_goal": "ship a lean source bridge; keep generated proof worlds outside the core zip",
        },
    }


def render_package_audit_text(report: dict[str, Any]) -> str:
    def mb(value: int | float) -> str:
        return f"{float(value) / (1024 * 1024):.2f} MB"

    lines = [
        "GPTOOL package audit",
        f"Root: {report.get('root')}",
        f"Status: {'PASS' if report.get('ok') else 'FAIL'}",
        f"Total: {mb(report.get('total_size_bytes', 0))} / {report.get('total_file_count', 0)} files",
        f"Safe cleanup candidates: {mb(report.get('removable_size_bytes', 0))} / {report.get('removable_file_count', 0)} files",
        "",
        "Largest top-level folders:",
    ]
    for item in (report.get("largest_directories") or [])[:TEXT_SUMMARY_LIMIT]:
        lines.append(f"- {item.get('path')}: {mb(item.get('size_bytes', 0))} / {item.get('file_count', 0)} files")
    candidates = report.get("candidates") or []
    if candidates:
        lines.extend(["", "Largest cleanup candidates:"])
        for item in candidates[:TEXT_SUMMARY_LIMIT]:
            lines.append(f"- [{item.get('category')}] {item.get('path')}: {mb(item.get('size_bytes', 0))} — {item.get('reason')}")
    missing = report.get("required_core_missing") or []
    if missing:
        lines.extend(["", "Missing required core files:"])
        for item in missing:
            lines.append(f"- {item}")
    return "\n".join(lines) + "\n"


def clean_package_tree(root: Path, *, apply: bool = False, include_examples: bool = False, include_generated_logs: bool = False) -> dict[str, Any]:
    root = root.resolve()
    candidates = _walk_candidates(root, include_examples=include_examples, include_generated_logs=include_generated_logs)
    actions: list[dict[str, Any]] = []
    for item in candidates:
        target = root / item.path
        action = {**asdict(item), "removed": False, "error": None}
        if apply:
            try:
                if target.is_dir():
                    shutil.rmtree(target)
                elif target.exists():
                    target.unlink()
                action["removed"] = True
            except Exception as exc:  # pragma: no cover - filesystem safety path
                action["error"] = f"{type(exc).__name__}: {exc}"
        actions.append(action)
    return {
        "schema_version": "gptool_package_clean.v1",
        "root": str(root),
        "apply": bool(apply),
        "ok": not any(action.get("error") for action in actions),
        "candidate_count": len(actions),
        "removed_count": sum(1 for action in actions if action.get("removed")),
        "candidate_size_bytes": sum(int(action.get("size_bytes") or 0) for action in actions),
        "actions": actions,
    }


def _should_include_for_zip(path: Path, root: Path, *, include_examples: bool, include_generated_logs: bool, include_pycache: bool) -> bool:
    try:
        rel = path.relative_to(root)
    except ValueError:
        return False
    parts = rel.parts
    if not parts:
        return False
    if not include_examples and parts[0] in OPTIONAL_HEAVY_DIR_NAMES:
        return False
    if any(part in BUILD_DIR_NAMES for part in parts):
        return False
    if not include_pycache and any(part in CACHE_DIR_NAMES for part in parts):
        return False
    if path.is_file():
        marker = _is_candidate_file(path, root, include_generated_logs=include_generated_logs)
        if marker and marker[0] in {"python_cache", "os_cache", "generated_log", "generated_report"}:
            return False
    return True


def create_lean_package_zip(
    source_root: Path,
    output_zip: Path,
    *,
    include_examples: bool = False,
    include_generated_logs: bool = False,
    include_pycache: bool = False,
) -> dict[str, Any]:
    source_root = source_root.resolve()
    output_zip = output_zip.resolve()
    output_zip.parent.mkdir(parents=True, exist_ok=True)
    added = 0
    added_bytes = 0
    skipped = 0
    with zipfile.ZipFile(output_zip, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path in sorted(source_root.rglob("*")):
            if path == output_zip or not path.is_file():
                continue
            if not _should_include_for_zip(
                path,
                source_root,
                include_examples=include_examples,
                include_generated_logs=include_generated_logs,
                include_pycache=include_pycache,
            ):
                skipped += 1
                continue
            rel = Path(source_root.name) / path.relative_to(source_root)
            zf.write(path, rel.as_posix())
            added += 1
            try:
                added_bytes += path.stat().st_size
            except OSError:
                pass
    zip_size = output_zip.stat().st_size if output_zip.exists() else 0
    return {
        "schema_version": "gptool_lean_zip.v1",
        "ok": output_zip.exists(),
        "source_root": str(source_root),
        "output_zip": str(output_zip),
        "added_file_count": added,
        "skipped_file_count": skipped,
        "source_bytes_added": added_bytes,
        "zip_size_bytes": zip_size,
        "include_examples": bool(include_examples),
        "include_generated_logs": bool(include_generated_logs),
        "include_pycache": bool(include_pycache),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit and clean GPTOOL source bundles.")
    sub = parser.add_subparsers(dest="command", required=True)

    audit = sub.add_parser("audit")
    audit.add_argument("root")
    audit.add_argument("--include-examples", action="store_true")
    audit.add_argument("--include-generated-logs", action="store_true")
    audit.add_argument("--json", action="store_true")

    clean = sub.add_parser("clean")
    clean.add_argument("root")
    clean.add_argument("--apply", action="store_true", help="Remove candidates. Without this, only reports what would be removed.")
    clean.add_argument("--include-examples", action="store_true", help="Treat examples as required, not cleanup candidates.")
    clean.add_argument("--include-generated-logs", action="store_true", help="Treat generated logs as required, not cleanup candidates.")
    clean.add_argument("--json", action="store_true")

    zip_cmd = sub.add_parser("lean-zip")
    zip_cmd.add_argument("source_root")
    zip_cmd.add_argument("output_zip")
    zip_cmd.add_argument("--include-examples", action="store_true")
    zip_cmd.add_argument("--include-generated-logs", action="store_true")
    zip_cmd.add_argument("--include-pycache", action="store_true")
    zip_cmd.add_argument("--json", action="store_true")

    args = parser.parse_args(argv)
    if args.command == "audit":
        report = analyze_package(Path(args.root), include_examples=args.include_examples, include_generated_logs=args.include_generated_logs)
        print(json.dumps(report, indent=2) if args.json else render_package_audit_text(report))
        return 0 if report.get("ok") else 1
    if args.command == "clean":
        report = clean_package_tree(Path(args.root), apply=args.apply, include_examples=args.include_examples, include_generated_logs=args.include_generated_logs)
        if args.json:
            print(json.dumps(report, indent=2))
        else:
            mode = "removed" if args.apply else "would remove"
            print(f"Clean package: {mode} {report.get('candidate_count')} candidates / {report.get('candidate_size_bytes', 0)} bytes")
        return 0 if report.get("ok") else 1
    if args.command == "lean-zip":
        report = create_lean_package_zip(
            Path(args.source_root),
            Path(args.output_zip),
            include_examples=args.include_examples,
            include_generated_logs=args.include_generated_logs,
            include_pycache=args.include_pycache,
        )
        if args.json:
            print(json.dumps(report, indent=2))
        else:
            print(f"Lean zip: {'PASS' if report.get('ok') else 'FAIL'}")
            print(f"Output: {report.get('output_zip')}")
            print(f"Files: {report.get('added_file_count')} added / {report.get('skipped_file_count')} skipped")
            print(f"Size: {report.get('zip_size_bytes')} bytes")
        return 0 if report.get("ok") else 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
