from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

PANEL_BG = (11, 14, 18, 255)
CARD_BG = (20, 24, 31, 255)
CARD_OUTLINE = (68, 82, 102, 255)
TEXT = (236, 241, 248, 255)
MUTED = (165, 176, 190, 255)
ACCENT = (115, 199, 255, 255)
GOOD = (110, 228, 168, 255)


@dataclass
class PartPose:
    part_id: str
    pivot: tuple[int, int]
    translation: tuple[int, int] = (0, 0)
    rotation_deg: float = 0.0
    scale: float = 1.0


@dataclass
class Keyframe:
    frame: int
    tag: str
    duration_ms: int
    poses: list[PartPose]


@dataclass
class RigPart:
    name: str
    image_path: str
    bbox: tuple[int, int, int, int]
    pivot: tuple[int, int]
    centroid: tuple[int, int]
    area: int


def _bbox_from_alpha(img: Image.Image) -> tuple[int, int, int, int]:
    alpha = img.convert('RGBA').getchannel('A')
    bbox = alpha.getbbox()
    if bbox is None:
        return (0, 0, img.width, img.height)
    return bbox


def _centroid_from_alpha(img: Image.Image) -> tuple[int, int]:
    rgba = img.convert('RGBA')
    alpha = rgba.getchannel('A')
    total = 0
    sx = 0
    sy = 0
    for y in range(alpha.height):
        for x in range(alpha.width):
            a = alpha.getpixel((x, y))
            if a <= 0:
                continue
            total += a
            sx += x * a
            sy += y * a
    if total <= 0:
        return (rgba.width // 2, rgba.height // 2)
    return (int(round(sx / total)), int(round(sy / total)))


def estimate_pivot(img: Image.Image, mode: str = 'bottom_center') -> tuple[int, int]:
    x0, y0, x1, y1 = _bbox_from_alpha(img)
    cx, cy = _centroid_from_alpha(img)
    if mode == 'centroid':
        return (cx, cy)
    if mode == 'shoulder':
        return ((x0 + x1) // 2, int(y0 + (y1 - y0) * 0.28))
    return ((x0 + x1) // 2, y1 - 1)


def extract_part_profile(path: Path, pivot_mode: str = 'bottom_center') -> RigPart:
    img = Image.open(path).convert('RGBA')
    bbox = _bbox_from_alpha(img)
    pivot = estimate_pivot(img, pivot_mode)
    centroid = _centroid_from_alpha(img)
    area = max(0, (bbox[2] - bbox[0]) * (bbox[3] - bbox[1]))
    return RigPart(name=path.stem, image_path=str(path), bbox=bbox, pivot=pivot, centroid=centroid, area=area)


def default_keyframes(parts: list[RigPart]) -> list[Keyframe]:
    idle = Keyframe(frame=0, tag='idle', duration_ms=140, poses=[PartPose(p.name, p.pivot) for p in parts])
    reach = Keyframe(frame=1, tag='reach', duration_ms=120, poses=[PartPose(p.name, p.pivot, rotation_deg=(-12 if i % 2 == 0 else 14)) for i, p in enumerate(parts)])
    brace = Keyframe(frame=2, tag='brace', duration_ms=120, poses=[PartPose(p.name, p.pivot, translation=(0, 2 if i % 2 == 0 else -2), rotation_deg=(8 if i % 2 == 0 else -8)) for i, p in enumerate(parts)])
    return [idle, reach, brace]


def build_demo_parts(root: Path) -> list[Path]:
    root.mkdir(parents=True, exist_ok=True)
    specs = [
        ('body.png', (100, 160), ('rounded_rect', (24, 18, 76, 142), (78, 156, 212, 255))),
        ('head.png', (88, 88), ('ellipse', (16, 10, 72, 68), (234, 242, 250, 255))),
        ('arm_l.png', (92, 74), ('polygon', [(60, 10), (76, 16), (38, 70), (24, 64)], (221, 232, 238, 255))),
        ('arm_r.png', (92, 74), ('polygon', [(32, 10), (16, 16), (54, 70), (68, 64)], (221, 232, 238, 255))),
    ]
    out: list[Path] = []
    for name, size, spec in specs:
        path = root / name
        img = Image.new('RGBA', size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        if spec[0] == 'rounded_rect':
            draw.rounded_rectangle(spec[1], radius=18, fill=spec[2])
        elif spec[0] == 'ellipse':
            draw.ellipse(spec[1], fill=spec[2])
        else:
            draw.polygon(spec[1], fill=spec[2])
        img.save(path)
        out.append(path)
    return out


def render_panel(parts: list[RigPart], keyframes: list[Keyframe], output_path: Path) -> None:
    width, height = 1460, 900
    img = Image.new('RGBA', (width, height), PANEL_BG)
    draw = ImageDraw.Draw(img)
    draw.text((26, 22), 'Sprite Rig Lab', fill=TEXT)
    draw.text((26, 50), 'Salvaged cutout, pivot, and keyframe conventions for 2D part-based animation.', fill=MUTED)
    draw.rounded_rectangle((24, 94, 948, 874), radius=18, fill=CARD_BG, outline=CARD_OUTLINE, width=2)
    draw.rounded_rectangle((968, 94, 1412, 874), radius=18, fill=CARD_BG, outline=CARD_OUTLINE, width=2)
    draw.text((42, 110), 'Part Profiles', fill=ACCENT)
    draw.text((986, 110), 'Keyframes', fill=ACCENT)
    x, y = 42, 150
    for part in parts[:8]:
        box = (x, y, x + 270, y + 168)
        draw.rounded_rectangle(box, radius=14, fill=(25, 30, 38, 255), outline=CARD_OUTLINE, width=1)
        part_img = Image.open(part.image_path).convert('RGBA')
        preview = Image.new('RGBA', (110, 110), (0, 0, 0, 0))
        scale = min(110 / max(1, part_img.width), 110 / max(1, part_img.height))
        resized = part_img.resize((max(1, int(part_img.width * scale)), max(1, int(part_img.height * scale))), Image.Resampling.NEAREST)
        preview.alpha_composite(resized, ((110 - resized.width) // 2, (110 - resized.height) // 2))
        img.alpha_composite(preview, (x + 12, y + 16))
        px = x + 12 + int(part.pivot[0] * scale) + (110 - resized.width) // 2 if part_img.width else x + 68
        py = y + 16 + int(part.pivot[1] * scale) + (110 - resized.height) // 2 if part_img.height else y + 68
        draw.line((px - 7, py, px + 7, py), fill=GOOD, width=2)
        draw.line((px, py - 7, px, py + 7), fill=GOOD, width=2)
        draw.text((x + 134, y + 18), part.name[:18], fill=TEXT)
        draw.text((x + 134, y + 46), f'bbox: {part.bbox}', fill=MUTED)
        draw.text((x + 134, y + 74), f'pivot: {part.pivot}', fill=TEXT)
        draw.text((x + 134, y + 102), f'centroid: {part.centroid}', fill=MUTED)
        draw.text((x + 134, y + 130), f'area: {part.area}', fill=MUTED)
        x += 292
        if x + 270 > 930:
            x = 42
            y += 190
    yy = 150
    for frame in keyframes:
        draw.rounded_rectangle((986, yy, 1392, yy + 170), radius=14, fill=(25, 30, 38, 255), outline=CARD_OUTLINE, width=1)
        draw.text((1004, yy + 16), f"frame {frame.frame}: {frame.tag}", fill=TEXT)
        draw.text((1004, yy + 44), f"duration_ms: {frame.duration_ms}", fill=MUTED)
        line_y = yy + 74
        for pose in frame.poses[:3]:
            draw.text((1004, line_y), f"{pose.part_id}: rot {pose.rotation_deg:+.1f}  move {pose.translation}", fill=TEXT)
            line_y += 28
        yy += 190
    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(output_path)


def main() -> int:
    ap = argparse.ArgumentParser(description='Bridge-side 2D rig profile extractor and previewer.')
    ap.add_argument('--images', nargs='*', help='Optional part images. If omitted, demo parts are generated.')
    ap.add_argument('--pivot-mode', default='bottom_center', choices=['bottom_center', 'centroid', 'shoulder'])
    ap.add_argument('--output', help='Optional JSON output path.')
    ap.add_argument('--debug-image', help='Optional debug image path.')
    ap.add_argument('--json', action='store_true')
    args = ap.parse_args()

    if args.images:
        paths = [Path(p).resolve() for p in args.images]
    else:
        demo_dir = Path('logs').resolve() / 'sprite_rig_demo_parts'
        paths = build_demo_parts(demo_dir)
    parts = [extract_part_profile(path, args.pivot_mode) for path in paths]
    keyframes = default_keyframes(parts)
    report = {
        'tool': 'sprite_rig_lab',
        'part_count': len(parts),
        'pivot_mode': args.pivot_mode,
        'parts': [asdict(p) for p in parts],
        'keyframes': [{
            'frame': k.frame,
            'tag': k.tag,
            'duration_ms': k.duration_ms,
            'poses': [asdict(p) for p in k.poses],
        } for k in keyframes],
        'notes': [
            'This is a bridge-side rig profile and pivot suggestion layer, not a full editor replacement.',
            'Use it to normalize cutout sprites before handoff to a dedicated animation tool or runtime importer.',
        ],
    }
    if args.output:
        out = Path(args.output).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2), encoding='utf-8')
    if args.debug_image:
        render_panel(parts, keyframes, Path(args.debug_image).resolve())
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(json.dumps(report, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
