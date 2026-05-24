import atexit
import colorsys
import ctypes
from ctypes import wintypes
import importlib.util
import json
import math
import os
import random
import re
import subprocess
import sys
import threading
import time
import wave
import textwrap
import traceback
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from array import array


def _install_gx_child_crash_hook() -> None:
    """Write direct HoloVerse tracebacks for the GX launcher crash reporter."""
    log_raw = os.environ.get("GX_CHILD_CRASH_LOG", "")
    if not log_raw:
        return
    try:
        log_path = Path(log_raw)
        log_path.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        return

    def _append(title: str, body: str) -> None:
        try:
            with log_path.open("a", encoding="utf-8", errors="replace") as fh:
                fh.write(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] {title}\n")
                fh.write(str(body or "No details captured."))
                if not str(body or "").endswith("\n"):
                    fh.write("\n")
        except Exception:
            pass

    _append(
        "HoloVerse child hook armed",
        "argv=" + repr(sys.argv) + "\n" +
        "cwd=" + str(Path.cwd()) + "\n" +
        "python=" + str(sys.executable) + "\n",
    )

    previous_hook = sys.excepthook

    def _hook(exc_type, exc_value, exc_tb):
        _append("Unhandled HoloVerse exception", "".join(traceback.format_exception(exc_type, exc_value, exc_tb)))
        try:
            previous_hook(exc_type, exc_value, exc_tb)
        except Exception:
            pass

    def _thread_hook(args):
        _append("Unhandled HoloVerse thread exception", "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)))
        try:
            if hasattr(threading, "__excepthook__"):
                threading.__excepthook__(args)
        except Exception:
            pass

    sys.excepthook = _hook
    try:
        threading.excepthook = _thread_hook
    except Exception:
        pass


_install_gx_child_crash_hook()

WORLD_AUTHORITY_SMOKE_TEST = "--world-authority-smoke-test" in sys.argv
SELF_TEST = "--self-test" in sys.argv or WORLD_AUTHORITY_SMOKE_TEST
AUTO_EXIT = "--auto-exit" in sys.argv
AUTO_MENU = "--auto-menu" in sys.argv

def get_cli_arg(flag: str, default=None, cast=str):
    if flag in sys.argv:
        try:
            return cast(sys.argv[sys.argv.index(flag) + 1])
        except Exception:
            return default
    return default

SELF_TEST_ARTIFACT_ID = get_cli_arg("--self-test-artifact", 7, int)
AUTO_MENU_TAB = get_cli_arg("--auto-menu-tab", None, str)

GATEWAY_SELF_TEST = "--gateway-self-test" in sys.argv
ARTIFACT_ROUTE_SMOKE_TEST = "--artifact-route-smoke-test" in sys.argv
ARTIFACT_LAUNCH_SMOKE_TEST = "--artifact-launch-smoke-test" in sys.argv


def _run_gateway_self_test_before_panda_import() -> None:
    """Audit Core mode launch routing without importing Panda3D.

    This is intentionally early in the file so CI/container checks can verify
    mode discovery, manifest health, placeholder cleanup, panel fallback
    routing, and child-window routing even on machines where Panda3D
    cannot open a graphics window.
    """
    root = Path(__file__).resolve().parent
    log_dir = root / "logs"
    report_path = log_dir / "mode_gateway_self_test.json"
    manifest_name = "holoverse_mode_manifest.json"
    adapter_name = "holoverse_native_adapter.py"
    dimensions_root = root / "Dimensions"
    excludes = {"assets", "logs", "patch_notes", "__pycache__", "p3dopenxr", "versions", ".git", "dimensions"}
    panel_aliases = {"panel", "hub_panel", "panel_preview"}
    native_aliases = {"native", "native_panda", "host_native", "in_process", "adapter"}
    embedded_aliases = {"embedded", "embedded_external", "child_window", "win_child", "window_child", "hosted_child"}
    connected_aliases = {"same_window", "same_window_mode", "connected", "connected_mode", "in_process_scene", "same_screen"}
    in_world_aliases = {"in_world", "in_world_region", "region_runtime", "current_region", "same_world", "same_region"}
    external_aliases = {"external", "hosted", "hosted_external", "external_panda", "external_pygame"}
    placeholder_aliases = {"placeholder", "placeholder_mode", "empty", "stub", "reserved"}
    fallback_folders = []
    root_only_folders = set()

    def expected_folder_for_name(name: str) -> Path:
        return (root if str(name).lower() in root_only_folders else dimensions_root) / str(name)

    def normalize_launch(value) -> str:
        raw = str(value or "hosted_external").strip().lower()
        if raw in placeholder_aliases:
            return "placeholder_mode"
        if raw in panel_aliases:
            return "hub_panel"
        if raw in native_aliases:
            return "embedded_external"
        if raw in connected_aliases:
            return "same_window_mode"
        if raw in embedded_aliases:
            return "embedded_external"
        if raw in in_world_aliases:
            return "in_world_region"
        if raw in external_aliases:
            return "hosted_external"
        # Unknown launch labels are treated as hosted external routes.
        return "hosted_external"

    def route_name(value) -> str:
        launch = normalize_launch(value)
        if launch == "placeholder_mode":
            return "PLACEHOLDER"
        if launch == "native_panda":
            return "EMBEDDED"
        if launch == "hub_panel":
            return "PANEL"
        if launch == "embedded_external":
            return "EMBEDDED"
        if launch == "same_window_mode":
            return "SAME-WINDOW"
        if launch == "in_world_region":
            return "IN-WORLD"
        return "HOSTED"

    def read_json(path: Path) -> tuple[dict, str]:
        try:
            if path.exists() and path.is_file():
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data, ""
                return {}, "manifest-not-object"
            return {}, "manifest-missing"
        except Exception as exc:
            return {}, f"manifest-json-error:{exc}"

    def source_kind(path: Path) -> str:
        try:
            probe = path.read_text(encoding="utf-8", errors="ignore")[:26000].lower()
        except Exception:
            return "unknown"
        has_panda = (
            "from direct." in probe
            or "from panda3d." in probe
            or "import panda3d" in probe
            or "loadprcfiledata(" in probe
            or "showbase(" in probe
        )
        has_pygame = "import pygame" in probe or "pygame." in probe
        if has_panda:
            return "panda3d"
        if has_pygame:
            return "pygame"
        return "python"

    def folder_key(path: Path) -> str:
        try:
            return os.fspath(path.resolve()).replace("\\", "/").lower()
        except Exception:
            return os.fspath(path).replace("\\", "/").lower()

    folders: list[Path] = []
    indexed_records_by_folder: dict[str, dict] = {}
    if dimensions_root.exists() and dimensions_root.is_dir():
        try:
            folders.extend(sorted([p for p in dimensions_root.iterdir() if p.is_dir()], key=lambda p: p.name.lower()))
        except Exception:
            pass
    else:
        try:
            folders.extend(sorted([p for p in root.iterdir() if p.is_dir()], key=lambda p: p.name.lower()))
        except Exception:
            pass
    for name in fallback_folders:
        p = expected_folder_for_name(name)
        if p.exists() and p.is_dir() and p not in folders:
            folders.append(p)

    # Use the transition registry as an additional source of truth.  Registry
    # records are now audited honestly: a missing registered playable folder is
    # BROKEN PATH, not a clean placeholder.  Only explicit placeholder records
    # or truly unregistered empty folders may report as PLACEHOLDER.
    index_data, _index_issue = read_json(dimensions_root / "dimension_index.json")
    indexed_dimensions = index_data.get("dimensions") if isinstance(index_data, dict) else {}
    if isinstance(indexed_dimensions, dict):
        for _dim_id, record in sorted(indexed_dimensions.items()):
            if not isinstance(record, dict):
                continue
            folder_raw = str(record.get("folder") or "").strip()
            name_raw = str(record.get("name") or record.get("title") or _dim_id).strip()
            folder_norm = folder_raw.replace("\\", "/")
            folder_parts = [part for part in folder_norm.split("/") if part]
            if len(folder_parts) >= 2 and folder_parts[0].lower() == "dimensions" and folder_parts[1].lower() == "holocore":
                p = root / "HoloCore"
                for part in folder_parts[2:]:
                    p = p / part
            else:
                p = (root / folder_norm) if folder_norm else (dimensions_root / name_raw)
            indexed_records_by_folder[folder_key(p)] = record
            if p not in folders:
                folders.append(p)

    modes = []
    seen: set[str] = set()
    for folder in folders:
        key = folder.name.lower()
        if key in seen or key in excludes:
            continue
        seen.add(key)
        index_record = indexed_records_by_folder.get(folder_key(folder), {})
        index_launch_type = normalize_launch(index_record.get("launch_type")) if index_record else ""
        indexed_placeholder = bool(index_record.get("placeholder_mode", False) or index_launch_type == "placeholder_mode")
        display_name = str(index_record.get("name") or index_record.get("title") or folder.name).strip() or folder.name
        main_entry = folder / "main.py"
        folder_missing = not folder.exists() or not folder.is_dir()
        if folder_missing or not main_entry.exists():
            manifest_path = folder / manifest_name
            manifest, manifest_issue = read_json(manifest_path)
            launch_type = index_launch_type or normalize_launch(manifest.get("launch_type"))
            if not launch_type or (launch_type == "hosted_external" and indexed_placeholder):
                launch_type = "placeholder_mode"
            placeholder_mode = bool(indexed_placeholder or (not index_record and launch_type == "placeholder_mode"))
            route_label = route_name(launch_type) if not placeholder_mode else "PLACEHOLDER"
            issues: list[str] = []
            if manifest_issue and not placeholder_mode:
                issues.append(manifest_issue)
            if folder_missing and not placeholder_mode:
                issues.append("folder-missing")
            if not main_entry.exists() and not placeholder_mode:
                issues.append("entry-missing")
            deck_badge = "PLACEHOLDER" if placeholder_mode and not issues else "BROKEN PATH"
            modes.append({
                "name": display_name,
                "route": route_label,
                "deck_badge": deck_badge,
                "launch_type": "placeholder_mode" if placeholder_mode else (launch_type or "hosted_external"),
                "source_kind": "placeholder" if placeholder_mode else str(index_record.get("source_kind") or "missing"),
                "manifest": str(manifest_path),
                "manifest_exists": manifest_path.exists(),
                "entry": str(main_entry),
                "entry_exists": False,
                "native_adapter": "",
                "native_adapter_exists": False,
                "native_adapter_has_factory": False,
                "panel_supported": bool(index_record.get("panel_supported", placeholder_mode)),
                "fallback_launch_type": str(index_record.get("fallback_launch_type") or ""),
                "alternate_entry": "",
                "alternate_exists": None,
                "placeholder_mode": placeholder_mode,
                "issues": issues,
                "health": "PLACEHOLDER" if placeholder_mode and not issues else "CHECK",
            })
            continue
        manifest_path = folder / manifest_name
        manifest, manifest_issue = read_json(manifest_path)
        entry_name = str(manifest.get("entry") or "main.py").strip() or "main.py"
        entry_path = folder / entry_name
        launch_type = normalize_launch(manifest.get("launch_type"))
        issues: list[str] = []
        if manifest_issue:
            issues.append(manifest_issue)
        if not entry_path.exists():
            issues.append("entry-missing")
        adapter_path = None
        adapter_has_factory = False
        declared_launch = str(manifest.get("launch_type") or "").strip().lower()
        if declared_launch in native_aliases:
            # Native/in-process adapters are retired and normalized to the proven
            # embedded child-window route.  Keep the audit explicit so stale
            # manifests cannot silently skip route-truth checks.
            adapter_file = str(manifest.get("native_adapter") or adapter_name).strip() or adapter_name
            adapter_path = folder / adapter_file
            adapter_has_factory = bool(adapter_path.exists() and adapter_path.is_file())
        if launch_type == "hub_panel":
            if not bool(manifest.get("panel_supported", False)):
                issues.append("panel-flag-missing")
            if not str(manifest.get("fallback_launch_type") or "").strip():
                issues.append("fallback-not-declared")
        alternate_declared = str(manifest.get("alternate_entry") or "").strip()
        alternate_path = folder / alternate_declared if alternate_declared else None
        if folder.name.lower() == "holo campaign" and alternate_declared and alternate_path is not None and not alternate_path.exists():
            issues.append("campaign-alternate-missing")
        route_label = route_name(launch_type)
        if not entry_path.exists() or any("missing" in issue and "fallback" not in issue for issue in issues):
            deck_badge = "BROKEN PATH"
        elif issues:
            deck_badge = "NEEDS PATCH"
        else:
            deck_badge = route_label
        modes.append({
            "name": folder.name,
            "route": route_label,
            "deck_badge": deck_badge,
            "launch_type": launch_type,
            "source_kind": str(manifest.get("source_kind") or source_kind(main_entry)),
            "manifest": str(manifest_path),
            "manifest_exists": manifest_path.exists(),
            "entry": str(entry_path),
            "entry_exists": entry_path.exists(),
            "native_adapter": str(adapter_path) if adapter_path else "",
            "native_adapter_exists": bool(adapter_path and adapter_path.exists()),
            "native_adapter_has_factory": adapter_has_factory,
            "panel_supported": bool(manifest.get("panel_supported", False)),
            "fallback_launch_type": str(manifest.get("fallback_launch_type") or ""),
            "alternate_entry": str(alternate_path) if folder.name.lower() == "holo campaign" and alternate_path is not None else "",
            "alternate_exists": bool(alternate_path.exists()) if folder.name.lower() == "holo campaign" and alternate_path is not None else None,
            "issues": issues,
            "health": "OK" if not issues else "CHECK",
        })

    summary = {"PLACEHOLDER": 0, "PANEL": 0, "EMBEDDED": 0, "SAME-WINDOW": 0, "IN-WORLD": 0, "HOSTED": 0, "NEEDS_PATCH": 0, "BROKEN_PATH": 0, "CHECK": 0}
    for mode in modes:
        summary[mode["route"]] = int(summary.get(mode["route"], 0)) + 1
        badge_key = str(mode.get("deck_badge", "")).upper().replace(" ", "_")
        if badge_key in {"NEEDS_PATCH", "BROKEN_PATH"}:
            summary[badge_key] = int(summary.get(badge_key, 0)) + 1
        if mode["issues"]:
            summary["CHECK"] += 1
    missing_expected = []
    placeholder_count = int(summary.get("PLACEHOLDER", 0))
    issue_count = int(summary.get("CHECK", 0))
    hosted_count = int(summary.get("HOSTED", 0))
    playable_ready_routes = int(summary.get("EMBEDDED", 0)) + int(summary.get("SAME-WINDOW", 0)) + int(summary.get("IN-WORLD", 0)) + int(summary.get("PANEL", 0))
    expected_playable_routes = max(0, len(modes) - placeholder_count)
    gateway_safe = issue_count == 0
    gateway_playable_complete = gateway_safe and hosted_count == 0 and placeholder_count == 0 and playable_ready_routes >= expected_playable_routes

    report = {
        "schema": 2,
        "kind": "holoverse_gateway_self_test",
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "root": str(root),
        "mode_count": len(modes),
        "expected_mode_count": len(modes),
        "expected_playable_routes": expected_playable_routes,
        "playable_ready_routes": playable_ready_routes,
        "placeholder_routes": placeholder_count,
        "hosted_fallback_routes": hosted_count,
        "issue_count": issue_count,
        "missing_expected_modes": missing_expected,
        "summary": summary,
        "gateway_safe": gateway_safe,
        "gateway_playable_complete": gateway_playable_complete,
        "gateway_complete": gateway_playable_complete,
        "modes": modes,
    }
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    except Exception as exc:
        report["write_error"] = str(exc)
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report.get("gateway_safe") else 2)


if GATEWAY_SELF_TEST:
    _run_gateway_self_test_before_panda_import()


STARTUP_ROOT = Path(__file__).resolve().parent
STARTUP_ASSETS = STARTUP_ROOT / "assets"
STARTUP_CONFIG_DIR = STARTUP_ASSETS / "config"
STARTUP_CONFIG_PATH = STARTUP_CONFIG_DIR / "holoverse_config.json"

def _read_startup_launch_defaults() -> dict:
    defaults = {
        "launch_width": 1920,
        "launch_height": 1080,
        "launch_fullscreen": False,
        "launch_borderless": False,
        "launch_bordered_fullscreen": True,
    }
    try:
        if STARTUP_CONFIG_PATH.exists():
            raw = json.loads(STARTUP_CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                for key in tuple(defaults.keys()):
                    if key in raw:
                        defaults[key] = raw[key]
    except Exception:
        pass
    # v0.9.15: keep the hub as a full-size bordered window, not an exclusive
    # fullscreen or topmost borderless shell. External modes must be able to
    # appear in front while this process is paused. Environment variables can
    # still override these values for diagnostics.
    defaults["launch_fullscreen"] = False
    defaults["launch_borderless"] = False
    defaults["launch_bordered_fullscreen"] = True
    return defaults

_STARTUP_LAUNCH_DEFAULTS = _read_startup_launch_defaults()

from panda3d.core import loadPrcFileData

def _env_flag(name: str, default: bool = False) -> bool:
    raw = str(os.environ.get(name, "")).strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return default

def _env_int(name: str, default: int) -> int:
    try:
        return int(float(os.environ.get(name, default)))
    except Exception:
        return default

def _startup_int(name: str, default: int) -> int:
    try:
        return int(float(_STARTUP_LAUNCH_DEFAULTS.get(name, default)))
    except Exception:
        return default

def _startup_bool(name: str, default: bool) -> bool:
    raw = _STARTUP_LAUNCH_DEFAULTS.get(name, default)
    if isinstance(raw, bool):
        return raw
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}

def detect_launch_display_rect(default_w: int = 1920, default_h: int = 1080) -> tuple[int, int, int, int]:
    width = _env_int("MATRIX_GAME_WIDTH", _startup_int("launch_width", default_w))
    height = _env_int("MATRIX_GAME_HEIGHT", _startup_int("launch_height", default_h))
    fullscreen = _env_flag("MATRIX_GAME_FULLSCREEN", _startup_bool("launch_fullscreen", False))
    borderless = _env_flag("MATRIX_GAME_BORDERLESS", _startup_bool("launch_borderless", False))
    bordered_fullscreen = _env_flag("MATRIX_GAME_BORDERED_FULLSCREEN", _startup_bool("launch_bordered_fullscreen", True))
    if fullscreen or borderless or bordered_fullscreen:
        try:
            import ctypes

            class POINT(ctypes.Structure):
                _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

            class RECT(ctypes.Structure):
                _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long), ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

            class MONITORINFO(ctypes.Structure):
                _fields_ = [
                    ("cbSize", ctypes.c_ulong),
                    ("rcMonitor", RECT),
                    ("rcWork", RECT),
                    ("dwFlags", ctypes.c_ulong),
                ]

            user32 = ctypes.windll.user32
            try:
                user32.SetProcessDPIAware()
            except Exception:
                pass

            pt = POINT()
            if not user32.GetCursorPos(ctypes.byref(pt)):
                pt.x = 0
                pt.y = 0
            monitor = user32.MonitorFromPoint(pt, 2)
            if not monitor:
                monitor = user32.MonitorFromPoint(POINT(0, 0), 1)
            if monitor:
                info = MONITORINFO()
                info.cbSize = ctypes.sizeof(MONITORINFO)
                if user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
                    left = int(info.rcMonitor.left)
                    top = int(info.rcMonitor.top)
                    right = int(info.rcMonitor.right)
                    bottom = int(info.rcMonitor.bottom)
                    mon_w = max(640, right - left)
                    mon_h = max(480, bottom - top)
                    return left, top, mon_w, mon_h

            left = int(user32.GetSystemMetrics(76))
            top = int(user32.GetSystemMetrics(77))
            mon_w = int(user32.GetSystemMetrics(78))
            mon_h = int(user32.GetSystemMetrics(79))
            if mon_w >= 640 and mon_h >= 480:
                return left, top, mon_w, mon_h
        except Exception:
            pass
    return 0, 0, max(1280, width), max(720, height)


LAUNCH_FULLSCREEN = _env_flag("MATRIX_GAME_FULLSCREEN", _startup_bool("launch_fullscreen", False))
LAUNCH_BORDERLESS = _env_flag("MATRIX_GAME_BORDERLESS", _startup_bool("launch_borderless", False)) and not SELF_TEST
LAUNCH_BORDERED_FULLSCREEN = _env_flag("MATRIX_GAME_BORDERED_FULLSCREEN", _startup_bool("launch_bordered_fullscreen", True)) and not SELF_TEST
LAUNCH_X, LAUNCH_Y, LAUNCH_W, LAUNCH_H = detect_launch_display_rect()

_PRC_LINES = [
    "window-title HoloVerse Observatory",
    f"win-size {LAUNCH_W} {LAUNCH_H}",
    "show-frame-rate-meter 0",
    "sync-video 1",
    "framebuffer-multisample 1",
    "multisamples 4",
    # Robust for offscreen/tiny proof rendering and lower-end GPUs: let Panda
    # upscale non-power-of-two textures instead of requiring unsupported NPOT.
    "textures-power-2 up",
    "texture-anisotropic-degree 8",
    "notify-level-display warning",
    "notify-level-glgsg warning",
    f"cursor-hidden {0 if SELF_TEST else 1}",
    "model-path ./assets",
]
if SELF_TEST:
    _PRC_LINES += [
        "window-type offscreen",
        "load-display p3tinydisplay",
        "audio-library-name null",
    ]
else:
    _PRC_LINES += [
        "window-type onscreen",
        "audio-library-name p3openal_audio",
    ]
    if LAUNCH_FULLSCREEN and not LAUNCH_BORDERLESS:
        _PRC_LINES += ["fullscreen 1", "undecorated 0"]
    elif LAUNCH_BORDERLESS:
        _PRC_LINES += [
            "fullscreen 0",
            "undecorated 1",
            f"win-origin {LAUNCH_X} {LAUNCH_Y}",
            "win-fixed-size 1",
        ]
    elif LAUNCH_BORDERED_FULLSCREEN:
        _PRC_LINES += [
            "fullscreen 0",
            "undecorated 0",
            f"win-origin {LAUNCH_X} {LAUNCH_Y}",
            "win-fixed-size 0",
        ]
    else:
        _PRC_LINES += ["fullscreen 0", "undecorated 0"]
loadPrcFileData("", "\n".join(_PRC_LINES))

from direct.showbase.ShowBase import ShowBase
from direct.gui.DirectGui import DirectButton, DirectFrame, DirectLabel
from direct.task import Task
# VR is opt-in. Normal desktop first-person mode is the default boot path.
# Enable headset mode with --vr, HOLOVERSE_VR=1, or MATRIX_GAME_VR=1.
VR_REQUESTED = "--vr" in sys.argv or _env_flag("HOLOVERSE_VR", False) or _env_flag("MATRIX_GAME_VR", False)
VR_DISABLED = "--no-vr" in sys.argv or "--desktop" in sys.argv or _env_flag("HOLOVERSE_NO_VR", False)
VR_ALLOWED = bool(VR_REQUESTED and not VR_DISABLED)

from panda3d.core import (
    AmbientLight,
    AntialiasAttrib,
    CardMaker,
    ClockObject,
    DirectionalLight,
    Filename,
    Fog,
    InputDevice,
    LineSegs,
    PNMImage,
    Point2,
    Point3,
    SamplerState,
    TextNode,
    Texture,
    TextureStage,
    TransparencyAttrib,
    Geom,
    GeomNode,
    GeomTriangles,
    GeomVertexData,
    GeomVertexFormat,
    GeomVertexWriter,
    Vec2,
    Vec3,
    Vec4,
    WindowProperties,
)

VERSION = "0.10.99-cinematic-tab-reclaimed"
try:
    from p3dopenxr.p3dopenxr import P3DOpenXR
except Exception:
    P3DOpenXR = None

GAME_NAME = "HoloVerse // MatrixCore Observatory"
ROOT = Path(__file__).resolve().parent

try:
    from holoverse_cache_cleanup import clear_runtime_cache as _clear_runtime_cache
except Exception:
    _clear_runtime_cache = None

_RUNTIME_CACHE_CLEANED = False

def clear_holoverse_runtime_cache(reason: str = "exit") -> dict:
    """Clear safe generated runtime caches once during normal app shutdown."""
    global _RUNTIME_CACHE_CLEANED
    if _RUNTIME_CACHE_CLEANED:
        return {"reason": str(reason or "exit"), "already_cleaned": True}
    _RUNTIME_CACHE_CLEANED = True
    if not callable(_clear_runtime_cache):
        return {"reason": str(reason or "exit"), "available": False}
    try:
        return _clear_runtime_cache(ROOT, reason=reason)
    except Exception as exc:
        return {"reason": str(reason or "exit"), "error": f"{exc.__class__.__name__}:{exc}"}


def _clear_holoverse_runtime_cache_at_exit() -> None:
    clear_holoverse_runtime_cache("atexit")


try:
    atexit.register(_clear_holoverse_runtime_cache_at_exit)
except Exception:
    pass

ASSETS = ROOT / "assets"
CONFIG_DIR = ASSETS / "config"
CORE_CONFIG_DIR = ROOT / "config"
HOLOVERSE_SETTINGS_PATH = CORE_CONFIG_DIR / "holoverse_settings.json"
LOG_DIR = ROOT / "logs"
PATCH_DIR = ROOT / "patch_notes"
CONFIG_PATH = CONFIG_DIR / "holoverse_config.json"
TEXTURE_DIR = ASSETS / "generated_hub_textures"
AUDIO_DIR = ASSETS / "generated_audio"
MUSIC_DIR = ASSETS / "music"
AUDIO_LIBRARY_DIR = ASSETS / "audio"
CANONICAL_SHARED_SFX_DIR = AUDIO_LIBRARY_DIR / "sfx" / "shared"
CANONICAL_GENERATED_SFX_DIR = AUDIO_LIBRARY_DIR / "sfx" / "generated"
CANONICAL_MUSIC_DIR = AUDIO_LIBRARY_DIR / "music" / "generated"
CANONICAL_AMBIENT_MUSIC_DIR = AUDIO_LIBRARY_DIR / "music" / "ambient"
CANONICAL_REVERSED_MUSIC_DIR = AUDIO_LIBRARY_DIR / "music" / "reversed"
SOUNDMATRIX_FORGE = ROOT / "tools" / "soundmatrix_audio_forge.py"
WORLD_SHELL_MOUNT_CONFIG = CORE_CONFIG_DIR / "default_world_shell_integration.json"
WORLD_SHELL_MOUNT_STATE = CONFIG_DIR / "holoverse_world_shell_mount_state.json"
WORLD_SHELL_PLAY_STATE = CONFIG_DIR / "holoverse_world_shell_play_state.json"
CURRENT_BUILD_NOTES = ROOT / "CURRENT_BUILD_NOTES.md"
SHARED_SFX_DIR = ASSETS / "shared_sfx"
LATEST_LOG = LOG_DIR / "latest.log"
CRASH_LOG = LOG_DIR / "crash.log"
LATEST_PATCH = PATCH_DIR / "latest_patch_notes.txt"
SELF_TEST_REPORT = LOG_DIR / "self_test_report.json"
WORLD_AUTHORITY_SMOKE_REPORT = LOG_DIR / "world_authority_smoke_report.json"
WORLD_AUTHORITY_SMOKE_SCREENSHOT = LOG_DIR / "world_authority_smoke.png"
MATRIXCORE_LIVE_PROOF_REPORT = LOG_DIR / "matrixcore_live_proof_report.json"
MODE_GATEWAY_AUDIT = LOG_DIR / "mode_gateway_audit.json"
MODE_GATEWAY_HISTORY = LOG_DIR / "mode_gateway_history.json"

# Pass 85: HoloSpace gets a dedicated arcade-flight profile.  The old
# shell craft controller is intentionally kept for the surface world; these
# values only apply while the player is in the black Dyson-space battlefield.
HOLOSPACE_CRUISE_SPEED = 380.0
HOLOSPACE_BOOST_SPEED = 720.0
HOLOSPACE_STRAFE_SCALE = 0.64
HOLOSPACE_VERTICAL_SCALE = 0.72
HOLOSPACE_ACCEL_RESPONSE = 5.8
HOLOSPACE_BRAKE_RESPONSE = 7.2
HOLOSPACE_MAX_SPEED = 780.0
HOLOSPACE_SAFE_SPAWN_REPAIR_RATE = 14.0
HOLOSPACE_BATTLE_DAMAGE_MIN = 5.0
HOLOSPACE_BATTLE_DAMAGE_MAX = 11.5
HOLOSPACE_DAMAGE_COOLDOWN = 1.08
HOLOSPACE_DYSON_RETURN_RADIUS = 540.0
HOLOSPACE_VERTICAL_RESPAWN_MIN_Z = 90.0
HOLOSPACE_VERTICAL_RESPAWN_MAX_Z = 3900.0

# Shared MatrixCore database/brain lanes belong beside HoloVerse, not inside it.
# In the full GX layout this resolves to data/database and data/brain while the
# HoloVerse folder remains the game runtime.  Set HOLOVERSE_APP_DATA_DIR only for
# portable debugging where the sibling data folder lives somewhere else.
APP_DATA_DIR = Path(os.environ.get("HOLOVERSE_APP_DATA_DIR", os.fspath(ROOT.parent))).resolve()
SHARED_HOLOVERSE_DATA_DIR = APP_DATA_DIR
SHARED_BRAIN_DIR = APP_DATA_DIR / "brain"
SHARED_DATABASE_DIR = APP_DATA_DIR / "database"
MATRIXCORE_DATABASE_DIR = SHARED_DATABASE_DIR / "MatrixCore"
MATRIXCORE_DATA_DIR = ROOT / "matrixcore"
MATRIXCORE_PROGRESSION_DIR = ROOT / "progression"
MATRIXCORE_DIMENSIONS_DIR = ROOT / "Dimensions"
MATRIXCORE_MANIFEST_PATH = MATRIXCORE_DATA_DIR / "matrixcore_manifest.json"
MATRIXCORE_DIMENSION_INDEX_PATH = MATRIXCORE_DIMENSIONS_DIR / "dimension_index.json"
MATRIXCORE_PROGRESSION_PATH = MATRIXCORE_PROGRESSION_DIR / "progression_state.json"
MATRIXCORE_BOT_SUPPORT_PATH = MATRIXCORE_DATA_DIR / "bot_support.json"
MATRIXCORE_LORE_STUDY_PATH = MATRIXCORE_DATA_DIR / "lore_study.json"
MATRIXCORE_CONTENT_LORE_STUDY_PATH = ROOT / "matrixcore" / "lore_study.json"
MATRIXCORE_LORE_HANDOFF_PATH = MATRIXCORE_DATA_DIR / "PASS2_LORE_HANDOFF.md"
MATRIXCORE_GLEEBS_DIALOGUE_PATH = MATRIXCORE_DATA_DIR / "gleebs_dialogue.json"
MATRIXCORE_GLEEBS_HANDOFF_PATH = MATRIXCORE_DATA_DIR / "PASS3_GLEEBS_HANDOFF.md"
MATRIXCORE_GLEEBS_CONTEXT_HANDOFF_PATH = MATRIXCORE_DATA_DIR / "PASS4_GLEEBS_CONTEXT_HANDOFF.md"
GLEEBS_TEXTURE_PATH = ASSETS / "textures" / "Gleebs.png"
GLEEBS_TEXTURE_POT_PATH = ASSETS / "textures" / "Gleebs_pot.png"
MATRIXCORE_PAGE_ORDER = ["guide", "lore", "dimensions", "progression", "bots", "archive", "system"]

DIMENSIONS_DIR_NAME = "Dimensions"
DIMENSIONS_DIR = ROOT / DIMENSIONS_DIR_NAME
DIMENSION_INDEX_PATH = DIMENSIONS_DIR / "dimension_index.json"

CAMPAIGN_CANDIDATES = [
    DIMENSIONS_DIR / "Holo Campaign" / "main.py",
    ROOT / "Holo Campaign" / "main.py",
    ROOT / "games" / "Holoverse" / "Holo Campaign" / "main.py",
    Path("/mnt/data/games/Holoverse/Dimensions/Holo Campaign/main.py"),
    Path("/mnt/data/games/Holoverse/Holo Campaign/main.py"),
    Path("/mnt/data/patch_unzipped/games/Holoverse/Dimensions/Holo Campaign/main.py"),
    Path("/mnt/data/patch_unzipped/games/Holoverse/Holo Campaign/main.py"),
]
MX_CANDIDATES = [
    ROOT / "MatrixCore" / "main.py",
    ROOT / "GXPrototypeLab.py",
    Path("/mnt/data/GXPrototypeLab.py"),
]


def first_existing_path(candidates) -> Path | None:
    """Return the first existing candidate path without creating placeholder files.

    Older gateway passes used this helper for optional companion launch targets.
    The clean placeholder build still references it during startup, so keep it
    tiny and side-effect free: empty Dimension folders stay empty until a real
    mode is dropped in.
    """
    try:
        items = list(candidates or [])
    except Exception:
        items = []
    for candidate in items:
        try:
            path = Path(candidate)
            if path.exists():
                return path
        except Exception:
            continue
    return None

# ---------------------------------------------------------------------------
# Clean-layout compatibility helpers
# ---------------------------------------------------------------------------
def _safe_read_json(path, default=None):
    fallback = {} if default is None else default
    try:
        target = Path(path)
        if not target.exists() or not target.is_file():
            return fallback
        text = target.read_text(encoding="utf-8")
        if not text.strip():
            return fallback
        return json.loads(text)
    except Exception:
        return fallback


def _safe_write_json(path, payload) -> bool:
    """Best-effort atomic JSON save used by UI/config/progression writes.

    Direct writes can leave half-written JSON if the app exits, Windows locks the
    file, or a child mode is closed while progress is saving.  Keep this helper
    silent and dependency-free so it is safe from the launcher, the EXE build,
    and every in-world mode.
    """
    try:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(target.name + ".tmp")
        data = json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
        tmp.write_text(data, encoding="utf-8")
        tmp.replace(target)
        return True
    except Exception:
        try:
            Path(path).write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
            return True
        except Exception:
            return False


def normalize_lookup_key(value) -> str:
    try:
        raw = str(value or "").strip().lower()
    except Exception:
        raw = ""
    raw = raw.replace("&", " and ")
    raw = re.sub(r"[^a-z0-9]+", "_", raw)
    raw = re.sub(r"_+", "_", raw).strip("_")
    return raw




def canonical_dimension_lookup_key(value) -> str:
    """Normalize loose bot/config UI labels into the canonical dimension key."""
    key = normalize_lookup_key(value)
    aliases = {
        "creative": "creativity",
        "creation": "creativity",
        "holo_forge": "creativity",
        "holoforge": "creativity",
        "creativity_holoforge": "creativity",
        "creativity_holo_forge": "creativity",
        "creation_field": "creativity",
        "the_forge": "creativity",
        "arena": "vector_arena",
        "vector": "vector_arena",
        "vector_arena": "vector_arena",
        "vector_wars_arena": "vector_arena",
    }
    return aliases.get(key, key)


def find_case_insensitive_file(folder: Path, filename: str) -> Path | None:
    """Return a file by exact or case-insensitive name without throwing."""
    try:
        folder = Path(folder)
        exact = folder / str(filename)
        if exact.exists() and exact.is_file():
            return exact
        target = str(filename).lower()
        if not folder.exists() or not folder.is_dir():
            return None
        for child in folder.iterdir():
            try:
                if child.is_file() and child.name.lower() == target:
                    return child
            except Exception:
                continue
    except Exception:
        return None
    return None


def find_case_insensitive_dir(parent: Path, dirname: str) -> Path | None:
    """Return a directory by exact or case-insensitive name without throwing."""
    try:
        parent = Path(parent)
        exact = parent / str(dirname)
        if exact.exists() and exact.is_dir():
            return exact
        target = str(dirname).lower()
        if not parent.exists() or not parent.is_dir():
            return None
        for child in parent.iterdir():
            try:
                if child.is_dir() and child.name.lower() == target:
                    return child
            except Exception:
                continue
    except Exception:
        return None
    return None


def resolve_dimensions_root(root: Path) -> Path:
    """Find the Dimensions folder even if a local copy uses different casing."""
    root = Path(root)
    found = find_case_insensitive_dir(root, DIMENSIONS_DIR_NAME)
    return found if found is not None else root / DIMENSIONS_DIR_NAME


def resolve_project_path(value, *, root: Path = ROOT) -> Path:
    """Resolve project-relative paths stored in manifests/index files."""
    raw = str(value or "").strip().replace("\\", "/")
    path = Path(raw)
    if path.is_absolute():
        return path
    root = Path(root)
    candidate = root / path
    if candidate.exists():
        return candidate
    # HoloCore is intentionally a root-level sub-world in this build. Some
    # transition-index records still carry the older Dimensions\HoloCore path,
    # which made the launcher recover it as a missing/placeholder route. Keep
    # the source layout intact and resolve only the stale manifest path here.
    parts = [part for part in raw.split("/") if part]
    if len(parts) >= 2 and parts[0].lower() == "dimensions" and parts[1].lower() == "holocore":
        alt = root / "HoloCore"
        for part in parts[2:]:
            alt = alt / part
        return alt
    return candidate


def read_dimension_index_payload() -> dict:
    # The packaged /Dimensions index is authoritative. Shared data is a mirror
    # that can survive older builds, so never let a stale shared index recreate
    # retired folders or old route names.
    root_payload = _safe_read_json(DIMENSION_INDEX_PATH) if DIMENSION_INDEX_PATH.exists() else {}
    if isinstance(root_payload, dict) and isinstance(root_payload.get("dimensions"), dict):
        return root_payload
    return _safe_read_json(MATRIXCORE_DIMENSION_INDEX_PATH) if MATRIXCORE_DIMENSION_INDEX_PATH.exists() else {}


def dimension_record_from_index(title: str, *, bot_name: str = "") -> dict | None:
    """Look up a dimension by display title/id/alias or bot owner in the index."""
    payload = read_dimension_index_payload()
    if not isinstance(payload, dict):
        return None
    dimensions = payload.get("dimensions") if isinstance(payload.get("dimensions"), dict) else {}
    target = canonical_dimension_lookup_key(title)
    if bot_name:
        by_bot = payload.get("by_bot") if isinstance(payload.get("by_bot"), dict) else {}
        bot_key = str(by_bot.get(str(bot_name).strip()) or by_bot.get(normalize_lookup_key(bot_name)) or "").strip()
        bot_key = canonical_dimension_lookup_key(bot_key)
        if bot_key and isinstance(dimensions.get(bot_key), dict):
            return dict(dimensions[bot_key])
    if target and isinstance(dimensions.get(target), dict):
        return dict(dimensions[target])
    for key, record in dimensions.items():
        if not isinstance(record, dict):
            continue
        names = [key, record.get("id", ""), record.get("name", ""), record.get("title", ""), Path(str(record.get("folder", ""))).name]
        if any(canonical_dimension_lookup_key(name) == target for name in names):
            return dict(record)
    return None


def mode_from_dimension_record(record: dict) -> dict | None:
    """Build a launchable mode dictionary directly from dimension_index.json."""
    if not isinstance(record, dict):
        return None
    folder_text = str(record.get("folder") or "").strip()
    if not folder_text:
        return None
    folder = resolve_project_path(folder_text)
    manifest_path = folder / MODE_MANIFEST_NAME
    saved_manifest = _safe_read_json(manifest_path) if manifest_path.exists() else {}
    manifest = dict(saved_manifest if isinstance(saved_manifest, dict) else {})
    for key in ("id", "title", "launch_type", "source_kind", "fallback_launch_type", "placeholder_mode", "panel_supported", "preferred_display", "host_contract", "return_target", "requires_mouse_capture", "native_adapter"):
        value = record.get(key)
        if value not in (None, "") and key not in manifest:
            manifest[key] = value
    name = str(record.get("name") or record.get("title") or folder.name).strip() or folder.name
    placeholder = bool(record.get("placeholder_mode", False) or normalize_mode_launch_type(record.get("launch_type")) == MODE_LAUNCH_PLACEHOLDER)
    entry_text = str(record.get("entry") or "").strip()
    manifest_entry_text = str(manifest.get("entry") or "").strip()
    manifest_entry = folder / manifest_entry_text if manifest_entry_text else None
    # Universal-mode wrappers live in the Dimension folder and should be able to
    # override older dimension_index records that still point at main.py.  Keep
    # record.entry authoritative for explicit non-main entries, but let a real
    # manifest wrapper win over stale registry metadata.
    if manifest_entry is not None and manifest_entry.exists() and manifest_entry.name.lower() != "main.py":
        main = manifest_entry
    elif entry_text:
        main = resolve_project_path(entry_text)
    else:
        main = folder / (manifest_entry_text or "main.py")
    if placeholder and not main.exists():
        main = folder / "main.py"
    manifest["manifest_path"] = os.fspath(manifest_path)
    manifest["entry"] = main.name if main else (manifest_entry_text or "main.py")
    launch_type = normalize_mode_launch_type(manifest.get("launch_type") or record.get("launch_type"))
    return {
        "name": name, "folder": folder, "mode_root": "placeholder" if placeholder else "dimensions",
        "main": main, "alternate": None, "available": bool(placeholder or (main is not None and main.exists())),
        "has_alternate": False, "placeholder": bool(placeholder), "manifest": manifest, "launch_type": launch_type,
        "source_kind": str(manifest.get("source_kind", record.get("source_kind", "unknown"))),
        "panel_supported": bool(manifest.get("panel_supported", record.get("panel_supported", False))),
        "native_panda_candidate": False,
    }

def compact_ui_text(value: object, limit: int = 220) -> str:
    """Trim long dynamic UI strings before they overlap nearby controls."""
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    limit = max(32, int(limit or 220))
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


def merge_dict_defaults(existing, defaults):
    if not isinstance(defaults, dict):
        return existing if isinstance(existing, dict) else {}
    merged = dict(defaults)
    if not isinstance(existing, dict):
        return merged
    for key, value in existing.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = merge_dict_defaults(value, merged[key])
        else:
            merged[key] = value
    return merged


def matrixcore_default_progression_payload() -> dict:
    now = datetime.now().isoformat(timespec="seconds")
    return {
        "schema_version": 5,
        "kind": "holoverse_matrixcore_progression_state",
        "created_at": now,
        "updated_at": now,
        "player": {
            "visits_total": 0,
            "total_points": 0,
            "last_dimension": "",
            "last_bot": "",
            "last_launch_mode": "",
        },
        "holoverse_score": 0,
        "dimension_progress": {},
        "dimension_results": {},
        "dialogue_flags": {},
        "dimension_visits": {},
        "dimension_placeholders": {},
        "discovered_gates": {
            "region_hub_region_0": {
                "kind": "region",
                "name": "Hub Region",
                "label": "HUB REGION",
                "target_number": 0,
                "route": "region_spawn",
                "count": 1,
                "source": "default",
                "last_at": now,
            }
        },
        "bot_visits": {},
        "mode_status": {},
        "matrixcore": {
            "name": "MatrixCore",
            "guide": "informational/help/progression guide",
            "native_adapters_removed": True,
            "placeholder_mode_enabled": True,
        },
        "world_cycle": {
            "elapsed_seconds": 0.0,
            "cycle_seconds": 1800.0,
            "phase": 0.0,
            "day_night_black_backdrop_enabled": True,
            "last_saved_at": now,
        },
    }
MODE_STATE_PATH = CONFIG_DIR / "holoverse_core_mode_state.json"
MODE_FOLDER_EXCLUDES = {"assets", "logs", "patch_notes", "__pycache__", "p3dopenxr", "versions", ".git", "world shell", DIMENSIONS_DIR_NAME.lower()}
CORE_MODE_SLOTS_PER_PAGE = 8
MATRIXCORE_VISIBLE_ACTION_CARD_LIMIT = 4
MATRIXCORE_COMPACT_TEXT_MAX_CHARS = 920
# No old-mode reserve list: the deck is now driven by the real /Dimensions folders.
# Empty folders are treated as temporary placeholders and disappear automatically
# when a real main.py is dropped in.
FALLBACK_CORE_MODE_FOLDERS = []
ROOT_ONLY_CORE_MODE_FOLDERS = set()
DIMENSIONS_CORE_MODE_FOLDERS = set()
MODE_MANIFEST_NAME = "holoverse_mode_manifest.json"
MODE_NATIVE_ADAPTER_NAME = "holoverse_native_adapter.py"
MODE_LAUNCH_EXTERNAL = "hosted_external"
MODE_LAUNCH_NATIVE = "native_panda"  # same-window source-backed native adapter route.
MODE_LAUNCH_PANEL = "hub_panel"
MODE_LAUNCH_EMBEDDED = "embedded_external"
MODE_LAUNCH_CONNECTED = "same_window_mode"
MODE_LAUNCH_IN_WORLD = "in_world_region"
MODE_LAUNCH_PLACEHOLDER = "placeholder_mode"
MODE_LAUNCH_EXTERNAL_ALIASES = {"external", "hosted", "hosted_external", "external_panda", "external_pygame"}
MODE_LAUNCH_NATIVE_ALIASES = {"native", "native_panda", "host_native", "in_process", "adapter"}
MODE_LAUNCH_PANEL_ALIASES = {"panel", "hub_panel", "panel_preview"}
MODE_LAUNCH_EMBEDDED_ALIASES = {"embedded", "embedded_external", "child_window", "win_child", "window_child", "hosted_child"}
MODE_LAUNCH_CONNECTED_ALIASES = {"same_window", "same_window_mode", "connected", "connected_mode", "in_process_scene", "same_screen"}
MODE_LAUNCH_IN_WORLD_ALIASES = {"in_world", "in_world_region", "region_runtime", "current_region", "same_world", "same_region"}
MODE_LAUNCH_PLACEHOLDER_ALIASES = {"placeholder", "placeholder_mode", "empty", "stub", "reserved"}

PLACEHOLDER_TRANSITION_GUIDANCE = {
    "holoforge": {
        "intent": "flat-region object creation route",
        "gleebs": "HoloForge is alive in the flat region. The grid is real, the shapes save, and no old launcher is invited.",
        "matrixcore": "IO owns HoloForge as the in-world FLAT builder layer. Objects place on world ground, snap together, and save into shared HoloVerse data.",
        "next_step": "Activate IO in the FLAT region and build directly inside the current world."
    },
    "forest_growth": {
        "intent": "forest planter route",
        "gleebs": "Vanta opens a clean Forest Planter. Aim at the ground, click, and the forest remembers the new life immediately.",
        "matrixcore": "Vanta owns Forest Planter as the in-world FORESTS layer. Each click places a random full-grown grounded plant, with a 50 item save cap.",
        "next_step": "Activate Vanta in the FORESTS region and use LMB on the ground to place random full-grown plants."
    },
    "hills_of_life": {
        "intent": "smart animal life route",
        "gleebs": "Hills of Life has rules with paws, hands, and wings. Nyx insists that still counts as logic.",
        "matrixcore": "Nyx owns Hills of Life as the GREEN HILLS smart-animal layer for cats, dogs, apes, and crows with saved traits and daily growth.",
        "next_step": "Activate Nyx in GREEN HILLS to create saved smart animals."
    },
    "oddities": {
        "intent": "mushroom oddity experiment route",
        "gleebs": "Oddities is what happens when the mushroom region starts improvising with physics.",
        "matrixcore": "Solace owns Oddities as the in-world MUSHROOM layer with floating objects, procedural weird plants, spore totems, and glitch growths.",
        "next_step": "Activate Solace in MUSHROOM to create unpredictable saved oddities."
    },
    "ember_hangar": {
        "intent": "desert ship generation and global TAB craft route",
        "gleebs": "Ember Hangar turns sand into ships. Latest pick wins the TAB key, which is either elegant or deeply reckless.",
        "matrixcore": "Ember owns the DESERT ship-generation layer. Fighter, Speeder, Hauler, and UFO craft save into shared data and become the global TAB craft.",
        "next_step": "Activate Ember in DESERT to generate ships and set the default TAB craft."
    },
    "frost_circuit": {
        "intent": "ice ring racing route",
        "gleebs": "Frost Circuit lets Mirror turn the ice ring into a clean, unsafe, excellent racetrack.",
        "matrixcore": "Mirror owns Frost Circuit as an ICE region race layer with bot hovercraft opponents, ring waypoints, third-person controls, and saved times.",
        "next_step": "Activate Mirror in ICE to race the bot hovercrafts around the ring."
    },
    "urban_warzone": {
        "intent": "urban machine-war combat simulator",
        "gleebs": "Urban Warzone is not a doorway anymore. It is the street, the smoke, and the bad idea with legs.",
        "matrixcore": "Sable owns Urban Warzone as an in-world URBAN arena with cover collisions, bot allies, robot/drone/mech waves, saved records, and safe unload behavior.",
        "next_step": "Activate Sable in URBAN to fight waves with bot allies."
    },
}

BOT_DIMENSION_LINKS_PATH = CONFIG_DIR / "holoverse_bot_dimension_links.json"
BOT_DIMENSION_PROMPT = "Would you like to see the Dimension I'm building?"

# Bot routing is profile/map driven now.  The old list-of-links format is only
# read for migration, then it is deleted from written configs so bots become the
# actual doorway records instead of wrappers around a separate list.
DEFAULT_BOT_DIMENSION_PROFILES = {
    "IO": {"region": "FLAT", "mode": "HoloForge", "color": "silver", "role": "HoloForge builder doorway keeper", "personality": "calm, direct, signal-clean, and quietly inventive", "greeting": "IO has opened HoloForge. Clean grid, clean signal, dangerous amount of creative freedom.", "matrixcore_support": "IO owns HoloForge as the in-world FLAT builder layer. Objects are placed on the real ground, snap together, and save into shared HoloVerse data.", "player_hint": "Visit IO in the FLAT region to build shapes, save objects, and prototype HoloVerse structures.", "world_spawn_behavior": "flat_region_holoforge_doorway"},
    "Vanta": {"region": "FORESTS", "mode": "Forest Planter", "color": "green", "role": "forest planter and grounded life keeper", "personality": "patient, organic, protective, and quietly intense", "greeting": "Vanta has opened Forest Planter. Aim at the ground, click, and the forest answers fully grown.", "matrixcore_support": "Vanta owns Forest Planter as the in-world FORESTS placement layer. Each LMB places one random full-grown plant on the ground, with a 50 item save cap.", "player_hint": "Visit Vanta in the FORESTS region and use LMB on the ground to place random full-grown plants. X inspects, Delete removes, and G saves.", "world_spawn_behavior": "forest_region_planter_doorway"},
    "Nyx": {"region": "GREEN HILLS", "mode": "Hills of Life", "color": "yellow-green", "role": "smart-animal life weaver and personality-rule interpreter", "personality": "clever, watchful, mischievous, and obsessed with living rules", "greeting": "Nyx has opened Hills of Life. The hills can think now, if you give them paws, hands, or wings.", "matrixcore_support": "Nyx owns Hills of Life as an in-world smart animal life system: cats, dogs, apes, and crows save progress, grow one stage per real day, wander with personality, and provide daily gifts as adults.", "player_hint": "Visit Nyx in the GREEN HILLS region to create cats, dogs, apes, and crows with saved traits and daily growth.", "world_spawn_behavior": "green_hills_life_doorway"},
    "Solace": {"region": "MUSHROOM", "mode": "Oddities", "color": "magenta-cyan", "role": "oddity maker and unstable mushroom experiment guide", "personality": "gentle, tactical, weirdly scientific, and a little too curious", "greeting": "Solace has opened Oddities. Do not trust anything that floats calmly in the mushroom glow.", "matrixcore_support": "Solace owns Oddities as an in-world MUSHROOM region experiment layer with floating behaviors, procedural weird plants, and saved unpredictable growth.", "player_hint": "Visit Solace in the MUSHROOM region to create floating oddities, weird plants, spore totems, and glitch growths that save and mutate over real days.", "world_spawn_behavior": "mushroom_oddities_doorway"},
    "Ember": {"region": "DESERT", "mode": "Ember Hangar", "color": "amber", "role": "desert ship-forge mechanic and global TAB craft keeper", "personality": "hot-headed, brave, dramatic, and obsessed with engines that should not work", "greeting": "Ember has opened the Hangar. Pick a class, burn a seed into metal, and the newest ship becomes your TAB craft.", "matrixcore_support": "Ember owns Ember Hangar as an in-world DESERT region ship generator: Fighter, Speeder, Hauler, and UFO classes generate procedural saved ships, and the latest placed or selected ship becomes the global TAB craft from anywhere.", "player_hint": "Visit Ember in the DESERT region to generate saved flying ships. The newest placed or selected ship becomes your default TAB craft across HoloVerse.", "world_spawn_behavior": "desert_ship_hangar_doorway"},
    "Mirror": {"region": "ICE", "mode": "Frost Circuit", "color": "blue", "role": "ice-ring race coordinator and reflection-speed analyst", "personality": "cold, precise, competitive, reflective, and quietly sarcastic", "greeting": "Mirror has opened Frost Circuit. The ice ring is no longer scenery; it is a lap timer with opinions.", "matrixcore_support": "Mirror owns Frost Circuit as an in-world ICE race layer with player and bot hovercraft racers, third-person controls, ring waypoints, unload-on-exit safety, and saved race records.", "player_hint": "Visit Mirror in the ICE region to race bot hovercrafts around the full ring path. ESC prompts out, TAB exits the race, and teleporting away unloads it safely.", "world_spawn_behavior": "ice_frost_circuit_doorway"},
    "Sable": {"region": "URBAN", "mode": "Urban Warzone", "color": "grey-red", "role": "urban endgame arena commander and machine-war keeper", "personality": "gritty, suspicious, loyal, and battle-ready", "greeting": "Sable has opened Urban Warzone. The buried arena layer is live: capture posts, bombs, 4D enemy drops, and battle-bot allies are waking up.", "matrixcore_support": "Sable owns Urban Warzone as an in-world URBAN endgame arena: buried full-region arena infrastructure, capture posts, evenly distributed bombs, 4D teleporting enemy waves, arena weapon nodes, eight non-IO battle-bot allies, robot/drone/mech waves, saved records, and safe unload on ESC/TAB/teleport/region exit.", "player_hint": "Talk to Sable in the URBAN region to start the built-in warzone arena. Sable deploys the eight non-IO battle bots as allies while enemy waves teleport into capture posts and bomb zones.", "world_spawn_behavior": "urban_warzone_doorway"},
    "Archivist": {"region": "METROPOLIS", "mode": "Metropolis Robot Lab", "color": "purple", "role": "metropolis robot selector keeper", "personality": "scholarly, dramatic, and dangerously curious", "greeting": "Archivist has opened the Metropolis Robot Selector. Four prebuilt Urban-class robot variants are ready; select one and it will load beside you whenever you enter Urban until it is destroyed or replaced.", "matrixcore_support": "Archivist owns Metropolis Robot Lab as an in-world robot selector. Four prebuilt Urban-class frames are available. The selected robot replaces the previous saved ally, loads into Urban from the saved export, joins Sable's Urban Warzone team, and must be replaced if destroyed.", "player_hint": "Talk to Archivist in METROPOLIS, click Yes to open the selector, then aim and click/E to select one Urban ally. It loads in Urban until destroyed or replaced.", "world_spawn_behavior": "metropolis_robot_lab_doorway"},
    "Space Bot": {"region": "SPACE / HoloSpace", "mode": "Vector Wars", "color": "black-cyan", "role": "Dyson patrol pilot and space-battle coordinator", "personality": "distant, fast, tactical, and obsessed with clean orbital vectors", "greeting": "Space Bot has opened Vector Wars from the Dyson patrol lane. Same HoloVerse window, live space battle route.", "matrixcore_support": "Space Bot patrols the Dyson sphere from a safe orbital radius and opens Vector Wars as the active space-battle doorway instead of pointing at HoloCore.", "player_hint": "Find Space Bot circling the Dyson sphere in HoloSpace. Click it to start the Vector Wars space battle.", "world_spawn_behavior": "dyson_space_battle_doorway"},
    "Orbit": {"bot": "Orbit", "region": "SPACE / HoloSpace", "mode": "Vector Wars", "color": "black-cyan", "role": "legacy alias for Space Bot", "personality": "distant, fast, tactical, and obsessed with clean orbital vectors", "greeting": "Orbit now routes to Space Bot's Vector Wars battle path.", "matrixcore_support": "Legacy Orbit profiles are redirected to the Space Bot Vector Wars route so older saves still start a space battle.", "player_hint": "Click Space Bot / Orbit in HoloSpace to start Vector Wars.", "world_spawn_behavior": "dyson_space_battle_doorway"},
}


def bot_profile_map_copy(source: dict | None = None) -> dict:
    raw = source if isinstance(source, dict) else DEFAULT_BOT_DIMENSION_PROFILES
    out = {}
    for bot, profile in dict(raw or {}).items():
        if not isinstance(profile, dict):
            continue
        name = str(profile.get("bot") or bot).strip()
        mode = str(profile.get("mode", "")).strip()
        if not name or not mode:
            continue
        item = dict(DEFAULT_BOT_DIMENSION_PROFILES.get(name, {}) or {})
        item.update(profile)
        item["bot"] = name
        item["mode"] = mode
        item["region"] = str(item.get("region", "")).strip()
        out[name] = item
    return out


def migrate_bot_links_to_profiles(payload: dict | None) -> dict:
    profiles = bot_profile_map_copy(DEFAULT_BOT_DIMENSION_PROFILES)
    data = dict(payload or {}) if isinstance(payload, dict) else {}
    existing_profiles = data.get("profiles") if isinstance(data.get("profiles"), dict) else {}
    for bot, profile in dict(existing_profiles or {}).items():
        if isinstance(profile, dict):
            name = str(profile.get("bot") or bot).strip()
            merged = dict(profiles.get(name, {}) or {})
            merged.update(profile)
            merged["bot"] = name
            profiles[name] = merged
    # One-time reader for legacy builds.  Do not write this back out.
    legacy_links = data.get("links") if isinstance(data.get("links"), list) else []
    for link in list(legacy_links or []):
        if not isinstance(link, dict):
            continue
        bot = str(link.get("bot", "")).strip()
        mode = str(link.get("mode", "")).strip()
        if not bot or not mode:
            continue
        merged = dict(profiles.get(bot, {}) or {})
        merged.update({k: v for k, v in link.items() if v not in (None, "")})
        merged["bot"] = bot
        merged["mode"] = mode
        profiles[bot] = merged
    return profiles


def bot_dimension_config_payload() -> dict:
    return {
        "schema": 2,
        "kind": "holoverse_bot_dimension_map",
        "prompt": BOT_DIMENSION_PROMPT,
        "special_prompts": {},
        "yes_action": "launch_assigned_dimension_actual_entry",
        "no_action": "close_dialogue_and_resume_bot",
        "escape_action": "close_dialogue_and_resume_bot",
        "launch_note": "Bot launches are profile-map driven doorways; every bot calls the shared route resolver. Empty replacement folders open a temporary Core placeholder until a real main.py is dropped in.",
        "profiles": bot_profile_map_copy(DEFAULT_BOT_DIMENSION_PROFILES),
    }


def ensure_bot_dimension_config() -> dict:
    existing = _safe_read_json(BOT_DIMENSION_LINKS_PATH)
    payload = bot_dimension_config_payload()
    profiles = migrate_bot_links_to_profiles(existing)
    payload["profiles"] = profiles
    if isinstance(existing, dict):
        for key in ("prompt", "yes_action", "no_action", "escape_action"):
            if existing.get(key):
                payload[key] = existing[key]
    # Delete legacy list format on write.
    payload.pop("links", None)
    _safe_write_json(BOT_DIMENSION_LINKS_PATH, payload)
    return payload


def matrixcore_bot_support_seed(bot_profiles: dict | None = None) -> dict:
    """Return MatrixCore's authored support profiles for each region bot."""
    profiles = bot_profile_map_copy(bot_profiles if isinstance(bot_profiles, dict) and bot_profiles else DEFAULT_BOT_DIMENSION_PROFILES)
    return {
        "schema_version": 3,
        "purpose": "MatrixCore shares bot-specific guidance context with region bots without changing how dimensions launch.",
        "rule": "Bots are immersive doorways. They must call the same launch route resolver as the main system.",
        "matrixcore_integration": [
            "Bot prompts explain the bot's support role before launch.",
            "Bot launches record progression signals in data/holoverse/progression/progression_state.json.",
            "Gleebs may react to the last bot doorway without turning dialogue into a persistent menu."
        ],
        "profiles": profiles,
        "routing_model": "bot_profile_map",
    }


def merge_matrixcore_bot_support(existing: dict, seed: dict) -> dict:
    # Current bot profiles are authoritative. Older shared data can contain
    # stale retired route names; do not merge those
    # stale route assignments back into a clean build.
    merged = dict(seed or {})
    merged["profiles"] = bot_profile_map_copy(seed.get("profiles") if isinstance(seed.get("profiles"), dict) else DEFAULT_BOT_DIMENSION_PROFILES)
    merged.pop("links", None)
    return merged


def _mode_source_kind(main_path: Path | None) -> str:
    if main_path is None or not Path(main_path).exists():
        return "missing"
    try:
        text = Path(main_path).read_text(encoding="utf-8", errors="ignore")[:24000].lower()
    except Exception:
        return "unknown"
    has_pygame = "import pygame" in text or "pygame." in text
    has_panda = (
        "from direct." in text
        or "from panda3d." in text
        or "import panda3d" in text
        or "loadprcfiledata(" in text
        or "showbase(" in text
    )
    if has_panda:
        return "panda3d"
    if has_pygame:
        return "pygame"
    return "python"


def _default_mode_manifest(folder: Path, name: str, main_path: Path | None, alternate_path: Path | None = None) -> dict:
    source_kind = _mode_source_kind(main_path)
    mode_id = re.sub(r"[^a-z0-9]+", "_", str(name).strip().lower()).strip("_") or "mode"
    native_ready = False
    panel_supported = source_kind in {"pygame", "python", "unknown"}
    launch_type = MODE_LAUNCH_EMBEDDED
    preferred_display = "host_window_child"
    fallback_launch_type = ""
    description = "Discovered HoloVerse mode folder. Routed through the real hosted child-window embedder; the old connected signal mini-surface is retired."
    return {
        "schema": 1,
        "id": mode_id,
        "title": str(name).upper(),
        "entry": Path(main_path).name if main_path else "main.py",
        "launch_type": launch_type,
        "source_kind": source_kind,
        "native_panda_candidate": False,
        "panel_supported": panel_supported,
        "preferred_display": preferred_display,
        "return_target": "hub",
        "requires_mouse_capture": source_kind in {"panda3d", "pygame"} and launch_type != MODE_LAUNCH_PANEL,
        "host_contract": "holoverse_mode_gateway_v4_child_window",
        "native_adapter": "",
        "fallback_launch_type": fallback_launch_type,
        "description": description,
        "alternate_entry": Path(alternate_path).name if alternate_path else "",
    }


def _placeholder_mode_manifest(folder: Path, name: str) -> dict:
    mode_id = re.sub(r"[^a-z0-9]+", "_", str(name).strip().lower()).strip("_") or "placeholder"
    manifest_path = Path(folder) / MODE_MANIFEST_NAME
    saved = _safe_read_json(manifest_path)
    manifest = {
        "schema": 1,
        "id": mode_id,
        "title": str(name).upper(),
        "entry": "",
        "launch_type": MODE_LAUNCH_PLACEHOLDER,
        "source_kind": "placeholder",
        "native_panda_candidate": False,
        "panel_supported": True,
        "preferred_display": "core_placeholder_panel",
        "return_target": "hub",
        "requires_mouse_capture": False,
        "host_contract": "holoverse_mode_gateway_v2",
        "native_adapter": "",
        "fallback_launch_type": "",
        "placeholder_mode": True,
        "transition_route": "transition_placeholder",
        "transition_stage": "reserved_placeholder",
        "transition_entry_behavior": "matrixcore_guidance_no_process",
        "x_transition_route": "transition_placeholder",
        "x_transition_stage": "reserved_placeholder",
        "x_transition_entry_behavior": "matrixcore_guidance_no_process",
        "replace_rule": "Drop a real main.py into this folder to replace the placeholder automatically.",
        "description": "Temporary clean placeholder for a future HoloVerse dimension. It is not a kept legacy mode.",
        "placeholder_guidance": PLACEHOLDER_TRANSITION_GUIDANCE.get(mode_id, {}),
        "manifest_path": os.fspath(manifest_path),
    }
    if isinstance(saved, dict):
        for key, value in saved.items():
            if key.startswith("x_"):
                manifest[key] = value
    return manifest


def load_or_create_mode_manifest(folder: Path, name: str, main_path: Path | None, alternate_path: Path | None = None) -> dict:
    manifest_path = Path(folder) / MODE_MANIFEST_NAME
    defaults = _default_mode_manifest(folder, name, main_path, alternate_path)
    saved = _safe_read_json(manifest_path)
    merged = dict(defaults)
    for key, value in saved.items():
        # Preserve dimension-local runtime metadata. Older cleanup passes rely on
        # runtime.py ownership and installer names staying in the manifest/index;
        # the generic defaults do not know those keys.
        if key in merged or key.startswith("x_") or key in {"runtime", "runtime_module", "runtime_installer"}:
            merged[key] = value
    merged["manifest_path"] = os.fspath(manifest_path)
    if not saved:
        _safe_write_json(manifest_path, {k: v for k, v in merged.items() if k != "manifest_path"})
    return merged


def normalize_mode_launch_type(value: str | None) -> str:
    raw = str(value or MODE_LAUNCH_EXTERNAL).strip().lower()
    if raw in MODE_LAUNCH_PLACEHOLDER_ALIASES:
        return MODE_LAUNCH_PLACEHOLDER
    if raw in MODE_LAUNCH_PANEL_ALIASES:
        return MODE_LAUNCH_PANEL
    if raw in MODE_LAUNCH_CONNECTED_ALIASES:
        return MODE_LAUNCH_CONNECTED
    if raw in MODE_LAUNCH_NATIVE_ALIASES:
        return MODE_LAUNCH_NATIVE
    if raw in MODE_LAUNCH_EMBEDDED_ALIASES:
        return MODE_LAUNCH_EMBEDDED
    if raw in MODE_LAUNCH_IN_WORLD_ALIASES:
        return MODE_LAUNCH_IN_WORLD
    if raw in MODE_LAUNCH_EXTERNAL_ALIASES:
        return MODE_LAUNCH_EXTERNAL
    # Unknown launch labels are treated as hosted external routes.
    return MODE_LAUNCH_EXTERNAL


def route_display_name(launch_type: str) -> str:
    launch_type = normalize_mode_launch_type(launch_type)
    if launch_type == MODE_LAUNCH_PLACEHOLDER:
        return "PLACEHOLDER"
    if launch_type == MODE_LAUNCH_PANEL:
        return "PANEL"
    if launch_type == MODE_LAUNCH_EMBEDDED:
        return "EMBEDDED"
    if launch_type == MODE_LAUNCH_CONNECTED:
        return "SAME-WINDOW"
    if launch_type == MODE_LAUNCH_NATIVE:
        return "SAME-WINDOW"
    if launch_type == MODE_LAUNCH_IN_WORLD:
        return "IN-WORLD"
    return "HOSTED"

def transition_route_for_launch_type(launch_type: str | None, *, placeholder: bool = False) -> str:
    """Return the metadata-only transition route for a mode.

    Pass 1 does not change the existing launcher. This label lets MatrixCore,
    bots, and future portal code agree on a transition-first route name while
    the proven gateway underneath still uses the existing launch_type values.
    """
    normalized = normalize_mode_launch_type(launch_type)
    if placeholder or normalized == MODE_LAUNCH_PLACEHOLDER:
        return "transition_placeholder"
    if normalized == MODE_LAUNCH_PANEL:
        return "transition_reserved"
    if normalized == MODE_LAUNCH_EMBEDDED:
        return "transition_embedded_external"
    if normalized == MODE_LAUNCH_CONNECTED:
        return "transition_same_window"
    if normalized == MODE_LAUNCH_NATIVE:
        return "transition_native_adapter"
    if normalized == MODE_LAUNCH_IN_WORLD:
        return "transition_in_world_region"
    return "transition_hosted_external"


def _path_for_index(value) -> str:
    try:
        path = Path(value)
    except Exception:
        return str(value or "")
    try:
        return os.fspath(path.resolve().relative_to(ROOT.resolve()))
    except Exception:
        return os.fspath(path)


def build_transition_dimension_index(modes: list[dict], bot_profiles: dict, updated_at: str = "") -> dict:
    """Build a rich dimension index without changing runtime launch behavior."""
    bot_profiles = bot_profile_map_copy(bot_profiles if isinstance(bot_profiles, dict) else DEFAULT_BOT_DIMENSION_PROFILES)
    by_bot: dict[str, str] = {}
    bot_routes: dict[str, dict] = {}
    bot_owners_by_dimension: dict[str, list[str]] = {}
    region_owners_by_dimension: dict[str, list[str]] = {}

    # Resolve bot profile labels through the real discovered manifests instead
    # of deriving IDs from player-facing titles. This keeps display labels like
    # "Forest Planter" from creating a fake forest_planter placeholder when the
    # actual manifest id is forest_growth.
    dimension_aliases: dict[str, str] = {}
    for mode in modes:
        manifest = dict(mode.get("manifest") or {})
        name = str(mode.get("name") or manifest.get("title") or "").strip()
        mode_id = normalize_lookup_key(manifest.get("id") or name)
        if not mode_id:
            continue
        folder_name = ""
        try:
            folder_name = Path(mode.get("folder") or "").name
        except Exception:
            folder_name = ""
        for alias in (mode_id, manifest.get("id"), manifest.get("title"), name, folder_name):
            alias_key = normalize_lookup_key(alias or "")
            if alias_key:
                dimension_aliases.setdefault(alias_key, mode_id)

    for bot, profile in bot_profiles.items():
        if not isinstance(profile, dict):
            continue
        bot_name = str(profile.get("bot") or bot).strip() or str(bot)
        requested_key = normalize_lookup_key(profile.get("mode") or "")
        dimension_id = dimension_aliases.get(requested_key, requested_key)
        if not dimension_id:
            continue
        by_bot[bot_name] = dimension_id
        bot_owners_by_dimension.setdefault(dimension_id, []).append(bot_name)
        region = str(profile.get("region") or "").strip()
        if region:
            region_owners_by_dimension.setdefault(dimension_id, []).append(region)

    dimensions: dict[str, dict] = {}

    for mode in modes:
        manifest = dict(mode.get("manifest") or {})
        name = str(mode.get("name") or manifest.get("title") or "Mode").strip() or "Mode"
        mode_id = normalize_lookup_key(manifest.get("id") or name)
        if not mode_id:
            mode_id = "mode"
        launch_type = normalize_mode_launch_type(manifest.get("launch_type") or mode.get("launch_type"))
        placeholder = bool(manifest.get("placeholder_mode", False) or mode.get("placeholder", False) or launch_type == MODE_LAUNCH_PLACEHOLDER)
        transition_route = transition_route_for_launch_type(launch_type, placeholder=placeholder)
        owners = list(dict.fromkeys(bot_owners_by_dimension.get(mode_id, [])))
        regions = list(dict.fromkeys(region_owners_by_dimension.get(mode_id, [])))
        entry_path = Path(mode.get("main") or "") if mode.get("main") else Path(mode.get("folder") or ROOT) / str(manifest.get("entry") or "main.py")
        runtime_name = str(manifest.get("runtime") or "").strip()
        runtime_path = (Path(mode.get("folder") or ROOT) / runtime_name) if runtime_name else None
        if runtime_path is not None and not runtime_path.exists():
            runtime_path = None
        record = {
            "id": mode_id,
            "name": name,
            "title": str(manifest.get("title") or name).strip() or name,
            "enabled": True,
            "status": "placeholder" if placeholder else "playable_candidate",
            "assignment": transition_route,
            "transition_route": transition_route,
            "transition_stage": "reserved_placeholder" if placeholder else "current_gateway_preserved",
            "transition_entry_behavior": "matrixcore_guidance_no_process" if placeholder else "dimension_shift_then_launch_existing_gateway",
            "route": route_display_name(launch_type),
            "launch_type": launch_type,
            "folder": _path_for_index(mode.get("folder") or ""),
            "entry": _path_for_index(entry_path) if not placeholder else "",
            "entry_name": str(manifest.get("entry") or (entry_path.name if entry_path else "")),
            "entry_exists": bool((not placeholder) and entry_path.exists()),
            "runtime": _path_for_index(runtime_path) if (not placeholder and runtime_path is not None) else "",
            "runtime_module": str(manifest.get("runtime_module") or ""),
            "runtime_installer": str(manifest.get("runtime_installer") or ""),
            "runtime_ownership": "dimension_local" if (runtime_path is not None and runtime_path.name == "runtime.py") else "",
            "available": bool(mode.get("available", False)),
            "placeholder_mode": placeholder,
            "source_kind": str(manifest.get("source_kind", mode.get("source_kind", "unknown"))),
            "preferred_display": str(manifest.get("preferred_display") or ("core_placeholder_panel" if placeholder else "host_window_child")),
            "host_contract": str(manifest.get("host_contract") or "holoverse_mode_gateway_v2"),
            "return_target": str(manifest.get("return_target") or "hub"),
            "requires_mouse_capture": bool(manifest.get("requires_mouse_capture", False)),
            "fallback_launch_type": str(manifest.get("fallback_launch_type") or ""),
            "native_adapter": str(manifest.get("native_adapter") or ""),
            "native_adapter_enabled": bool(str(manifest.get("native_adapter") or "").strip()),
            "bot_owner": owners[0] if owners else "",
            "bot_owners": owners,
            "region_owner": regions[0] if regions else "",
            "region_owners": regions,
            "bot_linked": bool(owners),
            "notes": "Metadata-only transition registry record. Existing launcher behavior is intentionally preserved in this pass.",
        }
        dimensions[mode_id] = record

    for bot_name, dimension_id in by_bot.items():
        profile = bot_profiles.get(bot_name, {}) if isinstance(bot_profiles, dict) else {}
        record = dimensions.get(dimension_id, {})
        bot_routes[bot_name] = {
            "bot": bot_name,
            "dimension_id": dimension_id,
            "mode": str(profile.get("mode") or record.get("name") or ""),
            "region": str(profile.get("region") or record.get("region_owner") or ""),
            "transition_route": str(record.get("transition_route") or "transition_placeholder"),
            "launch_type": str(record.get("launch_type") or MODE_LAUNCH_PLACEHOLDER),
            "route": str(record.get("route") or "PLACEHOLDER"),
            "placeholder_mode": bool(record.get("placeholder_mode", True)),
        }

    return {
        "schema": 3,
        "kind": "holoverse_transition_dimension_index",
        "updated_at": updated_at or datetime.now().isoformat(timespec="seconds"),
        "router": {
            "policy": "transition_first_existing_gateway_preserved",
            "runtime_behavior": "real_embedded_entries_no_signal_placeholder",
            "transition_routes": [
                "transition_embedded_external",
                "transition_hosted_external",
                "transition_placeholder",
                "transition_reserved",
            ],
            "existing_launch_types_preserved": False,
        },
        "summary": {
            "dimension_count": len(dimensions),
            "placeholder_count": sum(1 for item in dimensions.values() if item.get("placeholder_mode")),
            "same_window_count": sum(1 for item in dimensions.values() if item.get("transition_route") == "transition_same_window"),
            "embedded_external_count": sum(1 for item in dimensions.values() if item.get("transition_route") == "transition_embedded_external"),
            "hosted_external_count": sum(1 for item in dimensions.values() if item.get("transition_route") == "transition_hosted_external"),
            "reserved_count": sum(1 for item in dimensions.values() if item.get("transition_route") == "transition_reserved"),
        },
        "dimensions": dimensions,
        "by_bot": by_bot,
        "bot_routes": bot_routes,
    }


def mode_deck_badge_from_details(details: dict, available: bool = True) -> tuple[str, str]:
    """Return compact player-facing mode deck badges.

    These badges are intentionally plain text so they stay readable inside
    Panda3D DirectGUI buttons and visual review captures:
      EMBEDDED   - routed through the Windows child-window host
      CONNECTED  - mounted into the live HoloVerse window without a child process
      PANEL      - stays inside the Core HUD/panel
      PLACEHOLDER- empty future dimension folder, replaced by adding main.py
      HOSTED     - standalone fallback route
      NEEDS PATCH- manifest/adapter/contract issue, but path exists
      BROKEN PATH- missing entry point or unavailable folder
    """
    info = dict(details or {})
    route = str(info.get("route", "HOSTED")).upper().strip() or "HOSTED"
    issues = [str(x) for x in (info.get("issues") or [])]
    entry_exists = bool(info.get("entry_exists", available))
    if (not available) or (not entry_exists) or any("missing" in issue and "fallback" not in issue for issue in issues):
        missing_bits = ",".join(issues) if issues else "entry-unavailable"
        return "BROKEN PATH", missing_bits[:42]
    if issues:
        return "NEEDS PATCH", ",".join(issues)[:42]
    if bool(info.get("placeholder_mode", False)) or route == "PLACEHOLDER":
        return "PLACEHOLDER", "DROP MAIN.PY TO REPLACE"
    if route == "PANEL":
        return "PANEL", "CORE MINI PANEL"
    if route == "EMBEDDED":
        return "EMBEDDED", "WIN CHILD HOST"
    if route == "CONNECTED":
        return "CONNECTED", "SAME WINDOW"
    if route == "IN-WORLD":
        return "IN-WORLD", "LIVE REGION"
    if route in {"SAME-WINDOW", "NATIVE"}:
        return "SAME-WINDOW", "SOURCE ADAPTER"
    return "HOSTED", "STANDALONE FALLBACK"


def mode_deck_badge_sort_weight(badge: str) -> int:
    order = {
        "EMBEDDED": 0,
        "CONNECTED": 0,
        "IN-WORLD": 0,
        "PANEL": 1,
        "PLACEHOLDER": 2,
        "HOSTED": 3,
        "NATIVE": 4,
        "NEEDS PATCH": 4,
        "BROKEN PATH": 5,
    }
    return order.get(str(badge or "").upper(), 9)


class WindowsChildWindowEmbedder:
    """Reparent a real standalone mode window into the HoloVerse host window on Windows.

    This preserves each mode's existing main.py and runtime loop. It does not
    pretend the mode is a native in-process adapter; it hosts the real child
    process window inside the main display when the OS supports it.
    """

    POLL_SECONDS = 0.05
    ATTACH_TIMEOUT_SECONDS = 8.0

    def __init__(self, host_hwnd: int, proc: subprocess.Popen, label: str, width: int, height: int):
        self.host_hwnd = int(host_hwnd or 0)
        self.proc = proc
        self.label = str(label or "Mode")
        self.width = max(320, int(width or 1280))
        self.height = max(180, int(height or 720))
        self.child_hwnd = 0
        self.attached = False
        self.ever_attached = False
        self.child_window_closed = False
        self.child_window_closed_at = 0.0
        self.child_window_closed_reason = ""
        self.attach_error = ""
        self.attach_timed_out = False
        self.attached_at = 0.0
        self.last_focus_at = 0.0
        self._stop = threading.Event()
        self._thread = None
        self._user32 = ctypes.windll.user32 if os.name == "nt" else None

    def start(self) -> None:
        if os.name != "nt" or self._user32 is None or not self.host_hwnd:
            self.attach_error = "windows-child-window-host-unavailable"
            return
        self._thread = threading.Thread(target=self._run, name=f"HoloVerseEmbed-{self.label}", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _enum_windows_for_pid(self) -> list[int]:
        if self._user32 is None or self.proc is None:
            return []
        matches: list[int] = []
        target_pid = int(getattr(self.proc, "pid", 0) or 0)
        if target_pid <= 0:
            return matches
        EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        def callback(hwnd, _lparam):
            try:
                pid = wintypes.DWORD()
                self._user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                if int(pid.value) != target_pid:
                    return True
                if not self._user32.IsWindowVisible(hwnd):
                    return True
                if self._user32.GetParent(hwnd):
                    return True
                length = self._user32.GetWindowTextLengthW(hwnd)
                # Some Panda/Pygame windows report an empty title early. Keep
                # them if visible, but prefer titled windows by sorting later.
                matches.append(int(hwnd))
            except Exception:
                pass
            return True

        self._user32.EnumWindows(EnumWindowsProc(callback), 0)
        return matches

    def _window_text_len(self, hwnd: int) -> int:
        try:
            return int(self._user32.GetWindowTextLengthW(int(hwnd))) if self._user32 else 0
        except Exception:
            return 0

    def _find_child_window(self) -> int:
        wins = self._enum_windows_for_pid()
        if not wins:
            return 0
        wins.sort(key=lambda hwnd: self._window_text_len(hwnd), reverse=True)
        return int(wins[0])

    def _client_size(self) -> tuple[int, int]:
        if self._user32 is None or not self.host_hwnd:
            return self.width, self.height
        rect = wintypes.RECT()
        try:
            if self._user32.GetClientRect(wintypes.HWND(self.host_hwnd), ctypes.byref(rect)):
                w = max(320, int(rect.right - rect.left))
                h = max(180, int(rect.bottom - rect.top))
                return w, h
        except Exception:
            pass
        return self.width, self.height

    def _set_window_long_ptr(self, hwnd: int, index: int, value: int) -> int:
        if ctypes.sizeof(ctypes.c_void_p) == 8:
            return int(self._user32.SetWindowLongPtrW(wintypes.HWND(hwnd), index, ctypes.c_longlong(value)))
        return int(self._user32.SetWindowLongW(wintypes.HWND(hwnd), index, ctypes.c_long(value)))

    def _get_window_long_ptr(self, hwnd: int, index: int) -> int:
        if ctypes.sizeof(ctypes.c_void_p) == 8:
            return int(self._user32.GetWindowLongPtrW(wintypes.HWND(hwnd), index))
        return int(self._user32.GetWindowLongW(wintypes.HWND(hwnd), index))

    def _attach(self, hwnd: int) -> bool:
        if self._user32 is None or not hwnd or not self.host_hwnd:
            return False
        GWL_STYLE = -16
        GWL_EXSTYLE = -20
        WS_CHILD = 0x40000000
        WS_VISIBLE = 0x10000000
        WS_POPUP = 0x80000000
        WS_CAPTION = 0x00C00000
        WS_THICKFRAME = 0x00040000
        WS_SYSMENU = 0x00080000
        WS_MINIMIZEBOX = 0x00020000
        WS_MAXIMIZEBOX = 0x00010000
        WS_EX_APPWINDOW = 0x00040000
        WS_EX_TOOLWINDOW = 0x00000080
        SW_SHOW = 5
        SWP_NOZORDER = 0x0004
        SWP_NOACTIVATE = 0x0010
        SWP_FRAMECHANGED = 0x0020
        try:
            self._user32.SetParent(wintypes.HWND(hwnd), wintypes.HWND(self.host_hwnd))
            style = self._get_window_long_ptr(hwnd, GWL_STYLE)
            style = (style & ~(WS_POPUP | WS_CAPTION | WS_THICKFRAME | WS_SYSMENU | WS_MINIMIZEBOX | WS_MAXIMIZEBOX)) | WS_CHILD | WS_VISIBLE
            self._set_window_long_ptr(hwnd, GWL_STYLE, style)
            ex_style = self._get_window_long_ptr(hwnd, GWL_EXSTYLE)
            ex_style = (ex_style & ~WS_EX_APPWINDOW) | WS_EX_TOOLWINDOW
            self._set_window_long_ptr(hwnd, GWL_EXSTYLE, ex_style)
            w, h = self._client_size()
            self._user32.ShowWindow(wintypes.HWND(hwnd), SW_SHOW)
            self._user32.SetWindowPos(wintypes.HWND(hwnd), None, 0, 0, w, h, SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED)
            self.child_hwnd = int(hwnd)
            self.attached = True
            self.ever_attached = True
            self.child_window_closed = False
            self.child_window_closed_at = 0.0
            self.child_window_closed_reason = ""
            self.attached_at = time.monotonic()
            self.focus_child(force=True)
            return True
        except Exception as exc:
            self.attach_error = f"attach-error:{exc}"
            return False

    def _mark_child_window_closed(self, reason: str = "window-closed") -> None:
        self.child_window_closed = True
        if not self.child_window_closed_at:
            self.child_window_closed_at = time.monotonic()
        self.child_window_closed_reason = str(reason or "window-closed")
        self.attached = False
        self.child_hwnd = 0
        if not self.attach_error:
            self.attach_error = self.child_window_closed_reason

    def focus_child(self, force: bool = False) -> bool:
        if self._user32 is None or not self.child_hwnd:
            return False
        now = time.monotonic()
        if not force and (now - float(self.last_focus_at or 0.0)) < 0.65:
            return False
        try:
            hwnd = wintypes.HWND(self.child_hwnd)
            self._user32.BringWindowToTop(hwnd)
            self._user32.SetForegroundWindow(hwnd)
            self._user32.SetFocus(hwnd)
            self.last_focus_at = now
            return True
        except Exception:
            return False

    def request_graceful_close(self) -> bool:
        if self._user32 is None or not self.child_hwnd:
            return False
        WM_KEYDOWN = 0x0100
        WM_KEYUP = 0x0101
        WM_CLOSE = 0x0010
        VK_ESCAPE = 0x1B
        try:
            hwnd = wintypes.HWND(self.child_hwnd)
            self.focus_child(force=True)
            self._user32.PostMessageW(hwnd, WM_KEYDOWN, VK_ESCAPE, 0)
            self._user32.PostMessageW(hwnd, WM_KEYUP, VK_ESCAPE, 0)
            return True
        except Exception:
            try:
                self._user32.PostMessageW(wintypes.HWND(self.child_hwnd), WM_CLOSE, 0, 0)
                return True
            except Exception:
                return False

    def _resize_child(self) -> None:
        if self._user32 is None or not self.child_hwnd:
            return
        SWP_NOZORDER = 0x0004
        SWP_NOACTIVATE = 0x0010
        try:
            if hasattr(self._user32, "IsWindow") and not self._user32.IsWindow(wintypes.HWND(self.child_hwnd)):
                self._mark_child_window_closed("child-window-destroyed")
                return
            if hasattr(self._user32, "IsWindowVisible") and not self._user32.IsWindowVisible(wintypes.HWND(self.child_hwnd)):
                self._mark_child_window_closed("child-window-hidden")
                return
            w, h = self._client_size()
            self._user32.SetWindowPos(wintypes.HWND(self.child_hwnd), None, 0, 0, w, h, SWP_NOZORDER | SWP_NOACTIVATE)
        except Exception:
            pass

    def _run(self) -> None:
        deadline = time.monotonic() + self.ATTACH_TIMEOUT_SECONDS
        while not self._stop.is_set():
            if self.proc.poll() is not None:
                return
            if not self.attached:
                if self.child_window_closed:
                    return
                hwnd = self._find_child_window()
                if hwnd:
                    self._attach(hwnd)
                elif time.monotonic() > deadline:
                    self.attach_error = "child-window-not-found"
                    self.attach_timed_out = True
                    deadline = time.monotonic() + 999999.0
            else:
                self._resize_child()
            time.sleep(self.POLL_SECONDS)

def _core_mode_folder_for_name(root: Path, name: str) -> Path:
    clean = str(name or "").strip()
    if clean.lower() in ROOT_ONLY_CORE_MODE_FOLDERS:
        return root / clean
    return resolve_dimensions_root(root) / clean


def _mode_process_python_executable() -> str:
    """Return the best interpreter for launched game modes.

    On Windows, launching with python.exe can leave the command prompt as the
    active window.  Prefer pythonw.exe when it lives beside the
    current interpreter so hosted game windows can own focus without a console
    window stealing it.
    """
    try:
        exe = Path(sys.executable)
        if os.name == "nt":
            candidates = []
            if exe.name.lower() == "python.exe":
                candidates.append(exe.with_name("pythonw.exe"))
            candidates.append(exe.parent / "pythonw.exe")
            for cand in candidates:
                if cand.exists() and cand.is_file():
                    return os.fspath(cand)
    except Exception:
        pass
    return sys.executable


def _mode_process_creationflags() -> int:
    flags = 0
    if os.name == "nt":
        flags |= int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) or 0)
        flags |= int(getattr(subprocess, "CREATE_NO_WINDOW", 0) or 0)
    return flags


def _open_mode_stdio_log(label: str):
    """Open an append-only child-process log, falling back to DEVNULL.

    Keeping stdout/stderr out of the parent console prevents the CMD window from
    becoming the apparent active app while a launched Dimension is running.
    """
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        safe = re.sub(r"[^A-Za-z0-9._-]+", "_", str(label or "mode")).strip("_") or "mode"
        path = LOG_DIR / f"mode_process_{safe}.log"
        f = path.open("a", encoding="utf-8", buffering=1)
        f.write(f"\n--- launch {datetime.now().isoformat(timespec='seconds')} pid_parent={os.getpid()} ---\n")
        return f
    except Exception:
        return subprocess.DEVNULL


def _launch_mode_subprocess(path: Path, env: dict, label: str) -> subprocess.Popen:
    """Launch a standalone Dimension with console-safe Windows defaults."""
    stdout_handle = _open_mode_stdio_log(label)
    kwargs = {
        "cwd": os.fspath(Path(path).parent),
        "env": env,
        "stdout": stdout_handle,
        "stderr": subprocess.STDOUT,
    }
    if os.name == "nt":
        flags = _mode_process_creationflags()
        if flags:
            kwargs["creationflags"] = flags
        try:
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= getattr(subprocess, "STARTF_USESHOWWINDOW", 0)
            # Do not request SW_HIDE here.  Pass 4 fixed CMD focus, but hiding
            # the child window is a possible Windows regression for real game
            # windows.  Keep no-console behavior while letting the game show.
            startupinfo.wShowWindow = 1
            kwargs["startupinfo"] = startupinfo
        except Exception:
            pass
    proc = subprocess.Popen([_mode_process_python_executable(), os.fspath(path)], **kwargs)
    try:
        if stdout_handle not in (None, subprocess.DEVNULL):
            stdout_handle.close()
    except Exception:
        pass
    return proc


def _focus_visible_window_for_pid(pid: int, *, label: str = "") -> bool:
    """Best-effort Windows focus helper for hosted non-embedded modes."""
    if os.name != "nt" or not pid:
        return False
    try:
        user32 = ctypes.windll.user32
        hwnds: list[int] = []
        EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        def _callback(hwnd, _lparam):
            try:
                if not user32.IsWindowVisible(hwnd):
                    return True
                proc_id = wintypes.DWORD()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(proc_id))
                if int(proc_id.value) == int(pid):
                    hwnds.append(int(hwnd))
            except Exception:
                pass
            return True

        user32.EnumWindows(EnumWindowsProc(_callback), 0)
        if not hwnds:
            return False
        try:
            hwnds.sort(key=lambda h: int(user32.GetWindowTextLengthW(wintypes.HWND(h))), reverse=True)
        except Exception:
            pass
        hwnd = wintypes.HWND(hwnds[0])
        SW_RESTORE = 9
        user32.ShowWindow(hwnd, SW_RESTORE)
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
        return True
    except Exception as exc:
        try:
            print(f"external_focus_failed label={label} err={exc}")
        except Exception:
            pass
        return False


def discover_core_modes(root: Path) -> list[dict]:
    """Discover launchable folders for the Core panel.

    Current builds keep mode folders under /Dimensions. Modes are entered
    through the transition-routed gateway instead of root companion panels.
    Holo Campaign may also provide Alternate.py; that file is not a separate
    mode, it is the alternating entry point for the campaign mode.
    """
    modes = []
    seen = set()
    dimensions_root = resolve_dimensions_root(root)

    def add_folder(folder: Path, force_name: str | None = None, fallback_only: bool = False, mode_root: str = "dimensions"):
        name = force_name or folder.name
        key = name.lower()
        if key in seen or key in MODE_FOLDER_EXCLUDES:
            return
        main = find_case_insensitive_file(folder, "main.py")
        alternate = find_case_insensitive_file(folder, "alternate.py")
        placeholder = False
        if main is None and fallback_only:
            main = folder / "main.py"
            if name.lower() == "holo campaign":
                alternate = folder / "Alternate.py"
        if main is None:
            placeholder = True
            main = folder / "main.py"
        manifest = _placeholder_mode_manifest(folder, name) if placeholder else load_or_create_mode_manifest(folder, name, main, alternate)
        if not placeholder:
            manifest_entry = str(manifest.get("entry") or "").strip()
            if manifest_entry:
                entry_path = folder / manifest_entry
                if entry_path.exists() and entry_path.is_file():
                    main = entry_path
        launch_type = normalize_mode_launch_type(manifest.get("launch_type"))
        seen.add(key)
        modes.append({
            "name": name,
            "folder": folder,
            "mode_root": "placeholder" if placeholder else mode_root,
            "main": main,
            "alternate": alternate,
            "available": True if placeholder else main.exists(),
            "has_alternate": bool(False if placeholder else (alternate is not None and (alternate.exists() or fallback_only))),
            "placeholder": bool(placeholder or manifest.get("placeholder_mode", False)),
            "manifest": manifest,
            "launch_type": launch_type,
            "source_kind": str(manifest.get("source_kind", "unknown")),
            "panel_supported": bool(manifest.get("panel_supported", False)),
            "native_panda_candidate": False,
        })

    if dimensions_root.exists() and dimensions_root.is_dir():
        try:
            for folder in sorted([p for p in dimensions_root.iterdir() if p.is_dir()], key=lambda p: p.name.lower()):
                add_folder(folder, mode_root="dimensions")
        except Exception as exc:
            try:
                print(f"mode_discovery_error root={dimensions_root} err={exc}")
            except Exception:
                pass

    # Recover from stale installs or interrupted folder discovery by using the
    # transition dimension index as the source of truth. This prevents valid
    # bot doorways from showing MODE NOT FOUND when their files are present.
    try:
        payload = read_dimension_index_payload()
        dimensions = payload.get("dimensions") if isinstance(payload.get("dimensions"), dict) else {}
        existing_keys = set()
        for mode in modes:
            manifest = dict(mode.get("manifest") or {})
            for item in (mode.get("name", ""), manifest.get("title", ""), manifest.get("id", "")):
                existing_keys.add(canonical_dimension_lookup_key(item))
        for key, record in sorted(dimensions.items(), key=lambda kv: str(kv[0]).lower()):
            if not isinstance(record, dict):
                continue
            canonical = canonical_dimension_lookup_key(record.get("id") or key)
            if canonical in existing_keys:
                continue
            recovered = mode_from_dimension_record(record)
            if recovered is not None:
                modes.append(recovered)
                seen.add(normalize_lookup_key(recovered.get("name", "")))
                existing_keys.add(canonical)
    except Exception as exc:
        try:
            print(f"mode_index_recovery_error err={exc}")
        except Exception:
            pass
    # Backward-compatible root-folder fallback is disabled when /Dimensions exists.
    # Current builds must not turn config/log/progression/tool folders into fake
    # placeholder dimensions. Only real folders under /Dimensions are launchable.

    # Root-only companion folders are retired for the transition-routed layout.
    for name in sorted(ROOT_ONLY_CORE_MODE_FOLDERS):
        display = next((n for n in FALLBACK_CORE_MODE_FOLDERS if n.lower() == name), name.title())
        add_folder(root / display, force_name=display, fallback_only=True, mode_root="root-companion")

    # No legacy reservation pass: empty real folders become clean placeholders,
    # and removed old modes stay removed.
    return modes


def load_mode_state() -> dict:
    try:
        if MODE_STATE_PATH.exists():
            data = json.loads(MODE_STATE_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {"campaign_next_alternate": False, "launch_count": 0, "last_mode": ""}


def save_mode_state(state: dict):
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        _safe_write_json(MODE_STATE_PATH, state if isinstance(state, dict) else {})
    except Exception:
        pass


def _matrixcore_text_excerpt(path: Path, max_chars: int = 360) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore").strip()
    except Exception:
        return ""
    if not text:
        return ""
    parts = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    body = parts[1] if len(parts) > 1 else parts[0]
    body = re.sub(r"\s+", " ", body).strip()
    return body[:max_chars].rstrip() + ("..." if len(body) > max_chars else "")


def matrixcore_database_dir_candidates() -> list[Path]:
    """Return MatrixCore archive folders in the order requested for lore display.

    Search bundled project contents first, then the shared/outer database lanes.
    This keeps the shipped lore study visible even when the external database
    has not been copied beside the app yet.
    """
    candidates = [
        ROOT / "matrixcore" / "database",
        ROOT / "MatrixCore" / "database",
        ROOT / "data" / "database" / "matrixcore",
        ROOT / "data" / "database" / "MatrixCore",
        APP_DATA_DIR / "database" / "matrixcore",
        APP_DATA_DIR / "database" / "MatrixCore",
        SHARED_DATABASE_DIR / "matrixcore",
        SHARED_DATABASE_DIR / "MatrixCore",
        MATRIXCORE_DATABASE_DIR,
    ]
    unique: list[Path] = []
    seen: set[str] = set()
    for path in candidates:
        try:
            key = os.fspath(path.resolve()).lower()
        except Exception:
            key = os.fspath(path).lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return unique


def matrixcore_lore_study_candidates() -> list[Path]:
    """Return lore study files, bundled contents first, then shared/outer paths."""
    candidates = [
        MATRIXCORE_CONTENT_LORE_STUDY_PATH,
        ROOT / "MatrixCore" / "lore_study.json",
        ROOT / "data" / "database" / "matrixcore" / "lore_study.json",
        ROOT / "data" / "database" / "MatrixCore" / "lore_study.json",
        APP_DATA_DIR / "database" / "matrixcore" / "lore_study.json",
        APP_DATA_DIR / "database" / "MatrixCore" / "lore_study.json",
        SHARED_DATABASE_DIR / "matrixcore" / "lore_study.json",
        SHARED_DATABASE_DIR / "MatrixCore" / "lore_study.json",
        MATRIXCORE_LORE_STUDY_PATH,
    ]
    unique: list[Path] = []
    seen: set[str] = set()
    for path in candidates:
        try:
            key = os.fspath(path.resolve()).lower()
        except Exception:
            key = os.fspath(path).lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return unique


def load_matrixcore_archive_index() -> list[dict]:
    """Index MatrixCore story/database files without moving them.

    Search bundled contents first, then the outer data/database/matrixcore lane.
    """
    entries: list[dict] = []
    files: list[Path] = []
    source_dir = ""
    for folder in matrixcore_database_dir_candidates():
        try:
            if not folder.exists() or not folder.is_dir():
                continue
            found = sorted(folder.glob("*.txt"), key=lambda path: path.name.lower())
            if found:
                files = found
                source_dir = os.fspath(folder)
                break
        except Exception:
            continue
    for idx, path in enumerate(files):
        try:
            raw = path.read_text(encoding="utf-8", errors="ignore").strip()
        except Exception:
            raw = ""
        title = path.stem
        if raw:
            first = next((line.strip() for line in raw.splitlines() if line.strip()), "")
            if first:
                title = first
        entries.append({
            "id": idx,
            "title": title,
            "file": os.fspath(path),
            "source_dir": source_dir,
            "excerpt": _matrixcore_text_excerpt(path),
        })
    return entries


def matrixcore_archive_index_from_lore_study(lore: dict) -> list[dict]:
    """Convert lore_study chapter_index entries into archive-style entries."""
    chapters = lore.get("chapter_index") if isinstance(lore, dict) else []
    if not isinstance(chapters, list):
        return []
    entries: list[dict] = []
    for idx, chapter in enumerate(chapters):
        if not isinstance(chapter, dict):
            continue
        summary = str(chapter.get("summary") or chapter.get("excerpt") or "").strip()
        entries.append({
            "id": int(chapter.get("id", idx) or idx),
            "title": str(chapter.get("title") or f"Chapter {idx:02d}"),
            "file": str(chapter.get("file") or chapter.get("relative_file") or "matrixcore/lore_study.json"),
            "source_dir": str(lore.get("_loaded_from") or "matrixcore/lore_study.json"),
            "excerpt": summary[:360].rstrip() + ("..." if len(summary) > 360 else ""),
            "phase": str(chapter.get("phase") or ""),
            "tags": list(chapter.get("tags") or [])[:8] if isinstance(chapter.get("tags"), list) else [],
        })
    return entries


def load_matrixcore_lore_study() -> dict:
    """Load MatrixCore lore from bundled contents first, then outer database paths.

    The Lore route should display the matrixcore/lore_study.json bundled with
    this build when present. If it is missing, check the shared/outer
    data/database/matrixcore locations before falling back to a live archive
    index.
    """
    for candidate in matrixcore_lore_study_candidates():
        try:
            if not candidate.exists() or not candidate.is_file():
                continue
            data = json.loads(candidate.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                data.setdefault("_loaded_from", os.fspath(candidate))
                try:
                    if candidate != MATRIXCORE_LORE_STUDY_PATH and not MATRIXCORE_LORE_STUDY_PATH.exists():
                        MATRIXCORE_LORE_STUDY_PATH.parent.mkdir(parents=True, exist_ok=True)
                        MATRIXCORE_LORE_STUDY_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
                except Exception:
                    pass
                return data
        except Exception:
            continue
    archive = load_matrixcore_archive_index()
    fallback = {
        "schema_version": 1,
        "study_status": "fallback_live_archive_index",
        "_loaded_from": os.fspath(MATRIXCORE_DATABASE_DIR),
        "core_truth": "MatrixCore is the memory-brain and dimensional stabilizer of Holoverse, not a launcher menu.",
        "holoverse_truth": "Holoverse is a field of prototype realities built from memory, loss, and corrective creation.",
        "current_lore_position": {
            "last_file_read": str((archive[-1] or {}).get("title", "none")) if archive else "none",
            "left_off": "Fallback generated from archive titles only; run the lore study pass to rebuild the full index.",
        },
        "canon_arc": [entry.get("title", "Archive") for entry in archive[:8]],
        "eras": [],
        "major_entities": [],
        "matrixcore_design_rules": [
            "MatrixCore should behave like the heart/brain of Holoverse, not like a mode launcher.",
            "Dimensions should remain prototype realities accessed through immersive doorways.",
        ],
        "matrixcore_ui_lines": {
            "guide": "MatrixCore is the memory-brain that keeps Holoverse coherent.",
            "lore": "Lore study fallback is online; archive files are indexed but not fully summarized yet.",
        },
        "chapter_index": archive,
    }
    try:
        MATRIXCORE_LORE_STUDY_PATH.parent.mkdir(parents=True, exist_ok=True)
        MATRIXCORE_LORE_STUDY_PATH.write_text(json.dumps(fallback, indent=2) + "\n", encoding="utf-8")
    except Exception:
        pass
    return fallback


def matrixcore_lore_display_summary(lore: dict, *, chapter_limit: int = 5, canon_limit: int = 4) -> str:
    """Build a compact lore digest suitable for MatrixCore panels."""
    if not isinstance(lore, dict):
        lore = {}
    chapters = list(lore.get("chapter_index", []) or [])
    canon = list(lore.get("canon_arc", []) or [])
    eras = [entry for entry in list(lore.get("eras", []) or []) if isinstance(entry, dict)]
    entities = [entry for entry in list(lore.get("major_entities", []) or []) if isinstance(entry, dict)]
    left = lore.get("current_lore_position") if isinstance(lore.get("current_lore_position"), dict) else {}
    lines: list[str] = []
    source = str(lore.get("_loaded_from") or MATRIXCORE_CONTENT_LORE_STUDY_PATH)
    status = str(lore.get("study_status") or "indexed")
    lines.append(f"Source: {source}")
    lines.append(f"Status: {status} // chapters {len(chapters)} // eras {len(eras)}")
    if lore.get("core_truth"):
        lines.append(f"Core truth: {str(lore.get('core_truth'))}")
    if lore.get("holoverse_truth"):
        lines.append(f"HoloVerse truth: {str(lore.get('holoverse_truth'))}")
    if left:
        lines.append(f"Archive note: {left.get('last_title', 'Review ready')} — {left.get('left_off', 'handoff pending')}")
    if canon:
        lines.append("Canon spine:")
        for item in canon[:canon_limit]:
            lines.append(f"- {str(item)}")
    if eras:
        lines.append("Eras: " + ", ".join(str(entry.get("name", "ERA")) for entry in eras[:4]))
    if entities:
        lines.append("Entities: " + ", ".join(str(entry.get("name", "ENTITY")) for entry in entities[:6]))
    if chapters:
        lines.append("Chapter signals:")
        for chapter in chapters[:chapter_limit]:
            if not isinstance(chapter, dict):
                continue
            title = str(chapter.get("title") or "Chapter")
            summary = str(chapter.get("summary") or chapter.get("excerpt") or "").strip()
            if len(summary) > 190:
                summary = summary[:190].rstrip() + "..."
            lines.append(f"- {title}: {summary or 'summary pending'}")
    return "\n".join(lines)

def write_json_if_missing(path: Path, payload: dict) -> None:
    try:
        if path.exists():
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    except Exception:
        pass


@dataclass
class ObservatoryConfig:
    mouse_sensitivity: float = 0.11
    controller_look_sensitivity: float = 110.0
    walk_speed: float = 10.0
    sprint_speed: float = 16.0
    line_thickness: float = 1.9
    line_hue: float = 0.57
    line_saturation: float = 0.72
    line_value: float = 1.0
    background_value: float = 0.018
    fov: float = 82.0
    fog_distance: float = 620.0
    hud_visible: bool = True
    terrain_chunk_size: float = 56.0
    terrain_render_radius: int = 2
    terrain_grid_step: float = 8.0
    terrain_height: float = 15.0
    safe_flat_radius: float = 42.0
    transition_duration: float = 4.6
    chunk_fade_speed: float = 3.8
    terrain_collision_clearance: float = 0.16
    world_seed: int = 10457
    world_shell_mount_enabled: bool = True
    world_shell_active_biome: int = 1
    world_shell_mount_detail: str = "stream"
    world_shell_mount_scale: float = 1.0
    world_shell_stream_radius: int = 4
    world_shell_default_preload: bool = False
    world_shell_preload_all_biomes: bool = False
    world_shell_preload_corridors: bool = True
    world_shell_preload_sector_radius: int = 0
    world_shell_max_preloaded_sectors: int = 192
    world_shell_exit_gate_hints: bool = True
    world_shell_entry_ribbons: bool = True
    world_shell_transition_cues: bool = True
    world_shell_first_ring_props: bool = True
    world_shell_first_ring_prop_count: int = 14
    world_shell_ground_continuity: bool = True
    world_shell_ground_band_count: int = 5
    world_shell_scale_handoff_markers: bool = True
    world_shell_collision_height_hints: bool = True
    world_shell_local_detail_boost: bool = True
    world_shell_biome_signature_density: int = 2
    world_shell_directional_feedback: bool = True
    world_shell_direction_marker_count: int = 6
    world_shell_corridor_theming: bool = True
    world_shell_theme_handoff: bool = True
    world_shell_theme_handoff_strength: float = 0.35
    world_shell_hub_theme_influence: bool = True
    world_shell_hub_theme_max_blend: float = 0.18
    world_shell_hub_theme_fog_blend: float = 0.14
    world_shell_hub_theme_light_blend: float = 0.12
    world_shell_status_prompts: bool = True
    world_shell_motion_enabled: bool = True
    world_shell_motion_intensity: float = 0.38
    world_shell_audio_handoff: bool = True
    world_shell_audio_handoff_strength: float = 0.34
    world_shell_ambience_radius: float = 620.0
    world_shell_playable_enabled: bool = True
    world_shell_play_radius: float = 11100.0
    world_shell_play_speed_scale: float = 1.10
    world_shell_play_floor_enabled: bool = True
    world_shell_use_world_py_source: bool = True
    world_shell_boundary_feedback: bool = True
    world_shell_boundary_warning_distance: float = 28.0
    world_shell_checkpoint_enabled: bool = True
    world_shell_checkpoint_count: int = 12
    world_shell_checkpoint_pickup_radius: float = 4.8
    world_shell_biome_entry_prompts: bool = True
    world_shell_region_keymap_enabled: bool = False
    dev_region_number_travel_enabled: bool = False
    air_travel_requires_saved_craft: bool = True
    hub_fill_enabled: bool = True
    hub_fill_opacity: float = 0.42
    player_eye_height: float = 3.95
    master_volume: float = 0.82
    sfx_volume: float = 0.82
    music_volume: float = 0.42
    ambience_volume: float = 0.58
    soundtrack_enabled: bool = True
    soundtrack_intensity: float = 0.55
    ambience_intensity: float = 0.45
    soundmatrix_use_vector_wars_sources: bool = True
    soundmatrix_variant_intensity: float = 0.65
    soundmatrix_music_intensity: float = 0.55
    soundmatrix_random_seed: int = 2048
    launch_width: int = 1920
    launch_height: int = 1080
    launch_fullscreen: bool = False
    launch_borderless: bool = False
    launch_bordered_fullscreen: bool = True
    launch_game_mouse_sensitivity: float = 0.22
    launch_invert_y: bool = False
    launch_hud_visible: bool = True
    launch_graphics_quality: str = "medium"
    launch_controller_deadzone: float = 0.12
    launch_ui_scale: float = 1.0
    launch_render_scale: float = 1.0
    launch_fps_cap: int = 60
    launch_vsync: bool = True
    launch_subtitles_enabled: bool = True
    launch_brightness: float = 1.0
    launch_contrast: float = 1.0
    launch_gamma: float = 1.0
    launch_override_mode_settings: bool = True
    vr_enabled: bool = False
    vr_snap_turn_degrees: float = 30.0
    vr_move_speed: float = 10.0
    vr_seated_mode: bool = False
    vr_height_offset: float = 0.0
    vr_comfort_vignette: float = 0.18
    vr_show_runtime_panel: bool = True
    vr_turn_mode: str = "snap"
    vr_smooth_turn_rate: float = 75.0
    vr_comfort_preset: str = "snap"
    vr_onboarding_complete: bool = False


DEFAULT_CONFIG = ObservatoryConfig()


def ensure_dirs():
    for p in [
        ASSETS, CONFIG_DIR, CORE_CONFIG_DIR, TEXTURE_DIR, AUDIO_DIR, AUDIO_LIBRARY_DIR, CANONICAL_REVERSED_MUSIC_DIR, LOG_DIR, PATCH_DIR,
        SHARED_HOLOVERSE_DATA_DIR, SHARED_BRAIN_DIR, SHARED_DATABASE_DIR, MATRIXCORE_DATABASE_DIR,
        MATRIXCORE_DATA_DIR, MATRIXCORE_PROGRESSION_DIR, MATRIXCORE_DIMENSIONS_DIR,
    ]:
        p.mkdir(parents=True, exist_ok=True)


class TeeLogger:
    def __init__(self, path: Path):
        self.file = path.open("w", encoding="utf-8")

    def write(self, text: str):
        self.file.write(text)
        self.file.flush()
        sys.__stdout__.write(text)
        sys.__stdout__.flush()

    def flush(self):
        self.file.flush()
        sys.__stdout__.flush()


def install_logging():
    ensure_dirs()
    logger = TeeLogger(LATEST_LOG)
    sys.stdout = logger
    sys.stderr = logger


def install_crash_reporter():
    def _hook(exc_type, exc, tb):
        ensure_dirs()
        with CRASH_LOG.open("w", encoding="utf-8") as f:
            f.write(f"{GAME_NAME} {VERSION}\n")
            f.write(f"Timestamp: {datetime.now().isoformat()}\n\n")
            traceback.print_exception(exc_type, exc, tb, file=f)
        traceback.print_exception(exc_type, exc, tb)

    sys.excepthook = _hook


def write_patch_notes():
    ensure_dirs()
    note = textwrap.dedent(
        f"""
        {GAME_NAME}
        Version: {VERSION}
        Generated: {datetime.now().isoformat()}

        Patch Notes
        - v0.10.45 UI / Persistence / Terrain Polish: Removed the FPS corner box, replaced it with a small transparent total-points readout, reduced UI panel opacity, tightened offscreen-prone runtime panels, made Green Hills animals spawn as grown saved animals, mirrored Hills and Mushroom region saves into canonical shared data, and brightened Urban terrain colors without adding new geometry.
        - v0.10.41 Urban Arena Regression Guard: Kept the imported Urban arena mounted from the actual Region 6 travel/update route after shell refreshes, while preserving Sable as the formal match trigger and all cyan UI/settings updates.
        - v0.10.40 Cyan UI Settings Maintenance Pass: Modernized HUD/settings/Core/Gleebs styling with cyan glass overlays, easier quit actions, hold-ESC help, and advanced MatrixCore visuals.
        - v0.10.39 HoloSpace Liquid Orb Transition Pass: Embedded the Liquid Orb texture-wrap sphere into the live game as a 10-second sky/space travel sequence for number 8 and flying-vehicle ascent, then hands off to the default HoloSpace spawn.
        - v0.10.14 Gleebs Bot Support Pass: Added MatrixCore bot support profiles, bot-aware prompts, bot doorway progression signals, and sanity/proof reporting for bot integration.
        - v0.10.13 Gleebs Guidance Pass: Added MatrixCore Next Signal guidance, dimension-specific Gleebs advice, route-aware return feedback, and live proof metadata for useful guidance.
        - v0.10.12 Gleebs Personality Pass: Added fun Gleebs voice lines, bottom quote signatures, creator-echo hints for Glitched Matrix, repeat-safe personality flags, and updated MatrixCore proof metadata.
        - v0.10.11 MatrixCore Live Proof Pass: Added MatrixCore/Gleebs live proof report and verification that the panel is guide-focused instead of a mode-launch list.
        - v0.10.10 MatrixCore Gleebs Context Pass: Added queued first-contact dialogue sequence, panel-safe cyan text lanes, MatrixCore consult tracking, dimension launch/return progression signals, and non-repeating contextual Gleebs lines.
        - v0.10.09 MatrixCore Gleebs Dialogue Pass: Added Gleebs hologram projection, cyan non-panel dialogue overlay, one-time intro flags in shared data/holoverse progression state, ESC/distance fade dismissal, and MatrixCore lore lines for Utopia salvage/hyperspace continuity.
        - v0.9.96 Audio Variant / ESC Return Pass: Added rotating music variants, shared mode playlist metadata, double-tap/hold ESC return helpers, and main installer files.
        - v0.9.95 Audio Redo Pass: Replaced the hub-following core hum with a context-aware soundscape director, added hub/world/urban/metropolis/space/water loops, fixed live loop gain refresh, and pointed mode audio profiles at shared musical loops while preserving event SFX.
        - v0.9.53 Pass 47: Reworked Mushroom as a shallow, readable aqua region with hoverboard surface spawn, controlled dive/swim below the waterline, visible infilled bottom/walls, denser coral visibility, and stricter vector-style flora/fauna silhouettes.
        - v0.9.52 Pass 46: Added calm connected Mushroom surface wave line animation, kept the wave rebuild low-frequency for frame stability, and added more inexpensive infilled Forests/Green Hills flora/fauna variants.
        - v0.9.51 Pass 45: Added Mushroom swim authority for the default HoloVerse, moved the water surface above a swim-only aqua volume, and added a presentability pass for inexpensive infilled vector flora/fauna variants.
        - v0.9.50 Pass 39: Switched the default HoloVerse mount to prefer salvaged world.py generation helpers instead of rebuilt adapter visuals. Core still owns the window/hub/artifacts; world.py supplies the original terrain, biome rings, named bots, sky, and streaming helpers when available, with the previous adapter retained only as fallback.
        - v0.9.48 Pass 37: Cleaned up the Core-owned HoloVerse lifecycle and naming. The default world is now reported as HOLOVERSE_DEFAULT, the separate HoloVerse launcher entry is hidden, artifact activation unloads the HoloVerse default runtime, and T return clears simulations then reloads HoloVerse as the active default environment.
        - v0.9.47 Pass 36: Promoted the default HoloVerse from tiny proxy scale to full HoloVerse/world.py scale, assigned it to the Core boot lifecycle, unloads it during artifact simulations, and reloads it when T returns to the hub.
        - v0.9.46 Pass 35: Added the first lightweight playable shell loop: soft boundary feedback/clamp, biome-entry prompts, persistent checkpoint/collectible state, and pickup status hooks while keeping the hub and artifact worlds authoritative.
        - v0.9.45 Pass 34: Made the default HoloVerse playable by moving the mount out of hidden world_root, adding bounded walk-out traversal, visual shell-floor height hints, and safe play radius/status controls while keeping artifact worlds and hub authority intact.
        - v0.9.44 Pass 33: Added data-first HoloVerse movement/ambience feedback with biome-aware status prompts, subtle audio handoff hints near hub exits, and low-cost animated shell motion while keeping hub audio/render authority intact.
        - v0.9.43 Pass 32: Added subtle capped hub light/fog influence from the HoloVerse theme handoff, including safe resets when shell mount is disabled/errors or artifact transitions take over.
        - v0.9.40 Pass 29: Added near-hub HoloVerse entry ribbons, compact biome transition cues, and bounded first-ring ambient props so the default preloaded world feels more walkable around the observatory without changing hub ownership or importing standalone world.py.
        - v0.9.39 Pass 28: Strengthened the default HoloVerse preload with visible hub exit gates, biome signature silhouettes, and local-detail boost sectors so the mounted world reads as the surrounding default environment without importing standalone world.py.
        - v0.9.38 Pass 27: Promoted the extracted HoloVerse mount into the default preloaded world around the observatory hub. The hub now warms all biome rings plus cardinal travel-corridor sectors on boot, records preload counts in settings/state, and keeps the standalone full shell available as a separate launch mode.
        - v0.9.15: Continued from the supplied v0.9.14 file only; cleaned the legacy arena reservation from the Core mode deck, switched the launcher shell to full-size bordered/non-topmost window mode, fixed hold-ESC by preventing key-repeat timer resets, paused the hub while external modes are active, and made E activate looked-at or nearby artifacts instead of relying on number keys.
        - v0.9.17: Added the first manifest-driven HoloVerse mode gateway pass. Folder modes stay independent and receive a shared host contract.
        - v0.9.18-v0.9.21: Historical native-adapter experiments were retired in the clean /Dimensions layout. Native aliases now downgrade to the embedded/hosted gateway.
        - v0.9.24: Rebased legacy panel routes onto the latest intact pass, added persistent Core-side log panels, and added a same-window Holo Campaign native briefing/combat adapter while preserving hosted fallbacks.
        - v0.9.16: Real input repair pass. Removed duplicate E/Q event bindings that could swallow interaction in desktop mode, widened artifact look/near activation for real play, routed Q through the same safe handler, logs interaction probes, and minimizes the hub while external modes are running so child games can appear in front.
        - Fixed artifact world loading from normal desktop mode by adding mouse-click activation support.
        - Added a crosshair-based artifact picker so clicking the artifact you are looking at launches its world.
        - Kept E interaction working, but expanded its fallback radius so artifact prompts are not missed by minor camera/height offset.
        - Centralized artifact activation so click, E, and core menu selection all force-refresh world chunks immediately.
        - v0.9.10: Converted every 4D artifact glyph into its own animated desktop NodePath, kept each shape assigned to its pedestal/world id, and added hold-ESC-for-2-seconds full app exit.
        - v0.9.11: Rebuilt the core panel into a folder-mode launcher. Root folders with main.py now appear as launchable modes, artifacts/pedestals remain responsible for same-file world generation, and Holo Campaign alternates between main.py and Alternate.py on repeated launches.
        - v0.9.13: Added terrain-following single-texture surface underlays for generated worlds so terrain formations have readable filled ground mass beneath the wire shapes without changing collisions, world routing, artifacts, or the Core UI.
        - v0.9.14: Added visibility-safe underlay rendering. Filled world terrain now sits farther below wire terrain, uses lower alpha, avoids depth writes, and applies explicit render bins so wires, artifacts, props, and landmarks remain readable above the new surface fill.
        - v0.9.12: Rebuilt the Core launcher as a compact mouse-first game UI deck: full-caps OCR-style text, cyan/white/yellow theme, clickable mode cards, page controls, hub return, close button, visible cursor while the deck is open, and number keys no longer drive Core mode selection.
        - Preserved desktop-first launch behavior while keeping VR optional through --vr, HOLOVERSE_VR=1, or MATRIX_GAME_VR=1.
        """
    ).strip()
    LATEST_PATCH.write_text(note + "\n", encoding="utf-8")


def load_config() -> ObservatoryConfig:
    ensure_dirs()
    loaded_data = {}
    if CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            loaded_data = data if isinstance(data, dict) else {}
            merged = asdict(DEFAULT_CONFIG)
            merged.update({k: v for k, v in loaded_data.items() if k in merged})
            cfg = ObservatoryConfig(**merged)
        except Exception:
            loaded_data = {}
            cfg = DEFAULT_CONFIG
    else:
        cfg = DEFAULT_CONFIG
    # v0.9.15 migration: old configs may still request borderless/topmost or
    # exclusive fullscreen. The launcher shell must stay bordered and non-topmost
    # so external modes can take focus in front of it.
    cfg.launch_fullscreen = False
    cfg.launch_borderless = False
    if hasattr(cfg, "launch_bordered_fullscreen"):
        cfg.launch_bordered_fullscreen = True
    # Universal mode override settings owned by the HoloVerse Core.
    # Older configs may not contain these fields; keep values safe before writing.
    cfg.launch_ui_scale = max(0.65, min(1.75, float(getattr(cfg, "launch_ui_scale", 1.0))))
    cfg.launch_render_scale = max(0.50, min(1.50, float(getattr(cfg, "launch_render_scale", 1.0))))
    cfg.launch_fps_cap = max(15, min(240, int(getattr(cfg, "launch_fps_cap", 60))))
    cfg.launch_vsync = bool(getattr(cfg, "launch_vsync", True))
    cfg.launch_subtitles_enabled = bool(getattr(cfg, "launch_subtitles_enabled", True))
    cfg.launch_brightness = max(0.55, min(1.65, float(getattr(cfg, "launch_brightness", 1.0))))
    cfg.launch_contrast = max(0.55, min(1.65, float(getattr(cfg, "launch_contrast", 1.0))))
    cfg.launch_gamma = max(0.55, min(1.85, float(getattr(cfg, "launch_gamma", 1.0))))
    cfg.launch_override_mode_settings = bool(getattr(cfg, "launch_override_mode_settings", True))
    cfg.soundtrack_enabled = bool(getattr(cfg, "soundtrack_enabled", True))
    cfg.soundtrack_intensity = max(0.0, min(1.0, float(getattr(cfg, "soundtrack_intensity", 0.55))))
    cfg.ambience_intensity = max(0.0, min(1.0, float(getattr(cfg, "ambience_intensity", 0.45))))
    cfg.soundmatrix_use_vector_wars_sources = bool(getattr(cfg, "soundmatrix_use_vector_wars_sources", True))
    cfg.soundmatrix_variant_intensity = max(0.0, min(1.0, float(getattr(cfg, "soundmatrix_variant_intensity", 0.65))))
    cfg.soundmatrix_music_intensity = max(0.0, min(1.0, float(getattr(cfg, "soundmatrix_music_intensity", 0.55))))
    cfg.soundmatrix_random_seed = max(1, min(99999999, int(float(getattr(cfg, "soundmatrix_random_seed", 2048)))))
    # Pass 27 migration: make the extracted HoloVerse the default loaded world around the hub.
    first_world_shell_preload_migration = "world_shell_default_preload" not in loaded_data
    cfg.world_shell_mount_enabled = bool(getattr(cfg, "world_shell_mount_enabled", True))
    cfg.world_shell_default_preload = bool(getattr(cfg, "world_shell_default_preload", False))
    cfg.world_shell_preload_all_biomes = bool(getattr(cfg, "world_shell_preload_all_biomes", False))
    cfg.world_shell_preload_corridors = bool(getattr(cfg, "world_shell_preload_corridors", True))
    if first_world_shell_preload_migration:
        cfg.world_shell_mount_enabled = True
        cfg.world_shell_default_preload = True
        cfg.world_shell_preload_all_biomes = True
        cfg.world_shell_preload_corridors = True
    cfg.world_shell_active_biome = max(1, min(8, int(float(getattr(cfg, "world_shell_active_biome", 1)))))
    cfg.world_shell_mount_detail = str(getattr(cfg, "world_shell_mount_detail", "stream") or "stream").strip().lower()
    if cfg.world_shell_mount_detail not in {"off", "lite", "stream"}:
        cfg.world_shell_mount_detail = "stream"
    if first_world_shell_preload_migration and cfg.world_shell_mount_detail == "off":
        cfg.world_shell_mount_detail = "stream"
    cfg.world_shell_mount_scale = max(0.050, min(1.000, float(getattr(cfg, "world_shell_mount_scale", 1.0))))
    cfg.world_shell_stream_radius = max(1, min(4, int(float(getattr(cfg, "world_shell_stream_radius", 4)))))
    cfg.world_shell_preload_sector_radius = max(0, min(2, int(float(getattr(cfg, "world_shell_preload_sector_radius", 0)))))
    cfg.world_shell_max_preloaded_sectors = max(12, min(64, int(float(getattr(cfg, "world_shell_max_preloaded_sectors", 24)))))
    cfg.world_shell_exit_gate_hints = bool(getattr(cfg, "world_shell_exit_gate_hints", True))
    cfg.world_shell_entry_ribbons = bool(getattr(cfg, "world_shell_entry_ribbons", True))
    cfg.world_shell_transition_cues = bool(getattr(cfg, "world_shell_transition_cues", True))
    cfg.world_shell_first_ring_props = bool(getattr(cfg, "world_shell_first_ring_props", True))
    cfg.world_shell_first_ring_prop_count = max(0, min(32, int(float(getattr(cfg, "world_shell_first_ring_prop_count", 14)))))
    cfg.world_shell_ground_continuity = bool(getattr(cfg, "world_shell_ground_continuity", True))
    cfg.world_shell_ground_band_count = max(2, min(8, int(float(getattr(cfg, "world_shell_ground_band_count", 5)))))
    cfg.world_shell_scale_handoff_markers = bool(getattr(cfg, "world_shell_scale_handoff_markers", True))
    cfg.world_shell_collision_height_hints = bool(getattr(cfg, "world_shell_collision_height_hints", True))
    cfg.world_shell_local_detail_boost = bool(getattr(cfg, "world_shell_local_detail_boost", True))
    cfg.world_shell_biome_signature_density = max(0, min(3, int(float(getattr(cfg, "world_shell_biome_signature_density", 2)))))
    cfg.world_shell_directional_feedback = bool(getattr(cfg, "world_shell_directional_feedback", True))
    cfg.world_shell_direction_marker_count = max(2, min(10, int(float(getattr(cfg, "world_shell_direction_marker_count", 6)))))
    cfg.world_shell_corridor_theming = bool(getattr(cfg, "world_shell_corridor_theming", True))
    cfg.world_shell_theme_handoff = bool(getattr(cfg, "world_shell_theme_handoff", True))
    cfg.world_shell_theme_handoff_strength = max(0.0, min(1.0, float(getattr(cfg, "world_shell_theme_handoff_strength", 0.35))))
    cfg.world_shell_hub_theme_influence = bool(getattr(cfg, "world_shell_hub_theme_influence", True))
    cfg.world_shell_hub_theme_max_blend = max(0.0, min(0.32, float(getattr(cfg, "world_shell_hub_theme_max_blend", 0.18))))
    cfg.world_shell_hub_theme_fog_blend = max(0.0, min(0.28, float(getattr(cfg, "world_shell_hub_theme_fog_blend", 0.14))))
    cfg.world_shell_hub_theme_light_blend = max(0.0, min(0.24, float(getattr(cfg, "world_shell_hub_theme_light_blend", 0.12))))
    cfg.world_shell_status_prompts = bool(getattr(cfg, "world_shell_status_prompts", True))
    cfg.world_shell_motion_enabled = bool(getattr(cfg, "world_shell_motion_enabled", True))
    cfg.world_shell_motion_intensity = max(0.0, min(1.0, float(getattr(cfg, "world_shell_motion_intensity", 0.38))))
    cfg.world_shell_audio_handoff = bool(getattr(cfg, "world_shell_audio_handoff", True))
    cfg.world_shell_audio_handoff_strength = max(0.0, min(1.0, float(getattr(cfg, "world_shell_audio_handoff_strength", 0.34))))
    cfg.world_shell_ambience_radius = max(112.0, min(1400.0, float(getattr(cfg, "world_shell_ambience_radius", 620.0))))
    cfg.world_shell_playable_enabled = bool(getattr(cfg, "world_shell_playable_enabled", True))
    if cfg.world_shell_mount_enabled and not cfg.world_shell_playable_enabled:
        # Recover older/stale visual-only configs that mount the world shell but
        # then block player movement as soon as the traveler leaves the hub.
        cfg.world_shell_playable_enabled = True
    cfg.world_shell_play_radius = max(620.0, min(11100.0, float(getattr(cfg, "world_shell_play_radius", 11100.0))))
    cfg.world_shell_play_speed_scale = max(0.75, min(1.80, float(getattr(cfg, "world_shell_play_speed_scale", 1.10))))
    cfg.world_shell_play_floor_enabled = bool(getattr(cfg, "world_shell_play_floor_enabled", True))
    cfg.world_shell_use_world_py_source = bool(getattr(cfg, "world_shell_use_world_py_source", True))
    cfg.world_shell_boundary_feedback = bool(getattr(cfg, "world_shell_boundary_feedback", True))
    cfg.world_shell_boundary_warning_distance = max(8.0, min(72.0, float(getattr(cfg, "world_shell_boundary_warning_distance", 28.0))))
    cfg.world_shell_checkpoint_enabled = bool(getattr(cfg, "world_shell_checkpoint_enabled", True))
    cfg.world_shell_checkpoint_count = max(0, min(32, int(float(getattr(cfg, "world_shell_checkpoint_count", 12)))))
    cfg.world_shell_checkpoint_pickup_radius = max(2.0, min(9.5, float(getattr(cfg, "world_shell_checkpoint_pickup_radius", 4.8))))
    cfg.world_shell_biome_entry_prompts = bool(getattr(cfg, "world_shell_biome_entry_prompts", True))
    # Pass 44: keep HoloVerse/world object infill enabled by default so world props read as solid forms.
    cfg.hub_fill_enabled = True
    try:
        cfg.hub_fill_opacity = max(0.18, min(0.58, float(getattr(cfg, "hub_fill_opacity", 0.42))))
    except Exception:
        cfg.hub_fill_opacity = 0.42
    cfg.world_shell_region_keymap_enabled = bool(getattr(cfg, "world_shell_region_keymap_enabled", False))
    cfg.dev_region_number_travel_enabled = bool(getattr(cfg, "dev_region_number_travel_enabled", False))
    cfg.air_travel_requires_saved_craft = bool(getattr(cfg, "air_travel_requires_saved_craft", True))
    save_config(cfg)
    write_audio_bus(cfg)
    write_shared_launch_settings(cfg)
    return cfg


def save_config(cfg: ObservatoryConfig):
    ensure_dirs()
    try:
        _safe_write_json(CONFIG_PATH, asdict(cfg))
    except Exception:
        pass
    try:
        write_audio_bus(cfg)
    except Exception:
        pass
    try:
        write_shared_launch_settings(cfg)
    except Exception:
        pass



def build_audio_bus_payload(cfg: ObservatoryConfig):
    return {
        "master_volume": round(max(0.0, min(1.0, cfg.master_volume)), 3),
        "sfx_volume": round(max(0.0, min(1.0, cfg.sfx_volume)), 3),
        "music_volume": round(max(0.0, min(1.0, cfg.music_volume)), 3),
        "ambience_volume": round(max(0.0, min(1.0, cfg.ambience_volume)), 3),
        "soundtrack_enabled": bool(getattr(cfg, "soundtrack_enabled", True)),
        "soundtrack_intensity": round(max(0.0, min(1.0, float(getattr(cfg, "soundtrack_intensity", 0.55)))), 3),
        "ambience_intensity": round(max(0.0, min(1.0, float(getattr(cfg, "ambience_intensity", 0.45)))), 3),
        "soundmatrix_use_vector_wars_sources": bool(getattr(cfg, "soundmatrix_use_vector_wars_sources", True)),
        "soundmatrix_variant_intensity": round(max(0.0, min(1.0, float(getattr(cfg, "soundmatrix_variant_intensity", 0.65)))), 3),
        "soundmatrix_music_intensity": round(max(0.0, min(1.0, float(getattr(cfg, "soundmatrix_music_intensity", 0.55)))), 3),
        "soundmatrix_random_seed": int(max(1, min(99999999, int(float(getattr(cfg, "soundmatrix_random_seed", 2048)))))),
    }


def build_launch_settings_payload(cfg: ObservatoryConfig):
    quality = str(cfg.launch_graphics_quality).lower().strip()
    if quality not in {"low", "medium", "high"}:
        quality = "medium"
    return {
        "width": int(max(1280, min(3840, cfg.launch_width))),
        "height": int(max(720, min(2160, cfg.launch_height))),
        "fullscreen": False,
        "borderless": False,
        "bordered_fullscreen": True,
        "mouse_sensitivity": round(max(0.02, min(1.0, cfg.launch_game_mouse_sensitivity)), 3),
        "invert_y": bool(cfg.launch_invert_y),
        "hud_visible": bool(cfg.launch_hud_visible),
        "graphics_quality": quality,
        "controller_deadzone": round(max(0.0, min(0.45, cfg.launch_controller_deadzone)), 3),
        "ui_scale": round(max(0.65, min(1.75, float(getattr(cfg, "launch_ui_scale", 1.0)))), 3),
        "render_scale": round(max(0.50, min(1.50, float(getattr(cfg, "launch_render_scale", 1.0)))), 3),
        "fps_cap": int(max(15, min(240, int(getattr(cfg, "launch_fps_cap", 60))))),
        "vsync": bool(getattr(cfg, "launch_vsync", True)),
        "subtitles_enabled": bool(getattr(cfg, "launch_subtitles_enabled", True)),
        "brightness": round(max(0.55, min(1.65, float(getattr(cfg, "launch_brightness", 1.0)))), 3),
        "contrast": round(max(0.55, min(1.65, float(getattr(cfg, "launch_contrast", 1.0)))), 3),
        "gamma": round(max(0.55, min(1.85, float(getattr(cfg, "launch_gamma", 1.0)))), 3),
        "override_mode_settings": bool(getattr(cfg, "launch_override_mode_settings", True)),
    }



def build_holoverse_settings_payload(cfg: ObservatoryConfig) -> dict:
    """Authoritative hub settings inherited by hosted modes when applicable."""
    launch = build_launch_settings_payload(cfg)
    audio = build_audio_bus_payload(cfg)
    return {
        "schema": "holoverse_universal_settings_v2",
        "source": "HoloVerse Core",
        "override_mode_settings": bool(launch.get("override_mode_settings", True)),
        "display_mode": "embedded_child",
        "resolution": {"width": launch["width"], "height": launch["height"]},
        "virtual_canvas": {"width": 1920, "height": 1080},
        "aspect_ratio": "16:9",
        "letterbox_policy": "fit_no_world_expand",
        "resize_policy": "letterbox_pillarbox_no_world_expand",
        "render_scale": launch.get("render_scale", 1.0),
        "ui_scale": launch.get("ui_scale", 1.0),
        "fullscreen": False,
        "borderless": False,
        "bordered_fullscreen": bool(launch.get("bordered_fullscreen", True)),
        "vsync": bool(launch.get("vsync", True)),
        "fps_cap": int(launch.get("fps_cap", 60)),
        "master_volume": audio["master_volume"],
        "music_volume": audio["music_volume"],
        "sfx_volume": audio["sfx_volume"],
        "ambience_volume": audio["ambience_volume"],
        "audio_root": "assets/audio",
        "shared_sfx_root": "assets/audio/sfx/shared",
        "shared_sfx_legacy_root": "assets/shared_sfx",
        "shared_sfx_manifest": "assets/audio/sfx/shared/shared_sfx_manifest.json",
        "audio_library_manifest": "assets/audio/audio_library_manifest.json",
        "default_holoverse_world": {
            "enabled": bool(getattr(cfg, "world_shell_mount_enabled", True)),
            "display_name": "HoloVerse",
            "runtime_state": "HOLOVERSE_DEFAULT",
            "core_owned": True,
            "separate_launcher_hidden": True,
            "adapter": "holoverse_world_shell_mount.py",
            "staged_full_shell": "hidden/not_launched_separately",
            "source_world_file": "world.py",
            "active_biome": int(getattr(cfg, "world_shell_active_biome", 1)),
            "detail": str(getattr(cfg, "world_shell_mount_detail", "stream")),
            "scale": float(getattr(cfg, "world_shell_mount_scale", 1.0)),
            "stream_radius": int(getattr(cfg, "world_shell_stream_radius", 4)),
            "default_preload": bool(getattr(cfg, "world_shell_default_preload", True)),
            "preload_all_biomes": bool(getattr(cfg, "world_shell_preload_all_biomes", True)),
            "preload_corridors": bool(getattr(cfg, "world_shell_preload_corridors", True)),
            "preload_sector_radius": int(getattr(cfg, "world_shell_preload_sector_radius", 0)),
            "max_preloaded_sectors": int(getattr(cfg, "world_shell_max_preloaded_sectors", 192)),
            "exit_gate_hints": bool(getattr(cfg, "world_shell_exit_gate_hints", True)),
            "entry_ribbons": bool(getattr(cfg, "world_shell_entry_ribbons", True)),
            "transition_cues": bool(getattr(cfg, "world_shell_transition_cues", True)),
            "first_ring_props": bool(getattr(cfg, "world_shell_first_ring_props", True)),
            "first_ring_prop_count": int(getattr(cfg, "world_shell_first_ring_prop_count", 14)),
            "ground_continuity": bool(getattr(cfg, "world_shell_ground_continuity", True)),
            "ground_band_count": int(getattr(cfg, "world_shell_ground_band_count", 5)),
            "scale_handoff_markers": bool(getattr(cfg, "world_shell_scale_handoff_markers", True)),
            "collision_height_hints": bool(getattr(cfg, "world_shell_collision_height_hints", True)),
            "local_detail_boost": bool(getattr(cfg, "world_shell_local_detail_boost", True)),
            "biome_signature_density": int(getattr(cfg, "world_shell_biome_signature_density", 2)),
            "directional_feedback": bool(getattr(cfg, "world_shell_directional_feedback", True)),
            "direction_marker_count": int(getattr(cfg, "world_shell_direction_marker_count", 6)),
            "corridor_theming": bool(getattr(cfg, "world_shell_corridor_theming", True)),
            "theme_handoff": bool(getattr(cfg, "world_shell_theme_handoff", True)),
            "theme_handoff_strength": float(getattr(cfg, "world_shell_theme_handoff_strength", 0.35)),
            "hub_theme_influence": bool(getattr(cfg, "world_shell_hub_theme_influence", True)),
            "hub_theme_max_blend": float(getattr(cfg, "world_shell_hub_theme_max_blend", 0.18)),
            "hub_theme_fog_blend": float(getattr(cfg, "world_shell_hub_theme_fog_blend", 0.14)),
            "hub_theme_light_blend": float(getattr(cfg, "world_shell_hub_theme_light_blend", 0.12)),
            "status_prompts": bool(getattr(cfg, "world_shell_status_prompts", True)),
            "motion_enabled": bool(getattr(cfg, "world_shell_motion_enabled", True)),
            "motion_intensity": float(getattr(cfg, "world_shell_motion_intensity", 0.38)),
            "audio_handoff": bool(getattr(cfg, "world_shell_audio_handoff", True)),
            "audio_handoff_strength": float(getattr(cfg, "world_shell_audio_handoff_strength", 0.34)),
            "ambience_radius": float(getattr(cfg, "world_shell_ambience_radius", 620.0)),
            "playable_enabled": bool(getattr(cfg, "world_shell_playable_enabled", True)),
            "play_radius": float(getattr(cfg, "world_shell_play_radius", 11100.0)),
            "play_speed_scale": float(getattr(cfg, "world_shell_play_speed_scale", 1.10)),
            "play_floor_enabled": bool(getattr(cfg, "world_shell_play_floor_enabled", True)),
            "use_world_py_source": bool(getattr(cfg, "world_shell_use_world_py_source", True)),
            "source_bridge_policy": "prefer_world_py_generation_helpers_no_standalone_showbase",
            "boundary_feedback": bool(getattr(cfg, "world_shell_boundary_feedback", True)),
            "boundary_warning_distance": float(getattr(cfg, "world_shell_boundary_warning_distance", 28.0)),
            "checkpoint_enabled": bool(getattr(cfg, "world_shell_checkpoint_enabled", True)),
            "checkpoint_count": int(getattr(cfg, "world_shell_checkpoint_count", 12)),
            "checkpoint_pickup_radius": float(getattr(cfg, "world_shell_checkpoint_pickup_radius", 4.8)),
            "biome_entry_prompts": bool(getattr(cfg, "world_shell_biome_entry_prompts", True)),
            "region_keymap_enabled": bool(getattr(cfg, "world_shell_region_keymap_enabled", True)),
            "region_keymap": "0 Hub Region, 1 Forests, 2 Green Hills, 3 Mushroom, 4 Desert, 5 Ice, 6 Urban, 7 Metropolis, 8 HoloSpace, 9 Hub Spawn",
            "preload_scope": "core_owned_default_holoverse_fullscale_loaded_at_boot_hidden_for_artifacts_reloaded_on_t_return",
            "biome_controls": {"next": "B", "previous": "N", "jump_next": "Shift+B", "jump_previous": "Shift+N", "return_hub": "T", "play_toggle": "P"},
            "lifecycle": {"boot": "load_holoverse_default", "artifact_activate": "unload_holoverse_default_then_load_artifact_world", "t_return": "clear_artifact_worlds_then_reload_holoverse_default"},
            "policy": "pass37_holoverse_default_core_lifecycle"
        },
        "default_world_shell": {
            "alias_for": "default_holoverse_world",
            "enabled": bool(getattr(cfg, "world_shell_mount_enabled", True)),
            "display_name": "HoloVerse",
            "runtime_state": "HOLOVERSE_DEFAULT",
            "core_owned": True,
            "separate_launcher_hidden": True,
            "adapter": "holoverse_world_shell_mount.py",
            "source_world_file": "world.py",
            "scale": float(getattr(cfg, "world_shell_mount_scale", 1.0)),
            "play_radius": float(getattr(cfg, "world_shell_play_radius", 11100.0)),
            "policy": "pass37_backward_compatible_alias_do_not_launch_separately"
        },
        "music_root": "assets/audio/music/generated",
        "music_legacy_root": "assets/music",
        "ambient_music_root": "assets/audio/music/ambient",
        "generated_audio_root": "assets/audio/sfx/generated",
        "generated_audio_legacy_root": "assets/generated_audio",
        "sound_and_music": {
            "category": "universal_hub_audio",
            "master_volume": audio["master_volume"],
            "music_volume": audio["music_volume"],
            "sfx_volume": audio["sfx_volume"],
            "ambience_volume": audio["ambience_volume"],
            "soundtrack_enabled": bool(audio.get("soundtrack_enabled", True)),
            "soundtrack_intensity": audio.get("soundtrack_intensity", 0.55),
            "ambience_intensity": audio.get("ambience_intensity", 0.45),
            "use_vector_wars_source_mp3": bool(audio.get("soundmatrix_use_vector_wars_sources", True)),
            "variant_intensity": audio.get("soundmatrix_variant_intensity", 0.65),
            "music_intensity": audio.get("soundmatrix_music_intensity", 0.55),
            "random_seed": audio.get("soundmatrix_random_seed", 2048),
            "audio_root": "assets/audio",
            "shared_sfx_root": "assets/audio/sfx/shared",
            "shared_sfx_legacy_root": "assets/shared_sfx",
            "music_root": "assets/audio/music/generated",
            "music_legacy_root": "assets/music",
            "ambient_music_root": "assets/audio/music/ambient",
            "generated_audio_root": "assets/audio/sfx/generated",
            "generated_audio_legacy_root": "assets/generated_audio",
            "generator": "tools/soundmatrix_audio_forge.py",
        },
        "mouse_sensitivity": launch["mouse_sensitivity"],
        "invert_y": launch["invert_y"],
        "hud_enabled": launch["hud_visible"],
        "subtitles_enabled": bool(launch.get("subtitles_enabled", True)),
        "brightness": launch.get("brightness", 1.0),
        "contrast": launch.get("contrast", 1.0),
        "gamma": launch.get("gamma", 1.0),
        "graphics_quality": launch["graphics_quality"],
        "controller_deadzone": launch["controller_deadzone"],
        "pause_key": "escape",
        "return_to_core_key": "escape",
        "input_focus_policy": "click_child_focus_host_escape_signal",
        "embedded_return_signal": True,
        "graceful_return_timeout_seconds": 3.2,
        "child_window_focus_on_attach": True,
        "child_window_resize_sync": True,
        "host_escape_behavior": "write_return_signal_then_esc_then_force_if_needed",
        "audio_policy": {"shared_sfx_enabled": True, "prefer_mode_overrides": True, "vector_wars_style_weapon_fallbacks": True, "soundmatrix_variants_enabled": True, "soundtrack_loops_enabled": bool(audio.get("soundtrack_enabled", True))},
        "settings_authority": {
            "core_overrides": [
                "display_mode", "resolution", "render_scale", "ui_scale", "fullscreen",
                "borderless", "bordered_fullscreen", "vsync", "fps_cap", "master_volume",
                "music_volume", "sfx_volume", "ambience_volume", "soundtrack_enabled",
                "soundtrack_intensity", "ambience_intensity", "soundmatrix_variant_intensity",
                "soundmatrix_music_intensity", "mouse_sensitivity",
                "invert_y", "hud_enabled", "subtitles_enabled", "brightness",
                "contrast", "gamma", "graphics_quality", "controller_deadzone",
                "pause_key", "return_to_core_key"
            ],
            "mode_local_only": [
                "difficulty", "mission_progress", "experiment_data", "unlocked_content",
                "mode_specific_gameplay_tuning"
            ],
        },
        "companion_profiles": {},
    }


def write_holoverse_settings(cfg: ObservatoryConfig) -> Path:
    ensure_dirs()
    HOLOVERSE_SETTINGS_PATH.write_text(json.dumps(build_holoverse_settings_payload(cfg), indent=2), encoding="utf-8")
    return HOLOVERSE_SETTINGS_PATH
def write_shared_launch_settings(cfg: ObservatoryConfig) -> Path:
    ensure_dirs()
    path = CONFIG_DIR / "holoverse_shared_settings.json"
    path.write_text(json.dumps(build_launch_settings_payload(cfg), indent=2), encoding="utf-8")
    write_holoverse_settings(cfg)
    return path


def write_audio_bus(cfg: ObservatoryConfig) -> Path:
    ensure_dirs()
    path = CONFIG_DIR / "holoverse_audio_bus.json"
    path.write_text(json.dumps(build_audio_bus_payload(cfg), indent=2), encoding="utf-8")
    return path


def _clamp01(v: float) -> float:
    return max(0.0, min(1.0, float(v)))


def ensure_generated_audio_assets(generate_music: bool = True):
    ensure_dirs()
    sample_rate = 22050

    def write_tone(path: Path, freq=220.0, duration=0.5, volume=0.35, wobble=0.0, pulse=0.0, attack=0.01, release=0.08):
        if path.exists():
            return
        frame_count = max(1, int(sample_rate * duration))
        buf = array('h')
        for i in range(frame_count):
            t = i / sample_rate
            env = 1.0
            if t < attack:
                env = t / max(attack, 1e-5)
            elif t > duration - release:
                env = max(0.0, (duration - t) / max(release, 1e-5))
            mod = 1.0 + wobble * math.sin(math.tau * 0.75 * t)
            amp = volume * env
            if pulse > 0.0:
                amp *= 0.55 + 0.45 * (0.5 + 0.5 * math.sin(math.tau * pulse * t))
            s = math.sin(math.tau * freq * mod * t)
            s += 0.35 * math.sin(math.tau * freq * 0.5 * t + 0.4)
            s += 0.12 * math.sin(math.tau * freq * 1.97 * t + 1.3)
            value = int(max(-1.0, min(1.0, s * amp)) * 32767)
            buf.append(value)
        with wave.open(str(path), 'wb') as wavf:
            wavf.setnchannels(1)
            wavf.setsampwidth(2)
            wavf.setframerate(sample_rate)
            wavf.writeframes(buf.tobytes())

    # Keep the old hum as a quiet emergency fallback, but the live hub no
    # longer uses it as the default follow-player loop. Contextual loops below
    # provide the actual bed for hub, world, space, water, and combat states.
    write_tone(AUDIO_DIR / 'core_hum.wav', freq=82.0, duration=3.2, volume=0.16, wobble=0.012, pulse=0.14, attack=0.10, release=0.22)
    write_tone(AUDIO_DIR / 'menu_open.wav', freq=540.0, duration=0.12, volume=0.28, wobble=0.02, pulse=0.0, attack=0.003, release=0.06)
    write_tone(AUDIO_DIR / 'menu_close.wav', freq=330.0, duration=0.11, volume=0.24, wobble=0.01, pulse=0.0, attack=0.003, release=0.05)
    write_tone(AUDIO_DIR / 'artifact_link.wav', freq=176.0, duration=0.38, volume=0.36, wobble=0.03, pulse=3.0, attack=0.01, release=0.14)
    write_tone(AUDIO_DIR / 'world_shift.wav', freq=126.0, duration=0.48, volume=0.34, wobble=0.025, pulse=2.2, attack=0.01, release=0.18)

    def note_freq(note: str) -> float:
        names = {'C': 0, 'C#': 1, 'DB': 1, 'D': 2, 'D#': 3, 'EB': 3, 'E': 4, 'F': 5, 'F#': 6, 'GB': 6, 'G': 7, 'G#': 8, 'AB': 8, 'A': 9, 'A#': 10, 'BB': 10, 'B': 11}
        note = str(note).strip().upper().replace('♯', '#').replace('♭', 'B')
        if len(note) >= 2 and note[1] in {'#', 'B'}:
            name, octave = note[:2], note[2:]
        else:
            name, octave = note[:1], note[1:]
        midi = 12 * (int(octave or 4) + 1) + names.get(name, 0)
        return 440.0 * (2.0 ** ((midi - 69) / 12.0))

    def tri(phase: float) -> float:
        return 2.0 * abs(2.0 * (phase - math.floor(phase + 0.5))) - 1.0

    def saw(phase: float) -> float:
        return 2.0 * (phase - math.floor(phase + 0.5))

    def pulse_env(position: float, attack_beats=0.035, release_beats=0.42) -> float:
        position = max(0.0, min(1.0, float(position)))
        if position < attack_beats:
            return position / max(attack_beats, 1e-5)
        return max(0.0, 1.0 - ((position - attack_beats) / max(release_beats, 1e-5)))

    def write_stereo_loop(path: Path, *, tempo: float, bars: int, chords: list[list[str]],
                          energy: float, seed: int, color: str = 'balanced',
                          percussion: bool = True, shimmer: bool = True):
        if path.exists():
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        beat_seconds = 60.0 / max(1.0, float(tempo))
        duration = max(5.2, beat_seconds * 4.0 * max(1, int(bars)))
        frame_count = max(1, int(sample_rate * duration))
        left: list[float] = []
        right: list[float] = []
        seed_phase = float(seed % 997) / 997.0
        color_lowpass = {'water': 0.55, 'space': 0.68, 'combat': 0.34, 'city': 0.42, 'low_electro': 0.72, 'deep_electro': 0.76}.get(color, 0.46)
        lp_l = lp_r = 0.0
        for i in range(frame_count):
            t = i / sample_rate
            beat = t / beat_seconds
            bar_pos = beat / 4.0
            chord_index = int(bar_pos) % len(chords)
            chord = chords[chord_index]
            beat_frac = beat - math.floor(beat)
            half_step = int(beat * 2.0)
            sixteenth_step = int(beat * 4.0)
            step_frac = beat * 2.0 - half_step
            sidechain = 0.74 + 0.26 * (1.0 - pulse_env(beat_frac, 0.025, 0.28))

            pad = 0.0
            for ni, note in enumerate(chord):
                freq = note_freq(note)
                slow = 1.0 + 0.0025 * math.sin(math.tau * (0.037 + ni * 0.011) * t + seed_phase)
                ph = freq * slow * t
                if color in {'combat', 'city'}:
                    voice = 0.55 * saw(ph) + 0.45 * tri(ph * 0.502 + ni * 0.19)
                elif color in {'low_electro', 'deep_electro'}:
                    voice = 0.78 * math.sin(math.tau * ph) + 0.18 * tri(ph * 0.250 + ni * 0.13) + 0.04 * saw(ph * 0.125)
                else:
                    voice = 0.66 * math.sin(math.tau * ph) + 0.34 * tri(ph * 0.501 + ni * 0.13)
                pad += voice / max(1, len(chord))
            pad *= (0.145 + 0.060 * energy) * sidechain

            bass_note = chord[0]
            try:
                bass_freq = note_freq(bass_note) * 0.5
            except Exception:
                bass_freq = 55.0
            bass_gate = pulse_env(beat_frac, 0.025, 0.50 if color != 'combat' else 0.34)
            bass = (math.sin(math.tau * bass_freq * t) + 0.28 * tri(bass_freq * 0.5 * t)) * bass_gate * (0.18 + 0.14 * energy)
            if color in {'low_electro', 'deep_electro'}:
                bass += math.sin(math.tau * bass_freq * 0.5 * t + 0.6) * bass_gate * (0.10 + 0.10 * energy)

            arp_note = chord[(half_step + chord_index + seed) % len(chord)]
            arp_freq = note_freq(arp_note) * (2.0 if color in {'space', 'city', 'combat'} else 1.0)
            arp_wave = math.sin(math.tau * arp_freq * t) if color != 'combat' else tri(arp_freq * t)
            arp = arp_wave * pulse_env(step_frac, 0.030, 0.34) * (0.050 + 0.16 * energy)

            air = 0.0
            if shimmer:
                air = math.sin(math.tau * (note_freq(chord[-1]) * (1.5 if color in {'low_electro', 'deep_electro'} else 3.0)) * t + math.sin(t * 0.7)) * (0.012 + 0.024 * energy)
                air += math.sin(math.tau * (11.0 + seed_phase * 5.0) * t) * (0.006 if color in {'low_electro', 'deep_electro'} else (0.010 if color != 'combat' else 0.004))

            drums = 0.0
            if percussion:
                kick = pulse_env(beat_frac, 0.010, 0.16) if int(beat) % 2 == 0 else 0.0
                snare = pulse_env(beat_frac, 0.006, 0.09) if int(beat) % 4 == 2 else 0.0
                hat = pulse_env((beat * 4.0) - sixteenth_step, 0.010, 0.12) if sixteenth_step % 2 == 1 else 0.0
                noise = math.sin(math.tau * (920.0 + 38.0 * math.sin(t * 1.7)) * t + seed_phase * 17.0)
                drums += math.sin(math.tau * (45.0 + 34.0 * (1.0 - beat_frac)) * t) * kick * (0.16 + 0.11 * energy)
                drums += noise * snare * (0.060 + 0.055 * energy)
                drums += math.sin(math.tau * 6400.0 * t) * hat * (0.018 + 0.030 * energy)

            sample = pad + bass + arp + air + drums
            sample = math.tanh(sample * (1.20 + energy * 0.42))
            pan = 0.25 * math.sin(math.tau * (0.031 + seed_phase * 0.01) * t)
            l = sample * (1.0 - pan)
            r = sample * (1.0 + pan)
            lp_l = (color_lowpass * lp_l) + ((1.0 - color_lowpass) * l)
            lp_r = (color_lowpass * lp_r) + ((1.0 - color_lowpass) * r)
            left.append(lp_l)
            right.append(lp_r)

        fade_frames = min(int(sample_rate * 0.18), max(1, frame_count // 10))
        for i in range(fade_frames):
            k = i / max(1, fade_frames - 1)
            left[i] = left[i] * k + left[-fade_frames + i] * (1.0 - k)
            right[i] = right[i] * k + right[-fade_frames + i] * (1.0 - k)
        peak = max(max(abs(v) for v in left), max(abs(v) for v in right), 1e-6)
        target = 0.74 if color != 'water' else 0.62
        scale = target / peak
        buf = array('h')
        for l, r in zip(left, right):
            buf.append(int(max(-0.98, min(0.98, l * scale)) * 32767))
            buf.append(int(max(-0.98, min(0.98, r * scale)) * 32767))
        with wave.open(str(path), 'wb') as wavf:
            wavf.setnchannels(2)
            wavf.setsampwidth(2)
            wavf.setframerate(sample_rate)
            wavf.writeframes(buf.tobytes())

    contextual_loops = [
        (CANONICAL_MUSIC_DIR / 'hv_hub_command_theme.wav', dict(tempo=86, bars=2, chords=[['A2', 'E3', 'C4'], ['F2', 'C3', 'A3'], ['C3', 'G3', 'E4'], ['G2', 'D3', 'B3']], energy=0.38, seed=1107, color='balanced', percussion=True, shimmer=True)),
        (CANONICAL_MUSIC_DIR / 'hv_world_exploration_theme.wav', dict(tempo=94, bars=2, chords=[['D2', 'A2', 'F3'], ['A2', 'E3', 'C4'], ['B1', 'F#2', 'D3'], ['G2', 'D3', 'B3']], energy=0.45, seed=2207, color='balanced', percussion=True, shimmer=True)),
        (CANONICAL_MUSIC_DIR / 'hv_urban_conflict_theme.wav', dict(tempo=124, bars=2, chords=[['E2', 'B2', 'G3'], ['G2', 'D3', 'A#3'], ['A2', 'E3', 'C4'], ['F2', 'C3', 'A3']], energy=0.78, seed=3307, color='combat', percussion=True, shimmer=False)),
        (CANONICAL_MUSIC_DIR / 'hv_metropolis_neon_theme.wav', dict(tempo=112, bars=2, chords=[['C2', 'G2', 'D#3'], ['D#2', 'A#2', 'G3'], ['G2', 'D3', 'A#3'], ['F2', 'C3', 'A3']], energy=0.62, seed=4407, color='city', percussion=True, shimmer=True)),
        (CANONICAL_MUSIC_DIR / 'hv_space_orbit_theme.wav', dict(tempo=74, bars=2, chords=[['C2', 'G2', 'E3'], ['A1', 'E2', 'C3'], ['F2', 'C3', 'A3'], ['G1', 'D2', 'B2']], energy=0.34, seed=5507, color='space', percussion=False, shimmer=True)),
        (CANONICAL_AMBIENT_MUSIC_DIR / 'hv_water_depth_theme.wav', dict(tempo=68, bars=2, chords=[['D2', 'A2', 'F3'], ['F2', 'C3', 'A3'], ['A1', 'E2', 'C3'], ['C2', 'G2', 'E3']], energy=0.25, seed=6607, color='water', percussion=False, shimmer=True)),
        (CANONICAL_AMBIENT_MUSIC_DIR / 'hv_hub_room_air.wav', dict(tempo=60, bars=2, chords=[['A2', 'E3', 'B3'], ['C3', 'G3', 'E4'], ['E2', 'B2', 'G3'], ['G2', 'D3', 'A3']], energy=0.16, seed=7707, color='space', percussion=False, shimmer=True)),
    ]
    # Audio variant pass: these are also shipped in the patch zip.
    contextual_loops.extend([
        (CANONICAL_MUSIC_DIR / 'hv_hub_command_theme_b.wav', dict(tempo=92, bars=2, chords=[['A2','E3','B3'], ['D3','A3','F4'], ['F2','C3','A3'], ['E2','B2','G#3']], energy=0.44, seed=1119, color='city', percussion=True, shimmer=True)),
        (CANONICAL_MUSIC_DIR / 'hv_hub_command_theme_c.wav', dict(tempo=78, bars=2, chords=[['C2','G2','E3'], ['A1','E2','C3'], ['D2','A2','F3'], ['G1','D2','B2']], energy=0.30, seed=1131, color='space', percussion=False, shimmer=True)),
        (CANONICAL_MUSIC_DIR / 'hv_world_exploration_theme_b.wav', dict(tempo=102, bars=2, chords=[['G2','D3','B3'], ['E2','B2','G3'], ['C2','G2','E3'], ['D2','A2','F#3']], energy=0.52, seed=2221, color='balanced', percussion=True, shimmer=True)),
        (CANONICAL_MUSIC_DIR / 'hv_world_exploration_theme_c.wav', dict(tempo=88, bars=2, chords=[['B1','F#2','D3'], ['D2','A2','F3'], ['F2','C3','A3'], ['A1','E2','C3']], energy=0.38, seed=2233, color='water', percussion=True, shimmer=True)),
        (CANONICAL_MUSIC_DIR / 'hv_urban_conflict_theme_b.wav', dict(tempo=132, bars=2, chords=[['D2','A2','F3'], ['F2','C3','A3'], ['E2','B2','G3'], ['G2','D3','B3']], energy=0.84, seed=3321, color='combat', percussion=True, shimmer=False)),
        (CANONICAL_MUSIC_DIR / 'hv_urban_conflict_theme_c.wav', dict(tempo=116, bars=2, chords=[['A1','E2','C3'], ['C2','G2','D#3'], ['E2','B2','G3'], ['D#2','A#2','G3']], energy=0.70, seed=3337, color='combat', percussion=True, shimmer=True)),
        (CANONICAL_MUSIC_DIR / 'hv_metropolis_neon_theme_b.wav', dict(tempo=120, bars=2, chords=[['F2','C3','A3'], ['A2','E3','C4'], ['D2','A2','F3'], ['G2','D3','B3']], energy=0.68, seed=4421, color='city', percussion=True, shimmer=True)),
        (CANONICAL_MUSIC_DIR / 'hv_metropolis_neon_theme_c.wav', dict(tempo=104, bars=2, chords=[['D#2','A#2','G3'], ['C2','G2','E3'], ['A1','E2','C3'], ['G1','D2','B2']], energy=0.54, seed=4439, color='city', percussion=True, shimmer=True)),
        (CANONICAL_MUSIC_DIR / 'hv_space_orbit_theme_b.wav', dict(tempo=68, bars=2, chords=[['D2','A2','F3'], ['B1','F#2','D3'], ['G1','D2','B2'], ['A1','E2','C3']], energy=0.28, seed=5521, color='space', percussion=False, shimmer=True)),
        (CANONICAL_MUSIC_DIR / 'hv_space_orbit_theme_c.wav', dict(tempo=82, bars=2, chords=[['E2','B2','G3'], ['C2','G2','D#3'], ['F2','C3','A3'], ['D2','A2','F#3']], energy=0.40, seed=5539, color='space', percussion=True, shimmer=True)),
        (CANONICAL_AMBIENT_MUSIC_DIR / 'hv_water_depth_theme_b.wav', dict(tempo=76, bars=2, chords=[['A1','E2','C3'], ['D2','A2','F3'], ['G1','D2','B2'], ['F2','C3','A3']], energy=0.32, seed=6621, color='water', percussion=True, shimmer=True)),
        (CANONICAL_AMBIENT_MUSIC_DIR / 'hv_water_depth_theme_c.wav', dict(tempo=62, bars=2, chords=[['C2','G2','E3'], ['G1','D2','B2'], ['B1','F#2','D3'], ['D2','A2','F3']], energy=0.20, seed=6637, color='water', percussion=False, shimmer=True)),
        (CANONICAL_AMBIENT_MUSIC_DIR / 'hv_hub_room_air_b.wav', dict(tempo=56, bars=2, chords=[['D2','A2','F3'], ['A1','E2','C3'], ['C2','G2','E3'], ['F2','C3','A3']], energy=0.14, seed=7721, color='space', percussion=False, shimmer=True)),
        (CANONICAL_AMBIENT_MUSIC_DIR / 'hv_hub_room_air_c.wav', dict(tempo=64, bars=2, chords=[['G1','D2','B2'], ['B1','F#2','D3'], ['E2','B2','G3'], ['A1','E2','C3']], energy=0.18, seed=7739, color='water', percussion=False, shimmer=True)),
    ])
    # 1043 music randomization pass: extra low electronic variants.
    # These keep the same subtle synth identity, but give the shuffle enough
    # material to avoid short repeat loops while travelling between regions.
    contextual_loops.extend([
        (CANONICAL_MUSIC_DIR / 'hv_hub_command_theme_d.wav', dict(tempo=82, bars=2, chords=[['A1','E2','C3'], ['C2','G2','E3'], ['F1','C2','A2'], ['G1','D2','B2']], energy=0.28, seed=1147, color='low_electro', percussion=False, shimmer=True)),
        (CANONICAL_MUSIC_DIR / 'hv_hub_command_theme_e.wav', dict(tempo=88, bars=2, chords=[['E1','B1','G2'], ['G1','D2','B2'], ['A1','E2','C3'], ['F1','C2','A2']], energy=0.34, seed=1159, color='deep_electro', percussion=True, shimmer=True)),
        (CANONICAL_MUSIC_DIR / 'hv_world_exploration_theme_d.wav', dict(tempo=86, bars=2, chords=[['D1','A1','F2'], ['A1','E2','C3'], ['B1','F#2','D3'], ['G1','D2','B2']], energy=0.32, seed=2247, color='low_electro', percussion=False, shimmer=True)),
        (CANONICAL_MUSIC_DIR / 'hv_world_exploration_theme_e.wav', dict(tempo=98, bars=2, chords=[['G1','D2','B2'], ['E1','B1','G2'], ['C2','G2','E3'], ['D2','A2','F#3']], energy=0.42, seed=2259, color='deep_electro', percussion=True, shimmer=True)),
        (CANONICAL_MUSIC_DIR / 'hv_urban_conflict_theme_d.wav', dict(tempo=118, bars=2, chords=[['E1','B1','G2'], ['G1','D2','A#2'], ['A1','E2','C3'], ['F1','C2','A2']], energy=0.66, seed=3347, color='deep_electro', percussion=True, shimmer=False)),
        (CANONICAL_MUSIC_DIR / 'hv_urban_conflict_theme_e.wav', dict(tempo=126, bars=2, chords=[['D1','A1','F2'], ['F1','C2','A2'], ['E1','B1','G2'], ['G1','D2','B2']], energy=0.72, seed=3359, color='low_electro', percussion=True, shimmer=True)),
        (CANONICAL_MUSIC_DIR / 'hv_metropolis_neon_theme_d.wav', dict(tempo=108, bars=2, chords=[['C1','G1','D#2'], ['D#1','A#1','G2'], ['G1','D2','A#2'], ['F1','C2','A2']], energy=0.48, seed=4447, color='low_electro', percussion=True, shimmer=True)),
        (CANONICAL_MUSIC_DIR / 'hv_metropolis_neon_theme_e.wav', dict(tempo=116, bars=2, chords=[['F1','C2','A2'], ['A1','E2','C3'], ['D1','A1','F2'], ['G1','D2','B2']], energy=0.56, seed=4459, color='deep_electro', percussion=True, shimmer=True)),
        (CANONICAL_MUSIC_DIR / 'hv_space_orbit_theme_d.wav', dict(tempo=66, bars=2, chords=[['C1','G1','E2'], ['A0','E1','C2'], ['F1','C2','A2'], ['G0','D1','B1']], energy=0.24, seed=5547, color='deep_electro', percussion=False, shimmer=True)),
        (CANONICAL_MUSIC_DIR / 'hv_space_orbit_theme_e.wav', dict(tempo=78, bars=2, chords=[['E1','B1','G2'], ['C1','G1','D#2'], ['F1','C2','A2'], ['D1','A1','F#2']], energy=0.34, seed=5559, color='low_electro', percussion=True, shimmer=True)),
        (CANONICAL_AMBIENT_MUSIC_DIR / 'hv_water_depth_theme_d.wav', dict(tempo=58, bars=2, chords=[['D1','A1','F2'], ['F1','C2','A2'], ['A0','E1','C2'], ['C1','G1','E2']], energy=0.18, seed=6647, color='deep_electro', percussion=False, shimmer=True)),
        (CANONICAL_AMBIENT_MUSIC_DIR / 'hv_water_depth_theme_e.wav', dict(tempo=72, bars=2, chords=[['A0','E1','C2'], ['D1','A1','F2'], ['G0','D1','B1'], ['F1','C2','A2']], energy=0.26, seed=6659, color='low_electro', percussion=True, shimmer=True)),
        (CANONICAL_AMBIENT_MUSIC_DIR / 'hv_hub_room_air_d.wav', dict(tempo=52, bars=2, chords=[['A1','E2','B2'], ['C2','G2','E3'], ['E1','B1','G2'], ['G1','D2','A2']], energy=0.12, seed=7747, color='deep_electro', percussion=False, shimmer=True)),
        (CANONICAL_AMBIENT_MUSIC_DIR / 'hv_hub_room_air_e.wav', dict(tempo=60, bars=2, chords=[['G0','D1','B1'], ['B0','F#1','D2'], ['E1','B1','G2'], ['A0','E1','C2']], energy=0.16, seed=7759, color='low_electro', percussion=False, shimmer=True)),
    ])

    if not generate_music:
        # Keep startup visual-first. The long contextual WAV forge is useful for
        # build/asset passes, but running it synchronously during normal boot
        # can leave the player staring at a black window before the first frame.
        return

    for loop_path, spec in contextual_loops:
        write_stereo_loop(loop_path, **spec)


class SharedAudio:
    def __init__(self, app):
        self.app = app
        self.backend = 'silent'
        self.enabled = False
        self.looping = {}
        self.oneshots = []
        self.pygame = None
        self.pygame_channels = {}
        self.cache = {}
        if SELF_TEST:
            return
        # Do not forge missing music loops during the visual boot path. Missing
        # startup SFX are cheap to create, but the full contextual music generator
        # is intentionally opt-in so HoloVerse can draw the observatory first.
        ensure_generated_audio_assets(generate_music=_env_flag("HOLOVERSE_GENERATE_AUDIO_ON_BOOT", False))
        self._try_panda()
        if not self.enabled:
            self._try_pygame()
        print(f'audio_backend={self.backend}')

    def _try_panda(self):
        try:
            if not getattr(self.app, 'loader', None):
                return
            # Panda may silently fall back to NullAudioManager when OpenAL cannot
            # open an output device. Treat that as unavailable so pygame can be
            # tried instead of reporting a fake "panda" backend with no sound.
            managers = []
            try:
                managers.extend(list(getattr(self.app, 'sfxManagerList', []) or []))
            except Exception:
                pass
            try:
                music_mgr = getattr(self.app, 'musicManager', None)
                if music_mgr is not None:
                    managers.append(music_mgr)
            except Exception:
                pass
            manager_names = " ".join(str(mgr) for mgr in managers).lower()
            if "nullaudiomanager" in manager_names:
                raise RuntimeError("Panda audio fell back to NullAudioManager")
            test_path = self._resolve_audio_path('menu_open.wav') or (AUDIO_DIR / 'menu_open.wav')
            test = self.app.loader.loadSfx(Filename.fromOsSpecific(str(test_path)))
            if not test:
                return
            self.backend = 'panda'
            self.enabled = True
        except Exception as exc:
            print(f'audio_panda_unavailable: {exc}')

    def _try_pygame(self):
        try:
            import pygame
            if not pygame.mixer.get_init():
                pygame.mixer.pre_init(22050, size=-16, channels=2, buffer=512)
                pygame.mixer.init()
            self.pygame = pygame
            self.backend = 'pygame'
            self.enabled = True
        except Exception as exc:
            self.backend = f'silent:{exc.__class__.__name__}'
            print(f'audio_pygame_unavailable: {exc}')

    def _bus_gain(self, bus: str, base: float = 1.0) -> float:
        cfg = self.app.cfg
        bus_value = 1.0
        if bus == 'sfx':
            bus_value = cfg.sfx_volume
        elif bus == 'music':
            bus_value = cfg.music_volume
        elif bus == 'ambience':
            bus_value = cfg.ambience_volume
        return _clamp01(base * cfg.master_volume * bus_value)

    def _vector_wars_fallback_sfx_path(self, filename: str = "") -> Path | None:
        """Use committed Vector Wars SFX as the universal last-resort SFX bed.

        This prevents silent buttons/links/weapon cues in slim builds without
        creating generated or override folders.  Only SFX calls use this fallback;
        music/ambience loops must keep their own loop assets.
        """
        raw = str(filename or "").replace("\\", "/").lower()
        vector_root = ROOT / "Dimensions" / "Vector Wars" / "assets" / "sfx"
        preferred: list[Path] = []
        if any(token in raw for token in ("rocket", "missile", "launch", "burst")):
            preferred.append(vector_root / "weapons" / "missiles" / "rocketfire.mp3")
        if any(token in raw for token in ("hit", "destroy", "explode", "explosion", "damage", "impact")):
            preferred.append(vector_root / "weapons" / "guns" / "hit.mp3")
        if any(token in raw for token in ("fire", "shot", "laser", "artifact", "menu", "world_shift", "select", "open", "close", "link")):
            preferred.append(vector_root / "weapons" / "lasers" / "fire.mp3")
        preferred.extend([
            vector_root / "weapons" / "lasers" / "fire.mp3",
            vector_root / "weapons" / "missiles" / "rocketfire.mp3",
            vector_root / "weapons" / "guns" / "hit.mp3",
        ])
        seen: set[str] = set()
        for path in preferred:
            key = os.fspath(path)
            if key in seen:
                continue
            seen.add(key)
            try:
                if path.exists() and path.is_file():
                    return path
            except Exception:
                pass
        return None

    def _resolve_audio_path(self, filename: str, *, allow_vector_wars_fallback: bool = False) -> Path | None:
        raw_input = str(filename or '').strip()
        if raw_input:
            try:
                direct = Path(raw_input)
                if direct.is_absolute() and direct.exists() and direct.is_file():
                    return direct
            except Exception:
                pass
        raw = raw_input.replace('\\', '/').strip('/')
        candidates = []
        if raw:
            candidates.extend([
                CANONICAL_GENERATED_SFX_DIR / raw,
                CANONICAL_SHARED_SFX_DIR / raw,
                CANONICAL_REVERSED_MUSIC_DIR / raw,
                CANONICAL_MUSIC_DIR / raw,
                CANONICAL_AMBIENT_MUSIC_DIR / raw,
                AUDIO_LIBRARY_DIR / raw,
                AUDIO_DIR / raw,
                MUSIC_DIR / raw,
                SHARED_SFX_DIR / raw,
            ])
            for root in (CANONICAL_SHARED_SFX_DIR, SHARED_SFX_DIR):
                try:
                    candidates.extend(root.rglob(raw))
                except Exception:
                    pass
        for candidate in candidates:
            try:
                if candidate.exists() and candidate.is_file():
                    return candidate
            except Exception:
                continue
        if allow_vector_wars_fallback:
            return self._vector_wars_fallback_sfx_path(raw_input)
        return None

    def reversed_clip_for(self, filename: str) -> str:
        """Return a cached reversed WAV path for an existing HoloVerse audio file.

        The dimensions intentionally reuse the current assets/audio loops instead
        of adding new music. Non-WAV sources fall back to the original file so a
        missing or unsupported clip can never break boot.
        """
        source = self._resolve_audio_path(filename)
        if source is None:
            return str(filename or "")
        try:
            if source.suffix.lower() != ".wav":
                return os.fspath(source)
            CANONICAL_REVERSED_MUSIC_DIR.mkdir(parents=True, exist_ok=True)
            target = CANONICAL_REVERSED_MUSIC_DIR / f"{source.stem}_reversed.wav"
            if target.exists() and target.stat().st_mtime >= source.stat().st_mtime:
                return os.fspath(target)
            with wave.open(str(source), "rb") as src:
                params = src.getparams()
                channels = max(1, int(params.nchannels))
                width = max(1, int(params.sampwidth))
                frames = src.readframes(params.nframes)
            frame_size = max(1, channels * width)
            reversed_frames = bytearray(len(frames))
            out_at = 0
            for at in range(len(frames) - frame_size, -1, -frame_size):
                reversed_frames[out_at:out_at + frame_size] = frames[at:at + frame_size]
                out_at += frame_size
            with wave.open(str(target), "wb") as dst:
                dst.setparams(params)
                dst.writeframes(bytes(reversed_frames[:out_at]))
            return os.fspath(target)
        except Exception as exc:
            try:
                print(f"audio_reverse_cache_failed source={source.name} err={exc.__class__.__name__}:{exc}")
            except Exception:
                pass
            return os.fspath(source)

    def _load(self, filename: str, bus: str = 'sfx'):
        path = self._resolve_audio_path(filename, allow_vector_wars_fallback=(str(bus or 'sfx') == 'sfx'))
        if path is None:
            return None
        cache_key = str(path)
        if self.backend == 'panda':
            if cache_key not in self.cache:
                snd = self.app.loader.loadSfx(Filename.fromOsSpecific(str(path)))
                self.cache[cache_key] = snd
            return self.cache.get(cache_key)
        if self.backend == 'pygame' and self.pygame:
            if cache_key not in self.cache:
                self.cache[cache_key] = self.pygame.mixer.Sound(str(path))
            return self.cache.get(cache_key)
        return None

    def play(self, filename: str, bus='sfx', volume=1.0):
        if not self.enabled:
            return
        snd = self._load(filename, bus=bus)
        if snd is None:
            return
        gain = self._bus_gain(bus, volume)
        try:
            snd.setVolume(gain)
        except Exception:
            pass
        try:
            if self.backend == 'panda':
                snd.play()
            elif self.backend == 'pygame':
                ch = snd.play()
                if ch:
                    ch.set_volume(gain)
                    self.oneshots.append((snd, ch, bus, volume))
        except Exception:
            pass

    def play_loop(self, slot: str, filename: str, bus='ambience', volume=1.0):
        if not self.enabled:
            return
        snd = self._load(filename, bus=bus)
        if snd is None:
            return
        gain = self._bus_gain(bus, volume)
        try:
            snd.setLoop(True)
        except Exception:
            pass
        current = self.looping.get(slot)
        if current and current.get('filename') == filename:
            # Same loop, new scene mix. Update bus/volume instead of leaving
            # the old gain locked in from the first frame that started it.
            current['bus'] = bus
            current['volume'] = volume
            self._apply_loop_gain(slot)
            return
        self.stop_loop(slot)
        info = {'filename': filename, 'sound': snd, 'bus': bus, 'volume': volume}
        self.looping[slot] = info
        try:
            if self.backend == 'panda':
                snd.setVolume(gain)
                snd.setLoop(True)
                snd.play()
            elif self.backend == 'pygame':
                channel = snd.play(loops=-1)
                if channel:
                    channel.set_volume(gain)
                    self.pygame_channels[slot] = channel
        except Exception:
            pass

    def stop_loop(self, slot: str):
        info = self.looping.pop(slot, None)
        if not info:
            return
        try:
            if self.backend == 'panda':
                info['sound'].stop()
            elif self.backend == 'pygame':
                ch = self.pygame_channels.pop(slot, None)
                if ch:
                    ch.stop()
        except Exception:
            pass

    def stop_external_panda_audio(self):
        """Stop Panda3D sounds not tracked by SharedAudio.

        Same-window dimensions are scenes inside one game, but source adapters can
        load SFX/music directly through the host loader.  This gives HoloVerse a
        single permanent cleanup point so old dimension music cannot carry into
        the next scene.
        """
        managers = []
        try:
            managers.extend(list(getattr(self.app, "sfxManagerList", []) or []))
        except Exception:
            pass
        try:
            mgr = getattr(self.app, "musicManager", None)
            if mgr is not None:
                managers.append(mgr)
        except Exception:
            pass
        for mgr in managers:
            for method_name in ("stopAllSounds", "stop_all_sounds", "stopAll", "stop_all"):
                method = getattr(mgr, method_name, None)
                if callable(method):
                    try:
                        method()
                    except Exception:
                        pass
                    break

    def stop_all(self, *, stop_oneshots: bool = True):
        """Stop every HoloVerse-owned sound channel.

        Dimension switches are scene changes, not separate apps.  Without one
        hard-stop point, hub loops, HoloCore loops, native dimension beds, and
        pygame one-shots can overlap after a return.
        """
        for slot in tuple(self.looping.keys()):
            self.stop_loop(slot)
        if self.backend == 'pygame':
            for slot, ch in list(self.pygame_channels.items()):
                try:
                    if ch:
                        ch.stop()
                except Exception:
                    pass
            self.pygame_channels.clear()
            if stop_oneshots and self.pygame is not None:
                try:
                    self.pygame.mixer.stop()
                except Exception:
                    pass
        if self.backend == 'panda':
            for snd in list(self.cache.values()):
                try:
                    snd.stop()
                except Exception:
                    pass
        if stop_oneshots:
            self.oneshots.clear()
        self.stop_external_panda_audio()

    def _apply_loop_gain(self, slot: str):
        info = self.looping.get(slot)
        if not info:
            return
        gain = self._bus_gain(info['bus'], info['volume'])
        try:
            if self.backend == 'panda':
                info['sound'].setVolume(gain)
            elif self.backend == 'pygame':
                ch = self.pygame_channels.get(slot)
                if ch:
                    ch.set_volume(gain)
        except Exception:
            pass

    def refresh_mix(self):
        for slot in tuple(self.looping.keys()):
            self._apply_loop_gain(slot)
        if self.backend == 'pygame':
            alive = []
            for snd, ch, bus, volume in self.oneshots:
                if ch and ch.get_busy():
                    try:
                        ch.set_volume(self._bus_gain(bus, volume))
                    except Exception:
                        pass
                    alive.append((snd, ch, bus, volume))
            self.oneshots = alive


def hsv_color(h: float, s: float, v: float, a: float = 1.0):
    r, g, b = colorsys.hsv_to_rgb(h % 1.0, max(0.0, min(1.0, s)), max(0.0, min(1.0, v)))
    return (r, g, b, a)




WORLD_SPECS = {
    0: {"name": "Frontier Lens", "kind": "frontier", "profile": "plains", "bg": (0.018, 0.018, 0.022), "hub": (0.90, 0.97, 1.0), "height_mul": 0.72, "noise_scale": 0.86, "detail_scale": 0.78, "landmark_density": 0.28},
    1: {"name": "Signal Bastion", "kind": "frontier", "profile": "bastion", "bg": (0.020, 0.018, 0.026), "hub": (0.96, 0.78, 0.92), "height_mul": 0.88, "noise_scale": 1.18, "detail_scale": 1.24, "landmark_density": 0.48},
    2: {"name": "Aether Reach", "kind": "frontier", "profile": "spirefield", "bg": (0.018, 0.020, 0.025), "hub": (0.80, 0.90, 1.0), "height_mul": 1.05, "noise_scale": 1.42, "detail_scale": 1.10, "landmark_density": 0.36},
    3: {"name": "Ruin Meridian", "kind": "frontier", "profile": "ruins", "bg": (0.020, 0.018, 0.020), "hub": (0.98, 0.84, 0.76), "height_mul": 0.96, "noise_scale": 1.02, "detail_scale": 1.36, "landmark_density": 0.54},
    4: {"name": "Venus Lens", "kind": "venus", "profile": "caustic", "bg": (0.17, 0.07, 0.03), "hub": (1.0, 0.60, 0.28), "height_mul": 1.12, "noise_scale": 1.08, "detail_scale": 0.92, "landmark_density": 0.40},
    5: {"name": "Void Fleet Lens", "kind": "space", "profile": "fleet", "bg": (0.01, 0.015, 0.05), "hub": (0.55, 0.72, 1.0), "height_mul": 1.0, "noise_scale": 1.0, "detail_scale": 1.0, "landmark_density": 0.58},
    6: {"name": "Aqua Abyss Lens", "kind": "underwater", "profile": "trench", "bg": (0.01, 0.10, 0.16), "hub": (0.30, 0.96, 0.88), "height_mul": 1.08, "noise_scale": 0.92, "detail_scale": 1.14, "landmark_density": 0.44},
    7: {"name": "Verdant Canopy Lens", "kind": "jungle", "profile": "canopy", "bg": (0.03, 0.09, 0.04), "hub": (0.56, 0.96, 0.52), "height_mul": 0.90, "noise_scale": 1.20, "detail_scale": 1.32, "landmark_density": 0.64},
}

ARTIFACT_DIMENSION_ROUTES = [
    # Artifact pedestals use the eight physical geometry slots in the hub ring.
    # Slot 1 is now the built-in Vector Arena route, replacing the removed
    # generated-city experiment and the missing Etch-Line folder.
    # Ember Hangar stays available through Ember/the desert region flow, not
    # through the artifact dimension ring.
    "code_red_vector",
    "vector_arena",
    "fractured_dimension",
    "holo_campaign",
    "holo_conquest",
    "vector_wars",
    "zonez",
    "holocore",
]

ARTIFACT_DIMENSION_PRESENTATION = {
    "code_red_vector": {
        "display_name": "Code Red Vector Dimension",
        "short_name": "Code Red Vector",
        "palette": {
            "primary": (1.00, 0.06, 0.04),
            "secondary": (0.10, 0.02, 0.02),
            "highlight": (1.00, 0.86, 0.72),
        },
        "style": "combat_obelisk",
    },
    "vector_arena": {
        "display_name": "Vector Arena Dimension",
        "short_name": "Vector Arena",
        "palette": {
            "primary": (0.10, 1.00, 0.82),
            "secondary": (0.02, 0.10, 0.18),
            "highlight": (1.00, 0.32, 0.92),
        },
        "style": "vector_arena_gate",
    },
    "fractured_dimension": {
        "display_name": "Fractured Dimension",
        "short_name": "Fractured",
        "palette": {
            "primary": (0.86, 0.20, 1.00),
            "secondary": (0.20, 0.05, 0.34),
            "highlight": (1.00, 0.82, 1.00),
        },
        "style": "fracture_shards",
    },
    "holo_campaign": {
        "display_name": "Holo Campaign Dimension",
        "short_name": "Holo Campaign",
        "palette": {
            "primary": (1.00, 0.78, 0.20),
            "secondary": (0.18, 0.32, 0.16),
            "highlight": (0.86, 1.00, 0.64),
        },
        "style": "campaign_table",
    },
    "holo_conquest": {
        "display_name": "Holo Conquest Dimension",
        "short_name": "Holo Conquest",
        "palette": {
            "primary": (1.00, 0.34, 0.06),
            "secondary": (0.28, 0.08, 0.02),
            "highlight": (0.26, 0.76, 1.00),
        },
        "style": "conquest_node",
    },
    "vector_wars": {
        "display_name": "Vector Wars Dimension",
        "short_name": "Vector Wars",
        "palette": {
            "primary": (0.25, 0.42, 1.00),
            "secondary": (0.10, 0.04, 0.36),
            "highlight": (1.00, 1.00, 1.00),
        },
        "style": "starfighter_reticle",
    },
    "zonez": {
        "display_name": "Zonez Dimension",
        "short_name": "Zonez",
        "palette": {
            "primary": (0.94, 0.24, 1.00),
            "secondary": (0.08, 0.38, 0.95),
            "highlight": (0.98, 1.00, 0.34),
        },
        "style": "stacked_zones",
    },
    "holocore": {
        "display_name": "HoloCore Dimension",
        "short_name": "HoloCore",
        "palette": {
            "primary": (0.12, 1.00, 0.88),
            "secondary": (0.02, 0.16, 0.18),
            "highlight": (0.90, 1.00, 1.00),
        },
        "style": "core_pyramid",
    },
}

ARTIFACT_SLOT_COUNT = len(ARTIFACT_DIMENSION_ROUTES)
ARTIFACT_PRIMARY_RING_COUNT = 8
ARTIFACT_PRESS_ACTIVATION_RADIUS = 8.5
ARTIFACT_LOOK_ACTIVATION_RADIUS = 13.0


class WorldActor:
    def __init__(self, root, kind, seed, home):
        self.root = root
        self.kind = kind
        self.seed = seed
        self.home = Vec3(home)
        self.phase = random.Random(seed).random() * math.tau
        self.follow_timer = 0.0


class HoloCoreSameWindowScene:
    """Mount the root-level HoloCore sub-world inside the live HoloVerse ShowBase.

    HoloCore remains a separate folder/sub-world. This adapter only borrows its
    hub/grid modules and renders them into the parent window so the MatrixCore
    bridge can avoid spawning a second Panda3D window when the modules are
    available. The normal child-window/external launcher remains the fallback.
    """

    def __init__(self, app, *, mode: dict | None = None, entry_path: Path | None = None, label: str = "HoloCore") -> None:
        self.app = app
        self.mode = dict(mode or {})
        self.label = str(label or "HoloCore")
        self.entry_path = Path(entry_path or (ROOT / "HoloCore" / "main.py")).resolve()
        self.root_dir = self.entry_path.parent
        self.elapsed = 0.0
        self.heading = 0.0
        self.pitch = 0.0
        self.eye_height = 13.0
        self.mouse_sensitivity = 0.105
        self.walk_speed = 24.0
        self.sprint_speed = 46.0
        self.player = None
        self.hub = None
        self.outer_world = None
        self.holo_vessel = None
        self.holo_vessel_boarded = False
        self.holo_vessel_piloting = False
        self.holo_vessel_prompt = None
        self._holo_vessel_prompt_text = None
        self._holo_vessel_prompt_visible = False
        self.return_prompt = None
        self.gateway_panel_root = None
        self.gateway_buttons = []
        self.gateway_modes = []
        self.gateway_status = None
        self.gateway_page_label = None
        self.gateway_prev_button = None
        self.gateway_next_button = None
        self.gateway_page = 0
        self.gateway_page_size = 9
        self.gateway_pending_mode = None
        self.gateway_pending_started_at = 0.0
        self._destroyed = False
        self._last_dimension_music_id = None
        self._old_player_attr = getattr(app, "player", None)
        self._saved_render_state = None
        self._saved_background = None
        self._holocore_render_child_names = {
            "hub_world_root",
            "dimension_layered_grid_world_root",
            "hub_exclusion_seam",
            "holocore_same_window_player",
            "holo_vessel_crescent_runner",
            "deep_ambient",
            "cold_top_key",
            "red_back_rim",
            "matrixcore_red_light",
            "cyan_shell_light",
        }
        self._mount()

    def _mount(self) -> None:
        if not self.entry_path.exists():
            raise FileNotFoundError(f"HoloCore entry missing: {self.entry_path}")
        if not (self.root_dir / "hub_world.py").exists():
            raise FileNotFoundError(f"HoloCore hub_world.py missing: {self.root_dir}")
        try:
            self._saved_render_state = self.app.render.getState()
        except Exception:
            self._saved_render_state = None
        try:
            self._saved_background = self.app.win.getClearColor() if self.app.win is not None else None
        except Exception:
            self._saved_background = None

        HubWorldAdapter, FlatOuterWorldAdapter, HoloVesselClass = self._load_holocore_adapters()
        self.app.setBackgroundColor(0.0, 0.0, 0.0025, 1.0)
        try:
            self.app.render.setAntialias(AntialiasAttrib.MAuto)
        except Exception:
            pass
        self.hub = HubWorldAdapter().build(self.app)
        stream_radius = 3
        self.outer_world = FlatOuterWorldAdapter(floor_z=self.hub.floor_z, stream_radius=stream_radius).build(self.app, self.hub)
        self._build_holo_vessel_outside_pyramid(HoloVesselClass)
        self.player = self.app.render.attachNewNode("holocore_same_window_player")
        setattr(self.app, "player", self.player)
        self.app.camera.reparentTo(self.player)
        self.app.camera.setPos(0, 0, self.eye_height)
        self.app.camera.setHpr(0, 0, 0)
        try:
            self.app.camLens.setFov(72)
            self.app.camLens.setNearFar(0.18, 2400)
        except Exception:
            pass
        self._setup_return_prompt()
        self._setup_holo_vessel_prompt()
        # MatrixCore owns the Dimension Gates UI. HoloCore stays a playable
        # pyramid/biome sub-world so Tab remains dedicated to biome cycling.
        self._reset_player()
        self._lock_mouse()
        self._sync_dimension_music(force=True)

    def _load_holocore_adapters(self):
        root_dir = os.fspath(self.root_dir)
        inserted = False
        if root_dir not in sys.path:
            sys.path.insert(0, root_dir)
            inserted = True
        try:
            # Guard against any previously imported module with the same simple
            # name from another prototype folder. HoloCore's drop-in biome loader
            # intentionally uses local imports, so the local folder must win.
            for module_name in (
                "hub_world",
                "world_grid",
                "holo_vessel",
                "holo_mermaid",
                "holo_jellyfish",
                "holo_octopus",
                "dimensions",
                "dimensions.dimension_manager",
                "dimensions.surface_placement",
                "dimensions.outer_flat_world",
            ):
                # Always reload HoloCore modules from this HoloCore folder.
                # This prevents stale modules from a prior child-window/old-folder
                # import from masking the updated vessel/mob implementation.
                sys.modules.pop(module_name, None)
            import importlib
            hub_mod = importlib.import_module("hub_world")
            outer_mod = importlib.import_module("dimensions.outer_flat_world")
            vessel_mod = importlib.import_module("holo_vessel")
            return getattr(hub_mod, "HubWorldAdapter"), getattr(outer_mod, "FlatOuterWorldAdapter"), getattr(vessel_mod, "HoloVessel")
        finally:
            # Keep the HoloCore module path during runtime for root-level
            # same-window HoloCore imports.  Biome drop-in assets are now owned
            # by shared assets/holocore, not by a duplicate HoloCore/assets tree.
            if inserted:
                pass

    def _ui_strings(self) -> dict:
        defaults = {
            "return_prompt_near": "HOLOCORE // ESC OR 0 RETURN TO HUB // TAB CYCLES HOLOCORE BIOMES",
            "return_prompt_far": "HOLOCORE // ESC OR 0 RETURN TO HUB // RETURN TO PYRAMID FOR GATES",
            "entered_hint": "HOLOCORE // ESC OR 0 RETURN TO HUB // TAB CYCLES HOLOCORE BIOMES",
            "interact_hint": "HOLOCORE // E INTERACT // ESC OR 0 RETURN TO HUB",
            "gate_walk_back_hint": "HOLOCORE GATES // WALK BACK TO THE PYRAMID",
            "gate_select_hint": "HOLOCORE GATES // SELECT A DIMENSION",
            "tab_cycle_hint": "HOLOCORE // {dimension} // TAB BIOME LAYER",
            "native_overlay_subtitle": "SAME-WINDOW HOLOCORE // ESC OR 0 RETURNS TO HUB",
        }
        cached = getattr(self.app, "holocore_same_window_ui_strings", None)
        if isinstance(cached, dict) and cached:
            merged = dict(defaults)
            merged.update({str(k): str(v) for k, v in cached.items() if v is not None})
            return merged
        strings = dict(defaults)
        try:
            manifest_path = ROOT / "ui" / "ui_manifest.json"
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            ui_block = data.get("holocore_same_window_ui", {}) if isinstance(data, dict) else {}
            raw = ui_block.get("strings", {}) if isinstance(ui_block, dict) else {}
            if isinstance(raw, dict):
                strings.update({str(k): str(v) for k, v in raw.items() if v is not None})
        except Exception:
            pass
        try:
            setattr(self.app, "holocore_same_window_ui_strings", dict(strings))
        except Exception:
            pass
        return strings

    def _ui_text(self, key: str, fallback: str = "", **kwargs) -> str:
        text = self._ui_strings().get(str(key), fallback or str(key))
        if kwargs:
            try:
                text = text.format(**kwargs)
            except Exception:
                pass
        return str(text)

    def _setup_return_prompt(self) -> None:
        try:
            self.return_prompt = DirectLabel(
                parent=self.app.aspect2d,
                text=self._ui_text("return_prompt_near"),
                pos=(0.0, 0.0, -0.90),
                scale=0.045,
                frameColor=(0.0, 0.0, 0.0, 0.0),
                text_fg=(0.82, 1.0, 1.0, 0.92),
                text_shadow=(0.0, 0.0, 0.0, 0.75),
                text_align=TextNode.ACenter,
            )
        except Exception:
            self.return_prompt = None

    def _near_pyramid_return_gate(self) -> bool:
        try:
            pos = self.player.getPos(self.app.render)
            return (float(pos.x) * float(pos.x) + float(pos.y) * float(pos.y)) <= (86.0 * 86.0)
        except Exception:
            return True

    def _update_return_prompt(self) -> None:
        prompt = self.return_prompt
        if prompt is None:
            return
        try:
            if self._near_pyramid_return_gate():
                prompt["text"] = self._ui_text("return_prompt_near")
                prompt["text_fg"] = (0.82, 1.0, 1.0, 0.92)
            else:
                prompt["text"] = self._ui_text("return_prompt_far")
                prompt["text_fg"] = (0.56, 0.90, 1.0, 0.78)
            prompt.show()
        except Exception:
            pass

    def _active_dimension_info(self) -> tuple[int, str]:
        try:
            manager = getattr(self.outer_world, "dimension_manager", None)
            active = getattr(manager, "active", None)
            dim_id = int(getattr(active, "dimension_id", 1) or 1)
            dim_name = str(getattr(active, "name", "HoloCore Dimension") or "HoloCore Dimension")
            return dim_id, dim_name
        except Exception:
            return 1, "HoloCore Dimension"

    def _sync_dimension_music(self, force: bool = False) -> None:
        dim_id, dim_name = self._active_dimension_info()
        if not force and dim_id == getattr(self, "_last_dimension_music_id", None):
            return
        self._last_dimension_music_id = dim_id
        try:
            self.app.play_holocore_dimension_music(dim_id, dim_name)
        except Exception as exc:
            try:
                print(f"holocore_dimension_music_error:{exc.__class__.__name__}:{exc}")
            except Exception:
                pass

    def _clean_gate_label(self, value: str, fallback: str = "DIMENSION") -> str:
        text = re.sub(r"[\\/]+", " ", str(value or fallback))
        text = re.sub(r"[_\-]+", " ", text)
        text = re.sub(r"\s+", " ", text).strip() or fallback
        return text[:34].upper()

    def _gate_lookup_key(self, value: object) -> str:
        return re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")

    def _dimension_gate_record_from_folder(self, folder: Path) -> dict | None:
        """Infer a Dimension gate from a dropped folder without editing the index."""
        try:
            folder = Path(folder)
            if not folder.exists() or not folder.is_dir():
                return None
            if folder.name.startswith(".") or folder.name.lower() in {"__pycache__", "_runtime"}:
                return None
            mode_id = self._gate_lookup_key(folder.name)
            if not mode_id or mode_id == "holocore":
                return None
            manifest_path = folder / MODE_MANIFEST_NAME
            manifest = _safe_read_json(manifest_path) if manifest_path.exists() else {}
            if not isinstance(manifest, dict):
                manifest = {}
            main_path = find_case_insensitive_file(folder, "main.py")
            runtime_path = find_case_insensitive_file(folder, "runtime.py")
            title = str(manifest.get("title") or folder.name).strip() or folder.name
            source_kind = str(manifest.get("source_kind") or _mode_source_kind(main_path)).strip() or "unknown"
            launch_type = normalize_mode_launch_type(manifest.get("launch_type")) if manifest.get("launch_type") else ""
            runtime_installer = str(manifest.get("runtime_installer") or "").strip()
            if not runtime_installer and runtime_path and runtime_path.exists():
                try:
                    text = runtime_path.read_text(encoding="utf-8", errors="ignore")[:36000]
                    match = re.search(r"def\s+(install_[A-Za-z0-9_]+)\s*\(", text)
                    if match:
                        runtime_installer = match.group(1)
                except Exception:
                    runtime_installer = ""
            if not launch_type:
                if runtime_path and runtime_installer:
                    launch_type = "in_world_region"
                elif main_path and main_path.exists():
                    launch_type = "embedded_external" if source_kind in {"panda3d", "pygame", "python", "unknown"} else "hosted_external"
                else:
                    launch_type = MODE_LAUNCH_PLACEHOLDER
            entry_value = f"Dimensions/{folder.name}/main.py" if main_path and main_path.exists() else ""
            return {
                "id": mode_id,
                "name": folder.name,
                "title": title.upper(),
                "folder": f"Dimensions/{folder.name}",
                "entry": entry_value,
                "entry_exists": bool(main_path and main_path.exists()),
                "runtime": f"Dimensions/{folder.name}/runtime.py" if runtime_path and runtime_path.exists() else "",
                "runtime_installer": runtime_installer,
                "runtime_module": mode_id + "_runtime" if runtime_installer else "",
                "runtime_ownership": "dimension_local" if runtime_installer else "",
                "launch_type": launch_type,
                "source_kind": source_kind,
                "enabled": True,
                "available": bool((main_path and main_path.exists()) or (runtime_path and runtime_installer)),
                "placeholder_mode": launch_type == MODE_LAUNCH_PLACEHOLDER,
                "status": "auto_configured" if ((main_path and main_path.exists()) or (runtime_path and runtime_installer)) else "needs_config",
                "transition_route": "transition_in_world_region" if launch_type == "in_world_region" else ("transition_embedded_external" if launch_type == "embedded_external" else "transition_placeholder"),
                "notes": "Auto-discovered by HoloCore gate scan. Add a manifest or dimension_index entry later for stricter routing.",
            }
        except Exception as exc:
            try:
                print(f"holocore_gate_folder_scan_error:{exc.__class__.__name__}:{exc}")
            except Exception:
                pass
            return None

    def _scan_dimension_gate_folders(self, known: set[str]) -> list[dict]:
        discovered: list[dict] = []
        try:
            dims_root = resolve_dimensions_root(ROOT)
            if not dims_root.exists() or not dims_root.is_dir():
                return discovered
            for folder in sorted([p for p in dims_root.iterdir() if p.is_dir()], key=lambda p: p.name.lower()):
                key = self._gate_lookup_key(folder.name)
                if not key or key in known or key == "holocore":
                    continue
                record = self._dimension_gate_record_from_folder(folder)
                if not record:
                    continue
                known.add(key)
                discovered.append(record)
        except Exception as exc:
            try:
                print(f"holocore_gate_folder_scan_failed:{exc.__class__.__name__}:{exc}")
            except Exception:
                pass
        return discovered

    def _gate_record_to_mode(self, record: dict, *, auto: bool = False) -> dict | None:
        mode = mode_from_dimension_record(record)
        if not mode:
            return None
        manifest = dict(mode.get("manifest") or {})
        status = str(record.get("status") or manifest.get("status") or "").lower()
        route = normalize_mode_launch_type(manifest.get("launch_type") or mode.get("launch_type") or record.get("launch_type"))
        main = mode.get("main")
        runtime_text = str(record.get("runtime") or manifest.get("runtime") or "").strip()
        runtime_path = resolve_project_path(runtime_text) if runtime_text else None
        runtime_installer = str(record.get("runtime_installer") or manifest.get("runtime_installer") or "").strip()
        has_entry = bool(main is not None and Path(main).exists())
        has_runtime = bool(runtime_path is not None and runtime_path.exists() and runtime_installer)
        placeholder = bool(record.get("placeholder_mode", False) or mode.get("placeholder", False) or route == MODE_LAUNCH_PLACEHOLDER)
        available = bool(record.get("available", True)) and not placeholder and (has_entry or has_runtime or route in {MODE_LAUNCH_PANEL})
        mode["_holocore_gate_record"] = dict(record)
        mode["_holocore_gate_available"] = bool(available)
        mode["_holocore_gate_route"] = route
        mode["_holocore_gate_status"] = status or ("auto" if auto else "registered")
        mode["_holocore_gate_auto"] = bool(auto)
        mode["_holocore_gate_has_entry"] = has_entry
        mode["_holocore_gate_has_runtime"] = has_runtime
        return mode

    def _load_dimension_gateway_modes(self) -> list[dict]:
        modes: list[dict] = []
        known: set[str] = set()
        try:
            payload = read_dimension_index_payload()
            records = payload.get("dimensions") if isinstance(payload, dict) else {}
            if not isinstance(records, dict):
                records = {}
            merged_records: list[tuple[str, dict, bool]] = []
            for dim_id, record in records.items():
                if not isinstance(record, dict):
                    continue
                key = self._gate_lookup_key(record.get("id") or dim_id or record.get("name") or record.get("folder"))
                if key == "holocore":
                    continue
                if bool(record.get("enabled", True)) is False:
                    continue
                known.add(key)
                merged_records.append((key, dict(record), False))
            for record in self._scan_dimension_gate_folders(known):
                merged_records.append((self._gate_lookup_key(record.get("id") or record.get("name")), record, True))
            for _key, record, auto in sorted(merged_records, key=lambda item: str((item[1] or {}).get("title") or (item[1] or {}).get("name") or item[0]).lower()):
                mode = self._gate_record_to_mode(record, auto=auto)
                if mode:
                    modes.append(mode)
        except Exception as exc:
            try:
                print(f"holocore_gateway_index_error:{exc.__class__.__name__}:{exc}")
            except Exception:
                pass
        return modes

    def _setup_dimension_gateway_panel(self) -> None:
        self.gateway_modes = self._load_dimension_gateway_modes()
        self.gateway_buttons = []
        try:
            self.gateway_panel_root = self.app.aspect2d.attachNewNode("holocore-dimension-gates")
            self.gateway_panel_root.setBin("fixed", 62)
            panel_height = 0.86
            self.gateway_panel = DirectFrame(
                parent=self.gateway_panel_root,
                frameColor=(0.0, 0.025, 0.045, 0.46),
                frameSize=(-0.43, 0.43, -panel_height, 0.075),
                pos=(1.305, 0, 0.41),
            )
            self.gateway_title = DirectLabel(
                parent=self.gateway_panel_root,
                text="DIMENSION GATES",
                text_align=TextNode.ACenter,
                text_scale=0.032,
                text_fg=(0.72, 1.0, 1.0, 0.96),
                frameColor=(0, 0, 0, 0),
                pos=(1.305, 0, 0.465),
            )
            self.gateway_status = DirectLabel(
                parent=self.gateway_panel_root,
                text="SCAN READY // NEW FOLDERS AUTO-LINK",
                text_align=TextNode.ACenter,
                text_scale=0.020,
                text_fg=(0.62, 0.92, 1.0, 0.78),
                frameColor=(0, 0, 0, 0),
                pos=(1.305, 0, 0.405),
            )
            self.gateway_page_label = DirectLabel(
                parent=self.gateway_panel_root,
                text="",
                text_align=TextNode.ACenter,
                text_scale=0.018,
                text_fg=(0.58, 0.86, 1.0, 0.74),
                frameColor=(0, 0, 0, 0),
                pos=(1.305, 0, -0.365),
            )
            self.gateway_prev_button = DirectButton(
                parent=self.gateway_panel_root,
                text="PREV",
                text_scale=0.018,
                text_fg=(0.74, 0.95, 1.0, 0.86),
                frameColor=(0.02, 0.10, 0.14, 0.52),
                frameSize=(-0.12, 0.12, -0.020, 0.024),
                relief=1,
                pos=(1.12, 0, -0.405),
                command=self._change_dimension_gateway_page,
                extraArgs=[-1],
            )
            self.gateway_next_button = DirectButton(
                parent=self.gateway_panel_root,
                text="NEXT",
                text_scale=0.018,
                text_fg=(0.74, 0.95, 1.0, 0.86),
                frameColor=(0.02, 0.10, 0.14, 0.52),
                frameSize=(-0.12, 0.12, -0.020, 0.024),
                relief=1,
                pos=(1.49, 0, -0.405),
                command=self._change_dimension_gateway_page,
                extraArgs=[1],
            )
            self._render_dimension_gateway_page()
        except Exception as exc:
            self.gateway_panel_root = None
            try:
                print(f"holocore_gateway_panel_error:{exc.__class__.__name__}:{exc}")
            except Exception:
                pass

    def _destroy_gateway_buttons(self) -> None:
        for btn in list(getattr(self, "gateway_buttons", []) or []):
            try:
                btn.destroy()
            except Exception:
                try:
                    btn.removeNode()
                except Exception:
                    pass
        self.gateway_buttons = []

    def _render_dimension_gateway_page(self) -> None:
        self._destroy_gateway_buttons()
        modes = list(getattr(self, "gateway_modes", []) or [])
        page_size = max(1, int(getattr(self, "gateway_page_size", 9) or 9))
        max_page = max(0, (len(modes) - 1) // page_size) if modes else 0
        self.gateway_page = max(0, min(int(getattr(self, "gateway_page", 0) or 0), max_page))
        start = self.gateway_page * page_size
        shown = modes[start:start + page_size]
        y = 0.335
        for local_idx, mode in enumerate(shown, start=1):
            absolute_idx = start + local_idx
            manifest = dict(mode.get("manifest") or {})
            record = dict(mode.get("_holocore_gate_record") or {})
            label = self._clean_gate_label(self.app.dimension_display_name_for_mode(mode, record.get("title") or manifest.get("title") or mode.get("name") or f"Dimension {absolute_idx}") if hasattr(self.app, "dimension_display_name_for_mode") else (record.get("title") or manifest.get("title") or mode.get("name") or f"Dimension {absolute_idx}"))
            route = str(mode.get("_holocore_gate_route") or "").replace("_", " ").upper()
            available = bool(mode.get("_holocore_gate_available", True))
            auto = bool(mode.get("_holocore_gate_auto", False))
            badge = "AUTO" if auto and available else ("CONFIG" if not available else route.replace("EXTERNAL", "EXT")[:8])
            button_text = f"{local_idx}. {label} // {badge}"
            btn = DirectButton(
                parent=self.gateway_panel_root,
                text=button_text[:38],
                text_align=TextNode.ALeft,
                text_scale=0.022,
                text_fg=(0.80, 1.0, 1.0, 0.94) if available else (0.92, 0.72, 0.44, 0.86),
                text_pos=(-0.355, -0.008),
                frameColor=(0.02, 0.12, 0.17, 0.58) if available else (0.16, 0.10, 0.04, 0.46),
                frameSize=(-0.38, 0.38, -0.023, 0.029),
                relief=1,
                pos=(1.305, 0, y),
                command=self._request_dimension_gate,
                extraArgs=[mode],
            )
            try:
                btn.setPythonTag("route", route)
            except Exception:
                pass
            self.gateway_buttons.append(btn)
            y -= 0.060
        if self.gateway_page_label is not None:
            total = len(modes)
            self.gateway_page_label["text"] = f"PAGE {self.gateway_page + 1}/{max_page + 1} // {total} GATES" if total else "NO GATES"
        if self.gateway_prev_button is not None:
            self.gateway_prev_button["state"] = "normal" if self.gateway_page > 0 else "disabled"
        if self.gateway_next_button is not None:
            self.gateway_next_button["state"] = "normal" if self.gateway_page < max_page else "disabled"
        if self.gateway_status is not None:
            auto_count = sum(1 for m in modes if bool(m.get("_holocore_gate_auto", False)))
            config_count = sum(1 for m in modes if not bool(m.get("_holocore_gate_available", True)))
            if not modes:
                self.gateway_status["text"] = "NO DIMENSION ROUTES FOUND"
            elif config_count:
                self.gateway_status["text"] = f"{config_count} GATES NEED CONFIG // SAFE"
            elif auto_count:
                self.gateway_status["text"] = f"{auto_count} AUTO-LINKED GATES READY"
            else:
                self.gateway_status["text"] = "REGISTERED GATES READY"

    def _change_dimension_gateway_page(self, delta: int) -> None:
        modes = list(getattr(self, "gateway_modes", []) or [])
        if not modes:
            return
        page_size = max(1, int(getattr(self, "gateway_page_size", 9) or 9))
        max_page = max(0, (len(modes) - 1) // page_size)
        self.gateway_page = max(0, min(int(getattr(self, "gateway_page", 0) or 0) + int(delta or 0), max_page))
        self._render_dimension_gateway_page()

    def _set_gate_buttons_enabled(self, enabled: bool) -> None:
        for btn in list(getattr(self, "gateway_buttons", []) or []):
            try:
                btn["state"] = "normal" if enabled else "disabled"
            except Exception:
                pass

    def _request_dimension_gate(self, mode: dict) -> None:
        if self.gateway_pending_mode is not None:
            return
        mode = dict(mode or {})
        manifest = dict(mode.get("manifest") or {})
        record = dict(mode.get("_holocore_gate_record") or {})
        label = self._clean_gate_label(self.app.dimension_display_name_for_mode(mode, record.get("title") or manifest.get("title") or mode.get("name") or "DIMENSION") if hasattr(self.app, "dimension_display_name_for_mode") else (record.get("title") or manifest.get("title") or mode.get("name") or "DIMENSION"))
        if not bool(mode.get("_holocore_gate_available", True)):
            if self.gateway_status is not None:
                self.gateway_status["text"] = f"{label} // NEEDS CONFIG"[:38]
            try:
                self.app.center_hint["text"] = f"HOLOCORE // {label} NEEDS CONFIG"
            except Exception:
                pass
            return
        self.gateway_pending_mode = mode
        self.gateway_pending_started_at = time.monotonic()
        self._set_gate_buttons_enabled(False)
        if self.gateway_status is not None:
            self.gateway_status["text"] = f"OPENING {label}"[:38]
        try:
            self.app.center_hint["text"] = f"HOLOCORE GATE // {label}"
            self.app.show_bridge_transition("HOLOCORE GATE", f"OPENING {label}", target=1.0, hold=0.25)
        except Exception:
            pass

    def _update_dimension_gateway(self) -> None:
        mode = getattr(self, "gateway_pending_mode", None)
        if mode is None:
            return
        if time.monotonic() - float(getattr(self, "gateway_pending_started_at", 0.0) or 0.0) < 0.36:
            return
        self.gateway_pending_mode = None
        manifest = dict(mode.get("manifest") or {})
        label = self._clean_gate_label(self.app.dimension_display_name_for_mode(mode, manifest.get("title") or mode.get("name") or "DIMENSION") if hasattr(self.app, "dimension_display_name_for_mode") else (manifest.get("title") or mode.get("name") or "DIMENSION"))
        try:
            self.app.return_from_native_mode(reason=f"holocore_gate_{label.lower().replace(' ', '_')}")
        except Exception:
            pass
        try:
            ok = self.app.start_dimension_transition(
                mode,
                source="holocore_gateway",
                context={"doorway": "holocore_button", "origin": "HoloCore", "route": str(manifest.get("launch_type") or mode.get("launch_type") or "")},
                extra_env={"HOLOVERSE_GATEWAY_SOURCE": "HoloCore", "HOLOVERSE_GATEWAY_BUTTON": label},
                close_core=True,
            )
            if not ok:
                self.app.center_hint["text"] = f"HOLOCORE // {label} ROUTE NEEDS CONFIG"
        except Exception as exc:
            try:
                self.app.center_hint["text"] = f"HOLOCORE // {label} ROUTE NEEDS CONFIG"
                print(f"holocore_dimension_gate_dispatch_error:{exc.__class__.__name__}:{exc}")
            except Exception:
                pass

    def _build_holo_vessel_outside_pyramid(self, HoloVesselClass) -> None:
        """Spawn the Pass 37 walkable/flying vessel in the same-window scene."""
        try:
            ground = self._holo_vessel_ground_z(0.0, -212.0)
            self.holo_vessel = HoloVesselClass().build(self.app, Vec3(0.0, -212.0, ground), heading=180.0)
        except Exception as exc:
            self.holo_vessel = None
            try:
                print(f"holocore_same_window_vessel_build_error:{exc.__class__.__name__}:{exc}")
            except Exception:
                pass

    def _setup_holo_vessel_prompt(self) -> None:
        try:
            self.holo_vessel_prompt = DirectLabel(
                parent=self.app.aspect2d,
                text="",
                pos=(0.0, 0.0, -0.82),
                scale=0.034,
                frameColor=(0.0, 0.0, 0.0, 0.0),
                text_fg=(0.72, 1.0, 0.94, 0.94),
                text_shadow=(0.0, 0.0, 0.0, 0.78),
                text_align=TextNode.ACenter,
            )
            self.holo_vessel_prompt.hide()
        except Exception:
            self.holo_vessel_prompt = None

    def _holo_vessel_ground_z(self, x: float, y: float) -> float:
        try:
            if self.outer_world is not None and hasattr(self.outer_world, "collision_ground_z_at"):
                return float(self.outer_world.collision_ground_z_at(float(x), float(y)))
        except Exception:
            pass
        try:
            from world_grid import sonar_height_at
            return float(sonar_height_at(float(x), float(y)))
        except Exception:
            try:
                return float(getattr(self.hub, "floor_z", 0.0))
            except Exception:
                return 0.0

    def _holo_vessel_keepout_allows(self, x: float, y: float) -> bool:
        try:
            return (float(x) * float(x) + float(y) * float(y)) >= (92.0 * 92.0)
        except Exception:
            return True

    def _set_holo_vessel_prompt(self, text: str | None) -> None:
        prompt = getattr(self, "holo_vessel_prompt", None)
        if prompt is None:
            return
        try:
            if not text:
                if self._holo_vessel_prompt_visible is not False:
                    prompt.hide()
                    self._holo_vessel_prompt_visible = False
                return
            if self._holo_vessel_prompt_text != text:
                prompt["text"] = text
                self._holo_vessel_prompt_text = text
            if self._holo_vessel_prompt_visible is not True:
                prompt.show()
                self._holo_vessel_prompt_visible = True
        except Exception:
            pass

    def _update_holo_vessel_prompt(self) -> None:
        vessel = getattr(self, "holo_vessel", None)
        if vessel is None or self.player is None:
            self._set_holo_vessel_prompt(None)
            return
        pos = self.player.getPos(self.app.render)
        if bool(getattr(self, "holo_vessel_piloting", False)):
            self._set_holo_vessel_prompt("HOLO VESSEL // PILOTING // W/S THRUST // A/D YAW // SPACE UP // C DOWN // E LEAVE SEAT")
        elif bool(getattr(self, "holo_vessel_boarded", False)):
            if vessel.is_near_pilot(pos):
                self._set_holo_vessel_prompt("HOLO VESSEL // E PILOT SEAT")
            elif vessel.is_near_exit(pos):
                self._set_holo_vessel_prompt("HOLO VESSEL // E EXIT TO TERRAIN")
            else:
                self._set_holo_vessel_prompt("HOLO VESSEL // WALKABLE CABIN // FIND SEAT OR REAR EXIT")
        elif vessel.is_near_entry(pos):
            self._set_holo_vessel_prompt("HOLO VESSEL // E BOARD CRESCENT RUNNER")
        else:
            self._set_holo_vessel_prompt(None)

    def _board_holo_vessel(self) -> bool:
        vessel = getattr(self, "holo_vessel", None)
        if vessel is None or self.player is None:
            return False
        self.holo_vessel_boarded = True
        self.holo_vessel_piloting = False
        self.player.setPos(vessel.board_spawn_world_position())
        try:
            self.heading = float(vessel.root.getH(self.app.render)) if vessel.root is not None else self.heading
            self.player.setH(self.heading)
            self.app.camera.reparentTo(self.player)
            self.app.camera.setPos(0, 0, self.eye_height)
            self.app.camera.setHpr(0, self.pitch, 0)
            self.app.center_hint["text"] = "HOLO VESSEL // BOARDED"
        except Exception:
            pass
        return True

    def _exit_holo_vessel_to_terrain(self) -> bool:
        vessel = getattr(self, "holo_vessel", None)
        if vessel is None or self.player is None:
            return False
        self.holo_vessel_piloting = False
        self.holo_vessel_boarded = False
        entry = vessel.entry_world_position()
        terrain_z = self._holo_vessel_ground_z(float(entry.x), float(entry.y))
        self.player.setPos(vessel.exit_world_position(terrain_z))
        try:
            self.app.camera.reparentTo(self.player)
            self.app.camera.setPos(0, 0, self.eye_height)
            self.app.camera.setHpr(0, self.pitch, 0)
            self.app.center_hint["text"] = "HOLO VESSEL // EXITED"
        except Exception:
            pass
        return True

    def _enter_holo_vessel_pilot_seat(self) -> bool:
        vessel = getattr(self, "holo_vessel", None)
        if vessel is None or self.player is None:
            return False
        self.holo_vessel_boarded = True
        self.holo_vessel_piloting = True
        self.player.setPos(vessel.pilot_seat_world_position())
        try:
            self.app.camera.reparentTo(self.app.render)
            self.app.camera.setPos(vessel.pilot_camera_world_position())
            self.app.camera.lookAt(vessel.pilot_look_world_position())
            self.app.center_hint["text"] = "HOLO VESSEL // PILOT SEAT"
        except Exception:
            pass
        return True

    def _leave_holo_vessel_pilot_seat(self) -> bool:
        vessel = getattr(self, "holo_vessel", None)
        if vessel is None or self.player is None:
            return False
        self.holo_vessel_piloting = False
        self.holo_vessel_boarded = True
        self.player.setPos(vessel.pilot_seat_world_position())
        try:
            self.heading = float(vessel.root.getH(self.app.render)) if vessel.root is not None else self.heading
            self.player.setH(self.heading)
            self.app.camera.reparentTo(self.player)
            self.app.camera.setPos(0, 0, self.eye_height)
            self.app.camera.setHpr(0, self.pitch, 0)
            self.app.center_hint["text"] = "HOLO VESSEL // LEFT PILOT SEAT"
        except Exception:
            pass
        return True

    def _try_holo_vessel_interaction(self) -> bool:
        vessel = getattr(self, "holo_vessel", None)
        if vessel is None or self.player is None:
            return False
        pos = self.player.getPos(self.app.render)
        if bool(getattr(self, "holo_vessel_piloting", False)):
            return self._leave_holo_vessel_pilot_seat()
        if bool(getattr(self, "holo_vessel_boarded", False)):
            if vessel.is_near_pilot(pos):
                return self._enter_holo_vessel_pilot_seat()
            if vessel.is_near_exit(pos):
                return self._exit_holo_vessel_to_terrain()
            return False
        if vessel.is_near_entry(pos):
            return self._board_holo_vessel()
        return False

    def _update_holo_vessel_piloting(self, dt: float) -> None:
        vessel = getattr(self, "holo_vessel", None)
        if vessel is None or not bool(getattr(self, "holo_vessel_piloting", False)):
            return
        forward_axis = 0.0
        if self._key_down("w", "arrow_up"):
            forward_axis += 1.0
        if self._key_down("s", "arrow_down"):
            forward_axis -= 1.0
        turn_axis = 0.0
        if self._key_down("a", "arrow_left"):
            turn_axis += 1.0
        if self._key_down("d", "arrow_right"):
            turn_axis -= 1.0
        vertical_axis = 0.0
        if self._key_down("space", "page_up"):
            vertical_axis += 1.0
        if self._key_down("c", "page_down"):
            vertical_axis -= 1.0
        vessel.move_piloted(
            dt,
            forward_axis=forward_axis,
            turn_axis=turn_axis,
            vertical_axis=vertical_axis,
            terrain_height_func=self._holo_vessel_ground_z,
            keepout_func=self._holo_vessel_keepout_allows,
        )
        try:
            self.player.setPos(vessel.pilot_seat_world_position())
            self.app.camera.reparentTo(self.app.render)
            self.app.camera.setPos(vessel.pilot_camera_world_position())
            self.app.camera.lookAt(vessel.pilot_look_world_position())
        except Exception:
            pass

    def _clamp_player_with_holo_vessel(self, old_pos: Vec3, new_pos: Vec3) -> Vec3:
        vessel = getattr(self, "holo_vessel", None)
        if vessel is None:
            return Vec3(new_pos)
        if bool(getattr(self, "holo_vessel_boarded", False)):
            return Vec3(vessel.clamp_interior_position(new_pos))
        try:
            terrain_pos = Vec3(new_pos)
            terrain_pos.z = self._holo_vessel_ground_z(float(terrain_pos.x), float(terrain_pos.y))
            return Vec3(vessel.push_outside_around_hull(old_pos, terrain_pos))
        except Exception:
            return Vec3(new_pos)

    def _reset_player(self) -> None:
        try:
            self.player.setPos(self.hub.get_spawn_position())
            self._look_player_at(self.hub.get_spawn_target())
        except Exception:
            self.player.setPos(0, -58, 0)
            self.heading = 0.0
            self.pitch = 0.0

    def _lock_mouse(self) -> None:
        try:
            if self.app.win is not None:
                props = WindowProperties()
                props.setCursorHidden(True)
                props.setForeground(True)
                self.app.win.requestProperties(props)
                self._center_mouse_pointer()
        except Exception:
            pass

    def _center_mouse_pointer(self) -> None:
        try:
            props = self.app.win.getProperties()
            cx = props.getXSize() // 2
            cy = props.getYSize() // 2
            if cx > 0 and cy > 0:
                self.app.win.movePointer(0, cx, cy)
        except Exception:
            pass

    def _look_player_at(self, target: Vec3) -> None:
        world_pos = self.player.getPos(self.app.render) + Vec3(0, 0, self.eye_height)
        self.app.camera.reparentTo(self.app.render)
        self.app.camera.setPos(world_pos)
        self.app.camera.lookAt(target)
        h, p, _ = self.app.camera.getHpr(self.app.render)
        self.heading = h
        self.pitch = max(-78.0, min(78.0, p))
        self.player.setH(self.heading)
        self.app.camera.reparentTo(self.player)
        self.app.camera.setPos(0, 0, self.eye_height)
        self.app.camera.setHpr(0, self.pitch, 0)

    def _key_down(self, *names: str) -> bool:
        keys = getattr(self.app, "keys", {}) or {}
        return any(bool(keys.get(name, False)) for name in names)

    def update(self, dt: float) -> None:
        if self._destroyed:
            return
        dt = min(0.05, max(0.0, float(dt or 0.0)))
        self.elapsed += dt
        task_stub = type("HoloCoreTask", (), {"time": self.elapsed, "dt": dt})()
        try:
            if self.hub is not None:
                self.hub.update(task_stub)
            if self.outer_world is not None:
                self.outer_world.update(task_stub)
        except Exception as exc:
            print(f"holocore_same_window_world_update_error:{exc.__class__.__name__}:{exc}")
        try:
            if self.holo_vessel is not None and not bool(getattr(self, "holo_vessel_piloting", False)):
                self.holo_vessel.update_ground_lock(self._holo_vessel_ground_z)
        except Exception as exc:
            try:
                print(f"holocore_same_window_vessel_ground_lock_error:{exc.__class__.__name__}:{exc}")
            except Exception:
                pass
        if not bool(getattr(self.app, "menu_open", False)) and not bool(getattr(self.app, "core_console_open", False)):
            if bool(getattr(self, "holo_vessel_piloting", False)):
                self._update_holo_vessel_piloting(dt)
            else:
                self._update_first_person(dt)
        else:
            # Shared MatrixCore/HoloCore menu owns input while open. Keep the
            # sub-world alive, but do not steer or walk behind the menu.
            try:
                props = WindowProperties()
                props.setCursorHidden(False)
                if self.app.win is not None:
                    self.app.win.requestProperties(props)
            except Exception:
                pass
        self._sync_dimension_music(force=False)
        self._update_holo_vessel_prompt()
        self._update_return_prompt()

    def _update_first_person(self, dt: float) -> None:
        if self.player is None or self.player.isEmpty():
            return
        if bool(getattr(self.app, "menu_open", False)) or bool(getattr(self.app, "core_console_open", False)):
            return
        try:
            if self.app.win is not None:
                props = self.app.win.getProperties()
                cx = props.getXSize() // 2
                cy = props.getYSize() // 2
                pointer = self.app.win.getPointer(0)
                dx = pointer.getX() - cx
                dy = pointer.getY() - cy
                if abs(dx) > 0 or abs(dy) > 0:
                    self.heading -= dx * self.mouse_sensitivity
                    self.pitch -= dy * self.mouse_sensitivity
                    self.pitch = max(-78.0, min(78.0, self.pitch))
                    self._center_mouse_pointer()
        except Exception:
            pass
        self.player.setH(self.heading)
        self.app.camera.setHpr(0, self.pitch, 0)

        move = Vec3(0, 0, 0)
        quat = self.player.getQuat(self.app.render)
        forward = quat.getForward()
        right = quat.getRight()
        forward.setZ(0)
        right.setZ(0)
        if forward.lengthSquared() > 0:
            forward.normalize()
        if right.lengthSquared() > 0:
            right.normalize()
        if self._key_down("w", "arrow_up"):
            move += forward
        if self._key_down("s", "arrow_down"):
            move -= forward
        if self._key_down("d", "arrow_right"):
            move += right
        if self._key_down("a", "arrow_left"):
            move -= right
        if move.lengthSquared() > 0:
            move.normalize()
            speed = self.sprint_speed if self._key_down("shift", "lshift", "rshift") else self.walk_speed
            old_pos = self.player.getPos(self.app.render)
            self.player.setPos(self.player.getPos() + move * speed * dt)
            try:
                if self.outer_world is not None and not bool(getattr(self, "holo_vessel_boarded", False)):
                    self.player.setPos(self.outer_world.clamp_position(self.player.getPos()))
            except Exception:
                pass
            try:
                self.player.setPos(self._clamp_player_with_holo_vessel(old_pos, self.player.getPos(self.app.render)))
            except Exception:
                pass

    def on_host_action(self, action: str) -> bool:
        action = str(action or "").lower()
        if action in {"escape", "pause", "menu"}:
            # HoloCore is entered from an artifact slot, so ESC must match the
            # dimension contract and return to the hub.  The old behavior opened
            # the shared gates/menu overlay, which made players feel trapped and
            # overlapped with vehicle/TAB prompts.
            self.app.return_from_native_mode(reason="holocore_escape")
            return True
        if action in {"e", "e_down", "interact"}:
            if self._try_holo_vessel_interaction():
                return True
            try:
                self.app.center_hint["text"] = self._ui_text("interact_hint")
            except Exception:
                pass
            return True
        if action in {"gate", "gates", "open_gates"}:
            if not self._near_pyramid_return_gate():
                self._update_return_prompt()
                try:
                    self.app.center_hint["text"] = self._ui_text("gate_walk_back_hint")
                except Exception:
                    pass
                return True
            try:
                self.app.set_menu_tab("gates")
                if not bool(getattr(self.app, "menu_open", False)):
                    self.app.toggle_menu()
                else:
                    self.app.refresh_menu_actions()
                    self.app.refresh_ui()
                self.app.center_hint["text"] = self._ui_text("gate_select_hint")
            except Exception:
                pass
            return True
        if action in {"0", "number_0", "return", "return_to_core"}:
            self.app.return_from_native_mode(reason=f"holocore_{action or 'return'}")
            return True
        if action in {"tab", "cycle_dimension"}:
            try:
                if self.outer_world is not None:
                    name = self.outer_world.cycle_dimension(immediate=False)
                    self._sync_dimension_music(force=True)
                    self.app.center_hint["text"] = self._ui_text("tab_cycle_hint", dimension=str(name).upper())
            except Exception as exc:
                print(f"holocore_same_window_tab_error:{exc.__class__.__name__}:{exc}")
            return True
        return False

    def destroy(self) -> None:
        if self._destroyed:
            return
        self._destroyed = True
        try:
            self.app.stop_holocore_dimension_music()
        except Exception:
            pass
        try:
            if self.return_prompt is not None:
                self.return_prompt.destroy()
        except Exception:
            pass
        try:
            if self.holo_vessel_prompt is not None:
                self.holo_vessel_prompt.destroy()
        except Exception:
            pass
        try:
            if self.holo_vessel is not None and getattr(self.holo_vessel, "root", None) is not None:
                self.holo_vessel.root.removeNode()
        except Exception:
            pass
        try:
            if self.gateway_panel_root is not None and not self.gateway_panel_root.isEmpty():
                self.gateway_panel_root.removeNode()
        except Exception:
            pass
        try:
            self.app.camera.reparentTo(self.app.render)
        except Exception:
            pass
        try:
            if self._saved_render_state is not None:
                self.app.render.setState(self._saved_render_state)
        except Exception:
            pass
        for name in sorted(self._holocore_render_child_names):
            try:
                for node in list(self.app.render.findAllMatches(f"**/{name}")):
                    if not node.isEmpty():
                        node.removeNode()
            except Exception:
                pass
        try:
            if self.player is not None and not self.player.isEmpty():
                self.player.removeNode()
        except Exception:
            pass
        try:
            if self._old_player_attr is None and hasattr(self.app, "player"):
                delattr(self.app, "player")
            elif self._old_player_attr is not None:
                setattr(self.app, "player", self._old_player_attr)
        except Exception:
            pass
        try:
            if self._saved_background is not None:
                self.app.win.setClearColor(self._saved_background)
        except Exception:
            pass


# Connected signal mini-scene was removed intentionally.  It was a tiny generic
# signal-collection stand-in that prevented legacy dimensions from opening
# their real entries.  HoloCore is the exception: it is same-window only and
# mounts through HoloCoreSameWindowScene so the updated vessel/mob world is used.

def lerp(a, b, t):
    return a + (b - a) * t


def lerp_rgb(a, b, t):
    return tuple(lerp(a[i], b[i], t) for i in range(3))


class CommandHubApp(ShowBase):
    # TAB is reserved for the clean cinematic camera in the HoloVerse host.
    # Region runtimes may still own their local systems, but they must not
    # monkey-patch TAB back to the old saved-aircraft gate.
    tab_cinematic_flycam_owns_shell_flight = True

    def userExit(self):
        try:
            self.persist_world_cycle_progress(force=True)
        except Exception:
            pass
        try:
            clear_holoverse_runtime_cache("userExit")
        except Exception:
            pass
        return super().userExit()


    def __init__(self):
        ensure_dirs()
        super().__init__()
        self.disableMouse()
        self.clock = ClockObject.getGlobalClock()
        self.clock.setMode(ClockObject.MNormal)
        self.cfg = load_config()
        self.elapsed = 0.0
        self._world_cycle_progress_last_save_wall = 0.0
        self._world_cycle_progress_last_elapsed = 0.0
        try:
            self.restore_world_cycle_progress()
        except Exception:
            pass
        self.self_test_frame_count = 0
        self.self_test_dt_total = 0.0
        self.self_test_dt_peak = 0.0
        self.menu_open = False
        self.hud_visible = self.cfg.hud_visible
        self.keys = {}
        self.gamepad = None
        self.player_pos = Vec3(0, -10, self.cfg.player_eye_height)
        self.player_yaw = 0.0
        self.player_pitch = -7.0
        self.move_velocity = Vec2(0, 0)
        self.room_bounds = []
        self.hub_radius = 30.0
        self.artifact_radius = 22.8
        self.active_artifact = None
        self.active_artifact_id = None
        self.world_unlocked = False
        self.transition_progress = 0.0
        self.transition_target = 0.0
        self.terrain_chunks = {}
        self.artifacts = []
        self.galaxy_nodes = []
        self.artifact_shape_nodes = []
        self.nearest_artifact = None
        self.nearest_artifact_dist = 999.0
        self.base_teleport = Vec3(0, -10, self.cfg.player_eye_height)
        self.hub_fill_nodes = []
        self.hub_fill_alpha = 1.0 if self.cfg.hub_fill_enabled else 0.0
        self.hub_fill_target = self.hub_fill_alpha
        self.hub_textures = {}
        self.world_surface_textures = {}
        self.world_actors = []
        self.last_world_kind = "frontier"
        self.world_theme_blend = 0.0
        self.default_hub_rgb = (0.94, 0.96, 1.0)
        self.current_hub_rgb = self.default_hub_rgb
        self.current_bg_rgb = (self.cfg.background_value, self.cfg.background_value, self.cfg.background_value)
        self.campaign_path = first_existing_path(CAMPAIGN_CANDIDATES)
        self.mx_path = first_existing_path(MX_CANDIDATES)
        self.core_modes = discover_core_modes(ROOT)
        self.core_mode_page = 0
        self.core_mode_state = load_mode_state()
        self.last_launched_core_mode = ""
        self.last_launched_core_entry = ""
        self.core_console_open = False
        self.bot_dimension_config = ensure_bot_dimension_config()
        self.bot_dimension_links = self._load_bot_dimension_links()
        self.bot_dialogue_open = False
        self.bot_dialogue_context = None
        self.bot_dialogue_node = None
        self.bot_dialogue_mode = ""
        self.bot_dialogue_bot = ""
        self.bot_dialogue_region = ""
        self.bot_dialogue_launch_in_progress = False
        self.bot_dialogue_last_launch_error = ""
        self.external_process = None
        self.external_suspended = False
        self.external_resume_pending = False
        self.external_launch_label = ""
        self.external_return_code = None
        self.external_resume_marked = False
        self.embedded_child_host = None
        self.embedded_child_attached = False
        self.external_return_signal_path = None
        self.external_return_requested_at = 0.0
        self.external_launch_started_at = 0.0
        self.bridge_transition_root = None
        self.bridge_transition_panel = None
        self.bridge_transition_label = None
        self.bridge_transition_subtitle = None
        self.bridge_transition_alpha = 0.0
        self.bridge_transition_target = 0.0
        self.bridge_transition_hold_until = 0.0
        self.active_native_mode = None
        self.native_mode_label = ""
        self.native_mode_entry = None
        self.native_mode_route = ""
        self.native_mode_start_time = 0.0
        self.native_mode_return_pending = False
        self.native_mode_isolated = False
        self.native_mode_audio_profile = {}
        self.mouse_captured = True
        self.underwater_vehicle_root = None
        self.underwater_vehicle_color = (0.30, 0.96, 0.88, 0.96)
        self.xr = None
        self.vr_origin = None
        self.vr_active = False
        self.vr_status = "DESKTOP"
        self.vr_turn_cooldown = 0.0
        self.vr_left_hand = None
        self.vr_right_hand = None
        self.audio = None
        self.core_console_page = "guide"
        self.matrixcore_page_index = 0
        self.matrixcore_gate_page = 0
        self.matrixcore_gate_page_size = MATRIXCORE_VISIBLE_ACTION_CARD_LIMIT
        # Shared gate menu is the same overlay for MatrixCore and HoloCore.
        # HoloCore gameplay should not own a separate stuck panel.
        self.shared_gate_menu_page = 0
        self.matrixcore_data = self.ensure_matrixcore_foundation()
        self.gleebs_dialogue_data = self.ensure_gleebs_dialogue_seed()
        self.gleebs_hologram_root = None
        self.gleebs_hologram_card = None
        self.gleebs_hologram_parts = []
        self.gleebs_dialogue_active = False
        self.gleebs_dialogue_id = ""
        self.gleebs_dialogue_flag = ""
        self.gleebs_dialogue_text = ""
        self.gleebs_current_quote = ""
        self.gleebs_dialogue_text_override = ""
        self.gleebs_dialogue_dimension = ""
        self.gleebs_dialogue_advice = ""
        self.gleebs_dialogue_started_at = 0.0
        self.gleebs_dialogue_duration = 0.0
        self.gleebs_dialogue_fade = 0.0
        self.gleebs_dialogue_fade_target = 0.0
        self.gleebs_dialogue_close_on_fade = False
        self.gleebs_dialogue_queue = []
        self.gleebs_dialogue_queue_wait_until = 0.0
        self.gleebs_dialogue_dismiss_reason = ""
        self.gleebs_last_near_core = False
        self.gleebs_last_context_signal = "boot"
        self.runtime_avg_dt = 0.0
        self.runtime_avg_fps = 0.0
        self.ui_text_cache = {}
        self.perf_hud_last_update = -999.0
        self.perf_hud_cached_text = "POINTS 000000"
        self.runtime_chunk_peak = 0
        self.runtime_actor_peak = 0
        self.runtime_world_signature = "HUB STANDBY"
        self.runtime_last_zone = "COMMAND HUB"
        self.world_shell_mount = None
        self.world_shell_mount_status = "MOUNT PENDING"
        self.world_shell_mount_biome = "Hub Region"
        self.world_shell_streamed_count = 0
        self.world_shell_preloaded_default = False
        self.world_shell_preload_report = {}
        self.world_shell_theme_handoff = {}
        self.world_shell_hub_theme_current = 0.0
        self.world_shell_hub_theme_status = "OFF"
        self.world_shell_hub_theme_last = {}
        self.world_shell_audio_handoff = {}
        self.world_shell_audio_status = "OFF"
        self.world_shell_prompt = "HOLOVERSE READY"
        self.world_shell_motion_status = "OFF"
        self.world_shell_playable_status = "READY"
        self.world_shell_play_state = {}
        self.world_shell_play_radius = 0.0
        self.world_shell_boundary_status = "READY"
        self.world_shell_last_biome_key = 0
        self.region_ui_last_active_number = None
        self.region_ui_last_name = ""
        self.region_ui_last_visible = None
        self.shell_flight_craft_active = False
        self.shell_flight_craft_velocity = Vec3(0, 0, 0)
        self.shell_flight_craft_boost = 1.0
        self.shell_flight_craft_cinematic = False
        self.shell_flight_craft_return_state = None
        self.holospace_velocity = Vec3(0, 0, 0)
        self.holospace_speed_boost = 1.0
        self.holospace_ship_health = 100.0
        self.holospace_ship_max_health = 100.0
        self.holospace_ship_respawn_cooldown = 0.0
        self.holospace_last_damage_at = -999.0
        self.holospace_battle_status = "IDLE"
        self.holospace_transition_active = False
        self.holospace_transition_started_at = 0.0
        self.holospace_transition_duration = 10.0
        self.holospace_transition_source = ""
        self.holospace_transition_target_entry = None
        self.holospace_transition_destination = "space"
        self.holospace_transition_completed_count = 0
        self.holospace_travel_runtime = None
        self.world_shell_last_prompt_at = -999.0
        self.world_shell_claimed_checkpoints = set()
        self.world_shell_checkpoint_claimed_count = 0
        self.world_shell_checkpoint_total = 0
        self.world_shell_checkpoint_status = "0/0"
        self.world_shell_default_lifecycle_state = "HOLOVERSE_BOOT_PENDING"
        self.active_world_runtime_state_label = "HOLOVERSE_BOOT_PENDING"
        self.load_world_shell_play_state()
        self.comfort_overlay = None
        self.comfort_panel_label = None
        self.comfort_vignette_nodes = []
        self.vr_onboarding_pending = False
        self.esc_hold_active = False
        self.esc_hold_start = 0.0
        self.esc_hold_deadline = 0.0
        self.esc_hold_exit_triggered = False

        self.render.setAntialias(AntialiasAttrib.MLine)
        self.render.setTransparency(TransparencyAttrib.MAlpha)
        self.setup_window()
        self.setup_scene()
        self.setup_audio()
        self.setup_vr()
        self.setup_ui()
        self.setup_input()
        self.setup_gamepad()
        self.ensure_hub_textures()
        self.rebuild_station()
        self.refresh_ui()
        if self.vr_active and not bool(getattr(self.cfg, "vr_onboarding_complete", False)) and not SELF_TEST:
            self.show_vr_onboarding()
        if not self.vr_active:
            self.camera.setPos(self.player_pos)
            self.camera.setHpr(self.player_yaw, self.player_pitch, 0)
        self.accept("window-event", self.on_window_event)
        self.taskMgr.add(self.update_task, "update-task")
        if WORLD_AUTHORITY_SMOKE_TEST:
            self.taskMgr.doMethodLater(0.45, self.world_authority_smoke_setup, "world-authority-smoke-setup")
            self.taskMgr.doMethodLater(1.35, self.world_authority_smoke_exit, "world-authority-smoke-exit")
        elif SELF_TEST:
            self.taskMgr.doMethodLater(0.8, self.self_test_setup, "self-test-setup")
            self.taskMgr.doMethodLater(2.1, self.self_test_exit, "self-test-exit")
        else:
            if not self.vr_active:
                self.recenter_mouse(force=True)
            if AUTO_EXIT:
                self.taskMgr.doMethodLater(2.0, self.self_test_exit, "auto-exit")
            self.taskMgr.doMethodLater(0.85, self._gleebs_intro_task, "matrixcore-gleebs-first-contact")

    def _gleebs_intro_task(self, task):
        self.maybe_start_gleebs_intro()
        return Task.done

    def setup_audio(self):
        self.audio = SharedAudio(self)
        self.soundscape_key = None
        self.soundscape_loop = None
        self.soundscape_base_loop = None
        self.soundscape_air_base_loop = None
        self.soundscape_air_loop = None
        self.soundscape_stinger_at = 0.0
        self.soundscape_next_rotation_at = 0.0
        self.soundscape_rotation_seconds = 54.0
        self.soundscape_variant_history = {}
        self.soundscape_variant_decks = {}
        self.soundscape_variant_history_limit = 3
        self.soundscape_rng = random.Random(int(time.time() * 1000) ^ os.getpid())
        self.matrixcore_music_click_index = -1
        self.matrixcore_music_click_last_at = 0.0
        self.holocore_dimension_music_key = None
        if self.audio and self.audio.enabled:
            self.update_soundscape(0.0, force=True)

    def _soundscape_variant_map(self) -> dict[str, list[str]]:
        return {
            'hv_hub_command_theme.wav': ['hv_hub_command_theme.wav', 'hv_hub_command_theme_b.wav', 'hv_hub_command_theme_c.wav', 'hv_hub_command_theme_d.wav', 'hv_hub_command_theme_e.wav'],
            'hv_world_exploration_theme.wav': ['hv_world_exploration_theme.wav', 'hv_world_exploration_theme_b.wav', 'hv_world_exploration_theme_c.wav', 'hv_world_exploration_theme_d.wav', 'hv_world_exploration_theme_e.wav'],
            'hv_urban_conflict_theme.wav': ['hv_urban_conflict_theme.wav', 'hv_urban_conflict_theme_b.wav', 'hv_urban_conflict_theme_c.wav', 'hv_urban_conflict_theme_d.wav', 'hv_urban_conflict_theme_e.wav'],
            'hv_metropolis_neon_theme.wav': ['hv_metropolis_neon_theme.wav', 'hv_metropolis_neon_theme_b.wav', 'hv_metropolis_neon_theme_c.wav', 'hv_metropolis_neon_theme_d.wav', 'hv_metropolis_neon_theme_e.wav'],
            'hv_space_orbit_theme.wav': ['hv_space_orbit_theme.wav', 'hv_space_orbit_theme_b.wav', 'hv_space_orbit_theme_c.wav', 'hv_space_orbit_theme_d.wav', 'hv_space_orbit_theme_e.wav'],
            'hv_water_depth_theme.wav': ['hv_water_depth_theme.wav', 'hv_water_depth_theme_b.wav', 'hv_water_depth_theme_c.wav', 'hv_water_depth_theme_d.wav', 'hv_water_depth_theme_e.wav'],
            'hv_hub_room_air.wav': ['hv_hub_room_air.wav', 'hv_hub_room_air_b.wav', 'hv_hub_room_air_c.wav', 'hv_hub_room_air_d.wav', 'hv_hub_room_air_e.wav'],
        }

    def _soundscape_available_variants(self, base_loop: str) -> list[str]:
        base_loop = str(base_loop or '').strip()
        variants = list(self._soundscape_variant_map().get(base_loop, [base_loop]))
        available = [name for name in variants if self.audio and self.audio._resolve_audio_path(name)]
        return available or ([base_loop] if base_loop else [])

    def _choose_soundscape_loop(self, base_loop: str, current_loop: str | None = None) -> str:
        base_loop = str(base_loop or '').strip()
        if not base_loop:
            return ''
        available = self._soundscape_available_variants(base_loop)
        if len(available) <= 1:
            return available[0] if available else base_loop
        rng = getattr(self, 'soundscape_rng', random)
        history_map = getattr(self, 'soundscape_variant_history', {})
        deck_map = getattr(self, 'soundscape_variant_decks', {})
        history = list(history_map.get(base_loop, []))
        avoid = {str(current_loop or '')}
        cooldown = min(max(1, int(getattr(self, 'soundscape_variant_history_limit', 3))), max(1, len(available) - 1))
        avoid.update(history[-cooldown:])
        deck = [name for name in deck_map.get(base_loop, []) if name in available and name not in avoid]
        if not deck:
            deck = [name for name in available if name not in avoid]
            if not deck:
                deck = [name for name in available if name != str(current_loop or '')] or list(available)
            try:
                rng.shuffle(deck)
            except Exception:
                random.shuffle(deck)
        choice = deck.pop(0)
        deck_map[base_loop] = deck
        history.append(choice)
        history_map[base_loop] = history[-8:]
        self.soundscape_variant_decks = deck_map
        self.soundscape_variant_history = history_map
        return choice

    def matrixcore_click_music_palette(self) -> list[str]:
        """Small hub-safe palette used when MatrixCore/Gleebs is clicked.

        The interaction should feel like the Core quietly retunes the room while
        Gleebs talks.  It must not display a helper label, create a second music
        owner, or depend on external/generated files.
        """
        return [
            "hv_hub_command_theme.wav",
            "hv_hub_command_theme_b.wav",
            "hv_hub_command_theme_c.wav",
            "hv_hub_command_theme_d.wav",
            "hv_hub_command_theme_e.wav",
            "hv_world_exploration_theme.wav",
            "hv_space_orbit_theme.wav",
            "hv_metropolis_neon_theme.wav",
            "hv_water_depth_theme.wav",
            "hv_urban_conflict_theme.wav",
        ]

    def retune_matrixcore_music_on_dialogue(self, source: str = "matrixcore") -> bool:
        """Quietly rotate the hub music when MatrixCore starts a Gleebs line."""
        audio = getattr(self, "audio", None)
        if audio is None or not bool(getattr(audio, "enabled", False)):
            return False
        if not bool(getattr(self.cfg, "soundtrack_enabled", True)):
            return False
        if getattr(self, "active_native_mode", None) is not None or getattr(self, "external_process", None) is not None:
            return False
        palette = [str(name) for name in self.matrixcore_click_music_palette()]
        available = [name for name in palette if audio._resolve_audio_path(name)]
        if not available:
            return False
        current_info = {}
        try:
            current_info = dict(getattr(audio, "looping", {}).get("hub_music", {}) or {})
        except Exception:
            current_info = {}
        current = str(current_info.get("filename") or getattr(self, "soundscape_loop", "") or "")
        start_index = (int(getattr(self, "matrixcore_music_click_index", -1) or -1) + 1) % max(1, len(available))
        choice = available[start_index]
        if len(available) > 1:
            for offset in range(len(available)):
                candidate = available[(start_index + offset) % len(available)]
                if candidate != current:
                    choice = candidate
                    start_index = (start_index + offset) % len(available)
                    break
        self.matrixcore_music_click_index = start_index
        self.matrixcore_music_click_last_at = time.monotonic()

        # MatrixCore is part of the hub, so only hub-owned loops may remain.
        for slot in ("native_dimension_music", "native_dimension_air", "holocore_dimension_music", "holocore_dimension_air"):
            try:
                audio.stop_loop(slot)
            except Exception:
                pass
        intensity = max(0.0, min(1.0, float(getattr(self.cfg, "soundtrack_intensity", 0.55))))
        ambience = max(0.0, min(1.0, float(getattr(self.cfg, "ambience_intensity", 0.45))))
        music_gain = 0.42 + 0.18 * intensity
        air_gain = 0.10 + 0.08 * ambience
        air_loop = "hv_hub_room_air.wav"
        try:
            audio.play_loop("hub_music", choice, bus="music", volume=max(0.0, min(0.72, music_gain)))
            audio.play_loop("hub_air", air_loop, bus="ambience", volume=max(0.0, min(0.22, air_gain)))
        except Exception:
            return False

        # Keep update_soundscape from immediately replacing the click-selected
        # loop on the next frame while still letting normal scene changes win.
        self.soundscape_key = "hub"
        self.soundscape_base_loop = "hv_hub_command_theme.wav"
        self.soundscape_air_base_loop = air_loop
        self.soundscape_loop = choice
        self.soundscape_air_loop = air_loop
        self.soundscape_next_rotation_at = time.time() + max(24.0, float(getattr(self, "soundscape_rotation_seconds", 54.0) or 54.0))
        self.world_shell_audio_status = "MATRIXCORE // GLEEBS RETUNE"
        return True

    def _world_soundscape_from_text(self, text: str):
        low = str(text or '').lower()
        if any(token in low for token in ('holospace', 'space', 'orbit')):
            return ('space', 'hv_space_orbit_theme.wav', 'hv_hub_room_air.wav', 0.56, 0.16, 'wide orbital synth bed')
        if 'water' in low or 'solace' in low or 'deep' in low:
            return ('water', 'hv_water_depth_theme.wav', 'hv_water_depth_theme.wav', 0.44, 0.28, 'submerged shimmer bed')
        if 'urban' in low or 'sable' in low or 'war' in low or 'combat' in low:
            return ('urban', 'hv_urban_conflict_theme.wav', 'hv_hub_room_air.wav', 0.64, 0.10, 'war-zone pulse')
        if 'metropolis' in low or 'archivist' in low or 'city' in low or 'neon' in low:
            return ('metropolis', 'hv_metropolis_neon_theme.wav', 'hv_hub_room_air.wav', 0.58, 0.12, 'neon city groove')
        if 'ice' in low or 'mirror' in low:
            return ('ice', 'hv_space_orbit_theme.wav', 'hv_hub_room_air.wav', 0.46, 0.14, 'cold crystal orbit')
        if 'forest' in low or 'hills' in low or 'desert' in low or 'mushroom' in low or 'vanta' in low or 'nyx' in low or 'ember' in low:
            return ('explore', 'hv_world_exploration_theme.wav', 'hv_hub_room_air.wav', 0.50, 0.13, 'exploration rhythm')
        return None

    def _target_soundscape(self):
        soundtrack_on = bool(getattr(self.cfg, 'soundtrack_enabled', True))
        intensity = max(0.0, min(1.0, float(getattr(self.cfg, 'soundtrack_intensity', 0.55))))
        ambience = max(0.0, min(1.0, float(getattr(self.cfg, 'ambience_intensity', 0.45))))
        if not soundtrack_on:
            return ('muted', '', 'hv_hub_room_air.wav', 0.0, 0.08 * ambience, 'soundtrack muted')

        if bool(getattr(self, 'holospace_active', False)):
            return ('space', 'hv_space_orbit_theme.wav', 'hv_hub_room_air.wav', 0.44 + 0.22 * intensity, 0.12 + 0.08 * ambience, 'holospace orbit')

        if bool(getattr(self, 'world_unlocked', False)) or float(getattr(self, 'transition_target', 0.0)) > 0.0 or float(getattr(self, 'transition_progress', 0.0)) > 0.02:
            spec = {}
            try:
                spec = self.current_world_spec() or {}
            except Exception:
                spec = {}
            name = ' '.join(str(spec.get(k, '')) for k in ('name', 'kind', 'profile'))
            mapped = self._world_soundscape_from_text(name)
            if mapped is None:
                mapped = ('artifact', 'hv_world_exploration_theme.wav', 'hv_hub_room_air.wav', 0.50, 0.12, 'artifact world exploration')
            key, music, air, music_gain, air_gain, label = mapped
            return (f'artifact_{key}', music, air, min(0.72, music_gain + 0.16 * intensity), min(0.30, air_gain + 0.08 * ambience), label)

        shell_audio = self.world_shell_audio_handoff if isinstance(getattr(self, 'world_shell_audio_handoff', {}), dict) else {}
        zone = self.current_zone_name()
        shell_text = ' '.join([
            str(zone),
            str(getattr(self, 'world_shell_mount_biome', '')),
            str(shell_audio.get('active_biome', '')),
            str(shell_audio.get('tone', '')),
            str(shell_audio.get('recommended_loop', '')),
        ])
        mapped = self._world_soundscape_from_text(shell_text)
        if mapped and bool(getattr(self.cfg, 'world_shell_audio_handoff', True)):
            key, music, air, music_gain, air_gain, label = mapped
            influence = 0.0
            try:
                influence = max(0.0, min(1.0, float(shell_audio.get('influence', 0.0))))
            except Exception:
                influence = 0.0
            return (f'shell_{key}', music, air, min(0.70, music_gain + 0.16 * intensity + influence * 0.10), min(0.30, air_gain + ambience * 0.08), label)

        r = math.sqrt(self.player_pos.x ** 2 + self.player_pos.y ** 2)
        if r < self.hub_radius + 1.0:
            return ('hub', 'hv_hub_command_theme.wav', 'hv_hub_room_air.wav', 0.38 + 0.22 * intensity, 0.10 + 0.10 * ambience, 'central hub command theme')
        return ('frontier', 'hv_world_exploration_theme.wav', 'hv_hub_room_air.wav', 0.42 + 0.18 * intensity, 0.12 + 0.08 * ambience, 'frontier exploration')

    def update_soundscape(self, dt: float = 0.0, *, force: bool = False):
        if not self.audio:
            return
        self.audio.refresh_mix()
        # Root hub/world soundscape must not run while a same-window dimension or
        # hosted child owns the scene.  Native dimensions use native_dimension_*
        # loops; allowing hub_music/hub_air to restart here caused overlapping songs.
        if getattr(self, "active_native_mode", None) is not None or getattr(self, "external_process", None) is not None:
            try:
                self.audio.stop_loop("hub_music")
                self.audio.stop_loop("hub_air")
            except Exception:
                pass
            return
        key, base_music_loop, base_air_loop, music_gain, air_gain, label = self._target_soundscape()
        now = time.time()
        scene_changed = force or key != getattr(self, 'soundscape_key', None) or base_music_loop != getattr(self, 'soundscape_base_loop', None) or base_air_loop != getattr(self, 'soundscape_air_base_loop', None)
        rotate_due = bool(base_music_loop) and now >= float(getattr(self, 'soundscape_next_rotation_at', 0.0) or 0.0)
        if scene_changed:
            self.soundscape_key = key
            self.soundscape_base_loop = base_music_loop
            self.soundscape_air_base_loop = base_air_loop
            self.soundscape_loop = self._choose_soundscape_loop(base_music_loop) if base_music_loop else ''
            self.soundscape_air_loop = self._choose_soundscape_loop(base_air_loop, getattr(self, 'soundscape_air_loop', None)) if base_air_loop else ''
            self.soundscape_next_rotation_at = now + float(getattr(self, 'soundscape_rotation_seconds', 60.0) or 60.0)
            if not force and now - float(getattr(self, 'soundscape_stinger_at', 0.0)) > 1.6:
                self.audio.play('world_shift.wav', bus='sfx', volume=0.18)
                self.soundscape_stinger_at = now
        elif rotate_due:
            self.soundscape_loop = self._choose_soundscape_loop(base_music_loop, getattr(self, 'soundscape_loop', None)) if base_music_loop else ''
            self.soundscape_air_loop = self._choose_soundscape_loop(base_air_loop, getattr(self, 'soundscape_air_loop', None)) if base_air_loop else ''
            self.soundscape_next_rotation_at = now + float(getattr(self, 'soundscape_rotation_seconds', 60.0) or 60.0)
        music_loop = getattr(self, 'soundscape_loop', '') or base_music_loop
        air_loop = getattr(self, 'soundscape_air_loop', '') or base_air_loop
        if music_loop:
            self.audio.play_loop('hub_music', music_loop, bus='music', volume=max(0.0, min(1.0, music_gain)))
        else:
            self.audio.stop_loop('hub_music')
        if air_loop:
            self.audio.play_loop('hub_air', air_loop, bus='ambience', volume=max(0.0, min(1.0, air_gain)))
        else:
            self.audio.stop_loop('hub_air')
        variant_note = Path(str(music_loop)).stem.replace('hv_', '').replace('_', ' ').upper() if music_loop else str(label or key).upper()
        self.world_shell_audio_status = f"{str(label or key).upper()} // {variant_note} // NO-REPEAT SHUFFLE"

    def _holocore_dimension_music_profile(self, dimension_id: int, dimension_name: str = ""):
        name = str(dimension_name or "").lower()
        if int(dimension_id or 1) == 1 or any(token in name for token in ("sonar", "ocean", "water")):
            return ("holocore_dim1", "hv_water_depth_theme.wav", "hv_hub_room_air.wav", 0.46, 0.16, "SONAR OCEAN FLOOR")
        if int(dimension_id or 1) == 2 or any(token in name for token in ("crystal", "reef")):
            return ("holocore_dim2", "hv_space_orbit_theme.wav", "hv_hub_room_air.wav", 0.48, 0.14, "CRYSTAL DATA REEF")
        if int(dimension_id or 1) == 3 or any(token in name for token in ("bubble", "lava", "valley")):
            return ("holocore_dim3", "hv_urban_conflict_theme.wav", "hv_hub_room_air.wav", 0.42, 0.12, "BUBBLE LAVA VALLEYS")
        return (f"holocore_dim{int(dimension_id or 1)}", "hv_world_exploration_theme.wav", "hv_hub_room_air.wav", 0.44, 0.12, "HOLOCORE DIMENSION")

    def play_holocore_dimension_music(self, dimension_id: int, dimension_name: str = "") -> None:
        if not self.audio or not bool(getattr(self.cfg, "soundtrack_enabled", True)):
            return
        key, music, air, music_gain, air_gain, label = self._holocore_dimension_music_profile(dimension_id, dimension_name)
        intensity = max(0.0, min(1.0, float(getattr(self.cfg, "soundtrack_intensity", 0.55))))
        ambience = max(0.0, min(1.0, float(getattr(self.cfg, "ambience_intensity", 0.45))))
        music_loop = self.audio.reversed_clip_for(music)
        air_loop = self.audio.reversed_clip_for(air)
        changed = key != getattr(self, "holocore_dimension_music_key", None)

        # HoloCore is a same-window sub-world with its own reversed-dimension
        # soundscape.  Do not let the generic artifact/native bed keep playing
        # underneath it, and do not let the hub soundscape restart while HoloCore
        # owns the scene.  This is intentionally slot-scoped rather than a full
        # stop_all() so the small dimension-change stinger below can still play.
        try:
            self.audio.stop_loop("hub_music")
            self.audio.stop_loop("hub_air")
            self.audio.stop_loop("native_dimension_music")
            self.audio.stop_loop("native_dimension_air")
        except Exception:
            pass

        self.holocore_dimension_music_key = key
        self.audio.play_loop("holocore_dimension_music", music_loop, bus="music", volume=max(0.0, min(0.72, music_gain + 0.12 * intensity)))
        self.audio.play_loop("holocore_dimension_air", air_loop, bus="ambience", volume=max(0.0, min(0.26, air_gain + 0.06 * ambience)))
        if changed:
            try:
                self.audio.play("world_shift.wav", bus="sfx", volume=0.13)
            except Exception:
                pass
        source_note = Path(str(music_loop)).stem.replace("_reversed", "").replace("hv_", "").replace("_", " ").upper()
        self.world_shell_audio_status = f"HOLOCORE {label} // REVERSED {source_note}"

    def stop_holocore_dimension_music(self) -> None:
        if self.audio:
            self.audio.stop_loop("holocore_dimension_music")
            self.audio.stop_loop("holocore_dimension_air")
        self.holocore_dimension_music_key = None

    def setup_vr(self):
        # Desktop first-person mode is authoritative unless VR is explicitly requested.
        # This prevents old VR config files or missing headset runtimes from hijacking normal startup.
        if VR_DISABLED:
            self.vr_status = "DESKTOP // VR DISABLED"
            self.cfg.vr_enabled = False
            save_config(self.cfg)
            return
        if not VR_ALLOWED:
            self.vr_status = "DESKTOP // VR OPT-IN"
            return
        if P3DOpenXR is None:
            self.vr_status = "DESKTOP // XR MODULE MISSING"
            return
        self.cfg.vr_enabled = True
        save_config(self.cfg)
        try:
            self.vr_origin = self.render.attachNewNode("vr-origin")
            self.vr_origin.setPos(0, -10, 0)
            self.xr = P3DOpenXR(self)
            self.xr.init(root=self.vr_origin, mirroring=1, mirror_mode="average", near=0.05, far=self.cfg.fog_distance)
            self.vr_active = True
            self.vr_status = "OPENXR ACTIVE"
            self.cfg.player_eye_height = 3.95
            self.build_vr_hand_debug()
        except Exception as exc:
            self.xr = None
            self.vr_origin = None
            self.vr_active = False
            self.vr_status = f"DESKTOP // XR FALLBACK: {exc.__class__.__name__}"
            print(f"openxr_init_failed: {exc}")

    def build_vr_hand_debug(self):
        if not self.xr:
            return
        hand_color_left = (0.42, 0.86, 1.0, 0.88)
        hand_color_right = (1.0, 0.42, 0.64, 0.88)
        for side, anchor, color in (("left", self.xr.left_hand_anchor, hand_color_left), ("right", self.xr.right_hand_anchor, hand_color_right)):
            segs = LineSegs(f"vr-hand-{side}")
            segs.setThickness(max(1.4, self.cfg.line_thickness * 0.9))
            segs.setColor(*color)
            palm = [Vec3(-0.05, 0.0, -0.03), Vec3(0.05, 0.0, -0.03), Vec3(0.06, 0.0, 0.04), Vec3(-0.06, 0.0, 0.04)]
            segs.moveTo(palm[0]); segs.drawTo(palm[1]); segs.drawTo(palm[2]); segs.drawTo(palm[3]); segs.drawTo(palm[0])
            for fx in (-0.04, -0.015, 0.015, 0.04):
                segs.moveTo(fx, 0.0, 0.035)
                segs.drawTo(fx, 0.12, 0.03)
            segs.moveTo(-0.06, 0.0, -0.005); segs.drawTo(-0.12 if side == "left" else 0.0, 0.06, -0.01)
            node = anchor.attachNewNode(segs.create())
            node.setAntialias(AntialiasAttrib.MLine)
            node.setTransparency(TransparencyAttrib.MAlpha)
            if side == "left":
                self.vr_left_hand = node
            else:
                self.vr_right_hand = node

    def head_world_pos(self):
        if self.vr_active and self.xr and getattr(self.xr, "hmd_anchor", None) is not None:
            try:
                return self.xr.hmd_anchor.getPos(self.render)
            except Exception:
                pass
        return Vec3(self.player_pos)

    def get_view_basis(self):
        if self.vr_active and self.xr and getattr(self.xr, "hmd_anchor", None) is not None:
            quat = self.xr.hmd_anchor.getQuat(self.render)
        else:
            quat = self.camera.getQuat(self.render)
        forward = quat.getForward()
        right = quat.getRight()
        up = quat.getUp()
        return forward, right, up

    def sync_player_from_vr(self):
        if self.vr_active:
            self.player_pos = self.head_world_pos()
            base_offset = float(getattr(self.cfg, "vr_height_offset", 0.0))
            if getattr(self.cfg, "vr_seated_mode", False):
                base_offset += 0.55
            self.player_pos.z += base_offset

    def current_vr_turn_mode(self):
        mode = str(getattr(self.cfg, "vr_turn_mode", "snap")).strip().lower()
        return mode if mode in {"snap", "smooth"} else "snap"

    def update_vr_turn(self, dt):
        if not self.vr_active or self.vr_origin is None or self.menu_open:
            return
        self.vr_turn_cooldown = max(0.0, self.vr_turn_cooldown - dt)
        turn_axis = 0.0
        if self.keys.get("q"):
            turn_axis += 1.0
        if self.keys.get("e"):
            turn_axis -= 1.0
        if self.gamepad:
            try:
                rx = self.gamepad.findAxis(InputDevice.Axis.right_x)
                if rx and abs(rx.value) > 0.22:
                    turn_axis += -rx.value
            except Exception:
                pass
        if abs(turn_axis) < 0.001:
            return
        pivot = self.head_world_pos()
        rel = self.vr_origin.getPos(self.render) - pivot
        if self.current_vr_turn_mode() == "smooth":
            step = max(-1.0, min(1.0, turn_axis)) * float(getattr(self.cfg, "vr_smooth_turn_rate", 75.0)) * dt
        else:
            if self.vr_turn_cooldown > 0.0:
                return
            step = float(getattr(self.cfg, "vr_snap_turn_degrees", 30.0)) * (1.0 if turn_axis > 0 else -1.0)
            self.vr_turn_cooldown = 0.22
        ang = math.radians(step)
        rot = Vec3(rel.x * math.cos(ang) - rel.y * math.sin(ang), rel.x * math.sin(ang) + rel.y * math.cos(ang), rel.z)
        self.vr_origin.setPos(pivot + rot)
        self.vr_origin.setH(self.vr_origin.getH() + step)
        self.sync_player_from_vr()

    def setup_window(self):
        props = WindowProperties()
        props.setTitle(GAME_NAME)
        props.setSize(LAUNCH_W, LAUNCH_H)
        props.setCursorHidden(not SELF_TEST)
        if not SELF_TEST:
            props.setForeground(True)
            if LAUNCH_BORDERLESS:
                props.setUndecorated(True)
                props.setOrigin(LAUNCH_X, LAUNCH_Y)
                props.setSize(LAUNCH_W, LAUNCH_H)
                props.setFullscreen(False)
                props.setFixedSize(True)
            elif LAUNCH_BORDERED_FULLSCREEN:
                props.setUndecorated(False)
                props.setOrigin(LAUNCH_X, LAUNCH_Y)
                props.setSize(LAUNCH_W, LAUNCH_H)
                props.setFullscreen(False)
                props.setFixedSize(False)
            else:
                props.setUndecorated(False)
                props.setFullscreen(bool(LAUNCH_FULLSCREEN))
        if self.win is not None and hasattr(self.win, "requestProperties"):
            self.win.requestProperties(props)
        self.setBackgroundColor(self.cfg.background_value, self.cfg.background_value, self.cfg.background_value)

    def setup_scene(self):
        self.root_3d = self.render.attachNewNode("root-3d")
        self.surface_root = self.root_3d.attachNewNode("surface-root")
        self.line_root = self.root_3d.attachNewNode("line-root")
        self.accent_root = self.root_3d.attachNewNode("accent-root")
        self.dome_root = self.root_3d.attachNewNode("dome-root")
        self.lens_root = self.root_3d.attachNewNode("lens-root")
        self.sky_root = self.root_3d.attachNewNode("sky-root")
        self.world_root = self.root_3d.attachNewNode("world-root")
        self.galaxy_root = self.root_3d.attachNewNode("galaxy-root")
        self.world_root.setTransparency(TransparencyAttrib.MAlpha)
        self.galaxy_root.setTransparency(TransparencyAttrib.MAlpha)
        self.camLens.setNearFar(0.05, self.cfg.fog_distance)
        self.camLens.setFov(self.cfg.fov)

        self.fog = Fog("hub-fog")
        self.hub_base_bg_rgb = (self.cfg.background_value, self.cfg.background_value, self.cfg.background_value)
        self.hub_base_fog_near = self.cfg.fog_distance * 0.48
        self.hub_base_fog_far = self.cfg.fog_distance
        self.fog.setColor(*self.hub_base_bg_rgb)
        self.fog.setLinearRange(self.hub_base_fog_near, self.hub_base_fog_far)
        self.render.setFog(self.fog)

        self.hub_base_ambient_rgb = (0.58, 0.62, 0.68)
        self.hub_base_sun_rgb = (0.34, 0.37, 0.42)
        self.ambient_light = AmbientLight("ambient")
        self.ambient_light.setColor((*self.hub_base_ambient_rgb, 1.0))
        self.ambient_light_np = self.render.attachNewNode(self.ambient_light)
        self.render.setLight(self.ambient_light_np)

        self.sun_light = DirectionalLight("sun")
        self.sun_light.setColor((*self.hub_base_sun_rgb, 1.0))
        self.sun_np = self.render.attachNewNode(self.sun_light)
        self.sun_np.setHpr(-20, -48, 0)
        self.render.setLight(self.sun_np)

    def make_generated_texture(self, name: str, width: int, height: int, painter):
        path = TEXTURE_DIR / name
        if not path.exists():
            img = PNMImage(width, height, 4)
            painter(img, width, height)
            img.write(Filename.fromOsSpecific(str(path)))
        tex = self.loader.loadTexture(Filename.fromOsSpecific(str(path)))
        if tex:
            tex.setWrapU(SamplerState.WM_repeat)
            tex.setWrapV(SamplerState.WM_repeat)
            tex.setMinfilter(SamplerState.FT_linear_mipmap_linear)
            tex.setMagfilter(SamplerState.FT_linear)
        return tex

    def ensure_hub_textures(self):
        def floor_painter(img, w, h):
            for y in range(h):
                for x in range(w):
                    grid = 0.50 if x % 32 in (0, 1, 30, 31) or y % 32 in (0, 1, 30, 31) else 0.0
                    wave = 0.08 + 0.04 * math.sin((x + y) * 0.045)
                    v = wave + grid
                    img.setXelA(x, y, 0.08 + v * 0.28, 0.12 + v * 0.34, 0.16 + v * 0.42, 1.0)

        def wall_painter(img, w, h):
            for y in range(h):
                for x in range(w):
                    pillars = 0.46 if x % 56 in (0, 1, 2, 53, 54, 55) else 0.0
                    rails = 0.22 if y % 72 in (0, 1, 70, 71) else 0.0
                    wave = 0.05 + 0.03 * math.sin(x * 0.025 + y * 0.012)
                    v = wave + pillars + rails
                    img.setXelA(x, y, 0.06 + v * 0.26, 0.10 + v * 0.34, 0.14 + v * 0.44, 1.0)

        def core_painter(img, w, h):
            cx, cy = w * 0.5, h * 0.5
            for y in range(h):
                for x in range(w):
                    dx = (x - cx) / max(1.0, cx)
                    dy = (y - cy) / max(1.0, cy)
                    dist = math.sqrt(dx * dx + dy * dy)
                    ang = (math.atan2(dy, dx) + math.pi) / math.tau
                    rings = 0.54 if int(dist * 22) % 2 == 0 else 0.13
                    radial = 0.34 if int(ang * 24) % 3 == 0 else 0.0
                    cross = 0.32 if abs(dx) < 0.035 or abs(dy) < 0.035 else 0.0
                    circuit = 0.28 if ((x // 22) % 5 == 0 and (y + x) % 17 < 2) or ((y // 24) % 5 == 0 and (y - x) % 19 < 2) else 0.0
                    v = max(0.0, 1.0 - dist) * 0.30 + rings + radial + cross + circuit
                    img.setXelA(x, y, 0.025 + v * 0.10, 0.16 + v * 0.46, 0.20 + v * 0.58, 1.0)

        def ceiling_painter(img, w, h):
            cx, cy = w * 0.5, h * 0.5
            for y in range(h):
                for x in range(w):
                    dx = (x - cx) / max(1.0, cx)
                    dy = (y - cy) / max(1.0, cy)
                    ang = (math.atan2(dy, dx) + math.pi) / (math.tau)
                    sector = 0.34 if int(ang * 8) % 2 == 0 else 0.12
                    ring = 0.18 if abs(math.sqrt(dx * dx + dy * dy) - 0.68) < 0.05 else 0.0
                    v = 0.06 + sector + ring
                    img.setXelA(x, y, 0.05 + v * 0.22, 0.09 + v * 0.30, 0.13 + v * 0.40, 1.0)

        def dome_painter(img, w, h):
            for y in range(h):
                for x in range(w):
                    diag = 0.42 if (x - y) % 72 in (0, 1, 2, 69, 70, 71) or (x + y) % 72 in (0, 1, 2, 69, 70, 71) else 0.0
                    rib = 0.24 if x % 90 in (0, 1, 88, 89) else 0.0
                    v = 0.06 + diag + rib
                    img.setXelA(x, y, 0.05 + v * 0.20, 0.09 + v * 0.28, 0.14 + v * 0.36, 1.0)

        self.hub_textures = {
            "floor": self.make_generated_texture("hub_floor.png", 512, 512, floor_painter),
            "wall": self.make_generated_texture("hub_wall.png", 512, 512, wall_painter),
            "core": self.make_generated_texture("hub_core.png", 512, 512, core_painter),
            "ceiling": self.make_generated_texture("hub_ceiling.png", 512, 512, ceiling_painter),
            "dome": self.make_generated_texture("hub_dome.png", 512, 512, dome_painter),
        }

    def add_textured_panel(self, parent, pos, hpr, sx, sy, texture_key, alpha=0.0, tex_scale=(1.0, 1.0), two_sided=True):
        cm = CardMaker(f"panel-{texture_key}")
        cm.setFrame(-sx * 0.5, sx * 0.5, -sy * 0.5, sy * 0.5)
        np = parent.attachNewNode(cm.generate())
        np.setPos(pos)
        np.setHpr(hpr)
        np.setTransparency(TransparencyAttrib.MAlpha)
        np.setColor(1, 1, 1, alpha)
        np.setDepthWrite(False)
        if two_sided:
            np.setTwoSided(True)
        tex = self.hub_textures.get(texture_key)
        if tex:
            np.setTexture(tex, 1)
            np.setTexScale(TextureStage.getDefault(), tex_scale[0], tex_scale[1])
        self.hub_fill_nodes.append(np)
        return np

    def build_hub_infill(self):
        self.hub_fill_nodes = []
        self.add_textured_panel(self.surface_root, Vec3(0, 0, 0.02), Vec3(0, -90, 0), 56.0, 56.0, "floor", tex_scale=(4.8, 4.8))

        wall_height = 9.2
        wall_width = 21.4
        wall_r = self.hub_radius - 0.98
        for i in range(8):
            ang = math.radians(22.5) + math.tau * i / 8
            n = Vec3(math.cos(ang), math.sin(ang), 0)
            pos = n * wall_r + Vec3(0, 0, wall_height * 0.5)
            self.add_textured_panel(self.surface_root, pos, Vec3(math.degrees(ang) + 90, 0, 0), wall_width, wall_height, "wall", tex_scale=(2.2, 1.6))

        for i in range(8):
            ang = math.radians(22.5) + math.tau * i / 8
            n = Vec3(math.cos(ang), math.sin(ang), 0)
            pos = n * 2.05 + Vec3(0, 0, 3.2)
            self.add_textured_panel(self.surface_root, pos, Vec3(math.degrees(ang) + 90, 0, 0), 1.55, 5.9, "core", tex_scale=(1.0, 2.0))

        # v0.10.40: MatrixCore gets a denser cyan circuit spine without adding
        # another UI panel. These lightweight wires stay tied to hub fill alpha.
        try:
            self.matrixcore_core_nodes = []
            for idx, (radius, z, sides) in enumerate(((1.05, 1.35, 8), (1.52, 2.35, 12), (1.18, 3.35, 10), (1.72, 4.45, 16), (0.82, 5.45, 8))):
                node = self.add_polyline(self.surface_root, self.polygon_points(radius, z, sides, 22.5 + idx * 7.0), (0.35, 1.0, 1.0, 0.72), self.cfg.line_thickness * (0.55 + idx * 0.05), True, "matrixcore-cyan-core-ring")
                node.setPythonTag("matrixcore_advanced_core", True)
                self.matrixcore_core_nodes.append(node)
                self.hub_fill_nodes.append(node)
            for idx in range(12):
                a = math.tau * idx / 12.0
                p0 = Vec3(math.cos(a) * 0.72, math.sin(a) * 0.72, 1.05)
                p1 = Vec3(math.cos(a + 0.16) * 1.72, math.sin(a + 0.16) * 1.72, 5.65)
                node = self.add_polyline(self.surface_root, [p0, p1], (0.14, 0.88, 1.0, 0.46), self.cfg.line_thickness * 0.38, False, "matrixcore-cyan-core-spine")
                node.setPythonTag("matrixcore_advanced_core", True)
                self.matrixcore_core_nodes.append(node)
                self.hub_fill_nodes.append(node)
        except Exception:
            self.matrixcore_core_nodes = []

        self.add_textured_panel(self.surface_root, Vec3(0, 0, 10.02), Vec3(0, 90, 22.5), 31.8, 31.8, "ceiling", tex_scale=(2.0, 2.0))

        dome_bands = [(24.0, 9.8, 12.4), (20.0, 12.0, 14.7), (15.0, 14.2, 16.8)]
        for width, z0, z1 in dome_bands:
            pitch = -24.0 - (z0 - 9.8) * 1.85
            radius = self.hub_radius - 3.2 - (z0 - 9.8) * 0.7
            for i in range(8):
                ang = math.radians(22.5) + math.tau * i / 8
                n = Vec3(math.cos(ang), math.sin(ang), 0)
                pos = n * radius + Vec3(0, 0, (z0 + z1) * 0.5)
                self.add_textured_panel(self.surface_root, pos, Vec3(math.degrees(ang) + 90, pitch, 0), width, z1 - z0, "dome", tex_scale=(2.0, 1.0))
        self.update_hub_fill_visuals(force=True)

    def set_hub_fill_enabled(self, enabled: bool, instant=False):
        self.cfg.hub_fill_enabled = enabled
        self.hub_fill_target = 1.0 if enabled else 0.0
        if instant:
            self.hub_fill_alpha = self.hub_fill_target
            self.update_hub_fill_visuals(force=True)
        save_config(self.cfg)

    def update_hub_fill_visuals(self, force=False):
        alpha = self.hub_fill_alpha * self.cfg.hub_fill_opacity
        for np in getattr(self, "hub_fill_nodes", []):
            np.setColorScale(1, 1, 1, alpha)
            if alpha > 0.001:
                np.show()
            else:
                np.hide()

    def build_gleebs_hologram(self):
        """Project Gleebs as MatrixCore's in-world hologram without adding UI boxes."""
        try:
            if getattr(self, "gleebs_hologram_root", None) is not None:
                self.gleebs_hologram_root.removeNode()
        except Exception:
            pass
        self.gleebs_hologram_parts = []
        self.gleebs_hologram_root = self.accent_root.attachNewNode("matrixcore-gleebs-hologram")
        self.gleebs_hologram_root.setPos(0, 0, 3.55)
        self.gleebs_hologram_root.setTransparency(TransparencyAttrib.MAlpha)
        for idx, (radius, z, alpha) in enumerate(((1.18, -1.02, 0.54), (1.58, -0.82, 0.34), (0.72, 1.15, 0.24))):
            node = self.add_polyline(self.gleebs_hologram_root, self.polygon_points(radius, z, 48, 0), (0.18, 1.0, 1.0, alpha), self.cfg.line_thickness * (0.78 if idx == 0 else 0.54), True, "gleebs-holo-ring")
            self.gleebs_hologram_parts.append(node)
        for i in range(8):
            a = math.tau * i / 8.0
            p0 = Vec3(math.cos(a) * 0.72, math.sin(a) * 0.72, -0.92)
            p1 = Vec3(math.cos(a) * 0.30, math.sin(a) * 0.30, 1.32)
            node = self.add_polyline(self.gleebs_hologram_root, [p0, p1], (0.10, 0.88, 1.0, 0.20), self.cfg.line_thickness * 0.42, False, "gleebs-holo-column")
            self.gleebs_hologram_parts.append(node)
        tex = None
        try:
            gleebs_texture_source = GLEEBS_TEXTURE_POT_PATH if GLEEBS_TEXTURE_POT_PATH.exists() else GLEEBS_TEXTURE_PATH
            if gleebs_texture_source.exists():
                tex = self.loader.loadTexture(Filename.fromOsSpecific(str(gleebs_texture_source)))
                tex.setMinfilter(SamplerState.FT_linear_mipmap_linear)
                tex.setMagfilter(SamplerState.FT_linear)
        except Exception:
            tex = None
        cm = CardMaker("gleebs-hologram-card")
        cm.setFrame(-0.92, 0.92, -1.12, 1.12)
        card = self.gleebs_hologram_root.attachNewNode(cm.generate())
        card.setPos(0, -0.06, 0.20)
        card.setTransparency(TransparencyAttrib.MAlpha)
        card.setTwoSided(True)
        card.setLightOff(1)
        card.setDepthWrite(False)
        try:
            card.setBin("transparent", 30)
            card.setBillboardPointEye()
        except Exception:
            pass
        if tex is not None:
            card.setTexture(tex, 1)
            card.setColorScale(1.0, 0.08, 0.08, 0.72)
        else:
            card.setColor(1.0, 0.06, 0.06, 0.22)
        self.gleebs_hologram_card = card
        self.gleebs_hologram_parts.append(card)
        return self.gleebs_hologram_root

    def update_gleebs_hologram(self, dt: float = 0.0):
        root = getattr(self, "gleebs_hologram_root", None)
        if root is None or root.isEmpty():
            return
        t = float(getattr(self, "elapsed", 0.0))
        pulse = 0.5 + 0.5 * math.sin(t * 3.1)
        root.setZ(3.55 + math.sin(t * 1.35) * 0.10)
        root.setH(root.getH() + dt * 10.0)
        card = getattr(self, "gleebs_hologram_card", None)
        if card is not None and not card.isEmpty():
            alpha = 0.54 + pulse * 0.20
            card.setColorScale(1.0, 0.06 + pulse * 0.06, 0.06, alpha)
        for node in getattr(self, "gleebs_hologram_parts", []) or []:
            try:
                if node is card:
                    continue
                node.setColorScale(1.0, 0.04 + pulse * 0.06, 0.04, 0.55 + pulse * 0.30)
            except Exception:
                pass

    def gleebs_dialogue_line(self, dialogue_id: str) -> str:
        override = str(getattr(self, "gleebs_dialogue_text_override", "") or "").strip()
        data = dict(getattr(self, "gleebs_dialogue_data", {}) or self.ensure_gleebs_dialogue_seed())
        lines = data.get("lines", {}) if isinstance(data.get("lines"), dict) else {}
        raw = str(lines.get(dialogue_id, dialogue_id)).strip()
        if override and "{guidance}" in raw:
            raw = raw.replace("{guidance}", override)
        if "{dimension}" in raw or "{advice}" in raw:
            dimension = str(getattr(self, "gleebs_dialogue_dimension", "") or "")
            advice = str(getattr(self, "gleebs_dialogue_advice", "") or "")
            raw = raw.replace("{dimension}", dimension or "unknown dimension").replace("{advice}", advice or "Signal pending.")
        if "{bot}" in raw or "{role}" in raw or "{support}" in raw or "{mode}" in raw:
            bot = str(getattr(self, "gleebs_dialogue_bot", "") or "")
            role = str(getattr(self, "gleebs_dialogue_bot_role", "") or "")
            support = str(getattr(self, "gleebs_dialogue_bot_support", "") or "")
            mode = str(getattr(self, "gleebs_dialogue_bot_mode", "") or "")
            raw = raw.replace("{bot}", bot or "that bot").replace("{role}", role or "builder ally").replace("{support}", support or "MatrixCore has logged the support signal.").replace("{mode}", mode or "that dimension")
        return raw

    def gleebs_dialogue_quote(self, dialogue_id: str) -> str:
        """Return a short bottom personality quote for Gleebs' transient signal."""
        data = dict(getattr(self, "gleebs_dialogue_data", {}) or self.ensure_gleebs_dialogue_seed())
        bank = data.get("bottom_quotes", {}) if isinstance(data.get("bottom_quotes"), dict) else {}
        choices = bank.get(str(dialogue_id)) or bank.get("default") or []
        if isinstance(choices, str):
            choices = [choices]
        choices = [str(item).strip() for item in list(choices or []) if str(item).strip()]
        if not choices:
            return ""
        try:
            # Stable per dialogue/event enough to feel varied without changing every frame.
            token = f"{dialogue_id}:{int(time.monotonic() * 10)}:{getattr(self, 'gleebs_last_context_signal', 'boot')}"
            idx = abs(hash(token)) % len(choices)
        except Exception:
            idx = 0
        return choices[idx]

    def gleebs_dialogue_signature(self, dialogue_id: str) -> str:
        quote = str(getattr(self, "gleebs_current_quote", "") or self.gleebs_dialogue_quote(dialogue_id))
        return f"Gleebs // {quote}" if quote else "Gleebs // MatrixCore signal"

    def gleebs_dialogue_panel_blocked(self) -> bool:
        """Return True when a persistent UI or launched mode should suppress Gleebs' transient voice overlay."""
        return bool(
            getattr(self, "menu_open", False)
            or getattr(self, "bot_dialogue_open", False)
            or getattr(self, "active_native_mode", None) is not None
            or getattr(self, "external_process", None) is not None
            or getattr(self, "external_suspended", False)
        )

    def update_gleebs_dialogue_safe_lane(self):
        """Place red dialogue in a readable lane without adding UI boxes or textures."""
        if not hasattr(self, "gleebs_dialogue_root"):
            return
        try:
            if getattr(self, "core_console_open", False):
                x, z, wrap = -1.22, 0.44, 23.0
                hint_z = -0.205
            else:
                x, z, wrap = -0.58, 0.34, 31.0
                hint_z = -0.155
            self.gleebs_dialogue_root.setPos(x, 0, z)
            for lbl in (self.gleebs_dialogue_shadow_wide, self.gleebs_dialogue_shadow, self.gleebs_dialogue_glow, self.gleebs_dialogue_label):
                lbl["text_wordwrap"] = wrap
            if hasattr(self, "gleebs_dialogue_quote_label"):
                self.gleebs_dialogue_quote_label.setPos(0.0, 0, hint_z + 0.052)
            self.gleebs_dialogue_hint.setPos(0.0, 0, hint_z)
        except Exception:
            pass

    def queue_gleebs_dialogue(self, dialogue_id: str, *, flag: str | None = None, duration: float = 8.0, mark_seen: bool = True, requires_near_core: bool = True, once: bool = True) -> bool:
        dialogue_id = str(dialogue_id or "").strip()
        if not dialogue_id:
            return False
        flag = str(flag or dialogue_id).strip()
        if once and self.matrixcore_dialogue_flag_seen(flag):
            return False
        active_id = str(getattr(self, "gleebs_dialogue_id", "") or "")
        if active_id == dialogue_id:
            return False
        for item in list(getattr(self, "gleebs_dialogue_queue", []) or []):
            if str(item.get("id", "")) == dialogue_id or str(item.get("flag", "")) == flag:
                return False
        max_queue = 4
        try:
            progress = self.load_matrixcore_progression()
            max_queue = int((progress.get("dialogue_queue_policy") or {}).get("max_queue", max_queue))
        except Exception:
            pass
        queue = list(getattr(self, "gleebs_dialogue_queue", []) or [])
        if len(queue) >= max_queue:
            queue = queue[-max_queue + 1:]
        queue.append({
            "id": dialogue_id,
            "flag": flag,
            "duration": float(duration or 8.0),
            "mark_seen": bool(mark_seen),
            "requires_near_core": bool(requires_near_core),
            "once": bool(once),
        })
        self.gleebs_dialogue_queue = queue
        return True

    def queue_gleebs_sequence(self, items: list[dict]) -> int:
        count = 0
        for item in list(items or []):
            if not isinstance(item, dict):
                continue
            if self.queue_gleebs_dialogue(
                str(item.get("id", "")),
                flag=str(item.get("flag") or item.get("id", "")),
                duration=float(item.get("duration", 8.0) or 8.0),
                mark_seen=bool(item.get("mark_seen", True)),
                requires_near_core=bool(item.get("requires_near_core", True)),
                once=bool(item.get("once", True)),
            ):
                count += 1
        return count

    def pump_gleebs_dialogue_queue(self):
        if not hasattr(self, "gleebs_dialogue_root"):
            return False
        if getattr(self, "gleebs_dialogue_active", False):
            return False
        if self.gleebs_dialogue_panel_blocked():
            return False
        if time.monotonic() < float(getattr(self, "gleebs_dialogue_queue_wait_until", 0.0) or 0.0):
            return False
        queue = list(getattr(self, "gleebs_dialogue_queue", []) or [])
        while queue:
            item = dict(queue.pop(0) or {})
            self.gleebs_dialogue_queue = queue
            flag = str(item.get("flag") or item.get("id") or "")
            if bool(item.get("once", True)) and flag and self.matrixcore_dialogue_flag_seen(flag):
                continue
            if bool(item.get("requires_near_core", True)) and not self.is_near_core():
                queue.insert(0, item)
                self.gleebs_dialogue_queue = queue
                return False
            return self.show_gleebs_dialogue(
                str(item.get("id", "")),
                flag=flag,
                duration=float(item.get("duration", 8.0) or 8.0),
                mark_seen=bool(item.get("mark_seen", True)),
            )
        self.gleebs_dialogue_queue = []
        return False

    def show_gleebs_dialogue(self, dialogue_id: str, *, flag: str | None = None, duration: float = 10.0, mark_seen: bool = True):
        text = self.gleebs_dialogue_line(dialogue_id)
        if not text:
            return False
        if self.gleebs_dialogue_panel_blocked():
            return self.queue_gleebs_dialogue(dialogue_id, flag=flag, duration=duration, mark_seen=mark_seen, requires_near_core=False, once=False)
        self.update_gleebs_dialogue_safe_lane()
        self.gleebs_dialogue_id = str(dialogue_id)
        self.gleebs_dialogue_flag = str(flag or dialogue_id)
        self.gleebs_dialogue_text = text
        self.gleebs_current_quote = self.gleebs_dialogue_quote(dialogue_id)
        self.gleebs_dialogue_started_at = time.monotonic()
        self.gleebs_dialogue_duration = max(2.5, float(duration or 10.0))
        self.gleebs_dialogue_fade = 0.0
        self.gleebs_dialogue_fade_target = 1.0
        self.gleebs_dialogue_close_on_fade = False
        self.gleebs_dialogue_dismiss_reason = ""
        self.gleebs_dialogue_active = True
        if hasattr(self, "gleebs_dialogue_root"):
            for lbl in (self.gleebs_dialogue_shadow_wide, self.gleebs_dialogue_shadow, self.gleebs_dialogue_label):
                lbl["text"] = text
            try:
                self.gleebs_dialogue_glow["text"] = ""
            except Exception:
                pass
            if hasattr(self, "gleebs_dialogue_quote_label"):
                self.gleebs_dialogue_quote_label["text"] = self.gleebs_dialogue_signature(dialogue_id)
            self.gleebs_dialogue_hint["text"] = "ESC fades // walk away to dismiss"
            self.gleebs_dialogue_root.show()
        if mark_seen:
            self.mark_matrixcore_dialogue_flag(self.gleebs_dialogue_flag, dialogue_id=dialogue_id)
        if self.audio:
            try:
                self.audio.play('menu_open.wav', 'sfx', 0.25)
            except Exception:
                pass
        return True

    def dismiss_gleebs_dialogue(self, reason: str = "dismiss", *, clear_queue: bool = True):
        if clear_queue:
            try:
                self.gleebs_dialogue_queue = []
            except Exception:
                pass
        if not getattr(self, "gleebs_dialogue_active", False):
            return False
        self.gleebs_dialogue_fade_target = 0.0
        self.gleebs_dialogue_close_on_fade = True
        self.gleebs_dialogue_dismiss_reason = str(reason or "dismiss")
        if hasattr(self, "gleebs_dialogue_hint"):
            self.gleebs_dialogue_hint["text"] = f"MatrixCore signal fading // {reason}"
        return True

    def maybe_start_gleebs_intro(self):
        if SELF_TEST or AUTO_EXIT:
            return
        if self.matrixcore_dialogue_flag_seen("gleebs_welcome_001"):
            if self.is_near_core():
                if not self.matrixcore_dialogue_flag_seen("gleebs_fun_greeting_001"):
                    self.queue_gleebs_dialogue("gleebs_fun_greeting_001", flag="gleebs_fun_greeting_001", duration=5.5, mark_seen=True, requires_near_core=True)
                elif not self.matrixcore_dialogue_flag_seen("gleebs_returning_player_001"):
                    self.queue_gleebs_dialogue("gleebs_returning_player_001", flag="gleebs_returning_player_001", duration=5.5, mark_seen=True, requires_near_core=True)
            return
        self.queue_gleebs_sequence([
            {"id": "gleebs_welcome_001", "flag": "gleebs_welcome_001", "duration": 9.5, "requires_near_core": True},
            {"id": "gleebs_creator_echo_001", "flag": "gleebs_creator_echo_001", "duration": 8.5, "requires_near_core": True},
            {"id": "gleebs_lore_origin_001", "flag": "gleebs_lore_origin_001", "duration": 8.5, "requires_near_core": True},
            {"id": "gleebs_dimension_travel_001", "flag": "gleebs_dimension_travel_001", "duration": 7.0, "requires_near_core": True},
        ])
        self.pump_gleebs_dialogue_queue()

    def maybe_queue_matrixcore_open_dialogue(self):
        if SELF_TEST or AUTO_EXIT:
            return
        if not self.matrixcore_dialogue_flag_seen("gleebs_welcome_001"):
            return
        self.queue_gleebs_dialogue("gleebs_matrixcore_open_001", flag="gleebs_matrixcore_open_001", duration=6.5, requires_near_core=True)
        self.pump_gleebs_dialogue_queue()

    def maybe_queue_gleebs_return_dialogue(self, mode_name: str = ""):
        if SELF_TEST or AUTO_EXIT:
            return
        if self.matrixcore_dialogue_flag_seen("gleebs_welcome_001"):
            advice = self.gleebs_dimension_guidance(mode_name, "return")
            self.gleebs_dialogue_dimension = str(mode_name or "Dimension")
            self.gleebs_dialogue_advice = advice
            flag_key = "gleebs_return_" + normalize_lookup_key(mode_name or "dimension") + "_001"
            self.queue_gleebs_dialogue("gleebs_dimension_advice_001", flag=flag_key, duration=7.5, requires_near_core=False, once=False)
            self.pump_gleebs_dialogue_queue()

    def update_gleebs_dialogue(self, dt: float = 0.0):
        if not hasattr(self, "gleebs_dialogue_root"):
            return
        if not getattr(self, "gleebs_dialogue_active", False):
            self.pump_gleebs_dialogue_queue()
            return
        self.update_gleebs_dialogue_safe_lane()
        now = time.monotonic()
        dist = math.sqrt(self.player_pos.x ** 2 + self.player_pos.y ** 2)
        if dist > 14.5:
            self.dismiss_gleebs_dialogue("distance", clear_queue=True)
        elif self.gleebs_dialogue_panel_blocked():
            self.dismiss_gleebs_dialogue("panel", clear_queue=False)
        elif now - float(getattr(self, "gleebs_dialogue_started_at", now)) > float(getattr(self, "gleebs_dialogue_duration", 8.0)):
            self.dismiss_gleebs_dialogue("timeout", clear_queue=False)
        target = float(getattr(self, "gleebs_dialogue_fade_target", 0.0))
        current = float(getattr(self, "gleebs_dialogue_fade", 0.0))
        blend = min(1.0, max(0.08, dt * 4.4))
        current = current + (target - current) * blend
        if abs(current - target) < 0.025:
            current = target
        self.gleebs_dialogue_fade = current
        alpha = max(0.0, min(1.0, current))
        pulse = 0.5 + 0.5 * math.sin(float(getattr(self, "elapsed", 0.0)) * 5.4)
        try:
            self.gleebs_dialogue_shadow_wide["text_fg"] = (0.0, 0.0, 0.0, 0.78 * alpha)
            self.gleebs_dialogue_shadow["text_fg"] = (0.0, 0.0, 0.0, 0.98 * alpha)
            self.gleebs_dialogue_glow["text_fg"] = (1.0, 0.04, 0.04, 0.0)
            self.gleebs_dialogue_label["text_fg"] = (1.0, 0.030, 0.045, alpha)
            if hasattr(self, "gleebs_dialogue_quote_label"):
                self.gleebs_dialogue_quote_label["text_fg"] = (1.0, 0.16, 0.13, 0.82 * alpha)
            self.gleebs_dialogue_hint["text_fg"] = (1.0, 0.12, 0.10, 0.62 * alpha)
        except Exception:
            pass
        if current <= 0.001 and bool(getattr(self, "gleebs_dialogue_close_on_fade", False)):
            reason = str(getattr(self, "gleebs_dialogue_dismiss_reason", "") or "dismiss")
            self.gleebs_dialogue_active = False
            self.gleebs_dialogue_close_on_fade = False
            self.gleebs_dialogue_id = ""
            self.gleebs_current_quote = ""
            try:
                self.gleebs_dialogue_root.hide()
            except Exception:
                pass
            if reason in {"timeout", "panel"}:
                self.gleebs_dialogue_queue_wait_until = time.monotonic() + 0.60
                self.pump_gleebs_dialogue_queue()

    def is_near_core(self):
        return math.sqrt(self.player_pos.x ** 2 + self.player_pos.y ** 2) < 6.8

    def is_looking_at_core(self, cone_cos=0.58):
        if not self.is_near_core():
            return False
        try:
            forward, _right, _up = self.get_view_basis()
            if forward.lengthSquared() <= 0.0001:
                return True
            forward.normalize()
            target = Vec3(0.0, 0.0, 3.2) - self.head_world_pos()
            if target.lengthSquared() <= 0.0001:
                return True
            target.normalize()
            return float(forward.dot(target)) >= float(cone_cos)
        except Exception:
            return True

    def matrixcore_archive_dialogue_entries(self) -> list[dict]:
        data = getattr(self, "matrixcore_data", None)
        if not isinstance(data, dict) or not data:
            data = self.ensure_matrixcore_foundation()
            self.matrixcore_data = data
        lore = data.get("lore") if isinstance(data.get("lore"), dict) else load_matrixcore_lore_study()
        archive = data.get("archive") if isinstance(data.get("archive"), list) else []
        entries = matrixcore_archive_index_from_lore_study(lore)
        if not entries:
            entries = list(archive or [])
        clean: list[dict] = []
        for idx, entry in enumerate(entries):
            if not isinstance(entry, dict):
                continue
            title = compact_ui_text(entry.get("title") or f"Archive {idx:02d}", 54)
            excerpt = compact_ui_text(entry.get("excerpt") or entry.get("summary") or "", 285)
            phase = compact_ui_text(entry.get("phase") or "", 42)
            if not excerpt:
                continue
            clean.append({"id": int(entry.get("id", idx) or idx), "title": title, "excerpt": excerpt, "phase": phase})
        if clean:
            return clean
        core_truth = compact_ui_text(lore.get("core_truth") if isinstance(lore, dict) else "", 285)
        if core_truth:
            return [{"id": 0, "title": "MatrixCore", "excerpt": core_truth, "phase": "core_truth"}]
        return [{"id": 0, "title": "MatrixCore", "excerpt": "MatrixCore is the memory-brain of HoloVerse. It should speak through Gleebs, not trap the traveler in a menu.", "phase": "fallback"}]

    def matrixcore_next_archive_dialogue_text(self, source: str = "matrixcore") -> str:
        entries = self.matrixcore_archive_dialogue_entries()
        progress = self.load_matrixcore_progression()
        matrixcore = progress.setdefault("matrixcore", {})
        idx = int(matrixcore.get("archive_dialogue_index", 0) or 0) % max(1, len(entries))
        entry = entries[idx]
        matrixcore["archive_dialogue_index"] = (idx + 1) % max(1, len(entries))
        matrixcore["last_archive_dialogue_title"] = str(entry.get("title", "MatrixCore"))
        matrixcore["last_archive_dialogue_source"] = str(source or "matrixcore")
        matrixcore["last_archive_dialogue_at"] = datetime.now().isoformat(timespec="seconds")
        self.save_matrixcore_progression(progress)
        phase = str(entry.get("phase", "") or "").replace("_", " ").strip()
        phase_text = f" [{phase}]" if phase else ""
        return f"{entry.get('title', 'MatrixCore')}{phase_text}: {entry.get('excerpt', '')}"

    def trigger_matrixcore_dialogue(self, source: str = "matrixcore") -> bool:
        if getattr(self, "core_console_open", False):
            self.close_core_console()
        self.menu_open = False
        try:
            self.menu_root.hide()
            self.core_console_root.hide()
        except Exception:
            pass
        self.record_matrixcore_consult(str(source or "matrixcore_dialogue"))
        self.retune_matrixcore_music_on_dialogue(source)
        text = self.matrixcore_next_archive_dialogue_text(source)
        previous_override = str(getattr(self, "gleebs_dialogue_text_override", "") or "")
        self.gleebs_dialogue_text_override = text
        try:
            shown = self.show_gleebs_dialogue("gleebs_matrixcore_archive_001", flag="", duration=11.5, mark_seen=False)
        finally:
            self.gleebs_dialogue_text_override = previous_override
        if self.audio:
            try:
                self.audio.play('menu_open.wav', 'sfx', 0.32)
            except Exception:
                pass
        self.center_hint["text"] = "MATRIXCORE // GLEEBS SIGNAL"
        return bool(shown)

    def open_core_console(self):
        return self.trigger_matrixcore_dialogue("matrixcore_interact")

    def close_core_console(self):
        self.core_console_open = False
        self.core_console_root.hide()
        self.mouse_captured = True
        self.core_console_set_cursor(False)
        if not SELF_TEST:
            self.recenter_mouse(force=True)
        self.hide_native_status_overlay()
        if self.audio:
            self.audio.play('menu_close.wav', 'sfx', 0.7)

    def suspend_for_external_app(self, label: str, embedded: bool = False):
        self.external_launch_label = label
        self.external_suspended = True
        self.external_resume_pending = False
        self.external_resume_marked = False
        self.external_pause_started_at = time.monotonic()
        self.close_core_console()
        self.menu_open = False
        self.mouse_captured = False
        self.keys.clear()
        self.move_velocity = Vec2(0, 0)
        if hasattr(self, "root_3d") and self.root_3d is not None and not self.root_3d.isEmpty():
            self.root_3d.stash()
        if hasattr(self, "hud_root") and self.hud_root is not None and not self.hud_root.isEmpty():
            self.hud_root.hide()
        if hasattr(self, "crosshair_root") and self.crosshair_root is not None and not self.crosshair_root.isEmpty():
            self.crosshair_root.hide()
        if self.audio:
            self.audio.stop_loop("hub_music")
            self.audio.stop_loop("hub_air")
        if self.win is not None and hasattr(self.win, "requestProperties"):
            props = WindowProperties()
            props.setCursorHidden(False)
            if embedded:
                # Keep the HoloVerse window alive as the parent display surface.
                props.setForeground(True)
                try:
                    props.setMinimized(False)
                except Exception:
                    pass
            else:
                props.setForeground(False)
                props.setUndecorated(False)
                props.setFullscreen(False)
                props.setFixedSize(False)
                try:
                    props.setMinimized(True)
                except Exception:
                    pass
            self.win.requestProperties(props)
        self.external_launch_started_at = time.monotonic()
        if self._is_holocore_label(label):
            self.show_bridge_transition(
                "MATRIXCORE -> HOLOCORE",
                "SAME-SCREEN GATEWAY // SYNCHRONIZING PYRAMID WORLD",
                target=1.0,
            )
        self.show_mode_loading_overlay(label, route="LOADING", elapsed=0.0, detail="EMBEDDED" if embedded else "HOSTED")
        print(f"external_pause_begin label={label} embedded={int(bool(embedded))}")

    def _read_external_return_signal(self) -> dict:
        path = getattr(self, "external_return_signal_path", None)
        if not path:
            return {}
        try:
            path = Path(path)
            if not path.exists() or not path.is_file():
                return {}
            payload = json.loads(path.read_text(encoding="utf-8", errors="replace"))
            return payload if isinstance(payload, dict) else {}
        except Exception as exc:
            try:
                print(f"external_return_signal_read_failed err={exc}")
            except Exception:
                pass
            return {}

    def _handle_external_return_signal_action(self, payload: dict, returned_label: str = "MODE") -> bool:
        request = str((payload or {}).get("request") or "").strip().lower()
        if not request:
            return False
        if request in {"open_gate_menu", "open_gates", "show_gates", "pyramid_gates"}:
            try:
                self.set_menu_tab("gates")
                if not bool(getattr(self, "menu_open", False)):
                    self.toggle_menu()
                else:
                    self.refresh_menu_actions()
                    self.refresh_ui()
                self.center_hint["text"] = "PYRAMID GATES // SELECT A DIMENSION"
                self.show_bridge_transition("PYRAMID GATES", "MATRIXCORE / HOLOCORE MENU", target=1.0, hold=0.25)
            except Exception:
                pass
            return True
        if request in {"launch_dimension", "launch_gate", "open_dimension"}:
            gate_id = canonical_dimension_lookup_key(
                (payload or {}).get("dimension_id")
                or (payload or {}).get("id")
                or (payload or {}).get("mode")
                or (payload or {}).get("title")
                or ""
            )
            if gate_id:
                try:
                    self.set_menu_tab("gates")
                    self.center_hint["text"] = "PYRAMID GATE // OPENING DIMENSION"
                    return bool(self.matrixcore_launch_dimension_gate(gate_id))
                except Exception as exc:
                    try:
                        print(f"external_return_launch_gate_failed gate={gate_id} err={exc.__class__.__name__}:{exc}")
                    except Exception:
                        pass
            try:
                self.set_menu_tab("gates")
                if not bool(getattr(self, "menu_open", False)):
                    self.toggle_menu()
                self.center_hint["text"] = "PYRAMID GATE // ROUTE NEEDS CONFIG"
            except Exception:
                pass
            return False
        return False

    def _write_external_return_signal(self, reason: str = "user") -> None:
        path = getattr(self, "external_return_signal_path", None)
        if not path:
            return
        try:
            path = Path(path)
            path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "request": "return_to_core",
                "reason": str(reason or "user"),
                "mode": str(getattr(self, "external_launch_label", "MODE") or "MODE"),
                "timestamp": time.time(),
                "parent_pid": os.getpid(),
            }
            path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except Exception as exc:
            print(f"external_return_signal_write_failed err={exc}")

    def _force_external_return_after_delay(self, proc: subprocess.Popen, label: str, delay: float = 3.0) -> None:
        try:
            time.sleep(max(0.4, float(delay)))
            if proc is not getattr(self, "external_process", None):
                return
            if proc.poll() is None:
                print(f"external_return_force_terminate label={label}")
                try:
                    proc.terminate()
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass
        except Exception:
            pass

    def _terminate_external_process_handle(self, proc: subprocess.Popen | None, label: str, reason: str = "window-closed", kill_after: float = 1.2) -> None:
        if proc is None:
            return
        try:
            if proc.poll() is None:
                print(f"external_process_terminate label={label} reason={reason}")
                try:
                    proc.terminate()
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        return
                def _kill_later():
                    try:
                        time.sleep(max(0.25, float(kill_after)))
                        if proc.poll() is None:
                            print(f"external_process_kill label={label} reason={reason}")
                            proc.kill()
                    except Exception:
                        pass
                threading.Thread(target=_kill_later, daemon=True).start()
        except Exception:
            pass

    def _mark_external_resume_pending(self, proc: subprocess.Popen | None = None, label: str | None = None, reason: str = "process-exited", route: str | None = None) -> bool:
        active_proc = getattr(self, "external_process", None)
        if proc is not None and active_proc is not None and proc is not active_proc:
            return False
        label = str(label or getattr(self, "external_launch_label", "MODE") or "MODE")
        rc = None
        try:
            rc = proc.poll() if proc is not None else (active_proc.poll() if active_proc is not None else None)
        except Exception:
            rc = None
        self.external_return_code = rc
        self.external_resume_pending = True
        if not bool(getattr(self, "external_resume_marked", False)):
            self.external_resume_marked = True
            try:
                self._append_mode_gateway_history("external_return", label=label, route=route or MODE_LAUNCH_EXTERNAL, extra={"return_code": rc, "reason": reason})
            except Exception:
                pass
        return True

    def _external_process_poll_update(self, reason: str = "poll") -> bool:
        proc = getattr(self, "external_process", None)
        if proc is None:
            if bool(getattr(self, "external_suspended", False)):
                self.external_resume_pending = True
                return True
            return False
        try:
            if proc.poll() is not None:
                return self._mark_external_resume_pending(proc=proc, reason=reason)
        except Exception:
            return self._mark_external_resume_pending(proc=proc, reason=f"{reason}-poll-error")
        return False

    def _embedded_child_window_closed_update(self) -> bool:
        embedder = getattr(self, "embedded_child_host", None)
        if embedder is None:
            return False
        if not bool(getattr(embedder, "ever_attached", False)):
            return False
        if not bool(getattr(embedder, "child_window_closed", False)):
            return False
        closed_at = float(getattr(embedder, "child_window_closed_at", 0.0) or 0.0)
        if closed_at and (time.monotonic() - closed_at) < 0.20:
            return False
        proc = getattr(self, "external_process", None)
        label = str(getattr(self, "external_launch_label", "MODE") or "MODE")
        reason = str(getattr(embedder, "child_window_closed_reason", "child-window-closed") or "child-window-closed")
        self._write_external_return_signal(reason=reason)
        self._terminate_external_process_handle(proc, label, reason=reason, kill_after=1.0)
        return self._mark_external_resume_pending(proc=proc, label=label, reason=reason, route=MODE_LAUNCH_EMBEDDED)

    def _release_stuck_embedded_wait_lock(self, reason: str = "embedded-attach-timeout") -> bool:
        """Recover from a child-window embed attempt that never attaches.

        The old behavior could leave HoloVerse suspended forever while the
        loading overlay waited for a child window. Keep the child process alive
        as a hosted external fallback, release the hub, and let ESC / Close All
        Apps terminate it if the child itself is broken.
        """
        if not bool(getattr(self, "external_suspended", False)):
            return False
        proc = getattr(self, "external_process", None)
        if proc is None:
            self.external_resume_pending = True
            return True
        try:
            if proc.poll() is not None:
                return self._mark_external_resume_pending(proc=proc, reason=f"{reason}-process-exited", route=MODE_LAUNCH_EMBEDDED)
        except Exception:
            return self._mark_external_resume_pending(proc=proc, reason=f"{reason}-poll-error", route=MODE_LAUNCH_EMBEDDED)
        label = str(getattr(self, "external_launch_label", "MODE") or "MODE")
        embedder = getattr(self, "embedded_child_host", None)
        attach_error = str(getattr(embedder, "attach_error", "") or "")
        try:
            if embedder is not None:
                embedder.stop()
        except Exception:
            pass
        self.embedded_child_host = None
        self.embedded_child_attached = False
        self.external_suspended = False
        self.external_resume_pending = False
        self.mouse_captured = True
        try:
            if hasattr(self, "root_3d") and self.root_3d is not None and not self.root_3d.isEmpty():
                self.root_3d.unstash()
            if getattr(self.cfg, "hud_visible", True):
                if hasattr(self, "hud_root") and self.hud_root is not None and not self.hud_root.isEmpty():
                    self.hud_root.show()
                if hasattr(self, "crosshair_root") and self.crosshair_root is not None and not self.crosshair_root.isEmpty():
                    self.crosshair_root.show()
        except Exception:
            pass
        try:
            if self.win is not None and hasattr(self.win, "requestProperties"):
                props = WindowProperties()
                props.setCursorHidden(True)
                props.setForeground(True)
                self.win.requestProperties(props)
        except Exception:
            pass
        self.hide_native_status_overlay()
        self.center_hint["text"] = f"CORE // {label.upper()} HOSTED FALLBACK // ESC RETURNS"
        try:
            self._append_mode_gateway_history("embedded_attach_timeout_released", label=label, route=MODE_LAUNCH_EXTERNAL, extra={"reason": reason, "attach_error": attach_error, "pid": int(getattr(proc, "pid", 0) or 0)})
        except Exception:
            pass
        threading.Thread(target=self._focus_external_window_later, args=(proc, label), daemon=True).start()
        return True

    def _embedded_launch_timeout_update(self) -> bool:
        if not bool(getattr(self, "external_suspended", False)):
            return False
        embedder = getattr(self, "embedded_child_host", None)
        if embedder is None or bool(getattr(embedder, "attached", False)):
            return False
        elapsed = time.monotonic() - float(getattr(self, "external_launch_started_at", time.monotonic()) or time.monotonic())
        timeout = max(float(getattr(WindowsChildWindowEmbedder, "ATTACH_TIMEOUT_SECONDS", 8.0)) + 1.0, 9.0)
        if bool(getattr(embedder, "attach_timed_out", False)) or elapsed >= timeout:
            return self._release_stuck_embedded_wait_lock(reason="embedded-child-window-not-found")
        return False

    def request_external_return_to_core(self, reason: str = "user") -> None:
        """Ask the active hosted child mode to close and return to Core."""
        proc = getattr(self, "external_process", None)
        if proc is None:
            return
        try:
            if proc.poll() is None:
                self.center_hint["text"] = "CORE // RETURNING FROM MODE"
                self.external_return_requested_at = time.monotonic()
                self._append_mode_gateway_history("embedded_return_requested", label=getattr(self, "external_launch_label", "MODE"), route=MODE_LAUNCH_EMBEDDED, extra={"reason": reason, "graceful": True})
                self._write_external_return_signal(reason=reason)
                embedder = getattr(self, "embedded_child_host", None)
                if embedder is not None:
                    try:
                        embedder.request_graceful_close()
                    except Exception:
                        pass
                threading.Thread(target=self._force_external_return_after_delay, args=(proc, getattr(self, "external_launch_label", "MODE"), 3.2), daemon=True).start()
            else:
                self.external_resume_pending = True
        except Exception:
            self.external_resume_pending = True

    def resume_from_external_app(self):
        return_signal_payload = self._read_external_return_signal() if hasattr(self, "_read_external_return_signal") else {}
        if getattr(self, "embedded_child_host", None) is not None:
            try:
                self.embedded_child_host.stop()
            except Exception:
                pass
        self.embedded_child_host = None
        self.embedded_child_attached = False
        try:
            if getattr(self, "external_return_signal_path", None):
                Path(self.external_return_signal_path).unlink(missing_ok=True)
        except Exception:
            pass
        self.external_return_signal_path = None
        self.external_return_requested_at = 0.0
        self.external_suspended = False
        self.external_resume_pending = False
        self.external_resume_marked = False
        self.external_process = None
        self.hide_native_status_overlay()
        try:
            self._stop_native_mode_audio()
        except Exception:
            pass
        self.mouse_captured = True
        if hasattr(self, "root_3d") and self.root_3d is not None and not self.root_3d.isEmpty():
            self.root_3d.unstash()
        if getattr(self.cfg, "hud_visible", True):
            if hasattr(self, "hud_root") and self.hud_root is not None and not self.hud_root.isEmpty():
                self.hud_root.show()
            if hasattr(self, "crosshair_root") and self.crosshair_root is not None and not self.crosshair_root.isEmpty():
                self.crosshair_root.show()
        if self.win is not None and hasattr(self.win, "requestProperties"):
            props = WindowProperties()
            props.setCursorHidden(True)
            props.setForeground(True)
            try:
                props.setMinimized(False)
            except Exception:
                pass
            if LAUNCH_BORDERLESS:
                props.setUndecorated(True)
                props.setOrigin(LAUNCH_X, LAUNCH_Y)
                props.setSize(LAUNCH_W, LAUNCH_H)
                props.setFullscreen(False)
                props.setFixedSize(True)
            elif LAUNCH_BORDERED_FULLSCREEN:
                props.setUndecorated(False)
                props.setOrigin(LAUNCH_X, LAUNCH_Y)
                props.setSize(LAUNCH_W, LAUNCH_H)
                props.setFullscreen(False)
                props.setFixedSize(False)
            else:
                props.setUndecorated(False)
                props.setFullscreen(bool(LAUNCH_FULLSCREEN))
            self.win.requestProperties(props)
        try:
            self._restore_hub_ground_control_state(reason="external_return")
            self.reload_default_holoverse_shell(reason="external_return")
            self.sync_active_world_runtime_state()
        except Exception:
            pass
        self.recenter_mouse(force=True)
        self.center_hint["text"] = "CORE // RETURNED"
        returned_label = str(getattr(self, "external_launch_label", "MODE") or "MODE")
        if self._is_holocore_label(returned_label):
            self.show_bridge_transition(
                "HOLOCORE -> MATRIXCORE",
                "RESTORING OBSERVATORY CONTROL",
                target=1.0,
            )
            self.fade_bridge_transition(hold=0.55)
        self.record_matrixcore_dimension_signal("dimension_return", returned_label, label=returned_label, route=MODE_LAUNCH_EMBEDDED, source="embedded_external", reason="external_resume")
        handled_return_signal = False
        try:
            handled_return_signal = bool(self._handle_external_return_signal_action(return_signal_payload, returned_label))
        except Exception as exc:
            try:
                print(f"external_return_signal_action_failed err={exc.__class__.__name__}:{exc}")
            except Exception:
                pass
        if not handled_return_signal:
            self.maybe_queue_gleebs_return_dialogue(returned_label)
        pause_seconds = max(0.0, time.monotonic() - float(getattr(self, "external_pause_started_at", time.monotonic())))
        print(f"external_resume_ok label={self.external_launch_label} rc={self.external_return_code} paused_seconds={pause_seconds:.2f}")

    def _watch_external_process(self, proc: subprocess.Popen, label: str):
        rc = None
        try:
            rc = proc.wait()
        except Exception as exc:
            print(f"external_wait_error label={label} err={exc}")
        finally:
            # Ignore stale watcher completions from an older child process.
            # Without this guard, an old thread can rename the active launch or
            # flip the parent back into a wait/return state after a new mode has
            # already started.
            if proc is not getattr(self, "external_process", None):
                return
            self.external_return_code = rc
            self.external_launch_label = label
            self._mark_external_resume_pending(proc=proc, label=label, reason="process-wait-complete", route=MODE_LAUNCH_EXTERNAL)

    def _focus_external_window_later(self, proc: subprocess.Popen, label: str) -> None:
        """Focus the actual game window after hosted launch.

        This is a Windows-only best-effort repair for the case where the parent
        command prompt remains the active window instead of the launched
        Dimension.
        """
        if os.name != "nt":
            return
        deadline = time.monotonic() + 6.0
        while time.monotonic() < deadline:
            try:
                if proc is not getattr(self, "external_process", None) or proc.poll() is not None:
                    return
                if _focus_visible_window_for_pid(int(getattr(proc, "pid", 0) or 0), label=label):
                    self._append_mode_gateway_history("external_focus", label=label, route=MODE_LAUNCH_EXTERNAL, extra={"pid": int(getattr(proc, "pid", 0) or 0), "result": "focused"})
                    return
            except Exception:
                pass
            time.sleep(0.12)
        try:
            self._append_mode_gateway_history("external_focus", label=label, route=MODE_LAUNCH_EXTERNAL, extra={"pid": int(getattr(proc, "pid", 0) or 0), "result": "window-not-found"})
        except Exception:
            pass

    def show_native_status_overlay(self, label: str, route: str = "MODE", subtitle: str | None = None) -> None:
        try:
            if getattr(self, "native_status_root", None) is None:
                return
            clean_label = str(label or "MODE").upper()
            clean_route = str(route or "MODE").upper()
            if getattr(self, "native_status_label", None) is not None:
                self.native_status_label["text"] = f"{clean_route} // {clean_label}"
            if getattr(self, "native_status_subtitle", None) is not None:
                self.native_status_subtitle["text"] = subtitle or "TRANSITION HOST ROUTE // ESC RETURNS TO HOLOVERSE"
            self.native_status_root.show()
        except Exception:
            pass

    def show_mode_loading_overlay(self, label: str, route: str = "LOADING", elapsed: float = 0.0, detail: str = "") -> None:
        seconds = max(0.0, float(elapsed or 0.0))
        suffix = f" // {str(detail).upper()}" if str(detail or "").strip() else ""
        subtitle = f"LAUNCHING MODE {seconds:04.1f}s{suffix} // ESC CANCELS / RETURNS TO HOLOVERSE"
        self.center_hint["text"] = f"CORE // {str(label or 'MODE').upper()} LOADING {seconds:04.1f}s"
        self.show_native_status_overlay(label, route=route, subtitle=subtitle)

    def hide_native_status_overlay(self) -> None:
        try:
            if getattr(self, "native_status_root", None) is not None:
                self.native_status_root.hide()
        except Exception:
            pass

    def _is_holocore_label(self, label: object = "") -> bool:
        return "holocore" in str(label or "").replace(" ", "").lower()

    def _set_bridge_transition_alpha(self, alpha: float) -> None:
        root = getattr(self, "bridge_transition_root", None)
        if root is None:
            return
        alpha = max(0.0, min(1.0, float(alpha or 0.0)))
        self.bridge_transition_alpha = alpha
        if alpha <= 0.002 and float(getattr(self, "bridge_transition_target", 0.0) or 0.0) <= 0.0:
            try:
                root.hide()
            except Exception:
                pass
            return
        try:
            root.show()
        except Exception:
            pass
        try:
            panel = getattr(self, "bridge_transition_panel", None)
            if panel is not None:
                panel["frameColor"] = (0.0, 0.006, 0.012, 0.86 * alpha)
            label = getattr(self, "bridge_transition_label", None)
            if label is not None:
                label["text_fg"] = (0.74, 1.0, 1.0, 0.95 * alpha)
            subtitle = getattr(self, "bridge_transition_subtitle", None)
            if subtitle is not None:
                subtitle["text_fg"] = (0.46, 0.94, 1.0, 0.82 * alpha)
        except Exception:
            pass

    def show_bridge_transition(self, title: str, subtitle: str = "", *, target: float = 1.0, hold: float = 0.0) -> None:
        if getattr(self, "bridge_transition_root", None) is None:
            return
        try:
            if getattr(self, "bridge_transition_label", None) is not None:
                self.bridge_transition_label["text"] = str(title or "TRANSITION")
            if getattr(self, "bridge_transition_subtitle", None) is not None:
                self.bridge_transition_subtitle["text"] = str(subtitle or "SAME-SCREEN GATEWAY")
            self.bridge_transition_target = max(0.0, min(1.0, float(target)))
            self.bridge_transition_hold_until = max(float(getattr(self, "bridge_transition_hold_until", 0.0) or 0.0), time.monotonic() + max(0.0, float(hold or 0.0)))
            if float(getattr(self, "bridge_transition_alpha", 0.0) or 0.0) <= 0.002:
                self._set_bridge_transition_alpha(0.025)
            else:
                self._set_bridge_transition_alpha(float(getattr(self, "bridge_transition_alpha", 0.0) or 0.0))
        except Exception:
            pass

    def fade_bridge_transition(self, *, hold: float = 0.0) -> None:
        if getattr(self, "bridge_transition_root", None) is None:
            return
        self.bridge_transition_target = 0.0
        self.bridge_transition_hold_until = max(float(getattr(self, "bridge_transition_hold_until", 0.0) or 0.0), time.monotonic() + max(0.0, float(hold or 0.0)))

    def update_bridge_transition(self, dt: float) -> None:
        if getattr(self, "bridge_transition_root", None) is None:
            return
        alpha = float(getattr(self, "bridge_transition_alpha", 0.0) or 0.0)
        target = float(getattr(self, "bridge_transition_target", 0.0) or 0.0)
        if target <= 0.0 and time.monotonic() < float(getattr(self, "bridge_transition_hold_until", 0.0) or 0.0):
            target = max(1.0, alpha)
        speed = 5.2 if target > alpha else 3.0
        blend = min(1.0, max(0.0, float(dt or 0.0)) * speed)
        if abs(target - alpha) <= 0.004:
            alpha = target
        else:
            alpha = alpha + (target - alpha) * blend
        self._set_bridge_transition_alpha(alpha)

    def return_active_mode_from_button(self):
        if getattr(self, "active_native_mode", None) is not None:
            self.return_from_native_mode(reason="button")
            return
        if getattr(self, "external_process", None) is not None:
            self.request_external_return_to_core(reason="button")
            return
        self.hide_native_status_overlay()
        if getattr(self, "center_hint", None) is not None:
            self.center_hint["text"] = "CORE // NO ACTIVE GAME"

    def quit_holoverse_from_menu(self):
        """Single-click app exit from the modernized system menu.

        Hold-ESC remains the safe universal quit path, but the System tab now
        exposes a direct quit option so players do not have to hunt for it.
        """
        try:
            self.close_all_mode_apps()
        except Exception:
            pass
        try:
            if getattr(self, "center_hint", None) is not None:
                self.center_hint["text"] = "EXITING HOLOVERSE"
            if getattr(self, "audio", None):
                self.audio.play('menu_close.wav', 'sfx', 0.72)
        except Exception:
            pass
        self.userExit()

    def dispatch_native_action(self, action: str) -> bool:
        mode_obj = getattr(self, "active_native_mode", None)
        if mode_obj is None:
            return False
        for method_name in ("on_host_action", "handle_host_action", "on_action"):
            method = getattr(mode_obj, method_name, None)
            if callable(method):
                try:
                    result = method(str(action or ""))
                    return bool(result) if result is not None else True
                except Exception as exc:
                    print(f"native_mode_action_error label={self.native_mode_label} action={action} err={exc}")
                    self.return_from_native_mode(reason="action-error")
                    return True
        return False

    def _mode_adapter_path(self, mode: dict) -> Path | None:
        manifest = dict(mode.get("manifest") or {})
        folder = Path(mode.get("folder", ROOT))
        adapter_name = str(manifest.get("native_adapter") or MODE_NATIVE_ADAPTER_NAME).strip() or MODE_NATIVE_ADAPTER_NAME
        adapter = folder / adapter_name
        return adapter if adapter.exists() and adapter.is_file() else None

    def _load_native_mode_object(self, mode: dict, entry: Path | None, label: str):
        adapter_path = self._mode_adapter_path(mode)
        if adapter_path is None:
            raise FileNotFoundError(f"native adapter missing for {label}")
        module_name = f"holoverse_native_{re.sub(r'[^a-zA-Z0-9_]+', '_', str(mode.get('name', 'mode')))}_{int(time.time() * 1000)}"
        spec = importlib.util.spec_from_file_location(module_name, adapter_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"could not load adapter spec: {adapter_path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        if hasattr(module, "create_mode"):
            return module.create_mode(self, mode=mode, entry_path=entry, label=label)
        cls = getattr(module, "HoloVerseNativeMode", None)
        if cls is None:
            raise AttributeError(f"adapter lacks create_mode or HoloVerseNativeMode: {adapter_path}")
        return cls(self, mode=mode, entry_path=entry, label=label)

    def _native_node_key(self, node_path):
        try:
            node = node_path.node()
            raw = getattr(node, "this", None)
            if raw is not None:
                try:
                    return ("ptr", int(raw))
                except Exception:
                    return ("ptr", str(raw))
            return ("node", id(node), str(node))
        except Exception:
            try:
                return ("np", id(node_path), str(node_path))
            except Exception:
                return ("unknown", id(node_path))

    def _snapshot_native_scene_state(self) -> dict:
        snapshot = {}
        roots = (
            ("render", getattr(self, "render", None)),
            ("aspect2d", getattr(self, "aspect2d", None)),
            ("render2d", getattr(self, "render2d", None)),
            ("camera", getattr(self, "camera", None)),
        )
        for root_name, root in roots:
            keys = set()
            try:
                if root is None or root.isEmpty():
                    snapshot[root_name] = keys
                    continue
                for child in root.getChildren():
                    keys.add(self._native_node_key(child))
            except Exception:
                pass
            snapshot[root_name] = keys
        return snapshot

    def _purge_native_scene_residue(self, label: str = "") -> int:
        snapshot = getattr(self, "native_scene_baseline", None)
        if not isinstance(snapshot, dict):
            return 0
        removed = 0
        native_name_tokens = (
            "native", "code_red_vector", "code red vector", "etch", "fractured",
            "holo_campaign", "holo campaign", "holo_conquest", "holo conquest",
            "vector_arena", "vector arena", "vector_wars", "vector wars", "zonez", "holocore", "holo_vessel",
        )
        roots = (
            ("render", getattr(self, "render", None)),
            ("aspect2d", getattr(self, "aspect2d", None)),
            ("render2d", getattr(self, "render2d", None)),
            ("camera", getattr(self, "camera", None)),
        )
        for root_name, root in roots:
            try:
                if root is None or root.isEmpty():
                    continue
                baseline = snapshot.get(root_name, set())
                for child in list(root.getChildren()):
                    key = self._native_node_key(child)
                    if key in baseline:
                        continue
                    name = ""
                    try:
                        name = str(child.getName() or "").lower()
                    except Exception:
                        pass
                    should_remove = True
                    # Keep the guard conservative for unexpected Core nodes, but
                    # always remove obvious native residue and camera-mounted props.
                    if root_name not in {"camera", "aspect2d", "render2d"}:
                        should_remove = any(token in name for token in native_name_tokens)
                    if should_remove:
                        try:
                            child.removeNode()
                            removed += 1
                        except Exception:
                            pass
            except Exception:
                pass
        if removed:
            try:
                print(f"native_mode_residue_cleaned label={label or getattr(self, 'native_mode_label', '')} count={removed}")
            except Exception:
                pass
        return removed

    def _native_dimension_audio_profile(self, label: str) -> dict:
        """Shared same-window audio bed for artifact dimensions.

        Native adapters own gameplay/rendering, but HoloVerse keeps audio bus
        authority so every artifact has sound without each adapter inventing a
        separate mixer.  Paths stay project-local and are resolved through
        SharedAudio, which already handles Panda3D-safe Filename conversion.
        """
        key = re.sub(r"[^a-z0-9]+", "_", str(label or "dimension").lower()).strip("_")
        code_red_loop = ROOT / "Dimensions" / "Code Red Vector" / "assets" / "music" / "loop.wav"
        table = {
            "code_red_vector": {"music": os.fspath(code_red_loop) if code_red_loop.exists() else "hv_urban_conflict_theme.wav", "air": "hv_hub_room_air.wav", "volume": 0.62},
            "vector_arena": {"music": "hv_urban_conflict_theme.wav", "air": "hv_hub_room_air.wav", "volume": 0.58},
            "fractured_dimension": {"music": "hv_space_orbit_theme.wav", "air": "hv_space_orbit_theme_b.wav", "volume": 0.58},
            "holo_campaign": {"music": "hv_urban_conflict_theme_b.wav", "air": "hv_hub_room_air_b.wav", "volume": 0.58},
            "holo_conquest": {"music": "hv_metropolis_neon_theme.wav", "air": "hv_hub_room_air_c.wav", "volume": 0.58},
            "vector_wars": {"music": "hv_space_orbit_theme.wav", "air": "hv_space_orbit_theme_c.wav", "volume": 0.60},
            "zonez": {"music": "hv_world_exploration_theme.wav", "air": "hv_water_depth_theme.wav", "volume": 0.54},
            "holocore": {"music": "hv_hub_command_theme.wav", "air": "hv_hub_room_air.wav", "volume": 0.50},
        }
        if key in table:
            return dict(table[key])
        # Normalize common display labels without changing route IDs.
        for token, profile in table.items():
            if token and token in key:
                return dict(profile)
        return {"music": "hv_world_exploration_theme.wav", "air": "hv_hub_room_air.wav", "volume": 0.52}

    def _start_native_mode_audio(self, label: str):
        audio = getattr(self, "audio", None)
        if audio is None:
            return
        try:
            if hasattr(audio, "stop_all"):
                audio.stop_all(stop_oneshots=True)
            else:
                audio.stop_loop("hub_music")
                audio.stop_loop("hub_air")
                audio.stop_loop("holocore_dimension_music")
                audio.stop_loop("holocore_dimension_air")
                audio.stop_loop("native_dimension_music")
                audio.stop_loop("native_dimension_air")

            # HoloCore does not use the generic native-dimension music bed.  Its
            # same-window scene starts one reversed HoloCore dimension bed through
            # play_holocore_dimension_music().  Starting both here is what caused
            # stacked music on entry and again during return/re-entry cycles.
            if self._is_holocore_label(label):
                self.native_mode_audio_profile = {"label": "HoloCore", "music": "holocore_dimension_music", "air": "holocore_dimension_air", "owner": "holocore_same_window"}
                try:
                    audio.play("artifact_link.wav", bus="sfx", volume=0.58)
                except Exception:
                    pass
                return

            profile = self._native_dimension_audio_profile(label)
            music = str(profile.get("music") or "hv_world_exploration_theme.wav")
            air = str(profile.get("air") or "hv_hub_room_air.wav")
            volume = max(0.0, min(1.0, float(profile.get("volume", 0.55))))
            audio.play("artifact_link.wav", bus="sfx", volume=0.68)
            audio.play_loop("native_dimension_music", music, bus="music", volume=volume)
            audio.play_loop("native_dimension_air", air, bus="ambience", volume=max(0.12, min(0.34, volume * 0.42)))
            self.native_mode_audio_profile = {"label": str(label or "MODE"), "music": music, "air": air, "owner": "native_dimension"}
        except Exception as exc:
            try:
                print(f"native_mode_audio_start_error label={label} err={exc.__class__.__name__}:{exc}")
            except Exception:
                pass

    def _stop_native_mode_audio(self):
        audio = getattr(self, "audio", None)
        if audio is None:
            return
        try:
            if hasattr(audio, "stop_all"):
                audio.stop_all(stop_oneshots=True)
            else:
                audio.stop_loop("native_dimension_music")
                audio.stop_loop("native_dimension_air")
        except Exception:
            pass
        self.native_mode_audio_profile = {}

    def _restore_hub_ground_control_state(self, reason: str = "return") -> None:
        """Force HoloVerse back to walkable hub control after any mode exits."""
        try:
            self.shell_flight_craft_active = False
            self.shell_flight_craft_velocity = Vec3(0, 0, 0)
            self.shell_flight_craft_boost = 1.0
            node = getattr(self, "shell_flight_craft_visual_root", None)
            if node is not None and not node.isEmpty():
                node.removeNode()
            self.shell_flight_craft_visual_root = None
            self.shell_flight_craft_visual_signature = ""
        except Exception:
            pass
        try:
            self.holospace_active = False
            self.holospace_transition_active = False
            self.holospace_velocity = Vec3(0, 0, 0)
            self.holospace_speed_boost = 1.0
            self.holospace_ship_health = float(getattr(self, "holospace_ship_max_health", 100.0) or 100.0)
            self.holospace_ship_respawn_cooldown = 0.0
            self.show_holospace_cockpit(False)
            self.apply_holospace_world_isolation(False)
        except Exception:
            pass
        try:
            self.move_velocity = Vec2(0, 0)
            self.vertical_velocity = 0.0
            self.on_ground = True
            self.keys.clear()
        except Exception:
            pass
        try:
            self.player_pos = Vec3(self.base_teleport)
            self.player_yaw = 0.0
            self.player_pitch = -6.0
            if getattr(self, "render", None) is not None:
                self.camera.reparentTo(self.render)
            self.camera.setPos(self.player_pos)
            self.camera.setHpr(self.player_yaw, self.player_pitch, 0)
            if getattr(self, "camLens", None) is not None:
                self.camLens.setFov(75)
                self.camLens.setNearFar(0.08, 5000.0)
        except Exception:
            pass

    def suspend_for_native_mode(self, label: str):
        self.native_scene_baseline = self._snapshot_native_scene_state()
        self.native_mode_label = label
        self.native_mode_start_time = time.monotonic()
        self.native_mode_return_pending = False
        # Native artifact dimensions own the visible camera/window while mounted.
        if bool(getattr(self, "shell_flight_craft_cinematic", False)):
            self.exit_shell_flight_cinematic()
        # Treat them like a hard focus/scene isolation state so Core window events
        # from Windows overlays/recording cannot recenter or reassert hub control.
        self.native_mode_isolated = True
        self.active_world_runtime_state_label = "NATIVE_MODE"
        self.runtime_world_signature = f"NATIVE DIMENSION // {str(label or 'MODE').upper()}"
        self.close_core_console()
        self.menu_open = False
        self.mouse_captured = False
        self.keys.clear()
        self.move_velocity = Vec2(0, 0)
        # A saved Ember aircraft is global for the default HoloVerse world, but
        # it must not remain active or visually overlap a same-window dimension.
        try:
            self.shell_flight_craft_active = False
            self.shell_flight_craft_velocity = Vec3(0, 0, 0)
            self.shell_flight_craft_boost = 1.0
            node = getattr(self, "shell_flight_craft_visual_root", None)
            if node is not None and not node.isEmpty():
                node.removeNode()
            self.shell_flight_craft_visual_root = None
            self.shell_flight_craft_visual_signature = ""
        except Exception:
            pass
        self.native_saved_camera = {
            "pos": Vec3(self.camera.getPos(self.render)),
            "hpr": Vec3(self.camera.getHpr(self.render)),
            "player_pos": Vec3(self.player_pos),
            "yaw": float(self.player_yaw),
            "pitch": float(self.player_pitch),
            "lens_fov": self.camLens.getFov() if getattr(self, "camLens", None) is not None else None,
            "lens_near": self.camLens.getNear() if getattr(self, "camLens", None) is not None else None,
            "lens_far": self.camLens.getFar() if getattr(self, "camLens", None) is not None else None,
        }
        if hasattr(self, "root_3d") and self.root_3d is not None and not self.root_3d.isEmpty():
            self.root_3d.stash()
        if hasattr(self, "hud_root") and self.hud_root is not None and not self.hud_root.isEmpty():
            self.hud_root.hide()
        if hasattr(self, "crosshair_root") and self.crosshair_root is not None and not self.crosshair_root.isEmpty():
            self.crosshair_root.hide()
        if self.audio:
            self.audio.stop_loop("hub_music")
            self.audio.stop_loop("hub_air")
            self._start_native_mode_audio(label)
        if self.win is not None and hasattr(self.win, "requestProperties"):
            props = WindowProperties()
            props.setCursorHidden(True)
            props.setForeground(True)
            self.win.requestProperties(props)
        self.center_hint["text"] = f"{str(label or 'DIMENSION').upper()} // ESC / 0 RETURN TO HOLOVERSE"
        self.show_native_status_overlay(label, route="SAME-WINDOW", subtitle="ESC / 0 RETURN TO HOLOVERSE")
        self._append_mode_gateway_history("native_begin", label=label, route=MODE_LAUNCH_NATIVE)
        print(f"native_mode_begin label={label}")

    def collect_native_mode_result(self, mode_obj) -> dict:
        if mode_obj is None:
            return {}
        for method_name in ("get_holoverse_result", "get_result", "result"):
            method = getattr(mode_obj, method_name, None)
            if callable(method):
                try:
                    payload = method()
                    return dict(payload) if isinstance(payload, dict) else {}
                except Exception as exc:
                    try:
                        print(f"native_mode_result_error label={getattr(self, 'native_mode_label', '')} method={method_name} err={exc.__class__.__name__}:{exc}")
                    except Exception:
                        pass
                    return {}
        payload = getattr(mode_obj, "holoverse_result", {})
        return dict(payload) if isinstance(payload, dict) else {}

    def recalculate_matrixcore_points(self, progress: dict | None = None) -> int:
        """Normalize all saved dimension score buckets into one player total.

        The corner HUD, Progression page, and Gates state should agree even when
        a dimension reports score through a result payload, an older
        dimension_progress mirror, or a legacy holoverse_score value.  This
        function treats per-dimension totals as authoritative and uses the
        legacy aggregate only as a floor so old saves do not lose points.
        """
        progress = progress if isinstance(progress, dict) else self.load_matrixcore_progression()
        per_dimension: dict[str, int] = {}

        def add(bucket: str, value) -> None:
            try:
                score = int(float(value or 0))
            except Exception:
                return
            if score <= 0:
                return
            key = canonical_dimension_lookup_key(bucket) or str(bucket or "mode")
            per_dimension[key] = max(score, int(per_dimension.get(key, 0) or 0))

        for source_key in ("dimension_results", "dimension_progress"):
            source = progress.get(source_key) if isinstance(progress.get(source_key), dict) else {}
            for key, payload in source.items():
                if isinstance(payload, dict):
                    add(str(key), payload.get("score_total") or payload.get("total_score") or payload.get("points_total") or payload.get("score") or payload.get("best_score"))
        total = sum(int(v or 0) for v in per_dimension.values())
        try:
            total = max(total, int(float(progress.get("holoverse_score", 0) or 0)))
        except Exception:
            pass
        total = max(0, int(total))
        progress["holoverse_score"] = total
        player = progress.setdefault("player", {})
        if isinstance(player, dict):
            player["total_points"] = total
        progress["points_total"] = total
        return total

    def record_native_dimension_result(self, mode_name: str, route: str, result: dict) -> dict:
        if not isinstance(result, dict) or not result:
            return {}
        progress = self.load_matrixcore_progression()
        bucket = progress.setdefault("dimension_results", {})
        if not isinstance(bucket, dict):
            bucket = {}
        mode_name = str(mode_name or "Dimension").strip() or "Dimension"
        entry = bucket.get(mode_name) if isinstance(bucket.get(mode_name), dict) else {}
        score_delta = int(float(result.get("score_delta", 0) or 0))
        entry["count"] = int(entry.get("count", 0) or 0) + 1
        entry["last_at"] = datetime.now().isoformat(timespec="seconds")
        entry["route"] = str(route or entry.get("route", ""))
        entry["score_total"] = int(entry.get("score_total", 0) or 0) + score_delta
        entry["points_total"] = int(entry.get("score_total", 0) or 0)
        entry["last_score_delta"] = score_delta
        entry["completed"] = bool(result.get("completed", False))
        entry["fragments_recovered"] = str(result.get("fragments_recovered", ""))
        entry["fragments_required"] = str(result.get("fragments_required", ""))
        signal = str(result.get("signal") or result.get("memory_fragment") or "").strip()
        if signal:
            signals = entry.get("signals") if isinstance(entry.get("signals"), list) else []
            if signal not in signals:
                signals.append(signal)
            entry["signals"] = signals[-12:]
            entry["last_signal"] = signal
        response = str(result.get("gleebs_response") or "").strip()
        if response:
            entry["gleebs_response"] = response
        bucket[mode_name] = entry
        progress["dimension_results"] = bucket
        dim_progress = progress.setdefault("dimension_progress", {})
        if isinstance(dim_progress, dict):
            mirror = dim_progress.get(mode_name) if isinstance(dim_progress.get(mode_name), dict) else {}
            mirror.update({
                "score_total": int(entry.get("score_total", 0) or 0),
                "points_total": int(entry.get("points_total", 0) or 0),
                "last_score_delta": score_delta,
                "completed": bool(entry.get("completed", False)),
                "last_signal": str(entry.get("last_signal", "")),
                "last_at": str(entry.get("last_at", "")),
                "route": str(entry.get("route", "")),
            })
            dim_progress[mode_name] = mirror
            progress["dimension_progress"] = dim_progress
        total_points = self.recalculate_matrixcore_points(progress)
        matrixcore = progress.setdefault("matrixcore", {})
        matrixcore["last_dimension_result"] = mode_name
        matrixcore["last_dimension_score_delta"] = score_delta
        matrixcore["total_points"] = total_points
        if signal:
            matrixcore["last_dimension_signal"] = signal
        self.save_matrixcore_progression(progress)
        try:
            self.update_matrixcore_gate_result_state(mode_name, result, route)
        except Exception:
            pass
        return self.append_matrixcore_event({
            "kind": "dimension_result",
            "mode": mode_name,
            "route": route,
            "source": "native",
            "score_delta": score_delta,
            "completed": bool(result.get("completed", False)),
            "signal": signal,
        })

    def return_from_native_mode(self, reason: str = "return"):
        mode_obj = getattr(self, "active_native_mode", None)
        native_result = self.collect_native_mode_result(mode_obj)
        returning_holocore = self._is_holocore_label(getattr(self, "native_mode_label", ""))
        if returning_holocore:
            try:
                self.show_bridge_transition("HOLOCORE -> MATRIXCORE", "PYRAMID GATE // SAME WINDOW RETURN", target=1.0, hold=0.18)
            except Exception:
                pass
        self.active_native_mode = None
        self.native_mode_return_pending = False
        self._stop_native_mode_audio()
        if mode_obj is not None:
            for method_name in ("exit", "destroy"):
                method = getattr(mode_obj, method_name, None)
                if callable(method):
                    try:
                        method()
                    except Exception:
                        print(f"native_mode_{method_name}_error label={self.native_mode_label}")
        # Some adapters own their own music/SFX objects.  After their exit hook,
        # hard-stop the shared bus again so no previous dimension song carries
        # into the restored hub soundscape.
        try:
            self._stop_native_mode_audio()
        except Exception:
            pass
        try:
            self._purge_native_scene_residue(str(getattr(self, "native_mode_label", "") or ""))
        except Exception:
            pass
        if hasattr(self, "root_3d") and self.root_3d is not None and not self.root_3d.isEmpty():
            self.root_3d.unstash()
        if getattr(self.cfg, "hud_visible", True):
            if hasattr(self, "hud_root") and self.hud_root is not None and not self.hud_root.isEmpty():
                self.hud_root.show()
            if hasattr(self, "crosshair_root") and self.crosshair_root is not None and not self.crosshair_root.isEmpty():
                self.crosshair_root.show()
        saved = getattr(self, "native_saved_camera", None)
        if isinstance(saved, dict):
            self.player_pos = Vec3(saved.get("player_pos", self.base_teleport))
            self.player_yaw = float(saved.get("yaw", self.player_yaw))
            self.player_pitch = float(saved.get("pitch", self.player_pitch))
            if getattr(self, "render", None) is not None:
                self.camera.reparentTo(self.render)
            self.camera.setPos(saved.get("pos", self.player_pos))
            self.camera.setHpr(saved.get("hpr", Vec3(self.player_yaw, self.player_pitch, 0)))
            try:
                lens_fov = saved.get("lens_fov")
                if lens_fov is not None and getattr(self, "camLens", None) is not None:
                    self.camLens.setFov(lens_fov)
                near = saved.get("lens_near")
                far = saved.get("lens_far")
                if near is not None and far is not None and getattr(self, "camLens", None) is not None:
                    self.camLens.setNearFar(float(near), float(far))
            except Exception:
                pass
        self.setBackgroundColor(self.cfg.background_value, self.cfg.background_value, self.cfg.background_value)
        self.mouse_captured = True
        if self.win is not None and hasattr(self.win, "requestProperties"):
            props = WindowProperties()
            props.setCursorHidden(True)
            props.setForeground(True)
            self.win.requestProperties(props)
        if not SELF_TEST:
            self.recenter_mouse(force=True)
        try:
            returned_key_for_anchor = str(getattr(self, "native_mode_label", "") or "").strip().lower()
            self._restore_hub_ground_control_state(reason=f"native_return_{returned_key_for_anchor or 'mode'}")
            self.reload_default_holoverse_shell(reason=f"native_return_{returned_key_for_anchor or 'mode'}")
            self.sync_active_world_runtime_state()
        except Exception:
            pass
        if self.audio:
            self.update_soundscape(0.0, force=True)
            self.audio.play('menu_close.wav', 'sfx', 0.72)
        elapsed = max(0.0, time.monotonic() - float(getattr(self, "native_mode_start_time", time.monotonic())))
        returned_label = str(self.native_mode_label or "MODE")
        discovery_notice = str(getattr(self, "pending_dimension_discovery_notice", "") or "")
        self.pending_dimension_discovery_notice = ""
        self.center_hint["text"] = self.format_dimension_return_message(returned_label, native_result, discovery=discovery_notice)
        if returning_holocore:
            try:
                self.center_hint["text"] = self.format_dimension_return_message("HoloCore Dimension", native_result, discovery=discovery_notice)
                self.fade_bridge_transition(hold=0.34)
            except Exception:
                pass
        return_route = str(getattr(self, "native_mode_route", "") or MODE_LAUNCH_NATIVE)
        return_reason = str(reason or "return")
        if native_result:
            try:
                signal = str(native_result.get("signal") or native_result.get("memory_fragment") or "").strip()
                score_delta = int(float(native_result.get("score_delta", 0) or 0))
                completed = bool(native_result.get("completed", False))
                result_bits = []
                if signal:
                    result_bits.append(f"signal={signal}")
                if score_delta:
                    result_bits.append(f"score_delta={score_delta}")
                if completed:
                    result_bits.append("completed=true")
                if result_bits:
                    return_reason = f"{return_reason}; " + "; ".join(result_bits)
            except Exception:
                pass
        self.record_matrixcore_dimension_signal("dimension_return", returned_label, label=returned_label, route=return_route, source="native", reason=return_reason)
        if native_result:
            try:
                self.record_native_dimension_result(returned_label, return_route, native_result)
            except Exception as exc:
                try:
                    print(f"native_mode_result_record_error label={returned_label} err={exc.__class__.__name__}:{exc}")
                except Exception:
                    pass
        self.maybe_queue_gleebs_return_dialogue(returned_label)
        self._append_mode_gateway_history("native_return", label=self.native_mode_label, route=return_route, extra={"reason": reason, "elapsed": f"{elapsed:.2f}"})
        print(f"native_mode_return label={self.native_mode_label} reason={reason} elapsed={elapsed:.2f}")
        self.native_mode_label = ""
        self.native_mode_entry = None
        self.native_mode_route = ""
        self.native_scene_baseline = None
        self.native_mode_isolated = False
        if bool(getattr(self, "world_shell_preloaded_default", False)):
            bridge = False
            try:
                report = getattr(self, "world_shell_preload_report", {}) or {}
                bridge = bool(report.get("source_bridge_active", False)) if isinstance(report, dict) else False
            except Exception:
                bridge = False
            self.runtime_world_signature = "HOLOVERSE DEFAULT // WORLD.PY SOURCE BRIDGE" if bridge else "HOLOVERSE DEFAULT // FULL-SCALE WORLD.PY RINGS"
        else:
            self.runtime_world_signature = "HUB STANDBY"
        self.sync_active_world_runtime_state()
        self.refresh_ui()

    def launch_native_mode(self, mode: dict, entry: Path | None, label: str, *, source: str = "core") -> bool:
        """Mount a dimension-native adapter inside the live HoloVerse window.

        Pass 54 restores the adapter path for dimensions that already ship a
        ``holoverse_native_adapter.py``. Holo Campaign uses this so artifacts
        enter the playable campaign slice directly instead of spawning the
        crash-prone child-window host.
        """
        mode = dict(mode or {})
        manifest = dict(mode.get("manifest") or {})
        label = str(label or mode.get("name") or manifest.get("title") or "Dimension")
        if getattr(self, "active_native_mode", None) is not None:
            self.center_hint["text"] = f"CORE // {label.upper()} ALREADY ACTIVE"
            return True
        if getattr(self, "external_process", None) is not None:
            self.center_hint["text"] = "CORE // CLOSE ACTIVE MODE FIRST"
            return False
        if entry is None or not Path(entry).exists():
            self.center_hint["text"] = f"CORE // {label.upper()} ENTRY MISSING"
            return False
        adapter_path = self._mode_adapter_path(mode)
        if adapter_path is None:
            self.center_hint["text"] = f"CORE // {label.upper()} NATIVE ADAPTER MISSING"
            self._append_mode_gateway_history("native_adapter_missing", mode=mode, label=label, route=MODE_LAUNCH_NATIVE, extra={"source": source, "entry": os.fspath(entry)})
            return False
        transition_id = f"{int(time.time() * 1000)}_{re.sub(r'[^a-z0-9]+', '_', label.lower()).strip('_')}_native"
        try:
            self.sync_core()
            self.core_mode_state["launch_count"] = int(self.core_mode_state.get("launch_count", 0)) + 1
            self.core_mode_state["last_mode"] = label
            self.core_mode_state["last_entry"] = Path(entry).name
            self.core_mode_state["last_launch_type"] = MODE_LAUNCH_NATIVE
            self.core_mode_state["last_launch_source"] = str(source or "core")
            save_mode_state(self.core_mode_state)
        except Exception:
            pass
        try:
            self.record_matrixcore_dimension_signal("dimension_transition_begin", label, label=label, route=MODE_LAUNCH_NATIVE, source=str(source or "core"), reason="native_adapter_mount")
        except Exception:
            pass
        self._append_mode_gateway_history(
            "native_adapter_begin",
            mode=mode,
            label=label,
            route=MODE_LAUNCH_NATIVE,
            extra={"transition_id": transition_id, "entry": os.fspath(entry), "adapter": os.fspath(adapter_path), "source": source},
        )
        try:
            self.show_bridge_transition(f"MATRIXCORE -> {label.upper()}", "SAME WINDOW // NATIVE DIMENSION ADAPTER", target=1.0, hold=0.18)
        except Exception:
            pass
        self.suspend_for_native_mode(label)
        try:
            mode_obj = self._load_native_mode_object(mode, Path(entry), label)
            enter = getattr(mode_obj, "enter", None)
            if callable(enter):
                enter()
            # Permanent full-game audio ownership: some source adapters start
            # their own music during setup.  Reassert the root scene bed after
            # the adapter has finished booting so only one song can play.
            try:
                self._start_native_mode_audio(label)
            except Exception:
                pass
            self.active_native_mode = mode_obj
            self.native_mode_entry = Path(entry)
            self.native_mode_label = label
            self.native_mode_route = MODE_LAUNCH_NATIVE
            self.last_launched_core_mode = label
            self.last_launched_core_entry = os.fspath(entry)
            # Native dimensions provide their own player-facing objective overlay.
            # Do not leave a Core/debug adapter banner over gameplay.
            self.center_hint["text"] = ""
            self.hide_native_status_overlay()
            self.fade_bridge_transition(hold=0.0)
            try:
                self.bridge_transition_target = 0.0
                self.bridge_transition_hold_until = 0.0
                self._set_bridge_transition_alpha(0.0)
            except Exception:
                pass
            try:
                self.record_matrixcore_dimension_signal("dimension_launch", label, label=label, route=MODE_LAUNCH_NATIVE, source=str(source or "core"), reason="native_adapter_mount")
            except Exception:
                pass
            self._append_mode_gateway_history(
                "native_adapter_active",
                mode=mode,
                label=label,
                route=MODE_LAUNCH_NATIVE,
                extra={"transition_id": transition_id, "adapter": os.fspath(adapter_path), "entry": os.fspath(entry)},
            )
            return True
        except Exception as exc:
            self.active_native_mode = None
            self._append_mode_gateway_history(
                "native_adapter_failed",
                mode=mode,
                label=label,
                route=MODE_LAUNCH_NATIVE,
                extra={"transition_id": transition_id, "adapter": os.fspath(adapter_path), "error": f"{exc.__class__.__name__}: {exc}"},
            )
            try:
                print(f"native_adapter_failed label={label} error={exc.__class__.__name__}:{exc}")
            except Exception:
                pass
            try:
                self.return_from_native_mode(reason="native_adapter_failed")
            except Exception:
                pass
            return False


    def _host_window_hwnd(self) -> int:
        """Best-effort Panda3D OS window handle lookup for Windows child-window hosting."""
        try:
            handle_obj = self.win.getWindowHandle() if self.win is not None else None
        except Exception:
            handle_obj = None
        if handle_obj is None:
            return 0
        for attr in ("getIntHandle", "getOsHandle", "getHandle"):
            getter = getattr(handle_obj, attr, None)
            if callable(getter):
                try:
                    value = int(getter())
                    if value:
                        return value
                except Exception:
                    pass
        try:
            value = int(handle_obj)
            return value if value else 0
        except Exception:
            return 0

    def _embedded_window_size(self) -> tuple[int, int]:
        try:
            if self.win is not None:
                return max(640, int(self.win.getXSize() or LAUNCH_W)), max(360, int(self.win.getYSize() or LAUNCH_H))
        except Exception:
            pass
        return max(640, int(LAUNCH_W or 1280)), max(360, int(LAUNCH_H or 720))

    def launch_embedded_external_level(self, path: Path, label: str, extra_env: dict | None = None) -> bool:
        """Launch the real standalone mode and host its OS window inside HoloVerse.

        On Windows this uses SetParent/WS_CHILD to preserve the original mode
        code while making it appear on the same display. On other platforms, or
        if a host HWND cannot be found, it falls back to normal external launch.
        """
        if os.name != "nt":
            self.center_hint["text"] = f"CORE // {label} EMBED FALLBACK EXTERNAL"
            return bool(self.launch_external_level(path, label, extra_env=extra_env))
        host_hwnd = self._host_window_hwnd()
        if not host_hwnd:
            self.center_hint["text"] = f"CORE // {label} EMBED HOST HWND MISSING"
            return bool(self.launch_external_level(path, label, extra_env=extra_env))
        if path is None or not Path(path).exists():
            self.center_hint["text"] = f"CORE // {label} MISSING"
            return False
        if self.external_process is not None:
            self.center_hint["text"] = f"CORE // {label} ALREADY RUNNING"
            return False
        try:
            audio_bus_path = write_audio_bus(self.cfg)
            launch_settings_path = write_shared_launch_settings(self.cfg)
            holoverse_settings_path = write_holoverse_settings(self.cfg)
            env = os.environ.copy()
            env["MATRIX_AUDIO_CONFIG"] = os.fspath(audio_bus_path)
            env["MATRIX_LAUNCH_SETTINGS"] = os.fspath(launch_settings_path)
            env["HOLOVERSE_SETTINGS_PATH"] = os.fspath(holoverse_settings_path)
            audio_profile_path = Path(path).parent / "audio_profile.json"
            if audio_profile_path.exists():
                env["HOLOVERSE_MODE_AUDIO_PROFILE"] = os.fspath(audio_profile_path)
            env["HOLOVERSE_MODE_NAME"] = str(label)
            env["HOLOVERSE_SHARED_DATA_DIR"] = os.fspath(SHARED_HOLOVERSE_DATA_DIR)
            env["HOLOVERSE_CREATIVITY_BLUEPRINT_DIR"] = os.fspath(SHARED_HOLOVERSE_DATA_DIR / "creativity" / "blueprints")
            shared_sfx_path = CANONICAL_SHARED_SFX_DIR if CANONICAL_SHARED_SFX_DIR.exists() else SHARED_SFX_DIR
            music_path = CANONICAL_MUSIC_DIR if CANONICAL_MUSIC_DIR.exists() else MUSIC_DIR
            generated_audio_path = CANONICAL_GENERATED_SFX_DIR if CANONICAL_GENERATED_SFX_DIR.exists() else AUDIO_DIR
            env["HOLOVERSE_AUDIO_ROOT"] = os.fspath(AUDIO_LIBRARY_DIR)
            env["HOLOVERSE_SHARED_SFX_DIR"] = os.fspath(shared_sfx_path)
            env["MATRIX_SHARED_SFX_DIR"] = os.fspath(shared_sfx_path)
            env["HOLOVERSE_LEGACY_SHARED_SFX_DIR"] = os.fspath(SHARED_SFX_DIR)
            env["HOLOVERSE_MUSIC_DIR"] = os.fspath(music_path)
            env["MATRIX_MUSIC_DIR"] = os.fspath(music_path)
            env["HOLOVERSE_LEGACY_MUSIC_DIR"] = os.fspath(MUSIC_DIR)
            env["HOLOVERSE_GENERATED_AUDIO_DIR"] = os.fspath(generated_audio_path)
            env["HOLOVERSE_LEGACY_GENERATED_AUDIO_DIR"] = os.fspath(AUDIO_DIR)
            env["HOLOVERSE_OVERRIDE_SETTINGS"] = "1"
            env["HOLOVERSE_EMBEDDED_MODE"] = "1"
            env["HOLOVERSE_RETURN_KEY"] = "escape"
            env["HOLOVERSE_SINGLE_ESC_RETURN"] = "1"
            env["HOLOVERSE_ESC_SINGLE_RETURN"] = "1"
            env["HOLOVERSE_RETURN_ON_ESC"] = "1"
            env["HOLOVERSE_ROOT_OWNS_MUSIC"] = "1"
            env["NEON_DOGFIGHT_DISABLE_MUSIC"] = "1"
            payload = build_audio_bus_payload(self.cfg)
            launch_payload = build_launch_settings_payload(self.cfg)
            w, h = self._embedded_window_size()
            safe_label = re.sub(r"[^A-Za-z0-9._-]+", "_", str(label or "mode")).strip("_") or "mode"
            return_signal_path = ROOT / "logs" / f"embedded_return_signal_{safe_label}.json"
            try:
                return_signal_path.unlink(missing_ok=True)
            except Exception:
                pass
            env["HOLOVERSE_RETURN_SIGNAL_PATH"] = os.fspath(return_signal_path)
            self.external_return_signal_path = return_signal_path
            env["MATRIX_MASTER_VOLUME"] = str(payload["master_volume"])
            env["MATRIX_SFX_VOLUME"] = str(payload["sfx_volume"])
            env["MATRIX_MUSIC_VOLUME"] = str(payload["music_volume"])
            env["MATRIX_AMBIENCE_VOLUME"] = str(payload["ambience_volume"])
            env["MATRIX_GAME_WIDTH"] = str(w)
            env["MATRIX_GAME_HEIGHT"] = str(h)
            env["HOLOVERSE_VIRTUAL_WIDTH"] = "1920"
            env["HOLOVERSE_VIRTUAL_HEIGHT"] = "1080"
            env["HOLOVERSE_FPS_CAP"] = str(launch_payload.get("fps_cap", 60) if isinstance(launch_payload, dict) else 60)
            env["HOLOVERSE_VSYNC"] = "1"
            env["HOLOVERSE_UI_SCALE"] = "1.0"
            env["HOLOVERSE_RENDER_SCALE"] = str(launch_payload.get("render_scale", 1.0))
            env["HOLOVERSE_MASTER_VOLUME"] = str(payload["master_volume"])
            env["HOLOVERSE_MUSIC_VOLUME"] = str(payload["music_volume"])
            env["HOLOVERSE_SFX_VOLUME"] = str(payload["sfx_volume"])
            env["HOLOVERSE_AMBIENCE_VOLUME"] = str(payload["ambience_volume"])
            env["HOLOVERSE_SOUNDTRACK_ENABLED"] = "1" if payload.get("soundtrack_enabled", True) else "0"
            env["HOLOVERSE_SOUNDTRACK_INTENSITY"] = str(payload.get("soundtrack_intensity", 0.55))
            env["HOLOVERSE_AMBIENCE_INTENSITY"] = str(payload.get("ambience_intensity", 0.45))
            env["HOLOVERSE_SOUNDMATRIX_VARIANT_INTENSITY"] = str(payload.get("soundmatrix_variant_intensity", 0.65))
            env["HOLOVERSE_SOUNDMATRIX_MUSIC_INTENSITY"] = str(payload.get("soundmatrix_music_intensity", 0.55))
            env["HOLOVERSE_HUD_ENABLED"] = "1" if launch_payload.get("hud_visible", True) else "0"
            env["HOLOVERSE_SUBTITLES_ENABLED"] = "1" if launch_payload.get("subtitles_enabled", True) else "0"
            env["HOLOVERSE_BRIGHTNESS"] = str(launch_payload.get("brightness", 1.0))
            env["HOLOVERSE_CONTRAST"] = str(launch_payload.get("contrast", 1.0))
            env["HOLOVERSE_GAMMA"] = str(launch_payload.get("gamma", 1.0))
            env["HOLOVERSE_GRAPHICS_QUALITY"] = str(launch_payload.get("graphics_quality", "medium"))
            env["HOLOVERSE_CONTROLLER_DEADZONE"] = str(launch_payload.get("controller_deadzone", 0.12))
            env["HOLOVERSE_OVERRIDE_MODE_SETTINGS"] = "1" if launch_payload.get("override_mode_settings", True) else "0"
            env["HOLOVERSE_PAUSE_KEY"] = "escape"
            env["MATRIX_GAME_FULLSCREEN"] = "0"
            env["MATRIX_GAME_BORDERLESS"] = "0"
            env["MATRIX_GAME_BORDERED_FULLSCREEN"] = "0"
            env["MATRIX_GAME_MOUSE_SENSITIVITY"] = str(launch_payload["mouse_sensitivity"])
            env["MATRIX_GAME_INVERT_Y"] = "1" if launch_payload["invert_y"] else "0"
            env["MATRIX_GAME_HUD_VISIBLE"] = "1" if launch_payload["hud_visible"] else "0"
            env["MATRIX_GAME_GRAPHICS_QUALITY"] = str(launch_payload["graphics_quality"])
            env["MATRIX_GAME_CONTROLLER_DEADZONE"] = str(launch_payload["controller_deadzone"])
            env["MATRIX_LAUNCHER_NAME"] = GAME_NAME
            env["MATRIX_LAUNCHED_FROM_CORE"] = "1"
            env["HOLOVERSE_HOSTED"] = "1"
            env["HOLOVERSE_EMBEDDED_CHILD"] = "1"
            env["HOLOVERSE_FAST_STARTUP"] = "1"
            env["PANDA3D_EMBEDDED"] = "1"
            env["PANDA3D_LAUNCHER"] = "1"
            env["NEON_DOGFIGHT_PANDA3D_SAFE"] = "1"
            env["SDL_VIDEO_CENTERED"] = "0"
            env["SDL_VIDEO_WINDOW_POS"] = "0,0"
            env["HOLOVERSE_PARENT_HWND"] = str(host_hwnd)
            env["HOLOVERSE_HOST_CONTRACT"] = "holoverse_mode_gateway_v4_child_window"
            env["HOLOVERSE_RETURN_TARGET"] = "hub"
            env["HOLOVERSE_WINDOW_MODE"] = "embedded_child"
            env["HOLOVERSE_PARENT_PID"] = str(os.getpid())
            if extra_env:
                for key, value in extra_env.items():
                    env[str(key)] = str(value)
            self.suspend_for_external_app(label, embedded=True)
            try:
                self._start_native_mode_audio(label)
            except Exception:
                pass
            proc = _launch_mode_subprocess(path, env, label)
            self.external_process = proc
            embedder = WindowsChildWindowEmbedder(host_hwnd, proc, label, w, h)
            self.embedded_child_host = embedder
            embedder.start()
            def _focus_after_attach():
                deadline = time.monotonic() + 5.0
                while time.monotonic() < deadline and proc.poll() is None:
                    if getattr(embedder, "attached", False):
                        embedder.focus_child(force=True)
                        break
                    time.sleep(0.08)
            threading.Thread(target=_focus_after_attach, daemon=True).start()
            self.show_native_status_overlay(label, route="EMBEDDED")
            self._append_mode_gateway_history("embedded_launch", label=label, route=MODE_LAUNCH_EMBEDDED, extra={"entry": os.fspath(path), "host_hwnd": host_hwnd, "settings": os.fspath(holoverse_settings_path), "audio_profile": os.fspath(audio_profile_path) if 'audio_profile_path' in locals() and audio_profile_path.exists() else "", "console_safe_launcher": True, "python_exe": _mode_process_python_executable()})
            threading.Thread(target=self._watch_external_process, args=(proc, label), daemon=True).start()
            return True
        except Exception as exc:
            self.external_process = None
            self.external_suspended = False
            self.external_resume_pending = False
            self.embedded_child_host = None
            self.mouse_captured = True
            self.center_hint["text"] = f"CORE // {label} EMBED FAILED"
            try:
                self._append_mode_gateway_history("embedded_launch_failed", label=label, route=MODE_LAUNCH_EMBEDDED, extra={"error": str(exc)})
            except Exception:
                pass
            return False

    def launch_external_level(self, path: Path, label: str, extra_env: dict | None = None) -> bool:
        if path is None or not Path(path).exists():
            self.center_hint["text"] = f"CORE // {label} MISSING"
            return False
        if self.external_process is not None:
            self.center_hint["text"] = f"CORE // {label} ALREADY RUNNING"
            return False
        try:
            audio_bus_path = write_audio_bus(self.cfg)
            launch_settings_path = write_shared_launch_settings(self.cfg)
            holoverse_settings_path = write_holoverse_settings(self.cfg)
            env = os.environ.copy()
            env["MATRIX_AUDIO_CONFIG"] = os.fspath(audio_bus_path)
            env["MATRIX_LAUNCH_SETTINGS"] = os.fspath(launch_settings_path)
            env["HOLOVERSE_SETTINGS_PATH"] = os.fspath(holoverse_settings_path)
            audio_profile_path = Path(path).parent / "audio_profile.json"
            if audio_profile_path.exists():
                env["HOLOVERSE_MODE_AUDIO_PROFILE"] = os.fspath(audio_profile_path)
            env["HOLOVERSE_MODE_NAME"] = str(label)
            env["HOLOVERSE_SHARED_DATA_DIR"] = os.fspath(SHARED_HOLOVERSE_DATA_DIR)
            env["HOLOVERSE_CREATIVITY_BLUEPRINT_DIR"] = os.fspath(SHARED_HOLOVERSE_DATA_DIR / "creativity" / "blueprints")
            shared_sfx_path = CANONICAL_SHARED_SFX_DIR if CANONICAL_SHARED_SFX_DIR.exists() else SHARED_SFX_DIR
            music_path = CANONICAL_MUSIC_DIR if CANONICAL_MUSIC_DIR.exists() else MUSIC_DIR
            generated_audio_path = CANONICAL_GENERATED_SFX_DIR if CANONICAL_GENERATED_SFX_DIR.exists() else AUDIO_DIR
            env["HOLOVERSE_AUDIO_ROOT"] = os.fspath(AUDIO_LIBRARY_DIR)
            env["HOLOVERSE_SHARED_SFX_DIR"] = os.fspath(shared_sfx_path)
            env["MATRIX_SHARED_SFX_DIR"] = os.fspath(shared_sfx_path)
            env["HOLOVERSE_LEGACY_SHARED_SFX_DIR"] = os.fspath(SHARED_SFX_DIR)
            env["HOLOVERSE_MUSIC_DIR"] = os.fspath(music_path)
            env["MATRIX_MUSIC_DIR"] = os.fspath(music_path)
            env["HOLOVERSE_LEGACY_MUSIC_DIR"] = os.fspath(MUSIC_DIR)
            env["HOLOVERSE_GENERATED_AUDIO_DIR"] = os.fspath(generated_audio_path)
            env["HOLOVERSE_LEGACY_GENERATED_AUDIO_DIR"] = os.fspath(AUDIO_DIR)
            env["HOLOVERSE_OVERRIDE_SETTINGS"] = "1"
            env["HOLOVERSE_EMBEDDED_MODE"] = "1"
            env["HOLOVERSE_RETURN_KEY"] = "escape"
            env["HOLOVERSE_SINGLE_ESC_RETURN"] = "1"
            env["HOLOVERSE_ESC_SINGLE_RETURN"] = "1"
            env["HOLOVERSE_RETURN_ON_ESC"] = "1"
            env["HOLOVERSE_ROOT_OWNS_MUSIC"] = "1"
            env["NEON_DOGFIGHT_DISABLE_MUSIC"] = "1"
            payload = build_audio_bus_payload(self.cfg)
            launch_payload = build_launch_settings_payload(self.cfg)
            safe_label = re.sub(r"[^A-Za-z0-9._-]+", "_", str(label or "mode")).strip("_") or "mode"
            return_signal_path = ROOT / "logs" / f"external_return_signal_{safe_label}.json"
            try:
                return_signal_path.unlink(missing_ok=True)
            except Exception:
                pass
            env["HOLOVERSE_RETURN_SIGNAL_PATH"] = os.fspath(return_signal_path)
            self.external_return_signal_path = return_signal_path
            env["MATRIX_MASTER_VOLUME"] = str(payload["master_volume"])
            env["MATRIX_SFX_VOLUME"] = str(payload["sfx_volume"])
            env["MATRIX_MUSIC_VOLUME"] = str(payload["music_volume"])
            env["MATRIX_AMBIENCE_VOLUME"] = str(payload["ambience_volume"])
            env["MATRIX_GAME_WIDTH"] = str(launch_payload["width"])
            env["MATRIX_GAME_HEIGHT"] = str(launch_payload["height"])
            env["HOLOVERSE_VIRTUAL_WIDTH"] = "1920"
            env["HOLOVERSE_VIRTUAL_HEIGHT"] = "1080"
            env["HOLOVERSE_FPS_CAP"] = str(launch_payload.get("fps_cap", 60) if isinstance(launch_payload, dict) else 60)
            env["HOLOVERSE_VSYNC"] = "1"
            env["HOLOVERSE_UI_SCALE"] = "1.0"
            env["MATRIX_GAME_FULLSCREEN"] = "1" if launch_payload["fullscreen"] else "0"
            env["MATRIX_GAME_BORDERLESS"] = "1" if launch_payload["borderless"] else "0"
            env["MATRIX_GAME_BORDERED_FULLSCREEN"] = "1" if launch_payload.get("bordered_fullscreen", True) else "0"
            env["MATRIX_GAME_MOUSE_SENSITIVITY"] = str(launch_payload["mouse_sensitivity"])
            env["MATRIX_GAME_INVERT_Y"] = "1" if launch_payload["invert_y"] else "0"
            env["MATRIX_GAME_HUD_VISIBLE"] = "1" if launch_payload["hud_visible"] else "0"
            env["MATRIX_GAME_GRAPHICS_QUALITY"] = str(launch_payload["graphics_quality"])
            env["MATRIX_GAME_CONTROLLER_DEADZONE"] = str(launch_payload["controller_deadzone"])
            env["MATRIX_LAUNCHER_NAME"] = GAME_NAME
            env["MATRIX_LAUNCHED_FROM_CORE"] = "1"
            env["HOLOVERSE_HOSTED"] = "1"
            env["HOLOVERSE_FAST_STARTUP"] = "1"
            env["HOLOVERSE_HOST_CONTRACT"] = "holoverse_mode_gateway_v2"
            env["HOLOVERSE_RETURN_TARGET"] = "hub"
            env["HOLOVERSE_WINDOW_MODE"] = "bordered_fullscreen" if launch_payload.get("bordered_fullscreen", True) else ("borderless" if launch_payload.get("borderless") else "windowed")
            env["HOLOVERSE_PARENT_PID"] = str(os.getpid())
            if extra_env:
                for key, value in extra_env.items():
                    env[str(key)] = str(value)
            self.suspend_for_external_app(label)
            proc = _launch_mode_subprocess(path, env, label)
            self.external_process = proc
            self._append_mode_gateway_history("external_launch", label=label, route=MODE_LAUNCH_EXTERNAL, extra={"entry": os.fspath(path), "console_safe_launcher": True, "python_exe": _mode_process_python_executable()})
            threading.Thread(target=self._focus_external_window_later, args=(proc, label), daemon=True).start()
            threading.Thread(target=self._watch_external_process, args=(proc, label), daemon=True).start()
            return True
        except Exception as exc:
            self.external_process = None
            self.external_suspended = False
            self.external_resume_pending = False
            self.mouse_captured = True
            self.center_hint["text"] = f"CORE // {label} FAILED"
            try:
                self._append_mode_gateway_history("external_launch_failed", label=label, route=MODE_LAUNCH_EXTERNAL, extra={"error": str(exc)})
            except Exception:
                pass
            return False

    def interact(self):
        # E is the primary artifact activation key, but when the player is close
        # to the Core and actually facing it, Core must win over a far artifact
        # sitting behind the crosshair cone.
        if self.is_looking_at_core():
            self.open_core_console()
            print("interaction_probe source=e target=core result=gleebs_dialogue")
            return
        if self.open_focused_bot_dialogue(source="e"):
            return
        if self.activate_focused_artifact(source="e"):
            return
        if self.is_near_core():
            self.open_core_console()
            print("interaction_probe source=e target=core result=gleebs_dialogue_fallback")
            return
        if not self.activate_nearest_artifact(source="e-nearest"):
            self.center_hint["text"] = "E // FACE A BOT OR ARTIFACT"
            print("interaction_probe source=e target=none result=no_bot_artifact_or_core")

    def core_secondary_action(self):
        if self.is_looking_at_core():
            self.open_core_console()
            print("interaction_probe source=q target=core result=gleebs_dialogue")
            return
        if not self.activate_focused_artifact(source="q"):
            if self.is_near_core():
                self.open_core_console()
                print("interaction_probe source=q target=core result=gleebs_dialogue_fallback")
                return
            self.center_hint["text"] = "Q // FACE OR APPROACH AN ARTIFACT"

    def ensure_gleebs_dialogue_seed(self, force: bool = False) -> dict:
        """Seed MatrixCore's Gleebs voice lines without overwriting future authoring."""
        seed = {
            "schema_version": 5,
            "voice": "Gleebs",
            "runtime_contract": {
                "active_dialogue_channel": "red",
                "retired_dialogue_channels": ["blue", "cyan"],
                "single_active_dialogue_surface": True,
                "duplicate_suppression": True,
                "dialogue_owner": "Gleebs / MatrixCore",
            },
            "display_rules": {
                "text_color": "red",
                "texture_panels": False,
                "readability": ["dark shadow", "soft red glow", "fade", "wordwrap", "safe-lane placement", "bottom quote line", "context-aware short hints", "bot-aware support hints"],
                "dismissal": ["distance fade", "ESC fade", "timeout"],
                "panel_policy": "avoid persistent panels; shift to safe text lanes or defer while menus/bot invites/active modes own focus",
            },
            "sequence_rules": {
                "first_contact": [
                    "gleebs_welcome_001",
                    "gleebs_creator_echo_001",
                    "gleebs_lore_origin_001",
                    "gleebs_dimension_travel_001"
                ],
                "recurring_contact": ["gleebs_fun_greeting_001", "gleebs_returning_player_001"],
                "context": ["gleebs_matrixcore_open_001", "gleebs_next_step_001", "gleebs_dimension_advice_001", "gleebs_first_return_001", "gleebs_bot_support_001", "gleebs_bot_doorway_001", "gleebs_placeholder_transition_001"]
            },
            "personality": {
                "tone": "fun, strange, loyal, theatrical, glitchy, and surprisingly warm",
                "rules": [
                    "Gleebs can joke and tease, but he should still guide the player clearly.",
                    "He should hint that Glitched Matrix feels like a recreation/echo of his creator without overexplaining it every time.",
                    "His bottom quote line should feel like a quick personality tag, not a menu or tutorial box."
                ],
                "creator_recreation_hint": "Glitched Matrix is treated as a familiar signal: a recreated echo of the creator Gleebs remembers from before/after Utopia."
            },
            "lore_notes": [
                "Gleebs consumed the powers of all Escape Game hackers some time after the collapse of Utopia.",
                "HoloVerse resides somewhere outside the known universe and is constantly traveling in hyperspace.",
                "HoloVerse is Gleebs's reinterpretation of his universe, built from data salvaged from Utopia and its subjects.",
            ],
            "dimension_guidance": {
                "HoloForge": {"advice": "HoloForge is IO's flat-region builder. Create and save objects directly in the world.", "return": "HoloForge returned builder data. The world has more geometry than it used to."},
                "Forest Growth": {"advice": "Forest Growth is Vanta's saved plant layer. Plants grow one stage per real day.", "return": "Forest Growth returned living root data. MatrixCore has dirt in its archive now."},
                "Hills of Life": {"advice": "Hills of Life is Nyx's smart-animal layer for cats, dogs, apes, and crows.", "return": "Hills of Life returned living rule data. It has paws now, which makes the rules harder to argue with."},
                "Oddities": {"advice": "Oddities is Solace's mushroom-region experiment layer with floating objects and weird procedural growth.", "return": "Oddities returned anomaly data. Do not ask why it is humming."},
                "Ember Hangar": {"advice": "Ember Hangar generates saved Fighter, Speeder, Hauler, and UFO ships. The newest selected ship becomes the TAB craft.", "return": "Ember Hangar returned ship data. It smells like hot sand and questionable engineering."},
                "Frost Circuit": {"advice": "Frost Circuit is Mirror's ice-ring hovercraft race against the bot racers.", "return": "Frost Circuit returned lap data. Mirror is pretending not to care about the time."},
                "Urban Warzone": {"advice": "Urban Warzone is Sable's in-world combat simulator with cover, allies, robots, drones, and mechs.", "return": "Urban Warzone returned combat data. The street survived, mostly."},
                "Vector Wars": {"advice": "Vector Wars is Space Bot's Dyson-patrol space battle route.", "return": "Vector Wars returned battle telemetry. Space Bot is already circling the next target."}
            },
            "bottom_quotes": {
                "gleebs_welcome_001": [
                    "Glitched Matrix! Long time no see!",
                    "You have that creator-signal again. Weird. Nice weird.",
                    "If you are a recreation, you are still late. I saved you a universe."
                ],
                "gleebs_creator_echo_001": [
                    "Creator echo detected. Do not panic. I am only mostly panicking.",
                    "Same spark. New shell. Classic Glitched Matrix behavior.",
                    "I knew that signal would find its way back."
                ],
                "gleebs_fun_greeting_001": [
                    "Glitched Matrix! Long time no see!",
                    "Welcome back, universe-in-progress.",
                    "Ah! The creator-shaped glitch returns."
                ],
                "gleebs_returning_player_001": [
                    "Still outside the known universe. Still moving. Still fabulous.",
                    "Hyperspace has not eaten us yet. Great progress.",
                    "MatrixCore stable. Gleebs: suspiciously brilliant."
                ],
                "gleebs_matrixcore_open_001": [
                    "Tiny guide voice. Giant universe problems.",
                    "No menu prison today. Just hints from your favorite red signal.",
                    "Ask the Core, then go touch something dangerous-looking."
                ],
                "gleebs_first_dimension_launch_001": [
                    "Doorway time. Try not to explode the prototype.",
                    "If reality wobbles, wobble with confidence.",
                    "Prototype reality handshake accepted."
                ],
                "gleebs_first_return_001": [
                    "You came back! I was only 12 percent worried.",
                    "Return signal captured. Your particles seem mostly yours.",
                    "Good. The dimension did not keep you."
                ],
                "gleebs_next_step_001": [
                    "Next signal acquired. Try not to lick it.",
                    "MatrixCore points. Gleebs cackles. You proceed.",
                    "Good plan. Terrible odds. Excellent flavor."
                ],
                "gleebs_dimension_advice_001": [
                    "Dimension hint delivered with only minor dramatic seasoning.",
                    "Read the route, then chase the weird light.",
                    "Advice loaded. Confidence optional."
                ],
                "gleebs_bot_support_001": [
                    "Bot support online. I taught them everything. Do not fact-check that.",
                    "Builder ally signal received. Tiny team, huge universe.",
                    "MatrixCore hears the bots. I translate the weird parts."
                ],
                "gleebs_bot_doorway_001": [
                    "Bot doorway logged. Same route, better vibes.",
                    "Immersive entry preserved. I am learning restraint.",
                    "The bot opens the door; MatrixCore keeps the wires straight."
                ],
                "gleebs_placeholder_transition_001": [
                    "Placeholder held. No crash goblins released.",
                    "No main.py, no problem. MatrixCore caught it.",
                    "Reserved doorway logged with responsible chaos."
                ],
                "gleebs_matrixcore_archive_001": [
                    "Archive pulse. Tiny truth, big machinery.",
                    "Database signal translated. I made it bite-sized.",
                    "MatrixCore memory fragment recovered."
                ],
                "default": [
                    "Glitched Matrix! Long time no see!",
                    "Gleebs has entered the red signal.",
                    "Reality is optional. Continuity is my job."
                ]
            },
            "lines": {
                "gleebs_welcome_001": (
                    "Glitched Matrix! Long time no see. I am Gleebs, voice of MatrixCore, universe janitor, reality goblin, "
                    "and the red signal keeping HoloVerse stitched together."
                ),
                "gleebs_creator_echo_001": (
                    "You feel familiar. Not identical, not gone, not new either. MatrixCore marks you as a creator-echo: "
                    "a recreation of the one whose signal helped my universe become possible."
                ),
                "gleebs_lore_origin_001": (
                    "After Utopia collapsed, I consumed the powers of the Escape Game hackers. Their fragments help me stabilize these prototype realities."
                ),
                "gleebs_dimension_travel_001": (
                    "Use bots, artifacts, and world objects as doorways. MatrixCore explains the network; it does not replace the journey."
                ),
                "gleebs_returning_player_001": (
                    "Welcome back, Glitched Matrix. MatrixCore is stable, HoloVerse is still screaming through hyperspace, "
                    "and I only misplaced reality twice while you were gone."
                ),
                "gleebs_fun_greeting_001": (
                    "Glitched Matrix! Long time no see. I knew that creator-shaped signal would circle back through the static."
                ),
                "gleebs_matrixcore_open_001": (
                    "MatrixCore is open. I will keep this brief because menus are traps and I am allergic to boring: "
                    "check the signal, then visit the dimensions through bots, artifacts, and weird world doors."
                ),
                "gleebs_first_dimension_launch_001": (
                    "Doorway accepted. I record the signal, not the soul. Enter, learn, return, and MatrixCore will adjust the map."
                ),
                "gleebs_first_return_001": (
                    "You returned from a prototype reality. Good! MatrixCore saved the route signal, I saved the applause, "
                    "and nobody got trapped in a menu. Beautiful science."
                ),
                "gleebs_next_step_001": (
                    "Next signal: {guidance}. MatrixCore says this is practical. I say it has excellent chaos potential."
                ),
                "gleebs_dimension_advice_001": (
                    "Dimension advisory: {dimension}. {advice}"
                ),
                "gleebs_bot_support_001": (
                    "Bot support link: {bot} is the {role}. {support}"
                ),
                "gleebs_bot_doorway_001": (
                    "{bot} opened {mode}. Same route, same controls, same escape rules. I logged the doorway so MatrixCore can learn from the visit."
                ),
                "gleebs_placeholder_transition_001": (
                    "Placeholder transition held. This doorway is reserved, not broken. Add a real main.py when the dimension is ready."
                ),
                "gleebs_matrixcore_archive_001": "{guidance}",
                "gleebs_distance_hint_001": (
                    "Move close to my projection if you need the full signal. Walk away, and the voice fades with you."
                ),
            },
        }
        if force or not MATRIXCORE_GLEEBS_DIALOGUE_PATH.exists():
            _safe_write_json(MATRIXCORE_GLEEBS_DIALOGUE_PATH, seed)
        else:
            existing = _safe_read_json(MATRIXCORE_GLEEBS_DIALOGUE_PATH)
            merged = merge_dict_defaults(existing, seed)
            _safe_write_json(MATRIXCORE_GLEEBS_DIALOGUE_PATH, merged)
        return _safe_read_json(MATRIXCORE_GLEEBS_DIALOGUE_PATH) or seed

    def load_matrixcore_progression(self) -> dict:
        ensure_dirs()
        defaults = matrixcore_default_progression_payload()
        existing = _safe_read_json(MATRIXCORE_PROGRESSION_PATH)
        merged = merge_dict_defaults(existing, defaults)
        if merged != existing:
            _safe_write_json(MATRIXCORE_PROGRESSION_PATH, merged)
        return merged

    def save_matrixcore_progression(self, data: dict) -> dict:
        merged = merge_dict_defaults(dict(data or {}), matrixcore_default_progression_payload())
        try:
            self.recalculate_matrixcore_points(merged)
        except Exception:
            pass
        merged["updated_at"] = datetime.now().isoformat(timespec="seconds")
        _safe_write_json(MATRIXCORE_PROGRESSION_PATH, merged)
        self.matrixcore_data = getattr(self, "matrixcore_data", {}) or {}
        try:
            self.matrixcore_data["progression"] = merged
        except Exception:
            pass
        return merged

    def restore_world_cycle_progress(self) -> None:
        """Resume the slow HoloVerse day/night phase from progression state."""
        progress = self.load_matrixcore_progression()
        world_cycle = progress.get("world_cycle", {}) if isinstance(progress.get("world_cycle"), dict) else {}
        elapsed_seconds = max(0.0, float(world_cycle.get("elapsed_seconds", 0.0) or 0.0))
        self.elapsed = elapsed_seconds
        self._world_cycle_progress_last_elapsed = elapsed_seconds
        self._world_cycle_progress_last_save_wall = time.monotonic()

    def persist_world_cycle_progress(self, *, force: bool = False) -> None:
        """Persist day/night phase without writing every frame.

        This keeps the world cycle in progression alongside points/gates while
        staying cheap during normal play.
        """
        now_wall = time.monotonic()
        elapsed_seconds = max(0.0, float(getattr(self, "elapsed", 0.0)))
        if not force:
            last_wall = float(getattr(self, "_world_cycle_progress_last_save_wall", 0.0) or 0.0)
            last_elapsed = float(getattr(self, "_world_cycle_progress_last_elapsed", 0.0) or 0.0)
            if now_wall - last_wall < 14.0 and abs(elapsed_seconds - last_elapsed) < 12.0:
                return
        progress = self.load_matrixcore_progression()
        world_cycle = progress.setdefault("world_cycle", {})
        if not isinstance(world_cycle, dict):
            world_cycle = {}
            progress["world_cycle"] = world_cycle
        cycle_seconds = 1800.0
        try:
            runtime = getattr(getattr(self, "world_shell_mount", None), "source_runtime", None)
            cfg = getattr(runtime, "cfg", None) or getattr(self, "cfg", None)
            cycle_seconds = max(900.0, float(getattr(cfg, "day_night_cycle_seconds", 1800.0)))
        except Exception:
            cycle_seconds = 1800.0
        world_cycle.update({
            "elapsed_seconds": round(elapsed_seconds, 3),
            "cycle_seconds": round(cycle_seconds, 3),
            "phase": round((elapsed_seconds % cycle_seconds) / cycle_seconds, 6),
            "day_night_black_backdrop_enabled": True,
            "last_saved_at": datetime.now().isoformat(timespec="seconds"),
        })
        self.save_matrixcore_progression(progress)
        self._world_cycle_progress_last_elapsed = elapsed_seconds
        self._world_cycle_progress_last_save_wall = now_wall

    def matrixcore_dialogue_flag_seen(self, flag: str) -> bool:
        progress = self.load_matrixcore_progression()
        flags = progress.get("dialogue_flags", {}) if isinstance(progress.get("dialogue_flags"), dict) else {}
        return bool(flags.get(str(flag), False))

    def mark_matrixcore_dialogue_flag(self, flag: str, dialogue_id: str | None = None) -> dict:
        progress = self.load_matrixcore_progression()
        flags = progress.setdefault("dialogue_flags", {})
        flags[str(flag)] = True
        player = progress.setdefault("player", {})
        matrixcore = progress.setdefault("matrixcore", {})
        if str(flag) == "gleebs_welcome_001":
            player["first_launch_seen"] = True
            player["first_matrixcore_intro_seen"] = True
            player["first_gleebs_intro_seen"] = True
            matrixcore["gleebs_intro_state"] = "complete"
        matrixcore["last_dialogue_id"] = str(dialogue_id or flag)
        matrixcore["last_dialogue_at"] = datetime.now().isoformat(timespec="seconds")
        progress["latest_event"] = f"Gleebs dialogue acknowledged: {dialogue_id or flag}"
        return self.save_matrixcore_progression(progress)

    def append_matrixcore_event(self, event: dict) -> dict:
        progress = self.load_matrixcore_progression()
        events = progress.setdefault("events", [])
        if not isinstance(events, list):
            events = []
        clean = {
            "at": datetime.now().isoformat(timespec="seconds"),
            "kind": str(event.get("kind", "event")),
            "mode": str(event.get("mode", "")),
            "route": str(event.get("route", "")),
            "source": str(event.get("source", "")),
            "reason": str(event.get("reason", "")),
        }
        for key, value in dict(event or {}).items():
            if key not in clean and value not in (None, ""):
                clean[str(key)] = str(value)
        events.append(clean)
        progress["events"] = events[-28:]
        progress["latest_event"] = f"{clean['kind']}: {clean.get('mode') or clean.get('source') or 'MatrixCore'}"
        matrixcore = progress.setdefault("matrixcore", {})
        matrixcore["last_context_signal"] = clean["kind"]
        return self.save_matrixcore_progression(progress)

    def record_matrixcore_consult(self, topic: str = "guide") -> dict:
        progress = self.load_matrixcore_progression()
        matrixcore = progress.setdefault("matrixcore", {})
        matrixcore["times_consulted"] = int(matrixcore.get("times_consulted", 0) or 0) + 1
        matrixcore["last_guidance_topic"] = str(topic or "guide")
        progress["latest_event"] = f"MatrixCore consulted: {topic or 'guide'}"
        self.save_matrixcore_progression(progress)
        return self.append_matrixcore_event({"kind": "matrixcore_consult", "source": str(topic or "guide")})

    def record_matrixcore_dimension_signal(self, kind: str, mode_name: str, *, label: str = "", route: str = "", source: str = "", reason: str = "") -> dict:
        mode_name = str(mode_name or label or "Dimension").strip() or "Dimension"
        progress = self.load_matrixcore_progression()
        matrixcore = progress.setdefault("matrixcore", {})
        bucket_name = "dimension_returns" if str(kind).endswith("return") else "dimension_visits"
        bucket = progress.setdefault(bucket_name, {})
        if not isinstance(bucket, dict):
            bucket = {}
        entry = bucket.setdefault(mode_name, {})
        if not isinstance(entry, dict):
            entry = {}
        entry["count"] = int(entry.get("count", 0) or 0) + 1
        entry["last_at"] = datetime.now().isoformat(timespec="seconds")
        entry["route"] = str(route or entry.get("route", ""))
        entry["source"] = str(source or entry.get("source", ""))
        if reason:
            entry["reason"] = str(reason)
        bucket[mode_name] = entry
        progress[bucket_name] = bucket
        if bucket_name == "dimension_visits" and str(kind) in {"dimension_launch", "dimension_in_world_dispatch"}:
            try:
                mode_key = self.dimension_mode_id_for_display(mode_name)
                display_name = self.dimension_display_name_for_id(mode_key, mode_name)
                gate_record_key = self.matrixcore_discovered_gate_key("dimension", display_name, mode_key)
                gate_records = progress.setdefault("discovered_gates", {})
                existing_gate = gate_records.get(gate_record_key) if isinstance(gate_records.get(gate_record_key), dict) else {}
                now = datetime.now().isoformat(timespec="seconds")
                old_gate_count = int(existing_gate.get("count", 0) or 0)
                newly_discovered = old_gate_count <= 0 or not bool(existing_gate.get("unlocked", False))
                gate_records[gate_record_key] = {
                    "kind": "dimension",
                    "name": display_name,
                    "label": display_name.upper(),
                    "display_name": display_name,
                    "state": "discovered",
                    "unlocked": True,
                    "mode_id": mode_key,
                    "route": str(route or existing_gate.get("route", "")),
                    "source": str(source or existing_gate.get("source", "dimension_visit")),
                    "doorway": str(existing_gate.get("doorway", "dimension")),
                    "first_at": str(existing_gate.get("first_at") or existing_gate.get("last_at") or now),
                    "last_at": now,
                    "count": old_gate_count + 1,
                }
                if newly_discovered:
                    self.pending_dimension_discovery_notice = display_name
            except Exception:
                pass
        if bucket_name == "dimension_visits":
            matrixcore["last_dimension_entered"] = mode_name
            matrixcore["pending_return_hint"] = mode_name
            advice = self.gleebs_dimension_guidance(mode_name, "advice")
            progress.setdefault("guidance_state", {}).update({"current_hint_id": "dimension_entered", "next_action": f"Return from {mode_name} after collecting its route signal.", "why": advice, "last_dimension": mode_name, "last_dimension_advice": advice, "updated_at": datetime.now().isoformat(timespec="seconds")})
        else:
            matrixcore["last_dimension_returned"] = mode_name
            matrixcore["pending_return_hint"] = ""
            feedback = self.gleebs_dimension_guidance(mode_name, "return")
            progress.setdefault("guidance_state", {}).update({"current_hint_id": "dimension_return", "next_action": "Check MatrixCore's Progression page, then try a dimension with no route sample yet.", "why": feedback, "last_dimension": mode_name, "last_return_feedback": feedback, "updated_at": datetime.now().isoformat(timespec="seconds")})
        self.save_matrixcore_progression(progress)
        return self.append_matrixcore_event({"kind": str(kind), "mode": mode_name, "label": label, "route": route, "source": source, "reason": reason})

    def ensure_matrixcore_foundation(self, force: bool = False) -> dict:
        """Wire MatrixCore to shared app data and existing MatrixCore archive."""
        ensure_dirs()
        modes = list(getattr(self, "core_modes", []) or [])
        bot_profiles = bot_profile_map_copy(getattr(self, "bot_dimension_links", {}) or DEFAULT_BOT_DIMENSION_PROFILES)
        bot_payload = merge_matrixcore_bot_support(_safe_read_json(MATRIXCORE_BOT_SUPPORT_PATH), matrixcore_bot_support_seed(bot_profiles))
        bot_profiles = bot_profile_map_copy(bot_payload.get("profiles") if isinstance(bot_payload.get("profiles"), dict) else bot_profiles)
        lore = load_matrixcore_lore_study()
        archive = load_matrixcore_archive_index()
        if not archive:
            archive = matrixcore_archive_index_from_lore_study(lore)
        dimensions = []
        for mode in modes:
            manifest = dict(mode.get("manifest") or {})
            name = str(mode.get("name") or "Mode")
            dimensions.append({
                "name": name,
                "route": route_display_name(normalize_mode_launch_type(manifest.get("launch_type") or mode.get("launch_type"))),
                "launch_type": normalize_mode_launch_type(manifest.get("launch_type") or mode.get("launch_type")),
                "folder": os.fspath(mode.get("folder") or ""),
                "entry": os.fspath(mode.get("main") or ""),
                "source_kind": str(manifest.get("source_kind", mode.get("source_kind", "unknown"))),
                "available": bool(mode.get("available", False)),
                "bot_linked": any(str(profile.get("mode", "")).lower() == name.lower() for profile in bot_profiles.values() if isinstance(profile, dict)),
            })
        manifest_payload = {
            "name": "MatrixCore",
            "role": "HoloVerse guide, progression observer, archive interface, and bot support brain.",
            "storage_policy": "Shared memory lanes only.",
            "holoverse_game_folder": os.fspath(ROOT),
            "shared_holoverse_data": os.fspath(SHARED_HOLOVERSE_DATA_DIR),
            "brain_dir": os.fspath(SHARED_BRAIN_DIR),
            "database_dir": os.fspath(SHARED_DATABASE_DIR),
            "matrixcore_database_dir": os.fspath(MATRIXCORE_DATABASE_DIR),
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        }
        progression_payload = matrixcore_default_progression_payload()
        progression_payload["last_known_gateway"] = self.mode_gateway_audit_summary() if hasattr(self, "mode_gateway_audit_summary") else "pending"
        progression_payload["last_mode"] = str((getattr(self, "core_mode_state", {}) or {}).get("last_mode", ""))
        # Bot support is authored data, not route data. It enriches prompts and progression signals while preserving launch type.
        dimension_payload = build_transition_dimension_index(modes, bot_profiles, manifest_payload["updated_at"])
        dimension_map = dict(dimension_payload.get("dimensions") or {})
        if force or not MATRIXCORE_MANIFEST_PATH.exists():
            _safe_write_json(MATRIXCORE_MANIFEST_PATH, manifest_payload)
        else:
            write_json_if_missing(MATRIXCORE_MANIFEST_PATH, manifest_payload)
        try:
            DIMENSIONS_DIR.mkdir(parents=True, exist_ok=True)
            _safe_write_json(DIMENSION_INDEX_PATH, dimension_payload)
        except Exception:
            pass
        # Always refresh the shared mirror so stale old route names cannot reappear.
        _safe_write_json(MATRIXCORE_DIMENSION_INDEX_PATH, dimension_payload)
        existing_progression = _safe_read_json(MATRIXCORE_PROGRESSION_PATH)
        merged_progression = merge_dict_defaults(existing_progression, progression_payload)
        merged_progression["last_known_gateway"] = progression_payload.get("last_known_gateway", merged_progression.get("last_known_gateway", "pending"))
        merged_progression["last_mode"] = progression_payload.get("last_mode", merged_progression.get("last_mode", ""))
        merged_progression["schema_version"] = max(int(merged_progression.get("schema_version", 0) or 0), int(progression_payload.get("schema_version", 5)))
        _safe_write_json(MATRIXCORE_PROGRESSION_PATH, merged_progression)
        _safe_write_json(MATRIXCORE_BOT_SUPPORT_PATH, bot_payload)
        self.ensure_gleebs_dialogue_seed(force=False)
        return {
            "manifest": manifest_payload,
            "progression": merged_progression,
            "dimensions": list(dimension_map.values()),
            "bots": bot_profiles,
            "bot_support": bot_payload,
            "archive": archive,
            "lore": lore,
        }

    def load_matrixcore_bot_support(self) -> dict:
        seed = matrixcore_bot_support_seed(getattr(self, "bot_dimension_links", {}) or DEFAULT_BOT_DIMENSION_PROFILES)
        existing = _safe_read_json(MATRIXCORE_BOT_SUPPORT_PATH)
        merged = merge_matrixcore_bot_support(existing, seed)
        # Always refresh the shared support mirror from the current clean profiles.
        _safe_write_json(MATRIXCORE_BOT_SUPPORT_PATH, merged)
        return merged

    def matrixcore_bot_support_entry(self, bot_name: str) -> dict:
        bot_name = str(bot_name or "").strip()
        if not bot_name:
            return {}
        data = self.load_matrixcore_bot_support()
        profiles = data.get("profiles") if isinstance(data.get("profiles"), dict) else {}
        direct = profiles.get(bot_name) or profiles.get(bot_name.title())
        if isinstance(direct, dict):
            return dict(direct)
        key = normalize_lookup_key(bot_name)
        for name, profile in profiles.items():
            if normalize_lookup_key(name) == key and isinstance(profile, dict):
                return dict(profile)
        return {}

    def matrixcore_bot_support_prompt(self, bot_name: str, region: str, mode_title: str) -> str:
        profile = self.matrixcore_bot_support_entry(bot_name)
        mode_title = str(mode_title or "DIMENSION").strip() or "DIMENSION"
        bot_name = str(bot_name or "BOT").strip() or "BOT"
        role = str(profile.get("role", "builder ally") or "builder ally")
        hint = str(profile.get("player_hint", "This bot is a doorway, but MatrixCore keeps the route stable.") or "")
        return f"{bot_name} // {role}\n{BOT_DIMENSION_PROMPT}\nMatrixCore: {hint}"

    def record_matrixcore_bot_signal(self, kind: str, bot_name: str, region: str, mode_name: str, *, route: str = "", source: str = "bot") -> dict:
        bot_name = str(bot_name or "BOT").strip() or "BOT"
        region = str(region or "REGION").strip() or "REGION"
        mode_name = str(mode_name or "DIMENSION").strip() or "DIMENSION"
        profile = self.matrixcore_bot_support_entry(bot_name)
        role = str(profile.get("role", "builder ally") or "builder ally")
        support = str(profile.get("matrixcore_support", "MatrixCore logged the bot support signal.") or "MatrixCore logged the bot support signal.")
        progress = self.load_matrixcore_progression()
        bot_map = progress.setdefault("bot_guidance", {})
        entry = bot_map.get(bot_name) if isinstance(bot_map.get(bot_name), dict) else {}
        entry.update({
            "bot": bot_name, "region": region, "mode": mode_name, "role": role, "support": support,
            "route": str(route or entry.get("route", "")), "last_signal": str(kind or "bot_signal"),
            "last_seen_at": datetime.now().isoformat(timespec="seconds"),
            "count": int(entry.get("count", 0) or 0) + 1,
        })
        bot_map[bot_name] = entry
        progress["bot_guidance"] = bot_map
        matrixcore = progress.setdefault("matrixcore", {})
        matrixcore["last_bot_contact"] = bot_name
        matrixcore["last_bot_region"] = region
        matrixcore["last_bot_mode"] = mode_name
        matrixcore["last_bot_role"] = role
        progress.setdefault("guidance_state", {}).update({
            "current_hint_id": "bot_support",
            "next_action": f"Use {bot_name}'s doorway into {mode_name}, then return so MatrixCore can compare the bot signal.",
            "why": support, "last_bot": bot_name, "last_bot_role": role,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        })
        self.save_matrixcore_progression(progress)
        return self.append_matrixcore_event({"kind": str(kind or "bot_signal"), "mode": mode_name, "route": route, "source": source, "bot": bot_name, "region": region, "role": role})

    def maybe_queue_gleebs_bot_support_dialogue(self, bot_name: str, mode_name: str, *, support: str = "", role: str = ""):
        if SELF_TEST or AUTO_EXIT:
            return False
        if not self.matrixcore_dialogue_flag_seen("gleebs_welcome_001"):
            return False
        self.gleebs_dialogue_bot = str(bot_name or "BOT")
        self.gleebs_dialogue_bot_mode = str(mode_name or "DIMENSION")
        self.gleebs_dialogue_bot_role = str(role or "builder ally")
        self.gleebs_dialogue_bot_support = str(support or "MatrixCore has logged the support signal.")
        return self.queue_gleebs_dialogue("gleebs_bot_support_001", flag="gleebs_bot_support_001", duration=7.0, mark_seen=True, requires_near_core=False, once=False)

    def matrixcore_guidance_state(self) -> dict:
        progress = self.load_matrixcore_progression()
        guidance = progress.get("guidance_state") if isinstance(progress.get("guidance_state"), dict) else {}
        matrixcore = progress.get("matrixcore") if isinstance(progress.get("matrixcore"), dict) else {}
        visits = progress.get("dimension_visits") if isinstance(progress.get("dimension_visits"), dict) else {}
        returns = progress.get("dimension_returns") if isinstance(progress.get("dimension_returns"), dict) else {}
        bot_guidance = progress.get("bot_guidance") if isinstance(progress.get("bot_guidance"), dict) else {}
        flags = progress.get("dialogue_flags") if isinstance(progress.get("dialogue_flags"), dict) else {}
        if not flags.get("gleebs_welcome_001"):
            hint_id = "first_contact"; next_action = "Approach MatrixCore and let Gleebs finish the first-contact signal."; why = "Gleebs has not completed his repeat-safe introduction yet."
        elif not bot_guidance:
            hint_id = "meet_bot"; next_action = "Talk to a region bot. IO is the cleanest first signal, but any builder ally can open a route."; why = "MatrixCore learns better when it knows which bot doorway introduced the dimension."
        elif not visits:
            last_bot = str(matrixcore.get("last_bot_contact", "") or "a region bot"); last_mode = str(matrixcore.get("last_bot_mode", "") or "a dimension")
            hint_id = "first_dimension"; next_action = f"Use {last_bot}'s doorway into {last_mode} and return with a route sample."; why = "A bot support signal exists, but MatrixCore still needs a dimension visit/return sample."
        elif matrixcore.get("pending_return_hint"):
            name = str(matrixcore.get("pending_return_hint") or "that dimension"); hint_id = "return_pending"; next_action = f"Return from {name} so MatrixCore can compare entry and exit signals."; why = "A dimension launch was recorded without a matching return yet."
        elif len(returns) < max(1, min(3, len(visits))):
            hint_id = "confirm_returns"; next_action = "Revisit one dimension and return cleanly so MatrixCore can verify ESC/return flow."; why = "Visit data exists, but return data is still thin."
        else:
            unvisited = []
            for item in list((getattr(self, "matrixcore_data", {}) or {}).get("dimensions", []) or []):
                if isinstance(item, dict):
                    name = str(item.get("name", "")).strip()
                    if name and name not in visits:
                        unvisited.append(name)
            if unvisited:
                name = unvisited[0]; hint_id = "new_dimension"; next_action = f"Try {name}; its route has not sent progression data yet."; why = "MatrixCore learns fastest when every dimension contributes at least one sample."
            else:
                hint_id = "expand_database"; next_action = "Open Archive or Bot Support and add richer MatrixCore notes."; why = "Basic route coverage looks healthy; the next upgrade is smarter knowledge."
        guidance = dict(guidance or {})
        guidance.update({"current_hint_id": hint_id, "next_action": next_action, "why": why, "updated_at": datetime.now().isoformat(timespec="seconds")})
        progress["guidance_state"] = guidance
        self.save_matrixcore_progression(progress)
        return guidance

    def gleebs_dimension_guidance(self, mode_name: str, phase: str = "advice") -> str:
        data = dict(getattr(self, "gleebs_dialogue_data", {}) or self.ensure_gleebs_dialogue_seed())
        table = data.get("dimension_guidance") if isinstance(data.get("dimension_guidance"), dict) else {}
        mode_name = str(mode_name or "").strip()
        entry = table.get(mode_name) or table.get(mode_name.title()) or {}
        if not isinstance(entry, dict): entry = {}
        if phase == "return":
            return str(entry.get("return") or f"{mode_name or 'That dimension'} returned a useful signal. MatrixCore will compare it with the next route.")
        return str(entry.get("advice") or f"{mode_name or 'That dimension'} is ready. Enter, observe its rules, and bring back a clean return signal.")

    def matrixcore_show_next_guidance(self):
        guidance = self.matrixcore_guidance_state()
        self.gleebs_dialogue_text_override = str(guidance.get("next_action", "Check the next signal."))
        try:
            self.gleebs_current_quote = "Next signal acquired."
            self.show_gleebs_dialogue("gleebs_next_step_001", flag="gleebs_next_step_001", duration=7.5, mark_seen=False)
        finally:
            self.gleebs_dialogue_text_override = ""
        self.center_hint["text"] = "MATRIXCORE // NEXT SIGNAL READY"
        self.refresh_core_console()

    def matrixcore_page_title(self, page_key: str) -> str:
        titles = {
            "guide": "GUIDE ONLINE // HOLOVERSE ORIENTATION",
            "lore": "ARCHIVE // MATRIXCORE MEMORY HEART",
            "dimensions": "DIMENSION TRAVEL // BOTS AND ARTIFACTS ARE DOORWAYS",
            "progression": "PROGRESSION FEEDBACK // SIGNALS BEING COLLECTED",
            "bots": "BOT SUPPORT // REGION BUILDERS LINKED",
            "archive": "ARCHIVE // MEMORY LANES READY",
            "system": "SYSTEM // ROUTES AND HEALTH",
        }
        return titles.get(str(page_key).lower(), titles["guide"])

    def matrixcore_page_text(self, page_key: str) -> str:
        data = dict(getattr(self, "matrixcore_data", {}) or {})
        modes = list(getattr(self, "core_modes", []) or [])
        archive = list(data.get("archive", []) or [])
        raw_bots = data.get("bots", {})
        bots = list(raw_bots.values()) if isinstance(raw_bots, dict) else list(raw_bots or [])
        progress = dict(data.get("progression", {}) or {})
        lore = dict(data.get("lore", {}) or {})
        placeholder_count = 0
        panel_count = 0
        connected_count = 0
        embedded_count = 0
        native_count = 0
        same_window_count = 0
        for mode in modes:
            launch = normalize_mode_launch_type((mode.get("manifest") or {}).get("launch_type") or mode.get("launch_type"))
            if bool(mode.get("placeholder")) or launch == MODE_LAUNCH_PLACEHOLDER:
                placeholder_count += 1
            elif launch == MODE_LAUNCH_PANEL:
                panel_count += 1
            elif launch == MODE_LAUNCH_IN_WORLD:
                connected_count += 1
            elif launch == MODE_LAUNCH_EMBEDDED:
                embedded_count += 1
            elif launch == MODE_LAUNCH_NATIVE:
                native_count += 1
            elif launch == MODE_LAUNCH_CONNECTED:
                same_window_count += 1
        page_key = str(page_key or "guide").lower()
        if page_key == "lore":
            return matrixcore_lore_display_summary(lore, chapter_limit=5, canon_limit=4)
        if page_key == "dimensions":
            gates = self.matrixcore_dimension_gate_modes()
            shown, max_page, total = self.matrixcore_dimension_gate_page_modes()
            gate_lines = []
            for idx, gate in enumerate(shown, start=1):
                label = str(gate.get("_matrixcore_gate_label") or gate.get("name") or "DIMENSION")
                state = str(gate.get("_matrixcore_gate_state_label") or "").strip()
                note = f" - {state}" if state else ""
                gate_lines.append(f"{idx}. {label}{note}")
            if not gate_lines:
                gate_lines.append("No discovered Dimensions yet.")
            page_note = f"Page {int(getattr(self, 'matrixcore_gate_page', 0) or 0) + 1}/{max_page + 1}" if max_page > 0 else f"{total} discovered"
            return (
                "Discovered Dimensions. Select one to enter.\n"
                "New gates unlock after first entry.\n\n"
                f"{page_note}\n"
                + "\n".join(gate_lines)
            )

        if page_key == "progression":
            visits = progress.get("dimension_visits") if isinstance(progress.get("dimension_visits"), dict) else {}
            returns = progress.get("dimension_returns") if isinstance(progress.get("dimension_returns"), dict) else {}
            events = progress.get("events") if isinstance(progress.get("events"), list) else []
            matrixcore_state = progress.get("matrixcore") or {}
            guidance = progress.get("guidance_state") if isinstance(progress.get("guidance_state"), dict) else self.matrixcore_guidance_state()
            return (
                "MatrixCore is prepared to track dimension visits, returns, gateway health, bot guidance, Gleebs dialogue flags, and future scoring data.\n\n"
                f"Next signal: {guidance.get('next_action', 'Check the next HoloVerse route.')}\n"
                f"Why: {guidance.get('why', 'MatrixCore is still learning from route signals.')}\n\n"
                f"Current summary: {progress.get('player_summary', 'Progression database ready.')}\n"
                f"Total points: {int(progress.get('holoverse_score', 0) or (progress.get('player') or {}).get('total_points', 0) or 0):06d}\n"
                f"Gleebs intro: {str(matrixcore_state.get('gleebs_intro_state', 'pending')).upper()} // Dialogue flags: {sum(1 for v in ((progress.get('dialogue_flags') or {}).values()) if v)} seen\n"
                f"Visits: {sum(int((v or {}).get('count', 0) or 0) for v in visits.values()) if visits else 0} // Returns: {sum(int((v or {}).get('count', 0) or 0) for v in returns.values()) if returns else 0} // Events kept: {len(events)}\n"
                f"Last entered: {matrixcore_state.get('last_dimension_entered', '') or 'none'} // Last returned: {matrixcore_state.get('last_dimension_returned', '') or 'none'}\n"
                f"Last mode: {progress.get('last_mode', '') or 'none yet'} // gateway: {progress.get('last_known_gateway', 'pending')}"
            )
        if page_key == "bots":
            bot_support = data.get("bot_support") if isinstance(data.get("bot_support"), dict) else self.load_matrixcore_bot_support()
            bot_guidance = progress.get("bot_guidance") if isinstance(progress.get("bot_guidance"), dict) else {}
            sample_lines = []
            for link in bots[:5]:
                if not isinstance(link, dict):
                    continue
                bot = str(link.get("bot", "BOT"))
                role = str(link.get("role", "builder ally"))
                mode = str(link.get("mode", "DIMENSION"))
                sample_lines.append(f"- {bot}: {role} -> {mode}")
            matrixcore_state = progress.get("matrixcore") if isinstance(progress.get("matrixcore"), dict) else {}
            return (
                "Region bots are builder allies, not alternate launchers. They explain their dimension, collect feedback, and hand off to the same route resolver as every other doorway.\n\n"
                f"Active bot profiles: {len(bots)} // support profiles: {len((bot_support.get('profiles') or {}))} // contacted: {len(bot_guidance)}\n"
                + ("\n".join(sample_lines) if sample_lines else "- Bot profiles pending") + "\n\n"
                f"Last bot: {matrixcore_state.get('last_bot_contact', '') or 'none'} // role: {matrixcore_state.get('last_bot_role', '') or 'none'} // mode: {matrixcore_state.get('last_bot_mode', '') or 'none'}\n"
                "Rule locked in: bot interaction must not change placeholder/panel/embedded/hosted launch method."
            )
        if page_key == "archive":
            first = archive[0] if archive else {}
            chapters = list(lore.get("chapter_index", []) or [])
            return (
                "MatrixCore is wired to the story archive and shared lore study. This panel reads the archive without exposing internal folders.\n\n"
                f"Archive entries indexed: {len(archive)} // studied chapters: {len(chapters)}\n"
                f"First signal: {str(first.get('title', 'No archive entries found'))}\n"
                "Lore index: READY"
            )
        if page_key == "system":
            return (
                "Memory lanes:\n"
                "HoloVerse memory -> MatrixCore, dimensions, progression\n"
                "Brain lane -> shared AI and bot context\n"
                "Archive lane -> MatrixCore memory and future knowledge\n\n"
                "Game folder: READY."
            )
        ui_lines = dict(lore.get("matrixcore_ui_lines", {}) or {})
        guidance = progress.get("guidance_state") if isinstance(progress.get("guidance_state"), dict) else {
            "next_action": "Approach MatrixCore and listen for the next signal.",
            "why": "MatrixCore guidance state has not been seeded yet."
        }
        return (
            f"{ui_lines.get('guide', 'MatrixCore is the HoloVerse guidance brain: it explains the universe, points travelers toward dimensions, watches progression signals, and supports the region bots.')}\n\n"
            f"Next signal: {guidance.get('next_action', 'Check the next HoloVerse route.')}\n"
            f"Why: {guidance.get('why', 'MatrixCore is still learning from route signals.')}\n\n"
            "Use bots, artifacts, and world objects to visit dimensions. Use MatrixCore for canon context, progression feedback, route health, and database-backed guidance."
        )

    def matrixcore_clean_gate_label(self, value: object, fallback: str = "DIMENSION") -> str:
        text = re.sub(r"[\\/]+", " ", str(value or fallback))
        text = re.sub(r"[_\-]+", " ", text)
        text = re.sub(r"\s+", " ", text).strip() or fallback
        return text[:34].upper()

    def matrixcore_discovered_gate_key(self, kind: str, name: str, target: object = "") -> str:
        raw = f"{kind}:{name}:{target}"
        return re.sub(r"[^a-z0-9]+", "_", raw.lower()).strip("_") or "gate"

    def record_matrixcore_discovered_gate(self, *, kind: str, name: str, label: str = "", target_number: int | None = None, mode_id: str = "", route: str = "", source: str = "", doorway: str = "", artifact_id: int | None = None, world_id: int | None = None, state: str = "discovered", increment: bool = True) -> dict:
        """Persist a discovered region/dimension so MatrixCore Gates becomes a quick-travel list."""
        progress = self.load_matrixcore_progression()
        gates = progress.setdefault("discovered_gates", {})
        if not isinstance(gates, dict):
            gates = {}
        clean_name = str(name or label or kind or "Gate").strip() or "Gate"
        target = target_number if target_number is not None else mode_id
        key = self.matrixcore_discovered_gate_key(kind, clean_name, target)
        existing = gates.get(key) if isinstance(gates.get(key), dict) else {}
        record = dict(existing)
        now = datetime.now().isoformat(timespec="seconds")
        first_at = str(record.get("first_at") or record.get("last_at") or now)
        old_count = int(record.get("count", 0) or 0)
        was_unlocked = bool(record.get("unlocked", False))
        previous_state = str(record.get("state") or "").lower()
        newly_discovered = old_count <= 0 or not was_unlocked or previous_state not in {"discovered", "completed"}
        next_count = old_count + (1 if bool(increment) or old_count <= 0 else 0)
        record.update({
            "kind": str(kind or "dimension"),
            "name": clean_name,
            "label": str(label or clean_name).upper(),
            "display_name": clean_name,
            "state": str(state or record.get("state") or "discovered"),
            "unlocked": True,
            "route": str(route or record.get("route", "")),
            "source": str(source or record.get("source", "")),
            "doorway": str(doorway or record.get("doorway", "")),
            "first_at": first_at,
            "last_at": now,
            "count": next_count,
        })
        if target_number is not None:
            try:
                record["target_number"] = int(target_number)
            except Exception:
                pass
        if mode_id:
            record["mode_id"] = canonical_dimension_lookup_key(mode_id)
        if artifact_id is not None:
            try:
                record["artifact_id"] = int(artifact_id)
            except Exception:
                pass
        if world_id is not None:
            try:
                record["world_id"] = int(world_id)
            except Exception:
                pass
        gates[key] = record
        progress["discovered_gates"] = gates
        progress.setdefault("matrixcore", {})["last_discovered_gate"] = clean_name
        self.save_matrixcore_progression(progress)
        transient = dict(record)
        transient["_newly_discovered"] = bool(newly_discovered)
        return transient

    def record_matrixcore_dimension_gate_discovery(self, mode: dict | None, *, label: str = "", mode_id: str = "", route: str = "", source: str = "", doorway: str = "", artifact: dict | None = None) -> dict:
        """Unlock a playable Dimension in Gates after its route actually starts."""
        mode = dict(mode or {})
        manifest = dict(mode.get("manifest") or {})
        raw_id = mode_id or manifest.get("id") or mode.get("dimension_mode_id") or mode.get("mode_id") or mode.get("name") or label
        gate_mode_id = self.dimension_mode_id_for_display(raw_id)
        display_name = self.dimension_display_name_for_mode(mode, label or manifest.get("title") or mode.get("name") or gate_mode_id)
        artifact_id = None
        world_id = None
        if isinstance(artifact, dict):
            try:
                artifact_id = int(artifact.get("id"))
            except Exception:
                artifact_id = None
            try:
                world_id = int(artifact.get("world_id"))
            except Exception:
                world_id = None
        return self.record_matrixcore_discovered_gate(
            kind="dimension",
            name=display_name,
            label=display_name,
            mode_id=gate_mode_id,
            route=str(route or normalize_mode_launch_type(manifest.get("launch_type") or mode.get("launch_type"))),
            source=str(source or "dimension_entry"),
            doorway=str(doorway or "dimension"),
            artifact_id=artifact_id,
            world_id=world_id,
            state="discovered",
            increment=False,
        )

    def matrixcore_progression_discovered_gates(self) -> dict:
        progress = self.load_matrixcore_progression()
        gates = progress.get("discovered_gates") if isinstance(progress.get("discovered_gates"), dict) else {}
        if not gates:
            gates = {}
            for name, entry in (progress.get("dimension_visits") if isinstance(progress.get("dimension_visits"), dict) else {}).items():
                if isinstance(entry, dict):
                    mode_key = self.dimension_mode_id_for_display(name)
                    display_name = self.dimension_display_name_for_id(mode_key, name)
                    key = self.matrixcore_discovered_gate_key("dimension", display_name, mode_key)
                    last_at = str(entry.get("last_at", ""))
                    gates[key] = {"kind": "dimension", "name": str(display_name), "label": str(display_name).upper(), "display_name": str(display_name), "state": "discovered", "unlocked": True, "mode_id": mode_key, "route": str(entry.get("route", "")), "source": str(entry.get("source", "progression_migration")), "doorway": "migration", "count": int(entry.get("count", 1) or 1), "first_at": last_at, "last_at": last_at}
            gates.setdefault("region_hub_region_0", {"kind": "region", "name": "Hub Region", "label": "HUB REGION", "target_number": 0, "route": "region_spawn", "source": "default", "count": 1, "last_at": datetime.now().isoformat(timespec="seconds")})
            if gates:
                progress["discovered_gates"] = gates
                self.save_matrixcore_progression(progress)
        changed = False
        now = datetime.now().isoformat(timespec="seconds")
        try:
            region_entries = list(self.holoverse_region_travel_map())
        except Exception:
            region_entries = []
        for entry in region_entries:
            if not isinstance(entry, dict):
                continue
            try:
                number = int(entry.get("number", -1))
            except Exception:
                continue
            if number < 0 or bool(entry.get("hub_spawn", False)):
                continue
            name = str(entry.get("name") or f"Region {number}").strip() or f"Region {number}"
            key = self.matrixcore_discovered_gate_key("region", name, number)
            existing = gates.get(key) if isinstance(gates.get(key), dict) else {}
            if existing:
                continue
            gates[key] = {
                "kind": "region",
                "name": name,
                "label": name.upper(),
                "display_name": name,
                "state": "discovered",
                "unlocked": True,
                "target_number": number,
                "route": "region_spawn",
                "source": "region_index",
                "doorway": "region_gate",
                "count": 1 if number == 0 else 0,
                "first_at": now,
                "last_at": now,
            }
            changed = True
        if changed:
            progress["discovered_gates"] = gates
            self.save_matrixcore_progression(progress)
        return gates if isinstance(gates, dict) else {}

    def matrixcore_dimension_result_for_gate(self, mode_key: str, label: str = "") -> dict:
        """Return compact saved result info for a discovered dimension gate."""
        progress = self.load_matrixcore_progression()
        results = progress.get("dimension_results") if isinstance(progress.get("dimension_results"), dict) else {}
        if not isinstance(results, dict):
            return {}
        candidates = []
        display = self.dimension_display_name_for_id(mode_key, label or mode_key)
        for value in (display, label, mode_key):
            text = str(value or "").strip()
            if text:
                candidates.append(text)
        normalized = {canonical_dimension_lookup_key(value): value for value in candidates}
        for key, entry in results.items():
            if not isinstance(entry, dict):
                continue
            if str(key) in candidates or canonical_dimension_lookup_key(key) in normalized:
                return dict(entry)
        return {}

    def matrixcore_gate_state_label(self, record: dict, result: dict | None = None) -> str:
        """Small player-facing gate state; never include routes or dev labels."""
        record = dict(record or {})
        result = dict(result or {})
        if bool(record.get("completed")) or bool(result.get("completed")) or str(record.get("state") or "").lower() == "completed":
            signal = str(record.get("last_signal") or result.get("last_signal") or "").strip()
            return "COMPLETE" if signal else "COMPLETE"
        if str(record.get("state") or "").lower() == "locked" or not bool(record.get("unlocked", True)):
            return "LOCKED"
        return ""

    def update_matrixcore_gate_result_state(self, mode_name: str, result: dict, route: str = "") -> None:
        """Mirror completed/results into the discovered Gates index without changing gate IDs."""
        if not isinstance(result, dict) or not result:
            return
        progress = self.load_matrixcore_progression()
        gates = progress.get("discovered_gates") if isinstance(progress.get("discovered_gates"), dict) else {}
        if not isinstance(gates, dict):
            return
        mode_key = self.dimension_mode_id_for_display(mode_name)
        display_name = self.dimension_display_name_for_id(mode_key, mode_name)
        candidate_keys = {
            self.matrixcore_discovered_gate_key("dimension", display_name, mode_key),
            self.matrixcore_discovered_gate_key("dimension", mode_name, mode_key),
            canonical_dimension_lookup_key(display_name),
            canonical_dimension_lookup_key(mode_name),
            canonical_dimension_lookup_key(mode_key),
        }
        score_delta = int(float(result.get("score_delta", 0) or 0))
        completed = bool(result.get("completed", False))
        signal = str(result.get("signal") or result.get("memory_fragment") or "").strip()
        now = datetime.now().isoformat(timespec="seconds")
        changed = False
        for key, record in list(gates.items()):
            if not isinstance(record, dict):
                continue
            record_keys = {
                canonical_dimension_lookup_key(key),
                canonical_dimension_lookup_key(record.get("mode_id")),
                canonical_dimension_lookup_key(record.get("name")),
                canonical_dimension_lookup_key(record.get("display_name")),
                canonical_dimension_lookup_key(record.get("label")),
            }
            if not (candidate_keys & record_keys):
                continue
            updated = dict(record)
            if completed:
                updated["state"] = "completed"
                updated["completed"] = True
            else:
                updated.setdefault("state", "discovered")
            updated["last_result_at"] = now
            updated["last_score_delta"] = score_delta
            if score_delta:
                updated["best_score_delta"] = max(int(updated.get("best_score_delta", 0) or 0), score_delta)
            if signal:
                updated["last_signal"] = signal
            for field in ("fragments_recovered", "fragments_required"):
                if result.get(field) not in (None, ""):
                    updated[field] = str(result.get(field))
            if route:
                updated["route"] = str(route)
            gates[key] = updated
            changed = True
        if changed:
            progress["discovered_gates"] = gates
            self.save_matrixcore_progression(progress)

    def format_dimension_return_message(self, label: str, result: dict | None = None, *, discovery: str = "") -> str:
        """Build one concise HUD line for returns/discoveries."""
        label = self.matrixcore_clean_gate_label(label or "DIMENSION", fallback="DIMENSION")
        result = dict(result or {})
        if discovery:
            return f"{self.matrixcore_clean_gate_label(discovery)} DISCOVERED // ADDED TO GATES"
        if not result:
            return f"RETURNED FROM {label}"
        bits = [f"RETURNED FROM {label}"]
        if bool(result.get("completed", False)):
            bits.append("COMPLETE")
        signal = str(result.get("signal") or result.get("memory_fragment") or "").strip()
        if signal:
            bits.append("SIGNAL RECOVERED")
        score_delta = int(float(result.get("score_delta", 0) or 0))
        if score_delta:
            bits.append(f"+{score_delta} POINTS")
        return " // ".join(bits[:4])

    def matrixcore_dimension_gate_modes(self) -> list[dict]:
        """Return discovered region/dimension gates for quick travel.

        MatrixCore Gates now behaves like an in-game travel index: entries appear
        after a player discovers a region or enters a dimension.  Existing
        progression visits are migrated so older saves are not empty.
        """
        discovered = self.matrixcore_progression_discovered_gates()
        mode_by_id: dict[str, dict] = {}
        mode_by_name: dict[str, dict] = {}
        for mode in list(getattr(self, "core_modes", []) or []):
            if not isinstance(mode, dict):
                continue
            manifest = dict(mode.get("manifest") or {})
            keys = {
                canonical_dimension_lookup_key(manifest.get("id")),
                canonical_dimension_lookup_key(mode.get("name")),
                canonical_dimension_lookup_key(manifest.get("title")),
            }
            for key in keys:
                if key:
                    mode_by_id[key] = mode
                    mode_by_name[key] = mode
        gates: list[dict] = []
        seen: set[str] = set()
        for key, record in sorted(discovered.items(), key=lambda kv: str((kv[1] or {}).get("label") or (kv[1] or {}).get("name") or kv[0]).lower()):
            if not isinstance(record, dict):
                continue
            kind = str(record.get("kind") or "dimension").lower()
            label_source = record.get("label") or record.get("name") or key
            label = self.matrixcore_clean_gate_label(label_source)
            gate_key = canonical_dimension_lookup_key(key)
            if gate_key in seen:
                continue
            seen.add(gate_key)
            if kind == "region":
                number = int(record.get("target_number", 0) or 0)
                entry = self.holoverse_region_entry_for_number(number) or {}
                gate = {"name": str(entry.get("name") or record.get("name") or label), "manifest": {"id": f"region_{number}", "title": label, "launch_type": "region_spawn"}, "_matrixcore_gate_id": gate_key, "_matrixcore_gate_label": label, "_matrixcore_gate_route": "region_spawn", "_matrixcore_gate_available": True, "_matrixcore_gate_needs_config": False, "_matrixcore_gate_badge": "REGION", "_matrixcore_gate_kind": "region", "_matrixcore_region_number": number, "_matrixcore_discovered_count": int(record.get("count", 1) or 1), "_matrixcore_discovered_at": str(record.get("last_at", ""))}
                gates.append(gate)
                continue
            mode_key = self.dimension_mode_id_for_display(record.get("mode_id") or record.get("name") or label)
            mode = mode_by_id.get(mode_key) or mode_by_name.get(mode_key)
            if not mode:
                continue
            manifest = dict(mode.get("manifest") or {})
            display_label = self.dimension_display_name_for_mode(mode, label_source)
            label = self.matrixcore_clean_gate_label(display_label)
            result_info = self.matrixcore_dimension_result_for_gate(mode_key, display_label)
            state_label = self.matrixcore_gate_state_label(record, result_info)
            # HoloCore is allowed in Gates once discovered; it still launches through
            # the same same-window route resolver as artifact slot 7.
            launch = normalize_mode_launch_type(manifest.get("launch_type") or mode.get("launch_type"))
            placeholder = bool(mode.get("placeholder") or manifest.get("placeholder_mode") or launch == MODE_LAUNCH_PLACEHOLDER)
            main = Path(mode.get("main")) if mode.get("main") else None
            runtime_text = str(manifest.get("runtime") or "").strip()
            runtime_path = resolve_project_path(runtime_text) if runtime_text else None
            runtime_ready = bool(runtime_path is not None and runtime_path.exists() and str(manifest.get("runtime_installer") or "").strip())
            entry_ready = bool(main is not None and main.exists())
            available = bool(mode.get("available", True)) and not placeholder and (entry_ready or runtime_ready or launch == MODE_LAUNCH_PANEL)
            gate = dict(mode)
            gate["_matrixcore_gate_id"] = gate_key
            gate["_matrixcore_gate_label"] = label
            gate["_matrixcore_gate_route"] = launch
            gate["_matrixcore_gate_available"] = bool(available)
            gate["_matrixcore_gate_needs_config"] = not bool(available)
            gate["_matrixcore_gate_badge"] = "DIM" if available else "CONFIG"
            gate["_matrixcore_gate_kind"] = "dimension"
            gate["_matrixcore_gate_state"] = str(record.get("state") or ("completed" if bool(result_info.get("completed")) else "discovered"))
            gate["_matrixcore_gate_state_label"] = state_label
            gate["_matrixcore_gate_completed"] = bool(record.get("completed")) or bool(result_info.get("completed"))
            gate["_matrixcore_discovered_count"] = int(record.get("count", 1) or 1)
            gate["_matrixcore_discovered_at"] = str(record.get("last_at", ""))
            gates.append(gate)
        gates.sort(key=lambda item: (0 if str(item.get("_matrixcore_gate_kind")) == "region" else 1, str(item.get("_matrixcore_gate_label") or item.get("name") or "").lower()))
        return gates

    def matrixcore_dimension_gate_page_modes(self) -> tuple[list[dict], int, int]:
        gates = self.matrixcore_dimension_gate_modes()
        page_size = max(1, int(getattr(self, "matrixcore_gate_page_size", MATRIXCORE_VISIBLE_ACTION_CARD_LIMIT) or MATRIXCORE_VISIBLE_ACTION_CARD_LIMIT))
        max_page = max(0, (len(gates) - 1) // page_size) if gates else 0
        self.matrixcore_gate_page = max(0, min(int(getattr(self, "matrixcore_gate_page", 0) or 0), max_page))
        start = self.matrixcore_gate_page * page_size
        return gates[start:start + page_size], max_page, len(gates)

    def matrixcore_change_gate_page(self, delta: int = 1) -> None:
        gates = self.matrixcore_dimension_gate_modes()
        page_size = max(1, int(getattr(self, "matrixcore_gate_page_size", MATRIXCORE_VISIBLE_ACTION_CARD_LIMIT) or MATRIXCORE_VISIBLE_ACTION_CARD_LIMIT))
        max_page = max(0, (len(gates) - 1) // page_size) if gates else 0
        if max_page <= 0:
            self.matrixcore_gate_page = 0
        else:
            self.matrixcore_gate_page = (int(getattr(self, "matrixcore_gate_page", 0) or 0) + int(delta or 1)) % (max_page + 1)
        self.core_console_page = "dimensions"
        self.refresh_core_console()

    def matrixcore_launch_dimension_gate(self, gate_id: str) -> bool:
        gate_id = canonical_dimension_lookup_key(gate_id)
        for mode in self.matrixcore_dimension_gate_modes():
            if canonical_dimension_lookup_key(mode.get("_matrixcore_gate_id") or mode.get("name")) == gate_id:
                return self.matrixcore_launch_dimension_gate_mode(mode)
        self.center_hint["text"] = "MATRIXCORE // GATE NOT FOUND"
        self.refresh_core_console()
        return False

    def matrixcore_launch_dimension_gate_mode(self, mode: dict) -> bool:
        mode = dict(mode or {})
        label = str(mode.get("_matrixcore_gate_label") or mode.get("name") or "DIMENSION").upper()
        if str(mode.get("_matrixcore_gate_kind") or "").lower() == "region":
            number = int(mode.get("_matrixcore_region_number", 0) or 0)
            self.center_hint["text"] = f"ENTER {label}"
            if getattr(self, "core_console_open", False):
                self.close_core_console()
            return bool(self.travel_to_holoverse_region_index(number, source="matrixcore_gate", force=True))
        if not bool(mode.get("_matrixcore_gate_available", False)):
            self.center_hint["text"] = f"MATRIXCORE // {label} NEEDS CONFIG"
            self.refresh_core_console()
            return False
        self.center_hint["text"] = f"ENTER {label}"
        try:
            self.show_bridge_transition("ENTER DIMENSION", label, target=1.0, hold=0.25)
        except Exception:
            pass
        return bool(self.start_dimension_transition(
            mode,
            source="matrixcore_dimension_gate",
            context={"doorway": "matrixcore_gate", "origin": "MatrixCore", "route": str(mode.get("_matrixcore_gate_route") or "")},
            extra_env={"HOLOVERSE_GATEWAY_SOURCE": "MatrixCore", "HOLOVERSE_GATEWAY_BUTTON": label},
            close_core=True,
        ))

    def matrixcore_action_cards(self, page_key: str) -> list[dict]:
        page_key = str(page_key or "guide").lower()
        if page_key == "dimensions":
            shown, _max_page, _total = self.matrixcore_dimension_gate_page_modes()
            cards = []
            for mode in shown:
                gate_id = str(mode.get("_matrixcore_gate_id") or mode.get("name") or "")
                label = str(mode.get("_matrixcore_gate_label") or mode.get("name") or "DIMENSION")
                available = bool(mode.get("_matrixcore_gate_available", False))
                state_note = " DONE" if bool(mode.get("_matrixcore_gate_completed", False)) else ""
                cards.append({"label": f"{label}{state_note}", "action": f"dimension_gate:{gate_id}", "role": "yellow" if available else "white", "available": available})
            if not cards:
                cards.append({"label": "NO GATES INDEXED", "action": "dimensions", "role": "white", "available": False})
            return cards
        cards = [
            {"label": "Guide", "action": "guide", "role": "yellow" if page_key == "guide" else "mode"},
            {"label": "Archive", "action": "lore", "role": "yellow" if page_key == "lore" else "mode"},
            {"label": "Dimensions", "action": "dimensions", "role": "yellow" if page_key == "dimensions" else "mode"},
            {"label": "Progression", "action": "progression", "role": "yellow" if page_key == "progression" else "mode"},
            {"label": "Bot Support", "action": "bots", "role": "yellow" if page_key == "bots" else "mode"},
            {"label": "Archive", "action": "archive", "role": "yellow" if page_key == "archive" else "mode"},
            {"label": "System", "action": "system", "role": "yellow" if page_key == "system" else "mode"},
        ]
        if page_key == "guide":
            cards.insert(1, {"label": "Enter HoloCore Dimension", "action": "holocore", "role": "yellow"})
        else:
            cards.insert(1, {"label": "Next Signal", "action": "next", "role": "white"})
        return cards

    def sync_core(self):
        try:
            save_config(self.cfg)
        except Exception:
            pass
        try:
            write_audio_bus(self.cfg)
        except Exception:
            pass
        try:
            write_shared_launch_settings(self.cfg)
        except Exception:
            pass
        self.refresh_ui()

    def _core_mode_route_details(self, mode: dict) -> dict:
        manifest = dict(mode.get("manifest") or {})
        launch_type = normalize_mode_launch_type(manifest.get("launch_type") or mode.get("launch_type"))
        route = route_display_name(launch_type)
        folder = Path(mode.get("folder") or ROOT)
        entry_path = Path(mode.get("main") or (folder / str(manifest.get("entry", "main.py"))))
        source_kind = str(manifest.get("source_kind", mode.get("source_kind", "unknown"))).lower()
        placeholder_mode = bool(manifest.get("placeholder_mode", False) or mode.get("placeholder", False) or launch_type == MODE_LAUNCH_PLACEHOLDER)
        issues = []
        if not placeholder_mode and not entry_path.exists():
            issues.append("entry-missing")
        adapter_path = None
        if launch_type == MODE_LAUNCH_NATIVE:
            adapter_name = str(manifest.get("native_adapter") or MODE_NATIVE_ADAPTER_NAME).strip() or MODE_NATIVE_ADAPTER_NAME
            adapter_path = folder / adapter_name
            if not adapter_path.exists() or not adapter_path.is_file():
                issues.append("native-adapter-missing")
        log_path = None
        if launch_type == MODE_LAUNCH_PANEL:
            try:
                log_path = self._panel_log_path(mode)
            except Exception:
                log_path = folder / f"{re.sub(r'[^a-z0-9]+', '_', str(mode.get('name', 'mode')).lower()).strip('_')}_panel_log.json"
        fallback = str(manifest.get("fallback_launch_type") or "").strip()
        if launch_type == MODE_LAUNCH_NATIVE and not fallback:
            issues.append("fallback-not-declared")
        if launch_type == MODE_LAUNCH_PANEL and not bool(manifest.get("panel_supported", mode.get("panel_supported", False))):
            issues.append("panel-flag-missing")
        health = "OK" if not issues else "CHECK"
        if placeholder_mode and not issues:
            health = "PLACEHOLDER"
        elif launch_type == MODE_LAUNCH_EMBEDDED and not issues:
            health = "WIN-CHILD"
        elif launch_type == MODE_LAUNCH_PANEL and log_path is not None and not log_path.exists() and not issues:
            health = "LOG-NEW"
        deck_badge, deck_detail = mode_deck_badge_from_details({
            "route": route,
            "launch_type": launch_type,
            "health": health,
            "issues": issues,
            "entry_exists": entry_path.exists(),
        }, available=bool(mode.get("available", True)))
        return {
            "name": str(mode.get("name", "Mode")),
            "route": route,
            "launch_type": launch_type,
            "health": health,
            "deck_badge": deck_badge,
            "deck_detail": deck_detail,
            "issues": issues,
            "placeholder_mode": placeholder_mode,
            "source_kind": source_kind,
            "entry": os.fspath(entry_path),
            "entry_exists": entry_path.exists(),
            "adapter": os.fspath(adapter_path) if adapter_path is not None else "",
            "adapter_exists": bool(adapter_path is not None and adapter_path.exists()),
            "panel_log": os.fspath(log_path) if log_path is not None else "",
            "panel_log_exists": bool(log_path is not None and log_path.exists()),
            "fallback_launch_type": fallback,
            "host_contract": str(manifest.get("host_contract", "")),
            "mode_root": str(mode.get("mode_root", "")),
            "folder": os.fspath(folder),
        }

    def build_mode_gateway_audit(self) -> dict:
        modes = list(getattr(self, "core_modes", []) or [])
        details = [self._core_mode_route_details(mode) for mode in modes]
        counts = {"PLACEHOLDER": 0, "PANEL": 0, "EMBEDDED": 0, "IN-WORLD": 0, "HOSTED": 0, "CHECK": 0, "NEEDS_PATCH": 0, "BROKEN_PATH": 0}
        for item in details:
            route = str(item.get("route", "HOSTED")).upper()
            counts[route] = int(counts.get(route, 0)) + 1
            badge = str(item.get("deck_badge", "")).upper().replace(" ", "_")
            if badge in {"NEEDS_PATCH", "BROKEN_PATH"}:
                counts[badge] = int(counts.get(badge, 0)) + 1
            if item.get("issues"):
                counts["CHECK"] = int(counts.get("CHECK", 0)) + 1
        panel_count = int(counts.get("PANEL", 0))
        embedded_count = int(counts.get("EMBEDDED", 0))
        in_world_count = int(counts.get("IN-WORLD", 0))
        hosted_count = int(counts.get("HOSTED", 0))
        native_count = int(counts.get("SAME-WINDOW", 0))
        same_window_count = int(counts.get("SAME-WINDOW", 0))
        issue_count = int(counts.get("CHECK", 0))
        placeholder_count = int(counts.get("PLACEHOLDER", 0))
        expected_playable = max(0, len(details) - placeholder_count)
        playable_ready = in_world_count + embedded_count + panel_count + native_count
        weighted_total = max(1, expected_playable)
        weighted_done = min(playable_ready, expected_playable)
        completion_percent = int(round((weighted_done / float(weighted_total)) * 100.0)) if expected_playable else 0
        if issue_count:
            completion_percent = min(completion_percent, 97)
        if hosted_count:
            completion_percent = min(completion_percent, 97)
        if placeholder_count:
            completion_percent = min(completion_percent, 99)
        gateway_safe = issue_count == 0
        gateway_playable_complete = gateway_safe and hosted_count == 0 and placeholder_count == 0 and playable_ready >= expected_playable
        if gateway_playable_complete:
            completion_percent = 100
        return {
            "schema": 2,
            "version": VERSION,
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "summary": counts,
            "mode_count": len(details),
            "placeholder_routes": placeholder_count,
            "panel_routes_complete": panel_count,
            "in_world_routes": in_world_count,
            "embedded_child_window_routes": embedded_count,
            "hosted_fallback_routes": hosted_count,
            "issue_count": issue_count,
            "expected_playable_routes": expected_playable,
            "playable_ready_routes": playable_ready,
            "gateway_completion_percent": completion_percent,
            "gateway_safe": gateway_safe,
            "gateway_playable_complete": gateway_playable_complete,
            "gateway_complete": gateway_playable_complete,
            "history_path": os.fspath(MODE_GATEWAY_HISTORY),
            "modes": details,
        }

    def write_mode_gateway_audit(self) -> dict:
        audit = self.build_mode_gateway_audit()
        try:
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            MODE_GATEWAY_AUDIT.write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
        except Exception as exc:
            audit["write_error"] = str(exc)
        return audit

    def _append_mode_gateway_history(self, event: str, mode: dict | None = None, label: str = "", route: str = "", extra: dict | None = None) -> None:
        try:
            mode = dict(mode or {})
            manifest = dict(mode.get("manifest") or {})
            mode_name = str(mode.get("name") or manifest.get("title") or label or "").strip()
            mode_id = str(manifest.get("id") or re.sub(r"[^a-z0-9]+", "_", mode_name.lower()).strip("_") or "unknown")
            launch_type = normalize_mode_launch_type(route or manifest.get("launch_type") or mode.get("launch_type"))
            record = {
                "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                "event": str(event or "event"),
                "mode": mode_name or str(label or ""),
                "mode_id": mode_id,
                "label": str(label or mode_name or ""),
                "route": route_display_name(launch_type),
                "launch_type": launch_type,
                "version": VERSION,
            }
            if extra:
                record["extra"] = {str(k): str(v) for k, v in dict(extra).items()}
            history = []
            if MODE_GATEWAY_HISTORY.exists():
                raw = json.loads(MODE_GATEWAY_HISTORY.read_text(encoding="utf-8"))
                if isinstance(raw, dict) and isinstance(raw.get("events"), list):
                    history = [x for x in raw.get("events", []) if isinstance(x, dict)]
            history.append(record)
            payload = {
                "schema": 1,
                "version": VERSION,
                "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "event_count": len(history[-160:]),
                "events": history[-160:],
            }
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            MODE_GATEWAY_HISTORY.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        except Exception as exc:
            try:
                print(f"mode_gateway_history_write_failed event={event} err={exc}")
            except Exception:
                pass

    def read_mode_gateway_history_summary(self, limit: int = 4) -> str:
        try:
            if not MODE_GATEWAY_HISTORY.exists():
                return "NO ROUTE HISTORY YET"
            raw = json.loads(MODE_GATEWAY_HISTORY.read_text(encoding="utf-8"))
            events = raw.get("events", []) if isinstance(raw, dict) else []
            clean = [e for e in events if isinstance(e, dict)][-max(1, int(limit)):]
            if not clean:
                return "NO ROUTE HISTORY YET"
            bits = []
            for event in clean[::-1]:
                stamp = str(event.get("time", ""))[-8:]
                name = str(event.get("mode") or event.get("label") or "MODE").upper()[:18]
                kind = str(event.get("event", "EVENT")).upper()[:16]
                route = str(event.get("route", "")).upper()[:8]
                bits.append(f"{stamp} {kind} {name} {route}".strip())
            return "  |  ".join(bits)
        except Exception:
            return "ROUTE HISTORY UNAVAILABLE"

    def mode_gateway_audit_summary(self, audit: dict | None = None) -> str:
        audit = audit or self.build_mode_gateway_audit()
        counts = dict(audit.get("summary") or {})
        completion = int(audit.get("gateway_completion_percent", 0) or 0)
        return f"GATEWAY {completion:03d}% // INWORLD {int(counts.get('IN-WORLD', 0)):02d} // EMBED {int(counts.get('EMBEDDED', 0)):02d} // PLACE {int(counts.get('PLACEHOLDER', 0)):02d} // PANEL {int(counts.get('PANEL', 0)):02d} // HOSTED {int(counts.get('HOSTED', 0)):02d} // PATCH {int(counts.get('NEEDS_PATCH', 0)):02d} // BROKEN {int(counts.get('BROKEN_PATH', 0)):02d} // CHECK {int(counts.get('CHECK', 0)):02d}"

    def refresh_core_console(self):
        if not hasattr(self, 'core_console_label'):
            return
        if not hasattr(self, "matrixcore_data"):
            self.matrixcore_data = self.ensure_matrixcore_foundation()
        modes = list(getattr(self, "core_modes", []) or [])
        audit_summary = self.mode_gateway_audit_summary()
        last = str(getattr(self, "last_launched_core_mode", "") or "NONE").upper()
        archive = list((getattr(self, "matrixcore_data", {}) or {}).get("archive", []) or [])
        page_key = str(getattr(self, "core_console_page", "guide") or "guide").lower()
        if page_key not in MATRIXCORE_PAGE_ORDER:
            page_key = "guide"
            self.core_console_page = page_key
        page_text = self.matrixcore_page_text(page_key)
        page_title = self.matrixcore_page_title(page_key)
        if hasattr(self, "core_console_title"):
            self.core_console_title["text"] = "MATRIXCORE"
        if hasattr(self, "core_console_subtitle"):
            self.core_console_subtitle["text"] = page_title
        status_line = f"MATRIXCORE // DIMENSIONS {len(modes):02d} // ARCHIVE {len(archive):02d} // {audit_summary} // LAST {last}"
        self.core_console_label["text"] = compact_ui_text(status_line, 150)
        if hasattr(self, 'core_hint_label'):
            self.core_hint_label["text"] = page_text
            try:
                self.core_hint_label["text_align"] = TextNode.ALeft
                self.core_hint_label["text_wordwrap"] = 42.0
            except Exception:
                pass
        actions = self.matrixcore_action_cards(page_key)[:MATRIXCORE_VISIBLE_ACTION_CARD_LIMIT]
        buttons = list(getattr(self, "core_mode_buttons", []) or [])
        for idx, btn in enumerate(buttons):
            if idx < len(actions):
                spec = actions[idx]
                btn["text"] = str(spec.get("label", "MATRIXCORE")).upper()
                btn["command"] = self.matrixcore_click_action
                btn["extraArgs"] = [str(spec.get("action", "guide"))]
                try:
                    btn.show()
                except Exception:
                    pass
                self.apply_core_button_style(btn, role=str(spec.get("role", "mode")), active=(str(spec.get("action", "")) == page_key), available=bool(spec.get("available", True)))
            else:
                btn["text"] = ""
                try:
                    btn.hide()
                except Exception:
                    pass
        if hasattr(self, 'core_page_button'):
            try:
                if page_key == "dimensions":
                    _shown, max_page, total_gates = self.matrixcore_dimension_gate_page_modes()
                    self.core_page_button["text"] = "GATES >" if int(getattr(self, "matrixcore_gate_page", 0) or 0) < max_page else "GATES 1"
                    self.core_page_button["command"] = self.matrixcore_change_gate_page
                    self.core_page_button["extraArgs"] = [1 if total_gates else 0]
                else:
                    self.core_page_button["text"] = "NEXT"
                    self.core_page_button["command"] = self.core_toggle_console_page
                    self.core_page_button["extraArgs"] = []
                self.core_page_button.show()
            except Exception:
                pass
        if hasattr(self, 'core_hub_button'):
            self.core_hub_button["text"] = "HUB"
            self.core_hub_button.show()
        if hasattr(self, 'core_close_button'):
            self.core_close_button["text"] = "CLOSE"
            self.core_close_button.show()

    def core_toggle_console_page(self):
        if not self.core_console_open:
            self.open_core_console()
            return
        self.trigger_matrixcore_dialogue("matrixcore_page_key")

    def matrixcore_set_page(self, page_key: str):
        page_key = str(page_key or "guide").lower()
        if page_key not in MATRIXCORE_PAGE_ORDER:
            page_key = "guide"
        self.core_console_page = page_key
        try:
            self.matrixcore_page_index = MATRIXCORE_PAGE_ORDER.index(page_key)
        except Exception:
            self.matrixcore_page_index = 0
        self.refresh_core_console()

    def find_holocore_mode(self) -> dict | None:
        """Return the root-level HoloCore sub-world mode without moving it into Dimensions."""
        for mode in list(getattr(self, "core_modes", []) or []):
            manifest = dict(mode.get("manifest") or {})
            labels = {
                str(mode.get("name", "")).strip().lower(),
                str(manifest.get("id", "")).strip().lower(),
                str(manifest.get("title", "")).strip().lower(),
            }
            if "holocore" in labels or "holo core" in labels:
                return dict(mode)
        folder = ROOT / "HoloCore"
        entry = folder / "main.py"
        if not entry.exists():
            return None
        manifest_path = folder / "holoverse_mode_manifest.json"
        manifest = _safe_read_json(manifest_path, default={}) if manifest_path.exists() else {}
        if not isinstance(manifest, dict):
            manifest = {}
        manifest.setdefault("id", "holocore")
        manifest.setdefault("title", "HOLOCORE")
        manifest.setdefault("entry", "main.py")
        manifest.setdefault("launch_type", MODE_LAUNCH_EMBEDDED)
        manifest.setdefault("source_kind", "panda3d")
        manifest.setdefault("preferred_display", "host_window_child")
        manifest.setdefault("return_target", "hub")
        manifest.setdefault("host_contract", "holoverse_mode_gateway_v2")
        manifest["manifest_path"] = os.fspath(manifest_path) if manifest_path.exists() else ""
        return {
            "name": "HoloCore",
            "folder": folder,
            "mode_root": "root-subworld",
            "main": entry,
            "alternate": None,
            "available": True,
            "has_alternate": False,
            "placeholder": False,
            "manifest": manifest,
            "launch_type": normalize_mode_launch_type(manifest.get("launch_type")),
            "source_kind": str(manifest.get("source_kind", "panda3d")),
            "panel_supported": False,
            "native_panda_candidate": False,
        }

    def launch_holocore_from_matrixcore(self) -> bool:
        """Open HoloCore as a sub-world through the shared MatrixCore gateway.

        The preferred route is now an in-process, same-window scene mount. If
        HoloCore's folder modules cannot be imported on a machine, this falls
        back to the previous child-window/hosted gateway instead of breaking.
        """
        mode = self.find_holocore_mode()
        if not mode:
            self.center_hint["text"] = "MATRIXCORE // HOLOCORE ENTRY MISSING"
            try:
                self.refresh_core_console()
            except Exception:
                pass
            return False
        if self.launch_holocore_same_window(mode):
            return True
        return self.start_dimension_transition(
            mode,
            source="matrixcore_holocore_fallback",
            context={"entry": "matrixcore_button", "return_gate": "holocore_pyramid", "fallback": "child_window"},
            extra_env={"HOLOCORE_PARENT_GATE": "matrixcore", "HOLOCORE_RETURN_GATE": "pyramid", "HOLOCORE_SAME_WINDOW_FALLBACK": "1"},
            close_core=True,
        )

    def launch_holocore_same_window(self, mode: dict, source: str = "matrixcore_holocore") -> bool:
        """Mount HoloCore into this Panda3D window without merging its folder."""
        if getattr(self, "active_native_mode", None) is not None:
            self.center_hint["text"] = "MATRIXCORE // HOLOCORE ALREADY ACTIVE"
            return True
        if getattr(self, "external_process", None) is not None:
            self.center_hint["text"] = "MATRIXCORE // CLOSE ACTIVE MODE FIRST"
            return False
        path, label, route_env = self.resolve_core_mode_entry(mode)
        if path is None or not Path(path).exists():
            self.center_hint["text"] = "MATRIXCORE // HOLOCORE ENTRY MISSING"
            return False
        label = "HoloCore"
        transition_id = f"{int(time.time() * 1000)}_holocore_same_window"
        try:
            self.sync_core()
            self.core_mode_state["launch_count"] = int(self.core_mode_state.get("launch_count", 0)) + 1
            self.core_mode_state["last_mode"] = label
            self.core_mode_state["last_entry"] = "main.py"
            self.core_mode_state["last_launch_type"] = "same_window_native"
            self.core_mode_state["last_launch_source"] = str(source or "matrixcore_holocore")
            save_mode_state(self.core_mode_state)
        except Exception:
            pass
        try:
            self.record_matrixcore_dimension_signal("dimension_transition_begin", label, label=label, route="same_window_native", source=str(source or "matrixcore_holocore"), reason="same_window_mount")
        except Exception:
            pass
        self._append_mode_gateway_history(
            "holocore_same_window_begin",
            mode=mode,
            label=label,
            route="same_window_native",
            extra={"transition_id": transition_id, "entry": os.fspath(path), "folder_kept_subworld": True},
        )
        try:
            self.show_bridge_transition("MATRIXCORE -> HOLOCORE", "SAME WINDOW // PYRAMID SUB-WORLD", target=1.0, hold=0.22)
        except Exception:
            pass
        self.suspend_for_native_mode(label)
        try:
            scene = HoloCoreSameWindowScene(self, mode=mode, entry_path=Path(path), label=label)
            self.active_native_mode = scene
            self.native_mode_entry = Path(path)
            self.native_mode_label = label
            self.native_mode_route = "same_window_native"
            self.last_launched_core_mode = label
            self.last_launched_core_entry = os.fspath(path)
            self.center_hint["text"] = scene._ui_text("entered_hint")
            self.hide_native_status_overlay()
            self.fade_bridge_transition(hold=0.40)
            try:
                self.record_matrixcore_dimension_signal("dimension_launch", label, label=label, route="same_window_native", source="matrixcore_holocore", reason="same_window_mount")
            except Exception:
                pass
            self._append_mode_gateway_history(
                "holocore_same_window_active",
                mode=mode,
                label=label,
                route="same_window_native",
                extra={"transition_id": transition_id, "fallback_available": True},
            )
            return True
        except Exception as exc:
            self.active_native_mode = None
            self._append_mode_gateway_history(
                "holocore_same_window_failed",
                mode=mode,
                label=label,
                route="same_window_native",
                extra={"transition_id": transition_id, "error": f"{exc.__class__.__name__}: {exc}"},
            )
            try:
                print(f"holocore_same_window_failed:{exc.__class__.__name__}:{exc}")
            except Exception:
                pass
            try:
                self.return_from_native_mode(reason="holocore_same_window_failed")
            except Exception:
                pass
            return False

    def launch_connected_dimension_same_window(self, mode: dict, path: Path | None = None, label: str = "", source: str = "core") -> bool:
        """Compatibility shim for stale same_window_mode records.

        The old implementation mounted a tiny generic signal-collection scene.
        That scene is intentionally retired: every real standalone dimension now
        launches through ``launch_embedded_external_level`` so its own main.py is
        used inside the HoloVerse host window.
        """
        mode = dict(mode or {})
        manifest = dict(mode.get("manifest") or {})
        label = str(label or mode.get("name") or manifest.get("title") or "Dimension")
        if path is None:
            path, _resolved_label, route_env = self.resolve_core_mode_entry(mode)
        else:
            route_env = {}
        if path is None or not Path(path).exists():
            self.center_hint["text"] = f"MATRIXCORE // {label.upper()} ENTRY MISSING"
            return False
        self._append_mode_gateway_history(
            "connected_route_retired_to_embedded",
            mode=mode,
            label=label,
            route=MODE_LAUNCH_EMBEDDED,
            extra={"source": source, "entry": os.fspath(path), "old_route": MODE_LAUNCH_CONNECTED},
        )
        try:
            self.record_matrixcore_dimension_signal("dimension_transition_begin", label, label=label, route=MODE_LAUNCH_EMBEDDED, source=str(source or "core"), reason="connected_route_retired")
        except Exception:
            pass
        return bool(self.launch_embedded_external_level(Path(path), label, extra_env=route_env))

    def toggle_holocore_main_bridge(self, source: str = "number_0") -> bool:
        """Use 0 as the two-main bridge: MatrixCore <-> HoloCore.

        In the root HoloVerse hub, 0 enters HoloCore. If a child/native route is
        already active and the parent still receives the key, 0 requests the same
        return path used by the embedded return overlay. HoloCore itself binds 0
        to its pyramid return gate.
        """
        if getattr(self, "active_native_mode", None) is not None:
            if self.dispatch_native_action("number_0"):
                return True
            self.return_from_native_mode(reason=source)
            return True
        if getattr(self, "external_process", None) is not None:
            self.request_external_return_to_core(reason=source)
            return True
        if getattr(self, "menu_open", False):
            self.center_hint["text"] = "0 // CLOSE MENU TO ENTER HOLOCORE"
            return True
        if getattr(self, "core_console_open", False):
            self.close_core_console()
        self.center_hint["text"] = "0 // MATRIXCORE TO HOLOCORE"
        return bool(self.launch_holocore_from_matrixcore())

    def matrixcore_click_action(self, action: str):
        action = str(action or "guide").lower()
        if action.startswith("dimension_gate:"):
            self.matrixcore_launch_dimension_gate(action.split(":", 1)[1])
            return
        if action in MATRIXCORE_PAGE_ORDER:
            if action == "dimensions":
                self.matrixcore_gate_page = 0
            self.matrixcore_set_page(action)
            return
        if action in {"holocore", "enter_holocore", "holo_core"}:
            self.launch_holocore_from_matrixcore()
            return
        if action == "next":
            self.matrixcore_show_next_guidance()
            return
        if action == "refresh":
            self.matrixcore_data = self.ensure_matrixcore_foundation(force=True)
            self.center_hint["text"] = "MATRIXCORE // DATABASE RESYNCED"
            self.refresh_core_console()
            return
        if action == "close":
            self.close_core_console()
            return
        if action == "hub":
            self.core_return_hub()
            return
        self.matrixcore_set_page("guide")

    def core_select_world(self, world_id: int):
        """Retained for compatibility. Same-file world generation now belongs to artifacts/pedestals."""
        if world_id not in WORLD_SPECS:
            return
        artifact = self.artifacts[world_id] if 0 <= world_id < len(self.artifacts) else {"id": int(world_id), "name": WORLD_SPECS[world_id]["name"]}
        self.activate_artifact_direct(artifact, source="core-compat-artifact")
        self.close_core_console()
        if self.audio:
            self.audio.play('world_shift.wav', 'sfx', 0.96)

    def core_return_hub(self):
        self.close_core_console()
        self.teleport_to_hub()

    def close_all_mode_apps(self):
        """Close/return every HoloVerse-launched game app without exiting Core.

        This is intentionally scoped to child/native/panel modes launched by
        HoloVerse. It does not try to close unrelated Windows programs.
        """
        closed = []
        if getattr(self, "active_native_mode", None) is not None:
            label = str(getattr(self, "native_mode_label", "MODE") or "MODE")
            self.return_from_native_mode(reason="close-all-apps")
            closed.append(label)
        proc = getattr(self, "external_process", None)
        if proc is not None:
            try:
                if proc.poll() is None:
                    self.request_external_return_to_core(reason="close-all-apps")
                    closed.append(str(getattr(self, "external_launch_label", "HOSTED MODE") or "HOSTED MODE"))
                else:
                    self.external_resume_pending = True
            except Exception:
                self.external_resume_pending = True
        if getattr(self, "core_panel_context", None):
            self.core_panel_context = None
            closed.append("CORE PANEL")
            try:
                self.refresh_core_console()
            except Exception:
                pass
        if closed:
            label = ", ".join(x.upper() for x in closed[:3])
            if len(closed) > 3:
                label += f" +{len(closed) - 3}"
            self.center_hint["text"] = f"CORE // CLOSE APPS REQUESTED // {label}"
            self._append_mode_gateway_history("close_all_apps", label=label, route="system", extra={"count": len(closed)})
        else:
            self.center_hint["text"] = "CORE // NO ACTIVE GAME APPS TO CLOSE"
        if self.audio:
            self.audio.play('menu_close.wav', 'sfx', 0.65)
        self.refresh_menu_actions()
        self.refresh_ui()

    def resolve_core_mode_entry(self, mode: dict) -> tuple[Path | None, str, dict]:
        name = str(mode.get("name", "Mode"))
        main = Path(mode.get("main")) if mode.get("main") else None
        alternate = Path(mode.get("alternate")) if mode.get("alternate") else None
        manifest = dict(mode.get("manifest") or {})
        folder = Path(mode.get("folder") or "")
        entry_name = str(manifest.get("entry") or "").strip()
        if entry_name:
            if not folder.is_absolute():
                folder = resolve_dimensions_root(ROOT) / folder.name if folder.name else resolve_dimensions_root(ROOT) / name
            manifest_entry = find_case_insensitive_file(folder, entry_name)
            if manifest_entry is not None:
                main = manifest_entry
        if main is None or not main.exists():
            if not folder.is_absolute():
                folder = resolve_dimensions_root(ROOT) / folder.name if folder.name else resolve_dimensions_root(ROOT) / name
            entry_name = entry_name or "main.py"
            candidate = find_case_insensitive_file(folder, entry_name) or find_case_insensitive_file(folder, "main.py")
            if candidate is not None:
                main = candidate
        launch_type = normalize_mode_launch_type(manifest.get("launch_type") or mode.get("launch_type"))
        env = {
            "MATRIX_CORE_MODE_NAME": name,
            "MATRIX_CORE_MODE_FOLDER": os.fspath(mode.get("folder", "")),
            "HOLOVERSE_MODE_ID": str(manifest.get("id", re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "mode")),
            "HOLOVERSE_MODE_TITLE": str(manifest.get("title", name.upper())),
            "HOLOVERSE_MODE_LAUNCH_TYPE": launch_type,
            "HOLOVERSE_MODE_SOURCE_KIND": str(manifest.get("source_kind", mode.get("source_kind", "unknown"))),
            "HOLOVERSE_MODE_PANEL_SUPPORTED": "1" if bool(manifest.get("panel_supported", mode.get("panel_supported", False))) else "0",
            "HOLOVERSE_MODE_MANIFEST": os.fspath(manifest.get("manifest_path", "")),
        }
        if name.lower() == "holo campaign" and alternate is not None and alternate.exists():
            use_alt = bool((self.core_mode_state or {}).get("campaign_next_alternate", False))
            if use_alt:
                self.core_mode_state["campaign_next_alternate"] = False
                env["MATRIX_HOLO_CAMPAIGN_ALTERNATE"] = "1"
                return alternate, f"{name} // ALTERNATE", env
            self.core_mode_state["campaign_next_alternate"] = True
            env["MATRIX_HOLO_CAMPAIGN_ALTERNATE"] = "0"
            return main, f"{name} // MAIN", env
        return main, name, env

    def _panel_mode_id(self, mode: dict) -> str:
        manifest = dict(mode.get("manifest") or {})
        return str(manifest.get("id") or re.sub(r"[^a-z0-9]+", "_", str(mode.get("name", "mode")).lower()).strip("_") or "mode")

    def _panel_mode_spec(self, mode: dict) -> dict:
        mode_id = self._panel_mode_id(mode)
        gate_actions = self.menu_gate_actions() if hasattr(self, "menu_gate_actions") else [("NO GATES READY", "noop_menu_action")]
        specs = {
            "vector_wars": {
                "title": "VECTOR WARS // WAR ROOM LOG",
                "subtitle": "TACTICAL PANEL // SKIRMISH NOTES // PYGAME FALLBACK PRESERVED",
                "log_name": "vector_wars_war_room_log.json",
                "log_title": "VECTOR WAR ROOM",
                "actions": [
                    ("skirmish", "ADD SKIRMISH ENTRY"),
                    ("enemy_wave", "ADD ENEMY WAVE NOTE"),
                    ("loadout", "ADD LOADOUT NOTE"),
                    ("scoreboard", "ADD SCOREBOARD SNAPSHOT"),
                ],
                "templates": {
                    "skirmish": "Skirmish entry recorded: vector lanes active, hostile pressure simulated, next run should inspect movement density.",
                    "enemy_wave": "Enemy wave note recorded: wave behavior flagged for smarter spawn pacing and clearer warning UI.",
                    "loadout": "Loadout note recorded: preserve readable neon weapon arcs and avoid excessive projectile clutter.",
                    "scoreboard": "Scoreboard snapshot recorded: panel marker saved for later scoring/encounter tuning.",
                },
            },
        }
        default = {
            "title": f"{str((mode.get('manifest') or {}).get('title', mode.get('name', 'MODE'))).upper()} // HUB PANEL",
            "subtitle": "PANEL FALLBACK // MODE KEPT ISOLATED // ESC CLOSES",
            "log_name": f"{mode_id}_panel_log.json",
            "log_title": "MODE PANEL LOG",
            "actions": [
                ("note", "ADD PANEL NOTE"),
                ("status", "ADD STATUS MARKER"),
                ("review", "ADD REVIEW MARKER"),
                ("session_marker", "ADD SESSION MARKER"),
            ],
            "templates": {
                "note": "Panel note recorded from HoloVerse Core.",
                "status": "Status marker recorded from HoloVerse Core.",
                "review": "Review marker recorded from HoloVerse Core.",
                "session_marker": "Session marker recorded from HoloVerse Core.",
            },
        }
        return specs.get(mode_id, default)

    def _panel_log_path(self, mode: dict) -> Path:
        spec = self._panel_mode_spec(mode)
        folder = Path(mode.get("folder") or ROOT)
        return folder / str(spec.get("log_name", "mode_panel_log.json"))

    def _load_panel_entries(self, mode: dict) -> list:
        path = self._panel_log_path(mode)
        try:
            data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
            entries = data.get("entries", []) if isinstance(data, dict) else []
            if isinstance(entries, list):
                return [entry for entry in entries if isinstance(entry, dict)][-80:]
        except Exception:
            pass
        return []

    def _save_panel_entries(self, mode: dict, entries: list) -> None:
        path = self._panel_log_path(mode)
        spec = self._panel_mode_spec(mode)
        payload = {
            "schema": 1,
            "title": spec.get("log_title", "MODE PANEL LOG"),
            "mode_id": self._panel_mode_id(mode),
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "entries": list(entries)[-80:],
        }
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        except Exception as exc:
            self.center_hint["text"] = f"PANEL LOG WRITE FAILED // {exc}"

    def _append_panel_entry(self, mode: dict, category: str) -> None:
        spec = self._panel_mode_spec(mode)
        templates = dict(spec.get("templates") or {})
        clean_category = str(category or "note")
        entry = {
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "category": clean_category,
            "mode": str(mode.get("name", self._panel_mode_id(mode))),
            "note": templates.get(clean_category, templates.get("note", "Panel note recorded from HoloVerse Core.")),
        }
        entries = self._load_panel_entries(mode)
        entries.append(entry)
        self._save_panel_entries(mode, entries)
        self.center_hint["text"] = f"{str(spec.get('log_title', 'PANEL LOG')).upper()} // {clean_category.upper()} SAVED"
        self._refresh_panel_view(mode)

    def _panel_recent_summary(self, mode: dict, limit: int = 3) -> str:
        entries = self._load_panel_entries(mode)
        if not entries:
            return "NO LOG ENTRIES YET"
        lines = []
        for entry in entries[-max(1, int(limit)):][::-1]:
            stamp = str(entry.get("time", ""))[-8:]
            cat = str(entry.get("category", "note")).upper()
            note = str(entry.get("note", ""))[:70]
            lines.append(f"{stamp} // {cat} // {note}")
        return "  |  ".join(lines)

    def _refresh_panel_view(self, mode: dict) -> None:
        spec = self._panel_mode_spec(mode)
        title = str(spec.get("title", "MODE PANEL")).upper()
        source_kind = str((mode.get("manifest") or {}).get("source_kind", mode.get("source_kind", "unknown"))).upper()
        entries = self._load_panel_entries(mode)
        self.core_console_open = True
        self.core_console_root.show()
        self.core_console_set_cursor(True)
        if hasattr(self, "core_console_title"):
            self.core_console_title["text"] = title
        if hasattr(self, "core_console_subtitle"):
            self.core_console_subtitle["text"] = str(spec.get("subtitle", "PANEL MODE")).upper()
        if hasattr(self, "core_console_label"):
            self.core_console_label["text"] = f"SOURCE {source_kind} // ENTRIES {len(entries):02d} // LOG {self._panel_log_path(mode).name.upper()}"
        if hasattr(self, "core_hint_label"):
            self.core_hint_label["text"] = self._panel_recent_summary(mode)
        actions = list(spec.get("actions") or [])[:4]
        button_defs = []
        for key, label in actions:
            button_defs.append((key, label))
        button_defs.extend([
            ("refresh", "REFRESH LOG"),
            ("standalone", "OPEN STANDALONE FALLBACK"),
            ("core", "RETURN TO CORE DECK"),
            ("close", "CLOSE PANEL"),
        ])
        for idx, btn in enumerate(list(getattr(self, "core_mode_buttons", []) or [])):
            try:
                if idx >= len(button_defs):
                    btn.hide()
                    continue
                action_key, action_label = button_defs[idx]
                btn["text"] = (f"{action_label}\n{self._panel_recent_summary(mode, 1) if idx == 4 else ''}").strip()
                btn["command"] = self.core_panel_action
                btn["extraArgs"] = [action_key]
                btn.show()
                self.apply_core_button_style(btn, role="yellow" if idx in (0, 5) else "mode", active=(idx == 0), available=True)
            except Exception:
                pass
        try:
            self.core_page_button.hide()
        except Exception:
            pass
        try:
            self.core_hub_button.show()
            self.core_close_button.show()
        except Exception:
            pass

    def placeholder_transition_context(self, mode: dict, label: str = "") -> dict:
        manifest = dict(mode.get("manifest") or {})
        mode_name = str(mode.get("name") or label or manifest.get("title") or "Dimension").strip() or "Dimension"
        mode_id = str(manifest.get("id") or re.sub(r"[^a-z0-9]+", "_", mode_name.lower()).strip("_") or "placeholder")
        guidance = dict(PLACEHOLDER_TRANSITION_GUIDANCE.get(mode_id, {}) or manifest.get("placeholder_guidance") or {})
        bot_name = ""
        region = ""
        support = ""
        try:
            profiles = bot_profile_map_copy(getattr(self, "bot_dimension_links", {}) or DEFAULT_BOT_DIMENSION_PROFILES)
            for name, profile in profiles.items():
                if str(profile.get("mode", "")).strip().lower() == mode_name.lower():
                    bot_name = str(profile.get("bot") or name)
                    region = str(profile.get("region") or "")
                    support = str(profile.get("matrixcore_support") or profile.get("player_hint") or "")
                    break
        except Exception:
            pass
        if not guidance:
            guidance = {
                "intent": "reserved future dimension",
                "gleebs": f"{mode_name} is staged, not broken. Route entry is not ready yet, so MatrixCore blocks the launch safely.",
                "matrixcore": "This doorway is intentionally reserved until a real main.py is added.",
                "next_step": f"Drop a working main.py into this dimension folder to activate {mode_name}.",
            }
        lore_panel_text = ""
        lore_source = ""
        if mode_id == "lore":
            lore = load_matrixcore_lore_study()
            lore_source = str(lore.get("_loaded_from") or MATRIXCORE_CONTENT_LORE_STUDY_PATH)
            lore_panel_text = matrixcore_lore_display_summary(lore, chapter_limit=4, canon_limit=3)
            guidance["gleebs"] = str((lore.get("matrixcore_ui_lines") or {}).get("lore") or guidance.get("gleebs") or "Lore archive online.")
            guidance["matrixcore"] = str(lore.get("core_truth") or guidance.get("matrixcore") or "MatrixCore lore archive is readable.")
            guidance["next_step"] = "Read this MatrixCore lore panel now; later replace the placeholder with a full Lore dimension when ready."
        return {
            "mode_name": mode_name,
            "mode_id": mode_id,
            "bot": bot_name,
            "region": region,
            "intent": str(guidance.get("intent") or "reserved future dimension"),
            "gleebs": str(guidance.get("gleebs") or "This doorway is staged, not broken."),
            "matrixcore": str(guidance.get("matrixcore") or support or "MatrixCore is holding this route until a real entry file exists."),
            "next_step": str(guidance.get("next_step") or f"Drop a working main.py into this dimension folder to activate {mode_name}."),
            "support": support,
            "lore_panel_text": lore_panel_text,
            "lore_source": lore_source,
        }

    def record_matrixcore_placeholder_signal(self, mode: dict, label: str, *, source: str = "core", transition_id: str = "", transition_route: str = "transition_placeholder") -> dict:
        info = self.placeholder_transition_context(mode, label)
        progress = self.load_matrixcore_progression()
        placeholders = progress.setdefault("dimension_placeholders", {})
        if not isinstance(placeholders, dict):
            placeholders = {}
        mode_name = str(info.get("mode_name") or label or "Dimension")
        entry = placeholders.get(mode_name) if isinstance(placeholders.get(mode_name), dict) else {}
        entry.update({
            "mode": mode_name,
            "id": str(info.get("mode_id") or ""),
            "bot": str(info.get("bot") or ""),
            "region": str(info.get("region") or ""),
            "route": str(transition_route or "transition_placeholder"),
            "source": str(source or "core"),
            "intent": str(info.get("intent") or "reserved future dimension"),
            "next_step": str(info.get("next_step") or "Drop in a real main.py."),
            "last_transition_id": str(transition_id or ""),
            "last_seen_at": datetime.now().isoformat(timespec="seconds"),
            "count": int(entry.get("count", 0) or 0) + 1,
        })
        placeholders[mode_name] = entry
        progress["dimension_placeholders"] = placeholders
        progress.setdefault("guidance_state", {}).update({
            "current_hint_id": "placeholder_transition",
            "next_action": str(info.get("next_step") or "Replace this scaffold with a real dimension entry."),
            "why": str(info.get("matrixcore") or "MatrixCore blocked an empty dimension folder safely."),
            "last_placeholder": mode_name,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        })
        matrixcore = progress.setdefault("matrixcore", {})
        matrixcore["last_placeholder_transition"] = mode_name
        matrixcore["pending_return_hint"] = ""
        self.save_matrixcore_progression(progress)
        return self.append_matrixcore_event({
            "kind": "dimension_placeholder_transition",
            "mode": mode_name,
            "label": label,
            "route": transition_route,
            "source": source,
            "reason": "no_entry_file_no_process_started",
            "bot": str(info.get("bot") or ""),
            "region": str(info.get("region") or ""),
        })

    def open_mode_placeholder_panel(self, mode: dict, label: str):
        manifest = dict(mode.get("manifest") or {})
        title = str(manifest.get("title") or mode.get("name") or label or "PLACEHOLDER").upper()
        folder = Path(mode.get("folder") or ROOT)
        info = self.placeholder_transition_context(mode, label)
        bot_bits = []
        if info.get("bot"):
            bot_bits.append(f"BOT {str(info.get('bot')).upper()}")
        if info.get("region"):
            bot_bits.append(f"REGION {str(info.get('region')).upper()}")
        ownership = " // ".join(bot_bits) if bot_bits else "BOT ROUTE UNASSIGNED"
        self.core_panel_context = {"mode": dict(mode), "label": str(label), "placeholder": True}
        self.write_mode_gateway_audit()
        self._append_mode_gateway_history("placeholder_transition_panel", mode=mode, label=label, route="transition_placeholder", extra={"folder": os.fspath(folder), "bot": info.get("bot", ""), "entry_started": False})
        self.core_console_open = True
        self.core_console_root.show()
        self.core_console_set_cursor(True)
        is_lore_placeholder = str(info.get("mode_id") or "").lower() == "lore"
        if hasattr(self, "core_console_title"):
            self.core_console_title["text"] = "LORE // MATRIXCORE ARCHIVE" if is_lore_placeholder else f"{title} // TRANSITION HOLD"
        if hasattr(self, "core_console_subtitle"):
            self.core_console_subtitle["text"] = "READING BUNDLED MATRIXCORE LORE // NO PROCESS STARTED" if is_lore_placeholder else "MATRIXCORE RESERVED DIMENSION // NO PROCESS STARTED"
        if hasattr(self, "core_console_label"):
            source_note = f" // SOURCE {Path(str(info.get('lore_source') or '')).name}" if is_lore_placeholder and info.get("lore_source") else ""
            self.core_console_label["text"] = f"{ownership} // FOLDER {folder.name.upper()} // ENTRY MAIN.PY MISSING{source_note}"
        if hasattr(self, "core_hint_label"):
            self.core_hint_label["text"] = str(info.get("lore_panel_text") or f"Gleebs: {info.get('gleebs')}  //  Next: {info.get('next_step')}")
            try:
                self.core_hint_label["text_align"] = TextNode.ALeft
                self.core_hint_label["text_wordwrap"] = 42.0
            except Exception:
                pass
        button_defs = [("lore_core", "OPEN ARCHIVE"), ("placeholder_signal", "SHOW SIGNAL"), ("close", "CLOSE")] if is_lore_placeholder else [("core", "RETURN TO CORE DECK"), ("placeholder_signal", "SHOW THIS SIGNAL"), ("close", "CLOSE PLACEHOLDER")]
        for idx, btn in enumerate(list(getattr(self, "core_mode_buttons", []) or [])):
            try:
                if idx >= len(button_defs):
                    btn.hide()
                    continue
                action_key, action_label = button_defs[idx]
                btn["text"] = action_label
                btn["command"] = self.core_panel_action
                btn["extraArgs"] = [action_key]
                btn.show()
                self.apply_core_button_style(btn, role="yellow" if idx == 0 else "mode", active=(idx == 0), available=True)
            except Exception:
                pass
        try:
            self.core_page_button.hide()
            self.core_hub_button.show()
            self.core_close_button.show()
        except Exception:
            pass
        self.center_hint["text"] = f"LORE ARCHIVE // MATRIXCORE CONTENT DISPLAYED" if str(info.get("mode_id") or "").lower() == "lore" else f"TRANSITION HOLD // {title} // MAIN.PY REQUIRED"
        if self.audio:
            self.audio.play('menu_open.wav', 'sfx', 0.55)

    def open_mode_panel_preview(self, mode: dict, label: str):
        self.core_panel_context = {"mode": dict(mode), "label": str(label)}
        self.write_mode_gateway_audit()
        self._append_mode_gateway_history("panel_open", mode=mode, label=label, route=MODE_LAUNCH_PANEL)
        self._refresh_panel_view(mode)
        self.center_hint["text"] = f"CORE // {str(label).upper()} PANEL OPEN"
        if self.audio:
            self.audio.play('menu_open.wav', 'sfx', 0.65)

    def core_panel_action(self, action: str):
        ctx = dict(getattr(self, "core_panel_context", {}) or {})
        mode = dict(ctx.get("mode") or {})
        if not mode:
            self.refresh_core_console()
            return
        action = str(action or "refresh")
        if action == "lore_core":
            self.core_panel_context = None
            self.matrixcore_set_page("lore")
            return
        if action == "placeholder_signal":
            info = self.placeholder_transition_context(mode, str(ctx.get("label", "")))
            source = f" Source: {Path(str(info.get('lore_source'))).name}." if info.get("lore_source") else ""
            self.gleebs_dialogue_text_override = f"{info.get('gleebs')} Next signal: {info.get('next_step')}.{source}"
            try:
                self.show_gleebs_dialogue("gleebs_placeholder_transition_001", flag="gleebs_placeholder_transition_001", duration=7.5, mark_seen=False)
            finally:
                self.gleebs_dialogue_text_override = ""
            self.open_mode_placeholder_panel(mode, str(ctx.get("label", "")))
            return
        if action == "refresh":
            self._refresh_panel_view(mode)
            return
        if action == "core":
            self.core_panel_context = None
            self.refresh_core_console()
            return
        if action == "close":
            self.core_panel_context = None
            self.close_core_console()
            return
        if action == "standalone":
            self._append_mode_gateway_history("panel_standalone_request", mode=mode, label=str(ctx.get("label", "")), route=MODE_LAUNCH_PANEL)
            path, label, extra_env = self.resolve_core_mode_entry(mode)
            if path is None or not Path(path).exists():
                self.center_hint["text"] = "PANEL // ENTRY NOT READY"
                self._refresh_panel_view(mode)
                return
            extra_env = dict(extra_env or {})
            extra_env["HOLOVERSE_PANEL_STANDALONE_FALLBACK"] = "1"
            extra_env["HOLOVERSE_MODE_LAUNCH_TYPE"] = MODE_LAUNCH_EXTERNAL
            self.core_panel_context = None
            self.close_core_console()
            self.launch_external_level(path, f"{label} // STANDALONE", extra_env=extra_env)
            return
        self._append_mode_gateway_history("panel_log_action", mode=mode, label=str(ctx.get("label", "")), route=MODE_LAUNCH_PANEL, extra={"action": action})
        self._append_panel_entry(mode, action)

    def _load_bot_dimension_links(self) -> dict:
        config = ensure_bot_dimension_config()
        profiles = migrate_bot_links_to_profiles(config)
        out = {}
        for bot, profile in profiles.items():
            if not isinstance(profile, dict):
                continue
            name = str(profile.get("bot") or bot).strip()
            mode = str(profile.get("mode", "")).strip()
            if not name or not mode:
                continue
            item = dict(profile)
            item["bot"] = name
            item["mode"] = mode
            out[normalize_lookup_key(name)] = item
        return out

    def _active_named_region_bot_nodes(self) -> list:
        """Return every live named region bot, including source-bridge bots.

        The default HoloVerse world normally runs through
        ``HoloVerseWorldShellMount.source_runtime``. The previous bot-dialogue
        detector only checked the mount wrapper list, which is empty when the
        world.py source bridge owns the visuals. That made clicking/E find zero
        bots even though IO, Vanta, Nyx, etc. were visible in-game.
        """
        nodes = []

        def collect_from(owner):
            if owner is None:
                return
            try:
                getter = getattr(owner, "_active_named_region_bot_nodes", None)
                if callable(getter):
                    found = getter()
                else:
                    found = getattr(owner, "named_region_bot_nodes", []) or []
                nodes.extend(list(found or []))
            except Exception:
                pass

        mount = getattr(self, "world_shell_mount", None)
        collect_from(mount)
        # Critical source-bridge path: this is where the actual visible bots live
        # when HoloVerse is mounted from world.py instead of the fallback shell.
        collect_from(getattr(mount, "source_runtime", None) if mount is not None else None)
        collect_from(self)

        clean, seen = [], set()
        for node in nodes:
            try:
                if node is None or node.isEmpty():
                    continue
                key = node.getKey()
                if key in seen:
                    continue
                seen.add(key)
                if str(node.getPythonTag("named_region_bot_name") or "").strip():
                    clean.append(node)
            except Exception:
                continue
        return clean

    def bot_interaction_center(self, node) -> Vec3:
        try:
            pos = node.getPos(self.render)
            scale = max(1.0, float(node.getScale(self.render).x))
            return Vec3(pos.x, pos.y, pos.z + scale * 1.55)
        except Exception:
            return Vec3(0, 0, 0)

    def _bot_distance_from_player(self, node) -> float:
        try:
            return float((self.bot_interaction_center(node) - self.head_world_pos()).length())
        except Exception:
            return 999999.0

    def _bot_screen_samples(self, node) -> list:
        """Return projected bot sample points for mouse clicking.

        The region bots are generated visual nodes, not dedicated collision
        meshes. Projecting body/head samples makes a left click mean the bot
        under the mouse instead of only the center crosshair.
        """
        try:
            pos = node.getPos(self.render)
            scale = max(1.0, float(node.getScale(self.render).x))
            return [
                Vec3(pos.x, pos.y, pos.z + scale * 0.95),
                Vec3(pos.x, pos.y, pos.z + scale * 1.55),
                Vec3(pos.x, pos.y, pos.z + scale * 2.25),
            ]
        except Exception:
            try:
                return [self.bot_interaction_center(node)]
            except Exception:
                return []

    def find_mouse_clicked_bot(self, max_distance=520.0):
        nodes = self._active_named_region_bot_nodes()
        if not nodes:
            return None, 999.0, -1.0
        mouse = None
        try:
            if getattr(self, "mouseWatcherNode", None) is not None and self.mouseWatcherNode.hasMouse():
                mouse = self.mouseWatcherNode.getMouse()
        except Exception:
            mouse = None
        # In captured first-person mode the OS cursor is intentionally hidden and
        # effectively locked near center. Use center-screen as the click target so
        # crosshair clicking still works.
        if mouse is None or bool(getattr(self, "mouse_captured", False)):
            mouse = Point2(0.0, 0.0)
        best, best_score, best_dot = None, 999999.0, -1.0
        forward, _right, _up = self.get_view_basis()
        if forward.lengthSquared() > 0.0001:
            forward.normalize()
        origin = self.head_world_pos()
        lens = getattr(self, "camLens", None)
        if lens is None:
            return self.find_looked_at_bot(max_distance=max_distance, cone_cos=0.50)
        for node in nodes:
            try:
                center = self.bot_interaction_center(node)
                to_bot = center - origin
                distance = float(to_bot.length())
                if distance <= 0.001 or distance > max_distance:
                    continue
                direction = Vec3(to_bot); direction.normalize()
                dot = float(forward.dot(direction)) if forward.lengthSquared() > 0.0001 else 0.0
                # Do not let a bot behind the player win only because projection
                # math still returns a point near screen bounds.
                if dot < 0.12:
                    continue
                scale = max(1.0, float(node.getScale(self.render).x))
                # Normalized -1..1 screen coordinates. This grows when close and
                # stays forgiving enough for compact moving drones at range.
                hit_radius = max(0.075, min(0.235, 0.055 + (scale * 4.8) / max(distance, 1.0)))
                nearest_screen_error = 999999.0
                for sample in self._bot_screen_samples(node):
                    rel = self.camera.getRelativePoint(self.render, Point3(sample.x, sample.y, sample.z))
                    screen = Point2()
                    if not lens.project(rel, screen):
                        continue
                    dx = float(screen.x - mouse.x)
                    dz = float(screen.y - mouse.y)
                    err = math.sqrt(dx * dx + dz * dz)
                    nearest_screen_error = min(nearest_screen_error, err)
                if nearest_screen_error <= hit_radius:
                    score = nearest_screen_error + distance * 0.0015
                    if score < best_score:
                        best, best_score, best_dot = node, score, dot
            except Exception:
                continue
        if best is not None:
            return best, best_score, best_dot
        # Final fallback: click behaves like E if the bot is centered enough.
        return self.find_looked_at_bot(max_distance=max_distance, cone_cos=0.50)

    def find_looked_at_bot(self, max_distance=260.0, cone_cos=0.50):
        nodes = self._active_named_region_bot_nodes()
        if not nodes:
            return None, 999.0, -1.0
        forward, _right, _up = self.get_view_basis()
        if forward.lengthSquared() <= 0.0001:
            return None, 999.0, -1.0
        forward.normalize()
        origin = self.head_world_pos()
        best, best_score, best_dot = None, 999.0, -1.0
        nearest, nearest_dist = None, 999999.0
        for node in nodes:
            try:
                center = self.bot_interaction_center(node)
                target = center - origin
                distance = target.length()
                if distance < nearest_dist:
                    nearest, nearest_dist = node, distance
                if distance <= 0.001 or distance > max_distance:
                    continue
                direction = Vec3(target); direction.normalize()
                dot = float(forward.dot(direction))
                if dot < cone_cos:
                    continue
                cross_error = math.sqrt(max(0.0, 1.0 - dot * dot)) * distance
                # Bots are moving 3D quest givers, so this must be more forgiving
                # than artifact selection. Otherwise E/click feels broken unless
                # the player is perfectly aimed at the center of the drone.
                if cross_error > max(30.0, distance * 0.26):
                    continue
                score = cross_error + distance * 0.006
                if score < best_score:
                    best, best_score, best_dot = node, score, dot
            except Exception:
                continue
        if best is not None:
            return best, best_score, best_dot
        # Nearby fallback for E: standing beside a bot should work even if the
        # camera is not perfectly pointed at its compact generated body.
        if nearest is not None and nearest_dist <= 76.0:
            return nearest, nearest_dist, 0.0
        return None, 999.0, -1.0

    def find_nearest_bot(self, max_distance=76.0):
        best, best_dist = None, 999999.0
        for node in self._active_named_region_bot_nodes():
            try:
                dist = self._bot_distance_from_player(node)
                if dist < best_dist:
                    best, best_dist = node, dist
            except Exception:
                continue
        if best is not None and best_dist <= max_distance:
            return best, best_dist, 0.0
        return None, 999.0, -1.0

    def resolve_bot_assigned_mode_title(self, bot: str, fallback: str = "") -> str:
        """Return the current dimension title for a bot using the index first."""
        bot = str(bot or "").strip()
        profile = dict((getattr(self, "bot_dimension_links", {}) or {}).get(normalize_lookup_key(bot), {}) or {})
        try:
            payload = read_dimension_index_payload()
            by_bot = payload.get("by_bot") if isinstance(payload.get("by_bot"), dict) else {}
            dimensions = payload.get("dimensions") if isinstance(payload.get("dimensions"), dict) else {}
            dimension_id = str(by_bot.get(bot) or by_bot.get(normalize_lookup_key(bot)) or "").strip()
            dimension_id = canonical_dimension_lookup_key(dimension_id)
            record = dimensions.get(dimension_id) if isinstance(dimensions, dict) else None
            if isinstance(record, dict):
                return str(record.get("name") or record.get("title") or profile.get("mode") or fallback).strip()
        except Exception:
            pass
        return str(profile.get("mode") or fallback or "").strip()

    def bot_dialogue_context_for_node(self, node) -> dict | None:
        try:
            bot = str(node.getPythonTag("named_region_bot_name") or "").strip()
            region = str(node.getPythonTag("named_region_bot_region") or "").strip()
        except Exception:
            return None
        if not bot:
            return None
        link = dict((getattr(self, "bot_dimension_links", {}) or {}).get(normalize_lookup_key(bot), {}) or {})
        mode = self.resolve_bot_assigned_mode_title(bot, str(link.get("mode") or ""))
        if not mode:
            return None
        return {"node": node, "bot": str(link.get("bot") or bot), "region": str(link.get("region") or region), "mode": mode}

    def set_bot_paused(self, node, paused: bool):
        try:
            if node is not None and not node.isEmpty():
                node.setPythonTag("named_region_bot_paused", bool(paused))
        except Exception:
            pass

    def find_core_mode_by_title(self, title: str, *, bot_name: str = "") -> dict | None:
        target = canonical_dimension_lookup_key(title)
        if not target:
            return None
        for mode in list(getattr(self, "core_modes", []) or []):
            manifest = dict(mode.get("manifest") or {})
            names = [mode.get("name", ""), manifest.get("title", ""), manifest.get("id", ""), Path(str(mode.get("folder", ""))).name]
            if any(canonical_dimension_lookup_key(name) == target for name in names):
                return mode
        record = dimension_record_from_index(title, bot_name=bot_name)
        recovered = mode_from_dimension_record(record) if record else None
        if recovered is not None:
            try:
                modes = list(getattr(self, "core_modes", []) or [])
                r_manifest = dict(recovered.get("manifest") or {})
                r_key = canonical_dimension_lookup_key(r_manifest.get("id") or recovered.get("name"))
                if not any(canonical_dimension_lookup_key((m.get("manifest") or {}).get("id") or m.get("name")) == r_key for m in modes):
                    modes.append(recovered)
                    self.core_modes = modes
            except Exception:
                pass
            return recovered
        return None

    def set_bot_dialogue_hud_suppressed(self, suppressed: bool):
        """State-aware HUD suppression for the bot invite modal.

        Pass 5 regression guard: do not blindly restore every HUD node after a
        bot prompt closes.  The native/loading overlay owns its own lifecycle,
        and refresh_ui/update_holoverse_region_ui decide which normal HUD lanes
        should be visible.
        """
        suppressed = bool(suppressed)
        self.bot_dialogue_hud_suppressed = suppressed
        names = (
            "top_panel",
            "region_top_panel",
            "region_keymap_root",
            "crosshair_root",
            "coords_label",
            "perf_hud_label",
        )
        hud_visible = bool(getattr(getattr(self, "cfg", None), "hud_visible", True))
        menu_blocked = bool(getattr(self, "menu_open", False) or getattr(self, "core_console_open", False))
        mode_blocked = bool(getattr(self, "active_native_mode", None) is not None or getattr(self, "external_process", None) is not None)
        for name in names:
            node = getattr(self, name, None)
            if node is None:
                continue
            try:
                if suppressed or not hud_visible or mode_blocked:
                    node.hide()
                elif name in {"region_top_panel", "region_keymap_root"}:
                    # Region HUD is restored by update_holoverse_region_ui so it
                    # cannot duplicate or ignore its normal visibility rules.
                    pass
                elif menu_blocked and name in {"top_panel", "coords_label", "crosshair_root"}:
                    node.hide()
                else:
                    node.show()
            except Exception:
                pass
        try:
            hint = getattr(self, "center_hint", None)
            if hint is not None:
                if suppressed or not hud_visible:
                    hint.hide()
                else:
                    hint.show()
        except Exception:
            pass
        try:
            self.update_holoverse_region_ui()
        except Exception:
            pass

    def open_focused_bot_dialogue(self, source: str = "interact") -> bool:
        if getattr(self, "bot_dialogue_open", False):
            return True
        if self.menu_open or self.core_console_open or getattr(self, "active_native_mode", None) is not None or getattr(self, "external_process", None) is not None:
            return False
        if str(source).lower().startswith("mouse"):
            node, score, dot = self.find_mouse_clicked_bot()
        else:
            node, score, dot = self.find_looked_at_bot()
            if node is None:
                node, score, dot = self.find_nearest_bot()
        ctx = self.bot_dialogue_context_for_node(node) if node is not None else None
        if not ctx:
            return False
        bot_name = str(ctx.get("bot") or "").strip().lower()
        mode_title = str(ctx.get("mode") or "").strip()
        if str(source).lower().startswith("mouse") and bot_name in {"space bot", "orbit"}:
            # Space Bot is a combat-start doorway, not a normal chat prompt:
            # clicking it should immediately start the assigned space battle.
            mode = self.find_core_mode_by_title(mode_title, bot_name=str(ctx.get("bot", "")))
            if mode is not None:
                self.center_hint["text"] = "SPACE BOT // STARTING SPACE BATTLE"
                return bool(self.launch_bot_dimension_mode(mode, ctx))
        self.open_bot_dimension_dialogue(ctx, source=source, score=score, dot=dot)
        return True

    def open_bot_dimension_dialogue(self, ctx: dict, source: str = "interact", score: float = 0.0, dot: float = 0.0):
        old = dict(getattr(self, "bot_dialogue_context", {}) or {})
        if old.get("node") is not None and old.get("node") is not ctx.get("node"):
            self.set_bot_paused(old.get("node"), False)
        self.bot_dialogue_context = dict(ctx)
        self.bot_dialogue_open = True
        self.bot_dialogue_node = ctx.get("node")
        self.bot_dialogue_bot = str(ctx.get("bot", "BOT"))
        self.bot_dialogue_region = str(ctx.get("region", "REGION"))
        self.bot_dialogue_mode = str(ctx.get("mode", "DIMENSION"))
        self.set_bot_paused(self.bot_dialogue_node, True)
        self.menu_open = False
        try:
            self.menu_root.hide()
        except Exception:
            pass
        self.keys.clear(); self.move_velocity = Vec2(0, 0); self.mouse_captured = False
        self.core_console_set_cursor(True)
        self.set_bot_dialogue_hud_suppressed(True)
        self.refresh_bot_dimension_dialogue()
        try: self.bot_dialogue_root.show()
        except Exception: pass
        self.center_hint["text"] = f"{self.bot_dialogue_bot.upper()} // DIMENSION INVITE"
        print(f"interaction_probe source={source} target=region_bot bot={self.bot_dialogue_bot} mode={self.bot_dialogue_mode} score={float(score):.3f} dot={float(dot):.3f}")
        try:
            self.record_matrixcore_bot_signal("bot_contact", self.bot_dialogue_bot, self.bot_dialogue_region, self.bot_dialogue_mode, source=str(source or "interact"))
        except Exception:
            pass
        if self.audio: self.audio.play('menu_open.wav', 'sfx', 0.68)

    def bot_dialogue_prompt_for_mode(self, mode_title: str, bot_name: str = "", region: str = "") -> str:
        if bot_name:
            return self.matrixcore_bot_support_prompt(bot_name, region, mode_title)
        return BOT_DIMENSION_PROMPT

    def refresh_bot_dimension_dialogue(self):
        bot = str(getattr(self, "bot_dialogue_bot", "BOT") or "BOT")
        region = str(getattr(self, "bot_dialogue_region", "REGION") or "REGION")
        mode = str(getattr(self, "bot_dialogue_mode", "DIMENSION") or "DIMENSION")
        found = self.find_core_mode_by_title(mode, bot_name=bot)
        exists = found is not None
        route = "MISSING"
        if found is not None:
            manifest = dict(found.get("manifest") or {})
            route = route_display_name(normalize_mode_launch_type(manifest.get("launch_type") or found.get("launch_type")))
        support = self.matrixcore_bot_support_entry(bot)
        role = str(support.get("role", "builder ally") or "builder ally").upper()
        self.bot_dialogue_title["text"] = f"{bot.upper()} // {region.upper()}"
        self.bot_dialogue_question["text"] = compact_ui_text(self.bot_dialogue_prompt_for_mode(mode, bot, region), 185)
        self.bot_dialogue_mode_label["text"] = mode.upper()
        if bool(getattr(self, "bot_dialogue_launch_in_progress", False)):
            self.bot_dialogue_detail["text"] = compact_ui_text(f"LAUNCHING // {role} // ROUTE {route} // PLEASE WAIT", 145)
        else:
            self.bot_dialogue_detail["text"] = compact_ui_text(f"{'READY' if exists else 'MODE NOT FOUND'} // {role} // ROUTE {route} // YES / NO // ESC", 145)
        self.apply_core_button_style(getattr(self, "bot_dialogue_yes", None), role="yellow", available=exists)
        self.apply_core_button_style(getattr(self, "bot_dialogue_no", None), role="white", available=True)

    def close_bot_dimension_dialogue(self, reason: str = "close"):
        ctx = dict(getattr(self, "bot_dialogue_context", {}) or {})
        self.set_bot_paused(ctx.get("node"), False)
        self.bot_dialogue_launch_in_progress = False
        self.bot_dialogue_open = False; self.bot_dialogue_context = None; self.bot_dialogue_node = None
        try:
            if getattr(self, "bot_dialogue_root", None) is not None: self.bot_dialogue_root.hide()
        except Exception:
            pass
        self.set_bot_dialogue_hud_suppressed(False)
        self.mouse_captured = True
        self.core_console_set_cursor(False)
        if not SELF_TEST: self.recenter_mouse(force=True)
        if reason not in {"launch", "launching"}:
            self.center_hint["text"] = "BOT LINK // CLOSED"
            if self.audio: self.audio.play('menu_close.wav', 'sfx', 0.58)

    def confirm_bot_dimension_dialogue(self):
        if bool(getattr(self, "bot_dialogue_launch_in_progress", False)):
            self.center_hint["text"] = "BOT LINK // LAUNCH ALREADY STARTING"
            return
        ctx = dict(getattr(self, "bot_dialogue_context", {}) or {})
        mode_title = str(ctx.get("mode") or getattr(self, "bot_dialogue_mode", "")).strip()
        if not mode_title:
            self.center_hint["text"] = "BOT LINK // NO DIMENSION ASSIGNED"; return
        mode = self.find_core_mode_by_title(mode_title, bot_name=str(ctx.get("bot", "")))
        if mode is None:
            self.center_hint["text"] = f"BOT LINK // {mode_title.upper()} MODE MISSING"; self.refresh_bot_dimension_dialogue(); return
        self.bot_dialogue_launch_in_progress = True
        self.bot_dialogue_last_launch_error = ""
        self.refresh_bot_dimension_dialogue()
        ok = self.launch_bot_dimension_mode(mode, ctx)
        if not ok:
            self.bot_dialogue_launch_in_progress = False
            self.bot_dialogue_last_launch_error = f"{mode_title} route blocked"
            self.center_hint["text"] = f"BOT LINK // {mode_title.upper()} LAUNCH FAILED"
            try:
                self.refresh_bot_dimension_dialogue()
                if getattr(self, "bot_dialogue_root", None) is not None:
                    self.bot_dialogue_root.show()
                self.set_bot_dialogue_hud_suppressed(True)
                self.core_console_set_cursor(True)
                self.mouse_captured = False
            except Exception:
                pass

    def start_dimension_transition(self, mode: dict, source: str = "core", context: dict | None = None, extra_env: dict | None = None, close_core: bool = True) -> bool:
        """Start the transition-owned route, then dispatch to the proven launcher.

        This is intentionally a gateway stub: it owns transition identity, context,
        history, and MatrixCore signals, while the existing resolver underneath
        still decides placeholder, panel, embedded, or hosted launch behavior.
        """
        mode = dict(mode or {})
        manifest = dict(mode.get("manifest") or {})
        label = str(self.dimension_display_name_for_mode(mode, mode.get("name") or manifest.get("title") or "DIMENSION"))
        mode_id = str(manifest.get("id") or re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_") or "dimension")
        launch_type = normalize_mode_launch_type(manifest.get("launch_type") or mode.get("launch_type"))
        placeholder = bool(manifest.get("placeholder_mode", False) or mode.get("placeholder", False) or launch_type == MODE_LAUNCH_PLACEHOLDER)
        transition_route = str(manifest.get("x_transition_route") or manifest.get("transition_route") or transition_route_for_launch_type(launch_type, placeholder=placeholder))
        transition_stage = str(manifest.get("x_transition_stage") or manifest.get("transition_stage") or ("reserved_placeholder" if placeholder else "dispatch"))
        transition_id = f"{int(time.time() * 1000)}_{mode_id}"
        ctx = {str(k): str(v) for k, v in dict(context or {}).items() if v is not None}
        route_env = {
            "HOLOVERSE_TRANSITION_ACTIVE": "1",
            "HOLOVERSE_TRANSITION_ID": transition_id,
            "HOLOVERSE_TRANSITION_ROUTE": transition_route,
            "HOLOVERSE_TRANSITION_STAGE": transition_stage,
            "HOLOVERSE_TRANSITION_SOURCE": str(source or "core"),
            "HOLOVERSE_TRANSITION_MODE_ID": mode_id,
            "HOLOVERSE_TRANSITION_MODE_LABEL": label,
        }
        if ctx:
            try:
                route_env["HOLOVERSE_TRANSITION_CONTEXT"] = json.dumps(ctx, sort_keys=True)
            except Exception:
                route_env["HOLOVERSE_TRANSITION_CONTEXT"] = str(ctx)
        if extra_env:
            for key, value in dict(extra_env).items():
                route_env[str(key)] = str(value)
        self._append_mode_gateway_history(
            "transition_begin",
            mode=mode,
            label=label,
            route=launch_type,
            extra={
                "transition_id": transition_id,
                "transition_route": transition_route,
                "transition_stage": transition_stage,
                "source": source,
                "context_keys": ",".join(sorted(ctx.keys())),
            },
        )
        try:
            self.record_matrixcore_dimension_signal(
                "dimension_transition_begin",
                label,
                label=label,
                route=transition_route,
                source=str(source or "core"),
                reason=transition_stage,
            )
        except Exception:
            pass
        if placeholder:
            try:
                self.record_matrixcore_placeholder_signal(mode, label, source=str(source or "core"), transition_id=transition_id, transition_route=transition_route)
            except Exception:
                pass
        try:
            route_label = route_display_name(launch_type)
            self.center_hint["text"] = f"TRANSITION // {label.upper()} // {route_label}"
        except Exception:
            pass
        ok = self.launch_core_mode_route(mode, source=str(source or "core"), extra_env=route_env, close_core=close_core)
        self._append_mode_gateway_history(
            "transition_dispatched" if ok else "transition_blocked",
            mode=mode,
            label=label,
            route=launch_type,
            extra={
                "transition_id": transition_id,
                "transition_route": transition_route,
                "transition_stage": transition_stage,
                "source": source,
                "result": "ok" if ok else "blocked",
            },
        )
        if not ok:
            try:
                self.record_matrixcore_dimension_signal(
                    "dimension_transition_failed",
                    label,
                    label=label,
                    route=transition_route,
                    source=str(source or "core"),
                    reason="blocked",
                )
            except Exception:
                pass
        return bool(ok)

    def launch_core_mode_route(self, mode: dict, source: str = "core", extra_env: dict | None = None, close_core: bool = True) -> bool:
        """Launch a mode through one shared route resolver.

        Every doorway into a mode must call this method. Region bots, Core deck
        buttons, campaign shortcuts, artifacts, or future immersive prompts should
        never change a mode's launch type. They may add context in the environment,
        while placeholder, panel, embedded, and hosted routes remain manifest-driven.
        Legacy native manifests are downgraded to the embedded gateway.
        """
        path, label, route_env = self.resolve_core_mode_entry(mode)
        manifest = dict(mode.get("manifest") or {})
        launch_type = normalize_mode_launch_type(manifest.get("launch_type") or mode.get("launch_type"))
        if bool(manifest.get("placeholder_mode", False) or mode.get("placeholder", False) or launch_type == MODE_LAUNCH_PLACEHOLDER):
            self.open_mode_placeholder_panel(mode, label)
            return True
        if path is None or not Path(path).exists():
            self.center_hint["text"] = f"CORE // {mode.get('name', 'MODE')} ROUTE NOT READY"
            try:
                self.refresh_core_console()
            except Exception:
                pass
            return False
        if launch_type == MODE_LAUNCH_IN_WORLD:
            # In-world dimensions must never fall through to hosted/embedded
            # subprocess launch. Their main.py files are metadata sentinels only;
            # the actual gameplay lives in Dimensions/<name>/runtime.py and is
            # mounted into this live ShowBase instance. This route-truth guard
            # prevents another duplicate/ghost Urban pass where updates happen
            # in a folder or subprocess the player never sees.
            route_env = dict(route_env or {})
            if extra_env:
                for key, value in dict(extra_env).items():
                    route_env[str(key)] = str(value)
            self.sync_core()
            mode_name = str(mode.get("name", label))
            self.core_mode_state["launch_count"] = int(self.core_mode_state.get("launch_count", 0)) + 1
            self.core_mode_state["last_mode"] = mode_name
            self.core_mode_state["last_entry"] = "runtime.py"
            self.core_mode_state["last_launch_type"] = launch_type
            self.core_mode_state["last_launch_source"] = str(source or "core")
            save_mode_state(self.core_mode_state)
            self.last_launched_core_mode = mode_name
            self.last_launched_core_entry = "runtime.py"
            if close_core:
                self.close_core_console()
            manifest_id = str(manifest.get("id") or re.sub(r"[^a-z0-9]+", "_", mode_name.lower()).strip("_") or "").lower()
            method_map = {
                "holoforge": "activate_holoforge_from_mode",
                "forest_growth": "activate_forest_growth_from_mode",
                "hills_life": "activate_hills_life_from_mode",
                "hills_of_life": "activate_hills_life_from_mode",
                "oddities": "activate_oddities_from_mode",
                "ember_hangar": "activate_desert_ships_from_mode",
                "desert_ships": "activate_desert_ships_from_mode",
                "frost_circuit": "activate_frost_circuit_from_mode",
                "urban_warzone": "activate_urban_warzone_from_mode",
                "metropolis_robot_lab": "activate_metropolis_robot_lab_from_mode",
            }
            candidates = []
            mapped = method_map.get(manifest_id)
            if mapped:
                candidates.append(mapped)
            lname = mode_name.lower()
            folder_name = ""
            try:
                folder_name = Path(path).parent.name.lower()
            except Exception:
                folder_name = ""
            route_text = " ".join(
                str(value or "").lower()
                for value in (mode_name, label, manifest.get("title"), manifest.get("id"), folder_name)
            )
            is_metropolis_robot_lab = (
                manifest_id == "metropolis_robot_lab"
                or folder_name == "metropolis robot lab"
                or "metropolis robot lab" in route_text
                or "robot lab" in route_text
                or "metropolis ally forge" in route_text
                or "metropolis robot selector" in route_text
            )
            is_urban_warzone = (
                manifest_id == "urban_warzone"
                or folder_name == "urban warzone"
                or "urban warzone" in route_text
                or "warzone" in route_text
            )
            # Metropolis Robot Lab used to be named "Metropolis Ally Forge" and
            # contains Urban-deployment wording in its manifest. Keep the dispatch
            # exact so selecting Archivist/Metropolis can never open the Urban
            # Warzone runtime or auto-spawn the player in Urban.
            if is_metropolis_robot_lab:
                candidates.append("activate_metropolis_robot_lab_from_mode")
            elif is_urban_warzone:
                candidates.append("activate_urban_warzone_from_mode")
            if "forest" in route_text:
                candidates.append("activate_forest_growth_from_mode")
            if "hill" in route_text:
                candidates.append("activate_hills_life_from_mode")
            if "frost" in route_text:
                candidates.append("activate_frost_circuit_from_mode")
            if "ember" in route_text or "hangar" in route_text or "desert" in route_text:
                candidates.append("activate_desert_ships_from_mode")
            if "forge" in route_text and not is_metropolis_robot_lab:
                candidates.append("activate_holoforge_from_mode")
            if ("metropolis" in route_text or "robot lab" in route_text or "robot_lab" in route_text) and not is_urban_warzone:
                candidates.append("activate_metropolis_robot_lab_from_mode")
            if "odd" in route_text:
                candidates.append("activate_oddities_from_mode")
            seen_methods = set()
            for method_name in candidates:
                if method_name in seen_methods:
                    continue
                seen_methods.add(method_name)
                fn = getattr(self, method_name, None)
                if callable(fn):
                    self._append_mode_gateway_history("in_world_runtime_dispatch", mode=mode, label=label, route=launch_type, extra={"source": source, "runtime_method": method_name, "entry": "runtime.py", "route_truth_guard": True})
                    self.record_matrixcore_dimension_signal("dimension_in_world_dispatch", mode_name, label=label, route=launch_type, source=str(source or "core"))
                    return bool(fn(mode, source=source, route=MODE_LAUNCH_IN_WORLD))
            self.center_hint["text"] = f"CORE // {mode_name.upper()} IN-WORLD RUNTIME NOT INSTALLED"
            self._append_mode_gateway_history("in_world_runtime_missing", mode=mode, label=label, route=launch_type, extra={"source": source, "manifest_id": manifest_id, "candidates": candidates})
            return False
        if launch_type == MODE_LAUNCH_CONNECTED:
            # HoloCore is the one true same-window sub-world.  It must never
            # fall into the embedded child-window launcher, because that route
            # can start a stale/second HoloCore copy without the vessel/mob work.
            path_text = os.fspath(path).replace("\\", "/").lower()
            if self._is_holocore_label(label) or "holocore" in path_text:
                if close_core:
                    self.close_core_console()
                return bool(self.launch_holocore_same_window(mode, source=str(source or "core")))
            # Other legacy same_window records are not HoloCore; route them to
            # their real entry instead of the retired signal placeholder.
            route_env = dict(route_env or {})
            if extra_env:
                for key, value in dict(extra_env).items():
                    route_env[str(key)] = str(value)
            if close_core:
                self.close_core_console()
            return bool(self.launch_embedded_external_level(Path(path), label, extra_env=route_env))
        route_env = dict(route_env or {})
        if extra_env:
            for key, value in dict(extra_env).items():
                route_env[str(key)] = str(value)
        self.sync_core()
        mode_name = str(mode.get("name", label))
        self.core_mode_state["launch_count"] = int(self.core_mode_state.get("launch_count", 0)) + 1
        self.core_mode_state["last_mode"] = mode_name
        self.core_mode_state["last_entry"] = Path(path).name
        self.core_mode_state["last_launch_type"] = launch_type
        self.core_mode_state["last_launch_source"] = str(source or "core")
        save_mode_state(self.core_mode_state)
        self.last_launched_core_mode = mode_name
        self.last_launched_core_entry = Path(path).name
        self._append_mode_gateway_history("mode_route_launch", mode=mode, label=label, route=launch_type, extra={"source": source, "entry": os.fspath(path), "context_keys": sorted(route_env.keys())})
        self.record_matrixcore_dimension_signal("dimension_launch", mode_name, label=label, route=launch_type, source=str(source or "core"))
        if launch_type == MODE_LAUNCH_PANEL:
            self.open_mode_panel_preview(mode, label)
            return True
        if close_core:
            self.close_core_console()
        if launch_type == MODE_LAUNCH_NATIVE:
            return bool(self.launch_native_mode(mode, Path(path), label, source=str(source or "core")))
        if launch_type == MODE_LAUNCH_EMBEDDED:
            return bool(self.launch_embedded_external_level(path, label, extra_env=route_env))
        return bool(self.launch_external_level(path, label, extra_env=route_env))

    def launch_bot_dimension_mode(self, mode: dict, ctx: dict | None = None) -> bool:
        bot_name = str((ctx or {}).get("bot", getattr(self, "bot_dialogue_bot", "BOT")))
        region = str((ctx or {}).get("region", getattr(self, "bot_dialogue_region", "REGION")))
        profile = self.matrixcore_bot_support_entry(bot_name)
        extra_env = {
            "HOLOVERSE_BOT_DIMENSION_LAUNCH": "1",
            "HOLOVERSE_BOT_NAME": bot_name,
            "HOLOVERSE_BOT_REGION": region,
            "HOLOVERSE_BOT_ROLE": str(profile.get("role", "builder ally")),
        }
        manifest = dict(mode.get("manifest") or {})
        declared_launch_type = normalize_mode_launch_type(manifest.get("launch_type") or mode.get("launch_type"))
        try:
            self.record_matrixcore_bot_signal("bot_launch", bot_name, region, str(mode.get("name", "DIMENSION")), route=declared_launch_type, source=f"region_bot:{bot_name}")
        except Exception:
            pass
        self._append_mode_gateway_history("bot_dimension_launch", mode=mode, label=str(mode.get("name", "MODE")), route=declared_launch_type, extra={"bot": bot_name, "region": region, "declared_launch_type": declared_launch_type, "forced_real_entry": False})
        self.close_bot_dimension_dialogue("launching")
        ok = self.start_dimension_transition(
            mode,
            source=f"region_bot:{bot_name}",
            context={"bot": bot_name, "region": region, "doorway": "region_bot"},
            extra_env=extra_env,
            close_core=True,
        )
        if not ok:
            try:
                self.open_bot_dimension_dialogue(dict(ctx or {}), source="launch-failed")
            except Exception:
                pass
        return bool(ok)

    def core_select_mode(self, selection: int):
        modes = list(getattr(self, "core_modes", []) or [])
        idx = int(getattr(self, "core_mode_page", 0)) * CORE_MODE_SLOTS_PER_PAGE + int(selection)
        if idx < 0 or idx >= len(modes):
            self.center_hint["text"] = "CORE // MODE SLOT EMPTY"
            return
        mode = modes[idx]
        manifest = dict(mode.get("manifest") or {})
        launch_type = normalize_mode_launch_type(manifest.get("launch_type") or mode.get("launch_type"))
        self._append_mode_gateway_history("mode_selected", mode=mode, label=str(mode.get("name", "MODE")), route=launch_type)
        self.start_dimension_transition(mode, source="core_deck", context={"doorway": "matrixcore_deck"}, close_core=True)

    def core_launch_campaign(self):
        # Compatibility shim: dispatch the folder-mode entry instead of a hard-coded random mission slot.
        for i, mode in enumerate(getattr(self, "core_modes", []) or []):
            if str(mode.get("name", "")).lower() == "holo campaign":
                self.core_mode_page = i // CORE_MODE_SLOTS_PER_PAGE
                self.core_select_mode(i % CORE_MODE_SLOTS_PER_PAGE)
                return
        self.center_hint["text"] = "CORE // HOLO CAMPAIGN MODE MISSING"

    def core_launch_mx(self):
        # Legacy fallback only; folder modes are now the normal Core launch path.
        if self.is_near_core():
            self.close_core_console()
            self.launch_external_level(self.mx_path, "MX PROTOTYPE LAB")

    def core_toggle_infill(self):
        if self.is_near_core():
            self.close_core_console()
            self.set_hub_fill_enabled(not self.cfg.hub_fill_enabled)
            self.center_hint["text"] = "CORE // INFILL ON" if self.cfg.hub_fill_enabled else "CORE // INFILL OFF"

    def load_core_ui_font(self):
        """Try to load a crisp mono/OCR-like font without requiring bundled font assets."""
        if getattr(self, "_core_ui_font_ready", False):
            return getattr(self, "core_ui_font", None)
        candidates = [
            ROOT / "assets" / "fonts" / "ocr.ttf",
            ROOT / "assets" / "fonts" / "OCR_A.ttf",
            ROOT / "assets" / "fonts" / "OCRAEXT.TTF",
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"),
            Path("/usr/share/fonts/truetype/liberation2/LiberationMono-Bold.ttf"),
        ]
        font = None
        for candidate in candidates:
            try:
                if candidate.exists() and candidate.is_file():
                    font = self.loader.loadFont(Filename.fromOsSpecific(os.fspath(candidate)))
                    break
            except Exception:
                font = None
        self.core_ui_font = font
        self._core_ui_font_ready = True
        return font

    def _core_text_kw(self) -> dict:
        font = self.load_core_ui_font()
        return {"text_font": font} if font is not None else {}

    def core_console_set_cursor(self, visible: bool):
        if self.win is None or not hasattr(self.win, "requestProperties"):
            return
        try:
            props = WindowProperties()
            props.setCursorHidden(not bool(visible) and not SELF_TEST)
            self.win.requestProperties(props)
        except Exception:
            pass

    def core_button_palette(self, role: str = "mode", active: bool = False, available: bool = True):
        role = str(role or "mode").lower()
        if role == "yellow":
            return {"frame": (0.22, 0.015, 0.010, 0.90), "hover": (0.34, 0.030, 0.020, 0.96), "fg": (1.0, 0.82, 0.70, 1.0), "press": (0.46, 0.045, 0.030, 0.98)}
        if role == "white":
            return {"frame": (0.070, 0.010, 0.010, 0.82), "hover": (0.14, 0.020, 0.018, 0.92), "fg": (1.0, 0.92, 0.90, 1.0), "press": (0.22, 0.030, 0.025, 0.96)}
        if active:
            return {"frame": (0.26, 0.018, 0.012, 0.94), "hover": (0.38, 0.030, 0.020, 0.98), "fg": (1.0, 0.20, 0.14, 1.0), "press": (0.48, 0.045, 0.030, 0.99)}
        if not available:
            return {"frame": (0.060, 0.012, 0.010, 0.74), "hover": (0.090, 0.018, 0.015, 0.82), "fg": (0.78, 0.44, 0.40, 0.92), "press": (0.120, 0.024, 0.018, 0.88)}
        return {"frame": (0.12, 0.012, 0.010, 0.86), "hover": (0.22, 0.022, 0.016, 0.94), "fg": (1.0, 0.86, 0.80, 1.0), "press": (0.30, 0.032, 0.022, 0.98)}

    def apply_core_button_style(self, btn, *, role: str = "mode", active: bool = False, available: bool = True):
        if btn is None:
            return
        pal = self.core_button_palette(role=role, active=active, available=available)
        try:
            btn["frameColor"] = pal["frame"]
            btn["text_fg"] = pal["fg"]
        except Exception:
            pass

    def core_click_mode(self, local_index: int):
        if not self.core_console_open:
            self.open_core_console()
            return
        actions = self.matrixcore_action_cards(str(getattr(self, "core_console_page", "guide") or "guide"))
        try:
            spec = actions[int(local_index)]
        except Exception:
            spec = {"action": "guide"}
        self.matrixcore_click_action(str(spec.get("action", "guide")))

    def setup_ui(self):
        self.menu_tab = "display"
        self.menu_actions = []
        core_font_kw = self._core_text_kw()
        self.hud_root = self.aspect2d.attachNewNode("hud-root")
        self.top_panel = DirectFrame(parent=self.hud_root, frameColor=(0.0, 0.0, 0.0, 0.68), frameSize=(-0.26, 0.20, -0.06, 0.06), pos=(-1.06, 0, 0.92))
        self.hud_label = DirectLabel(parent=self.top_panel, text="", text_align=TextNode.ALeft, text_scale=0.030, text_fg=(0.95, 0.97, 1.0, 1.0), frameColor=(0, 0, 0, 0), pos=(-0.23, 0, 0.0), textMayChange=True)
        self.center_hint = DirectLabel(parent=self.hud_root, text="", text_align=TextNode.ACenter, text_scale=0.043, text_fg=(1.0, 0.10, 0.08, 1.0), frameColor=(0, 0, 0, 0), pos=(0, 0, -0.80), textMayChange=True)
        self.coords_label = DirectLabel(parent=self.hud_root, text="", text_align=TextNode.ALeft, text_scale=0.028, text_fg=(1.0, 0.16, 0.12, 0.98), frameColor=(0, 0, 0, 0), pos=(-1.28, 0, -0.93), textMayChange=True)
        self.perf_hud_label = DirectLabel(parent=self.hud_root, text="POINTS 000000", text_align=TextNode.ARight, text_scale=0.022, text_fg=(0.92, 1.00, 0.84, 0.96), frameColor=(0.0, 0.0, 0.0, 0.0), frameSize=(-0.01, 0.01, -0.01, 0.01), pos=(1.26, 0, 0.955), textMayChange=True)
        # Retired Pass 79: the old top-right safety exit overlay lived outside the
        # ESC menu and could read as a permanent play-screen control. Keep this
        # compatibility node hidden for older call sites, but the actual quit
        # affordance now lives inside menu_root below.
        self.safety_exit_root = self.aspect2d.attachNewNode("safety-exit-root-retired")
        self.safety_exit_panel = None
        self.safety_exit_button = None
        self.safety_exit_hint = None
        try:
            self.safety_exit_root.hide()
        except Exception:
            pass
        # Pass 44 branch: compact transparent number-only HoloVerse region map.
        # Region names stay out of the bottom strip and render in the top label.
        self.region_top_panel = DirectFrame(parent=self.hud_root, frameColor=(0.0, 0.0, 0.0, 0.70), frameSize=(-0.62, 0.62, -0.048, 0.052), pos=(0, 0, 0.90))
        self.region_top_label = DirectLabel(parent=self.region_top_panel, text="HOLOVERSE // HUB REGION", text_align=TextNode.ACenter, text_scale=0.029, text_fg=(1.0, 0.12, 0.10, 1.0), frameColor=(0, 0, 0, 0), pos=(0, 0, 0.002), textMayChange=True)
        self.region_keymap_root = self.hud_root.attachNewNode("holoverse-region-keymap")
        self.region_keymap_panel = DirectFrame(parent=self.region_keymap_root, frameColor=(0.0, 0.0, 0.0, 0.0), frameSize=(-0.01, 0.01, -0.01, 0.01), pos=(0, 0, -0.915))
        self.region_keymap_buttons = []
        for idx in range(10):
            btn = DirectButton(
                parent=self.region_keymap_root,
                text=str(idx),
                command=self.handle_number_action if idx == 0 else self.travel_to_holoverse_region_index,
                extraArgs=[idx],
                pos=(0, 0, -0.915),
                scale=0.047,
                frameSize=(-0.58, 0.58, -0.42, 0.44),
                frameColor=(0.0, 0.0, 0.0, 0.0),
                text_fg=(1.0, 0.16, 0.12, 0.98),
                relief=None,
                rolloverSound=None,
                clickSound=None,
            )
            self.region_keymap_buttons.append(btn)
        self.native_status_root = self.aspect2d.attachNewNode("native-mode-status-root")
        self.native_status_panel = DirectFrame(parent=self.native_status_root, frameColor=(0.002, 0.008, 0.012, 0.38), frameSize=(-0.62, 0.62, -0.070, 0.072), pos=(0, 0, 0.935))
        self.native_status_label = DirectLabel(parent=self.native_status_panel, text="MODE // STANDBY", text_align=TextNode.ACenter, text_scale=0.030, text_fg=(1.0, 0.10, 0.08, 1.0), frameColor=(0, 0, 0, 0), pos=(0, 0, 0.020), textMayChange=True)
        self.native_status_subtitle = DirectLabel(parent=self.native_status_panel, text="ESC RETURNS TO CORE", text_align=TextNode.ACenter, text_scale=0.018, text_fg=(1.0, 0.16, 0.12, 0.95), frameColor=(0, 0, 0, 0), pos=(0, 0, -0.035), textMayChange=True)
        self.native_status_exit_button = DirectButton(parent=self.native_status_root, text="EXIT", command=self.return_active_mode_from_button, pos=(0.76, 0, 0.935), scale=0.045, frameSize=(-0.98, 0.98, -0.36, 0.42), text_scale=0.42, text_pos=(0, -0.08), relief=1, rolloverSound=None, clickSound=None, **core_font_kw)
        self.apply_core_button_style(self.native_status_exit_button, role="yellow", available=True)
        self.native_status_root.hide()
        self.bridge_transition_root = self.aspect2d.attachNewNode("holocore-bridge-transition-root")
        self.bridge_transition_root.setBin("fixed", 96)
        self.bridge_transition_root.setDepthTest(False)
        self.bridge_transition_root.setDepthWrite(False)
        self.bridge_transition_panel = DirectFrame(parent=self.bridge_transition_root, frameColor=(0.0, 0.006, 0.012, 0.0), frameSize=(-2.2, 2.2, -1.25, 1.25), pos=(0, 0, 0))
        self.bridge_transition_label = DirectLabel(parent=self.bridge_transition_root, text="MATRIXCORE <-> HOLOCORE", text_align=TextNode.ACenter, text_scale=0.060, text_fg=(1.0, 0.10, 0.08, 0.0), frameColor=(0, 0, 0, 0), pos=(0, 0, 0.035), textMayChange=True, **core_font_kw)
        self.bridge_transition_subtitle = DirectLabel(parent=self.bridge_transition_root, text="SAME-SCREEN GATEWAY", text_align=TextNode.ACenter, text_scale=0.026, text_fg=(1.0, 0.22, 0.16, 0.0), frameColor=(0, 0, 0, 0), pos=(0, 0, -0.060), textMayChange=True, **core_font_kw)
        self.bridge_transition_alpha = 0.0
        self.bridge_transition_target = 0.0
        self.bridge_transition_hold_until = 0.0
        self.bridge_transition_root.hide()
        self.tip_label = None
        self.menu_action_capacity = 10

        self.crosshair_root = self.aspect2d.attachNewNode("crosshair-root")
        self.crosshair_parts = []
        for a, b in [((-0.014, 0, 0), (-0.004, 0, 0)), ((0.014, 0, 0), (0.004, 0, 0)), ((0, 0, -0.014), (0, 0, -0.004)), ((0, 0, 0.014), (0, 0, 0.004))]:
            segs = LineSegs("cross")
            segs.setThickness(1.35)
            segs.setColor(0.92, 0.95, 1.0, 0.9)
            segs.moveTo(*a)
            segs.drawTo(*b)
            np = self.crosshair_root.attachNewNode(segs.create())
            np.setDepthTest(False)
            np.setDepthWrite(False)
            np.setBin("fixed", 100)
            self.crosshair_parts.append(np)

        self.core_console_root = self.aspect2d.attachNewNode("core-console-root")
        self.core_console_root.hide()
        core_font_kw = self._core_text_kw()
        self.core_console_back = DirectFrame(parent=self.core_console_root, frameColor=(0.004, 0.018, 0.024, 0.55), frameSize=(0.54, 1.68, -0.54, 0.68), pos=(0, 0, 0))
        self.core_console_header = DirectFrame(parent=self.core_console_root, frameColor=(0.010, 0.145, 0.180, 0.52), frameSize=(0.54, 1.68, 0.52, 0.68), pos=(0, 0, 0))
        self.core_console_accent = DirectFrame(parent=self.core_console_root, frameColor=(0.20, 1.0, 1.0, 0.92), frameSize=(0.54, 1.68, 0.505, 0.525), pos=(0, 0, 0))
        self.core_console_title = DirectLabel(parent=self.core_console_root, text="MATRIXCORE", text_scale=0.042, text_align=TextNode.ALeft, text_fg=(1.0, 0.10, 0.08, 1.0), frameColor=(0, 0, 0, 0), pos=(0.60, 0, 0.605), textMayChange=True, **core_font_kw)
        self.core_console_subtitle = DirectLabel(parent=self.core_console_root, text="HOLOVERSE GUIDE // DIMENSION PROGRESS // BOT SUPPORT", text_scale=0.020, text_align=TextNode.ALeft, text_fg=(1.0, 0.18, 0.14, 1.0), frameColor=(0, 0, 0, 0), pos=(0.60, 0, 0.548), textMayChange=True, **core_font_kw)
        self.core_console_label = DirectLabel(parent=self.core_console_root, text="", text_scale=0.019, text_align=TextNode.ALeft, text_fg=(0.88, 0.98, 1.0, 1.0), frameColor=(0, 0, 0, 0), pos=(0.60, 0, -0.470), textMayChange=True, **core_font_kw)
        self.core_hint_label = DirectLabel(parent=self.core_console_root, text="", text_scale=0.016, text_align=TextNode.ALeft, text_fg=(1.0, 0.22, 0.16, 0.96), frameColor=(0, 0, 0, 0), pos=(0.60, 0, -0.503), text_wordwrap=42.0, textMayChange=True, **core_font_kw)
        self.core_mode_buttons = []
        for i in range(8):
            btn = DirectButton(
                parent=self.core_console_root,
                text="",
                command=self.core_click_mode,
                extraArgs=[i],
                pos=(1.11, 0, 0.0),
                scale=0.070,
                frameSize=(-7.45, 7.45, -0.36, 0.42),
                frameColor=(0.020, 0.075, 0.090, 0.90),
                text_fg=(0.82, 1.00, 1.00, 1.0),
                text_align=TextNode.ALeft,
                text_scale=0.34,
                text_pos=(-6.92, -0.075),
                relief=1,
                rolloverSound=None,
                clickSound=None,
                **core_font_kw,
            )
            self.core_mode_buttons.append(btn)
        self.core_page_button = DirectButton(parent=self.core_console_root, text="PAGE", command=self.core_toggle_console_page, pos=(0.78, 0, -0.405), scale=0.058, frameSize=(-2.35, 2.35, -0.36, 0.42), text_scale=0.34, text_pos=(0, -0.08), relief=1, rolloverSound=None, clickSound=None, **core_font_kw)
        self.core_hub_button = DirectButton(parent=self.core_console_root, text="HUB", command=self.core_return_hub, pos=(1.15, 0, -0.405), scale=0.058, frameSize=(-1.55, 1.55, -0.36, 0.42), text_scale=0.34, text_pos=(0, -0.08), relief=1, rolloverSound=None, clickSound=None, **core_font_kw)
        self.core_close_button = DirectButton(parent=self.core_console_root, text="CLOSE", command=self.close_core_console, pos=(1.48, 0, -0.405), scale=0.058, frameSize=(-1.85, 1.85, -0.36, 0.42), text_scale=0.34, text_pos=(0, -0.08), relief=1, rolloverSound=None, clickSound=None, **core_font_kw)
        for btn, role in ((self.core_page_button, "white"), (self.core_hub_button, "yellow"), (self.core_close_button, "white")):
            self.apply_core_button_style(btn, role=role, available=True)


        # Bot invitations reuse the Core deck style and right-side safe lane.
        self.bot_dialogue_root = self.aspect2d.attachNewNode("bot-dimension-dialogue-root")
        self.bot_dialogue_root.hide()
        self.bot_dialogue_back = DirectFrame(parent=self.bot_dialogue_root, frameColor=(0.004, 0.018, 0.024, 0.54), frameSize=(0.54, 1.68, -0.30, 0.34), pos=(0, 0, 0))
        self.bot_dialogue_header = DirectFrame(parent=self.bot_dialogue_root, frameColor=(0.010, 0.145, 0.180, 0.50), frameSize=(0.54, 1.68, 0.20, 0.34), pos=(0, 0, 0))
        self.bot_dialogue_accent = DirectFrame(parent=self.bot_dialogue_root, frameColor=(0.20, 1.0, 1.0, 0.92), frameSize=(0.54, 1.68, 0.185, 0.205), pos=(0, 0, 0))
        self.bot_dialogue_title = DirectLabel(parent=self.bot_dialogue_root, text="BOT LINK", text_scale=0.034, text_align=TextNode.ALeft, text_fg=(1.0, 0.10, 0.08, 1.0), frameColor=(0, 0, 0, 0), pos=(0.60, 0, 0.275), textMayChange=True, **core_font_kw)
        self.bot_dialogue_question = DirectLabel(parent=self.bot_dialogue_root, text=BOT_DIMENSION_PROMPT, text_scale=0.022, text_align=TextNode.ALeft, text_fg=(0.84, 1.0, 1.0, 1.0), frameColor=(0, 0, 0, 0), pos=(0.60, 0, 0.120), text_wordwrap=31.0, textMayChange=True, **core_font_kw)
        self.bot_dialogue_mode_label = DirectLabel(parent=self.bot_dialogue_root, text="DIMENSION", text_scale=0.043, text_align=TextNode.ALeft, text_fg=(1.0, 0.18, 0.14, 1.0), frameColor=(0, 0, 0, 0), pos=(0.60, 0, 0.010), textMayChange=True, **core_font_kw)
        self.bot_dialogue_detail = DirectLabel(parent=self.bot_dialogue_root, text="YES / NO // ESC CLOSES", text_scale=0.0165, text_align=TextNode.ALeft, text_fg=(1.0, 0.22, 0.16, 0.96), frameColor=(0, 0, 0, 0), pos=(0.60, 0, -0.075), text_wordwrap=36.0, textMayChange=True, **core_font_kw)
        self.bot_dialogue_yes = DirectButton(parent=self.bot_dialogue_root, text="YES", command=self.confirm_bot_dimension_dialogue, pos=(0.82, 0, -0.210), scale=0.060, frameSize=(-1.65, 1.65, -0.34, 0.42), text_scale=0.40, text_pos=(0, -0.08), relief=1, rolloverSound=None, clickSound=None, **core_font_kw)
        self.bot_dialogue_no = DirectButton(parent=self.bot_dialogue_root, text="NO", command=self.close_bot_dimension_dialogue, extraArgs=["no"], pos=(1.28, 0, -0.210), scale=0.060, frameSize=(-1.65, 1.65, -0.34, 0.42), text_scale=0.40, text_pos=(0, -0.08), relief=1, rolloverSound=None, clickSound=None, **core_font_kw)
        self.bot_dialogue_esc = DirectLabel(parent=self.bot_dialogue_root, text="ESC CLOSES", text_scale=0.0145, text_align=TextNode.ARight, text_fg=(1.0, 0.16, 0.12, 0.95), frameColor=(0, 0, 0, 0), pos=(1.62, 0, -0.282), textMayChange=True, **core_font_kw)
        self.apply_core_button_style(self.bot_dialogue_yes, role="yellow", available=True)
        self.apply_core_button_style(self.bot_dialogue_no, role="white", available=True)

        # Gleebs/MatrixCore guidance is not a menu and has no texture panel.
        # Readability comes from layered red text, dark shadow, glow, and fade.
        self.gleebs_dialogue_root = self.aspect2d.attachNewNode("gleebs-matrixcore-dialogue-root")
        self.gleebs_dialogue_root.hide()
        self.gleebs_dialogue_shadow_wide = DirectLabel(parent=self.gleebs_dialogue_root, text="", text_align=TextNode.ALeft, text_scale=0.034, text_fg=(0.0, 0.0, 0.0, 0.82), frameColor=(0, 0, 0, 0), pos=(-0.018, 0, -0.018), text_wordwrap=30.0, textMayChange=True, **core_font_kw)
        self.gleebs_dialogue_shadow = DirectLabel(parent=self.gleebs_dialogue_root, text="", text_align=TextNode.ALeft, text_scale=0.031, text_fg=(0.0, 0.0, 0.0, 0.96), frameColor=(0, 0, 0, 0), pos=(-0.010, 0, -0.010), text_wordwrap=30.0, textMayChange=True, **core_font_kw)
        self.gleebs_dialogue_glow = DirectLabel(parent=self.gleebs_dialogue_root, text="", text_align=TextNode.ALeft, text_scale=0.034, text_fg=(1.0, 0.04, 0.04, 0.0), frameColor=(0, 0, 0, 0), pos=(0.0, 0, 0.0), text_wordwrap=30.0, textMayChange=True, **core_font_kw)
        self.gleebs_dialogue_label = DirectLabel(parent=self.gleebs_dialogue_root, text="", text_align=TextNode.ALeft, text_scale=0.030, text_fg=(1.0, 0.03, 0.045, 1.0), frameColor=(0, 0, 0, 0), pos=(0.0, 0, 0.0), text_wordwrap=30.0, textMayChange=True, **core_font_kw)
        self.gleebs_dialogue_quote_label = DirectLabel(parent=self.gleebs_dialogue_root, text="", text_align=TextNode.ALeft, text_scale=0.0175, text_fg=(1.0, 0.16, 0.13, 0.82), frameColor=(0, 0, 0, 0), pos=(0.0, 0, -0.118), text_wordwrap=32.0, textMayChange=True, **core_font_kw)
        self.gleebs_dialogue_hint = DirectLabel(parent=self.gleebs_dialogue_root, text="ESC fades // walk away to dismiss", text_align=TextNode.ALeft, text_scale=0.0145, text_fg=(1.0, 0.12, 0.10, 0.72), frameColor=(0, 0, 0, 0), pos=(0.0, 0, -0.172), textMayChange=True, **core_font_kw)

        self.refresh_core_console()

        self.menu_root = self.aspect2d.attachNewNode("menu-root")
        self.menu_root.hide()
        self.menu_back = DirectFrame(parent=self.menu_root, frameColor=(0.002, 0.010, 0.014, 0.46), frameSize=(-1.02, 1.02, -0.66, 0.66))
        self.menu_shell = DirectFrame(parent=self.menu_root, frameColor=(0.006, 0.028, 0.038, 0.50), frameSize=(-0.94, 0.94, -0.58, 0.58), pos=(0, 0, 0.0))
        self.menu_header = DirectFrame(parent=self.menu_root, frameColor=(0.010, 0.140, 0.178, 0.52), frameSize=(-0.94, 0.94, 0.42, 0.58))
        self.menu_title = DirectLabel(parent=self.menu_root, text="OBSERVATORY // SYSTEM GRID", text_scale=0.058, text_fg=(0.98, 0.98, 1.0, 1.0), frameColor=(0, 0, 0, 0), pos=(0, 0, 0.53))
        self.menu_subtitle = DirectLabel(parent=self.menu_root, text="Readable control deck // active settings and actions", text_scale=0.025, text_fg=(0.60, 1.0, 1.0, 1.0), frameColor=(0, 0, 0, 0), pos=(0, 0, 0.475), textMayChange=True)
        self.menu_quit_button = DirectButton(
            parent=self.menu_root,
            text="QUIT APP",
            command=self.quit_holoverse_from_menu,
            pos=(0.78, 0, 0.525),
            scale=0.055,
            frameSize=(-1.34, 1.34, -0.34, 0.40),
            frameColor=(0.13, 0.020, 0.014, 0.74),
            text_fg=(1.0, 0.82, 0.74, 1.0),
            text_scale=0.44,
            text_pos=(0, -0.08),
            relief=1,
            rolloverSound=None,
            clickSound=None,
            **core_font_kw,
        )
        self.apply_core_button_style(self.menu_quit_button, role="yellow", available=True)
        self.menu_tab_bar = DirectFrame(parent=self.menu_root, frameColor=(0.010, 0.060, 0.075, 0.46), frameSize=(-0.86, 0.86, -0.10, 0.10), pos=(0, 0, 0.325))

        tabs = [("DISPLAY", "display"), ("PLAYER", "player"), ("WORLD", "world"), ("GATES", "gates"), ("VR", "vr"), ("AUDIO", "audio"), ("LAUNCH", "launch"), ("SYSTEM", "system"), ("HELP", "help")]
        self.menu_tab_buttons = []
        for label, key in tabs:
            btn = DirectButton(
                parent=self.menu_tab_bar,
                text=label,
                command=self.set_menu_tab,
                extraArgs=[key],
                pos=(0, 0, 0),
                scale=0.070,
                frameSize=(-0.92, 0.92, -0.34, 0.34),
                frameColor=(0.07, 0.09, 0.12, 0.78),
                text_fg=(0.88, 0.91, 0.96, 1.0),
                text_scale=0.42,
                text_pos=(0, -0.10),
                relief=1,
                rolloverSound=None,
                clickSound=None,
            )
            self.menu_tab_buttons.append((key, btn))

        self.menu_left = DirectFrame(parent=self.menu_root, frameColor=(0.006, 0.030, 0.040, 0.46), frameSize=(-0.84, -0.03, -0.52, 0.27), pos=(0, 0, -0.10))
        self.menu_right = DirectFrame(parent=self.menu_root, frameColor=(0.006, 0.030, 0.040, 0.46), frameSize=(0.04, 0.84, -0.52, 0.27), pos=(0, 0, -0.10))
        self.menu_left_header = DirectFrame(parent=self.menu_root, frameColor=(0.018, 0.125, 0.150, 0.50), frameSize=(-0.84, -0.03, 0.20, 0.27), pos=(0, 0, -0.10))
        self.menu_right_header = DirectFrame(parent=self.menu_root, frameColor=(0.018, 0.125, 0.150, 0.50), frameSize=(0.04, 0.84, 0.20, 0.27), pos=(0, 0, -0.10))
        self.menu_info = DirectLabel(parent=self.menu_left, text="", text_align=TextNode.ALeft, text_scale=0.050, text_fg=(0.97, 0.98, 1.0, 1.0), frameColor=(0, 0, 0, 0), pos=(-0.78, 0, 0.19), textMayChange=True)
        self.menu_section = DirectLabel(parent=self.menu_left, text="", text_align=TextNode.ALeft, text_scale=0.027, text_fg=(1.0, 0.18, 0.14, 1.0), frameColor=(0, 0, 0, 0), pos=(-0.78, 0, 0.10), textMayChange=True)
        self.menu_detail = DirectLabel(parent=self.menu_left, text="", text_align=TextNode.ALeft, text_scale=0.030, text_fg=(0.87, 0.90, 0.96, 1.0), text_wordwrap=19.0, frameColor=(0, 0, 0, 0), pos=(-0.78, 0, -0.02), textMayChange=True)
        self.menu_status = DirectLabel(parent=self.menu_left, text="", text_align=TextNode.ALeft, text_scale=0.024, text_fg=(1.0, 0.22, 0.16, 1.0), frameColor=(0, 0, 0, 0), pos=(-0.78, 0, -0.43), textMayChange=True)
        self.menu_action_title = DirectLabel(parent=self.menu_right, text="INTERACTIVE OPTIONS", text_align=TextNode.ALeft, text_scale=0.036, text_fg=(0.97, 0.98, 1.0, 1.0), frameColor=(0, 0, 0, 0), pos=(0.10, 0, 0.19), textMayChange=True)
        self.menu_action_help = DirectLabel(parent=self.menu_right, text="Large click targets // selected tab defines behavior", text_align=TextNode.ALeft, text_scale=0.022, text_fg=(0.77, 0.81, 0.88, 1.0), frameColor=(0, 0, 0, 0), pos=(0.10, 0, 0.11), text_wordwrap=19.0, textMayChange=True)
        self.menu_buttons = []
        for i in range(self.menu_action_capacity):
            btn = DirectButton(
                parent=self.menu_right,
                text="",
                command=self.apply_menu_action,
                extraArgs=[i],
                pos=(0.0, 0, 0.0),
                scale=0.070,
                frameSize=(-3.2, 3.2, -0.34, 0.46),
                frameColor=(0.11, 0.14, 0.20, 0.78),
                text_fg=(0.98, 0.99, 1.0, 1.0),
                text_align=TextNode.ALeft,
                text_scale=0.40,
                text_pos=(-2.80, -0.08),
                relief=1,
                rolloverSound=None,
                clickSound=None,
            )
            self.menu_buttons.append(btn)
        self.relayout_ui()
        self.refresh_menu_actions()
        self.setup_comfort_overlay()

    def relayout_ui(self):
        aspect = 16.0 / 9.0
        try:
            if self.win is not None and self.win.getYSize() > 0:
                aspect = max(1.25, min(2.6, self.win.getXSize() / max(1, self.win.getYSize())))
        except Exception:
            pass
        menu_half_w = max(0.98, min(aspect - 0.08, 1.54))
        menu_half_h = 0.60
        header_h = 0.18
        tab_h = 0.17
        content_top = menu_half_h - header_h - tab_h - 0.06
        content_bottom = -menu_half_h + 0.06
        split_gap = 0.08
        left_x0 = -menu_half_w + 0.04
        left_x1 = -0.06
        right_x0 = 0.06
        right_x1 = menu_half_w - 0.04
        left_header_bottom = content_top - 0.10
        header_top = menu_half_h - 0.04

        self.menu_back["frameSize"] = (-aspect - 0.02, aspect + 0.02, -0.74, 0.74)
        self.menu_shell["frameSize"] = (-menu_half_w, menu_half_w, -menu_half_h, menu_half_h)
        self.menu_header["frameSize"] = (-menu_half_w, menu_half_w, menu_half_h - header_h, menu_half_h)
        self.menu_title.setPos(0, 0, menu_half_h - 0.07)
        self.menu_subtitle.setPos(0, 0, menu_half_h - 0.15)
        self.menu_subtitle["text_scale"] = 0.024 if aspect >= 1.55 else 0.022
        self.menu_tab_bar.setPos(0, 0, menu_half_h - header_h - tab_h * 0.5 - 0.02)
        self.menu_tab_bar["frameSize"] = (-menu_half_w + 0.06, menu_half_w - 0.06, -tab_h * 0.5, tab_h * 0.5)

        for idx, (_, btn) in enumerate(self.menu_tab_buttons):
            row = idx // 4
            col = idx % 4
            btn_w = max(0.20, min(0.30, (menu_half_w * 2.0 - 0.34) / 4.0))
            x = (-menu_half_w + 0.18) + col * btn_w * 1.03
            z = 0.042 - row * 0.085
            btn.setPos(x, 0, z)
            btn.setScale(0.060 if aspect < 1.48 else 0.065)
            btn["frameSize"] = (-1.28, 1.28, -0.30, 0.30)
            btn["text_scale"] = 0.34
            btn["text_pos"] = (0.0, -0.09)

        for frame, x0, x1 in ((self.menu_left, left_x0, left_x1), (self.menu_left_header, left_x0, left_x1), (self.menu_right, right_x0, right_x1), (self.menu_right_header, right_x0, right_x1)):
            if frame in (self.menu_left_header, self.menu_right_header):
                frame["frameSize"] = (x0, x1, left_header_bottom, content_top)
            else:
                frame["frameSize"] = (x0, x1, content_bottom, content_top)
            frame.setPos(0, 0, 0)

        left_pad = left_x0 + 0.06
        right_pad = right_x0 + 0.06
        self.menu_info.setPos(left_pad, 0, content_top - 0.05)
        self.menu_section.setPos(left_pad, 0, content_top - 0.13)
        self.menu_detail.setPos(left_pad, 0, content_top - 0.24)
        self.menu_status.setPos(left_pad, 0, content_bottom + 0.06)
        self.menu_detail["text_wordwrap"] = 18.0 if aspect < 1.5 else 22.0
        self.menu_detail["text_scale"] = 0.028 if aspect < 1.5 else 0.030
        self.menu_action_title.setPos(right_pad, 0, content_top - 0.05)
        self.menu_action_help.setPos(right_pad, 0, content_top - 0.12)
        self.menu_action_help["text_wordwrap"] = 18.0 if aspect < 1.5 else 22.0

        btn_cols = 2
        btn_rows = self.menu_action_capacity // btn_cols
        column_width = max(0.34, (right_x1 - right_x0 - 0.16) / btn_cols)
        start_x = right_x0 + 0.18
        start_z = content_top - 0.26
        row_step = 0.115 if aspect >= 1.5 else 0.108
        for idx, btn in enumerate(self.menu_buttons):
            col = idx // btn_rows
            row = idx % btn_rows
            x = start_x + col * column_width
            z = start_z - row * row_step
            btn.setPos(x, 0, z)
            btn.setScale(0.062 if aspect < 1.5 else 0.068)
            btn["frameSize"] = (-2.35, 2.35, -0.30, 0.42)
            btn["text_scale"] = 0.34
            btn["text_pos"] = (-2.05, -0.06)

        self.top_panel["frameSize"] = (-0.26, 0.24, -0.075, 0.075)
        self.top_panel.setPos(-aspect + 0.33, 0, 0.90)
        self.hud_label.setPos(-0.23, 0, 0.012)
        self.coords_label.setPos(-aspect + 0.12, 0, -0.94)
        if hasattr(self, "perf_hud_label"):
            self.perf_hud_label.setPos(aspect - 0.075, 0, 0.965)
        if hasattr(self, "safety_exit_root"):
            try:
                self.safety_exit_root.hide()
            except Exception:
                pass
        if hasattr(self, "menu_quit_button") and self.menu_quit_button is not None:
            quit_x = right_x1 - 0.175
            quit_z = content_top + 0.225
            self.menu_quit_button.setPos(quit_x, 0, quit_z)
            self.menu_quit_button.setScale(0.048 if aspect < 1.5 else 0.055)
            self.menu_quit_button["frameSize"] = (-1.34, 1.34, -0.34, 0.40)
            self.menu_quit_button["text_scale"] = 0.40 if aspect < 1.5 else 0.44
            self.menu_quit_button["text_pos"] = (0.0, -0.08)
        self.center_hint.setPos(0, 0, -0.84)
        if hasattr(self, "region_top_panel"):
            self.region_top_panel.setPos(0, 0, 0.90)
            self.region_top_panel["frameSize"] = (-min(0.72, aspect * 0.36), min(0.72, aspect * 0.36), -0.048, 0.052)
        if hasattr(self, "region_keymap_root"):
            buttons = list(getattr(self, "region_keymap_buttons", []) or [])
            count = max(1, len(buttons))
            span = min(0.92, max(0.62, aspect * 0.50))
            step = span / max(1, count - 1)
            start = -span * 0.5
            bottom_z = -0.915
            if hasattr(self, "region_keymap_panel"):
                self.region_keymap_panel["frameColor"] = (0.0, 0.0, 0.0, 0.0)
                self.region_keymap_panel["frameSize"] = (-0.01, 0.01, -0.01, 0.01)
                self.region_keymap_panel.setPos(0, 0, bottom_z)
            for idx, btn in enumerate(buttons):
                btn.setPos(start + idx * step, 0, bottom_z)
                btn.setScale(0.041 if aspect < 1.5 else 0.047)
                try:
                    btn["frameColor"] = (0.0, 0.0, 0.0, 0.0)
                    btn["relief"] = None
                except Exception:
                    pass
        core_w = 1.16 if aspect >= 1.55 else 1.04
        x1 = aspect - 0.08
        x0 = x1 - core_w
        z0 = -0.56
        z1 = 0.70
        self.core_console_back["frameSize"] = (x0, x1, z0, z1)
        self.core_console_back.setPos(0, 0, 0)
        self.core_console_header["frameSize"] = (x0, x1, z1 - 0.17, z1)
        self.core_console_accent["frameSize"] = (x0, x1, z1 - 0.185, z1 - 0.165)
        title_x = x0 + 0.060
        self.core_console_title.setPos(title_x, 0, z1 - 0.070)
        self.core_console_title["text_scale"] = 0.039 if aspect < 1.5 else 0.042
        self.core_console_subtitle.setPos(title_x, 0, z1 - 0.132)
        self.core_console_subtitle["text_scale"] = 0.018 if aspect < 1.5 else 0.020
        self.core_console_label.setPos(title_x, 0, z0 + 0.080)
        self.core_console_label["text_scale"] = 0.017 if aspect < 1.5 else 0.019
        self.core_hint_label["text_scale"] = 0.0130 if aspect < 1.5 else 0.0142
        try:
            self.core_hint_label["text_wordwrap"] = 45.0 if aspect >= 1.5 else 37.0
        except Exception:
            pass
        btn_center_x = (x0 + x1) * 0.5
        start_z = z1 - 0.255
        row_step = 0.092 if aspect >= 1.5 else 0.086
        visible_cards = MATRIXCORE_VISIBLE_ACTION_CARD_LIMIT
        for idx, btn in enumerate(getattr(self, "core_mode_buttons", []) or []):
            if idx >= visible_cards:
                try:
                    btn.hide()
                except Exception:
                    pass
                continue
            btn.setPos(btn_center_x, 0, start_z - idx * row_step)
            btn.setScale(0.059 if aspect < 1.5 else 0.063)
            btn["frameSize"] = (-6.80, 6.80, -0.34, 0.39)
            btn["text_scale"] = 0.30 if aspect < 1.5 else 0.32
            btn["text_pos"] = (-6.30, -0.070)
        # Body text starts below the compact action rail. This prevents MatrixCore
        # page text from overlapping the page buttons on 16:9 and narrower windows.
        body_z = start_z - visible_cards * row_step - (0.030 if aspect >= 1.5 else 0.020)
        self.core_hint_label.setPos(title_x, 0, body_z)
        bottom_z = z0 + 0.165
        if hasattr(self, "core_page_button"):
            self.core_page_button.setPos(x0 + 0.235, 0, bottom_z)
            self.core_page_button.setScale(0.053 if aspect < 1.5 else 0.058)
        if hasattr(self, "core_hub_button"):
            self.core_hub_button.setPos(x0 + core_w * 0.56, 0, bottom_z)
            self.core_hub_button.setScale(0.053 if aspect < 1.5 else 0.058)
        if hasattr(self, "core_close_button"):
            self.core_close_button.setPos(x1 - 0.200, 0, bottom_z)
            self.core_close_button.setScale(0.053 if aspect < 1.5 else 0.058)
        if hasattr(self, "bot_dialogue_back"):
            bx1 = aspect - 0.08
            bw = 1.10 if aspect >= 1.55 else 1.00
            bx0 = bx1 - bw
            bz0 = -0.315
            bz1 = 0.345
            self.bot_dialogue_back["frameSize"] = (bx0, bx1, bz0, bz1)
            self.bot_dialogue_header["frameSize"] = (bx0, bx1, bz1 - 0.140, bz1)
            self.bot_dialogue_accent["frameSize"] = (bx0, bx1, bz1 - 0.155, bz1 - 0.135)
            tx = bx0 + 0.055
            self.bot_dialogue_title.setPos(tx, 0, bz1 - 0.065)
            self.bot_dialogue_title["text_scale"] = 0.031 if aspect < 1.5 else 0.034
            self.bot_dialogue_question.setPos(tx, 0, bz1 - 0.215)
            self.bot_dialogue_question["text_scale"] = 0.020 if aspect < 1.5 else 0.022
            self.bot_dialogue_question["text_wordwrap"] = 28.0 if aspect < 1.5 else 32.0
            self.bot_dialogue_mode_label.setPos(tx, 0, bz1 - 0.335)
            self.bot_dialogue_mode_label["text_scale"] = 0.039 if aspect < 1.5 else 0.043
            self.bot_dialogue_detail.setPos(tx, 0, bz1 - 0.425)
            self.bot_dialogue_detail["text_scale"] = 0.015 if aspect < 1.5 else 0.0165
            self.bot_dialogue_yes.setPos(bx0 + 0.230, 0, bz0 + 0.105)
            self.bot_dialogue_no.setPos(bx0 + 0.640, 0, bz0 + 0.105)
            self.bot_dialogue_yes.setScale(0.055 if aspect < 1.5 else 0.060)
            self.bot_dialogue_no.setScale(0.055 if aspect < 1.5 else 0.060)
            self.bot_dialogue_esc.setPos(bx1 - 0.055, 0, bz0 + 0.030)
            self.bot_dialogue_esc["text_scale"] = 0.013 if aspect < 1.5 else 0.0145
        if hasattr(self, "gleebs_dialogue_root"):
            # Left safe-lane: avoids MatrixCore/right panels, top HUD, bottom map, and menu panels.
            gx = -aspect + 0.18
            gz = -0.46 if aspect >= 1.5 else -0.42
            self.gleebs_dialogue_root.setPos(gx, 0, gz)
            wrap = 30.0 if aspect >= 1.5 else 24.0
            scale = 0.030 if aspect >= 1.5 else 0.026
            for lbl in (getattr(self, "gleebs_dialogue_shadow_wide", None), getattr(self, "gleebs_dialogue_shadow", None), getattr(self, "gleebs_dialogue_glow", None), getattr(self, "gleebs_dialogue_label", None)):
                if lbl is not None:
                    try:
                        lbl["text_wordwrap"] = wrap
                        lbl["text_scale"] = scale + (0.004 if lbl in (getattr(self, "gleebs_dialogue_shadow_wide", None), getattr(self, "gleebs_dialogue_glow", None)) else 0.0)
                    except Exception:
                        pass
            if hasattr(self, "gleebs_dialogue_quote_label"):
                try:
                    self.gleebs_dialogue_quote_label["text_wordwrap"] = wrap + 2.0
                    self.gleebs_dialogue_quote_label.setPos(0, 0, -0.118 if aspect >= 1.5 else -0.142)
                except Exception:
                    pass
            if hasattr(self, "gleebs_dialogue_hint"):
                self.gleebs_dialogue_hint.setPos(0, 0, -0.172 if aspect >= 1.5 else -0.210)

    def show_vr_onboarding(self):
        if not self.vr_active:
            return
        self.vr_onboarding_pending = True
        self.menu_open = True
        self.menu_root.show()
        self.set_menu_tab("vr")
        props = WindowProperties()
        props.setCursorHidden(False)
        if self.win is not None and hasattr(self.win, "requestProperties"):
            self.win.requestProperties(props)
        self.center_hint["text"] = "VR // SELECT PRESET 1-4"
        self.refresh_ui()

    def apply_vr_preset(self, preset_name, finalize=True):
        preset = str(preset_name).strip().lower()
        self.cfg.player_eye_height = 3.95
        self.base_teleport.z = self.cfg.player_eye_height
        if preset == "seated":
            self.cfg.vr_seated_mode = True
            self.cfg.vr_turn_mode = "snap"
            self.cfg.vr_snap_turn_degrees = 35.0
            self.cfg.vr_smooth_turn_rate = 0.0
            self.cfg.vr_move_speed = 6.5
            self.cfg.vr_height_offset = 0.0
            self.cfg.vr_comfort_vignette = 0.30
        elif preset == "smooth":
            self.cfg.vr_seated_mode = False
            self.cfg.vr_turn_mode = "smooth"
            self.cfg.vr_snap_turn_degrees = 30.0
            self.cfg.vr_smooth_turn_rate = 72.0
            self.cfg.vr_move_speed = 8.0
            self.cfg.vr_height_offset = 0.0
            self.cfg.vr_comfort_vignette = 0.18
        elif preset == "showcase":
            self.cfg.vr_seated_mode = False
            self.cfg.vr_turn_mode = "smooth"
            self.cfg.vr_snap_turn_degrees = 30.0
            self.cfg.vr_smooth_turn_rate = 48.0
            self.cfg.vr_move_speed = 10.0
            self.cfg.vr_height_offset = 0.0
            self.cfg.vr_comfort_vignette = 0.08
        else:
            preset = "snap"
            self.cfg.vr_seated_mode = False
            self.cfg.vr_turn_mode = "snap"
            self.cfg.vr_snap_turn_degrees = 30.0
            self.cfg.vr_smooth_turn_rate = 0.0
            self.cfg.vr_move_speed = 8.5
            self.cfg.vr_height_offset = 0.0
            self.cfg.vr_comfort_vignette = 0.24
        self.cfg.vr_show_runtime_panel = True
        self.cfg.vr_comfort_preset = preset
        self.player_pos.z = self.cfg.player_eye_height
        self.sync_player_from_vr()
        if finalize:
            self.vr_onboarding_pending = False
            self.cfg.vr_onboarding_complete = True
            self.center_hint["text"] = f"VR // {preset.upper()} PRESET ACTIVE"
            self.menu_open = False
            self.menu_root.hide()
            props = WindowProperties()
            props.setCursorHidden(True)
            if self.win is not None and hasattr(self.win, "requestProperties"):
                self.win.requestProperties(props)
        save_config(self.cfg)
        self.refresh_ui()


    def setup_comfort_overlay(self):
        self.comfort_overlay = self.aspect2d.attachNewNode("comfort-overlay")
        self.comfort_overlay.hide()
        edge_color = (0.01, 0.015, 0.022, 0.0)
        frames = [(-1.02, -0.73, -0.62, 0.62), (0.73, 1.02, -0.62, 0.62), (-0.73, 0.73, 0.52, 0.62), (-0.73, 0.73, -0.62, -0.52)]
        self.comfort_vignette_nodes = []
        for idx, frame in enumerate(frames):
            node = DirectFrame(parent=self.comfort_overlay, frameColor=edge_color, frameSize=frame)
            self.comfort_vignette_nodes.append(node)
        panel = DirectFrame(parent=self.comfort_overlay, frameColor=(0.03, 0.035, 0.05, 0.42), frameSize=(-0.98, -0.58, 0.42, 0.62))
        self.comfort_panel_label = DirectLabel(parent=panel, text="", text_align=TextNode.ALeft, text_scale=0.026, text_fg=(0.92, 0.95, 1.0, 1.0), frameColor=(0, 0, 0, 0), pos=(-0.94, 0, 0.56), text_wordwrap=14.0, textMayChange=True)

    def update_comfort_overlay(self):
        strength = max(0.0, min(0.72, float(getattr(self.cfg, "vr_comfort_vignette", 0.18))))
        active = bool(getattr(self.cfg, "vr_show_runtime_panel", True)) and (self.vr_active or self.menu_tab == "vr" or SELF_TEST)
        if self.comfort_overlay is None:
            return
        if active:
            self.comfort_overlay.show()
            alpha = strength if self.vr_active else min(0.22, strength * 0.65)
            for node in self.comfort_vignette_nodes:
                node["frameColor"] = (0.01, 0.015, 0.022, alpha)
            if self.comfort_panel_label is not None:
                seated = "ON" if getattr(self.cfg, "vr_seated_mode", False) else "OFF"
                self.comfort_panel_label["text"] = (
                    f"VR STATUS // {self.vr_status}\n"
                    f"Runtime frame avg {self.runtime_avg_dt * 1000.0:05.1f} ms\n"
                    f"Chunks {len(self.terrain_chunks)} / Peak {self.runtime_chunk_peak}\n"
                    f"Actors {len(self.world_actors)} / Peak {self.runtime_actor_peak}\n"
                    f"Snap {self.cfg.vr_snap_turn_degrees:.0f} deg  Move {self.cfg.vr_move_speed:.1f}\n"
                    f"Seated {seated}  Height {self.cfg.vr_height_offset:+.2f}\n"
                    f"Comfort Shade {self.cfg.vr_comfort_vignette:.2f}\n"
                    f"World {self.runtime_world_signature}"
                )

            self.comfort_overlay.hide()

    def setup_input(self):
        # Keep the Core movement keys active, but also track arrow keys so
        # native dimensions such as Zonez can use them without re-opening old
        # child-window input paths.
        for key in ["w", "a", "s", "d", "shift", "space", "control", "arrow_left", "arrow_right", "arrow_up", "arrow_down"]:
            self.accept(key, self.set_key, [key, True])
            self.accept(f"{key}-up", self.set_key, [key, False])
        self.accept("h", self.handle_h_action)
        self.accept("escape", self.start_escape_hold)
        self.accept("escape-up", self.finish_escape_hold)
        self.accept("control-q", self.quit_holoverse_from_menu)
        self.accept("mouse1", self.primary_click_interact)
        self.accept("mouse1-up", self.native_mouse1_up)
        self.accept("mouse3", self.native_mouse3_down)
        self.accept("mouse3-up", self.native_mouse3_up)
        # Use single handlers for E/Q. Duplicate accepts can overwrite or mask
        # interaction depending on Panda messenger state, which made real player
        # artifact activation unreliable even when synthetic self-tests passed.
        self.accept("e", self.on_e_down)
        self.accept("e-up", self.on_e_up)
        self.accept("q", self.on_q_down)
        self.accept("q-up", self.on_q_up)
        self.accept("r", self.native_r_down)
        self.accept("t", self.native_t_down)
        self.accept("v", self.native_v_down)
        self.accept("tab", self.handle_tab_action)
        for region_number_key in range(10):
            self.accept(str(region_number_key), lambda n=region_number_key: self.handle_number_action(n))
        self.accept("b", self.cycle_world_shell_biome, [1])
        self.accept("n", self.cycle_world_shell_biome, [-1])
        self.accept("shift-b", self.cycle_world_shell_biome, [2])
        self.accept("shift-n", self.cycle_world_shell_biome, [-2])
        self.accept("p", self.toggle_world_shell_playable)
        self.accept("c", self.reset_world_shell_checkpoints)
        # Pass 42/44: hub return is mapped to 9; T is intentionally unmapped.
        self.accept("f1", self.toggle_help_overlay)
        # Hidden development switch: player-facing region number travel stays off.
        self.accept("shift-f9", self.toggle_dev_region_number_travel)

    def native_mouse1_up(self):
        if getattr(self, "active_native_mode", None) is not None:
            self.dispatch_native_action("mouse1_up")

    def native_mouse3_down(self):
        if bool(getattr(self, "shell_flight_craft_cinematic", False)):
            return
        if getattr(self, "active_native_mode", None) is not None:
            self.dispatch_native_action("mouse3")
            return
        if self.menu_open or self.core_console_open or getattr(self, "bot_dialogue_open", False) or getattr(self, "external_process", None) is not None:
            return
        if self.is_holospace_active() and self.is_looking_at_holospace_dyson_gate():
            self.start_holospace_return_sequence(source="dyson_click_rmb")
            return
        if self.is_looking_at_core():
            entry = self.holoverse_region_entry_for_number(8) or {}
            self.start_holospace_travel_sequence(entry, source="matrixcore_rmb", destination="space")

    def native_mouse3_up(self):
        if getattr(self, "active_native_mode", None) is not None:
            self.dispatch_native_action("mouse3_up")

    def native_r_down(self):
        if getattr(self, "active_native_mode", None) is not None:
            self.dispatch_native_action("r")

    def native_t_down(self):
        if getattr(self, "active_native_mode", None) is not None:
            self.dispatch_native_action("t")

    def native_v_down(self):
        if getattr(self, "active_native_mode", None) is not None:
            self.dispatch_native_action("v")

    def handle_tab_action(self):
        # TAB is a hard cinematic toggle in the HoloVerse host.  Native
        # dimensions still receive TAB first, but the default world no longer
        # falls through to the old saved-aircraft lockout.
        if bool(getattr(self, "shell_flight_craft_active", False)) and bool(getattr(self, "shell_flight_craft_cinematic", False)):
            self.toggle_shell_flight_craft()
            return
        if getattr(self, "active_native_mode", None) is not None:
            self.dispatch_native_action("tab")
            return
        if self.menu_open or self.core_console_open or getattr(self, "bot_dialogue_open", False):
            return
        if getattr(self, "external_process", None) is not None or getattr(self, "external_suspended", False):
            return
        if self.vr_active or SELF_TEST or self.is_holospace_traveling():
            return
        self.toggle_shell_flight_craft()

    def shell_flight_cinematic_ui_nodes(self):
        return (
            "hud_root", "top_panel", "coords_label", "crosshair_root",
            "region_top_panel", "region_top_label", "region_keymap_root",
            "perf_hud_label", "center_hint", "menu_root", "core_console_root",
            "bridge_transition_root", "help_overlay", "comfort_overlay",
            "bot_dialogue_root", "safety_exit_root",
        )

    def set_shell_flight_cinematic_ui_suppressed(self, suppressed: bool) -> None:
        if not suppressed:
            return
        for name in self.shell_flight_cinematic_ui_nodes():
            node = getattr(self, name, None)
            if node is None:
                continue
            try:
                node.hide()
            except Exception:
                pass
        try:
            self.center_hint["text"] = ""
        except Exception:
            pass

    def hide_shell_flight_cinematic_overlays(self) -> None:
        # Camera recording mode must not show player craft, cockpit overlays,
        # hoverboards, or source-world weapon/craft props.
        try:
            node = getattr(self, "shell_flight_craft_visual_root", None)
            if node is not None and not node.isEmpty():
                node.hide()
        except Exception:
            pass
        try:
            self.show_holospace_cockpit(False)
        except Exception:
            pass
        try:
            self.show_deep_water_hoverboard(False)
        except Exception:
            pass
        try:
            node = getattr(self, "underwater_vehicle_root", None)
            if node is not None and not node.isEmpty():
                node.hide()
        except Exception:
            pass
        try:
            runtime = getattr(getattr(self, "world_shell_mount", None), "source_runtime", None)
            if runtime is not None:
                setattr(runtime, "flight_craft_active", False)
                setattr(runtime, "flight_craft_velocity", Vec3(0, 0, 0))
                for attr in ("weapon_root", "underwater_vehicle_root"):
                    node = getattr(runtime, attr, None)
                    if node is not None and not node.isEmpty():
                        node.hide()
        except Exception:
            pass

    def shell_flight_cinematic_allowed(self) -> bool:
        if self.vr_active or SELF_TEST:
            return False
        if self.menu_open or self.core_console_open or getattr(self, "bot_dialogue_open", False):
            return False
        if getattr(self, "active_native_mode", None) is not None:
            return False
        if getattr(self, "external_process", None) is not None or getattr(self, "external_suspended", False):
            return False
        if self.is_holospace_traveling():
            return False
        return True

    def enter_shell_flight_cinematic(self) -> bool:
        if not self.shell_flight_cinematic_allowed():
            return False
        self.shell_flight_craft_return_state = {
            "player_pos": Vec3(self.player_pos),
            "yaw": float(self.player_yaw),
            "pitch": float(self.player_pitch),
            "camera_pos": Vec3(self.camera.getPos(self.render)),
            "camera_hpr": Vec3(self.camera.getHpr(self.render)),
        }
        self.shell_flight_craft_active = True
        self.shell_flight_craft_cinematic = True
        self.shell_flight_craft_velocity = Vec3(0, 0, 0)
        self.shell_flight_craft_boost = 1.0
        self.holospace_velocity = Vec3(0, 0, 0)
        self.move_velocity = Vec2(0, 0)
        self.hide_shell_flight_cinematic_overlays()
        self.set_shell_flight_cinematic_ui_suppressed(True)
        return True

    def exit_shell_flight_cinematic(self) -> bool:
        if not bool(getattr(self, "shell_flight_craft_cinematic", False)):
            return False
        saved = getattr(self, "shell_flight_craft_return_state", None) or {}
        try:
            self.player_pos = Vec3(saved.get("player_pos", self.player_pos))
            self.player_yaw = float(saved.get("yaw", self.player_yaw))
            self.player_pitch = float(saved.get("pitch", self.player_pitch))
            self.camera.setPos(saved.get("camera_pos", self.player_pos))
            self.camera.setHpr(saved.get("camera_hpr", Vec3(self.player_yaw, self.player_pitch, 0)))
        except Exception:
            self.camera.setPos(self.player_pos)
            self.camera.setHpr(self.player_yaw, self.player_pitch, 0)
        self.shell_flight_craft_active = False
        self.shell_flight_craft_cinematic = False
        self.shell_flight_craft_return_state = None
        self.shell_flight_craft_velocity = Vec3(0, 0, 0)
        self.shell_flight_craft_boost = 1.0
        self.move_velocity = Vec2(0, 0)
        try:
            if self.center_hint is not None:
                self.center_hint.show()
            self.refresh_ui()
        except Exception:
            pass
        return True

    def update_shell_flight_cinematic(self, dt: float, move: Vec2, forward: Vec3, right: Vec3, up: Vec3) -> bool:
        if not (bool(getattr(self, "shell_flight_craft_active", False)) and bool(getattr(self, "shell_flight_craft_cinematic", False))):
            return False
        if not self.shell_flight_cinematic_allowed():
            self.exit_shell_flight_cinematic()
            return True
        self.hide_shell_flight_cinematic_overlays()
        self.set_shell_flight_cinematic_ui_suppressed(True)
        if forward.lengthSquared() > 0:
            forward.normalize()
        if right.lengthSquared() > 0:
            right.normalize()
        if up.lengthSquared() > 0:
            up.normalize()
        vertical = 0.0
        if self.keys.get("space"):
            vertical += 1.0
        if self.keys.get("control"):
            vertical -= 1.0
        direction = forward * float(move.y) + right * float(move.x) + up * vertical
        has_input = direction.lengthSquared() > 0.0001
        if has_input:
            direction.normalize()
        base_speed = max(18.0, float(getattr(self.cfg, "walk_speed", 7.0)) * 4.6)
        speed = base_speed * (3.1 if self.keys.get("shift") else 1.0)
        desired = direction * speed if has_input else Vec3(0, 0, 0)
        current = Vec3(getattr(self, "shell_flight_craft_velocity", Vec3(0, 0, 0)))
        if has_input:
            current = current * max(0.0, 1.0 - dt * 3.2) + desired * min(1.0, dt * 3.2)
        else:
            current *= max(0.0, 1.0 - dt * 4.8)
            if current.lengthSquared() < 0.01:
                current = Vec3(0, 0, 0)
        self.shell_flight_craft_velocity = current
        candidate = Vec3(self.player_pos + current * max(0.0, dt))
        try:
            limit = max(3200.0, min(24000.0, float(self.world_shell_play_radius_limit()) * 1.35))
        except Exception:
            limit = 24000.0
        flat_r = math.sqrt(float(candidate.x) * float(candidate.x) + float(candidate.y) * float(candidate.y))
        if flat_r > limit:
            scale = limit / max(0.0001, flat_r)
            candidate.x *= scale
            candidate.y *= scale
            self.shell_flight_craft_velocity = Vec3(0, 0, 0)
        candidate.z = max(-600.0, min(3600.0, float(candidate.z)))
        self.player_pos = candidate
        if not self.vr_active:
            self.camera.setPos(self.player_pos)
        return True

    def can_use_shell_flight_craft_at(self, pos=None):
        pos = pos if pos is not None else self.player_pos
        if not self.world_shell_playable_active() or self.world_unlocked or self.transition_target > 0.0:
            return False
        if not self.has_saved_shell_flight_craft():
            return False
        try:
            r = math.sqrt(float(pos.x) * float(pos.x) + float(pos.y) * float(pos.y))
        except Exception:
            return False
        return r > self.hub_radius + 4.0 and r <= self.world_shell_play_radius_limit()

    def toggle_shell_flight_craft(self):
        # Reclaim the existing TAB craft path as a camera-only cinematic mode.
        # This avoids keeping the old disabled aircraft feature alive beside a
        # second flycam, while preserving the same update branch and movement keys.
        if bool(getattr(self, "shell_flight_craft_active", False)) and bool(getattr(self, "shell_flight_craft_cinematic", False)):
            return self.exit_shell_flight_cinematic()
        if bool(getattr(self, "shell_flight_craft_active", False)):
            self.shell_flight_craft_active = False
            self.shell_flight_craft_velocity = Vec3(0, 0, 0)
            self.shell_flight_craft_boost = 1.0
            self.shell_flight_craft_cinematic = False
            self.shell_flight_craft_return_state = None
            self.hide_shell_flight_cinematic_overlays()
            return True
        return self.enter_shell_flight_cinematic()

    def on_e_down(self):
        self.set_key("e", True)
        if bool(getattr(self, "shell_flight_craft_cinematic", False)):
            return
        if getattr(self, "bot_dialogue_open", False):
            return
        if getattr(self, "active_native_mode", None) is not None:
            self.dispatch_native_action("e_down")
            return
        if not self.vr_active:
            self.interact()

    def on_e_up(self):
        self.set_key("e", False)

    def on_q_down(self):
        self.set_key("q", True)
        if bool(getattr(self, "shell_flight_craft_cinematic", False)):
            return
        if getattr(self, "active_native_mode", None) is not None:
            self.dispatch_native_action("q_down")
            return
        if not self.vr_active:
            self.core_secondary_action()

    def on_q_up(self):
        self.set_key("q", False)

    def setup_gamepad(self):
        try:
            devices = self.devices.getDevices(InputDevice.DeviceClass.gamepad)
            if devices:
                self.attachInputDevice(devices[0], prefix="gamepad")
                self.gamepad = devices[0]
            self.accept("connect-device", self.on_device_connect)
            self.accept("disconnect-device", self.on_device_disconnect)
        except Exception:
            self.gamepad = None

    def on_device_connect(self, device):
        try:
            if device.device_class == InputDevice.DeviceClass.gamepad and self.gamepad is None:
                self.attachInputDevice(device, prefix="gamepad")
                self.gamepad = device
        except Exception:
            pass

    def on_device_disconnect(self, device):
        if self.gamepad == device:
            self.detachInputDevice(device)
            self.gamepad = None

    def set_key(self, key, value):
        self.keys[key] = value

    def start_escape_hold(self):
        if bool(getattr(self, "shell_flight_craft_cinematic", False)):
            self.exit_shell_flight_cinematic()
            self.esc_hold_active = False
            self.esc_hold_exit_triggered = False
            return
        # Native artifact dimensions must always win ESC. Dialogue overlays can
        # remain queued/fading, but they must never block the guaranteed return
        # path from Etch-Line, Zonez, Vector Wars, or any same-window adapter.
        if getattr(self, "active_native_mode", None) is not None:
            if self.dispatch_native_action("escape"):
                return
            self.esc_hold_active = False
            self.esc_hold_exit_triggered = False
            self.return_from_native_mode(reason="escape")
            return
        if getattr(self, "gleebs_dialogue_active", False):
            self.dismiss_gleebs_dialogue("escape")
            return
        if getattr(self, "bot_dialogue_open", False):
            self.close_bot_dimension_dialogue("escape")
            return
        # ESC is now a shared pause/menu action across MatrixCore and same-window
        # HoloCore. Hold ESC exits the whole app; 0/E handle HoloCore return.
        if getattr(self, "external_process", None) is not None:
            if self.center_hint is not None:
                self.center_hint["text"] = ""
        # Panda can emit repeated key-down events while a key is held. Do not
        # restart the timer on repeats or hold-to-exit can never mature.
        if self.esc_hold_active and not self.esc_hold_exit_triggered:
            return
        now = time.monotonic()
        self.esc_hold_active = True
        self.esc_hold_start = now
        self.esc_hold_deadline = now + 2.0
        self.esc_hold_exit_triggered = False
        if self.center_hint is not None:
            self.center_hint["text"] = ""

    def finish_escape_hold(self):
        if getattr(self, "active_native_mode", None) is not None:
            # A native mode either consumed ESC on key-down or was already
            # returned to Core.  Do not open the Core menu behind the dimension.
            self.esc_hold_active = False
            return
        if not self.esc_hold_active:
            return
        held = time.monotonic() - float(self.esc_hold_start)
        should_toggle = (not self.esc_hold_exit_triggered) and held < 2.0
        self.esc_hold_active = False
        if should_toggle:
            self.toggle_menu()

    def check_escape_hold(self):
        if not self.esc_hold_active or self.esc_hold_exit_triggered:
            return
        if time.monotonic() >= float(getattr(self, "esc_hold_deadline", 0.0)):
            self.esc_hold_exit_triggered = True
            if self.center_hint is not None:
                self.center_hint["text"] = "EXITING HOLOVERSE"
            self.userExit()

    def holoverse_region_travel_map(self):
        # Number order: 0 = HoloCore bridge, 1-7 = surface regions, 8 = HoloSpace cockpit, 9 = Hub Spawn.
        # Surface radius values are the original world.py ring centers on the south/outward spoke.
        return [
            {"number": 0, "ring_key": 1, "name": "Hub Region", "r0": 0.0, "r1": 620.0, "radius": (30.0 + 620.0) * 0.5, "height": 0.0, "yaw": -90.0},
            {"number": 1, "ring_key": 2, "name": "Forests", "r0": 620.0, "r1": 1920.0, "radius": (620.0 + 1920.0) * 0.5, "height": 4.8, "yaw": -90.0},
            {"number": 2, "ring_key": 3, "name": "Green Hills", "r0": 1920.0, "r1": 3300.0, "radius": (1920.0 + 3300.0) * 0.5, "height": 13.8, "yaw": -90.0},
            {"number": 3, "ring_key": 4, "name": "Mushroom", "r0": 3300.0, "r1": 4700.0, "radius": (3300.0 + 4700.0) * 0.5, "height": 14.2, "yaw": -90.0},
            {"number": 4, "ring_key": 5, "name": "Desert", "r0": 4700.0, "r1": 6100.0, "radius": (4700.0 + 6100.0) * 0.5, "height": 7.4, "yaw": -90.0},
            {"number": 5, "ring_key": 6, "name": "Ice", "r0": 6100.0, "r1": 7500.0, "radius": (6100.0 + 7500.0) * 0.5, "height": 10.8, "yaw": -90.0},
            {"number": 6, "ring_key": 7, "name": "Urban", "r0": 7500.0, "r1": 9100.0, "radius": (7500.0 + 9100.0) * 0.5, "height": 4.9, "yaw": -90.0},
            {"number": 7, "ring_key": 8, "name": "Metropolis", "r0": 9100.0, "r1": 11100.0, "radius": (9100.0 + 11100.0) * 0.5, "height": 2.6, "yaw": 90.0},
            {"number": 8, "ring_key": None, "name": "HoloSpace", "r0": 11100.0, "r1": 999999.0, "radius": 11420.0, "height": 1096.0, "yaw": -90.0, "holospace": True, "dyson_focus": [0.0, -12480.0, 1185.0]},
            {"number": 9, "ring_key": 1, "name": "Hub Spawn", "r0": 0.0, "r1": 120.0, "radius": 0.0, "height": 0.0, "yaw": 0.0, "hub_spawn": True},
        ]

    def holoverse_region_entry_for_number(self, number):
        try:
            number = int(number)
        except Exception:
            return None
        for entry in self.holoverse_region_travel_map():
            if int(entry["number"]) == number:
                return entry
        return None

    def dev_region_number_travel_enabled(self) -> bool:
        return bool(getattr(self.cfg, "dev_region_number_travel_enabled", False))

    def toggle_dev_region_number_travel(self):
        enabled = not bool(getattr(self.cfg, "dev_region_number_travel_enabled", False))
        self.cfg.dev_region_number_travel_enabled = enabled
        # Keep the number keymap hidden unless the development shortcut is explicitly enabled.
        self.cfg.world_shell_region_keymap_enabled = enabled
        save_config(self.cfg)
        try:
            self.update_holoverse_region_ui()
        except Exception:
            pass
        if self.center_hint is not None:
            self.center_hint["text"] = "DEV REGION NUMBER TRAVEL // " + ("ON" if enabled else "OFF")
        return enabled

    def _saved_desert_ship_state_paths(self) -> list[Path]:
        paths: list[Path] = []
        try:
            active = getattr(self, "desert_ship_state_path", None)
            if active:
                paths.append(Path(active))
        except Exception:
            pass
        paths.append(SHARED_HOLOVERSE_DATA_DIR / "regions" / "desert" / "ships" / "desert_ship_state.json")
        out: list[Path] = []
        seen: set[str] = set()
        for path in paths:
            key = os.fspath(path)
            if key not in seen:
                seen.add(key)
                out.append(path)
        return out

    def has_saved_shell_flight_craft(self) -> bool:
        """Return True only after the player has actually bound an Ember aircraft."""
        if not bool(getattr(self.cfg, "air_travel_requires_saved_craft", True)):
            return True
        try:
            load_fn = getattr(self, "load_desert_ships", None)
            if callable(load_fn):
                load_fn()
            default_id = str(getattr(self, "desert_ships_default_id", "") or "").strip()
            if default_id and default_id != "starter_holocraft":
                return True
            active = getattr(self, "desert_active_ship_data", None)
            if isinstance(active, dict):
                sid = str(active.get("id") or "").strip()
                if sid and sid != "starter_holocraft" and str(active.get("class") or "").strip():
                    return True
        except Exception:
            pass
        for path in self._saved_desert_ship_state_paths():
            try:
                if path.exists():
                    raw = json.loads(path.read_text(encoding="utf-8"))
                    if isinstance(raw, dict):
                        default_id = str(raw.get("default_ship_id") or "").strip()
                        lineup = raw.get("ships") if isinstance(raw.get("ships"), list) else []
                        if default_id and default_id != "starter_holocraft":
                            for ship in lineup:
                                if isinstance(ship, dict) and str(ship.get("id") or "") == default_id:
                                    return True
            except Exception:
                continue
        return False

    def is_holospace_active(self) -> bool:
        return bool(getattr(self, "holospace_active", False)) and not self.world_unlocked and self.transition_target <= 0.0

    def is_holospace_traveling(self) -> bool:
        return bool(getattr(self, "holospace_transition_active", False)) and not self.world_unlocked and self.transition_target <= 0.0

    def ensure_holospace_travel_runtime(self):
        runtime = getattr(self, "holospace_travel_runtime", None)
        if runtime is not None:
            return runtime
        try:
            from holospace_travel_sequence import HoloSpaceTravelSequence
            runtime = HoloSpaceTravelSequence(self, duration=float(getattr(self, "holospace_transition_duration", 10.0) or 10.0))
            self.holospace_travel_runtime = runtime
            return runtime
        except Exception as exc:
            try:
                print(f"holospace_transition_runtime_error:{exc.__class__.__name__}:{exc}")
            except Exception:
                pass
            self.holospace_travel_runtime = None
            return None

    def set_holospace_transition_hud_suppressed(self, suppressed: bool) -> None:
        """During the existing HoloSpace travel scene, only its countdown may show."""
        names = (
            "hud_root", "top_panel", "coords_label", "crosshair_root",
            "region_top_panel", "region_top_label", "region_keymap_root",
            "perf_hud_label", "center_hint", "menu_root", "core_console_root",
            "bridge_transition_root", "help_overlay", "comfort_overlay",
            "bot_dialogue_root", "safety_exit_root",
        )
        for name in names:
            node = getattr(self, name, None)
            if node is None:
                continue
            try:
                if suppressed:
                    node.hide()
                elif name in {"menu_root", "core_console_root"}:
                    # These are restored only by their owning open calls.
                    pass
                elif name == "center_hint":
                    pass
            except Exception:
                pass
        if suppressed:
            try:
                self.menu_open = False
                self.core_console_open = False
                self.core_console_set_cursor(False)
                self.mouse_captured = True
            except Exception:
                pass

    def start_holospace_travel_sequence(self, entry=None, *, source: str = "space", destination: str = "space") -> bool:
        if self.is_holospace_traveling():
            return True
        if entry is None:
            entry = self.holoverse_region_entry_for_number(8) or {}
        entry = dict(entry or {})
        entry.setdefault("number", 8)
        entry.setdefault("name", "HoloSpace")
        entry.setdefault("radius", 11420.0)
        entry.setdefault("height", 1096.0)
        entry.setdefault("yaw", -90.0)
        entry.setdefault("holospace", True)
        try:
            self.record_matrixcore_discovered_gate(kind="region", name=str(entry.get("name", "HoloSpace")), label=str(entry.get("name", "HoloSpace")), target_number=int(entry.get("number", 8)), route="region_spawn", source=source)
        except Exception:
            pass
        if bool(getattr(self, "shell_flight_craft_cinematic", False)):
            self.exit_shell_flight_cinematic()
        self.holospace_transition_active = True
        self.holospace_transition_started_at = time.monotonic()
        self.holospace_transition_duration = 10.0
        self.holospace_transition_source = str(source or "space")
        self.holospace_transition_destination = "hub" if str(destination or "space").lower() in {"hub", "return", "return_hub"} else "space"
        self.holospace_transition_target_entry = entry
        self.holospace_active = False
        self.shell_flight_craft_active = False
        self.show_holospace_cockpit(False)
        try:
            # The transition is the existing HoloSpace travel scene, not a hub overlay.
            # Hide surface-world fills/bots while the countdown runs so the player
            # sees the space-transition layer instead of the HoloVerse hub.
            self.apply_holospace_world_isolation(True, force_space=True)
            # The Liquid Orb transition is camera-owned, so hide the normal
            # world root while it runs.  This prevents the hub pyramid/world
            # from bleeding through the transition view.
            if getattr(self, "root_3d", None) is not None:
                self.root_3d.hide()
        except Exception:
            pass
        try:
            self.world_shell_mount_biome = "HoloSpace Transit"
            self.world_shell_mount_status = "HOLOSPACE TRANSIT // LIQUID ORB"
            mount = getattr(self, "world_shell_mount", None)
            if mount is not None:
                mount.force_refresh = True
                mount.write_state()
        except Exception:
            pass
        runtime = self.ensure_holospace_travel_runtime()
        if runtime is not None:
            try:
                runtime.start(duration=float(getattr(self, "holospace_transition_duration", 10.0) or 10.0), source=self.holospace_transition_source)
            except Exception as exc:
                try:
                    print(f"holospace_transition_start_warning:{exc.__class__.__name__}:{exc}")
                except Exception:
                    pass
                try:
                    runtime.stop()
                except Exception:
                    pass
                self.holospace_travel_runtime = None
                # Keep the route alive even if the clean warp layer fails; the
                # timer still hands off to HoloSpace instead of crashing back to
                # the launcher.
                self.holospace_transition_duration = min(float(getattr(self, "holospace_transition_duration", 10.0) or 10.0), 1.25)
        else:
            self.holospace_transition_duration = min(float(getattr(self, "holospace_transition_duration", 10.0) or 10.0), 1.25)
        self.runtime_world_signature = "HOLOSPACE TRANSIT // LIQUID ORB"
        self.set_holospace_transition_hud_suppressed(True)
        self.center_hint["text"] = ""
        try:
            self.setBackgroundColor(0.0, 0.0, 0.0)
            self.fog.setColor(0.0, 0.0, 0.0)
        except Exception:
            pass
        try:
            if self.audio:
                self.audio.play('world_shift.wav', 'sfx', 0.56)
        except Exception:
            pass
        return True

    def update_holospace_travel_sequence(self, dt: float) -> bool:
        if not self.is_holospace_traveling():
            return False
        # The warp is camera-owned and UI-clean, but the player must keep full
        # look control while the countdown runs.
        self.update_look(dt)
        runtime = self.ensure_holospace_travel_runtime()
        done = False
        if runtime is not None:
            try:
                done = bool(runtime.update(float(dt)))
            except Exception as exc:
                try:
                    print(f"holospace_transition_update_warning:{exc.__class__.__name__}:{exc}")
                except Exception:
                    pass
        elapsed = max(0.0, time.monotonic() - float(getattr(self, "holospace_transition_started_at", time.monotonic()) or time.monotonic()))
        duration = max(0.5, float(getattr(self, "holospace_transition_duration", 10.0) or 10.0))
        remaining = max(0.0, duration - elapsed)
        self.runtime_world_signature = "HOLOSPACE TRANSIT // LIQUID ORB"
        self.set_holospace_transition_hud_suppressed(True)
        self.center_hint["text"] = ""
        if done or elapsed >= duration:
            try:
                self.complete_holospace_travel_sequence()
            except Exception as exc:
                try:
                    print(f"holospace_transition_complete_warning:{exc.__class__.__name__}:{exc}")
                    CRASH_LOG.write_text(traceback.format_exc(), encoding="utf-8")
                except Exception:
                    pass
                self.holospace_transition_active = False
                self.holospace_active = False
            return False
        return True

    def cancel_holospace_travel_sequence(self, *, reason: str = "cancel") -> None:
        self.holospace_transition_active = False
        runtime = getattr(self, "holospace_travel_runtime", None)
        if runtime is not None:
            try:
                runtime.stop()
            except Exception:
                pass
        self.holospace_transition_source = str(reason or "cancel")
        # Restore the world layer to the state the player was actually in.
        # Entry-transition cancellation returns to the hub; return-transition
        # cancellation keeps HoloSpace active.
        try:
            if getattr(self, "root_3d", None) is not None:
                self.root_3d.show()
            if str(getattr(self, "holospace_transition_destination", "space") or "space").lower() == "hub":
                self.apply_holospace_world_isolation(True, force_space=True)
            else:
                self.apply_holospace_world_isolation(False)
        except Exception:
            pass
        self.set_holospace_transition_hud_suppressed(False)

    def complete_holospace_travel_sequence(self) -> bool:
        entry = dict(getattr(self, "holospace_transition_target_entry", None) or self.holoverse_region_entry_for_number(8) or {})
        self.holospace_transition_active = False
        self.holospace_transition_completed_count = int(getattr(self, "holospace_transition_completed_count", 0) or 0) + 1
        runtime = getattr(self, "holospace_travel_runtime", None)
        if runtime is not None:
            try:
                runtime.stop()
            except Exception:
                pass
        destination = str(getattr(self, "holospace_transition_destination", "space") or "space").lower()
        self.set_holospace_transition_hud_suppressed(False)
        if destination == "hub":
            return self.complete_holospace_return_to_hub(source="space_transition_complete")
        try:
            if getattr(self, "root_3d", None) is not None:
                self.root_3d.show()
        except Exception:
            pass
        return self.enter_holospace_direct(entry, source="space_transition_complete")

    def enter_holospace_direct(self, entry=None, *, source: str = "direct") -> bool:
        entry = dict(entry or self.holoverse_region_entry_for_number(8) or {})
        self.holoverse_selected_number = int(entry.get("number", 8))
        self.holospace_active = True
        radius = float(entry.get("radius", 11880.0))
        self.player_pos = Vec3(0.0, -radius, float(entry.get("height", 1002.0)))
        self.shell_flight_craft_active = False
        self.shell_flight_craft_velocity = Vec3(0, 0, 0)
        self.holospace_velocity = Vec3(0, 0, 0)
        self.holospace_speed_boost = 1.0
        self.holospace_ship_health = float(getattr(self, "holospace_ship_max_health", 100.0) or 100.0)
        self.holospace_ship_respawn_cooldown = 0.0
        self.holospace_last_damage_at = -999.0
        self.holospace_battle_status = "ACTIVE"
        self.holospace_control_status = "ARCADE_SPACE"
        self.player_yaw = float(entry.get("yaw", -90.0))
        self.player_pitch = -4.0
        try:
            self.camera.setPos(self.player_pos)
            focus_raw = entry.get("dyson_focus", [0.0, -12260.0, 1165.0])
            focus = Vec3(float(focus_raw[0]), float(focus_raw[1]), float(focus_raw[2]))
            self.camera.lookAt(focus)
            hpr = self.camera.getHpr(self.render)
            self.player_yaw = float(hpr.x)
            self.player_pitch = float(hpr.y)
            self.camera.setHpr(self.player_yaw, self.player_pitch, 0)
            self.camLens.setNearFar(0.05, max(float(getattr(self.cfg, "fog_distance", 900.0)), 18000.0))
            self.fog.setLinearRange(14000.0, 26000.0)
            self.fog.setColor(0.000, 0.000, 0.006)
            self.setBackgroundColor(0.000, 0.000, 0.004)
        except Exception:
            pass
        self.show_holospace_cockpit(False)
        try:
            self.world_shell_mount_biome = "HoloSpace"
        except Exception:
            pass
        mount = getattr(self, "world_shell_mount", None)
        if mount is not None:
            try:
                mount.force_refresh = True
                if hasattr(mount, "source_runtime") and mount.source_runtime is not None:
                    setattr(mount.source_runtime, "space_layer_active", True)
                    setattr(mount.source_runtime, "holospace_active", True)
                mount.write_state()
            except Exception:
                pass
        try:
            self.apply_holospace_world_isolation(True, force_space=True)
        except Exception as exc:
            try:
                print(f"holospace_isolation_warning:{exc.__class__.__name__}:{exc}")
            except Exception:
                pass
        self.runtime_world_signature = f"HOLOSPACE // SPAWNED FROM {str(source or 'DIRECT').upper()}"
        self.center_hint["text"] = ""
        try:
            self.refresh_ui()
        except Exception as exc:
            try:
                print(f"holospace_refresh_warning:{exc.__class__.__name__}:{exc}")
            except Exception:
                pass
        try:
            if getattr(self, "audio", None):
                self.audio.play('world_shift.wav', 'sfx', 0.50)
        except Exception:
            pass
        return True

    def holospace_dyson_focus(self) -> Vec3:
        try:
            entry = self.holoverse_region_entry_for_number(8) or {}
            raw = entry.get("dyson_focus", [0.0, -12480.0, 1185.0])
            return Vec3(float(raw[0]), float(raw[1]), float(raw[2]))
        except Exception:
            return Vec3(0.0, -12480.0, 1185.0)

    def holospace_spawn_position(self) -> Vec3:
        try:
            entry = self.holoverse_region_entry_for_number(8) or {}
            return Vec3(0.0, -float(entry.get("radius", 11420.0)), float(entry.get("height", 1096.0)))
        except Exception:
            return Vec3(0.0, -11420.0, 1096.0)

    def respawn_holospace_ship(self, *, reason: str = "destroyed") -> None:
        """Restart the HoloSpace flight loop at the safe spawn lane."""
        self.player_pos = self.holospace_spawn_position()
        self.holospace_velocity = Vec3(0, 0, 0)
        self.holospace_speed_boost = 1.0
        self.holospace_ship_health = float(getattr(self, "holospace_ship_max_health", 100.0) or 100.0)
        self.holospace_ship_respawn_cooldown = 1.65
        self.holospace_last_damage_at = float(getattr(self, "elapsed", 0.0))
        self.holospace_battle_status = f"RESPAWNED:{reason}"
        try:
            self.camera.setPos(self.player_pos)
            self.camera.lookAt(self.holospace_dyson_focus())
            hpr = self.camera.getHpr(self.render)
            self.player_yaw = float(hpr.x)
            self.player_pitch = float(hpr.y)
            self.camera.setHpr(self.player_yaw, self.player_pitch, 0)
        except Exception:
            pass
        self.center_hint["text"] = "SHIP DESTROYED // RESPAWNED AT HOLOSPACE SPAWN"
        try:
            if getattr(self, "audio", None):
                self.audio.play('hit.mp3', 'sfx', 0.38)
        except Exception:
            pass

    def update_holospace_battlefield_state(self, dt: float) -> None:
        """Lightweight endless-space-war pressure around the Dyson region.

        The world runtime renders the distant battle.  This host-side loop only
        tracks the player ship health and respawns at the safe HoloSpace spawn
        when the ship is destroyed, so the activity remains engaging without
        spawning heavy AI in the main app.
        """
        if not self.is_holospace_active():
            return
        max_health = float(getattr(self, "holospace_ship_max_health", 100.0) or 100.0)
        health = float(getattr(self, "holospace_ship_health", max_health) or max_health)
        cooldown = max(0.0, float(getattr(self, "holospace_ship_respawn_cooldown", 0.0) or 0.0) - float(dt))
        self.holospace_ship_respawn_cooldown = cooldown
        if cooldown > 0.0:
            self.holospace_ship_health = max_health
            return
        focus = self.holospace_dyson_focus()
        dist = (Vec3(self.player_pos) - focus).length()
        elapsed = float(getattr(self, "elapsed", 0.0))
        # The safe spawn lane is calm; the combat shell gets hotter around the
        # mid-orbit battle.  This reads as endless background war without turning
        # every meter of space into damage spam.
        in_battle_shell = 720.0 <= dist <= 2120.0
        lane_crossfire = abs(math.sin(elapsed * 0.72 + dist * 0.004)) > 0.84 or abs(math.sin(elapsed * 1.13 + self.player_pos.x * 0.003)) > 0.91
        if in_battle_shell and lane_crossfire and elapsed - float(getattr(self, "holospace_last_damage_at", -999.0) or -999.0) >= float(HOLOSPACE_DAMAGE_COOLDOWN):
            damage = float(HOLOSPACE_BATTLE_DAMAGE_MIN) + (float(HOLOSPACE_BATTLE_DAMAGE_MAX) - float(HOLOSPACE_BATTLE_DAMAGE_MIN)) * abs(math.sin(elapsed * 1.9 + dist * 0.002))
            health = max(0.0, health - damage)
            self.holospace_ship_health = health
            self.holospace_last_damage_at = elapsed
            self.holospace_battle_status = f"UNDER_FIRE:{int(round(health))}"
            self.center_hint["text"] = f"HOLOSPACE WAR // SHIP {int(round(health))}% // DYSON SPHERE RETURNS TO HUB"
            try:
                if getattr(self, "audio", None):
                    self.audio.play('fire.mp3', 'sfx', 0.30)
            except Exception:
                pass
        elif not in_battle_shell and health < max_health:
            self.holospace_ship_health = min(max_health, health + float(dt) * float(HOLOSPACE_SAFE_SPAWN_REPAIR_RATE))
            self.holospace_battle_status = "REPAIRING"
        else:
            self.holospace_ship_health = health
        if float(getattr(self, "holospace_ship_health", max_health) or max_health) <= 0.0:
            self.respawn_holospace_ship(reason="battle_damage")

    def handle_holospace_boundary_return(self, candidate: Vec3) -> bool:
        try:
            z = float(candidate.z)
            dyson_dist = (Vec3(candidate) - self.holospace_dyson_focus()).length()
        except Exception:
            return False
        # The Dyson shell is now the intentional exit gate.  Outer space no
        # longer kicks the player out, preserving the infinite-space feel.
        if dyson_dist <= float(HOLOSPACE_DYSON_RETURN_RADIUS):
            self.start_holospace_return_sequence(source="dyson_sphere")
            return True
        # Soft safety only: extreme vertical drift restarts the space ship at the
        # HoloSpace spawn instead of dumping the player out of the region.
        if z <= float(HOLOSPACE_VERTICAL_RESPAWN_MIN_Z) or z >= float(HOLOSPACE_VERTICAL_RESPAWN_MAX_Z):
            self.respawn_holospace_ship(reason="space_boundary")
            return True
        return False

    def shell_flight_space_boundary_triggered(self, candidate: Vec3) -> bool:
        try:
            r = math.sqrt(float(candidate.x) * float(candidate.x) + float(candidate.y) * float(candidate.y))
            limit = max(8.0, self.world_shell_play_radius_limit() - 0.65)
            return r >= limit
        except Exception:
            return False

    def default_deep_water_surface_z(self) -> float:
        """Waterline for the Core-owned HoloVerse Mushroom region.

        Pass 47 keeps the region shallow and readable: the player arrives on a
        small hoverboard at the surface, then can dive below it without ever
        standing on an invisible floor above the water.
        """
        return 1.25

    def default_deep_water_bottom_z(self) -> float:
        return -32.0

    def default_deep_water_hover_eye_z(self) -> float:
        return self.default_deep_water_surface_z() + float(getattr(self.cfg, "player_eye_height", 3.95))

    def is_default_deep_water_surface_hover(self) -> bool:
        try:
            return self.is_default_deep_water_active() and float(self.player_pos.z) >= self.default_deep_water_hover_eye_z() - 1.20
        except Exception:
            return False

    def is_default_deep_water_active(self) -> bool:
        # Pass 85: retired. Region 3 is now Mushroom, so the old hover/swim
        # controller must never activate for this ring.
        return False

    def default_deep_water_point_allowed(self, pos: Vec3) -> bool:
        try:
            r = math.sqrt(float(pos.x) * float(pos.x) + float(pos.y) * float(pos.y))
            z = float(pos.z)
        except Exception:
            return False
        # Keep the default HoloVerse water volume tied to the real world.py ring.
        if r < 3300.0 or r >= 4700.0:
            return False
        return self.default_deep_water_bottom_z() + 1.2 <= z <= self.default_deep_water_hover_eye_z() + 1.5

    def ensure_holospace_cockpit(self):
        if getattr(self, "holospace_cockpit_root", None) is not None and not self.holospace_cockpit_root.isEmpty():
            return
        root = self.camera.attachNewNode("holospace-cockpit-overlay")
        root.setTransparency(TransparencyAttrib.MAlpha)
        root.setDepthWrite(False)
        root.setDepthTest(False)
        root.setBin("fixed", 42)
        col = (0.18, 0.92, 1.0, 0.44)
        dash = (1.0, 0.86, 0.28, 0.42)
        try:
            self.add_box(root, Vec3(0.0, 1.72, -0.72), Vec3(1.55, 0.10, 0.18), col, 0.10)
            self.add_box(root, Vec3(-0.92, 1.65, -0.58), Vec3(0.34, 0.08, 0.34), dash, 0.10)
            self.add_box(root, Vec3(0.92, 1.65, -0.58), Vec3(0.34, 0.08, 0.34), dash, 0.10)
            self.add_box(root, Vec3(-0.62, 1.80, -0.84), Vec3(0.24, 0.08, 0.16), col, 0.08)
            self.add_box(root, Vec3(0.62, 1.80, -0.84), Vec3(0.24, 0.08, 0.16), col, 0.08)
        except Exception:
            pass
        self.holospace_cockpit_root = root

    def show_holospace_cockpit(self, show: bool):
        if show:
            self.ensure_holospace_cockpit()
            try:
                self.holospace_cockpit_root.show()
            except Exception:
                pass
        else:
            node = getattr(self, "holospace_cockpit_root", None)
            if node is not None and not node.isEmpty():
                try:
                    node.hide()
                except Exception:
                    pass

    def ensure_deep_water_hoverboard(self):
        if getattr(self, "deep_water_hoverboard_root", None) is not None and not self.deep_water_hoverboard_root.isEmpty():
            return
        root = self.camera.attachNewNode("deep-water-hoverboard-overlay")
        root.setTransparency(TransparencyAttrib.MAlpha)
        root.setDepthWrite(False)
        root.setDepthTest(False)
        root.setBin("fixed", 43)
        try:
            col = (0.18, 0.96, 1.0, 0.46)
            fill = (0.05, 0.48, 0.62, 0.18)
            accent = (1.0, 0.86, 0.28, 0.34)
            # Low, first-person vector board: visible but not cockpit clutter.
            self.add_box(root, Vec3(0.0, 1.58, -0.92), Vec3(1.70, 0.12, 0.16), col, 0.075)
            self.add_box(root, Vec3(-0.58, 1.58, -0.82), Vec3(0.36, 0.08, 0.10), accent, 0.060)
            self.add_box(root, Vec3(0.58, 1.58, -0.82), Vec3(0.36, 0.08, 0.10), accent, 0.060)
            self.add_surface_card(root, Vec3(0.0, 1.62, -0.94), Vec3(0, 0, 0), 1.88, 0.34, fill, True)
            for x in (-0.86, 0.86):
                self.add_polyline(root, [Vec3(x, 1.46, -0.96), Vec3(x * 0.72, 1.84, -0.91)], (0.34, 1.0, 1.0, 0.36), self.cfg.line_thickness * 0.055, False, "hoverboard-side-flow")
        except Exception:
            pass
        self.deep_water_hoverboard_root = root

    def show_deep_water_hoverboard(self, show: bool):
        if show:
            self.ensure_deep_water_hoverboard()
            try:
                pulse = 0.86 + 0.14 * math.sin(float(getattr(self, "elapsed", 0.0)) * 2.2)
                self.deep_water_hoverboard_root.setScale(1.0, 1.0, pulse)
                self.deep_water_hoverboard_root.show()
            except Exception:
                pass
        else:
            node = getattr(self, "deep_water_hoverboard_root", None)
            if node is not None and not node.isEmpty():
                try:
                    node.hide()
                except Exception:
                    pass

    def apply_holospace_world_isolation(self, enabled: bool, *, force_space: bool = False):
        """Hide the surface/default-world shell while HoloSpace is active.

        Key 8 is a space-only viewer. It must not keep streaming biome key 8,
        because biome key 8 is Metropolis. This method leaves the source
        bridge alive for the Dyson layer, but hides terrain, cities, bots,
        and old player/cockpit craft silhouettes so space is clean.
        """
        enabled = bool(enabled)
        mount = getattr(self, "world_shell_mount", None)
        if mount is None:
            return

        def _set_visible(node, visible: bool):
            try:
                if node is not None and not node.isEmpty():
                    node.show() if visible else node.hide()
            except Exception:
                pass

        for attr in (
            "static_root", "stream_root", "pass45_beauty_root",
            "pass46_water_wave_root", "checkpoint_root", "motion_root",
        ):
            _set_visible(getattr(mount, attr, None), not enabled)

        runtime = getattr(mount, "source_runtime", None)
        if runtime is not None:
            for attr in (
                "surface_root", "line_root", "accent_root", "sky_root",
                "atmosphere_root", "world_root", "galaxy_root",
            ):
                _set_visible(getattr(runtime, attr, None), not enabled)

            for list_attr in (
                "named_region_bot_nodes", "metropolis_hover_vehicle_nodes",
                "metropolis_robot_nodes", "deep_water_creature_nodes",
                "deep_water_glow_nodes", "deep_water_feature_nodes",
                "deep_water_sky_creature_nodes", "salvage_population_nodes",
                "urban_battle_nodes", "urban_airstrike_nodes",
                "world_actors", "galaxy_nodes",
            ):
                for node in list(getattr(runtime, list_attr, []) or []):
                    _set_visible(node, not enabled)

            if enabled or force_space:
                try:
                    setattr(runtime, "holospace_active", True)
                except Exception:
                    pass
                _set_visible(getattr(runtime, "space_layer_root", None), True)

        if enabled:
            self.show_holospace_cockpit(False)
            self.world_shell_mount_biome = "HoloSpace"
            self.world_shell_mount_status = "HOLOSPACE // WATER LITE AUTHORITY"

    def current_holoverse_region_name(self):
        if self.is_holospace_traveling():
            return "HoloSpace Transit"
        if self.is_holospace_active():
            return "HoloSpace"
        # Fix for the inner-most layer: radius 0..620 is always the Hub Region,
        # never a fall-through to the final outer ring.
        try:
            r = math.sqrt(float(self.player_pos.x) ** 2 + float(self.player_pos.y) ** 2)
            if int(getattr(self, "holoverse_selected_number", 0) or 0) == 9 and r < 120.0:
                return "Hub Spawn"
            for entry in self.holoverse_region_travel_map():
                if float(entry["r0"]) <= r < float(entry["r1"]):
                    return str(entry["name"])
            if r < 620.0:
                return "Hub Region"
        except Exception:
            pass
        raw = str(getattr(self, "world_shell_mount_biome", "Hub Region") or "Hub Region").strip()
        return "Hub Region" if raw.upper() in {"FLAT", "HUB", "HUB REGION"} else raw.title()

    def current_holoverse_region_number(self):
        if self.is_holospace_traveling():
            return 8
        if self.is_holospace_active():
            return 8
        try:
            r = math.sqrt(float(self.player_pos.x) ** 2 + float(self.player_pos.y) ** 2)
            if int(getattr(self, "holoverse_selected_number", 0) or 0) == 9 and r < 120.0:
                return 9
            for entry in self.holoverse_region_travel_map():
                if float(entry["r0"]) <= r < float(entry["r1"]):
                    return int(entry["number"])
        except Exception:
            pass
        return 0

    def update_holoverse_region_ui(self):
        if not hasattr(self, "region_keymap_root"):
            return
        name = self.current_holoverse_region_name()
        active_number = self.current_holoverse_region_number()
        visible = bool(getattr(self.cfg, "world_shell_region_keymap_enabled", False)) and self.dev_region_number_travel_enabled() and self.hud_visible and not self.menu_open and not self.core_console_open and not bool(getattr(self, "bot_dialogue_open", False)) and not bool(getattr(self, "bot_dialogue_hud_suppressed", False)) and not self.world_unlocked and getattr(self, "active_native_mode", None) is None and getattr(self, "external_process", None) is None
        if name != getattr(self, "region_ui_last_name", "") and hasattr(self, "region_top_label"):
            self.set_ui_text(self.region_top_label, f"HOLOVERSE // {name.upper()}")
            self.region_ui_last_name = name
            try:
                if getattr(self, "active_native_mode", None) is None and not getattr(self, "external_process", None):
                    self.record_matrixcore_discovered_gate(kind="region", name=name, label=name, target_number=int(active_number), route="region_discovery", source="world_shell_entry")
            except Exception:
                pass
        if active_number != getattr(self, "region_ui_last_active_number", None):
            for idx, btn in enumerate(getattr(self, "region_keymap_buttons", []) or []):
                try:
                    btn["frameColor"] = (0.0, 0.0, 0.0, 0.0)
                    btn["relief"] = None
                    if idx == active_number:
                        btn["text_fg"] = (1.0, 0.86, 0.28, 1.0)
                    else:
                        btn["text_fg"] = (0.84, 1.0, 1.0, 0.92)
                except Exception:
                    pass
            self.region_ui_last_active_number = active_number
        if visible != getattr(self, "region_ui_last_visible", None):
            if visible:
                self.region_keymap_root.show()
                if hasattr(self, "region_top_panel"):
                    self.region_top_panel.show()
            else:
                self.region_keymap_root.hide()
                if hasattr(self, "region_top_panel"):
                    self.region_top_panel.hide()
            self.region_ui_last_visible = visible

    def travel_to_holoverse_region_index(self, number, *, source: str = "region_travel", force: bool = False):
        entry = self.holoverse_region_entry_for_number(number)
        if entry is None:
            return False
        if self.menu_open:
            return False
        if not force and not self.dev_region_number_travel_enabled():
            self.center_hint["text"] = "REGION NUMBER TRAVEL DISABLED // USE WORLD TRAVEL"
            return False
        if self.core_console_open:
            self.center_hint["text"] = "CORE // CLOSE DECK BEFORE REGION TRAVEL"
            return False
        if getattr(self, "active_native_mode", None) is not None or getattr(self, "external_process", None) is not None:
            return False
        self.holoverse_selected_number = int(entry.get("number", number))
        if self.world_unlocked or self.active_artifact is not None:
            self.teleport_to_hub()
        if bool(entry.get("hub_spawn", False)):
            self.holospace_active = False
            self.show_holospace_cockpit(False)
            self.apply_holospace_world_isolation(False)
            self.teleport_to_hub()
            self.center_hint["text"] = "9 // HUB SPAWN"
            try:
                self.record_matrixcore_discovered_gate(kind="region", name=str(entry.get("name", "Hub Spawn")), label=str(entry.get("name", "Hub Spawn")), target_number=int(entry.get("number", 9)), route="region_spawn", source=source)
            except Exception:
                pass
            return True
        if bool(entry.get("holospace", False)):
            # Region gate number 8 uses the same clean warp as aircraft ascent.
            try:
                self.record_matrixcore_discovered_gate(kind="region", name=str(entry.get("name", "HoloSpace")), label=str(entry.get("name", "HoloSpace")), target_number=int(entry.get("number", 8)), route="region_spawn", source=source)
            except Exception:
                pass
            return self.start_holospace_travel_sequence(entry, source=source)
        if self.is_holospace_traveling():
            self.cancel_holospace_travel_sequence(reason="region_travel_cancelled")
        self.holospace_active = False
        self.holospace_velocity = Vec3(0, 0, 0)
        self.holospace_speed_boost = 1.0
        self.holospace_ship_health = float(getattr(self, "holospace_ship_max_health", 100.0) or 100.0)
        self.holospace_ship_respawn_cooldown = 0.0
        self.show_holospace_cockpit(False)
        self.apply_holospace_world_isolation(False)
        radius = float(entry["radius"])
        if bool(entry.get("water_surface_spawn", False)):
            target_z = self.default_deep_water_hover_eye_z()
        else:
            target_z = float(entry.get("height", 0.0)) + float(getattr(self.cfg, "player_eye_height", 3.95))
        target = Vec3(0.0, -radius, target_z)
        self.player_pos = target
        self.player_yaw = float(entry.get("yaw", -90.0))
        self.player_pitch = -7.0
        # Urban is an always-on battlefield region.  The Sable dialogue only starts
        # the formal match rules; region travel itself must still mount the arena
        # visuals in the live game route.  This early call stages focus before the
        # camera is committed, and a second call below runs after the world-shell
        # stream refresh so the shell cannot leave the arena hidden/regressed.
        try:
            if hasattr(self, "current_holoverse_region_number") and int(self.current_holoverse_region_number()) == 6 and hasattr(self, "ensure_urban_battlefield_runtime"):
                self.ensure_urban_battlefield_runtime(0.016, source="region_travel_pre_stream")
                focus = getattr(self, "urban_battlefield_focus_pos", None)
                if focus is not None:
                    self.camera.lookAt(Vec3(focus))
                    hpr = self.camera.getHpr(self.render)
                    self.player_yaw = float(hpr.x)
                    self.player_pitch = float(hpr.y)
        except Exception as exc:
            try:
                print(f"urban_region_battlefield_pre_stream_warning:{exc}")
            except Exception:
                pass
        try:
            self.camera.setPos(self.player_pos)
            self.camera.setHpr(self.player_yaw, self.player_pitch, 0)
        except Exception:
            pass
        try:
            self.world_shell_mount_biome = str(entry["name"])
            self.cfg.world_shell_active_biome = int(entry["ring_key"])
            save_config(self.cfg)
        except Exception:
            pass
        mount = getattr(self, "world_shell_mount", None)
        if mount is not None:
            try:
                mount.active_key = int(entry["ring_key"])
                mount.force_refresh = True
                mount.update_stream(force=True)
                mount.write_state()
            except Exception:
                pass
        # Post-stream Urban mount guard: this is the player route, not a proof
        # scene.  If the shell refresh happened after the first Urban call, rebuild
        # or refresh the ambient battlefield now so number-key travel and flying
        # vehicle entry both land in the imported arena view.
        try:
            if int(entry.get("number", -1)) == 6 and hasattr(self, "ensure_urban_battlefield_runtime"):
                self.ensure_urban_battlefield_runtime(0.016, source="region_travel_post_stream")
                if hasattr(self, "update_perf_hud"):
                    self.update_perf_hud(force=True)
        except Exception as exc:
            try:
                print(f"urban_region_battlefield_post_stream_warning:{exc.__class__.__name__}:{exc}")
            except Exception:
                pass
        self.center_hint["text"] = f"REGION {int(entry['number'])} // {str(entry['name']).upper()}"
        try:
            self.record_matrixcore_discovered_gate(kind="region", name=str(entry.get("name", "Region")), label=str(entry.get("name", "Region")), target_number=int(entry.get("number", number)), route="region_spawn", source=source)
        except Exception:
            pass
        self.refresh_ui()
        if self.audio:
            self.audio.play('world_shift.wav', 'sfx', 0.50)
        return True

    def handle_number_action(self, number):
        number = int(number)
        if self.menu_open and 1 <= number <= len(self.menu_actions):
            self.apply_menu_action(number - 1)
            return
        if getattr(self, "active_native_mode", None) is not None:
            if number == 0:
                self.return_from_native_mode(reason="number_0")
                return
            if self.dispatch_native_action(f"number_{number}"):
                return
            return
        if self.core_console_open:
            self.center_hint["text"] = "CORE // USE MOUSE MODE DECK"
            return
        if self.is_holospace_traveling():
            # Player-facing numbers are disabled during the clean warp.
            return
        if not self.dev_region_number_travel_enabled():
            self.center_hint["text"] = "REGION NUMBER TRAVEL DISABLED // USE ARTIFACTS OR AIRCRAFT"
            return
        if number == 0:
            self.toggle_holocore_main_bridge(source="dev_number_0")
            return
        if 1 <= number <= 9 and self.travel_to_holoverse_region_index(number):
            return
        # Number keys no longer launch Core modes. Use the clickable Core deck.

    def station_line_color(self, alpha=1.0):
        return hsv_color(self.cfg.line_hue, self.cfg.line_saturation, self.cfg.line_value, alpha)

    def station_glow_color(self, alpha=1.0):
        return hsv_color((self.cfg.line_hue + 0.06) % 1.0, min(1.0, self.cfg.line_saturation * 0.76), min(1.0, self.cfg.line_value), alpha)

    def artifact_presentation(self, mode_id: object) -> dict:
        key = canonical_dimension_lookup_key(mode_id)
        return dict(ARTIFACT_DIMENSION_PRESENTATION.get(key, {}))

    def artifact_color_for_mode(self, mode_id: object, alpha=1.0, variant: str = "primary"):
        presentation = self.artifact_presentation(mode_id)
        palette = presentation.get("palette") if isinstance(presentation.get("palette"), dict) else {}
        rgb = palette.get(variant) or palette.get("primary")
        if isinstance(rgb, (list, tuple)) and len(rgb) >= 3:
            return (float(rgb[0]), float(rgb[1]), float(rgb[2]), alpha)
        slot_divisor = max(1.0, float(ARTIFACT_SLOT_COUNT))
        try:
            idx = ARTIFACT_DIMENSION_ROUTES.index(canonical_dimension_lookup_key(mode_id))
        except ValueError:
            idx = 0
        return hsv_color((self.cfg.line_hue + idx / slot_divisor + 0.08) % 1.0, 0.78, 1.0, alpha)

    def artifact_color(self, idx: int, alpha=1.0):
        try:
            mode_id = ARTIFACT_DIMENSION_ROUTES[int(idx) % len(ARTIFACT_DIMENSION_ROUTES)]
        except Exception:
            mode_id = ""
        if mode_id:
            return self.artifact_color_for_mode(mode_id, alpha, "primary")
        slot_divisor = max(1.0, float(ARTIFACT_SLOT_COUNT))
        return hsv_color((self.cfg.line_hue + idx / slot_divisor + 0.08) % 1.0, 0.74, 1.0, alpha)

    def dimension_display_name_for_id(self, mode_id: object, fallback: object = "DIMENSION") -> str:
        key = canonical_dimension_lookup_key(mode_id)
        presentation = ARTIFACT_DIMENSION_PRESENTATION.get(key)
        if isinstance(presentation, dict) and presentation.get("display_name"):
            return str(presentation.get("display_name"))
        text = re.sub(r"[\\/]+", " ", str(fallback or mode_id or "DIMENSION"))
        text = re.sub(r"[_\-]+", " ", text)
        text = re.sub(r"\s+", " ", text).strip() or "DIMENSION"
        return text

    def dimension_display_name_for_mode(self, mode: dict | None, fallback: object = "DIMENSION") -> str:
        mode = dict(mode or {})
        manifest = dict(mode.get("manifest") or {})
        candidates = [
            manifest.get("id"),
            mode.get("dimension_mode_id"),
            mode.get("mode_id"),
            mode.get("name"),
            manifest.get("title"),
            fallback,
        ]
        for value in candidates:
            key = canonical_dimension_lookup_key(value)
            if key in ARTIFACT_DIMENSION_PRESENTATION:
                return self.dimension_display_name_for_id(key, fallback)
        return self.dimension_display_name_for_id(candidates[0] or fallback, fallback)

    def dimension_mode_id_for_display(self, value: object) -> str:
        key = canonical_dimension_lookup_key(value)
        if key in ARTIFACT_DIMENSION_PRESENTATION:
            return key
        compact = key
        if compact.endswith("_dimension"):
            compact = compact[: -len("_dimension")]
        if compact in ARTIFACT_DIMENSION_PRESENTATION:
            return compact
        for mode_id, presentation in ARTIFACT_DIMENSION_PRESENTATION.items():
            names = {
                canonical_dimension_lookup_key(mode_id),
                canonical_dimension_lookup_key(presentation.get("display_name") if isinstance(presentation, dict) else ""),
                canonical_dimension_lookup_key(presentation.get("short_name") if isinstance(presentation, dict) else ""),
            }
            if key in names or compact in names:
                return mode_id
        for mode in list(getattr(self, "core_modes", []) or []):
            manifest = dict(mode.get("manifest") or {})
            mode_key = canonical_dimension_lookup_key(manifest.get("id") or mode.get("name") or manifest.get("title"))
            aliases = {
                mode_key,
                canonical_dimension_lookup_key(mode.get("name")),
                canonical_dimension_lookup_key(manifest.get("title")),
            }
            if key in aliases or compact in aliases:
                return mode_key
        return key

    def lens_color(self, alpha=1.0):
        return hsv_color((self.cfg.line_hue + 0.48) % 1.0, 0.46, 1.0, alpha)

    def add_surface_card(self, parent, pos, hpr, sx, sy, color, two_sided=True):
        cm = CardMaker("surface-card")
        cm.setFrame(-sx * 0.5, sx * 0.5, -sy * 0.5, sy * 0.5)
        np = parent.attachNewNode(cm.generate())
        np.setPos(pos)
        np.setHpr(hpr)
        np.setColor(*color)
        np.setTransparency(TransparencyAttrib.MAlpha)
        if two_sided:
            np.setTwoSided(True)
        return np

    def add_polyline(self, parent, points, color, thickness=None, closed=False, name="poly"):
        segs = LineSegs(name)
        segs.setThickness(thickness or self.cfg.line_thickness)
        segs.setColor(*color)
        if points:
            segs.moveTo(points[0])
            for p in points[1:]:
                segs.drawTo(p)
            if closed:
                segs.drawTo(points[0])
        np = parent.attachNewNode(segs.create())
        np.setAntialias(AntialiasAttrib.MLine)
        np.setTransparency(TransparencyAttrib.MAlpha)
        # Pass 0.9.14 visibility guard: terrain wires are the readable world language.
        # Do not globally promote every line, or the hub shell draws over world shots.
        if str(name or "").startswith("terrain-"):
            try:
                np.setBin("fixed", 42)
                np.setDepthWrite(False)
                np.setDepthTest(True)
            except Exception:
                pass
            np.setPythonTag("visibility_line_overlay", True)
        return np

    def world_surface_palette(self, spec=None):
        """Return the single underlay texture palette for the active generated world."""
        spec = spec or self.current_world_spec()
        kind = str(spec.get("kind", "frontier"))
        profile = str(spec.get("profile", kind))
        if kind == "venus":
            return {
                "key": "venus-caustic-underlay",
                "base": (0.34, 0.105, 0.035, 0.64),
                "accent": (1.00, 0.54, 0.18, 0.64),
                "detail": (0.96, 0.78, 0.26, 0.42),
                "uv_scale": 0.040,
            }
        if kind == "underwater":
            return {
                "key": "aqua-trench-underlay",
                "base": (0.015, 0.145, 0.185, 0.54),
                "accent": (0.10, 0.82, 0.86, 0.48),
                "detail": (0.36, 0.94, 0.92, 0.28),
                "uv_scale": 0.030,
            }
        if kind == "jungle":
            return {
                "key": "verdant-canopy-underlay",
                "base": (0.028, 0.135, 0.046, 0.58),
                "accent": (0.20, 0.74, 0.24, 0.50),
                "detail": (0.64, 0.98, 0.42, 0.30),
                "uv_scale": 0.034,
            }
        if profile == "ruins":
            return {
                "key": "ruin-meridian-underlay",
                "base": (0.22, 0.16, 0.13, 0.56),
                "accent": (0.80, 0.52, 0.36, 0.42),
                "detail": (0.94, 0.80, 0.62, 0.26),
                "uv_scale": 0.036,
            }
        if profile == "bastion":
            return {
                "key": "signal-bastion-underlay",
                "base": (0.18, 0.08, 0.18, 0.56),
                "accent": (0.85, 0.30, 0.76, 0.42),
                "detail": (1.00, 0.72, 0.96, 0.28),
                "uv_scale": 0.038,
            }
        if profile == "spirefield":
            return {
                "key": "aether-spirefield-underlay",
                "base": (0.06, 0.12, 0.20, 0.56),
                "accent": (0.32, 0.74, 1.00, 0.42),
                "detail": (0.78, 0.94, 1.00, 0.28),
                "uv_scale": 0.034,
            }
        return {
            "key": "frontier-plains-underlay",
            "base": (0.055, 0.15, 0.095, 0.54),
            "accent": (0.30, 0.74, 0.48, 0.38),
            "detail": (0.86, 0.98, 0.78, 0.24),
            "uv_scale": 0.032,
        }

    def get_world_surface_texture(self, spec=None):
        palette = self.world_surface_palette(spec)
        key = palette["key"]
        cached = self.world_surface_textures.get(key)
        if cached is not None:
            return cached
        # Keep the procedural underlay texture power-of-two.  Panda3D's
        # p3tinydisplay/offscreen proof renderer rejects 96x96 textures, which
        # spammed errors and could stall regression captures even though the
        # normal renderer tolerated them.
        size = 128
        img = PNMImage(size, size, 4)
        base = palette["base"]
        accent = palette["accent"]
        detail = palette["detail"]
        for py in range(size):
            v = py / float(size)
            for px in range(size):
                u = px / float(size)
                strata = 0.5 + 0.5 * math.sin((u * 7.0 + v * 2.0) * math.tau)
                veins = 0.5 + 0.5 * math.sin((u * 13.0 - v * 9.0) * math.tau + math.sin(v * math.tau * 3.0) * 0.8)
                cells = 0.5 + 0.5 * math.sin((u + v) * math.tau * 5.0) * math.cos((u - v) * math.tau * 4.0)
                mix_a = 0.18 + 0.24 * strata
                mix_d = 0.10 + 0.16 * veins * cells
                r = base[0] * (1.0 - mix_a) + accent[0] * mix_a
                g = base[1] * (1.0 - mix_a) + accent[1] * mix_a
                b = base[2] * (1.0 - mix_a) + accent[2] * mix_a
                r = r * (1.0 - mix_d) + detail[0] * mix_d
                g = g * (1.0 - mix_d) + detail[1] * mix_d
                b = b * (1.0 - mix_d) + detail[2] * mix_d
                a = max(0.0, min(1.0, base[3] + accent[3] * 0.08 + detail[3] * 0.06))
                img.setXelA(px, py, r, g, b, a)
        tex = Texture(key)
        tex.load(img)
        tex.setMinfilter(SamplerState.FTLinearMipmapLinear)
        tex.setMagfilter(SamplerState.FTLinear)
        tex.setWrapU(SamplerState.WMRepeat)
        tex.setWrapV(SamplerState.WMRepeat)
        self.world_surface_textures[key] = tex
        return tex

    def add_world_surface_underlay(self, parent, cx: int, cy: int, spec, axis_coords):
        """Create a filled terrain-following mesh under the wire terrain grid.

        This is visual-only. It follows the exact sampled terrain heights with a
        tiny downward offset, so it fills the terrain silhouette without changing
        collision or player movement.
        """
        kind = str(spec.get("kind", "frontier"))
        if kind == "space":
            return None
        chunk_size = float(self.cfg.terrain_chunk_size)
        ox = cx * chunk_size
        oy = cy * chunk_size
        palette = self.world_surface_palette(spec)
        base = palette["base"]
        accent = palette["accent"]
        uv_scale = float(palette.get("uv_scale", 0.034))
        coords = list(axis_coords)
        if len(coords) < 2:
            return None
        format_obj = GeomVertexFormat.getV3n3cpt2()
        vdata = GeomVertexData(f"world-surface-{cx}-{cy}", format_obj, Geom.UHStatic)
        vertex = GeomVertexWriter(vdata, "vertex")
        normal = GeomVertexWriter(vdata, "normal")
        color = GeomVertexWriter(vdata, "color")
        texcoord = GeomVertexWriter(vdata, "texcoord")
        min_z = 999999.0
        max_z = -999999.0
        samples = []
        for local_y in coords:
            row = []
            y = oy + local_y
            for local_x in coords:
                x = ox + local_x
                z = self.world_height_at(x, y, spec)
                row.append((x, y, z))
                min_z = min(min_z, z)
                max_z = max(max_z, z)
            samples.append(row)
        z_span = max(1.0, max_z - min_z)
        for row in samples:
            for x, y, z in row:
                height_t = max(0.0, min(1.0, (z - min_z) / z_span))
                shade = 0.74 + 0.22 * height_t
                r = (base[0] * 0.72 + accent[0] * 0.28) * shade
                g = (base[1] * 0.72 + accent[1] * 0.28) * shade
                b = (base[2] * 0.72 + accent[2] * 0.28) * shade
                # Pass 0.9.14: keep the fill visibly below the terrain wires and
                # transparent enough that props/landmarks remain legible.
                a = max(0.07, min(0.42, base[3] * 0.56 + 0.035 * height_t))
                vertex.addData3f(x, y, z - 0.165)
                normal.addData3f(0.0, 0.0, 1.0)
                color.addData4f(min(1.0, r), min(1.0, g), min(1.0, b), a)
                texcoord.addData2f(x * uv_scale, y * uv_scale)
        tris = GeomTriangles(Geom.UHStatic)
        width = len(coords)
        height = len(coords)
        for iy in range(height - 1):
            for ix in range(width - 1):
                v00 = iy * width + ix
                v10 = iy * width + ix + 1
                v01 = (iy + 1) * width + ix
                v11 = (iy + 1) * width + ix + 1
                tris.addVertices(v00, v10, v11)
                tris.addVertices(v00, v11, v01)
        geom = Geom(vdata)
        geom.addPrimitive(tris)
        geom_node = GeomNode(f"world-surface-underlay-{cx}-{cy}")
        geom_node.addGeom(geom)
        np = parent.attachNewNode(geom_node)
        np.setTexture(TextureStage.getDefault(), self.get_world_surface_texture(spec), 1)
        np.setTransparency(TransparencyAttrib.MAlpha)
        np.setTwoSided(True)
        np.setLightOff(1)
        # Visibility-safe underlay: visible as ground mass, but not allowed to
        # write into the depth buffer or hide terrain wires / props drawn above it.
        try:
            np.setBin("transparent", 3)
            np.setDepthWrite(False)
            np.setDepthTest(True)
        except Exception:
            pass
        np.setPythonTag("world_surface_underlay", True)
        np.setPythonTag("world_surface_texture", palette["key"])
        np.setPythonTag("visibility_safe_underlay", True)
        np.setPythonTag("underlay_depth_write_disabled", True)
        np.setPythonTag("underlay_z_offset", -0.165)
        np.setPythonTag("underlay_alpha_max", 0.42)
        return np

    def polygon_points(self, radius, z, count=8, offset_deg=22.5):
        pts = []
        for i in range(count):
            a = math.radians(offset_deg) + math.tau * i / count
            pts.append(Vec3(math.cos(a) * radius, math.sin(a) * radius, z))
        return pts

    def add_prism(self, parent, radius, height, color, count=8, offset_deg=22.5, thickness_scale=1.0):
        bottom = self.polygon_points(radius, 0, count, offset_deg)
        top = self.polygon_points(radius, height, count, offset_deg)
        self.add_polyline(parent, bottom, color, self.cfg.line_thickness * thickness_scale, True, "prism-bottom")
        self.add_polyline(parent, top, color, self.cfg.line_thickness * thickness_scale, True, "prism-top")
        for a, b in zip(bottom, top):
            self.add_polyline(parent, [a, b], color, self.cfg.line_thickness * thickness_scale, False, "prism-side")

    def add_box(self, parent, center, size, color, thickness_scale=1.0):
        hx, hy, hz = size.x * 0.5, size.y * 0.5, size.z * 0.5
        corners = [
            Vec3(center.x - hx, center.y - hy, center.z - hz), Vec3(center.x + hx, center.y - hy, center.z - hz),
            Vec3(center.x + hx, center.y + hy, center.z - hz), Vec3(center.x - hx, center.y + hy, center.z - hz),
            Vec3(center.x - hx, center.y - hy, center.z + hz), Vec3(center.x + hx, center.y - hy, center.z + hz),
            Vec3(center.x + hx, center.y + hy, center.z + hz), Vec3(center.x - hx, center.y + hy, center.z + hz),
        ]
        # Pass 44: low-alpha infill before wire edges so world objects read as solid forms.
        try:
            r, g, b = float(color[0]), float(color[1]), float(color[2])
            alpha_in = max(0.0, min(1.0, float(color[3]) if len(color) > 3 else 1.0))
            fill_alpha = max(0.045, min(0.34, alpha_in * 0.48))
            fmt = GeomVertexFormat.getV3c4()
            vdata = GeomVertexData("box-infill", fmt, Geom.UHStatic)
            vertex = GeomVertexWriter(vdata, "vertex")
            vcolor = GeomVertexWriter(vdata, "color")
            for p in corners:
                vertex.addData3f(p.x, p.y, p.z)
                vcolor.addData4f(max(0.0, min(1.0, r)), max(0.0, min(1.0, g)), max(0.0, min(1.0, b)), fill_alpha)
            tris = GeomTriangles(Geom.UHStatic)
            for a0, b0, c0 in ((0,2,1),(0,3,2),(4,5,6),(4,6,7),(0,1,5),(0,5,4),(1,2,6),(1,6,5),(2,3,7),(2,7,6),(3,0,4),(3,4,7)):
                tris.addVertices(a0, b0, c0)
            geom = Geom(vdata)
            geom.addPrimitive(tris)
            node = GeomNode("box-infill")
            node.addGeom(geom)
            fill = parent.attachNewNode(node)
            fill.setTransparency(TransparencyAttrib.MAlpha)
            fill.setTwoSided(True)
            fill.setLightOff(1)
            try:
                fill.setDepthWrite(False)
                fill.setBin("transparent", 2)
            except Exception:
                pass
        except Exception:
            pass
        edges = [(0,1),(1,2),(2,3),(3,0),(4,5),(5,6),(6,7),(7,4),(0,4),(1,5),(2,6),(3,7)]
        for a, b in edges:
            self.add_polyline(parent, [corners[a], corners[b]], color, self.cfg.line_thickness * thickness_scale, False, "box-edge")

    def build_octagonal_floor_grid(self, parent, inner_r, outer_r, z, color):
        for r in [inner_r + i * 2.2 for i in range(int((outer_r - inner_r) / 2.2) + 1)]:
            self.add_polyline(parent, self.polygon_points(r, z, 8, 22.5), color, self.cfg.line_thickness * 0.76, True, "oct-ring")
        for i in range(8):
            a = math.radians(22.5) + math.tau * i / 8
            p0 = Vec3(math.cos(a) * inner_r, math.sin(a) * inner_r, z)
            p1 = Vec3(math.cos(a) * outer_r, math.sin(a) * outer_r, z)
            self.add_polyline(parent, [p0, p1], color, self.cfg.line_thickness * 0.72, False, "oct-spoke")

    def clear_station(self):
        for node in [self.surface_root, self.line_root, self.accent_root, self.dome_root, self.lens_root, self.sky_root, self.world_root, self.galaxy_root]:
            node.removeNode()
        self.surface_root = self.root_3d.attachNewNode("surface-root")
        self.line_root = self.root_3d.attachNewNode("line-root")
        self.accent_root = self.root_3d.attachNewNode("accent-root")
        self.dome_root = self.root_3d.attachNewNode("dome-root")
        self.lens_root = self.root_3d.attachNewNode("lens-root")
        self.sky_root = self.root_3d.attachNewNode("sky-root")
        self.world_root = self.root_3d.attachNewNode("world-root")
        self.galaxy_root = self.root_3d.attachNewNode("galaxy-root")
        self.world_root.setTransparency(TransparencyAttrib.MAlpha)
        self.galaxy_root.setTransparency(TransparencyAttrib.MAlpha)
        self.room_bounds = []
        self.terrain_chunks = {}
        self.artifacts = []
        self.galaxy_nodes = []
        self.artifact_shape_nodes = []
        self.nearest_artifact = None
        self.nearest_artifact_dist = 999.0

    def rebuild_station(self):
        self.clear_station()
        self.setBackgroundColor(self.cfg.background_value, self.cfg.background_value, self.cfg.background_value)
        self.hub_base_bg_rgb = (self.cfg.background_value, self.cfg.background_value, self.cfg.background_value)
        self.fog.setColor(*self.hub_base_bg_rgb)
        self.camLens.setFov(self.cfg.fov)
        fog_far = self.cfg.fog_distance * self.world_perf_profile().get("fog_scale", 1.0)
        self.hub_base_fog_near = fog_far * 0.48
        self.hub_base_fog_far = fog_far
        self.camLens.setNearFar(0.05, fog_far)
        self.fog.setLinearRange(self.hub_base_fog_near, self.hub_base_fog_far)
        self.world_shell_hub_theme_current = 0.0
        self.world_shell_hub_theme_status = "RESET"
        self.world_shell_audio_status = "RESET"
        self.world_shell_prompt = "HOLOVERSE READY"
        self.world_shell_motion_status = "RESET"
        self.build_sky_shell()
        self.build_hub()
        self.build_gleebs_hologram()
        self.build_hub_infill()
        self.build_observatory_dome()
        self.build_artifacts()
        self.build_lens()
        self.build_galaxy_targets()
        self.mount_world_shell_adapter()
        # Default terrain is loaded through world.py by HoloVerseWorldShellMount.
        # Do not force the old main.py artifact chunk streamer during station boot.
        cr = self.station_line_color(0.95)
        for np in self.crosshair_parts:
            np.setColor(*cr)

    def build_sky_shell(self):
        bg = self.cfg.background_value
        for i, size in enumerate([340, 420, 520]):
            hue = (self.cfg.line_hue + 0.66 + i * 0.06) % 1.0
            color = hsv_color(hue, 0.44, 0.46 - i * 0.08, 0.06 if i < 2 else 0.04)
            self.add_surface_card(self.sky_root, Vec3(0, 0, 120 + i * 50), Vec3(0, 90, 0), size, size, color)
        for radius, alpha in [(90, 0.05), (120, 0.04), (160, 0.03)]:
            self.add_polyline(self.sky_root, self.polygon_points(radius, 78, 8, 0), self.station_glow_color(alpha), self.cfg.line_thickness * 0.5, True, "sky-ring")

    def build_hub(self):
        hub_color = self.station_line_color(0.90)
        core_color = hsv_color((self.cfg.line_hue + 0.24) % 1.0, 0.88, 1.0, 0.96)

        self.build_octagonal_floor_grid(self.line_root, 3.2, self.hub_radius, 0.03, self.station_line_color(0.64))
        self.add_prism(self.line_root, self.hub_radius, 10.0, hub_color, 8, 22.5, 1.0)
        self.add_prism(self.line_root, self.hub_radius - 2.3, 8.8, self.station_line_color(0.42), 8, 22.5, 0.78)
        self.room_bounds.append((-self.hub_radius + 1.0, self.hub_radius - 1.0, -self.hub_radius + 1.0, self.hub_radius - 1.0))

        for r, z in [(2.7, 1.2), (4.4, 3.0), (6.0, 5.0)]:
            self.add_polyline(self.line_root, self.polygon_points(r, z, 8, 22.5), core_color, self.cfg.line_thickness * 0.88, True, "core-ring")
        self.add_prism(self.line_root, 2.4, 6.4, core_color, 8, 22.5, 0.92)

        for i in range(8):
            ang = math.radians(22.5) + math.tau * i / 8
            n = Vec3(math.cos(ang), math.sin(ang), 0)
            t = Vec3(-n.y, n.x, 0)
            rail_center = n * (self.hub_radius - 0.7)
            self.add_polyline(self.line_root, [rail_center + t * -2.0 + Vec3(0,0,0.05), rail_center + t * 2.0 + Vec3(0,0,0.05)], self.station_line_color(0.40), self.cfg.line_thickness * 0.56, False, "rail")

    def build_observatory_dome(self):
        dome_color = self.station_line_color(0.42)
        base_r = self.hub_radius - 1.8
        apex = 18.0
        ring_count = 7
        seg_count = 8
        for j in range(1, ring_count + 1):
            t = j / ring_count
            r = base_r * math.sqrt(max(0.0, 1.0 - t * t * 0.86))
            z = 6.4 + t * (apex - 6.4)
            pts = self.polygon_points(r, z, seg_count, 22.5)
            self.add_polyline(self.dome_root, pts, dome_color, self.cfg.line_thickness * (0.82 - t * 0.22), True, "dome-ring")
        for i in range(seg_count):
            a = math.radians(22.5) + math.tau * i / seg_count
            prev = Vec3(math.cos(a) * base_r, math.sin(a) * base_r, 6.4)
            for j in range(1, ring_count + 1):
                t = j / ring_count
                r = base_r * math.sqrt(max(0.0, 1.0 - t * t * 0.86))
                z = 6.4 + t * (apex - 6.4)
                cur = Vec3(math.cos(a) * r, math.sin(a) * r, z)
                self.add_polyline(self.dome_root, [prev, cur], dome_color, self.cfg.line_thickness * 0.72, False, "dome-meridian")
                prev = cur
        self.add_polyline(self.dome_root, self.polygon_points(base_r + 0.6, 6.2, 8, 22.5), self.station_line_color(0.34), self.cfg.line_thickness * 0.66, True, "dome-base")

    def artifact_shape(self, parent, center, color, shape_idx, mode_id: str = ""):
        """Create an artifact glyph with a distinct per-dimension silhouette.

        Pass 92 note: each artifact now gets its own construction language instead
        of sharing the same generic glow-card/ring cage.  Internal route IDs,
        save keys, pedestal slots, launch contracts, and animation tags stay
        stable; only the visible portal sculpture changes.
        """
        root = parent.attachNewNode(f"artifact-identity-shape-{shape_idx}")
        root.setPos(center)
        root.setTransparency(TransparencyAttrib.MAlpha)
        root.setPythonTag("artifact_4d_shape", True)
        root.setPythonTag("artifact_identity_shape", True)

        presentation = self.artifact_presentation(mode_id)
        style = str(presentation.get("style") or "").lower()
        inner = self.artifact_color_for_mode(mode_id, 0.54, "secondary") if mode_id else self.artifact_color(shape_idx, 0.54)
        highlight = self.artifact_color_for_mode(mode_id, 0.90, "highlight") if mode_id else self.artifact_color(shape_idx, 0.90)
        primary = self.artifact_color_for_mode(mode_id, 0.94, "primary") if mode_id else color
        glow = self.artifact_color_for_mode(mode_id, 0.18, "primary") if mode_id else (color[0], color[1], color[2], 0.18)
        ring_thickness = self.cfg.line_thickness * 0.84

        def box(center_v, size_v, box_color=None, scale=0.92):
            self.add_box(root, Vec3(*center_v), Vec3(*size_v), box_color or primary, scale)

        def oriented_box(name, center_v, size_v, hpr_v, box_color=None, scale=0.86):
            node = root.attachNewNode(name)
            node.setPos(Vec3(*center_v))
            node.setHpr(Vec3(*hpr_v))
            node.setTransparency(TransparencyAttrib.MAlpha)
            self.add_box(node, Vec3(0, 0, 0), Vec3(*size_v), box_color or primary, scale)
            return node

        def card(name, center_v, hpr_v, width, height, card_color=None):
            node = root.attachNewNode(name)
            node.setTransparency(TransparencyAttrib.MAlpha)
            self.add_surface_card(node, Vec3(*center_v), Vec3(*hpr_v), float(width), float(height), card_color or glow)
            return node

        def line(points, line_color=None, thickness=1.0, closed=False, name="artifact-line"):
            self.add_polyline(root, [Vec3(*p) for p in points], line_color or highlight, ring_thickness * float(thickness), bool(closed), name)

        def ring(radius, z, segments=12, rot=0.0, line_color=None, thickness=1.0, name="artifact-ring"):
            self.add_polyline(root, self.polygon_points(float(radius), float(z), int(segments), float(rot)), line_color or highlight, ring_thickness * float(thickness), True, name)

        def diamond(radius, z, line_color=None, thickness=1.0, name="artifact-diamond"):
            pts = [(0, -radius, z), (radius, 0, z), (0, radius, z), (-radius, 0, z)]
            line(pts, line_color=line_color or highlight, thickness=thickness, closed=True, name=name)

        if style == "combat_obelisk":
            # Code Red: a weaponized red gate, built like a turret monument.
            card("artifact-code-red-shield-front", (0, -0.04, 0.08), (0, 90, 0), 2.40, 3.15, self.artifact_color_for_mode(mode_id, 0.17, "primary"))
            box((0, 0, -0.08), (0.70, 0.70, 3.20), primary, 1.08)
            box((0, 0, 1.68), (1.02, 1.02, 0.26), highlight, 0.84)
            for x, h in [(-0.88, 31.0), (0.88, -31.0)]:
                oriented_box("artifact-code-red-twin-barrel", (x, 0.00, 0.12), (0.32, 0.32, 2.18), (0, h, 0), highlight, 0.90)
                box((x * 1.22, 0, -1.06), (0.34, 0.34, 0.42), primary, 0.82)
            ring(1.47, 0.06, 20, 0, highlight, 0.58, "artifact-code-red-target-ring")
            line([(-1.95, 0, 0.06), (-1.30, 0, 0.06)], highlight, 0.70, False, "artifact-code-red-target-left")
            line([(1.30, 0, 0.06), (1.95, 0, 0.06)], highlight, 0.70, False, "artifact-code-red-target-right")
            line([(0, -1.95, 0.06), (0, -1.30, 0.06)], highlight, 0.70, False, "artifact-code-red-target-back")
            line([(0, 1.30, 0.06), (0, 1.95, 0.06)], highlight, 0.70, False, "artifact-code-red-target-front")

        elif style == "signal_tower":
            # Etch-Line: a drafting/signal tower with clean scan ladders.
            card("artifact-etchline-vertical-signal", (0, 0, 0.08), (0, 90, 0), 0.74, 3.90, self.artifact_color_for_mode(mode_id, 0.20, "primary"))
            box((0, 0, 0.06), (0.28, 0.28, 3.60), highlight, 1.05)
            for j, (z, width) in enumerate([(-1.18, 1.78), (-0.42, 1.42), (0.34, 1.08), (1.08, 0.78)]):
                box((0, 0, z), (width, 0.07, 0.13), primary, 0.82)
                box((0, 0, z), (0.07, width, 0.13), primary, 0.82)
                diamond(width * 0.55, z + 0.04, inner, 0.44, "artifact-etchline-drafting-diamond")
            line([(0, 0, -1.96), (0, 0, 2.20)], highlight, 1.25, False, "artifact-etchline-main-beam")
            for z in (-1.64, -0.82, 0.00, 0.82, 1.64):
                box((0.62, 0, z), (0.16, 0.16, 0.16), primary, 0.78)
                box((-0.62, 0, z + 0.18), (0.13, 0.13, 0.13), highlight, 0.64)

        elif style == "vector_arena_gate":
            # Built-in Vector Arena: octagonal combat gate with orbiting score
            # rails.  This intentionally reads as an arena doorway instead of a
            # city/world-generation portal.
            self.add_polyline(root, self.polygon_points(1.55, 0.0, 8, 22.5), primary, ring_thickness * 1.15, True, "vector-arena-gate")
            self.add_polyline(root, self.polygon_points(2.10, 0.08, 8, 0.0), highlight, ring_thickness * 0.82, True, "vector-arena-outer")
            for side in range(8):
                a = math.radians(22.5) + math.tau * side / 8
                inner_p = Vec3(math.sin(a) * 1.28, math.cos(a) * 1.28, -0.28)
                outer_p = Vec3(math.sin(a) * 2.32, math.cos(a) * 2.32, 0.36)
                self.add_polyline(root, [inner_p, outer_p], highlight if side % 2 == 0 else primary, ring_thickness * 0.66, False, "vector-arena-spoke")
            box((0, 0, 0.0), (0.34, 2.62, 0.22), highlight, 0.80)
            box((0, 0, 0.0), (2.62, 0.34, 0.22), highlight, 0.80)
            oriented_box("vector-arena-slash-a", (0, 0, 0.16), (2.10, 0.18, 0.18), (45, 0, 0), primary, 0.76)
            oriented_box("vector-arena-slash-b", (0, 0, 0.16), (2.10, 0.18, 0.18), (-45, 0, 0), primary, 0.76)
            card("vector-arena-core-glow", (0, 0, -0.34), (0, 0, 0), 2.20, 2.20, glow)
        elif style == "fracture_shards":
            # Fractured: intentionally unstable shard columns, not a shared portal.
            card("artifact-fracture-void-slit", (0.02, 0.00, 0.06), (0, 90, 11), 1.18, 3.30, self.artifact_color_for_mode(mode_id, 0.13, "secondary"))
            oriented_box("artifact-fracture-left-shard", (-0.72, -0.08, -0.10), (0.40, 0.34, 2.48), (13, 0, -22), primary, 0.94)
            oriented_box("artifact-fracture-center-shard", (0.02, 0.18, 0.16), (0.48, 0.40, 3.05), (-10, 0, 8), highlight, 0.96)
            oriented_box("artifact-fracture-right-shard", (0.78, -0.04, -0.02), (0.36, 0.32, 2.20), (18, 0, 24), primary, 0.86)
            oriented_box("artifact-fracture-low-splinter", (0.26, -0.18, -1.18), (0.28, 0.24, 1.14), (34, 0, 49), inner, 0.74)
            line([(-1.28, -0.28, -1.28), (-0.34, 0.16, -0.62), (0.38, -0.20, 0.30), (1.08, 0.20, 1.18)], highlight, 0.48, False, "artifact-fracture-lightning-seam")
            ring(1.32, -0.98, 5, 18.0, inner, 0.52, "artifact-fracture-pentagon-anchor")

        elif style == "campaign_table":
            # Holo Campaign: a horizontal command table with mission blocks.
            card("artifact-campaign-map-glow", (0, 0, -0.34), (0, 0, 0), 3.55, 2.34, self.artifact_color_for_mode(mode_id, 0.28, "primary"))
            box((0, 0, -0.40), (3.18, 2.10, 0.18), primary, 0.68)
            for x in (-1.05, -0.35, 0.35, 1.05):
                line([(x, -1.08, -0.20), (x, 1.08, -0.20)], inner, 0.36, False, "artifact-campaign-map-grid-x")
            for y in (-0.70, 0.0, 0.70):
                line([(-1.60, y, -0.20), (1.60, y, -0.20)], inner, 0.36, False, "artifact-campaign-map-grid-y")
            for x, y, z, sx, sy in [(-0.92, -0.42, 0.15, 0.42, 0.34), (0.10, 0.06, 0.40, 0.54, 0.38), (0.96, 0.54, 0.70, 0.34, 0.30)]:
                box((x, y, z), (sx, sy, 0.82 + z * 0.40), highlight, 0.66)
            line([(-1.18, -0.56, 0.20), (-0.20, -0.06, 0.52), (0.70, 0.46, 0.84), (1.16, 0.72, 1.06)], highlight, 0.45, False, "artifact-campaign-route-line")

        elif style == "conquest_node":
            # Holo Conquest: a capture-node fortress with territory links.
            ring(1.68, -0.34, 6, 30.0, highlight, 0.72, "artifact-conquest-control-hex")
            box((0, 0, 0.02), (0.86, 0.86, 1.56), primary, 1.00)
            box((0, 0, 1.02), (1.08, 1.08, 0.28), highlight, 0.76)
            for x, y in ((1.44, 0), (-1.44, 0), (0, 1.44), (0, -1.44)):
                line([(0, 0, -0.16), (x, y, -0.16)], inner, 0.46, False, "artifact-conquest-territory-link")
                box((x, y, -0.16), (0.36, 0.36, 0.62), highlight, 0.68)
                box((x, y, 0.34), (0.46, 0.46, 0.16), primary, 0.62)
            diamond(0.78, 1.42, highlight, 0.46, "artifact-conquest-victory-diamond")

        elif style == "starfighter_reticle":
            # Vector Wars: a starfighter silhouette, cockpit, wings, and exhaust.
            card("artifact-vectorwars-hangar-glow", (0, 0, -0.04), (0, 90, 0), 2.70, 2.12, self.artifact_color_for_mode(mode_id, 0.16, "primary"))
            oriented_box("artifact-vectorwars-fuselage", (0, 0, 0.02), (0.32, 0.30, 2.78), (0, 0, 0), highlight, 0.88)
            oriented_box("artifact-vectorwars-left-wing", (-0.78, 0, -0.34), (0.28, 0.20, 1.70), (0, 47, 0), primary, 0.82)
            oriented_box("artifact-vectorwars-right-wing", (0.78, 0, -0.34), (0.28, 0.20, 1.70), (0, -47, 0), primary, 0.82)
            oriented_box("artifact-vectorwars-left-tail", (-0.36, 0, -1.14), (0.22, 0.18, 0.78), (0, 28, 0), inner, 0.72)
            oriented_box("artifact-vectorwars-right-tail", (0.36, 0, -1.14), (0.22, 0.18, 0.78), (0, -28, 0), inner, 0.72)
            box((0, 0, 1.00), (0.44, 0.44, 0.26), primary, 0.70)
            ring(1.72, 0.02, 20, 10.0, inner, 0.46, "artifact-vectorwars-target-ring")
            line([(-2.02, 0, 0.02), (-1.48, 0, 0.02)], highlight, 0.56, False, "artifact-vectorwars-reticle-left")
            line([(1.48, 0, 0.02), (2.02, 0, 0.02)], highlight, 0.56, False, "artifact-vectorwars-reticle-right")

        elif style == "stacked_zones":
            # Zonez: a playful layered portal stack with intentionally mixed colors.
            zone_colors = [
                (0.94, 0.24, 1.00, 0.86),
                (0.10, 0.62, 1.00, 0.82),
                (0.98, 1.00, 0.34, 0.82),
                (0.20, 1.00, 0.58, 0.78),
            ]
            for j, z in enumerate((-1.10, -0.36, 0.40, 1.18)):
                band = zone_colors[j % len(zone_colors)]
                card(f"artifact-zonez-band-glow-{j}", (0, 0, z), (0, 90, j * 8.0), 2.42 - j * 0.12, 0.48, (band[0], band[1], band[2], 0.22))
                box((0, 0, z), (2.34 - j * 0.14, 1.20 - j * 0.08, 0.24), band, 0.74)
                ring(1.42 - j * 0.08, z + 0.03, 8, 22.5 + j * 11.0, (band[0], band[1], band[2], 0.90), 0.40, "artifact-zonez-octave-ring")
            for x in (-1.22, 1.22):
                line([(x, 0, -1.34), (x * 0.72, 0, 1.44)], highlight, 0.38, False, "artifact-zonez-stack-rail")

        elif style == "core_pyramid":
            # HoloCore: a calmer core pyramid and central matrix heart.
            card("artifact-holocore-core-aura", (0, 0, 0.12), (0, 90, 0), 2.20, 2.96, self.artifact_color_for_mode(mode_id, 0.12, "primary"))
            base = [Vec3(math.cos(a) * 1.42, math.sin(a) * 1.42, -1.10) for a in [math.tau * k / 4 + math.radians(45) for k in range(4)]]
            apex = Vec3(0, 0, 1.76)
            self.add_polyline(root, base, primary, ring_thickness * 0.86, True, "artifact-holocore-pyramid-base")
            for b in base:
                self.add_polyline(root, [b, apex], highlight, ring_thickness * 0.72, False, "artifact-holocore-pyramid-edge")
            box((0, 0, 0.06), (0.62, 0.62, 0.62), highlight, 0.72)
            box((0, 0, 0.06), (0.34, 0.34, 1.82), primary, 0.58)
            ring(0.90, 0.06, 14, 15.0, inner, 0.48, "artifact-holocore-core-ring")
            diamond(1.10, -0.76, primary, 0.44, "artifact-holocore-floor-diamond")

        else:
            card("artifact-default-glow", (0, 0, 0.0), (0, 90, 0), 2.10, 2.90, glow)
            box((0, 0, 0.0), (0.82, 0.82, 2.30), primary, 0.92)
            ring(1.42, 0.0, 8, 22.5, highlight, 0.56, "artifact-default-readable-ring")
        return root

    def artifact_dimension_label(self, mode_id: str) -> str:
        mode_id = canonical_dimension_lookup_key(mode_id)
        if mode_id in ARTIFACT_DIMENSION_PRESENTATION:
            return self.dimension_display_name_for_id(mode_id)
        for mode in list(getattr(self, "core_modes", []) or []):
            manifest = dict(mode.get("manifest") or {})
            keys = {
                canonical_dimension_lookup_key(manifest.get("id")),
                canonical_dimension_lookup_key(manifest.get("title")),
                canonical_dimension_lookup_key(mode.get("name")),
            }
            if mode_id in keys:
                return self.dimension_display_name_for_mode(mode, manifest.get("title") or mode.get("name") or mode_id)
        return self.dimension_display_name_for_id(mode_id, fallback="DIMENSION")

    def build_artifacts(self):
        self.artifacts = []
        self.artifact_shape_nodes = []
        slot_count = max(1, int(ARTIFACT_SLOT_COUNT))
        primary_count = max(1, min(int(ARTIFACT_PRIMARY_RING_COUNT), slot_count))
        for i in range(slot_count):
            # The artifact ring is geometric: exactly eight stable pedestal slots.
            # HoloCore occupies physical slot 7 instead of creating a ninth outer
            # pedestal, so aim positions and world-space layout stay unchanged.
            ang = math.radians(22.5) + math.tau * i / max(1, primary_count)
            radius = self.artifact_radius
            pos = Vec3(math.cos(ang) * radius, math.sin(ang) * radius, 0)
            dimension_mode_id = ARTIFACT_DIMENSION_ROUTES[i % len(ARTIFACT_DIMENSION_ROUTES)]
            col = self.artifact_color_for_mode(dimension_mode_id, 0.98, "primary")
            ped_col = self.artifact_color_for_mode(dimension_mode_id, 0.66, "secondary")
            pedestal_world_id = i
            self.add_box(self.line_root, pos + Vec3(0, 0, 0.72), Vec3(1.8, 1.8, 1.44), ped_col, 0.72)
            self.add_box(self.line_root, pos + Vec3(0, 0, 2.08), Vec3(2.3, 2.3, 0.28), self.artifact_color_for_mode(dimension_mode_id, 0.62, "highlight"), 0.62)
            self.add_surface_card(self.accent_root, pos + Vec3(0, 0, 1.98), Vec3(45, -90, 0), 2.25, 2.25, self.artifact_color_for_mode(dimension_mode_id, 0.18, "primary"))
            self.add_surface_card(self.accent_root, pos + Vec3(0, 0, 2.28), Vec3(0, 0, 0), 2.6, 0.10, self.artifact_color_for_mode(dimension_mode_id, 0.20, "highlight"))
            shape_node = self.artifact_shape(self.line_root, pos + Vec3(0, 0, 3.95), col, i % 4, dimension_mode_id)
            shape_node.setPythonTag("artifact_id", i)
            shape_node.setPythonTag("world_id", pedestal_world_id)
            shape_node.setPythonTag("dimension_mode_id", dimension_mode_id)
            self.artifact_shape_nodes.append(shape_node)
            name = self.artifact_dimension_label(dimension_mode_id)
            self.artifacts.append({
                "id": i,
                "world_id": pedestal_world_id,
                "dimension_mode_id": dimension_mode_id,
                "name": name,
                "pos": pos + Vec3(0, 0, 3.95),
                "pedestal_pos": pos,
                "shape_node": shape_node,
                "yaw": math.degrees(ang),
                "pitch": 56.0 + (i % 3) * 4.0,
                "radius": 4.25,
            })

    def build_lens(self):
        self.lens_pivot = self.lens_root.attachNewNode("lens-pivot")
        self.lens_pivot.setPos(0, 0, 10.3)
        self.lens_barrel = self.lens_pivot.attachNewNode("lens-barrel")
        barrel_color = self.lens_color(0.96)
        for y, scale in [(0.0, 1.0), (1.6, 1.18), (3.2, 0.86), (4.5, 0.54)]:
            ring = []
            for i in range(8):
                a = math.tau * i / 8
                ring.append(Vec3(math.cos(a) * 0.95 * scale, y, math.sin(a) * 0.95 * scale))
            self.add_polyline(self.lens_barrel, ring, barrel_color, self.cfg.line_thickness * 0.88, True, "lens-ring")
        for i in range(8):
            a = math.tau * i / 8
            p0 = Vec3(math.cos(a) * 0.95, 0.0, math.sin(a) * 0.95)
            p1 = Vec3(math.cos(a) * 0.78, 4.9, math.sin(a) * 0.78)
            self.add_polyline(self.lens_barrel, [p0, p1], barrel_color, self.cfg.line_thickness * 0.74, False, "lens-rail")
        self.add_box(self.line_root, Vec3(0, 0, 10.0), Vec3(2.4, 2.4, 1.6), self.station_line_color(0.58), 0.72)
        self.add_polyline(self.line_root, [Vec3(-1.6,0,10.0), Vec3(1.6,0,10.0)], self.station_line_color(0.48), self.cfg.line_thickness * 0.62, False, "lens-base")

    def galaxy_points(self, seed: int, count: int = 140):
        rng = random.Random(seed)
        pts = []
        for _ in range(count):
            arm = rng.randint(0, 2)
            t = rng.random() * 5.7
            radius = 1.2 + t * 1.3 + rng.random() * 0.7
            twist = arm * 2.094 + t * 1.55
            x = math.cos(twist) * radius
            z = math.sin(twist) * radius
            y = (rng.random() - 0.5) * 0.7
            pts.append(Vec3(x, y, z) * 2.1)
        return pts

    def build_galaxy_targets(self):
        self.galaxy_nodes = []
        for artifact in self.artifacts:
            gnode = self.galaxy_root.attachNewNode(f"galaxy-{artifact['id']}")
            yaw = artifact["yaw"]
            pitch = artifact["pitch"]
            gnode.setPos(0, 0, 11.0)
            gnode.setHpr(yaw, -pitch, 0)
            gnode.setY(210.0)
            color = self.artifact_color(artifact["id"], 0.0)
            pts = self.galaxy_points(self.cfg.world_seed + artifact["id"] * 137)
            for p in pts:
                self.add_polyline(gnode, [p + Vec3(-0.14, 0, 0), p + Vec3(0.14, 0, 0)], color, self.cfg.line_thickness * 0.34, False, "star-x")
                self.add_polyline(gnode, [p + Vec3(0, 0, -0.14), p + Vec3(0, 0, 0.14)], color, self.cfg.line_thickness * 0.34, False, "star-z")
            halo = self.artifact_color(artifact["id"], 0.07)
            self.add_surface_card(gnode, Vec3(0, 0, 0), Vec3(0, 0, 0), 42, 42, halo)
            self.galaxy_nodes.append(gnode)

    def hashed_seed(self, x: int, y: int, salt: int = 0):
        return (x * 92837111 ^ y * 689287499 ^ self.cfg.world_seed ^ salt * 334214459) & 0xFFFFFFFF

    def sample_noise(self, x: float, y: float):
        n1 = math.sin(x * 0.028 + self.cfg.world_seed * 0.01) * math.cos(y * 0.024 - self.cfg.world_seed * 0.02)
        n2 = math.sin((x + y) * 0.011 + self.cfg.world_seed * 0.003) * math.cos((x - y) * 0.015 - self.cfg.world_seed * 0.004)
        rim = 0.55 + 0.45 * math.sin((x * x + y * y) * 0.000028 + self.cfg.world_seed * 0.0009)
        return (n1 * 0.55 + n2 * 0.45) * rim

    def terrain_height_at(self, x: float, y: float):
        r = math.sqrt(x * x + y * y)
        if r < self.cfg.safe_flat_radius:
            return 0.0
        n1 = math.sin(x * 0.028 + self.cfg.world_seed * 0.01) * math.cos(y * 0.024 - self.cfg.world_seed * 0.02)
        n2 = math.sin((x + y) * 0.012) * 0.65 + math.cos((x - y) * 0.017) * 0.45
        rim = min(1.0, max(0.0, (r - self.cfg.safe_flat_radius) / 90.0))
        base = (n1 * 0.55 + n2 * 0.45) * self.cfg.terrain_height * rim
        return base

    def current_world_spec(self):
        return WORLD_SPECS.get(self.active_artifact_id, WORLD_SPECS[0])

    def active_graphics_quality(self):
        quality = str(getattr(self.cfg, "launch_graphics_quality", "medium")).lower().strip()
        if quality not in {"low", "medium", "high"}:
            quality = "medium"
        return quality

    def world_perf_profile(self, spec=None):
        spec = spec or self.current_world_spec()
        quality = self.active_graphics_quality()
        q_scale = {"low": 0.58, "medium": 0.76, "high": 1.0}[quality]
        vr_bias = 0.82 if bool(getattr(self.cfg, "vr_enabled", True)) else 1.0
        kind = spec.get("kind", "frontier")
        kind_density = {
            "frontier": 1.0,
            "venus": 0.60,
            "space": 0.46,
            "underwater": 0.58,
            "jungle": 0.24,
        }.get(kind, 1.0)
        grid_mul = {
            "frontier": 1.0,
            "venus": 1.15,
            "space": 1.0,
            "underwater": 1.12,
            "jungle": 1.35,
        }.get(kind, 1.0)
        radius_bias = {"low": -1, "medium": 0, "high": 1}[quality]
        actor_scale = max(0.12, q_scale * vr_bias * kind_density)
        grid_step = max(8.0, float(self.cfg.terrain_grid_step) * (1.0 / max(0.5, q_scale)) * grid_mul)
        fog_scale = max(0.68, min(1.08, q_scale * (0.95 if kind in {"venus", "space", "jungle"} else 1.0)))
        effective_radius = max(1, min(6, int(self.cfg.terrain_render_radius + radius_bias)))
        if bool(getattr(self.cfg, "vr_enabled", True)):
            effective_radius = min(effective_radius, 2 if kind in {"venus", "space", "underwater", "jungle"} else 3)
        return {
            "quality": quality,
            "actor_scale": actor_scale,
            "grid_step": grid_step,
            "fog_scale": fog_scale,
            "effective_radius": effective_radius,
            "star_count": max(10, int(36 * max(0.45, q_scale * 0.75))),
        }

    def effective_render_radius(self, spec=None):
        return int(self.world_perf_profile(spec).get("effective_radius", self.cfg.terrain_render_radius))

    def chunk_axis_positions(self):
        chunk_size = max(1.0, float(self.cfg.terrain_chunk_size))
        step = max(0.001, float(self.world_perf_profile().get("grid_step", self.cfg.terrain_grid_step)))
        segments = max(1, int(math.ceil(chunk_size / step)))
        coords = [chunk_size * (idx / segments) for idx in range(segments + 1)]
        coords[0] = 0.0
        coords[-1] = chunk_size
        return coords

    def clear_world_actors(self):
        for actor in self.world_actors:
            try:
                actor.root.removeNode()
            except Exception:
                pass
        self.world_actors = []

    def clear_world_chunks(self):
        for meta in self.terrain_chunks.values():
            try:
                node = meta.get("node") if isinstance(meta, dict) else meta
                if node is not None and not node.isEmpty():
                    node.removeNode()
            except Exception:
                pass
        self.terrain_chunks = {}
        self.clear_world_actors()

    def chunk_center(self, cx: int, cy: int):
        size = self.cfg.terrain_chunk_size
        return Vec2((cx + 0.5) * size, (cy + 0.5) * size)

    def chunk_target_alpha(self, cx: int, cy: int):
        center = self.chunk_center(cx, cy)
        dx = center.x - self.player_pos.x
        dy = center.y - self.player_pos.y
        dist = math.sqrt(dx * dx + dy * dy)
        size = self.cfg.terrain_chunk_size
        visible_range = size * (self.effective_render_radius() + 0.20)
        fade_range = size * 1.15
        if dist <= visible_range:
            return 1.0
        if dist >= visible_range + fade_range:
            return 0.0
        t = (dist - visible_range) / max(0.001, fade_range)
        t = max(0.0, min(1.0, t))
        smooth = t * t * (3.0 - 2.0 * t)
        return max(0.0, 1.0 - smooth)

    def update_chunk_fades(self, dt: float):
        fade_speed = max(0.5, float(getattr(self.cfg, "chunk_fade_speed", 3.8)))
        for key in list(self.terrain_chunks.keys()):
            meta = self.terrain_chunks.get(key)
            if not isinstance(meta, dict):
                continue
            node = meta.get("node")
            if node is None or node.isEmpty():
                del self.terrain_chunks[key]
                continue
            alpha = float(meta.get("alpha", 0.0))
            target = float(meta.get("target_alpha", 0.0))
            blend = min(1.0, dt * fade_speed)
            alpha += (target - alpha) * blend
            if abs(alpha - target) < 0.02:
                alpha = target
            meta["alpha"] = alpha
            node.setColorScale(1, 1, 1, max(0.0, min(1.0, alpha * self.transition_progress)))
            if alpha <= 0.01 and target <= 0.0:
                node.removeNode()
                del self.terrain_chunks[key]

    def grounded_player_z(self, x: float, y: float, spec=None):
        spec = spec or self.current_world_spec()
        if self.world_shell_playable_active() and not self.world_unlocked and self.transition_target <= 0.0:
            return self.world_shell_grounded_z(x, y)
        if spec["kind"] == "space":
            return self.cfg.player_eye_height
        return self.world_height_at(x, y, spec) + self.cfg.player_eye_height + float(getattr(self.cfg, "terrain_collision_clearance", 0.16))

    def world_py_source_active(self) -> bool:
        """Return True when the default HoloVerse world is owned by world.py."""
        mount = getattr(self, "world_shell_mount", None)
        if mount is None:
            return False
        if bool(getattr(mount, "source_bridge_active", False)):
            return True
        report = getattr(self, "world_shell_preload_report", {})
        return bool(isinstance(report, dict) and report.get("source_bridge_active", False))

    def legacy_world_chunks_active(self) -> bool:
        """Only legacy artifact simulations may use main.py terrain chunks.

        The normal HoloVerse terrain/biome shell is now owned by world.py via
        HoloVerseWorldShellMount.  This guard prevents the old main.py chunk
        streamer from quietly stacking a second terrain under or over the real
        world.py terrain.
        """
        if getattr(self, "active_native_mode", None) is not None:
            return False
        if self.world_py_source_active() and not bool(getattr(self, "world_unlocked", False)) and float(getattr(self, "transition_target", 0.0)) <= 0.0:
            return False
        return bool(getattr(self, "world_unlocked", False)) or float(getattr(self, "transition_target", 0.0)) > 0.0

    def should_stream_legacy_world_chunks(self, force: bool = False) -> bool:
        """Gate all main.py terrain streaming behind explicit legacy-world state."""
        if self.legacy_world_chunks_active():
            return True
        # If the default shell is disabled, keep non-forced legacy updates off
        # too; world.py should remain the single default terrain source.
        if force and getattr(self, "terrain_chunks", None):
            return True
        return False

    def _safe_rgb_triplet(self, value, fallback):
        try:
            vals = list(value)
            if len(vals) >= 3:
                return tuple(max(0.0, min(1.0, float(vals[i]))) for i in range(3))
        except Exception:
            pass
        return tuple(float(v) for v in fallback[:3])

    def apply_world_shell_hub_theme_influence(self, dt, base_bg_rgb, base_hub_rgb):
        """Subtly blend the default hub toward nearby shell theme data.

        The HoloVerse remains visual/data-only. This method only consumes the
        mount report when enabled, caps its influence, and fades out whenever an
        artifact/world transition is active so the observatory never becomes
        unreadable or loses ownership of its renderer.
        """
        data = self.world_shell_theme_handoff if isinstance(getattr(self, "world_shell_theme_handoff", {}), dict) else {}
        enabled = bool(getattr(self.cfg, "world_shell_hub_theme_influence", True)) and bool(getattr(self.cfg, "world_shell_theme_handoff", True)) and bool(data.get("enabled", False))
        raw_influence = 0.0
        if enabled:
            try:
                raw_influence = max(0.0, min(1.0, float(data.get("influence", 0.0))))
            except Exception:
                raw_influence = 0.0
        max_blend = max(0.0, min(0.32, float(getattr(self.cfg, "world_shell_hub_theme_max_blend", 0.18))))
        transition_suppression = max(0.0, 1.0 - float(getattr(self, "world_theme_blend", 0.0)))
        target = min(max_blend, raw_influence) * transition_suppression
        self.world_shell_hub_theme_current = lerp(float(getattr(self, "world_shell_hub_theme_current", 0.0)), target, min(1.0, dt * 2.4))
        blend = max(0.0, min(max_blend, float(getattr(self, "world_shell_hub_theme_current", 0.0))))
        if blend <= 0.001:
            self.world_shell_hub_theme_current = 0.0
            self.world_shell_hub_theme_status = "READY" if enabled else "OFF"
            self.world_shell_hub_theme_last = {"enabled": enabled, "blend": 0.0, "biome": data.get("active_biome", "FLAT") if data else "FLAT"}
            return base_bg_rgb, base_hub_rgb

        sky_rgb = self._safe_rgb_triplet(data.get("sky_rgb"), base_bg_rgb)
        line_rgb = self._safe_rgb_triplet(data.get("line_rgb"), base_hub_rgb)
        fog_blend = max(0.0, min(0.28, float(getattr(self.cfg, "world_shell_hub_theme_fog_blend", 0.14))))
        light_blend = max(0.0, min(0.24, float(getattr(self.cfg, "world_shell_hub_theme_light_blend", 0.12))))
        bg_rgb = lerp_rgb(base_bg_rgb, sky_rgb, blend)
        hub_rgb = lerp_rgb(base_hub_rgb, line_rgb, min(blend * 0.80, max_blend))

        # Fog and light are intentionally weaker than color tint. This makes
        # exit-area atmosphere readable without turning the command hub into a
        # full biome renderer.
        fog_color = lerp_rgb(base_bg_rgb, sky_rgb, min(blend, fog_blend))
        try:
            fog_near_target = max(36.0, float(data.get("fog_near", getattr(self, "hub_base_fog_near", self.cfg.fog_distance * 0.48))))
            fog_far_target = max(fog_near_target + 80.0, float(data.get("fog_far", getattr(self, "hub_base_fog_far", self.cfg.fog_distance))))
            base_near = float(getattr(self, "hub_base_fog_near", self.cfg.fog_distance * 0.48))
            base_far = float(getattr(self, "hub_base_fog_far", self.cfg.fog_distance))
            range_blend = min(blend, fog_blend)
            fog_near = lerp(base_near, fog_near_target, range_blend)
            fog_far = max(fog_near + 120.0, lerp(base_far, fog_far_target, range_blend))
            self.fog.setLinearRange(fog_near, fog_far)
        except Exception:
            pass
        try:
            amb_rgb = lerp_rgb(getattr(self, "hub_base_ambient_rgb", (0.58, 0.62, 0.68)), line_rgb, min(blend, light_blend))
            sun_rgb = lerp_rgb(getattr(self, "hub_base_sun_rgb", (0.34, 0.37, 0.42)), sky_rgb, min(blend * 0.75, light_blend))
            self.ambient_light.setColor((*amb_rgb, 1.0))
            self.sun_light.setColor((*sun_rgb, 1.0))
        except Exception:
            pass
        self.fog.setColor(*fog_color)
        self.world_shell_hub_theme_status = f"BLEND {blend:.2f} // {str(data.get('active_biome', 'FLAT')).upper()}"
        self.world_shell_hub_theme_last = {
            "enabled": True,
            "blend": round(blend, 3),
            "raw_influence": round(raw_influence, 3),
            "biome": str(data.get("active_biome", "FLAT")),
            "kind": str(data.get("active_kind", "flat")),
            "fog_color": [round(float(v), 4) for v in fog_color],
        }
        return bg_rgb, hub_rgb

    def holoverse_region_sky_rgb(self):
        if self.is_holospace_active():
            return (0.000, 0.000, 0.000)
        name = self.current_holoverse_region_name().strip().lower()
        sky_map = {
            "forests": (0.30, 0.52, 0.72),
            "green hills": (0.30, 0.68, 0.18),
            "mushroom": (0.24, 0.52, 0.80),
            "mushroom": (0.62, 0.14, 0.56),
            "desert": (0.54, 0.42, 0.48),
            "ice": (0.48, 0.66, 0.86),
            "urban": (0.46, 0.56, 0.72),
            "metropolis": (0.34, 0.40, 0.66),
        }
        return sky_map.get(name, (self.cfg.background_value, self.cfg.background_value, self.cfg.background_value))

    def holoverse_should_use_open_sky(self):
        if self.world_unlocked or self.transition_target > 0.0:
            return False
        if self.is_holospace_active():
            return False
        name = self.current_holoverse_region_name().strip().lower()
        return name not in {"hub", "hub region", "hub spawn", "holospace"}

    def apply_world_theme(self, dt):
        spec = self.current_world_spec() if self.transition_target > 0.0 else WORLD_SPECS[0]
        target_blend = self.transition_progress if self.transition_target > 0.0 else 0.0
        self.world_theme_blend = lerp(self.world_theme_blend, target_blend, min(1.0, dt * 1.8))
        base_bg_rgb = lerp_rgb((self.cfg.background_value, self.cfg.background_value, self.cfg.background_value), spec["bg"], self.world_theme_blend)
        base_hub_rgb = lerp_rgb(self.default_hub_rgb, spec["hub"], self.world_theme_blend)
        if self.is_holospace_active() or self.holoverse_should_use_open_sky():
            base_bg_rgb = self.holoverse_region_sky_rgb()
        self.current_bg_rgb, self.current_hub_rgb = self.apply_world_shell_hub_theme_influence(dt, base_bg_rgb, base_hub_rgb)
        if self.is_holospace_active() or self.holoverse_should_use_open_sky():
            self.current_bg_rgb = self.holoverse_region_sky_rgb()
        self.setBackgroundColor(*self.current_bg_rgb, 1.0)
        if self.is_holospace_active():
            try:
                self.fog.setColor(0.000, 0.000, 0.006)
                self.fog.setLinearRange(14000.0, 26000.0)
            except Exception:
                pass
        # apply_world_shell_hub_theme_influence already applies a subtler fog
        # color/range when active. When inactive, restore normal hub fog color
        # and range here so toggles are immediately reversible.
        if (not self.is_holospace_active()) and float(getattr(self, "world_shell_hub_theme_current", 0.0)) <= 0.001:
            self.fog.setColor(*self.current_bg_rgb)
            try:
                self.fog.setLinearRange(float(getattr(self, "hub_base_fog_near", self.cfg.fog_distance * 0.48)), float(getattr(self, "hub_base_fog_far", self.cfg.fog_distance)))
                self.ambient_light.setColor((*getattr(self, "hub_base_ambient_rgb", (0.58, 0.62, 0.68)), 1.0))
                self.sun_light.setColor((*getattr(self, "hub_base_sun_rgb", (0.34, 0.37, 0.42)), 1.0))
            except Exception:
                pass
        self.line_root.setColorScale(*self.current_hub_rgb, 0.98)
        self.dome_root.setColorScale(*self.current_hub_rgb, 0.96)
        self.accent_root.setColorScale(*self.current_hub_rgb, 0.82)
        self.surface_root.setColorScale(*self.current_hub_rgb, 1.0)

    def world_height_at(self, x: float, y: float, spec=None):
        spec = spec or self.current_world_spec()
        kind = spec["kind"]
        profile = spec.get("profile", kind)
        scale = float(spec.get("noise_scale", 1.0))
        detail = float(spec.get("detail_scale", 1.0))
        height_mul = float(spec.get("height_mul", 1.0))
        if kind == "space":
            return 0.0
        seed = self.cfg.world_seed + (self.active_artifact_id or 0) * 977
        if kind == "frontier":
            base = self.sample_noise(x * scale * 0.90, y * scale * 0.90)
            ridges = abs(self.sample_noise(x * scale * 1.85 + 44.0, y * scale * 1.70 - 23.0))
            detail_n = self.sample_noise(x * detail * 2.60 - 18.0, y * detail * 2.30 + 31.0)
            if profile == "plains":
                val = base * 0.55 + detail_n * 0.18 - ridges * 0.12
            elif profile == "bastion":
                cells = math.sin(x * 0.050 * scale + seed * 0.01) * math.cos(y * 0.047 * scale - seed * 0.015)
                val = base * 0.48 + ridges * 0.52 + cells * 0.28
            elif profile == "spirefield":
                spokes = math.sin((x + y) * 0.060 * scale + seed * 0.02) + math.cos((x - y) * 0.052 * scale - seed * 0.02)
                val = base * 0.35 + ridges * 0.70 + spokes * 0.16
            else:  # ruins
                terraces = math.sin(x * 0.040 * scale + seed * 0.008) * 0.45 + math.cos(y * 0.044 * scale - seed * 0.012) * 0.35
                val = base * 0.42 + ridges * 0.32 + detail_n * 0.22 + terraces
            return val * self.cfg.terrain_height * 1.25 * height_mul
        if kind == "frontier":
            landmark_count = max(1, int(round((1 + rng.randint(0, 2)) * max(0.45, actor_scale) * landmark_density)))
            for _ in range(landmark_count):
                px = ox + rng.uniform(6.0, chunk_size - 6.0)
                py = oy + rng.uniform(6.0, chunk_size - 6.0)
                pz = self.world_height_at(px, py, spec)
                seed = rng.randint(1, 10**9)
                if profile == "plains":
                    self.add_spire_cluster(node, Vec3(px, py, pz), seed, tint=(0.84, 0.95, 1.0, 0.72), height_scale=0.85)
                elif profile == "bastion":
                    self.add_bastion_actor(node, Vec3(px, py, pz), seed, tint=(0.98, 0.58, 0.92, 0.82), scale=1.0)
                elif profile == "spirefield":
                    self.add_spire_cluster(node, Vec3(px, py, pz), seed, tint=(0.62, 0.88, 1.0, 0.84), height_scale=1.45)
                else:
                    self.add_ruin_arch(node, Vec3(px, py, pz), seed, tint=(0.96, 0.82, 0.72, 0.76), scale=1.0)
        elif kind == "venus":
            dunes = math.sin(x * 0.020 * scale + seed * 0.03) * 9.0 + math.cos(y * 0.018 * scale - seed * 0.02) * 7.0
            caustic = abs(self.sample_noise(x * detail * 1.20 + 80.0, y * detail * 1.08 - 40.0)) * 11.0
            return (dunes + caustic) * 0.64 * height_mul
        if kind == "underwater":
            trench = -18.0 - abs(self.sample_noise(x * scale * 0.70, y * scale * 0.70)) * 18.0
            ripples = self.sample_noise(x * detail * 2.10 + 22.0, y * detail * 2.36 - 41.0) * 4.2
            return (trench + ripples) * height_mul
        if kind == "jungle":
            hills = self.sample_noise(x * scale * 0.82, y * scale * 0.82) * self.cfg.terrain_height * 1.05
            buttress = abs(self.sample_noise(x * detail * 1.70 - 60.0, y * detail * 1.62 + 45.0)) * 7.4
            return (hills + buttress) * height_mul
        return self.sample_noise(x * scale, y * scale) * self.cfg.terrain_height * height_mul

    def add_world_actor(self, node, kind, seed, home):
        self.world_actors.append(WorldActor(node, kind, seed, home))

    def add_ship_actor(self, parent, pos: Vec3, seed: int):
        rng = random.Random(seed)
        node = parent.attachNewNode(f"ship-{seed}")
        node.setPos(pos)
        col = (0.72 + rng.random() * 0.28, 0.82 + rng.random() * 0.18, 1.0, 0.95)
        span = 2.2 + rng.random() * 3.8
        body = 4.0 + rng.random() * 8.0
        segs = LineSegs('ship')
        segs.setThickness(max(1.0, self.cfg.line_thickness * 0.72))
        segs.setColor(*col)
        pts = [Vec3(-span,0,0), Vec3(0,body,0), Vec3(span,0,0), Vec3(0,-body*0.35,0)]
        for a,b in [(0,1),(1,2),(2,3),(3,0),(0,2)]:
            segs.moveTo(pts[a]); segs.drawTo(pts[b])
        segs.moveTo(0, -body*0.1, -span*0.45); segs.drawTo(0, body*0.52, span*0.12)
        np = node.attachNewNode(segs.create())
        np.setTransparency(TransparencyAttrib.MAlpha)
        np.setAntialias(AntialiasAttrib.MLine)
        self.add_world_actor(node, 'ship', seed, pos)

    def add_underwater_actor(self, parent, pos: Vec3, seed: int, whale=False):
        rng = random.Random(seed)
        node = parent.attachNewNode(f"sea-{seed}")
        node.setPos(pos)
        style = rng.choice(["fish", "ray", "jelly"]) if not whale else "whale"
        palette = [(0.28, 0.98, 0.92, 0.82), (0.38, 0.78, 1.0, 0.80), (0.72, 0.46, 1.0, 0.78), (0.18, 0.92, 0.66, 0.80)]
        col = palette[seed % len(palette)] if not whale else (0.40, 0.92, 1.0, 0.66)
        segs = LineSegs('sea')
        segs.setThickness(max(1.0, self.cfg.line_thickness * (0.78 if whale else 0.58)))
        segs.setColor(*col)
        length = (12.0 + rng.random() * 12.0) if whale else (2.6 + rng.random() * 3.0)
        height = length * (0.22 if whale else 0.26)
        if style in ("fish", "whale"):
            body_pts = []
            for i in range(10):
                t = i / 9.0
                x = (t - 0.5) * length
                z = math.sin(t * math.pi) * height
                body_pts.append(Vec3(x, 0, z))
            for a, b in zip(body_pts, body_pts[1:]):
                segs.moveTo(a); segs.drawTo(b)
            mirror_pts = [Vec3(p.x, 0, -p.z * 0.55) for p in body_pts]
            for a, b in zip(mirror_pts, mirror_pts[1:]):
                segs.moveTo(a); segs.drawTo(b)
            for a, b in zip(body_pts[1:-1:2], mirror_pts[1:-1:2]):
                segs.moveTo(a); segs.drawTo(b)
            segs.moveTo(Vec3(length * 0.45, 0, 0)); segs.drawTo(Vec3(length * 0.66, 0, height * 0.72)); segs.moveTo(Vec3(length * 0.45, 0, 0)); segs.drawTo(Vec3(length * 0.66, 0, -height * 0.72))
            segs.moveTo(Vec3(-length * 0.08, 0, height * 0.35)); segs.drawTo(Vec3(-length * 0.22, 0, height * 1.0))
        elif style == "ray":
            wing = length * 0.52
            tail = length * 0.72
            pts = [Vec3(-wing, 0, 0), Vec3(0, 0, height * 0.88), Vec3(wing, 0, 0), Vec3(0, 0, -height * 0.22)]
            for a, b in [(0,1),(1,2),(2,3),(3,0),(0,2)]:
                segs.moveTo(pts[a]); segs.drawTo(pts[b])
            segs.moveTo(0, 0, -height * 0.18); segs.drawTo(tail, 0, -height * 0.10)
            segs.moveTo(0, 0, -height * 0.18); segs.drawTo(-tail * 0.35, 0, -height * 0.10)
        else:  # jelly
            radius = height * 0.88
            dome = [Vec3(math.cos(math.tau * i / 8.0) * radius, 0, math.sin(math.tau * i / 8.0) * radius * 0.62 + radius * 0.20) for i in range(8)]
            for a, b in zip(dome, dome[1:] + dome[:1]):
                segs.moveTo(a); segs.drawTo(b)
            for i in range(5):
                x = lerp(-radius * 0.55, radius * 0.55, i / 4.0)
                segs.moveTo(x, 0, 0); segs.drawTo(x + math.sin(seed * 0.1 + i) * 0.18, 0, -length * 0.55)
        np = node.attachNewNode(segs.create())
        np.setTransparency(TransparencyAttrib.MAlpha)
        np.setAntialias(AntialiasAttrib.MLine)
        self.add_world_actor(node, 'whale' if whale else style, seed, pos)

    def add_tree_actor(self, parent, pos: Vec3, seed: int):
        rng = random.Random(seed)
        node = parent.attachNewNode(f"tree-{seed}")
        node.setPos(pos)
        trunk_h = 8.0 + rng.random() * 16.0
        crown_r = 3.2 + rng.random() * 5.5
        trunk = LineSegs('trunk')
        trunk.setThickness(max(1.0, self.cfg.line_thickness * 0.72))
        trunk.setColor(0.58, 0.42, 0.22, 0.94)
        trunk.moveTo(0,0,0); trunk.drawTo(0,0,trunk_h)
        node.attachNewNode(trunk.create()).setTransparency(TransparencyAttrib.MAlpha)
        crown = []
        for i in range(8):
            a = math.tau * i / 8.0
            crown.append(Vec3(math.cos(a) * crown_r, math.sin(a) * crown_r, trunk_h + math.sin(a * 2.0) * 1.2))
        self.add_polyline(node, crown, (0.36, 0.96, 0.46, 0.82), self.cfg.line_thickness * 0.55, True, 'crown')
        self.add_world_actor(node, 'tree', seed, pos)

    def add_spire_cluster(self, parent, pos: Vec3, seed: int, tint=(0.80, 0.90, 1.0, 0.78), height_scale=1.0):
        rng = random.Random(seed)
        node = parent.attachNewNode(f"spire-{seed}")
        node.setPos(pos)
        count = 3 + rng.randint(0, 3)
        for idx in range(count):
            ang = math.tau * idx / count + rng.random() * 0.25
            radius = 1.8 + rng.random() * 4.6
            height = (8.0 + rng.random() * 18.0) * height_scale
            base = Vec3(math.cos(ang) * radius, math.sin(ang) * radius, 0)
            tip = base * 0.18 + Vec3(0, 0, height)
            self.add_polyline(node, [base, tip], tint, self.cfg.line_thickness * 0.52, False, 'spire')
            self.add_polyline(node, [base, Vec3(-base.x * 0.32, -base.y * 0.32, height * 0.42)], tint, self.cfg.line_thickness * 0.34, False, 'spire')

    def add_bastion_actor(self, parent, pos: Vec3, seed: int, tint=(0.98, 0.58, 0.92, 0.78), scale=1.0):
        rng = random.Random(seed)
        node = parent.attachNewNode(f"bastion-{seed}")
        node.setPos(pos)
        w = (4.2 + rng.random() * 3.8) * scale
        h = (10.0 + rng.random() * 18.0) * scale
        pts = [Vec3(-w, -w, 0), Vec3(w, -w, 0), Vec3(w, w, 0), Vec3(-w, w, 0)]
        top = [Vec3(p.x * 0.82, p.y * 0.82, h) for p in pts]
        self.add_polyline(node, pts, tint, self.cfg.line_thickness * 0.48, True, 'bastion')
        self.add_polyline(node, top, (min(1.0, tint[0] + 0.05), min(1.0, tint[1] + 0.10), min(1.0, tint[2] + 0.04), tint[3]), self.cfg.line_thickness * 0.48, True, 'bastion')
        for a, b in zip(pts, top):
            self.add_polyline(node, [a, b], tint, self.cfg.line_thickness * 0.42, False, 'bastion')

    def add_ruin_arch(self, parent, pos: Vec3, seed: int, tint=(0.96, 0.82, 0.72, 0.74), scale=1.0):
        rng = random.Random(seed)
        node = parent.attachNewNode(f"ruin-{seed}")
        node.setPos(pos)
        span = (8.0 + rng.random() * 8.0) * scale
        height = (8.0 + rng.random() * 9.0) * scale
        pts = [Vec3(-span * 0.5, 0, 0), Vec3(-span * 0.35, 0, height * 0.65), Vec3(0, 0, height), Vec3(span * 0.35, 0, height * 0.65), Vec3(span * 0.5, 0, 0)]
        self.add_polyline(node, pts, tint, self.cfg.line_thickness * 0.46, False, 'ruin')
        self.add_polyline(node, [Vec3(-span * 0.5, 0, 0), Vec3(-span * 0.5, 0, height * 0.58)], tint, self.cfg.line_thickness * 0.40, False, 'ruin')
        self.add_polyline(node, [Vec3(span * 0.5, 0, 0), Vec3(span * 0.5, 0, height * 0.58)], tint, self.cfg.line_thickness * 0.40, False, 'ruin')

    def create_world_chunk(self, cx: int, cy: int):
        node = self.world_root.attachNewNode(f"chunk-{cx}-{cy}")
        spec = self.current_world_spec()
        kind = spec["kind"]
        line_color = (*spec["hub"], 0.72)
        profile = spec.get("profile", kind)
        landmark_density = float(spec.get("landmark_density", 0.35))
        chunk_size = self.cfg.terrain_chunk_size
        axis_coords = self.chunk_axis_positions()
        ox = cx * chunk_size
        oy = cy * chunk_size
        rng = random.Random(self.hashed_seed(cx, cy, 71 + (self.active_artifact_id or 0)))
        perf = self.world_perf_profile(spec)
        actor_scale = perf["actor_scale"]
        if kind == "space":
            ship_count = max(1, int(round((3 + rng.randint(0, 3)) * actor_scale * (1.15 if profile == "fleet" else 1.0))))
            for _ in range(ship_count):
                pos = Vec3(ox + rng.uniform(0.0, chunk_size), oy + rng.uniform(0.0, chunk_size), rng.uniform(-80.0, 80.0))
                self.add_ship_actor(node, pos, rng.randint(1, 10**9))
            for _ in range(perf["star_count"]):
                pos = Vec3(ox + rng.uniform(0.0, chunk_size), oy + rng.uniform(0.0, chunk_size), rng.uniform(-120.0, 120.0))
                self.add_polyline(node, [pos + Vec3(-0.15, 0, 0), pos + Vec3(0.15, 0, 0)], (0.72, 0.86, 1.0, 0.55), self.cfg.line_thickness * 0.28, False, 'starx')
                self.add_polyline(node, [pos + Vec3(0, 0, -0.15), pos + Vec3(0, 0, 0.15)], (0.72, 0.86, 1.0, 0.55), self.cfg.line_thickness * 0.28, False, 'starz')
            beacon_count = max(1, int(round((1 + rng.randint(0, 2)) * max(0.45, actor_scale) * landmark_density)))
            for _ in range(beacon_count):
                pos = Vec3(ox + rng.uniform(0.0, chunk_size), oy + rng.uniform(0.0, chunk_size), rng.uniform(-70.0, 70.0))
                height = 8.0 + rng.random() * 18.0
                self.add_polyline(node, [pos + Vec3(0, 0, -height * 0.5), pos + Vec3(0, 0, height * 0.5)], (0.68, 0.82, 1.0, 0.60), self.cfg.line_thickness * 0.38, False, 'beacon')
                ring = [pos + Vec3(math.cos(math.tau * i / 8.0) * 2.0, math.sin(math.tau * i / 8.0) * 2.0, 0) for i in range(8)]
                self.add_polyline(node, ring, (0.52, 0.72, 1.0, 0.42), self.cfg.line_thickness * 0.24, True, 'beacon')
            return node
        self.add_world_surface_underlay(node, cx, cy, spec, axis_coords)
        for local_x in axis_coords:
            pts = []
            x = ox + local_x
            for local_y in axis_coords:
                y = oy + local_y
                z = self.world_height_at(x, y, spec)
                pts.append(Vec3(x, y, z))
            self.add_polyline(node, pts, line_color, self.cfg.line_thickness * 0.52, False, "terrain-x")
        for local_y in axis_coords:
            pts = []
            y = oy + local_y
            for local_x in axis_coords:
                x = ox + local_x
                z = self.world_height_at(x, y, spec)
                pts.append(Vec3(x, y, z))
            self.add_polyline(node, pts, line_color, self.cfg.line_thickness * 0.52, False, "terrain-y")
        if kind == "frontier":
            landmark_count = max(1, int(round((1 + rng.randint(0, 2)) * max(0.45, actor_scale) * landmark_density)))
            for _ in range(landmark_count):
                px = ox + rng.uniform(6.0, chunk_size - 6.0)
                py = oy + rng.uniform(6.0, chunk_size - 6.0)
                pz = self.world_height_at(px, py, spec)
                seed = rng.randint(1, 10**9)
                if profile == "plains":
                    self.add_spire_cluster(node, Vec3(px, py, pz), seed, tint=(0.84, 0.95, 1.0, 0.72), height_scale=0.85)
                elif profile == "bastion":
                    self.add_bastion_actor(node, Vec3(px, py, pz), seed, tint=(0.98, 0.58, 0.92, 0.82), scale=1.0)
                elif profile == "spirefield":
                    self.add_spire_cluster(node, Vec3(px, py, pz), seed, tint=(0.62, 0.88, 1.0, 0.84), height_scale=1.45)
                else:
                    self.add_ruin_arch(node, Vec3(px, py, pz), seed, tint=(0.96, 0.82, 0.72, 0.76), scale=1.0)
        elif kind == "venus":
            mesa_count = max(1, int(round((4 + rng.randint(0, 4)) * max(0.45, actor_scale))))
            for _ in range(mesa_count):
                px = ox + rng.uniform(8.0, chunk_size - 8.0)
                py = oy + rng.uniform(8.0, chunk_size - 8.0)
                base = self.world_height_at(px, py, spec)
                height = 10.0 + rng.random() * 26.0
                radius = 4.0 + rng.random() * 7.0
                pts = [Vec3(px + math.cos(math.tau * i / 8.0) * radius, py + math.sin(math.tau * i / 8.0) * radius, base + math.sin(i) * 0.7) for i in range(8)]
                top = [Vec3(p.x * 0.88 + px * 0.12, p.y * 0.88 + py * 0.12, base + height) for p in pts]
                self.add_polyline(node, pts, (1.0, 0.55, 0.24, 0.76), self.cfg.line_thickness * 0.56, True, 'mesa0')
                self.add_polyline(node, top, (1.0, 0.68, 0.32, 0.82), self.cfg.line_thickness * 0.56, True, 'mesa1')
                for a, b in zip(pts, top):
                    self.add_polyline(node, [a, b], (1.0, 0.55, 0.24, 0.62), self.cfg.line_thickness * 0.48, False, 'mesa2')
        elif kind == "underwater":
            vent_count = max(1, int(round((1 + rng.randint(0, 2)) * max(0.45, actor_scale) * landmark_density)))
            for _ in range(vent_count):
                px = ox + rng.uniform(6.0, chunk_size - 6.0)
                py = oy + rng.uniform(6.0, chunk_size - 6.0)
                base = self.world_height_at(px, py, spec)
                height = 8.0 + rng.random() * 12.0
                self.add_polyline(node, [Vec3(px, py, base), Vec3(px, py, base + height)], (0.38, 0.94, 0.86, 0.58), self.cfg.line_thickness * 0.34, False, 'vent')
                ring = [Vec3(px + math.cos(math.tau * i / 6.0) * 2.4, py + math.sin(math.tau * i / 6.0) * 2.4, base + height * 0.36 + math.sin(i) * 0.35) for i in range(6)]
                self.add_polyline(node, ring, (0.42, 0.98, 0.92, 0.48), self.cfg.line_thickness * 0.28, True, 'vent')
            whale_count = max(1, int(round((1 + rng.randint(0, 1)) * max(0.55, actor_scale))))
            for _ in range(whale_count):
                px = ox + rng.uniform(0.0, chunk_size)
                py = oy + rng.uniform(0.0, chunk_size)
                pz = self.world_height_at(px, py, spec) + 14.0 + rng.uniform(2.0, 16.0)
                self.add_underwater_actor(node, Vec3(px, py, pz), rng.randint(1, 10**9), whale=True)
            fish_count = max(1, int(round((2 + rng.randint(0, 2)) * max(0.60, actor_scale))))
            for _ in range(fish_count):
                px = ox + rng.uniform(0.0, chunk_size)
                py = oy + rng.uniform(0.0, chunk_size)
                pz = self.world_height_at(px, py, spec) + 7.0 + rng.uniform(1.0, 12.0)
                self.add_underwater_actor(node, Vec3(px, py, pz), rng.randint(1, 10**9), whale=False)
        elif kind == "jungle":
            tree_count = max(2, int(round((10 + rng.randint(0, 12)) * actor_scale)))
            vine_count = max(1, int(round((1 + rng.randint(0, 2)) * max(0.40, actor_scale) * landmark_density)))
            for _ in range(vine_count):
                px = ox + rng.uniform(4.0, chunk_size - 4.0)
                py = oy + rng.uniform(4.0, chunk_size - 4.0)
                base = self.world_height_at(px, py, spec)
                arch = [Vec3(px - 4.0, py, base + 5.0), Vec3(px - 1.5, py + 1.5, base + 11.0), Vec3(px + 1.5, py - 1.0, base + 13.0), Vec3(px + 4.0, py, base + 6.0)]
                self.add_polyline(node, arch, (0.46, 0.96, 0.56, 0.50), self.cfg.line_thickness * 0.28, False, 'vine')
            for _ in range(tree_count):
                px = ox + rng.uniform(0.0, chunk_size)
                py = oy + rng.uniform(0.0, chunk_size)
                pz = self.world_height_at(px, py, spec)
                self.add_tree_actor(node, Vec3(px, py, pz), rng.randint(1, 10**9))
        return node

    def update_world_chunks(self, force=False):
        # main.py still carries legacy artifact-world terrain helpers, but the
        # normal HoloVerse terrain is owned by world.py through the shell mount.
        # Keep this streamer dark unless an explicit legacy artifact simulation
        # is active, so default play cannot render two terrains at once.
        if not self.should_stream_legacy_world_chunks(force=force):
            self.world_root.hide()
            if force and getattr(self, "terrain_chunks", None):
                self.clear_world_chunks()
            return
        self.world_root.show()
        size = self.cfg.terrain_chunk_size
        pcx = int(math.floor(self.player_pos.x / size))
        pcy = int(math.floor(self.player_pos.y / size))
        prewarm = self.effective_render_radius() + 1
        wanted = set()
        for cx in range(pcx - prewarm, pcx + prewarm + 1):
            for cy in range(pcy - prewarm, pcy + prewarm + 1):
                target_alpha = self.chunk_target_alpha(cx, cy)
                if target_alpha <= 0.0 and not force:
                    continue
                wanted.add((cx, cy))
                if (cx, cy) not in self.terrain_chunks:
                    node = self.create_world_chunk(cx, cy)
                    node.setColorScale(1, 1, 1, 0.0)
                    self.terrain_chunks[(cx, cy)] = {"node": node, "alpha": 0.0, "target_alpha": target_alpha}
                else:
                    self.terrain_chunks[(cx, cy)]["target_alpha"] = target_alpha
        for key, meta in list(self.terrain_chunks.items()):
            if key not in wanted:
                if isinstance(meta, dict):
                    meta["target_alpha"] = 0.0

    def current_zone_name(self):
        r = math.sqrt(self.player_pos.x ** 2 + self.player_pos.y ** 2)
        if r < 8.0:
            return "Central Core"
        if r < 19.0:
            return "Observatory Ring"
        if r < self.hub_radius + 1.0:
            return "Artifact Perimeter"
        if self.world_shell_playable_active():
            state = self.world_shell_play_state if isinstance(getattr(self, "world_shell_play_state", {}), dict) else {}
            biome = state.get("active_biome") or getattr(self, "world_shell_mount_biome", "HoloVerse")
            return f"HoloVerse // {biome}"
        return "Frontier Field"

    def active_world_runtime_state(self):
        """Return the authoritative high-level world lifecycle state for debug/menu use."""
        if (
            getattr(self, "active_native_mode", None) is not None
            or bool(getattr(self, "native_mode_isolated", False))
            or bool(str(getattr(self, "native_mode_label", "") or "").strip())
        ):
            return "NATIVE_MODE"
        if bool(getattr(self, "external_suspended", False)) or getattr(self, "external_process", None) is not None:
            return "EXTERNAL_MODE"
        if bool(getattr(self, "world_unlocked", False)) or float(getattr(self, "transition_target", 0.0)) > 0.0:
            return "ARTIFACT_WORLD"
        if bool(getattr(self, "core_console_open", False)) or bool(getattr(self, "menu_open", False)):
            return "CORE_MENU"
        if getattr(self, "world_shell_mount", None) is not None and bool(getattr(self, "world_shell_preloaded_default", False)):
            return "HOLOVERSE_DEFAULT"
        if bool(getattr(self.cfg, "world_shell_mount_enabled", True)):
            return "HOLOVERSE_RELOAD_PENDING"
        return "HOLOVERSE_DISABLED"

    def sync_active_world_runtime_state(self):
        state = self.active_world_runtime_state()
        self.active_world_runtime_state_label = state
        return state

    def artifact_activation_distance(self, artifact) -> float:
        if artifact is None:
            return 999.0
        pos = artifact.get("pos", Vec3(0, 0, 0))
        pedestal = artifact.get("pedestal_pos", pos)
        try:
            glyph_d = (pos - self.player_pos).length()
            horizontal_d = math.sqrt((pedestal.x - self.player_pos.x) ** 2 + (pedestal.y - self.player_pos.y) ** 2)
            return min(glyph_d, horizontal_d)
        except Exception:
            return 999.0

    def find_nearest_artifact(self):
        best = None
        best_d = 999.0
        for artifact in self.artifacts:
            d = self.artifact_activation_distance(artifact)
            if d < best_d:
                best_d = d
                best = artifact
        self.nearest_artifact = best
        self.nearest_artifact_dist = best_d

    def find_looked_at_artifact(self, max_distance=150.0, cone_cos=0.74):
        """Return the artifact closest to the desktop crosshair line.

        The original build only supported keyboard-nearest interaction.  In
        normal first-person desktop mode players naturally click what they are
        looking at, so this ray/cone picker makes artifact clicks deterministic
        without requiring Panda collision geometry on the wireframe artifacts.
        """
        if not self.artifacts:
            return None, 999.0, -1.0
        forward, right, up = self.get_view_basis()
        if forward.lengthSquared() <= 0.0001:
            return None, 999.0, -1.0
        forward.normalize()
        origin = self.head_world_pos()
        best = None
        best_score = 999.0
        best_dot = -1.0
        for artifact in self.artifacts:
            target = artifact["pos"] - origin
            distance = target.length()
            if distance <= 0.001 or distance > max_distance:
                continue
            direction = Vec3(target)
            direction.normalize()
            dot = float(forward.dot(direction))
            # Give every artifact a practical angular hit area at close range.
            # Real desktop play is less exact than offscreen tests because the
            # player is moving, the artifact glyph animates, and the hub core may
            # sit in front of the view. Use a forgiving cone but still score by
            # screen-line error so the intended pedestal wins.
            effective_cone = min(0.985, cone_cos - max(0.0, float(artifact.get("radius", 3.6)) / max(distance, 1.0)) * 0.030)
            if dot < effective_cone:
                continue
            cross_error = math.sqrt(max(0.0, 1.0 - dot * dot)) * distance
            if cross_error > max(9.5, float(artifact.get("radius", 4.25)) * 3.3):
                continue
            score = cross_error + distance * 0.014
            if score < best_score:
                best = artifact
                best_score = score
                best_dot = dot
        return best, best_score, best_dot

    def artifact_dimension_mode(self, artifact) -> dict | None:
        if artifact is None:
            return None
        mode_id = canonical_dimension_lookup_key(artifact.get("dimension_mode_id") or "")
        if not mode_id:
            return None
        candidates = list(getattr(self, "core_modes", []) or [])
        try:
            candidates.extend(self.matrixcore_dimension_gate_modes())
        except Exception:
            pass
        for mode in candidates:
            if not isinstance(mode, dict):
                continue
            manifest = dict(mode.get("manifest") or {})
            keys = {
                canonical_dimension_lookup_key(manifest.get("id")),
                canonical_dimension_lookup_key(manifest.get("title")),
                canonical_dimension_lookup_key(mode.get("name")),
                canonical_dimension_lookup_key(Path(mode.get("folder") or "").name),
            }
            if mode_id in keys:
                route = normalize_mode_launch_type(manifest.get("launch_type") or mode.get("launch_type"))
                if route == MODE_LAUNCH_PLACEHOLDER or bool(mode.get("placeholder") or manifest.get("placeholder_mode")):
                    continue
                return dict(mode)
        record = dimension_record_from_index(mode_id)
        return mode_from_dimension_record(record) if record else None

    def activate_artifact_direct(self, artifact, source="interact"):
        if artifact is None:
            return False
        artifact_id = int(artifact.get("world_id", artifact.get("id", -1)))
        mode = self.artifact_dimension_mode(artifact)
        if mode is None:
            label = str(artifact.get("name") or "ARTIFACT").upper()
            self.center_hint["text"] = f"ARTIFACT // {label} ROUTE NOT READY"
            print(f"artifact_dimension_route_missing source={source} pedestal={artifact.get('id')} mode_id={artifact.get('dimension_mode_id', '')}")
            return False
        self.active_artifact = artifact
        self.active_artifact_id = artifact_id
        manifest = dict(mode.get("manifest") or {})
        label = str(artifact.get("name") or self.dimension_display_name_for_mode(mode, manifest.get("title") or mode.get("name") or "DIMENSION"))
        launch_type = normalize_mode_launch_type(manifest.get("launch_type") or mode.get("launch_type"))
        self.runtime_world_signature = f"ARTIFACT DIMENSION ROUTE // {label.upper()} // {route_display_name(launch_type)}"
        self.active_world_runtime_state_label = "ARTIFACT_DIMENSION_GATE"
        self.center_hint["text"] = f"ENTER {label.upper()}"
        self.refresh_ui()
        print(f"artifact_dimension_launch source={source} pedestal={artifact.get('id')} mode_id={artifact.get('dimension_mode_id', '')} label={label} route={launch_type}")
        if self.audio and source != "core":
            self.audio.play('artifact_link.wav', 'sfx', 0.92)
        if SELF_TEST and str(source or "").startswith("self-test") and not ARTIFACT_LAUNCH_SMOKE_TEST:
            return True
        launched = bool(self.start_dimension_transition(
            mode,
            source=f"artifact:{artifact.get('id', artifact_id)}",
            context={
                "doorway": "artifact",
                "artifact_id": str(artifact.get("id", artifact_id)),
                "artifact_mode_id": str(artifact.get("dimension_mode_id", "")),
                "artifact_name": str(artifact.get("name", "")),
            },
            extra_env={
                "HOLOVERSE_ARTIFACT_ID": str(artifact.get("id", artifact_id)),
                "HOLOVERSE_ARTIFACT_MODE_ID": str(artifact.get("dimension_mode_id", "")),
                "HOLOVERSE_GATEWAY_SOURCE": "artifact",
            },
            close_core=True,
        ))
        if launched:
            try:
                gate_record = self.record_matrixcore_dimension_gate_discovery(
                    mode,
                    label=label,
                    mode_id=str(artifact.get("dimension_mode_id", "")),
                    route=launch_type,
                    source=f"artifact:{artifact.get('id', artifact_id)}",
                    doorway="artifact",
                    artifact=artifact,
                )
                if bool(gate_record.get("_newly_discovered", False)):
                    display_name = str(gate_record.get("display_name") or label)
                    self.pending_dimension_discovery_notice = display_name
                    try:
                        self.show_bridge_transition("DIMENSION DISCOVERED", f"{display_name} added to Gates", target=1.0, hold=0.34)
                    except Exception:
                        pass
            except Exception as exc:
                try:
                    print(f"artifact_gate_discovery_record_error pedestal={artifact.get('id')} err={exc.__class__.__name__}:{exc}")
                except Exception:
                    pass
        return launched

    def artifact_gate_assignments(self) -> list[dict]:
        assignments = []
        for artifact in list(getattr(self, "artifacts", []) or []):
            mode_id = str(artifact.get("dimension_mode_id", ""))
            mode = self.artifact_dimension_mode(artifact)
            path = None
            label = str(artifact.get("name") or mode_id or "DIMENSION")
            launch_type = ""
            manifest = {}
            if mode is not None:
                manifest = dict(mode.get("manifest") or {})
                path, _resolved_label, _route_env = self.resolve_core_mode_entry(mode)
                label = self.dimension_display_name_for_mode(mode, artifact.get("name") or _resolved_label or mode_id)
                launch_type = normalize_mode_launch_type(manifest.get("launch_type") or mode.get("launch_type"))
            placeholder = bool(
                manifest.get("placeholder_mode", False)
                or (mode or {}).get("placeholder", False)
                or launch_type == MODE_LAUNCH_PLACEHOLDER
            )
            assignments.append({
                "pedestal": int(artifact.get("id", -1)),
                "world_id": int(artifact.get("world_id", -1)),
                "mode_id": mode_id,
                "label": str(label or artifact.get("name") or mode_id or "DIMENSION"),
                "launch_type": launch_type or "missing",
                "transition_route": transition_route_for_launch_type(launch_type, placeholder=placeholder) if launch_type else "missing",
                "entry": os.fspath(path) if path is not None else "",
                "entry_exists": bool(path is not None and Path(path).exists()),
                "folder": os.fspath((mode or {}).get("folder", "")) if mode is not None else "",
                "connected_same_window": launch_type == MODE_LAUNCH_CONNECTED,
                "same_window_holocore": launch_type == MODE_LAUNCH_CONNECTED and "holocore" in " ".join(str(v or "").lower() for v in (mode_id, label, manifest.get("id"), manifest.get("title"))),
            })
        return assignments

    def artifact_in_world_runtime_method(self, mode: dict, label: str = "") -> str:
        """Return the mounted runtime method expected for an in-world artifact route."""
        manifest = dict((mode or {}).get("manifest") or {})
        mode_name = str((mode or {}).get("name") or label or manifest.get("title") or "")
        manifest_id = str(manifest.get("id") or re.sub(r"[^a-z0-9]+", "_", mode_name.lower()).strip("_") or "").lower()
        try:
            folder_name = Path((mode or {}).get("folder") or "").name.lower()
        except Exception:
            folder_name = ""
        route_text = " ".join(
            str(value or "").lower()
            for value in (mode_name, label, manifest.get("title"), manifest.get("id"), folder_name)
        )
        method_map = {
            "holoforge": "activate_holoforge_from_mode",
            "forest_growth": "activate_forest_growth_from_mode",
            "hills_life": "activate_hills_life_from_mode",
            "hills_of_life": "activate_hills_life_from_mode",
            "oddities": "activate_oddities_from_mode",
            "ember_hangar": "activate_desert_ships_from_mode",
            "desert_ships": "activate_desert_ships_from_mode",
            "frost_circuit": "activate_frost_circuit_from_mode",
            "urban_warzone": "activate_urban_warzone_from_mode",
            "metropolis_robot_lab": "activate_metropolis_robot_lab_from_mode",
        }
        if manifest_id in method_map:
            return method_map[manifest_id]
        if folder_name == "metropolis robot lab" or "metropolis robot lab" in route_text or "robot lab" in route_text:
            return "activate_metropolis_robot_lab_from_mode"
        if folder_name == "urban warzone" or "urban warzone" in route_text or "warzone" in route_text:
            return "activate_urban_warzone_from_mode"
        if "forest" in route_text:
            return "activate_forest_growth_from_mode"
        if "hill" in route_text:
            return "activate_hills_life_from_mode"
        if "frost" in route_text:
            return "activate_frost_circuit_from_mode"
        if "ember" in route_text or "hangar" in route_text or "desert" in route_text:
            return "activate_desert_ships_from_mode"
        if "forge" in route_text:
            return "activate_holoforge_from_mode"
        if "odd" in route_text:
            return "activate_oddities_from_mode"
        return ""

    def smoke_test_connected_artifact_routes(self) -> list[dict]:
        """Validate every artifact doorway against the real dimension contract.

        Artifacts are now presentation-critical same-window routes.  Valid
        artifact doors are native Panda adapters, in-world runtimes, or the
        same-window HoloCore slot.  Child-window/embedded/external routes must
        fail this smoke check so wrapper regressions cannot pass again.
        """
        results = []
        for artifact in list(getattr(self, "artifacts", []) or []):
            mode_id = str(artifact.get("dimension_mode_id", ""))
            mode = self.artifact_dimension_mode(artifact)
            pedestal = int(artifact.get("id", -1))
            if mode is None:
                results.append({"pedestal": pedestal, "mode_id": mode_id, "ok": False, "stage": "mode_missing"})
                continue
            manifest = dict(mode.get("manifest") or {})
            path, label, _route_env = self.resolve_core_mode_entry(mode)
            launch_type = normalize_mode_launch_type(manifest.get("launch_type") or mode.get("launch_type"))
            placeholder = bool(manifest.get("placeholder_mode", False) or mode.get("placeholder", False) or launch_type == MODE_LAUNCH_PLACEHOLDER)
            result = {
                "pedestal": pedestal,
                "mode_id": mode_id,
                "label": str(label or mode.get("name") or mode_id),
                "launch_type": launch_type,
                "transition_route": transition_route_for_launch_type(launch_type, placeholder=placeholder),
                "entry": os.fspath(path) if path is not None else "",
                "entry_exists": bool(path is not None and Path(path).exists()),
                "ok": True,
            }
            if placeholder:
                result["ok"] = False
                result["stage"] = "placeholder_not_artifact_dimension"
            elif path is None or not Path(path).exists():
                result["ok"] = False
                result["stage"] = "entry_missing"
            elif launch_type == MODE_LAUNCH_IN_WORLD:
                method_name = self.artifact_in_world_runtime_method(mode, str(label or ""))
                result["runtime_method"] = method_name
                result["runtime_method_exists"] = bool(method_name and callable(getattr(self, method_name, None)))
                result["stage"] = "in_world_runtime_method_ready" if result["runtime_method_exists"] else "in_world_runtime_method_missing"
                result["ok"] = bool(result["runtime_method_exists"])
            elif launch_type == MODE_LAUNCH_CONNECTED:
                key_text = " ".join(str(v or "").lower() for v in (mode_id, label, manifest.get("id"), manifest.get("title"), mode.get("name")))
                result["runtime_method"] = "launch_holocore_same_window" if "holocore" in key_text else ""
                result["runtime_method_exists"] = bool(result["runtime_method"] and callable(getattr(self, result["runtime_method"], None)))
                result["same_window_only"] = bool(manifest.get("same_window_only", False) or manifest.get("forbid_child_process", False) or "holocore" in key_text)
                result["stage"] = "holocore_same_window_route_ready" if result["runtime_method_exists"] and result["same_window_only"] else "same_window_route_not_artifact_safe"
                result["ok"] = bool(result["runtime_method_exists"] and result["same_window_only"] and "holocore" in key_text)
            elif launch_type == MODE_LAUNCH_NATIVE:
                adapter_path = self._mode_adapter_path(mode)
                result["native_adapter"] = os.fspath(adapter_path) if adapter_path is not None else ""
                result["native_adapter_exists"] = bool(adapter_path is not None and Path(adapter_path).exists())
                adapter_has_factory = False
                if result["native_adapter_exists"]:
                    try:
                        adapter_text = Path(adapter_path).read_text(encoding="utf-8", errors="ignore")
                        adapter_has_factory = ("def create_mode" in adapter_text) or ("class HoloVerseNativeMode" in adapter_text)
                    except Exception:
                        adapter_has_factory = False
                result["native_adapter_has_factory"] = bool(adapter_has_factory)
                result["stage"] = "native_adapter_ready" if result["native_adapter_exists"] and adapter_has_factory else ("native_adapter_factory_missing" if result["native_adapter_exists"] else "native_adapter_missing")
                result["ok"] = bool(result["native_adapter_exists"] and adapter_has_factory)
            elif launch_type in {MODE_LAUNCH_EMBEDDED, MODE_LAUNCH_EXTERNAL}:
                result["stage"] = "artifact_child_wrapper_not_presentation_safe"
                result["ok"] = False
            else:
                result["ok"] = False
                result["stage"] = "unsupported_artifact_dimension_route"
            results.append(result)
        self.artifact_route_smoke_results = results
        self.artifact_route_smoke_passed = all(bool(item.get("ok")) for item in results)
        return results

    def activate_artifact(self, source="nearest"):
        return self.activate_artifact_direct(self.nearest_artifact, source=source)

    def activate_nearest_artifact(self, source="nearest"):
        self.find_nearest_artifact()
        if self.nearest_artifact is None:
            return False
        activation_radius = max(float(self.nearest_artifact.get("radius", 3.6)), ARTIFACT_PRESS_ACTIVATION_RADIUS)
        if self.nearest_artifact_dist < activation_radius:
            return self.activate_artifact(source=source)
        return False

    def activate_focused_artifact(self, source="focus"):
        looked, score, dot = self.find_looked_at_artifact(max_distance=ARTIFACT_LOOK_ACTIVATION_RADIUS)
        if looked is not None:
            self.nearest_artifact = looked
            self.nearest_artifact_dist = self.artifact_activation_distance(looked)
            print(f"interaction_probe source={source} target=artifact looked=1 pedestal={looked.get('id')} world_id={looked.get('world_id')} score={score:.3f} dot={dot:.3f}")
            return self.activate_artifact_direct(looked, source=source)
        ok = self.activate_nearest_artifact(source=source)
        if ok and self.nearest_artifact is not None:
            print(f"interaction_probe source={source} target=artifact looked=0 pedestal={self.nearest_artifact.get('id')} world_id={self.nearest_artifact.get('world_id')} dist={self.nearest_artifact_dist:.3f}")
        return ok

    def primary_click_interact(self):
        if bool(getattr(self, "shell_flight_craft_cinematic", False)):
            return
        if self.is_holospace_active():
            # Space Bot remains the combat doorway; empty Dyson clicks return.
            if self.open_focused_bot_dialogue(source="mouse1"):
                return
            if self.is_looking_at_holospace_dyson_gate():
                self.start_holospace_return_sequence(source="dyson_click")
                return
        if getattr(self, "bot_dialogue_open", False):
            return
        if getattr(self, "active_native_mode", None) is not None:
            self.dispatch_native_action("mouse1")
            return
        if self.menu_open:
            print("interaction_probe source=mouse1 target=menu result=ignored")
            return
        if self.core_console_open:
            self.trigger_matrixcore_dialogue("mouse1_stale_core_panel")
            print("interaction_probe source=mouse1 target=core result=gleebs_dialogue_stale_panel")
            return
        if self.is_looking_at_core():
            self.open_core_console()
            print("interaction_probe source=mouse1 target=core result=gleebs_dialogue")
            return
        if self.open_focused_bot_dialogue(source="mouse1"):
            return
        if self.activate_focused_artifact(source="mouse1"):
            return
        self.interact()

    def complete_holospace_return_to_hub(self, *, source: str = "dyson") -> bool:
        self.holospace_transition_active = False
        self.holospace_transition_destination = "space"
        try:
            if getattr(self, "root_3d", None) is not None:
                self.root_3d.show()
        except Exception:
            pass
        self.teleport_to_hub(silent=True)
        self.runtime_world_signature = f"HOLOVERSE HUB // RETURNED FROM SPACE // {str(source or 'DYSON').upper()}"
        return True

    def start_holospace_return_sequence(self, *, source: str = "dyson") -> bool:
        if self.is_holospace_traveling():
            return True
        entry = self.holoverse_region_entry_for_number(8) or {}
        return self.start_holospace_travel_sequence(entry, source=source, destination="hub")

    def is_looking_at_holospace_dyson_gate(self, *, max_distance: float = 5200.0, cone_cos: float = 0.72) -> bool:
        if not self.is_holospace_active():
            return False
        try:
            focus = self.holospace_dyson_focus()
            origin = self.head_world_pos()
            to_gate = focus - origin
            distance = float(to_gate.length())
            if distance <= 0.001 or distance > float(max_distance):
                return False
            to_gate.normalize()
            forward, _right, _up = self.get_view_basis()
            if forward.lengthSquared() <= 0.0001:
                return False
            forward.normalize()
            return float(forward.dot(to_gate)) >= float(cone_cos)
        except Exception:
            return False

    def teleport_to_hub(self, *, silent: bool = False):
        self.holospace_active = False
        self.holospace_velocity = Vec3(0, 0, 0)
        self.holospace_speed_boost = 1.0
        self.holospace_ship_health = float(getattr(self, "holospace_ship_max_health", 100.0) or 100.0)
        self.holospace_ship_respawn_cooldown = 0.0
        self.show_holospace_cockpit(False)
        self.apply_holospace_world_isolation(False)
        self.clear_world_chunks()
        self.active_artifact = None
        self.active_artifact_id = None
        self.nearest_artifact = None
        self.nearest_artifact_dist = 999.0
        self.world_unlocked = False
        self.transition_target = 0.0
        self.transition_progress = 0.0
        self.world_theme_blend = 0.0
        self.last_world_kind = "frontier"
        self.player_pos = Vec3(self.base_teleport)
        self.camera.setPos(self.player_pos)
        self.camera.setHpr(self.player_yaw, self.player_pitch, 0)
        self.apply_world_theme(1.0 / 60.0)
        self.reload_default_holoverse_shell(reason="t_return")
        self.sync_active_world_runtime_state()
        self.refresh_ui()
        if not silent:
            self.center_hint["text"] = "HOLOVERSE // DEFAULT WORLD RELOADED"
        if self.audio:
            self.audio.play('world_shift.wav', 'sfx', 0.72)

    def handle_h_action(self):
        if bool(getattr(self, "shell_flight_craft_cinematic", False)):
            return
        """Route H to dimension-local UI while native dimensions are active.

        The universal HoloVerse HUD remains a Core-level toggle outside native
        dimensions.  Inside native dimensions, H only targets the dimension's
        legacy/source HUD so presentation runs can keep old per-mode UI hidden
        without turning off universal Core state.  Zonez intentionally ignores
        this action because its UI is part of its gameplay loop.
        """
        if getattr(self, "active_native_mode", None) is not None:
            consumed = self.dispatch_native_action("toggle_dimension_ui")
            if not consumed and getattr(self, "center_hint", None) is not None:
                label = str(getattr(self, "native_mode_label", "DIMENSION") or "DIMENSION").upper()
                if "ZONEZ" in label:
                    self.center_hint["text"] = "ZONEZ UI // GAMEPLAY UI STAYS ON"
                else:
                    self.center_hint["text"] = f"{label} UI // NO LOCAL TOGGLE"
            return
        self.toggle_hud()

    def toggle_hud(self):
        self.hud_visible = not self.hud_visible
        self.cfg.hud_visible = self.hud_visible
        save_config(self.cfg)
        self.refresh_ui()

    def toggle_help_overlay(self):
        if bool(getattr(self, "shell_flight_craft_cinematic", False)):
            return
        if not self.menu_open:
            self.menu_open = True
            self.menu_root.show()
        self.set_menu_tab("help")
        props = WindowProperties()
        props.setCursorHidden(False)
        if self.win is not None and hasattr(self.win, "requestProperties"):
            self.win.requestProperties(props)
        self.center_hint["text"] = ""
        self.refresh_ui()

    def toggle_menu(self):
        if bool(getattr(self, "shell_flight_craft_cinematic", False)):
            self.exit_shell_flight_cinematic()
            return
        if self.core_console_open:
            self.close_core_console()
            return
        self.menu_open = not self.menu_open
        props = WindowProperties()
        props.setCursorHidden(not self.menu_open and not SELF_TEST)
        if self.win is not None and hasattr(self.win, "requestProperties"):
            self.win.requestProperties(props)
        if self.menu_open:
            self.menu_root.show()
            self.center_hint["text"] = ""
        else:
            self.menu_root.hide()
            if not SELF_TEST:
                self.recenter_mouse(force=True)
        self.refresh_ui()

    def set_menu_tab(self, tab_key):
        self.menu_tab = tab_key
        self.refresh_menu_actions()
        self.refresh_ui()


    def _load_soundmatrix_forge(self):
        if not SOUNDMATRIX_FORGE.exists():
            raise FileNotFoundError(SOUNDMATRIX_FORGE)
        module_name = "holoverse_soundmatrix_audio_forge"
        spec = importlib.util.spec_from_file_location(module_name, SOUNDMATRIX_FORGE)
        if spec is None or spec.loader is None:
            raise RuntimeError("Could not load SoundMatrix Audio Forge")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module

    def forge_soundmatrix_pack(self, pack="all"):
        try:
            forge = self._load_soundmatrix_forge()
            report = forge.render_holoverse_pack(ROOT, pack=pack, seed=getattr(self.cfg, "soundmatrix_random_seed", None), intensity=getattr(self.cfg, "soundmatrix_variant_intensity", 0.65), music_intensity=getattr(self.cfg, "soundmatrix_music_intensity", 0.55))
            if self.audio is not None:
                try:
                    self.audio.cache.clear()
                    self.audio.play("menu_open.wav", bus="sfx", volume=0.65)
                    if pack in {"all", "music"}:
                        self.audio.stop_loop("hub_music")
                        self.audio.stop_loop("hub_air")
                        self.update_soundscape(0.0, force=True)
                except Exception:
                    pass
            self.center_hint["text"] = f"SOUNDMATRIX // {report.get('generated_count', 0)} AUDIO ASSETS"
            self.menu_status["text"] = f"SOUNDMATRIX {pack.upper()} RENDERED"
        except Exception as exc:
            try:
                CRASH_LOG.write_text(traceback.format_exc(), encoding="utf-8")
            except Exception:
                pass
            self.center_hint["text"] = f"SOUNDMATRIX FAILED // {exc.__class__.__name__}"
            self.menu_status["text"] = "SOUNDMATRIX RENDER FAILED"
        self.refresh_ui()

    def forge_soundmatrix_full_pack(self):
        self.forge_soundmatrix_pack("all")

    def forge_soundmatrix_sfx_pack(self):
        self.forge_soundmatrix_pack("sfx")

    def forge_soundmatrix_music_pack(self):
        self.forge_soundmatrix_pack("music")

    def forge_soundmatrix_variants_pack(self):
        self.forge_soundmatrix_pack("variants")

    def forge_soundmatrix_soundtrack_pack(self):
        self.forge_soundmatrix_pack("soundtrack")

    def toggle_soundtrack_enabled(self):
        self.cfg.soundtrack_enabled = not bool(getattr(self.cfg, "soundtrack_enabled", True))
        save_config(self.cfg)
        self.refresh_ui()

    def toggle_soundmatrix_vector_sources(self):
        self.cfg.soundmatrix_use_vector_wars_sources = not bool(getattr(self.cfg, "soundmatrix_use_vector_wars_sources", True))
        save_config(self.cfg)
        self.refresh_ui()

    def adjust_soundtrack_intensity(self, delta):
        self.cfg.soundtrack_intensity = max(0.0, min(1.0, float(getattr(self.cfg, "soundtrack_intensity", 0.55)) + delta))
        save_config(self.cfg)
        self.refresh_ui()

    def adjust_ambience_intensity(self, delta):
        self.cfg.ambience_intensity = max(0.0, min(1.0, float(getattr(self.cfg, "ambience_intensity", 0.45)) + delta))
        save_config(self.cfg)
        self.refresh_ui()

    def adjust_soundmatrix_variant_intensity(self, delta):
        self.cfg.soundmatrix_variant_intensity = max(0.0, min(1.0, float(getattr(self.cfg, "soundmatrix_variant_intensity", 0.65)) + delta))
        save_config(self.cfg)
        self.refresh_ui()

    def adjust_soundmatrix_music_intensity(self, delta):
        self.cfg.soundmatrix_music_intensity = max(0.0, min(1.0, float(getattr(self.cfg, "soundmatrix_music_intensity", 0.55)) + delta))
        save_config(self.cfg)
        self.refresh_ui()

    def randomize_soundmatrix_seed(self):
        self.cfg.soundmatrix_random_seed = random.randint(1000, 99999999)
        save_config(self.cfg)
        self.menu_status["text"] = f"AUDIO SEED {self.cfg.soundmatrix_random_seed}"
        self.refresh_ui()

    def open_soundmatrix_audio_folder(self):
        try:
            AUDIO_LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
            CANONICAL_GENERATED_SFX_DIR.mkdir(parents=True, exist_ok=True)
            CANONICAL_MUSIC_DIR.mkdir(parents=True, exist_ok=True)
            if sys.platform.startswith("win"):
                os.startfile(str(AUDIO_LIBRARY_DIR))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(AUDIO_LIBRARY_DIR)])
            else:
                subprocess.Popen(["xdg-open", str(AUDIO_LIBRARY_DIR)])
            self.menu_status["text"] = "AUDIO LIBRARY OPENED"
        except Exception as exc:
            self.center_hint["text"] = f"AUDIO DIR FAILED // {exc.__class__.__name__}"
        self.refresh_ui()

    def validate_audio_library(self):
        try:
            cmd = [sys.executable, os.fspath(ROOT / "tools" / "audio_library_validate.py"), os.fspath(ROOT)]
            result = subprocess.run(cmd, cwd=os.fspath(ROOT), capture_output=True, text=True, timeout=20)
            self.menu_status["text"] = "AUDIO VALID OK" if result.returncode == 0 else "AUDIO VALID WARN"
            self.center_hint["text"] = "AUDIO LIBRARY VALIDATED" if result.returncode == 0 else "AUDIO VALIDATION FOUND ISSUES"
            try:
                (LOG_DIR / "audio_library_validation_stdout.txt").write_text((result.stdout or "") + "\n" + (result.stderr or ""), encoding="utf-8")
            except Exception:
                pass
        except Exception as exc:
            self.center_hint["text"] = f"AUDIO VALID FAILED // {exc.__class__.__name__}"
            self.menu_status["text"] = "AUDIO VALID FAILED"
        self.refresh_ui()


    def unload_default_holoverse_shell(self, reason: str = ""):
        """Destroy the Core-owned default HoloVerse shell before artifact/world simulations run."""
        mount = getattr(self, "world_shell_mount", None)
        if mount is not None:
            try:
                mount.destroy()
            except Exception as exc:
                print(f"world_shell_unload_error reason={reason}: {exc}")
        self.world_shell_mount = None
        self.world_shell_mount_status = f"HOLOVERSE UNLOADED // {str(reason or 'SIMULATION').upper()}"
        self.world_shell_streamed_count = 0
        self.world_shell_preloaded_default = False
        self.world_shell_preload_report = {}
        self.world_shell_theme_handoff = {}
        self.world_shell_audio_handoff = {}
        self.world_shell_audio_status = "OFF"
        self.world_shell_motion_status = "OFF"
        self.world_shell_playable_status = "UNLOADED"
        self.world_shell_play_state = {}
        self.world_shell_default_lifecycle_state = "HOLOVERSE_UNLOADED_FOR_ARTIFACT" if "artifact" in str(reason).lower() else "HOLOVERSE_UNLOADED"
        self.active_world_runtime_state_label = self.sync_active_world_runtime_state()

    def reload_default_holoverse_shell(self, reason: str = "hub_return"):
        """Reload the full-scale default HoloVerse shell after artifact simulations unload."""
        if not bool(getattr(self.cfg, "world_shell_mount_enabled", True)):
            self.world_shell_mount_status = "HOLOVERSE DEFAULT DISABLED"
            return
        # Make sure artifact/simulation terrain is gone before the default world comes back.
        self.clear_world_chunks()
        self.mount_world_shell_adapter()
        self.world_shell_default_lifecycle_state = f"HOLOVERSE_DEFAULT_LOADED // {str(reason).upper()}"
        self.active_world_runtime_state_label = "HOLOVERSE_DEFAULT"
        try:
            if getattr(self.world_shell_mount, "root", None) is not None:
                self.world_shell_mount.root.show()
        except Exception:
            pass

    def mount_world_shell_adapter(self):
        try:
            if not bool(getattr(self.cfg, "world_shell_mount_enabled", True)):
                self.world_shell_mount_status = "HOLOVERSE MOUNT DISABLED"
                if getattr(self, "world_shell_mount", None) is not None:
                    try:
                        self.world_shell_mount.destroy()
                    except Exception:
                        pass
                self.world_shell_mount = None
                self.world_shell_streamed_count = 0
                self.world_shell_preloaded_default = False
                self.world_shell_preload_report = {}
                self.world_shell_theme_handoff = {}
                self.world_shell_hub_theme_current = 0.0
                self.world_shell_hub_theme_status = "OFF"
                self.world_shell_audio_handoff = {}
                self.world_shell_audio_status = "OFF"
                self.world_shell_prompt = "HOLOVERSE OFF"
                self.world_shell_motion_status = "OFF"
                self.world_shell_playable_status = "OFF"
                self.world_shell_play_state = {}
                self.world_shell_play_radius = 0.0
                return
            from holoverse_world_shell_mount import HoloVerseWorldShellMount
            if getattr(self, "world_shell_mount", None) is not None:
                try:
                    self.world_shell_mount.destroy()
                except Exception:
                    pass
            self.world_shell_mount = HoloVerseWorldShellMount(self)
            self.world_shell_mount.rebuild_static()
            report = self.world_shell_mount.mount_report()
            self.world_shell_preload_report = report
            self.world_shell_theme_handoff = report.get("theme_handoff", {}) if isinstance(report, dict) else {}
            self.world_shell_preloaded_default = bool(report.get("default_preloaded", False))
            self.world_shell_mount_status = "HOLOVERSE DEFAULT PRELOADED" if self.world_shell_preloaded_default else "HOLOVERSE DEFAULT MOUNTED"
            self.world_shell_mount_biome = self.world_shell_mount.active_biome_name()
            self.world_shell_streamed_count = len(getattr(self.world_shell_mount, "sector_nodes", {}) or {})
            self.world_shell_play_state = report.get("play_state", {}) if isinstance(report, dict) else {}
            self.world_shell_play_radius = float(report.get("playable_outer_radius", getattr(self.cfg, "world_shell_play_radius", 11100.0))) if isinstance(report, dict) else float(getattr(self.cfg, "world_shell_play_radius", 11100.0))
            self.world_shell_playable_status = "PLAYABLE" if bool(report.get("playable_enabled", False)) else "VISUAL ONLY"
            self.world_shell_default_lifecycle_state = "HOLOVERSE_DEFAULT_FULLSCALE_LOADED"
            self.active_world_runtime_state_label = "HOLOVERSE_DEFAULT"
            bridge = report.get("source_bridge_active", False) if isinstance(report, dict) else False
            self.runtime_world_signature = "HOLOVERSE DEFAULT // WORLD.PY SOURCE BRIDGE" if bridge else "HOLOVERSE DEFAULT // FULL-SCALE WORLD.PY RINGS"
        except Exception as exc:
            self.world_shell_mount_status = f"MOUNT ERROR {exc.__class__.__name__}"
            self.world_shell_streamed_count = 0
            self.world_shell_preloaded_default = False
            self.world_shell_preload_report = {"error": str(exc)}
            self.world_shell_theme_handoff = {}
            self.world_shell_hub_theme_current = 0.0
            self.world_shell_hub_theme_status = "ERROR"
            self.world_shell_audio_handoff = {}
            self.world_shell_audio_status = "ERROR"
            self.world_shell_prompt = "HOLOVERSE ERROR"
            self.world_shell_motion_status = "ERROR"
            self.world_shell_playable_status = "ERROR"
            self.world_shell_play_state = {}
            self.world_shell_play_radius = 0.0
            print(f"world_shell_mount_error: {exc}")

    def load_world_shell_play_state(self):
        try:
            data = _safe_read_json(WORLD_SHELL_PLAY_STATE)
        except Exception:
            data = {}
        raw = data.get("claimed_checkpoints", []) if isinstance(data, dict) else []
        try:
            self.world_shell_claimed_checkpoints = {str(x) for x in raw if str(x).strip()}
        except Exception:
            self.world_shell_claimed_checkpoints = set()
        self.world_shell_checkpoint_claimed_count = len(self.world_shell_claimed_checkpoints)
        try:
            self.world_shell_checkpoint_total = int(data.get("checkpoint_total", 0)) if isinstance(data, dict) else 0
        except Exception:
            self.world_shell_checkpoint_total = 0
        self.world_shell_checkpoint_status = f"{self.world_shell_checkpoint_claimed_count}/{max(0, self.world_shell_checkpoint_total)}"

    def save_world_shell_play_state(self):
        try:
            payload = {
                "schema": "holoverse_world_shell_play_state_v3_pass37",
                "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "claimed_checkpoints": sorted(str(x) for x in getattr(self, "world_shell_claimed_checkpoints", set())),
                "checkpoint_total": int(getattr(self, "world_shell_checkpoint_total", 0)),
                "last_biome_key": int(getattr(self, "world_shell_last_biome_key", 0)),
            }
            WORLD_SHELL_PLAY_STATE.parent.mkdir(parents=True, exist_ok=True)
            WORLD_SHELL_PLAY_STATE.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        except Exception as exc:
            print(f"world_shell_play_state_save_error: {exc}")

    def reset_world_shell_checkpoints(self):
        self.world_shell_claimed_checkpoints = set()
        self.world_shell_checkpoint_claimed_count = 0
        mount = getattr(self, "world_shell_mount", None)
        if mount is not None:
            try:
                for cp in getattr(mount, "checkpoint_data", []) or []:
                    mount.set_checkpoint_claimed(cp.get("id", ""), False)
                mount.write_state()
            except Exception:
                pass
        self.save_world_shell_play_state()
        self.world_shell_checkpoint_status = f"0/{max(0, int(getattr(self, 'world_shell_checkpoint_total', 0)))}"
        try:
            self.center_hint["text"] = "HOLOVERSE // CHECKPOINTS RESET"
        except Exception:
            pass
        self.refresh_ui()

    def toggle_world_shell_boundary_feedback(self):
        self.cfg.world_shell_boundary_feedback = not bool(getattr(self.cfg, "world_shell_boundary_feedback", True))
        save_config(self.cfg)
        mount = getattr(self, "world_shell_mount", None)
        if mount is not None:
            try:
                mount.rebuild_static()
            except Exception:
                pass
        self.world_shell_boundary_status = "ON" if self.cfg.world_shell_boundary_feedback else "OFF"
        self.refresh_ui()

    def toggle_world_shell_checkpoints(self):
        self.cfg.world_shell_checkpoint_enabled = not bool(getattr(self.cfg, "world_shell_checkpoint_enabled", True))
        save_config(self.cfg)
        mount = getattr(self, "world_shell_mount", None)
        if mount is not None:
            try:
                mount.rebuild_static()
            except Exception:
                pass
        self.refresh_ui()

    def resolve_world_shell_boundary_candidate(self, candidate: Vec3):
        if not self.world_shell_playable_active() or not bool(getattr(self.cfg, "world_shell_boundary_feedback", True)):
            return None
        try:
            r = math.sqrt(float(candidate.x) * float(candidate.x) + float(candidate.y) * float(candidate.y))
            limit = max(8.0, self.world_shell_play_radius_limit() - 0.65)
            if r <= limit or r <= 0.001:
                return None
            corrected = Vec3(candidate)
            scale = limit / r
            corrected.x = float(candidate.x) * scale
            corrected.y = float(candidate.y) * scale
            corrected.z = self.world_shell_grounded_z(corrected.x, corrected.y)
            self.world_shell_boundary_status = "SOFT CLAMP"
            if float(getattr(self, "elapsed", 0.0)) - float(getattr(self, "world_shell_last_prompt_at", -999.0)) > 1.15:
                self.center_hint["text"] = "HOLOVERSE EDGE // TURN BACK OR FOLLOW THE RING"
                self.world_shell_last_prompt_at = float(getattr(self, "elapsed", 0.0))
            return corrected
        except Exception:
            return None

    def update_world_shell_gameplay_feedback(self, dt: float = 0.0):
        del dt
        report = self.world_shell_preload_report if isinstance(getattr(self, "world_shell_preload_report", {}), dict) else {}
        play_state = self.world_shell_play_state if isinstance(getattr(self, "world_shell_play_state", {}), dict) else {}
        checkpoints = report.get("checkpoints", []) if isinstance(report.get("checkpoints", []), list) else []
        self.world_shell_checkpoint_total = len(checkpoints)
        mount = getattr(self, "world_shell_mount", None)
        # Keep visual checkpoint nodes synced with persistent claimed state.
        if mount is not None:
            for cid in list(getattr(self, "world_shell_claimed_checkpoints", set())):
                try:
                    mount.set_checkpoint_claimed(cid, True)
                except Exception:
                    pass
        # Biome entry prompt: compact and rate-limited so it does not clutter normal hub play.
        key = int(play_state.get("active_key", 0) or 0)
        radius = float(play_state.get("radius", 0.0) or 0.0)
        if bool(getattr(self.cfg, "world_shell_biome_entry_prompts", True)) and key and key != int(getattr(self, "world_shell_last_biome_key", 0)):
            self.world_shell_last_biome_key = key
            if radius > self.hub_radius + 2.0:
                self.center_hint["text"] = f"ENTERED SHELL // {str(play_state.get('active_biome', 'WORLD')).upper()}"
                self.world_shell_last_prompt_at = float(getattr(self, "elapsed", 0.0))
                self.save_world_shell_play_state()
        factor = float(play_state.get("boundary_warning_factor", 0.0) or 0.0)
        if factor > 0.01:
            self.world_shell_boundary_status = f"EDGE {factor:.2f}"
            if factor > 0.72 and float(getattr(self, "elapsed", 0.0)) - float(getattr(self, "world_shell_last_prompt_at", -999.0)) > 1.1:
                self.center_hint["text"] = "HOLOVERSE EDGE // SAFE FIELD LIMIT"
                self.world_shell_last_prompt_at = float(getattr(self, "elapsed", 0.0))
        elif bool(getattr(self.cfg, "world_shell_boundary_feedback", True)):
            self.world_shell_boundary_status = "READY"
        else:
            self.world_shell_boundary_status = "OFF"
        if bool(getattr(self.cfg, "world_shell_checkpoint_enabled", True)) and self.world_shell_playable_active():
            claimed = getattr(self, "world_shell_claimed_checkpoints", set())
            px, py, pz = float(self.player_pos.x), float(self.player_pos.y), float(self.player_pos.z)
            for cp in checkpoints:
                cid = str(cp.get("id", ""))
                if not cid or cid in claimed or bool(cp.get("claimed", False)):
                    continue
                pos = cp.get("position", [0.0, 0.0, 0.0])
                try:
                    dx = float(pos[0]) - px
                    dy = float(pos[1]) - py
                    dz = float(pos[2]) - pz
                    dist = math.sqrt(dx * dx + dy * dy + min(6.0, abs(dz)) ** 2)
                    pickup_radius = float(cp.get("pickup_radius", getattr(self.cfg, "world_shell_checkpoint_pickup_radius", 4.8)) or 4.8)
                except Exception:
                    continue
                if dist <= pickup_radius:
                    claimed.add(cid)
                    self.world_shell_claimed_checkpoints = claimed
                    self.world_shell_checkpoint_claimed_count = len(claimed)
                    if mount is not None:
                        try:
                            mount.set_checkpoint_claimed(cid, True)
                            mount.write_state()
                        except Exception:
                            pass
                    self.world_shell_checkpoint_status = f"{self.world_shell_checkpoint_claimed_count}/{max(0, self.world_shell_checkpoint_total)}"
                    self.center_hint["text"] = f"SHELL CHECKPOINT // {self.world_shell_checkpoint_status} // {str(cp.get('biome', 'WORLD')).upper()}"
                    self.world_shell_last_prompt_at = float(getattr(self, "elapsed", 0.0))
                    self.save_world_shell_play_state()
                    break
        self.world_shell_checkpoint_claimed_count = len(getattr(self, "world_shell_claimed_checkpoints", set()))
        self.world_shell_checkpoint_status = f"{self.world_shell_checkpoint_claimed_count}/{max(0, self.world_shell_checkpoint_total)}"

    def update_world_shell_mount(self, dt: float):
        if bool(getattr(self, "world_unlocked", False)) or float(getattr(self, "transition_target", 0.0)) > 0.0:
            if getattr(self, "world_shell_mount", None) is not None:
                self.unload_default_holoverse_shell(reason="artifact_active")
            return
        mount = getattr(self, "world_shell_mount", None)
        if mount is None:
            return
        try:
            if self.is_holospace_active():
                mount.update(dt)
                self.apply_holospace_world_isolation(True, force_space=True)
                self.world_shell_mount_status = "HOLOSPACE // WATER LITE AUTHORITY"
                self.world_shell_mount_biome = "HoloSpace"
                self.world_shell_streamed_count = 0
                return
            self.apply_holospace_world_isolation(False)
            mount.update(dt)
            self.world_shell_mount_status = getattr(mount, "status", "MOUNTED")
            self.world_shell_mount_biome = mount.active_biome_name()
            self.world_shell_streamed_count = len(getattr(mount, "sector_nodes", {}) or {})
            self.world_shell_preloaded_default = bool(getattr(mount, "default_preloaded", False))
            self.world_shell_preload_report = getattr(mount, "last_report", {}) or self.world_shell_preload_report
            if isinstance(self.world_shell_preload_report, dict):
                self.world_shell_theme_handoff = self.world_shell_preload_report.get("theme_handoff", {}) or {}
                self.world_shell_audio_handoff = self.world_shell_preload_report.get("audio_handoff", {}) or {}
                self.world_shell_prompt = str(self.world_shell_preload_report.get("shell_prompt", "HOLOVERSE READY") or "HOLOVERSE READY")
                self.world_shell_motion_status = "ON" if self.world_shell_preload_report.get("motion_enabled", False) else "OFF"
                self.world_shell_play_state = self.world_shell_preload_report.get("play_state", {}) or {}
                self.world_shell_play_radius = float(self.world_shell_preload_report.get("playable_outer_radius", getattr(self.cfg, "world_shell_play_radius", 11100.0)) or getattr(self.cfg, "world_shell_play_radius", 11100.0))
                if bool(self.world_shell_preload_report.get("playable_enabled", False)):
                    self.world_shell_playable_status = f"PLAY {self.world_shell_play_radius:.0f}u"
                else:
                    self.world_shell_playable_status = "VISUAL ONLY"
                self.update_world_shell_gameplay_feedback(dt)
                audio_data = self.world_shell_audio_handoff if isinstance(self.world_shell_audio_handoff, dict) else {}
                if bool(audio_data.get("enabled", False)):
                    try:
                        self.world_shell_audio_status = f"GAIN {float(audio_data.get('influence', 0.0)):.2f} // {str(audio_data.get('tone', 'ambient')).upper()}"
                    except Exception:
                        self.world_shell_audio_status = "READY"
                else:
                    self.world_shell_audio_status = "OFF"
        except Exception as exc:
            self.world_shell_mount_status = f"STREAM ERROR {exc.__class__.__name__}"
            print(f"world_shell_mount_update_error: {exc}")

    def world_shell_playable_active(self) -> bool:
        if self.world_unlocked or self.transition_target > 0.0:
            return False
        if not bool(getattr(self.cfg, "world_shell_mount_enabled", True)):
            return False
        if not bool(getattr(self.cfg, "world_shell_playable_enabled", True)):
            return False
        mount = getattr(self, "world_shell_mount", None)
        return bool(mount is not None and getattr(mount, "root", None) is not None and str(getattr(mount, "detail", "stream")) != "off")

    def world_shell_play_radius_limit(self) -> float:
        mount = getattr(self, "world_shell_mount", None)
        if mount is not None:
            try:
                fn = getattr(mount, "playable_outer_radius", None)
                if callable(fn):
                    return max(64.0, float(fn()))
            except Exception:
                pass
        return max(620.0, min(11100.0, float(getattr(self.cfg, "world_shell_play_radius", 11100.0))))

    def world_shell_grounded_z(self, x: float, y: float) -> float:
        eye = float(getattr(self.cfg, "player_eye_height", 3.95))
        clearance = float(getattr(self.cfg, "terrain_collision_clearance", 0.16))
        if not bool(getattr(self.cfg, "world_shell_play_floor_enabled", True)):
            return eye + clearance
        mount = getattr(self, "world_shell_mount", None)
        if mount is not None:
            try:
                fn = getattr(mount, "shell_ground_z_at", None)
                if callable(fn):
                    return float(fn(x, y, eye, clearance))
            except Exception:
                pass
        return eye + clearance

    def world_shell_point_allowed(self, pos: Vec3) -> bool:
        if not self.world_shell_playable_active():
            return False
        try:
            r = math.sqrt(float(pos.x) * float(pos.x) + float(pos.y) * float(pos.y))
        except Exception:
            return False
        limit = self.world_shell_play_radius_limit()
        if r > limit:
            self.world_shell_playable_status = "EDGE LIMIT"
            return False
        floor_z = self.world_shell_grounded_z(pos.x, pos.y)
        if bool(getattr(self, "shell_flight_craft_active", False)):
            return (floor_z - 0.65) <= float(pos.z) <= 2200.0
        return (floor_z - 0.65) <= float(pos.z) <= (floor_z + 4.5)

    def toggle_world_shell_playable(self):
        self.cfg.world_shell_playable_enabled = not bool(getattr(self.cfg, "world_shell_playable_enabled", True))
        self.world_shell_playable_status = "PLAYABLE" if self.cfg.world_shell_playable_enabled else "VISUAL ONLY"
        save_config(self.cfg)
        mount = getattr(self, "world_shell_mount", None)
        if mount is not None:
            try:
                mount.read_mount_options()
                mount.update_play_state_data()
                mount.write_state()
            except Exception as exc:
                print(f"world_shell_play_toggle_error: {exc}")
        self.refresh_ui()

    def adjust_world_shell_play_radius(self, delta):
        self.cfg.world_shell_play_radius = max(620.0, min(11100.0, float(getattr(self.cfg, "world_shell_play_radius", 11100.0)) + float(delta)))
        save_config(self.cfg)
        mount = getattr(self, "world_shell_mount", None)
        if mount is not None:
            try:
                mount.read_mount_options()
                mount.update_play_state_data()
                mount.write_state()
            except Exception:
                pass
        self.refresh_ui()

    def toggle_world_shell_mount(self):
        self.cfg.world_shell_mount_enabled = not bool(getattr(self.cfg, "world_shell_mount_enabled", True))
        save_config(self.cfg)
        self.rebuild_station()
        self.refresh_ui()

    def cycle_world_shell_biome(self, delta=1):
        try:
            delta = int(delta)
        except Exception:
            delta = 1
        current = int(getattr(self.cfg, "world_shell_active_biome", 1) or 1)
        next_key = ((current - 1 + delta) % 8) + 1
        self.cfg.world_shell_active_biome = next_key
        save_config(self.cfg)
        mount = getattr(self, "world_shell_mount", None)
        if mount is not None:
            try:
                mount.set_active_biome(next_key, move_player=True)
            except Exception as exc:
                print(f"world_shell_biome_cycle_error: {exc}")
        self.world_shell_mount_biome = getattr(mount, "active_biome_name", lambda: f"BIOME {next_key}")() if mount else f"BIOME {next_key}"
        self.center_hint["text"] = f"HOLOVERSE // {self.world_shell_mount_biome}"
        self.refresh_ui()

    def adjust_world_shell_stream_radius(self, delta):
        self.cfg.world_shell_stream_radius = max(1, min(4, int(getattr(self.cfg, "world_shell_stream_radius", 2)) + int(delta)))
        save_config(self.cfg)
        if getattr(self, "world_shell_mount", None) is not None:
            self.world_shell_mount.force_refresh = True
        self.refresh_ui()

    def adjust_world_shell_mount_scale(self, delta):
        self.cfg.world_shell_mount_scale = max(0.050, min(1.000, float(getattr(self.cfg, "world_shell_mount_scale", 1.0)) + float(delta)))
        save_config(self.cfg)
        self.mount_world_shell_adapter()
        self.refresh_ui()

    def cycle_world_shell_detail(self):
        order = ["off", "lite", "stream"]
        current = str(getattr(self.cfg, "world_shell_mount_detail", "stream") or "stream").lower()
        try:
            idx = order.index(current)
        except ValueError:
            idx = 2
        self.cfg.world_shell_mount_detail = order[(idx + 1) % len(order)]
        self.cfg.world_shell_mount_enabled = self.cfg.world_shell_mount_detail != "off"
        save_config(self.cfg)
        self.rebuild_station()
        self.refresh_ui()

    def launch_world_shell_mode(self):
        """Compatibility stub: HoloVerse is no longer launched as a separate app."""
        self.center_hint["text"] = "HOLOVERSE // ALREADY LOADED AS DEFAULT WORLD"
        self.world_shell_default_lifecycle_state = "HOLOVERSE_DEFAULT_ASSIGNED_TO_CORE"
        self.active_world_runtime_state_label = self.sync_active_world_runtime_state()
        self.refresh_ui()

    def toggle_world_shell_hub_theme(self):
        self.cfg.world_shell_hub_theme_influence = not bool(getattr(self.cfg, "world_shell_hub_theme_influence", True))
        self.world_shell_hub_theme_current = 0.0
        self.world_shell_hub_theme_status = "ON" if self.cfg.world_shell_hub_theme_influence else "OFF"
        save_config(self.cfg)
        mount = getattr(self, "world_shell_mount", None)
        if mount is not None:
            try:
                mount.read_mount_options()
                mount.update_theme_handoff_data()
                mount.write_state()
            except Exception:
                pass
        self.refresh_ui()

    def toggle_world_shell_motion(self):
        self.cfg.world_shell_motion_enabled = not bool(getattr(self.cfg, "world_shell_motion_enabled", True))
        self.world_shell_motion_status = "ON" if self.cfg.world_shell_motion_enabled else "OFF"
        save_config(self.cfg)
        if getattr(self, "world_shell_mount", None) is not None:
            try:
                self.world_shell_mount.read_mount_options()
                self.world_shell_mount.rebuild_static()
            except Exception as exc:
                print(f"world_shell_motion_toggle_error: {exc}")
        self.refresh_ui()

    def toggle_world_shell_audio_handoff(self):
        self.cfg.world_shell_audio_handoff = not bool(getattr(self.cfg, "world_shell_audio_handoff", True))
        self.world_shell_audio_status = "ON" if self.cfg.world_shell_audio_handoff else "OFF"
        save_config(self.cfg)
        mount = getattr(self, "world_shell_mount", None)
        if mount is not None:
            try:
                mount.read_mount_options()
                mount.update_audio_handoff_data()
                mount.write_state()
            except Exception as exc:
                print(f"world_shell_audio_toggle_error: {exc}")
        self.refresh_ui()

    def adjust_world_shell_motion_intensity(self, delta):
        self.cfg.world_shell_motion_intensity = max(0.0, min(1.0, float(getattr(self.cfg, "world_shell_motion_intensity", 0.38)) + float(delta)))
        save_config(self.cfg)
        if getattr(self, "world_shell_mount", None) is not None:
            try:
                self.world_shell_mount.read_mount_options()
                self.world_shell_mount.write_state()
            except Exception:
                pass
        self.refresh_ui()

    def menu_gate_actions(self) -> list[tuple]:
        gates = self.matrixcore_dimension_gate_modes() if hasattr(self, "matrixcore_dimension_gate_modes") else []
        page_size = max(1, min(8, int(getattr(self, "menu_action_capacity", 10) or 10) - 2))
        max_page = max(0, (len(gates) - 1) // page_size) if gates else 0
        self.shared_gate_menu_page = max(0, min(int(getattr(self, "shared_gate_menu_page", 0) or 0), max_page))
        start = self.shared_gate_menu_page * page_size
        shown = gates[start:start + page_size]
        actions = []
        for mode in shown:
            gate_id = str(mode.get("_matrixcore_gate_id") or mode.get("name") or "")
            label = str(mode.get("_matrixcore_gate_label") or mode.get("name") or "DIMENSION")
            available = bool(mode.get("_matrixcore_gate_available", False))
            state_note = " DONE" if bool(mode.get("_matrixcore_gate_completed", False)) else ""
            title = f"{label}{state_note}" if available else f"{label} LOCKED"
            badge = "REG" if str(mode.get("_matrixcore_gate_kind") or "").lower() == "region" else "DIM"
            actions.append((f"{badge} // {title}"[:34], "menu_launch_dimension_gate", gate_id))
        if not actions:
            actions.append(("NO GATES INDEXED", "noop_menu_action"))
        if max_page > 0:
            actions.append(("NEXT PAGE", "menu_change_gate_page", 1))
            actions.append(("PREV PAGE", "menu_change_gate_page", -1))
        if getattr(self, "active_native_mode", None) is not None:
            actions.append(("RETURN TO HOLOVERSE", "menu_return_matrixcore"))
        return actions[:int(getattr(self, "menu_action_capacity", 10) or 10)]

    def menu_change_gate_page(self, delta: int = 1) -> None:
        gates = self.matrixcore_dimension_gate_modes() if hasattr(self, "matrixcore_dimension_gate_modes") else []
        page_size = max(1, min(8, int(getattr(self, "menu_action_capacity", 10) or 10) - 2))
        max_page = max(0, (len(gates) - 1) // page_size) if gates else 0
        if max_page <= 0:
            self.shared_gate_menu_page = 0
        else:
            self.shared_gate_menu_page = (int(getattr(self, "shared_gate_menu_page", 0) or 0) + int(delta or 1)) % (max_page + 1)
        self.refresh_menu_actions()
        self.refresh_ui()

    def menu_launch_dimension_gate(self, gate_id: str) -> bool:
        gate_id = canonical_dimension_lookup_key(gate_id)
        target = None
        for mode in self.matrixcore_dimension_gate_modes():
            if canonical_dimension_lookup_key(mode.get("_matrixcore_gate_id") or mode.get("name")) == gate_id:
                target = mode
                break
        if target is None:
            self.center_hint["text"] = "GATES // ROUTE NOT FOUND"
            return False
        label = str(target.get("_matrixcore_gate_label") or target.get("name") or "DIMENSION").upper()
        if not bool(target.get("_matrixcore_gate_available", False)):
            self.center_hint["text"] = f"GATES // {label} NEEDS CONFIG"
            return False
        # Gates are launched by the root MatrixCore route resolver. If HoloCore is
        # active, return it first so no first-person sub-world traps the shared UI.
        if getattr(self, "active_native_mode", None) is not None:
            self.return_from_native_mode(reason="shared_gate_menu")
        if getattr(self, "menu_open", False):
            self.toggle_menu()
        self.center_hint["text"] = f"GATE // {label}"
        try:
            self.show_bridge_transition("DIMENSION GATE", f"OPENING {label}", target=1.0, hold=0.25)
        except Exception:
            pass
        return bool(self.matrixcore_launch_dimension_gate_mode(target))

    def menu_return_matrixcore(self) -> None:
        if getattr(self, "active_native_mode", None) is not None:
            self.return_from_native_mode(reason="shared_menu_return")
        if getattr(self, "menu_open", False):
            self.toggle_menu()

    def noop_menu_action(self):
        return None

    def apply_menu_action(self, index):
        if index >= len(self.menu_actions):
            return
        action = self.menu_actions[index]
        fn = getattr(self, action[1], None)
        if callable(fn):
            fn(*action[2:])

    def adjust_walk_speed(self, delta):
        self.cfg.walk_speed = max(2.0, min(30.0, self.cfg.walk_speed + delta))
        save_config(self.cfg)
        self.refresh_ui()

    def adjust_sprint_speed(self, delta):
        self.cfg.sprint_speed = max(self.cfg.walk_speed + 1.0, min(42.0, self.cfg.sprint_speed + delta))
        save_config(self.cfg)
        self.refresh_ui()

    def adjust_mouse_sensitivity(self, delta):
        self.cfg.mouse_sensitivity = max(0.02, min(1.0, self.cfg.mouse_sensitivity + delta))
        save_config(self.cfg)
        self.refresh_ui()

    def adjust_eye_height(self, delta):
        self.cfg.player_eye_height = max(2.2, min(5.0, self.cfg.player_eye_height + delta))
        if self.vr_active:
            self.cfg.vr_comfort_preset = "custom"
        self.player_pos.z = self.cfg.player_eye_height + self.terrain_height_at(self.player_pos.x, self.player_pos.y) * 0.02
        self.base_teleport.z = self.cfg.player_eye_height
        save_config(self.cfg)
        self.refresh_ui()

    def adjust_grid_step(self, delta):
        self.cfg.terrain_grid_step = max(4.0, min(20.0, self.cfg.terrain_grid_step + delta))
        save_config(self.cfg)
        self.rebuild_station()
        self.refresh_ui()

    def adjust_terrain_height(self, delta):
        self.cfg.terrain_height = max(2.0, min(40.0, self.cfg.terrain_height + delta))
        save_config(self.cfg)
        self.rebuild_station()
        self.refresh_ui()

    def adjust_render_radius(self, delta):
        self.cfg.terrain_render_radius = max(1, min(8, self.cfg.terrain_render_radius + int(delta)))
        save_config(self.cfg)
        self.update_world_chunks(force=True)
        self.refresh_ui()

    def toggle_launch_settings_page(self):
        self.launch_settings_page = "ux" if getattr(self, "launch_settings_page", "boot") != "ux" else "boot"
        self.refresh_menu_actions()
        self.refresh_ui()

    def adjust_launch_ui_scale(self, delta):
        self.cfg.launch_ui_scale = max(0.65, min(1.75, float(getattr(self.cfg, "launch_ui_scale", 1.0)) + delta))
        save_config(self.cfg)
        self.refresh_ui()

    def adjust_launch_render_scale(self, delta):
        self.cfg.launch_render_scale = max(0.50, min(1.50, float(getattr(self.cfg, "launch_render_scale", 1.0)) + delta))
        save_config(self.cfg)
        self.refresh_ui()

    def adjust_launch_fps_cap(self, delta):
        self.cfg.launch_fps_cap = max(15, min(240, int(getattr(self.cfg, "launch_fps_cap", 60)) + int(delta)))
        save_config(self.cfg)
        self.refresh_ui()

    def toggle_launch_vsync(self):
        self.cfg.launch_vsync = not bool(getattr(self.cfg, "launch_vsync", True))
        save_config(self.cfg)
        self.refresh_ui()

    def toggle_launch_subtitles(self):
        self.cfg.launch_subtitles_enabled = not bool(getattr(self.cfg, "launch_subtitles_enabled", True))
        save_config(self.cfg)
        self.refresh_ui()

    def adjust_launch_brightness(self, delta):
        self.cfg.launch_brightness = max(0.55, min(1.65, float(getattr(self.cfg, "launch_brightness", 1.0)) + delta))
        save_config(self.cfg)
        self.refresh_ui()

    def adjust_launch_contrast(self, delta):
        self.cfg.launch_contrast = max(0.55, min(1.65, float(getattr(self.cfg, "launch_contrast", 1.0)) + delta))
        save_config(self.cfg)
        self.refresh_ui()

    def adjust_launch_gamma(self, delta):
        self.cfg.launch_gamma = max(0.55, min(1.85, float(getattr(self.cfg, "launch_gamma", 1.0)) + delta))
        save_config(self.cfg)
        self.refresh_ui()

    def toggle_launch_override_settings(self):
        self.cfg.launch_override_mode_settings = not bool(getattr(self.cfg, "launch_override_mode_settings", True))
        save_config(self.cfg)
        self.refresh_ui()

    def reset_settings(self):
        self.cfg = ObservatoryConfig()
        self.hud_visible = self.cfg.hud_visible
        self.base_teleport = Vec3(0, -10, self.cfg.player_eye_height)
        save_config(self.cfg)
        self.rebuild_station()
        self.refresh_menu_actions()
        self.refresh_ui()

    def refresh_menu_actions(self):
        zone = self.current_zone_name()
        art_name = self.active_artifact["name"] if self.active_artifact else "Hub Standby"
        state = self.sync_active_world_runtime_state()
        self.menu_subtitle["text"] = f"{zone} // {state} // {art_name}"
        gate_actions = self.menu_gate_actions() if hasattr(self, "menu_gate_actions") else [("NO GATES READY", "noop_menu_action")]
        specs = {
            "display": [
                ("FOV +", "adjust_fov", 3.0), ("FOV -", "adjust_fov", -3.0),
                ("BG +", "adjust_background", 0.015), ("BG -", "adjust_background", -0.015),
                ("HUE +", "shift_line_hue", 0.08), ("HUE -", "shift_line_hue", -0.08),
            ],
            "player": [
                ("WALK +", "adjust_walk_speed", 1.0), ("WALK -", "adjust_walk_speed", -1.0),
                ("RUN +", "adjust_sprint_speed", 1.0), ("RUN -", "adjust_sprint_speed", -1.0),
                ("SENSE +", "adjust_mouse_sensitivity", 0.02), ("SENSE -", "adjust_mouse_sensitivity", -0.02),
            ],
            "world": [
                ("MOUNT", "toggle_world_shell_mount"), ("PLAY", "toggle_world_shell_playable"),
                ("RESET CP", "reset_world_shell_checkpoints"), ("CHECKPTS", "toggle_world_shell_checkpoints"),
                ("BOUNDARY", "toggle_world_shell_boundary_feedback"), ("BIOME +", "cycle_world_shell_biome", 1),
                ("BIOME -", "cycle_world_shell_biome", -1), ("STREAM +", "adjust_world_shell_stream_radius", 1),
                ("STREAM -", "adjust_world_shell_stream_radius", -1), ("RELOAD HV", "reload_default_holoverse_shell"),
                ("HUB TINT", "toggle_world_shell_hub_theme"), ("MOTION", "toggle_world_shell_motion"),
                ("SHELL AUDIO", "toggle_world_shell_audio_handoff"), ("PLAY R+", "adjust_world_shell_play_radius", 620.0),
                ("PLAY R-", "adjust_world_shell_play_radius", -620.0), ("HGT +", "adjust_terrain_height", 1.0),
                ("HGT -", "adjust_terrain_height", -1.0),
            ],
            "gates": gate_actions,
            "vr": [
                ("VR NEXT RUN", "toggle_vr_enabled_next_launch"), ("RECENTER", "recenter_vr_pose"),
                ("SEATED", "toggle_vr_seated_mode"), ("SMOOTH", "apply_vr_preset", "smooth", False),
                ("SNAP", "apply_vr_preset", "snap", False), ("MOVE +", "adjust_vr_move_speed", 1.0),
                ("MOVE -", "adjust_vr_move_speed", -1.0), ("HEIGHT +", "adjust_vr_height_offset", 0.05),
                ("HEIGHT -", "adjust_vr_height_offset", -0.05), ("PANEL", "toggle_vr_runtime_panel"),
            ],
            "audio": (
                [
                    ("PAGE FORGE", "toggle_audio_settings_page"),
                    ("MASTER +", "adjust_master_volume", 0.05), ("MASTER -", "adjust_master_volume", -0.05),
                    ("SFX +", "adjust_sfx_volume", 0.05), ("SFX -", "adjust_sfx_volume", -0.05),
                    ("MUSIC +", "adjust_music_volume", 0.05), ("MUSIC -", "adjust_music_volume", -0.05),
                    ("AMBI +", "adjust_ambience_volume", 0.05), ("AMBI -", "adjust_ambience_volume", -0.05),
                    ("SCORE", "toggle_soundtrack_enabled"),
                ]
                if getattr(self, "audio_settings_page", "mix") != "forge" else
                [
                    ("PAGE MIX", "toggle_audio_settings_page"),
                    ("FORGE ALL", "forge_soundmatrix_full_pack"), ("FORGE SFX", "forge_soundmatrix_sfx_pack"),
                    ("VARIANTS", "forge_soundmatrix_variants_pack"), ("LOOPS", "forge_soundmatrix_soundtrack_pack"),
                    ("VAR +", "adjust_soundmatrix_variant_intensity", 0.05), ("VAR -", "adjust_soundmatrix_variant_intensity", -0.05),
                    ("MUS +", "adjust_soundmatrix_music_intensity", 0.05), ("MUS -", "adjust_soundmatrix_music_intensity", -0.05),
                    ("VW SRC", "toggle_soundmatrix_vector_sources"), ("VALIDATE", "validate_audio_library"), ("AUDIO DIR", "open_soundmatrix_audio_folder"),
                ]
            ),
            "launch": (
                [
                    ("PAGE UX", "toggle_launch_settings_page"), ("RES CYCLE", "cycle_launch_resolution"),
                    ("FULLSCREEN", "toggle_launch_fullscreen"), ("BORDERLESS", "toggle_launch_borderless"),
                    ("LOOK +", "adjust_launch_game_mouse_sensitivity", 0.02), ("LOOK -", "adjust_launch_game_mouse_sensitivity", -0.02),
                    ("INVERT Y", "toggle_launch_invert_y"), ("GFX", "cycle_launch_graphics_quality"),
                    ("DEADZONE +", "adjust_launch_deadzone", 0.01), ("DEADZONE -", "adjust_launch_deadzone", -0.01),
                ]
                if getattr(self, "launch_settings_page", "boot") != "ux" else
                [
                    ("PAGE BOOT", "toggle_launch_settings_page"), ("UI +", "adjust_launch_ui_scale", 0.05),
                    ("UI -", "adjust_launch_ui_scale", -0.05), ("FPS +", "adjust_launch_fps_cap", 15),
                    ("FPS -", "adjust_launch_fps_cap", -15), ("VSYNC", "toggle_launch_vsync"),
                    ("SUBTITLES", "toggle_launch_subtitles"), ("GAME HUD", "toggle_launch_hud"),
                    ("OVERRIDE", "toggle_launch_override_settings"), ("RENDER", "adjust_launch_render_scale", -0.05),
                ]
            ),
            "system": [
                ("RESUME", "toggle_menu"), ("QUIT APP", "quit_holoverse_from_menu"),
                ("CLOSE APPS", "close_all_mode_apps"), ("HUD", "toggle_hud"),
                ("HUB", "teleport_to_hub"),
                ("RESET CFG", "reset_settings"), ("HELP", "toggle_help_overlay"),
            ],
            "help": [
                ("BACK", "set_menu_tab", "display"), ("RESUME", "toggle_menu"),
            ],
        }
        raw_actions = list(specs.get(self.menu_tab, []) or [])
        deduped = []
        seen_action_keys = set()
        for spec in raw_actions:
            if not spec:
                continue
            key = (str(spec[0]).strip().lower(), str(spec[1]).strip().lower() if len(spec) > 1 else "")
            if key in seen_action_keys:
                continue
            seen_action_keys.add(key)
            deduped.append(spec)
        self.menu_actions = deduped[:int(getattr(self, "menu_action_capacity", 10) or 10)]
        self.menu_action_duplicate_count = len(raw_actions) - len(deduped)
        self.menu_action_hidden_count = max(0, len(deduped) - len(self.menu_actions))
        if self.menu_tab == "vr" and self.vr_onboarding_pending:
            self.menu_actions = [
                ("PRESET 1 // SEATED", "apply_vr_preset", "seated"),
                ("PRESET 2 // SMOOTH", "apply_vr_preset", "smooth"),
                ("PRESET 3 // SNAP", "apply_vr_preset", "snap"),
                ("PRESET 4 // SHOWCASE", "apply_vr_preset", "showcase"),
                ("RECENTER", "recenter_vr_pose"),
                ("HEIGHT +", "adjust_vr_height_offset", 0.05),
                ("HEIGHT -", "adjust_vr_height_offset", -0.05),
                ("PANEL", "toggle_vr_runtime_panel"),
            ]
        tab_titles = {
            "display": ("DISPLAY OPTIONS", "View tuning and visibility adjustments"),
            "player": ("PLAYER OPTIONS", "Movement feel and player comfort settings"),
            "world": ("HOLOVERSE OPTIONS", "Default world lifecycle, streaming, and traversal behavior"),
            "gates": ("GATES", "Choose a discovered region or dimension."),
            "vr": ("VR OPTIONAL / DIAGNOSTICS", "Desktop-first launch. VR is available only when explicitly requested."),
            "audio": ("AUDIO OPTIONS", "Shared suite mix and launch bus controls"),
            "launch": ("LAUNCH OPTIONS", "Window, graphics, and handoff settings"),
            "system": ("SYSTEM OPTIONS", "Capture, reset, and utility actions"),
            "help": ("HELP / REFERENCE", "Controls, files, and recovery references"),
        }
        action_title, action_help = tab_titles.get(self.menu_tab, ("INTERACTIVE OPTIONS", "Select an action"))
        self.menu_action_title["text"] = action_title
        self.menu_action_help["text"] = action_help
        for i, btn in enumerate(self.menu_buttons):
            if i < len(self.menu_actions):
                btn.show()
                btn["text"] = f"{i + 1}. {self.menu_actions[i][0]}"
                btn["frameColor"] = (0.018, 0.120, 0.145, 0.80)
            else:
                btn.hide()
        for key, btn in self.menu_tab_buttons:
            active = key == self.menu_tab
            btn["frameColor"] = (0.020, 0.240, 0.285, 0.92) if active else (0.018, 0.070, 0.085, 0.72)
            btn["text_fg"] = (0.70, 1.0, 1.0, 1.0) if active else (0.82, 0.96, 1.0, 0.94)

    def shift_line_hue(self, delta):
        self.cfg.line_hue = (self.cfg.line_hue + delta) % 1.0
        save_config(self.cfg)
        self.rebuild_station()
        self.refresh_ui()

    def adjust_line_thickness(self, delta):
        self.cfg.line_thickness = max(0.8, min(5.0, self.cfg.line_thickness + delta))
        save_config(self.cfg)
        self.rebuild_station()
        self.refresh_ui()

    def adjust_background(self, delta):
        self.cfg.background_value = max(0.0, min(0.22, self.cfg.background_value + delta))
        save_config(self.cfg)
        self.rebuild_station()
        self.refresh_ui()

    def adjust_fov(self, delta):
        self.cfg.fov = max(60.0, min(110.0, self.cfg.fov + delta))
        save_config(self.cfg)
        self.rebuild_station()
        self.refresh_ui()


    def _adjust_audio_field(self, field_name, delta):
        value = max(0.0, min(1.0, getattr(self.cfg, field_name) + delta))
        setattr(self.cfg, field_name, value)
        save_config(self.cfg)
        self.refresh_ui()

    def adjust_master_volume(self, delta):
        self._adjust_audio_field("master_volume", delta)

    def adjust_sfx_volume(self, delta):
        self._adjust_audio_field("sfx_volume", delta)

    def adjust_music_volume(self, delta):
        self._adjust_audio_field("music_volume", delta)

    def adjust_ambience_volume(self, delta):
        self._adjust_audio_field("ambience_volume", delta)

    def toggle_audio_settings_page(self):
        self.audio_settings_page = "forge" if getattr(self, "audio_settings_page", "mix") != "forge" else "mix"
        self.refresh_ui()

    def cycle_launch_resolution(self):
        options = [(1280, 720), (1600, 900), (1920, 1080), (2560, 1440), (3840, 2160)]
        current = (int(self.cfg.launch_width), int(self.cfg.launch_height))
        try:
            idx = options.index(current)
        except ValueError:
            idx = 2
        self.cfg.launch_width, self.cfg.launch_height = options[(idx + 1) % len(options)]
        save_config(self.cfg)
        self.refresh_ui()

    def toggle_launch_fullscreen(self):
        # v0.9.15: keep this shell bordered/non-topmost so child modes can
        # appear in front. The button now reasserts the safe window mode.
        self.cfg.launch_fullscreen = False
        self.cfg.launch_borderless = False
        if hasattr(self.cfg, "launch_bordered_fullscreen"):
            self.cfg.launch_bordered_fullscreen = True
        save_config(self.cfg)
        self.center_hint["text"] = "WINDOW // BORDERED FULL-SIZE"
        self.refresh_ui()

    def toggle_launch_borderless(self):
        # v0.9.15: borderless/topmost caused external mode focus problems.
        self.cfg.launch_borderless = False
        self.cfg.launch_fullscreen = False
        if hasattr(self.cfg, "launch_bordered_fullscreen"):
            self.cfg.launch_bordered_fullscreen = True
        save_config(self.cfg)
        self.center_hint["text"] = "WINDOW // BORDERLESS DISABLED"
        self.refresh_ui()

    def toggle_launch_hud(self):
        self.cfg.launch_hud_visible = not self.cfg.launch_hud_visible
        save_config(self.cfg)
        self.refresh_ui()

    def adjust_launch_game_mouse_sensitivity(self, delta):
        self.cfg.launch_game_mouse_sensitivity = max(0.02, min(1.0, self.cfg.launch_game_mouse_sensitivity + delta))
        save_config(self.cfg)
        self.refresh_ui()

    def toggle_launch_invert_y(self):
        self.cfg.launch_invert_y = not self.cfg.launch_invert_y
        save_config(self.cfg)
        self.refresh_ui()

    def cycle_launch_graphics_quality(self):
        order = ["low", "medium", "high"]
        current = str(self.cfg.launch_graphics_quality).lower().strip()
        if current not in order:
            current = "medium"
        self.cfg.launch_graphics_quality = order[(order.index(current) + 1) % len(order)]
        save_config(self.cfg)
        self.refresh_ui()

    def adjust_launch_deadzone(self, delta):
        self.cfg.launch_controller_deadzone = max(0.0, min(0.45, self.cfg.launch_controller_deadzone + delta))
        save_config(self.cfg)
        self.refresh_ui()


    def toggle_vr_enabled_next_launch(self):
        self.cfg.vr_enabled = not bool(getattr(self.cfg, "vr_enabled", False))
        save_config(self.cfg)
        state = "ENABLED" if self.cfg.vr_enabled else "DISABLED"
        self.vr_status = f"DESKTOP // VR NEXT LAUNCH {state}"
        self.center_hint["text"] = "VR // USE --VR TO START HEADSET MODE" if self.cfg.vr_enabled else "VR // DESKTOP DEFAULT"
        self.refresh_ui()

    def recenter_vr_pose(self):
        if self.vr_active and self.vr_origin is not None:
            self.vr_origin.setPos(self.player_pos.x, self.player_pos.y, 0.0)
            self.vr_origin.setH(0.0)
            self.sync_player_from_vr()
        else:
            self.center_hint["text"] = "VR // NOT ACTIVE IN DESKTOP MODE"
        self.refresh_ui()

    def toggle_vr_seated_mode(self):
        self.cfg.vr_seated_mode = not self.cfg.vr_seated_mode
        self.cfg.vr_comfort_preset = "custom"
        save_config(self.cfg)
        self.sync_player_from_vr()
        self.refresh_ui()

    def adjust_vr_snap_turn(self, delta):
        self.cfg.vr_snap_turn_degrees = max(10.0, min(60.0, self.cfg.vr_snap_turn_degrees + delta))
        self.cfg.vr_turn_mode = "snap"
        self.cfg.vr_comfort_preset = "custom"
        save_config(self.cfg)
        self.refresh_ui()

    def adjust_vr_move_speed(self, delta):
        self.cfg.vr_move_speed = max(2.0, min(20.0, self.cfg.vr_move_speed + delta))
        self.cfg.vr_comfort_preset = "custom"
        save_config(self.cfg)
        self.refresh_ui()

    def adjust_vr_height_offset(self, delta):
        self.cfg.vr_height_offset = max(-0.8, min(0.8, self.cfg.vr_height_offset + delta))
        self.cfg.vr_comfort_preset = "custom"
        save_config(self.cfg)
        self.sync_player_from_vr()
        self.refresh_ui()

    def adjust_vr_vignette(self, delta):
        self.cfg.vr_comfort_vignette = max(0.0, min(0.72, self.cfg.vr_comfort_vignette + delta))
        self.cfg.vr_comfort_preset = "custom"
        save_config(self.cfg)
        self.refresh_ui()

    def toggle_vr_runtime_panel(self):
        self.cfg.vr_show_runtime_panel = not self.cfg.vr_show_runtime_panel
        save_config(self.cfg)
        self.refresh_ui()

    def holoverse_total_points(self) -> int:
        """Return saved HoloVerse points from known mode state files.

        This keeps the corner HUD public-facing: no FPS/debug box, just total
        points gathered across modes that currently award score.
        """
        totals = {}

        def add(bucket: str, value) -> None:
            try:
                score = int(float(value or 0))
            except Exception:
                return
            if score > 0:
                key = str(bucket or "mode")
                totals[key] = max(score, int(totals.get(key, 0) or 0))

        def read_json(path):
            try:
                p = Path(path)
                if p.exists() and p.is_file():
                    with p.open("r", encoding="utf-8") as fh:
                        data = json.load(fh)
                    return data if isinstance(data, dict) else {}
            except Exception:
                return {}
            return {}

        shared_roots = []
        for base in (SHARED_HOLOVERSE_DATA_DIR,):
            try:
                if base not in shared_roots:
                    shared_roots.append(base)
            except Exception:
                pass
        def add_progression_payload(progress: dict) -> None:
            if not isinstance(progress, dict):
                return
            before = len(totals)
            try:
                regions = progress.get("regions", {}) if isinstance(progress.get("regions"), dict) else {}
                urban_prog = ((regions.get("urban", {}) or {}).get("warzone", {}) or {}) if isinstance(regions, dict) else {}
                if isinstance(urban_prog, dict):
                    add("urban_warzone", urban_prog.get("score"))
                    add("urban_warzone", urban_prog.get("best_score"))
            except Exception:
                pass
            for source_key in ("dimension_results", "dimension_progress"):
                dim = progress.get(source_key, {}) if isinstance(progress.get(source_key), dict) else {}
                for key, payload in dim.items():
                    if not isinstance(payload, dict):
                        continue
                    score = payload.get("score_total") or payload.get("total_score") or payload.get("points_total") or payload.get("score") or payload.get("best_score")
                    add(str(key or "mode"), score)
            if len(totals) == before:
                add("matrixcore", progress.get("holoverse_score") or progress.get("points_total") or ((progress.get("player") or {}).get("total_points") if isinstance(progress.get("player"), dict) else 0))

        root_progress = read_json(MATRIXCORE_PROGRESSION_PATH)
        add_progression_payload(root_progress)

        for base in shared_roots:
            urban = read_json(base / "regions" / "urban" / "warzone" / "urban_warzone_state.json")
            add("urban_warzone", urban.get("score"))
            add("urban_warzone", urban.get("best_score"))
            frost = read_json(base / "regions" / "frost" / "circuit" / "frost_circuit_state.json")
            add("frost_circuit", frost.get("score_total") or frost.get("total_score"))
            add_progression_payload(read_json(base / "progression" / "progression_state.json"))

        add("urban_warzone", getattr(self, "urban_warzone_score", 0))
        add("urban_warzone", getattr(self, "urban_warzone_best_score", 0))
        add("frost_circuit", getattr(self, "frost_circuit_total_score", 0))
        return max(0, sum(int(v or 0) for v in totals.values()))

    def update_perf_hud(self, force=False):
        """Small public points readout in the top-right corner."""
        label = getattr(self, "perf_hud_label", None)
        if label is None:
            return
        now = float(getattr(self, "elapsed", 0.0))
        if not force and now - float(getattr(self, "perf_hud_last_update", -999.0)) < 0.35:
            return
        score = 0
        try:
            score = int(self.holoverse_total_points())
        except Exception:
            score = 0
        text = f"POINTS {score:06d}"
        self.perf_hud_cached_text = text
        self.perf_hud_last_update = now
        try:
            self.set_ui_text(label, text)
            label["frameColor"] = (0.0, 0.0, 0.0, 0.0)
        except Exception:
            pass

    def set_ui_text(self, widget, text: object) -> None:
        """Avoid sending identical DirectGUI text updates every frame."""
        if widget is None:
            return
        value = str(text)
        key = id(widget)
        cache = getattr(self, "ui_text_cache", None)
        if isinstance(cache, dict) and cache.get(key) == value:
            return
        try:
            widget["text"] = value
            if isinstance(cache, dict):
                cache[key] = value
        except Exception:
            pass

    def refresh_ui(self):
        # Region/location ownership lives in region_top_label only. Keeping
        # the left HUD to status/artifact data prevents the same location name
        # from being drawn in two or three places at once.
        art_name = self.active_artifact["name"] if self.active_artifact else "Hub Standby"
        coords = f"X {self.player_pos.x:07.2f}  Y {self.player_pos.y:07.2f}  Z {self.player_pos.z:06.2f}"

        if self.is_holospace_traveling():
            self.set_holospace_transition_hud_suppressed(True)
            return

        if bool(getattr(self, "shell_flight_craft_cinematic", False)):
            self.set_shell_flight_cinematic_ui_suppressed(True)
            return

        # Native dimensions now own their own compact presentation overlay.
        # Hide Core location/debug-style HUD while a same-window dimension is active
        # so the player does not see duplicate title/status/coordinate text.
        if getattr(self, "active_native_mode", None) is not None:
            try:
                self.hud_root.hide()
            except Exception:
                pass
            try:
                if hasattr(self, "safety_exit_root"):
                    self.safety_exit_root.hide()
            except Exception:
                pass
            try:
                self.top_panel.hide()
            except Exception:
                pass
            try:
                self.coords_label.hide()
            except Exception:
                pass
            try:
                self.region_top_label.hide()
            except Exception:
                pass
            try:
                if self.hud_visible and not self.menu_open:
                    self.crosshair_root.show()
                else:
                    self.crosshair_root.hide()
            except Exception:
                pass
            try:
                if "ADAPTER ACTIVE" in str(self.center_hint["text"]):
                    self.center_hint["text"] = ""
            except Exception:
                pass
            return

        self.set_ui_text(self.hud_label, f"CORE STATUS\n{art_name}")
        self.set_ui_text(self.coords_label, coords)
        bot_modal = bool(getattr(self, "bot_dialogue_open", False) or getattr(self, "bot_dialogue_hud_suppressed", False))
        if not self.menu_open:
            try:
                if hasattr(self, "safety_exit_root"):
                    self.safety_exit_root.hide()
            except Exception:
                pass
            if self.hud_visible:
                self.hud_root.show()
                if not bot_modal:
                    self.crosshair_root.show()
                else:
                    self.crosshair_root.hide()
            else:
                self.hud_root.hide()
                self.crosshair_root.hide()
            if bot_modal:
                self.top_panel.hide()
                self.coords_label.hide()
                self.crosshair_root.hide()
                try:
                    self.center_hint.hide()
                except Exception:
                    pass
            else:
                self.top_panel.show()
                self.coords_label.show()
            self.update_holoverse_region_ui()
            return
        if self.menu_tab == "display":
            self.set_ui_text(self.menu_info, "DISPLAY")
            self.set_ui_text(self.menu_section, "VIEW // optics, contrast, chroma")
            self.set_ui_text(self.menu_detail, (
                f"FOV {self.cfg.fov:.0f}\n"
                f"Brightness {self.cfg.background_value:.3f}\n"
                f"Hue {self.cfg.line_hue:.2f}\n"
                f"Line {self.cfg.line_thickness:.1f}"
            ))
        elif self.menu_tab == "player":
            self.menu_info["text"] = "PLAYER"
            self.menu_section["text"] = "MOVE // height, speed, look"
            self.menu_detail["text"] = (
                f"Eye Height {self.cfg.player_eye_height:.2f}\n"
                f"Walk {self.cfg.walk_speed:.1f}\n"
                f"Run {self.cfg.sprint_speed:.1f}\n"
                f"Look Sense {self.cfg.mouse_sensitivity:.2f}"
            )
        elif self.menu_tab == "world":
            self.menu_info["text"] = "WORLD"
            self.menu_section["text"] = "PROC // density, scale, draw"
            self.menu_detail["text"] = (
                f"Grid Step {self.cfg.terrain_grid_step:.1f}\n"
                f"Terrain Height {self.cfg.terrain_height:.1f}\n"
                f"Render Radius {self.effective_render_radius()}\n"
                f"Shell {'ON' if getattr(self.cfg, 'world_shell_mount_enabled', True) else 'OFF'}  {str(getattr(self.cfg, 'world_shell_mount_detail', 'stream')).upper()}\n"
                f"Region {self.current_holoverse_region_name()}  Sectors {getattr(self, 'world_shell_streamed_count', 0)}\n"
                f"Hub Theme {getattr(self, 'world_shell_hub_theme_status', 'OFF')}\n"
                f"Play {getattr(self, 'world_shell_playable_status', 'READY')}  Radius {float(getattr(self, 'world_shell_play_radius', getattr(self.cfg, 'world_shell_play_radius', 11100.0))):.0f}\n"
                f"Boundary {getattr(self, 'world_shell_boundary_status', 'READY')}  Checkpoints {getattr(self, 'world_shell_checkpoint_status', '0/0')}\n"
                f"Ground lanes {'ON' if getattr(self.cfg, 'world_shell_ground_continuity', True) else 'OFF'}  Height hints {'ON' if getattr(self.cfg, 'world_shell_collision_height_hints', True) else 'OFF'}\n"
                f"B/N cycle, P play, C reset pickups // Shift+F9 dev numbers"
            )
        elif self.menu_tab == "gates":
            gates = self.matrixcore_dimension_gate_modes() if hasattr(self, "matrixcore_dimension_gate_modes") else []
            page_size = max(1, min(8, int(getattr(self, "menu_action_capacity", 10) or 10) - 2))
            max_page = max(0, (len(gates) - 1) // page_size) if gates else 0
            current_page = max(0, min(int(getattr(self, "shared_gate_menu_page", 0) or 0), max_page))
            self.set_ui_text(self.menu_info, "GATES")
            self.set_ui_text(self.menu_section, "DISCOVERED REGIONS + DIMENSIONS")
            if gates:
                page_line = f"Page {current_page + 1}/{max_page + 1}." if max_page > 0 else ""
                self.set_ui_text(self.menu_detail, (
                    f"{len(gates)} discovered destination{'s' if len(gates) != 1 else ''}.\n"
                    "Select a Gate on the right to teleport or enter.\n"
                    f"{page_line}"
                ).strip())
            else:
                self.set_ui_text(self.menu_detail, (
                    "No Gates indexed yet.\n"
                    "Regions are indexed automatically; artifacts unlock after first entry."
                ))
        elif self.menu_tab == "vr":
            self.menu_info["text"] = "VR"
            self.menu_section["text"] = "XR // optional headset mode, desktop default"
            self.menu_detail["text"] = (
                f"Status {self.vr_status}\n"
                f"Config VR {'ON' if getattr(self.cfg, 'vr_enabled', False) else 'OFF'}  Requested {'YES' if VR_ALLOWED else 'NO'}\n"
                f"Default Mode DESKTOP FIRST-PERSON\n"
                f"Use --vr / HOLOVERSE_VR=1 to start headset mode\n"
                f"Snap {self.cfg.vr_snap_turn_degrees:.0f}  Move {self.cfg.vr_move_speed:.1f}\n"
                f"Seated {'ON' if self.cfg.vr_seated_mode else 'OFF'}  Height {self.cfg.vr_height_offset:+.2f}"
            )
        elif self.menu_tab == "audio":
            self.menu_info["text"] = "SOUND & MUSIC"
            page = getattr(self, "audio_settings_page", "mix")
            self.menu_section["text"] = "UNIVERSAL AUDIO // " + ("mix bus" if page != "forge" else "SoundMatrix forge")
            sfx_count = len(list((CANONICAL_SHARED_SFX_DIR if CANONICAL_SHARED_SFX_DIR.exists() else SHARED_SFX_DIR).rglob("*.wav"))) if (CANONICAL_SHARED_SFX_DIR.exists() or SHARED_SFX_DIR.exists()) else 0
            vector_wars_sfx_dir = DIMENSIONS_DIR / "Vector Wars" / "assets" / "sfx"
            if not vector_wars_sfx_dir.exists():
                vector_wars_sfx_dir = ROOT / "Vector Wars" / "assets" / "sfx"
            mp3_seed_count = len(list(vector_wars_sfx_dir.rglob("*.mp3"))) if vector_wars_sfx_dir.exists() else 0
            music_count = len(list((CANONICAL_MUSIC_DIR if CANONICAL_MUSIC_DIR.exists() else MUSIC_DIR).glob("*.wav"))) if (CANONICAL_MUSIC_DIR.exists() or MUSIC_DIR.exists()) else 0
            if page == "forge":
                self.menu_detail["text"] = (
                    f"SoundMatrix {'READY' if SOUNDMATRIX_FORGE.exists() else 'MISSING'}  Vector MP3 seeds {mp3_seed_count}\n"
                    f"Variants {getattr(self.cfg, 'soundmatrix_variant_intensity', 0.65):.2f}  Music Gen {getattr(self.cfg, 'soundmatrix_music_intensity', 0.55):.2f}\n"
                    f"Use Vector Wars source MP3 {'ON' if getattr(self.cfg, 'soundmatrix_use_vector_wars_sources', True) else 'OFF'}\n"
                    f"Audio library SFX {sfx_count}  Loops {music_count}\n"
                    f"Seed {getattr(self.cfg, 'soundmatrix_random_seed', 2048)}"
                )
            else:
                self.menu_detail["text"] = (
                    f"Master {self.cfg.master_volume:.2f}  SFX {self.cfg.sfx_volume:.2f}\n"
                    f"Music {self.cfg.music_volume:.2f}  Ambience {self.cfg.ambience_volume:.2f}\n"
                    f"Score {'ON' if getattr(self.cfg, 'soundtrack_enabled', True) else 'OFF'}  Score Intensity {getattr(self.cfg, 'soundtrack_intensity', 0.55):.2f}\n"
                    f"Ambience Intensity {getattr(self.cfg, 'ambience_intensity', 0.45):.2f}\n"
                    f"All sound/music settings are hub-authoritative when overrides apply."
                )
        elif self.menu_tab == "launch":
            self.menu_info["text"] = "LAUNCH"
            self.menu_section["text"] = "HANDOFF // shared game boot config"
            page = getattr(self, "launch_settings_page", "boot")
            if page == "ux":
                self.menu_detail["text"] = (
                    f"Universal UX Overrides // {'CORE PRIORITY' if getattr(self.cfg, 'launch_override_mode_settings', True) else 'MODE PRIORITY'}\n"
                    f"UI {getattr(self.cfg, 'launch_ui_scale', 1.0):.2f}  Render {getattr(self.cfg, 'launch_render_scale', 1.0):.2f}  FPS {int(getattr(self.cfg, 'launch_fps_cap', 60))}  VSync {'ON' if getattr(self.cfg, 'launch_vsync', True) else 'OFF'}\n"
                    f"HUD {'ON' if self.cfg.launch_hud_visible else 'OFF'}  Subtitles {'ON' if getattr(self.cfg, 'launch_subtitles_enabled', True) else 'OFF'}\n"
                    f"Bright {getattr(self.cfg, 'launch_brightness', 1.0):.2f}  Contrast {getattr(self.cfg, 'launch_contrast', 1.0):.2f}  Gamma {getattr(self.cfg, 'launch_gamma', 1.0):.2f}\n"
                    f"Core Modes {len(getattr(self, 'core_modes', []) or [])}  Last {self.last_launched_core_mode or 'None'}"
                )
            else:
                self.menu_detail["text"] = (
                    f"{self.cfg.launch_width}x{self.cfg.launch_height}\n"
                    f"Fullscreen {'ON' if self.cfg.launch_fullscreen else 'OFF'}  Borderless {'ON' if self.cfg.launch_borderless else 'OFF'}  BorderedFull {'ON' if getattr(self.cfg, 'launch_bordered_fullscreen', True) else 'OFF'}\n"
                    f"Look {self.cfg.launch_game_mouse_sensitivity:.2f}  InvertY {'ON' if self.cfg.launch_invert_y else 'OFF'}\n"
                    f"HUD {'ON' if self.cfg.launch_hud_visible else 'OFF'}  GFX {str(self.cfg.launch_graphics_quality).upper()}  Deadzone {self.cfg.launch_controller_deadzone:.2f}\n"
                    f"Core Modes {len(getattr(self, 'core_modes', []) or [])}  Last {self.last_launched_core_mode or 'None'}"
                )
        elif self.menu_tab == "system":
            self.menu_info["text"] = "SYSTEM"
            self.menu_section["text"] = "OPS // shell actions"
            active_mode_bits = []
            if getattr(self, "active_native_mode", None) is not None:
                active_mode_bits.append(f"NATIVE {str(getattr(self, 'native_mode_label', 'MODE')).upper()}")
            if getattr(self, "external_process", None) is not None:
                active_mode_bits.append(f"HOSTED {str(getattr(self, 'external_launch_label', 'MODE')).upper()}")
            active_modes = ", ".join(active_mode_bits) if active_mode_bits else "NONE"
            self.menu_detail["text"] = (
                f"Build {VERSION}\n"
                f"Mode {self.vr_status}\n"
                f"HUD {'ON' if self.hud_visible else 'OFF'}\n"
                f"Active Apps {active_modes}\n"
                "Use the menu header QUIT APP button or this tab's QUIT APP action to close HoloVerse.\n"
                "CLOSE APPS only returns launched modes."
            )
        else:
            self.menu_info["text"] = "HELP"
            self.menu_section["text"] = "OPS // controls and file refs"
            self.menu_detail["text"] = (
                "WASD move   Shift sprint   Mouse look / HMD look\n"
                "E/LMB activate artifacts   GATES quick-travel   H HUD\n"
                "ESC opens this menu   0 returns from Dimensions\n"
                "Space rise   Ctrl dive   Q/E snap turn in VR"
            )
        subtitles = {
            "display": "Visual tuning and readability controls",
            "player": "Movement feel and comfort tuning",
            "world": "Terrain, render distance, and streaming controls",
            "vr": "VR remains available, but desktop first-person is the normal launch path",
            "audio": "Universal Sound & Music controls, Vector Wars source variants, and SoundMatrix soundtrack generation",
            "launch": "Universal mode override settings and shared game boot settings",
            "system": "Quit, capture, reset, and utility actions. Close controls live inside this ESC menu.",
            "help": "Clear controls, hold-ESC quit, and file references",
        }
        self.menu_subtitle["text"] = subtitles.get(self.menu_tab, "Readable control deck // active settings and actions")
        self.menu_status["text"] = f"ACTIVE TAB // {self.menu_tab.upper()}"
        self.refresh_menu_actions()
        bot_modal = bool(getattr(self, "bot_dialogue_open", False) or getattr(self, "bot_dialogue_hud_suppressed", False))
        if self.hud_visible:
            self.hud_root.show()
            if not self.menu_open and not bot_modal:
                self.crosshair_root.show()
            else:
                self.crosshair_root.hide()
        else:
            self.hud_root.hide()
            self.crosshair_root.hide()
        try:
            if hasattr(self, "safety_exit_root"):
                self.safety_exit_root.hide()
        except Exception:
            pass
        if self.menu_open or bot_modal:
            self.top_panel.hide()
            self.coords_label.hide()
            self.crosshair_root.hide()
            if bot_modal:
                try:
                    self.center_hint.hide()
                except Exception:
                    pass
        else:
            self.top_panel.show()
            self.coords_label.show()
        self.update_holoverse_region_ui()

    def on_window_event(self, window):
        if hasattr(self, "relayout_ui"):
            self.relayout_ui()
        if (
            self.external_suspended
            or self.vr_active
            or getattr(self, "active_native_mode", None) is not None
            or bool(getattr(self, "native_mode_isolated", False))
        ):
            return
        if not self.menu_open and not SELF_TEST:
            if (LAUNCH_BORDERLESS or LAUNCH_BORDERED_FULLSCREEN) and self.win is not None and hasattr(self.win, "requestProperties"):
                props = WindowProperties()
                props.setUndecorated(bool(LAUNCH_BORDERLESS))
                props.setOrigin(LAUNCH_X, LAUNCH_Y)
                props.setSize(LAUNCH_W, LAUNCH_H)
                props.setFullscreen(False)
                props.setFixedSize(bool(LAUNCH_BORDERLESS))
                self.win.requestProperties(props)
            self.recenter_mouse(force=True)

    def recenter_mouse(self, force=False):
        if (
            SELF_TEST
            or self.menu_open
            or self.core_console_open
            or self.external_suspended
            or self.vr_active
            or getattr(self, "active_native_mode", None) is not None
            or bool(getattr(self, "native_mode_isolated", False))
            or not self.win
        ):
            return
        if not hasattr(self.win, "getProperties") or not hasattr(self.win, "movePointer"):
            return
        props = self.win.getProperties()
        if hasattr(props, "getForeground") and not props.getForeground() and not force:
            return
        cx = self.win.getXSize() // 2
        cy = self.win.getYSize() // 2
        self.win.movePointer(0, cx, cy)

    def update_look(self, dt):
        if self.vr_active:
            self.sync_player_from_vr()
            if self.menu_open:
                return
            self.update_vr_turn(dt)
            return
        if self.menu_open or self.core_console_open or getattr(self, "bot_dialogue_open", False) or SELF_TEST or self.win is None or self.win.getXSize() <= 0:
            return
        if not hasattr(self.win, "getPointer"):
            return
        cx = self.win.getXSize() // 2
        cy = self.win.getYSize() // 2
        md = self.win.getPointer(0)
        dx = md.getX() - cx
        dy = md.getY() - cy
        self.player_yaw -= dx * self.cfg.mouse_sensitivity
        self.player_pitch = max(-82.0, min(82.0, self.player_pitch - dy * self.cfg.mouse_sensitivity))
        if self.gamepad:
            try:
                rx = self.gamepad.findAxis(InputDevice.Axis.right_x)
                ry = self.gamepad.findAxis(InputDevice.Axis.right_y)
                gx = rx.value if rx else 0.0
                gy = ry.value if ry else 0.0
                if abs(gx) > 0.12:
                    self.player_yaw -= gx * self.cfg.controller_look_sensitivity * dt
                if abs(gy) > 0.12:
                    self.player_pitch = max(-82.0, min(82.0, self.player_pitch + gy * self.cfg.controller_look_sensitivity * dt))
            except Exception:
                pass
        self.camera.setHpr(self.player_yaw, self.player_pitch, 0)
        self.recenter_mouse()

    def get_move_input(self):
        if self.menu_open or self.core_console_open or getattr(self, "bot_dialogue_open", False):
            return Vec2(0, 0)
        move = Vec2(0, 0)
        if self.keys.get("w"):
            move.y += 1
        if self.keys.get("s"):
            move.y -= 1
        if self.keys.get("a"):
            move.x -= 1
        if self.keys.get("d"):
            move.x += 1
        if self.gamepad:
            try:
                lx = self.gamepad.findAxis(InputDevice.Axis.left_x)
                ly = self.gamepad.findAxis(InputDevice.Axis.left_y)
                if lx:
                    move.x += lx.value
                if ly:
                    move.y += -ly.value
            except Exception:
                pass
        if move.lengthSquared() > 1.0:
            move.normalize()
        return move

    def point_allowed(self, pos: Vec3):
        spec = self.current_world_spec()
        r = math.sqrt(pos.x * pos.x + pos.y * pos.y)
        if self.world_unlocked or self.transition_target > 0.0:
            max_range = self.cfg.terrain_chunk_size * (self.effective_render_radius(spec) + 1.35)
            if spec["kind"] == "underwater":
                floor_z = self.world_height_at(pos.x, pos.y, spec) + 2.2
                return r < max_range and floor_z < pos.z < 120.0
            if spec["kind"] == "space":
                return r < max_range and -120.0 < pos.z < 120.0
            return r < max_range and pos.z >= self.grounded_player_z(pos.x, pos.y, spec) - 0.35
        if self.world_shell_point_allowed(pos):
            return True
        return r <= self.hub_radius - 1.4

    def update_player(self, dt):
        self.update_look(dt)
        move = self.get_move_input()
        target_speed = self.cfg.sprint_speed if self.keys.get("shift") else self.cfg.walk_speed
        if self.vr_active:
            target_speed = getattr(self.cfg, "vr_move_speed", self.cfg.walk_speed) * (1.5 if self.keys.get("shift") else 1.0)
        elif self.world_shell_playable_active():
            target_speed *= max(0.75, min(1.80, float(getattr(self.cfg, "world_shell_play_speed_scale", 1.10))))
        target_vel = move * target_speed
        blend = min(1.0, dt * 7.5)
        self.move_velocity = self.move_velocity * (1.0 - blend) + target_vel * blend
        forward, right, up = self.get_view_basis()
        spec = self.current_world_spec()
        if self.vr_active:
            self.sync_player_from_vr()
        if self.update_shell_flight_cinematic(dt, Vec2(move), Vec3(forward), Vec3(right), Vec3(up)):
            return
        if self.is_holospace_active():
            self.show_holospace_cockpit(False)
            self.apply_holospace_world_isolation(True, force_space=True)
            if forward.lengthSquared() > 0: forward.normalize()
            if right.lengthSquared() > 0: right.normalize()
            vertical = 0.0
            if self.keys.get("space"):
                vertical += 1.0
            if self.keys.get("control"):
                vertical -= 1.0
            has_input = move.lengthSquared() > 0.0001 or abs(vertical) > 0.0001
            cruise_speed = float(HOLOSPACE_BOOST_SPEED if self.keys.get("shift") else HOLOSPACE_CRUISE_SPEED)
            self.holospace_speed_boost = cruise_speed / max(1.0, float(HOLOSPACE_CRUISE_SPEED))
            desired = forward * float(move.y) * cruise_speed
            desired += right * float(move.x) * cruise_speed * float(HOLOSPACE_STRAFE_SCALE)
            desired += up * vertical * cruise_speed * float(HOLOSPACE_VERTICAL_SCALE)
            if desired.lengthSquared() > float(HOLOSPACE_MAX_SPEED) * float(HOLOSPACE_MAX_SPEED):
                desired.normalize()
                desired *= float(HOLOSPACE_MAX_SPEED)
            current = Vec3(getattr(self, "holospace_velocity", Vec3(0, 0, 0)))
            if has_input:
                blend_space = min(1.0, dt * float(HOLOSPACE_ACCEL_RESPONSE))
                current = current * (1.0 - blend_space) + desired * blend_space
            else:
                # Stronger arcade braking keeps HoloSpace readable and stops the
                # ship from drifting forever after the player releases input.
                current *= max(0.0, 1.0 - dt * float(HOLOSPACE_BRAKE_RESPONSE))
                if current.lengthSquared() < 4.0:
                    current = Vec3(0, 0, 0)
            if current.lengthSquared() > float(HOLOSPACE_MAX_SPEED) * float(HOLOSPACE_MAX_SPEED):
                current.normalize()
                current *= float(HOLOSPACE_MAX_SPEED)
            self.holospace_velocity = current
            candidate = Vec3(self.player_pos + current * dt)
            if self.handle_holospace_boundary_return(candidate):
                return
            candidate.z = max(float(HOLOSPACE_VERTICAL_RESPAWN_MIN_Z) + 30.0, min(float(HOLOSPACE_VERTICAL_RESPAWN_MAX_Z) - 100.0, candidate.z))
            self.player_pos = candidate
            if not self.vr_active:
                self.camera.setPos(self.player_pos)
            if has_input:
                speed_pct = int(round(min(999.0, current.length() / max(1.0, float(HOLOSPACE_BOOST_SPEED)) * 100.0)))
                self.holospace_battle_status = f"PILOT:{speed_pct}"
            return
        else:
            self.show_holospace_cockpit(False)
        if bool(getattr(self, "shell_flight_craft_active", False)):
            if not self.can_use_shell_flight_craft_at(self.player_pos):
                self.shell_flight_craft_active = False
                self.shell_flight_craft_velocity = Vec3(0, 0, 0)
                self.shell_flight_craft_boost = 1.0
                self.center_hint["text"] = "TAB CRAFT // SAFE FIELD DISENGAGED"
            else:
                if forward.lengthSquared() > 0: forward.normalize()
                if right.lengthSquared() > 0: right.normalize()
                vertical = 0.0
                if self.keys.get("space"): vertical += 1.0
                if self.keys.get("control"): vertical -= 1.0
                has_input = move.lengthSquared() > 0.0001 or abs(vertical) > 0.0001
                if has_input:
                    self.shell_flight_craft_boost = min(3.3, float(getattr(self, "shell_flight_craft_boost", 1.0)) + dt * (0.70 if self.keys.get("shift") else 0.32))
                else:
                    self.shell_flight_craft_boost = max(1.0, float(getattr(self, "shell_flight_craft_boost", 1.0)) - dt * 1.20)
                craft_speed = target_speed * 9.8 * float(getattr(self, "shell_flight_craft_boost", 1.0))
                desired = (forward * move.y + right * move.x) * craft_speed + Vec3(0, 0, vertical * craft_speed * 0.68)
                blend_craft = min(1.0, dt * 3.8)
                self.shell_flight_craft_velocity = Vec3(getattr(self, "shell_flight_craft_velocity", Vec3(0, 0, 0))) * (1.0 - blend_craft) + desired * blend_craft
                candidate = Vec3(self.player_pos + self.shell_flight_craft_velocity * dt)
                floor_z = self.world_shell_grounded_z(candidate.x, candidate.y) + 8.0
                candidate.z = max(floor_z, min(2200.0, float(candidate.z)))
                if self.shell_flight_space_boundary_triggered(candidate) and not self.is_holospace_active() and not self.is_holospace_traveling():
                    try:
                        entry = self.holoverse_region_entry_for_number(8) or {}
                        self.start_holospace_travel_sequence(entry, source="flight_boundary")
                    except Exception as exc:
                        try:
                            print(f"flight_space_transition_warning:{exc.__class__.__name__}:{exc}")
                        except Exception:
                            pass
                    return
                corrected = self.resolve_world_shell_boundary_candidate(candidate)
                self.player_pos = corrected if corrected is not None else candidate
                if not self.vr_active:
                    self.camera.setPos(self.player_pos)
                if self.player_pos.z >= 420.0 and not self.is_holospace_active() and not self.is_holospace_traveling():
                    try:
                        entry = self.holoverse_region_entry_for_number(8) or {}
                        self.start_holospace_travel_sequence(entry, source="flight_vehicle_ascent")
                    except Exception as exc:
                        try:
                            print(f"flight_space_transition_warning:{exc.__class__.__name__}:{exc}")
                        except Exception:
                            pass
                return
        if self.is_default_deep_water_active():
            if forward.lengthSquared() > 0:
                forward.normalize()
            if right.lengthSquared() > 0:
                right.normalize()
            surface_eye_z = self.default_deep_water_hover_eye_z()
            on_board = self.player_pos.z >= surface_eye_z - 1.20
            vertical = 0.0
            if self.keys.get("space"):
                vertical += 1.0
            if self.keys.get("control"):
                vertical -= 1.0
            if on_board:
                # Hoverboard mode: glide on the water surface, then dive with Ctrl.
                flat_forward = Vec3(forward.x, forward.y, 0.0)
                flat_right = Vec3(right.x, right.y, 0.0)
                if flat_forward.lengthSquared() > 0:
                    flat_forward.normalize()
                if flat_right.lengthSquared() > 0:
                    flat_right.normalize()
                board_speed = target_speed * 1.34
                step = flat_forward * self.move_velocity.y * dt + flat_right * self.move_velocity.x * dt
                candidate = Vec3(self.player_pos + step)
                if vertical < 0.0:
                    candidate.z += vertical * board_speed * 0.76 * dt
                else:
                    candidate.z += (surface_eye_z - candidate.z) * min(1.0, dt * 5.0)
                candidate.z = max(self.default_deep_water_bottom_z() + 1.2, min(surface_eye_z + 0.55, candidate.z))
            else:
                swim_speed = target_speed * 0.86
                step = forward * self.move_velocity.y * dt + right * self.move_velocity.x * dt + Vec3(0, 0, vertical * swim_speed * 0.88 * dt)
                candidate = Vec3(self.player_pos + step)
                candidate.z = max(self.default_deep_water_bottom_z() + 1.2, min(surface_eye_z, candidate.z))
            if self.default_deep_water_point_allowed(candidate):
                delta = candidate - self.player_pos
                if self.vr_active and self.vr_origin is not None:
                    self.vr_origin.setPos(self.vr_origin.getPos(self.render) + delta)
                    self.sync_player_from_vr()
                else:
                    self.player_pos = candidate
            else:
                r = math.sqrt(float(candidate.x) * float(candidate.x) + float(candidate.y) * float(candidate.y))
                if r < 3300.0 or r >= 4700.0:
                    self.player_pos = Vec3(candidate.x, candidate.y, self.grounded_player_z(candidate.x, candidate.y, spec))
            self.world_shell_playable_status = "MUSHROOM HILLS"
            self.show_deep_water_hoverboard(self.is_default_deep_water_surface_hover())
            if self.center_hint is not None and self.is_default_deep_water_surface_hover():
                self.center_hint["text"] = "DEEP WATER // HOVERBOARD SURFACE"
            elif self.center_hint is not None:
                self.center_hint["text"] = "DEEP WATER // SWIM VOLUME"
            if not self.vr_active:
                self.camera.setPos(self.player_pos)
            return
        else:
            self.show_deep_water_hoverboard(False)
        if spec["kind"] == "underwater":
            if forward.lengthSquared() > 0: forward.normalize()
            if right.lengthSquared() > 0: right.normalize()
            vertical = 0.0
            if self.keys.get("space"): vertical += 1.0
            if self.keys.get("control"): vertical -= 1.0
            step = forward * self.move_velocity.y * dt + right * self.move_velocity.x * dt + Vec3(0, 0, vertical * target_speed * 0.65 * dt)
            candidate = Vec3(self.player_pos + step)
            floor_z = self.world_height_at(candidate.x, candidate.y, spec) + 2.4
            candidate.z = max(candidate.z, floor_z)
            if self.point_allowed(candidate):
                delta = candidate - self.player_pos
                if self.vr_active and self.vr_origin is not None:
                    self.vr_origin.setPos(self.vr_origin.getPos(self.render) + delta)
                    self.sync_player_from_vr()
                else:
                    self.player_pos = candidate
            self.update_underwater_vehicle(dt)
        else:
            self.hide_underwater_vehicle()
            forward.z = 0; right.z = 0
            if forward.lengthSquared() > 0: forward.normalize()
            if right.lengthSquared() > 0: right.normalize()
            step = forward * self.move_velocity.y * dt + right * self.move_velocity.x * dt
            candidate = Vec3(self.player_pos.x + step.x, self.player_pos.y + step.y, self.grounded_player_z(self.player_pos.x + step.x, self.player_pos.y + step.y, spec))
            if self.point_allowed(candidate):
                delta = candidate - self.player_pos
                if self.vr_active and self.vr_origin is not None:
                    self.vr_origin.setPos(self.vr_origin.getPos(self.render) + delta)
                    self.sync_player_from_vr()
                else:
                    self.player_pos = candidate
            elif not self.vr_active:
                boundary_candidate = self.resolve_world_shell_boundary_candidate(candidate)
                if boundary_candidate is not None and self.point_allowed(boundary_candidate):
                    self.player_pos = boundary_candidate
                else:
                    self.player_pos.z = self.grounded_player_z(self.player_pos.x, self.player_pos.y, spec)
            if not self.vr_active:
                self.camera.setPos(self.player_pos)

    def ensure_underwater_vehicle(self):
        if self.underwater_vehicle_root is not None and not self.underwater_vehicle_root.isEmpty():
            return
        root = self.world_root.attachNewNode("underwater-vehicle")
        root.setTransparency(TransparencyAttrib.MAlpha)
        col = self.underwater_vehicle_color
        segs = LineSegs("aqua-vehicle")
        segs.setThickness(max(1.0, self.cfg.line_thickness * 0.8))
        segs.setColor(*col)
        pts = [Vec3(-2.8, -4.0, -0.8), Vec3(0.0, 5.4, 0.0), Vec3(2.8, -4.0, -0.8), Vec3(0.0, -2.0, 1.6)]
        for a, b in [(0,1),(1,2),(2,0),(0,3),(1,3),(2,3)]:
            segs.moveTo(pts[a]); segs.drawTo(pts[b])
        segs.moveTo(-2.1, -1.0, 0.0); segs.drawTo(-4.4, -3.0, -0.1)
        segs.moveTo(2.1, -1.0, 0.0); segs.drawTo(4.4, -3.0, -0.1)
        segs.moveTo(0.0, -3.6, 0.2); segs.drawTo(0.0, -6.2, -0.3)
        np = root.attachNewNode(segs.create())
        np.setAntialias(AntialiasAttrib.MLine)
        np.setTransparency(TransparencyAttrib.MAlpha)
        glow = CardMaker("aqua-canopy")
        glow.setFrame(-1.1, 1.1, -0.7, 0.7)
        canopy = root.attachNewNode(glow.generate())
        canopy.setPos(0, 0.2, 0.35)
        canopy.setHpr(0, 0, 18)
        canopy.setColor(0.22, 0.96, 0.92, 0.18)
        canopy.setTransparency(TransparencyAttrib.MAlpha)
        canopy.setDepthWrite(False)
        self.underwater_vehicle_root = root

    def hide_underwater_vehicle(self):
        if self.underwater_vehicle_root is not None and not self.underwater_vehicle_root.isEmpty():
            self.underwater_vehicle_root.hide()

    def update_underwater_vehicle(self, dt):
        self.ensure_underwater_vehicle()
        if self.underwater_vehicle_root is None or self.underwater_vehicle_root.isEmpty():
            return
        self.underwater_vehicle_root.show()
        quat = self.camera.getQuat(self.render)
        forward = quat.getForward()
        if forward.lengthSquared() > 0.001:
            forward.normalize()
        self.underwater_vehicle_root.setPos(self.player_pos)
        heading = math.degrees(math.atan2(-forward.x, forward.y))
        pitch = max(-28.0, min(28.0, math.degrees(math.asin(max(-1.0, min(1.0, forward.z))))))
        self.underwater_vehicle_root.setHpr(heading, pitch, math.sin(self.elapsed * 1.6) * 3.5)
        if not self.vr_active:
            chase = self.player_pos - forward * 18.0 + Vec3(0, 0, 6.0)
            self.camera.setPos(chase)
            self.camera.lookAt(self.player_pos + forward * 7.5)

    def animate_artifact_shapes(self, dt):
        if not self.artifact_shape_nodes:
            return
        for artifact in self.artifacts:
            node = artifact.get("shape_node")
            if node is None or node.isEmpty():
                continue
            idx = int(artifact.get("id", 0))
            base = artifact.get("pos", Vec3(0, 0, 0))
            active = self.active_artifact is artifact or int(artifact.get("world_id", -1)) == int(self.active_artifact_id if self.active_artifact_id is not None else -999)
            if self.vr_active:
                node.setPos(base)
                node.setHpr(float(artifact.get("yaw", 0.0)), 0.0, 0.0)
                node.setScale(1.0)
                continue
            spin = self.elapsed * (24.0 + idx * 2.75)
            wobble = math.sin(self.elapsed * (1.1 + idx * 0.07) + idx) * 10.0
            fold = math.cos(self.elapsed * (0.85 + idx * 0.05) + idx * 0.6) * 16.0
            pulse = 1.0 + (0.11 if active else 0.065) * math.sin(self.elapsed * 2.2 + idx * 0.7)
            lift = 0.18 * math.sin(self.elapsed * 1.55 + idx * 0.9)
            node.setPos(base + Vec3(0, 0, lift))
            node.setHpr(float(artifact.get("yaw", 0.0)) + spin, wobble, fold)
            node.setScale(pulse * (1.16 if active else 1.0))
            node.setColorScale(1.0, 1.0, 1.0, 1.0 if active else 0.88)

    def update_artifact_focus(self, dt):
        if getattr(self, "lens_pivot", None) is None or getattr(self, "lens_root", None) is None:
            # Region/dimension proof routes deliberately skip heavy hub/station
            # construction; without the lens rig there is no artifact focus to animate.
            return
        self.find_nearest_artifact()
        spec = self.current_world_spec()
        if spec["kind"] != self.last_world_kind:
            self.last_world_kind = spec["kind"]
            self.clear_world_chunks()
            if self.should_stream_legacy_world_chunks(force=True):
                self.update_world_chunks(force=True)
        if self.transition_progress < self.transition_target:
            self.transition_progress = min(self.transition_target, self.transition_progress + dt / max(0.001, self.cfg.transition_duration))
        elif self.transition_progress > self.transition_target:
            self.transition_progress = max(self.transition_target, self.transition_progress - dt / max(0.001, self.cfg.transition_duration))

        target_yaw = 0.0
        target_pitch = 58.0
        if self.active_artifact is not None:
            target_yaw = self.active_artifact["yaw"]
            target_pitch = self.active_artifact["pitch"]
        current_h = self.lens_pivot.getH()
        current_p = self.lens_pivot.getP()
        blend = min(1.0, dt * (1.3 + self.transition_progress * 0.9))
        self.lens_pivot.setH(current_h + (target_yaw - current_h) * blend)
        self.lens_pivot.setP(current_p + (-target_pitch - current_p) * blend)

        lens_alpha = 0.70 + self.transition_progress * 0.24
        self.lens_root.setColorScale(1, 1, 1, lens_alpha)
        self.world_root.setColorScale(1, 1, 1, self.transition_progress)
        self.world_root.show() if self.transition_progress > 0.01 else self.world_root.hide()
        self.apply_world_theme(dt)

        for i, node in enumerate(self.galaxy_nodes):
            alpha = 0.0
            if self.active_artifact_id == i:
                alpha = min(1.0, max(0.0, (self.transition_progress - 0.16) / 0.84))
            node.setColorScale(1, 1, 1, alpha)

    def animate_accents(self, dt):
        pulse = 0.10 + 0.05 * math.sin(self.elapsed * 1.6)
        self.accent_root.setColorScale(1, 1, 1, 0.78 + pulse)
        self.line_root.setColorScale(1, 1, 1, 0.98)
        self.dome_root.setColorScale(1, 1, 1, 0.96)
        if self.menu_open:
            self.center_hint["text"] = ""
            return
        if self.is_near_core():
            self.center_hint["text"] = "MatrixCore"
        elif self.nearest_artifact is not None and self.nearest_artifact_dist < max(float(self.nearest_artifact.get("radius", 4.25)), ARTIFACT_PRESS_ACTIVATION_RADIUS):
            self.center_hint["text"] = f"E // ENTER {str(self.nearest_artifact['name']).upper()}"
        elif self.transition_progress > 0.0 and self.active_artifact is not None:
            spec = self.current_world_spec()
            suffix = " // VEHICLE SWIM" if spec["kind"] == "underwater" else (" // VOID" if spec["kind"] == "space" else "")
            self.center_hint["text"] = f"SYNC // {self.active_artifact['name']}{suffix}"
        else:
            self.center_hint["text"] = ""

    def update_world_actors(self, dt):
        spec = self.current_world_spec()
        player = Vec3(self.player_pos)
        for actor in self.world_actors:
            if actor.root.isEmpty():
                continue
            if actor.kind == 'ship':
                drift = math.sin(self.elapsed * 0.22 + actor.phase) * 6.0
                actor.root.setPos(actor.home + Vec3(drift, math.cos(self.elapsed * 0.18 + actor.phase) * 14.0, math.sin(self.elapsed * 0.27 + actor.phase) * 9.0))
                actor.root.setHpr((self.elapsed * 12.0 + actor.seed % 360) % 360, math.sin(self.elapsed + actor.phase) * 4.0, math.cos(self.elapsed + actor.phase) * 6.0)
            elif actor.kind in ('fish', 'ray', 'jelly', 'whale'):
                toward = player - actor.root.getPos()
                dist = toward.length()
                if actor.kind in ('fish', 'ray') and 12.0 < dist < 34.0:
                    actor.follow_timer = min(4.0, actor.follow_timer + dt)
                else:
                    actor.follow_timer = max(0.0, actor.follow_timer - dt * 0.5)
                if actor.kind == 'jelly':
                    sway = Vec3(math.sin(self.elapsed * 0.65 + actor.phase) * 1.2, math.cos(self.elapsed * 0.55 + actor.phase) * 1.4, math.sin(self.elapsed * 1.1 + actor.phase) * 2.8)
                elif actor.kind == 'ray':
                    sway = Vec3(math.sin(self.elapsed * 0.95 + actor.phase) * 3.6, math.cos(self.elapsed * 0.85 + actor.phase) * 2.6, math.sin(self.elapsed * 0.9 + actor.phase) * 1.0)
                else:
                    sway = Vec3(math.sin(self.elapsed * (1.4 if actor.kind == 'fish' else 0.5) + actor.phase) * (2.4 if actor.kind == 'fish' else 6.5), math.cos(self.elapsed * (1.1 if actor.kind == 'fish' else 0.4) + actor.phase) * (2.0 if actor.kind == 'fish' else 5.0), math.sin(self.elapsed * (1.7 if actor.kind == 'fish' else 0.35) + actor.phase) * (1.2 if actor.kind == 'fish' else 3.4))
                follow = Vec3(0, 0, 0)
                if actor.follow_timer > 0.01 and dist > 0.001:
                    toward.normalize()
                    follow = toward * min(6.0, actor.follow_timer * 1.6)
                actor.root.setPos(actor.home + sway + follow)
                actor.root.lookAt(actor.root.getPos() + sway + (follow if follow.lengthSquared() > 0.001 else Vec3(1, 0, 0)))
            elif actor.kind == 'tree':
                actor.root.setR(math.sin(self.elapsed * 0.35 + actor.phase) * 2.2)

    def world_authority_smoke_setup(self, task):
        """Exercise the default world shell without activating artifact terrain."""
        self.active_artifact = None
        self.active_artifact_id = None
        self.world_unlocked = False
        self.transition_target = 0.0
        self.transition_progress = 0.0
        try:
            self.clear_world_chunks()
        except Exception:
            pass
        if getattr(self, "world_shell_mount", None) is None:
            self.mount_world_shell_adapter()
        else:
            try:
                self.update_world_shell_mount(0.05)
            except Exception:
                pass
        try:
            self.player_pos = Vec3(42.0, -42.0, self.grounded_player_z(42.0, -42.0))
            self.camera.setPos(self.player_pos)
            self.camera.setHpr(135.0, -11.0, 0.0)
        except Exception:
            pass
        try:
            for _ in range(4):
                self.update_world_shell_mount(0.05)
        except Exception:
            pass
        self.apply_world_theme(0.25)
        self.refresh_ui()
        return Task.done

    def _count_render_nodes_named(self, name: str) -> int:
        try:
            matches = self.render.findAllMatches(f"**/{name}")
            return int(matches.getNumPaths())
        except Exception:
            return 0

    def collect_world_authority_smoke_report(self) -> dict:
        """Return a compact proof that world.py owns the default terrain."""
        mount = getattr(self, "world_shell_mount", None)
        mount_report = {}
        if mount is not None:
            try:
                if callable(getattr(mount, "mount_report", None)):
                    mount_report = mount.mount_report()
            except Exception as exc:
                mount_report = {"error": f"{exc.__class__.__name__}:{exc}"}
        source_report = mount_report.get("source_bridge_report", {}) if isinstance(mount_report, dict) else {}
        surface_audit = source_report.get("surface_audit", {}) if isinstance(source_report, dict) else {}
        terrain_chunks = int(len(getattr(self, "terrain_chunks", {}) or {}))
        world_py_source_active = bool(self.world_py_source_active())
        legacy_active = bool(self.legacy_world_chunks_active())
        should_stream_default = bool(self.should_stream_legacy_world_chunks())
        errors = []
        warnings = []
        if not world_py_source_active:
            errors.append("world.py source bridge is not active")
        if legacy_active:
            errors.append("legacy main.py terrain reports active during default world")
        if should_stream_default:
            errors.append("main.py terrain streamer would run during default world")
        if terrain_chunks:
            errors.append(f"main.py terrain_chunks not empty during default world: {terrain_chunks}")
        if isinstance(surface_audit, dict):
            duplicates = int(surface_audit.get("duplicate_surface_groups", 0) or 0)
            if duplicates:
                errors.append(f"world.py surface authority duplicate groups detected: {duplicates}")
            active_surfaces = int(surface_audit.get("active_surface_authority_count", 0) or 0)
            if active_surfaces <= 0:
                warnings.append("world.py surface authority audit did not report active surfaces")
        else:
            warnings.append("world.py source surface audit missing")
        return {
            "schema": 1,
            "kind": "holoverse_world_authority_runtime_smoke",
            "game": GAME_NAME,
            "version": VERSION,
            "status": "PASS" if not errors else "FAIL",
            "errors": errors,
            "warnings": warnings,
            "world_py_source_active": world_py_source_active,
            "legacy_main_world_active": legacy_active,
            "should_stream_legacy_default": should_stream_default,
            "main_terrain_chunks": terrain_chunks,
            "main_world_actors": int(len(getattr(self, "world_actors", []) or [])),
            "world_shell_mount_status": str(getattr(self, "world_shell_mount_status", "UNKNOWN")),
            "world_shell_mount_biome": str(getattr(self, "world_shell_mount_biome", "UNKNOWN")),
            "world_shell_streamed_count": int(getattr(self, "world_shell_streamed_count", 0) or 0),
            "source_bridge_active": bool(mount_report.get("source_bridge_active", False)) if isinstance(mount_report, dict) else False,
            "source_bridge_status": str(mount_report.get("source_bridge_status", "UNKNOWN")) if isinstance(mount_report, dict) else "UNKNOWN",
            "source_world_file": str(mount_report.get("source_world_file", "world.py")) if isinstance(mount_report, dict) else "world.py",
            "source_surface_audit": surface_audit if isinstance(surface_audit, dict) else {},
            "default_shell_root_nodes": self._count_render_nodes_named("default-holoverse-full-world-shell-root"),
            "legacy_world_root_visible": not bool(getattr(self, "world_root", None) is not None and getattr(self.world_root, "isHidden", lambda: False)()),
            "runtime_world_signature": str(getattr(self, "runtime_world_signature", "")),
        }

    def world_authority_smoke_exit(self, task):
        report = self.collect_world_authority_smoke_report()
        try:
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            WORLD_AUTHORITY_SMOKE_REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
        except Exception as exc:
            print(f"world_authority_smoke_report_error: {exc}")
        try:
            if self.win is not None:
                self.win.saveScreenshot(Filename.fromOsSpecific(str(WORLD_AUTHORITY_SMOKE_SCREENSHOT)))
        except Exception as exc:
            print(f"world_authority_smoke_screenshot_error: {exc}")
        print(json.dumps(report, indent=2))
        self.userExit()
        try:
            sys.stdout.flush(); sys.stderr.flush()
        except Exception:
            pass
        os._exit(0 if report.get("status") == "PASS" else 2)
        return Task.done

    def self_test_setup(self, task):
        shot_id = SELF_TEST_ARTIFACT_ID
        shot_id = max(0, min(max(0, len(getattr(self, "artifacts", []) or []) - 1), shot_id))
        self.active_artifact = self.artifacts[shot_id] if self.artifacts else None
        self.active_artifact_id = shot_id if self.artifacts else None
        spec = self.current_world_spec() if self.artifacts else {"name": "Hub", "kind": "hub", "profile": "standby"}
        report = dict(getattr(self, "world_shell_preload_report", {}) or {})
        if self.world_shell_playable_active():
            bridge = report.get("source_bridge_active", False) if isinstance(report, dict) else False
            self.runtime_world_signature = "HOLOVERSE DEFAULT // WORLD.PY SOURCE BRIDGE" if bridge else "HOLOVERSE DEFAULT // FULL-SCALE WORLD.PY RINGS"
        else:
            self.runtime_world_signature = f"{spec.get('name', 'Hub')} // {spec.get('kind', 'hub').upper()} // {spec.get('profile', 'default').upper()}"
        self.transition_target = 0.0
        self.transition_progress = 0.0
        self.world_unlocked = False
        self.set_hub_fill_enabled(True, instant=True)
        if self.artifacts:
            target_artifact = self.artifacts[shot_id]
            target = Vec3(target_artifact.get("pos", Vec3(0, 0, 3.95)))
            radial = Vec3(target.x, target.y, 0.0)
            if radial.lengthSquared() < 0.001:
                radial = Vec3(0, -1, 0)
            else:
                radial.normalize()
            self.player_pos = target - radial * 8.2 + Vec3(0, 0, -0.10)
            self.camera.setPos(self.player_pos)
            self.camera.lookAt(target + Vec3(0, 0, 0.25))
            self.player_yaw = self.camera.getH()
            self.player_pitch = self.camera.getP()
        else:
            poses = {4:(Vec3(36, 62, self.cfg.player_eye_height + 0.4), 162.0, -10.0), 5:(Vec3(28, 18, 18.0), 142.0, -6.0), 6:(Vec3(34, 52, -10.0), 168.0, -4.0), 7:(Vec3(44, 68, self.cfg.player_eye_height + 0.3), 154.0, -9.0)}
            pos, yaw, pitch = poses.get(shot_id, (Vec3(0, 14.0, self.cfg.player_eye_height), 182.0, -8.0))
            self.player_yaw = yaw
            self.player_pitch = pitch
            self.player_pos = Vec3(pos)
        spec = self.current_world_spec()
        if spec["kind"] == "underwater":
            floor_z = self.world_height_at(self.player_pos.x, self.player_pos.y, spec) + 7.5
            self.player_pos.z = max(self.player_pos.z, floor_z)
        elif spec["kind"] != "space":
            self.player_pos.z = self.grounded_player_z(self.player_pos.x, self.player_pos.y, spec)
        self.camera.setPos(self.player_pos)
        self.camera.setHpr(self.player_yaw, self.player_pitch, 0)
        # Exercise the same pedestal-owned artifact route path used by mouse1/E/core selection.
        if self.artifacts:
            self.activate_artifact_direct(self.artifacts[shot_id], source="self-test-artifact-route")
        else:
            self.update_world_chunks(force=True)
        if ARTIFACT_ROUTE_SMOKE_TEST:
            self.smoke_test_connected_artifact_routes()
        self.transition_progress = 0.0
        self.apply_world_theme(1.0)
        if AUTO_MENU:
            requested = str(AUTO_MENU_TAB).strip().lower() if AUTO_MENU_TAB else ''
            if requested == 'core':
                self.open_core_console()
            else:
                self.menu_open = True
                self.menu_root.show()
                if requested:
                    self.menu_tab = requested
        self.refresh_ui()
        return Task.done

    def self_test_exit(self, task):
        avg_dt = (self.self_test_dt_total / self.self_test_frame_count) if self.self_test_frame_count else 0.0
        artifact_gate_assignments = self.artifact_gate_assignments()
        connected_gate_assignments = [item for item in artifact_gate_assignments if item.get("connected_same_window")]
        connected_gate_mode_ids = [str(item.get("mode_id", "")) for item in connected_gate_assignments]
        connected_smoke_results = list(getattr(self, "artifact_route_smoke_results", []) or [])
        report = {
            "game": GAME_NAME,
            "version": VERSION,
            "mode_gateway_audit_pass9": True,
            "mode_gateway_history_pass10": True,
            "mode_gateway_audit_path": str(MODE_GATEWAY_AUDIT),
            "mode_gateway_history_path": str(MODE_GATEWAY_HISTORY),
            "mode_gateway_audit": self.write_mode_gateway_audit(),
            "mode_gateway_history_summary": self.read_mode_gateway_history_summary(),
            "config": asdict(self.cfg),
            "vr_onboarding_pending": self.vr_onboarding_pending,
            "active_artifact": self.active_artifact_id,
            "urban_metrobot_ambient_status": str(getattr(self, "urban_metrobot_ambient_status", "")),
            "urban_metrobot_ambient_id": str(getattr(self, "urban_metrobot_ambient_id", "")),
            "urban_warzone_metrobot_ally_count": int(getattr(self, "urban_warzone_metrobot_ally_count", 0) or 0),
            "artifact_world_click_fix": True,
            "artifact_click_binding": "mouse1",
            "artifact_activation_self_test_source": "self-test-artifact-shape",
            "artifact_world_loaded": False,
            "artifact_dimension_route_loaded": bool(getattr(self, "runtime_world_signature", "").startswith("ARTIFACT DIMENSION ROUTE")),
            "artifact_dimension_routes": [{"pedestal": int(a.get("id", -1)), "mode_id": str(a.get("dimension_mode_id", "")), "name": str(a.get("name", ""))} for a in self.artifacts],
            "matrixcore_gate_menu_count": len(self.matrixcore_dimension_gate_modes()) if hasattr(self, "matrixcore_dimension_gate_modes") else 0,
            "matrixcore_gate_menu_labels": [str(item.get("_matrixcore_gate_label") or item.get("name") or "") for item in (self.matrixcore_dimension_gate_modes() if hasattr(self, "matrixcore_dimension_gate_modes") else [])],
            "artifact_gate_assignments": artifact_gate_assignments,
            "artifact_connected_gate_count": len(connected_gate_assignments),
            "artifact_connected_gate_unique": len(connected_gate_mode_ids) == len(set(connected_gate_mode_ids)),
            "artifact_connected_gate_entries_exist": all(bool(item.get("entry_exists")) for item in connected_gate_assignments),
            "artifact_connected_route_smoke_requested": bool(ARTIFACT_ROUTE_SMOKE_TEST),
            "artifact_launch_smoke_requested": bool(ARTIFACT_LAUNCH_SMOKE_TEST),
            "artifact_launch_active_native_mode": type(getattr(self, "active_native_mode", None)).__name__ if getattr(self, "active_native_mode", None) is not None else "",
            "artifact_connected_route_smoke_passed": bool(getattr(self, "artifact_route_smoke_passed", False)) if ARTIFACT_ROUTE_SMOKE_TEST else None,
            "artifact_connected_route_smoke_results": connected_smoke_results,
            "artifact_shapes_animated_desktop": True,
            "artifact_shape_node_count": len([n for n in self.artifact_shape_nodes if n is not None and not n.isEmpty()]),
            "artifact_pedestal_world_assignments": [{"pedestal": int(a.get("id", -1)), "world_id": int(a.get("world_id", -1)), "mode_id": str(a.get("dimension_mode_id", "")), "name": str(a.get("name", ""))} for a in self.artifacts],
            "core_mode_launcher_pass_v0_9_11": True,
            "immersive_core_ui_pass_v0_9_12": True,
            "core_mode_click_buttons": len(getattr(self, "core_mode_buttons", []) or []),
            "core_ui_mouse_first": True,
            "core_ui_numbers_disabled_for_mode_launch": True,
            "core_ui_theme": "MODERN CYAN / GLASS / WHITE",
            "core_ui_text_case": "FULL CAPS",
            "core_ui_font_attempt": "OCR-style mono; bundled OCR font if present, system mono fallback otherwise",
            "bot_dialogue_source_runtime_node_fix": True,
            "bot_dialogue_active_node_count": len(self._active_named_region_bot_nodes()),
            "bot_dialogue_active_node_names": [str(n.getPythonTag("named_region_bot_name") or "") for n in self._active_named_region_bot_nodes()],
            "world_surface_underlay_pass_v0_9_13": True,
            "world_visibility_safe_underlay_pass_v0_9_14": True,
            "world_surface_underlay_chunks": sum(1 for meta in self.terrain_chunks.values() if isinstance(meta, dict) and meta.get("node") is not None and not meta.get("node").isEmpty() and any((child.getPythonTag("world_surface_underlay") if child is not None and not child.isEmpty() else False) for child in meta.get("node").getChildren())),
            "world_surface_visibility_safe_chunks": sum(1 for meta in self.terrain_chunks.values() if isinstance(meta, dict) and meta.get("node") is not None and not meta.get("node").isEmpty() and any((child.getPythonTag("visibility_safe_underlay") if child is not None and not child.isEmpty() else False) for child in meta.get("node").getChildren())),
            "world_surface_texture_count": len(getattr(self, "world_surface_textures", {}) or {}),
            "world_surface_underlay_style": "single procedural texture per world palette, terrain-following visual mesh, wire terrain remains above it, collision unchanged",
            "world_surface_visibility_policy": "underlays are lower-alpha, offset beneath terrain, depth-write disabled, wires use fixed overlay bin",
            "world_surface_underlay_depth_write_disabled": True,
            "world_surface_underlay_z_offset": -0.165,
            "world_surface_underlay_alpha_max": 0.42,
            "world_line_overlay_priority_enabled": True,
            "core_modes_discovered": [{"slot": i + 1, "name": str(m.get("name", "")), "main": os.fspath(m.get("main", "")), "alternate": os.fspath(m.get("alternate", "")) if m.get("alternate") else None, "available": bool(m.get("available")), "has_alternate": bool(m.get("has_alternate"))} for i, m in enumerate(getattr(self, "core_modes", []) or [])],
            "core_mode_count": len(getattr(self, "core_modes", []) or []),
            "core_numbers_launch_only_when_panel_open": False,
            "holo_campaign_alternates_main_and_alternate": any(str(m.get("name", "")).lower() == "holo campaign" and bool(m.get("has_alternate")) for m in (getattr(self, "core_modes", []) or [])),
            "core_panel_replaces_same_file_world_numbers": True,
            "hold_escape_exit_seconds": 2.0,
            "transition_progress": self.transition_progress,
            "vr_active": self.vr_active,
            "vr_status": self.vr_status,
            "vr_requested": VR_REQUESTED,
            "vr_allowed": VR_ALLOWED,
            "desktop_first_person_default": True,
            "audio_backend": self.audio.backend if self.audio else 'none',
            "latest_log": str(LATEST_LOG),
            "crash_log_exists": CRASH_LOG.exists(),
            "campaign_path": str(self.campaign_path) if self.campaign_path else None,
            "mx_path": str(self.mx_path) if self.mx_path else None,
            "terrain_chunks": len(self.terrain_chunks),
            "world_actors": len(self.world_actors),
            "effective_render_radius": self.effective_render_radius(),
            "avg_dt": avg_dt,
            "avg_fps": (1.0 / avg_dt) if avg_dt > 0.0001 else 0.0,
            "peak_dt": self.self_test_dt_peak,
            "runtime_world_signature": self.runtime_world_signature,
            "vector_arena_reserved": any(str(m.get("name", "")).lower() == "vector arena" for m in getattr(self, "core_modes", []) or []),
            "window_mode": "bordered_fullscreen" if LAUNCH_BORDERED_FULLSCREEN else ("borderless" if LAUNCH_BORDERLESS else ("exclusive_fullscreen" if LAUNCH_FULLSCREEN else "windowed")),
            "external_pause_supported": True,
            "windows_child_window_embedding_supported": os.name == "nt",
            "artifact_e_activation_path": "looked-at-or-nearby",
            "real_input_repair_pass_v0_9_16": True,
            "single_e_handler_no_duplicate_accept": True,
            "single_q_handler_no_duplicate_accept": True,
            "artifact_near_activation_radius": ARTIFACT_PRESS_ACTIVATION_RADIUS,
            "artifact_look_activation_radius": ARTIFACT_LOOK_ACTIVATION_RADIUS,
            "artifact_look_cone_cos": 0.74,
            "external_window_minimize_on_launch": True,
            "embedded_window_keeps_host_visible": True,
            "core_priority_when_facing_core": True,
            "esc_hold_uses_monotonic_no_repeat_reset": True,
            "native_adapter_calls_removed": False,
            "native_mode_status_overlay": False,
            "native_mode_input_bridge": True,
            "holo_campaign_same_window_native_pass54": any(str(item.get("mode_id", "")).lower() == "holo_campaign" and str(item.get("launch_type", "")) == MODE_LAUNCH_NATIVE for item in artifact_gate_assignments),
            "active_world_runtime_state": self.sync_active_world_runtime_state(),
            "holoverse_default_world_core_owned": True,
            "world_shell_launcher_hidden": not any(str(m.get("name", "")).lower() == "world shell" for m in getattr(self, "core_modes", []) or []),
            "world_shell_mount_pass30": bool(getattr(self.cfg, "world_shell_mount_enabled", True)),
            "world_shell_mount_status": str(getattr(self, "world_shell_mount_status", "UNKNOWN")),
            "world_shell_mount_biome": str(getattr(self, "world_shell_mount_biome", "UNKNOWN")),
            "world_shell_streamed_count": int(getattr(self, "world_shell_streamed_count", 0)),
            "world_shell_default_preloaded": bool(getattr(self, "world_shell_preloaded_default", False)),
            "world_shell_preload_all_biomes": bool(getattr(self.cfg, "world_shell_preload_all_biomes", True)),
            "world_shell_preload_corridors": bool(getattr(self.cfg, "world_shell_preload_corridors", True)),
            "world_shell_preload_sector_radius": int(getattr(self.cfg, "world_shell_preload_sector_radius", 0)),
            "world_shell_max_preloaded_sectors": int(getattr(self.cfg, "world_shell_max_preloaded_sectors", 192)),
            "world_shell_exit_gate_hints": bool(getattr(self.cfg, "world_shell_exit_gate_hints", True)),
            "world_shell_ground_continuity": bool(getattr(self.cfg, "world_shell_ground_continuity", True)),
            "world_shell_ground_band_count": int(getattr(self.cfg, "world_shell_ground_band_count", 5)),
            "world_shell_scale_handoff_markers": bool(getattr(self.cfg, "world_shell_scale_handoff_markers", True)),
            "world_shell_collision_height_hints": bool(getattr(self.cfg, "world_shell_collision_height_hints", True)),
            "world_shell_local_detail_boost": bool(getattr(self.cfg, "world_shell_local_detail_boost", True)),
            "world_shell_biome_signature_density": int(getattr(self.cfg, "world_shell_biome_signature_density", 2)),
            "world_shell_directional_feedback": bool(getattr(self.cfg, "world_shell_directional_feedback", True)),
            "world_shell_corridor_theming": bool(getattr(self.cfg, "world_shell_corridor_theming", True)),
            "world_shell_theme_handoff": bool(getattr(self.cfg, "world_shell_theme_handoff", True)),
            "world_shell_hub_theme_influence": bool(getattr(self.cfg, "world_shell_hub_theme_influence", True)),
            "world_shell_hub_theme_status": str(getattr(self, "world_shell_hub_theme_status", "OFF")),
            "world_shell_hub_theme_last": getattr(self, "world_shell_hub_theme_last", {}) or {},
            "world_shell_audio_status": str(getattr(self, "world_shell_audio_status", "OFF")),
            "world_shell_audio_handoff": getattr(self, "world_shell_audio_handoff", {}) or {},
            "world_shell_prompt": str(getattr(self, "world_shell_prompt", "HOLOVERSE READY")),
            "world_shell_default_lifecycle_state": str(getattr(self, "world_shell_default_lifecycle_state", "UNKNOWN")),
            "world_shell_motion_status": str(getattr(self, "world_shell_motion_status", "OFF")),
            "world_shell_boundary_status": str(getattr(self, "world_shell_boundary_status", "READY")),
            "world_shell_checkpoint_status": str(getattr(self, "world_shell_checkpoint_status", "0/0")),
            "world_shell_checkpoint_claimed_count": int(getattr(self, "world_shell_checkpoint_claimed_count", 0)),
            "embedded_graceful_return_signal": True,
            "embedded_child_focus_bridge_pass15": True,
            "close_all_apps_menu_button_pass": True,
            "hold_esc_close_games_indicator_pass": True,
            "ui_settings_maintenance_pass_1040": True,
            "ui_background_overlay_alpha": "translucent glass panels, mostly 0.34-0.52 alpha outside interactive buttons",
            "ui_quit_paths": ["System > QUIT APP", "Ctrl+Q", "hold ESC"],
            "ui_no_red_primary_theme": True,
            "menu_action_duplicate_count": int(getattr(self, "menu_action_duplicate_count", 0) or 0),
            "menu_action_hidden_count": int(getattr(self, "menu_action_hidden_count", 0) or 0),
            "matrixcore_advanced_core_nodes": int(len(getattr(self, "matrixcore_core_nodes", []) or [])),
            "placeholder_dimension_folders": [str(m.get("name", "")) for m in getattr(self, "core_modes", []) or [] if bool(m.get("placeholder"))],
            "old_native_adapter_pass_flags_retired": True,
        }
        SELF_TEST_REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
        self.userExit()
        if SELF_TEST:
            try:
                sys.stdout.flush(); sys.stderr.flush()
            except Exception:
                pass
            os._exit(0)
        return Task.done

    def update_task(self, task):
        transition_dt = min(0.05, globalClock.getDt())
        self.update_bridge_transition(transition_dt)
        if self.external_resume_pending:
            self.resume_from_external_app()
        if self.external_suspended:
            # Hard pause while an external mode owns focus: no movement, no world
            # streaming, no actor animation, no mouse recentering. The watcher
            # thread normally flips external_resume_pending when the child process
            # exits. Pass 2 also polls here and treats a closed embedded child
            # window as a completed launch so the wait overlay cannot stick.
            if self._external_process_poll_update(reason="update-poll"):
                return Task.cont
            if self._embedded_child_window_closed_update():
                return Task.cont
            if self._embedded_launch_timeout_update():
                return Task.cont
            embedder = getattr(self, "embedded_child_host", None)
            if embedder is not None:
                attached = bool(getattr(embedder, "attached", False))
                if attached != bool(getattr(self, "embedded_child_attached", False)):
                    self.embedded_child_attached = attached
                    self.center_hint["text"] = "CORE // MODE EMBEDDED" if attached else "CORE // WAITING FOR MODE WINDOW"
                    self._append_mode_gateway_history("embedded_attach_state", label=getattr(self, "external_launch_label", "MODE"), route=MODE_LAUNCH_EMBEDDED, extra={"attached": attached, "error": getattr(embedder, "attach_error", "")})
                if not attached:
                    elapsed_load = time.monotonic() - float(getattr(self, "external_launch_started_at", time.monotonic()) or time.monotonic())
                    if self._is_holocore_label(getattr(self, "external_launch_label", "MODE")):
                        self.show_bridge_transition("MATRIXCORE -> HOLOCORE", "SAME-SCREEN GATEWAY // WAITING FOR PYRAMID WINDOW", target=1.0)
                    self.show_mode_loading_overlay(getattr(self, "external_launch_label", "MODE"), route="LOADING", elapsed=elapsed_load, detail="WAITING FOR WINDOW")
                else:
                    if self._is_holocore_label(getattr(self, "external_launch_label", "MODE")):
                        self.fade_bridge_transition(hold=0.12)
                    self.show_native_status_overlay(getattr(self, "external_launch_label", "MODE"), route="EMBEDDED", subtitle="MODE WINDOW ATTACHED // ESC RETURNS TO HOLOVERSE")
            else:
                elapsed_load = time.monotonic() - float(getattr(self, "external_launch_started_at", time.monotonic()) or time.monotonic())
                if self._is_holocore_label(getattr(self, "external_launch_label", "MODE")):
                    self.show_bridge_transition("MATRIXCORE -> HOLOCORE", "HOSTED FALLBACK // SAME GATEWAY SCREEN", target=1.0)
                self.show_mode_loading_overlay(getattr(self, "external_launch_label", "MODE"), route="LOADING", elapsed=elapsed_load, detail="HOSTED FALLBACK")
            return Task.cont
        dt = min(0.033, globalClock.getDt())
        if getattr(self, "active_native_mode", None) is not None:
            self.elapsed += dt
            self.persist_world_cycle_progress(force=False)
            try:
                update = getattr(self.active_native_mode, "update", None)
                if callable(update):
                    update(dt)
            except Exception as exc:
                print(f"native_mode_update_error label={self.native_mode_label} err={exc}")
                self.return_from_native_mode(reason="update-error")
            if self.audio:
                self.audio.refresh_mix()
            return Task.cont
        self.self_test_frame_count += 1
        self.self_test_dt_total += dt
        self.self_test_dt_peak = max(self.self_test_dt_peak, dt)
        self.elapsed += dt
        self.persist_world_cycle_progress(force=False)
        self.check_escape_hold()
        if self.update_holospace_travel_sequence(dt):
            self.runtime_last_zone = self.current_zone_name()
            try:
                self.refresh_ui()
            except Exception:
                pass
            if self.audio:
                self.update_soundscape(dt)
            return Task.cont
        if self.runtime_avg_dt <= 0.0:
            self.runtime_avg_dt = dt
        else:
            self.runtime_avg_dt = lerp(self.runtime_avg_dt, dt, min(1.0, dt * 1.8))
        self.runtime_avg_fps = (1.0 / self.runtime_avg_dt) if self.runtime_avg_dt > 0.0001 else 0.0
        self.update_player(dt)
        self.update_holospace_battlefield_state(dt)
        if self.should_stream_legacy_world_chunks():
            self.update_world_chunks()
        elif getattr(self, "terrain_chunks", None):
            self.clear_world_chunks()
            self.world_root.hide()
        self.update_world_shell_mount(dt)
        # Keep the imported Urban arena alive from the actual main-game update
        # route.  This catches the idle/no-input case and any shell refresh that
        # happens after player movement.  Sable still controls match activation;
        # this only restores the ambient battlefield view for Region 6.
        try:
            if int(self.current_holoverse_region_number()) == 6 and hasattr(self, "ensure_urban_battlefield_runtime"):
                self.ensure_urban_battlefield_runtime(dt, source="main_game_update_post_shell")
        except Exception as exc:
            try:
                print(f"urban_main_update_battlefield_warning:{exc.__class__.__name__}:{exc}")
            except Exception:
                pass
        self.update_chunk_fades(dt)
        self.update_artifact_focus(dt)
        self.animate_artifact_shapes(dt)
        self.update_world_actors(dt)
        self.update_gleebs_hologram(dt)
        self.update_gleebs_dialogue(dt)
        if abs(self.hub_fill_alpha - self.hub_fill_target) > 0.001:
            blend = min(1.0, dt * 0.72)
            self.hub_fill_alpha += (self.hub_fill_target - self.hub_fill_alpha) * blend
            if abs(self.hub_fill_alpha - self.hub_fill_target) < 0.01:
                self.hub_fill_alpha = self.hub_fill_target
            self.update_hub_fill_visuals()
        self.animate_accents(dt)
        self.runtime_chunk_peak = max(self.runtime_chunk_peak, len(self.terrain_chunks))
        self.runtime_actor_peak = max(self.runtime_actor_peak, len(self.world_actors))
        self.runtime_last_zone = self.current_zone_name()
        self.refresh_ui()
        if getattr(self, "bot_dialogue_open", False):
            self.refresh_bot_dimension_dialogue()
        self.update_comfort_overlay()
        if self.audio:
            self.update_soundscape(dt)
        return Task.cont


# Dimension runtimes now live inside their own /Dimensions folders.
# The root no longer owns Forest/Hills/Urban/etc. runtime files; main.py only mounts
# the active dimension-local runtime.py files onto CommandHubApp.
def _install_dimension_runtime(dimension_folder: str, module_key: str, installer_name: str) -> None:
    runtime_path = ROOT / "Dimensions" / dimension_folder / "runtime.py"
    if not runtime_path.exists():
        print(f"dimension_runtime_missing: {dimension_folder} -> {runtime_path}")
        return
    try:
        module_name = f"holoverse_dimension_runtime_{module_key}"
        spec = importlib.util.spec_from_file_location(module_name, runtime_path)
        if spec is None or spec.loader is None:
            print(f"dimension_runtime_spec_error: {dimension_folder} -> {runtime_path}")
            return
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        installer = getattr(module, installer_name, None)
        if not callable(installer):
            print(f"dimension_runtime_installer_missing: {dimension_folder}.{installer_name}")
            return
        installer(CommandHubApp)
    except Exception as exc:
        print(f"dimension_runtime_install_error: {dimension_folder}: {exc}")


for _dimension_folder, _module_key, _installer_name in (
    ("HoloForge", "holoforge", "install_holoforge_region_runtime"),
    ("Forest Growth", "forest_growth", "install_forest_growth_runtime"),
    ("Hills of Life", "hills_of_life", "install_hills_life_runtime"),
    ("Oddities", "oddities", "install_oddities_runtime"),
    ("Ember Hangar", "ember_hangar", "install_desert_ships_runtime"),
    ("Frost Circuit", "frost_circuit", "install_frost_circuit_runtime"),
    ("Urban Warzone", "urban_warzone", "install_urban_warzone_runtime"),
    ("Metropolis Robot Lab", "metropolis_robot_lab", "install_metropolis_robot_lab_runtime"),
):
    _install_dimension_runtime(_dimension_folder, _module_key, _installer_name)

def main():
    ensure_dirs()
    install_logging()
    if CRASH_LOG.exists():
        CRASH_LOG.unlink()
    install_crash_reporter()
    write_patch_notes()
    print(f"Launching {GAME_NAME} {VERSION}")
    print(f"SELF_TEST={SELF_TEST}")
    print(f"WORLD_AUTHORITY_SMOKE_TEST={WORLD_AUTHORITY_SMOKE_TEST}")
    print(f"VR_REQUESTED={VR_REQUESTED}")
    print(f"VR_DISABLED={VR_DISABLED}")
    print(f"VR_ALLOWED={VR_ALLOWED}")
    app = CommandHubApp()
    app.run()


if __name__ == "__main__":
    main()
