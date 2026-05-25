#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def _run(args: list[str]) -> int:
    return subprocess.call([sys.executable, str(ROOT / "automation_tasks" / "test_run_director.py"), *args], cwd=str(ROOT))


def command_task_menu(args: argparse.Namespace) -> int:
    return subprocess.call([sys.executable, str(ROOT / "automation_tasks" / "task_menu.py")], cwd=str(ROOT))


def command_task_validate(args: argparse.Namespace) -> int:
    return _run(["validate", args.manifest, *( ["--json"] if args.json else [] )])


def command_task_run(args: argparse.Namespace) -> int:
    cmd = ["run", args.manifest, "--report-dir", args.report_dir]
    if args.apply:
        cmd.append("--apply")
    if args.approval:
        cmd.extend(["--approval", args.approval])
    if args.json:
        cmd.append("--json")
    return _run(cmd)


def command_task_new(args: argparse.Namespace) -> int:
    return _run(["new", "--id", args.id, "--title", args.title, "--project", args.project, "--output", args.output])


def add_automation_task_commands(sub) -> None:
    menu = sub.add_parser("task-menu", help="Open GPTOOL Automation Task Director menu.")
    menu.set_defaults(func=command_task_menu)

    validate = sub.add_parser("task-validate", help="Validate a GPTOOL task manifest.")
    validate.add_argument("manifest")
    validate.add_argument("--json", action="store_true")
    validate.set_defaults(func=command_task_validate)

    run = sub.add_parser("task-run", help="Dry-run or apply a GPTOOL task manifest.")
    run.add_argument("manifest")
    run.add_argument("--apply", action="store_true")
    run.add_argument("--approval", default="")
    run.add_argument("--report-dir", default="reports/automation_tasks")
    run.add_argument("--json", action="store_true")
    run.set_defaults(func=command_task_run)

    new = sub.add_parser("task-new", help="Create a starter GPTOOL task manifest.")
    new.add_argument("--id", required=True)
    new.add_argument("--title", required=True)
    new.add_argument("--project", default=".")
    new.add_argument("--output", required=True)
    new.set_defaults(func=command_task_new)
