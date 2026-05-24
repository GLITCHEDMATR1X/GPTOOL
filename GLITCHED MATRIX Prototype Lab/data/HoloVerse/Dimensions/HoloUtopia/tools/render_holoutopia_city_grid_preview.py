"""Render a city-level HoloUtopia district-frame preview PNG."""
from __future__ import annotations
import argparse, sys
from pathlib import Path


def _find_holoverse_root() -> Path:
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        if parent.name.lower() == "holoverse" and (parent / "main.py").exists():
            return parent
    for parent in [here.parent, *here.parents]:
        candidate = parent / "data" / "HoloVerse"
        if candidate.exists():
            return candidate
    raise SystemExit("Could not resolve data/HoloVerse root")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render HoloUtopia city atlas preview PNG.")
    parser.add_argument("--out", default="holoutopia_city_grid_evenness_preview.png")
    parser.add_argument("--size", type=int, default=1400)
    args = parser.parse_args(argv)
    root = _find_holoverse_root()
    sys.path.insert(0, str(root)) if str(root) not in sys.path else None
    from holoutopia_town_blocks import city_frame_metrics, load_city_atlas, load_town
    try:
        from PIL import Image, ImageDraw, ImageFont
    except Exception as exc:
        print(f"Pillow is required for preview rendering: {exc}")
        return 2
    atlas = load_city_atlas(root)
    metrics = city_frame_metrics(atlas)
    size = max(768, int(args.size))
    img = Image.new("RGBA", (size, size), (2, 9, 13, 255))
    draw = ImageDraw.Draw(img)
    entries = [e for e in atlas.get("towns", []) if isinstance(e, dict)]
    slots = [(int(e["city_grid"][0]), int(e["city_grid"][1]), e) for e in entries]
    min_x = min(x for x, _, _ in slots) - 0.7
    max_x = max(x for x, _, _ in slots) + 0.7
    min_y = min(y for _, y, _ in slots) - 0.7
    max_y = max(y for _, y, _ in slots) + 0.7
    span_x = max(1.0, max_x - min_x)
    span_y = max(1.0, max_y - min_y)
    margin = 120
    scale = min((size - margin * 2) / span_x, (size - margin * 2) / span_y)
    def pt(cx: float, cy: float) -> tuple[int, int]:
        return int(margin + (cx - min_x) * scale), int(size - margin - (cy - min_y) * scale)
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 22)
        small = ImageFont.truetype("DejaVuSans.ttf", 15)
        tiny = ImageFont.truetype("DejaVuSans.ttf", 12)
    except Exception:
        font = small = tiny = None
    by_town = {str(e.get("town_id")): e for e in entries}
    for conn in atlas.get("connections", []):
        a = by_town.get(str(conn.get("from"))) if isinstance(conn, dict) else None
        b = by_town.get(str(conn.get("to"))) if isinstance(conn, dict) else None
        if not a or not b:
            continue
        p0 = pt(float(a["city_grid"][0]), float(a["city_grid"][1]))
        p1 = pt(float(b["city_grid"][0]), float(b["city_grid"][1]))
        draw.line([p0, p1], fill=(0, 235, 255, 115), width=8)
        draw.line([p0, p1], fill=(190, 250, 255, 210), width=2)
    colors = {"portal_core": (255, 65, 255, 155), "starter_neighborhood": (80, 255, 170, 145), "market_social": (255, 80, 230, 145), "controlled_access": (90, 255, 90, 145), "industrial_service": (160, 255, 80, 145), "harbor_waterfront": (55, 210, 255, 145), "archive_memory": (175, 105, 255, 145), "civic_commons": (90, 255, 205, 145), "glitched_restricted": (255, 55, 85, 155)}
    frame_w = scale * 0.82
    frame_h = scale * 0.66
    for x, y, entry in slots:
        town_id = str(entry.get("town_id"))
        role = str(entry.get("role", ""))
        town = load_town(town_id, holoverse_root=root)
        cx, cy = pt(x, y)
        x0, y0 = int(cx - frame_w * 0.5), int(cy - frame_h * 0.5)
        x1, y1 = int(cx + frame_w * 0.5), int(cy + frame_h * 0.5)
        draw.rounded_rectangle([x0, y0, x1, y1], radius=16, fill=colors.get(role, (75, 190, 255, 130)), outline=(220, 250, 255, 235), width=3)
        for gx in range(1, int(metrics["grid_w"])):
            xx = x0 + (x1 - x0) * gx / metrics["grid_w"]
            draw.line([(xx, y0), (xx, y1)], fill=(235, 255, 255, 45), width=1)
        for gy in range(1, int(metrics["grid_h"])):
            yy = y0 + (y1 - y0) * gy / metrics["grid_h"]
            draw.line([(x0, yy), (x1, yy)], fill=(235, 255, 255, 45), width=1)
        label = str(town.get("display_name") or town_id).replace(" Holo-Grid", "")
        draw.text((x0 + 12, y0 + 10), label, fill=(245, 255, 255, 255), font=small)
        draw.text((x0 + 12, y0 + 34), f"{town['grid_size'][0]}x{town['grid_size'][1]}  blocks:{len(town.get('town_blocks', []))}", fill=(220, 250, 255, 220), font=tiny)
        draw.text((x0 + 12, y1 - 24), f"city {entry.get('city_grid')}", fill=(190, 235, 245, 220), font=tiny)
    draw.text((28, 24), str(atlas.get("display_name", "HoloUtopia City Grid")), fill=(235, 255, 255, 255), font=font)
    draw.text((28, 58), f"alignment {atlas.get('alignment_id')} | canonical {atlas.get('canonical_grid_size')} | next: {atlas.get('next_build_target', {}).get('town_id')}", fill=(150, 230, 245, 230), font=small)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
