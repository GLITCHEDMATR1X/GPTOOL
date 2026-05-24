from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

TOOL_TARGETS = {
    'PYCodeSmith': {
        'lane': 'code_preview_analysis',
        'functions': ['PythonAnalyzer', 'build_module_index', 'resolve_local_module_path', 'build_preview_spec', 'render_verified_gallery', 'render_ui_proof'],
    },
    'MatrixTools': {
        'lane': 'runtime_utils',
        'functions': ['backup_existing_file', 'safe_write_text', 'write_crash_log', 'install_crash_hook', 'discover_projects', 'guess_engine', 'scan_metadata_sources', 'compute_diff_stats', 'create_manifest', 'smoke_capture'],
    },
    '2D Prototype Editor': {
        'lane': 'texture_forge',
        'functions': ['fit_image_to_canvas', 'checkerboard', 'quantize_image', 'extract_palette', 'nearest_palette_color', 'palette_reduce_exact', 'outline_from_alpha', 'remove_corner_background', 'make_tileable_rgba'],
    },
    'tablet_sprite_studio': {
        'lane': 'texture_forge',
        'functions': ['PenProfile', 'AppSettings', 'default_procedural_slots', 'nearest_palette_color', 'adjust_color', 'run_smoke_test'],
    },
    'Sprite Animator': {
        'lane': 'sprite_rig_lab',
        'functions': ['PartPose', 'Keyframe', 'PivotHandle', 'PartItem', 'CanvasView', 'MainWindow'],
    },
    'Silhouette': {
        'lane': 'sprite_rig_lab',
        'functions': ['SegmentData', 'SegmentPart', 'ProjectState', 'edge_propagation_fill_rgba', 'convex_polygon_mask', 'make_pivot_bridge_overlay'],
    },
    'PixelMask': {
        'lane': 'texture_forge',
        'functions': ['Stroke', 'PaintLayer', 'ColorWheelWidget', 'PaintCanvas', 'MainWindow'],
    },
}

PANEL_BG = (11, 14, 18, 255)
CARD_BG = (20, 24, 31, 255)
CARD_OUTLINE = (68, 82, 102, 255)
TEXT = (236, 241, 248, 255)
MUTED = (165, 176, 190, 255)
ACCENT = (115, 199, 255, 255)
GOOD = (110, 228, 168, 255)
WARN = (255, 199, 109, 255)


def _extract_defs(path: Path) -> set[str]:
    try:
        tree = ast.parse(path.read_text(encoding='utf-8', errors='replace'))
    except Exception:
        return set()
    names: set[str] = set()
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
    return names


def salvage_inventory(source_roots: list[Path]) -> dict[str, Any]:
    donors: list[dict[str, Any]] = []
    for root in source_roots:
        label = root.name
        target = TOOL_TARGETS.get(label)
        matched: list[str] = []
        all_defs: set[str] = set()
        for py in root.rglob('*.py'):
            all_defs |= _extract_defs(py)
        if target:
            for name in target['functions']:
                if name in all_defs:
                    matched.append(name)
        donors.append({
            'label': label,
            'source_root': str(root),
            'lane': target['lane'] if target else 'unmapped',
            'matched_functions': matched,
            'matched_count': len(matched),
            'scanned_symbol_count': len(all_defs),
            'adoption_status': 'integrated' if target else 'review_only',
        })
    report = {
        'tool': 'tool_function_salvager',
        'donor_count': len(donors),
        'donors': donors,
        'notes': [
            'This inventory maps donor-tool functions to normalized bridge salvage lanes.',
            'Integration is surgical: utilities are extracted into bridge-safe modules instead of whole-app merges.',
            '2D texture and sprite-rig donors are now tracked beside the original code and runtime salvage lanes.',
        ],
    }
    return report


def render_panel(report: dict[str, Any], output_path: Path) -> None:
    donors = report['donors']
    cols = 3
    card_w = 444
    card_h = 250
    gap = 20
    width = 24 + cols * card_w + (cols - 1) * gap + 24
    rows = max(1, (len(donors) + cols - 1) // cols)
    height = 110 + rows * (card_h + gap) + 24
    img = Image.new('RGBA', (width, height), PANEL_BG)
    draw = ImageDraw.Draw(img)
    draw.text((26, 22), 'Tool Function Salvage', fill=TEXT)
    draw.text((26, 50), 'Mapped donor-tool functions into bridge-safe salvage lanes, including 2D texture and sprite-rig upgrades.', fill=MUTED)
    for idx, donor in enumerate(donors):
        col = idx % cols
        row = idx // cols
        x0 = 24 + col * (card_w + gap)
        y0 = 94 + row * (card_h + gap)
        x1 = x0 + card_w
        y1 = y0 + card_h
        draw.rounded_rectangle((x0, y0, x1, y1), radius=18, fill=CARD_BG, outline=CARD_OUTLINE, width=2)
        draw.text((x0 + 18, y0 + 16), donor['label'][:28], fill=ACCENT)
        draw.text((x0 + 18, y0 + 44), f"lane: {donor['lane']}", fill=GOOD if donor['adoption_status'] == 'integrated' else WARN)
        draw.text((x0 + 18, y0 + 72), f"matched: {donor['matched_count']}", fill=TEXT)
        draw.text((x0 + 18, y0 + 100), f"scanned symbols: {donor['scanned_symbol_count']}", fill=MUTED)
        y = y0 + 132
        for item in donor['matched_functions'][:4]:
            draw.text((x0 + 18, y), item[:34], fill=TEXT)
            y += 24
        if len(donor['matched_functions']) > 4:
            draw.text((x0 + 18, y), f"+{len(donor['matched_functions']) - 4} more", fill=MUTED)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(output_path)


def main() -> int:
    ap = argparse.ArgumentParser(description='Inventory donor-tool functions and map them into bridge salvage lanes.')
    ap.add_argument('--sources', nargs='+', required=True)
    ap.add_argument('--output', help='Optional JSON output path.')
    ap.add_argument('--debug-image', help='Optional debug image output path.')
    ap.add_argument('--json', action='store_true')
    args = ap.parse_args()

    report = salvage_inventory([Path(p).resolve() for p in args.sources])
    if args.output:
        out = Path(args.output).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2), encoding='utf-8')
    if args.debug_image:
        render_panel(report, Path(args.debug_image).resolve())
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(json.dumps(report, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
