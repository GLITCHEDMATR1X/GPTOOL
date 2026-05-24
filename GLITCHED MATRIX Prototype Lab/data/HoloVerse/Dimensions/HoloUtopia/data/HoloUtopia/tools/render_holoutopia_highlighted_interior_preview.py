"""Render a lightweight 2D cutaway preview for one highlighted HoloUtopia building interior."""
from __future__ import annotations
import argparse
from pathlib import Path
import sys


def _find_holoverse_root() -> Path:
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        if parent.name.lower() in {"holoverse", "holoutopia"}:
            return parent
    for parent in [here.parent, *here.parents]:
        candidate = parent / "data" / "HoloUtopia"
        if candidate.exists():
            return candidate
    raise SystemExit("Could not resolve data/HoloUtopia root")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render a highlighted interior cutaway preview PNG.")
    parser.add_argument("--neighborhood", default="residential_alpha_neighborhood_01")
    parser.add_argument("--lot", default="res_alpha_lot_07")
    parser.add_argument("--out", default="holoutopia_highlighted_interior_preview.png")
    parser.add_argument("--size", type=int, default=1300)
    args = parser.parse_args(argv)
    root = _find_holoverse_root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    try:
        from PIL import Image, ImageDraw, ImageFont
    except Exception as exc:
        print(f"Pillow is required for preview rendering: {exc}")
        return 2
    from holoutopia_town_blocks import load_interior_blueprint, load_neighborhood
    nbhd = load_neighborhood(args.neighborhood, root)
    lot = next((item for item in nbhd.get("lots", []) if isinstance(item, dict) and str(item.get("id")) == args.lot), None)
    if lot is None:
        print(f"Lot not found: {args.lot}")
        return 2
    interior = load_interior_blueprint(str(lot.get("interior_blueprint_id")), root)
    size = max(720, int(args.size))
    img = Image.new("RGBA", (size, size), (2, 8, 12, 255))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 22)
        small = ImageFont.truetype("DejaVuSans.ttf", 15)
        tiny = ImageFont.truetype("DejaVuSans.ttf", 12)
    except Exception:
        font = small = tiny = None
    margin = 90
    x0, x1 = margin, size - margin
    y0, y1 = margin + 122, size - margin
    profile = interior.get("source_building_profile", {})
    floor_count = int(profile.get("floor_count", max(1, len(interior.get("floors", [])) - 1)))
    floor_h = (y1 - y0) / max(1, floor_count + 1)
    draw.text((margin, 28), f"HoloUtopia highlighted interior: {interior.get('display_name')}", fill=(236, 255, 238, 255), font=font)
    draw.text((margin, 58), "load mode: highlight_only / unload on selection change", fill=(255, 224, 90, 240), font=small)
    draw.text((margin, 82), "foundation contract: building sits on pad / no arbitrary crossing lines", fill=(120, 255, 232, 230), font=small)
    draw.rectangle([x0, y0, x1, y1], outline=(255, 230, 80, 220), width=3)
    # Floors.
    for floor in range(0, floor_count + 1):
        y = y1 - floor * floor_h
        fill = (255, 230, 80, 210) if floor in {0, floor_count} else (100, 255, 240, 150)
        draw.line([x0, y, x1, y], fill=fill, width=3 if floor in {0, floor_count} else 1)
        draw.text((x0 - 56, y - 8), f"F{floor}", fill=(200, 255, 255, 210), font=tiny)
    # Resident units.
    units_by_floor = {}
    for unit in interior.get("resident_unit_slots", []):
        units_by_floor.setdefault(int(unit.get("floor", 1)), []).append(unit)
    for floor, units in units_by_floor.items():
        y_top = y1 - floor * floor_h
        y_bottom = y1 - (floor - 1) * floor_h
        room_w = (x1 - x0 - 70) / max(1, len(units))
        for idx, unit in enumerate(units):
            rx0 = x0 + 35 + idx * room_w
            rx1 = rx0 + room_w * 0.78
            ry0 = y_top + 12
            ry1 = y_bottom - 12
            assigned = bool(unit.get("assigned_npc_ids"))
            fill = (255, 90, 70, 94) if assigned else (40, 255, 190, 72)
            outline = (255, 150, 120, 230) if assigned else (88, 255, 210, 190)
            draw.rectangle([rx0, ry0, rx1, ry1], fill=fill, outline=outline, width=2)
            label = f"{unit.get('id').split('_')[-1]} cap {unit.get('capacity')}"
            if assigned:
                label += " HOME"
            draw.text((rx0 + 4, ry0 + 4), label, fill=(235, 255, 245, 230), font=tiny)
    # Activity nodes.
    for node in interior.get("activity_nodes", []):
        floor = int(node.get("floor", 0))
        ox, oy, _ = node.get("local_offset_3d", [0, 0, floor])
        px = (x0 + x1) * 0.5 + float(ox) * (x1 - x0) * 0.7
        py = y1 - floor * floor_h - floor_h * 0.45 + float(oy) * floor_h
        draw.ellipse([px - 5, py - 5, px + 5, py + 5], fill=(255, 245, 88, 255))
        draw.text((px + 8, py - 7), str(node.get("kind", "node")), fill=(255, 245, 120, 220), font=tiny)
    draw.text((margin, size - margin + 24), f"capacity: {profile.get('residential_capacity')} | floors: {profile.get('floor_count')} | source lot: {interior.get('lot_id')}", fill=(210, 255, 255, 230), font=small)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
