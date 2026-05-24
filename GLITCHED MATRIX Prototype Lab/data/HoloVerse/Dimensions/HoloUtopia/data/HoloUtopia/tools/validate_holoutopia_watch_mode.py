from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from holoutopia_watch_mode import build_watch_snapshot, format_watch_lines


def _check_clock(clock: str) -> None:
    snap = build_watch_snapshot(ROOT, clock)
    assert snap["watch_mode_active"] is True
    assert snap["join_hook_ready"] is True
    assert snap["join_mode_active"] is False
    assert snap["world_population"] == 1000
    assert snap["visible_total"] <= 40  # activity + residential/commute reps may be present.
    assert snap["active_district_label"] in {"Central Simulation Hub", "Residential Alpha"}
    assert snap["safety"]["read_only"] is True
    assert snap["safety"]["collisionless_panel"] is True
    assert snap["safety"]["visible_citizens_street_safe"] is True
    lines = format_watch_lines(snap)
    assert lines[0] == "HOLOUTOPIA WATCH MODE"
    assert any("Goal: watch over now" in line for line in lines)
    joined = "\n".join(lines)
    assert "_cluster" not in joined
    assert "central_core_civic_ring" not in joined
    assert "act_sim_" not in joined


def main() -> int:
    for clock in ("07:15", "12:45", "18:15", "20:35", "23:30"):
        _check_clock(clock)
    print("[OK] HoloUtopia Watch Mode validated")
    print("[OK] watch over city now; join hook ready but inactive")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
