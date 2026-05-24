#!/usr/bin/env python3
"""Friendly launcher/menu for Anti-Heroes GPTOOL bridge tools.

This is the file to run when the helper scripts feel like they do not launch.
It keeps output visible, explains missing Panda3D/model-manifest states, and
runs the safest checks first.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPORTS = ROOT / "reports"
MANIFEST = ROOT / "assets" / "characters" / "humans" / "human_manifest.json"


def run_cmd(args: list[str]) -> int:
    print("\n$ " + " ".join(args))
    print("-" * 72)
    try:
        proc = subprocess.run(args, cwd=str(ROOT), check=False)
        print("-" * 72)
        print(f"Exit code: {proc.returncode}")
        return int(proc.returncode)
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}")
        return 1


def show_status() -> None:
    print("\nAnti-Heroes Tools Status")
    print("=" * 72)
    print(f"Folder: {ROOT}")
    print(f"Python: {sys.executable}")
    print(f"Manifest exists: {MANIFEST.exists()}")
    if MANIFEST.exists():
        try:
            data = json.loads(MANIFEST.read_text(encoding="utf-8"))
            print(f"Base assets: {len(data.get('base_assets', []) or [])}")
            print(f"Animations: {len(data.get('animations', []) or [])}")
        except Exception as exc:
            print(f"Manifest parse error: {exc}")
    else:
        print("No synced GPTOOL human manifest yet. Static checks still work; visual model tests may show fallback/no-model warnings.")
    print(f"Reports folder: {REPORTS}")


def print_menu() -> None:
    print("\nChoose a test:")
    print("  1) Run static bridge pipeline")
    print("  2) Initialize/validate spawn roster")
    print("  3) Run state-only runtime adapter proof")
    print("  4) Run visual probes with Panda3D")
    print("  5) Show expected output folders")
    print("  q) Quit")


def show_outputs() -> None:
    print("\nExpected output folders/files:")
    paths = [
        ROOT / "reports" / "antiheroes_gptool_pipeline_report.md",
        ROOT / "reports" / "antiheroes_gptool_pipeline_report.json",
        ROOT / "reports" / "antiheroes_spawn_roster_report.md",
        ROOT / "reports" / "antiheroes_character_runtime_state.json",
        ROOT / "screenshots" / "progress",
        ROOT / "screenshots" / "progress" / "animation_roles",
    ]
    for path in paths:
        print(f"  {'FOUND   ' if path.exists() else 'missing '} {path}")


def main() -> int:
    show_status()
    while True:
        print_menu()
        choice = input("\nSelection: ").strip().lower()
        if choice in {"q", "quit", "exit"}:
            return 0
        if choice == "1":
            run_cmd([sys.executable, "antiheroes_gptool_pipeline.py", "--static"])
        elif choice == "2":
            run_cmd([sys.executable, "antiheroes_spawn_roster.py", "--init-default"])
            run_cmd([sys.executable, "antiheroes_spawn_roster.py", "--validate"])
        elif choice == "3":
            run_cmd([sys.executable, "antiheroes_character_runtime_adapter.py", "--state-only"])
        elif choice == "4":
            print("\nVisual probes require Panda3D. If Panda3D is missing, this will write reports with warnings.")
            run_cmd([sys.executable, "antiheroes_gptool_pipeline.py", "--visual"])
        elif choice == "5":
            show_outputs()
        else:
            print("Unknown selection.")


if __name__ == "__main__":
    raise SystemExit(main())
