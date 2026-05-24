from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
from PIL import Image, ImageDraw, ImageOps

from validators.image_debug_utils import (
    bbox_from_mask,
    gradient_map,
    grayscale,
    infer_subject_mask,
    load_rgba,
    mask_boundary,
    overlay_mask,
    resize_for_panel,
    save_json,
    write_text_block,
)


def _chamfer_distance(mask: np.ndarray) -> np.ndarray:
    h, w = mask.shape
    inf = 1.0e6
    dist = np.full((h, w), inf, dtype=np.float32)
    boundary = mask_boundary(mask)
    dist[~mask] = 0.0
    dist[boundary] = 0.0

    for y in range(h):
        for x in range(w):
            value = dist[y, x]
            if y > 0:
                value = min(value, dist[y - 1, x] + 1.0)
                if x > 0:
                    value = min(value, dist[y - 1, x - 1] + 1.4142)
                if x + 1 < w:
                    value = min(value, dist[y - 1, x + 1] + 1.4142)
            if x > 0:
                value = min(value, dist[y, x - 1] + 1.0)
            dist[y, x] = value

    for y in range(h - 1, -1, -1):
        for x in range(w - 1, -1, -1):
            value = dist[y, x]
            if y + 1 < h:
                value = min(value, dist[y + 1, x] + 1.0)
                if x > 0:
                    value = min(value, dist[y + 1, x - 1] + 1.4142)
                if x + 1 < w:
                    value = min(value, dist[y + 1, x + 1] + 1.4142)
            if x + 1 < w:
                value = min(value, dist[y, x + 1] + 1.0)
            dist[y, x] = value

    max_value = float(dist[mask].max()) if np.any(mask) else 0.0
    if max_value > 0.0:
        dist[mask] /= max_value
    dist[~mask] = 0.0
    return dist


def _normalize_map(values: np.ndarray, mask: np.ndarray) -> np.ndarray:
    if not np.any(mask):
        return np.zeros_like(values, dtype=np.float32)
    inside = values[mask]
    low = float(np.percentile(inside, 2))
    high = float(np.percentile(inside, 98))
    if high <= low:
        high = low + 1.0e-5
    out = np.clip((values - low) / (high - low), 0.0, 1.0)
    out[~mask] = 0.0
    return out.astype(np.float32)


def _colormap(depth: np.ndarray) -> Image.Image:
    depth_u8 = np.clip(depth * 255.0, 0, 255).astype(np.uint8)
    red = depth_u8
    green = np.clip(255 - np.abs(depth_u8.astype(np.int16) - 128) * 2, 0, 255).astype(np.uint8)
    blue = 255 - depth_u8
    alpha = np.where(depth_u8 > 0, 255, 0).astype(np.uint8)
    rgba = np.stack([red, green, blue, alpha], axis=-1)
    return Image.fromarray(rgba, mode='RGBA')


def _depth_from_reference(image_path: Path) -> tuple[dict[str, Any], np.ndarray, np.ndarray, np.ndarray, Image.Image]:
    image, rgba = load_rgba(image_path)
    rgb = rgba[..., :3]
    gray = grayscale(rgb)
    grad = gradient_map(gray)
    mask, mask_source, mask_meta = infer_subject_mask(rgba)

    border_distance = _chamfer_distance(mask)
    inverse_grad = 1.0 - _normalize_map(grad, mask)
    brightness = _normalize_map(1.0 - gray, mask)

    depth_hint = (0.68 * border_distance) + (0.22 * inverse_grad) + (0.10 * brightness)
    depth_hint = _normalize_map(depth_hint, mask)
    boundary = mask_boundary(mask)

    bbox = bbox_from_mask(mask)
    occupancy = float(mask.mean())
    depth_span = float(depth_hint[mask].max() - depth_hint[mask].min()) if np.any(mask) else 0.0
    edge_focus = float(np.mean(depth_hint[boundary])) if np.any(boundary) else 0.0
    center_focus = float(np.mean(depth_hint[(border_distance > 0.6) & mask])) if np.any((border_distance > 0.6) & mask) else 0.0
    confidence = float(np.clip((depth_span * 0.7) + max(0.0, center_focus - edge_focus) * 0.9 + occupancy * 0.2, 0.0, 1.0))

    metrics = {
        'mask_source': mask_source,
        'mask_source_details': mask_meta,
        'occupancy': round(occupancy, 4),
        'depth_span': round(depth_span, 4),
        'edge_focus': round(edge_focus, 4),
        'center_focus': round(center_focus, 4),
        'confidence': round(confidence, 4),
        'bbox': None if bbox is None else {
            'x0': bbox[0], 'y0': bbox[1], 'x1': bbox[2], 'y1': bbox[3],
        },
        'notes': [
            'This is a heuristic depth hint, not a learned monocular depth prediction.',
            'Use it to spot front-back ambiguity, silhouette imbalance, and cleanup needs before generation.',
        ],
    }
    status = {
        'ok': bool(np.any(mask)),
        'method': 'heuristic_depth_hint',
        'confidence_label': 'strong' if confidence >= 0.7 else 'medium' if confidence >= 0.45 else 'weak',
    }
    result = {
        'validator': 'depth_hint_generator',
        'image_path': str(image_path),
        'status': status,
        'metrics': metrics,
        'guidance': [
            'If the near/far read feels wrong, improve the source image with clearer silhouette lighting or multiple reference angles.',
            'If the mask catches background clutter, run alpha_prep.py and clean the cutout before generation.',
        ],
        'unknowns': [
            'No external depth model was invoked in this pass.',
        ],
    }
    return result, mask, depth_hint, boundary, image


def build_debug_panel(image_path: Path, output_path: Path, depth_output_path: Path | None = None) -> dict[str, Any]:
    result, mask, depth_hint, boundary, image = _depth_from_reference(image_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    mask_overlay = overlay_mask(image, mask, color=(0, 220, 255), alpha=92)
    depth_color = _colormap(depth_hint)
    subject_depth = Image.alpha_composite(Image.new('RGBA', image.size, (16, 16, 18, 255)), depth_color)

    contour_map = np.zeros((*mask.shape, 4), dtype=np.uint8)
    contour_map[..., 3] = np.where(mask, 255, 0).astype(np.uint8)
    contour_map[..., :3] = np.where(depth_hint[..., None] > 0, np.clip(depth_hint[..., None] * np.array([255, 220, 120], dtype=np.float32), 0, 255).astype(np.uint8), 0)
    contour_map[boundary] = np.array([255, 255, 255, 255], dtype=np.uint8)
    contour_image = Image.fromarray(contour_map, mode='RGBA')

    panels = [
        ('reference', image.convert('RGBA')),
        ('mask overlay', mask_overlay),
        ('depth hint', subject_depth),
        ('depth contours', contour_image),
    ]

    panel_w, panel_h = 350, 300
    info_w = 420
    margin = 24
    canvas_w = (panel_w * 2) + info_w + (margin * 4)
    canvas_h = (panel_h * 2) + (margin * 3)
    canvas = Image.new('RGBA', (canvas_w, canvas_h), (14, 16, 20, 255))
    draw = ImageDraw.Draw(canvas)

    for idx, (label, img) in enumerate(panels):
        col = idx % 2
        row = idx // 2
        x = margin + (col * (panel_w + margin))
        y = margin + (row * (panel_h + margin))
        draw.rounded_rectangle((x, y, x + panel_w, y + panel_h), radius=16, outline=(54, 78, 92), width=2, fill=(20, 24, 30))
        draw.text((x + 16, y + 12), label, fill=(235, 235, 235))
        fitted = resize_for_panel(img, panel_w - 24, panel_h - 48)
        px = x + ((panel_w - fitted.width) // 2)
        py = y + 38 + ((panel_h - 56 - fitted.height) // 2)
        canvas.alpha_composite(fitted.convert('RGBA'), (px, py))

    info_x = (panel_w * 2) + (margin * 3)
    draw.rounded_rectangle((info_x, margin, canvas_w - margin, canvas_h - margin), radius=16, outline=(78, 92, 112), width=2, fill=(18, 22, 28))
    draw.text((info_x + 18, margin + 14), 'depth-hint readout', fill=(235, 235, 235))
    lines = [
        f"method: {result['status']['method']}",
        f"confidence: {result['status']['confidence_label']} ({result['metrics']['confidence']:.2f})",
        f"occupancy: {result['metrics']['occupancy']:.2%}",
        f"depth span: {result['metrics']['depth_span']:.3f}",
        f"center focus: {result['metrics']['center_focus']:.3f}",
        f"edge focus: {result['metrics']['edge_focus']:.3f}",
        '',
        'how to read it:',
        '- warmer colors suggest nearer mass',
        '- cool colors suggest farther mass',
        '- white traces show silhouette and internal depth edges',
        '',
        'correction use:',
        '- fix references whose depth collapses into a flat sheet',
        '- spot symmetry or silhouette ambiguities before generation',
        '- verify that bulky volumes sit where the eye expects them',
    ]
    write_text_block(draw, lines, info_x + 18, margin + 48, width=info_w - 36)

    canvas.save(output_path)
    if depth_output_path is not None:
        depth_output_path.parent.mkdir(parents=True, exist_ok=True)
        depth_output = np.clip(depth_hint * 255.0, 0, 255).astype(np.uint8)
        Image.fromarray(depth_output, mode='L').save(depth_output_path)
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description='Generate a heuristic depth hint and visual debug panel for image-to-3D preparation.')
    ap.add_argument('--image', required=True)
    ap.add_argument('--output', required=True)
    ap.add_argument('--debug-image', help='Optional PNG path for the visual debug panel.')
    ap.add_argument('--depth-output', help='Optional grayscale depth-hint PNG path.')
    args = ap.parse_args()

    result, _, _, _, _ = _depth_from_reference(Path(args.image))
    save_json(result, Path(args.output))
    if args.debug_image:
        build_debug_panel(Path(args.image), Path(args.debug_image), Path(args.depth_output) if args.depth_output else None)

    if args.depth_output and not args.debug_image:
        _, mask, depth_hint, _, _ = _depth_from_reference(Path(args.image))
        out = np.clip(depth_hint * 255.0, 0, 255).astype(np.uint8)
        out[~mask] = 0
        Path(args.depth_output).parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(out, mode='L').save(args.depth_output)
    return 0 if result['status']['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
