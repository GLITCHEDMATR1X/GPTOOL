"""Shared HoloVerse hosted-mode entry wrapper.

Legacy dimensions keep their own ``main.py`` files, but their small
``holoverse_entry.py`` stubs call this module so host sizing, ESC-return,
crash logging, and fallback behavior stay consistent across Panda3D and
pygame modes.  This avoids six near-duplicate gateway wrappers drifting apart.
"""
from __future__ import annotations

import json
import os
import runpy
import sys
import time
import traceback
from pathlib import Path
from typing import Iterable

HOST_ENV_KEYS = (
    "HOLOVERSE_HOSTED",
    "HOLOVERSE_EMBEDDED_MODE",
    "MATRIX_LAUNCHED_FROM_CORE",
)
WINDOW_WIDTH_KEYS = ("MATRIX_GAME_WIDTH", "HOLOVERSE_WINDOW_WIDTH", "HOLOVERSE_VIRTUAL_WIDTH")
WINDOW_HEIGHT_KEYS = ("MATRIX_GAME_HEIGHT", "HOLOVERSE_WINDOW_HEIGHT", "HOLOVERSE_VIRTUAL_HEIGHT")
WRAPPER_GATE = "shared_holoverse_hosted_entry_v1"


def _hosted() -> bool:
    return any(str(os.environ.get(key, "")).strip() == "1" for key in HOST_ENV_KEYS)


def _env_int(keys: Iterable[str], default: int) -> int:
    for key in keys:
        raw = os.environ.get(str(key), "").strip()
        if not raw:
            continue
        try:
            value = int(float(raw))
            if value > 0:
                return value
        except Exception:
            continue
    return int(default)


class HostedEntryContext:
    def __init__(self, mode_root: Path, default_mode_name: str, original_entry_name: str = "main.py") -> None:
        self.mode_root = Path(mode_root).resolve()
        self.default_mode_name = str(default_mode_name or self.mode_root.name).strip() or self.mode_root.name
        self.original_entry = self.mode_root / os.environ.get("HOLOVERSE_ORIGINAL_ENTRY", original_entry_name)
        self.return_signal_path = os.environ.get("HOLOVERSE_RETURN_SIGNAL_PATH", "").strip()
        self.hosted = _hosted()

    @property
    def mode_name(self) -> str:
        return os.environ.get("HOLOVERSE_MODE_NAME", self.default_mode_name).strip() or self.default_mode_name

    def write_return_signal(self, reason: str = "return") -> None:
        if not self.return_signal_path:
            return
        try:
            target = Path(self.return_signal_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "request": "return_to_core",
                "reason": str(reason or "return"),
                "mode": self.mode_name,
                "gate": WRAPPER_GATE,
                "timestamp": time.time(),
                "pid": os.getpid(),
            }
            target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        except Exception as exc:
            print(f"holoverse_return_signal_failed: {exc.__class__.__name__}: {exc}")

    def write_wrapper_crash(self, exc: BaseException) -> None:
        try:
            log_dir = self.mode_root / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            payload = {
                "mode": self.mode_name,
                "reason": "wrapper_caught_exception",
                "timestamp": time.time(),
                "exception_type": exc.__class__.__name__,
                "message": str(exc),
                "traceback": "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
                "gate": WRAPPER_GATE,
            }
            (log_dir / "holoverse_wrapper_crash.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        except Exception:
            pass

    def request_return_to_hub(self, reason: str = "escape_return") -> None:
        self.write_return_signal(reason)
        try:
            from direct.showbase.ShowBaseGlobal import base  # type: ignore
            base.userExit()
            return
        except Exception:
            pass
        raise SystemExit(0)

    def patch_panda_for_host(self) -> None:
        if not self.hosted:
            return
        try:
            import panda3d.core as p3core  # type: ignore
        except Exception:
            return
        if getattr(p3core, "_holoverse_hosted_entry_patched", False):
            return
        original_load_prc = p3core.loadPrcFileData
        width = _env_int(WINDOW_WIDTH_KEYS, 1600)
        height = _env_int(WINDOW_HEIGHT_KEYS, 900)
        window_mode = os.environ.get("HOLOVERSE_WINDOW_MODE", "").strip().lower()

        def patched_load_prc_file_data(name, data):
            text = str(data or "")
            lines: list[str] = []
            saw_win_size = False
            saw_cursor = False
            saw_undecorated = False
            saw_origin = False
            for raw in text.splitlines():
                stripped = raw.strip()
                if stripped.startswith("win-size "):
                    lines.append(f"win-size {width} {height}")
                    saw_win_size = True
                elif stripped.startswith("cursor-hidden "):
                    lines.append("cursor-hidden 1")
                    saw_cursor = True
                elif stripped.startswith("undecorated "):
                    lines.append("undecorated true" if window_mode in {"embedded_child", "borderless"} else raw)
                    saw_undecorated = True
                elif stripped.startswith("win-origin "):
                    lines.append(raw)
                    saw_origin = True
                else:
                    lines.append(raw)
            if not saw_win_size:
                lines.append(f"win-size {width} {height}")
            if not saw_cursor:
                lines.append("cursor-hidden 1")
            if window_mode in {"embedded_child", "borderless"}:
                if not saw_undecorated:
                    lines.append("undecorated true")
                if not saw_origin:
                    lines.append("win-origin 0 0")
            return original_load_prc(name, "\n".join(lines))

        p3core.loadPrcFileData = patched_load_prc_file_data
        setattr(p3core, "_holoverse_hosted_entry_patched", True)

    def patch_panda_escape_for_host(self) -> None:
        if not self.hosted or not self.return_signal_path:
            return
        try:
            from direct.showbase.DirectObject import DirectObject  # type: ignore
        except Exception:
            return
        if getattr(DirectObject, "_holoverse_escape_patched", False):
            return
        original_accept = DirectObject.accept
        context = self

        def patched_accept(self_obj, event, method, extraArgs=None):
            event_name = str(event or "").strip().lower()
            if event_name == "escape" and os.environ.get("HOLOVERSE_RETURN_ON_ESC", "1").strip() != "0":
                return original_accept(self_obj, event, context.request_return_to_hub, [])
            return original_accept(self_obj, event, method, [] if extraArgs is None else extraArgs)

        DirectObject.accept = patched_accept
        setattr(DirectObject, "_holoverse_escape_patched", True)

    def patch_pygame_for_host(self) -> None:
        if not self.hosted:
            return
        try:
            import pygame  # type: ignore
        except Exception:
            return
        display = getattr(pygame, "display", None)
        events = getattr(pygame, "event", None)
        if display is None or events is None or getattr(pygame, "_holoverse_hosted_entry_patched", False):
            return
        width = _env_int(WINDOW_WIDTH_KEYS, 1600)
        height = _env_int(WINDOW_HEIGHT_KEYS, 900)
        original_set_mode = display.set_mode
        original_event_get = events.get
        context = self

        def patched_set_mode(size=(0, 0), flags=0, depth=0, display=0, vsync=0):
            try:
                flags = int(flags or 0)
                flags &= ~getattr(pygame, "FULLSCREEN", 0)
                flags |= getattr(pygame, "RESIZABLE", 0)
                return original_set_mode((width, height), flags, depth, display, vsync)
            except TypeError:
                return original_set_mode((width, height), flags, depth)

        def patched_event_get(*args, **kwargs):
            event_list = list(original_event_get(*args, **kwargs))
            for ev in event_list:
                try:
                    if (
                        ev.type == pygame.KEYDOWN
                        and ev.key == pygame.K_ESCAPE
                        and os.environ.get("HOLOVERSE_RETURN_ON_ESC", "1").strip() != "0"
                    ):
                        context.write_return_signal("escape_return")
                except Exception:
                    pass
            return event_list

        display.set_mode = patched_set_mode
        events.get = patched_event_get
        setattr(pygame, "_holoverse_hosted_entry_patched", True)
        os.environ.setdefault("SDL_VIDEO_CENTERED", "1")

    def run(self) -> None:
        if not self.original_entry.exists():
            print("HoloVerse mode entry is missing; returning to MatrixCore.")
            self.request_return_to_hub("entry_missing")
            return
        if str(self.mode_root) not in sys.path:
            sys.path.insert(0, str(self.mode_root))
        self.patch_panda_for_host()
        self.patch_panda_escape_for_host()
        self.patch_pygame_for_host()
        os.environ.setdefault("HOLOVERSE_SINGLE_ESC_RETURN", "1")
        os.environ.setdefault("HOLOVERSE_RETURN_ON_ESC", "1")
        os.environ.setdefault("MATRIX_LAUNCHED_FROM_CORE", "1" if self.hosted else "0")
        sys.argv[0] = str(self.original_entry)
        try:
            runpy.run_path(str(self.original_entry), run_name="__main__")
        except SystemExit as exc:
            code = getattr(exc, "code", 0)
            if code in (None, 0):
                raise
            self.write_wrapper_crash(exc)
            self.request_return_to_hub("system_exit_nonzero")
        except BaseException as exc:
            self.write_wrapper_crash(exc)
            self.request_return_to_hub("mode_crash")


def run_hosted_entry(mode_root: Path | str, default_mode_name: str, original_entry_name: str = "main.py") -> None:
    HostedEntryContext(Path(mode_root), default_mode_name, original_entry_name).run()
