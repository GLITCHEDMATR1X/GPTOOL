from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Iterable


def _tail_text(value: Any, limit: int = 4000) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")[-limit:]
    return str(value)[-limit:]


DEFAULT_LOG_PATH = Path("logs") / "panda3d_bootstrap.json"
def _panda3d_package_spec() -> str:
    # Windows target: Python 3.12.x + Panda3D 1.10.15.
    # Python 3.13 test environments need 1.10.16 because 1.10.15 has no cp313 wheel.
    return "panda3d==1.10.16" if sys.version_info >= (3, 13) else "panda3d==1.10.15"


DEFAULT_PACKAGES = (_panda3d_package_spec(),)
OPTIONAL_PROFILE_PACKAGES = ("panda3d-gltf", "panda3d-simplepbr")


def _package_installed(module_name: str) -> bool:
    try:
        __import__(module_name)
        return True
    except Exception:
        return False


def _candidate_pip_commands() -> list[list[str]]:
    commands: list[list[str]] = []
    commands.append([sys.executable, "-m", "pip"])
    pip_path = shutil.which("pip")
    if pip_path:
        commands.append([pip_path])
    seen: set[tuple[str, ...]] = set()
    unique: list[list[str]] = []
    for command in commands:
        key = tuple(command)
        if key not in seen:
            seen.add(key)
            unique.append(command)
    return unique


def _run_pip_install(packages: Iterable[str], timeout: int) -> dict[str, Any]:
    package_list = list(packages)
    errors: list[str] = []
    stdout_tail = ""
    stderr_tail = ""
    chosen_command: list[str] | None = None

    for base_command in _candidate_pip_commands():
        command = [*base_command, "install", *package_list]
        chosen_command = command
        try:
            proc = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
                env=os.environ.copy(),
            )
            stdout_tail = _tail_text(proc.stdout)
            stderr_tail = _tail_text(proc.stderr)
            if proc.returncode == 0:
                return {
                    "ok": True,
                    "returncode": proc.returncode,
                    "command": command,
                    "stdout": stdout_tail,
                    "stderr": stderr_tail,
                    "errors": errors,
                }
            errors.append(f"Install command failed with return code {proc.returncode}: {' '.join(command)}")
        except subprocess.TimeoutExpired as exc:
            stdout_tail = _tail_text(exc.stdout)
            stderr_tail = _tail_text(exc.stderr)
            errors.append(f"Install command timed out after {timeout}s: {' '.join(command)}")
        except Exception as exc:
            errors.append(f"{type(exc).__name__}: {exc}")

    return {
        "ok": False,
        "returncode": None,
        "command": chosen_command,
        "stdout": stdout_tail,
        "stderr": stderr_tail,
        "errors": errors,
    }


def build_bootstrap_report(
    *,
    install_attempted: bool,
    install_requested: bool,
    timeout: int,
    requested_packages: Iterable[str],
    install_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    panda_present = _package_installed("panda3d")
    direct_present = _package_installed("direct")
    gltf_present = _package_installed("gltf")
    simplepbr_present = _package_installed("simplepbr")

    notes: list[str] = []
    if panda_present and direct_present:
        notes.append("Panda3D core imports are available.")
    else:
        notes.append("Panda3D core imports are incomplete.")

    if install_attempted:
        notes.append("An install attempt was made during launch.")
    elif install_requested:
        notes.append("Install was requested but skipped because Panda3D was already available.")
    else:
        notes.append("Auto-install was not requested for this launch.")

    return {
        "bootstrap": "panda3d_bootstrap",
        "python_executable": str(Path(sys.executable).resolve()),
        "cwd": str(Path.cwd().resolve()),
        "requested_packages": list(requested_packages),
        "install_requested": install_requested,
        "install_attempted": install_attempted,
        "install_result": install_result,
        "packages": {
            "panda3d": {"present": panda_present},
            "direct": {"present": direct_present},
            "gltf": {"present": gltf_present},
            "simplepbr": {"present": simplepbr_present},
        },
        "capabilities": {
            "panda3d_profile_ready": panda_present and direct_present,
            "notes": notes,
        },
        "timeout_seconds": timeout,
        "timestamp_unix": round(time.time(), 3),
    }


def ensure_panda3d(
    *,
    auto_install: bool = True,
    include_optional_profile_packages: bool = False,
    timeout: int = 300,
    log_path: str | Path | None = DEFAULT_LOG_PATH,
) -> dict[str, Any]:
    requested_packages = list(DEFAULT_PACKAGES)
    if include_optional_profile_packages:
        requested_packages.extend(OPTIONAL_PROFILE_PACKAGES)

    panda_ready = _package_installed("panda3d") and _package_installed("direct")
    install_attempted = False
    install_result: dict[str, Any] | None = None

    if auto_install and not panda_ready:
        install_attempted = True
        install_result = _run_pip_install(requested_packages, timeout)

    report = build_bootstrap_report(
        install_attempted=install_attempted,
        install_requested=auto_install,
        timeout=timeout,
        requested_packages=requested_packages,
        install_result=install_result,
    )

    if log_path is not None:
        output_path = Path(log_path).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    return report
