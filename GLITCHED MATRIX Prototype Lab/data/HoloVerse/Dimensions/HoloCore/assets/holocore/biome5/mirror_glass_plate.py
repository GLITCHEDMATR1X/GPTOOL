from __future__ import annotations

import math
from assets.holocore_object_primitives import line_segments, make_root, organic_disc, set_ambient_motion, soft_polyline_loop

SURFACE_OBJECT = {
    "id": "mirror_glass_plate",
    "weight": 1.0,
    "hierarchy": 0,
    "min_distance_from_hub": 620.0,
    "max_slope": 0.55,
    "local_density": 0.86,
    "silhouette": "organic_glass_shelf",
}


def build(parent, x, y, z, rng, metadata):
    root = make_root(parent, "mirror_glass_plate", x, y, z + 0.08)
    root.setH(rng.uniform(0, 360))
    rx = rng.uniform(10.0, 17.0)
    ry = rng.uniform(4.2, 7.8)
    organic_disc(root, "glass_tide_pool_surface", rx, ry, (0.78, 0.96, 1.00, 0.18), points=21, wobble=0.22, heading=rng.uniform(-8, 8), roll=rng.uniform(-3, 3))
    soft_polyline_loop(root, "glass_soft_edge", rx, ry, 0.09, (0.92, 1.00, 1.00, 0.58), thickness=1.2, points=21, wobble=0.22)
    cracks = []
    crack_count = rng.randint(2, 4)
    for idx in range(crack_count):
        a = rng.random() * math.tau
        start = (math.cos(a) * rx * rng.uniform(0.1, 0.28), math.sin(a) * ry * rng.uniform(0.1, 0.28), 0.11)
        mid = (math.cos(a + rng.uniform(-0.5, 0.5)) * rx * rng.uniform(0.32, 0.62), math.sin(a + rng.uniform(-0.5, 0.5)) * ry * rng.uniform(0.32, 0.62), 0.12)
        end = (math.cos(a + rng.uniform(-0.5, 0.5)) * rx * rng.uniform(0.66, 0.92), math.sin(a + rng.uniform(-0.5, 0.5)) * ry * rng.uniform(0.66, 0.92), 0.12)
        cracks.extend([(start, mid), (mid, end)])
    line_segments(root, "organic_glass_cracks", cracks, (0.92, 1.00, 1.00, 0.42), 1.0)
    if rng.random() < 0.45:
        soft_polyline_loop(root, "mirror_halo", rng.uniform(6.0, 9.2), rng.uniform(1.9, 3.2), rng.uniform(0.6, 1.2), (0.62, 0.88, 1.00, 0.22), thickness=1.0, points=20)
    return set_ambient_motion(root, rng.random() * math.tau, amp=0.7, rate=0.08, kind="signal_pulse", pulse_amp=0.085, scale_amp=0.010)
