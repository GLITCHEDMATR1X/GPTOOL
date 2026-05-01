from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

SECTION_HEADERS = [
    "Goal",
    "Hard standards",
    "Implementation checklist",
    "Acceptance checklist",
    "Failure conditions",
    "Reference links",
]

HARD_TAG = "[HARD]"

def _split_mechanics(text: str) -> list[tuple[str, str]]:
    matches = list(re.finditer(r"^# (.+)$", text, flags=re.MULTILINE))
    mechanics: list[tuple[str, str]] = []
    for idx, match in enumerate(matches):
        title = match.group(1).strip()
        if title.lower().startswith("mechanic standards pack"):
            continue
        start = match.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        block = text[start:end].strip()
        if any(header in block for header in SECTION_HEADERS):
            mechanics.append((title, block))
    return mechanics

def _extract_section(block: str, section_name: str) -> str:
    pattern = re.compile(rf"^## {re.escape(section_name)}\s*$", flags=re.MULTILINE)
    match = pattern.search(block)
    if not match:
        return ""
    start = match.end()
    end = len(block)
    for next_section in SECTION_HEADERS:
        if next_section == section_name:
            continue
        next_pattern = re.compile(rf"^## {re.escape(next_section)}\s*$", flags=re.MULTILINE)
        next_match = next_pattern.search(block, start)
        if next_match:
            end = min(end, next_match.start())
    return block[start:end].strip()

def _extract_bullets(section_text: str) -> list[str]:
    bullets = []
    for line in section_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("- "):
            bullets.append(stripped[2:].strip())
        elif stripped.startswith("[ ] ") or stripped.startswith("[x] ") or stripped.startswith("[X] "):
            bullets.append(stripped[4:].strip())
    return bullets

def _extract_checklist(section_text: str) -> list[dict[str, Any]]:
    items = []
    for line in section_text.splitlines():
        stripped = line.strip()
        checkbox = re.match(r"^- \[([ xX])\]\s+(.*)$", stripped)
        if checkbox:
            items.append({"checked": checkbox.group(1).lower() == "x", "text": checkbox.group(2).strip()})
            continue
        bullet = re.match(r"^- (.*)$", stripped)
        if bullet:
            items.append({"checked": False, "text": bullet.group(1).strip()})
    return items

def parse_mechanics(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="replace")
    blocks = _split_mechanics(text)
    mechanics = []
    for title, block in blocks:
        goal = _extract_section(block, "Goal")
        hard = _extract_checklist(_extract_section(block, "Hard standards"))
        impl = _extract_checklist(_extract_section(block, "Implementation checklist"))
        accept = _extract_checklist(_extract_section(block, "Acceptance checklist"))
        fail = _extract_checklist(_extract_section(block, "Failure conditions"))
        refs = _extract_bullets(_extract_section(block, "Reference links"))
        mechanics.append({
            "name": title,
            "slug": re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_"),
            "goal": " ".join(goal.split()),
            "hard_standards": hard,
            "implementation_checklist": impl,
            "acceptance_checklist": accept,
            "failure_conditions": fail,
            "reference_links": refs,
            "hard_rule_count": sum(1 for item in hard if HARD_TAG in item["text"]),
        })
    return {
        "source_path": str(path),
        "mechanic_count": len(mechanics),
        "mechanics": mechanics,
    }

def main() -> int:
    parser = argparse.ArgumentParser(description="Convert mechanic standards markdown into a machine-readable manifest.")
    parser.add_argument("path", help="Mechanic standards markdown file.")
    parser.add_argument("--json", action="store_true", help="Emit JSON to stdout.")
    parser.add_argument("--out", help="Optional output JSON path.")
    args = parser.parse_args()

    report = parse_mechanics(Path(args.path).resolve())
    if args.out:
        out_path = Path(args.out).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    if args.json or not args.out:
        print(json.dumps(report, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
