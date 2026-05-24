"""Standalone debug launcher for the built-in HoloVerse Vector Arena.

The HoloVerse artifact route uses holoverse_native_adapter.py.  Running this
file directly starts a small Panda3D host only for local testing.
"""
from __future__ import annotations

from panda3d.core import loadPrcFileData

loadPrcFileData("", "window-title HoloVerse Vector Arena")
loadPrcFileData("", "win-size 1280 720")
loadPrcFileData("", "sync-video true")

from direct.showbase.ShowBase import ShowBase
from holoverse_native_adapter import create_mode


class _VectorArenaDebugHost(ShowBase):
    def __init__(self):
        super().__init__()
        self.mode = create_mode(self, label="Vector Arena")
        self.mode.enter()
        self.taskMgr.add(self._update, "vector-arena-debug-update")
        self.accept("escape", self._exit)
        self.accept("h", self.mode.toggle_dimension_ui)
        self.accept("mouse1", lambda: self.mode.on_host_action("mouse1"))
        self.accept("mouse3", lambda: self.mode.on_host_action("mouse3"))

    def _update(self, task):
        self.mode.update(globalClock.getDt())
        return task.cont

    def _exit(self):
        self.mode.exit()
        self.userExit()


if __name__ == "__main__":
    _VectorArenaDebugHost().run()
