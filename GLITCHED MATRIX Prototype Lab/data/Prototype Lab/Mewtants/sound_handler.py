import os
import random
from typing import Optional, Tuple, List

try:
    import pygame
except Exception:
    pygame = None


AUDIO_EXTS = (".ogg", ".wav", ".mp3")


def _first_existing_audio_file(folder: str) -> Optional[str]:
    """Return a random audio file path from folder, or None if none exist."""
    if not os.path.isdir(folder):
        return None
    files = []
    for fn in os.listdir(folder):
        lo = fn.lower()
        if lo.endswith(AUDIO_EXTS):
            files.append(os.path.join(folder, fn))
    if not files:
        return None
    return random.choice(files)


def _write_readme(folder: str, title: str, examples: List[str]) -> None:
    try:
        os.makedirs(folder, exist_ok=True)
        readme = os.path.join(folder, "README.txt")
        if os.path.exists(readme):
            return
        with open(readme, "w", encoding="utf-8") as f:
            f.write(title.strip() + "\n\n")
            f.write("Drop .ogg/.wav/.mp3 files into this folder.\n")
            if examples:
                f.write("\nSuggested filenames:\n")
                for ex in examples:
                    f.write(f"  - {ex}\n")
    except Exception:
        # Folder creation/readme failure should never crash the game.
        pass


class SoundHandler:
    """
    Minimal, crash-resistant audio manager:
    - Creates an on-disk folder tree for SFX, ambience, and music.
    - Loads/plays audio if files exist (otherwise silently no-ops).
    - Supports 2-layer ambience crossfade for biome blending (overworld).
    - Switches dungeon ambience/music while inside dungeons.
    """

    def __init__(self, project_root: Optional[str] = None, enabled: bool = True):
        self.project_root = project_root or os.path.dirname(os.path.abspath(__file__))
        self.audio_root = os.path.join(self.project_root, "assets", "audio")

        self.enabled = bool(enabled)
        self._mixer_ok = False
        self._rng = random.Random()

        # Channels:
        # 0,1 reserved for ambience layers (crossfade)
        # 2..7 for SFX spam-safe rotation
        self._amb_ch = [None, None]
        self._sfx_channels = []
        self._sfx_idx = 0

        self._amb_paths = [None, None]  # currently playing file per layer
        self._context = "overworld"  # or "dungeon"
        self._dungeon_kind = None

        self._music_path = None
        self._cache = {}  # filepath -> pygame.mixer.Sound

        self._ensure_folder_tree()

        if self.enabled and pygame is not None:
            self._init_mixer()

    # ---------------- Folder generation ----------------
    def _ensure_folder_tree(self) -> None:
        # SFX folders
        sfx_actions = [
            "jump.ogg",
            "scratch.ogg",
            "bite.ogg",
            "hit.ogg",
            "power.ogg",
            "power_ember.ogg",
            "power_breeze.ogg",
            "power_frost.ogg",
            "power_sparkle.ogg",
            "enter_dungeon.ogg",
            "exit_dungeon.ogg",
            "boss_defeated.ogg",
            "wall_break.ogg",
            "projectile_fire.ogg",
            "projectile_hit.ogg",
            "ui_click.ogg",
        ]
        _write_readme(os.path.join(self.audio_root, "sfx", "actions"),
                      "SFX / Actions", sfx_actions)

        _write_readme(os.path.join(self.audio_root, "sfx", "characters", "kitten"),
                      "SFX / Characters / Kitten", ["meow.ogg", "purr.ogg", "hurt.ogg", "death.ogg"])

        _write_readme(os.path.join(self.audio_root, "sfx", "characters", "boss_cat"),
                      "SFX / Characters / Boss Cat", ["roar.ogg", "hurt.ogg", "death.ogg"])

        _write_readme(os.path.join(self.audio_root, "sfx", "enemies", "generic"),
                      "SFX / Enemies / Generic", ["enemy_hurt.ogg", "enemy_death.ogg"])

        _write_readme(os.path.join(self.audio_root, "sfx", "powerups"),
                      "SFX / Powerups", ["catnip.ogg", "tuna.ogg", "whistle.ogg", "upgrade.ogg"])

        _write_readme(os.path.join(self.audio_root, "sfx", "npcs", "generic"),
                      "SFX / NPCs / Generic", ["hello.ogg", "trade.ogg", "bye.ogg"])

        # Ambience folders
        biomes = ["grass", "desert", "snow", "mountain", "jungle", "swamp", "beach"]
        for b in biomes:
            _write_readme(os.path.join(self.audio_root, "ambience", "overworld", b),
                          f"Ambience / Overworld / {b}", [f"{b}_loop.ogg", f"{b}_wind.ogg"])

        dungeon_types = ["tower_maze", "ruins", "cavern", "sewers"]
        for d in dungeon_types:
            _write_readme(os.path.join(self.audio_root, "ambience", "dungeon", d),
                          f"Ambience / Dungeon / {d}", [f"{d}_loop.ogg", f"{d}_drip.ogg"])

        # Music folders
        for b in biomes:
            _write_readme(os.path.join(self.audio_root, "music", "overworld", b),
                          f"Music / Overworld / {b}", [f"{b}.ogg", f"{b}_theme.ogg"])

        for d in dungeon_types:
            _write_readme(os.path.join(self.audio_root, "music", "dungeon", d),
                          f"Music / Dungeon / {d}", [f"{d}.ogg", f"{d}_theme.ogg"])

        _write_readme(os.path.join(self.audio_root, "music", "boss"),
                      "Music / Boss", ["boss_theme.ogg", "boss_phase2.ogg"])

    # ---------------- Mixer init / shutdown ----------------
    def _init_mixer(self) -> None:
        try:
            # Safe defaults; if this fails, we just disable audio.
            pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
            pygame.mixer.set_num_channels(16)

            self._amb_ch[0] = pygame.mixer.Channel(0)
            self._amb_ch[1] = pygame.mixer.Channel(1)
            self._sfx_channels = [pygame.mixer.Channel(i) for i in range(2, 8)]
            self._mixer_ok = True
        except Exception:
            self._mixer_ok = False

    def shutdown(self) -> None:
        if not (self.enabled and self._mixer_ok and pygame is not None):
            return
        try:
            for ch in self._amb_ch:
                if ch is not None:
                    ch.stop()
            for ch in self._sfx_channels:
                ch.stop()
            try:
                pygame.mixer.music.stop()
            except Exception:
                pass
        except Exception:
            pass

    # ---------------- Low-level load/play helpers ----------------
    def _load(self, path: str):
        if path in self._cache:
            return self._cache[path]
        try:
            s = pygame.mixer.Sound(path)
            self._cache[path] = s
            return s
        except Exception:
            return None

    def _play_on_channel(self, ch, sound, volume: float = 1.0, loops: int = 0) -> None:
        if ch is None or sound is None:
            return
        try:
            ch.set_volume(max(0.0, min(1.0, float(volume))))
            ch.play(sound, loops=loops)
        except Exception:
            pass

    # ---------------- Public SFX API ----------------
    def play_sfx(self, group: str, name: str, volume: float = 0.85) -> bool:
        """
        Play a one-shot SFX if present. Looks under:
          assets/audio/sfx/<group>/<name>.(ogg|wav|mp3)
        If name doesn't exist, also tries "<name>_01" style variants via random file pick.
        """
        if not (self.enabled and self._mixer_ok and pygame is not None):
            return False

        folder = os.path.join(self.audio_root, "sfx", group)
        # 1) exact match attempt
        candidates = []
        for ext in AUDIO_EXTS:
            candidates.append(os.path.join(folder, name + ext))
        path = None
        for c in candidates:
            if os.path.exists(c):
                path = c
                break
        # 2) random pick as fallback (supports multiple files)
        if path is None:
            path = _first_existing_audio_file(folder)

        if path is None:
            return False

        snd = self._load(path)
        if snd is None:
            return False

        # rotate channels to avoid cutting off repeated attacks
        ch = self._sfx_channels[self._sfx_idx % len(self._sfx_channels)]
        self._sfx_idx += 1
        self._play_on_channel(ch, snd, volume=volume, loops=0)
        return True

    def play_action(self, name: str, volume: float = 0.85, fallbacks: Optional[List[str]] = None) -> bool:
        """Convenience: sfx/actions/<name> with optional fallback list."""
        if self.play_sfx("actions", name, volume=volume):
            return True
        if fallbacks:
            for fb in fallbacks:
                if self.play_sfx("actions", fb, volume=volume):
                    return True
        return False

    def play_powerup(self, name: str, volume: float = 0.9) -> bool:
        return self.play_sfx("powerups", name, volume=volume)

    # ---------------- Ambience/music context management ----------------
    def _amb_folder(self, context: str, key: str) -> str:
        return os.path.join(self.audio_root, "ambience", context, key)

    def _music_folder(self, context: str, key: str) -> str:
        return os.path.join(self.audio_root, "music", context, key)

    def _ensure_amb_layer(self, layer: int, context: str, key: str) -> None:
        folder = self._amb_folder(context, key)
        path = _first_existing_audio_file(folder)
        if path is None:
            # No file: stop layer if currently playing.
            if self._amb_ch[layer] is not None:
                try:
                    self._amb_ch[layer].stop()
                except Exception:
                    pass
            self._amb_paths[layer] = None
            return

        if self._amb_paths[layer] == path and self._amb_ch[layer] is not None and self._amb_ch[layer].get_busy():
            return

        snd = self._load(path)
        self._amb_paths[layer] = path
        self._play_on_channel(self._amb_ch[layer], snd, volume=0.0, loops=-1)

    def _set_music(self, context: str, key: str, fade_ms: int = 700) -> None:
        if not (self.enabled and self._mixer_ok and pygame is not None):
            return
        folder = self._music_folder(context, key)
        path = _first_existing_audio_file(folder)
        if path is None:
            return
        if path == self._music_path:
            return
        self._music_path = path
        try:
            pygame.mixer.music.fadeout(fade_ms)
        except Exception:
            pass
        try:
            pygame.mixer.music.load(path)
            pygame.mixer.music.set_volume(0.55)
            pygame.mixer.music.play(loops=-1, fade_ms=fade_ms)
        except Exception:
            # bad file format etc.
            self._music_path = None

    def update_overworld_biome(self, b0: str, b1: str, t: float) -> None:
        """
        Overworld ambience: 2-layer crossfade between b0 and b1 by t.
        Music: picks primary biome (b0 if t<0.5 else b1).
        """
        if not (self.enabled and self._mixer_ok and pygame is not None):
            return

        # Ensure correct context
        self._context = "overworld"
        self._dungeon_kind = None

        # Keep two layers loaded/playing
        self._ensure_amb_layer(0, "overworld", b0)
        self._ensure_amb_layer(1, "overworld", b1)

        # Volumes crossfade
        v0 = 0.65 * (1.0 - float(t))
        v1 = 0.65 * float(t)
        try:
            if self._amb_ch[0] is not None:
                self._amb_ch[0].set_volume(max(0.0, min(1.0, v0)))
            if self._amb_ch[1] is not None:
                self._amb_ch[1].set_volume(max(0.0, min(1.0, v1)))
        except Exception:
            pass

        primary = b0 if t < 0.5 else b1
        self._set_music("overworld", primary, fade_ms=900)

    def enter_dungeon(self, dungeon_kind: str = "tower_maze") -> None:
        """Switch ambience/music to dungeon context."""
        if not (self.enabled and self._mixer_ok and pygame is not None):
            return
        self._context = "dungeon"
        self._dungeon_kind = dungeon_kind

        self._ensure_amb_layer(0, "dungeon", dungeon_kind)
        # stop layer 1 to avoid mixing old biome ambience
        try:
            if self._amb_ch[1] is not None:
                self._amb_ch[1].stop()
        except Exception:
            pass
        self._amb_paths[1] = None

        # Set dungeon volumes
        try:
            if self._amb_ch[0] is not None:
                self._amb_ch[0].set_volume(0.75)
        except Exception:
            pass

        self._set_music("dungeon", dungeon_kind, fade_ms=900)

    def exit_dungeon(self) -> None:
        """Dungeon -> overworld transition; overworld layers will resume on next update_overworld_biome call."""
        if not (self.enabled and self._mixer_ok and pygame is not None):
            return
        # Stop dungeon ambience now; overworld update will restart correct layers
        try:
            for ch in self._amb_ch:
                if ch is not None:
                    ch.stop()
        except Exception:
            pass
        self._amb_paths = [None, None]
        self._context = "overworld"
        self._dungeon_kind = None
        # Do not force music here; overworld update will pick correct track.
