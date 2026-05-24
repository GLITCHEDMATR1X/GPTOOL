from __future__ import annotations

import argparse
import ast
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from PIL import Image, ImageDraw

PANEL_BG = (11, 14, 18, 255)
CARD_BG = (20, 24, 31, 255)
CARD_OUTLINE = (68, 82, 102, 255)
TEXT = (236, 241, 248, 255)
MUTED = (165, 176, 190, 255)
ACCENT = (115, 199, 255, 255)
GOOD = (110, 228, 168, 255)
WARN = (255, 199, 109, 255)


@dataclass
class SymbolInfo:
    key: str
    name: str
    kind: str
    lineno: int
    end_lineno: int
    parent: Optional[str] = None
    imports: set[str] = field(default_factory=set)
    dependencies: set[str] = field(default_factory=set)
    calls: set[str] = field(default_factory=set)
    assigns: set[str] = field(default_factory=set)
    doc: str = ''


class PythonAnalyzer(ast.NodeVisitor):
    def __init__(self, source: str):
        self.source = source
        self.tree = ast.parse(source)
        self.symbols: dict[str, SymbolInfo] = {}
        self.imports: set[str] = set()
        self.module_assigns: set[str] = set()
        self._stack: list[SymbolInfo] = []
        self.visit(self.tree)

    def _add_symbol(self, node: ast.AST, kind: str, name: str) -> SymbolInfo:
        parent_key = self._stack[-1].key if self._stack else None
        key = f"{parent_key}.{name}" if parent_key else name
        info = SymbolInfo(
            key=key,
            name=name,
            kind=kind,
            lineno=getattr(node, 'lineno', 1),
            end_lineno=getattr(node, 'end_lineno', getattr(node, 'lineno', 1)),
            parent=parent_key,
            doc=ast.get_docstring(node) or '',
        )
        self.symbols[key] = info
        return info

    def visit_ClassDef(self, node: ast.ClassDef):
        info = self._add_symbol(node, 'class', node.name)
        self._stack.append(info)
        self.generic_visit(node)
        self._stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef):
        info = self._add_symbol(node, 'function', node.name)
        self._stack.append(info)
        self.generic_visit(node)
        self._stack.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        info = self._add_symbol(node, 'async_function', node.name)
        self._stack.append(info)
        self.generic_visit(node)
        self._stack.pop()

    def visit_Import(self, node: ast.Import):
        names = {alias.asname or alias.name.split('.')[0] for alias in node.names}
        if self._stack:
            self._stack[-1].imports |= names
            self._stack[-1].dependencies |= names
        else:
            self.imports |= names

    def visit_ImportFrom(self, node: ast.ImportFrom):
        names = {alias.asname or alias.name for alias in node.names}
        if node.module:
            names.add(node.module.split('.')[0])
        if self._stack:
            self._stack[-1].imports |= names
            self._stack[-1].dependencies |= names
        else:
            self.imports |= names

    def visit_Name(self, node: ast.Name):
        if self._stack:
            cur = self._stack[-1]
            if isinstance(node.ctx, ast.Load):
                cur.dependencies.add(node.id)
            elif isinstance(node.ctx, (ast.Store, ast.Del)):
                cur.assigns.add(node.id)
        elif isinstance(node.ctx, (ast.Store, ast.Del)):
            self.module_assigns.add(node.id)

    def visit_Call(self, node: ast.Call):
        if self._stack:
            cur = self._stack[-1]
            name = _expr_name(node.func)
            if name:
                cur.calls.add(name)
                cur.dependencies.add(name)
        self.generic_visit(node)


def _expr_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _expr_name(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    if isinstance(node, ast.Call):
        return _expr_name(node.func)
    return None


def build_module_index(project_root: Optional[Path]) -> dict[str, Path]:
    index: dict[str, Path] = {}
    if not project_root or not project_root.exists():
        return index
    for path in project_root.rglob('*.py'):
        rel = path.relative_to(project_root)
        parts = list(rel.with_suffix('').parts)
        if parts and parts[-1] == '__init__':
            parts = parts[:-1]
        if not parts:
            continue
        key = '.'.join(parts)
        index[key] = path
    return index


def resolve_local_module_path(module_name: str, context_path: Optional[Path], project_root: Optional[Path], module_index: Optional[dict[str, Path]] = None) -> Optional[Path]:
    module_index = module_index or build_module_index(project_root)
    if module_name in module_index:
        return module_index[module_name]
    if context_path and project_root and context_path.exists():
        direct = context_path.parent / f"{module_name.replace('.', '/')}.py"
        if direct.exists():
            return direct
        pkg_init = context_path.parent / module_name.replace('.', '/') / '__init__.py'
        if pkg_init.exists():
            return pkg_init
    return None


def extract_preview_signals(source: str) -> dict[str, Any]:
    tree = ast.parse(source)
    signals = {
        'uses_panda3d': False,
        'uses_directgui': False,
        'uses_pygame': False,
        'loads_models': False,
        'ui_widgets': [],
        'preview_calls': [],
    }
    ui_hits: set[str] = set()
    preview_calls: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.name.lower()
                if name.startswith('pygame'):
                    signals['uses_pygame'] = True
        elif isinstance(node, ast.ImportFrom):
            mod = (node.module or '').lower()
            if mod.startswith('panda3d') or mod.startswith('direct.'):
                signals['uses_panda3d'] = True
            if 'direct.gui' in mod:
                signals['uses_directgui'] = True
                ui_hits |= {alias.name for alias in node.names}
        elif isinstance(node, ast.Call):
            name = _expr_name(node.func) or ''
            lname = name.lower()
            if 'loadmodel' in lname or 'loader.loadmodel' in lname:
                signals['loads_models'] = True
            if any(token in lname for token in ('showbase', 'loadprcfiledata', 'onscreentext', 'directbutton', 'directframe', 'setpos', 'setscale')):
                preview_calls.add(name)
    signals['ui_widgets'] = sorted(ui_hits)[:12]
    signals['preview_calls'] = sorted(preview_calls)[:16]
    return signals


def analyze_python_file(path: Path, project_root: Optional[Path] = None) -> dict[str, Any]:
    source = path.read_text(encoding='utf-8', errors='replace')
    analyzer = PythonAnalyzer(source)
    symbols = list(analyzer.symbols.values())
    preview = extract_preview_signals(source)
    classes = [s.key for s in symbols if s.kind == 'class']
    functions = [s.key for s in symbols if 'function' in s.kind]
    report = {
        'tool': 'code_preview_analysis',
        'path': str(path),
        'project_root': str(project_root) if project_root else None,
        'symbol_count': len(symbols),
        'class_count': len(classes),
        'function_count': len(functions),
        'imports': sorted(analyzer.imports)[:40],
        'module_assigns': sorted(analyzer.module_assigns)[:40],
        'classes': classes[:24],
        'functions': functions[:48],
        'preview_signals': preview,
        'notes': [
            'AST scan is static and does not execute the target.',
            'Preview signals are heuristic and intended for bridge-side planning.',
        ],
    }
    return report


def render_debug_panel(report: dict[str, Any], output_path: Path) -> None:
    img = Image.new('RGBA', (1400, 860), PANEL_BG)
    draw = ImageDraw.Draw(img)

    def card(x0, y0, x1, y1, title, lines, accent=ACCENT):
        draw.rounded_rectangle((x0, y0, x1, y1), radius=18, fill=CARD_BG, outline=CARD_OUTLINE, width=2)
        draw.text((x0 + 18, y0 + 14), title, fill=accent)
        y = y0 + 46
        for line, color in lines:
            draw.text((x0 + 18, y), line[:116], fill=color)
            y += 24

    title = f"Code Preview Analysis — {Path(report['path']).name}"
    draw.text((28, 22), title, fill=TEXT)
    draw.text((28, 52), 'Static symbol graph + preview-signal extraction salvaged for bridge-side code understanding.', fill=MUTED)

    stats = [
        (f"symbols: {report['symbol_count']}", TEXT),
        (f"classes: {report['class_count']}", GOOD),
        (f"functions: {report['function_count']}", GOOD),
        (f"imports: {len(report['imports'])}", MUTED),
    ]
    preview = report['preview_signals']
    flags = [
        (f"uses_panda3d: {preview['uses_panda3d']}", GOOD if preview['uses_panda3d'] else WARN),
        (f"uses_directgui: {preview['uses_directgui']}", GOOD if preview['uses_directgui'] else MUTED),
        (f"uses_pygame: {preview['uses_pygame']}", GOOD if preview['uses_pygame'] else MUTED),
        (f"loads_models: {preview['loads_models']}", GOOD if preview['loads_models'] else MUTED),
    ]
    card(28, 94, 454, 278, 'Summary', stats + flags)
    card(476, 94, 952, 360, 'Classes', [(c, TEXT) for c in report['classes'][:10]] or [('none', MUTED)])
    card(974, 94, 1370, 360, 'Functions', [(f, TEXT) for f in report['functions'][:10]] or [('none', MUTED)])
    card(28, 304, 680, 608, 'Preview Calls', [(c, TEXT) for c in preview['preview_calls'][:12]] or [('none', MUTED)])
    card(702, 304, 1370, 608, 'Imports / Widgets', [(i, TEXT) for i in report['imports'][:10]] + [(f"widget: {w}", ACCENT) for w in preview['ui_widgets'][:8]] or [('none', MUTED)])
    card(28, 632, 1370, 820, 'Notes', [(n, MUTED) for n in report['notes']])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(output_path)


def main() -> int:
    ap = argparse.ArgumentParser(description='Static code-preview analyzer salvaged from tool donors.')
    ap.add_argument('target', help='Python file to analyze.')
    ap.add_argument('--project-root', help='Optional project root for local-module resolution context.')
    ap.add_argument('--output', help='Optional JSON report path.')
    ap.add_argument('--debug-image', help='Optional debug image path.')
    ap.add_argument('--json', action='store_true')
    args = ap.parse_args()

    path = Path(args.target).resolve()
    project_root = Path(args.project_root).resolve() if args.project_root else path.parent
    report = analyze_python_file(path, project_root=project_root)
    if args.output:
        out = Path(args.output).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2), encoding='utf-8')
    if args.debug_image:
        render_debug_panel(report, Path(args.debug_image).resolve())
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"Analyzed {path.name}: {report['class_count']} classes, {report['function_count']} functions")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
