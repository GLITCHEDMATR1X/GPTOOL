from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TOOL_VERSION = "0.7.3-pass20-fauna-resource-scan"
ASSET_EXTENSIONS = {".glb", ".gltf", ".fbx", ".obj", ".dae", ".blend", ".bam", ".egg"}
SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", ".mypy_cache", "node_modules", "dist", "build", "venv", ".venv"}

FAUNA_TOKENS = {
    "fox", "wolf", "dog", "cat", "stag", "deer", "elk", "moose", "horse", "boar", "goat", "sheep", "cow", "bull", "bison",
    "rabbit", "hare", "squirrel", "bird", "raven", "crow", "owl", "eagle", "hawk", "moth", "butterfly", "bee", "insect",
    "fish", "shark", "whale", "dolphin", "manta", "ray", "crab", "frog", "toad", "lizard", "snake", "turtle", "dragon",
    "animal", "creature", "fauna", "beast", "glider", "grazer", "runner", "mammal", "amphibian", "reptile",
}
REGION_HINTS = {
    "forest": ["forest", "tree", "moss", "stag", "deer", "owl"],
    "green_hills": ["hill", "hills", "grass", "grazer", "rabbit", "sheep", "goat"],
    "mushroom": ["mushroom", "fungus", "spore", "frog", "toad", "glow"],
    "desert": ["desert", "sand", "dune", "lizard", "snake", "scorpion", "camel"],
    "ice": ["ice", "snow", "crystal", "arctic", "fox", "wolf"],
    "urban": ["urban", "ash", "raven", "crow", "rat", "pigeon"],
    "water": ["water", "reef", "fish", "manta", "ray", "shark", "whale", "dolphin"],
    "metropolis": ["metro", "moth", "butterfly", "city", "glass"],
}

KNOWN_GITHUB_RESOURCES = [
    {
        "name": "Khronos glTF Sample Models - Fox",
        "source_url": "https://github.com/KhronosGroup/glTF-Sample-Models/tree/main/2.0/Fox",
        "asset_path_hint": "2.0/Fox/glTF/Fox.gltf or 2.0/Fox/glTF-Binary/Fox.glb",
        "species_hint": "fox",
        "region_hint": "ice or forest",
        "why_relevant": "Animated low-poly fox with Survey, Walk, and Run cycles; useful as the first rig/animation proof target.",
        "license_note": "Model body is CC0; rigging/animation is CC-BY 4.0, so attribution must be preserved before promotion.",
        "status": "candidate_reference_only",
    },
]


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _tokenize(value: str) -> set[str]:
    return {tok for tok in re.split(r"[^a-z0-9]+", value.lower()) if tok}


def _score_tokens(tokens: set[str]) -> int:
    score = 0
    for token in tokens:
        if token in FAUNA_TOKENS:
            score += 4
        for fauna in FAUNA_TOKENS:
            if fauna and fauna in token and token != fauna:
                score += 2
    return score


def _region_hint(tokens: set[str]) -> str | None:
    best: tuple[int, str | None] = (0, None)
    for region, hints in REGION_HINTS.items():
        score = 0
        for hint in hints:
            if hint in tokens:
                score += 3
            for token in tokens:
                if hint in token and hint != token:
                    score += 1
        if score > best[0]:
            best = (score, region)
    return best[1]


def _read_small_text(path: Path, limit: int = 700_000) -> str:
    try:
        if path.stat().st_size > limit:
            return ""
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def _gltf_capabilities(path: Path) -> dict[str, Any]:
    if path.suffix.lower() != ".gltf":
        return {"checked": False, "reason": "not_gltf_json"}
    text = _read_small_text(path)
    if not text:
        return {"checked": False, "reason": "empty_or_too_large"}
    try:
        data = json.loads(text)
    except Exception as exc:
        return {"checked": False, "reason": f"json_error:{type(exc).__name__}"}
    return {
        "checked": True,
        "animations": len(data.get("animations") or []),
        "skins": len(data.get("skins") or []),
        "nodes": len(data.get("nodes") or []),
        "meshes": len(data.get("meshes") or []),
        "scene_count": len(data.get("scenes") or []),
    }


def _license_context(path: Path, root: Path) -> dict[str, Any]:
    candidates: list[Path] = []
    cur = path.parent
    for _ in range(4):
        if cur == root.parent or not str(cur).startswith(str(root)):
            break
        for name in ("LICENSE", "LICENSE.txt", "LICENSE.md", "COPYING", "README.md", "README.txt", "readme.md", "readme.txt"):
            p = cur / name
            if p.exists():
                candidates.append(p)
        if cur == cur.parent:
            break
        cur = cur.parent
    unique = []
    seen = set()
    for p in candidates:
        if p not in seen:
            unique.append(p)
            seen.add(p)
    snippets = []
    for p in unique[:3]:
        text = _read_small_text(p, limit=120_000)
        found = []
        for needle in ("CC0", "CC-BY", "Creative Commons", "MIT", "Apache", "GPL", "BSD", "license", "attribution"):
            if needle.lower() in text.lower():
                found.append(needle)
        snippets.append({"path": str(p), "signals": sorted(set(found))})
    return {"nearby_files": snippets, "needs_review": True}


def _iter_asset_files(root: Path, max_files: int) -> list[Path]:
    out: list[Path] = []
    for path in root.rglob("*"):
        if len(out) >= max_files:
            break
        if set(path.parts) & SKIP_DIRS:
            continue
        if path.is_file() and path.suffix.lower() in ASSET_EXTENSIONS:
            out.append(path)
    return out


def scan_roots(roots: list[str | Path], *, max_files: int = 5000, include_known_github: bool = True) -> dict[str, Any]:
    scanned_roots: list[str] = []
    missing_roots: list[str] = []
    candidates: list[dict[str, Any]] = []
    all_assets = 0
    for raw in roots:
        root = Path(raw).expanduser().resolve()
        if not root.exists():
            missing_roots.append(str(root))
            continue
        scanned_roots.append(str(root))
        for path in _iter_asset_files(root, max_files=max_files):
            all_assets += 1
            rel = path.relative_to(root)
            tokens = _tokenize(" ".join([path.stem, str(rel), path.parent.name]))
            score = _score_tokens(tokens)
            region = _region_hint(tokens)
            gltf = _gltf_capabilities(path)
            if gltf.get("checked"):
                if gltf.get("animations", 0) > 0:
                    score += 3
                if gltf.get("skins", 0) > 0:
                    score += 3
            likely = score >= 4
            candidates.append({
                "path": str(path),
                "root": str(root),
                "relative_path": str(rel).replace("\\", "/"),
                "extension": path.suffix.lower(),
                "name": path.stem,
                "size_bytes": path.stat().st_size,
                "tokens": sorted(tokens),
                "fauna_score": score,
                "likely_fauna": likely,
                "region_hint": region,
                "gltf_capabilities": gltf,
                "license_context": _license_context(path, root),
                "status": "candidate" if likely else "asset_nonfauna_or_low_confidence",
            })
    candidates.sort(key=lambda item: (not item["likely_fauna"], -int(item["fauna_score"]), item["relative_path"]))
    return {
        "schema_version": "holoverse_fauna_resource_scan.v1",
        "tool_version": TOOL_VERSION,
        "created_at": _now(),
        "roots": scanned_roots,
        "missing_roots": missing_roots,
        "asset_file_count": all_assets,
        "candidate_count": sum(1 for item in candidates if item["likely_fauna"]),
        "candidates": candidates,
        "known_github_resources": KNOWN_GITHUB_RESOURCES if include_known_github else [],
        "notes": [
            "Local candidates are not approved until license and visual proof are reviewed.",
            "Known GitHub resources are references only; download/import should happen in a separate controlled pass.",
            "Promotion into HoloVerse should still go through the fauna preview and promotion gate.",
        ],
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# HoloVerse Fauna Resource Scan",
        "",
        f"- Tool: `{report.get('tool_version')}`",
        f"- Asset files scanned: `{report.get('asset_file_count')}`",
        f"- Likely fauna candidates: `{report.get('candidate_count')}`",
        "",
        "## Roots",
        "",
    ]
    for root in report.get("roots") or []:
        lines.append(f"- `{root}`")
    for root in report.get("missing_roots") or []:
        lines.append(f"- Missing: `{root}`")
    lines.extend(["", "## Local candidates", ""])
    local = [item for item in report.get("candidates") or [] if item.get("likely_fauna")]
    if not local:
        lines.append("No likely local fauna model assets were found in the scanned roots.")
    else:
        for item in local[:60]:
            caps = item.get("gltf_capabilities") or {}
            rig = ""
            if caps.get("checked"):
                rig = f" animations={caps.get('animations')} skins={caps.get('skins')}"
            lines.append(f"- `{item.get('relative_path')}` score={item.get('fauna_score')} region={item.get('region_hint') or 'unknown'}{rig}")
    lines.extend(["", "## Known GitHub references", ""])
    for item in report.get("known_github_resources") or []:
        lines.append(f"- **{item.get('name')}** - {item.get('why_relevant')}  ")
        lines.append(f"  URL: {item.get('source_url')}  ")
        lines.append(f"  License: {item.get('license_note')}")
    lines.extend(["", "## Notes", ""])
    for note in report.get("notes") or []:
        lines.append(f"- {note}")
    return "\n".join(lines) + "\n"


def write_report(report: dict[str, Any], output_dir: str | Path) -> tuple[Path, Path]:
    out = Path(output_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    json_path = out / "fauna_resource_scan.json"
    md_path = out / "fauna_resource_scan.md"
    json_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    return json_path, md_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scan backup/model folders for fauna-like 3D assets before HoloVerse preview import.")
    parser.add_argument("roots", nargs="+", help="One or more local backup/model roots to scan.")
    parser.add_argument("--output-dir", default="reports")
    parser.add_argument("--max-files", type=int, default=5000)
    parser.add_argument("--no-known-github", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = scan_roots(args.roots, max_files=args.max_files, include_known_github=not args.no_known_github)
    json_path, md_path = write_report(report, args.output_dir)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print("HoloVerse fauna resource scan: PASS")
        print(f"Report JSON: {json_path}")
        print(f"Report Markdown: {md_path}")
        print(f"Asset files scanned: {report['asset_file_count']}")
        print(f"Likely fauna candidates: {report['candidate_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
