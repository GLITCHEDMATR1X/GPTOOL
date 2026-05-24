"""
Outer dimension grid adapter.

Pass 19 keeps the terrain/grid shared, then lets Tab switch active dimension
content. Dimension-owned content is loaded from drop-in asset folders under
assets/holocore/biome*/ or the host HoloVerse shared assets/holocore tree.
Old biome objects fade out, new biome objects fade in, and the
neon grid palette refreshes without changing the terrain surface.
"""
from __future__ import annotations

import math
from random import Random
from dataclasses import dataclass, field
from pathlib import Path

from panda3d.core import (
    Geom,
    GeomNode,
    GeomTriangles,
    GeomVertexData,
    GeomVertexFormat,
    GeomVertexWriter,
    LineSegs,
    NodePath,
    TransparencyAttrib,
    Vec3,
)
from direct.task import Task

from dimensions.dimension_manager import DimensionManager
from dimensions.surface_placement import SurfacePlacementSystem
try:
    from assets.entities.holo_mermaid import HoloMermaidMob, MERMAID_SPAWN_CHANCE, MERMAID_HEIGHT_OFFSET, MERMAID_MIN_DISTANCE_FROM_HUB, stable_chunk_seed
except Exception:  # pragma: no cover - keeps editor/static probes safe if Panda3D import fails.
    try:
        from holo_mermaid import HoloMermaidMob, MERMAID_SPAWN_CHANCE, MERMAID_HEIGHT_OFFSET, MERMAID_MIN_DISTANCE_FROM_HUB, stable_chunk_seed
    except Exception:
        HoloMermaidMob = None
        MERMAID_SPAWN_CHANCE = 0.10
        MERMAID_HEIGHT_OFFSET = 8.25
        MERMAID_MIN_DISTANCE_FROM_HUB = 660.0
        def stable_chunk_seed(chunk_key, salt=0x4D3D5EA):
            return ((int(chunk_key[0]) * 73856093) ^ (int(chunk_key[1]) * 19349663) ^ int(salt)) & 0xFFFFFFFF
try:
    from assets.entities.holo_jellyfish import HoloJellyfishMob, JELLYFISH_SPAWN_CHANCE, JELLYFISH_HEIGHT_OFFSET, JELLYFISH_MIN_DISTANCE_FROM_HUB, JELLYFISH_VARIANTS, stable_jellyfish_seed
except Exception:  # pragma: no cover - keeps editor/static probes safe if Panda3D import fails.
    try:
        from holo_jellyfish import HoloJellyfishMob, JELLYFISH_SPAWN_CHANCE, JELLYFISH_HEIGHT_OFFSET, JELLYFISH_MIN_DISTANCE_FROM_HUB, JELLYFISH_VARIANTS, stable_jellyfish_seed
    except Exception:
        HoloJellyfishMob = None
        JELLYFISH_SPAWN_CHANCE = 0.20
        JELLYFISH_HEIGHT_OFFSET = 12.75
        JELLYFISH_MIN_DISTANCE_FROM_HUB = 620.0
        JELLYFISH_VARIANTS = ()
        def stable_jellyfish_seed(chunk_key, salt=0x4A311F15):
            return ((int(chunk_key[0]) * 83492791) ^ (int(chunk_key[1]) * 2654435761) ^ int(salt)) & 0xFFFFFFFF
try:
    from assets.entities.holo_octopus import (
        HoloOctopusMob,
        OCTOPUS_SPAWN_CHANCE,
        OCTOPUS_HEIGHT_OFFSET,
        OCTOPUS_HEIGHT_VARIANCE,
        OCTOPUS_MIN_DISTANCE_FROM_HUB,
        OCTOPUS_UPDATE_INTERVAL,
        stable_octopus_seed,
    )
except Exception:  # pragma: no cover - keeps editor/static probes safe if Panda3D import fails.
    try:
        from holo_octopus import (
            HoloOctopusMob,
            OCTOPUS_SPAWN_CHANCE,
            OCTOPUS_HEIGHT_OFFSET,
            OCTOPUS_HEIGHT_VARIANCE,
            OCTOPUS_MIN_DISTANCE_FROM_HUB,
            OCTOPUS_UPDATE_INTERVAL,
            stable_octopus_seed,
        )
    except Exception:
        HoloOctopusMob = None
        OCTOPUS_SPAWN_CHANCE = 0.03
        OCTOPUS_HEIGHT_OFFSET = 18.0
        OCTOPUS_HEIGHT_VARIANCE = 13.0
        OCTOPUS_MIN_DISTANCE_FROM_HUB = 720.0
        OCTOPUS_UPDATE_INTERVAL = 1.0 / 10.0
        def stable_octopus_seed(chunk_key, salt=0x0C70B00F):
            return ((int(chunk_key[0]) * 92837111) ^ (int(chunk_key[1]) * 689287499) ^ int(salt)) & 0xFFFFFFFF

try:
    from assets.entities.biome_entity_registry import BIOME_ENTITY_SPECS
except Exception:  # pragma: no cover - keeps editor/static probes safe if biome entity imports fail.
    BIOME_ENTITY_SPECS = {}
from world_grid import (
    CELL_SIZE,
    BIOME_BLEND_WIDTH,
    BIOME_DISTANCE_STRIDE,
    TERRAIN_MESH_STEP,
    GRID_LINE_SAMPLE_STEP,
    FLAT_WORLD_RADIUS,
    HUB_VISUAL_EXTENT,
    REGION_SIZE,
    STREAM_CHUNK_SIZE,
    Rect,
    chunk_index_for,
    chunk_rect,
    horizontal_segments_excluding_hub,
    iter_world_lines,
    line_is_major_cell,
    line_is_region_boundary,
    rects_excluding_center_square,
    sonar_color_boost_at,
    sonar_height_at,
    vertical_segments_excluding_hub,
)


FADE_IN_SECONDS = 0.90
FADE_OUT_SECONDS = 0.70
BUILDS_PER_FRAME = 1
GRID_REFRESHES_PER_FRAME = 1
BIOME_REFRESHES_PER_FRAME = 1
MOB_MIN_SURFACE_CLEARANCE = 3.0
MOB_FADE_FULL_DISTANCE = 560.0
MOB_FADE_START_DISTANCE = 820.0


@dataclass
class StreamedChunk:
    """Runtime state for a streamed dimension chunk."""

    key: tuple[int, int]
    node: NodePath
    rect: Rect
    surface_layer: NodePath | None = None
    grid_layer: NodePath | None = None
    alpha: float = 0.0
    state: str = "fading_in"  # fading_in | stable | fading_out
    rendered_alpha: float | None = None

    def apply_alpha(self) -> None:
        alpha = max(0.0, min(1.0, self.alpha))
        if self.rendered_alpha is not None and abs(self.rendered_alpha - alpha) < 0.002:
            return
        if self.rendered_alpha is None:
            self.node.setTransparency(TransparencyAttrib.MAlpha)
        self.node.setColorScale(1.0, 1.0, 1.0, alpha)
        self.rendered_alpha = alpha


@dataclass
class FlatOuterWorldAdapter:
    """Streaming adapter for the surrounding shared dimension grid."""

    outer_extent: float = 520.0
    floor_z: float = -0.10
    chunk_size: float = STREAM_CHUNK_SIZE
    stream_radius: int = 3
    root: NodePath | None = None
    seam_node: NodePath | None = None
    active_chunks: dict[tuple[int, int], StreamedChunk] = field(default_factory=dict)
    desired_chunks: set[tuple[int, int]] = field(default_factory=set)
    build_queue: list[tuple[int, int]] = field(default_factory=list)
    grid_refresh_queue: list[tuple[int, int]] = field(default_factory=list)
    biome_refresh_queue: list[tuple[int, int]] = field(default_factory=list)
    last_center_chunk: tuple[int, int] | None = None
    last_auto_dimension_index: int | None = None
    dimension_manager: DimensionManager | None = None
    surface_objects: SurfacePlacementSystem | None = None
    mermaid_mobs: dict[tuple[int, int], object] = field(default_factory=dict)
    mermaid_spawn_chance: float = MERMAID_SPAWN_CHANCE
    mermaid_update_interval: float = 1.0 / 30.0
    _mermaid_update_elapsed: float = 0.0
    jellyfish_mobs: dict[tuple[int, int], object] = field(default_factory=dict)
    jellyfish_spawn_chance: float = JELLYFISH_SPAWN_CHANCE
    jellyfish_update_interval: float = 1.0 / 24.0
    _jellyfish_update_elapsed: float = 0.0
    octopus_mobs: dict[tuple[int, int], object] = field(default_factory=dict)
    octopus_spawn_chance: float = OCTOPUS_SPAWN_CHANCE
    octopus_update_interval: float = OCTOPUS_UPDATE_INTERVAL
    _octopus_update_elapsed: float = 0.0
    biome_entity_mobs: dict[tuple[int, int], object] = field(default_factory=dict)
    biome_entity_update_interval: float = 1.0 / 20.0
    _biome_entity_update_elapsed: float = 0.0

    @staticmethod
    def _asset_root_has_biomes(path: Path) -> bool:
        """Return True when an asset root has at least one usable biome folder.

        Empty folders are still valid: they keep the drop-in contract stable
        while future biome objects are added.
        """
        try:
            return bool(path.exists() and any(child.is_dir() and child.name.startswith("biome") for child in path.iterdir()))
        except Exception:
            return False

    def build(self, app, hub_adapter) -> "FlatOuterWorldAdapter":
        self.app = app
        self.render = app.render
        self.hub = hub_adapter
        self.root = self.render.attachNewNode("dimension_layered_grid_world_root")

        # Prefer HoloVerse host-level assets when mounted as a same-window
        # HoloVerse adapter, then fall back to this HoloCore drop's local
        # asset authority. The final legacy path keeps older drops loadable.
        root_dir = Path(__file__).resolve().parents[1]
        host_assets_root = Path(__file__).resolve().parents[2] / "assets" / "holocore"
        local_assets_root = root_dir / "assets" / "holocore"
        legacy_assets_root = root_dir / "assets"
        assets_root = next((candidate for candidate in (host_assets_root, local_assets_root, legacy_assets_root) if self._asset_root_has_biomes(candidate)), local_assets_root)
        self.dimension_manager = DimensionManager(assets_root=assets_root)
        self.surface_objects = SurfacePlacementSystem(
            asset_dir=self.dimension_manager.active_asset_dir,
            floor_z=self.floor_z,
            surface_height=sonar_height_at,
        ).load_assets()

        self.sync_around(Vec3(0, 0, 0), force=True, immediate=False)
        self._build_hub_seam_marker()
        return self

    @property
    def walk_limit(self) -> float:
        return float("inf")

    def collision_ground_z_at(self, x: float, y: float) -> float:
        """Return the player-footing height for the shared terrain surface.

        The rendered outer floor is built at ``floor_z + sonar_height_at``.
        Player feet sit a small clearance above that mesh so the camera reads as
        standing on the neon surface instead of clipping through it. Keeping
        this tied to the same global height function makes the ground stay solid
        across streamed chunks and automatic biome-band transitions.
        """
        # The hub and visual floor use a slight -Z offset to prevent z-fighting
        # against grid lines.  Player feet stay at z=0 in the hub and then track
        # the same sampled sonar height used by the streamed outer terrain.
        return sonar_height_at(float(x), float(y))

    def clamp_position(self, pos: Vec3) -> Vec3:
        # Terrain is now collision-authoritative instead of visual-only.  This
        # fixes the old failure where travelling far enough to cross an
        # automatic biome band left the player walking through/above the newly
        # streamed surface.
        pos.setZ(self.collision_ground_z_at(pos.x, pos.y))
        return pos

    @property
    def active_dimension_name(self) -> str:
        if self.dimension_manager is None:
            return "Unknown Dimension"
        return self.dimension_manager.active.name

    def cycle_dimension(self, immediate: bool = False) -> str:
        """Switch active dimension/biome layer with no UI."""
        if self.dimension_manager is None or self.surface_objects is None:
            return "Unknown Dimension"
        definition = self.dimension_manager.set_index(self.dimension_manager.active_index + 1)
        self._activate_dimension_assets(immediate=immediate)
        self.last_auto_dimension_index = self.dimension_manager.active_index
        if immediate:
            self._settle_grid_refresh_queue()
            self._settle_biome_refresh_queue()
        print(f"active dimension: {definition.dimension_id} | {definition.name}")
        return definition.name

    def _dimension_index_for_distance(self, distance: float) -> int:
        if self.dimension_manager is None or not self.dimension_manager.dimensions:
            return 0
        exploration = max(0.0, float(distance or 0.0) - FLAT_WORLD_RADIUS)
        return int(exploration // max(1.0, BIOME_DISTANCE_STRIDE)) % len(self.dimension_manager.dimensions)

    def _sync_auto_dimension_for_position(self, pos: Vec3, immediate: bool = False) -> None:
        if self.dimension_manager is None or self.surface_objects is None:
            return
        distance = math.hypot(float(pos.x), float(pos.y))
        if distance - FLAT_WORLD_RADIUS < BIOME_DISTANCE_STRIDE - BIOME_BLEND_WIDTH:
            if self.last_auto_dimension_index is None:
                self.last_auto_dimension_index = self.dimension_manager.active_index
            return
        target_index = self._dimension_index_for_distance(distance)
        if self.last_auto_dimension_index is None:
            self.last_auto_dimension_index = self.dimension_manager.active_index
        if target_index == self.dimension_manager.active_index:
            self.last_auto_dimension_index = target_index
            return
        definition = self.dimension_manager.set_index(target_index)
        self.last_auto_dimension_index = target_index
        self._activate_dimension_assets(immediate=immediate)
        print(
            "auto biome band: "
            f"{definition.dimension_id} | {definition.name} | "
            f"distance={distance:.0f} stride={BIOME_DISTANCE_STRIDE:.0f} blend={BIOME_BLEND_WIDTH:.0f}"
        )

    def _activate_dimension_assets(self, immediate: bool = False) -> None:
        if self.dimension_manager is None or self.surface_objects is None:
            return
        self.surface_objects.set_asset_dir(self.dimension_manager.active_asset_dir)
        self._clear_biome_entities()
        for key, record in list(self.active_chunks.items()):
            if record.node.isEmpty():
                continue
            if key not in self.grid_refresh_queue:
                self.grid_refresh_queue.append(key)
            if key not in self.biome_refresh_queue:
                self.biome_refresh_queue.append(key)
        if immediate:
            self._settle_grid_refresh_queue()
            self._settle_biome_refresh_queue()

    def sync_around(self, pos: Vec3, force: bool = False, immediate: bool = False) -> None:
        if self.root is None:
            return
        self._sync_auto_dimension_for_position(pos, immediate=immediate)
        center = (
            chunk_index_for(pos.x, self.chunk_size),
            chunk_index_for(pos.y, self.chunk_size),
        )
        if not force and center == self.last_center_chunk:
            return
        self.last_center_chunk = center

        desired: set[tuple[int, int]] = set()
        cx, cy = center
        for dx in range(-self.stream_radius, self.stream_radius + 1):
            for dy in range(-self.stream_radius, self.stream_radius + 1):
                desired.add((cx + dx, cy + dy))
        self.desired_chunks = desired

        missing = [key for key in desired if key not in self.active_chunks and key not in self.build_queue]
        missing.sort(key=lambda key: (key[0] - cx) ** 2 + (key[1] - cy) ** 2)
        self.build_queue.extend(missing)

        for key in desired:
            record = self.active_chunks.get(key)
            if record is not None and record.state == "fading_out":
                record.state = "fading_in"

        for key, record in list(self.active_chunks.items()):
            if key not in desired and record.state != "fading_out":
                record.state = "fading_out"

        if immediate:
            self._settle_streaming_queue()

    def _settle_streaming_queue(self) -> None:
        guard = 0
        while self.build_queue and guard < 512:
            key = self.build_queue.pop(0)
            if key in self.desired_chunks and key not in self.active_chunks:
                record = self._build_chunk_record(*key)
                record.alpha = 1.0
                record.state = "stable"
                record.apply_alpha()
                self.active_chunks[key] = record
            guard += 1
        for key, record in list(self.active_chunks.items()):
            if key not in self.desired_chunks:
                self._remove_chunk_record(key, record)
        self._settle_grid_refresh_queue()
        self._settle_biome_refresh_queue()

    def _settle_grid_refresh_queue(self) -> None:
        guard = 0
        while self.grid_refresh_queue and guard < 512:
            key = self.grid_refresh_queue.pop(0)
            record = self.active_chunks.get(key)
            if record is not None and not record.node.isEmpty():
                self._refresh_chunk_visuals(record)
            guard += 1

    def _settle_biome_refresh_queue(self) -> None:
        guard = 0
        while self.biome_refresh_queue and guard < 512:
            key = self.biome_refresh_queue.pop(0)
            record = self.active_chunks.get(key)
            if record is not None and not record.node.isEmpty():
                self._replace_chunk_surface_objects(record, fade=False)
            guard += 1

    def _process_streaming_frame(self, dt: float) -> None:
        built = 0
        while self.build_queue and built < BUILDS_PER_FRAME:
            key = self.build_queue.pop(0)
            if key not in self.desired_chunks or key in self.active_chunks:
                continue
            record = self._build_chunk_record(*key)
            record.alpha = 0.0
            record.state = "fading_in"
            record.apply_alpha()
            self.active_chunks[key] = record
            built += 1

        refreshed = 0
        while self.grid_refresh_queue and refreshed < GRID_REFRESHES_PER_FRAME:
            key = self.grid_refresh_queue.pop(0)
            record = self.active_chunks.get(key)
            if record is not None and not record.node.isEmpty():
                self._refresh_chunk_visuals(record)
                refreshed += 1

        biome_refreshed = 0
        while self.biome_refresh_queue and biome_refreshed < BIOME_REFRESHES_PER_FRAME:
            key = self.biome_refresh_queue.pop(0)
            record = self.active_chunks.get(key)
            if record is not None and not record.node.isEmpty():
                self._replace_chunk_surface_objects(record, fade=True)
                biome_refreshed += 1

        for key, record in list(self.active_chunks.items()):
            if record.node.isEmpty():
                self.active_chunks.pop(key, None)
                continue
            alpha_changed = False
            if record.state == "fading_in":
                record.alpha = min(1.0, record.alpha + dt / max(0.01, FADE_IN_SECONDS))
                if record.alpha >= 1.0:
                    record.state = "stable"
                alpha_changed = True
            elif record.state == "fading_out":
                record.alpha = max(0.0, record.alpha - dt / max(0.01, FADE_OUT_SECONDS))
                if record.alpha <= 0.0:
                    self._remove_chunk_record(key, record)
                    continue
                alpha_changed = True
            if alpha_changed:
                record.apply_alpha()

    def _remove_chunk_record(self, key: tuple[int, int], record: StreamedChunk) -> None:
        if self.surface_objects is not None:
            self.surface_objects.remove_chunk(key)
        mob = self.mermaid_mobs.pop(key, None)
        if mob is not None:
            try:
                mob.destroy()
            except Exception:
                pass
        jelly = self.jellyfish_mobs.pop(key, None)
        if jelly is not None:
            try:
                jelly.destroy()
            except Exception:
                pass
        octo = self.octopus_mobs.pop(key, None)
        if octo is not None:
            try:
                octo.destroy()
            except Exception:
                pass
        biome_mob = self.biome_entity_mobs.pop(key, None)
        if biome_mob is not None:
            try:
                biome_mob.destroy()
            except Exception:
                pass
        if not record.node.isEmpty():
            record.node.removeNode()
        self.active_chunks.pop(key, None)
        self.grid_refresh_queue = [queued for queued in self.grid_refresh_queue if queued != key]
        self.biome_refresh_queue = [queued for queued in self.biome_refresh_queue if queued != key]

    def _build_chunk_record(self, cx: int, cy: int) -> StreamedChunk:
        assert self.root is not None
        rect = chunk_rect(cx, cy, self.chunk_size)
        chunk_np = self.root.attachNewNode(f"dimension_layered_grid_chunk_{cx}_{cy}")
        chunk_np.setTransparency(TransparencyAttrib.MAlpha)
        chunk_np.setColorScale(1.0, 1.0, 1.0, 0.0)
        surface_layer = self._build_chunk_surface(chunk_np, rect)
        grid_layer = self._build_chunk_grid(chunk_np, rect)
        self._build_chunk_surface_objects(chunk_np, rect, (cx, cy))
        self._build_chunk_mermaid(chunk_np, rect, (cx, cy))
        self._build_chunk_jellyfish(chunk_np, rect, (cx, cy))
        self._build_chunk_octopus(chunk_np, rect, (cx, cy))
        self._build_chunk_biome_entity(chunk_np, rect, (cx, cy))
        return StreamedChunk(key=(cx, cy), node=chunk_np, rect=rect, surface_layer=surface_layer, grid_layer=grid_layer)

    def _refresh_chunk_visuals(self, record: StreamedChunk) -> None:
        self._rebuild_chunk_surface(record)
        self._rebuild_chunk_grid(record)

    def _rebuild_chunk_surface(self, record: StreamedChunk) -> None:
        if record.surface_layer is not None and not record.surface_layer.isEmpty():
            record.surface_layer.removeNode()
        record.surface_layer = self._build_chunk_surface(record.node, record.rect)

    def _rebuild_chunk_grid(self, record: StreamedChunk) -> None:
        if record.grid_layer is not None and not record.grid_layer.isEmpty():
            record.grid_layer.removeNode()
        record.grid_layer = self._build_chunk_grid(record.node, record.rect)

    def _terrain_z(self, x: float, y: float, line_lift: float = 0.0) -> float:
        return self.floor_z + sonar_height_at(x, y) + line_lift

    def _coords_for_rect(self, start: float, end: float) -> list[float]:
        coords = [float(start)]
        for value in iter_world_lines(start, end, TERRAIN_MESH_STEP):
            if start < value < end:
                coords.append(float(value))
        coords.append(float(end))
        out: list[float] = []
        for value in coords:
            if not out or not math.isclose(out[-1], value, abs_tol=1e-6):
                out.append(round(value, 6))
        return out

    def _surface_color(self, x: float, y: float) -> tuple[float, float, float, float]:
        distance = math.hypot(x, y)
        far = max(0.0, min(1.0, (distance - FLAT_WORLD_RADIUS) / 900.0))
        boost = sonar_color_boost_at(x, y)
        tint = (0.55, 0.80, 1.00)
        if self.dimension_manager is not None:
            tint = self.dimension_manager.active.palette.surface_tint
        base = 0.0008 + 0.0035 * boost
        return (
            base * tint[0] + 0.0005 * far,
            base * tint[1] + 0.0010 * far,
            base * tint[2] + 0.0020 * far,
            0.78,
        )

    def _build_chunk_surface(self, chunk_np: NodePath, rect: Rect) -> NodePath:
        fmt = GeomVertexFormat.getV3c4()
        surface_layer = chunk_np.attachNewNode("dimension_surface_layer")
        for idx, sub_rect in enumerate(rects_excluding_center_square(rect, HUB_VISUAL_EXTENT)):
            xs = self._coords_for_rect(sub_rect.x1, sub_rect.x2)
            ys = self._coords_for_rect(sub_rect.y1, sub_rect.y2)
            if len(xs) < 2 or len(ys) < 2:
                continue

            vdata = GeomVertexData(f"dimension_surface_{idx}", fmt, Geom.UHStatic)
            vw = GeomVertexWriter(vdata, "vertex")
            cw = GeomVertexWriter(vdata, "color")

            for y in ys:
                for x in xs:
                    vw.addData3(x, y, self._terrain_z(x, y, 0.0))
                    cw.addData4(*self._surface_color(x, y))

            prim = GeomTriangles(Geom.UHStatic)
            width = len(xs)
            for row in range(len(ys) - 1):
                for col in range(len(xs) - 1):
                    a = row * width + col
                    b = a + 1
                    c = a + width
                    d = c + 1
                    prim.addVertices(a, c, b)
                    prim.addVertices(b, c, d)
            prim.closePrimitive()

            geom = Geom(vdata)
            geom.addPrimitive(prim)
            node = GeomNode(f"dimension_surface_node_{idx}")
            node.addGeom(geom)
            surface = surface_layer.attachNewNode(node)
            surface.setLightOff()
            surface.setTransparency(TransparencyAttrib.MAlpha)
            surface.setBin("background", -3)
        return surface_layer

    def _line_color(self, value: float) -> tuple[float, float, float, float]:
        if self.dimension_manager is None:
            if line_is_region_boundary(value):
                return (1.00, 0.060, 0.045, 0.62)
            if line_is_major_cell(value):
                return (0.12, 0.92, 1.00, 0.50)
            return (0.060, 0.70, 0.98, 0.25)
        palette = self.dimension_manager.active.palette
        if line_is_region_boundary(value):
            return palette.region
        if line_is_major_cell(value):
            return palette.major
        return palette.minor

    def _line_glow_color(self, value: float) -> tuple[float, float, float, float]:
        if self.dimension_manager is None:
            if line_is_region_boundary(value):
                return (1.00, 0.055, 0.040, 0.16)
            if line_is_major_cell(value):
                return (0.10, 0.86, 1.00, 0.14)
            return (0.040, 0.68, 1.00, 0.060)
        palette = self.dimension_manager.active.palette
        if line_is_region_boundary(value):
            return palette.region_glow
        if line_is_major_cell(value):
            return palette.major_glow
        return palette.minor_glow

    def _sample_line_values(self, start: float, end: float) -> list[float]:
        values = [float(start)]
        for value in iter_world_lines(start, end, GRID_LINE_SAMPLE_STEP):
            if start < value < end:
                values.append(float(value))
        values.append(float(end))
        out: list[float] = []
        for value in values:
            if not out or not math.isclose(out[-1], value, abs_tol=1e-6):
                out.append(round(value, 6))
        return out

    def _draw_grid_into(self, grid: LineSegs, rect: Rect, color_fn, line_lift: float, include_contours: bool = True) -> None:
        for x in iter_world_lines(rect.x1, rect.x2, CELL_SIZE):
            grid.setColor(*color_fn(x))
            for y1, y2 in vertical_segments_excluding_hub(x, rect.y1, rect.y2, HUB_VISUAL_EXTENT):
                samples = self._sample_line_values(y1, y2)
                if not samples:
                    continue
                grid.moveTo(x, samples[0], self._terrain_z(x, samples[0], line_lift))
                for y in samples[1:]:
                    grid.drawTo(x, y, self._terrain_z(x, y, line_lift))

        for y in iter_world_lines(rect.y1, rect.y2, CELL_SIZE):
            grid.setColor(*color_fn(y))
            for x1, x2 in horizontal_segments_excluding_hub(y, rect.x1, rect.x2, HUB_VISUAL_EXTENT):
                samples = self._sample_line_values(x1, x2)
                if not samples:
                    continue
                grid.moveTo(samples[0], y, self._terrain_z(samples[0], y, line_lift + 0.010))
                for x in samples[1:]:
                    grid.drawTo(x, y, self._terrain_z(x, y, line_lift + 0.010))

        if not include_contours:
            return

        contour = (0.18, 0.96, 1.0, 0.13)
        if self.dimension_manager is not None:
            major = self.dimension_manager.active.palette.major
            contour = (major[0], major[1], major[2], 0.13)
        for y in iter_world_lines(rect.y1, rect.y2, REGION_SIZE / 2.0):
            if abs(y) < FLAT_WORLD_RADIUS:
                continue
            grid.setColor(*contour)
            samples = self._sample_line_values(rect.x1, rect.x2)
            grid.moveTo(samples[0], y, self._terrain_z(samples[0], y, line_lift + 0.070))
            for x in samples[1:]:
                grid.drawTo(x, y, self._terrain_z(x, y, line_lift + 0.070))

    def _build_chunk_grid(self, chunk_np: NodePath, rect: Rect) -> NodePath:
        grid_layer = chunk_np.attachNewNode("dimension_grid_layer")
        grid_layer.setTransparency(TransparencyAttrib.MAlpha)

        glow = LineSegs("dimension_grid_glow")
        glow.setThickness(3.6)
        self._draw_grid_into(glow, rect, self._line_glow_color, 0.095, include_contours=False)
        glow_np = grid_layer.attachNewNode(glow.create())
        glow_np.setLightOff()
        glow_np.setTransparency(TransparencyAttrib.MAlpha)
        glow_np.setBin("transparent", 4)

        grid = LineSegs("dimension_grid_lines")
        grid.setThickness(1.15)
        self._draw_grid_into(grid, rect, self._line_color, 0.125, include_contours=True)
        grid_np = grid_layer.attachNewNode(grid.create())
        grid_np.setLightOff()
        grid_np.setTransparency(TransparencyAttrib.MAlpha)
        grid_np.setBin("transparent", 5)
        return grid_layer

    def mermaid_candidate_position(self, chunk_key: tuple[int, int], rect: Rect | None = None) -> Vec3 | None:
        """Return deterministic mermaid spawn position for a chunk, if selected.

        The chance is exactly one roll per chunk. If selected, a few candidate
        positions are tried so the mob stays outside the pyramid/hub footprint.
        """
        if HoloMermaidMob is None:
            return None
        chance = max(0.0, min(1.0, float(self.mermaid_spawn_chance)))
        rng = Random(stable_chunk_seed(chunk_key, salt=0x51A7E11))
        if rng.random() >= chance:
            return None
        if rect is None:
            rect = chunk_rect(int(chunk_key[0]), int(chunk_key[1]), self.chunk_size)
        for _attempt in range(8):
            x = rng.uniform(float(rect.x1) + 24.0, float(rect.x2) - 24.0)
            y = rng.uniform(float(rect.y1) + 24.0, float(rect.y2) - 24.0)
            if math.hypot(x, y) < max(float(MERMAID_MIN_DISTANCE_FROM_HUB), float(HUB_VISUAL_EXTENT) + 80.0):
                continue
            height_offset = self._mob_height_offset(chunk_key, MERMAID_HEIGHT_OFFSET, 5.0, 0x5EAF10A)
            z = self.collision_ground_z_at(x, y) + height_offset
            return Vec3(x, y, z)
        return None

    def _build_chunk_mermaid(self, chunk_np: NodePath, rect: Rect, chunk_key: tuple[int, int]) -> None:
        if HoloMermaidMob is None or chunk_key in self.mermaid_mobs:
            return
        pos = self.mermaid_candidate_position(chunk_key, rect)
        if pos is None:
            return
        try:
            seed = stable_chunk_seed(chunk_key, salt=0xA11E5EA)
            rng = Random(seed)
            scale = rng.uniform(2.35, 2.90)
            heading = rng.uniform(0.0, 360.0)
            height_offset = self._mob_height_offset(chunk_key, MERMAID_HEIGHT_OFFSET, 5.0, 0x5EAF10A)
            mob = HoloMermaidMob(seed=seed, surface_height_offset=height_offset).build(chunk_np, pos, scale=scale, heading=heading)
            self._apply_mob_visibility(mob)
            self.mermaid_mobs[chunk_key] = mob
        except Exception as exc:
            print(f"holocore_mermaid_spawn_silent chunk={chunk_key} err={exc.__class__.__name__}:{exc}")

    def update_mermaid_mobs(self, time_value: float, dt: float) -> None:
        if not self.mermaid_mobs:
            return
        self._mermaid_update_elapsed += max(0.0, float(dt or 0.0))
        if self._mermaid_update_elapsed < self.mermaid_update_interval:
            return
        self._mermaid_update_elapsed = min(self._mermaid_update_elapsed - self.mermaid_update_interval, self.mermaid_update_interval)
        alive: dict[tuple[int, int], object] = {}
        for key, mob in list(self.mermaid_mobs.items()):
            try:
                root = getattr(mob, "root", None)
                if root is None or root.isEmpty():
                    continue
                mob.update_surface_lock(self.collision_ground_z_at)
                mob.update_pose(float(time_value or 0.0))
                self._apply_mob_visibility(mob)
                alive[key] = mob
            except Exception as exc:
                print(f"holocore_mermaid_update_silent chunk={key} err={exc.__class__.__name__}:{exc}")
        self.mermaid_mobs = alive

    def jellyfish_candidate_position(self, chunk_key: tuple[int, int], rect: Rect | None = None) -> Vec3 | None:
        """Return deterministic jellyfish spawn position for a chunk, if selected.

        The chance is one independent 20% roll per streamed chunk.  The selected
        position stays outside the pyramid/hub footprint and is surface-locked
        when spawned.
        """
        if HoloJellyfishMob is None:
            return None
        chance = max(0.20, min(1.0, float(self.jellyfish_spawn_chance)))
        rng = Random(stable_jellyfish_seed(chunk_key, salt=0x7E11A5EA))
        if rng.random() >= chance:
            return None
        if rect is None:
            rect = chunk_rect(int(chunk_key[0]), int(chunk_key[1]), self.chunk_size)
        for _attempt in range(8):
            x = rng.uniform(float(rect.x1) + 26.0, float(rect.x2) - 26.0)
            y = rng.uniform(float(rect.y1) + 26.0, float(rect.y2) - 26.0)
            if math.hypot(x, y) < max(float(JELLYFISH_MIN_DISTANCE_FROM_HUB), float(HUB_VISUAL_EXTENT) + 80.0):
                continue
            height_offset = self._mob_height_offset(chunk_key, JELLYFISH_HEIGHT_OFFSET, 8.0, 0x7E11F15A)
            z = self.collision_ground_z_at(x, y) + height_offset
            return Vec3(x, y, z)
        return None

    def _build_chunk_jellyfish(self, chunk_np: NodePath, rect: Rect, chunk_key: tuple[int, int]) -> None:
        if HoloJellyfishMob is None or chunk_key in self.jellyfish_mobs:
            return
        pos = self.jellyfish_candidate_position(chunk_key, rect)
        if pos is None:
            return
        try:
            seed = stable_jellyfish_seed(chunk_key, salt=0xA17E11A5)
            rng = Random(seed)
            variants = tuple(JELLYFISH_VARIANTS or ())
            variant = variants[seed % len(variants)] if variants else None
            scale_jitter = rng.uniform(0.82, 1.18)
            heading = rng.uniform(0.0, 360.0)
            height_offset = self._mob_height_offset(chunk_key, JELLYFISH_HEIGHT_OFFSET, 8.0, 0x7E11F15A)
            mob = HoloJellyfishMob(seed=seed, variant=variant, surface_height_offset=height_offset).build(
                chunk_np, pos, scale=scale_jitter, heading=heading
            )
            self._apply_mob_visibility(mob)
            self.jellyfish_mobs[chunk_key] = mob
        except Exception as exc:
            print(f"holocore_jellyfish_spawn_silent chunk={chunk_key} err={exc.__class__.__name__}:{exc}")

    def update_jellyfish_mobs(self, time_value: float, dt: float) -> None:
        if not self.jellyfish_mobs:
            return
        self._jellyfish_update_elapsed += max(0.0, float(dt or 0.0))
        if self._jellyfish_update_elapsed < self.jellyfish_update_interval:
            return
        self._jellyfish_update_elapsed = min(self._jellyfish_update_elapsed - self.jellyfish_update_interval, self.jellyfish_update_interval)
        alive: dict[tuple[int, int], object] = {}
        for key, mob in list(self.jellyfish_mobs.items()):
            try:
                root = getattr(mob, "root", None)
                if root is None or root.isEmpty():
                    continue
                mob.update_surface_lock(self.collision_ground_z_at)
                mob.update_pose(float(time_value or 0.0))
                self._apply_mob_visibility(mob)
                alive[key] = mob
            except Exception as exc:
                print(f"holocore_jellyfish_update_silent chunk={key} err={exc.__class__.__name__}:{exc}")
        self.jellyfish_mobs = alive

    def _mob_height_offset(self, chunk_key: tuple[int, int], base: float, variance: float, salt: int) -> float:
        rng = Random(((int(chunk_key[0]) * 119954089) ^ (int(chunk_key[1]) * 1013904223) ^ int(salt)) & 0xFFFFFFFF)
        return max(float(MOB_MIN_SURFACE_CLEARANCE), float(base) + rng.uniform(0.0, max(0.0, float(variance))))

    def _mob_visibility_alpha(self, root: NodePath | None) -> float:
        if root is None or root.isEmpty():
            return 0.0
        try:
            player = getattr(self.app, "player", None)
            if player is None:
                return 1.0
            pp = player.getPos(self.app.render)
            rp = root.getPos(self.app.render)
            dist = math.hypot(float(rp.x - pp.x), float(rp.y - pp.y))
            if dist <= MOB_FADE_FULL_DISTANCE:
                return 1.0
            if dist >= MOB_FADE_START_DISTANCE:
                return 0.0
            return max(0.0, min(1.0, 1.0 - (dist - MOB_FADE_FULL_DISTANCE) / max(1.0, MOB_FADE_START_DISTANCE - MOB_FADE_FULL_DISTANCE)))
        except Exception:
            return 1.0

    def _apply_mob_visibility(self, mob: object) -> None:
        root = getattr(mob, "root", None)
        alpha = self._mob_visibility_alpha(root)
        try:
            if hasattr(mob, "set_visibility_alpha"):
                mob.set_visibility_alpha(alpha)
            elif root is not None and not root.isEmpty():
                root.setTransparency(TransparencyAttrib.MAlpha)
                root.setColorScale(1.0, 1.0, 1.0, alpha)
        except Exception:
            pass

    def _mob_anchor_positions(self, mob_dict: dict[tuple[int, int], object]) -> list[Vec3]:
        anchors: list[Vec3] = []
        for mob in list(mob_dict.values()):
            root = getattr(mob, "root", None)
            try:
                if root is not None and not root.isEmpty():
                    anchors.append(root.getPos(self.render))
            except Exception:
                pass
        return anchors

    def octopus_candidate_position(self, chunk_key: tuple[int, int], rect: Rect | None = None) -> Vec3 | None:
        """Return deterministic rare octopus position for a selected chunk."""
        if HoloOctopusMob is None:
            return None
        chance = max(0.0, min(1.0, float(self.octopus_spawn_chance)))
        rng = Random(stable_octopus_seed(chunk_key, salt=0x0C700012))
        if rng.random() >= chance:
            return None
        if rect is None:
            rect = chunk_rect(int(chunk_key[0]), int(chunk_key[1]), self.chunk_size)
        height_offset = self._mob_height_offset(chunk_key, OCTOPUS_HEIGHT_OFFSET, OCTOPUS_HEIGHT_VARIANCE, 0x0C700013)
        for _attempt in range(10):
            x = rng.uniform(float(rect.x1) + 30.0, float(rect.x2) - 30.0)
            y = rng.uniform(float(rect.y1) + 30.0, float(rect.y2) - 30.0)
            if math.hypot(x, y) < max(float(OCTOPUS_MIN_DISTANCE_FROM_HUB), float(HUB_VISUAL_EXTENT) + 100.0):
                continue
            z = self.collision_ground_z_at(x, y) + height_offset
            return Vec3(x, y, z)
        return None

    def _build_chunk_octopus(self, chunk_np: NodePath, rect: Rect, chunk_key: tuple[int, int]) -> None:
        if HoloOctopusMob is None or chunk_key in self.octopus_mobs:
            return
        pos = self.octopus_candidate_position(chunk_key, rect)
        if pos is None:
            return
        try:
            seed = stable_octopus_seed(chunk_key, salt=0xA170C70)
            rng = Random(seed)
            scale = rng.uniform(4.9, 6.4)
            heading = rng.uniform(0.0, 360.0)
            height_offset = self._mob_height_offset(chunk_key, OCTOPUS_HEIGHT_OFFSET, OCTOPUS_HEIGHT_VARIANCE, 0x0C700013)
            mob = HoloOctopusMob(seed=seed, surface_height_offset=height_offset).build(chunk_np, pos, scale=scale, heading=heading)
            self._apply_mob_visibility(mob)
            self.octopus_mobs[chunk_key] = mob
        except Exception as exc:
            print(f"holocore_octopus_spawn_silent chunk={chunk_key} err={exc.__class__.__name__}:{exc}")

    def update_octopus_mobs(self, time_value: float, dt: float) -> None:
        if not self.octopus_mobs:
            return
        self._octopus_update_elapsed += max(0.0, float(dt or 0.0))
        if self._octopus_update_elapsed < self.octopus_update_interval:
            return
        step_dt = min(0.2, self._octopus_update_elapsed)
        self._octopus_update_elapsed = min(self._octopus_update_elapsed - self.octopus_update_interval, self.octopus_update_interval)
        mermaid_positions = self._mob_anchor_positions(self.mermaid_mobs)
        jellyfish_positions = self._mob_anchor_positions(self.jellyfish_mobs)
        alive: dict[tuple[int, int], object] = {}
        for key, mob in list(self.octopus_mobs.items()):
            try:
                root = getattr(mob, "root", None)
                if root is None or root.isEmpty():
                    continue
                mob.update_behavior(mermaid_positions, jellyfish_positions, step_dt)
                mob.update_surface_lock(self.collision_ground_z_at)
                mob.update_pose(float(time_value or 0.0))
                self._apply_mob_visibility(mob)
                alive[key] = mob
            except Exception as exc:
                print(f"holocore_octopus_update_silent chunk={key} err={exc.__class__.__name__}:{exc}")
        self.octopus_mobs = alive


    def _active_biome_entity_spec(self):
        if self.dimension_manager is None:
            return None
        folder = str(getattr(self.dimension_manager.active, "biome_folder", "") or "")
        return BIOME_ENTITY_SPECS.get(folder) if isinstance(BIOME_ENTITY_SPECS, dict) else None

    def _remove_biome_entity(self, key: tuple[int, int]) -> None:
        mob = self.biome_entity_mobs.pop(key, None)
        if mob is not None:
            try:
                mob.destroy()
            except Exception:
                pass

    def _clear_biome_entities(self) -> None:
        for key, mob in list(self.biome_entity_mobs.items()):
            try:
                mob.destroy()
            except Exception:
                pass
        self.biome_entity_mobs.clear()

    def _biome_entity_spacing_allows(self, chunk_key: tuple[int, int], spec) -> bool:
        """Sparse deterministic spacing gate for special biome creatures.

        This keeps biome-specific entities from appearing in every nearby
        streamed chunk while still producing stable placements as chunks reload.
        """
        spacing = max(1, int(getattr(spec, "spacing_chunks", 1) or 1))
        if spacing <= 1:
            return True
        cx, cy = int(chunk_key[0]), int(chunk_key[1])
        cell_x = math.floor(cx / spacing)
        cell_y = math.floor(cy / spacing)
        seed_func = getattr(spec, "seed_func", None)
        if not callable(seed_func):
            return False
        seed = seed_func((cell_x, cell_y), int(getattr(spec, "seed_salt", 0xB10E)) ^ 0x5A5A91)
        rng = Random(seed)
        target_x = cell_x * spacing + rng.randrange(spacing)
        target_y = cell_y * spacing + rng.randrange(spacing)
        return cx == target_x and cy == target_y

    def _biome_entity_height_offset(self, chunk_key: tuple[int, int], spec) -> float:
        tiers = tuple(float(v) for v in (getattr(spec, "height_tiers", ()) or ()))
        seed_salt = int(getattr(spec, "seed_salt", 0xB10E))
        if tiers:
            rng = Random(getattr(spec, "seed_func")(chunk_key, seed_salt ^ 0x7717))
            tier = tiers[rng.randrange(len(tiers))]
            variance = max(0.0, float(getattr(spec, "height_variance", 0.0))) * 0.22
            return max(MOB_MIN_SURFACE_CLEARANCE, tier + rng.uniform(-variance, variance))
        return self._mob_height_offset(
            chunk_key,
            float(getattr(spec, "height_offset", 10.0)),
            float(getattr(spec, "height_variance", 4.0)),
            seed_salt ^ 0x7717,
        )

    def biome_entity_candidate_position(self, chunk_key: tuple[int, int], rect: Rect | None = None) -> Vec3 | None:
        """Return deterministic biome-specific entity position for the active biome."""
        spec = self._active_biome_entity_spec()
        if spec is None:
            return None
        if not self._biome_entity_spacing_allows(chunk_key, spec):
            return None
        chance = max(0.0, min(1.0, float(getattr(spec, "spawn_chance", 0.0))))
        seed_func = getattr(spec, "seed_func", None)
        if not callable(seed_func):
            return None
        rng = Random(seed_func(chunk_key, int(getattr(spec, "seed_salt", 0xB10E))))
        if rng.random() >= chance:
            return None
        if rect is None:
            rect = chunk_rect(int(chunk_key[0]), int(chunk_key[1]), self.chunk_size)
        min_distance = max(float(getattr(spec, "min_distance_from_hub", HUB_VISUAL_EXTENT + 120.0)), float(HUB_VISUAL_EXTENT) + 100.0)
        height_offset = self._biome_entity_height_offset(chunk_key, spec)
        for _attempt in range(12):
            margin = min(62.0, max(36.0, float(self.chunk_size) * 0.18))
            x = rng.uniform(float(rect.x1) + margin, float(rect.x2) - margin)
            y = rng.uniform(float(rect.y1) + margin, float(rect.y2) - margin)
            if math.hypot(x, y) < min_distance:
                continue
            z = self.collision_ground_z_at(x, y) + height_offset
            return Vec3(x, y, z)
        return None

    def _build_chunk_biome_entity(self, chunk_np: NodePath, rect: Rect, chunk_key: tuple[int, int]) -> None:
        if chunk_key in self.biome_entity_mobs:
            return
        spec = self._active_biome_entity_spec()
        if spec is None:
            return
        pos = self.biome_entity_candidate_position(chunk_key, rect)
        if pos is None:
            return
        try:
            seed_func = getattr(spec, "seed_func")
            seed = seed_func(chunk_key, int(getattr(spec, "seed_salt", 0xB10E)) ^ 0xA11CE)
            rng = Random(seed)
            scale = rng.uniform(float(getattr(spec, "scale_min", 1.0)), float(getattr(spec, "scale_max", 1.0)))
            heading = rng.uniform(0.0, 360.0)
            height_offset = self._biome_entity_height_offset(chunk_key, spec)
            mob = getattr(spec, "mob_class")(seed=seed, surface_height_offset=height_offset).build(chunk_np, pos, scale=scale, heading=heading)
            setattr(mob, "_holocore_biome_entity_id", str(getattr(spec, "entity_id", "biome_entity")))
            setattr(mob, "_holocore_biome_entity_folder", str(getattr(spec, "biome_folder", "")))
            setattr(mob, "_holocore_biome_entity_behavior", str(getattr(spec, "behavior_id", "")))
            setattr(mob, "_holocore_biome_entity_spacing_chunks", int(getattr(spec, "spacing_chunks", 1) or 1))
            self._apply_mob_visibility(mob)
            self.biome_entity_mobs[chunk_key] = mob
        except Exception as exc:
            print(f"holocore_biome_entity_spawn_silent chunk={chunk_key} err={exc.__class__.__name__}:{exc}")

    def update_biome_entities(self, time_value: float, dt: float) -> None:
        if not self.biome_entity_mobs:
            return
        self._biome_entity_update_elapsed += max(0.0, float(dt or 0.0))
        if self._biome_entity_update_elapsed < self.biome_entity_update_interval:
            return
        self._biome_entity_update_elapsed = min(self._biome_entity_update_elapsed - self.biome_entity_update_interval, self.biome_entity_update_interval)
        alive: dict[tuple[int, int], object] = {}
        active_folder = str(getattr(getattr(self.dimension_manager, "active", None), "biome_folder", "") or "") if self.dimension_manager is not None else ""
        for key, mob in list(self.biome_entity_mobs.items()):
            try:
                root = getattr(mob, "root", None)
                if root is None or root.isEmpty():
                    continue
                if str(getattr(mob, "_holocore_biome_entity_folder", "")) != active_folder:
                    mob.destroy()
                    continue
                mob.update_surface_lock(self.collision_ground_z_at)
                mob.update_pose(float(time_value or 0.0))
                self._apply_mob_visibility(mob)
                alive[key] = mob
            except Exception as exc:
                print(f"holocore_biome_entity_update_silent chunk={key} err={exc.__class__.__name__}:{exc}")
        self.biome_entity_mobs = alive

    def _build_chunk_surface_objects(self, chunk_np: NodePath, rect: Rect, chunk_key: tuple[int, int]) -> None:
        if self.surface_objects is None:
            return
        self.surface_objects.build_for_chunk(chunk_np, rect, chunk_key, fade_in=False)

    def _replace_chunk_surface_objects(self, record: StreamedChunk, fade: bool = True) -> None:
        if self.surface_objects is None:
            return
        self.surface_objects.replace_for_chunk(record.node, record.rect, record.key, fade=fade)
        self._remove_biome_entity(record.key)
        self._build_chunk_biome_entity(record.node, record.rect, record.key)

    def _build_hub_seam_marker(self) -> None:
        assert self.root is not None
        h = self.hub.hub_extent
        seam = LineSegs("outer_world_hub_seam_no_generation_boundary")
        seam.setThickness(2.0)
        seam.setColor(0.08, 0.92, 1.0, 0.52)
        pts = [(-h, -h), (h, -h), (h, h), (-h, h), (-h, -h)]
        for idx, (x, y) in enumerate(pts):
            if idx == 0:
                seam.moveTo(x, y, 0.09)
            else:
                seam.drawTo(x, y, 0.09)
        self.seam_node = self.root.attachNewNode(seam.create())
        self.seam_node.setName("hub_footprint_boundary_world_starts_here")
        self.seam_node.setLightOff()
        self.seam_node.setTransparency(TransparencyAttrib.MAlpha)

    def update(self, task: Task) -> None:
        if hasattr(self.app, "player"):
            self.sync_around(self.app.player.getPos(self.app.render))
        dt = getattr(task, "dt", 0.0) or 0.016
        self._process_streaming_frame(min(dt, 0.05))
        if self.surface_objects is not None:
            self.surface_objects.update(task)
        self.update_mermaid_mobs(task.time, dt)
        self.update_jellyfish_mobs(task.time, dt)
        self.update_octopus_mobs(task.time, dt)
        self.update_biome_entities(task.time, dt)
        if self.seam_node is not None:
            pulse = 0.82 + math.sin(task.time * 0.55) * 0.10
            self.seam_node.setColorScale(1, 1, 1, pulse)

# PASS23_BUBBLE_WEED_SMOOTHER
# Conservative smoothing targets for streamed terrain. Wire these into
# the chunk/flora queues if this source uses custom constant names.
PASS23_CHUNK_BUILDS_PER_FRAME = 1
PASS23_FLORA_BUILDS_PER_FRAME = 1
PASS23_FADE_REMOVALS_PER_FRAME = 3
PASS23_MAX_FRAME_DT = 1.0 / 30.0

# PASS23_BUBBLE_WEED_SMOOTHER
# Conservative smoothing targets for streamed terrain. Wire these into
# the chunk/flora queues if this source uses custom constant names.
PASS23_CHUNK_BUILDS_PER_FRAME = 1
PASS23_FLORA_BUILDS_PER_FRAME = 1
PASS23_FADE_REMOVALS_PER_FRAME = 3
PASS23_MAX_FRAME_DT = 1.0 / 30.0
