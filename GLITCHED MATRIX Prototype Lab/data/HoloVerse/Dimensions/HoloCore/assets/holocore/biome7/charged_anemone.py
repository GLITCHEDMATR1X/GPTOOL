from __future__ import annotations

import math
from assets.holocore_object_primitives import line_segments, make_root, organic_lobe, set_ambient_motion, soft_polyline_loop

SURFACE_OBJECT = {
    "id": "charged_anemone",
    "weight": 0.80,
    "hierarchy": 1,
    "min_distance_from_hub": 700.0,
    "max_slope": 0.86,
    "local_density": 0.70,
    "silhouette": "organic_electric_anemone",
}


def build(parent, x, y, z, rng, metadata):
    root = make_root(parent, "charged_anemone", x, y, z)
    root.setH(rng.uniform(0, 360))
    soft_polyline_loop(root, "anemone_base_soft_loop", rng.uniform(4.2, 6.5), rng.uniform(2.8, 4.8), 0.25, (0.24, 0.54, 1.00, 0.35), thickness=1.2, points=17)
    segments = []
    arms = rng.randint(7, 11)
    for idx in range(arms):
        a = math.tau * idx / arms + rng.uniform(-0.18, 0.18)
        height = rng.uniform(8.0, 17.0)
        mid = (math.cos(a) * rng.uniform(1.5, 3.2), math.sin(a) * rng.uniform(1.5, 3.2), height * 0.48)
        tip = (math.cos(a) * rng.uniform(4.0, 7.0), math.sin(a) * rng.uniform(4.0, 7.0), height)
        segments.append(((0, 0, 0.4), mid))
        segments.append((mid, tip))
        if idx % 3 == 0:
            lobe = organic_lobe(root, f"charged_tip_lobe_{idx}", rng.uniform(2.0, 3.4), rng.uniform(2.4, 4.2), (1.00, 0.12, 0.52, 0.22), x=tip[0], y=tip[1], z=tip[2] - 1.2, heading=math.degrees(a), roll=rng.uniform(-20, 20))
            lobe.setPythonTag("animated_surface_object", True)
    line_segments(root, "charged_tendrils", segments, (0.45, 0.78, 1.00, 0.62), 1.35)
    return set_ambient_motion(root, rng.random() * math.tau, amp=2.2, rate=0.19, kind="electric_flicker", pulse_amp=0.090)
