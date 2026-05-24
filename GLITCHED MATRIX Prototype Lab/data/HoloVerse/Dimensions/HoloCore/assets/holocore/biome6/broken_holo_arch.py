from __future__ import annotations

import math
from assets.holocore_object_primitives import line_segments, make_root, ring, set_ambient_motion

SURFACE_OBJECT = {
    "id": "broken_holo_arch",
    "weight": 0.58,
    "hierarchy": 2,
    "min_distance_from_hub": 760.0,
    "max_slope": 0.62,
    "silhouette": "curved_broken_arch",
    "local_density": 0.55,
}


def build(parent, x, y, z, rng, metadata):
    root = make_root(parent, "broken_holo_arch", x, y, z)
    root.setH(rng.uniform(0, 360))
    radius = rng.uniform(9.0, 14.0)
    height = rng.uniform(20.0, 31.0)
    segments = []
    last = None
    for i in range(15):
        t = i / 14.0
        if 0.48 < t < 0.60 and rng.random() < 0.85:
            last = None
            continue
        angle = math.pi * t
        p = ((t - 0.5) * radius * 2.0, 0.0, math.sin(angle) * height)
        if last is not None:
            segments.append((last, p))
        last = p
    segments.extend([((-radius, 0, 0), (-radius, 0, height * 0.28)), ((radius, 0, 0), (radius, 0, height * 0.22))])
    line_segments(root, "arch_curve", segments, (1.00, 0.72, 0.32, 0.54), 1.8)
    ring(root, "arch_projection_shadow", radius * 0.64, 0.2, (0.22, 0.90, 1.00, 0.20), 1.0, 22, x_scale=1.7, y_scale=0.28)
    return set_ambient_motion(root, rng.random() * math.tau, amp=0.45, rate=0.06, kind="signal_pulse", pulse_amp=0.075, scale_amp=0.008)
