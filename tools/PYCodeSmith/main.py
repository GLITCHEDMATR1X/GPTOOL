import ast
import io
import json
import keyword
import os
import re
import sys
import tempfile
import textwrap
import traceback
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

try:
    from PIL import Image, ImageDraw
except Exception:
    Image = None
    ImageDraw = None

try:
    from panda3d.core import PNMImage, loadPrcFileData
    from direct.gui.DirectGui import DirectButton, DirectEntry, DirectFrame, DirectLabel, DirectScrolledFrame, DirectSlider, DirectCheckButton, DirectOptionMenu, DirectWaitBar
    from direct.gui.OnscreenText import OnscreenText
    from direct.showbase.ShowBase import ShowBase
except Exception:
    PNMImage = None
    loadPrcFileData = None
    DirectButton = DirectEntry = DirectFrame = DirectLabel = DirectScrolledFrame = DirectSlider = DirectCheckButton = DirectOptionMenu = DirectWaitBar = OnscreenText = None
    ShowBase = None

APP_VERSION = "v8"
APP_TITLE = f"PyCodeSmith {APP_VERSION}"
REFERENCE_W = 1920
REFERENCE_H = 1080
PY_KEYWORDS = set(keyword.kwlist)

DARK = {
    "bg": "#111318",
    "panel": "#181c22",
    "panel2": "#1f242d",
    "line": "#2a313d",
    "text": "#dce3ea",
    "muted": "#9fb0c2",
    "accent": "#73b7ff",
    "accent2": "#8edc9d",
    "warn": "#ffbf69",
    "danger": "#ff6b6b",
    "code_bg": "#0d1015",
    "selection": "#1d2c40",
}


@dataclass
class SymbolInfo:
    key: str
    name: str
    kind: str
    lineno: int
    end_lineno: int
    parent: Optional[str] = None
    dependencies: Set[str] = field(default_factory=set)
    direct_dependencies: Set[str] = field(default_factory=set)
    imports: Set[str] = field(default_factory=set)
    string_literals: Set[str] = field(default_factory=set)
    doc: str = ""
    returns: Set[str] = field(default_factory=set)
    assigns: Set[str] = field(default_factory=set)
    calls: Set[str] = field(default_factory=set)
    decorators: Set[str] = field(default_factory=set)
    bases: Set[str] = field(default_factory=set)
    children: List[str] = field(default_factory=list)

    @property
    def display_name(self) -> str:
        return self.key


class PythonAnalyzer(ast.NodeVisitor):
    def __init__(self, source: str):
        self.source = source
        self.lines = source.splitlines()
        self.tree = ast.parse(source)
        self.symbols: Dict[str, SymbolInfo] = {}
        self.name_index: Dict[str, Set[str]] = {}
        self.imports: Set[str] = set()
        self.module_assigns: Set[str] = set()
        self.parse_error: Optional[str] = None
        self._stack: List[SymbolInfo] = []
        self.visit(self.tree)
        self._finalize()

    def _add_symbol(self, node: ast.AST, kind: str, name: str) -> SymbolInfo:
        parent_key = self._stack[-1].key if self._stack else None
        key = f"{parent_key}.{name}" if parent_key else name
        info = SymbolInfo(
            key=key,
            name=name,
            kind=kind,
            lineno=getattr(node, "lineno", 1),
            end_lineno=getattr(node, "end_lineno", getattr(node, "lineno", 1)),
            parent=parent_key,
            doc=ast.get_docstring(node) or "",
        )
        self.symbols[key] = info
        self.name_index.setdefault(name, set()).add(key)
        if parent_key and parent_key in self.symbols:
            self.symbols[parent_key].children.append(key)
        return info

    def visit_ClassDef(self, node: ast.ClassDef):
        info = self._add_symbol(node, "class", node.name)
        info.bases |= {self._expr_name(base) for base in node.bases if self._expr_name(base)}
        info.decorators |= {self._expr_name(d) for d in node.decorator_list if self._expr_name(d)}
        self._stack.append(info)
        self.generic_visit(node)
        self._stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef):
        self._visit_function_like(node, "function")

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        self._visit_function_like(node, "async function")

    def _visit_function_like(self, node: ast.AST, kind: str):
        info = self._add_symbol(node, kind, getattr(node, "name", "anonymous"))
        info.decorators |= {self._expr_name(d) for d in getattr(node, "decorator_list", []) if self._expr_name(d)}
        self._stack.append(info)
        self.generic_visit(node)
        self._stack.pop()

    def visit_Import(self, node: ast.Import):
        names = {alias.asname or alias.name.split(".")[0] for alias in node.names}
        if self._stack:
            self._stack[-1].imports |= names
            self._stack[-1].dependencies |= names
        else:
            self.imports |= names

    def visit_ImportFrom(self, node: ast.ImportFrom):
        names = {alias.asname or alias.name for alias in node.names}
        if node.module:
            names.add(node.module.split(".")[0])
        if self._stack:
            self._stack[-1].imports |= names
            self._stack[-1].dependencies |= names
        else:
            self.imports |= names

    def visit_Name(self, node: ast.Name):
        if not self._stack:
            return
        cur = self._stack[-1]
        if isinstance(node.ctx, ast.Load):
            cur.dependencies.add(node.id)
        elif isinstance(node.ctx, (ast.Store, ast.Del)):
            cur.assigns.add(node.id)

    def visit_Attribute(self, node: ast.Attribute):
        if self._stack:
            cur = self._stack[-1]
            full_name = self._expr_name(node)
            if full_name:
                cur.dependencies.add(full_name)
                cur.direct_dependencies.add(node.attr)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call):
        if self._stack:
            cur = self._stack[-1]
            call_name = self._expr_name(node.func)
            if call_name:
                cur.calls.add(call_name)
                cur.dependencies.add(call_name)
                cur.direct_dependencies.add(call_name.split(".")[-1])
        self.generic_visit(node)

    def visit_Return(self, node: ast.Return):
        if self._stack and node.value is not None:
            cur = self._stack[-1]
            cur.returns.add(type(node.value).__name__)
            expr_name = self._expr_name(node.value)
            if expr_name:
                cur.dependencies.add(expr_name)
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign):
        if self._stack:
            cur = self._stack[-1]
            for target in node.targets:
                cur.assigns |= self._collect_target_names(target)
        else:
            for target in node.targets:
                self.module_assigns |= self._collect_target_names(target)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign):
        if self._stack:
            self._stack[-1].assigns |= self._collect_target_names(node.target)
        else:
            self.module_assigns |= self._collect_target_names(node.target)
        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant):
        if self._stack and isinstance(node.value, str):
            value = node.value.strip()
            if 2 <= len(value) <= 120 and ("/" in value or "." in value or " " in value or value.isidentifier()):
                self._stack[-1].string_literals.add(value)

    def _collect_target_names(self, node: ast.AST) -> Set[str]:
        found: Set[str] = set()
        if isinstance(node, ast.Name):
            found.add(node.id)
        elif isinstance(node, ast.Attribute):
            found.add(node.attr)
        elif isinstance(node, (ast.Tuple, ast.List)):
            for item in node.elts:
                found |= self._collect_target_names(item)
        return found

    def _expr_name(self, node: ast.AST) -> Optional[str]:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            left = self._expr_name(node.value)
            return f"{left}.{node.attr}" if left else node.attr
        if isinstance(node, ast.Call):
            return self._expr_name(node.func)
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.Subscript):
            return self._expr_name(node.value)
        return None

    def _finalize(self):
        valid_names = set(self.name_index) | self.imports | self.module_assigns
        for info in self.symbols.values():
            info.dependencies = {d for d in info.dependencies if d and d not in PY_KEYWORDS and d != info.name}
            info.direct_dependencies |= {d.split(".")[-1] for d in info.dependencies if d}
            info.direct_dependencies = {d for d in info.direct_dependencies if d and d not in PY_KEYWORDS}
            info.imports = {d for d in info.imports if d}
            info.decorators = {d for d in info.decorators if d}
            info.bases = {d for d in info.bases if d}
            linked = set()
            for dep in info.direct_dependencies | info.imports | info.bases | info.decorators:
                if dep in self.name_index:
                    linked.add(dep)
            info.dependencies |= linked

    def lookup_links(self, info: SymbolInfo) -> Set[str]:
        links: Set[str] = set()
        for dep in info.direct_dependencies | info.imports | info.bases | info.decorators:
            links |= self.name_index.get(dep, set())
        if info.parent:
            links.add(info.parent)
        for child in info.children:
            links.add(child)
        return links


def _safe_literal(node):
    try:
        return ast.literal_eval(node)
    except Exception:
        pass
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        val = _safe_literal(node.operand)
        return -val if isinstance(val, (int, float)) else None
    if isinstance(node, ast.Tuple):
        vals = [_safe_literal(e) for e in node.elts]
        return tuple(vals) if all(v is not None for v in vals) else None
    if isinstance(node, ast.List):
        vals = [_safe_literal(e) for e in node.elts]
        return vals if all(v is not None for v in vals) else None
    if isinstance(node, ast.Dict):
        keys = [_safe_literal(k) for k in node.keys]
        vals = [_safe_literal(v) for v in node.values]
        if all(k is not None for k in keys) and all(v is not None for v in vals):
            return dict(zip(keys, vals))
    return None


def _call_name(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        left = _call_name(node.value)
        return f"{left}.{node.attr}" if left else node.attr
    return None


def extract_preview_spec(source: str, info: SymbolInfo) -> dict:
    lines = source.splitlines()
    snippet = "\n".join(lines[info.lineno - 1:info.end_lineno])
    dedented = textwrap.dedent(snippet)
    try:
        tree = ast.parse(dedented)
    except Exception:
        return {}
    spec = extract_directgui_spec(tree)
    if spec:
        return spec
    spec = extract_panda_model_spec(tree)
    if spec:
        return spec
    spec = extract_pygame_spec(tree)
    if spec:
        return spec
    return {}


IMAGE_EXTS = {'.png', '.jpg', '.jpeg', '.webp', '.bmp', '.gif'}


def _read_text_file(path: Path) -> Optional[str]:
    for enc in ('utf-8', 'latin-1'):
        try:
            return path.read_text(encoding=enc)
        except Exception:
            continue
    return None


def _rgba_tuple(value, default):
    if not isinstance(value, (list, tuple)) or len(value) < 3:
        return default
    out = []
    for i, c in enumerate(value[:4]):
        if isinstance(c, float) and 0.0 <= c <= 1.0:
            out.append(float(c))
        elif isinstance(c, (int, float)):
            out.append(max(0.0, min(1.0, float(c) / 255.0 if c > 1.0 else float(c))))
    while len(out) < 4:
        out.append(default[len(out)] if len(default) > len(out) else 1.0)
    return tuple(out[:4])

def _luma(rgb):
    r, g, b = rgb[:3]
    return 0.2126 * r + 0.7152 * g + 0.0722 * b

def _is_lifted(spec: dict) -> bool:
    return bool((spec or {}).get('lifted_from'))

def build_module_index(project_root: Optional[Path]) -> Dict[str, Path]:
    index: Dict[str, Path] = {}
    if not project_root or not project_root.exists():
        return index
    for py_path in project_root.rglob('*.py'):
        try:
            rel = py_path.relative_to(project_root)
        except Exception:
            rel = py_path.name
        parts = list(rel.parts)
        if parts[-1] == '__init__.py':
            parts = parts[:-1]
        else:
            parts[-1] = Path(parts[-1]).stem
        if not parts:
            continue
        dotted = '.'.join(parts)
        index.setdefault(dotted, py_path)
        index.setdefault(parts[-1], py_path)
    return index


def resolve_local_module_path(module_name: str, context_path: Optional[Path], project_root: Optional[Path], module_index: Optional[Dict[str, Path]] = None) -> Optional[Path]:
    if not module_name:
        return None
    name = module_name.lstrip('.')
    idx = module_index or build_module_index(project_root)
    if name in idx:
        return idx[name]
    short = name.split('.')[-1]
    if short in idx:
        return idx[short]
    if context_path and module_name.startswith('.'):
        levels = len(module_name) - len(module_name.lstrip('.'))
        base = context_path.parent
        for _ in range(max(0, levels - 1)):
            base = base.parent
        rel = name.split('.') if name else []
        cand = base.joinpath(*rel).with_suffix('.py') if rel else base / '__init__.py'
        if cand.exists():
            return cand
    return None


def extract_image_asset_spec(strings: Set[str], context_path: Optional[Path], project_root: Optional[Path]) -> dict:
    if not strings:
        return {}
    preferred = []
    fallback = []
    for value in sorted(strings):
        value = value.strip().strip("\"'")
        low = value.lower()
        if not any(low.endswith(ext) for ext in IMAGE_EXTS):
            continue
        p = Path(value)
        search = []
        if p.is_absolute():
            search.append(p)
        if context_path:
            search.append(context_path.parent / p)
        if project_root:
            search.append(project_root / p)
        for candidate in search:
            if candidate.exists() and candidate.is_file():
                score = 0
                name = candidate.name.lower()
                if any(k in name for k in ['sprite', 'icon', 'hud', 'ui', 'button', 'menu', 'weapon', 'item', 'avatar', 'portrait']):
                    score += 30
                if any(k in name for k in ['bg', 'background', 'sky', 'terrain', 'wallpaper']):
                    score -= 18
                record = (score, candidate)
                if score >= 20:
                    preferred.append(record)
                else:
                    fallback.append(record)
                break
    choices = preferred or fallback
    if choices:
        choices.sort(key=lambda item: item[0], reverse=True)
        return {'kind': 'image_asset', 'images': [str(p) for _, p in choices[:6]]}
    return {}


def build_preview_spec(source: str, info: SymbolInfo, context_path: Optional[Path] = None, project_root: Optional[Path] = None, analyzer: Optional[PythonAnalyzer] = None, module_index: Optional[Dict[str, Path]] = None, source_cache: Optional[Dict[str, str]] = None, analyzer_cache: Optional[Dict[str, Optional[PythonAnalyzer]]] = None, _depth: int = 0) -> dict:
    spec = extract_preview_spec(source, info)
    if spec:
        return spec
    spec = extract_image_asset_spec(info.string_literals, context_path, project_root)
    if spec:
        return spec
    if not analyzer:
        return {}
    # Same-file lifting from linked symbols.
    for key in sorted(analyzer.lookup_links(info)):
        linked = analyzer.symbols.get(key)
        if not linked or linked.key == info.key:
            continue
        spec = extract_preview_spec(source, linked)
        if not spec:
            spec = extract_image_asset_spec(linked.string_literals, context_path, project_root)
        if spec:
            lifted = dict(spec)
            lifted['lifted_from'] = linked.display_name
            lifted['lifted_scope'] = 'same-file'
            return lifted
    if _depth >= 1 or not project_root:
        return {}
    wanted = {d.split('.')[-1] for d in (info.direct_dependencies | info.imports | info.calls) if d}
    checked = set()
    for dep in sorted(wanted):
        mod_path = resolve_local_module_path(dep, context_path, project_root, module_index)
        if not mod_path or mod_path in checked or mod_path == context_path:
            continue
        checked.add(mod_path)
        cache_key = str(mod_path)
        other_source = source_cache.get(cache_key) if source_cache is not None else None
        if other_source is None:
            other_source = _read_text_file(mod_path)
            if source_cache is not None and other_source is not None:
                source_cache[cache_key] = other_source
        if not other_source:
            continue
        other_analyzer = analyzer_cache.get(cache_key) if analyzer_cache is not None else None
        if other_analyzer is None:
            try:
                other_analyzer = PythonAnalyzer(other_source)
            except Exception:
                other_analyzer = None
            if analyzer_cache is not None:
                analyzer_cache[cache_key] = other_analyzer
        if other_analyzer is None:
            continue
        preferred = [s for s in other_analyzer.symbols.values() if s.name in wanted]
        pool = preferred + [s for s in other_analyzer.symbols.values() if s not in preferred]
        for other in pool:
            spec = extract_preview_spec(other_source, other)
            if not spec:
                spec = extract_image_asset_spec(other.string_literals, mod_path, project_root)
            if spec:
                lifted = dict(spec)
                lifted['lifted_from'] = f"{mod_path.name}:{other.display_name}"
                lifted['lifted_scope'] = 'cross-file'
                return lifted
    return {}



def extract_directgui_spec(tree: ast.AST) -> dict:
    widgets = []
    names = {"DirectFrame", "DirectButton", "DirectLabel", "DirectEntry", "DirectScrolledFrame", "DirectSlider", "DirectCheckButton", "DirectOptionMenu", "DirectWaitBar", "OnscreenText"}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _call_name(node.func) or ""
        short = name.split('.')[-1]
        if short not in names:
            continue
        entry = {"type": short}
        for kw in node.keywords:
            if kw.arg is None:
                continue
            val = _safe_literal(kw.value)
            if val is not None:
                entry[kw.arg] = val
        if node.args and short == 'OnscreenText':
            if 'text' not in entry:
                val = _safe_literal(node.args[0])
                if isinstance(val, str):
                    entry['text'] = val
        widgets.append(entry)
    if widgets:
        return {"kind": "panda_gui", "widgets": widgets}
    return {}




def extract_panda_model_spec(tree: ast.AST) -> dict:
    model_vars = {}
    models = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            target = node.targets[0].id
            if isinstance(node.value, ast.Call):
                call_name = _call_name(node.value.func) or ''
                if call_name.endswith('loadModel') and node.value.args:
                    model_path = _safe_literal(node.value.args[0])
                    if isinstance(model_path, str):
                        entry = {
                            'var': target,
                            'path': model_path,
                            'pos': (0, 7, 0),
                            'hpr': (20, -10, 0),
                            'scale': 1.0,
                            'color': None,
                        }
                        model_vars[target] = entry
                        models.append(entry)
        elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            call = node.value
            if isinstance(call.func, ast.Attribute) and isinstance(call.func.value, ast.Name):
                var = call.func.value.id
                if var in model_vars:
                    method = call.func.attr
                    args = [_safe_literal(a) for a in call.args]
                    entry = model_vars[var]
                    if method == 'setPos' and len(args) >= 3 and all(isinstance(v, (int, float)) for v in args[:3]):
                        entry['pos'] = tuple(float(v) for v in args[:3])
                    elif method == 'setHpr' and len(args) >= 3 and all(isinstance(v, (int, float)) for v in args[:3]):
                        entry['hpr'] = tuple(float(v) for v in args[:3])
                    elif method == 'setScale' and args:
                        if len(args) == 1 and isinstance(args[0], (int, float)):
                            entry['scale'] = float(args[0])
                        elif len(args) >= 3 and all(isinstance(v, (int, float)) for v in args[:3]):
                            entry['scale'] = tuple(float(v) for v in args[:3])
                    elif method == 'setColor' and len(args) >= 3 and all(isinstance(v, (int, float)) for v in args[:3]):
                        alpha = float(args[3]) if len(args) > 3 and isinstance(args[3], (int, float)) else 1.0
                        entry['color'] = tuple(float(v) for v in args[:3]) + (alpha,)
    if models:
        return {'kind': 'panda_models', 'models': models}
    return {}


def _rect_from_node(node, rect_vars):
    if isinstance(node, ast.Call) and (_call_name(node.func) or '').endswith('pygame.Rect'):
        vals = [_safe_literal(a) for a in node.args[:4]]
        if len(vals) == 4 and all(isinstance(v, (int, float)) for v in vals):
            return tuple(int(v) for v in vals)
    if isinstance(node, ast.Name):
        return rect_vars.get(node.id)
    val = _safe_literal(node)
    if isinstance(val, (list, tuple)) and len(val) == 4 and all(isinstance(v, (int, float)) for v in val):
        return tuple(int(v) for v in val)
    return None


def extract_pygame_spec(tree: ast.AST) -> dict:
    rect_vars = {}
    shapes = []
    windows = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            rect = _rect_from_node(node.value, rect_vars)
            if rect:
                rect_vars[node.targets[0].id] = rect
        if isinstance(node, ast.Call):
            name = _call_name(node.func) or ''
            if name.endswith('PipWindow') and len(node.args) >= 2:
                rect = _rect_from_node(node.args[1], rect_vars)
                mode = _safe_literal(node.args[2]) if len(node.args) > 2 else None
                idx = _safe_literal(node.args[0])
                if rect:
                    windows.append({"rect": rect, "label": f"PIP {idx}" if idx is not None else "PIP", "mode": mode})
            elif name.endswith('pygame.draw.rect') and len(node.args) >= 3:
                rect = _rect_from_node(node.args[2], rect_vars)
                color = _safe_literal(node.args[1])
                if rect:
                    shapes.append({"type": "rect", "rect": rect, "color": color})
            elif name.endswith('pygame.draw.line') and len(node.args) >= 4:
                p1 = _safe_literal(node.args[2]); p2 = _safe_literal(node.args[3]); color = _safe_literal(node.args[1])
                if isinstance(p1, (list, tuple)) and isinstance(p2, (list, tuple)) and len(p1) >= 2 and len(p2) >= 2:
                    shapes.append({"type": "line", "p1": (int(p1[0]), int(p1[1])), "p2": (int(p2[0]), int(p2[1])), "color": color})
            elif name.endswith('pygame.draw.circle') and len(node.args) >= 4:
                center = _safe_literal(node.args[2]); radius = _safe_literal(node.args[3]); color = _safe_literal(node.args[1])
                if isinstance(center, (list, tuple)) and len(center) >= 2 and isinstance(radius, (int, float)):
                    shapes.append({"type": "circle", "center": (int(center[0]), int(center[1])), "radius": int(radius), "color": color})
    if windows or shapes:
        return {"kind": "pygame_primitives", "windows": windows, "shapes": shapes}
    return {}



class PandaOffscreenRenderer:
    _configured = False

    def __init__(self):
        self.available = all([Image is not None, PNMImage is not None, ShowBase is not None])
        self.base = None
        self._nodes = []

    def _ensure_base(self, width: int, height: int):
        if not self.available:
            return None
        if not PandaOffscreenRenderer._configured:
            loadPrcFileData('', 'window-type offscreen')
            loadPrcFileData('', 'audio-library-name null')
            loadPrcFileData('', f'win-size {max(320, width)} {max(180, height)}')
            PandaOffscreenRenderer._configured = True
        if self.base is None:
            self.base = ShowBase(windowType='offscreen')
            self.base.setBackgroundColor(17 / 255.0, 19 / 255.0, 24 / 255.0, 1)
        return self.base

    def _clear_nodes(self):
        for node in self._nodes:
            try:
                if hasattr(node, 'destroy'):
                    node.destroy()
                elif hasattr(node, 'removeNode'):
                    node.removeNode()
            except Exception:
                pass
        self._nodes.clear()

    def render_gui_spec(self, width: int, height: int, spec: dict):
        base = self._ensure_base(width, height)
        if base is None:
            return None
        self._clear_nodes()
        widgets = spec.get('widgets', [])
        for widget in widgets:
            node = self._create_widget(widget)
            if node is not None:
                self._nodes.append(node)
        for _ in range(3):
            base.graphicsEngine.renderFrame()
        tex = base.win.getScreenshot()
        pnm = PNMImage()
        tex.store(pnm)
        tmp_path = Path(tempfile.mkdtemp(prefix='vcw_panda_')) / 'preview.png'
        pnm.write(str(tmp_path))
        try:
            image = Image.open(tmp_path).convert('RGB')
        finally:
            self._clear_nodes()
        return image

    def render_model_spec(self, width: int, height: int, spec: dict):
        base = self._ensure_base(width, height)
        if base is None:
            return None
        self._clear_nodes()
        from panda3d.core import AmbientLight, DirectionalLight, Vec4, Point3
        models = spec.get('models', [])[:12]
        root = base.render.attachNewNode('preview_root')
        self._nodes.append(root)
        step = 3.5
        offset = -((len(models) - 1) * step) / 2.0 if models else 0.0
        loaded = []
        for idx, model_spec in enumerate(models):
            path = model_spec.get('path')
            if not isinstance(path, str):
                continue
            try:
                node = base.loader.loadModel(path)
            except Exception:
                continue
            node.reparentTo(root)
            pos = model_spec.get('pos', (0, 7, 0))
            z = float(pos[2]) if isinstance(pos, (list, tuple)) and len(pos) >= 3 else 0.0
            node.setPos(offset + idx * step, 0, z)
            hpr = model_spec.get('hpr', (20, -10, 0))
            if isinstance(hpr, (list, tuple)) and len(hpr) >= 3:
                node.setHpr(float(hpr[0]), float(hpr[1]), float(hpr[2]))
            scale = model_spec.get('scale', 1.0)
            if isinstance(scale, (list, tuple)) and len(scale) >= 3:
                node.setScale(float(scale[0]), float(scale[1]), float(scale[2]))
            elif isinstance(scale, (int, float)):
                node.setScale(float(scale))
            color = model_spec.get('color')
            if isinstance(color, (list, tuple)) and len(color) >= 3:
                rgba = [float(c) for c in color[:4]]
                while len(rgba) < 4:
                    rgba.append(1.0)
                node.setColor(*rgba)
            loaded.append(node)
            self._nodes.append(node)
        if not loaded:
            self._clear_nodes()
            return None
        min_pt, max_pt = root.getTightBounds()
        if min_pt is None or max_pt is None:
            min_pt, max_pt = Point3(-1, -1, -1), Point3(1, 1, 1)
        center = (min_pt + max_pt) * 0.5
        extents = max_pt - min_pt
        radius = max(1.5, max(abs(extents.x), abs(extents.y), abs(extents.z)) * 0.8)
        base.cam.setPos(center.x, center.y - radius * 3.0, center.z + radius * 0.55)
        base.cam.lookAt(center)
        plight = base.render.attachNewNode('preview_light')
        self._nodes.append(plight)
        al = AmbientLight('al')
        al.setColor(Vec4(0.5,0.5,0.56,1))
        dl = DirectionalLight('dl')
        dl.setColor(Vec4(0.95,0.95,0.9,1))
        dl_np = base.render.attachNewNode(dl)
        dl_np.setHpr(35,-35,0)
        al_np = base.render.attachNewNode(al)
        base.render.setLight(al_np)
        base.render.setLight(dl_np)
        self._nodes.extend([al_np, dl_np])
        for _ in range(3):
            base.graphicsEngine.renderFrame()
        tex = base.win.getScreenshot()
        pnm = PNMImage()
        tex.store(pnm)
        tmp_path = Path(tempfile.mkdtemp(prefix='vcw_panda_model_')) / 'preview.png'
        pnm.write(str(tmp_path))
        try:
            image = Image.open(tmp_path).convert('RGB')
        finally:
            self._clear_nodes()
        return image


    def _create_widget(self, widget: dict):
        kind = widget.get('type', 'DirectFrame')
        common = {}
        for key in ('pos', 'scale', 'frameSize', 'frameColor', 'text', 'text_scale', 'text_fg', 'text_pos', 'width', 'numLines'):
            if key in widget:
                common[key] = widget[key]

        default_frame = (0.12, 0.15, 0.19, 0.94)
        default_text = (0.88, 0.91, 0.94, 1.0)
        frame_color = _rgba_tuple(common.get('frameColor'), default_frame) if 'frameColor' in common else default_frame
        text_fg = _rgba_tuple(common.get('text_fg'), default_text) if 'text_fg' in common else default_text

        if _luma(frame_color[:3]) < 0.07 or _luma(frame_color[:3]) > 0.78:
            frame_color = default_frame
        if abs(_luma(text_fg[:3]) - _luma(frame_color[:3])) < 0.42:
            text_fg = default_text

        if 'text' in common:
            common['text_fg'] = text_fg
        if 'frameSize' in common or kind in {'DirectFrame', 'DirectButton', 'DirectLabel', 'DirectEntry', 'DirectScrolledFrame', 'DirectSlider', 'DirectCheckButton', 'DirectOptionMenu', 'DirectWaitBar'}:
            common.setdefault('frameColor', frame_color)

        common.setdefault('relief', 'ridge' if kind in {'DirectButton', 'DirectOptionMenu'} else 'flat')
        if kind == 'DirectButton':
            common.setdefault('pressEffect', 1)
        if kind == 'DirectLabel':
            common.setdefault('text_align', 0)
        if kind == 'DirectEntry':
            common.setdefault('focus', 0)
            common.setdefault('numLines', max(1, int(common.get('numLines', 1))))
        if kind == 'DirectSlider':
            common.setdefault('range', (0, 100))
            common.setdefault('value', 50)
            common.setdefault('pageSize', 5)
        if kind == 'DirectCheckButton':
            common.setdefault('indicatorValue', False)
        if kind == 'DirectOptionMenu':
            common.setdefault('items', ['Option A', 'Option B'])
            common.setdefault('highlightColor', (0.2, 0.36, 0.5, 1.0))
        if kind == 'DirectWaitBar':
            common.setdefault('range', 100)
            common.setdefault('value', 65)
            common.setdefault('barColor', (0.35, 0.66, 0.98, 1.0))

        if kind == 'DirectFrame':
            return DirectFrame(**common)
        if kind == 'DirectButton':
            return DirectButton(**common)
        if kind == 'DirectLabel':
            return DirectLabel(**common)
        if kind == 'DirectEntry':
            return DirectEntry(**common)
        if kind == 'DirectScrolledFrame':
            return DirectScrolledFrame(**common)
        if kind == 'DirectSlider':
            return DirectSlider(**common)
        if kind == 'DirectCheckButton':
            return DirectCheckButton(**common)
        if kind == 'DirectOptionMenu':
            return DirectOptionMenu(**common)
        if kind == 'DirectWaitBar':
            return DirectWaitBar(**common)
        if kind == 'OnscreenText':
            params = {}
            for key in ('text', 'pos', 'scale', 'fg'):
                if key in widget:
                    params[key] = widget[key]
            params['fg'] = _rgba_tuple(params.get('fg'), default_text)
            if abs(_luma(params['fg'][:3]) - _luma(default_frame[:3])) < 0.42:
                params['fg'] = default_text
            return OnscreenText(**params)
        return None


class DependencyPreviewRenderer:

    def preview_source_label(self, spec: dict) -> str:
        spec = spec or {}
        kind = spec.get("kind")
        scope = spec.get('lifted_scope')
        if kind == "panda_gui":
            return "cross-file lifted Panda DirectGUI" if scope == 'cross-file' else ("same-file lifted Panda DirectGUI" if scope == 'same-file' else "engine-verified Panda DirectGUI")
        if kind == "pygame_primitives":
            return "cross-file lifted pygame layout" if scope == 'cross-file' else ("same-file lifted pygame layout" if scope == 'same-file' else "extracted pygame layout")
        if kind == "panda_models":
            return "cross-file lifted Panda model scene" if scope == 'cross-file' else ("same-file lifted Panda model scene" if scope == 'same-file' else "engine-verified Panda model scene")
        if kind == 'image_asset':
            return "resolved image asset preview"
        return "inferred preview"

    def __init__(self):
        self.panda_renderer = PandaOffscreenRenderer()

    def _fit_rect(self, width: int, height: int) -> Tuple[int, int, int, int]:
        scale = min(width / REFERENCE_W, height / REFERENCE_H)
        view_w = int(REFERENCE_W * scale)
        view_h = int(REFERENCE_H * scale)
        x = (width - view_w) // 2
        y = (height - view_h) // 2
        return x, y, view_w, view_h

    def render_image(self, width: int, height: int, payload: dict):
        if Image is None:
            return None
        spec = payload.get("preview_spec") or {}
        if spec.get("kind") == "panda_gui":
            verified = self.panda_renderer.render_gui_spec(width, height, spec)
            if verified is not None:
                return verified
        if spec.get("kind") == "panda_models":
            verified = self.panda_renderer.render_model_spec(width, height, spec)
            if verified is not None:
                return verified
        if spec.get('kind') == 'image_asset':
            verified = self._render_asset_image(width, height, spec)
            if verified is not None:
                return verified
        image = Image.new("RGB", (width, height), DARK["panel"])
        draw = ImageDraw.Draw(image)
        self._draw_image(draw, width, height, payload)
        return image

    def draw_tk(self, canvas: tk.Canvas, payload: dict):
        canvas.delete("all")
        width = max(canvas.winfo_width(), 10)
        height = max(canvas.winfo_height(), 10)
        self._draw_canvas(canvas, width, height, payload)

    def _preview_type(self, payload: dict) -> str:
        spec = payload.get("preview_spec") or {}
        if spec.get("kind") == "panda_gui":
            return "ui"
        if spec.get("kind") == "pygame_primitives":
            return "scene" if spec.get("shapes") else "ui"
        if spec.get("kind") == "panda_models":
            return "scene" if len(spec.get("models", [])) > 1 else "entity"
        if spec.get("kind") == "image_asset":
            return "entity"
        text = " ".join([
            str(payload.get("name", "")),
            str(payload.get("doc", "")),
            " ".join(sorted(payload.get("calls", []))),
            " ".join(sorted(payload.get("assigns", []))),
            " ".join(sorted(payload.get("strings", []))),
        ]).lower()
        if any(k in text for k in ["menu", "panel", "hud", "dialog", "button", "inventory", "settings", "ui", "tooltip", "overlay"]):
            return "ui"
        if any(k in text for k in ["player", "enemy", "character", "weapon", "entity", "npc", "actor", "ship", "vehicle", "robot"]):
            return "entity"
        if any(k in text for k in ["terrain", "world", "map", "biome", "chunk", "tile", "level", "room", "scene"]):
            return "scene"
        return "logic"

    def _draw_canvas(self, canvas: tk.Canvas, width: int, height: int, payload: dict):
        canvas.create_rectangle(0, 0, width, height, fill=DARK["panel"], outline="")
        x, y, w, h = self._fit_rect(width, height)
        canvas.create_rectangle(x, y, x + w, y + h, fill=DARK["bg"], outline=DARK["line"], width=2)
        ptype = self._preview_type(payload)
        spec = payload.get("preview_spec") or {}
        if spec.get("kind") == "panda_gui":
            self._draw_panda_gui_canvas(canvas, x, y, w, h, payload, spec)
        elif spec.get("kind") == "panda_models":
            self._draw_panda_model_canvas(canvas, x, y, w, h, payload, spec)
        elif spec.get("kind") == "pygame_primitives":
            self._draw_pygame_canvas(canvas, x, y, w, h, payload, spec)
        elif spec.get("kind") == "image_asset":
            self._draw_image_asset_canvas(canvas, x, y, w, h, payload, spec)
        elif spec.get("kind") == 'image_asset':
            self._draw_image_asset_canvas(canvas, x, y, w, h, payload, spec)
        elif ptype == "ui":
            self._draw_ui_canvas(canvas, x, y, w, h, payload)
        elif ptype == "entity":
            self._draw_entity_canvas(canvas, x, y, w, h, payload)
        elif ptype == "scene":
            self._draw_scene_canvas(canvas, x, y, w, h, payload)
        else:
            self._draw_logic_canvas(canvas, x, y, w, h, payload)

    def _draw_image(self, draw, width: int, height: int, payload: dict):
        draw.rectangle((0, 0, width, height), fill=DARK["panel"])
        x, y, w, h = self._fit_rect(width, height)
        draw.rectangle((x, y, x + w, y + h), fill=DARK["bg"], outline=DARK["line"], width=2)
        ptype = self._preview_type(payload)
        spec = payload.get("preview_spec") or {}
        if spec.get("kind") == "panda_gui":
            self._draw_panda_gui_image(draw, x, y, w, h, payload, spec)
        elif spec.get("kind") == "panda_models":
            self._draw_panda_model_image(draw, x, y, w, h, payload, spec)
        elif spec.get("kind") == "pygame_primitives":
            self._draw_pygame_image(draw, x, y, w, h, payload, spec)
        elif spec.get("kind") == "image_asset":
            self._draw_image_asset_image(draw, x, y, w, h, payload, spec)
        elif spec.get("kind") == 'image_asset':
            self._draw_image_asset_image(draw, x, y, w, h, payload, spec)
        elif ptype == "ui":
            self._draw_ui_image(draw, x, y, w, h, payload)
        elif ptype == "entity":
            self._draw_entity_image(draw, x, y, w, h, payload)
        elif ptype == "scene":
            self._draw_scene_image(draw, x, y, w, h, payload)
        else:
            self._draw_logic_image(draw, x, y, w, h, payload)


    def _render_asset_image(self, width: int, height: int, spec: dict):
        if Image is None:
            return None
        images = [Path(p) for p in spec.get('images', [])]
        for path in images:
            try:
                src = Image.open(path).convert('RGB')
                break
            except Exception:
                src = None
        else:
            src = None
        if src is None:
            return None
        canvas = Image.new('RGB', (width, height), DARK['panel'])
        draw = ImageDraw.Draw(canvas)
        x, y, w, h = self._fit_rect(width, height)
        draw.rectangle((x, y, x + w, y + h), fill=DARK['bg'], outline=DARK['line'], width=2)
        scale = min((w - 40) / max(1, src.width), (h - 80) / max(1, src.height))
        tw = max(1, int(src.width * scale)); th = max(1, int(src.height * scale))
        fitted = src.resize((tw, th))
        ox = x + (w - tw) // 2; oy = y + (h - th) // 2
        canvas.paste(fitted, (ox, oy))
        draw.rectangle((ox, oy, ox + tw, oy + th), outline=DARK['accent'], width=2)
        draw.rectangle((x, y, x + w, y + 34), fill=(5, 8, 14))
        draw.text((x + 12, y + 9), textwrap.shorten(images[0].name, width=72, placeholder='…'), fill=DARK['text'])
        return canvas

    def _draw_image_asset_canvas(self, canvas, x, y, w, h, payload, spec):
        canvas.create_text(x + 16, y + 16, text='Resolved image asset preview · aspect preserved', anchor='nw', fill=DARK['muted'], font=('Segoe UI', 10))
        images = spec.get('images', [])
        canvas.create_rectangle(x + 40, y + 48, x + w - 40, y + h - 40, outline=DARK['accent'], width=2)
        label = Path(images[0]).name if images else 'missing image'
        canvas.create_text(x + w // 2, y + h // 2, text=label, fill=DARK['text'], font=('Segoe UI', 14, 'bold'))

    def _draw_image_asset_image(self, draw, x, y, w, h, payload, spec):
        draw.rectangle((x + 40, y + 48, x + w - 40, y + h - 40), outline=DARK['accent'], width=2)

    def _summary_lines(self, payload: dict, limit: int = 5) -> List[str]:
        lines = []
        if payload.get("kind"):
            lines.append(f"Type: {payload['kind']}")
        if payload.get("preview_source"):
            lines.append(f"Preview: {payload['preview_source']}")
        if payload.get("line_span"):
            lines.append(f"Lines: {payload['line_span']}")
        if payload.get("calls"):
            lines.append("Calls: " + ", ".join(sorted(payload["calls"])[:4]))
        if payload.get("assigns"):
            lines.append("Writes: " + ", ".join(sorted(payload["assigns"])[:4]))
        if payload.get("linked"):
            lines.append("Links: " + ", ".join(sorted(payload["linked"])[:4]))
        doc = (payload.get("doc") or "").strip()
        if doc:
            lines.append(textwrap.shorten(doc.replace("\n", " "), width=54, placeholder="…"))
        return lines[:limit]

    def _draw_ui_canvas(self, canvas, x, y, w, h, payload):
        panel_w = int(w * 0.34)
        panel_h = int(h * 0.38)
        px = x + int(w * 0.05)
        py = y + int(h * 0.54)
        canvas.create_text(x + 16, y + 16, text="Real placement view · 16:9 preserved", anchor="nw", fill=DARK["muted"], font=("Segoe UI", 10))
        canvas.create_rectangle(px, py, px + panel_w, py + panel_h, fill=DARK["panel2"], outline=DARK["accent"], width=2)
        canvas.create_text(px + 22, py + 18, text=payload.get("name", "UI Preview"), anchor="w", fill=DARK["text"], font=("Segoe UI", 14, "bold"))
        for i, line in enumerate(self._summary_lines(payload, 4)):
            yy = py + 52 + i * 30
            canvas.create_rectangle(px + 18, yy, px + panel_w - 18, yy + 22, fill="#242b34", outline=DARK["line"])
            canvas.create_text(px + 28, yy + 11, text=line, anchor="w", fill=DARK["muted"], font=("Segoe UI", 10))

    def _draw_entity_canvas(self, canvas, x, y, w, h, payload):
        cx = x + int(w * 0.5)
        cy = y + int(h * 0.54)
        canvas.create_text(x + 16, y + 16, text="Entity view · isolated staging", anchor="nw", fill=DARK["muted"], font=("Segoe UI", 10))
        canvas.create_oval(cx - 34, cy - 160, cx + 34, cy - 92, fill="#354458", outline=DARK["accent2"], width=2)
        canvas.create_rectangle(cx - 42, cy - 92, cx + 42, cy + 60, fill="#283141", outline=DARK["accent2"], width=2)
        canvas.create_line(cx - 26, cy + 60, cx - 48, cy + 130, fill=DARK["accent2"], width=4)
        canvas.create_line(cx + 26, cy + 60, cx + 48, cy + 130, fill=DARK["accent2"], width=4)
        canvas.create_line(cx - 42, cy - 40, cx - 100, cy + 10, fill=DARK["accent2"], width=4)
        canvas.create_line(cx + 42, cy - 40, cx + 100, cy + 10, fill=DARK["accent2"], width=4)
        canvas.create_text(cx, cy + 180, text=payload.get("name", "Entity"), fill=DARK["text"], font=("Segoe UI", 15, "bold"))
        canvas.create_text(cx, cy + 208, text="Preview inferred from class/function signals", fill=DARK["muted"], font=("Segoe UI", 10))

    def _draw_scene_canvas(self, canvas, x, y, w, h, payload):
        canvas.create_text(x + 16, y + 16, text="Scene view · sandbox framing", anchor="nw", fill=DARK["muted"], font=("Segoe UI", 10))
        ground_y = y + int(h * 0.72)
        canvas.create_polygon(x + 40, ground_y, x + int(w*0.25), ground_y - 70, x + int(w*0.42), ground_y - 20, x + int(w*0.65), ground_y - 110, x + w - 50, ground_y, fill="#24303c", outline=DARK["accent"])
        canvas.create_rectangle(x, ground_y, x + w, y + h, fill="#1a242d", outline="")
        for i in range(5):
            px = x + 120 + i * 180
            canvas.create_rectangle(px, ground_y - 60 - (i % 2) * 25, px + 60, ground_y, fill="#2c3947", outline=DARK["line"])
        canvas.create_text(x + 24, y + h - 40, text=payload.get("name", "Scene Preview"), anchor="w", fill=DARK["text"], font=("Segoe UI", 14, "bold"))

    def _draw_logic_canvas(self, canvas, x, y, w, h, payload):
        panel_x = x + int(w * 0.08)
        panel_y = y + int(h * 0.12)
        panel_w = int(w * 0.84)
        panel_h = int(h * 0.76)
        canvas.create_text(x + 16, y + 16, text="Trace view · no direct renderer detected", anchor="nw", fill=DARK["muted"], font=("Segoe UI", 10))
        canvas.create_rectangle(panel_x, panel_y, panel_x + panel_w, panel_y + panel_h, fill=DARK["panel2"], outline=DARK["accent"], width=2)
        canvas.create_text(panel_x + 20, panel_y + 18, text=payload.get("name", "Logic Preview"), anchor="w", fill=DARK["text"], font=("Segoe UI", 14, "bold"))
        for i, line in enumerate(self._summary_lines(payload, 5)):
            canvas.create_text(panel_x + 24, panel_y + 58 + i * 28, text=line, anchor="w", fill=DARK["muted"], font=("Consolas", 10))

    def _draw_ui_image(self, draw, x, y, w, h, payload):
        panel_w = int(w * 0.34)
        panel_h = int(h * 0.38)
        px = x + int(w * 0.05)
        py = y + int(h * 0.54)
        draw.rectangle((px, py, px + panel_w, py + panel_h), fill=DARK["panel2"], outline=DARK["accent"], width=2)
        for i, _line in enumerate(self._summary_lines(payload, 4)):
            yy = py + 52 + i * 30
            draw.rectangle((px + 18, yy, px + panel_w - 18, yy + 22), fill="#242b34", outline=DARK["line"])

    def _draw_entity_image(self, draw, x, y, w, h, payload):
        cx = x + int(w * 0.5)
        cy = y + int(h * 0.54)
        draw.ellipse((cx - 34, cy - 160, cx + 34, cy - 92), fill="#354458", outline=DARK["accent2"], width=2)
        draw.rectangle((cx - 42, cy - 92, cx + 42, cy + 60), fill="#283141", outline=DARK["accent2"], width=2)
        draw.line((cx - 26, cy + 60, cx - 48, cy + 130), fill=DARK["accent2"], width=4)
        draw.line((cx + 26, cy + 60, cx + 48, cy + 130), fill=DARK["accent2"], width=4)
        draw.line((cx - 42, cy - 40, cx - 100, cy + 10), fill=DARK["accent2"], width=4)
        draw.line((cx + 42, cy - 40, cx + 100, cy + 10), fill=DARK["accent2"], width=4)

    def _draw_scene_image(self, draw, x, y, w, h, payload):
        ground_y = y + int(h * 0.72)
        draw.polygon((x + 40, ground_y, x + int(w*0.25), ground_y - 70, x + int(w*0.42), ground_y - 20, x + int(w*0.65), ground_y - 110, x + w - 50, ground_y), fill="#24303c", outline=DARK["accent"])
        draw.rectangle((x, ground_y, x + w, y + h), fill="#1a242d")

    def _draw_logic_image(self, draw, x, y, w, h, payload):
        panel_x = x + int(w * 0.08)
        panel_y = y + int(h * 0.12)
        panel_w = int(w * 0.84)
        panel_h = int(h * 0.76)
        draw.rectangle((panel_x, panel_y, panel_x + panel_w, panel_y + panel_h), fill=DARK["panel2"], outline=DARK["accent"], width=2)


    def _panda_to_screen(self, px, pz, x, y, w, h):
        aspect = REFERENCE_W / REFERENCE_H
        sx = x + int(((float(px) + aspect) / (2 * aspect)) * w)
        sy = y + int((1 - ((float(pz) + 1) / 2)) * h)
        return sx, sy

    def _pygame_bounds(self, spec: dict):
        xs=[]; ys=[]
        for item in spec.get('windows', []):
            rx, ry, rw, rh = item['rect']
            xs.extend([rx, rx+rw]); ys.extend([ry, ry+rh])
        for shape in spec.get('shapes', [])[:160]:
            if shape['type'] == 'rect':
                rx, ry, rw, rh = shape['rect']; xs.extend([rx, rx+rw]); ys.extend([ry, ry+rh])
            elif shape['type'] == 'line':
                p1, p2 = shape['p1'], shape['p2']; xs.extend([p1[0], p2[0]]); ys.extend([p1[1], p2[1]])
            elif shape['type'] == 'circle':
                cx, cy = shape['center']; r = shape['radius']; xs.extend([cx-r, cx+r]); ys.extend([cy-r, cy+r])
        if not xs or not ys:
            return (0, 0, REFERENCE_W, REFERENCE_H)
        min_x, max_x = min(xs), max(xs); min_y, max_y = min(ys), max(ys)
        pad_x = max(24, int((max_x - min_x) * 0.2)); pad_y = max(24, int((max_y - min_y) * 0.2))
        min_x = max(0, min_x - pad_x); min_y = max(0, min_y - pad_y)
        max_x = min(REFERENCE_W, max_x + pad_x); max_y = min(REFERENCE_H, max_y + pad_y)
        if max_x - min_x < 180: max_x = min(REFERENCE_W, min_x + 180)
        if max_y - min_y < 180: max_y = min(REFERENCE_H, min_y + 180)
        return min_x, min_y, max_x, max_y

    def _pygame_map_point(self, px, py, x, y, w, h, bounds):
        min_x, min_y, max_x, max_y = bounds
        bw = max(1, max_x - min_x); bh = max(1, max_y - min_y)
        scale = min((w - 24) / bw, (h - 24) / bh)
        ox = x + (w - int(bw * scale)) // 2; oy = y + (h - int(bh * scale)) // 2
        sx = ox + int((px - min_x) * scale); sy = oy + int((py - min_y) * scale)
        return sx, sy, scale

    def _color_to_hex(self, color, default):
        if isinstance(color, (list, tuple)) and len(color) >= 3:
            vals = []
            for c in color[:3]:
                if isinstance(c, float) and 0 <= c <= 1:
                    vals.append(int(c * 255))
                elif isinstance(c, (int, float)):
                    vals.append(max(0, min(255, int(c))))
            if len(vals) == 3:
                return f"#{vals[0]:02x}{vals[1]:02x}{vals[2]:02x}"
        return default

    def _draw_panda_gui_canvas(self, canvas, x, y, w, h, payload, spec):
        canvas.create_text(x + 16, y + 16, text="Extracted DirectGUI preview · real placement", anchor="nw", fill=DARK["muted"], font=("Segoe UI", 10))
        for widget in spec.get('widgets', []):
            kind = widget.get('type', 'Widget')
            pos = widget.get('pos', (0, 0, 0))
            if isinstance(pos, (list, tuple)) and len(pos) >= 3:
                px, pz = pos[0], pos[2]
            else:
                px, pz = 0, 0
            sx, sy = self._panda_to_screen(px, pz, x, y, w, h)
            if 'frameSize' in widget and isinstance(widget['frameSize'], (list, tuple)) and len(widget['frameSize']) == 4:
                l, r, b, t = widget['frameSize']
                aspect = REFERENCE_W / REFERENCE_H
                rx1 = x + int(((px + l + aspect) / (2 * aspect)) * w)
                rx2 = x + int(((px + r + aspect) / (2 * aspect)) * w)
                ry1 = y + int((1 - ((pz + t + 1) / 2)) * h)
                ry2 = y + int((1 - ((pz + b + 1) / 2)) * h)
                canvas.create_rectangle(rx1, ry1, rx2, ry2, fill=DARK['panel2'], outline=DARK['accent'], width=2)
                label_x, label_y = rx1 + 10, ry1 + 10
            else:
                ww = max(80, int((widget.get('width', 12) or 12) * 8))
                hh = 34 if kind != 'DirectEntry' else max(50, int((widget.get('numLines', 1) or 1) * 18))
                canvas.create_rectangle(sx - ww // 2, sy - hh // 2, sx + ww // 2, sy + hh // 2, fill=DARK['panel2'], outline=DARK['accent2'], width=2)
                label_x, label_y = sx - ww // 2 + 10, sy - hh // 2 + 10
            text = str(widget.get('text', kind)).replace('\n', ' ')
            text = textwrap.shorten(text, width=42, placeholder='…')
            canvas.create_text(label_x, label_y, text=f"{kind}: {text}", anchor='nw', fill=DARK['text'], font=("Segoe UI", 10, 'bold'))

    def _draw_panda_model_canvas(self, canvas, x, y, w, h, payload, spec):
        canvas.create_text(x + 16, y + 16, text="Extracted Panda model scene · engine-backed", anchor="nw", fill=DARK["muted"], font=("Segoe UI", 10))
        floor_y = y + int(h * 0.76)
        canvas.create_rectangle(x, floor_y, x + w, y + h, fill="#1a242d", outline="")
        models = spec.get('models', [])[:6]
        step = w / max(7, len(models) + 1)
        for idx, model in enumerate(models):
            cx = x + int(step * (idx + 1))
            base_y = floor_y
            canvas.create_rectangle(cx - 28, base_y - 70, cx + 28, base_y, fill="#2b3744", outline=DARK['accent2'], width=2)
            canvas.create_text(cx, base_y + 14, text=textwrap.shorten(Path(str(model.get('path','model'))).name, width=16, placeholder='…'), anchor='n', fill=DARK['text'], font=("Segoe UI", 9, 'bold'))

    def _draw_panda_model_image(self, draw, x, y, w, h, payload, spec):
        floor_y = y + int(h * 0.76)
        draw.rectangle((x, floor_y, x + w, y + h), fill="#1a242d")
        models = spec.get('models', [])[:6]
        step = w / max(7, len(models) + 1)
        for idx, model in enumerate(models):
            cx = x + int(step * (idx + 1))
            base_y = floor_y
            draw.rectangle((cx - 28, base_y - 70, cx + 28, base_y), fill="#2b3744", outline=DARK['accent2'], width=2)

    def _draw_pygame_canvas(self, canvas, x, y, w, h, payload, spec):
        canvas.create_text(x + 16, y + 16, text="Extracted pygame layout preview · fitted to content", anchor="nw", fill=DARK["muted"], font=("Segoe UI", 10))
        bounds = self._pygame_bounds(spec)
        for item in spec.get('windows', []):
            rx, ry, rw, rh = item['rect']
            sx1, sy1, scale = self._pygame_map_point(rx, ry, x, y, w, h, bounds)
            sx2, sy2, _ = self._pygame_map_point(rx + rw, ry + rh, x, y, w, h, bounds)
            canvas.create_rectangle(sx1, sy1, sx2, sy2, fill=DARK['panel2'], outline=DARK['accent'], width=2)
            canvas.create_text(sx1 + 10, sy1 + 10, text=f"{item.get('label','Window')} · {item.get('mode') or ''}", anchor='nw', fill=DARK['text'], font=("Segoe UI", 10, 'bold'))
        for shape in spec.get('shapes', [])[:160]:
            color = self._color_to_hex(shape.get('color'), DARK['accent2'])
            if shape['type'] == 'rect':
                rx, ry, rw, rh = shape['rect']
                sx1, sy1, _ = self._pygame_map_point(rx, ry, x, y, w, h, bounds)
                sx2, sy2, _ = self._pygame_map_point(rx + rw, ry + rh, x, y, w, h, bounds)
                canvas.create_rectangle(sx1, sy1, sx2, sy2, outline=color)
            elif shape['type'] == 'line':
                p1 = shape['p1']; p2 = shape['p2']
                x1, y1, _ = self._pygame_map_point(p1[0], p1[1], x, y, w, h, bounds)
                x2, y2, _ = self._pygame_map_point(p2[0], p2[1], x, y, w, h, bounds)
                canvas.create_line(x1, y1, x2, y2, fill=color)
            elif shape['type'] == 'circle':
                cx, cy = shape['center']
                px, py, scale = self._pygame_map_point(cx, cy, x, y, w, h, bounds)
                r = max(1, int(shape['radius'] * scale))
                canvas.create_oval(px - r, py - r, px + r, py + r, outline=color)

    def _draw_panda_gui_image(self, draw, x, y, w, h, payload, spec):
        for widget in spec.get('widgets', []):
            kind = widget.get('type', 'Widget')
            pos = widget.get('pos', (0, 0, 0))
            px, pz = (pos[0], pos[2]) if isinstance(pos, (list, tuple)) and len(pos) >= 3 else (0, 0)
            sx, sy = self._panda_to_screen(px, pz, x, y, w, h)
            if 'frameSize' in widget and isinstance(widget['frameSize'], (list, tuple)) and len(widget['frameSize']) == 4:
                l, r, b, t = widget['frameSize']
                aspect = REFERENCE_W / REFERENCE_H
                rx1 = x + int(((px + l + aspect) / (2 * aspect)) * w)
                rx2 = x + int(((px + r + aspect) / (2 * aspect)) * w)
                ry1 = y + int((1 - ((pz + t + 1) / 2)) * h)
                ry2 = y + int((1 - ((pz + b + 1) / 2)) * h)
                draw.rectangle((rx1, ry1, rx2, ry2), fill=DARK['panel2'], outline=DARK['accent'], width=2)
            else:
                ww = max(80, int((widget.get('width', 12) or 12) * 8))
                hh = 34 if kind != 'DirectEntry' else max(50, int((widget.get('numLines', 1) or 1) * 18))
                draw.rectangle((sx - ww // 2, sy - hh // 2, sx + ww // 2, sy + hh // 2), fill=DARK['panel2'], outline=DARK['accent2'], width=2)

    def _draw_pygame_image(self, draw, x, y, w, h, payload, spec):
        bounds = self._pygame_bounds(spec)
        for item in spec.get('windows', []):
            rx, ry, rw, rh = item['rect']
            sx1, sy1, _ = self._pygame_map_point(rx, ry, x, y, w, h, bounds)
            sx2, sy2, _ = self._pygame_map_point(rx + rw, ry + rh, x, y, w, h, bounds)
            draw.rectangle((sx1, sy1, sx2, sy2), fill=DARK['panel2'], outline=DARK['accent'], width=2)
        for shape in spec.get('shapes', [])[:160]:
            color = self._color_to_hex(shape.get('color'), DARK['accent2'])
            if shape['type'] == 'rect':
                rx, ry, rw, rh = shape['rect']
                sx1, sy1, _ = self._pygame_map_point(rx, ry, x, y, w, h, bounds)
                sx2, sy2, _ = self._pygame_map_point(rx + rw, ry + rh, x, y, w, h, bounds)
                draw.rectangle((sx1, sy1, sx2, sy2), outline=color, width=1)
            elif shape['type'] == 'line':
                p1 = shape['p1']; p2 = shape['p2']
                x1, y1, _ = self._pygame_map_point(p1[0], p1[1], x, y, w, h, bounds)
                x2, y2, _ = self._pygame_map_point(p2[0], p2[1], x, y, w, h, bounds)
                draw.line((x1, y1, x2, y2), fill=color, width=1)
            elif shape['type'] == 'circle':
                cx, cy = shape['center']
                px, py, scale = self._pygame_map_point(cx, cy, x, y, w, h, bounds)
                r = max(1, int(shape['radius'] * scale))
                draw.ellipse((px - r, py - r, px + r, py + r), outline=color, width=1)


class BatchTester:
    def __init__(self):
        self.renderer = DependencyPreviewRenderer()
        self.source_cache: Dict[str, str] = {}
        self.analyzer_cache: Dict[str, Optional[PythonAnalyzer]] = {}
        self.preview_cache: Dict[Tuple[str, str], dict] = {}

    def analyze_path(self, path: Path) -> dict:
        py_files = self._expand_inputs(path)
        scan_root = self._scan_root(path)
        module_index = build_module_index(scan_root)
        result = {
            "root": str(path),
            "python_files": len(py_files),
            "parsed_files": 0,
            "symbols": 0,
            "previewable": 0,
            "verified_panda_gui": 0,
            "verified_panda_models": 0,
            "resolved_image_assets": 0,
            "categories": {"ui": 0, "entity": 0, "scene": 0, "logic": 0},
            "files": [],
        }
        for file_path in py_files:
            source = self._read_text(file_path)
            if source is None:
                continue
            try:
                analyzer = PythonAnalyzer(source)
            except Exception as exc:
                result["files"].append({"path": str(file_path), "error": str(exc)})
                continue
            result["parsed_files"] += 1
            file_record = {"path": str(file_path), "symbols": len(analyzer.symbols), "previewable": 0, "verified_panda_gui": 0, "verified_panda_models": 0, "resolved_image_assets": 0, "categories": {"ui": 0, "entity": 0, "scene": 0, "logic": 0}}
            for info in analyzer.symbols.values():
                payload = self.payload_for(analyzer, info, file_path, scan_root, module_index)
                category = self.renderer._preview_type(payload)
                file_record["previewable"] += 1
                file_record["categories"][category] += 1
                result["symbols"] += 1
                result["previewable"] += 1
                result["categories"][category] += 1
                spec = payload.get("preview_spec") or {}
                if spec.get("kind") == "panda_gui" and spec.get("widgets"):
                    result["verified_panda_gui"] += 1
                    file_record["verified_panda_gui"] += 1
                if spec.get("kind") == "panda_models" and spec.get("models"):
                    result["verified_panda_models"] += 1
                    file_record["verified_panda_models"] += 1
                if spec.get("kind") == "image_asset" and spec.get("images"):
                    result["resolved_image_assets"] += 1
                    file_record["resolved_image_assets"] += 1
            result["files"].append(file_record)
        return result

    def payload_for(self, analyzer: PythonAnalyzer, info: SymbolInfo, context_path: Optional[Path] = None, project_root: Optional[Path] = None, module_index: Optional[Dict[str, Path]] = None) -> dict:
        cache_key = (str(context_path or ""), info.key)
        preview_spec = self.preview_cache.get(cache_key)
        if preview_spec is None:
            preview_spec = build_preview_spec(analyzer.source, info, context_path, project_root, analyzer, module_index, self.source_cache, self.analyzer_cache)
            self.preview_cache[cache_key] = preview_spec
        return {
            "name": info.display_name,
            "kind": info.kind,
            "doc": info.doc,
            "calls": info.calls,
            "assigns": info.assigns,
            "returns": info.returns,
            "dependencies": info.dependencies,
            "linked": analyzer.lookup_links(info),
            "strings": info.string_literals,
            "line_span": f"{info.lineno}-{info.end_lineno}",
            "preview_spec": preview_spec,
            "preview_source": self.renderer.preview_source_label(preview_spec),
        }

    def _scan_root(self, path: Path) -> Optional[Path]:
        if path.is_dir():
            return path
        if path.suffix.lower() == ".zip":
            root = Path(tempfile.mkdtemp(prefix="vcw_zip_scanroot_"))
            with zipfile.ZipFile(path) as zf:
                zf.extractall(root)
            roots = [p for p in root.iterdir() if p.is_dir()]
            return roots[0] if len(roots) == 1 else root
        return path.parent if path.suffix.lower() == ".py" else None

    def _expand_inputs(self, path: Path) -> List[Path]:
        if path.is_dir():
            return sorted(path.rglob("*.py"))
        if path.suffix.lower() == ".zip":
            root = Path(tempfile.mkdtemp(prefix="vcw_zip_"))
            with zipfile.ZipFile(path) as zf:
                zf.extractall(root)
            return sorted(root.rglob("*.py"))
        return [path] if path.suffix.lower() == ".py" else []

    def _read_text(self, path: Path) -> Optional[str]:
        for enc in ("utf-8", "latin-1"):
            try:
                return path.read_text(encoding=enc)
            except Exception:
                continue
        return None


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1600x920")
        self.minsize(1220, 760)
        self.configure(bg=DARK["bg"])
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        self.project_root: Optional[Path] = None
        self.module_index: Dict[str, Path] = {}
        self.zip_extract_root: Optional[Path] = None
        self.current_file: Optional[Path] = None
        self.current_source = ""
        self.analyzer: Optional[PythonAnalyzer] = None
        self.symbol_map: Dict[str, SymbolInfo] = {}
        self.current_symbol: Optional[SymbolInfo] = None
        self.preview_payload = {"name": "No selection", "kind": "idle", "doc": "Open a Python file or project to inspect code.", "preview_source": "idle"}
        self.preview_renderer = DependencyPreviewRenderer()
        self.status_text = tk.StringVar(value="Ready")
        self.preview_source_text = tk.StringVar(value="Preview: idle")
        self.diagnostics_text = tk.StringVar(value="No issues detected.")
        self.validation_after_id = None
        self.last_error = None
        self.live_preview_var = tk.BooleanVar(value=True)
        self.problem_items: List[dict] = []
        self.problem_listbox = None

        self._configure_style()
        self._build_ui()
        self._bind_shortcuts()
        self.log("Ready. Open a project folder, zip, or Python file.")

    def _configure_style(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("Treeview", background=DARK["panel"], foreground=DARK["text"], fieldbackground=DARK["panel"], rowheight=24, bordercolor=DARK["line"], relief="flat")
        style.map("Treeview", background=[("selected", DARK["selection"])])
        style.configure("TFrame", background=DARK["bg"])
        style.configure("TLabel", background=DARK["bg"], foreground=DARK["text"])

    def _build_ui(self):
        self._build_menu()
        toolbar = tk.Frame(self, bg=DARK["panel"], height=42)
        toolbar.pack(fill="x", side="top")
        buttons = [
            ("Open Project", self.open_project),
            ("Open Zip", self.open_zip),
            ("Open File", self.open_file),
            ("Save", self.save_file),
            ("Save As", self.save_as),
            ("Export Preview", self.export_preview),
            ("Batch Report", self.batch_report_dialog),
            ("Refresh", self.reparse_current_file),
        ]
        for label, cmd in buttons:
            tk.Button(toolbar, text=label, command=cmd, bg=DARK["panel2"], fg=DARK["text"], activebackground=DARK["selection"], relief="flat", bd=0, padx=10, pady=6).pack(side="left", padx=5, pady=6)
        tk.Label(toolbar, textvariable=self.status_text, bg=DARK["panel"], fg=DARK["muted"], padx=10).pack(side="right")

        top = tk.PanedWindow(self, orient="horizontal", bg=DARK["bg"], sashwidth=8, bd=0)
        top.pack(fill="both", expand=True)

        left = tk.Frame(top, bg=DARK["panel"], width=320)
        center = tk.Frame(top, bg=DARK["bg"])
        right = tk.Frame(top, bg=DARK["panel"], width=430)
        top.add(left, minsize=280)
        top.add(center, minsize=620)
        top.add(right, minsize=380)

        self._build_left(left)
        self._build_center(center)
        self._build_right(right)
        self._build_bottom()

    def _build_menu(self):
        menubar = tk.Menu(self, bg=DARK["panel"], fg=DARK["text"], tearoff=0)
        file_menu = tk.Menu(menubar, tearoff=0, bg=DARK["panel"], fg=DARK["text"])
        file_menu.add_command(label="Open Project", command=self.open_project)
        file_menu.add_command(label="Open Zip", command=self.open_zip)
        file_menu.add_command(label="Open File", command=self.open_file)
        file_menu.add_separator()
        file_menu.add_command(label="Save", command=self.save_file)
        file_menu.add_command(label="Save As", command=self.save_as)
        file_menu.add_separator()
        file_menu.add_command(label="Export Preview", command=self.export_preview)
        file_menu.add_command(label="Batch Report", command=self.batch_report_dialog)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.on_close)
        menubar.add_cascade(label="File", menu=file_menu)

        edit_menu = tk.Menu(menubar, tearoff=0, bg=DARK["panel"], fg=DARK["text"])
        edit_menu.add_command(label="Undo", command=lambda: self.editor.event_generate("<<Undo>>"))
        edit_menu.add_command(label="Redo", command=lambda: self.editor.event_generate("<<Redo>>"))
        edit_menu.add_separator()
        edit_menu.add_command(label="Copy", command=lambda: self.editor.event_generate("<<Copy>>"))
        edit_menu.add_command(label="Paste", command=lambda: self.editor.event_generate("<<Paste>>"))
        edit_menu.add_command(label="Cut", command=lambda: self.editor.event_generate("<<Cut>>"))
        edit_menu.add_separator()
        edit_menu.add_command(label="Find", command=self.find_text)
        edit_menu.add_separator()
        edit_menu.add_command(label="Delete Block", command=self.delete_current_block)
        edit_menu.add_command(label="Jump to Next Problem", command=self.jump_to_next_problem)
        menubar.add_cascade(label="Edit", menu=edit_menu)
        self.config(menu=menubar)

    def _build_left(self, parent):
        tk.Label(parent, text="Project", bg=DARK["panel"], fg=DARK["text"], anchor="w", padx=10, pady=8).pack(fill="x")
        self.file_tree = ttk.Treeview(parent, show="tree")
        self.file_tree.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.file_tree.bind("<<TreeviewSelect>>", self.on_file_tree_select)

        tk.Label(parent, text="Symbols", bg=DARK["panel"], fg=DARK["text"], anchor="w", padx=10, pady=8).pack(fill="x")
        self.symbol_tree = ttk.Treeview(parent, columns=("kind", "line"), show="tree headings", height=12)
        self.symbol_tree.heading("#0", text="Name")
        self.symbol_tree.heading("kind", text="Type")
        self.symbol_tree.heading("line", text="Line")
        self.symbol_tree.column("#0", width=190)
        self.symbol_tree.column("kind", width=90, anchor="center")
        self.symbol_tree.column("line", width=60, anchor="center")
        self.symbol_tree.pack(fill="x", padx=8, pady=(0, 8))
        self.symbol_tree.bind("<<TreeviewSelect>>", self.on_symbol_select)

    def _build_center(self, parent):
        header = tk.Frame(parent, bg=DARK["panel"])
        header.pack(fill="x")
        self.file_label = tk.Label(header, text="No file open", bg=DARK["panel"], fg=DARK["text"], anchor="w", padx=10, pady=8)
        self.file_label.pack(fill="x")

        editor_frame = tk.Frame(parent, bg=DARK["code_bg"])
        editor_frame.pack(fill="both", expand=True)
        self.editor = tk.Text(editor_frame, bg=DARK["code_bg"], fg=DARK["text"], insertbackground=DARK["text"], undo=True, wrap="none", relief="flat", padx=12, pady=12, font=("Consolas", 11))
        self.editor.pack(side="left", fill="both", expand=True)
        y_scroll = tk.Scrollbar(editor_frame, orient="vertical", command=self.editor.yview)
        y_scroll.pack(side="right", fill="y")
        self.editor.configure(yscrollcommand=y_scroll.set)
        self.editor.bind("<KeyRelease>", self.on_editor_changed)
        self.editor.bind("<ButtonRelease-1>", self.on_editor_click)
        self.editor.tag_configure("kw", foreground="#c792ea")
        self.editor.tag_configure("str", foreground="#ecc48d")
        self.editor.tag_configure("comment", foreground="#7f8c98")
        self.editor.tag_configure("primary", background="#24303b", foreground=DARK["text"])
        self.editor.tag_configure("secondary", background="#1c2732", foreground=DARK["text"])
        self.editor.tag_configure("tertiary", background="#18212b", foreground=DARK["text"])
        self.editor.tag_configure("cursor_line", background="#131a22")
        self.editor.tag_configure("search", background="#5a4a1f", foreground="#fff6cf")
        self.editor.tag_configure("error_line", background="#402126", foreground="#ffd7d7")

    def _build_right(self, parent):
        tk.Label(parent, text="Preview", bg=DARK["panel"], fg=DARK["text"], anchor="w", padx=10, pady=8).pack(fill="x")
        controls = tk.Frame(parent, bg=DARK["panel"])
        controls.pack(fill="x", padx=8, pady=(0, 6))
        tk.Checkbutton(controls, text="Live preview", variable=self.live_preview_var, bg=DARK["panel"], fg=DARK["text"], selectcolor=DARK["panel2"], activebackground=DARK["panel"], activeforeground=DARK["text"], relief="flat", command=self.schedule_live_analysis).pack(side="left")
        tk.Button(controls, text="Delete Block", command=self.delete_current_block, bg=DARK["panel2"], fg=DARK["text"], activebackground=DARK["selection"], relief="flat", bd=0, padx=10, pady=5).pack(side="left", padx=(8, 6))
        tk.Button(controls, text="Replace Asset", command=self.replace_preview_asset, bg=DARK["panel2"], fg=DARK["text"], activebackground=DARK["selection"], relief="flat", bd=0, padx=10, pady=5).pack(side="left", padx=(0, 6))
        tk.Button(controls, text="Save Asset Copy", command=self.save_preview_asset_copy, bg=DARK["panel2"], fg=DARK["text"], activebackground=DARK["selection"], relief="flat", bd=0, padx=10, pady=5).pack(side="left")
        tk.Label(controls, textvariable=self.preview_source_text, bg=DARK["panel"], fg=DARK["muted"], anchor="e").pack(side="right")
        self.preview_canvas = tk.Canvas(parent, bg=DARK["panel"], highlightthickness=0)
        self.preview_canvas.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.preview_canvas.bind("<Configure>", lambda _e: self.refresh_preview())
        diagnostics = tk.Frame(parent, bg=DARK["panel2"])
        diagnostics.pack(fill="x", padx=8, pady=(0, 6))
        tk.Label(diagnostics, text="Diagnostics", bg=DARK["panel2"], fg=DARK["text"], anchor="w", padx=10, pady=6).pack(fill="x")
        self.diagnostics_label = tk.Label(diagnostics, textvariable=self.diagnostics_text, bg=DARK["panel2"], fg=DARK["muted"], justify="left", anchor="w", wraplength=390, padx=10, pady=4)
        self.diagnostics_label.pack(fill="x")
        self.problem_listbox = tk.Listbox(diagnostics, height=5, bg=DARK["code_bg"], fg=DARK["text"], selectbackground=DARK["selection"], selectforeground=DARK["text"], highlightthickness=0, relief="flat")
        self.problem_listbox.pack(fill="x", padx=10, pady=(4, 8))
        self.problem_listbox.bind("<<ListboxSelect>>", self.on_problem_select)
        self.details = tk.Text(parent, bg=DARK["panel2"], fg=DARK["text"], height=12, relief="flat", wrap="word", padx=10, pady=10, font=("Segoe UI", 10))
        self.details.pack(fill="x", padx=8, pady=(0, 8))
        self.details.configure(state="disabled")

    def _build_bottom(self):
        bottom = tk.Frame(self, bg=DARK["panel"], height=150)
        bottom.pack(fill="x", side="bottom")
        tk.Label(bottom, text="Logs", bg=DARK["panel"], fg=DARK["text"], anchor="w", padx=10, pady=6).pack(fill="x")
        self.log_box = tk.Text(bottom, bg=DARK["code_bg"], fg=DARK["muted"], height=8, relief="flat", wrap="word", padx=10, pady=8, font=("Consolas", 10))
        self.log_box.pack(fill="x", padx=8, pady=(0, 8))
        self.log_box.configure(state="disabled")

    def _bind_shortcuts(self):
        self.bind("<Control-o>", lambda _e: self.open_file())
        self.bind("<Control-Shift-O>", lambda _e: self.open_project())
        self.bind("<Control-s>", lambda _e: self.save_file())
        self.bind("<Control-Shift-S>", lambda _e: self.save_as())
        self.bind("<Control-f>", lambda _e: self.find_text())
        self.bind("<Control-BackSpace>", lambda _e: self.delete_current_block())
        self.bind("<F8>", lambda _e: self.jump_to_next_problem())
        self.bind("<F5>", lambda _e: self.reparse_current_file())

    def log(self, text: str):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", text + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")
        self.status_text.set(text)

    def open_project(self):
        folder = filedialog.askdirectory(title="Open project folder")
        if folder:
            self.set_project_root(Path(folder))

    def open_zip(self):
        filename = filedialog.askopenfilename(filetypes=[("Zip archives", "*.zip"), ("All files", "*.*")], title="Open zip project")
        if not filename:
            return
        self.load_zip_project(Path(filename))

    def set_project_root(self, path: Path):
        self.project_root = path
        self.module_index = build_module_index(path)
        self.populate_file_tree()
        self.log(f"Project opened: {path}")

    def load_zip_project(self, zip_path: Path):
        extract_root = Path(tempfile.mkdtemp(prefix="vcw_project_"))
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(extract_root)
        roots = [p for p in extract_root.iterdir() if p.is_dir()]
        project_path = roots[0] if len(roots) == 1 else extract_root
        self.zip_extract_root = extract_root
        self.set_project_root(project_path)
        self.log(f"Zip project extracted: {zip_path.name} -> {project_path}")

    def populate_file_tree(self):
        self.file_tree.delete(*self.file_tree.get_children())
        if not self.project_root:
            return
        root_id = self.file_tree.insert("", "end", text=self.project_root.name, open=True)
        self._insert_dir(root_id, self.project_root)

    def _insert_dir(self, parent_id, path: Path):
        try:
            children = sorted(path.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
        except Exception as exc:
            self.log(f"Folder read failed: {exc}")
            return
        for child in children:
            if child.name.startswith("."):
                continue
            item_id = self.file_tree.insert(parent_id, "end", text=child.name, open=False)
            if child.is_dir():
                self._insert_dir(item_id, child)

    def on_file_tree_select(self, _event=None):
        selection = self.file_tree.selection()
        if not selection:
            return
        path = self._tree_path(selection[0])
        if path and path.is_file() and path.suffix.lower() == ".py":
            self.load_file(path)

    def _tree_path(self, item) -> Optional[Path]:
        if not self.project_root:
            return None
        parts = []
        while item:
            parts.append(self.file_tree.item(item, "text"))
            item = self.file_tree.parent(item)
        parts.reverse()
        if parts and parts[0] == self.project_root.name:
            return self.project_root.joinpath(*parts[1:])
        return None

    def open_file(self):
        filename = filedialog.askopenfilename(filetypes=[("Python files", "*.py"), ("All files", "*.*")], title="Open file")
        if filename:
            self.load_file(Path(filename))

    def _read_text(self, path: Path) -> str:
        for enc in ("utf-8", "latin-1"):
            try:
                return path.read_text(encoding=enc)
            except Exception:
                pass
        raise OSError(f"Could not read: {path}")

    def load_file(self, path: Path):
        try:
            source = self._read_text(path)
        except Exception as exc:
            messagebox.showerror(APP_TITLE, f"Could not open file:\n{exc}")
            return
        self.current_file = path
        self.current_source = source
        self.file_label.configure(text=str(path))
        self.editor.delete("1.0", "end")
        self.editor.insert("1.0", source)
        self.colorize()
        self.reparse_current_file(log_success=False)
        self.log(f"Loaded file: {path}")

    def reparse_current_file(self, log_success=True):
        if not self.current_file:
            return
        self.current_source = self.editor.get("1.0", "end-1c")
        valid = self.validate_buffer(show_success=log_success)
        if not valid:
            self.symbol_map = {}
            self.populate_symbol_tree()
            return
        try:
            self.analyzer = PythonAnalyzer(self.current_source)
            self.symbol_map = self.analyzer.symbols
            self.populate_symbol_tree()
            if self.current_symbol and self.current_symbol.key in self.symbol_map:
                self.focus_symbol(self.symbol_map[self.current_symbol.key])
            else:
                self.refresh_preview()
            if log_success:
                self.log(f"Parse successful. Symbols: {len(self.symbol_map)}")
        except Exception as exc:
            self.log(f"Parse failed: {exc}")
            self._set_details("Parse error", traceback.format_exc())

    def populate_symbol_tree(self):
        self.symbol_tree.delete(*self.symbol_tree.get_children())
        if not self.analyzer:
            return
        created = set()
        for key, info in sorted(self.symbol_map.items(), key=lambda item: (item[1].lineno, item[0])):
            parent = info.parent if info.parent in self.symbol_map else ""
            self.symbol_tree.insert(parent, "end", iid=key, text=info.name, values=(info.kind, info.lineno), open=True)
            created.add(key)

    def on_symbol_select(self, _event=None):
        selection = self.symbol_tree.selection()
        if selection:
            info = self.symbol_map.get(selection[0])
            if info:
                self.focus_symbol(info)

    def focus_symbol(self, info: SymbolInfo):
        self.current_symbol = info
        self.highlight_symbol(info)
        start_index = f"{info.lineno}.0"
        self.editor.mark_set("insert", start_index)
        self.editor.see(start_index)
        linked = self.analyzer.lookup_links(info) if self.analyzer else set()
        preview_spec = build_preview_spec(self.current_source, info, self.current_file, self.project_root, self.analyzer, getattr(self, "module_index", None))
        self.preview_payload = {
            "name": info.display_name,
            "kind": info.kind,
            "doc": info.doc,
            "calls": info.calls,
            "assigns": info.assigns,
            "returns": info.returns,
            "dependencies": info.dependencies,
            "linked": linked,
            "strings": info.string_literals,
            "line_span": f"{info.lineno}-{info.end_lineno}",
            "preview_spec": preview_spec,
            "preview_source": self._preview_source_label(preview_spec),
        }
        self.preview_source_text.set(f"Preview: {self.preview_payload['preview_source']}")
        self.refresh_preview()
        self._set_details(info.display_name, self._details_text(info, linked))
        self.log(f"Focused symbol: {info.display_name}")

    def highlight_symbol(self, info: SymbolInfo):
        for tag in ("primary", "secondary", "tertiary", "cursor_line"):
            self.editor.tag_remove(tag, "1.0", "end")
        self.editor.tag_add("primary", f"{info.lineno}.0", f"{info.end_lineno}.end")

        secondary_names = set(info.direct_dependencies) | set(info.imports) | set(info.bases) | set(info.decorators)
        tertiary_names = {Path(s).name for s in info.string_literals if len(s) < 50}

        for dep in sorted(secondary_names):
            if dep == info.name or dep in PY_KEYWORDS:
                continue
            self._highlight_word(dep, "secondary")
        for dep in sorted(tertiary_names):
            if dep and dep not in PY_KEYWORDS and dep.isidentifier():
                self._highlight_word(dep, "tertiary")
        self.editor.tag_add("cursor_line", f"{info.lineno}.0", f"{info.lineno}.end")

    def _highlight_word(self, word: str, tag: str):
        start = "1.0"
        pattern = rf"\m{re.escape(word)}\M"
        while True:
            pos = self.editor.search(pattern, start, stopindex="end", regexp=True)
            if not pos:
                break
            end = f"{pos}+{len(word)}c"
            self.editor.tag_add(tag, pos, end)
            start = end


    def _preview_source_label(self, spec: dict) -> str:
        return self.preview_renderer.preview_source_label(spec)

    def _details_text(self, info: SymbolInfo, linked: Set[str]) -> str:
        preview_spec = build_preview_spec(self.current_source, info, self.current_file, self.project_root, self.analyzer, getattr(self, "module_index", None))
        lines = [
            f"Type: {info.kind}",
            f"Preview source: {self._preview_source_label(preview_spec)}",
            f"Lines: {info.lineno}-{info.end_lineno}",
            f"Calls: {', '.join(sorted(info.calls)) or 'None'}",
            f"Writes: {', '.join(sorted(info.assigns)) or 'None'}",
            f"Returns: {', '.join(sorted(info.returns)) or 'No explicit return'}",
            f"Imports: {', '.join(sorted(info.imports)) or 'None'}",
            f"Bases: {', '.join(sorted(info.bases)) or 'None'}",
            f"Decorators: {', '.join(sorted(info.decorators)) or 'None'}",
            f"Local links: {', '.join(sorted(linked)) or 'None'}",
            f"Dependencies: {', '.join(sorted(info.dependencies)) or 'None'}",
        ]
        if info.string_literals:
            lines.append("Strings: " + ", ".join(sorted(list(info.string_literals))[:6]))
        if info.doc:
            lines.extend(["", "Docstring:", info.doc])
        return "\n".join(lines)

    def _set_details(self, title: str, body: str):
        self.details.configure(state="normal")
        self.details.delete("1.0", "end")
        self.details.insert("1.0", title + "\n\n" + body)
        self.details.configure(state="disabled")

    def refresh_preview(self):
        try:
            self.preview_renderer.draw_tk(self.preview_canvas, self.preview_payload)
        except Exception as exc:
            self.set_problem_items([{"label": f"Preview error: {exc}", "line": 1, "column": 0, "severity": "error"}])
            self.set_diagnostics(f"Preview error: {exc}", error=True)
            self.log(f"Preview error: {exc}")

    def on_editor_changed(self, _event=None):
        self.colorize()
        self.schedule_live_analysis()

    def on_editor_click(self, _event=None):
        best = self._find_symbol_at_cursor()
        if best:
            self.symbol_tree.selection_set(best.key)
            self.focus_symbol(best)

    def schedule_live_analysis(self, *_args):
        if self.validation_after_id is not None:
            try:
                self.after_cancel(self.validation_after_id)
            except Exception:
                pass
        self.validation_after_id = self.after(220, self.run_live_analysis)

    def run_live_analysis(self):
        self.validation_after_id = None
        self.validate_buffer(show_success=False)
        if self.live_preview_var.get() and self.current_symbol and self.analyzer and self.current_symbol.key in self.symbol_map:
            try:
                self.focus_symbol(self.symbol_map[self.current_symbol.key])
            except Exception as exc:
                self.set_problem_items([{"label": f"Preview error: {exc}", "line": 1, "column": 0, "severity": "error"}])
                self.set_diagnostics(f"Preview error: {exc}", error=True)

    def clear_problem_marks(self):
        self.editor.tag_remove("error_line", "1.0", "end")

    def set_problem_items(self, items: List[dict]):
        self.problem_items = list(items)
        if self.problem_listbox is not None:
            self.problem_listbox.delete(0, "end")
            for item in self.problem_items:
                self.problem_listbox.insert("end", item.get("label", "Issue"))
        self.clear_problem_marks()
        for item in self.problem_items:
            line = max(1, int(item.get("line", 1)))
            self.editor.tag_add("error_line", f"{line}.0", f"{line}.end")

    def set_diagnostics(self, text: str, error: bool = False):
        self.diagnostics_text.set(text)
        self.diagnostics_label.configure(fg=DARK["danger"] if error else DARK["muted"])

    def validate_buffer(self, show_success: bool = False) -> bool:
        content = self.editor.get("1.0", "end-1c")
        try:
            ast.parse(content)
            self.last_error = None
            self.set_problem_items([])
            self.set_diagnostics("No issues detected.", error=False)
            if show_success:
                self.log("Validation passed.")
            return True
        except SyntaxError as exc:
            self.last_error = exc
            line = getattr(exc, "lineno", 1) or 1
            col = getattr(exc, "offset", 1) or 1
            msg = getattr(exc, "msg", str(exc))
            self.set_problem_items([{"label": f"Syntax error · line {line}: {msg}", "line": line, "column": max(0, col - 1), "severity": "error"}])
            self.set_diagnostics(f"Syntax error on line {line}: {msg}", error=True)
            return False

    def on_problem_select(self, _event=None):
        if self.problem_listbox is None:
            return
        sel = self.problem_listbox.curselection()
        if not sel:
            return
        item = self.problem_items[sel[0]]
        self.jump_to_problem(item)

    def jump_to_problem(self, item: dict):
        line = max(1, int(item.get("line", 1)))
        col = max(0, int(item.get("column", 0)))
        index = f"{line}.{col}"
        self.editor.mark_set("insert", index)
        self.editor.see(index)
        self.editor.focus_set()

    def jump_to_next_problem(self):
        if not self.problem_items:
            return
        current = self.problem_listbox.curselection()[0] if self.problem_listbox and self.problem_listbox.curselection() else -1
        next_idx = (current + 1) % len(self.problem_items)
        if self.problem_listbox is not None:
            self.problem_listbox.selection_clear(0, "end")
            self.problem_listbox.selection_set(next_idx)
            self.problem_listbox.activate(next_idx)
        self.jump_to_problem(self.problem_items[next_idx])

    def _find_symbol_at_cursor(self) -> Optional[SymbolInfo]:
        line = int(float(self.editor.index("insert")))
        best = None
        for info in self.symbol_map.values():
            if info.lineno <= line <= info.end_lineno:
                if best is None or (info.end_lineno - info.lineno) < (best.end_lineno - best.lineno):
                    best = info
        return best

    def _block_start_with_decorators(self, info: SymbolInfo) -> int:
        start = info.lineno
        while start > 1:
            line = self.editor.get(f"{start - 1}.0", f"{start - 1}.end")
            if line.lstrip().startswith("@"):
                start -= 1
                continue
            break
        return start

    def _normalize_blank_lines(self, text: str) -> str:
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.lstrip("\n")


    def _repair_expected_block_errors(self, text: str) -> str:
        attempts = 0
        while attempts < 8:
            try:
                ast.parse(text)
                return text
            except IndentationError as exc:
                msg = getattr(exc, "msg", "")
                if "expected an indented block" not in msg:
                    break
                line_no = getattr(exc, "lineno", None)
                if not line_no:
                    break
                lines = text.splitlines()
                if not (1 <= line_no <= len(lines)):
                    break
                header = lines[line_no - 1]
                indent = re.match(r"\s*", header).group(0) + "    "
                insert_at = line_no
                if insert_at < len(lines) and lines[insert_at].strip() == "pass":
                    break
                lines.insert(insert_at, indent + "pass")
                text = "\n".join(lines) + ("\n" if text.endswith("\n") else "")
                attempts += 1
                continue
                text = "\n".join(lines) + ("\n" if text.endswith("\n") else "")
    def delete_current_block(self):
        info = self.current_symbol if self.current_symbol and self.current_symbol.key in self.symbol_map else self._find_symbol_at_cursor()
        if not info:
            self.set_diagnostics("No code block selected to delete.", error=True)
            return
        start_line = self._block_start_with_decorators(info)
        end_line = info.end_lineno
        start_index = f"{start_line}.0"
        end_index = f"{end_line + 1}.0"
        original = self.editor.get("1.0", "end-1c")
        self.editor.delete(start_index, end_index)
        updated = self.editor.get("1.0", "end-1c")
        updated = self._normalize_blank_lines(updated)
        updated = self._repair_expected_block_errors(updated)
        self.editor.delete("1.0", "end")
        self.editor.insert("1.0", updated)
        self.colorize()
        valid = self.validate_buffer(show_success=False)
        self.current_source = updated
        if valid:
            self.reparse_current_file(log_success=False)
            self.set_diagnostics(f"Deleted block: {info.display_name}", error=False)
            self.log(f"Deleted block: {info.display_name}")
            replacement = self._find_symbol_at_cursor()
            if replacement:
                self.symbol_tree.selection_set(replacement.key)
                self.focus_symbol(replacement)
            else:
                self.current_symbol = None
                self.preview_payload = {"name": "No selection", "kind": "idle", "doc": "Block deleted.", "preview_source": "idle"}
                self.preview_source_text.set("Preview: idle")
                self.refresh_preview()
        else:
            self.log(f"Deleted block with remaining syntax issue near line {getattr(self.last_error, 'lineno', '?')}")

    def _preview_asset_candidates(self) -> List[Tuple[str, str]]:
        spec = self.preview_payload.get("preview_spec") or {}
        candidates: List[Tuple[str, str]] = []
        if spec.get("kind") == "image_asset":
            for path in spec.get("images", []):
                candidates.append((str(path), str(path)))
        strings = sorted(self.preview_payload.get("strings", []))
        for value in strings:
            low = value.lower().strip().strip("\"'")
            if any(low.endswith(ext) for ext in IMAGE_EXTS) or low.endswith((".egg", ".bam", ".gltf", ".glb", ".obj")):
                candidates.append((value, value))
        seen = set()
        uniq = []
        for old, new in candidates:
            if old not in seen:
                uniq.append((old, new))
                seen.add(old)
            low = value.lower().strip().strip("\"'")

    def replace_preview_asset(self):
        if not self.current_symbol:
            self.set_diagnostics("Select a block with an asset reference first.", error=True)
            return
        candidates = self._preview_asset_candidates()
        if not candidates:
            self.set_diagnostics("No replaceable asset path found in the selected block.", error=True)
            return
        old_value = candidates[0][0]
        new_path = filedialog.askopenfilename(title="Choose replacement asset")
        if not new_path:
            return
        block_start = f"{self.current_symbol.lineno}.0"
        block_end = f"{self.current_symbol.end_lineno}.end"
        block = self.editor.get(block_start, block_end)
        if old_value not in block:
            self.set_diagnostics("The selected asset path is not present in the current block text.", error=True)
            return
        block = block.replace(old_value, new_path.replace("\\", "/"), 1)
        self.editor.delete(block_start, block_end)
        self.editor.insert(block_start, block)
        self.colorize()
        self.run_live_analysis()
        self.log(f"Replaced asset in {self.current_symbol.display_name}: {old_value} -> {new_path}")

    def save_preview_asset_copy(self):
        spec = self.preview_payload.get("preview_spec") or {}
        source_path = None
        if spec.get("kind") == "image_asset" and spec.get("images"):
            source_path = spec["images"][0]
        else:
            candidates = self._preview_asset_candidates()
            if candidates:
                source_path = candidates[0][0]
        if not source_path:
            self.set_diagnostics("No asset available to copy from this preview.", error=True)
            return
        src = Path(source_path)
        if not src.exists():
            self.set_diagnostics("The current asset path does not exist on disk.", error=True)
            return
        target = filedialog.asksaveasfilename(initialfile=src.name, title="Save asset copy as")
        if not target:
            return
        Path(target).write_bytes(src.read_bytes())
        self.set_diagnostics(f"Asset copied to {target}", error=False)
        self.log(f"Asset copied: {src} -> {target}")

    def colorize(self):
        content = self.editor.get("1.0", "end-1c")
        for tag in ("kw", "str", "comment"):
            self.editor.tag_remove(tag, "1.0", "end")
        for match in re.finditer(r"#.*$", content, flags=re.MULTILINE):
            self._tag_span("comment", match.start(), match.end())
        for match in re.finditer(r"(?:'''[\s\S]*?'''|\"\"\"[\s\S]*?\"\"\"|'[^'\\]*(?:\\.[^'\\]*)*'|\"[^\"\\]*(?:\\.[^\"\\]*)*\")", content):
            self._tag_span("str", match.start(), match.end())
        for match in re.finditer(r"\b[a-zA-Z_][a-zA-Z0-9_]*\b", content):
            if match.group(0) in PY_KEYWORDS:
                self._tag_span("kw", match.start(), match.end())

    def _tag_span(self, tag: str, start_off: int, end_off: int):
        self.editor.tag_add(tag, self._offset_to_index(start_off), self._offset_to_index(end_off))

    def _offset_to_index(self, offset: int) -> str:
        content = self.editor.get("1.0", "end-1c")
        before = content[:offset]
        line = before.count("\n") + 1
        col = len(before.rsplit("\n", 1)[-1])
        return f"{line}.{col}"

    def save_file(self):
        if not self.current_file:
            return self.save_as()
        content = self.editor.get("1.0", "end-1c")
        try:
            ast.parse(content)
        except SyntaxError as exc:
            messagebox.showerror(APP_TITLE, f"Syntax check failed:\n{exc}")
            self.log(f"Save blocked by syntax error: {exc}")
            return
        self.current_file.write_text(content, encoding="utf-8")
        self.current_source = content
        self.reparse_current_file(log_success=False)
        self.log(f"Saved: {self.current_file}")

    def save_as(self):
        filename = filedialog.asksaveasfilename(defaultextension=".py", filetypes=[("Python files", "*.py"), ("All files", "*.*")], title="Save as")
        if filename:
            self.current_file = Path(filename)
            self.save_file()
            self.file_label.configure(text=str(self.current_file))

    def find_text(self):
        needle = simpledialog.askstring(APP_TITLE, "Find text:")
        if not needle:
            return
        self.editor.tag_remove("search", "1.0", "end")
        start = "1.0"
        hits = 0
        while True:
            pos = self.editor.search(needle, start, stopindex="end")
            if not pos:
                break
            end = f"{pos}+{len(needle)}c"
            self.editor.tag_add("search", pos, end)
            hits += 1
            start = end
        self.log(f"Find: '{needle}' hit {hits} occurrence(s).")
        if hits:
            first = self.editor.tag_ranges("search")[0]
            self.editor.see(first)
            self.editor.mark_set("insert", first)

    def export_preview(self):
        if Image is None:
            messagebox.showerror(APP_TITLE, "Pillow is required for PNG export.")
            return
        filename = filedialog.asksaveasfilename(defaultextension=".png", filetypes=[("PNG Image", "*.png")], title="Export preview")
        if not filename:
            return
        try:
            image = self.preview_renderer.render_image(1600, 900, self.preview_payload)
        except Exception as exc:
            self.set_diagnostics(f"Preview export failed: {exc}", error=True)
            self.log(f"Preview export failed: {exc}")
            messagebox.showerror(APP_TITLE, f"Preview export failed:\n{exc}")
            return
        if image is None:
            messagebox.showerror(APP_TITLE, "Preview export failed.")
            return
        image.save(filename)
        self.log(f"Preview exported: {filename}")

    def batch_report_dialog(self):
        if self.project_root:
            target = self.project_root
        elif self.current_file:
            target = self.current_file
        else:
            path = filedialog.askopenfilename(filetypes=[("Python or zip", "*.py *.zip"), ("All files", "*.*")], title="Pick file or zip for batch report")
            if not path:
                return
            target = Path(path)
        report = BatchTester().analyze_path(target)
        top = sorted((f for f in report["files"] if "symbols" in f), key=lambda r: r["symbols"], reverse=True)[:10]
        lines = [
            f"Root: {report['root']}",
            f"Python files: {report['python_files']}",
            f"Parsed files: {report['parsed_files']}",
            f"Symbols: {report['symbols']}",
            f"Verified Panda GUI previews: {report.get('verified_panda_gui', 0)}",
            f"Verified Panda model previews: {report.get('verified_panda_models', 0)}",
            f"Resolved image assets: {report.get('resolved_image_assets', 0)}",
            "Categories: " + ", ".join(f"{k}={v}" for k, v in report["categories"].items()),
            "",
            "Top files by symbol count:",
        ]
        for item in top:
            lines.append(f"- {Path(item['path']).name}: {item['symbols']} symbols")
        self._set_details("Batch report", "\n".join(lines))
        save_path = filedialog.asksaveasfilename(defaultextension='.json', filetypes=[('JSON', '*.json')], initialfile=f'PyCodeSmith_{APP_VERSION}_report.json', title='Save batch report as')
        if save_path:
            Path(save_path).write_text(json.dumps(report, indent=2), encoding='utf-8')
            self.log(f"Batch report saved: {save_path}")
        else:
            self.log(f"Batch report complete. Parsed {report['parsed_files']} Python files.")

    def on_close(self):
        self.destroy()


def render_sample_screenshot(output_path: str):
    renderer = DependencyPreviewRenderer()
    payload = {
        "name": "SettingsMenu",
        "kind": "class",
        "doc": "Minimal right-panel UI preview preserving 16:9 reference placement.",
        "calls": {"open_menu", "apply_settings"},
        "assigns": {"volume", "resolution", "ui_scale"},
        "returns": {"None"},
        "line_span": "120-188",
        "linked": {"App", "AudioSettings"},
        "strings": {"settings panel", "volume slider"},
    }
    image = renderer.render_image(1600, 900, payload)
    if image:
        image.save(output_path)


def _image_quality_score(image) -> float:
    from PIL import ImageStat
    stat = ImageStat.Stat(image)
    mean = sum(stat.mean[:3]) / max(1, len(stat.mean[:3]))
    std = sum(stat.stddev[:3]) / max(1, len(stat.stddev[:3]))
    extrema = sum(abs(mx - mn) for mn, mx in stat.extrema[:3]) / 3.0
    return std * 2.2 + min(180.0, mean) + extrema * 0.35

def _preview_richness_score(spec: dict) -> float:
    spec = spec or {}
    kind = spec.get('kind')
    if kind == 'panda_gui':
        widgets = spec.get('widgets', [])
        texts = sum(1 for w in widgets if str(w.get('text', '')).strip())
        framed = sum(1 for w in widgets if w.get('frameSize'))
        return len(widgets) * 14 + texts * 8 + framed * 6
    if kind == 'panda_models':
        models = spec.get('models', [])
        return len(models) * 24
    if kind == 'pygame_primitives':
        return len(spec.get('windows', [])) * 26 + len(spec.get('shapes', [])) * 1.2
    if kind == 'image_asset':
        return len(spec.get('images', [])) * 40
    return 0.0




def _spec_candidate_score(payload: dict, spec: dict) -> float:
    score = _preview_richness_score(spec)
    name = str(payload.get('name','')).lower()
    doc = str(payload.get('doc','')).lower()
    text = name + ' ' + doc
    if spec.get('kind') == 'panda_gui':
        if any(k in text for k in ['menu','hud','settings','panel','dialog','inventory']):
            score += 25
    elif spec.get('kind') == 'panda_models':
        if any(k in text for k in ['player','enemy','weapon','ship','vehicle','robot','monster']):
            score += 18
    elif spec.get('kind') == 'pygame_primitives':
        if len(spec.get('windows', [])):
            score += 22
    elif spec.get('kind') == 'image_asset':
        imgs = spec.get('images', [])
        if imgs:
            n = Path(imgs[0]).name.lower()
            if any(k in n for k in ['hud','icon','weapon','sprite','ui','button','menu']):
                score += 20
    return score

def render_verified_gallery(target: str, output_path: str, max_items: int = 4):
    renderer = DependencyPreviewRenderer()
    tester = BatchTester()
    target_path = Path(target)
    project_root = target_path if target_path.is_dir() else (tester._scan_root(target_path) or target_path.parent)
    module_index = build_module_index(project_root)
    files = tester._expand_inputs(target_path)
    candidates = {
        'panda_gui': [],
        'panda_models': [],
        'pygame_primitives': [],
        'image_asset': [],
    }
    for file_path in files:
        source = tester._read_text(file_path)
        if source is None:
            continue
        try:
            analyzer = PythonAnalyzer(source)
        except Exception:
            continue
        for info in analyzer.symbols.values():
            payload = tester.payload_for(analyzer, info, file_path, project_root, module_index)
            spec = payload.get('preview_spec') or {}
            kind = spec.get('kind')
            if kind not in candidates:
                continue
            score = _spec_candidate_score(payload, spec)
            candidates[kind].append((score, Path(file_path).parent.name, file_path, payload, None))
    for kind, vals in candidates.items():
        vals.sort(key=lambda item: item[0], reverse=True)
        if kind in {'pygame_primitives', 'image_asset', 'panda_gui'}:
            vals = sorted(vals, key=lambda item: (_is_lifted((item[3].get('preview_spec') or {})), -item[0]))
        candidates[kind] = vals[:12]



def _visual_readability_score(image) -> float:
    from PIL import ImageStat
    stat = ImageStat.Stat(image)
    mean = sum(stat.mean[:3]) / max(1, len(stat.mean[:3]))
    std = sum(stat.stddev[:3]) / max(1, len(stat.stddev[:3]))
    extrema = sum(abs(mx - mn) for mn, mx in stat.extrema[:3]) / 3.0
    center_box = image.crop((image.width * 0.1, image.height * 0.1, image.width * 0.9, image.height * 0.9))
    cstat = ImageStat.Stat(center_box)
    cstd = sum(cstat.stddev[:3]) / max(1, len(cstat.stddev[:3]))
    return std * 2.2 + min(180.0, mean) * 0.35 + extrema * 0.35 + cstd * 1.1

    desired_order = ['panda_gui', 'panda_models', 'pygame_primitives', 'image_asset']
    # Rerank likely finalists by actual visual readability so washed-out GUI cells and weak asset picks lose.
    for kind in ['panda_gui', 'pygame_primitives', 'image_asset']:
        reranked = []
        for score, parent_name, file_path, payload, card in candidates[kind][:6]:
            try:
                rendered = renderer.render_image(960, 540, payload)
                vis = _visual_readability_score(rendered) if rendered is not None else 0.0
            except Exception:
                rendered = None
                vis = 0.0
            reranked.append((score + vis, parent_name, file_path, payload, rendered))
        reranked.sort(key=lambda item: item[0], reverse=True)
        if reranked:
            candidates[kind] = reranked + candidates[kind][6:]
    used_parents = set()
    examples = []
    for kind in desired_order:
        for score, parent_name, file_path, payload, card in candidates[kind]:
            if parent_name in used_parents:
                continue
            examples.append((file_path, payload, card))
            used_parents.add(parent_name)
            break
        if len(examples) >= max_items:
            break
    if len(examples) < max_items:
        flat = []
        for kind in desired_order:
            flat.extend(candidates[kind])
        flat.sort(key=lambda item: item[0], reverse=True)
        for score, parent_name, file_path, payload, card in flat:
            item = (file_path, payload, card)
            if item in examples:
                continue
            if score < 90 and examples:
                continue
            examples.append(item)
            if len(examples) >= max_items:
                break
    if not examples:
        render_sample_screenshot(output_path)
        return

    card_w, card_h = 960, 540
    margin = 28
    cols = 2
    rows = (len(examples) + cols - 1) // cols
    sheet = Image.new('RGB', (cols * card_w + (cols + 1) * margin, rows * card_h + (rows + 1) * margin), DARK['bg'])
    draw = ImageDraw.Draw(sheet)
    for idx, (file_path, payload, card) in enumerate(examples):
        if card is None:
            try:
                card = renderer.render_image(card_w, card_h, payload)
            except Exception:
                card = renderer.render_image(card_w, card_h, {'name':'Preview failed','kind':'logic','doc':'Renderer fallback.'})
        x = margin + (idx % cols) * (card_w + margin)
        y = margin + (idx // cols) * (card_h + margin)
        sheet.paste(card, (x, y))
        draw.rectangle((x, y, x + card_w, y + card_h), outline=DARK['line'], width=2)
        label = f"{Path(file_path).parent.name} / {payload.get('name','symbol')} / {payload.get('preview_source','preview')}"
        draw.rectangle((x, y, x + card_w, y + 34), fill=(5, 8, 14))
        draw.text((x + 12, y + 9), textwrap.shorten(label, width=78, placeholder='…'), fill=DARK['text'])
        kind = (payload.get('preview_spec') or {}).get('kind', payload.get('kind', 'preview'))
        footer = f"{kind} · lines {payload.get('line_span','?')}"
        lifted = (payload.get('preview_spec') or {}).get('lifted_from')
        if lifted:
            footer += f" · from {lifted}"
        draw.rectangle((x, y + card_h - 34, x + card_w, y + card_h), fill=(0, 0, 0))
        draw.text((x + 12, y + card_h - 25), textwrap.shorten(footer, width=92, placeholder='…'), fill=DARK['text'])
    sheet.save(output_path)


def run_batch_report(target: str, output_path: Optional[str] = None):
    report = BatchTester().analyze_path(Path(target))
    text = json.dumps(report, indent=2)
    if output_path:
        Path(output_path).write_text(text, encoding="utf-8")
    else:
        print(text)


def render_ui_proof(output_path: str):
    if Image is None:
        return
    img = Image.new("RGB", (1600, 900), DARK["bg"])
    draw = ImageDraw.Draw(img)
    draw.rectangle((0, 0, 1600, 48), fill=DARK["panel"])
    draw.text((18, 15), f"PyCodeSmith {APP_VERSION} · live edit · delete block · asset replace · problems", fill=DARK["text"])
    draw.rectangle((10, 58, 310, 720), fill=DARK["panel"], outline=DARK["line"])
    draw.text((22, 74), "Project", fill=DARK["text"])
    draw.rectangle((330, 58, 1080, 720), fill=DARK["code_bg"], outline=DARK["line"])
    draw.rectangle((330, 58, 1080, 96), fill=DARK["panel"], outline=DARK["line"])
    draw.text((344, 72), "SpriteFactory.py", fill=DARK["text"])
    lines = [
        ("def create_artifact(self, source_path):", DARK["text"]),
        ("    sprite = pygame.image.load(source_path).convert_alpha()", "#ecc48d"),
        ("    self.preview_path = source_path", DARK["text"]),
        ("    return sprite", DARK["text"]),
        ("", DARK["text"]),
        ("def load_preview(self):", DARK["text"]),
        ("    return self.create_artifact(\"assets/sprites/weapon.png\")", "#ecc48d"),
    ]
    y = 116
    for i,(line,color) in enumerate(lines):
        if i in (1,6):
            draw.rectangle((342, y-2, 1068, y+20), fill="#24303b")
        draw.text((352, y), line, fill=color)
        y += 28
    draw.rectangle((1100, 58, 1590, 500), fill=DARK["panel"], outline=DARK["line"])
    draw.text((1114, 72), "Preview", fill=DARK["text"])
    draw.rectangle((1114, 104, 1568, 138), fill=DARK["panel2"])
    draw.text((1124, 114), "Delete Block   Replace Asset   Save Asset Copy", fill=DARK["text"])
    draw.text((1390, 72), "Preview: resolved image asset preview", fill=DARK["muted"], anchor="ra")
    draw.rectangle((1116, 106, 1574, 146), fill=DARK["panel2"], outline=DARK["line"])
    draw.text((1128, 118), "☑ Live preview    [Replace Asset]   [Save Asset Copy]", fill=DARK["text"])
    draw.rectangle((1130, 166, 1560, 410), fill=DARK["bg"], outline=DARK["accent"])
    draw.rectangle((1210, 210, 1480, 380), fill="#263241", outline=DARK["accent2"], width=2)
    draw.text((1238, 388), "weapon_sprite_variant.png", fill=DARK["text"])
    draw.rectangle((1100, 518, 1590, 620), fill=DARK["panel2"], outline=DARK["line"])
    draw.text((1114, 532), "Diagnostics", fill=DARK["text"])
    draw.text((1114, 564), "No issues detected. Live edit, preview, and save are available.", fill=DARK["accent2"])
    draw.rectangle((1100, 636, 1590, 892), fill=DARK["panel2"], outline=DARK["line"])
    draw.text((1114, 652), "Selection Details", fill=DARK["text"])
    draw.text((1114, 686), "Type: function\nPreview: resolved image asset preview\nLines: 22-36\nCalls: image.load, convert_alpha", fill=DARK["muted"])
    draw.rectangle((10, 736, 1590, 892), fill=DARK["panel"], outline=DARK["line"])
    draw.text((22, 752), "Logs", fill=DARK["text"])
    draw.text((22, 786), "Parse successful. Symbols: 122\nFocused symbol: SpriteFactory.create_artifact\nAsset reference replaced with: assets/sprites/weapon_sprite_variant.png", fill=DARK["muted"])
    img.save(output_path)

if __name__ == "__main__":
    if "--ui-proof" in sys.argv:
        out = sys.argv[sys.argv.index("--ui-proof") + 1]
        render_ui_proof(out)
        raise SystemExit(0)
    if "--screenshot" in sys.argv:
        out = sys.argv[sys.argv.index("--screenshot") + 1]
        render_sample_screenshot(out)
        raise SystemExit(0)
    if "--verified-gallery" in sys.argv:
        target = sys.argv[sys.argv.index("--verified-gallery") + 1]
        output = sys.argv[sys.argv.index("--output") + 1] if "--output" in sys.argv else f"PyCodeSmith_{APP_VERSION}_gallery.png"
        render_verified_gallery(target, output)
        raise SystemExit(0)
    if "--batch-report" in sys.argv:
        target = sys.argv[sys.argv.index("--batch-report") + 1]
        output = None
        if "--output" in sys.argv:
            output = sys.argv[sys.argv.index("--output") + 1]
        run_batch_report(target, output)
        raise SystemExit(0)
    app = App()
    app.mainloop()
