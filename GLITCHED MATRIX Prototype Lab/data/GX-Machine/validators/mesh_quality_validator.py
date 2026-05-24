from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
from PIL import Image, ImageDraw
import trimesh

from validators.image_debug_utils import resize_for_panel, save_json, write_text_block


PANEL_BG = (14, 16, 20, 255)
CARD_BG = (20, 24, 30, 255)
CARD_OUTLINE = (54, 78, 92)
TEXT = (235, 235, 235)


def _load_mesh(mesh_path: Path) -> tuple[trimesh.Trimesh, dict[str, Any]]:
    loaded = trimesh.load(mesh_path, force='scene')
    if isinstance(loaded, trimesh.Scene):
        geometries = [g for g in loaded.geometry.values() if isinstance(g, trimesh.Trimesh)]
        if not geometries:
            raise ValueError(f'No mesh geometry found in {mesh_path}')
        merged = trimesh.util.concatenate(geometries)
        meta = {'source_type': 'scene', 'geometry_count': len(geometries)}
        return merged, meta
    if isinstance(loaded, trimesh.Trimesh):
        return loaded, {'source_type': 'mesh', 'geometry_count': 1}
    raise ValueError(f'Unsupported mesh type for {mesh_path}')


def _triangle_area_2d(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> float:
    return abs(float((a[0] * (b[1] - c[1])) + (b[0] * (c[1] - a[1])) + (c[0] * (a[1] - b[1])))) * 0.5


def _project_points(vertices: np.ndarray, axes: tuple[int, int], size: int = 320, padding: float = 0.10) -> tuple[np.ndarray, float, np.ndarray]:
    pts = vertices[:, axes]
    mins = pts.min(axis=0)
    maxs = pts.max(axis=0)
    span = np.maximum(maxs - mins, 1.0e-6)
    inner = size * (1.0 - padding * 2.0)
    scale = float(inner / max(span[0], span[1]))
    out = (pts - mins) * scale
    out[:, 0] += size * padding
    out[:, 1] += size * padding
    out[:, 1] = size - out[:, 1]
    return out.astype(np.float32), scale, mins


def _draw_projection(mesh: trimesh.Trimesh, axes: tuple[int, int], label: str, size: int = 320) -> Image.Image:
    canvas = Image.new('RGBA', (size, size), CARD_BG)
    draw = ImageDraw.Draw(canvas)
    verts_2d, _, _ = _project_points(mesh.vertices, axes=axes, size=size)
    faces = np.asarray(mesh.faces)
    if faces.size:
        for face in faces:
            pts = [tuple(map(float, verts_2d[idx])) for idx in face[:3]]
            draw.polygon(pts, outline=(120, 210, 255), fill=(40, 76, 94, 72))
    draw.text((12, 10), label, fill=TEXT)
    return canvas


def _uv_analysis(mesh: trimesh.Trimesh, size: int = 320) -> tuple[dict[str, Any], Image.Image | None]:
    visual = getattr(mesh, 'visual', None)
    uv = getattr(visual, 'uv', None) if visual is not None else None
    if uv is None or len(uv) == 0:
        return {
            'present': False,
            'outside_01_ratio': None,
            'atlas_fill_ratio': None,
            'overlap_ratio': None,
        }, None

    uv = np.asarray(uv, dtype=np.float32)
    outside = np.any((uv < 0.0) | (uv > 1.0), axis=1)
    outside_ratio = float(np.mean(outside))
    image = Image.new('L', (size, size), 0)
    overlap = np.zeros((size, size), dtype=np.uint16)
    draw = ImageDraw.Draw(image)

    faces = np.asarray(mesh.faces)
    if faces.size:
        for face in faces:
            pts = uv[face[:3]].copy()
            pts[:, 1] = 1.0 - pts[:, 1]
            pts[:, 0] *= (size - 1)
            pts[:, 1] *= (size - 1)
            polygon = [tuple(map(float, p)) for p in pts]
            draw.polygon(polygon, fill=255, outline=255)
            tri_mask = Image.new('L', (size, size), 0)
            tri_draw = ImageDraw.Draw(tri_mask)
            tri_draw.polygon(polygon, fill=1, outline=1)
            overlap += np.asarray(tri_mask, dtype=np.uint16)

    filled = np.asarray(image, dtype=np.uint8) > 0
    atlas_fill = float(np.mean(filled))
    overlap_ratio = float(np.mean(overlap > 1))

    uv_canvas = Image.new('RGBA', (size, size), CARD_BG)
    uv_draw = ImageDraw.Draw(uv_canvas)
    uv_draw.rectangle((8, 8, size - 8, size - 8), outline=(96, 96, 96), width=1)
    heat = np.zeros((size, size, 4), dtype=np.uint8)
    heat[..., 1] = np.where(filled, 170, 0).astype(np.uint8)
    heat[..., 2] = np.where(filled, 255, 0).astype(np.uint8)
    heat[..., 3] = np.where(filled, 180, 0).astype(np.uint8)
    heat[overlap > 1] = np.array([255, 110, 80, 255], dtype=np.uint8)
    uv_canvas.alpha_composite(Image.fromarray(heat, mode='RGBA'))
    uv_draw.text((12, 10), 'uv layout', fill=TEXT)
    return {
        'present': True,
        'outside_01_ratio': round(outside_ratio, 4),
        'atlas_fill_ratio': round(atlas_fill, 4),
        'overlap_ratio': round(overlap_ratio, 4),
    }, uv_canvas


def _face_metrics(mesh: trimesh.Trimesh) -> dict[str, Any]:
    vertices = np.asarray(mesh.vertices, dtype=np.float32)
    faces = np.asarray(mesh.faces)
    if faces.size == 0:
        return {
            'degenerate_ratio': 1.0,
            'bad_aspect_ratio': 1.0,
        }

    tri = vertices[faces]
    e0 = np.linalg.norm(tri[:, 1] - tri[:, 0], axis=1)
    e1 = np.linalg.norm(tri[:, 2] - tri[:, 1], axis=1)
    e2 = np.linalg.norm(tri[:, 0] - tri[:, 2], axis=1)
    longest = np.maximum.reduce([e0, e1, e2])
    shortest = np.maximum(np.minimum.reduce([e0, e1, e2]), 1.0e-6)
    aspect = longest / shortest
    areas = trimesh.triangles.area(tri)
    degenerate_ratio = float(np.mean(areas < 1.0e-8))
    bad_aspect = float(np.mean(aspect > 12.0))
    return {
        'degenerate_ratio': round(degenerate_ratio, 4),
        'bad_aspect_ratio': round(bad_aspect, 4),
    }


def analyze_mesh(mesh_path: Path) -> tuple[dict[str, Any], dict[str, Image.Image | None]]:
    mesh, load_meta = _load_mesh(mesh_path)
    if mesh.is_empty:
        raise ValueError(f'Mesh is empty: {mesh_path}')

    mesh = mesh.copy()
    if mesh.vertices.shape[0] > 0:
        mesh.remove_unreferenced_vertices()

    bounds = mesh.bounds
    extents = mesh.extents.astype(float)
    face_metrics = _face_metrics(mesh)
    uv_metrics, uv_image = _uv_analysis(mesh)
    duplicate_ratio = float(1.0 - (len(np.unique(np.round(mesh.vertices, 6), axis=0)) / max(1, len(mesh.vertices))))
    score = 1.0
    score -= min(0.25, face_metrics['degenerate_ratio'] * 2.5)
    score -= min(0.20, face_metrics['bad_aspect_ratio'] * 0.8)
    score -= min(0.18, duplicate_ratio * 0.7)
    if uv_metrics['present']:
        score -= min(0.12, float(uv_metrics['overlap_ratio'] or 0.0) * 1.4)
        score -= min(0.08, float(uv_metrics['outside_01_ratio'] or 0.0) * 0.8)
    else:
        score -= 0.12
    quality = float(np.clip(score, 0.0, 1.0))

    result = {
        'validator': 'mesh_quality_validator',
        'mesh_path': str(mesh_path),
        'status': {
            'ok': mesh.faces.shape[0] > 0 and face_metrics['degenerate_ratio'] < 0.25,
            'quality_label': 'strong' if quality >= 0.75 else 'medium' if quality >= 0.45 else 'weak',
        },
        'metrics': {
            **load_meta,
            'vertex_count': int(mesh.vertices.shape[0]),
            'face_count': int(mesh.faces.shape[0]),
            'watertight': bool(mesh.is_watertight),
            'euler_number': int(mesh.euler_number),
            'surface_area': round(float(mesh.area), 4),
            'volume': round(float(mesh.volume), 4) if mesh.is_volume else None,
            'bounds_min': [round(float(v), 4) for v in bounds[0]],
            'bounds_max': [round(float(v), 4) for v in bounds[1]],
            'extents': [round(float(v), 4) for v in extents],
            'duplicate_vertex_ratio': round(duplicate_ratio, 4),
            'quality_score': round(quality, 4),
            **face_metrics,
            'uv': uv_metrics,
        },
        'guidance': [
            'Use the orthographic panels to catch stretched silhouettes, missing depth, and uneven proportions before export.',
            'Use the UV panel to catch overlap and wasted atlas space before texture baking or material work.',
        ],
        'unknowns': [
            'This pass does not inspect animation rigs, skin weights, or material shader correctness.',
        ],
    }

    images = {
        'front': _draw_projection(mesh, axes=(0, 1), label='front'),
        'side': _draw_projection(mesh, axes=(2, 1), label='side'),
        'top': _draw_projection(mesh, axes=(0, 2), label='top'),
        'uv': uv_image,
    }
    return result, images


def build_debug_panel(mesh_path: Path, output_path: Path) -> dict[str, Any]:
    result, images = analyze_mesh(mesh_path)
    panel_w, panel_h = 350, 300
    info_w = 420
    margin = 24
    canvas_w = (panel_w * 2) + info_w + (margin * 4)
    canvas_h = (panel_h * 2) + (margin * 3)
    canvas = Image.new('RGBA', (canvas_w, canvas_h), PANEL_BG)
    draw = ImageDraw.Draw(canvas)

    tiles = [
        ('front projection', images['front']),
        ('side projection', images['side']),
        ('top projection', images['top']),
        ('uv layout' if images['uv'] is not None else 'uv layout missing', images['uv'] or Image.new('RGBA', (320, 320), CARD_BG)),
    ]

    for idx, (label, img) in enumerate(tiles):
        col = idx % 2
        row = idx // 2
        x = margin + (col * (panel_w + margin))
        y = margin + (row * (panel_h + margin))
        draw.rounded_rectangle((x, y, x + panel_w, y + panel_h), radius=16, outline=CARD_OUTLINE, width=2, fill=CARD_BG)
        draw.text((x + 16, y + 12), label, fill=TEXT)
        fitted = resize_for_panel(img, panel_w - 24, panel_h - 48)
        px = x + ((panel_w - fitted.width) // 2)
        py = y + 38 + ((panel_h - 56 - fitted.height) // 2)
        canvas.alpha_composite(fitted.convert('RGBA'), (px, py))

    info_x = (panel_w * 2) + (margin * 3)
    draw.rounded_rectangle((info_x, margin, canvas_w - margin, canvas_h - margin), radius=16, outline=(78, 92, 112), width=2, fill=(18, 22, 28))
    draw.text((info_x + 18, margin + 14), 'mesh-quality readout', fill=TEXT)
    uv = result['metrics']['uv']
    lines = [
        f"quality: {result['status']['quality_label']} ({result['metrics']['quality_score']:.2f})",
        f"vertices: {result['metrics']['vertex_count']}",
        f"faces: {result['metrics']['face_count']}",
        f"watertight: {result['metrics']['watertight']}",
        f"degenerate ratio: {result['metrics']['degenerate_ratio']:.2%}",
        f"bad aspect ratio: {result['metrics']['bad_aspect_ratio']:.2%}",
        f"duplicate vertices: {result['metrics']['duplicate_vertex_ratio']:.2%}",
        f"uv present: {uv['present']}",
    ]
    if uv['present']:
        lines.extend([
            f"uv overlap: {float(uv['overlap_ratio'] or 0.0):.2%}",
            f"uv outside 0-1: {float(uv['outside_01_ratio'] or 0.0):.2%}",
            f"uv atlas fill: {float(uv['atlas_fill_ratio'] or 0.0):.2%}",
        ])
    lines.extend([
        '',
        'visual correction use:',
        '- compare front / side / top balance before export',
        '- catch thin or collapsed depth in the side projection',
        '- catch wasted or overlapping UV regions before texturing',
    ])
    write_text_block(draw, lines, info_x + 18, margin + 48, width=info_w - 36)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path)
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description='Validate basic mesh quality and emit a visual debug panel for geometry/UV review.')
    ap.add_argument('--mesh', required=True)
    ap.add_argument('--output', required=True)
    ap.add_argument('--debug-image', help='Optional PNG path for the visual debug panel.')
    args = ap.parse_args()

    result, _ = analyze_mesh(Path(args.mesh))
    save_json(result, Path(args.output))
    if args.debug_image:
        build_debug_panel(Path(args.mesh), Path(args.debug_image))
    return 0 if result['status']['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
