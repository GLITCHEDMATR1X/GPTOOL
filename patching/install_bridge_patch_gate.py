#!/usr/bin/env python3
"""Safely install AI Patch Gate bridge.py command hooks.

Default is dry-run. Use --apply after reviewing the printed plan. This script
creates a .bak copy and only performs narrow text insertions:
  1. import add_patch_gate_commands from patching.bridge_patch_adapter
  2. call add_patch_gate_commands(sub) after argparse subparsers are created
"""
from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import sys

IMPORT_LINE = "from patching.bridge_patch_adapter import add_patch_gate_commands\n"
CALL_LINE = "    add_patch_gate_commands(sub)\n"
SUBPARSER_MARKER = "    sub = parser.add_subparsers(dest=\"command\", required=True)\n"


def patch_bridge(path: Path, *, apply: bool) -> int:
    if not path.exists():
        print(f"bridge.py not found: {path}")
        return 2
    text = path.read_text(encoding="utf-8", errors="replace")
    original = text
    changes: list[str] = []
    if IMPORT_LINE not in text:
        # Prefer inserting after ROOT/sys.path setup imports, before local module imports.
        anchor = "from adapters.panda3d_adapter import "
        idx = text.find(anchor)
        if idx >= 0:
            text = text[:idx] + IMPORT_LINE + text[idx:]
        else:
            text = IMPORT_LINE + text
        changes.append("add bridge_patch_adapter import")
    else:
        changes.append("import already present")
    if CALL_LINE not in text:
        if SUBPARSER_MARKER not in text:
            print("Could not find argparse subparser marker in bridge.py; no changes made.")
            return 3
        text = text.replace(SUBPARSER_MARKER, SUBPARSER_MARKER + "\n" + CALL_LINE, 1)
        changes.append("add add_patch_gate_commands(sub) call")
    else:
        changes.append("subparser call already present")

    print("Bridge patch gate install plan:")
    for item in changes:
        print(f"- {item}")
    if text == original:
        print("No bridge.py changes needed.")
        return 0
    if not apply:
        print("\nDry-run only. Re-run with --apply to update bridge.py.")
        return 0
    backup = path.with_suffix(path.suffix + ".patch_gate.bak")
    shutil.copy2(path, backup)
    path.write_text(text, encoding="utf-8")
    print(f"Updated: {path}")
    print(f"Backup:  {backup}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Install Patch Gate commands into GPTOOL bridge.py")
    parser.add_argument("--bridge", default="bridge.py")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    return patch_bridge(Path(args.bridge).resolve(), apply=args.apply)

if __name__ == "__main__":
    raise SystemExit(main())
