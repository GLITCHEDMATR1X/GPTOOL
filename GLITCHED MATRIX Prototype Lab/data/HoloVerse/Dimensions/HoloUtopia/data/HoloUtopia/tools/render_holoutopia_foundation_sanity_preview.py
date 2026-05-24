"""Render a 2D visual-sanity preview for Residential Alpha foundations."""
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
    parser = argparse.ArgumentParser(description="Render Residential Alpha foundation sanity preview PNG.")
    parser.add_argument("--out", default="holoutopia_residential_alpha_foundation_sanity_preview.png")
    parser.add_argument("--size", type=int, default=1400)
    args = parser.parse_args(argv)
    root = _find_holoverse_root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    try:
        from PIL import Image, ImageDraw, ImageFont
    except Exception as exc:
        print(f"Pillow is required for preview rendering: {exc}")
        return 2
    from holoutopia_town_blocks import load_neighborhood, load_town, neighborhood_local_point
    nbhd = load_neighborhood("residential_alpha_neighborhood_01", root)
    town = load_town(str(nbhd.get("town_id")), root)
    blocks = {str(b.get("id")): b for b in town.get("town_blocks", [])}
    size = max(900, int(args.size))
    img = Image.new("RGBA", (size, size), (2, 8, 12, 255))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 24)
        small = ImageFont.truetype("DejaVuSans.ttf", 15)
        tiny = ImageFont.truetype("DejaVuSans.ttf", 11)
    except Exception:
        font = small = tiny = None
    block_size = float(town["block_size"])
    coords = []
    lots = []
    for lot in nbhd.get("lots", []):
        block = blocks.get(str(lot.get("block")))
        if not block:
            continue
        fp = lot.get("footprint", {})
        fd = lot.get("foundation_profile", {})
        c = neighborhood_local_point(town, block, fp.get("local_offset", [0,0]))
        fc = neighborhood_local_point(town, block, fd.get("pad_local_offset", fp.get("local_offset", [0,0])))
        sx, sy = fp.get("size_blocks", [0.5,0.5])
        psx, psy = fd.get("pad_size_blocks", [float(sx)+0.12,float(sy)+0.12])
        lots.append((lot,c,fc,float(sx)*block_size,float(sy)*block_size,float(psx)*block_size,float(psy)*block_size))
        coords.extend([(fc.x-float(psx)*block_size/2,fc.y-float(psy)*block_size/2),(fc.x+float(psx)*block_size/2,fc.y+float(psy)*block_size/2)])
    minx=min(x for x,y in coords)-40; maxx=max(x for x,y in coords)+40; miny=min(y for x,y in coords)-40; maxy=max(y for x,y in coords)+40
    scale=min((size-160)/(maxx-minx),(size-220)/(maxy-miny))
    def xy(x,y):
        return (80+(x-minx)*scale, size-100-(y-miny)*scale)
    draw.text((80,30), "Residential Alpha: foundations under buildings", fill=(238,255,238,255), font=font)
    draw.text((80,62), "dark slab = foundation pad / bright outline = building footprint / no arbitrary roof diagonals", fill=(255,230,95,235), font=small)
    for lot,c,fc,w,h,pw,ph in lots:
        lid=str(lot.get('id'))
        x0,y0=xy(fc.x-pw/2, fc.y+ph/2); x1,y1=xy(fc.x+pw/2, fc.y-ph/2)
        draw.rectangle([x0,y0,x1,y1], fill=(8,45,54,230), outline=(75,255,225,230), width=3)
        bx0,by0=xy(c.x-w/2,c.y+h/2); bx1,by1=xy(c.x+w/2,c.y-h/2)
        cls=str(lot.get('building_profile',{}).get('height_class','low'))
        col={'low':(235,255,210,235),'mid':(80,245,255,235),'tall':(225,100,255,235)}.get(cls,(235,255,210,235))
        draw.rectangle([bx0,by0,bx1,by1], outline=col, width=2)
        profile=lot.get('building_profile',{})
        draw.text((bx0+3, by0+3), f"{lid[-2:]} F{profile.get('floor_count')} C{profile.get('residential_capacity')}", fill=(235,255,245,230), font=tiny)
    draw.text((80,size-62), "Foundation contract: building footprint fits pad, pad masks underlay grid, interiors only appear on highlight.", fill=(210,255,255,230), font=small)
    out=Path(args.out); out.parent.mkdir(parents=True, exist_ok=True); img.save(out); print(out); return 0

if __name__ == "__main__":
    raise SystemExit(main())
