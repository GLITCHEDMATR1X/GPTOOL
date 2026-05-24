from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

TEXT_LITERAL_RE = re.compile(r'["\']([^"\']{40,})["\']')
SMALL_SCALE_RE = re.compile(r"\b(?:scale|text_scale|textScale)\s*=\s*0\.(0[0-9]|1[0-2])")

def validate_text_fit(path: Path) -> dict[str, Any]:
    path = path.resolve()
    report: dict[str, Any] = {
        "path": str(path),
        "ok": True,
        "warnings": [],
        "notes": [
            "This validator flags likely text-density and tiny-scale risks.",
            "It cannot measure rendered font bounds without a running UI."
        ]
    }
    if not path.exists():
        report["ok"] = False
        report["warnings"].append({"type": "missing_file", "message": "File not found."})
        return report

    for lineno, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
        for literal in TEXT_LITERAL_RE.findall(line):
            dense = " " in literal and len(literal) > 80
            if dense:
                report["warnings"].append({
                    "type": "long_text_literal",
                    "line": lineno,
                    "message": "Long text literal may need wrapping, scrolling, or truncation.",
                    "source": line.strip()[:240],
                })
        if SMALL_SCALE_RE.search(line):
            report["warnings"].append({
                "type": "small_text_scale_risk",
                "line": lineno,
                "message": "Very small text scale may be unreadable at normal viewing distance.",
                "source": line.strip()[:240],
            })
    report["ok"] = len(report["warnings"]) == 0
    return report

def main() -> int:
    parser = argparse.ArgumentParser(description="Heuristic text fit validator for Python UI code.")
    parser.add_argument("path", help="Python file to scan.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = validate_text_fit(Path(args.path))
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
