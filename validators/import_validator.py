from __future__ import annotations

import argparse
import ast
import pkgutil
import json
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any


STDLIB_HINTS = {
    "__future__", "argparse", "ast", "collections", "dataclasses", "functools", "json",
    "math", "os", "pathlib", "platform", "re", "shlex", "subprocess", "sys", "time",
    "typing", "hashlib", "datetime", "traceback", "statistics", "random", "itertools",
    "textwrap", "copy", "enum", "logging", "tempfile", "zipfile", "csv", "sqlite3",
    "tkinter", "http", "urllib", "email", "html", "xml", "unittest", "typing_extensions",
}
EXCLUDED_DIRS = {".git", "__pycache__", ".mypy_cache", ".pytest_cache", "node_modules", "dist", "build"}

@lru_cache(maxsize=1)
def stdlib_roots() -> set[str]:
    return set(STDLIB_HINTS) | set(getattr(sys, "stdlib_module_names", set()))


@lru_cache(maxsize=1)
def available_top_level_modules() -> set[str]:
    names = set(sys.builtin_module_names)
    try:
        names.update(module.name for module in pkgutil.iter_modules())
    except Exception:
        pass
    return names


def imported_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.level and node.level > 0:
                continue
            roots.add(node.module.split(".")[0])
    return roots


@lru_cache(maxsize=64)
def _local_import_roots_cached(project_root_str: str) -> tuple[str, ...]:
    project_root = Path(project_root_str).resolve()
    roots: set[str] = set()
    if not project_root.exists() or not project_root.is_dir():
        return tuple()
    for child in project_root.iterdir():
        if child.name.startswith(".") or child.name in EXCLUDED_DIRS:
            continue
        if child.is_dir() and ((child / "__init__.py").exists() or any(child.glob("*.py"))):
            roots.add(child.name)
        elif child.suffix == ".py":
            roots.add(child.stem)
    return tuple(sorted(roots))


def local_import_roots(project_root: Path | None) -> set[str]:
    if project_root is None:
        return set()
    return set(_local_import_roots_cached(str(project_root.resolve())))


def iter_python_files(path: Path) -> list[Path]:
    path = path.resolve()
    if path.is_file() or not path.exists():
        return [path]
    files: list[Path] = []
    for child in sorted(path.rglob("*.py")):
        try:
            parts = child.relative_to(path).parts
        except Exception:
            parts = child.parts
        if any(part in EXCLUDED_DIRS for part in parts):
            continue
        files.append(child)
    return files


def _has_local_module_file(path: Path, root: str) -> bool:
    return (path.parent / f"{root}.py").exists() or (path.parent / root / "__init__.py").exists()


def validate_imports(path: Path, project_root: Path | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "path": str(path),
        "project_root": str(project_root.resolve()) if project_root else None,
        "exists": path.exists(),
        "ok": False,
        "imports": [],
        "missing": [],
        "local_roots": sorted(local_import_roots(project_root)),
        "error": None,
    }
    if not path.exists():
        result["error"] = "File not found."
        return result

    try:
        roots = sorted(imported_roots(path))
        result["imports"] = roots
        missing = []
        local_roots = local_import_roots(project_root or path.parent)
        stdlib_names = stdlib_roots()
        for root in roots:
            if root in stdlib_names:
                continue
            if root in local_roots or _has_local_module_file(path, root):
                continue
            if root not in available_top_level_modules():
                missing.append(root)
        result["missing"] = missing
        result["ok"] = len(missing) == 0
    except SyntaxError as exc:
        result["error"] = {
            "type": "SyntaxError",
            "message": exc.msg,
            "line": exc.lineno,
        }
    except Exception as exc:
        result["error"] = {"type": type(exc).__name__, "message": str(exc)}
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Check whether imported top-level modules resolve.")
    parser.add_argument("paths", nargs="+", help="Python files or folders to inspect.")
    parser.add_argument("--project-root", help="Project root used to resolve local imports.")
    parser.add_argument("--json", action="store_true", help="Emit structured JSON.")
    args = parser.parse_args()

    paths: list[Path] = []
    for raw in args.paths:
        paths.extend(iter_python_files(Path(raw)))
    project_root = Path(args.project_root).resolve() if args.project_root else None
    if project_root is None and len(args.paths) == 1 and Path(args.paths[0]).is_dir():
        project_root = Path(args.paths[0]).resolve()
    results = [validate_imports(path.resolve(), project_root=project_root) for path in paths]
    summary = {
        "validator": "import_validator",
        "all_ok": all(item["ok"] for item in results),
        "checked_file_count": len(results),
        "results": results,
    }

    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        for item in results:
            status = "PASS" if item["ok"] else "FAIL"
            print(f"[{status}] {item['path']}")
            if item["missing"]:
                print(f"  Missing: {', '.join(item['missing'])}")
            if item["error"]:
                print(f"  Error: {item['error']}")
    return 0 if summary["all_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
