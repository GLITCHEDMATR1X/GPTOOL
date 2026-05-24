"""Movable snap-panel UI for HoloUtopia runtime inspectors.

The panel layer is intentionally small and reusable.  It does not own gameplay
state; it only displays read-only payloads from HoloUtopia citizen/building data.
"""
from __future__ import annotations

from dataclasses import dataclass
import textwrap
from typing import Any


@dataclass(frozen=True)
class SnapPanelSummary:
    movable: bool = True
    snap_left: bool = True
    snap_right: bool = True
    snap_top: bool = True
    snap_bottom: bool = True
    close_button: bool = True
    pin_button: bool = True
    keeps_crosshair_clear: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "movable": self.movable,
            "snap_left": self.snap_left,
            "snap_right": self.snap_right,
            "snap_top": self.snap_top,
            "snap_bottom": self.snap_bottom,
            "close_button": self.close_button,
            "pin_button": self.pin_button,
            "keeps_crosshair_clear": self.keeps_crosshair_clear,
        }


class MovableSnapPanelManager:
    """Runtime-safe DirectGUI panel controller with drag and snap behavior."""

    def __init__(self, app: Any, *, default_snap: str = "left", max_open_panels: int = 4, debug_raw_ids: bool = False, on_all_panels_closed: Any = None) -> None:
        self.app = app
        self.default_snap = str(default_snap or "left")
        self.max_open_panels = max(1, int(max_open_panels or 4))
        self.debug_raw_ids = bool(debug_raw_ids)
        self.on_all_panels_closed = on_all_panels_closed
        self.panels: dict[str, dict[str, Any]] = {}
        self.focused_panel_id: str | None = None
        self.dragging_panel_id: str | None = None
        self.drag_offset = (0.0, 0.0)
        self._drag_task_name = "holoutopia-snap-panel-drag"
        self._drag_task_active = False

    def destroy(self) -> None:
        for panel_id in list(self.panels):
            self.close_panel(panel_id)
        self.dragging_panel_id = None
        self.focused_panel_id = None

    def close_focused(self) -> bool:
        if not self.focused_panel_id:
            return False
        return self.close_panel(self.focused_panel_id)

    def close_panel(self, panel_id: str) -> bool:
        panel_id = str(panel_id or "")
        item = self.panels.pop(panel_id, None)
        if not item:
            return False
        try:
            node = item.get("node")
            if node is not None:
                node.destroy()
        except Exception:
            try:
                node.removeNode()
            except Exception:
                pass
        if self.focused_panel_id == panel_id:
            self.focused_panel_id = next(iter(self.panels.keys()), None)
        if self.dragging_panel_id == panel_id:
            self.dragging_panel_id = None
        if not self.panels and callable(self.on_all_panels_closed):
            try:
                self.on_all_panels_closed()
            except Exception:
                pass
        return True

    def show_citizen_panel(self, payload: dict[str, Any]) -> str:
        """Create/update the citizen inspector panel for a selected robot civilian."""
        from holoutopia_display_names import build_citizen_panel_tabs

        queue = payload.get("queue") if isinstance(payload.get("queue"), dict) else {}
        citizen_id = str(queue.get("citizen_id") or payload.get("citizen_id") or "citizen")
        panel_id = f"citizen:{citizen_id}"
        runtime_context = payload.get("runtime_context") if isinstance(payload.get("runtime_context"), dict) else {}
        view = build_citizen_panel_tabs(
            queue,
            holoverse_root=runtime_context.get("holoverse_root"),
            debug_raw_ids=bool(payload.get("debug_raw_ids", self.debug_raw_ids)),
        )
        tabs = view.get("tabs") if isinstance(view.get("tabs"), dict) else {}
        default_tab = str(view.get("default_tab") or "overview")
        body = str(tabs.get(default_tab) or next(iter(tabs.values()), "No citizen data loaded."))
        return self.show_text_panel(
            panel_id,
            str(view.get("title") or "Citizen"),
            body,
            accent=(0.20, 0.96, 1.0, 0.96),
            tab_bodies=tabs,
            active_tab=default_tab,
        )

    def show_building_panel(self, payload: dict[str, Any]) -> str:
        """Create/update a clean building inspector panel from highlight data."""
        from holoutopia_display_names import build_building_panel_tabs

        building = payload.get("building") if isinstance(payload.get("building"), dict) else payload
        building_id = str(building.get("id") or payload.get("building_id") or "building")
        panel_id = f"building:{building_id}"
        runtime_context = payload.get("runtime_context") if isinstance(payload.get("runtime_context"), dict) else {}
        view = build_building_panel_tabs(
            payload,
            holoverse_root=runtime_context.get("holoverse_root"),
            debug_raw_ids=bool(payload.get("debug_raw_ids", self.debug_raw_ids)),
        )
        tabs = view.get("tabs") if isinstance(view.get("tabs"), dict) else {}
        default_tab = str(view.get("default_tab") or "overview")
        body = str(tabs.get(default_tab) or next(iter(tabs.values()), "No building data loaded."))
        return self.show_text_panel(
            panel_id,
            str(view.get("title") or "Building"),
            body,
            accent=(1.0, 0.36, 0.92, 0.96),
            tab_bodies=tabs,
            active_tab=default_tab,
        )

    def show_text_panel(
        self,
        panel_id: str,
        title: str,
        body: str,
        *,
        accent=(0.20, 0.96, 1.0, 0.96),
        tab_bodies: dict[str, str] | None = None,
        active_tab: str = "overview",
    ) -> str:
        from direct.gui.DirectGui import DirectButton, DirectFrame, DirectLabel
        from direct.gui import DirectGuiGlobals as DGG
        from panda3d.core import TextNode

        panel_id = str(panel_id or "panel")
        self._trim_panel_count(keep_panel_id=panel_id)
        if panel_id in self.panels:
            item = self.panels[panel_id]
            try:
                item["title"]["text"] = str(title)
                item["tab_bodies"] = dict(tab_bodies or {"overview": str(body)})
                item["active_tab"] = str(active_tab or next(iter(item["tab_bodies"].keys()), "overview"))
                item["body"]["text"] = str(item["tab_bodies"].get(item["active_tab"], body))
                self.focus_panel(panel_id)
                return panel_id
            except Exception:
                self.close_panel(panel_id)

        aspect2d = getattr(self.app, "aspect2d", None)
        if aspect2d is None:
            aspect2d = getattr(__import__("builtins"), "aspect2d", None)
        frame = DirectFrame(
            parent=aspect2d,
            frameSize=(-0.60, 0.60, -0.68, 0.68),
            frameColor=(0.003, 0.012, 0.020, 0.94),
            state=DGG.NORMAL,
            sortOrder=150,
        )
        frame.setTransparency(True)
        titlebar = DirectFrame(
            parent=frame,
            frameSize=(-0.60, 0.60, 0.50, 0.68),
            frameColor=(accent[0], accent[1], accent[2], 0.38),
            state=DGG.NORMAL,
        )
        title_label = DirectLabel(
            parent=frame,
            text=str(title),
            text_align=TextNode.ALeft,
            text_fg=(0.80, 1.0, 1.0, 1.0),
            text_scale=0.037,
            text_pos=(-0.552, 0.575),
            frameColor=(0, 0, 0, 0),
        )
        body_label = DirectLabel(
            parent=frame,
            text=str(body),
            text_align=TextNode.ALeft,
            text_fg=(0.92, 1.0, 1.0, 0.95),
            text_scale=0.0285,
            text_wordwrap=36.5,
            text_pos=(-0.552, 0.397),
            frameColor=(0, 0, 0, 0),
        )
        close_button = DirectButton(parent=frame, text="Close", scale=0.030, pos=(0.510, 0, 0.594), frameColor=(0.30, 0.04, 0.05, 0.90), text_fg=(1, 0.74, 0.72, 1), command=lambda: self.close_panel(panel_id))
        pin_button = DirectButton(parent=frame, text="Pin", scale=0.030, pos=(0.405, 0, 0.594), frameColor=(0.02, 0.14, 0.18, 0.90), text_fg=(0.75, 1, 1, 1), command=lambda: self.focus_panel(panel_id))
        tab_buttons = self._make_tab_buttons(frame, panel_id, tab_bodies or {"overview": str(body)}, active_tab)
        left_button = DirectButton(parent=frame, text="Dock L", scale=0.024, pos=(-0.455, 0, -0.615), frameColor=(0.03, 0.12, 0.16, 0.86), text_fg=(0.7, 1, 1, 1), command=lambda: self.snap_panel(panel_id, "left"))
        right_button = DirectButton(parent=frame, text="Dock R", scale=0.024, pos=(-0.330, 0, -0.615), frameColor=(0.03, 0.12, 0.16, 0.86), text_fg=(0.7, 1, 1, 1), command=lambda: self.snap_panel(panel_id, "right"))
        top_button = DirectButton(parent=frame, text="Top", scale=0.024, pos=(-0.215, 0, -0.615), frameColor=(0.03, 0.12, 0.16, 0.86), text_fg=(0.7, 1, 1, 1), command=lambda: self.snap_panel(panel_id, "top"))
        bottom_button = DirectButton(parent=frame, text="Bottom", scale=0.024, pos=(-0.112, 0, -0.615), frameColor=(0.03, 0.12, 0.16, 0.86), text_fg=(0.7, 1, 1, 1), command=lambda: self.snap_panel(panel_id, "bottom"))
        hint_label = DirectLabel(parent=frame, text="drag header  •  dock to corners  •  Shift+X closes", text_align=TextNode.ARight, text_fg=(0.56, 0.90, 1.0, 0.68), text_scale=0.021, text_pos=(0.552, -0.628), frameColor=(0, 0, 0, 0))
        for widget in (titlebar, title_label):
            try:
                widget.bind(DGG.B1PRESS, lambda _event=None, pid=panel_id: self.begin_drag(pid))
                widget.bind(DGG.B1RELEASE, lambda _event=None: self.end_drag())
            except Exception:
                pass
        self.panels[panel_id] = {
            "node": frame,
            "titlebar": titlebar,
            "title": title_label,
            "body": body_label,
            "buttons": [close_button, pin_button, *list(tab_buttons.values()), left_button, right_button, top_button, bottom_button, hint_label],
            "tab_buttons": tab_buttons,
            "pinned": False,
            "snap": self.default_snap,
            "tab_bodies": dict(tab_bodies or {"overview": str(body)}),
            "active_tab": str(active_tab or "overview"),
        }
        self.snap_panel(panel_id, self.default_snap)
        self.focus_panel(panel_id)
        return panel_id

    def focus_panel(self, panel_id: str) -> None:
        panel_id = str(panel_id or "")
        if panel_id not in self.panels:
            return
        self.focused_panel_id = panel_id
        for idx, (pid, item) in enumerate(self.panels.items()):
            node = item.get("node")
            try:
                node.setBin("fixed", 142 + idx + (20 if pid == panel_id else 0))
            except Exception:
                pass

    def begin_drag(self, panel_id: str) -> None:
        if panel_id not in self.panels:
            return
        self.focus_panel(panel_id)
        item = self.panels[panel_id]
        node = item.get("node")
        mx, mz = self._mouse_aspect2d()
        try:
            self.drag_offset = (float(node.getX()) - mx, float(node.getZ()) - mz)
        except Exception:
            self.drag_offset = (0.0, 0.0)
        self.dragging_panel_id = panel_id
        self._ensure_drag_task()

    def end_drag(self) -> None:
        pid = self.dragging_panel_id
        self.dragging_panel_id = None
        if pid:
            self._auto_snap_if_near_edge(pid)

    def snap_panel(self, panel_id: str, side: str) -> None:
        item = self.panels.get(panel_id)
        if not item:
            return
        node = item.get("node")
        aspect = self._aspect_ratio()
        side = str(side or "left").lower()
        positions = {
            "left": (-aspect + 0.68, 0.0, 0.20),
            "right": (aspect - 0.68, 0.0, 0.20),
            "top": (0.0, 0.0, 0.28),
            "bottom": (0.0, 0.0, -0.24),
        }
        pos = positions.get(side, positions["left"])
        try:
            node.setPos(*pos)
            item["snap"] = side
        except Exception:
            pass

    def _make_tab_buttons(self, frame: Any, panel_id: str, tab_bodies: dict[str, str], active_tab: str) -> dict[str, Any]:
        from direct.gui.DirectGui import DirectButton

        labels = {"overview": "Overview", "status": "Status", "tasks": "Tasks", "social": "Social", "people": "People", "activity": "Activity"}
        buttons: dict[str, Any] = {}
        ordered_tabs = [key for key in ("overview", "status", "tasks", "social", "people", "activity") if key in tab_bodies]
        start_x = -0.455
        spacing = 0.182 if len(ordered_tabs) >= 5 else 0.220
        for idx, tab in enumerate(ordered_tabs[:6]):
            is_active = tab == active_tab
            button = DirectButton(
                parent=frame,
                text=labels.get(tab, tab.title()),
                scale=0.0255,
                pos=(start_x + idx * spacing, 0, 0.465),
                frameColor=self._tab_color(is_active),
                text_fg=(0.88, 1.0, 1.0, 1.0),
                command=lambda tab_id=tab: self.set_panel_tab(panel_id, tab_id),
            )
            buttons[tab] = button
        return buttons

    @staticmethod
    def _tab_color(active: bool) -> tuple[float, float, float, float]:
        return (0.06, 0.29, 0.34, 0.94) if active else (0.015, 0.075, 0.095, 0.88)

    def set_panel_tab(self, panel_id: str, tab_id: str) -> bool:
        item = self.panels.get(str(panel_id or ""))
        if not item:
            return False
        tabs = item.get("tab_bodies") if isinstance(item.get("tab_bodies"), dict) else {}
        tab_id = str(tab_id or "")
        if tab_id not in tabs:
            return False
        item["active_tab"] = tab_id
        try:
            item["body"]["text"] = str(tabs[tab_id])
            buttons = item.get("tab_buttons") if isinstance(item.get("tab_buttons"), dict) else {}
            for key, button in buttons.items():
                try:
                    button["frameColor"] = self._tab_color(str(key) == tab_id)
                except Exception:
                    pass
        except Exception:
            return False
        self.focus_panel(panel_id)
        return True

    def _trim_panel_count(self, *, keep_panel_id: str) -> None:
        if keep_panel_id in self.panels:
            return
        while len(self.panels) >= self.max_open_panels:
            victim = next((pid for pid, item in self.panels.items() if not item.get("pinned")), None)
            if victim is None:
                victim = next(iter(self.panels.keys()), None)
            if victim is None:
                return
            self.close_panel(victim)

    def _ensure_drag_task(self) -> None:
        if self._drag_task_active:
            return
        task_mgr = getattr(self.app, "taskMgr", None) or getattr(self.app, "task_mgr", None)
        if task_mgr is None:
            task_mgr = getattr(__import__("builtins"), "taskMgr", None)
        if task_mgr is not None and hasattr(task_mgr, "add"):
            try:
                task_mgr.add(self._drag_update_task, self._drag_task_name)
                self._drag_task_active = True
            except Exception:
                pass

    def _drag_update_task(self, task: Any) -> Any:
        pid = self.dragging_panel_id
        if pid and pid in self.panels:
            mx, mz = self._mouse_aspect2d()
            dx, dz = self.drag_offset
            x = mx + dx
            z = mz + dz
            aspect = self._aspect_ratio()
            x = max(-aspect + 0.42, min(aspect - 0.42, x))
            z = max(-0.84, min(0.86, z))
            try:
                self.panels[pid]["node"].setPos(x, 0, z)
            except Exception:
                pass
        return getattr(task, "cont", task)

    def _auto_snap_if_near_edge(self, panel_id: str) -> None:
        item = self.panels.get(panel_id)
        if not item:
            return
        node = item.get("node")
        aspect = self._aspect_ratio()
        try:
            x = float(node.getX())
            z = float(node.getZ())
        except Exception:
            return
        if x < -aspect + 0.82:
            self.snap_panel(panel_id, "left")
        elif x > aspect - 0.82:
            self.snap_panel(panel_id, "right")
        elif z > 0.56:
            self.snap_panel(panel_id, "top")
        elif z < -0.58:
            self.snap_panel(panel_id, "bottom")

    def _mouse_aspect2d(self) -> tuple[float, float]:
        watcher = getattr(self.app, "mouseWatcherNode", None)
        if watcher is not None and watcher.hasMouse():
            m = watcher.getMouse()
            return float(m.getX()) * self._aspect_ratio(), float(m.getY())
        return 0.0, 0.0

    def _aspect_ratio(self) -> float:
        try:
            return float(self.app.getAspectRatio())
        except Exception:
            return 16.0 / 9.0


def build_snap_panel_summary() -> SnapPanelSummary:
    return SnapPanelSummary()
