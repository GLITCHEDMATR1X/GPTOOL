from __future__ import annotations

import math
from assets.holocore_object_primitives import line_segments, make_root, set_ambient_motion, soft_polyline_loop, tapered_cage

SURFACE_OBJECT = {
    "id": "storm_current_pylon",
    "weight": 0.95,
    "hierarchy": 0,
    "min_distance_from_hub": 640.0,
    "max_slope": 0.72,
    "local_density": 0.82,
    "silhouette": "tapered_electric_coral",
}


def build(parent, x, y, z, rng, metadata):
    root = make_root(parent, "storm_current_pylon", x, y, z)
    root.setH(rng.uniform(0, 360))
    height = rng.uniform(24.0, 42.0)
    lean_x = rng.uniform(-1.2, 1.2)
    lean_y = rng.uniform(-1.2, 1.2)
    tapered_cage(root, "pylon_organic_core", rng.uniform(2.6, 4.0), height, (0.22, 0.56, 1.00, 0.60), top_radius=rng.uniform(0.65, 1.5), sides=rng.randint(6, 8), thickness=1.5, lean_x=lean_x, lean_y=lean_y)
    soft_polyline_loop(root, "lower_current_soft_ring", rng.uniform(5.5, 7.8), rng.uniform(2.2, 3.8), height * 0.35, (0.30, 0.70, 1.00, 0.42), thickness=1.15, points=18)
    soft_polyline_loop(root, "upper_current_soft_ring", rng.uniform(7.0, 10.5), rng.uniform(2.6, 4.5), height * 0.72, (1.00, 0.10, 0.52, 0.36), thickness=1.25, points=22)
    bolts = []
    for idx in range(4):
        a = math.tau * idx / 4.0 + rng.uniform(-0.25, 0.25)
        start = (math.cos(a) * 1.7, math.sin(a) * 1.7, height * rng.uniform(0.18, 0.35))
        mid = (math.cos(a + 0.24) * rng.uniform(5.0, 7.5), math.sin(a + 0.24) * rng.uniform(5.0, 7.5), height * rng.uniform(0.45, 0.62))
        end = (math.cos(a - 0.18) * rng.uniform(3.0, 5.5), math.sin(a - 0.18) * rng.uniform(3.0, 5.5), height * rng.uniform(0.74, 0.92))
        bolts.append((start, mid))
        bolts.append((mid, end))
    line_segments(root, "electric_bolts", bolts, (0.62, 0.88, 1.00, 0.56), 1.1)
    return set_ambient_motion(root, rng.random() * math.tau, amp=1.0, rate=0.18, kind="electric_flicker", pulse_amp=0.105)
