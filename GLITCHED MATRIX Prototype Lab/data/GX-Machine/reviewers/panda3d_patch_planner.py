from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

BRIDGE_ROOT = Path(__file__).resolve().parents[1]
if str(BRIDGE_ROOT) not in sys.path:
    sys.path.insert(0, str(BRIDGE_ROOT))

from salvage.code_preview_analysis import PythonAnalyzer

PANEL_BG = (11, 14, 18, 255)
CARD_BG = (20, 24, 31, 255)
CARD_OUTLINE = (68, 82, 102, 255)
TEXT = (236, 241, 248, 255)
MUTED = (165, 176, 190, 255)
ACCENT = (115, 199, 255, 255)
GOOD = (110, 228, 168, 255)
WARN = (255, 199, 109, 255)

PLAYER_HINTS = ('player', 'avatar', 'character', 'pawn', 'actor')
CAMERA_HINTS = ('camera', 'cam', 'cam_np')
UPDATE_HINTS = ('update', 'tick', 'step', 'move', 'control')


def _read_source(path: Path) -> str:
    return path.read_text(encoding='utf-8', errors='replace')


def _class_bases(node: ast.ClassDef) -> list[str]:
    out = []
    for base in node.bases:
        if isinstance(base, ast.Name):
            out.append(base.id)
        elif isinstance(base, ast.Attribute):
            out.append(base.attr)
    return out


def _find_showbase_classes(tree: ast.AST) -> list[dict[str, Any]]:
    matches = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            bases = _class_bases(node)
            if 'ShowBase' in bases:
                matches.append({'name': node.name, 'lineno': node.lineno, 'bases': bases})
    return matches


def _candidate_score(name: str, keywords: tuple[str, ...]) -> int:
    lower = name.lower()
    if lower in keywords:
        return 100
    if any(token in lower for token in ('distance', 'height', 'heading', 'offset', 'speed', 'sensitivity')) and lower not in keywords:
        return -100
    score = 0
    for hint in keywords:
        if hint in lower:
            score += 25
    if lower.startswith('camera_') or lower.endswith('_camera'):
        score += 8
    return score


def _find_assignments(tree: ast.AST, keywords: tuple[str, ...]) -> list[dict[str, Any]]:
    matches = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                raw_name = None
                if isinstance(target, ast.Attribute):
                    raw_name = target.attr
                elif isinstance(target, ast.Name):
                    raw_name = target.id
                if raw_name is None:
                    continue
                score = _candidate_score(raw_name, keywords)
                if score > 0:
                    matches.append({'name': raw_name, 'lineno': node.lineno, 'score': score})
    matches.sort(key=lambda item: (-item['score'], item['lineno'], item['name']))
    return matches


def _find_update_methods(tree: ast.AST) -> list[dict[str, Any]]:
    hits = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            lname = node.name.lower()
            args = [a.arg for a in node.args.args]
            if any(h in lname for h in UPDATE_HINTS) or 'task' in args:
                hits.append({'name': node.name, 'lineno': node.lineno, 'args': args})
    return hits


def build_patch_plan(target: Path) -> dict[str, Any]:
    source = _read_source(target)
    analyzer = PythonAnalyzer(source)
    tree = analyzer.tree
    showbase_classes = _find_showbase_classes(tree)
    players = _find_assignments(tree, PLAYER_HINTS)
    cameras = _find_assignments(tree, CAMERA_HINTS)
    updates = _find_update_methods(tree)
    uses_helper = 'install_trace_helper' in source or 'Panda3DTraceHelper' in source
    likely_class = showbase_classes[0]['name'] if showbase_classes else None
    player_name = players[0]['name'] if players else 'self.player'
    camera_name = cameras[0]['name'] if cameras else 'self.camera'
    update_name = updates[0]['name'] if updates else None
    import_line = 'from reviewers.panda3d_trace_helper import install_trace_helper'
    player_expr = player_name if player_name.startswith('self.') else 'self.' + player_name
    camera_expr = camera_name if camera_name.startswith('self.') else 'self.' + camera_name
    install_snippet = '\n'.join([
        '        self._bridge_trace_helper = install_trace_helper(',
        '            self,',
        f'            {player_expr},',
        f'            camera={camera_expr},',
        f'            actor={player_expr},',
        f"            grounded_getter=lambda: bool(getattr({player_expr}, 'getPythonTag', lambda *_: True)('bridge_grounded'))," ,
        f"            collision_getter=lambda: int(getattr({player_expr}, 'getPythonTag', lambda *_: 0)('bridge_collision_count') or 0)," ,
        f"            anim_getter=lambda: getattr({player_expr}, 'getPythonTag', lambda *_: None)('current_anim')," ,
        f"            label='{target.stem}'," ,
        '        )',
    ])
    patch_points = []
    if showbase_classes:
        patch_points.append({'kind': 'class_init', 'line': showbase_classes[0]['lineno'], 'hint': 'Insert helper import at module top and install block near the end of __init__ once player and camera exist.'})
    if updates:
        patch_points.append({'kind': 'update_loop', 'line': updates[0]['lineno'], 'hint': 'Optional: call helper.set_metrics(...) here when you have explicit grounded/collision/animation/controller values.'})
    confidence = 0.3
    confidence += 0.25 if showbase_classes else 0.0
    confidence += 0.2 if players else 0.0
    confidence += 0.15 if cameras else 0.0
    confidence += 0.1 if updates else 0.0
    confidence -= 0.2 if uses_helper else 0.0
    confidence = max(0.0, min(0.98, confidence))
    return {
        'tool': 'panda3d_patch_planner',
        'target': str(target),
        'already_helper_instrumented': uses_helper,
        'showbase_classes': showbase_classes,
        'player_candidates': players[:8],
        'camera_candidates': cameras[:8],
        'update_candidates': updates[:8],
        'import_line': import_line,
        'install_snippet': install_snippet,
        'patch_points': patch_points,
        'recommended_class': likely_class,
        'confidence': round(confidence, 3),
        'notes': [
            'Planner output is heuristic and should be applied surgically.',
            'Prefer attaching the helper after player and camera objects exist.',
            'When a project already has explicit grounded/collision/animation data, wire those into install_trace_helper getter hooks or helper.set_metrics calls.',
        ],
    }


def render_panel(report: dict[str, Any], output_path: Path) -> None:
    img = Image.new('RGBA', (1440, 900), PANEL_BG)
    draw = ImageDraw.Draw(img)
    draw.text((28, 22), f"Panda3D Patch Planner — {Path(report['target']).name}", fill=TEXT)
    draw.text((28, 50), 'Plans a helper insertion path so live trace capture stops relying on scene-graph guesswork.', fill=MUTED)

    def card(x0, y0, x1, y1, title, lines, accent=ACCENT):
        draw.rounded_rectangle((x0, y0, x1, y1), radius=18, fill=CARD_BG, outline=CARD_OUTLINE, width=2)
        draw.text((x0 + 18, y0 + 14), title, fill=accent)
        y = y0 + 44
        for line, color in lines:
            draw.text((x0 + 18, y), line[:120], fill=color)
            y += 24

    summary = [
        (f"confidence: {report['confidence']}", GOOD if report['confidence'] >= 0.7 else WARN),
        (f"helper already present: {report['already_helper_instrumented']}", WARN if report['already_helper_instrumented'] else TEXT),
        (f"showbase classes: {len(report['showbase_classes'])}", TEXT),
        (f"player candidates: {len(report['player_candidates'])}", TEXT),
        (f"camera candidates: {len(report['camera_candidates'])}", TEXT),
        (f"update candidates: {len(report['update_candidates'])}", TEXT),
    ]
    card(28, 94, 430, 300, 'Summary', summary)
    card(452, 94, 900, 300, 'Patch Points', [(f"line {p['line']} — {p['hint']}", TEXT) for p in report['patch_points']] or [('none', MUTED)])
    card(922, 94, 1412, 300, 'Candidates', [(f"player: {c['name']} @ {c['lineno']}", GOOD) for c in report['player_candidates'][:3]] + [(f"camera: {c['name']} @ {c['lineno']}", ACCENT) for c in report['camera_candidates'][:3]] + [(f"update: {c['name']} @ {c['lineno']}", TEXT) for c in report['update_candidates'][:3]] or [('none', MUTED)])
    snippet_lines = [(line, TEXT) for line in report['install_snippet'].splitlines()[:14]]
    card(28, 326, 1412, 730, 'Suggested Install Snippet', snippet_lines)
    card(28, 754, 1412, 874, 'Notes', [(n, MUTED) for n in report['notes']])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(output_path)


def main() -> int:
    ap = argparse.ArgumentParser(description='Plan where to add Panda3D trace-helper instrumentation in a project script.')
    ap.add_argument('--target', required=True, help='Python file to inspect for ShowBase/player/camera/update hooks.')
    ap.add_argument('--output', help='Optional JSON output path.')
    ap.add_argument('--debug-image', help='Optional debug image path.')
    ap.add_argument('--snippet-output', help='Optional path to write the suggested install snippet as text.')
    ap.add_argument('--json', action='store_true')
    args = ap.parse_args()

    report = build_patch_plan(Path(args.target).resolve())
    if args.output:
        out = Path(args.output).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2), encoding='utf-8')
    if args.snippet_output:
        out = Path(args.snippet_output).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        snippet_text = ("# Suggested helper insertion snippet\n" + report['import_line'] + "\n\nSNIPPET = \"\"\"\n" + report['install_snippet'] + "\n\"\"\"\n")
        out.write_text(snippet_text, encoding='utf-8')
    if args.debug_image:
        render_panel(report, Path(args.debug_image).resolve())
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(json.dumps(report, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
