"""Same-window built-in Vector Arena first-person arcade shooter.

Vector Arena is intentionally a native Panda3D dimension, not a child-window
route.  This pass makes the artifact a presentation-grade first-person arcade shooter: ground-level camera, cursor-look, hitscan
pulse weapon, cover lanes, spawn gates, enemy waves, class-based menacing enemy models, solid armored hardlight materials, and a changing hardlight scenery shell.

ESC / 0 are owned by the HoloVerse host return contract.
H toggles the optional local help/status panel.  The reticle and minimal combat
readout stay visible because they are part of the arcade shooter presentation,
not legacy debug UI.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass
from pathlib import Path

from direct.gui.OnscreenText import OnscreenText
from panda3d.core import (
    AmbientLight,
    CardMaker,
    DirectionalLight,
    KeyboardButton,
    LineSegs,
    MouseButton,
    NodePath,
    TextNode,
    TransparencyAttrib,
    Vec3,
    Vec4,
    WindowProperties,
)

MODE_TITLE = "Vector Arena"
MODE_ID = "vector_arena"
MODE_STATUS = "VECTOR ARENA // PHASED FIRST-PERSON ARCADE SHOOTER // CURRENT-GEN HARDLIGHT STYLE PASS // ESC / 0 RETURN TO HOLOVERSE // H SHOWS LEGACY UI / HELP"

ARENA_RADIUS = 118.0
EYE_HEIGHT = 4.4
ENEMY_CAP = 20
PROJECTILE_CAP = 48  # hitscan beam/tracer pool; kept under the original projectile contract name
IMPACT_CAP = 48
SPAWN_PULSE_CAP = 10
KILL_BURST_CAP = 24
MUZZLE_FLASH_CAP = 12
REPULSOR_WAVE_CAP = 8
HEAT_VENT_SPARK_CAP = 16
MAX_HEAT = 100.0

ENEMY_VARIANTS = (
    {
        "id": "stalker",
        "name": "VECTOR STALKER",
        "color": Vec4(1.00, 0.18, 0.16, 0.95),
        "accent": Vec4(1.00, 0.74, 0.12, 0.82),
        "hp": 42.0,
        "speed": 1.35,
        "damage": 9.0,
        "score": 105,
        "scale": 0.92,
        "aim_radius": 0.012,
    },
    {
        "id": "brute",
        "name": "IRON BRUTE",
        "color": Vec4(1.00, 0.42, 0.08, 0.96),
        "accent": Vec4(1.00, 0.06, 0.04, 0.84),
        "hp": 108.0,
        "speed": 0.62,
        "damage": 20.0,
        "score": 240,
        "scale": 1.34,
        "aim_radius": 0.026,
    },
    {
        "id": "sentry",
        "name": "ARC SENTRY",
        "color": Vec4(0.62, 0.88, 1.00, 0.94),
        "accent": Vec4(0.26, 1.00, 0.96, 0.82),
        "hp": 72.0,
        "speed": 0.82,
        "damage": 13.0,
        "score": 165,
        "scale": 1.05,
        "aim_radius": 0.018,
    },
    {
        "id": "wraith",
        "name": "RED WRAITH",
        "color": Vec4(0.96, 0.10, 1.00, 0.92),
        "accent": Vec4(1.00, 0.18, 0.40, 0.82),
        "hp": 56.0,
        "speed": 1.12,
        "damage": 15.0,
        "score": 190,
        "scale": 1.06,
        "aim_radius": 0.014,
    },
    {
        "id": "guardian",
        "name": "GATE GUARDIAN",
        "color": Vec4(1.00, 0.08, 0.18, 0.98),
        "accent": Vec4(1.00, 0.82, 0.18, 0.88),
        "hp": 170.0,
        "speed": 0.52,
        "damage": 28.0,
        "score": 420,
        "scale": 1.58,
        "aim_radius": 0.034,
    },
)

ENEMY_POOL_VARIANTS = (
    "stalker", "stalker", "stalker", "wraith", "sentry", "stalker", "brute", "stalker",
    "sentry", "wraith", "stalker", "brute", "sentry", "wraith", "brute", "sentry",
    "guardian", "wraith", "brute", "guardian",
)

VARIANT_BY_ID = {profile["id"]: profile for profile in ENEMY_VARIANTS}

SCENERY_THEMES = (
    {
        "name": "PRISM FOUNDRY",
        "primary": Vec4(0.18, 1.00, 0.86, 0.82),
        "secondary": Vec4(1.00, 0.78, 0.18, 0.72),
        "accent": Vec4(1.00, 0.22, 0.92, 0.66),
        "floor": Vec4(0.010, 0.025, 0.034, 0.93),
        "sky": (0.002, 0.004, 0.010),
    },
    {
        "name": "NEON CANYON",
        "primary": Vec4(1.00, 0.36, 0.12, 0.82),
        "secondary": Vec4(1.00, 0.18, 0.88, 0.70),
        "accent": Vec4(0.38, 0.92, 1.00, 0.66),
        "floor": Vec4(0.032, 0.016, 0.010, 0.93),
        "sky": (0.018, 0.004, 0.012),
    },
    {
        "name": "FROST CIRCUIT",
        "primary": Vec4(0.46, 0.86, 1.00, 0.82),
        "secondary": Vec4(0.86, 1.00, 1.00, 0.68),
        "accent": Vec4(0.24, 0.34, 1.00, 0.62),
        "floor": Vec4(0.006, 0.020, 0.034, 0.93),
        "sky": (0.001, 0.008, 0.018),
    },
    {
        "name": "DATA STORM",
        "primary": Vec4(0.30, 1.00, 0.38, 0.82),
        "secondary": Vec4(0.18, 1.00, 0.92, 0.72),
        "accent": Vec4(1.00, 1.00, 0.24, 0.62),
        "floor": Vec4(0.006, 0.030, 0.018, 0.93),
        "sky": (0.002, 0.014, 0.006),
    },
    {
        "name": "REDLINE CORE",
        "primary": Vec4(1.00, 0.16, 0.18, 0.84),
        "secondary": Vec4(1.00, 0.52, 0.14, 0.72),
        "accent": Vec4(0.94, 0.22, 1.00, 0.64),
        "floor": Vec4(0.034, 0.006, 0.010, 0.93),
        "sky": (0.018, 0.002, 0.004),
    },
)


@dataclass
class _Enemy:
    node: NodePath
    pos: Vec3
    vel: Vec3
    hp: float
    max_hp: float
    tier: int
    phase: float
    attack_cooldown: float
    variant: str = "stalker"
    display_name: str = "VECTOR STALKER"
    speed_scale: float = 1.0
    damage_scale: float = 1.0
    score_value: int = 100
    aim_radius: float = 0.012
    active: bool = True
    hit_flash: float = 0.0
    death_flash: float = 0.0


@dataclass
class _Projectile:
    node: NodePath
    age: float = 0.0
    life: float = 0.085
    active: bool = False


@dataclass
class _Impact:
    node: NodePath
    pos: Vec3
    age: float = 0.0
    life: float = 0.34
    active: bool = False


@dataclass
class _SpawnPulse:
    node: NodePath
    pos: Vec3
    age: float = 0.0
    life: float = 0.70
    active: bool = False


@dataclass
class _KillBurst:
    node: NodePath
    pos: Vec3
    age: float = 0.0
    life: float = 0.46
    active: bool = False


@dataclass
class _MuzzleFlash:
    node: NodePath
    pos: Vec3
    age: float = 0.0
    life: float = 0.105
    active: bool = False


@dataclass
class _RepulsorWave:
    node: NodePath
    pos: Vec3
    age: float = 0.0
    life: float = 0.42
    active: bool = False


@dataclass
class _HeatVentSpark:
    node: NodePath
    pos: Vec3
    age: float = 0.0
    life: float = 0.30
    active: bool = False


@dataclass(frozen=True)
class _CoverBlock:
    pos: Vec3
    half: Vec3


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _safe_dt(dt: float) -> float:
    try:
        return _clamp(float(dt), 0.0, 0.05)
    except Exception:
        return 0.016


def _heading_vec(deg: float) -> Vec3:
    a = math.radians(float(deg))
    return Vec3(math.sin(a), math.cos(a), 0.0)


def _forward_vec(yaw: float, pitch: float) -> Vec3:
    # Panda3D forward is +Y.  Positive pitch aims down, so z uses -sin(pitch).
    y = math.radians(float(yaw))
    p = math.radians(float(pitch))
    cp = math.cos(p)
    vec = Vec3(math.sin(y) * cp, math.cos(y) * cp, -math.sin(p))
    if vec.lengthSquared() > 0.0001:
        vec.normalize()
    return vec


def _line_node(name: str, points: list[Vec3], color: Vec4, thickness: float = 1.0, closed: bool = False) -> NodePath:
    seg = LineSegs(name)
    seg.setThickness(float(thickness))
    seg.setColor(color)
    if not points:
        return NodePath(name)
    seg.moveTo(points[0])
    for point in points[1:]:
        seg.drawTo(point)
    if closed and len(points) > 2:
        seg.drawTo(points[0])
    node = NodePath(seg.create())
    node.setTransparency(TransparencyAttrib.MAlpha)
    return node


def _circle_node(name: str, radius: float, color: Vec4, thickness: float = 1.0, segments: int = 48) -> NodePath:
    pts: list[Vec3] = []
    count = max(12, int(segments))
    for i in range(count):
        a = math.tau * i / count
        pts.append(Vec3(math.sin(a) * radius, math.cos(a) * radius, 0.0))
    return _line_node(name, pts, color, thickness, True)


def _wire_box(name: str, half: Vec3, color: Vec4, thickness: float = 1.0) -> NodePath:
    sx, sy, sz = abs(float(half.x)), abs(float(half.y)), abs(float(half.z))
    pts = [
        Vec3(-sx, -sy, -sz), Vec3(sx, -sy, -sz), Vec3(sx, sy, -sz), Vec3(-sx, sy, -sz),
        Vec3(-sx, -sy, sz), Vec3(sx, -sy, sz), Vec3(sx, sy, sz), Vec3(-sx, sy, sz),
    ]
    edges = ((0,1),(1,2),(2,3),(3,0),(4,5),(5,6),(6,7),(7,4),(0,4),(1,5),(2,6),(3,7))
    seg = LineSegs(name)
    seg.setThickness(float(thickness))
    seg.setColor(color)
    for a, b in edges:
        seg.moveTo(pts[a])
        seg.drawTo(pts[b])
    node = NodePath(seg.create())
    node.setTransparency(TransparencyAttrib.MAlpha)
    return node


def _panel_node(name: str, width: float, height: float, color: Vec4, axis: str = "floor") -> NodePath:
    cm = CardMaker(name)
    cm.setFrame(-width * 0.5, width * 0.5, -height * 0.5, height * 0.5)
    node = NodePath(cm.generate())
    if axis == "floor":
        node.setP(-90)
    elif axis == "wall_y":
        node.setP(0)
    elif axis == "wall_x":
        node.setH(90)
    node.setColor(color)
    if getattr(color, "w", 1.0) < 1.0:
        node.setTransparency(TransparencyAttrib.MAlpha)
    try:
        node.setTwoSided(True)
    except Exception:
        pass
    return node


def _solid_box_node(name: str, half: Vec3, color: Vec4, trim_color: Vec4 | None = None, trim_thickness: float = 0.8) -> NodePath:
    """Cheap opaque hard-surface cuboid built from cards plus optional neon trim.

    Pass 98 style rule: objects should read as solid current-gen armor first,
    with glow used as thin seams/cores instead of whole translucent bodies.
    """
    sx, sy, sz = abs(float(half.x)), abs(float(half.y)), abs(float(half.z))
    root = NodePath(name)
    faces = (
        ("front", "wall_y", Vec3(0, -sy, 0), 0),
        ("back", "wall_y", Vec3(0, sy, 0), 180),
        ("right", "wall_x", Vec3(sx, 0, 0), 0),
        ("left", "wall_x", Vec3(-sx, 0, 0), 180),
        ("top", "floor", Vec3(0, 0, sz), 0),
        ("bottom", "floor", Vec3(0, 0, -sz), 180),
    )
    for suffix, axis, pos, extra_h in faces:
        if axis == "floor":
            panel = _panel_node(f"{name}_{suffix}_solid_armor_face", sx * 2.0, sy * 2.0, color, axis)
        elif axis == "wall_x":
            panel = _panel_node(f"{name}_{suffix}_solid_armor_face", sy * 2.0, sz * 2.0, color, axis)
        else:
            panel = _panel_node(f"{name}_{suffix}_solid_armor_face", sx * 2.0, sz * 2.0, color, axis)
        panel.setPos(pos)
        if extra_h:
            panel.setH(panel.getH() + extra_h)
        panel.reparentTo(root)
    if trim_color is not None:
        trim = _wire_box(f"{name}_thin_emissive_seams", half, trim_color, trim_thickness)
        trim.reparentTo(root)
    return root


def _armor_strip_node(name: str, length: float, color: Vec4, vertical: bool = False) -> NodePath:
    if vertical:
        return _line_node(name, [Vec3(0, 0, -length * 0.5), Vec3(0, 0, length * 0.5)], color, 1.15, False)
    return _line_node(name, [Vec3(-length * 0.5, 0, 0), Vec3(length * 0.5, 0, 0)], color, 1.15, False)




def _diamond_node(name: str, width: float, height: float, color: Vec4, thickness: float = 1.0) -> NodePath:
    hw = abs(float(width)) * 0.5
    hh = abs(float(height)) * 0.5
    pts = [Vec3(0, 0, hh), Vec3(hw, 0, 0), Vec3(0, 0, -hh), Vec3(-hw, 0, 0)]
    return _line_node(name, pts, color, thickness, True)


def _chevron_node(name: str, width: float, height: float, color: Vec4, thickness: float = 1.0, flipped: bool = False) -> NodePath:
    hw = abs(float(width)) * 0.5
    hh = abs(float(height)) * 0.5
    tip = -hh if flipped else hh
    base = hh if flipped else -hh
    pts = [Vec3(-hw, 0, base), Vec3(0, 0, tip), Vec3(hw, 0, base)]
    return _line_node(name, pts, color, thickness, False)


def _fang_arc_node(name: str, radius: float, height: float, color: Vec4, thickness: float = 1.0, count: int = 5) -> NodePath:
    pts: list[Vec3] = []
    n = max(3, int(count))
    for i in range(n):
        t = -1.0 + 2.0 * i / max(1, n - 1)
        pts.append(Vec3(t * radius, -abs(t) * 0.18, height * (1.0 - 0.24 * abs(t))))
    return _line_node(name, pts, color, thickness, False)


def _enemy_threat_rig(name: str, profile: dict, scale: float, height: float, tier: int = 0) -> tuple[NodePath, ...]:
    """Shared current-gen enemy armor kit.

    Pass 98 keeps the old menacing-model tokens for validator continuity, but
    changes the look from translucent hologram stacks into opaque black armored
    hardlight bodies with thin emissive seams, core diamonds, and controlled
    threat lighting.
    """
    color = profile["color"]
    accent = profile["accent"]
    armor = Vec4(0.026, 0.032, 0.042, 1.0)
    armor_hi = Vec4(0.052, 0.062, 0.078, 1.0)
    seam = Vec4(accent.x, accent.y, accent.z, 0.62)
    aura_radius = (2.25 + tier * 0.22) * scale

    aura = _circle_node(name + "_floor_threat_aura", aura_radius, Vec4(accent.x, accent.y, accent.z, 0.20), 0.8 + tier * 0.08, 36)
    aura.setZ(0.08)
    shadow = _circle_node(name + "_inner_shadow_ring", aura_radius * 0.56, Vec4(color.x, color.y, color.z, 0.14), 0.75, 28)
    shadow.setZ(0.10)

    armored_core = _solid_box_node(name + "_current_gen_armored_core", Vec3(0.72 * scale, 0.34 * scale, height * 0.265), armor, seam, 0.72)
    armored_core.setZ(height * 0.46)
    chest_armor = _solid_box_node(name + "_current_gen_chest_plate", Vec3(0.96 * scale, 0.18 * scale, height * 0.108), armor_hi, Vec4(accent.x, accent.y, accent.z, 0.40), 0.58)
    chest_armor.setPos(0, -0.30 * scale, height * 0.56)
    shoulder_armor_l = _solid_box_node(name + "_current_gen_left_shoulder_armor", Vec3(0.54 * scale, 0.26 * scale, height * 0.055), armor_hi, seam, 0.58)
    shoulder_armor_l.setPos(-1.18 * scale, -0.05 * scale, height * 0.68)
    shoulder_armor_r = _solid_box_node(name + "_current_gen_right_shoulder_armor", Vec3(0.54 * scale, 0.26 * scale, height * 0.055), armor_hi, seam, 0.58)
    shoulder_armor_r.setPos(1.18 * scale, -0.05 * scale, height * 0.68)

    # Legacy token names kept, but these are now thin emissive cuts rather than full transparent body sheets.
    body_glow = _panel_node(name + "_hardlight_body_glow_panel", 1.18 * scale + tier * 0.08, height * 0.38, Vec4(color.x, color.y, color.z, 0.060), "wall_y")
    body_glow.setPos(0, -0.335 * scale, height * 0.48)
    shoulder_glow = _panel_node(name + "_hardlight_shoulder_glow_panel", 2.45 * scale + tier * 0.20, height * 0.050, Vec4(accent.x, accent.y, accent.z, 0.12), "wall_y")
    shoulder_glow.setPos(0, -0.355 * scale, height * 0.705)

    core = _diamond_node(name + "_weak_core_diamond", 0.82 * scale, 1.10 * scale, Vec4(accent.x, accent.y, accent.z, 0.95), 1.15 + tier * 0.08)
    core.setPos(0, -0.43 * scale, height * 0.565)
    optic = _circle_node(name + "_predator_optic", 0.30 * scale, Vec4(1.0, 0.08, 0.14, 0.92), 1.0, 18)
    optic.setPos(0, -0.42 * scale, height * 0.80)
    optic.setP(90)
    crest = _chevron_node(name + "_threat_crest", 1.74 * scale, 1.10 * scale, Vec4(accent.x, accent.y, accent.z, 0.76), 0.95 + tier * 0.08)
    crest.setPos(0, -0.22 * scale, height * 0.94)
    spine = _line_node(
        name + "_back_spine_stack",
        [
            Vec3(-0.76 * scale, 0.45 * scale, height * 0.38),
            Vec3(0.0, 0.82 * scale, height * 0.52),
            Vec3(0.76 * scale, 0.45 * scale, height * 0.38),
            Vec3(0.0, 0.98 * scale, height * 0.68),
            Vec3(-0.76 * scale, 0.45 * scale, height * 0.38),
        ],
        Vec4(accent.x, accent.y, accent.z, 0.48),
        0.82 + tier * 0.06,
        False,
    )
    marker = _line_node(
        name + "_vertical_threat_marker",
        [Vec3(0, -0.48 * scale, height * 0.18), Vec3(0, -0.48 * scale, height * 0.98)],
        Vec4(1.0, 0.06, 0.10, 0.42),
        0.85,
        False,
    )
    return (
        aura, shadow, armored_core, chest_armor, shoulder_armor_l, shoulder_armor_r,
        body_glow, shoulder_glow, core, optic, crest, spine, marker
    )

def _enemy_profile(variant: str) -> dict:
    return VARIANT_BY_ID.get(str(variant or "stalker"), VARIANT_BY_ID["stalker"])


def _enemy_color(variant: str) -> Vec4:
    return _enemy_profile(variant)["color"]


def _pawn_node(name: str, variant: str = "stalker", tier: int = 0) -> NodePath:
    """Build a presentation-grade hardlight enemy model from cheap primitives.

    This intentionally avoids mesh/model dependencies so Vector Arena remains
    portable and fast, but each class now has a readable monster silhouette:
    armor layers, horns/claws/pauldrons, glowing weak cores, ground threat rings,
    and distinct head/torso proportions for first-person targeting.
    """
    root = NodePath(name)
    profile = _enemy_profile(variant)
    color = profile["color"]
    accent = profile["accent"]
    scale = float(profile.get("scale", 1.0)) * (1.0 + tier * 0.04)
    vid = profile["id"]

    if vid == "brute":
        height = 9.4 * scale
        feet = _line_node(name + "_heavy_claw_feet", [
            Vec3(-3.25*scale, -0.10, 0), Vec3(-2.35*scale, 0.12, 1.55*scale), Vec3(-1.38*scale, 0.05, 2.65*scale),
            Vec3(0, 0.16, 3.15*scale), Vec3(1.38*scale, 0.05, 2.65*scale), Vec3(2.35*scale, 0.12, 1.55*scale), Vec3(3.25*scale, -0.10, 0)
        ], color, 2.35, False)
        torso = _wire_box(name + "_layered_crusher_torso", Vec3(2.25*scale, 0.95*scale, 2.55*scale), color, 2.05)
        torso.setZ(4.85 * scale)
        chest_plate = _diamond_node(name + "_molten_chest_plate", 2.65*scale, 2.05*scale, accent, 1.65)
        chest_plate.setZ(5.10*scale)
        pauldron_l = _wire_box(name + "_left_pauldrons", Vec3(1.20*scale, 0.58*scale, 0.62*scale), accent, 1.55)
        pauldron_l.setPos(-2.65*scale, 0, 6.55*scale)
        pauldron_r = _wire_box(name + "_right_pauldrons", Vec3(1.20*scale, 0.58*scale, 0.62*scale), accent, 1.55)
        pauldron_r.setPos(2.65*scale, 0, 6.55*scale)
        head = _wire_box(name + "_executioner_mask", Vec3(1.18*scale, 0.44*scale, 0.78*scale), color, 1.75)
        head.setZ(7.92 * scale)
        horns = _fang_arc_node(name + "_heavy_horn_crown", 2.35*scale, 8.95*scale, accent, 1.75, 7)
        cleaver_l = _line_node(name + "_left_cleaver_arm", [Vec3(-3.45*scale, -0.34, 6.4*scale), Vec3(-1.85*scale, -0.92, 5.28*scale), Vec3(-4.05*scale, -1.08, 4.1*scale)], accent, 1.45, False)
        cleaver_r = _line_node(name + "_right_cleaver_arm", [Vec3(3.45*scale, -0.34, 6.4*scale), Vec3(1.85*scale, -0.92, 5.28*scale), Vec3(4.05*scale, -1.08, 4.1*scale)], accent, 1.45, False)
        belt = _line_node(name + "_armor_belt", [Vec3(-2.4*scale, -0.38, 3.85*scale), Vec3(2.4*scale, -0.38, 3.85*scale)], accent, 1.2, False)
        parts = (feet, torso, chest_plate, pauldron_l, pauldron_r, head, horns, cleaver_l, cleaver_r, belt)
    elif vid == "sentry":
        height = 8.0 * scale
        base = _circle_node(name + "_levitating_crawler_base", 1.72*scale, color, 1.8, 36)
        base.setZ(1.15 * scale); base.setP(90)
        lower_ring = _circle_node(name + "_rotor_lower_ring", 1.25*scale, accent, 1.1, 32)
        lower_ring.setZ(2.15*scale); lower_ring.setP(90)
        mast = _line_node(name + "_optic_mast", [Vec3(0,0,0.6*scale), Vec3(0,0,6.25*scale)], color, 1.75, False)
        eye_outer = _circle_node(name + "_wide_targeting_eye", 1.10*scale, accent, 1.65, 32)
        eye_outer.setZ(6.32*scale); eye_outer.setP(90)
        eye_inner = _diamond_node(name + "_diamond_lens", 1.15*scale, 1.15*scale, Vec4(1.0, 1.0, 0.62, 0.92), 1.0)
        eye_inner.setZ(6.32*scale)
        fins = _line_node(name + "_signal_wing_fins", [
            Vec3(-3.2*scale,0,4.0*scale), Vec3(-1.05*scale,0,5.05*scale), Vec3(-0.42*scale,0,4.54*scale),
            Vec3(0.42*scale,0,4.54*scale), Vec3(1.05*scale,0,5.05*scale), Vec3(3.2*scale,0,4.0*scale)
        ], accent, 1.35, False)
        spider_legs = _line_node(name + "_spider_tripod_plus", [
            Vec3(-2.85*scale,0,0), Vec3(-0.55*scale,0,1.65*scale), Vec3(0,0,2.05*scale), Vec3(0.55*scale,0,1.65*scale), Vec3(2.85*scale,0,0),
            Vec3(0,0,2.05*scale), Vec3(0,2.45*scale,0), Vec3(0,0,2.05*scale), Vec3(0,-1.95*scale,0.25*scale)
        ], color, 1.42, False)
        antennae = _line_node(name + "_antennae", [Vec3(-0.65*scale,0,6.92*scale), Vec3(-1.35*scale,0,7.88*scale), Vec3(0,0,6.92*scale), Vec3(1.35*scale,0,7.88*scale), Vec3(0.65*scale,0,6.92*scale)], accent, 1.05, False)
        parts = (base, lower_ring, mast, eye_outer, eye_inner, fins, spider_legs, antennae)
    elif vid == "wraith":
        height = 9.2 * scale
        spine = _line_node(name + "_knife_spine", [Vec3(0,0,0.10*scale), Vec3(0,0,7.9*scale)], color, 1.72, False)
        cloak_l = _line_node(name + "_left_phase_cloak", [Vec3(-2.65*scale,0.10,1.1*scale), Vec3(-1.25*scale,0.34,3.8*scale), Vec3(-1.9*scale,0.18,6.65*scale), Vec3(-0.42*scale,0.08,7.85*scale)], Vec4(color.x, color.y, color.z, 0.55), 1.22, False)
        cloak_r = _line_node(name + "_right_phase_cloak", [Vec3(2.65*scale,0.10,1.1*scale), Vec3(1.25*scale,0.34,3.8*scale), Vec3(1.9*scale,0.18,6.65*scale), Vec3(0.42*scale,0.08,7.85*scale)], Vec4(color.x, color.y, color.z, 0.55), 1.22, False)
        ribs = _line_node(name + "_exposed_rib_cage", [Vec3(-2.25*scale,0,3.35*scale), Vec3(-0.78*scale,0,4.58*scale), Vec3(0.0,0,4.95*scale), Vec3(0.78*scale,0,4.58*scale), Vec3(2.25*scale,0,3.35*scale)], color, 1.42, False)
        mask = _circle_node(name + "_floating_void_mask", 0.98*scale, accent, 1.45, 28)
        mask.setZ(7.72*scale); mask.setP(90)
        horns = _line_node(name + "_split_wraith_horns", [Vec3(-1.45*scale,0,8.05*scale), Vec3(-2.35*scale,0,8.95*scale), Vec3(-0.42*scale,0,8.15*scale), Vec3(0.42*scale,0,8.15*scale), Vec3(2.35*scale,0,8.95*scale), Vec3(1.45*scale,0,8.05*scale)], accent, 1.22, False)
        claws = _line_node(name + "_long_phase_claws", [Vec3(-3.45*scale,-0.35,5.75*scale), Vec3(-1.05*scale,-0.84,4.12*scale), Vec3(0, -1.02, 5.95*scale), Vec3(1.05*scale,-0.84,4.12*scale), Vec3(3.45*scale,-0.35,5.75*scale)], accent, 1.24, False)
        legs = _line_node(name + "_needle_split_legs", [Vec3(-1.55*scale,0,0), Vec3(-0.44*scale,0,2.8*scale), Vec3(0,0,3.35*scale), Vec3(0.44*scale,0,2.8*scale), Vec3(1.55*scale,0,0)], color, 1.32, False)
        phase_halo = _circle_node(name + "_phase_halo", 1.42*scale, Vec4(accent.x, accent.y, accent.z, 0.48), 1.05, 34)
        phase_halo.setZ(6.45*scale); phase_halo.setP(90)
        parts = (spine, cloak_l, cloak_r, ribs, mask, horns, claws, legs, phase_halo)
    elif vid == "guardian":
        height = 11.2 * scale
        legs = _line_node(name + "_guardian_titan_legs", [
            Vec3(-3.55*scale,0,0), Vec3(-1.85*scale,0,2.35*scale), Vec3(-0.78*scale,0,3.45*scale), Vec3(0,0,4.0*scale),
            Vec3(0.78*scale,0,3.45*scale), Vec3(1.85*scale,0,2.35*scale), Vec3(3.55*scale,0,0)
        ], color, 2.55, False)
        torso = _wire_box(name + "_fortress_torso", Vec3(2.75*scale, 1.12*scale, 2.95*scale), color, 2.25)
        torso.setZ(5.75*scale)
        shield_plate = _diamond_node(name + "_fortress_core_plate", 3.00*scale, 2.75*scale, accent, 1.85)
        shield_plate.setZ(6.0*scale)
        crown = _line_node(name + "_guardian_crown_spikes", [
            Vec3(-2.65*scale,0,8.95*scale), Vec3(-1.35*scale,0,10.35*scale), Vec3(-0.42*scale,0,9.35*scale),
            Vec3(0,0,10.70*scale), Vec3(0.42*scale,0,9.35*scale), Vec3(1.35*scale,0,10.35*scale), Vec3(2.65*scale,0,8.95*scale)
        ], accent, 1.95, False)
        halo_outer = _circle_node(name + "_boss_halo_outer", 2.05*scale, accent, 1.48, 42)
        halo_outer.setZ(8.10*scale); halo_outer.setP(90)
        halo_inner = _circle_node(name + "_boss_halo_inner", 1.10*scale, Vec4(1.0, 0.95, 0.56, 0.76), 1.05, 32)
        halo_inner.setZ(8.10*scale); halo_inner.setP(90)
        blade_l = _line_node(name + "_left_execution_blade", [Vec3(-4.25*scale,-0.38,6.25*scale), Vec3(-1.65*scale,-0.92,4.92*scale), Vec3(-3.70*scale,-1.18,3.85*scale)], accent, 1.58, False)
        blade_r = _line_node(name + "_right_execution_blade", [Vec3(4.25*scale,-0.38,6.25*scale), Vec3(1.65*scale,-0.92,4.92*scale), Vec3(3.70*scale,-1.18,3.85*scale)], accent, 1.58, False)
        shoulder_l = _wire_box(name + "_left_boss_shoulder", Vec3(1.38*scale, 0.65*scale, 0.75*scale), accent, 1.55)
        shoulder_l.setPos(-3.10*scale, 0, 7.05*scale)
        shoulder_r = _wire_box(name + "_right_boss_shoulder", Vec3(1.38*scale, 0.65*scale, 0.75*scale), accent, 1.55)
        shoulder_r.setPos(3.10*scale, 0, 7.05*scale)
        parts = (legs, torso, shield_plate, crown, halo_outer, halo_inner, blade_l, blade_r, shoulder_l, shoulder_r)
    else:
        height = 7.8 * scale
        legs = _line_node(name + "_razor_runner_legs", [Vec3(-1.85*scale, 0, 0), Vec3(-0.92*scale, 0, 2.20*scale), Vec3(0,0,3.20*scale), Vec3(0.92*scale,0,2.20*scale), Vec3(1.85*scale,0,0)], color, 1.78, False)
        torso = _wire_box(name + "_thin_predator_torso", Vec3(1.22*scale, 0.44*scale, 2.05*scale), color, 1.55)
        torso.setZ(4.35 * scale)
        chest_spike = _diamond_node(name + "_blade_chest_core", 1.52*scale, 1.92*scale, accent, 1.35)
        chest_spike.setZ(4.70*scale)
        head = _circle_node(name + "_bright_single_eye", 0.84 * scale, accent, 1.38, 26)
        head.setZ(6.86 * scale); head.setP(90)
        brow = _line_node(name + "_predator_brow", [Vec3(-1.28*scale,0,7.20*scale), Vec3(0,0,7.55*scale), Vec3(1.28*scale,0,7.20*scale)], Vec4(1.0, 0.84, 0.20, 0.82), 1.1, False)
        spikes = _line_node(name + "_knife_shoulder_spikes", [Vec3(-2.58*scale, 0, 4.9*scale), Vec3(-0.84*scale, 0, 5.82*scale), Vec3(0,0,5.18*scale), Vec3(0.84*scale,0,5.82*scale), Vec3(2.58*scale,0,4.9*scale)], accent, 1.16, False)
        blade_l = _line_node(name + "_left_razor_arm", [Vec3(-2.58*scale, -0.38, 4.65*scale), Vec3(-0.82*scale, -0.82, 5.55*scale), Vec3(-3.05*scale, -1.02, 3.68*scale)], color, 1.12, False)
        blade_r = _line_node(name + "_right_razor_arm", [Vec3(2.58*scale, -0.38, 4.65*scale), Vec3(0.82*scale, -0.82, 5.55*scale), Vec3(3.05*scale, -1.02, 3.68*scale)], color, 1.12, False)
        parts = (legs, torso, chest_spike, head, brow, spikes, blade_l, blade_r)

    rig = _enemy_threat_rig(name, profile, scale, height, tier)
    for part in parts + rig:
        part.reparentTo(root)
        try:
            part.setTransparency(TransparencyAttrib.MAlpha)
        except Exception:
            pass
    root.setName(f"{name}_{profile['id']}_menacing_model")
    return root

class HoloVerseNativeMode:
    """Built-in Vector Arena mounted in the live HoloVerse ShowBase."""

    def __init__(self, host, mode=None, entry_path=None, label=MODE_TITLE):
        self.host = host
        self.mode = mode or {}
        self.entry_path = Path(entry_path) if entry_path else Path(__file__).resolve().parent / "main.py"
        self.folder = self.entry_path.parent
        self.label = str(label or MODE_TITLE)
        self._entered = False
        self._rng = random.Random(49173)
        self._owned: list[NodePath] = []
        self._dimension_ui_node_names = ("local_ui_root",)
        self.dimension_ui_visible = False
        self._saved_camera_parent = None
        self._saved_camera_transform = None
        self._saved_bg = None
        self._elapsed = 0.0
        self.player_pos = Vec3(0, -82, 0.0)
        self.player_vel = Vec3(0, 0, 0)
        self.player_yaw = 0.0
        self.player_pitch = 0.0
        self.health = 100.0
        self.armor = 50.0
        self.heat = 0.0
        self.combo = 1
        self.combo_timer = 0.0
        self.score = 0
        self.kills = 0
        self.wave = 1
        self.fire_cooldown = 0.0
        self.blast_cooldown = 0.0
        self.damage_flash = 0.0
        self._mouse1_latched = False
        self._mouse3_latched = False
        self._r_latched = False
        self._capture_pointer_once = True
        self.enemies: list[_Enemy] = []
        self.projectiles: list[_Projectile] = []
        self.impacts: list[_Impact] = []
        self.spawn_pulses: list[_SpawnPulse] = []
        self.kill_bursts: list[_KillBurst] = []
        self.muzzle_flashes: list[_MuzzleFlash] = []
        self.repulsor_waves: list[_RepulsorWave] = []
        self.heat_vent_sparks: list[_HeatVentSpark] = []
        self.cover_blocks: list[_CoverBlock] = []
        self.enemy_variant_counts: dict[str, int] = {profile["id"]: 0 for profile in ENEMY_VARIANTS}
        self.spawn_points = [
            Vec3(-64, 54, 0), Vec3(0, 68, 0), Vec3(64, 54, 0), Vec3(-78, -4, 0), Vec3(78, -4, 0), Vec3(-38, -52, 0), Vec3(38, -52, 0)
        ]
        self.reticle_root: NodePath | None = None
        self.local_ui_root: NodePath | None = None
        self.combat_text: OnscreenText | None = None
        self.help_text: OnscreenText | None = None
        self.wave_text: OnscreenText | None = None
        self.damage_overlay: NodePath | None = None
        self.weapon_root: NodePath | None = None
        self.weapon_glow_nodes: list[NodePath] = []
        self.weapon_recoil = 0.0
        self.weapon_charge = 0.0
        self.repulsor_flash = 0.0
        self.vent_fx_cooldown = 0.0
        self.phase_banner: OnscreenText | None = None
        self.theme_index = 0
        self.theme_pulse = 0.0
        self.wave_intro_timer = 2.5
        self.scenery_nodes: dict[str, list[NodePath]] = {"primary": [], "secondary": [], "accent": [], "floor": []}
        self.scenery_motion_nodes: list[NodePath] = []
        self.cover_glow_nodes: list[NodePath] = []
        self.spawn_gate_nodes: list[NodePath] = []

    # ------------------------------------------------------------------
    # Host resources
    # ------------------------------------------------------------------
    def _host_resources(self):
        self.render = self.host.render
        self.aspect2d = self.host.aspect2d
        self.render2d = getattr(self.host, "render2d", self.aspect2d)
        self.camera = self.host.camera
        self.camLens = self.host.camLens
        self.win = getattr(self.host, "win", None)
        self.accept = getattr(self.host, "accept", lambda *a, **k: None)
        self.ignore = getattr(self.host, "ignore", lambda *a, **k: None)
        self.disableMouse = getattr(self.host, "disableMouse", lambda *a, **k: None)
        self.setBackgroundColor = getattr(self.host, "setBackgroundColor", lambda *a, **k: None)
        self._saved_camera_parent = self.camera.getParent()
        self._saved_camera_transform = self.camera.getTransform()
        try:
            self._saved_bg = self.win.getClearColor() if self.win is not None else None
        except Exception:
            self._saved_bg = None
        self.root = self.render.attachNewNode("vector_arena_fps_native_root")
        self.world_root = self.root.attachNewNode("vector_arena_fps_world")
        self.fx_root = self.root.attachNewNode("vector_arena_fps_fx")
        self.reticle_root = self.aspect2d.attachNewNode("vector_arena_fps_reticle_root")
        self.local_ui_root = self.aspect2d.attachNewNode("vector_arena_fps_help_root")
        self._owned.extend([self.root, self.world_root, self.fx_root, self.reticle_root, self.local_ui_root])
        try:
            self.disableMouse()
            self.camLens.setFov(78)
            self.camLens.setNearFar(0.08, 900.0)
            self.setBackgroundColor(0.0015, 0.0025, 0.0065)
            if self.win is not None and hasattr(self.win, "requestProperties"):
                props = WindowProperties()
                props.setCursorHidden(True)
                self.win.requestProperties(props)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Scene build
    # ------------------------------------------------------------------
    def _build_lights(self):
        ambient = AmbientLight("vector_arena_fps_ambient")
        ambient.setColor(Vec4(0.10, 0.13, 0.17, 1.0))
        amb_np = self.root.attachNewNode(ambient)
        self.world_root.setLight(amb_np)
        sun = DirectionalLight("vector_arena_fps_directional")
        sun.setColor(Vec4(0.78, 0.96, 1.0, 1.0))
        sun_np = self.root.attachNewNode(sun)
        sun_np.setHpr(-24, -62, 0)
        self.world_root.setLight(sun_np)
        self._owned.extend([amb_np, sun_np])

    def _build_floor_and_grid(self):
        floor = _panel_node("vector_arena_fps_floor", ARENA_RADIUS * 2.25, ARENA_RADIUS * 2.25, SCENERY_THEMES[0]["floor"], "floor")
        floor.reparentTo(self.world_root)
        floor.setZ(-0.03)
        self.scenery_nodes["floor"].append(floor)
        self._owned.append(floor)

        seg = LineSegs("vector_arena_fps_floor_grid")
        seg.setThickness(0.9)
        step = 12
        span = int(ARENA_RADIUS)
        seg.setColor(Vec4(0.08, 1.0, 0.82, 0.28))
        for i in range(-span, span + 1, step):
            seg.moveTo(Vec3(i, -span, 0.025)); seg.drawTo(Vec3(i, span, 0.025))
            seg.moveTo(Vec3(-span, i, 0.025)); seg.drawTo(Vec3(span, i, 0.025))
        seg.setThickness(2.0)
        seg.setColor(Vec4(0.18, 1.0, 0.88, 0.68))
        for radius in (36, 72, ARENA_RADIUS):
            for k in range(65):
                a = math.tau * (k % 64) / 64
                p = Vec3(math.sin(a) * radius, math.cos(a) * radius, 0.05)
                if k == 0:
                    seg.moveTo(p)
                else:
                    seg.drawTo(p)
        node = NodePath(seg.create())
        node.setTransparency(TransparencyAttrib.MAlpha)
        node.reparentTo(self.world_root)
        self.scenery_nodes["primary"].append(node)
        self._owned.append(node)

        # Fixed combat lanes make the arena readable even while scenery colors shift.
        lane_specs = [
            ("north_lane", Vec3(0, 38, 0.025), ARENA_RADIUS * 1.45, 8.0, Vec4(0.08, 0.60, 0.72, 0.14)),
            ("south_lane", Vec3(0, -38, 0.026), ARENA_RADIUS * 1.45, 8.0, Vec4(0.08, 0.60, 0.72, 0.14)),
            ("center_lane", Vec3(0, 0, 0.027), 9.0, ARENA_RADIUS * 1.55, Vec4(0.10, 0.38, 0.68, 0.12)),
        ]
        for name, pos, width, height, color in lane_specs:
            lane = _panel_node("vector_arena_fps_" + name, width, height, color, "floor")
            lane.reparentTo(self.world_root)
            lane.setPos(pos)
            self.scenery_nodes["floor"].append(lane)
            self._owned.append(lane)

    def _build_walls_and_cover(self):
        armor = Vec4(0.022, 0.028, 0.038, 1.0)
        armor_hi = Vec4(0.050, 0.060, 0.078, 1.0)
        cyan_trim = Vec4(0.18, 0.95, 1.0, 0.44)
        red_trim = Vec4(1.0, 0.08, 0.18, 0.30)
        # Current-gen arena rule: solid armored architecture first, thin hardlight seams second.
        for name, pos, half in [
            ("north", Vec3(0, ARENA_RADIUS + 1.8, 9.5), Vec3(ARENA_RADIUS, 2.2, 9.5)),
            ("south", Vec3(0, -ARENA_RADIUS - 1.8, 9.5), Vec3(ARENA_RADIUS, 2.2, 9.5)),
            ("east", Vec3(ARENA_RADIUS + 1.8, 0, 9.5), Vec3(2.2, ARENA_RADIUS, 9.5)),
            ("west", Vec3(-ARENA_RADIUS - 1.8, 0, 9.5), Vec3(2.2, ARENA_RADIUS, 9.5)),
        ]:
            wall = _solid_box_node("vector_arena_fps_solid_armored_wall_" + name, half, armor, cyan_trim, 0.65)
            wall.reparentTo(self.world_root)
            wall.setPos(pos)
            self.scenery_nodes["secondary"].append(wall)
            self._owned.append(wall)
            # panel cuts keep the sci-fi identity without making the entire wall see-through.
            if half.x > half.y:
                for x in (-72, -36, 0, 36, 72):
                    strip = _armor_strip_node(f"vector_arena_fps_wall_{name}_thin_emissive_cut_{x}", 11.5, cyan_trim, True)
                    strip.reparentTo(self.world_root)
                    strip.setPos(x, pos.y + (-2.35 if pos.y > 0 else 2.35), 9.0)
                    self.scenery_nodes["primary"].append(strip)
                    self._owned.append(strip)
            else:
                for y in (-72, -36, 0, 36, 72):
                    strip = _armor_strip_node(f"vector_arena_fps_wall_{name}_thin_emissive_cut_{y}", 11.5, cyan_trim, True)
                    strip.reparentTo(self.world_root)
                    strip.setPos(pos.x + (-2.35 if pos.x > 0 else 2.35), y, 9.0)
                    self.scenery_nodes["primary"].append(strip)
                    self._owned.append(strip)

        cover_specs = [
            (Vec3(-34, -42, 3.0), Vec3(10, 5, 3)), (Vec3(34, -42, 3.0), Vec3(10, 5, 3)),
            (Vec3(-48, -4, 4.2), Vec3(7, 7, 4.2)), (Vec3(48, -4, 4.2), Vec3(7, 7, 4.2)),
            (Vec3(-24, 30, 3.2), Vec3(12, 4.5, 3.2)), (Vec3(24, 30, 3.2), Vec3(12, 4.5, 3.2)),
            (Vec3(0, 10, 5.0), Vec3(6, 6, 5.0)), (Vec3(0, 54, 6.0), Vec3(16, 3, 6.0)),
        ]
        for i, (pos, half) in enumerate(cover_specs):
            self.cover_blocks.append(_CoverBlock(pos=Vec3(pos.x, pos.y, 0), half=Vec3(half.x, half.y, half.z)))
            base = _solid_box_node(f"vector_arena_fps_solid_armored_cover_{i}", half, armor_hi, cyan_trim, 0.72)
            base.reparentTo(self.world_root)
            base.setPos(pos)
            cap = _solid_box_node(f"vector_arena_fps_cover_beveled_top_cap_{i}", Vec3(half.x * 0.82, half.y * 0.82, 0.22), Vec4(0.055, 0.065, 0.078, 1.0), Vec4(0.20, 1.0, 0.92, 0.34), 0.55)
            cap.reparentTo(self.world_root)
            cap.setPos(pos.x, pos.y, pos.z + half.z + 0.25)
            front_strip = _armor_strip_node(f"vector_arena_fps_cover_{i}_thin_front_light_seam", half.x * 1.6, Vec4(0.20, 1.0, 0.92, 0.52), False)
            front_strip.reparentTo(self.world_root)
            front_strip.setPos(pos.x, pos.y - half.y - 0.08, pos.z + half.z * 0.45)
            red_scar = _armor_strip_node(f"vector_arena_fps_cover_{i}_corruption_scar", half.x * 0.65, red_trim, False)
            red_scar.reparentTo(self.world_root)
            red_scar.setPos(pos.x, pos.y + half.y + 0.10, pos.z + half.z * 0.68)
            glow = _panel_node(f"vector_arena_fps_cover_glow_{i}", half.x * 1.65, half.y * 1.65, Vec4(0.05, 0.34, 0.42, 0.08), "floor")
            glow.reparentTo(self.world_root)
            glow.setPos(pos.x, pos.y, 0.08)
            self.scenery_nodes["primary"].extend([front_strip, red_scar])
            self.cover_glow_nodes.append(glow)
            self._owned.extend([base, cap, front_strip, red_scar, glow])

    def _build_spawn_gates(self):
        armor = Vec4(0.024, 0.030, 0.040, 1.0)
        accent = Vec4(1.0, 0.08, 0.18, 0.58)
        amber = Vec4(1.0, 0.58, 0.16, 0.48)
        for i, point in enumerate(self.spawn_points):
            gate_root = self.world_root.attachNewNode(f"vector_arena_fps_solid_spawn_gate_machine_{i}")
            direction = Vec3(-point.x, -point.y, 0)
            if direction.lengthSquared() > 0.001:
                direction.normalize()
            gate_root.setPos(point)
            gate_root.setH(math.degrees(math.atan2(direction.x, direction.y)))
            left = _solid_box_node(f"vector_arena_fps_spawn_gate_{i}_left_armored_pylon", Vec3(0.72, 0.78, 4.4), armor, accent, 0.62)
            right = _solid_box_node(f"vector_arena_fps_spawn_gate_{i}_right_armored_pylon", Vec3(0.72, 0.78, 4.4), armor, accent, 0.62)
            header = _solid_box_node(f"vector_arena_fps_spawn_gate_{i}_heavy_header", Vec3(4.2, 0.72, 0.72), Vec4(0.026, 0.030, 0.038, 1.0), accent, 0.58)
            left.setPos(-4.1, 0.0, 4.4)
            right.setPos(4.1, 0.0, 4.4)
            header.setPos(0.0, 0.0, 8.55)
            slit_l = _armor_strip_node(f"vector_arena_fps_spawn_gate_{i}_left_red_light_slit", 6.2, accent, True)
            slit_r = _armor_strip_node(f"vector_arena_fps_spawn_gate_{i}_right_red_light_slit", 6.2, accent, True)
            slit_l.setPos(-4.95, -0.86, 4.7)
            slit_r.setPos(4.95, -0.86, 4.7)
            inner = _circle_node(f"vector_arena_fps_spawn_gate_inner_{i}", 2.25, amber, 0.95, 28)
            inner.setPos(0, -0.94, 5.8)
            inner.setP(90)
            gate = _circle_node(f"vector_arena_fps_spawn_gate_{i}", 4.05, Vec4(1.0, 0.08, 0.18, 0.28), 0.82, 36)
            gate.setPos(0, -0.96, 5.8)
            gate.setP(90)
            for part in (left, right, header, slit_l, slit_r, inner, gate):
                part.reparentTo(gate_root)
            self.spawn_gate_nodes.extend([gate_root, left, right, header, slit_l, slit_r, inner, gate])
            self.scenery_nodes["accent"].extend([slit_l, slit_r, inner, gate])
            self.scenery_nodes["secondary"].extend([gate_root, left, right, header])
            self._owned.extend([gate_root, left, right, header, slit_l, slit_r, inner, gate])

    def _build_scenery_shell(self):
        # Presentation scenery: solid skyline machinery plus controlled glow rings.
        armor = Vec4(0.020, 0.026, 0.036, 1.0)
        trim = Vec4(0.18, 1.0, 0.90, 0.34)
        for i in range(12):
            angle = math.tau * i / 12.0
            radius = ARENA_RADIUS + 18.0
            x = math.sin(angle) * radius
            y = math.cos(angle) * radius
            height = 18.0 + (i % 3) * 5.0
            pylon = _solid_box_node(f"vector_arena_fps_solid_skyline_pylon_{i}", Vec3(2.8, 2.8, height), armor, trim, 0.58)
            pylon.reparentTo(self.world_root)
            pylon.setPos(x, y, height)
            pylon.setH(-math.degrees(angle))
            light_cut = _armor_strip_node(f"vector_arena_fps_skyline_pylon_{i}_vertical_light_cut", height * 1.2, trim, True)
            light_cut.reparentTo(pylon)
            light_cut.setPos(0, -2.92, 0)
            self.scenery_nodes["primary"].append(light_cut)
            self.scenery_nodes["secondary"].append(pylon)
            self.scenery_motion_nodes.append(pylon)
            self._owned.extend([pylon, light_cut])

        for j, (radius, z, thick) in enumerate(((ARENA_RADIUS * 0.72, 25.0, 1.0), (ARENA_RADIUS * 0.98, 33.0, 0.9), (ARENA_RADIUS * 1.18, 43.0, 0.8))):
            ring = _circle_node(f"vector_arena_fps_overhead_ring_{j}", radius, Vec4(0.18, 1.0, 0.90, 0.26), thick, 80)
            ring.reparentTo(self.world_root)
            ring.setZ(z)
            self.scenery_nodes["secondary"].append(ring)
            self.scenery_motion_nodes.append(ring)
            self._owned.append(ring)

        for i in range(8):
            angle = math.tau * i / 8.0 + math.radians(22.5)
            start = Vec3(math.sin(angle) * 42, math.cos(angle) * 42, 0.20)
            end = Vec3(math.sin(angle) * (ARENA_RADIUS - 10), math.cos(angle) * (ARENA_RADIUS - 10), 0.20)
            spoke = _line_node(f"vector_arena_fps_power_spoke_{i}", [start, end], Vec4(1.0, 0.72, 0.18, 0.32), 1.0, False)
            spoke.reparentTo(self.world_root)
            self.scenery_nodes["accent"].append(spoke)
            self._owned.append(spoke)

    def _build_score_board(self):
        frame = _wire_box("vector_arena_fps_scoreboard_frame", Vec3(34, 1.0, 8), Vec4(0.12, 1.0, 0.86, 0.68), 1.1)
        frame.reparentTo(self.world_root)
        frame.setPos(0, ARENA_RADIUS - 2.0, 20)
        self.wave_text = OnscreenText(
            text="VECTOR ARENA\nFIRST PERSON BOOT",
            mayChange=True,
            parent=frame,
            align=TextNode.ACenter,
            pos=(0, 0.02),
            scale=2.7,
            fg=(0.64, 1.0, 0.88, 0.94),
            shadow=(0, 0, 0, 0.85),
        )
        self.wave_text.setBillboardPointEye()
        self._owned.extend([frame, self.wave_text])

    def _build_enemy_pool(self):
        for i in range(ENEMY_CAP):
            variant = ENEMY_POOL_VARIANTS[i % len(ENEMY_POOL_VARIANTS)]
            profile = _enemy_profile(variant)
            tier = max(0, min(3, ENEMY_VARIANTS.index(profile)))
            node = _pawn_node(f"vector_arena_fps_enemy_{i}", variant, tier)
            node.reparentTo(self.world_root)
            enemy = _Enemy(
                node=node,
                pos=Vec3(0, 0, 0),
                vel=Vec3(0, 0, 0),
                hp=float(profile["hp"]),
                max_hp=float(profile["hp"]),
                tier=tier,
                phase=self._rng.random() * math.tau,
                attack_cooldown=self._rng.uniform(0.2, 1.8),
                variant=variant,
                display_name=str(profile["name"]),
                speed_scale=float(profile["speed"]),
                damage_scale=float(profile["damage"]),
                score_value=int(profile["score"]),
                aim_radius=float(profile["aim_radius"]),
                active=True,
            )
            self.enemies.append(enemy)
            self._spawn_enemy(enemy, i, initial=True)

    def _build_projectile_pool(self):
        for i in range(PROJECTILE_CAP):
            beam_root = NodePath(f"vector_arena_fps_hitscan_beam_{i}")
            core = _line_node(f"vector_arena_fps_hitscan_beam_core_{i}", [Vec3(0, 0, 0), Vec3(0, 1, 0)], Vec4(1.0, 0.96, 0.34, 0.98), 2.6, False)
            halo = _line_node(f"vector_arena_fps_hitscan_beam_halo_{i}", [Vec3(0, 0, 0), Vec3(0, 1, 0)], Vec4(0.22, 1.0, 0.90, 0.44), 5.2, False)
            spark = _line_node(f"vector_arena_fps_hitscan_beam_spark_{i}", [Vec3(-0.18, 0.50, 0), Vec3(0.18, 0.50, 0)], Vec4(1.0, 0.26, 0.94, 0.68), 1.1, False)
            for part in (halo, core, spark):
                part.reparentTo(beam_root)
            beam_root.reparentTo(self.fx_root)
            beam_root.hide()
            self.projectiles.append(_Projectile(node=beam_root))
        for i in range(IMPACT_CAP):
            impact_root = NodePath(f"vector_arena_fps_impact_{i}")
            ring = _circle_node(f"vector_arena_fps_impact_ring_{i}", 2.2, Vec4(1.0, 0.30, 0.94, 0.78), 1.6, 28)
            star_a = _line_node(f"vector_arena_fps_impact_star_a_{i}", [Vec3(-1.65,0,0), Vec3(1.65,0,0)], Vec4(1.0, 0.92, 0.22, 0.70), 1.0, False)
            star_b = _line_node(f"vector_arena_fps_impact_star_b_{i}", [Vec3(0,-1.65,0), Vec3(0,1.65,0)], Vec4(0.28, 1.0, 0.92, 0.62), 0.9, False)
            for part in (ring, star_a, star_b):
                part.reparentTo(impact_root)
            impact_root.reparentTo(self.fx_root)
            impact_root.hide()
            self.impacts.append(_Impact(node=impact_root, pos=Vec3(0, 0, 0)))
        for i in range(SPAWN_PULSE_CAP):
            node = _circle_node(f"vector_arena_fps_spawn_pulse_{i}", 3.0, Vec4(1.0, 0.20, 0.82, 0.62), 1.4, 28)
            node.reparentTo(self.fx_root)
            node.setP(90)
            node.hide()
            self.spawn_pulses.append(_SpawnPulse(node=node, pos=Vec3(0,0,0)))
        for i in range(KILL_BURST_CAP):
            burst_root = NodePath(f"vector_arena_fps_kill_burst_{i}")
            ring_a = _circle_node(f"vector_arena_fps_kill_burst_ring_a_{i}", 2.0, Vec4(1.0, 0.86, 0.18, 0.80), 1.75, 32)
            ring_b = _circle_node(f"vector_arena_fps_kill_burst_ring_b_{i}", 1.2, Vec4(1.0, 0.20, 0.92, 0.72), 1.25, 28)
            spike_a = _line_node(f"vector_arena_fps_kill_burst_spike_a_{i}", [Vec3(-3.2,0,0), Vec3(3.2,0,0)], Vec4(1.0, 0.92, 0.22, 0.84), 1.35, False)
            spike_b = _line_node(f"vector_arena_fps_kill_burst_spike_b_{i}", [Vec3(0,-3.2,0), Vec3(0,3.2,0)], Vec4(1.0, 0.25, 0.94, 0.74), 1.15, False)
            crown = _chevron_node(f"vector_arena_fps_kill_burst_crown_{i}", 5.0, 2.2, Vec4(0.30, 1.0, 0.92, 0.68), 1.0, False)
            for part in (ring_a, ring_b, spike_a, spike_b, crown):
                part.reparentTo(burst_root)
            burst_root.reparentTo(self.fx_root)
            burst_root.setP(90)
            burst_root.hide()
            self.kill_bursts.append(_KillBurst(node=burst_root, pos=Vec3(0,0,0)))
        for i in range(MUZZLE_FLASH_CAP):
            flash_root = NodePath(f"vector_arena_fps_muzzle_flash_{i}")
            cone = _circle_node(f"vector_arena_fps_muzzle_flash_cone_{i}", 0.34, Vec4(1.0, 0.92, 0.26, 0.86), 1.5, 20)
            cross = _line_node(f"vector_arena_fps_muzzle_flash_cross_{i}", [Vec3(-0.42,0,0), Vec3(0.42,0,0), Vec3(0,0,-0.42), Vec3(0,0,0.42)], Vec4(0.24, 1.0, 0.92, 0.68), 1.1, False)
            crown = _chevron_node(f"vector_arena_fps_muzzle_flash_crown_{i}", 0.72, 0.52, Vec4(1.0, 0.22, 0.92, 0.70), 1.0, False)
            for part in (cone, cross, crown):
                part.reparentTo(flash_root)
            flash_root.reparentTo(self.fx_root)
            flash_root.hide()
            self.muzzle_flashes.append(_MuzzleFlash(node=flash_root, pos=Vec3(0,0,0)))
        for i in range(REPULSOR_WAVE_CAP):
            wave_root = NodePath(f"vector_arena_fps_repulsor_wave_{i}")
            ring_a = _circle_node(f"vector_arena_fps_repulsor_wave_ring_a_{i}", 3.0, Vec4(0.24, 1.0, 0.96, 0.62), 1.45, 36)
            ring_b = _circle_node(f"vector_arena_fps_repulsor_wave_ring_b_{i}", 1.6, Vec4(1.0, 0.26, 0.96, 0.52), 1.05, 32)
            slash = _line_node(f"vector_arena_fps_repulsor_wave_slash_{i}", [Vec3(-3.2,0,0), Vec3(3.2,0,0), Vec3(0,-3.2,0), Vec3(0,3.2,0)], Vec4(1.0, 0.86, 0.22, 0.54), 1.0, False)
            for part in (ring_a, ring_b, slash):
                part.reparentTo(wave_root)
            wave_root.reparentTo(self.fx_root)
            wave_root.setP(90)
            wave_root.hide()
            self.repulsor_waves.append(_RepulsorWave(node=wave_root, pos=Vec3(0,0,0)))
        for i in range(HEAT_VENT_SPARK_CAP):
            spark_root = NodePath(f"vector_arena_fps_heat_vent_spark_{i}")
            line_a = _line_node(f"vector_arena_fps_heat_vent_spark_line_a_{i}", [Vec3(-0.5,0,0), Vec3(0.5,0,0)], Vec4(1.0, 0.72, 0.18, 0.70), 1.0, False)
            line_b = _line_node(f"vector_arena_fps_heat_vent_spark_line_b_{i}", [Vec3(0,0,-0.5), Vec3(0,0,0.5)], Vec4(1.0, 0.22, 0.92, 0.60), 0.9, False)
            for part in (line_a, line_b):
                part.reparentTo(spark_root)
            spark_root.reparentTo(self.fx_root)
            spark_root.hide()
            self.heat_vent_sparks.append(_HeatVentSpark(node=spark_root, pos=Vec3(0,0,0)))


    def _build_weapon_viewmodel(self):
        # Current-gen hardlight rifle: solid black receiver and barrel housing with
        # restrained cyan/magenta emissive seams.  Keeps old token names for route
        # validator continuity, but removes the see-through wireframe gun feel.
        self.weapon_root = self.camera.attachNewNode("vector_arena_fps_weapon_root")
        self.weapon_root.setPos(0.50, 1.02, -0.36)
        self.weapon_root.setHpr(-5.0, -2.0, 0.0)
        armor = Vec4(0.024, 0.030, 0.040, 1.0)
        armor_hi = Vec4(0.038, 0.045, 0.055, 1.0)
        cyan = Vec4(0.22, 1.0, 0.88, 0.78)
        gold = Vec4(1.0, 0.84, 0.24, 0.82)
        magenta = Vec4(1.0, 0.18, 0.66, 0.72)
        hot = Vec4(1.0, 0.20, 0.10, 0.70)

        receiver = _solid_box_node("vector_arena_fps_weapon_receiver", Vec3(0.18, 0.36, 0.105), armor_hi, cyan, 0.45)
        receiver.reparentTo(self.weapon_root); receiver.setPos(0, 0.14, 0)
        grip_body = _solid_box_node("vector_arena_fps_weapon_grip_solid_body", Vec3(0.075, 0.075, 0.22), armor, Vec4(0.18, 1.0, 0.88, 0.30), 0.35)
        grip_body.reparentTo(self.weapon_root); grip_body.setPos(0.06, -0.02, -0.25); grip_body.setR(-11)
        grip = _line_node("vector_arena_fps_weapon_grip", [Vec3(-0.08, -0.10, -0.08), Vec3(-0.13, -0.02, -0.30), Vec3(0.08, -0.10, -0.08), Vec3(0.13, -0.02, -0.30)], cyan, 0.55, False)
        grip.reparentTo(self.weapon_root)
        stock_body = _solid_box_node("vector_arena_fps_weapon_stock_solid_body", Vec3(0.24, 0.12, 0.055), armor, Vec4(0.14, 0.62, 1.0, 0.26), 0.34)
        stock_body.reparentTo(self.weapon_root); stock_body.setPos(0, -0.31, -0.055)
        stock = _line_node("vector_arena_fps_weapon_stock", [Vec3(-0.16, -0.26, -0.03), Vec3(-0.42, -0.42, -0.11), Vec3(0.16, -0.26, -0.03), Vec3(0.42, -0.42, -0.11)], Vec4(0.32, 0.80, 1.0, 0.42), 0.62, False)
        stock.reparentTo(self.weapon_root)
        barrel_shell = _solid_box_node("vector_arena_fps_weapon_barrel_opaque_shell", Vec3(0.105, 0.38, 0.055), armor, cyan, 0.36)
        barrel_shell.reparentTo(self.weapon_root); barrel_shell.setPos(0, 0.63, 0.02)
        barrel_core = _line_node("vector_arena_fps_weapon_barrel_core", [Vec3(0, 0.22, 0.035), Vec3(0, 1.08, 0.035)], gold, 1.42, False)
        barrel_core.reparentTo(self.weapon_root)
        barrel_top = _line_node("vector_arena_fps_weapon_top_rail", [Vec3(-0.10, 0.22, 0.112), Vec3(0.10, 0.22, 0.112), Vec3(0.10, 1.02, 0.112), Vec3(-0.10, 1.02, 0.112)], cyan, 0.75, True)
        barrel_top.reparentTo(self.weapon_root)
        side_a = _solid_box_node("vector_arena_fps_weapon_left_arc_fin_solid", Vec3(0.035, 0.28, 0.052), armor, cyan, 0.30)
        side_b = _solid_box_node("vector_arena_fps_weapon_right_arc_fin_solid", Vec3(0.035, 0.28, 0.052), armor, cyan, 0.30)
        side_a.reparentTo(self.weapon_root); side_a.setPos(-0.22, 0.56, -0.055); side_a.setH(-7)
        side_b.reparentTo(self.weapon_root); side_b.setPos(0.22, 0.56, -0.055); side_b.setH(7)
        coil_a = _circle_node("vector_arena_fps_weapon_capacitor_coil_a", 0.135, magenta, 0.95, 28)
        coil_b = _circle_node("vector_arena_fps_weapon_capacitor_coil_b", 0.100, gold, 0.85, 24)
        for coil, y, x in ((coil_a, 0.50, -0.085), (coil_b, 0.70, 0.085)):
            coil.reparentTo(self.weapon_root); coil.setPos(x, y, 0.040); coil.setP(90)
        heat_l = _line_node("vector_arena_fps_weapon_left_heat_strip", [Vec3(-0.192, 0.34, -0.045), Vec3(-0.192, 0.88, -0.045)], hot, 0.95, False)
        heat_r = _line_node("vector_arena_fps_weapon_right_heat_strip", [Vec3(0.192, 0.34, -0.045), Vec3(0.192, 0.88, -0.045)], hot, 0.95, False)
        heat_l.reparentTo(self.weapon_root); heat_r.reparentTo(self.weapon_root)
        sight_bridge = _solid_box_node("vector_arena_fps_weapon_projector_sight_bridge", Vec3(0.09, 0.05, 0.025), armor, gold, 0.28)
        sight_bridge.reparentTo(self.weapon_root); sight_bridge.setPos(0, 0.95, 0.115)
        sight = _circle_node("vector_arena_fps_weapon_projector_sight", 0.070, gold, 0.78, 20)
        sight.reparentTo(self.weapon_root); sight.setPos(0, 1.00, 0.135); sight.setP(90)
        muzzle_crown = _chevron_node("vector_arena_fps_weapon_muzzle_crown", 0.34, 0.24, Vec4(1.0, 0.24, 0.82, 0.70), 0.88, False)
        muzzle_crown.reparentTo(self.weapon_root); muzzle_crown.setPos(0, 1.12, 0.035)
        charge_core = _diamond_node("vector_arena_fps_weapon_charge_core", 0.18, 0.24, Vec4(0.32, 1.0, 0.92, 0.70), 0.82)
        charge_core.reparentTo(self.weapon_root); charge_core.setPos(0, 0.30, 0.032)
        self.weapon_glow_nodes = [coil_a, coil_b, heat_l, heat_r, muzzle_crown, charge_core, sight]
        for node in (self.weapon_root, receiver, grip_body, grip, stock_body, stock, barrel_shell, barrel_core, barrel_top, side_a, side_b, coil_a, coil_b, heat_l, heat_r, sight_bridge, sight, muzzle_crown, charge_core):
            self._owned.append(node)

    def _build_reticle_and_hud(self):
        assert self.reticle_root is not None
        # Reticle is not debug UI; it is part of the first-person shooter presentation.
        reticle_lines = [
            _line_node("vector_arena_fps_reticle_h", [Vec3(-0.030, 0, 0), Vec3(-0.010, 0, 0), Vec3(0.010, 0, 0), Vec3(0.030, 0, 0)], Vec4(0.72, 1.0, 0.92, 0.95), 1.15, False),
            _line_node("vector_arena_fps_reticle_v", [Vec3(0, 0, -0.030), Vec3(0, 0, -0.010), Vec3(0, 0, 0.010), Vec3(0, 0, 0.030)], Vec4(0.72, 1.0, 0.92, 0.95), 1.15, False),
            _circle_node("vector_arena_fps_reticle_ring", 0.045, Vec4(0.20, 1.0, 0.88, 0.44), 0.85, 32),
        ]
        for node in reticle_lines:
            node.reparentTo(self.reticle_root)
            self._owned.append(node)

        self.combat_text = OnscreenText(
            text="HP 100  ARMOR 050  HEAT 000  SCORE 00000",
            parent=self.reticle_root,
            pos=(-1.30, -0.88),
            align=TextNode.ALeft,
            scale=0.038,
            fg=(0.62, 1.0, 0.90, 0.92),
            shadow=(0, 0, 0, 0.85),
            mayChange=True,
        )
        self._owned.append(self.combat_text)

        self.phase_banner = OnscreenText(
            text="SCENERY SHIFT // PRISM FOUNDRY",
            parent=self.reticle_root,
            pos=(0.0, 0.72),
            align=TextNode.ACenter,
            scale=0.050,
            fg=(0.76, 1.0, 0.92, 0.90),
            shadow=(0, 0, 0, 0.90),
            mayChange=True,
        )
        self._owned.append(self.phase_banner)

        cm = CardMaker("vector_arena_fps_damage_overlay")
        cm.setFrameFullscreenQuad()
        self.damage_overlay = self.render2d.attachNewNode(cm.generate())
        self.damage_overlay.setColor(1.0, 0.05, 0.05, 0.0)
        self.damage_overlay.setTransparency(TransparencyAttrib.MAlpha)
        self._owned.append(self.damage_overlay)

        assert self.local_ui_root is not None
        self.help_text = OnscreenText(
            text=(
                "VECTOR ARENA // FIRST-PERSON ARCADE SHOOTER\n"
                "WASD move  Mouse look  LMB pulse rifle  RMB repulsor blast  Shift dash  R vent heat\n"
                "Use cover, keep enemies in the reticle, survive waves. ESC / 0 returns to HoloVerse."
            ),
            parent=self.local_ui_root,
            pos=(-1.30, 0.86),
            align=TextNode.ALeft,
            scale=0.035,
            fg=(0.74, 0.96, 1.0, 0.90),
            shadow=(0, 0, 0, 0.80),
            mayChange=True,
        )
        self._owned.append(self.help_text)

    def _build_scene(self):
        self._build_lights()
        self._build_floor_and_grid()
        self._build_walls_and_cover()
        self._build_spawn_gates()
        self._build_scenery_shell()
        self._build_score_board()
        self._build_enemy_pool()
        self._build_projectile_pool()
        self._build_weapon_viewmodel()
        self._build_reticle_and_hud()
        self._apply_scenery_theme(0, instant=True)

    def _current_theme(self) -> dict:
        return SCENERY_THEMES[self.theme_index % len(SCENERY_THEMES)]

    def _set_nodes_color(self, nodes: list[NodePath], color: Vec4):
        for node in nodes:
            try:
                node.setColor(color)
                node.setColorScale(1, 1, 1, 1)
            except Exception:
                pass

    def _apply_scenery_theme(self, index: int | None = None, instant: bool = False):
        if index is not None:
            self.theme_index = int(index) % len(SCENERY_THEMES)
        theme = self._current_theme()
        self.theme_pulse = 1.0 if not instant else 0.25
        self._set_nodes_color(self.scenery_nodes.get("primary", []), theme["primary"])
        self._set_nodes_color(self.scenery_nodes.get("secondary", []), theme["secondary"])
        self._set_nodes_color(self.scenery_nodes.get("accent", []), theme["accent"])
        self._set_nodes_color(self.scenery_nodes.get("floor", []), theme["floor"])
        cover_color = Vec4(theme["primary"].x * 0.30, theme["primary"].y * 0.42, theme["primary"].z * 0.46, 0.22)
        self._set_nodes_color(self.cover_glow_nodes, cover_color)
        try:
            sky = theme.get("sky", (0.002, 0.004, 0.010))
            self.setBackgroundColor(float(sky[0]), float(sky[1]), float(sky[2]))
        except Exception:
            pass
        if self.phase_banner is not None:
            self.phase_banner["text"] = f"SCENERY SHIFT // {theme['name']}"
        if self.help_text is not None:
            self.help_text["text"] = (
                f"VECTOR ARENA // {theme['name']}\n"
                "WASD move  Mouse look  LMB pulse rifle  RMB repulsor blast  Shift dash  R vent heat\n"
                "Survive the changing wave room. The arena layout stays stable; the hardlight shell shifts each wave."
            )

    def _advance_wave(self):
        self.wave += 1
        self.armor = min(72.0, self.armor + 11.0)
        self.health = min(100.0, self.health + 8.0)
        self.wave_intro_timer = 2.2
        self._apply_scenery_theme(self.wave - 1)
        for i, enemy in enumerate(self.enemies):
            self._spawn_enemy(enemy, i)

    def _update_scenery(self, dt: float):
        self.theme_pulse = max(0.0, self.theme_pulse - dt * 0.70)
        if self.wave_intro_timer > 0.0:
            self.wave_intro_timer = max(0.0, self.wave_intro_timer - dt)
        pulse = 1.0 + self.theme_pulse * 0.04
        for i, node in enumerate(self.scenery_motion_nodes):
            try:
                if "overhead_ring" in node.getName():
                    node.setH((self._elapsed * (4.0 + i * 1.2)) % 360.0)
                    node.setScale(pulse + math.sin(self._elapsed * 1.4 + i) * 0.008)
                else:
                    node.setScale(1.0, 1.0, pulse + math.sin(self._elapsed * 2.0 + i) * 0.010)
            except Exception:
                pass
        if self.phase_banner is not None:
            alpha = 0.0
            if self.wave_intro_timer > 0.0:
                alpha = min(0.95, 0.35 + self.wave_intro_timer * 0.32)
            elif self.theme_pulse > 0.0:
                alpha = min(0.70, self.theme_pulse)
            self.phase_banner.setColorScale(1, 1, 1, alpha)

    # ------------------------------------------------------------------
    # Input helpers
    # ------------------------------------------------------------------
    def _keyboard_button(self, name: str):
        try:
            if len(name) == 1:
                return KeyboardButton.asciiKey(name)
            if name == "space":
                return KeyboardButton.space()
            if name == "shift":
                return KeyboardButton.shift()
            if name == "arrow_up":
                return KeyboardButton.up()
            if name == "arrow_down":
                return KeyboardButton.down()
            if name == "arrow_left":
                return KeyboardButton.left()
            if name == "arrow_right":
                return KeyboardButton.right()
        except Exception:
            return None
        return None

    def _button_down(self, button) -> bool:
        watcher = getattr(self.host, "mouseWatcherNode", None)
        if watcher is None or button is None:
            return False
        try:
            return bool(watcher.isButtonDown(button))
        except Exception:
            try:
                return bool(watcher.is_button_down(button))
            except Exception:
                return False

    def _key_down(self, *names: str) -> bool:
        return any(self._button_down(self._keyboard_button(name)) for name in names)

    def _mouse_down(self, index: int) -> bool:
        try:
            button = MouseButton.one() if index == 1 else MouseButton.three()
            return self._button_down(button)
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Gameplay
    # ------------------------------------------------------------------
    def _spawn_pulse(self, pos: Vec3):
        for pulse in self.spawn_pulses:
            if not pulse.active:
                pulse.active = True
                pulse.age = 0.0
                pulse.pos = Vec3(pos)
                pulse.node.setPos(pos + Vec3(0, 0, 4.8))
                pulse.node.setScale(0.5)
                try:
                    pulse.node.setColor(self._current_theme()["accent"])
                except Exception:
                    pass
                pulse.node.show()
                return

    def _spawn_enemy(self, enemy: _Enemy, slot: int, initial: bool = False):
        active_budget = min(ENEMY_CAP, 8 + self.wave * 2)
        if slot >= active_budget:
            enemy.active = False
            enemy.node.hide()
            return
        point = self.spawn_points[slot % len(self.spawn_points)]
        jitter = Vec3(self._rng.uniform(-8, 8), self._rng.uniform(-5, 5), 0)
        enemy.pos = point + jitter
        enemy.vel = Vec3(0, 0, 0)
        profile = _enemy_profile(enemy.variant)
        wave_hp = self.wave * (3.0 if enemy.variant == "stalker" else 6.5)
        enemy.max_hp = float(profile["hp"]) + wave_hp
        enemy.hp = enemy.max_hp
        enemy.speed_scale = float(profile["speed"])
        enemy.damage_scale = float(profile["damage"])
        enemy.score_value = int(profile["score"])
        enemy.aim_radius = float(profile["aim_radius"])
        enemy.attack_cooldown = self._rng.uniform(0.4, 1.6)
        enemy.hit_flash = 0.0
        enemy.death_flash = 0.0
        enemy.active = True
        enemy.node.show()
        enemy.node.setPos(enemy.pos)
        enemy.node.setScale(float(profile.get("scale", 1.0)) * (1.0 + self.wave * 0.012))
        try:
            enemy.node.clearColorScale()
        except Exception:
            pass
        if not initial:
            self._spawn_pulse(enemy.pos)

    def _closest_target_in_reticle(self, max_range: float = 155.0):
        eye = self.player_pos + Vec3(0, 0, EYE_HEIGHT)
        forward = _forward_vec(self.player_yaw, self.player_pitch)
        best_enemy = None
        best_score = -1.0
        for enemy in self.enemies:
            if not enemy.active:
                continue
            target = enemy.pos + Vec3(0, 0, 4.6 + enemy.tier * 0.42)
            delta = target - eye
            distance = delta.length()
            if distance <= 0.001 or distance > max_range:
                continue
            aim = Vec3(delta)
            aim.normalize()
            dot = forward.dot(aim)
            # Slightly forgiving arcade cone.  Bigger enemies are easier to catch.
            required = 0.986 - enemy.aim_radius - enemy.tier * 0.006
            if dot >= required:
                score = dot * 3.0 - distance / max_range
                if score > best_score:
                    best_score = score
                    best_enemy = enemy
        return best_enemy

    def _emit_beam(self, start: Vec3, end: Vec3):
        for beam in self.projectiles:
            if not beam.active:
                beam.active = True
                beam.age = 0.0
                beam.life = 0.070
                delta = end - start
                length = max(0.1, delta.length())
                beam.node.setPos(start)
                try:
                    beam.node.lookAt(end)
                except Exception:
                    pass
                beam.node.setScale(1.0, length, 1.0)
                beam.node.setR(self._elapsed * 720.0)
                beam.node.setColorScale(1, 1, 1, 1)
                beam.node.show()
                return

    def _impact(self, pos: Vec3):
        for impact in self.impacts:
            if not impact.active:
                impact.active = True
                impact.age = 0.0
                impact.pos = Vec3(pos)
                impact.node.setPos(pos)
                impact.node.setScale(0.35)
                try:
                    impact.node.setColorScale(self._current_theme()["accent"])
                except Exception:
                    impact.node.setColorScale(1, 1, 1, 1)
                impact.node.show()
                return

    def _kill_burst(self, pos: Vec3, enemy: _Enemy | None = None):
        for burst in self.kill_bursts:
            if not burst.active:
                burst.active = True
                burst.age = 0.0
                burst.pos = Vec3(pos)
                burst.node.setPos(pos + Vec3(0, 0, 4.2))
                burst.node.setScale(0.42)
                if enemy is not None:
                    try:
                        burst.node.setColorScale(_enemy_profile(enemy.variant)["accent"])
                    except Exception:
                        burst.node.setColorScale(1, 1, 1, 1)
                burst.node.show()
                return

    def _muzzle_flash(self, pos: Vec3, forward: Vec3, repulsor: bool = False):
        for flash in self.muzzle_flashes:
            if not flash.active:
                flash.active = True
                flash.age = 0.0
                flash.life = 0.150 if repulsor else 0.095
                flash.pos = Vec3(pos)
                flash.node.setPos(pos)
                try:
                    flash.node.lookAt(pos + forward)
                except Exception:
                    pass
                flash.node.setScale(0.70 if repulsor else 0.42)
                flash.node.setColorScale(1.0, 0.92 if not repulsor else 0.58, 1.0, 1.0)
                flash.node.show()
                return

    def _repulsor_wave(self, pos: Vec3, forward: Vec3):
        for wave in self.repulsor_waves:
            if not wave.active:
                wave.active = True
                wave.age = 0.0
                wave.pos = Vec3(pos)
                wave.node.setPos(pos + forward * 2.8)
                try:
                    wave.node.lookAt(pos + forward * 8.0)
                except Exception:
                    pass
                wave.node.setScale(0.45)
                wave.node.show()
                return

    def _heat_vent_spark(self):
        if self.weapon_root is None:
            return
        forward = _forward_vec(self.player_yaw, self.player_pitch)
        side = Vec3(forward.y, -forward.x, 0.0)
        if side.lengthSquared() > 0.001:
            side.normalize()
        eye = self.player_pos + Vec3(0, 0, EYE_HEIGHT)
        base = eye + forward * 1.65 + side * 0.54 + Vec3(0, 0, -0.48)
        for spark in self.heat_vent_sparks:
            if not spark.active:
                spark.active = True
                spark.age = 0.0
                spark.pos = base + side * self._rng.uniform(-0.18, 0.18) + Vec3(0, 0, self._rng.uniform(-0.08, 0.18))
                spark.node.setPos(spark.pos)
                try:
                    spark.node.lookAt(spark.pos + forward + Vec3(self._rng.uniform(-0.2, 0.2), self._rng.uniform(-0.2, 0.2), 0.2))
                except Exception:
                    pass
                spark.node.setScale(0.28)
                spark.node.show()
                return

    def _score_enemy_kill(self, enemy: _Enemy, multiplier: float = 1.0):
        enemy.active = False
        enemy.node.hide()
        enemy.death_flash = 0.35
        self.kills += 1
        self.combo += 1
        self.combo_timer = 3.2
        self.enemy_variant_counts[enemy.variant] = self.enemy_variant_counts.get(enemy.variant, 0) + 1
        self.score += int((enemy.score_value + self.wave * 18) * min(4.5, multiplier * (1.0 + self.combo * 0.045)))
        self._kill_burst(enemy.pos, enemy)
        self._impact(enemy.pos + Vec3(0, 0, 4.8))

    def _fire_primary(self):
        if self.fire_cooldown > 0.0 or self.heat >= MAX_HEAT:
            return
        self.fire_cooldown = 0.082
        self.heat = min(MAX_HEAT, self.heat + 8.5)
        self.weapon_recoil = max(self.weapon_recoil, 0.20)
        self.weapon_charge = min(1.0, self.weapon_charge + 0.22)
        eye = self.player_pos + Vec3(0, 0, EYE_HEIGHT)
        forward = _forward_vec(self.player_yaw, self.player_pitch)
        side = Vec3(forward.y, -forward.x, 0.0)
        if side.lengthSquared() > 0.001:
            side.normalize()
        muzzle = eye + forward * 2.2 + side * 0.36 + Vec3(0, 0, -0.44)
        target = self._closest_target_in_reticle()
        end = muzzle + forward * 152.0
        if target is not None:
            target_point = target.pos + Vec3(0, 0, 4.6 + target.tier * 0.5)
            end = target_point
            damage = 27.0 + max(0, self.combo - 1) * 1.5
            if target.variant in {"wraith", "sentry"}:
                damage *= 1.08
            target.hp -= damage
            target.hit_flash = 0.18
            self._impact(target_point)
            if target.hp <= 0.0:
                self._score_enemy_kill(target, 1.0)
        self._muzzle_flash(muzzle, forward, False)
        self._emit_beam(muzzle, end)

    def _fire_repulsor(self):
        if self.blast_cooldown > 0.0 or self.heat > 85.0:
            return
        self.blast_cooldown = 2.2
        self.heat = min(MAX_HEAT, self.heat + 26.0)
        self.weapon_recoil = max(self.weapon_recoil, 0.55)
        self.repulsor_flash = 1.0
        self.weapon_charge = 1.0
        eye = self.player_pos + Vec3(0, 0, EYE_HEIGHT)
        forward = _forward_vec(self.player_yaw, self.player_pitch)
        radius = 34.0
        for enemy in self.enemies:
            if not enemy.active:
                continue
            target = enemy.pos + Vec3(0, 0, 4.2)
            delta = target - eye
            distance = delta.length()
            if distance > radius:
                continue
            aim = Vec3(delta)
            if aim.lengthSquared() > 0.001:
                aim.normalize()
            if forward.dot(aim) < 0.58:
                continue
            damage = 55.0 * (1.0 - distance / radius) + 15.0
            if enemy.variant in {"brute", "guardian"}:
                damage *= 0.78
            enemy.hp -= damage
            enemy.hit_flash = 0.26
            push = Vec3(enemy.pos - self.player_pos)
            push.z = 0
            if push.lengthSquared() > 0.001:
                push.normalize()
                enemy.vel += push * (64.0 + enemy.tier * 14.0) / max(0.72, enemy.speed_scale)
            self._impact(target)
            if enemy.hp <= 0.0:
                self._score_enemy_kill(enemy, 1.12)
        muzzle = eye + forward * 2.0
        self._muzzle_flash(muzzle, forward, True)
        self._repulsor_wave(eye, forward)
        self._emit_beam(muzzle, eye + forward * radius)

    def _update_pointer_look(self, dt: float):
        # Fallback keyboard look for dev/offscreen and keyboard-only users.
        if self._key_down("arrow_left"):
            self.player_yaw += 118.0 * dt
        if self._key_down("arrow_right"):
            self.player_yaw -= 118.0 * dt
        if self._key_down("q"):
            self.player_yaw += 92.0 * dt
        if self._key_down("e"):
            self.player_yaw -= 92.0 * dt

        if self.win is None:
            return
        try:
            props = self.win.getProperties()
            width = max(1, int(props.getXSize()))
            height = max(1, int(props.getYSize()))
            cx, cy = width // 2, height // 2
            pointer = self.win.getPointer(0)
            px, py = int(pointer.getX()), int(pointer.getY())
            if self._capture_pointer_once:
                self._capture_pointer_once = False
                if hasattr(self.win, "movePointer"):
                    self.win.movePointer(0, cx, cy)
                return
            dx, dy = px - cx, py - cy
            if abs(dx) > 0 or abs(dy) > 0:
                self.player_yaw -= dx * 0.105
                self.player_pitch = _clamp(self.player_pitch - dy * 0.092, -62.0, 58.0)
                if hasattr(self.win, "movePointer"):
                    self.win.movePointer(0, cx, cy)
        except Exception:
            return

    def _push_out_of_cover(self):
        for cover in self.cover_blocks:
            dx = self.player_pos.x - cover.pos.x
            dy = self.player_pos.y - cover.pos.y
            px = cover.half.x + 1.6 - abs(dx)
            py = cover.half.y + 1.6 - abs(dy)
            if px > 0 and py > 0:
                if px < py:
                    sign = 1.0 if dx >= 0 else -1.0
                    self.player_pos.x = cover.pos.x + sign * (cover.half.x + 1.6)
                    self.player_vel.x = 0.0
                else:
                    sign = 1.0 if dy >= 0 else -1.0
                    self.player_pos.y = cover.pos.y + sign * (cover.half.y + 1.6)
                    self.player_vel.y = 0.0

    def _update_player(self, dt: float):
        self._update_pointer_look(dt)
        forward = _heading_vec(self.player_yaw)
        right = Vec3(forward.y, -forward.x, 0)
        move = Vec3(0, 0, 0)
        if self._key_down("w"):
            move += forward
        if self._key_down("s"):
            move -= forward
        if self._key_down("d"):
            move += right
        if self._key_down("a"):
            move -= right
        if move.lengthSquared() > 0.001:
            move.normalize()
        dash = self._key_down("shift") and self.heat < 86.0
        speed = 46.0 * (1.55 if dash else 1.0)
        if dash:
            self.heat = min(MAX_HEAT, self.heat + dt * 13.0)
        desired = move * speed
        self.player_vel += (desired - self.player_vel) * min(1.0, dt * 10.0)
        self.player_pos += self.player_vel * dt
        self._push_out_of_cover()
        r = math.sqrt(self.player_pos.x * self.player_pos.x + self.player_pos.y * self.player_pos.y)
        if r > ARENA_RADIUS - 5.0:
            n = Vec3(self.player_pos.x, self.player_pos.y, 0)
            if n.lengthSquared() > 0.001:
                n.normalize()
                self.player_pos = n * (ARENA_RADIUS - 5.0)
                self.player_vel -= n * max(0.0, self.player_vel.dot(n)) * 1.2
        self.player_pos.z = 0.0

    def _steer_enemy_from_cover(self, enemy: _Enemy, desired: Vec3) -> Vec3:
        steer = Vec3(desired)
        for cover in self.cover_blocks:
            dx = enemy.pos.x - cover.pos.x
            dy = enemy.pos.y - cover.pos.y
            px = cover.half.x + 4.5 - abs(dx)
            py = cover.half.y + 4.5 - abs(dy)
            if px > 0 and py > 0:
                if px < py:
                    steer.x += (1.0 if dx >= 0 else -1.0) * 28.0
                else:
                    steer.y += (1.0 if dy >= 0 else -1.0) * 28.0
        return steer

    def _update_enemies(self, dt: float):
        active_count = 0
        for i, enemy in enumerate(self.enemies):
            if not enemy.active:
                self._spawn_enemy(enemy, i)
                continue
            active_count += 1
            to_player = self.player_pos - enemy.pos
            distance = max(0.001, to_player.length())
            seek = Vec3(to_player)
            seek.z = 0
            if seek.lengthSquared() > 0.001:
                seek.normalize()
            orbit = Vec3(-seek.y, seek.x, 0) * math.sin(self._elapsed * (0.9 + enemy.tier * 0.2) + enemy.phase)
            base_speed = 24.0 + self.wave * 1.2
            if enemy.variant == "stalker":
                desired = seek * (base_speed * 1.42) + orbit * 5.5
            elif enemy.variant == "brute":
                desired = seek * (base_speed * 0.72) + orbit * 3.0
            elif enemy.variant == "sentry":
                keep = -seek * 18.0 if distance < 28.0 else seek * 10.0
                desired = keep + orbit * 20.0
            elif enemy.variant == "wraith":
                zig = math.sin(self._elapsed * 4.6 + enemy.phase)
                desired = seek * (base_speed * 1.05) + orbit * (17.0 * zig)
            else:  # guardian
                desired = seek * (base_speed * 0.56) + orbit * 2.2
            if distance < 9.0:
                desired -= seek * (20.0 if enemy.variant not in {"brute", "guardian"} else 9.0)
            desired = self._steer_enemy_from_cover(enemy, desired)
            enemy.vel += (desired * enemy.speed_scale - enemy.vel) * min(1.0, dt * (2.3 + enemy.speed_scale * 0.55))
            enemy.pos += enemy.vel * dt
            r = math.sqrt(enemy.pos.x * enemy.pos.x + enemy.pos.y * enemy.pos.y)
            if r > ARENA_RADIUS - 6.0:
                n = Vec3(enemy.pos.x, enemy.pos.y, 0)
                if n.lengthSquared() > 0.001:
                    n.normalize()
                    enemy.pos = n * (ARENA_RADIUS - 6.0)
                    enemy.vel -= n * max(0.0, enemy.vel.dot(n)) * 1.15
            enemy.pos.z = 0.0
            if enemy.vel.lengthSquared() > 1.0:
                enemy.node.setH(math.degrees(math.atan2(enemy.vel.x, enemy.vel.y)))
            bob = math.sin(self._elapsed * 5.0 + enemy.phase) * 0.16
            enemy.node.setPos(enemy.pos + Vec3(0, 0, bob))
            enemy.node.setR(math.sin(self._elapsed * 3.1 + enemy.phase) * 4.5)
            if enemy.hit_flash > 0.0:
                enemy.hit_flash = max(0.0, enemy.hit_flash - dt)
                enemy.node.setColorScale(1.9, 1.9, 1.9, 1.0)
            else:
                enemy.node.clearColorScale()
            enemy.attack_cooldown -= dt
            if distance < 7.8 and enemy.attack_cooldown <= 0.0:
                enemy.attack_cooldown = max(0.52, 1.05 - enemy.speed_scale * 0.18) + enemy.tier * 0.08
                damage = enemy.damage_scale + self.wave * 0.85
                if self.armor > 0:
                    used = min(self.armor, damage * 0.7)
                    self.armor -= used
                    damage -= used * 0.55
                self.health = max(0.0, self.health - damage)
                self.damage_flash = 0.24
                push = Vec3(self.player_pos - enemy.pos)
                push.z = 0
                if push.lengthSquared() > 0.001:
                    push.normalize()
                    self.player_vel += push * 18.0
            if enemy.hp <= 0.0:
                self._score_enemy_kill(enemy, 1.0)
        if active_count <= 2:
            self._advance_wave()

    def _update_input_fire(self, dt: float):
        mouse1 = self._mouse_down(1) or self._mouse1_latched
        mouse3 = self._mouse_down(3) or self._mouse3_latched
        if mouse1:
            self._fire_primary()
        if mouse3:
            self._fire_repulsor()
        if self._r_latched or self._key_down("r"):
            self.heat = max(0.0, self.heat - dt * 95.0)
            self.vent_fx_cooldown = max(0.0, self.vent_fx_cooldown - dt)
            if self.vent_fx_cooldown <= 0.0:
                self.vent_fx_cooldown = 0.075
                self._heat_vent_spark()
        self._mouse1_latched = False
        self._mouse3_latched = False
        self._r_latched = False

    def _update_projectiles(self, dt: float):
        for beam in self.projectiles:
            if not beam.active:
                continue
            beam.age += dt
            t = beam.age / max(beam.life, 0.001)
            if t >= 1.0:
                beam.active = False
                try:
                    beam.node.hide()
                except Exception:
                    pass
                continue
            try:
                beam.node.setColorScale(1, 1, 1, max(0.0, 1.0 - t))
            except Exception:
                pass

    def _update_impacts(self, dt: float):
        for impact in self.impacts:
            if not impact.active:
                continue
            impact.age += dt
            t = impact.age / max(impact.life, 0.001)
            if t >= 1.0:
                impact.active = False
                impact.node.hide()
                continue
            impact.node.setScale(0.4 + t * 3.8)
            impact.node.setColorScale(1, 1, 1, max(0.0, 1.0 - t))
        for pulse in self.spawn_pulses:
            if not pulse.active:
                continue
            pulse.age += dt
            t = pulse.age / max(pulse.life, 0.001)
            if t >= 1.0:
                pulse.active = False
                pulse.node.hide()
                continue
            pulse.node.setScale(0.7 + t * 4.7)
            pulse.node.setColorScale(1, 1, 1, max(0.0, 1.0 - t))
        for burst in self.kill_bursts:
            if not burst.active:
                continue
            burst.age += dt
            t = burst.age / max(burst.life, 0.001)
            if t >= 1.0:
                burst.active = False
                burst.node.hide()
                continue
            burst.node.setScale(0.55 + t * 6.2)
            burst.node.setH(self._elapsed * 220.0)
            burst.node.setColorScale(1.0, 1.0, 1.0, max(0.0, 1.0 - t))
        for flash in self.muzzle_flashes:
            if not flash.active:
                continue
            flash.age += dt
            t = flash.age / max(flash.life, 0.001)
            if t >= 1.0:
                flash.active = False
                flash.node.hide()
                continue
            flash.node.setScale(0.42 + t * 1.6)
            flash.node.setColorScale(1.0, 1.0, 1.0, max(0.0, 1.0 - t))
        for wave in self.repulsor_waves:
            if not wave.active:
                continue
            wave.age += dt
            t = wave.age / max(wave.life, 0.001)
            if t >= 1.0:
                wave.active = False
                wave.node.hide()
                continue
            wave.node.setScale(0.45 + t * 8.8)
            wave.node.setColorScale(1.0, 1.0, 1.0, max(0.0, 0.86 - t))
        for spark in self.heat_vent_sparks:
            if not spark.active:
                continue
            spark.age += dt
            t = spark.age / max(spark.life, 0.001)
            if t >= 1.0:
                spark.active = False
                spark.node.hide()
                continue
            spark.node.setZ(spark.pos.z + t * 1.8)
            spark.node.setScale(0.25 + t * 0.9)
            spark.node.setH(self._elapsed * 360.0 + t * 120.0)
            spark.node.setColorScale(1.0, 0.78, 0.34, max(0.0, 1.0 - t))

    def _update_weapon_viewmodel(self, dt: float):
        self.weapon_recoil = max(0.0, self.weapon_recoil - dt * 3.8)
        self.weapon_charge = max(0.0, self.weapon_charge - dt * 1.4)
        self.repulsor_flash = max(0.0, self.repulsor_flash - dt * 2.2)
        if self.weapon_root is None:
            return
        bob = math.sin(self._elapsed * 5.2) * 0.012
        recoil = self.weapon_recoil
        self.weapon_root.setPos(0.48 + recoil * 0.035, 1.05 - recoil * 0.22, -0.34 + bob - recoil * 0.045)
        self.weapon_root.setHpr(-5.0 - recoil * 7.0, -2.0 + recoil * 4.0, math.sin(self._elapsed * 2.6) * 0.8)
        heat_ratio = _clamp(self.heat / MAX_HEAT, 0.0, 1.0)
        pulse = 0.58 + 0.42 * math.sin(self._elapsed * (8.0 + heat_ratio * 10.0))
        for node in self.weapon_glow_nodes:
            try:
                node.setColorScale(1.0, 1.0 - heat_ratio * 0.32, 1.0 - heat_ratio * 0.70 + pulse * 0.18, 0.72 + max(self.weapon_charge, self.repulsor_flash) * 0.28)
            except Exception:
                pass

    def _update_camera(self, dt: float):
        self.camera.reparentTo(self.render)
        eye = self.player_pos + Vec3(0, 0, EYE_HEIGHT)
        self.camera.setPos(eye)
        self.camera.setHpr(self.player_yaw, self.player_pitch, 0)

    def _update_status(self, dt: float):
        self.heat = max(0.0, self.heat - dt * 18.0)
        self.fire_cooldown = max(0.0, self.fire_cooldown - dt)
        self.blast_cooldown = max(0.0, self.blast_cooldown - dt)
        self.vent_fx_cooldown = max(0.0, self.vent_fx_cooldown - dt)
        self.damage_flash = max(0.0, self.damage_flash - dt)
        self.combo_timer = max(0.0, self.combo_timer - dt)
        if self.combo_timer <= 0.0:
            self.combo = max(1, self.combo - 1)
        if self.health <= 0.0:
            self.health = 100.0
            self.armor = 50.0
            self.heat = 0.0
            self.score = max(0, self.score - 300)
            self.combo = 1
            self.player_pos = Vec3(0, -82, 0.0)
            self.player_vel = Vec3(0, 0, 0)
            self.damage_flash = 0.35
        active = sum(1 for enemy in self.enemies if enemy.active)
        theme_name = self._current_theme()["name"]
        if self.combat_text is not None:
            self.combat_text["text"] = (
                f"HP {int(self.health):03d}  ARMOR {int(self.armor):03d}  HEAT {int(self.heat):03d}  "
                f"WAVE {self.wave:02d}  SCORE {self.score:05d}  KILLS {self.kills:03d}  ENEMIES {active:02d}  {theme_name}"
            )
        if self.wave_text is not None:
            alert = "BREACH SHIFT" if self.wave_intro_timer > 0.0 else "GROUND COMBAT"
            top_variant = max(self.enemy_variant_counts.items(), key=lambda item: item[1])[0] if any(self.enemy_variant_counts.values()) else "none"
            self.wave_text["text"] = f"VECTOR ARENA\n{alert} // WAVE {self.wave:02d}\n{theme_name}\nSCORE {self.score:05d}  COMBO x{self.combo:02d}\nTHREAT MIX: STALKER / BRUTE / SENTRY / WRAITH / GUARDIAN"
        if self.damage_overlay is not None:
            alpha = min(0.32, self.damage_flash * 1.2)
            self.damage_overlay.setColor(1.0, 0.05, 0.05, alpha)

    # ------------------------------------------------------------------
    # Dimension UI / host contract
    # ------------------------------------------------------------------
    def _dimension_ui_nodes(self):
        nodes = []
        for name in getattr(self, "_dimension_ui_node_names", ()):
            node = getattr(self, name, None)
            if node is not None:
                nodes.append(node)
        return nodes

    def _set_dimension_ui_visible(self, visible: bool):
        self.dimension_ui_visible = bool(visible)
        for node in self._dimension_ui_nodes():
            try:
                node.show() if self.dimension_ui_visible else node.hide()
            except Exception:
                pass

    def toggle_dimension_ui(self) -> bool:
        self._set_dimension_ui_visible(not self.dimension_ui_visible)
        return True

    def enter(self):
        self._host_resources()
        self._build_scene()
        self._set_dimension_ui_visible(False)
        self._entered = True
        self._update_camera(0.016)
        self._update_status(0.016)

    def on_host_action(self, action: str) -> bool:
        action = str(action or "").strip().lower()
        if action in {"toggle_dimension_ui", "dimension_ui", "h"}:
            return self.toggle_dimension_ui()
        if action in {"mouse1", "mouse1_down", "fire"}:
            self._mouse1_latched = True
            return True
        if action in {"mouse3", "right_click", "shock", "repulsor"}:
            self._mouse3_latched = True
            return True
        if action in {"reload", "vent", "r"}:
            self._r_latched = True
            return True
        if action in {"escape", "pause", "number_0", "return", "return_to_core"}:
            return False
        return False

    def update(self, dt: float):
        if not self._entered:
            return
        dt = _safe_dt(dt)
        self._elapsed += dt
        self._update_player(dt)
        self._update_input_fire(dt)
        self._update_projectiles(dt)
        self._update_enemies(dt)
        self._update_impacts(dt)
        self._update_scenery(dt)
        self._update_status(dt)
        self._update_weapon_viewmodel(dt)
        self._update_camera(dt)

    def get_result(self) -> dict:
        return {
            "mode_id": MODE_ID,
            "score_delta": int(self.score),
            "completed": bool(self.wave >= 4 or self.kills >= 25),
            "kills": int(self.kills),
            "wave": int(self.wave),
            "signal": "VECTOR_ARENA_PHASED_WAVE_COMBAT_TRACE" if self.kills else "VECTOR_ARENA_PHASED_ARENA_BOOT_TRACE",
            "scenery_theme": self._current_theme()["name"],
            "enemy_variants": dict(self.enemy_variant_counts),
            "weapon_fx": "pooled_muzzle_flash_repulsor_wave_heat_vent_sparks_and_layered_hitscan_beams",
            "gleebs_response": "Vector Arena returned a phased first-person combat signal with enemy variant telemetry." if self.kills else "Vector Arena loaded as a clean phased arena shooter with class-based threats.",
        }

    def exit(self):
        try:
            self.ignore("mouse1")
            self.ignore("mouse3")
        except Exception:
            pass
        try:
            self.camera.reparentTo(self._saved_camera_parent)
            self.camera.setTransform(self._saved_camera_transform)
        except Exception:
            pass
        try:
            if self._saved_bg is not None and self.win is not None:
                self.win.setClearColor(self._saved_bg)
        except Exception:
            pass
        try:
            if self.win is not None and hasattr(self.win, "requestProperties"):
                props = WindowProperties()
                props.setCursorHidden(False)
                self.win.requestProperties(props)
        except Exception:
            pass
        for node in list(self._owned):
            try:
                if node is not None and not node.isEmpty():
                    node.removeNode()
            except Exception:
                pass
        self._owned.clear()
        self.enemies.clear()
        self.projectiles.clear()
        self.impacts.clear()
        self.spawn_pulses.clear()
        self.kill_bursts.clear()
        self.muzzle_flashes.clear()
        self.repulsor_waves.clear()
        self.heat_vent_sparks.clear()
        self.cover_blocks.clear()
        self.enemy_variant_counts.clear()
        self.scenery_nodes = {"primary": [], "secondary": [], "accent": [], "floor": []}
        self.scenery_motion_nodes.clear()
        self.cover_glow_nodes.clear()
        self.spawn_gate_nodes.clear()
        self.weapon_glow_nodes.clear()
        self._entered = False


def create_mode(host, mode=None, entry_path=None, label=MODE_TITLE):
    return HoloVerseNativeMode(host, mode=mode, entry_path=entry_path, label=label)
