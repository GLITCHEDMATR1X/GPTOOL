from __future__ import annotations

import math
from assets.holocore_object_primitives import line_segments, make_root, ring, set_ambient_motion

SURFACE_OBJECT = {
    "id": "current_ring_marker",
    "weight": 0.62,
    "hierarchy": 2,
    "min_distance_from_hub": 780.0,
    "max_slope": 0.78,
    "silhouette": "soft_current_rings",
    "local_density": 0.54,
}


def build(parent, x, y, z, rng, metadata):
    root = make_root(parent, "current_ring_marker", x, y, z)
    root.setH(rng.uniform(0, 360))
    radius = rng.uniform(8.0, 13.0)
    ring(root, "current_marker_low", radius, rng.uniform(3.0, 5.5), (0.24, 0.58, 1.00, 0.36), 1.2, 28, x_scale=1.0, y_scale=0.36)
    ring(root, "current_marker_high", radius * rng.uniform(0.56, 0.78), rng.uniform(10.0, 17.0), (1.00, 0.10, 0.52, 0.32), 1.1, 24, x_scale=1.0, y_scale=0.42)
    line_segments(root, "current_vertical_ticks", [((radius * 0.6, 0, 4), (radius * 0.6, 0, 13)), ((-radius * 0.6, 0, 4), (-radius * 0.6, 0, 13)), ((0, radius * 0.24, 5), (0, radius * 0.24, 16)), ((0, -radius * 0.24, 5), (0, -radius * 0.24, 16))], (0.72, 0.92, 1.00, 0.44), 1.0)
    return set_ambient_motion(root, rng.random() * math.tau, amp=1.15, rate=0.16, kind="orbit_spin", spin_rate=7.5, pulse_amp=0.080, scale_amp=0.006)
