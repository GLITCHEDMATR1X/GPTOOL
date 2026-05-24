"""Validate HoloVerse dimension-index routing without importing Panda3D."""
from __future__ import annotations

import json
import sys
from pathlib import Path


def norm(value: object) -> str:
    text = str(value or "").strip().lower()
    out = []
    last_sep = False
    for ch in text:
        if ch.isalnum():
            out.append(ch)
            last_sep = False
        else:
            if not last_sep:
                out.append("_")
                last_sep = True
    return "".join(out).strip("_")


def read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    index_path = root / "Dimensions" / "dimension_index.json"
    payload = read_json(index_path)
    errors: list[str] = []
    warnings: list[str] = []

    dimensions = payload.get("dimensions") if isinstance(payload.get("dimensions"), dict) else {}
    by_bot = payload.get("by_bot") if isinstance(payload.get("by_bot"), dict) else {}
    bot_routes = payload.get("bot_routes") if isinstance(payload.get("bot_routes"), dict) else {}

    if not dimensions:
        errors.append("dimension_index.json has no dimensions map")
    if not by_bot:
        errors.append("dimension_index.json has no by_bot map")
    if not bot_routes:
        errors.append("dimension_index.json has no bot_routes map")

    aliases: dict[str, str] = {}
    for dim_id, record in dimensions.items():
        if not isinstance(record, dict):
            errors.append(f"dimension {dim_id!r} is not an object")
            continue
        canonical_id = norm(record.get("id") or dim_id)
        if canonical_id != norm(dim_id):
            warnings.append(f"dimension key/id mismatch: key={dim_id!r} id={record.get('id')!r}")
        for candidate in (dim_id, record.get("id"), record.get("name"), record.get("title"), Path(str(record.get("folder") or "")).name):
            key = norm(candidate)
            if key:
                aliases.setdefault(key, dim_id)

        folder = root / str(record.get("folder") or "").replace("\\", "/")
        manifest_path = folder / "holoverse_mode_manifest.json"
        if manifest_path.exists():
            manifest = read_json(manifest_path)
            for candidate in (manifest.get("id"), manifest.get("title"), manifest.get("entry"), folder.name):
                key = norm(candidate)
                if key:
                    aliases.setdefault(key, dim_id)
            manifest_id = norm(manifest.get("id"))
            if manifest_id and manifest_id != norm(record.get("id") or dim_id):
                errors.append(f"manifest id mismatch for {dim_id}: manifest={manifest.get('id')!r}")
            for field in ("bot_owner", "region_owner", "launch_type", "runtime_installer"):
                record_value = str(record.get(field) or "").strip()
                manifest_value = str(manifest.get(field) or "").strip()
                if manifest_value and record_value and record_value != manifest_value:
                    warnings.append(f"{dim_id}.{field} differs from manifest: index={record_value!r} manifest={manifest_value!r}")
        else:
            warnings.append(f"missing manifest for dimension {dim_id}: {manifest_path}")

        if str(record.get("launch_type") or "") == "in_world_region":
            runtime_text = str(record.get("runtime") or "").replace("\\", "/")
            runtime_path = root / runtime_text if runtime_text else Path("")
            if not runtime_text or not runtime_path.exists():
                errors.append(f"in-world dimension {dim_id} has missing runtime: {runtime_text!r}")
            if not str(record.get("runtime_installer") or "").strip():
                errors.append(f"in-world dimension {dim_id} has no runtime_installer")

    for bot, dim_ref in by_bot.items():
        dim_id = aliases.get(norm(dim_ref), norm(dim_ref))
        if dim_id not in dimensions:
            errors.append(f"bot {bot!r} maps to missing dimension {dim_ref!r}")
            continue
        route = bot_routes.get(bot)
        if not isinstance(route, dict):
            errors.append(f"bot {bot!r} has no bot_routes record")
            continue
        route_dim = aliases.get(norm(route.get("dimension_id")), norm(route.get("dimension_id")))
        if route_dim != dim_id:
            errors.append(f"bot {bot!r} by_bot={dim_id!r} but route dimension_id={route.get('dimension_id')!r}")
        record = dimensions[dim_id]
        for field in ("launch_type", "route", "transition_route", "placeholder_mode"):
            if route.get(field) != record.get(field):
                errors.append(f"bot {bot!r} {field} mismatch: route={route.get(field)!r} dimension={record.get(field)!r}")

    result = {
        "index": str(index_path),
        "dimension_count": len(dimensions),
        "bot_count": len(by_bot),
        "errors": errors,
        "warnings": warnings,
        "ok": not errors,
    }
    print(json.dumps(result, indent=2))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
