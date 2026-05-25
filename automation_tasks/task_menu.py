#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_DIR = ROOT / "task_manifests"


def list_manifests() -> list[Path]:
    return sorted(MANIFEST_DIR.glob("*.json"))


def run_director(args: list[str]) -> int:
    return subprocess.call([sys.executable, str(ROOT / "automation_tasks" / "test_run_director.py"), *args], cwd=str(ROOT))


def main() -> int:
    while True:
        print("\nGPTOOL Automation Task Director")
        print("1. List task manifests")
        print("2. Validate a task manifest")
        print("3. Dry-run a task manifest")
        print("4. Apply/run a task manifest with approval")
        print("5. Create a starter task manifest")
        print("0. Exit")
        choice = input("> ").strip()
        if choice == "0":
            return 0
        if choice == "1":
            for i, path in enumerate(list_manifests(), start=1):
                print(f"{i}. {path}")
        elif choice in {"2", "3", "4"}:
            manifests = list_manifests()
            if not manifests:
                print("No manifests in task_manifests/.")
                continue
            for i, path in enumerate(manifests, start=1):
                print(f"{i}. {path.name}")
            raw = input("Select manifest number or path: ").strip()
            try:
                path = manifests[int(raw) - 1]
            except Exception:
                path = Path(raw)
            if choice == "2":
                run_director(["validate", str(path)])
            elif choice == "3":
                run_director(["run", str(path)])
            else:
                token = input("Type APPLY to run approval-required commands: ").strip()
                run_director(["run", str(path), "--apply", "--approval", token])
        elif choice == "5":
            task_id = input("Task id: ").strip() or "new_task"
            title = input("Title: ").strip() or "New Automation Task"
            project = input("Project path [.]: ").strip() or "."
            output = MANIFEST_DIR / f"{task_id}.json"
            run_director(["new", "--id", task_id, "--title", title, "--project", project, "--output", str(output)])
        else:
            print("Unknown choice.")


if __name__ == "__main__":
    raise SystemExit(main())
