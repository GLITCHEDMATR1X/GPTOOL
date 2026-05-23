#!/usr/bin/env python3
from __future__ import annotations
import argparse, ast, json
from pathlib import Path
from typing import Any

FRAMEWORK_IMPORTS = {
    "pygame": {"pygame"},
    "panda3d": {"panda3d", "direct"},
    "tkinter": {"tkinter", "tkinterdnd2"},
    "pyqt": {"PyQt5", "PyQt6", "PySide2", "PySide6"},
}
DANGEROUS_CALLS = {
    "sys.exit": "direct process exit",
    "os._exit": "hard process exit",
    "pygame.display.set_mode": "pygame owns window",
    "pygame.event.get": "pygame event pump",
    "pygame.mixer.init": "pygame owns audio mixer",
    "taskMgr.remove": "direct Panda3D task removal",
    "base.destroy": "direct Panda3D base destroy",
    "ShowBase": "creates/owns Panda3D ShowBase",
}
EXCLUDED_PARTS = {".git", "__pycache__", ".pytest_cache", ".mypy_cache", "build", "dist", "node_modules", "reports"}

def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _call_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return ""

def _scan_python_file(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="replace")
    result = {"path": str(path), "imports": [], "frameworks": [], "dangerous_calls": [], "classes": [], "functions": [], "has_while_loop": False, "syntax_ok": True, "syntax_error": None}
    try:
        tree = ast.parse(text, filename=str(path))
    except SyntaxError as exc:
        result["syntax_ok"] = False
        result["syntax_error"] = f"{exc.msg} line {exc.lineno}"
        return result
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
        elif isinstance(node, ast.ClassDef):
            result["classes"].append(node.name)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            result["functions"].append(node.name)
        elif isinstance(node, ast.While):
            result["has_while_loop"] = True
        elif isinstance(node, ast.Call):
            name = _call_name(node.func)
            for needle, reason in DANGEROUS_CALLS.items():
                if name == needle or name.endswith("." + needle):
                    result["dangerous_calls"].append({"call": name, "reason": reason, "line": getattr(node, "lineno", None)})
    result["imports"] = sorted(imports)
    frameworks = set()
    for framework, roots in FRAMEWORK_IMPORTS.items():
        if imports.intersection(roots):
            frameworks.add(framework)
    if "pygame." in text:
        frameworks.add("pygame")
    if "ShowBase" in text or "panda3d." in text or "direct." in text:
        frameworks.add("panda3d")
    result["frameworks"] = sorted(frameworks)
    return result

def scan_app(root: str | Path, *, max_files: int = 5000) -> dict[str, Any]:
    app_root = Path(root).resolve()
    files: list[dict[str, Any]] = []
    for path in sorted(app_root.rglob("*.py")):
        try: rel = path.relative_to(app_root)
        except Exception: rel = path
        if any(part in EXCLUDED_PARTS for part in rel.parts):
            continue
        files.append(_scan_python_file(path))
        if len(files) >= max_files:
            break
    frameworks: dict[str, int] = {}
    dangerous: list[dict[str, Any]] = []
    while_loops = syntax_failed = 0
    for item in files:
        for fw in item.get("frameworks", []):
            frameworks[fw] = frameworks.get(fw, 0) + 1
        if item.get("has_while_loop"):
            while_loops += 1
        if not item.get("syntax_ok"):
            syntax_failed += 1
        for call in item.get("dangerous_calls", []):
            dangerous.append({"path": item["path"], **call})
    detected = sorted(frameworks, key=lambda key: (-frameworks[key], key))
    recommended_kind = "legacy_quarantine"
    if detected and detected[0] == "panda3d" and "pygame" not in detected:
        recommended_kind = "panda3d_same_window"
    elif "pygame" in detected:
        recommended_kind = "pygame_legacy"
    elif "tkinter" in detected:
        recommended_kind = "tkinter_tool"
    elif not detected:
        recommended_kind = "data_module"
    blockers: list[str] = []
    if syntax_failed:
        blockers.append(f"{syntax_failed} Python files have syntax errors")
    if "pygame" in detected:
        blockers.append("pygame apps need loop/window/audio migration before Panda3D same-window use")
    if dangerous:
        blockers.append(f"{len(dangerous)} host-ownership/dangerous calls need review")
    return {"schema_version": "gptool.app_scan.v1", "project_root": str(app_root), "python_file_count": len(files), "framework_counts": frameworks, "detected_frameworks": detected, "recommended_kind": recommended_kind, "while_loop_files": while_loops, "syntax_failed_files": syntax_failed, "dangerous_calls": dangerous[:200], "blockers": blockers, "files": files[:500]}

def render_markdown(report: dict[str, Any]) -> str:
    lines = ["# GPTOOL App Scan Report", "", f"- Project: `{report.get('project_root')}`", f"- Python files: `{report.get('python_file_count')}`", f"- Detected frameworks: `{', '.join(report.get('detected_frameworks') or ['none'])}`", f"- Recommended capsule kind: `{report.get('recommended_kind')}`", f"- While-loop files: `{report.get('while_loop_files')}`", "", "## Framework counts", ""]
    for name, count in sorted((report.get("framework_counts") or {}).items()):
        lines.append(f"- `{name}`: {count}")
    if report.get("blockers"):
        lines += ["", "## Blockers / Review Items", ""] + [f"- {x}" for x in report.get("blockers", [])]
    if report.get("dangerous_calls"):
        lines += ["", "## Host Ownership / Dangerous Calls", ""]
        for item in report.get("dangerous_calls", [])[:50]:
            lines.append(f"- `{Path(item.get('path','')).name}` line {item.get('line')}: `{item.get('call')}` — {item.get('reason')}")
    return "\n".join(lines) + "\n"

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scan a Python app and classify it for GPTOOL app-capsule integration.")
    parser.add_argument("project")
    parser.add_argument("--max-files", type=int, default=5000)
    parser.add_argument("--output-dir", default="reports/app_capsule")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = scan_app(args.project, max_files=args.max_files)
    out_dir = Path(args.output_dir); out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "app_scan_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (out_dir / "app_scan_report.md").write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps(report, indent=2) if args.json else f"App scan: {report.get('recommended_kind')} frameworks={','.join(report.get('detected_frameworks') or ['none'])}\nReport: {out_dir / 'app_scan_report.md'}")
    return 0 if not report.get("syntax_failed_files") else 1

if __name__ == "__main__":
    raise SystemExit(main())
