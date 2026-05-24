from __future__ import annotations

import math
from assets.holocore_object_primitives import line_segments, make_root, set_ambient_motion, soft_polyline_loop, tapered_cage

SURFACE_OBJECT = {
    "id": "archive_pillar_ruin",
    "weight": 0.92,
    "hierarchy": 0,
    "min_distance_from_hub": 640.0,
    "max_slope": 0.70,
    "local_density": 0.76,
    "silhouette": "eroded_tapered_ruins",
}


def build(parent, x, y, z, rng, metadata):
    root = make_root(parent, "archive_pillar_ruin", x, y, z)
    root.setH(rng.uniform(0, 360))
    count = rng.randint(2, 4)
    for idx in range(count):
        angle = math.tau * idx / count + rng.uniform(-0.25, 0.25)
        radius = rng.uniform(4.0, 9.0)
        height = rng.uniform(15.0, 32.0)
        pillar = root.attachNewNode(f"pillar_{idx}")
        pillar.setPos(math.cos(angle) * radius, math.sin(angle) * radius, 0.0)
        pillar.setH(rng.uniform(0, 360))
        lean = rng.uniform(-1.3, 1.3)
        tapered_cage(
            pillar,
            "eroded_pillar_cage",
            rng.uniform(2.0, 3.2),
            height,
            (1.00, 0.78, 0.34, 0.58),
            top_radius=rng.uniform(0.8, 1.8),
            sides=rng.randint(6, 8),
            thickness=1.35,
            lean_x=math.cos(angle) * lean,
            lean_y=math.sin(angle) * lean,
        )
        if rng.random() < 0.75:
            soft_polyline_loop(pillar, "data_cap_soft_ring", rng.uniform(2.6, 4.4), rng.uniform(1.8, 3.1), height + rng.uniform(0.4, 1.1), (0.20, 0.92, 1.00, 0.42), thickness=1.0, points=15)
    floor_links = []
    for idx in range(5):
        a = rng.random() * math.tau
        b = a + rng.uniform(0.8, 1.8)
        floor_links.append(((math.cos(a) * rng.uniform(5, 11), math.sin(a) * rng.uniform(4, 9), 0.2), (math.cos(b) * rng.uniform(5, 11), math.sin(b) * rng.uniform(4, 9), 0.2)))
    line_segments(root, "broken_floor_links", floor_links, (1.00, 0.62, 0.26, 0.28), 1.0)
    return set_ambient_motion(root, rng.random() * math.tau, amp=0.55, rate=0.055, kind="signal_pulse", pulse_amp=0.070, scale_amp=0.006)
