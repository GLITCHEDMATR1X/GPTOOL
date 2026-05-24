"""Validate HoloUtopia single-district Residential focus mode.

This guard makes sure screenshots/runtime tests cannot accidentally drift back
into the 3x3 city view while the Residential district is the only active scope.
"""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from holoutopia_citizen_simulation import load_simulation_inputs, simulate_city_at_time
from holoutopia_game_runtime import build_runtime_summary, load_runtime_config


def _validate_config(errors: list[str]) -> None:
    config = load_runtime_config(ROOT)
    focus = config.get("district_focus") if isinstance(config.get("district_focus"), dict) else {}
    if focus.get("enabled") is not True:
        errors.append("district_focus.enabled must be true")
    if str(focus.get("active_town_id")) != "residential_alpha":
        errors.append("active_town_id must be residential_alpha")
    if focus.get("lock_to_active_district") is not True:
        errors.append("Residential focus must lock to the active district")
    if focus.get("hide_other_districts_until_unlock") is not True:
        errors.append("other districts must stay hidden until unlock")
    allowed = [str(item) for item in focus.get("allowed_town_ids", [])] if isinstance(focus.get("allowed_town_ids"), list) else []
    if allowed != ["residential_alpha"]:
        errors.append(f"allowed_town_ids must only contain residential_alpha, got {allowed!r}")
    layers = config.get("render_layers") if isinstance(config.get("render_layers"), dict) else {}
    if layers.get("district_activity_markers") is not True:
        errors.append("district activity markers must be enabled for detail mode")
    summary = build_runtime_summary(ROOT).as_dict()
    if summary.get("active_district_id") != "residential_alpha":
        errors.append(f"runtime summary active district mismatch: {summary.get('active_district_id')!r}")
    if summary.get("focused_district_mode") is not True:
        errors.append("runtime summary did not report focused district mode")


def _validate_simulation_scope(errors: list[str]) -> None:
    inputs = load_simulation_inputs(ROOT)
    frame = simulate_city_at_time(ROOT, "18:00", inputs=inputs)
    citizens = frame.get("citizens", {}) if isinstance(frame.get("citizens"), dict) else {}
    residential = {cid: c for cid, c in citizens.items() if isinstance(c, dict) and c.get("town_id") == "residential_alpha"}
    if len(residential) != 8:
        errors.append(f"expected 8 Residential citizens at detail sample, got {len(residential)}")
    leaked = [cid for cid, c in residential.items() if c.get("town_id") != "residential_alpha"]
    if leaked:
        errors.append(f"non-residential citizens leaked into Residential filter: {leaked}")


def _validate_panda_runtime(errors: list[str]) -> None:
    try:
        from panda3d.core import loadPrcFileData
        loadPrcFileData("", "\n".join([
            "window-type offscreen",
            "load-display p3tinydisplay",
            "audio-library-name null",
            "show-frame-rate-meter 0",
        ]))
        from direct.showbase.ShowBase import ShowBase
        from holoutopia_game_runtime import install_holoutopia_runtime
    except Exception as exc:
        errors.append(f"Panda3D import failed: {exc}")
        return
    base = None
    try:
        base = ShowBase(windowType="offscreen")
        base.root_3d = base.render.attachNewNode("root_3d")
        base.world_root = base.root_3d.attachNewNode("holoverse_world_root")
        runtime = install_holoutopia_runtime(base, ROOT)
        if not runtime.installed:
            errors.append(f"runtime did not install: {runtime.error}")
            return
        if runtime.active_town_id != "residential_alpha":
            errors.append(f"runtime active_town_id mismatch: {runtime.active_town_id!r}")
        if not runtime.district_focus_enabled:
            errors.append("runtime district_focus_enabled is false")
        child_names = [child.getName() for child in runtime.city_root.getChildren()] if runtime.city_root is not None else []
        if not any("residential_alpha" in name for name in child_names):
            errors.append(f"Residential district node missing from city root: {child_names}")
        forbidden = [name for name in child_names if any(token in name for token in ("central_core", "market_crossing", "harbor_grid", "archive_quarter", "industrial_yard", "security_gate", "glitched_quarantine", "civic_commons"))]
        if forbidden:
            errors.append(f"non-Residential district nodes rendered in focused mode: {forbidden}")
        marker_towns = []
        for cid, node in runtime._marker_nodes.items():
            citizen = runtime._last_citizen_frame.get("citizens", {}).get(cid, {}) if isinstance(runtime._last_citizen_frame.get("citizens"), dict) else {}
            marker_towns.append(str(citizen.get("town_id") or ""))
        if len(marker_towns) != 8:
            errors.append(f"expected 8 visible Residential markers, got {len(marker_towns)}")
        if any(town != "residential_alpha" for town in marker_towns):
            errors.append(f"visible marker town leak: {marker_towns}")
        activity_count = runtime.activities_root.getPythonTag("holoutopia_activity_group_count") if runtime.activities_root is not None else 0
        if int(activity_count or 0) <= 0:
            errors.append("focused district activity markers were not created")
    finally:
        if base is not None:
            try:
                base.destroy()
            except Exception:
                pass


def main() -> int:
    errors: list[str] = []
    _validate_config(errors)
    _validate_simulation_scope(errors)
    _validate_panda_runtime(errors)
    if errors:
        print("HoloUtopia Residential focus validation FAILED")
        for error in errors:
            print(" -", error)
        return 2
    print("[OK] HoloUtopia Residential focus validated")
    print("[OK] active_town_id=residential_alpha visible_markers=8 other_districts_hidden activity_markers=on")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
