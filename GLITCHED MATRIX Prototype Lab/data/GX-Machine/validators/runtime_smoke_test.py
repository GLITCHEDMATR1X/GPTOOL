from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


DEFAULT_TIMEOUT = 20


def run_command(command: str, timeout: int) -> dict[str, Any]:
    started = time.time()
    try:
        proc = subprocess.run(
            shlex.split(command),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        ended = time.time()
        return {
            "mode": "command",
            "command": command,
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "duration_seconds": round(ended - started, 3),
            "stdout": proc.stdout[-4000:],
            "stderr": proc.stderr[-4000:],
            "crash_suspected": proc.returncode not in (0,),
            "timed_out": False,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "mode": "command",
            "command": command,
            "ok": False,
            "returncode": None,
            "duration_seconds": timeout,
            "stdout": (exc.stdout or "")[-4000:],
            "stderr": (exc.stderr or "")[-4000:],
            "crash_suspected": False,
            "timed_out": True,
        }


def smoke_import(module_name: str, timeout: int) -> dict[str, Any]:
    started = time.time()
    command = [sys.executable, "-c", f"import {module_name}; print('IMPORT_OK')"]
    try:
        proc = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return {
            "mode": "module_import",
            "module_name": module_name,
            "command": command,
            "ok": proc.returncode == 0 and "IMPORT_OK" in proc.stdout,
            "returncode": proc.returncode,
            "duration_seconds": round(time.time() - started, 3),
            "stdout": proc.stdout[-4000:],
            "stderr": proc.stderr[-4000:],
            "crash_suspected": proc.returncode not in (0,),
            "timed_out": False,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "mode": "module_import",
            "module_name": module_name,
            "command": command,
            "ok": False,
            "returncode": None,
            "duration_seconds": timeout,
            "stdout": (exc.stdout or "")[-4000:],
            "stderr": (exc.stderr or "")[-4000:],
            "crash_suspected": False,
            "timed_out": True,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a conservative runtime smoke test.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--command", help="Shell-like command string to run.")
    group.add_argument("--module-import", help="Module name to import in a subprocess.")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="Timeout in seconds.")
    parser.add_argument("--json", action="store_true", help="Emit structured JSON.")
    parser.add_argument("--report-path", help="Optional path to write the JSON report.")
    args = parser.parse_args()

    if args.command:
        report = run_command(args.command, args.timeout)
    else:
        report = smoke_import(args.module_import, args.timeout)

    report["validator"] = "runtime_smoke_test"
    report["unknowns"] = [
        "Interactive input behavior is not validated by this smoke test.",
        "Visual framing and UI layout are not validated by this smoke test."
    ]

    if args.report_path:
        report_path = Path(args.report_path).resolve()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        status = "PASS" if report["ok"] else "FAIL"
        print(f"[{status}] {report['mode']}")
        print(f"Duration: {report['duration_seconds']}s")
        if report["timed_out"]:
            print("Timed out.")
        if report["stderr"]:
            print("stderr tail:")
            print(report["stderr"])
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
