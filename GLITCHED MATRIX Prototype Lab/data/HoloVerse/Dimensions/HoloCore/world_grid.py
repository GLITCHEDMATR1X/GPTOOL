"""
Shared dimension grid math for the HoloVerse hub prototype.

Performance pass:
    * Keep one authoritative global grid/terrain surface.
    * Reduce streamed chunk mesh and line sampling cost.
    * Preserve all public names used by HoloCore world adapters.

The rendered floor remains the authority: every dimension/chunk snaps to this
same global coordinate grid instead of creating its own local board.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterator


CELL_SIZE = 20.0           # visible cyan floor cell spacing
MAJOR_CELL_SIZE = 100.0    # stronger cyan line spacing
REGION_SIZE = 200.0        # red dimension-zone spacing
STREAM_CHUNK_SIZE = 240.0  # larger chunks reduce stream churn while travelling
HUB_VISUAL_EXTENT = 130.0  # visible pyramid/hub footprint in hub_world.py
FLAT_WORLD_RADIUS = 360.0  # hub-adjacent dimension floor remains flat
SONAR_TRANSITION_WIDTH = 180.0
SONAR_HEIGHT_SCALE = 12.0

# Pass 55 perf: old 10-unit samples created dense terrain/grid geometry across
# up to 49 streamed chunks. 20-unit sampling keeps the grid aligned while cutting
# terrain vertices and line samples substantially.
TERRAIN_MESH_STEP = 20.0
GRID_LINE_SAMPLE_STEP = 20.0

BIOME_DISTANCE_STRIDE = 1440.0
BIOME_BLEND_WIDTH = 260.0


@dataclass(frozen=True)
class Rect:
    x1: float
    x2: float
    y1: float
    y2: float

    @property
    def valid(self) -> bool:
        return self.x2 > self.x1 and self.y2 > self.y1


def chunk_index_for(value: float, chunk_size: float = STREAM_CHUNK_SIZE) -> int:
    """Return the infinite grid chunk index that contains a world coordinate."""
    return math.floor(value / chunk_size)


def chunk_rect(cx: int, cy: int, chunk_size: float = STREAM_CHUNK_SIZE) -> Rect:
    """Return a world-space rectangle for a streamed chunk index."""
    x1 = cx * chunk_size
    y1 = cy * chunk_size
    return Rect(x1, x1 + chunk_size, y1, y1 + chunk_size)


def iter_world_lines(start: float, end: float, step: float = CELL_SIZE) -> Iterator[float]:
    """Yield globally aligned line coordinates inside [start, end]."""
    first = math.ceil(start / step) * step
    value = first
    epsilon = step * 0.001
    while value <= end + epsilon:
        yield round(value, 6)
        value += step


def line_is_region_boundary(value: float) -> bool:
    return math.isclose(value % REGION_SIZE, 0.0, abs_tol=1e-6) or math.isclose(value % REGION_SIZE, REGION_SIZE, abs_tol=1e-6)


def line_is_major_cell(value: float) -> bool:
    return math.isclose(value % MAJOR_CELL_SIZE, 0.0, abs_tol=1e-6) or math.isclose(value % MAJOR_CELL_SIZE, MAJOR_CELL_SIZE, abs_tol=1e-6)


def rects_excluding_center_square(rect: Rect, exclusion_extent: float = HUB_VISUAL_EXTENT) -> list[Rect]:
    """Split a rectangle so no output rectangle fills the central hub square."""
    h = exclusion_extent
    if rect.x2 <= -h or rect.x1 >= h or rect.y2 <= -h or rect.y1 >= h:
        return [rect] if rect.valid else []

    left = Rect(rect.x1, min(rect.x2, -h), rect.y1, rect.y2)
    right = Rect(max(rect.x1, h), rect.x2, rect.y1, rect.y2)
    bottom = Rect(max(rect.x1, -h), min(rect.x2, h), rect.y1, min(rect.y2, -h))
    top = Rect(max(rect.x1, -h), min(rect.x2, h), max(rect.y1, h), rect.y2)
    return [r for r in (left, right, bottom, top) if r.valid]


def vertical_segments_excluding_hub(x: float, y1: float, y2: float, exclusion_extent: float = HUB_VISUAL_EXTENT) -> list[tuple[float, float]]:
    """Segments for a vertical grid line, clipped out of the hub square."""
    h = exclusion_extent
    if not (-h < x < h):
        return [(y1, y2)]
    return [(a, b) for a, b in ((y1, min(y2, -h)), (max(y1, h), y2)) if b > a]


def horizontal_segments_excluding_hub(y: float, x1: float, x2: float, exclusion_extent: float = HUB_VISUAL_EXTENT) -> list[tuple[float, float]]:
    """Segments for a horizontal grid line, clipped out of the hub square."""
    h = exclusion_extent
    if not (-h < y < h):
        return [(x1, x2)]
    return [(a, b) for a, b in ((x1, min(x2, -h)), (max(x1, h), x2)) if b > a]


def smoothstep(edge0: float, edge1: float, value: float) -> float:
    """Hermite fade used to blend the flat world into sonar terrain."""
    if edge0 == edge1:
        return 1.0 if value >= edge1 else 0.0
    t = max(0.0, min(1.0, (value - edge0) / (edge1 - edge0)))
    return t * t * (3.0 - 2.0 * t)


def _hash01(ix: int, iy: int) -> float:
    """Small deterministic value-noise hash. Stable across chunks and runs."""
    n = (ix * 374761393 + iy * 668265263) & 0xFFFFFFFF
    n = (n ^ (n >> 13)) * 1274126177
    n = (n ^ (n >> 16)) & 0xFFFFFFFF
    return n / 0xFFFFFFFF


def _value_noise(x: float, y: float, scale: float) -> float:
    """Continuous 2D value noise in [-1, 1] without external dependencies."""
    sx = x / scale
    sy = y / scale
    ix = math.floor(sx)
    iy = math.floor(sy)
    fx = sx - ix
    fy = sy - iy
    ux = fx * fx * (3.0 - 2.0 * fx)
    uy = fy * fy * (3.0 - 2.0 * fy)

    a = _hash01(ix, iy)
    b = _hash01(ix + 1, iy)
    c = _hash01(ix, iy + 1)
    d = _hash01(ix + 1, iy + 1)
    ab = a + (b - a) * ux
    cd = c + (d - c) * ux
    return (ab + (cd - ab) * uy) * 2.0 - 1.0


def _direction_weights(x: float, y: float) -> tuple[float, float, float, float]:
    """Return smooth cardinal-region weights: north, south, east, west."""
    distance = max(1.0, math.hypot(x, y))
    nx = x / distance
    ny = y / distance
    sharpness = 1.85
    north = max(0.0, ny) ** sharpness
    south = max(0.0, -ny) ** sharpness
    east = max(0.0, nx) ** sharpness
    west = max(0.0, -nx) ** sharpness
    total = north + south + east + west
    if total <= 0.0001:
        return 0.0, 0.0, 0.0, 0.0
    return north / total, south / total, east / total, west / total


def _north_mountain_profile(x: float, y: float, distance: float) -> float:
    rise = smoothstep(600.0, 2200.0, distance)
    broad_range = math.sin(x * 0.0046 + _value_noise(x, y, 620.0) * 0.70) * 0.5 + 0.5
    ridge_a = abs(math.sin(x * 0.0085 + y * 0.0018))
    ridge_b = abs(math.sin(x * 0.0055 - y * 0.0026))
    folded = ridge_a * 0.38 + ridge_b * 0.28 + broad_range * 0.46
    rolling_floor = _value_noise(x + 180.0, y - 420.0, 420.0) * 2.8
    return folded * 24.0 * rise + rolling_floor - 3.0


def _west_valley_crater_profile(x: float, y: float, distance: float) -> float:
    maturity = smoothstep(560.0, 1750.0, distance)
    valley = -abs(math.sin(y * 0.0075 + _value_noise(x, y, 520.0) * 1.35)) * 13.0
    ridge = abs(math.sin((x - y) * 0.0068)) * 5.8
    cell = 320.0
    lx = ((x + 0.5 * cell) % cell) - 0.5 * cell
    ly = ((y + 0.5 * cell) % cell) - 0.5 * cell
    r = math.hypot(lx, ly)
    crater = -smoothstep(165.0, 38.0, r) * 13.0
    rim = smoothstep(105.0, 165.0, r) * (1.0 - smoothstep(165.0, 220.0, r)) * 5.3
    noise = _value_noise(x - 230.0, y + 140.0, 240.0) * 3.0
    return (valley + ridge + crater + rim) * (0.30 + 0.70 * maturity) + noise


def _east_rugged_profile(x: float, y: float, distance: float) -> float:
    maturity = smoothstep(520.0, 1650.0, distance)
    swells = math.sin(x * 0.0075 + y * 0.0038) * 4.0
    swells += math.cos(y * 0.0088 - x * 0.0032) * 3.2
    low_ridges = abs(math.sin((x + y * 0.35) * 0.0115)) * 6.2
    noise = _value_noise(x + 610.0, y + 90.0, 200.0) * 3.8
    return (swells + low_ridges + noise) * (0.38 + 0.62 * maturity) - 2.4


def _south_canyon_profile(x: float, y: float, distance: float) -> float:
    maturity = smoothstep(600.0, 2050.0, distance)
    channel_wave = math.sin(x * 0.0078 + math.sin(y * 0.0035) * 1.35 + _value_noise(x, y, 720.0) * 0.75)
    channel = 1.0 - smoothstep(0.08, 0.38, abs(channel_wave))
    secondary_wave = math.sin((x * 0.0048) - (y * 0.0070))
    side_channel = 1.0 - smoothstep(0.06, 0.31, abs(secondary_wave))
    canyon = -(channel * 18.0 + side_channel * 8.5) * maturity
    rim = smoothstep(0.30, 0.50, abs(channel_wave)) * (1.0 - smoothstep(0.50, 0.76, abs(channel_wave))) * 5.6 * maturity
    plateau_noise = _value_noise(x - 90.0, y - 680.0, 360.0) * 3.0
    return canyon + rim + plateau_noise - 1.5 * maturity


def _distant_band_profile(x: float, y: float, distance: float, band: int) -> float:
    if band <= 0:
        return 0.0
    band = int(band)
    maturity = smoothstep(FLAT_WORLD_RADIUS + 760.0, FLAT_WORLD_RADIUS + BIOME_DISTANCE_STRIDE * 1.35, distance)
    amp = 4.0 + min(18.0, band * 3.0)
    offset_x = band * 311.0
    offset_y = band * -197.0
    pattern = band % 6

    if pattern == 1:
        terrace = math.sin((x + offset_x) * 0.0062) + math.cos((y + offset_y) * 0.0054)
        shelf = math.floor((terrace + 2.0) * 2.2) / 2.2 - 0.90
        noise = _value_noise(x + offset_x, y + offset_y, 520.0) * 2.4
        return (shelf * amp + noise) * maturity
    if pattern == 2:
        wave = math.sin((x - y) * 0.0048 + _value_noise(x + offset_x, y, 760.0))
        basin = -smoothstep(0.14, 0.78, abs(wave)) * amp * 0.95
        rim = smoothstep(0.44, 0.78, abs(wave)) * (1.0 - smoothstep(0.78, 0.96, abs(wave))) * amp * 0.36
        return (basin + rim + _value_noise(x, y + offset_y, 360.0) * 2.8) * maturity
    if pattern == 3:
        folds = abs(math.sin((x + offset_x) * 0.0042 + (y + offset_y) * 0.0028))
        cross = math.sin((y - offset_y) * 0.0060) * 0.35
        return ((folds + cross) * amp * 0.72 - amp * 0.22) * maturity
    if pattern == 4:
        spike_a = max(0.0, math.sin((x + offset_x) * 0.0105) * math.cos((y + offset_y) * 0.0090))
        spike_b = max(0.0, _value_noise(x + offset_x, y + offset_y, 220.0))
        return (spike_a * amp * 0.78 + spike_b * amp * 0.32 - 3.0) * maturity
    if pattern == 5:
        plate = _value_noise(x + offset_x, y + offset_y, 680.0)
        edge = smoothstep(-0.10, 0.42, plate) - smoothstep(0.58, 0.90, plate)
        return (edge * amp * 0.72 + _value_noise(x - offset_y, y + offset_x, 280.0) * 2.6) * maturity

    dunes = math.sin((x + offset_x) * 0.0055 + math.sin((y + offset_y) * 0.0022))
    dunes += math.cos((y - offset_y) * 0.0046) * 0.65
    return dunes * amp * 0.42 * maturity


def _distant_formation_profile(x: float, y: float, distance: float) -> float:
    exploration = max(0.0, distance - FLAT_WORLD_RADIUS)
    if exploration <= 0.0:
        return 0.0
    band_float = exploration / max(1.0, BIOME_DISTANCE_STRIDE)
    band = int(math.floor(band_float))
    local = exploration - band * BIOME_DISTANCE_STRIDE
    blend = smoothstep(BIOME_DISTANCE_STRIDE - BIOME_BLEND_WIDTH, BIOME_DISTANCE_STRIDE, local)
    current = _distant_band_profile(x, y, distance, band)
    upcoming = _distant_band_profile(x, y, distance, band + 1)
    return current * (1.0 - blend) + upcoming * blend


def sonar_height_at(x: float, y: float) -> float:
    """Return seam-safe directional terrain height for the dimension floor."""
    distance = math.hypot(x, y)
    fade = smoothstep(FLAT_WORLD_RADIUS, FLAT_WORLD_RADIUS + SONAR_TRANSITION_WIDTH, distance)
    if fade <= 0.0:
        return 0.0

    north, south, east, west = _direction_weights(x, y)
    base_scan = (
        math.sin(x * 0.010 + y * 0.0048) * 2.2
        + math.cos(y * 0.009 - x * 0.0038) * 1.8
        + _value_noise(x, y, 320.0) * 2.8
    )
    distant_depth = -6.0 * smoothstep(FLAT_WORLD_RADIUS, 1250.0, distance)
    directional = (
        north * _north_mountain_profile(x, y, distance)
        + west * _west_valley_crater_profile(x, y, distance)
        + east * _east_rugged_profile(x, y, distance)
        + south * _south_canyon_profile(x, y, distance)
    )
    height = base_scan + directional + distant_depth + _distant_formation_profile(x, y, distance)
    height = max(-44.0, min(42.0, height))
    return height * fade


def sonar_color_boost_at(x: float, y: float) -> float:
    """Subtle intensity hint for higher/lower scanned terrain."""
    h = sonar_height_at(x, y)
    return max(0.0, min(1.0, (h + SONAR_HEIGHT_SCALE * 0.55) / (SONAR_HEIGHT_SCALE * 1.65)))
