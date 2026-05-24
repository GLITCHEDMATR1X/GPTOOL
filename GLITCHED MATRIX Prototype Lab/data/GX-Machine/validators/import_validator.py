from __future__ import annotations

import argparse
import ast
import importlib.util
import json
from pathlib import Path
from typing import Any, Iterable


STDLIB_HINTS = {
    "__future__", "argparse", "ast", "collections", "dataclasses", "functools", "json",
    "math", "os", "pathlib", "platform", "re", "shlex", "subprocess", "sys", "time",
    "typing"
}
PYTHON_SUFFIX = ".py"


def iter_python_files(path: Path) -> Iterable[Path]:
    if path.is_file():
        yield path
        return
    if path.is_dir():
        for child in sorted(path.rglob(f"*{PYTHON_SUFFIX}")):
            if child.is_file():
                yield child


def expand_paths(raw_paths: list[str]) -> list[Path]:
    expanded: list[Path] = []
    seen: set[Path] = set()
    for raw in raw_paths:
        path = Path(raw).resolve()
        if not path.exists():
            if path not in seen:
                expanded.append(path)
                seen.add(path)
            continue
        candidates = list(iter_python_files(path)) if path.is_dir() else [path]
        if not candidates and path not in seen:
            expanded.append(path)
            seen.add(path)
            continue
        for candidate in candidates:
            if candidate not in seen:
                expanded.append(candidate)
                seen.add(candidate)
    return expanded


def local_module_roots(raw_paths: list[str], expanded_files: list[Path]) -> set[str]:
    roots: set[str] = set()
    input_paths = [Path(raw).resolve() for raw in raw_paths]

    search_roots: set[Path] = set()
    for path in input_paths:
        if path.exists() and path.is_dir():
            search_roots.add(path)
        elif path.exists() and path.is_file():
            search_roots.add(path.parent)
    for file_path in expanded_files:
        search_roots.add(file_path.parent)
        if file_path.parent.parent.exists():
            search_roots.add(file_path.parent.parent)

    for root in search_roots:
        for child in root.iterdir():
            if child.name.startswith('.'):
                continue
            if child.is_dir() and (child / '__init__.py').exists():
                roots.add(child.name)
            elif child.is_file() and child.suffix == PYTHON_SUFFIX:
                roots.add(child.stem)
    return roots


def imported_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def validate_imports(path: Path, known_local_roots: set[str]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "path": str(path),
        "exists": path.exists(),
        "ok": False,
        "imports": [],
        "missing": [],
        "error": None,
    }
    if not path.exists():
        result["error"] = "File not found."
        return result
    if path.is_dir():
        result["error"] = "Directory input must be expanded before validation."
        return result

    try:
        roots = sorted(imported_roots(path))
        result["imports"] = roots
        missing = []
        for root in roots:
            if root in STDLIB_HINTS or root in known_local_roots:
                continue
            if importlib.util.find_spec(root) is None:
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
    parser = argparse.ArgumentParser(
        description="Check whether imported top-level modules resolve for files or directories."
    )
    parser.add_argument("paths", nargs="+", help="Python files or directories to inspect.")
    parser.add_argument("--json", action="store_true", help="Emit structured JSON.")
    args = parser.parse_args()

    expanded_paths = expand_paths(args.paths)
    known_local_roots = local_module_roots(args.paths, expanded_paths)
    results = [validate_imports(path, known_local_roots) for path in expanded_paths]
    summary = {
        "validator": "import_validator",
        "input_paths": [str(Path(raw).resolve()) for raw in args.paths],
        "expanded_count": len(expanded_paths),
        "known_local_roots": sorted(known_local_roots),
        "all_ok": bool(results) and all(item["ok"] for item in results),
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
