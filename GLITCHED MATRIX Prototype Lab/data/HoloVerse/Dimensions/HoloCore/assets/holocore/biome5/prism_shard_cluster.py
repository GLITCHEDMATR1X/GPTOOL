from __future__ import annotations

import math
from assets.holocore_object_primitives import line_segments, make_root, organic_lobe, set_ambient_motion, tapered_cage

SURFACE_OBJECT = {
    "id": "prism_shard_cluster",
    "weight": 0.78,
    "hierarchy": 1,
    "min_distance_from_hub": 680.0,
    "max_slope": 0.78,
    "local_density": 0.72,
    "silhouette": "faceted_natural_prisms",
}


def build(parent, x, y, z, rng, metadata):
    root = make_root(parent, "prism_shard_cluster", x, y, z)
    root.setH(rng.uniform(0, 360))
    glow_segments = []
    for idx in range(rng.randint(3, 6)):
        angle = rng.random() * math.tau
        base_r = rng.uniform(1.0, 5.5)
        bx = math.cos(angle) * base_r
        by = math.sin(angle) * base_r
        height = rng.uniform(12.0, 27.0)
        lean_x = math.cos(angle + rng.uniform(-0.65, 0.65)) * rng.uniform(1.2, 3.4)
        lean_y = math.sin(angle + rng.uniform(-0.65, 0.65)) * rng.uniform(1.2, 3.4)
        shard = root.attachNewNode(f"organic_prism_{idx}")
        shard.setPos(bx, by, 0.0)
        shard.setH(rng.uniform(0, 360))
        tapered_cage(shard, "prism_faceted_cage", rng.uniform(1.6, 2.8), height, (0.84, 0.96, 1.00, 0.66), top_radius=rng.uniform(0.18, 0.55), sides=rng.randint(5, 7), thickness=1.35, lean_x=lean_x, lean_y=lean_y)
        glow = organic_lobe(root, f"prism_internal_glow_{idx}", rng.uniform(2.6, 4.8), height * rng.uniform(0.42, 0.66), (0.72, 0.86, 1.00, 0.13), x=bx * 0.9, y=by * 0.9, z=height * 0.10, heading=math.degrees(angle), roll=rng.uniform(-16, 16))
        glow.setPythonTag("animated_surface_object", True)
        glow_segments.append(((bx, by, height * 0.25), (bx + lean_x, by + lean_y, height)))
    line_segments(root, "prism_inner_rays", glow_segments, (0.64, 0.92, 1.00, 0.30), 0.9)
    return set_ambient_motion(root, rng.random() * math.tau, amp=0.9, rate=0.09, kind="signal_pulse", pulse_amp=0.095, scale_amp=0.012)
