"""Render an offscreen Panda3D preview for authored HoloUtopia town/city data."""
from __future__ import annotations
import argparse, sys
from pathlib import Path


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render an offscreen Panda3D HoloUtopia preview.")
    parser.add_argument("--town", default="central_core_civic_ring")
    parser.add_argument("--neighborhood", default=None, help="Render a detailed neighborhood overlay instead of a plain town.")
    parser.add_argument("--city", action="store_true", help="Render the full city atlas instead of one town.")
    parser.add_argument("--city-neighborhoods", action="store_true", help="Render all authored neighborhoods placed in the city atlas.")
    parser.add_argument("--highlight-interior-lot", default=None, help="Render a highlight-only interior cutaway for the selected lot.")
    parser.add_argument("--out", default="holoutopia_panda_preview.png")
    parser.add_argument("--size", type=int, default=1400)
    args = parser.parse_args(argv)
    root = _find_holoverse_root()
    sys.path.insert(0, str(root)) if str(root) not in sys.path else None
    try:
        from panda3d.core import Filename, loadPrcFileData, Vec3
        loadPrcFileData("", "\n".join(["window-type offscreen", "load-display p3tinydisplay", f"win-size {max(512, int(args.size))} {max(512, int(args.size))}", "audio-library-name null", "show-frame-rate-meter 0", "sync-video 0"]))
        from direct.showbase.ShowBase import ShowBase
    except Exception as exc:
        print(f"Panda3D is required for this preview: {exc}")
        return 2
    from holoutopia_town_blocks import attach_holoutopia_city, attach_holoutopia_city_neighborhoods, attach_holoutopia_highlighted_interior, attach_holoutopia_neighborhood, attach_holoutopia_town, city_atlas_bounds, load_city_atlas, load_neighborhood, load_town, town_bounds
    base = ShowBase(windowType="offscreen")
    base.win.setClearColor((0.002, 0.008, 0.012, 1.0))
    if args.highlight_interior_lot:
        neighborhood = load_neighborhood(args.neighborhood or "residential_alpha_neighborhood_01", root)
        town = load_town(str(neighborhood.get("town_id") or args.town), holoverse_root=root)
        bounds = town_bounds(town)
        attach_holoutopia_highlighted_interior(base.render, root, args.neighborhood or "residential_alpha_neighborhood_01", args.highlight_interior_lot, z=0.08)
    elif args.city_neighborhoods:
        atlas = load_city_atlas(root)
        bounds = city_atlas_bounds(atlas)
        attach_holoutopia_city_neighborhoods(base.render, root, z=0.08)
    elif args.city:
        atlas = load_city_atlas(root)
        bounds = city_atlas_bounds(atlas)
        attach_holoutopia_city(base.render, root, z=0.08)
    elif args.neighborhood:
        neighborhood = load_neighborhood(args.neighborhood, root)
        town = load_town(str(neighborhood.get("town_id") or args.town), holoverse_root=root)
        bounds = town_bounds(town)
        attach_holoutopia_neighborhood(base.render, root, args.neighborhood, z=0.08)
    else:
        town = load_town(args.town, holoverse_root=root)
        bounds = town_bounds(town)
        attach_holoutopia_town(base.render, root, args.town, z=0.08)
    diagonal = max(bounds.width, bounds.height, 1.0)
    center_x = (bounds.min_x + bounds.max_x) * 0.5
    center_y = (bounds.min_y + bounds.max_y) * 0.5
    base.cam.setPos(center_x, center_y - diagonal * 1.10, diagonal * 0.94)
    base.cam.lookAt(Vec3(center_x, center_y, 0))
    base.camLens.setFov(42)
    base.camLens.setNearFar(1.0, diagonal * 8.0)
    for _ in range(4):
        base.graphicsEngine.renderFrame()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    ok = base.win.saveScreenshot(Filename.fromOsSpecific(str(out)))
    base.destroy()
    if not ok:
        print(f"Could not save screenshot: {out}")
        return 2
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
