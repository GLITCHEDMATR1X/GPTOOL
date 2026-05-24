from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from holoutopia_game_runtime import build_runtime_summary, load_runtime_config, _node_grid_to_city_render_xy
from holoutopia_town_blocks import city_frame_metrics, load_city_atlas, load_town, town_bounds
from holoutopia_citizen_simulation import build_node_index, load_simulation_inputs, simulate_city_at_time


def main() -> int:
    try:
        from PIL import Image, ImageDraw, ImageFont
    except Exception as exc:
        print(f"Pillow unavailable: {exc}")
        return 2

    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("holoutopia_world_integration_preview.png")
    cfg = load_runtime_config(ROOT)
    summary = build_runtime_summary(ROOT).as_dict()
    placement = cfg.get("placement", {}) if isinstance(cfg.get("placement"), dict) else {}
    integration = cfg.get("world_integration", {}) if isinstance(cfg.get("world_integration"), dict) else {}
    scale = float(placement.get("scale", 0.55))
    atlas = load_city_atlas(ROOT)
    metrics = city_frame_metrics(atlas)
    anchor = placement.get("anchor_city_grid", [1, 1])
    anchor_x = float(anchor[0]) * float(metrics["frame_w"])
    anchor_y = float(anchor[1]) * float(metrics["frame_h"])
    inputs = load_simulation_inputs(ROOT)
    frame = simulate_city_at_time(ROOT, str(cfg.get("citizen_runtime", {}).get("sample_clock_on_start", "08:00")), inputs=inputs)
    node_index = build_node_index(inputs)

    W, H = 1800, 1000
    img = Image.new("RGB", (W, H), (2, 9, 13))
    draw = ImageDraw.Draw(img, "RGBA")
    font = ImageFont.load_default()

    def sx(x: float) -> float:
        return W / 2 + ((x - anchor_x) * scale) * 0.78

    def sy(y: float) -> float:
        return H / 2 - ((y - anchor_y) * scale) * 0.78

    # Actual HoloVerse origin, where the Central Core is anchored.
    draw.ellipse((W/2-45, H/2-45, W/2+45, H/2+45), outline=(255, 80, 100, 190), width=3)
    draw.line((W/2-55, H/2, W/2+55, H/2), fill=(255, 80, 100, 175), width=2)
    draw.line((W/2, H/2-55, W/2, H/2+55), fill=(255, 80, 100, 175), width=2)
    draw.text((W/2+52, H/2-12), "HoloVerse Origin / Portal Hub", fill=(255, 185, 195, 230), font=font)

    palette = {
        "central_core_civic_ring": (90, 220, 255, 150),
        "residential_alpha": (90, 255, 160, 145),
        "market_crossing": (255, 85, 230, 145),
        "industrial_yard_alpha": (170, 255, 90, 145),
        "harbor_grid_beta": (80, 215, 255, 145),
        "archive_quarter_gamma": (195, 120, 255, 145),
        "security_gate": (80, 255, 95, 145),
        "civic_commons_delta": (120, 235, 255, 145),
        "glitched_quarantine_epsilon": (255, 70, 65, 150),
    }

    for entry in atlas.get("towns", []):
        if not isinstance(entry, dict):
            continue
        town_id = str(entry.get("town_id"))
        grid = entry.get("city_grid", [0, 0])
        ox = float(grid[0]) * float(metrics["frame_w"])
        oy = float(grid[1]) * float(metrics["frame_h"])
        bounds = town_bounds(load_town(town_id, ROOT))
        x0, y0 = sx(ox + bounds.min_x), sy(oy + bounds.max_y)
        x1, y1 = sx(ox + bounds.max_x), sy(oy + bounds.min_y)
        c = palette.get(town_id, (140, 220, 255, 140))
        draw.rectangle((x0, y0, x1, y1), outline=c, width=3)
        draw.text((x0 + 6, y0 + 6), town_id.replace("_", " ").title(), fill=(220, 250, 255, 225), font=font)
        town = load_town(town_id, ROOT)
        for block in town.get("town_blocks", []):
            if not isinstance(block, dict):
                continue
            gx, gy = block.get("grid", [0, 0])
            size = block.get("size", [1, 1])
            mass = block.get("structure_massing_profile") if isinstance(block.get("structure_massing_profile"), dict) else {}
            height = str(mass.get("height_class") or block.get("height_class") or "low")
            lw = 2 if height == "tall" else 1
            local_x = ox + (float(gx) - 4.5) * 64
            local_y = oy + (3.5 - float(gy)) * 64
            halfx = float(size[0]) * 64 * 0.27
            halfy = float(size[1]) * 64 * 0.27
            alpha = 98 if height == "low" else 135 if height == "mid" else 185
            draw.rectangle((sx(local_x-halfx), sy(local_y+halfy), sx(local_x+halfx), sy(local_y-halfy)), outline=(c[0], c[1], c[2], alpha), width=lw)

    # Live citizens as small in-world avatars at resolved schedule nodes.
    for cid, citizen in frame.get("citizens", {}).items():
        node = node_index.get(citizen.get("resolved_node"))
        if node is None:
            continue
        x, y = _node_grid_to_city_render_xy(ROOT, node.town_id, node.grid)
        px, py = sx(x), sy(y)
        act = str(citizen.get("activity_id", ""))
        color = (80, 240, 255, 230)
        if "work" in act:
            color = (95, 255, 105, 235)
        elif "meal" in act or "social" in act or "friend" in act:
            color = (255, 95, 235, 235)
        elif "home" in act or "sleep" in act or citizen.get("location_mode") == "private_home_hidden":
            color = (125, 165, 255, 190)
        draw.ellipse((px-5, py-5, px+5, py+5), fill=color)
        draw.line((px, py-10, px, py+10), fill=color, width=1)

    draw.rectangle((18, 18, 720, 132), fill=(0, 0, 0, 165), outline=(80, 240, 255, 210), width=2)
    draw.text((32, 32), "HOLOUTOPIA PASS 22 // 3D WORLD INTEGRATION", fill=(215, 255, 255, 245), font=font)
    draw.text((32, 54), f"{summary['town_count']} districts // {summary['neighborhood_count']} neighborhoods // {summary['citizen_count']} live citizens", fill=(220, 255, 255, 225), font=font)
    draw.text((32, 76), f"Parent preference: {' > '.join(summary['parent_preference'])} // root: {summary['root_node_name']}", fill=(220, 255, 255, 225), font=font)
    draw.text((32, 98), f"Central Core anchored at HoloVerse origin // scale {summary['placement_scale']} // sample {frame.get('clock')}", fill=(255, 235, 130, 230), font=font)
    draw.text((32, 118), "No collision, no route edits, hidden during native dimensions/HoloCore/HoloSpace", fill=(255, 235, 130, 220), font=font)

    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
