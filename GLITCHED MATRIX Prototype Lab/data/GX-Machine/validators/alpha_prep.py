from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from validators.image_debug_utils import (
    bbox_from_mask,
    border_touch_ratio,
    connected_components,
    downscale_mask,
    infer_subject_mask,
    load_rgba,
    overlay_mask,
    resize_for_panel,
    save_json,
    write_text_block,
)


def _checkerboard(size: tuple[int, int], tile: int = 16) -> Image.Image:
    w, h = size
    base = Image.new('RGBA', size, (28, 30, 34, 255))
    draw = ImageDraw.Draw(base)
    color = (48, 52, 58, 255)
    for y in range(0, h, tile):
        for x in range(0, w, tile):
            if ((x // tile) + (y // tile)) % 2 == 0:
                draw.rectangle((x, y, min(w, x + tile), min(h, y + tile)), fill=color)
    return base


def _feathered_alpha(mask: np.ndarray, radius: float = 1.4) -> Image.Image:
    alpha = Image.fromarray((mask.astype(np.uint8) * 255), mode='L')
    softened = alpha.filter(ImageFilter.GaussianBlur(radius=radius))
    return softened


def prepare_alpha(image_path: Path) -> tuple[dict[str, Any], Image.Image, Image.Image, np.ndarray]:
    image, rgba = load_rgba(image_path)
    mask, mask_source, mask_meta = infer_subject_mask(rgba)
    bbox = bbox_from_mask(mask)
    occupancy = float(mask.mean())
    components = connected_components(downscale_mask(mask, 160))
    touch_ratio = border_touch_ratio(mask)
    alpha = _feathered_alpha(mask)

    isolated = image.convert('RGBA').copy()
    isolated.putalpha(alpha)
    checker = _checkerboard(isolated.size)
    preview = Image.alpha_composite(checker, isolated)

    alpha_np = np.asarray(alpha, dtype=np.uint8)
    semi_soft_ratio = float(np.mean((alpha_np > 15) & (alpha_np < 240)))
    fragmented = len(components) > 1 and (components[1] / max(1, components[0])) > 0.12
    score = float(np.clip(1.0 - (touch_ratio * 0.6) - (0.25 if fragmented else 0.0) + min(0.18, semi_soft_ratio), 0.0, 1.0))

    result = {
        'validator': 'alpha_prep',
        'image_path': str(image_path),
        'status': {
            'ok': bool(np.any(mask)),
            'method': 'heuristic_matte',
            'quality_label': 'strong' if score >= 0.72 else 'medium' if score >= 0.45 else 'weak',
        },
        'metrics': {
            'mask_source': mask_source,
            'mask_source_details': mask_meta,
            'occupancy': round(occupancy, 4),
            'border_touch_ratio': round(touch_ratio, 4),
            'soft_edge_ratio': round(semi_soft_ratio, 4),
            'component_count': len(components),
            'largest_component_share': round((components[0] / max(1, sum(components))) if components else 0.0, 4),
            'quality_score': round(score, 4),
            'bbox': None if bbox is None else {
                'x0': bbox[0], 'y0': bbox[1], 'x1': bbox[2], 'y1': bbox[3],
            },
        },
        'guidance': [
            'Use the cutout preview to check for missing horns, limbs, props, or edge chatter before image-to-3D generation.',
            'If the border-touch ratio is high, crop or isolate the source more tightly before running a heavy backend.',
        ],
        'unknowns': [
            'This pass does not invoke a learned background remover.',
        ],
    }
    return result, isolated, preview, mask


def build_debug_panel(image_path: Path, output_path: Path, cutout_output: Path | None = None) -> dict[str, Any]:
    result, isolated, preview, mask = prepare_alpha(image_path)
    image = Image.open(image_path).convert('RGBA')
    overlay = overlay_mask(image, mask, color=(255, 120, 90), alpha=96)

    bbox = bbox_from_mask(mask)
    zoom = image.copy()
    if bbox is not None:
        x0, y0, x1, y1 = bbox
        pad_x = max(8, int((x1 - x0) * 0.12))
        pad_y = max(8, int((y1 - y0) * 0.12))
        crop = preview.crop((max(0, x0 - pad_x), max(0, y0 - pad_y), min(image.width, x1 + pad_x), min(image.height, y1 + pad_y)))
        zoom = crop

    panels = [
        ('reference', image),
        ('mask overlay', overlay),
        ('cutout on checker', preview),
        ('edge zoom', zoom),
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
    draw.text((info_x + 18, margin + 14), 'alpha-prep readout', fill=(235, 235, 235))
    lines = [
        f"quality: {result['status']['quality_label']} ({result['metrics']['quality_score']:.2f})",
        f"occupancy: {result['metrics']['occupancy']:.2%}",
        f"border touch: {result['metrics']['border_touch_ratio']:.2%}",
        f"soft-edge ratio: {result['metrics']['soft_edge_ratio']:.2%}",
        f"components: {result['metrics']['component_count']}",
        '',
        'what to inspect:',
        '- missing thin details at the edge zoom',
        '- clipped props or silhouette chunks in the mask overlay',
        '- floating fragments from background clutter',
        '',
        'correction use:',
        '- fix the matte before pushing the image into depth or 3D generation',
        '- confirm the isolated preview still reads as the intended object',
    ]
    write_text_block(draw, lines, info_x + 18, margin + 48, width=info_w - 36)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path)
    if cutout_output is not None:
        cutout_output.parent.mkdir(parents=True, exist_ok=True)
        isolated.save(cutout_output)
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description='Prepare a heuristic alpha matte and visual cutout panel for image-to-3D input cleanup.')
    ap.add_argument('--image', required=True)
    ap.add_argument('--output', required=True)
    ap.add_argument('--debug-image', help='Optional PNG path for the visual debug panel.')
    ap.add_argument('--cutout-output', help='Optional RGBA PNG path for the isolated cutout.')
    args = ap.parse_args()

    result, isolated, _, _ = prepare_alpha(Path(args.image))
    save_json(result, Path(args.output))
    if args.cutout_output:
        Path(args.cutout_output).parent.mkdir(parents=True, exist_ok=True)
        isolated.save(args.cutout_output)
    if args.debug_image:
        build_debug_panel(Path(args.image), Path(args.debug_image), Path(args.cutout_output) if args.cutout_output else None)
    return 0 if result['status']['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
