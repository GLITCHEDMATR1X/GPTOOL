#!/usr/bin/env python3
"""
GXPrototypeLab_boot.py

PyInstaller-safe entrypoint:
- Forces working directory to the folder containing the executable (portable folder layout).
- Enables DPI awareness (reduces "wrong resolution" / scaling issues on Windows).
- Redirects sys.executable to a bundled runner (py_runner) so GXPrototypeLab can launch other .py games/tools.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _set_dpi_awareness() -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes

        # Prefer per-monitor DPI awareness (Win 8.1+)
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
        except Exception:
            pass

        # Fallback
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass
    except Exception:
        pass


def _app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def main() -> None:
    _set_dpi_awareness()

    base = _app_dir()
    try:
        os.chdir(base)
    except Exception:
        pass

    # Do not create crash_reports on normal launch; crash handlers create it on demand.

    os.environ["GXPLAB_APP_DIR"] = str(base)
    os.environ["GXPLAB_RESOURCE_DIR"] = str(getattr(sys, "_MEIPASS", base))

    # Use the bundled runner so GXPrototypeLab can spawn python scripts even when frozen.
    runner = base / "py_runner" / "py_runner.exe"
    if runner.exists():
        sys.executable = str(runner)

    # Import and run the real app
    import GXPrototypeLab  # noqa: F401

    GXPrototypeLab.main()


if __name__ == "__main__":
    main()
