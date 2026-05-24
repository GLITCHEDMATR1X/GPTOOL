"""Validate HoloUtopia residential building foundations and visual-line sanity."""
from __future__ import annotations
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


def main() -> int:
    root = _find_holoverse_root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from holoutopia_town_blocks import HoloUtopiaTownError, load_neighborhood
    try:
        neighborhood = load_neighborhood("residential_alpha_neighborhood_01", root)
        total = 0
        clean_lines = 0
        for lot in neighborhood.get("lots", []):
            if not isinstance(lot, dict):
                continue
            total += 1
            lid = str(lot.get("id"))
            footprint = lot.get("footprint", {})
            foundation = lot.get("foundation_profile", {})
            profile = lot.get("building_profile", {})
            fs = footprint.get("size_blocks", [0, 0])
            ps = foundation.get("pad_size_blocks", [0, 0])
            if float(ps[0]) < float(fs[0]) or float(ps[1]) < float(fs[1]):
                raise HoloUtopiaTownError(f"{lid}: foundation smaller than footprint")
            if foundation.get("anchor_rule") != "building_footprint_centered_on_foundation":
                raise HoloUtopiaTownError(f"{lid}: foundation anchor rule is not centered")
            line_policy = profile.get("line_policy", {})
            if line_policy.get("draw_roof_cross_braces") is not False:
                raise HoloUtopiaTownError(f"{lid}: roof cross braces must be disabled for Pass 12")
            if line_policy.get("draw_unexplained_diagonals") is not False:
                raise HoloUtopiaTownError(f"{lid}: unexplained diagonals must be disabled")
            if not foundation.get("cover_underlay_grid", False):
                raise HoloUtopiaTownError(f"{lid}: foundation must cover underlay grid")
            clean_lines += 1
        print(f"OK foundations: {clean_lines}/{total} lots aligned, grid-covering, no arbitrary roof diagonals")
        return 0
    except HoloUtopiaTownError as exc:
        print(f"FOUNDATION VALIDATION FAILED: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
