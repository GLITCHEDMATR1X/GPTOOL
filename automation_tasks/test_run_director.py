#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from automation_tasks.task_schema import load_manifest, validate_manifest
    from automation_tasks.task_runner import TaskRunner, render_markdown
else:
    from .task_schema import load_manifest, validate_manifest
    from .task_runner import TaskRunner, render_markdown


def command_validate(args: argparse.Namespace) -> int:
    data = load_manifest(args.manifest, root_config=getattr(args, "root_config", None))
    report = validate_manifest(data)
    print(json.dumps(report, indent=2) if args.json else ("PASS" if report["ok"] else "FAIL"))
    return 0 if report["ok"] else 2


def command_run(args: argparse.Namespace) -> int:
    data = load_manifest(args.manifest, root_config=getattr(args, "root_config", None))
    validation = validate_manifest(data)
    report_dir = Path(args.report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    if not validation["ok"]:
        report = {"ok": False, "validation": validation, "id": data.get("id")}
    else:
        runner = TaskRunner(data, apply=args.apply, approval=args.approval, report_dir=report_dir)
        report = runner.run()
        report["validation"] = validation
    json_path = report_dir / f"{data.get('id', 'task')}_run_report.json"
    md_path = report_dir / f"{data.get('id', 'task')}_run_report.md"
    json_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"Task report: {json_path}")
        print(f"Task markdown: {md_path}")
        print(f"Result: {'PASS' if report.get('ok') else 'FAIL'}")
    return 0 if report.get("ok") else 2


def command_new(args: argparse.Namespace) -> int:
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    sample = {
        "schema": "gptool.task.v1",
        "id": args.id,
        "title": args.title,
        "requires_approval": True,
        "steps": [
            {"action": "note", "label": "purpose", "message": "Describe the game journey or patch workflow here."},
            {"action": "assert_dir_exists", "label": "project root exists", "path": args.project},
            {"action": "command", "label": "compile project", "cmd": "python -m compileall -q .", "cwd": args.project, "run_in_dry_run": False, "timeout": 120},
        ],
    }
    target.write_text(json.dumps(sample, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote task manifest: {target}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="GPTOOL Automation Task Director")
    sub = parser.add_subparsers(dest="command", required=True)
    val = sub.add_parser("validate")
    val.add_argument("manifest")
    val.add_argument("--root-config", help="Optional local_project_roots.json path for ${root} expansion.")
    val.add_argument("--json", action="store_true")
    val.set_defaults(func=command_validate)
    run = sub.add_parser("run")
    run.add_argument("manifest")
    run.add_argument("--root-config", help="Optional local_project_roots.json path for ${root} expansion.")
    run.add_argument("--apply", action="store_true", help="Actually run write/launch commands. Dry-run by default.")
    run.add_argument("--approval", default="", help="Use APPLY for approval-required steps.")
    run.add_argument("--report-dir", default="reports/automation_tasks")
    run.add_argument("--json", action="store_true")
    run.set_defaults(func=command_run)
    new = sub.add_parser("new")
    new.add_argument("--id", required=True)
    new.add_argument("--title", required=True)
    new.add_argument("--project", default=".")
    new.add_argument("--output", required=True)
    new.set_defaults(func=command_new)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
