from __future__ import annotations

import math
from dataclasses import dataclass

from panda3d.core import LVector3f, NodePath

from .constants import (
    DRONE_ACCEL,
    DRONE_ASCEND_SPEED,
    DRONE_DECEL,
    DRONE_MOVE_SPEED,
    DRONE_SPRINT_MULTIPLIER,
    PLAYER_EYE_HEIGHT,
)


@dataclass
class InputState:
    forward: bool = False
    backward: bool = False
    left: bool = False
    right: bool = False
    ascend: bool = False
    descend: bool = False
    sprint: bool = False
    turn_left: bool = False
    turn_right: bool = False
    look_up: bool = False
    look_down: bool = False


def _approach(current: float, target: float, delta: float) -> float:
    if current < target:
        return min(target, current + delta)
    return max(target, current - delta)

DRONE_COLLISION_RADIUS = 0.42
DRONE_COLLISION_BOTTOM = 0.26
DRONE_COLLISION_TOP = 0.30
DRONE_MIN_ALTITUDE = DRONE_COLLISION_BOTTOM + 0.06


def _add_block(
    cube_template: NodePath,
    parent: NodePath,
    name: str,
    pos: tuple[float, float, float],
    scale: tuple[float, float, float],
    color: tuple[float, float, float, float],
    hpr: tuple[float, float, float] = (0.0, 0.0, 0.0),
    *,
    light_off: bool = False,
) -> NodePath:
    pivot = parent.attachNewNode(name)
    pivot.setPos(*pos)
    pivot.setHpr(*hpr)
    mesh = cube_template.copyTo(pivot)
    mesh.setScale(*scale)
    mesh.setColorScale(*color)
    if light_off:
        mesh.setLightOff()
    return pivot


def _collect_palette_meshes(root: NodePath) -> list[tuple[NodePath, tuple[float, float, float, float]]]:
    palette_meshes = []
    for mesh_np in root.findAllMatches('**/+GeomNode'):
        scale = mesh_np.getColorScale()
        palette_meshes.append((mesh_np, (float(scale.x), float(scale.y), float(scale.z), float(scale.w))))
    return palette_meshes


def build_robot_character(parent: NodePath, cube_template: NodePath) -> dict[str, NodePath | list]:
    rig = parent.attachNewNode('robot_rig')

    steel = (0.74, 0.74, 0.76, 1.0)
    dark_steel = (0.42, 0.42, 0.46, 1.0)
    red = (0.78, 0.20, 0.18, 1.0)
    red_dark = (0.55, 0.12, 0.11, 1.0)
    red_gloss = (0.88, 0.33, 0.28, 1.0)
    ivory = (0.93, 0.93, 0.95, 1.0)
    yellow = (0.98, 0.82, 0.16, 1.0)

    pelvis = rig.attachNewNode('pelvis')
    pelvis.setPos(0.0, 0.0, 0.98)
    _add_block(cube_template, pelvis, 'pelvis_block', (0.0, 0.0, 0.0), (0.30, 0.18, 0.24), red_dark)

    torso = rig.attachNewNode('torso')
    torso.setPos(0.0, 0.0, 1.46)
    _add_block(cube_template, torso, 'torso_core', (0.0, 0.0, 0.0), (0.56, 0.24, 0.68), red)
    _add_block(cube_template, torso, 'torso_bevel_top', (0.0, 0.0, 0.30), (0.50, 0.22, 0.10), red_gloss)
    _add_block(cube_template, torso, 'torso_bevel_bottom', (0.0, 0.0, -0.28), (0.44, 0.20, 0.08), red_dark)
    _add_block(cube_template, torso, 'belly', (0.0, 0.15, -0.02), (0.34, 0.10, 0.34), ivory)
    _add_block(cube_template, torso, 'left_shoulder_cap', (-0.39, 0.0, 0.22), (0.10, 0.10, 0.10), dark_steel)
    _add_block(cube_template, torso, 'right_shoulder_cap', (0.39, 0.0, 0.22), (0.10, 0.10, 0.10), dark_steel)

    chest = rig.attachNewNode('chest')
    chest.setPos(0.0, 0.0, 1.86)
    _add_block(cube_template, chest, 'chest_spine', (0.0, 0.0, 0.00), (0.18, 0.10, 0.18), dark_steel)
    _add_block(cube_template, chest, 'neck_socket', (0.0, 0.0, 0.20), (0.10, 0.10, 0.08), dark_steel)

    head_pivot = rig.attachNewNode('head_pivot')
    head_pivot.setPos(0.0, 0.0, 2.30)
    _add_block(cube_template, head_pivot, 'head_core', (0.0, 0.0, 0.02), (0.40, 0.28, 0.34), red)
    _add_block(cube_template, head_pivot, 'head_forehead', (0.0, 0.03, 0.12), (0.34, 0.20, 0.10), red_gloss)
    _add_block(cube_template, head_pivot, 'head_back', (0.0, -0.03, 0.00), (0.36, 0.18, 0.24), red_dark)
    _add_block(cube_template, head_pivot, 'antenna_l', (-0.23, 0.0, 0.42), (0.04, 0.04, 0.28), red_gloss)
    _add_block(cube_template, head_pivot, 'antenna_r', (0.23, 0.0, 0.42), (0.04, 0.04, 0.28), red_gloss)
    _add_block(cube_template, head_pivot, 'brow_l', (-0.12, 0.18, 0.18), (0.10, 0.05, 0.02), steel, (0.0, 0.0, 18.0))
    _add_block(cube_template, head_pivot, 'brow_r', (0.12, 0.18, 0.18), (0.10, 0.05, 0.02), steel, (0.0, 0.0, -18.0))
    _add_block(cube_template, head_pivot, 'eye_l', (-0.11, 0.19, 0.08), (0.08, 0.04, 0.08), yellow, light_off=True)
    _add_block(cube_template, head_pivot, 'eye_r', (0.11, 0.19, 0.08), (0.08, 0.04, 0.08), yellow, light_off=True)
    _add_block(cube_template, head_pivot, 'jaw_center', (0.0, 0.08, -0.16), (0.30, 0.16, 0.16), steel)
    _add_block(cube_template, head_pivot, 'jaw_left', (-0.16, 0.08, -0.12), (0.08, 0.16, 0.10), steel)
    _add_block(cube_template, head_pivot, 'jaw_right', (0.16, 0.08, -0.12), (0.08, 0.16, 0.10), steel)

    shoulder_l = rig.attachNewNode('shoulder_l')
    shoulder_l.setPos(-0.47, 0.0, 1.84)
    _add_block(cube_template, shoulder_l, 'upper_arm_l', (0.0, 0.0, -0.22), (0.08, 0.08, 0.34), dark_steel)
    _add_block(cube_template, shoulder_l, 'arm_guard_l', (-0.02, 0.06, -0.34), (0.18, 0.12, 0.34), red, (0.0, 0.0, -8.0))
    forearm_l = shoulder_l.attachNewNode('forearm_l')
    forearm_l.setPos(0.0, 0.0, -0.48)
    _add_block(cube_template, forearm_l, 'forearm_rod_l', (0.0, 0.0, -0.12), (0.07, 0.07, 0.26), steel)
    _add_block(cube_template, forearm_l, 'wrist_shell_l', (0.0, 0.05, -0.26), (0.13, 0.10, 0.12), red_dark)

    shoulder_r = rig.attachNewNode('shoulder_r')
    shoulder_r.setPos(0.47, 0.0, 1.84)
    _add_block(cube_template, shoulder_r, 'upper_arm_r', (0.0, 0.0, -0.22), (0.08, 0.08, 0.34), dark_steel)
    _add_block(cube_template, shoulder_r, 'arm_guard_r', (0.02, 0.06, -0.34), (0.18, 0.12, 0.34), red, (0.0, 0.0, 8.0))
    forearm_r = shoulder_r.attachNewNode('forearm_r')
    forearm_r.setPos(0.0, 0.0, -0.48)
    _add_block(cube_template, forearm_r, 'forearm_rod_r', (0.0, 0.0, -0.12), (0.07, 0.07, 0.26), steel)
    _add_block(cube_template, forearm_r, 'wrist_shell_r', (0.0, 0.05, -0.26), (0.13, 0.10, 0.12), red_dark)

    hip_l = rig.attachNewNode('hip_l')
    hip_l.setPos(-0.14, 0.0, 0.92)
    _add_block(cube_template, hip_l, 'thigh_l', (0.0, 0.0, -0.10), (0.06, 0.06, 0.42), steel)
    _add_block(cube_template, hip_l, 'thigh_shell_l', (0.0, 0.03, -0.34), (0.12, 0.10, 0.30), red_gloss)
    shin_l = hip_l.attachNewNode('shin_l')
    shin_l.setPos(0.0, 0.0, -0.52)
    _add_block(cube_template, shin_l, 'shin_rod_l', (0.0, 0.0, -0.10), (0.06, 0.06, 0.34), steel)
    _add_block(cube_template, shin_l, 'boot_l', (0.0, 0.03, -0.34), (0.14, 0.12, 0.30), red)

    hip_r = rig.attachNewNode('hip_r')
    hip_r.setPos(0.14, 0.0, 0.92)
    _add_block(cube_template, hip_r, 'thigh_r', (0.0, 0.0, -0.10), (0.06, 0.06, 0.42), steel)
    _add_block(cube_template, hip_r, 'thigh_shell_r', (0.0, 0.03, -0.34), (0.12, 0.10, 0.30), red_gloss)
    shin_r = hip_r.attachNewNode('shin_r')
    shin_r.setPos(0.0, 0.0, -0.52)
    _add_block(cube_template, shin_r, 'shin_rod_r', (0.0, 0.0, -0.10), (0.06, 0.06, 0.34), steel)
    _add_block(cube_template, shin_r, 'boot_r', (0.0, 0.03, -0.34), (0.14, 0.12, 0.30), red)

    return {
        'rig': rig,
        'pelvis': pelvis,
        'torso': torso,
        'chest': chest,
        'head_pivot': head_pivot,
        'shoulder_l': shoulder_l,
        'shoulder_r': shoulder_r,
        'forearm_l': forearm_l,
        'forearm_r': forearm_r,
        'hip_l': hip_l,
        'hip_r': hip_r,
        'shin_l': shin_l,
        'shin_r': shin_r,
        'palette_meshes': _collect_palette_meshes(rig),
    }


def build_human_character(parent: NodePath, cube_template: NodePath, helmet: bool = False, palette: dict | None = None, elf_hat: bool = False) -> dict[str, NodePath | list]:
    rig = parent.attachNewNode('human_rig')

    palette = palette or {}
    skin = palette.get('skin', (0.90, 0.73, 0.61, 1.0))
    hair = palette.get('hair', (0.16, 0.10, 0.08, 1.0))
    shirt = palette.get('shirt', (0.20, 0.56, 0.92, 1.0))
    shirt_dark = palette.get('shirt_dark', (0.11, 0.24, 0.48, 1.0))
    pants = palette.get('pants', (0.18, 0.20, 0.25, 1.0))
    shoes = palette.get('shoes', (0.10, 0.08, 0.08, 1.0))
    helmet_shell = palette.get('helmet_shell', (0.76, 0.82, 0.90, 1.0))
    helmet_dark = palette.get('helmet_dark', (0.24, 0.28, 0.36, 1.0))
    visor = palette.get('visor', (0.18, 0.28, 0.40, 0.84))
    hat_main = palette.get('hat_main', (0.16, 0.62, 0.22, 1.0))
    hat_trim = palette.get('hat_trim', (0.98, 0.98, 0.98, 1.0))

    hips = rig.attachNewNode('hips')
    hips.setPos(0.0, 0.0, 0.96)
    _add_block(cube_template, hips, 'hips_block', (0.0, 0.0, 0.0), (0.28, 0.18, 0.22), pants)

    torso = rig.attachNewNode('torso')
    torso.setPos(0.0, 0.0, 1.42)
    _add_block(cube_template, torso, 'torso_core', (0.0, 0.0, 0.0), (0.46, 0.22, 0.62), shirt)
    _add_block(cube_template, torso, 'torso_lower', (0.0, 0.0, -0.26), (0.42, 0.20, 0.10), shirt_dark)

    chest = rig.attachNewNode('chest')
    chest.setPos(0.0, 0.0, 1.78)
    _add_block(cube_template, chest, 'chest_block', (0.0, 0.0, 0.0), (0.22, 0.10, 0.16), shirt_dark)

    head_pivot = rig.attachNewNode('head_pivot')
    head_pivot.setPos(0.0, 0.0, 2.20)
    _add_block(cube_template, head_pivot, 'head', (0.0, 0.0, 0.0), (0.30, 0.24, 0.34), skin)
    _add_block(cube_template, head_pivot, 'hair_cap', (0.0, -0.01, 0.11), (0.31, 0.25, 0.12), hair)
    _add_block(cube_template, head_pivot, 'hair_back', (0.0, -0.08, 0.02), (0.28, 0.08, 0.22), hair)
    _add_block(cube_template, head_pivot, 'eye_l', (-0.08, 0.15, 0.05), (0.04, 0.03, 0.04), (0.12, 0.12, 0.12, 1.0), light_off=True)
    _add_block(cube_template, head_pivot, 'eye_r', (0.08, 0.15, 0.05), (0.04, 0.03, 0.04), (0.12, 0.12, 0.12, 1.0), light_off=True)
    if helmet:
        _add_block(cube_template, head_pivot, 'helmet_shell', (0.0, -0.01, 0.08), (0.35, 0.28, 0.24), helmet_shell)
        _add_block(cube_template, head_pivot, 'helmet_cap', (0.0, 0.00, 0.25), (0.28, 0.22, 0.08), helmet_shell)
        _add_block(cube_template, head_pivot, 'helmet_back', (0.0, -0.12, 0.04), (0.30, 0.08, 0.20), helmet_dark)
        _add_block(cube_template, head_pivot, 'helmet_jaw', (0.0, 0.08, -0.16), (0.26, 0.10, 0.10), helmet_dark)
        visor_np = _add_block(cube_template, head_pivot, 'helmet_visor', (0.0, 0.17, 0.08), (0.24, 0.03, 0.10), visor, light_off=True)
        visor_np.setTransparency(1)
    elif elf_hat:
        _add_block(cube_template, head_pivot, 'elf_hat_brim', (0.0, 0.00, 0.20), (0.26, 0.18, 0.04), hat_trim)
        hat = head_pivot.attachNewNode('elf_hat')
        hat.setPos(0.0, -0.02, 0.20)
        hat.setP(-14.0)
        _add_block(cube_template, hat, 'elf_hat_base', (0.0, 0.0, 0.14), (0.22, 0.20, 0.18), hat_main)
        _add_block(cube_template, hat, 'elf_hat_mid', (0.0, 0.04, 0.36), (0.16, 0.16, 0.16), hat_main)
        _add_block(cube_template, hat, 'elf_hat_tip', (0.0, 0.10, 0.56), (0.10, 0.10, 0.12), hat_main)
        _add_block(cube_template, hat, 'elf_hat_pom', (0.0, 0.16, 0.72), (0.07, 0.07, 0.07), hat_trim, light_off=True)

    shoulder_l = rig.attachNewNode('shoulder_l')
    shoulder_l.setPos(-0.34, 0.0, 1.74)
    _add_block(cube_template, shoulder_l, 'upper_arm_l', (0.0, 0.0, -0.18), (0.06, 0.06, 0.30), skin)
    forearm_l = shoulder_l.attachNewNode('forearm_l')
    forearm_l.setPos(0.0, 0.0, -0.42)
    _add_block(cube_template, forearm_l, 'forearm_l_block', (0.0, 0.0, -0.12), (0.05, 0.05, 0.22), skin)

    shoulder_r = rig.attachNewNode('shoulder_r')
    shoulder_r.setPos(0.34, 0.0, 1.74)
    _add_block(cube_template, shoulder_r, 'upper_arm_r', (0.0, 0.0, -0.18), (0.06, 0.06, 0.30), skin)
    forearm_r = shoulder_r.attachNewNode('forearm_r')
    forearm_r.setPos(0.0, 0.0, -0.42)
    _add_block(cube_template, forearm_r, 'forearm_r_block', (0.0, 0.0, -0.12), (0.05, 0.05, 0.22), skin)

    hip_l = rig.attachNewNode('hip_l')
    hip_l.setPos(-0.12, 0.0, 0.92)
    _add_block(cube_template, hip_l, 'thigh_l', (0.0, 0.0, -0.12), (0.07, 0.07, 0.40), pants)
    shin_l = hip_l.attachNewNode('shin_l')
    shin_l.setPos(0.0, 0.0, -0.50)
    _add_block(cube_template, shin_l, 'shin_l_block', (0.0, 0.0, -0.10), (0.06, 0.06, 0.34), pants)
    _add_block(cube_template, shin_l, 'shoe_l', (0.0, 0.08, -0.34), (0.10, 0.16, 0.08), shoes)

    hip_r = rig.attachNewNode('hip_r')
    hip_r.setPos(0.12, 0.0, 0.92)
    _add_block(cube_template, hip_r, 'thigh_r', (0.0, 0.0, -0.12), (0.07, 0.07, 0.40), pants)
    shin_r = hip_r.attachNewNode('shin_r')
    shin_r.setPos(0.0, 0.0, -0.50)
    _add_block(cube_template, shin_r, 'shin_r_block', (0.0, 0.0, -0.10), (0.06, 0.06, 0.34), pants)
    _add_block(cube_template, shin_r, 'shoe_r', (0.0, 0.08, -0.34), (0.10, 0.16, 0.08), shoes)

    return {
        'rig': rig,
        'hips': hips,
        'torso': torso,
        'chest': chest,
        'head_pivot': head_pivot,
        'shoulder_l': shoulder_l,
        'shoulder_r': shoulder_r,
        'forearm_l': forearm_l,
        'forearm_r': forearm_r,
        'hip_l': hip_l,
        'hip_r': hip_r,
        'shin_l': shin_l,
        'shin_r': shin_r,
        'palette_meshes': _collect_palette_meshes(rig),
    }


def build_elf_character(parent: NodePath, cube_template: NodePath, variant: int = 0) -> dict[str, NodePath | list]:
    palettes = [
        {
            'shirt': (0.14, 0.58, 0.22, 1.0),
            'shirt_dark': (0.08, 0.34, 0.14, 1.0),
            'pants': (0.62, 0.12, 0.12, 1.0),
            'shoes': (0.22, 0.12, 0.08, 1.0),
            'hat_main': (0.16, 0.62, 0.22, 1.0),
            'hat_trim': (0.98, 0.98, 0.98, 1.0),
        },
        {
            'shirt': (0.70, 0.14, 0.16, 1.0),
            'shirt_dark': (0.42, 0.08, 0.10, 1.0),
            'pants': (0.14, 0.44, 0.18, 1.0),
            'shoes': (0.22, 0.12, 0.08, 1.0),
            'hat_main': (0.70, 0.14, 0.16, 1.0),
            'hat_trim': (0.98, 0.98, 0.98, 1.0),
        },
        {
            'shirt': (0.16, 0.42, 0.76, 1.0),
            'shirt_dark': (0.10, 0.24, 0.48, 1.0),
            'pants': (0.16, 0.56, 0.22, 1.0),
            'shoes': (0.22, 0.12, 0.08, 1.0),
            'hat_main': (0.16, 0.56, 0.22, 1.0),
            'hat_trim': (0.98, 0.98, 0.98, 1.0),
        },
    ]
    palette = palettes[variant % len(palettes)]
    return build_human_character(parent, cube_template, helmet=False, palette=palette, elf_hat=True)


class PlayerController:
    def __init__(self, world, parent: NodePath, cube_template: NodePath):
        self.world = world
        self.root = parent.attachNewNode('player_root')
        self.avatar = self._build_drone(self.root, cube_template)

        self.pos = LVector3f(0.5, 0.5, 8.0)
        self.velocity = LVector3f(0.0, 0.0, 0.0)
        self.visual_yaw = 0.0
        self.visual_pitch = 0.0
        self.hover_time = 0.0
        self.turn_velocity = 0.0
        self.bumped_boundary = False
        self.last_flat_speed = 0.0

    def _build_drone(self, parent: NodePath, cube_template: NodePath) -> dict[str, NodePath | list]:
        rig = parent.attachNewNode('drone_rig')

        shell = (0.74, 0.80, 0.88, 1.0)
        shell_dark = (0.28, 0.32, 0.40, 1.0)
        glow = (0.36, 0.86, 1.0, 1.0)
        glow_warm = (0.96, 0.90, 0.62, 1.0)

        body = rig.attachNewNode('body')
        _add_block(cube_template, body, 'core', (0.0, 0.0, 0.0), (0.34, 0.28, 0.18), shell)
        _add_block(cube_template, body, 'nose', (0.0, 0.18, 0.00), (0.18, 0.12, 0.08), shell_dark)
        _add_block(cube_template, body, 'top', (0.0, 0.0, 0.14), (0.24, 0.20, 0.08), shell_dark)
        _add_block(cube_template, body, 'lens', (0.0, 0.20, -0.02), (0.09, 0.05, 0.09), glow, light_off=True)
        _add_block(cube_template, body, 'center_glow', (0.0, 0.02, -0.03), (0.10, 0.10, 0.10), glow_warm, light_off=True)

        arms = []
        rotors = []
        for idx, (ax, ay) in enumerate(((-0.42, 0.32), (0.42, 0.32), (-0.42, -0.32), (0.42, -0.32))):
            arm = rig.attachNewNode(f'arm_{idx}')
            arm.setPos(ax * 0.52, ay * 0.52, 0.02)
            arm.lookAt(arm, ax, ay, 0.0)
            _add_block(cube_template, arm, 'strut', (0.0, 0.12, 0.0), (0.05, 0.26, 0.04), shell_dark)
            hub = arm.attachNewNode('rotor_hub')
            hub.setPos(0.0, 0.28, 0.03)
            _add_block(cube_template, hub, 'hub_core', (0.0, 0.0, 0.0), (0.11, 0.11, 0.05), shell)
            blade_a = _add_block(cube_template, hub, 'blade_a', (0.0, 0.0, 0.02), (0.48, 0.03, 0.015), glow, light_off=True)
            blade_b = _add_block(cube_template, hub, 'blade_b', (0.0, 0.0, 0.02), (0.03, 0.48, 0.015), glow, light_off=True)
            arms.append(arm)
            rotors.append(hub)
            blade_a.setScale(0.54, 0.03, 0.015)
            blade_b.setScale(0.03, 0.54, 0.015)

        tail = rig.attachNewNode('tail')
        tail.setPos(0.0, -0.28, -0.01)
        _add_block(cube_template, tail, 'tail_fin', (0.0, -0.10, 0.0), (0.12, 0.26, 0.03), shell_dark)
        _add_block(cube_template, tail, 'tail_top', (0.0, -0.08, 0.08), (0.05, 0.12, 0.18), shell_dark)

        return {
            'rig': rig,
            'body': body,
            'tail': tail,
            'rotors': rotors,
            'palette_meshes': _collect_palette_meshes(rig),
        }

    def set_pos(self, x: float, y: float, z: float) -> None:
        self.pos = LVector3f(x, y, z)
        self.velocity = LVector3f(0.0, 0.0, 0.0)
        self.root.setPos(self.pos)

    def get_eye_pos(self) -> LVector3f:
        return self.pos + LVector3f(0.0, 0.08, 0.12)

    def get_camera_anchor_pos(self) -> LVector3f:
        return self.pos + LVector3f(0.0, 0.0, 0.58)

    def get_camera_look_pos(self) -> LVector3f:
        return self.pos + LVector3f(0.0, 0.0, 0.18)

    def get_move_velocity(self) -> LVector3f:
        return LVector3f(self.velocity)

    def set_avatar_visible(self, visible: bool) -> None:
        if visible:
            self.avatar['rig'].show()
        else:
            self.avatar['rig'].hide()

    def set_palette_mode(self, grayscale: bool) -> None:
        for mesh_np, rgba in self.avatar.get('palette_meshes', []):
            r, g, b, a = rgba
            if grayscale:
                gray = r * 0.299 + g * 0.587 + b * 0.114
                mesh_np.setColorScale(gray, gray, gray, a)
            else:
                mesh_np.setColorScale(r, g, b, a)

    def _collides(self, x: float, y: float, z: float) -> bool:
        return self.world.collides_aabb(
            x - DRONE_COLLISION_RADIUS,
            x + DRONE_COLLISION_RADIUS,
            y - DRONE_COLLISION_RADIUS,
            y + DRONE_COLLISION_RADIUS,
            z - DRONE_COLLISION_BOTTOM,
            z + DRONE_COLLISION_TOP,
        )

    def update(self, dt: float, inputs: InputState, camera_yaw_deg: float, camera_pitch_deg: float = 0.0) -> None:
        self.hover_time += dt
        self.bumped_boundary = False

        move_x = 0.0
        move_y = 0.0
        move_z = 0.0
        if inputs.forward:
            move_y += 1.0
        if inputs.backward:
            move_y -= 1.0
        if inputs.left:
            move_x -= 1.0
        if inputs.right:
            move_x += 1.0
        if inputs.ascend:
            move_z += 1.0
        if inputs.descend:
            move_z -= 1.0

        yaw_rad = math.radians(camera_yaw_deg)
        forward_x = math.sin(yaw_rad)
        forward_y = math.cos(yaw_rad)
        right_x = math.cos(yaw_rad)
        right_y = -math.sin(yaw_rad)

        flat_len = math.hypot(move_x, move_y)
        target_x = 0.0
        target_y = 0.0
        if flat_len > 1e-5:
            move_x /= flat_len
            move_y /= flat_len
            target_x = (right_x * move_x + forward_x * move_y) * DRONE_MOVE_SPEED
            target_y = (right_y * move_x + forward_y * move_y) * DRONE_MOVE_SPEED

        target_z = max(-1.0, min(1.0, move_z)) * DRONE_ASCEND_SPEED

        speed_mul = DRONE_SPRINT_MULTIPLIER if inputs.sprint else 1.0
        target_x *= speed_mul
        target_y *= speed_mul
        target_z *= speed_mul

        moving = abs(target_x) + abs(target_y) + abs(target_z) > 1e-4
        accel = DRONE_ACCEL if moving else DRONE_DECEL
        self.velocity.x = _approach(self.velocity.x, target_x, accel * dt)
        self.velocity.y = _approach(self.velocity.y, target_y, accel * dt)
        self.velocity.z = _approach(self.velocity.z, target_z, accel * dt)

        next_pos = LVector3f(self.pos)
        for axis_name in ('x', 'y', 'z'):
            delta = getattr(self.velocity, axis_name) * dt
            if abs(delta) < 1e-6:
                continue
            trial = LVector3f(next_pos)
            setattr(trial, axis_name, getattr(trial, axis_name) + delta)
            if self._collides(trial.x, trial.y, trial.z):
                setattr(self.velocity, axis_name, 0.0)
                continue
            next_pos = trial

        clamped_x, clamped_y = self.world.clamp_to_world_boundary(next_pos.x, next_pos.y, margin=DRONE_COLLISION_RADIUS + 0.20)
        if abs(clamped_x - next_pos.x) > 1e-5:
            next_pos.x = clamped_x
            self.velocity.x = 0.0
            self.bumped_boundary = True
        if abs(clamped_y - next_pos.y) > 1e-5:
            next_pos.y = clamped_y
            self.velocity.y = 0.0
            self.bumped_boundary = True

        self.pos = next_pos
        if self.pos.z < DRONE_MIN_ALTITUDE:
            self.pos.z = DRONE_MIN_ALTITUDE
            self.velocity.z = max(0.0, self.velocity.z)

        flat_speed = math.hypot(self.velocity.x, self.velocity.y)
        self.last_flat_speed = flat_speed
        if flat_speed > 0.01:
            self.visual_yaw = math.degrees(math.atan2(self.velocity.x, self.velocity.y))
        else:
            self.visual_yaw = camera_yaw_deg

        target_pitch = max(-18.0, min(18.0, -camera_pitch_deg * 0.22 - self.velocity.z * 1.3))
        self.visual_pitch = _approach(self.visual_pitch, target_pitch, 120.0 * dt)

        lateral_bias = max(-1.0, min(1.0, (right_x * self.velocity.x + right_y * self.velocity.y) / max(0.001, DRONE_MOVE_SPEED * speed_mul)))
        forward_bias = max(-1.0, min(1.0, (forward_x * self.velocity.x + forward_y * self.velocity.y) / max(0.001, DRONE_MOVE_SPEED * speed_mul)))
        turn_delta = (camera_yaw_deg - self.visual_yaw + 180.0) % 360.0 - 180.0
        self.turn_velocity = _approach(self.turn_velocity, turn_delta * 0.2, 180.0 * dt)
        visual_roll = max(-20.0, min(20.0, -lateral_bias * 14.0 - self.turn_velocity * 0.18))
        visual_pitch = self.visual_pitch + max(-10.0, min(10.0, forward_bias * 8.0))

        hover_bob = math.sin(self.hover_time * 3.5) * 0.06
        self.avatar['rig'].setPos(0.0, 0.0, hover_bob)
        self.avatar['rig'].setHpr(self.visual_yaw, visual_pitch, visual_roll)

        for idx, hub in enumerate(self.avatar['rotors']):
            spin_dir = 1.0 if idx % 2 == 0 else -1.0
            hub.setH((hub.getH() + (900.0 + flat_speed * 45.0) * spin_dir * dt) % 360.0)

        body = self.avatar['body']
        body.setP(math.sin(self.hover_time * 4.8) * 1.8)
        self.root.setPos(self.pos)
