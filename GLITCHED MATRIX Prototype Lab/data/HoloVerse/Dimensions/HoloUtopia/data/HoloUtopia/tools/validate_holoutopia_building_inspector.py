from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from holoutopia_building_inspector import build_highlight_index, inspect_building, load_highlight_rules, write_highlight_index
from holoutopia_citizen_simulation import load_simulation_inputs


def main() -> int:
    issues: list[str] = []
    inputs = load_simulation_inputs(ROOT)
    towns = inputs.get("towns", {})
    neighborhoods = inputs.get("neighborhoods", {})
    citizens = inputs.get("citizen_manifest", {}).get("citizens", [])
    expected_blocks = sum(len(town.get("town_blocks", [])) for town in towns.values() if isinstance(town, dict))
    expected_lots = sum(len(n.get("lots", [])) for n in neighborhoods.values() if isinstance(n, dict))
    citizen_ids = {str(c.get("id")) for c in citizens if isinstance(c, dict)}

    try:
        rules = load_highlight_rules(ROOT)
    except Exception as exc:
        issues.append(f"highlight rules failed to load: {exc}")
        rules = {}
    if rules.get("lazy_interior_contract", {}).get("max_loaded_interiors") != 1:
        issues.append("lazy interior contract must keep max_loaded_interiors at 1")
    if rules.get("runtime_writes_allowed") is not False:
        issues.append("highlight rules must be read-only")

    index = build_highlight_index(ROOT, clock="12:00")
    records = index.get("records", {}) if isinstance(index.get("records"), dict) else {}
    totals = index.get("totals", {}) if isinstance(index.get("totals"), dict) else {}

    if totals.get("district_block_records") != expected_blocks:
        issues.append(f"district block record mismatch: {totals.get('district_block_records')} != {expected_blocks}")
    if totals.get("residential_lot_records") != expected_lots:
        issues.append(f"residential lot record mismatch: {totals.get('residential_lot_records')} != {expected_lots}")
    if len(records) != expected_blocks + expected_lots:
        issues.append(f"highlight record mismatch: {len(records)} != {expected_blocks + expected_lots}")

    for cid, citizen in [(str(c.get("id")), c) for c in citizens if isinstance(c, dict)]:
        home_lot = str(citizen.get("home_lot_id", ""))
        if home_lot not in records:
            issues.append(f"citizen {cid} home lot is not inspectable: {home_lot}")
        job = citizen.get("job") if isinstance(citizen.get("job"), dict) else {}
        work_node = str(job.get("work_node", ""))
        if work_node and not any(cid in [str(w.get("id")) for w in rec.get("workers", [])] for rec in records.values()):
            issues.append(f"citizen {cid} job is not represented in any inspector worker list: {work_node}")

    resident_assignments = sum(len(r.get("residents", [])) for r in records.values() if r.get("highlight_kind") == "residential_lot")
    if resident_assignments != len(citizen_ids):
        issues.append(f"resident assignment mismatch: {resident_assignments} != {len(citizen_ids)}")
    worker_assignments = sum(len(r.get("workers", [])) for r in records.values())
    if worker_assignments < len(citizen_ids):
        issues.append(f"worker assignment too low: {worker_assignments} < {len(citizen_ids)}")

    lazy_interior_records = [r for r in records.values() if r.get("inspection_policy", {}).get("load_interior_on_highlight")]
    if not lazy_interior_records:
        issues.append("expected at least one lazy-load interior record")
    for record in records.values():
        if record.get("inspection_policy", {}).get("load_interior_on_highlight") and not record.get("interior_blueprint_id"):
            issues.append(f"record loads interior but has no interior_blueprint_id: {record.get('id')}")
        if not record.get("inspection_policy", {}).get("selectable"):
            issues.append(f"record is not selectable: {record.get('id')}")
        massing = record.get("massing") if isinstance(record.get("massing"), dict) else {}
        if int(massing.get("floor_count", 0) or 0) < 1:
            issues.append(f"record has invalid massing floor_count: {record.get('id')}")

    for probe in ("res_alpha_lot_07", "central_core_civic_ring:core_plaza_octagon"):
        try:
            panel = inspect_building(ROOT, probe, clock="12:00")
            if not panel.get("panel_lines"):
                issues.append(f"inspection panel missing lines for {probe}")
        except Exception as exc:
            issues.append(f"inspection probe failed for {probe}: {exc}")

    if not issues:
        out = ROOT.parent / "database" / "utopia" / "inspection" / "building_highlight_index.json"
        write_highlight_index(out, ROOT, clock="12:00")

    payload = {
        "ok": not issues,
        "district_block_records": totals.get("district_block_records"),
        "residential_lot_records": totals.get("residential_lot_records"),
        "highlight_records": totals.get("highlight_records"),
        "residential_capacity": totals.get("residential_capacity"),
        "resident_assignments": resident_assignments,
        "worker_assignments": worker_assignments,
        "lazy_interior_records": len(lazy_interior_records),
        "issues": issues,
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if not issues else 1


if __name__ == "__main__":
    raise SystemExit(main())
