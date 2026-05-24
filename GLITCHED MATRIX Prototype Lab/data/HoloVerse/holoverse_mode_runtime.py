#!/usr/bin/env python3
"""Shared compatibility helpers for HoloVerse-hosted standalone modes.

This module is deliberately dependency-light so Pygame and Panda3D modes can
import it before their own display system starts.  The HoloVerse Core owns the
universal settings file; mode-local settings should only fill gameplay-specific
options that the hub does not manage.
"""
from __future__ import annotations

import json
import os
import random
import sys
import time
from pathlib import Path
from typing import Any

BASE_CANVAS = (1920, 1080)


IN_WORLD_ROUTE = "in_world_region"
IN_WORLD_ROUTE_ALIASES = {"in_world", "in_world_region", "region_runtime", "current_region", "same_world", "same_region"}


def install_in_world_route_aliases(main_module: object) -> None:
    """Teach the HoloVerse gateway to treat dimension-local runtimes as in-world routes.

    Several region runtimes used to carry identical monkey patches for
    ``normalize_mode_launch_type``, ``route_display_name``, and
    ``transition_route_for_launch_type``.  Keeping the hook here prevents the
    region files from drifting apart and makes future route changes single-point.
    """
    if main_module is None:
        return

    old_normalize = getattr(main_module, "normalize_mode_launch_type", None)
    if callable(old_normalize) and not getattr(old_normalize, "_holoverse_in_world_alias_patch", False):
        def normalize_mode_launch_type(value):
            raw = str(value or "").strip().lower()
            if raw in IN_WORLD_ROUTE_ALIASES:
                return IN_WORLD_ROUTE
            return old_normalize(value)

        setattr(normalize_mode_launch_type, "_holoverse_in_world_alias_patch", True)
        main_module.normalize_mode_launch_type = normalize_mode_launch_type

    old_route_display = getattr(main_module, "route_display_name", None)
    if callable(old_route_display) and not getattr(old_route_display, "_holoverse_in_world_alias_patch", False):
        def route_display_name(launch_type: str) -> str:
            raw = str(launch_type or "").strip().lower()
            if raw in IN_WORLD_ROUTE_ALIASES:
                return "IN-WORLD"
            try:
                if main_module.normalize_mode_launch_type(launch_type) == IN_WORLD_ROUTE:
                    return "IN-WORLD"
            except Exception:
                pass
            return old_route_display(launch_type)

        setattr(route_display_name, "_holoverse_in_world_alias_patch", True)
        main_module.route_display_name = route_display_name

    old_transition = getattr(main_module, "transition_route_for_launch_type", None)
    if callable(old_transition) and not getattr(old_transition, "_holoverse_in_world_alias_patch", False):
        def transition_route_for_launch_type(launch_type, *, placeholder=False):
            try:
                if main_module.normalize_mode_launch_type(launch_type) == IN_WORLD_ROUTE:
                    return "transition_in_world_region"
            except Exception:
                pass
            return old_transition(launch_type, placeholder=placeholder)

        setattr(transition_route_for_launch_type, "_holoverse_in_world_alias_patch", True)
        main_module.transition_route_for_launch_type = transition_route_for_launch_type



def resolve_shared_data_root(main_module: object | None = None, root: Path | str | None = None) -> Path:
    """Resolve the app-owned shared data folder without creating data/data.

    HoloVerse itself lives at ``<app>/data/HoloVerse``. Region runtimes should
    save shared state to ``<app>/data``; older code accidentally used
    ``ROOT.parent / \"data\"``, which becomes ``<app>/data/data``.
    """
    for env_name in ("HOLOVERSE_APP_DATA_DIR", "GXPLAB_DATA_DIR"):
        raw = os.environ.get(env_name, "").strip()
        if raw:
            try:
                return Path(raw).resolve()
            except Exception:
                return Path(raw)

    if main_module is not None:
        for attr in ("APP_DATA_DIR", "SHARED_HOLOVERSE_DATA_DIR"):
            value = getattr(main_module, attr, None)
            if value:
                try:
                    return Path(value).resolve()
                except Exception:
                    return Path(value)

    root_path = Path(root) if root is not None else Path(__file__).resolve().parent
    try:
        root_path = root_path.resolve()
    except Exception:
        pass

    if root_path.name.lower() == "holoverse" and root_path.parent.name.lower() == "data":
        return root_path.parent
    if root_path.name.lower() == "data" and (root_path / "HoloVerse").exists():
        return root_path

    sibling_data = root_path.parent / "data"
    if sibling_data.exists() and (sibling_data / "HoloVerse").exists():
        return sibling_data

    return root_path.parent


def resolve_accidental_nested_data_root(root: Path | str | None = None) -> Path:
    """Return the old accidental nested data lane for read-only migration checks.

    Callers must not mkdir or write through this path; it only lets updated
    runtimes recover state from old builds that already created it.
    """
    root_path = Path(root) if root is not None else Path(__file__).resolve().parent
    try:
        root_path = root_path.resolve()
    except Exception:
        pass
    return root_path.parent / "data"

def truthy(value: object) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def embedded_mode() -> bool:
    return truthy(
        os.environ.get("HOLOVERSE_EMBEDDED_MODE")
        or os.environ.get("HOLOVERSE_EMBEDDED_CHILD")
        or os.environ.get("HOLOVERSE_HOSTED")
    )


def settings_path() -> Path:
    raw = os.environ.get("HOLOVERSE_SETTINGS_PATH", "").strip()
    if raw:
        return Path(raw)
    return Path(__file__).resolve().parent / "config" / "holoverse_settings.json"


def load_settings() -> dict[str, Any]:
    try:
        path = settings_path()
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}


def setting(name: str, default=None):
    return load_settings().get(name, default)


def _env_int(name: str, default: int) -> int:
    try:
        return int(float(os.environ.get(name, default)))
    except Exception:
        return int(default)


def _clamp_int(value: int, low: int, high: int) -> int:
    return max(low, min(high, int(value)))


def resolution(default: tuple[int, int] = BASE_CANVAS) -> tuple[int, int]:
    """Return the OS/window resolution requested by the Core."""
    data = load_settings().get("resolution", {})
    if not isinstance(data, dict):
        data = {}
    width = _env_int("MATRIX_GAME_WIDTH", int(data.get("width") or default[0]))
    height = _env_int("MATRIX_GAME_HEIGHT", int(data.get("height") or default[1]))
    return _clamp_int(width, 640, 3840), _clamp_int(height, 360, 2160)


def virtual_canvas(default: tuple[int, int] = BASE_CANVAS) -> tuple[int, int]:
    """Return the fixed internal 16:9 canvas for mode rendering.

    Modes should draw to this size and letterbox/pillarbox into the current OS
    window.  This prevents resize from expanding gameplay space.
    """
    data = load_settings().get("virtual_canvas", {})
    if not isinstance(data, dict):
        data = {}
    width = _env_int("HOLOVERSE_VIRTUAL_WIDTH", int(data.get("width") or default[0]))
    height = _env_int("HOLOVERSE_VIRTUAL_HEIGHT", int(data.get("height") or default[1]))
    return _clamp_int(width, 640, 3840), _clamp_int(height, 360, 2160)


def fps_cap(default: int = 60) -> int:
    try:
        value = int(float(os.environ.get("HOLOVERSE_FPS_CAP") or load_settings().get("fps_cap", default)))
    except Exception:
        value = default
    return _clamp_int(value, 30, 240)


def vsync(default: bool = True) -> bool:
    raw = os.environ.get("HOLOVERSE_VSYNC")
    if raw is not None:
        return truthy(raw)
    return bool(load_settings().get("vsync", default))


def ui_scale(default: float = 1.0) -> float:
    try:
        return max(0.6, min(2.0, float(os.environ.get("HOLOVERSE_UI_SCALE") or load_settings().get("ui_scale", default))))
    except Exception:
        return default


def volume(name: str, default: float = 1.0) -> float:
    try:
        env_name = "HOLOVERSE_" + str(name).upper()
        return max(0.0, min(1.0, float(os.environ.get(env_name, load_settings().get(name, default)))))
    except Exception:
        return default


def compute_letterbox(window_size: tuple[int, int], canvas_size: tuple[int, int] = BASE_CANVAS) -> tuple[float, tuple[int, int], tuple[int, int]]:
    win_w, win_h = max(1, int(window_size[0])), max(1, int(window_size[1]))
    can_w, can_h = max(1, int(canvas_size[0])), max(1, int(canvas_size[1]))
    scale = min(win_w / can_w, win_h / can_h)
    view_w = max(1, int(can_w * scale))
    view_h = max(1, int(can_h * scale))
    off_x = (win_w - view_w) // 2
    off_y = (win_h - view_h) // 2
    return scale, (view_w, view_h), (off_x, off_y)


def window_to_canvas(pos: tuple[int, int], window_size: tuple[int, int], canvas_size: tuple[int, int] = BASE_CANVAS, *, clamp: bool = True) -> tuple[int, int]:
    scale, view_size, offset = compute_letterbox(window_size, canvas_size)
    x = (int(pos[0]) - offset[0]) / max(scale, 1e-6)
    y = (int(pos[1]) - offset[1]) / max(scale, 1e-6)
    if clamp:
        x = max(0, min(canvas_size[0] - 1, x))
        y = max(0, min(canvas_size[1] - 1, y))
    return int(x), int(y)


def point_in_view(pos: tuple[int, int], window_size: tuple[int, int], canvas_size: tuple[int, int] = BASE_CANVAS) -> bool:
    _scale, view_size, offset = compute_letterbox(window_size, canvas_size)
    x, y = int(pos[0]), int(pos[1])
    return offset[0] <= x < offset[0] + view_size[0] and offset[1] <= y < offset[1] + view_size[1]


def panda_prc_lines(title: str = "HoloVerse Mode", default: tuple[int, int] = BASE_CANVAS) -> str:
    """Return a conservative PRC block for hosted Panda3D modes."""
    width, height = resolution(default)
    sync = "true" if vsync(True) else "false"
    return f"""
        window-title {title}
        win-size {width} {height}
        fullscreen false
        undecorated false
        sync-video {sync}
        show-frame-rate-meter false
        textures-power-2 none
        model-cache-dir
    """


def return_signal_path() -> Path | None:
    raw = os.environ.get("HOLOVERSE_RETURN_SIGNAL_PATH", "").strip()
    return Path(raw) if raw else None

def return_requested() -> bool:
    path = return_signal_path()
    try:
        return bool(path and path.exists())
    except Exception:
        return False

def read_return_request() -> dict[str, Any]:
    path = return_signal_path()
    if path is None:
        return {}
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
    except Exception:
        pass
    return {}

def acknowledge_return_request() -> None:
    path = return_signal_path()
    if path is None:
        return
    try:
        path.unlink(missing_ok=True)
    except Exception:
        pass

def parent_alive() -> bool:
    raw = os.environ.get("HOLOVERSE_PARENT_PID", "").strip()
    if not raw:
        return True
    try:
        pid = int(raw)
    except Exception:
        return True
    if pid <= 0:
        return True
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False
    except Exception:
        return True

def should_return_to_core() -> bool:
    return embedded_mode() and (return_requested() or not parent_alive())

def poll_return_to_core() -> None:
    if should_return_to_core():
        acknowledge_return_request()
        return_to_core(0)


def return_to_core(code: int = 0) -> None:
    sys.exit(code)


_ESC_LAST_TAP_AT = 0.0
_ESC_DOWN_AT = 0.0
_ESC_HOLD_TRIGGERED = False

def embedded_escape_pressed(default_handler=None, *, double_tap_seconds: float = 1.35, hold_seconds: float = 1.05):
    """Hosted-mode ESC: first tap can open mode menu; double-tap or hold exits to hub."""
    global _ESC_LAST_TAP_AT, _ESC_DOWN_AT, _ESC_HOLD_TRIGGERED
    if not embedded_mode():
        if callable(default_handler): return default_handler()
        return None
    now = time.monotonic()
    if _ESC_LAST_TAP_AT and (now - _ESC_LAST_TAP_AT) <= max(0.25, float(double_tap_seconds)):
        acknowledge_return_request(); return_to_core(0)
    _ESC_LAST_TAP_AT = now; _ESC_DOWN_AT = now; _ESC_HOLD_TRIGGERED = False
    if callable(default_handler): return default_handler()
    return None

def embedded_escape_released() -> None:
    global _ESC_DOWN_AT, _ESC_HOLD_TRIGGERED
    _ESC_DOWN_AT = 0.0; _ESC_HOLD_TRIGGERED = False

def poll_embedded_escape_hold(*, hold_seconds: float = 1.05) -> None:
    global _ESC_HOLD_TRIGGERED
    if not embedded_mode() or not _ESC_DOWN_AT or _ESC_HOLD_TRIGGERED: return
    if (time.monotonic() - float(_ESC_DOWN_AT)) >= max(0.45, float(hold_seconds)):
        _ESC_HOLD_TRIGGERED = True; acknowledge_return_request(); return_to_core(0)

def pygame_embedded_escape_event(event) -> bool:
    """Consume hosted Pygame ESC keydown/up so Pygame modes support double-tap/hold hub return."""
    if not embedded_mode(): return False
    try:
        import pygame
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            embedded_escape_pressed(None); return True
        if event.type == pygame.KEYUP and event.key == pygame.K_ESCAPE:
            embedded_escape_released(); return True
    except SystemExit: raise
    except Exception: return False
    return False


UNIVERSAL_OVERRIDE_KEYS = {
    "display_mode", "resolution", "virtual_canvas", "render_scale", "ui_scale",
    "fullscreen", "borderless", "bordered_fullscreen", "vsync", "fps_cap",
    "master_volume", "music_volume", "sfx_volume", "ambience_volume",
    "soundtrack_enabled", "soundtrack_intensity", "ambience_intensity",
    "soundmatrix_variant_intensity", "soundmatrix_music_intensity",
    "mouse_sensitivity", "invert_y", "hud_enabled", "subtitles_enabled",
    "brightness", "contrast", "gamma", "graphics_quality", "controller_deadzone",
    "pause_key", "return_to_core_key",
}

SETTING_ALIASES = {
    "hud_visible": "hud_enabled",
    "show_hud": "hud_enabled",
    "subtitles": "subtitles_enabled",
    "look_sensitivity": "mouse_sensitivity",
}

def override_enabled(default: bool = True) -> bool:
    raw = os.environ.get("HOLOVERSE_OVERRIDE_MODE_SETTINGS") or os.environ.get("HOLOVERSE_OVERRIDE_SETTINGS")
    if raw is not None:
        return truthy(raw)
    return bool(load_settings().get("override_mode_settings", default))

def canonical_setting_name(name: str) -> str:
    return SETTING_ALIASES.get(str(name), str(name))

def merged_settings(local: dict[str, Any] | None = None, *, core: dict[str, Any] | None = None, core_priority: bool | None = None) -> dict[str, Any]:
    """Merge local mode settings with hub settings.

    Universal keys are owned by the HoloVerse Core when override_mode_settings is true.
    Mode-local settings remain available for gameplay-specific values.
    """
    local_data = dict(local or {})
    core_data = dict(core if core is not None else load_settings())
    if core_priority is None:
        core_priority = override_enabled(True)
    merged = dict(local_data)
    if core_priority:
        for key, value in core_data.items():
            ckey = canonical_setting_name(key)
            if ckey in UNIVERSAL_OVERRIDE_KEYS or key in UNIVERSAL_OVERRIDE_KEYS:
                merged[ckey] = value
        # also expose non-universal metadata without replacing local gameplay keys
        for meta_key in ("schema", "source", "settings_authority", "companion_profiles"):
            if meta_key in core_data:
                merged.setdefault(meta_key, core_data[meta_key])
    else:
        for key, value in core_data.items():
            ckey = canonical_setting_name(key)
            merged.setdefault(ckey, value)
    return merged

def bool_setting(name: str, default: bool = False) -> bool:
    env_name = "HOLOVERSE_" + canonical_setting_name(name).upper()
    if env_name in os.environ:
        return truthy(os.environ.get(env_name))
    value = merged_settings().get(canonical_setting_name(name), default)
    if isinstance(value, bool):
        return value
    return truthy(value) if value is not None else default

def int_setting(name: str, default: int = 0, low: int | None = None, high: int | None = None) -> int:
    env_name = "HOLOVERSE_" + canonical_setting_name(name).upper()
    raw = os.environ.get(env_name, merged_settings().get(canonical_setting_name(name), default))
    try:
        value = int(float(raw))
    except Exception:
        value = int(default)
    if low is not None:
        value = max(int(low), value)
    if high is not None:
        value = min(int(high), value)
    return value

def float_setting(name: str, default: float = 0.0, low: float | None = None, high: float | None = None) -> float:
    env_name = "HOLOVERSE_" + canonical_setting_name(name).upper()
    raw = os.environ.get(env_name, merged_settings().get(canonical_setting_name(name), default))
    try:
        value = float(raw)
    except Exception:
        value = float(default)
    if low is not None:
        value = max(float(low), value)
    if high is not None:
        value = min(float(high), value)
    return value

def keybind(name: str, default: str = "") -> str:
    env_name = "HOLOVERSE_" + canonical_setting_name(name).upper()
    return str(os.environ.get(env_name, merged_settings().get(canonical_setting_name(name), default)) or default).strip().lower()

def visual_profile() -> dict[str, float]:
    return {
        "brightness": float_setting("brightness", 1.0, 0.55, 1.65),
        "contrast": float_setting("contrast", 1.0, 0.55, 1.65),
        "gamma": float_setting("gamma", 1.0, 0.55, 1.85),
        "render_scale": float_setting("render_scale", 1.0, 0.50, 1.50),
        "ui_scale": ui_scale(1.0),
    }

def audio_profile() -> dict[str, float]:
    return {
        "master_volume": volume("master_volume", 1.0),
        "music_volume": volume("music_volume", 1.0),
        "sfx_volume": volume("sfx_volume", 1.0),
        "ambience_volume": volume("ambience_volume", 1.0),
    }


AUDIO_EXTENSIONS = (".wav", ".ogg", ".mp3")


def audio_library_root() -> Path:
    raw = os.environ.get("HOLOVERSE_AUDIO_ROOT") or os.environ.get("MATRIX_AUDIO_ROOT")
    if raw:
        return Path(raw)
    settings = load_settings()
    raw2 = str(settings.get("audio_root", "") or settings.get("sound_and_music", {}).get("audio_root", "")).strip()
    if raw2:
        p = Path(raw2)
        return p if p.is_absolute() else Path(__file__).resolve().parent / p
    return Path(__file__).resolve().parent / "assets" / "audio"


def _setting_path(value: object) -> Path | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    p = Path(raw)
    return p if p.is_absolute() else Path(__file__).resolve().parent / p


def _unique_existing_first(paths: list[Path]) -> list[Path]:
    out: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        try:
            key = str(path.resolve()) if path.exists() else str(path)
        except Exception:
            key = str(path)
        if key in seen:
            continue
        seen.add(key)
        out.append(path)
    out.sort(key=lambda p: (not p.exists(), str(p).lower()))
    return out


def shared_sfx_roots() -> list[Path]:
    """Return canonical then legacy shared SFX roots."""
    settings = load_settings()
    sam = settings.get("sound_and_music", {}) if isinstance(settings.get("sound_and_music", {}), dict) else {}
    candidates: list[Path] = []
    for raw in (
        os.environ.get("HOLOVERSE_SHARED_SFX_DIR"),
        os.environ.get("MATRIX_SHARED_SFX_DIR"),
        settings.get("shared_sfx_root"),
        sam.get("shared_sfx_root"),
    ):
        p = _setting_path(raw)
        if p is not None:
            candidates.append(p)
    root_dir = Path(__file__).resolve().parent
    candidates.extend([
        audio_library_root() / "sfx" / "shared",
        root_dir / "assets" / "shared_sfx",
        # Slim source exports can omit the generated shared SFX library while
        # still carrying the committed Vector Wars event sounds.  Treat those
        # sounds as the last shared fallback so every profile-driven dimension
        # can resolve weapons/hit/UI cues instead of silently falling back to
        # generic menu bleeps.
        root_dir / "assets" / "audio" / "source" / "vector_wars",
        root_dir / "Dimensions" / "Vector Wars" / "assets" / "sfx",
    ])
    for raw in (os.environ.get("HOLOVERSE_LEGACY_SHARED_SFX_DIR"), settings.get("shared_sfx_legacy_root"), sam.get("shared_sfx_legacy_root")):
        p = _setting_path(raw)
        if p is not None:
            candidates.append(p)
    return _unique_existing_first(candidates)


def shared_sfx_root() -> Path:
    """Return the preferred shared HoloVerse SFX root used by all hosted modes."""
    roots = shared_sfx_roots()
    return roots[0] if roots else Path(__file__).resolve().parent / "assets" / "audio" / "sfx" / "shared"


def sfx_bus_gain(bus: str = "sfx", base: float = 1.0) -> float:
    profile = audio_profile()
    master = profile.get("master_volume", 1.0)
    bus_gain = profile.get(f"{bus}_volume", profile.get("sfx_volume", 1.0))
    try:
        return max(0.0, min(1.0, float(base) * float(master) * float(bus_gain)))
    except Exception:
        return max(0.0, min(1.0, float(base)))


_SFX_CATEGORY_FALLBACKS: dict[str, tuple[str, ...]] = {
    # Vector Wars ships only three committed cue folders.  These aliases let
    # older audio_profile.json files with richer categories resolve to those
    # real cues when the full shared library is not present.
    "damage/hit": ("weapons/guns",),
    "damage/destroy": ("weapons/guns", "weapons/missiles"),
    "ambient/battle": ("weapons/guns", "weapons/missiles"),
    "science": ("weapons/lasers", "ui"),
    "ui": ("ui", "weapons/lasers"),
}


def shared_sfx_files(category: str, *, extensions: tuple[str, ...] = AUDIO_EXTENSIONS) -> list[Path]:
    category = str(category or "").replace("\\", "/").strip("/")
    search_categories = [category]
    for fallback in _SFX_CATEGORY_FALLBACKS.get(category, ()):
        if fallback not in search_categories:
            search_categories.append(fallback)
    files: list[Path] = []
    for root in shared_sfx_roots():
        for rel_category in search_categories:
            if not rel_category:
                continue
            folder = root / rel_category
            if not folder.exists() or not folder.is_dir():
                continue
            for ext in extensions:
                files.extend(sorted(folder.glob(f"*{ext}")))
                files.extend(sorted(folder.glob(f"*{ext.upper()}")))
    # Prefer wav/ogg over mp3 for short SFX because mixer mp3 support varies.
    files = sorted(set(files), key=lambda p: (p.suffix.lower() == ".mp3", p.name.lower()))
    return files


def first_shared_sfx(category: str) -> Path | None:
    files = shared_sfx_files(category)
    return files[0] if files else None



def shared_music_roots() -> list[Path]:
    settings = load_settings()
    sam = settings.get("sound_and_music", {}) if isinstance(settings.get("sound_and_music", {}), dict) else {}
    candidates: list[Path] = []
    for raw in (
        os.environ.get("HOLOVERSE_MUSIC_DIR"),
        os.environ.get("MATRIX_MUSIC_DIR"),
        settings.get("music_root"),
        sam.get("music_root"),
        settings.get("ambient_music_root"),
        sam.get("ambient_music_root"),
    ):
        p = _setting_path(raw)
        if p is not None:
            candidates.append(p)
    candidates.extend([
        audio_library_root() / "music" / "generated",
        audio_library_root() / "music" / "ambient",
        Path(__file__).resolve().parent / "assets" / "music",
        Path(__file__).resolve().parent / "assets" / "generated_audio",
    ])
    for raw in (os.environ.get("HOLOVERSE_LEGACY_MUSIC_DIR"), settings.get("music_legacy_root"), sam.get("music_legacy_root")):
        p = _setting_path(raw)
        if p is not None:
            candidates.append(p)
    return _unique_existing_first(candidates)


def shared_music_root() -> Path:
    roots = shared_music_roots()
    return roots[0] if roots else Path(__file__).resolve().parent / "assets" / "audio" / "music" / "generated"


def music_files(*, extensions: tuple[str, ...] = AUDIO_EXTENSIONS) -> list[Path]:
    files: list[Path] = []
    for root in shared_music_roots():
        if not root.exists() or not root.is_dir():
            continue
        for ext in extensions:
            files.extend(sorted(root.glob(f"*{ext}")))
            files.extend(sorted(root.glob(f"*{ext.upper()}")))
    return sorted(set(files), key=lambda p: (p.suffix.lower() == ".mp3", p.name.lower()))




def audio_profile_path(mode_dir: Path | str | None = None) -> Path | None:
    """Return the mode audio profile path supplied by Core or discovered beside the mode."""
    raw = os.environ.get("HOLOVERSE_MODE_AUDIO_PROFILE", "").strip()
    if raw:
        return Path(raw)
    try:
        base = Path(mode_dir) if mode_dir is not None else Path.cwd()
        candidate = base / "audio_profile.json"
        if candidate.exists():
            return candidate
    except Exception:
        pass
    return None


def load_audio_profile(mode_dir: Path | str | None = None) -> dict[str, Any]:
    path = audio_profile_path(mode_dir)
    if path is None:
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _profile_event(profile: dict[str, Any] | None, event: str) -> dict[str, Any]:
    events = (profile or {}).get("events", {})
    item = events.get(str(event), {}) if isinstance(events, dict) else {}
    return item if isinstance(item, dict) else {}


def profile_sfx_files(event: str, *, profile: dict[str, Any] | None = None, mode_dir: Path | str | None = None) -> list[Path]:
    """Resolve an event name through audio_profile.json into shared SFX files."""
    prof = profile if profile is not None else load_audio_profile(mode_dir)
    item = _profile_event(prof, event)
    files: list[Path] = []
    preferred = item.get("preferred", [])
    if isinstance(preferred, str):
        preferred = [preferred]
    categories = item.get("categories", item.get("category", []))
    if isinstance(categories, str):
        categories = [categories]
    root = shared_sfx_root()
    for cat in categories:
        folder = root / str(cat).replace("\\", "/").strip("/")
        for pref in preferred:
            candidate = folder / str(pref)
            if candidate.exists() and candidate.is_file():
                files.append(candidate)
    for cat in categories:
        files.extend(shared_sfx_files(str(cat)))
    seen: set[str] = set()
    out: list[Path] = []
    for path in files:
        key = str(path.resolve()) if path.exists() else str(path)
        if key in seen:
            continue
        seen.add(key)
        out.append(path)
    # Generated/core SFX fallback: slim builds may omit assets/audio/sfx/shared
    # while still shipping assets/generated_audio. Use preferred names first, then
    # safe core UI/action cues so hosted and embedded modes never go silent.
    if not out:
        generated_names = list(preferred) + ["world_shift.wav", "artifact_link.wav", "menu_open.wav", "menu_close.wav", "core_hum.wav"]
        for root in generated_audio_roots():
            if not root.exists() or not root.is_dir():
                continue
            for name in generated_names:
                candidate = root / str(name)
                if candidate.exists() and candidate.is_file():
                    key = str(candidate.resolve())
                    if key not in seen:
                        seen.add(key)
                        out.append(candidate)
            if out:
                break
    return out


def first_profile_sfx(event: str, *, profile: dict[str, Any] | None = None, mode_dir: Path | str | None = None) -> Path | None:
    files = profile_sfx_files(event, profile=profile, mode_dir=mode_dir)
    return files[0] if files else None


def profile_event_volume(event: str, default: float = 1.0, *, profile: dict[str, Any] | None = None, mode_dir: Path | str | None = None) -> float:
    prof = profile if profile is not None else load_audio_profile(mode_dir)
    item = _profile_event(prof, event)
    try:
        return max(0.0, min(1.0, float(item.get("volume", default))))
    except Exception:
        return max(0.0, min(1.0, float(default)))


def _resolve_music_name(name: str) -> Path | None:
    name = str(name or "").strip()
    if not name: return None
    raw = Path(name)
    if raw.is_absolute() and raw.exists() and raw.is_file(): return raw
    for root in shared_music_roots():
        candidate = root / name
        if candidate.exists() and candidate.is_file(): return candidate
    stem = raw.stem
    if stem:
        for path in music_files():
            if path.name == name or path.stem == stem: return path
    return None

def profile_music_paths(*, profile: dict[str, Any] | None = None, mode_dir: Path | str | None = None) -> list[Path]:
    prof = profile if profile is not None else load_audio_profile(mode_dir)
    names: list[str] = []
    for key in ("music_variants", "music_playlist", "music_loops"):
        raw = (prof or {}).get(key, [])
        if isinstance(raw, str): raw = [raw]
        if isinstance(raw, list): names.extend(str(x).strip() for x in raw if str(x).strip())
    loop = str((prof or {}).get("music_loop", "")).strip()
    if loop: names.insert(0, loop)
    out=[]; seen=set()
    for name in names:
        path=_resolve_music_name(name)
        if path is None: continue
        key=str(path.resolve()) if path.exists() else str(path)
        if key in seen: continue
        seen.add(key); out.append(path)
    return out

def profile_music_path(*, profile: dict[str, Any] | None = None, mode_dir: Path | str | None = None) -> Path | None:
    paths = profile_music_paths(profile=profile, mode_dir=mode_dir)
    return paths[0] if paths else None

def next_profile_music_path(current: str | Path | None = None, *, profile: dict[str, Any] | None = None, mode_dir: Path | str | None = None) -> Path | None:
    paths = profile_music_paths(profile=profile, mode_dir=mode_dir)
    if not paths: return None
    cur = str(current or "")
    pool = [p for p in paths if str(p) != cur and p.name != Path(cur).name] or paths
    return random.choice(pool)

def profile_music_rotation_seconds(default: float = 60.0, *, profile: dict[str, Any] | None = None, mode_dir: Path | str | None = None) -> float:
    prof = profile if profile is not None else load_audio_profile(mode_dir)
    try: value = float((prof or {}).get("music_rotation_seconds", default))
    except Exception: value = float(default)
    return max(20.0, min(240.0, value))

def rotate_panda_profile_music(app, *, profile: dict[str, Any] | None = None, default_volume: float = 0.3, bus: str = "music", attr: str = "music") -> None:
    if app is None or not soundtrack_enabled(True): return
    now = time.monotonic()
    if now < float(getattr(app, "_holoverse_next_music_rotate_at", 0.0) or 0.0): return
    current = str(getattr(app, "_holoverse_current_music_path", "") or "")
    path = next_profile_music_path(current, profile=profile)
    if path is None or not path.exists(): return
    try:
        existing = getattr(app, attr, None)
        if existing is not None:
            try: existing.stop()
            except Exception: pass
        try:
            from panda3d.core import Filename
            panda_path = Filename.fromOsSpecific(str(path)) if hasattr(Filename, "fromOsSpecific") else Filename.from_os_specific(str(path))
            snd = app.loader.loadMusic(panda_path)
        except Exception:
            snd = app.loader.loadMusic(str(path))
        if not snd: return
        try: snd.setLoop(True)
        except Exception: pass
        try: snd.setVolume(music_bus_gain(profile_music_volume(default_volume, profile=profile), bus=str((profile or {}).get("music_bus", bus))))
        except Exception: pass
        snd.play(); setattr(app, attr, snd); setattr(app, "_holoverse_current_music_path", str(path)); setattr(app, "_holoverse_next_music_rotate_at", now + profile_music_rotation_seconds(60.0, profile=profile))
    except Exception:
        setattr(app, "_holoverse_next_music_rotate_at", now + 10.0)

def profile_music_volume(default: float = 0.35, *, profile: dict[str, Any] | None = None, mode_dir: Path | str | None = None) -> float:
    prof = profile if profile is not None else load_audio_profile(mode_dir)
    try:
        return max(0.0, min(1.0, float((prof or {}).get("music_volume", default))))
    except Exception:
        return max(0.0, min(1.0, float(default)))


def soundtrack_enabled(default: bool = True) -> bool:
    if os.environ.get("HOLOVERSE_SOUNDTRACK_ENABLED") is not None:
        return truthy(os.environ.get("HOLOVERSE_SOUNDTRACK_ENABLED"))
    profile = sound_and_music_profile()
    return bool(profile.get("soundtrack_enabled", default))


def music_bus_gain(base: float = 1.0, *, bus: str = "music") -> float:
    return sfx_bus_gain(bus, base)


def generated_audio_roots() -> list[Path]:
    settings = load_settings()
    sam = settings.get("sound_and_music", {}) if isinstance(settings.get("sound_and_music", {}), dict) else {}
    candidates: list[Path] = []
    for raw in (
        os.environ.get("HOLOVERSE_GENERATED_AUDIO_DIR"),
        settings.get("generated_audio_root"),
        sam.get("generated_audio_root"),
        os.environ.get("HOLOVERSE_LEGACY_GENERATED_AUDIO_DIR"),
        settings.get("generated_audio_legacy_root"),
        sam.get("generated_audio_legacy_root"),
    ):
        p = _setting_path(raw)
        if p is not None:
            candidates.append(p)
    candidates.extend([audio_library_root() / "sfx" / "generated", Path(__file__).resolve().parent / "assets" / "generated_audio"])
    return _unique_existing_first(candidates)

def sound_and_music_profile() -> dict[str, Any]:
    settings = load_settings()
    nested = settings.get("sound_and_music", {}) if isinstance(settings.get("sound_and_music", {}), dict) else {}
    return {
        "audio": audio_profile(),
        "soundtrack_enabled": bool_setting("soundtrack_enabled", bool(nested.get("soundtrack_enabled", True))),
        "soundtrack_intensity": float_setting("soundtrack_intensity", float(nested.get("soundtrack_intensity", 0.55)), 0.0, 1.0),
        "ambience_intensity": float_setting("ambience_intensity", float(nested.get("ambience_intensity", 0.45)), 0.0, 1.0),
        "variant_intensity": float_setting("soundmatrix_variant_intensity", float(nested.get("variant_intensity", 0.65)), 0.0, 1.0),
        "music_intensity": float_setting("soundmatrix_music_intensity", float(nested.get("music_intensity", 0.55)), 0.0, 1.0),
        "audio_root": audio_library_root(),
        "shared_sfx_root": shared_sfx_root(),
        "shared_sfx_roots": shared_sfx_roots(),
        "music_root": shared_music_root(),
        "music_roots": shared_music_roots(),
        "generated_audio_roots": generated_audio_roots(),
    }
