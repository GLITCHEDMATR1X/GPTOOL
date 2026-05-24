#!/usr/bin/env python3
"""Scan-friendly HoloVerse UI target helper.

This script intentionally does not rewrite files. It prints the known UI/HUD
owners from ui_manifest.json so future passes can check the current UI surface
without searching the whole repository.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / "ui_manifest.json"


def _iter_entries(value):
    if isinstance(value, dict):
        if "path" in value:
            yield value
        for child in value.values():
            yield from _iter_entries(child)
    elif isinstance(value, list):
        for item in value:
            yield from _iter_entries(item)


def main() -> None:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    authority = data.get("dominant_ui_authority", {})
    print("HoloVerse UI Authority")
    print("=" * 24)
    print(f"dominant: {authority.get('path', 'unknown')}")
    print()
    print("Known UI/HUD files:")
    grouped = data.get("grouped_ui_sources", {})
    for group_name, group_value in grouped.items():
        print(f"\n[{group_name}]")
        for entry in _iter_entries(group_value):
            path = entry.get("path", "")
            engine = entry.get("engine", "")
            status = entry.get("status", "")
            action = entry.get("migration_action", "")
            wrapper = entry.get("wrapper", "")
            suffix = f" | {engine}" if engine else ""
            if status:
                suffix += f" | {status}"
            print(f"- {path}{suffix}")
            if wrapper:
                print(f"  wrapper: {wrapper}")
            if action:
                print(f"  action: {action}")


if __name__ == "__main__":
    main()
