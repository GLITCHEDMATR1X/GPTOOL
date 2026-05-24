from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from holoutopia_citizen_simulation import load_simulation_inputs
from holoutopia_navigation import build_citizen_route_index, load_navigation_graph


def _load_font(size: int = 14):
    try:
        from PIL import ImageFont
        for name in ("DejaVuSans.ttf", "Arial.ttf"):
            try:
                return ImageFont.truetype(name, size)
            except Exception:
                pass
        return ImageFont.load_default()
    except Exception:
        return None


def _role_color(role: str) -> tuple[int, int, int]:
    role = str(role)
    if "glitched" in role:
        return (150, 70, 180)
    if "security" in role or "controlled" in role:
        return (135, 180, 80)
    if "market" in role:
        return (205, 150, 75)
    if "harbor" in role:
        return (60, 160, 215)
    if "archive" in role:
        return (160, 120, 230)
    if "industrial" in role:
        return (220, 110, 80)
    if "civic" in role:
        return (95, 205, 190)
    if "starter" in role or "residential" in role:
        return (80, 180, 255)
    return (80, 130, 145)


def render_preview(out_path: Path, route_limit: int = 12) -> Path:
    from PIL import Image, ImageDraw

    inputs = load_simulation_inputs(ROOT)
    atlas = inputs["city_atlas"]
    graph = load_navigation_graph(ROOT)
    route_index = build_citizen_route_index(ROOT)
    frame_w, frame_h = atlas.get("canonical_grid_size", [10, 8])
    gap = int(atlas.get("district_gap_blocks", 2))
    block = int(atlas.get("block_size", 64))
    city_w = (3 * frame_w + 2 * gap) * block
    city_h = (3 * frame_h + 2 * gap) * block
    img_w, img_h = 1360, 920
    margin = 70
    right_panel = 360
    canvas_w = img_w - margin * 2 - right_panel
    canvas_h = img_h - 170
    scale = min(canvas_w / city_w, canvas_h / city_h)
    ox = margin
    oy = 112

    img = Image.new("RGB", (img_w, img_h), (6, 12, 16))
    draw = ImageDraw.Draw(img)
    title_font = _load_font(23)
    font = _load_font(14)
    small = _load_font(11)
    draw.text((margin, 26), "HoloUtopia Navigation Graph + Citizen Commute Routes", fill=(220, 245, 255), font=title_font)
    draw.text((margin, 58), "District centers/gates form the route spine; citizen home/work/social nodes connect as temporary endpoints.", fill=(145, 178, 188), font=font)

    towns_by_id = {str(t["town_id"]): t for t in atlas.get("towns", []) if isinstance(t, dict)}
    for tid, town in towns_by_id.items():
        gx, gy = town.get("city_grid", [0, 0])
        x = ox + gx * (frame_w + gap) * block * scale
        y = oy + (2 - gy) * (frame_h + gap) * block * scale
        w = frame_w * block * scale
        h = frame_h * block * scale
        color = _role_color(str(town.get("role", "")))
        draw.rectangle((x, y, x + w, y + h), outline=color, width=2)
        draw.text((x + 5, y + 5), tid.replace("_", " ").title()[:27], fill=(170, 210, 215), font=small)

    def map_xy(world: list[float] | tuple[float, float]) -> tuple[float, float]:
        return ox + float(world[0]) * scale, oy + (city_h - float(world[1])) * scale

    graph_nodes = {str(n.get("id")): n for n in graph.get("nodes", []) if isinstance(n, dict)}
    for edge in graph.get("edges", []):
        if not isinstance(edge, dict):
            continue
        a = graph_nodes.get(str(edge.get("from")))
        b = graph_nodes.get(str(edge.get("to")))
        if not a or not b:
            continue
        ax, ay = map_xy(a.get("world", [0, 0]))
        bx, by = map_xy(b.get("world", [0, 0]))
        tags = edge.get("tags", []) if isinstance(edge.get("tags"), list) else []
        color = (85, 170, 190)
        if "restricted_checkpoint" in tags:
            color = (210, 90, 220)
        elif "security_monitored" in tags:
            color = (185, 220, 90)
        draw.line((ax, ay, bx, by), fill=color, width=2)

    for node in graph_nodes.values():
        x, y = map_xy(node.get("world", [0, 0]))
        kind = str(node.get("kind"))
        r = 4 if kind == "district_center" else 3
        fill = (230, 250, 255) if kind == "district_center" else (110, 220, 240)
        draw.ellipse((x - r, y - r, x + r, y + r), fill=fill)

    # Draw a sample of citizen home->work routes on top.
    palette = [(255, 225, 90), (255, 150, 90), (135, 245, 160), (190, 135, 255), (95, 200, 255)]
    route_rows = []
    for idx, (cid, record) in enumerate(route_index.get("citizens", {}).items()):
        if idx >= route_limit:
            break
        route = record.get("routes", {}).get("home_to_work", {})
        steps = route.get("steps", [])
        if len(steps) >= 2:
            color = palette[idx % len(palette)]
            points = [map_xy(step.get("world", [0, 0])) for step in steps]
            for a, b in zip(points, points[1:]):
                draw.line((*a, *b), fill=color, width=1)
            route_rows.append((record.get("display_name", cid), route.get("distance_units", 0), route.get("district_hops", 0), route.get("route_tags", []), color))

    panel_x = img_w - right_panel + 10
    draw.rectangle((panel_x - 12, 100, img_w - 40, img_h - 65), outline=(35, 95, 110), fill=(4, 9, 12))
    totals = route_index.get("totals", {})
    draw.text((panel_x, 118), "Route Index", fill=(220, 245, 255), font=font)
    summary = [
        f"citizens: {totals.get('citizens')}",
        f"routes: {totals.get('routes')}",
        f"nav nodes: {len(graph.get('nodes', []))}",
        f"nav edges: {len(graph.get('edges', []))}",
        f"max district hops: {totals.get('max_district_hops')}",
        f"restricted-tagged: {totals.get('restricted_tagged_routes')}",
    ]
    y = 150
    for line in summary:
        draw.text((panel_x, y), line, fill=(165, 198, 205), font=small)
        y += 19
    y += 12
    draw.text((panel_x, y), "Sample home → work routes", fill=(220, 245, 255), font=font)
    y += 26
    for name, distance, hops, tags, color in route_rows[:route_limit]:
        draw.line((panel_x, y + 7, panel_x + 18, y + 7), fill=color, width=2)
        tag_text = " restricted" if "restricted_checkpoint" in tags else ""
        draw.text((panel_x + 26, y), f"{str(name)[:22]}", fill=(190, 225, 230), font=small)
        draw.text((panel_x + 26, y + 14), f"{int(float(distance))}u, {hops} hops{tag_text}", fill=(130, 160, 168), font=small)
        y += 36

    legend_y = img_h - 42
    legend = [
        ((85, 170, 190), "public route spine"),
        ((185, 220, 90), "security monitored"),
        ((210, 90, 220), "restricted checkpoint"),
        ((255, 225, 90), "sample citizen routes"),
    ]
    x = margin
    for color, label in legend:
        draw.line((x, legend_y + 8, x + 30, legend_y + 8), fill=color, width=3)
        draw.text((x + 38, legend_y), label, fill=(170, 200, 205), font=small)
        x += 230

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)
    return out_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Render HoloUtopia navigation and citizen route preview.")
    parser.add_argument("--out", default="/mnt/data/holoutopia_navigation_routes_preview.png")
    parser.add_argument("--route-limit", type=int, default=12)
    args = parser.parse_args()
    out = render_preview(Path(args.out), route_limit=args.route_limit)
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
