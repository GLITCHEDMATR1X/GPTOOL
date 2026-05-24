from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
from typing import Any, Iterable


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
    if path.is_dir():
        result["error"] = "Directory input must be expanded before validation."
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


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate Python syntax for one or more files or directories."
    )
    parser.add_argument("paths", nargs="+", help="Python files or directories to parse.")
    parser.add_argument("--json", action="store_true", help="Emit structured JSON.")
    args = parser.parse_args()

    expanded_paths = expand_paths(args.paths)
    results = [validate_file(path) for path in expanded_paths]
    summary = {
        "validator": "syntax_validator",
        "input_paths": [str(Path(raw).resolve()) for raw in args.paths],
        "expanded_count": len(expanded_paths),
        "all_ok": bool(results) and all(item["ok"] for item in results),
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
