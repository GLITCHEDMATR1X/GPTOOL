"""Bubble Lava Valleys drop-in object: bubble weed cluster.

Pass 23 hotfix version
----------------------
This version is intentionally defensive.  It supports several surface-placement
call styles, never creates its own Panda task, and returns a harmless NodePath
or None instead of raising during Dimension 3 activation.
"""

from __future__ import annotations

import math
import random
from typing import Any

try:
    from panda3d.core import LineSegs, NodePath, TransparencyAttrib, Vec3
except Exception:  # Static analysis / compile without Panda3D.
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


OBJECT_ID = "bubble_weed_cluster"
DIMENSION_ID = 3
BIOME_ID = "biome3"
SPAWN_WEIGHT = 0.75  # 25% less than lava_bubble_tube.py baseline.
SPAWN_RADIUS = 9.5
CLAIM_RADIUS = 6.5
SURFACE_ANCHORED = True
LOW_ANIMATION = True
PERFORMANCE_CLASS = "low"
PREFERRED_NEAR_OBJECT = "lava_bubble_tube"

OBJECT_INFO = {
    "id": OBJECT_ID,
    "object_id": OBJECT_ID,
    "dimension": DIMENSION_ID,
    "biome": BIOME_ID,
    "spawn_weight": SPAWN_WEIGHT,
    "claim_radius": CLAIM_RADIUS,
    "surface_anchored": SURFACE_ANCHORED,
    "near": PREFERRED_NEAR_OBJECT,
    "performance": PERFORMANCE_CLASS,
}

# Common lower-case aliases for object registries.
object_id = OBJECT_ID
spawn_weight = SPAWN_WEIGHT
claim_radius = CLAIM_RADIUS
surface_anchored = SURFACE_ANCHORED


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
        return int(float(value) * 9973) & 0x7FFFFFFF
    except Exception:
        try:
            return abs(hash(repr(value))) & 0x7FFFFFFF
        except Exception:
            return 0


def _vec3_from_any(value: Any = None, default_z: float = 0.0) -> Vec3:
    if value is None:
        return Vec3(0.0, 0.0, default_z)
    try:
        return Vec3(_safe_float(value.x), _safe_float(value.y), _safe_float(value.z, default_z))
    except Exception:
        pass
    if isinstance(value, dict):
        return Vec3(_safe_float(value.get("x", 0.0)), _safe_float(value.get("y", 0.0)), _safe_float(value.get("z", default_z)))
    try:
        seq = list(value)
        if len(seq) >= 3:
            return Vec3(_safe_float(seq[0]), _safe_float(seq[1]), _safe_float(seq[2], default_z))
        if len(seq) >= 2:
            return Vec3(_safe_float(seq[0]), _safe_float(seq[1]), default_z)
    except Exception:
        pass
    return Vec3(0.0, 0.0, default_z)


def _is_parent_candidate(value: Any) -> bool:
    return value is not None and hasattr(value, "attachNewNode")


def _make_root(parent: Any, name: str) -> Any:
    name = str(name or OBJECT_ID)
    if _is_parent_candidate(parent):
        try:
            return parent.attachNewNode(name)
        except Exception:
            pass
    # Fallback: unattached NodePath. This prevents a crash if the loader calls a
    # metadata probe without a real parent yet.
    try:
        if NodePath is not None:
            return NodePath(name)
    except Exception:
        pass
    return None


def _set_alpha_blend(node: Any) -> None:
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
        node.setDepthWrite(False)
    except Exception:
        pass


def _new_linesegs(name: str, color: tuple[float, float, float, float], thickness: float) -> Any:
    if LineSegs is None:
        return None
    try:
        segs = LineSegs(str(name))
        try:
            segs.setThickness(float(thickness))
        except Exception:
            pass
        try:
            segs.setColor(float(color[0]), float(color[1]), float(color[2]), float(color[3]))
        except Exception:
            pass
        return segs
    except Exception:
        return None


def _attach_lines(parent: Any, segs: Any) -> Any:
    if parent is None or segs is None:
        return None
    try:
        node = parent.attachNewNode(segs.create())
        _set_alpha_blend(node)
        return node
    except Exception:
        return None


def _draw_soft_ring(
    parent: Any,
    name: str,
    radius: float,
    z: float,
    color: tuple[float, float, float, float],
    segments: int = 8,
    tilt: float = 0.0,
) -> Any:
    segs = _new_linesegs(name, color, 1.05)
    if segs is None:
        return None
    segments = max(6, min(14, int(segments)))
    radius = max(0.03, float(radius))
    try:
        for idx in range(segments + 1):
            ang = (idx / float(segments)) * math.tau
            x = math.cos(ang) * radius
            y = math.sin(ang) * radius * (0.62 + 0.12 * math.sin(tilt))
            p = (x, y, z + math.sin(ang + tilt) * radius * 0.08)
            if idx == 0:
                segs.moveTo(*p)
            else:
                segs.drawTo(*p)
    except Exception:
        return None
    return _attach_lines(parent, segs)


def _draw_stem(parent: Any, name: str, bx: float, by: float, height: float, lean: float, color: tuple[float, float, float, float], phase: float) -> Any:
    segs = _new_linesegs(name, color, 1.15)
    if segs is None:
        return None
    try:
        segs.moveTo(bx, by, 0.03)
        for step in range(1, 4):
            t = step / 3.0
            wave = math.sin(phase + t * math.pi) * 0.10
            segs.drawTo(bx + lean * t + wave, by + math.cos(phase + t * 2.2) * 0.06 * t, height * t)
    except Exception:
        return None
    return _attach_lines(parent, segs)


def build_cluster_geometry(root: Any, *, scale: float = 1.0, seed: Any = 0) -> Any:
    if root is None:
        return None
    rng = random.Random(_safe_seed(seed))
    scale = max(0.35, min(_safe_float(scale, 1.0), 2.4))

    # Cheap wire geometry only; no textures, shaders, physics, or per-object tasks.
    try:
        _draw_soft_ring(root, "bubble_weed_base_orange", 1.05 * scale, 0.030 * scale, (1.0, 0.36, 0.10, 0.34), segments=12, tilt=rng.random() * math.tau)
        _draw_soft_ring(root, "bubble_weed_base_cyan", 0.62 * scale, 0.044 * scale, (0.30, 0.95, 1.00, 0.32), segments=8, tilt=rng.random() * math.tau)
    except Exception:
        pass

    try:
        stem_count = rng.randint(3, 5)
        for idx in range(stem_count):
            angle = rng.random() * math.tau
            radius = rng.uniform(0.12, 0.64) * scale
            bx = math.cos(angle) * radius
            by = math.sin(angle) * radius
            height = rng.uniform(0.45, 1.10) * scale
            lean = rng.uniform(-0.20, 0.20) * scale
            phase = rng.random() * math.tau
            stem_color = (rng.choice((0.72, 0.88, 1.0)), rng.uniform(0.30, 0.58), rng.uniform(0.12, 0.28), 0.48)
            _draw_stem(root, f"bubble_weed_stem_{idx:02d}", bx, by, height, lean, stem_color, phase)
            if idx % 2 == 0:
                tip = _draw_soft_ring(root, f"bubble_weed_tip_{idx:02d}", rng.uniform(0.09, 0.18) * scale, height + 0.08 * scale, (1.0, 0.56, 0.18, 0.38), segments=7, tilt=phase)
                try:
                    if tip is not None:
                        tip.setPos(bx + lean, by, 0.0)
                except Exception:
                    pass
    except Exception:
        pass

    try:
        root.setPythonTag("object_id", OBJECT_ID)
        root.setPythonTag("dimension", DIMENSION_ID)
        root.setPythonTag("spawn_weight", SPAWN_WEIGHT)
        root.setPythonTag("claim_radius", CLAIM_RADIUS)
        root.setPythonTag("passive_animation", False)
    except Exception:
        pass
    _set_alpha_blend(root)
    return root


def _extract_call_args(args: tuple[Any, ...], kwargs: dict[str, Any]) -> tuple[Any, Vec3, float, Any, str]:
    parent = kwargs.pop("parent", None) or kwargs.pop("root", None) or kwargs.pop("chunk", None)
    pos = kwargs.pop("pos", None) or kwargs.pop("position", None) or kwargs.pop("surface_pos", None)
    scale = kwargs.pop("scale", kwargs.pop("size", 1.0))
    seed = kwargs.pop("seed", kwargs.pop("rng_seed", 0))
    name = kwargs.pop("name", OBJECT_ID)

    # Locate parent and position across common loader call styles.
    leftover = []
    for item in args:
        if parent is None and _is_parent_candidate(item):
            parent = item
        elif pos is None:
            pos = item
        else:
            leftover.append(item)

    # Numeric x/y/z may be positional or keyword based.
    x = kwargs.pop("x", None)
    y = kwargs.pop("y", None)
    z = kwargs.pop("z", None)
    if pos is None and len(leftover) >= 2:
        pos = (leftover[0], leftover[1], leftover[2] if len(leftover) >= 3 else 0.0)
    p = _vec3_from_any(pos, default_z=0.0)
    if x is not None:
        p.x = _safe_float(x)
    if y is not None:
        p.y = _safe_float(y)
    if z is not None:
        p.z = _safe_float(z)
    return parent, p, _safe_float(scale, 1.0), seed, str(name or OBJECT_ID)


def create(*args: Any, **kwargs: Any) -> Any:
    parent, p, scale, seed, name = _extract_call_args(args, kwargs)
    root = _make_root(parent, name)
    if root is None:
        return None
    try:
        root.setPos(p)
    except Exception:
        try:
            root.setPos(float(p.x), float(p.y), float(p.z))
        except Exception:
            pass
    return build_cluster_geometry(root, scale=scale, seed=seed)


# Compatibility aliases for likely drop-in loaders.
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


def descriptor() -> dict[str, Any]:
    return dict(OBJECT_INFO)


def passive_update(root: Any, t: float, dt: float = 0.016) -> None:
    # Hotfix: intentionally static.  Central update systems can call this safely.
    return
