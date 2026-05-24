import math
from random import Random
from typing import Any, Dict, List

from panda3d.core import CardMaker, PNMImage, Texture, TextureStage, TransparencyAttrib, Vec3, Vec4
from direct.task import Task


LEVEL_INDEX = 6
STYLE_ID = 6
STYLE_NAME = "Fractured Virtual World"


# Mirror the launcher constants so this file can be imported cleanly.
CELL = 2.55
MODULE_CELLS = 12
MODULE_SIZE = CELL * MODULE_CELLS
WALL_H = 4.4
DECK_Z = 0.0
DECK = 1


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _seed(mx: int, my: int, salt: int = 0) -> int:
    return ((mx * 73856093) ^ (my * 19349663) ^ (LEVEL_INDEX * 83492791) ^ salt) & 0xFFFFFFFF


def _finish_tex(tex: Texture, clamp_mode: bool = False) -> Texture:
    if hasattr(tex, "setMagfilter"):
        tex.setMagfilter(Texture.FT_nearest)
    if hasattr(tex, "setMinfilter"):
        tex.setMinfilter(Texture.FT_nearest_mipmap_nearest)
    if clamp_mode:
        if hasattr(tex, "setWrapU"):
            tex.setWrapU(Texture.WMClamp)
        if hasattr(tex, "setWrapV"):
            tex.setWrapV(Texture.WMClamp)
    else:
        if hasattr(tex, "setWrapU"):
            tex.setWrapU(Texture.WM_repeat)
        if hasattr(tex, "setWrapV"):
            tex.setWrapV(Texture.WM_repeat)
    if hasattr(tex, "setAnisotropicDegree"):
        tex.setAnisotropicDegree(2)
    return tex


def _make_glitch_texture(name: str, size: int, bg, c1, c2, lines) -> Texture:
    img = PNMImage(size, size, 4)
    for y in range(size):
        for x in range(size):
            scan = 0.025 if (y % 2 == 0) else 0.0
            img.setXelA(
                x,
                y,
                _clamp(bg[0] + scan, 0.0, 1.0),
                _clamp(bg[1] + scan, 0.0, 1.0),
                _clamp(bg[2] + scan, 0.0, 1.0),
                1.0,
            )

    rng = Random(hash(name) & 0xFFFFFFFF)
    for _ in range(size * 5):
        x0 = rng.randrange(0, size)
        y0 = rng.randrange(0, size)
        w = rng.randrange(2, max(3, size // 6))
        h = rng.randrange(1, max(2, size // 10))
        col = c1 if rng.random() < 0.58 else c2
        alpha = rng.uniform(0.58, 1.0)
        for yy in range(y0, min(size, y0 + h)):
            for xx in range(x0, min(size, x0 + w)):
                stripe = 0.12 if (yy % 3 == 0) else 0.0
                img.setXelA(
                    xx,
                    yy,
                    _clamp(col[0] + stripe, 0.0, 1.0),
                    _clamp(col[1] + stripe * 0.5, 0.0, 1.0),
                    _clamp(col[2] + stripe, 0.0, 1.0),
                    alpha,
                )

    for _ in range(size // 4):
        x = rng.randrange(0, size)
        for y in range(size):
            if rng.random() < 0.80:
                img.setXelA(x, y, lines[0], lines[1], lines[2], rng.uniform(0.24, 0.78))

    tex = Texture(name)
    tex.load(img)
    return _finish_tex(tex)


def _make_overlay_texture(name: str, size: int = 256) -> Texture:
    img = PNMImage(size, size, 4)
    rng = Random((hash(name) ^ 0x4A5C11) & 0xFFFFFFFF)
    for y in range(size):
        for x in range(size):
            scan = 0.012 if (y % 2 == 0) else 0.0
            spark = 0.05 if rng.random() < 0.02 else 0.0
            alpha = _clamp(scan + spark, 0.0, 0.22)
            img.setXelA(x, y, 1.0, 1.0, 1.0, alpha)
    tex = Texture(name)
    tex.load(img)
    return _finish_tex(tex, clamp_mode=True)


def get_level_settings(_game=None) -> Dict[str, Any]:
    return {
        "display_name": "Level 6 — Fractured Virtual World",
        "style_name": STYLE_NAME,
        "move_speed_mult": 1.06,
        "static_water_default": True,
        "bg_color": [0.0, 0.0, 0.0, 1.0],
        "fog_color": [0.0, 0.0, 0.0, 1.0],
        "ambient_light": [0.16, 0.16, 0.18, 1.0],
        "sun_light": [0.18, 0.65, 0.92, 1.0],
        "fill_light": [0.52, 0.10, 0.72, 1.0],
        "lift_light": [0.10, 0.16, 0.22, 1.0],
        "dark_bg_color": [0.0, 0.0, 0.0, 1.0],
        "dark_fog_color": [0.0, 0.0, 0.0, 1.0],
        "dark_ambient_light": [0.06, 0.06, 0.07, 1.0],
        "dark_sun_light": [0.06, 0.16, 0.22, 1.0],
        "dark_fill_light": [0.16, 0.03, 0.22, 1.0],
        "dark_lift_light": [0.05, 0.06, 0.08, 1.0],
        "fog_start": 1.6,
        "fog_end": 15.5,
        "dark_fog_start": 0.9,
        "dark_fog_end": 8.8,
        "weapon_color_scale": [0.82, 0.90, 1.0, 1.0],
        "weapon_indicator_tint": [0.74, 0.90, 1.0, 1.0],
        "weapon_pulse_strength": 0.04,
    }


def _ensure_state(game) -> Dict[str, Any]:
    state = getattr(game, "level_runtime_state", None)
    if state is None:
        game.level_runtime_state = {}
        state = game.level_runtime_state
    level_state = state.setdefault("level6", {})
    if "textures" not in level_state:
        level_state["textures"] = {
            "floor": _make_glitch_texture(
                "level6_floor", 128,
                (0.02, 0.02, 0.03), (0.10, 0.22, 0.30), (0.65, 0.18, 0.76), (0.16, 0.90, 1.00)
            ),
            "wall": _make_glitch_texture(
                "level6_wall", 128,
                (0.01, 0.01, 0.02), (0.06, 0.08, 0.15), (0.48, 0.10, 0.70), (0.28, 0.95, 1.00)
            ),
            "shard": _make_glitch_texture(
                "level6_shard", 64,
                (0.02, 0.01, 0.03), (0.12, 0.08, 0.18), (0.75, 0.25, 0.90), (0.10, 0.95, 0.95)
            ),
            "accent": _make_glitch_texture(
                "level6_accent", 64,
                (0.03, 0.01, 0.04), (0.18, 0.06, 0.25), (0.10, 0.95, 1.00), (1.00, 0.20, 0.85)
            ),
            "overlay": _make_overlay_texture("level6_overlay", 256),
        }
    level_state.setdefault("anim_nodes", [])
    level_state.setdefault("projection_nodes", [])
    return level_state


def _register_anim(level_state: Dict[str, Any], np, kind: str, base_pos: Vec3, base_hpr: Vec3, amp: float, phase: float, speed: float) -> None:
    level_state.setdefault("anim_nodes", []).append({
        "node": np,
        "kind": kind,
        "base_pos": Vec3(base_pos),
        "base_hpr": Vec3(base_hpr),
        "amp": float(amp),
        "phase": float(phase),
        "speed": float(speed),
    })


def _register_projection(game, level_state: Dict[str, Any], np, phase: float, pulse: float, color: Vec4) -> None:
    game.pattern_overlays.append((np, phase, pulse, color))
    level_state.setdefault("projection_nodes", []).append(np)


def _install_runtime_task(game) -> None:
    if getattr(game, "_level6_runtime_task_installed", False):
        return

    def _level6_runtime(task):
        if getattr(game, "current_level", None) != LEVEL_INDEX:
            return Task.cont

        level_state = getattr(game, "level_runtime_state", {}).get("level6")
        if not level_state:
            return Task.cont

        t = float(getattr(game, "ambience_t", 0.0))
        alive: List[Dict[str, Any]] = []
        for entry in list(level_state.get("anim_nodes", [])):
            np = entry.get("node")
            if np is None or np.isEmpty():
                continue
            phase = entry["phase"]
            amp = entry["amp"]
            speed = entry["speed"]
            base_pos = entry["base_pos"]
            base_hpr = entry["base_hpr"]
            kind = entry["kind"]

            if kind == "shard":
                jitter = Vec3(
                    math.sin(t * (1.6 + speed) + phase),
                    math.cos(t * (1.2 + speed * 0.7) + phase * 1.13),
                    math.sin(t * (2.1 + speed * 0.9) + phase * 0.77),
                ) * (0.16 + amp * 0.18)
                rot = Vec3(
                    math.sin(t * (28.0 + speed * 7.0) + phase) * (7.0 + amp * 5.0),
                    math.cos(t * (24.0 + speed * 6.0) + phase * 0.6) * (6.0 + amp * 4.0),
                    math.sin(t * (31.0 + speed * 5.0) + phase * 0.9) * (8.0 + amp * 6.0),
                )
                np.setPos(base_pos + jitter)
                np.setHpr(base_hpr + rot)
            elif kind == "screen":
                drift = Vec3(0.0, 0.0, math.sin(t * (0.9 + speed * 0.3) + phase) * (0.06 + amp * 0.05))
                rot = Vec3(
                    math.sin(t * 5.0 + phase) * (1.4 + amp),
                    math.cos(t * 4.2 + phase * 1.4) * (1.1 + amp),
                    math.sin(t * 6.5 + phase * 0.7) * (1.7 + amp),
                )
                np.setPos(base_pos + drift)
                np.setHpr(base_hpr + rot)
            else:
                pulse = 0.5 + 0.5 * math.sin(t * (1.1 + speed * 0.2) + phase)
                np.setColorScale(
                    0.72 + pulse * 0.16,
                    0.80 + pulse * 0.10,
                    1.00,
                    0.18 + pulse * 0.06,
                )
            alive.append(entry)
        level_state["anim_nodes"] = alive

        for idx, np in enumerate(list(level_state.get("projection_nodes", []))):
            if np is None or np.isEmpty():
                continue
            stage = TextureStage.getDefault()
            np.setTexOffset(stage, (t * 0.02 + idx * 0.09) % 1.0, (t * 0.11 + idx * 0.13) % 1.0)
        return Task.cont

    game.taskMgr.add(_level6_runtime, "level6_runtime")
    game._level6_runtime_task_installed = True


def on_level_load(game) -> None:
    level_state = _ensure_state(game)
    level_state["anim_nodes"] = []
    level_state["projection_nodes"] = []
    game.return_to_halls_unlocked = False
    game.player_pos = Vec3(MODULE_SIZE * 0.5, MODULE_SIZE * 0.5, 0.0)
    _install_runtime_task(game)


def build_module_data(_game, _mx: int, _my: int):
    # Full DECK grid so movement stays clean and this level never falls back to
    # the built-in poolrooms generator.
    grid = [[DECK for _ in range(MODULE_CELLS)] for __ in range(MODULE_CELLS)]
    return {"grid": grid, "style_id": STYLE_ID}


def _add_void_underlay(game, root, tex: Texture) -> None:
    underlay = game._add_plane(
        root,
        Vec3(MODULE_SIZE * 0.5, MODULE_SIZE * 0.5, DECK_Z - 0.10),
        MODULE_SIZE,
        MODULE_SIZE,
        (0, -90, 0),
        tex,
        MODULE_CELLS * 0.90,
        MODULE_CELLS * 0.90,
    )
    underlay.setColorScale(0.24, 0.18, 0.30, 1.0)
    game.deck_surfaces.append(underlay)


def _add_broken_floor(game, root, mx: int, my: int, floor_tex: Texture, accent_tex: Texture) -> None:
    tile = MODULE_SIZE / 4.0
    rng = Random(_seed(mx, my, 0xF10A))
    for gx in range(4):
        for gy in range(4):
            center = Vec3(gx * tile + tile * 0.5, gy * tile + tile * 0.5, DECK_Z + rng.uniform(-0.16, 0.14))
            scale = Vec3(tile * rng.uniform(0.84, 0.94), tile * rng.uniform(0.84, 0.94), rng.uniform(0.18, 0.34))
            tex = accent_tex if rng.random() < 0.18 else floor_tex
            tile_box = game._add_box(root, center, scale, tex)
            tint = 0.82 + rng.uniform(-0.08, 0.10)
            tile_box.setColorScale(0.10 * tint + 0.02, 0.13 * tint + 0.02, 0.18 * tint + 0.02, 1.0)

            if rng.random() < 0.42:
                seam = game._add_plane(
                    root,
                    center + Vec3(0.0, 0.0, scale.z * 0.5 + 0.02),
                    scale.x * rng.uniform(0.24, 0.48),
                    scale.y * rng.uniform(0.08, 0.14),
                    (rng.uniform(0.0, 180.0), -90, 0),
                    accent_tex,
                    1.0,
                    1.0,
                    True,
                )
                seam.setBin("transparent", 18)
                seam.setColorScale(0.16, 0.82, 1.0, 0.10)
                game.deck_gloss_overlays.append((seam, mx * 0.06 + gx * 0.11, my * 0.05 + gy * 0.13))


def _add_chunk_seams(game, root, accent_tex: Texture) -> None:
    half = MODULE_SIZE * 0.5
    for sign in (-1.0, 1.0):
        rib_x = game._add_box(
            root,
            Vec3((half + sign * (half - 0.34)), half, 2.2),
            Vec3(0.16, MODULE_SIZE, 2.6),
            accent_tex,
        )
        rib_y = game._add_box(
            root,
            Vec3(half, (half + sign * (half - 0.34)), 2.2),
            Vec3(MODULE_SIZE, 0.16, 2.6),
            accent_tex,
        )
        rib_x.setColorScale(0.18, 0.68, 1.0, 1.0)
        rib_y.setColorScale(0.22, 0.30, 0.90, 1.0)


def _add_ceiling_and_slices(game, root, mx: int, my: int, wall_tex: Texture, overlay_tex: Texture, level_state: Dict[str, Any]) -> None:
    ceiling = game._add_plane(
        root,
        Vec3(MODULE_SIZE * 0.5, MODULE_SIZE * 0.5, WALL_H - 0.04),
        MODULE_SIZE,
        MODULE_SIZE,
        (0, -90, 0),
        wall_tex,
        MODULE_CELLS * 0.85,
        MODULE_CELLS * 0.85,
    )
    ceiling.setColorScale(0.06, 0.05, 0.08, 1.0)

    rng = Random(_seed(mx, my, 0xCE11))
    for idx in range(4):
        screen = game._add_plane(
            root,
            Vec3(rng.uniform(4.0, MODULE_SIZE - 4.0), rng.uniform(4.0, MODULE_SIZE - 4.0), rng.uniform(1.6, 3.4)),
            rng.uniform(4.0, 8.0),
            rng.uniform(0.22, 0.46),
            (rng.uniform(0.0, 180.0), rng.uniform(-20.0, 20.0), rng.uniform(-18.0, 18.0)),
            overlay_tex,
            1.0,
            1.0,
            True,
        )
        screen.setBin("transparent", 22)
        screen.setDepthWrite(False)
        color = Vec4(0.42 + rng.random() * 0.32, 0.22 + rng.random() * 0.22, 0.86 + rng.random() * 0.10, 1.0)
        screen.setColorScale(color.x, color.y, color.z, 0.16)
        _register_projection(game, level_state, screen, phase=mx * 0.31 + my * 0.27 + idx * 0.58, pulse=0.05 + idx * 0.01, color=color)
        _register_anim(level_state, screen, "screen", Vec3(screen.getPos()), Vec3(screen.getHpr()), 0.5 + idx * 0.12, idx * 0.9 + mx * 0.3, 0.8 + idx * 0.2)


def _add_monoliths(game, root, mx: int, my: int, wall_tex: Texture, accent_tex: Texture) -> None:
    rng = Random(_seed(mx, my, 0xBEEF))
    count = 5 + rng.randrange(4)
    for idx in range(count):
        x = rng.uniform(2.5, MODULE_SIZE - 2.5)
        y = rng.uniform(2.5, MODULE_SIZE - 2.5)
        h = rng.uniform(3.2, 9.0)
        sx = rng.uniform(0.24, 1.1)
        sy = rng.uniform(0.24, 0.95)
        monolith = game._add_box(root, Vec3(x, y, DECK_Z + h * 0.5), Vec3(sx, sy, h), accent_tex if rng.random() < 0.28 else wall_tex)
        tone = 0.85 + rng.uniform(-0.08, 0.10)
        monolith.setColorScale(0.08 * tone, 0.09 * tone, 0.14 * tone + 0.02, 1.0)

        if rng.random() < 0.55:
            slit = game._add_plane(
                root,
                Vec3(x, y, rng.uniform(1.1, min(WALL_H - 0.4, h - 0.5))),
                max(0.22, sx * 0.72),
                rng.uniform(0.55, 1.8),
                (rng.uniform(0.0, 360.0), 0.0, 0.0),
                accent_tex,
                1.0,
                1.0,
                True,
            )
            slit.setBin("transparent", 20)
            slit.setColorScale(0.18, 0.82, 1.0, 0.10)
            game.deck_reflection_overlays.append((slit, mx * 0.04 + idx * 0.07, my * 0.03 + idx * 0.09))


def _add_floating_shards(game, root, mx: int, my: int, shard_tex: Texture, accent_tex: Texture, level_state: Dict[str, Any]) -> None:
    rng = Random(_seed(mx, my, 0x51A6))
    for idx in range(10 + rng.randrange(5)):
        pos = Vec3(
            rng.uniform(1.5, MODULE_SIZE - 1.5),
            rng.uniform(1.5, MODULE_SIZE - 1.5),
            rng.uniform(2.0, 10.8),
        )
        hpr = Vec3(rng.uniform(0.0, 360.0), rng.uniform(0.0, 360.0), rng.uniform(0.0, 360.0))
        scale = Vec3(rng.uniform(0.12, 1.25), rng.uniform(0.12, 1.05), rng.uniform(0.16, 1.65))
        shard = game._add_box(root, pos, scale, accent_tex if rng.random() < 0.42 else shard_tex)
        tint = 0.86 + rng.uniform(-0.10, 0.12)
        shard.setColorScale(0.10 * tint + 0.02, 0.12 * tint + 0.01, 0.18 * tint + 0.04, 1.0)
        _register_anim(level_state, shard, "shard", pos, hpr, rng.uniform(0.4, 1.0), rng.uniform(0.0, math.tau), rng.uniform(0.4, 1.5))


def _add_distant_void_cards(game, root, mx: int, my: int, overlay_tex: Texture, level_state: Dict[str, Any]) -> None:
    rng = Random(_seed(mx, my, 0xA11F))
    for idx in range(6):
        card = game._add_plane(
            root,
            Vec3(rng.uniform(2.0, MODULE_SIZE - 2.0), rng.uniform(2.0, MODULE_SIZE - 2.0), rng.uniform(6.0, 12.0)),
            rng.uniform(0.8, 2.6),
            rng.uniform(1.6, 4.8),
            (rng.uniform(0.0, 360.0), rng.uniform(0.0, 360.0), rng.uniform(0.0, 360.0)),
            overlay_tex,
            1.0,
            1.0,
            True,
        )
        card.setBin("transparent", 15)
        card.setDepthWrite(False)
        card.setColorScale(0.24, 0.78, 1.0, 0.08)
        _register_anim(level_state, card, "screen", Vec3(card.getPos()), Vec3(card.getHpr()), 0.30, idx * 0.61 + mx * 0.2 + my * 0.16, 0.55)


def _add_glow_lights(game, root, mx: int, my: int) -> None:
    game._add_point_light(
        root,
        Vec3(MODULE_SIZE * 0.28, MODULE_SIZE * 0.34, WALL_H * 0.72),
        Vec4(0.05, 0.16, 0.24, 1.0),
        Vec3(1.0, 0.0, 0.035),
        phase=mx * 0.22 + my * 0.31,
        pulse=0.05,
    )
    game._add_point_light(
        root,
        Vec3(MODULE_SIZE * 0.74, MODULE_SIZE * 0.68, WALL_H * 0.66),
        Vec4(0.16, 0.05, 0.22, 1.0),
        Vec3(1.0, 0.0, 0.038),
        phase=mx * -0.18 + my * 0.27 + 1.4,
        pulse=0.05,
    )
    game._add_point_light(
        root,
        Vec3(MODULE_SIZE * 0.54, MODULE_SIZE * 0.48, WALL_H * 0.82),
        Vec4(0.08, 0.10, 0.18, 1.0),
        Vec3(1.0, 0.0, 0.030),
        phase=mx * 0.14 - my * 0.16 + 2.1,
        pulse=0.03,
    )


def build_module(game, root, water_root, mx: int, my: int, data) -> None:
    del water_root  # This level is dry; do not let the default poolrooms water build.
    del data

    level_state = _ensure_state(game)
    tex = level_state["textures"]

    _add_void_underlay(game, root, tex["wall"])
    _add_broken_floor(game, root, mx, my, tex["floor"], tex["accent"])
    _add_chunk_seams(game, root, tex["accent"])
    _add_ceiling_and_slices(game, root, mx, my, tex["wall"], tex["overlay"], level_state)
    _add_monoliths(game, root, mx, my, tex["wall"], tex["accent"])
    _add_floating_shards(game, root, mx, my, tex["shard"], tex["accent"], level_state)
    _add_distant_void_cards(game, root, mx, my, tex["overlay"], level_state)
    _add_glow_lights(game, root, mx, my)
