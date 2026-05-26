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
from .input_script import load_input_plan, normalize_input_plan, render_input_plan_markdown, validate_input_plan, write_input_plan


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
        steps = list(self.manifest.get("steps") or [])
        blocking_failures: list[dict[str, Any]] = []
        nonblocking_failures: list[dict[str, Any]] = []
        for step, result in zip(steps, self.results):
            if result.get("ok"):
                continue
            if step.get("block_on_fail", True):
                blocking_failures.append(result)
            else:
                nonblocking_failures.append(result)
        report = {
            "schema": "gptool.task.run_report.v1",
            "id": self.manifest.get("id"),
            "title": self.manifest.get("title"),
            "mode": "apply" if self.apply else "dry_run",
            "started_at": _now(),
            "ok": not self.blocked and not blocking_failures,
            "blocked": self.blocked or bool(blocking_failures),
            "warning_count": len(nonblocking_failures),
            "blocking_failure_count": len(blocking_failures),
            "step_count": len(steps),
            "completed_steps": len(self.results),
            "results": self.results,
        }
        if nonblocking_failures:
            report["warnings"] = [
                {
                    "index": item.get("index"),
                    "label": item.get("label"),
                    "action": item.get("action"),
                    "reason": item.get("reason") or item.get("error") or item.get("stderr") or item.get("stdout") or "non-blocking step failed",
                }
                for item in nonblocking_failures
            ]
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
        if action == "write_input_plan":
            plan = {
                "schema": "gptool.input_plan.v1",
                "id": step.get("id") or label,
                "title": step.get("title") or label,
                "target": step.get("target", {}),
                "steps": step.get("steps") or [],
            }
            output = Path(step.get("output"))
            if not output.is_absolute():
                output = self.report_dir / output
            result = write_input_plan(output, plan)
            md_path = output.with_suffix(".md")
            md_path.write_text(render_input_plan_markdown(result["plan"], result["validation"]), encoding="utf-8")
            return {**base, "ok": result["ok"], "path": str(output), "markdown": str(md_path), "validation": result["validation"]}
        if action == "validate_input_plan":
            if step.get("path"):
                plan = load_input_plan(step["path"])
            else:
                plan = normalize_input_plan(step.get("plan") or {"id": label, "title": label, "steps": step.get("steps") or []})
            validation = validate_input_plan(plan)
            return {**base, "ok": bool(validation.get("ok")), "validation": validation}
        if action == "screenshot_checkpoint":
            path = Path(step["path"])
            exists = path.is_file()
            min_size = int(step.get("min_size_bytes", 1))
            size = path.stat().st_size if exists else 0
            ok = (exists and size >= min_size) or (not step.get("required", True))
            return {**base, "ok": ok, "path": str(path), "exists": exists, "size_bytes": size, "min_size_bytes": min_size}
        if action == "panda3d_journey_smoke":
            cmd = [sys.executable, "bridge.py", "panda3d-smoke", step.get("project", ".")]
            for key, flag in (
                ("entry", "--entry"),
                ("runtime", "--runtime"),
                ("runtime_path", "--runtime-path"),
                ("exe", "--exe"),
                ("screenshot_path", "--screenshot-path"),
                ("proof_path", "--proof-path"),
                ("window_type", "--window-type"),
            ):
                if step.get(key):
                    cmd.extend([flag, str(step[key])])
            if step.get("require_screenshot"):
                cmd.append("--require-screenshot")
            if step.get("require_proof"):
                cmd.append("--require-proof")
            if step.get("frames") is not None:
                cmd.extend(["--frames", str(step["frames"])])
            for item in step.get("extra_env") or []:
                cmd.extend(["--extra-env", str(item)])
            env = dict(step.get("env") or {})
            if step.get("journey_plan"):
                env["GPT_BRIDGE_JOURNEY_PLAN"] = str(step["journey_plan"])
            if step.get("journey_id"):
                env["GPT_BRIDGE_JOURNEY_ID"] = str(step["journey_id"])
            if not self.apply and not step.get("run_in_dry_run", False):
                return {**base, "ok": True, "dry_run_only": True, "cmd": cmd, "env": env}
            result = run_process(cmd, cwd=step.get("cwd"), timeout=int(step.get("timeout", 90)), env=env)
            if not result.get("ok") and not step.get("block_on_fail", True):
                result["nonblocking_failure"] = True
            return {**base, **result}
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
        f"- Blocking failures: {report.get('blocking_failure_count', 0)}",
        f"- Non-blocking warnings: {report.get('warning_count', 0)}",
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
        if item.get("nonblocking_failure"):
            lines.append("  - Non-blocking failure recorded as a warning.")
    return "\n".join(lines) + "\n"
