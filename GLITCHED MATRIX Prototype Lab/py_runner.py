#!/usr/bin/env python3
"""
py_runner.py

A tiny "python script runner" to ship alongside GXPrototypeLab.exe.
GXPrototypeLab launches games/tools via:
    subprocess.Popen([sys.executable, path/to/main.py], ...)

When GXPrototypeLab is frozen, sys.executable becomes GXPrototypeLab.exe.
That breaks game launching.

Solution:
- Ship py_runner.exe (built from this file).
- GXPrototypeLab_boot.py sets sys.executable = py_runner.exe at runtime.
- py_runner.exe executes the target script in-process via runpy.
"""

from __future__ import annotations

import os
import runpy
import sys
import traceback
from pathlib import Path


def _set_dpi_awareness() -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            pass
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass
    except Exception:
        pass


def _write_runner_crash(title: str, content: str) -> None:
    try:
        app_dir = Path(os.environ.get("GXPLAB_APP_DIR", "")).resolve() if os.environ.get("GXPLAB_APP_DIR") else None
        base = app_dir if app_dir and app_dir.exists() else Path(sys.executable).resolve().parent.parent
        out_dir = base / "crash_reports"
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "latest_runner_crash.txt").write_text(f"{title}\n\n{content}", encoding="utf-8")
    except Exception:
        pass


def _force_common_includes() -> None:
    """
    Helps PyInstaller discover optional deps used across your games/tools.
    If a package is not installed, we ignore it.
    """
    modules = [
        # Core (already in requirements.txt but keeps bundling stable)
        "pygame",
        "PIL.Image",
        "PIL.ImageTk",
        "tkinter",
        "_tkinter",
        "tkinter.ttk",
        "tkinter.filedialog",
        "tkinter.messagebox",
        "tkinter.simpledialog",
        "tkinter.font",
        "tkinterdnd2",
        "pyttsx3",
        # Common across included projects
        "numpy",
        "pydub",
        "reportlab",
        "trimesh",
        # Panda3D (many of your games import direct.showbase)
        "direct.showbase.ShowBase",
        # Optional heavy tools (only if installed)
        "cv2",
        "PyQt6",
        "PySide6",
        "panda3d.core",
        "direct.showbase.ShowBase",
    ]
    for mod in modules:
        try:
            __import__(mod)
        except Exception:
            pass


def main() -> int:
    _set_dpi_awareness()
    _force_common_includes()

    if len(sys.argv) < 2:
        print("Usage: py_runner.exe <script.py> [args...]")
        return 2

    script = Path(sys.argv[1]).resolve()
    if not script.exists():
        _write_runner_crash("Runner Error", f"Script not found:\n{script}")
        return 2

    # Make relative imports + file loads behave like "run from that folder"
    try:
        os.chdir(script.parent)
    except Exception:
        pass

    if str(script.parent) not in sys.path:
        sys.path.insert(0, str(script.parent))

    app_dir_env = os.environ.get("GXPLAB_APP_DIR", "").strip()
    if app_dir_env and app_dir_env not in sys.path:
        sys.path.insert(0, app_dir_env)

    resource_dir_env = os.environ.get("GXPLAB_RESOURCE_DIR", "").strip()
    if resource_dir_env and resource_dir_env not in sys.path:
        sys.path.insert(0, resource_dir_env)

    os.environ.setdefault("PYTHONIOENCODING", "utf-8")

    # Forward argv to the target script
    sys.argv = sys.argv[1:]

    try:
        runpy.run_path(str(script), run_name="__main__")
        return 0
    except SystemExit as e:
        return int(e.code) if isinstance(e.code, int) else 1
    except Exception:
        _write_runner_crash("Runner Crash", f"Script: {script}\nCWD: {Path.cwd()}\nPython: {sys.executable}\n\n{traceback.format_exc()}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
