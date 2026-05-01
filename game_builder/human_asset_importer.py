from __future__ import annotations

import json
import re
import shutil
import struct
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


RIGGED_BASE_EXTS = {".glb", ".gltf", ".bam", ".egg", ".fbx"}
STATIC_REFERENCE_EXTS = {".obj"}
ANIMATION_EXTS = {".glb", ".gltf", ".bam", ".egg", ".fbx", ".bvh"}
HUMAN_TOKENS = (
    "human",
    "humanoid",
    "female",
    "male",
    "woman",
    "man",
    "girl",
    "survivor",
    "character",
    "avatar",
    "idle",
)
NON_HUMAN_TOKENS = (
    "house",
    "building",
    "car",
    "truck",
    "tank",
    "tree",
    "pistol",
    "rifle",
    "knife",
    "sword",
    "robot",
    "dog",
    "wolf",
    "cat",
)
ANIMATION_ROLE_TOKENS = {
    "idle": ("idle", "standing"),
    "walk": ("walk", "walking"),
    "run": ("run", "running", "sprint"),
    "jump": ("jump", "jumping"),
    "attack": ("attack", "punch", "kick", "hook"),
    "hit": ("hit", "damage"),
    "fall": ("fall", "falling"),
    "death": ("death", "dying"),
    "get_up": ("get up", "getting up", "get_up"),
    "block": ("block", "blocking"),
}
EXCLUDED_PARTS = {
    ".git",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    "node_modules",
    "dist",
    "build",
    ".venv",
    "venv",
    "site-packages",
}
DEFAULT_EXPORT_FORMATS = ("glb", "obj", "fbx")


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _slugify(text: str, default: str = "asset") -> str:
    text = str(text or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text or default


def _path_text(path: Path) -> str:
    return str(path).replace("\\", "/").lower()


def _has_any(text: str, tokens: tuple[str, ...]) -> bool:
    return any(token in text for token in tokens)


def _relative(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve())).replace("\\", "/")
    except Exception:
        return str(path.resolve())


def _is_under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except Exception:
        return False


def _read_gltf_json(path: Path) -> dict[str, Any] | None:
    suffix = path.suffix.lower()
    try:
        if suffix == ".gltf":
            return json.loads(path.read_text(encoding="utf-8", errors="replace"))
        if suffix != ".glb":
            return None
        data = path.read_bytes()
        if len(data) < 20:
            return None
        magic, _version, _total_length = struct.unpack_from("<4sII", data, 0)
        if magic != b"glTF":
            return None
        json_length, chunk_type = struct.unpack_from("<I4s", data, 12)
        if chunk_type != b"JSON":
            return None
        raw_json = data[20 : 20 + json_length]
        return json.loads(raw_json.decode("utf-8", errors="replace"))
    except Exception:
        return None


def summarize_model_file(path: Path) -> dict[str, Any]:
    suffix = path.suffix.lower()
    summary: dict[str, Any] = {
        "format": suffix.lstrip("."),
        "file_size": path.stat().st_size if path.exists() else 0,
        "has_mesh": suffix in RIGGED_BASE_EXTS | STATIC_REFERENCE_EXTS,
        "has_skin": False,
        "has_animation": False,
        "mesh_count": None,
        "skin_count": None,
        "animation_count": None,
        "joint_count": None,
        "animation_names": [],
        "notes": [],
    }
    data = _read_gltf_json(path)
    if data is not None:
        skins = data.get("skins") or []
        animations = data.get("animations") or []
        meshes = data.get("meshes") or []
        joint_counts = [len(skin.get("joints") or []) for skin in skins if isinstance(skin, dict)]
        summary.update(
            {
                "has_mesh": bool(meshes),
                "has_skin": bool(skins),
                "has_animation": bool(animations),
                "mesh_count": len(meshes),
                "skin_count": len(skins),
                "animation_count": len(animations),
                "joint_count": max(joint_counts) if joint_counts else 0,
                "animation_names": [str(anim.get("name") or "") for anim in animations[:12] if isinstance(anim, dict)],
            }
        )
        if skins and not animations:
            summary["notes"].append("Rig/skin data was detected, but no embedded animations were detected.")
        if animations and not skins:
            summary["notes"].append("Animations were detected without a skin; Panda3D may load this as a static scene.")
    elif suffix == ".fbx":
        summary["notes"].append("FBX rig details are runtime-probed by Panda3D/Assimp when available; static GLB metadata is not embedded here.")
    elif suffix == ".obj":
        summary["notes"].append("OBJ is a static reference format and is not a rigged runtime mesh.")
    return summary


def _animation_role(path: Path) -> str | None:
    text = path.stem.lower().replace("_", " ").replace("-", " ")
    for role, tokens in ANIMATION_ROLE_TOKENS.items():
        if any(token in text for token in tokens):
            return role
    return None


def _score_candidate(path: Path, summary: dict[str, Any]) -> tuple[int, list[str], str]:
    suffix = path.suffix.lower()
    text = _path_text(path)
    score = 0
    reasons: list[str] = []
    asset_type = "static_reference"

    if suffix in {".glb", ".gltf"}:
        asset_type = "runtime_mesh"
        score += 20
        reasons.append("Panda3D-friendly glTF/GLB runtime format.")
        if summary.get("has_skin"):
            score += 80
            reasons.append("glTF skin data detected.")
        if summary.get("has_animation"):
            score += 25
            reasons.append("embedded animation data detected.")
    elif suffix in {".bam", ".egg"}:
        asset_type = "runtime_mesh"
        score += 35
        reasons.append("Panda3D native runtime format.")
    elif suffix == ".fbx":
        asset_type = "rig_or_animation_source"
        score += 30
        reasons.append("FBX can be a rig or animation source when the runtime supports it.")
    elif suffix == ".obj":
        score += 5
        reasons.append("Static human shape reference only.")

    if _has_any(text, HUMAN_TOKENS):
        score += 30
        reasons.append("human/character naming signal.")
    if any(part.lower() in {"female", "male", "character", "characters", "humans", "survivor"} for part in path.parts):
        score += 18
        reasons.append("human-oriented folder context.")
    if _has_any(text, NON_HUMAN_TOKENS) and not _has_any(text, ("human", "male", "female", "survivor", "character")):
        score -= 60
        reasons.append("non-human naming signal.")
    if suffix == ".fbx" and _animation_role(path):
        asset_type = "animation_clip"
        score += 15
        reasons.append(f"animation role signal: {_animation_role(path)}.")
    if summary.get("file_size", 0) > 96 * 1024 * 1024:
        score -= 18
        reasons.append("large source file; import requires explicit large-file allowance.")
    return score, reasons, asset_type


def _iter_asset_files(search_root: Path, max_files: int) -> list[Path]:
    files: list[Path] = []
    for path in sorted(search_root.rglob("*")):
        try:
            rel_parts = path.relative_to(search_root).parts
        except Exception:
            rel_parts = path.parts
        lower_parts = [part.lower() for part in rel_parts]
        if "gptool" in lower_parts and "examples" in lower_parts:
            continue
        if any(part in EXCLUDED_PARTS for part in rel_parts):
            continue
        if not path.is_file():
            continue
        if path.suffix.lower() in RIGGED_BASE_EXTS | STATIC_REFERENCE_EXTS | ANIMATION_EXTS:
            files.append(path)
            if len(files) >= max_files:
                break
    return files


def scan_human_asset_sources(
    search_root: str | Path,
    *,
    max_files: int = 12000,
    min_score: int = 25,
    prefer_tokens: tuple[str, ...] = (),
    require_tokens: tuple[str, ...] = (),
    rigged_only: bool = False,
) -> dict[str, Any]:
    root = Path(search_root).resolve()
    candidates: list[dict[str, Any]] = []
    if not root.exists():
        return {
            "schema_version": "human_asset_scan.v1",
            "ok": False,
            "search_root": str(root),
            "candidates": [],
            "summary": {"candidate_count": 0},
            "notes": ["Search root does not exist."],
        }

    for path in _iter_asset_files(root, max_files=max_files):
        summary = summarize_model_file(path)
        if rigged_only and not summary.get("has_skin"):
            continue
        score, reasons, asset_type = _score_candidate(path, summary)
        lowered_path = _path_text(path)
        required = [token for token in require_tokens if token]
        if required and not any(token.lower() in lowered_path for token in required):
            continue
        preferred_hits = [token for token in prefer_tokens if token and token.lower() in lowered_path]
        if preferred_hits:
            score += 45 + (len(preferred_hits) * 5)
            reasons.append("preferred token match: " + ", ".join(preferred_hits))
        if score < min_score:
            continue
        candidates.append(
            {
                "id": _slugify(path.stem),
                "path": str(path.resolve()),
                "relative_path": _relative(path, root),
                "name": path.name,
                "asset_type": asset_type,
                "score": score,
                "role": _animation_role(path),
                "summary": summary,
                "reasons": reasons,
            }
        )

    candidates.sort(key=lambda item: (-int(item["score"]), item["relative_path"].lower()))
    rigged = [item for item in candidates if item.get("summary", {}).get("has_skin")]
    animations = [item for item in candidates if item.get("asset_type") == "animation_clip" or item.get("summary", {}).get("has_animation")]
    return {
        "schema_version": "human_asset_scan.v1",
        "ok": True,
        "search_root": str(root),
        "generated_at": _now_iso(),
        "summary": {
            "candidate_count": len(candidates),
            "rigged_candidate_count": len(rigged),
            "animation_candidate_count": len(animations),
            "top_runtime_candidates": [item["relative_path"] for item in candidates[:8]],
        },
        "candidates": candidates,
        "notes": [
            "GLB/GLTF files are statically inspected for skins and animations.",
            "FBX compatibility is marked as a runtime concern because binary FBX skin data is not reliably introspected without a DCC/runtime importer.",
            "Preferred tokens only adjust ranking; they do not hide otherwise compatible assets.",
            "Required tokens filter candidates before ranking.",
        ],
    }


def _copy_asset(source: Path, target_dir: Path, used_names: set[str], *, overwrite: bool) -> tuple[Path, bool]:
    slug = _slugify(source.stem)
    candidate = target_dir / f"{slug}{source.suffix.lower()}"
    counter = 2
    while candidate.name.lower() in used_names or (candidate.exists() and not overwrite):
        candidate = target_dir / f"{slug}_{counter}{source.suffix.lower()}"
        counter += 1
    candidate.parent.mkdir(parents=True, exist_ok=True)
    if not candidate.exists() or overwrite:
        shutil.copy2(source, candidate)
        written = True
    else:
        written = False
    used_names.add(candidate.name.lower())
    return candidate, written


def _candidate_signature(item: dict[str, Any]) -> tuple[str, int, int, int]:
    path = Path(str(item.get("path", "")))
    summary = item.get("summary") or {}
    return (
        _slugify(path.stem),
        int(summary.get("file_size") or 0),
        int(summary.get("joint_count") or 0),
        int(summary.get("animation_count") or 0),
    )


def _select_base_assets(candidates: list[dict[str, Any]], limit: int, *, include_large: bool, rigged_only: bool = False) -> list[dict[str, Any]]:
    base_types = {"runtime_mesh", "rig_or_animation_source"}
    selected: list[dict[str, Any]] = []
    seen_signatures: set[tuple[str, int, int, int]] = set()
    seen_names: set[str] = set()
    for item in candidates:
        if item.get("asset_type") not in base_types:
            continue
        summary = item.get("summary") or {}
        if rigged_only and not summary.get("has_skin"):
            continue
        if not include_large and int(summary.get("file_size") or 0) > 96 * 1024 * 1024:
            continue
        if item.get("asset_type") == "rig_or_animation_source" and _animation_role(Path(str(item.get("path", "")))):
            continue
        signature = _candidate_signature(item)
        name_key = signature[0]
        if signature in seen_signatures:
            continue
        if name_key in seen_names and len(selected) < limit:
            continue
        selected.append(item)
        seen_signatures.add(signature)
        seen_names.add(name_key)
        if len(selected) >= limit:
            break
    return selected


def _select_animation_assets(candidates: list[dict[str, Any]], limit: int, *, include_large: bool) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    seen_roles: set[str] = set()
    for item in candidates:
        summary = item.get("summary") or {}
        if not include_large and int(summary.get("file_size") or 0) > 96 * 1024 * 1024:
            continue
        role = item.get("role") or _animation_role(Path(str(item.get("path", "")))) or item.get("id")
        if item.get("asset_type") != "animation_clip":
            continue
        if role in seen_roles and len(selected) >= 4:
            continue
        seen_roles.add(str(role))
        selected.append(item)
        if len(selected) >= limit:
            break
    return selected


def _find_fbx2gltf(search_root: Path) -> Path | None:
    roots = [
        search_root,
        search_root / "3D Editors" / "3D Modeling" / "panda_asset_workstation" / "tools",
        Path("D:/Apps/BACKUP/3D Editors/3D Modeling/panda_asset_workstation/tools"),
    ]
    names = [
        "FBX2glTF.exe",
        "FBX2glTF-windows-x86_64.exe",
        "FBX2glTF/FBX2glTF.exe",
        "fbx2gltf/FBX2glTF.exe",
        "FBX2glTF-windows-x86_64/FBX2glTF.exe",
        "FBX2glTF-windows-x86_64/FBX2glTF-windows-x86_64/FBX2glTF-windows-x86_64.exe",
    ]
    seen: set[str] = set()
    for root in roots:
        for name in names:
            candidate = (root / name).resolve()
            key = str(candidate).lower()
            if key in seen:
                continue
            seen.add(key)
            if candidate.exists() and candidate.is_file():
                return candidate
        if root.exists():
            for pattern in ("FBX2glTF.exe", "FBX2glTF*.exe"):
                for candidate in root.rglob(pattern):
                    if candidate.exists() and candidate.is_file():
                        return candidate.resolve()
    return None


def _export_with_trimesh(source: Path, out_path: Path, fmt: str) -> dict[str, Any]:
    try:
        import trimesh
    except Exception as exc:
        return {"format": fmt, "path": str(out_path), "ok": False, "reason": f"trimesh unavailable: {exc}"}
    try:
        scene = trimesh.load(str(source), force="scene")
        if scene is None:
            raise RuntimeError("trimesh returned no scene")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        exported = scene.export(file_type=fmt)
        if isinstance(exported, bytes):
            out_path.write_bytes(exported)
        elif isinstance(exported, str):
            out_path.write_text(exported, encoding="utf-8")
        elif exported is None and out_path.exists():
            pass
        else:
            raise RuntimeError(f"unsupported trimesh export result: {type(exported).__name__}")
        return {
            "format": fmt,
            "path": str(out_path),
            "ok": out_path.exists(),
            "reason": "static geometry export; rig/animation data may not be preserved",
        }
    except Exception as exc:
        return {"format": fmt, "path": str(out_path), "ok": False, "reason": str(exc)}


def _convert_fbx_to_glb(source: Path, out_path: Path, search_root: Path) -> dict[str, Any]:
    exe = _find_fbx2gltf(search_root)
    if not exe:
        return {"format": "glb", "path": str(out_path), "ok": False, "reason": "FBX2glTF executable not found"}
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [str(exe), "--binary", "--input", str(source), "--output", str(out_path)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=90, check=False)
    except Exception as exc:
        return {"format": "glb", "path": str(out_path), "ok": False, "reason": f"FBX2glTF launch failed: {exc}"}
    text = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
    return {
        "format": "glb",
        "path": str(out_path),
        "ok": proc.returncode == 0 and out_path.exists(),
        "backend": str(exe),
        "returncode": proc.returncode,
        "reason": "FBX2glTF conversion" if proc.returncode == 0 and out_path.exists() else text[-1200:],
    }


def _export_asset_formats(source: Path, asset_id: str, export_dir: Path, formats: tuple[str, ...], search_root: Path) -> list[dict[str, Any]]:
    exports: list[dict[str, Any]] = []
    normalized_formats = tuple(dict.fromkeys(fmt.strip().lower().lstrip(".") for fmt in formats if fmt.strip()))
    for fmt in normalized_formats:
        if fmt == "glb":
            out = export_dir / "glb" / f"{asset_id}.glb"
            if source.suffix.lower() == ".glb":
                out.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, out)
                exports.append({"format": "glb", "path": str(out), "ok": True, "reason": "rig-safe GLB copy"})
            elif source.suffix.lower() == ".fbx":
                exports.append(_convert_fbx_to_glb(source, out, search_root))
            else:
                exports.append(_export_with_trimesh(source, out, "glb"))
        elif fmt == "obj":
            out = export_dir / "obj" / f"{asset_id}.obj"
            if source.suffix.lower() == ".obj":
                out.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, out)
                exports.append({"format": "obj", "path": str(out), "ok": True, "reason": "static OBJ copy"})
            else:
                exports.append(_export_with_trimesh(source, out, "obj"))
        elif fmt == "fbx":
            out = export_dir / "fbx" / f"{asset_id}.fbx"
            if source.suffix.lower() == ".fbx":
                out.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, out)
                exports.append({"format": "fbx", "path": str(out), "ok": True, "reason": "source FBX copy-through"})
            else:
                exports.append({
                    "format": "fbx",
                    "path": str(out),
                    "ok": False,
                    "reason": "FBX writing is not available in this Python pipeline; use source FBX copy-through or export from a DCC tool.",
                })
        else:
            exports.append({"format": fmt, "path": "", "ok": False, "reason": "unsupported export format"})
    return exports


def _update_project_settings(project_root: Path, manifest: dict[str, Any]) -> dict[str, Any] | None:
    settings_path = project_root / "settings" / "game_settings.json"
    if not settings_path.exists():
        return None
    try:
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    settings.setdefault("assets", {})
    settings["assets"]["human_manifest"] = "assets/characters/humans/human_manifest.json"
    settings["assets"]["human_meshes"] = [
        {
            "id": item.get("id"),
            "path": item.get("relative_path"),
            "has_skin": item.get("summary", {}).get("has_skin"),
            "has_animation": item.get("summary", {}).get("has_animation"),
            "exports": item.get("exports", []),
        }
        for item in manifest.get("base_assets", [])
    ]
    base_assets = manifest.get("base_assets") or []
    if base_assets:
        chars = settings.setdefault("characters", [])
        if not chars:
            chars.append({"id": "imported_human", "name": "Imported Human", "role": "player_or_npc"})
        for idx, char in enumerate(chars):
            base = base_assets[idx % len(base_assets)]
            char["asset_manifest_id"] = base.get("id")
            char["asset_runtime"] = "panda3d_actor_preferred"
            char["silhouette"] = "imported_rigged_human_mesh"
    settings_path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    return settings


def import_human_assets(
    project_root: str | Path,
    search_root: str | Path,
    *,
    limit: int = 4,
    animation_limit: int = 10,
    include_large: bool = False,
    overwrite: bool = False,
    update_settings: bool = True,
    export_formats: tuple[str, ...] = DEFAULT_EXPORT_FORMATS,
    prefer_tokens: tuple[str, ...] = (),
    require_tokens: tuple[str, ...] = (),
    rigged_only: bool = False,
    clean: bool = False,
) -> dict[str, Any]:
    project = Path(project_root).resolve()
    search = Path(search_root).resolve()
    scan = scan_human_asset_sources(search, min_score=25, prefer_tokens=prefer_tokens, require_tokens=require_tokens)
    if not scan.get("ok"):
        return {
            "schema_version": "human_asset_import.v1",
            "ok": False,
            "project_root": str(project),
            "search_root": str(search),
            "scan": scan,
            "reason": "Human asset scan failed.",
        }

    external_candidates = [
        item for item in (scan.get("candidates") or [])
        if not _is_under(Path(str(item.get("path", ""))), project)
    ]
    base_candidates = _select_base_assets(external_candidates, max(1, limit), include_large=include_large, rigged_only=rigged_only)
    animation_candidates = _select_animation_assets(external_candidates, max(0, animation_limit), include_large=include_large)
    if not base_candidates:
        return {
            "schema_version": "human_asset_import.v1",
            "ok": False,
            "project_root": str(project),
            "search_root": str(search),
            "scan": {"summary": scan.get("summary"), "top_candidates": (scan.get("candidates") or [])[:12]},
            "reason": "No rigged/runtime human mesh candidates were selected.",
        }

    target_root = project / "assets" / "characters" / "humans"
    if clean and target_root.exists() and _is_under(target_root, project):
        shutil.rmtree(target_root)
    model_dir = target_root / "models"
    anim_dir = target_root / "animations"
    export_dir = target_root / "exports"
    used_names: set[str] = set()
    base_assets: list[dict[str, Any]] = []
    animation_assets: list[dict[str, Any]] = []
    files: list[dict[str, Any]] = []
    export_records: list[dict[str, Any]] = []

    for item in base_candidates:
        source = Path(item["path"])
        copied, written = _copy_asset(source, model_dir, used_names, overwrite=overwrite)
        rel = _relative(copied, project)
        base_record = {
            "id": _slugify(copied.stem),
            "label": source.stem.replace("_", " "),
            "relative_path": rel,
            "source_path": str(source),
            "runtime_role": "actor_preferred" if source.suffix.lower() in RIGGED_BASE_EXTS else "static_reference",
            "summary": item.get("summary"),
            "score": item.get("score"),
            "reasons": item.get("reasons", []),
            "exports": _export_asset_formats(copied, _slugify(copied.stem), export_dir, export_formats, search),
        }
        export_records.extend(base_record["exports"])
        base_assets.append(base_record)
        files.append({"source": str(source), "target": str(copied), "written": written})

    for item in animation_candidates:
        source = Path(item["path"])
        if any(source.resolve() == Path(base.get("source_path", "")).resolve() for base in base_assets):
            continue
        copied, written = _copy_asset(source, anim_dir, used_names, overwrite=overwrite)
        rel = _relative(copied, project)
        animation_assets.append(
            {
                "id": _slugify(copied.stem),
                "role": item.get("role") or _animation_role(source),
                "relative_path": rel,
                "source_path": str(source),
                "summary": item.get("summary"),
                "score": item.get("score"),
            }
        )
        files.append({"source": str(source), "target": str(copied), "written": written})

    manifest = {
        "schema_version": "human_asset_manifest.v1",
        "generated_at": _now_iso(),
        "source_search_root": str(search),
        "import_strategy": {
            "base_mesh": "Prefer GLB/GLTF files with detected skin data; fall back to Panda3D-readable runtime/source meshes.",
            "animations": "Prefer embedded GLB/GLTF animations; copy named FBX/BVH clips as optional Actor clip sources.",
            "runtime": "Generated templates attempt Actor first, then static loadModel fallback.",
        },
        "base_assets": base_assets,
        "animations": animation_assets,
        "notes": [
            "Panda3D Actor loading of GLB requires panda3d-gltf in the active runtime.",
            "External FBX clips are copied as optional sources and may only bind when their skeleton matches the selected base mesh.",
            "GLB exports are rig-safe only when copied from rigged GLB sources or produced by a rig-aware converter. OBJ exports are static geometry.",
            "FBX export is copy-through only unless the source asset is already FBX.",
        ],
    }
    manifest_path = target_root / "human_manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    settings = _update_project_settings(project, manifest) if update_settings else None

    return {
        "schema_version": "human_asset_import.v1",
        "ok": True,
        "project_root": str(project),
        "search_root": str(search),
        "manifest": str(manifest_path),
        "base_asset_count": len(base_assets),
        "animation_asset_count": len(animation_assets),
        "files": files,
        "exports": export_records,
        "export_summary": {
            "requested_formats": list(export_formats),
            "ok_count": len([item for item in export_records if item.get("ok")]),
            "failed_count": len([item for item in export_records if not item.get("ok")]),
        },
        "settings_updated": settings is not None,
        "scan_summary": scan.get("summary"),
        "selected_base_assets": [item["relative_path"] for item in base_assets],
        "selected_animation_assets": [item["relative_path"] for item in animation_assets],
    }
