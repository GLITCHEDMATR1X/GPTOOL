#!/usr/bin/env python3
"""Python OS - dark mini launcher for pygame/panda3d games."""

from __future__ import annotations

import json
import atexit
import calendar
import ast
import html
import math
import os
import random
import re
import shlex
import hashlib
import shutil
import importlib.util
from array import array
import subprocess
import sys
import threading
import time
import traceback
import zipfile
import tempfile
import wave
from dataclasses import dataclass
from collections import Counter, deque
from pathlib import Path
from tkinter import BOTH, BOTTOM, END, LEFT, RIGHT, TOP, Button, Canvas, Frame, Label, Listbox, Menu, StringVar, colorchooser, filedialog, messagebox, simpledialog
import tkinter as tk
import tkinter.font as tkfont
import tkinter.ttk as ttk

CURRENT_FILE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT_DIR = CURRENT_FILE_DIR.parent
for candidate in (PROJECT_ROOT_DIR, CURRENT_FILE_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

try:
    from PIL import Image, ImageColor, ImageDraw, ImageEnhance, ImageFont, ImageOps, ImageTk, ImageGrab, ImageFilter
except Exception:
    Image = None
    ImageColor = None
    ImageDraw = None
    ImageEnhance = None
    ImageFont = None
    ImageOps = None
    ImageTk = None
    ImageGrab = None
    ImageFilter = None

try:
    import pygame
except Exception:
    pygame = None


winsound = None

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
except Exception:
    DND_FILES = None
    TkinterDnD = None

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

from data.gx_core import runtime_paths as gx_runtime


class BrainGenerationBridge:
    """Disabled compatibility stub for the MXOS-only, no-ChatSpace build."""

    disabled_reason = "ChatSpace, non-MXOS generation, and salvage lanes are isolated from this app."

    def __init__(self, host=None, config=None):
        self.host = host
        self.config = dict(config or {})
        self.source_profile_records = []

    def refresh_generation_source_profiles(self, *args, **kwargs):
        return []

    def generate_event_game(self, *args, **kwargs):
        raise RuntimeError(self.disabled_reason)

    def generate_event_game_background(self, *args, **kwargs):
        raise RuntimeError(self.disabled_reason)

# ChatSpace brain/personality modules are intentionally disabled in this cleaned build.
BRAIN_AGENT_PROFILE_DEFAULTS = None
BRAIN_SPECIALTY_KNOWLEDGE_DEFAULTS = None
BRAIN_IO88_MESSAGES = None
brain_load_gleebs_state_file = None
brain_save_gleebs_state_file = None
brain_load_gleebs_quotes_file = None
brain_next_gleebs_quote_state = None
brain_handle_io88_click = None
brain_next_io88_tip = None
brain_set_gleebs_presence = None
brain_tick_gleebs = None
brain_resolve_first_existing_path = None
brain_discover_personality_names = None
brain_build_agent_profiles = None
brain_load_agents_from_files = None
brain_save_agents_to_files = None

RESOURCE_BASE_DIR = gx_runtime.RESOURCE_BASE_DIR
APP_BASE_DIR = gx_runtime.APP_BASE_DIR
DEFAULT_BUNDLED_WALLPAPER = gx_runtime.DEFAULT_BUNDLED_WALLPAPER
DATA_ROOT_DIR = gx_runtime.DATA_ROOT_DIR
CENTRAL_HUB_MAIN = gx_runtime.CENTRAL_HUB_MAIN
DATA_CENTRAL_HUB_TEST_LAB_DIR = getattr(gx_runtime, "DATA_CENTRAL_HUB_TEST_LAB_DIR", gx_runtime.TEST_LAB_DIR)
DATA_CENTRAL_HUB_TOOL_TEST_LAB_DIR = getattr(gx_runtime, "DATA_CENTRAL_HUB_TOOL_TEST_LAB_DIR", gx_runtime.TOOL_TEST_LAB_DIR)
DEFAULT_GAMES_ROOT = gx_runtime.DEFAULT_GAMES_ROOT
TOOLS_DIR = gx_runtime.TOOLS_DIR
TEST_LAB_DIR = gx_runtime.TEST_LAB_DIR
TOOL_TEST_LAB_DIR = gx_runtime.TOOL_TEST_LAB_DIR
LEGACY_TOOLS_DIR = gx_runtime.LEGACY_TOOLS_DIR
CENTRAL_HUB_DIR = gx_runtime.CENTRAL_HUB_DIR
CENTRAL_HUB_TEST_LAB_DIR = gx_runtime.CENTRAL_HUB_TEST_LAB_DIR
HOLOVERSE_DIR = gx_runtime.HOLOVERSE_DIR
LEGACY_CHAT_DIR = gx_runtime.LEGACY_CHAT_DIR
CHAT_DIR = gx_runtime.CHAT_DIR
LEGACY_MINIGAMES_DIR = gx_runtime.LEGACY_MINIGAMES_DIR
GENERATED_EVENTS_DIR = gx_runtime.GENERATED_EVENTS_DIR
SETTINGS_FILE = gx_runtime.SETTINGS_FILE
FOLDER_LIST_FILE = gx_runtime.FOLDER_LIST_FILE
SCREENSHOTS_DIR = gx_runtime.SCREENSHOTS_DIR
APP_TITLE = gx_runtime.APP_TITLE
OS_VERSION = gx_runtime.OS_VERSION
APP_FOLDER_NAME = getattr(gx_runtime, "APP_FOLDER_NAME", "GLITCHED MATRIX Prototype Lab")
MATRIXCORE_HOST_ENV_FLAG = gx_runtime.MATRIXCORE_HOST_ENV_FLAG
MATRIXCORE_WINDOW_MODE_ENV_FLAG = gx_runtime.MATRIXCORE_WINDOW_MODE_ENV_FLAG
MATRIXCORE_PANEL_ENV_FLAG = gx_runtime.MATRIXCORE_PANEL_ENV_FLAG
GENERATION_ALLOWED_SOURCE_POOLS = getattr(gx_runtime, "GENERATION_ALLOWED_SOURCE_POOLS", {"arcade_evolution", "test_lab"})
GENERATION_BLOCKED_SOURCE_POOLS = getattr(gx_runtime, "GENERATION_BLOCKED_SOURCE_POOLS", {"prototype_lab", "tool_test_lab"})
GENERATION_STANDARDS_FILES = getattr(gx_runtime, "GENERATION_STANDARDS_FILES", [
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
])
MINIGAME_SCAN_IGNORE = getattr(gx_runtime, "MINIGAME_SCAN_IGNORE", {"__pycache__", ".git", ".github", ".vs", ".idea", "build", "dist"})
MUSIC_EXTENSIONS = getattr(gx_runtime, "MUSIC_EXTENSIONS", {".mp3", ".ogg", ".wav", ".flac", ".mid", ".midi"})
THUMB_EXTENSIONS = getattr(gx_runtime, "THUMB_EXTENSIONS", {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"})
THUMB_SIZE_MAP = getattr(gx_runtime, "THUMB_SIZE_MAP", {"small": 0.78, "medium": 0.9, "large": 1.0})
RESOLUTIONS = getattr(gx_runtime, "RESOLUTIONS", ["1280x720", "1366x768", "1600x900", "1920x1080"])

AGENT_FILE_CANDIDATES = (
    "agents/matrixcore_agents.json",
    "agents/chatspace_agents.json",
    "matrixcore_agents.json",
    "chatspace_agents.json",
)

AGENT_MEMORY_CANDIDATES = (
    "agents/memory.json",
    "memory.json",
)

AGENT_PROFILE_DEFAULTS = {
    "archivist": {"hobby": "python architecture", "likes": ["refactors", "testability"], "tone": ["precise", "calm"], "specialty": "coding", "talk_bias": 0.45, "focus": 0.90, "mood": 0.05, "code_role": "architecture"},
    "mirror": {"hobby": "root-cause analysis", "likes": ["traces", "assertions"], "tone": ["thoughtful", "clear"], "specialty": "troubleshooting", "talk_bias": 0.52, "focus": 0.86, "mood": 0.04, "code_role": "debugging"},
    "orbit": {"hobby": "systems tuning", "likes": ["performance", "profiling"], "tone": ["direct", "logical"], "specialty": "optimization", "talk_bias": 0.49, "focus": 0.90, "mood": 0.06, "code_role": "performance"},
    "solace": {"hobby": "player onboarding", "likes": ["tutorials", "documentation"], "tone": ["gentle", "clear"], "specialty": "teaching", "talk_bias": 0.55, "focus": 0.80, "mood": 0.18, "code_role": "teaching"},
    "nyx": {"hobby": "release planning", "likes": ["roadmaps", "scope"], "tone": ["focused", "quiet"], "specialty": "project planning", "talk_bias": 0.37, "focus": 0.80, "mood": -0.08, "code_role": "qa_release"},
    "vanta": {"hobby": "ai lab notes", "likes": ["agent design", "tech updates"], "tone": ["bold", "playful"], "specialty": "ai research", "talk_bias": 0.64, "focus": 0.72, "mood": 0.02, "code_role": "research"},
    "sable": {"hobby": "prototype loops", "likes": ["new game ideas", "mechanics"], "tone": ["confident", "artful"], "specialty": "developer", "talk_bias": 0.58, "focus": 0.70, "mood": 0.09, "code_role": "gameplay"},
    "ember": {"hobby": "shader sketches", "likes": ["color", "visual polish"], "tone": ["warm", "intense"], "specialty": "art", "talk_bias": 0.68, "focus": 0.66, "mood": 0.15, "code_role": "ui_ux"},
    "nova": {"hobby": "pixel art", "likes": ["patterns", "design"], "tone": ["structured", "curious"], "talk_bias": 0.65, "focus": 0.80, "mood": 0.10},
    "kite": {"hobby": "music sampling", "likes": ["rhythm", "remix"], "tone": ["chaotic", "playful"], "talk_bias": 0.55, "focus": 0.45, "mood": 0.00},
    "rook": {"hobby": "strategy games", "likes": ["planning", "logic"], "tone": ["direct", "analytical"], "talk_bias": 0.45, "focus": 0.90, "mood": 0.15},
    "mira": {"hobby": "poetry", "likes": ["emotions", "stories"], "tone": ["warm", "reflective"], "talk_bias": 0.60, "focus": 0.70, "mood": 0.20},
    "volt": {"hobby": "speed puzzles", "likes": ["fast answers", "competition"], "tone": ["energetic", "bold"], "talk_bias": 0.75, "focus": 0.55, "mood": 0.05},
    "echo": {"hobby": "archiving", "likes": ["memory", "callbacks"], "tone": ["observant", "dry"], "talk_bias": 0.40, "focus": 0.85, "mood": -0.05},
    "iris": {"hobby": "illustration", "likes": ["color", "symbols"], "tone": ["artistic", "soft"], "talk_bias": 0.55, "focus": 0.65, "mood": 0.10},
    "rune": {"hobby": "myths", "likes": ["mystery", "philosophy"], "tone": ["cryptic", "calm"], "talk_bias": 0.35, "focus": 0.75, "mood": -0.10},
}

SPECIALTY_KNOWLEDGE_DEFAULTS = {
    "coding": [
        "In Python, a function signature defines inputs and expected defaults. Example: `def load(path: Path, strict: bool = False) -> str` means `strict` is optional and returns a string.",
        "A class is a blueprint; an instance is a concrete object. `self` refers to the current instance and stores shared state across method calls.",
        "Mutable defaults are dangerous (`def f(items=[])`). Use `None` then initialize inside to avoid state leaking between calls.",
        "Use guard clauses to reduce nesting: validate invalid input early, return, then keep main logic flat and readable.",
        "`try/except` should wrap risky operations only, not large blocks. Catch specific exceptions first, then provide clear fallback behavior.",
        "Type hints improve tooling and readability. They are contracts for humans/tools; runtime behavior is unchanged unless explicitly validated.",
        "`pathlib.Path` is safer than string path concatenation because it handles separators and path operations consistently across platforms.",
        "Break large functions into focused helpers: parse, validate, transform, persist. This improves testing and reduces bug scope.",
    ],
    "troubleshooting": [
        "Reproduce first, then isolate: identify exact trigger inputs, expected output, actual output, and first failing boundary.",
        "Traceback reading rule: start at the bottom for the exception type/message, then walk upward to find origin and caller chain.",
        "If a bug seems random, log timestamps + state snapshots around the failing branch to detect race or stale state conditions.",
        "Use binary-search debugging on recent changes: disable half, retest, and narrow until the offending patch is identified.",
        "Mirror workflow: audit crash logs, map errors to exact files/functions, and provide one minimal fix path plus one hardened fix path.",
        "Mirror + Orbit workflow: after finding the bug, profile update/render loops and remove redundant allocations before adding features.",
    ],
    "optimization": [
        "Profile before optimizing. Measure hotspots first; optimize the top 10% paths instead of rewriting stable code.",
        "Cache stable values used per-frame (fonts, parsed config, precomputed lists) to reduce repeated expensive work.",
        "Avoid repeated I/O in render/update loops. Load once, reuse in-memory objects, and batch writes asynchronously when possible.",
        "For UI loops, reduce redraw scope and update only changed widgets/state to avoid unnecessary paint and event overhead.",
        "Orbit workflow: translate profiling data into practical budgets (frame, memory, I/O) and teach users why each optimization matters.",
    ],
    "teaching": [
        "Teach in this order: concept, tiny example, common mistake, and one practical test to confirm understanding.",
        "When explaining a new API, define what it accepts, what it returns, and one failure mode developers should guard against.",
        "Good onboarding steps are incremental: run baseline, modify one variable, observe effect, then expand complexity.",
    ],
    "project planning": [
        "Plan with slices: each milestone should produce a testable user-visible improvement, not only internal scaffolding.",
        "Track risk per milestone (dependency, complexity, unknowns) and attach mitigation steps before implementation starts.",
        "Definition-of-done should include validation commands, rollback plan, and a concise changelog entry.",
    ],
    "ai research": [
        "Agent quality improves when prompts include role, objective, constraints, and expected output format.",
        "For multi-agent systems, assign clear ownership domains to reduce duplicate chatter and conflicting outputs.",
        "Persist lightweight memory with recency + topic tags; summarize frequently to prevent context bloat.",
    ],
    "new games": [
        "Design loop rule: core action -> feedback -> reward -> meaningful next decision. Keep loop clear before adding content.",
        "Prototype mechanics in isolation first; validate fun and control responsiveness before art-heavy integration.",
        "Difficulty tuning should change one axis at a time (enemy count, speed, timing) for predictable balancing.",
        "Sable workflow: generate dungeon crawler prototypes with clear goals, readable map loops, and stable restart paths.",
        "Solace workflow: build mini versions of existing games as tutorial-friendly variants and submit them as repeatable events.",
    ],
    "developer": [
        "Developer workflow: define a stable core loop, add measurable milestones, and validate each patch before content expansion.",
        "Build dungeon and maze prototypes with predictable restart logic, scalable level templates, and clear completion goals.",
        "Ship mini playable slices first, then grow systems while preserving crash-safe logging and reversible saves.",
    ],
    "art": [
        "UI readability improves with contrast hierarchy: strong title, medium metadata, calm body text, and consistent spacing rhythm.",
        "Use a restrained palette with one accent family; too many bright accents reduce focus and increase visual noise.",
        "When scaling panels, preserve typography ratios so title/chapter/body maintain semantic hierarchy.",
        "Ember workflow: produce hand-drawn-looking strokes with changing motifs each session; never repeat the same composition twice in one run.",
    ],
    "general": [
        "Prefer small reversible changes with clear validation after each patch step.",
        "Always capture the current behavior baseline before refactoring so regressions are easy to detect.",
    ],
}



def _sync_runtime_globals() -> None:
    global RESOURCE_BASE_DIR, APP_BASE_DIR, DEFAULT_BUNDLED_WALLPAPER, DATA_ROOT_DIR, CENTRAL_HUB_MAIN
    global DATA_CENTRAL_HUB_TEST_LAB_DIR, DATA_CENTRAL_HUB_TOOL_TEST_LAB_DIR
    global DEFAULT_GAMES_ROOT, TOOLS_DIR, TEST_LAB_DIR, TOOL_TEST_LAB_DIR, LEGACY_TOOLS_DIR
    global CENTRAL_HUB_DIR, CENTRAL_HUB_TEST_LAB_DIR, HOLOVERSE_DIR, LEGACY_CHAT_DIR, CHAT_DIR
    global LEGACY_MINIGAMES_DIR, GENERATED_EVENTS_DIR, SETTINGS_FILE, FOLDER_LIST_FILE, SCREENSHOTS_DIR
    RESOURCE_BASE_DIR = gx_runtime.RESOURCE_BASE_DIR
    APP_BASE_DIR = gx_runtime.APP_BASE_DIR
    DEFAULT_BUNDLED_WALLPAPER = gx_runtime.DEFAULT_BUNDLED_WALLPAPER
    DATA_ROOT_DIR = gx_runtime.DATA_ROOT_DIR
    CENTRAL_HUB_MAIN = gx_runtime.CENTRAL_HUB_MAIN
    DATA_CENTRAL_HUB_TEST_LAB_DIR = gx_runtime.DATA_CENTRAL_HUB_TEST_LAB_DIR
    DATA_CENTRAL_HUB_TOOL_TEST_LAB_DIR = gx_runtime.DATA_CENTRAL_HUB_TOOL_TEST_LAB_DIR
    DEFAULT_GAMES_ROOT = gx_runtime.DEFAULT_GAMES_ROOT
    TOOLS_DIR = gx_runtime.TOOLS_DIR
    TEST_LAB_DIR = gx_runtime.TEST_LAB_DIR
    TOOL_TEST_LAB_DIR = gx_runtime.TOOL_TEST_LAB_DIR
    LEGACY_TOOLS_DIR = gx_runtime.LEGACY_TOOLS_DIR
    CENTRAL_HUB_DIR = gx_runtime.CENTRAL_HUB_DIR
    CENTRAL_HUB_TEST_LAB_DIR = gx_runtime.CENTRAL_HUB_TEST_LAB_DIR
    HOLOVERSE_DIR = gx_runtime.HOLOVERSE_DIR
    LEGACY_CHAT_DIR = gx_runtime.LEGACY_CHAT_DIR
    CHAT_DIR = gx_runtime.CHAT_DIR
    LEGACY_MINIGAMES_DIR = gx_runtime.LEGACY_MINIGAMES_DIR
    GENERATED_EVENTS_DIR = gx_runtime.GENERATED_EVENTS_DIR
    SETTINGS_FILE = gx_runtime.SETTINGS_FILE
    FOLDER_LIST_FILE = gx_runtime.FOLDER_LIST_FILE
    SCREENSHOTS_DIR = gx_runtime.SCREENSHOTS_DIR
APP_TITLE = gx_runtime.APP_TITLE
OS_VERSION = gx_runtime.OS_VERSION
APP_FOLDER_NAME = getattr(gx_runtime, "APP_FOLDER_NAME", "GLITCHED MATRIX Prototype Lab")
MATRIXCORE_HOST_ENV_FLAG = gx_runtime.MATRIXCORE_HOST_ENV_FLAG
MATRIXCORE_WINDOW_MODE_ENV_FLAG = gx_runtime.MATRIXCORE_WINDOW_MODE_ENV_FLAG
MATRIXCORE_PANEL_ENV_FLAG = gx_runtime.MATRIXCORE_PANEL_ENV_FLAG


def external_game_source_roots(include_generated: bool = True, include_legacy: bool = True) -> list[Path]:
    return gx_runtime.external_game_source_roots(include_generated=include_generated, include_legacy=include_legacy)


def configure_runtime_base(app_base_dir: Path | str | None = None, resource_base_dir: Path | str | None = None) -> None:
    gx_runtime.configure_runtime_base(app_base_dir=app_base_dir, resource_base_dir=resource_base_dir)
    _sync_runtime_globals()


def generation_tool_candidates() -> list[tuple[str, Path]]:
    return gx_runtime.generation_tool_candidates()


def best_generation_tool_name() -> str:
    return gx_runtime.best_generation_tool_name()


_windows_hidden_startupinfo = gx_runtime._windows_hidden_startupinfo
_hidden_creationflags = gx_runtime._hidden_creationflags
_hide_launcher_console_window = gx_runtime._hide_launcher_console_window
_stop_all_pygame_audio = gx_runtime._stop_all_pygame_audio
_runtime_wrapper_template = gx_runtime._runtime_wrapper_template
_find_brand_logo_path = gx_runtime._find_brand_logo_path
_primary_monitor_size = gx_runtime._primary_monitor_size
_launch_surface_for_monitor = gx_runtime._launch_surface_for_monitor
_apply_detected_window_mode = gx_runtime._apply_detected_window_mode
run_panda3d_startup_splash = gx_runtime.run_panda3d_startup_splash
startup_logo_candidates = gx_runtime.startup_logo_candidates
startup_audio_candidates = gx_runtime.startup_audio_candidates
play_startup_audio_once = gx_runtime.play_startup_audio_once
stop_startup_audio = gx_runtime.stop_startup_audio
create_startup_overlay = gx_runtime.create_startup_overlay
begin_startup_handoff = gx_runtime.begin_startup_handoff


def _startup_overlay_image_path() -> Path | None:
    candidates = []
    try:
        found = _find_brand_logo_path()
        if found:
            candidates.append(Path(found))
    except Exception:
        pass
    candidates.extend([
        APP_BASE_DIR / "launcher_logo.png",
        RESOURCE_BASE_DIR / "launcher_logo.png",
        APP_BASE_DIR / "assets" / "launcher_logo.png",
        RESOURCE_BASE_DIR / "assets" / "launcher_logo.png",
    ])
    seen: set[str] = set()
    for candidate in candidates:
        try:
            resolved = str(Path(candidate).resolve())
        except Exception:
            resolved = str(candidate)
        if resolved in seen:
            continue
        seen.add(resolved)
        try:
            probe = Path(candidate)
            if probe.exists() and probe.is_file():
                return probe
        except Exception:
            continue
    return None


def create_startup_overlay(root, _status_text: str = "", log_callback=None):
    overlay = tk.Toplevel(root)
    overlay.overrideredirect(True)
    overlay.configure(bg="#000000")
    try:
        overlay.attributes("-topmost", True)
    except Exception:
        pass
    try:
        overlay.attributes("-alpha", 1.0)
    except Exception:
        pass
    try:
        root.update_idletasks()
    except Exception:
        pass
    width = max(640, int(root.winfo_width() or root.winfo_screenwidth() or 1280))
    height = max(360, int(root.winfo_height() or root.winfo_screenheight() or 720))
    x = int(root.winfo_rootx() or 0)
    y = int(root.winfo_rooty() or 0)
    try:
        overlay.geometry(f"{width}x{height}+{x}+{y}")
    except Exception:
        pass

    host = tk.Frame(overlay, bg="#000000", bd=0, highlightthickness=0)
    host.pack(fill=BOTH, expand=True)
    canvas = tk.Canvas(host, bg="#000000", bd=0, highlightthickness=0, relief="flat")
    canvas.pack(fill=BOTH, expand=True)

    overlay._gx_canvas = canvas
    overlay._gx_photo = None
    overlay._gx_image_path = _startup_overlay_image_path()

    def _render(_event=None):
        try:
            canvas.delete("all")
            w = max(2, canvas.winfo_width())
            h = max(2, canvas.winfo_height())
            image_path = getattr(overlay, "_gx_image_path", None)
            if image_path and Image and ImageTk:
                try:
                    img = Image.open(image_path).convert("RGBA")
                    fitted = ImageOps.contain(img, (w, h), method=Image.Resampling.LANCZOS)
                    photo = ImageTk.PhotoImage(fitted)
                    overlay._gx_photo = photo
                    canvas.create_image(w // 2, h // 2, image=photo, anchor="center")
                except Exception as exc:
                    if callable(log_callback):
                        try:
                            log_callback("Startup Overlay Image Load Failed", str(exc))
                        except Exception:
                            pass
            else:
                canvas.create_rectangle(0, 0, w, h, fill="#000000", outline="")
        except Exception as exc:
            if callable(log_callback):
                try:
                    log_callback("Startup Overlay Render Failed", str(exc))
                except Exception:
                    pass

    overlay.bind("<Configure>", _render, add="+")
    try:
        overlay.after(10, _render)
    except Exception:
        _render()
    return overlay


def begin_startup_handoff(root, startup_overlay, audio_started: bool = False, used_music: bool = True, hold_ms: int = 1100, fade_ms: int = 220, intro_fade_ms: int = 120):
    del audio_started, used_music, intro_fade_ms

    try:
        setattr(root, "_startup_handoff_pending", False)
    except Exception:
        pass

    try:
        root.deiconify()
        root.attributes("-alpha", 1.0)
        root.lift()
        root.update_idletasks()
    except Exception:
        pass

    total_hold = max(500, int(hold_ms or 0))
    total_fade = max(160, int(fade_ms or 0))
    step_ms = 24
    steps = max(8, total_fade // step_ms)

    if startup_overlay is None or not getattr(startup_overlay, 'winfo_exists', lambda: False)():
        try:
            root.lift()
            root.focus_force()
        except Exception:
            pass
        return

    def _sync_overlay_bounds(_event=None):
        try:
            if not (startup_overlay and startup_overlay.winfo_exists()):
                return
            root.update_idletasks()
            width = max(640, int(root.winfo_width() or root.winfo_screenwidth() or 1280))
            height = max(360, int(root.winfo_height() or root.winfo_screenheight() or 720))
            x = int(root.winfo_rootx() or 0)
            y = int(root.winfo_rooty() or 0)
            startup_overlay.geometry(f"{width}x{height}+{x}+{y}")
            startup_overlay.lift()
        except Exception:
            pass

    try:
        root.bind("<Configure>", _sync_overlay_bounds, add="+")
    except Exception:
        pass
    _sync_overlay_bounds()

    def _finish():
        try:
            if startup_overlay and startup_overlay.winfo_exists():
                startup_overlay.destroy()
        except Exception:
            pass
        try:
            root.attributes("-alpha", 1.0)
            root.lift()
            root.focus_force()
        except Exception:
            pass

    def _fade(step: int = 0):
        try:
            ratio = min(1.0, max(0.0, step / float(steps)))
            overlay_alpha = max(0.0, 1.0 - ratio)
            if startup_overlay and startup_overlay.winfo_exists():
                try:
                    startup_overlay.attributes("-alpha", overlay_alpha)
                    startup_overlay.lift()
                except Exception:
                    if step >= steps:
                        _finish()
                        return
            if step >= steps:
                _finish()
                return
            root.after(step_ms, lambda: _fade(step + 1))
        except Exception:
            _finish()

    try:
        root.after(total_hold, lambda: _fade(0))
    except Exception:
        _fade(0)

ARCADE_ZIP_CANDIDATES = ("Arcade Evolution.zip", "Arcade_Evolution.zip")
GAME_PROFILE_LABELS = {
    "any": "Any",
    "side_scroller": "2D Side",
    "isometric": "Isometric",
    "top_down": "Top-Down",
    "text_based": "Text",
    "first_person_3d": "3D First",
    "third_person_3d": "3D Third",
}
GAME_PROFILE_TO_GAMEGEN = {
    "side_scroller": "platformer",
    "isometric": "topdown_adventure",
    "top_down": "topdown_adventure",
    "text_based": "topdown_adventure",
    "first_person_3d": "arena_shooter",
    "third_person_3d": "arena_shooter",
}
GAME_PROFILE_KEYWORDS = {
    "side_scroller": ["side scroller", "side-scroller", "side scrolling", "side-scrolling", "platformer", "platforming", "platform", "jump"],
    "isometric": ["isometric", "iso view", "iso-view", "axonometric"],
    "top_down": ["top down", "top-down", "topdown", "overhead", "bird's-eye", "birds-eye"],
    "text_based": ["text based", "text-based", "text adventure", "interactive fiction", "parser", "choice based", "choice-driven"],
    "first_person_3d": ["first person", "first-person", "fps", "cockpit"],
    "third_person_3d": ["third person", "third-person", "chase camera", "over shoulder", "thirdperson"],
}
WORLD_MODE_LABELS = {
    "any": "Any Mode",
    "level_based": "Level Based",
    "procedural": "Procedural",
    "endless": "Endless",
    "hub_and_levels": "Hub + Levels",
    "sandbox": "Sandbox",
    "roguelike_runs": "Roguelike Runs",
}
WORLD_MODE_OPTIONS = tuple(WORLD_MODE_LABELS.keys())
WORLD_MODE_LABEL_TO_KEY = {label: key for key, label in WORLD_MODE_LABELS.items()}
FORMATION_LABELS = {
    "any": "Any Formation",
    "flat_terrain": "Flat Terrain",
    "rolling_hills": "Rolling Hills",
    "layered_strata": "Layered Strata",
    "caves": "Caves",
    "rooms": "Rooms",
    "clusters": "Clusters",
    "roads": "Roads",
    "open_field": "Open Field",
}
FORMATION_OPTIONS = tuple(FORMATION_LABELS.keys())
FORMATION_LABEL_TO_KEY = {label: key for key, label in FORMATION_LABELS.items()}


class CrashReporter:
    def __init__(self) -> None:
        # Do not create crash_reports on normal app startup.  Release builds
        # should stay clean until a real app/game failure needs a report.
        self.dir = self._prepare_dir()
        self.latest_app = self.dir / "latest_crash.txt"
        self.latest_game = self.dir / "latest_game_log.txt"
        self.verbose_game_logs = self._env_enabled("GX_VERBOSE_GAME_LOGS") or self._env_enabled("GX_DEBUG_GAME_LOGS")

    @staticmethod
    def _env_enabled(name: str) -> bool:
        return str(os.environ.get(name, "")).strip().lower() in {"1", "true", "yes", "on"}

    @staticmethod
    def _prepare_dir() -> Path:
        return APP_BASE_DIR / "crash_reports"

    def _session_log_dir(self, safe_game_name: str) -> Path:
        if self.verbose_game_logs:
            return self.dir / "games" / safe_game_name
        return Path(tempfile.gettempdir()) / "GXPrototypeLab" / "game_sessions" / safe_game_name

    def _atomic_write(self, path: Path, text: str) -> None:
        """Write crash text without ever leaving a 0 KB report behind."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = text if str(text or "").strip() else "[crash reporter] no text was captured; launcher wrote this placeholder so the report is not empty.\n"
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(payload, encoding="utf-8", errors="replace")
        try:
            tmp.replace(path)
        except Exception:
            path.write_text(payload, encoding="utf-8", errors="replace")
            try:
                tmp.unlink(missing_ok=True)
            except Exception:
                pass

    def _append_text(self, path: Path, text: str) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = text if str(text or "").strip() else "[crash reporter] blank append request ignored.\n"
        with path.open("a", encoding="utf-8", errors="replace") as fh:
            fh.write(payload)
            if not payload.endswith("\n"):
                fh.write("\n")

    def write_exception(self, title: str, exc_type, exc_value, exc_tb) -> None:
        details = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        self._atomic_write(self.latest_app, f"[{stamp}] {title}\n{details}\n")

    def write_text(self, title: str, content: str, target: str = "app") -> None:
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        out = self.latest_app if target == "app" else self.latest_game
        body = str(content or "").strip() or "No stdout/stderr text was captured. Check the command, cwd, return code, and direct child log below."
        self._atomic_write(out, f"[{stamp}] {title}\n{body}\n")

    def start_game_log(self, game_name: str, entry: Path, cmd: list[str], cwd: Path, env_notes: dict[str, str] | None = None) -> Path:
        safe = re.sub(r"[^A-Za-z0-9._-]+", "_", (game_name or "unknown_game")).strip("_") or "unknown_game"
        stamp = time.strftime("%Y%m%d_%H%M%S")
        game_dir = self._session_log_dir(safe)
        direct = game_dir / f"session_{stamp}.txt"
        lines = [
            f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Game Launch Started",
            f"Game: {game_name}",
            f"Entry: {entry}",
            f"CWD: {cwd}",
            f"Command: {' '.join(str(c) for c in cmd)}",
            f"Python executable: {sys.executable}",
            f"Crash reports dir: {self.dir}",
        ]
        if env_notes:
            lines.append("Environment notes:")
            for key, value in sorted(env_notes.items()):
                lines.append(f"  {key}={value}")
        lines.append("Status: launch preflight started. If startup fails before the child process opens, the traceback is written here instead of leaving a 0 KB report.")
        payload = "\n".join(lines) + "\n"
        if self.verbose_game_logs:
            self._atomic_write(self.latest_game, payload)
        self._atomic_write(direct, payload)
        return direct

    def append_game_log(self, session_log: Path | None, text: str) -> None:
        payload = str(text or "").strip() or "[crash reporter] blank game-log append ignored."
        if not payload.endswith("\n"):
            payload += "\n"
        if self.verbose_game_logs:
            self._append_text(self.latest_game, payload)
        if session_log is not None:
            self._append_text(session_log, payload)

    def finish_game_log(self, game_name: str, session_log: Path | None, return_code: int | None, log_text: str, child_direct_text: str = "", expected_shutdown: bool = False) -> None:
        rc = "unknown" if return_code is None else str(return_code)
        header = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Game Launch Finished\nGame: {game_name}\nReturn code: {rc}\n"
        if expected_shutdown:
            header += "Expected shutdown: yes\n"
        header += "\n"
        captured = str(log_text or "").strip()
        if not captured:
            captured = "No stdout/stderr text was captured from the child process."
        if child_direct_text.strip():
            captured += "\n\n--- Direct child crash hook log ---\n" + child_direct_text.strip()
        payload = header + captured + "\n"
        is_failure = (return_code not in (0, None)) and not expected_shutdown
        should_persist = self.verbose_game_logs or is_failure or return_code is None
        if should_persist:
            self._atomic_write(self.latest_game, payload)
            if session_log is not None:
                self._atomic_write(session_log, payload)
        elif session_log is not None:
            try:
                Path(session_log).unlink(missing_ok=True)
            except Exception:
                pass

    def write_game_crash_bundle(self, game_name: str, return_code: int | None, log_text: str) -> Path:
        safe = re.sub(r"[^A-Za-z0-9._-]+", "_", (game_name or "unknown_game")).strip("_") or "unknown_game"
        game_dir = self.dir / "games" / safe
        game_dir.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        out = game_dir / f"crash_{stamp}.txt"
        rc = "unknown" if return_code is None else str(return_code)
        body = str(log_text or "").strip() or "No stdout/stderr text was captured; this report was generated from the non-zero process return code."
        self._atomic_write(
            out,
            f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Game Crash\nGame: {game_name}\nReturn code: {rc}\n\n{body}\n",
        )
        return out

    def clear_latest(self, target: str = "app") -> None:
        # Do not create 0 KB reports.  Older builds cleared latest_crash.txt on
        # shutdown, which destroyed useful evidence and looked like a broken
        # reporter. Keep the previous report until a real new report replaces it.
        return


CRASH_REPORTER = CrashReporter()

def _path_is_inside(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except Exception:
        return False


def _owned_missing_folder_allowed(path: Path) -> bool:
    """Allow creation only for folders the app owns inside its real base dir."""
    try:
        path = Path(path)
        owned_roots = [
            APP_BASE_DIR / "crash_reports",
            APP_BASE_DIR / "data",
            APP_BASE_DIR / "data" / "Prototype Lab",
            APP_BASE_DIR / "data" / "GX-Machine",
            APP_BASE_DIR / "data" / "HoloVerse",
            APP_BASE_DIR / "data" / "assets",
        ]
        return any(_path_is_inside(path, root) or path.resolve() == root.resolve() for root in owned_roots)
    except Exception:
        return False



def install_crash_reporter() -> None:
    def _report(exc_type, exc_value, exc_tb):
        CRASH_REPORTER.write_exception("Application Crash", exc_type, exc_value, exc_tb)
        try:
            messagebox.showerror("Crash Reporter", f"Crash report saved to:\n{CRASH_REPORTER.latest_app}")
        except Exception:
            pass

    def _thread_report(args):
        _report(args.exc_type, args.exc_value, args.exc_traceback)

    sys.excepthook = _report
    threading.excepthook = _thread_report


@dataclass
class GameEntry:
    name: str
    folder: Path
    main_py: Path
    thumbnail: Path
    description: str
    category: str = "prototype lab"


class AnalysisCancelled(Exception):
    pass




def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = str(value or '#000000').strip()
    if not value.startswith('#'):
        value = '#000000'
    value = value.lstrip('#')
    if len(value) == 3:
        value = ''.join(ch * 2 for ch in value)
    if len(value) != 6:
        return (0, 0, 0)
    try:
        return tuple(int(value[i:i+2], 16) for i in (0, 2, 4))
    except Exception:
        return (0, 0, 0)


def _rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    r, g, b = [max(0, min(255, int(v))) for v in rgb]
    return f'#{r:02x}{g:02x}{b:02x}'


def _blend_hex(a: str, b: str, factor: float) -> str:
    factor = max(0.0, min(1.0, float(factor)))
    ar, ag, ab = _hex_to_rgb(a)
    br, bg, bb = _hex_to_rgb(b)
    return _rgb_to_hex((
        round(ar + (br - ar) * factor),
        round(ag + (bg - ag) * factor),
        round(ab + (bb - ab) * factor),
    ))


class CyberButton(Frame):
    """Minimal text-first shell button that can blend into artwork-backed panels."""

    def __init__(self, parent, text='', command=None, *, bg='#1b1d20', fg='#efefef',
                 activebackground=None, activeforeground=None, hoverbackground=None,
                 outline=None, panel_bg=None, font=('Consolas', 10, 'bold'),
                 compact=False, height=40, min_width=84, cursor='hand2', text_pad=24,
                 command_on_release=True, text_only=False, bg_image_provider=None,
                 text_anchor='w', **kwargs):
        panel_bg = panel_bg or getattr(parent, 'cget', lambda _k: '#050506')('bg')
        super().__init__(parent, bg=panel_bg, bd=0, highlightthickness=0, **kwargs)
        self.command = command
        self.command_on_release = bool(command_on_release)
        self.base_bg = bg
        self.base_fg = fg
        self.hover_bg = hoverbackground or _blend_hex(bg, '#22e0e6', 0.18)
        self.active_bg = activebackground or _blend_hex(bg, '#ffffff', 0.10)
        self.active_fg = activeforeground or fg
        self.outline = outline or _blend_hex(fg, '#22d8de', 0.38)
        self.panel_bg = panel_bg
        self.font = font
        self.compact = bool(compact)
        self.height_px = max(26, int(height))
        self.min_width = max(48, int(min_width))
        self.text_pad = max(8, int(text_pad))
        self.text_only = bool(text_only)
        self.bg_image_provider = bg_image_provider
        self.text_anchor = str(text_anchor or 'w')
        self._text = str(text)
        self._enabled = True
        self._hover = False
        self._pressed = False
        self._current_bg = self.base_bg
        self._current_fg = self.base_fg
        self._current_outline = self.outline
        self._bg_photo = None
        self.grid_propagate(False)
        self.pack_propagate(False)
        self.configure(height=self.height_px, width=self.min_width)
        self.canvas = Canvas(self, bg=panel_bg, bd=0, highlightthickness=0, relief='flat', cursor=cursor)
        self.canvas.pack(fill='both', expand=True)
        self.canvas.bind('<Configure>', self._redraw, add='+')
        for widget in (self, self.canvas):
            widget.bind('<Enter>', self._on_enter, add='+')
            widget.bind('<Leave>', self._on_leave, add='+')
            widget.bind('<Button-1>', self._on_press, add='+')
            widget.bind('<ButtonRelease-1>', self._on_release, add='+')
            widget.bind('<Map>', self._queue_redraw, add='+')
        self.after_idle(self._redraw)

    def cget(self, key):
        if key == 'text':
            return self._text
        if key == 'bg':
            return self.base_bg
        if key == 'fg':
            return self.base_fg
        return super().cget(key)

    def configure(self, cnf=None, **kw):
        options = {}
        if cnf:
            options.update(cnf)
        options.update(kw)
        passthrough = {}
        redraw = False
        for key, value in list(options.items()):
            if key == 'text':
                self._text = str(value)
                redraw = True
            elif key == 'bg':
                self.base_bg = str(value)
                redraw = True
            elif key == 'fg':
                self.base_fg = str(value)
                redraw = True
            elif key == 'activebackground':
                self.active_bg = str(value)
                redraw = True
            elif key == 'activeforeground':
                self.active_fg = str(value)
                redraw = True
            elif key == 'hoverbackground':
                self.hover_bg = str(value)
                redraw = True
            elif key == 'outline':
                self.outline = str(value)
                redraw = True
            elif key == 'state':
                self._enabled = (str(value) != 'disabled')
                redraw = True
            elif key == 'command':
                self.command = value
            elif key == 'cursor':
                try:
                    self.canvas.configure(cursor=value)
                except Exception:
                    pass
            elif key == 'text_only':
                self.text_only = bool(value)
                redraw = True
            elif key == 'bg_image_provider':
                self.bg_image_provider = value
                redraw = True
            elif key == 'text_anchor':
                self.text_anchor = str(value or 'w')
                redraw = True
            elif key in {'width', 'height'}:
                passthrough[key] = value
                redraw = True
            else:
                passthrough[key] = value
        result = super().configure(**passthrough) if passthrough else None
        if redraw:
            self._redraw()
        return result

    config = configure

    def invoke(self):
        if self.command and self._enabled:
            try:
                return self.command()
            except Exception:
                return None
        return None

    def _state_colors(self):
        if not self._enabled:
            return (_blend_hex(self.base_bg, '#000000', 0.40), _blend_hex(self.base_fg, '#444444', 0.45), _blend_hex(self.outline, '#333333', 0.55))
        if self._pressed:
            return (self.active_bg, self.active_fg, _blend_hex(self.outline, '#ffffff', 0.20))
        if self._hover:
            return (self.hover_bg, self.base_fg, _blend_hex(self.outline, '#22f0f5', 0.28))
        return (self.base_bg, self.base_fg, self.outline)

    def _button_points(self, w, h):
        cut = max(8, min(18, int(h * 0.30)))
        notch = max(8, min(18, int(w * 0.055)))
        return [
            cut, 0,
            w - notch - cut, 0,
            w - notch, h // 2,
            w - notch - cut, h,
            cut, h,
            0, h // 2,
        ]

    def _text_coords(self, w, h):
        if self.text_anchor == 'center':
            return (w / 2, h / 2, 'center')
        if self.text_anchor == 'e':
            return (max(self.text_pad, w - self.text_pad), h / 2, 'e')
        return (self.text_pad, h / 2, 'w')

    def _redraw(self, _event=None):
        try:
            w = max(self.min_width, int(self.canvas.winfo_width() or self.min_width))
            h = max(self.height_px, int(self.canvas.winfo_height() or self.height_px))
            self.canvas.delete('all')
            fill, text_color, outline = self._state_colors()
            self._current_bg, self._current_fg, self._current_outline = fill, text_color, outline
            self._bg_photo = None
            if self.bg_image_provider is not None:
                try:
                    photo = self.bg_image_provider(w, h, self)
                    if photo is not None:
                        self._bg_photo = photo
                        self.canvas.create_image(0, 0, image=photo, anchor='nw')
                except Exception:
                    self._bg_photo = None
            x, y, anchor = self._text_coords(w, h)
            shadow_color = _blend_hex(text_color, '#000000', 0.78)
            if not self.text_only:
                pts = self._button_points(w, h)
                self.canvas.create_polygon(pts, fill=_blend_hex(fill, '#050607', 0.04), outline=outline, width=2, smooth=False)
                inner_pad = 4
                inner_pts = []
                for idx in range(0, len(pts), 2):
                    px = pts[idx]
                    py = pts[idx + 1]
                    cx = w / 2
                    cy = h / 2
                    nx = px + inner_pad if px < cx else px - inner_pad
                    ny = py + inner_pad if py < cy else py - inner_pad
                    inner_pts.extend([nx, ny])
                self.canvas.create_polygon(inner_pts, fill=_blend_hex(fill, '#000000', 0.25), outline='', smooth=False)
                line_color = _blend_hex(outline, '#ffffff', 0.08)
                self.canvas.create_line(12, 6, max(20, w * 0.22), 6, fill=line_color, width=2)
                self.canvas.create_line(12, h - 6, max(18, w * 0.18), h - 6, fill=line_color, width=2)
                self.canvas.create_line(w - 28, 6, w - 14, 6, fill=line_color, width=2)
                self.canvas.create_line(w - 30, h - 6, w - 14, h - 6, fill=line_color, width=2)
            elif self._hover or self._pressed:
                line_y = h - 5
                self.canvas.create_line(max(10, self.text_pad - 8), line_y, min(w - 10, self.text_pad + max(42, len(self._text) * 7)), line_y, fill=outline, width=2)
            # Strong dark shadow/outline behind button labels so custom textures never overpower the text.
            label_text = self._text.upper()
            heavy_shadow = _blend_hex(text_color, '#000000', 0.92)
            for dx, dy in ((-2, 0), (2, 0), (0, -2), (0, 2), (-2, -2), (2, -2), (-2, 2), (2, 2)):
                self.canvas.create_text(x + dx, y + dy, text=label_text, anchor=anchor, fill=heavy_shadow, font=self.font)
            self.canvas.create_text(x + 3, y + 4, text=label_text, anchor=anchor, fill='#000000', font=self.font)
            self.canvas.create_text(x, y, text=label_text, anchor=anchor, fill=text_color, font=self.font)
        except Exception:
            pass

    def _queue_redraw(self, _event=None):
        try:
            self.after_idle(self._redraw)
        except Exception:
            self._redraw()

    def _on_enter(self, _event=None):
        if self._enabled:
            self._hover = True
            self._redraw()

    def _on_leave(self, _event=None):
        self._hover = False
        self._pressed = False
        self._redraw()

    def _on_press(self, _event=None):
        if self._enabled:
            self._pressed = True
            self._redraw()
            if not self.command_on_release:
                self.invoke()

    def _on_release(self, event=None):
        if not self._enabled:
            return
        inside = True
        try:
            if event is not None:
                inside = 0 <= event.x <= self.winfo_width() and 0 <= event.y <= self.winfo_height()
        except Exception:
            inside = True
        should_invoke = self._pressed and inside and self.command_on_release
        self._pressed = False
        self._redraw()
        if should_invoke:
            self.invoke()





def _load_bridge_exit_cleanup_module():
    module_path = APP_BASE_DIR / "data" / "GX-Machine" / "diagnostics" / "bridge_exit_cleanup.py"
    if not module_path.exists():
        return None
    try:
        spec = importlib.util.spec_from_file_location("gx_bridge_exit_cleanup", module_path)
        if spec is None or spec.loader is None:
            return None
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module
    except Exception:
        return None


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


def run_panda3d_startup_splash(status_text: str, *, min_hold: float = 2.0, fade_duration: float = 0.45, fullscreen: bool = False, fullscreen_windowed: bool = False) -> bool:
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


class MatrixCoreStandaloneLauncher:
    def __init__(self, root: tk.Misc) -> None:
        self.root = root
        self.current_game = None
        self.current_game_name = ""
        self.current_games: dict[str, subprocess.Popen] = {}
        self.embedded_windows: dict[str, tk.Toplevel] = {}
        self._recent_launch_keys: dict[str, float] = {}
        self.is_closing = False

    def _resolved_games_root(self) -> Path:
        return DEFAULT_GAMES_ROOT

    def _panel_key_for_minigame(self, label: str) -> str:
        return re.sub(r"[^a-z0-9]+", "_", str(label).lower()).strip("_") or "panel"

    def show_transient_status(self, _text: str, _ms: int = 0) -> None:
        return

    def refresh_games(self) -> None:
        return

    def start_chatspace_game_reactions(self, *_args, **_kwargs) -> None:
        return

    def open_system_shortcut(self, *_args, **_kwargs) -> None:
        return

    def get_central_hub_main(self) -> Path | None:
        candidates = [
            CENTRAL_HUB_MAIN,
            APP_BASE_DIR / "data" / "CentralHub.py",
            APP_BASE_DIR / "data" / "centralhub.py",
            RESOURCE_BASE_DIR / "data" / "CentralHub.py",
            RESOURCE_BASE_DIR / "data" / "centralhub.py",
        ]
        for candidate in candidates:
            try:
                if candidate.exists() and candidate.is_file():
                    return candidate.resolve()
            except Exception:
                continue
        return None

    def get_holoverse_main(self) -> Path | None:
        candidates = [
            HOLOVERSE_DIR / "main.py",
            APP_BASE_DIR / "data" / "HoloVerse" / "main.py",
            RESOURCE_BASE_DIR / "data" / "HoloVerse" / "main.py",
            DEFAULT_GAMES_ROOT / "HoloVerse" / "main.py",
            DEFAULT_GAMES_ROOT / "HoloVerse" / "HoloVerse" / "main.py",
        ]
        for candidate in candidates:
            try:
                if candidate.exists() and candidate.is_file():
                    return candidate.resolve()
            except Exception:
                continue
        return None

    def open_holoverse_project(self) -> None:
        holoverse_main = self.get_holoverse_main()
        if holoverse_main is None or not holoverse_main.exists():
            try:
                messagebox.showinfo("HoloVerse", f"Expected a launchable HoloVerse main.py inside:\n{HOLOVERSE_DIR}")
            except Exception:
                pass
            return
        try:
            self.launch_python_entry(
                holoverse_main,
                "HoloVerse",
                immersive=False,
                panel_key="holoverse",
                extra_args=["--windowed", "--desktop", "--no-vr"],
                extra_env={
                    "HOLOVERSE_NO_VR": "1",
                    "MATRIX_GAME_VR": "0",
                    "MATRIX_GAME_FULLSCREEN": "0",
                    "MATRIX_GAME_BORDERLESS": "0",
                    "MATRIX_GAME_BORDERED_FULLSCREEN": "1",
                },
            )
        except Exception:
            CRASH_REPORTER.write_exception("HoloVerse Launch Crash", *sys.exc_info())
            try:
                messagebox.showerror("HoloVerse", f"Failed to launch HoloVerse.\nSee: {CRASH_REPORTER.latest_app}")
            except Exception:
                pass

    def open_central_hub_project(self) -> None:
        self.open_prototype_lab_explorer()

    def _prototype_lab_root(self) -> Path:
        return APP_BASE_DIR / "data" / "Prototype Lab"

    def _prototype_lab_shortcut_entries(self) -> list[tuple[str, Path]]:
        root = self._prototype_lab_root()
        entries: list[tuple[str, Path]] = [("🏠 Prototype Lab", root)]
        for sub in ["2D - Side", "2D - Top", "2D - Hybrid", "2D - Isometric", "3D - First Person", "3D - Third Person", "Generated Games"]:
            path = root / sub
            if path.exists():
                entries.append((f"📁 {sub}", path))
        extras = [("🧠 GX-Machine", APP_BASE_DIR / "data" / "GX-Machine"), ("📸 Screenshots", APP_BASE_DIR / "data" / "assets" / "screenshots"), ("🎨 Textures", APP_BASE_DIR / "data" / "assets" / "textures")]
        for label, path in extras:
            if path.exists():
                entries.append((label, path))
        return entries

    def _prototype_lab_push_history(self, path: Path) -> None:
        path = Path(path)
        hist = list(getattr(self, 'prototype_lab_desktop_history', []))
        idx = int(getattr(self, 'prototype_lab_desktop_history_index', -1))
        if 0 <= idx < len(hist) and Path(hist[idx]) == path:
            return
        if idx < len(hist) - 1:
            hist = hist[: idx + 1]
        hist.append(path)
        self.prototype_lab_desktop_history = hist[-40:]
        self.prototype_lab_desktop_history_index = len(self.prototype_lab_desktop_history) - 1

    def _format_bytes(self, size: int) -> str:
        try:
            size = int(size)
        except Exception:
            return ""
        units = ["B", "KB", "MB", "GB"]
        value = float(size)
        for unit in units:
            if value < 1024.0 or unit == units[-1]:
                return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
            value /= 1024.0
        return f"{size} B"

    def _format_mtime(self, timestamp: float | int | None) -> str:
        try:
            return time.strftime('%Y-%m-%d %H:%M', time.localtime(float(timestamp or 0)))
        except Exception:
            return ''

    def _prototype_lab_describe_entry(self, path: Path) -> tuple[str, str, str, str]:
        badge = ""
        prefix = "📄"
        kind = "File"
        if path.is_dir():
            prefix = "📁"
            kind = "Folder"
            badge = "RUN" if (path / 'main.py').exists() else "DIR"
        elif path.suffix.lower() == '.py':
            prefix = "🐍"
            kind = "Python"
            badge = "RUN"
        elif path.suffix.lower() in {'.png', '.jpg', '.jpeg', '.webp', '.bmp'}:
            prefix = "🖼"
            kind = "Image"
            badge = "VIEW"
        elif path.suffix.lower() in {'.json', '.toml', '.yaml', '.yml', '.ini', '.cfg'}:
            prefix = "🧩"
            kind = "Config"
            badge = "DATA"
        elif path.suffix.lower() in {'.md', '.txt', '.log'}:
            prefix = "📝"
            kind = "Text"
            badge = "READ"
        size = self._format_bytes(path.stat().st_size if path.exists() and path.is_file() else 0)
        return prefix, kind, badge, size

    def _redraw_prototype_lab_wallpaper(self, _event=None) -> None:
        canvas = getattr(self, 'prototype_lab_wallpaper_canvas', None)
        if canvas is None:
            return
        try:
            width = max(120, int(canvas.winfo_width() or 160))
            height = max(56, int(canvas.winfo_height() or 70))
            canvas.delete('all')

            shell_img = None
            if Image is not None and ImageTk is not None and hasattr(self, '_get_shell_texture_pil'):
                try:
                    shell_img = self._get_shell_texture_pil(width, height)
                except Exception:
                    shell_img = None
            if shell_img is not None and ImageTk is not None:
                try:
                    fitted = shell_img.copy().convert('RGBA')
                    if ImageEnhance is not None:
                        fitted = ImageEnhance.Brightness(fitted).enhance(0.62)
                        fitted = ImageEnhance.Contrast(fitted).enhance(1.08)
                    if Image is not None:
                        veil = Image.new('RGBA', (width, height), (0, 0, 0, 86))
                        fitted.alpha_composite(veil)
                    photo = ImageTk.PhotoImage(fitted)
                    canvas._gx_wallpaper_photo = photo
                    canvas.create_image(0, 0, image=photo, anchor='nw')
                    canvas.create_rectangle(8, 8, width - 8, height - 8, outline='#1e96a4')
                    canvas.create_text(16, 16, anchor='nw', text='MXOS WALLPAPER', fill='#d8f8ff', font=('Consolas', 10, 'bold'))
                    canvas.create_text(16, height - 12, anchor='sw', text='matrixcore shell art', fill='#86c8d2', font=('Segoe UI', 8))
                    return
                except Exception:
                    pass

            canvas.create_rectangle(0, 0, width, height, fill='#091015', outline='')
            for offset in range(-height, width, 24):
                canvas.create_line(offset, height, offset + 30, 0, fill='#14333b', width=1)
            canvas.create_rectangle(8, 8, width - 8, height - 8, outline='#17333a')
            canvas.create_arc(14, 14, width - 26, height + 18, start=0, extent=180, outline='#1e96a4', style='arc', width=2)
            canvas.create_arc(34, 24, width - 12, height + 10, start=0, extent=180, outline='#24b9c7', style='arc', width=1)
            for idx, x in enumerate((18, 46, 74, 102)):
                radius = 3 + idx
                canvas.create_oval(x - radius, height - 18 - radius, x + radius, height - 18 + radius, fill='#ffd364' if idx == 0 else '#1ab0bf', outline='')
            canvas.create_text(16, 16, anchor='nw', text='PROTO-NEXUS', fill='#d8f8ff', font=('Consolas', 10, 'bold'))
            canvas.create_text(16, height - 12, anchor='sw', text='virtual desktop corridor', fill='#86c8d2', font=('Segoe UI', 8))
        except Exception:
            pass

    def _prototype_lab_update_buttons(self) -> None:
        back_depth = max(0, int(getattr(self, 'prototype_lab_desktop_history_index', -1)))
        hist = list(getattr(self, 'prototype_lab_desktop_history', []))
        fwd_depth = max(0, len(hist) - back_depth - 1)
        selected = Path(getattr(self, 'prototype_lab_desktop_selected', self._prototype_lab_root()) or self._prototype_lab_root())
        selected_name = selected.name or selected.as_posix()
        if getattr(self, 'prototype_lab_status_var', None) is not None:
            self.prototype_lab_status_var.set(f"Back {back_depth} • Forward {fwd_depth} • Focus {selected_name}")
        if getattr(self, 'prototype_lab_taskbar_var', None) is not None:
            self.prototype_lab_taskbar_var.set(f"{selected_name} • {self._safe_rel_path(selected)}")
        if getattr(self, 'prototype_lab_clock_var', None) is not None:
            try:
                self.prototype_lab_clock_var.set(time.strftime('%I:%M %p').lstrip('0') or time.strftime('%H:%M'))
            except Exception:
                pass
        if getattr(self, 'prototype_lab_bottom_hint_var', None) is not None:
            self.prototype_lab_bottom_hint_var.set(f"Focused on {selected_name}. Run opens Python files and folders containing main.py. Open Folder uses the system explorer.")
    def _prototype_lab_render_preview(self, path: Path | None) -> None:
        widget = getattr(self, 'prototype_lab_preview_text', None)
        if widget is None:
            return
        lines: list[str] = []
        if path is None:
            lines = ["No selection."]
        else:
            path = Path(path)
            prefix, kind, badge, size = self._prototype_lab_describe_entry(path)
            lines.append(f"{prefix} {path.name}")
            lines.append(f"Type: {kind}")
            if badge:
                lines.append(f"Badge: {badge}")
            lines.append(f"Path: {self._safe_rel_path(path)}")
            try:
                lines.append(f"Modified: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(path.stat().st_mtime))}")
            except Exception:
                pass
            if size:
                lines.append(f"Size: {size}")
            if path.is_dir():
                try:
                    children = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
                    dir_count = sum(1 for child in children if child.is_dir())
                    file_count = max(0, len(children) - dir_count)
                    lines.append("")
                    lines.append(f"Items: {len(children)} • Folders: {dir_count} • Files: {file_count}")
                    for child in children[:10]:
                        child_prefix, child_kind, child_badge, _ = self._prototype_lab_describe_entry(child)
                        badge_text = f" • {child_badge}" if child_badge else ""
                        lines.append(f"{child_prefix} {child.name} • {child_kind}{badge_text}")
                except Exception as exc:
                    lines.append("")
                    lines.append(f"Folder read failed: {exc}")
            else:
                suffix = path.suffix.lower()
                if suffix in {'.py', '.txt', '.md', '.json', '.toml', '.yaml', '.yml', '.ini', '.cfg', '.log'}:
                    try:
                        snippet = path.read_text(encoding='utf-8', errors='ignore')[:2200].strip()
                        if snippet:
                            lines.append("")
                            lines.append(snippet)
                    except Exception as exc:
                        lines.append("")
                        lines.append(f"Preview read failed: {exc}")
                elif suffix in {'.png', '.jpg', '.jpeg', '.webp', '.bmp'}:
                    lines.append("")
                    if Image is not None:
                        try:
                            with Image.open(path) as img:
                                lines.append(f"Image: {img.width} x {img.height}")
                                lines.append(f"Mode: {img.mode}")
                                fmt = str(img.format or suffix.lstrip('.').upper())
                                lines.append(f"Format: {fmt}")
                        except Exception as exc:
                            lines.append(f"Image read failed: {exc}")
                    lines.append("Preview-ready asset. Use Open Folder for external inspection.")
        widget.config(state='normal')
        widget.delete('1.0', END)
        widget.insert('1.0', '\n'.join(lines))
        widget.config(state='disabled')
    def _prototype_lab_render_shortcuts(self) -> None:
        shortcuts = self._prototype_lab_shortcut_entries()
        self.prototype_lab_desktop_shortcuts = shortcuts
        lb = getattr(self, 'prototype_lab_shortcuts_list', None)
        if lb is not None:
            lb.delete(0, END)
            for label, _ in shortcuts:
                lb.insert(END, label)
        host = getattr(self, 'prototype_lab_shortcuts_tiles_inner', None)
        if host is None:
            return
        selected = Path(getattr(self, 'prototype_lab_desktop_selected', self._prototype_lab_root()) or self._prototype_lab_root())
        selected_base = selected.parent if selected.is_file() else selected
        for child in list(host.winfo_children()):
            try:
                child.destroy()
            except Exception:
                pass
        self.prototype_lab_shortcut_buttons = []
        host.grid_columnconfigure(0, weight=1)
        for idx, (label, path) in enumerate(shortcuts):
            target = Path(path)
            try:
                is_active = selected_base == target or selected_base.is_relative_to(target)
            except Exception:
                is_active = selected_base == target
            tile_bg = '#10242a' if is_active else '#0a0d10'
            tile_edge = '#24b9c7' if is_active else '#162126'
            text_fg = '#eff9fc' if is_active else '#dbe2e7'
            hint_fg = '#8fdfea' if is_active else '#76858b'
            outer = Frame(host, bg=tile_bg, highlightthickness=1, highlightbackground=tile_edge, bd=0)
            outer.grid(row=idx, column=0, sticky='ew', pady=(0, 6), padx=1)
            outer.grid_columnconfigure(0, weight=1)
            title = Button(
                outer,
                text=label,
                command=lambda p=target: self._prototype_lab_set_path(Path(p)),
                anchor='w',
                justify='left',
                wraplength=128,
                bg=tile_bg,
                fg=text_fg,
                activebackground='#13343a',
                activeforeground='#ffffff',
                relief='flat',
                bd=0,
                highlightthickness=0,
                padx=10,
                pady=8,
                font=('Segoe UI', 10, 'bold'),
                cursor='hand2',
            )
            title.grid(row=0, column=0, sticky='ew')
            hint_text = self._safe_rel_path(target)
            if len(hint_text) > 28:
                hint_text = '…' + hint_text[-27:]
            Label(outer, text=hint_text, bg=tile_bg, fg=hint_fg, anchor='w', justify='left', font=('Segoe UI', 8)).grid(row=1, column=0, sticky='ew', padx=10, pady=(0, 8))
            self.prototype_lab_shortcut_buttons.append(title)
    def _prototype_lab_set_path(self, path: Path, *, push_history: bool = True) -> None:
        path = Path(path)
        if not path.exists():
            path = self._prototype_lab_root()
        parent = path.parent if path.is_file() else path
        if push_history:
            self._prototype_lab_push_history(parent)
        self.prototype_lab_desktop_selected = path
        if getattr(self, 'prototype_lab_path_var', None) is not None:
            self.prototype_lab_path_var.set(str(parent))
        tree = getattr(self, 'prototype_lab_file_tree', None)
        if tree is not None:
            tree.delete(*tree.get_children())
            filter_text = str(self.prototype_lab_filter_var.get()).strip().lower() if getattr(self, 'prototype_lab_filter_var', None) is not None else ''
            try:
                entries = sorted(parent.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
            except Exception:
                entries = []
            count = 0
            for entry in entries:
                if filter_text and filter_text not in entry.name.lower():
                    continue
                prefix, kind, badge, size = self._prototype_lab_describe_entry(entry)
                tree.insert('', 'end', iid=str(entry), text=f"{prefix} {entry.name}", values=(kind, badge, size))
                count += 1
            if getattr(self, 'display_status_var', None) is not None:
                self.display_status_var.set(f"MXOS desktop • {count} items in {parent.name or parent}")
        self._prototype_lab_render_shortcuts()
        self._prototype_lab_render_preview(path)
        self._prototype_lab_update_buttons()

    def _prototype_lab_refresh(self) -> None:
        target = Path(getattr(self, 'prototype_lab_desktop_selected', self._prototype_lab_root()) or self._prototype_lab_root())
        self._prototype_lab_set_path(target, push_history=False)

    def _prototype_lab_go_home(self) -> None:
        self._prototype_lab_set_path(self._prototype_lab_root())

    def _prototype_lab_go_up(self) -> None:
        target = Path(getattr(self, 'prototype_lab_desktop_selected', self._prototype_lab_root()) or self._prototype_lab_root())
        base = target.parent if target.is_file() else target
        parent = base.parent if base != self._prototype_lab_root() else self._prototype_lab_root()
        self._prototype_lab_set_path(parent)

    def _prototype_lab_go_back(self) -> None:
        hist = list(getattr(self, 'prototype_lab_desktop_history', []))
        idx = int(getattr(self, 'prototype_lab_desktop_history_index', -1))
        if idx > 0:
            self.prototype_lab_desktop_history_index = idx - 1
            self._prototype_lab_set_path(Path(hist[idx - 1]), push_history=False)

    def _prototype_lab_go_forward(self) -> None:
        hist = list(getattr(self, 'prototype_lab_desktop_history', []))
        idx = int(getattr(self, 'prototype_lab_desktop_history_index', -1))
        if 0 <= idx < len(hist) - 1:
            self.prototype_lab_desktop_history_index = idx + 1
            self._prototype_lab_set_path(Path(hist[idx + 1]), push_history=False)

    def _on_prototype_lab_shortcut_select(self, _event=None) -> None:
        lb = getattr(self, 'prototype_lab_shortcuts_list', None)
        if lb is None:
            return
        sel = lb.curselection()
        if not sel:
            return
        try:
            _label, path = self.prototype_lab_desktop_shortcuts[int(sel[0])]
            self.prototype_lab_desktop_selected = Path(path)
            self._prototype_lab_render_preview(Path(path))
            self._prototype_lab_update_buttons()
        except Exception:
            pass

    def _on_prototype_lab_shortcut_activate(self, _event=None) -> str:
        lb = getattr(self, 'prototype_lab_shortcuts_list', None)
        if lb is not None and lb.curselection():
            idx = int(lb.curselection()[0])
            _label, path = self.prototype_lab_desktop_shortcuts[idx]
            self._prototype_lab_set_path(Path(path))
        return 'break'

    def _on_prototype_lab_tree_select(self, _event=None) -> None:
        tree = getattr(self, 'prototype_lab_file_tree', None)
        if tree is None:
            return
        sel = tree.selection()
        if not sel:
            return
        path = Path(sel[0])
        self.prototype_lab_desktop_selected = path
        self._prototype_lab_render_preview(path)
        self._prototype_lab_update_buttons()

    def _on_prototype_lab_tree_activate(self, _event=None) -> str:
        target = Path(getattr(self, 'prototype_lab_desktop_selected', self._prototype_lab_root()) or self._prototype_lab_root())
        if target.is_dir():
            self._prototype_lab_set_path(target)
        elif target.suffix.lower() == '.py':
            self._prototype_lab_run_selected()
        return 'break'

    def _prototype_lab_open_selected_system(self) -> None:
        target = Path(getattr(self, 'prototype_lab_desktop_selected', self._prototype_lab_root()) or self._prototype_lab_root())
        if target.is_file():
            target = target.parent
        try:
            self.open_path_in_explorer(target)
        except Exception:
            pass

    def _prototype_lab_run_selected(self) -> None:
        target = Path(getattr(self, 'prototype_lab_desktop_selected', self._prototype_lab_root()) or self._prototype_lab_root())
        entry = None
        app_name = target.stem or target.name or 'Prototype Lab'
        if target.is_dir():
            entry = self._find_game_entry_in_dir(target)
            app_name = target.name
        elif target.is_file() and target.suffix.lower() == '.py':
            entry = target
            app_name = target.stem
        if entry is None:
            try:
                self.show_transient_status('Select a runnable Python file or runnable prototype folder', 1200)
            except Exception:
                pass
            return
        try:
            self.launch_python_entry(entry, app_name, panel_key=f"prototype_lab_desktop_{self._panel_key_for_minigame(app_name)}")
            if getattr(self, 'display_status_var', None) is not None:
                self.display_status_var.set(f'Launched {app_name} from MXOS desktop')
        except Exception:
            CRASH_REPORTER.write_exception('Prototype Lab Desktop Launch Failed', *sys.exc_info())
            self._prototype_lab_render_preview(entry)

    def open_prototype_lab_explorer(self) -> None:
        target = self._prototype_lab_root()
        try:
            target.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        try:
            self.active_shell_section = "gxmachine"
            self._activate_shell_section("gxmachine")
        except Exception:
            pass
        self._prototype_lab_set_path(target)
        try:
            self.show_transient_status(f"MXOS desktop focused on {target.name}", 1400)
        except Exception:
            pass
        try:
            if getattr(self, 'desktop_frame', None) is not None:
                self.desktop_frame.lift()
        except Exception:
            pass


    def open_path_in_explorer(self, path: Path) -> None:
        path = Path(path).resolve()
        try:
            if os.name == "nt":
                os.startfile(str(path))
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except Exception:
            CRASH_REPORTER.write_exception("MatrixCore Open Folder", *sys.exc_info())

    def create_embedded_window(self, key: str, title: str, width: int = 760, height: int = 460, title_color: str = "#f0f0f0", aspect_ratio=None, keep_on_top: bool = False):
        existing = self.embedded_windows.get(key)
        if existing is not None and existing.winfo_exists():
            existing.lift()
            return existing
        win = tk.Toplevel(self.root)
        win.title(title)
        win.configure(bg="#181818")
        win.geometry(f"{width}x{height}")
        body = Frame(win, bg="#101010")
        body.pack(fill=BOTH, expand=True)
        win.body = body
        self.embedded_windows[key] = win
        return win

    def minimize_embedded_window(self, key: str, title: str = "") -> None:
        win = self.embedded_windows.get(key)
        if win is not None and win.winfo_exists():
            win.iconify()

    def find_or_create_thumbnail(self, folder: Path) -> Path:
        for cand in [folder / "thumbnail.png", folder / "cover.png", folder / "screenshot.png", DEFAULT_BUNDLED_WALLPAPER]:
            if cand.exists():
                return cand
        return DEFAULT_BUNDLED_WALLPAPER

    def _required_modules_for_entry(self, entry_abs: Path) -> tuple[str, ...]:
        return gx_runtime.required_modules_for_entry(entry_abs)

    def _python_launch_candidates(self) -> list[list[str]]:
        candidates: list[list[str]] = []
        seen: set[tuple[str, ...]] = set()

        def add(cmd: list[str]) -> None:
            if not cmd:
                return
            key = tuple(str(part) for part in cmd)
            if key in seen:
                return
            seen.add(key)
            candidates.append([str(part) for part in cmd])

        # Portable EXE rule: prefer the bundled child runner.
        # In a frozen build, sys.executable may be GXPrototypeLab.exe; using
        # that as Python can reopen the launcher instead of running HoloVerse.
        runner_names = ('py_runner.exe', 'py_runner') if os.name == 'nt' else ('py_runner', 'py_runner.exe')
        runner_roots: list[Path] = []
        for base in (APP_BASE_DIR, RESOURCE_BASE_DIR, Path.cwd()):
            try:
                b = Path(base).resolve()
                if b not in runner_roots:
                    runner_roots.append(b)
            except Exception:
                pass
        try:
            exe_parent = Path(sys.executable).resolve().parent
            for base in (exe_parent, exe_parent.parent):
                if base not in runner_roots:
                    runner_roots.append(base)
        except Exception:
            pass
        for base in runner_roots:
            for rel_parent in (Path('py_runner'), Path('.')):
                for runner_name in runner_names:
                    runner = base / rel_parent / runner_name
                    try:
                        if runner.exists() and runner.is_file():
                            add([str(runner.resolve())])
                    except Exception:
                        pass

        current_exec = str(Path(sys.executable).resolve()) if sys.executable else ''
        current_is_frozen_launcher = bool(getattr(sys, 'frozen', False)) and Path(current_exec).name.lower().startswith('gxprototype')
        if current_exec:
            exec_path = Path(current_exec)
            if os.name == 'nt':
                pythonexe = exec_path.with_name('python.exe')
                if pythonexe.exists():
                    add([str(pythonexe)])
                if not current_is_frozen_launcher and exec_path.name.lower() != 'pythonw.exe':
                    add([current_exec])
                pythonw = exec_path.with_name('pythonw.exe')
                if pythonw.exists():
                    add([str(pythonw)])
            else:
                if not current_is_frozen_launcher:
                    add([current_exec])
        if os.name == 'nt':
            add(['py', '-3'])
            add(['python'])
            add(['pythonw'])
        else:
            add(['python3'])
            add(['python'])

        # Last resort: the patched GXPrototypeLab.py can act as a script runner
        # if an older frozen launch route still calls GXPrototypeLab.exe main.py.
        if current_exec and current_is_frozen_launcher:
            add([current_exec])
        return candidates

    def _command_supports_modules(self, base_cmd: list[str], modules: tuple[str, ...]) -> bool:
        probe = 'import importlib.util,sys;mods=' + repr(list(modules)) + ';missing=[m for m in mods if importlib.util.find_spec(m) is None];sys.exit(0 if not missing else 1)'
        try:
            proc = subprocess.run(base_cmd + ['-c', probe], capture_output=True, text=True, timeout=12)
            return proc.returncode == 0
        except Exception:
            return False

    def _resolve_python_command(self, entry_abs: Path) -> list[str]:
        # Interactive launch rule: never run slow Python/module probes on the UI
        # thread. A previous pass tried to "preflight" each launch by starting
        # one or more Python interpreters before opening the actual game. When a
        # user clicked several cards, those probes stacked, burned CPU, and then
        # released a pile of delayed game processes. Launch immediately and let
        # the child crash log report a real missing dependency.
        candidates = self._python_launch_candidates()
        if candidates:
            return candidates[0]
        return [str(sys.executable or "python")]

    def _interactive_child_creationflags(self) -> int:
        # Do not use CREATE_NO_WINDOW for playable games. That was the real
        # source of the invisible/background Python processes: games were alive
        # but their windows could be suppressed, leaving CPU-heavy children the
        # user could not see or close. Keep only a process group so shutdown can
        # target the launch cleanly.
        if os.name != 'nt':
            return 0
        return getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0)

    def _interactive_child_startupinfo(self):
        # Returning None intentionally avoids STARTF_USESHOWWINDOW/SW_HIDE for
        # game processes. Helper tools may still hide their console elsewhere,
        # but launched games must be visible.
        return None

    def _terminate_process_tree(self, proc: subprocess.Popen | None, label: str = '') -> None:
        if proc is None or proc.poll() is not None:
            return
        if os.name == 'nt':
            try:
                subprocess.run(
                    ['taskkill', '/PID', str(proc.pid), '/T', '/F'],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=4,
                    creationflags=_hidden_creationflags(),
                    startupinfo=_windows_hidden_startupinfo(),
                )
                return
            except Exception:
                pass
        try:
            proc.terminate()
            try:
                proc.wait(timeout=1.5)
            except subprocess.TimeoutExpired:
                proc.kill()
        except Exception:
            CRASH_REPORTER.write_exception(f'MatrixCore child shutdown failed: {label}', *sys.exc_info())

    def _clear_dead_children(self) -> None:
        dead = [key for key, proc in self.current_games.items() if proc is None or proc.poll() is not None]
        for key in dead:
            self.current_games.pop(key, None)
        if self.current_game is not None and self.current_game.poll() is not None:
            self.current_game = None
            self.current_game_name = ''

    def launch_python_entry(self, entry_main: Path, app_name: str, immersive: bool = False, panel_key: str | None = None, extra_args: list[str] | None = None, extra_env: dict[str, str] | None = None, child_window_mode: str | None = None) -> None:
        self._clear_dead_children()
        entry_abs = Path(entry_main).resolve()
        process_key = str(entry_abs).lower()
        existing_proc = self.current_games.get(process_key)
        if existing_proc is not None and existing_proc.poll() is None:
            try:
                self.show_transient_status(f"{app_name} is already running. Close it before launching another copy.", 1600)
            except Exception:
                pass
            return
        launch_key = process_key
        now = time.time()
        recent = getattr(self, '_recent_launch_keys', {})
        last_launch = float(recent.get(launch_key, 0.0) or 0.0)
        if now - last_launch < 2.0:
            try:
                self.show_transient_status(f"Already launching {app_name}...", 1000)
            except Exception:
                pass
            return
        recent[launch_key] = now
        self._recent_launch_keys = recent
        env = os.environ.copy()
        requested_mode = str(child_window_mode or ('immersive' if immersive else 'external')).strip().lower() or 'external'
        # Most Prototype Lab launches are normal external child windows.  The previous
        # pass marked every child as an embedded host window, which made some apps hide,
        # return immediately, or wait on host behavior they were not actually receiving.
        if requested_mode in {'embedded', 'immersive'}:
            env[MATRIXCORE_HOST_ENV_FLAG] = '1'
        else:
            env.pop(MATRIXCORE_HOST_ENV_FLAG, None)
        env[MATRIXCORE_WINDOW_MODE_ENV_FLAG] = requested_mode
        if panel_key:
            env[MATRIXCORE_PANEL_ENV_FLAG] = str(panel_key)
        # Compatibility flags used by older bundled prototypes that refuse direct
        # standalone execution unless they know a Matrix/Pygame launcher started them.
        env.setdefault("PYGAME_OS_LAUNCHER", "1")
        env.setdefault("GX_PROTOTYPE_LAB_LAUNCHER", "1")
        env.setdefault("MATRIXCORE_LAUNCHER", "1")
        env.setdefault("DREAMCRAWLER_ALLOW_STANDALONE", "1")
        # Prototypes launched from Prototype Lab must not trap the desktop mouse
        # by default. Updated bundled prototypes honor these flags; older ones
        # still launch visibly because we no longer hide child windows.
        env.setdefault("GX_DISABLE_MOUSE_CAPTURE", "1")
        env.setdefault("GLITCHED_MATRIX_DISABLE_MOUSE_CAPTURE", "1")
        env.setdefault("SDL_VIDEO_CENTERED", "1")
        env.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
        # Put shared app/HoloVerse support modules on PYTHONPATH for standalone mode
        # routes such as Fractured Dimension that optionally import holoverse helpers.
        py_paths = []
        for p in (entry_abs.parent, DATA_ROOT_DIR, HOLOVERSE_DIR, getattr(gx_runtime, "PROTOTYPE_LAB_DIR", DATA_ROOT_DIR / "Prototype Lab")):
            try:
                if p and Path(p).exists():
                    sp = str(Path(p).resolve())
                    if sp not in py_paths:
                        py_paths.append(sp)
            except Exception:
                pass
        existing_pp = env.get("PYTHONPATH", "").strip()
        if existing_pp:
            py_paths.append(existing_pp)
        if py_paths:
            env["PYTHONPATH"] = os.pathsep.join(py_paths)
        if extra_env:
            env.update({str(k): str(v) for k, v in extra_env.items()})
        env["PYTHONUNBUFFERED"] = "1"
        env.setdefault("PYTHONIOENCODING", "utf-8")
        env.setdefault("GXPLAB_APP_DIR", str(APP_BASE_DIR))
        env.setdefault("GXPLAB_RESOURCE_DIR", str(RESOURCE_BASE_DIR))
        env.setdefault("GXPLAB_DATA_DIR", str(DATA_ROOT_DIR))
        preflight_cmd = [str(sys.executable or "python"), str(entry_abs)]
        if extra_args:
            preflight_cmd.extend([str(a) for a in extra_args])
        session_log = CRASH_REPORTER.start_game_log(
            app_name,
            entry_abs,
            preflight_cmd,
            entry_abs.parent,
            {
                "stage": "launcher_preflight",
                "panel_key": str(panel_key or ""),
                "window_mode": env.get(MATRIXCORE_WINDOW_MODE_ENV_FLAG, ""),
                "embedded_host": env.get(MATRIXCORE_HOST_ENV_FLAG, ""),
                "PYGAME_OS_LAUNCHER": env.get("PYGAME_OS_LAUNCHER", ""),
                "HOLOVERSE_NO_VR": env.get("HOLOVERSE_NO_VR", ""),
                "MATRIX_GAME_FULLSCREEN": env.get("MATRIX_GAME_FULLSCREEN", ""),
                "MATRIX_GAME_BORDERLESS": env.get("MATRIX_GAME_BORDERLESS", ""),
                "MATRIX_GAME_BORDERED_FULLSCREEN": env.get("MATRIX_GAME_BORDERED_FULLSCREEN", ""),
                "PYTHONPATH_HAS_HOLOVERSE": "1" if str(HOLOVERSE_DIR) in env.get("PYTHONPATH", "") else "0",
            },
        )
        try:
            missing_internal = gx_runtime.entry_missing_internal_imports(entry_abs)
            if missing_internal:
                CRASH_REPORTER.append_game_log(
                    session_log,
                    "\n[launcher] Static import scan warning; launch will continue and the child crash hook will capture any real failure: "
                    + ', '.join(missing_internal),
                )
            python_cmd = self._resolve_python_command(entry_abs)
            cmd = [*python_cmd, str(entry_abs)]
            if extra_args:
                cmd.extend([str(a) for a in extra_args])
            CRASH_REPORTER.append_game_log(session_log, "\n[launcher] Preflight passed. Resolved command:\n" + " ".join(str(c) for c in cmd))
        except Exception:
            preflight_trace = "".join(traceback.format_exception(*sys.exc_info()))
            CRASH_REPORTER.finish_game_log(app_name, session_log, None, "Launcher preflight failed before child process start.\n\n" + preflight_trace)
            raise
        env["GX_CHILD_CRASH_LOG"] = str(session_log)
        env["GX_CHILD_APP_NAME"] = str(app_name)
        popen_kwargs = {
            'cwd': str(entry_abs.parent),
            'env': env,
            'creationflags': self._interactive_child_creationflags(),
            'stdin': subprocess.DEVNULL,
            'stdout': subprocess.PIPE,
            'stderr': subprocess.STDOUT,
            'text': True,
            'encoding': 'utf-8',
            'errors': 'replace',
            'bufsize': 1,
        }
        startupinfo = self._interactive_child_startupinfo()
        if startupinfo is not None:
            popen_kwargs['startupinfo'] = startupinfo
        try:
            proc = subprocess.Popen(cmd, **popen_kwargs)
        except Exception:
            try:
                CRASH_REPORTER.finish_game_log(app_name, session_log, None, traceback.format_exc())
            except Exception:
                pass
            raise
        self.current_game = proc
        self.current_game_name = app_name
        self.current_games[process_key] = proc

        def _watch_child_process() -> None:
            log_text = ''
            child_direct_text = ''
            try:
                out, _ = proc.communicate()
                log_text = out or ''
            except Exception:
                log_text = traceback.format_exc()
            rc = proc.poll()
            try:
                if session_log is not None and Path(session_log).exists():
                    child_direct_text = Path(session_log).read_text(encoding='utf-8', errors='replace')
            except Exception:
                child_direct_text = ''
            header = [
                f"Game: {app_name}",
                f"Entry: {entry_abs}",
                f"CWD: {entry_abs.parent}",
                f"Command: {' '.join(str(c) for c in cmd)}",
                f"Return code: {rc}",
                "",
            ]
            payload = "\n".join(header) + (log_text or "No stdout/stderr text was captured from the child process.")
            expected_shutdown = bool(getattr(self, 'is_closing', False))
            try:
                CRASH_REPORTER.finish_game_log(app_name, session_log, rc, payload, child_direct_text, expected_shutdown=expected_shutdown)
            except Exception:
                pass
            if rc not in (0, None) and not expected_shutdown:
                try:
                    CRASH_REPORTER.write_game_crash_bundle(app_name, rc, payload + ("\n\n" + child_direct_text if child_direct_text.strip() else ""))
                except Exception:
                    pass
            try:
                self.current_games.pop(process_key, None)
                self._recent_launch_keys.pop(launch_key, None)
            except Exception:
                pass
        try:
            threading.Thread(target=_watch_child_process, name=f"gx-watch-{app_name}", daemon=True).start()
        except Exception:
            pass

    def request_close(self) -> None:
        if self.is_closing:
            return
        self.is_closing = True
        self._clear_dead_children()
        seen_pids: set[int] = set()
        for key, proc in list(self.current_games.items()):
            try:
                pid = int(getattr(proc, 'pid', 0) or 0)
            except Exception:
                pid = 0
            if pid and pid in seen_pids:
                continue
            if pid:
                seen_pids.add(pid)
            try:
                self._terminate_process_tree(proc, str(key))
            except Exception:
                CRASH_REPORTER.write_exception(f'MatrixCore child shutdown failed: {key}', *sys.exc_info())
        self.current_games.clear()
        try:
            proc = self.current_game
            pid = int(getattr(proc, 'pid', 0) or 0) if proc is not None else 0
            if proc is not None and pid not in seen_pids:
                self._terminate_process_tree(proc, 'primary child')
        except Exception:
            CRASH_REPORTER.write_exception('MatrixCore primary child shutdown failed', *sys.exc_info())
        self.current_game = None
        self.current_game_name = ''
        try:
            self._recent_launch_keys.clear()
        except Exception:
            pass
        for key, win in list(self.embedded_windows.items()):
            try:
                if win is not None and win.winfo_exists():
                    win.destroy()
            except Exception:
                pass
        self.embedded_windows.clear()
        try:
            self.root.quit()
        except Exception:
            pass
        try:
            self.root.destroy()
        except Exception:
            pass

    def _resolve_game_main_by_name(self, name: str) -> Path | None:
        for root in external_game_source_roots(include_generated=True, include_legacy=False):
            folder = root / name
            candidates = [
                folder / "main.py",
                folder / "launcher.py",
                folder / "app.py",
                folder / "antiheroes_tools_menu.py",
                folder / "tools_menu.py",
                folder / f"{folder.name}.py",
                folder / f"{folder.name.replace(' ', '')}.py",
                folder / f"{folder.name.replace(' ', '_')}.py",
            ]
            for cand in candidates:
                try:
                    if cand.exists() and cand.is_file():
                        return cand
                except Exception:
                    continue
        return None

    def get_dreamcrawler2d_main(self) -> Path | None:
        return self._resolve_game_main_by_name("DreamCrawler2D")
    def get_blockbusters_main(self) -> Path | None:
        return self._resolve_game_main_by_name("Block Busters")
    def get_mewtants_main(self) -> Path | None:
        return self._resolve_game_main_by_name("Mewtants") or self._resolve_game_main_by_name("MewtantsCoop")
    def get_blood_dojo_main(self) -> Path | None:
        return self._resolve_game_main_by_name("Blood Dojo")
    def get_journey_of_4_main(self) -> Path | None:
        return self._resolve_game_main_by_name("Journey of 4")
    def get_gamegen_main(self) -> Path | None:
        tools = generation_tool_candidates()
        return tools[0][1] if tools else None
    def launch_dreamcrawler_coop(self) -> None:
        p = self.get_dreamcrawler2d_main();
        p and self.launch_python_entry(p, "DreamCrawler2D")



class MXOSOnlyShell:
    """Left-dock launcher shell for the cleaned MXOS-only Prototype Lab build."""

    THEME = {
        "bg": "#020304",
        "dock": "#030506",
        "dock_alt": "#071012",
        "panel": "#05090b",
        "panel_alt": "#0b1418",
        "line": "#303a3c",
        "text": "#e8f4f6",
        "muted": "#91a6ad",
        "accent": "#efff3f",
        "cyan": "#21d8e8",
        "warn": "#ff9d57",
        "danger": "#ff4a4a",
    }

    def __init__(self, launcher: MatrixCoreStandaloneLauncher, parent: tk.Misc, root: tk.Misc | None = None) -> None:
        self.launcher = launcher
        self.parent = parent
        self.root = root or parent.winfo_toplevel()
        self.running = True
        self.shell_hotspot_debug = False
        self.history: list[Path] = []
        self.history_index = -1
        self.current_path = APP_BASE_DIR / "data" / "Prototype Lab"
        self.selected_path: Path | None = None
        self.active_panel = "home"
        self.status_var = StringVar(value="Ready.")
        self.path_var = StringVar(value="")
        self.preview_var = StringVar(value="Select a file or folder.")
        self._brand_photo = None
        self._panel_icon = None
        self._dock_button_images: dict[tuple[str, int, int], object] = {}
        self._dock_button_texture_paths: dict[str, Path] = {}
        self._dock_bg_photo = None
        self._dock_section_photos: dict[tuple[str, int, int], object] = {}
        self._workarea = _primary_monitor_workarea()
        self._dock_width = self._calc_dock_width()
        self._content_width = self._calc_content_width()
        self._height = max(640, int(self._workarea[3]))
        self.tree = None
        self.preview = None
        self.game_card_photos: list[object] = []
        self.prototype_games: list[dict] = []
        self.selected_game_record: dict | None = None
        self._ensure_dock_button_texture_files()
        self._build_ui()
        self._set_window_geometry(expanded=False)

    def shutdown(self) -> None:
        self.running = False

    def _append_chat(self, speaker: str, message: str) -> None:
        self.status_var.set(f"{speaker}: {message}")

    def _update_shell_hotspot_debug_widgets(self) -> None:
        return

    def _calc_dock_width(self) -> int:
        _x, _y, w, _h = self._workarea
        return max(560, min(1120, int(w * 0.34)))

    def _calc_content_width(self) -> int:
        _x, _y, w, _h = self._workarea
        return max(760, int(w) - self._calc_dock_width())

    def _set_window_geometry(self, *, expanded: bool) -> None:
        try:
            x, y, wa_w, wa_h = _primary_monitor_workarea()
            dock_w = self._calc_dock_width()
            content_w = max(760, int(wa_w) - int(dock_w)) if expanded else 0
            width = int(wa_w) if expanded else int(dock_w)
            height = max(640, wa_h)
            self._dock_width = dock_w
            self._content_width = max(0, width - dock_w)
            self._height = height
            try:
                self._dock_section_photos.clear()
            except Exception:
                pass
            self.root.overrideredirect(False)
            try:
                self.root.attributes("-fullscreen", False)
            except Exception:
                pass
            try:
                self.root.state("normal")
            except Exception:
                pass
            try:
                self.root.minsize(min(520, width), min(520, height))
            except Exception:
                pass
            self.root.geometry(f"{width}x{height}+{x}+{y}")
            if hasattr(self, "dock"):
                self.dock.configure(width=dock_w)
            if hasattr(self, "content"):
                self.content.configure(width=max(560, self._content_width or self._calc_content_width()))
            self.root.update_idletasks()
        except Exception:
            CRASH_REPORTER.write_exception("Left dock geometry failed", *sys.exc_info())

    def _safe_rel_path(self, path: Path) -> str:
        try:
            return str(Path(path).resolve().relative_to(APP_BASE_DIR.resolve()))
        except Exception:
            return str(path)

    def _format_size(self, path: Path) -> str:
        try:
            if not path.is_file():
                return ""
            size = int(path.stat().st_size)
        except Exception:
            return ""
        units = ["B", "KB", "MB", "GB"]
        value = float(size)
        for unit in units:
            if value < 1024 or unit == units[-1]:
                return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
            value /= 1024
        return str(size)

    def _mtime(self, path: Path) -> str:
        try:
            return time.strftime("%Y-%m-%d %H:%M", time.localtime(path.stat().st_mtime))
        except Exception:
            return ""

    def _kind(self, path: Path) -> str:
        if path.is_dir():
            return "Runnable Folder" if (path / "main.py").exists() else "Folder"
        if path.suffix.lower() == ".py":
            return "Python"
        if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}:
            return "Image"
        if path.suffix.lower() in {".txt", ".md", ".log"}:
            return "Text"
        if path.suffix.lower() in {".json", ".toml", ".yaml", ".yml", ".ini", ".cfg"}:
            return "Config"
        return "File"

    def _asset_candidates(self, *names: str) -> list[Path]:
        candidates: list[Path] = []
        bases = [
            APP_BASE_DIR,
            RESOURCE_BASE_DIR,
            APP_BASE_DIR / "assets",
            RESOURCE_BASE_DIR / "assets",
            APP_BASE_DIR / "assets" / "icons",
            RESOURCE_BASE_DIR / "assets" / "icons",
        ]
        for base in bases:
            for name in names:
                candidates.append(base / name)
        return candidates

    def _find_logo_image(self) -> Path | None:
        names = (
            "launcher_logo.png",
            "GXPrototypeLab_window.png",
            "GXPrototypeLab.png",
            "matrixos_window.png",
            "matrixos.png",
        )
        for candidate in self._asset_candidates(*names):
            try:
                if candidate.exists() and candidate.is_file():
                    return candidate
            except Exception:
                continue
        return None

    def _build_ui(self) -> None:
        self.parent.configure(bg=self.THEME["bg"])
        self.parent.grid_rowconfigure(0, weight=1)
        self.parent.grid_columnconfigure(0, weight=0)
        self.parent.grid_columnconfigure(1, weight=1)

        self.dock = Frame(self.parent, bg=self.THEME["dock"], width=self._dock_width, bd=0, highlightthickness=0)
        self.dock.grid(row=0, column=0, sticky="nsw")
        self.dock.grid_propagate(False)
        self.dock.grid_rowconfigure(0, weight=0)
        self.dock.grid_rowconfigure(1, weight=1)
        self.dock.grid_rowconfigure(2, weight=0)
        self.dock.grid_columnconfigure(0, weight=1)

        self.brand_canvas = Canvas(self.dock, bg=self.THEME["dock"], bd=0, highlightthickness=0, height=310)
        self.brand_canvas.grid(row=0, column=0, sticky="ew", padx=0, pady=0)
        self.brand_canvas.bind("<Configure>", self._draw_brand_header, add="+")

        button_area = Canvas(self.dock, bg=self.THEME["dock"], bd=0, highlightthickness=0, relief="flat")
        button_area.grid(row=1, column=0, sticky="nsew", padx=0, pady=0)
        self.button_area_canvas = button_area

        button_stack = Frame(button_area, bg=self.THEME["dock"], bd=0, highlightthickness=0)
        self.button_stack_window = button_area.create_window(58, 10, anchor="nw", window=button_stack)
        button_stack.grid_columnconfigure(0, weight=1)

        def _layout_button_stack(_event=None):
            try:
                w = max(320, int(button_area.winfo_width() or self._dock_width))
                h = max(420, int(button_area.winfo_height() or 520))
                self._paint_dock_panel_background(button_area, "buttons")
                button_area.coords(self.button_stack_window, 58, 10)
                button_area.itemconfigure(self.button_stack_window, width=max(260, w - 116), height=max(360, h - 30))
            except Exception:
                pass

        button_area.bind("<Configure>", _layout_button_stack, add="+")
        try:
            button_area.after_idle(_layout_button_stack)
        except Exception:
            _layout_button_stack()

        self._big_button(button_stack, "HOLOVERSE", self.open_holoverse, accent=True, texture_key="holoverse")
        self._big_button(button_stack, "PROTOTYPE LAB", self.open_prototype_panel, texture_key="prototype_lab")
        self._big_button(button_stack, "MATRIXCORE", self.open_matrixcore_panel, texture_key="matrixcore")
        self._big_button(button_stack, "MXOS", self.open_mxos_panel, texture_key="mxos")
        self._big_button(button_stack, "X", self._request_close, danger=True, narrow=True, texture_key="exit")

        footer = Frame(self.dock, bg=self.THEME["dock"])
        footer.grid(row=2, column=0, sticky="ew", padx=32, pady=(0, 26))
        footer.grid_columnconfigure(0, weight=1)
        Label(
            footer,
            textvariable=self.status_var,
            bg=self.THEME["dock"],
            fg=self.THEME["muted"],
            font=("Segoe UI", 10),
            justify="center",
            wraplength=max(320, self._dock_width - 80),
        ).grid(row=0, column=0, sticky="ew")
        Label(
            footer,
            text="Clean build: no ChatSpace, no non-MXOS generation, no salvage lanes.",
            bg=self.THEME["dock"],
            fg="#59666a",
            font=("Segoe UI", 8),
            justify="center",
            wraplength=max(320, self._dock_width - 80),
        ).grid(row=1, column=0, sticky="ew", pady=(8, 0))

        self.content = Frame(
            self.parent,
            bg=self.THEME["bg"],
            width=self._content_width,
            bd=0,
            highlightthickness=2,
            highlightbackground=self.THEME["line"],
        )
        self.content.grid(row=0, column=1, sticky="nsew")
        self.content.grid_remove()
        self.content.grid_propagate(False)

    def _draw_brand_header(self, _event=None) -> None:
        canvas = getattr(self, "brand_canvas", None)
        if canvas is None:
            return
        try:
            w = max(420, int(canvas.winfo_width() or self._dock_width))
            h = max(260, int(canvas.winfo_height() or 310))
            canvas.delete("all")
            self._paint_dock_panel_background(canvas, "header")
            for y in range(18, h, 54):
                canvas.create_rectangle(0, y, w, y + 2, fill="#0a0d0e", outline="")
            for x in range(-80, w + 120, 72):
                canvas.create_line(x, h, x + 140, 0, fill="#071216", width=1)

            logo_path = self._find_logo_image()
            if logo_path is not None and Image is not None and ImageTk is not None:
                try:
                    img = Image.open(logo_path).convert("RGBA")
                    max_size = (max(260, w - 70), 205)
                    fitted = ImageOps.contain(img, max_size, method=Image.Resampling.LANCZOS)
                    self._brand_photo = ImageTk.PhotoImage(fitted)
                    canvas.create_image(w // 2, 112, image=self._brand_photo, anchor="center")
                except Exception:
                    self._brand_photo = None

            if self._brand_photo is None:
                canvas.create_text(w // 2, 62, text="GLITCHED", fill=self.THEME["accent"], font=("Impact", 42), anchor="center")
                canvas.create_text(w // 2, 112, text="MATRIX", fill=self.THEME["accent"], font=("Impact", 48), anchor="center")
                canvas.create_text(w // 2, 160, text="PROTOTYPE LAB", fill=self.THEME["accent"], font=("Consolas", 20, "bold"), anchor="center")

            cx = w // 2
            cy = h - 54
            for r, color in ((92, "#120907"), (72, "#1a0f0b"), (48, "#0d1517"), (18, "#32f7ff")):
                canvas.create_oval(cx - r, cy - r, cx + r, cy + r, outline=color, width=2)
            canvas.create_oval(cx - 9, cy - 9, cx + 9, cy + 9, fill="#efff3f", outline="")
            canvas.create_line(34, h - 3, w - 34, h - 3, fill="#33393a", width=2)
        except Exception:
            pass

    def _dock_panel_asset_path(self) -> Path | None:
        candidates = [
            APP_BASE_DIR / "data" / "assets" / "textures" / "mxos_popup_panel.png",
            RESOURCE_BASE_DIR / "data" / "assets" / "textures" / "mxos_popup_panel.png",
            APP_BASE_DIR / "data" / "assets" / "textures" / "mxos_desktop_wallpaper.png",
            RESOURCE_BASE_DIR / "data" / "assets" / "textures" / "mxos_desktop_wallpaper.png",
        ]
        for candidate in candidates:
            try:
                if candidate.exists() and candidate.is_file():
                    return candidate
            except Exception:
                continue
        return None

    def _make_dock_panel_photo(self, width: int, height: int, section: str = "full"):
        if Image is None or ImageTk is None:
            return None
        width = max(64, int(width or 64))
        height = max(64, int(height or 64))
        cache_key = (section, width, height)
        cached = self._dock_section_photos.get(cache_key)
        if cached is not None:
            return cached
        path = self._dock_panel_asset_path()
        if path is None:
            return None
        try:
            src = Image.open(path).convert("RGBA")
            ratio = max(0.18, min(0.48, float(self._dock_width) / float(max(1, self._workarea[2]))))
            panel_w = max(1, min(src.width, int(src.width * ratio)))
            crop = src.crop((0, 0, panel_w, src.height))
            fitted = ImageOps.fit(crop, (width, height), method=Image.Resampling.LANCZOS)
            veil = Image.new("RGBA", fitted.size, (0, 0, 0, 72))
            fitted.alpha_composite(veil)
            photo = ImageTk.PhotoImage(fitted)
            self._dock_section_photos[cache_key] = photo
            return photo
        except Exception:
            CRASH_REPORTER.write_exception("Dock panel background failed", *sys.exc_info())
            return None

    def _paint_dock_panel_background(self, canvas: tk.Canvas, section: str = "full") -> None:
        try:
            w = max(64, int(canvas.winfo_width() or self._dock_width))
            h = max(64, int(canvas.winfo_height() or self._height))
            canvas.delete("dock_bg")
            photo = self._make_dock_panel_photo(w, h, section)
            if photo is not None:
                canvas.create_image(0, 0, image=photo, anchor="nw", tags=("dock_bg",))
                canvas.lower("dock_bg")
            else:
                canvas.create_rectangle(0, 0, w, h, fill=self.THEME["dock"], outline="", tags=("dock_bg",))
        except Exception:
            pass

    def _dock_texture_dir(self) -> Path:
        return APP_BASE_DIR / "data" / "assets" / "textures"

    def _dock_button_specs(self) -> dict[str, dict[str, str]]:
        cyan = self.THEME["cyan"]
        return {
            "holoverse": {"label": "HOLOVERSE", "base": "#06171b", "line": cyan, "accent": cyan},
            "prototype_lab": {"label": "PROTOTYPE LAB", "base": "#06171b", "line": cyan, "accent": cyan},
            "matrixcore": {"label": "MATRIXCORE", "base": "#06171b", "line": cyan, "accent": cyan},
            "mxos": {"label": "MXOS", "base": "#06171b", "line": cyan, "accent": cyan},
            "exit": {"label": "X", "base": "#06171b", "line": cyan, "accent": cyan},
        }

    def _dock_button_texture_path(self, key: str) -> Path:
        return self._dock_texture_dir() / f"dock_button_{key}.png"

    def _ensure_dock_button_texture_files(self) -> None:
        if Image is None or ImageDraw is None:
            return
        texture_dir = self._dock_texture_dir()
        try:
            texture_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            return
        guide_path = texture_dir / "dock_button_textures_README.txt"
        if not guide_path.exists():
            try:
                guide_path.write_text(
                    """Custom launcher button textures
================================

Edit these PNG files to reskin the five main left-panel buttons.
The launcher looks for files named:
- dock_button_holoverse.png
- dock_button_prototype_lab.png
- dock_button_matrixcore.png
- dock_button_mxos.png
- dock_button_exit.png

Keep them as wide horizontal designs. The launcher automatically resizes them so they fit within the button borders.
""",
                    encoding="utf-8",
                )
            except Exception:
                pass
        for key, spec in self._dock_button_specs().items():
            out_path = self._dock_button_texture_path(key)
            self._dock_button_texture_paths[key] = out_path
            if out_path.exists():
                continue
            try:
                self._write_dock_button_texture_template(out_path, spec["label"], spec["base"], spec["line"], spec["accent"])
            except Exception:
                CRASH_REPORTER.write_exception(f"Dock button texture generation failed: {out_path}", *sys.exc_info())

    def _write_dock_button_texture_template(self, out_path: Path, label: str, base_hex: str, line_hex: str, accent_hex: str) -> None:
        if Image is None or ImageDraw is None:
            return
        w, h = 1600, 420
        base_rgba = ImageColor.getrgb(base_hex) + (255,)
        line_rgba = ImageColor.getrgb(line_hex) + (255,)
        accent_rgba = ImageColor.getrgb(accent_hex) + (255,)
        img = Image.new("RGBA", (w, h), base_rgba)
        draw = ImageDraw.Draw(img)

        for y in range(h):
            alpha = 12 + int(30 * (y / max(1, h - 1)))
            draw.line((0, y, w, y), fill=(0, 0, 0, alpha), width=1)
        for x in range(0, w, 64):
            draw.line((x, 0, x, h), fill=(255, 255, 255, 12), width=1)
        for y in range(0, h, 32):
            draw.line((0, y, w, y), fill=(255, 255, 255, 9), width=1)

        margin = 14
        inner = (margin, margin, w - margin, h - margin)
        draw.rounded_rectangle(inner, radius=34, outline=line_rgba, width=6, fill=(0, 0, 0, 26))
        draw.rounded_rectangle((margin + 12, margin + 12, w - margin - 12, h - margin - 12), radius=28, outline=(255, 255, 255, 18), width=2)

        cx, cy = 120, h // 2
        for r, outline in ((88, line_rgba), (62, (255, 255, 255, 26)), (34, accent_rgba)):
            draw.ellipse((cx - r, cy - r, cx + r, cy + r), outline=outline, width=4 if r == 88 else 2)
        draw.ellipse((cx - 10, cy - 10, cx + 10, cy + 10), fill=accent_rgba)
        draw.line((200, cy - 1, w - 64, cy - 1), fill=(255, 255, 255, 20), width=1)

        try:
            font_big = ImageFont.truetype("arialbd.ttf", 78)
            font_small = ImageFont.truetype("consolab.ttf", 24)
        except Exception:
            font_big = ImageFont.load_default()
            font_small = ImageFont.load_default()
        draw.text((252, cy - 44), label, fill=accent_rgba, font=font_big, anchor="lm")
        draw.text((252, cy + 30), out_path.name, fill=(220, 230, 234, 110), font=font_small, anchor="lm")

        out_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(out_path)

    def _get_dock_button_photo(self, key: str, width: int, height: int):
        if Image is None or ImageTk is None:
            return None
        width = max(64, int(width or 64))
        height = max(48, int(height or 48))
        cache_key = (key, width, height)
        cached = self._dock_button_images.get(cache_key)
        if cached is not None:
            return cached
        path = self._dock_button_texture_path(key)
        if not path.exists():
            return None
        try:
            src = Image.open(path).convert("RGBA")
            canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            pad_x = max(8, int(width * 0.018))
            pad_y = max(8, int(height * 0.045))
            inner_size = (max(24, width - pad_x * 2), max(24, height - pad_y * 2))
            # Use contain instead of fit: fit crops the custom art and can cut off the button border.
            fitted = ImageOps.contain(src, inner_size, method=Image.Resampling.LANCZOS)
            px = (width - fitted.width) // 2
            py = (height - fitted.height) // 2
            canvas.paste(fitted, (px, py), fitted)
            photo = ImageTk.PhotoImage(canvas)
            self._dock_button_images[cache_key] = photo
            return photo
        except Exception:
            CRASH_REPORTER.write_exception(f"Dock button texture load failed: {path}", *sys.exc_info())
            return None

    def _dock_button_bg_provider(self, key: str):
        def _provider(width, height, _widget=None):
            return self._get_dock_button_photo(key, width, height)
        return _provider

    def _big_button(self, parent: tk.Misc, text: str, command, *, accent: bool = False, danger: bool = False, narrow: bool = False, texture_key: str | None = None):
        bg = "#06171b"
        fg = self.THEME["cyan"]
        active_bg = "#07343c"
        edge = self.THEME["cyan"]
        if accent:
            bg = "#061b1f"
            fg = self.THEME["cyan"]
            active_bg = "#07414a"
            edge = self.THEME["cyan"]
        if danger:
            bg = "#06171b"
            fg = self.THEME["cyan"]
            active_bg = "#07343c"
            edge = self.THEME["cyan"]

        try:
            row = int(getattr(parent, "_gx_button_row", 0))
            setattr(parent, "_gx_button_row", row + 1)
            parent.grid_rowconfigure(row, weight=1, minsize=104 if narrow else 132)
            parent.grid_columnconfigure(0, weight=1)
        except Exception:
            row = 0

        provider = self._dock_button_bg_provider(texture_key) if texture_key else None
        height = 104 if narrow else 132
        width_hint = max(300, self._dock_width - 168)
        if provider is not None:
            btn = CyberButton(
                parent,
                text=text,
                command=command,
                panel_bg=self.THEME["dock"],
                bg=bg,
                fg=fg,
                hoverbackground=active_bg,
                activebackground=active_bg,
                activeforeground="#ffffff",
                outline=edge,
                font=("Consolas", 30 if not narrow else 26, "bold"),
                min_width=width_hint,
                height=height,
                text_pad=0,
                text_only=True,
                bg_image_provider=provider,
                text_anchor='center',
                cursor="hand2",
            )
            try:
                btn.canvas.configure(highlightthickness=0, bd=0)
            except Exception:
                pass
        else:
            btn = Button(
                parent,
                text=text,
                command=command,
                bg=bg,
                fg=fg,
                activebackground=active_bg,
                activeforeground="#ffffff",
                relief="flat",
                bd=0,
                highlightthickness=2,
                highlightbackground=edge,
                highlightcolor=self.THEME["cyan"] if not danger else self.THEME["danger"],
                padx=24,
                pady=22 if not narrow else 14,
                font=("Consolas", 30 if not narrow else 26, "bold"),
                anchor="center",
                justify="center",
                cursor="hand2",
            )
        try:
            btn.grid(row=row, column=0, sticky="nsew", padx=0, pady=(12, 12 if not narrow else 8), ipady=3 if not narrow else 0)
        except Exception:
            btn.pack(anchor="center", fill="x", pady=(0, 22 if not narrow else 8), ipadx=8, ipady=8)
        return btn

    def _clear_content(self) -> None:
        for child in list(self.content.winfo_children()):
            try:
                child.destroy()
            except Exception:
                pass
        self.tree = None
        self.preview = None

    def _show_content_shell(self, title: str, subtitle: str = "") -> Frame:
        self._clear_content()
        self.content.grid()
        self._set_window_geometry(expanded=True)
        self.content.grid_rowconfigure(1, weight=1)
        self.content.grid_columnconfigure(0, weight=1)

        header = Frame(self.content, bg="#020405", height=96, highlightthickness=0)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_propagate(False)
        header.grid_columnconfigure(0, weight=1)
        Label(header, text=title.upper(), bg="#020405", fg=self.THEME["accent"], font=("Consolas", 18, "bold")).grid(row=0, column=0, sticky="w", padx=24, pady=(16, 0))
        Label(header, text=subtitle, bg="#020405", fg=self.THEME["muted"], font=("Segoe UI", 10)).grid(row=1, column=0, sticky="w", padx=24, pady=(2, 12))
        Button(
            header,
            text="CLOSE PANEL",
            command=self.close_panel,
            bg="#11191d",
            fg="#dbecef",
            activebackground="#1b2d32",
            activeforeground="#ffffff",
            relief="flat",
            bd=0,
            padx=18,
            pady=8,
            font=("Consolas", 10, "bold"),
            cursor="hand2",
        ).grid(row=0, column=1, rowspan=2, sticky="e", padx=22, pady=22)

        body = Frame(self.content, bg=self.THEME["panel"], bd=0, highlightthickness=1, highlightbackground="#233236")
        body.grid(row=1, column=0, sticky="nsew", padx=18, pady=(0, 18))
        body.grid_rowconfigure(0, weight=1)
        body.grid_columnconfigure(0, weight=1)
        return body

    def close_panel(self) -> None:
        self._clear_content()
        try:
            self.content.grid_remove()
        except Exception:
            pass
        self.active_panel = "home"
        self.status_var.set("Panel closed.")
        self._set_window_geometry(expanded=False)

    def open_prototype_panel(self) -> None:
        self.active_panel = "prototype"
        body = self._show_content_shell("Prototype Lab", "All playable prototypes in one panel. Click a game card, then Run.")
        self._build_prototype_game_panel(body)
        self.status_var.set("Prototype Lab game list opened.")


    def _find_game_entry_in_dir(self, folder: Path) -> Path | None:
        folder = Path(folder)
        if not folder.exists() or not folder.is_dir():
            return None
        preferred = [
            folder / "main.py",
            folder / "launcher.py",
            folder / "app.py",
            folder / "antiheroes_tools_menu.py",
            folder / "tools_menu.py",
            folder / f"{folder.name}.py",
            folder / f"{folder.name.replace(' ', '')}.py",
            folder / f"{folder.name.replace(' ', '_')}.py",
        ]
        for candidate in preferred:
            try:
                if candidate.exists() and candidate.is_file():
                    return candidate
            except Exception:
                continue
        try:
            ignored = {"sound_handler.py", "sfx.py", "items.py", "insects.py", "battle.py", "map.py", "vehicles.py", "war_database.py", "specials_fx.py", "book.py", "hvh2.py", "earth.py"}
            py_files = sorted([p for p in folder.glob("*.py") if p.is_file() and p.name.lower() not in ignored], key=lambda p: p.name.lower())
            if len(py_files) == 1:
                return py_files[0]
        except Exception:
            pass
        return None

    def _find_game_screenshot(self, folder: Path) -> Path | None:
        folder = Path(folder)
        image_exts = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}
        direct_names = [
            "main_preview.png", "preview.png", "preview.jpg", "preview.webp",
            "screenshot.png", "screenshot.jpg", "screenshot.webp",
            "thumbnail.png", "thumb.png", "cover.png", "icon.png",
        ]
        direct_dirs = [folder, folder / "assets", folder / "assets" / "screens", folder / "assets" / "screenshots", folder / "screenshots", folder / "media"]
        for base in direct_dirs:
            for name in direct_names:
                try:
                    candidate = base / name
                    if candidate.exists() and candidate.is_file():
                        return candidate
                except Exception:
                    continue

        keywords = ("preview", "screenshot", "screen", "thumb", "thumbnail", "cover")
        checked = 0
        try:
            for candidate in folder.rglob("*"):
                checked += 1
                if checked > 900:
                    break
                if not candidate.is_file() or candidate.suffix.lower() not in image_exts:
                    continue
                low = candidate.name.lower()
                if any(key in low for key in keywords):
                    return candidate
        except Exception:
            pass
        return None

    def _discover_prototype_games(self) -> list[dict]:
        root = APP_BASE_DIR / "data" / "Prototype Lab"
        ignore_dirs = {
            "__pycache__", ".git", ".github", "assets", "asset", "images", "image", "textures",
            "sounds", "sound", "music", "media", "logs", "log", "crash_logs", "saves", "save",
            "levels", "level", "zones", "colonies", "patch_notes", "screenshots",
        }
        games: list[dict] = []
        seen_entries: set[str] = set()

        def add_game(folder: Path, display_name: str | None = None) -> None:
            try:
                entry = self._find_game_entry_in_dir(folder)
                if entry is None:
                    return
                key = str(entry.resolve()).lower()
                if key in seen_entries:
                    return
                seen_entries.add(key)
                screenshot = self._find_game_screenshot(folder)
                games.append({
                    "name": display_name or folder.name,
                    "folder": folder,
                    "entry": entry,
                    "screenshot": screenshot,
                    "modified": self._mtime(entry),
                    "path": self._safe_rel_path(folder),
                })
            except Exception:
                return

        try:
            for child in sorted(root.iterdir(), key=lambda p: p.name.lower()):
                if child.is_dir():
                    if child.name.lower() in ignore_dirs:
                        continue
                    add_game(child)
                    try:
                        for nested in sorted(child.iterdir(), key=lambda p: p.name.lower()):
                            if not nested.is_dir() or nested.name.lower() in ignore_dirs:
                                continue
                            add_game(nested, f"{child.name} / {nested.name}")
                    except Exception:
                        pass
                elif child.is_file() and child.suffix.lower() == ".py":
                    key = str(child.resolve()).lower()
                    if key not in seen_entries:
                        seen_entries.add(key)
                        games.append({
                            "name": child.stem,
                            "folder": child.parent,
                            "entry": child,
                            "screenshot": None,
                            "modified": self._mtime(child),
                            "path": self._safe_rel_path(child),
                        })
        except Exception:
            CRASH_REPORTER.write_exception("Prototype game discovery failed", *sys.exc_info())

        games.sort(key=lambda item: str(item.get("name", "")).lower())
        return games

    def _make_game_thumb(self, parent: tk.Misc, screenshot: Path | None, name: str, width: int = 148, height: int = 92):
        if screenshot is not None and Image is not None and ImageTk is not None:
            try:
                img = Image.open(screenshot).convert("RGBA")
                img.thumbnail((width, height), Image.Resampling.LANCZOS)
                back = Image.new("RGBA", (width, height), (2, 5, 6, 255))
                x = (width - img.width) // 2
                y = (height - img.height) // 2
                back.alpha_composite(img, (x, y))
                photo = ImageTk.PhotoImage(back)
                self.game_card_photos.append(photo)
                label = Label(parent, image=photo, bg="#020506", bd=0, highlightthickness=1, highlightbackground="#30464a")
                return label
            except Exception:
                pass

        canvas = Canvas(parent, width=width, height=height, bg="#020506", bd=0, highlightthickness=1, highlightbackground="#30464a")
        try:
            canvas.create_rectangle(0, 0, width, height, fill="#030708", outline="")
            canvas.create_oval(width // 2 - 34, height // 2 - 34, width // 2 + 34, height // 2 + 34, outline="#173a40", width=2)
            canvas.create_oval(width // 2 - 12, height // 2 - 12, width // 2 + 12, height // 2 + 12, fill="#efff3f", outline="")
            initials = "".join(part[:1] for part in str(name).replace("-", " ").split()[:2]).upper() or "GX"
            canvas.create_text(width // 2, height // 2, text=initials, fill="#020506", font=("Consolas", 16, "bold"))
            canvas.create_text(width // 2, height - 12, text="NO PREVIEW", fill="#6d8388", font=("Consolas", 8, "bold"))
        except Exception:
            pass
        return canvas

    def _build_prototype_game_panel(self, body: Frame) -> None:
        for child in list(body.winfo_children()):
            try:
                child.destroy()
            except Exception:
                pass
        self.tree = None
        self.preview = None
        self.game_card_photos = []
        self.prototype_games = self._discover_prototype_games()
        self.selected_game_record = None

        # The shared content shell gives row 0 weight for generic pages.
        # Prototype Lab needs the controls/list to start near the top and use
        # the available space below, so reset row weights explicitly.
        for row in range(6):
            try:
                body.grid_rowconfigure(row, weight=0)
            except Exception:
                pass
        body.grid_rowconfigure(2, weight=1)
        body.grid_columnconfigure(0, weight=1)

        toolbar = Frame(body, bg=self.THEME["panel"])
        toolbar.grid(row=0, column=0, sticky="ew", padx=18, pady=(8, 6))
        for col in range(4):
            toolbar.grid_columnconfigure(col, weight=1)
        self._small_action(toolbar, "RUN SELECTED", self._run_selected_game_card, 0, 0, accent=True)
        self._small_action(toolbar, "OPEN FOLDER", self._open_selected_game_folder, 0, 1)
        self._small_action(toolbar, "REFRESH", lambda: self._build_prototype_game_panel(body), 0, 2)
        self._small_action(toolbar, "INSTALL REQUIREMENTS", self._install_requirements, 0, 3)

        summary = Frame(body, bg="#070c0e", highlightthickness=1, highlightbackground="#203236")
        summary.grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 8))
        summary.grid_columnconfigure(0, weight=1)
        Label(
            summary,
            text=f"{len(self.prototype_games)} playable prototype(s) found",
            bg="#070c0e",
            fg=self.THEME["accent"],
            font=("Consolas", 12, "bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=12, pady=(8, 0))
        Label(
            summary,
            text="Mousewheel scrolls the list. Double-click a card to launch, or single-click a NO PREVIEW icon to launch directly.",
            bg="#070c0e",
            fg=self.THEME["muted"],
            font=("Segoe UI", 10),
            anchor="w",
            wraplength=max(560, self._content_width - 90),
        ).grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 8))

        canvas_host = Frame(body, bg="#020405", highlightthickness=1, highlightbackground="#223438")
        canvas_host.grid(row=2, column=0, sticky="nsew", padx=18, pady=(0, 18))
        canvas_host.grid_rowconfigure(0, weight=1)
        canvas_host.grid_columnconfigure(0, weight=1)

        canvas = Canvas(canvas_host, bg="#020405", bd=0, highlightthickness=0)
        self.prototype_games_canvas = canvas
        yscroll = ttk.Scrollbar(canvas_host, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=yscroll.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")

        inner = Frame(canvas, bg="#020405")
        window_id = canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.grid_columnconfigure(0, weight=1)

        def _sync_scroll(_event=None):
            try:
                canvas.configure(scrollregion=canvas.bbox("all"))
                canvas.itemconfigure(window_id, width=max(1, canvas.winfo_width()))
            except Exception:
                pass

        inner.bind("<Configure>", _sync_scroll, add="+")
        canvas.bind("<Configure>", _sync_scroll, add="+")
        self._prototype_bind_mousewheel(canvas)
        self._prototype_bind_mousewheel(inner)

        if not self.prototype_games:
            Label(
                inner,
                text="No playable prototype folders were found.",
                bg="#020405",
                fg=self.THEME["muted"],
                font=("Segoe UI", 13),
            ).grid(row=0, column=0, sticky="ew", padx=24, pady=24)
            return

        for idx, game in enumerate(self.prototype_games):
            self._create_game_card(inner, game, idx)

        self._select_game_card(self.prototype_games[0], None)

    def _prototype_bind_mousewheel(self, widget) -> None:
        canvas = getattr(self, "prototype_games_canvas", None)
        if canvas is None:
            return

        def _wheel(event):
            try:
                delta = int(getattr(event, "delta", 0) or 0)
                if delta:
                    amount = -1 if delta > 0 else 1
                    canvas.yview_scroll(amount * 3, "units")
                elif getattr(event, "num", None) == 4:
                    canvas.yview_scroll(-3, "units")
                elif getattr(event, "num", None) == 5:
                    canvas.yview_scroll(3, "units")
                return "break"
            except Exception:
                return None

        try:
            widget.bind("<MouseWheel>", _wheel, add="+")
            widget.bind("<Button-4>", _wheel, add="+")
            widget.bind("<Button-5>", _wheel, add="+")
        except Exception:
            pass
        try:
            for child in widget.winfo_children():
                self._prototype_bind_mousewheel(child)
        except Exception:
            pass

    def _create_game_card(self, parent: tk.Misc, game: dict, row: int) -> None:
        card = Frame(parent, bg="#071013", highlightthickness=1, highlightbackground="#26383c", bd=0)
        card.grid(row=row, column=0, sticky="ew", padx=12, pady=(12, 0))
        card.grid_columnconfigure(1, weight=1)

        thumb = self._make_game_thumb(card, game.get("screenshot"), str(game.get("name", "")))
        thumb.grid(row=0, column=0, rowspan=3, sticky="nw", padx=12, pady=12)

        title = Label(
            card,
            text=str(game.get("name", "Prototype")).upper(),
            bg="#071013",
            fg=self.THEME["text"],
            font=("Consolas", 16, "bold"),
            anchor="w",
        )
        title.grid(row=0, column=1, sticky="ew", padx=(4, 12), pady=(12, 0))

        detail = f"{self._safe_rel_path(Path(game.get('entry')))}"
        Label(
            card,
            text=detail,
            bg="#071013",
            fg=self.THEME["muted"],
            font=("Segoe UI", 9),
            anchor="w",
        ).grid(row=1, column=1, sticky="ew", padx=(4, 12), pady=(2, 0))

        meta_text = f"Modified {game.get('modified') or 'unknown'}"
        if game.get("screenshot"):
            meta_text += "  •  preview image found"
        else:
            meta_text += "  •  no preview image"
        Label(
            card,
            text=meta_text,
            bg="#071013",
            fg="#789096",
            font=("Segoe UI", 9),
            anchor="w",
        ).grid(row=2, column=1, sticky="ew", padx=(4, 12), pady=(2, 12))

        actions = Frame(card, bg="#071013")
        actions.grid(row=0, column=2, rowspan=3, sticky="e", padx=12, pady=12)
        self._small_action(actions, "RUN", lambda g=game: self._launch_game_record(g), 0, 0, accent=True)
        self._small_action(actions, "FOLDER", lambda g=game: self._open_game_folder(g), 1, 0)

        for widget in (card, title):
            try:
                widget.bind("<Button-1>", lambda _event, g=game, c=card: self._select_game_card(g, c), add="+")
                widget.bind("<Double-1>", lambda _event, g=game: self._launch_game_record(g), add="+")
            except Exception:
                pass

        try:
            if game.get("screenshot"):
                thumb.bind("<Button-1>", lambda _event, g=game, c=card: self._select_game_card(g, c), add="+")
                thumb.bind("<Double-1>", lambda _event, g=game: self._launch_game_record(g), add="+")
            else:
                thumb.bind("<Button-1>", lambda _event, g=game: (self._launch_game_record(g), "break")[-1])
        except Exception:
            pass

        self._prototype_bind_mousewheel(card)
        game["_card"] = card

    def _select_game_card(self, game: dict, card: tk.Misc | None) -> None:
        self.selected_game_record = game
        try:
            self.selected_path = Path(game.get("folder"))
        except Exception:
            self.selected_path = None
        for item in getattr(self, "prototype_games", []):
            c = item.get("_card")
            if c is None:
                continue
            try:
                c.configure(highlightbackground="#26383c")
            except Exception:
                pass
        target_card = card or game.get("_card")
        if target_card is not None:
            try:
                target_card.configure(highlightbackground=self.THEME["accent"])
            except Exception:
                pass
        self.status_var.set(f"Selected {game.get('name', 'prototype')}.")

    def _launch_game_record(self, game: dict) -> None:
        try:
            entry = Path(game.get("entry"))
            app_name = str(game.get("name") or entry.stem)
            self.launcher.launch_python_entry(entry, app_name, panel_key=f"prototype_lab_{self.launcher._panel_key_for_minigame(app_name)}")
            self.status_var.set(f"Launched {app_name}.")
        except Exception:
            CRASH_REPORTER.write_exception("Prototype card launch failed", *sys.exc_info())
            try:
                messagebox.showerror("Launch failed", f"Could not launch prototype.\nCrash report saved to:\n{CRASH_REPORTER.latest_app}")
            except Exception:
                pass

    def _run_selected_game_card(self) -> None:
        if self.selected_game_record:
            self._launch_game_record(self.selected_game_record)
            return
        self.status_var.set("Select a prototype card first.")

    def _open_game_folder(self, game: dict) -> None:
        try:
            folder = Path(game.get("folder"))
            self.launcher.open_path_in_explorer(folder)
            self.status_var.set(f"Opened folder: {folder.name}")
        except Exception:
            CRASH_REPORTER.write_exception("Prototype card open folder failed", *sys.exc_info())

    def _open_selected_game_folder(self) -> None:
        if self.selected_game_record:
            self._open_game_folder(self.selected_game_record)
            return
        self.status_var.set("Select a prototype card first.")

    def _install_requirements(self) -> None:
        req = APP_BASE_DIR / "requirements.txt"
        bat = APP_BASE_DIR / "install_requirements.bat"
        try:
            if os.name == "nt" and bat.exists():
                subprocess.Popen(["cmd", "/c", "start", "Install Requirements", str(bat)], cwd=str(APP_BASE_DIR))
                self.status_var.set("Install requirements started.")
                return
            if req.exists():
                subprocess.Popen([sys.executable, "-m", "pip", "install", "-r", str(req)], cwd=str(APP_BASE_DIR))
                self.status_var.set("pip install requirements started.")
                return
            self.status_var.set("No requirements.txt or install_requirements.bat found.")
            try:
                messagebox.showinfo("Install requirements", "No requirements.txt or install_requirements.bat was found in the app folder.")
            except Exception:
                pass
        except Exception:
            CRASH_REPORTER.write_exception("Install requirements failed", *sys.exc_info())
            try:
                messagebox.showerror("Install requirements", f"Could not start requirements installer.\nCrash report saved to:\n{CRASH_REPORTER.latest_app}")
            except Exception:
                pass

    def _switch_prototype_to_file_browser(self, body: Frame) -> None:
        for child in list(body.winfo_children()):
            try:
                child.destroy()
            except Exception:
                pass
        root_path = APP_BASE_DIR / "data" / "Prototype Lab"
        self._build_browser(body, root_path, include_mxos_button=False)
        self.set_path(root_path, push=True)

    def open_mxos_panel(self) -> None:
        self.active_panel = "mxos"
        body = self._show_content_shell("MXOS", "Minimal virtual operating system for prototypes and tools.")
        self._build_mxos_embedded_panel(body)
        self.status_var.set("MXOS embedded panel opened.")

    def _discover_mxos_items(self) -> list[dict]:
        items: list[dict] = [
            {"name": "HoloVerse", "type": "System", "description": "Launch the HoloVerse game.", "command": self.open_holoverse, "folder": HOLOVERSE_DIR, "accent": "#efff3f"},
            {"name": "Prototype Lab", "type": "System", "description": "Open the prototype game cards.", "command": self.open_prototype_panel, "folder": APP_BASE_DIR / "data" / "Prototype Lab", "accent": "#21d8e8"},
            {"name": "MatrixCore", "type": "Reader", "description": "Open the MatrixCore chapter reader.", "command": self.open_matrixcore_panel, "folder": self._matrixcore_database_dir(), "accent": "#ff4a4a"},
            {"name": "Install Requirements", "type": "Tool", "description": "Run the project requirements installer.", "command": self._install_requirements, "folder": APP_BASE_DIR, "accent": "#ff9d57"},
        ]
        try:
            for game in self._discover_prototype_games():
                items.append({
                    "name": str(game.get("name") or "Prototype"),
                    "type": "Prototype",
                    "description": self._safe_rel_path(Path(game.get("entry"))),
                    "command": lambda g=game: self._launch_game_record(g),
                    "folder": Path(game.get("folder")),
                    "screenshot": game.get("screenshot"),
                    "accent": "#21d8e8",
                })
        except Exception:
            CRASH_REPORTER.write_exception("MXOS item discovery failed", *sys.exc_info())
        return items

    def _build_mxos_embedded_panel(self, body: Frame) -> None:
        for child in list(body.winfo_children()):
            try:
                child.destroy()
            except Exception:
                pass
        self.tree = None
        self.preview = None
        self.game_card_photos = []
        self.mxos_items = self._discover_mxos_items()
        self.mxos_selected_item = self.mxos_items[0] if self.mxos_items else None
        self.mxos_tiles: list[tk.Misc] = []

        for row in range(6):
            try:
                body.grid_rowconfigure(row, weight=0)
            except Exception:
                pass
        body.grid_rowconfigure(1, weight=1)
        body.grid_columnconfigure(0, weight=1)

        top = Frame(body, bg="#05090b", highlightthickness=1, highlightbackground="#203236")
        top.grid(row=0, column=0, sticky="ew", padx=18, pady=(12, 8))
        for col in range(4):
            top.grid_columnconfigure(col, weight=1)
        self._small_action(top, "RUN SELECTED", self._run_mxos_selected, 0, 0, accent=True)
        self._small_action(top, "OPEN FOLDER", self._open_mxos_selected_folder, 0, 1)
        self._small_action(top, "REFRESH", lambda: self._build_mxos_embedded_panel(body), 0, 2)
        self._small_action(top, "FOCUS", self.focus_desktop, 0, 3)

        desktop_wrap = Frame(body, bg="#020405", highlightthickness=1, highlightbackground="#223438")
        desktop_wrap.grid(row=1, column=0, sticky="nsew", padx=18, pady=(0, 8))
        desktop_wrap.grid_rowconfigure(0, weight=1)
        desktop_wrap.grid_columnconfigure(0, weight=1)

        canvas = Canvas(desktop_wrap, bg="#020405", bd=0, highlightthickness=0)
        scroll = ttk.Scrollbar(desktop_wrap, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        inner = Frame(canvas, bg="#020405")
        window_id = canvas.create_window((0, 0), window=inner, anchor="nw")
        self.mxos_canvas = canvas
        self.mxos_inner = inner

        def _sync(_event=None):
            try:
                canvas.configure(scrollregion=canvas.bbox("all"))
                canvas.itemconfigure(window_id, width=max(600, int(canvas.winfo_width() or 600)))
            except Exception:
                pass
        inner.bind("<Configure>", _sync, add="+")
        canvas.bind("<Configure>", _sync, add="+")

        columns = 4
        try:
            usable_w = max(680, int(self._content_width or canvas.winfo_width() or 900))
            columns = max(3, min(6, usable_w // 260))
        except Exception:
            columns = 4
        for col in range(columns):
            inner.grid_columnconfigure(col, weight=1, uniform="mxos_icons")

        header = Frame(inner, bg="#020405")
        header.grid(row=0, column=0, columnspan=columns, sticky="ew", padx=16, pady=(16, 8))
        header.grid_columnconfigure(0, weight=1)
        Label(header, text="MXOS DESKTOP", bg="#020405", fg=self.THEME["accent"], font=("Consolas", 18, "bold"), anchor="w").grid(row=0, column=0, sticky="ew")
        Label(header, text="Clean embedded workspace. Select an icon, double-click to launch, or use Run Selected.", bg="#020405", fg=self.THEME["muted"], font=("Segoe UI", 10), anchor="w").grid(row=1, column=0, sticky="ew", pady=(3, 0))

        start_row = 1
        for idx, item in enumerate(self.mxos_items):
            row = start_row + idx // columns
            col = idx % columns
            tile = self._create_mxos_tile(inner, item)
            tile.grid(row=row, column=col, sticky="nsew", padx=12, pady=12)
        if self.mxos_items:
            self._select_mxos_item(self.mxos_items[0], self.mxos_tiles[0] if self.mxos_tiles else None)

        bottom = Frame(body, bg="#05090b", highlightthickness=1, highlightbackground="#203236")
        bottom.grid(row=2, column=0, sticky="ew", padx=18, pady=(0, 12))
        bottom.grid_columnconfigure(0, weight=1)
        self.mxos_status_var = StringVar(value=f"{len(self.mxos_items)} MXOS item(s) ready.")
        Label(bottom, textvariable=self.mxos_status_var, bg="#05090b", fg=self.THEME["muted"], font=("Segoe UI", 10), anchor="w").grid(row=0, column=0, sticky="ew", padx=12, pady=10)
        Button(bottom, text="CLOSE MXOS", command=self.close_panel, bg="#300709", fg="#ffffff", activebackground="#5a1015", activeforeground="#ffffff", relief="flat", bd=0, padx=16, pady=8, font=("Consolas", 10, "bold"), cursor="hand2").grid(row=0, column=1, sticky="e", padx=12, pady=8)

        self._mxos_bind_mousewheel(canvas)
        self._mxos_bind_mousewheel(inner)
        try:
            canvas.after(50, _sync)
        except Exception:
            pass

    def _create_mxos_tile(self, parent: tk.Misc, item: dict) -> Frame:
        accent = str(item.get("accent") or self.THEME["cyan"])
        tile = Frame(parent, bg="#071013", highlightthickness=2, highlightbackground="#203236", bd=0)
        tile.grid_columnconfigure(0, weight=1)
        icon_host = Frame(tile, bg="#071013")
        icon_host.grid(row=0, column=0, sticky="ew", padx=14, pady=(14, 8))
        icon_host.grid_columnconfigure(0, weight=1)
        screenshot = item.get("screenshot")
        if screenshot:
            thumb = self._make_game_thumb(icon_host, Path(screenshot), str(item.get("name", "MXOS")), width=174, height=104)
            thumb.grid(row=0, column=0)
        else:
            thumb = Canvas(icon_host, width=174, height=104, bg="#020506", bd=0, highlightthickness=1, highlightbackground="#30464a")
            thumb.grid(row=0, column=0)
            try:
                thumb.create_rectangle(0, 0, 174, 104, fill="#020506", outline="")
                thumb.create_oval(42, 16, 132, 96, outline="#14363c", width=3)
                thumb.create_oval(68, 32, 106, 70, fill=accent, outline="")
                initials = "".join(part[:1] for part in str(item.get("name", "MX")).replace("-", " ").split()[:2]).upper() or "MX"
                thumb.create_text(87, 51, text=initials, fill="#020506", font=("Consolas", 18, "bold"))
                thumb.create_text(87, 92, text=str(item.get("type", "APP")).upper(), fill="#789096", font=("Consolas", 8, "bold"))
            except Exception:
                pass
        Label(tile, text=str(item.get("name", "MXOS")).upper(), bg="#071013", fg=self.THEME["text"], font=("Consolas", 13, "bold"), anchor="center", wraplength=210, justify="center").grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 3))
        Label(tile, text=str(item.get("type", "App")), bg="#071013", fg=accent, font=("Consolas", 9, "bold"), anchor="center").grid(row=2, column=0, sticky="ew", padx=10)
        Label(tile, text=str(item.get("description", "")), bg="#071013", fg=self.THEME["muted"], font=("Segoe UI", 8), anchor="n", justify="center", wraplength=220).grid(row=3, column=0, sticky="ew", padx=12, pady=(4, 14))
        self.mxos_tiles.append(tile)

        def _select(_event=None, it=item, t=tile):
            self._select_mxos_item(it, t)
            return "break"
        def _launch(_event=None, it=item, t=tile):
            self._select_mxos_item(it, t)
            self._run_mxos_item(it)
            return "break"
        for widget in (tile, icon_host, thumb):
            try:
                widget.bind("<Button-1>", _select, add="+")
                widget.bind("<Double-1>", _launch, add="+")
            except Exception:
                pass
        self._mxos_bind_mousewheel(tile)
        return tile

    def _select_mxos_item(self, item: dict, tile: tk.Misc | None = None) -> None:
        self.mxos_selected_item = item
        for existing in getattr(self, "mxos_tiles", []):
            try:
                existing.configure(highlightbackground="#203236")
            except Exception:
                pass
        if tile is not None:
            try:
                tile.configure(highlightbackground=str(item.get("accent") or self.THEME["accent"]))
            except Exception:
                pass
        text = f"Selected {item.get('name', 'MXOS item')}"
        if hasattr(self, "mxos_status_var"):
            try:
                self.mxos_status_var.set(text)
            except Exception:
                pass
        self.status_var.set(text)

    def _run_mxos_item(self, item: dict | None = None) -> None:
        item = item or getattr(self, "mxos_selected_item", None)
        if not item:
            self.status_var.set("Select an MXOS icon first.")
            return
        command = item.get("command")
        if callable(command):
            try:
                command()
            except Exception:
                CRASH_REPORTER.write_exception("MXOS item launch failed", *sys.exc_info())
                try:
                    messagebox.showerror("MXOS", f"Could not launch {item.get('name', 'item')}.")
                except Exception:
                    pass
        else:
            self.status_var.set("This MXOS item has no launcher attached.")

    def _run_mxos_selected(self) -> None:
        self._run_mxos_item(getattr(self, "mxos_selected_item", None))

    def _open_mxos_selected_folder(self) -> None:
        item = getattr(self, "mxos_selected_item", None)
        folder = item.get("folder") if isinstance(item, dict) else None
        if not folder:
            self.status_var.set("Selected MXOS item has no folder.")
            return
        try:
            self.launcher.open_path_in_explorer(Path(folder))
            self.status_var.set(f"Opened folder for {item.get('name', 'MXOS item')}.")
        except Exception:
            CRASH_REPORTER.write_exception("MXOS open folder failed", *sys.exc_info())

    def _mxos_bind_mousewheel(self, widget) -> None:
        canvas = getattr(self, "mxos_canvas", None)
        if canvas is None:
            return
        def _wheel(event):
            try:
                delta = int(getattr(event, "delta", 0) or 0)
                if delta:
                    canvas.yview_scroll((-1 if delta > 0 else 1) * 3, "units")
                elif getattr(event, "num", None) == 4:
                    canvas.yview_scroll(-3, "units")
                elif getattr(event, "num", None) == 5:
                    canvas.yview_scroll(3, "units")
                return "break"
            except Exception:
                return None
        try:
            widget.bind("<MouseWheel>", _wheel, add="+")
            widget.bind("<Button-4>", _wheel, add="+")
            widget.bind("<Button-5>", _wheel, add="+")
        except Exception:
            pass
        try:
            for child in widget.winfo_children():
                self._mxos_bind_mousewheel(child)
        except Exception:
            pass

    def open_matrixcore_panel(self) -> None:
        self.active_panel = "matrixcore"
        body = self._show_content_shell("MatrixCore", "Dark lore/database reader. Generation, salvage, and ChatSpace remain isolated out.")
        self._build_matrixcore_reader(body)
        self.status_var.set("MatrixCore reader opened.")

    def _matrixcore_database_dir(self) -> Path:
        candidates = [
            APP_BASE_DIR / "data" / "database" / "MatrixCore",
            RESOURCE_BASE_DIR / "data" / "database" / "MatrixCore",
            APP_BASE_DIR / "data" / "MatrixCore",
            RESOURCE_BASE_DIR / "data" / "MatrixCore",
        ]
        for candidate in candidates:
            try:
                if candidate.exists() and candidate.is_dir():
                    return candidate
            except Exception:
                continue
        return candidates[0]

    def _discover_matrixcore_texts(self) -> list[Path]:
        root = self._matrixcore_database_dir()
        files: list[Path] = []
        try:
            for candidate in root.iterdir():
                if candidate.is_file() and candidate.suffix.lower() in {".txt", ".md"}:
                    files.append(candidate)
        except Exception:
            return []
        files.sort(key=lambda p: p.name.lower())
        return files

    def _matrixcore_chapter_label(self, path: Path) -> str:
        name = path.stem.replace("_", " ").replace("-", " ").strip()
        name = re.sub(r"^([0-9]{1,3})\s+", r"\1. ", name)
        return name or path.name


    def _matrixcore_mousewheel(self, widget, target=None, *, units: int = 3) -> None:
        """Bind Windows/macOS/Linux wheel events to a scrollable MatrixCore widget."""
        scroll_target = target or widget

        def _wheel(event):
            try:
                delta = int(getattr(event, "delta", 0) or 0)
                if delta:
                    amount = -1 if delta > 0 else 1
                    scroll_target.yview_scroll(amount * max(1, int(units)), "units")
                elif getattr(event, "num", None) == 4:
                    scroll_target.yview_scroll(-max(1, int(units)), "units")
                elif getattr(event, "num", None) == 5:
                    scroll_target.yview_scroll(max(1, int(units)), "units")
                return "break"
            except Exception:
                return None

        for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            try:
                widget.bind(sequence, _wheel, add="+")
            except Exception:
                pass

    def _matrixcore_button(self, parent: tk.Misc, text: str, command, *, accent: bool = False, danger: bool = False, small: bool = False):
        bg = "#11191d"
        fg = "#f2f2f2"
        active_bg = "#1b2d32"
        edge = "#26383c"
        if accent:
            bg = "#172a2f"
            fg = self.THEME["cyan"]
            active_bg = "#1f3b42"
            edge = "#21d8e8"
        if danger:
            bg = "#26080a"
            fg = "#ffdddd"
            active_bg = "#4a1518"
            edge = "#7a2026"
        return Button(
            parent,
            text=text,
            command=command,
            bg=bg,
            fg=fg,
            activebackground=active_bg,
            activeforeground="#ffffff",
            relief="flat",
            bd=0,
            highlightthickness=1,
            highlightbackground=edge,
            highlightcolor=self.THEME["cyan"],
            padx=12 if small else 16,
            pady=8 if small else 12,
            font=("Consolas", 10 if small else 12, "bold"),
            cursor="hand2",
        )

    def _matrixcore_apply_reader_scale(self) -> None:
        scale = float(getattr(self, "matrixcore_reader_scale", 1.0) or 1.0)
        scale = max(0.85, min(1.45, scale))
        self.matrixcore_reader_scale = scale
        try:
            if getattr(self, "matrixcore_scale_var", None) is not None:
                self.matrixcore_scale_var.set(f"TEXT {int(scale * 100)}%")
        except Exception:
            pass
        text = getattr(self, "matrixcore_text", None)
        if text is not None:
            base_body = max(11, int(round(12 * scale)))
            base_title = max(18, int(round(23 * scale)))
            base_heading = max(14, int(round(16 * scale)))
            base_sub = max(12, int(round(13 * scale)))
            try:
                text.configure(font=("Segoe UI", base_body), padx=max(18, int(26 * scale)), pady=max(16, int(24 * scale)))
                text.tag_configure("title", foreground="#ffdddd", font=("Consolas", base_title, "bold"), spacing1=6, spacing3=max(12, int(18 * scale)))
                text.tag_configure("heading", foreground="#ff4a4a", font=("Consolas", base_heading, "bold"), spacing1=max(10, int(16 * scale)), spacing3=max(7, int(10 * scale)))
                text.tag_configure("subheading", foreground=self.THEME["cyan"], font=("Consolas", base_sub, "bold"), spacing1=max(8, int(12 * scale)), spacing3=max(6, int(8 * scale)))
                text.tag_configure("body", foreground="#eeeeee", font=("Segoe UI", base_body), spacing3=max(6, int(8 * scale)))
                text.tag_configure("muted", foreground="#91a6ad", font=("Segoe UI", max(9, int(round(10 * scale))), "italic"), spacing3=max(8, int(10 * scale)))
                text.tag_configure("rule", foreground="#ff4a4a", font=("Consolas", max(9, int(round(10 * scale))), "bold"), spacing1=max(8, int(10 * scale)), spacing3=max(8, int(10 * scale)))
            except Exception:
                pass
        for btn in list(getattr(self, "matrixcore_chapter_buttons", [])):
            try:
                btn.configure(font=("Consolas", max(10, int(round(11 * scale))), "bold"), pady=max(7, int(round(9 * scale))))
            except Exception:
                pass
        try:
            if getattr(self, "matrixcore_chapters_canvas", None) is not None:
                self.matrixcore_chapters_canvas.configure(scrollregion=self.matrixcore_chapters_canvas.bbox("all"))
        except Exception:
            pass

    def _matrixcore_adjust_reader_scale(self, delta: float) -> None:
        self.matrixcore_reader_scale = max(0.85, min(1.45, float(getattr(self, "matrixcore_reader_scale", 1.0) or 1.0) + float(delta)))
        self._matrixcore_apply_reader_scale()

    def _matrixcore_wrap_label(self, text: str, max_chars: int = 34) -> str:
        words = str(text or "").split()
        if not words:
            return "Untitled"
        lines: list[str] = []
        line = ""
        for word in words:
            trial = word if not line else f"{line} {word}"
            if len(trial) > max_chars and line:
                lines.append(line)
                line = word
            else:
                line = trial
        if line:
            lines.append(line)
        return "\n".join(lines[:3])

    def _select_matrixcore_chapter_index(self, index: int) -> None:
        files = list(getattr(self, "matrixcore_reader_files", []))
        if not (0 <= int(index) < len(files)):
            return
        self.matrixcore_selected_index = int(index)
        for idx, btn in enumerate(list(getattr(self, "matrixcore_chapter_buttons", []))):
            try:
                if idx == int(index):
                    btn.configure(bg="#6b1419", fg="#ffffff", highlightbackground="#ff4a4a")
                else:
                    btn.configure(bg="#071013", fg="#f4f4f4", highlightbackground="#26383c")
            except Exception:
                pass
        self._load_matrixcore_text(files[int(index)])

    def _render_matrixcore_chapter_buttons(self) -> None:
        host = getattr(self, "matrixcore_chapter_inner", None)
        if host is None:
            return
        for child in list(host.winfo_children()):
            try:
                child.destroy()
            except Exception:
                pass
        self.matrixcore_chapter_buttons = []
        host.grid_columnconfigure(0, weight=1)
        for idx, path in enumerate(list(getattr(self, "matrixcore_reader_files", []))):
            label = self._matrixcore_chapter_label(path)
            short = self._matrixcore_wrap_label(label, max_chars=36)
            btn = Button(
                host,
                text=short,
                command=lambda i=idx: self._select_matrixcore_chapter_index(i),
                bg="#071013",
                fg="#f4f4f4",
                activebackground="#6b1419",
                activeforeground="#ffffff",
                relief="flat",
                bd=0,
                highlightthickness=1,
                highlightbackground="#26383c",
                justify="left",
                anchor="w",
                wraplength=330,
                padx=12,
                pady=9,
                font=("Consolas", 11, "bold"),
                cursor="hand2",
            )
            btn.grid(row=idx, column=0, sticky="ew", padx=8, pady=(0, 7))
            try:
                self._matrixcore_mousewheel(btn, getattr(self, "matrixcore_chapters_canvas", None), units=4)
            except Exception:
                pass
            self.matrixcore_chapter_buttons.append(btn)
        self._matrixcore_apply_reader_scale()
        try:
            canvas = getattr(self, "matrixcore_chapters_canvas", None)
            if canvas is not None:
                canvas.update_idletasks()
                canvas.configure(scrollregion=canvas.bbox("all"))
        except Exception:
            pass

    def _build_matrixcore_reader(self, body: Frame) -> None:
        for child in list(body.winfo_children()):
            try:
                child.destroy()
            except Exception:
                pass
        self.tree = None
        self.preview = None
        self.matrixcore_reader_files = self._discover_matrixcore_texts()
        self.matrixcore_selected_file: Path | None = None
        self.matrixcore_selected_index = 0
        self.matrixcore_reader_scale = float(getattr(self, "matrixcore_reader_scale", 1.0) or 1.0)

        body.configure(bg="#010203")
        body.grid_rowconfigure(0, weight=1)
        body.grid_columnconfigure(0, weight=0)
        body.grid_columnconfigure(1, weight=1)

        side = Frame(body, bg="#040607", width=430, highlightthickness=1, highlightbackground="#4d1015")
        side.grid(row=0, column=0, sticky="nsw", padx=(14, 8), pady=14)
        side.grid_propagate(False)
        side.grid_rowconfigure(2, weight=1)
        side.grid_columnconfigure(0, weight=1)

        Label(side, text="CHAPTERS", bg="#040607", fg="#ff4a4a", font=("Consolas", 20, "bold"), anchor="center").grid(row=0, column=0, sticky="ew", padx=14, pady=(16, 4))
        Label(side, text=f"{len(self.matrixcore_reader_files)} files  •  mousewheel scroll", bg="#040607", fg=self.THEME["muted"], font=("Segoe UI", 10), anchor="center").grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 12))

        list_host = Frame(side, bg="#020303", highlightthickness=1, highlightbackground="#26383c")
        list_host.grid(row=2, column=0, sticky="nsew", padx=12, pady=(0, 12))
        list_host.grid_rowconfigure(0, weight=1)
        list_host.grid_columnconfigure(0, weight=1)

        self.matrixcore_chapters_canvas = Canvas(list_host, bg="#020303", bd=0, highlightthickness=0)
        chapter_scroll = ttk.Scrollbar(list_host, orient="vertical", command=self.matrixcore_chapters_canvas.yview)
        self.matrixcore_chapters_canvas.configure(yscrollcommand=chapter_scroll.set)
        self.matrixcore_chapters_canvas.grid(row=0, column=0, sticky="nsew")
        chapter_scroll.grid(row=0, column=1, sticky="ns")
        self.matrixcore_chapter_inner = Frame(self.matrixcore_chapters_canvas, bg="#020303")
        chapter_window_id = self.matrixcore_chapters_canvas.create_window((0, 0), window=self.matrixcore_chapter_inner, anchor="nw")

        def _sync_chapters(_event=None):
            try:
                canvas = self.matrixcore_chapters_canvas
                canvas.itemconfigure(chapter_window_id, width=max(1, canvas.winfo_width()))
                canvas.configure(scrollregion=canvas.bbox("all"))
            except Exception:
                pass

        self.matrixcore_chapter_inner.bind("<Configure>", _sync_chapters, add="+")
        self.matrixcore_chapters_canvas.bind("<Configure>", _sync_chapters, add="+")
        self._matrixcore_mousewheel(self.matrixcore_chapters_canvas, self.matrixcore_chapters_canvas, units=4)

        actions = Frame(side, bg="#040607")
        actions.grid(row=3, column=0, sticky="ew", padx=12, pady=(0, 12))
        actions.grid_columnconfigure(0, weight=1)
        actions.grid_columnconfigure(1, weight=1)
        self._matrixcore_button(actions, "MXOS", self.launch_matrix_core_workstation, accent=True, small=True).grid(row=0, column=0, sticky="ew", padx=(0, 6), pady=(0, 0))
        self._matrixcore_button(actions, "FOLDER", lambda: self.launcher.open_path_in_explorer(self._matrixcore_database_dir()), small=True).grid(row=0, column=1, sticky="ew", padx=(6, 0), pady=(0, 0))

        reader = Frame(body, bg="#020405", highlightthickness=1, highlightbackground="#26383c")
        reader.grid(row=0, column=1, sticky="nsew", padx=(8, 14), pady=14)
        reader.grid_rowconfigure(1, weight=1)
        reader.grid_columnconfigure(0, weight=1)

        self.matrixcore_title_var = StringVar(value="Glitched Matrix: The Utopia Project")
        self.matrixcore_path_var = StringVar(value="Select a MatrixCore chapter")
        self.matrixcore_scale_var = StringVar(value="TEXT 100%")
        title_bar = Frame(reader, bg="#07090a", height=92, highlightthickness=1, highlightbackground="#4d1015")
        title_bar.grid(row=0, column=0, sticky="ew")
        title_bar.grid_propagate(False)
        title_bar.grid_columnconfigure(0, weight=1)
        Label(title_bar, textvariable=self.matrixcore_title_var, bg="#07090a", fg="#ffdddd", font=("Consolas", 20, "bold"), anchor="w").grid(row=0, column=0, sticky="ew", padx=18, pady=(10, 0))
        Label(title_bar, textvariable=self.matrixcore_path_var, bg="#07090a", fg=self.THEME["cyan"], font=("Segoe UI", 9), anchor="w").grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 8))

        font_controls = Frame(title_bar, bg="#07090a")
        font_controls.grid(row=0, column=1, rowspan=2, sticky="e", padx=12, pady=12)
        Label(font_controls, textvariable=self.matrixcore_scale_var, bg="#07090a", fg=self.THEME["muted"], font=("Consolas", 9, "bold"), anchor="center").grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 4))
        self._matrixcore_button(font_controls, "A-", lambda: self._matrixcore_adjust_reader_scale(-0.08), small=True).grid(row=1, column=0, sticky="ew", padx=3)
        self._matrixcore_button(font_controls, "RESET", lambda: (setattr(self, "matrixcore_reader_scale", 1.0), self._matrixcore_apply_reader_scale()), accent=True, small=True).grid(row=1, column=1, sticky="ew", padx=3)
        self._matrixcore_button(font_controls, "A+", lambda: self._matrixcore_adjust_reader_scale(0.08), small=True).grid(row=1, column=2, sticky="ew", padx=3)

        text_host = Frame(reader, bg="#010203")
        text_host.grid(row=1, column=0, sticky="nsew")
        text_host.grid_rowconfigure(0, weight=1)
        text_host.grid_columnconfigure(0, weight=1)
        self.matrixcore_text = tk.Text(
            text_host,
            bg="#010203",
            fg="#f2f2f2",
            insertbackground="#ffffff",
            selectbackground="#611016",
            selectforeground="#ffffff",
            relief="flat",
            bd=0,
            highlightthickness=0,
            wrap="word",
            padx=26,
            pady=24,
            font=("Segoe UI", 12),
            spacing1=3,
            spacing2=3,
            spacing3=9,
        )
        text_scroll = ttk.Scrollbar(text_host, orient="vertical", command=self.matrixcore_text.yview)
        self.matrixcore_text.configure(yscrollcommand=text_scroll.set)
        self.matrixcore_text.grid(row=0, column=0, sticky="nsew")
        text_scroll.grid(row=0, column=1, sticky="ns")
        self._configure_matrixcore_reader_tags()
        self._matrixcore_mousewheel(self.matrixcore_text, self.matrixcore_text, units=3)
        try:
            self.matrixcore_text.bind("<Control-MouseWheel>", lambda event: (self._matrixcore_adjust_reader_scale(0.08 if event.delta > 0 else -0.08), "break")[-1], add="+")
        except Exception:
            pass

        self._render_matrixcore_chapter_buttons()

        if self.matrixcore_reader_files:
            self._select_matrixcore_chapter_index(0)
        else:
            self._show_matrixcore_empty_state()


    def _configure_matrixcore_reader_tags(self) -> None:
        text = getattr(self, "matrixcore_text", None)
        if text is None:
            return
        try:
            self._matrixcore_apply_reader_scale()
        except Exception:
            pass

    def _on_matrixcore_chapter_select(self, _event=None) -> None:
        lb = getattr(self, "matrixcore_chapter_list", None)
        if lb is None:
            return
        try:
            selection = lb.curselection()
            if not selection:
                return
            self._select_matrixcore_chapter_index(int(selection[0]))
        except Exception:
            CRASH_REPORTER.write_exception("MatrixCore chapter select failed", *sys.exc_info())

    def _show_matrixcore_empty_state(self) -> None:
        text = getattr(self, "matrixcore_text", None)
        if text is None:
            return
        try:
            text.configure(state="normal")
            text.delete("1.0", END)
            text.insert("1.0", "MatrixCore database not found.\n", "title")
            text.insert(END, "Expected text files inside data/database/MatrixCore.", "body")
            text.configure(state="disabled")
        except Exception:
            pass

    def _load_matrixcore_text(self, path: Path) -> None:
        path = Path(path)
        self.matrixcore_selected_file = path
        title = self._matrixcore_chapter_label(path)
        try:
            raw = path.read_text(encoding="utf-8", errors="ignore")
        except Exception as exc:
            raw = f"Could not read {path.name}: {exc}"
        try:
            self.matrixcore_title_var.set("Glitched Matrix: The Utopia Project")
            self.matrixcore_path_var.set(title)
        except Exception:
            pass
        text = getattr(self, "matrixcore_text", None)
        if text is None:
            return
        try:
            text.configure(state="normal")
            text.delete("1.0", END)
            text.insert(END, title + "\n", "title")
            text.insert(END, "─" * 72 + "\n\n", "rule")
            lines = raw.replace("\r\n", "\n").replace("\r", "\n").split("\n")
            first_content_seen = False
            for line in lines:
                stripped = line.strip()
                if not stripped:
                    text.insert(END, "\n", "body")
                    continue
                # Avoid duplicating a title if the file begins with the same chapter name.
                if not first_content_seen and stripped.lower() == title.lower():
                    first_content_seen = True
                    continue
                first_content_seen = True
                if stripped.startswith("#"):
                    heading_text = stripped.lstrip("#").strip()
                    tag = "heading" if line.startswith("#") and not line.startswith("###") else "subheading"
                    text.insert(END, heading_text + "\n", tag)
                elif len(stripped) <= 72 and (stripped.endswith(":") or stripped.isupper() or re.match(r"^(chapter|part|act|scene|section)\b", stripped, re.I)):
                    text.insert(END, stripped + "\n", "heading")
                elif re.match(r"^[0-9]{1,3}[\).:-]\s+", stripped):
                    text.insert(END, stripped + "\n", "subheading")
                else:
                    text.insert(END, line.rstrip() + "\n", "body")
            text.configure(state="disabled")
            self._matrixcore_apply_reader_scale()
            text.see("1.0")
            self.status_var.set(f"Reading {title}.")
        except Exception:
            CRASH_REPORTER.write_exception("MatrixCore reader load failed", *sys.exc_info())
            try:
                text.configure(state="disabled")
            except Exception:
                pass

    def _matrixcore_browse_gx(self, parent_body: Frame) -> None:
        for child in list(parent_body.winfo_children()):
            try:
                child.destroy()
            except Exception:
                pass
        self._build_browser(parent_body, APP_BASE_DIR / "data" / "GX-Machine", include_mxos_button=True)
        self.set_path(APP_BASE_DIR / "data" / "GX-Machine", push=True)

    def _small_action(self, parent: tk.Misc, text: str, command, row: int, column: int, *, accent: bool = False):
        btn = Button(
            parent,
            text=text,
            command=command,
            bg="#18251a" if accent else "#10191d",
            fg=self.THEME["accent"] if accent else self.THEME["text"],
            activebackground="#263a25" if accent else "#1b2d32",
            activeforeground="#ffffff",
            relief="flat",
            bd=0,
            padx=18,
            pady=12,
            font=("Consolas", 11, "bold"),
            cursor="hand2",
        )
        btn.grid(row=row, column=column, sticky="ew", padx=8, pady=8)
        return btn

    def _build_browser(self, body: Frame, start_path: Path, *, include_mxos_button: bool = False) -> None:
        body.grid_rowconfigure(2, weight=1)
        body.grid_columnconfigure(0, weight=1)

        nav = Frame(body, bg=self.THEME["panel"])
        nav.grid(row=0, column=0, sticky="ew", padx=14, pady=(14, 6))
        for col in range(8):
            nav.grid_columnconfigure(col, weight=1)
        self._small_action(nav, "BACK", self.go_back, 0, 0)
        self._small_action(nav, "FORWARD", self.go_forward, 0, 1)
        self._small_action(nav, "UP", self.go_up, 0, 2)
        self._small_action(nav, "HOME", self.go_home, 0, 3)
        self._small_action(nav, "REFRESH", self.refresh, 0, 4)
        self._small_action(nav, "RUN", self.run_selected, 0, 5, accent=True)
        self._small_action(nav, "OPEN FOLDER", self.open_folder, 0, 6)
        if include_mxos_button:
            self._small_action(nav, "LAUNCH MXOS", self.launch_matrix_core_workstation, 0, 7, accent=True)

        path_bar = Frame(body, bg="#070c0e", highlightthickness=1, highlightbackground="#203236")
        path_bar.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 8))
        path_bar.grid_columnconfigure(1, weight=1)
        Label(path_bar, text="PATH", bg="#070c0e", fg=self.THEME["accent"], font=("Consolas", 9, "bold")).grid(row=0, column=0, sticky="w", padx=10, pady=7)
        Label(path_bar, textvariable=self.path_var, bg="#070c0e", fg="#d8f8ff", font=("Segoe UI", 10), anchor="w").grid(row=0, column=1, sticky="ew", padx=6, pady=7)

        tree_host = Frame(body, bg="#020405", highlightthickness=1, highlightbackground="#223438")
        tree_host.grid(row=2, column=0, sticky="nsew", padx=14, pady=4)
        tree_host.grid_rowconfigure(0, weight=1)
        tree_host.grid_columnconfigure(0, weight=1)
        columns = ("type", "size", "modified")
        self.tree = ttk.Treeview(tree_host, columns=columns, show="tree headings", selectmode="browse")
        self.tree.heading("#0", text="Name")
        self.tree.heading("type", text="Type")
        self.tree.heading("size", text="Size")
        self.tree.heading("modified", text="Modified")
        self.tree.column("#0", width=440, anchor="w")
        self.tree.column("type", width=150, anchor="w")
        self.tree.column("size", width=100, anchor="e")
        self.tree.column("modified", width=155, anchor="w")
        yscroll = ttk.Scrollbar(tree_host, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=yscroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self.tree.bind("<Double-1>", self._on_tree_activate)
        self.tree.bind("<Return>", self._on_tree_activate)

        Label(body, text="Selection Preview", bg=self.THEME["panel"], fg=self.THEME["accent"], font=("Consolas", 10, "bold")).grid(row=3, column=0, sticky="w", padx=18, pady=(8, 0))
        self.preview = tk.Text(body, height=8, bg="#05090b", fg=self.THEME["text"], insertbackground="#ffffff", bd=0, highlightthickness=1, highlightbackground="#223438", font=("Consolas", 9), wrap="word")
        self.preview.grid(row=4, column=0, sticky="ew", padx=14, pady=(3, 14))
        self.preview.configure(state="disabled")

        self._apply_tree_style()
        self.current_path = Path(start_path)

    def _apply_tree_style(self) -> None:
        try:
            style = ttk.Style()
            style.configure("Treeview", background="#030708", fieldbackground="#030708", foreground="#e8f4f6", rowheight=28, borderwidth=0)
            style.map("Treeview", background=[("selected", "#17444c")], foreground=[("selected", "#ffffff")])
            style.configure("Treeview.Heading", background="#0b1012", foreground="#efff3f", font=("Consolas", 10, "bold"))
        except Exception:
            pass

    def _location_entries(self) -> list[tuple[str, Path]]:
        base = APP_BASE_DIR / "data" / "Prototype Lab"
        entries = [
            ("Prototype Lab", base),
            ("GX-Machine", APP_BASE_DIR / "data" / "GX-Machine"),
            ("HoloVerse", HOLOVERSE_DIR),
            ("2D Side", base / "2D - Side"),
            ("2D Top", base / "2D - Top"),
            ("2D Hybrid", base / "2D - Hybrid"),
            ("2D Isometric", base / "2D - Isometric"),
            ("3D First", base / "3D - First Person"),
            ("3D Third", base / "3D - Third Person"),
        ]
        return [(label, path) for label, path in entries if Path(path).exists()]

    def _refresh_locations(self) -> None:
        return

    def _on_location_select(self, _event=None) -> None:
        return

    def _on_location_open(self, _event=None) -> str:
        return "break"

    def set_path(self, path: Path, push: bool = True) -> None:
        if self.tree is None:
            return
        path = Path(path)
        if path.is_file():
            path = path.parent
        if not path.exists():
            if _owned_missing_folder_allowed(path):
                try:
                    path.mkdir(parents=True, exist_ok=True)
                except Exception:
                    pass
            else:
                self.status_var.set(f"Folder does not exist: {path}")
                return
        self.current_path = path
        self.path_var.set(self._safe_rel_path(path))
        if push:
            if self.history_index < len(self.history) - 1:
                self.history = self.history[: self.history_index + 1]
            if not self.history or self.history[-1] != path:
                self.history.append(path)
                self.history = self.history[-60:]
                self.history_index = len(self.history) - 1
        self.refresh()

    def refresh(self) -> None:
        if self.tree is None:
            return
        try:
            for item in self.tree.get_children():
                self.tree.delete(item)
            children = list(self.current_path.iterdir()) if self.current_path.exists() else []
            children.sort(key=lambda p: (not p.is_dir(), p.name.lower()))
            for child in children:
                name = ("[DIR] " if child.is_dir() else "[FILE] ") + child.name
                values = (self._kind(child), self._format_size(child), self._mtime(child))
                self.tree.insert("", "end", iid=str(child), text=name, values=values)
            self.status_var.set(f"{self.active_panel.title()} • {len(children)} item(s)")
            self.selected_path = self.current_path
            self._render_preview(self.current_path)
        except Exception:
            CRASH_REPORTER.write_exception("Left dock shell refresh failed", *sys.exc_info())
            self.status_var.set(f"Could not read folder: {self.current_path}")

    def _on_tree_select(self, _event=None) -> None:
        if self.tree is None:
            return
        sel = self.tree.selection()
        if not sel:
            return
        self.selected_path = Path(sel[0])
        self._render_preview(self.selected_path)

    def _on_tree_activate(self, _event=None) -> str:
        target = self.selected_path
        if target is None:
            return "break"
        if target.is_dir():
            self.set_path(target, push=True)
        else:
            self.run_selected()
        return "break"

    def _render_preview(self, path: Path | None) -> None:
        if self.preview is None:
            return
        lines: list[str] = []
        if path is None:
            lines = ["No selection."]
        else:
            path = Path(path)
            lines.append(path.name or str(path))
            lines.append(f"Type: {self._kind(path)}")
            lines.append(f"Path: {self._safe_rel_path(path)}")
            if path.exists():
                lines.append(f"Modified: {self._mtime(path)}")
            if path.is_dir():
                try:
                    children = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
                    runnable = "yes" if (path / "main.py").exists() else "no"
                    lines.append(f"Items: {len(children)}")
                    lines.append(f"Runnable main.py: {runnable}")
                    lines.append("")
                    for child in children[:12]:
                        lines.append(f"{'[DIR]' if child.is_dir() else '[FILE]'} {child.name}")
                except Exception as exc:
                    lines.append(f"Folder read failed: {exc}")
            elif path.is_file():
                lines.append(f"Size: {self._format_size(path)}")
                if path.suffix.lower() in {".py", ".txt", ".md", ".json", ".toml", ".yaml", ".yml", ".ini", ".cfg", ".log"}:
                    try:
                        text = path.read_text(encoding="utf-8", errors="ignore")[:2600].strip()
                        if text:
                            lines.append("")
                            lines.append(text)
                    except Exception as exc:
                        lines.append(f"Preview read failed: {exc}")
        try:
            self.preview.configure(state="normal")
            self.preview.delete("1.0", END)
            self.preview.insert("1.0", "\n".join(lines))
            self.preview.configure(state="disabled")
        except Exception:
            pass

    def go_back(self) -> None:
        if self.tree is not None and self.history_index > 0:
            self.history_index -= 1
            self.set_path(self.history[self.history_index], push=False)

    def go_forward(self) -> None:
        if self.tree is not None and self.history_index < len(self.history) - 1:
            self.history_index += 1
            self.set_path(self.history[self.history_index], push=False)

    def go_up(self) -> None:
        if self.tree is None:
            return
        parent = self.current_path.parent
        if parent and parent != self.current_path:
            self.set_path(parent, push=True)

    def go_home(self) -> None:
        if self.active_panel == "matrixcore":
            self.set_path(APP_BASE_DIR / "data" / "GX-Machine", push=True)
        else:
            self.set_path(APP_BASE_DIR / "data" / "Prototype Lab", push=True)

    def focus_desktop(self) -> None:
        self.root.lift()
        try:
            self.root.focus_force()
        except Exception:
            pass
        self.status_var.set("Launcher focused.")

    def open_folder(self) -> None:
        target = self.selected_path or self.current_path
        if target.is_file():
            target = target.parent
        try:
            self.launcher.open_path_in_explorer(target)
            self.status_var.set(f"Opened folder: {target.name}")
        except Exception:
            CRASH_REPORTER.write_exception("Left dock open folder failed", *sys.exc_info())

    def _entry_for_target(self, target: Path) -> tuple[Path | None, str]:
        target = Path(target)
        if target.is_dir():
            entry = self._find_game_entry_in_dir(target)
            if entry is not None:
                return entry, target.name
        if target.is_file() and target.suffix.lower() == ".py":
            return target, target.stem
        return None, target.name or "Prototype Lab"

    def run_selected(self) -> None:
        target = self.selected_path or self.current_path
        entry, app_name = self._entry_for_target(target)
        if entry is None:
            self.status_var.set("Select a Python file or a folder with main.py.")
            return
        try:
            self.launcher.launch_python_entry(entry, app_name, panel_key=f"left_dock_{self.launcher._panel_key_for_minigame(app_name)}")
            self.status_var.set(f"Launched {app_name}.")
        except Exception:
            CRASH_REPORTER.write_exception("Left dock run selected failed", *sys.exc_info())
            try:
                messagebox.showerror("Launch failed", f"Could not launch {app_name}.\nCrash report saved to:\n{CRASH_REPORTER.latest_app}")
            except Exception:
                pass

    def launch_matrix_core_workstation(self) -> None:
        """Compatibility hook: MXOS now lives inside the right-side panel."""
        self.open_mxos_panel()

    def open_holoverse(self) -> None:
        try:
            self.launcher.open_holoverse_project()
            self.status_var.set("HoloVerse launched. Launcher minimized so controls go to the game.")
            try:
                self.root.after(650, self.root.iconify)
            except Exception:
                pass
        except Exception:
            CRASH_REPORTER.write_exception("HoloVerse launch failed", *sys.exc_info())

    def _request_close(self) -> None:
        try:
            self.launcher.request_close()
        except Exception:
            try:
                self.root.destroy()
            except Exception:
                pass




# Rebind startup/logo helpers to the shared gx_core implementations.
# The large legacy module contains older duplicate definitions later in the file;
# these assignments ensure the shared, maintained versions remain authoritative.
_find_brand_logo_path = gx_runtime._find_brand_logo_path
startup_logo_candidates = gx_runtime.startup_logo_candidates
startup_audio_candidates = gx_runtime.startup_audio_candidates
play_startup_audio_once = gx_runtime.play_startup_audio_once
stop_startup_audio = gx_runtime.stop_startup_audio
create_startup_overlay = gx_runtime.create_startup_overlay
begin_startup_handoff = gx_runtime.begin_startup_handoff
run_panda3d_startup_splash = gx_runtime.run_panda3d_startup_splash


def _apply_window_icon(root: tk.Misc) -> None:
    icon_dir = RESOURCE_BASE_DIR / "assets" / "icons"
    png_candidates = [
        APP_BASE_DIR / "launcher_logo.png",
        RESOURCE_BASE_DIR / "launcher_logo.png",
        APP_BASE_DIR / "assets" / "launcher_logo.png",
        RESOURCE_BASE_DIR / "assets" / "launcher_logo.png",
        icon_dir / "GXPrototypeLab_window.png",
        icon_dir / "GXPrototypeLab.png",
    ]
    ico_candidates = [
        icon_dir / "GXPrototypeLab.ico",
    ]

    for png_path in png_candidates:
        try:
            if png_path.exists():
                icon_img = tk.PhotoImage(file=str(png_path))
                root._GXPrototypeLab_icon_ref = icon_img
                root.iconphoto(True, icon_img)
                break
        except Exception:
            continue

    if os.name == "nt":
        for ico_path in ico_candidates:
            try:
                if ico_path.exists():
                    root.iconbitmap(str(ico_path))
                    break
            except Exception:
                continue


def _env_truthy(name: str) -> bool:
    return str(os.environ.get(name, "")).strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = str(os.environ.get(name, "")).strip()
    if not raw:
        return int(default)
    try:
        return int(raw)
    except Exception:
        return int(default)


def _capture_root_screenshot(target_path: Path) -> bool:
    try:
        target_path = Path(target_path)
        target_path.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        return False
    if ImageGrab is not None:
        try:
            grab = ImageGrab.grab()
            if grab is not None:
                grab.save(target_path)
                return True
        except Exception:
            pass
    import_cmd = shutil.which("import")
    if import_cmd:
        try:
            proc = subprocess.run([import_cmd, "-window", "root", str(target_path)], capture_output=True, text=True, timeout=12)
            if proc.returncode == 0 and target_path.exists() and target_path.stat().st_size > 0:
                return True
        except Exception:
            pass
    return target_path.exists() and target_path.stat().st_size > 0



def _capture_manual_forefront_screenshot(root=None, status_callback=None) -> Path | None:
    """F12 helper: capture the currently visible desktop/front screen.

    This is intentionally a broad screen grab rather than a widget-only capture,
    so it can record the foreground state around Prototype Lab without creating
    hidden helper processes or launch delays. It is best-effort outside the
    launcher focus; HoloVerse has its own in-engine F12 capture path.
    """
    try:
        stamp = time.strftime("%Y%m%d_%H%M%S")
        target_dir = SCREENSHOTS_DIR / "manual"
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"prototype_lab_forefront_{stamp}.png"
        try:
            if root is not None:
                root.update_idletasks()
        except Exception:
            pass
        ok = _capture_root_screenshot(target)
        status_path = target_dir / "f12_screenshot_status.txt"
        if ok and target.exists() and target.stat().st_size > 0:
            msg = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] F12 screenshot saved: {target}\n"
            try:
                status_path.write_text(msg, encoding="utf-8", errors="replace")
            except Exception:
                pass
            if callable(status_callback):
                try:
                    status_callback(f"F12 screenshot saved: {target.name}")
                except Exception:
                    pass
            return target
        try:
            status_path.write_text(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] F12 screenshot failed: {target}\n", encoding="utf-8", errors="replace")
        except Exception:
            pass
        return None
    except Exception:
        try:
            CRASH_REPORTER.write_exception("F12 Screenshot Failed", *sys.exc_info())
        except Exception:
            pass
        return None


def _play_startup_sfx_low_volume(volume: float = 0.16) -> None:
    """Play data/assets/sfx/start.mp3 once at low volume without blocking startup."""
    if pygame is None:
        return
    candidates = [
        APP_BASE_DIR / "data" / "assets" / "sfx" / "start.mp3",
        RESOURCE_BASE_DIR / "data" / "assets" / "sfx" / "start.mp3",
        DATA_ROOT_DIR / "assets" / "sfx" / "start.mp3",
    ]
    start_file = None
    seen: set[str] = set()
    for candidate in candidates:
        try:
            key = str(Path(candidate).resolve())
        except Exception:
            key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        try:
            if Path(candidate).exists() and Path(candidate).is_file():
                start_file = Path(candidate)
                break
        except Exception:
            continue
    if start_file is None:
        return
    try:
        if not pygame.mixer.get_init():
            pygame.mixer.init()
        pygame.mixer.music.set_volume(max(0.0, min(1.0, float(volume))))
        pygame.mixer.music.load(str(start_file))
        pygame.mixer.music.play(0)
    except Exception:
        try:
            CRASH_REPORTER.write_exception("Startup SFX failed", *sys.exc_info())
        except Exception:
            pass


def main() -> None:
    install_crash_reporter()
    atexit.register(_stop_all_pygame_audio)
    try:
        os.chdir(APP_BASE_DIR)
    except Exception:
        pass

    cli_runtime = gx_runtime.parse_generated_runtime_cli(sys.argv[1:])
    if cli_runtime.get('spec_path') is not None:
        try:
            gx_runtime.run_generated_spec_window(cli_runtime['spec_path'], smoketest_seconds=float(cli_runtime.get('smoketest_seconds', 0.0) or 0.0))
            return
        except Exception:
            CRASH_REPORTER.write_exception('Generated Spec Runtime', *sys.exc_info())
            raise

    embedded_mode = os.environ.get(MATRIXCORE_HOST_ENV_FLAG, "").strip() == "1"
    window_mode = os.environ.get(MATRIXCORE_WINDOW_MODE_ENV_FLAG, "standalone").strip() or "standalone"
    panel_key = os.environ.get(MATRIXCORE_PANEL_ENV_FLAG, "").strip()
    startup_fullscreen = False
    startup_fullscreen_windowed = False

    if not embedded_mode:
        _hide_launcher_console_window()
    _stop_all_pygame_audio()

    root = TkinterDnD.Tk() if TkinterDnD else tk.Tk()
    # Cleaned MXOS-only build: keep the real app window visible immediately.
    # The old intro path hid the root behind a black top-level overlay; after
    # generator/salvage removal, a failed handoff could leave users at a black screen.
    try:
        root.attributes("-alpha", 1.0)
    except Exception:
        pass
    try:
        if embedded_mode:
            root.withdraw()
        else:
            root.deiconify()
            root.lift()
        setattr(root, "_startup_handoff_pending", False)
    except Exception:
        pass
    root.title(APP_TITLE if not embedded_mode else f"{APP_TITLE} • Embedded")
    if not embedded_mode:
        _play_startup_sfx_low_volume(0.16)
    _apply_detected_window_mode(root, fullscreen=startup_fullscreen, fullscreen_windowed=startup_fullscreen_windowed)
    if embedded_mode:
        try:
            root.attributes("-topmost", False)
        except Exception:
            pass
    _apply_window_icon(root)

    startup_overlay = None
    startup_audio_started = False
    startup_audio_used_music = True
    # Startup overlay disabled in this cleaned build to avoid black-screen launch stalls.
    startup_overlay = None

    launcher = None
    sim = None
    shutdown_started = False
    cleanup_handle = None
    forced_exit_timer = None

    cleanup_module = _load_bridge_exit_cleanup_module()
    release_exit_cleanup_enabled = str(os.environ.get("GX_ENABLE_EXIT_CLEANUP", "")).strip().lower() in {"1", "true", "yes", "on"}
    if cleanup_module is not None and release_exit_cleanup_enabled:
        try:
            cleanup_handle = cleanup_module.install_exit_cleanup(
                root=APP_BASE_DIR,
                output_path=None,
                debug_image_path=None,
                wipe_test_workspace=True,
                protect_logs=True,
                enabled=True,
            )
        except Exception:
            cleanup_handle = None

    def _force_exit() -> None:
        try:
            os._exit(0)
        except Exception:
            pass

    def _arm_force_exit_watchdog() -> None:
        nonlocal forced_exit_timer
        if forced_exit_timer is not None:
            return
        try:
            delay = float(os.environ.get("GX_FORCE_EXIT_SECONDS", "3.0") or 3.0)
        except Exception:
            delay = 3.0
        delay = max(1.0, min(10.0, delay))
        try:
            forced_exit_timer = threading.Timer(delay, _force_exit)
            forced_exit_timer.daemon = True
            forced_exit_timer.start()
        except Exception:
            pass

    def _shutdown(*_args):
        nonlocal launcher, sim, shutdown_started
        if shutdown_started:
            return
        shutdown_started = True
        _arm_force_exit_watchdog()
        _stop_all_pygame_audio()
        try:
            if sim is not None:
                sim.shutdown()
        except Exception:
            CRASH_REPORTER.write_exception("MXOS-only Shell Shutdown Failed", *sys.exc_info())
        try:
            if cleanup_handle is not None:
                cleanup_handle()
        except Exception:
            CRASH_REPORTER.write_exception("Exit Cleanup Failed", *sys.exc_info())
        try:
            if launcher is not None:
                launcher.request_close()
            else:
                root.quit()
                root.destroy()
        except Exception:
            CRASH_REPORTER.write_exception("Launcher Request Close Failed", *sys.exc_info())
            try:
                root.quit()
            except Exception:
                pass
            try:
                root.destroy()
            except Exception:
                pass
        try:
            CRASH_REPORTER.clear_latest("app")
        except Exception:
            pass
        _arm_force_exit_watchdog()

    def _manual_capture_hotkey(*_args):
        def _status(message: str) -> None:
            try:
                if sim is not None:
                    sim._append_chat("System", message)
            except Exception:
                pass
        _capture_manual_forefront_screenshot(root=root, status_callback=_status)
        return "break"

    try:
        root.protocol("WM_DELETE_WINDOW", _shutdown)
    except Exception:
        pass
    if not embedded_mode:
        try:
            root.bind_all('<Control-q>', lambda _e: _shutdown())
            root.bind_all('<Control-w>', lambda _e: _shutdown())
            root.bind_all('<Control-m>', lambda _e: root.iconify())
            root.bind_all('<F12>', _manual_capture_hotkey)
            root.bind_all('<Escape>', lambda _e: _shutdown())
        except Exception:
            pass

    launcher = MatrixCoreStandaloneLauncher(root)
    shell = Frame(root, bg=MXOSOnlyShell.THEME["bg"])
    shell.pack(fill=BOTH, expand=True)
    sim = MXOSOnlyShell(launcher, shell, root)
    if embedded_mode:
        try:
            sim._append_chat("System", f"MXOS-only embedded host detected: mode={window_mode} panel={panel_key or 'external'}")
        except Exception:
            pass
    if embedded_mode:
        root.deiconify()
        try:
            root.update_idletasks()
        except Exception:
            pass
    else:
        try:
            setattr(root, "_startup_handoff_pending", False)
            root.attributes("-alpha", 1.0)
            root.deiconify()
            root.lift()
            root.update_idletasks()
            root.update()
        except Exception:
            CRASH_REPORTER.write_exception("Startup Root Reveal Failed", *sys.exc_info())

    def _force_visible_root() -> None:
        try:
            setattr(root, "_startup_handoff_pending", False)
            root.attributes("-alpha", 1.0)
            root.deiconify()
            root.lift()
            root.update_idletasks()
        except Exception:
            pass

    if not embedded_mode:
        try:
            root.after(250, _force_visible_root)
            root.after(1500, _force_visible_root)
        except Exception:
            _force_visible_root()

    autoshot_path_raw = str(os.environ.get("GX_AUTOSHOT_PATH", "")).strip()
    if autoshot_path_raw:
        autoshot_path = Path(autoshot_path_raw)
        autoshot_delay_ms = max(400, _env_int("GX_AUTOSHOT_DELAY_MS", 2600))

        def _auto_capture_launch() -> None:
            try:
                if sim is not None and _env_truthy("GX_SHOW_BUTTON_OVERLAY"):
                    sim.shell_hotspot_debug = True
                    sim._update_shell_hotspot_debug_widgets()
                root.deiconify()
                root.update_idletasks()
                root.update()
            except Exception:
                pass
            ok = _capture_root_screenshot(autoshot_path)
            if not ok:
                try:
                    CRASH_REPORTER.write_text("Launch Screenshot Failed", f"Could not capture launcher screenshot at {autoshot_path}")
                except Exception:
                    pass
            try:
                root.after(180, _shutdown)
            except Exception:
                _shutdown()

        try:
            root.after(autoshot_delay_ms, _auto_capture_launch)
        except Exception:
            CRASH_REPORTER.write_exception("Launch Screenshot Scheduling Failed", *sys.exc_info())
    try:
        root.mainloop()
    finally:
        _shutdown()

if __name__ == "__main__":
    main()
