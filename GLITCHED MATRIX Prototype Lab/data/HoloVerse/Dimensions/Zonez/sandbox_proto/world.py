from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from panda3d.core import (
    Geom,
    GeomNode,
    GeomTriangles,
    GeomVertexData,
    GeomVertexFormat,
    GeomVertexWriter,
    LPoint3f,
    LVector3f,
    NodePath,
    Texture,
    TransparencyAttrib,
)

from .constants import (
    BLOCK_DEFS,
    CAMERA_COLLISION_PADDING,
    CHUNK_SIZE,
    FADE_RADIUS,
    INITIAL_BOOTSTRAP_RADIUS,
    FORWARD_PRELOAD_BIAS,
    FORWARD_PRELOAD_RADIUS,
    FORCE_READY_RADIUS,
    LOAD_RADIUS,
    MAX_CACHED_CHUNKS,
    MAX_CHUNK_GENERATIONS_PER_FRAME,
    MAX_CHUNK_REBUILDS_PER_FRAME,
    MAX_RAY_DISTANCE,
    UNLOAD_RADIUS,
    WATER_LEVEL,
    WORLD_BOUNDARY_CHUNK_RADIUS,
    WORLD_BOUNDARY_MARGIN,
    WORLD_HEIGHT_LIMIT,
)
from .noise import fractal_noise_2d
from .textures import build_texture_atlas, get_face_tile, get_tile_uv


@dataclass
class Chunk:
    key: tuple[int, int]
    base_blocks: dict[tuple[int, int, int], int] = field(default_factory=dict)
    root: NodePath | None = None
    generated: bool = False
    dirty: bool = True
    last_touched: int = 0
    opaque_quad_count: int = 0
    transparent_quad_count: int = 0


@dataclass(frozen=True)
class FaceMask:
    block_id: int
    axis: int
    normal_sign: int
    transparent: bool


class VoxelWorld:
    def __init__(self, parent: NodePath, seed: int, project_root: Path | None = None, zone_key: str = 'day_zone', boundary_chunk_radius: int = WORLD_BOUNDARY_CHUNK_RADIUS):
        self.root_parent = parent
        self.parent = parent.attachNewNode('world_root')
        self.seed = seed
        self.project_root = project_root
        self.zone_key = zone_key
        self.atlas_textures: dict[str, Texture] = {}
        self.active_atlas_variant = 'default'
        self._build_atlas_variants(project_root)
        self.atlas_texture = self.atlas_textures[self.active_atlas_variant]
        self.chunks: dict[tuple[int, int], Chunk] = {}
        self.modifications: dict[tuple[int, int, int], int] = {}
        self.tick_counter = 0
        self.total_opaque_quads = 0
        self.total_transparent_quads = 0
        self.cube_template = self._build_cube_model()
        self.boundary_chunk_radius = WORLD_BOUNDARY_CHUNK_RADIUS
        self.max_cached_chunks = MAX_CACHED_CHUNKS
        self.set_world_size(boundary_chunk_radius)

    def set_world_size(self, boundary_chunk_radius: int) -> None:
        radius = max(3, int(round(boundary_chunk_radius)))
        self.boundary_chunk_radius = radius
        self.max_cached_chunks = max(MAX_CACHED_CHUNKS, int((radius * 2 + 1) ** 2 + 12))

    def get_world_size_chunks(self) -> int:
        return int(self.boundary_chunk_radius)

    def clear(self) -> None:
        self.parent.removeNode()

    def _build_atlas_variants(self, project_root: Path | None) -> None:
        default_path = None
        grayscale_path = None
        if project_root is not None:
            textures_dir = project_root / 'assets' / 'textures'
            default_path = textures_dir / 'block_atlas.png'
            grayscale_path = textures_dir / 'block_atlas_grayscale.png'
        hell_path = textures_dir / 'block_atlas_hell.png' if project_root is not None else None
        candy_path = textures_dir / 'block_atlas_candy.png' if project_root is not None else None
        polar_path = textures_dir / 'block_atlas_polar.png' if project_root is not None else None
        self.atlas_textures['default'] = build_texture_atlas(default_path, variant='default')
        self.atlas_textures['grayscale'] = build_texture_atlas(grayscale_path, variant='grayscale')
        self.atlas_textures['hell'] = build_texture_atlas(hell_path, variant='hell')
        self.atlas_textures['candy'] = build_texture_atlas(candy_path, variant='candy')
        self.atlas_textures['polar'] = build_texture_atlas(polar_path, variant='polar')

    def apply_atlas_variant(self, variant: str) -> None:
        self.active_atlas_variant = variant if variant in self.atlas_textures else 'default'
        self.atlas_texture = self.atlas_textures[self.active_atlas_variant]
        for chunk in self.chunks.values():
            if chunk.root is None:
                continue
            for child in chunk.root.getChildren():
                child.setTexture(self.atlas_texture, 1)

    def apply_zone(self, zone_key: str, atlas_variant: str) -> None:
        self.zone_key = zone_key
        self.apply_atlas_variant(atlas_variant)

    def _build_cube_model(self) -> NodePath:
        fmt = GeomVertexFormat.getV3n3()
        vdata = GeomVertexData('cube', fmt, Geom.UHStatic)
        vertex = GeomVertexWriter(vdata, 'vertex')
        normal = GeomVertexWriter(vdata, 'normal')

        faces = [
            ((1, 0, 0), [(0.5, -0.5, -0.5), (0.5, 0.5, -0.5), (0.5, 0.5, 0.5), (0.5, -0.5, 0.5)]),
            ((-1, 0, 0), [(-0.5, 0.5, -0.5), (-0.5, -0.5, -0.5), (-0.5, -0.5, 0.5), (-0.5, 0.5, 0.5)]),
            ((0, 1, 0), [(-0.5, 0.5, -0.5), (-0.5, 0.5, 0.5), (0.5, 0.5, 0.5), (0.5, 0.5, -0.5)]),
            ((0, -1, 0), [(0.5, -0.5, -0.5), (0.5, -0.5, 0.5), (-0.5, -0.5, 0.5), (-0.5, -0.5, -0.5)]),
            ((0, 0, 1), [(-0.5, -0.5, 0.5), (0.5, -0.5, 0.5), (0.5, 0.5, 0.5), (-0.5, 0.5, 0.5)]),
            ((0, 0, -1), [(-0.5, 0.5, -0.5), (0.5, 0.5, -0.5), (0.5, -0.5, -0.5), (-0.5, -0.5, -0.5)]),
        ]

        tris = GeomTriangles(Geom.UHStatic)
        index = 0
        for nrm, verts in faces:
            for vx, vy, vz in verts:
                vertex.addData3(vx, vy, vz)
                normal.addData3(*nrm)
            tris.addVertices(index, index + 1, index + 2)
            tris.addVertices(index, index + 2, index + 3)
            index += 4

        geom = Geom(vdata)
        geom.addPrimitive(tris)
        node = GeomNode('cube')
        node.addGeom(geom)
        np = NodePath(node)
        return np

    def reset_world(self, seed: int, modifications: dict[tuple[int, int, int], int] | None = None) -> None:
        self.parent.removeNode()
        self.parent = self.root_parent.attachNewNode('world_root')
        self.seed = seed
        self.tick_counter = 0
        self.chunks.clear()
        self.modifications = dict(modifications or {})
        self.total_opaque_quads = 0
        self.total_transparent_quads = 0

    def _normalized_look(self, look_x: float, look_y: float) -> tuple[float, float]:
        look_len = math.hypot(look_x, look_y)
        if look_len < 1e-5:
            return 0.0, 1.0
        return look_x / look_len, look_y / look_len


    def get_boundary_half_extent(self) -> float:
        return float(self.boundary_chunk_radius * CHUNK_SIZE)

    def get_boundary_inner_half_extent(self, margin: float = 0.0) -> float:
        return max(0.0, self.get_boundary_half_extent() - WORLD_BOUNDARY_MARGIN - margin)

    def clamp_to_world_boundary(self, x: float, y: float, margin: float = 0.0) -> tuple[float, float]:
        half = self.get_boundary_inner_half_extent(margin)
        return (max(-half, min(half, x)), max(-half, min(half, y)))

    def _chunk_intersects_boundary(self, key: tuple[int, int]) -> bool:
        half = self.get_boundary_half_extent()
        min_x = key[0] * CHUNK_SIZE
        max_x = min_x + CHUNK_SIZE
        min_y = key[1] * CHUNK_SIZE
        max_y = min_y + CHUNK_SIZE
        return max_x > -half and min_x < half and max_y > -half and min_y < half

    def is_within_world_boundary(self, x: float, y: float, margin: float = 0.0) -> bool:
        half = self.get_boundary_inner_half_extent(margin)
        return (-half <= x <= half) and (-half <= y <= half)

    def _compute_chunk_sets(
        self,
        player_x: float,
        player_y: float,
        look_x: float = 0.0,
        look_y: float = 1.0,
        bootstrap_extra_radius: float = 0.0,
    ) -> tuple[set[tuple[int, int]], set[tuple[int, int]], float, float, float, float, float, float]:
        _ = bootstrap_extra_radius
        look_x, look_y = self._normalized_look(look_x, look_y)

        player_chunk_x = player_x / CHUNK_SIZE
        player_chunk_y = player_y / CHUNK_SIZE
        biased_chunk_x = player_chunk_x
        biased_chunk_y = player_chunk_y

        needed: set[tuple[int, int]] = set()
        visible: set[tuple[int, int]] = set()
        edge = self.boundary_chunk_radius + 1
        for cx in range(-edge, edge):
            for cy in range(-edge, edge):
                key = (cx, cy)
                if not self._chunk_intersects_boundary(key):
                    continue
                needed.add(key)
                visible.add(key)

        return needed, visible, player_chunk_x, player_chunk_y, biased_chunk_x, biased_chunk_y, look_x, look_y

    def _ensure_chunk_root(self, chunk: Chunk) -> None:
        if chunk.root is not None:
            return
        key = chunk.key
        chunk.root = self.parent.attachNewNode(f'chunk_{key[0]}_{key[1]}')
        chunk.root.setPos(key[0] * CHUNK_SIZE, key[1] * CHUNK_SIZE, 0)
        chunk.root.setTransparency(TransparencyAttrib.MAlpha)

    def preload_chunk_shell(
        self,
        player_x: float,
        player_y: float,
        look_x: float = 0.0,
        look_y: float = 1.0,
        progress_callback=None,
    ) -> tuple[int, int]:
        needed, visible, player_chunk_x, player_chunk_y, biased_chunk_x, biased_chunk_y, look_x, look_y = self._compute_chunk_sets(
            player_x,
            player_y,
            look_x,
            look_y,
            bootstrap_extra_radius=max(0.0, INITIAL_BOOTSTRAP_RADIUS - LOAD_RADIUS),
        )
        ordered = [self.ensure_chunk(key) for key in needed]
        ordered.sort(key=lambda chunk: self._chunk_priority(chunk.key, player_chunk_x, player_chunk_y, biased_chunk_x, biased_chunk_y, look_x, look_y))

        total = max(1, len(ordered))
        for index, chunk in enumerate(ordered, start=1):
            chunk.last_touched = self.tick_counter
            self._ensure_chunk_root(chunk)
            if not chunk.generated:
                self._generate_chunk(chunk)
            if chunk.dirty:
                self._rebuild_chunk(chunk)

            if chunk.key in visible:
                fade = self._chunk_fade_alpha(chunk.key, player_chunk_x, player_chunk_y, biased_chunk_x, biased_chunk_y, look_x, look_y)
                chunk.root.show()
                chunk.root.setColorScale(1.0, 1.0, 1.0, fade)
            else:
                chunk.root.hide()

            if progress_callback is not None:
                progress_callback(index, total, chunk.key)

        self._refresh_quad_totals()
        return len(visible), len(ordered)

    def update_loaded_chunks(self, player_x: float, player_y: float, look_x: float = 0.0, look_y: float = 1.0) -> None:
        self.tick_counter += 1
        center_cx, center_cy = self.world_to_chunk(math.floor(player_x), math.floor(player_y))
        needed, visible, player_chunk_x, player_chunk_y, biased_chunk_x, biased_chunk_y, look_x, look_y = self._compute_chunk_sets(
            player_x, player_y, look_x, look_y
        )

        for key in needed:
            chunk = self.ensure_chunk(key)
            chunk.last_touched = self.tick_counter
            self._ensure_chunk_root(chunk)

        self._force_ready_near_chunks(visible, player_chunk_x, player_chunk_y, biased_chunk_x, biased_chunk_y, look_x, look_y)
        self._generate_pending_chunks(needed, player_chunk_x, player_chunk_y, biased_chunk_x, biased_chunk_y, look_x, look_y)

        dirty_needed = [
            chunk for key, chunk in self.chunks.items()
            if key in needed and chunk.root is not None and chunk.generated and chunk.dirty
        ]
        dirty_needed.sort(key=lambda chunk: self._chunk_priority(chunk.key, player_chunk_x, player_chunk_y, biased_chunk_x, biased_chunk_y, look_x, look_y))
        for chunk in dirty_needed[:MAX_CHUNK_REBUILDS_PER_FRAME]:
            self._rebuild_chunk(chunk)

        self._apply_chunk_visibility(needed, visible, player_chunk_x, player_chunk_y, biased_chunk_x, biased_chunk_y, look_x, look_y)
        self._refresh_quad_totals()
        self._prune_cache(center_cx, center_cy)

    def _apply_chunk_visibility(
        self,
        needed: set[tuple[int, int]],
        visible: set[tuple[int, int]],
        player_chunk_x: float,
        player_chunk_y: float,
        biased_chunk_x: float,
        biased_chunk_y: float,
        look_x: float,
        look_y: float,
    ) -> None:
        for key, chunk in self.chunks.items():
            if chunk.root is None:
                continue
            if key not in needed:
                chunk.root.removeNode()
                chunk.root = None
                continue
            is_ready = chunk.generated and not chunk.dirty and chunk.root.getNumChildren() > 0
            if key in visible and is_ready:
                chunk.root.show()
                fade = self._chunk_fade_alpha(key, player_chunk_x, player_chunk_y, biased_chunk_x, biased_chunk_y, look_x, look_y)
                chunk.root.setColorScale(1.0, 1.0, 1.0, fade)
            else:
                chunk.root.hide()

    def _force_ready_near_chunks(
        self,
        visible: set[tuple[int, int]],
        player_chunk_x: float,
        player_chunk_y: float,
        biased_chunk_x: float,
        biased_chunk_y: float,
        look_x: float,
        look_y: float,
    ) -> None:
        critical = []
        for key in visible:
            if self._chunk_distance_to_point(key, player_chunk_x, player_chunk_y) <= FORCE_READY_RADIUS:
                critical.append(self.ensure_chunk(key))
        critical.sort(key=lambda chunk: self._chunk_priority(chunk.key, player_chunk_x, player_chunk_y, biased_chunk_x, biased_chunk_y, look_x, look_y))
        for chunk in critical:
            self._ensure_chunk_root(chunk)
            if not chunk.generated:
                self._generate_chunk(chunk)
            if chunk.dirty:
                self._rebuild_chunk(chunk)

    def _generate_pending_chunks(
        self,
        needed: set[tuple[int, int]],
        player_chunk_x: float,
        player_chunk_y: float,
        biased_chunk_x: float,
        biased_chunk_y: float,
        look_x: float,
        look_y: float,
    ) -> None:
        pending = [
            chunk for key, chunk in self.chunks.items()
            if key in needed and not chunk.generated
        ]
        pending.sort(key=lambda chunk: self._chunk_priority(chunk.key, player_chunk_x, player_chunk_y, biased_chunk_x, biased_chunk_y, look_x, look_y))
        for chunk in pending[:MAX_CHUNK_GENERATIONS_PER_FRAME]:
            self._generate_chunk(chunk)

    def _chunk_distance_to_point(self, key: tuple[int, int], px: float, py: float) -> float:
        cx = key[0] + 0.5
        cy = key[1] + 0.5
        return math.hypot(cx - px, cy - py)

    def _chunk_forward_dot(self, key: tuple[int, int], px: float, py: float, look_x: float, look_y: float) -> float:
        vx = (key[0] + 0.5) - px
        vy = (key[1] + 0.5) - py
        length = math.hypot(vx, vy)
        if length < 1e-5:
            return 1.0
        return (vx / length) * look_x + (vy / length) * look_y

    def _chunk_fade_alpha(
        self,
        key: tuple[int, int],
        player_chunk_x: float,
        player_chunk_y: float,
        biased_chunk_x: float,
        biased_chunk_y: float,
        look_x: float,
        look_y: float,
    ) -> float:
        return 1.0

    def _chunk_priority(
        self,
        key: tuple[int, int],
        player_chunk_x: float,
        player_chunk_y: float,
        biased_chunk_x: float,
        biased_chunk_y: float,
        look_x: float,
        look_y: float,
    ) -> float:
        return self._chunk_distance_to_point(key, player_chunk_x, player_chunk_y)

    def _refresh_quad_totals(self) -> None:
        self.total_opaque_quads = sum(chunk.opaque_quad_count for chunk in self.chunks.values() if chunk.root is not None)
        self.total_transparent_quads = sum(chunk.transparent_quad_count for chunk in self.chunks.values() if chunk.root is not None)

    def _prune_cache(self, center_cx: int, center_cy: int) -> None:
        if len(self.chunks) <= self.max_cached_chunks:
            return
        sortable = []
        for key, chunk in self.chunks.items():
            if chunk.root is not None:
                continue
            dist = abs(key[0] - center_cx) + abs(key[1] - center_cy)
            sortable.append((dist, chunk.last_touched, key))
        sortable.sort(reverse=True)
        while len(self.chunks) > self.max_cached_chunks and sortable:
            _, _, key = sortable.pop(0)
            self.chunks.pop(key, None)

    def ensure_chunk(self, key: tuple[int, int]) -> Chunk:
        chunk = self.chunks.get(key)
        if chunk is not None:
            return chunk
        chunk = Chunk(key=key, dirty=False)
        self.chunks[key] = chunk
        return chunk

    def _generate_chunk(self, chunk: Chunk) -> None:
        if chunk.generated:
            return
        chunk.base_blocks.clear()
        if self.zone_key == 'hell_zone':
            self._generate_hell_chunk(chunk)
        elif self.zone_key == 'candy_zone':
            self._generate_candy_chunk(chunk)
        elif self.zone_key == 'desert_zone':
            self._generate_desert_chunk(chunk)
        elif self.zone_key == 'tropical_zone':
            self._generate_tropical_chunk(chunk)
        elif self.zone_key == 'tech_zone':
            self._generate_tech_chunk(chunk)
        elif self.zone_key == 'polar_zone':
            self._generate_polar_chunk(chunk)
        else:
            cx, cy = chunk.key
            for lx in range(CHUNK_SIZE):
                wx = cx * CHUNK_SIZE + lx
                for ly in range(CHUNK_SIZE):
                    wy = cy * CHUNK_SIZE + ly
                    height = self._terrain_height(wx, wy)
                    biome = self._biome_value(wx, wy)
                    top_block = 4 if height <= WATER_LEVEL + 1 or biome < 0.24 else 1

                    chunk.base_blocks[(lx, ly, height)] = top_block

                    if self._should_spawn_tree(wx, wy, height, top_block):
                        self._stamp_tree(chunk.base_blocks, lx, ly, height + 1)
        chunk.generated = True
        chunk.dirty = True

    def _generate_hell_chunk(self, chunk: Chunk) -> None:
        cx, cy = chunk.key
        for lx in range(CHUNK_SIZE):
            wx = cx * CHUNK_SIZE + lx
            for ly in range(CHUNK_SIZE):
                wy = cy * CHUNK_SIZE + ly
                height = self._terrain_height_hell(wx, wy)
                river_strength = self._hell_river_strength(wx, wy)
                top_block = 4 if river_strength > 0.78 else (3 if height >= 8 else 2)
                chunk.base_blocks[(lx, ly, height)] = top_block

                roof_z = self._hell_roof_height(wx, wy, height, river_strength)
                if roof_z is not None:
                    chunk.base_blocks[(lx, ly, roof_z)] = 3
                    if roof_z + 1 < WORLD_HEIGHT_LIMIT and ((wx + wy + self.seed) & 3) == 0:
                        chunk.base_blocks[(lx, ly, roof_z + 1)] = 3

                if self._should_spawn_hell_tree(wx, wy, height, river_strength):
                    self._stamp_burned_tree(chunk.base_blocks, lx, ly, height + 1)

    def _generate_candy_chunk(self, chunk: Chunk) -> None:
        cx, cy = chunk.key
        for lx in range(CHUNK_SIZE):
            wx = cx * CHUNK_SIZE + lx
            for ly in range(CHUNK_SIZE):
                wy = cy * CHUNK_SIZE + ly
                height = self._terrain_height_candy(wx, wy)
                confection = self._candy_confection_value(wx, wy)
                top_block = 4 if confection > 0.60 or height <= 4 else 1
                chunk.base_blocks[(lx, ly, height)] = top_block

                if self._should_spawn_candy_tree(wx, wy, height, top_block):
                    self._stamp_candy_tree(chunk.base_blocks, lx, ly, height + 1)

    def _generate_desert_chunk(self, chunk: Chunk) -> None:
        cx, cy = chunk.key
        for lx in range(CHUNK_SIZE):
            wx = cx * CHUNK_SIZE + lx
            for ly in range(CHUNK_SIZE):
                wy = cy * CHUNK_SIZE + ly
                height = self._terrain_height_desert(wx, wy)
                stone_mask = self._desert_stone_value(wx, wy)
                chunk.base_blocks[(lx, ly, height)] = 3 if stone_mask > 0.76 else 4

                if self._should_spawn_desert_spire(wx, wy, height, stone_mask):
                    self._stamp_desert_spire(chunk.base_blocks, lx, ly, height + 1)


    def _generate_polar_chunk(self, chunk: Chunk) -> None:
        cx, cy = chunk.key
        for lx in range(CHUNK_SIZE):
            wx = cx * CHUNK_SIZE + lx
            for ly in range(CHUNK_SIZE):
                wy = cy * CHUNK_SIZE + ly
                height = self._terrain_height_polar(wx, wy)
                ice_mask = self._polar_ice_value(wx, wy)
                packed = self._polar_packed_value(wx, wy)
                cap_block = 7 if ice_mask > 0.78 else (3 if packed > 0.66 else 1)
                chunk.base_blocks[(lx, ly, height)] = cap_block
                if cap_block == 3 and height - 1 >= 0:
                    chunk.base_blocks[(lx, ly, height - 1)] = 3
                elif height - 1 >= 0 and packed > 0.52:
                    chunk.base_blocks[(lx, ly, height - 1)] = 2

                if self._should_spawn_polar_tree(wx, wy, height, cap_block):
                    self._stamp_polar_tree(chunk.base_blocks, lx, ly, height + 1)
                elif self._should_spawn_candy_cane_post(wx, wy, height, cap_block):
                    self._stamp_candy_cane_post(chunk.base_blocks, lx, ly, height + 1)

    def _generate_tech_chunk(self, chunk: Chunk) -> None:
        cx, cy = chunk.key
        district_size = 40
        avenue = 8
        mega_wall_period = district_size * 4
        for lx in range(CHUNK_SIZE):
            wx = cx * CHUNK_SIZE + lx
            for ly in range(CHUNK_SIZE):
                wy = cy * CHUNK_SIZE + ly
                ground = self._terrain_height_tech(wx, wy)
                mx = wx % district_size
                my = wy % district_size
                road_x = mx < avenue or mx >= district_size - avenue
                road_y = my < avenue or my >= district_size - avenue
                cross_road = road_x or road_y

                if cross_road:
                    chunk.base_blocks[(lx, ly, ground)] = 3
                    if (mx in (avenue - 1, district_size - avenue) or my in (avenue - 1, district_size - avenue)) and ((wx + wy + self.seed) % 5 == 0):
                        chunk.base_blocks[(lx, ly, ground + 1)] = 7
                    continue

                chunk.base_blocks[(lx, ly, ground)] = 9
                if ground - 1 >= 0:
                    chunk.base_blocks[(lx, ly, ground - 1)] = 3

                plaza_margin = 5
                local_x = mx - avenue
                local_y = my - avenue
                block_span = district_size - avenue * 2

                world_wall_x = wx % mega_wall_period
                world_wall_y = wy % mega_wall_period
                on_outer_wall = world_wall_x in (0, 1, mega_wall_period - 2, mega_wall_period - 1) or world_wall_y in (0, 1, mega_wall_period - 2, mega_wall_period - 1)
                gate_open = (world_wall_x in range(mega_wall_period // 2 - 8, mega_wall_period // 2 + 8) or world_wall_y in range(mega_wall_period // 2 - 8, mega_wall_period // 2 + 8))
                if on_outer_wall and not gate_open:
                    for dz in range(1, 6):
                        chunk.base_blocks[(lx, ly, ground + dz)] = 5
                    if ((wx + wy + self.seed) % 7) == 0:
                        chunk.base_blocks[(lx, ly, ground + 6)] = 7
                    continue

                if not (plaza_margin <= local_x < block_span - plaza_margin and plaza_margin <= local_y < block_span - plaza_margin):
                    continue

                block_cx = wx // district_size
                block_cy = wy // district_size
                build_seed = self._cell_hash(block_cx, block_cy, 77)
                building_count = 1 + int(((build_seed >> 5) & 1) and ((build_seed >> 7) & 1))
                built_here = False
                for idx in range(building_count):
                    jitter_seed = self._cell_hash(block_cx, block_cy, 90 + idx)
                    pad = 3 + ((jitter_seed >> 2) & 1)
                    size_x = 8 + ((jitter_seed >> 4) % 5)
                    size_y = 8 + ((jitter_seed >> 8) % 5)
                    if ((jitter_seed >> 12) & 7) == 0:
                        size_x += 3
                        size_y += 2
                    max_x0 = max(pad, block_span - pad - size_x)
                    max_y0 = max(pad, block_span - pad - size_y)
                    x0 = pad + (jitter_seed % max(1, max_x0 - pad + 1))
                    y0 = pad + (((jitter_seed >> 16) % max(1, max_y0 - pad + 1)))
                    x1 = x0 + size_x - 1
                    y1 = y0 + size_y - 1
                    if not (x0 <= local_x <= x1 and y0 <= local_y <= y1):
                        continue
                    built_here = True
                    tower_height = 7 + ((jitter_seed >> 20) % 8)
                    if size_x >= 12 or size_y >= 12:
                        tower_height += 3
                    on_skin = local_x in (x0, x1) or local_y in (y0, y1)
                    if on_skin:
                        for dz in range(1, tower_height + 1):
                            z = ground + dz
                            window_band = dz % 3 == 1 and dz < tower_height
                            if window_band and ((local_x + local_y + dz + idx) % 2 == 0):
                                chunk.base_blocks[(lx, ly, z)] = 7
                            else:
                                chunk.base_blocks[(lx, ly, z)] = 5
                    roof_z = ground + tower_height + 1
                    if roof_z < WORLD_HEIGHT_LIMIT and x0 + 1 <= local_x <= x1 - 1 and y0 + 1 <= local_y <= y1 - 1:
                        chunk.base_blocks[(lx, ly, roof_z)] = 9
                    break

                if not built_here and ((build_seed >> 24) & 3) == 0:
                    kiosk_x0 = plaza_margin + 2
                    kiosk_y0 = plaza_margin + 2
                    kiosk_x1 = kiosk_x0 + 4
                    kiosk_y1 = kiosk_y0 + 4
                    if kiosk_x0 <= local_x <= kiosk_x1 and kiosk_y0 <= local_y <= kiosk_y1:
                        for dz in range(1, 4):
                            chunk.base_blocks[(lx, ly, ground + dz)] = 5
                        if local_x in (kiosk_x0 + 1, kiosk_x1 - 1) and local_y in (kiosk_y0 + 1, kiosk_y1 - 1):
                            chunk.base_blocks[(lx, ly, ground + 4)] = 7

    def _cell_hash(self, cx: int, cy: int, salt: int = 0) -> int:
        value = (cx * 92837111) ^ (cy * 689287499) ^ (self.seed * 283923481) ^ (salt * 19349663)
        value &= 0xFFFFFFFF
        value ^= (value >> 16)
        value = (value * 2246822519) & 0xFFFFFFFF
        value ^= (value >> 13)
        value = (value * 3266489917) & 0xFFFFFFFF
        value ^= (value >> 16)
        return value

    def _cell_rand01(self, cx: int, cy: int, salt: int = 0) -> float:
        return self._cell_hash(cx, cy, salt) / 0xFFFFFFFF

    def _generate_tropical_chunk(self, chunk: Chunk) -> None:
        cx, cy = chunk.key
        for lx in range(CHUNK_SIZE):
            wx = cx * CHUNK_SIZE + lx
            for ly in range(CHUNK_SIZE):
                wy = cy * CHUNK_SIZE + ly
                height = self._terrain_height_tropical(wx, wy)
                wetness = self._tropical_wetness_value(wx, wy)
                beach = height <= WATER_LEVEL + 1 or wetness > 0.62
                top_block = 4 if beach else 1
                chunk.base_blocks[(lx, ly, height)] = top_block
                if top_block == 1 and self._should_spawn_tropical_palm(wx, wy, height):
                    self._stamp_tropical_palm(chunk.base_blocks, lx, ly, height + 1)

    def _terrain_height_tropical(self, wx: int, wy: int) -> int:
        broad = fractal_noise_2d(wx * 0.018, wy * 0.018, self.seed + 30000, octaves=5)
        dunes = fractal_noise_2d(wx * 0.050, wy * 0.050, self.seed + 30100, octaves=4)
        detail = fractal_noise_2d(wx * 0.110, wy * 0.110, self.seed + 30200, octaves=2)
        shaped = broad * 0.62 + dunes * 0.28 + detail * 0.10
        height = int(round(4 + shaped * 5.5))
        return max(3, min(WORLD_HEIGHT_LIMIT - 5, height))

    def _tropical_wetness_value(self, wx: int, wy: int) -> float:
        return fractal_noise_2d(wx * 0.028, wy * 0.028, self.seed + 30300, octaves=3)

    def _should_spawn_tropical_palm(self, wx: int, wy: int, height: int) -> bool:
        if height <= WATER_LEVEL + 1:
            return False
        chance = fractal_noise_2d(wx * 0.10, wy * 0.10, self.seed + 30400, octaves=1)
        return chance > 0.80 and (wx % CHUNK_SIZE) not in (0, 1, CHUNK_SIZE - 2, CHUNK_SIZE - 1) and (wy % CHUNK_SIZE) not in (0, 1, CHUNK_SIZE - 2, CHUNK_SIZE - 1)

    def _stamp_tropical_palm(self, block_map: dict[tuple[int, int, int], int], lx: int, ly: int, base_z: int) -> None:
        trunk_height = 3 + int(((lx * 5 + ly * 11 + self.seed) & 1) == 0)
        curve_dir = -1 if ((lx + ly + self.seed) & 1) == 0 else 1
        tip_x = lx
        tip_y = ly
        for dz in range(trunk_height):
            px = lx + (curve_dir if dz >= 2 else 0)
            py = ly
            if 0 <= px < CHUNK_SIZE and 0 <= py < CHUNK_SIZE and base_z + dz < WORLD_HEIGHT_LIMIT:
                block_map[(px, py, base_z + dz)] = 6
                tip_x, tip_y = px, py
        crown_z = min(WORLD_HEIGHT_LIMIT - 1, base_z + trunk_height)
        for ox, oy in ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1), (2 * curve_dir, 0), (curve_dir, 1), (curve_dir, -1)):
            px = tip_x + ox
            py = tip_y + oy
            if 0 <= px < CHUNK_SIZE and 0 <= py < CHUNK_SIZE and crown_z < WORLD_HEIGHT_LIMIT:
                block_map[(px, py, crown_z)] = 8
        if crown_z + 1 < WORLD_HEIGHT_LIMIT:
            block_map[(tip_x, tip_y, crown_z + 1)] = 8


    def _terrain_height_polar(self, wx: int, wy: int) -> int:
        broad = fractal_noise_2d(wx * 0.015, wy * 0.015, self.seed + 26000, octaves=5)
        ridges = abs(fractal_noise_2d(wx * 0.032, wy * 0.032, self.seed + 26100, octaves=4))
        crags = abs(fractal_noise_2d(wx * 0.072, wy * 0.072, self.seed + 26200, octaves=2))
        plains = fractal_noise_2d((wx - 220) * 0.010, (wy + 180) * 0.010, self.seed + 26300, octaves=2)
        plateau = broad * 0.34 + plains * 0.18
        peaks = max(0.0, ridges - 0.46) * 20.0 + max(0.0, crags - 0.70) * 11.0
        height = int(round(4 + plateau * 3.0 + peaks))
        return max(2, min(WORLD_HEIGHT_LIMIT - 3, height))

    def _polar_ice_value(self, wx: int, wy: int) -> float:
        return abs(fractal_noise_2d(wx * 0.020, wy * 0.020, self.seed + 26400, octaves=2))

    def _polar_packed_value(self, wx: int, wy: int) -> float:
        return abs(fractal_noise_2d((wx + 410) * 0.046, (wy - 260) * 0.046, self.seed + 26500, octaves=2))

    def _should_spawn_polar_tree(self, wx: int, wy: int, height: int, top_block: int) -> bool:
        if top_block not in (1, 2) or height < 5:
            return False
        chance = fractal_noise_2d(wx * 0.10, wy * 0.10, self.seed + 26600, octaves=1)
        edge = (wx % CHUNK_SIZE) in (0, 1, CHUNK_SIZE - 2, CHUNK_SIZE - 1) or (wy % CHUNK_SIZE) in (0, 1, CHUNK_SIZE - 2, CHUNK_SIZE - 1)
        return chance > 0.80 and not edge

    def _stamp_polar_tree(self, block_map: dict[tuple[int, int, int], int], lx: int, ly: int, base_z: int) -> None:
        trunk_height = 3 + int(((lx * 13 + ly * 17 + self.seed) & 1) == 0)
        for dz in range(trunk_height):
            z = base_z + dz
            if z < WORLD_HEIGHT_LIMIT:
                block_map[(lx, ly, z)] = 6
        top = base_z + trunk_height
        layers = [
            (0, 2),
            (1, 2),
            (2, 1),
            (3, 1),
        ]
        for dz, radius in layers:
            z = top + dz
            if z >= WORLD_HEIGHT_LIMIT:
                break
            for ox in range(-radius, radius + 1):
                for oy in range(-radius, radius + 1):
                    if abs(ox) + abs(oy) > radius + 1:
                        continue
                    px = lx + ox
                    py = ly + oy
                    if 0 <= px < CHUNK_SIZE and 0 <= py < CHUNK_SIZE:
                        block_map[(px, py, z)] = 8
        if top + 4 < WORLD_HEIGHT_LIMIT:
            block_map[(lx, ly, top + 4)] = 1

    def _should_spawn_candy_cane_post(self, wx: int, wy: int, height: int, top_block: int) -> bool:
        if top_block not in (1, 2) or height < 4:
            return False
        chance = fractal_noise_2d((wx - 180) * 0.12, (wy + 70) * 0.12, self.seed + 26700, octaves=1)
        edge = (wx % CHUNK_SIZE) in (0, 1, CHUNK_SIZE - 2, CHUNK_SIZE - 1) or (wy % CHUNK_SIZE) in (0, 1, CHUNK_SIZE - 2, CHUNK_SIZE - 1)
        return chance > 0.86 and not edge

    def _stamp_candy_cane_post(self, block_map: dict[tuple[int, int, int], int], lx: int, ly: int, base_z: int) -> None:
        height = 4 + int(((lx * 7 + ly * 19 + self.seed) & 1) == 0)
        for dz in range(height):
            z = base_z + dz
            if z >= WORLD_HEIGHT_LIMIT:
                break
            block_map[(lx, ly, z)] = 5 if dz % 2 == 0 else 7
        hook_z = base_z + height - 1
        for ox in (1, 2):
            px = lx + ox
            if 0 <= px < CHUNK_SIZE and hook_z < WORLD_HEIGHT_LIMIT:
                block_map[(px, ly, hook_z)] = 5 if ox == 1 else 7
        if 0 <= lx + 2 < CHUNK_SIZE and hook_z - 1 >= 0:
            block_map[(lx + 2, ly, hook_z - 1)] = 5

    def _terrain_height_tech(self, wx: int, wy: int) -> int:
        plate = fractal_noise_2d(wx * 0.008, wy * 0.008, self.seed + 24000, octaves=2)
        micro = fractal_noise_2d(wx * 0.032, wy * 0.032, self.seed + 24100, octaves=1)
        shaped = plate * 0.28 + micro * 0.10
        height = 3 + int(round(max(-0.45, min(0.45, shaped))))
        return max(2, min(WORLD_HEIGHT_LIMIT - 9, height))

    def _terrain_height_desert(self, wx: int, wy: int) -> int:
        broad = fractal_noise_2d(wx * 0.018, wy * 0.018, self.seed + 23000, octaves=5)
        dunes = fractal_noise_2d(wx * 0.060, wy * 0.060, self.seed + 23100, octaves=3)
        ripples = fractal_noise_2d(wx * 0.140, wy * 0.140, self.seed + 23200, octaves=2)
        shaped = broad * 0.54 + dunes * 0.34 + ripples * 0.12
        lee = abs(fractal_noise_2d((wx + 320) * 0.024, (wy - 480) * 0.024, self.seed + 23300, octaves=2))
        height = int(round(3 + shaped * 8 + max(0.0, lee - 0.62) * 4.0))
        return max(2, min(WORLD_HEIGHT_LIMIT - 5, height))

    def _desert_stone_value(self, wx: int, wy: int) -> float:
        return abs(fractal_noise_2d(wx * 0.028, wy * 0.028, self.seed + 23400, octaves=2))

    def _should_spawn_desert_spire(self, wx: int, wy: int, height: int, stone_mask: float) -> bool:
        if height < 4 or stone_mask > 0.88:
            return False
        chance = fractal_noise_2d(wx * 0.10, wy * 0.10, self.seed + 23500, octaves=1)
        edge = (wx % CHUNK_SIZE) in (0, 1, CHUNK_SIZE - 2, CHUNK_SIZE - 1) or (wy % CHUNK_SIZE) in (0, 1, CHUNK_SIZE - 2, CHUNK_SIZE - 1)
        return chance > 0.83 and not edge

    def _stamp_desert_spire(self, block_map: dict[tuple[int, int, int], int], lx: int, ly: int, base_z: int) -> None:
        height = 3 + int(((lx * 7 + ly * 11 + self.seed) & 1) == 0)
        for dz in range(height):
            block_map[(lx, ly, base_z + dz)] = 5
        top_z = base_z + height - 1
        for ox, oy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            px = lx + ox
            py = ly + oy
            if 0 <= px < CHUNK_SIZE and 0 <= py < CHUNK_SIZE and top_z < WORLD_HEIGHT_LIMIT:
                block_map[(px, py, top_z)] = 5

    def _terrain_height_candy(self, wx: int, wy: int) -> int:
        broad = fractal_noise_2d(wx * 0.020, wy * 0.020, self.seed + 21000, octaves=5)
        rolling = fractal_noise_2d(wx * 0.055, wy * 0.055, self.seed + 21100, octaves=3)
        detail = fractal_noise_2d(wx * 0.120, wy * 0.120, self.seed + 21200, octaves=2)
        dreamy = broad * 0.62 + rolling * 0.28 + detail * 0.10
        valley = fractal_noise_2d((wx - 400) * 0.015, (wy + 260) * 0.015, self.seed + 21300, octaves=2)
        height = int(round(4 + dreamy * 7 + max(0.0, valley - 0.45) * 2.2))
        return max(2, min(WORLD_HEIGHT_LIMIT - 5, height))

    def _candy_confection_value(self, wx: int, wy: int) -> float:
        stream = abs(fractal_noise_2d(wx * 0.018, wy * 0.018, self.seed + 21400, octaves=2))
        swirl = abs(fractal_noise_2d((wx + 240) * 0.042, (wy - 310) * 0.042, self.seed + 21500, octaves=1))
        return 1.0 - min(1.0, stream * 0.76 + swirl * 0.20)

    def _should_spawn_candy_tree(self, wx: int, wy: int, height: int, top_block: int) -> bool:
        if top_block != 1 or height < 4:
            return False
        chance = fractal_noise_2d(wx * 0.11, wy * 0.11, self.seed + 21600, octaves=1)
        return chance > 0.77 and (wx % CHUNK_SIZE) not in (0, 1, CHUNK_SIZE - 2, CHUNK_SIZE - 1) and (wy % CHUNK_SIZE) not in (0, 1, CHUNK_SIZE - 2, CHUNK_SIZE - 1)

    def _stamp_candy_tree(self, block_map: dict[tuple[int, int, int], int], lx: int, ly: int, base_z: int) -> None:
        trunk_height = 3 + int(((lx * 9 + ly * 17 + self.seed) & 1) == 0)
        for dz in range(trunk_height):
            block_map[(lx, ly, base_z + dz)] = 6

        canopy_z = base_z + trunk_height
        for ox in range(-2, 3):
            for oy in range(-2, 3):
                for oz in range(-1, 2):
                    if abs(ox) + abs(oy) + abs(oz) > 4:
                        continue
                    px = lx + ox
                    py = ly + oy
                    pz = canopy_z + oz
                    if 0 <= px < CHUNK_SIZE and 0 <= py < CHUNK_SIZE and 0 <= pz < WORLD_HEIGHT_LIMIT:
                        block_map[(px, py, pz)] = 8

        fruit_choices = [5, 7, 9]
        fruit_points = [(-1, 0, 0), (1, 0, 1), (0, -1, 0), (0, 1, 1), (-1, -1, 1), (1, 1, 0)]
        for idx, (ox, oy, oz) in enumerate(fruit_points):
            if ((lx * 31 + ly * 17 + idx + self.seed) % 3) == 0:
                px = lx + ox
                py = ly + oy
                pz = canopy_z + oz
                if 0 <= px < CHUNK_SIZE and 0 <= py < CHUNK_SIZE and 0 <= pz < WORLD_HEIGHT_LIMIT:
                    block_map[(px, py, pz)] = fruit_choices[(idx + lx + ly + self.seed) % len(fruit_choices)]

        crown_z = canopy_z + 2
        if crown_z < WORLD_HEIGHT_LIMIT:
            block_map[(lx, ly, crown_z)] = 8

    def _terrain_height(self, wx: int, wy: int) -> int:
        broad = fractal_noise_2d(wx * 0.035, wy * 0.035, self.seed, octaves=5)
        hills = fractal_noise_2d(wx * 0.085, wy * 0.085, self.seed + 1000, octaves=4)
        detail = fractal_noise_2d(wx * 0.20, wy * 0.20, self.seed + 2000, octaves=2)
        shaped = broad * 0.65 + hills * 0.30 + detail * 0.05
        height = int(round(2 + shaped * 9))
        return max(1, min(WORLD_HEIGHT_LIMIT - 4, height))

    def _biome_value(self, wx: int, wy: int) -> float:
        return fractal_noise_2d(wx * 0.02, wy * 0.02, self.seed + 5000, octaves=3)

    def _terrain_height_hell(self, wx: int, wy: int) -> int:
        broad = fractal_noise_2d(wx * 0.017, wy * 0.017, self.seed + 13000, octaves=5)
        ridges = abs(fractal_noise_2d(wx * 0.034, wy * 0.034, self.seed + 13100, octaves=4))
        serration = abs(fractal_noise_2d(wx * 0.082, wy * 0.082, self.seed + 13200, octaves=3))
        canyon = 1.0 - min(1.0, ridges * 1.10 + serration * 0.32)
        plateau = broad * 0.70 + (1.0 - ridges) * 0.25 + (1.0 - serration) * 0.05
        height = int(round(7 + plateau * 11 - canyon * 8.2))
        return max(1, min(WORLD_HEIGHT_LIMIT - 4, height))

    def _hell_river_strength(self, wx: int, wy: int) -> float:
        river_a = abs(fractal_noise_2d(wx * 0.018, wy * 0.018, self.seed + 14100, octaves=2))
        river_b = abs(fractal_noise_2d((wx + 700) * 0.033, (wy - 400) * 0.033, self.seed + 14200, octaves=1))
        return max(0.0, 1.0 - min(1.0, river_a * 0.82 + river_b * 0.30))

    def _hell_roof_height(self, wx: int, wy: int, floor_height: int, river_strength: float) -> int | None:
        cave_mask = fractal_noise_2d(wx * 0.014, wy * 0.014, self.seed + 17000, octaves=3)
        vault_mask = fractal_noise_2d((wx - 300) * 0.010, (wy + 500) * 0.010, self.seed + 17100, octaves=2)
        if river_strength > 0.76 and cave_mask > 0.48:
            roof = floor_height + 9 + int((cave_mask - 0.48) * 8)
        elif cave_mask > 0.70 and vault_mask > 0.18:
            roof = floor_height + 8 + int((cave_mask - 0.70) * 10)
        else:
            return None
        return max(floor_height + 7, min(WORLD_HEIGHT_LIMIT - 2, roof))

    def _should_spawn_hell_tree(self, wx: int, wy: int, height: int, river_strength: float) -> bool:
        if river_strength > 0.70 or height < 4:
            return False
        chance = fractal_noise_2d(wx * 0.11, wy * 0.11, self.seed + 19000, octaves=1)
        return chance > 0.82 and (wx % CHUNK_SIZE) not in (0, 1, CHUNK_SIZE - 2, CHUNK_SIZE - 1) and (wy % CHUNK_SIZE) not in (0, 1, CHUNK_SIZE - 2, CHUNK_SIZE - 1)

    def _stamp_burned_tree(self, block_map: dict[tuple[int, int, int], int], lx: int, ly: int, base_z: int) -> None:
        trunk_height = 5 + int(((lx * 13 + ly * 19 + self.seed) & 1) == 0)
        for dz in range(trunk_height):
            block_map[(lx, ly, base_z + dz)] = 6
        top_z = base_z + trunk_height - 1
        for ox, oy, oz in [(-1, 0, -1), (1, 0, 0), (0, -1, 1), (0, 1, 0), (-1, -1, 1), (1, 1, 1)]:
            px, py, pz = lx + ox, ly + oy, top_z + oz
            if 0 <= px < CHUNK_SIZE and 0 <= py < CHUNK_SIZE and 0 <= pz < WORLD_HEIGHT_LIMIT:
                block_map[(px, py, pz)] = 6

    def _should_spawn_tree(self, wx: int, wy: int, height: int, top_block: int) -> bool:
        if top_block != 1 or height <= WATER_LEVEL + 1:
            return False
        chance = fractal_noise_2d(wx * 0.13, wy * 0.13, self.seed + 9000, octaves=1)
        return chance > 0.79 and (wx % CHUNK_SIZE) not in (0, 1, CHUNK_SIZE - 2, CHUNK_SIZE - 1) and (wy % CHUNK_SIZE) not in (0, 1, CHUNK_SIZE - 2, CHUNK_SIZE - 1)

    def _stamp_tree(self, block_map: dict[tuple[int, int, int], int], lx: int, ly: int, base_z: int) -> None:
        trunk_height = 3 + int(((lx * 17 + ly * 31 + self.seed) & 1) == 0)
        for dz in range(trunk_height):
            block_map[(lx, ly, base_z + dz)] = 6
        canopy_z = base_z + trunk_height
        for ox in range(-2, 3):
            for oy in range(-2, 3):
                for oz in range(-1, 2):
                    if abs(ox) + abs(oy) + abs(oz) > 4:
                        continue
                    px = lx + ox
                    py = ly + oy
                    pz = canopy_z + oz
                    if 0 <= px < CHUNK_SIZE and 0 <= py < CHUNK_SIZE:
                        block_map[(px, py, pz)] = 8
        block_map[(lx, ly, canopy_z + 2)] = 8

    def world_to_chunk(self, x: int, y: int) -> tuple[int, int]:
        return x // CHUNK_SIZE, y // CHUNK_SIZE

    def world_to_local(self, x: int, y: int) -> tuple[int, int]:
        return x % CHUNK_SIZE, y % CHUNK_SIZE

    def get_block(self, x: int, y: int, z: int) -> int:
        if z < 0:
            return 3
        if z >= WORLD_HEIGHT_LIMIT:
            return 0
        key = (x, y, z)
        if key in self.modifications:
            return self.modifications[key]
        ck = self.world_to_chunk(x, y)
        lx, ly = self.world_to_local(x, y)
        chunk = self.ensure_chunk(ck)
        if not chunk.generated:
            self._generate_chunk(chunk)
        return chunk.base_blocks.get((lx, ly, z), 0)

    def is_solid(self, x: int, y: int, z: int) -> bool:
        block_id = self.get_block(x, y, z)
        return BLOCK_DEFS[block_id].solid and block_id != 0


    def highest_solid_in_column(self, x: int, y: int) -> tuple[int | None, int]:
        for z in range(WORLD_HEIGHT_LIMIT - 1, -1, -1):
            block_id = self.get_block(x, y, z)
            if block_id != 0:
                return z, block_id
        return None, 0

    def remove_surface_step(self, x: int, y: int, z: int) -> bool:
        top_z, top_block = self.highest_solid_in_column(x, y)
        if top_z is None or top_z != z:
            return False
        if top_block not in (1, 2, 3, 4):
            return False

        self.set_block(x, y, z, 0)
        if z - 1 >= 0 and self.get_block(x, y, z - 1) == 0:
            self.set_block(x, y, z - 1, 2)
        return True

    def collides_aabb(self, min_x: float, max_x: float, min_y: float, max_y: float, min_z: float, max_z: float) -> bool:
        half = self.get_boundary_half_extent() - WORLD_BOUNDARY_MARGIN
        if min_x < -half or max_x > half or min_y < -half or max_y > half:
            return True
        ix0 = math.floor(min_x)
        ix1 = math.floor(max_x)
        iy0 = math.floor(min_y)
        iy1 = math.floor(max_y)
        iz0 = math.floor(min_z)
        iz1 = math.floor(max_z)
        for x in range(ix0, ix1 + 1):
            for y in range(iy0, iy1 + 1):
                for z in range(iz0, iz1 + 1):
                    if self.is_solid(x, y, z):
                        return True
        return False

    def _chunk_positions(self, chunk: Chunk) -> Iterable[tuple[int, int, int, int]]:
        cx, cy = chunk.key
        yielded = set()
        for (lx, ly, z), base_block in chunk.base_blocks.items():
            wx = cx * CHUNK_SIZE + lx
            wy = cy * CHUNK_SIZE + ly
            key = (wx, wy, z)
            block = self.modifications.get(key, base_block)
            if block != 0:
                yielded.add(key)
                yield wx, wy, z, block
        for (wx, wy, z), block in self.modifications.items():
            if block == 0:
                continue
            if self.world_to_chunk(wx, wy) != chunk.key:
                continue
            key = (wx, wy, z)
            if key in yielded:
                continue
            yield wx, wy, z, block

    def _rebuild_chunk(self, chunk: Chunk) -> None:
        if chunk.root is None:
            return
        for child in list(chunk.root.getChildren()):
            child.removeNode()

        opaque_geom, opaque_quads = self._build_chunk_geom(chunk, transparent=False)
        transparent_geom, transparent_quads = self._build_chunk_geom(chunk, transparent=True)

        if opaque_geom is not None:
            opaque_np = chunk.root.attachNewNode(opaque_geom)
            opaque_np.setTexture(self.atlas_texture, 1)

        if transparent_geom is not None:
            transparent_np = chunk.root.attachNewNode(transparent_geom)
            transparent_np.setTexture(self.atlas_texture, 1)
            transparent_np.setTransparency(TransparencyAttrib.MAlpha)
            transparent_np.setBin('transparent', 0)

        chunk.opaque_quad_count = opaque_quads
        chunk.transparent_quad_count = transparent_quads
        chunk.dirty = False

    def _build_chunk_geom(self, chunk: Chunk, transparent: bool) -> tuple[GeomNode | None, int]:
        dims = [CHUNK_SIZE, CHUNK_SIZE, WORLD_HEIGHT_LIMIT]
        fmt = GeomVertexFormat.getV3n3c4t2()
        vdata = GeomVertexData('chunk_mesh', fmt, Geom.UHStatic)
        vertex = GeomVertexWriter(vdata, 'vertex')
        normal = GeomVertexWriter(vdata, 'normal')
        color = GeomVertexWriter(vdata, 'color')
        texcoord = GeomVertexWriter(vdata, 'texcoord')
        triangles = GeomTriangles(Geom.UHStatic)

        quad_count = 0
        cx, cy = chunk.key

        def local_block(lx: int, ly: int, lz: int) -> int:
            wx = cx * CHUNK_SIZE + lx
            wy = cy * CHUNK_SIZE + ly
            return self.get_block(wx, wy, lz)

        for axis in range(3):
            u = (axis + 1) % 3
            v = (axis + 2) % 3
            q = [0, 0, 0]
            q[axis] = 1
            x = [0, 0, 0]

            for x[axis] in range(-1, dims[axis]):
                mask: list[FaceMask | None] = [None] * (dims[u] * dims[v])
                n = 0
                for x[v] in range(dims[v]):
                    for x[u] in range(dims[u]):
                        a = local_block(x[0], x[1], x[2]) if x[axis] >= 0 else 0
                        b = local_block(x[0] + q[0], x[1] + q[1], x[2] + q[2])
                        mask[n] = self._face_mask_entry(a, b, axis)
                        n += 1

                x[axis] += 1
                n = 0
                for j in range(dims[v]):
                    i = 0
                    while i < dims[u]:
                        face = mask[n]
                        if face is None or face.transparent != transparent:
                            i += 1
                            n += 1
                            continue

                        width = 1
                        while i + width < dims[u] and mask[n + width] == face:
                            width += 1

                        height = 1
                        done = False
                        while j + height < dims[v] and not done:
                            for k in range(width):
                                if mask[n + k + height * dims[u]] != face:
                                    done = True
                                    break
                            if not done:
                                height += 1

                        base = [x[0], x[1], x[2]]
                        du = [0, 0, 0]
                        dv = [0, 0, 0]
                        du[u] = width
                        dv[v] = height
                        base[u] = i
                        base[v] = j

                        self._emit_quad(vertex, normal, color, texcoord, triangles, base, du, dv, face)
                        quad_count += 1

                        for y2 in range(height):
                            for x2 in range(width):
                                mask[n + x2 + y2 * dims[u]] = None
                        i += width
                        n += width

        if quad_count == 0:
            return None, 0

        geom = Geom(vdata)
        geom.addPrimitive(triangles)
        node = GeomNode('transparent_mesh' if transparent else 'opaque_mesh')
        node.addGeom(geom)
        return node, quad_count

    def _face_mask_entry(self, a: int, b: int, axis: int) -> FaceMask | None:
        if a != 0 and b == 0:
            return FaceMask(a, axis, 1, BLOCK_DEFS[a].alpha < 1.0)
        if b != 0 and a == 0:
            return FaceMask(b, axis, -1, BLOCK_DEFS[b].alpha < 1.0)
        return None

    def _emit_quad(self, vertex, normal, color, texcoord, triangles, base, du, dv, face: FaceMask) -> None:
        start = vertex.getWriteRow()
        bx, by, bz = (float(base[0]), float(base[1]), float(base[2]))
        duv = (float(du[0]), float(du[1]), float(du[2]))
        dvv = (float(dv[0]), float(dv[1]), float(dv[2]))

        p0 = (bx, by, bz)
        p1 = (bx + duv[0], by + duv[1], bz + duv[2])
        p2 = (bx + duv[0] + dvv[0], by + duv[1] + dvv[1], bz + duv[2] + dvv[2])
        p3 = (bx + dvv[0], by + dvv[1], bz + dvv[2])
        positions = [p0, p1, p2, p3] if face.normal_sign > 0 else [p0, p3, p2, p1]

        nx, ny, nz = 0.0, 0.0, 0.0
        if face.axis == 0:
            nx = float(face.normal_sign)
        elif face.axis == 1:
            ny = float(face.normal_sign)
        else:
            nz = float(face.normal_sign)

        shade = 0.86
        if face.axis == 2 and face.normal_sign > 0:
            shade = 1.0
        elif face.axis == 2 and face.normal_sign < 0:
            shade = 0.58
        elif face.axis == 0:
            shade = 0.80
        elif face.axis == 1:
            shade = 0.90

        alpha = BLOCK_DEFS[face.block_id].alpha
        tile_index = get_face_tile(face.block_id, face.axis, face.normal_sign)
        u0, v0, u1, v1 = get_tile_uv(tile_index)
        uvs = [(u0, v0), (u1, v0), (u1, v1), (u0, v1)]

        for (px, py, pz), (u, vv) in zip(positions, uvs):
            vertex.addData3(px, py, pz)
            normal.addData3(nx, ny, nz)
            color.addData4(shade, shade, shade, alpha)
            texcoord.addData2(u, vv)

        triangles.addVertices(start, start + 1, start + 2)
        triangles.addVertices(start, start + 2, start + 3)

    def set_block(self, x: int, y: int, z: int, block_id: int) -> None:
        if z < 0 or z >= WORLD_HEIGHT_LIMIT:
            return
        base = self._base_block(x, y, z)
        key = (x, y, z)
        if block_id == base:
            self.modifications.pop(key, None)
        else:
            self.modifications[key] = block_id
        self._mark_neighbors_dirty(x, y)

    def _base_block(self, x: int, y: int, z: int) -> int:
        ck = self.world_to_chunk(x, y)
        lx, ly = self.world_to_local(x, y)
        chunk = self.ensure_chunk(ck)
        if not chunk.generated:
            self._generate_chunk(chunk)
        return chunk.base_blocks.get((lx, ly, z), 0)

    def _mark_neighbors_dirty(self, x: int, y: int) -> None:
        cx, cy = self.world_to_chunk(x, y)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                chunk = self.chunks.get((cx + dx, cy + dy))
                if chunk:
                    chunk.dirty = True

    def raycast_blocks(self, origin: LPoint3f, direction: LVector3f, max_distance: float = MAX_RAY_DISTANCE):
        step = 0.1
        pos = LPoint3f(origin)
        direction = LVector3f(direction)
        if direction.length_squared() == 0:
            return None
        direction.normalize()
        previous_cell = None
        traveled = 0.0
        while traveled <= max_distance:
            cell = (math.floor(pos.x), math.floor(pos.y), math.floor(pos.z))
            if cell != previous_cell and self.get_block(*cell) != 0:
                return {
                    'hit': cell,
                    'place': previous_cell,
                    'distance': traveled,
                }
            previous_cell = cell
            pos += direction * step
            traveled += step
        return None

    def pick_camera_target(self, target: LPoint3f, desired_camera_pos: LPoint3f) -> LPoint3f:
        direction = desired_camera_pos - target
        distance = direction.length()
        if distance <= 1e-4:
            return desired_camera_pos
        direction.normalize()

        world_up = LVector3f(0.0, 0.0, 1.0)
        right = direction.cross(world_up)
        if right.length_squared() < 1e-6:
            right = LVector3f(1.0, 0.0, 0.0)
        else:
            right.normalize()
        up = right.cross(direction)
        if up.length_squared() < 1e-6:
            up = LVector3f(0.0, 0.0, 1.0)
        else:
            up.normalize()

        probe = 0.18
        offsets = [
            LVector3f(0.0, 0.0, 0.0),
            right * probe,
            right * -probe,
            up * probe,
            up * -probe,
            (right + up) * (probe * 0.72),
            (right - up) * (probe * 0.72),
            (-right + up) * (probe * 0.72),
            (-right - up) * (probe * 0.72),
        ]

        safe_distance = distance
        for offset in offsets:
            result = self.raycast_blocks(target + offset, direction, distance)
            if result:
                safe_distance = min(safe_distance, result['distance'] - CAMERA_COLLISION_PADDING)

        if safe_distance >= distance:
            return desired_camera_pos
        safe_distance = max(0.55, safe_distance)
        return target + direction * safe_distance
