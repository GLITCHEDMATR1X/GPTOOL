"""Render a citywide purpose/structure variant preview for HoloUtopia."""
from __future__ import annotations
import argparse, sys
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


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = str(value or "#dff7ff").strip().lstrip("#")
    if len(value) != 6:
        return (223, 247, 255)
    return tuple(int(value[i:i+2], 16) for i in (0, 2, 4))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="holoutopia_structure_variants_preview.png")
    args = parser.parse_args(argv)
    root = _find_holoverse_root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from holoutopia_town_blocks import city_frame_metrics, load_city_atlas, load_town
    atlas = load_city_atlas(root)
    metrics = city_frame_metrics(atlas)
    town_entries = [e for e in atlas.get("towns", []) if isinstance(e, dict)]
    scale = 0.20
    margin = 130
    coords = [(e.get("city_grid", [0,0])[0]*metrics["frame_w"], e.get("city_grid", [0,0])[1]*metrics["frame_h"]) for e in town_entries]
    minx = min(x for x, y in coords) - metrics["frame_w"] * 0.60
    maxx = max(x for x, y in coords) + metrics["frame_w"] * 0.60
    miny = min(y for x, y in coords) - metrics["frame_h"] * 0.60
    maxy = max(y for x, y in coords) + metrics["frame_h"] * 0.60
    w = int((maxx - minx) * scale + margin * 2 + 320)
    h = int((maxy - miny) * scale + margin * 2)
    img = Image.new("RGB", (w, h), (2, 8, 12))
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default()
    def sx(x: float) -> int: return int((x - minx) * scale + margin)
    def sy(y: float) -> int: return int(h - ((y - miny) * scale + margin))
    def town_grid_to_world(town: dict, grid: list[float]) -> tuple[float, float]:
        gx, gy = grid
        width, height = town["grid_size"]
        bs = town["block_size"]
        return ((gx - (width - 1) * 0.5) * bs, ((height - 1) * 0.5 - gy) * bs)
    purpose_legend: dict[str, tuple[int, int, int]] = {}
    total_blocks = 0
    for entry in town_entries:
        town_id = str(entry.get("town_id"))
        town = load_town(town_id, root)
        profile = town.get("structure_variant_profile", {})
        purpose_colors = {str(p.get("id")): _hex_to_rgb(str(p.get("color", "#dff7ff"))) for p in profile.get("purpose_layers", []) if isinstance(p, dict)}
        ox = entry.get("city_grid", [0,0])[0] * metrics["frame_w"]
        oy = entry.get("city_grid", [0,0])[1] * metrics["frame_h"]
        fw = metrics["grid_w"] * metrics["block_size"]
        fh = metrics["grid_h"] * metrics["block_size"]
        draw.rectangle([sx(ox-fw/2), sy(oy+fh/2), sx(ox+fw/2), sy(oy-fh/2)], outline=(20, 160, 180), width=1)
        draw.text((sx(ox-fw/2)+4, sy(oy+fh/2)+4), town_id, fill=(170, 245, 255), font=font)
        for block in town.get("town_blocks", []):
            if not isinstance(block, dict):
                continue
            gx, gy = block.get("grid", [0,0])
            bw, bh = block.get("size", [1,1])
            cx, cy = town_grid_to_world(town, [gx+(bw-1)*0.5, gy+(bh-1)*0.5])
            bs = town["block_size"]
            rect = [sx(ox+cx-bw*bs*0.36), sy(oy+cy+bh*bs*0.36), sx(ox+cx+bw*bs*0.36), sy(oy+cy-bh*bs*0.36)]
            pid = str(block.get("purpose_id", "unknown"))
            color = purpose_colors.get(pid, (223, 247, 255))
            purpose_legend.setdefault(pid, color)
            fill = tuple(max(0, int(c*0.17)) for c in color)
            draw.rectangle(rect, fill=fill, outline=color, width=1)
            total_blocks += 1
    draw.text((20, 22), f"HoloUtopia Pass 14 | District Structure Variants + Purposes | blocks={total_blocks} purposes={len(purpose_legend)}", fill=(245,245,220), font=font)
    lx = w - 300
    ly = 56
    draw.text((lx, ly-24), "Purpose legend", fill=(240, 245, 255), font=font)
    for idx, (pid, color) in enumerate(sorted(purpose_legend.items())[:34]):
        y = ly + idx * 18
        draw.rectangle([lx, y, lx+12, y+12], fill=color)
        draw.text((lx+18, y-1), pid, fill=(225, 238, 242), font=font)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
