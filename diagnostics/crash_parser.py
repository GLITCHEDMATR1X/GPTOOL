from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

SIGNATURES = [
    ("syntax", re.compile(r"SyntaxError|IndentationError")),
    ("import", re.compile(r"ModuleNotFoundError|ImportError")),
    ("asset", re.compile(r"No such file|FileNotFoundError|could not read|Texture::read")),
    ("renderer", re.compile(r"Graphics|OpenGL|Direct3D|Vulkan|X11|window")),
    ("runtime", re.compile(r"Traceback|Exception|Error")),
]

def _parse_structured_json(text: str) -> dict[str, Any] | None:
    try:
        data = json.loads(text)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    known = {"ok", "crash_suspected", "timed_out", "stderr", "stdout", "validator"}
    if not known.intersection(data.keys()):
        return None
    categories: list[str] = []
    if data.get("timed_out"):
        categories.append("timeout")
    if data.get("crash_suspected"):
        categories.append("runtime")
    if not categories:
        categories.append("clean_report")
    return {
        "categories": categories,
        "line_count": len(text.splitlines()),
        "tail": text.splitlines()[-20:],
        "crash_likely": bool(data.get("crash_suspected")) or bool(data.get("timed_out")),
        "structured_report": True,
        "structured_ok": bool(data.get("ok", False)),
    }

def parse_text(text: str) -> dict[str, Any]:
    structured = _parse_structured_json(text)
    if structured is not None:
        return structured

    lines = text.splitlines()
    categories: list[str] = []
    for label, pattern in SIGNATURES:
        if pattern.search(text):
            categories.append(label)

    if not categories and text.strip():
        categories.append("unknown")
    if not text.strip():
        categories.append("empty")

    return {
        "categories": categories,
        "line_count": len(lines),
        "tail": lines[-20:],
        "crash_likely": any(cat in {"syntax", "import", "asset", "renderer", "runtime", "unknown"} for cat in categories if cat != "empty"),
        "structured_report": False,
    }

def parse_file(path: Path) -> dict[str, Any]:
    result: dict[str, Any] = {
        "path": str(path),
        "exists": path.exists(),
        "ok": False,
        "parsed": None,
        "error": None
    }
    if not path.exists():
        result["error"] = "Log file not found."
        return result

    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        result["parsed"] = parse_text(text)
        result["ok"] = True
    except Exception as exc:
        result["error"] = {"type": type(exc).__name__, "message": str(exc)}
    return result

def main() -> int:
    parser = argparse.ArgumentParser(description="Classify a log or crash text file into likely failure categories.")
    parser.add_argument("path", help="Path to a log or crash report.")
    parser.add_argument("--json", action="store_true", help="Emit structured JSON.")
    args = parser.parse_args()

    report = parse_file(Path(args.path).resolve())
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        if not report["ok"]:
            print(f"FAIL: {report['error']}")
            return 1
        parsed = report["parsed"]
        print(f"Categories: {', '.join(parsed['categories'])}")
        print(f"Crash likely: {parsed['crash_likely']}")
    return 0 if report["ok"] else 1

if __name__ == "__main__":
    raise SystemExit(main())
