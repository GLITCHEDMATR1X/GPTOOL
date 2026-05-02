#!/usr/bin/env python3
"""Run a conservative GPTOOL validation pass for The Anti-Heroes.

This helper is intentionally non-destructive. It locates the Anti-Heroes project
inside a GX Prototype Lab checkout, writes a profile-aware command/work-order,
and runs bridge validation against the existing game instead of generating over it.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROFILE_PATH = ROOT / "profiles" / "antiheroes.json"
DEFAULT_COMMAND = (
    "improve The Anti-Heroes as a third-person city sandbox: preserve existing "
    "combat/editor/menu systems, make districts and street traversal more readable, "
    "add hero-villain stance and service anchors only where safe, and verify with "
    "Panda3D proof instead of placeholders"
)


def _load_profile() -> dict:
    return json.loads(PROFILE_PATH.read_text(encoding="utf-8"))


def _candidate_paths(gx_root: Path, profile: dict) -> list[Path]:
    paths: list[Path] = []
    for hint in profile.get("expected_project_path_hints", []):
        paths.append(gx_root / hint)
    paths.extend([
        gx_root / "data" / "Prototype Lab" / "3D - Third Person" / "The Anti-Heroes",
        gx_root / "data" / "Prototype Lab" / "The Anti-Heroes",
        gx_root / "The Anti-Heroes",
    ])
    out: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        try:
            resolved = path.resolve()
        except Exception:
            resolved = path
        key = str(resolved).lower()
        if key not in seen:
            out.append(resolved)
            seen.add(key)
    return out


def _looks_like_antiheroes(path: Path) -> bool:
    if not path.exists() or not path.is_dir():
        return False
    names = {p.name.lower() for p in path.iterdir() if p.is_file()}
    if "main.py" in names:
        return True
    return any("anti" in p.name.lower() and p.suffix.lower() == ".py" for p in path.iterdir() if p.is_file())


def locate_antiheroes(gx_root: Path, explicit: str | None = None) -> Path:
    if explicit:
        path = Path(explicit)
        if not path.is_absolute():
            path = (Path.cwd() / path).resolve()
        if _looks_like_antiheroes(path):
            return path
        raise SystemExit(f"Explicit Anti-Heroes path does not look valid: {path}")

    profile = _load_profile()
    for path in _candidate_paths(gx_root.resolve(), profile):
        if _looks_like_antiheroes(path):
            return path

    # Last-resort bounded search. The GX repo can be large, so stop after enough hits.
    checked = 0
    for path in gx_root.rglob("*"):
        checked += 1
        if checked > 20000:
            break
        if not path.is_dir():
            continue
        low = path.name.lower().replace("-", " ").replace("_", " ")
        if "anti" in low and "hero" in low and _looks_like_antiheroes(path):
            return path.resolve()
    raise SystemExit("Could not locate The Anti-Heroes. Pass --antiheroes-path to the project folder.")


def run(cmd: list[str], *, cwd: Path) -> int:
    print("$ " + " ".join(str(c) for c in cmd), flush=True)
    completed = subprocess.run(cmd, cwd=str(cwd))
    return int(completed.returncode)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Anti-Heroes GPTOOL validation without editing game code.")
    parser.add_argument("--gx-root", default="../GX-Prototype-Lab", help="Path to the GX Prototype Lab checkout.")
    parser.add_argument("--antiheroes-path", default=None, help="Explicit Anti-Heroes folder if auto-detect fails.")
    parser.add_argument("--command", default=DEFAULT_COMMAND, help="Improvement command to convert into a work order.")
    parser.add_argument("--runtime", default="auto", choices=["auto", "system_python", "portable_python", "packaged_exe", "mock_display", "mock"], help="Panda3D runtime provider.")
    parser.add_argument("--runtime-path", default=None, help="Portable Panda3D runtime path.")
    parser.add_argument("--entry", default="main.py", help="Entry file to validate/smoke.")
    parser.add_argument("--no-smoke", action="store_true", help="Skip Panda3D smoke execution and run static checks only.")
    parser.add_argument("--require-screenshot", action="store_true", help="Require screenshot proof instead of warning when unavailable.")
    parser.add_argument("--baseline", default=None, help="Optional baseline folder for regression comparison.")
    args = parser.parse_args()

    gx_root = Path(args.gx_root)
    if not gx_root.is_absolute():
        gx_root = (Path.cwd() / gx_root).resolve()
    antiheroes = locate_antiheroes(gx_root, args.antiheroes_path)
    reports = antiheroes / "reports"
    screenshots = antiheroes / "screenshots"
    reports.mkdir(parents=True, exist_ok=True)
    screenshots.mkdir(parents=True, exist_ok=True)

    command_path = reports / "antiheroes_command.txt"
    work_order_path = reports / "antiheroes_work_order.json"
    screenshot_path = screenshots / "antiheroes_gptool_probe.png"
    proof_path = reports / "antiheroes_scene_proof.json"
    profile_report = reports / "antiheroes_profile_manifest.json"
    profile_report.write_text(PROFILE_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    command_path.write_text(args.command.strip() + "\n", encoding="utf-8")

    print(f"Anti-Heroes project: {antiheroes}")
    print(f"Profile manifest: {profile_report}")

    plan_cmd = [
        sys.executable,
        "bridge.py",
        "plan-command",
        str(antiheroes),
        "--profile",
        "panda3d",
        "--command-file",
        str(command_path),
        "--output",
        str(work_order_path),
    ]
    code = run(plan_cmd, cwd=ROOT)
    if code != 0:
        return code

    full_cmd = [
        sys.executable,
        "bridge.py",
        "full-pass",
        str(antiheroes),
        "--profile",
        "panda3d",
        "--work-order",
        str(work_order_path),
        "--entry",
        args.entry,
        "--runtime",
        "mock_display" if args.runtime == "mock" else args.runtime,
        "--screenshot-path",
        str(screenshot_path),
        "--proof-path",
        str(proof_path),
    ]
    if args.runtime_path:
        full_cmd.extend(["--runtime-path", args.runtime_path])
    if args.baseline:
        full_cmd.extend(["--baseline", args.baseline])
    if not args.no_smoke:
        full_cmd.append("--smoke")
    if args.require_screenshot:
        full_cmd.append("--require-screenshot")

    return run(full_cmd, cwd=ROOT)


if __name__ == "__main__":
    raise SystemExit(main())
