from __future__ import annotations

import argparse
import colorsys
import json
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

PANEL_BG = (11, 14, 18, 255)
CARD_BG = (20, 24, 31, 255)
CARD_OUTLINE = (68, 82, 102, 255)
TEXT = (236, 241, 248, 255)
MUTED = (165, 176, 190, 255)
ACCENT = (115, 199, 255, 255)
GOOD = (110, 228, 168, 255)


def checkerboard(size: tuple[int, int] = (256, 256), a=(38, 42, 50, 255), b=(58, 63, 74, 255), step: int = 16) -> Image.Image:
    img = Image.new('RGBA', size, a)
    draw = ImageDraw.Draw(img)
    for y in range(0, size[1], step):
        for x in range(0, size[0], step):
            if ((x // step) + (y // step)) % 2:
                draw.rectangle([x, y, x + step - 1, y + step - 1], fill=b)
    return img


def fit_image_to_canvas(image: Image.Image, size: tuple[int, int], bg=(0, 0, 0, 0)) -> Image.Image:
    w, h = size
    base = Image.new('RGBA', size, bg)
    if image.width == 0 or image.height == 0:
        return base
    scale = min(w / image.width, h / image.height)
    nw = max(1, int(image.width * scale))
    nh = max(1, int(image.height * scale))
    resized = image.resize((nw, nh), Image.Resampling.NEAREST)
    x = (w - nw) // 2
    y = (h - nh) // 2
    base.alpha_composite(resized, (x, y))
    return base


def quantize_image(img: Image.Image, colors: int = 16) -> Image.Image:
    colors = max(2, min(256, int(colors)))
    alpha = img.getchannel('A') if img.mode == 'RGBA' else None
    quant = img.convert('RGB').quantize(colors=colors, method=Image.Quantize.MEDIANCUT).convert('RGBA')
    if alpha is not None:
        quant.putalpha(alpha)
    return quant


def extract_palette(img: Image.Image, count: int = 8) -> list[tuple[int, int, int, int]]:
    img = img.convert('RGBA')
    reduced = quantize_image(img, max(count, 2))
    colors = reduced.getcolors(maxcolors=4096) or []
    colors.sort(key=lambda item: item[0], reverse=True)
    palette = [c for _, c in colors[:count]]
    while len(palette) < count:
        palette.append((0, 0, 0, 0))
    return palette


def nearest_palette_color(pixel: tuple[int, int, int, int], palette: list[tuple[int, int, int, int]]) -> tuple[int, int, int, int]:
    pr, pg, pb, pa = (int(pixel[0]), int(pixel[1]), int(pixel[2]), int(pixel[3]))
    best = palette[0]
    best_d = float('inf')
    for color in palette:
        cr, cg, cb, ca = (int(color[0]), int(color[1]), int(color[2]), int(color[3]))
        d = (pr - cr) ** 2 + (pg - cg) ** 2 + (pb - cb) ** 2 + ((pa - ca) ** 2) * 0.25
        if d < best_d:
            best = color
            best_d = d
    return best


def palette_reduce_exact(img: Image.Image, palette: list[tuple[int, int, int, int]]) -> Image.Image:
    img = img.convert('RGBA')
    arr = np.array(img, dtype=np.uint8)
    flat = arr.reshape(-1, 4)
    reduced = np.array([nearest_palette_color(tuple(px), palette) for px in flat], dtype=np.uint8).reshape(arr.shape)
    return Image.fromarray(reduced, 'RGBA')


def outline_from_alpha(img: Image.Image, outline=(22, 26, 32, 255)) -> Image.Image:
    img = img.convert('RGBA')
    alpha = img.getchannel('A')
    grown = alpha.filter(ImageFilter.MaxFilter(3))
    edge = ImageChops.subtract(grown, alpha)
    ol = Image.new('RGBA', img.size, outline)
    ol.putalpha(edge)
    return Image.alpha_composite(ol, img)


def remove_corner_background(img: Image.Image, threshold: int = 28) -> Image.Image:
    img = img.convert('RGBA')
    arr = np.array(img, dtype=np.uint8)
    corners = np.array([arr[0, 0], arr[0, -1], arr[-1, 0], arr[-1, -1]], dtype=np.float32)
    avg = corners.mean(axis=0)
    rgb_dist = np.abs(arr[..., :3].astype(np.float32) - avg[:3]).sum(axis=2)
    out = arr.copy()
    out[..., 3] = np.where(rgb_dist <= threshold, 0, out[..., 3])
    return Image.fromarray(out, 'RGBA')


def make_tileable_rgba(arr: np.ndarray, blend_fraction: float = 0.12) -> np.ndarray:
    arr = arr.astype(np.float32)
    h, w = arr.shape[:2]
    out = arr.copy()
    edge_x = max(1, int(w * blend_fraction))
    edge_y = max(1, int(h * blend_fraction))
    if edge_x > 1:
        t = np.linspace(0.0, 1.0, edge_x, dtype=np.float32)[None, :, None]
        mix = (1.0 - t) * 0.5
        left = arr[:, :edge_x, :]
        right = arr[:, -edge_x:, :]
        out[:, :edge_x, :] = left * (1.0 - mix) + right * mix
        out[:, -edge_x:, :] = right * (1.0 - mix[:, ::-1, :]) + left * mix[:, ::-1, :]
    if edge_y > 1:
        t = np.linspace(0.0, 1.0, edge_y, dtype=np.float32)[:, None, None]
        mix = (1.0 - t) * 0.5
        top = out[:edge_y, :, :]
        bottom = out[-edge_y:, :, :]
        out[:edge_y, :, :] = top * (1.0 - mix) + bottom * mix
        out[-edge_y:, :, :] = bottom * (1.0 - mix[::-1, :, :]) + top * mix[::-1, :, :]
    return np.clip(out, 0, 255).astype(np.uint8)


def make_tileable_image(img: Image.Image, blend_fraction: float = 0.12) -> Image.Image:
    return Image.fromarray(make_tileable_rgba(np.array(img.convert('RGBA'), dtype=np.uint8), blend_fraction=blend_fraction))


def _hex_to_rgba(value: str) -> tuple[int, int, int, int]:
    value = value.lstrip('#')
    if len(value) == 6:
        value += 'ff'
    if len(value) != 8:
        raise ValueError(f'Invalid color: {value}')
    return tuple(int(value[i:i+2], 16) for i in range(0, 8, 2))


def procedural_slots(base_hex: str) -> list[dict[str, Any]]:
    r, g, b, _ = _hex_to_rgba(base_hex)
    h, s, v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
    shifts = [0.16, 0.08, 0.0, -0.07, -0.14, -0.22]
    sizes = [1, 1, 2, 2, 3, 4]
    weights = [100, 90, 76, 64, 52, 40]
    slots: list[dict[str, Any]] = []
    for shift, size, weight in zip(shifts, sizes, weights):
        vv = max(0.0, min(1.0, v + shift))
        rr, gg, bb = colorsys.hsv_to_rgb(h, max(0.06, s), vv)
        slots.append({
            'enabled': True,
            'color': '#%02x%02x%02x' % (int(rr * 255), int(gg * 255), int(bb * 255)),
            'size': size,
            'weight': weight,
        })
    return slots


def build_demo_image() -> Image.Image:
    img = checkerboard((256, 256), (50, 56, 70, 255), (36, 41, 53, 255), 16)
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((36, 48, 220, 210), radius=26, fill=(70, 158, 214, 255))
    draw.ellipse((64, 74, 126, 136), fill=(238, 245, 250, 255))
    draw.ellipse((130, 74, 192, 136), fill=(188, 214, 228, 255))
    draw.rectangle((92, 140, 164, 198), fill=(18, 24, 30, 255))
    draw.polygon([(42, 210), (120, 228), (190, 220), (224, 246), (36, 246)], fill=(121, 98, 170, 255))
    return img


def _palette_hex(palette: list[tuple[int, int, int, int]]) -> list[str]:
    return ['#%02x%02x%02x%02x' % tuple(px) for px in palette]


def render_texture_panel(original: Image.Image, processed: Image.Image, report: dict[str, Any], output_path: Path) -> None:
    width, height = 1460, 900
    img = Image.new('RGBA', (width, height), PANEL_BG)
    draw = ImageDraw.Draw(img)
    draw.text((26, 22), f"Texture Forge — {report['operation']}", fill=TEXT)
    draw.text((26, 50), 'Salvaged 2D texture and palette workflow for bridge-side editing, cleanup, and tileable prep.', fill=MUTED)
    cards = [(24, 94, 708, 510), (728, 94, 1412, 510), (24, 534, 952, 872), (972, 534, 1412, 872)]
    for box in cards:
        draw.rounded_rectangle(box, radius=18, fill=CARD_BG, outline=CARD_OUTLINE, width=2)
    draw.text((42, 110), 'Original / Input', fill=ACCENT)
    draw.text((746, 110), 'Processed / Output', fill=ACCENT)
    draw.text((42, 550), 'Palette / Slots', fill=ACCENT)
    draw.text((990, 550), 'Notes', fill=ACCENT)

    left = fit_image_to_canvas(original, (620, 340))
    right = fit_image_to_canvas(processed, (620, 340))
    img.alpha_composite(left, (56, 146))
    img.alpha_composite(right, (760, 146))

    y = 590
    for idx, hex_color in enumerate(report['palette_hex'][:12]):
        col = idx % 4
        row = idx // 4
        x0 = 48 + col * 210
        yy = y + row * 78
        draw.rounded_rectangle((x0, yy, x0 + 48, yy + 48), radius=8, fill=_hex_to_rgba(hex_color))
        draw.text((x0 + 60, yy + 14), hex_color, fill=TEXT)
    y2 = 550
    note_lines = [
        f"size: {report['processed_size'][0]} x {report['processed_size'][1]}",
        f"palette count: {len(report['palette_hex'])}",
        f"tileable blend: {report['tileable_blend_fraction']:.2f}",
    ] + report['notes']
    for line in note_lines:
        draw.text((990, y2 + 36), line[:42], fill=MUTED if ': ' not in line else TEXT)
        y2 += 32
    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(output_path)


def process_image(image: Image.Image, operation: str, colors: int, tileable_blend_fraction: float, base_color: str) -> tuple[Image.Image, dict[str, Any]]:
    original = image.convert('RGBA')
    palette = extract_palette(original, max(4, colors))
    processed = original
    notes: list[str] = []
    if operation in {'knockout', 'sprite_variation'}:
        processed = remove_corner_background(processed)
        notes.append('Corner-color knockout removed broad flat background regions.')
    if operation in {'quantize', 'tileable', 'sprite_variation'}:
        processed = quantize_image(processed, colors)
        palette = extract_palette(processed, max(4, colors))
        processed = palette_reduce_exact(processed, palette)
        notes.append('Palette reduction locked output to a concise editable color set.')
    if operation in {'tileable', 'sprite_variation'}:
        processed = make_tileable_image(processed, blend_fraction=tileable_blend_fraction)
        notes.append('Edge blending made the texture safer for repeated tiling.')
    if operation == 'sprite_variation':
        processed = outline_from_alpha(processed)
        notes.append('Alpha outline improved readability against mixed backgrounds.')
    slots = procedural_slots(base_color)
    report = {
        'tool': 'texture_forge',
        'operation': operation,
        'processed_size': [processed.width, processed.height],
        'palette_hex': _palette_hex(palette),
        'procedural_slots': slots,
        'tileable_blend_fraction': float(tileable_blend_fraction),
        'notes': notes or ['No destructive edits were applied beyond normalization and preview generation.'],
    }
    return processed, report


def main() -> int:
    ap = argparse.ArgumentParser(description='Bridge-side 2D texture salvage workflow.')
    ap.add_argument('--image', help='Optional input image path.')
    ap.add_argument('--operation', default='tileable', choices=['quantize', 'tileable', 'knockout', 'sprite_variation'])
    ap.add_argument('--colors', type=int, default=8)
    ap.add_argument('--base-color', default='#4cc9f0')
    ap.add_argument('--tileable-blend-fraction', type=float, default=0.12)
    ap.add_argument('--image-output', help='Optional processed image output path.')
    ap.add_argument('--output', help='Optional JSON report path.')
    ap.add_argument('--debug-image', help='Optional debug image output path.')
    ap.add_argument('--json', action='store_true')
    args = ap.parse_args()

    original = Image.open(args.image).convert('RGBA') if args.image else build_demo_image()
    processed, report = process_image(original, args.operation, args.colors, args.tileable_blend_fraction, args.base_color)
    if args.image_output:
        out_img = Path(args.image_output).resolve()
        out_img.parent.mkdir(parents=True, exist_ok=True)
        processed.save(out_img)
        report['image_output'] = str(out_img)
    if args.output:
        out = Path(args.output).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2), encoding='utf-8')
    if args.debug_image:
        render_texture_panel(original, processed, report, Path(args.debug_image).resolve())
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(json.dumps(report, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
