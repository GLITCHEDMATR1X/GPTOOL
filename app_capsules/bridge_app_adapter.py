from __future__ import annotations
import argparse, subprocess, sys
from pathlib import Path
APP_DIR = Path(__file__).resolve().parent

def _run(script: str, args: list[str]) -> int:
    return subprocess.call([sys.executable, str(APP_DIR / script), *args])

def command_app_menu(args): return _run("app_bridge_menu.py", [])
def command_app_scan(args): return _run("app_scanner.py", [args.project, "--output-dir", args.output_dir] + (["--json"] if args.json else []))
def command_app_migrate_plan(args):
    cmd=[args.project,"--target",args.target,"--output-dir",args.output_dir]
    if args.app_id: cmd += ["--app-id",args.app_id]
    if args.title: cmd += ["--title",args.title]
    if args.write_sample_capsule: cmd += ["--write-sample-capsule"]
    if args.json: cmd += ["--json"]
    return _run("framework_migration.py", cmd)
def command_app_adapter_audit(args): return _run("adapter_audit.py", [args.project,"--output-dir",args.output_dir] + (["--json"] if args.json else []))
def command_app_validate(args): return _run("validate_capsule.py", [args.app_root,"--output-dir",args.output_dir] + (["--json"] if args.json else []))

def add_app_capsule_commands(sub) -> None:
    m=sub.add_parser("app-menu", help="Open the App Capsule Bridge menu."); m.set_defaults(func=command_app_menu)
    s=sub.add_parser("app-scan", help="Scan a Python app and classify framework/capsule risks."); s.add_argument("project"); s.add_argument("--output-dir",default="reports/app_capsule"); s.add_argument("--json",action="store_true"); s.set_defaults(func=command_app_scan)
    p=sub.add_parser("app-migrate-plan", help="Plan pygame/tkinter/Panda3D to app-capsule migration."); p.add_argument("project"); p.add_argument("--target",default="panda3d_same_window"); p.add_argument("--app-id"); p.add_argument("--title"); p.add_argument("--output-dir",default="reports/app_capsule"); p.add_argument("--write-sample-capsule",action="store_true"); p.add_argument("--json",action="store_true"); p.set_defaults(func=command_app_migrate_plan)
    a=sub.add_parser("app-adapter-audit", help="Audit adapter/bridge/wrapper files for host ownership risk."); a.add_argument("project"); a.add_argument("--output-dir",default="reports/app_capsule"); a.add_argument("--json",action="store_true"); a.set_defaults(func=command_app_adapter_audit)
    v=sub.add_parser("app-validate", help="Validate app_manifest.json and capsule lifecycle object."); v.add_argument("app_root"); v.add_argument("--output-dir",default="reports/app_capsule"); v.add_argument("--json",action="store_true"); v.set_defaults(func=command_app_validate)
