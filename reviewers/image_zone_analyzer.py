from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
from typing import Dict, Any, List, Tuple

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
from PIL import Image
from reviewers.layout_expectations import get_layout_profile


def load_image(path: Path) -> np.ndarray:
    return np.asarray(Image.open(path).convert('RGB'), dtype=np.float32) / 255.0


def grayscale(arr: np.ndarray) -> np.ndarray:
    return (0.2126 * arr[..., 0]) + (0.7152 * arr[..., 1]) + (0.0722 * arr[..., 2])


def crop_norm(arr: np.ndarray, rect: Tuple[float, float, float, float]) -> np.ndarray:
    h, w = arr.shape[:2]
    x0, y0, x1, y1 = rect
    xs0, ys0 = max(0, int(round(x0 * w))), max(0, int(round(y0 * h)))
    xs1, ys1 = min(w, int(round(x1 * w))), min(h, int(round(y1 * h)))
    return arr[ys0:ys1, xs0:xs1]


def edge_density(gray: np.ndarray) -> float:
    gx = np.abs(np.diff(gray, axis=1, prepend=gray[:, :1]))
    gy = np.abs(np.diff(gray, axis=0, prepend=gray[:1, :]))
    return float(np.mean((gx + gy) > 0.12))


def normalized_entropy(gray: np.ndarray) -> float:
    hist, _ = np.histogram(gray, bins=32, range=(0.0, 1.0), density=False)
    total = float(hist.sum())
    if total <= 0.0:
        return 0.0
    hist = hist.astype(np.float64) / total
    hist = hist[hist > 1e-12]
    if hist.size == 0:
        return 0.0
    ent = -np.sum(hist * np.log2(hist))
    return float(ent / np.log2(32))


def luminance_stats(gray: np.ndarray) -> Dict[str, float]:
    return {
        'mean': float(gray.mean()),
        'std': float(gray.std()),
        'min': float(gray.min()),
        'max': float(gray.max()),
    }


def saliency_grid(gray: np.ndarray, cells: int = 3) -> List[Dict[str, Any]]:
    h, w = gray.shape
    ch, cw = max(1, h // cells), max(1, w // cells)
    results = []
    for r in range(cells):
        for c in range(cells):
            y0, y1 = r * ch, h if r == cells - 1 else (r + 1) * ch
            x0, x1 = c * cw, w if c == cells - 1 else (c + 1) * cw
            region = gray[y0:y1, x0:x1]
            score = (region.std() * 1.8) + (edge_density(region) * 1.2) + abs(region.mean() - gray.mean())
            results.append({
                'row': r, 'col': c, 'score': round(float(score), 4),
                'mean': round(float(region.mean()), 4), 'std': round(float(region.std()), 4)
            })
    return sorted(results, key=lambda item: item['score'], reverse=True)


def analyze(image_path: Path, layout_profile: str = 'gameplay') -> Dict[str, Any]:
    arr = load_image(image_path)
    gray = grayscale(arr)
    profile = get_layout_profile(layout_profile)
    zones = profile['zones']
    target = profile['target']
    zone_results = []
    allowed_busy = 0.0
    disallowed_busy = 0.0

    for zone in zones:
        region = crop_norm(arr, (zone['x0'], zone['y0'], zone['x1'], zone['y1']))
        region_gray = grayscale(region)
        edge = edge_density(region_gray)
        lum = luminance_stats(region_gray)
        entropy = normalized_entropy(region_gray)
        busy = (edge * 0.85) + (lum['std'] * 0.45) + (entropy * 0.45)
        if zone['ui_allowed']:
            allowed_busy += busy * zone['weight']
        else:
            disallowed_busy += busy * zone['weight']
        zone_results.append({
            'name': zone['name'],
            'purpose': zone['purpose'],
            'ui_allowed': zone['ui_allowed'],
            'weight': zone['weight'],
            'edge_density': round(edge, 4),
            'entropy': round(entropy, 4),
            'luminance': {k: round(v, 4) for k, v in lum.items()},
            'occupancy_score': round(busy, 4),
        })

    full = luminance_stats(gray)
    bands = max(1, min(gray.shape[0], gray.shape[1]) // 10)
    top = gray[:bands, :]
    bottom = gray[-bands:, :]
    left = gray[:, :bands]
    right = gray[:, -bands:]
    edges = np.concatenate([top.ravel(), bottom.ravel(), left.ravel(), right.ravel()])
    corners = np.concatenate([
        gray[:bands, :bands].ravel(),
        gray[:bands, -bands:].ravel(),
        gray[-bands:, :bands].ravel(),
        gray[-bands:, -bands:].ravel(),
    ])
    edge_pressure = float((edge_density(top) + edge_density(bottom) + edge_density(left) + edge_density(right)) / 4.0)
    corner_pressure = float((
        edge_density(gray[:bands, :bands]) +
        edge_density(gray[:bands, -bands:]) +
        edge_density(gray[-bands:, :bands]) +
        edge_density(gray[-bands:, -bands:])
    ) / 4.0)
    total_busy = max(1e-6, allowed_busy + disallowed_busy)
    center_busy = disallowed_busy / total_busy
    center_clearance = float(max(0.0, min(1.0, 1.0 - center_busy)))
    grid = saliency_grid(gray, cells=3)
    focal = grid[0]

    return {
        'image_path': str(image_path),
        'layout_profile': profile['name'],
        'image_size': {'width': int(arr.shape[1]), 'height': int(arr.shape[0])},
        'global_luminance': {k: round(v, 4) for k, v in full.items()},
        'edge_pressure': round(edge_pressure, 4),
        'corner_pressure': round(corner_pressure, 4),
        'edge_mean': round(float(edges.mean()), 4),
        'edge_std': round(float(edges.std()), 4),
        'corner_mean': round(float(corners.mean()), 4),
        'corner_std': round(float(corners.std()), 4),
        'center_clearance': round(center_clearance, 4),
        'center_busy_weighted': round(disallowed_busy, 4),
        'allowed_busy_weighted': round(allowed_busy, 4),
        'focal_grid': grid,
        'focal_cell': {'row': focal['row'], 'col': focal['col'], 'centered': focal['row'] == 1 and focal['col'] == 1},
        'target': target,
        'zones': zone_results,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description='Analyze a screenshot by layout zones and frame pressure metrics.')
    ap.add_argument('--image', required=True)
    ap.add_argument('--layout-profile', default='gameplay')
    ap.add_argument('--output', required=True)
    args = ap.parse_args()
    result = analyze(Path(args.image), args.layout_profile)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2), encoding='utf-8')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
