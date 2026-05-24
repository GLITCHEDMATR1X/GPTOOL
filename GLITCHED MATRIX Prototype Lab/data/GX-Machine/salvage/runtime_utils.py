from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import shutil
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any


def backup_existing_file(path: Path, category: str = 'general') -> Path | None:
    path = Path(path)
    if not path.exists() or not path.is_file():
        return None
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_dir = path.parent / '_bridge_backups' / category
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / f"{path.stem}_{stamp}{path.suffix}"
    shutil.copy2(path, backup_path)
    return backup_path


def safe_write_text(path: Path, content: str, category: str = 'general') -> Path | None:
    path = Path(path)
    backup = backup_existing_file(path, category=category)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding='utf-8')
    return backup


def write_crash_log(log_path: Path, exc_type, exc_value, exc_tb) -> None:
    payload = {
        'timestamp': datetime.now().isoformat(timespec='seconds'),
        'exc_type': getattr(exc_type, '__name__', str(exc_type)),
        'exc_value': str(exc_value),
        'traceback': ''.join(traceback.format_exception(exc_type, exc_value, exc_tb))[-16000:],
    }
    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(json.dumps(payload, indent=2), encoding='utf-8')


def install_crash_hook(log_path: Path) -> None:
    def _hook(exc_type, exc_value, exc_tb):
        write_crash_log(log_path, exc_type, exc_value, exc_tb)
        sys.__excepthook__(exc_type, exc_value, exc_tb)
    sys.excepthook = _hook


def guess_engine_from_text(source_text: str) -> str:
    lower = source_text.lower()
    if 'direct.showbase' in lower or 'panda3d.core' in lower:
        return 'panda3d'
    if 'pygame' in lower:
        return 'pygame'
    if 'godot' in lower:
        return 'godot'
    if 'unityengine' in lower:
        return 'unity'
    return 'python'


def guess_engine(entry: Path) -> str:
    try:
        return guess_engine_from_text(Path(entry).read_text(encoding='utf-8', errors='replace'))
    except Exception:
        return 'unknown'


def discover_projects(root_dir: Path) -> list[dict[str, Any]]:
    root_dir = Path(root_dir)
    projects: list[dict[str, Any]] = []
    for path in sorted(root_dir.rglob('*.py')):
        name = path.name.lower()
        if name.startswith('_') or '__pycache__' in path.parts:
            continue
        engine = guess_engine(path)
        title = path.parent.name if path.parent != root_dir else path.stem
        projects.append({
            'title': title,
            'entry': str(path),
            'engine': engine,
            'path_hash': hashlib.sha1(str(path).encode('utf-8')).hexdigest()[:10],
        })
    return projects


def compute_diff_stats(left_text: str, right_text: str) -> dict[str, Any]:
    left_lines = left_text.splitlines()
    right_lines = right_text.splitlines()
    diff = list(difflib.unified_diff(left_lines, right_lines, lineterm=''))
    added = sum(1 for line in diff if line.startswith('+') and not line.startswith('+++'))
    removed = sum(1 for line in diff if line.startswith('-') and not line.startswith('---'))
    changed = min(added, removed)
    return {
        'left_lines': len(left_lines),
        'right_lines': len(right_lines),
        'added_lines': added,
        'removed_lines': removed,
        'changed_lines_estimate': changed,
        'diff_excerpt': diff[:80],
    }


def create_manifest(project_root: Path) -> dict[str, Any]:
    root = Path(project_root)
    projects = discover_projects(root)
    engines: dict[str, int] = {}
    for proj in projects:
        engines[proj['engine']] = engines.get(proj['engine'], 0) + 1
    return {
        'tool': 'runtime_utils',
        'project_root': str(root),
        'project_count': len(projects),
        'engine_counts': engines,
        'projects': projects[:120],
        'notes': [
            'Discovery is file-based and does not claim a full project graph.',
            'Use this as a safe manifest/before-write helper layer.',
        ],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description='Runtime/file safety utilities salvaged from tool donors.')
    ap.add_argument('--project-root', help='Optional project root to scan into a manifest.')
    ap.add_argument('--compare-left', help='Optional left file for diff stats.')
    ap.add_argument('--compare-right', help='Optional right file for diff stats.')
    ap.add_argument('--output', help='Optional JSON output path.')
    ap.add_argument('--json', action='store_true')
    args = ap.parse_args()

    report: dict[str, Any] = {'tool': 'runtime_utils'}
    if args.project_root:
        report['manifest'] = create_manifest(Path(args.project_root).resolve())
    if args.compare_left and args.compare_right:
        report['diff'] = compute_diff_stats(
            Path(args.compare_left).read_text(encoding='utf-8', errors='replace'),
            Path(args.compare_right).read_text(encoding='utf-8', errors='replace'),
        )
    if args.output:
        out = Path(args.output).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2), encoding='utf-8')
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(json.dumps(report, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
