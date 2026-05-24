from __future__ import annotations

import math
from collections import deque
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageFont


RGB_DTYPE = np.float32
MASK_THRESHOLD_ALPHA = 16


def load_rgba(path: Path) -> tuple[Image.Image, np.ndarray]:
    image = Image.open(path).convert("RGBA")
    rgba = np.asarray(image, dtype=RGB_DTYPE) / 255.0
    return image, rgba


def grayscale(rgb: np.ndarray) -> np.ndarray:
    return (0.2126 * rgb[..., 0]) + (0.7152 * rgb[..., 1]) + (0.0722 * rgb[..., 2])


def gradient_map(gray: np.ndarray) -> np.ndarray:
    gx = np.abs(np.diff(gray, axis=1, prepend=gray[:, :1]))
    gy = np.abs(np.diff(gray, axis=0, prepend=gray[:1, :]))
    return gx + gy


def compute_border_color(rgb: np.ndarray) -> np.ndarray:
    h, w = rgb.shape[:2]
    band = max(1, min(h, w) // 24)
    border = np.concatenate([
        rgb[:band, :, :].reshape(-1, 3),
        rgb[-band:, :, :].reshape(-1, 3),
        rgb[:, :band, :].reshape(-1, 3),
        rgb[:, -band:, :].reshape(-1, 3),
    ], axis=0)
    return np.median(border, axis=0)


def infer_subject_mask(rgba: np.ndarray) -> tuple[np.ndarray, str, dict[str, Any]]:
    alpha = rgba[..., 3]
    rgb = rgba[..., :3]
    alpha_nontrivial = float(np.mean(alpha < 0.98)) > 0.005 and float(alpha.max() - alpha.min()) > 0.08
    if alpha_nontrivial:
        mask = alpha > (MASK_THRESHOLD_ALPHA / 255.0)
        return mask, 'alpha', {'alpha_nontrivial': True}

    bg_color = compute_border_color(rgb)
    dist = np.sqrt(np.sum((rgb - bg_color) ** 2, axis=-1)) / math.sqrt(3.0)
    h, w = dist.shape
    band = max(1, min(h, w) // 24)
    border_dist = np.concatenate([
        dist[:band, :].ravel(),
        dist[-band:, :].ravel(),
        dist[:, :band].ravel(),
        dist[:, -band:].ravel(),
    ])
    threshold = max(0.11, float(np.percentile(border_dist, 95) + 0.06))
    mask = dist > threshold

    occupancy = float(mask.mean())
    if occupancy < 0.01 or occupancy > 0.90:
        fallback_threshold = max(0.10, float(dist.mean() + (0.55 * dist.std())))
        mask = dist > fallback_threshold
        threshold = fallback_threshold

    return mask, 'background_distance', {
        'alpha_nontrivial': False,
        'background_color': [round(float(v), 4) for v in bg_color],
        'distance_threshold': round(float(threshold), 4),
    }


def bbox_from_mask(mask: np.ndarray) -> tuple[int, int, int, int] | None:
    ys, xs = np.where(mask)
    if xs.size == 0 or ys.size == 0:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def normalized_bbox(mask: np.ndarray) -> dict[str, float] | None:
    bbox = bbox_from_mask(mask)
    if bbox is None:
        return None
    x0, y0, x1, y1 = bbox
    h, w = mask.shape
    return {
        'x0': round(x0 / w, 4),
        'y0': round(y0 / h, 4),
        'x1': round(x1 / w, 4),
        'y1': round(y1 / h, 4),
        'width': round((x1 - x0) / w, 4),
        'height': round((y1 - y0) / h, 4),
    }


def mask_centroid(mask: np.ndarray) -> tuple[float, float] | None:
    ys, xs = np.where(mask)
    if xs.size == 0 or ys.size == 0:
        return None
    h, w = mask.shape
    return float(xs.mean() / w), float(ys.mean() / h)


def border_touch_ratio(mask: np.ndarray) -> float:
    if mask.size == 0:
        return 0.0
    border = np.concatenate([
        mask[0, :].astype(np.float32),
        mask[-1, :].astype(np.float32),
        mask[:, 0].astype(np.float32),
        mask[:, -1].astype(np.float32),
    ])
    return float(border.mean()) if border.size else 0.0


def connected_components(mask: np.ndarray, max_components: int = 12) -> list[int]:
    h, w = mask.shape
    visited = np.zeros((h, w), dtype=bool)
    sizes: list[int] = []
    neighbors = ((1, 0), (-1, 0), (0, 1), (0, -1))
    for y in range(h):
        for x in range(w):
            if not mask[y, x] or visited[y, x]:
                continue
            q = deque([(y, x)])
            visited[y, x] = True
            size = 0
            while q:
                cy, cx = q.popleft()
                size += 1
                for dy, dx in neighbors:
                    ny, nx = cy + dy, cx + dx
                    if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not visited[ny, nx]:
                        visited[ny, nx] = True
                        q.append((ny, nx))
            sizes.append(size)
            if len(sizes) >= max_components and sum(sizes) >= int(mask.sum()):
                break
    return sorted(sizes, reverse=True)


def downscale_mask(mask: np.ndarray, size: int = 192) -> np.ndarray:
    pil = Image.fromarray((mask.astype(np.uint8) * 255), mode='L').resize((size, size), Image.Resampling.NEAREST)
    return np.asarray(pil, dtype=np.uint8) > 127


def mask_boundary(mask: np.ndarray) -> np.ndarray:
    mask = mask.astype(bool)
    neighbors = [
        np.roll(mask, 1, axis=0),
        np.roll(mask, -1, axis=0),
        np.roll(mask, 1, axis=1),
        np.roll(mask, -1, axis=1),
    ]
    interior = mask.copy()
    for n in neighbors:
        interior &= n
    boundary = mask & (~interior)
    boundary[[0, -1], :] = mask[[0, -1], :]
    boundary[:, [0, -1]] = mask[:, [0, -1]]
    return boundary


def fit_mask_to_canvas(mask: np.ndarray, canvas_size: int = 320, padding_ratio: float = 0.08) -> np.ndarray:
    bbox = bbox_from_mask(mask)
    if bbox is None:
        return np.zeros((canvas_size, canvas_size), dtype=bool)
    x0, y0, x1, y1 = bbox
    crop = mask[y0:y1, x0:x1].astype(np.uint8) * 255
    ch, cw = crop.shape
    inner = max(8, int(round(canvas_size * (1.0 - (padding_ratio * 2.0)))))
    scale = min(inner / max(1, cw), inner / max(1, ch))
    nw = max(1, int(round(cw * scale)))
    nh = max(1, int(round(ch * scale)))
    resized = Image.fromarray(crop, mode='L').resize((nw, nh), Image.Resampling.NEAREST)
    canvas = Image.new('L', (canvas_size, canvas_size), 0)
    ox = (canvas_size - nw) // 2
    oy = (canvas_size - nh) // 2
    canvas.paste(resized, (ox, oy))
    return np.asarray(canvas, dtype=np.uint8) > 127


def overlay_mask(image: Image.Image, mask: np.ndarray, color: tuple[int, int, int] = (0, 255, 255), alpha: int = 96) -> Image.Image:
    base = image.convert('RGBA')
    overlay = Image.new('RGBA', base.size, (0, 0, 0, 0))
    mask_img = Image.fromarray((mask.astype(np.uint8) * alpha), mode='L')
    color_layer = Image.new('RGBA', base.size, color + (0,))
    overlay = Image.composite(Image.new('RGBA', base.size, color + (alpha,)), overlay, mask_img)
    return Image.alpha_composite(base, overlay)


def draw_bbox(draw: ImageDraw.ImageDraw, bbox: tuple[int, int, int, int] | None, outline: tuple[int, int, int], width: int = 3) -> None:
    if bbox is None:
        return
    draw.rectangle(bbox, outline=outline, width=width)


def resize_for_panel(image: Image.Image, max_w: int, max_h: int) -> Image.Image:
    image = image.copy()
    image.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)
    return image


def best_font(size: int = 14) -> ImageFont.ImageFont:
    try:
        return ImageFont.truetype('DejaVuSans.ttf', size)
    except Exception:
        return ImageFont.load_default()


def write_text_block(draw: ImageDraw.ImageDraw, lines: list[str], x: int, y: int, width: int, line_height: int = 18) -> None:
    font = best_font(14)
    cursor_y = y
    for line in lines:
        if len(line) <= 70:
            draw.text((x, cursor_y), line, fill=(235, 235, 235), font=font)
            cursor_y += line_height
            continue
        words = line.split()
        current = []
        for word in words:
            trial = ' '.join(current + [word])
            bbox = draw.textbbox((0, 0), trial, font=font)
            if bbox[2] - bbox[0] > width and current:
                draw.text((x, cursor_y), ' '.join(current), fill=(235, 235, 235), font=font)
                cursor_y += line_height
                current = [word]
            else:
                current.append(word)
        if current:
            draw.text((x, cursor_y), ' '.join(current), fill=(235, 235, 235), font=font)
            cursor_y += line_height


def save_json(data: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(__import__('json').dumps(data, indent=2), encoding='utf-8')
