from __future__ import annotations

import argparse
import atexit
import json
import os
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

try:
    from PIL import Image, ImageDraw
except Exception:  # pragma: no cover - Pillow is optional
    Image = None
    ImageDraw = None


DEFAULT_CACHE_DIR_NAMES = {
    '__pycache__',
    '.pytest_cache',
    '.mypy_cache',
    '.ruff_cache',
    '.cache',
    'cache',
    '.bridge_cache',
    '_bridge_cache',
    'runtime_cache',
}
DEFAULT_TEMP_DIR_NAMES = {
    'tmp',
    'temp',
    '.bridge_temp',
    '_bridge_temp',
    'runtime_temp',
    'scratch',
    'scratchpad',
}
DEFAULT_TEST_DIR_NAMES = {
    '.bridge_test',
    '_bridge_test',
    '_test_workspace',
    'test_workspace',
    'tests_runtime',
    'test_output',
    'test_runs',
    'smoke_test_workspace',
}
DEFAULT_FILE_SUFFIXES = {'.pyc', '.pyo', '.tmp', '.temp'}
DEFAULT_FILE_NAMES = {'Thumbs.db', '.DS_Store'}
DEFAULT_MANAGED_RELATIVE_DIRS = (
    Path('workspace/cache'),
    Path('workspace/temp'),
    Path('workspace/test_workspace'),
)
PROTECTED_TOP_LEVEL_DIRS = {
    'logs',
    'reports',
    'guide',
    'memory',
}


@dataclass
class CleanupCandidate:
    path: Path
    category: str
    reason: str
    kind: str


def _project_root_from(root: Path | str | None) -> Path:
    if root is None:
        return Path(__file__).resolve().parents[1]
    return Path(root).resolve()


def _is_protected(path: Path, project_root: Path, protect_logs: bool) -> bool:
    if not protect_logs:
        return False
    try:
        rel = path.resolve().relative_to(project_root)
    except Exception:
        return False
    parts = rel.parts
    if not parts:
        return False
    return parts[0] in PROTECTED_TOP_LEVEL_DIRS


def _iter_named_dirs(root: Path, names: set[str], category: str, protect_logs: bool) -> list[CleanupCandidate]:
    results: list[CleanupCandidate] = []
    for path in root.rglob('*'):
        if not path.is_dir():
            continue
        if path.name not in names:
            continue
        if _is_protected(path, root, protect_logs):
            continue
        results.append(CleanupCandidate(path=path, category=category, reason=f'directory_name:{path.name}', kind='directory'))
    return results


def _iter_temp_files(root: Path, protect_logs: bool) -> list[CleanupCandidate]:
    results: list[CleanupCandidate] = []
    for path in root.rglob('*'):
        if not path.is_file():
            continue
        if _is_protected(path, root, protect_logs):
            continue
        if path.suffix.lower() in DEFAULT_FILE_SUFFIXES:
            results.append(CleanupCandidate(path=path, category='file_cleanup', reason=f'file_suffix:{path.suffix.lower()}', kind='file'))
        elif path.name in DEFAULT_FILE_NAMES:
            results.append(CleanupCandidate(path=path, category='file_cleanup', reason=f'file_name:{path.name}', kind='file'))
    return results


def _managed_dir_candidates(root: Path, wipe_test_workspace: bool, protect_logs: bool) -> list[CleanupCandidate]:
    results: list[CleanupCandidate] = []
    for rel in DEFAULT_MANAGED_RELATIVE_DIRS:
        path = (root / rel).resolve()
        if not path.exists():
            continue
        if _is_protected(path, root, protect_logs):
            continue
        is_test_dir = 'test' in rel.as_posix().lower()
        if is_test_dir and not wipe_test_workspace:
            continue
        category = 'test_workspace' if is_test_dir else ('cache' if 'cache' in rel.as_posix() else 'temp')
        results.append(CleanupCandidate(path=path, category=category, reason=f'managed_dir:{rel.as_posix()}', kind='directory'))
    return results


def collect_cleanup_candidates(
    root: Path | str | None = None,
    *,
    wipe_test_workspace: bool = False,
    protect_logs: bool = True,
) -> list[CleanupCandidate]:
    project_root = _project_root_from(root)
    candidates: dict[str, CleanupCandidate] = {}
    all_groups = [
        _managed_dir_candidates(project_root, wipe_test_workspace=wipe_test_workspace, protect_logs=protect_logs),
        _iter_named_dirs(project_root, DEFAULT_CACHE_DIR_NAMES, 'cache', protect_logs),
        _iter_named_dirs(project_root, DEFAULT_TEMP_DIR_NAMES, 'temp', protect_logs),
        _iter_temp_files(project_root, protect_logs),
    ]
    if wipe_test_workspace:
        all_groups.append(_iter_named_dirs(project_root, DEFAULT_TEST_DIR_NAMES, 'test_workspace', protect_logs))
    for group in all_groups:
        for item in group:
            if item.path == project_root:
                continue
            candidates[str(item.path)] = item
    return sorted(candidates.values(), key=lambda item: (str(item.path).count(os.sep), str(item.path)), reverse=True)


def perform_cleanup(
    root: Path | str | None = None,
    *,
    wipe_test_workspace: bool = False,
    protect_logs: bool = True,
) -> dict:
    project_root = _project_root_from(root)
    started = datetime.now().isoformat(timespec='seconds')
    candidates = collect_cleanup_candidates(project_root, wipe_test_workspace=wipe_test_workspace, protect_logs=protect_logs)
    removed: list[dict[str, str]] = []
    failures: list[dict[str, str]] = []
    for item in candidates:
        try:
            if item.kind == 'directory':
                if item.path.exists():
                    shutil.rmtree(item.path)
            else:
                if item.path.exists():
                    item.path.unlink()
            removed.append({
                'path': str(item.path),
                'category': item.category,
                'reason': item.reason,
                'kind': item.kind,
            })
        except Exception as exc:  # pragma: no cover - defensive reporting
            failures.append({
                'path': str(item.path),
                'category': item.category,
                'reason': item.reason,
                'kind': item.kind,
                'error': str(exc),
            })
    ended = datetime.now().isoformat(timespec='seconds')
    return {
        'tool': 'bridge_exit_cleanup',
        'project_root': str(project_root),
        'started_at': started,
        'ended_at': ended,
        'status': {
            'ok': not failures,
            'candidate_count': len(candidates),
            'removed_count': len(removed),
            'failure_count': len(failures),
        },
        'config': {
            'wipe_test_workspace': wipe_test_workspace,
            'protect_logs': protect_logs,
            'managed_relative_dirs': [str(path) for path in DEFAULT_MANAGED_RELATIVE_DIRS],
        },
        'removed': removed,
        'failures': failures,
        'notes': [
            'Logs, reports, and source modules are protected by default so proof artifacts survive a passing run.',
            'Use --wipe-test-workspace when you also want the managed test workspace removed after a commit or validation cycle.',
            'Python bytecode caches are removed even when no managed workspace exists.',
        ],
    }


def _write_json(path: Path | str | None, payload: dict) -> None:
    if not path:
        return
    out = Path(path).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding='utf-8')


def _write_debug_image(path: Path | str | None, payload: dict) -> None:
    if not path or Image is None or ImageDraw is None:
        return
    lines = [
        'GPT Bridge Exit Cleanup',
        f"Removed: {payload['status']['removed_count']}",
        f"Failures: {payload['status']['failure_count']}",
        f"Wipe test workspace: {payload['config']['wipe_test_workspace']}",
        '',
        'Recent removals:',
    ]
    for entry in payload['removed'][:10]:
        rel = entry['path']
        try:
            rel = str(Path(entry['path']).resolve().relative_to(Path(payload['project_root']).resolve()))
        except Exception:
            pass
        lines.append(f"- [{entry['category']}] {rel}")
    if payload['failures']:
        lines.append('')
        lines.append('Failures:')
        for entry in payload['failures'][:4]:
            lines.append(f"- {entry['path']}: {entry['error']}")
    width, height = 1280, 720
    image = Image.new('RGB', (width, height), (16, 18, 24))
    draw = ImageDraw.Draw(image)
    y = 32
    for index, line in enumerate(lines):
        fill = (220, 230, 240) if index == 0 else ((120, 220, 180) if line.startswith('- [') else (180, 190, 205))
        draw.text((32, y), line, fill=fill)
        y += 28 if index == 0 else 24
        if y > height - 32:
            break
    out = Path(path).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    image.save(out)


_REGISTERED_HANDLE = None


class _ExitCleanupHandle:
    def __init__(self, root: Path, output_path: Path | None, debug_image_path: Path | None, wipe_test_workspace: bool, protect_logs: bool):
        self.root = root
        self.output_path = output_path
        self.debug_image_path = debug_image_path
        self.wipe_test_workspace = wipe_test_workspace
        self.protect_logs = protect_logs
        self._ran = False

    def __call__(self) -> None:
        if self._ran:
            return
        self._ran = True
        report = perform_cleanup(
            self.root,
            wipe_test_workspace=self.wipe_test_workspace,
            protect_logs=self.protect_logs,
        )
        _write_json(self.output_path, report)
        _write_debug_image(self.debug_image_path, report)


def install_exit_cleanup(
    root: Path | str | None = None,
    *,
    output_path: Path | str | None = None,
    debug_image_path: Path | str | None = None,
    wipe_test_workspace: bool = False,
    protect_logs: bool = True,
    enabled: bool = True,
):
    global _REGISTERED_HANDLE
    if not enabled:
        return None
    if _REGISTERED_HANDLE is not None:
        return _REGISTERED_HANDLE
    project_root = _project_root_from(root)
    handle = _ExitCleanupHandle(
        root=project_root,
        output_path=Path(output_path).resolve() if output_path else None,
        debug_image_path=Path(debug_image_path).resolve() if debug_image_path else None,
        wipe_test_workspace=wipe_test_workspace,
        protect_logs=protect_logs,
    )
    atexit.register(handle)
    _REGISTERED_HANDLE = handle
    return handle


def main() -> int:
    ap = argparse.ArgumentParser(description='Clean cache, temp, and optional test-workspace files for the GPT bridge.')
    ap.add_argument('--root', default='.', help='Project root to clean.')
    ap.add_argument('--wipe-test-workspace', action='store_true', help='Also remove the managed test workspace directories.')
    ap.add_argument('--allow-log-clean', action='store_true', help='Permit cleanup candidates inside logs and reports.')
    ap.add_argument('--output', help='Optional JSON report path.')
    ap.add_argument('--debug-image', help='Optional PNG summary path.')
    ap.add_argument('--json', action='store_true', help='Print structured JSON.')
    args = ap.parse_args()

    report = perform_cleanup(
        root=args.root,
        wipe_test_workspace=args.wipe_test_workspace,
        protect_logs=not args.allow_log_clean,
    )
    _write_json(args.output, report)
    _write_debug_image(args.debug_image, report)
    print(json.dumps(report, indent=2))
    return 0 if report['status']['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
