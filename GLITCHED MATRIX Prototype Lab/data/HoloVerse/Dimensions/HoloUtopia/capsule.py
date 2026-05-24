"""GPTOOL app capsule for HoloUtopia inside HoloVerse.

This module is the clean connection point between HoloVerse and the authored
HoloUtopia city runtime.  The standalone HoloUtopia launcher remains separate;
HoloVerse imports this capsule and delegates lifecycle calls instead of pasting
city runtime code into HoloVerse or growing another large adapter.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

APP_ID = "holoutopia"
APP_TITLE = "HoloUtopia"
CAPSULE_CONTRACT = "app_capsule.v1"
MODE_STATUS = "HOLOUTOPIA // LIVING CITY CAPSULE // ESC / 0 RETURN TO HOLOVERSE // H SHOWS LEGACY UI"


class RuntimeHostProxy:
    """Small ShowBase-like host surface for the authored HoloUtopia runtime.

    The proxy exposes only the roots/services HoloUtopia already expects.  It
    does not own the window, render loop, host process, or HoloVerse task names.
    """

    def __init__(self, capsule: "HoloUtopiaCapsule") -> None:
        self._capsule = capsule
        self._host = capsule.host
        self.render = capsule.scene_root
        self.root_3d = capsule.scene_root
        self.world_root = capsule.scene_root
        self.taskMgr = getattr(self._host, "taskMgr", None)
        self.loader = getattr(self._host, "loader", None)
        self.camera = getattr(self._host, "camera", None)
        self.camLens = getattr(self._host, "camLens", None)
        self.win = getattr(self._host, "win", None)
        self.aspect2d = capsule.ui_root

    def accept(self, key: str, method, extraArgs=None) -> None:  # noqa: N803 - Panda3D style
        self._capsule.accepted_keys.add(str(key))
        accept = getattr(self._host, "accept", None)
        if callable(accept):
            if extraArgs is None:
                accept(key, method)
            else:
                accept(key, method, extraArgs)

    def ignore(self, key: str) -> None:
        ignore = getattr(self._host, "ignore", None)
        if callable(ignore):
            ignore(key)


class HoloUtopiaCapsule:
    """Same-window HoloUtopia lifecycle capsule."""

    def __init__(self, host=None, *, app_root: str | Path | None = None, context: dict[str, Any] | None = None) -> None:
        self.host = host
        self.context = dict(context or {})
        self.app_root = Path(app_root) if app_root else Path(__file__).resolve().parent
        self.module_root = self.app_root / "data" / "HoloUtopia"
        self.scene_root = None
        self.ui_root = None
        self.runtime = None
        self.status_text = None
        self.dimension_ui_visible = False
        self.entered = False
        self.accepted_keys: set[str] = set()
        self.result: dict[str, Any] = {
            "app_id": APP_ID,
            "score_delta": 0,
            "completed": False,
            "signal": "holoutopia_live_city_capsule_ready",
            "memory_fragment": "HoloUtopia connected through a GPTOOL app capsule contract.",
            "warnings": [],
        }

    def prepare(self, host=None) -> "HoloUtopiaCapsule":
        if host is not None:
            self.host = host
        for path in (self.module_root, self.app_root):
            text = str(path)
            if path.exists() and text not in sys.path:
                sys.path.insert(0, text)
        return self

    def _set_camera(self) -> None:
        if self.host is None:
            return
        camera = getattr(self.host, "camera", None)
        if camera is None:
            return
        try:
            from panda3d.core import Vec3
            camera.reparentTo(getattr(self.host, "render", self.scene_root))
            camera.setPos(-360.0, -430.0, 96.0)
            camera.lookAt(Vec3(8.0, -18.0, 24.0))
            lens = getattr(self.host, "camLens", None)
            if lens is not None:
                lens.setFov(54)
                lens.setNearFar(1.0, 5000.0)
        except Exception:
            self.result.setdefault("warnings", []).append("camera_setup_failed")

    def _create_dimension_ui(self) -> None:
        if self.ui_root is None:
            return
        try:
            from direct.gui.OnscreenText import OnscreenText
            from panda3d.core import TextNode
            self.status_text = OnscreenText(
                parent=self.ui_root,
                text=MODE_STATUS,
                pos=(-1.28, 0.88),
                scale=0.034,
                align=TextNode.ALeft,
                fg=(0.72, 1.0, 0.92, 0.92),
                shadow=(0, 0, 0, 0.72),
            )
            self.status_text.hide()
        except Exception:
            self.status_text = None
            self.result.setdefault("warnings", []).append("status_ui_setup_failed")

    def _set_dimension_ui_visible(self, visible: bool) -> None:
        self.dimension_ui_visible = bool(visible)
        try:
            if self.status_text is not None:
                self.status_text.show() if self.dimension_ui_visible else self.status_text.hide()
        except Exception:
            pass

    def toggle_dimension_ui(self) -> bool:
        self._set_dimension_ui_visible(not bool(self.dimension_ui_visible))
        return True

    def enter(self, context: dict[str, Any] | None = None) -> None:
        if context:
            self.context.update(context)
        self.prepare(self.host)
        if self.host is None:
            raise RuntimeError("HoloUtopia capsule requires a HoloVerse host")
        host_render = getattr(self.host, "render", None)
        host_aspect = getattr(self.host, "aspect2d", None)
        if host_render is None:
            raise RuntimeError("HoloUtopia capsule requires a Panda3D render root")

        self.scene_root = host_render.attachNewNode("holoutopia_capsule_root")
        self.ui_root = (host_aspect or host_render).attachNewNode("holoutopia_capsule_ui_root")
        self._set_camera()
        self._create_dimension_ui()
        try:
            from panda3d.core import WindowProperties
            if getattr(self.host, "win", None) is not None:
                props = WindowProperties()
                props.setCursorHidden(False)
                self.host.win.requestProperties(props)
        except Exception:
            pass

        from holoutopia_game_runtime import install_holoutopia_runtime
        proxy = RuntimeHostProxy(self)
        self.runtime = install_holoutopia_runtime(proxy, self.module_root, enabled=True)
        if not getattr(self.runtime, "installed", False):
            error = str(getattr(self.runtime, "error", "runtime failed to install") or "runtime failed to install")
            raise RuntimeError(error)
        self._set_dimension_ui_visible(False)
        self.entered = True

    def update(self, dt: float = 0.0) -> None:
        # HoloUtopia's authored runtime owns its Panda task after install.
        # The hook stays available for future host-service input/camera bridging.
        return None

    def on_host_action(self, action: str) -> bool:
        action = str(action or "").lower()
        if action in {"toggle_dimension_ui", "dimension_ui", "h"}:
            return self.toggle_dimension_ui()
        if action in {"escape", "number_0"}:
            return False
        return False

    def get_result(self) -> dict[str, Any]:
        result = dict(self.result)
        try:
            summary = self.runtime.summary() if self.runtime is not None and hasattr(self.runtime, "summary") else {}
        except Exception:
            summary = {}
        if isinstance(summary, dict):
            result["summary"] = summary
            try:
                result["score_delta"] = max(0, int(summary.get("citizen_count", 0) or 0))
            except Exception:
                pass
        result["completed"] = True
        return result

    def exit(self, reason: str = "return_to_holoverse") -> None:
        self.result["exit_reason"] = str(reason or "return_to_holoverse")
        self.cleanup()

    def cleanup(self) -> None:
        try:
            if self.runtime is not None:
                self.runtime.destroy()
        except Exception:
            pass
        self.runtime = None
        if self.host is not None:
            for key in list(self.accepted_keys):
                try:
                    ignore = getattr(self.host, "ignore", None)
                    if callable(ignore):
                        ignore(key)
                except Exception:
                    pass
        self.accepted_keys.clear()
        for attr in ("ui_root", "scene_root"):
            node = getattr(self, attr, None)
            try:
                if node is not None and not node.isEmpty():
                    node.removeNode()
            except Exception:
                pass
            setattr(self, attr, None)
        self.entered = False


def create_capsule(host=None, context: dict[str, Any] | None = None, app_root: str | Path | None = None) -> HoloUtopiaCapsule:
    capsule = HoloUtopiaCapsule(host=host, app_root=app_root, context=context)
    return capsule.prepare(host)
