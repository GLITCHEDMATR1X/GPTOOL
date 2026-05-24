"""Bubble Lava Valleys drop-in object: large terrain bubble dome.

Pass 24 intent
--------------
Dimension 3 third object.  Big terrain domes that prefer open/unused ground,
avoid lava vents and other claimed flora, and give a lightweight gravitational-
lensing impression from the inside without needing expensive post-processing.

The module is defensive by design: if the current surface-placement loader calls
``create``, ``spawn``, ``build``, ``make``, ``make_object``, or ``create_object``
with a slightly different argument style, this module tries to adapt and returns
``None`` instead of crashing Dimension 3.
"""

from __future__ import annotations

import math
import random
from typing import Any, Iterable

try:
    from panda3d.core import LineSegs, NodePath, TransparencyAttrib, Vec3
except Exception:  # Allows compile/static inspection without Panda3D.
    LineSegs = None  # type: ignore[assignment]
    NodePath = None  # type: ignore[assignment]
    TransparencyAttrib = None  # type: ignore[assignment]

    class Vec3:  # type: ignore[no-redef]
        def __init__(self, x: float = 0.0, y: float = 0.0, z: float = 0.0) -> None:
            self.x = float(x)
            self.y = float(y)
            self.z = float(z)

        def __iter__(self):
            yield self.x
            yield self.y
            yield self.z


OBJECT_ID = "bubble_dome"
DIMENSION_ID = 3
BIOME_ID = "biome3"

# Hierarchy rule: Object 3 is 25% less than object 2 (bubble_weed_cluster 0.75).
SPAWN_WEIGHT = 0.5625

# Domes are large, so their claim radius is intentionally wide.  This tells the
# existing claimed-location system to keep them away from vents/weeds/spikes.
SPAWN_RADIUS = 34.0
CLAIM_RADIUS = 42.0
MIN_DISTANCE_FROM_CLAIMS = 34.0
SURFACE_ANCHORED = True
PREFERRED_OPEN_AREA = True
LOW_ANIMATION = True
PERFORMANCE_CLASS = "medium_low"
AVOID_OBJECTS = ("lava_bubble_tube", "bubble_weed_cluster", "crystal_spike_patch")

OBJECT_INFO = {
    "id": OBJECT_ID,
    "object_id": OBJECT_ID,
    "dimension": DIMENSION_ID,
    "biome": BIOME_ID,
    "spawn_weight": SPAWN_WEIGHT,
    "claim_radius": CLAIM_RADIUS,
    "min_distance_from_claims": MIN_DISTANCE_FROM_CLAIMS,
    "surface_anchored": SURFACE_ANCHORED,
    "preferred_open_area": PREFERRED_OPEN_AREA,
    "avoid": AVOID_OBJECTS,
    "performance": PERFORMANCE_CLASS,
}

# Common lower-case aliases for object registries.
object_id = OBJECT_ID
spawn_weight = SPAWN_WEIGHT
claim_radius = CLAIM_RADIUS
surface_anchored = SURFACE_ANCHORED
preferred_open_area = PREFERRED_OPEN_AREA
avoid_objects = AVOID_OBJECTS


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def _safe_seed(value: Any) -> int:
    try:
        if value is None:
            return 0
        return int(float(value) * 10007) & 0x7FFFFFFF
    except Exception:
        try:
            return hash(str(value)) & 0x7FFFFFFF
        except Exception:
            return 0


def _vec3_from_any(value: Any, default_z: float = 0.0) -> Vec3:
    if value is None:
        return Vec3(0.0, 0.0, default_z)
    try:
        return Vec3(float(value.x), float(value.y), float(value.z))
    except Exception:
        pass
    if isinstance(value, dict):
        return Vec3(
            _safe_float(value.get("x"), 0.0),
            _safe_float(value.get("y"), 0.0),
            _safe_float(value.get("z"), default_z),
        )
    try:
        seq = list(value)
        if len(seq) >= 3:
            return Vec3(_safe_float(seq[0]), _safe_float(seq[1]), _safe_float(seq[2]))
        if len(seq) >= 2:
            return Vec3(_safe_float(seq[0]), _safe_float(seq[1]), default_z)
    except Exception:
        pass
    return Vec3(0.0, 0.0, default_z)


def _safe_attach(parent: Any, name: str) -> Any:
    if parent is None or not hasattr(parent, "attachNewNode"):
        return None
    try:
        return parent.attachNewNode(name)
    except Exception:
        return None


def _set_alpha_blend(node: Any, alpha: float | None = None) -> None:
    if node is None:
        return
    try:
        if TransparencyAttrib is not None:
            node.setTransparency(TransparencyAttrib.M_alpha)
    except Exception:
        pass
    try:
        node.setLightOff(True)
    except Exception:
        pass
    try:
        node.setBin("transparent", 35)
    except Exception:
        pass
    if alpha is not None:
        try:
            color = node.getColor()
            node.setColor(color.x, color.y, color.z, alpha)
        except Exception:
            pass


def _line_node(name: str, color: tuple[float, float, float, float], thickness: float) -> Any:
    if LineSegs is None:
        return None
    segs = LineSegs(name)
    try:
        segs.setThickness(thickness)
    except Exception:
        pass
    try:
        segs.setColor(*color)
    except Exception:
        pass
    return segs


def _draw_polyline(parent: Any, name: str, points: Iterable[tuple[float, float, float]], color: tuple[float, float, float, float], thickness: float = 1.0) -> Any:
    segs = _line_node(name, color, thickness)
    if segs is None or parent is None:
        return None
    first = True
    for point in points:
        if first:
            segs.moveTo(*point)
            first = False
        else:
            segs.drawTo(*point)
    try:
        node = parent.attachNewNode(segs.create())
        _set_alpha_blend(node)
        return node
    except Exception:
        return None


def _ring_points(radius: float, z: float, segments: int, y_scale: float = 1.0, wobble: float = 0.0) -> list[tuple[float, float, float]]:
    pts: list[tuple[float, float, float]] = []
    segments = max(12, int(segments))
    for idx in range(segments + 1):
        ang = (idx / float(segments)) * math.tau
        r = radius * (1.0 + wobble * math.sin(ang * 3.0 + z * 0.07))
        pts.append((math.cos(ang) * r, math.sin(ang) * r * y_scale, z))
    return pts


def _dome_arc_points(radius: float, angle: float, segments: int, wobble: float = 0.0) -> list[tuple[float, float, float]]:
    pts: list[tuple[float, float, float]] = []
    segments = max(8, int(segments))
    ca = math.cos(angle)
    sa = math.sin(angle)
    for idx in range(segments + 1):
        t = (idx / float(segments)) * math.pi
        local_r = math.sin(t) * radius * (1.0 + wobble * math.sin(t * 4.0 + angle))
        z = math.cos(t) * radius
        # Convert top-to-ground hemisphere: start at apex, end at opposite ground
        if z < 0.0:
            z = 0.0
        pts.append((ca * local_r, sa * local_r, z))
    return pts


def _make_dome_geometry(root: Any, radius: float, rng: random.Random) -> None:
    """Build cheap line/ring geometry for a large bubble shell."""
    shell_color = (0.45, 0.92, 1.0, 0.34)
    rim_color = (1.0, 0.44, 0.18, 0.52)
    lens_color = (0.85, 0.30, 1.0, 0.22)
    shimmer_color = (1.0, 0.82, 0.34, 0.18)

    # Ground rim and a few latitude rings.  These make the dome readable from far
    # away without adding transparent sphere fill cost.
    _draw_polyline(root, "bubble_dome_ground_rim", _ring_points(radius, 0.08, 40, wobble=0.015), rim_color, 1.65)
    for i, frac in enumerate((0.22, 0.42, 0.62, 0.80)):
        z = radius * frac
        ring_r = max(0.1, radius * math.sqrt(max(0.0, 1.0 - frac * frac)))
        _draw_polyline(
            root,
            f"bubble_dome_latitude_{i}",
            _ring_points(ring_r, z, 36, y_scale=0.96, wobble=0.025),
            shell_color,
            1.0,
        )

    # Vertical arcs.  Sparse enough to remain cheap, numerous enough to sell the
    # dome shape from a distance.
    for i in range(8):
        angle = (i / 8.0) * math.tau
        _draw_polyline(root, f"bubble_dome_arc_{i}", _dome_arc_points(radius, angle, 20, wobble=0.018), shell_color, 1.05)

    # Interior lensing ribbons: when the player steps inside, these curved lines
    # surround the camera and read as warped gravity/light without postprocess.
    for i in range(5):
        frac = 0.18 + i * 0.145
        z = radius * (0.28 + i * 0.10)
        ring_r = radius * (0.32 + i * 0.10)
        pts = []
        for idx in range(44):
            t = idx / 43.0
            ang = t * math.tau * (0.78 + i * 0.09) + i * 0.7
            wave = math.sin(t * math.tau * 2.0 + i) * radius * 0.035
            pts.append((math.cos(ang) * (ring_r + wave), math.sin(ang) * (ring_r * 0.62), z + math.sin(ang * 1.7) * radius * 0.055))
        _draw_polyline(root, f"bubble_dome_inner_lens_ribbon_{i}", pts, lens_color if i % 2 else shimmer_color, 1.15)

    # A small bright apex sparkle.  Static, no per-object task.
    sparkle = radius * 0.055
    apex_z = radius * 1.01
    _draw_polyline(
        root,
        "bubble_dome_apex_spark_x",
        [(-sparkle, 0, apex_z), (sparkle, 0, apex_z), (0, -sparkle, apex_z), (0, sparkle, apex_z)],
        (1.0, 0.92, 0.66, 0.55),
        1.3,
    )


def _extract_parent(args: tuple[Any, ...], kwargs: dict[str, Any]) -> Any:
    for key in ("parent", "root", "render", "chunk", "chunk_node", "node", "surface_parent"):
        value = kwargs.get(key)
        if value is not None and hasattr(value, "attachNewNode"):
            return value
    for item in args:
        if hasattr(item, "attachNewNode"):
            return item
    return None


def _extract_position(args: tuple[Any, ...], kwargs: dict[str, Any]) -> Vec3:
    for key in ("pos", "position", "location", "point", "surface_point"):
        if key in kwargs:
            return _vec3_from_any(kwargs.get(key))
    if all(k in kwargs for k in ("x", "y")):
        return Vec3(_safe_float(kwargs.get("x")), _safe_float(kwargs.get("y")), _safe_float(kwargs.get("z")))
    for item in args:
        # Skip NodePaths; many NodePaths are iterable-ish in odd ways.
        if hasattr(item, "attachNewNode"):
            continue
        try:
            if hasattr(item, "x") and hasattr(item, "y"):
                return _vec3_from_any(item)
        except Exception:
            pass
        if isinstance(item, (tuple, list, dict)):
            return _vec3_from_any(item)
    return Vec3(0.0, 0.0, 0.0)


def _extract_radius(pos: Vec3, kwargs: dict[str, Any]) -> float:
    explicit = kwargs.get("radius") or kwargs.get("scale") or kwargs.get("dome_radius")
    if explicit is not None:
        return max(18.0, min(58.0, _safe_float(explicit, 32.0)))
    seed = _safe_seed(pos.x * 0.31 + pos.y * 0.17 + pos.z * 0.11)
    rng = random.Random(seed)
    return rng.uniform(24.0, 42.0)


def create(*args: Any, **kwargs: Any) -> Any:
    """Create a large terrain bubble dome.

    Supported call examples:
    - create(parent, pos)
    - create(parent=chunk_node, position=Vec3(...))
    - create(render, x=..., y=..., z=...)
    - create(base=..., parent=..., position=...)
    """
    try:
        parent = _extract_parent(args, kwargs)
        if parent is None:
            return None
        pos = _extract_position(args, kwargs)
        radius = _extract_radius(pos, kwargs)
        rng = random.Random(_safe_seed(pos.x * 13.0 + pos.y * 7.0 + radius))

        root = _safe_attach(parent, OBJECT_ID)
        if root is None:
            return None
        try:
            root.setPos(pos.x, pos.y, pos.z + 0.05)
        except Exception:
            pass
        try:
            root.setPythonTag("object_id", OBJECT_ID)
            root.setPythonTag("dimension_id", DIMENSION_ID)
            root.setPythonTag("bubble_dome_radius", radius)
            root.setPythonTag("pass24_lensing", True)
            root.setPythonTag("claim_radius", CLAIM_RADIUS)
        except Exception:
            pass

        _set_alpha_blend(root)
        _make_dome_geometry(root, radius, rng)
        return root
    except Exception:
        # Dimension switching must never crash because of an optional biome prop.
        return None


# Factory aliases used by different drop-in loaders.
def spawn(*args: Any, **kwargs: Any) -> Any:
    return create(*args, **kwargs)


def build(*args: Any, **kwargs: Any) -> Any:
    return create(*args, **kwargs)


def make(*args: Any, **kwargs: Any) -> Any:
    return create(*args, **kwargs)


def make_object(*args: Any, **kwargs: Any) -> Any:
    return create(*args, **kwargs)


def create_object(*args: Any, **kwargs: Any) -> Any:
    return create(*args, **kwargs)


def get_spawn_metadata() -> dict[str, Any]:
    return dict(OBJECT_INFO)


def should_spawn_at(*args: Any, **kwargs: Any) -> bool:
    """Optional hook for loaders that ask objects to validate placement.

    Avoids claimed/occupied areas when the loader passes known claims as dicts,
    tuples, or objects with x/y/radius fields.  If no claim data is supplied,
    return True and let the normal loader claim system handle it.
    """
    try:
        pos = _extract_position(args, kwargs)
        claims = kwargs.get("claims") or kwargs.get("claimed_locations") or kwargs.get("occupied") or []
        for claim in claims:
            cpos = _vec3_from_any(claim)
            cr = CLAIM_RADIUS
            if isinstance(claim, dict):
                cr = _safe_float(claim.get("radius") or claim.get("claim_radius"), CLAIM_RADIUS)
            else:
                cr = _safe_float(getattr(claim, "radius", getattr(claim, "claim_radius", CLAIM_RADIUS)), CLAIM_RADIUS)
            dx = pos.x - cpos.x
            dy = pos.y - cpos.y
            if (dx * dx + dy * dy) ** 0.5 < (MIN_DISTANCE_FROM_CLAIMS + cr * 0.25):
                return False
        return True
    except Exception:
        return True
