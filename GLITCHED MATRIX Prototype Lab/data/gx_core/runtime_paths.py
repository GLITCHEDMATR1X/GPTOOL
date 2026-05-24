from __future__ import annotations

import ast
import importlib.util
import json
import math
import os
import random
import subprocess
import sys
import time
from pathlib import Path
import tkinter as tk

try:
    from PIL import Image, ImageTk
except Exception:
    Image = None
    ImageTk = None

try:
    import pygame
except Exception:
    pygame = None

try:
    from panda3d.core import loadPrcFileData, TextNode, Filename
    from direct.showbase.ShowBase import ShowBase
    from direct.gui.OnscreenImage import OnscreenImage
    from direct.gui.OnscreenText import OnscreenText
except Exception:
    loadPrcFileData = None
    TextNode = None
    Filename = None
    ShowBase = None
    OnscreenImage = None
    OnscreenText = None

APP_TITLE = "GLITCHED MATRIX Prototype Lab"
APP_FOLDER_NAME = "GLITCHED MATRIX Prototype Lab"
OS_VERSION = "v1.1.8"

def _looks_like_app_root(path: Path) -> bool:
    try:
        return (path / "data" / "gx_app_main.py").is_file() and (path / "data" / "gx_core" / "runtime_paths.py").is_file()
    except Exception:
        return False

def _discover_app_root(anchor: Path) -> Path | None:
    candidates = []
    try:
        anchor = anchor.resolve()
    except Exception:
        pass
    candidates.extend([
        anchor,
        anchor / APP_FOLDER_NAME,
        anchor.parent / APP_FOLDER_NAME,
        Path.cwd(),
        Path.cwd() / APP_FOLDER_NAME,
    ])
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
    return None


def _resource_base_dir() -> Path:
    try:
        if getattr(sys, "frozen", False):
            meipass = getattr(sys, "_MEIPASS", "")
            if meipass:
                meipass_path = Path(meipass)
                discovered = _discover_app_root(meipass_path)
                return discovered or meipass_path
            exe_parent = Path(sys.executable).resolve().parent
            discovered = _discover_app_root(exe_parent)
            return discovered or exe_parent
    except Exception:
        pass
    try:
        module_root = Path(__file__).resolve().parents[2]
        discovered = _discover_app_root(module_root)
        return discovered or module_root
    except Exception:
        discovered = _discover_app_root(Path.cwd())
        return discovered or Path.cwd()

def _app_base_dir() -> Path:
    try:
        if getattr(sys, "frozen", False):
            exe_parent = Path(sys.executable).resolve().parent
            discovered = _discover_app_root(exe_parent)
            if discovered is not None:
                return discovered
            resource_root = _resource_base_dir()
            if _looks_like_app_root(resource_root):
                return resource_root
            # Last-resort containment: do not spray data/games folders into a
            # drive root when a one-file build is launched from there.
            if exe_parent.parent == exe_parent or str(exe_parent).endswith(":\\"):
                return exe_parent / APP_FOLDER_NAME
            return exe_parent
    except Exception:
        pass
    return _resource_base_dir()

RESOURCE_BASE_DIR = _resource_base_dir()
APP_BASE_DIR = _app_base_dir()
DEFAULT_BUNDLED_WALLPAPER = RESOURCE_BASE_DIR / "assets" / "wallpaper" / "wallpaper.png"
DATA_ROOT_DIR = APP_BASE_DIR / "data"
PROTOTYPE_LAB_DIR = DATA_ROOT_DIR / "Prototype Lab"
GX_MACHINE_DIR = DATA_ROOT_DIR / "GX-Machine"
TOOLS_SHELF_DIR = GX_MACHINE_DIR
DEFAULT_GAMES_ROOT = APP_BASE_DIR / "games" / "Arcade Evolution"
TOOLS_DIR = PROTOTYPE_LAB_DIR
TEST_LAB_DIR = GX_MACHINE_DIR
TOOL_TEST_LAB_DIR = PROTOTYPE_LAB_DIR
LEGACY_TOOLS_DIR = APP_BASE_DIR / "games" / "the architect room"
CENTRAL_HUB_MAIN = DATA_ROOT_DIR / "CentralHub.py"
CENTRAL_HUB_DIR = DEFAULT_GAMES_ROOT / "Central Hub Project"
CENTRAL_HUB_TEST_LAB_DIR = CENTRAL_HUB_DIR / "Test Hub" / "Test Lab"
DATA_CENTRAL_HUB_TEST_LAB_DIR = CENTRAL_HUB_TEST_LAB_DIR
DATA_CENTRAL_HUB_TOOL_TEST_LAB_DIR = TOOL_TEST_LAB_DIR
HOLOVERSE_DIR = APP_BASE_DIR / "data" / "HoloVerse"
LEGACY_CHAT_DIR = APP_BASE_DIR / "data" / "chatspace"
CHAT_DIR = DATA_ROOT_DIR
LEGACY_MINIGAMES_DIR = APP_BASE_DIR / "data" / "minigames"
LEGACY_TEST_LAB_DIR = APP_BASE_DIR / "games" / "Test Lab"
LEGACY_TOOL_TEST_LAB_DIR = APP_BASE_DIR / "games" / "Tool Test Lab"
GENERATED_EVENTS_DIR = PROTOTYPE_LAB_DIR
SETTINGS_FILE = APP_BASE_DIR / "desktop_settings.json"
FOLDER_LIST_FILE = PROTOTYPE_LAB_DIR / "folder_list.txt"
SCREENSHOTS_DIR = DATA_ROOT_DIR / "assets" / "screenshots"
BUNDLED_RULES_DIR = DATA_ROOT_DIR / "rules"
UNIFIED_REQUIREMENTS = [
    "Pillow>=10.0.0",
    "pygame>=2.5.0",
    "tkinterdnd2>=0.3.0",
    "panda3d==1.10.15; python_version < \"3.13\"",
    "panda3d==1.10.16; python_version >= \"3.13\"",
    "numpy>=1.26.0",
    "mss>=9.0.0",
    "panda3d-gltf==1.3.0",
    "panda3d-simplepbr==0.13.1",
]
KNOWN_EXTERNAL_IMPORT_ROOTS = {
    "numpy", "simplepbr", "gltf",
    "panda3d", "direct", "pygame", "PIL",
    "cv2", "trimesh", "tkinterdnd2", "mss", "PySide6",
}
OPTIONAL_IMPORT_ROOTS = {"p3dopenxr", "holoverse_mode_runtime"}
GENERATION_RUNTIME_NAME = "GX-Machine MXOS"
GENERATION_ALLOWED_SOURCE_POOLS = {"arcade_evolution", "prototype_lab"}
GENERATION_BLOCKED_SOURCE_POOLS = {"tool_test_lab"}
MATRIXCORE_HOST_ENV_FLAG = "GLITCHED_MATRIX_EMBEDDED_HOST"
MATRIXCORE_WINDOW_MODE_ENV_FLAG = "GLITCHED_MATRIX_WINDOW_MODE"
MATRIXCORE_PANEL_ENV_FLAG = "GLITCHED_MATRIX_PANEL_KEY"

GENERATION_STANDARDS_FILES = [
    "Mechanic_Standards_Combined_Complete.md",
    "00_Master_Index.md",
    "01_Player_Locomotion.md",
    "02_Camera_and_Framing.md",
    "03_Animation_State_Machine.md",
    "04_Playtest_World_and_Grid.md",
    "05_Editor_Mode_and_Object_Placement.md",
    "06_Model_Import_Export_and_Validation.md",
    "07_Texture_Materials_and_Live_Reload.md",
    "08_UI_Settings_and_Responsiveness.md",
    "09_QA_Performance_and_Shipping.md",
    "10_Third_Person_Outdoor_World_Standards.md",
    "11_First_Person_Interior_Combat_Standards.md",
    "12_Endless_Outdoor_World_Generation.md",
    "IMPORTANT-INSTRUCTIONS.txt",
]
MINIGAME_SCAN_IGNORE = {"__pycache__", ".git", ".github", ".vs", ".idea", "build", "dist"}
MUSIC_EXTENSIONS = {".mp3", ".ogg", ".wav", ".flac", ".mid", ".midi"}
THUMB_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}
THUMB_SIZE_MAP = {"small": 0.78, "medium": 0.9, "large": 1.0}
RESOLUTIONS = ["1280x720", "1366x768", "1600x900", "1920x1080"]
DESKTOP_LAYOUT_VERSION = 3

def external_game_source_roots(include_generated: bool = True, include_legacy: bool = True) -> list[Path]:
    # Main-app scan roots should be read-only discovery lanes.  Do not return
    # legacy game folders that do not already exist; older UI code may navigate
    # to returned roots and create them.  The app-owned data/Prototype Lab lane
    # remains authoritative for this build.
    roots: list[Path] = [TEST_LAB_DIR, TOOL_TEST_LAB_DIR, TOOLS_DIR]
    if LEGACY_TOOLS_DIR.exists():
        roots.append(LEGACY_TOOLS_DIR)
    if include_generated and GENERATED_EVENTS_DIR not in roots:
        roots.append(GENERATED_EVENTS_DIR)
    if include_legacy:
        for legacy_root in (CENTRAL_HUB_TEST_LAB_DIR, LEGACY_TEST_LAB_DIR, LEGACY_TOOL_TEST_LAB_DIR):
            if legacy_root.exists():
                roots.append(legacy_root)
    ordered: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        key = str(root)
        if key in seen:
            continue
        seen.add(key)
        ordered.append(root)
    return ordered

def configure_runtime_base(app_base_dir: Path | str | None = None, resource_base_dir: Path | str | None = None) -> None:
    global RESOURCE_BASE_DIR, APP_BASE_DIR, DEFAULT_BUNDLED_WALLPAPER, DATA_ROOT_DIR, CENTRAL_HUB_MAIN
    global DATA_CENTRAL_HUB_TEST_LAB_DIR, DATA_CENTRAL_HUB_TOOL_TEST_LAB_DIR
    global PROTOTYPE_LAB_DIR, GX_MACHINE_DIR, TOOLS_SHELF_DIR, DEFAULT_GAMES_ROOT, TOOLS_DIR, TEST_LAB_DIR, TOOL_TEST_LAB_DIR, LEGACY_TOOLS_DIR
    global CENTRAL_HUB_DIR, CENTRAL_HUB_TEST_LAB_DIR, HOLOVERSE_DIR, LEGACY_CHAT_DIR, CHAT_DIR
    global LEGACY_MINIGAMES_DIR, LEGACY_TEST_LAB_DIR, LEGACY_TOOL_TEST_LAB_DIR, GENERATED_EVENTS_DIR, SETTINGS_FILE, FOLDER_LIST_FILE, SCREENSHOTS_DIR, BUNDLED_RULES_DIR
    if resource_base_dir:
        RESOURCE_BASE_DIR = Path(resource_base_dir).resolve()
    if app_base_dir:
        APP_BASE_DIR = Path(app_base_dir).resolve()
    DEFAULT_BUNDLED_WALLPAPER = RESOURCE_BASE_DIR / "assets" / "wallpaper" / "wallpaper.png"
    DATA_ROOT_DIR = APP_BASE_DIR / "data"
    PROTOTYPE_LAB_DIR = DATA_ROOT_DIR / "Prototype Lab"
    GX_MACHINE_DIR = DATA_ROOT_DIR / "GX-Machine"
    TOOLS_SHELF_DIR = GX_MACHINE_DIR
    CENTRAL_HUB_MAIN = DATA_ROOT_DIR / "CentralHub.py"
    SETTINGS_FILE = APP_BASE_DIR / "desktop_settings.json"
    FOLDER_LIST_FILE = PROTOTYPE_LAB_DIR / "folder_list.txt"
    DEFAULT_GAMES_ROOT = APP_BASE_DIR / "games" / "Arcade Evolution"
    TOOLS_DIR = PROTOTYPE_LAB_DIR
    TEST_LAB_DIR = GX_MACHINE_DIR
    TOOL_TEST_LAB_DIR = PROTOTYPE_LAB_DIR
    LEGACY_TOOLS_DIR = APP_BASE_DIR / "games" / "the architect room"
    CENTRAL_HUB_DIR = DEFAULT_GAMES_ROOT / "Central Hub Project"
    CENTRAL_HUB_TEST_LAB_DIR = CENTRAL_HUB_DIR / "Test Hub" / "Test Lab"
    DATA_CENTRAL_HUB_TEST_LAB_DIR = CENTRAL_HUB_TEST_LAB_DIR
    DATA_CENTRAL_HUB_TOOL_TEST_LAB_DIR = TOOL_TEST_LAB_DIR
    HOLOVERSE_DIR = APP_BASE_DIR / "data" / "HoloVerse"
    LEGACY_CHAT_DIR = APP_BASE_DIR / "data" / "chatspace"
    CHAT_DIR = DATA_ROOT_DIR
    LEGACY_MINIGAMES_DIR = APP_BASE_DIR / "data" / "minigames"
    LEGACY_TEST_LAB_DIR = APP_BASE_DIR / "games" / "Test Lab"
    LEGACY_TOOL_TEST_LAB_DIR = APP_BASE_DIR / "games" / "Tool Test Lab"
    GENERATED_EVENTS_DIR = PROTOTYPE_LAB_DIR
    SCREENSHOTS_DIR = DATA_ROOT_DIR / "assets" / "screenshots"
    BUNDLED_RULES_DIR = DATA_ROOT_DIR / "rules"

def generation_tool_candidates() -> list[tuple[str, Path]]:
    """Return only the MXOS lane in this cleaned build.

    Bridge/router/salvage generator tools were isolated out of the main app.
    """
    candidate = GX_MACHINE_DIR / "mxos.py"
    return [("GX-Machine MXOS", candidate)] if candidate.exists() else []

def best_generation_tool_name() -> str:
    tools = generation_tool_candidates()
    return tools[0][0] if tools else GENERATION_RUNTIME_NAME

def generation_standard_search_dirs(app_base_dir: Path | None = None, resource_base_dir: Path | None = None) -> list[Path]:
    app_root = Path(app_base_dir).resolve() if app_base_dir else APP_BASE_DIR
    resource_root = Path(resource_base_dir).resolve() if resource_base_dir else RESOURCE_BASE_DIR
    candidates = [
        app_root,
        resource_root,
        app_root / "Rules",
        resource_root / "Rules",
        app_root / "data" / "rules",
        resource_root / "data" / "rules",
    ]
    ordered: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        ordered.append(candidate)
    return ordered


def resolve_generation_standard_files(file_names: list[str] | tuple[str, ...] | None = None, *, app_base_dir: Path | None = None, resource_base_dir: Path | None = None) -> list[Path]:
    names = list(file_names or GENERATION_STANDARDS_FILES)
    resolved: list[Path] = []
    seen: set[str] = set()
    for base_dir in generation_standard_search_dirs(app_base_dir=app_base_dir, resource_base_dir=resource_base_dir):
        for name in names:
            fp = base_dir / name
            key = str(fp)
            if key in seen:
                continue
            seen.add(key)
            if fp.exists() and fp.is_file():
                resolved.append(fp)
    return resolved


def write_unified_dependency_bootstrap(requirements_path: Path | str, installer_path: Path | str) -> None:
    req = Path(requirements_path)
    bat = Path(installer_path)
    req.write_text("\n".join(UNIFIED_REQUIREMENTS) + "\n", encoding="utf-8")
    bat.write_text(
        "@echo off\n"
        "setlocal\n"
        "echo Installing GLITCHED MATRIX Prototype Lab unified dependencies...\n"
        "python -m pip install --upgrade pip\n"
        "python -m pip install -r requirements.txt\n"
        "echo Done. Press any key to exit.\n"
        "pause >nul\n",
        encoding="utf-8",
    )


def entry_missing_internal_imports(entry_abs: Path | str) -> list[str]:
    entry = Path(entry_abs)
    try:
        source = entry.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []
    try:
        tree = ast.parse(source)
    except Exception:
        return []
    search_roots = [entry.parent, APP_BASE_DIR, RESOURCE_BASE_DIR, DATA_ROOT_DIR]
    missing: list[str] = []
    seen: set[str] = set()
    for node in ast.walk(tree):
        module_name = None
        if isinstance(node, ast.Import):
            for alias in node.names:
                module_name = (alias.name or "").split(".")[0]
                if not module_name:
                    continue
                if module_name in seen or module_name in OPTIONAL_IMPORT_ROOTS or module_name in KNOWN_EXTERNAL_IMPORT_ROOTS or module_name in sys.stdlib_module_names:
                    continue
                seen.add(module_name)
                if importlib.util.find_spec(module_name) is not None:
                    continue
                found_local = False
                for base in search_roots:
                    if (base / f"{module_name}.py").exists() or (base / module_name / "__init__.py").exists() or (base / module_name).exists():
                        found_local = True
                        break
                if not found_local:
                    missing.append(module_name)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            module_name = node.module.split(".")[0]
            if not module_name:
                continue
            if module_name in seen or module_name in OPTIONAL_IMPORT_ROOTS or module_name in KNOWN_EXTERNAL_IMPORT_ROOTS or module_name in sys.stdlib_module_names:
                continue
            seen.add(module_name)
            if importlib.util.find_spec(module_name) is not None:
                continue
            found_local = False
            for base in search_roots:
                if (base / f"{module_name}.py").exists() or (base / module_name / "__init__.py").exists() or (base / module_name).exists():
                    found_local = True
                    break
            if not found_local:
                missing.append(module_name)
    return missing


def required_modules_for_entry(entry_abs: Path | str) -> tuple[str, ...]:
    entry = "/" + str(Path(entry_abs)).lower().replace('\\', '/').lstrip('/')
    if entry.endswith('/data/centralhub.py'):
        return ('pygame',)
    if entry.endswith('/data/holoverse/main.py'):
        # HoloVerse only hard-requires Panda3D. pygame is an optional audio
        # backend inside HoloVerse and falls back safely when unavailable;
        # requiring it here can block launch before the real crash reporter
        # gets a useful child-process trace.
        return ('panda3d',)
    if '/data/gx-machine/' in entry or '/data/tools/' in entry or '/data/matrix_core_tools/' in entry:
        if '/matrixtools/' in entry or entry.endswith('/matrixtools/main.py'):
            return ('PySide6', 'numpy', 'pygame', 'mss')
        if '/2d prototype editor/' in entry:
            return ('PySide6', 'numpy', 'pygame', 'panda3d', 'cv2')
        if '/3d prototype editor/' in entry:
            return ('panda3d', 'trimesh', 'numpy', 'cv2')
    if '/liquid mercury 4d' in entry:
        return ('panda3d', 'numpy', 'cv2')
    return tuple()

def _windows_hidden_startupinfo():
    if os.name != "nt" or not hasattr(subprocess, "STARTUPINFO"):
        return None
    try:
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow = 0
        return startup
    except Exception:
        return None

def _hidden_creationflags() -> int:
    if os.name != "nt":
        return 0
    flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    if hasattr(subprocess, "CREATE_NO_WINDOW"):
        flags |= subprocess.CREATE_NO_WINDOW
    return flags

def _hide_launcher_console_window() -> None:
    if os.name != "nt":
        return
    try:
        import ctypes
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 0)
    except Exception:
        pass

def _stop_all_pygame_audio() -> None:
    if pygame is None:
        return
    try:
        if pygame.mixer.get_init():
            try:
                pygame.mixer.music.stop()
            except Exception:
                pass
            try:
                pygame.mixer.stop()
            except Exception:
                pass
    except Exception:
        pass

def _runtime_wrapper_template(runtime_module_path: Path) -> str:
    runtime = str(runtime_module_path.resolve()).replace('\\', '\\\\')
    lines = [
        '#!/usr/bin/env python3',
        'from pathlib import Path',
        'import importlib.util',
        'import sys',
        '',
        'HERE = Path(__file__).resolve().parent',
        f'RUNTIME = Path(r"{runtime}")',
        "SPEC_PATH = HERE / 'generated_spec.json'",
        '',
        'spec = importlib.util.spec_from_file_location("matrixcore_runtime_embed", RUNTIME)',
        'module = importlib.util.module_from_spec(spec)',
        'sys.modules["matrixcore_runtime_embed"] = module',
        'spec.loader.exec_module(module)',
        'module.configure_runtime_base(HERE.parents[2], resource_base_dir=HERE.parents[2])',
        'opts = module.gx_runtime.parse_generated_runtime_cli(sys.argv[1:])',
        'module.gx_runtime.run_generated_spec_window(SPEC_PATH, smoketest_seconds=float(opts.get("smoketest_seconds", 0.0) or 0.0))',
    ]
    return "\n".join(lines) + "\n"

def _find_brand_logo_path() -> Path | None:
    candidates = [
        APP_BASE_DIR / "launcher_logo.png",
        RESOURCE_BASE_DIR / "launcher_logo.png",
        APP_BASE_DIR / "assets" / "launcher_logo.png",
        RESOURCE_BASE_DIR / "assets" / "launcher_logo.png",
        APP_BASE_DIR / "assets" / "icons" / "GXPrototypeLab_window.png",
        RESOURCE_BASE_DIR / "assets" / "icons" / "GXPrototypeLab_window.png",
        APP_BASE_DIR / "assets" / "icons" / "GXPrototypeLab.png",
        RESOURCE_BASE_DIR / "assets" / "icons" / "GXPrototypeLab.png",
    ]
    seen: set[str] = set()
    for candidate in candidates:
        try:
            resolved = candidate.resolve() if candidate.exists() else candidate
            key = str(resolved)
            if key in seen:
                continue
            seen.add(key)
            if candidate.exists():
                return candidate
        except Exception:
            continue
    fallback_names = {"launcher_logo.png", "gxprototypelab_window.png", "gxprototypelab.png"}
    for base in (APP_BASE_DIR, RESOURCE_BASE_DIR):
        try:
            for probe in base.rglob('*'):
                if not probe.is_file():
                    continue
                if probe.name.lower() in fallback_names:
                    return probe
        except Exception:
            continue
    return None

def startup_logo_candidates() -> list[Path]:
    found: list[Path] = []
    for cand in [
        APP_BASE_DIR / "launcher_logo.png",
        RESOURCE_BASE_DIR / "launcher_logo.png",
        APP_BASE_DIR / "assets" / "launcher_logo.png",
        RESOURCE_BASE_DIR / "assets" / "launcher_logo.png",
        APP_BASE_DIR / "data" / "assets" / "launcher_logo.png",
        RESOURCE_BASE_DIR / "data" / "assets" / "launcher_logo.png",
    ]:
        try:
            if cand.exists() and cand.is_file() and cand not in found:
                found.append(cand)
        except Exception:
            continue
    return found


def startup_audio_candidates() -> list[Path]:
    found: list[Path] = []
    for cand in [
        APP_BASE_DIR / "data" / "assets" / "sfx" / "start.mp3",
        RESOURCE_BASE_DIR / "data" / "assets" / "sfx" / "start.mp3",
        APP_BASE_DIR / "assets" / "sfx" / "start.mp3",
        RESOURCE_BASE_DIR / "assets" / "sfx" / "start.mp3",
        APP_BASE_DIR / "data" / "assets" / "sfx" / "start.wav",
        RESOURCE_BASE_DIR / "data" / "assets" / "sfx" / "start.wav",
        APP_BASE_DIR / "assets" / "sfx" / "start.wav",
        RESOURCE_BASE_DIR / "assets" / "sfx" / "start.wav",
        APP_BASE_DIR / "data" / "assets" / "sfx" / "startup.mp3",
        RESOURCE_BASE_DIR / "data" / "assets" / "sfx" / "startup.mp3",
        APP_BASE_DIR / "assets" / "sfx" / "startup.mp3",
        RESOURCE_BASE_DIR / "assets" / "sfx" / "startup.mp3",
    ]:
        try:
            if cand.exists() and cand.is_file() and cand not in found:
                found.append(cand)
        except Exception:
            continue
    return found


def play_startup_audio_once(volume: float = 0.72) -> tuple[bool, bool]:
    if pygame is None:
        return (False, False)
    for audio_path in startup_audio_candidates():
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            try:
                pygame.mixer.music.stop()
            except Exception:
                pass
            pygame.mixer.music.load(str(audio_path))
            pygame.mixer.music.set_volume(max(0.0, min(1.0, float(volume))))
            pygame.mixer.music.play(loops=0)
            return (True, True)
        except Exception:
            continue
    return (False, False)


def stop_startup_audio(use_music: bool = True) -> None:
    if pygame is None:
        return
    try:
        if use_music and pygame.mixer.get_init():
            pygame.mixer.music.stop()
    except Exception:
        pass


def _fit_image_cover(img, width: int, height: int):
    if Image is None:
        return None
    src_w, src_h = img.size
    if src_w <= 0 or src_h <= 0 or width <= 0 or height <= 0:
        return img
    scale = max(width / float(src_w), height / float(src_h))
    new_w = max(1, int(round(src_w * scale)))
    new_h = max(1, int(round(src_h * scale)))
    resized = img.resize((new_w, new_h), Image.LANCZOS)
    left = max(0, (new_w - width) // 2)
    top = max(0, (new_h - height) // 2)
    return resized.crop((left, top, left + width, top + height))


def _alpha_frame(base_rgba, alpha: float):
    if Image is None or base_rgba is None:
        return None
    a = max(0.0, min(1.0, float(alpha)))
    if a >= 0.999:
        return base_rgba.copy()
    frame = base_rgba.copy()
    alpha_band = frame.getchannel("A").point(lambda px: int(px * a))
    frame.putalpha(alpha_band)
    return frame


def create_startup_overlay(root: tk.Misc, status_text: str, *, log_callback=None) -> tk.Toplevel | None:
    """Disabled for the cleaned MXOS-only build: launch directly to the app UI."""
    del root, status_text, log_callback
    return None

def begin_startup_handoff(root: tk.Misc, overlay: tk.Toplevel | None, *, audio_started: bool = False, used_music: bool = True, hold_ms: int = 900, fade_ms: int = 180, intro_fade_ms: int = 120) -> None:
    """Reveal the root immediately; destroy any stale overlay if one exists."""
    del audio_started, used_music, hold_ms, fade_ms, intro_fade_ms
    try:
        setattr(root, "_startup_handoff_pending", False)
    except Exception:
        pass
    try:
        if overlay is not None and getattr(overlay, "winfo_exists", lambda: False)():
            overlay.destroy()
    except Exception:
        pass
    try:
        root.attributes("-alpha", 1.0)
    except Exception:
        pass
    try:
        root.deiconify()
        root.lift()
        root.focus_force()
        root.update_idletasks()
    except Exception:
        pass

def _primary_monitor_size() -> tuple[int, int]:
    if os.name == "nt":
        try:
            import ctypes
            user32 = ctypes.windll.user32
            user32.SetProcessDPIAware()
            sw = int(user32.GetSystemMetrics(0) or 1920)
            sh = int(user32.GetSystemMetrics(1) or 1080)
            return max(1280, sw), max(720, sh)
        except Exception:
            pass
    try:
        probe = tk.Tk()
        probe.withdraw()
        sw = int(probe.winfo_screenwidth() or 1920)
        sh = int(probe.winfo_screenheight() or 1080)
        probe.destroy()
        return max(1280, sw), max(720, sh)
    except Exception:
        return 1920, 1080

def _primary_monitor_workarea() -> tuple[int, int, int, int]:
    if os.name == "nt":
        try:
            import ctypes
            user32 = ctypes.windll.user32
            user32.SetProcessDPIAware()
            class RECT(ctypes.Structure):
                _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long), ("right", ctypes.c_long), ("bottom", ctypes.c_long)]
            rect = RECT()
            SPI_GETWORKAREA = 0x0030
            if user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(rect), 0):
                x = int(rect.left)
                y = int(rect.top)
                w = max(960, int(rect.right - rect.left))
                h = max(540, int(rect.bottom - rect.top))
                return x, y, w, h
        except Exception:
            pass
    sw, sh = _primary_monitor_size()
    return 0, 0, sw, sh

def _launch_surface_for_monitor(sw: int, sh: int) -> tuple[int, int]:
    sw = max(1280, int(sw or 1920))
    sh = max(720, int(sh or 1080))
    target_w = min(1920, sw)
    target_h = int(round(target_w * 9 / 16))
    if target_h > sh:
        target_h = min(sh, 1080)
        target_w = int(round(target_h * 16 / 9))
    target_w = max(960, min(target_w, sw))
    target_h = max(540, min(target_h, sh))
    return target_w, target_h

def _apply_detected_window_mode(root: tk.Misc, *, fullscreen: bool = False, fullscreen_windowed: bool = False) -> tuple[int, int, int, int]:
    wa_x, wa_y, wa_w, wa_h = _primary_monitor_workarea()
    sw, sh = _primary_monitor_size()
    target_w, target_h = _launch_surface_for_monitor(wa_w, wa_h)
    try:
        root.minsize(960, 540)
    except Exception:
        pass
    try:
        root.attributes('-fullscreen', False)
    except Exception:
        pass
    try:
        root.overrideredirect(False)
    except Exception:
        pass
    if fullscreen_windowed:
        try:
            root.geometry(f"{wa_w}x{wa_h}+{wa_x}+{wa_y}")
        except Exception:
            pass
        try:
            root.overrideredirect(True)
        except Exception:
            pass
        try:
            root.lift()
        except Exception:
            pass
        return wa_w, wa_h, wa_w, wa_h
    if fullscreen:
        try:
            root.geometry(f"{sw}x{sh}+0+0")
        except Exception:
            pass
        try:
            root.state('zoomed')
        except Exception:
            pass
        try:
            root.attributes('-fullscreen', True)
        except Exception:
            try:
                root.geometry(f"{sw}x{sh}+0+0")
            except Exception:
                pass
        return sw, sh, sw, sh
    try:
        if os.name == "nt":
            root.state('zoomed')
            return wa_w, wa_h, wa_w, wa_h
    except Exception:
        pass
    x = wa_x + max(0, (wa_w - target_w) // 2)
    y = wa_y + max(0, (wa_h - target_h) // 2)
    try:
        root.geometry(f"{target_w}x{target_h}+{x}+{y}")
    except Exception:
        pass
    return wa_w, wa_h, target_w, target_h

def run_panda3d_startup_splash(status_text: str, *, min_hold: float = 0.9, fade_duration: float = 0.18, fullscreen: bool = False, fullscreen_windowed: bool = False) -> bool:
    logo_path = _find_brand_logo_path()
    if ShowBase is None or loadPrcFileData is None or TextNode is None or Filename is None or logo_path is None or not logo_path.exists():
        return False
    sw, sh = _primary_monitor_size()
    target_w, target_h = _launch_surface_for_monitor(sw, sh)
    use_display_size = fullscreen or fullscreen_windowed
    win_w, win_h = (sw, sh) if use_display_size else (target_w, target_h)
    try:
        loadPrcFileData('', 'window-title GLITCHED MATRIX Prototype Lab Startup')
        loadPrcFileData('', f'win-size {win_w} {win_h}')
        loadPrcFileData('', f'fullscreen {1 if fullscreen else 0}')
        loadPrcFileData('', f'undecorated {1 if (fullscreen or fullscreen_windowed) else 0}')
        loadPrcFileData('', 'win-origin 0 0')
        loadPrcFileData('', 'show-frame-rate-meter 0')
        loadPrcFileData('', 'sync-video 0')
        loadPrcFileData('', 'audio-library-name null')
        loadPrcFileData('', 'textures-power-2 none')
    except Exception:
        return False

    class _StartupSplash(ShowBase):
        def __init__(self):
            super().__init__(windowType='onscreen')
            self.disableMouse()
            self.setBackgroundColor(0, 0, 0, 1)
            self._started_at = time.time()
            aspect = float(win_w) / float(max(1, win_h))
            logo_scale_x = min(1.45, aspect * 0.72)
            logo_scale_z = min(0.9, logo_scale_x * 0.42)
            panda_logo = Filename.from_os_specific(str(logo_path))
            self.logo = OnscreenImage(image=panda_logo, pos=(0, 0, 0.12), scale=(logo_scale_x, 1.0, logo_scale_z))
            try:
                self.logo.setTransparency(True)
            except Exception:
                pass
            self.status = OnscreenText(text=status_text, pos=(0, -0.78), scale=0.055, fg=(0.86, 0.88, 0.92, 1.0), align=TextNode.ACenter, mayChange=True)
            self.version = OnscreenText(text=f'{APP_TITLE}  {OS_VERSION}', pos=(-1.28, -0.95), scale=0.037, fg=(0.55, 0.58, 0.63, 1.0), align=TextNode.ALeft)
            self.taskMgr.add(self._tick, 'gx_startup_splash_tick')

        def _tick(self, task):
            elapsed = time.time() - self._started_at
            if elapsed <= min_hold:
                return task.cont
            fade_t = min(1.0, (elapsed - min_hold) / max(0.05, fade_duration))
            alpha = max(0.0, 1.0 - fade_t)
            try:
                self.logo.setColorScale(1, 1, 1, alpha)
            except Exception:
                pass
            try:
                self.status.setFg((0.86, 0.88, 0.92, alpha))
                self.version.setFg((0.55, 0.58, 0.63, alpha))
            except Exception:
                pass
            if fade_t >= 1.0:
                self.userExit()
                return task.done
            return task.cont

    splash = None
    try:
        splash = _StartupSplash()
        splash.run()
        return True
    except Exception:
        return False
    finally:
        try:
            if splash is not None:
                splash.destroy()
        except Exception:
            pass



def parse_generated_runtime_cli(argv: list[str] | tuple[str, ...] | None = None) -> dict:
    args = list(argv if argv is not None else sys.argv[1:])
    spec_path: Path | None = None
    smoketest_seconds = 0.0
    passthrough: list[str] = []
    i = 0
    while i < len(args):
        arg = str(args[i])
        if arg == '--spec' and i + 1 < len(args):
            spec_path = Path(str(args[i + 1])).expanduser()
            i += 2
            continue
        if arg == '--runtime-smoketest' and i + 1 < len(args):
            try:
                smoketest_seconds = max(0.0, float(args[i + 1]))
            except Exception:
                smoketest_seconds = 1.25
            i += 2
            continue
        passthrough.append(arg)
        i += 1
    return {
        'spec_path': spec_path,
        'smoketest_seconds': smoketest_seconds,
        'passthrough': passthrough,
    }


def _generated_runtime_color(palette: dict, key: str, default_rgb: tuple[int, int, int]) -> tuple[float, float, float, float]:
    raw = palette.get(key) if isinstance(palette, dict) else None
    if isinstance(raw, str):
        raw = raw.strip().lstrip('#')
        if len(raw) == 6:
            try:
                r = int(raw[0:2], 16)
                g = int(raw[2:4], 16)
                b = int(raw[4:6], 16)
                return (r / 255.0, g / 255.0, b / 255.0, 1.0)
            except Exception:
                pass
    r, g, b = default_rgb
    return (r / 255.0, g / 255.0, b / 255.0, 1.0)


def _generated_runtime_bounds_intersect(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> bool:
    ax, az, aw, ah = a
    bx, bz, bw, bh = b
    return ax < bx + bw and ax + aw > bx and az < bz + bh and az + ah > bz


def _generated_runtime_int(value, default: int, minimum: int = 0) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = int(default)
    return max(int(minimum), parsed)


def _generated_runtime_float(value, default: float, minimum: float | None = None) -> float:
    try:
        parsed = float(value)
    except Exception:
        parsed = float(default)
    if minimum is not None:
        parsed = max(float(minimum), parsed)
    return parsed


def _generated_runtime_rgba_scale(color: tuple[float, float, float, float], *, mul=(1.0, 1.0, 1.0), add=(0.0, 0.0, 0.0), alpha: float | None = None) -> tuple[float, float, float, float]:
    r = max(0.0, min(1.0, color[0] * float(mul[0]) + float(add[0])))
    g = max(0.0, min(1.0, color[1] * float(mul[1]) + float(add[1])))
    b = max(0.0, min(1.0, color[2] * float(mul[2]) + float(add[2])))
    a = color[3] if alpha is None else max(0.0, min(1.0, float(alpha)))
    return (r, g, b, a)


def _generated_runtime_palette_recipe(bg, panel, accent, accent2, text_color, recipe: str, seed_profile: dict | None = None):
    recipe = str(recipe or 'neutral_runtime')
    if recipe == 'alien_colony_bloom':
        colors = (
            _generated_runtime_rgba_scale(bg, mul=(0.82, 0.76, 1.05), add=(0.00, 0.01, 0.03)),
            _generated_runtime_rgba_scale(panel, mul=(0.88, 0.82, 1.08), add=(0.02, 0.00, 0.04)),
            _generated_runtime_rgba_scale(accent, mul=(1.08, 0.82, 1.18), add=(0.06, -0.02, 0.08)),
            _generated_runtime_rgba_scale(accent2, mul=(0.86, 1.12, 1.14), add=(0.00, 0.06, 0.06)),
            text_color,
        )
    elif recipe == 'cluster_bloom':
        colors = (bg, _generated_runtime_rgba_scale(panel, add=(0.03, 0.01, 0.04)), accent, _generated_runtime_rgba_scale(accent2, add=(0.04, 0.04, 0.06)), text_color)
    elif recipe == 'room_circuit':
        colors = (
            _generated_runtime_rgba_scale(bg, mul=(0.82, 0.88, 1.06)),
            _generated_runtime_rgba_scale(panel, mul=(0.88, 0.94, 1.10), add=(0.01, 0.02, 0.04)),
            _generated_runtime_rgba_scale(accent, mul=(1.05, 0.86, 1.08), add=(0.02, 0.00, 0.06)),
            _generated_runtime_rgba_scale(accent2, mul=(0.92, 1.10, 1.12), add=(0.00, 0.04, 0.06)),
            text_color,
        )
    elif recipe == 'strata_oxide':
        colors = (
            _generated_runtime_rgba_scale(bg, mul=(1.00, 0.88, 0.82)),
            _generated_runtime_rgba_scale(panel, mul=(1.04, 0.92, 0.86), add=(0.04, 0.01, 0.00)),
            _generated_runtime_rgba_scale(accent, mul=(1.12, 0.88, 0.74), add=(0.08, 0.00, -0.02)),
            _generated_runtime_rgba_scale(accent2, mul=(0.96, 0.90, 0.84), add=(0.02, 0.00, 0.00)),
            text_color,
        )
    elif recipe == 'cave_nocturne':
        colors = (
            _generated_runtime_rgba_scale(bg, mul=(0.74, 0.82, 1.08), add=(0.00, 0.00, 0.04)),
            _generated_runtime_rgba_scale(panel, mul=(0.78, 0.88, 1.12), add=(0.00, 0.02, 0.06)),
            _generated_runtime_rgba_scale(accent, mul=(0.88, 0.96, 1.18), add=(0.00, 0.02, 0.08)),
            _generated_runtime_rgba_scale(accent2, mul=(0.84, 1.02, 1.20), add=(0.00, 0.04, 0.08)),
            text_color,
        )
    elif recipe == 'hill_bloom':
        colors = (bg, _generated_runtime_rgba_scale(panel, add=(0.02, 0.04, 0.00)), _generated_runtime_rgba_scale(accent, add=(0.04, 0.02, 0.00)), _generated_runtime_rgba_scale(accent2, add=(0.02, 0.06, 0.02)), text_color)
    elif recipe == 'road_signal_grid':
        colors = (
            _generated_runtime_rgba_scale(bg, mul=(0.84, 0.90, 1.00)),
            _generated_runtime_rgba_scale(panel, mul=(0.90, 0.96, 1.04)),
            _generated_runtime_rgba_scale(accent, mul=(1.10, 0.96, 0.70), add=(0.10, 0.04, -0.02)),
            _generated_runtime_rgba_scale(accent2, mul=(0.86, 1.08, 1.14), add=(0.00, 0.04, 0.06)),
            text_color,
        )
    elif recipe == 'field_bloom':
        colors = (bg, _generated_runtime_rgba_scale(panel, add=(0.02, 0.04, 0.02)), _generated_runtime_rgba_scale(accent, add=(0.04, 0.04, 0.00)), _generated_runtime_rgba_scale(accent2, add=(0.02, 0.08, 0.02)), text_color)
    else:
        colors = (bg, panel, accent, accent2, text_color)
    seed_profile = dict(seed_profile or {})
    labels = [str(x) for x in list(seed_profile.get('labels', []) or []) if str(x).strip()]
    material_profile = str(seed_profile.get('material_profile', 'neutral') or 'neutral')
    texture_rhythm = str(seed_profile.get('texture_rhythm', 'plain') or 'plain')
    noise_channels = [str(x) for x in list(seed_profile.get('noise_channels', []) or []) if str(x).strip()]
    moisture_bias = str(seed_profile.get('moisture_bias', 'balanced') or 'balanced')
    lane_cadence = str(seed_profile.get('lane_cadence', 'steady') or 'steady')
    tile_pattern = str(seed_profile.get('tile_pattern', 'plain') or 'plain')
    bg, panel, accent, accent2, text_color = colors
    if material_profile == 'strata':
        bg = _generated_runtime_rgba_scale(bg, mul=(1.02, 0.92, 0.86), add=(0.03, 0.01, 0.00))
        panel = _generated_runtime_rgba_scale(panel, mul=(1.06, 0.94, 0.88), add=(0.05, 0.02, 0.00))
    elif material_profile in {'biome_field', 'tile_textured'}:
        bg = _generated_runtime_rgba_scale(bg, mul=(0.94, 1.00, 0.94), add=(0.00, 0.03, 0.00))
        panel = _generated_runtime_rgba_scale(panel, mul=(0.96, 1.04, 0.98), add=(0.00, 0.03, 0.01))
    elif material_profile == 'road_bands':
        panel = _generated_runtime_rgba_scale(panel, mul=(0.90, 0.94, 1.02), add=(0.01, 0.02, 0.04))
        accent2 = _generated_runtime_rgba_scale(accent2, mul=(0.92, 1.08, 1.12), add=(0.00, 0.05, 0.06))
    if texture_rhythm == 'dither':
        accent2 = _generated_runtime_rgba_scale(accent2, add=(0.04, 0.04, 0.02))
    elif texture_rhythm == 'tile_speckle':
        panel = _generated_runtime_rgba_scale(panel, add=(0.03, 0.03, 0.04))
    elif texture_rhythm == 'drip':
        accent = _generated_runtime_rgba_scale(accent, mul=(0.90, 0.98, 1.14), add=(0.00, 0.02, 0.06))
    if 'heat' in noise_channels:
        accent = _generated_runtime_rgba_scale(accent, add=(0.04, 0.01, -0.01))
    if 'moisture' in noise_channels:
        accent2 = _generated_runtime_rgba_scale(accent2, add=(0.00, 0.05, 0.05))
    if 'height' in noise_channels:
        bg = _generated_runtime_rgba_scale(bg, mul=(0.96, 0.96, 1.02))
    if moisture_bias == 'wet':
        panel = _generated_runtime_rgba_scale(panel, add=(0.00, 0.03, 0.04))
        accent2 = _generated_runtime_rgba_scale(accent2, add=(0.00, 0.04, 0.06))
    elif moisture_bias == 'dry':
        panel = _generated_runtime_rgba_scale(panel, add=(0.03, 0.02, 0.00))
        accent = _generated_runtime_rgba_scale(accent, add=(0.04, 0.02, -0.01))
    elif moisture_bias == 'mixed':
        accent2 = _generated_runtime_rgba_scale(accent2, add=(0.00, 0.03, 0.04))
        accent = _generated_runtime_rgba_scale(accent, add=(0.03, 0.01, 0.00))
    if lane_cadence == 'dense':
        accent2 = _generated_runtime_rgba_scale(accent2, add=(0.02, 0.04, 0.03))
    elif lane_cadence == 'sparse':
        bg = _generated_runtime_rgba_scale(bg, mul=(0.98, 0.98, 1.01))
    if tile_pattern == 'stripe':
        panel = _generated_runtime_rgba_scale(panel, add=(0.02, 0.02, 0.03))
    elif tile_pattern == 'speckle_stripe':
        panel = _generated_runtime_rgba_scale(panel, add=(0.03, 0.03, 0.05))
        accent2 = _generated_runtime_rgba_scale(accent2, add=(0.02, 0.03, 0.04))
    if 'hill_world_fill' in labels:
        panel = _generated_runtime_rgba_scale(panel, add=(0.03, 0.02, 0.00))
    return bg, panel, accent, accent2, text_color


def _generated_runtime_preview_card(blueprint: dict) -> list[str]:
    return [str(x) for x in list(blueprint.get('preview_card', []) or [])[:4]]


def _generated_runtime_art_motif_rects(plan: dict, blueprint: dict, world_w: float, world_h: float, world_floor: float, seed: int) -> list[dict]:
    rng = random.Random(int(seed) ^ 0x6A77B1D)
    motif = str(blueprint.get('visual_motif', 'noise_scatter') or 'noise_scatter')
    seed_profile = _generated_runtime_seed_profile(blueprint)
    texture_rhythm = str(seed_profile.get('texture_rhythm', 'plain') or 'plain')
    noise_channels = [str(x) for x in list(seed_profile.get('noise_channels', []) or []) if str(x).strip()]
    rects: list[dict] = []
    def add(kind: str, x: float, z: float, w: float, h: float, depth: float = 7.33, alpha: float = 0.12):
        rects.append({'kind': kind, 'x': x, 'z': z, 'w': w, 'h': h, 'depth': depth, 'alpha': alpha})
    def frame(kind: str, x: float, z: float, w: float, h: float, step: float = 12.0, count: int = 3, alpha: float = 0.12):
        for idx in range(count):
            off = idx * step
            ww = max(18.0, w - off * 2.0)
            hh = max(18.0, h - off * 2.0)
            xx = x + off
            zz = z + off
            if ww <= 18.0 or hh <= 18.0:
                break
            band = 3.0 + idx
            add(kind, xx, zz, ww, band, alpha=alpha)
            add(kind, xx, zz + hh - band, ww, band, alpha=alpha)
            add(kind, xx, zz, band, hh, alpha=alpha)
            add(kind, xx + ww - band, zz, band, hh, alpha=alpha)
    if motif in {'concentric_clusters', 'hub_rings'}:
        targets = [d for d in plan.get('decor_rects', []) if str(d.get('kind')) in {'cluster_core', 'hub_core'}]
        for dec in targets[:6]:
            frame('motif_frame', float(dec['x']) - 18.0, float(dec['z']) - 16.0, float(dec['w']) + 36.0, float(dec['h']) + 32.0, step=12.0, count=3 if motif == 'concentric_clusters' else 4, alpha=0.10)
    elif motif in {'wave_grid', 'district_grid'}:
        left = 64.0
        top = 64.0
        w = max(220.0, world_w - 128.0)
        h = max(220.0, world_h - 160.0)
        rows = 10 if motif == 'wave_grid' else 8
        cols = 10 if motif == 'wave_grid' else 8
        for ridx in range(rows):
            z = top + ridx * (h / max(1, rows - 1))
            wob = math.sin(ridx * 0.75) * 12.0
            add('motif_grid', left + 8.0 + wob, z, w - 16.0, 3.0, alpha=0.11)
        for cidx in range(cols):
            x = left + cidx * (w / max(1, cols - 1))
            wob = math.cos(cidx * 0.66) * 10.0
            add('motif_grid', x, top + 8.0 + wob, 3.0, h - 16.0, alpha=0.10)
    elif motif in {'harmonic_bands', 'harmonic_waves', 'wave_runner'}:
        band_count = 7 if motif == 'harmonic_bands' else 5
        for idx in range(band_count):
            z = world_floor + 54.0 + idx * 72.0
            amplitude = 10.0 + idx * 2.0
            seg_w = max(80.0, world_w / 9.0)
            x = 0.0
            for seg in range(10):
                offset = math.sin((seg * 0.85) + idx * 0.42) * amplitude
                add('motif_wave', x, z + offset, seg_w, 6.0 if motif != 'wave_runner' else 4.0, alpha=0.10)
                x += seg_w - 6.0
    elif motif == 'drip_noise':
        for idx in range(32):
            x = 70.0 + idx * max(22.0, (world_w - 140.0) / 32.0)
            length = 10.0 + (idx % 5) * 8.0 + rng.randint(0, 6)
            z = min(world_h - 120.0, world_floor + 190.0 + (idx % 4) * 46.0)
            add('motif_drip', x, z, 4.0, length, alpha=0.12)
        for idx in range(18):
            add('motif_noise', 100.0 + rng.random() * max(80.0, world_w - 200.0), world_floor + 90.0 + rng.random() * max(80.0, world_h - world_floor - 220.0), 8.0, 8.0, alpha=0.08)
    else:
        for idx in range(18):
            add('motif_noise', 90.0 + rng.random() * max(80.0, world_w - 180.0), 90.0 + rng.random() * max(80.0, world_h - 180.0), 10.0, 10.0, alpha=0.08)
    if texture_rhythm == 'tile_speckle':
        for idx in range(28):
            add('motif_noise', 72.0 + (idx % 7) * max(26.0, (world_w - 160.0) / 7.0), 84.0 + (idx // 7) * 64.0, 6.0, 6.0, depth=7.34, alpha=0.10)
    elif texture_rhythm == 'bands':
        for idx in range(5):
            add('motif_wave', 48.0, world_floor + 56.0 + idx * 78.0, max(120.0, world_w - 96.0), 4.0, depth=7.34, alpha=0.08)
    elif texture_rhythm == 'dither':
        for idx in range(24):
            add('motif_grid', 70.0 + (idx % 6) * max(28.0, (world_w - 180.0) / 6.0), 96.0 + (idx // 6) * 52.0, 4.0, 4.0, depth=7.34, alpha=0.09)
    if 'moisture' in noise_channels:
        for idx in range(10):
            add('motif_wave', 90.0 + idx * max(40.0, (world_w - 220.0) / 10.0), world_floor + 120.0 + math.sin(idx * 0.55) * 18.0, 26.0, 3.0, depth=7.35, alpha=0.09)
    return rects


def _generated_runtime_world_blueprint(spec: dict) -> dict:
    bp = dict(spec.get('world_blueprint', {}) or {})
    dims = dict(bp.get('dimensions', {}) or {})
    controls = dict(bp.get('controls', {}) or {})
    seed_profile = dict(bp.get('seed_profile', {}) or {})
    return {
        'world_family': str(bp.get('world_family', 'generic_world') or 'generic_world'),
        'requested_profile': str(bp.get('requested_profile', 'any') or 'any'),
        'variant': str(bp.get('variant', '') or ''),
        'world_mode': str(bp.get('world_mode', 'any') or 'any'),
        'formation_style': str(bp.get('formation_style', 'any') or 'any'),
        'generator_family': str(bp.get('generator_family', 'mixed_world') or 'mixed_world'),
        'terrain_recipe': str(bp.get('terrain_recipe', 'generic_fields') or 'generic_fields'),
        'layout_recipe': str(bp.get('layout_recipe', 'balanced') or 'balanced'),
        'runtime_shape': str(bp.get('runtime_shape', 'single_map') or 'single_map'),
        'dimensions': dims,
        'controls': controls,
        'summary': str(bp.get('summary', '') or ''),
        'visual_motif': str(bp.get('visual_motif', 'noise_scatter') or 'noise_scatter'),
        'palette_recipe': str(bp.get('palette_recipe', 'neutral_runtime') or 'neutral_runtime'),
        'preview_card': list(bp.get('preview_card', []) or []),
        'terrain_seed_snippets': list(bp.get('terrain_seed_snippets', []) or []),
        'terrain_seed_labels': [str(x) for x in list(bp.get('terrain_seed_labels', []) or []) if str(x).strip()],
        'standard_packs': [str(x) for x in list(bp.get('standard_packs', []) or []) if str(x).strip()],
        'spatial_manifest': dict(bp.get('spatial_manifest', {}) or {}),
        'seed_profile': {
            'labels': [str(x) for x in list(seed_profile.get('labels', []) or []) if str(x).strip()],
            'donors': [str(x) for x in list(seed_profile.get('donors', []) or []) if str(x).strip()],
            'material_profile': str(seed_profile.get('material_profile', 'neutral') or 'neutral'),
            'geometry_bias': str(seed_profile.get('geometry_bias', 'balanced') or 'balanced'),
            'texture_rhythm': str(seed_profile.get('texture_rhythm', 'plain') or 'plain'),
            'noise_channels': [str(x) for x in list(seed_profile.get('noise_channels', []) or []) if str(x).strip()],
            'moisture_bias': str(seed_profile.get('moisture_bias', 'balanced') or 'balanced'),
            'layer_density': str(seed_profile.get('layer_density', 'medium') or 'medium'),
            'cave_spacing': str(seed_profile.get('cave_spacing', 'medium') or 'medium'),
            'lane_cadence': str(seed_profile.get('lane_cadence', 'steady') or 'steady'),
            'surface_motion': str(seed_profile.get('surface_motion', 'settled') or 'settled'),
            'tile_pattern': str(seed_profile.get('tile_pattern', 'plain') or 'plain'),
            'biome_patch_mode': str(seed_profile.get('biome_patch_mode', 'balanced') or 'balanced'),
            'region_blend': str(seed_profile.get('region_blend', 'balanced') or 'balanced'),
            'vista_density': str(seed_profile.get('vista_density', 'medium') or 'medium'),
            'terrain_step': str(seed_profile.get('terrain_step', 'medium') or 'medium'),
            'stream_budget': str(seed_profile.get('stream_budget', 'balanced') or 'balanced'),
            'prop_budget': str(seed_profile.get('prop_budget', 'medium') or 'medium'),
            'interior_density': str(seed_profile.get('interior_density', 'medium') or 'medium'),
        },
    }


def _generated_runtime_seed_profile(blueprint: dict) -> dict:
    seed_profile = dict(blueprint.get('seed_profile', {}) or {})
    labels = [str(x) for x in list(seed_profile.get('labels', []) or blueprint.get('terrain_seed_labels', []) or []) if str(x).strip()]
    donors = [str(x) for x in list(seed_profile.get('donors', []) or []) if str(x).strip()]
    material_profile = str(seed_profile.get('material_profile', 'neutral') or 'neutral')
    geometry_bias = str(seed_profile.get('geometry_bias', 'balanced') or 'balanced')
    texture_rhythm = str(seed_profile.get('texture_rhythm', 'plain') or 'plain')
    noise_channels = [str(x) for x in list(seed_profile.get('noise_channels', []) or []) if str(x).strip()]
    moisture_bias = str(seed_profile.get('moisture_bias', 'balanced') or 'balanced')
    layer_density = str(seed_profile.get('layer_density', 'medium') or 'medium')
    cave_spacing = str(seed_profile.get('cave_spacing', 'medium') or 'medium')
    lane_cadence = str(seed_profile.get('lane_cadence', 'steady') or 'steady')
    surface_motion = str(seed_profile.get('surface_motion', 'settled') or 'settled')
    tile_pattern = str(seed_profile.get('tile_pattern', 'plain') or 'plain')
    biome_patch_mode = str(seed_profile.get('biome_patch_mode', 'balanced') or 'balanced')
    region_blend = str(seed_profile.get('region_blend', 'balanced') or 'balanced')
    vista_density = str(seed_profile.get('vista_density', 'medium') or 'medium')
    terrain_step = str(seed_profile.get('terrain_step', 'medium') or 'medium')
    stream_budget = str(seed_profile.get('stream_budget', 'balanced') or 'balanced')
    prop_budget = str(seed_profile.get('prop_budget', 'medium') or 'medium')
    interior_density = str(seed_profile.get('interior_density', 'medium') or 'medium')
    transition_pressure = str(seed_profile.get('transition_pressure', 'medium') or 'medium')
    horizon_openness = str(seed_profile.get('horizon_openness', 'medium') or 'medium')
    landmark_density = str(seed_profile.get('landmark_density', 'medium') or 'medium')
    runner_flow = str(seed_profile.get('runner_flow', 'steady') or 'steady')
    travel_phase_count = int(seed_profile.get('travel_phase_count', 3) or 3)
    landmark_stride = str(seed_profile.get('landmark_stride', 'medium') or 'medium')
    underground_depth = str(seed_profile.get('underground_depth', 'medium') or 'medium')
    travel_phase_count = int(seed_profile.get('travel_phase_count', 3) or 3)
    landmark_stride = str(seed_profile.get('landmark_stride', 'medium') or 'medium')
    underground_depth = str(seed_profile.get('underground_depth', 'medium') or 'medium')
    if 'terrain_layers' in labels and material_profile == 'neutral':
        material_profile = 'strata'
        layer_density = 'high' if layer_density == 'medium' else layer_density
    if 'cave_carving' in labels and geometry_bias == 'balanced':
        geometry_bias = 'cavernous'
        cave_spacing = 'tight' if cave_spacing == 'medium' else cave_spacing
    if 'tile_texture_generation' in labels and texture_rhythm == 'plain':
        texture_rhythm = 'tile_speckle'
        tile_pattern = 'speckle' if tile_pattern == 'plain' else tile_pattern
    if 'ground_band_texture' in labels and texture_rhythm == 'plain':
        texture_rhythm = 'dither'
        surface_motion = 'forward_runner' if surface_motion == 'settled' else surface_motion
    if 'height_noise' in labels and 'height' not in noise_channels:
        noise_channels.append('height')
    if 'heat_noise' in labels and 'heat' not in noise_channels:
        noise_channels.append('heat')
    if 'moisture_noise' in labels and 'moisture' not in noise_channels:
        noise_channels.append('moisture')
    if 'moisture' in noise_channels and 'heat' in noise_channels and moisture_bias == 'balanced':
        moisture_bias = 'mixed'
        biome_patch_mode = 'wet_dry_fields' if biome_patch_mode == 'balanced' else biome_patch_mode
    elif 'moisture' in noise_channels and moisture_bias == 'balanced':
        moisture_bias = 'wet'
    elif 'heat' in noise_channels and moisture_bias == 'balanced':
        moisture_bias = 'dry'
    return {
        'labels': labels[:8],
        'donors': donors[:4],
        'material_profile': material_profile,
        'geometry_bias': geometry_bias,
        'texture_rhythm': texture_rhythm,
        'noise_channels': noise_channels[:4],
        'moisture_bias': moisture_bias,
        'layer_density': layer_density,
        'cave_spacing': cave_spacing,
        'lane_cadence': lane_cadence,
        'surface_motion': surface_motion,
        'tile_pattern': tile_pattern,
        'biome_patch_mode': biome_patch_mode,
        'region_blend': region_blend,
        'vista_density': vista_density,
        'terrain_step': terrain_step,
        'stream_budget': stream_budget,
        'prop_budget': prop_budget,
        'interior_density': interior_density,
        'transition_pressure': transition_pressure,
        'horizon_openness': horizon_openness,
        'landmark_density': landmark_density,
        'runner_flow': runner_flow,
        'travel_phase_count': travel_phase_count,
        'landmark_stride': landmark_stride,
        'underground_depth': underground_depth,
    }


def _generated_runtime_stage_positions(world_w: float, stage_count: int) -> list[float]:
    stage_count = max(2, int(stage_count))
    step = max(180.0, float(world_w) / float(stage_count))
    return [min(float(world_w) - 120.0, 90.0 + idx * step) for idx in range(stage_count)]


def _generated_runtime_build_plan(game_type: str, world_w: float, world_h: float, world_floor: float, blueprint: dict, runtime_recipe: dict, *, seed: int) -> dict:
    rng = random.Random(int(seed) ^ 0x4F33A19)
    terrain_recipe = str(blueprint.get('terrain_recipe', 'generic_fields') or 'generic_fields')
    runtime_shape = str(blueprint.get('runtime_shape', 'single_map') or 'single_map')
    world_family = str(blueprint.get('world_family', 'generic_world') or 'generic_world')
    formation = str(blueprint.get('formation_style', 'any') or 'any')
    controls = dict(blueprint.get('controls', {}) or {})
    dims = dict(blueprint.get('dimensions', {}) or {})
    seed_profile = _generated_runtime_seed_profile(blueprint)
    seed_labels = [str(x) for x in list(seed_profile.get('labels', []) or []) if str(x).strip()]
    noise_channels = [str(x) for x in list(seed_profile.get('noise_channels', []) or []) if str(x).strip()]
    texture_rhythm = str(seed_profile.get('texture_rhythm', 'plain') or 'plain')
    geometry_bias = str(seed_profile.get('geometry_bias', 'balanced') or 'balanced')
    moisture_bias = str(seed_profile.get('moisture_bias', 'balanced') or 'balanced')
    layer_density = str(seed_profile.get('layer_density', 'medium') or 'medium')
    cave_spacing = str(seed_profile.get('cave_spacing', 'medium') or 'medium')
    lane_cadence = str(seed_profile.get('lane_cadence', 'steady') or 'steady')
    surface_motion = str(seed_profile.get('surface_motion', 'settled') or 'settled')
    tile_pattern = str(seed_profile.get('tile_pattern', 'plain') or 'plain')
    biome_patch_mode = str(seed_profile.get('biome_patch_mode', 'balanced') or 'balanced')
    transition_pressure = str(seed_profile.get('transition_pressure', 'medium') or 'medium')
    horizon_openness = str(seed_profile.get('horizon_openness', 'medium') or 'medium')
    landmark_density = str(seed_profile.get('landmark_density', 'medium') or 'medium')
    runner_flow = str(seed_profile.get('runner_flow', 'steady') or 'steady')
    travel_phase_count = int(seed_profile.get('travel_phase_count', 3) or 3)
    landmark_stride = str(seed_profile.get('landmark_stride', 'medium') or 'medium')
    underground_depth = str(seed_profile.get('underground_depth', 'medium') or 'medium')
    plan = {
        'note': f"{world_family} • {terrain_recipe} • {runtime_shape}",
        'decor_rects': [],
        'segments': [],
        'pickups': [],
        'enemies': [],
        'player_spawn': None,
        'goal_markers': [],
        'preview_lines': [],
        'formation_signature': '',
        'seed_labels': seed_labels[:6],
        'seed_profile': seed_profile,
    }
    if seed_labels:
        plan['note'] = f"{plan['note']} • seeds {', '.join(seed_labels[:3])}"

    def add_decor(kind: str, x: float, z: float, w: float, h: float, *, depth: float = 7.2, alpha: float = 0.18):
        plan['decor_rects'].append({'kind': kind, 'x': x, 'z': z, 'w': w, 'h': h, 'depth': depth, 'alpha': alpha})

    def add_segment(x: float, z: float, w: float, h: float, *, kind: str = 'solid', enemy: bool = False, pickup: bool = False):
        plan['segments'].append({'x': x, 'z': z, 'w': w, 'h': h, 'kind': kind})
        if pickup:
            plan['pickups'].append((x + max(10.0, w * 0.5 - 12.0), z + h + 38.0))
        if enemy:
            patrol = None
            if game_type == 'platformer':
                patrol = (x + 16.0, x + max(20.0, w - 42.0))
                ez = z + h
            else:
                ez = z + max(8.0, h * 0.5)
            ex = x + max(12.0, min(w - 44.0, w * 0.65))
            plan['enemies'].append({'x': ex, 'z': ez, 'patrol': patrol, 'speed': 96.0 + (len(plan['enemies']) % 3) * 16.0})

    if game_type == 'platformer':
        zones = _generated_runtime_int(dims.get('zones', 6), 6, 4)
        bands = _generated_runtime_int(dims.get('bands', 4), 4, 2)
        base_floor_h = max(28.0, world_floor)
        add_segment(0.0, 0.0, float(world_w), base_floor_h, kind='ground')
        add_decor('ground_band', 0.0, 0.0, float(world_w), base_floor_h + 24.0, depth=7.1, alpha=0.14)
        stage_count = _generated_runtime_int(controls.get('stage_count', 5), 5, 2)
        if runtime_shape == 'staged_levels':
            for pos in _generated_runtime_stage_positions(world_w, stage_count):
                plan['goal_markers'].append((pos, world_floor + 42.0))
        x_cursor = 150.0
        if terrain_recipe == 'surface_sub_deep_layers':
            strata_layers = bands + (1 if 'terrain_layers' in seed_labels else 0)
            if layer_density == 'high':
                strata_layers += 1
            elif layer_density == 'low':
                strata_layers = max(3, strata_layers - 1)
            layer_count = _generated_runtime_int(controls.get('material_layers', bands), strata_layers, 3)
            zone_span = max(220.0, (world_w - 220.0) / max(1, zones))
            plan['formation_signature'] = 'strata'
            plan['preview_lines'] = ['Layered strata bands', f'{layer_count} material layers', f'{zones} traversal zones • {layer_density} density • {transition_pressure} transitions']
            for zone in range(zones):
                zone_x = 120.0 + zone * zone_span
                previous_top = None
                surface_anchor = world_floor + 82.0 + rng.randint(-6, 8)
                for layer in range(layer_count):
                    width = max(120.0, zone_span - 40.0 - layer * (18.0 if 'height' in noise_channels else 24.0))
                    z = surface_anchor + layer * (82.0 if transition_pressure == 'high' else 92.0) + rng.randint(-10, 12)
                    x = zone_x + layer * 14.0 + rng.randint(-6, 6)
                    height = 22.0 + (layer % 2) * 6.0 + (4.0 if texture_rhythm == 'bands' and layer % 2 == 0 else 0.0)
                    add_segment(x, z, width, height, kind='strata', pickup=(layer > 0), enemy=(layer == layer_count - 1 or (zone + layer) % 2 == 0))
                    add_decor('strata_back', x - 8.0, max(0.0, z - 34.0), width + 16.0, 28.0, alpha=0.16)
                    vein_h = 10.0 + (layer % 2) * 3.0
                    add_decor('strata_vein', x + 12.0, z + height + 4.0, max(60.0, width - 24.0), vein_h, depth=7.26, alpha=0.18)
                    if layer == 0 and (zone % 2 == 1 or transition_pressure == 'high'):
                        cut_h = 28.0 + (12.0 if transition_pressure == 'high' else 0.0)
                        add_decor('strata_cut', x + width * 0.12, max(world_floor + 18.0, z - cut_h - 6.0), 18.0, cut_h, depth=7.27, alpha=0.22)
                    if previous_top is not None and layer > 0:
                        bridge_x = x + width * 0.18
                        bridge_w = max(44.0, min(112.0 if layer_density == 'high' else 96.0, width * (0.34 if layer_density == 'high' else 0.28)))
                        bridge_z = previous_top + (24.0 if transition_pressure == 'high' else (30.0 if layer_density == 'high' else 36.0)) + rng.randint(-6, 8)
                        bridge_kind = 'strata_bridge'
                        add_segment(bridge_x, bridge_z, bridge_w, 12.0, kind=bridge_kind, pickup=False, enemy=False)
                        if transition_pressure == 'high' and layer == layer_count - 1:
                            ramp_x = bridge_x + bridge_w * 0.68
                            add_segment(ramp_x, bridge_z + 14.0, max(34.0, bridge_w * 0.26), 10.0, kind='strata_ramp', pickup=False, enemy=False)
                    previous_top = z + height
            plan['player_spawn'] = (140.0, world_floor + 124.0)
        elif terrain_recipe == 'surface_layers_with_cave_carve':
            cave_density = _generated_runtime_float(controls.get('cave_density', 0.55), 0.62 if cave_spacing == 'tight' else 0.55, 0.1)
            chamber_count = max(4, zones + 1 + (1 if 'cave_carving' in seed_labels else 0) + (1 if cave_spacing == 'tight' else 0))
            plan['formation_signature'] = 'caves'
            plan['preview_lines'] = ['Carved cave route', f'{chamber_count} chambers', f'density {cave_density:0.2f} • {cave_spacing} spacing • {transition_pressure} exits']
            for idx in range(chamber_count):
                floor_w = 180.0 + rng.randint(0, 3) * (42.0 if 'terrain_layers' in seed_labels else 50.0)
                floor_z = world_floor + 90.0 + (idx % 3) * (68.0 if transition_pressure == 'high' else 74.0) + rng.randint(-16, 18)
                add_segment(x_cursor, floor_z, floor_w, 24.0, kind='cave_floor', pickup=True, enemy=(idx % 2 == 0))
                chamber_x = x_cursor + 18.0
                chamber_w = max(70.0, floor_w - 36.0)
                chamber_z = max(world_floor + 22.0, floor_z - 28.0)
                chamber_h = 76.0 + (idx % 2) * 20.0 + (10.0 if cave_spacing == 'wide' else 0.0)
                add_decor('cave_chamber', chamber_x, chamber_z, chamber_w, chamber_h, depth=7.29, alpha=0.14)
                if cave_density > 0.35:
                    ceiling_h = 26.0 + (idx % 2) * 10.0
                    ceiling_z = min(world_h - 130.0, floor_z + 126.0 + rng.randint(0, 40))
                    add_decor('cave_ceiling', x_cursor - 12.0, ceiling_z, floor_w + 24.0, ceiling_h, depth=7.35, alpha=0.2)
                    add_decor('cave_drip', x_cursor + floor_w * 0.33, ceiling_z - 18.0, 8.0, 18.0, depth=7.34, alpha=0.24)
                    add_decor('cave_drip', x_cursor + floor_w * 0.68, ceiling_z - 14.0, 8.0, 14.0, depth=7.34, alpha=0.22)
                if idx % 2 == 1:
                    pillar_x = x_cursor + floor_w * 0.5
                    add_decor('cave_pillar', pillar_x, world_floor + 12.0, 20.0, max(60.0, floor_z - world_floor + 18.0), depth=7.32, alpha=0.22)
                if idx < chamber_count - 1:
                    plan['goal_markers'].append((x_cursor + floor_w - 24.0, floor_z + 18.0))
                    if transition_pressure == 'high' or idx % 2 == 0:
                        exit_x = x_cursor + floor_w * 0.74
                        exit_h = 34.0 + (8.0 if cave_spacing == 'tight' else 0.0)
                        add_decor('cave_exit', exit_x, max(world_floor + 12.0, floor_z - exit_h - 4.0), 18.0, exit_h, depth=7.31, alpha=0.20)
                cave_gap = 52.0 if cave_spacing == 'tight' else 90.0 if cave_spacing == 'medium' else 132.0
                x_cursor += floor_w + cave_gap + rng.randint(0, 50 if cave_spacing == 'tight' else 60)
            plan['player_spawn'] = (130.0, world_floor + 120.0)
        elif terrain_recipe == 'rolling_heightfield':
            wave_count = max(8, zones * 3 + (1 if 'hill_world_fill' in seed_labels else 0) + max(0, travel_phase_count - 3))
            seg_w = max(120.0, (world_w - 220.0) / wave_count)
            landmark_mod = 5 if landmark_stride == 'sparse' else 4 if landmark_stride == 'medium' else 3
            x = 0.0
            plan['preview_lines'] = ['Rolling hill traverse', f'{wave_count} hill bands', f'{horizon_openness} horizon • {travel_phase_count} travel phases']
            for idx in range(wave_count):
                phase = idx % max(2, travel_phase_count)
                crest = math.sin(idx * 0.72) * (84.0 if geometry_bias == 'rolling_fill' else 70.0) + math.cos(idx * 0.31) * 26.0
                if phase == 0:
                    crest *= 0.45
                elif phase == max(2, travel_phase_count) - 1:
                    crest *= 1.15
                z = world_floor + 86.0 + crest
                width = seg_w + 18.0 + (12.0 if phase == 0 else 0.0)
                add_segment(x, z, width, 22.0, kind='hill', pickup=(idx % 3 == 1), enemy=(idx % 4 == 2 and phase != 0))
                add_decor('hill_shadow', x, max(0.0, z - 26.0), width, 22.0, alpha=0.15)
                if idx % landmark_mod == 0:
                    add_decor('road_landmark', x + width * 0.68, z + 24.0, 14.0, 22.0, depth=7.23, alpha=0.15)
                x += seg_w
            plan['player_spawn'] = (90.0, world_floor + 132.0)
        elif terrain_recipe == 'open_field_side_bands':
            field_segments = max(7, zones * 2 + (1 if horizon_openness == 'high' else 0) + max(0, travel_phase_count - 3))
            seg_w = max(150.0, (world_w - 220.0) / field_segments)
            plan['formation_signature'] = 'open_field'
            plan['preview_lines'] = ['Open side field', f'{field_segments} stretches', f'{horizon_openness} horizon • {landmark_density} landmarks • {travel_phase_count} phases']
            x = 0.0
            for idx in range(field_segments):
                phase = idx % max(2, travel_phase_count)
                roll = math.sin(idx * 0.46) * (22.0 if horizon_openness == 'high' else 34.0)
                if phase == 0:
                    roll *= 0.35
                z = world_floor + 94.0 + roll + rng.randint(-8, 10)
                width = seg_w + rng.randint(-6, 24) + (20.0 if phase == 0 else 0.0)
                add_segment(x, z, width, 20.0, kind='open_ground', pickup=(idx % 4 == 1), enemy=(idx % 5 == 3 and landmark_density != 'sparse' and phase != 0))
                if idx % (5 if landmark_density == 'sparse' else 3) == 0:
                    add_decor('hill_shadow', x, max(0.0, z - 18.0), width, 16.0, alpha=0.12)
                if idx % (6 if landmark_density == 'sparse' else 4) == 2:
                    add_decor('road_landmark', x + width * 0.62, z + 18.0, 16.0, 22.0, depth=7.23, alpha=0.16)
                x += seg_w
            plan['player_spawn'] = (92.0, world_floor + 122.0)
        elif terrain_recipe == 'strip_roads_with_surface_bands' or runtime_shape in {'lane_traverse', 'endless_scroll'}:
            lane_base = 2 if lane_cadence != 'dense' else 3
            lane_count = _generated_runtime_int(controls.get('lane_count', 2), lane_base, 2)
            road_base = 12 if lane_cadence == 'dense' else 8 if lane_cadence == 'sparse' else 10
            road_segments = _generated_runtime_int(controls.get('road_segments', 10), road_base + max(0, travel_phase_count - 3), 4)
            seg_w = max(140.0, (world_w - 220.0) / road_segments)
            divider_step = 1 if lane_cadence == 'dense' else 3 if lane_cadence == 'sparse' else 2
            sign_step = 2 if lane_cadence == 'dense' else 4 if lane_cadence == 'sparse' else 3
            landmark_step = 2 if landmark_density == 'high' else 4 if landmark_density == 'sparse' else 3
            pace_block = 2 if runner_flow == 'high' else 3
            landmark_mod = 2 if landmark_stride == 'dense' else 4 if landmark_stride == 'sparse' else 3
            plan['formation_signature'] = 'roads'
            plan['preview_lines'] = ['Strip-road traversal', f'{lane_count} lanes', f'{road_segments} road bands • {lane_cadence} cadence • {runner_flow} flow • {travel_phase_count} phases']
            for lane_idx in range(lane_count):
                lane_z = world_floor + 82.0 + lane_idx * 78.0
                add_decor('road_band', 0.0, lane_z - 10.0, float(world_w), 44.0, depth=7.18, alpha=0.18)
                x = 0.0
                for seg_idx in range(road_segments):
                    cycle = seg_idx % max(2, pace_block + 1)
                    travel_phase = seg_idx % max(2, travel_phase_count)
                    width = seg_w - 24.0 + rng.randint(-10, 20)
                    if cycle == 0 and runner_flow == 'high':
                        width += 18.0
                    if travel_phase == 0:
                        width += 24.0
                    elif travel_phase == max(2, travel_phase_count) - 1:
                        width -= 8.0
                    add_segment(x, lane_z, width, 18.0, kind='road_lane', pickup=(seg_idx % 3 == 1 and lane_idx == 0), enemy=((seg_idx + lane_idx) % (3 if runner_flow == 'high' else 4) == 2 and lane_idx == lane_count - 1 and travel_phase != 0))
                    add_decor('road_shoulder', x, lane_z - 12.0, width, 6.0, depth=7.19, alpha=0.12)
                    if seg_idx % divider_step == 0:
                        add_decor('road_divider', x + width * 0.45, lane_z + 20.0, 18.0, 10.0, depth=7.28, alpha=0.24)
                        if texture_rhythm == 'dither' and seg_idx % sign_step == 0:
                            add_decor('road_sign', x + width * 0.72, lane_z + 40.0, 12.0, 18.0, depth=7.24, alpha=0.24)
                    if seg_idx % sign_step == 0:
                        add_decor('road_marker', x + width * 0.24, lane_z + 24.0, 8.0, 14.0, depth=7.29, alpha=0.22)
                        add_decor('road_sign', x + width * 0.72, lane_z + 28.0, 12.0, 22.0, depth=7.3, alpha=0.26)
                    if seg_idx % landmark_mod == 0:
                        landmark_x = x + width * (0.6 if runner_flow == 'high' else 0.52)
                        add_decor('road_landmark', landmark_x, lane_z + 50.0, 18.0, 26.0, depth=7.25, alpha=0.22)
                    if seg_idx % max(2, landmark_mod + 1) == 1:
                        add_decor('road_debris', x + width * 0.16, lane_z - 6.0, 16.0, 8.0, depth=7.21, alpha=0.18)
                    if seg_idx % max(2, sign_step + 1) == 1 and lane_idx == lane_count - 1:
                        add_segment(x + width * 0.2, lane_z + 28.0, 32.0, 16.0, kind='road_gate', enemy=False, pickup=False)
                    x += seg_w
            plan['player_spawn'] = (90.0, world_floor + 108.0)
        else:
            step = 0
            while x_cursor < world_w - 220.0:
                width = 180.0 + rng.randint(0, 3) * 70.0
                z = 180.0 + (step % 5) * 90.0 + rng.randint(-22, 22)
                if step % 4 == 3:
                    z += 90.0
                add_segment(x_cursor, z, width, 28.0, kind='platform', pickup=(step > 0), enemy=(step % 2 == 0))
                x_cursor += width + 120.0 + rng.randint(0, 70)
                step += 1
            plan['player_spawn'] = (float(controls.get('spawn_x', 160.0) or 160.0), float(controls.get('spawn_z', world_floor + 120.0) or (world_floor + 120.0)))
    else:
        border = 42.0
        # border walls remain part of segments to preserve collision
        plan['segments'].extend([
            {'x': 0.0, 'z': world_h - border, 'w': float(world_w), 'h': border, 'kind': 'wall'},
            {'x': 0.0, 'z': 0.0, 'w': float(world_w), 'h': border, 'kind': 'wall'},
            {'x': 0.0, 'z': 0.0, 'w': border, 'h': float(world_h), 'kind': 'wall'},
            {'x': world_w - border, 'z': 0.0, 'w': border, 'h': float(world_h), 'kind': 'wall'},
        ])
        inner_left, inner_bottom = border + 28.0, border + 28.0
        inner_w, inner_h = world_w - (border + 28.0) * 2.0, world_h - (border + 28.0) * 2.0
        add_decor('playfield', inner_left, inner_bottom, inner_w, inner_h, depth=7.12, alpha=0.08)
        if terrain_recipe == 'clustered_biome_fields':
            cluster_count = _generated_runtime_int(controls.get('cluster_count', 5), 5 + (1 if 'tile_generation' in seed_labels else 0), 3)
            spacing = max(180.0, inner_w / max(2, cluster_count))
            centers = []
            plan['formation_signature'] = 'clusters'
            plan['preview_lines'] = ['Clustered top-down biomes', f'{cluster_count} clusters', f'{max(0, cluster_count - 1)} soft corridors • {moisture_bias}']
            for idx in range(cluster_count):
                cx = inner_left + spacing * (0.6 + idx) + rng.randint(-40, 40)
                cz = inner_bottom + inner_h * (0.35 + 0.25 * ((idx % 2) * 2 - 1)) + rng.randint(-50, 50)
                centers.append((cx, cz))
                patch_w = 180.0 + rng.randint(0, 2) * (34.0 if 'height' in noise_channels else 40.0)
                patch_h = 140.0 + rng.randint(0, 2) * (28.0 if 'moisture' in noise_channels else 36.0)
                add_decor('cluster_patch', cx - patch_w * 0.5, cz - patch_h * 0.5, patch_w, patch_h, depth=7.16, alpha=0.16)
                if biome_patch_mode in {'wet_dry_fields', 'clustered_biomes'}:
                    wet_first = moisture_bias in {'wet', 'mixed'} or (idx % 2 == 0 and moisture_bias != 'dry')
                    add_decor('wet_patch' if wet_first else 'dry_patch', cx - patch_w * 0.28, cz - patch_h * 0.22, patch_w * 0.52, 12.0, depth=7.17, alpha=0.18)
                    add_decor('dry_patch' if wet_first else 'wet_patch', cx - patch_w * 0.12, cz + patch_h * 0.14, patch_w * 0.34, 10.0, depth=7.17, alpha=0.14)
                elif 'moisture' in noise_channels:
                    add_decor('cluster_patch', cx - patch_w * 0.25, cz - patch_h * 0.22, patch_w * 0.5, 10.0, depth=7.17, alpha=0.18)
                add_decor('cluster_core', cx - 34.0, cz - 30.0, 68.0, 60.0, depth=7.22, alpha=0.20)
                for _ in range(2):
                    ow = 58.0 + rng.randint(0, 2) * 18.0
                    oh = 48.0 + rng.randint(0, 2) * 16.0
                    ox = cx + rng.randint(-50, 40)
                    oz = cz + rng.randint(-40, 34)
                    add_segment(ox, oz, ow, oh, kind='cluster_obstacle', pickup=False, enemy=False)
                plan['pickups'].append((cx - 12.0, cz - 12.0))
                plan['enemies'].append({'x': cx + 26.0, 'z': cz + 24.0, 'patrol': None, 'speed': 92.0 + idx * 6.0})
            for idx in range(len(centers) - 1):
                ax, az = centers[idx]
                bx, bz = centers[idx + 1]
                add_decor('corridor', min(ax, bx), min(az, bz) + abs(az - bz) * 0.45, abs(ax - bx), 24.0, depth=7.14, alpha=0.14)
            plan['player_spawn'] = (centers[0][0], centers[0][1]) if centers else (inner_left + 80.0, inner_bottom + 80.0)
        elif terrain_recipe == 'room_network_tiles' or runtime_shape in {'room_graph', 'run_sequence', 'hub_and_spokes'}:
            room_count = _generated_runtime_int(controls.get('room_count', controls.get('run_rooms', 10)), 10, 4)
            rooms = []
            cols = max(2, int(math.ceil(math.sqrt(room_count))))
            rows = max(2, int(math.ceil(room_count / cols)))
            cell_w = inner_w / cols
            cell_h = inner_h / rows
            room_idx = 0
            plan['formation_signature'] = 'rooms'
            room_mode_label = 'Hub-and-spokes rooms' if runtime_shape == 'hub_and_spokes' else 'Room network'
            plan['preview_lines'] = [room_mode_label, f'{room_count} rooms', f'{max(0, room_count - 1)} corridor links • {tile_pattern}']
            for row in range(rows):
                for col in range(cols):
                    if room_idx >= room_count:
                        break
                    hub_boost = 1.28 if runtime_shape == 'hub_and_spokes' and room_idx == 0 else 1.0
                    rw = max(90.0, cell_w * (0.55 + rng.random() * 0.18) * hub_boost)
                    rh = max(80.0, cell_h * (0.5 + rng.random() * 0.18) * hub_boost)
                    rx = inner_left + col * cell_w + (cell_w - rw) * 0.5
                    rz = inner_bottom + row * cell_h + (cell_h - rh) * 0.5
                    rooms.append((rx, rz, rw, rh))
                    add_decor('room_floor', rx, rz, rw, rh, depth=7.16, alpha=0.14)
                    if 'tile_texture_generation' in seed_labels:
                        add_decor('room_floor', rx + 8.0, rz + 8.0, max(18.0, rw - 16.0), 6.0, depth=7.17, alpha=0.10)
                    if tile_pattern in {'stripe', 'speckle_stripe'}:
                        stripe_count = 2 if tile_pattern == 'stripe' else 3
                        for stripe_idx in range(stripe_count):
                            stripe_z = rz + 16.0 + stripe_idx * max(18.0, rh / max(3.0, stripe_count + 1))
                            add_decor('room_stripe', rx + 10.0, stripe_z, max(18.0, rw - 20.0), 4.0, depth=7.18, alpha=0.10)
                        if tile_pattern == 'speckle_stripe':
                            add_decor('room_speckle', rx + rw * 0.34, rz + rh * 0.34, 10.0, 10.0, depth=7.18, alpha=0.10)
                            add_decor('room_speckle', rx + rw * 0.62, rz + rh * 0.56, 8.0, 8.0, depth=7.18, alpha=0.10)
                    if runtime_shape == 'hub_and_spokes' and room_idx == 0:
                        add_decor('hub_core', rx + rw * 0.2, rz + rh * 0.2, rw * 0.6, rh * 0.6, depth=7.2, alpha=0.18)
                    wall = 16.0 if 'tile_texture_generation' in seed_labels else 14.0
                    door_w = max(26.0, rw * 0.18)
                    door_h = max(24.0, rh * 0.18)
                    # top / bottom with center door gap
                    add_segment(rx, rz + rh - wall, max(12.0, rw * 0.5 - door_w * 0.5), wall, kind='room_wall')
                    add_segment(rx + rw * 0.5 + door_w * 0.5, rz + rh - wall, max(12.0, rw * 0.5 - door_w * 0.5), wall, kind='room_wall')
                    add_segment(rx, rz, max(12.0, rw * 0.5 - door_w * 0.5), wall, kind='room_wall')
                    add_segment(rx + rw * 0.5 + door_w * 0.5, rz, max(12.0, rw * 0.5 - door_w * 0.5), wall, kind='room_wall')
                    add_segment(rx, rz + wall, wall, max(12.0, rh * 0.5 - door_h * 0.5), kind='room_wall')
                    add_segment(rx, rz + rh * 0.5 + door_h * 0.5, wall, max(12.0, rh * 0.5 - door_h * 0.5), kind='room_wall')
                    add_segment(rx + rw - wall, rz + wall, wall, max(12.0, rh * 0.5 - door_h * 0.5), kind='room_wall')
                    add_segment(rx + rw - wall, rz + rh * 0.5 + door_h * 0.5, wall, max(12.0, rh * 0.5 - door_h * 0.5), kind='room_wall')
                    if room_idx % 2 == 0:
                        plan['pickups'].append((rx + rw * 0.5 - 10.0, rz + rh * 0.5 - 10.0))
                    if room_idx % 3 == 1:
                        plan['enemies'].append({'x': rx + rw * 0.62, 'z': rz + rh * 0.54, 'patrol': None, 'speed': 94.0 + room_idx * 3.0})
                    room_idx += 1
            if runtime_shape == 'hub_and_spokes' and rooms:
                hx, hz, hw, hh = rooms[0]
                hcx, hcz = hx + hw * 0.5, hz + hh * 0.5
                for idx in range(1, len(rooms)):
                    bx, bz, bw, bh = rooms[idx]
                    bcx, bcz = bx + bw * 0.5, bz + bh * 0.5
                    add_decor('corridor', min(hcx, bcx), hcz - 12.0, abs(hcx - bcx) + 24.0, 24.0, depth=7.15, alpha=0.12)
                    add_decor('corridor', bcx - 12.0, min(hcz, bcz), 24.0, abs(hcz - bcz) + 24.0, depth=7.15, alpha=0.12)
            else:
                for idx in range(len(rooms) - 1):
                    ax, az, aw, ah = rooms[idx]
                    bx, bz, bw, bh = rooms[idx + 1]
                    acx, acz = ax + aw * 0.5, az + ah * 0.5
                    bcx, bcz = bx + bw * 0.5, bz + bh * 0.5
                    add_decor('corridor', min(acx, bcx), acz - 10.0, abs(acx - bcx) + 20.0, 20.0, depth=7.15, alpha=0.12)
                    add_decor('corridor', bcx - 10.0, min(acz, bcz), 20.0, abs(acz - bcz) + 20.0, depth=7.15, alpha=0.12)
            if rooms:
                rx, rz, rw, rh = rooms[0]
                plan['player_spawn'] = (rx + rw * 0.5 - 16.0, rz + rh * 0.5 - 16.0)
        elif terrain_recipe == 'road_grid_tiles':
            hub_count = _generated_runtime_int(controls.get('hub_count', 3), 3 + (1 if 'heat' in noise_channels else 0), 2)
            road_segments = _generated_runtime_int(controls.get('road_segments', 8), 8, 4)
            road_w = 42.0
            plan['formation_signature'] = 'roads'
            plan['preview_lines'] = ['Road-grid district', f'{hub_count} hubs', f'{road_segments} district blocks • {lane_cadence} cadence']
            x_positions = [inner_left + (idx + 1) * inner_w / (hub_count + 1) for idx in range(hub_count)]
            z_positions = [inner_bottom + (idx + 1) * inner_h / (hub_count + 1) for idx in range(hub_count)]
            for x in x_positions:
                add_decor('road_band', x - road_w * 0.5, inner_bottom, road_w, inner_h, depth=7.16, alpha=0.16)
            for z in z_positions:
                add_decor('road_band', inner_left, z - road_w * 0.5, inner_w, road_w, depth=7.16, alpha=0.16)
            for idx in range(max(4, road_segments)):
                ox = inner_left + (idx % hub_count) * inner_w / max(1, hub_count) + 54.0
                oz = inner_bottom + ((idx // hub_count) % hub_count) * inner_h / max(1, hub_count) + 54.0
                add_segment(ox, oz, 84.0 + (idx % 3) * 18.0, 64.0 + (idx % 2) * 20.0, kind='district_block', enemy=(idx % 3 == 0))
            for x in x_positions:
                for z in z_positions:
                    plan['pickups'].append((x - 10.0, z - 10.0))
            plan['player_spawn'] = (x_positions[0], z_positions[0]) if x_positions and z_positions else (inner_left + 80.0, inner_bottom + 80.0)
        else:
            obstacle_total = 6 if terrain_recipe == 'open_field_tiles' else 10
            if 'hill_world_fill' in seed_labels:
                obstacle_total = max(4, obstacle_total - 1)
            if terrain_recipe == 'open_field_tiles':
                plan['formation_signature'] = 'open_field'
                plan['preview_lines'] = ['Open-field topdown map', f'{obstacle_total} obstacle pockets', f'wide traversal clearings • {moisture_bias}']
            for idx in range(obstacle_total):
                w = 70.0 + rng.randint(0, 3) * 28.0
                h = 58.0 + rng.randint(0, 3) * 24.0
                x = inner_left + rng.random() * max(120.0, inner_w - w - 20.0)
                z = inner_bottom + rng.random() * max(120.0, inner_h - h - 20.0)
                add_segment(x, z, w, h, kind='obstacle', enemy=(idx % 2 == 0))
            pickup_total = 6 if terrain_recipe == 'open_field_tiles' else 8
            for _ in range(pickup_total):
                plan['pickups'].append((inner_left + 36.0 + rng.random() * max(40.0, inner_w - 72.0), inner_bottom + 36.0 + rng.random() * max(40.0, inner_h - 72.0)))
            plan['player_spawn'] = (inner_left + 80.0, inner_bottom + 80.0)
    return plan


def run_generated_spec_window(spec_path: Path | str, *, smoketest_seconds: float = 0.0) -> dict:
    spec_fp = Path(spec_path).expanduser().resolve()
    if not spec_fp.exists():
        raise FileNotFoundError(f'Generated spec not found: {spec_fp}')
    spec = json.loads(spec_fp.read_text(encoding='utf-8'))
    if ShowBase is None or loadPrcFileData is None or TextNode is None or Filename is None:
        raise RuntimeError('Panda3D runtime is unavailable for generated spec playback.')

    from panda3d.core import CardMaker, ClockObject, Filename as PandaFilename, OrthographicLens

    window = dict(spec.get('window', {}) or {})
    world = dict(spec.get('world', {}) or {})
    player = dict(spec.get('player', {}) or {})
    physics = dict(spec.get('physics', {}) or {})
    style = dict(spec.get('style', {}) or {})
    runtime_recipe = dict(spec.get('runtime_recipe', {}) or {})
    world_blueprint = _generated_runtime_world_blueprint(spec)
    validation_targets = dict(spec.get('validation_targets', {}) or {})
    palette = dict(style.get('palette', {}) or {})
    game_type = str(spec.get('game_type', 'topdown_adventure') or 'topdown_adventure').strip().lower()
    title = str(window.get('title') or spec.get('title') or spec_fp.stem)
    win_w = max(960, int(window.get('w', 1280) or 1280))
    win_h = max(540, int(window.get('h', 720) or 720))
    target_fps = max(30, int(window.get('fps', 60) or 60))
    world_w = max(win_w + 240, int(world.get('w', 2200) or 2200))
    world_h = max(win_h + 120, int(world.get('h', 1400) or 1400))
    toolbar_h = max(0, int((spec.get('toolbar', {}) or {}).get('height', 36) or 36))
    world_floor = 96.0
    world_seed = int(world.get('seed', 1) or 1)
    rng = random.Random(world_seed)
    screenshot_dir = SCREENSHOTS_DIR / 'generated_runtime'
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    screenshot_fp = screenshot_dir / f"{spec_fp.stem}_{int(time.time())}.png"
    receipt_fp = spec_fp.with_name(f"{spec_fp.stem}_runtime_receipt.json")

    bg = _generated_runtime_color(palette, 'bg', (22, 24, 30))
    panel = _generated_runtime_color(palette, 'panel', (48, 62, 76))
    accent = _generated_runtime_color(palette, 'accent', (214, 98, 116))
    accent2 = _generated_runtime_color(palette, 'accent2', (95, 170, 206))
    text_color = _generated_runtime_color(palette, 'text', (232, 236, 244))
    seed_profile = _generated_runtime_seed_profile(world_blueprint)
    bg, panel, accent, accent2, text_color = _generated_runtime_palette_recipe(bg, panel, accent, accent2, text_color, world_blueprint.get('palette_recipe', 'neutral_runtime'), seed_profile)

    loadPrcFileData('', f'window-title {title}')
    loadPrcFileData('', f'win-size {win_w} {win_h}')
    loadPrcFileData('', 'fullscreen 0')
    loadPrcFileData('', 'undecorated 0')
    loadPrcFileData('', 'show-frame-rate-meter 0')
    loadPrcFileData('', f'clock-mode limited\nclock-frame-rate {target_fps}')
    loadPrcFileData('', 'sync-video 0')
    loadPrcFileData('', 'audio-library-name null')
    loadPrcFileData('', 'textures-power-2 none')

    class _GeneratedRuntime(ShowBase):
        def __init__(self):
            super().__init__(windowType='onscreen')
            self.disableMouse()
            self.setBackgroundColor(*bg)
            self.accept('escape', self.request_exit)
            self.accept('h', self.toggle_hud)
            self.accept('arrow_left', self._set_key, ['left', True])
            self.accept('arrow_left-up', self._set_key, ['left', False])
            self.accept('a', self._set_key, ['left', True])
            self.accept('a-up', self._set_key, ['left', False])
            self.accept('arrow_right', self._set_key, ['right', True])
            self.accept('arrow_right-up', self._set_key, ['right', False])
            self.accept('d', self._set_key, ['right', True])
            self.accept('d-up', self._set_key, ['right', False])
            self.accept('arrow_up', self._set_key, ['up', True])
            self.accept('arrow_up-up', self._set_key, ['up', False])
            self.accept('w', self._set_key, ['up', True])
            self.accept('w-up', self._set_key, ['up', False])
            self.accept('arrow_down', self._set_key, ['down', True])
            self.accept('arrow_down-up', self._set_key, ['down', False])
            self.accept('s', self._set_key, ['down', True])
            self.accept('s-up', self._set_key, ['down', False])
            self.accept('space', self._trigger_action)
            self.accept('mouse1', self._trigger_action)
            self.keys = {'left': False, 'right': False, 'up': False, 'down': False}
            self.started_at = time.time()
            self.exit_requested = False
            self.hud_visible = True
            self.screenshot_captured = False
            self.last_error = ''
            self.pickups_collected = 0
            self.enemies_defeated = 0
            self.health = 5
            self._next_shot_time = 0.0
            self._hurt_cooldown = 0.0
            self.player_velocity_z = 0.0
            self.last_move_dir = (1.0, 0.0)
            self.platform_segments: list[tuple[float, float, float, float]] = []
            self.pickups: list[dict] = []
            self.enemies: list[dict] = []
            self.bullets: list[dict] = []
            self.runtime_note = ''
            self.world_blueprint = dict(world_blueprint)
            self.world_plan = _generated_runtime_build_plan(game_type, float(world_w), float(world_h), float(world_floor), self.world_blueprint, runtime_recipe, seed=world_seed)
            self.world_plan['motif_rects'] = _generated_runtime_art_motif_rects(self.world_plan, self.world_blueprint, float(world_w), float(world_h), float(world_floor), world_seed)
            self.decor_nodes = []

            lens = OrthographicLens()
            lens.setFilmSize(win_w, win_h)
            lens.setNearFar(-2000, 2000)
            self.cam.node().setLens(lens)
            self.cam.setPos(win_w * 0.5, -1200.0, win_h * 0.5)
            self.cam.lookAt(win_w * 0.5, 0.0, win_h * 0.5)

            self.world_root = self.render.attachNewNode('generated_world')
            self._build_backdrop()
            self._build_level()
            self._build_hud()
            self.taskMgr.add(self._update_runtime, 'generated_spec_runtime_update')

        def _set_key(self, key: str, value: bool) -> None:
            self.keys[key] = value

        def _trigger_action(self) -> None:
            now = time.time()
            if game_type == 'platformer':
                if self._player_grounded():
                    self.player_velocity_z = float(player.get('jump_v', -600.0) or -600.0)
            elif game_type == 'arena_shooter':
                if now >= self._next_shot_time:
                    self._next_shot_time = now + 0.18
                    self._spawn_bullet()

        def _role_color(self, role: str, alpha: float = 0.2) -> tuple[float, float, float, float]:
            role = str(role or 'field')
            a = max(0.04, min(0.95, float(alpha)))
            if role in {'ground_band', 'road_band', 'road_divider', 'road_sign', 'road_marker', 'road_shoulder'}:
                return (accent2[0], accent2[1], accent2[2], min(0.95, a + 0.08))
            if role in {'cluster_patch', 'room_floor', 'corridor', 'playfield', 'room_stripe', 'room_speckle'}:
                return (panel[0], panel[1] * 1.02, min(1.0, panel[2] * 1.08), a)
            if role in {'wet_patch'}:
                return (accent2[0] * 0.96, min(1.0, accent2[1] * 1.08), min(1.0, accent2[2] * 1.12), min(0.95, a + 0.04))
            if role in {'dry_patch'}:
                return (accent[0], min(1.0, accent[1] * 0.94), accent[2] * 0.88, min(0.95, a + 0.03))
            if role in {'cluster_core', 'hub_core'}:
                return (accent[0], accent[1], accent[2], min(0.95, a + 0.08))
            if role in {'strata_back', 'hill_shadow', 'cave_ceiling', 'cave_pillar', 'cave_chamber', 'strata_vein', 'cave_drip', 'strata_cut', 'cave_exit', 'road_landmark', 'road_debris'}:
                return (panel[0] * 0.85, panel[1] * 0.88, panel[2] * 0.95, min(0.95, a + 0.04))
            if role in {'goal_marker'}:
                return (accent[0], accent[1], accent[2], min(1.0, a + 0.18))
            if role in {'motif_frame', 'motif_grid', 'motif_wave', 'motif_drip', 'motif_noise'}:
                return (accent2[0], accent2[1], accent2[2], min(0.88, a + 0.08))
            return (panel[0], panel[1], panel[2], a)

        def _segment_color(self, kind: str) -> tuple[float, float, float, float]:
            kind = str(kind or 'solid')
            if kind in {'ground', 'road_lane'}:
                return (accent2[0], accent2[1], accent2[2], 0.96)
            if kind in {'road_gate'}:
                return (accent[0], accent[1], accent[2], 0.92)
            if kind in {'strata', 'cave_floor', 'hill', 'strata_bridge', 'strata_ramp', 'open_ground'}:
                return (accent[0], accent[1], accent[2], 0.95)
            if kind in {'room_wall', 'district_block', 'cluster_obstacle', 'obstacle', 'wall'}:
                return (panel[0] * 0.95, panel[1] * 0.95, min(1.0, panel[2] * 1.12), 0.94)
            return (accent2[0], accent2[1], accent2[2], 0.92)

        def _build_backdrop(self) -> None:
            self._make_rect('bg_panel', 0.0, 0.0, float(world_w), float(world_h), panel, y=8.0)
            terrain_recipe = str(self.world_blueprint.get('terrain_recipe', 'generic_fields') or 'generic_fields')
            runtime_shape = str(self.world_blueprint.get('runtime_shape', 'single_map') or 'single_map')
            seed_profile = _generated_runtime_seed_profile(self.world_blueprint)
            texture_rhythm = str(seed_profile.get('texture_rhythm', 'plain') or 'plain')
            moisture_bias = str(seed_profile.get('moisture_bias', 'balanced') or 'balanced')
            layer_density = str(seed_profile.get('layer_density', 'medium') or 'medium')
            lane_cadence = str(seed_profile.get('lane_cadence', 'steady') or 'steady')
            tile_pattern = str(seed_profile.get('tile_pattern', 'plain') or 'plain')
            biome_patch_mode = str(seed_profile.get('biome_patch_mode', 'balanced') or 'balanced')
            transition_pressure = str(seed_profile.get('transition_pressure', 'medium') or 'medium')
            horizon_openness = str(seed_profile.get('horizon_openness', 'medium') or 'medium')
            landmark_density = str(seed_profile.get('landmark_density', 'medium') or 'medium')
            runner_flow = str(seed_profile.get('runner_flow', 'steady') or 'steady')
            stripe_count = max(8, min(26, world_w // (140 if game_type == 'platformer' else 190)))
            if texture_rhythm == 'bands':
                stripe_count += 2
            elif texture_rhythm == 'tile_speckle':
                stripe_count = max(10, stripe_count - 2)
            if layer_density == 'high':
                stripe_count += 2
            elif layer_density == 'low':
                stripe_count = max(6, stripe_count - 1)
            if lane_cadence == 'dense':
                stripe_count += 2
            elif lane_cadence == 'sparse':
                stripe_count = max(6, stripe_count - 2)
            if runtime_shape in {'room_graph', 'hub_and_spokes'}:
                stripe_count = max(6, min(14, world_w // 260))
            for idx in range(int(stripe_count)):
                stripe_w = 54.0 + (idx % 4) * 18.0
                x = idx * (world_w / stripe_count)
                alpha = 0.08 + (idx % 3) * 0.03
                if terrain_recipe in {'surface_sub_deep_layers', 'surface_layers_with_cave_carve'}:
                    alpha += 0.03
                if lane_cadence == 'dense' and idx % 2 == 0:
                    alpha += 0.02
                color = (accent2[0], accent2[1], accent2[2], alpha)
                self._make_rect(f'stripe_{idx}', x, 0.0, stripe_w, float(world_h), color, y=7.5)
                if texture_rhythm == 'tile_speckle' and idx % 2 == 0:
                    self._make_rect(f'speckle_{idx}', x + stripe_w * 0.18, 84.0 + (idx % 5) * 58.0, max(8.0, stripe_w * 0.16), 8.0, (panel[0], panel[1], panel[2], 0.14), y=7.56)
                elif texture_rhythm == 'bands':
                    band_step = 56.0 if layer_density == 'high' else 72.0 if layer_density == 'medium' else 92.0
                    self._make_rect(f'band_{idx}', x, world_floor + 54.0 + (idx % 4) * band_step, stripe_w, 4.0, (accent[0], accent[1], accent[2], 0.08), y=7.56)
                elif texture_rhythm == 'dither':
                    cadence_step = 2 if lane_cadence == 'dense' else 4 if lane_cadence == 'sparse' else 3
                    if idx % cadence_step == 0:
                        self._make_rect(f'dither_{idx}', x + stripe_w * 0.32, 96.0 + (idx % 4) * 52.0, 6.0, 6.0, (accent2[0], accent2[1], accent2[2], 0.10), y=7.56)
            if game_type == 'platformer' and terrain_recipe == 'surface_sub_deep_layers':
                cut_count = 4 if transition_pressure == 'high' else 2
                for idx in range(cut_count):
                    cut_x = 120.0 + idx * (world_w / max(3, cut_count + 1))
                    cut_h = 42.0 + (12.0 if transition_pressure == 'high' else 0.0)
                    self._make_rect(f'strata_cut_{idx}', cut_x, world_floor + 56.0 + (idx % 2) * 34.0, 14.0, cut_h, self._role_color('strata_cut', 0.16), y=7.27)
            if game_type == 'platformer' and terrain_recipe == 'surface_layers_with_cave_carve':
                exit_count = 3 if transition_pressure == 'high' else 2
                for idx in range(exit_count):
                    exit_x = 160.0 + idx * (world_w / max(3, exit_count + 1))
                    self._make_rect(f'cave_exit_{idx}', exit_x, world_floor + 44.0 + (idx % 2) * 28.0, 16.0, 28.0, self._role_color('cave_exit', 0.15), y=7.26)
            if game_type == 'platformer' and terrain_recipe in {'strip_roads_with_surface_bands', 'open_field_side_bands'}:
                cadence = 120.0 if lane_cadence == 'dense' else 220.0 if lane_cadence == 'sparse' else 160.0
                landmark_step = 2 if landmark_density == 'high' else 4 if landmark_density == 'sparse' else 3
                x_land = 64.0
                idx = 0
                while x_land < world_w - 48.0:
                    if idx % landmark_step == 0:
                        self._make_rect(f'runner_landmark_{idx}', x_land, world_floor + 32.0, 18.0, 28.0, self._role_color('road_landmark', 0.14), y=7.24)
                    if terrain_recipe == 'strip_roads_with_surface_bands' and idx % max(2, landmark_step + 1) == 1:
                        self._make_rect(f'runner_debris_{idx}', x_land - 10.0, world_floor + 20.0, 14.0, 6.0, self._role_color('road_debris', 0.12), y=7.22)
                    x_land += cadence * (0.85 if runner_flow == 'high' else 1.0)
                    idx += 1
            if biome_patch_mode in {'wet_dry_fields', 'clustered_biomes', 'field_biomes'}:
                patch_count = 4 if biome_patch_mode == 'wet_dry_fields' else 3
                for idx in range(patch_count):
                    pw = 120.0 + idx * 28.0
                    ph = 82.0 + (idx % 2) * 24.0
                    px = 90.0 + idx * ((world_w - 220.0) / max(1, patch_count))
                    pz = world_floor + 42.0 + (idx % 3) * 58.0
                    wet_first = moisture_bias in {'wet', 'mixed'} and idx % 2 == 0
                    kind = 'wet_patch' if wet_first else 'dry_patch'
                    self._make_rect(f'{kind}_{idx}', px, pz, pw, ph, self._role_color(kind, 0.12 if wet_first else 0.10), y=7.22)
            if runtime_shape in {'room_graph', 'hub_and_spokes'} and tile_pattern in {'stripe', 'speckle_stripe'}:
                stripe_rows = 6 if tile_pattern == 'speckle_stripe' else 4
                for idx in range(stripe_rows):
                    rz = world_floor + 60.0 + idx * 78.0
                    self._make_rect(f'room_stripe_{idx}', 84.0, rz, max(120.0, world_w - 168.0), 4.0, self._role_color('room_stripe', 0.10), y=7.21)
                    if tile_pattern == 'speckle_stripe':
                        self._make_rect(f'room_speckle_{idx}', 120.0 + (idx % 5) * 80.0, rz + 10.0, 12.0, 12.0, self._role_color('room_speckle', 0.10), y=7.22)
            if terrain_recipe in {'strip_roads_with_surface_bands', 'road_grid_tiles'}:
                cadence = 120.0 if lane_cadence == 'dense' else 220.0 if lane_cadence == 'sparse' else 160.0
                x = 48.0
                marker_idx = 0
                while x < world_w - 32.0:
                    self._make_rect(f'road_marker_{marker_idx}', x, world_floor + 46.0, 12.0, 20.0, self._role_color('road_marker', 0.16), y=7.24)
                    if marker_idx % 2 == 0:
                        self._make_rect(f'road_shoulder_{marker_idx}', x - 10.0, world_floor + 24.0, 32.0, 6.0, self._role_color('road_shoulder', 0.11), y=7.23)
                    x += cadence
                    marker_idx += 1
            for idx, decor in enumerate(list(self.world_plan.get('decor_rects', []))):
                kind = str(decor.get('kind', 'field') or 'field')
                color = self._role_color(kind, float(decor.get('alpha', 0.18) or 0.18))
                node = self._make_rect(f'decor_{idx}', float(decor.get('x', 0.0) or 0.0), float(decor.get('z', 0.0) or 0.0), float(decor.get('w', 0.0) or 0.0), float(decor.get('h', 0.0) or 0.0), color, y=float(decor.get('depth', 7.2) or 7.2))
                self.decor_nodes.append(node)
            motif_rects = list(self.world_plan.get('motif_rects', []))
            for idx, decor in enumerate(motif_rects):
                kind = str(decor.get('kind', 'motif_noise') or 'motif_noise')
                color = self._role_color(kind, float(decor.get('alpha', 0.12) or 0.12))
                node = self._make_rect(f'motif_{idx}', float(decor.get('x', 0.0) or 0.0), float(decor.get('z', 0.0) or 0.0), float(decor.get('w', 0.0) or 0.0), float(decor.get('h', 0.0) or 0.0), color, y=float(decor.get('depth', 7.33) or 7.33))
                self.decor_nodes.append(node)
            if terrain_recipe in {'strip_roads_with_surface_bands', 'road_grid_tiles'}:
                self._make_rect('toolbar_glow', 0.0, float(world_h - toolbar_h - 6.0), float(world_w), 6.0, (accent2[0], accent2[1], accent2[2], 0.28), y=7.75)
            self._make_rect('toolbar', 0.0, float(world_h - toolbar_h), float(world_w), float(toolbar_h), (0.05, 0.05, 0.07, 0.95), y=7.8)

        def _build_level(self) -> None:
            size = float(player.get('size', 42) or 42)
            self.player_size = size
            spawn_x, spawn_z = self.world_plan.get('player_spawn') or (float(player.get('x', 160) or 160), float(player.get('y', 160) or 160))
            self.player_node = self._make_rect('player', float(spawn_x), float(spawn_z), size, size, accent)
            self.spawn_point = (float(spawn_x), float(spawn_z))
            self.platform_segments = []
            self.runtime_note = str(self.world_plan.get('note') or ('Arena lane active' if game_type == 'arena_shooter' else 'Top-down lane active'))
            signature = str(self.world_plan.get('formation_signature', '') or '').strip()
            if signature:
                self.runtime_note = f"{self.runtime_note} • {signature}"
            for idx, segment in enumerate(list(self.world_plan.get('segments', []))):
                px = float(segment.get('x', 0.0) or 0.0)
                pz = float(segment.get('z', 0.0) or 0.0)
                pw = float(segment.get('w', 0.0) or 0.0)
                ph = float(segment.get('h', 0.0) or 0.0)
                kind = str(segment.get('kind', 'solid') or 'solid')
                color = self._segment_color(kind)
                node_name = 'platform' if game_type == 'platformer' else 'obstacle'
                self._make_rect(f'{node_name}_{idx}', px, pz, pw, ph, color)
                self.platform_segments.append((px, pz, pw, ph))
            for idx, (gx, gz) in enumerate(list(self.world_plan.get('goal_markers', []))):
                self._make_rect(f'goal_marker_{idx}', float(gx), float(gz), 26.0, 72.0, self._role_color('goal_marker', 0.34), y=-1.5)
            for pickup_x, pickup_z in list(self.world_plan.get('pickups', [])):
                self._spawn_pickup(float(pickup_x), float(pickup_z))
            for enemy in list(self.world_plan.get('enemies', [])):
                self._spawn_enemy(float(enemy.get('x', 120.0) or 120.0), float(enemy.get('z', 120.0) or 120.0), patrol=enemy.get('patrol'), speed=float(enemy.get('speed', 110.0) or 110.0))

        def _build_hud(self) -> None:
            self.hud = OnscreenText(
                text='',
                pos=(-1.28, 0.92),
                scale=0.045,
                fg=text_color,
                align=TextNode.ALeft,
                mayChange=True,
            )
            self.hint = OnscreenText(
                text=('Esc exit  •  H HUD  •  Arrows/WASD move  •  Space jump' if game_type == 'platformer' else 'Esc exit  •  H HUD  •  Arrows/WASD move  •  Space / mouse action'),
                pos=(0.0, -0.95),
                scale=0.04,
                fg=(text_color[0], text_color[1], text_color[2], 0.92),
                align=TextNode.ACenter,
                mayChange=True,
            )
            self._refresh_hud()

        def _make_rect(self, name: str, x: float, z: float, w: float, h: float, color: tuple[float, float, float, float], *, y: float = 0.0):
            cm = CardMaker(name)
            cm.setFrame(0.0, w, 0.0, h)
            node = self.world_root.attachNewNode(cm.generate())
            node.setPos(x, y, z)
            node.setColor(*color)
            try:
                node.setTransparency(True)
            except Exception:
                pass
            return node

        def _spawn_pickup(self, x: float, z: float) -> None:
            node = self._make_rect(f'pickup_{len(self.pickups)}', x, z, 22.0, 22.0, (0.95, 0.9, 0.4, 0.95))
            self.pickups.append({'node': node, 'x': x, 'z': z, 'w': 22.0, 'h': 22.0, 'alive': True})

        def _spawn_enemy(self, x: float, z: float, patrol: tuple[float, float] | None, speed: float = 110.0) -> None:
            node = self._make_rect(f'enemy_{len(self.enemies)}', x, z, 38.0, 38.0, (0.82, 0.28, 0.32, 0.96))
            direction = -1.0 if len(self.enemies) % 2 else 1.0
            self.enemies.append({'node': node, 'x': x, 'z': z, 'w': 38.0, 'h': 38.0, 'speed': speed, 'dir': direction, 'alive': True, 'patrol': patrol})

        def _spawn_bullet(self) -> None:
            px, pz, pw, ph = self._player_bounds()
            dx, dz = self.last_move_dir
            if abs(dx) < 0.05 and abs(dz) < 0.05:
                dx = 1.0
                dz = 0.0
            mag = max(0.001, math.sqrt(dx * dx + dz * dz))
            dx /= mag
            dz /= mag
            node = self._make_rect(f'bullet_{len(self.bullets)}', px + pw * 0.5 - 8.0, pz + ph * 0.5 - 8.0, 16.0, 16.0, (1.0, 0.96, 0.82, 1.0), y=-2.0)
            self.bullets.append({'node': node, 'x': px + pw * 0.5 - 8.0, 'z': pz + ph * 0.5 - 8.0, 'w': 16.0, 'h': 16.0, 'vx': dx * 520.0, 'vz': dz * 520.0, 'alive': True})

        def _player_bounds(self) -> tuple[float, float, float, float]:
            pos = self.player_node.getPos()
            return (float(pos.x), float(pos.z), self.player_size, self.player_size)

        def _player_grounded(self) -> bool:
            px, pz, pw, _ph = self._player_bounds()
            for sx, sz, sw, sh in self.platform_segments:
                top = sz + sh
                if px + pw > sx + 6.0 and px < sx + sw - 6.0 and abs(pz - top) <= 10.0 and self.player_velocity_z >= -20.0:
                    return True
            return False

        def toggle_hud(self) -> None:
            self.hud_visible = not self.hud_visible
            try:
                if self.hud_visible:
                    self.hud.show(); self.hint.show()
                else:
                    self.hud.hide(); self.hint.hide()
            except Exception:
                pass

        def request_exit(self) -> None:
            self.exit_requested = True

        def _refresh_hud(self) -> None:
            recipe = runtime_recipe.get('layout_bias', 'balanced')
            source_titles = ', '.join(list(runtime_recipe.get('source_titles', []))[:2]) or 'MatrixCore baseline'
            bp_recipe = str(self.world_blueprint.get('terrain_recipe', 'generic_fields') or 'generic_fields')
            bp_shape = str(self.world_blueprint.get('runtime_shape', 'single_map') or 'single_map')
            bp_summary = str(self.world_blueprint.get('summary', '') or '').strip()
            status = f"{title}\nLane: {game_type}  •  Recipe: {recipe}\nBlueprint: {bp_recipe} / {bp_shape}\nRuntime: {self.runtime_note}\nHealth: {self.health}  •  Pickups: {self.pickups_collected}  •  Defeated: {self.enemies_defeated}\nSource: {source_titles}"
            if bp_summary:
                status += f"\nWorld: {bp_summary}"
            preview_lines = list(self.world_plan.get('preview_lines', []) or [])[:3]
            if preview_lines:
                status += "\nPreview: " + " • ".join(str(x) for x in preview_lines if str(x).strip())
            self.hud.setText(status)

        def _capture_runtime_screenshot(self) -> None:
            if self.screenshot_captured:
                return
            try:
                self.win.saveScreenshot(PandaFilename.from_os_specific(str(screenshot_fp)))
                self.screenshot_captured = screenshot_fp.exists()
            except Exception as exc:
                self.last_error = str(exc)

        def _clamp_player(self) -> None:
            x, z, w, h = self._player_bounds()
            x = min(max(0.0, x), world_w - w)
            z = min(max(0.0, z), world_h - h)
            self.player_node.setPos(x, 0.0, z)

        def _topdown_obstacle_pushout(self, new_x: float, new_z: float) -> tuple[float, float]:
            candidate = (new_x, new_z, self.player_size, self.player_size)
            for ox, oz, ow, oh in self.platform_segments:
                obstacle = (ox, oz, ow, oh)
                if not _generated_runtime_bounds_intersect(candidate, obstacle):
                    continue
                old_x, old_z, _, _ = self._player_bounds()
                if not _generated_runtime_bounds_intersect((old_x, new_z, self.player_size, self.player_size), obstacle):
                    new_x = old_x
                if not _generated_runtime_bounds_intersect((new_x, old_z, self.player_size, self.player_size), obstacle):
                    new_z = old_z
                candidate = (new_x, new_z, self.player_size, self.player_size)
            return new_x, new_z

        def _update_topdown_player(self, dt: float) -> None:
            move_x = float(self.keys['right']) - float(self.keys['left'])
            move_z = float(self.keys['up']) - float(self.keys['down'])
            if abs(move_x) > 0.01 or abs(move_z) > 0.01:
                mag = max(0.001, math.sqrt(move_x * move_x + move_z * move_z))
                move_x /= mag
                move_z /= mag
                self.last_move_dir = (move_x, move_z)
            speed = float(player.get('speed', 260.0) or 260.0)
            old_x, old_z, _w, _h = self._player_bounds()
            new_x = old_x + move_x * speed * dt
            new_z = old_z + move_z * speed * dt
            new_x, new_z = self._topdown_obstacle_pushout(new_x, new_z)
            self.player_node.setPos(new_x, 0.0, new_z)
            self._clamp_player()

        def _update_platformer_player(self, dt: float) -> None:
            move_x = float(self.keys['right']) - float(self.keys['left'])
            speed = float(player.get('speed', 300.0) or 300.0)
            x, z, w, h = self._player_bounds()
            x += move_x * speed * dt
            self.player_velocity_z += float(physics.get('gravity', 1220.0) or 1220.0) * dt
            z -= self.player_velocity_z * dt
            landed = False
            for sx, sz, sw, sh in self.platform_segments:
                top = sz + sh
                was_above = (self.player_node.getZ() >= top - 2.0)
                crosses = z <= top <= self.player_node.getZ() + 2.0
                overlaps = x + w > sx + 6.0 and x < sx + sw - 6.0
                if self.player_velocity_z >= 0.0 and overlaps and was_above and crosses:
                    z = top
                    self.player_velocity_z = 0.0
                    landed = True
                    break
            if z < -220.0:
                x, z = self.spawn_point
                self.player_velocity_z = 0.0
                self.health = max(1, self.health - 1)
            self.player_node.setPos(min(max(0.0, x), world_w - w), 0.0, min(max(0.0, z), world_h - h))
            if landed:
                self.last_move_dir = (1.0 if move_x >= 0.0 else -1.0, 0.0)
            elif abs(move_x) > 0.01:
                self.last_move_dir = (1.0 if move_x >= 0.0 else -1.0, 0.0)

        def _update_pickups(self) -> None:
            player_bounds = self._player_bounds()
            for pickup in self.pickups:
                if not pickup['alive']:
                    continue
                if _generated_runtime_bounds_intersect(player_bounds, (pickup['x'], pickup['z'], pickup['w'], pickup['h'])):
                    pickup['alive'] = False
                    pickup['node'].hide()
                    self.pickups_collected += 1
                    self._refresh_hud()

        def _update_enemies(self, dt: float) -> None:
            px, pz, pw, ph = self._player_bounds()
            player_cx = px + pw * 0.5
            player_cz = pz + ph * 0.5
            if self._hurt_cooldown > 0.0:
                self._hurt_cooldown = max(0.0, self._hurt_cooldown - dt)
            for enemy in self.enemies:
                if not enemy['alive']:
                    continue
                ex = float(enemy['x'])
                ez = float(enemy['z'])
                if game_type == 'platformer':
                    patrol = enemy.get('patrol')
                    ex += float(enemy['dir']) * float(enemy['speed']) * dt
                    if patrol is not None:
                        min_x, max_x = patrol
                        if ex <= min_x or ex >= max_x:
                            enemy['dir'] *= -1.0
                            ex = min(max(ex, min_x), max_x)
                else:
                    dx = player_cx - (ex + enemy['w'] * 0.5)
                    dz = player_cz - (ez + enemy['h'] * 0.5)
                    dist = max(0.001, math.sqrt(dx * dx + dz * dz))
                    if dist > 6.0:
                        ex += dx / dist * float(enemy['speed']) * dt
                        ez += dz / dist * float(enemy['speed']) * dt
                enemy['x'] = ex
                enemy['z'] = ez
                enemy['node'].setPos(ex, 0.0, ez)
                if _generated_runtime_bounds_intersect(self._player_bounds(), (ex, ez, enemy['w'], enemy['h'])) and self._hurt_cooldown <= 0.0:
                    self._hurt_cooldown = 0.8
                    self.health = max(0, self.health - 1)
                    self._refresh_hud()
                    if self.health <= 0:
                        self.request_exit()

        def _update_bullets(self, dt: float) -> None:
            if game_type != 'arena_shooter':
                return
            for bullet in self.bullets:
                if not bullet['alive']:
                    continue
                bullet['x'] += bullet['vx'] * dt
                bullet['z'] += bullet['vz'] * dt
                bullet['node'].setPos(bullet['x'], -2.0, bullet['z'])
                if bullet['x'] < -40.0 or bullet['x'] > world_w + 40.0 or bullet['z'] < -40.0 or bullet['z'] > world_h + 40.0:
                    bullet['alive'] = False
                    bullet['node'].hide()
                    continue
                bullet_bounds = (bullet['x'], bullet['z'], bullet['w'], bullet['h'])
                for enemy in self.enemies:
                    if not enemy['alive']:
                        continue
                    enemy_bounds = (enemy['x'], enemy['z'], enemy['w'], enemy['h'])
                    if _generated_runtime_bounds_intersect(bullet_bounds, enemy_bounds):
                        bullet['alive'] = False
                        bullet['node'].hide()
                        enemy['alive'] = False
                        enemy['node'].hide()
                        self.enemies_defeated += 1
                        self._refresh_hud()
                        break

        def _update_camera(self) -> None:
            px, pz, pw, ph = self._player_bounds()
            target_x = min(max(px + pw * 0.5, win_w * 0.5), world_w - win_w * 0.5)
            if game_type == 'platformer':
                preferred_z = min(max(pz + ph * 0.4, win_h * 0.38), world_h - win_h * 0.42)
                target_z = min(max(preferred_z, win_h * 0.38), world_h - win_h * 0.38)
            else:
                target_z = min(max(pz + ph * 0.5, win_h * 0.5), world_h - win_h * 0.5)
            self.cam.setPos(target_x, -1200.0, target_z)
            self.cam.lookAt(target_x, 0.0, target_z)

        def _update_runtime(self, task):
            dt = min(0.05, ClockObject.getGlobalClock().getDt())
            if game_type == 'platformer':
                self._update_platformer_player(dt)
            else:
                self._update_topdown_player(dt)
            self._update_pickups()
            self._update_enemies(dt)
            self._update_bullets(dt)
            self._update_camera()
            self._refresh_hud()
            if not self.screenshot_captured and (time.time() - self.started_at) >= 0.55:
                self._capture_runtime_screenshot()
            if self.exit_requested:
                self.userExit()
                return task.done
            if smoketest_seconds > 0.0 and (time.time() - self.started_at) >= smoketest_seconds:
                self.request_exit()
            return task.cont

    runtime = None
    start_time = time.time()
    status = 'error'
    error_message = ''
    try:
        runtime = _GeneratedRuntime()
        try:
            runtime.run()
            status = 'ok'
        except SystemExit as exc:
            code = getattr(exc, 'code', 0)
            if code in (0, None):
                status = 'ok'
            else:
                error_message = str(exc)
                raise
    except Exception as exc:
        error_message = str(exc)
        raise
    finally:
        payload = {
            'spec_path': str(spec_fp),
            'title': title,
            'game_type': game_type,
            'status': status,
            'error': error_message or getattr(runtime, 'last_error', ''),
            'elapsed_seconds': round(time.time() - start_time, 3),
            'screenshot': str(screenshot_fp) if screenshot_fp.exists() else '',
            'screenshot_captured': bool(screenshot_fp.exists()),
            'validation_targets': validation_targets,
            'runtime_recipe': runtime_recipe,
            'pickups_collected': int(getattr(runtime, 'pickups_collected', 0) or 0),
            'enemies_defeated': int(getattr(runtime, 'enemies_defeated', 0) or 0),
            'health_remaining': int(getattr(runtime, 'health', 0) or 0),
            'smoketest_seconds': float(smoketest_seconds or 0.0),
        }
        try:
            receipt_fp.write_text(json.dumps(payload, indent=2), encoding='utf-8')
        except Exception:
            pass
        try:
            if runtime is not None:
                runtime.destroy()
        except Exception:
            pass
    return payload

# ---------------------------------------------------------------------------
# Runtime lock / dependency drift guard
# ---------------------------------------------------------------------------
RUNTIME_TARGET_PYTHON = "3.12.x"
RUNTIME_TARGET_PYTHON_MAJOR_MINOR = (3, 12)
RUNTIME_TARGET_PANDA3D = "1.10.15"
RUNTIME_COMPAT_PANDA3D_PY313 = "1.10.16"
RUNTIME_LOCK_NOTES = [
    "Windows target runtime is Python 3.12.x with Panda3D 1.10.15.",
    "Python 3.13 test environments use Panda3D 1.10.16 only because Panda3D 1.10.15 has no cp313 wheel.",
    "Do not convert project installers or generated handoffs back to unpinned `pip install panda3d`.",
    "Pygame and pydub audio bridges are verified separately and are not replaced by this guard.",
]


def _runtime_import_version(module_name: str) -> dict:
    data = {"present": False, "version": None, "error": ""}
    try:
        module = __import__(module_name)
        data["present"] = True
        data["version"] = str(getattr(module, "__version__", "") or "") or None
    except Exception as exc:
        data["error"] = f"{type(exc).__name__}: {exc}"
    if data["present"] and not data["version"]:
        try:
            from importlib import metadata as importlib_metadata
            data["version"] = importlib_metadata.version(module_name)
        except Exception:
            pass
    return data


def build_runtime_lock_report() -> dict:
    py_major_minor = (int(sys.version_info.major), int(sys.version_info.minor))
    packages = {
        "panda3d": _runtime_import_version("panda3d"),
        "direct": _runtime_import_version("direct"),
        "pygame": _runtime_import_version("pygame"),
        "PIL": _runtime_import_version("PIL"),
        "pydub": _runtime_import_version("pydub"),
        "numpy": _runtime_import_version("numpy"),
        "reportlab": _runtime_import_version("reportlab"),
    }
    panda_core_version = None
    try:
        from panda3d.core import PandaSystem
        panda_core_version = str(PandaSystem.getVersionString())
        packages["panda3d"]["version"] = panda_core_version
    except Exception as exc:
        packages["panda3d"]["core_error"] = f"{type(exc).__name__}: {exc}"

    expected_panda = RUNTIME_TARGET_PANDA3D
    if py_major_minor >= (3, 13):
        expected_panda = RUNTIME_COMPAT_PANDA3D_PY313

    warnings: list[str] = []
    if py_major_minor != RUNTIME_TARGET_PYTHON_MAJOR_MINOR:
        warnings.append(
            f"Runtime is Python {py_major_minor[0]}.{py_major_minor[1]}, but shipped Windows target is {RUNTIME_TARGET_PYTHON}."
        )
    panda_version = packages.get("panda3d", {}).get("version")
    if panda_version and str(panda_version) != expected_panda:
        warnings.append(f"Panda3D version is {panda_version}; expected {expected_panda} for this Python runtime.")
    if not packages.get("pygame", {}).get("present"):
        warnings.append("pygame is not importable; audio/pygame bridge modes may fail until requirements are installed.")
    if not packages.get("pydub", {}).get("present"):
        warnings.append("pydub is not importable; Vector Wars audio helper fallback may be limited until requirements are installed.")

    return {
        "runtime_lock": "GLITCHED_MATRIX_RUNTIME_LOCK_PASS5",
        "timestamp_unix": round(time.time(), 3),
        "python": {
            "version": sys.version.split()[0],
            "executable": str(Path(sys.executable).resolve()),
            "major_minor": list(py_major_minor),
            "target_major_minor": list(RUNTIME_TARGET_PYTHON_MAJOR_MINOR),
            "target_label": RUNTIME_TARGET_PYTHON,
            "is_target_windows_runtime": py_major_minor == RUNTIME_TARGET_PYTHON_MAJOR_MINOR,
        },
        "panda3d": {
            "expected_for_this_python": expected_panda,
            "target_windows": RUNTIME_TARGET_PANDA3D,
            "python_313_compat": RUNTIME_COMPAT_PANDA3D_PY313,
        },
        "packages": packages,
        "audio_bridges": {
            "pygame_present": bool(packages.get("pygame", {}).get("present")),
            "pydub_present": bool(packages.get("pydub", {}).get("present")),
            "policy": "Do not replace pygame/pydub bridges while locking Panda3D; only verify their imports.",
        },
        "install_policy": {
            "root_requirements": "Uses environment markers: Panda3D 1.10.15 for Python < 3.13, Panda3D 1.10.16 for Python >= 3.13.",
            "windows_default": "Install with py -3.12 whenever available.",
            "no_unpinned_panda3d": True,
        },
        "notes": list(RUNTIME_LOCK_NOTES),
        "warnings": warnings,
    }


def write_runtime_lock_report(log_path: Path | str | None = None) -> dict:
    report = build_runtime_lock_report()
    try:
        output = Path(log_path) if log_path is not None else (DATA_ROOT_DIR / "logs" / "runtime_lock_report.json")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    except Exception as exc:
        report.setdefault("warnings", []).append(f"Could not write runtime lock report: {type(exc).__name__}: {exc}")
    return report


# Keep this override at the end so future app-generated installers do not regress
# back to plain `python -m pip install panda3d` or unpinned Panda3D.
def write_unified_dependency_bootstrap(requirements_path: Path | str, installer_path: Path | str) -> None:
    req = Path(requirements_path)
    bat = Path(installer_path)
    req.write_text("\n".join(UNIFIED_REQUIREMENTS) + "\n", encoding="utf-8")
    bat.write_text(
        "@echo off\n"
        "setlocal EnableExtensions\n"
        "cd /d \"%~dp0\"\n"
        "echo Installing GLITCHED MATRIX Prototype Lab unified dependencies...\n"
        "echo Target runtime: Windows 10+ / Python 3.12.x / Panda3D 1.10.15\n"
        "echo Python 3.13 test environments use Panda3D 1.10.16 only as a compatibility fallback.\n"
        "echo.\n"
        "set \"PYLAUNCH=\"\n"
        "where py >nul 2>nul && set \"PYLAUNCH=py -3.12\"\n"
        "if not defined PYLAUNCH where python >nul 2>nul && set \"PYLAUNCH=python\"\n"
        "if not defined PYLAUNCH (\n"
        "    echo Python was not found. Install Python 3.12.x from python.org, then run this again.\n"
        "    goto FAIL\n"
        ")\n"
        "%PYLAUNCH% -c \"import sys; print('Using Python', sys.version.split()[0]); raise SystemExit(0 if sys.version_info[:2] == (3, 12) else 12)\"\n"
        "if errorlevel 12 (\n"
        "    echo.\n"
        "    echo WARNING: This project targets Python 3.12.x on Windows.\n"
        "    echo The install will continue only if requirements markers can select a compatible Panda3D wheel.\n"
        "    echo.\n"
        ")\n"
        "%PYLAUNCH% -m pip install --upgrade pip setuptools wheel\n"
        "if errorlevel 1 goto FAIL\n"
        "%PYLAUNCH% -m pip install --prefer-binary -r requirements.txt\n"
        "if errorlevel 1 goto FAIL\n"
        "echo.\n"
        "%PYLAUNCH% -c \"import pygame; import panda3d; from panda3d.core import PandaSystem; print('pygame bridge OK'); print('Panda3D', PandaSystem.getVersionString())\"\n"
        "if errorlevel 1 goto FAIL\n"
        "echo.\n"
        "echo Done. Press any key to exit.\n"
        "pause >nul\n"
        "exit /b 0\n"
        ":FAIL\n"
        "echo.\n"
        "echo Dependency installation failed.\n"
        "pause >nul\n"
        "exit /b 1\n",
        encoding="utf-8",
    )
