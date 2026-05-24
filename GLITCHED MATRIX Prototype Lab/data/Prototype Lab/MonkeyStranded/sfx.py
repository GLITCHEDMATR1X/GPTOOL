"""
sfx.py - SFX handler for MonkeyStranded.

Folder convention (relative to this file):
  sfx/
    ui/
    monkeys/
    birds/
    world/
    crabs/
    iguanas/

If a file is missing, a short placeholder WAV will be generated automatically
to keep the game stable and avoid missing-asset crashes.
"""

from __future__ import annotations

import os
import math
import random
import wave
import struct
from typing import Optional

try:
    import pygame
except Exception:  # pragma: no cover
    pygame = None


def _ensure_dir(path: str):
    try:
        os.makedirs(path, exist_ok=True)
    except Exception:
        pass


def _write_wav(path: str, seconds: float, kind: str, seed: int = 0):
    """Generate a tiny mono WAV placeholder."""
    if seconds <= 0:
        seconds = 0.15
    sr = 22050
    n = max(64, int(sr * seconds))
    rng = random.Random(seed)

    def env(t: float) -> float:
        # quick attack, exponential-ish decay
        a = 0.02
        if t < a:
            return t / a
        return math.exp(-3.5 * (t - a))

    frames = bytearray()
    base = 200 + rng.randint(-40, 40)

    for i in range(n):
        t = i / sr
        e = env(t)
        if kind == "click":
            f = 1200.0
            s = math.sin(2 * math.pi * f * t) * e
        elif kind == "step":
            f = 180.0 + 40.0 * math.sin(2 * math.pi * 2.0 * t)
            s = (math.sin(2 * math.pi * f * t) + 0.3 * math.sin(2 * math.pi * (f * 2.1) * t)) * 0.7 * e
        elif kind == "splash":
            # filtered noise + low tone
            s = (rng.uniform(-1.0, 1.0) * 0.55 + math.sin(2 * math.pi * 110.0 * t) * 0.25) * e
        elif kind == "scurry":
            f = 420.0 + 120.0 * math.sin(2 * math.pi * 10.0 * t)
            s = (math.sin(2 * math.pi * f * t) * 0.4 + rng.uniform(-1.0, 1.0) * 0.15) * e
        elif kind == "hit":
            f = 240.0
            s = (math.sin(2 * math.pi * f * t) * 0.8 + rng.uniform(-1.0, 1.0) * 0.25) * e
        elif kind == "loot":
            f = 620.0
            s = (math.sin(2 * math.pi * f * t) * 0.6 + math.sin(2 * math.pi * (f * 1.6) * t) * 0.2) * e
        elif kind == "bird":
            # chirp
            f0 = 500.0 + 900.0 * t
            s = math.sin(2 * math.pi * f0 * t) * e
        elif kind == "ocean":
            s = rng.uniform(-1.0, 1.0) * 0.15
        else:
            s = math.sin(2 * math.pi * base * t) * e

        v = int(max(-1.0, min(1.0, s)) * 32767)
        frames += struct.pack('<h', v)

    _ensure_dir(os.path.dirname(path))
    try:
        with wave.open(path, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sr)
            wf.writeframes(frames)
    except Exception:
        pass


def _ensure_wav_file(path: str, kind: str, seconds: float, seed: int):
    if os.path.exists(path):
        return
    _write_wav(path, seconds=seconds, kind=kind, seed=seed)


class SFXManager:
    def __init__(self):
        self.enabled = False
        self.sounds = {}
        self.ch_ocean: Optional['pygame.mixer.Channel'] = None
        self._ocean_playing = False

        if pygame is None:
            return

        try:
            pygame.mixer.pre_init(22050, -16, 1, 512)
            pygame.mixer.init()
            self.enabled = True
        except Exception:
            self.enabled = False

        if self.enabled:
            self._ensure_placeholders()
            self._load_all()

    def _base_dir(self) -> str:
        return os.path.dirname(os.path.abspath(__file__))

    def _ensure_placeholders(self):
        base = self._base_dir()
        # UI
        _ensure_wav_file(os.path.join(base, "sfx", "ui", "click.wav"), "click", 0.08, 1)
        _ensure_wav_file(os.path.join(base, "sfx", "ui", "toggle.wav"), "click", 0.10, 2)
        _ensure_wav_file(os.path.join(base, "sfx", "ui", "error.wav"), "hit", 0.16, 3)

        # Monkeys
        _ensure_wav_file(os.path.join(base, "sfx", "monkeys", "step.wav"), "step", 0.10, 10)
        _ensure_wav_file(os.path.join(base, "sfx", "monkeys", "throw.wav"), "click", 0.12, 11)
        _ensure_wav_file(os.path.join(base, "sfx", "monkeys", "pickup.wav"), "loot", 0.12, 12)
        _ensure_wav_file(os.path.join(base, "sfx", "monkeys", "interact.wav"), "click", 0.10, 13)
        _ensure_wav_file(os.path.join(base, "sfx", "monkeys", "climb.wav"), "scurry", 0.18, 14)

        # Birds
        _ensure_wav_file(os.path.join(base, "sfx", "birds", "seagull.wav"), "bird", 0.35, 20)
        _ensure_wav_file(os.path.join(base, "sfx", "birds", "parrot.wav"), "bird", 0.28, 21)
        _ensure_wav_file(os.path.join(base, "sfx", "birds", "hit.wav"), "hit", 0.14, 22)
        _ensure_wav_file(os.path.join(base, "sfx", "birds", "loot.wav"), "loot", 0.12, 23)

        # World
        _ensure_wav_file(os.path.join(base, "sfx", "world", "coconut_fall.wav"), "hit", 0.20, 30)
        _ensure_wav_file(os.path.join(base, "sfx", "world", "ocean_loop.wav"), "ocean", 0.80, 31)

        # Crabs
        _ensure_wav_file(os.path.join(base, "sfx", "crabs", "scuttle.wav"), "scurry", 0.12, 40)
        _ensure_wav_file(os.path.join(base, "sfx", "crabs", "hit.wav"), "hit", 0.12, 41)
        _ensure_wav_file(os.path.join(base, "sfx", "crabs", "loot.wav"), "loot", 0.12, 42)

        # Iguanas
        _ensure_wav_file(os.path.join(base, "sfx", "iguanas", "scurry.wav"), "scurry", 0.14, 50)
        _ensure_wav_file(os.path.join(base, "sfx", "iguanas", "hit.wav"), "hit", 0.14, 51)
        _ensure_wav_file(os.path.join(base, "sfx", "iguanas", "loot.wav"), "loot", 0.14, 52)

    def _load(self, key: str, rel_path: str):
        if not self.enabled or pygame is None:
            return
        p = os.path.join(self._base_dir(), rel_path)
        try:
            self.sounds[key] = pygame.mixer.Sound(p)
        except Exception:
            pass

    def _load_all(self):
        # UI
        self._load("ui_click", os.path.join("sfx", "ui", "click.wav"))
        self._load("ui_toggle", os.path.join("sfx", "ui", "toggle.wav"))
        self._load("ui_error", os.path.join("sfx", "ui", "error.wav"))

        # Monkeys
        self._load("monkey_step", os.path.join("sfx", "monkeys", "step.wav"))
        self._load("monkey_throw", os.path.join("sfx", "monkeys", "throw.wav"))
        self._load("monkey_pickup", os.path.join("sfx", "monkeys", "pickup.wav"))
        self._load("monkey_interact", os.path.join("sfx", "monkeys", "interact.wav"))
        self._load("monkey_climb", os.path.join("sfx", "monkeys", "climb.wav"))

        # Birds
        self._load("bird_seagull", os.path.join("sfx", "birds", "seagull.wav"))
        self._load("bird_parrot", os.path.join("sfx", "birds", "parrot.wav"))
        self._load("bird_hit", os.path.join("sfx", "birds", "hit.wav"))
        self._load("bird_loot", os.path.join("sfx", "birds", "loot.wav"))

        # World
        self._load("coconut_fall", os.path.join("sfx", "world", "coconut_fall.wav"))
        self._load("ocean_loop", os.path.join("sfx", "world", "ocean_loop.wav"))

        # Crabs
        self._load("crab_scuttle", os.path.join("sfx", "crabs", "scuttle.wav"))
        self._load("crab_hit", os.path.join("sfx", "crabs", "hit.wav"))
        self._load("crab_loot", os.path.join("sfx", "crabs", "loot.wav"))

        # Iguanas
        self._load("iguana_scurry", os.path.join("sfx", "iguanas", "scurry.wav"))
        self._load("iguana_hit", os.path.join("sfx", "iguanas", "hit.wav"))
        self._load("iguana_loot", os.path.join("sfx", "iguanas", "loot.wav"))

        try:
            self.ch_ocean = pygame.mixer.Channel(2)
        except Exception:
            self.ch_ocean = None

    def play(self, key: str, volume: float = 0.7):
        if not self.enabled:
            return
        s = self.sounds.get(key)
        if not s:
            return
        try:
            s.set_volume(max(0.0, min(1.0, float(volume))))
            s.play()
        except Exception:
            pass

    def ocean_set(self, volume: float):
        """Volume 0..1. Starts/stops loop automatically."""
        if not self.enabled or not self.ch_ocean:
            return
        vol = max(0.0, min(1.0, float(volume)))
        snd = self.sounds.get("ocean_loop")
        if not snd:
            return
        try:
            if vol <= 0.01:
                if self._ocean_playing:
                    self.ch_ocean.stop()
                    self._ocean_playing = False
                return
            if not self._ocean_playing:
                self.ch_ocean.play(snd, loops=-1)
                self._ocean_playing = True
            self.ch_ocean.set_volume(vol)
        except Exception:
            pass
