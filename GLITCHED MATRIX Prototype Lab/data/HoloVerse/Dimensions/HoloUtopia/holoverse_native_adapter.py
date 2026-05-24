"""Same-window HoloUtopia adapter for HoloVerse.

This route replaces a stale/missing archived dimension with the authored
HoloUtopia live-city runtime.  It mounts the city into the current Panda3D
ShowBase without spawning a child window, without writing authored data, and
without touching HoloCore or region routes.
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

from direct.gui.OnscreenText import OnscreenText
from panda3d.core import NodePath, TextNode, Vec3, WindowProperties

MODE_TITLE = "HoloUtopia"
MODE_ID = "holoutopia"
MODE_STATUS = "HOLOUTOPIA // LIVE CITY SAME-WINDOW // ESC / 0 RETURN TO HOLOVERSE // H SHOWS LEGACY UI"


class _RuntimeHostProxy:
    """Expose a safe ShowBase-like surface for the standalone city runtime."""

    def __init__(self, owner: "HoloVerseNativeMode") -> None:
        self._owner = owner
        self._host = owner.host
        self.render = owner.scene_root
        self.root_3d = owner.scene_root
        self.world_root = owner.scene_root
        self.taskMgr = getattr(self._host, "taskMgr", None)
        self.loader = getattr(self._host, "loader", None)
        self.camera = getattr(self._host, "camera", None)
        self.camLens = getattr(self._host, "camLens", None)
        self.win = getattr(self._host, "win", None)
        self.aspect2d = owner.ui_root

    def accept(self, key: str, method, extraArgs=None) -> None:
        self._owner._accepted_keys.add(str(key))
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


class HoloVerseNativeMode:
    """Mount HoloUtopia's authored city runtime inside HoloVerse."""

    def __init__(self, host, mode=None, entry_path=None, label=MODE_TITLE):
        self.host = host
        self.mode = mode or {}
        self.entry_path = Path(entry_path) if entry_path else Path(__file__).resolve().parent / "main.py"
        self.folder = self.entry_path.parent
        self.module_root = self.folder / "data" / "HoloUtopia"
        self.label = str(label or MODE_TITLE)
        self.scene_root: NodePath | None = None
        self.ui_root: NodePath | None = None
        self.runtime = None
        self.dimension_ui_visible = False
        self._entered = False
        self._accepted_keys: set[str] = set()
        self.holoverse_result = {
            "score_delta": 0,
            "completed": False,
            "signal": "holoutopia_live_city_stabilized",
            "memory_fragment": "HoloUtopia replaced a missing archive route with a living city signal.",
        }

    def _install_module_path(self) -> None:
        for path in (self.module_root, self.folder):
            text = str(path)
            if path.exists() and text not in sys.path:
                sys.path.insert(0, text)

    def _set_camera(self) -> None:
        camera = getattr(self.host, "camera", None)
        if camera is None:
            return
        try:
            camera.reparentTo(getattr(self.host, "render", self.scene_root))
            camera.setPos(-360.0, -430.0, 96.0)
            camera.lookAt(Vec3(8.0, -18.0, 24.0))
            lens = getattr(self.host, "camLens", None)
            if lens is not None:
                lens.setFov(54)
                lens.setNearFar(1.0, 5000.0)
        except Exception:
            pass

    def _create_dimension_ui(self) -> None:
        if self.ui_root is None:
            return
        try:
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

    def _set_dimension_ui_visible(self, visible: bool) -> None:
        self.dimension_ui_visible = bool(visible)
        node = getattr(self, "status_text", None)
        try:
            if node is not None:
                node.show() if self.dimension_ui_visible else node.hide()
        except Exception:
            pass

    def toggle_dimension_ui(self) -> bool:
        self._set_dimension_ui_visible(not bool(getattr(self, "dimension_ui_visible", False)))
        return True

    def enter(self) -> None:
        self._install_module_path()
        host_render = getattr(self.host, "render", None)
        host_aspect = getattr(self.host, "aspect2d", None)
        if host_render is None:
            raise RuntimeError("HoloUtopia native adapter requires a Panda3D render root")
        self.scene_root = host_render.attachNewNode("holoutopia_native_root")
        self.ui_root = (host_aspect or host_render).attachNewNode("holoutopia_native_ui_root")
        self._set_camera()
        self._create_dimension_ui()
        try:
            if getattr(self.host, "win", None) is not None:
                props = WindowProperties()
                props.setCursorHidden(False)
                self.host.win.requestProperties(props)
        except Exception:
            pass
        from holoutopia_game_runtime import install_holoutopia_runtime
        proxy = _RuntimeHostProxy(self)
        self.runtime = install_holoutopia_runtime(proxy, self.module_root, enabled=True)
        if not getattr(self.runtime, "installed", False):
            error = str(getattr(self.runtime, "error", "runtime failed to install") or "runtime failed to install")
            raise RuntimeError(error)
        self._set_dimension_ui_visible(False)
        self._entered = True

    def update(self, dt: float = 0.0) -> None:
        # The authored runtime owns its own Panda task.  This hook stays present
        # so HoloVerse can call it every frame without treating the mode as stale.
        return None

    def on_host_action(self, action: str) -> bool:
        action = str(action or "").lower()
        if action in {"toggle_dimension_ui", "dimension_ui", "h"}:
            return self.toggle_dimension_ui()
        if action in {"escape", "number_0"}:
            return False
        return False

    def get_holoverse_result(self) -> dict:
        result = dict(self.holoverse_result)
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

    def destroy(self) -> None:
        try:
            if self.runtime is not None:
                self.runtime.destroy()
        except Exception:
            pass
        self.runtime = None
        for key in list(self._accepted_keys):
            try:
                ignore = getattr(self.host, "ignore", None)
                if callable(ignore):
                    ignore(key)
            except Exception:
                pass
        self._accepted_keys.clear()
        for attr in ("ui_root", "scene_root"):
            node = getattr(self, attr, None)
            try:
                if node is not None and not node.isEmpty():
                    node.removeNode()
            except Exception:
                pass
            setattr(self, attr, None)
        self._entered = False

    exit = destroy


def create_mode(host, mode=None, entry_path=None, label=MODE_TITLE):
    return HoloVerseNativeMode(host, mode=mode, entry_path=entry_path, label=label)
