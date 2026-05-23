#!/usr/bin/env python3
from __future__ import annotations
import argparse, difflib, json
from pathlib import Path

IMPORT_LINE = "from app_capsules.bridge_app_adapter import add_app_capsule_commands"
CALL_LINE = "    add_app_capsule_commands(sub)"
MARKER = "    return parser"

def plan_bridge_patch(bridge_path: Path) -> dict:
    text = bridge_path.read_text(encoding="utf-8")
    notes = []
    new = text
    if IMPORT_LINE not in new:
        anchor = "from maintenance.package_cleaner import analyze_package, clean_package_tree, create_lean_package_zip, render_package_audit_text\n"
        if anchor in new:
            new = new.replace(anchor, anchor + IMPORT_LINE + "\n", 1)
            notes.append("add import for app capsule commands")
        else:
            notes.append("could not find import anchor; import not added")
    else: notes.append("import already present")
    if CALL_LINE not in new:
        if MARKER in new:
            new = new.replace(MARKER, CALL_LINE + "\n\n" + MARKER, 1)
            notes.append("register app capsule commands before return parser")
        else:
            notes.append("could not find return parser marker; command registration not added")
    else: notes.append("command registration already present")
    return {"changed": new != text, "notes": notes, "new_text": new, "old_text": text}

def main(argv=None):
    p=argparse.ArgumentParser(description="Install GPTOOL Pass 18 App Capsule Bridge commands into bridge.py.")
    p.add_argument("--bridge", default="bridge.py"); p.add_argument("--apply", action="store_true"); p.add_argument("--report-dir", default="app_capsule_bridge_install_reports")
    a=p.parse_args(argv); bridge=Path(a.bridge).resolve(); out=Path(a.report_dir); out.mkdir(parents=True, exist_ok=True)
    if not bridge.exists():
        print(f"bridge.py not found: {bridge}"); return 1
    plan=plan_bridge_patch(bridge); diff="".join(difflib.unified_diff(plan["old_text"].splitlines(True),plan["new_text"].splitlines(True),fromfile="bridge.py",tofile="bridge.py.pass18_app_capsules"))
    (out/"bridge_app_capsule_install_plan.json").write_text(json.dumps({"bridge":str(bridge),"changed":plan["changed"],"notes":plan["notes"]},indent=2)+"\n",encoding="utf-8")
    (out/"bridge_app_capsule_install.diff").write_text(diff,encoding="utf-8")
    if a.apply and plan["changed"]:
        backup=bridge.with_suffix(bridge.suffix+".pass18_app_capsules.bak")
        backup.write_text(plan["old_text"],encoding="utf-8")
        bridge.write_text(plan["new_text"],encoding="utf-8")
        print(f"Applied bridge app capsule commands. Backup: {backup}")
    else:
        print(f"Dry-run bridge app capsule install. Report: {out}")
        if not a.apply: print("Re-run with --apply after reviewing the diff.")
    return 0
if __name__ == "__main__": raise SystemExit(main())
