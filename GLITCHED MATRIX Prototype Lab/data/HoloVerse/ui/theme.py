from __future__ import annotations

from typing import Any

HOLOVERSE_UI_RED = (1.0, 0.08, 0.08, 1.0)
HOLOVERSE_UI_RED_DIM = (0.72, 0.03, 0.03, 1.0)
HOLOVERSE_UI_RED_SOFT = (1.0, 0.18, 0.12, 1.0)
HOLOVERSE_UI_SHADOW = (0.0, 0.0, 0.0, 0.72)

GLEEBS_DIALOGUE_CHANNEL = "red"
RETIRED_DIALOGUE_CHANNELS = ("blue", "cyan")
SINGLE_GLEEBS_DIALOGUE_SURFACE = True


def red_text_kwargs(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "text_fg": HOLOVERSE_UI_RED,
        "text_shadow": HOLOVERSE_UI_SHADOW,
        "text_shadowOffset": (0.045, 0.045),
    }
    payload.update(overrides)
    return payload


def apply_red_text(widget: Any) -> None:
    for key, value in red_text_kwargs().items():
        try:
            widget[key] = value
            continue
        except Exception:
            pass
        if key == "text_fg":
            try:
                setter = getattr(widget, "setTextColor", None)
                if callable(setter):
                    setter(*value)
            except Exception:
                pass
