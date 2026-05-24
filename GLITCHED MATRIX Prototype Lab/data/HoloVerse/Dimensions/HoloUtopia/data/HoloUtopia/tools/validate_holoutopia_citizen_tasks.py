"""Validate HoloUtopia citizen task queues and movable panel contract."""
from __future__ import annotations

import json
import sys
from pathlib import Path


def _find_holoverse_root() -> Path:
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        if parent.name.lower() in {"holoverse", "holoutopia"} and (parent / "holoutopia_citizen_tasks.py").exists():
            return parent
    for parent in [here.parent, *here.parents]:
        candidate = parent / "data" / "HoloUtopia"
        if (candidate / "holoutopia_citizen_tasks.py").exists():
            return candidate
    raise SystemExit("Could not resolve data/HoloUtopia root")


def main() -> int:
    root = _find_holoverse_root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from holoutopia_citizen_tasks import build_all_citizen_task_queues, build_task_summary, data_root_from_holoverse
    from holoutopia_snap_panels import build_snap_panel_summary

    data_root = data_root_from_holoverse(root)
    tasks_dir = data_root / "database" / "utopia" / "tasks"
    catalog = json.loads((tasks_dir / "task_type_catalog.json").read_text(encoding="utf-8"))
    rules = json.loads((tasks_dir / "citizen_task_rules.json").read_text(encoding="utf-8"))
    assert isinstance(catalog.get("task_types"), dict) and len(catalog["task_types"]) >= 8, "task catalog too small"
    assert rules.get("runtime_contract", {}).get("authored_files_are_read_only") is True, "task runtime contract must keep authored data read-only"
    snapshot = build_all_citizen_task_queues(root, clock="08:00")
    queues = snapshot.get("queues", {})
    assert snapshot.get("citizen_count", 0) >= 44, "expected at least 44 citizens"
    assert isinstance(queues, dict) and len(queues) == snapshot.get("citizen_count"), "queue count mismatch"
    for cid, queue in queues.items():
        assert queue.get("purpose"), f"{cid} missing purpose"
        assert isinstance(queue.get("current_task"), dict), f"{cid} missing current task"
        assert queue["current_task"].get("target_node") is not None, f"{cid} current task missing target"
        assert isinstance(queue.get("queued_tasks"), list) and queue["queued_tasks"], f"{cid} missing queued tasks"
        assert queue.get("mood"), f"{cid} missing mood"
        assert 0 <= int(queue.get("energy", -1)) <= 100, f"{cid} invalid energy"
    panel = build_snap_panel_summary().as_dict()
    assert panel["movable"] and panel["close_button"] and panel["pin_button"], "panel controls incomplete"
    assert panel["snap_left"] and panel["snap_right"] and panel["snap_top"] and panel["snap_bottom"], "panel snap contract incomplete"
    summary = build_task_summary(root, clock="08:00").as_dict()
    print(json.dumps({"ok": True, "summary": summary, "panel": panel}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
