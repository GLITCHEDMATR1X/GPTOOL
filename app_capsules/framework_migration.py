#!/usr/bin/env python3
from __future__ import annotations
import argparse, json
from pathlib import Path
from typing import Any
try:
    from .app_scanner import scan_app
    from .manifest_schema import default_manifest, write_manifest
except Exception:
    from app_scanner import scan_app
    from manifest_schema import default_manifest, write_manifest

PYGAME_PORTABILITY = {
    "logic": ["score/state/timers", "enemy wave rules", "weapon cooldowns", "collision intent", "save/config data"],
    "convert": ["pygame.Surface / blit rendering", "pygame.Rect camera-space collision", "pygame.draw primitives", "pygame.display.set_mode window ownership", "pygame.event pump", "pygame.mixer audio ownership", "while running loop"],
    "target": ["logic/game_state.py", "panda3d_view/scene.py", "panda3d_view/hud.py", "capsule.py", "app_manifest.json", "legacy/original_pygame_main.py"],
}

def build_migration_plan(project: str | Path, *, target: str = "panda3d_same_window", app_id: str | None = None, title: str | None = None) -> dict[str, Any]:
    scan = scan_app(project)
    root = Path(project).resolve()
    detected = scan.get("detected_frameworks") or []
    source = "unknown"
    if "pygame" in detected: source = "pygame"
    elif "panda3d" in detected: source = "panda3d"
    elif "tkinter" in detected: source = "tkinter"
    elif not detected: source = "data_module"
    if source == "pygame" and target == "panda3d_same_window": strategy = "extract_logic_rebuild_panda3d_view"
    elif source == "panda3d" and target == "panda3d_same_window": strategy = "capsule_wrap_panda3d"
    elif source == "tkinter": strategy = "tool_panel_or_subprocess"
    elif source == "data_module": strategy = "data_capsule"
    else: strategy = "quarantine"
    app_id = app_id or root.name.lower().replace(" ", "_").replace("-", "_")
    title = title or root.name
    manifest = default_manifest(app_id, title, kind=target if source != "pygame" else "legacy_quarantine", entry="capsule.py")
    if source == "pygame":
        steps = [
            {"phase": "preserve", "action": "copy original pygame entry into legacy/ without editing it"},
            {"phase": "extract", "action": "move portable rules/state into logic/ modules"},
            {"phase": "replace-loop", "action": "replace while-running loop with capsule.update(dt)"},
            {"phase": "replace-window", "action": "remove pygame.display.set_mode from active capsule"},
            {"phase": "replace-render", "action": "rebuild Surface/blit/draw visuals as Panda3D nodes or UI"},
            {"phase": "replace-input", "action": "map pygame key/mouse checks to host.input service"},
            {"phase": "replace-audio", "action": "route mixer sounds through host.audio service"},
            {"phase": "validate", "action": "run syntax/import/capsule validation and Panda3D smoke"},
        ]
    elif source == "panda3d":
        steps = [
            {"phase": "isolate", "action": "move app-owned nodes under assigned capsule root"},
            {"phase": "host-services", "action": "replace direct camera/audio/task/window ownership with host services"},
            {"phase": "cleanup", "action": "ensure cleanup removes only owned nodes/tasks/ui"},
            {"phase": "validate", "action": "run capsule cleanup and route-safety checks"},
        ]
    elif source == "tkinter":
        steps = [
            {"phase": "classify", "action": "decide whether this is a GX tool panel or subprocess tool"},
            {"phase": "wrap", "action": "expose launch/close/report contract"},
            {"phase": "protect", "action": "prevent tkinter mainloop from owning game host loop"},
        ]
    else:
        steps = [{"phase": "manifest", "action": "create data_module manifest and validators"}]
    blockers = list(scan.get("blockers") or [])
    if source == "pygame" and target == "panda3d_same_window":
        blockers.append("Do not enable same-window mode until pygame loop/window/audio ownership is converted")
    return {"schema_version": "gptool.framework_migration_plan.v1", "project_root": str(root), "source_framework": source, "target_kind": target, "migration_kind": strategy, "scan_summary": {"detected_frameworks": detected, "dangerous_call_count": len(scan.get("dangerous_calls") or []), "while_loop_files": scan.get("while_loop_files"), "syntax_failed_files": scan.get("syntax_failed_files")}, "recommended_manifest": manifest, "pygame_portability": PYGAME_PORTABILITY if source == "pygame" else {}, "steps": steps, "blockers": blockers}

def render_markdown(plan: dict[str, Any]) -> str:
    lines = ["# GPTOOL Framework Migration Plan", "", f"- Project: `{plan.get('project_root')}`", f"- Source framework: `{plan.get('source_framework')}`", f"- Target kind: `{plan.get('target_kind')}`", f"- Migration strategy: `{plan.get('migration_kind')}`", "", "## Steps", ""]
    for step in plan.get("steps", []): lines.append(f"- **{step.get('phase')}**: {step.get('action')}")
    if plan.get("blockers"):
        lines += ["", "## Blockers / Requires Approval", ""] + [f"- {x}" for x in plan.get("blockers", [])]
    if plan.get("source_framework") == "pygame":
        lines += ["", "## Pygame to Panda3D Split", ""]
        for key in ("logic", "convert", "target"):
            lines.append(f"### {key.title()}")
            lines += [f"- {item}" for item in plan.get("pygame_portability", {}).get(key, [])]
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"

def maybe_write_sample_capsule(output_dir: Path, manifest: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    write_manifest(output_dir / "app_manifest.json", manifest)
    (output_dir / "capsule.py").write_text('''from __future__ import annotations\n\nclass Capsule:\n    def __init__(self):\n        self.host = None\n        self.active = False\n        self.result = {"exit_reason": "not_started", "discoveries": []}\n    def prepare(self, host): self.host = host\n    def enter(self, context=None):\n        self.active = True; self.result["exit_reason"] = "active"\n    def update(self, dt: float):\n        if not self.active: return\n    def exit(self, reason: str = "return_to_host"):\n        self.active = False; self.result["exit_reason"] = reason\n    def cleanup(self): self.active = False\n    def get_result(self): return dict(self.result)\n''', encoding="utf-8")

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create a framework migration/capsule plan for a Python app.")
    parser.add_argument("project"); parser.add_argument("--target", default="panda3d_same_window"); parser.add_argument("--app-id"); parser.add_argument("--title"); parser.add_argument("--output-dir", default="reports/app_capsule"); parser.add_argument("--write-sample-capsule", action="store_true"); parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    plan = build_migration_plan(args.project, target=args.target, app_id=args.app_id, title=args.title)
    out = Path(args.output_dir); out.mkdir(parents=True, exist_ok=True)
    (out / "migration_plan.json").write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    (out / "migration_plan.md").write_text(render_markdown(plan), encoding="utf-8")
    if args.write_sample_capsule: maybe_write_sample_capsule(out / "sample_capsule", plan["recommended_manifest"])
    print(json.dumps(plan, indent=2) if args.json else f"Migration plan: {plan.get('migration_kind')} -> {out / 'migration_plan.md'}")
    return 0 if not plan.get("scan_summary", {}).get("syntax_failed_files") else 1
if __name__ == "__main__": raise SystemExit(main())
