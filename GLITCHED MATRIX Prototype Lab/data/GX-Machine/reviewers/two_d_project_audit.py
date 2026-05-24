from __future__ import annotations

import argparse
import json
import sys
import warnings
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PANEL_BG = (11, 14, 18, 255)
CARD_BG = (20, 24, 30, 255)
CARD_OUTLINE = (74, 86, 102, 255)
TEXT = (235, 240, 248, 255)
MUTED = (176, 186, 198, 255)
ACCENT = (255, 205, 110, 255)


def _project_key(root: Path, path: Path) -> str:
    rel = path.relative_to(root)
    parts = [p for p in rel.parts[:-1] if p != '__pycache__']
    if not parts:
        return 'root'
    return '/'.join(parts)


def _compile_file(path: Path) -> tuple[bool, str | None, list[str]]:
    text = path.read_text(encoding='utf-8', errors='ignore')
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always')
        try:
            compile(text, str(path), 'exec')
            ok = True
            error = None
        except Exception as exc:
            ok = False
            error = f'{type(exc).__name__}: {exc}'
    warn_lines = [str(w.message) for w in caught]
    return ok, error, warn_lines


def audit_root(root: Path) -> dict[str, Any]:
    files = [p for p in root.rglob('*.py') if '__pycache__' not in p.parts]
    projects: dict[str, dict[str, Any]] = {}
    warning_count = 0
    failure_count = 0
    pygame_required = 0
    for path in sorted(files):
        key = _project_key(root, path)
        info = projects.setdefault(key, {'files': 0, 'ok': True, 'warnings': [], 'errors': [], 'pygame_signals': 0})
        ok, error, warns = _compile_file(path)
        info['files'] += 1
        text = path.read_text(encoding='utf-8', errors='ignore').lower()
        if 'pygame' in text:
            info['pygame_signals'] += 1
        if not ok:
            info['ok'] = False
            info['errors'].append({'file': str(path.relative_to(root)), 'error': error})
            failure_count += 1
        for warn in warns:
            info['warnings'].append({'file': str(path.relative_to(root)), 'warning': warn})
            warning_count += 1
    for info in projects.values():
        if info['pygame_signals']:
            pygame_required += 1
    return {
        'audit': 'two_d_project_audit',
        'root': str(root),
        'summary': {
            'python_file_count': len(files),
            'project_count': len(projects),
            'failure_count': failure_count,
            'warning_count': warning_count,
            'pygame_project_count': pygame_required,
            'runtime_environment_note': 'pygame runtime smoke blocked in this workspace unless pygame is installed successfully',
        },
        'projects': projects,
    }


def save_json(data: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding='utf-8')


def build_debug_panel(report: dict[str, Any], output_path: Path) -> None:
    summary = report['summary']
    cards = list(report['projects'].items())[:12]
    cols = 2
    card_w = 640
    card_h = 200
    margin = 24
    header_h = 124
    rows = max(1, (len(cards) + cols - 1) // cols)
    canvas_w = margin + cols * (card_w + margin)
    canvas_h = header_h + margin + rows * (card_h + margin)
    canvas = Image.new('RGBA', (canvas_w, canvas_h), PANEL_BG)
    draw = ImageDraw.Draw(canvas)
    draw.text((margin, 20), '2D Project Audit v0.15', fill=TEXT)
    lines = [
        f"python files: {summary['python_file_count']}",
        f"projects: {summary['project_count']}",
        f"compile failures: {summary['failure_count']}",
        f"warnings: {summary['warning_count']}",
        f"pygame-signaled projects: {summary['pygame_project_count']}",
    ]
    y = 52
    for line in lines:
        draw.text((margin, y), line, fill=MUTED)
        y += 18
    for idx, (name, info) in enumerate(cards):
        col = idx % cols
        row = idx // cols
        x = margin + col * (card_w + margin)
        y = header_h + margin + row * (card_h + margin)
        draw.rounded_rectangle((x, y, x + card_w, y + card_h), radius=18, fill=CARD_BG, outline=CARD_OUTLINE, width=2)
        status = 'ok' if info['ok'] else 'error'
        tint = (110, 235, 170, 255) if info['ok'] else (255, 110, 110, 255)
        draw.rounded_rectangle((x + 14, y + 14, x + 92, y + 42), radius=12, fill=tint)
        draw.text((x + 30, y + 20), status, fill=(8, 10, 12, 255))
        draw.text((x + 110, y + 18), name[:72], fill=TEXT)
        draw.text((x + 20, y + 60), f"files: {info['files']}  pygame-signals: {info['pygame_signals']}", fill=MUTED)
        if info['warnings']:
            draw.text((x + 20, y + 88), ('warning: ' + info['warnings'][0]['warning'])[:80], fill=TEXT)
        elif info['errors']:
            draw.text((x + 20, y + 88), ('error: ' + info['errors'][0]['error'])[:80], fill=TEXT)
        else:
            draw.text((x + 20, y + 88), 'static compile sweep passed', fill=TEXT)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert('RGB').save(output_path)


def main() -> int:
    ap = argparse.ArgumentParser(description='Run a static compile and warning audit over a 2D donor project root.')
    ap.add_argument('--root', required=True)
    ap.add_argument('--output', required=True)
    ap.add_argument('--debug-image')
    ap.add_argument('--json', action='store_true')
    args = ap.parse_args()

    report = audit_root(Path(args.root).resolve())
    save_json(report, Path(args.output))
    if args.debug_image:
        build_debug_panel(report, Path(args.debug_image))
    if args.json:
        print(json.dumps(report, indent=2))
    return 0 if report['summary']['failure_count'] == 0 else 1


if __name__ == '__main__':
    raise SystemExit(main())
