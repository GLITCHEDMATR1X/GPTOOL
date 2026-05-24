"""Render a top-down PNG preview of all HoloUtopia residential infill neighborhoods."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


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
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="holoutopia_cross_district_residential_infill_preview.png")
    args = parser.parse_args(argv)
    root = _find_holoverse_root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from holoutopia_town_blocks import city_frame_metrics, load_all_neighborhoods, load_city_atlas, load_town
    atlas = load_city_atlas(root)
    metrics = city_frame_metrics(atlas)
    town_pos = {str(e.get("town_id")): e.get("city_grid", [0, 0]) for e in atlas.get("towns", []) if isinstance(e, dict)}
    neighborhoods = load_all_neighborhoods(root)
    scale = 0.22
    margin = 90
    # compute bounds from atlas frames
    coords = []
    for grid in town_pos.values():
        coords.append((grid[0] * metrics["frame_w"], grid[1] * metrics["frame_h"]))
    minx = min(x for x, y in coords) - metrics["frame_w"] * 0.58
    maxx = max(x for x, y in coords) + metrics["frame_w"] * 0.58
    miny = min(y for x, y in coords) - metrics["frame_h"] * 0.58
    maxy = max(y for x, y in coords) + metrics["frame_h"] * 0.58
    w = int((maxx - minx) * scale + margin * 2)
    h = int((maxy - miny) * scale + margin * 2)
    img = Image.new("RGB", (w, h), (2, 8, 12))
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default()
    colors = {"low": (235, 238, 170), "mid": (50, 220, 235), "tall": (230, 80, 255)}
    def sx(x): return int((x - minx) * scale + margin)
    def sy(y): return int(h - ((y - miny) * scale + margin))
    def grid_to_world(town, grid):
        gx, gy = grid
        width, height = town["grid_size"]
        bs = town["block_size"]
        return ((gx - (width - 1) * 0.5) * bs, ((height - 1) * 0.5 - gy) * bs)
    # draw district frames
    for town_id, grid in town_pos.items():
        cx = grid[0] * metrics["frame_w"]; cy = grid[1] * metrics["frame_h"]
        fw = metrics["grid_w"] * metrics["block_size"]; fh = metrics["grid_h"] * metrics["block_size"]
        draw.rectangle([sx(cx-fw/2), sy(cy+fh/2), sx(cx+fw/2), sy(cy-fh/2)], outline=(20, 160, 180), width=1)
        draw.text((sx(cx-fw/2)+4, sy(cy+fh/2)+4), town_id, fill=(160, 250, 255), font=font)
    total_capacity = 0
    for neighborhood in neighborhoods:
        town_id = str(neighborhood.get("town_id"))
        if town_id not in town_pos: continue
        town = load_town(town_id, root)
        blocks = {str(b.get("id")): b for b in town.get("town_blocks", []) if isinstance(b, dict)}
        offx = town_pos[town_id][0] * metrics["frame_w"]; offy = town_pos[town_id][1] * metrics["frame_h"]
        for lot in neighborhood.get("lots", []):
            block = blocks.get(str(lot.get("block")))
            if not block: continue
            bx, by = grid_to_world(town, [block["grid"][0] + (block["size"][0]-1)*0.5, block["grid"][1] + (block["size"][1]-1)*0.5])
            fp = lot.get("footprint", {}).get("size_blocks", [0.55,0.55])
            prof = lot.get("building_profile", {})
            hclass = prof.get("height_class", "low")
            cap = int(prof.get("residential_capacity", 0) or 0)
            total_capacity += cap
            bs = town["block_size"]
            hw = fp[0]*bs/2; hh = fp[1]*bs/2
            color = colors.get(hclass, (220,220,220))
            rect = [sx(offx+bx-hw), sy(offy+by+hh), sx(offx+bx+hw), sy(offy+by-hh)]
            draw.rectangle(rect, fill=tuple(max(0, c//5) for c in color), outline=color, width=2)
            draw.text((rect[0]+2, rect[1]+2), str(cap), fill=(255,255,255), font=font)
    draw.text((20, 20), f"HoloUtopia Cross-District Residential Infill | neighborhoods={len(neighborhoods)} capacity={total_capacity}", fill=(245,245,220), font=font)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    print(out)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
