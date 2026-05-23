#!/usr/bin/env python3
from __future__ import annotations
import argparse, importlib.util, json, sys
from pathlib import Path
try:
    from .manifest_schema import read_manifest, validate_manifest
    from .contract import validate_capsule_object
except Exception:
    from manifest_schema import read_manifest, validate_manifest
    from contract import validate_capsule_object

def validate_capsule(root: str | Path) -> dict:
    app_root = Path(root).resolve(); manifest_path = app_root / "app_manifest.json"
    report = {"schema_version": "gptool.capsule_validation.v1", "app_root": str(app_root), "manifest_exists": manifest_path.exists(), "manifest_errors": [], "capsule_errors": [], "ok": False}
    if not manifest_path.exists():
        report["manifest_errors"].append("missing app_manifest.json"); return report
    data = read_manifest(manifest_path); report["manifest"] = data; report["manifest_errors"] = validate_manifest(data, root=app_root)
    entry = app_root / str(data.get("entry", "capsule.py"))
    if entry.exists() and entry.suffix == ".py":
        try:
            spec = importlib.util.spec_from_file_location("_gptool_capsule_candidate", entry)
            mod = importlib.util.module_from_spec(spec); assert spec and spec.loader; spec.loader.exec_module(mod)
            cls = getattr(mod, "Capsule", None) or getattr(mod, "AppCapsule", None)
            if cls is None: report["capsule_errors"].append("entry does not expose Capsule or AppCapsule class")
            else: report["capsule_errors"].extend(validate_capsule_object(cls()))
        except Exception as exc:
            report["capsule_errors"].append(f"entry import failed: {type(exc).__name__}: {exc}")
    report["ok"] = not report["manifest_errors"] and not report["capsule_errors"]
    return report

def main(argv=None):
    p=argparse.ArgumentParser(description="Validate a GPTOOL app capsule manifest and lifecycle object."); p.add_argument("app_root"); p.add_argument("--output-dir",default="reports/app_capsule"); p.add_argument("--json",action="store_true"); a=p.parse_args(argv)
    r=validate_capsule(a.app_root); out=Path(a.output_dir); out.mkdir(parents=True, exist_ok=True); (out/"capsule_validation.json").write_text(json.dumps(r,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(r, indent=2) if a.json else f"Capsule validation: {'PASS' if r.get('ok') else 'FAIL'} -> {out/'capsule_validation.json'}")
    return 0 if r.get("ok") else 1
if __name__ == "__main__": raise SystemExit(main())
