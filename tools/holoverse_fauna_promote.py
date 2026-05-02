from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TOOL_VERSION = "0.7.1-pass18-fauna-promotion-gate"
PROTECTED_ROUTES = ["Urban/Sable", "Metropolis/Archivist", "points-ui", "esc-exit", "screenshots"]


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _preview_paths(preview_dir: Path) -> dict[str, Path]:
    return {
        "settings": preview_dir / "settings" / "fauna_preview_settings.json",
        "manifest": preview_dir / "assets" / "fauna" / "fauna_manifest.json",
        "proof": preview_dir / "reports" / "fauna_preview_scene_proof.json",
        "generation": preview_dir / "reports" / "preview_generation_result.json",
    }


def _load_preview(preview_dir: Path) -> dict[str, Any]:
    paths = _preview_paths(preview_dir)
    if not paths["manifest"].exists():
        raise FileNotFoundError(f"Missing fauna manifest: {paths['manifest']}")
    manifest = _read_json(paths["manifest"])
    settings = _read_json(paths["settings"]) if paths["settings"].exists() else {}
    proof = _read_json(paths["proof"]) if paths["proof"].exists() else None
    generation = _read_json(paths["generation"]) if paths["generation"].exists() else None
    return {"preview_dir": str(preview_dir), "paths": {k: str(v) for k, v in paths.items()}, "manifest": manifest, "settings": settings, "proof": proof, "generation": generation}


def _select_species(fauna: list[dict[str, Any]], approve: str) -> list[dict[str, Any]]:
    approve = (approve or "").strip()
    if not approve or approve.lower() in {"none", "dry-run"}:
        return []
    if approve.lower() == "all":
        return list(fauna)
    wanted = {x.strip().lower() for x in approve.split(",") if x.strip()}
    return [item for item in fauna if str(item.get("id", "")).lower() in wanted or str(item.get("name", "")).lower() in wanted]


def _merge_manifest(existing: dict[str, Any], approved: list[dict[str, Any]]) -> dict[str, Any]:
    merged = dict(existing or {})
    merged.setdefault("schema_version", "holoverse_fauna_manifest.v1")
    merged.setdefault("fauna", [])
    by_id = {str(item.get("id")): dict(item) for item in merged.get("fauna") or [] if item.get("id")}
    for item in approved:
        candidate = dict(item)
        candidate["preview_status"] = "approved_for_holoverse"
        candidate["approved_at"] = _now()
        by_id[str(candidate.get("id"))] = candidate
    merged["fauna"] = sorted(by_id.values(), key=lambda item: str(item.get("id", "")))
    merged["updated_at"] = _now()
    merged["source"] = "gptool fauna promotion gate"
    return merged


def _markdown(plan: dict[str, Any]) -> str:
    lines = [
        "# HoloVerse Fauna Promotion Plan",
        "",
        f"- Tool: `{TOOL_VERSION}`",
        f"- Preview: `{plan['preview_dir']}`",
        f"- Target: `{plan.get('target_manifest')}`",
        f"- Mode: `{'apply' if plan.get('applied') else 'dry-run'}`",
        f"- Proof required: `{plan.get('proof_required')}`",
        f"- Proof found: `{plan.get('proof_found')}`",
        "",
        "## Protected routes",
        "",
    ]
    for route in PROTECTED_ROUTES:
        lines.append(f"- {route}")
    lines.extend(["", "## Approved species", ""])
    approved = plan.get("approved_species") or []
    if not approved:
        lines.append("No species selected. Re-run with `--approve all` or a comma-separated species id list.")
    else:
        for item in approved:
            lines.append(f"- **{item.get('name')}** (`{item.get('id')}`) — {item.get('region')} / {item.get('bot')}")
    lines.extend(["", "## Notes", ""])
    for note in plan.get("notes") or []:
        lines.append(f"- {note}")
    return "\n".join(lines) + "\n"


def plan_promotion(
    preview_dir: str | Path,
    target_manifest: str | Path | None = None,
    *,
    approve: str = "",
    apply: bool = False,
    require_proof: bool = False,
) -> dict[str, Any]:
    preview = Path(preview_dir).resolve()
    loaded = _load_preview(preview)
    fauna = list((loaded.get("manifest") or {}).get("fauna") or [])
    approved = _select_species(fauna, approve)
    proof_found = bool(loaded.get("proof"))
    blockers: list[str] = []
    notes: list[str] = []
    if require_proof and not proof_found:
        blockers.append("Visual proof JSON is required but was not found.")
    if apply and not approved:
        blockers.append("Apply requested, but no species were approved.")
    if not target_manifest:
        target_manifest = preview / "reports" / "approved_fauna_manifest.json"
        notes.append("No HoloVerse target manifest supplied; writing approved manifest into preview reports only.")
    target = Path(target_manifest).resolve()
    existing = _read_json(target) if target.exists() else {"schema_version": "holoverse_fauna_manifest.v1", "fauna": []}
    merged = _merge_manifest(existing, approved)
    applied = False
    if apply and not blockers:
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            backup = target.with_suffix(target.suffix + f".bak_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
            shutil.copy2(target, backup)
            notes.append(f"Backed up existing target manifest to {backup}.")
        _write_json(target, merged)
        applied = True
    plan = {
        "schema_version": "holoverse_fauna_promotion_plan.v1",
        "tool_version": TOOL_VERSION,
        "created_at": _now(),
        "preview_dir": str(preview),
        "target_manifest": str(target),
        "proof_required": bool(require_proof),
        "proof_found": proof_found,
        "apply_requested": bool(apply),
        "applied": applied,
        "blockers": blockers,
        "protected_routes": PROTECTED_ROUTES,
        "candidate_count": len(fauna),
        "approved_count": len(approved),
        "approved_species": approved,
        "notes": notes,
        "merged_manifest_preview": merged,
    }
    _write_json(preview / "reports" / "fauna_promotion_plan.json", plan)
    _write_text(preview / "reports" / "fauna_promotion_plan.md", _markdown(plan))
    return plan


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Plan or apply approved HoloVerse fauna preview promotion.")
    parser.add_argument("preview_dir")
    parser.add_argument("--target-manifest", help="Target HoloVerse fauna manifest. Omit to write an approved manifest inside the preview reports folder.")
    parser.add_argument("--approve", default="", help="Species ids/names separated by commas, or 'all'. Default selects none.")
    parser.add_argument("--apply", action="store_true", help="Write the merged target manifest. Default is dry-run only.")
    parser.add_argument("--require-proof", action="store_true", help="Block promotion unless reports/fauna_preview_scene_proof.json exists.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    plan = plan_promotion(args.preview_dir, args.target_manifest, approve=args.approve, apply=args.apply, require_proof=args.require_proof)
    if args.json:
        print(json.dumps(plan, indent=2))
    else:
        status = "APPLIED" if plan["applied"] else "DRY-RUN"
        if plan["blockers"]:
            status = "BLOCKED"
        print(f"HoloVerse fauna promotion: {status}")
        print(f"Preview: {plan['preview_dir']}")
        print(f"Approved: {plan['approved_count']} / {plan['candidate_count']}")
        print(f"Plan JSON: {Path(plan['preview_dir']) / 'reports' / 'fauna_promotion_plan.json'}")
        print(f"Plan Markdown: {Path(plan['preview_dir']) / 'reports' / 'fauna_promotion_plan.md'}")
        for blocker in plan["blockers"]:
            print(f"BLOCKER: {blocker}")
    return 0 if not plan["blockers"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
