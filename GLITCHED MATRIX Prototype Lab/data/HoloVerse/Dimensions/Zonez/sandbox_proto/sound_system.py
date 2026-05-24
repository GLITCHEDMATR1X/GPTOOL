from __future__ import annotations

import random
from pathlib import Path

from direct.showbase import Audio3DManager
from panda3d.core import AudioSound, Filename, NodePath


class ZoneAudio:
    def __init__(self, app, project_root: Path):
        self.app = app
        self.project_root = Path(project_root)
        self.sfx_root = self.project_root / 'assets' / 'sfx'
        self.enabled = False
        self.audio3d = None
        self._rng = random.Random(91357)
        self._ambient_loops: list[AudioSound] = []
        self._transient_3d: list[AudioSound] = []
        self._boundary_timer = 0.0
        self._player_loop: AudioSound | None = None
        self._player_loop_base_volume = 0.16
        self._monster_sound_map = {
            'elf': ('zone/elf_chime.wav', (4.0, 7.5), 0.34, 5.0, 40.0),
            'human': ('zone/human_chirp.wav', (5.0, 8.0), 0.30, 5.0, 42.0),
            'robot_npc': ('zone/robot_beep.wav', (3.5, 6.0), 0.34, 5.0, 40.0),
            'cactus_sage': ('zone/cactus_bloom.wav', (5.5, 9.0), 0.38, 6.0, 42.0),
            'hell': ('zone/hell_grumble.wav', (5.5, 8.5), 0.34, 12.0, 60.0),
            'dread': ('zone/dread_whisper.wav', (7.0, 11.0), 0.38, 12.0, 72.0),
            'whale': ('zone/whale_bloop.wav', (6.0, 10.0), 0.40, 14.0, 84.0),
            'snowflake': ('zone/snow_tinkle.wav', (6.0, 10.0), 0.16, 8.0, 30.0),
        }
        try:
            if getattr(self.app, 'sfxManagerList', None):
                self.audio3d = Audio3DManager.Audio3DManager(self.app.sfxManagerList[0], self.app.camera)
                self.audio3d.setDistanceFactor(1.0)
                self.audio3d.setDropOffFactor(1.08)
                self.enabled = True
        except Exception:
            self.audio3d = None
            self.enabled = False
        self._setup_player_loop()

    def _to_filename(self, path: Path) -> Filename:
        return Filename.fromOsSpecific(str(path.resolve()))

    def _load_2d(self, relative_path: str) -> AudioSound | None:
        if not self.enabled:
            return None
        path = self.sfx_root / relative_path
        if not path.exists():
            return None
        try:
            return self.app.loader.loadSfx(self._to_filename(path))
        except Exception:
            try:
                return self.app.loader.loadSfx(str(path).replace('\\', '/'))
            except Exception:
                return None

    def _load_3d(self, relative_path: str) -> AudioSound | None:
        if not self.enabled or self.audio3d is None:
            return None
        path = self.sfx_root / relative_path
        if not path.exists():
            return None
        try:
            return self.audio3d.loadSfx(self._to_filename(path))
        except Exception:
            try:
                return self.audio3d.loadSfx(str(path).replace('\\', '/'))
            except Exception:
                return None

    def _setup_player_loop(self) -> None:
        self._player_loop = self._load_2d('world/rotor_loop.wav')
        if self._player_loop is None:
            return
        self._player_loop.setLoop(True)
        self._player_loop.setVolume(0.0)
        self._player_loop.play()

    def _play_sound(self, sound: AudioSound | None, volume: float = 1.0) -> None:
        if sound is None:
            return
        try:
            sound.setVolume(max(0.0, min(1.0, volume)))
            sound.stop()
            sound.play()
        except Exception:
            return

    def play_ui(self, cue: str) -> None:
        mapping = {
            'portal_open': ('ui/portal_open.wav', 0.42),
            'portal_close': ('ui/portal_close.wav', 0.38),
            'zone_switch': ('ui/zone_switch.wav', 0.48),
            'pause_on': ('ui/pause_on.wav', 0.32),
            'pause_off': ('ui/pause_off.wav', 0.34),
            'loading_done': ('ui/loading_done.wav', 0.42),
        }
        spec = mapping.get(cue)
        if spec is None:
            return
        path, volume = spec
        self._play_sound(self._load_2d(path), volume)

    def play_boundary(self, node: NodePath) -> None:
        if not self.enabled or self.audio3d is None:
            return
        if self._boundary_timer > 0.0:
            return
        self._boundary_timer = 0.16
        self._play_attached_once(node, 'world/boundary_boop.wav', 0.36, 4.0, 26.0)

    def _play_attached_once(self, node: NodePath, relative_path: str, volume: float, min_distance: float, max_distance: float) -> None:
        if not self.enabled or self.audio3d is None or node is None or node.isEmpty():
            return
        sound = self._load_3d(relative_path)
        if sound is None:
            return
        try:
            sound.setVolume(max(0.0, min(1.0, volume)))
            sound.set3dMinDistance(min_distance)
            sound.set3dMaxDistance(max_distance)
            self.audio3d.attachSoundToObject(sound, node)
            sound.play()
            self._transient_3d.append(sound)
        except Exception:
            return

    def _attach_loop(self, node: NodePath, relative_path: str, volume: float, min_distance: float, max_distance: float) -> None:
        if not self.enabled or self.audio3d is None or node is None or node.isEmpty():
            return
        sound = self._load_3d(relative_path)
        if sound is None:
            return
        try:
            sound.setLoop(True)
            sound.setVolume(max(0.0, min(1.0, volume)))
            sound.set3dMinDistance(min_distance)
            sound.set3dMaxDistance(max_distance)
            self.audio3d.attachSoundToObject(sound, node)
            sound.play()
            self._ambient_loops.append(sound)
        except Exception:
            return

    def _stop_all_ambient(self) -> None:
        for sound in self._ambient_loops:
            try:
                sound.stop()
            except Exception:
                pass
        self._ambient_loops.clear()

    def refresh_zone_audio(self, zone_key: str, zone_root: NodePath, zone_monsters: list[dict]) -> None:
        if not self.enabled:
            return
        self._stop_all_ambient()

        if zone_root is not None and not zone_root.isEmpty():
            boundary = zone_root.find('**/world_boundary')
            if boundary is not None and not boundary.isEmpty():
                self._attach_loop(boundary, 'world/boundary_glow.wav', 0.08, 16.0, 128.0)

            if zone_key == 'tropical_zone':
                ocean = zone_root.find('**/tropical_ocean')
                if ocean is not None and not ocean.isEmpty():
                    self._attach_loop(ocean, 'zone/ocean_loop.wav', 0.18, 18.0, 120.0)
            elif zone_key == 'tech_zone':
                city = zone_root.find('**/tech_cityscape')
                if city is not None and not city.isEmpty():
                    self._attach_loop(city, 'zone/city_hum.wav', 0.15, 14.0, 92.0)

        first_glowbug = True
        first_snow = True
        for monster in zone_monsters:
            mtype = monster.get('type')
            root = monster.get('root')
            if root is None or root.isEmpty():
                continue
            spec = self._monster_sound_map.get(mtype)
            if spec is not None:
                monster['sound_timer'] = self._rng.uniform(*spec[1])
                monster['sound_spec'] = spec
            if mtype == 'glowbug' and first_glowbug:
                self._attach_loop(root, 'zone/glowbug_buzz.wav', 0.10, 4.0, 24.0)
                first_glowbug = False
            elif mtype == 'candy_blimp':
                self._attach_loop(root, 'zone/blimp_whistle.wav', 0.10, 10.0, 72.0)
            elif mtype == 'hell':
                self._attach_loop(root, 'zone/hell_grumble.wav', 0.08, 14.0, 68.0)
            elif mtype == 'dread':
                self._attach_loop(root, 'zone/dread_whisper.wav', 0.08, 14.0, 72.0)
            elif mtype == 'snowflake' and first_snow:
                self._attach_loop(root, 'zone/snow_tinkle.wav', 0.05, 8.0, 28.0)
                first_snow = False

    def update(self, dt: float, player, zone_monsters: list[dict], *, active: bool) -> None:
        if not self.enabled:
            return
        if self._boundary_timer > 0.0:
            self._boundary_timer = max(0.0, self._boundary_timer - dt)

        # Clean finished one-shots.
        alive: list[AudioSound] = []
        for sound in self._transient_3d:
            try:
                if sound.status() == AudioSound.PLAYING:
                    alive.append(sound)
            except Exception:
                pass
        self._transient_3d = alive

        if self._player_loop is not None:
            try:
                target_volume = 0.0
                if active:
                    speed_ratio = min(1.0, max(0.0, float(getattr(player, 'last_flat_speed', 0.0)) / 7.0))
                    target_volume = self._player_loop_base_volume + speed_ratio * 0.18
                current = self._player_loop.getVolume()
                self._player_loop.setVolume(current + (target_volume - current) * min(1.0, dt * 5.0))
                if self._player_loop.status() != AudioSound.PLAYING:
                    self._player_loop.play()
            except Exception:
                pass

        if not active:
            return

        player_pos = player.pos
        for monster in zone_monsters:
            root = monster.get('root')
            spec = monster.get('sound_spec')
            if root is None or root.isEmpty() or spec is None:
                continue
            sound_rel, interval_range, volume, min_distance, max_distance = spec
            timer = monster.get('sound_timer', self._rng.uniform(*interval_range)) - dt
            if timer > 0.0:
                monster['sound_timer'] = timer
                continue
            # Only trigger local one-shots when close enough to matter.
            dx = root.getX() - player_pos.x
            dy = root.getY() - player_pos.y
            if dx * dx + dy * dy <= (max_distance * 0.82) * (max_distance * 0.82):
                self._play_attached_once(root, sound_rel, volume, min_distance, max_distance)
            monster['sound_timer'] = self._rng.uniform(*interval_range)
