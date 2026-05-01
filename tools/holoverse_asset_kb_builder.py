from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TOOL_VERSION = "0.7.4-pass21-asset-kb-builder"

DEFAULT_REFERENCES = [
    {
        "id": "khronos_fox",
        "name": "Fox",
        "category": "animal",
        "subtype": "fox",
        "source": "KhronosGroup/glTF-Sample-Models/2.0/Fox",
        "source_url": "https://github.com/KhronosGroup/glTF-Sample-Models/tree/main/2.0/Fox",
        "format": "gltf/glb",
        "rigged": True,
        "animations": ["Survey", "Walk", "Run"],
        "license_summary": "Body CC0; rigging/animation CC-BY 4.0; attribution required for animated rig use.",
        "holoverse_region_fit": ["ice", "forest"],
        "training_use": "reference_metadata_and_import_test",
        "promotion_status": "reference_only_until_import_and_attribution",
    },
    {
        "id": "khronos_cesium_man",
        "name": "Cesium Man",
        "category": "person",
        "subtype": "humanoid",
        "source": "KhronosGroup/glTF-Sample-Models/2.0/CesiumMan",
        "source_url": "https://github.com/KhronosGroup/glTF-Sample-Models/tree/main/2.0/CesiumMan",
        "format": "gltf/glb",
        "rigged": True,
        "animations": ["skinned_animation"],
        "license_summary": "Requires source license review before redistribution.",
        "holoverse_region_fit": ["hub", "metropolis", "urban"],
        "training_use": "humanoid_skinning_reference",
        "promotion_status": "reference_only_until_license_review",
    },
    {
        "id": "khronos_rigged_simple",
        "name": "Rigged Simple",
        "category": "person",
        "subtype": "minimal_rig_test",
        "source": "KhronosGroup/glTF-Sample-Models/2.0/RiggedSimple",
        "source_url": "https://github.com/KhronosGroup/glTF-Sample-Models/tree/main/2.0/RiggedSimple",
        "format": "gltf/glb",
        "rigged": True,
        "animations": ["simple_skin_animation"],
        "license_summary": "Requires source license review before redistribution.",
        "holoverse_region_fit": ["tooling", "import_tests"],
        "training_use": "minimal_skinning_reference",
        "promotion_status": "reference_only_until_license_review",
    },
    {
        "id": "khronos_sponza",
        "name": "Sponza",
        "category": "structure",
        "subtype": "building_interior_lighting_test",
        "source": "KhronosGroup/glTF-Sample-Models/2.0/Sponza",
        "source_url": "https://github.com/KhronosGroup/glTF-Sample-Models/tree/main/2.0/Sponza",
        "format": "gltf/glb",
        "rigged": False,
        "animations": [],
        "license_summary": "Requires source license review before redistribution.",
        "holoverse_region_fit": ["metropolis", "urban", "lighting_tests"],
        "training_use": "structure_and_lighting_reference",
        "promotion_status": "reference_only_until_license_review",
    },
    {
        "id": "khronos_virtual_city",
        "name": "Virtual City",
        "category": "structure",
        "subtype": "city_scene",
        "source": "KhronosGroup/glTF-Sample-Models/2.0/VC",
        "source_url": "https://github.com/KhronosGroup/glTF-Sample-Models/tree/main/2.0/VC",
        "format": "gltf/glb",
        "rigged": False,
        "animations": ["scene_animation"],
        "license_summary": "Requires source license review before redistribution.",
        "holoverse_region_fit": ["metropolis", "urban"],
        "training_use": "city_scene_reference",
        "promotion_status": "reference_only_until_license_review",
    },
    {
        "id": "khronos_barramundi_fish",
        "name": "Barramundi Fish",
        "category": "animal",
        "subtype": "fish",
        "source": "KhronosGroup/glTF-Sample-Models/2.0/BarramundiFish",
        "source_url": "https://github.com/KhronosGroup/glTF-Sample-Models/tree/main/2.0/BarramundiFish",
        "format": "gltf/glb",
        "rigged": False,
        "animations": [],
        "license_summary": "Requires source license review before redistribution.",
        "holoverse_region_fit": ["water"],
        "training_use": "water_creature_shape_reference",
        "promotion_status": "reference_only_until_license_review",
    },
    {
        "id": "khronos_duck",
        "name": "Duck",
        "category": "object_or_animal",
        "subtype": "simple_textured_model",
        "source": "KhronosGroup/glTF-Sample-Models/2.0/Duck",
        "source_url": "https://github.com/KhronosGroup/glTF-Sample-Models/tree/main/2.0/Duck",
        "format": "gltf/glb",
        "rigged": False,
        "animations": [],
        "license_summary": "Requires source license review before redistribution.",
        "holoverse_region_fit": ["water", "import_tests"],
        "training_use": "basic_textured_model_reference",
        "promotion_status": "reference_only_until_license_review",
    },
    {
        "id": "khronos_box_textured",
        "name": "Box Textured",
        "category": "object",
        "subtype": "simple_prop_test",
        "source": "KhronosGroup/glTF-Sample-Models/2.0/BoxTextured",
        "source_url": "https://github.com/KhronosGroup/glTF-Sample-Models/tree/main/2.0/BoxTextured",
        "format": "gltf/glb",
        "rigged": False,
        "animations": [],
        "license_summary": "Requires source license review before redistribution.",
        "holoverse_region_fit": ["all", "import_tests"],
        "training_use": "basic_object_import_reference",
        "promotion_status": "reference_only_until_license_review",
    },
]

CATEGORY_RULES = {
    "animal": ["fox", "wolf", "fish", "stag", "deer", "bird", "raven", "moth", "glider", "grazer", "animal", "creature", "fauna", "lizard", "frog", "manta"],
    "person": ["man", "woman", "human", "person", "humanoid", "character", "rigged", "cesium", "avatar"],
    "structure": ["building", "city", "sponza", "house", "tower", "bridge", "interior", "structure", "metro"],
    "object": ["box", "crate", "helmet", "bottle", "lamp", "camera", "lantern", "vehicle", "prop", "object", "duck"],
}

REGION_RULES = {
    "forest": ["forest", "tree", "moss", "stag", "deer", "fox"],
    "green_hills": ["hill", "hills", "grass", "grazer", "sheep", "goat", "rabbit"],
    "mushroom": ["mushroom", "fungus", "spore", "frog", "glow"],
    "desert": ["desert", "sand", "dune", "lizard", "snake"],
    "ice": ["ice", "snow", "crystal", "arctic", "fox", "wolf"],
    "urban": ["urban", "city", "raven", "crow", "rat", "pigeon", "helmet"],
    "water": ["water", "fish", "duck", "manta", "reef", "barramundi"],
    "metropolis": ["metro", "city", "building", "tower", "moth", "virtual"],
}


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _slug(value: str, default: str = "asset") -> str:
    text = re.sub(r"[^a-z0-9]+", "_", str(value).lower()).strip("_")
    return text or default


def _tokens(value: str) -> set[str]:
    return {part for part in re.split(r"[^a-z0-9]+", str(value).lower()) if part}


def _infer_category(asset: dict[str, Any]) -> str:
    explicit = asset.get("category")
    if explicit:
        return str(explicit)
    text = " ".join(str(asset.get(key, "")) for key in ("id", "name", "relative_path", "source", "subtype"))
    tokens = _tokens(text)
    best = (0, "object")
    for category, hints in CATEGORY_RULES.items():
        score = sum(1 for hint in hints if hint in tokens or hint in text.lower())
        if score > best[0]:
            best = (score, category)
    return best[1]


def _infer_region_fit(asset: dict[str, Any]) -> list[str]:
    existing = asset.get("holoverse_region_fit") or asset.get("region_fit")
    if existing:
        return list(existing)
    region_hint = asset.get("region_hint")
    if region_hint:
        return [str(region_hint)]
    text = " ".join(str(asset.get(key, "")) for key in ("id", "name", "relative_path", "source", "subtype"))
    tokens = _tokens(text)
    fits = []
    for region, hints in REGION_RULES.items():
        if any(hint in tokens or hint in text.lower() for hint in hints):
            fits.append(region)
    return fits or ["unassigned"]


def _normalize_reference(asset: dict[str, Any], source_group: str) -> dict[str, Any]:
    name = str(asset.get("name") or asset.get("id") or asset.get("relative_path") or "Unnamed Asset")
    asset_id = str(asset.get("id") or _slug(name))
    gltf = asset.get("gltf_capabilities") or {}
    animations: list[str] = []
    if isinstance(asset.get("animations"), list):
        animations = [str(item) for item in asset.get("animations")]
    elif gltf.get("animations", 0):
        animations = [f"detected_{gltf.get('animations')}_animation_slots"]
    rigged = bool(asset.get("rigged")) or bool(gltf.get("skins", 0))
    category = _infer_category(asset)
    return {
        "id": asset_id,
        "name": name,
        "category": category,
        "subtype": str(asset.get("subtype") or asset.get("body") or asset.get("extension") or "unknown"),
        "source_group": source_group,
        "source": asset.get("source") or asset.get("root") or asset.get("path") or asset.get("source_url") or "unknown",
        "source_url": asset.get("source_url"),
        "relative_path": asset.get("relative_path"),
        "format": asset.get("format") or asset.get("extension"),
        "size_bytes": asset.get("size_bytes"),
        "rigged": rigged,
        "animations": animations,
        "animation_count": len(animations) or int(gltf.get("animations", 0) or 0),
        "skin_count": int(gltf.get("skins", 0) or (1 if rigged else 0)),
        "holoverse_region_fit": _infer_region_fit(asset),
        "license_summary": asset.get("license_summary") or _summarize_license(asset),
        "license_status": _license_status(asset),
        "training_use": asset.get("training_use") or "metadata_reference_only",
        "promotion_status": asset.get("promotion_status") or "candidate_requires_license_and_visual_review",
        "import_status": "not_imported",
        "proof_status": "not_render_proven",
        "notes": asset.get("notes") or [],
    }


def _summarize_license(asset: dict[str, Any]) -> str:
    text = json.dumps(asset.get("license_context") or {}, sort_keys=True).lower()
    if "cc0" in text:
        return "Nearby license/readme signals mention CC0; verify exact asset coverage."
    if "cc-by" in text or "attribution" in text:
        return "Nearby license/readme signals mention attribution; preserve credit before promotion."
    if "mit" in text or "apache" in text or "bsd" in text:
        return "Nearby license/readme signals mention permissive software license; verify art asset coverage."
    if "gpl" in text:
        return "Nearby license/readme signals mention GPL; avoid bundling until reviewed."
    return "No verified license summary; treat as metadata-only until reviewed."


def _license_status(asset: dict[str, Any]) -> str:
    summary = str(asset.get("license_summary") or _summarize_license(asset)).lower()
    if "cc0" in summary:
        return "likely_permissive_verify_scope"
    if "cc-by" in summary or "attribution" in summary:
        return "attribution_required"
    if "gpl" in summary:
        return "blocked_until_review"
    if "requires" in summary or "review" in summary or "unknown" in summary:
        return "needs_review"
    return "needs_review"


def _read_scan_report(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _assets_from_scan(report: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for item in report.get("candidates") or []:
        if item.get("likely_fauna") or item.get("fauna_score", 0) >= 4:
            out.append(_normalize_reference(item, "local_scan_candidate"))
    for item in report.get("known_github_resources") or []:
        mapped = {
            "id": _slug(item.get("name", "github_resource")),
            "name": item.get("name"),
            "category": "animal" if "fox" in str(item.get("name", "")).lower() else "object",
            "subtype": item.get("species_hint") or "reference",
            "source_url": item.get("source_url"),
            "source": item.get("source_url"),
            "format": "gltf/glb",
            "rigged": "animated" in str(item.get("why_relevant", "")).lower(),
            "animations": ["unknown_from_reference"],
            "license_summary": item.get("license_note"),
            "holoverse_region_fit": [str(item.get("region_hint") or "unassigned")],
            "training_use": "reference_metadata_only",
            "promotion_status": item.get("status") or "reference_only",
        }
        out.append(_normalize_reference(mapped, "known_github_reference"))
    return out


def _dedupe_assets(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for item in items:
        asset_id = str(item.get("id") or _slug(item.get("name", "asset")))
        if asset_id not in by_id:
            by_id[asset_id] = item
        else:
            old = by_id[asset_id]
            merged = dict(old)
            merged["source_group"] = ",".join(sorted(set(str(x) for x in [old.get("source_group"), item.get("source_group")] if x)))
            merged["notes"] = list((old.get("notes") or [])) + list((item.get("notes") or []))
            by_id[asset_id] = merged
    return sorted(by_id.values(), key=lambda item: (str(item.get("category")), str(item.get("name"))))


def build_kb(scan_reports: list[str | Path] | None = None, *, include_defaults: bool = True) -> dict[str, Any]:
    assets: list[dict[str, Any]] = []
    if include_defaults:
        assets.extend(_normalize_reference(item, "curated_reference") for item in DEFAULT_REFERENCES)
    for raw in scan_reports or []:
        path = Path(raw).resolve()
        if path.exists():
            assets.extend(_assets_from_scan(_read_scan_report(path)))
    assets = _dedupe_assets(assets)
    licenses = []
    rig_profiles = []
    animation_profiles = []
    region_fit = []
    training_cards = []
    for asset in assets:
        licenses.append({
            "asset_id": asset["id"],
            "license_summary": asset["license_summary"],
            "license_status": asset["license_status"],
            "source": asset.get("source_url") or asset.get("source"),
            "action": "verify before bundling or promotion",
        })
        rig_profiles.append({
            "asset_id": asset["id"],
            "rigged": asset["rigged"],
            "skin_count": asset["skin_count"],
            "category": asset["category"],
            "expected_import_path": "preview_import_before_holoverse_promotion",
        })
        animation_profiles.append({
            "asset_id": asset["id"],
            "animation_count": asset["animation_count"],
            "animations": asset["animations"],
            "proof_required": bool(asset["animation_count"]),
        })
        region_fit.append({
            "asset_id": asset["id"],
            "regions": asset["holoverse_region_fit"],
            "category": asset["category"],
            "promotion_rule": "region_fit_is_suggestion_until_screenshot_proof",
        })
        training_cards.append({
            "asset_id": asset["id"],
            "name": asset["name"],
            "category": asset["category"],
            "learn": [
                "silhouette proportions",
                "rig/animation presence",
                "region fit metadata",
                "import constraints",
            ],
            "do_not_learn": [
                "do not copy unlicensed geometry into HoloVerse",
                "do not bundle source asset without license approval",
                "do not promote without Panda3D screenshot proof",
            ],
            "allowed_use": asset["training_use"],
        })
    return {
        "schema_version": "holoverse_asset_kb.v1",
        "tool_version": TOOL_VERSION,
        "created_at": _now(),
        "policy": {
            "metadata_first": True,
            "copy_assets_by_default": False,
            "requires_license_review": True,
            "requires_visual_proof_before_promotion": True,
            "codex_instruction": "Use this KB to choose candidates, write import plans, and build procedural equivalents. Do not copy or promote assets without license/proof gates.",
        },
        "assets": assets,
        "licenses": licenses,
        "rig_profiles": rig_profiles,
        "animation_profiles": animation_profiles,
        "holoverse_region_fit": region_fit,
        "codex_training_manifest": training_cards,
    }


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _write_markdown(path: Path, kb: dict[str, Any]) -> None:
    lines = [
        "# HoloVerse Asset Knowledge Base",
        "",
        f"- Tool: `{kb.get('tool_version')}`",
        f"- Assets: `{len(kb.get('assets') or [])}`",
        f"- Metadata first: `{kb.get('policy', {}).get('metadata_first')}`",
        f"- Copy assets by default: `{kb.get('policy', {}).get('copy_assets_by_default')}`",
        "",
        "## Assets",
        "",
    ]
    for asset in kb.get("assets") or []:
        lines.append(f"- **{asset.get('name')}** (`{asset.get('id')}`) - {asset.get('category')} / {asset.get('subtype')} / regions: {', '.join(asset.get('holoverse_region_fit') or [])}")
    lines.extend(["", "## Codex rule", "", kb.get("policy", {}).get("codex_instruction", "")])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_kb(kb: dict[str, Any], output_dir: str | Path) -> dict[str, str]:
    out = Path(output_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    files = {
        "assets": out / "assets.json",
        "licenses": out / "licenses.json",
        "rig_profiles": out / "rig_profiles.json",
        "animation_profiles": out / "animation_profiles.json",
        "holoverse_region_fit": out / "holoverse_region_fit.json",
        "codex_training_manifest": out / "codex_training_manifest.json",
        "full_kb": out / "holoverse_asset_kb.json",
        "readme": out / "README.md",
    }
    _write_json(files["assets"], {"schema_version": "asset_kb_assets.v1", "assets": kb["assets"]})
    _write_json(files["licenses"], {"schema_version": "asset_kb_licenses.v1", "licenses": kb["licenses"]})
    _write_json(files["rig_profiles"], {"schema_version": "asset_kb_rig_profiles.v1", "rig_profiles": kb["rig_profiles"]})
    _write_json(files["animation_profiles"], {"schema_version": "asset_kb_animation_profiles.v1", "animation_profiles": kb["animation_profiles"]})
    _write_json(files["holoverse_region_fit"], {"schema_version": "asset_kb_region_fit.v1", "holoverse_region_fit": kb["holoverse_region_fit"]})
    _write_json(files["codex_training_manifest"], {"schema_version": "asset_kb_codex_training_manifest.v1", "policy": kb["policy"], "training_cards": kb["codex_training_manifest"]})
    _write_json(files["full_kb"], kb)
    _write_markdown(files["readme"], kb)
    return {key: str(value) for key, value in files.items()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a metadata-first HoloVerse asset knowledge base for Codex/GPTOOL.")
    parser.add_argument("scan_reports", nargs="*", help="Optional fauna_resource_scan.json files to ingest.")
    parser.add_argument("--output-dir", default="data/asset_kb")
    parser.add_argument("--no-defaults", action="store_true", help="Do not include curated reference entries.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    kb = build_kb(args.scan_reports, include_defaults=not args.no_defaults)
    files = write_kb(kb, args.output_dir)
    result = {
        "schema_version": "holoverse_asset_kb_build_result.v1",
        "tool_version": TOOL_VERSION,
        "ok": True,
        "asset_count": len(kb["assets"]),
        "output_dir": str(Path(args.output_dir).resolve()),
        "files": files,
    }
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print("HoloVerse asset KB build: PASS")
        print(f"Assets: {result['asset_count']}")
        print(f"Output: {result['output_dir']}")
        print(f"Codex manifest: {files['codex_training_manifest']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
