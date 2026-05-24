"""Thin HoloVerse adapter for the HoloUtopia app capsule.

This file intentionally stays small.  HoloUtopia's authored runtime remains in
its own modules, capsule.py owns the same-window lifecycle contract, and this
adapter only translates HoloVerse native-mode calls into capsule calls.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

MODE_TITLE = "HoloUtopia"
MODE_ID = "holoutopia"
MODE_STATUS = "HOLOUTOPIA // LIVING CITY CAPSULE // ESC / 0 RETURN TO HOLOVERSE // H SHOWS LEGACY UI"


class HoloVerseNativeMode:
    """HoloVerse native-mode wrapper around HoloUtopiaCapsule."""

    def __init__(self, host, mode=None, entry_path=None, label=MODE_TITLE):
        self.host = host
        self.mode = mode or {}
        self.entry_path = Path(entry_path) if entry_path else Path(__file__).resolve().parent / "main.py"
        self.folder = self.entry_path.parent
        self.label = str(label or MODE_TITLE)
        self.dimension_ui_visible = False
        self.capsule = None
        self._install_path()

    def _install_path(self) -> None:
        folder_text = str(self.folder)
        if folder_text not in sys.path:
            sys.path.insert(0, folder_text)

    def enter(self) -> None:
        from capsule import create_capsule
        context: dict[str, Any] = {
            "mode": dict(self.mode or {}),
            "label": self.label,
            "entry_path": str(self.entry_path),
            "source": "holoverse_native_adapter",
        }
        self.capsule = create_capsule(self.host, context=context, app_root=self.folder)
        self.capsule.enter(context)
        self.dimension_ui_visible = bool(getattr(self.capsule, "dimension_ui_visible", False))

    def update(self, dt: float = 0.0) -> None:
        if self.capsule is not None:
            return self.capsule.update(dt)
        return None

    def toggle_dimension_ui(self) -> bool:
        if self.capsule is not None and hasattr(self.capsule, "toggle_dimension_ui"):
            result = bool(self.capsule.toggle_dimension_ui())
            self.dimension_ui_visible = bool(getattr(self.capsule, "dimension_ui_visible", False))
            return result
        self.dimension_ui_visible = not self.dimension_ui_visible
        return True

    def on_host_action(self, action: str) -> bool:
        if self.capsule is not None and hasattr(self.capsule, "on_host_action"):
            return bool(self.capsule.on_host_action(action))
        action = str(action or "").lower()
        if action in {"toggle_dimension_ui", "dimension_ui", "h"}:
            return self.toggle_dimension_ui()
        return False

    def get_holoverse_result(self) -> dict[str, Any]:
        if self.capsule is not None and hasattr(self.capsule, "get_result"):
            return dict(self.capsule.get_result())
        return {
            "app_id": MODE_ID,
            "score_delta": 0,
            "completed": False,
            "signal": "holoutopia_capsule_not_entered",
            "memory_fragment": "HoloUtopia capsule wrapper was created but not entered.",
        }

    def destroy(self) -> None:
        if self.capsule is not None:
            try:
                self.capsule.exit("return_to_holoverse")
            except Exception:
                try:
                    self.capsule.cleanup()
                except Exception:
                    pass
        self.capsule = None
        self.dimension_ui_visible = False

    exit = destroy


def create_mode(host, mode=None, entry_path=None, label=MODE_TITLE):
    return HoloVerseNativeMode(host, mode=mode, entry_path=entry_path, label=label)
