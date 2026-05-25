#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import shutil

IMPORT_LINE = "from automation_tasks.bridge_task_adapter import add_automation_task_commands\n"
CALL_LINE = "    add_automation_task_commands(sub)\n"
MARKER = "    report = sub.add_parser(\"report\", help=\"Render a JSON report as Markdown text.\")"


def plan(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    return {
        "bridge": str(path),
        "has_import": IMPORT_LINE.strip() in text,
        "has_call": "add_automation_task_commands(sub)" in text,
        "can_insert": MARKER in text,
    }


def apply(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    result = plan(path)
    if not result["has_import"]:
        insert_after = "from maintenance.package_cleaner import analyze_package, clean_package_tree, create_lean_package_zip, render_package_audit_text\n"
        if insert_after in text:
            text = text.replace(insert_after, insert_after + IMPORT_LINE, 1)
        else:
            text = IMPORT_LINE + text
    if not result["has_call"]:
        if MARKER not in text:
            raise RuntimeError("Could not find parser insertion marker")
        text = text.replace(MARKER, CALL_LINE + "\n" + MARKER, 1)
    backup = path.with_suffix(path.suffix + ".before_automation_tasks.bak")
    shutil.copy2(path, backup)
    path.write_text(text, encoding="utf-8")
    after = plan(path)
    after["backup"] = str(backup)
    return after


def main() -> int:
    parser = argparse.ArgumentParser(description="Install GPTOOL Automation Task Director bridge.py commands.")
    parser.add_argument("--bridge", default="bridge.py")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    path = Path(args.bridge).resolve()
    result = apply(path) if args.apply else plan(path)
    for k, v in result.items():
        print(f"{k}: {v}")
    if not args.apply:
        print("Dry-run only. Re-run with --apply to modify bridge.py.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
