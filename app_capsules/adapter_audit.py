#!/usr/bin/env python3
from __future__ import annotations
import argparse, ast, json
from pathlib import Path
from typing import Any
ADAPTER_NAME_HINTS = ("adapter", "bridge", "wrapper", "launcher", "route")
RISK_CALLS = {"taskMgr.remove": "may remove host tasks", "base.destroy": "may destroy host base", "ShowBase": "may create/own window", "subprocess.Popen": "launches subprocess", "subprocess.call": "launches subprocess", "pygame.display.set_mode": "owns pygame display", "pygame.mixer.init": "owns pygame audio", "sys.exit": "exits process"}
EXCLUDED_PARTS = {".git", "__pycache__", ".pytest_cache", "build", "dist", "reports"}
def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name): return node.id
    if isinstance(node, ast.Attribute):
        p = _call_name(node.value); return f"{p}.{node.attr}" if p else node.attr
    return ""
def _audit_file(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="replace"); lines = text.splitlines()
    result = {"path": str(path), "line_count": len(lines), "risk_score": 0, "risks": [], "classes": [], "functions": [], "syntax_ok": True}
    try: tree = ast.parse(text, filename=str(path))
    except SyntaxError as exc:
        result["syntax_ok"] = False; result["risk_score"] += 10; result["risks"].append({"kind": "syntax_error", "reason": f"{exc.msg} line {exc.lineno}"}); return result
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef): result["classes"].append(node.name)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)): result["functions"].append(node.name)
        elif isinstance(node, ast.Call):
            name = _call_name(node.func)
            for needle, reason in RISK_CALLS.items():
                if name == needle or name.endswith("." + needle):
                    result["risk_score"] += 3; result["risks"].append({"kind": "call", "call": name, "line": getattr(node, "lineno", None), "reason": reason})
    if len(lines) > 500: result["risk_score"] += 4; result["risks"].append({"kind": "size", "reason": "adapter-like file is over 500 lines"})
    elif len(lines) > 220: result["risk_score"] += 2; result["risks"].append({"kind": "size", "reason": "adapter-like file is over 220 lines"})
    if any(word in text for word in ("native_panda", "embedded_external", "same_window")): result["risk_score"] += 1; result["risks"].append({"kind": "route", "reason": "contains route/mode keywords"})
    if "cleanup" not in text.lower(): result["risk_score"] += 1; result["risks"].append({"kind": "cleanup", "reason": "no obvious cleanup handling"})
    return result
def audit_adapters(root: str | Path) -> dict[str, Any]:
    project = Path(root).resolve(); candidates = []
    for path in sorted(project.rglob("*.py")):
        try: rel = path.relative_to(project)
        except Exception: rel = path
        if any(part in EXCLUDED_PARTS for part in rel.parts): continue
        s = (path.name + "/" + "/".join(rel.parts)).lower()
        if any(h in s for h in ADAPTER_NAME_HINTS): candidates.append(path)
    audits = [_audit_file(p) for p in candidates]; audits.sort(key=lambda x: (-int(x.get("risk_score", 0)), x.get("path", "")))
    return {"schema_version": "gptool.adapter_audit.v1", "project_root": str(project), "candidate_count": len(audits), "high_risk_count": sum(1 for x in audits if int(x.get("risk_score", 0)) >= 8), "medium_risk_count": sum(1 for x in audits if 4 <= int(x.get("risk_score", 0)) < 8), "audits": audits}
def render_markdown(report):
    lines = ["# GPTOOL Adapter Audit", "", f"- Project: `{report.get('project_root')}`", f"- Adapter candidates: `{report.get('candidate_count')}`", f"- High risk: `{report.get('high_risk_count')}`", f"- Medium risk: `{report.get('medium_risk_count')}`", "", "## Candidates", ""]
    for item in report.get("audits", [])[:100]:
        score = int(item.get("risk_score", 0)); lines += [f"### `{item.get('path')}`", f"- Lines: `{item.get('line_count')}`", f"- Risk score: `{score}`"]
        lines.append("- Recommendation: **convert to capsule/quarantine before expanding**" if score >= 8 else "- Recommendation: review cleanup/host ownership" if score >= 4 else "- Recommendation: low risk")
        for risk in item.get("risks", [])[:12]: lines.append(f"  - {risk.get('kind')}: {risk.get('reason') or risk.get('call')}")
        lines.append("")
    return "\n".join(lines)
def main(argv=None):
    p = argparse.ArgumentParser(description="Audit adapter/bridge/wrapper files for capsule migration risk."); p.add_argument("project"); p.add_argument("--output-dir", default="reports/app_capsule"); p.add_argument("--json", action="store_true"); a=p.parse_args(argv)
    r=audit_adapters(a.project); out=Path(a.output_dir); out.mkdir(parents=True, exist_ok=True); (out/"adapter_audit.json").write_text(json.dumps(r,indent=2)+"\n",encoding="utf-8"); (out/"adapter_audit.md").write_text(render_markdown(r),encoding="utf-8"); print(json.dumps(r, indent=2) if a.json else f"Adapter audit: {r.get('candidate_count')} candidates, high risk={r.get('high_risk_count')}\nReport: {out/'adapter_audit.md'}"); return 0 if not r.get("high_risk_count") else 1
if __name__ == "__main__": raise SystemExit(main())
