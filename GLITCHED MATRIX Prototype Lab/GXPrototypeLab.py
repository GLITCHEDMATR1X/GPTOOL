#!/usr/bin/env python3
"""Thin launcher wrapper for GLITCHED MATRIX Prototype Lab."""

from __future__ import annotations

import os
import runpy
import sys
import traceback
from pathlib import Path

APP_FOLDER_NAME = "GLITCHED MATRIX Prototype Lab"


def _looks_like_app_root(path: Path) -> bool:
    try:
        return (path / "data" / "gx_app_main.py").is_file() and (path / "data" / "gx_core" / "runtime_paths.py").is_file()
    except Exception:
        return False


def _find_app_root() -> Path:
    """Resolve the real app folder without creating drive-root folders.

    Some installs launch GXPrototypeLab.py from a shortcut/copy that lives one
    level above the actual app folder.  The old wrapper treated that launcher
    location as APP_BASE_DIR, which could create empty data/games folders beside
    the drive root.  Prefer the folder that actually owns data/gx_app_main.py.
    """
    here = Path(__file__).resolve().parent
    candidates = [
        here,
        here / APP_FOLDER_NAME,
        here.parent / APP_FOLDER_NAME,
        Path.cwd(),
        Path.cwd() / APP_FOLDER_NAME,
    ]
    seen: set[str] = set()
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except Exception:
            resolved = candidate
        key = str(resolved).lower()
        if key in seen:
            continue
        seen.add(key)
        if _looks_like_app_root(resolved):
            return resolved
    return here


ROOT_DIR = _find_app_root()
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from data.gx_core import runtime_paths as gx_runtime

gx_runtime.configure_runtime_base(app_base_dir=ROOT_DIR, resource_base_dir=ROOT_DIR)

from data.gx_app_main import main


def _run_python_script_argument_if_present() -> bool:
    """Let a frozen GXPrototypeLab.exe safely act like Python for child scripts."""
    if len(sys.argv) < 2:
        return False
    raw = str(sys.argv[1] or "").strip().strip('"')
    if not raw.lower().endswith(".py"):
        return False
    script = Path(raw)
    if not script.is_absolute():
        script = (Path.cwd() / script).resolve()
    if not script.exists() or not script.is_file():
        return False

    try:
        os.chdir(script.parent)
    except Exception:
        pass

    for path in (
        script.parent,
        ROOT_DIR,
        ROOT_DIR / "data",
        ROOT_DIR / "data" / "HoloVerse",
        ROOT_DIR / "data" / "Prototype Lab",
    ):
        try:
            sp = str(Path(path).resolve())
            if sp not in sys.path:
                sys.path.insert(0, sp)
        except Exception:
            pass

    os.environ.setdefault("GXPLAB_APP_DIR", str(ROOT_DIR))
    os.environ.setdefault("GXPLAB_RESOURCE_DIR", str(ROOT_DIR))
    os.environ.setdefault("PYTHONUNBUFFERED", "1")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    sys.argv = [str(script), *sys.argv[2:]]
    try:
        runpy.run_path(str(script), run_name="__main__")
    except SystemExit:
        raise
    except Exception:
        try:
            crash_dir = ROOT_DIR / "crash_reports"
            crash_dir.mkdir(parents=True, exist_ok=True)
            (crash_dir / "latest_runner_fallback_crash.txt").write_text(
                "GXPrototypeLab.exe child-script fallback crashed\n\n"
                f"Script: {script}\nCWD: {Path.cwd()}\nExecutable: {sys.executable}\n\n"
                + traceback.format_exc(),
                encoding="utf-8",
                errors="replace",
            )
        except Exception:
            pass
        raise
    return True


if __name__ == "__main__":
    if not _run_python_script_argument_if_present():
        main()
