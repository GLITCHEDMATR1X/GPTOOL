from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from holoutopia_citizen_simulation import DEFAULT_SAMPLE_TIMES, load_simulation_inputs, simulate_city_day


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


def _activity_color(activity: str) -> tuple[int, int, int]:
    return {
        "wake_up": (95, 170, 255),
        "commute": (255, 225, 105),
        "work_shift": (90, 230, 180),
        "meal_break": (255, 160, 90),
        "hobby": (220, 120, 255),
        "return_home": (150, 170, 255),
        "danger_override": (255, 80, 90),
    }.get(activity, (210, 210, 210))


def render_preview(out_path: Path, sample_times: list[str], danger: bool = False) -> Path:
    from PIL import Image, ImageDraw

    inputs = load_simulation_inputs(ROOT)
    sim = simulate_city_day(ROOT, sample_times, danger_state=danger)
    atlas = inputs["city_atlas"]
    frame_w, frame_h = atlas.get("canonical_grid_size", [10, 8])
    gap = int(atlas.get("district_gap_blocks", 2))
    block = int(atlas.get("block_size", 64))
    city_w = (3 * frame_w + 2 * gap) * block
    city_h = (3 * frame_h + 2 * gap) * block
    panel_w, panel_h = 430, 360
    margin = 34
    cols = min(3, max(1, len(sample_times)))
    rows = (len(sample_times) + cols - 1) // cols
    header = 86
    legend_h = 62
    img = Image.new("RGB", (cols * panel_w + margin * 2, rows * panel_h + header + legend_h), (8, 14, 18))
    draw = ImageDraw.Draw(img)
    title_font = _load_font(21)
    font = _load_font(13)
    small_font = _load_font(11)
    draw.text((margin, 20), "HoloUtopia Citizen Schedule Runner Preview", fill=(220, 245, 255), font=title_font)
    draw.text((margin, 50), "Each dot is a scheduled citizen position. Private home activity stays hidden until highlighted in-game.", fill=(150, 180, 190), font=font)

    sx = (panel_w - 84) / city_w
    sy = (panel_h - 92) / city_h
    scale = min(sx, sy)

    towns_by_id = {str(t["town_id"]): t for t in atlas.get("towns", []) if isinstance(t, dict)}
    town_names = {tid: tid.replace("_", " ").title() for tid in towns_by_id}

    for idx, frame in enumerate(sim["frames"]):
        col = idx % cols
        row = idx // cols
        x0 = margin + col * panel_w
        y0 = header + row * panel_h
        draw.rectangle((x0 + 12, y0 + 8, x0 + panel_w - 12, y0 + panel_h - 14), outline=(35, 95, 110), fill=(4, 10, 12))
        draw.text((x0 + 24, y0 + 18), f"{frame['clock']}  " + ("DANGER" if danger else "normal"), fill=(220, 245, 255), font=font)
        ox = x0 + 42
        oy = y0 + 54
        # district frames
        for town_id, town in towns_by_id.items():
            gx, gy = town.get("city_grid", [0, 0])
            dx = ox + gx * (frame_w + gap) * block * scale
            dy = oy + (2 - gy) * (frame_h + gap) * block * scale
            dw = frame_w * block * scale
            dh = frame_h * block * scale
            role = str(town.get("role", ""))
            outline = (40, 110, 130)
            if "glitched" in role:
                outline = (160, 70, 180)
            elif "security" in role or "controlled" in role:
                outline = (120, 160, 70)
            elif "market" in role:
                outline = (190, 140, 60)
            elif "harbor" in role:
                outline = (60, 155, 200)
            draw.rectangle((dx, dy, dx + dw, dy + dh), outline=outline)
            label = town_id.replace("_", " ").split()[0].title()
            draw.text((dx + 3, dy + 3), label, fill=(95, 130, 140), font=small_font)
        # citizen points
        for state in frame.get("citizens", {}).values():
            px = float(state["position"]["x"])
            py = float(state["position"]["y"])
            cx = ox + px * scale
            cy = oy + (city_h - py) * scale
            color = _activity_color(str(state.get("activity_id")))
            r = 2 if state.get("location_mode") == "private_home_hidden" else 3
            draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=color)
        summary = ", ".join(f"{k}:{v}" for k, v in sorted(frame.get("by_activity", {}).items()))
        draw.text((x0 + 24, y0 + panel_h - 44), summary[:72], fill=(145, 180, 185), font=small_font)
        draw.text((x0 + 24, y0 + panel_h - 28), f"citizens {frame['citizen_count']} | hidden homes {frame['private_home_hidden']}", fill=(145, 180, 185), font=small_font)

    legend_y = header + rows * panel_h + 10
    x = margin
    for activity in ("wake_up", "work_shift", "meal_break", "hobby", "return_home", "danger_override"):
        color = _activity_color(activity)
        draw.ellipse((x, legend_y + 8, x + 10, legend_y + 18), fill=color)
        draw.text((x + 16, legend_y + 5), activity.replace("_", " "), fill=(170, 200, 205), font=small_font)
        x += 132
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)
    return out_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Render a HoloUtopia citizen schedule preview image.")
    parser.add_argument("--out", default="/mnt/data/holoutopia_citizen_schedule_runner_preview.png")
    parser.add_argument("--sample-times", nargs="*", default=list(DEFAULT_SAMPLE_TIMES))
    parser.add_argument("--danger", action="store_true")
    args = parser.parse_args()
    out = render_preview(Path(args.out), [str(t) for t in args.sample_times], danger=args.danger)
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
