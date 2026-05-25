from __future__ import annotations

import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import time
from typing import Any

from .task_schema import find_junk


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def run_process(cmd: str | list[str], *, cwd: str | Path | None = None, timeout: int = 60, env: dict[str, str] | None = None) -> dict[str, Any]:
    if isinstance(cmd, str):
        shell = os.name == "nt"
        args = cmd if shell else shlex.split(cmd)
    else:
        shell = False
        args = [str(x) for x in cmd]
    started = time.time()
    try:
        proc = subprocess.run(
            args,
            cwd=str(cwd) if cwd else None,
            env={**os.environ, **(env or {})},
            shell=shell,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )
        return {
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "cmd": cmd,
            "cwd": str(cwd) if cwd else None,
            "seconds": round(time.time() - started, 3),
            "stdout": proc.stdout[-12000:],
            "stderr": proc.stderr[-12000:],
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "returncode": None,
            "cmd": cmd,
            "cwd": str(cwd) if cwd else None,
            "seconds": round(time.time() - started, 3),
            "stdout": (exc.stdout or "")[-12000:] if isinstance(exc.stdout, str) else "",
            "stderr": (exc.stderr or "")[-12000:] if isinstance(exc.stderr, str) else "",
            "error": f"timeout after {timeout}s",
        }


class TaskRunner:
    def __init__(self, manifest: dict[str, Any], *, apply: bool = False, approval: str = "", report_dir: str | Path = "reports/automation_tasks"):
        self.manifest = manifest
        self.apply = bool(apply)
        self.approval = approval
        self.report_dir = Path(report_dir)
        self.results: list[dict[str, Any]] = []
        self.blocked = False

    def run(self) -> dict[str, Any]:
        self.report_dir.mkdir(parents=True, exist_ok=True)
        for index, step in enumerate(self.manifest.get("steps") or [], start=1):
            result = self.run_step(index, step)
            self.results.append(result)
            if not result.get("ok") and step.get("block_on_fail", True):
                self.blocked = True
                break
        report = {
            "schema": "gptool.task.run_report.v1",
            "id": self.manifest.get("id"),
            "title": self.manifest.get("title"),
            "mode": "apply" if self.apply else "dry_run",
            "started_at": _now(),
            "ok": not self.blocked and all(item.get("ok") for item in self.results),
            "blocked": self.blocked,
            "step_count": len(self.manifest.get("steps") or []),
            "completed_steps": len(self.results),
            "results": self.results,
        }
        return report

    def run_step(self, index: int, step: dict[str, Any]) -> dict[str, Any]:
        action = step.get("action")
        label = step.get("label") or f"step-{index}-{action}"
        base = {"index": index, "label": label, "action": action}
        if action == "note":
            return {**base, "ok": True, "message": step.get("message", "")}
        if action == "assert_file_exists":
            path = Path(step["path"])
            return {**base, "ok": path.is_file(), "path": str(path)}
        if action == "assert_dir_exists":
            path = Path(step["path"])
            return {**base, "ok": path.is_dir(), "path": str(path)}
        if action == "assert_text_contains":
            path = Path(step["path"])
            text = str(step.get("text", ""))
            content = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""
            return {**base, "ok": bool(text and text in content), "path": str(path), "text": text}
        if action == "assert_no_junk":
            junk = find_junk(step["path"], limit=int(step.get("limit", 200)))
            return {**base, "ok": not junk, "path": step["path"], "junk": junk}
        if action == "command":
            if not self.apply and not step.get("run_in_dry_run", False):
                return {**base, "ok": True, "dry_run_only": True, "cmd": step.get("cmd")}
            return {**base, **run_process(step.get("cmd"), cwd=step.get("cwd"), timeout=int(step.get("timeout", 60)), env=step.get("env") or {})}
        if action == "panda3d_smoke":
            cmd = [sys.executable, "bridge.py", "panda3d-smoke", step.get("project", ".")]
            for key, flag in (("entry", "--entry"), ("runtime", "--runtime"), ("runtime_path", "--runtime-path"), ("exe", "--exe"), ("screenshot_path", "--screenshot-path")):
                if step.get(key):
                    cmd.extend([flag, str(step[key])])
            if step.get("require_screenshot"):
                cmd.append("--require-screenshot")
            if not self.apply and not step.get("run_in_dry_run", False):
                return {**base, "ok": True, "dry_run_only": True, "cmd": cmd}
            return {**base, **run_process(cmd, cwd=step.get("cwd"), timeout=int(step.get("timeout", 60)))}
        if action in {"patch_gate_dry_run", "patch_gate_apply"}:
            will_apply = action == "patch_gate_apply"
            if will_apply and self.approval != "APPLY":
                return {**base, "ok": False, "blocked": True, "reason": "patch apply requires approval token APPLY"}
            cmd = [
                sys.executable, "patching/repo_patch_tool.py",
                "--repo-root", step["repo_root"],
                "--patch-zip", step["patch_zip"],
                "--profile", step.get("profile", "gx-prototype-lab"),
                "--report-dir", step.get("report_dir", "repo_patch_reports"),
            ]
            if step.get("strip_prefix"):
                cmd.extend(["--strip-prefix", step["strip_prefix"]])
            if step.get("target_prefix"):
                cmd.extend(["--target-prefix", step["target_prefix"]])
            if will_apply:
                cmd.append("--apply")
            if not self.apply and will_apply:
                return {**base, "ok": True, "dry_run_only": True, "cmd": cmd}
            return {**base, **run_process(cmd, cwd=step.get("gptool_root") or ".", timeout=int(step.get("timeout", 120)))}
        if action == "capture_expected_artifact":
            path = Path(step["path"])
            exists = path.exists()
            return {**base, "ok": exists or not step.get("required", True), "path": str(path), "exists": exists}
        return {**base, "ok": False, "error": f"unsupported action {action!r}"}


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# GPTOOL Automation Task Report",
        "",
        f"- Task: `{report.get('id')}`",
        f"- Title: {report.get('title') or ''}",
        f"- Mode: `{report.get('mode')}`",
        f"- Result: **{'PASS' if report.get('ok') else 'FAIL'}**",
        f"- Completed: {report.get('completed_steps')} / {report.get('step_count')}",
        "",
        "## Steps",
        "",
    ]
    for item in report.get("results") or []:
        lines.append(f"- {item.get('index')}. **{item.get('label')}** `{item.get('action')}`: {'PASS' if item.get('ok') else 'FAIL'}")
        if item.get("reason"):
            lines.append(f"  - Reason: {item.get('reason')}")
        if item.get("error"):
            lines.append(f"  - Error: {item.get('error')}")
        if item.get("dry_run_only"):
            lines.append("  - Dry-run only; no write/launch command executed.")
    return "\n".join(lines) + "\n"
