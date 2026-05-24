"""Validate city world-atlas, skyline, core clarity, atlas-depth, and motif wiring."""
from __future__ import annotations

import json
import sys
from pathlib import Path


def _root() -> Path:
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        if (parent / "holoutopia_city_world_style.py").exists():
            return parent
    raise SystemExit("Could not resolve data/HoloUtopia root")


def main() -> int:
    root = _root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    import holoutopia_city_world_style as style
    if not hasattr(style, "attach_holoutopia_city_world_style"):
        raise SystemExit("missing attach_holoutopia_city_world_style")
    if not hasattr(style, "_attach_district_landmarks"):
        raise SystemExit("missing district landmark helper")
    if not hasattr(style, "_central_hub"):
        raise SystemExit("missing central hub helper")
    if not hasattr(style, "attach_holoutopia_central_core_overlay"):
        raise SystemExit("missing central core overlay attach helper")
    for helper in ("_attach_district_atlas_depth", "_attach_road_flow_nodes", "_attach_atlas_ring_nodes", "_attach_district_surface_motifs", "_attach_atlas_skyway_ribbon"):
        if not hasattr(style, helper):
            raise SystemExit(f"missing atlas depth helper: {helper}")
    bridge = root.parent / "database" / "utopia" / "runtime" / "holoutopia_runtime_bridge.json"
    data = json.loads(bridge.read_text())
    layers = data.get("render_layers", {})
    if layers.get("city_world_atlas_style") is not True:
        raise SystemExit("runtime bridge does not enable city_world_atlas_style")
    if layers.get("central_core_overlay") is not True:
        raise SystemExit("runtime bridge does not enable central_core_overlay")
    safety = data.get("safety", {})
    for key in ("city_world_atlas_style_collisionless", "central_core_visual_is_substantial_hub", "district_pads_and_global_roads_are_visual_only", "district_landmarks_are_collisionless", "district_skyline_language_visual_only", "central_core_blocks_render_as_low_plaza_pads", "central_core_hub_lifted_above_local_pads", "central_core_clearance_plate_is_visual_only", "central_core_hub_has_no_collision", "central_core_overlay_layer_after_massing", "central_core_overlay_before_citizens", "central_core_overlay_hides_local_core_clutter", "simulation_hub_activity_props_are_low_profile", "simulation_hub_activity_props_do_not_compete_with_core", "central_core_neighborhood_overlay_suppressed_in_world_atlas", "world_atlas_depth_layer_collisionless", "district_boundary_glow_visual_only", "road_node_beacons_visual_only", "world_flow_markers_not_traffic_lines", "dark_roads_still_have_no_traffic_lanes", "district_surface_motifs_visual_only", "district_surface_motifs_are_not_traffic_lines", "atlas_skyway_ribbons_collisionless", "atlas_skyway_ribbons_visual_only"):
        if safety.get(key) is not True:
            raise SystemExit(f"missing safety flag: {key}")
    from holoutopia_town_blocks import city_frame_metrics, load_city_atlas
    atlas = load_city_atlas(root)
    towns = [entry for entry in atlas.get("towns", []) if isinstance(entry, dict)]
    if len(towns) != 9:
        raise SystemExit(f"expected 9 city districts, found {len(towns)}")
    if not any(str(entry.get("town_id")) == "central_core_civic_ring" and list(entry.get("city_grid", [])) == [1, 1] for entry in towns):
        raise SystemExit("central_core_civic_ring is not the atlas center")
    metrics = city_frame_metrics(atlas)
    if metrics.get("frame_w", 0) <= 0 or metrics.get("frame_h", 0) <= 0:
        raise SystemExit("invalid city frame metrics")
    if "motifs" not in str(data.get("id") or ""):
        raise SystemExit("runtime bridge id was not advanced to motif pass")
    citizen_runtime = data.get("citizen_runtime", {})
    if citizen_runtime.get("central_core_clarity_pass") is not True:
        raise SystemExit("missing citizen_runtime.central_core_clarity_pass")
    if citizen_runtime.get("world_atlas_visual_depth_pass") is not True:
        raise SystemExit("missing citizen_runtime.world_atlas_visual_depth_pass")
    if citizen_runtime.get("district_surface_motif_pass") is not True:
        raise SystemExit("missing citizen_runtime.district_surface_motif_pass")
    if citizen_runtime.get("atlas_skyway_ribbon_pass") is not True:
        raise SystemExit("missing citizen_runtime.atlas_skyway_ribbon_pass")
    print("[OK] HoloUtopia city world-atlas + skyline + core clarity + atlas depth + motif style validated")
    print(f"[OK] districts={len(towns)} center=central_core_civic_ring frame={metrics['frame_w']:.1f}x{metrics['frame_h']:.1f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
