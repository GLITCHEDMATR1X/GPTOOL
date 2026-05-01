
from __future__ import annotations

import json
import math
import random
import struct
import sys
import time
import traceback
import wave
from dataclasses import asdict, dataclass, field
from pathlib import Path

from direct.gui.DirectGui import DirectButton, DirectFrame, DirectLabel
from direct.showbase.ShowBase import ShowBase
from direct.showbase.ShowBaseGlobal import globalClock
from direct.task import Task
from panda3d.core import (
    AmbientLight,
    AntialiasAttrib,
    Filename,
    Fog,
    InputDevice,
    LineSegs,
    MatrixLens,
    NodePath,
    TextNode,
    TransparencyAttrib,
    Vec2,
    Vec3,
    Vec4,
    WindowProperties,
    load_prc_file_data,
)

from .p3dopenxr import P3DOpenXR
from .version import __version__

APP_NAME = 'Etchline XR World Walk'
PACKAGE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_ROOT.parent
APP_ROOT = PROJECT_ROOT if (PROJECT_ROOT / 'main.py').exists() else Path.cwd()
ASSETS_DIR = APP_ROOT / 'assets'
MUSIC_DIR = ASSETS_DIR / 'music'
LOG_DIR = APP_ROOT / 'logs'
PATCH_DIR = APP_ROOT / 'patch_notes'
CRASH_DIR = LOG_DIR / 'crash_reports'
SCREENSHOT_DIR = LOG_DIR / 'screenshots'
CONFIG_PATH = APP_ROOT / 'xr_world_walk_config.json'
PLACEHOLDER_MUSIC = MUSIC_DIR / 'placeholder_loop.wav'

load_prc_file_data(
    '',
    '\n'.join(
        [
            f'window-title {APP_NAME}',
            'sync-video 1',
            'framebuffer-srgb false',
            'framebuffer-multisample 0',
            'multisamples 0',
            'win-size 1600 900',
            'show-frame-rate-meter 0',
            'texture-anisotropic-degree 4',
            'cursor-hidden 1',
            'notify-level-display warning',
            'notify-level-glgsg warning',
            'audio-library-name p3openal_audio',
        ]
    ),
)

WORLD_COLOR_PRESETS = [
    ('Noir', (0.05, 0.05, 0.06)),
    ('Cobalt', (0.04, 0.07, 0.14)),
    ('Violet', (0.07, 0.05, 0.11)),
    ('Rust', (0.12, 0.06, 0.04)),
    ('Emerald', (0.03, 0.10, 0.08)),
]
LINE_COLOR_PRESETS = [
    ('Ivory', (0.92, 0.92, 0.89)),
    ('Cyan', (0.60, 0.95, 1.00)),
    ('Amber', (1.00, 0.85, 0.44)),
    ('Rose', (1.00, 0.68, 0.78)),
    ('Lime', (0.76, 1.00, 0.62)),
]
DIALOGUE_BANK = [
    'Signal is quiet tonight. The city is thinking.',
    'Walk slow. The linework shifts when rushed.',
    'We patrol, but nothing here wants war anymore.',
    'Those ships overhead never land where you expect.',
    'Every district redraws itself a little after midnight.',
    'You look calibrated now. Better than before.',
    'The skyline remembers older versions of us.',
    'The plazas are safer than the bridges in bad weather.',
]


@dataclass
class WorldConfig:
    chunk_size: int = 72
    active_chunk_radius: int = 3
    max_view_distance: float = 620.0
    fog_start_ratio: float = 0.52
    line_thickness: float = 1.25
    line_jitter: float = 0.025
    movement_speed: float = 2.55
    sprint_multiplier: float = 1.45
    turn_speed: float = 95.0
    player_height_m: float = 1.8288
    eye_height_m: float = 1.70
    player_radius: float = 0.42
    show_hud: bool = False
    world_color_index: int = 0
    line_color_index: int = 0
    music_enabled: bool = True
    music_volume: float = 0.32
    world_seed: int = 74219
    mirror_mode: str = 'average'
    xr_floor_settle_delay: float = 0.85
    xr_floor_sample_window: int = 10
    xr_floor_raise_bias: float = 0.04
    xr_floor_stage_min_head: float = 0.9
    xr_floor_local_min_head: float = 0.35
    vr_performance_mode: bool = True
    projectile_budget_player: int = 18
    projectile_budget_enemy: int = 10
    effect_budget: int = 24
    walker_budget: int = 24
    skyline_detail_distance: float = 220.0
    palette_refresh_hz: float = 10.0


@dataclass
class BoxBounds:
    min_v: Vec3
    max_v: Vec3
    normal_hint: Vec3


@dataclass
class WalkerNPC:
    root: NodePath
    body: NodePath
    radius: float
    height: float
    wander_dir: Vec3
    wander_timer: float
    speed: float
    phase: float
    seed: int
    label: str
    talk_cooldown: float = 0.0
    health: float = 100.0
    max_health: float = 100.0
    launch_velocity: Vec3 = field(default_factory=lambda: Vec3(0, 0, 0))
    alert_timer: float = 0.0
    fire_flash: float = 0.0
    destroyed_timer: float = 0.0
    aggressive: bool = False
    attack_cooldown: float = 0.0
    stagger_timer: float = 0.0
    cut_flash: float = 0.0
    hover_height: float = 0.0


@dataclass
class SkyShip:
    root: NodePath
    velocity: Vec3
    lifetime: float
    phase: float


@dataclass
class ClawHand:
    root: NodePath
    palm: NodePath
    finger_nodes: list[NodePath]
    side: str


@dataclass
class WristBlaster:
    root: NodePath
    muzzle: NodePath
    side: str
    kind: str = 'blaster'
    blade: NodePath | None = None
    cooldown: float = 0.0
    recoil: float = 0.0
    charge: float = 0.0
    swing: float = 0.0
    swing_dir: float = 1.0
    combo_step: int = 0
    combo_timer: float = 0.0
    heat: float = 0.0


@dataclass
class PlasmaBolt:
    root: NodePath
    velocity: Vec3
    ttl: float
    side: str
    damage: float
    radius: float


@dataclass
class ImpactBurst:
    root: NodePath
    ttl: float
    max_ttl: float


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _lerp3(a: tuple[float, float, float], b: tuple[float, float, float], t: float) -> tuple[float, float, float]:
    return (_lerp(a[0], b[0], t), _lerp(a[1], b[1], t), _lerp(a[2], b[2], t))


def _rgb_to_hsv(rgb: tuple[float, float, float]) -> tuple[float, float, float]:
    r, g, b = rgb
    mx = max(r, g, b)
    mn = min(r, g, b)
    d = mx - mn
    if d == 0:
        h = 0.0
    elif mx == r:
        h = ((g - b) / d) % 6.0
    elif mx == g:
        h = (b - r) / d + 2.0
    else:
        h = (r - g) / d + 4.0
    h /= 6.0
    s = 0.0 if mx == 0 else d / mx
    return h, s, mx


def _hsv_to_rgb(h: float, s: float, v: float) -> tuple[float, float, float]:
    h = (h % 1.0) * 6.0
    i = int(h)
    f = h - i
    p = v * (1.0 - s)
    q = v * (1.0 - s * f)
    t = v * (1.0 - s * (1.0 - f))
    if i == 0:
        return v, t, p
    if i == 1:
        return q, v, p
    if i == 2:
        return p, v, t
    if i == 3:
        return p, q, v
    if i == 4:
        return t, p, v
    return v, p, q


def _rotate_hue(rgb: tuple[float, float, float], amount: float, sat_scale: float = 1.0, val_scale: float = 1.0) -> tuple[float, float, float]:
    h, s, v = _rgb_to_hsv(rgb)
    return _hsv_to_rgb(h + amount, _clamp01(s * sat_scale), _clamp01(v * val_scale))


def ensure_dirs() -> None:
    for path in (ASSETS_DIR, MUSIC_DIR, LOG_DIR, PATCH_DIR, CRASH_DIR, SCREENSHOT_DIR):
        path.mkdir(exist_ok=True, parents=True)



def _is_runtime_unavailable(exc: BaseException) -> bool:
    names = {exc.__class__.__name__, exc.__class__.__qualname__}
    return 'RuntimeUnavailableError' in names or ('runtime' in str(exc).lower() and 'unavailable' in str(exc).lower())



def write_crash_report(exc: BaseException) -> Path:
    ensure_dirs()
    stamp = time.strftime('%Y%m%d_%H%M%S')
    path = CRASH_DIR / f'crash_{stamp}.log'
    path.write_text(''.join(traceback.format_exception(exc)), encoding='utf-8')
    return path



def write_patch_notes(force: bool = True) -> Path:
    ensure_dirs()
    existing = sorted(PATCH_DIR.glob('patch_*.md'))
    if not force and existing:
        return existing[-1]
    stamp = time.strftime('%Y%m%d_%H%M%S')
    path = PATCH_DIR / f'patch_{stamp}.md'
    body = (
        f'# Patch Notes - {APP_NAME} {__version__}\n\n'
        '- Stabilized floor calibration around a 6-foot-tall standing profile with a 1.70m eye line.\n'
        '- Added tracking-space-aware floor settling, median head-height sampling, and a manual floor set action.\n'
        '- Reworked XR anchor handling to stop head-height floor flips and reduce recenter jitter.\n'
        '- Slowed ambient walkers and added interaction dialogue when you approach them.\n'
        '- Added color customization for world and line palettes with automatic config saving.\n'
        '- Added replaceable looping music placeholder in assets/music.\n'
        '- Added robotic claw hands for controller-tracked XR presence, stars, and occasional overhead ships.\n'
        '- Added a slow day/night hue cycle for the grid and structures with low-cost palette updates.\n'
        '- Replaced the left wrist blaster with a long sword and upgraded the right-hand blaster silhouette.\n'
        '- Tightened rendering cost with calmer palette updates, lighter sky effects, and fewer active transient systems.\n'
        '- Extended the visual cycle so the grid, structure lines, and skyline drift through longer hue and saturation changes.\n'
        '- Added a slow inversion pass that gradually pushes background and line colors toward opposite values across the day/night cycle.\n'
    )
    path.write_text(body, encoding='utf-8')
    return path



def ensure_placeholder_music() -> None:
    ensure_dirs()
    if PLACEHOLDER_MUSIC.exists():
        return
    sample_rate = 22050
    duration = 12.0
    total = int(sample_rate * duration)
    rng = random.Random(90210)
    with wave.open(str(PLACEHOLDER_MUSIC), 'wb') as wav_f:
        wav_f.setnchannels(1)
        wav_f.setsampwidth(2)
        wav_f.setframerate(sample_rate)
        frames = bytearray()
        for i in range(total):
            t = i / sample_rate
            env = 0.5 - 0.5 * math.cos(min(1.0, t / 1.5) * math.pi)
            release = 0.5 - 0.5 * math.cos(min(1.0, (duration - t) / 1.5) * math.pi)
            env *= release
            tone = (
                0.55 * math.sin(math.tau * 55.0 * t)
                + 0.22 * math.sin(math.tau * 82.5 * t)
                + 0.12 * math.sin(math.tau * (110.0 + 8.0 * math.sin(t * 0.3)) * t)
            )
            shimmer = 0.04 * math.sin(math.tau * 420.0 * t + math.sin(t * 1.7) * 1.5)
            noise = 0.015 * rng.uniform(-1.0, 1.0)
            sample = max(-1.0, min(1.0, (tone + shimmer + noise) * 0.25 * env))
            frames.extend(struct.pack('<h', int(sample * 32767)))
        wav_f.writeframes(frames)



def _yaw_from_vec(vec: Vec3) -> float:
    if vec.length_squared() < 1e-8:
        return 0.0
    return math.degrees(math.atan2(-vec.x, vec.y))


class XRWorldWalk(ShowBase):
    def __init__(self):
        ensure_dirs()
        ensure_placeholder_music()
        self.patch_note_path = write_patch_notes(force=True)
        super().__init__()
        self.disableMouse()
        self.win.set_clear_color_active(True)

        self.user_config = self._load_config()
        self.hud_visible = bool(self.user_config.get('show_hud', False))
        self.settings_visible = False
        self._clamp_config()
        self.status_lines: list[str] = []
        self.keys: dict[str, bool] = {}
        self.elapsed = 0.0
        self.day_mix = 0.0
        self.day_phase = 0.0
        self.day_hue_shift = 0.0
        self.long_hue_shift = 0.0
        self.long_sat_scale = 1.0
        self.invert_mix = 0.0
        self.palette_bg_rgb = (0.02, 0.03, 0.04)
        self.palette_line_rgb = self._line_rgb()
        self.palette_refresh_timer = 0.0
        self.walker_tick_toggle = False
        self.player_root = self.render.attach_new_node('player-root')
        self.player_root.set_pos(0, 0, 0)
        self.spawn_safe_z = 0.0
        self.player_heading = 0.0
        self.player_height_m = float(self.user_config.get('player_height_m', 2.02))
        self.eye_height_m = float(self.user_config.get('eye_height_m', 1.84))
        self.player_radius = float(self.user_config.get('player_radius', 0.42))
        self.floor_offset_z = 0.0
        self.xr_floor_calibrated = False
        self.xr_tracking_space_name = 'unknown'
        self.xr_floor_settle_timer = 0.0
        self.xr_floor_samples: list[float] = []
        self.xr_floor_pending = False
        self.last_local_head_z: float | None = None
        self.last_local_head_yaw: float | None = None
        self.desktop_pitch = -9.0
        self.walkers: list[WalkerNPC] = []
        self.walker_nodes_by_chunk: dict[tuple[int, int], list[WalkerNPC]] = {}
        self.chunks: dict[tuple[int, int], NodePath] = {}
        self.chunk_obstacles: dict[tuple[int, int], list[BoxBounds]] = {}
        self.chunk_npc_spawns: dict[tuple[int, int], list[tuple[float, float, int]]] = {}
        self.xr: P3DOpenXR | None = None
        self.music = None
        self.music_active = False
        self.dialogue_timer = 0.0
        self.dialogue_text = ''
        self.dialogue_speaker = ''
        self.prev_interact_down = False
        self.prev_recenter_down = False
        self.prev_menu_down = False
        self.sky_ships: list[SkyShip] = []
        self.next_ship_timer = 6.0
        self._last_palette_key = None
        self.left_claw: ClawHand | None = None
        self.right_claw: ClawHand | None = None
        self.left_blaster: WristBlaster | None = None
        self.right_blaster: WristBlaster | None = None
        self.bolts: list[PlasmaBolt] = []
        self.impact_bursts: list[ImpactBurst] = []
        self.prev_fire_left_down = False
        self.prev_fire_right_down = False
        self.last_parry_timer = 0.0
        self.parry_flash_timer = 0.0

        self.accept('escape', self.toggle_settings)
        self.accept('h', self.toggle_hud)
        self.accept('f', self._set_key, ['interact', True])
        self.accept('f-up', self._set_key, ['interact', False])
        self.accept('r', self._set_key, ['recenter', True])
        self.accept('r-up', self._set_key, ['recenter', False])
        self.accept('g', self._set_floor_to_current_head)
        self.accept('mouse1', self._set_key, ['fire_left', True])
        self.accept('mouse1-up', self._set_key, ['fire_left', False])
        self.accept('mouse3', self._set_key, ['fire_right', True])
        self.accept('mouse3-up', self._set_key, ['fire_right', False])
        self.accept('z', self._set_key, ['fire_left', True])
        self.accept('z-up', self._set_key, ['fire_left', False])
        self.accept('c', self._set_key, ['fire_right', True])
        self.accept('c-up', self._set_key, ['fire_right', False])
        self.accept('w', self._set_key, ['w', True])
        self.accept('w-up', self._set_key, ['w', False])
        self.accept('a', self._set_key, ['a', True])
        self.accept('a-up', self._set_key, ['a', False])
        self.accept('s', self._set_key, ['s', True])
        self.accept('s-up', self._set_key, ['s', False])
        self.accept('d', self._set_key, ['d', True])
        self.accept('d-up', self._set_key, ['d', False])
        self.accept('shift', self._set_key, ['shift', True])
        self.accept('shift-up', self._set_key, ['shift', False])
        self.accept('q', self._set_key, ['turn_left', True])
        self.accept('q-up', self._set_key, ['turn_left', False])
        self.accept('e', self._set_key, ['turn_right', True])
        self.accept('e-up', self._set_key, ['turn_right', False])
        self.accept('arrow_left', self._set_key, ['turn_left', True])
        self.accept('arrow_left-up', self._set_key, ['turn_left', False])
        self.accept('arrow_right', self._set_key, ['turn_right', True])
        self.accept('arrow_right-up', self._set_key, ['turn_right', False])
        self.accept('f12', self.capture_screenshot)

        self.render.setAntialias(AntialiasAttrib.MLine)
        self.render.setTransparency(TransparencyAttrib.MAlpha)
        self._build_scene()
        self._build_ui()
        self._setup_music()

        try:
            self.xr = P3DOpenXR(self)
            self.xr.init(mirroring=1, mirror_mode=self.user_config.get('mirror_mode', 'average'), near=0.03, far=float(self.user_config.get('max_view_distance', 620.0)))
            self._build_claws()
            self._build_blasters()
            self.status_lines.append('XR bridge initialized.')
        except Exception as exc:
            self.xr = None
            if _is_runtime_unavailable(exc):
                self.status_lines.append('OpenXR runtime not found. Running in desktop fallback mode.')
            else:
                crash_path = write_crash_report(exc)
                self.status_lines.append(f'XR startup failed: {crash_path.name}')
                self.status_lines.append(str(exc))

        if self.xr is None:
            props = WindowProperties()
            props.setCursorHidden(True)
            self.win.requestProperties(props)
            self.camera.set_pos(0, -2.0, self.eye_height_m)
            self.camera.look_at(0, 6.0, 1.6)
            self._build_blasters()
        else:
            self._calibrate_floor(force=True)

        self._adjust_runtime_budgets()
        self.generate_city_around_player(force=True)
        self.taskMgr.add(self._update_world_task, 'xr-world-walk-update')
        self.taskMgr.add(self._update_ui_task, 'xr-world-walk-ui')
        self.taskMgr.add(self._late_sky_task, 'xr-world-walk-sky', sort=50)

    def _load_config(self) -> dict:
        user_config = asdict(WorldConfig())
        if CONFIG_PATH.exists():
            try:
                user_config.update(json.loads(CONFIG_PATH.read_text(encoding='utf-8')))
            except Exception:
                pass
        CONFIG_PATH.write_text(json.dumps(user_config, indent=2), encoding='utf-8')
        return user_config

    def _clamp_config(self) -> None:
        self.user_config['world_color_index'] = int(self.user_config.get('world_color_index', 0)) % len(WORLD_COLOR_PRESETS)
        self.user_config['line_color_index'] = int(self.user_config.get('line_color_index', 0)) % len(LINE_COLOR_PRESETS)
        self.user_config['player_height_m'] = 2.02
        self.user_config['eye_height_m'] = 1.84
        self.user_config['movement_speed'] = max(1.4, min(5.5, float(self.user_config.get('movement_speed', 2.55))))
        self.user_config['turn_speed'] = max(45.0, min(180.0, float(self.user_config.get('turn_speed', 95.0))))
        self.user_config['music_volume'] = max(0.0, min(1.0, float(self.user_config.get('music_volume', 0.32))))
        self.user_config['max_view_distance'] = max(280.0, min(1200.0, float(self.user_config.get('max_view_distance', 620.0))))
        self.user_config['vr_performance_mode'] = bool(self.user_config.get('vr_performance_mode', True))
        self.user_config['projectile_budget_player'] = max(8, min(48, int(self.user_config.get('projectile_budget_player', 18))))
        self.user_config['projectile_budget_enemy'] = max(4, min(32, int(self.user_config.get('projectile_budget_enemy', 10))))
        self.user_config['effect_budget'] = max(8, min(64, int(self.user_config.get('effect_budget', 24))))
        self.user_config['walker_budget'] = max(8, min(72, int(self.user_config.get('walker_budget', 24))))
        self.user_config['skyline_detail_distance'] = max(96.0, min(480.0, float(self.user_config.get('skyline_detail_distance', 220.0))))
        self.user_config['palette_refresh_hz'] = max(3.0, min(30.0, float(self.user_config.get('palette_refresh_hz', 10.0))))
        if self.user_config['vr_performance_mode']:
            self.user_config['active_chunk_radius'] = min(int(self.user_config.get('active_chunk_radius', 3)), 2)
            self.user_config['max_view_distance'] = min(float(self.user_config.get('max_view_distance', 620.0)), 560.0)
        self._save_config()

    def _save_config(self) -> None:
        self.user_config['show_hud'] = self.hud_visible
        self.user_config['last_patch_note'] = self.patch_note_path.name
        self.user_config['last_patch_version'] = __version__
        CONFIG_PATH.write_text(json.dumps(self.user_config, indent=2), encoding='utf-8')

    def _append_status(self, line: str) -> None:
        self.status_lines.append(line)
        self.status_lines = self.status_lines[-10:]

    def _set_key(self, key: str, value: bool) -> None:
        self.keys[key] = value

    def _perf_mode(self) -> bool:
        return bool(self.user_config.get('vr_performance_mode', True))

    def _adjust_runtime_budgets(self) -> None:
        if self._perf_mode():
            self.user_config['projectile_budget_player'] = min(int(self.user_config.get('projectile_budget_player', 18)), 18)
            self.user_config['projectile_budget_enemy'] = min(int(self.user_config.get('projectile_budget_enemy', 10)), 10)
            self.user_config['effect_budget'] = min(int(self.user_config.get('effect_budget', 24)), 24)
            self.user_config['walker_budget'] = min(int(self.user_config.get('walker_budget', 24)), 24)
        self._prune_runtime_load()

    def _prune_runtime_load(self) -> None:
        player_budget = int(self.user_config.get('projectile_budget_player', 18))
        enemy_budget = int(self.user_config.get('projectile_budget_enemy', 10))
        effect_budget = int(self.user_config.get('effect_budget', 24))
        player_bolts = [b for b in self.bolts if b.side != 'enemy']
        enemy_bolts = [b for b in self.bolts if b.side == 'enemy']
        while len(player_bolts) > player_budget:
            bolt = player_bolts.pop(0)
            if bolt in self.bolts:
                bolt.root.remove_node()
                self.bolts.remove(bolt)
        while len(enemy_bolts) > enemy_budget:
            bolt = enemy_bolts.pop(0)
            if bolt in self.bolts:
                bolt.root.remove_node()
                self.bolts.remove(bolt)
        while len(self.impact_bursts) > effect_budget:
            burst = self.impact_bursts.pop(0)
            burst.root.remove_node()
        walker_budget = int(self.user_config.get('walker_budget', 24))
        if len(self.walkers) > walker_budget:
            head = self._head_world_pos()
            ranked = sorted(self.walkers, key=lambda w: (w.root.get_pos(self.render) - head).length_squared(), reverse=True)
            for walker in ranked[: len(self.walkers) - walker_budget]:
                for chunk_key, chunk_walkers in self.walker_nodes_by_chunk.items():
                    if walker in chunk_walkers:
                        chunk_walkers.remove(walker)
                        break
                if walker in self.walkers:
                    self.walkers.remove(walker)
                walker.root.remove_node()

    def _setup_music(self) -> None:
        self.music_active = False
        try:
            if not bool(self.user_config.get('music_enabled', True)):
                return
            music_path = PLACEHOLDER_MUSIC
            panda_path = Filename.fromOsSpecific(str(music_path))
            self.music = self.loader.loadMusic(panda_path)
            if self.music is not None:
                self.music.setLoop(True)
                self.music.setVolume(float(self.user_config.get('music_volume', 0.32)))
                self.music.play()
                self.music_active = True
        except Exception as exc:
            self.music = None
            self._append_status(f'Music unavailable: {exc}')

    def _apply_music_state(self) -> None:
        if self.music is None:
            return
        enabled = bool(self.user_config.get('music_enabled', True))
        try:
            self.music.setVolume(float(self.user_config.get('music_volume', 0.32)))
            if enabled and not self.music.status() == self.music.PLAYING:
                self.music.setLoop(True)
                self.music.play()
            elif not enabled and self.music.status() == self.music.PLAYING:
                self.music.stop()
        except Exception:
            pass

    def _build_scene(self) -> None:
        self.city_root = self.render.attach_new_node('city-root')
        ambient = AmbientLight('ambient')
        ambient.set_color((1.0, 1.0, 1.0, 1.0))
        self.render.set_light(self.render.attach_new_node(ambient))
        self.fog = Fog('distance-fog')
        max_view = float(self.user_config.get('max_view_distance', 620.0))
        self.fog.setExpDensity(0.0)
        self.fog.setLinearRange(max_view * float(self.user_config.get('fog_start_ratio', 0.52)), max_view)
        self.render.setFog(self.fog)
        self.camLens.setNearFar(0.03, max_view)
        self.camLens.setFov(82)
        self.ground_root = self.render.attach_new_node('ground-root')
        self._draw_ground_grid(self.ground_root, span=1400.0, step=14.0)
        self.sky_root = self.render.attach_new_node('sky-root')
        self.sky_root.setBin('background', 0)
        self.sky_root.setDepthWrite(False)
        self.sky_root.setDepthTest(False)
        self.ship_root = self.render.attach_new_node('ship-root')
        self.fx_root = self.render.attach_new_node('fx-root')
        self.projectile_root = self.fx_root.attach_new_node('projectile-root')
        self.impact_root = self.fx_root.attach_new_node('impact-root')
        self._build_star_field()
        self.update_palette(0.0, force=True)

    def _draw_ground_grid(self, parent: NodePath, span: float, step: float) -> None:
        segs = LineSegs('ground-grid')
        segs.setThickness(0.8)
        segs.setColor(0.15, 0.15, 0.15, 0.22)
        half = span * 0.5
        count = int(span / step)
        for i in range(count + 1):
            x = -half + i * step
            segs.moveTo(x, -half, 0)
            segs.drawTo(x, half, 0)
            y = -half + i * step
            segs.moveTo(-half, y, 0)
            segs.drawTo(half, y, 0)
        np = parent.attach_new_node(segs.create())
        np.set_z(-0.045)
        np.setAntialias(AntialiasAttrib.MLine)
        np.setTransparency(TransparencyAttrib.MAlpha)
        np.setDepthWrite(False)

    def _build_star_field(self) -> None:
        rng = random.Random(1937)
        segs = LineSegs('stars')
        segs.setThickness(1.0)
        for _ in range(140):
            theta = rng.uniform(0.0, math.tau)
            phi = rng.uniform(0.12, 0.46 * math.pi)
            radius = rng.uniform(260.0, 420.0)
            x = math.cos(theta) * math.sin(phi) * radius
            y = math.sin(theta) * math.sin(phi) * radius
            z = math.cos(phi) * radius + 100.0
            s = rng.uniform(0.2, 0.75)
            segs.setColor(1.0, 1.0, 1.0, rng.uniform(0.18, 0.45))
            segs.moveTo(x - s, y, z)
            segs.drawTo(x + s, y, z)
            segs.moveTo(x, y - s, z)
            segs.drawTo(x, y + s, z)
        self.star_np = self.sky_root.attach_new_node(segs.create())
        self.star_np.setTransparency(TransparencyAttrib.MAlpha)
        self.star_np.setDepthWrite(False)
        self.star_np.setDepthTest(False)

    def _spawn_sky_ship(self) -> None:
        rng = random.Random(int(self.elapsed * 1000) ^ 58123 ^ len(self.sky_ships) * 37)
        start_side = rng.choice([-1, 1])
        player = self.player_root.get_pos(self.render)
        start = Vec3(player.x + start_side * rng.uniform(110.0, 160.0), player.y + rng.uniform(-40.0, 40.0), rng.uniform(72.0, 118.0))
        end = Vec3(player.x - start_side * rng.uniform(110.0, 160.0), player.y + rng.uniform(-80.0, 80.0), start.z + rng.uniform(-8.0, 8.0))
        direction = end - start
        if direction.length_squared() < 0.01:
            return
        speed = rng.uniform(8.0, 14.0)
        velocity = direction.normalized() * speed
        lifetime = direction.length() / speed
        root = self.ship_root.attach_new_node(f'sky-ship-{int(self.elapsed*1000)}')
        root.set_pos(start)
        body = LineSegs('sky-ship')
        body.setThickness(1.3)
        body.setColor(*self._ship_color(alpha=0.65))
        outline = [
            ((-2.8, 0.0, 0.0), (-1.1, 2.4, 0.0)),
            ((-1.1, 2.4, 0.0), (1.9, 1.2, 0.0)),
            ((1.9, 1.2, 0.0), (3.0, 0.0, 0.0)),
            ((3.0, 0.0, 0.0), (1.9, -1.2, 0.0)),
            ((1.9, -1.2, 0.0), (-1.1, -2.4, 0.0)),
            ((-1.1, -2.4, 0.0), (-2.8, 0.0, 0.0)),
            ((-0.9, 0.0, 0.0), (1.6, 0.0, 0.0)),
            ((-1.2, 1.6, 0.0), (-2.6, 2.7, 0.0)),
            ((-1.2, -1.6, 0.0), (-2.6, -2.7, 0.0)),
        ]
        for a, b in outline:
            body.moveTo(*a)
            body.drawTo(*b)
        np = root.attach_new_node(body.create())
        np.setTransparency(TransparencyAttrib.MAlpha)
        root.look_at(start + velocity)
        self.sky_ships.append(SkyShip(root=root, velocity=velocity, lifetime=lifetime, phase=rng.random() * math.tau))

    def _ship_color(self, alpha: float = 1.0) -> tuple[float, float, float, float]:
        line_rgb = self._line_rgb()
        return (min(1.0, line_rgb[0] * 0.72 + 0.18), min(1.0, line_rgb[1] * 0.72 + 0.18), min(1.0, line_rgb[2] * 0.72 + 0.18), alpha)

    def _build_ui(self) -> None:
        self.hud_text = DirectLabel(
            parent=self.aspect2d,
            text='',
            text_align=TextNode.ALeft,
            text_scale=0.038,
            text_fg=(0.92, 0.92, 0.92, 1.0),
            frameColor=(0, 0, 0, 0),
            pos=(-1.27, 0, 0.92),
            textMayChange=True,
        )
        self.dialogue_label = DirectLabel(
            parent=self.aspect2d,
            text='',
            text_align=TextNode.ACenter,
            text_scale=0.048,
            text_fg=(0.96, 0.96, 0.96, 1.0),
            frameColor=(0.02, 0.02, 0.02, 0.68),
            frameSize=(-1.1, 1.1, -0.12, 0.12),
            pos=(0.0, 0.0, -0.82),
            textMayChange=True,
        )
        self.settings_panel = DirectFrame(
            parent=self.aspect2d,
            frameColor=(0.04, 0.04, 0.04, 0.94),
            frameSize=(-0.62, 0.62, -0.82, 0.82),
            pos=(0.64, 0, 0.0),
        )
        DirectLabel(
            parent=self.settings_panel,
            text='XR WORLD WALK',
            text_scale=0.056,
            text_fg=(0.96, 0.96, 0.96, 1.0),
            frameColor=(0, 0, 0, 0),
            pos=(0, 0, 0.72),
        )
        self.settings_text = DirectLabel(
            parent=self.settings_panel,
            text='',
            text_align=TextNode.ALeft,
            text_scale=0.032,
            text_fg=(0.92, 0.92, 0.92, 1.0),
            frameColor=(0, 0, 0, 0),
            pos=(-0.56, 0, 0.54),
            textMayChange=True,
        )
        btn_kwargs = dict(scale=0.045, frameColor=(0.12, 0.12, 0.12, 0.96), text_fg=(0.95, 0.95, 0.95, 1))
        DirectButton(parent=self.settings_panel, text='Resume', command=self.toggle_settings, pos=(0.0, 0.0, -0.72), **btn_kwargs)
        DirectButton(parent=self.settings_panel, text='More Draw Distance', command=self._adjust_draw_distance, extraArgs=[60.0], pos=(0.0, 0.0, -0.57), **btn_kwargs)
        DirectButton(parent=self.settings_panel, text='Faster Move', command=self._adjust_move_speed, extraArgs=[0.2], pos=(0.0, 0.0, -0.45), **btn_kwargs)
        DirectButton(parent=self.settings_panel, text='Cycle World Color', command=self._cycle_world_color, pos=(0.0, 0.0, -0.33), **btn_kwargs)
        DirectButton(parent=self.settings_panel, text='Cycle Line Color', command=self._cycle_line_color, pos=(0.0, 0.0, -0.21), **btn_kwargs)
        DirectButton(parent=self.settings_panel, text='Toggle Music', command=self._toggle_music, pos=(0.0, 0.0, -0.09), **btn_kwargs)
        DirectButton(parent=self.settings_panel, text='VR Perf Mode', command=self._toggle_vr_performance_mode, pos=(0.0, 0.0, 0.03), **btn_kwargs)
        DirectButton(parent=self.settings_panel, text='Set Floor To Head', command=self._set_floor_to_current_head, pos=(0.0, 0.0, 0.15), **btn_kwargs)
        self.floor_panel = DirectFrame(
            parent=self.aspect2d,
            frameColor=(0.03, 0.07, 0.09, 0.82),
            frameSize=(-0.34, 0.34, -0.10, 0.10),
            pos=(0.0, 0.0, 0.84),
        )
        self.floor_label = DirectLabel(
            parent=self.floor_panel,
            text='',
            text_align=TextNode.ACenter,
            text_scale=0.038,
            text_fg=(0.88, 0.97, 1.0, 1.0),
            frameColor=(0, 0, 0, 0),
            pos=(0.0, 0.0, -0.01),
            textMayChange=True,
        )
        self.floor_panel.hide()
        self.settings_panel.hide()
        if self.hud_visible:
            self.hud_text.show()
        else:
            self.hud_text.hide()

    def toggle_settings(self) -> None:
        self.settings_visible = not self.settings_visible
        if self.settings_visible:
            self.settings_panel.show()
        else:
            self.settings_panel.hide()
        self._save_config()

    def toggle_hud(self) -> None:
        self.hud_visible = not self.hud_visible
        if self.hud_visible:
            self.hud_text.show()
        else:
            self.hud_text.hide()
        self._save_config()

    def _adjust_draw_distance(self, delta: float) -> None:
        self.user_config['max_view_distance'] = max(280.0, min(1200.0, float(self.user_config.get('max_view_distance', 620.0)) + delta))
        max_view = float(self.user_config['max_view_distance'])
        self.camLens.setNearFar(0.03, max_view)
        self.fog.setLinearRange(max_view * float(self.user_config.get('fog_start_ratio', 0.52)), max_view)
        self._append_status(f'Draw distance {int(max_view)}')
        self._save_config()

    def _adjust_move_speed(self, delta: float) -> None:
        self.user_config['movement_speed'] = max(1.2, min(5.0, float(self.user_config.get('movement_speed', 2.55)) + delta))
        self._append_status(f'Move speed {self.user_config["movement_speed"]:.2f}')
        self._save_config()

    def _cycle_world_color(self) -> None:
        self.user_config['world_color_index'] = (int(self.user_config.get('world_color_index', 0)) + 1) % len(WORLD_COLOR_PRESETS)
        self._append_status(f'World color {WORLD_COLOR_PRESETS[self.user_config["world_color_index"]][0]}')
        self.update_palette(0.0, force=True)
        self._save_config()

    def _cycle_line_color(self) -> None:
        self.user_config['line_color_index'] = (int(self.user_config.get('line_color_index', 0)) + 1) % len(LINE_COLOR_PRESETS)
        self._append_status(f'Line color {LINE_COLOR_PRESETS[self.user_config["line_color_index"]][0]}')
        self.update_palette(0.0, force=True)
        self._save_config()

    def _toggle_music(self) -> None:
        self.user_config['music_enabled'] = not bool(self.user_config.get('music_enabled', True))
        self._apply_music_state()
        self._append_status('Music on' if self.user_config['music_enabled'] else 'Music off')
        self._save_config()

    def _toggle_vr_performance_mode(self) -> None:
        enabled = not bool(self.user_config.get('vr_performance_mode', True))
        self.user_config['vr_performance_mode'] = enabled
        if enabled:
            self.user_config['active_chunk_radius'] = min(int(self.user_config.get('active_chunk_radius', 3)), 2)
            self.user_config['max_view_distance'] = min(float(self.user_config.get('max_view_distance', 620.0)), 560.0)
        self._adjust_runtime_budgets()
        self._append_status('VR performance mode on' if enabled else 'VR performance mode off')
        self.generate_city_around_player(force=True)
        self._save_config()

    def capture_screenshot(self) -> None:
        ensure_dirs()
        stamp = time.strftime('%Y%m%d_%H%M%S')
        path = SCREENSHOT_DIR / f'shot_{stamp}.png'
        self.win.saveScreenshot(str(path))
        self._append_status(f'Screenshot: {path.name}')

    def _world_rgb(self) -> tuple[float, float, float]:
        return WORLD_COLOR_PRESETS[int(self.user_config.get('world_color_index', 0)) % len(WORLD_COLOR_PRESETS)][1]

    def _line_rgb(self) -> tuple[float, float, float]:
        return LINE_COLOR_PRESETS[int(self.user_config.get('line_color_index', 0)) % len(LINE_COLOR_PRESETS)][1]

    def current_district_label(self) -> str:
        csize = int(self.user_config.get('chunk_size', 72))
        cx = int(math.floor(self.player_root.get_x() / csize))
        cy = int(math.floor(self.player_root.get_y() / csize))
        names = ['Transit Wards', 'Relay Plaza', 'Needle Court', 'Iron Promenade', 'Signal Bastion']
        return names[self.hashed_seed(cx, cy, 404) % len(names)]

    def current_line_color(self, alpha: float = 1.0) -> tuple[float, float, float, float]:
        rgb = self.palette_line_rgb
        pulse = 0.94 + 0.12 * (0.5 + 0.5 * math.sin(self.day_phase * math.tau * 3.0))
        return (min(1.0, rgb[0] * pulse), min(1.0, rgb[1] * pulse), min(1.0, rgb[2] * pulse), alpha)

    def update_palette(self, dt: float, force: bool = False) -> None:
        if not force:
            self.palette_refresh_timer -= dt
            if self.palette_refresh_timer > 0.0:
                return
            self.palette_refresh_timer = 1.0 / float(self.user_config.get('palette_refresh_hz', 10.0))
        day_len = 1200.0
        long_len = 3600.0
        phase = (self.elapsed % day_len) / day_len
        long_phase = (self.elapsed % long_len) / long_len
        transition = 180.0 / day_len
        def smooth_band(x: float, center: float) -> float:
            d = abs((x - center + 0.5) % 1.0 - 0.5)
            if d >= transition * 0.5:
                return 0.0
            y = 1.0 - d / (transition * 0.5)
            return y * y * (3 - 2 * y)
        dawn = smooth_band(phase, 0.12)
        dusk = smooth_band(phase, 0.62)
        day_base = 1.0 if 0.12 <= phase < 0.62 else 0.0
        day_amount = max(day_base, dawn)
        self.day_mix = min(day_amount, 1.0 - dusk * (1.0 - day_amount))
        self.day_phase = phase
        night_mix = 1.0 - self.day_mix
        self.day_hue_shift = 0.05 * math.sin(math.tau * phase) + 0.025 * math.sin(math.tau * phase * 2.0 + 0.6)
        self.long_hue_shift = 0.18 * math.sin(math.tau * long_phase - 0.25) + 0.07 * math.sin(math.tau * long_phase * 0.5 + 1.15)
        self.long_sat_scale = 0.76 + 0.36 * (0.5 + 0.5 * math.sin(math.tau * long_phase - 0.45))
        self.invert_mix = min(1.0, max(0.0, 0.08 + 0.84 * (night_mix ** 1.25)))
        world_shift = self.day_hue_shift * 0.45 + self.long_hue_shift * 0.90
        base = _rotate_hue(self._world_rgb(), world_shift, sat_scale=(0.80 + 0.24 * self.day_mix) * self.long_sat_scale, val_scale=1.0)
        horizon_mix = 0.5 + 0.5 * math.sin(math.tau * phase - 0.35)
        cool = _rotate_hue(base, -0.07 + 0.03 * math.sin(math.tau * long_phase), sat_scale=1.05, val_scale=0.94)
        warm = _rotate_hue(base, 0.11 + 0.02 * math.sin(math.tau * long_phase + 1.8), sat_scale=0.93, val_scale=1.06)
        sky_mix = _lerp3(cool, warm, horizon_mix * (0.92 - self.day_mix * 0.16))
        bg_day = tuple(max(0.01, min(1.0, c * (0.18 + 0.42 * self.day_mix))) for c in sky_mix)
        bg_night = tuple(max(0.01, min(1.0, (1.0 - c) * (0.05 + 0.14 * (0.5 + 0.5 * math.sin(math.tau * long_phase + 0.7))))) for c in sky_mix)
        bg = tuple(max(0.01, min(1.0, bg_day[i] * (1.0 - self.invert_mix * 0.55) + bg_night[i] * (self.invert_mix * 0.55))) for i in range(3))
        line_base = _rotate_hue(self._line_rgb(), self.day_hue_shift + self.long_hue_shift, sat_scale=(0.88 + 0.22 * self.day_mix) * self.long_sat_scale, val_scale=1.02)
        inverted_bg = tuple(max(0.0, min(1.0, 1.0 - c)) for c in bg)
        line_rgb = tuple(max(0.0, min(1.0, line_base[i] * (1.0 - self.invert_mix) + inverted_bg[i] * self.invert_mix)) for i in range(3))
        self.palette_bg_rgb = bg
        self.palette_line_rgb = line_rgb
        key = (
            round(bg[0], 3), round(bg[1], 3), round(bg[2], 3),
            round(line_rgb[0], 3), round(line_rgb[1], 3), round(line_rgb[2], 3),
            int(self.user_config.get('line_color_index', 0)),
            int(self.user_config.get('world_color_index', 0)),
            round(self.day_mix, 2),
            round(self.invert_mix, 2),
        )
        if not force and key == self._last_palette_key:
            return
        self._last_palette_key = key
        self.setBackgroundColor(bg[0], bg[1], bg[2], 1.0)
        self.fog.setColor(bg[0], bg[1], bg[2])
        tint = self.current_line_color(alpha=0.96)
        if hasattr(self, 'ground_root'):
            grid_alpha = 0.16 + 0.10 * (0.5 + 0.5 * math.sin(math.tau * long_phase + 0.8)) + 0.08 * self.invert_mix
            self.ground_root.setColorScale(tint[0] * 0.88, tint[1] * 0.88, tint[2] * 0.88, min(0.42, grid_alpha))
        for chunk in self.chunks.values():
            chunk.setColor(*tint)
        for walker in self.walkers:
            walker.body.setColor(*self.current_line_color(alpha=0.98))
        if hasattr(self, 'star_np'):
            self.star_np.setColorScale(1.0, 1.0, 1.0, 0.36 + night_mix * 0.48)
        for ship in self.sky_ships:
            ship.root.setColorScale(*self._ship_color(alpha=0.7))
        for claw in (self.left_claw, self.right_claw):
            if claw is not None:
                claw.root.setColorScale(*self.current_line_color(alpha=0.95))
        for blaster in (self.left_blaster, self.right_blaster):
            if blaster is not None:
                if blaster.kind == 'sword':
                    sword_rgb = _rotate_hue(self.palette_line_rgb, 0.08, sat_scale=0.86, val_scale=1.08)
                    blaster.root.setColorScale(sword_rgb[0], sword_rgb[1], sword_rgb[2], 0.98)
                else:
                    blaster.root.setColorScale(*self.current_line_color(alpha=0.95))

    def hashed_seed(self, x: int, y: int, salt: int = 0) -> int:
        return (x * 92837111 ^ y * 689287499 ^ int(self.user_config.get('world_seed', 74219)) ^ salt * 334214459) & 0xFFFFFFFF

    def draw_box_outline_2d(self, segs: LineSegs, x0: float, y0: float, x1: float, y1: float, z: float) -> None:
        segs.moveTo(x0, y0, z)
        segs.drawTo(x1, y0, z)
        segs.drawTo(x1, y1, z)
        segs.drawTo(x0, y1, z)
        segs.drawTo(x0, y0, z)

    def draw_ring(self, segs: LineSegs, center: Vec3, radius: float, segments: int) -> None:
        last = None
        first = None
        for i in range(segments):
            ang = math.tau * i / segments
            p = Vec3(center.x + math.cos(ang) * radius, center.y, center.z + math.sin(ang) * radius)
            if first is None:
                first = p
            if last is not None:
                segs.moveTo(last)
                segs.drawTo(p)
            last = p
        if last is not None and first is not None:
            segs.moveTo(last)
            segs.drawTo(first)

    def draw_box_edges(self, segs: LineSegs, center: Vec3, size: Vec3) -> None:
        hx, hy, hz = size.x * 0.5, size.y * 0.5, size.z * 0.5
        x0, x1 = center.x - hx, center.x + hx
        y0, y1 = center.y - hy, center.y + hy
        z0, z1 = center.z - hz, center.z + hz
        edges = [
            ((x0, y0, z0), (x1, y0, z0)), ((x1, y0, z0), (x1, y1, z0)), ((x1, y1, z0), (x0, y1, z0)), ((x0, y1, z0), (x0, y0, z0)),
            ((x0, y0, z1), (x1, y0, z1)), ((x1, y0, z1), (x1, y1, z1)), ((x1, y1, z1), (x0, y1, z1)), ((x0, y1, z1), (x0, y0, z1)),
            ((x0, y0, z0), (x0, y0, z1)), ((x1, y0, z0), (x1, y0, z1)), ((x1, y1, z0), (x1, y1, z1)), ((x0, y1, z0), (x0, y1, z1)),
        ]
        jitter = float(self.user_config.get('line_jitter', 0.025))
        for a, b in edges:
            j = Vec3(random.uniform(-jitter, jitter), random.uniform(-jitter, jitter), random.uniform(-jitter, jitter))
            segs.moveTo(a[0] + j.x, a[1] + j.y, a[2] + j.z)
            segs.drawTo(b[0] + j.x, b[1] + j.y, b[2] + j.z)

    def add_building_mass(self, segs: LineSegs, obstacles: list[BoxBounds], base_pos: Vec3, width: float, depth: float, height: float, rng: random.Random, style: int, district: str) -> None:
        tiers = 2 + (1 if rng.random() < 0.55 else 0)
        cur_center = Vec3(base_pos.x, base_pos.y, height * 0.5)
        cur_w = width
        cur_d = depth
        cur_h = height
        for tier in range(tiers):
            size = Vec3(cur_w, cur_d, cur_h)
            self.draw_box_edges(segs, cur_center, size)
            obstacles.append(BoxBounds(cur_center - size * 0.5, cur_center + size * 0.5, Vec3(0, 0, 1)))
            roof_z = cur_center.z + cur_h * 0.5
            if style in (1, 4):
                fin_top = roof_z + rng.uniform(8, 18)
                segs.moveTo(cur_center.x, cur_center.y, roof_z)
                segs.drawTo(cur_center.x, cur_center.y, fin_top)
                segs.moveTo(cur_center.x - cur_w * 0.18, cur_center.y, fin_top - 3)
                segs.drawTo(cur_center.x + cur_w * 0.18, cur_center.y, fin_top - 3)
            if style in (2, 3) and tier == 0:
                buttress_w = max(2.8, cur_w * 0.22)
                for sign in (-1, 1):
                    brace_center = Vec3(cur_center.x + sign * (cur_w * 0.5 + buttress_w * 0.36), cur_center.y, cur_center.z - cur_h * 0.12)
                    brace_size = Vec3(buttress_w, max(2.6, cur_d * 0.48), cur_h * 0.76)
                    self.draw_box_edges(segs, brace_center, brace_size)
                    obstacles.append(BoxBounds(brace_center - brace_size * 0.5, brace_center + brace_size * 0.5, Vec3(0, 0, 1)))
            cur_center = Vec3(
                cur_center.x + rng.uniform(-2.6, 2.6) if style != 0 else cur_center.x,
                cur_center.y + rng.uniform(-2.6, 2.6) if style in (0, 3, 4) else cur_center.y,
                roof_z + max(8.0, cur_h * 0.33),
            )
            cur_w = max(4.2, cur_w * rng.uniform(0.56, 0.82))
            cur_d = max(4.2, cur_d * rng.uniform(0.56, 0.82))
            cur_h = max(8.0, cur_h * rng.uniform(0.45, 0.68))
        if district == 'bridge' and rng.random() < 0.35:
            wing = rng.uniform(8, 14)
            bridge_center = Vec3(base_pos.x, base_pos.y, height * rng.uniform(0.35, 0.62))
            bridge_size = Vec3(wing, 3.2, 2.8) if rng.random() < 0.5 else Vec3(3.2, wing, 2.8)
            self.draw_box_edges(segs, bridge_center, bridge_size)
            obstacles.append(BoxBounds(bridge_center - bridge_size * 0.5, bridge_center + bridge_size * 0.5, Vec3(0, 0, 1)))

    def draw_plaza_landmark(self, segs: LineSegs, obstacles: list[BoxBounds], center: Vec3, rng: random.Random, avenue_vertical: bool, avenue_axis: float, road_half: float, avenue_half: float) -> None:
        self.draw_ring(segs, Vec3(center.x, center.y, 0.15), 9.0, 18)
        self.draw_ring(segs, Vec3(center.x, center.y, 0.15), 4.8, 14)
        for off in (-1, 1):
            p = Vec3(center.x + off * 5.5, center.y, 3.6)
            self.draw_box_edges(segs, p, Vec3(2.6, 2.6, 7.2))
            obstacles.append(BoxBounds(p - Vec3(1.3, 1.3, 3.6), p + Vec3(1.3, 1.3, 3.6), Vec3(0, 0, 1)))

    def draw_spire_landmark(self, segs: LineSegs, obstacles: list[BoxBounds], center: Vec3, rng: random.Random, avenue_vertical: bool, avenue_axis: float, road_half: float, avenue_half: float) -> None:
        spire_center = Vec3(center.x, center.y, 28)
        spire_size = Vec3(6.4, 6.4, 56)
        self.draw_box_edges(segs, spire_center, spire_size)
        obstacles.append(BoxBounds(spire_center - spire_size * 0.5, spire_center + spire_size * 0.5, Vec3(0, 0, 1)))
        for z in (18, 34, 48):
            self.draw_ring(segs, Vec3(center.x, center.y, z), 5.2 + z * 0.04, 14)

    def draw_industrial_landmark(self, segs: LineSegs, obstacles: list[BoxBounds], center: Vec3, rng: random.Random, avenue_vertical: bool, avenue_axis: float, road_half: float, avenue_half: float) -> None:
        for off in (-1, 1):
            tank = Vec3(center.x + off * 5.4, center.y, 7.0)
            self.draw_box_edges(segs, tank, Vec3(6.8, 6.8, 14.0))
            obstacles.append(BoxBounds(tank - Vec3(3.4, 3.4, 7.0), tank + Vec3(3.4, 3.4, 7.0), Vec3(0, 0, 1)))
            self.draw_ring(segs, Vec3(tank.x, tank.y, 14.4), 3.2, 12)
        stack = Vec3(center.x, center.y - 5.5, 18)
        self.draw_box_edges(segs, stack, Vec3(4.2, 4.2, 36.0))
        obstacles.append(BoxBounds(stack - Vec3(2.1, 2.1, 18), stack + Vec3(2.1, 2.1, 18), Vec3(0, 0, 1)))

    def draw_bridge_landmark(self, segs: LineSegs, obstacles: list[BoxBounds], center: Vec3, rng: random.Random, avenue_vertical: bool, avenue_axis: float, road_half: float, avenue_half: float) -> None:
        bridge_center = Vec3(center.x, center.y, 8.6)
        bridge_size = Vec3(22.0, 5.4, 3.0) if avenue_vertical else Vec3(5.4, 22.0, 3.0)
        self.draw_box_edges(segs, bridge_center, bridge_size)
        obstacles.append(BoxBounds(bridge_center - bridge_size * 0.5, bridge_center + bridge_size * 0.5, Vec3(0, 0, 1)))
        for off in (-1, 1):
            pylon = Vec3(center.x + off * (8.0 if avenue_vertical else 0), center.y + off * (0 if avenue_vertical else 8.0), 12.0)
            size = Vec3(3.2, 3.2, 24.0)
            self.draw_box_edges(segs, pylon, size)
            obstacles.append(BoxBounds(pylon - size * 0.5, pylon + size * 0.5, Vec3(0, 0, 1)))

    def draw_sentinel_landmark(self, segs: LineSegs, obstacles: list[BoxBounds], center: Vec3, rng: random.Random, avenue_vertical: bool, avenue_axis: float, road_half: float, avenue_half: float) -> None:
        dais = Vec3(center.x, center.y, 2.0)
        self.draw_box_edges(segs, dais, Vec3(12.0, 12.0, 4.0))
        obstacles.append(BoxBounds(dais - Vec3(6.0, 6.0, 2.0), dais + Vec3(6.0, 6.0, 2.0), Vec3(0, 0, 1)))
        statue = Vec3(center.x, center.y, 11.0)
        self.draw_box_edges(segs, statue, Vec3(3.2, 3.2, 14.0))
        obstacles.append(BoxBounds(statue - Vec3(1.6, 1.6, 7.0), statue + Vec3(1.6, 1.6, 7.0), Vec3(0, 0, 1)))
        self.draw_ring(segs, Vec3(center.x, center.y, 17.2), 4.6, 12)

    def generate_chunk_geometry(self, cx: int, cy: int) -> tuple[NodePath, list[BoxBounds], list[tuple[float, float, int]]]:
        chunk_seed = self.hashed_seed(cx, cy)
        rng = random.Random(chunk_seed)
        origin_x = cx * int(self.user_config.get('chunk_size', 72))
        origin_y = cy * int(self.user_config.get('chunk_size', 72))
        size = int(self.user_config.get('chunk_size', 72))
        np = self.city_root.attach_new_node(f'chunk-{cx}-{cy}')
        segs = LineSegs(f'chunk-lines-{cx}-{cy}')
        segs.setThickness(float(self.user_config.get('line_thickness', 1.25)))
        segs.setColor(*self.current_line_color(alpha=0.94))
        obstacles: list[BoxBounds] = []
        npc_spawns: list[tuple[float, float, int]] = []

        district_styles = ['plaza', 'spire', 'industrial', 'bridge', 'sentinel']
        district = district_styles[chunk_seed % len(district_styles)]
        player_chunk_x = int(math.floor(self.player_root.get_x() / size)) if size else 0
        player_chunk_y = int(math.floor(self.player_root.get_y() / size)) if size else 0
        chunk_distance = math.hypot(cx - player_chunk_x, cy - player_chunk_y)
        detail_distance = float(self.user_config.get('skyline_detail_distance', 220.0)) / max(1.0, float(size))
        low_detail = self._perf_mode() and chunk_distance > max(1.1, detail_distance)
        road_half = 8.0 + (chunk_seed % 3) * 1.4
        avenue_half = 5.0 + ((chunk_seed >> 3) % 3) * 1.1
        avenue_vertical = (chunk_seed >> 5) & 1 == 0
        avenue_axis = origin_x + size * 0.5 if avenue_vertical else origin_y + size * 0.5

        self.draw_box_outline_2d(segs, origin_x, origin_y, origin_x + size, origin_y + size, 0)
        self.draw_box_outline_2d(segs, origin_x + road_half, origin_y + road_half, origin_x + size - road_half, origin_y + size - road_half, 0)
        lane_step = 18 if low_detail else 12
        for gx in range(lane_step, size, lane_step):
            x = origin_x + gx
            segs.moveTo(x, origin_y + road_half * 0.65, 0)
            segs.drawTo(x, origin_y + road_half, 0)
            segs.moveTo(x, origin_y + size - road_half * 0.65, 0)
            segs.drawTo(x, origin_y + size - road_half, 0)
        for gy in range(lane_step, size, lane_step):
            y = origin_y + gy
            segs.moveTo(origin_x + road_half * 0.65, y, 0)
            segs.drawTo(origin_x + road_half, y, 0)
            segs.moveTo(origin_x + size - road_half * 0.65, y, 0)
            segs.drawTo(origin_x + size - road_half, y, 0)
        if avenue_vertical:
            x0 = avenue_axis - avenue_half
            x1 = avenue_axis + avenue_half
            segs.moveTo(x0, origin_y + road_half, 0)
            segs.drawTo(x0, origin_y + size - road_half, 0)
            segs.moveTo(x1, origin_y + road_half, 0)
            segs.drawTo(x1, origin_y + size - road_half, 0)
        else:
            y0 = avenue_axis - avenue_half
            y1 = avenue_axis + avenue_half
            segs.moveTo(origin_x + road_half, y0, 0)
            segs.drawTo(origin_x + size - road_half, y0, 0)
            segs.moveTo(origin_x + road_half, y1, 0)
            segs.drawTo(origin_x + size - road_half, y1, 0)

        build_margin = road_half + 6.0
        interior_min_x = origin_x + build_margin
        interior_max_x = origin_x + size - build_margin
        interior_min_y = origin_y + build_margin
        interior_max_y = origin_y + size - build_margin
        landmarks = {
            'plaza': self.draw_plaza_landmark,
            'spire': self.draw_spire_landmark,
            'industrial': self.draw_industrial_landmark,
            'bridge': self.draw_bridge_landmark,
            'sentinel': self.draw_sentinel_landmark,
        }
        landmark_center = Vec3(origin_x + size * 0.5, origin_y + size * 0.5, 0)
        if not low_detail:
            landmarks[district](segs, obstacles, landmark_center, rng, avenue_vertical, avenue_axis, road_half, avenue_half)
        else:
            self.draw_box_outline_2d(segs, landmark_center.x - 5.0, landmark_center.y - 5.0, landmark_center.x + 5.0, landmark_center.y + 5.0, 0)

        if avenue_vertical:
            plot_regions = [
                (interior_min_x, avenue_axis - avenue_half - 4, interior_min_y, interior_max_y),
                (avenue_axis + avenue_half + 4, interior_max_x, interior_min_y, interior_max_y),
            ]
        else:
            plot_regions = [
                (interior_min_x, interior_max_x, interior_min_y, avenue_axis - avenue_half - 4),
                (interior_min_x, interior_max_x, avenue_axis + avenue_half + 4, interior_max_y),
            ]
        unique_regions = []
        for rx0, rx1, ry0, ry1 in plot_regions:
            if rx1 - rx0 > 12 and ry1 - ry0 > 12:
                unique_regions.append((rx0, rx1, ry0, ry1))
        built_centers: list[tuple[float, float]] = []
        for idx, (rx0, rx1, ry0, ry1) in enumerate(unique_regions):
            count = 1 + (0 if low_detail else (1 if rng.random() < 0.45 else 0))
            for slot in range(count):
                bx = rng.uniform(rx0 + 4, rx1 - 4)
                by = rng.uniform(ry0 + 4, ry1 - 4)
                if avenue_vertical and abs(bx - avenue_axis) < avenue_half + 7:
                    continue
                if (not avenue_vertical) and abs(by - avenue_axis) < avenue_half + 7:
                    continue
                if any((Vec2(bx, by) - Vec2(px, py)).length() < 12.0 for px, py in built_centers):
                    continue
                style = (idx + slot + (chunk_seed % 4)) % 5
                if low_detail:
                    footprint = rng.uniform(10.0, 16.0)
                    depth = rng.uniform(10.0, 16.0)
                    height = rng.uniform(14.0, 42.0)
                else:
                    footprint = rng.uniform(8.0, 14.0)
                    depth = rng.uniform(8.0, 14.0)
                    height = rng.uniform(18.0, 64.0)
                self.add_building_mass(segs, obstacles, Vec3(bx, by, 0), footprint, depth, height, rng, style, district)
                built_centers.append((bx, by))

        spawn_candidates = [
            (origin_x + size * 0.5, origin_y + road_half + 8),
            (origin_x + size * 0.5, origin_y + size - road_half - 8),
            (origin_x + road_half + 8, origin_y + size * 0.5),
            (origin_x + size - road_half - 8, origin_y + size * 0.5),
            (origin_x + size * 0.5 + (14 if avenue_vertical else 0), origin_y + size * 0.5 + (0 if avenue_vertical else 14)),
        ]
        rng.shuffle(spawn_candidates)
        spawn_count = 1 if low_detail else 1 + rng.randint(1, 2)
        for i, (px, py) in enumerate(spawn_candidates[:spawn_count]):
            if not self.point_hits_obstacle(Vec3(px, py, 0), radius=1.6, height=5.2, obstacles=obstacles):
                npc_spawns.append((px, py, self.hashed_seed(cx, cy, i + 91)))
        visual_np = np.attach_new_node(segs.create())
        visual_np.setAntialias(AntialiasAttrib.MLine)
        visual_np.setTransparency(TransparencyAttrib.MAlpha)
        return np, obstacles, npc_spawns

    def _draw_walker_model(self, parent: NodePath) -> NodePath:
        body = parent.attach_new_node('walker-body')
        body.setTransparency(TransparencyAttrib.MAlpha)
        body.setAntialias(AntialiasAttrib.MLine)
        def add_box(pos: tuple[float, float, float], size: tuple[float, float, float]) -> None:
            segs = LineSegs('walker-box')
            segs.setThickness(max(1.0, float(self.user_config.get('line_thickness', 1.25)) * 0.92))
            segs.setColor(*self.current_line_color(alpha=0.96))
            self.draw_box_edges(segs, Vec3(*pos), Vec3(*size))
            np = body.attach_new_node(segs.create())
            np.setAntialias(AntialiasAttrib.MLine)
        for pos, size in [
            ((0, 0, 2.8), (1.55, 1.05, 1.95)),
            ((0, 0.08, 4.15), (0.9, 0.86, 0.72)),
            ((0, 0.2, 1.55), (0.95, 0.82, 0.7)),
            ((-1.02, 0.0, 3.55), (0.56, 0.62, 0.44)),
            ((1.02, 0.0, 3.55), (0.56, 0.62, 0.44)),
            ((-0.42, 0.08, 0.16), (0.5, 0.74, 1.82)),
            ((0.42, 0.08, 0.16), (0.5, 0.74, 1.82)),
            ((-0.46, 0.24, -0.38), (0.72, 1.12, 0.3)),
            ((0.46, 0.24, -0.38), (0.72, 1.12, 0.3)),
        ]:
            add_box(pos, size)
        ring = LineSegs('walker-ring')
        ring.setThickness(max(1.0, float(self.user_config.get('line_thickness', 1.25)) * 0.86))
        ring.setColor(*self.current_line_color(alpha=0.95))
        self.draw_ring(ring, Vec3(0, 0.46, 4.15), 0.32, 12)
        ring_np = body.attach_new_node(ring.create())
        ring_np.setAntialias(AntialiasAttrib.MLine)
        return body

    def _spawn_walker(self, pos: Vec3, seed: int) -> WalkerNPC:
        rng = random.Random(seed)
        root = self.render.attach_new_node(f'walker-{seed}')
        root.set_pos(pos)
        body = self._draw_walker_model(root)
        wander = Vec3(rng.uniform(-1, 1), rng.uniform(-1, 1), 0)
        if wander.length_squared() < 0.05:
            wander = Vec3(1, 0, 0)
        wander.normalize()
        return WalkerNPC(
            root=root,
            body=body,
            radius=0.95,
            height=4.9,
            wander_dir=wander,
            wander_timer=1.6 + rng.random() * 3.2,
            speed=0.55 + rng.random() * 0.35,
            phase=rng.random() * math.tau,
            seed=seed,
            label=f'Walker-{seed % 1000:03d}',
        )

    def generate_city_around_player(self, force: bool = False) -> None:
        csize = int(self.user_config.get('chunk_size', 72))
        px = int(math.floor(self.player_root.get_x() / csize))
        py = int(math.floor(self.player_root.get_y() / csize))
        required = set()
        radius = int(self.user_config.get('active_chunk_radius', 3))
        for cx in range(px - radius, px + radius + 1):
            for cy in range(py - radius, py + radius + 1):
                required.add((cx, cy))
                if (cx, cy) not in self.chunks:
                    chunk_np, obstacles, spawns = self.generate_chunk_geometry(cx, cy)
                    self.chunks[(cx, cy)] = chunk_np
                    self.chunk_obstacles[(cx, cy)] = obstacles
                    self.chunk_npc_spawns[(cx, cy)] = spawns
                    spawned_walkers: list[WalkerNPC] = []
                    walker_budget = int(self.user_config.get('walker_budget', 24))
                    for ex, ey, seed in spawns:
                        if len(self.walkers) < walker_budget:
                            walker = self._spawn_walker(Vec3(ex, ey, 0.0), seed)
                            self.walkers.append(walker)
                            spawned_walkers.append(walker)
                    self.walker_nodes_by_chunk[(cx, cy)] = spawned_walkers
        for key in list(self.chunks.keys()):
            if key not in required:
                self.chunks[key].remove_node()
                del self.chunks[key]
                self.chunk_obstacles.pop(key, None)
                self.chunk_npc_spawns.pop(key, None)
                for walker in self.walker_nodes_by_chunk.pop(key, []):
                    if walker in self.walkers:
                        self.walkers.remove(walker)
                    walker.root.remove_node()

    def point_hits_obstacle(self, pos: Vec3, radius: float = 0.42, height: float = 1.8, obstacles: list[BoxBounds] | None = None) -> bool:
        obs = obstacles
        if obs is None:
            obs = []
            csize = int(self.user_config.get('chunk_size', 72))
            px = int(math.floor(pos.x / csize))
            py = int(math.floor(pos.y / csize))
            for cx in range(px - 1, px + 2):
                for cy in range(py - 1, py + 2):
                    obs.extend(self.chunk_obstacles.get((cx, cy), []))
        test_min = Vec3(pos.x - radius, pos.y - radius, 0)
        test_max = Vec3(pos.x + radius, pos.y + radius, height)
        for box in obs:
            if (
                test_min.x <= box.max_v.x and test_max.x >= box.min_v.x and
                test_min.y <= box.max_v.y and test_max.y >= box.min_v.y and
                test_min.z <= box.max_v.z and test_max.z >= box.min_v.z
            ):
                return True
        return False

    def _head_quat(self):
        if self.xr is not None:
            return self.xr.hmd_anchor.get_quat(self.render)
        return self.camera.get_quat(self.render)

    def _head_world_pos(self) -> Vec3:
        if self.xr is not None:
            return self.xr.hmd_anchor.get_pos(self.render)
        return self.camera.get_pos(self.render)

    def _local_hmd_pose(self) -> tuple[Vec3, float]:
        if self.xr is None:
            return Vec3(0, 0, self.eye_height_m), 0.0
        local = self.xr.hmd_anchor.get_pos(self.xr.tracking_space_anchor)
        quat = self.xr.hmd_anchor.get_quat(self.xr.tracking_space_anchor)
        forward = quat.get_forward()
        forward.z = 0
        yaw = _yaw_from_vec(forward) if forward.length_squared() > 1e-6 else 0.0
        return Vec3(local), yaw

    def _xr_tracking_space_kind(self) -> str:
        if self.xr is None:
            return 'desktop'
        name = str(getattr(getattr(self.xr, 'tracking_space', None), 'reference_space_type', 'unknown'))
        self.xr_tracking_space_name = name
        return name.lower()

    def _queue_floor_calibration(self, reset_samples: bool = False) -> None:
        self.xr_floor_pending = True
        self.xr_floor_settle_timer = float(self.user_config.get('xr_floor_settle_delay', 0.85))
        if reset_samples:
            self.xr_floor_samples.clear()

    def _stable_head_height(self, local_z: float) -> float:
        sample_window = int(self.user_config.get('xr_floor_sample_window', 10))
        self.xr_floor_samples.append(float(local_z))
        if len(self.xr_floor_samples) > sample_window:
            self.xr_floor_samples = self.xr_floor_samples[-sample_window:]
        ordered = sorted(self.xr_floor_samples)
        if not ordered:
            return float(local_z)
        return ordered[len(ordered) // 2]

    def _set_floor_to_current_head(self) -> None:
        if self.xr is None:
            self._append_status('Floor set works in XR mode only.')
            return
        if not getattr(self.xr, 'hmd_pose_valid', False):
            self._append_status('Headset pose not valid yet.')
            return
        local, local_yaw = self._local_hmd_pose()
        stable_z = self._stable_head_height(local.z)
        self.floor_offset_z = max(-0.35, min(self.eye_height_m + 0.35, self.eye_height_m - stable_z + float(self.user_config.get('xr_floor_raise_bias', 0.04))))
        self.xr_floor_calibrated = True
        self.last_local_head_z = local.z
        self.last_local_head_yaw = local_yaw
        self.xr_floor_pending = False
        self._append_status(f'Floor set from current head height: {stable_z:.2f}m')

    def _calibrate_floor(self, force: bool = False) -> None:
        if self.xr is None:
            return
        if not getattr(self.xr, 'hmd_pose_valid', False) and not force:
            return
        local, local_yaw = self._local_hmd_pose()
        stable_z = self._stable_head_height(local.z)
        tracking_kind = self._xr_tracking_space_kind()
        target = self.eye_height_m - stable_z + float(self.user_config.get('xr_floor_raise_bias', 0.04))
        if 'stage' in tracking_kind:
            min_head = float(self.user_config.get('xr_floor_stage_min_head', 0.9))
            if stable_z < min_head:
                target = self.eye_height_m + float(self.user_config.get('xr_floor_raise_bias', 0.04))
        else:
            min_head = float(self.user_config.get('xr_floor_local_min_head', 0.35))
            if stable_z < min_head:
                target = self.eye_height_m + float(self.user_config.get('xr_floor_raise_bias', 0.04))
        target = max(-0.35, min(self.eye_height_m + 0.35, target))
        if not self.xr_floor_calibrated or force:
            self.floor_offset_z = target
        else:
            self.floor_offset_z = self.floor_offset_z * 0.82 + target * 0.18
        self.last_local_head_z = local.z
        self.last_local_head_yaw = local_yaw
        self.xr_floor_calibrated = True
        self.xr_floor_pending = False
        self._append_status(f'Floor calibrated [{self.xr_tracking_space_name}] head {stable_z:.2f}m')

    def _xr_button_down(self, action_name: str) -> bool:
        if self.xr is None:
            return False
        try:
            return self.xr.button(action_name, 'left') or self.xr.button(action_name, 'right')
        except Exception:
            return False

    def _movement_input(self) -> tuple[Vec2, float]:
        move = Vec2(0, 0)
        turn = 0.0
        if self.xr is not None:
            try:
                lx, ly = self.xr.axis2d('thumbstick', 'left')
                rx, _ = self.xr.axis2d('thumbstick', 'right')
                move = Vec2(lx, ly)
                turn = rx
            except Exception:
                pass
        else:
            if self.keys.get('a'):
                move.x -= 1.0
            if self.keys.get('d'):
                move.x += 1.0
            if self.keys.get('w'):
                move.y += 1.0
            if self.keys.get('s'):
                move.y -= 1.0
            if self.keys.get('turn_left'):
                turn += 1.0
            if self.keys.get('turn_right'):
                turn -= 1.0
        if move.length_squared() > 1.0:
            move.normalize()
        return move, turn

    def _update_desktop_fallback_camera(self) -> None:
        self.camera.set_hpr(self.player_heading, self.desktop_pitch, 0)
        self.camera.set_pos(self.player_root.get_pos(self.render) + Vec3(0, 0, self.eye_height_m))

    def _apply_tracking_anchor(self) -> None:
        if self.xr is None:
            return
        if not self.xr_floor_calibrated:
            self._calibrate_floor(force=True)
        self.xr.tracking_space_anchor.set_pos(self.player_root.get_x(), self.player_root.get_y(), self.floor_offset_z + self.spawn_safe_z)
        self.xr.tracking_space_anchor.set_h(self.player_heading)

    def _update_player_motion(self, dt: float) -> None:
        move, turn = self._movement_input()
        if abs(turn) > 0.12:
            self.player_heading += -turn * float(self.user_config.get('turn_speed', 95.0)) * dt
        if move.length_squared() > 0.0001:
            speed = float(self.user_config.get('movement_speed', 2.55))
            if self.keys.get('shift') and self.xr is None:
                speed *= float(self.user_config.get('sprint_multiplier', 1.45))
            heading = self._head_quat() if self.xr is not None else self.camera.get_quat(self.render)
            forward = heading.get_forward()
            right = heading.get_right()
            forward.z = 0
            right.z = 0
            if forward.length_squared() > 0.0001:
                forward.normalize()
            if right.length_squared() > 0.0001:
                right.normalize()
            move_vec = forward * move.y + right * move.x
            if move_vec.length_squared() > 1.0:
                move_vec.normalize()
            next_pos = self.player_root.get_pos(self.render) + move_vec * speed * dt
            next_pos.z = self.spawn_safe_z
            if not self.point_hits_obstacle(next_pos, radius=self.player_radius, height=self.player_height_m):
                self.player_root.set_pos(next_pos)
        if self.xr is not None:
            local, local_yaw = self._local_hmd_pose()
            self._xr_tracking_space_kind()
            if getattr(self.xr, 'hmd_pose_valid', False):
                self._stable_head_height(local.z)
                if not self.xr_floor_calibrated and not self.xr_floor_pending:
                    self._queue_floor_calibration(reset_samples=True)
                if self.xr_floor_pending:
                    self.xr_floor_settle_timer -= dt
                    if self.xr_floor_settle_timer <= 0.0:
                        self._calibrate_floor(force=True)
                if self.xr_floor_calibrated and (local.z < 0.10 or local.z > 3.2):
                    self._append_status('Recovered from invalid floor sample.')
                    self._queue_floor_calibration(reset_samples=True)
            self.last_local_head_z = local.z
            self.last_local_head_yaw = local_yaw
            self._apply_tracking_anchor()
        else:
            self._update_desktop_fallback_camera()

    def _nearest_walker(self, max_dist: float = 5.2) -> WalkerNPC | None:
        head = self._head_world_pos()
        best = None
        best_d = max_dist
        for walker in self.walkers:
            d = (walker.root.get_pos(self.render) - head).length()
            if d < best_d:
                best = walker
                best_d = d
        return best

    def _walker_line(self, walker: WalkerNPC) -> str:
        idx = (walker.seed + int(self.elapsed * 0.25)) % len(DIALOGUE_BANK)
        return DIALOGUE_BANK[idx]

    def _trigger_dialogue(self, walker: WalkerNPC) -> None:
        line = self._walker_line(walker)
        self.dialogue_speaker = walker.label
        self.dialogue_text = line
        self.dialogue_timer = 4.2
        walker.talk_cooldown = 4.5
        walker.wander_timer = max(walker.wander_timer, 2.4)
        self._append_status(f'{walker.label} engaged.')
        if self.xr is not None:
            try:
                self.xr.pulse('right', amplitude=0.18, duration_sec=0.04)
            except Exception:
                pass

    def _handle_interactions(self) -> None:
        interact_down = bool(self.keys.get('interact', False)) or self._xr_button_down('primary_button')
        recenter_down = bool(self.keys.get('recenter', False)) or self._xr_button_down('secondary_button')
        menu_down = False
        if self.xr is not None:
            try:
                menu_down = self.xr.button('menu_click', 'left')
            except Exception:
                menu_down = False
        if interact_down and not self.prev_interact_down:
            walker = self._nearest_walker()
            if walker is not None and walker.talk_cooldown <= 0.0:
                self._trigger_dialogue(walker)
        if recenter_down and not self.prev_recenter_down:
            self.xr_floor_calibrated = False
            self._queue_floor_calibration(reset_samples=True)
            self._append_status('Manual recenter requested.')
        if menu_down and not self.prev_menu_down:
            self.toggle_settings()
        self.prev_interact_down = interact_down
        self.prev_recenter_down = recenter_down
        self.prev_menu_down = menu_down

    def _update_walkers(self, dt: float) -> None:
        head = self._head_world_pos()
        self.walker_tick_toggle = not self.walker_tick_toggle
        for walker in self.walkers:
            walker.talk_cooldown = max(0.0, walker.talk_cooldown - dt)
            walker.alert_timer = max(0.0, walker.alert_timer - dt)
            walker.attack_cooldown = max(0.0, walker.attack_cooldown - dt)
            walker.fire_flash = max(0.0, walker.fire_flash - dt * 2.4)
            if walker.destroyed_timer > 0.0:
                walker.destroyed_timer -= dt
                walker.launch_velocity *= max(0.0, 1.0 - dt * 1.2)
                walker.root.set_pos(walker.root.get_pos() + walker.launch_velocity * dt)
                walker.root.setP(walker.root.getP() + dt * 240.0)
                walker.root.setR(walker.root.getR() + dt * 170.0)
                fade = max(0.0, walker.destroyed_timer / 1.35)
                walker.body.setColorScale(1.0, 0.45 + fade * 0.35, 0.45 + fade * 0.45, fade)
                if walker.destroyed_timer <= 0.0:
                    walker.health = walker.max_health
                    walker.root.set_pos(walker.root.get_x(), walker.root.get_y(), 0.0)
                    walker.root.setHpr(_yaw_from_vec(Vec3(random.uniform(-1, 1), random.uniform(-1, 1), 0)), 0, 0)
                    walker.launch_velocity = Vec3(0, 0, 0)
                    walker.body.setColorScale(1, 1, 1, 1)
                    walker.aggressive = False
                    walker.alert_timer = 0.0
                continue
            to_player = head - walker.root.get_pos(self.render)
            flat = Vec3(to_player.x, to_player.y, 0)
            dist = flat.length()
            if self._perf_mode() and dist > 38.0 and self.walker_tick_toggle:
                walker.body.setP(math.sin(self.elapsed * 0.9 + walker.phase) * 0.25)
                continue
            if dist < 18.0 or walker.alert_timer > 0.0:
                walker.aggressive = True
                walker.alert_timer = max(walker.alert_timer, 1.6 if dist < 18.0 else walker.alert_timer)
            elif dist > 24.0:
                walker.aggressive = False
            walker.wander_timer -= dt
            if walker.aggressive and dist > 0.001:
                chase_dir = flat.normalized()
                strafe = Vec3(-chase_dir.y, chase_dir.x, 0) * math.sin(self.elapsed * 0.75 + walker.phase) * 0.22
                walker.wander_dir = (chase_dir + strafe).normalized()
                speed = walker.speed * (1.35 if dist > 7.5 else 0.85)
                if walker.stagger_timer > 0.0:
                    speed *= 0.18
                if dist < 3.2 and walker.attack_cooldown <= 0.0 and walker.stagger_timer <= 0.0:
                    shove_dir = flat.normalized() if dist > 0.001 else Vec3(0, 1, 0)
                    self.player_root.set_pos(self.player_root.get_pos(self.render) + shove_dir * -0.18)
                    walker.attack_cooldown = 1.25
                    walker.fire_flash = 0.4
                    self._append_status(f'{walker.label} rushed your position.')
                elif 5.0 < dist < 18.0 and walker.attack_cooldown <= 0.0 and walker.stagger_timer <= 0.0:
                    self._spawn_enemy_bolt(walker, head)
                    walker.attack_cooldown = 1.9 + random.random() * 0.9
                    walker.fire_flash = 0.7
                candidate = walker.root.get_pos() + walker.wander_dir * speed * dt
            else:
                if walker.wander_timer <= 0.0:
                    rng = random.Random(walker.seed ^ int(self.elapsed * 800))
                    new_dir = Vec3(rng.uniform(-1, 1), rng.uniform(-1, 1), 0)
                    if new_dir.length_squared() < 0.05:
                        new_dir = Vec3(1, 0, 0)
                    new_dir.normalize()
                    walker.wander_dir = new_dir
                    walker.wander_timer = 2.0 + rng.random() * 4.0
                speed = walker.speed * (0.35 if walker.talk_cooldown > 0.0 else 1.0)
                candidate = walker.root.get_pos() + walker.wander_dir * speed * dt
            walker.stagger_timer = max(0.0, walker.stagger_timer - dt)
            walker.cut_flash = max(0.0, walker.cut_flash - dt * 2.2)
            if walker.launch_velocity.length_squared() > 0.001:
                candidate += walker.launch_velocity * dt
                walker.launch_velocity.z -= 15.0 * dt
                walker.launch_velocity.x *= max(0.0, 1.0 - dt * 1.8)
                walker.launch_velocity.y *= max(0.0, 1.0 - dt * 1.8)
                if candidate.z <= walker.hover_height:
                    candidate.z = walker.hover_height
                    if abs(walker.launch_velocity.z) > 1.0:
                        self._spawn_impact_burst(candidate + Vec3(0, 0, 0.2), 0.75)
                    walker.launch_velocity.z = 0.0
            candidate.z = max(walker.hover_height, candidate.z)
            if candidate.z > 0.01 or not self.point_hits_obstacle(candidate, radius=walker.radius, height=walker.height):
                walker.root.set_pos(candidate)
            else:
                walker.wander_dir *= -1
            if walker.wander_dir.length_squared() > 0.001:
                walker.root.set_h(math.degrees(math.atan2(-walker.wander_dir.x, walker.wander_dir.y)))
            bob = math.sin(self.elapsed * (1.45 + 0.25 * float(walker.aggressive)) + walker.phase)
            stagger_pitch = math.sin(walker.stagger_timer * math.pi * 4.0) * 14.0 if walker.stagger_timer > 0.0 else 0.0
            walker.body.setP(bob * (0.45 + 0.55 * float(walker.aggressive)) + stagger_pitch)
            walker.body.setR(math.sin(self.elapsed * 1.05 + walker.phase) * (0.8 + 2.6 * walker.fire_flash) + walker.cut_flash * 8.0)
            walker.body.setZ(math.sin(self.elapsed * 2.0 + walker.phase) * 0.025 + max(0.0, walker.root.get_z()) * 0.28)
            base = self.current_line_color(alpha=0.98)
            hurt_mix = 1.0 - max(0.0, walker.health / walker.max_health)
            walker.body.setColor(
                min(1.0, base[0] + 0.35 * walker.fire_flash + 0.25 * hurt_mix + 0.35 * walker.cut_flash),
                max(0.18, base[1] * (1.0 - 0.35 * hurt_mix) + 0.14 * walker.cut_flash),
                max(0.18, base[2] * (1.0 - 0.48 * hurt_mix)),
                base[3],
            )

    def _build_claw(self, parent: NodePath, side: str) -> ClawHand:
        root = parent.attach_new_node(f'{side}-claw-root')
        root.setScale(0.14)
        root.setP(-90)
        palm_segs = LineSegs(f'{side}-claw-palm')
        palm_segs.setThickness(1.6)
        palm_segs.setColor(*self.current_line_color(alpha=0.95))
        palm_lines = [
            ((-1.2, 0.0, -0.9), (1.2, 0.0, -0.9)),
            ((1.2, 0.0, -0.9), (1.4, 0.0, 0.2)),
            ((1.4, 0.0, 0.2), (0.8, 0.0, 1.0)),
            ((0.8, 0.0, 1.0), (-0.8, 0.0, 1.0)),
            ((-0.8, 0.0, 1.0), (-1.4, 0.0, 0.2)),
            ((-1.4, 0.0, 0.2), (-1.2, 0.0, -0.9)),
            ((-0.7, 0.0, -0.9), (-0.7, 0.0, 1.0)),
            ((0.0, 0.0, -0.9), (0.0, 0.0, 1.0)),
            ((0.7, 0.0, -0.9), (0.7, 0.0, 1.0)),
        ]
        for a, b in palm_lines:
            palm_segs.moveTo(*a)
            palm_segs.drawTo(*b)
        palm = root.attach_new_node(palm_segs.create())
        finger_nodes = []
        finger_offsets = [-0.68, 0.0, 0.68]
        for idx, x in enumerate(finger_offsets):
            finger_root = root.attach_new_node(f'{side}-finger-{idx}')
            finger_root.setPos(x, 0.0, 1.0)
            segs = LineSegs(f'{side}-finger-segs-{idx}')
            segs.setThickness(1.4)
            segs.setColor(*self.current_line_color(alpha=0.95))
            segs.moveTo(0.0, 0.0, 0.0)
            segs.drawTo(0.0, 0.0, 1.1)
            segs.drawTo(0.0, 0.0, 2.0)
            segs.drawTo(0.18 if side == 'right' else -0.18, 0.0, 2.45)
            finger_root.attach_new_node(segs.create())
            finger_nodes.append(finger_root)
        return ClawHand(root=root, palm=palm, finger_nodes=finger_nodes, side=side)

    def _build_claws(self) -> None:
        if self.xr is None:
            return
        self.left_claw = self._build_claw(self.xr.left_grip_anchor, 'left')
        self.right_claw = self._build_claw(self.xr.right_grip_anchor, 'right')

    def _update_claws(self, dt: float) -> None:
        if self.xr is None:
            return
        for side, claw in (('left', self.left_claw), ('right', self.right_claw)):
            if claw is None:
                continue
            try:
                curl = max(self.xr.axis1d('squeeze', side), self.xr.axis1d('trigger', side) * 0.8)
            except Exception:
                curl = 0.0
            for idx, finger in enumerate(claw.finger_nodes):
                bias = idx * 7.0
                finger.setP(-15.0 - curl * (48.0 + bias))
            claw.root.setColorScale(*self.current_line_color(alpha=0.94))

    def _build_blaster(self, parent: NodePath, side: str, desktop: bool = False) -> WristBlaster:
        root = parent.attach_new_node(f'{side}-blaster-root')
        root.setScale(0.11)
        if desktop:
            root.reparent_to(self.camera)
            lateral = -0.48 if side == 'left' else 0.48
            root.setPos(lateral, 1.55, -0.36)
            root.setHpr(0, -2.5, 0)
        else:
            root.setPos(-0.36 if side == 'left' else 0.40, 0.22 if side == 'left' else 0.16, -0.18 if side == 'left' else -0.24)
            root.setHpr(-10 if side == 'left' else 0, -82 if side == 'left' else -90, -8 if side == 'left' else 0)
        segs = LineSegs(f'{side}-blaster-lines')
        segs.setThickness(1.8)
        segs.setColor(*self.current_line_color(alpha=0.96))
        if side == 'left':
            frame = [
                ((-1.45, 0.0, -0.06), (1.65, 0.0, -0.06)),
                ((-1.45, 0.0, 0.06), (1.65, 0.0, 0.06)),
                ((-1.25, 0.0, -0.18), (-1.45, 0.0, 0.0)),
                ((-1.25, 0.0, 0.18), (-1.45, 0.0, 0.0)),
                ((1.65, 0.0, -0.06), (2.55, 0.0, 0.0)),
                ((1.65, 0.0, 0.06), (2.55, 0.0, 0.0)),
                ((-0.24, 0.0, -0.34), (0.14, 0.0, -0.98)),
                ((0.14, 0.0, -0.98), (0.42, 0.0, -0.44)),
                ((0.48, 0.0, -0.12), (0.74, 0.0, 0.36)),
                ((0.74, 0.0, 0.36), (1.22, 0.0, 0.44)),
                ((0.48, 0.0, 0.12), (0.74, 0.0, 0.48)),
            ]
            kind = 'sword'
            muzzle_pos = (2.55, 0.0, 0.0)
        else:
            frame = [
                ((-1.15, 0.0, -0.42), (0.92, 0.0, -0.42)),
                ((0.92, 0.0, -0.42), (1.38, 0.0, -0.12)),
                ((1.38, 0.0, -0.12), (1.82, 0.0, -0.06)),
                ((1.82, 0.0, -0.06), (2.18, 0.0, 0.0)),
                ((2.18, 0.0, 0.0), (1.82, 0.0, 0.06)),
                ((1.82, 0.0, 0.06), (1.38, 0.0, 0.12)),
                ((1.38, 0.0, 0.12), (0.92, 0.0, 0.42)),
                ((0.92, 0.0, 0.42), (-1.02, 0.0, 0.42)),
                ((-1.02, 0.0, 0.42), (-1.28, 0.0, 0.14)),
                ((-1.28, 0.0, 0.14), (-1.15, 0.0, -0.42)),
                ((-0.62, 0.0, -0.64), (0.06, 0.0, -1.02)),
                ((0.06, 0.0, -1.02), (0.54, 0.0, -0.58)),
                ((0.20, 0.0, -0.42), (0.20, 0.0, 0.42)),
                ((0.72, 0.0, -0.32), (2.18, 0.0, 0.0)),
                ((0.72, 0.0, 0.32), (2.18, 0.0, 0.0)),
                ((0.32, 0.0, 0.64), (1.28, 0.0, 0.84)),
                ((0.82, 0.0, 0.42), (1.34, 0.0, 0.84)),
            ]
            kind = 'blaster'
            muzzle_pos = (2.35, 0.0, 0.0)
        for a, b in frame:
            segs.moveTo(*a)
            segs.drawTo(*b)
        root.attach_new_node(segs.create())
        muzzle = root.attach_new_node(f'{side}-blaster-muzzle')
        muzzle.setPos(*muzzle_pos)
        return WristBlaster(root=root, muzzle=muzzle, side=side, kind=kind)

    def _build_blasters(self) -> None:
        if self.xr is not None:
            self.left_blaster = self._build_blaster(self.xr.left_grip_anchor, 'left', desktop=False)
            self.right_blaster = self._build_blaster(self.xr.right_grip_anchor, 'right', desktop=False)
        else:
            self.left_blaster = self._build_blaster(self.render.attach_new_node('desktop-left-blaster-anchor'), 'left', desktop=True)
            self.right_blaster = self._build_blaster(self.render.attach_new_node('desktop-right-blaster-anchor'), 'right', desktop=True)


    def _spawn_enemy_bolt(self, walker: WalkerNPC, target: Vec3) -> None:
        if len([b for b in self.bolts if b.side == 'enemy']) >= int(self.user_config.get('projectile_budget_enemy', 10)):
            return
        origin = walker.root.get_pos(self.render) + Vec3(0, 0, 0.78)
        to_target = target - origin
        if to_target.length_squared() < 1e-6:
            to_target = Vec3(0, 1, 0)
        lead = Vec3(random.uniform(-0.25, 0.25), random.uniform(-0.25, 0.25), random.uniform(-0.04, 0.1))
        velocity = (to_target.normalized() + lead * 0.06).normalized() * 21.0
        segs = LineSegs(f'enemy-bolt-{walker.seed}')
        segs.setThickness(1.8)
        segs.setColor(1.0, 0.38, 0.32, 0.92)
        segs.moveTo(0.0, 0.0, 0.0)
        segs.drawTo(0.0, 0.9, 0.0)
        segs.moveTo(-0.08, 0.12, 0.0)
        segs.drawTo(0.08, 0.7, 0.0)
        root = self.projectile_root.attach_new_node(segs.create())
        root.set_pos(origin)
        root.look_at(origin + velocity)
        root.setTransparency(TransparencyAttrib.MAlpha)
        root.setPythonTag('source_walker', walker)
        self.bolts.append(PlasmaBolt(root=root, velocity=velocity, ttl=1.5, side='enemy', damage=12.0, radius=0.85))
        self._prune_runtime_load()
        self._spawn_impact_burst(origin + Vec3(0, 0, 0.05), 0.45)

    def _spawn_shock_ring(self, pos: Vec3, scale: float = 1.0) -> None:
        segs = LineSegs('shock-ring')
        segs.setThickness(2.1)
        rgb = _rotate_hue(self._line_rgb(), self.day_hue_shift + 0.18, sat_scale=0.85, val_scale=1.18)
        segs.setColor(rgb[0], rgb[1], rgb[2], 0.95)
        radius = 0.95 + scale * 0.42
        points = 18
        for i in range(points + 1):
            a = math.tau * (i / points)
            x = math.cos(a) * radius
            y = math.sin(a) * radius
            z = 0.04 * math.sin(a * 2.0)
            if i == 0:
                segs.moveTo(x, y, z)
            else:
                segs.drawTo(x, y, z)
        root = self.impact_root.attach_new_node(segs.create())
        root.set_pos(pos + Vec3(0, 0, 0.04))
        root.setTransparency(TransparencyAttrib.MAlpha)
        self.impact_bursts.append(ImpactBurst(root=root, ttl=0.32 + scale * 0.08, max_ttl=0.32 + scale * 0.08))
        self._prune_runtime_load()

    def _spawn_impact_burst(self, pos: Vec3, scale: float = 1.0) -> None:
        segs = LineSegs('impact-burst')
        segs.setThickness(1.4 + scale * 0.6)
        burst_color = self.current_line_color(alpha=0.98)
        segs.setColor(*burst_color)
        spokes = 7
        radius = 0.26 * scale
        for i in range(spokes):
            ang = math.tau * i / spokes
            rise = (i % 3 - 1) * 0.08 * scale
            segs.moveTo(0, 0, 0)
            segs.drawTo(math.cos(ang) * radius, math.sin(ang) * radius, rise)
        root = self.impact_root.attach_new_node(segs.create())
        root.setPos(pos)
        root.setTransparency(TransparencyAttrib.MAlpha)
        self.impact_bursts.append(ImpactBurst(root=root, ttl=0.24 + scale * 0.08, max_ttl=0.24 + scale * 0.08))
        self._prune_runtime_load()

    def _spawn_cut_sparks(self, pos: Vec3, forward: Vec3, scale: float = 1.0) -> None:
        segs = LineSegs('cut-sparks')
        segs.setThickness(1.2 + scale * 0.35)
        rgb = _rotate_hue(self._line_rgb(), self.day_hue_shift + 0.16, sat_scale=0.78, val_scale=1.2)
        segs.setColor(rgb[0], rgb[1], rgb[2], 0.98)
        tangent = Vec3(-forward.y, forward.x, 0.0)
        if tangent.length_squared() < 1e-6:
            tangent = Vec3(1, 0, 0)
        tangent.normalize()
        up = Vec3(0, 0, 1)
        for i in range(5):
            spread = tangent * ((i - 2) * 0.18 * scale)
            reach = forward * (0.18 + 0.07 * i) * scale
            segs.moveTo(0, 0, 0)
            segs.drawTo(spread.x + reach.x, spread.y + reach.y, 0.04 * i * scale)
            segs.moveTo(0, 0, 0)
            segs.drawTo(spread.x * 0.55 + up.x, spread.y * 0.55 + up.y, 0.1 + 0.05 * i * scale)
        root = self.impact_root.attach_new_node(segs.create())
        root.setPos(pos)
        root.look_at(pos + forward)
        root.setTransparency(TransparencyAttrib.MAlpha)
        self.impact_bursts.append(ImpactBurst(root=root, ttl=0.18 + scale * 0.06, max_ttl=0.18 + scale * 0.06))
        self._prune_runtime_load()

    def _spawn_blade_trail(self, blaster: WristBlaster) -> None:
        if random.random() > 0.5:
            return
        muzzle = blaster.muzzle.get_pos(self.render)
        root = blaster.root.get_pos(self.render)
        forward = blaster.muzzle.get_quat(self.render).get_forward()
        if forward.length_squared() < 1e-6:
            forward = self.camera.get_quat(self.render).get_forward()
        segs = LineSegs('blade-trail')
        segs.setThickness(1.15)
        rgb = _rotate_hue(self._line_rgb(), self.day_hue_shift + 0.12, sat_scale=0.74, val_scale=1.16)
        segs.setColor(rgb[0], rgb[1], rgb[2], 0.5)
        segs.moveTo(root)
        segs.drawTo((root + muzzle) * 0.5 + Vec3(0, 0, 0.06))
        segs.drawTo(muzzle)
        trail = self.impact_root.attach_new_node(segs.create())
        trail.setTransparency(TransparencyAttrib.MAlpha)
        self.impact_bursts.append(ImpactBurst(root=trail, ttl=0.08, max_ttl=0.08))
        self._prune_runtime_load()

    def _spawn_bolt(self, blaster: WristBlaster, side: str, charge: float = 0.0) -> None:
        if blaster is None:
            return
        muzzle = blaster.muzzle
        world_pos = muzzle.get_pos(self.render)
        forward = muzzle.get_quat(self.render).get_forward()
        if forward.length_squared() < 1e-6:
            forward = self.camera.get_quat(self.render).get_forward()
        right = muzzle.get_quat(self.render).get_right()
        up = muzzle.get_quat(self.render).get_up()
        jitter = (right * (random.uniform(-0.06, 0.06)) + up * (random.uniform(-0.04, 0.04))) * (0.15 + charge * 0.15)
        velocity = (forward + jitter).normalized() * (42.0 + charge * 24.0)
        segs = LineSegs(f'bolt-{side}')
        segs.setThickness(2.2 + charge * 1.2)
        segs.setColor(*self.current_line_color(alpha=0.98))
        length = 0.82 + charge * 0.65
        width = 0.12 + charge * 0.06
        segs.moveTo(-length * 0.45, 0, 0)
        segs.drawTo(length * 0.55, 0, 0)
        segs.moveTo(0.18, 0, -width)
        segs.drawTo(length * 0.55, 0, 0)
        segs.drawTo(0.18, 0, width)
        root = self.projectile_root.attach_new_node(segs.create())
        root.setPos(world_pos)
        root.look_at(world_pos + velocity)
        root.setTransparency(TransparencyAttrib.MAlpha)
        ttl = 1.15 if charge > 0.5 else 0.9
        damage = 22.0 + charge * 28.0
        radius = 1.05 + charge * 0.55
        self.bolts.append(PlasmaBolt(root=root, velocity=velocity, ttl=ttl, side=side, damage=damage, radius=radius))
        self._prune_runtime_load()
        blaster.recoil = 1.0
        blaster.heat = min(1.0, blaster.heat + 0.22 + charge * 0.34)
        self._spawn_impact_burst(world_pos + forward * 0.15, 0.7 + charge * 0.5)
        if charge > 0.72:
            self._spawn_shock_ring(world_pos + forward * 0.22, 0.6 + charge * 0.6)

    def _fire_from_side(self, side: str, charge: float = 0.0) -> None:
        blaster = self.left_blaster if side == 'left' else self.right_blaster
        if blaster is None or blaster.cooldown > 0.0:
            return
        if blaster.kind == 'sword':
            if blaster.combo_timer > 0.0:
                blaster.combo_step = (blaster.combo_step + 1) % 3
            else:
                blaster.combo_step = 0
            blaster.combo_timer = 0.52
            blaster.swing = 1.0
            blaster.swing_dir = (-1.0, 1.0, -1.0)[blaster.combo_step]
            blaster.recoil = 0.75 + 0.1 * blaster.combo_step
            blaster.cooldown = 0.28 if blaster.combo_step else 0.34
            self._sword_strike(blaster)
            pulse_amp = 0.18 + 0.03 * blaster.combo_step
            pulse_dur = 0.025
        else:
            self._spawn_bolt(blaster, side=side, charge=charge)
            blaster.cooldown = 0.32
            pulse_amp = 0.25 + charge * 0.2
            pulse_dur = 0.03 + charge * 0.05
        if self.xr is not None:
            try:
                self.xr.pulse(side, amplitude=pulse_amp, duration_sec=pulse_dur)
            except Exception:
                pass

    def _update_blasters(self, dt: float) -> None:
        left_down = bool(self.keys.get('fire_left', False))
        right_down = bool(self.keys.get('fire_right', False))
        if self.xr is not None:
            try:
                left_down = left_down or self.xr.axis1d('trigger', 'left') > 0.42
                right_down = right_down or self.xr.axis1d('trigger', 'right') > 0.42
            except Exception:
                pass
        for blaster in (self.left_blaster, self.right_blaster):
            if blaster is None:
                continue
            blaster.cooldown = max(0.0, blaster.cooldown - dt)
            blaster.recoil = max(0.0, blaster.recoil - dt * 7.5)
            blaster.combo_timer = max(0.0, blaster.combo_timer - dt)
            blaster.heat = max(0.0, blaster.heat - dt * 0.4)
            if blaster.side == 'right':
                if right_down:
                    blaster.charge = min(1.0, blaster.charge + dt * 1.25)
                elif self.prev_fire_right_down:
                    self._fire_from_side('right', charge=max(0.12, blaster.charge))
                    blaster.charge = 0.0
            else:
                if left_down and blaster.cooldown <= 0.0 and not self.prev_fire_left_down:
                    self._fire_from_side('left', charge=0.0)
                blaster.charge = 0.0
            kick = -0.18 * blaster.recoil
            sway = 0.03 * math.sin(self.elapsed * 8.0 + (0.0 if blaster.side == 'left' else 0.9))
            if blaster.kind == 'sword':
                blaster.swing = max(0.0, blaster.swing - dt * (3.0 + 0.25 * blaster.combo_step))
                combo_bias = (-14.0, 8.0, -26.0)[blaster.combo_step]
                slash = math.sin((1.0 - blaster.swing) * math.pi) * (42.0 + blaster.combo_step * 8.0) * blaster.swing_dir
                if self.xr is None:
                    blaster.root.setPos(-0.64 + sway * 0.55, 1.34 - blaster.recoil * 0.08, -0.30 + kick * 0.8)
                    blaster.root.setHpr(-22.0 + combo_bias + slash * 0.34, -28.0 - blaster.recoil * 10.0, -56.0 + slash)
                else:
                    blaster.root.setPos(-0.22 + sway * 0.35, 0.18 - blaster.recoil * 0.03, -0.12 + kick * 0.55)
                    blaster.root.setHpr(-24.0 + combo_bias * 0.25 + slash * 0.22, -104.0 - blaster.recoil * 9.0, -34.0 + slash * 0.52)
                sword_rgb = _rotate_hue(self._line_rgb(), self.day_hue_shift + 0.11, sat_scale=0.82, val_scale=1.12)
                glow = 0.18 * blaster.swing + 0.08 * (blaster.combo_step > 0)
                blaster.root.setColorScale(min(1.25, sword_rgb[0] + glow), min(1.25, sword_rgb[1] + glow), min(1.25, sword_rgb[2] + glow), 0.98)
                if blaster.swing > 0.08:
                    self._spawn_blade_trail(blaster)
            else:
                if self.xr is None:
                    lateral = 0.54
                    blaster.root.setPos(lateral + sway, 1.55 - blaster.recoil * 0.06, -0.36 + kick)
                    blaster.root.setP(-4.0 - blaster.recoil * 22.0)
                    blaster.root.setR(10.0 + sway * 28.0)
                else:
                    blaster.root.setPos(0.42 + sway, 0.18 - blaster.recoil * 0.03, -0.24 + kick)
                    blaster.root.setP(-92 - blaster.recoil * 12.0)
                    blaster.root.setR(4.0)
                tint = self.current_line_color(alpha=0.95)
                boost = 0.2 * blaster.charge + 0.14 * blaster.heat
                blaster.root.setColorScale(min(1.3, tint[0] + boost), min(1.3, tint[1] + boost), min(1.3, tint[2] + boost), tint[3])
        self.prev_fire_left_down = left_down
        self.prev_fire_right_down = right_down


    def _sword_strike(self, weapon: WristBlaster) -> None:
        tip = weapon.muzzle.get_pos(self.render)
        origin = weapon.root.get_pos(self.render)
        forward = weapon.muzzle.get_quat(self.render).get_forward()
        if forward.length_squared() < 1e-6:
            forward = self.camera.get_quat(self.render).get_forward()
        forward.z = 0.0
        if forward.length_squared() < 1e-6:
            forward = Vec3(0, 1, 0)
        forward.normalize()
        self._spawn_impact_burst(tip, 0.95)
        self._spawn_cut_sparks(tip, forward, 0.9 + 0.12 * weapon.combo_step)
        self.last_parry_timer = max(self.last_parry_timer, 0.22 + 0.03 * weapon.combo_step)
        hit_count = 0
        for walker in self.walkers:
            if walker.destroyed_timer > 0.0:
                continue
            delta = walker.root.get_pos(self.render) - origin
            planar = Vec3(delta.x, delta.y, 0.0)
            if planar.length() > 4.3:
                continue
            to_tip = walker.root.get_pos(self.render) - tip
            if to_tip.length() > 2.4:
                continue
            facing = planar.normalized() if planar.length_squared() > 1e-6 else forward
            if forward.dot(facing) < -0.05:
                continue
            damage = 36.0 + weapon.combo_step * 9.0
            radius = 1.75 + weapon.combo_step * 0.18
            hit_pos = walker.root.get_pos(self.render) + Vec3(0, 0, 0.7)
            self._spawn_cut_sparks(hit_pos, forward, 1.0 + 0.1 * weapon.combo_step)
            self._damage_walker(walker, PlasmaBolt(root=weapon.root, velocity=forward * 28.0, ttl=0.0, side='left', damage=damage, radius=radius), hit_pos)
            walker.stagger_timer = max(walker.stagger_timer, 0.32 + 0.08 * weapon.combo_step)
            walker.cut_flash = max(walker.cut_flash, 0.85)
            hit_count += 1
        if hit_count >= 2:
            self._append_status(f'Sword combo cleaved {hit_count} targets.')

    def _update_projectiles(self, dt: float) -> None:
        self.last_parry_timer = max(0.0, self.last_parry_timer - dt)
        self.parry_flash_timer = max(0.0, self.parry_flash_timer - dt)
        for burst in list(self.impact_bursts):
            burst.ttl -= dt
            life = max(0.0, burst.ttl / burst.max_ttl)
            burst.root.setScale(1.0 + (1.0 - life) * 1.8)
            burst.root.setColorScale(1.0, 1.0, 1.0, life)
            if burst.ttl <= 0.0:
                burst.root.remove_node()
                self.impact_bursts.remove(burst)
        for bolt in list(self.bolts):
            bolt.ttl -= dt
            last_pos = bolt.root.get_pos(self.render)
            new_pos = last_pos + bolt.velocity * dt
            bolt.root.set_pos(new_pos)
            bolt.root.setScale(1.0 + math.sin(self.elapsed * 22.0) * 0.05, 1.0, 1.0)
            if self.point_hits_obstacle(new_pos, radius=0.12, height=1.0):
                self._spawn_impact_burst(new_pos, 0.9)
                if bolt.side != 'enemy' and bolt.damage >= 44.0:
                    self._spawn_shock_ring(new_pos, 0.75)
                bolt.root.remove_node()
                self.bolts.remove(bolt)
                continue
            if bolt.side == 'enemy':
                sword_tip = self.left_blaster.muzzle.get_pos(self.render) if self.left_blaster is not None else self._head_world_pos()
                to_bolt = new_pos - sword_tip
                parry_ready = self.last_parry_timer > 0.0 and self.left_blaster is not None and self.left_blaster.swing > 0.1
                if parry_ready and to_bolt.length() <= 1.6:
                    forward = self.left_blaster.muzzle.get_quat(self.render).get_forward()
                    if forward.length_squared() < 1e-6:
                        forward = self.camera.get_quat(self.render).get_forward()
                    forward.z = 0.0
                    if forward.length_squared() < 1e-6:
                        forward = Vec3(0, 1, 0)
                    forward.normalize()
                    bolt.side = 'right'
                    bolt.damage = 22.0
                    bolt.radius = 1.05
                    bolt.ttl = 1.15
                    bolt.velocity = (forward + Vec3(random.uniform(-0.08, 0.08), random.uniform(-0.08, 0.08), random.uniform(-0.02, 0.08))).normalized() * 30.0
                    bolt.root.look_at(new_pos + bolt.velocity)
                    bolt.root.setColorScale(0.7, 1.0, 1.0, 1.0)
                    self.parry_flash_timer = 0.22
                    self._spawn_cut_sparks(new_pos, forward, 0.92)
                    self._spawn_shock_ring(new_pos, 0.42)
                    self._append_status('Parry deflect.')
                    if self.xr is not None:
                        try:
                            self.xr.pulse('left', amplitude=0.3, duration_sec=0.045)
                        except Exception:
                            pass
                    continue
                head = self._head_world_pos()
                if (head - new_pos).length() <= 0.92:
                    self._spawn_impact_burst(new_pos, 0.8)
                    self._append_status('Incoming bolt hit your rig.')
                    bolt.root.remove_node()
                    self.bolts.remove(bolt)
                    continue
            hit_target = None
            for walker in self.walkers:
                if walker.destroyed_timer > 0.0:
                    continue
                if bolt.side == 'enemy' and bolt.root.getPythonTag('source_walker') is walker:
                    continue
                if (walker.root.get_pos(self.render) - new_pos).length() <= bolt.radius and bolt.side != 'enemy':
                    hit_target = walker
                    break
            if hit_target is not None:
                self._damage_walker(hit_target, bolt, new_pos)
                if bolt.damage >= 44.0:
                    self._spawn_shock_ring(new_pos, 0.85)
                bolt.root.remove_node()
                self.bolts.remove(bolt)
                continue
            if bolt.ttl <= 0.0:
                bolt.root.remove_node()
                self.bolts.remove(bolt)

    def _damage_walker(self, walker: WalkerNPC, bolt: PlasmaBolt, hit_pos: Vec3) -> None:
        walker.health -= bolt.damage
        walker.alert_timer = max(walker.alert_timer, 5.5)
        walker.aggressive = True
        launch_dir = (walker.root.get_pos(self.render) - self._head_world_pos())
        launch_dir.z = 0
        if launch_dir.length_squared() < 0.001:
            launch_dir = Vec3(0, 1, 0)
        launch_dir.normalize()
        walker.launch_velocity = launch_dir * (4.4 + bolt.damage * 0.05) + Vec3(0, 0, 5.8 + bolt.damage * 0.06)
        walker.fire_flash = 0.55
        if bolt.side == 'left':
            walker.stagger_timer = max(walker.stagger_timer, 0.36)
            walker.cut_flash = max(walker.cut_flash, 0.9)
        self._spawn_impact_burst(hit_pos, 1.15 + bolt.damage * 0.01)
        if walker.health <= 0.0:
            walker.destroyed_timer = 1.35
            walker.attack_cooldown = 999.0
            walker.wander_dir = Vec3(0, 0, 0)
            self._append_status(f'{walker.label} neutralized.')
        else:
            self._append_status(f'{walker.label} hit {max(0.0, walker.health):.0f}%')

    def _update_ships(self, dt: float) -> None:
        self.next_ship_timer -= dt
        if self.next_ship_timer <= 0.0 and len(self.sky_ships) < 2:
            self._spawn_sky_ship()
            self.next_ship_timer = random.uniform(16.0, 32.0)
        for ship in list(self.sky_ships):
            ship.lifetime -= dt
            ship.root.set_pos(ship.root.get_pos() + ship.velocity * dt)
            ship.root.setR(math.sin(self.elapsed * 0.8 + ship.phase) * 6.0)
            ship.root.setZ(ship.root.get_z() + math.sin(self.elapsed * 0.7 + ship.phase) * 0.03)
            ship.root.setColorScale(*self._ship_color(alpha=0.58 + 0.18 * math.sin(self.elapsed * 0.7 + ship.phase)))
            if ship.lifetime <= 0.0:
                ship.root.remove_node()
                self.sky_ships.remove(ship)

    def _late_sky_task(self, task: Task):
        head = self._head_world_pos()
        self.sky_root.set_pos(head)
        return Task.cont

    def _update_ui_task(self, task: Task):
        district = self.current_district_label()
        world_name = WORLD_COLOR_PRESETS[int(self.user_config.get('world_color_index', 0))][0]
        line_name = LINE_COLOR_PRESETS[int(self.user_config.get('line_color_index', 0))][0]
        player_bolts = sum(1 for b in self.bolts if b.side != 'enemy')
        enemy_bolts = sum(1 for b in self.bolts if b.side == 'enemy')
        hud_lines = [
            APP_NAME,
            f'District: {district}',
            f'Enemies: {len(self.walkers)}',
            f'FX: P{player_bolts}/E{enemy_bolts}/B{len(self.impact_bursts)}',
            f'Perf: {"VR Safe" if self._perf_mode() else "Full"}',
            f'World: {world_name}',
            f'Lines: {line_name}',
        ]
        settings_lines = [
            'Esc settings | H HUD | F12 screenshot | G set floor',
            '',
            f'Draw distance: {int(float(self.user_config.get("max_view_distance", 620.0)))}',
            f'Move speed: {float(self.user_config.get("movement_speed", 2.55)):.2f}',
            f'World color: {world_name}',
            f'Line color: {line_name}',
            f'Music: {"On" if self.user_config.get("music_enabled", True) else "Off"}',
            f'Eye height: {self.eye_height_m:.2f} m (6ft profile)',
            f'VR perf mode: {"On" if self._perf_mode() else "Off"}',
            f'Budgets: walkers {int(self.user_config.get("walker_budget", 24))} | player bolts {int(self.user_config.get("projectile_budget_player", 18))} | enemy bolts {int(self.user_config.get("projectile_budget_enemy", 10))} | bursts {int(self.user_config.get("effect_budget", 24))}',
            '',
            'Interaction:',
            '- Approach a walker and press F / A / X to talk',
            '- Press R / B / Y to recenter floor and orientation',
            '- Left trigger / LMB long-sword combo slash / parry deflect',
            '- Right trigger / RMB charge-shot wrist blaster + shock ring',
            '- Robotic claws follow controller tracking',
        ]
        if self.xr is not None:
            try:
                diag = self.xr.get_diagnostics()
                self.xr_tracking_space_name = diag.tracking_space
                hud_lines.extend([
                    f'Runtime: {diag.runtime_name}',
                    f'Session: {diag.session_state}',
                    f'Space: {diag.tracking_space}',
                ])
                stable_head = self.xr_floor_samples[-1] if self.xr_floor_samples else self.last_local_head_z
                settings_lines.extend([
                    '',
                    f'Runtime: {diag.runtime_name} {diag.runtime_version}',
                    f'Session state: {diag.session_state}',
                    f'Tracking space: {diag.tracking_space}',
                    f'Should render: {diag.should_render}',
                    f'HMD tracked: {diag.headset_tracked}',
                    f'Left tracked: {diag.left_controller_tracked}',
                    f'Right tracked: {diag.right_controller_tracked}',
                    f"Floor settled: {'Yes' if self.xr_floor_calibrated else 'Pending'}",
                    f'Current head Z: {stable_head:.2f} m' if stable_head is not None else 'Current head Z: n/a',
                    '',
                    'VR controls:',
                    '- Left stick: move',
                    '- Right stick: turn',
                    '- A / X: interact',
                    '- Left trigger: sword combo / parry',
                    '- Right trigger: charge shot + shock ring',
                    '- B / Y: queue recenter',
                    '- G: set floor from current head',
                ])
            except Exception as exc:
                settings_lines.extend(['', f'Diagnostics failed: {exc}'])
        else:
            settings_lines.extend([
                '',
                'Desktop fallback controls:',
                '- WASD move',
                '- Q/E or arrows turn',
                '- F interact',
                '- LMB/Z sword combo / parry',
                '- RMB/C charge fire right wrist / shock ring',
                '- R recenter view height',
            ])
        if self.status_lines:
            settings_lines.extend(['', 'Status:'])
            settings_lines.extend(f'- {line}' for line in self.status_lines[-6:])
        self.hud_text['text'] = '\n'.join(hud_lines)
        self.settings_text['text'] = '\n'.join(settings_lines)
        self.dialogue_label['text'] = f'{self.dialogue_speaker}: {self.dialogue_text}' if self.dialogue_timer > 0.0 else ''
        floor_text = ''
        if self.xr is not None:
            if self.xr_floor_pending:
                floor_text = f'Floor settling... {max(0.0, self.xr_floor_settle_timer):.1f}s'
            elif self.xr_floor_calibrated:
                floor_text = f'Floor locked [{self.xr_tracking_space_name}]'
        elif self.parry_flash_timer > 0.0:
            floor_text = 'Desktop fallback mode'
        if self.parry_flash_timer > 0.0:
            self.floor_panel['frameColor'] = (0.08, 0.16, 0.19, 0.90)
            floor_text = (floor_text + '  |  PARRY').strip()
        else:
            self.floor_panel['frameColor'] = (0.03, 0.07, 0.09, 0.82)
        self.floor_label['text'] = floor_text
        if floor_text:
            self.floor_panel.show()
        else:
            self.floor_panel.hide()
        if self.hud_visible:
            self.hud_text.show()
        else:
            self.hud_text.hide()
        return Task.cont

    def _update_world_task(self, task: Task):
        dt = min(0.033, globalClock.getDt())
        self.elapsed += dt
        self.update_palette(dt)
        self._update_player_motion(dt)
        self.generate_city_around_player(force=False)
        self._handle_interactions()
        self._update_walkers(dt)
        self._update_claws(dt)
        self._update_blasters(dt)
        self._update_projectiles(dt)
        self._update_ships(dt)
        if self._perf_mode():
            self._prune_runtime_load()
        self._apply_music_state()
        self.dialogue_timer = max(0.0, self.dialogue_timer - dt)
        return Task.cont


def main() -> None:
    try:
        app = XRWorldWalk()
        app.run()
    except SystemExit:
        raise
    except Exception as exc:
        path = write_crash_report(exc)
        print(f'Crash log written to: {path}')
        raise
