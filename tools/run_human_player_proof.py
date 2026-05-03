#!/usr/bin/env python3
"""Recover and prove the GPTOOL rigged human player lane.

This runner is intentionally strict: it imports real rigged human assets from a
local backup/source folder, runs the generated Panda3D screenshot/proof mode,
and fails if the generated scene falls back to procedural placeholders.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_COMMAND = (
    "make a 16:9 gray rigged human model import test world with male and female "
    "third-person playable characters, screenshot mode, crash diagnostics, stress "
    "proof, and points only"
)
DEFAULT_PREFER = ("female", "male", "survivor", "human", "character", "idle", "cranberry", "rig")


def _run(cmd: list[str], *, cwd: Path) -> int:
    print("$ " + " ".join(str(part) for part in cmd), flush=True)
    completed = subprocess.run(cmd, cwd=str(cwd))
    return int(completed.returncode)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _verify_import(import_report: Path) -> tuple[bool, str]:
    if not import_report.exists():
        return False, f"Missing import report: {import_report}"
    data = _read_json(import_report)
    if not data.get("ok"):
        return False, f"Import report failed: {data.get('reason') or 'unknown reason'}"
    if int(data.get("base_asset_count") or 0) < 1:
        return False, "Import report contains no base human assets."
    manifest = Path(str(data.get("manifest") or ""))
    if not manifest.exists():
        return False, f"Missing human manifest: {manifest}"
    manifest_data = _read_json(manifest)
    base_assets = manifest_data.get("base_assets") or []
    if not base_assets:
        return False, "human_manifest.json has no base_assets."
    return True, "Human import report and manifest look valid."


def _verify_scene_proof(project: Path, proof_path: Path) -> tuple[bool, str]:
    crash_log = project / "logs" / "crash_latest.txt"
    if crash_log.exists():
        return False, f"Crash log exists: {crash_log}"
    if not proof_path.exists():
        return False, f"Missing proof JSON: {proof_path}"
    data = _read_json(proof_path)
    chars = data.get("simulation_characters") or data.get("characters") or []
    if not chars and isinstance(data.get("scene"), dict):
        chars = data["scene"].get("simulation_characters") or []
    if not chars:
        return False, "Proof JSON has no simulation character state."
    missing = [item.get("id") or item.get("name") or str(index) for index, item in enumerate(chars) if not item.get("actor_loaded")]
    if missing:
        return False, "One or more playable characters did not load imported Actor assets: " + ", ".join(map(str, missing))
    return True, "All playable characters reported actor_loaded=True."


def main() -> int:
    parser = argparse.ArgumentParser(description="Import real human player assets and run third-person screenshot proof.")
    parser.add_argument("--search-root", required=True, help="Local backup/source folder containing rigged human GLB/GLTF/FBX assets.")
    parser.add_argument("--project", default="GeneratedHumanPlayerRecovery", help="Generated proof project folder.")
    parser.add_argument("--command", default=DEFAULT_COMMAND, help="Generation command for the proof project.")
    parser.add_argument("--prefer", nargs="*", default=list(DEFAULT_PREFER), help="Ranking tokens for human asset scan/import.")
    parser.add_argument("--require", nargs="*", default=[], help="Required path/name tokens before import selection.")
    parser.add_argument("--limit", type=int, default=10, help="Maximum base meshes to import.")
    parser.add_argument("--animation-limit", type=int, default=16, help="Maximum animation clips to import.")
    parser.add_argument("--runtime", default="system_python", choices=["system_python", "portable_python", "mock_display", "auto"], help="Runtime label for follow-up validation notes.")
    parser.add_argument("--runtime-path", default=None, help="Optional portable Panda3D runtime path.")
    parser.add_argument("--window-type", default="offscreen", choices=["offscreen", "default", "none"], help="Panda3D window type for screenshot proof.")
    parser.add_argument("--screenshot", default=None, help="Screenshot output path. Defaults inside project/screenshots.")
    parser.add_argument("--proof", default=None, help="Proof JSON output path. Defaults inside project/reports.")
    parser.add_argument("--keep-existing", action="store_true", help="Do not force-regenerate the proof project.")
    parser.add_argument("--no-stress", action="store_true", help="Run route screenshot proof without stress proof.")
    args = parser.parse_args()

    project = Path(args.project)
    if not project.is_absolute():
        project = (ROOT / project).resolve()
    search_root = Path(args.search_root).resolve()
    if not search_root.exists():
        print(f"Search root does not exist: {search_root}", file=sys.stderr)
        return 2

    project.mkdir(parents=True, exist_ok=True)
    reports = project / "reports"
    screenshots = project / "screenshots"
    reports.mkdir(parents=True, exist_ok=True)
    screenshots.mkdir(parents=True, exist_ok=True)
    import_report = reports / "human_player_import_recovery.json"
    screenshot_path = Path(args.screenshot).resolve() if args.screenshot else screenshots / "human_player_recovery.png"
    proof_path = Path(args.proof).resolve() if args.proof else reports / "human_player_recovery.json"

    if not args.keep_existing:
        code = _run([
            sys.executable,
            "bridge.py",
            "generate-game",
            str(project),
            "--profile",
            "panda3d",
            "--command",
            args.command,
            "--force",
        ], cwd=ROOT)
        if code != 0:
            return code

    import_cmd = [
        sys.executable,
        "bridge.py",
        "import-human-assets",
        str(project),
        "--search-root",
        str(search_root),
        "--rigged-only",
        "--limit",
        str(args.limit),
        "--animation-limit",
        str(args.animation_limit),
        "--export-formats",
        "glb",
        "obj",
        "fbx",
        "--clean",
        "--force",
        "--output",
        str(import_report),
    ]
    if args.prefer:
        import_cmd.extend(["--prefer", *args.prefer])
    if args.require:
        import_cmd.extend(["--require", *args.require])
    code = _run(import_cmd, cwd=ROOT)
    if code != 0:
        return code

    ok, message = _verify_import(import_report)
    print(message)
    if not ok:
        return 1

    code = _run([sys.executable, str(project / "main.py"), "--settings-check"], cwd=ROOT)
    if code != 0:
        return code

    proof_cmd = [
        sys.executable,
        str(project / "main.py"),
        "--screenshot-mode",
        "--route-proof",
        "--window-type",
        args.window_type,
        "--screenshot-path",
        str(screenshot_path),
        "--proof-path",
        str(proof_path),
    ]
    if not args.no_stress:
        proof_cmd.insert(3, "--stress-proof")
    code = _run(proof_cmd, cwd=ROOT)
    if code != 0:
        return code

    ok, message = _verify_scene_proof(project, proof_path)
    print(message)
    if not ok:
        return 1
    if not screenshot_path.exists():
        print(f"Missing screenshot: {screenshot_path}", file=sys.stderr)
        return 1

    result = {
        "schema_version": "human_player_recovery_result.v1",
        "ok": True,
        "project": str(project),
        "search_root": str(search_root),
        "import_report": str(import_report),
        "screenshot": str(screenshot_path),
        "proof": str(proof_path),
        "runtime": args.runtime,
        "runtime_path": args.runtime_path,
        "message": "Real imported human player proof passed; no placeholder fallback accepted.",
    }
    summary_path = reports / "human_player_recovery_result.json"
    summary_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print("Human player recovery: PASS")
    print(f"Screenshot: {screenshot_path}")
    print(f"Proof: {proof_path}")
    print(f"Summary: {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
