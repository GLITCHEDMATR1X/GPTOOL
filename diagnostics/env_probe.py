from __future__ import annotations

import argparse
import importlib
import json
import os
import platform
import shutil
import sys
from pathlib import Path
from typing import Any

def find_module(module_name: str) -> dict[str, Any]:
    try:
        module = importlib.import_module(module_name)
        version = getattr(module, "__version__", None)
        return {"present": True, "version": version}
    except Exception as exc:
        return {"present": False, "error": f"{type(exc).__name__}: {exc}"}

def build_probe() -> dict[str, Any]:
    python_exe = Path(sys.executable).resolve()
    cwd = Path.cwd().resolve()
    return {
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
            "python_version": platform.python_version()
        },
        "paths": {
            "python_executable": str(python_exe),
            "cwd": str(cwd),
            "home": str(Path.home()),
            "temp": os.getenv("TMPDIR") or os.getenv("TEMP") or "/tmp"
        },
        "tools": {
            "python": shutil.which("python"),
            "pip": shutil.which("pip")
        },
        "packages": {
            "panda3d": find_module("panda3d"),
            "direct": find_module("direct"),
            "gltf": find_module("gltf"),
            "simplepbr": find_module("simplepbr"),
            "PIL": find_module("PIL")
        },
        "capabilities": {
            "panda3d_profile_ready": False,
            "notes": []
        }
    }

def finalize_probe(data: dict[str, Any]) -> dict[str, Any]:
    pkgs = data["packages"]
    ready = pkgs["panda3d"]["present"] and pkgs["direct"]["present"]
    data["capabilities"]["panda3d_profile_ready"] = ready
    if ready:
        data["capabilities"]["notes"].append("Panda3D core imports are available.")
    else:
        data["capabilities"]["notes"].append("Panda3D core imports are incomplete.")
    if pkgs["gltf"]["present"]:
        data["capabilities"]["notes"].append("glTF support package is present through the gltf module.")
    else:
        data["capabilities"]["notes"].append("glTF support module is missing or not importable.")
    if pkgs["simplepbr"]["present"]:
        data["capabilities"]["notes"].append("simplepbr is present.")
    return data

def main() -> int:
    parser = argparse.ArgumentParser(description="Probe the local Python/game-generation environment.")
    parser.add_argument("--json", action="store_true", help="Emit structured JSON.")
    args = parser.parse_args()

    report = finalize_probe(build_probe())
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"System: {report['platform']['system']} {report['platform']['release']}")
        print(f"Python: {report['platform']['python_version']}")
        print(f"Panda3D ready: {report['capabilities']['panda3d_profile_ready']}")
        for note in report["capabilities"]["notes"]:
            print(f"- {note}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
