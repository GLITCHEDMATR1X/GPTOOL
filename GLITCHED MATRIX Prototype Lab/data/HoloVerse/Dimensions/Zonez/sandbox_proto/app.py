from __future__ import annotations

import json
import math
import random
from pathlib import Path

from direct.showbase.ShowBase import ShowBase
from panda3d.core import (
    AmbientLight,
    CardMaker,
    ClockObject,
    DirectionalLight,
    Filename,
    Fog,
    LPoint3f,
    LVector3f,
    LineSegs,
    NodePath,
    TransparencyAttrib,
    WindowProperties,
)

from .constants import (
    CAMERA_DISTANCE,
    CHUNK_SIZE,
    CAMERA_HEIGHT,
    CAMERA_LOOKAHEAD,
    CAMERA_MOUSE_SMOOTHING,
    CAMERA_POSITION_SMOOTHING,
    CAMERA_SHOULDER_OFFSET,
    CAMERA_SMOOTHING,
    CAMERA_VERTICAL_OFFSET,
    DEFAULT_SEED,
    HOTBAR_IDS,
    MAX_WORLD_SIZE_CHUNKS,
    MIN_WORLD_SIZE_CHUNKS,
    MOUSE_SENSITIVITY,
    PLAYER_HEIGHT,
    PLAYER_RADIUS,
    WORLD_BOUNDARY_CHUNK_RADIUS,
    WORLD_BOUNDARY_WALL_HEIGHT,
    ZONE_DEFS,
    ZONE_ORDER,
)
from .player import InputState, PlayerController, build_elf_character, build_human_character, build_robot_character
from .save_system import SaveSystem
from .ui import GameUI
from .world import VoxelWorld
from .sound_system import ZoneAudio


class SandboxApp(ShowBase):
    def __init__(self):
        super().__init__()
        self.disableMouse()
        self.setFrameRateMeter(False)

        self.project_root = Path(__file__).resolve().parent.parent
        self.save_system = SaveSystem(self.project_root)

        self.seed = DEFAULT_SEED
        self.rng = random.Random(self.seed)
        self.zone_states = self._build_default_zone_states(self.seed)
        self.active_zone_key = ZONE_ORDER[0]
        self.world_size_chunks = WORLD_BOUNDARY_CHUNK_RADIUS

        self.world = VoxelWorld(self.render, self.zone_states[self.active_zone_key]['seed'], self.project_root, zone_key=self.active_zone_key, boundary_chunk_radius=self.world_size_chunks)
        self.player = PlayerController(self.world, self.render, self.world.cube_template)
        self.ui = GameUI(self)
        self.sound = ZoneAudio(self, self.project_root)
        self.zone_setpieces_root = self.render.attachNewNode('zone_setpieces_root')
        self.zone_monsters = []

        self.input_state = InputState()
        self.paused = False
        self.zone_portal_open = False
        self.first_person = False
        self.selected_index = 0
        self.camera_yaw = 26.0
        self.camera_pitch = -14.0
        self.camera_target = LPoint3f(0, 0, 0)
        self.camera_focus = LPoint3f(0, 0, 0)
        self.camera_distance = max(6.4, CAMERA_DISTANCE - 0.6)
        self.camera_distance_min = 3.4
        self.camera_distance_max = 14.0
        self.camera_zoom_step = 0.75
        self.camera_pos = LPoint3f(0, -10, 8)
        self.camera.setPos(self.camera_pos)
        self.mouse_captured = False
        self.mouse_dx_filtered = 0.0
        self.mouse_dy_filtered = 0.0
        self.status_timer = 0.0

        self.hit_highlight = self._build_outline_box((1.0, 1.0, 1.0, 1.0), 1.02)
        self.place_preview = self.world.cube_template.copyTo(self.render)
        self.place_preview.setScale(1.01)
        self.place_preview.setColorScale(0.35, 0.95, 1.0, 0.28)
        self.place_preview.setTransparency(TransparencyAttrib.MAlpha)
        self.place_preview.setLightOff()
        self.place_preview.hide()

        self._setup_lighting()
        self._setup_fog()
        self._apply_zone_visuals(self.active_zone_key)
        self.ui.set_zone(self.current_zone_name)
        self._bind_inputs()
        self._bootstrap_initial_start(f'Preparing {self.current_zone_name}')
        self.capture_mouse(True)

        self.taskMgr.add(self.update_task, 'update_task', sort=10)
        self.taskMgr.add(self.status_task, 'status_task', sort=20)

    @property
    def current_zone_name(self) -> str:
        return ZONE_DEFS[self.active_zone_key].name

    def _build_default_zone_states(self, base_seed: int) -> dict[str, dict]:
        states = {}
        for zone_key in ZONE_ORDER:
            zone_def = ZONE_DEFS[zone_key]
            states[zone_key] = {
                'seed': base_seed + zone_def.seed_offset,
                'player_pos': (0.5, 0.5, 10.0),
                'modifications': {},
            }
        return states

    def _ensure_zone_dirs(self) -> None:
        for zone_key in ZONE_ORDER:
            self.save_system.zone_dir(zone_key).mkdir(parents=True, exist_ok=True)

    def _build_outline_box(self, color: tuple[float, float, float, float], scale: float) -> NodePath:
        lines = LineSegs('highlight_box')
        lines.setThickness(2.0)
        lines.setColor(*color)
        s = 0.5 * scale
        corners = [
            (-s, -s, -s), (s, -s, -s), (s, s, -s), (-s, s, -s),
            (-s, -s, s), (s, -s, s), (s, s, s), (-s, s, s),
        ]
        edges = [
            (0, 1), (1, 2), (2, 3), (3, 0),
            (4, 5), (5, 6), (6, 7), (7, 4),
            (0, 4), (1, 5), (2, 6), (3, 7),
        ]
        for a, b in edges:
            ax, ay, az = corners[a]
            bx, by, bz = corners[b]
            lines.moveTo(ax, ay, az)
            lines.drawTo(bx, by, bz)
        node = self.render.attachNewNode(lines.create())
        node.setLightOff()
        node.setDepthWrite(False)
        node.setTransparency(TransparencyAttrib.MAlpha)
        node.hide()
        return node

    def _setup_lighting(self) -> None:
        self.ambient_light = AmbientLight('ambient')
        self.ambient_np = self.render.attachNewNode(self.ambient_light)
        self.render.setLight(self.ambient_np)

        self.sun_light = DirectionalLight('sun')
        self.sun_np = self.render.attachNewNode(self.sun_light)
        self.render.setLight(self.sun_np)

    def _setup_fog(self) -> None:
        self.fog = Fog('world_fog')
        self.render.setFog(self.fog)

    def _apply_zone_visuals(self, zone_key: str) -> None:
        zone = ZONE_DEFS[zone_key]
        self.ambient_light.setColor(zone.ambient_color)
        self.sun_light.setColor(zone.sun_color)
        self.sun_np.setHpr(*zone.sun_hpr)
        self.fog.setColor(*zone.fog_color)
        self.fog.setExpDensity(zone.fog_density)
        self.setBackgroundColor(*zone.background_color)
        self.world.apply_zone(zone_key, zone.atlas_variant)
        self.player.set_palette_mode(zone.grayscale_player)
        self.ui.set_zone(zone.name)

    def _clamp_xy_inside_boundary(self, x: float, y: float, padding: float = 0.0) -> tuple[float, float]:
        clamped_x, clamped_y = self.world.clamp_to_world_boundary(x, y, margin=padding)
        return float(clamped_x), float(clamped_y)

    def _boundary_safe_radius(self, anchor_x: float, anchor_y: float, desired_radius: float, padding: float = 0.0) -> float:
        half = self.world.get_boundary_inner_half_extent(padding)
        max_radius = min(half - abs(anchor_x), half - abs(anchor_y))
        return max(0.0, min(desired_radius, max_radius))



    def _safe_load_texture(self, texture_path: Path | None):
        if texture_path is None:
            return None
        try:
            resolved = texture_path.resolve()
        except Exception:
            resolved = texture_path
        if not resolved.exists():
            return None
        candidates = [resolved]
        try:
            candidates.append(resolved.relative_to(self.project_root))
        except Exception:
            pass
        for candidate in candidates:
            try:
                tex = self.loader.loadTexture(Filename.fromOsSpecific(str(candidate)))
                if tex is not None:
                    return tex
            except Exception:
                continue
            try:
                tex = self.loader.loadTexture(str(candidate).replace('\\', '/'))
                if tex is not None:
                    return tex
            except Exception:
                continue
        return None

    def _resolve_boundary_wall_image(self, zone_key: str, slot: str) -> Path | None:
        bounds_dir = self.project_root / 'assets' / 'boundaries'
        candidates = [
            bounds_dir / f'{zone_key}_{slot}.png',
            bounds_dir / 'walls' / f'{zone_key}_{slot}.png',
            bounds_dir / zone_key / f'{slot}.png',
            bounds_dir / 'walls' / zone_key / f'{slot}.png',
            bounds_dir / f'default_{slot}.png',
            bounds_dir / 'walls' / f'default_{slot}.png',
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return None

    def _build_textured_card(self, parent: NodePath, name: str, texture_path: Path | None, pos: tuple[float, float, float], hpr: tuple[float, float, float], scale: tuple[float, float, float], color: tuple[float, float, float, float] = (1.0, 1.0, 1.0, 1.0), transparent: bool = False) -> NodePath:
        card = CardMaker(name)
        card.setFrame(-0.5, 0.5, -0.5, 0.5)
        np = parent.attachNewNode(card.generate())
        np.setPos(*pos)
        np.setHpr(*hpr)
        np.setScale(*scale)
        np.setColorScale(*color)
        np.setLightOff()
        np.setFogOff()
        np.setTwoSided(True)
        np.setDepthWrite(False)
        if transparent or color[3] < 1.0:
            np.setTransparency(TransparencyAttrib.MAlpha)
        tex = self._safe_load_texture(texture_path)
        if tex is not None:
            np.setTexture(tex, 1)
        return np

    def _load_boundary_profile(self, zone_key: str) -> dict:
        bounds_dir = self.project_root / 'assets' / 'boundaries'
        profile_path = bounds_dir / 'boundary_profiles.json'
        data = {}
        if profile_path.exists():
            try:
                data = json.loads(profile_path.read_text())
            except Exception:
                data = {}
        profiles = data.get('zones', {}) if isinstance(data, dict) else {}
        profile = dict(profiles.get('default', {}))
        zone_profile = profiles.get(zone_key, {})
        if isinstance(zone_profile, dict):
            profile.update(zone_profile)
        profile['horizon_path'] = bounds_dir / profile.get('horizon', 'default_horizon.png')
        profile['ceiling_path'] = bounds_dir / profile.get('ceiling', 'default_ceiling.png')
        return profile

    def _build_world_boundary(self, parent: NodePath) -> None:
        profile = self._load_boundary_profile(self.active_zone_key)
        zone = ZONE_DEFS[self.active_zone_key]
        root = parent.attachNewNode('world_boundary')
        half = self.world.get_boundary_half_extent()
        wall_height = float(profile.get('wall_height', WORLD_BOUNDARY_WALL_HEIGHT))
        glow_color = tuple(profile.get('glow_color', [zone.background_color[0], zone.background_color[1], zone.background_color[2], 0.18]))
        sky_color = (zone.background_color[0], zone.background_color[1], zone.background_color[2], 1.0)
        span = half * 2.0

        horizon_offset = half + 0.6
        horizon_h = wall_height * 0.92
        horizon_z = wall_height * 0.46
        horizon_scale = span + CHUNK_SIZE * 2.0
        for name, slot, pos, hpr in [
            ('north_horizon', 'north', (0.0, horizon_offset, horizon_z), (0.0, 0.0, 0.0)),
            ('south_horizon', 'south', (0.0, -horizon_offset, horizon_z), (180.0, 0.0, 0.0)),
            ('east_horizon', 'east', (horizon_offset, 0.0, horizon_z), (90.0, 0.0, 0.0)),
            ('west_horizon', 'west', (-horizon_offset, 0.0, horizon_z), (-90.0, 0.0, 0.0)),
        ]:
            wall_texture = self._resolve_boundary_wall_image(self.active_zone_key, slot)
            wall_color = (1.0, 1.0, 1.0, 1.0) if wall_texture is not None else sky_color
            card = self._build_textured_card(root, name, wall_texture, pos, hpr, (horizon_scale, 1.0, horizon_h), wall_color, transparent=wall_texture is not None)
            card.setBin('background', 5)

        corner_scale = span * 0.55
        corner_offset = horizon_offset * 0.74
        for name, slot, pos, hpr in [
            ('north_east_horizon', 'north_east', (corner_offset, corner_offset, horizon_z), (45.0, 0.0, 0.0)),
            ('north_west_horizon', 'north_west', (-corner_offset, corner_offset, horizon_z), (-45.0, 0.0, 0.0)),
            ('south_east_horizon', 'south_east', (corner_offset, -corner_offset, horizon_z), (135.0, 0.0, 0.0)),
            ('south_west_horizon', 'south_west', (-corner_offset, -corner_offset, horizon_z), (-135.0, 0.0, 0.0)),
        ]:
            wall_texture = self._resolve_boundary_wall_image(self.active_zone_key, slot)
            wall_color = (1.0, 1.0, 1.0, 1.0) if wall_texture is not None else sky_color
            card = self._build_textured_card(root, name, wall_texture, pos, hpr, (corner_scale, 1.0, horizon_h * 0.92), wall_color, transparent=wall_texture is not None)
            card.setBin('background', 4)

        canopy_z = wall_height + 5.5
        ceiling_path = profile.get('ceiling_path')
        ceiling_texture = ceiling_path if isinstance(ceiling_path, Path) and ceiling_path.exists() else None
        ceiling_color = (1.0, 1.0, 1.0, float(profile.get('ceiling_alpha', 0.50))) if ceiling_texture is not None else sky_color
        ceiling = self._build_textured_card(root, 'sky_blend', ceiling_texture, (0.0, 0.0, canopy_z), (0.0, -90.0, 0.0), (span + 48.0, 1.0, span + 48.0), ceiling_color, transparent=ceiling_texture is not None)
        ceiling.setBin('background', 3)

        rim = self._add_colored_cube(root, (0.0, 0.0, 1.0), (half + 24.0, half + 24.0, 0.02), (glow_color[0], glow_color[1], glow_color[2], 0.05), light_off=True, transparency=True)
        rim.setFogOff()
        rim.setBin('background', 2)
        haze = self._add_colored_cube(root, (0.0, 0.0, canopy_z - 2.8), (half + 20.0, half + 20.0, 0.08), glow_color, light_off=True, transparency=True)
        haze.setFogOff()
        haze.setBin('background', 1)

    def _clear_zone_setpieces(self) -> None:
        if self.zone_setpieces_root is not None:
            self.zone_setpieces_root.removeNode()
        self.zone_setpieces_root = self.render.attachNewNode('zone_setpieces_root')
        self.zone_monsters = []

    def _add_colored_cube(self, parent: NodePath, pos: tuple[float, float, float], scale: tuple[float, float, float], color: tuple[float, float, float, float], light_off: bool = False, transparency: bool = False) -> NodePath:
        cube = self.world.cube_template.copyTo(parent)
        cube.setPos(*pos)
        cube.setScale(*scale)
        cube.setColorScale(*color)
        if light_off:
            cube.setLightOff()
        if transparency or color[3] < 1.0:
            cube.setTransparency(TransparencyAttrib.MAlpha)
        return cube

    def _build_cloud_cluster(self, parent: NodePath, center: tuple[float, float, float], scale: float = 1.0) -> None:
        cx, cy, cz = center
        puffs = [
            ((0.0, 0.0, 0.0), (4.8, 2.6, 1.3)),
            ((3.1, 0.7, 0.2), (3.6, 2.0, 1.0)),
            ((-3.0, 0.4, -0.1), (3.2, 1.8, 0.95)),
            ((0.6, 1.8, 0.15), (4.0, 1.8, 0.95)),
        ]
        for (ox, oy, oz), (sx, sy, sz) in puffs:
            cloud = self._add_colored_cube(
                parent,
                (cx + ox * scale, cy + oy * scale, cz + oz * scale),
                (sx * scale, sy * scale, sz * scale),
                (0.95, 0.95, 0.95, 0.98),
                light_off=True,
            )
            cloud.setFogOff()

    def _ground_height_for_zone(self, x: float, y: float, prefer_floor: bool = False) -> float:
        wx = int(round(x))
        wy = int(round(y))
        if prefer_floor or self.active_zone_key == 'hell_zone':
            ground = self.find_surface_floor(wx, wy)
            if ground is None:
                ground = self.find_surface(wx, wy)
        else:
            ground = self.find_surface(wx, wy)
        if ground is None:
            ground = 4
        return float(ground)

    def _face_heading_to_point(self, from_x: float, from_y: float, to_x: float, to_y: float) -> float:
        dx = to_x - from_x
        dy = to_y - from_y
        if abs(dx) + abs(dy) < 1e-6:
            return 0.0
        return math.degrees(math.atan2(-dx, dy))

    def _actor_collides(self, x: float, y: float, z: float, radius: float, height: float) -> bool:
        return self.world.collides_aabb(x - radius, x + radius, y - radius, y + radius, z, z + height)

    def _move_actor_with_collision(
        self,
        current: LPoint3f,
        target_x: float,
        target_y: float,
        dt: float,
        *,
        radius: float,
        height: float,
        prefer_floor: bool = False,
        step_height: float = 1.15,
        max_blend: float = 2.2,
    ) -> LPoint3f:
        blend = min(1.0, dt * max_blend)
        pos = LPoint3f(current)
        step_x = (target_x - current.x) * blend
        step_y = (target_y - current.y) * blend

        for axis, delta in (('x', step_x), ('y', step_y)):
            if abs(delta) < 1e-6:
                continue
            trial = LPoint3f(pos)
            setattr(trial, axis, getattr(trial, axis) + delta)
            floor_z = self._ground_height_for_zone(trial.x, trial.y, prefer_floor=prefer_floor) + 0.5
            trial.z = max(pos.z - 0.7, floor_z)
            if not self._actor_collides(trial.x, trial.y, trial.z, radius, height):
                pos = trial
                continue

            stepped = LPoint3f(trial.x, trial.y, max(pos.z, floor_z) + step_height)
            if not self._actor_collides(stepped.x, stepped.y, stepped.z, radius, height):
                pos = stepped

        target_z = self._ground_height_for_zone(pos.x, pos.y, prefer_floor=prefer_floor) + 0.5
        if not self._actor_collides(pos.x, pos.y, target_z, radius, height):
            pos.z += (target_z - pos.z) * min(1.0, dt * 8.0)
        return pos

    def _teleport_dread_monster(self, monster: dict, *, behind_player: bool) -> None:
        root = monster.get('root')
        if root is None or root.isEmpty():
            return

        look_x, look_y = self._look_vector()
        right_x, right_y = look_y, -look_x
        side = -1.0 if math.sin(monster.get('time', 0.0) * 1.7) < 0.0 else 1.0
        if behind_player:
            dist = 10.5 + math.sin(monster.get('time', 0.0) * 0.63) * 1.5
            lateral = 3.2
        else:
            dist = 22.0 + math.sin(monster.get('time', 0.0) * 0.63) * 2.4
            lateral = 6.5
        target_x = self.player.pos.x - look_x * dist + right_x * (lateral * side)
        target_y = self.player.pos.y - look_y * dist + right_y * (lateral * 0.82 * side)
        target_x, target_y = self._clamp_xy_inside_boundary(target_x, target_y, padding=11.0)

        ground = self._ground_height_for_zone(target_x, target_y, prefer_floor=False)
        root.setPos(target_x, target_y, ground + 0.5)
        root.setH(self._face_heading_to_point(target_x, target_y, self.player.pos.x, self.player.pos.y) + 180.0)
        monster['last_player_pos'] = LPoint3f(self.player.pos.x, self.player.pos.y, self.player.pos.z)

    def _build_tech_starfield(self, parent: NodePath, center: tuple[float, float, float], radius: float = 120.0, height: float = 34.0, count: int = 160) -> None:
        cx, cy, _ = center
        sky = parent.attachNewNode('tech_starfield')
        for idx in range(count):
            ang = ((idx * 37) % 360) * math.pi / 180.0
            ring = radius * (0.35 + 0.65 * (((idx * 19) % 100) / 100.0))
            sx = cx + math.cos(ang) * ring
            sy = cy + math.sin(ang * 1.17) * ring
            sz = height + ((idx * 23) % 17) * 0.65
            size = 0.10 + (((idx * 7) % 9) / 100.0)
            star = self._add_colored_cube(sky, (sx, sy, sz), (size, size, size), (0.82, 0.90, 1.0, 0.95), light_off=True, transparency=True)
            star.setFogOff()
        haze = self._add_colored_cube(sky, (cx, cy, height - 3.8), (radius * 1.65, radius * 1.65, 0.22), (0.08, 0.14, 0.24, 0.18), light_off=True, transparency=True)
        haze.setFogOff()

    def _build_night_sky(self, parent: NodePath, center: tuple[float, float, float], radius: float = 125.0, height: float = 30.0, count: int = 120) -> None:
        cx, cy, _ = center
        sky = parent.attachNewNode('night_sky')
        for idx in range(count):
            ang = ((idx * 29) % 360) * math.pi / 180.0
            ring = radius * (0.28 + 0.72 * (((idx * 17) % 100) / 100.0))
            sx = cx + math.cos(ang) * ring
            sy = cy + math.sin(ang * 1.11) * ring
            sz = height + ((idx * 13) % 14) * 0.58
            size = 0.08 + (((idx * 5) % 7) / 120.0)
            star = self._add_colored_cube(sky, (sx, sy, sz), (size, size, size), (0.92, 0.96, 1.0, 0.95), light_off=True, transparency=True)
            star.setFogOff()
        moon = self._add_colored_cube(sky, (cx - radius * 0.26, cy + radius * 0.34, height + 7.0), (1.8, 1.8, 1.8), (0.92, 0.94, 1.0, 0.95), light_off=True, transparency=True)
        moon.setFogOff()
        moon_glow = self._add_colored_cube(sky, (cx - radius * 0.26, cy + radius * 0.34, height + 7.0), (3.8, 3.8, 0.20), (0.68, 0.78, 1.0, 0.12), light_off=True, transparency=True)
        moon_glow.setFogOff()

    def _build_tech_cityscape(self, parent: NodePath, center: tuple[float, float, float], width: float = 42.0, depth: float = 36.0) -> None:
        cx, cy, base_z = center
        root = parent.attachNewNode('tech_cityscape')
        wall_color = (0.10, 0.12, 0.16, 1.0)
        wall_edge = (0.22, 0.30, 0.38, 1.0)
        neon_a = (0.10, 0.82, 1.0, 1.0)
        neon_b = (1.0, 0.22, 0.66, 1.0)
        neon_c = (0.66, 0.30, 1.0, 1.0)
        for ox, oy, sx, sy in [
            (0.0, depth * 0.5, width * 1.02, 0.8),
            (0.0, -depth * 0.5, width * 1.02, 0.8),
            (width * 0.5, 0.0, 0.8, depth * 1.02),
            (-width * 0.5, 0.0, 0.8, depth * 1.02),
        ]:
            self._add_colored_cube(root, (cx + ox, cy + oy, base_z + 3.4), (sx, sy, 3.6), wall_color)
            edge = self._add_colored_cube(root, (cx + ox, cy + oy, base_z + 7.1), (sx * 0.98, sy * 0.98, 0.14), neon_a, light_off=True)
            edge.setFogOff()
        tower_specs = [
            (-13.0, -9.0, 5.0, 5.0, 13.0, neon_a),
            (14.0, -8.5, 5.4, 5.4, 15.0, neon_b),
            (-14.0, 9.5, 5.2, 5.2, 12.5, neon_c),
            (13.5, 10.0, 5.6, 5.6, 16.0, neon_a),
            (0.0, 13.0, 7.0, 7.0, 18.0, neon_b),
        ]
        for idx, (ox, oy, sx, sy, sz, neon) in enumerate(tower_specs):
            body = self._add_colored_cube(root, (cx + ox, cy + oy, base_z + sz * 0.5), (sx, sy, sz), wall_color)
            body.setColorScale(0.92, 0.96, 1.0, 1.0)
            for band_i in range(3):
                band_z = base_z + 2.6 + band_i * (sz / 3.3)
                band = self._add_colored_cube(root, (cx + ox, cy + oy + sy * 0.50, band_z), (sx * 0.76, 0.10, 0.16), neon, light_off=True)
                band.setFogOff()
            roof = self._add_colored_cube(root, (cx + ox, cy + oy, base_z + sz + 0.8), (sx * 0.76, sy * 0.76, 0.20), wall_edge)
            mast = self._add_colored_cube(root, (cx + ox, cy + oy, base_z + sz + 2.1), (0.20, 0.20, 1.0 + idx * 0.20), neon, light_off=True)
            roof.setFogOff()
            mast.setFogOff()
        boulevard = self._add_colored_cube(root, (cx, cy, base_z + 0.2), (width * 0.42, depth * 0.18, 0.16), (0.08, 0.10, 0.13, 1.0))
        boulevard.setFogOff()
        gate = self._add_colored_cube(root, (cx, cy - depth * 0.5, base_z + 2.4), (8.8, 0.90, 2.6), wall_edge)
        gate.setFogOff()
        gate_light = self._add_colored_cube(root, (cx, cy - depth * 0.5 + 0.16, base_z + 3.8), (6.8, 0.10, 0.18), neon_b, light_off=True)
        gate_light.setFogOff()

    def _build_glow_bug_swarm(self, parent: NodePath, center: tuple[float, float, float], count: int = 12, radius: float = 7.5) -> None:
        cx, cy, cz = center
        for idx in range(count):
            ang = (idx / max(1, count)) * math.tau
            dist = radius * (0.45 + 0.55 * ((idx % 5) / 4.0))
            bug_root = parent.attachNewNode(f'glow_bug_{idx}')
            bug_root.setPos(cx + math.cos(ang) * dist, cy + math.sin(ang) * dist, cz + (idx % 4) * 0.35)
            abdomen = self._add_colored_cube(bug_root, (0.0, 0.0, 0.0), (0.12, 0.18, 0.12), (0.86, 1.0, 0.52, 1.0), light_off=True)
            abdomen.setFogOff()
            thorax = self._add_colored_cube(bug_root, (0.0, -0.12, 0.02), (0.10, 0.12, 0.08), (0.18, 0.22, 0.28, 1.0), light_off=True)
            thorax.setFogOff()
            wing_l = self._add_colored_cube(bug_root, (-0.08, 0.02, 0.05), (0.11, 0.04, 0.06), (0.78, 0.96, 1.0, 0.55), light_off=True, transparency=True)
            wing_r = self._add_colored_cube(bug_root, (0.08, 0.02, 0.05), (0.11, 0.04, 0.06), (0.78, 0.96, 1.0, 0.55), light_off=True, transparency=True)
            wing_l.setFogOff()
            wing_r.setFogOff()
            self.zone_monsters.append({
                'type': 'glowbug',
                'root': bug_root,
                'anchor': LPoint3f(cx, cy, cz),
                'orbit_angle': ang,
                'orbit_radius': dist,
                'phase': idx * 0.73,
                'height_offset': (idx % 4) * 0.35,
                'speed': 0.8 + idx * 0.07,
            })

    def _build_desert_cactus(self, parent: NodePath, base_x: float, base_y: float) -> None:
        spawn_x, spawn_y = self._clamp_xy_inside_boundary(base_x + 0.5, base_y + 0.5, padding=7.0)
        ground = self._ground_height_for_zone(spawn_x, spawn_y, prefer_floor=False)
        root = parent.attachNewNode('cactus_sage_root')
        root.setPos(spawn_x, spawn_y, ground + 0.5)
        body = (0.18, 0.54, 0.24, 1.0)
        dark = (0.08, 0.26, 0.12, 1.0)
        eye_white = (0.96, 0.98, 1.0, 1.0)
        pupil = (0.08, 0.08, 0.08, 1.0)
        bloom = (0.86, 1.0, 0.70, 1.0)
        self._add_colored_cube(root, (0.0, 0.0, 4.1), (1.6, 1.5, 4.6), body)
        self._add_colored_cube(root, (0.0, 0.0, 8.7), (1.2, 1.1, 1.0), body)
        for side, oy in ((-1.0, 1.6), (1.0, -0.2)):
            arm = root.attachNewNode(f'arm_{int(side)}')
            arm.setPos(1.65 * side, oy, 5.4)
            self._add_colored_cube(arm, (0.0, 0.0, 0.0), (0.56, 0.56, 2.6), body)
            self._add_colored_cube(arm, (0.0, 0.0, 2.1), (0.56, 0.56, 0.56), body)
            fore = arm.attachNewNode('fore')
            fore.setPos(0.0, 0.0, 2.3)
            fore.setR(-20.0 * side)
            self._add_colored_cube(fore, (0.0, 0.0, 1.5), (0.48, 0.48, 1.8), body)
        for sx in (-0.42, 0.42):
            white = self._add_colored_cube(root, (sx, 0.82, 6.45), (0.34, 0.16, 0.30), eye_white, light_off=True)
            white.setName(f'eye_white_{int((sx+1)*10)}')
            pup = self._add_colored_cube(root, (sx, 0.92, 6.45), (0.10, 0.05, 0.14), pupil, light_off=True)
            pup.setName(f'pupil_{int((sx+1)*10)}')
        mouth = self._add_colored_cube(root, (0.0, 0.78, 5.75), (0.44, 0.08, 0.10), dark, light_off=True)
        mouth.setFogOff()
        aura = self._add_colored_cube(root, (0.0, 0.0, 9.8), (0.42, 0.42, 0.42), bloom, light_off=True)
        aura.setFogOff()
        self.zone_monsters.append({
            'type': 'cactus_sage',
            'root': root,
            'anchor': LPoint3f(spawn_x, spawn_y, ground + 0.5),
            'time': 0.0,
        })

    def _build_tropical_ocean(self, parent: NodePath, center: tuple[float, float, float], size: float = 260.0) -> None:
        cx, cy, cz = center
        half = self.world.get_boundary_inner_half_extent(3.0)
        usable = max(8.0, min(size, half - 2.0))
        root = parent.attachNewNode('tropical_ocean')
        deep = self._add_colored_cube(root, (0.0, 0.0, cz - 1.8), (usable, usable, 2.4), (0.04, 0.14, 0.24, 1.0), light_off=True)
        deep.setFogOff()
        water = self._add_colored_cube(root, (0.0, 0.0, cz + 0.18), (usable, usable, 0.22), (0.10, 0.46, 0.72, 0.72), light_off=True, transparency=True)
        water.setFogOff()
        sheen = self._add_colored_cube(root, (-usable * 0.10, usable * 0.08, cz + 0.26), (usable * 0.46, usable * 0.18, 0.02), (0.66, 0.90, 1.0, 0.10), light_off=True, transparency=True)
        sheen.setH(18.0)
        sheen.setFogOff()

    def _build_tropical_whale(self, parent: NodePath, center: tuple[float, float, float], radius: float = 54.0) -> None:
        cx, cy, cz = center
        cx, cy = self._clamp_xy_inside_boundary(cx, cy, padding=10.0)
        radius = self._boundary_safe_radius(cx, cy, radius, padding=10.0)
        root = parent.attachNewNode('tropical_whale')
        root.setPos(cx + radius * 0.65, cy, cz - 0.2)
        skin = (0.16, 0.26, 0.34, 1.0)
        belly = (0.44, 0.54, 0.62, 1.0)
        eye = (0.95, 0.98, 1.0, 1.0)
        body = root.attachNewNode('body')
        self._add_colored_cube(body, (0.0, 0.0, 0.0), (6.4, 2.3, 1.8), skin)
        self._add_colored_cube(body, (0.6, 1.5, 0.1), (3.6, 1.1, 1.0), skin)
        self._add_colored_cube(body, (0.0, 0.2, -0.9), (5.3, 1.5, 0.55), belly)
        head = body.attachNewNode('head')
        head.setPos(0.0, 2.2, 0.15)
        self._add_colored_cube(head, (0.0, 0.8, 0.0), (2.8, 1.9, 1.4), skin)
        self._add_colored_cube(head, (-0.9, 1.55, 0.18), (0.18, 0.12, 0.18), eye, light_off=True)
        self._add_colored_cube(head, (0.9, 1.55, 0.18), (0.18, 0.12, 0.18), eye, light_off=True)
        tail = body.attachNewNode('tail')
        tail.setPos(0.0, -2.8, 0.1)
        self._add_colored_cube(tail, (0.0, -0.8, 0.0), (2.6, 1.6, 0.9), skin)
        fluke_l = tail.attachNewNode('fluke_l')
        fluke_l.setPos(-1.4, -1.9, 0.0)
        fluke_l.setR(18.0)
        self._add_colored_cube(fluke_l, (0.0, 0.0, 0.0), (1.8, 0.9, 0.18), skin)
        fluke_r = tail.attachNewNode('fluke_r')
        fluke_r.setPos(1.4, -1.9, 0.0)
        fluke_r.setR(-18.0)
        self._add_colored_cube(fluke_r, (0.0, 0.0, 0.0), (1.8, 0.9, 0.18), skin)
        fin_l = body.attachNewNode('fin_l')
        fin_l.setPos(-2.4, 0.2, -0.55)
        fin_l.setR(18.0)
        self._add_colored_cube(fin_l, (0.0, 0.0, 0.0), (1.1, 0.5, 0.14), skin)
        fin_r = body.attachNewNode('fin_r')
        fin_r.setPos(2.4, 0.2, -0.55)
        fin_r.setR(-18.0)
        self._add_colored_cube(fin_r, (0.0, 0.0, 0.0), (1.1, 0.5, 0.14), skin)
        root.setFogOff()
        self.zone_monsters.append({
            'type': 'whale',
            'root': root,
            'anchor': LPoint3f(cx, cy, cz),
            'orbit_radius': radius,
            'time': 0.0,
            'speed': 0.06,
        })

    def _build_candy_blimp(self, parent: NodePath, center: tuple[float, float, float]) -> None:
        cx, cy, cz = center
        cx, cy = self._clamp_xy_inside_boundary(cx, cy, padding=8.0)
        root = parent.attachNewNode('candy_blimp')
        root.setPos(cx, cy, cz)
        hull_color = (1.0, 0.72, 0.88, 1.0)
        stripe_color = (0.74, 0.98, 0.98, 1.0)
        basket_color = (0.84, 0.66, 0.48, 1.0)
        self._add_colored_cube(root, (0.0, 0.0, 0.0), (4.4, 2.2, 1.9), hull_color, light_off=True)
        self._add_colored_cube(root, (0.0, 0.0, 0.0), (3.2, 2.28, 0.52), stripe_color, light_off=True)
        self._add_colored_cube(root, (0.0, 0.0, 0.86), (1.12, 0.62, 0.42), (0.98, 0.86, 0.94, 1.0), light_off=True)
        tail = root.attachNewNode('tail')
        tail.setPos(0.0, -2.48, 0.04)
        self._add_colored_cube(tail, (0.0, 0.0, 0.0), (0.34, 0.22, 1.02), stripe_color, light_off=True)
        self._add_colored_cube(tail, (-0.58, 0.0, 0.0), (0.30, 0.12, 0.72), stripe_color, light_off=True)
        self._add_colored_cube(tail, (0.58, 0.0, 0.0), (0.30, 0.12, 0.72), stripe_color, light_off=True)
        for sx in (-1.12, 1.12):
            for sy in (-0.28, 0.28):
                rope = root.attachNewNode('rope')
                rope.setPos(sx, sy, -1.14)
                rope.setP(8.0 if sx < 0 else -8.0)
                self._add_colored_cube(rope, (0.0, 0.0, -0.66), (0.06, 0.06, 0.70), (0.80, 0.68, 0.56, 1.0), light_off=True)
        basket = root.attachNewNode('basket')
        basket.setPos(0.0, 0.0, -2.22)
        self._add_colored_cube(basket, (0.0, 0.0, 0.0), (1.18, 0.84, 0.38), basket_color, light_off=True)
        self._add_colored_cube(basket, (0.0, 0.0, 0.28), (0.90, 0.66, 0.14), (0.96, 0.86, 0.78, 1.0), light_off=True)
        root.setFogOff()
        self.zone_monsters.append({
            'type': 'candy_blimp',
            'root': root,
            'anchor': LPoint3f(cx, cy, cz),
            'time': 0.0,
        })

    def _build_day_human(self, parent: NodePath, base_x: float, base_y: float) -> None:
        spawn_x, spawn_y = self._clamp_xy_inside_boundary(base_x + 0.5, base_y + 0.5, padding=4.0)
        ground = self._ground_height_for_zone(spawn_x, spawn_y, prefer_floor=False)
        root = parent.attachNewNode('day_human')
        root.setPos(spawn_x, spawn_y, ground + 0.5)
        rig = build_human_character(root, self.world.cube_template, helmet=True)
        self.zone_monsters.append({
            'type': 'human',
            'root': root,
            'rig': rig,
            'anchor': LPoint3f(spawn_x, spawn_y, ground + 0.18),
            'time': 0.0,
            'wander_radius': 6.5,
            'speed': 0.46,
        })


    def _build_polar_elf(self, parent: NodePath, base_x: float, base_y: float, variant: int = 0) -> None:
        spawn_x, spawn_y = self._clamp_xy_inside_boundary(base_x + 0.5, base_y + 0.5, padding=4.5)
        ground = self._ground_height_for_zone(spawn_x, spawn_y, prefer_floor=False)
        root = parent.attachNewNode(f'polar_elf_{variant}')
        root.setPos(spawn_x, spawn_y, ground + 0.18)
        root.setScale(0.42)
        rig = build_elf_character(root, self.world.cube_template, variant=variant)
        self.zone_monsters.append({
            'type': 'elf',
            'root': root,
            'rig': rig,
            'anchor': LPoint3f(spawn_x, spawn_y, ground + 0.5),
            'time': 0.0,
            'wander_radius': 1.7 + (variant % 2) * 0.45,
            'speed': 0.42 + variant * 0.05,
        })

    def _build_snow_flurry(self, parent: NodePath, center: tuple[float, float, float], count: int = 22, radius: float = 11.0) -> None:
        cx, cy, cz = center
        for idx in range(count):
            root = parent.attachNewNode(f'snowflake_{idx}')
            drift_x = ((idx * 37) % 100) / 100.0
            drift_y = ((idx * 53) % 100) / 100.0
            drift_z = ((idx * 29) % 100) / 100.0
            root.setPos(cx + (drift_x - 0.5) * radius * 2.0, cy + (drift_y - 0.5) * radius * 2.0, cz + 6.0 + drift_z * 8.0)
            flake = self._add_colored_cube(root, (0.0, 0.0, 0.0), (0.08, 0.08, 0.08), (0.98, 0.99, 1.0, 0.86), light_off=True, transparency=True)
            flake.setFogOff()
            self.zone_monsters.append({
                'type': 'snowflake',
                'root': root,
                'anchor': LPoint3f(cx, cy, cz),
                'time': idx * 0.17,
                'fall_speed': 1.5 + (idx % 5) * 0.18,
                'drift_radius': radius,
                'phase': idx * 0.41,
            })

    def _build_tech_robot(self, parent: NodePath, base_x: float, base_y: float) -> None:
        spawn_x, spawn_y = self._clamp_xy_inside_boundary(base_x + 0.5, base_y + 0.5, padding=4.5)
        ground = self._ground_height_for_zone(spawn_x, spawn_y, prefer_floor=False)
        root = parent.attachNewNode('tech_robot')
        root.setPos(spawn_x, spawn_y, ground + 0.5)
        rig = build_robot_character(root, self.world.cube_template)
        self.zone_monsters.append({
            'type': 'robot_npc',
            'root': root,
            'rig': rig,
            'anchor': LPoint3f(spawn_x, spawn_y, ground + 0.5),
            'time': 0.0,
            'wander_radius': 4.2,
            'speed': 0.34,
        })

    def _build_dread_monster(self, parent: NodePath, base_x: float, base_y: float) -> None:
        spawn_x, spawn_y = self._clamp_xy_inside_boundary(base_x + 0.5, base_y + 0.5, padding=10.0)
        ground = self.find_surface(int(round(spawn_x)), int(round(spawn_y)))
        if ground is None:
            ground = 4
        root = parent.attachNewNode('dread_monster')
        root.setPos(spawn_x, spawn_y, ground + 0.5)

        leg_color = (0.09, 0.09, 0.09, 1.0)
        body_color = (0.16, 0.16, 0.16, 1.0)
        arm_color = (0.44, 0.44, 0.44, 1.0)
        head_color = (0.82, 0.82, 0.82, 1.0)
        eye_color = (1.0, 1.0, 1.0, 1.0)

        body_pivot = root.attachNewNode('body_pivot')
        body_pivot.setPos(0.0, 0.0, 8.8)
        body_pivot.setP(-6.0)
        self._add_colored_cube(body_pivot, (0.0, 0.12, 0.0), (1.9, 2.4, 1.2), body_color)
        self._add_colored_cube(body_pivot, (0.0, -0.50, -0.16), (1.35, 1.9, 1.0), body_color)
        self._add_colored_cube(body_pivot, (0.0, 0.0, 1.2), (1.25, 1.55, 1.0), body_color)

        leg_points = [(-1.0, -1.05), (-1.15, -0.35), (-1.15, 0.38), (-1.0, 1.08), (1.0, -1.05), (1.15, -0.35), (1.15, 0.38), (1.0, 1.08)]
        for idx, (lx, ly) in enumerate(leg_points):
            side = -1.0 if lx < 0 else 1.0
            socket = body_pivot.attachNewNode(f'leg_socket_{idx}')
            socket.setPos(lx, ly, -0.12)
            self._add_colored_cube(socket, (0.0, 0.0, 0.0), (0.26, 0.26, 0.26), body_color)

            upper = socket.attachNewNode(f'leg_upper_{idx}')
            upper.setPos(0.0, 0.0, -0.10)
            upper.setR(46.0 * side)
            upper.setP(-18.0 + abs(ly) * 4.0)
            self._add_colored_cube(upper, (0.0, 0.0, -1.20), (0.18, 0.18, 1.55), leg_color)

            knee = upper.attachNewNode(f'leg_knee_{idx}')
            knee.setPos(0.56 * side, 0.12 * ly, -2.45)
            knee.setR(26.0 * side)
            knee.setP(34.0)
            self._add_colored_cube(knee, (0.0, 0.0, -1.18), (0.16, 0.16, 1.55), leg_color)

            foot = knee.attachNewNode(f'leg_foot_{idx}')
            foot.setPos(0.62 * side, 0.08 * ly, -2.26)
            foot.setP(50.0)
            self._add_colored_cube(foot, (0.0, 0.0, -0.92), (0.13, 0.13, 1.18), leg_color)

        neck = body_pivot.attachNewNode('neck')
        neck.setPos(0.0, 0.16, 1.22)
        self._add_colored_cube(neck, (0.0, 0.10, 1.72), (0.28, 0.34, 2.2), arm_color)

        head = neck.attachNewNode('head')
        head.setPos(0.0, 0.24, 3.42)
        self._add_colored_cube(head, (0.0, 0.06, 0.0), (0.98, 1.02, 1.18), head_color)
        self._add_colored_cube(head, (0.0, 0.48, 0.12), (0.68, 0.18, 0.28), body_color)
        self._add_colored_cube(head, (-0.18, 0.56, 0.18), (0.09, 0.09, 0.09), eye_color, light_off=True)
        self._add_colored_cube(head, (0.18, 0.56, 0.18), (0.09, 0.09, 0.09), eye_color, light_off=True)

        for side in (-1.0, 1.0):
            shoulder = body_pivot.attachNewNode(f'arm_socket_{int(side)}')
            shoulder.setPos(0.92 * side, -0.10, 1.18)
            self._add_colored_cube(shoulder, (0.0, 0.0, 0.0), (0.24, 0.24, 0.24), body_color)
            arm = shoulder.attachNewNode(f'arm_{int(side)}')
            arm.setR(-24.0 * side)
            arm.setP(12.0)
            self._add_colored_cube(arm, (0.0, 0.0, -1.72), (0.20, 0.20, 1.95), arm_color)
            forearm = arm.attachNewNode(f'forearm_{int(side)}')
            forearm.setPos(0.0, 0.0, -3.46)
            forearm.setP(-28.0)
            self._add_colored_cube(forearm, (0.0, 0.0, -1.86), (0.18, 0.18, 2.18), arm_color)
            hand = forearm.attachNewNode(f'hand_{int(side)}')
            hand.setPos(0.0, 0.0, -4.08)
            self._add_colored_cube(hand, (0.0, 0.0, -0.28), (0.30, 0.30, 0.42), head_color)

        root.setH(self._face_heading_to_point(root.getX(), root.getY(), self.player.pos.x, self.player.pos.y) + 180.0)
        self.zone_monsters.append({
            'type': 'dread',
            'root': root,
            'time': 0.0,
            'teleport_anchor': LPoint3f(spawn_x, spawn_y, ground + 0.5),
            'last_player_pos': LPoint3f(self.player.pos.x, self.player.pos.y, self.player.pos.z),
            'teleport_distance': 18.0,
        })

    def _build_hell_smoke_cluster(self, parent: NodePath, center: tuple[float, float, float], scale: float = 1.0) -> None:
        cx, cy, cz = center
        puffs = [
            ((0.0, 0.0, 0.0), (6.0, 3.4, 1.3), (0.14, 0.04, 0.03, 0.78)),
            ((3.6, 0.8, 0.4), (4.8, 2.2, 1.0), (0.22, 0.06, 0.04, 0.70)),
            ((-3.2, -0.5, 0.2), (4.0, 2.0, 0.9), (0.08, 0.03, 0.03, 0.76)),
            ((0.3, 2.2, 0.0), (5.0, 1.6, 0.8), (0.38, 0.10, 0.06, 0.54)),
        ]
        for (ox, oy, oz), (sx, sy, sz), color in puffs:
            cloud = self._add_colored_cube(
                parent,
                (cx + ox * scale, cy + oy * scale, cz + oz * scale),
                (sx * scale, sy * scale, sz * scale),
                color,
                light_off=True,
                transparency=True,
            )
            cloud.setFogOff()

    def _build_candy_cloud_cluster(self, parent: NodePath, center: tuple[float, float, float], scale: float = 1.0) -> None:
        cx, cy, cz = center
        puffs = [
            ((0.0, 0.0, 0.0), (5.0, 2.6, 1.0), (1.0, 0.78, 0.90, 0.95)),
            ((3.2, 0.6, 0.2), (3.5, 1.9, 0.82), (1.0, 0.88, 0.95, 0.92)),
            ((-3.0, 0.2, 0.1), (3.1, 1.7, 0.74), (0.98, 0.70, 0.86, 0.90)),
            ((0.5, 1.7, 0.0), (4.0, 1.6, 0.70), (1.0, 0.86, 0.93, 0.88)),
        ]
        for (ox, oy, oz), (sx, sy, sz), color in puffs:
            cloud = self._add_colored_cube(
                parent,
                (cx + ox * scale, cy + oy * scale, cz + oz * scale),
                (sx * scale, sy * scale, sz * scale),
                color,
                light_off=True,
                transparency=True,
            )
            cloud.setFogOff()

    def _build_hell_monster(self, parent: NodePath, base_x: float, base_y: float) -> None:
        ground = self.find_surface_floor(int(round(base_x)), int(round(base_y)))
        if ground is None:
            ground = self.find_surface(int(round(base_x)), int(round(base_y)))
        if ground is None:
            ground = 4

        root = parent.attachNewNode('hell_monster')
        root.setPos(base_x + 0.5, base_y + 0.5, ground + 0.5)

        skin = (0.56, 0.10, 0.08, 1.0)
        dark = (0.09, 0.02, 0.02, 1.0)
        horn = (0.76, 0.66, 0.48, 1.0)
        ember = (1.0, 0.44, 0.12, 1.0)
        metal = (0.22, 0.22, 0.26, 1.0)
        wood = (0.32, 0.18, 0.08, 1.0)

        pelvis = root.attachNewNode('pelvis')
        pelvis.setPos(0.0, 0.0, 4.5)
        self._add_colored_cube(pelvis, (0.0, 0.0, 0.0), (2.2, 1.4, 1.2), dark)

        torso = root.attachNewNode('torso')
        torso.setPos(0.0, 0.0, 6.5)
        self._add_colored_cube(torso, (0.0, 0.0, 0.0), (2.5, 1.6, 3.2), skin)
        chest = torso.attachNewNode('chest')
        chest.setPos(0.0, 0.0, 1.8)
        self._add_colored_cube(chest, (0.0, 0.0, 0.0), (2.0, 1.3, 1.8), dark)
        self._add_colored_cube(torso, (0.0, 0.48, 0.4), (1.7, 0.34, 1.2), dark)
        self._add_colored_cube(torso, (0.0, -0.48, 0.2), (1.8, 0.28, 1.0), dark)

        shoulders = root.attachNewNode('shoulders')
        shoulders.setPos(0.0, 0.0, 8.2)
        self._add_colored_cube(shoulders, (0.0, 0.0, 0.0), (3.3, 1.2, 0.9), dark)

        neck = root.attachNewNode('neck')
        neck.setPos(0.0, 0.08, 9.35)
        self._add_colored_cube(neck, (0.0, 0.0, 0.0), (0.62, 0.62, 0.82), skin)

        head = root.attachNewNode('head')
        head.setPos(0.0, 0.1, 10.8)
        self._add_colored_cube(head, (0.0, 0.0, 0.1), (1.55, 1.2, 1.6), skin)
        brow = self._add_colored_cube(head, (0.0, 0.30, 0.38), (1.18, 0.22, 0.26), dark)
        brow.setLightOff()
        jaw = self._add_colored_cube(head, (0.0, 0.46, -0.32), (1.1, 0.34, 0.52), dark)
        jaw.setLightOff()
        self._add_colored_cube(head, (-0.30, 0.58, 0.22), (0.14, 0.14, 0.14), ember, light_off=True)
        self._add_colored_cube(head, (0.30, 0.58, 0.22), (0.14, 0.14, 0.14), ember, light_off=True)

        for side in (-1.0, 1.0):
            horn_base = head.attachNewNode(f'horn_{int(side)}')
            horn_base.setPos(0.72 * side, -0.08, 0.96)
            horn_base.setR(36.0 * side)
            horn_base.setP(-10.0)
            self._add_colored_cube(horn_base, (0.0, 0.0, 0.82), (0.34, 0.28, 1.60), horn)
            horn_mid = horn_base.attachNewNode('mid')
            horn_mid.setPos(0.34 * side, -0.02, 1.62)
            horn_mid.setR(28.0 * side)
            horn_mid.setP(-6.0)
            self._add_colored_cube(horn_mid, (0.0, 0.0, 0.70), (0.28, 0.24, 1.34), horn)
            horn_tip = horn_mid.attachNewNode('tip')
            horn_tip.setPos(0.42 * side, 0.02, 1.30)
            horn_tip.setR(20.0 * side)
            horn_tip.setP(4.0)
            self._add_colored_cube(horn_tip, (0.0, 0.0, 0.56), (0.20, 0.18, 1.02), horn)

        for side in (-1.0, 1.0):
            arm = root.attachNewNode(f'arm_{int(side)}')
            arm.setPos(1.72 * side, 0.02, 8.0)
            arm.setR(-12.0 * side)
            arm.setP(12.0)
            self._add_colored_cube(arm, (0.0, 0.0, -1.58), (0.42, 0.42, 1.92), skin)
            elbow = arm.attachNewNode('elbow')
            elbow.setPos(0.0, 0.0, -3.05)
            elbow.setP(-16.0)
            self._add_colored_cube(elbow, (0.0, 0.0, -1.62), (0.36, 0.36, 1.95), skin)
            hand = elbow.attachNewNode('hand')
            hand.setPos(0.0, 0.0, -3.24)
            self._add_colored_cube(hand, (0.0, 0.0, -0.22), (0.44, 0.44, 0.34), dark)

        for side in (-1.0, 1.0):
            leg = root.attachNewNode(f'leg_{int(side)}')
            leg.setPos(0.72 * side, 0.0, 4.0)
            self._add_colored_cube(leg, (0.0, 0.0, -1.72), (0.52, 0.52, 2.0), dark)
            knee = leg.attachNewNode('knee')
            knee.setPos(0.0, 0.0, -3.28)
            self._add_colored_cube(knee, (0.0, 0.0, -1.78), (0.44, 0.44, 2.1), dark)
            foot = knee.attachNewNode('foot')
            foot.setPos(0.0, 0.62, -3.70)
            self._add_colored_cube(foot, (0.0, 0.0, -0.18), (0.56, 1.10, 0.20), dark)

        grip = root.find('**/arm_1/**/hand')
        if not grip.isEmpty():
            pitchfork = grip.attachNewNode('pitchfork')
            pitchfork.setPos(0.34, 0.06, -0.06)
            pitchfork.setR(-10.0)
            pitchfork.setP(-8.0)
            self._add_colored_cube(pitchfork, (0.0, 0.0, 2.6), (0.08, 0.08, 3.2), wood)
            head_np = pitchfork.attachNewNode('head')
            head_np.setPos(0.0, 0.0, 5.8)
            self._add_colored_cube(head_np, (0.0, 0.0, 0.0), (0.46, 0.12, 0.12), metal)
            for off in (-0.32, 0.0, 0.32):
                tine = head_np.attachNewNode('tine')
                tine.setPos(off, 0.0, 0.62)
                self._add_colored_cube(tine, (0.0, 0.0, 0.34), (0.08, 0.08, 0.72), metal)

        self.zone_monsters.append({
            'type': 'hell',
            'root': root,
            'anchor': LPoint3f(base_x + 0.5, base_y + 0.5, ground + 0.5),
            'time': 0.0,
            'wander_radius': 10.5,
            'speed': 0.34,
        })

    def _update_zone_monsters(self, dt: float) -> None:
        player_xy = LPoint3f(self.player.pos.x, self.player.pos.y, self.player.pos.z)
        for monster in self.zone_monsters:
            root = monster.get('root')
            if root is None or root.isEmpty():
                continue
            monster['time'] = monster.get('time', 0.0) + dt
            t = monster['time']
            mtype = monster.get('type')
            if mtype == 'hell':
                anchor = monster['anchor']
                radius = monster['wander_radius']
                speed = monster['speed']
                target_x = anchor.x + math.sin(t * speed) * radius
                target_y = anchor.y + math.cos(t * speed * 0.78) * (radius * 0.78)
                ground = self.find_surface_floor(int(round(target_x)), int(round(target_y)))
                if ground is None:
                    ground = self.find_surface(int(round(target_x)), int(round(target_y)))
                if ground is None:
                    ground = anchor.z
                current = root.getPos()
                desired = LPoint3f(target_x, target_y, ground + 0.5)
                blend = min(1.0, dt * 1.6)
                root.setPos(current + (desired - current) * blend)
                look_dx = desired.x - current.x
                look_dy = desired.y - current.y
                if abs(look_dx) + abs(look_dy) > 0.02:
                    root.setH(math.degrees(math.atan2(-look_dx, look_dy)))
                root.setP(math.sin(t * 1.2) * 2.2)
                if not root.find('**/arm_1').isEmpty():
                    root.find('**/arm_1').setP(12.0 + math.sin(t * 2.1) * 9.0)
                if not root.find('**/arm_-1').isEmpty():
                    root.find('**/arm_-1').setP(12.0 - math.sin(t * 2.1) * 9.0)
                if not root.find('**/leg_1').isEmpty():
                    root.find('**/leg_1').setP(math.sin(t * 1.8) * 6.0)
                if not root.find('**/leg_-1').isEmpty():
                    root.find('**/leg_-1').setP(-math.sin(t * 1.8) * 6.0)
                pitchfork = root.find('**/pitchfork')
                if not pitchfork.isEmpty():
                    pitchfork.setR(-10.0 + math.sin(t * 1.6) * 3.5)
            elif mtype == 'dread':
                current = root.getPos()
                player_moved = (player_xy - monster.get('last_player_pos', player_xy)).length()
                close_distance = LVector3f(current.x - player_xy.x, current.y - player_xy.y, 0.0).length()
                if close_distance < 24.0:
                    self._teleport_dread_monster(monster, behind_player=True)
                    current = root.getPos()
                elif player_moved > monster.get('teleport_distance', 18.0) or close_distance > 62.0:
                    self._teleport_dread_monster(monster, behind_player=True)
                    current = root.getPos()

                root.setH(self._face_heading_to_point(current.x, current.y, self.player.pos.x, self.player.pos.y) + 180.0)
                body = root.find('**/body_pivot')
                if not body.isEmpty():
                    body.setP(-6.0 + math.sin(t * 1.1) * 1.8)
                    body.setR(math.sin(t * 0.62) * 1.6)
                head = root.find('**/head')
                if not head.isEmpty():
                    head.setH(math.sin(t * 0.9) * 5.0)
                for idx, upper in enumerate(root.findAllMatches('**/leg_upper_*')):
                    upper.setP(-18.0 + math.sin(t * 2.4 + idx * 0.45) * 6.0)
                for idx, knee in enumerate(root.findAllMatches('**/leg_knee_*')):
                    knee.setP(34.0 + math.sin(t * 2.1 + idx * 0.55) * 8.0)
                for idx, foot in enumerate(root.findAllMatches('**/leg_foot_*')):
                    foot.setP(50.0 + math.sin(t * 2.7 + idx * 0.62) * 6.0)
                for idx, arm in enumerate(root.findAllMatches('**/arm_*')):
                    arm.setP(12.0 + math.sin(t * 1.8 + idx * math.pi) * 6.0)
            elif mtype in ('human', 'robot_npc', 'elf'):
                anchor = monster['anchor']
                radius = monster['wander_radius']
                speed = monster['speed']
                target_x = anchor.x + math.sin(t * speed) * radius
                target_y = anchor.y + math.sin(t * speed * 0.72 + 1.2) * radius * 0.85
                target_x, target_y = self._clamp_xy_inside_boundary(target_x, target_y, padding=4.0 if mtype == 'elf' else 5.0)
                current = root.getPos()
                moved = self._move_actor_with_collision(
                    current,
                    target_x,
                    target_y,
                    dt,
                    radius=0.22 if mtype == 'robot_npc' else (0.24 if mtype == 'elf' else 0.28),
                    height=1.85,
                    prefer_floor=False,
                    step_height=0.72,
                    max_blend=1.35,
                )
                z_blend = min(1.0, dt * 7.0)
                smooth_z = current.z + (moved.z - current.z) * z_blend
                root.setPos(moved.x, moved.y, smooth_z)
                look_dx = moved.x - current.x
                look_dy = moved.y - current.y
                walk = math.hypot(look_dx, look_dy)
                if abs(look_dx) + abs(look_dy) > 0.01:
                    target_h = self._face_heading_to_point(current.x, current.y, moved.x, moved.y)
                    current_h = root.getH()
                    delta_h = (target_h - current_h + 180.0) % 360.0 - 180.0
                    root.setH(current_h + delta_h * min(1.0, dt * 8.0))
                rig = monster.get('rig', {})
                sway = math.sin(t * 6.0)
                counter = math.sin(t * 6.0 + math.pi)
                stride = 16.0 if mtype == 'human' else (17.0 if mtype == 'elf' else 18.0)
                arm_swing = 12.0 if mtype == 'human' else (13.0 if mtype == 'elf' else 14.0)
                if walk < 0.001:
                    sway = math.sin(t * 1.6) * 0.2
                    counter = -sway
                    stride = 2.5
                    arm_swing = 3.0
                torso = rig.get('torso')
                chest = rig.get('chest')
                head = rig.get('head_pivot')
                if torso is not None:
                    torso.setP(4.0 + abs(math.sin(t * 3.0)) * 2.0 if mtype == 'robot_npc' else abs(math.sin(t * 3.0)) * (1.8 if mtype == 'elf' else 1.2))
                    torso.setR(math.sin(t * 2.4) * (1.8 if mtype == 'elf' else (1.2 if mtype == 'human' else 2.5)))
                if chest is not None:
                    chest.setP((2.0 if mtype == 'robot_npc' else 0.8) + abs(math.sin(t * 3.0)) * (2.1 if mtype == 'elf' else 1.8))
                if head is not None:
                    head.setH(math.sin(t * 1.6) * (8.5 if mtype == 'elf' else (7.0 if mtype == 'human' else 4.0)))
                for key, mult in [('shoulder_l', 1.0), ('shoulder_r', -1.0)]:
                    part = rig.get(key)
                    if part is not None:
                        part.setP(sway * arm_swing * mult)
                for key, mult in [('forearm_l', -1.0), ('forearm_r', 1.0)]:
                    part = rig.get(key)
                    if part is not None:
                        part.setP(8.0 + counter * 4.5 * mult)
                for key, mult in [('hip_l', -1.0), ('hip_r', 1.0)]:
                    part = rig.get(key)
                    if part is not None:
                        part.setP(sway * stride * mult)
                for key, mult in [('shin_l', 1.0), ('shin_r', -1.0)]:
                    part = rig.get(key)
                    if part is not None:
                        part.setP(10.0 + counter * 8.5 * mult)
            elif mtype == 'glowbug':
                anchor = monster['anchor']
                angle = monster['orbit_angle'] + t * monster['speed']
                radius = monster['orbit_radius'] + math.sin(t * 1.9 + monster['phase']) * 0.55
                bob = math.sin(t * 5.0 + monster['phase']) * 0.28
                bug_x, bug_y = self._clamp_xy_inside_boundary(anchor.x + math.cos(angle) * radius, anchor.y + math.sin(angle * 1.08) * radius, padding=3.5)
                root.setPos(
                    bug_x,
                    bug_y,
                    anchor.z + monster['height_offset'] + bob,
                )
                root.setH(math.degrees(angle))
                for idx, wing in enumerate(root.findAllMatches('**/wing*')):
                    wing.setR(math.sin(t * 18.0 + idx * math.pi) * 28.0)
                glow = 0.72 + 0.28 * (0.5 + 0.5 * math.sin(t * 7.0 + monster['phase']))
                root.setColorScale(glow, glow, glow, 1.0)
            elif mtype == 'candy_blimp':
                anchor = monster['anchor']
                blimp_x, blimp_y = self._clamp_xy_inside_boundary(anchor.x + math.sin(t * 0.16) * 6.0, anchor.y + math.cos(t * 0.13) * 4.0, padding=8.0)
                root.setPos(blimp_x, blimp_y, anchor.z + math.sin(t * 0.72) * 0.9)
                root.setH(t * 4.0)
                basket = root.find('**/basket')
                if not basket.isEmpty():
                    basket.setP(math.sin(t * 1.4) * 2.5)
            elif mtype == 'whale':
                anchor = monster['anchor']
                radius = monster.get('orbit_radius', 54.0)
                speed = monster.get('speed', 0.06)
                ang = t * speed
                x = anchor.x + math.cos(ang) * radius
                y = anchor.y + math.sin(ang * 0.84) * (radius * 0.72)
                x, y = self._clamp_xy_inside_boundary(x, y, padding=10.0)
                z = anchor.z - 0.25 + math.sin(t * 0.55) * 0.35
                root.setPos(x, y, z)
                root.setH(math.degrees(ang) + 90.0)
                body = root.find('**/body')
                if not body.isEmpty():
                    body.setP(math.sin(t * 1.2) * 2.2)
                for node in root.findAllMatches('**/fluke*'):
                    node.setP(math.sin(t * 2.0) * 12.0)
                for node in root.findAllMatches('**/fin*'):
                    node.setP(math.sin(t * 1.5) * 8.0)

            elif mtype == 'snowflake':
                anchor = monster['anchor']
                root.setX(anchor.x + math.sin(t * 0.7 + monster['phase']) * monster['drift_radius'] * 0.45 + math.cos(t * 1.7 + monster['phase']) * 0.55)
                root.setY(anchor.y + math.cos(t * 0.6 + monster['phase']) * monster['drift_radius'] * 0.45 + math.sin(t * 1.3 + monster['phase']) * 0.45)
                root.setZ(root.getZ() - monster['fall_speed'] * dt)
                ground = self._ground_height_for_zone(root.getX(), root.getY(), prefer_floor=False) + 0.7
                if root.getZ() <= ground:
                    root.setZ(anchor.z + 8.0 + abs(math.sin(t * 0.8 + monster['phase'])) * 6.0)
            elif mtype == 'cactus_sage':
                blink = abs(math.sin(t * 0.9))
                for pupil_np in root.findAllMatches('**/pupil*'):
                    pupil_np.setZ(6.45 + math.sin(t * 0.7) * 0.02)
                eye_scale_z = 0.30 if blink > 0.08 else 0.05
                for eye_np in root.findAllMatches('**/eye_white*'):
                    scale = eye_np.getScale()
                    eye_np.setScale(scale.x, scale.y, eye_scale_z)

    def _rebuild_zone_setpieces(self) -> None:
        self._clear_zone_setpieces()

        look_x, look_y = self._look_vector()
        right_x, right_y = look_y, -look_x
        px, py = self.player.pos.x, self.player.pos.y

        self._build_world_boundary(self.zone_setpieces_root)

        if self.active_zone_key == 'polar_zone':
            self._build_snow_flurry(self.zone_setpieces_root, (px, py, self._ground_height_for_zone(px, py) + 0.8), count=24, radius=12.0)
            self._build_polar_elf(self.zone_setpieces_root, px + look_x * 7.0 + right_x * 4.0, py + look_y * 7.0 + right_y * 4.0, 0)
            self._build_polar_elf(self.zone_setpieces_root, px + look_x * 10.0 - right_x * 3.5, py + look_y * 10.0 - right_y * 3.5, 1)
            self._build_polar_elf(self.zone_setpieces_root, px + look_x * 5.5 - right_x * 6.0, py + look_y * 5.5 - right_y * 6.0, 2)
            self.sound.refresh_zone_audio(self.active_zone_key, self.zone_setpieces_root, self.zone_monsters)
            return

        if self.active_zone_key == 'day_zone':
            self._build_cloud_cluster(self.zone_setpieces_root, (px + look_x * 12.0, py + look_y * 12.0, 19.0), 0.86)
            human_x, human_y = self._clamp_xy_inside_boundary(px + look_x * 5.5 + right_x * 2.8, py + look_y * 5.5 + right_y * 2.8, padding=4.0)
            self._build_day_human(self.zone_setpieces_root, human_x - 0.5, human_y - 0.5)
            self.sound.refresh_zone_audio(self.active_zone_key, self.zone_setpieces_root, self.zone_monsters)
            return

        if self.active_zone_key == 'night_zone':
            self._build_night_sky(self.zone_setpieces_root, (px, py, 0.0), radius=128.0, height=28.0, count=150)
            self._build_cloud_cluster(self.zone_setpieces_root, (px + look_x * 14.0, py + look_y * 15.0, 18.0), 0.72)
            self._build_glow_bug_swarm(self.zone_setpieces_root, (px + look_x * 10.0 - right_x * 6.0, py + look_y * 10.0 - right_y * 6.0, 8.0), count=10, radius=5.8)
            self.sound.refresh_zone_audio(self.active_zone_key, self.zone_setpieces_root, self.zone_monsters)
            return

        if self.active_zone_key == 'tech_zone':
            self._build_tech_starfield(self.zone_setpieces_root, (px, py, 0.0), radius=130.0, height=34.0, count=180)
            city_x, city_y = self._clamp_xy_inside_boundary(px + look_x * 18.0, py + look_y * 18.0, padding=20.0)
            self._build_tech_cityscape(self.zone_setpieces_root, (city_x, city_y, 4.0), width=34.0, depth=28.0)
            robot_x, robot_y = self._clamp_xy_inside_boundary(px + look_x * 7.0 - right_x * 3.0, py + look_y * 7.0 - right_y * 3.0, padding=4.5)
            self._build_tech_robot(self.zone_setpieces_root, robot_x - 0.5, robot_y - 0.5)
            self.sound.refresh_zone_audio(self.active_zone_key, self.zone_setpieces_root, self.zone_monsters)
            return

        if self.active_zone_key == 'dread_zone':
            self._build_cloud_cluster(self.zone_setpieces_root, (px + look_x * 14.0, py + look_y * 16.0, 22.0), 1.0)
            self._build_cloud_cluster(self.zone_setpieces_root, (px - right_x * 12.0 + look_x * 10.0, py - right_y * 12.0 + look_y * 12.0, 20.5), 0.82)
            self._build_cloud_cluster(self.zone_setpieces_root, (px + right_x * 15.0 + look_x * 22.0, py + right_y * 15.0 + look_y * 20.0, 23.0), 0.92)

            monster_x, monster_y = self._clamp_xy_inside_boundary(px + look_x * 26.0 + right_x * 4.0, py + look_y * 26.0 + right_y * 4.0, padding=10.0)
            self._build_dread_monster(self.zone_setpieces_root, monster_x - 0.5, monster_y - 0.5)
            self.sound.refresh_zone_audio(self.active_zone_key, self.zone_setpieces_root, self.zone_monsters)
            return

        if self.active_zone_key == 'hell_zone':
            self._build_hell_smoke_cluster(self.zone_setpieces_root, (px + look_x * 10.0, py + look_y * 18.0, 21.5), 1.0)
            self._build_hell_smoke_cluster(self.zone_setpieces_root, (px - right_x * 14.0 + look_x * 8.0, py - right_y * 14.0 + look_y * 10.0, 19.5), 0.88)
            self._build_hell_smoke_cluster(self.zone_setpieces_root, (px + right_x * 16.0 + look_x * 24.0, py + right_y * 16.0 + look_y * 22.0, 22.5), 1.05)

            monster_x, monster_y = self._clamp_xy_inside_boundary(px + look_x * 24.0 + right_x * 6.0, py + look_y * 24.0 + right_y * 6.0, padding=10.0)
            self._build_hell_monster(self.zone_setpieces_root, monster_x - 0.5, monster_y - 0.5)
            self.sound.refresh_zone_audio(self.active_zone_key, self.zone_setpieces_root, self.zone_monsters)
            return

        if self.active_zone_key == 'candy_zone':
            self._build_candy_cloud_cluster(self.zone_setpieces_root, (px + look_x * 10.0, py + look_y * 14.0, 18.0), 1.0)
            self._build_candy_cloud_cluster(self.zone_setpieces_root, (px - right_x * 13.0 + look_x * 15.0, py - right_y * 13.0 + look_y * 12.0, 19.5), 0.90)
            self._build_candy_cloud_cluster(self.zone_setpieces_root, (px + right_x * 15.0 + look_x * 24.0, py + right_y * 15.0 + look_y * 20.0, 21.0), 1.08)
            blimp_x, blimp_y = self._clamp_xy_inside_boundary(px + look_x * 20.0 + right_x * 9.5, py + look_y * 20.0 + right_y * 9.5, padding=8.0)
            self._build_candy_blimp(self.zone_setpieces_root, (blimp_x, blimp_y, 26.0))
            self.sound.refresh_zone_audio(self.active_zone_key, self.zone_setpieces_root, self.zone_monsters)
            return

        if self.active_zone_key == 'desert_zone':
            self._build_cloud_cluster(self.zone_setpieces_root, (px + look_x * 18.0, py + look_y * 20.0, 22.0), 0.62)
            cactus_x, cactus_y = self._clamp_xy_inside_boundary(px + look_x * 15.0 + right_x * 4.5, py + look_y * 15.0 + right_y * 4.5, padding=7.0)
            self._build_desert_cactus(self.zone_setpieces_root, cactus_x - 0.5, cactus_y - 0.5)
            self.sound.refresh_zone_audio(self.active_zone_key, self.zone_setpieces_root, self.zone_monsters)
            return

        if self.active_zone_key == 'tropical_zone':
            self._build_tropical_ocean(self.zone_setpieces_root, (0.0, 0.0, 1.0), size=self.world.get_boundary_inner_half_extent(3.0) - 2.0)
            self._build_cloud_cluster(self.zone_setpieces_root, (px + look_x * 16.0, py + look_y * 16.0, 22.0), 0.78)
            self._build_cloud_cluster(self.zone_setpieces_root, (px - right_x * 14.0 + look_x * 12.0, py - right_y * 14.0 + look_y * 11.0, 19.5), 0.68)
            self._build_tropical_whale(self.zone_setpieces_root, (0.0, 0.0, 1.25), radius=min(22.0, self.world.get_boundary_inner_half_extent(10.0) - 8.0))
            self.sound.refresh_zone_audio(self.active_zone_key, self.zone_setpieces_root, self.zone_monsters)
            return

        self.sound.refresh_zone_audio(self.active_zone_key, self.zone_setpieces_root, self.zone_monsters)

    def _render_loading_frame(self) -> None:
        if self.graphicsEngine:
            self.graphicsEngine.renderFrame()
            self.graphicsEngine.renderFrame()

    def _begin_loading_screen(self, title: str, detail: str, progress: float = 0.0) -> None:
        self.hit_highlight.hide()
        self.place_preview.hide()
        if self.world and self.world.parent:
            self.world.parent.hide()
        if self.zone_setpieces_root:
            self.zone_setpieces_root.hide()
        self.ui.show_loading(title, detail, progress)
        self._render_loading_frame()

    def _end_loading_screen(self, status: str = 'Ready') -> None:
        if self.world and self.world.parent:
            self.world.parent.show()
        if self.zone_setpieces_root:
            self.zone_setpieces_root.show()
        self.ui.hide_loading()
        self.ui.set_status(status)
        self.ui.set_zone(self.current_zone_name)
        self.sound.play_ui('loading_done')
        self._render_loading_frame()

    def _look_vector(self) -> tuple[float, float]:
        return math.sin(math.radians(self.camera_yaw)), math.cos(math.radians(self.camera_yaw))

    def _run_preload_for_position(self, title: str, x: float, y: float, start_progress: float, end_progress: float, detail_prefix: str) -> None:
        look_x, look_y = self._look_vector()

        def on_progress(index: int, total: int, key: tuple[int, int]) -> None:
            ratio = index / max(1, total)
            progress = start_progress + (end_progress - start_progress) * ratio
            self.ui.show_loading(title, f'{detail_prefix} {index}/{total}   chunk {key[0]}, {key[1]}', progress)
            self._render_loading_frame()

        self.world.preload_chunk_shell(x, y, look_x, look_y, progress_callback=on_progress)

    def _preload_current_position(self, title: str) -> None:
        self._begin_loading_screen(title, 'Preparing visible chunks...', 0.03)
        self._run_preload_for_position(title, self.player.pos.x, self.player.pos.y, 0.06, 1.00, f'Building {self.current_zone_name}')
        look_x, look_y = self._look_vector()
        self.world.update_loaded_chunks(self.player.pos.x, self.player.pos.y, look_x, look_y)
        self.camera_target = self.player.get_camera_anchor_pos()
        self.camera_focus = self.player.get_camera_look_pos()
        self._update_camera(1.0)
        self._rebuild_zone_setpieces()
        self._end_loading_screen(f'{self.current_zone_name} ready - buddies secure')

    def _bootstrap_initial_start(self, title: str) -> None:
        self._ensure_zone_dirs()
        self._begin_loading_screen(title, f'Opening {self.current_zone_name}...', 0.02)
        self._run_preload_for_position(title, 0.5, 0.5, 0.06, 0.62, f'Generating {self.current_zone_name}')
        self._spawn_player()
        self._save_current_zone_state()
        self._run_preload_for_position(title, self.player.pos.x, self.player.pos.y, 0.62, 1.00, 'Finalizing start area')
        look_x, look_y = self._look_vector()
        self.world.update_loaded_chunks(self.player.pos.x, self.player.pos.y, look_x, look_y)
        self.camera_target = self.player.get_camera_anchor_pos()
        self.camera_focus = self.player.get_camera_look_pos()
        self._update_camera(1.0)
        self._rebuild_zone_setpieces()
        self._end_loading_screen(f'{self.current_zone_name} ready - buddies secure')

    def _spawn_player(self, origin_x: int = 0, origin_y: int = 0, search_radius: int = 20) -> None:
        spawn_x = origin_x + 0.5
        spawn_y = origin_y + 0.5
        spawn_z = 10.0
        best = None
        for radius in range(0, search_radius):
            found = False
            for x in range(origin_x - radius, origin_x + radius + 1):
                for y in range(origin_y - radius, origin_y + radius + 1):
                    top = self.find_surface_floor(x, y) if self.active_zone_key == 'hell_zone' else self.find_surface(x, y)
                    if top is not None:
                        best = (x + 0.5, y + 0.5, top + 3.4)
                        found = True
                        break
                if found:
                    break
            if found:
                break
        if best is not None:
            spawn_x, spawn_y, spawn_z = best
        spawn_x, spawn_y = self._clamp_xy_inside_boundary(spawn_x, spawn_y, padding=2.0)
        self.player.set_pos(spawn_x, spawn_y, spawn_z)
        self.camera_target = self.player.get_camera_anchor_pos()
        self.camera_focus = self.player.get_camera_look_pos()
        self.camera_pos = self.camera_target + LVector3f(0, -self.camera_distance, CAMERA_HEIGHT * 0.72)
        self.camera.setPos(self.camera_pos)

    def _place_player_for_zone_state(self, preferred_pos: tuple[float, float, float] | None) -> None:
        if preferred_pos is not None:
            x, y, z = preferred_pos
            self._spawn_player(int(round(x - 0.5)), int(round(y - 0.5)), search_radius=10)
            x, y = self._clamp_xy_inside_boundary(x, y, padding=2.0)
            self.player.set_pos(x, y, max(2.0, z))
            self.camera_target = self.player.get_camera_anchor_pos()
            self.camera_focus = self.player.get_camera_look_pos()
        else:
            self._spawn_player()

    def _save_current_zone_state(self) -> None:
        self.zone_states[self.active_zone_key] = {
            'seed': self.seed,
            'player_pos': (self.player.pos.x, self.player.pos.y, self.player.pos.z),
            'modifications': dict(self.world.modifications),
        }

    def find_surface(self, x: int, y: int) -> int | None:
        for z in range(22, -1, -1):
            if self.world.get_block(x, y, z) != 0 and self.world.get_block(x, y, z + 1) == 0:
                return z
        return None

    def find_surface_floor(self, x: int, y: int) -> int | None:
        for z in range(0, 23):
            if self.world.get_block(x, y, z) != 0 and self.world.get_block(x, y, z + 1) == 0:
                return z
        return None

    def _bind_inputs(self) -> None:
        bindings = [
            ('w', 'forward', True), ('w-up', 'forward', False),
            ('s', 'backward', True), ('s-up', 'backward', False),
            ('a', 'left', True), ('a-up', 'left', False),
            ('d', 'right', True), ('d-up', 'right', False),
            ('space', 'ascend', True), ('space-up', 'ascend', False),
            ('lalt', 'descend', True), ('lalt-up', 'descend', False),
            ('shift', 'sprint', True), ('shift-up', 'sprint', False),
            ('arrow_left', 'turn_left', True), ('arrow_left-up', 'turn_left', False),
            ('arrow_right', 'turn_right', True), ('arrow_right-up', 'turn_right', False),
            ('arrow_up', 'look_up', True), ('arrow_up-up', 'look_up', False),
            ('arrow_down', 'look_down', True), ('arrow_down-up', 'look_down', False),
        ]
        for event_name, attr, value in bindings:
            self.accept(event_name, setattr, [self.input_state, attr, value])

        self.accept('escape', self.handle_escape)
        self.accept('wheel_up', self.adjust_camera_zoom, [-self.camera_zoom_step])
        self.accept('wheel_down', self.adjust_camera_zoom, [self.camera_zoom_step])
        self.accept('q', self.cycle_hotbar, [-1])
        self.accept('e', self.cycle_hotbar, [1])
        self.accept('h', self.toggle_help)
        self.accept('f3', self.toggle_debug)
        self.accept('v', self.toggle_camera_mode)
        self.accept('tab', self.toggle_zone)
        self.accept('z', self.toggle_zone_portal)
        self.accept('[', self.change_world_size, [-1])
        self.accept(']', self.change_world_size, [1])
        zone_hotkeys = {'0': 'polar_zone', '1': 'day_zone', '2': 'night_zone', '3': 'dread_zone', '4': 'hell_zone', '5': 'candy_zone', '6': 'desert_zone', '7': 'tropical_zone', '8': 'tech_zone', '9': 'tropical_zone'}
        for key_name, zone_key in zone_hotkeys.items():
            self.accept(key_name, self._switch_to_zone_key, [zone_key])

    def toggle_help(self) -> None:
        self.ui.toggle_help()

    def toggle_debug(self) -> None:
        self.ui.toggle_debug()

    def toggle_camera_mode(self) -> None:
        self.first_person = not self.first_person
        self.ui.set_status('First-person camera' if self.first_person else 'Third-person camera')
        self.status_timer = 1.5

    def adjust_camera_zoom(self, delta: float) -> None:
        if self.paused:
            return
        self.camera_distance = max(self.camera_distance_min, min(self.camera_distance_max, self.camera_distance + delta))
        if self.first_person:
            self.ui.set_status('Zoom stored for third-person')
        else:
            self.ui.set_status(f'Camera zoom {self.camera_distance:.1f}')
        self.status_timer = 0.8

    def cycle_hotbar(self, direction: int) -> None:
        self.selected_index = (self.selected_index + direction) % len(HOTBAR_IDS)
        self.ui.refresh_hotbar(self.selected_index)

    def select_hotbar(self, index: int) -> None:
        self.selected_index = max(0, min(len(HOTBAR_IDS) - 1, index))
        self.ui.refresh_hotbar(self.selected_index)

    def _switch_to_zone_key(self, next_zone_key: str) -> None:
        if self.paused or next_zone_key == self.active_zone_key or next_zone_key not in ZONE_DEFS:
            return
        self._save_current_zone_state()
        next_zone = ZONE_DEFS[next_zone_key]
        state = self.zone_states.get(next_zone_key)
        if state is None:
            state = {
                'seed': DEFAULT_SEED + next_zone.seed_offset,
                'player_pos': (self.player.pos.x, self.player.pos.y, self.player.pos.z),
                'modifications': {},
            }
            self.zone_states[next_zone_key] = state

        self.active_zone_key = next_zone_key
        self.seed = int(state.get('seed', DEFAULT_SEED + next_zone.seed_offset))
        self._apply_zone_visuals(next_zone_key)
        self.world.reset_world(self.seed, dict(state.get('modifications', {})))
        self._place_player_for_zone_state(state.get('player_pos'))
        self._preload_current_position(f'Switching to {next_zone.name}')
        self._save_current_zone_state()
        self.sound.play_ui('zone_switch')
        self.ui.set_status(f'Entered {next_zone.name}')
        self.status_timer = 2.0

    def select_zone_by_index(self, index: int) -> None:
        if index < 0 or index >= len(ZONE_ORDER):
            return
        self._switch_to_zone_key(ZONE_ORDER[index])

    def toggle_zone(self) -> None:
        current_index = ZONE_ORDER.index(self.active_zone_key)
        next_zone_key = ZONE_ORDER[(current_index + 1) % len(ZONE_ORDER)]
        self._switch_to_zone_key(next_zone_key)

    def get_selected_block_id(self) -> int:
        return HOTBAR_IDS[self.selected_index]

    def get_selected_block_name(self) -> str:
        from .constants import BLOCK_DEFS
        return BLOCK_DEFS[self.get_selected_block_id()].name

    def change_world_size(self, delta: int) -> None:
        self.set_world_size(self.world_size_chunks + int(delta))

    def set_world_size(self, size_chunks: int) -> None:
        target = max(MIN_WORLD_SIZE_CHUNKS, min(MAX_WORLD_SIZE_CHUNKS, int(round(size_chunks))))
        if target == self.world_size_chunks:
            self.ui.set_status(f'World size already {target} chunks')
            self.status_timer = 1.2
            self.ui.refresh_world_size()
            return

        self._save_current_zone_state()
        active_state = self.zone_states.get(self.active_zone_key, {})
        target_pos = active_state.get('player_pos', (self.player.pos.x, self.player.pos.y, self.player.pos.z))
        self.world_size_chunks = target
        self.world.set_world_size(target)
        self.world.reset_world(self.seed, dict(active_state.get('modifications', {})))
        self._apply_zone_visuals(self.active_zone_key)
        self._place_player_for_zone_state(target_pos)
        self._preload_current_position(f'Resizing world to {target} chunks')
        self._save_current_zone_state()
        self.ui.refresh_world_size()
        self.ui.set_status(f'World size {target} chunks')
        self.status_timer = 2.0

    def handle_escape(self) -> None:
        if self.zone_portal_open:
            self.toggle_zone_portal(False)
            return
        self.toggle_pause()

    def toggle_zone_portal(self, value: bool | None = None) -> None:
        if self.paused and not self.zone_portal_open and value is not False:
            return
        self.zone_portal_open = (not self.zone_portal_open) if value is None else bool(value)
        self.ui.show_zone_portal(self.zone_portal_open)
        if self.zone_portal_open:
            self.ui.show_menu(False)
            self.capture_mouse(False)
            self.sound.play_ui('portal_open')
            self.ui.set_status('Zone portal open')
        else:
            self.capture_mouse(not self.paused)
            self.sound.play_ui('portal_close')
            self.ui.set_status('Zone portal closed')
            self.status_timer = 0.8

    def portal_select_zone(self, zone_key: str) -> None:
        was_open = self.zone_portal_open
        self.zone_portal_open = False
        self.ui.show_zone_portal(False)
        self.capture_mouse(not self.paused)
        if zone_key != self.active_zone_key:
            self._switch_to_zone_key(zone_key)
        elif was_open:
            self.ui.set_status(f'{self.current_zone_name} selected')
            self.status_timer = 1.0

    def toggle_pause(self, value: bool | None = None) -> None:
        if self.zone_portal_open:
            self.zone_portal_open = False
            self.ui.show_zone_portal(False)
        self.paused = (not self.paused) if value is None else bool(value)
        self.ui.show_menu(self.paused)
        self.capture_mouse(not self.paused)
        if self.paused:
            self.sound.play_ui('pause_on')
            self.ui.set_status('Paused')
        else:
            self.sound.play_ui('pause_off')
            self.ui.set_status('Resumed')
            self.status_timer = 1.0

    def exit_game(self) -> None:
        self.ui.set_status('Exiting Zonez')
        self.userExit()

    def capture_mouse(self, captured: bool) -> None:
        props = WindowProperties()
        if captured:
            props.setCursorHidden(True)
            props.setMouseMode(WindowProperties.M_relative)
        else:
            props.setCursorHidden(False)
            props.setMouseMode(WindowProperties.M_absolute)
        if self.win and hasattr(self.win, 'requestProperties'):
            self.win.requestProperties(props)
            if hasattr(self.win, 'movePointer') and hasattr(self.win, 'getXSize') and hasattr(self.win, 'getYSize'):
                self.win.movePointer(0, self.win.getXSize() // 2, self.win.getYSize() // 2)
        self.mouse_dx_filtered = 0.0
        self.mouse_dy_filtered = 0.0
        self.mouse_captured = captured

    def current_mouse_delta(self) -> tuple[float, float]:
        if not self.mouse_captured or not self.win or not hasattr(self.win, 'getPointer'):
            return 0.0, 0.0
        pointer = self.win.getPointer(0)
        x = pointer.getX()
        y = pointer.getY()
        center_x = self.win.getXSize() // 2 if hasattr(self.win, 'getXSize') else 0
        center_y = self.win.getYSize() // 2 if hasattr(self.win, 'getYSize') else 0
        props = self.win.getProperties() if hasattr(self.win, 'getProperties') else None
        mouse_mode = props.getMouseMode() if props else WindowProperties.M_absolute
        if mouse_mode == WindowProperties.M_relative:
            dx = x
            dy = y
        else:
            dx = x - center_x
            dy = y - center_y
            if hasattr(self.win, 'movePointer'):
                self.win.movePointer(0, center_x, center_y)
        return float(dx), float(dy)

    def update_task(self, task):
        dt = min(globalClock.getDt(), 1 / 20)
        active_motion = False
        if not self.paused and not self.zone_portal_open:
            self._update_camera_rotation(dt)
            self.player.update(dt, self.input_state, self.camera_yaw, self.camera_pitch)
            active_motion = True
            if getattr(self.player, 'bumped_boundary', False):
                self.sound.play_boundary(self.player.root)
            look_x, look_y = self._look_vector()
            self.world.update_loaded_chunks(self.player.pos.x, self.player.pos.y, look_x, look_y)
            self._update_camera(dt)
            self.hit_highlight.hide()
            self.place_preview.hide()
            self._update_debug()
            self._update_zone_monsters(dt)
            self._save_current_zone_state()
        self.sound.update(dt, self.player, self.zone_monsters, active=active_motion)
        return task.cont

    def _update_camera_rotation(self, dt: float) -> None:
        dx, dy = self.current_mouse_delta()
        smooth = min(1.0, dt * CAMERA_MOUSE_SMOOTHING)
        self.mouse_dx_filtered += (dx - self.mouse_dx_filtered) * smooth
        self.mouse_dy_filtered += (dy - self.mouse_dy_filtered) * smooth
        self.camera_yaw -= self.mouse_dx_filtered * MOUSE_SENSITIVITY
        self.camera_pitch = max(-82.0, min(68.0, self.camera_pitch - self.mouse_dy_filtered * MOUSE_SENSITIVITY))

        key_turn_speed = 112.0
        key_pitch_speed = 84.0
        if self.input_state.turn_left:
            self.camera_yaw += key_turn_speed * dt
        if self.input_state.turn_right:
            self.camera_yaw -= key_turn_speed * dt
        if self.input_state.look_up:
            self.camera_pitch += key_pitch_speed * dt
        if self.input_state.look_down:
            self.camera_pitch -= key_pitch_speed * dt
        self.camera_pitch = max(-82.0, min(68.0, self.camera_pitch))
        self.camera_yaw = (self.camera_yaw + 180.0) % 360.0 - 180.0

        decay = max(0.0, 1.0 - dt * 12.0)
        self.mouse_dx_filtered *= decay
        self.mouse_dy_filtered *= decay

    def _update_camera(self, dt: float) -> None:
        anchor = self.player.get_camera_anchor_pos()
        look_origin = self.player.get_camera_look_pos()
        self.camera_target = self.camera_target + (anchor - self.camera_target) * min(1.0, dt * CAMERA_SMOOTHING)

        yaw_rad = math.radians(self.camera_yaw)
        pitch_rad = math.radians(self.camera_pitch)
        forward = LVector3f(
            math.sin(yaw_rad) * math.cos(pitch_rad),
            math.cos(yaw_rad) * math.cos(pitch_rad),
            math.sin(pitch_rad),
        )
        forward.normalize()
        flat_forward = LVector3f(math.sin(yaw_rad), math.cos(yaw_rad), 0.0)
        if flat_forward.length_squared() < 1e-6:
            flat_forward = LVector3f(0.0, 1.0, 0.0)
        flat_forward.normalize()

        if self.first_person:
            eye = self.player.get_eye_pos()
            cam_pos = eye + forward * 0.05
            look_at = eye + forward * 4.0
            self.camera_pos = LPoint3f(cam_pos)
            self.camera_focus = LPoint3f(look_at)
        else:
            pivot = self.camera_target + LVector3f(0.0, 0.0, 0.06)
            desired = pivot - forward * self.camera_distance + LVector3f(0.0, 0.0, CAMERA_HEIGHT * 0.16)
            collision_safe = self.world.pick_camera_target(pivot, desired)
            self.camera_pos = self.camera_pos + (collision_safe - self.camera_pos) * min(1.0, dt * CAMERA_POSITION_SMOOTHING)
            cam_pos = self.camera_pos
            desired_look = look_origin + flat_forward * 2.0 + LVector3f(0.0, 0.0, 0.10)
            self.camera_focus = self.camera_focus + (desired_look - self.camera_focus) * min(1.0, dt * 10.0)
            look_at = self.camera_focus

        self.camera.setPos(cam_pos)
        self.camera.lookAt(look_at)

    def _camera_pick(self):
        origin = self.camera.getPos(self.render)
        direction = self.camera.getQuat(self.render).getForward()
        return self.world.raycast_blocks(origin, direction)

    def _update_block_preview(self) -> None:
        self.hit_highlight.hide()
        self.place_preview.hide()

    def remove_block(self) -> None:
        return

    def place_block(self) -> None:
        return

    def _update_debug(self) -> None:
        if not self.ui.debug_visible:
            self.ui.refresh_debug('', hide=True)
            return
        pos = self.player.pos
        cx, cy = self.world.world_to_chunk(int(pos.x), int(pos.y))
        loaded = sum(1 for chunk in self.world.chunks.values() if chunk.root is not None)
        debug = (
            f'Zone: {self.current_zone_name}\n'
            f'FPS: {ClockObject.getGlobalClock().getAverageFrameRate():.1f}\n'
            f'Pos: ({pos.x:.2f}, {pos.y:.2f}, {pos.z:.2f})\n'
            f'Chunk: ({cx}, {cy})  Loaded: {loaded}\n'
            f'World size: {self.world.get_world_size_chunks()} chunks\n'
            f'Boundary half-extent: {self.world.get_boundary_half_extent():.0f}u\n'
            f'Seed: {self.seed}\n'
            f'Cached Chunks: {len(self.world.chunks)}\n'
            f'Modified Blocks: {len(self.world.modifications)}\n'
            f'Greedy quads: {self.world.total_opaque_quads + self.world.total_transparent_quads} '
            f'(opaque {self.world.total_opaque_quads} / alpha {self.world.total_transparent_quads})'
        )
        self.ui.refresh_debug(debug)

    def status_task(self, task):
        dt = globalClock.getDt()
        if self.status_timer > 0:
            self.status_timer -= dt
            if self.status_timer <= 0:
                self.ui.set_status('')
        return task.cont

    def save_game(self) -> None:
        self._save_current_zone_state()
        path = self.save_system.save(self.active_zone_key, self.zone_states, world_size_chunks=self.world_size_chunks)
        self.ui.set_status(f'Saved zones: {path.name}')
        self.status_timer = 2.0

    def load_game(self) -> None:
        payload = self.save_system.load()
        if not payload:
            self.ui.set_status('No zone save found')
            self.status_timer = 2.0
            return
        loaded_states = payload.get('zones', {})
        for zone_key in ZONE_ORDER:
            if zone_key not in loaded_states:
                loaded_states[zone_key] = self.zone_states.get(zone_key, {
                    'seed': DEFAULT_SEED + ZONE_DEFS[zone_key].seed_offset,
                    'player_pos': (0.5, 0.5, 10.0),
                    'modifications': {},
                })
        loaded_world_size = payload.get('world_size_chunks')
        if loaded_world_size is not None:
            self.world_size_chunks = max(MIN_WORLD_SIZE_CHUNKS, min(MAX_WORLD_SIZE_CHUNKS, int(loaded_world_size)))
            self.world.set_world_size(self.world_size_chunks)
        self.zone_states = loaded_states
        self.active_zone_key = payload.get('active_zone', self.active_zone_key)
        active_state = self.zone_states[self.active_zone_key]
        self.seed = int(active_state.get('seed', DEFAULT_SEED))
        self.world.reset_world(self.seed, dict(active_state.get('modifications', {})))
        self._apply_zone_visuals(self.active_zone_key)
        self._place_player_for_zone_state(active_state.get('player_pos'))
        self._preload_current_position(f'Loading {self.current_zone_name}')
        self._save_current_zone_state()
        self.ui.set_status(f'Loaded {self.current_zone_name}')
        self.status_timer = 2.0

    def regenerate_world(self) -> None:
        zone_def = ZONE_DEFS[self.active_zone_key]
        base_seed = self.rng.randint(1, 99999999)
        zone_seed = base_seed + zone_def.seed_offset
        self.seed = zone_seed
        self.world.reset_world(zone_seed, {})
        self.zone_states[self.active_zone_key] = {
            'seed': zone_seed,
            'player_pos': (0.5, 0.5, 10.0),
            'modifications': {},
        }
        self._spawn_player()
        self._preload_current_position(f'Generating new {self.current_zone_name}')
        self._save_current_zone_state()
        self.ui.set_status(f'New seed: {zone_seed}')
        self.status_timer = 2.0
