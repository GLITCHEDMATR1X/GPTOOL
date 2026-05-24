from __future__ import annotations

import math
from assets.holocore_object_primitives import line_segments, make_root, organic_lobe, set_ambient_motion, soft_polyline_loop

SURFACE_OBJECT = {
    "id": "data_relay_stone",
    "weight": 0.88,
    "hierarchy": 1,
    "min_distance_from_hub": 680.0,
    "max_slope": 0.82,
    "local_density": 0.64,
    "silhouette": "rounded_faceted_relay",
}


def build(parent, x, y, z, rng, metadata):
    root = make_root(parent, "data_relay_stone", x, y, z)
    root.setH(rng.uniform(0, 360))
    radius = rng.uniform(3.0, 5.5)
    height = rng.uniform(4.0, 7.5)
    points = []
    sides = rng.randint(7, 10)
    for idx in range(sides):
        a = math.tau * idx / sides
        wob = rng.uniform(0.82, 1.22)
        points.append((math.cos(a) * radius * wob, math.sin(a) * radius * rng.uniform(0.78, 1.18), 0.0))
    segments = []
    for idx, p in enumerate(points):
        q = points[(idx + 1) % len(points)]
        segments.append((p, q))
        segments.append((p, (p[0] * 0.38, p[1] * 0.38, height)))
    line_segments(root, "relay_stone_facets", segments, (1.00, 0.70, 0.30, 0.48), 1.25)
    soft_polyline_loop(root, "relay_signal_ring", radius * 1.42, radius * 0.92, height + 0.8, (0.14, 0.92, 1.00, 0.44), thickness=1.2, points=21)
    glow = organic_lobe(root, "relay_core_glow_lobe", radius * 1.9, height * 1.55, (0.15, 0.88, 1.00, 0.18), z=0.4, heading=rng.uniform(0, 360), roll=rng.uniform(-10, 10))
    glow.setPythonTag("animated_surface_object", True)
    return set_ambient_motion(root, rng.random() * math.tau, amp=0.75, rate=0.12, kind="orbit_spin", spin_rate=5.0, pulse_amp=0.090, scale_amp=0.004)
