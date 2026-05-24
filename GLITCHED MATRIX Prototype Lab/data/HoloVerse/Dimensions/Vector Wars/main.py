#!/usr/bin/env python3
"""
Neon Dogfight – Infinite Wireframe City: Space + Weather Edition (Pygame) [v3.2 aim-locked controls + wheel-x yaw + camera chase hold until aligned]

Adds on top of Cosmic Edition:
- Starfield (dense stars + twinkling) and "space flight" at high altitude (reduced damping, higher ceiling)
- Procedural cloud banks (volumetric-ish glow puffs) drifting below
- Procedural tornados (wireframe helix columns) that wander and apply turbulence damage/force
- More AI ships
- Player ship variants (press V): different wireframe silhouettes + stats

Controls
- W/S: pitch down/up
- A/D: yaw left/right
- Q/E: roll left/right
- Shift: boost
- Space or Ctrl: hover/brake (strong damping; in space acts like retro-thrusters)
- Mouse1: machine guns (varies by weapon mode)
- Mouse3: homing missile (varies by weapon mode)
- R: toggle weapon mode (also changes projectile FX + damage ranges)
- T: cycle target (ship targets)
- Tab: cycle combat mode (GROUND -> AIR -> OCEAN)
- V: cycle PLAYER ship variant
- Esc: quit

New in v3.2
- Ground plane now uses a black + green neon grid "texture" so it reads as the surface (not sky).
- Ground assault aiming: player weapons bias to a flatter, straighter firing vector in ground mode.
- Mouse yaw inversion fixed: moving mouse left yaws left (and horizontal wheel left yaws left).

- Horizontal mouse-wheel (trackpad two-finger left/right, or tilt wheel) yaws BOTH the ship aim and the camera together.
- Aim-locked steering: ship rotation is driven toward a stored aim-yaw/aim-pitch target for tighter, more precise pointing.
- Camera chase offset is held while turning; it only re-centers behind the ship once the ship is sufficiently aligned to the aim.
"""
from __future__ import annotations

import math
import random
import os
import sys
import time
import traceback
import platform
from pathlib import Path

import pygame
from pygame.math import Vector3

try:
    _HV_RUNTIME_ROOT = None
    for _hv_parent in Path(__file__).resolve().parents:
        if (_hv_parent / "holoverse_mode_runtime.py").exists():
            _HV_RUNTIME_ROOT = _hv_parent
            break
    if _HV_RUNTIME_ROOT is not None and str(_HV_RUNTIME_ROOT) not in sys.path:
        sys.path.insert(0, str(_HV_RUNTIME_ROOT))
    import holoverse_mode_runtime as hv_runtime
except Exception:
    hv_runtime = None
HOLOVERSE_EMBEDDED = bool(hv_runtime.embedded_mode()) if hv_runtime else False
HOLOVERSE_SETTINGS = hv_runtime.load_settings() if hv_runtime else {}
UNIVERSAL_SETTINGS = hv_runtime.merged_settings({}) if hv_runtime else HOLOVERSE_SETTINGS
UNIVERSAL_HUD_ENABLED = bool(hv_runtime.bool_setting("hud_enabled", True)) if hv_runtime else True
UNIVERSAL_UI_SCALE = float(hv_runtime.ui_scale(1.0)) if hv_runtime else 1.0
AUDIO_PROFILE = hv_runtime.load_audio_profile(Path(__file__).resolve().parent) if hv_runtime else {}

def holoverse_return_signal_requested():
    try:
        return bool(HOLOVERSE_EMBEDDED and hv_runtime is not None and hv_runtime.should_return_to_core())
    except Exception:
        return False

def holoverse_root_owns_music() -> bool:
    try:
        return str(os.environ.get("HOLOVERSE_ROOT_OWNS_MUSIC", "")).strip().lower() in {"1", "true", "yes", "on"}
    except Exception:
        return False


# ----------------------------
# Paths / Assets
#
# This project is often embedded/launched from other scripts (e.g., a launcher).
# In those cases, relying solely on the current working directory can break asset
# discovery. We therefore locate the project root using the same directory layout
# described in folder_list.txt (if present) and by searching for an "assets" folder.
# ----------------------------

def _read_text_any_encoding(p: str) -> str:
    for enc in ("utf-8", "utf-16", "utf-16-le", "utf-16-be", "cp1252"):
        try:
            with open(p, "r", encoding=enc) as f:
                return f.read()
        except Exception:
            continue
    return ""


def locate_project_root() -> str:
    """Best-effort project-root locator.

    Priority:
      1) A directory containing folder_list.txt
      2) A directory containing assets/sfx and assets/music
      3) Fall back to the directory of this file (or current working directory)
    """
    candidates: list[Path] = []
    try:
        candidates.append(Path(__file__).resolve().parent)
    except Exception:
        pass
    try:
        candidates.append(Path(sys.argv[0]).resolve().parent)
    except Exception:
        pass
    try:
        candidates.append(Path.cwd())
    except Exception:
        pass

    def _has_assets(p: Path) -> bool:
        try:
            return (p / "assets" / "sfx").is_dir() and (p / "assets" / "music").is_dir()
        except Exception:
            return False

    seen = set()
    for base in candidates:
        if base in seen:
            continue
        seen.add(base)
        # Search base + a few parents; enough for typical launcher layouts.
        for p in [base, *list(base.parents)[:5]]:
            try:
                if (p / "folder_list.txt").is_file():
                    return str(p)
                if _has_assets(p):
                    return str(p)

                # If the game is embedded, the code may be copied into a shared folder
                # while its assets remain in a subfolder (e.g., "Vector Wars/assets").
                # Check one directory level down for an assets tree.
                try:
                    for child in p.iterdir():
                        if child.is_dir() and _has_assets(child):
                            return str(child)
                except Exception:
                    pass
            except Exception:
                continue

    # Final fallback
    try:
        return str(Path(__file__).resolve().parent)
    except Exception:
        return os.getcwd()


ROOT_DIR = locate_project_root()
ASSETS_DIR = os.path.join(ROOT_DIR, "assets")
SFX_DIR = os.path.join(ASSETS_DIR, "sfx")
MUSIC_DIR = os.path.join(ASSETS_DIR, "music")
SHARED_SFX_DIR = os.environ.get("HOLOVERSE_SHARED_SFX_DIR") or os.environ.get("MATRIX_SHARED_SFX_DIR") or os.path.join(os.path.dirname(ROOT_DIR), "assets", "shared_sfx")


def _write_audio_log(msg: str):
    try:
        os.makedirs(os.path.join(ROOT_DIR, "crash_reports"), exist_ok=True)
        fn = os.path.join(ROOT_DIR, "crash_reports", "audio_log.txt")
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(fn, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] {msg}\n")
    except Exception:
        pass


def ensure_audio_folders():
    """Create audio folders so you can drop in any mp3/wav/ogg files."""
    try:
        paths = [
            os.path.join(SFX_DIR, 'weapons', 'lasers'),
            os.path.join(SFX_DIR, 'weapons', 'beams'),
            os.path.join(SFX_DIR, 'weapons', 'guns'),
            os.path.join(SFX_DIR, 'weapons', 'missiles'),
            os.path.join(SFX_DIR, 'damage', 'hit'),
            os.path.join(SFX_DIR, 'damage', 'destroy'),
            os.path.join(SFX_DIR, 'explosions'),
            os.path.join(SFX_DIR, 'engines', 'idle'),
            os.path.join(SFX_DIR, 'engines', 'cruise'),
            os.path.join(SFX_DIR, 'engines', 'boost'),
            os.path.join(SFX_DIR, 'ambient', 'battle'),
            os.path.join(MUSIC_DIR, 'ambient'),
        ]
        for d in paths:
            os.makedirs(d, exist_ok=True)
        readme = os.path.join(ASSETS_DIR, 'README_SOUNDS.txt')
        if not os.path.exists(readme):
            with open(readme, 'w', encoding='utf-8') as f:
                f.write('Drop any .mp3/.wav/.ogg files into assets/sfx/* and assets/music/* folders.\n')
                f.write('Multiple files in a folder are randomized.\n')
                f.write('Non-player SFX are short-range positional. Mid-range becomes quiet echo; too far is silent.\n')
                f.write('Optional: place hit.wav in assets/sfx/ (or assets/sfx/damage/hit/) to override hit sounds.\n')
    except Exception:
        return


class AudioSystem:
    """Positional SFX with near-range direct sound, far echo, and hard cutoff."""
    def __init__(self, seed=12345):
        self.enabled = False
        self.last_error = ""
        self.bank = {}            # category -> [paths]
        self.cache = {}           # path -> Sound
        self.order = []           # LRU
        self.cache_max = 96
        self.load_failures = {}   # path -> error str
        self.rng = random.Random(int(seed) & 0xFFFFFFFF)
        self.sfx_gain = hv_runtime.sfx_bus_gain("sfx", 1.0) if hv_runtime else 1.0
        self.music_gain = hv_runtime.music_bus_gain(hv_runtime.profile_music_volume(0.22, profile=AUDIO_PROFILE), bus="music") if hv_runtime else 0.08
        self.listener = Vector3(0,0,0)
        self.last_scan_t = -999.0
        self.last_play = {}       # key -> time
        self.pending = []         # (t_fire, path, l, r)
        self.hit_override = None
        self.music_paths = []
        self.current_music_path = ""
        self.next_music_rotate_t = 0.0
        self.music_rotation_seconds = hv_runtime.profile_music_rotation_seconds(60.0, profile=AUDIO_PROFILE) if hv_runtime else 60.0
        self._missing_logged = set()  # categories logged as missing (avoid spam)

        # Category aliases allow your assets folder to use simpler names.
        # Example: drop laser shots into assets/sfx/lasers/ (instead of weapons/lasers)
        # and the game will still find them.
        self._category_aliases = {
            # Weapons
            'weapons/guns': ['weapons/guns', 'guns', 'weapon/guns', 'weapons/gun', 'shooting', 'shoot', 'machine_guns', 'mg'],
            'weapons/lasers': ['weapons/lasers', 'lasers', 'weapon/lasers', 'weapons/laser', 'laser', 'laser_shots', 'pew'],
            'weapons/beams': ['weapons/beams', 'beams', 'weapon/beams', 'weapons/beam', 'beam', 'energy_beams'],
            'weapons/missiles': [
                'weapons/missiles', 'missiles', 'weapon/missiles', 'weapons/missile',
                'rockets', 'rocket', 'missile', 'missile_shot', 'rocket_shot',
                'homing', 'torpedo'
            ],
            # Damage / explosions
            'damage/hit': ['damage/hit', 'hit', 'hits', 'damage', 'damage_hits', 'impacts', 'impact'],
            'damage/destroy': [
                'damage/destroy', 'destroy', 'destroyed',
                'explosions', 'explosion', 'boom', 'booms',
                'blow', 'blowing_up', 'blowup',
                'explode', 'exploded',
                'death', 'kill',
                'destroy_sfx', 'damage_destroy'
            ],
            # Ambient
            'ambient/battle': ['ambient/battle', 'battle', 'ambient', 'battle_ambient'],
        }

        try:
            # If the launcher already initialized the mixer, don't re-init.
            if pygame.mixer.get_init() is None:
                pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
            pygame.mixer.set_num_channels(32)
            self.enabled = True
        except Exception as e:
            self.last_error = f"mixer init failed: {e!r}"
            _write_audio_log(self.last_error)
            self.enabled = False
            return

        self.refresh(force=True)
        try:
            sfx_n = sum(len(v) for v in self.bank.values())
            mus_n = len(self.music_paths or [])
            _write_audio_log(f"Audio enabled. root={ROOT_DIR} sfx_files={sfx_n} music_files={mus_n}")
        except Exception:
            pass
        self._start_music()

    def refresh(self, force=False):
        if not self.enabled:
            return
        # NOTE: Some pygame/SDL_mixer builds cannot decode MP3 for Sound() reliably.
        # We still scan .mp3, but prefer .wav/.ogg for short SFX when both exist.
        exts = ('.wav', '.ogg', '.mp3')
        # SFX bank
        self.bank.clear()
        try:
            for root, _, files in os.walk(SFX_DIR):
                rel = os.path.relpath(root, SFX_DIR)
                if rel == '.':
                    continue
                paths = [os.path.join(root, fn) for fn in files if fn.lower().endswith(exts)]
                if paths:
                    self.bank[rel.replace('\\\\','/').replace('\\','/')] = sorted(paths)
        except Exception:
            pass

        # Pass 21: shared HoloVerse SFX bank from SoundMatrix / Vector Wars variants.
        try:
            if os.path.isdir(SHARED_SFX_DIR):
                for root, _, files in os.walk(SHARED_SFX_DIR):
                    rel = os.path.relpath(root, SHARED_SFX_DIR)
                    if rel == '.':
                        continue
                    paths = [os.path.join(root, fn) for fn in files if fn.lower().endswith(exts)]
                    if paths:
                        key = rel.replace('\\', '/').replace('\\', '/')
                        existing = self.bank.get(key, [])
                        self.bank[key] = sorted(set(existing + paths))
        except Exception:
            pass

        # hit.wav override (assets/sfx/hit.wav OR assets/sfx/damage/hit/hit.wav)
        cand = []
        for ext in ('.wav', '.ogg', '.mp3'):
            cand.append(os.path.join(SFX_DIR, f'hit{ext}'))
            cand.append(os.path.join(SFX_DIR, 'damage', 'hit', f'hit{ext}'))
        self.hit_override = next((p for p in cand if os.path.exists(p)), None)

        # Music ambient
        self.music_paths = []
        try:
            amb = os.path.join(MUSIC_DIR, 'ambient')
            if os.path.isdir(amb):
                for fn in os.listdir(amb):
                    if fn.lower().endswith(exts):
                        self.music_paths.append(os.path.join(amb, fn))
        except Exception:
            pass

        # Pass 21: profile soundtrack loop from the hub music library.
        try:
            if hv_runtime and hv_runtime.soundtrack_enabled(True):
                for profile_music in hv_runtime.profile_music_paths(profile=AUDIO_PROFILE):
                    if profile_music and profile_music.exists():
                        self.music_paths.insert(0, os.fspath(profile_music))
        except Exception:
            pass

    def maybe_rescan(self, t_now: float):
        if not self.enabled:
            return
        if self.music_paths and float(t_now) >= float(getattr(self, "next_music_rotate_t", 0.0) or 0.0):
            self._start_music(rotate=True)
        if (t_now - self.last_scan_t) >= 8.0:
            self.last_scan_t = float(t_now)
            self.refresh()

    def set_listener(self, pos: Vector3):
        self.listener.x, self.listener.y, self.listener.z = float(pos.x), float(pos.y), float(pos.z)

    def _pick(self, category: str):
        # Resolve category through aliases.
        key = (category or '').replace('\\', '/').strip('/')
        candidates = self._category_aliases.get(key, [key])
        files = None
        used_key = None
        for k in candidates:
            k2 = (k or '').replace('\\', '/').strip('/')
            if k2 in self.bank:
                files = self.bank.get(k2)
                used_key = k2
                break
        if not files:
            # Log missing categories once so you can spot folder-name mismatches quickly.
            if key and key not in self._missing_logged:
                self._missing_logged.add(key)
                try:
                    sample = ', '.join(sorted(list(self.bank.keys()))[:25])
                except Exception:
                    sample = ''
                _write_audio_log(f"Missing SFX category '{key}'. Looked for {candidates}. Available (sample): {sample}")
            return None
        # Prefer non-mp3 (wav/ogg) when present, because mp3 support for Sound()
        # varies by platform build.
        non_mp3 = [p for p in files if p and (not str(p).lower().endswith('.mp3'))]
        pick_from = non_mp3 if non_mp3 else files
        # If we resolved through an alias, randomize within that folder.
        return self.rng.choice(pick_from)

    def _decode_mp3_to_sound(self, path: str):
        """Best-effort MP3 -> Sound() fallback.

        Some Windows/SDL_mixer builds cannot decode MP3 for pygame.mixer.Sound(path).
        If pydub+ffmpeg (or another backend) is available, we decode MP3 to raw PCM
        matching the mixer format (44.1kHz, 16-bit, stereo) and build a Sound from a buffer.

        Returns: (Sound|None, error_str).
        """
        try:
            from pydub import AudioSegment
        except Exception as e:
            return None, f'pydub import failed: {e!r}'
        try:
            seg = AudioSegment.from_file(path)
            # Guardrail: very long MP3s can be memory-heavy if decoded to raw PCM.
            if getattr(seg, 'duration_seconds', 0.0) and seg.duration_seconds > 18.0:
                return None, f'mp3 too long for SFX decode ({seg.duration_seconds:.1f}s); use assets/music instead'
            seg = seg.set_frame_rate(44100).set_channels(2).set_sample_width(2)
            raw = seg.raw_data
            if not raw:
                return None, 'decoded raw audio empty'
            return pygame.mixer.Sound(buffer=raw), ''
        except Exception as e:
            return None, repr(e)

    def _sound(self, path: str):
        snd = self.cache.get(path)
        if snd is not None:
            return snd
        try:
            snd = pygame.mixer.Sound(path)
        except Exception as e:
            # If MP3 decoding for Sound(path) is unavailable, try a pydub decode fallback.
            if str(path).lower().endswith('.mp3'):
                snd2, err2 = self._decode_mp3_to_sound(path)
                if snd2 is not None:
                    snd = snd2
                else:
                    if path not in self.load_failures:
                        self.load_failures[path] = f'{e!r} | mp3_decode: {err2}'
                        _write_audio_log(f'Sound load failed: {path} -> {e!r} | mp3_decode: {err2}')
                    return None
            else:
                # Log once per failing path
                if path not in self.load_failures:
                    self.load_failures[path] = repr(e)
                    _write_audio_log(f'Sound load failed: {path} -> {e!r}')
                return None
        self.cache[path] = snd
        self.order.append(path)
        if len(self.order) > self.cache_max:
            old = self.order.pop(0)
            self.cache.pop(old, None)
        return snd

    def _gate(self, key: str, cooldown: float):
        if cooldown <= 0:
            return True
        now = time.perf_counter()
        last = self.last_play.get(key, -999.0)
        if (now - last) < cooldown:
            return False
        self.last_play[key] = now
        return True

    def _pan_vol_direct(self, pos: Vector3, base: float, near: float, max_dist: float):
        dx = float(pos.x - self.listener.x)
        dy = float(pos.y - self.listener.y)
        dz = float(pos.z - self.listener.z)
        d = math.sqrt(dx*dx + dy*dy + dz*dz)
        if d > max_dist:
            return 0.0, 0.0, d
        if d > near:
            return 0.0, 0.0, d
        t = max(0.0, 1.0 - (d / max(near, 1e-6)))
        vol = float(base) * (t * t)
        pan = clamp(dx / max(near, 1.0), -0.90, 0.90)
        l = vol * (1.0 - pan)
        r = vol * (1.0 + pan)
        return l, r, d

    def process_pending(self):
        if not self.enabled or not self.pending:
            return
        now = time.perf_counter()
        keep = []
        for t_fire, path, l, r in self.pending:
            if now >= t_fire:
                snd = self._sound(path)
                if snd is None:
                    continue
                ch = pygame.mixer.find_channel(False)
                if ch is None:
                    continue
                ch.set_volume(clamp(l,0.0,1.0), clamp(r,0.0,1.0))
                ch.play(snd)
            else:
                keep.append((t_fire, path, l, r))
        self.pending = keep

    def play_local(self, category: str, *, base: float=0.9, cooldown: float=0.02, key: str='local'):
        if not self.enabled:
            return
        if not self._gate(key, cooldown):
            return
        path = self._pick(category)
        if path is None:
            return
        snd = self._sound(path)
        if snd is None:
            return
        ch = pygame.mixer.find_channel(False)
        if ch is None:
            return
        # Local sounds are always centered and capped.
        v = clamp(base * getattr(self, "sfx_gain", 1.0), 0.0, 1.0)
        ch.set_volume(v, v)
        ch.play(snd)

    def play_positional(self, category: str, pos: Vector3, *, base: float=0.25, near: float=260.0, max_dist: float=900.0,
                        cooldown: float=0.08, key: str='pos', echo: bool=True, echo_gain: float=0.20):
        if not self.enabled:
            return
        if not self._gate(key, cooldown):
            return
        path = self._pick(category)
        if path is None:
            return
        l, r, d = self._pan_vol_direct(pos, base, near, max_dist)
        now = time.perf_counter()

        # Direct only inside near.
        if (l > 0.0) or (r > 0.0):
            snd = self._sound(path)
            if snd is None:
                return
            ch = pygame.mixer.find_channel(False)
            if ch is not None:
                ch.set_volume(clamp(l,0.0,1.0), clamp(r,0.0,1.0))
                ch.play(snd)
            return

        # Echo only in the far zone.
        if echo and (d <= max_dist):
            # Delay grows with distance; gain is small; always quieter than player sounds.
            delay = 0.10 + (d / 1100.0) * 0.28
            # Pan is softened in echo.
            dx = float(pos.x - self.listener.x)
            pan = clamp(dx / max(near, 1.0), -0.60, 0.60)
            v = clamp(base * echo_gain * (1.0 - clamp((d-near)/(max_dist-near+1e-6), 0.0, 1.0)), 0.0, 0.22)
            l2 = v * (1.0 - pan)
            r2 = v * (1.0 + pan)
            self.pending.append((now + delay, path, l2, r2))
            # Optional second tap
            if d > (near + (max_dist-near)*0.55):
                self.pending.append((now + delay + 0.12, path, l2*0.75, r2*0.75))

    def play_hit(self, pos: Vector3, *, is_player: bool, key: str='hit'):
        if not self.enabled:
            return
        # Use hit.wav override if present; otherwise use damage/hit bank.
        if self.hit_override and os.path.exists(self.hit_override):
            path = self.hit_override
            if not self._gate(key, 0.04 if is_player else 0.08):
                return
            snd = self._sound(path)
            if snd is None:
                return
            ch = pygame.mixer.find_channel(False)
            if ch is None:
                return
            if is_player:
                v = 0.92
                ch.set_volume(v, v)
            else:
                # Short range positional hit with echo.
                l, r, d = self._pan_vol_direct(pos, 0.22, 220.0, 850.0)
                if (l > 0.0) or (r > 0.0):
                    ch.set_volume(clamp(l,0.0,1.0), clamp(r,0.0,1.0))
                else:
                    # Far: echo only, no direct
                    dx = float(pos.x - self.listener.x)
                    pan = clamp(dx / 220.0, -0.60, 0.60)
                    v = 0.06
                    now = time.perf_counter()
                    self.pending.append((now + 0.16 + (d/1100.0)*0.22, path, v*(1.0-pan), v*(1.0+pan)))
                    return
            ch.play(snd)
        else:
            if is_player:
                self.play_local('damage/hit', base=0.90, cooldown=0.04, key=key)
            else:
                self.play_positional('damage/hit', pos, base=0.20, near=220.0, max_dist=850.0, cooldown=0.10, key=key, echo=True, echo_gain=0.20)

    def _start_music(self, rotate: bool = False):
        if holoverse_root_owns_music() or _env_flag("NEON_DOGFIGHT_DISABLE_MUSIC", False):
            try:
                pygame.mixer.music.stop()
            except Exception:
                pass
            self.current_music_path = ""
            self.next_music_rotate_t = time.time() + 999999.0
            return
        if not self.enabled:
            return
        if not self.music_paths:
            return
        try:
            # Very low ambient bed; never louder than gameplay.
            pygame.mixer.music.set_volume(clamp(getattr(self, "music_gain", 0.08), 0.0, 1.0))
            pool = [p for p in self.music_paths if p != getattr(self, "current_music_path", "")] or list(self.music_paths)
            chosen = self.rng.choice(pool)
            self.current_music_path = chosen
            self.next_music_rotate_t = time.time() + float(getattr(self, "music_rotation_seconds", 60.0) or 60.0)
            pygame.mixer.music.load(chosen)
            pygame.mixer.music.play(-1)
        except Exception:
            pass


AUDIO = None

def _get_cli_arg(flag: str, default=None, cast=str):
    try:
        if flag in sys.argv:
            idx = sys.argv.index(flag) + 1
            if idx < len(sys.argv):
                return cast(sys.argv[idx])
    except Exception:
        pass
    return default


def _has_cli_flag(*flags: str) -> bool:
    return any(flag in sys.argv for flag in flags)


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return bool(default)
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _select_perf_profile() -> str:
    raw = (
        _get_cli_arg("--perf", None, str)
        or _get_cli_arg("--quality", None, str)
        or os.environ.get("NEON_DOGFIGHT_PERF", "")
        or "smooth"
    )
    profile = str(raw).strip().lower()
    aliases = {
        "fast": "smooth",
        "performance": "smooth",
        "perf": "smooth",
        "medium": "balanced",
        "med": "balanced",
        "hi": "quality",
        "high": "quality",
        "ultra": "quality",
        "potato": "low",
    }
    profile = aliases.get(profile, profile)
    if profile not in {"low", "smooth", "balanced", "quality"}:
        profile = "smooth"
    return profile


def _panda3d_launch_safe_requested() -> bool:
    return (
        _has_cli_flag("--panda3d-launch", "--panda-launch", "--embedded")
        or _env_flag("PANDA3D_LAUNCHER", False)
        or _env_flag("PANDA3D_EMBEDDED", False)
        or _env_flag("NEON_DOGFIGHT_PANDA3D_SAFE", False)
    )


PERF_PROFILE = _select_perf_profile()
PANDA3D_LAUNCH_SAFE = _panda3d_launch_safe_requested()

# Explicit budgets.  The renderer stays fixed at 1920x1080 internally; the OS
# window is letterboxed/pillarboxed around that canvas.
TARGET_RESOLUTION = (1920, 1080)
TARGET_FPS = hv_runtime.fps_cap(60) if hv_runtime else 60
TARGET_FRAME_MS = 1000.0 / TARGET_FPS

# Smooth is the default because this build has three heavy modes: air city,
# foot assault, and ocean combat.  Quality can be requested with --perf quality.
PERF_CAPS = {
    "low": {
        "city_keep_radius": 2, "city_drop_radius": 4, "evict_max": 96, "evict_floor": 72,
        "traffic": 20, "ai": 7, "ufo": 2, "clouds": 42, "tornados": 2, "stars": 420,
        "warships": 4, "helis": 1, "building_draw": 260, "cloud_draw": 36,
        "bullets": 220, "missiles": 80, "debris": 620, "explosions": 56, "fires": 36,
        "ring_segments": 32, "sky_ring_segments": 36,
    },
    "smooth": {
        "city_keep_radius": 3, "city_drop_radius": 5, "evict_max": 132, "evict_floor": 104,
        "traffic": 30, "ai": 10, "ufo": 3, "clouds": 70, "tornados": 3, "stars": 760,
        "warships": 5, "helis": 2, "building_draw": 420, "cloud_draw": 58,
        "bullets": 360, "missiles": 120, "debris": 950, "explosions": 80, "fires": 52,
        "ring_segments": 40, "sky_ring_segments": 44,
    },
    "balanced": {
        "city_keep_radius": 3, "city_drop_radius": 5, "evict_max": 160, "evict_floor": 128,
        "traffic": 36, "ai": 12, "ufo": 3, "clouds": 92, "tornados": 4, "stars": 1100,
        "warships": 6, "helis": 2, "building_draw": 560, "cloud_draw": 76,
        "bullets": 460, "missiles": 150, "debris": 1250, "explosions": 96, "fires": 64,
        "ring_segments": 48, "sky_ring_segments": 54,
    },
    "quality": {
        "city_keep_radius": 4, "city_drop_radius": 6, "evict_max": 190, "evict_floor": 160,
        "traffic": 42, "ai": 14, "ufo": 4, "clouds": 120, "tornados": 5, "stars": 1800,
        "warships": 8, "helis": 3, "building_draw": 720, "cloud_draw": 110,
        "bullets": 620, "missiles": 190, "debris": 1600, "explosions": 120, "fires": 80,
        "ring_segments": 64, "sky_ring_segments": 66,
    },
}
ACTIVE_CAPS = PERF_CAPS[PERF_PROFILE]


def _cap_value(key: str, default: int) -> int:
    return int(ACTIVE_CAPS.get(key, default))


def _trim_list_in_place(seq: list, cap: int) -> None:
    cap = int(cap)
    if cap >= 0 and len(seq) > cap:
        del seq[: len(seq) - cap]


def get_panda3d_launch_command(auto_mode: str = "foot", perf: str | None = None) -> list[str]:
    """Return a subprocess command a Panda3D launcher can use safely.

    This game remains a Pygame renderer, so the safest Panda3D integration is an
    external child process rather than running both main loops in one ShowBase.
    """
    profile = perf or PERF_PROFILE or "smooth"
    script = str(Path(__file__).resolve())
    return [
        sys.executable, script,
        "--panda3d-launch",
        "--windowed",
        "--no-maximize",
        "--no-grab",
        "--perf", str(profile),
        "--auto-mode", str(auto_mode),
    ]


# ----------------------------
# Config
# ----------------------------
W, H = 1920, 1080  # fixed internal render resolution (16:9)
FPS = hv_runtime.fps_cap(60) if hv_runtime else 60
FOV_DEG = 78.0
NEAR_Z = 0.18

CITY_CHUNK = 220.0
CITY_RADIUS = 2

# Streaming / retention hysteresis (pre-generation + conservative unloading)
CITY_KEEP_RADIUS = _cap_value("city_keep_radius", 4)            # keep chunks this far around player even if not in lookahead set
CITY_DROP_RADIUS = _cap_value("city_drop_radius", 6)            # chunks beyond this are eligible for unloading (with direction test)

# Chunk geometry cache (keeps recently-unloaded chunks in memory so re-entry doesn't regenerate spikes)
CITY_EVICT_CACHE_MAX = _cap_value("evict_max", 190)      # max number of recently unloaded chunks retained in RAM
CITY_EVICT_CACHE_FLOOR = _cap_value("evict_floor", 160)    # trim down to this when over max

# Ground traffic (kept lightweight for performance)
TRAFFIC_TARGET_COUNT = _cap_value("traffic", 42)
TRAFFIC_SPAWN_RADIUS_CHUNKS = 4
TRAFFIC_KEEP_RADIUS_CHUNKS = 6
TRAFFIC_DROP_RADIUS_CHUNKS = 8
TRAFFIC_STREET_HALF_WIDTH = 14.0
TRAFFIC_SPEED_RANGE = (18.0, 34.0)
TRAFFIC_HP = 38
TRAFFIC_FIRE_RANGE = 95.0
TRAFFIC_FIRE_COOLDOWN = (0.35, 0.85)
TRAFFIC_BULLET_SPEED = 165.0
TRAFFIC_BULLET_LIFE = 1.05
TRAFFIC_BULLET_DMG = 9
TRAFFIC_ASSAULT_ENGAGE_RANGE = 360.0
TRAFFIC_ASSAULT_MISSILE_RANGE = 260.0
TRAFFIC_MISSILE_SPEED = 165.0
TRAFFIC_MISSILE_DMG = 48
TRAFFIC_MISSILE_RADIUS = 14.0
TRAFFIC_MISSILE_COOLDOWN = (2.2, 4.2)

# Giant mech (ground boss)
MECH_HP = 22000
MECH_RADIUS = 26.0           # footprint radius (roughly building-sized)
MECH_HEIGHT = 120.0          # tall enough to rival/beat most buildings
MECH_SPEED = 14.0            # slow roaming
MECH_TURN_RATE = 55.0        # deg/sec
MECH_GUN_CD = 0.11
MECH_GUN_SPEED = 310.0
MECH_GUN_DMG = (48, 92)
MECH_MISSILE_CD = 2.8
MECH_MISSILE_SPEED = 230.0
MECH_MISSILE_DMG = (220, 340)
MECH_MISSILE_RADIUS = (22.0, 38.0)
MECH_STOMP_CD = 3.6
MECH_STOMP_RADIUS = 34.0
MECH_STOMP_DMG = 520
MECH_RESPAWN_DELAY = 300.0   # seconds

CITY_LOOKAHEAD = CITY_CHUNK * (CITY_RADIUS + 1.25)  # pre-stream ahead of player
BUILDINGS_PER_CHUNK = (6, 12)


# City layout (lower density; explicit streets and lots)
CITY_LOT_GRID = 4                 # lots per chunk side (streets run between lots)
CITY_LOT_BUILD_CHANCE = 0.62      # chance a lot gets a structure
CITY_PLAZA_CHANCE = 0.14          # chance a lot is left open (parking/plaza)
CITY_PYRAMID_CHANCE = 0.08        # chance a built lot becomes a pyramid landmark
CITY_LOT_PADDING = 6.0            # empty margin inside lot so buildings do not touch street
CITY_AVENUE_HALF_WIDTH = 26.0     # keeps a main cross-avenue through each chunk clear

ATMOS_MAX_ALT = 520.0
SPACE_MAX_ALT = 3600.0
MIN_ALT = 8.0


# Flight feel / controls tuning
MOUSE_SENS_YAW = 0.22    # deg per pixel (stiffer)
MOUSE_SENS_PITCH = 0.18  # deg per pixel (stiffer)
KEY_YAW_RATE = 150.0     # deg/sec
KEY_PITCH_RATE = 120.0   # deg/sec
KEY_ROLL_RATE = 180.0    # deg/sec
SHIFT_SPEED_MULT = 1.85
SHIFT_ALIGN_BONUS = 0.55
HOVER_ALIGN_BONUS = 0.85
JUMP_COOLDOWN = 0.60
JUMP_UP_IMPULSE = 190.0
JUMP_FWD_IMPULSE = 60.0
VERT_THRUST = 150.0      # up/down thrusters when holding LALT/LCTRL
BULLET_LIFE = 1.25
MISSILE_LIFE = 7.6
MISSILE_TURN_RATE = math.radians(250.0)

PLAYER_HP_BASE = 2600
PLAYER_SHIELD_BASE = 1800

AI_COUNT = _cap_value("ai", 14)
UFO_COUNT = _cap_value("ufo", 4)
UFO_HP = 900
UFO_SHIELD = 600

BOMB_DROP_MIN = 14.0
BOMB_DROP_MAX = 26.0

# Weather
CLOUD_COUNT = _cap_value("clouds", 120)
CLOUD_RING = (220.0, 720.0)
CLOUD_ALT = (55.0, 210.0)

TORNADO_COUNT = _cap_value("tornados", 5)
TORNADO_RING = (260.0, 920.0)
TORNADO_HEIGHT = (140.0, 360.0)

# Stars
STAR_COUNT = _cap_value("stars", 1800)

# Ocean combat
OCEAN_WARSHIP_COUNT = _cap_value("warships", 8)
OCEAN_HELI_LIMIT = _cap_value("helis", 3)
OCEAN_HELI_SPAWN_RANGE = (9.0, 16.0)
OCEAN_WARSHIP_RING = (280.0, 900.0)
OCEAN_WARSHIP_HP = 720
OCEAN_HELI_HP = 240
OCEAN_TORPEDO_SPEED = 245.0
OCEAN_TORPEDO_DAMAGE = (180, 255)
OCEAN_TORPEDO_RADIUS = (18.0, 28.0)
OCEAN_PLAYER_RIDE = 6.6

# Runtime object/render budgets derived from PERF_CAPS.
BUILDING_DRAW_BUDGET = _cap_value("building_draw", 420)
CLOUD_DRAW_BUDGET = _cap_value("cloud_draw", 58)
BULLET_CAP = _cap_value("bullets", 360)
MISSILE_CAP = _cap_value("missiles", 120)
DEBRIS_CAP = _cap_value("debris", 950)
EXPLOSION_CAP = _cap_value("explosions", 80)
FIRE_CAP = _cap_value("fires", 52)
RING_SEGMENTS = _cap_value("ring_segments", 40)
SKY_RING_SEGMENTS = _cap_value("sky_ring_segments", 44)

# ----------------------------
# Utils
# ----------------------------
def clamp(x, a, b):
    return a if x < a else b if x > b else x


def is_dead(obj):
    """Best-effort 'dead' check across multiple entity types.

    Some entities use .dead, others use .alive, and others are culled when
    hp/health reaches 0. This helper prevents AttributeError crashes when
    missiles/AI target objects that lack a .dead flag.
    """
    if obj is None:
        return True

    # Primary convention
    if hasattr(obj, "dead"):
        try:
            return bool(getattr(obj, "dead"))
        except Exception:
            return False

    # Alternate convention
    if hasattr(obj, "alive"):
        try:
            return not bool(getattr(obj, "alive"))
        except Exception:
            pass

    # Common health attributes
    for attr in ("hp", "health", "armor", "hull", "life"):
        if hasattr(obj, attr):
            try:
                return float(getattr(obj, attr)) <= 0.0
            except Exception:
                continue

    return False

def lerp(a, b, t):
    return a + (b - a) * t

def angle_wrap_deg(a):
    return (a + 180.0) % 360.0 - 180.0

def shortest_angle_deg(a, b):
    return angle_wrap_deg(b - a)

def lerp_angle_deg(a, b, t):
    return a + shortest_angle_deg(a, b) * clamp(t, 0.0, 1.0)

def rand_neon(rng: random.Random):
    pal = [
        (0.10, 0.90, 1.00),
        (1.00, 0.25, 0.95),
        (0.20, 1.00, 0.50),
        (1.00, 0.60, 0.10),
        (0.60, 0.35, 1.00),
        (0.10, 1.00, 0.85),
        (1.00, 0.20, 0.30),
        (0.85, 1.00, 0.20),
    ]
    r, g, b = rng.choice(pal)
    r = clamp(r + rng.uniform(-0.08, 0.08), 0, 1)
    g = clamp(g + rng.uniform(-0.08, 0.08), 0, 1)
    b = clamp(b + rng.uniform(-0.08, 0.08), 0, 1)
    return (r, g, b)

def rgbf_to_rgbi(c, a=255):
    return (int(clamp(c[0], 0, 1) * 255),
            int(clamp(c[1], 0, 1) * 255),
            int(clamp(c[2], 0, 1) * 255),
            int(a))

def basis_from_ypr_deg(yaw, pitch, roll):
    y = math.radians(yaw)
    p = math.radians(pitch)
    r = math.radians(roll)

    cy, sy = math.cos(y), math.sin(y)
    cp, sp = math.cos(p), math.sin(p)
    cr, sr = math.cos(r), math.sin(r)

    fwd = Vector3(sy * cp, cy * cp, -sp)

    right = Vector3(cy, -sy, 0.0)
    if right.length_squared() < 1e-8:
        right = Vector3(1, 0, 0)

    up = right.cross(fwd)
    if up.length_squared() < 1e-8:
        up = Vector3(0, 0, 1)
    else:
        up = up.normalize()

    def rot(v):
        return (v * cr) + (fwd.cross(v) * sr) + (fwd * (fwd.dot(v) * (1 - cr)))

    right2 = rot(right)
    up2 = rot(up)

    if fwd.length_squared() > 1e-8: fwd = fwd.normalize()
    if right2.length_squared() > 1e-8: right2 = right2.normalize()
    if up2.length_squared() > 1e-8: up2 = up2.normalize()
    return fwd, right2, up2

def safe_norm(v: Vector3, fallback=Vector3(0,1,0)):
    if v.length_squared() > 1e-8:
        return v.normalize()
    return fallback.copy()



def ocean_wave_height(x: float, y: float, t: float) -> float:
    return (
        math.sin(x * 0.020 + t * 0.95) * 2.9 +
        math.cos(y * 0.017 - t * 0.72) * 2.2 +
        math.sin((x + y) * 0.010 + t * 1.35) * 1.7 +
        math.cos((x - y) * 0.014 - t * 1.05) * 1.2
    )


def ocean_wave_normal(x: float, y: float, t: float) -> Vector3:
    eps = 2.0
    hx1 = ocean_wave_height(x + eps, y, t)
    hx0 = ocean_wave_height(x - eps, y, t)
    hy1 = ocean_wave_height(x, y + eps, t)
    hy0 = ocean_wave_height(x, y - eps, t)
    n = Vector3(-(hx1 - hx0) / (2.0 * eps), -(hy1 - hy0) / (2.0 * eps), 1.0)
    return safe_norm(n, Vector3(0, 0, 1))


class OceanWarship:
    def __init__(self, wid: int, rng: random.Random, center: Vector3):
        self.wid = int(wid)
        self.dead = False
        self.hp_max = int(OCEAN_WARSHIP_HP)
        self.hp = float(self.hp_max)
        self.neon = (0.18 + rng.random()*0.10, 0.74 + rng.random()*0.20, 1.0)
        self.anchor = center.copy()
        self.pos = center.copy()
        self.orbit_r = rng.uniform(40.0, 115.0)
        self.orbit_t = rng.uniform(0.0, math.pi * 2.0)
        self.orbit_speed = rng.uniform(0.04, 0.10) * (1.0 if rng.random() < 0.5 else -1.0)
        self.yaw = rng.uniform(-180.0, 180.0)
        self.phase = rng.uniform(0.0, math.pi * 2.0)
        self.fire_cd = rng.uniform(0.8, 1.9)
        self.missile_cd = rng.uniform(4.0, 7.0)
        self.length = rng.uniform(16.0, 24.0)
        self.width = rng.uniform(4.8, 7.2)
        self.height = rng.uniform(4.2, 6.2)
        self.speed = rng.uniform(18.0, 28.0)

    def take_damage(self, dmg: int, *_):
        self.hp -= max(0, int(dmg))
        if self.hp <= 0:
            self.hp = 0
            self.dead = True

    def update(self, dt: float, t_now: float, player, bullets, missiles, rng: random.Random):
        if self.dead:
            return
        self.orbit_t += self.orbit_speed * dt
        self.pos.x = self.anchor.x + math.cos(self.orbit_t) * self.orbit_r
        self.pos.y = self.anchor.y + math.sin(self.orbit_t) * self.orbit_r
        self.pos.z = ocean_wave_height(self.pos.x, self.pos.y, t_now) + 2.2
        tx = self.anchor.x + math.cos(self.orbit_t + 0.25) * self.orbit_r
        ty = self.anchor.y + math.sin(self.orbit_t + 0.25) * self.orbit_r
        self.yaw = math.degrees(math.atan2(tx - self.pos.x, ty - self.pos.y))
        self.fire_cd -= dt
        self.missile_cd -= dt
        to_p = player.pos - self.pos
        dist = max(1e-5, to_p.length())
        if self.fire_cd <= 0.0 and dist < 720.0:
            self.fire_cd = rng.uniform(0.8, 1.6)
            dirv = safe_norm(to_p, Vector3(0,1,0))
            right = safe_norm(Vector3(dirv.y, -dirv.x, 0.0), Vector3(1,0,0))
            for side in (-1.0, 1.0):
                origin = self.pos + right * (self.width * 0.55 * side) + Vector3(0, 0, 2.1)
                v = safe_norm(dirv + right * rng.uniform(-0.08, 0.08) + Vector3(0,0,rng.uniform(-0.02, 0.05)), dirv) * rng.uniform(185.0, 235.0)
                bullets.append(Bullet(self, origin, v, self.neon, rng.randint(16, 24), 2.6, 1.8, style_id=71))
            if AUDIO is not None:
                AUDIO.play_positional('weapons/guns', self.pos, base=0.14, near=320.0, max_dist=1300.0, cooldown=0.20, key=f'warship_guns_{self.wid}', echo=True, echo_gain=0.18)
        if self.missile_cd <= 0.0 and dist < 620.0 and rng.random() < 0.35:
            self.missile_cd = rng.uniform(4.8, 7.6)
            d = safe_norm(player.pos - self.pos, Vector3(0,1,0))
            missiles.append(Missile(self, self.pos + d * (self.length * 0.45) + Vector3(0,0,1.8), d * 170.0, player, self.neon, rng.randint(120, 180), rng.uniform(14.0, 20.0), style_id=72))


class OceanHelicopter:
    def __init__(self, hid: int, rng: random.Random, center: Vector3):
        self.hid = int(hid)
        self.dead = False
        self.hp_max = int(OCEAN_HELI_HP)
        self.hp = float(self.hp_max)
        self.neon = (1.0, 0.62 + rng.random()*0.18, 0.18 + rng.random()*0.08)
        self.center = center.copy()
        self.pos = center.copy()
        self.orbit_r = rng.uniform(140.0, 280.0)
        self.orbit_t = rng.uniform(0.0, math.pi * 2.0)
        self.orbit_speed = rng.uniform(0.28, 0.44) * (1.0 if rng.random() < 0.5 else -1.0)
        self.alt = rng.uniform(62.0, 96.0)
        self.yaw = rng.uniform(-180.0, 180.0)
        self.fire_cd = rng.uniform(1.6, 3.0)
        self.life = rng.uniform(16.0, 28.0)
        self.age = 0.0

    def take_damage(self, dmg: int, *_):
        self.hp -= max(0, int(dmg))
        if self.hp <= 0:
            self.hp = 0
            self.dead = True

    def update(self, dt: float, t_now: float, player, bullets, missiles, rng: random.Random):
        if self.dead:
            return
        self.age += dt
        if self.age > self.life:
            self.dead = True
            return
        self.orbit_t += self.orbit_speed * dt
        cx = self.center.x + math.cos(self.orbit_t) * self.orbit_r
        cy = self.center.y + math.sin(self.orbit_t) * self.orbit_r
        self.pos.x = cx
        self.pos.y = cy
        self.pos.z = ocean_wave_height(cx, cy, t_now) + self.alt + math.sin(t_now * 1.8 + self.hid) * 4.5
        look = player.pos - self.pos
        self.yaw = math.degrees(math.atan2(look.x, look.y))
        self.fire_cd -= dt
        dist = max(1e-5, look.length())
        if self.fire_cd <= 0.0 and dist < 760.0:
            self.fire_cd = rng.uniform(1.8, 3.6)
            d = safe_norm(look, Vector3(0,1,0))
            origin = self.pos + Vector3(0,0,-2.2)
            missiles.append(Missile(self, origin, d * 190.0, player, self.neon, rng.randint(90, 145), rng.uniform(12.0, 18.0), style_id=73))
            bullets.append(Bullet(self, origin, d * 260.0, self.neon, rng.randint(10, 18), 1.8, 1.6, style_id=74))
            if AUDIO is not None:
                AUDIO.play_positional('weapons/missiles', self.pos, base=0.12, near=320.0, max_dist=1250.0, cooldown=0.35, key=f'heli_fire_{self.hid}', echo=True, echo_gain=0.16)

class GroundCar:
    __slots__ = ("pos", "axis", "sign", "speed", "hp", "neon", "cooldown", "missile_cd", "turret_yaw", "shape_id", "hull_w", "hull_l", "hover_z", "rng_seed", "alive")

    def __init__(self, pos_xy, axis, sign, speed, neon, rng_seed):
        self.pos = Vector3(float(pos_xy[0]), float(pos_xy[1]), 0.0)
        self.axis = axis  # 0 = X street (moves along X), 1 = Y street (moves along Y)
        self.sign = 1 if sign >= 0 else -1
        self.speed = float(speed)
        self.hp = int(TRAFFIC_HP)
        self.neon = neon
        self.cooldown = 0.25
        self.missile_cd = 1.25
        self.rng_seed = int(rng_seed) & 0xFFFFFFFF
        rng = random.Random(self.rng_seed ^ 0xC0FFEE)
        self.shape_id = rng.randint(0, 5)
        self.hull_w = rng.uniform(1.2, 2.4)
        self.hull_l = rng.uniform(2.2, 4.0)
        self.hover_z = rng.uniform(0.55, 1.25)
        self.turret_yaw = rng.uniform(-180.0, 180.0)
        self.alive = True

    def _rng(self):
        return random.Random(self.rng_seed)

    def update(self, dt, city: City):
        if not self.alive:
            return False

        # Move along street axis
        v = self.speed * self.sign
        if self.axis == 0:
            self.pos.x += v * dt
        else:
            self.pos.y += v * dt

        # Occasional direction changes near chunk-center streets (intersections)
        # Intersections are near x = n*CITY_CHUNK and y = m*CITY_CHUNK.
        rng = self._rng()
        # advance seed deterministically so behavior is stable but not frozen
        self.rng_seed = (self.rng_seed * 1664525 + 1013904223) & 0xFFFFFFFF

        # If we're near an intersection, sometimes turn onto the perpendicular street.
        near_x = abs((self.pos.x / CITY_CHUNK) - round(self.pos.x / CITY_CHUNK)) < 0.03
        near_y = abs((self.pos.y / CITY_CHUNK) - round(self.pos.y / CITY_CHUNK)) < 0.03
        if near_x and near_y and rng.random() < 0.15:
            self.axis = 1 - self.axis
            if rng.random() < 0.5:
                self.sign *= -1
            # mild speed jitter
            self.speed = clamp(self.speed + rng.uniform(-3.0, 3.0), TRAFFIC_SPEED_RANGE[0], TRAFFIC_SPEED_RANGE[1])

        return True

    def take_damage(self, dmg):
        self.hp -= int(dmg)
        if self.hp <= 0:
            self.alive = False
        return self.alive


class TrafficManager:
    def __init__(self, seed=2025):
        self.seed = seed
        self.cars = []
        self._respawn_accum = 0.0

    def _street_spawn_point(self, rng: random.Random, pcx, pcy):
        # Choose a chunk near the player and spawn on its main streets (cross through chunk origin).
        cx = pcx + rng.randint(-TRAFFIC_SPAWN_RADIUS_CHUNKS, TRAFFIC_SPAWN_RADIUS_CHUNKS)
        cy = pcy + rng.randint(-TRAFFIC_SPAWN_RADIUS_CHUNKS, TRAFFIC_SPAWN_RADIUS_CHUNKS)
        base_x = cx * CITY_CHUNK
        base_y = cy * CITY_CHUNK

        # Pick a street: x-street at y=base_y OR y-street at x=base_x, with slight lateral offset.
        axis = 0 if rng.random() < 0.5 else 1
        off = rng.uniform(-TRAFFIC_STREET_HALF_WIDTH, TRAFFIC_STREET_HALF_WIDTH)
        if axis == 0:
            # move along X, keep y on street
            x = base_x + rng.uniform(-CITY_CHUNK*0.45, CITY_CHUNK*0.45)
            y = base_y + off
        else:
            x = base_x + off
            y = base_y + rng.uniform(-CITY_CHUNK*0.45, CITY_CHUNK*0.45)

        sign = 1 if rng.random() < 0.5 else -1
        speed = rng.uniform(*TRAFFIC_SPEED_RANGE)
        neon = rand_neon(rng)
        rid = rng.getrandbits(32)
        return (x, y), axis, sign, speed, neon, rid

    def ensure_density(self, player_pos: Vector3):
        pcx = int(math.floor(player_pos.x / CITY_CHUNK))
        pcy = int(math.floor(player_pos.y / CITY_CHUNK))

        # Cull only when far and effectively behind the player (handled in update with velocity).
        # Here we just keep list length bounded.
        if len(self.cars) > TRAFFIC_TARGET_COUNT * 2:
            self.cars = [c for c in self.cars if c.alive][:TRAFFIC_TARGET_COUNT*2]

        # Spawn up to target
        if len(self.cars) < TRAFFIC_TARGET_COUNT:
            rng = random.Random((pcx * 9176 + pcy * 31337 + self.seed) & 0xFFFFFFFF)
            add = TRAFFIC_TARGET_COUNT - len(self.cars)
            for _ in range(add):
                pos_xy, axis, sign, speed, neon, rid = self._street_spawn_point(rng, pcx, pcy)
                self.cars.append(GroundCar(pos_xy, axis, sign, speed, neon, rid))

    def update(self, dt, city: City, player, player_vel: Vector3, bullets, missiles, explosions, debris, ground_assault: bool=False, mech=None):
        # Maintain target density with modest respawn pacing to avoid bursts
        self._respawn_accum += dt
        if self._respawn_accum >= 0.25:
            self._respawn_accum = 0.0
            self.cars = [c for c in self.cars if c.alive]
            self.ensure_density(player.pos)

        # Conservative cull: only if far AND moving away AND well outside keep radius
        vx, vy = player_vel.x, player_vel.y
        sp2 = vx*vx + vy*vy
        keep_dist = (TRAFFIC_KEEP_RADIUS_CHUNKS * CITY_CHUNK)
        keep2 = keep_dist * keep_dist
        drop_dist = (TRAFFIC_DROP_RADIUS_CHUNKS * CITY_CHUNK)
        drop2 = drop_dist * drop_dist

        px, py = player.pos.x, player.pos.y
        new_cars = []
        for c in self.cars:
            if not c.alive:
                continue

            dx = c.pos.x - px
            dy = c.pos.y - py
            d2 = dx*dx + dy*dy

            # cull only when far and moving away and outside keep radius
            if d2 > drop2 and sp2 > 0.25 and (vx*dx + vy*dy) < 0.0:
                continue

            # update motion (no allocations)
            c.update(dt, city)

            # Combat:
            # - In air mode: cars shoot each other (background chaos)
            # - In ground assault: cars prioritize the player and can launch missiles
            c.cooldown -= dt
            c.missile_cd -= dt

            # Turret tracking (yaw only; vehicles hover level)
            # Desired yaw points toward the chosen target.
            target_pos = None
            target_obj = None
            if ground_assault:
                # Engage nearest of player vs giant mech (if present) when close enough
                best_obj = None
                best_d2 = (TRAFFIC_ASSAULT_ENGAGE_RANGE * TRAFFIC_ASSAULT_ENGAGE_RANGE)
                if d2 < best_d2:
                    best_obj = player
                    best_d2 = d2
                if mech is not None and (not getattr(mech, "dead", True)):
                    mx = mech.pos.x - c.pos.x
                    my = mech.pos.y - c.pos.y
                    md2 = mx*mx + my*my
                    if md2 < best_d2:
                        best_obj = mech
                        best_d2 = md2
                target_obj = best_obj
                target_pos = target_obj.pos if target_obj is not None else None
            else:
                # Find a nearby target car (cheap O(n))
                best = None
                best2 = (TRAFFIC_FIRE_RANGE * TRAFFIC_FIRE_RANGE)
                for o in self.cars:
                    if o is c or not o.alive:
                        continue
                    ox = o.pos.x - c.pos.x
                    oy = o.pos.y - c.pos.y
                    dd = ox*ox + oy*oy
                    if dd < best2:
                        best2 = dd
                        best = o
                if best is not None:
                    target_obj = best
                    target_pos = best.pos

                # Opportunistically pepper the mech if it is in range
                if mech is not None and (not getattr(mech, "dead", True)):
                    mx = mech.pos.x - c.pos.x
                    my = mech.pos.y - c.pos.y
                    md2 = mx*mx + my*my
                    if md2 < best2:
                        target_obj = mech
                        target_pos = mech.pos
                        best2 = md2

            if target_pos is not None:
                dx2 = target_pos.x - c.pos.x
                dy2 = target_pos.y - c.pos.y
                desired_yaw = math.degrees(math.atan2(dy2, dx2))
                # Smooth turret yaw toward desired
                c.turret_yaw = lerp_angle_deg(c.turret_yaw, desired_yaw, 1.0 - math.exp(-dt / 0.10))

                # Fire bullets from turret in both modes
                if c.cooldown <= 0.0:
                    L = math.sqrt(dx2*dx2 + dy2*dy2) + 1e-6
                    vx_b = (dx2 / L) * TRAFFIC_BULLET_SPEED
                    vy_b = (dy2 / L) * TRAFFIC_BULLET_SPEED
                    bpos = Vector3(c.pos.x, c.pos.y, c.hover_z + 0.65)
                    bvel = Vector3(vx_b, vy_b, 0.0)
                    bullets.append(Bullet(c, bpos, bvel, c.neon, TRAFFIC_BULLET_DMG, TRAFFIC_BULLET_LIFE, 0.7, style_id=2))
                    rng = random.Random(c.rng_seed ^ 0xA5A5A5A5)
                    c.cooldown = rng.uniform(*TRAFFIC_FIRE_COOLDOWN)

                # Missiles (ground assault only): slower cadence, higher threat
                if ground_assault and c.missile_cd <= 0.0 and target_obj is not None:
                    td2 = dx2*dx2 + dy2*dy2
                    if td2 < (TRAFFIC_ASSAULT_MISSILE_RANGE * TRAFFIC_ASSAULT_MISSILE_RANGE):
                        L = math.sqrt(dx2*dx2 + dy2*dy2) + 1e-6
                        spd = TRAFFIC_MISSILE_SPEED
                        mvel = Vector3((dx2 / L) * spd, (dy2 / L) * spd, 0.0)
                        mpos = Vector3(c.pos.x, c.pos.y, c.hover_z + 0.85)
                        missiles.append(Missile(c, mpos, mvel, target_obj, c.neon, TRAFFIC_MISSILE_DMG, TRAFFIC_MISSILE_RADIUS, style_id=4))
                        rng = random.Random(c.rng_seed ^ 0x55AA1234)
                        c.missile_cd = rng.uniform(*TRAFFIC_MISSILE_COOLDOWN)

            else:
                # no target: idle cooldown
                if c.cooldown <= 0.0:
                    c.cooldown = 0.25

            new_cars.append(c)

        self.cars = new_cars

    def draw(self, solid, glow, cam: Camera, cam_fwd: Vector3, cam_right: Vector3, cam_up: Vector3, city_alpha):
        # Hover-vehicle silhouettes: solid black fill + neon wireframe outlines
        a1 = int(90 * (city_alpha/255))
        a2 = int(190 * (city_alpha/255))

        for c in self.cars:
            # Heading based on lane axis/sign (keeps traffic coherent)
            if c.axis == 0:
                fwd = Vector3(1.0*c.sign, 0.0, 0.0)
                right = Vector3(0.0, 1.0, 0.0)
            else:
                fwd = Vector3(0.0, 1.0*c.sign, 0.0)
                right = Vector3(1.0, 0.0, 0.0)

            z = float(c.hover_z)

            # Hull polygon in local space (right/fwd plane)
            hw = float(c.hull_w)
            hl = float(c.hull_l)

            # A small library of hull shapes (wireframe-friendly)
            sid = int(c.shape_id) % 6
            if sid == 0:
                # diamond
                local = [(0.0, -hl), (hw, 0.0), (0.0, hl), (-hw, 0.0)]
            elif sid == 1:
                # arrowhead
                local = [(0.0, -hl), (hw*0.9, -hl*0.25), (hw*0.45, hl), (-hw*0.45, hl), (-hw*0.9, -hl*0.25)]
            elif sid == 2:
                # trapezoid
                local = [(-hw*0.75, -hl), (hw*0.75, -hl), (hw, hl*0.75), (-hw, hl*0.75)]
            elif sid == 3:
                # long wedge
                local = [(0.0, -hl), (hw, -hl*0.15), (hw*0.55, hl), (-hw*0.55, hl), (-hw, -hl*0.15)]
            elif sid == 4:
                # hex
                local = [(-hw*0.6, -hl), (hw*0.6, -hl), (hw, -hl*0.2), (hw*0.6, hl), (-hw*0.6, hl), (-hw, -hl*0.2)]
            else:
                # boxy
                local = [(-hw, -hl), (hw, -hl), (hw, hl), (-hw, hl)]

            hull_world = [c.pos + (right * lx) + (fwd * ly) + Vector3(0, 0, z) for (lx, ly) in local]
            proj = [cam.project(p, cam_fwd, cam_right, cam_up) for p in hull_world]
            if any(p is None for p in proj):
                continue
            pts = [(p[0], p[1]) for p in proj]

            # Transparent neon-tinted body fill (no opaque black discs)
            fill_col = rgbf_to_rgbi(c.neon, 18)
            pygame.draw.polygon(solid, fill_col, pts, 0)

            # Neon outline
            neon1 = rgbf_to_rgbi(c.neon, a1)
            neon2 = rgbf_to_rgbi(c.neon, a2)
            for i in range(len(pts)):
                a = pts[i]
                b = pts[(i+1) % len(pts)]
                draw_additive_line(glow, a, b, neon1, width=1)
                draw_additive_line(glow, a, b, neon2, width=2)

            # Turret (rotates independently)
            ty = math.radians(float(c.turret_yaw))
            t_fwd = Vector3(math.cos(ty), math.sin(ty), 0.0)
            t_right = Vector3(-t_fwd.y, t_fwd.x, 0.0)

            # turret base + barrel
            tbase = [
                ( t_right * 0.55) + (t_fwd * -0.35),
                ( t_right * -0.55) + (t_fwd * -0.35),
                ( t_right * -0.45) + (t_fwd * 0.35),
                ( t_right * 0.45) + (t_fwd * 0.35),
            ]
            barrel = [
                (t_right * 0.18) + (t_fwd * 0.35),
                (t_right * -0.18) + (t_fwd * 0.35),
                (t_right * -0.10) + (t_fwd * 1.10),
                (t_right * 0.10) + (t_fwd * 1.10),
            ]
            tbase_w = [c.pos + v + Vector3(0,0,z+0.18) for v in tbase]
            barrel_w = [c.pos + v + Vector3(0,0,z+0.20) for v in barrel]

            p_base = [cam.project(p, cam_fwd, cam_right, cam_up) for p in tbase_w]
            p_bar  = [cam.project(p, cam_fwd, cam_right, cam_up) for p in barrel_w]
            if not any(p is None for p in p_base):
                tb = [(p[0], p[1]) for p in p_base]
                fill_col = rgbf_to_rgbi(c.neon, 14)
                pygame.draw.polygon(solid, fill_col, tb, 0)
                for i in range(len(tb)):
                    draw_additive_line(glow, tb[i], tb[(i+1)%len(tb)], neon1, width=1)
            if not any(p is None for p in p_bar):
                bb = [(p[0], p[1]) for p in p_bar]
                fill_col = rgbf_to_rgbi(c.neon, 12)
                pygame.draw.polygon(solid, fill_col, bb, 0)
                for i in range(len(bb)):
                    draw_additive_line(glow, bb[i], bb[(i+1)%len(bb)], neon2, width=1)


# ----------------------------
# Giant mech (ground boss)
# ----------------------------
class GiantMech:
    """A building-sized roaming boss unit.

    Supports multiple variants via `kind`:
      - transformer (humanoid)
      - brute (chunkier humanoid)
      - spider (wider stance)
      - titan (very large humanoid)
      - godzilla (kaiju) : prefers heavy beam cannons
    """
    def __init__(self, rng: random.Random, pos_xy=(0.0, 0.0), kind: str = "transformer", scale: float = 1.0):
        self.kind = str(kind or "transformer").lower()
        self.scale = float(scale)

        # Variant defaults (kept lightweight: no heavy meshes; just proportions + behavior)
        if self.kind == "godzilla":
            self.scale = max(self.scale, 1.75)
            self.neon = (1.00, rng.uniform(0.10, 0.25), rng.uniform(0.05, 0.15))  # hot red/orange
        elif self.kind == "titan":
            self.scale = max(self.scale, 1.45)
            self.neon = rand_neon(rng)
        elif self.kind == "brute":
            self.scale = max(self.scale, 1.30)
            self.neon = rand_neon(rng)
        elif self.kind == "spider":
            self.scale = max(self.scale, 1.18)
            self.neon = rand_neon(rng)
        else:
            self.scale = max(self.scale, 1.10)
            self.neon = rand_neon(rng)

        self.hp_max = float(MECH_HP) * (1.35 if self.kind == "godzilla" else 1.0)
        self.hp = float(self.hp_max)
        self.dead = False

        self.pos = Vector3(float(pos_xy[0]), float(pos_xy[1]), 0.0)
        self.yaw = rng.uniform(-180.0, 180.0)

        # Scaled collision footprint / height
        self.radius = float(MECH_RADIUS) * self.scale
        self.h = float(MECH_HEIGHT) * self.scale

        # Movement tuning
        self.speed_mul = 0.78 if self.kind == "godzilla" else (0.88 if self.kind in ("titan", "brute") else 1.0)

        self._wander_t = 0.0
        self._wander_dir = Vector3(1.0, 0.0, 0.0)
        self.gun_cd = 0.0
        self.missile_cd = 0.0
        self.stomp_cd = 0.0
        self.respawn_t = 0.0

        # Beam mode (godzilla)
        self.beam_cd = 0.0
        self.beam_t = 0.0

    def take_damage(self, dmg: int, t_now: float = 0.0):
        if self.dead:
            return
        self.hp -= float(max(0, int(dmg)))
        if self.hp <= 0.0:
            self.hp = 0.0
            self.dead = True
            self.respawn_t = float(t_now) + float(MECH_RESPAWN_DELAY)

    def alive(self) -> bool:
        return (not self.dead) and (self.hp > 0.0)

    def hit_test(self, p: Vector3, pad_xy=2.0, pad_z=6.0) -> bool:
        # Cylinder-ish test (good enough): XY radius + height window
        dx = p.x - self.pos.x
        dy = p.y - self.pos.y
        rr = (self.radius + float(pad_xy))
        if (dx*dx + dy*dy) > (rr * rr):
            return False
        return (-float(pad_z)) <= p.z <= (self.h + float(pad_z))

    def _pick_target(self, targets):
        # targets: iterable of objects with .pos and optional .dead
        best = None
        best2 = 1e18
        px, py = self.pos.x, self.pos.y
        for t in targets:
            if t is None:
                continue
            if getattr(t, "dead", False):
                continue
            tp = getattr(t, "pos", None)
            if tp is None:
                continue
            dx = tp.x - px
            dy = tp.y - py
            d2 = dx*dx + dy*dy
            if d2 < best2:
                best2 = d2
                best = t
        return best, math.sqrt(best2) if best is not None else 1e9

    def update(self, dt: float, t_now: float, city: 'City', targets, bullets, missiles, explosions, rng: random.Random, anchor: Vector3=None):
        # Respawn handling
        if self.dead:
            if t_now >= self.respawn_t:
                self.dead = False
                self.hp = self.hp_max
                # respawn near the player anchor so it stays relevant
                if anchor is not None:
                    self.pos.x = float(anchor.x + rng.uniform(-220.0, 220.0))
                    self.pos.y = float(anchor.y + rng.uniform(-220.0, 220.0))
                    self.pos.z = 0.0
                    self.yaw = rng.uniform(-180.0, 180.0)
            else:
                return

        # Wander: slow roaming with gentle turns
        self._wander_t -= dt
        if self._wander_t <= 0.0:
            self._wander_t = rng.uniform(2.2, 4.8)
            # pick a new heading close to current yaw
            new_yaw = self.yaw + rng.uniform(-60.0, 60.0)
            r = math.radians(new_yaw)
            self._wander_dir = Vector3(math.cos(r), math.sin(r), 0.0)

        desired_yaw = math.degrees(math.atan2(self._wander_dir.y, self._wander_dir.x))
        self.yaw = lerp_angle_deg(self.yaw, desired_yaw, clamp(MECH_TURN_RATE * dt / 180.0, 0.0, 1.0))

        fwd = Vector3(math.cos(math.radians(self.yaw)), math.sin(math.radians(self.yaw)), 0.0)
        spd = float(MECH_SPEED) * float(self.speed_mul)
        self.pos.x += fwd.x * spd * dt
        self.pos.y += fwd.y * spd * dt

        # Combat cooldowns
        self.gun_cd = max(0.0, self.gun_cd - dt)
        self.missile_cd = max(0.0, self.missile_cd - dt)
        self.stomp_cd = max(0.0, self.stomp_cd - dt)
        self.beam_cd = max(0.0, self.beam_cd - dt)
        self.beam_t = max(0.0, self.beam_t - dt)

        tgt, dist = self._pick_target(targets)
        if tgt is None:
            return

        tp = tgt.pos
        dx = tp.x - self.pos.x
        dy = tp.y - self.pos.y
        dz = (tp.z - (self.h * 0.62))
        L = math.sqrt(dx*dx + dy*dy + dz*dz) + 1e-6
        dir3 = Vector3(dx / L, dy / L, dz / L)

        # Cannon position (upper torso)
        cannon = self.pos + Vector3(0.0, 0.0, self.h * 0.62)

        # GODZILLA: beam cannons (prefer beams, fewer missiles)
        if self.kind == "godzilla" and dist < 1400.0:
            # occasionally start a beam channel
            if self.beam_t <= 0.0 and self.beam_cd <= 0.0 and rng.random() < 0.22:
                self.beam_t = rng.uniform(0.35, 0.70)     # channel duration
                self.beam_cd = rng.uniform(1.40, 2.20)    # cooldown between channels

            if self.beam_t > 0.0:
                yaw = math.radians(self.yaw)
                fwd2 = Vector3(math.cos(yaw), math.sin(yaw), 0.0)
                up = Vector3(0, 0, 1)
                right2 = Vector3(-fwd2.y, fwd2.x, 0.0)

                aim = safe_norm(Vector3(tp.x - cannon.x, tp.y - cannon.y, (tp.z + 18.0) - cannon.z), fwd2)

                # Emitters: center + two shoulders
                emitters = [
                    cannon + aim * (self.radius * 0.35),
                    cannon + right2*(self.radius*0.28) + aim * (self.radius * 0.30),
                    cannon - right2*(self.radius*0.28) + aim * (self.radius * 0.30),
                ]

                # Fire multiple fast, thick shots to simulate a continuous beam.
                for origin in emitters:
                    for _ in range(3):
                        j = rng.uniform(-0.015, 0.015)
                        jj = rng.uniform(-0.015, 0.015)
                        d = safe_norm(aim + right2*j + up*jj, aim)
                        v = d * 2400.0
                        bullets.append(Bullet(self, origin, v, self.neon,
                                              dmg=rng.randint(95, 140),
                                              life=0.22,
                                              size=18.0,
                                              style_id=201))

        # Standard mech guns
        if self.gun_cd <= 0.0 and dist < 820.0:
            self.gun_cd = float(MECH_GUN_CD)
            spread = math.radians(1.8)
            jx = rng.uniform(-spread, spread)
            jy = rng.uniform(-spread, spread)
            up = Vector3(0, 0, 1)
            right = safe_norm(Vector3(dir3.y, -dir3.x, 0.0), Vector3(1, 0, 0))
            d = safe_norm(dir3 + right * math.sin(jx) * 0.22 + up * math.sin(jy) * 0.18, dir3)
            v = d * float(MECH_GUN_SPEED)
            dmg = rng.randint(int(MECH_GUN_DMG[0]), int(MECH_GUN_DMG[1]))
            bullets.append(Bullet(self, cannon, v, self.neon, dmg=dmg, life=1.55, size=9.0, style_id=88))

        # Missiles (disabled for godzilla; other variants use occasionally)
        if (self.kind != "godzilla") and self.missile_cd <= 0.0 and dist < 720.0 and rng.random() < 0.55:
            self.missile_cd = float(MECH_MISSILE_CD)
            ms = float(MECH_MISSILE_SPEED)
            mdmg = rng.randint(int(MECH_MISSILE_DMG[0]), int(MECH_MISSILE_DMG[1]))
            mrad = rng.uniform(float(MECH_MISSILE_RADIUS[0]), float(MECH_MISSILE_RADIUS[1]))
            mvel = dir3 * ms
            missiles.append(Missile(self, cannon + dir3 * 8.0, mvel, tgt, self.neon, mdmg, mrad, style_id=89))

        # Stomp: close-range AOE on ground targets
        if self.stomp_cd <= 0.0 and dist < (MECH_STOMP_RADIUS * 1.35 * self.scale):
            self.stomp_cd = float(MECH_STOMP_CD)
            explosions.append(Explosion(Vector3(self.pos.x, self.pos.y, 0.0), self.neon, radius=46.0 * self.scale, is_atomic=False))
            for t in targets:
                if t is None or getattr(t, "dead", False):
                    continue
                tp2 = getattr(t, "pos", None)
                if tp2 is None:
                    continue
                dx2 = tp2.x - self.pos.x
                dy2 = tp2.y - self.pos.y
                d2 = dx2*dx2 + dy2*dy2
                rr = (MECH_STOMP_RADIUS * self.scale)
                if d2 <= (rr * rr) and tp2.z <= 22.0:
                    try:
                        t.take_damage(int(MECH_STOMP_DMG), t_now)
                    except TypeError:
                        try:
                            t.take_damage(int(MECH_STOMP_DMG))
                        except Exception:
                            pass

    def draw(self, solid, glow, cam: 'Camera', cam_fwd: Vector3, cam_right: Vector3, cam_up: Vector3, city_alpha: int):
        if self.dead:
            return

        a1 = int(90 * (city_alpha/255))
        a2 = int(210 * (city_alpha/255))
        neon1 = rgbf_to_rgbi(self.neon, a1)
        neon2 = rgbf_to_rgbi(self.neon, a2)

        yaw = math.radians(self.yaw)
        fwd = Vector3(math.cos(yaw), math.sin(yaw), 0.0)
        right = Vector3(-fwd.y, fwd.x, 0.0)
        up = Vector3(0, 0, 1)

        def box(center: Vector3, hw: float, hl: float, hh: float):
            c = center
            r = right * hw
            f = fwd * hl
            u = up * hh
            b0 = c - r - f
            b1 = c + r - f
            b2 = c + r + f
            b3 = c - r + f
            t0 = b0 + u
            t1 = b1 + u
            t2 = b2 + u
            t3 = b3 + u
            return [b0, b1, b2, b3, t0, t1, t2, t3]

        def draw_box(vs, fill_alpha=10):
            pr = [cam.project(p, cam_fwd, cam_right, cam_up) for p in vs]
            if any(p is None for p in pr):
                return
            p2 = [(p[0], p[1]) for p in pr]
            top_fill = rgbf_to_rgbi(self.neon, int(fill_alpha))
            pygame.draw.polygon(solid, top_fill, [p2[4], p2[5], p2[6], p2[7]], 0)
            edges = [(0,1),(1,2),(2,3),(3,0),(4,5),(5,6),(6,7),(7,4),(0,4),(1,5),(2,6),(3,7)]
            for i,j in edges:
                draw_additive_line(glow, p2[i], p2[j], neon1, width=2)
                draw_additive_line(glow, p2[i], p2[j], neon2, width=1)

        sc = float(self.scale)
        # Base proportions by type
        if self.kind == "spider":
            leg_h = self.h * 0.38
            torso_h = self.h * 0.34
            head_h = self.h * 0.10
            leg_w = 4.2 * sc
            leg_l = 10.5 * sc
            torso_w = 12.0 * sc
            torso_l = 9.0 * sc
            head_w = 6.2 * sc
            head_l = 5.0 * sc
        elif self.kind == "brute":
            leg_h = self.h * 0.44
            torso_h = self.h * 0.36
            head_h = self.h * 0.10
            leg_w = 5.0 * sc
            leg_l = 8.5 * sc
            torso_w = 13.5 * sc
            torso_l = 10.0 * sc
            head_w = 6.8 * sc
            head_l = 5.2 * sc
        elif self.kind == "godzilla":
            leg_h = self.h * 0.30
            torso_h = self.h * 0.42
            head_h = self.h * 0.12
            leg_w = 6.2 * sc
            leg_l = 9.5 * sc
            torso_w = 14.0 * sc
            torso_l = 11.2 * sc
            head_w = 7.8 * sc
            head_l = 6.0 * sc
        else:
            leg_h = self.h * 0.45
            torso_h = self.h * 0.38
            head_h = self.h * 0.12
            leg_w = 4.2 * sc
            leg_l = 7.0 * sc
            torso_w = 10.5 * sc
            torso_l = 8.0 * sc
            head_w = 5.0 * sc
            head_l = 4.0 * sc

        leg_z = 0.0
        torso_z = leg_h

        if self.kind == "spider":
            leg_off = self.radius * 0.45
        else:
            leg_off = self.radius * 0.32

        # Legs
        draw_box(box(self.pos + right * (-leg_off) + Vector3(0, 0, leg_z), hw=leg_w, hl=leg_l, hh=leg_h), fill_alpha=8)
        draw_box(box(self.pos + right * ( leg_off) + Vector3(0, 0, leg_z), hw=leg_w, hl=leg_l, hh=leg_h), fill_alpha=8)

        # Torso
        torso_center = self.pos + Vector3(0, 0, torso_z)
        draw_box(box(torso_center, hw=torso_w, hl=torso_l, hh=torso_h), fill_alpha=10)

        # Head / neck
        head_center = self.pos + Vector3(0, 0, torso_z + torso_h)
        draw_box(box(head_center, hw=head_w, hl=head_l, hh=head_h), fill_alpha=10)

        # Arms (not for godzilla; it has shorter arms + tail + spines)
        arm_z = torso_z + torso_h * 0.62
        if self.kind != "godzilla":
            arm_hw = (5.5 * sc) if self.kind != "brute" else (6.6 * sc)
            arm_hl = (3.2 * sc) if self.kind != "brute" else (4.0 * sc)
            arm_hh = self.h * (0.10 if self.kind != "titan" else 0.12)
            draw_box(box(self.pos + right * (-15.0*sc) + Vector3(0, 0, arm_z), hw=arm_hw, hl=arm_hl, hh=arm_hh), fill_alpha=7)
            draw_box(box(self.pos + right * ( 15.0*sc) + Vector3(0, 0, arm_z), hw=arm_hw, hl=arm_hl, hh=arm_hh), fill_alpha=7)
        else:
            # Kaiju arms (shorter) + tail + dorsal spines
            arm_hw = 4.6 * sc
            arm_hl = 3.2 * sc
            arm_hh = self.h * 0.08
            draw_box(box(self.pos + right * (-12.0*sc) + Vector3(0, 0, arm_z), hw=arm_hw, hl=arm_hl, hh=arm_hh), fill_alpha=6)
            draw_box(box(self.pos + right * ( 12.0*sc) + Vector3(0, 0, arm_z), hw=arm_hw, hl=arm_hl, hh=arm_hh), fill_alpha=6)

            # Tail wire (polyline)
            tail_pts = []
            base = self.pos + Vector3(0, 0, torso_z + torso_h*0.35) - fwd * (torso_l*0.9)
            for i in range(7):
                t = i / 6.0
                p = base - fwd * (12.0*sc + 46.0*sc*t) + right * math.sin(t*3.0) * (4.0*sc) + up * (6.0*sc*(1.0-t))
                pr = cam.project(p, cam_fwd, cam_right, cam_up)
                if pr:
                    tail_pts.append((pr[0], pr[1]))
            if len(tail_pts) >= 2:
                pygame.draw.lines(glow, rgbf_to_rgbi(self.neon, a1), False, tail_pts, 4)
                pygame.draw.lines(glow, rgbf_to_rgbi(self.neon, a2), False, tail_pts, 2)

            # Dorsal spines (triangles along the back)
            spine_n = 7
            for i in range(spine_n):
                t = (i / (spine_n - 1))
                p0 = self.pos + up*(torso_z + torso_h*(0.55 + 0.25*t)) - fwd*(torso_l*0.15 + torso_l*0.95*t)
                tip = p0 + up*(16.0*sc*(0.9 - 0.4*t)) + right*(math.sin((i+1)*12.9898)*0.35*sc)
                l = p0 + right*(6.0*sc) - up*(2.0*sc)
                r = p0 - right*(6.0*sc) - up*(2.0*sc)
                pr0 = cam.project(l, cam_fwd, cam_right, cam_up)
                pr1 = cam.project(tip, cam_fwd, cam_right, cam_up)
                pr2 = cam.project(r, cam_fwd, cam_right, cam_up)
                if pr0 and pr1 and pr2:
                    pts = [(pr0[0], pr0[1]), (pr1[0], pr1[1]), (pr2[0], pr2[1])]
                    pygame.draw.polygon(solid, rgbf_to_rgbi(self.neon, 10), pts, 0)
                    pygame.draw.polygon(glow, rgbf_to_rgbi(self.neon, a2), pts, 2)

# ----------------------------
# VFX
# ----------------------------
class Trail:
    def __init__(self, color_rgb, max_pts=44):
        self.color = color_rgb
        self.max_pts = max_pts
        self.pts = []
    def add(self, p: Vector3):
        self.pts.append([p.copy(), 0.0])
        if len(self.pts) > self.max_pts:
            self.pts.pop(0)
    def update(self, dt):
        for it in self.pts:
            it[1] += dt
        self.pts = [it for it in self.pts if it[1] < 0.70]

class Explosion:
    def __init__(self, pos: Vector3, color_rgb, radius, is_atomic=False):
        self.pos = pos.copy()
        self.color = color_rgb
        self.radius = radius
        self.t = 0.0
        self.life = 1.35 if is_atomic else 0.95
        self.is_atomic = is_atomic
    def update(self, dt):
        self.t += dt
        return self.t < self.life


class Fire:
    """Lightweight persistent fire spot."""
    __slots__ = ("pos", "radius", "life", "t", "intensity")
    def __init__(self, pos: Vector3, radius: float, life: float=7.5, intensity: float=1.0):
        self.pos = pos.copy()
        self.radius = float(radius)
        self.life = float(life)
        self.t = 0.0
        self.intensity = float(intensity)
    def update(self, dt: float):
        self.t += dt
        self.intensity *= (0.987 ** (dt * 60.0))
        return (self.t < self.life) and (self.intensity > 0.10)
    def douse(self, amount: float):
        self.intensity = max(0.0, self.intensity - float(amount))

class Debris:
    def __init__(self, pos: Vector3, vel: Vector3, color_rgb, life=1.15, size=0.8):
        self.pos = pos.copy()
        self.vel = vel.copy()
        self.color = color_rgb
        self.life = life
        self.t = 0.0
        self.size = size
    def update(self, dt):
        self.t += dt
        self.vel.z -= 32.0 * dt
        self.vel *= (1.0 - clamp(0.09*dt, 0, 0.09))
        self.pos += self.vel * dt
        return self.t < self.life

class Beam:
    def __init__(self, a: Vector3, b: Vector3, color_rgb, life=0.14):
        self.a = a.copy()
        self.b = b.copy()
        self.color = color_rgb
        self.t = 0.0
        self.life = life
    def update(self, dt):
        self.t += dt
        return self.t < self.life

# ----------------------------
# Combat entities
# ----------------------------
class Bullet:
    def __init__(self, owner, pos: Vector3, vel: Vector3, color_rgb, dmg, life, size, style_id):
        self.owner = owner
        self.pos = pos.copy()
        self.vel = vel.copy()
        self.color = color_rgb
        self.dmg = int(dmg)
        self.life = float(life)
        self.size = float(size)
        self.style_id = int(style_id)
        self.t = 0.0
    def update(self, dt):
        self.t += dt
        self.pos += self.vel * dt
        return self.t < self.life

class Missile:
    def __init__(self, owner, pos: Vector3, vel: Vector3, target, color_rgb, dmg, radius, style_id):
        self.owner = owner
        self.pos = pos.copy()
        self.vel = vel.copy()
        self.target = target
        self.color = color_rgb
        self.dmg = int(dmg)
        self.radius = float(radius)
        self.style_id = int(style_id)
        self.t = 0.0
        self.life = MISSILE_LIFE
    def update(self, dt):
        self.t += dt
        if self.target and (not is_dead(self.target)):
            desired = (self.target.pos - self.pos)
            if desired.length_squared() > 1e-6:
                desired = desired.normalize()
                cur = self.vel.normalize() if self.vel.length_squared() > 1e-6 else Vector3(0,1,0)
                dot = clamp(cur.dot(desired), -1.0, 1.0)
                ang = math.acos(dot)
                max_ang = MISSILE_TURN_RATE * dt
                if ang > 1e-6:
                    t = min(1.0, max_ang / ang)
                    new_dir = (cur * (1.0 - t) + desired * t)
                    if new_dir.length_squared() > 1e-6:
                        new_dir = new_dir.normalize()
                        sp = self.vel.length()
                        self.vel = new_dir * sp
        sp = min(520.0, self.vel.length() + 160.0*dt)
        if self.vel.length_squared() > 1e-6:
            self.vel = self.vel.normalize() * sp
        self.pos += self.vel * dt
        return self.t < self.life

class AtomicBomb:
    def __init__(self, pos: Vector3, vel: Vector3, neon):
        self.pos = pos.copy()
        self.vel = vel.copy()
        self.neon = neon
        self.dead = False
    def update(self, dt):
        self.vel.z -= 38.0 * dt
        self.pos += self.vel * dt
        if self.pos.z <= 0.0:
            self.pos.z = 0.0
            self.dead = True
        return not self.dead

# ----------------------------
# Weapon modes
# ----------------------------
WEAPON_MODES = [
    {
        "name": "Pulse MG + Pink Seekers",
        "bullet_speed": 560.0,
        "bullet_spread_deg": 1.4,
        "bullet_color": (1.0, 0.85, 0.25),
        "bullet_life": 1.05,
        "bullet_size": 6,
        "bullet_dmg_rng": (14, 28),
        "missile_color": (1.0, 0.25, 0.85),
        "missile_speed": 300.0,
        "missile_dmg_rng": (120, 180),
        "missile_radius_rng": (12.0, 16.0),
        "impact_theme": "spark",
    },
    {
        "name": "Cyan Rail + Violet Swarm",
        "bullet_speed": 820.0,
        "bullet_spread_deg": 0.35,
        "bullet_color": (0.10, 0.90, 1.00),
        "bullet_life": 0.75,
        "bullet_size": 5,
        "bullet_dmg_rng": (20, 44),
        "missile_color": (0.60, 0.35, 1.00),
        "missile_speed": 320.0,
        "missile_dmg_rng": (105, 165),
        "missile_radius_rng": (10.0, 15.0),
        "impact_theme": "ring",
    },
    {
        "name": "Green Scatter + Orange Boomers",
        "bullet_speed": 510.0,
        "bullet_spread_deg": 2.6,
        "bullet_color": (0.20, 1.00, 0.50),
        "bullet_life": 1.10,
        "bullet_size": 7,
        "bullet_dmg_rng": (10, 24),
        "missile_color": (1.00, 0.60, 0.10),
        "missile_speed": 285.0,
        "missile_dmg_rng": (140, 220),
        "missile_radius_rng": (14.0, 22.0),
        "impact_theme": "burst",
    },
    {
        "name": "White Prism + Blue Nova",
        "bullet_speed": 640.0,
        "bullet_spread_deg": 1.0,
        "bullet_color": (1.00, 1.00, 1.00),
        "bullet_life": 0.95,
        "bullet_size": 5,
        "bullet_dmg_rng": (16, 36),
        "missile_color": (0.10, 1.00, 0.85),
        "missile_speed": 305.0,
        "missile_dmg_rng": (130, 195),
        "missile_radius_rng": (12.0, 18.0),
        "impact_theme": "prism",
    },
]


# Player-only default weapon (does not change AI weapon distribution).
# Press R to cycle into the global weapon modes list.
PLAYER_DEFAULT_WEAPON = {
    "name": "Laser Machine Guns",
    "bullet_speed": 780.0,
    "bullet_spread_deg": 0.65,
    "bullet_color": (0.45, 0.95, 1.00),
    "bullet_life": 0.75,
    "bullet_size": 7,
    "bullet_dmg_rng": (10, 18),
    # missiles disabled by default for this mode; player can still right-click missiles
    "missile_color": (1.0, 0.25, 0.85),
    "missile_speed": 300.0,
    "missile_dmg_rng": (130, 195),
    "missile_radius_rng": (12.0, 18.0),
    "impact_theme": "laser",
}

PLAYER_BOMB_CD = 0.55  # seconds between player bomb drops

def weapon_mode_index(mode_dict):
    try:
        return WEAPON_MODES.index(mode_dict)
    except ValueError:
        return 0

# ----------------------------
# Player ship variants (wireframe models + stats)
# ----------------------------
def make_variant_models():
    # Model A: spear fighter
    verts_a = [
        Vector3(0,  4.2,  0.0),
        Vector3(-1.0,  1.8, -0.3),
        Vector3( 1.0,  1.8, -0.3),
        Vector3(-2.3,  0.3,  0.0),
        Vector3( 2.3,  0.3,  0.0),
        Vector3(-0.8, -2.9,  0.1),
        Vector3( 0.8, -2.9,  0.1),
        Vector3(0.0, -4.2,  0.0),
        Vector3(0.0, -3.1,  1.2),
        Vector3(0.0,  2.8,  0.9),
    ]
    edges_a = [
        (0,1),(0,2),
        (1,3),(2,4),
        (3,5),(4,6),
        (5,7),(6,7),
        (5,8),(6,8),(8,7),
        (1,2),
        (5,6),
        (0,9),(9,8),
    ]

    # Model B: delta wing
    verts_b = [
        Vector3(0,  3.8,  0.0),
        Vector3(-2.8, 0.0,  0.0),
        Vector3( 2.8, 0.0,  0.0),
        Vector3(0, -3.6,  0.0),
        Vector3(0, -1.4,  1.4),
        Vector3(0,  0.8,  1.0),
        Vector3(-1.2, -2.4, 0.2),
        Vector3( 1.2, -2.4, 0.2),
    ]
    edges_b = [
        (0,1),(0,2),(1,3),(2,3),
        (1,6),(6,3),(2,7),(7,3),
        (0,5),(5,4),(4,3),
        (6,7),
    ]

    # Model C: heavy “box” interceptor
    verts_c = [
        Vector3(-1.6,  2.2,  0.5),
        Vector3( 1.6,  2.2,  0.5),
        Vector3( 1.6, -2.2,  0.5),
        Vector3(-1.6, -2.2,  0.5),
        Vector3(-1.6,  2.2, -0.5),
        Vector3( 1.6,  2.2, -0.5),
        Vector3( 1.6, -2.2, -0.5),
        Vector3(-1.6, -2.2, -0.5),
        Vector3(0.0,  4.0,  0.0),
        Vector3(0.0, -4.2,  0.0),
        Vector3(-3.2, -0.8, 0.0),
        Vector3( 3.2, -0.8, 0.0),
    ]
    edges_c = [
        (0,1),(1,2),(2,3),(3,0),
        (4,5),(5,6),(6,7),(7,4),
        (0,4),(1,5),(2,6),(3,7),
        (8,0),(8,1),
        (9,2),(9,3),
        (10,3),(10,0),
        (11,2),(11,1),
        (10,11),
    ]

    return [
        {"name":"Spear", "verts":verts_a, "edges":edges_a, "radius":4.4, "hp":2700, "shield":1900, "speed":156, "damp":0.060},
        {"name":"Delta", "verts":verts_b, "edges":edges_b, "radius":4.0, "hp":2400, "shield":2100, "speed":170, "damp":0.055},
        {"name":"Bulwark", "verts":verts_c, "edges":edges_c, "radius":5.0, "hp":3200, "shield":1800, "speed":142, "damp":0.065},
    ]

PLAYER_VARIANTS = make_variant_models()

# UFO model (kept)
UFO_VERTS = [
    Vector3(0,  0.0,  1.2),
    Vector3(0,  0.0, -0.4),
    Vector3(-2.0, 0.0, 0.2),
    Vector3( 2.0, 0.0, 0.2),
    Vector3(0.0, -2.0, 0.2),
    Vector3(0.0,  2.0, 0.2),
]
UFO_EDGES = [(0,2),(0,3),(0,4),(0,5),(1,2),(1,3),(1,4),(1,5),(2,4),(4,3),(3,5),(5,2)]


SPEED_BOAT_MODEL = {
    "verts": [
        Vector3(0.0, 7.8, 0.15),
        Vector3(2.7, 3.8, 0.25),
        Vector3(3.2, -2.8, 0.05),
        Vector3(1.8, -6.4, -0.10),
        Vector3(-1.8, -6.4, -0.10),
        Vector3(-3.2, -2.8, 0.05),
        Vector3(-2.7, 3.8, 0.25),
        Vector3(0.0, 1.8, 1.95),
        Vector3(1.15, 0.2, 1.25),
        Vector3(-1.15, 0.2, 1.25),
        Vector3(0.0, -4.8, 0.85),
        Vector3(0.0, -7.6, 0.55),
        Vector3(1.0, -7.1, -0.65),
        Vector3(-1.0, -7.1, -0.65),
    ],
    "edges": [
        (0,1),(1,2),(2,3),(3,4),(4,5),(5,6),(6,0),
        (0,7),(7,8),(8,2),(7,9),(9,5),
        (8,10),(9,10),(10,11),(3,11),(4,11),
        (3,12),(4,13),(12,13),(11,12),(11,13),
        (1,8),(6,9)
    ]
}

def transform_model(verts, pos: Vector3, fwd: Vector3, right: Vector3, up: Vector3):
    return [pos + right * v.x + fwd * v.y + up * v.z for v in verts]

# ----------------------------
# Ships / UFOs
# ----------------------------
class Ship:
    def __init__(self, sid: int, is_player: bool, rng: random.Random, variant_index=0):
        self.sid = sid
        self.is_player = is_player
        self.dead = False
        self.neon = rand_neon(rng)

        self.variant_index = int(variant_index)
        self.variant = PLAYER_VARIANTS[self.variant_index] if is_player else PLAYER_VARIANTS[sid % len(PLAYER_VARIANTS)]

        self.hp_max = int(self.variant["hp"] if is_player else self.variant["hp"] * 0.82)
        self.hp = float(self.hp_max)
        self.shield_max = int(self.variant["shield"] if is_player else self.variant["shield"] * 0.78)
        self.shield = float(self.shield_max)
        self.shield_recharge = 132.0 if is_player else 115.0
        self.shield_delay = 1.15
        self.last_hit = -999.0

        self.pos = Vector3(rng.uniform(-80, 80), rng.uniform(-80, 80), rng.uniform(40, 70))
        self.vel = Vector3(0, 0, 0)
        self.yaw = rng.uniform(-180, 180)
        self.pitch = rng.uniform(-8, 8)
        self.roll = 0.0 if is_player else rng.uniform(-180, 180)

        self.gun_cd = 0.035 if is_player else 0.06
        self.last_gun = -999.0
        self.missile_cd = 1.25
        self.last_missile = -999.0


        self.last_jump = -999.0
        self.radius = float(self.variant["radius"])
        self.trail = Trail(self.neon, max_pts=64 if is_player else 52)
        self.trail2 = Trail((1.0, 1.0, 1.0), max_pts=44)

    def apply_variant(self, idx: int):
        self.variant_index = idx % len(PLAYER_VARIANTS)
        self.variant = PLAYER_VARIANTS[self.variant_index]
        # keep percentage health/shield on swap (feels nicer than hard reset)
        hp_pct = 1.0 if self.hp_max <= 0 else (self.hp / self.hp_max)
        sh_pct = 1.0 if self.shield_max <= 0 else (self.shield / self.shield_max)
        self.hp_max = int(self.variant["hp"])
        self.shield_max = int(self.variant["shield"])
        self.hp = clamp(hp_pct, 0.0, 1.0) * self.hp_max
        self.shield = clamp(sh_pct, 0.0, 1.0) * self.shield_max
        self.radius = float(self.variant["radius"])

    def basis(self):
        return basis_from_ypr_deg(self.yaw, self.pitch, self.roll)

    def take_damage(self, dmg: int, t_now: float):
        if self.dead:
            return
        dmg = max(0, int(dmg))
        self.last_hit = t_now
        # Hit sound (hit.wav override supported). Player hit is always loud.
        if AUDIO is not None:
            AUDIO.play_hit(self.pos, is_player=bool(self.is_player), key=f'hit_ship_{self.sid}')
        if self.shield > 0.0:
            absorb = min(self.shield, dmg)
            self.shield -= absorb
            dmg = int(dmg - absorb * 0.72)
        if dmg > 0:
            self.hp -= dmg
        if self.hp <= 0:
            self.hp = 0
            self.dead = True

    def update(self, dt: float, t_now: float, ctrl, target, bullets, missiles, weapon_mode, rng: random.Random, space_factor: float):
        if self.dead:
            return

        if (t_now - self.last_hit) > self.shield_delay:
            self.shield = min(self.shield_max, self.shield + self.shield_recharge * dt)

        fwd, right, up = self.basis()

        if ctrl is not None:
            yaw_in = float(ctrl.get("yaw", 0.0))
            pitch_in = float(ctrl.get("pitch", 0.0))
            roll_in = float(ctrl.get("roll", 0.0))
            boost = bool(ctrl.get("boost", False))  # Shift
            hover = bool(ctrl.get("hover", False))  # auto-hover when throttle is zero
            fire = bool(ctrl.get("fire", False))
            fire_missile = bool(ctrl.get("missile", False))

            # Optional extras
            throttle = float(ctrl.get("throttle", 1.0))  # [-1..1]; 0 = hover
            jump = bool(ctrl.get("jump", False))          # Space (impulse)
            vz_in = float(ctrl.get("vz", 0.0))            # up/down thrusters

            # Stiffer rotation (less "draggy")
            self.yaw += yaw_in * KEY_YAW_RATE * dt
            self.pitch = clamp(self.pitch + pitch_in * KEY_PITCH_RATE * dt, -78.0, 78.0)
            self.roll = (self.roll + roll_in * KEY_ROLL_RATE * dt) % 360.0

            fwd, right, up = self.basis()

            # Speed / throttle model:
            base_spd = float(self.variant["speed"])
            spd = base_spd * (SHIFT_SPEED_MULT if boost else 1.0)

            if abs(throttle) < 1e-6:
                desired = Vector3(0.0, 0.0, 0.0)
                hover = True
            else:
                tscale = throttle if throttle > 0.0 else throttle * 0.65
                desired = fwd * (spd * tscale)

            # Higher alignment = stiffer controls; keep a little more inertia in space.
            align_atm = 2.20 + (SHIFT_ALIGN_BONUS if boost else 0.0) + (HOVER_ALIGN_BONUS if hover else 0.0)
            align_spc = 1.05 + (SHIFT_ALIGN_BONUS * 0.55 if boost else 0.0) + (HOVER_ALIGN_BONUS * 0.40 if hover else 0.0)
            align = lerp(align_atm, align_spc, space_factor)

            a = clamp(align * dt, 0.0, 1.0)
            self.vel = self.vel + (desired - self.vel) * a

            # Vertical control:
            self.vel.z += (-fwd.z) * lerp(32.0, 10.0, space_factor) * dt
            if abs(vz_in) > 1e-4:
                self.vel.z += vz_in * VERT_THRUST * dt

            self.vel.z += (lerp(16.0, 20.0, space_factor) if hover else lerp(-2.2, -0.2, space_factor)) * dt
            self.vel.z = clamp(self.vel.z, -160.0, 240.0)

            # Space = jump impulse (temporary boost up + slight forward)
            if jump and (t_now - self.last_jump) >= JUMP_COOLDOWN:
                self.last_jump = t_now
                self.vel += up * JUMP_UP_IMPULSE
                self.vel += fwd * JUMP_FWD_IMPULSE

            # Damping: lower in space, higher when hovering
            damp_base = float(self.variant["damp"])
            damp = lerp(damp_base * 0.95, damp_base * 0.30, space_factor) + (0.55 if hover else 0.05)
            self.vel *= (1.0 - clamp(damp * dt, 0.0, 0.42))

            if fire and (t_now - self.last_gun) >= self.gun_cd:
                self.last_gun = t_now
                if AUDIO:
                    # Player weapons should be the loudest; NPC weapons are short-range and quiet.
                    nm = str(weapon_mode.get('name','')).lower()
                    if 'beam' in nm:
                        cat = 'weapons/beams'
                    elif 'laser' in nm:
                        cat = 'weapons/lasers'
                    else:
                        cat = 'weapons/guns'
                    if self.is_player:
                        AUDIO.play_local(cat, base=0.95, cooldown=0.03, key=f'p_gun_{cat}')
                    else:
                        AUDIO.play_positional(cat, self.pos, base=0.12, near=220.0, max_dist=780.0, cooldown=0.12, key=f'n_gun_{self.sid}', echo=True, echo_gain=0.15)
                spread = math.radians(weapon_mode["bullet_spread_deg"])
                bs = weapon_mode["bullet_speed"] * (1.0 + 0.10 * space_factor)
                col = weapon_mode["bullet_color"]
                life = weapon_mode["bullet_life"]
                size = weapon_mode["bullet_size"]
                dmg = rng.randint(*weapon_mode["bullet_dmg_rng"])

                muzzle_offsets = [right * -1.2 + up * -0.2 + fwd * 2.2, right * 1.2 + up * -0.2 + fwd * 2.2]

                # v3.2: ground assault aiming for the PLAYER should be flatter/straighter (bias to horizontal fire).
                ground_flat = bool(self.is_player and getattr(self, "ground_mode", False))
                base_dir = Vector3(fwd.x, fwd.y, 0.0) if ground_flat else fwd
                base_dir = safe_norm(base_dir, fwd)

                for mo in muzzle_offsets:
                    jx = rng.uniform(-1, 1) * spread
                    jy = rng.uniform(-1, 1) * spread
                    if ground_flat:
                        # Keep spread mostly horizontal in ground mode; avoid pitching into the sky/ground.
                        dirv = (base_dir + right * math.sin(jx) * 0.22)
                    else:
                        dirv = (base_dir + right * math.sin(jx) * 0.18 + up * math.sin(jy) * 0.18)
                    dirv = safe_norm(dirv, base_dir)
                    bp = self.pos + mo
                    bv = dirv * bs + self.vel * 0.22
                    bullets.append(Bullet(self, bp, bv, col, dmg=dmg, life=life, size=size, style_id=(3 if (self.is_player and weapon_mode.get("name","")=="Laser Machine Guns") else weapon_mode_index(weapon_mode))))

            if fire_missile and (t_now - self.last_missile) >= self.missile_cd and target is not None:
                self.last_missile = t_now
                if AUDIO:
                    if self.is_player:
                        AUDIO.play_local('weapons/missiles', base=0.80, cooldown=0.35, key='p_missile')
                    else:
                        AUDIO.play_positional('weapons/missiles', self.pos, base=0.10, near=260.0, max_dist=900.0, cooldown=0.60, key=f'n_missile_{self.sid}', echo=True, echo_gain=0.14)
                ms = weapon_mode["missile_speed"] * (1.0 + 0.10 * space_factor)
                mcol = weapon_mode["missile_color"]
                mdmg = rng.randint(*weapon_mode["missile_dmg_rng"])
                mrad = rng.uniform(*weapon_mode["missile_radius_rng"])
                origin = self.pos + fwd * 3.4 + up * -0.15
                launch_dir = Vector3(fwd.x, fwd.y, 0.0) if (self.is_player and getattr(self, "ground_mode", False)) else fwd
                launch_dir = safe_norm(launch_dir, fwd)
                missiles.append(Missile(self, origin, launch_dir * ms + self.vel * 0.12, target, mcol, mdmg, mrad, style_id=weapon_mode_index(weapon_mode)))

        self.pos += self.vel * dt
        if self.pos.z < MIN_ALT:
            self.pos.z = MIN_ALT

        max_alt = lerp(ATMOS_MAX_ALT, SPACE_MAX_ALT, clamp(space_factor*1.15, 0.0, 1.0))
        self.pos.z = clamp(self.pos.z, MIN_ALT, max_alt)

        self.trail.add(self.pos - fwd * 2.9 + up * 0.2)
        self.trail2.add(self.pos - fwd * 2.9 + up * 0.2 - up * 0.25)

class UFO:
    def __init__(self, uid: int, rng: random.Random):
        self.uid = uid
        self.dead = False
        self.neon = rand_neon(rng)
        self.hp_max = int(UFO_HP * rng.uniform(0.9, 1.2))
        self.hp = float(self.hp_max)
        self.shield_max = int(UFO_SHIELD * rng.uniform(0.9, 1.2))
        self.shield = float(self.shield_max)
        self.shield_recharge = 95.0
        self.last_hit = -999.0
        self.pos = Vector3(rng.uniform(-150, 150), rng.uniform(-150, 150), rng.uniform(80, 140))
        self.vel = Vector3(0, 0, 0)
        self.yaw = rng.uniform(-180, 180)
        self.pitch = rng.uniform(-5, 5)
        self.roll = 0.0
        self.radius = 6.0
        self.fire_cd = rng.uniform(0.25, 0.45)
        self.last_fire = -999.0
        self.trail = Trail(self.neon, max_pts=44)

    def basis(self):
        return basis_from_ypr_deg(self.yaw, self.pitch, self.roll)

    def take_damage(self, dmg: int, t_now: float):
        if self.dead:
            return
        self.last_hit = t_now
        # Hit sound (hit.wav override supported).
        if AUDIO is not None:
            AUDIO.play_hit(self.pos, is_player=False, key=f'hit_ufo_{self.uid}')
        if self.shield > 0:
            absorb = min(self.shield, dmg)
            self.shield -= absorb
            dmg = int(dmg - absorb * 0.65)
        if dmg > 0:
            self.hp -= dmg
        if self.hp <= 0:
            self.hp = 0
            self.dead = True

    def update(self, dt: float, t_now: float, target, beams, rng: random.Random):
        if self.dead:
            return
        if (t_now - self.last_hit) > 1.15:
            self.shield = min(self.shield_max, self.shield + self.shield_recharge * dt)

        if target is None or getattr(target, "dead", False):
            return

        to = target.pos - self.pos
        dist = max(1e-6, to.length())
        dirv = to / dist
        desired_yaw = math.degrees(math.atan2(dirv.x, dirv.y))
        self.yaw = lerp_angle_deg(self.yaw, desired_yaw, clamp(1.35*dt, 0, 1))
        self.pitch = lerp(self.pitch, clamp(-math.degrees(math.asin(clamp(dirv.z, -1, 1))), -18, 18), clamp(0.9*dt, 0, 1))

        fwd, _, _ = self.basis()

        standoff = 110.0 + 35.0 * math.sin(t_now * 0.7 + self.uid)
        tang = Vector3(-dirv.y, dirv.x, 0.0)
        tang = safe_norm(tang, Vector3(1,0,0))
        desired = (tang * 58.0) + (dirv * (dist - standoff) * 0.65) + Vector3(0, 0, math.sin(t_now*1.6 + self.uid)*6.0)
        self.vel = self.vel * (1.0 - clamp(0.80*dt, 0, 0.25)) + desired * clamp(0.80*dt, 0, 0.25)
        self.vel *= (1.0 - clamp(0.06*dt, 0, 0.06))
        self.pos += self.vel * dt
        self.pos.z = clamp(self.pos.z, 40.0, 220.0)

        self.trail.add(self.pos - fwd * 1.6 + Vector3(0,0,0.2))

        if (t_now - self.last_fire) >= self.fire_cd and dist < 260.0:
            self.last_fire = t_now
            hit_point = target.pos + Vector3(rng.uniform(-2.0,2.0), rng.uniform(-2.0,2.0), rng.uniform(-1.5,1.5))
            beams.append(Beam(self.pos, hit_point, self.neon, life=0.13))
            dot = fwd.dot(dirv)
            if dot > 0.86:
                try:
                    target.take_damage(rng.randint(10, 22), t_now)
                except TypeError:
                    try:
                        target.take_damage(rng.randint(10, 22))
                    except Exception:
                        pass

# ----------------------------
# Rendering helpers
# ----------------------------
def draw_additive_line(surf, a, b, color_rgba, width=2):
    pygame.draw.line(surf, color_rgba, a, b, width)

def draw_glow_point(surf, p, color_rgb, size=10, alpha=180):
    r, g, b = rgbf_to_rgbi(color_rgb, 255)[:3]
    for i in range(3):
        rad = max(1, int(size * (1.0 + i * 0.55)))
        a = int(alpha * (0.55 if i == 0 else (0.30 if i == 1 else 0.18)))
        pygame.draw.circle(surf, (r, g, b, a), p, rad)

# ----------------------------
# Main
# ----------------------------

# ----------------------------
# World / Runner (merged)
# ----------------------------
# (world module docstring removed in merged build)



import math
import random
import os
import sys
import time
import traceback
import platform
import pygame
from pygame.math import Vector3


def convex_hull_2d(pts):
    """Monotone chain convex hull. Returns list of points in CCW order."""
    pts = [(float(x), float(y)) for (x, y) in pts]
    pts = sorted(set(pts))
    if len(pts) <= 2:
        return pts
    def cross(o, a, b):
        return (a[0]-o[0])*(b[1]-o[1]) - (a[1]-o[1])*(b[0]-o[0])
    lower = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]

def make_dawn_gradient(size):
    """Precomputed sky gradient surface (behind everything)."""
    w, h = size
    surf = pygame.Surface((w, h)).convert()
    # Top -> deep space indigo, mid -> violet, horizon -> warm dawn
    top = (5, 6, 12)
    mid = (44, 18, 70)
    horizon = (255, 120, 70)
    glow = (255, 190, 120)
    for y in range(h):
        t = y / max(1, (h-1))
        # Push warmth closer to horizon
        if t < 0.55:
            u = t / 0.55
            r = int(lerp(top[0], mid[0], u))
            g = int(lerp(top[1], mid[1], u))
            b = int(lerp(top[2], mid[2], u))
        else:
            u = (t - 0.55) / 0.45
            r = int(lerp(mid[0], horizon[0], u))
            g = int(lerp(mid[1], horizon[1], u))
            b = int(lerp(mid[2], horizon[2], u))
        # Extra bright band at very bottom (horizon glow)
        if t > 0.88:
            v = (t - 0.88) / 0.12
            r = int(lerp(r, glow[0], v * 0.85))
            g = int(lerp(g, glow[1], v * 0.85))
            b = int(lerp(b, glow[2], v * 0.70))
        pygame.draw.line(surf, (r, g, b), (0, y), (w, y))
    return surf

def circle_points_3d(center: Vector3, normal: Vector3, radius: float, segments=64):
    n = safe_norm(normal, Vector3(0,0,1))
    a = Vector3(1,0,0) if abs(n.dot(Vector3(1,0,0))) < 0.9 else Vector3(0,1,0)
    u = safe_norm(n.cross(a), Vector3(1,0,0))
    v = safe_norm(n.cross(u), Vector3(0,1,0))
    pts = []
    for i in range(segments+1):
        t = (i / segments) * (math.pi * 2.0)
        pts.append(center + (u * math.cos(t) + v * math.sin(t)) * radius)
    return pts

# ----------------------------
# Camera/projection
# ----------------------------
class Camera:
    def __init__(self):
        self.pos = Vector3(0, -25, 14)
        self.fov = math.radians(FOV_DEG)
        self.f = (W * 0.5) / math.tan(self.fov * 0.5)

    def project(self, p_world: Vector3, fwd: Vector3, right: Vector3, up: Vector3):
        v = p_world - self.pos
        x = v.dot(right)
        y = v.dot(up)
        z = v.dot(fwd)
        if z <= NEAR_Z:
            return None
        sx = (W * 0.5) + (x / z) * self.f
        sy = (H * 0.5) - (y / z) * self.f
        return (sx, sy, z)

# ----------------------------
# City streaming
# ----------------------------
class Building:
    __slots__ = (
        "cx", "cy", "w", "d", "h",
        "neon", "pattern", "stripe_count", "stripe_phase",
        "_corners",
        "hp", "hp_max", "alive",
    )
    def __init__(self, cx, cy, w, d, h, neon, pattern, stripe_count, stripe_phase):
        self.cx, self.cy = float(cx), float(cy)
        self.w, self.d, self.h = float(w), float(d), float(h)
        self.neon = neon
        # pattern: 0 = horizontal bands, 1 = vertical ribs
        self.pattern = int(pattern)
        self.stripe_count = int(stripe_count)
        self.stripe_phase = float(stripe_phase)

        # Destruction: scalable HP by footprint and height (keeps smaller buildings poppable, towers tougher)
        self.hp_max = float(max(180.0, 220.0 + (self.w * self.d) * 3.5 + self.h * 3.2))
        self.hp = float(self.hp_max)
        self.alive = True

        # Cache static geometry once (major perf win in dense cities)
        x0, x1 = self.cx - self.w, self.cx + self.w
        y0, y1 = self.cy - self.d, self.cy + self.d
        z0, z1 = 0.0, self.h
        self._corners = (
            Vector3(x0, y0, z0), Vector3(x1, y0, z0),
            Vector3(x1, y1, z0), Vector3(x0, y1, z0),
            Vector3(x0, y0, z1), Vector3(x1, y0, z1),
            Vector3(x1, y1, z1), Vector3(x0, y1, z1),
        )

    def corners(self):
        return self._corners





class Pyramid:
    __slots__ = ("cx", "cy", "w", "d", "h", "neon", "_corners", "hp", "hp_max", "alive")
    def __init__(self, cx, cy, w, d, h, neon):
        self.cx, self.cy = float(cx), float(cy)
        self.w, self.d, self.h = float(w), float(d), float(h)
        self.neon = neon

        # Landmark is tougher than average buildings.
        self.hp_max = float(max(900.0, 650.0 + (self.w * self.d) * 6.0 + self.h * 6.0))
        self.hp = float(self.hp_max)
        self.alive = True

        x0, x1 = self.cx - self.w, self.cx + self.w
        y0, y1 = self.cy - self.d, self.cy + self.d
        z0, z1 = 0.0, self.h
        apex = Vector3(self.cx, self.cy, self.h * 1.18)
        self._corners = (
            Vector3(x0, y0, z0), Vector3(x1, y0, z0),
            Vector3(x1, y1, z0), Vector3(x0, y1, z0),
            apex,
        )

    def corners(self):
        return self._corners


PYR_EDGES = [
    (0,1),(1,2),(2,3),(3,0),
    (0,4),(1,4),(2,4),(3,4),
]

BOX_EDGES = [
    (0,1),(1,2),(2,3),(3,0),
    (4,5),(5,6),(6,7),(7,4),
    (0,4),(1,5),(2,6),(3,7),
]

class City:
    def __init__(self, seed=1337):
        self.seed = seed
        self.chunks = {}              # active chunks
        # Evicted chunk cache: keep generated buildings for chunks that are unloaded from
        # the active set. This prevents regeneration spikes when the player returns.
        self._evicted = {}            # (cx,cy) -> buildings
        self._evict_order = []        # simple LRU-like order for evicted keys
        self._last_used = {}          # (cx,cy) -> last used time (seconds)

        self._flat_cache = []
        self._cache_dirty = True

    def _gen_chunk(self, cx, cy):
        rng = random.Random((cx * 928371 + cy * 192837 + self.seed) & 0xFFFFFFFF)
        blds = []
        base_x = cx * CITY_CHUNK
        base_y = cy * CITY_CHUNK

        # Lot grid inside the chunk; streets run between lots.
        chunk_min_x = base_x - CITY_CHUNK * 0.5
        chunk_min_y = base_y - CITY_CHUNK * 0.5
        cell = CITY_CHUNK / float(max(1, CITY_LOT_GRID))

        pyramid_used = False

        for ix in range(CITY_LOT_GRID):
            for iy in range(CITY_LOT_GRID):
                lot_cx = chunk_min_x + (ix + 0.5) * cell
                lot_cy = chunk_min_y + (iy + 0.5) * cell

                # Keep a main cross-avenue clear through the chunk center
                if abs(lot_cx - base_x) < CITY_AVENUE_HALF_WIDTH or abs(lot_cy - base_y) < CITY_AVENUE_HALF_WIDTH:
                    continue

                # Randomly keep lots empty to form plazas/parking/yard space
                if rng.random() < CITY_PLAZA_CHANCE:
                    continue

                if rng.random() > CITY_LOT_BUILD_CHANCE:
                    continue

                # Lot bounds with padding to create street setbacks
                lot_half = (cell * 0.5) - CITY_LOT_PADDING
                if lot_half < 10.0:
                    lot_half = 10.0

                # Choose footprint constrained by the lot
                w = rng.uniform(lot_half * 0.28, lot_half * 0.48)
                d = rng.uniform(lot_half * 0.28, lot_half * 0.48)

                px = lot_cx + rng.uniform(-lot_half * 0.18, lot_half * 0.18)
                py = lot_cy + rng.uniform(-lot_half * 0.18, lot_half * 0.18)

                # Landmark pyramids (rare): big footprint, lower height
                if (not pyramid_used) and (rng.random() < CITY_PYRAMID_CHANCE):
                    pyramid_used = True
                    pw = rng.uniform(lot_half * 0.55, lot_half * 0.80)
                    pd = rng.uniform(lot_half * 0.55, lot_half * 0.80)
                    ph = rng.uniform(34.0, 92.0)
                    neon = rand_neon(rng)
                    blds.append(Pyramid(px, py, pw, pd, ph, neon))
                    continue

                h = rng.uniform(20.0, 98.0) * (1.0 if rng.random() > 0.15 else 1.65)
                neon = rand_neon(rng)
                pattern = 0 if rng.random() < 0.5 else 1
                stripe_count = rng.randint(3, 7) if pattern == 0 else rng.randint(4, 9)
                stripe_phase = rng.random()
                blds.append(Building(px, py, w, d, h, neon, pattern, stripe_count, stripe_phase))

        # Fallback: ensure every chunk has at least a couple structures so the skyline reads
        if len(blds) < 2:
            n = rng.randint(BUILDINGS_PER_CHUNK[0], BUILDINGS_PER_CHUNK[1])
            for _ in range(n):
                px = base_x + rng.uniform(-CITY_CHUNK*0.44, CITY_CHUNK*0.44)
                py = base_y + rng.uniform(-CITY_CHUNK*0.44, CITY_CHUNK*0.44)
                if abs(px - base_x) < CITY_AVENUE_HALF_WIDTH or abs(py - base_y) < CITY_AVENUE_HALF_WIDTH:
                    continue
                w = rng.uniform(7.0, 18.0)
                d = rng.uniform(7.0, 18.0)
                h = rng.uniform(22.0, 92.0)
                neon = rand_neon(rng)
                pattern = 0 if rng.random() < 0.5 else 1
                stripe_count = rng.randint(3, 7) if pattern == 0 else rng.randint(4, 9)
                stripe_phase = rng.random()
                blds.append(Building(px, py, w, d, h, neon, pattern, stripe_count, stripe_phase))

        return blds

    

    def _touch_chunk(self, key, t_now: float):
        # Track most-recent use for both active and evicted chunks.
        self._last_used[key] = float(t_now)
        # If it lives in the eviction order, move it to the end (simple LRU).
        try:
            i = self._evict_order.index(key)
        except ValueError:
            return
        self._evict_order.pop(i)
        self._evict_order.append(key)

    def _maybe_trim_evicted(self):
        # Keep memory bounded. When over the cap, trim down to a floor.
        if len(self._evict_order) <= CITY_EVICT_CACHE_MAX:
            return
        target = CITY_EVICT_CACHE_FLOOR if CITY_EVICT_CACHE_FLOOR < CITY_EVICT_CACHE_MAX else CITY_EVICT_CACHE_MAX
        while len(self._evict_order) > target:
            k = self._evict_order.pop(0)
            self._evicted.pop(k, None)
            self._last_used.pop(k, None)

    def stream_around(self, look_x, look_y, player_pos_xy, player_vel_xy, t_now: float, cam_fwd_xy=(0.0, 1.0)):
        """Stream/generate chunks around a *lookahead* point, but unload conservatively.

        Unload only when:
          - the chunk is well outside the keep radius,
          - the player is moving away from it (dot < 0),
          - and it is outside the lookahead set (so it is very likely off-screen / irrelevant).
        """
        cx = int(math.floor(look_x / CITY_CHUNK))
        cy = int(math.floor(look_y / CITY_CHUNK))

        # Want set: what we pre-generate ahead of the player
        want = set()
        for dx in range(-CITY_RADIUS, CITY_RADIUS+1):
            for dy in range(-CITY_RADIUS, CITY_RADIUS+1):
                want.add((cx+dx, cy+dy))

        # Always keep a conservative neighborhood around the *actual* player position.
        pcx = int(math.floor(player_pos_xy[0] / CITY_CHUNK))
        pcy = int(math.floor(player_pos_xy[1] / CITY_CHUNK))
        keep = set()
        for dx in range(-CITY_KEEP_RADIUS, CITY_KEEP_RADIUS+1):
            for dy in range(-CITY_KEEP_RADIUS, CITY_KEEP_RADIUS+1):
                keep.add((pcx+dx, pcy+dy))

        # Generate what we want (lookahead) and what we keep (player neighborhood)
        new_added = 0
        for k in (want | keep):
            if k not in self.chunks:
                # Prefer restoring from the evicted cache to avoid regeneration stalls.
                if k in self._evicted:
                    self.chunks[k] = self._evicted.pop(k)
                    # remove from LRU list (we'll re-touch below)
                    try:
                        self._evict_order.remove(k)
                    except ValueError:
                        pass
                else:
                    self.chunks[k] = self._gen_chunk(k[0], k[1])
                    new_added += 1
            self._touch_chunk(k, t_now)
        if new_added:
            self._cache_dirty = True

        # Conservative unload: far + moving away + behind camera + not in keep + not in want.
        # Instead of discarding, move chunks into an evicted-cache so they can be restored quickly later.
        vx, vy = float(player_vel_xy[0]), float(player_vel_xy[1])
        sp2 = vx*vx + vy*vy
        if sp2 > 0.25:  # don't churn when basically stationary
            px, py = float(player_pos_xy[0]), float(player_pos_xy[1])
            fx, fy = float(cam_fwd_xy[0]), float(cam_fwd_xy[1])
            drop_dist = (CITY_DROP_RADIUS * CITY_CHUNK)
            drop2 = drop_dist * drop_dist

            rem = []
            for (kx, ky) in list(self.chunks.keys()):
                if (kx, ky) in want or (kx, ky) in keep:
                    continue
                # Chunk center
                ccx = (kx + 0.5) * CITY_CHUNK
                ccy = (ky + 0.5) * CITY_CHUNK
                dx = ccx - px
                dy = ccy - py
                if (dx*dx + dy*dy) < drop2:
                    continue
                # Moving away? (chunk is behind velocity vector)
                if (vx*dx + vy*dy) >= 0.0:
                    continue
                # Also require it to be behind the camera/ship facing direction (likely off-screen).
                if (fx*dx + fy*dy) >= 0.0:
                    continue
                rem.append((kx, ky))

            for k in rem:
                bl = self.chunks.pop(k, None)
                if bl is not None:
                    self._evicted[k] = bl
                    self._evict_order.append(k)
            if rem:
                self._maybe_trim_evicted()
                self._cache_dirty = True

    def all_buildings(self):
        for bld_list in self.chunks.values():
            for b in bld_list:
                yield b

    def all_buildings_list(self):
        # Cached flatten to avoid per-frame allocations in the renderer
        if self._cache_dirty:
            flat = []
            for bl in self.chunks.values():
                flat.extend(bl)
            self._flat_cache = flat
            self._cache_dirty = False
        return self._flat_cache

    # ----------------------------
    # Destructible buildings helpers (chunk-local for performance)
    # ----------------------------
    def nearby_buildings(self, x: float, y: float, radius_chunks: int = 1):
        cx = int(math.floor(x / CITY_CHUNK))
        cy = int(math.floor(y / CITY_CHUNK))
        out = []
        for dx in range(-radius_chunks, radius_chunks + 1):
            for dy in range(-radius_chunks, radius_chunks + 1):
                bl = self.chunks.get((cx + dx, cy + dy))
                if bl:
                    out.extend(bl)
        return out

    @staticmethod
    def hit_test(building, p: Vector3, pad_xy: float = 0.0, pad_z: float = 0.0):
        if building is None or (not getattr(building, "alive", True)):
            return False
        if p.z < (0.0 - pad_z) or p.z > (building.h + pad_z):
            return False
        return (abs(p.x - building.cx) <= (building.w + pad_xy)) and (abs(p.y - building.cy) <= (building.d + pad_xy))

    def damage_building(self, building, dmg: float):
        if building is None or (not getattr(building, "alive", True)):
            return False
        if not hasattr(building, "hp"):
            return False
        building.hp -= max(0.0, float(dmg))
        if building.hp > 0.0:
            return False
        building.hp = 0.0
        building.alive = False

        # Remove from whichever list currently holds it (active chunk preferred).
        k = (int(math.floor(building.cx / CITY_CHUNK)), int(math.floor(building.cy / CITY_CHUNK)))
        lst = self.chunks.get(k)
        removed = False
        if lst is not None:
            try:
                lst.remove(building)
                removed = True
            except ValueError:
                pass
        if not removed:
            # Fallback: search active chunks (rare; handles edge cases near borders)
            for _, bl in self.chunks.items():
                if building in bl:
                    bl.remove(building)
                    break

        # Also remove from evicted cache (so destruction persists longer if the chunk is unloaded/reloaded).
        el = self._evicted.get(k)
        if el is not None and building in el:
            try:
                el.remove(building)
            except ValueError:
                pass

        self._cache_dirty = True
        return True

    def damage_buildings_aoe(self, x: float, y: float, radius: float, base_damage: float):
        # Returns a list of buildings destroyed by the blast.
        radius = float(radius)
        if radius <= 0.0:
            return []
        rc = 1 + int(radius / CITY_CHUNK)
        destroyed = []
        cand = list(self.nearby_buildings(x, y, radius_chunks=rc))
        for b in cand:
            if not getattr(b, "alive", True):
                continue
            dx = b.cx - x
            dy = b.cy - y
            d2 = dx*dx + dy*dy
            # quick reject using footprint margin
            margin = max(b.w, b.d) + 4.0
            if d2 > (radius + margin) * (radius + margin):
                continue
            d = math.sqrt(max(0.0, d2))
            t = max(0.0, 1.0 - (d / radius))
            dmg = float(base_damage) * (t ** 0.65)
            if dmg > 0.5:
                if self.damage_building(b, dmg):
                    destroyed.append(b)
        return destroyed




# ----------------------------
# Ground traffic (lightweight street vehicles)
# ----------------------------
# Cosmic sky objects
# ----------------------------
class Planet:
    def __init__(self, rng: random.Random, center: Vector3, radius: float):
        self.center = center.copy()
        self.radius = radius
        self.color = rand_neon(rng)
        self.ring_color = rand_neon(rng)
        self.ring_tilt = rng.uniform(-35, 35)
        self.ring_yaw = rng.uniform(-180, 180)
        self.ring_thickness = rng.uniform(0.8, 1.8)
        self.ring_scale = rng.uniform(1.4, 2.2)

class BlackHole:
    def __init__(self, rng: random.Random, center: Vector3):
        self.center = center.copy()
        self.radius = rng.uniform(38, 62)
        self.ring_radius = self.radius * rng.uniform(1.35, 1.75)
        self.ring_color = (0.9, 0.2, 1.0) if rng.random() < 0.5 else (0.1, 0.9, 1.0)
        self.spin = rng.uniform(-1.0, 1.0)

# ----------------------------
# Weather
# ----------------------------
class CloudPuff:
    __slots__ = ("pos", "r", "neon", "seed", "drift")
    def __init__(self, pos: Vector3, r: float, neon, seed: int, drift: Vector3):
        self.pos = pos.copy()
        self.r = float(r)
        self.neon = neon
        self.seed = seed
        self.drift = drift.copy()

    def update(self, dt: float, t_now: float, anchor: Vector3):
        self.pos += self.drift * dt
        # keep around player
        to = self.pos - Vector3(anchor.x, anchor.y, self.pos.z)
        d = to.length()
        if d > CLOUD_RING[1] * 1.35:
            ang = math.atan2(to.y, to.x) + math.pi
            rr = random.Random(self.seed ^ int(t_now*10)).uniform(CLOUD_RING[0], CLOUD_RING[1])
            self.pos.x = anchor.x + math.cos(ang) * rr
            self.pos.y = anchor.y + math.sin(ang) * rr
        return True

class Tornado:
    __slots__ = ("base", "h", "r0", "r1", "spin", "drift", "neon", "seed")
    def __init__(self, rng: random.Random, base: Vector3):
        self.base = base.copy()
        self.h = rng.uniform(*TORNADO_HEIGHT)
        self.r0 = rng.uniform(8.0, 18.0)
        self.r1 = rng.uniform(34.0, 62.0)
        self.spin = rng.uniform(-1.2, 1.2)
        self.drift = Vector3(rng.uniform(-10, 10), rng.uniform(-10, 10), 0.0)
        self.neon = rand_neon(rng)
        self.seed = rng.randint(0, 1<<30)

    def update(self, dt: float, t_now: float, anchor: Vector3):
        # wander + keep roughly near player
        self.base += self.drift * dt
        self.base.x += math.sin(t_now*0.19 + self.seed*0.001) * 2.2 * dt
        self.base.y += math.cos(t_now*0.17 + self.seed*0.001) * 2.2 * dt

        to = Vector3(self.base.x - anchor.x, self.base.y - anchor.y, 0.0)
        d = to.length()
        if d > TORNADO_RING[1] * 1.2:
            ang = math.atan2(to.y, to.x) + math.pi
            rr = random.Random(self.seed ^ int(t_now*7)).uniform(TORNADO_RING[0], TORNADO_RING[1])
            self.base.x = anchor.x + math.cos(ang) * rr
            self.base.y = anchor.y + math.sin(ang) * rr

        # mild drift changes
        if random.random() < 0.006:
            self.drift = (self.drift * 0.75) + Vector3(random.uniform(-10, 10), random.uniform(-10, 10), 0.0) * 0.25
        return True

    def wind_force(self, p: Vector3):
        # returns sideways swirl vector + vertical lift near center
        dx = p.x - self.base.x
        dy = p.y - self.base.y
        r = math.hypot(dx, dy)
        if r < 1e-6:
            return Vector3(0,0,0), 0.0
        if r > self.r1 * 1.25:
            return Vector3(0,0,0), 0.0
        t = clamp(1.0 - (r / (self.r1 * 1.25)), 0.0, 1.0)
        tang = Vector3(-dy, dx, 0.0)
        tang = safe_norm(tang, Vector3(1,0,0))
        swirl = tang * (140.0 * t) * (1.0 if self.spin >= 0 else -1.0)
        lift = 38.0 * t
        return swirl, lift

# ----------------------------
def main(embedded: bool = False, doomsday_ctx=None):
    embedded = bool(embedded or PANDA3D_LAUNCH_SAFE)
    launch_safe = bool(embedded or PANDA3D_LAUNCH_SAFE)
    no_audio = _has_cli_flag("--no-audio") or _env_flag("NEON_DOGFIGHT_NO_AUDIO", False)

    # Pre-init the mixer before pygame.init() when allowed.  Panda3D launch-safe
    # mode can disable audio with --no-audio if the parent engine owns audio.
    if not no_audio:
        try:
            pygame.mixer.pre_init(frequency=44100, size=-16, channels=2, buffer=512)
        except Exception:
            pass
    pygame.init()
    ensure_audio_folders()
    global AUDIO
    if no_audio:
        AUDIO = None
    else:
        try:
            AUDIO = AudioSystem(seed=424242)
        except Exception:
            AUDIO = None
    pygame.display.set_caption(f"Neon Dogfight – Infinite Wireframe City v3.10 ({PERF_PROFILE})")
    auto_mode = str(_get_cli_arg("--auto-mode", "foot") or "foot").strip().lower()
    auto_exit_after = _get_cli_arg("--auto-exit", None, float)

    # ------------------------------------------------------------
    # Windowing / scaling
    # - Internal render is always 1920x1080 (W,H). DO NOT change this on resize.
    # - The OS window can be resized freely; we letterbox/pillarbox the internal render.
    # - This prevents "expanding the world" when going fullscreen or resizing.
    #
    # Controls:
    #   F1  toggle mouse lock (unlock to resize window with the mouse)
    # ------------------------------------------------------------
    BASE_W, BASE_H = int(W), int(H)

    maximized_flag = 0 if (HOLOVERSE_EMBEDDED or launch_safe or _has_cli_flag("--no-maximize", "--windowed")) else getattr(pygame, "WINDOWMAXIMIZED", 0)

    flags = pygame.RESIZABLE | pygame.DOUBLEBUF | maximized_flag
    def _set_display_mode(w: int, h: int):
        """Create the OS window surface with best-effort vsync."""
        try:
            return pygame.display.set_mode((int(w), int(h)), flags, vsync=1)
        except TypeError:
            # Older pygame builds may not accept vsync kwarg.
            return pygame.display.set_mode((int(w), int(h)), flags)
        except Exception:
            return pygame.display.set_mode((int(w), int(h)), flags)

    def _pick_initial_window_size():
        # Start at 1080p if it fits, otherwise scale down to fit.
        # We will then attempt to MAXIMIZE the window (so it looks like fullscreen but keeps borders).
        try:
            info = pygame.display.Info()
            max_w = int(getattr(info, "current_w", BASE_W))
            max_h = int(getattr(info, "current_h", BASE_H))
        except Exception:
            max_w, max_h = BASE_W, BASE_H

        s = min(1.0, max_w / BASE_W, max_h / BASE_H)
        w1 = int(BASE_W * s)
        h1 = int(BASE_H * s)

        # Snap to exact 16:9.
        h1 = int(w1 * (BASE_H / BASE_W))
        if h1 > max_h:
            h1 = int(max_h)
            w1 = int(h1 * (BASE_W / BASE_H))

        w1 = max(640, int(w1))
        h1 = max(360, int(h1))
        return w1, h1

    def _compute_viewport(win_w: int, win_h: int):
        # Returns: (scale, (vw,vh), (ox,oy))
        s = min(win_w / BASE_W, win_h / BASE_H)
        vw = max(1, int(BASE_W * s))
        vh = max(1, int(BASE_H * s))
        ox = int((win_w - vw) // 2)
        oy = int((win_h - vh) // 2)
        return s, (vw, vh), (ox, oy)

    win_w, win_h = _pick_initial_window_size()
    display = _set_display_mode(win_w, win_h)

    # Make it look like fullscreen but keep window borders (OS-maximized window).
    def _try_maximize_window():
        # Prefer SDL2 maximize when available (Windows/macOS/Linux with SDL2).
        try:
            from pygame._sdl2 import Window  # type: ignore
            Window.from_display_module().maximize()
            return True
        except Exception:
            pass
        try:
            from pygame._sdl2.video import Window  # type: ignore
            Window.from_display_module().maximize()
            return True
        except Exception:
            return False

    if not (HOLOVERSE_EMBEDDED or launch_safe or _has_cli_flag("--no-maximize", "--windowed")):
        _try_maximize_window()
    # After optional maximizing, refresh window size + viewport (some systems won't emit VIDEORESIZE reliably).
    win_w, win_h = pygame.display.get_surface().get_size()

    # Internal canvas (fixed 1920x1080). Everything renders here.
    screen = pygame.Surface((BASE_W, BASE_H)).convert()

    # Background gradient (dawn horizon) behind stars/city (precomputed at internal res).
    sky_bg = make_dawn_gradient((BASE_W, BASE_H))

    # Scaled present surface (allocated only when needed).
    view_scale, view_size, view_off = _compute_viewport(win_w, win_h)
    scaled_frame = None  # type: pygame.Surface | None
    if view_size != (BASE_W, BASE_H):
        scaled_frame = pygame.Surface(view_size).convert()

    mouse_locked = True

    def _set_mouse_lock(lock: bool):
        nonlocal mouse_locked
        mouse_locked = bool(lock)
        pygame.mouse.set_visible(not mouse_locked)
        pygame.event.set_grab(mouse_locked)
        pygame.mouse.get_rel()
        if mouse_locked:
            try:
                pygame.mouse.set_pos((win_w // 2, win_h // 2))
            except Exception:
                pass

    _set_mouse_lock(False if (launch_safe or _has_cli_flag("--no-grab")) else True)

    clock = pygame.time.Clock()

    glow = pygame.Surface((W, H), pygame.SRCALPHA)
    ui = pygame.Surface((W, H), pygame.SRCALPHA)
    solid = pygame.Surface((W, H), pygame.SRCALPHA)  # opaque fills live here (depth-sorted) so geometry blocks what's behind

    # Background sky: dawn gradient horizon (always behind all geometry)
    sky = make_dawn_gradient((W, H))

    font = pygame.font.SysFont("consolas", 18)
    big = pygame.font.SysFont("consolas", 22, bold=True)

    # Short boot-time audio status banner (helps diagnose silent builds).
    audio_banner_t = 6.0
    if AUDIO is None:
        audio_banner = "AUDIO: OFF (AudioSystem not created)"
    elif not getattr(AUDIO, "enabled", False):
        err = getattr(AUDIO, "last_error", "mixer disabled")
        audio_banner = f"AUDIO: OFF ({err})"
    else:
        sfx_n = sum(len(v) for v in getattr(AUDIO, "bank", {}).values())
        mus_n = len(getattr(AUDIO, "music_paths", []) or [])
        audio_banner = f"AUDIO: ON (sfx {sfx_n}, music {mus_n})  root={ROOT_DIR} | PERF {PERF_PROFILE} | PandaSafe {launch_safe}"

    rng = random.Random(42)
    city = City(seed=1337)
    traffic = TrafficManager(seed=424242)

    cam = Camera()

    ships = []
    player = Ship(0, True, rng, variant_index=0)
    player.pos = Vector3(0, 0, 220)
    # Giant robots (multiple variants) scattered around the spawn region.
    # These are hostile to everyone and will crush vehicles/buildings on contact.
    giants = []

    spawn_xy = (float(player.pos.x), float(player.pos.y))

    # Performance-safe count: a small roster of distinct silhouettes + one kaiju.
    variant_plan = [
        ("transformer", 1.15),
        ("brute",       1.30),
        ("spider",      1.18),
        ("titan",       1.45),
        ("transformer", 1.12),
        ("brute",       1.28),
        ("godzilla",    1.75),
    ]

    for i, (k, sc) in enumerate(variant_plan):
        ang = (i / max(1, len(variant_plan))) * (math.pi * 2.0) + rng.uniform(-0.25, 0.25)
        rr = rng.uniform(420.0, 980.0) if k != "godzilla" else rng.uniform(850.0, 1350.0)
        gx = spawn_xy[0] + math.cos(ang) * rr
        gy = spawn_xy[1] + math.sin(ang) * rr
        giants.append(GiantMech(rng, (gx, gy), kind=k, scale=sc))

    def _active_giants():
        return [g for g in giants if (g is not None and (not getattr(g, "dead", False)))]

    def nearest_giant(pos: Vector3):
        best = None
        best2 = 1e18
        for g in giants:
            if g is None or getattr(g, "dead", False):
                continue
            dx = g.pos.x - pos.x
            dy = g.pos.y - pos.y
            d2 = dx*dx + dy*dy
            if d2 < best2:
                best2 = d2
                best = g
        return best

    # Combat mode cycle: Ground -> Air -> Ocean -> Ground
    combat_mode = 1
    ground_assault = True
    ocean_mode = False
    _saved_air_alt = float(player.pos.z)


    def _apply_combat_mode(new_mode: int):
        nonlocal combat_mode, ground_assault, ocean_mode, _saved_air_alt, aim_pitch, aim_yaw, chase_dir
        new_mode = int(new_mode) % 3
        was_air = (combat_mode == 0)
        combat_mode = new_mode
        ground_assault = (combat_mode == 1)
        ocean_mode = (combat_mode == 2)
        if not was_air and combat_mode == 0:
            player.pos.z = max(80.0, float(_saved_air_alt))
            player.vel.z = 0.0
            player.pitch = 0.0
            player.roll = 0.0
        elif combat_mode in (1, 2):
            if was_air:
                _saved_air_alt = float(player.pos.z)
            gx, gy = find_clear_ground_spot(player.pos.x, player.pos.y)
            player.pos.x = gx
            player.pos.y = gy
            player.vel.x *= 0.35
            player.vel.y *= 0.35
            player.vel.z = 0.0
            player.pitch = 0.0
            player.roll = 0.0
            if ground_assault:
                player.pos.z = 3.0
            else:
                player.pos.z = ocean_wave_height(player.pos.x, player.pos.y, t_now) + OCEAN_PLAYER_RIDE
        aim_pitch = 0.0
        aim_yaw = float(player.yaw)
        fwd0, _, _ = basis_from_ypr_deg(player.yaw, 0.0, 0.0)
        chase_dir = safe_norm(Vector3(fwd0.x, fwd0.y, 0.0), Vector3(0.0, 1.0, 0.0))
        pygame.mouse.get_rel()


    def find_clear_ground_spot(x: float, y: float) -> tuple[float, float]:
        # When switching to ground assault, we may be over a building footprint.
        # Drop-to-ground while inside a building can cause immediate collision cascades.
        # This finds a nearby spot that is not inside any building AABB.
        try:
            # Spiral/ring search around (x,y)
            for ring in range(0, 16):
                r = ring * 16.0
                if ring == 0:
                    samples = [(0.0, 0.0)]
                else:
                    n = max(8, ring * 6)
                    samples = []
                    for i in range(n):
                        ang = (i / n) * ((math.pi * 2.0))
                        samples.append((math.cos(ang) * r, math.sin(ang) * r))
                for ox, oy in samples:
                    tx = float(x + ox)
                    ty = float(y + oy)
                    blocked = False
                    for bld in city.nearby_buildings(tx, ty, radius_chunks=1):
                        if not getattr(bld, "alive", True):
                            continue
                        if abs(tx - bld.cx) <= (bld.w + 2.0) and abs(ty - bld.cy) <= (bld.d + 2.0):
                            blocked = True
                            break
                    if not blocked:
                        return tx, ty
        except Exception:
            pass
        return float(x), float(y)

    # v3.2: "Aim" orientation (camera/reticle) can move immediately,
    # while the ship rotates toward it. This makes the ship go precisely
    # where you aim, and prevents camera chase offset from snapping behind
    # the ship until it is actually aligned.
    aim_yaw = float(player.yaw)
    aim_pitch = float(player.pitch)
    chase_dir = Vector3(0, 1, 0)  # forward direction used for camera offset

    ships.append(player)
    for i in range(1, AI_COUNT + 1):
        s = Ship(i, False, rng)
        s.pos = Vector3(rng.uniform(-160, 160), rng.uniform(80, 240), rng.uniform(45, 95))
        ships.append(s)

    ufos = [UFO(i, rng) for i in range(UFO_COUNT)]

    bullets = []
    missiles = []
    explosions = []
    debris = []
    beams = []
    bombs = []
    fires = []
    firetruck = None  # spawned in ground assault
    warships = []
    helicopters = []
    heli_spawn_t = 0.0

    # Low-volume battle ambience (positional; ramps with proximity; never exceeds player loudness)
    battle_amb_next = 0.0
    firetruck_cd = 0.0


    # Weather init
    clouds = []
    for i in range(CLOUD_COUNT):
        ang = rng.uniform(0, (math.pi * 2.0))
        rr = rng.uniform(*CLOUD_RING)
        z = rng.uniform(*CLOUD_ALT)
        pos = Vector3(player.pos.x + math.cos(ang)*rr, player.pos.y + math.sin(ang)*rr, z)
        r = rng.uniform(8.0, 38.0)
        neon = (0.65, 0.85, 1.0) if rng.random() < 0.55 else (1.0, 1.0, 1.0)
        drift = Vector3(rng.uniform(-18, 18), rng.uniform(-18, 18), 0.0)
        clouds.append(CloudPuff(pos, r, neon, seed=rng.randint(0, 1<<30), drift=drift))

    tornados = []
    for _ in range(TORNADO_COUNT):
        ang = rng.uniform(0, (math.pi * 2.0))
        rr = rng.uniform(*TORNADO_RING)
        base = Vector3(player.pos.x + math.cos(ang)*rr, player.pos.y + math.sin(ang)*rr, 0.0)
        tornados.append(Tornado(rng, base))

    for i in range(OCEAN_WARSHIP_COUNT):
        ang = rng.uniform(0, math.pi * 2.0)
        rr = rng.uniform(*OCEAN_WARSHIP_RING)
        center = Vector3(player.pos.x + math.cos(ang) * rr, player.pos.y + math.sin(ang) * rr, 0.0)
        warships.append(OceanWarship(i, rng, center))
    heli_spawn_t = rng.uniform(*OCEAN_HELI_SPAWN_RANGE)

    # Stars: directions in camera-space
    stars = []
    for _ in range(STAR_COUNT):
        u = rng.random()
        v = rng.random()
        theta = (math.pi * 2.0) * u
        phi = math.acos(2.0*v - 1.0)
        x = math.sin(phi) * math.cos(theta)
        y = math.sin(phi) * math.sin(theta)
        z = math.cos(phi)
        if z < 0.10:  # bias to be mostly in front of camera
            z = abs(z) + 0.15
        stars.append((Vector3(x, y, z).normalize(), rng.uniform(0.5, 1.0), rng.random(), rng.randint(0,3)))

    t_now = 0.0
    target_index = 0

    # Player starts with laser machine guns (player-only), R cycles into global modes.
    mode_i = -1
    mode = PLAYER_DEFAULT_WEAPON
    mode_flash_t = 0.0

    planets = []
    for _ in range(4):
        center = Vector3(rng.uniform(-1800, 1800), rng.uniform(2200, 3800), rng.uniform(900, 1600))
        planets.append(Planet(rng, center, radius=rng.uniform(120, 280)))
    black_hole = BlackHole(rng, Vector3(rng.uniform(-900, 900), rng.uniform(3600, 5200), rng.uniform(1200, 1700)))

    next_bomb_t = t_now + rng.uniform(BOMB_DROP_MIN, BOMB_DROP_MAX)

    mouse1 = False
    mouse3 = False
    bomb_pressed = False
    last_player_bomb = -999.0

    def _targetables():
        # Anything with .pos and .dead can be targeted by homing weapons.
        # Order is stable so cycling feels predictable.
        out = []
        if ocean_mode:
            out.extend([w for w in warships if not getattr(w, "dead", False)])
            out.extend([h for h in helicopters if not getattr(h, "dead", False)])
            return out
        out.extend([s for s in ships if not getattr(s, "is_player", False)])
        out.extend([u for u in ufos])
        for gm in _active_giants():
            out.append(gm)
        return out

    def current_target():
        nonlocal target_index
        lst = _targetables()
        if not lst:
            return None
        target_index = target_index % len(lst)
        for _ in range(len(lst)):
            t = lst[target_index]
            if not getattr(t, "dead", False):
                return t
            target_index = (target_index + 1) % len(lst)
        return None

    def cycle_target():
        nonlocal target_index
        lst = _targetables()
        if lst:
            target_index = (target_index + 1) % len(lst)

    def ocean_random_target():
        choices = [w for w in warships if not getattr(w, "dead", False)]
        if choices:
            return rng.choice(choices)
        choices = [h for h in helicopters if not getattr(h, "dead", False)]
        return (rng.choice(choices) if choices else None)

    if auto_mode == "foot":
        _apply_combat_mode(1)
    elif auto_mode == "ocean":
        _apply_combat_mode(2)
    else:
        _apply_combat_mode(0)

    def spawn_hit(pos: Vector3, base_neon, theme: str):
        if theme == "spark":
            col = base_neon
            count = 14
        elif theme == "ring":
            col = (0.10, 0.90, 1.0)
            count = 10
        elif theme == "burst":
            col = (1.00, 0.60, 0.10)
            count = 16
        else:
            col = (1.0, 1.0, 1.0)
            count = 12

        for _ in range(count):
            ang = rng.uniform(0, (math.pi * 2.0))
            sp = rng.uniform(55, 170)
            v = Vector3(math.sin(ang), math.cos(ang), rng.uniform(0.1, 1.0))
            v = safe_norm(v, Vector3(0,1,0)) * sp
            v.z += rng.uniform(60, 140)
            debris.append(Debris(pos, v, col, life=rng.uniform(0.35, 0.95), size=rng.uniform(0.4, 1.3)))
        explosions.append(Explosion(pos, col, radius=rng.uniform(8.0, 14.0), is_atomic=False))

    def spawn_explosion(pos: Vector3, neon, radius=28.0, is_atomic=False):
        explosions.append(Explosion(pos, neon, radius=radius, is_atomic=is_atomic))
# Chance to leave a burning spot (not always)
        if (not is_atomic) and rng.random() < 0.30:
            fires.append(Fire(pos + Vector3(rng.uniform(-4,4), rng.uniform(-4,4), 0.0),
                              radius=rng.uniform(10.0, 24.0),
                              life=rng.uniform(6.0, 11.0),
                              intensity=rng.uniform(0.6, 1.0)))
        frag_n = min(120 if is_atomic else 56, max(0, DEBRIS_CAP - len(debris)))
        for _ in range(frag_n):
            ang = rng.uniform(0, (math.pi * 2.0))
            sp = rng.uniform(90, 340) if is_atomic else rng.uniform(70, 230)
            v = Vector3(math.sin(ang), math.cos(ang), rng.uniform(0.2, 1.2))
            v = safe_norm(v, Vector3(0,1,0)) * sp
            v.z += rng.uniform(160, 330) if is_atomic else rng.uniform(80, 190)
            debris.append(Debris(pos + Vector3(rng.uniform(-2,2), rng.uniform(-2,2), rng.uniform(-2,2)), v, neon,
                                 life=rng.uniform(0.8, 2.1) if is_atomic else rng.uniform(0.6, 1.6),
                                 size=rng.uniform(0.8, 2.6) if is_atomic else rng.uniform(0.6, 1.8)))

    def apply_aoe_damage(center: Vector3, radius: float, base_damage: int):
        for s in ships:
            if s.dead:
                continue
            d = (s.pos - center).length()
            if d <= radius:
                dmg = int(base_damage * (1.0 - d / radius))
                if dmg > 0:
                    s.take_damage(dmg, t_now)
        for u in ufos:
            if u.dead:
                continue
            d = (u.pos - center).length()
            if d <= radius:
                dmg = int(base_damage * (1.0 - d / radius))
                if dmg > 0:
                    u.take_damage(dmg, t_now)

        # Giant robots
        for gm in _active_giants():
            mc = gm.pos + Vector3(0.0, 0.0, gm.h * 0.55)
            d = (mc - center).length()
            if d <= radius:
                dmg = int(base_damage * (1.0 - d / radius))
                if dmg > 0:
                    gm.take_damage(dmg, t_now)

        # Ground traffic (2D falloff; cheaper than full 3D)
        for gc in traffic.cars:
            if not getattr(gc, "alive", False):
                continue
            dx = gc.pos.x - center.x
            dy = gc.pos.y - center.y
            d = math.sqrt(dx*dx + dy*dy)
            if d <= radius:
                dmg = int(base_damage * 0.55 * (1.0 - d / radius))
                if dmg > 0:
                    gc.take_damage(dmg)
    # ----------------------------
    # Destructible buildings: FX + collision helpers
    # ----------------------------
    def collapse_building(bld, hard: bool = False, atomic: bool = False):
        # bld may already be removed from city lists; we only need its cached dimensions/colors.
        center = Vector3(float(bld.cx), float(bld.cy), 0.0)
        # scale blast by footprint; clamp for perf and readability
        base = max(float(getattr(bld, "w", 10.0)), float(getattr(bld, "d", 10.0)))
        rad = clamp(base * (3.8 if hard else 2.6), 18.0, 105.0)
        neon = getattr(bld, 'neon', (1.0, 1.0, 1.0))
        explosions.append(Explosion(center, neon, radius=rad * (1.4 if atomic else 1.0), is_atomic=atomic))

        # Chance to leave a burning spot (not always)
        if (not atomic) and rng.random() < (0.55 if hard else 0.30):
            fires.append(Fire(center + Vector3(rng.uniform(-5, 5), rng.uniform(-5, 5), 0.0),
                              radius=rng.uniform(14.0, 34.0) * (1.25 if hard else 1.0),
                              life=rng.uniform(7.0, 15.0) * (1.25 if hard else 1.0),
                              intensity=rng.uniform(0.6, 1.0)))

        # Debris budget cap (prevents runaway memory/cpu in long fights)
        cap = DEBRIS_CAP
        if len(debris) >= cap:
            return
        n = (70 if atomic else (44 if hard else 28))
        for _ in range(n):
            if len(debris) >= cap:
                break
            ang = rng.uniform(0, (math.pi * 2.0))
            sp = rng.uniform(140, 420) if atomic else (rng.uniform(120, 320) if hard else rng.uniform(80, 240))
            v = Vector3(math.sin(ang), math.cos(ang), rng.uniform(0.2, 1.2))
            v = safe_norm(v, Vector3(0, 1, 0)) * sp
            v.z += rng.uniform(200, 420) if atomic else (rng.uniform(160, 320) if hard else rng.uniform(90, 220))
            zoff = rng.uniform(0.0, float(getattr(bld, "h", 60.0)) * 0.25)
            debris.append(Debris(center + Vector3(rng.uniform(-3, 3), rng.uniform(-3, 3), zoff),
                                 v, neon,
                                 life=rng.uniform(0.9, 2.2) if atomic else rng.uniform(0.7, 1.6),
                                 size=rng.uniform(0.9, 2.8) if atomic else rng.uniform(0.7, 2.2)))

    def handle_ship_building_collisions(ship: Ship):
        if ship.dead:
            return
        # Fast reject: most flight happens above typical skyline
        if ship.pos.z > 220.0:
            return

        cand = city.nearby_buildings(ship.pos.x, ship.pos.y, radius_chunks=1)
        for bld in cand:
            if not getattr(bld, "alive", True):
                continue
            # AABB check with a little padding so it "feels" like you clipped something solid
            if ship.pos.z > (bld.h + ship.radius * 0.90):
                continue
            if abs(ship.pos.x - bld.cx) <= (bld.w + ship.radius) and abs(ship.pos.y - bld.cy) <= (bld.d + ship.radius):
                spd = ship.vel.length()
                impact = int(clamp(220.0 + spd * 60.0, 180.0, 2800.0))
                destroyed = city.damage_building(bld, impact)

                # Ship damage is meaningful but not instantly fatal on light bumps.
                ship.take_damage(int(impact * (0.55 if ship.is_player else 0.70)), t_now)
                spawn_hit(Vector3(ship.pos.x, ship.pos.y, clamp(ship.pos.z, 2.0, bld.h)), ship.neon, "burst")

                if destroyed:
                    collapse_building(bld, hard=True)

                # Push ship out to prevent repeated damage while overlapping.
                nx = ship.pos.x - bld.cx
                ny = ship.pos.y - bld.cy
                if abs(nx) > abs(ny):
                    ship.pos.x = bld.cx + (bld.w + ship.radius + 2.5) * (1.0 if nx >= 0.0 else -1.0)
                    ship.vel.x *= -0.28
                else:
                    ship.pos.y = bld.cy + (bld.d + ship.radius + 2.5) * (1.0 if ny >= 0.0 else -1.0)
                    ship.vel.y *= -0.28
                ship.vel *= 0.68
                break

    def handle_traffic_building_collisions():
        # Ground traffic is meant to stay on streets, but when chaos happens, let it smash through.
        for gc in traffic.cars:
            if not getattr(gc, "alive", False):
                continue
            cand = city.nearby_buildings(gc.pos.x, gc.pos.y, radius_chunks=1)
            for bld in cand:
                if not getattr(bld, "alive", True):
                    continue
                if abs(gc.pos.x - bld.cx) <= (bld.w + 1.4) and abs(gc.pos.y - bld.cy) <= (bld.d + 1.4):
                    impact = int(180 + getattr(gc, "speed", 40.0) * 18.0)
                    destroyed = city.damage_building(bld, impact)
                    gc.take_damage(int(TRAFFIC_HP * 0.80))
                    spawn_hit(Vector3(gc.pos.x, gc.pos.y, 1.2), gc.neon, "spark")
                    if destroyed:
                        collapse_building(bld, hard=False)
                    # Optional car explosion when it fully dies is already handled elsewhere (bullet collisions).
                    break

    
    def handle_mech_building_collisions():
        # Each giant can bulldoze structures just by walking through them.
        for mech in _active_giants():
            cand = city.nearby_buildings(mech.pos.x, mech.pos.y, radius_chunks=2)
            for bld in cand:
                if not getattr(bld, "alive", True):
                    continue
                if abs(mech.pos.x - bld.cx) <= (float(bld.w) + mech.radius) and abs(mech.pos.y - bld.cy) <= (float(bld.d) + mech.radius):
                    impact = int(1200 + MECH_SPEED * 120.0) * (1.25 if getattr(mech, "kind", "") == "godzilla" else 1.0)
                    destroyed = city.damage_building(bld, impact)
                    spawn_hit(Vector3(float(bld.cx), float(bld.cy), min(float(getattr(bld, "h", 30.0)), mech.h*0.65)), bld.neon, "burst")
                    if destroyed:
                        # Big smash blast for giants (especially kaiju)
                        collapse_building(bld, hard=True)
                        explosions.append(Explosion(Vector3(float(bld.cx), float(bld.cy), 0.0), mech.neon,
                                                    radius=130.0 * float(getattr(mech, "scale", 1.0)),
                                                    is_atomic=True))

    def handle_mech_vehicle_collisions():
        # Giants smash ships/UFOs that skim too low, and crush ground vehicles.
        for mech in _active_giants():
            for s in ships:
                if getattr(s, "dead", False):
                    continue
                dx = s.pos.x - mech.pos.x
                dy = s.pos.y - mech.pos.y
                r = mech.radius + float(getattr(s, "radius", 6.0))
                if (dx*dx + dy*dy) < (r*r) and s.pos.z < (mech.h + 10.0):
                    impact = int(320 + min(520.0, float(getattr(s, "vel", Vector3(0,0,0)).length()) * 22.0))
                    s.take_damage(impact, t_now)
                    spawn_hit(s.pos, s.neon, "burst")
                    away = safe_norm(Vector3(dx, dy, 0.0), Vector3(1, 0, 0))
                    try:
                        s.vel += away * 55.0
                    except Exception:
                        pass

            for u in ufos:
                if getattr(u, "dead", False):
                    continue
                dx = u.pos.x - mech.pos.x
                dy = u.pos.y - mech.pos.y
                r = mech.radius + float(getattr(u, "radius", 6.0))
                if (dx*dx + dy*dy) < (r*r) and u.pos.z < (mech.h + 10.0):
                    impact = int(260 + min(420.0, float(getattr(u, "vel", Vector3(0,0,0)).length()) * 18.0))
                    u.take_damage(impact, t_now)
                    spawn_hit(u.pos, u.neon, "prism")
                    away = safe_norm(Vector3(dx, dy, 0.0), Vector3(1, 0, 0))
                    u.vel += away * 45.0

            for gc in traffic.cars:
                if not getattr(gc, "alive", False):
                    continue
                dx = gc.pos.x - mech.pos.x
                dy = gc.pos.y - mech.pos.y
                if (dx*dx + dy*dy) < ((mech.radius + 3.2) * (mech.radius + 3.2)):
                    alive = gc.take_damage(9999)
                    spawn_hit(Vector3(gc.pos.x, gc.pos.y, 1.2), gc.neon, "burst")
                    if not alive:
                        explosions.append(Explosion(Vector3(gc.pos.x, gc.pos.y, 1.2), gc.neon, radius=22.0, is_atomic=False))
    def space_factor_for_alt(z):
        # 0 below ~160; 1 at/above ~760
        return clamp((z - 160.0) / 600.0, 0.0, 1.0)

    running = True

    quit_confirm = False  # ESC opens confirmation; ESC again quits (N cancels)
    while running:
        if hv_runtime is not None:
            hv_runtime.poll_embedded_escape_hold()
        dt = clock.tick(FPS) / 1000.0
        if quit_confirm:
            dt = 0.0
        dt = clamp(dt, 0.0, 1/30)
        t_now += dt

        if AUDIO is not None:
            AUDIO.set_listener(player.pos)
            AUDIO.maybe_rescan(t_now)
            AUDIO.process_pending()

            # Very low background battle bed that grows as you approach combat,
            # but never surpasses player weapon/hit loudness.
            if t_now >= battle_amb_next:
                # Find nearest active combat source.
                best_p = None
                best_d2 = 1e18
                for s in ships:
                    if getattr(s, 'dead', False) or getattr(s, 'is_player', False):
                        continue
                    d2 = (s.pos.x-player.pos.x)**2 + (s.pos.y-player.pos.y)**2 + (s.pos.z-player.pos.z)**2
                    if d2 < best_d2:
                        best_d2 = d2
                        best_p = s.pos
                for u in ufos:
                    if getattr(u, 'dead', False):
                        continue
                    d2 = (u.pos.x-player.pos.x)**2 + (u.pos.y-player.pos.y)**2 + (u.pos.z-player.pos.z)**2
                    if d2 < best_d2:
                        best_d2 = d2
                        best_p = u.pos
                for g in giants:
                    if g is None or getattr(g, 'dead', False):
                        continue
                    # giants live at ground level; use small Z.
                    gpz = 6.0
                    d2 = (g.pos.x-player.pos.x)**2 + (g.pos.y-player.pos.y)**2 + (gpz-player.pos.z)**2
                    if d2 < best_d2:
                        best_d2 = d2
                        best_p = Vector3(g.pos.x, g.pos.y, gpz)

                if best_p is not None and best_d2 < (2200.0**2):
                    AUDIO.play_positional('ambient/battle', best_p, base=0.14, near=420.0, max_dist=1800.0,
                                         cooldown=1.4, key='battle_bed', echo=True, echo_gain=0.12)
                    battle_amb_next = t_now + 1.25
                else:
                    battle_amb_next = t_now + 2.25

        if holoverse_return_signal_requested():
            running = False
            break

        jump_pressed = False
        for ev in pygame.event.get():
            if hv_runtime is not None and hv_runtime.pygame_embedded_escape_event(ev):
                continue
            if ev.type == pygame.VIDEORESIZE:
                # Resize the OS window; internal canvas stays BASE_WxBASE_H.
                win_w = max(640, int(getattr(ev, "w", 0) or 0))
                win_h = max(360, int(getattr(ev, "h", 0) or 0))
                if win_w <= 0 or win_h <= 0:
                    continue
                display = _set_display_mode(win_w, win_h)
                view_scale, view_size, view_off = _compute_viewport(win_w, win_h)
                if view_size == (BASE_W, BASE_H):
                    scaled_frame = None
                else:
                    if (scaled_frame is None) or (scaled_frame.get_size() != view_size):
                        scaled_frame = pygame.Surface(view_size).convert()
                # Re-apply mouse lock state; some window managers drop grab on resize.
                _set_mouse_lock(mouse_locked)
                continue

            if ev.type == pygame.QUIT:
                running = False
            elif ev.type == pygame.KEYDOWN:
                # Quit confirmation: ESC opens a modal confirmation, ESC again quits.
                if quit_confirm:
                    if ev.key in (pygame.K_ESCAPE, pygame.K_y, pygame.K_RETURN, pygame.K_KP_ENTER):
                        running = False
                    elif ev.key in (pygame.K_n, pygame.K_BACKSPACE):
                        quit_confirm = False
                    # Swallow other inputs while the confirm is up.
                    continue

                if ev.key == pygame.K_ESCAPE:
                    quit_confirm = True
                elif ev.key == pygame.K_F1:
                    _set_mouse_lock(not mouse_locked)
                elif ev.key == pygame.K_TAB:
                    try:
                        _next_combat_mode = {1: 0, 0: 2, 2: 1}.get(combat_mode, 1)
                        _apply_combat_mode(_next_combat_mode)
                    except Exception as e:
                        combat_mode = 1
                        ground_assault = True
                        ocean_mode = False
                        try:
                            _write_crash_report(e)
                        except Exception:
                            pass
                elif ev.key == pygame.K_t:
                    cycle_target()
                elif ev.key == pygame.K_r:
                    mode_i = (mode_i + 1) % len(WEAPON_MODES)
                    mode = WEAPON_MODES[mode_i]
                    mode_flash_t = 0.85
                elif ev.key == pygame.K_v:
                    player.apply_variant(player.variant_index + 1)
                    mode_flash_t = 0.85
                elif ev.key == pygame.K_SPACE:
                    jump_pressed = True
                elif ev.key == pygame.K_b:
                    bomb_pressed = True
            elif ev.type == pygame.MOUSEBUTTONDOWN:
                if ev.button == 1: mouse1 = True
                if ev.button == 3: mouse3 = True
            elif ev.type == pygame.MOUSEBUTTONUP:
                if ev.button == 1: mouse1 = False
                if ev.button == 3: mouse3 = False
            elif ev.type == pygame.MOUSEWHEEL:
                # v3.2: horizontal wheel / trackpad scroll turns BOTH camera aim + ship aim.
                # Pygame 2 uses ev.x for horizontal scroll (left negative, right positive).
                if getattr(ev, "x", 0) != 0:
                    step = 7.5  # degrees per notch
                    aim_yaw += (step if ev.x < 0 else -step)

        keys = pygame.key.get_pressed()

        # ----------------------------
        # Player flight model (stiffer mouse-turn + hover + vertical control)
        # - Mouse: yaw + pitch (immediate; less lag)
        # - W / Up: forward throttle
        # - S / Down: reverse / brake
        # - Shift: acceleration / higher top speed
        # - Space: jump boost (impulse)
        # - No throttle keys: hover (velocity damped toward 0)
        # - LALT: thruster up, LCTRL: thruster down
        # - Q/E: roll
        # ----------------------------
        mx, my = pygame.mouse.get_rel()

        # v3.2 Aim handling:
        # - Update aim orientation immediately from mouse/keys.
        # - Drive the ship toward aim using the same rate limits (feels precise, not laggy).
        aim_yaw += (mx * MOUSE_SENS_YAW)
        pitch_lim = 4.0 if ocean_mode else (12.0 if ground_assault else 78.0)
        aim_pitch = clamp(aim_pitch + (my * MOUSE_SENS_PITCH), -pitch_lim, pitch_lim)  # mouse up -> pitch up

        # Keyboard yaw assist (already swapped L/R per your request)
        if keys[pygame.K_a] or keys[pygame.K_LEFT]:
            aim_yaw -= KEY_YAW_RATE * dt
        if keys[pygame.K_d] or keys[pygame.K_RIGHT]:
            aim_yaw += KEY_YAW_RATE * dt

        aim_yaw = angle_wrap_deg(aim_yaw)

        # Convert to normalized control inputs (what Ship.update expects)
        yaw = shortest_angle_deg(player.yaw, aim_yaw) / max(1e-4, (KEY_YAW_RATE * dt))
        pitch = shortest_angle_deg(player.pitch, aim_pitch) / max(1e-4, (KEY_PITCH_RATE * dt))
        roll = 0.0
        if keys[pygame.K_q]:
            roll += 1.0
        if keys[pygame.K_e]:
            roll -= 1.0

        # Clamp inputs to avoid extreme spikes on focus changes
        yaw = clamp(yaw, -4.0, 4.0)
        pitch = clamp(pitch, -4.0, 4.0)

        throttle = 0.0
        if ocean_mode:
            # Speedboat handling: maintain a healthy cruise speed even when not accelerating.
            if keys[pygame.K_w] or keys[pygame.K_UP]:
                throttle = 1.0
            elif keys[pygame.K_s] or keys[pygame.K_DOWN]:
                throttle = -0.25
            else:
                throttle = 0.38
        else:
            if keys[pygame.K_w] or keys[pygame.K_UP]:
                throttle = 1.0
            elif keys[pygame.K_s] or keys[pygame.K_DOWN]:
                throttle = -0.75

        boost = keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]
        hover = (abs(throttle) < 1e-6)

        vz = 0.0
        if keys[pygame.K_LALT] or keys[pygame.K_RALT]:
            vz += 1.0
        if keys[pygame.K_LCTRL] or keys[pygame.K_RCTRL]:
            vz -= 1.0

        ctrl = {"yaw": yaw, "pitch": pitch, "roll": roll, "boost": boost, "hover": hover, "throttle": throttle, "vz": vz, "jump": jump_pressed, "fire": mouse1, "missile": mouse3}

        # Streaming around player
        # Pre-stream the city a bit ahead of the player so buildings feel pre-generated
        pfwd_stream, _, _ = player.basis()
        look_x = player.pos.x + pfwd_stream.x * CITY_LOOKAHEAD
        look_y = player.pos.y + pfwd_stream.y * CITY_LOOKAHEAD
        city.stream_around(look_x, look_y, (player.pos.x, player.pos.y), (player.vel.x, player.vel.y), t_now, cam_fwd_xy=(pfwd_stream.x, pfwd_stream.y))

        # Ground traffic persists in streets; lightweight update + combat

        if not ocean_mode:
            traffic.update(dt, city, player, player.vel, bullets, missiles, explosions, debris, ground_assault, nearest_giant(player.pos))

        # Player update (kept fast; required for controls + camera + audio positioning)
        sf = space_factor_for_alt(player.pos.z)
        player.ground_mode = bool(ground_assault or ocean_mode)
        tgt = current_target()
        player.update(dt, t_now, ctrl, tgt, bullets, missiles, mode, rng, sf)

        # Ground / ocean ride constraints
        if ground_assault:
            target_z = 3.0
            z_err = target_z - player.pos.z
            player.vel.z += z_err * (18.0 * dt)
            player.vel.z *= math.exp(-dt / 0.10)
            player.pos.z += player.vel.z * dt
            if player.pos.z < 1.2:
                player.pos.z = 1.2
                player.vel.z = 0.0
            player.pitch = 0.0
            player.roll = 0.0
        elif ocean_mode:
            wave_h = ocean_wave_height(player.pos.x, player.pos.y, t_now)
            target_z = wave_h + OCEAN_PLAYER_RIDE
            z_err = target_z - player.pos.z
            surf_n = ocean_wave_normal(player.pos.x, player.pos.y, t_now)

            # Speedboat planar handling: yaw-led cruise, strong lateral damping, and wave-ramp pops.
            boat_fwd = safe_norm(Vector3(math.sin(math.radians(player.yaw)), math.cos(math.radians(player.yaw)), 0.0), Vector3(0, 1, 0))
            boat_right = safe_norm(Vector3(boat_fwd.y, -boat_fwd.x, 0.0), Vector3(1, 0, 0))
            planar = Vector3(player.vel.x, player.vel.y, 0.0)
            fspd = planar.dot(boat_fwd)
            sspd = planar.dot(boat_right)
            cruise_target = 78.0 + max(0.0, throttle) * 58.0 + (34.0 if boost else 0.0)
            if throttle < 0.0:
                cruise_target = max(14.0, fspd - 180.0 * dt)
            fspd = lerp(fspd, cruise_target, clamp(dt * 2.4, 0.0, 1.0))
            sspd *= (1.0 - clamp(dt * 4.8, 0.0, 0.88))
            slope_push = max(0.0, -(surf_n.x * boat_fwd.x + surf_n.y * boat_fwd.y))
            if slope_push > 0.35:
                player.vel.z += slope_push * (22.0 + max(0.0, fspd) * 0.018) * dt
            planar = boat_fwd * fspd + boat_right * sspd
            player.vel.x = planar.x
            player.vel.y = planar.y

            player.vel.z += z_err * (12.5 * dt)
            player.vel.z *= math.exp(-dt / 0.22)
            player.pos.z += player.vel.z * dt
            if player.pos.z < wave_h + 1.0:
                player.pos.z = wave_h + 1.0
                player.vel.z = max(0.0, player.vel.z)
            player.pitch = lerp(player.pitch, clamp(surf_n.y * 24.0 + min(7.0, max(0.0, fspd - 86.0) * 0.03), -7.0, 11.0), clamp(dt * 2.4, 0.0, 1.0))
            player.roll = lerp(player.roll, clamp(-surf_n.x * 38.0 - sspd * 0.12, -16.0, 16.0), clamp(dt * 2.2, 0.0, 1.0))

        if ocean_mode:
            # Ocean-mode secondary weapon: homing torpedo barrage against live warships.
            if mouse3 and (t_now - player.last_missile) >= player.missile_cd:
                torpedo_target = ocean_random_target()
                if torpedo_target is not None:
                    player.last_missile = t_now
                    launch_dir = safe_norm(Vector3(math.sin(math.radians(player.yaw)), math.cos(math.radians(player.yaw)), 0.0), Vector3(0,1,0))
                    torp_origin = player.pos + launch_dir * 4.0 + Vector3(0, 0, -1.2)
                    torp_dmg = rng.randint(*OCEAN_TORPEDO_DAMAGE)
                    torp_rad = rng.uniform(*OCEAN_TORPEDO_RADIUS)
                    missiles.append(Missile(player, torp_origin, launch_dir * OCEAN_TORPEDO_SPEED + player.vel * 0.18, torpedo_target, (0.20, 0.90, 1.00), torp_dmg, torp_rad, style_id=97))
                    if AUDIO is not None:
                        AUDIO.play_local('weapons/missiles', base=0.82, cooldown=0.20, key='player_torpedo')

            # Live ocean threats
            for ws in warships:
                ws.update(dt, t_now, player, bullets, missiles, rng)
            helicopters[:] = [h for h in helicopters if not getattr(h, 'dead', False)]
            heli_spawn_t -= dt
            if heli_spawn_t <= 0.0 and len(helicopters) < OCEAN_HELI_LIMIT:
                heli_spawn_t = rng.uniform(*OCEAN_HELI_SPAWN_RANGE)
                ang = rng.uniform(0.0, math.pi * 2.0)
                rr = rng.uniform(240.0, 520.0)
                helicopters.append(OceanHelicopter(len(helicopters) + int(t_now * 10.0), rng, Vector3(player.pos.x + math.cos(ang) * rr, player.pos.y + math.sin(ang) * rr, 0.0)))
            for heli in helicopters:
                heli.center.x = lerp(heli.center.x, player.pos.x, clamp(dt * 0.12, 0.0, 1.0))
                heli.center.y = lerp(heli.center.y, player.pos.y, clamp(dt * 0.12, 0.0, 1.0))
                heli.update(dt, t_now, player, bullets, missiles, rng)

        # Building collisions: player can smash through structures.
        if not ocean_mode:
            handle_ship_building_collisions(player)

        # Player respawn: if destroyed, spawn a fresh ship immediately (air and ground modes).
        if getattr(player, 'dead', False):
            try:
                vi = int(getattr(player, 'variant_index', 0))
            except Exception:
                vi = 0
            new_player = Ship(0, True, rng, variant_index=vi)
            # Spawn at last position; clamp to appropriate altitude.
            new_player.pos = Vector3(player.pos.x, player.pos.y, (3.0 if ground_assault else ((ocean_wave_height(player.pos.x, player.pos.y, t_now) + OCEAN_PLAYER_RIDE) if ocean_mode else max(120.0, float(player.pos.z)))))
            if ground_assault or ocean_mode:
                gx, gy = find_clear_ground_spot(new_player.pos.x, new_player.pos.y)
                new_player.pos.x, new_player.pos.y = gx, gy
                new_player.pos.z = (3.0 if ground_assault else (ocean_wave_height(gx, gy, t_now) + OCEAN_PLAYER_RIDE))
            new_player.vel = Vector3(0, 0, 0)
            new_player.yaw = float(aim_yaw)
            new_player.pitch = 0.0
            new_player.roll = 0.0
            # Swap in list index 0 to keep assumptions stable elsewhere.
            ships[0] = new_player
            player = new_player
            # Reset aim to the new ship so controls remain sane.
            aim_pitch = 0.0
            aim_yaw = float(player.yaw)
            # Optional: play a quiet destroy cue at the old location (never louder than player).
            if AUDIO is not None:
                AUDIO.play_positional('damage/destroy', Vector3(player.pos.x, player.pos.y, player.pos.z), base=0.10, near=240.0, max_dist=900.0, cooldown=0.80, key='p_respawn', echo=True, echo_gain=0.10)


        # AI ships / UFO brawl
        if not ocean_mode:
            for s in ships:
                if s.is_player:
                    continue
                if s.dead:
                    if random.random() < 0.006:
                        s.dead = False
                        s.hp = s.hp_max
                        s.shield = s.shield_max
                        s.pos = player.pos + Vector3(random.uniform(-220, 220), random.uniform(140, 320), random.uniform(55, 115))
                        s.vel = Vector3(0,0,0)
                        s.yaw = random.uniform(-180, 180)
                        s.pitch = random.uniform(-10, 10)
                        s.roll = random.uniform(-180, 180)
                    continue

                # Acquire nearest hostile (ships, UFOs, mech). This produces free-for-all chaos.
                candidates = []
                candidates.extend([p for p in ships if (not getattr(p, "dead", False)) and p is not s])
                candidates.extend([u for u in ufos if (not getattr(u, "dead", False))])
                for gm in _active_giants():
                    candidates.append(gm)

                tgt_obj = None
                best2 = 1e18
                sx, sy, sz = s.pos.x, s.pos.y, s.pos.z
                for cand in candidates:
                    dx = cand.pos.x - sx
                    dy = cand.pos.y - sy
                    dz = cand.pos.z - sz
                    d2 = dx*dx + dy*dy + dz*dz
                    if d2 < best2:
                        best2 = d2
                        tgt_obj = cand

                if tgt_obj is None:
                    continue

                to = (tgt_obj.pos - s.pos)
                dist = max(1e-6, to.length())
                dirv = to / dist

                desired_yaw = math.degrees(math.atan2(dirv.x, dirv.y))
                desired_pitch = -math.degrees(math.asin(clamp(dirv.z, -1.0, 1.0)))
                s.yaw = lerp_angle_deg(s.yaw, desired_yaw, clamp(1.18*dt, 0.0, 1.0))
                s.pitch = lerp(s.pitch, clamp(desired_pitch, -52, 52), clamp(1.05*dt, 0.0, 1.0))
                s.roll = (s.roll + math.sin(t_now * 1.3 + s.sid) * (60.0 + 20.0*sf) * dt) % 360.0

                fwd, _, _ = s.basis()
                want_boost = dist > 130.0
                want_hover = dist < 58.0
                dot = fwd.dot(dirv)
                fire = dot > 0.985 and dist < 290.0 and random.random() < 0.92
                fire_missile = dot > 0.970 and dist < 210.0 and (t_now - s.last_missile) > s.missile_cd and random.random() < 0.20

                ai_ctrl = {"yaw": 0.0, "pitch": 0.0, "roll": 0.0, "boost": want_boost, "hover": want_hover, "fire": fire, "missile": fire_missile}
                ai_mode = WEAPON_MODES[s.sid % len(WEAPON_MODES)]
                s.update(dt, t_now, ai_ctrl, tgt_obj, bullets, missiles, ai_mode, rng, sf)
                handle_ship_building_collisions(s)

            # UFOs
            for u in ufos:
                if u.dead:
                    if random.random() < 0.0035:
                        u.dead = False
                        u.hp = u.hp_max
                        u.shield = u.shield_max
                        u.pos = player.pos + Vector3(random.uniform(-320, 320), random.uniform(180, 460), random.uniform(90, 170))
                    continue
                # UFOs also participate in the brawl: pick nearest hostile target.
                ucands = []
                ucands.extend([s for s in ships if not getattr(s, "dead", False)])
                for gm in _active_giants():
                    ucands.append(gm)

                utgt = None
                best2 = 1e18
                ux, uy, uz = u.pos.x, u.pos.y, u.pos.z
                for cand in ucands:
                    dx = cand.pos.x - ux
                    dy = cand.pos.y - uy
                    dz = cand.pos.z - uz
                    d2 = dx*dx + dy*dy + dz*dz
                    if d2 < best2:
                        best2 = d2
                        utgt = cand
                u.update(dt, t_now, utgt, beams, rng)

        # Projectiles update + collisions
        bullets = [b for b in bullets if b.update(dt)]

        for b in list(bullets):
            hit = False

            # Water projectiles extinguish fires
            if b.style_id == 77 and fires:
                for f in list(fires):
                    if (f.pos - b.pos).length() < (f.radius * 0.55 + 2.5):
                        f.douse(0.60)
                        spawn_hit(b.pos, (140, 200, 255), "spark")
                        bullets.remove(b)
                        hit = True
                        break
                if hit:
                    continue

            # Ships
            for s in ships:
                if s.dead or s is b.owner:
                    continue
                if (s.pos - b.pos).length() < (s.radius + 1.0):
                    s.take_damage(b.dmg, t_now)
                    spawn_hit(b.pos, s.neon, mode["impact_theme"] if getattr(b.owner, "is_player", False) else "spark")
                    bullets.remove(b)
                    hit = True
                    break
            if hit:
                continue

            # Giant robots
            if b in bullets:
                for gm in _active_giants():
                    if b.owner is gm:
                        continue
                    if gm.hit_test(b.pos, pad_xy=3.0, pad_z=8.0):
                        gm.take_damage(b.dmg, t_now)
                        spawn_hit(b.pos, gm.neon, "spark")
                        bullets.remove(b)
                        hit = True
                        break

            if hit:
                continue

            # Ocean targets
            if b in bullets:
                for ws in warships:
                    if getattr(ws, "dead", False) or ws is b.owner:
                        continue
                    if (ws.pos - b.pos).length() < (ws.length * 0.45 + 2.2):
                        ws.take_damage(b.dmg, t_now)
                        spawn_hit(b.pos, ws.neon, "burst")
                        bullets.remove(b)
                        hit = True
                        if ws.dead:
                            spawn_explosion(ws.pos, ws.neon, radius=48.0, is_atomic=False)
                        break
            if hit:
                continue
            if b in bullets:
                for heli in helicopters:
                    if getattr(heli, "dead", False) or heli is b.owner:
                        continue
                    if (heli.pos - b.pos).length() < 5.5:
                        heli.take_damage(b.dmg, t_now)
                        spawn_hit(b.pos, heli.neon, "spark")
                        bullets.remove(b)
                        hit = True
                        if heli.dead:
                            spawn_explosion(heli.pos, heli.neon, radius=30.0, is_atomic=False)
                        break
            if hit:
                continue

# UFOs
            for u in ufos:
                if u.dead:
                    continue
                if (u.pos - b.pos).length() < (u.radius + 1.0):
                    u.take_damage(b.dmg, t_now)
                    spawn_hit(b.pos, u.neon, "prism")
                    bullets.remove(b)
                    hit = True
                    break
            if hit:
                continue

            # Ground traffic collisions (kept cheap: 2D distance on x/y, small height window)
            # NOTE: ground cars fire style_id=2 bullets; ships can also hit them.
            if b in bullets:
                for gc in traffic.cars:
                    if (not getattr(gc, "alive", False)) or gc is b.owner:
                        continue
                    dx = gc.pos.x - b.pos.x
                    dy = gc.pos.y - b.pos.y
                    # treat cars as ~2.4m radius on ground plane
                    if (dx*dx + dy*dy) < (2.4*2.4) and abs(b.pos.z - 1.2) < 3.0:
                        alive = gc.take_damage(b.dmg)
                        spawn_hit(Vector3(gc.pos.x, gc.pos.y, 1.2), gc.neon, "spark")
                        bullets.remove(b)
                        if not alive:
                            # explosion + debris (performance-safe: capped)
                            explosions.append(Explosion(Vector3(gc.pos.x, gc.pos.y, 1.2), gc.neon, radius=18.0, is_atomic=False))
                            if len(debris) < DEBRIS_CAP:
                                rng2 = random.Random((gc.rng_seed ^ 0xC0FFEE) & 0xFFFFFFFF)
                                for _ in range(10):
                                    dv = Vector3(rng2.uniform(-55, 55), rng2.uniform(-55, 55), rng2.uniform(18, 75))
                                    debris.append(Debris(Vector3(gc.pos.x, gc.pos.y, 1.4), dv, gc.neon, life=rng2.uniform(0.7, 1.2), size=rng2.uniform(0.5, 1.1)))
                        hit = True
                        break
            if hit:
                continue

            # Buildings (chunk-local scan; cheap even with large skylines)
            if (not ocean_mode) and b in bullets and b.pos.z <= 220.0:
                cand = city.nearby_buildings(b.pos.x, b.pos.y, radius_chunks=1)
                for bd in cand:
                    if not getattr(bd, "alive", True):
                        continue
                    # AABB + height test (good enough for wireframe buildings)
                    if city.hit_test(bd, b.pos, pad_xy=1.2, pad_z=6.0):
                        destroyed = city.damage_building(bd, b.dmg)
                        spawn_hit(b.pos, bd.neon, "spark")
                        bullets.remove(b)
                        if destroyed:
                            collapse_building(bd, hard=False)
                        break

        # Missiles update + collisions (single update per frame; avoids time-dilation bugs)
        missiles = [m for m in missiles if m.update(dt)]
        for m in list(missiles):
            hit_any = False

            for s in ships:
                if s.dead or s is m.owner:
                    continue
                if (s.pos - m.pos).length() < (s.radius + 3.0):
                    hit_any = True
                    break

            if not hit_any:
                for u in ufos:
                    if u.dead or u is m.owner:
                        continue
                    if (u.pos - m.pos).length() < (u.radius + 3.0):
                        hit_any = True
                        break

            if not hit_any:
                for gm in _active_giants():
                    # test against torso center
                    mc = gm.pos + Vector3(0.0, 0.0, gm.h * 0.55)
                    if (mc - m.pos).length() < (gm.radius + 6.0):
                        hit_any = True
                        break

            if not hit_any:
                for ws in warships:
                    if getattr(ws, "dead", False) or ws is m.owner:
                        continue
                    if (ws.pos - m.pos).length() < (ws.length * 0.55 + 5.0):
                        hit_any = True
                        break
            if not hit_any:
                for heli in helicopters:
                    if getattr(heli, "dead", False) or heli is m.owner:
                        continue
                    if (heli.pos - m.pos).length() < 7.0:
                        hit_any = True
                        break

            if hit_any or m.t >= m.life:
                for s in ships:
                    if s.dead:
                        continue
                    d = (s.pos - m.pos).length()
                    if d <= m.radius:
                        dmg = int(m.dmg * (1.0 - d / m.radius))
                        if dmg > 0:
                            s.take_damage(dmg, t_now)
                            spawn_hit(s.pos, s.neon, "burst")

                for u in ufos:
                    if u.dead:
                        continue
                    d = (u.pos - m.pos).length()
                    if d <= m.radius:
                        dmg = int(m.dmg * (1.0 - d / m.radius))
                        if dmg > 0:
                            u.take_damage(dmg, t_now)
                            spawn_hit(u.pos, u.neon, "prism")
                # Giant robots take AOE damage too
                for gm in _active_giants():
                    mc = gm.pos + Vector3(0.0, 0.0, gm.h * 0.55)
                    d = (mc - m.pos).length()
                    if d <= m.radius:
                        dmg = int(m.dmg * (1.0 - d / m.radius))
                        if dmg > 0:
                            gm.take_damage(dmg, t_now)
                            spawn_hit(mc, gm.neon, "spark")

                for ws in warships:
                    if getattr(ws, "dead", False):
                        continue
                    d = (ws.pos - m.pos).length()
                    if d <= (m.radius + ws.width * 0.55):
                        dmg = int(m.dmg * max(0.0, 1.0 - d / (m.radius + ws.width * 0.55)))
                        if dmg > 0:
                            ws.take_damage(dmg, t_now)
                            spawn_hit(ws.pos, ws.neon, "burst")
                            if ws.dead:
                                spawn_explosion(ws.pos, ws.neon, radius=52.0, is_atomic=False)
                for heli in helicopters:
                    if getattr(heli, "dead", False):
                        continue
                    d = (heli.pos - m.pos).length()
                    if d <= (m.radius + 6.0):
                        dmg = int(m.dmg * max(0.0, 1.0 - d / (m.radius + 6.0)))
                        if dmg > 0:
                            heli.take_damage(dmg, t_now)
                            spawn_hit(heli.pos, heli.neon, "spark")
                            if heli.dead:
                                spawn_explosion(heli.pos, heli.neon, radius=30.0, is_atomic=False)

                # Ground traffic takes blast damage (cheap 2D)
                for gc in traffic.cars:
                    if not getattr(gc, "alive", False):
                        continue
                    dx = gc.pos.x - m.pos.x
                    dy = gc.pos.y - m.pos.y
                    d = math.sqrt(dx*dx + dy*dy)
                    if d <= m.radius:
                        dmg = int(m.dmg * 0.65 * (1.0 - d / m.radius))
                        if dmg > 0:
                            alive = gc.take_damage(dmg)
                            spawn_hit(Vector3(gc.pos.x, gc.pos.y, 1.2), gc.neon, "burst")
                            if not alive:
                                explosions.append(Explosion(Vector3(gc.pos.x, gc.pos.y, 1.2), gc.neon, radius=18.0, is_atomic=False))

                # Buildings: blast radius collapses nearby structures
                if not ocean_mode:
                    destroyed = city.damage_buildings_aoe(m.pos.x, m.pos.y, m.radius + 10.0, float(m.dmg) * 9.0)
                    for db in destroyed:
                        collapse_building(db, hard=True)

                spawn_explosion(m.pos, m.color, radius=38.0, is_atomic=False)
                missiles.remove(m)
        for s in ships:
            if (not s.dead) and s.hp <= 0:
                s.dead = True
                spawn_explosion(s.pos, s.neon, radius=44.0)
        for u in ufos:
            if (not u.dead) and u.hp <= 0:
                u.dead = True
                spawn_explosion(u.pos, u.neon, radius=54.0)

        for s in ships:
            s.trail.update(dt)
            s.trail2.update(dt)
        for u in ufos:
            u.trail.update(dt)

        explosions = [e for e in explosions if e.update(dt)]
        debris = [d for d in debris if d.update(dt)]
        beams = [bm for bm in beams if bm.update(dt)]
        fires = [f for f in fires if f.update(dt)]

        # Active object caps.  These protect all modes from long-session VFX/projectile creep.
        _trim_list_in_place(bullets, BULLET_CAP)
        _trim_list_in_place(missiles, MISSILE_CAP)
        _trim_list_in_place(debris, DEBRIS_CAP)
        _trim_list_in_place(explosions, EXPLOSION_CAP)
        _trim_list_in_place(fires, FIRE_CAP)

        # Camera chase (v3.2)
        # - Camera LOOKS where you aim (aim_yaw/aim_pitch) immediately.
        # - Camera POSITION holds its "behind-ship" direction until the ship has mostly aligned,
        #   preventing the camera from yanking around while the ship is still turning.
        pfwd_ship, pright_ship, pup_ship = player.basis()
        cam_fwd, cam_right, cam_up = basis_from_ypr_deg(aim_yaw, aim_pitch, 0.0)

        yaw_err = abs(shortest_angle_deg(player.yaw, aim_yaw))
        pitch_err = abs(shortest_angle_deg(player.pitch, aim_pitch))
        aligned = (yaw_err < 8.0 and pitch_err < 6.0)

        # Update chase_dir slowly when misaligned; quickly when aligned.
        tau = 0.18 if aligned else 0.85
        chase_dir = chase_dir.lerp(pfwd_ship, 1.0 - math.exp(-dt / max(1e-4, tau)))
        chase_dir = safe_norm(chase_dir, pfwd_ship)

        if ground_assault:
            cam_target = player.pos - chase_dir * 18.0 + cam_up * 6.0
            cam.pos = cam.pos.lerp(cam_target, 1.0 - math.exp(-dt / 0.10))
        elif ocean_mode:
            cam_target = player.pos - chase_dir * 22.0 + cam_up * 7.2
            cam.pos = cam.pos.lerp(cam_target, 1.0 - math.exp(-dt / 0.12))
        else:
            cam.pos = cam.pos.lerp(player.pos - chase_dir * 26.0 + cam_up * 10.0, 1.0 - math.exp(-dt / 0.14))

        # ----------------------------
        # Render
        # ----------------------------
        screen.blit(sky_bg, (0, 0))
        solid.fill((0, 0, 0, 0))
        glow.fill((0, 0, 0, 0))
        ui.fill((0, 0, 0, 0))

        # Visual fades for "space flight"
        city_alpha = int(lerp(255, 35, sf))
        grid_alpha = int(lerp(70, 10, sf))
        cloud_alpha = int(lerp(160, 0, clamp((sf - 0.15) / 0.50, 0, 1)))
        star_alpha = int(lerp(60, 220, clamp((sf - 0.10) / 0.85, 0, 1)))

        # Mode readability tuning
        if ground_assault:
            city_alpha = 255
            grid_alpha = 235
            cloud_alpha = 0
            star_alpha = 55
        elif ocean_mode:
            city_alpha = 0
            grid_alpha = 255
            cloud_alpha = 0
            star_alpha = 40


        # STARFIELD (camera-space sphere)
        # stars exist "around" the camera: construct a far point in world and project
        far = 6200.0
        twk = 0.0
        for d, mag, phase, tint in stars:
            twk = 0.70 + 0.30 * math.sin(t_now * (0.9 + mag*0.8) + phase * (math.pi * 2.0))
            a = int(star_alpha * twk * (0.65 + 0.35*mag))
            # choose subtle tint (mostly white)
            if tint == 0:
                c = (1.0, 1.0, 1.0)
            elif tint == 1:
                c = (0.70, 0.85, 1.0)
            elif tint == 2:
                c = (1.0, 0.85, 0.75)
            else:
                c = (0.90, 0.95, 1.0)
            p = cam.pos + cam_right * (d.x * far) + cam_up * (d.y * far) + cam_fwd * (abs(d.z) * far)
            pr = cam.project(p, cam_fwd, cam_right, cam_up)
            if pr:
                x, y = int(pr[0]), int(pr[1])
                if 0 <= x < W and 0 <= y < H:
                    # tiny star point
                    glow.set_at((x, y), rgbf_to_rgbi(c, a))
                    if mag > 0.92 and a > 60:
                        pygame.draw.circle(glow, rgbf_to_rgbi(c, int(a*0.35)), (x, y), 2, 0)

        # SKY objects (planets + black hole) – parallax with player
        par = Vector3(player.pos.x * 0.015, player.pos.y * 0.015, 0.0)
        for pl in planets:
            c = pl.center + par
            pc = cam.project(c, cam_fwd, cam_right, cam_up)
            if pc:
                rim = cam.project(c + cam_right * pl.radius, cam_fwd, cam_right, cam_up)
                if rim:
                    r2d = abs(rim[0] - pc[0])
                    # Solid black planet body to match the city's "mass" look.
                    # (Removed) no filled planet body; rings only (avoid black interior)
                    pygame.draw.circle(glow, rgbf_to_rgbi(pl.color, 70), (int(pc[0]), int(pc[1])), int(r2d), 1)
                    pygame.draw.circle(glow, rgbf_to_rgbi(pl.color, 140), (int(pc[0]), int(pc[1])), max(1, int(r2d*0.72)), 1)
            yawp = math.radians(pl.ring_yaw)
            tilt = math.radians(pl.ring_tilt)
            n = Vector3(math.sin(yawp) * math.cos(tilt), math.cos(yawp) * math.cos(tilt), math.sin(tilt))
            ring_pts = circle_points_3d(c, n, pl.radius * pl.ring_scale, segments=SKY_RING_SEGMENTS)
            proj_pts = []
            for p in ring_pts:
                pr = cam.project(p, cam_fwd, cam_right, cam_up)
                if pr:
                    proj_pts.append((pr[0], pr[1]))
            if len(proj_pts) > 6:
                pygame.draw.lines(glow, rgbf_to_rgbi(pl.ring_color, 120), False, proj_pts, 1)
                pygame.draw.lines(glow, rgbf_to_rgbi(pl.ring_color, 190), False, proj_pts, int(pl.ring_thickness))

        bh_c = black_hole.center + par * 1.15
        bhp = cam.project(bh_c, cam_fwd, cam_right, cam_up)
        if bhp:
            rim = cam.project(bh_c + cam_right * black_hole.radius, cam_fwd, cam_right, cam_up)
            rim2 = cam.project(bh_c + cam_right * black_hole.ring_radius, cam_fwd, cam_right, cam_up)
            if rim and rim2:
                r_disc = abs(rim[0] - bhp[0])
                r_ring = abs(rim2[0] - bhp[0])
                # (Removed) no filled black-hole disc; accretion rings only (avoid black interior)
                pygame.draw.circle(glow, (10, 10, 12, 255), (int(bhp[0]), int(bhp[1])), int(r_disc), 1)
                ring_col = rgbf_to_rgbi(black_hole.ring_color, 210)
                ring_col2 = rgbf_to_rgbi(black_hole.ring_color, 80)
                for k in range(6):
                    rr = r_ring * (0.88 + 0.05*k)
                    a0 = (t_now * 0.6 * black_hole.spin + k * 0.9) % (math.pi * 2.0)
                    a1 = a0 + (math.pi * 2.0) * 0.35
                    pts = []
                    steps = max(12, SKY_RING_SEGMENTS // 2)
                    for i in range(steps+1):
                        tt = i/steps
                        ang = a0 + (a1-a0)*tt
                        x = bhp[0] + math.cos(ang) * rr
                        y = bhp[1] + math.sin(ang) * rr * 0.72
                        pts.append((x, y))
                    pygame.draw.lines(glow, ring_col2, False, pts, 1)
                    pygame.draw.lines(glow, ring_col, False, pts, 2)

        # CLOUDS (only in atmosphere; faded in space)
        if cloud_alpha > 0:
            cloud_drawn = 0
            for c in clouds:
                if cloud_drawn >= CLOUD_DRAW_BUDGET:
                    break
                # render only if near camera forward half-space (cheap culling)
                if (c.pos - cam.pos).dot(cam_fwd) < 1.0:
                    continue
                pr = cam.project(c.pos, cam_fwd, cam_right, cam_up)
                if not pr:
                    continue
                # screen radius based on depth
                rad = int((c.r / pr[2]) * cam.f * 0.95)
                if rad <= 1:
                    continue
                a = int(cloud_alpha * clamp(1.2 - (pr[2]/850.0), 0.0, 1.0))
                # layer puffs for volume
                base = c.neon
                cx, cy = int(pr[0]), int(pr[1])
                for k in range(3):
                    rr = int(rad * (1.0 + 0.55*k))
                    aa = int(a * (0.40 if k == 0 else (0.22 if k == 1 else 0.12)))
                    pygame.draw.circle(glow, rgbf_to_rgbi(base, aa), (cx + int((k-1)*rad*0.12), cy + int((k-1)*rad*0.10)), rr, 0)
                cloud_drawn += 1


        
        # GROUND / GRID (stable + non-fading near the camera)
        # Draw a robust black ground fill plus a grid that stays visible at close range.
        if (city_alpha > 0) or ground_assault or ocean_mode:
            # (1) Screen-space ground fill: estimate horizon by projecting far points on ground plane.
            # In ground assault, keep the horizon line stable in screen-space (Twisted-Metal proto feel).
            # In flight, we still estimate a horizon from the ground plane projection.
            if ground_assault:
                horizon_y = int(H * 0.60)
            elif ocean_mode:
                horizon_y = int(H * 0.57)
            else:
                horizon_y = None
                try:
                    far = 12000.0
                    base = player.pos + (cam_fwd * far)
                    base = Vector3(base.x, base.y, 0.0)
                    left = Vector3(base.x - far*0.6, base.y, 0.0)
                    right = Vector3(base.x + far*0.6, base.y, 0.0)
                    pl = cam.project(left, cam_fwd, cam_right, cam_up)
                    pr = cam.project(right, cam_fwd, cam_right, cam_up)
                    if pl and pr:
                        horizon_y = int((pl[1] + pr[1]) * 0.5)
                except Exception:
                    horizon_y = None

                if horizon_y is None:
                    horizon_y = int(H * 0.48)

            horizon_y = clamp(horizon_y, 0, H)

            # Screen-space fill beneath the horizon.
            if ocean_mode:
                water_fill = (4, 10, 20, 255)
                pygame.draw.rect(solid, water_fill, pygame.Rect(0, horizon_y, W, H - horizon_y))
            else:
                pygame.draw.rect(solid, (0, 0, 0, 255), pygame.Rect(0, horizon_y, W, H - horizon_y))

            # (2) Optional local projected quad for correctness when projection is valid.
            ground_span = 1800.0
            gw = [
                Vector3(player.pos.x - ground_span, player.pos.y - ground_span, 0.0),
                Vector3(player.pos.x + ground_span, player.pos.y - ground_span, 0.0),
                Vector3(player.pos.x + ground_span, player.pos.y + ground_span, 0.0),
                Vector3(player.pos.x - ground_span, player.pos.y + ground_span, 0.0),
            ]
            gp = [cam.project(p, cam_fwd, cam_right, cam_up) for p in gw]
            if all(p is not None for p in gp):
                pts2 = [(int(p[0]), int(p[1])) for p in gp]
                pygame.draw.polygon(solid, ((4, 10, 20, 255) if ocean_mode else (0, 0, 0, 255)), pts2, 0)

            # --- GRID ---
            # Ground assault: projected perspective grid (3D feel). Uses segment subdivision so lines
            # do not disappear near the camera / near-plane.
            if ocean_mode:
                water_alpha = 245
                step = 22.0
                span = 1850.0
                cyan = (0.10, 0.85, 1.00)
                blue = (0.16, 0.44, 1.00)
                deep = (0.02, 0.16, 0.32)

                def _draw_ocean_segment(p0, p1, col_f, subs=18, width_core=2, width_glow=5):
                    last = None
                    last_a = 0
                    for s in range(subs + 1):
                        tt = s / float(subs)
                        px = p0.x + (p1.x - p0.x) * tt
                        py = p0.y + (p1.y - p0.y) * tt
                        pz = ocean_wave_height(px, py, t_now)
                        p = Vector3(px, py, pz)
                        prj = cam.project(p, cam_fwd, cam_right, cam_up)
                        if prj is not None:
                            d = math.hypot(px - player.pos.x, py - player.pos.y)
                            aa = int(water_alpha * (0.28 + 0.72 * clamp(1.0 - d / span, 0.0, 1.0)))
                            if last is not None:
                                alpha_use = min(last_a, aa)
                                pygame.draw.line(glow, rgbf_to_rgbi(col_f, int(alpha_use * 0.36)), (last[0], last[1]), (prj[0], prj[1]), width_glow)
                                pygame.draw.line(glow, rgbf_to_rgbi(col_f, alpha_use), (last[0], last[1]), (prj[0], prj[1]), width_core)
                            last = prj
                            last_a = aa
                        else:
                            last = None
                            last_a = 0

                gx0 = math.floor((player.pos.x - span) / step) * step
                gy0 = math.floor((player.pos.y - span) / step) * step
                n = int((span * 2) / step) + 1
                for ii in range(n):
                    x = gx0 + ii * step
                    _draw_ocean_segment(Vector3(x, player.pos.y - span, 0.0), Vector3(x, player.pos.y + span, 0.0), cyan, subs=18)
                for ii in range(n):
                    y = gy0 + ii * step
                    _draw_ocean_segment(Vector3(player.pos.x - span, y, 0.0), Vector3(player.pos.x + span, y, 0.0), blue, subs=18)
                # broad moving swells
                swell_step = 78.0
                sy0 = math.floor((player.pos.y - span) / swell_step) * swell_step
                for ii in range(int((span * 2) / swell_step) + 1):
                    y = sy0 + ii * swell_step
                    drift = math.sin(t_now * 0.85 + ii * 0.6) * 38.0
                    _draw_ocean_segment(Vector3(player.pos.x - span + drift, y, 0.0), Vector3(player.pos.x + span + drift, y, 0.0), deep, subs=16, width_core=1, width_glow=3)

            elif ground_assault:
                # Twisted-Metal-style neon grid: cyan + magenta lines with a thicker glow.
                # Also keep it stable near the camera by segment-subdividing and using a small z-bias.
                grid_alpha2 = 235
                step = 18.0
                span = 1600.0
                z_bias = 0.08

                cyan = (0.10, 0.85, 1.00)
                magenta = (1.00, 0.20, 0.85)

                def _seg_alpha(p_xy):
                    # Distance-based falloff (keeps close range strong; fades gently at distance)
                    dx = p_xy[0] - player.pos.x
                    dy = p_xy[1] - player.pos.y
                    d = math.sqrt(dx*dx + dy*dy)
                    t = clamp(1.0 - (d / span), 0.0, 1.0)
                    return int(grid_alpha2 * (0.30 + 0.70 * t))

                def _draw_grid_segment(p0, p1, col_f, subs=14):
                    last = None
                    last_a = 0
                    for s in range(subs + 1):
                        t = s / float(subs)
                        p = Vector3(
                            p0.x + (p1.x - p0.x) * t,
                            p0.y + (p1.y - p0.y) * t,
                            p0.z + (p1.z - p0.z) * t,
                        )
                        prj = cam.project(p, cam_fwd, cam_right, cam_up)
                        if prj is not None:
                            a = _seg_alpha((p.x, p.y))
                            if last is not None:
                                aa = min(last_a, a)
                                # glow pass (wide, soft)
                                pygame.draw.line(glow, rgbf_to_rgbi(col_f, int(aa * 0.45)), (last[0], last[1]), (prj[0], prj[1]), 5)
                                # core pass (thin, bright)
                                pygame.draw.line(glow, rgbf_to_rgbi(col_f, aa), (last[0], last[1]), (prj[0], prj[1]), 2)
                            last = prj
                            last_a = a
                        else:
                            last = None
                            last_a = 0

                gx0 = math.floor((player.pos.x - span) / step) * step
                gy0 = math.floor((player.pos.y - span) / step) * step
                n = int((span * 2) / step) + 1

                # X-constant lines (run along Y): cyan
                for ii in range(n):
                    x = gx0 + ii * step
                    _draw_grid_segment(
                        Vector3(x, player.pos.y - span, z_bias),
                        Vector3(x, player.pos.y + span, z_bias),
                        cyan,
                        subs=14,
                    )

                # Y-constant lines (run along X): magenta
                for ii in range(n):
                    y = gy0 + ii * step
                    _draw_grid_segment(
                        Vector3(player.pos.x - span, y, z_bias),
                        Vector3(player.pos.x + span, y, z_bias),
                        magenta,
                        subs=14,
                    )

            else:
                # Flight/atmos: projected local grid (kept close to player).
                grid_alpha2 = max(110, min(220, int(grid_alpha)))
                grid_color = rgbf_to_rgbi((1.00, 0.10, 0.10), grid_alpha2)
                step = 14.0
                span = 920.0
                gx0 = math.floor((player.pos.x - span) / step) * step
                gy0 = math.floor((player.pos.y - span) / step) * step
                for i in range(int((span*2)/step) + 1):
                    x = gx0 + i * step
                    a = cam.project(Vector3(x, player.pos.y - span, 0.02), cam_fwd, cam_right, cam_up)
                    b = cam.project(Vector3(x, player.pos.y + span, 0.02), cam_fwd, cam_right, cam_up)
                    if a and b:
                        pygame.draw.line(glow, grid_color, (a[0], a[1]), (b[0], b[1]), 2)
                for i in range(int((span*2)/step) + 1):
                    y = gy0 + i * step
                    a = cam.project(Vector3(player.pos.x - span, y, 0.02), cam_fwd, cam_right, cam_up)
                    b = cam.project(Vector3(player.pos.x + span, y, 0.02), cam_fwd, cam_right, cam_up)
                    if a and b:
                        pygame.draw.line(glow, grid_color, (a[0], a[1]), (b[0], b[1]), 2)

                # Colorful ground line patterns + fake traffic streaks (purely visual; cheap).
                major_step = step * 6.0
                span2 = span * 1.05
                tphase = t_now * 0.55

                # Major "circuit" lines
                mx0 = math.floor((player.pos.x - span2) / major_step) * major_step
                my0 = math.floor((player.pos.y - span2) / major_step) * major_step

                for i in range(int((span2*2)/major_step) + 1):
                    x = mx0 + i * major_step
                    a = cam.project(Vector3(x, player.pos.y - span2, 0.0), cam_fwd, cam_right, cam_up)
                    b = cam.project(Vector3(x, player.pos.y + span2, 0.0), cam_fwd, cam_right, cam_up)
                    if a and b:
                        k = i * 0.7 + tphase
                        col = rgbf_to_rgbi(
                            (0.55 + 0.45*math.sin(k),
                             0.55 + 0.45*math.sin(k+2.1),
                             0.55 + 0.45*math.sin(k+4.2)),
                            int(85 * (city_alpha/255))
                        )
                        pygame.draw.line(glow, col, (a[0], a[1]), (b[0], b[1]), 2)

                for i in range(int((span2*2)/major_step) + 1):
                    y = my0 + i * major_step
                    a = cam.project(Vector3(player.pos.x - span2, y, 0.0), cam_fwd, cam_right, cam_up)
                    b = cam.project(Vector3(player.pos.x + span2, y, 0.0), cam_fwd, cam_right, cam_up)
                    if a and b:
                        k = i * 0.7 + tphase + 1.3
                        col = rgbf_to_rgbi(
                            (0.55 + 0.45*math.sin(k),
                             0.55 + 0.45*math.sin(k+2.1),
                             0.55 + 0.45*math.sin(k+4.2)),
                            int(85 * (city_alpha/255))
                        )
                        pygame.draw.line(glow, col, (a[0], a[1]), (b[0], b[1]), 2)

                # Fake traffic streaks on a few lanes near the player
                lane_offs = [-72.0, -36.0, 0.0, 36.0, 72.0]
                seg_len = 120.0
                traffic_n = 18
                for li, lo in enumerate(lane_offs):
                    lane_y = player.pos.y + lo
                    for j in range(traffic_n):
                        phase = (t_now * (0.95 + 0.08*li) + j*0.73) % 1.0
                        cx = player.pos.x - span2 + (span2*2) * phase
                        p0 = cam.project(Vector3(cx - seg_len*0.5, lane_y, 0.25), cam_fwd, cam_right, cam_up)
                        p1 = cam.project(Vector3(cx + seg_len*0.5, lane_y, 0.25), cam_fwd, cam_right, cam_up)
                        if p0 and p1:
                            k = (li*1.7 + j*0.33 + t_now*0.8)
                            col = rgbf_to_rgbi((0.5+0.5*math.sin(k),
                                                0.5+0.5*math.sin(k+2.1),
                                                0.5+0.5*math.sin(k+4.2)),
                                               int(120 * (city_alpha/255)))
                            pygame.draw.line(glow, col, (p0[0], p0[1]), (p1[0], p1[1]), 3)
        # BUILDINGS (solid black mass + neon outlines + neon pattern lines)
        blds = ([] if ocean_mode else city.all_buildings_list())

        # Performance: distance cull + simple LOD (far buildings draw fewer primitives).
        # Avoid full per-frame sorts when the city is dense.
        DRAW_DIST = CITY_CHUNK * (CITY_KEEP_RADIUS + 1.65)
        DRAW_DIST2 = DRAW_DIST * DRAW_DIST
        LOD1 = DRAW_DIST * 0.55
        LOD12 = LOD1 * LOD1
        LOD2 = DRAW_DIST * 0.78
        LOD22 = LOD2 * LOD2

        # Lightweight bucket ordering (approx back-to-front by chunk center along camera forward)
        # This is far cheaper than sorting every building by exact depth.
        cam2 = cam.pos

        # Helper: quick lerp between two Vector3
        def vlerp(a: Vector3, b: Vector3, t: float):
            return a + (b - a) * t

        # We draw the black fill *after* the grid so it occludes it; then draw neon lines on top.
        fill_a = int(235 * (city_alpha / 255))
        fill_col = (0, 0, 0, 255)

        vis = []
        for b in blds:
            # Distance culling + cache projection for depth-sorted opaque fills
            dx = b.cx - cam2.x
            dy = b.cy - cam2.y
            dz = (b.h * 0.5) - cam2.z
            dist2 = dx*dx + dy*dy + dz*dz
            if dist2 > DRAW_DIST2:
                continue

            corners = b.corners()
            proj = [cam.project(p, cam_fwd, cam_right, cam_up) for p in corners]
            if any(p is None for p in proj):
                continue

            vis.append((dist2, b, proj))

        # Cap building rendering before painter sort.  Keep nearest objects, then draw far-to-near.
        if len(vis) > BUILDING_DRAW_BUDGET:
            vis.sort(key=lambda t: t[0])
            vis = vis[:BUILDING_DRAW_BUDGET]

        # Painter's algorithm: far-to-near so solid fills properly occlude buildings behind them.
        vis.sort(key=lambda t: t[0], reverse=True)

        for dist2, b, proj in vis:
            corners = b.corners()
            # LOD:
            #  - very far: outline only (no fill, no pattern stripes)
            #  - mid: outline + top face (no per-face fills)
            lod_far = dist2 > LOD22
            lod_mid = (not lod_far) and (dist2 > LOD12)

            if isinstance(b, Pyramid):
                # Pyramid landmark rendering (cheap, distinct silhouette)
                p2 = [(proj[i][0], proj[i][1]) for i in range(5)]

                if not lod_far:
                    # Fill: base + 4 sides
                    if not lod_mid:
                        pygame.draw.polygon(solid, fill_col, [p2[i] for i in (0, 1, 2, 3)], 0)
                        pygame.draw.polygon(solid, fill_col, [p2[i] for i in (0, 1, 4)], 0)
                        pygame.draw.polygon(solid, fill_col, [p2[i] for i in (1, 2, 4)], 0)
                        pygame.draw.polygon(solid, fill_col, [p2[i] for i in (2, 3, 4)], 0)
                        pygame.draw.polygon(solid, fill_col, [p2[i] for i in (3, 0, 4)], 0)
                    else:
                        # Mid LOD: sides only (no base)
                        pygame.draw.polygon(solid, fill_col, [p2[i] for i in (0, 1, 4)], 0)
                        pygame.draw.polygon(solid, fill_col, [p2[i] for i in (1, 2, 4)], 0)
                        pygame.draw.polygon(solid, fill_col, [p2[i] for i in (2, 3, 4)], 0)
                        pygame.draw.polygon(solid, fill_col, [p2[i] for i in (3, 0, 4)], 0)

                a1 = int(105 * (city_alpha/255))
                a2 = int(190 * (city_alpha/255))
                neon = (255, 0, 0, a1)
                neon2 = (255, 0, 0, a2)
                for e0, e1 in PYR_EDGES:
                    a = p2[e0]
                    c2 = p2[e1]
                    draw_additive_line(glow, a, c2, neon, width=1)
                    draw_additive_line(glow, a, c2, neon2, width=2)

                continue

            # Filled faces (black) to make buildings feel solid and pre-generated
            # Indices: bottom 0-3, top 4-7 (same winding)
            p2 = [(proj[i][0], proj[i][1]) for i in range(8)]

            if not lod_far:
                if not lod_mid:
                    faces = [
                        (0, 1, 5, 4),  # side
                        (1, 2, 6, 5),
                        (2, 3, 7, 6),
                        (3, 0, 4, 7),
                        (4, 5, 6, 7),  # roof
                    ]
                    for f in faces:
                        pygame.draw.polygon(solid, fill_col, [p2[i] for i in f], 0)
                else:
                    # Mid LOD: roof only (cheap, still reads as solid mass)
                    pygame.draw.polygon(solid, fill_col, [p2[i] for i in (4, 5, 6, 7)], 0)
# Neon outlines
            a1 = int(90 * (city_alpha/255))
            a2 = int(175 * (city_alpha/255))
            neon = (255, 0, 0, a1)
            neon2 = (255, 0, 0, a2)
            for e0, e1 in BOX_EDGES:
                a = (proj[e0][0], proj[e0][1])
                c2 = (proj[e1][0], proj[e1][1])
                draw_additive_line(glow, a, c2, neon, width=1)
                draw_additive_line(glow, a, c2, neon2, width=2)

            # Pattern lines: subtle neon ribs/bands over black mass
            patt_a1 = int(140 * (city_alpha/255))
            patt_a2 = int(70 * (city_alpha/255))
            patt_col1 = (255, 0, 0, patt_a1)
            patt_col2 = (255, 0, 0, patt_a2)

            if (not lod_mid) and (not lod_far) and b.pattern == 0:
                # Horizontal bands: rectangles around the building at various heights
                n = max(2, b.stripe_count)
                for k in range(1, n + 1):
                    t = (k / (n + 1)) * 0.92 + 0.04
                    z = b.h * t
                    ring = [
                        Vector3(corners[0].x, corners[0].y, z),
                        Vector3(corners[1].x, corners[1].y, z),
                        Vector3(corners[2].x, corners[2].y, z),
                        Vector3(corners[3].x, corners[3].y, z),
                        Vector3(corners[0].x, corners[0].y, z),
                    ]
                    ring2d = []
                    ok = True
                    for p in ring:
                        pr = cam.project(p, cam_fwd, cam_right, cam_up)
                        if not pr:
                            ok = False
                            break
                        ring2d.append((pr[0], pr[1]))
                    if ok and len(ring2d) >= 2:
                        pygame.draw.lines(glow, patt_col2, False, ring2d, 3)
                        pygame.draw.lines(glow, patt_col1, False, ring2d, 1)
            elif (not lod_mid) and (not lod_far) and b.pattern == 1:
                # Vertical ribs: lines running from base to roof on the side faces
                # Use deterministic offsets based on stripe_phase
                n = max(3, b.stripe_count)
                # We only do ribs on the four side faces (avoid clutter on roof)
                side_pairs = [(0, 1), (1, 2), (2, 3), (3, 0)]
                for si, (i0, i1) in enumerate(side_pairs):
                    for k in range(n):
                        t = ((k + 0.5) / n) + (b.stripe_phase * 0.17) + si * 0.03
                        t = t - math.floor(t)  # wrap 0..1
                        # keep ribs away from edges so it reads as "design" not outline
                        t = 0.10 + t * 0.80
                        pb = vlerp(corners[i0], corners[i1], t)
                        pt = Vector3(pb.x, pb.y, pb.z + b.h)
                        prb = cam.project(pb, cam_fwd, cam_right, cam_up)
                        prt = cam.project(pt, cam_fwd, cam_right, cam_up)
                        if prb and prt:
                            a = (prb[0], prb[1])
                            c2 = (prt[0], prt[1])
                            draw_additive_line(glow, a, c2, patt_col2, width=3)
                            draw_additive_line(glow, a, c2, patt_col1, width=1)

        # Ground traffic + giant mech
        # Mech should remain readable even when the city is fading at higher altitude.
                # Giant robots: draw all active variants (ensure readability even when the city fades at altitude)
        for gm in _active_giants():
            try:
                mdx = gm.pos.x - player.pos.x
                mdy = gm.pos.y - player.pos.y
                md2 = mdx*mdx + mdy*mdy
            except Exception:
                md2 = 0.0

            gm_alpha = city_alpha
            if md2 < (1400.0 * 1400.0):
                gm_alpha = max(gm_alpha, 70)

            gm.draw(solid, glow, cam, cam_fwd, cam_right, cam_up, gm_alpha)

        if (city_alpha > 10) and (not ocean_mode):
            traffic.draw(solid, glow, cam, cam_fwd, cam_right, cam_up, city_alpha)
# Fire truck overlay (simple solid + wireframe)
        if firetruck is not None:
            p = firetruck["pos"]
            pr = cam.project(p + Vector3(0,0,3.0), cam_fwd, cam_right, cam_up)
            if pr:
                sx, sy, sc = pr
                w = int(22 * sc)
                h = int(10 * sc)
                if w > 1 and h > 1:
                    pygame.draw.rect(solid, (0,0,0,255), pygame.Rect(sx-w//2, sy-h//2, w, h))
                    pygame.draw.rect(ui, (*firetruck["neon"], 255), pygame.Rect(sx-w//2, sy-h//2, w, h), 2)
                    pygame.draw.line(ui, (*firetruck["neon"], 255),
                                     (sx, sy),
                                     (sx+int(math.cos(firetruck["yaw"])*w), sy+int(math.sin(firetruck["yaw"])*w)), 2)




        # TORNADOS (wireframe helix columns)
        if sf < 0.92:
            for tw in tornados:
                col = rgbf_to_rgbi(tw.neon, int(150 * (1.0 - sf)))
                col2 = rgbf_to_rgbi(tw.neon, int(80 * (1.0 - sf)))
                segments = 42
                pts = []
                for i in range(segments+1):
                    t = i/segments
                    z = tw.h * t
                    # radius expands with height
                    rr = lerp(tw.r0, tw.r1, t) * (1.0 + 0.10*math.sin(t_now*2.2 + tw.seed*0.001 + t*8.0))
                    ang = (t_now * 2.8 * tw.spin) + t * (math.pi * 2.0) * 6.0
                    x = tw.base.x + math.cos(ang) * rr
                    y = tw.base.y + math.sin(ang) * rr
                    p = Vector3(x, y, z)
                    pr = cam.project(p, cam_fwd, cam_right, cam_up)
                    if pr:
                        pts.append((pr[0], pr[1]))
                if len(pts) > 6:
                    pygame.draw.lines(glow, col2, False, pts, 3)
                    pygame.draw.lines(glow, col, False, pts, 1)
                # base ring
                prb = cam.project(Vector3(tw.base.x, tw.base.y, 0.0), cam_fwd, cam_right, cam_up)
                if prb:
                    pygame.draw.circle(glow, col, (int(prb[0]), int(prb[1])), int(40 + tw.r1*1.2), 1)

        # TRAILS
        def draw_trail(tr: Trail, base_col, thickness):
            if len(tr.pts) < 2:
                return
            pts2 = []
            for p, age in tr.pts:
                pr = cam.project(p, cam_fwd, cam_right, cam_up)
                if pr:
                    pts2.append((pr[0], pr[1], age))
            if len(pts2) < 2:
                return
            for i in range(len(pts2)-1):
                a = pts2[i]
                b = pts2[i+1]
                u = i / max(1, (len(pts2)-2))
                alpha = int(255 * (u ** 1.6) * 0.85)
                col = rgbf_to_rgbi(base_col, alpha)
                draw_additive_line(glow, (a[0], a[1]), (b[0], b[1]), col, width=thickness)

        for s in ships:
            if s.dead:
                continue
            draw_trail(s.trail, s.neon, 3)
            draw_trail(s.trail2, (1.0, 1.0, 1.0), 1)
        for u in ufos:
            if u.dead:
                continue
            draw_trail(u.trail, u.neon, 2)

        # BEAMS
        for bm in beams:
            pr1 = cam.project(bm.a, cam_fwd, cam_right, cam_up)
            pr2 = cam.project(bm.b, cam_fwd, cam_right, cam_up)
            if pr1 and pr2:
                a = (pr1[0], pr1[1])
                b2 = (pr2[0], pr2[1])
                col = rgbf_to_rgbi(bm.color, 240)
                col2 = rgbf_to_rgbi(bm.color, 90)
                draw_additive_line(glow, a, b2, col2, width=6)
                draw_additive_line(glow, a, b2, col, width=2)

        # BULLETS
        for b in bullets:
            pr = cam.project(b.pos, cam_fwd, cam_right, cam_up)
            if pr:
                if b.style_id == 1:
                    draw_glow_point(glow, (int(pr[0]), int(pr[1])), b.color, size=int(b.size*1.15), alpha=210)
                    pygame.draw.line(glow, rgbf_to_rgbi(b.color, 140), (pr[0]-10, pr[1]), (pr[0]+10, pr[1]), 2)
                    pygame.draw.line(glow, rgbf_to_rgbi(b.color, 140), (pr[0], pr[1]-10), (pr[0], pr[1]+10), 2)
                elif b.style_id == 2:
                    draw_glow_point(glow, (int(pr[0]), int(pr[1])), b.color, size=int(b.size*1.4), alpha=220)
                elif b.style_id == 3:
                    # Laser MG: bright head + velocity-aligned streak
                    draw_glow_point(glow, (int(pr[0]), int(pr[1])), b.color, size=int(b.size*1.25), alpha=235)
                    v2 = b.vel
                    if v2.length_squared() > 1e-6:
                        v2n = v2.normalize()
                        tail_pos = b.pos - v2n * 22.0
                        pr2 = cam.project(tail_pos, cam_fwd, cam_right, cam_up)
                        if pr2:
                            pygame.draw.line(glow, rgbf_to_rgbi(b.color, 210), (pr[0], pr[1]), (pr2[0], pr2[1]), 3)
                            pygame.draw.line(glow, rgbf_to_rgbi((1.0,1.0,1.0), 120), (pr[0], pr[1]), (pr2[0], pr2[1]), 1)
                    draw_glow_point(glow, (int(pr[0]), int(pr[1])), b.color, size=int(b.size*0.95), alpha=160)
                elif b.style_id == 201:
                    # Kaiju beam cannon shot: very bright head + long streak (looks like a continuous laser when fired rapidly)
                    draw_glow_point(glow, (int(pr[0]), int(pr[1])), b.color, size=int(b.size*1.35), alpha=245)
                    v2 = b.vel
                    if v2.length_squared() > 1e-6:
                        v2n = v2.normalize()
                        tail_pos = b.pos - v2n * 120.0
                        pr2 = cam.project(tail_pos, cam_fwd, cam_right, cam_up)
                        if pr2:
                            pygame.draw.line(glow, rgbf_to_rgbi(b.color, 220), (pr[0], pr[1]), (pr2[0], pr2[1]), 6)
                            pygame.draw.line(glow, rgbf_to_rgbi((1.0, 1.0, 1.0), 110), (pr[0], pr[1]), (pr2[0], pr2[1]), 2)
                else:

                    draw_glow_point(glow, (int(pr[0]), int(pr[1])), b.color, size=int(b.size), alpha=200)

        # MISSILES
        for m in missiles:
            pr = cam.project(m.pos, cam_fwd, cam_right, cam_up)
            if pr:
                draw_glow_point(glow, (int(pr[0]), int(pr[1])), m.color, size=(14 if m.style_id == 97 else (12 + m.style_id*2)), alpha=230)
                if m.style_id in (72, 73, 97):
                    mv = safe_norm(m.vel, Vector3(0, 1, 0))
                    tail = m.pos - mv * (28.0 if m.style_id == 97 else 18.0)
                    if m.style_id == 97:
                        tail.z = ocean_wave_height(tail.x, tail.y, t_now) + 0.35
                        draw_ocean_wake(m.pos + Vector3(0,0,-2.0), mv, 1.2, 22.0, (0.78, 0.95, 1.0), alpha_scale=0.65)
                    pr2 = cam.project(tail, cam_fwd, cam_right, cam_up)
                    if pr2:
                        pygame.draw.line(glow, rgbf_to_rgbi(m.color, 185), (pr[0], pr[1]), (pr2[0], pr2[1]), 3)

        # BOMBS (falling)
        for b in bombs:
            pr = cam.project(b.pos, cam_fwd, cam_right, cam_up)
            if pr:
                draw_glow_point(glow, (int(pr[0]), int(pr[1])), b.neon, size=14, alpha=220)
                prg = cam.project(Vector3(b.pos.x, b.pos.y, 0.0), cam_fwd, cam_right, cam_up)
                if prg:
                    draw_additive_line(glow, (pr[0], pr[1]), (prg[0], prg[1]), rgbf_to_rgbi(b.neon, 80), width=2)

        # SHIPS/UFO WIREFRAME
        def draw_wire_object(verts_w, edges, neon_rgb, thickness_main=1):
            proj = [cam.project(p, cam_fwd, cam_right, cam_up) for p in verts_w]
            if any(p is None for p in proj):
                return

            # Transparent silhouette fill (keeps ships readable without opaque discs).
            hull = convex_hull_2d([(p[0], p[1]) for p in proj])
            if len(hull) >= 3:
                # Transparent tinted silhouette fill (avoid opaque black discs blocking view)
                fill_col = rgbf_to_rgbi(neon_rgb, 22)
                pygame.draw.polygon(solid, fill_col, hull, 0)

            col = rgbf_to_rgbi(neon_rgb, 220)
            col2 = rgbf_to_rgbi(neon_rgb, 120)
            for e0, e1 in edges:
                a = (proj[e0][0], proj[e0][1])
                b2 = (proj[e1][0], proj[e1][1])
                draw_additive_line(glow, a, b2, col2, width=3)
                draw_additive_line(glow, a, b2, col, width=thickness_main)


        def draw_ocean_wake(origin: Vector3, fwd_vec: Vector3, width: float, length: float, color_rgb, alpha_scale: float = 1.0):
            pts_l = []
            pts_r = []
            right_vec = safe_norm(Vector3(fwd_vec.y, -fwd_vec.x, 0.0), Vector3(1, 0, 0))
            for i in range(8):
                tt = i / 7.0
                back = origin - fwd_vec * (length * tt)
                foam = ocean_wave_height(back.x, back.y, t_now) + 0.25
                edge_w = width * (0.25 + 0.75 * (1.0 - tt))
                lp = Vector3(back.x + right_vec.x * edge_w, back.y + right_vec.y * edge_w, foam)
                rp = Vector3(back.x - right_vec.x * edge_w, back.y - right_vec.y * edge_w, foam)
                lpr = cam.project(lp, cam_fwd, cam_right, cam_up)
                rpr = cam.project(rp, cam_fwd, cam_right, cam_up)
                if lpr and rpr:
                    pts_l.append((lpr[0], lpr[1]))
                    pts_r.append((rpr[0], rpr[1]))
            if len(pts_l) > 1:
                pygame.draw.lines(glow, rgbf_to_rgbi(color_rgb, int(135 * alpha_scale)), False, pts_l, 2)
            if len(pts_r) > 1:
                pygame.draw.lines(glow, rgbf_to_rgbi(color_rgb, int(135 * alpha_scale)), False, pts_r, 2)


        if ocean_mode:
            # Player speed boat + twin wake lines
            pf, pr, pu = player.basis()
            boat_local = [Vector3(v.x * 1.45, v.y * 1.62, v.z * 1.10) for v in SPEED_BOAT_MODEL["verts"]]
            boat_verts = transform_model(boat_local, player.pos, pf, pr, pu)
            draw_wire_object(boat_verts, SPEED_BOAT_MODEL["edges"], player.neon, thickness_main=2)
            wake_origin = player.pos + Vector3(0, 0, -OCEAN_PLAYER_RIDE + 0.30)
            draw_ocean_wake(wake_origin - pr * 1.6, pf, 2.2, 56.0 + min(44.0, player.vel.length() * 0.15), (0.68, 0.92, 1.0), alpha_scale=1.0)
            draw_ocean_wake(wake_origin + pr * 1.6, pf, 2.2, 56.0 + min(44.0, player.vel.length() * 0.15), (0.68, 0.92, 1.0), alpha_scale=1.0)
            bow_spray = []
            for side in (-1.0, 1.0):
                spr = player.pos + pf * 5.2 + pr * (1.7 * side) + Vector3(0, 0, 0.25)
                prj = cam.project(spr, cam_fwd, cam_right, cam_up)
                if prj:
                    bow_spray.append((int(prj[0]), int(prj[1])))
            for bp in bow_spray:
                pygame.draw.circle(glow, rgbf_to_rgbi((0.82, 0.96, 1.0), 150), bp, 3)
            if current_target() is None:
                pr0 = cam.project(player.pos + Vector3(0,0,1.0), cam_fwd, cam_right, cam_up)
                if pr0:
                    pygame.draw.circle(ui, rgbf_to_rgbi((0.68, 0.92, 1.0), 140), (int(pr0[0]), int(pr0[1])), 16, 1)

            for ws in warships:
                if getattr(ws, 'dead', False):
                    continue
                yawr = math.radians(ws.yaw)
                fwd = Vector3(math.sin(yawr), math.cos(yawr), 0.0)
                right = Vector3(fwd.y, -fwd.x, 0.0)
                up = Vector3(0, 0, 1)
                hull = [
                    Vector3(0, ws.length * 0.60, 1.6), Vector3(ws.width * 0.55, ws.length * 0.15, 1.0),
                    Vector3(ws.width * 0.65, -ws.length * 0.38, 0.6), Vector3(0, -ws.length * 0.60, 0.4),
                    Vector3(-ws.width * 0.65, -ws.length * 0.38, 0.6), Vector3(-ws.width * 0.55, ws.length * 0.15, 1.0),
                    Vector3(0, -ws.length * 0.05, 3.8), Vector3(0, ws.length * 0.12, 5.4),
                ]
                edges = [(0,1),(1,2),(2,3),(3,4),(4,5),(5,0),(2,6),(4,6),(6,7),(1,7),(5,7)]
                verts_w = transform_model(hull, ws.pos, fwd, right, up)
                draw_wire_object(verts_w, edges, ws.neon, thickness_main=2)
                draw_ocean_wake(ws.pos + Vector3(0,0,0.2), fwd, ws.width * 0.85, ws.length * 1.8, (0.30, 0.78, 1.00), alpha_scale=0.85)
                if ws is current_target():
                    pr0 = cam.project(ws.pos + Vector3(0,0,4.0), cam_fwd, cam_right, cam_up)
                    if pr0:
                        pygame.draw.circle(ui, rgbf_to_rgbi((0.20, 0.90, 1.0), 255), (int(pr0[0]), int(pr0[1])), 20, 2)

            for heli in helicopters:
                if getattr(heli, 'dead', False):
                    continue
                yawr = math.radians(heli.yaw)
                fwd = Vector3(math.sin(yawr), math.cos(yawr), 0.0)
                right = Vector3(fwd.y, -fwd.x, 0.0)
                up = Vector3(0, 0, 1)
                heli_model = [
                    Vector3(0, 4.4, 0), Vector3(2.0, 0.8, 0), Vector3(2.0, -3.8, 0), Vector3(-2.0, -3.8, 0), Vector3(-2.0, 0.8, 0),
                    Vector3(0, -0.2, 1.6), Vector3(0, -0.4, -1.2), Vector3(0, 0.0, 2.6), Vector3(0, 0.0, -2.0)
                ]
                heli_edges = [(0,1),(1,2),(2,3),(3,4),(4,0),(1,5),(4,5),(2,6),(3,6),(7,8)]
                verts_w = transform_model(heli_model, heli.pos, fwd, right, up)
                draw_wire_object(verts_w, heli_edges, heli.neon, thickness_main=2)
                rotor_pts = []
                for ang in (0.0, math.pi * 0.5, math.pi, math.pi * 1.5):
                    p0 = heli.pos + right * math.cos(ang) * 7.0 + fwd * math.sin(ang) * 1.2 + up * 2.6
                    p1 = heli.pos - right * math.cos(ang) * 7.0 - fwd * math.sin(ang) * 1.2 + up * 2.6
                    pr0 = cam.project(p0, cam_fwd, cam_right, cam_up)
                    pr1 = cam.project(p1, cam_fwd, cam_right, cam_up)
                    if pr0 and pr1:
                        pygame.draw.line(glow, rgbf_to_rgbi(heli.neon, 170), (pr0[0], pr0[1]), (pr1[0], pr1[1]), 2)
                if heli is current_target():
                    pr0 = cam.project(heli.pos, cam_fwd, cam_right, cam_up)
                    if pr0:
                        pygame.draw.circle(ui, rgbf_to_rgbi((1.0, 0.72, 0.22), 255), (int(pr0[0]), int(pr0[1])), 18, 2)
        else:
            ships_sorted = [s for s in ships if not s.dead]
            ships_sorted.sort(key=lambda s: (s.pos - cam.pos).length_squared(), reverse=True)
            for s in ships_sorted:
                fwd, right, up = s.basis()
                model = s.variant if s.is_player else s.variant
                verts_w = transform_model(model["verts"], s.pos, fwd, right, up)
                draw_wire_object(verts_w, model["edges"], s.neon, thickness_main=1)
                if s is current_target():
                    pr0 = cam.project(s.pos, cam_fwd, cam_right, cam_up)
                    if pr0:
                        pygame.draw.circle(ui, rgbf_to_rgbi((1.0, 0.25, 0.95), 255), (int(pr0[0]), int(pr0[1])), 18, 2)

            for u in ufos:
                if u.dead:
                    continue
                fwd, right, up = u.basis()
                verts_w = transform_model(UFO_VERTS, u.pos, fwd, right, up)
                draw_wire_object(verts_w, UFO_EDGES, u.neon, thickness_main=2)
                ring_pts = circle_points_3d(u.pos + up * 0.2, up, 3.6, segments=28)
                pts2 = []
                for p in ring_pts:
                    pr = cam.project(p, cam_fwd, cam_right, cam_up)
                    if pr:
                        pts2.append((pr[0], pr[1]))
                if len(pts2) > 6:
                    pygame.draw.lines(glow, rgbf_to_rgbi(u.neon, 180), False, pts2, 2)

        # EXPLOSIONS/SHOCKWAVES

        for e in explosions:
            u = e.t / e.life

            # Hotter palette + higher transparency (keeps structures/vehicles readable through FX)
            # Blend the source color toward red/orange.
            e_col = (
                (float(e.color[0]) * 0.18) + (1.00 * 0.82),
                (float(e.color[1]) * 0.18) + (0.14 * 0.82),
                (float(e.color[2]) * 0.18) + (0.08 * 0.82),
            )

            pr = cam.project(e.pos + Vector3(0, 0, 12.0 if e.is_atomic else 2.0), cam_fwd, cam_right, cam_up)
            if pr:
                size = int(26 + (1.0 - (1.0-u)**2) * (110 if e.is_atomic else 62))
                alpha = int((190 if e.is_atomic else 145) * (1.0 - u))
                draw_glow_point(glow, (int(pr[0]), int(pr[1])), e_col, size=size, alpha=alpha)

            gp = Vector3(e.pos.x, e.pos.y, 0.0)
            prg = cam.project(gp, cam_fwd, cam_right, cam_up)
            if prg:
                base = 50 if e.is_atomic else 36
                maxr = 520 if e.is_atomic else 260
                r = int((base + u * maxr) * (1.0 + 0.05 * math.sin(u * math.pi * (9.0 if e.is_atomic else 7.0))))
                a = int((150 if e.is_atomic else 95) * ((1.0 - u) ** 1.6))
                col = rgbf_to_rgbi(e_col, a)
                pygame.draw.circle(glow, col, (int(prg[0]), int(prg[1])), r, 2)

                # Atomic: faint secondary rings (still transparent)
                if e.is_atomic and (u < 0.70):
                    for k in range(1, 4):
                        rr = int(r * (0.35 + 0.12*k))
                        aa = int(a * (0.45 - 0.10*k))
                        pygame.draw.circle(glow, rgbf_to_rgbi((1.0, 0.25, 0.10), aa), (int(prg[0]), int(prg[1])), rr, 1)
# FIRES (small flicker; cheap)
        for f in fires:
            pr = cam.project(f.pos + Vector3(0, 0, 2.0), cam_fwd, cam_right, cam_up)
            if pr:
                sx, sy, scale = pr
                flick = (0.55 + 0.45 * math.sin((t_now*18.0) + (f.pos.x+f.pos.y)*0.02))
                a = int(160 * max(0.0, min(1.0, f.intensity)) * flick)
                if a > 8:
                    col = (255, 120, 40, a)
                    r = int(6 + f.radius * 0.20 * scale)
                    pygame.draw.circle(glow, col, (sx, sy), max(2, r), 2)
        for d in debris:
            pr = cam.project(d.pos, cam_fwd, cam_right, cam_up)
            if pr:
                uu = d.t / d.life
                a = int(180 * (1.0 - uu))
                draw_glow_point(glow, (int(pr[0]), int(pr[1])), d.color, size=int(5 + d.size*2), alpha=a)

        screen.blit(solid, (0, 0))
        screen.blit(glow, (0, 0))
        screen.blit(ui, (0, 0))

        tgt = current_target()
        hp = int(player.hp)
        sh = int(player.shield)
        spd = int(player.vel.length())
        cd = max(0.0, player.missile_cd - (t_now - player.last_missile))
        vname = ("Speedboat" if ocean_mode else player.variant["name"])
        screen.blit(big.render(f"Variant {vname}   HP {hp}/{player.hp_max}   SH {sh}/{player.shield_max}   SPD {spd}   MissileCD {cd:.1f}s", True, (210, 225, 235)), (16, 14))

        # Boot-time audio status (6 seconds). Also logs to crash_reports/audio_log.txt.
        if audio_banner_t > 0.0:
            audio_banner_t -= dt
            screen.blit(font.render(audio_banner, True, (220, 220, 220)), (16, 110))
        if tgt:
            dist = int((tgt.pos - player.pos).length())
            t_hp = int(getattr(tgt, "hp", 0))
            t_sh = getattr(tgt, "shield", None)
            if isinstance(tgt, Ship):
                label = f"Ship {tgt.sid}"
            elif isinstance(tgt, UFO):
                label = f"UFO {tgt.uid}"
            elif isinstance(tgt, GiantMech):
                label = str(getattr(tgt, 'kind', 'GIANT')).upper()
            elif isinstance(tgt, OceanWarship):
                label = f"WARSHIP {tgt.wid}"
            elif isinstance(tgt, OceanHelicopter):
                label = f"HELI {tgt.hid}"
            else:
                label = "Target"
            extra = f"  SH {int(t_sh)}" if t_sh is not None else ""
            screen.blit(font.render(f"{label}  Dist {dist}  HP {t_hp}{extra}", True, (140, 220, 255)), (16, 44))
        else:
            screen.blit(font.render("Target: none", True, (140, 220, 255)), (16, 44))

        alive_ufos = sum(1 for u in ufos if not u.dead)
        giant_line = ""
        ags = _active_giants()
        if ags:
            ng = nearest_giant(player.pos)
            if ng is None:
                ng = ags[0]
            kind = str(getattr(ng, "kind", "giant")).upper()
            giant_line = f"   GIANTS {len(ags)}  NEAREST {kind} HP {int(ng.hp)}/{int(ng.hp_max)}"

        ocean_line = ""
        if ocean_mode:
            live_warships = sum(1 for w in warships if not getattr(w, 'dead', False))
            live_helis = sum(1 for h in helicopters if not getattr(h, 'dead', False))
            ocean_line = f"   WARSHIPS {live_warships}/{len(warships)}   HELIS {live_helis}/{OCEAN_HELI_LIMIT}"
        screen.blit(font.render(f"UFOs: {alive_ufos}/{len(ufos)}   Tornados: {len(tornados)}   Atomic drop in ~{max(0,int(next_bomb_t - t_now))}s{giant_line}{ocean_line}", True, (220, 160, 255)), (16, 66))

        # Mode / flight indicator
        atm = "SPACE" if sf >= 0.55 else "ATMOS"
        mode_name = ("OCEAN" if ocean_mode else ("FOOT" if ground_assault else "AIR"))
        hint = "Wave ride + torpedoes" if ocean_mode else ("Street assault" if ground_assault else "Dogfight")
        frame_ms = float(clock.get_time())
        perf_state = "OK" if frame_ms <= (TARGET_FRAME_MS * 1.25) else "OVER"
        active_blds = min(len(city.all_buildings_list()), BUILDING_DRAW_BUDGET)
        perf_line = (
            f"MODE {mode_name}   ALT {int(player.pos.z)}   FLIGHT {atm}   {hint}   "
            f"FPS {clock.get_fps():4.0f} {frame_ms:4.1f}ms/{TARGET_FRAME_MS:.1f}ms {perf_state}   "
            f"PERF {PERF_PROFILE.upper()}   BLD {active_blds}/{BUILDING_DRAW_BUDGET}   "
            f"B/M/D {len(bullets)}/{len(missiles)}/{len(debris)}"
        )
        screen.blit(font.render(perf_line, True, ((120, 210, 255) if ocean_mode else (160, 200, 190))), (16, 88))

        screen.blit(font.render("W/S pitch  A/D yaw  Q/E roll  Shift boost  Space/Ctrl hover/brake  LMB guns  RMB missile/torpedo  R weapon mode  V ship variant  TAB ground/air/ocean  T target  Esc quit", True, (160, 170, 190)), (16, H - 28))

        if mode_flash_t > 0.0:
            mode_flash_t -= dt
            weapon_slot = "LASER" if mode_i < 0 else f"{mode_i+1}/{len(WEAPON_MODES)}"
            banner = big.render(f"WEAPON {weapon_slot}  {mode['name']}   |   SHIP {player.variant_index+1}/{len(PLAYER_VARIANTS)}  {player.variant['name']}", True, (255, 230, 180))
            bg = pygame.Surface((banner.get_width()+18, banner.get_height()+10), pygame.SRCALPHA)
            pygame.draw.rect(bg, (0, 0, 0, 140), bg.get_rect(), border_radius=8)
            pygame.draw.rect(bg, (255, 255, 255, 35), bg.get_rect(), 2, border_radius=8)
            screen.blit(bg, (W//2 - bg.get_width()//2, 12))
            screen.blit(banner, (W//2 - banner.get_width()//2, 18))

        # Quit confirmation overlay (modal)
        if quit_confirm:
            shade = pygame.Surface((W, H), pygame.SRCALPHA)
            shade.fill((0, 0, 0, 160))
            screen.blit(shade, (0, 0))

            panel_w, panel_h = 760, 190
            px = W // 2 - panel_w // 2
            py = H // 2 - panel_h // 2

            panel = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
            pygame.draw.rect(panel, (0, 0, 0, 210), panel.get_rect(), border_radius=14)
            pygame.draw.rect(panel, (255, 255, 255, 70), panel.get_rect(), 2, border_radius=14)

            if HOLOVERSE_EMBEDDED:
                t1 = big.render("Return to HoloVerse Core?", True, (255, 255, 255))
                t2 = font.render("Press ESC again (or Y / Enter) to return. Hub return signal also works.", True, (235, 235, 235))
                t3 = font.render("Press N / Backspace to resume Vector Wars.", True, (210, 210, 210))
            else:
                t1 = big.render("Quit game?", True, (255, 255, 255))
                t2 = font.render("Press ESC again (or Y / Enter) to quit.", True, (235, 235, 235))
                t3 = font.render("Press N to cancel.", True, (210, 210, 210))

            panel.blit(t1, (24, 20))
            panel.blit(t2, (24, 78))
            panel.blit(t3, (24, 112))

            screen.blit(panel, (px, py))

        # Present (letterboxed scaling; keeps a fixed 16:9 virtual canvas)
        display.fill((0, 0, 0))
        if view_size == (BASE_W, BASE_H) and view_off == (0, 0):
            display.blit(screen, (0, 0))
        else:
            if scaled_frame is None or scaled_frame.get_size() != view_size:
                scaled_frame = pygame.Surface(view_size).convert()
            pygame.transform.scale(screen, view_size, scaled_frame)
            display.blit(scaled_frame, view_off)
        pygame.display.flip()

        if (auto_exit_after is not None) and (t_now >= float(auto_exit_after)):
            running = False

    if not embedded:
        pygame.quit()
    return 0


def launch_from_panda3d(auto_mode: str = "air", perf: str | None = None):
    """Helper for Panda3D launchers.

    Use this from a Panda3D game as a subprocess command source, e.g.
    subprocess.Popen(launch_from_panda3d("air"))
    """
    return get_panda3d_launch_command(auto_mode=auto_mode, perf=perf)


def _write_crash_report(exc: BaseException):
    try:
        os.makedirs(os.path.join(ROOT_DIR, "crash_reports"), exist_ok=True)
        ts = time.strftime("%Y%m%d_%H%M%S")
        fn = os.path.join(ROOT_DIR, "crash_reports", f"crash_{ts}.txt")
        with open(fn, "w", encoding="utf-8") as f:
            f.write("Dogfight Vector crash report\n")
            f.write(f"Timestamp: {ts}\n")
            f.write(f"Python: {sys.version}\n")
            f.write(f"Platform: {platform.platform()}\n")
            try:
                f.write(f"Pygame: {pygame.version.ver}\n")
            except Exception:
                pass
            f.write("\nTraceback:\n")
            f.write("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))
        print(f"[Crash] Report written to: {fn}")
    except Exception as e2:
        print("[Crash] Failed to write crash report:", e2)

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as e:
        _write_crash_report(e)
        raise
