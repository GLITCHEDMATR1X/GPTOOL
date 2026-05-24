#!/usr/bin/env python3
"""One-command Anti-Heroes bridge pipeline check.

Run from this folder:

    python antiheroes_gptool_pipeline.py --static
    python antiheroes_gptool_pipeline.py --visual

Static mode checks syntax, manifest readability, animation registry output,
spawn roster validation, and runtime adapter state output. Visual mode also runs
screenshot probes and stores progress captures under screenshots/progress when
Panda3D is available.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import py_compile
import subprocess
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
REPORT_JSON = ROOT / "reports" / "antiheroes_gptool_pipeline_report.json"
REPORT_MD = ROOT / "reports" / "antiheroes_gptool_pipeline_report.md"
MANIFEST = ROOT / "assets" / "characters" / "humans" / "human_manifest.json"
CHECK_FILES = [
    ROOT / "antiheroes_asset_bridge.py",
    ROOT / "antiheroes_animation_registry.py",
    ROOT / "antiheroes_character_runtime_adapter.py",
    ROOT / "antiheroes_manifest_sync.py",
    ROOT / "antiheroes_spawn_roster.py",
    ROOT / "antiheroes_gptool_pipeline.py",
]


def _tail(text: str, limit: int = 1200) -> str:
    return str(text or "")[-limit:]


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return None


def step(name: str, status: str, **details: Any) -> dict[str, Any]:
    return {"name": name, "status": status, "details": details}


def syntax_step() -> dict[str, Any]:
    failures = []
    for path in CHECK_FILES:
        try:
            py_compile.compile(str(path), doraise=True)
        except Exception as exc:
            failures.append({"file": str(path), "error": f"{type(exc).__name__}: {exc}"})
    return step("python_syntax", "pass" if not failures else "fail", checked=[str(p) for p in CHECK_FILES], failures=failures)


def manifest_step() -> dict[str, Any]:
    if not MANIFEST.exists():
        return step("manifest", "warn", path=str(MANIFEST), exists=False, message="Run GPTOOL import-human-assets before expecting model loads.")
    try:
        data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    except Exception as exc:
        return step("manifest", "fail", path=str(MANIFEST), exists=True, error=f"{type(exc).__name__}: {exc}")
    base_assets = [x for x in data.get("base_assets", []) if isinstance(x, dict)]
    animations = [x for x in data.get("animations", []) if isinstance(x, dict)]
    return step(
        "manifest",
        "pass" if base_assets else "warn",
        path=str(MANIFEST),
        exists=True,
        schema_version=data.get("schema_version"),
        base_asset_count=len(base_assets),
        animation_asset_count=len(animations),
        base_asset_ids=[str(x.get("id") or x.get("label") or "") for x in base_assets],
    )


def run_command(name: str, args: list[str], *, warn_on_fail: bool = False, timeout: int = 160) -> dict[str, Any]:
    try:
        proc = subprocess.run(args, cwd=str(ROOT), capture_output=True, text=True, timeout=timeout, check=False)
        status = "pass" if proc.returncode == 0 else ("warn" if warn_on_fail else "fail")
        return step(name, status, command=args, returncode=proc.returncode, stdout_tail=_tail(proc.stdout), stderr_tail=_tail(proc.stderr))
    except Exception as exc:
        return step(name, "warn" if warn_on_fail else "fail", command=args, error=f"{type(exc).__name__}: {exc}")


def enrich_outputs(result: dict[str, Any]) -> None:
    output_paths = {
        "animation_registry": ROOT / "reports" / "antiheroes_animation_registry.json",
        "runtime_state": ROOT / "reports" / "antiheroes_character_runtime_state.json",
        "manifest_sync": ROOT / "reports" / "antiheroes_manifest_sync_report.json",
        "spawn_roster": ROOT / "reports" / "antiheroes_spawn_roster_report.json",
        "asset_bridge_proof": ROOT / "reports" / "antiheroes_asset_bridge_proof.json",
        "role_probe_proof": ROOT / "reports" / "antiheroes_animation_role_probe.json",
    }
    result["outputs"] = {key: {"path": str(path), "exists": path.exists()} for key, path in output_paths.items()}
    registry = _read_json(output_paths["animation_registry"])
    if registry:
        result["registry_summary"] = {
            "ok": registry.get("ok"),
            "covered_roles": registry.get("covered_roles", []),
            "missing_core_roles": registry.get("missing_core_roles", []),
            "warnings": registry.get("warnings", []),
        }
    sync = _read_json(output_paths["manifest_sync"])
    if sync:
        result["manifest_sync_summary"] = {
            "ok": sync.get("ok"),
            "mode": sync.get("mode"),
            "base_asset_count": sync.get("base_asset_count", 0),
            "animation_asset_count": sync.get("animation_asset_count", 0),
            "missing_file_count": sync.get("missing_file_count", 0),
            "warnings": sync.get("warnings", []),
        }
    roster = _read_json(output_paths["spawn_roster"])
    if roster:
        result["spawn_roster_summary"] = {
            "ok": roster.get("ok"),
            "enabled_count": roster.get("enabled_count", 0),
            "manifest_exists": roster.get("manifest_exists"),
            "warnings": roster.get("warnings", []),
        }
    bridge = _read_json(output_paths["asset_bridge_proof"])
    role_probe = _read_json(output_paths["role_probe_proof"])
    shots: dict[str, Any] = {}
    if bridge and isinstance(bridge.get("screenshots"), dict):
        shots["asset_bridge"] = bridge.get("screenshots")
    if role_probe and isinstance(role_probe.get("screenshots"), dict):
        shots["animation_roles"] = role_probe.get("screenshots")
    result["visual_progress"] = {"review_folder": str(ROOT / "screenshots" / "progress"), "screenshots": shots}


def build_report(mode: str, results: list[dict[str, Any]]) -> dict[str, Any]:
    blockers = [x["name"] for x in results if x.get("status") == "fail"]
    warnings = [x["name"] for x in results if x.get("status") == "warn"]
    report = {
        "schema_version": "antiheroes_gptool_pipeline_report.v1",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "mode": mode,
        "project_root": str(ROOT),
        "panda3d_available": bool(importlib.util.find_spec("panda3d") and importlib.util.find_spec("direct")),
        "delivery": {"ok": not blockers, "blockers": blockers, "warnings": warnings},
        "steps": results,
        "review_notes": [
            "Warnings are expected before GPTOOL has imported a character manifest.",
            "Visual screenshots are only produced when Panda3D can run locally.",
            "This runner does not edit the live Anti-Heroes runtime.",
            "Run antiheroes_manifest_sync.py --dry-run before --apply when importing GPTOOL assets.",
            "Run antiheroes_spawn_roster.py --init-default after manifest sync to refresh player/NPC assignments.",
        ],
    }
    enrich_outputs(report)
    return report


def render_md(report: dict[str, Any]) -> str:
    lines = [
        "# Anti-Heroes GPTOOL Pipeline Report",
        "",
        f"- Mode: `{report.get('mode')}`",
        f"- Panda3D available: `{report.get('panda3d_available')}`",
        f"- Delivery OK: **{'YES' if report.get('delivery', {}).get('ok') else 'NO'}**",
        "",
        "## Steps",
        "",
    ]
    for item in report.get("steps", []):
        lines.append(f"- **{item.get('name')}**: `{item.get('status')}`")
    lines.extend(["", "## Outputs", ""])
    for name, info in (report.get("outputs") or {}).items():
        lines.append(f"- {name}: `{info.get('path')}` exists=`{info.get('exists')}`")
    lines.extend(["", "## Visual Progress", ""])
    lines.append(f"- Review folder: `{report.get('visual_progress', {}).get('review_folder')}`")
    return "\n".join(lines) + "\n"


def run(mode: str) -> dict[str, Any]:
    results = [
        syntax_step(),
        manifest_step(),
        run_command("animation_registry", [sys.executable, "antiheroes_animation_registry.py", "--write-registry"], warn_on_fail=True),
        run_command("runtime_adapter_state", [sys.executable, "antiheroes_character_runtime_adapter.py", "--state-only"], warn_on_fail=False),
        run_command("spawn_roster", [sys.executable, "antiheroes_spawn_roster.py", "--init-default"], warn_on_fail=True),
    ]
    if MANIFEST.exists():
        results.append(run_command("manifest_sync_dry_run", [sys.executable, "antiheroes_manifest_sync.py", "--source-manifest", str(MANIFEST), "--dry-run"], warn_on_fail=True))
    if mode == "visual":
        results.append(run_command("asset_bridge_visual", [sys.executable, "antiheroes_asset_bridge.py", "--visual-probe"], warn_on_fail=True, timeout=220))
        results.append(run_command("animation_role_visual", [sys.executable, "antiheroes_animation_registry.py", "--role-probe"], warn_on_fail=True, timeout=260))
    report = build_report(mode, results)
    _write_json(REPORT_JSON, report)
    REPORT_MD.write_text(render_md(report), encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the Anti-Heroes bridge pipeline checks.")
    parser.add_argument("--static", action="store_true", help="Run non-render bridge checks.")
    parser.add_argument("--visual", action="store_true", help="Run static checks plus visual probes.")
    args = parser.parse_args(argv)
    mode = "visual" if args.visual else "static"
    try:
        report = run(mode)
        print(json.dumps(report, indent=2, default=str))
        return 0 if report.get("delivery", {}).get("ok") else 1
    except Exception as exc:
        crash = ROOT / "reports" / "antiheroes_gptool_pipeline_crash.txt"
        crash.parent.mkdir(parents=True, exist_ok=True)
        crash.write_text(
            "Anti-Heroes bridge pipeline crashed\n\n"
            f"Exception: {type(exc).__name__}: {exc}\n\n"
            + traceback.format_exc(),
            encoding="utf-8",
            errors="replace",
        )
        print(f"Pipeline crash report: {crash}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
