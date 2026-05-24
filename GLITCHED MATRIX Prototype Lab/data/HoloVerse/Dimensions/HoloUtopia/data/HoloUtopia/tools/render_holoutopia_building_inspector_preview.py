from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from holoutopia_building_inspector import DEFAULT_HIGHLIGHT_ID, build_highlight_index, inspect_building


def _draw_preview(output: Path, highlight_id: str, clock: str) -> None:
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle

    index = build_highlight_index(ROOT, clock=clock)
    panel = inspect_building(ROOT, highlight_id, clock=clock)
    record = panel["building"]
    records = index["records"]

    xs = [float(r.get("world_position", {}).get("x", 0.0)) for r in records.values()]
    ys = [float(r.get("world_position", {}).get("y", 0.0)) for r in records.values()]
    min_x, max_x = min(xs) - 120, max(xs) + 120
    min_y, max_y = min(ys) - 120, max(ys) + 120

    fig, ax = plt.subplots(figsize=(13.66, 7.68), dpi=100)
    fig.patch.set_facecolor("#071011")
    ax.set_facecolor("#071011")

    # Draw all inspectable records as calm exterior masses. Residential lots sit above town blocks.
    for rec in records.values():
        pos = rec.get("world_position", {})
        x = float(pos.get("x", 0.0))
        y = float(pos.get("y", 0.0))
        kind = rec.get("highlight_kind")
        mass = rec.get("massing", {}) if isinstance(rec.get("massing"), dict) else {}
        floors = max(1, int(mass.get("floor_count", 1) or 1))
        if kind == "district_block":
            size = 24 + min(18, floors * 2)
            color = "#2ad4ff"
            alpha = 0.18
            lw = 0.55
        else:
            size = 18 + min(24, floors * 3)
            color = "#f7f1a1"
            alpha = 0.36
            lw = 0.9
        ax.add_patch(Rectangle((x - size / 2, y - size / 2), size, size, fill=True, facecolor=color, edgecolor=color, alpha=alpha, linewidth=lw))

    hp = record.get("world_position", {})
    hx = float(hp.get("x", 0.0))
    hy = float(hp.get("y", 0.0))
    ax.add_patch(Rectangle((hx - 44, hy - 44), 88, 88, fill=False, edgecolor="#ff4de8", linewidth=3.0))
    ax.scatter([hx], [hy], s=160, marker="x", c="#ff4de8", linewidths=2.5)

    # Active citizens in the highlighted building.
    active = record.get("active_citizens", [])
    for i, citizen in enumerate(active[:10]):
        ax.scatter([hx + (i % 5 - 2) * 12], [hy - 66 - (i // 5) * 12], s=35, c="#7cff7c", edgecolors="#0d170d", linewidths=0.5)

    ax.set_xlim(min_x, max_x)
    ax.set_ylim(min_y, max_y)
    ax.set_aspect("equal", adjustable="box")
    ax.grid(True, linewidth=0.35, alpha=0.22)
    ax.tick_params(colors="#5deaff", labelsize=7)
    for spine in ax.spines.values():
        spine.set_color("#1d6775")

    panel_lines = panel.get("panel_lines", [])
    text = "\n".join(panel_lines[:9])
    ax.text(0.015, 0.985, f"HoloUtopia Building Inspector // {clock}\n{text}", transform=ax.transAxes, va="top", ha="left", color="#eaffff", fontsize=9,
            bbox={"boxstyle": "round,pad=0.55", "facecolor": "#020708", "edgecolor": "#00e5ff", "alpha": 0.88})
    ax.text(0.985, 0.025, f"{index['totals']['highlight_records']} inspectable records • {index['totals']['residential_capacity']} total capacity", transform=ax.transAxes,
            va="bottom", ha="right", color="#8ff6ff", fontsize=8)

    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, bbox_inches="tight", pad_inches=0.08)
    plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser(description="Render a HoloUtopia building-inspector preview.")
    parser.add_argument("--highlight", default=DEFAULT_HIGHLIGHT_ID)
    parser.add_argument("--clock", default="12:00")
    parser.add_argument("--output", default=str(ROOT.parent.parent / "holoutopia_building_inspector_preview.png"))
    args = parser.parse_args()
    _draw_preview(Path(args.output), args.highlight, args.clock)
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
