"""Static validation for HoloUtopia movable snap panel module."""
from __future__ import annotations

import json
import sys
from pathlib import Path


def _find_holoverse_root() -> Path:
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        if parent.name.lower() in {"holoverse", "holoutopia"} and (parent / "holoutopia_snap_panels.py").exists():
            return parent
    raise SystemExit("Could not resolve data/HoloUtopia root")


def main() -> int:
    root = _find_holoverse_root()
    sys.path.insert(0, str(root))
    from holoutopia_snap_panels import build_snap_panel_summary
    config_path = root.parent / "database" / "utopia" / "runtime" / "holoutopia_runtime_bridge.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    summary = build_snap_panel_summary().as_dict()
    assert summary["movable"] is True
    assert summary["keeps_crosshair_clear"] is True
    for key in ("snap_left", "snap_right", "snap_top", "snap_bottom", "close_button", "pin_button"):
        assert summary[key] is True, key
    panels = config.get("panels", {}) if isinstance(config.get("panels"), dict) else {}
    assert panels.get("default_snap") in {"left", "right"}, "default panel snap must stay off the center gameplay view"
    assert panels.get("debug_raw_ids") is False, "raw IDs must stay behind an explicit debug flag"
    assert panels.get("normal_text_uses_display_names") is True, "normal panels must use display-name resolver"
    assert list(panels.get("tabs") or []) == ["overview", "tasks", "social"], "panel tabs missing"
    print(json.dumps({"ok": True, "summary": summary, "panels": panels}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
