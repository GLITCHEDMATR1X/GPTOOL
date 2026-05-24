from __future__ import annotations

import math
from assets.holocore_object_primitives import line_segments, make_root, organic_lobe, set_ambient_motion, soft_polyline_loop, wavy_stem_segments

SURFACE_OBJECT = {
    "id": "abyssal_kelp_column",
    "weight": 1.0,
    "hierarchy": 0,
    "min_distance_from_hub": 620.0,
    "max_slope": 0.82,
    "local_density": 0.92,
    "silhouette": "organic_kelp",
}


def build(parent, x, y, z, rng, metadata):
    root = make_root(parent, "abyssal_kelp_column", x, y, z)
    root.setH(rng.uniform(0.0, 360.0))
    height = rng.uniform(34.0, 58.0)
    stems = []
    stem_count = rng.randint(3, 6)
    for idx in range(stem_count):
        phase = rng.random() * math.tau
        ox = rng.uniform(-5.5, 5.5)
        oy = rng.uniform(-5.5, 5.5)
        sway = rng.uniform(2.2, 5.0)
        segments = [
            ((a[0] + ox, a[1] + oy, a[2]), (b[0] + ox, b[1] + oy, b[2]))
            for a, b in wavy_stem_segments(height * rng.uniform(0.78, 1.08), sway, 8, phase)
        ]
        stems.extend(segments)
        if idx % 2 == 0:
            frond = organic_lobe(
                root,
                f"kelp_frond_{idx}",
                rng.uniform(5.0, 8.5),
                rng.uniform(16.0, 24.0),
                (0.05, 1.00, 0.62, 0.22),
                x=ox,
                y=oy,
                z=height * rng.uniform(0.34, 0.58),
                heading=rng.uniform(0, 360),
                roll=rng.uniform(-12, 12),
            )
            frond.setPythonTag("animated_surface_object", True)
    line_segments(root, "kelp_stems", stems, (0.04, 0.92, 0.68, 0.68), 2.0)
    soft_polyline_loop(root, "kelp_crown_soft_halo", rng.uniform(5.0, 8.0), rng.uniform(1.8, 3.4), height * 0.74, (0.18, 1.00, 0.76, 0.26), thickness=1.1, points=17)
    crown = organic_lobe(
        root,
        "kelp_crown_glow_lobe",
        rng.uniform(10.0, 15.0),
        rng.uniform(11.0, 18.0),
        (0.18, 1.00, 0.76, 0.16),
        z=height * 0.62,
        heading=rng.uniform(0, 360),
        roll=rng.uniform(-16, 16),
    )
    crown.setPythonTag("animated_surface_object", True)
    return set_ambient_motion(root, rng.random() * math.tau, amp=2.4, rate=0.10)
