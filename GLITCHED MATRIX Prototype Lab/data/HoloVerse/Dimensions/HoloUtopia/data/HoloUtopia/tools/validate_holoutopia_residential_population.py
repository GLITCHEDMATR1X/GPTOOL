from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from holoutopia_citizen_simulation import load_simulation_inputs, simulate_city_at_time
from holoutopia_residential_population import build_population_rules_summary, build_residential_garrison_plan, build_residential_population_frame, load_population_rules
from holoutopia_game_runtime import load_runtime_config


def main() -> int:
    errors: list[str] = []
    rules = load_population_rules(ROOT)
    inputs = load_simulation_inputs(ROOT)
    summary = build_population_rules_summary(ROOT).as_dict()
    plan = build_residential_garrison_plan(inputs, rules)
    runtime = load_runtime_config(ROOT).get("citizen_runtime", {})
    frames = {
        clock: build_residential_population_frame(ROOT, clock, inputs=inputs, rules=rules)
        for clock in ("06:30", "12:00", "18:30", "21:30", "05:30")
    }
    schedule_frame = simulate_city_at_time(ROOT, "06:30", inputs=inputs)

    if int(summary.get("world_population", 0)) != 1000:
        errors.append(f"default world population must be 1000, got {summary.get('world_population')}")
    if str(summary.get("residential_home_town_id")) != "residential_alpha":
        errors.append("all citizens must live in residential_alpha for this pass")
    if int(summary.get("day_seconds", 0)) != 1440:
        errors.append(f"1 real minute = 1 game hour requires full_day_seconds 1440, got {summary.get('day_seconds')}")
    if float(runtime.get("city_day_seconds", 0)) != 1440.0:
        errors.append(f"runtime citizen_runtime.city_day_seconds must be 1440.0, got {runtime.get('city_day_seconds')}")
    if int(summary.get("max_outdoor_per_district", 0)) != 20:
        errors.append("max outdoor population per district must be 20")
    if int(summary.get("energy_active_hours", 0)) != 15 or int(summary.get("recharge_hours", 0)) != 9:
        errors.append("energy rule must be 15 active game hours / 9 home recharge game hours")
    if int(plan.get("resident_count", 0)) != 1000:
        errors.append(f"garrison plan must assign 1000 residents, got {plan.get('resident_count')}")
    if not plan.get("all_garrisons_capped"):
        errors.append("every garrison wing must respect the per-building cap")
    if int(plan.get("max_capacity_per_garrison", 0)) > 50:
        errors.append("largest garrison cap must be 50")
    for clock, frame in frames.items():
        if int(frame.get("outdoor_population", 0)) > 20:
            errors.append(f"{clock}: outdoor population exceeded cap: {frame.get('outdoor_population')}")
        if not frame.get("all_citizens_live_in_residential"):
            errors.append(f"{clock}: residential living rule was not reported")
        if not frame.get("work_and_activities_outside_residential"):
            errors.append(f"{clock}: work/activity rule was not reported")
    if int(frames["06:30"].get("outdoor_population", 0)) <= 0:
        errors.append("06:30 should show sampled outdoor residents departing by foot")
    if int(frames["21:30"].get("home_garrison_population", 0)) != 1000:
        errors.append("21:30 should have all residents inside home garrisons")
    model = schedule_frame.get("residential_population_model") if isinstance(schedule_frame.get("residential_population_model"), dict) else {}
    if int(model.get("world_population", 0)) != 1000:
        errors.append("schedule frame must carry residential population model")

    payload = {"summary": summary, "garrison_count": plan.get("garrison_count"), "frames": {k: {"phase": v.get("phase"), "outdoor": v.get("outdoor_population"), "home": v.get("home_garrison_population"), "outside_residential": v.get("outside_residential_population"), "energy": v.get("average_energy_percent")} for k, v in frames.items()}, "errors": errors}
    if errors:
        print("HoloUtopia residential population validation FAILED")
        print(json.dumps(payload, indent=2))
        return 2
    print("HoloUtopia residential population validation passed")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
