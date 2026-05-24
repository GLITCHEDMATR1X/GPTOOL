import math
import os
import random
import sys
import time
import traceback
from pathlib import Path
from dataclasses import dataclass

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
SHARED_SFX_ROOT = os.fspath(hv_runtime.shared_sfx_root()) if hv_runtime else os.path.join(Path(__file__).resolve().parent.parent, "assets", "shared_sfx")
AUDIO_PROFILE = hv_runtime.load_audio_profile(Path(__file__).resolve().parent) if hv_runtime else {}
_HOLOVERSE_LAST_ESC = 0.0

def holoverse_embedded_escape(default_handler=None):
    if hv_runtime is not None:
        return hv_runtime.embedded_escape_pressed(default_handler)
    if callable(default_handler):
        return default_handler()
    return None

def holoverse_embedded_escape_released():
    if hv_runtime is not None:
        try:
            hv_runtime.embedded_escape_released()
        except Exception:
            pass


def holoverse_return_signal_requested():
    try:
        return bool(HOLOVERSE_EMBEDDED and hv_runtime is not None and hv_runtime.should_return_to_core())
    except Exception:
        return False

def holoverse_poll_return_signal(task=None):
    if hv_runtime is not None:
        hv_runtime.poll_embedded_escape_hold()
        try:
            import builtins
            hv_runtime.rotate_panda_profile_music(getattr(builtins, "base", None), profile=globals().get("AUDIO_PROFILE", {}))
        except Exception:
            pass
    if holoverse_return_signal_requested():
        try:
            if hv_runtime is not None:
                hv_runtime.acknowledge_return_request()
        except Exception:
            pass
        sys.exit(0)
    return getattr(task, "cont", "cont")

from panda3d.core import (
    AmbientLight,
    CardMaker,
    DirectionalLight,
    Fog,
    Material,
    PNMImage,
    Texture,
    TextureStage,
    TransparencyAttrib,
    Vec3,
    Vec4,
    WindowProperties,
    Point2,
    Point3,
    Filename,
    loadPrcFileData,
)
from direct.showbase.Audio3DManager import Audio3DManager
from direct.showbase.ShowBase import ShowBase
from direct.task import Task


LEVEL_NAME = "Level 7"
DEDICATED_HUB_DOOR_INDEX = 1

HEADLESS = os.environ.get("P3D_HEADLESS", "0") == "1"


def panda_audio_path(path):
    """Return a Panda-friendly Filename for OS-specific audio paths.

    HoloVerse profile music can resolve to an absolute Windows path. Passing
    that raw string to Panda3D's audio loader produces Windows-style path
    warnings and can fail to open the file.
    """
    try:
        return Filename.fromOsSpecific(os.fspath(path))
    except Exception:
        return os.fspath(path)

def _read_holoverse_launch_settings(default_w=1600, default_h=900):
    try:
        width = int(float(os.environ.get("MATRIX_GAME_WIDTH", os.environ.get("HOLOVERSE_GAME_WIDTH", default_w))))
    except Exception:
        width = default_w
    try:
        height = int(float(os.environ.get("MATRIX_GAME_HEIGHT", os.environ.get("HOLOVERSE_GAME_HEIGHT", default_h))))
    except Exception:
        height = default_h
    width = max(640, min(3840, width))
    height = max(360, min(2160, height))
    return width, height

LAUNCH_W, LAUNCH_H = _read_holoverse_launch_settings()
PRC = f"""
window-title Fractured Virtual World - Titan Hunt
win-size {LAUNCH_W} {LAUNCH_H}
sync-video 1
show-frame-rate-meter 0
want-pstats 0
texture-minfilter linear-mipmap-linear
texture-magfilter linear
framebuffer-srgb true
cursor-hidden 1
notify-level-glgsg fatal
"""
if HEADLESS:
    PRC += "\naudio-library-name null\nwindow-type offscreen\nload-display p3tinydisplay\n"
loadPrcFileData("", PRC)


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def smoothstep(t: float) -> float:
    t = clamp(t, 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def vlerp(a: Vec3, b: Vec3, t: float) -> Vec3:
    return a + (b - a) * t


def vec_normalized(v: Vec3) -> Vec3:
    out = Vec3(v)
    if out.lengthSquared() > 1e-6:
        out.normalize()
    return out


def point_segment_distance(point: Vec3, seg_a: Vec3, seg_b: Vec3) -> float:
    seg = seg_b - seg_a
    seg_len_sq = seg.lengthSquared()
    if seg_len_sq <= 1e-8:
        return (point - seg_a).length()
    t = clamp((point - seg_a).dot(seg) / seg_len_sq, 0.0, 1.0)
    closest = seg_a + seg * t
    return (point - closest).length()


def install_crash_reporter() -> None:
    os.makedirs("logs", exist_ok=True)

    def handle_exception(exc_type, exc, tb):
        stamp = time.strftime("%Y%m%d_%H%M%S")
        path = os.path.join("logs", f"crash_{stamp}.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write("Fractured Virtual World crash report\n")
            f.write(f"Timestamp: {stamp}\n")
            f.write(f"Python: {sys.version}\n\n")
            traceback.print_exception(exc_type, exc, tb, file=f)
        traceback.print_exception(exc_type, exc, tb)
        print(f"Crash log written to: {path}")

    sys.excepthook = handle_exception


install_crash_reporter()


@dataclass
class Piece:
    node: object
    wire: object
    base_pos: Vec3
    base_hpr: Vec3
    base_scale: Vec3
    spawn_offset: Vec3
    collapse_dir: Vec3
    phase: float
    glitch_amp: float
    kind: str
    tint: Vec4
    wire_rgb: Vec3
    destroyed: bool = False


@dataclass
class Comet:
    head: object
    trail: object
    velocity: Vec3
    phase: float
    min_alpha: float
    max_alpha: float


@dataclass
class TitanPiece:
    node: object
    wire: object
    target_pos: Vec3
    target_hpr: Vec3
    target_scale: Vec3
    source_offset: Vec3
    group: str
    phase: float
    glow: float
    wire_rgb: Vec3
    thrown: bool = False
    active_projectile: object = None
    destroyed: bool = False


@dataclass
class TitanProjectile:
    node: object
    piece: TitanPiece
    owner: object
    velocity: Vec3
    spin: Vec3
    life: float
    gravity: float
    radius: float
    homing: float
    ignore_hit_time: float = 0.18
    deflected: bool = False


@dataclass
class WeaponProjectile:
    node: object
    wire: object
    velocity: Vec3
    spin: Vec3
    life: float
    gravity: float
    side: str


@dataclass
class ShrinkDeletion:
    node: object
    wire: object
    start_pos: Vec3
    start_hpr: Vec3
    start_scale: Vec3
    life: float
    max_life: float
    spin: Vec3
    start_alpha: float
    start_wire_alpha: float


@dataclass
class VariantSpec:
    name: str
    seed: int
    scale: float
    accent: Vec4
    emission: Vec4
    walk_speed: float
    throw_speed: float
    body_width: float
    body_height: float
    shoulder_width: float
    arm_length: float
    leg_spacing: float
    extra_spires: int = 0


@dataclass
class StormCell:
    node: object
    radius: float
    angle: float
    base_z: float
    phase: float
    swirl_speed: float
    base_scale: Vec3


@dataclass
class LightningSprite:
    node: object
    life: float
    max_life: float
    phase: float
    active: bool = False


class Chunk:
    def __init__(self, app, coord, seed):
        self.app = app
        self.coord = coord
        self.seed = seed
        self.rng = random.Random(seed)
        self.node = app.render.attachNewNode(f"chunk_{coord[0]}_{coord[1]}")
        self.node.setPos(coord[0] * app.CHUNK_SIZE, coord[1] * app.CHUNK_SIZE, 0)
        self.state = "assembling"
        self.timer = 0.0
        self.pieces = []
        self.dead = False
        self._build()

    def _tint(self, base):
        jitter = self.rng.uniform(-0.08, 0.08)
        return Vec4(
            clamp(base[0] + jitter, 0.0, 1.0),
            clamp(base[1] + jitter * 0.6, 0.0, 1.0),
            clamp(base[2] + jitter, 0.0, 1.0),
            1.0,
        )

    def _add_piece(self, pos, hpr, scale, kind, tex_name=None):
        body = self.app.box_model.copyTo(self.node)
        body.setPos(pos)
        body.setHpr(hpr)
        body.setScale(scale)
        body.setTransparency(TransparencyAttrib.MAlpha)
        body.setShaderAuto()
        body.setTwoSided(False)

        if kind == "floor":
            tint = self._tint((0.09, 0.08, 0.12))
            tex = self.app.floor_tex
        elif kind == "wall":
            tint = self._tint((0.07, 0.06, 0.10))
            tex = self.app.wall_tex
        else:
            tint = self._tint((0.12, 0.10, 0.16))
            tex = self.app.shard_tex

        if tex_name == "accent":
            tex = self.app.accent_tex
            tint = self._tint((0.20, 0.10, 0.28))

        body.setTexture(tex, 1)
        body.setColorScale(tint)

        mat = Material()
        mat.setShininess(16.0)
        mat.setAmbient((0.3, 0.3, 0.35, 1.0))
        mat.setDiffuse((1.0, 1.0, 1.0, 1.0))
        mat.setEmission((tint[0] * 0.12, tint[1] * 0.12, tint[2] * 0.18, 1.0))
        body.setMaterial(mat, 1)

        wire = self.app.box_model.copyTo(body)
        wire.setScale(1.012)
        wire.setRenderModeWireframe()
        wire.setLightOff(1)
        wire.setTextureOff(1)
        wire.setTransparency(TransparencyAttrib.MAlpha)
        wire_rgb = Vec3(0.25, 0.95, 1.2)
        wire_alpha = 0.35
        wire.setColorScale(wire_rgb.x, wire_rgb.y, wire_rgb.z, wire_alpha)

        if self.rng.random() < 0.38:
            wire_rgb = Vec3(1.1, 0.20, 1.0)
            wire_alpha = 0.30
            wire.setColorScale(wire_rgb.x, wire_rgb.y, wire_rgb.z, wire_alpha)

        spawn_offset = Vec3(
            self.rng.uniform(-4.0, 4.0),
            self.rng.uniform(-4.0, 4.0),
            self.rng.uniform(-2.0, 8.0),
        )
        collapse_dir = Vec3(
            self.rng.uniform(-1.0, 1.0),
            self.rng.uniform(-1.0, 1.0),
            self.rng.uniform(-0.15, 0.35),
        )
        if collapse_dir.lengthSquared() < 0.001:
            collapse_dir = Vec3(0.0, 1.0, 0.0)
        collapse_dir = vec_normalized(collapse_dir)

        piece = Piece(
            node=body,
            wire=wire,
            base_pos=Vec3(pos),
            base_hpr=Vec3(hpr),
            base_scale=Vec3(scale),
            spawn_offset=spawn_offset,
            collapse_dir=collapse_dir,
            phase=self.rng.uniform(0.0, math.tau),
            glitch_amp=self.rng.uniform(0.2, 1.0),
            kind=kind,
            tint=tint,
            wire_rgb=wire_rgb,
        )
        self.pieces.append(piece)

    def _build(self):
        tile = self.app.CHUNK_SIZE / 4.0
        half = self.app.CHUNK_SIZE * 0.5

        for gx in range(4):
            for gy in range(4):
                x = -half + gx * tile + tile * 0.5
                y = -half + gy * tile + tile * 0.5
                if self.rng.random() <= 0.10:
                    continue
                height = self.rng.uniform(-0.18, 0.15)
                if self.rng.random() < 0.15:
                    height += self.rng.uniform(0.5, 1.3)
                self._add_piece(
                    pos=Vec3(x, y, height),
                    hpr=Vec3(
                        self.rng.uniform(-1.5, 1.5),
                        self.rng.uniform(-1.5, 1.5),
                        self.rng.uniform(-1.0, 1.0),
                    ),
                    scale=Vec3(tile * 0.49, tile * 0.49, self.rng.uniform(0.18, 0.35)),
                    kind="floor",
                )

        pillar_count = self.rng.randint(5, 10)
        for _ in range(pillar_count):
            x = self.rng.uniform(-half + 2.0, half - 2.0)
            y = self.rng.uniform(-half + 2.0, half - 2.0)
            z = self.rng.uniform(1.5, 5.0)
            h = self.rng.uniform(3.0, 12.0)
            sx = self.rng.uniform(0.18, 1.4)
            sy = self.rng.uniform(0.18, 1.2)
            self._add_piece(
                pos=Vec3(x, y, z),
                hpr=Vec3(
                    self.rng.uniform(-5.0, 5.0),
                    self.rng.uniform(-5.0, 5.0),
                    self.rng.uniform(-12.0, 12.0),
                ),
                scale=Vec3(sx, sy, h),
                kind="wall",
                tex_name="accent" if self.rng.random() < 0.35 else None,
            )

        shard_count = self.rng.randint(8, 16)
        for _ in range(shard_count):
            self._add_piece(
                pos=Vec3(
                    self.rng.uniform(-half, half),
                    self.rng.uniform(-half, half),
                    self.rng.uniform(2.0, 11.0),
                ),
                hpr=Vec3(
                    self.rng.uniform(0.0, 360.0),
                    self.rng.uniform(0.0, 360.0),
                    self.rng.uniform(0.0, 360.0),
                ),
                scale=Vec3(
                    self.rng.uniform(0.08, 1.3),
                    self.rng.uniform(0.08, 1.3),
                    self.rng.uniform(0.08, 1.8),
                ),
                kind="shard",
                tex_name="accent" if self.rng.random() < 0.55 else None,
            )

        for axis in (-1, 1):
            self._add_piece(
                pos=Vec3(axis * (half - 0.6), 0.0, 2.3),
                hpr=Vec3(0.0, 0.0, 0.0),
                scale=Vec3(0.15, half, 2.5),
                kind="wall",
                tex_name="accent",
            )
            self._add_piece(
                pos=Vec3(0.0, axis * (half - 0.6), 2.3),
                hpr=Vec3(0.0, 0.0, 0.0),
                scale=Vec3(half, 0.15, 2.5),
                kind="wall",
                tex_name="accent",
            )

        for piece in self.pieces:
            piece.node.setPos(piece.base_pos + piece.spawn_offset)
            piece.node.setScale(piece.base_scale * 0.12)
            piece.node.setAlphaScale(0.05)
            piece.node.setHpr(piece.base_hpr + Vec3(35.0, -25.0, 55.0) * piece.glitch_amp)

    def begin_collapse(self):
        if self.state == "collapsing":
            return
        self.state = "collapsing"
        self.timer = 0.0

    def update(self, dt: float, clock: float, player_chunk):
        self.timer += dt
        dist = abs(player_chunk[0] - self.coord[0]) + abs(player_chunk[1] - self.coord[1])

        if self.state == "assembling":
            t = smoothstep(self.timer / 1.25)
            for piece in self.pieces:
                if piece.destroyed:
                    continue
                piece.node.setPos(vlerp(piece.base_pos + piece.spawn_offset, piece.base_pos, t))
                piece.node.setHpr(vlerp(piece.base_hpr + Vec3(35.0, -25.0, 55.0) * piece.glitch_amp, piece.base_hpr, t))
                piece.node.setScale(vlerp(piece.base_scale * 0.12, piece.base_scale, t))
                piece.node.setAlphaScale(0.05 + t * 0.95)
                piece.wire.setAlphaScale(0.10 + t * 0.35)
                piece.wire.setColorScale(*self.app.wire_flash_rgb(piece.wire_rgb), 1.0)
            if self.timer >= 1.25:
                self.state = "stable"
                self.timer = 0.0
            return

        if self.state == "collapsing":
            t = smoothstep(self.timer / 1.05)
            for piece in self.pieces:
                if piece.destroyed:
                    continue
                outward = piece.collapse_dir * (2.0 + 8.0 * piece.glitch_amp) * t
                downward = Vec3(0.0, 0.0, -10.0 * t * t)
                spin = Vec3(120.0, -160.0, 190.0) * piece.glitch_amp * t
                piece.node.setPos(piece.base_pos + outward + downward)
                piece.node.setHpr(piece.base_hpr + spin)
                piece.node.setScale(piece.base_scale * max(0.06, 1.0 - t))
                piece.node.setAlphaScale(max(0.0, 1.0 - t * 1.15))
                piece.wire.setAlphaScale(max(0.0, 0.35 - t * 0.35))
                piece.wire.setColorScale(*self.app.wire_flash_rgb(piece.wire_rgb), 1.0)
            if self.timer >= 1.05:
                self.node.removeNode()
                self.dead = True
            return

        edge_factor = clamp((dist - 0.4) / (self.app.ACTIVE_RADIUS + 0.75), 0.0, 1.0)
        for piece in self.pieces:
            if piece.destroyed:
                continue
            glitch = 0.5 + 0.5 * math.sin(clock * (2.2 + piece.glitch_amp * 4.0) + piece.phase)
            jitter_strength = (0.03 + edge_factor * 0.32) * piece.glitch_amp
            if piece.kind == "shard":
                jitter_strength *= 2.2
            jitter = Vec3(
                math.sin(clock * 2.1 + piece.phase),
                math.cos(clock * 1.7 + piece.phase * 1.13),
                math.sin(clock * 2.9 + piece.phase * 0.7),
            ) * jitter_strength * glitch
            rot = Vec3(
                math.sin(clock * 40.0 * piece.glitch_amp + piece.phase) * 3.5,
                math.cos(clock * 32.0 * piece.glitch_amp + piece.phase) * 3.0,
                math.sin(clock * 28.0 * piece.glitch_amp + piece.phase) * 3.5,
            ) * edge_factor
            piece.node.setPos(piece.base_pos + jitter)
            piece.node.setHpr(piece.base_hpr + rot)

            pulse = 0.18 + 0.17 * math.sin(clock * 3.1 + piece.phase + dist)
            if piece.kind == "shard":
                pulse += 0.08
            alpha = 0.28 + pulse + (1.0 - edge_factor) * 0.08
            piece.wire.setAlphaScale(clamp(alpha, 0.10, 0.52))
            piece.wire.setColorScale(*self.app.wire_flash_rgb(piece.wire_rgb), 1.0)

            if piece.kind != "floor":
                s = 1.0 + math.sin(clock * 2.0 + piece.phase) * 0.012 * piece.glitch_amp
                piece.node.setScale(piece.base_scale * s)


class MagneticTitan:
    def __init__(self, app, spec: VariantSpec, pos: Vec3, heading: float):
        self.app = app
        self.spec = spec
        self.root = app.render.attachNewNode(f"titan_{spec.name}")
        self.root.setPos(pos)
        self.root.setH(heading)
        self.home = Vec3(pos)
        self.rng = random.Random(spec.seed)
        self.pieces = []
        self.projectiles = []
        self.throw_queue = []
        self.state = "dormant"
        self.state_time = 0.0
        self.attack_timer = 0.0
        self.walk_phase = self.rng.uniform(0.0, math.tau)
        self.current_target = Vec3(pos)
        self.escape_called = False
        self.activation_radius = 128.0
        self.escape_radius = 86.0
        self.form_time = 6.0
        self.walk_time = 4.6
        self.rebuild_delay = 1.35
        self.throw_interval = 0.48
        self.root.setScale(spec.scale)
        self.audio_anchor = self.root.attachNewNode("audio_anchor")
        self._load_sounds()
        self._build_body()
        self._reset_pieces(initial=True)

    def _load_sounds(self):
        self.roar_sounds = self.app.load_sound_pool("roar", self.spec.name)
        self.attack_sounds = self.app.load_sound_pool("attack", self.spec.name)
        self.impact_sounds = self.app.load_sound_pool("impact", self.spec.name)
        self.loop_sound = None
        loop_pool = self.app.load_sound_pool("loop", self.spec.name)
        if loop_pool:
            self.loop_sound = loop_pool[0]
            try:
                self.loop_sound.setLoop(True)
                self.loop_sound.setVolume(0.32)
                self.app.attach_sound(self.loop_sound, self.audio_anchor, min_dist=26.0, max_dist=360.0)
                self.loop_sound.play()
            except Exception:
                self.loop_sound = None

    def _pick_sound(self, pool):
        return self.rng.choice(pool) if pool else None

    def _play_sound(self, pool, volume=1.0, node=None, rate=None):
        snd = self._pick_sound(pool)
        if not snd:
            return
        try:
            if node is not None:
                self.app.attach_sound(snd, node, min_dist=18.0, max_dist=320.0)
            snd.stop()
            snd.setVolume(volume)
            if rate is not None and hasattr(snd, "setPlayRate"):
                snd.setPlayRate(rate)
            snd.play()
        except Exception:
            pass

    def _make_piece(self, pos, hpr, scale, group, accent=False):
        body = self.app.box_model.copyTo(self.root)
        body.setPos(pos)
        body.setHpr(hpr)
        body.setScale(scale)
        body.setTransparency(TransparencyAttrib.MAlpha)
        body.setShaderAuto()
        body.setTexture(self.app.accent_tex if accent else self.app.wall_tex, 1)
        base = self.spec.accent
        gray = self.rng.uniform(0.48, 0.82)
        body.setColorScale(
            clamp(gray * 0.82 + base.x * 0.28, 0.0, 1.0),
            clamp(gray * 0.84 + base.y * 0.32, 0.0, 1.0),
            clamp(gray * 0.86 + base.z * 0.45, 0.0, 1.0),
            1.0,
        )
        mat = Material()
        mat.setShininess(12.0 if accent else 7.5)
        mat.setAmbient((0.22, 0.22, 0.25, 1.0))
        mat.setDiffuse((1.0, 1.0, 1.0, 1.0))
        mat.setEmission((self.spec.emission.x, self.spec.emission.y, self.spec.emission.z, 1.0))
        body.setMaterial(mat, 1)

        wire = self.app.box_model.copyTo(body)
        wire.setScale(1.018)
        wire.setRenderModeWireframe()
        wire.setLightOff(1)
        wire.setTextureOff(1)
        wire.setTransparency(TransparencyAttrib.MAlpha)
        wire_rgb = Vec3(base.x * 1.1 + 0.2, base.y * 1.1 + 0.2, base.z * 1.1 + 0.2)
        wire.setColorScale(wire_rgb.x, wire_rgb.y, wire_rgb.z, 0.32)

        radius = max(8.0, pos.length() + 10.0)
        source_offset = Vec3(
            self.rng.uniform(-1.0, 1.0) * radius,
            self.rng.uniform(-1.0, 1.0) * radius,
            self.rng.uniform(0.8, 2.4) * radius,
        )
        if group in ("head", "crown"):
            source_offset.z += 6.0
        piece = TitanPiece(
            node=body,
            wire=wire,
            target_pos=Vec3(pos),
            target_hpr=Vec3(hpr),
            target_scale=Vec3(scale),
            source_offset=source_offset,
            group=group,
            phase=self.rng.uniform(0.0, math.tau),
            glow=self.rng.uniform(0.8, 1.35),
            wire_rgb=wire_rgb,
        )
        self.pieces.append(piece)

    def _cluster(self, x, y, z, sx, sy, sz, count, scatter, group, accent_ratio=0.35):
        for _ in range(count):
            self._make_piece(
                pos=Vec3(
                    x + self.rng.uniform(-scatter, scatter) * sx,
                    y + self.rng.uniform(-scatter, scatter) * sy,
                    z + self.rng.uniform(-scatter, scatter) * sz,
                ),
                hpr=Vec3(
                    self.rng.uniform(-8.0, 8.0),
                    self.rng.uniform(-8.0, 8.0),
                    self.rng.uniform(-16.0, 16.0),
                ),
                scale=Vec3(
                    max(0.22, sx * self.rng.uniform(0.38, 0.88)),
                    max(0.22, sy * self.rng.uniform(0.38, 0.88)),
                    max(0.22, sz * self.rng.uniform(0.38, 0.90)),
                ),
                group=group,
                accent=self.rng.random() < accent_ratio,
            )

    def _build_body(self):
        s = self.spec
        self._cluster(-s.leg_spacing, 0.0, 2.2, 1.35, 1.0, s.body_height * 0.18, 5, 0.35, "left_leg")
        self._cluster(s.leg_spacing, 0.0, 2.2, 1.35, 1.0, s.body_height * 0.18, 5, 0.35, "right_leg")
        self._cluster(-s.leg_spacing * 0.86, 0.0, s.body_height * 0.34, 1.15, 1.0, s.body_height * 0.20, 5, 0.30, "left_leg")
        self._cluster(s.leg_spacing * 0.86, 0.0, s.body_height * 0.34, 1.15, 1.0, s.body_height * 0.20, 5, 0.30, "right_leg")
        self._cluster(0.0, 0.0, s.body_height * 0.52, s.body_width * 0.92, 1.25, 1.5, 6, 0.28, "hips")
        self._cluster(0.0, 0.0, s.body_height * 0.72, s.body_width, 1.45, s.body_height * 0.26, 8, 0.28, "torso", 0.45)
        self._cluster(0.0, 0.0, s.body_height * 0.98, s.shoulder_width, 1.12, 1.25, 7, 0.26, "shoulders", 0.50)
        self._cluster(-s.shoulder_width * 0.84, 0.0, s.body_height * 0.86, 0.9, 0.85, s.arm_length * 0.25, 4, 0.30, "left_arm")
        self._cluster(-s.shoulder_width * 0.92, 0.0, s.body_height * 0.62, 0.84, 0.84, s.arm_length * 0.34, 4, 0.30, "left_arm")
        self._cluster(s.shoulder_width * 0.84, 0.0, s.body_height * 0.86, 0.9, 0.85, s.arm_length * 0.25, 4, 0.30, "right_arm")
        self._cluster(s.shoulder_width * 0.92, 0.0, s.body_height * 0.62, 0.84, 0.84, s.arm_length * 0.34, 4, 0.30, "right_arm")
        self._cluster(0.0, 0.0, s.body_height * 1.20, 1.0, 0.95, 1.1, 5, 0.24, "head", 0.55)

        for i in range(s.extra_spires):
            side = -1.0 if i % 2 == 0 else 1.0
            self._make_piece(
                pos=Vec3(side * (1.2 + i * 0.18), 0.0, s.body_height * (1.32 + i * 0.08)),
                hpr=Vec3(self.rng.uniform(-12, 12), self.rng.uniform(-12, 12), self.rng.uniform(-12, 12)),
                scale=Vec3(0.32, 0.32, 1.4 + i * 0.4),
                group="crown",
                accent=True,
            )

    def _reset_pieces(self, initial=False):
        self.throw_queue = [p for p in self.pieces if p.group not in ("head", "hips", "crown")]
        self.rng.shuffle(self.throw_queue)
        self.projectiles.clear()
        for piece in self.pieces:
            piece.thrown = False
            piece.active_projectile = None
            piece.destroyed = False
            piece.node.reparentTo(self.root)
            piece.node.setPos(piece.target_pos + piece.source_offset)
            piece.node.setHpr(piece.target_hpr)
            piece.node.setScale(piece.target_scale * (0.05 if initial else 0.12))
            piece.node.setAlphaScale(0.0 if initial else 0.06)
            piece.wire.setAlphaScale(0.0 if initial else 0.08)
            piece.wire.setColorScale(*self.app.wire_flash_rgb(piece.wire_rgb), 1.0)
            piece.node.show()
        self.max_integrity = sum(self.app.titan_piece_weight_value(p.group) for p in self.pieces)
        self.current_integrity = self.max_integrity
        self.state_time = 0.0
        self.attack_timer = 0.0

    def activate(self):
        if self.state == "dormant":
            self.state = "assembling"
            self.state_time = 0.0
            self.escape_called = False
            self._play_sound(self.roar_sounds, volume=0.72, node=self.audio_anchor)

    def is_active(self):
        return self.state != "dormant" or bool(self.projectiles)

    def is_escaped_from(self, player_pos: Vec3):
        return (player_pos - self.root.getPos(self.app.render)).length() > self.escape_radius and self.state in ("walking", "throwing")

    def _predict_player_position(self, player_pos: Vec3, player_vel: Vec3, source_world: Vec3):
        to_player = player_pos - source_world
        dist = max(1.0, to_player.length())
        base_time = clamp(dist / max(12.0, self.spec.throw_speed), 0.35, 2.1)
        lead = player_pos + player_vel * base_time * 0.75
        lead.z = clamp(lead.z, 1.6, 8.0)
        return lead, base_time

    def _throw_piece(self, piece: TitanPiece, player_pos: Vec3, player_vel: Vec3):
        if piece.thrown or piece.destroyed:
            return
        source_world = piece.node.getPos(self.app.render)
        target, travel_time = self._predict_player_position(player_pos, player_vel, source_world)
        gravity = 12.0
        launch = (target - source_world) / travel_time
        launch.z += 0.5 * gravity * travel_time
        launch = vec_normalized(launch) * self.spec.throw_speed

        world_hpr = piece.node.getHpr(self.app.render)
        world_scale = piece.node.getScale(self.app.render)
        piece.node.wrtReparentTo(self.app.render)
        piece.node.setPos(source_world)
        piece.node.setHpr(world_hpr)
        piece.node.setScale(world_scale)

        proj = TitanProjectile(
            node=piece.node,
            piece=piece,
            owner=self,
            velocity=launch,
            spin=Vec3(
                self.rng.uniform(-180.0, 180.0),
                self.rng.uniform(-180.0, 180.0),
                self.rng.uniform(-180.0, 180.0),
            ),
            life=3.8,
            gravity=gravity,
            radius=max(1.8, world_scale.length() * 0.20),
            homing=2.8,
        )
        piece.active_projectile = proj
        piece.thrown = True
        self.projectiles.append(proj)
        piece.wire.setAlphaScale(0.52)
        self._play_sound(self.attack_sounds, volume=0.84, node=piece.node, rate=self.rng.uniform(0.9, 1.08))

    def _update_projectiles(self, dt: float, player_pos: Vec3, player_vel: Vec3):
        for proj in list(self.projectiles):
            proj.life -= dt
            pos = proj.node.getPos(self.app.render)

            if proj.deflected:
                target = proj.owner.root.getPos(self.app.render) + Vec3(0.0, 0.0, 6.0)
                desired = vec_normalized(target - pos) * (self.spec.throw_speed * 1.25)
                proj.velocity = vlerp(proj.velocity, desired, clamp(dt * 4.8, 0.0, 0.24))
            else:
                aim, _ = self._predict_player_position(player_pos, player_vel, pos)
                desired = vec_normalized(aim - pos) * self.spec.throw_speed
                proj.velocity = vlerp(proj.velocity, desired, clamp(dt * proj.homing, 0.0, 0.16))

            proj.velocity.z -= proj.gravity * dt
            pos += proj.velocity * dt
            proj.node.setPos(self.app.render, pos)
            proj.node.setHpr(proj.node.getH() + proj.spin.x * dt, proj.node.getP() + proj.spin.y * dt, proj.node.getR() + proj.spin.z * dt)

            if proj.deflected:
                owner_pos = proj.owner.root.getPos(self.app.render) + Vec3(0.0, 0.0, 6.0)
                owner_hit_radius = 5.6 * proj.owner.root.getScale().x
                if (pos - owner_pos).length() <= owner_hit_radius:
                    self.app.destroy_titan_piece(proj.owner, proj.piece, pos, proj.velocity)
                    continue
            else:
                dist_to_player = (pos - player_pos).length()
                proj.ignore_hit_time -= dt
                if self.app.shield_active and dist_to_player <= proj.radius + self.app.shield_radius:
                    self.app.deflect_titan_projectile(proj)
                    self._play_sound(self.impact_sounds, volume=0.62, node=proj.node, rate=self.rng.uniform(1.05, 1.18))
                    continue
                if proj.ignore_hit_time <= 0.0 and dist_to_player <= proj.radius + 1.4:
                    knock = vec_normalized(player_pos - pos)
                    self.app.apply_player_knockback(knock * 12.0 + Vec3(0.0, 0.0, 3.5))
                    self._play_sound(self.impact_sounds, volume=0.92, node=proj.node)
                    self._recover_projectile_piece(proj)
                    continue

            if proj.life <= 0.0 or pos.z < -8.0 or (pos - self.root.getPos(self.app.render)).length() > 180.0:
                self._play_sound(self.impact_sounds, volume=0.74, node=proj.node)
                self._recover_projectile_piece(proj)

    def _recover_projectile_piece(self, proj: TitanProjectile):
        piece = proj.piece
        if proj in self.projectiles:
            self.projectiles.remove(proj)
        piece.active_projectile = None
        proj.deflected = False
        if piece.destroyed:
            if proj.node is not None and not proj.node.isEmpty():
                proj.node.removeNode()
            piece.thrown = False
            return
        piece.node.wrtReparentTo(self.root)
        piece.node.setPos(piece.target_pos + piece.source_offset * 0.28)
        piece.node.setHpr(piece.target_hpr)
        piece.node.setScale(piece.target_scale * 0.12)
        piece.node.setAlphaScale(0.22)
        piece.wire.setAlphaScale(0.18)
        piece.wire.setColorScale(*self.app.wire_flash_rgb(piece.wire_rgb), 1.0)
        piece.thrown = False

    def _animate_assembled_body(self, clock: float, player_pos: Vec3):
        to_player = player_pos - self.root.getPos(self.app.render)
        desired_h = math.degrees(math.atan2(to_player.x, to_player.y))
        current_h = self.root.getH()
        delta = ((desired_h - current_h + 180.0) % 360.0) - 180.0
        self.root.setH(current_h + clamp(delta, -48.0, 48.0) * 0.035)

        body_pulse = 0.5 + 0.5 * math.sin(clock * 1.1 + self.walk_phase)
        for piece in self.pieces:
            if piece.destroyed:
                continue
            if piece.thrown and piece.active_projectile is not None:
                continue
            pos = Vec3(piece.target_pos)
            hpr = Vec3(piece.target_hpr)

            if piece.group in ("left_leg", "right_leg", "left_arm", "right_arm"):
                sign = -1.0 if "left" in piece.group else 1.0
                stride = math.sin(clock * 1.7 + self.walk_phase) * sign
                if "leg" in piece.group:
                    pos.y += stride * 0.18
                    pos.z += abs(stride) * 0.12
                    hpr.x += stride * 10.0
                else:
                    pos.y -= stride * 0.16
                    hpr.x -= stride * 14.0
            elif piece.group == "head":
                pos.z += math.sin(clock * 2.2 + piece.phase) * 0.16
                hpr.z += math.sin(clock * 1.4 + piece.phase) * 4.0
            elif piece.group == "crown":
                pos.z += math.sin(clock * 2.6 + piece.phase) * 0.24
                hpr.y += math.cos(clock * 1.8 + piece.phase) * 6.0

            pos += Vec3(
                math.sin(clock * (1.8 + piece.glow) + piece.phase) * 0.03,
                math.cos(clock * (1.4 + piece.glow) + piece.phase * 0.7) * 0.03,
                math.sin(clock * (2.3 + piece.glow) + piece.phase * 0.4) * 0.05,
            )

            piece.node.setPos(pos)
            piece.node.setHpr(hpr)
            piece.node.setScale(piece.target_scale * (1.0 + body_pulse * 0.015))
            piece.node.setAlphaScale(1.0)
            piece.wire.setAlphaScale(clamp(0.24 + body_pulse * 0.18, 0.18, 0.48))
            piece.wire.setColorScale(*self.app.wire_flash_rgb(piece.wire_rgb), 1.0)

    def update(self, dt: float, clock: float, player_pos: Vec3, player_vel: Vec3):
        self.state_time += dt
        world_pos = self.root.getPos(self.app.render)
        self._update_projectiles(dt, player_pos, player_vel)

        if self.state == "dormant":
            for i, piece in enumerate(self.pieces):
                if piece.destroyed:
                    continue
                orbit = Vec3(
                    math.cos(clock * 0.20 + piece.phase) * (2.2 + (i % 5) * 0.28),
                    math.sin(clock * 0.18 + piece.phase * 0.6) * 0.25,
                    math.sin(clock * 0.22 + piece.phase) * (1.8 + (i % 7) * 0.20),
                )
                piece.node.setPos(piece.target_pos + piece.source_offset * 0.52 + orbit)
                piece.node.setScale(piece.target_scale * 0.08)
                piece.node.setAlphaScale(0.06)
                piece.wire.setAlphaScale(0.08)
                piece.wire.setColorScale(*self.app.wire_flash_rgb(piece.wire_rgb), 1.0)
            return

        if self.state == "assembling":
            t = smoothstep(self.state_time / self.form_time)
            gather_bias = 0.85 + 0.15 * math.sin(clock * 1.4)
            for piece in self.pieces:
                if piece.destroyed:
                    continue
                pos = piece.target_pos + piece.source_offset * (1.0 - t * gather_bias)
                pos += Vec3(
                    math.sin(clock * 2.2 + piece.phase) * (1.0 - t) * 0.55,
                    math.cos(clock * 2.0 + piece.phase) * (1.0 - t) * 0.55,
                    math.sin(clock * 3.1 + piece.phase) * (1.0 - t) * 0.85,
                )
                piece.node.setPos(pos)
                piece.node.setHpr(piece.target_hpr + Vec3((1.0 - t) * 60.0, (1.0 - t) * 35.0, (1.0 - t) * 75.0))
                piece.node.setScale(piece.target_scale * max(0.10, 0.14 + t * 0.86))
                piece.node.setAlphaScale(0.08 + t * 0.92)
                piece.wire.setAlphaScale(0.08 + t * 0.38)
                piece.wire.setColorScale(*self.app.wire_flash_rgb(piece.wire_rgb), 1.0)
            if self.state_time >= self.form_time:
                self.state = "walking"
                self.state_time = 0.0
                self._play_sound(self.roar_sounds, volume=0.88, node=self.audio_anchor, rate=self.rng.uniform(0.9, 1.05))
            return

        if self.state == "walking":
            self.current_target = vlerp(self.current_target, player_pos + Vec3(0.0, 18.0, 22.0), clamp(dt * 0.9, 0.0, 1.0))
            to_target = self.current_target - world_pos
            flat = Vec3(to_target.x, to_target.y, 0.0)
            step = vec_normalized(flat) * self.spec.walk_speed * dt
            if flat.length() > 8.0:
                self.root.setPos(world_pos + step)
            bob = math.sin(clock * 1.7 + self.walk_phase) * 0.18
            self.root.setZ(self.home.z + bob)
            self._animate_assembled_body(clock, player_pos)
            if self.state_time >= self.walk_time:
                self.state = "throwing"
                self.state_time = 0.0
                self.attack_timer = 0.0
            return

        if self.state == "defeated":
            t = smoothstep(min(1.0, self.state_time / 1.6))
            self.root.setZ(self.home.z - t * 3.2 + math.sin(clock * 3.1) * 0.08)
            for piece in self.pieces:
                if piece.destroyed:
                    continue
                drift = vec_normalized(piece.target_pos + Vec3(0.0, 0.0, 2.0))
                if drift.lengthSquared() <= 1e-6:
                    drift = Vec3(0.0, 1.0, 0.4)
                pos = piece.target_pos + drift * (0.8 + 7.0 * t)
                pos.z += math.sin(clock * 4.0 + piece.phase) * 0.12
                piece.node.setPos(pos)
                piece.node.setHpr(piece.target_hpr + Vec3(85.0 * t, 110.0 * t, 140.0 * t))
                piece.node.setScale(piece.target_scale * max(0.05, 1.0 - t * 0.92))
                piece.node.setAlphaScale(max(0.0, 1.0 - t * 1.1))
                piece.wire.setAlphaScale(max(0.0, 0.42 - t * 0.42))
                piece.wire.setColorScale(*self.app.wire_flash_rgb(piece.wire_rgb), 1.0)
            if self.state_time >= 20.0:
                self.root.setPos(self.home)
                self._reset_pieces(initial=False)
                self.state = "assembling"
                self.state_time = 0.0
                self.attack_timer = 0.0
                self.escape_called = False
                self.throw_queue = [p for p in self.pieces if p.group not in ("head", "hips", "crown") and not p.destroyed]
                self.rng.shuffle(self.throw_queue)
                self._play_sound(self.roar_sounds, volume=0.76, node=self.audio_anchor, rate=self.rng.uniform(0.92, 1.06))
            return


        if self.state == "throwing":
            self._animate_assembled_body(clock, player_pos)
            self.attack_timer -= dt
            if self.throw_queue and self.attack_timer <= 0.0:
                next_piece = self.throw_queue.pop(0)
                self._throw_piece(next_piece, player_pos, player_vel)
                self.attack_timer = self.throw_interval
            if not self.throw_queue and not self.projectiles:
                self.state = "reforming"
                self.state_time = 0.0
                self.escape_called = False
            return

        if self.state == "reforming":
            reform = smoothstep(self.state_time / self.rebuild_delay)
            for piece in self.pieces:
                if piece.destroyed:
                    continue
                if piece.active_projectile is not None:
                    continue
                piece.thrown = False
                piece.node.reparentTo(self.root)
                piece.node.setPos(vlerp(piece.target_pos + piece.source_offset * 0.45, piece.target_pos, reform))
                piece.node.setHpr(vlerp(piece.target_hpr + Vec3(18.0, 8.0, 20.0), piece.target_hpr, reform))
                piece.node.setScale(vlerp(piece.target_scale * 0.18, piece.target_scale, reform))
                piece.node.setAlphaScale(0.18 + reform * 0.82)
                piece.wire.setAlphaScale(0.12 + reform * 0.28)
                piece.wire.setColorScale(*self.app.wire_flash_rgb(piece.wire_rgb), 1.0)
            if self.state_time >= self.rebuild_delay:
                self.state = "walking"
                self.state_time = 0.0
                self.throw_queue = [p for p in self.pieces if p.group not in ("head", "hips", "crown") and not p.destroyed]
                self.rng.shuffle(self.throw_queue)
                self._play_sound(self.roar_sounds, volume=0.68, node=self.audio_anchor, rate=self.rng.uniform(0.95, 1.1))


class FracturedWorld(ShowBase):
    CHUNK_SIZE = 32.0
    ACTIVE_RADIUS = 2

    def __init__(self):
        super().__init__()
        self.disableMouse()
        self.setBackgroundColor(0.0, 0.0, 0.0, 1.0)

        self.box_model = self.loader.loadModel("models/box")
        self.box_model.clearModelNodes()
        self.box_model.setTwoSided(False)

        self.floor_tex = self._make_glitch_texture(
            "floor", 128,
            bg=(0.02, 0.02, 0.03),
            c1=(0.10, 0.22, 0.30),
            c2=(0.65, 0.18, 0.76),
            lines=(0.16, 0.90, 1.00),
        )
        self.wall_tex = self._make_glitch_texture(
            "wall", 128,
            bg=(0.01, 0.01, 0.02),
            c1=(0.06, 0.08, 0.15),
            c2=(0.48, 0.10, 0.70),
            lines=(0.28, 0.95, 1.00),
        )
        self.shard_tex = self._make_glitch_texture(
            "shard", 64,
            bg=(0.02, 0.01, 0.03),
            c1=(0.12, 0.08, 0.18),
            c2=(0.75, 0.25, 0.90),
            lines=(0.10, 0.95, 0.95),
        )
        self.accent_tex = self._make_glitch_texture(
            "accent", 64,
            bg=(0.03, 0.01, 0.04),
            c1=(0.18, 0.06, 0.25),
            c2=(0.10, 0.95, 1.00),
            lines=(1.00, 0.20, 0.85),
        )
        self.storm_tex = self._make_glitch_texture(
            "storm", 128,
            bg=(0.03, 0.00, 0.00),
            c1=(0.14, 0.01, 0.02),
            c2=(0.52, 0.02, 0.08),
            lines=(1.00, 0.10, 0.12),
        )
        self.lightning_tex = self._make_lightning_texture(128, 320)
        self.overlay_tex = self._make_overlay_texture(256)
        self.red_flash_strength = 0.0
        self.next_lightning_time = 0.8
        self.storm_rng = random.Random(55331)
        self.hyper_explosions = []
        self.shrink_deletions = []
        self.fx_rng = random.Random(948211)

        self.audio3d = None
        self.loaded_sound_cache = {}
        if not HEADLESS and self.sfxManagerList:
            try:
                self.audio3d = Audio3DManager(self.sfxManagerList[0], self.camera)
                self.audio3d.setDropOffFactor(0.14)
                self.audio3d.setDistanceFactor(1.0)
                self.audio3d.setDopplerFactor(0.25)
            except Exception:
                self.audio3d = None

        self._setup_scene()
        self._setup_player()
        self._setup_weapons()
        self._setup_ui()
        self._setup_audio()
        self._setup_titans()

        self.shield_active = False
        self.shield_charges = 0
        self.shield_time = 0.0
        self.shield_max_time = 6.0
        self.shield_radius = 3.1

        self.keys = {k: False for k in ("w", "a", "s", "d", "shift", "q", "e")}
        self.accept("escape", lambda: holoverse_embedded_escape(sys.exit))
        self.accept("escape-up", holoverse_embedded_escape_released)
        if HOLOVERSE_EMBEDDED:
            self.taskMgr.add(holoverse_poll_return_signal, "holoverse-return-signal")
        self.accept("h", self.toggle_hud)
        self.accept("mouse1", self.fire_weapon_click)
        self.accept("mouse3", self.activate_shield)
        self.accept("f10", self.toggle_mouse_lock)
        for key in self.keys:
            self.accept(key, self._set_key, [key, True])
            self.accept(f"{key}-up", self._set_key, [key, False])

        self.mouse_locked = True
        self.center_x = 0
        self.center_y = 0
        self._refresh_center()
        self._apply_mouse_lock()

        self.chunks = {}
        self.ensure_chunks((0, 0))

        self.time_accum = 0.0
        self.walk_cycle = 0.0
        self.last_speed = 0.0
        self.player_velocity = Vec3(0, 0, 0)
        self.player_knockback = Vec3(0, 0, 0)
        self.active_titan_index = 0
        self.taskMgr.add(self.update, "update_world")

    def _set_key(self, key, value):
        self.keys[key] = value

    def _setup_scene(self):
        self.render.setShaderAuto()

        fog = Fog("void_fog")
        fog.setColor(0.0, 0.0, 0.0)
        fog.setExpDensity(0.035)
        self.render.setFog(fog)

        amb = AmbientLight("amb")
        amb.setColor((0.15, 0.15, 0.17, 1.0))
        self.render.setLight(self.render.attachNewNode(amb))

        key = DirectionalLight("key")
        key.setColor((0.18, 0.65, 0.92, 1.0))
        key_np = self.render.attachNewNode(key)
        key_np.setHpr(-35, -45, 0)
        self.render.setLight(key_np)

        fill = DirectionalLight("fill")
        fill.setColor((0.52, 0.10, 0.72, 1.0))
        fill_np = self.render.attachNewNode(fill)
        fill_np.setHpr(140, -15, 0)
        self.render.setLight(fill_np)

        self.sky_fragments = self.render.attachNewNode("sky_fragments")
        rng = random.Random(1337)
        for _ in range(96):
            frag = self.box_model.copyTo(self.sky_fragments)
            frag.setPos(rng.uniform(-220, 220), rng.uniform(-220, 220), rng.uniform(40, 130))
            frag.setScale(rng.uniform(0.14, 1.1), rng.uniform(0.05, 0.26), rng.uniform(3.0, 12.0))
            frag.setHpr(rng.uniform(0, 360), rng.uniform(0, 360), rng.uniform(0, 360))
            frag.setTexture(self.accent_tex, 1)
            frag.setColorScale(rng.uniform(0.05, 0.22), rng.uniform(0.15, 0.85), rng.uniform(0.35, 1.0), 1.0)
            frag.setLightOff(1)
            frag.setTransparency(TransparencyAttrib.MAlpha)
            frag.setAlphaScale(rng.uniform(0.09, 0.34))

        self._setup_red_storm()

        self.city_root = self.render.attachNewNode("city_shell")
        self.city_anchor_chunk = None
        self.comet_root = self.render.attachNewNode("comets")
        self.comets = []
        self._rebuild_city_shell((0, 0))
        self._spawn_comets()
        self._setup_overlay()


    def _setup_red_storm(self):
        self.storm_root = self.render.attachNewNode("red_storm")
        self.storm_cells = []
        for _ in range(52):
            cell = self.box_model.copyTo(self.storm_root)
            cell.setTexture(self.storm_tex, 1)
            cell.setTransparency(TransparencyAttrib.MAlpha)
            cell.setLightOff(1)
            cell.setTwoSided(True)
            cell.setColorScale(
                self.storm_rng.uniform(0.25, 0.55),
                self.storm_rng.uniform(0.02, 0.06),
                self.storm_rng.uniform(0.04, 0.08),
                self.storm_rng.uniform(0.08, 0.20),
            )
            cell.setScale(
                self.storm_rng.uniform(18.0, 58.0),
                self.storm_rng.uniform(3.5, 12.0),
                self.storm_rng.uniform(1.1, 4.4),
            )
            self.storm_cells.append(
                StormCell(
                    node=cell,
                    radius=self.storm_rng.uniform(170.0, 330.0),
                    angle=self.storm_rng.uniform(0.0, math.tau),
                    base_z=self.storm_rng.uniform(175.0, 255.0),
                    phase=self.storm_rng.uniform(0.0, math.tau),
                    swirl_speed=self.storm_rng.uniform(-0.045, 0.045),
                    base_scale=Vec3(cell.getScale()),
                )
            )

        self.lightning_root = self.render.attachNewNode("storm_lightning")
        self.lightning_sprites = []
        for i in range(8):
            cm = CardMaker(f"red_lightning_{i}")
            cm.setFrame(-0.5, 0.5, -1.0, 1.0)
            node = self.lightning_root.attachNewNode(cm.generate())
            node.setTexture(self.lightning_tex, 1)
            node.setTransparency(TransparencyAttrib.MAlpha)
            node.setLightOff(1)
            node.setDepthWrite(False)
            node.setDepthTest(False)
            node.setBin("transparent", 20)
            node.setBillboardPointEye()
            node.hide()
            self.lightning_sprites.append(
                LightningSprite(
                    node=node,
                    life=0.0,
                    max_life=0.18,
                    phase=self.storm_rng.uniform(0.0, math.tau),
                    active=False,
                )
            )

    def trigger_red_lightning(self):
        self.red_flash_strength = max(self.red_flash_strength, self.storm_rng.uniform(0.72, 1.0))
        burst = 1 if self.storm_rng.random() < 0.72 else 2
        available = [sprite for sprite in self.lightning_sprites if not sprite.active]
        if len(available) < burst:
            available = self.lightning_sprites[:]
        self.storm_rng.shuffle(available)

        for sprite in available[:burst]:
            angle = self.storm_rng.uniform(0.0, math.tau)
            radius = self.storm_rng.uniform(120.0, 340.0)
            height = self.storm_rng.uniform(165.0, 275.0)
            width = self.storm_rng.uniform(10.0, 24.0)
            tall = self.storm_rng.uniform(36.0, 90.0)
            sprite.node.setPos(math.cos(angle) * radius, math.sin(angle) * radius, height)
            sprite.node.setScale(width, 1.0, tall)
            sprite.node.setColorScale(
                self.storm_rng.uniform(1.2, 1.8),
                self.storm_rng.uniform(0.05, 0.14),
                self.storm_rng.uniform(0.06, 0.16),
                self.storm_rng.uniform(0.70, 1.0),
            )
            sprite.node.show()
            sprite.life = sprite.max_life = self.storm_rng.uniform(0.10, 0.22)
            sprite.phase = self.storm_rng.uniform(0.0, math.tau)
            sprite.active = True

    def update_red_storm(self, dt, clock, chunk_center):
        center = Vec3(chunk_center[0] * self.CHUNK_SIZE, chunk_center[1] * self.CHUNK_SIZE, 0.0)
        self.storm_root.setPos(center)
        self.lightning_root.setPos(center)

        if clock >= self.next_lightning_time:
            self.trigger_red_lightning()
            self.next_lightning_time = clock + (
                self.storm_rng.uniform(0.9, 1.8)
                if self.storm_rng.random() < 0.22
                else self.storm_rng.uniform(2.0, 4.4)
            )

        self.red_flash_strength = max(0.0, self.red_flash_strength - dt * (2.6 + self.red_flash_strength * 6.5))

        for cell in self.storm_cells:
            angle = cell.angle + clock * cell.swirl_speed + math.sin(clock * 0.18 + cell.phase) * 0.08
            radius = cell.radius + math.sin(clock * 0.52 + cell.phase) * 7.0
            x = math.cos(angle) * radius
            y = math.sin(angle) * radius
            z = cell.base_z + math.sin(clock * 0.86 + cell.phase) * 5.5
            cell.node.setPos(x, y, z)
            cell.node.setHpr(math.degrees(angle), math.sin(clock * 0.7 + cell.phase) * 8.0, math.cos(clock * 0.6 + cell.phase) * 6.0)
            scale_pulse = 1.0 + math.sin(clock * 0.9 + cell.phase) * 0.08
            cell.node.setScale(cell.base_scale * scale_pulse)
            alpha = clamp(0.08 + 0.06 * math.sin(clock * 1.6 + cell.phase) + self.red_flash_strength * 0.16, 0.06, 0.34)
            cell.node.setColorScale(
                0.36 + 0.22 * math.sin(clock * 0.8 + cell.phase) + self.red_flash_strength * 0.45,
                0.03 + self.red_flash_strength * 0.03,
                0.05 + self.red_flash_strength * 0.04,
                alpha,
            )

        for sprite in self.lightning_sprites:
            if not sprite.active:
                continue
            sprite.life -= dt
            if sprite.life <= 0.0:
                sprite.active = False
                sprite.node.hide()
                continue
            t = sprite.life / max(sprite.max_life, 1e-5)
            flicker = 0.45 + 0.55 * abs(math.sin((1.0 - t) * 24.0 + sprite.phase))
            sprite.node.setAlphaScale(clamp(t * flicker * 1.4, 0.0, 1.0))

    def _setup_overlay(self):
        cm = CardMaker("overlay")
        cm.setFrameFullscreenQuad()
        self.overlay = self.render2d.attachNewNode(cm.generate())
        self.overlay.setTexture(self.overlay_tex, 1)
        self.overlay.setTransparency(TransparencyAttrib.MAlpha)
        self.overlay.setBin("fixed", 100)
        self.overlay.setDepthWrite(False)
        self.overlay.setDepthTest(False)
        self.overlay.setLightOff(1)
        self.overlay.setColor(1.0, 1.0, 1.0, 0.13)

    def _setup_player(self):
        self.player = self.render.attachNewNode("player")
        self.player.setPos(0, 0, 2.1)
        self.pitch_node = self.player.attachNewNode("pitch")
        self.camera.reparentTo(self.pitch_node)
        self.camera.setPos(0, 0, 0)
        self.camera.setHpr(0, 0, 0)
        self.yaw = 0.0
        self.pitch = 0.0


    def _weapon_material(self, tint: Vec4, emission_boost: float = 0.0):
        mat = Material()
        mat.setShininess(22.0)
        mat.setAmbient((0.26, 0.26, 0.30, 1.0))
        mat.setDiffuse((1.0, 1.0, 1.0, 1.0))
        mat.setEmission(
            (
                clamp(tint[0] * (0.10 + emission_boost), 0.0, 1.0),
                clamp(tint[1] * (0.10 + emission_boost), 0.0, 1.0),
                clamp(tint[2] * (0.14 + emission_boost * 1.2), 0.0, 1.0),
                1.0,
            )
        )
        return mat

    def _add_weapon_part(self, parent, pos, hpr, scale, tex, tint, tex_scale=(8.0, 8.0), wire_rgb=None, emission_boost=0.0):
        part = self.box_model.copyTo(parent)
        part.setPos(pos)
        part.setHpr(hpr)
        part.setScale(scale)
        part.setTexture(tex, 1)
        part.setTexScale(TextureStage.getDefault(), tex_scale[0], tex_scale[1])
        part.setColorScale(tint)
        part.setMaterial(self._weapon_material(tint, emission_boost), 1)
        part.setShaderAuto()
        part.setTransparency(TransparencyAttrib.MAlpha)
        part.setTwoSided(False)

        wire = self.box_model.copyTo(part)
        wire.setScale(1.025)
        wire.setRenderModeWireframe()
        wire.setLightOff(1)
        wire.setTextureOff(1)
        wire.setTransparency(TransparencyAttrib.MAlpha)
        rgb = wire_rgb or Vec3(0.28, 0.92, 1.18)
        wire.setColorScale(rgb.x, rgb.y, rgb.z, 0.42)

        self.weapon_wire_nodes.append((wire, rgb))
        return part

    def _weapon_part_wire(self, node):
        if not node or node.isEmpty() or node.getNumChildren() <= 0:
            return None
        wire = node.getChild(0)
        return None if wire.isEmpty() else wire

    def _register_detachable_weapon_part(
        self,
        parent,
        node,
        side,
        local_pos,
        local_hpr,
        local_scale,
        tex,
        tint,
        tex_scale,
        wire_rgb,
        emission_boost,
        phase,
    ):
        self.weapon_detachable_parts.append(
            {
                "parent": parent,
                "node": node,
                "replacement_node": None,
                "projectile": None,
                "side": side,
                "local_pos": Vec3(local_pos),
                "local_hpr": Vec3(local_hpr),
                "local_scale": Vec3(local_scale),
                "tex": tex,
                "tint": Vec4(tint),
                "tex_scale": tex_scale,
                "wire_rgb": Vec3(wire_rgb),
                "emission_boost": emission_boost,
                "phase": phase,
                "state": "attached",
                "replacement_progress": 0.0,
                "replacement_start_pos": Vec3(0.0),
                "replacement_start_hpr": Vec3(0.0),
            }
        )

    def _spawn_replacement_weapon_part(self, slot):
        sign = -1.0 if slot["side"] == "left" else 1.0
        spawn_local = Vec3(
            slot["local_pos"].x + sign * 1.55,
            slot["local_pos"].y - 1.40,
            slot["local_pos"].z + 0.95,
        )
        spawn_hpr = Vec3(
            slot["local_hpr"].x + 32.0,
            slot["local_hpr"].y + 24.0 * sign,
            slot["local_hpr"].z + 65.0 * sign,
        )
        node = self._add_weapon_part(
            slot["parent"],
            spawn_local,
            spawn_hpr,
            slot["local_scale"] * 0.12,
            slot["tex"],
            slot["tint"],
            tex_scale=slot["tex_scale"],
            wire_rgb=slot["wire_rgb"],
            emission_boost=slot["emission_boost"],
        )
        node.setAlphaScale(0.0)
        wire = self._weapon_part_wire(node)
        if wire is not None:
            wire.setAlphaScale(0.0)
        slot["replacement_node"] = node
        slot["replacement_progress"] = 0.0
        slot["replacement_start_pos"] = spawn_local
        slot["replacement_start_hpr"] = spawn_hpr
        slot["state"] = "replacing"

    def fire_weapon_click(self):
        if self.shield_active:
            return
        if self.fire_random_weapon_part():
            self.trigger_weapon_recoil()

    def activate_shield(self):
        if self.shield_active:
            return
        self.shield_active = True
        self.shield_charges = 3
        self.shield_time = self.shield_max_time
        self.shield_root.show()
        self.shield_root.setScale(0.62)
        self.shield_root.setAlphaScale(0.0)

    def _consume_shield_charge(self):
        if not self.shield_active:
            return
        self.shield_charges = max(0, self.shield_charges - 1)
        if self.shield_charges <= 0:
            self.shield_active = False
            self.shield_time = 0.0

    def _screen_ray_for_crosshair(self, side: str):
        screen_x = self.crosshair_screen_x.get(side, 0.0)
        near_point = Point3()
        far_point = Point3()
        if not self.camLens.extrude(Point2(screen_x, 0.0), near_point, far_point):
            origin = self.camera.getPos(self.render)
            return origin, vec_normalized(self.camera.getQuat(self.render).getForward())
        origin = self.render.getRelativePoint(self.camera, near_point)
        far_world = self.render.getRelativePoint(self.camera, far_point)
        direction = vec_normalized(far_world - origin)
        if direction.lengthSquared() <= 1e-6:
            direction = vec_normalized(self.camera.getQuat(self.render).getForward())
        return origin, direction

    def _find_target_along_ray(self, origin: Vec3, direction: Vec3, max_dist: float = 420.0):
        best = None
        best_proj = max_dist

        def consider(kind, owner, piece, point: Vec3, radius: float):
            nonlocal best, best_proj
            rel = point - origin
            proj = rel.dot(direction)
            if proj <= 0.75 or proj >= best_proj:
                return
            lateral = (rel - direction * proj).length()
            hit_radius = max(0.18, radius * 1.08)
            if lateral <= hit_radius:
                best_proj = proj
                best = {
                    "kind": kind,
                    "owner": owner,
                    "piece": piece,
                    "point": origin + direction * proj,
                    "distance": proj,
                    "radius": hit_radius,
                }

        for titan in getattr(self, "titans", []):
            if titan.state == "dormant":
                continue
            for piece in titan.pieces:
                if piece.destroyed or piece.node.isEmpty():
                    continue
                piece_pos = piece.node.getPos(self.render)
                radius = max(0.72, piece.node.getScale(self.render).length() * 0.32)
                consider("titan", titan, piece, piece_pos, radius)

        for chunk in self.chunks.values():
            for piece in chunk.pieces:
                if piece.destroyed or piece.node.isEmpty():
                    continue
                piece_pos = piece.node.getPos(self.render)
                radius = max(0.58, piece.node.getScale(self.render).length() * 0.28)
                consider("chunk", chunk, piece, piece_pos, radius)

        return best

    def _crosshair_pick_point(self, side: str, max_dist: float = 420.0):
        origin, direction = self._screen_ray_for_crosshair(side)
        hit = self._find_target_along_ray(origin, direction, max_dist=max_dist)
        if hit is not None:
            return hit["point"], hit
        return origin + direction * max_dist, None

    def update_crosshair_ui(self, clock: float):
        pulse = 0.5 + 0.5 * math.sin(clock * 4.2)
        rect_alpha = 0.42 + pulse * 0.14
        for bar in self.crosshair_frame_bars:
            if bar is None or bar.isEmpty():
                continue
            bar.setColor(0.22, 1.0, 1.0, rect_alpha)

        for side in ("left", "right"):
            _, hit = self._crosshair_pick_point(side)
            active = hit is not None
            self.crosshair_hit_states[side] = active
            if active:
                r, g, b, a = 1.0, 0.18, 0.18, 0.96
            else:
                r, g, b, a = 0.22, 1.0, 1.0, 0.88
            for arm in self.crosshair_reticles[side]:
                if arm is None or arm.isEmpty():
                    continue
                arm.setColor(r, g, b, a)

    def _play_weapon_shot_sound(self, side: str):
        pool = self.weapon_shot_sounds.get(side, [])
        if not pool:
            return
        snd = self.weapon_rng.choice(pool)
        try:
            snd.stop()
            snd.setVolume(0.55)
            snd.play()
        except Exception:
            pass

    def fire_random_weapon_part(self):
        eligible = [slot for slot in self.weapon_detachable_parts if slot["state"] == "attached" and slot["node"] is not None and not slot["node"].isEmpty()]
        if not eligible:
            return False
        slot = self.weapon_rng.choice(eligible)
        node = slot["node"]
        wire = self._weapon_part_wire(node)
        world_pos = node.getPos(self.render)
        world_hpr = node.getHpr(self.render)
        world_scale = node.getScale(self.render)
        node.wrtReparentTo(self.render)
        node.setPos(world_pos)
        node.setHpr(world_hpr)
        node.setScale(world_scale)

        aim_point, _ = self._crosshair_pick_point(slot["side"], max_dist=420.0)
        aim_dir = vec_normalized(aim_point - world_pos)
        if aim_dir.lengthSquared() <= 1e-6:
            _, aim_dir = self._screen_ray_for_crosshair(slot["side"])
        velocity = aim_dir * 118.0
        projectile = WeaponProjectile(
            node=node,
            wire=wire,
            velocity=velocity,
            spin=Vec3(
                self.weapon_rng.uniform(-220.0, 220.0),
                self.weapon_rng.uniform(-220.0, 220.0),
                self.weapon_rng.uniform(-260.0, 260.0),
            ),
            life=5.8,
            gravity=3.4,
            side=slot["side"],
        )
        self.weapon_projectiles.append({"slot": slot, "projectile": projectile})
        slot["projectile"] = projectile
        slot["node"] = None
        slot["state"] = "projectile"
        self._spawn_replacement_weapon_part(slot)
        self._play_weapon_shot_sound(slot["side"])
        return True

    def _build_weapon(self, side: str):
        sign = -1.0 if side == "left" else 1.0
        base = self.weapon_root.attachNewNode(f"{side}_weapon")
        base.setPos(0.56 * sign, 1.48, -0.47)
        base.setHpr(7.0 * sign, -7.5, -2.0 * sign)
        base.setScale(0.34)
        base.setBin("fixed", 55)
        base.setDepthWrite(False)
        base.setDepthTest(False)
        base.setFogOff(1)

        accent_rgb = Vec4(0.26, 0.98, 1.0, 1.0) if side == "left" else Vec4(1.0, 0.28, 0.86, 1.0)
        accent_wire = Vec3(0.25, 1.0, 1.15) if side == "left" else Vec3(1.15, 0.26, 0.98)

        # Main body blockwork: small repeated textures from the existing glitch world.
        self._add_weapon_part(base, Vec3(0.0, 0.0, 0.0), Vec3(0.0, 0.0, 0.0), Vec3(0.54, 1.04, 0.34), self.wall_tex, Vec4(0.22, 0.22, 0.27, 1.0), tex_scale=(11.0, 11.0))
        self._add_weapon_part(base, Vec3(0.0, -0.02, 0.23), Vec3(0.0, 4.0, 0.0), Vec3(0.34, 0.64, 0.14), self.floor_tex, Vec4(0.40, 0.40, 0.46, 1.0), tex_scale=(13.0, 13.0))
        self._add_weapon_part(base, Vec3(0.0, -0.08, -0.18), Vec3(0.0, -8.0, 0.0), Vec3(0.28, 0.54, 0.12), self.floor_tex, Vec4(0.18, 0.18, 0.22, 1.0), tex_scale=(12.0, 12.0))

        # Barrel and emitter sections.
        self._add_weapon_part(base, Vec3(0.0, 0.86, 0.02), Vec3(0.0, 0.0, 0.0), Vec3(0.24, 0.62, 0.18), self.wall_tex, Vec4(0.18, 0.18, 0.22, 1.0), tex_scale=(12.0, 16.0))
        self._add_weapon_part(base, Vec3(0.0, 1.26, 0.02), Vec3(0.0, 0.0, 0.0), Vec3(0.15, 0.26, 0.15), self.accent_tex, accent_rgb, tex_scale=(7.0, 7.0), wire_rgb=accent_wire, emission_boost=0.20)
        self._add_weapon_part(base, Vec3(0.0, 1.48, 0.02), Vec3(0.0, 0.0, 0.0), Vec3(0.11, 0.14, 0.11), self.shard_tex, accent_rgb, tex_scale=(8.0, 8.0), wire_rgb=accent_wire, emission_boost=0.34)

        # Side architecture ribs / glitch fins.
        for idx, rib_y in enumerate((-0.18, 0.18, 0.56)):
            pos_a = Vec3(0.30 * sign, rib_y, 0.06)
            hpr_a = Vec3(0.0, 0.0, 18.0 * sign)
            scale_a = Vec3(0.08, 0.34, 0.08)
            rib_a = self._add_weapon_part(base, pos_a, hpr_a, scale_a, self.accent_tex, accent_rgb, tex_scale=(10.0, 6.0), wire_rgb=accent_wire, emission_boost=0.10)
            self._register_detachable_weapon_part(base, rib_a, side, pos_a, hpr_a, scale_a, self.accent_tex, accent_rgb, (10.0, 6.0), accent_wire, 0.10, idx * 0.7 + (0.1 if side == "left" else 1.2))
            pos_b = Vec3(-0.30 * sign, rib_y, 0.06)
            hpr_b = Vec3(0.0, 0.0, -18.0 * sign)
            scale_b = Vec3(0.08, 0.34, 0.08)
            rib_b = self._add_weapon_part(base, pos_b, hpr_b, scale_b, self.accent_tex, accent_rgb, tex_scale=(10.0, 6.0), wire_rgb=accent_wire, emission_boost=0.10)
            self._register_detachable_weapon_part(base, rib_b, side, pos_b, hpr_b, scale_b, self.accent_tex, accent_rgb, (10.0, 6.0), accent_wire, 0.10, idx * 0.7 + 0.35 + (0.2 if side == "left" else 1.4))

        # Handle and wrist spine.
        self._add_weapon_part(base, Vec3(0.0, -0.36, -0.56), Vec3(16.0, 0.0, 0.0), Vec3(0.18, 0.26, 0.44), self.shard_tex, Vec4(0.12, 0.12, 0.15, 1.0), tex_scale=(12.0, 9.0))
        self._add_weapon_part(base, Vec3(0.0, -0.10, -0.36), Vec3(-6.0, 0.0, 0.0), Vec3(0.22, 0.34, 0.18), self.floor_tex, Vec4(0.16, 0.16, 0.20, 1.0), tex_scale=(11.0, 11.0))

        # Glitch architecture crown blocks to sell the Panda3D box-built look.
        crown_offsets = [
            Vec3(0.16 * sign, -0.26, 0.34),
            Vec3(-0.14 * sign, 0.04, 0.38),
            Vec3(0.08 * sign, 0.42, 0.28),
            Vec3(-0.10 * sign, 0.70, 0.24),
        ]
        for idx, offset in enumerate(crown_offsets):
            tex = self.floor_tex if idx % 2 == 0 else self.wall_tex
            tint = Vec4(0.34, 0.34, 0.40, 1.0) if idx % 2 == 0 else Vec4(0.16, 0.16, 0.20, 1.0)
            hpr = Vec3(0.0, idx * 7.0, 0.0)
            scale = Vec3(0.12, 0.18, 0.10)
            crown = self._add_weapon_part(base, offset, hpr, scale, tex, tint, tex_scale=(14.0, 14.0))
            self._register_detachable_weapon_part(base, crown, side, offset, hpr, scale, tex, tint, (14.0, 14.0), Vec3(0.28, 0.92, 1.18), 0.0, idx * 0.82 + (0.5 if side == "left" else 1.8))

        # Animated energy rails.
        left_rail = self._add_weapon_part(base, Vec3(0.14 * sign, 0.54, -0.03), Vec3(0.0, 0.0, 0.0), Vec3(0.05, 0.78, 0.05), self.accent_tex, accent_rgb, tex_scale=(4.0, 16.0), wire_rgb=accent_wire, emission_boost=0.18)
        right_rail = self._add_weapon_part(base, Vec3(-0.14 * sign, 0.54, -0.03), Vec3(0.0, 0.0, 0.0), Vec3(0.05, 0.78, 0.05), self.accent_tex, accent_rgb, tex_scale=(4.0, 16.0), wire_rgb=accent_wire, emission_boost=0.18)
        core = self._add_weapon_part(base, Vec3(0.0, 0.98, 0.02), Vec3(0.0, 0.0, 0.0), Vec3(0.14, 0.18, 0.14), self.accent_tex, accent_rgb, tex_scale=(5.0, 5.0), wire_rgb=accent_wire, emission_boost=0.42)

        self.weapon_energy_parts.extend([
            {"node": left_rail, "base_scale": Vec3(0.05, 0.78, 0.05), "phase": 0.0 if side == "left" else 1.4, "accent": accent_rgb, "side": side},
            {"node": right_rail, "base_scale": Vec3(0.05, 0.78, 0.05), "phase": 0.7 if side == "left" else 2.1, "accent": accent_rgb, "side": side},
            {"node": core, "base_scale": Vec3(0.14, 0.18, 0.14), "phase": 1.0 if side == "left" else 2.8, "accent": accent_rgb, "side": side},
        ])

        return base

    def _setup_weapons(self):
        self.weapon_root = self.camera.attachNewNode("weapon_root")
        self.weapon_root.setPos(0.0, 0.0, 0.0)
        self.weapon_root.setHpr(0.0, 0.0, 0.0)
        self.weapon_root.setBin("fixed", 50)
        self.weapon_root.setDepthWrite(False)
        self.weapon_root.setDepthTest(False)
        self.weapon_root.setFogOff(1)
        self.weapon_wire_nodes = []
        self.weapon_energy_parts = []
        self.weapon_detachable_parts = []
        self.weapon_projectiles = []
        self.weapon_rng = random.Random(27017)
        self.weapon_recoil = 0.0
        self.weapon_idle = 0.0
        self.left_weapon = self._build_weapon("left")
        self.right_weapon = self._build_weapon("right")

    def trigger_weapon_recoil(self):
        self.weapon_recoil = clamp(self.weapon_recoil + 0.95, 0.0, 1.4)

    def _update_weapon_slot_visuals(self, dt, clock):
        flash = clamp(self.red_flash_strength, 0.0, 1.0)
        for slot in self.weapon_detachable_parts:
            phase = slot["phase"]
            side_sign = -1.0 if slot["side"] == "left" else 1.0
            breath = math.sin(clock * 0.82 + phase)
            disturbance = math.sin(clock * 0.48 + phase * 1.7)
            target_pos = slot["local_pos"] + Vec3(
                side_sign * disturbance * 0.010,
                breath * 0.040,
                abs(breath) * 0.020,
            )
            target_hpr = slot["local_hpr"] + Vec3(
                breath * 3.2,
                disturbance * 3.8,
                breath * side_sign * 5.0,
            )
            target_scale = slot["local_scale"] * (1.0 + abs(breath) * 0.035)

            node = slot.get("node")
            if node is not None and not node.isEmpty() and slot["state"] == "attached":
                node.setPos(target_pos)
                node.setHpr(target_hpr)
                node.setScale(target_scale)
                node.setAlphaScale(1.0)
                wire = self._weapon_part_wire(node)
                if wire is not None:
                    r, g, b = self.wire_flash_rgb(slot["wire_rgb"])
                    wire.setAlphaScale(clamp(0.28 + abs(breath) * 0.18 + flash * 0.14, 0.18, 0.72))
                    wire.setColorScale(r, g, b, 1.0)

            replacement = slot.get("replacement_node")
            if replacement is not None and not replacement.isEmpty():
                slot["replacement_progress"] = min(1.0, slot["replacement_progress"] + dt * 1.65)
                t = smoothstep(slot["replacement_progress"])
                replacement.setPos(vlerp(slot["replacement_start_pos"], target_pos, t))
                replacement.setHpr(vlerp(slot["replacement_start_hpr"], target_hpr, t))
                replacement.setScale(vlerp(slot["local_scale"] * 0.12, target_scale, t))
                replacement.setAlphaScale(0.08 + t * 0.92)
                wire = self._weapon_part_wire(replacement)
                if wire is not None:
                    r, g, b = self.wire_flash_rgb(slot["wire_rgb"])
                    wire.setAlphaScale(0.08 + t * 0.42)
                    wire.setColorScale(r, g, b, 1.0)
                if slot["replacement_progress"] >= 1.0:
                    slot["node"] = replacement
                    slot["replacement_node"] = None
                    slot["state"] = "attached"

    def update_weapon_projectiles(self, dt):
        if not self.weapon_projectiles:
            return

        for entry in list(self.weapon_projectiles):
            slot = entry["slot"]
            proj = entry["projectile"]
            if proj.node is None or proj.node.isEmpty():
                slot["projectile"] = None
                if entry in self.weapon_projectiles:
                    self.weapon_projectiles.remove(entry)
                continue

            proj.life -= dt
            start_pos = proj.node.getPos(self.render)
            proj.velocity.z -= proj.gravity * dt
            end_pos = start_pos + proj.velocity * dt
            proj.node.setPos(self.render, end_pos)
            proj.node.setHpr(
                proj.node.getH() + proj.spin.x * dt,
                proj.node.getP() + proj.spin.y * dt,
                proj.node.getR() + proj.spin.z * dt,
            )
            if proj.wire is not None and not proj.wire.isEmpty():
                r, g, b = self.wire_flash_rgb(slot["wire_rgb"])
                proj.wire.setAlphaScale(clamp(0.34 + proj.life * 0.06, 0.14, 0.62))
                proj.wire.setColorScale(r, g, b, 1.0)

            hit = self._find_weapon_projectile_hit(start_pos, end_pos)
            expired = proj.life <= 0.0 or end_pos.z < -8.0 or (end_pos - self.player.getPos(self.render)).length() > 320.0

            if hit is not None:
                kind, owner, piece, impact_pos, _ = hit
                if kind == "titan":
                    self.destroy_titan_piece(owner, piece, impact_pos, proj.velocity)
                else:
                    self.destroy_chunk_piece(owner, piece, impact_pos, proj.velocity)
                if proj.node is not None and not proj.node.isEmpty():
                    proj.node.removeNode()
                slot["projectile"] = None
                if slot["state"] == "projectile":
                    slot["state"] = "replacing"
                self.weapon_projectiles.remove(entry)
                continue

            if expired:
                if proj.node is not None and not proj.node.isEmpty():
                    proj.node.removeNode()
                slot["projectile"] = None
                if slot["state"] == "projectile":
                    slot["state"] = "replacing"
                self.weapon_projectiles.remove(entry)

    def update_weapon_viewmodels(self, dt, clock):
        self.weapon_idle += dt
        self.weapon_recoil = max(0.0, self.weapon_recoil - dt * 4.6)
        move_factor = min(1.0, self.last_speed / 18.0)
        bob_x = math.sin(self.walk_cycle * 0.5) * 0.012 * (0.25 + move_factor)
        bob_z = abs(math.sin(self.walk_cycle)) * 0.020 * (0.20 + move_factor)
        idle_x = math.sin(clock * 1.7) * 0.006
        idle_z = math.cos(clock * 1.3) * 0.004
        breath = math.sin(clock * 0.82)
        disturbance = math.sin(clock * 0.48 + 1.3)
        recoil_push = self.weapon_recoil * 0.12
        recoil_pitch = self.weapon_recoil * 10.0
        recoil_roll = self.weapon_recoil * 4.5
        magnet_push = breath * 0.022 + disturbance * 0.008
        magnet_roll = breath * 1.8 + disturbance * 1.2
        magnet_yaw = math.sin(clock * 0.39) * 0.75

        self.weapon_root.setPos(idle_x + bob_x, recoil_push + magnet_push, idle_z - bob_z + abs(breath) * 0.010)
        self.weapon_root.setHpr(magnet_yaw, recoil_pitch + breath * 1.2, -math.sin(clock * 1.1) * 0.8 + magnet_roll * 0.45)

        self.left_weapon.setPos(-0.56 + bob_x * 0.8 - self.weapon_recoil * 0.018 - disturbance * 0.014, 1.48 - recoil_push * 0.6 + breath * 0.030, -0.47 - bob_z * 0.6 + abs(breath) * 0.020)
        self.right_weapon.setPos(0.56 + bob_x * 0.8 + self.weapon_recoil * 0.018 + disturbance * 0.014, 1.48 - recoil_push * 0.6 + breath * 0.030, -0.47 - bob_z * 0.6 + abs(breath) * 0.020)
        self.left_weapon.setHpr(-7.0 + recoil_roll + magnet_roll, -7.5 - recoil_pitch * 0.7 + breath * 2.2, 2.0 + recoil_roll * 0.5 + magnet_roll * 0.45)
        self.right_weapon.setHpr(7.0 - recoil_roll - magnet_roll, -7.5 - recoil_pitch * 0.7 + breath * 2.2, -2.0 - recoil_roll * 0.5 - magnet_roll * 0.45)

        flash = clamp(self.red_flash_strength, 0.0, 1.0)
        for wire, rgb in list(self.weapon_wire_nodes):
            if wire is None or wire.isEmpty():
                continue
            r, g, b = self.wire_flash_rgb(rgb)
            alpha = clamp(0.24 + abs(breath) * 0.10 + flash * 0.20, 0.12, 0.72)
            wire.setColorScale(r, g, b, alpha)

        for part in self.weapon_energy_parts:
            pulse = 0.5 + 0.5 * math.sin(clock * 5.2 + part["phase"])
            scale = part["base_scale"]
            boost = 1.0 + pulse * 0.08 + flash * 0.08 + abs(breath) * 0.06
            part["node"].setScale(scale.x * (1.0 + pulse * 0.05), scale.y * boost, scale.z * (1.0 + pulse * 0.05))
            accent = part["accent"]
            part["node"].setColorScale(
                clamp(accent[0] * (0.78 + pulse * 0.40 + flash * 0.25), 0.0, 1.6),
                clamp(accent[1] * (0.78 + pulse * 0.40 + flash * 0.25), 0.0, 1.6),
                clamp(accent[2] * (0.78 + pulse * 0.48 + flash * 0.28), 0.0, 1.8),
                1.0,
            )

        self.update_crosshair_ui(clock)
        self._update_weapon_slot_visuals(dt, clock)
        self.update_weapon_projectiles(dt)

    def _setup_ui(self):
        self.hud_visible = False
        self._setup_crosshair()
        self._setup_shield_visual()

    def _setup_crosshair(self):
        self.crosshair_root = self.aspect2d.attachNewNode("crosshair_root")
        self.crosshair_root.setBin("fixed", 200)
        self.crosshair_root.setDepthWrite(False)
        self.crosshair_root.setDepthTest(False)
        self.crosshair_root.setTransparency(TransparencyAttrib.MAlpha)
        self.crosshair_root.setLightOff(1)
        self.crosshair_screen_x = {"left": -0.026, "right": 0.026}
        self.crosshair_hit_states = {"left": False, "right": False}
        self.crosshair_reticles = {"left": [], "right": []}
        self.crosshair_frame_bars = []

        frame_specs = [
            (-0.060, 0.060, 0.025, 0.0285),
            (-0.060, 0.060, -0.0285, -0.025),
            (-0.060, -0.0575, -0.0285, 0.0285),
            (0.0575, 0.060, -0.0285, 0.0285),
        ]
        for idx, (l, r, b, t) in enumerate(frame_specs):
            cm = CardMaker(f"crosshair_frame_{idx}")
            cm.setFrame(l, r, b, t)
            bar = self.crosshair_root.attachNewNode(cm.generate())
            bar.setColor(0.22, 1.0, 1.0, 0.50)
            bar.setTransparency(TransparencyAttrib.MAlpha)
            bar.setLightOff(1)
            self.crosshair_frame_bars.append(bar)

        for side, xoff in self.crosshair_screen_x.items():
            reticle_root = self.crosshair_root.attachNewNode(f"reticle_{side}")
            reticle_root.setPos(xoff, 0.0, 0.0)
            for angle in (45.0, -45.0):
                cm = CardMaker(f"crosshair_{side}_{int(angle)}")
                cm.setFrame(-0.0015, 0.0015, -0.0125, 0.0125)
                arm = reticle_root.attachNewNode(cm.generate())
                arm.setR(angle)
                arm.setColor(0.22, 1.0, 1.0, 0.88)
                arm.setTransparency(TransparencyAttrib.MAlpha)
                arm.setLightOff(1)
                self.crosshair_reticles[side].append(arm)

    def _setup_shield_visual(self):
        self.shield_root = self.player.attachNewNode("shield_root")
        self.shield_root.setPos(0.0, 0.0, -0.08)
        self.shield_root.setTransparency(TransparencyAttrib.MAlpha)
        self.shield_root.setLightOff(1)
        self.shield_root.hide()
        self.shield_shells = []

        sphere_model = self.loader.loadModel("models/misc/sphere")
        shell_specs = [
            (3.05, Vec4(0.14, 0.92, 1.0, 0.14), 1.0, 2.4, 0.0),
            (2.72, Vec4(0.24, 0.98, 1.0, 0.11), 0.72, 3.2, 0.8),
            (2.38, Vec4(0.10, 0.72, 0.92, 0.08), 0.46, 4.2, 1.7),
        ]
        for idx, (scale, color, alpha, scroll, phase) in enumerate(shell_specs):
            shell = sphere_model.copyTo(self.shield_root)
            shell.setScale(scale)
            shell.setTexture(self.accent_tex, 1)
            shell.setTexScale(TextureStage.getDefault(), 2.0 + idx * 0.7, 1.3 + idx * 0.4)
            shell.setColorScale(color)
            shell.setTransparency(TransparencyAttrib.MAlpha)
            shell.setTwoSided(True)
            shell.setLightOff(1)
            shell.setShaderOff(1)
            shell.setDepthWrite(False)
            shell.setDepthTest(False)
            self.shield_shells.append({
                "node": shell,
                "base_scale": scale,
                "base_color": color,
                "alpha": alpha,
                "scroll": scroll,
                "phase": phase,
            })

    def update_shield(self, dt: float, clock: float):
        if self.shield_active:
            self.shield_time = max(0.0, self.shield_time - dt)
            if self.shield_time <= 0.0 or self.shield_charges <= 0:
                self.shield_active = False
        if not self.shield_active:
            self.shield_root.setScale(max(0.62, self.shield_root.getScale().x * max(0.0, 1.0 - dt * 5.5)))
            self.shield_root.setAlphaScale(max(0.0, self.shield_root.getSa() - dt * 3.0))
            if self.shield_root.getSa() <= 0.01:
                self.shield_root.hide()
            return

        self.shield_root.show()
        pulse = 0.5 + 0.5 * math.sin(clock * 2.8)
        grow = 1.0 + pulse * 0.035
        self.shield_root.setScale(grow)
        self.shield_root.setAlphaScale(0.60 + pulse * 0.10)
        self.shield_root.setHpr(0.0, 0.0, 0.0)
        charge_boost = 0.90 + 0.08 * self.shield_charges
        for shell in self.shield_shells:
            node = shell["node"]
            if node.isEmpty():
                continue
            p = 0.5 + 0.5 * math.sin(clock * shell["scroll"] + shell["phase"])
            scale = shell["base_scale"] * (1.0 + p * 0.018)
            node.setScale(scale)
            node.setTexOffset(TextureStage.getDefault(), (clock * 0.06 * shell["scroll"]) % 1.0, (clock * 0.025 + shell["phase"] * 0.1) % 1.0)
            base = shell["base_color"]
            alpha = clamp(shell["alpha"] + p * 0.05 + self.red_flash_strength * 0.04, 0.04, 0.24)
            node.setColorScale(base.x * charge_boost, base.y * charge_boost, base.z * charge_boost, alpha)

    def _setup_audio(self):
        music_paths = self._find_audio_files(os.path.join("assets", "music", "loop"))
        try:
            if hv_runtime and hv_runtime.soundtrack_enabled(True):
                profile_music = hv_runtime.profile_music_path(profile=AUDIO_PROFILE)
                if profile_music and profile_music.exists():
                    music_paths.insert(0, os.fspath(profile_music))
        except Exception:
            pass
        self.music = None
        if music_paths:
            try:
                self.music = self.loader.loadMusic(panda_audio_path(music_paths[0]))
                self.music.setLoop(True)
                self.music.setVolume(hv_runtime.music_bus_gain(hv_runtime.profile_music_volume(0.34, profile=AUDIO_PROFILE), bus="ambience") if hv_runtime else 0.38)
                self.music.play()
            except Exception:
                self.music = None

        self.weapon_shot_sounds = {"left": [], "right": []}
        shot_dirs = {
            "left": os.path.join("assets", "sfx", "weapons", "dual_glitch_shots", "left"),
            "right": os.path.join("assets", "sfx", "weapons", "dual_glitch_shots", "right"),
        }
        for side, folder in shot_dirs.items():
            candidates = self._find_audio_files(folder)[:8]
            # The slim HoloVerse export does not always include Fractured's old
            # local weapon SFX folders.  Resolve the mode audio profile through
            # HoloVerse's shared SFX fallback before giving up, so the same-window
            # adapter has real weapon feedback like Vector Wars.
            if not candidates and hv_runtime:
                event_name = "shot_left" if side == "left" else "shot_right"
                try:
                    candidates.extend(os.fspath(p) for p in hv_runtime.profile_sfx_files(event_name, profile=AUDIO_PROFILE))
                except Exception:
                    pass
            if not candidates:
                for shared_folder in (os.path.join(SHARED_SFX_ROOT, "weapons", "lasers"), os.path.join(SHARED_SFX_ROOT, "weapons", "guns")):
                    candidates.extend(self._find_audio_files(shared_folder)[:4])
            for path in candidates[:8]:
                try:
                    snd = self.loader.loadSfx(panda_audio_path(path))
                    if snd:
                        self.weapon_shot_sounds[side].append(snd)
                except Exception:
                    continue

    def _setup_titans(self):
        self.variant_specs = [
            VariantSpec("prime", 7701, 1.55, Vec4(0.28, 0.78, 1.0, 1.0), Vec4(0.04, 0.10, 0.16, 1.0), 3.9, 29.0, 4.8, 20.0, 5.5, 8.0, 2.35, 2),
            VariantSpec("spire", 8811, 1.35, Vec4(0.85, 0.28, 1.0, 1.0), Vec4(0.14, 0.05, 0.12, 1.0), 4.8, 33.0, 3.8, 24.0, 4.6, 9.6, 1.85, 4),
            VariantSpec("bulwark", 9931, 1.75, Vec4(0.18, 1.0, 0.88, 1.0), Vec4(0.04, 0.14, 0.12, 1.0), 3.1, 26.0, 6.4, 18.0, 6.5, 7.2, 2.85, 1),
        ]
        placements = [
            (Vec3(0.0, 118.0, 28.0), 180.0),
            (Vec3(96.0, 90.0, 26.0), 220.0),
            (Vec3(-108.0, 82.0, 25.0), 140.0),
        ]
        self.titans = [MagneticTitan(self, spec, pos, heading) for spec, (pos, heading) in zip(self.variant_specs, placements)]
        for titan in self.titans:
            titan.max_integrity = sum(self.titan_piece_weight_value(piece.group) for piece in titan.pieces)
            titan.current_integrity = titan.max_integrity
        if self.titans:
            self.titans[0].activate()

    def _find_audio_files(self, folder):
        if not os.path.isdir(folder):
            return []
        found = []
        for root, _, files in os.walk(folder):
            for fn in sorted(files):
                if fn.lower().endswith((".wav", ".mp3")):
                    found.append(os.path.join(root, fn))
        return found

    def load_sound_pool(self, cue_name: str, variant_name: str):
        cache_key = (cue_name, variant_name)
        if cache_key in self.loaded_sound_cache:
            return self.loaded_sound_cache[cache_key]

        candidates = []
        if cue_name == "loop":
            candidates.extend(self._find_audio_files(os.path.join("assets", "sfx", "titan", "variants", variant_name, "loop")))
        else:
            candidates.extend(self._find_audio_files(os.path.join("assets", "sfx", "titan", "variants", variant_name, cue_name)))
            candidates.extend(self._find_audio_files(os.path.join("assets", "sfx", "titan", "common", cue_name)))
            candidates.extend(self._find_audio_files(os.path.join("assets", "sfx", "titan", cue_name)))

        sounds = []
        for path in candidates[:12]:
            try:
                snd = self.loader.loadSfx(panda_audio_path(path))
                if snd:
                    sounds.append(snd)
            except Exception:
                continue
        self.loaded_sound_cache[cache_key] = sounds
        return sounds

    def attach_sound(self, sound, node, min_dist=18.0, max_dist=260.0):
        if not sound or not self.audio3d:
            return
        try:
            self.audio3d.detachSound(sound)
        except Exception:
            pass
        try:
            self.audio3d.attachSoundToObject(sound, node)
            self.audio3d.setSoundMinDistance(sound, min_dist)
            self.audio3d.setSoundMaxDistance(sound, max_dist)
        except Exception:
            pass

    def apply_player_knockback(self, impulse: Vec3):
        self.player_knockback += impulse

    def toggle_hud(self):
        return

    def toggle_mouse_lock(self):
        self.mouse_locked = not self.mouse_locked
        self._apply_mouse_lock()

    def _apply_mouse_lock(self):
        if not self.win:
            return
        if os.environ.get('GX_DISABLE_MOUSE_CAPTURE') == '1' or os.environ.get('GLITCHED_MATRIX_DISABLE_MOUSE_CAPTURE') == '1':
            self.mouse_locked = False
        props = WindowProperties()
        props.setCursorHidden(self.mouse_locked)
        if self.mouse_locked:
            if hasattr(WindowProperties, "M_relative"):
                props.setMouseMode(WindowProperties.M_relative)
            else:
                props.setMouseMode(WindowProperties.M_confined)
        else:
            props.setMouseMode(WindowProperties.M_absolute)
        if hasattr(self.win, "requestProperties"):
            self.win.requestProperties(props)
        self._refresh_center()
        if self.mouse_locked and hasattr(self.win, "movePointer"):
            self.win.movePointer(0, self.center_x, self.center_y)

    def _refresh_center(self):
        if not self.win:
            return
        self.center_x = max(1, self.win.getXSize() // 2)
        self.center_y = max(1, self.win.getYSize() // 2)


    def wire_flash_rgb(self, base_rgb: Vec3):
        flash = clamp(self.red_flash_strength, 0.0, 1.0)
        return (
            clamp(base_rgb.x * (1.0 - flash * 0.88) + 1.55 * flash, 0.0, 2.0),
            clamp(base_rgb.y * (1.0 - flash * 0.95) + 0.12 * flash, 0.0, 2.0),
            clamp(base_rgb.z * (1.0 - flash * 0.96) + 0.10 * flash, 0.0, 2.0),
        )

    def titan_piece_weight_value(self, group: str) -> float:
        if group in ("head", "torso"):
            return 2.4
        if group in ("shoulders", "hips"):
            return 1.9
        if group == "crown":
            return 1.6
        return 1.0

    def _safe_effect_pos(self, pos: Vec3):
        player_pos = self.player.getPos(self.render)
        offset = pos - player_pos
        dist = offset.length()
        if dist < 6.5:
            direction = vec_normalized(offset)
            if direction.lengthSquared() <= 1e-6:
                direction = vec_normalized(self.camera.getQuat(self.render).getForward())
            if direction.lengthSquared() <= 1e-6:
                direction = Vec3(0.0, 1.0, 0.0)
            return player_pos + direction * 6.5, True
        return pos, False

    def queue_shrink_deletion(self, node, wire, duration: float = 0.18):
        if node is None or node.isEmpty():
            return
        world_pos = node.getPos(self.render)
        world_hpr = node.getHpr(self.render)
        world_scale = Vec3(node.getScale(self.render))
        node.wrtReparentTo(self.render)
        node.setPos(world_pos)
        node.setHpr(world_hpr)
        node.setScale(world_scale)
        start_wire_alpha = 0.20
        if wire is not None and not wire.isEmpty():
            try:
                start_wire_alpha = max(0.06, wire.getSa())
            except Exception:
                start_wire_alpha = 0.20
        self.shrink_deletions.append(
            ShrinkDeletion(
                node=node,
                wire=wire,
                start_pos=Vec3(world_pos),
                start_hpr=Vec3(world_hpr),
                start_scale=Vec3(world_scale),
                life=duration,
                max_life=duration,
                spin=Vec3(
                    self.fx_rng.uniform(-110.0, 110.0),
                    self.fx_rng.uniform(-110.0, 110.0),
                    self.fx_rng.uniform(-140.0, 140.0),
                ),
                start_alpha=1.0,
                start_wire_alpha=start_wire_alpha,
            )
        )

    def update_shrink_deletions(self, dt: float, clock: float):
        if not self.shrink_deletions:
            return
        for fx in list(self.shrink_deletions):
            if fx.node is None or fx.node.isEmpty():
                if fx in self.shrink_deletions:
                    self.shrink_deletions.remove(fx)
                continue
            fx.life -= dt
            t = 1.0 - clamp(fx.life / max(fx.max_life, 1e-5), 0.0, 1.0)
            shrink = max(0.015, (1.0 - smoothstep(t)) ** 1.35)
            fx.node.setPos(fx.start_pos)
            fx.node.setHpr(
                fx.start_hpr.x + fx.spin.x * t * 0.18,
                fx.start_hpr.y + fx.spin.y * t * 0.18,
                fx.start_hpr.z + fx.spin.z * t * 0.18,
            )
            fx.node.setScale(fx.start_scale * shrink)
            fx.node.setAlphaScale(max(0.0, fx.start_alpha * (1.0 - t * 1.10)))
            if fx.wire is not None and not fx.wire.isEmpty():
                fx.wire.setAlphaScale(max(0.0, fx.start_wire_alpha * (1.0 - t * 1.25)))
            if fx.life <= 0.0:
                fx.node.removeNode()
                self.shrink_deletions.remove(fx)

    def spawn_hyper_wire_explosion(self, pos: Vec3, scale: float = 1.0, base_rgb: Vec3 | None = None):
        pos, was_near_player = self._safe_effect_pos(pos)
        effect_scale = clamp(scale * 0.22, 0.12, 0.42)
        if was_near_player:
            effect_scale *= 0.72

        root = self.render.attachNewNode("hyper_wire_explosion")
        root.setPos(pos)
        root.setTransparency(TransparencyAttrib.MAlpha)
        root.setLightOff(1)
        rng = self.fx_rng
        colors = [
            Vec4(0.28, 1.00, 1.20, 0.22),
            Vec4(1.18, 0.30, 1.00, 0.18),
            Vec4(1.00, 0.78, 0.22, 0.16),
            Vec4(0.65, 0.92, 1.35, 0.20),
        ]
        if base_rgb is not None:
            colors[0] = Vec4(base_rgb.x, base_rgb.y, base_rgb.z, 0.20)

        fragments = []
        for i in range(8):
            node = self.box_model.copyTo(root)
            node.setTransparency(TransparencyAttrib.MAlpha)
            node.setRenderModeWireframe()
            node.setTextureOff(1)
            node.setLightOff(1)
            node.setTwoSided(True)
            color = colors[i % len(colors)]
            node.setColorScale(color.x, color.y, color.z, color.w)
            base_scale = Vec3(
                rng.uniform(0.05, 0.15),
                rng.uniform(0.05, 0.18),
                rng.uniform(0.05, 0.16),
            ) * effect_scale
            node.setScale(base_scale)
            node.setHpr(rng.uniform(0.0, 360.0), rng.uniform(0.0, 360.0), rng.uniform(0.0, 360.0))
            vel = vec_normalized(
                Vec3(rng.uniform(-1.0, 1.0), rng.uniform(-1.0, 1.0), rng.uniform(-0.2, 0.8))
            ) * rng.uniform(2.0, 8.0) * max(0.6, effect_scale)
            spin = Vec3(rng.uniform(-120.0, 120.0), rng.uniform(-120.0, 120.0), rng.uniform(-140.0, 140.0))
            fragments.append({"node": node, "vel": vel, "spin": spin, "base_scale": base_scale, "color": color, "wire": True})

        for axis in range(2):
            ring = self.box_model.copyTo(root)
            ring.setRenderModeWireframe()
            ring.setTextureOff(1)
            ring.setLightOff(1)
            ring.setTransparency(TransparencyAttrib.MAlpha)
            color = colors[(axis + 1) % len(colors)]
            ring.setColorScale(color.x, color.y, color.z, color.w)
            ring.setScale((0.09 + axis * 0.04) * effect_scale, (0.32 + axis * 0.10) * effect_scale, (0.03 + axis * 0.01) * effect_scale)
            ring.setHpr(axis * 42.0, axis * 58.0, axis * 76.0)
            fragments.append({"node": ring, "vel": Vec3(0.0, 0.0, 0.0), "spin": Vec3(70.0, -90.0, 105.0), "base_scale": ring.getScale(), "color": color, "wire": True, "ring": True})

        self.hyper_explosions.append(
            {
                "root": root,
                "fragments": fragments,
                "life": 0.28,
                "max_life": 0.28,
                "phase": rng.uniform(0.0, math.tau),
            }
        )

    def update_hyper_explosions(self, dt: float, clock: float):
        if not self.hyper_explosions:
            return
        for fx in list(self.hyper_explosions):
            fx["life"] -= dt
            t = 1.0 - clamp(fx["life"] / fx["max_life"], 0.0, 1.0)
            pulse = 1.0 + math.sin(clock * 14.0 + fx["phase"]) * 0.05
            for idx, frag in enumerate(fx["fragments"]):
                node = frag["node"]
                if node.isEmpty():
                    continue
                node.setPos(node.getPos() + frag["vel"] * dt)
                spin = frag["spin"]
                node.setHpr(node.getH() + spin.x * dt, node.getP() + spin.y * dt, node.getR() + spin.z * dt)
                scale_boost = 1.0 + t * (0.32 if frag.get("ring") else 0.18)
                node.setScale(frag["base_scale"] * scale_boost * pulse)
                color = frag["color"]
                alpha = max(0.0, color.w * (1.0 - t * 1.35))
                glow = 1.0 + 0.12 * math.sin(clock * 11.0 + idx + fx["phase"])
                node.setColorScale(color.x * glow, color.y * glow, color.z * glow, alpha)
            if fx["life"] <= 0.0:
                fx["root"].removeNode()
                self.hyper_explosions.remove(fx)

    def deflect_titan_projectile(self, proj: TitanProjectile):
        if proj is None or proj.node is None or proj.node.isEmpty() or proj.deflected:
            return
        pos = proj.node.getPos(self.render)
        owner_pos = proj.owner.root.getPos(self.render) + Vec3(0.0, 0.0, 6.0)
        direction = vec_normalized(owner_pos - pos)
        if direction.lengthSquared() <= 1e-6:
            direction = vec_normalized(self.camera.getQuat(self.render).getForward())
        proj.velocity = direction * (proj.owner.spec.throw_speed * 1.30) + Vec3(0.0, 0.0, 4.0)
        proj.spin = Vec3(-proj.spin.x * 0.8, proj.spin.y * 0.8, -proj.spin.z * 0.9)
        proj.life = max(proj.life, 2.8)
        proj.ignore_hit_time = 0.26
        proj.deflected = True
        proj.gravity *= 0.45
        if proj.piece.wire is not None and not proj.piece.wire.isEmpty():
            r, g, b = self.wire_flash_rgb(Vec3(0.24, 1.0, 1.0))
            proj.piece.wire.setColorScale(r, g, b, 0.58)
        self._consume_shield_charge()

    def _find_weapon_projectile_hit(self, start_pos: Vec3, end_pos: Vec3):
        best = None
        best_distance = 1e9

        for titan in getattr(self, "titans", []):
            if titan.state == "dormant":
                continue
            for piece in titan.pieces:
                if piece.destroyed or piece.node.isEmpty():
                    continue
                piece_pos = piece.node.getPos(self.render)
                radius = max(0.85, piece.node.getScale(self.render).length() * 0.30)
                dist = point_segment_distance(piece_pos, start_pos, end_pos)
                if dist <= radius and dist < best_distance:
                    best_distance = dist
                    best = ("titan", titan, piece, piece_pos, radius)

        for chunk in self.chunks.values():
            for piece in chunk.pieces:
                if piece.destroyed or piece.node.isEmpty():
                    continue
                piece_pos = piece.node.getPos(self.render)
                radius = max(0.70, piece.node.getScale(self.render).length() * 0.28)
                dist = point_segment_distance(piece_pos, start_pos, end_pos)
                if dist <= radius and dist < best_distance:
                    best_distance = dist
                    best = ("chunk", chunk, piece, piece_pos, radius)

        return best

    def destroy_chunk_piece(self, chunk, piece: Piece, impact_pos: Vec3, impact_velocity: Vec3):
        if piece.destroyed:
            return
        piece.destroyed = True
        self.queue_shrink_deletion(piece.node, piece.wire, duration=0.16)
        self.spawn_hyper_wire_explosion(
            impact_pos,
            scale=max(0.22, piece.base_scale.length() * 0.10),
            base_rgb=piece.wire_rgb,
        )
        self.red_flash_strength = max(self.red_flash_strength, 0.14)

    def defeat_titan(self, titan, impact_pos: Vec3):
        if titan.state == "defeated":
            return
        titan.state = "defeated"
        titan.state_time = 0.0
        titan.attack_timer = 0.0
        titan.throw_queue = []
        titan.escape_called = False
        for proj in list(titan.projectiles):
            piece = proj.piece
            piece.active_projectile = None
            piece.destroyed = True
            if proj.node is not None and not proj.node.isEmpty():
                proj.node.removeNode()
        titan.projectiles.clear()
        self.spawn_hyper_wire_explosion(impact_pos, scale=4.6, base_rgb=Vec3(titan.spec.accent.x * 1.15, titan.spec.accent.y * 1.15, titan.spec.accent.z * 1.15))
        self.red_flash_strength = max(self.red_flash_strength, 0.42)

    def destroy_titan_piece(self, titan, piece: TitanPiece, impact_pos: Vec3, impact_velocity: Vec3):
        if piece.destroyed:
            return
        piece.destroyed = True
        piece.thrown = False
        if piece.active_projectile is not None and piece.active_projectile in titan.projectiles:
            titan.projectiles.remove(piece.active_projectile)
        piece.active_projectile = None
        self.queue_shrink_deletion(piece.node, piece.wire, duration=0.18)

        titan.current_integrity = max(0.0, titan.current_integrity - self.titan_piece_weight_value(piece.group))
        self.spawn_hyper_wire_explosion(
            impact_pos,
            scale=max(0.26, piece.target_scale.length() * 0.12 * titan.root.getScale().x),
            base_rgb=piece.wire_rgb,
        )
        self.red_flash_strength = max(self.red_flash_strength, 0.18)

        integrity_fraction = titan.current_integrity / max(1e-6, titan.max_integrity)
        core_total = sum(1 for p in titan.pieces if p.group in ("head", "torso", "shoulders"))
        core_destroyed = sum(1 for p in titan.pieces if p.destroyed and p.group in ("head", "torso", "shoulders"))
        if integrity_fraction <= 0.54 or core_destroyed >= max(3, int(core_total * 0.50)):
            self.defeat_titan(titan, impact_pos)

    def _make_lightning_texture(self, width, height):
        img = PNMImage(width, height, 4)
        img.fill(0.0, 0.0, 0.0)
        img.alphaFill(0.0)
        rng = random.Random(99881)

        def stamp(px, py, alpha):
            if 0 <= px < width and 0 <= py < height:
                existing = img.getAlpha(px, py)
                if alpha > existing:
                    glow = clamp(alpha, 0.0, 1.0)
                    img.setXelA(px, py, 1.0, 1.0, 1.0, glow)

        for _ in range(4):
            x = rng.randint(int(width * 0.25), int(width * 0.75))
            y = 0
            while y < height - 1:
                nx = int(clamp(x + rng.randint(-12, 12), 3, width - 4))
                ny = min(height - 1, y + rng.randint(10, 30))
                steps = max(1, int(math.hypot(nx - x, ny - y)) * 2)
                for s in range(steps + 1):
                    px = int(x + (nx - x) * (s / steps))
                    py = int(y + (ny - y) * (s / steps))
                    for ox in range(-2, 3):
                        for oy in range(-2, 3):
                            falloff = max(abs(ox), abs(oy))
                            alpha = 1.0 if falloff == 0 else 0.55 if falloff == 1 else 0.18
                            stamp(px + ox, py + oy, alpha)
                    if rng.random() < 0.06 and py < height - 24:
                        bx = int(clamp(px + rng.randint(-18, 18), 2, width - 3))
                        by = min(height - 1, py + rng.randint(8, 28))
                        branch_steps = max(1, int(math.hypot(bx - px, by - py)) * 2)
                        for sb in range(branch_steps + 1):
                            bpx = int(px + (bx - px) * (sb / branch_steps))
                            bpy = int(py + (by - py) * (sb / branch_steps))
                            for ox in range(-1, 2):
                                for oy in range(-1, 2):
                                    falloff = max(abs(ox), abs(oy))
                                    alpha = 0.68 if falloff == 0 else 0.22
                                    stamp(bpx + ox, bpy + oy, alpha)
                x, y = nx, ny

        tex = Texture("red_lightning")
        tex.load(img)
        tex.setWrapU(Texture.WM_clamp)
        tex.setWrapV(Texture.WM_clamp)
        tex.setMinfilter(Texture.FT_linear)
        tex.setMagfilter(Texture.FT_linear)
        return tex

    def _make_glitch_texture(self, name, size, bg, c1, c2, lines):
        img = PNMImage(size, size, 4)
        for y in range(size):
            for x in range(size):
                scan = 0.025 if y % 2 == 0 else 0.0
                img.setXelA(x, y, bg[0] + scan, bg[1] + scan, bg[2] + scan, 1.0)

        rng = random.Random(hash(name) & 0xFFFFFFFF)
        for _ in range(size * 5):
            x0 = rng.randrange(0, size)
            y0 = rng.randrange(0, size)
            w = rng.randrange(2, max(3, size // 6))
            h = rng.randrange(1, max(2, size // 10))
            col = c1 if rng.random() < 0.55 else c2
            alpha = rng.uniform(0.60, 1.0)
            for yy in range(y0, min(size, y0 + h)):
                for xx in range(x0, min(size, x0 + w)):
                    stripe = 0.12 if yy % 3 == 0 else 0.0
                    img.setXelA(
                        xx,
                        yy,
                        clamp(col[0] + stripe, 0.0, 1.0),
                        clamp(col[1] + stripe * 0.5, 0.0, 1.0),
                        clamp(col[2] + stripe, 0.0, 1.0),
                        alpha,
                    )

        for _ in range(size // 4):
            x = rng.randrange(0, size)
            for y in range(size):
                if rng.random() < 0.82:
                    img.setXelA(x, y, lines[0], lines[1], lines[2], rng.uniform(0.25, 0.75))

        tex = Texture(name)
        tex.load(img)
        tex.setWrapU(Texture.WM_repeat)
        tex.setWrapV(Texture.WM_repeat)
        tex.setMinfilter(Texture.FT_nearest_mipmap_nearest)
        tex.setMagfilter(Texture.FT_nearest)
        tex.setAnisotropicDegree(2)
        return tex

    def _make_overlay_texture(self, size):
        img = PNMImage(size, size, 4)
        rng = random.Random(424242)
        for y in range(size):
            for x in range(size):
                base_alpha = 0.015 if y % 2 == 0 else 0.0
                noise = 0.04 if rng.random() < 0.018 else 0.0
                img.setXelA(x, y, 1.0, 1.0, 1.0, clamp(base_alpha + noise, 0.0, 0.18))
        tex = Texture("overlay")
        tex.load(img)
        tex.setWrapU(Texture.WM_repeat)
        tex.setWrapV(Texture.WM_repeat)
        tex.setMinfilter(Texture.FT_nearest)
        tex.setMagfilter(Texture.FT_nearest)
        return tex

    def _spawn_comet(self, comet: Comet, chunk_center):
        chunk_world_center = Vec3(chunk_center[0] * self.CHUNK_SIZE, chunk_center[1] * self.CHUNK_SIZE, 0.0)
        comet.head.setPos(
            chunk_world_center.x + random.uniform(-180.0, 180.0),
            chunk_world_center.y + random.uniform(60.0, 220.0),
            random.uniform(90.0, 190.0),
        )
        comet.trail.setPos(comet.head.getPos() + Vec3(0.0, 8.0, 4.0))

    def _spawn_comets(self):
        self.comets.clear()
        rng = random.Random(4441)
        for _ in range(16):
            head = self.box_model.copyTo(self.comet_root)
            head.setTexture(self.accent_tex, 1)
            head.setTransparency(TransparencyAttrib.MAlpha)
            head.setLightOff(1)
            head.setColorScale(0.55, 0.88, 1.0, 0.78)
            head.setScale(rng.uniform(0.16, 0.42), rng.uniform(0.16, 0.42), rng.uniform(0.8, 2.0))

            trail = self.box_model.copyTo(self.comet_root)
            trail.setTexture(self.accent_tex, 1)
            trail.setLightOff(1)
            trail.setTransparency(TransparencyAttrib.MAlpha)
            trail.setColorScale(0.20, 0.62, 1.0, 0.16)
            trail.setScale(rng.uniform(0.10, 0.18), rng.uniform(0.10, 0.18), rng.uniform(8.0, 18.0))

            comet = Comet(
                head=head,
                trail=trail,
                velocity=Vec3(rng.uniform(-5.0, 5.0), -rng.uniform(24.0, 46.0), -rng.uniform(8.0, 18.0)),
                min_alpha=rng.uniform(0.08, 0.20),
                max_alpha=rng.uniform(0.40, 0.85),
                phase=rng.uniform(0.0, math.tau),
            )
            self.comets.append(comet)
            self._spawn_comet(comet, (0, 0))

    def _rebuild_city_shell(self, chunk_center):
        self.city_root.getChildren().detach()
        self.city_anchor_chunk = chunk_center
        rng = random.Random((chunk_center[0] * 977) ^ (chunk_center[1] * 1597) ^ 0x7A11)
        center_x = chunk_center[0] * self.CHUNK_SIZE
        center_y = chunk_center[1] * self.CHUNK_SIZE
        inner_radius = self.CHUNK_SIZE * 2.8
        outer_radius = self.CHUNK_SIZE * 5.2
        tower_count = 42

        for i in range(tower_count):
            angle = (i / tower_count) * math.tau + rng.uniform(-0.12, 0.12)
            radius = rng.uniform(inner_radius, outer_radius)
            x = center_x + math.cos(angle) * radius
            y = center_y + math.sin(angle) * radius
            width = rng.uniform(2.6, 8.5)
            depth = rng.uniform(2.4, 8.0)
            height = rng.uniform(16.0, 76.0) * (1.45 if rng.random() < 0.25 else 1.0)

            tower = self.box_model.copyTo(self.city_root)
            tower.setPos(x, y, height * 0.5 - 2.0)
            tower.setScale(width, depth, height)
            tower.setTexture(self.wall_tex if rng.random() < 0.72 else self.accent_tex, 1)
            tower.setTransparency(TransparencyAttrib.MAlpha)
            tower.setColorScale(
                rng.uniform(0.06, 0.18),
                rng.uniform(0.12, 0.40),
                rng.uniform(0.24, 0.70),
                rng.uniform(0.22, 0.42),
            )
            mat = Material()
            mat.setShininess(8.0)
            mat.setAmbient((0.22, 0.22, 0.25, 1.0))
            mat.setDiffuse((1.0, 1.0, 1.0, 1.0))
            mat.setEmission((0.02, 0.03, 0.05, 1.0))
            tower.setMaterial(mat, 1)

            wire = self.box_model.copyTo(tower)
            wire.setScale(1.012)
            wire.setRenderModeWireframe()
            wire.setLightOff(1)
            wire.setTextureOff(1)
            wire.setTransparency(TransparencyAttrib.MAlpha)
            wire_alpha = rng.uniform(0.16, 0.34)
            wire.setColorScale(0.30, 0.88, 1.0, wire_alpha)
            wire.setTag("role", "wire")
            wire.setPythonTag("base_rgb", (0.30, 0.88, 1.0))
            wire.setPythonTag("base_alpha", wire_alpha)

            strip_count = rng.randint(2, 5)
            for _ in range(strip_count):
                strip = self.box_model.copyTo(tower)
                strip.setTexture(self.accent_tex, 1)
                strip.setLightOff(1)
                strip.setTransparency(TransparencyAttrib.MAlpha)
                strip.setColorScale(
                    rng.uniform(0.08, 0.25),
                    rng.uniform(0.55, 1.0),
                    rng.uniform(0.75, 1.0),
                    rng.uniform(0.10, 0.25),
                )
                strip.setPos(
                    rng.choice((-0.92, 0.92)) * width,
                    rng.uniform(-0.82, 0.82) * depth,
                    rng.uniform(-0.75, 0.82) * height,
                )
                strip.setScale(rng.uniform(0.08, 0.16), rng.uniform(0.18, 0.32), rng.uniform(0.2, 0.9) * height)

    def chunk_seed(self, coord):
        x, y = coord
        return ((x * 73856093) ^ (y * 19349663) ^ 0x5EEDBEEF) & 0xFFFFFFFF

    def ensure_chunks(self, center):
        needed = set()
        for dx in range(-self.ACTIVE_RADIUS, self.ACTIVE_RADIUS + 1):
            for dy in range(-self.ACTIVE_RADIUS, self.ACTIVE_RADIUS + 1):
                needed.add((center[0] + dx, center[1] + dy))

        for coord in needed:
            if coord not in self.chunks:
                self.chunks[coord] = Chunk(self, coord, self.chunk_seed(coord))

        for coord, chunk in list(self.chunks.items()):
            if coord not in needed:
                chunk.begin_collapse()

    def current_chunk(self):
        pos = self.player.getPos()
        return (math.floor(pos.x / self.CHUNK_SIZE), math.floor(pos.y / self.CHUNK_SIZE))

    def handle_mouse_look(self, dt):
        if not self.mouse_locked or not self.win:
            return
        if self.win.getXSize() <= 1 or self.win.getYSize() <= 1:
            return
        if not hasattr(self.win, "getPointer"):
            return
        pointer = self.win.getPointer(0)
        dx = pointer.getX() - self.center_x
        dy = pointer.getY() - self.center_y
        if dx == 0 and dy == 0:
            return
        sensitivity = 0.14
        self.yaw -= dx * sensitivity
        self.pitch = clamp(self.pitch - dy * sensitivity, -86.0, 86.0)
        self.player.setH(self.yaw)
        self.pitch_node.setP(self.pitch)
        if hasattr(self.win, "movePointer"):
            self.win.movePointer(0, self.center_x, self.center_y)

    def move_player(self, dt):
        start_pos = Vec3(self.player.getPos())
        move = Vec3(0, 0, 0)
        if self.keys["w"]:
            move.y += 1.0
        if self.keys["s"]:
            move.y -= 1.0
        if self.keys["a"]:
            move.x -= 1.0
        if self.keys["d"]:
            move.x += 1.0

        speed = 14.0 * (1.8 if self.keys["shift"] else 1.0)
        drift_speed = 7.0
        vertical = 0.0
        if self.keys["q"]:
            vertical += 1.0
        if self.keys["e"]:
            vertical -= 1.0

        if move.lengthSquared() > 0.0:
            move = vec_normalized(move)
            quat = self.player.getQuat(self.render)
            forward = quat.getForward()
            right = quat.getRight()
            forward.z = 0.0
            right.z = 0.0
            forward = vec_normalized(forward)
            right = vec_normalized(right)
            world_move = right * move.x + forward * move.y
            self.player.setPos(self.player.getPos() + world_move * speed * dt)
            self.last_speed = speed
            self.walk_cycle += dt * (8.5 if self.keys["shift"] else 6.0)
        else:
            self.last_speed = 0.0
            self.walk_cycle += dt * 1.5

        if vertical != 0.0:
            self.player.setZ(self.player.getZ() + vertical * drift_speed * dt)
        else:
            hover_target = 2.05
            self.player.setZ(self.player.getZ() + (hover_target - self.player.getZ()) * min(1.0, dt * 4.0))

        if self.player_knockback.lengthSquared() > 0.001:
            self.player.setPos(self.player.getPos() + self.player_knockback * dt)
            self.player_knockback *= max(0.0, 1.0 - dt * 3.6)

        bob = math.sin(self.walk_cycle) * 0.04 * min(1.0, self.last_speed / 14.0)
        sway = math.cos(self.walk_cycle * 0.5) * 0.02 * min(1.0, self.last_speed / 18.0)
        self.camera.setPos(sway, 0, bob)
        self.player_velocity = (self.player.getPos() - start_pos) / max(dt, 1e-5)

    def update_overlay(self, clock):
        offset_u = (clock * 0.017) % 1.0
        offset_v = (clock * 0.12) % 1.0
        scale_y = 3.0 + math.sin(clock * 0.33) * 0.08
        self.overlay.setTexOffset(TextureStage.getDefault(), offset_u, offset_v)
        self.overlay.setTexScale(TextureStage.getDefault(), 1.0, scale_y)
        alpha = 0.10 + 0.03 * math.sin(clock * 0.6) + 0.025 * (0.5 + 0.5 * math.sin(clock * 7.5))
        flash = self.red_flash_strength
        self.overlay.setColor(
            1.0 + flash * 0.10,
            1.0 - flash * 0.22,
            1.0 - flash * 0.24,
            clamp(alpha + flash * 0.05, 0.07, 0.24),
        )

    def update_sky_fragments(self, clock):
        for i, child in enumerate(self.sky_fragments.getChildren()):
            seed = i * 0.37
            p = child.getPos()
            child.setPos(p.x, p.y, p.z + math.sin(clock * (0.3 + seed * 0.02) + seed) * 0.02)
            child.setH(child.getH() + 0.05 + (i % 7) * 0.005)
            child.setP(child.getP() + 0.03)
            child.setR(child.getR() + 0.04)

    def update_city_shell(self, chunk_center, clock):
        if self.city_anchor_chunk != chunk_center:
            self._rebuild_city_shell(chunk_center)
        for i, node in enumerate(self.city_root.getChildren()):
            if i % 6 == 0:
                pulse = 0.13 + 0.07 * math.sin(clock * 1.2 + i * 0.7)
                cs = node.getColorScale()
                node.setColorScale(cs.x, cs.y, cs.z, clamp(max(pulse, cs.w), 0.08, 0.35))
            for child in node.getChildren():
                if child.getTag("role") == "wire":
                    base_rgb = child.getPythonTag("base_rgb") or (0.30, 0.88, 1.0)
                    base_alpha = child.getPythonTag("base_alpha") or 0.22
                    r, g, b = self.wire_flash_rgb(Vec3(*base_rgb))
                    child.setColorScale(r, g, b, clamp(base_alpha + self.red_flash_strength * 0.22, 0.10, 0.64))

    def update_comets(self, dt, clock, chunk_center):
        chunk_world_center = Vec3(chunk_center[0] * self.CHUNK_SIZE, chunk_center[1] * self.CHUNK_SIZE, 0.0)
        for i, comet in enumerate(self.comets):
            drift = Vec3(math.sin(clock * 0.6 + comet.phase) * 1.6, 0.0, math.cos(clock * 0.8 + comet.phase) * 0.55)
            vel = comet.velocity + drift
            pos = comet.head.getPos() + vel * dt
            comet.head.setPos(pos)
            trail_dir = vec_normalized(vel) if vel.lengthSquared() > 0.01 else Vec3(0, -1, 0)
            comet.trail.setPos(pos - trail_dir * (5.0 + (i % 5) * 1.6))
            comet.trail.lookAt(comet.head)
            comet.trail.setP(comet.trail.getP() + 90.0)
            alpha = clamp(comet.min_alpha + 0.05 * math.sin(clock * 7.0 + comet.phase), 0.06, comet.max_alpha)
            comet.trail.setAlphaScale(alpha)
            comet.head.setAlphaScale(clamp(alpha + 0.20, 0.18, 0.92))

            too_low = pos.z < 12.0
            too_far = (Vec3(pos.x, pos.y, 0.0) - chunk_world_center).length() > 260.0
            if too_low or too_far:
                self._spawn_comet(comet, chunk_center)

    def update_titans(self, dt):
        player_pos = self.player.getPos(self.render)
        if not self.titans:
            return

        current = self.titans[self.active_titan_index]
        if current.is_escaped_from(player_pos) and not current.escape_called:
            current.escape_called = True
            nearest_idx = None
            nearest_dist = 1e9
            for idx, titan in enumerate(self.titans):
                if idx == self.active_titan_index:
                    continue
                if titan.state == "dormant":
                    dist = (titan.home - player_pos).length()
                    if dist < nearest_dist:
                        nearest_idx = idx
                        nearest_dist = dist
            if nearest_idx is not None:
                self.titans[nearest_idx].activate()

        for idx, titan in enumerate(self.titans):
            dist = (titan.home - player_pos).length()
            if titan.state == "dormant" and dist < titan.activation_radius:
                titan.activate()
            titan.update(dt, self.time_accum, player_pos, self.player_velocity)

        active_distances = [(idx, (titan.root.getPos(self.render) - player_pos).length()) for idx, titan in enumerate(self.titans) if titan.is_active()]
        if active_distances:
            active_distances.sort(key=lambda item: item[1])
            self.active_titan_index = active_distances[0][0]

    def update(self, task):
        dt = min(globalClock.getDt(), 0.033)
        self.time_accum += dt

        if self.win and (self.win.getXSize() // 2 != self.center_x or self.win.getYSize() // 2 != self.center_y):
            self._refresh_center()

        self.handle_mouse_look(dt)
        self.move_player(dt)
        center = self.current_chunk()
        self.ensure_chunks(center)

        for coord, chunk in list(self.chunks.items()):
            chunk.update(dt, self.time_accum, center)
            if chunk.dead:
                del self.chunks[coord]

        self.update_red_storm(dt, self.time_accum, center)
        self.update_overlay(self.time_accum)
        self.update_sky_fragments(self.time_accum)
        self.update_city_shell(center, self.time_accum)
        self.update_comets(dt, self.time_accum, center)
        self.update_weapon_viewmodels(dt, self.time_accum)
        self.update_shield(dt, self.time_accum)
        self.update_shrink_deletions(dt, self.time_accum)
        self.update_hyper_explosions(dt, self.time_accum)
        self.update_titans(dt)

        if self.audio3d:
            try:
                self.audio3d.update()
            except Exception:
                pass

        return Task.cont


def get_level_settings():
    return {
        "name": LEVEL_NAME,
        "module_name": "level7",
        "entry_function": "run_app",
        "dedicated_hub_door_index": DEDICATED_HUB_DOOR_INDEX,
        "door_label": "Press E to Open",
        "door_subtitle": "Level 7",
    }


def run_app():
    app = FracturedWorld()
    if os.environ.get("P3D_SMOKE_TEST", "0") == "1":
        for _ in range(18):
            app.taskMgr.step()
        print("smoke test ok")
        app.destroy()
        return
    app.run()


if __name__ == "__main__":
    run_app()
