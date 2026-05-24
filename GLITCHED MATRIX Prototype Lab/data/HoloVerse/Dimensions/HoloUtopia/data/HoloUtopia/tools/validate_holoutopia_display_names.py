"""Validate Pass 26 display-name and player-facing citizen panel text."""
from __future__ import annotations

import json
import sys
from pathlib import Path


def _find_holoverse_root() -> Path:
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        if parent.name.lower() in {"holoverse", "holoutopia"} and (parent / "holoutopia_display_names.py").exists():
            return parent
    for parent in [here.parent, *here.parents]:
        candidate = parent / "data" / "HoloUtopia"
        if (candidate / "holoutopia_display_names.py").exists():
            return candidate
    raise SystemExit("Could not resolve data/HoloUtopia root")


def main() -> int:
    root = _find_holoverse_root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from holoutopia_citizen_tasks import build_all_citizen_task_queues
    from holoutopia_display_names import (
        DisplayNameResolver,
        build_citizen_panel_tabs,
        data_root_from_holoverse,
        read_json,
        validate_player_panel_text,
    )

    data_root = data_root_from_holoverse(root)
    ui_dir = data_root / "database" / "utopia" / "ui"
    required = [
        "display_name_catalog.json",
        "citizen_panel_layout.json",
        "task_icon_catalog.json",
        "district_style_catalog.json",
    ]
    for name in required:
        assert (ui_dir / name).exists(), f"missing ui catalog: {name}"
    layout = read_json(ui_dir / "citizen_panel_layout.json", {})
    assert layout.get("keeps_center_gameplay_view_clear") is True, "panel must keep center gameplay view clear by default"
    assert list(layout.get("tabs") or []) == ["overview", "tasks", "social"], "citizen panel tabs changed"
    resolver = DisplayNameResolver(root)
    snapshot = build_all_citizen_task_queues(root, clock="08:00")
    queues = snapshot.get("queues", {}) if isinstance(snapshot.get("queues"), dict) else {}
    assert queues, "no citizen queues"
    checked = 0
    for cid, queue in queues.items():
        view = build_citizen_panel_tabs(queue, holoverse_root=root, debug_raw_ids=False)
        assert view.get("debug_raw_ids") is False, f"{cid} normal panel unexpectedly debug"
        tabs = view.get("tabs") if isinstance(view.get("tabs"), dict) else {}
        assert set(("overview", "tasks", "social")).issubset(tabs.keys()), f"{cid} missing tabs"
        normal_text = str(view.get("title") or "") + "\n" + "\n".join(str(value) for value in tabs.values())
        result = validate_player_panel_text(normal_text)
        assert result.ok, f"{cid} leaked normal player text: {result.issues[:4]}"
        debug_text = "\n".join(str(value) for value in build_citizen_panel_tabs(queue, holoverse_root=root, debug_raw_ids=True)["tabs"].values())
        assert str(queue.get("citizen_id")) in debug_text, f"{cid} debug panel did not keep raw IDs available"
        checked += 1
    print(json.dumps({"ok": True, "checked_citizens": checked, "sample_place": resolver.place("res_alpha_home_a_node")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
