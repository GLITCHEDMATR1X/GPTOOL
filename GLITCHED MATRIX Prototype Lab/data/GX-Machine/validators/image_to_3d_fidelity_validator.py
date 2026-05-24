from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
from PIL import Image, ImageDraw

from validators.image_debug_utils import (
    bbox_from_mask,
    fit_mask_to_canvas,
    gradient_map,
    grayscale,
    infer_subject_mask,
    load_rgba,
    mask_boundary,
    mask_centroid,
    overlay_mask,
    resize_for_panel,
    save_json,
    write_text_block,
)


CANVAS_SIZE = 320


def clamp_score(value: float) -> float:
    return round(max(1.0, min(10.0, value)), 2)


def compare(reference_path: Path, candidate_path: Path) -> dict[str, Any]:
    ref_img, ref_rgba = load_rgba(reference_path)
    cand_img, cand_rgba = load_rgba(candidate_path)
    ref_mask, ref_source, ref_meta = infer_subject_mask(ref_rgba)
    cand_mask, cand_source, cand_meta = infer_subject_mask(cand_rgba)

    if not ref_mask.any() or not cand_mask.any():
        return {
            'validator': 'image_to_3d_fidelity_validator',
            'reference_image': str(reference_path),
            'candidate_image': str(candidate_path),
            'status': {'ok': False, 'reason': 'Reference or candidate silhouette could not be isolated.'},
            'issues': ['One of the images did not yield a usable subject mask.'],
            'suggestions': ['Use cleaner renders or supply alpha-backed exports for the candidate view.'],
        }

    ref_canvas = fit_mask_to_canvas(ref_mask, canvas_size=CANVAS_SIZE)
    cand_canvas = fit_mask_to_canvas(cand_mask, canvas_size=CANVAS_SIZE)
    overlap = ref_canvas & cand_canvas
    union = ref_canvas | cand_canvas
    ref_only = ref_canvas & (~cand_canvas)
    cand_only = cand_canvas & (~ref_canvas)

    iou = float(overlap.sum() / max(1, union.sum()))
    missing_ratio = float(ref_only.sum() / max(1, ref_canvas.sum()))
    extra_ratio = float(cand_only.sum() / max(1, cand_canvas.sum()))

    ref_bbox = bbox_from_mask(ref_mask)
    cand_bbox = bbox_from_mask(cand_mask)
    ref_centroid = mask_centroid(ref_mask)
    cand_centroid = mask_centroid(cand_mask)
    centroid_drift = 0.0
    if ref_centroid and cand_centroid:
        centroid_drift = float(((ref_centroid[0] - cand_centroid[0]) ** 2 + (ref_centroid[1] - cand_centroid[1]) ** 2) ** 0.5)

    bbox_scale_error = 0.0
    aspect_error = 0.0
    if ref_bbox and cand_bbox:
        rx0, ry0, rx1, ry1 = ref_bbox
        cx0, cy0, cx1, cy1 = cand_bbox
        ref_w, ref_h = max(1, rx1 - rx0), max(1, ry1 - ry0)
        cand_w, cand_h = max(1, cx1 - cx0), max(1, cy1 - cy0)
        bbox_scale_error = abs((cand_w * cand_h) - (ref_w * ref_h)) / max(1.0, float(ref_w * ref_h))
        aspect_error = abs((cand_w / cand_h) - (ref_w / ref_h))

    ref_boundary = mask_boundary(ref_canvas)
    cand_boundary = mask_boundary(cand_canvas)
    boundary_union = ref_boundary | cand_boundary
    edge_match = float((ref_boundary & cand_boundary).sum() / max(1, boundary_union.sum()))

    ref_grad = gradient_map(grayscale(ref_rgba[..., :3]))
    cand_grad = gradient_map(grayscale(cand_rgba[..., :3]))
    texture_energy_delta = float(abs(ref_grad.mean() - cand_grad.mean()))

    penalties = 0.0
    issues: list[str] = []
    suggestions: list[str] = []

    if iou < 0.72:
        penalties += 1.8 + ((0.72 - iou) * 8.0)
        issues.append(f'Silhouette overlap is weak at {iou:.2f}; the generated form is drifting away from the reference shape.')
        suggestions.append('Correct the generation or mesh edit pass using the overlap panel to target missing and extra areas.')
    if missing_ratio > 0.16:
        penalties += 1.0 + (missing_ratio * 4.0)
        issues.append(f'The candidate is missing {missing_ratio:.2f} of the normalized reference silhouette.')
        suggestions.append('Restore the missing mass first; red regions in the diff panel are reference areas not matched by the candidate.')
    if extra_ratio > 0.16:
        penalties += 1.0 + (extra_ratio * 4.0)
        issues.append(f'The candidate introduces {extra_ratio:.2f} extra silhouette area not supported by the reference.')
        suggestions.append('Trim the extra blue regions or adjust the camera-facing silhouette before export.')
    if centroid_drift > 0.08:
        penalties += 0.7 + ((centroid_drift - 0.08) * 8.0)
        issues.append(f'Centroid drift is {centroid_drift:.2f}; the candidate is not aligned to the reference framing.')
        suggestions.append('Recenter the mesh or render using the same framing used for the source reference.')
    if bbox_scale_error > 0.20:
        penalties += 0.7 + ((bbox_scale_error - 0.20) * 3.0)
        issues.append(f'BBox scale error is {bbox_scale_error:.2f}; the candidate subject mass is too large or too small.')
        suggestions.append('Adjust subject scale before judging finer detail fidelity.')
    if aspect_error > 0.18:
        penalties += 0.8 + ((aspect_error - 0.18) * 2.5)
        issues.append(f'Aspect ratio error is {aspect_error:.2f}; width/height proportions have drifted.')
        suggestions.append('Correct the broad proportion blockout before polishing textures or materials.')
    if edge_match < 0.46:
        penalties += 0.7 + ((0.46 - edge_match) * 4.0)
        issues.append(f'Contour agreement is weak at {edge_match:.2f}; edge flow does not follow the reference cleanly.')
        suggestions.append('Use the normalized contour panel to match the main contour before surface cleanup.')

    if not suggestions:
        suggestions.append('Silhouette fidelity is in a healthy range for a game-ready refinement pass.')

    overall = clamp_score(9.7 - penalties)

    return {
        'validator': 'image_to_3d_fidelity_validator',
        'reference_image': str(reference_path),
        'candidate_image': str(candidate_path),
        'status': {
            'ok': overall >= 7.0 and iou >= 0.72,
            'reason': 'Candidate tracks the reference silhouette well enough for refinement.' if overall >= 7.0 and iou >= 0.72 else 'Candidate needs silhouette correction before sign-off.',
        },
        'metrics': {
            'mask_sources': {
                'reference': {'source': ref_source, 'details': ref_meta},
                'candidate': {'source': cand_source, 'details': cand_meta},
            },
            'silhouette_iou': round(iou, 4),
            'missing_ratio': round(missing_ratio, 4),
            'extra_ratio': round(extra_ratio, 4),
            'centroid_drift': round(centroid_drift, 4),
            'bbox_scale_error': round(bbox_scale_error, 4),
            'aspect_ratio_error': round(aspect_error, 4),
            'contour_match': round(edge_match, 4),
            'texture_energy_delta': round(texture_energy_delta, 4),
        },
        'scores': {
            'overall': overall,
            'silhouette_match': clamp_score(1.0 + (iou * 9.0) - (missing_ratio * 2.0) - (extra_ratio * 2.0)),
            'proportion_match': clamp_score(10.0 - (bbox_scale_error * 7.0) - (aspect_error * 8.0)),
            'contour_match': clamp_score(1.0 + (edge_match * 9.0)),
        },
        'issues': issues,
        'suggestions': suggestions,
        'normalized_masks': {
            'reference_canvas_size': CANVAS_SIZE,
            'candidate_canvas_size': CANVAS_SIZE,
        },
    }


def build_debug_panel(reference_path: Path, candidate_path: Path, result: dict[str, Any], debug_path: Path) -> None:
    ref_img, ref_rgba = load_rgba(reference_path)
    cand_img, cand_rgba = load_rgba(candidate_path)
    ref_mask, _, _ = infer_subject_mask(ref_rgba)
    cand_mask, _, _ = infer_subject_mask(cand_rgba)
    ref_boxed = resize_for_panel(overlay_mask(ref_img, ref_mask, color=(0, 220, 255), alpha=96), 440, 440)
    cand_boxed = resize_for_panel(overlay_mask(cand_img, cand_mask, color=(255, 185, 0), alpha=96), 440, 440)

    ref_canvas = fit_mask_to_canvas(ref_mask, canvas_size=CANVAS_SIZE)
    cand_canvas = fit_mask_to_canvas(cand_mask, canvas_size=CANVAS_SIZE)
    overlap = ref_canvas & cand_canvas
    ref_only = ref_canvas & (~cand_canvas)
    cand_only = cand_canvas & (~ref_canvas)
    diff = np.zeros((CANVAS_SIZE, CANVAS_SIZE, 3), dtype=np.uint8)
    diff[overlap] = (52, 220, 110)
    diff[ref_only] = (230, 80, 80)
    diff[cand_only] = (80, 140, 255)
    diff_img = Image.fromarray(diff, mode='RGB').resize((440, 440), Image.Resampling.NEAREST)

    ref_boundary = Image.fromarray((mask_boundary(ref_canvas).astype(np.uint8) * 255), mode='L').resize((440, 440), Image.Resampling.NEAREST).convert('RGB')
    cand_boundary = Image.fromarray((mask_boundary(cand_canvas).astype(np.uint8) * 255), mode='L').resize((440, 440), Image.Resampling.NEAREST).convert('RGB')
    contour = Image.blend(ref_boundary, cand_boundary, 0.5)

    panel = Image.new('RGB', (1320, 980), (18, 20, 24))
    panel.paste(ref_boxed.convert('RGB'), (20, 20))
    panel.paste(cand_boxed.convert('RGB'), (460, 20))
    panel.paste(diff_img, (20, 470))
    panel.paste(contour, (460, 470))

    draw = ImageDraw.Draw(panel)
    draw.rectangle((900, 20, 1298, 958), fill=(26, 28, 34), outline=(70, 74, 82), width=2)
    labels = [
        (20, 20, 'Reference input'),
        (460, 20, 'Candidate render'),
        (20, 470, 'Normalized silhouette diff'),
        (460, 470, 'Normalized contour panel'),
    ]
    for x, y, text in labels:
        draw.rectangle((x, y, x + 200, y + 28), fill=(12, 14, 18))
        draw.text((x + 10, y + 6), text, fill=(240, 240, 240))

    lines = [
        'Image-to-3D Fidelity Review',
        '',
        f"Status: {'PASS' if result['status']['ok'] else 'FIX BEFORE APPROVAL'}",
        f"Overall: {result['scores']['overall']:.2f}/10",
        f"Silhouette match: {result['scores']['silhouette_match']:.2f}/10",
        f"Proportion match: {result['scores']['proportion_match']:.2f}/10",
        f"Contour match: {result['scores']['contour_match']:.2f}/10",
        '',
        f"Silhouette IoU: {result['metrics']['silhouette_iou']:.3f}",
        f"Missing ratio: {result['metrics']['missing_ratio']:.3f}",
        f"Extra ratio: {result['metrics']['extra_ratio']:.3f}",
        f"Centroid drift: {result['metrics']['centroid_drift']:.3f}",
        f"BBox scale error: {result['metrics']['bbox_scale_error']:.3f}",
        f"Aspect error: {result['metrics']['aspect_ratio_error']:.3f}",
        f"Contour match: {result['metrics']['contour_match']:.3f}",
        '',
        'Panel key:',
        'Green = shared silhouette',
        'Red = missing from candidate',
        'Blue = extra candidate mass',
        '',
        'Issues:',
    ]
    lines.extend(result['issues'][:4] or ['None'])
    lines.extend(['', 'Suggested fixes:'])
    lines.extend(result['suggestions'][:4])
    write_text_block(draw, lines, 920, 42, 350, line_height=20)
    debug_path.parent.mkdir(parents=True, exist_ok=True)
    panel.save(debug_path)


def main() -> int:
    ap = argparse.ArgumentParser(description='Compare a candidate image-to-3D render against its source reference.')
    ap.add_argument('--reference', required=True)
    ap.add_argument('--candidate', required=True)
    ap.add_argument('--output', required=True)
    ap.add_argument('--debug-image', help='Optional annotated diff panel PNG.')
    args = ap.parse_args()
    result = compare(Path(args.reference), Path(args.candidate))
    save_json(result, Path(args.output))
    if args.debug_image:
        build_debug_panel(Path(args.reference), Path(args.candidate), result, Path(args.debug_image))
    return 0 if result['status']['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
