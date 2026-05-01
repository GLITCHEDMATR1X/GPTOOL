from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
from typing import Any

EXCLUDED_DIRS = {".git", "__pycache__", ".mypy_cache", ".pytest_cache", "node_modules", "dist", "build"}


def validate_file(path: Path) -> dict[str, Any]:
    result: dict[str, Any] = {
        "path": str(path),
        "exists": path.exists(),
        "ok": False,
        "error": None,
    }
    if not path.exists():
        result["error"] = "File not found."
        return result

    try:
        source = path.read_text(encoding="utf-8")
        ast.parse(source, filename=str(path))
        result["ok"] = True
    except SyntaxError as exc:
        result["error"] = {
            "type": "SyntaxError",
            "message": exc.msg,
            "line": exc.lineno,
            "offset": exc.offset,
            "text": exc.text.strip() if exc.text else None,
        }
    except Exception as exc:
        result["error"] = {"type": type(exc).__name__, "message": str(exc)}
    return result


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


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Python syntax for one or more files or folders.")
    parser.add_argument("paths", nargs="+", help="Python files or folders to parse.")
    parser.add_argument("--json", action="store_true", help="Emit structured JSON.")
    args = parser.parse_args()

    paths: list[Path] = []
    for raw in args.paths:
        paths.extend(iter_python_files(Path(raw)))
    results = [validate_file(path.resolve()) for path in paths]
    summary = {
        "validator": "syntax_validator",
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
            if item["error"]:
                print(f"  {item['error']}")
    return 0 if summary["all_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
