from __future__ import annotations

import math
from assets.holocore_object_primitives import line_segments, make_root, organic_lobe, set_ambient_motion, soft_polyline_loop

SURFACE_OBJECT = {
    "id": "glow_frond_cluster",
    "weight": 0.82,
    "hierarchy": 1,
    "min_distance_from_hub": 660.0,
    "max_slope": 0.88,
    "local_density": 0.78,
    "silhouette": "organic_fronds",
}


def build(parent, x, y, z, rng, metadata):
    root = make_root(parent, "glow_frond_cluster", x, y, z)
    root.setH(rng.uniform(0, 360))
    soft_polyline_loop(root, "frond_base_soft_loop", rng.uniform(6.2, 9.2), rng.uniform(3.0, 5.0), 0.4, (0.06, 0.80, 0.62, 0.42), thickness=1.4, points=19)
    segments = []
    arms = rng.randint(5, 8)
    for idx in range(arms):
        angle = math.tau * idx / arms + rng.uniform(-0.25, 0.25)
        length = rng.uniform(11.0, 19.0)
        tip = (math.cos(angle) * rng.uniform(3.0, 6.0), math.sin(angle) * rng.uniform(3.0, 6.0), length)
        mid = (math.cos(angle) * rng.uniform(1.5, 3.0), math.sin(angle) * rng.uniform(1.5, 3.0), length * 0.48)
        segments.append(((0, 0, 0.5), mid))
        segments.append((mid, tip))
        lobe = organic_lobe(
            root,
            f"frond_lobe_{idx}",
            rng.uniform(3.6, 6.4),
            rng.uniform(8.0, 12.0),
            (0.12, 1.00, 0.84, 0.18),
            x=tip[0] * 0.62,
            y=tip[1] * 0.62,
            z=tip[2] * 0.34,
            heading=math.degrees(angle),
            roll=rng.uniform(-22, 22),
        )
        lobe.setPythonTag("animated_surface_object", True)
    line_segments(root, "glow_frond_lines", segments, (0.13, 1.00, 0.82, 0.62), 1.5)
    return set_ambient_motion(root, rng.random() * math.tau, amp=1.8, rate=0.13)
