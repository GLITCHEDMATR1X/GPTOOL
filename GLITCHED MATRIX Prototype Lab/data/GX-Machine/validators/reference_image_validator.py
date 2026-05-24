from __future__ import annotations

import argparse
import sys
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
from PIL import Image, ImageDraw

from validators.image_debug_utils import (
    bbox_from_mask,
    border_touch_ratio,
    connected_components,
    downscale_mask,
    gradient_map,
    grayscale,
    infer_subject_mask,
    load_rgba,
    mask_boundary,
    mask_centroid,
    normalized_bbox,
    overlay_mask,
    resize_for_panel,
    save_json,
    write_text_block,
)


TARGET_OCCUPANCY_MIN = 0.18
TARGET_OCCUPANCY_MAX = 0.72
TARGET_MARGIN_MIN = 0.05
TARGET_CENTER_OFFSET_MAX = 0.18
TARGET_BACKGROUND_COMPLEXITY_MAX = 0.48
TARGET_BLUR_MIN = 0.045


def clamp_score(value: float) -> float:
    return round(max(1.0, min(10.0, value)), 2)


def analyze_reference(image_path: Path) -> dict[str, Any]:
    image, rgba = load_rgba(image_path)
    rgb = rgba[..., :3]
    gray = grayscale(rgb)
    grad = gradient_map(gray)
    mask, mask_source, mask_meta = infer_subject_mask(rgba)
    bbox = bbox_from_mask(mask)
    centroid = mask_centroid(mask)
    occupancy = float(mask.mean())
    components = connected_components(downscale_mask(mask, 160))
    bbox_norm = normalized_bbox(mask)
    border_ratio = border_touch_ratio(mask)

    if bbox is None:
        metrics = {
            'occupancy': round(occupancy, 4),
            'mask_source': mask_source,
            'mask_source_details': mask_meta,
        }
        return {
            'validator': 'reference_image_validator',
            'image_path': str(image_path),
            'status': {'ok': False, 'reason': 'No subject mask could be isolated.'},
            'metrics': metrics,
            'issues': ['No subject region was detected. Use a cleaner source image or supply transparency.'],
            'suggestions': ['Provide an image with a simpler background or alpha cutout.'],
        }

    h, w = mask.shape
    x0, y0, x1, y1 = bbox
    margins = {
        'left': round(x0 / w, 4),
        'right': round((w - x1) / w, 4),
        'top': round(y0 / h, 4),
        'bottom': round((h - y1) / h, 4),
    }
    min_margin = min(margins.values())
    center_offset = 0.0 if centroid is None else float(((centroid[0] - 0.5) ** 2 + (centroid[1] - 0.5) ** 2) ** 0.5)
    blur_score = float(grad.std())
    outside = gray[~mask]
    background_complexity = float(grad[~mask].mean()) if outside.size else 0.0
    boundary = mask_boundary(mask)
    silhouette_complexity = float(boundary.sum() / max(1.0, np.sqrt(mask.sum())))
    small_components = [size for size in components[1:] if size >= max(8, int(components[0] * 0.03))] if components else []

    penalties = 0.0
    issues: list[str] = []
    suggestions: list[str] = []

    if occupancy < TARGET_OCCUPANCY_MIN:
        penalties += 1.3 + ((TARGET_OCCUPANCY_MIN - occupancy) * 6.0)
        issues.append(f'Subject occupancy is low at {occupancy:.2f}; the object reads too small for dependable reconstruction.')
        suggestions.append('Crop closer or use a tighter reference so the object fills more of the frame.')
    elif occupancy > TARGET_OCCUPANCY_MAX:
        penalties += 1.0 + ((occupancy - TARGET_OCCUPANCY_MAX) * 6.0)
        issues.append(f'Subject occupancy is high at {occupancy:.2f}; important contour detail is likely clipped.')
        suggestions.append('Add more breathing room around the object before generation.')

    if min_margin < TARGET_MARGIN_MIN:
        penalties += 1.2 + ((TARGET_MARGIN_MIN - min_margin) * 7.0)
        issues.append(f'Minimum crop margin is {min_margin:.2f}; the silhouette is touching the frame too aggressively.')
        suggestions.append('Reframe the object so all edges have visible clearance from the canvas border.')

    if center_offset > TARGET_CENTER_OFFSET_MAX:
        penalties += 0.8 + ((center_offset - TARGET_CENTER_OFFSET_MAX) * 4.0)
        issues.append(f'Subject centroid drift is {center_offset:.2f}; off-center framing will bias downstream alignment.')
        suggestions.append('Center the object more deliberately before running image-to-3D.')

    if background_complexity > TARGET_BACKGROUND_COMPLEXITY_MAX:
        penalties += 0.8 + ((background_complexity - TARGET_BACKGROUND_COMPLEXITY_MAX) * 4.0)
        issues.append(f'Background complexity is high at {background_complexity:.2f}; background edges may contaminate shape extraction.')
        suggestions.append('Remove or simplify the background, or use an alpha cutout if available.')

    if blur_score < TARGET_BLUR_MIN:
        penalties += 1.0 + ((TARGET_BLUR_MIN - blur_score) * 10.0)
        issues.append(f'Edge sharpness is weak at {blur_score:.3f}; the reference lacks crisp contour information.')
        suggestions.append('Use a sharper reference image with clearer edge definition.')

    if border_ratio > 0.02:
        penalties += 0.7 + (border_ratio * 6.0)
        issues.append(f'The subject touches the image border at a ratio of {border_ratio:.2f}.')
        suggestions.append('Avoid cut-off limbs or silhouettes touching the frame boundary.')

    if len(small_components) >= 2:
        penalties += 0.8 + (len(small_components) * 0.2)
        issues.append(f'The isolated subject mask splits into {1 + len(small_components)} meaningful regions, which suggests occlusion or clutter.')
        suggestions.append('Use a single unobstructed subject view with fewer overlapping pieces.')

    if not suggestions:
        suggestions.append('Reference framing is in a healthy range for a first-pass image-to-3D attempt.')

    overall = clamp_score(9.7 - penalties)
    status_ok = overall >= 7.0 and len(issues) <= 2

    return {
        'validator': 'reference_image_validator',
        'image_path': str(image_path),
        'status': {
            'ok': status_ok,
            'reason': 'Reference image is suitable for image-to-3D.' if status_ok else 'Reference image needs cleanup before generation.',
        },
        'metrics': {
            'image_size': {'width': int(w), 'height': int(h)},
            'mask_source': mask_source,
            'mask_source_details': mask_meta,
            'subject_occupancy': round(occupancy, 4),
            'bbox_normalized': bbox_norm,
            'margins_normalized': margins,
            'centroid_normalized': None if centroid is None else {'x': round(centroid[0], 4), 'y': round(centroid[1], 4)},
            'center_offset': round(center_offset, 4),
            'blur_sharpness': round(blur_score, 4),
            'background_complexity': round(background_complexity, 4),
            'silhouette_complexity': round(silhouette_complexity, 4),
            'border_touch_ratio': round(border_ratio, 4),
            'component_sizes_downscaled': components[:6],
        },
        'scores': {
            'overall': overall,
            'crop_framing': clamp_score(10.0 - max(0.0, (TARGET_MARGIN_MIN - min_margin) * 25.0) - (center_offset * 8.0)),
            'subject_isolation': clamp_score(10.0 - max(0.0, (background_complexity - TARGET_BACKGROUND_COMPLEXITY_MAX) * 9.0) - (len(small_components) * 0.7)),
            'edge_definition': clamp_score(10.0 - max(0.0, (TARGET_BLUR_MIN - blur_score) * 90.0)),
        },
        'issues': issues,
        'suggestions': suggestions,
    }


def build_debug_panel(image_path: Path, result: dict[str, Any], debug_path: Path) -> None:
    image, rgba = load_rgba(image_path)
    mask, _, _ = infer_subject_mask(rgba)
    boxed = overlay_mask(image, mask, color=(0, 220, 255), alpha=96)
    draw = ImageDraw.Draw(boxed)
    bbox = bbox_from_mask(mask)
    if bbox:
        draw.rectangle(bbox, outline=(255, 96, 96), width=4)
    w, h = boxed.size
    draw.line((w // 2, 0, w // 2, h), fill=(255, 255, 255, 110), width=1)
    draw.line((0, h // 2, w, h // 2), fill=(255, 255, 255, 110), width=1)

    left = resize_for_panel(boxed, 980, 980)
    panel_w = left.width + 420
    panel_h = max(left.height, 640)
    panel = Image.new('RGBA', (panel_w, panel_h), (18, 20, 24, 255))
    panel.paste(left, (20, 20))

    side = ImageDraw.Draw(panel)
    side.rectangle((left.width + 40, 20, panel_w - 20, panel_h - 20), fill=(26, 28, 34), outline=(70, 74, 82), width=2)
    lines = [
        'Reference Image Readiness',
        '',
        f"Status: {'PASS' if result['status']['ok'] else 'FIX BEFORE GENERATION'}",
        f"Overall: {result['scores']['overall']:.2f}/10",
        f"Crop framing: {result['scores']['crop_framing']:.2f}/10",
        f"Isolation: {result['scores']['subject_isolation']:.2f}/10",
        f"Edge definition: {result['scores']['edge_definition']:.2f}/10",
        '',
        f"Occupancy: {result['metrics']['subject_occupancy']:.3f}",
        f"Center offset: {result['metrics']['center_offset']:.3f}",
        f"Blur sharpness: {result['metrics']['blur_sharpness']:.3f}",
        f"Background complexity: {result['metrics']['background_complexity']:.3f}",
        f"Border touch ratio: {result['metrics']['border_touch_ratio']:.3f}",
        '',
        'Issues:',
    ]
    lines.extend(result['issues'][:4] or ['None'])
    lines.extend(['', 'Suggested fixes:'])
    lines.extend(result['suggestions'][:4])
    write_text_block(side, lines, left.width + 56, 42, 320, line_height=20)
    debug_path.parent.mkdir(parents=True, exist_ok=True)
    panel.convert('RGB').save(debug_path)


def main() -> int:
    ap = argparse.ArgumentParser(description='Validate whether a reference image is suitable for image-to-3D generation.')
    ap.add_argument('--image', required=True)
    ap.add_argument('--output', required=True)
    ap.add_argument('--debug-image', help='Optional annotated PNG for visual correction.')
    args = ap.parse_args()
    result = analyze_reference(Path(args.image))
    save_json(result, Path(args.output))
    if args.debug_image:
        build_debug_panel(Path(args.image), result, Path(args.debug_image))
    return 0 if result['status']['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
