from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

# Conservative heuristic scanner for common off-screen / overlap-prone direct placement patterns.
PIXEL_CALL_RE = re.compile(r"\b(?:setPos|pos)\s*\(\s*([0-9]{3,5})\s*,\s*([0-9]{3,5})")
RAW_COORD_RE = re.compile(r"\b(?:x|y|width|height)\s*=\s*([0-9]{3,5})")

def validate_ui_bounds(path: Path, width: int = 1920, height: int = 1080) -> dict[str, Any]:
    path = path.resolve()
    report: dict[str, Any] = {
        "path": str(path),
        "ok": True,
        "warnings": [],
        "notes": [
            "This is a heuristic static validator for direct-placement UI risks.",
            "Layout-managed UIs may be safe even when raw numbers appear large."
        ]
    }
    if not path.exists():
        report["ok"] = False
        report["warnings"].append({"type": "missing_file", "message": "File not found."})
        return report

    text = path.read_text(encoding="utf-8", errors="replace")
    for lineno, line in enumerate(text.splitlines(), start=1):
        for match in PIXEL_CALL_RE.finditer(line):
            x = int(match.group(1))
            y = int(match.group(2))
            if x > width or y > height:
                report["warnings"].append({
                    "type": "pixel_position_risk",
                    "line": lineno,
                    "message": f"Direct UI position may exceed target bounds: ({x}, {y}).",
                    "source": line.strip()[:240],
                })
        if "DirectButton" in line or "DirectLabel" in line or "DirectFrame" in line:
            if any(num in line for num in ["1.2", "1.3", "1.4", "1.5", "2.0"]):
                report["warnings"].append({
                    "type": "normalized_position_risk",
                    "line": lineno,
                    "message": "Normalized UI coordinate may extend beyond visible bounds.",
                    "source": line.strip()[:240],
                })
    report["ok"] = len(report["warnings"]) == 0
    return report

def main() -> int:
    parser = argparse.ArgumentParser(description="Heuristic UI bounds validator for Python UI code.")
    parser.add_argument("path", help="Python file to scan.")
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = validate_ui_bounds(Path(args.path), width=args.width, height=args.height)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        status = "PASS" if report["ok"] else "WARN"
        print(f"[{status}] {report['path']}")
        for item in report["warnings"][:20]:
            print(f"- line {item.get('line', '?')}: {item['message']}")
    return 0 if report["ok"] else 1

if __name__ == "__main__":
    raise SystemExit(main())
