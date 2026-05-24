from __future__ import annotations

import argparse
import json
import math
import re
import statistics
import struct
from collections import Counter, defaultdict
from pathlib import Path, PureWindowsPath
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageFilter
import trimesh

PANEL_BG = (11, 14, 18, 255)
CARD_BG = (20, 24, 31, 255)
CARD_OUTLINE = (68, 82, 102, 255)
TEXT = (236, 241, 248, 255)
MUTED = (165, 176, 190, 255)
ACCENT = (115, 199, 255, 255)
GOOD = (110, 228, 168, 255)
WARN = (255, 191, 124, 255)
BAD = (255, 130, 130, 255)

MODEL_EXTS = {'.obj', '.glb', '.fbx', '.gltf', '.dae', '.stl', '.ply'}
IMAGE_EXTS = {'.png', '.jpg', '.jpeg', '.webp', '.tif', '.tiff', '.dds', '.bmp'}

SLOT_PATTERNS: list[tuple[str, list[str]]] = [
    ('normal', [r'(^|[_\-\s])(normal|normals|nrm|nor)([_\-\s\.]|$)', r'_n\.', r'normal\.']),
    ('roughness', [r'(^|[_\-\s])(roughness|rough|rgh|glossiness|gloss)([_\-\s\.]|$)', r'_r\.']),
    ('metallic', [r'(^|[_\-\s])(metallic|metalness|metal)([_\-\s\.]|$)', r'_m\.']),
    ('specular', [r'(^|[_\-\s])(specular|spec)([_\-\s\.]|$)', r'_s\.']),
    ('ao', [r'(^|[_\-\s])(ao|ambientocclusion|occlusion)([_\-\s\.]|$)']),
    ('opacity', [r'(^|[_\-\s])(opacity|alpha|transparency|mask)([_\-\s\.]|$)']),
    ('emissive', [r'(^|[_\-\s])(emissive|emit|emission)([_\-\s\.]|$)']),
    ('bump', [r'(^|[_\-\s])(bump|height|disp|displacement)([_\-\s\.]|$)']),
    ('albedo', [r'(^|[_\-\s])(albedo|basecolor|base_color|diffuse|color|col)([_\-\s\.]|$)', r'_d\.', r'_c\.']),
]

MTL_KEY_TO_SLOT = {
    'map_kd': 'albedo',
    'map_ks': 'specular',
    'map_ke': 'emissive',
    'map_bump': 'bump',
    'bump': 'bump',
    'disp': 'bump',
    'refl': 'unknown',
}


def _fit_lines(text: str, width: int) -> list[str]:
    words = text.split()
    if not words:
        return ['']
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        if len(current) + 1 + len(word) <= width:
            current += ' ' + word
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _safe_round(value: float | int | None, digits: int = 4) -> float | None:
    if value is None:
        return None
    return round(float(value), digits)


def _classify_slot(name: str, map_key: str | None = None) -> str:
    lowered = name.lower()
    for slot, patterns in SLOT_PATTERNS:
        for pattern in patterns:
            if re.search(pattern, lowered):
                return slot
    if map_key:
        return MTL_KEY_TO_SLOT.get(map_key.lower(), 'unknown')
    return 'unknown'


def _extract_map_target(raw_value: str) -> str:
    tokens = raw_value.split()
    if not tokens:
        return raw_value.strip()
    return tokens[-1].strip().strip('"').replace('\\\\', '\\')


def _resolve_texture_path(base_dir: Path, target: str) -> Path | None:
    candidates: list[Path] = []
    p = Path(target)
    if p.exists() and p.is_file():
        candidates.append(p.resolve())

    basename = Path(PureWindowsPath(target).name).name or Path(target).name
    if basename:
        direct = base_dir / basename
        if direct.exists() and direct.is_file():
            candidates.append(direct.resolve())
        for hit in base_dir.rglob(basename):
            if hit.is_file():
                candidates.append(hit.resolve())
                break

    rel = target.lstrip('/\\')
    if rel:
        for root in [base_dir, base_dir.parent, base_dir.parent.parent]:
            probe = (root / rel).resolve()
            if probe.exists() and probe.is_file():
                candidates.append(probe)
                break

    seen: set[str] = set()
    for candidate in candidates:
        marker = str(candidate)
        if marker not in seen:
            seen.add(marker)
            return candidate
    return None


def _parse_mtl(mtl_path: Path) -> list[dict[str, Any]]:
    materials: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    try:
        lines = mtl_path.read_text(encoding='utf-8', errors='ignore').splitlines()
    except Exception:
        return materials
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        if line.startswith('newmtl '):
            current = {'name': line[7:].strip(), 'maps': {}}
            materials.append(current)
            continue
        if current is None:
            continue
        parts = line.split(None, 1)
        if len(parts) < 2:
            continue
        key, value = parts
        if key.startswith('map_') or key in {'bump', 'disp', 'refl'}:
            current['maps'].setdefault(key, []).append(value.strip())
    return materials


def _obj_static_counts(obj_path: Path) -> dict[str, Any]:
    text = obj_path.read_text(encoding='utf-8', errors='ignore')
    def count(prefix: str) -> int:
        return len(re.findall(rf'(?m)^{re.escape(prefix)}\s', text))
    return {
        'vertices': count('v'),
        'normals': count('vn'),
        'texcoords': count('vt'),
        'faces': count('f'),
        'material_libraries': re.findall(r'(?m)^mtllib\s+(.+)$', text),
        'material_uses': sorted(set(re.findall(r'(?m)^usemtl\s+(.+)$', text))),
    }


def _parse_glb(glb_path: Path) -> dict[str, Any]:
    payload = glb_path.read_bytes()
    if payload[:4] != b'glTF':
        return {'parse_error': 'invalid_glb_header'}
    json_chunk: dict[str, Any] = {}
    offset = 12
    while offset < len(payload):
        chunk_len, chunk_type = struct.unpack_from('<I4s', payload, offset)
        offset += 8
        chunk = payload[offset:offset + chunk_len]
        offset += chunk_len
        if chunk_type == b'JSON':
            json_chunk = json.loads(chunk.decode('utf-8'))
            break
    skins = json_chunk.get('skins', [])
    return {
        'nodes': len(json_chunk.get('nodes', [])),
        'meshes': len(json_chunk.get('meshes', [])),
        'materials': len(json_chunk.get('materials', [])),
        'skins': len(skins),
        'joints': sum(len(skin.get('joints', [])) for skin in skins),
        'animations': len(json_chunk.get('animations', [])),
        'images': len(json_chunk.get('images', [])),
    }


def _scan_fbx_tokens(fbx_path: Path) -> dict[str, Any]:
    payload = fbx_path.read_bytes()
    binary = payload.startswith(b'Kaydara FBX Binary')
    strings: list[str] = []
    current = bytearray()
    for value in payload[: min(len(payload), 4_000_000)]:
        if 32 <= value < 127:
            current.append(value)
        else:
            if len(current) >= 4:
                strings.append(current.decode('latin1'))
            current = bytearray()
    if len(current) >= 4:
        strings.append(current.decode('latin1'))
    searchable = '\n'.join(strings).lower()
    token_counts = {
        token: searchable.count(token)
        for token in ['limbnode', 'deformer', 'skin', 'cluster', 'animationstack', 'animationlayer', 'bindpose', 'skeleton', 'mixamorig', 'bone', 'take']
    }
    likely_rigged = bool(token_counts['limbnode'] or token_counts['deformer'] or token_counts['skin'] or token_counts['cluster'])
    likely_animated = bool(token_counts['animationstack'] or token_counts['animationlayer'] or token_counts['take'])
    return {
        'binary': binary,
        'ascii_token_counts': token_counts,
        'likely_rigged': likely_rigged,
        'likely_animated': likely_animated,
    }


def _load_scene_bounds(model_path: Path) -> dict[str, Any]:
    if model_path.suffix.lower() not in {'.obj', '.glb', '.gltf', '.stl', '.ply'}:
        return {'supported': False, 'reason': 'bounds loader only enabled for trimesh-supported static formats in this bridge pass'}
    try:
        loaded = trimesh.load(model_path, force='scene')
    except Exception as exc:
        return {'supported': False, 'reason': str(exc)}
    if isinstance(loaded, trimesh.Scene):
        extents = getattr(loaded, 'extents', None)
        geom_count = len(loaded.geometry)
        verts = sum(int(getattr(g, 'vertices', np.zeros((0, 3))).shape[0]) for g in loaded.geometry.values())
        faces = sum(int(getattr(g, 'faces', np.zeros((0, 3))).shape[0]) for g in loaded.geometry.values())
    elif isinstance(loaded, trimesh.Trimesh):
        extents = loaded.extents
        geom_count = 1
        verts = int(loaded.vertices.shape[0])
        faces = int(loaded.faces.shape[0])
    else:
        return {'supported': False, 'reason': f'unsupported trimesh payload {type(loaded).__name__}'}
    return {
        'supported': True,
        'geometry_count': geom_count,
        'vertices': verts,
        'faces': faces,
        'extents': [_safe_round(v) for v in (extents.tolist() if extents is not None else [0.0, 0.0, 0.0])],
        'largest_dimension': _safe_round(max(extents) if extents is not None and len(extents) else 0.0),
    }


def _image_metrics(image_path: Path) -> dict[str, Any]:
    with Image.open(image_path) as img:
        img.load()
        sample = img.convert('RGBA')
        max_dim = max(sample.size)
        if max_dim > 256:
            scale = 256 / max_dim
            sample = sample.resize((max(1, int(sample.width * scale)), max(1, int(sample.height * scale))), Image.Resampling.BILINEAR)
        arr = np.asarray(sample).astype(np.float32) / 255.0
        rgb = arr[..., :3]
        alpha = arr[..., 3]
        gray = (0.299 * rgb[..., 0]) + (0.587 * rgb[..., 1]) + (0.114 * rgb[..., 2])
        sat = rgb.max(axis=2) - rgb.min(axis=2)
        edge = np.asarray(Image.fromarray((gray * 255).astype('uint8')).filter(ImageFilter.FIND_EDGES)).astype(np.float32) / 255.0
        grayscale_like = float(np.mean(np.max(np.abs(rgb - gray[..., None]), axis=2) < 0.03))
        return {
            'image': str(image_path),
            'size': [int(img.width), int(img.height)],
            'mode': img.mode,
            'alpha_present': bool((alpha < 0.999).any()),
            'mean_saturation': _safe_round(float(np.mean(sat))),
            'contrast_std': _safe_round(float(np.std(gray))),
            'edge_density': _safe_round(float(np.mean(edge > 0.12))),
            'grayscale_likelihood': _safe_round(grayscale_like),
        }


def _collect_texture_refs(model_path: Path, static_analysis: dict[str, Any] | None) -> tuple[list[dict[str, Any]], dict[str, int], list[str]]:
    references: list[dict[str, Any]] = []
    unresolved: list[str] = []
    slot_counter: Counter[str] = Counter()
    if model_path.suffix.lower() != '.obj' or not static_analysis:
        return references, dict(slot_counter), unresolved
    for mtl_name in static_analysis.get('material_libraries', []):
        mtl_path = model_path.parent / mtl_name
        if not mtl_path.exists():
            unresolved.append(mtl_name)
            continue
        for material in _parse_mtl(mtl_path):
            for map_key, raw_values in material.get('maps', {}).items():
                for raw_value in raw_values:
                    target = _extract_map_target(raw_value)
                    resolved = _resolve_texture_path(model_path.parent, target)
                    slot = _classify_slot(Path(target).name, map_key)
                    slot_counter[slot] += 1
                    if resolved is None:
                        unresolved.append(target)
                        references.append({
                            'material': material.get('name'),
                            'map_key': map_key,
                            'slot': slot,
                            'source': target,
                            'resolved': None,
                        })
                    else:
                        references.append({
                            'material': material.get('name'),
                            'map_key': map_key,
                            'slot': slot,
                            'source': target,
                            'resolved': str(resolved),
                        })
    return references, dict(slot_counter), unresolved


def _rig_summary(model_path: Path, glb_meta: dict[str, Any] | None, fbx_meta: dict[str, Any] | None) -> dict[str, Any]:
    ext = model_path.suffix.lower()
    if ext == '.obj':
        return {
            'status': 'static_reference',
            'has_skin': False,
            'joint_count': 0,
            'animation_count': 0,
            'notes': ['OBJ references are treated as shape and material references only in this bridge pass.'],
        }
    if ext in {'.glb', '.gltf'}:
        skins = int((glb_meta or {}).get('skins', 0))
        joints = int((glb_meta or {}).get('joints', 0))
        animations = int((glb_meta or {}).get('animations', 0))
        return {
            'status': 'rigged' if skins or joints else 'static_reference',
            'has_skin': bool(skins or joints),
            'joint_count': joints,
            'animation_count': animations,
            'notes': ['GLB metadata is parsed directly from the embedded glTF JSON chunk.'],
        }
    if ext == '.fbx':
        likely_rigged = bool((fbx_meta or {}).get('likely_rigged'))
        likely_animated = bool((fbx_meta or {}).get('likely_animated'))
        token_counts = (fbx_meta or {}).get('ascii_token_counts', {})
        return {
            'status': 'likely_rigged' if likely_rigged else 'unknown_fbx',
            'has_skin': likely_rigged,
            'joint_count': None,
            'animation_count': None,
            'notes': [
                'FBX rig and animation status is estimated from binary-string token signals in this bridge pass.',
                f"FBX token signals: {token_counts}",
                'Prefer GLB for authoritative rig-safe metadata once the asset is converted or inspected in a dedicated DCC tool.',
            ],
        }
    return {
        'status': 'unknown',
        'has_skin': None,
        'joint_count': None,
        'animation_count': None,
        'notes': ['Unsupported format for rig extraction in this bridge pass.'],
    }


def _category_from_path(rel_path: Path) -> str:
    parts = rel_path.parts
    return parts[0] if parts else 'uncategorized'


def _summarize_texture_standardization(texture_metrics: list[dict[str, Any]], model_records: list[dict[str, Any]]) -> dict[str, Any]:
    slot_counter = Counter(metric['slot'] for metric in texture_metrics)
    widths = [metric['size'][0] for metric in texture_metrics]
    heights = [metric['size'][1] for metric in texture_metrics]
    saturations = [metric['mean_saturation'] for metric in texture_metrics]
    contrasts = [metric['contrast_std'] for metric in texture_metrics]
    edges = [metric['edge_density'] for metric in texture_metrics]
    grayscale = [metric['grayscale_likelihood'] for metric in texture_metrics]
    resolved_slots = {slot for slot in slot_counter if slot != 'unknown'}
    missing_pbr_count = 0
    for record in model_records:
        slots = set(record.get('texture_slot_counts', {}).keys())
        if slots and not {'albedo', 'normal'}.issubset(slots):
            missing_pbr_count += 1
    naming_quality = 'legacy_mixed'
    if slot_counter and slot_counter['unknown'] == 0:
        naming_quality = 'clean'
    elif slot_counter['unknown'] <= max(3, len(texture_metrics) * 0.1):
        naming_quality = 'mostly_clean'

    findings: list[str] = []
    if slot_counter['unknown'] >= max(4, int(len(texture_metrics) * 0.15)):
        findings.append('Texture naming is inconsistent enough that slot detection frequently falls back to unknown.')
    if slot_counter['bump'] > slot_counter['roughness'] + slot_counter['metallic']:
        findings.append('The pack leans toward older diffuse+bump/spec workflows more than modern ORM/PBR sets.')
    if grayscale and statistics.mean(grayscale) > 0.55:
        findings.append('A large share of maps are grayscale-like, which lines up with AO, bump, and spec-heavy legacy materials.')
    if saturations and statistics.mean(saturations) < 0.30:
        findings.append('Average saturation is moderate to low, suggesting many textures are baked/photo-derived rather than flat illustrated materials.')
    if edges and statistics.mean(edges) > 0.18:
        findings.append('Edge density is fairly busy, so a cleanup pass should keep macro form while softening noisy micro-detail.')

    recommendations = [
        'Store source-model metadata only: bounds, format, geometry counts, texture slots, and rig signals. Do not duplicate source meshes inside the bridge.',
        'Standardize texture slot names to basecolor/albedo, normal, orm or separate roughness+metallic+ao, emissive, and opacity when present.',
        'Treat OBJ references as static dimension and texture standards only. Route rig-safe character or animated references toward GLB whenever possible.',
        'Normalize texture exports toward power-of-two sizes and prefer PNG for authored maps that need alpha, JPG only for opaque photo/baked color when compression is acceptable.',
        'Where references only provide diffuse plus bump/spec, derive bridge standards from silhouette, scale, and material read first, then rebuild into cleaner PBR slot conventions.',
    ]
    return {
        'texture_count': len(texture_metrics),
        'slot_counts': dict(slot_counter),
        'mean_resolution': [round(float(np.mean(widths)), 1) if widths else 0.0, round(float(np.mean(heights)), 1) if heights else 0.0],
        'mean_saturation': _safe_round(statistics.mean(saturations) if saturations else 0.0),
        'mean_contrast_std': _safe_round(statistics.mean(contrasts) if contrasts else 0.0),
        'mean_edge_density': _safe_round(statistics.mean(edges) if edges else 0.0),
        'mean_grayscale_likelihood': _safe_round(statistics.mean(grayscale) if grayscale else 0.0),
        'naming_quality': naming_quality,
        'models_missing_basic_albedo_normal_pair': missing_pbr_count,
        'findings': findings,
        'recommendations': recommendations,
    }


def build_reference_model_library(root: Path) -> dict[str, Any]:
    root = root.resolve()
    models = sorted(p for p in root.rglob('*') if p.is_file() and p.suffix.lower() in MODEL_EXTS)
    texture_metric_cache: dict[str, dict[str, Any]] = {}
    records: list[dict[str, Any]] = []
    format_counter: Counter[str] = Counter()
    category_counter: Counter[str] = Counter()
    rig_counter: Counter[str] = Counter()
    unresolved_counter = 0

    for model_path in models:
        rel = model_path.relative_to(root)
        category = _category_from_path(rel)
        format_key = model_path.suffix.lower().lstrip('.')
        format_counter[format_key] += 1
        category_counter[category] += 1

        obj_meta = _obj_static_counts(model_path) if model_path.suffix.lower() == '.obj' else None
        glb_meta = _parse_glb(model_path) if model_path.suffix.lower() in {'.glb', '.gltf'} else None
        fbx_meta = _scan_fbx_tokens(model_path) if model_path.suffix.lower() == '.fbx' else None
        bounds = _load_scene_bounds(model_path)
        texture_refs, texture_slot_counts, unresolved = _collect_texture_refs(model_path, obj_meta)
        unresolved_counter += len(unresolved)

        texture_profiles: list[dict[str, Any]] = []
        for ref in texture_refs:
            resolved = ref.get('resolved')
            if not resolved:
                continue
            marker = str(Path(resolved).resolve())
            if marker not in texture_metric_cache:
                try:
                    metric = _image_metrics(Path(resolved))
                    metric['slot'] = ref.get('slot', 'unknown')
                    texture_metric_cache[marker] = metric
                except Exception as exc:
                    texture_metric_cache[marker] = {
                        'image': str(resolved),
                        'slot': ref.get('slot', 'unknown'),
                        'error': str(exc),
                    }
            texture_profiles.append(texture_metric_cache[marker])

        rig = _rig_summary(model_path, glb_meta, fbx_meta)
        rig_counter[rig['status']] += 1
        records.append({
            'path': str(rel),
            'category': category,
            'format': format_key,
            'store_binary_source': False,
            'bounds': bounds,
            'static_analysis': obj_meta,
            'glb_analysis': glb_meta,
            'fbx_analysis': fbx_meta,
            'rig': rig,
            'texture_slot_counts': texture_slot_counts,
            'texture_reference_count': len(texture_refs),
            'unresolved_texture_reference_count': len(unresolved),
            'texture_references': texture_refs,
            'texture_profiles': texture_profiles,
        })

    texture_metrics = [metric for metric in texture_metric_cache.values() if 'error' not in metric]
    dimension_buckets: dict[str, dict[str, Any]] = {}
    for category in sorted(category_counter):
        extents = [record['bounds'].get('extents') for record in records if record['category'] == category and record['bounds'].get('supported')]
        extents = [e for e in extents if isinstance(e, list) and len(e) == 3]
        if not extents:
            continue
        xs, ys, zs = zip(*extents)
        dimension_buckets[category] = {
            'count': len(extents),
            'mean_extents': [_safe_round(statistics.mean(xs)), _safe_round(statistics.mean(ys)), _safe_round(statistics.mean(zs))],
            'max_largest_dimension': _safe_round(max(max(e) for e in extents)),
        }

    texture_standardization = _summarize_texture_standardization(texture_metrics, records)
    summary = {
        'model_count': len(records),
        'format_counts': dict(format_counter),
        'category_counts': dict(category_counter),
        'rig_status_counts': dict(rig_counter),
        'resolved_texture_count': len(texture_metrics),
        'unresolved_texture_reference_count': unresolved_counter,
        'bounds_supported_count': sum(1 for record in records if record['bounds'].get('supported')),
    }

    standardization = {
        'storage_policy': {
            'store_binary_models_in_bridge': False,
            'preserve_metadata_only': ['dimensions', 'geometry_counts', 'format', 'texture_slots', 'material_layout', 'rig_signals', 'category'],
            'notes': [
                'This library stores reference metadata only and is intended to keep source models out of the bridge package.',
                'Use the original donor bundle as the source of truth for geometry; use this library as the standards and routing layer.',
            ],
        },
        'preferred_static_reference_format': 'obj_or_glb',
        'preferred_rig_safe_format': 'glb',
        'texture_naming_schema': {
            'recommended_slots': ['basecolor', 'normal', 'orm', 'emissive', 'opacity'],
            'alternate_split_slots': ['basecolor', 'normal', 'roughness', 'metallic', 'ao', 'emissive', 'opacity'],
            'example': '<asset>__basecolor.png, <asset>__normal.png, <asset>__orm.png',
        },
        'texture_guidance': texture_standardization,
        'dimension_buckets_by_category': dimension_buckets,
    }

    return {
        'tool': 'reference_model_library',
        'root': str(root),
        'summary': summary,
        'standardization': standardization,
        'models': records,
    }


def save_json(payload: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2), encoding='utf-8')


def build_debug_panel(report: dict[str, Any], output_path: Path) -> None:
    width, height = 1600, 980
    image = Image.new('RGBA', (width, height), PANEL_BG)
    draw = ImageDraw.Draw(image)
    draw.text((28, 20), 'Reference Model Library', fill=TEXT)
    draw.text((28, 52), 'Metadata-only ingest for 3D donor references: dimensions, rig signals, and texture standards without storing source meshes.', fill=MUTED)

    summary = report['summary']
    standardization = report['standardization']
    texture_guidance = standardization['texture_guidance']

    cards = [
        ((24, 96, 510, 314), 'Summary', [
            f"models: {summary['model_count']}",
            f"formats: {summary['format_counts']}",
            f"categories: {summary['category_counts']}",
            f"rig states: {summary['rig_status_counts']}",
            f"resolved textures: {summary['resolved_texture_count']}",
            f"unresolved texture refs: {summary['unresolved_texture_reference_count']}",
        ], ACCENT),
        ((536, 96, 1044, 314), 'Storage Policy', [
            'store binary models: False',
            'keep metadata: dimensions, geometry counts,',
            'texture slots, material layout, rig signals',
            f"preferred rig-safe format: {standardization['preferred_rig_safe_format']}",
            'use donor bundle as geometry source of truth',
        ], GOOD),
        ((1070, 96, 1576, 314), 'Texture Standardization', [
            f"naming quality: {texture_guidance['naming_quality']}",
            f"slot counts: {texture_guidance['slot_counts']}",
            f"mean res: {texture_guidance['mean_resolution'][0]} x {texture_guidance['mean_resolution'][1]}",
            f"mean sat: {texture_guidance['mean_saturation']}",
            f"mean edge density: {texture_guidance['mean_edge_density']}",
            f"missing albedo+normal pair: {texture_guidance['models_missing_basic_albedo_normal_pair']}",
        ], WARN),
    ]

    for box, title, lines, color in cards:
        draw.rounded_rectangle(box, radius=18, fill=CARD_BG, outline=CARD_OUTLINE, width=2)
        draw.text((box[0] + 18, box[1] + 14), title, fill=color)
        y = box[1] + 50
        for line in lines:
            for wrapped in _fit_lines(line, 44):
                draw.text((box[0] + 18, y), wrapped, fill=TEXT if ':' in wrapped else MUTED)
                y += 28

    draw.rounded_rectangle((24, 338, 790, 950), radius=18, fill=CARD_BG, outline=CARD_OUTLINE, width=2)
    draw.rounded_rectangle((810, 338, 1576, 950), radius=18, fill=CARD_BG, outline=CARD_OUTLINE, width=2)
    draw.text((42, 356), 'Key Findings', fill=ACCENT)
    draw.text((828, 356), 'Dimension Buckets by Category', fill=ACCENT)

    y = 394
    findings = texture_guidance.get('findings', []) + texture_guidance.get('recommendations', [])
    for item in findings[:14]:
        for wrapped in _fit_lines('- ' + item, 58):
            draw.text((42, y), wrapped, fill=TEXT if wrapped.startswith('- ') else MUTED)
            y += 28
        y += 6

    y = 394
    for category, data in list(standardization.get('dimension_buckets_by_category', {}).items())[:14]:
        draw.rounded_rectangle((828, y, 1540, y + 74), radius=12, fill=(25, 30, 38, 255), outline=CARD_OUTLINE, width=1)
        draw.text((846, y + 12), category, fill=TEXT)
        draw.text((846, y + 40), f"count {data['count']}  mean extents {data['mean_extents']}  max dim {data['max_largest_dimension']}", fill=MUTED)
        y += 88

    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path)


def main() -> int:
    parser = argparse.ArgumentParser(description='Build a metadata-only 3D reference-model library without storing source meshes.')
    parser.add_argument('--root', required=True, help='Directory containing unpacked 3D reference models and textures.')
    parser.add_argument('--output', required=True, help='JSON output path.')
    parser.add_argument('--debug-image', help='Optional PNG summary panel path.')
    parser.add_argument('--json', action='store_true', help='Also print the JSON payload to stdout.')
    args = parser.parse_args()

    report = build_reference_model_library(Path(args.root))
    save_json(report, Path(args.output))
    if args.debug_image:
        build_debug_panel(report, Path(args.debug_image))
    if args.json:
        print(json.dumps(report, indent=2))
    return 0 if report['summary']['model_count'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
