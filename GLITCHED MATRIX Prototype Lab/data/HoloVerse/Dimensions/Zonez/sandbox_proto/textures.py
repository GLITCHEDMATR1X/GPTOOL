from __future__ import annotations

from pathlib import Path

from panda3d.core import Filename, PNMImage, SamplerState, Texture

from .constants import ATLAS_COLUMNS, ATLAS_ROWS, ATLAS_TILE_SIZE


TILE_NAMES = {
    0: 'grass_top',
    1: 'dirt',
    2: 'stone',
    3: 'sand',
    4: 'brick',
    5: 'wood_side',
    6: 'wood_top',
    7: 'glass',
    8: 'leaves',
    9: 'planks',
    10: 'grass_side',
    11: 'outline',
}

BLOCK_FACE_TILES = {
    1: {'top': 0, 'bottom': 1, 'side': 10},
    2: {'top': 1, 'bottom': 1, 'side': 1},
    3: {'top': 2, 'bottom': 2, 'side': 2},
    4: {'top': 3, 'bottom': 3, 'side': 3},
    5: {'top': 4, 'bottom': 4, 'side': 4},
    6: {'top': 6, 'bottom': 6, 'side': 5},
    7: {'top': 7, 'bottom': 7, 'side': 7},
    8: {'top': 8, 'bottom': 8, 'side': 8},
    9: {'top': 9, 'bottom': 9, 'side': 9},
}

TILE_COLORS = {
    0: (0.36, 0.72, 0.28, 1.0),
    1: (0.47, 0.31, 0.18, 1.0),
    2: (0.56, 0.58, 0.62, 1.0),
    3: (0.85, 0.79, 0.57, 1.0),
    4: (0.67, 0.28, 0.25, 1.0),
    5: (0.49, 0.33, 0.18, 1.0),
    6: (0.57, 0.39, 0.22, 1.0),
    7: (0.74, 0.90, 0.98, 0.42),
    8: (0.22, 0.51, 0.21, 1.0),
    9: (0.74, 0.60, 0.35, 1.0),
    10: (0.30, 0.62, 0.24, 1.0),
    11: (1.0, 1.0, 1.0, 1.0),
}

HELL_TILE_COLORS = {
    0: (0.62, 0.20, 0.10, 1.0),
    1: (0.38, 0.14, 0.09, 1.0),
    2: (0.28, 0.14, 0.10, 1.0),
    3: (0.92, 0.12, 0.10, 1.0),
    4: (0.72, 0.22, 0.12, 1.0),
    5: (0.19, 0.11, 0.08, 1.0),
    6: (0.26, 0.16, 0.10, 1.0),
    7: (0.95, 0.22, 0.10, 0.42),
    8: (0.14, 0.12, 0.12, 1.0),
    9: (0.40, 0.14, 0.09, 1.0),
    10: (0.46, 0.16, 0.10, 1.0),
    11: (1.0, 1.0, 1.0, 1.0),
}


CANDY_TILE_COLORS = {
    0: (0.26, 0.90, 0.86, 1.0),
    1: (0.84, 0.63, 0.76, 1.0),
    2: (0.80, 0.74, 0.90, 1.0),
    3: (0.98, 0.72, 0.82, 1.0),
    4: (0.96, 0.42, 0.72, 1.0),
    5: (0.98, 0.90, 0.96, 1.0),
    6: (0.98, 0.82, 0.90, 1.0),
    7: (0.70, 0.98, 0.92, 0.42),
    8: (0.98, 0.92, 0.97, 1.0),
    9: (1.0, 0.74, 0.34, 1.0),
    10: (0.34, 0.86, 0.82, 1.0),
    11: (1.0, 1.0, 1.0, 1.0),
}


POLAR_TILE_COLORS = {
    0: (0.96, 0.98, 1.0, 1.0),
    1: (0.86, 0.92, 0.98, 1.0),
    2: (0.70, 0.78, 0.88, 1.0),
    3: (0.80, 0.89, 0.98, 1.0),
    4: (0.78, 0.16, 0.18, 1.0),
    5: (0.46, 0.30, 0.18, 1.0),
    6: (0.58, 0.40, 0.26, 1.0),
    7: (0.96, 0.99, 1.0, 0.58),
    8: (0.12, 0.34, 0.18, 1.0),
    9: (0.94, 0.96, 0.98, 1.0),
    10: (0.84, 0.90, 0.97, 1.0),
    11: (1.0, 1.0, 1.0, 1.0),
}


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _set_px(img: PNMImage, x: int, y: int, rgba: tuple[float, float, float, float]) -> None:
    r, g, b, a = rgba
    img.setXelA(x, y, _clamp01(r), _clamp01(g), _clamp01(b), _clamp01(a))


def _to_grayscale(rgba: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    r, g, b, a = rgba
    gray = r * 0.299 + g * 0.587 + b * 0.114
    return gray, gray, gray, a


def _variant_rgba(tile_index: int, variant: str) -> tuple[float, float, float, float]:
    rgba = TILE_COLORS[tile_index]
    if variant == 'grayscale':
        return _to_grayscale(rgba)
    if variant == 'hell':
        return HELL_TILE_COLORS.get(tile_index, rgba)
    if variant == 'candy':
        return CANDY_TILE_COLORS.get(tile_index, rgba)
    if variant == 'polar':
        return POLAR_TILE_COLORS.get(tile_index, rgba)
    return rgba


def _tile_origin(tile_index: int) -> tuple[int, int]:
    tx = tile_index % ATLAS_COLUMNS
    ty = tile_index // ATLAS_COLUMNS
    return tx * ATLAS_TILE_SIZE, ty * ATLAS_TILE_SIZE


def _fill_tile(img: PNMImage, tile_index: int, rgba: tuple[float, float, float, float]) -> None:
    ox, oy = _tile_origin(tile_index)
    for y in range(ATLAS_TILE_SIZE):
        for x in range(ATLAS_TILE_SIZE):
            _set_px(img, ox + x, oy + y, rgba)
    for x in range(ATLAS_TILE_SIZE):
        _set_px(img, ox + x, oy, rgba)
        _set_px(img, ox + x, oy + ATLAS_TILE_SIZE - 1, rgba)
    for y in range(ATLAS_TILE_SIZE):
        _set_px(img, ox, oy + y, rgba)
        _set_px(img, ox + ATLAS_TILE_SIZE - 1, oy + y, rgba)


def build_texture_atlas(output_path: Path | None = None, variant: str = 'default') -> Texture:
    width = ATLAS_COLUMNS * ATLAS_TILE_SIZE
    height = ATLAS_ROWS * ATLAS_TILE_SIZE
    img = PNMImage(width, height, 4)
    img.fill(0.12, 0.12, 0.12)
    img.alphaFill(1.0)

    for tile_index in TILE_COLORS:
        tile_rgba = _variant_rgba(tile_index, variant)
        _fill_tile(img, tile_index, tile_rgba)

    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        img.write(Filename.fromOsSpecific(str(output_path)))

    tex = Texture(f'block_atlas_{variant}')
    tex.load(img)
    tex.setMinfilter(SamplerState.FT_linear_mipmap_linear)
    tex.setMagfilter(SamplerState.FT_linear)
    tex.setAnisotropicDegree(4)
    try:
        tex.generateRamMipmapImages()
    except Exception:
        pass
    tex.setWrapU(SamplerState.WM_clamp)
    tex.setWrapV(SamplerState.WM_clamp)
    return tex


def get_face_tile(block_id: int, axis: int, normal_sign: int) -> int:
    face = 'side'
    if axis == 2:
        face = 'top' if normal_sign > 0 else 'bottom'
    return BLOCK_FACE_TILES[block_id][face]


def get_tile_uv(tile_index: int, inset_px: float = 1.75) -> tuple[float, float, float, float]:
    tx = tile_index % ATLAS_COLUMNS
    ty = tile_index // ATLAS_COLUMNS
    atlas_w = ATLAS_COLUMNS * ATLAS_TILE_SIZE
    atlas_h = ATLAS_ROWS * ATLAS_TILE_SIZE

    px0 = tx * ATLAS_TILE_SIZE + inset_px
    px1 = (tx + 1) * ATLAS_TILE_SIZE - inset_px
    py0 = ty * ATLAS_TILE_SIZE + inset_px
    py1 = (ty + 1) * ATLAS_TILE_SIZE - inset_px

    u0 = px0 / atlas_w
    u1 = px1 / atlas_w
    v0 = 1.0 - (py1 / atlas_h)
    v1 = 1.0 - (py0 / atlas_h)
    return u0, v0, u1, v1
