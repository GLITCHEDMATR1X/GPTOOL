#!/usr/bin/env python3
from __future__ import annotations
import os, subprocess, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app_capsules"
LOG_DIR = ROOT / "app_capsule_launcher_logs"
LOG_DIR.mkdir(exist_ok=True)

def run(args):
    print("\n> " + " ".join(str(x) for x in args))
    proc = subprocess.run([sys.executable, *map(str,args)], cwd=str(ROOT), text=True)
    print(f"exit={proc.returncode}")
    return proc.returncode

def prompt_path(label):
    raw = input(label).strip().strip('"')
    return raw or "."

def main():
    while True:
        print("\nGPTOOL App Capsule Bridge")
        print("1. Scan app/framework")
        print("2. Build migration plan")
        print("3. Audit adapters/bridges")
        print("4. Validate capsule manifest")
        print("5. Show quick examples")
        print("0. Exit")
        choice = input("Choose: ").strip()
        if choice == "0": return 0
        if choice == "1": run([APP/"app_scanner.py", prompt_path("Project/app folder: ")])
        elif choice == "2": run([APP/"framework_migration.py", prompt_path("Project/app folder: "), "--write-sample-capsule"])
        elif choice == "3": run([APP/"adapter_audit.py", prompt_path("Project/app folder: ")])
        elif choice == "4": run([APP/"validate_capsule.py", prompt_path("Capsule folder: ")])
        elif choice == "5":
            print("\nExamples:")
            print("python bridge.py app-scan data/HoloVerse")
            print("python bridge.py app-migrate-plan SomePygameGame --target panda3d_same_window")
            print("python bridge.py app-adapter-audit data/HoloVerse")
            print("python bridge.py app-validate data/HoloVerse/HoloCore")
        else: print("Unknown choice")
if __name__ == "__main__":
    try: raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}"); input("Press Enter to close..."); raise
