"""Validate authored HoloUtopia NPC identity, schedule, job, and friendship data."""
from __future__ import annotations
import json
from pathlib import Path
import sys


def _find_holoverse_root() -> Path:
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        if parent.name.lower() == "holoverse":
            return parent
    for parent in [here.parent, *here.parents]:
        candidate = parent / "data" / "HoloVerse"
        if candidate.exists():
            return candidate
    raise SystemExit("Could not resolve data/HoloVerse root")


def main() -> int:
    root = _find_holoverse_root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from holoutopia_town_blocks import HoloUtopiaTownError, load_npc_database
    report = {"ok": True, "npc_count": 0, "schedule_count": 0, "relationship_count": 0, "jobs": {}, "errors": []}
    try:
        data = load_npc_database(root)
        npcs = data["manifest"].get("npcs", [])
        schedules = data["schedules"].get("schedules", {})
        relationships = data["relationships"].get("relationships", [])
        report["npc_count"] = len(npcs)
        report["schedule_count"] = len(schedules)
        report["relationship_count"] = len(relationships)
        for npc in npcs:
            job = npc.get("job", {}) if isinstance(npc, dict) else {}
            title = str(job.get("title", "unknown"))
            report["jobs"][title] = report["jobs"].get(title, 0) + 1
    except HoloUtopiaTownError as exc:
        report["ok"] = False
        report["errors"].append(str(exc))
    print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
