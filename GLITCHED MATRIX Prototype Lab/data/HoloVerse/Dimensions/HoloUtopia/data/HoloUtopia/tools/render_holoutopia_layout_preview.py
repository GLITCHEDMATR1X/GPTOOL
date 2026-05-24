"""Render a lightweight 2D preview of authored HoloUtopia town data.

This is not an in-game Panda3D screenshot; it is a safe layout preview for
reviewing the JSON town grid when Panda3D is unavailable.
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path
import sys


def _find_holoverse_root() -> Path:
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        if parent.name.lower() in {"holoverse", "holoutopia"} and (parent / "main.py").exists():
            return parent
    for parent in [here.parent, *here.parents]:
        candidate = parent / "data" / "HoloUtopia"
        if candidate.exists():
            return candidate
    raise SystemExit("Could not resolve data/HoloUtopia root")


def _world_to_image(x: float, y: float, scale: float, cx: float, cy: float) -> tuple[int, int]:
    return int(cx + x * scale), int(cy - y * scale)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render HoloUtopia town layout preview PNG.")
    parser.add_argument("--town", default="central_core_civic_ring")
    parser.add_argument("--out", default="holoutopia_central_core_preview.png")
    parser.add_argument("--size", type=int, default=1200)
    args = parser.parse_args(argv)

    root = _find_holoverse_root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from holoutopia_town_blocks import grid_to_world, load_town, town_bounds

    try:
        from PIL import Image, ImageDraw, ImageFont
    except Exception as exc:
        print(f"Pillow is required for preview rendering: {exc}")
        return 2

    town = load_town(args.town, holoverse_root=root)
    size = max(512, int(args.size))
    img = Image.new("RGBA", (size, size), (2, 11, 14, 255))
    draw = ImageDraw.Draw(img)
    bounds = town_bounds(town)
    margin = 80
    scale = min((size - margin * 2) / max(bounds.width, 1.0), (size - margin * 2) / max(bounds.height, 1.0))
    cx = size * 0.5
    cy = size * 0.5

    def line(points, fill, width=2):
        draw.line([_world_to_image(p.x, p.y, scale, cx, cy) for p in points], fill=fill, width=width, joint="curve")

    block_size = float(town["block_size"])
    grid_w, grid_h = town["grid_size"]
    for gx in range(grid_w + 1):
        x = bounds.min_x + gx * block_size
        line([type("P", (), {"x": x, "y": bounds.min_y})(), type("P", (), {"x": x, "y": bounds.max_y})()], (0, 170, 190, 80), 1)
    for gy in range(grid_h + 1):
        y = bounds.min_y + gy * block_size
        line([type("P", (), {"x": bounds.min_x, "y": y})(), type("P", (), {"x": bounds.max_x, "y": y})()], (0, 170, 190, 80), 1)

    for road in town.get("roads", []):
        if road.get("kind") == "radial":
            line([grid_to_world(town, road["from"]), grid_to_world(town, road["to"])], (0, 245, 255, 190), max(2, int(float(road.get("width", 8)) * 0.35)))
        elif road.get("kind") == "ring":
            center = grid_to_world(town, road["center"])
            radius = float(road["radius_blocks"]) * block_size
            pts = [type("P", (), {"x": center.x + math.cos(i / 160 * math.tau) * radius, "y": center.y + math.sin(i / 160 * math.tau) * radius})() for i in range(161)]
            line(pts, (0, 235, 255, 150), max(2, int(float(road.get("width", 8)) * 0.28)))

    colors = {
        "portal": (220, 60, 255, 150),
        "home": (70, 255, 170, 130),
        "market": (255, 80, 235, 140),
        "guard": (90, 255, 90, 140),
        "restricted": (255, 70, 45, 150),
        "command": (255, 205, 55, 150),
        "matrixcore": (255, 55, 65, 150),
        "service": (65, 245, 220, 135),
        "garden": (70, 255, 110, 110),
        "transit": (80, 130, 255, 140),
        "future": (140, 155, 170, 95),
        "harbor": (40, 235, 255, 145),
        "water": (35, 105, 255, 115),
        "dock": (55, 210, 230, 145),
        "archive": (170, 105, 255, 145),
        "memory": (220, 75, 255, 135),
        "research": (110, 220, 255, 140),
        "default": (75, 190, 255, 130),
    }
    for block in town.get("town_blocks", []):
        center = grid_to_world(town, [block["grid"][0] + (block.get("size", [1, 1])[0] - 1) * 0.5, block["grid"][1] + (block.get("size", [1, 1])[1] - 1) * 0.5])
        w = block.get("size", [1, 1])[0] * block_size * 0.74
        h = block.get("size", [1, 1])[1] * block_size * 0.74
        tags = set(str(t).lower() for t in block.get("tags", []))
        key = "default"
        for probe in ("portal", "matrixcore", "restricted", "command", "memory", "research", "archive", "water", "dock", "harbor", "home", "market", "guard", "service", "garden", "transit", "future"):
            if probe in tags or probe in str(block.get("style", "")).lower() or probe in str(block.get("type", "")).lower():
                key = probe
                break
        p0 = _world_to_image(center.x - w * 0.5, center.y - h * 0.5, scale, cx, cy)
        p1 = _world_to_image(center.x + w * 0.5, center.y + h * 0.5, scale, cx, cy)
        x0, x1 = sorted((p0[0], p1[0]))
        y0, y1 = sorted((p0[1], p1[1]))
        draw.rectangle([x0, y0, x1, y1], fill=colors[key], outline=(220, 250, 255, 230), width=2)

    hub = town.get("portal_hub")
    anchor = town.get("district_anchor") if isinstance(town.get("district_anchor"), dict) else None
    if isinstance(hub, dict):
        center = grid_to_world(town, hub.get("grid", [0, 0]))
        radius = float(hub.get("radius", 52))
        oct_pts = []
        for index in range(8):
            angle = math.radians(22.5 + index * 45)
            oct_pts.append(_world_to_image(center.x + math.cos(angle) * radius, center.y + math.sin(angle) * radius, scale, cx, cy))
        draw.polygon(oct_pts, outline=(255, 65, 255, 255), fill=(255, 65, 255, 42))
        for portal in hub.get("portals", []):
            angle = math.radians(float(portal.get("angle_degrees", 0)))
            px, py = _world_to_image(center.x + math.cos(angle) * (radius + 8), center.y + math.sin(angle) * (radius + 8), scale, cx, cy)
            draw.ellipse([px - 6, py - 6, px + 6, py + 6], fill=(255, 220, 255, 245), outline=(255, 65, 255, 255))
    elif anchor is not None:
        center = grid_to_world(town, anchor.get("grid", [0, 0]))
        radius = float(anchor.get("radius", 40))
        pts = [
            _world_to_image(center.x, center.y + radius, scale, cx, cy),
            _world_to_image(center.x + radius, center.y, scale, cx, cy),
            _world_to_image(center.x, center.y - radius, scale, cx, cy),
            _world_to_image(center.x - radius, center.y, scale, cx, cy),
        ]
        draw.polygon(pts, outline=(255, 220, 70, 255), fill=(255, 220, 70, 40))

    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 20)
        small = ImageFont.truetype("DejaVuSans.ttf", 14)
    except Exception:
        font = small = None
    draw.text((24, 24), str(town.get("display_name") or town.get("id") or "HoloUtopia Town"), fill=(230, 250, 255, 255), font=font)
    draw.text((24, 54), f"{len(town.get('town_blocks', []))} blocks  |  {len(town.get('roads', []))} roads  |  {len(town.get('schedule_nodes', []))} schedule nodes", fill=(160, 230, 240, 230), font=small)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
