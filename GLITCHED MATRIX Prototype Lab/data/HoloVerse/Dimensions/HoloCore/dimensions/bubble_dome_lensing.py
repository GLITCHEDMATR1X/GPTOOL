"""Optional lightweight Bubble Dome lensing manager for HoloVerse pass24.

This is deliberately optional.  The domes already contain interior curved
"lensing" ribbons, so Dimension 3 remains stable even if no manager is wired.
If a game object calls ``install_pass24_lensing(base, player_or_camera)``, this
adds one low-frequency task that shows a subtle camera overlay only while the
camera/player is inside a tagged bubble dome.
"""

from __future__ import annotations

import math
from typing import Any

try:
    from panda3d.core import LineSegs, NodePath, TransparencyAttrib, Vec3
except Exception:
    LineSegs = None  # type: ignore[assignment]
    NodePath = None  # type: ignore[assignment]
    TransparencyAttrib = None  # type: ignore[assignment]


TASK_NAME = "pass24_bubble_dome_lensing_update"


def _safe_vec3(node: Any) -> Any:
    try:
        return node.getPos()
    except Exception:
        return None


def _distance_xy(a: Any, b: Any) -> float:
    try:
        dx = float(a.x) - float(b.x)
        dy = float(a.y) - float(b.y)
        return math.sqrt(dx * dx + dy * dy)
    except Exception:
        return 999999.0


def _make_overlay(camera: Any) -> Any:
    if camera is None or LineSegs is None or not hasattr(camera, "attachNewNode"):
        return None
    root = camera.attachNewNode("pass24_bubble_lensing_overlay")
    try:
        root.setPos(0.0, 1.85, 0.0)
        root.setScale(1.0)
        root.hide()
        if TransparencyAttrib is not None:
            root.setTransparency(TransparencyAttrib.M_alpha)
        root.setLightOff(True)
        root.setDepthTest(False)
        root.setDepthWrite(False)
        root.setBin("fixed", 40)
    except Exception:
        pass

    # A few curved rings close to the camera.  It is not a true refraction
    # post-process, but it is cheap and reads as gravitational lensing/warped
    # light when the player steps inside the dome.
    for i, scale in enumerate((0.18, 0.31, 0.47, 0.65)):
        segs = LineSegs(f"pass24_lens_overlay_ring_{i}")
        try:
            segs.setThickness(1.1)
            segs.setColor(0.55, 0.92, 1.0, 0.12 + i * 0.035)
        except Exception:
            pass
        first = True
        for idx in range(49):
            t = idx / 48.0
            ang = t * math.tau
            wob = math.sin(ang * 3.0 + i) * 0.018
            x = math.cos(ang) * (scale + wob)
            z = math.sin(ang) * (scale * 0.56 + wob)
            if first:
                segs.moveTo(x, 0.0, z)
                first = False
            else:
                segs.drawTo(x, 0.0, z)
        try:
            np = root.attachNewNode(segs.create())
            if TransparencyAttrib is not None:
                np.setTransparency(TransparencyAttrib.M_alpha)
        except Exception:
            pass
    return root


class BubbleDomeLensingManager:
    def __init__(self, base: Any, player_or_camera: Any = None, dome_parent: Any = None) -> None:
        self.base = base
        self.camera = getattr(base, "camera", None) or player_or_camera
        self.player = player_or_camera or self.camera
        self.dome_parent = dome_parent or getattr(base, "render", None)
        self.overlay = _make_overlay(self.camera)
        self._accum = 0.0
        self._inside = False

    def _iter_domes(self) -> list[Any]:
        root = self.dome_parent
        if root is None:
            return []
        try:
            # Panda3D findAllMatches accepts a glob.  This catches nodes created
            # by bubble_dome.py without walking unrelated Python containers.
            matches = root.findAllMatches("**/bubble_dome")
            return [matches[i] for i in range(matches.getNumPaths())]
        except Exception:
            return []

    def _is_inside_any_dome(self) -> bool:
        player_pos = _safe_vec3(self.player) or _safe_vec3(self.camera)
        if player_pos is None:
            return False
        for dome in self._iter_domes():
            try:
                radius = float(dome.getPythonTag("bubble_dome_radius"))
            except Exception:
                radius = 32.0
            dome_pos = _safe_vec3(dome)
            if dome_pos is not None and _distance_xy(player_pos, dome_pos) <= radius * 0.92:
                return True
        return False

    def update(self, task: Any) -> Any:
        try:
            dt = float(getattr(globalClock, "getDt", lambda: 0.016)())  # type: ignore[name-defined]
        except Exception:
            dt = 0.016
        self._accum += max(0.0, min(dt, 0.05))
        # Check at low frequency; the effect itself is static/cheap.
        if self._accum >= 0.12:
            self._accum = 0.0
            inside = self._is_inside_any_dome()
            if inside != self._inside:
                self._inside = inside
                try:
                    if self.overlay is not None:
                        self.overlay.show() if inside else self.overlay.hide()
                except Exception:
                    pass
        try:
            return task.cont
        except Exception:
            return None


def install_pass24_lensing(base: Any, player_or_camera: Any = None, dome_parent: Any = None) -> BubbleDomeLensingManager | None:
    """Install one safe, low-frequency lensing task.

    This function can be called by the game after the player/camera exists.  It
    does nothing if Panda3D/taskMgr is unavailable.
    """
    try:
        manager = BubbleDomeLensingManager(base, player_or_camera=player_or_camera, dome_parent=dome_parent)
        task_mgr = getattr(base, "taskMgr", None) or globals().get("taskMgr")
        if task_mgr is not None:
            try:
                task_mgr.remove(TASK_NAME)
            except Exception:
                pass
            task_mgr.add(manager.update, TASK_NAME)
        try:
            setattr(base, "pass24_bubble_dome_lensing", manager)
        except Exception:
            pass
        return manager
    except Exception:
        return None
