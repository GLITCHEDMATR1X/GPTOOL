from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from holoutopia_citizen_simulation import DEFAULT_SAMPLE_TIMES, events_as_jsonl, simulate_city_day, write_simulation_jsonl


def main() -> int:
    parser = argparse.ArgumentParser(description="Simulate one HoloUtopia citizen day from authored schedules.")
    parser.add_argument("--sample-times", nargs="*", default=list(DEFAULT_SAMPLE_TIMES), help="Clock samples such as 06:00 08:00 12:00 17:30 21:00")
    parser.add_argument("--danger", action="store_true", help="Apply danger overrides for every sample.")
    parser.add_argument("--json", action="store_true", help="Print the full simulation frame JSON.")
    parser.add_argument("--output-log", default="", help="Optional JSONL path for append-only activity events.")
    args = parser.parse_args()

    result = simulate_city_day(ROOT, args.sample_times, danger_state=args.danger)
    if args.output_log:
        write_simulation_jsonl(Path(args.output_log), result["frames"])
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(json.dumps({
            "ok": True,
            "sample_times": result["sample_times"],
            "danger_state": result["danger_state"],
            "citizens": result["citizen_count"],
            "frames": [
                {
                    "clock": frame["clock"],
                    "citizens": frame["citizen_count"],
                    "by_activity": frame["by_activity"],
                    "by_town": frame["by_town"],
                    "private_home_hidden": frame["private_home_hidden"],
                    "issues": frame["issues"],
                }
                for frame in result["frames"]
            ],
            "jsonl_event_count": sum(len(frame.get("events", [])) for frame in result["frames"]),
        }, indent=2, ensure_ascii=False))
        if args.output_log:
            print(f"activity_log={Path(args.output_log)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
