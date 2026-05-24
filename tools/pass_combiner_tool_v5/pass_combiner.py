#!/usr/bin/env python3
"""Safe patch/pass combiner for iterative game prototype zips.

Version: 4 repo-aware patch automation pass.

Purpose
-------
This tool combines a base project folder/zip with a sequence of patch-only zips
without blindly overwriting important larger files.  Version 4 adds repo-aware
patch-only output, built-in GX/HoloVerse/HoloCore profiles, symbol-regression
checks, and GitHub/PR handoff reports.  It is designed for the
"pass zip" workflow used by HoloCore / HoloVerse style projects.

Default strategy:
  1. Extract/copy the base project to a work directory.
  2. For each pass zip, normalize root paths such as ``HoloCore/main.py`` vs
     ``main.py`` so the patch lands in the same project root.
  3. If a paired ``.diff`` exists, try to apply it first with the system patch
     tool.  This is safer than full-file overwrite when the current target has
     already accumulated later changes.
  4. Apply any zip files not already changed by the diff.
  5. If a candidate file is suspiciously smaller than the current important
     file, do not blindly overwrite it.  For Python files, try a definition-level
     merge that transplants imports/constants/functions/class methods from the
     candidate into the current file while preserving unmentioned code.  For
     other files, save a ``*.incoming.CONFLICT`` copy and report it.

This is not a replacement for human review, but it prevents the common failure
mode where a partial ``main.py`` or runtime module erases a larger integrated
file.
"""
from __future__ import annotations

import argparse
import ast
import difflib
import fnmatch
import hashlib
import json
import os
import signal
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import zipfile
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Iterable

JUNK_PARTS = {
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "logs",
    "crash_reports",
}
JUNK_SUFFIXES = {
    ".pyc",
    ".pyo",
    ".log",
    ".tmp",
    ".bak",
    ".rej",
    ".orig",
}
IMPORTANT_SUFFIXES = {
    ".py",
    ".json",
    ".toml",
    ".yaml",
    ".yml",
    ".ini",
    ".cfg",
    ".txt",
    ".md",
}
DEFAULT_COMMAND_TIMEOUT_SECONDS = 120

ROOT_MARKERS = {
    "main.py",
    "pyproject.toml",
    "requirements.txt",
    "setup.py",
    "holoverse_mode_manifest.json",
    "GXPrototypeLab.py",
}

# Files that should never be blindly replaced in normal project-pass workflows.
# These are the places regressions usually happen: app entrypoints, route files,
# adapters, world/runtime systems, and manifests.  Users can add more with
# --protected-pattern.
DEFAULT_PROTECTED_PATTERNS = [
    "main.py",
    "world.py",
    "runtime.py",
    "*/runtime.py",
    "GXPrototypeLab.py",
    "holoverse_mode_manifest.json",
    "*manifest*.json",
    "ui/ui_manifest.json",
    "dimensions/*.py",
    "Dimensions/**/*.py",
    "adapters/*.py",
    "*/adapters/*.py",
    "*adapter*.py",
    "*route*.py",
    "*routes*.py",
]


BUILTIN_PROFILES = {
    "generic": {
        "protected_patterns": [],
        "validators": [],
        "banned_text": [],
        "description": "Generic guarded patch combine profile.",
    },
    "gx-prototype-lab": {
        "protected_patterns": [
            "GXPrototypeLab.py",
            "data/gx_app_main.py",
            "data/gx_core/*.py",
            "data/gx_core/**/*.py",
            "data/HoloVerse/**/*.py",
            "data/HoloVerse/**/manifest*.json",
            "data/HoloVerse/**/ui_manifest.json",
            "build_GXPrototypeLab.ps1",
            "*.spec",
            "requirements.txt",
            "install_requirements.bat",
            "README_BUILD_EXE.md",
        ],
        "validators": [
            "python -m compileall -q GXPrototypeLab.py data",
        ],
        "banned_text": [],
        "description": "GX Prototype Lab portable launcher/build profile. Guards launcher, runtime paths, HoloVerse tree, specs, requirements, and build scripts.",
    },
    "holoverse": {
        "protected_patterns": [
            "main.py",
            "world.py",
            "runtime.py",
            "Dimensions/**/*.py",
            "dimensions/**/*.py",
            "adapters/**/*.py",
            "*adapter*.py",
            "*route*.py",
            "*manifest*.json",
            "ui/ui_manifest.json",
            "tools/validate_*.py",
        ],
        "validators": [
            "python -m compileall -q .",
            "python tools/validate_holoverse_routes.py",
            "python tools/validate_dimension_contracts.py",
            "python tools/validate_dimension_launches.py",
            "python tools/validate_dimension_presentation_contracts.py",
        ],
        "banned_text": [
            "embedded_external",
            "placeholder_mode",
            "child-window",
        ],
        "description": "HoloVerse artifact/dimension route contract profile.",
    },
    "holocore": {
        "protected_patterns": [
            "main.py",
            "dimensions/**/*.py",
            "assets/entities/**/*.py",
            "assets/holocore/**/*.py",
            "tools/validate_holocore*.py",
        ],
        "validators": [
            "python -m compileall -q .",
            "python tools/validate_holocore_asset_layout.py",
            "python tools/validate_holocore_vertical_strata.py",
            "python tools/validate_holocore_ocean_space.py",
            "python tools/validate_holocore_vessel.py",
        ],
        "banned_text": [],
        "description": "Standalone/same-window HoloCore profile with vertical strata, Ocean-Space, vessel, and entity guards.",
    },
}

TEXT_DIFF_SUFFIXES = IMPORTANT_SUFFIXES | {".ps1", ".bat", ".spec", ".pyw", ".gitignore"}



@dataclass
class FileAction:
    patch: str
    path: str
    action: str
    detail: str = ""
    old_size: int | None = None
    new_size: int | None = None
    incoming_size: int | None = None


@dataclass
class PatchResult:
    patch: str
    diff: str | None
    diff_status: str
    actions: list[FileAction]


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def is_junk_path(path: str) -> bool:
    p = Path(path)
    if any(part in JUNK_PARTS for part in p.parts):
        return True
    if p.suffix.lower() in JUNK_SUFFIXES:
        return True
    # Tool output often nests screenshots in screenshot directories.
    if any("screenshot" in part.lower() for part in p.parts):
        return True
    return False


def safe_extract_zip(zip_path: Path, dest: Path) -> None:
    with zipfile.ZipFile(zip_path) as zf:
        for member in zf.infolist():
            name = member.filename.replace("\\", "/")
            if not name or name.endswith("/"):
                continue
            if name.startswith("/") or ".." in Path(name).parts:
                raise ValueError(f"Unsafe zip path {name!r} in {zip_path}")
            target = dest / name
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(member) as src, target.open("wb") as out:
                shutil.copyfileobj(src, out)


def copy_tree(src: Path, dest: Path) -> None:
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest)


def find_project_root(extracted: Path, preferred_root: str | None = None) -> Path:
    if preferred_root:
        candidate = extracted / preferred_root
        if candidate.exists() and candidate.is_dir():
            return candidate
        raise FileNotFoundError(f"Preferred root {preferred_root!r} was not found under {extracted}")
    if any((extracted / marker).exists() for marker in ROOT_MARKERS):
        return extracted
    children = [p for p in extracted.iterdir() if p.is_dir()]
    if len(children) == 1:
        child = children[0]
        if any((child / marker).exists() for marker in ROOT_MARKERS) or (child / "dimensions").exists():
            return child
    # Prefer a child that looks like a project root.
    for child in children:
        if any((child / marker).exists() for marker in ROOT_MARKERS) or (child / "dimensions").exists():
            return child
    return extracted


def prepare_base(base: Path, work_parent: Path, preferred_root: str | None = None) -> Path:
    base = base.resolve()
    base_stage = work_parent / "base_extracted"
    if base_stage.exists():
        shutil.rmtree(base_stage)
    base_stage.mkdir(parents=True)
    if base.is_file() and base.suffix.lower() == ".zip":
        safe_extract_zip(base, base_stage)
        root = find_project_root(base_stage, preferred_root)
        project = work_parent / "combined_project"
        copy_tree(root, project)
        return project
    if base.is_dir():
        root = find_project_root(base, preferred_root)
        project = work_parent / "combined_project"
        copy_tree(root, project)
        return project
    raise FileNotFoundError(f"Base path not found or unsupported: {base}")


def zip_list_files(zip_path: Path) -> list[str]:
    with zipfile.ZipFile(zip_path) as zf:
        return [n.replace("\\", "/") for n in zf.namelist() if not n.endswith("/")]


def determine_zip_root_prefix(names: list[str], project_root_name: str | None = None) -> str:
    clean = [n for n in names if n and not n.endswith("/") and not is_junk_path(n)]
    if not clean:
        return ""
    first_parts = [Path(n).parts[0] for n in clean if Path(n).parts]
    if not first_parts:
        return ""
    unique_first = sorted(set(first_parts))
    if project_root_name and project_root_name in unique_first:
        # Common pass zips are HoloCore/main.py while the work dir itself is already HoloCore.
        return project_root_name + "/"
    if len(unique_first) == 1:
        only = unique_first[0]
        # Strip one top folder only when the payload below it looks like a project/patch tree.
        below = ["/".join(Path(n).parts[1:]) for n in clean if len(Path(n).parts) > 1]
        if below and (any(Path(b).parts and Path(b).parts[0] in {"dimensions", "tools", "assets", "data"} for b in below) or any(Path(b).name in ROOT_MARKERS for b in below)):
            return only + "/"
    return ""


def normalized_zip_entries(zip_path: Path, project_root_name: str | None = None) -> dict[str, bytes]:
    names = zip_list_files(zip_path)
    prefix = determine_zip_root_prefix(names, project_root_name)
    entries: dict[str, bytes] = {}
    with zipfile.ZipFile(zip_path) as zf:
        for name in names:
            if is_junk_path(name):
                continue
            rel = name[len(prefix):] if prefix and name.startswith(prefix) else name
            rel = rel.lstrip("/")
            if not rel or rel.endswith("/") or is_junk_path(rel):
                continue
            if rel.startswith("/") or ".." in Path(rel).parts:
                raise ValueError(f"Unsafe normalized path {rel!r} in {zip_path}")
            entries[rel] = zf.read(name)
    return entries


def discover_paired_diff(patch_zip: Path, explicit_diffs: dict[str, Path] | None = None) -> Path | None:
    if explicit_diffs:
        got = explicit_diffs.get(patch_zip.name) or explicit_diffs.get(patch_zip.stem)
        if got:
            return got
    candidates = []
    stem = patch_zip.name
    if stem.endswith("_PATCH_ONLY.zip"):
        candidates.append(patch_zip.with_name(stem.replace("_PATCH_ONLY.zip", ".diff")))
    if stem.endswith(".zip"):
        candidates.append(patch_zip.with_suffix(".diff"))
    candidates.append(patch_zip.with_name(patch_zip.stem + ".diff"))
    for c in candidates:
        if c.exists():
            return c
    return None


def normalize_diff_text(diff_text: str, project_root_name: str | None = None) -> str:
    """Rewrite absolute diff headers to project-relative paths for patch -p0."""
    root_pattern = re.escape(project_root_name) if project_root_name else r"[A-Za-z0-9_. -]+"

    def convert_path(raw: str) -> str:
        raw = raw.strip()
        if raw == "/dev/null":
            return raw
        # Remove optional timestamp by taking path-like first chunk.  Header lines already split before tabs.
        raw = raw.split("\t", 1)[0]
        raw = raw.strip()
        raw = raw.replace("\\", "/")
        if project_root_name:
            marker = f"/{project_root_name}/"
            idx = raw.rfind(marker)
            if idx >= 0:
                return raw[idx + len(marker):]
            marker2 = f"{project_root_name}/"
            idx = raw.find(marker2)
            if idx >= 0:
                return raw[idx + len(marker2):]
        # Generic fallback: find common project subfolders or root files.
        for marker in ["/dimensions/", "/assets/", "/tools/", "/data/", "/ui/", "/runtime.py", "/main.py"]:
            idx = raw.rfind(marker)
            if idx >= 0:
                return raw[idx + 1:]
        p = Path(raw)
        return p.name if p.name else raw

    out: list[str] = []
    for line in diff_text.splitlines(keepends=True):
        if line.startswith("diff -"):
            # The following ---/+++ headers carry the meaningful paths. Keep a harmless marker.
            continue
        if line.startswith("--- ") or line.startswith("+++ "):
            prefix = line[:4]
            rest = line[4:].rstrip("\n")
            path_part = rest.split("\t", 1)[0]
            converted = convert_path(path_part)
            suffix = "\n" if line.endswith("\n") else ""
            out.append(prefix + converted + suffix)
        else:
            out.append(line)
    return "".join(out)


def run_process(
    cmd,
    *,
    cwd: Path | None = None,
    input: str | None = None,
    shell: bool = False,
    timeout_seconds: int = DEFAULT_COMMAND_TIMEOUT_SECONDS,
) -> subprocess.CompletedProcess[str]:
    """Run a subprocess with timeout and process-group cleanup.

    This prevents validators, compile checks, or patch tools from leaving a
    child process holding stdout open forever.
    """
    kwargs = {
        "cwd": cwd,
        "input": input,
        "text": True,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.STDOUT,
        "shell": shell,
    }
    if os.name != "nt":
        kwargs["start_new_session"] = True
    try:
        return subprocess.run(cmd, timeout=timeout_seconds, **kwargs)
    except subprocess.TimeoutExpired as exc:
        # Best effort cleanup of a full process group on POSIX.  On Windows,
        # subprocess.run already kills the direct child for TimeoutExpired.
        if getattr(exc, "process", None) is not None and os.name != "nt":
            try:
                os.killpg(os.getpgid(exc.process.pid), signal.SIGKILL)
            except Exception:
                pass
        output = exc.stdout or ""
        if isinstance(output, bytes):
            output = output.decode("utf-8", errors="replace")
        return subprocess.CompletedProcess(cmd, 124, str(output) + f"\nTIMEOUT after {timeout_seconds}s")


def _run_patch(project_dir: Path, norm: str, dry_run: bool, ignore_whitespace: bool = False, timeout_seconds: int = DEFAULT_COMMAND_TIMEOUT_SECONDS) -> subprocess.CompletedProcess[str]:
    patch_exe = shutil.which("patch")
    if not patch_exe:
        raise FileNotFoundError("patch command not found")
    cmd = [patch_exe, "-p0", "--forward", "--batch"]
    if ignore_whitespace:
        # GNU patch -l loosely matches whitespace.  This rescues many CRLF/LF
        # drift cases without allowing partial writes because we still dry-run.
        cmd.append("-l")
    if dry_run:
        cmd.append("--dry-run")
    return run_process(cmd, input=norm, cwd=project_dir, timeout_seconds=timeout_seconds)


def normalize_touched_files_line_endings(project_dir: Path, paths: Iterable[str]) -> dict[Path, bytes]:
    backups: dict[Path, bytes] = {}
    for rel in paths:
        if rel == "/dev/null":
            continue
        path = project_dir / rel
        if not path.exists() or not path.is_file():
            continue
        try:
            data = path.read_bytes()
        except OSError:
            continue
        if b"\r" not in data:
            continue
        # Only normalize text-like files; skip probable binaries.
        if b"\x00" in data[:4096]:
            continue
        backups[path] = data
        path.write_bytes(data.replace(b"\r\n", b"\n").replace(b"\r", b"\n"))
    return backups


def restore_line_ending_backups(backups: dict[Path, bytes]) -> None:
    for path, data in backups.items():
        try:
            path.write_bytes(data)
        except OSError:
            pass


def apply_diff_with_patch(project_dir: Path, diff_path: Path, project_root_name: str | None, dry_run: bool = False) -> tuple[bool, str, set[str]]:
    diff_text = diff_path.read_text(encoding="utf-8", errors="replace")
    diff_text = diff_text.replace("\r\n", "\n").replace("\r", "\n")
    norm = normalize_diff_text(diff_text, project_root_name)
    changed_paths = extract_paths_from_normalized_diff(norm)
    if not norm.strip():
        return False, "empty normalized diff", set()

    try:
        probe = _run_patch(project_dir, norm, dry_run=True, ignore_whitespace=False)
    except FileNotFoundError as exc:
        return False, f"{exc}; using guarded zip overlay instead", changed_paths

    mode = "normal"
    line_backups: dict[Path, bytes] = {}
    if probe.returncode != 0:
        # First rescue attempt: normalize only the files touched by the diff.
        # This handles CRLF/LF drift without broad project rewrites.  If this
        # does not work, backups are restored before returning failure.
        line_backups = normalize_touched_files_line_endings(project_dir, changed_paths)
        if line_backups:
            probe_norm = _run_patch(project_dir, norm, dry_run=True, ignore_whitespace=False)
            if probe_norm.returncode == 0:
                probe = probe_norm
                mode = "line-ending-normalized"
            else:
                restore_line_ending_backups(line_backups)
                line_backups = {}
        if probe.returncode != 0:
            probe_lax = _run_patch(project_dir, norm, dry_run=True, ignore_whitespace=True)
            if probe_lax.returncode == 0:
                probe = probe_lax
                mode = "whitespace-tolerant"
            else:
                return False, "dry-run failed; diff not applied; normal output: " + probe.stdout.strip()[:1200] + " | whitespace-tolerant output: " + probe_lax.stdout.strip()[:1200], changed_paths

    if dry_run:
        if line_backups:
            restore_line_ending_backups(line_backups)
        return True, f"dry-run would apply ({mode}): " + probe.stdout.strip(), changed_paths

    proc = _run_patch(project_dir, norm, dry_run=False, ignore_whitespace=(mode == "whitespace-tolerant"))
    if proc.returncode == 0:
        return True, f"applied with {mode} patch: " + proc.stdout.strip(), changed_paths
    if line_backups:
        restore_line_ending_backups(line_backups)
    return False, proc.stdout.strip(), changed_paths


def extract_paths_from_normalized_diff(norm: str) -> set[str]:
    paths: set[str] = set()
    for line in norm.splitlines():
        if line.startswith("+++ "):
            path = line[4:].strip()
            if path != "/dev/null":
                paths.add(path)
    return paths


def suspicious_shrink(current: bytes, incoming: bytes, rel_path: str, min_bytes: int, ratio: float) -> bool:
    suffix = Path(rel_path).suffix.lower()
    if suffix not in IMPORTANT_SUFFIXES:
        return False
    old = len(current)
    new = len(incoming)
    if old <= 0 or new >= old:
        return False
    delta = old - new
    if delta >= min_bytes:
        return True
    if new <= old * ratio:
        return True
    return False


def decode_text(data: bytes) -> tuple[str, str]:
    for enc in ("utf-8", "utf-8-sig", "cp1252"):
        try:
            return data.decode(enc), enc
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace"), "utf-8"


def encode_text(text: str, enc: str) -> bytes:
    try:
        return text.encode(enc)
    except Exception:
        return text.encode("utf-8")


def line_span(node: ast.AST) -> tuple[int, int]:
    start = getattr(node, "lineno", None)
    end = getattr(node, "end_lineno", None)
    if start is None or end is None:
        raise ValueError("AST node is missing line span; Python 3.8+ required")
    return int(start), int(end)


def node_key(node: ast.AST) -> tuple[str, str] | None:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return ("function", node.name)
    if isinstance(node, ast.ClassDef):
        return ("class", node.name)
    if isinstance(node, (ast.Assign, ast.AnnAssign)):
        names: list[str] = []
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        for target in targets:
            if isinstance(target, ast.Name):
                names.append(target.id)
        if names:
            return ("assign", ",".join(sorted(names)))
    return None


def class_member_key(node: ast.AST) -> tuple[str, str] | None:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return ("method", node.name)
    if isinstance(node, (ast.Assign, ast.AnnAssign)):
        names: list[str] = []
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        for target in targets:
            if isinstance(target, ast.Name):
                names.append(target.id)
        if names:
            return ("class_assign", ",".join(sorted(names)))
    return None


def get_block(lines: list[str], node: ast.AST) -> list[str]:
    start, end = line_span(node)
    return lines[start - 1:end]


def replace_ranges(lines: list[str], replacements: list[tuple[int, int, list[str]]]) -> list[str]:
    # Ranges are 1-indexed inclusive.
    out = list(lines)
    for start, end, block in sorted(replacements, reverse=True):
        out[start - 1:end] = block
    return out


def merge_imports(current_lines: list[str], incoming_tree: ast.Module, incoming_lines: list[str]) -> tuple[list[str], list[str]]:
    current_text = "".join(current_lines)
    imports_to_add: list[str] = []
    for node in incoming_tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            block = "".join(get_block(incoming_lines, node)).rstrip("\n")
            if block and block not in current_text and block not in imports_to_add:
                imports_to_add.append(block)
    if not imports_to_add:
        return current_lines, []
    # Insert after module docstring and existing import block.
    insert_at = 0
    try:
        cur_tree = ast.parse("".join(current_lines))
        if cur_tree.body and isinstance(cur_tree.body[0], ast.Expr) and isinstance(getattr(cur_tree.body[0], "value", None), ast.Constant) and isinstance(cur_tree.body[0].value.value, str):
            insert_at = getattr(cur_tree.body[0], "end_lineno", 0)
        for node in cur_tree.body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                insert_at = max(insert_at, getattr(node, "end_lineno", insert_at))
    except Exception:
        pass
    addition = [line + "\n" for item in imports_to_add for line in item.splitlines()]
    if addition and (insert_at >= len(current_lines) or current_lines[insert_at:insert_at+1] != ["\n"]):
        addition.append("\n")
    new_lines = current_lines[:insert_at] + addition + current_lines[insert_at:]
    return new_lines, imports_to_add


def merge_class(current_class: ast.ClassDef, incoming_class: ast.ClassDef, current_lines: list[str], incoming_lines: list[str]) -> tuple[list[str], list[str]]:
    notes: list[str] = []
    current_members: dict[tuple[str, str], ast.AST] = {}
    for node in current_class.body:
        key = class_member_key(node)
        if key:
            current_members[key] = node
    replacements: list[tuple[int, int, list[str]]] = []
    additions: list[list[str]] = []
    for node in incoming_class.body:
        key = class_member_key(node)
        if not key:
            continue
        block = get_block(incoming_lines, node)
        if key in current_members:
            s, e = line_span(current_members[key])
            replacements.append((s, e, block))
            notes.append(f"updated {current_class.name}.{key[1]}")
        else:
            additions.append(block)
            notes.append(f"added {current_class.name}.{key[1]}")
    new_lines = replace_ranges(current_lines, replacements)
    if additions:
        # Re-parse after replacements to find the class end in new line numbering.
        new_tree = ast.parse("".join(new_lines))
        new_current_class = next((n for n in new_tree.body if isinstance(n, ast.ClassDef) and n.name == current_class.name), None)
        if new_current_class is not None:
            _, end = line_span(new_current_class)
            insert_lines: list[str] = []
            for block in additions:
                if insert_lines and insert_lines[-1].strip():
                    insert_lines.append("\n")
                insert_lines.extend(block)
            new_lines = new_lines[:end] + insert_lines + new_lines[end:]
    return new_lines, notes


def python_definition_merge(current_data: bytes, incoming_data: bytes, rel_path: str) -> tuple[bytes | None, str]:
    current_text, enc = decode_text(current_data)
    incoming_text, _ = decode_text(incoming_data)
    try:
        current_tree = ast.parse(current_text)
        incoming_tree = ast.parse(incoming_text)
    except SyntaxError as exc:
        return None, f"python parse failed: {exc}"

    current_lines = current_text.splitlines(keepends=True)
    incoming_lines = incoming_text.splitlines(keepends=True)

    current_lines, import_notes = merge_imports(current_lines, incoming_tree, incoming_lines)
    notes: list[str] = [f"added import: {x}" for x in import_notes]

    # Re-parse after import insertion to keep line numbers accurate.
    current_tree = ast.parse("".join(current_lines))
    current_top: dict[tuple[str, str], ast.AST] = {}
    for node in current_tree.body:
        key = node_key(node)
        if key:
            current_top[key] = node

    replacements: list[tuple[int, int, list[str]]] = []
    additions: list[list[str]] = []
    class_merges: list[tuple[ast.ClassDef, ast.ClassDef]] = []

    for node in incoming_tree.body:
        key = node_key(node)
        if key is None or isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        if key[0] == "class" and key in current_top and isinstance(current_top[key], ast.ClassDef) and isinstance(node, ast.ClassDef):
            class_merges.append((current_top[key], node))
            continue
        block = get_block(incoming_lines, node)
        if key in current_top:
            s, e = line_span(current_top[key])
            replacements.append((s, e, block))
            notes.append(f"updated top-level {key[0]} {key[1]}")
        else:
            additions.append(block)
            notes.append(f"added top-level {key[0]} {key[1]}")

    current_lines = replace_ranges(current_lines, replacements)

    # Apply class member merges one by one with reparse for fresh line numbers.
    for _, incoming_class in class_merges:
        tree = ast.parse("".join(current_lines))
        fresh_class = next((n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == incoming_class.name), None)
        if fresh_class is None:
            additions.append(get_block(incoming_lines, incoming_class))
            notes.append(f"added class {incoming_class.name}")
            continue
        current_lines, class_notes = merge_class(fresh_class, incoming_class, current_lines, incoming_lines)
        notes.extend(class_notes)

    if additions:
        if current_lines and current_lines[-1].strip():
            current_lines.append("\n")
        for block in additions:
            if current_lines and current_lines[-1].strip():
                current_lines.append("\n")
            current_lines.extend(block)

    merged_text = "".join(current_lines)
    if merged_text == current_text:
        return None, "definition merge found no transferable changes"
    return encode_text(merged_text, enc), "; ".join(notes[:40])


def is_protected_path(rel_path: str, protected_patterns: Iterable[str]) -> bool:
    rel = rel_path.replace("\\", "/").lstrip("/")
    name = Path(rel).name
    for pat in protected_patterns:
        pat = pat.replace("\\", "/").lstrip("/")
        if fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(name, pat):
            return True
    return False


def write_override_copy(project_dir: Path, override_dir_name: str, patch_name: str, rel_path: str, incoming: bytes) -> Path:
    safe_patch = re.sub(r"[^A-Za-z0-9_.-]+", "_", Path(patch_name).stem)
    rel = rel_path.replace("\\", "/").lstrip("/")
    target = project_dir / override_dir_name / safe_patch / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(incoming)
    return target


def python_additive_merge(current_data: bytes, incoming_data: bytes, rel_path: str) -> tuple[bytes | None, str, bool]:
    """Safely transplant only new imports/top-level definitions/methods.

    Existing functions, classes, methods, and assignments are never replaced.
    The returned bool is True when incoming content also wanted to touch existing
    definitions and should therefore be staged for manual review in overrides.
    """
    current_text, enc = decode_text(current_data)
    incoming_text, _ = decode_text(incoming_data)
    try:
        current_tree = ast.parse(current_text)
        incoming_tree = ast.parse(incoming_text)
    except SyntaxError as exc:
        return None, f"python parse failed: {exc}", True

    current_lines = current_text.splitlines(keepends=True)
    incoming_lines = incoming_text.splitlines(keepends=True)
    notes: list[str] = []
    unresolved = False

    current_lines, import_notes = merge_imports(current_lines, incoming_tree, incoming_lines)
    notes.extend(f"added import: {x}" for x in import_notes)
    current_tree = ast.parse("".join(current_lines))

    current_top: dict[tuple[str, str], ast.AST] = {}
    for node in current_tree.body:
        key = node_key(node)
        if key:
            current_top[key] = node

    additions: list[list[str]] = []
    class_additions: list[tuple[str, list[list[str]]]] = []

    for node in incoming_tree.body:
        key = node_key(node)
        if key is None or isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        block = get_block(incoming_lines, node)
        if key not in current_top:
            additions.append(block)
            notes.append(f"added top-level {key[0]} {key[1]}")
            continue
        if key[0] == "class" and isinstance(current_top[key], ast.ClassDef) and isinstance(node, ast.ClassDef):
            current_members = {class_member_key(m): m for m in current_top[key].body if class_member_key(m)}
            new_member_blocks: list[list[str]] = []
            for member in node.body:
                mkey = class_member_key(member)
                if not mkey:
                    continue
                if mkey in current_members:
                    old_block = "".join(get_block(current_lines, current_members[mkey])).strip()
                    new_block = "".join(get_block(incoming_lines, member)).strip()
                    if old_block != new_block:
                        unresolved = True
                        notes.append(f"blocked existing {node.name}.{mkey[1]}")
                else:
                    new_member_blocks.append(get_block(incoming_lines, member))
                    notes.append(f"added {node.name}.{mkey[1]}")
            if new_member_blocks:
                class_additions.append((node.name, new_member_blocks))
        else:
            old_block = "".join(get_block(current_lines, current_top[key])).strip()
            new_block = "".join(block).strip()
            if old_block != new_block:
                unresolved = True
                notes.append(f"blocked existing top-level {key[0]} {key[1]}")

    if additions:
        if current_lines and current_lines[-1].strip():
            current_lines.append("\n")
        for block in additions:
            if current_lines and current_lines[-1].strip():
                current_lines.append("\n")
            current_lines.extend(block)

    for class_name, member_blocks in class_additions:
        tree = ast.parse("".join(current_lines))
        cls = next((n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name), None)
        if cls is None:
            unresolved = True
            continue
        _, end = line_span(cls)
        insert_lines: list[str] = []
        for block in member_blocks:
            if insert_lines and insert_lines[-1].strip():
                insert_lines.append("\n")
            insert_lines.extend(block)
        current_lines = current_lines[:end] + insert_lines + current_lines[end:]

    merged_text = "".join(current_lines)
    if merged_text == current_text:
        return None, "; ".join(notes[:60]) or "no additive changes", unresolved
    return encode_text(merged_text, enc), "; ".join(notes[:60]), unresolved


def write_conflict_copy(target: Path, incoming: bytes) -> Path:
    base = target.with_name(target.name + ".incoming.CONFLICT")
    candidate = base
    i = 2
    while candidate.exists():
        candidate = target.with_name(target.name + f".incoming.{i}.CONFLICT")
        i += 1
    candidate.write_bytes(incoming)
    return candidate


def apply_zip_entries(
    project_dir: Path,
    patch_zip: Path,
    entries: dict[str, bytes],
    skip_paths: set[str],
    shrink_min_bytes: int,
    shrink_ratio: float,
    allow_shrink_overwrite: bool,
    dry_run: bool,
    protected_patterns: list[str],
    strict_protected: bool,
    allow_protected_overwrite: bool,
    stage_overrides: bool,
    override_dir_name: str,
    diff_failed: bool,
    diff_touched_paths: set[str],
    small_updates_to_overrides: bool = False,
    small_update_max_bytes: int = 32768,
) -> list[FileAction]:
    actions: list[FileAction] = []

    def stage_override(rel_path: str, incoming_data: bytes, action: str, detail: str, old_size: int, new_size: int | None = None) -> FileAction:
        override_detail = detail
        if stage_overrides:
            if not dry_run:
                override = write_override_copy(project_dir, override_dir_name, patch_zip.name, rel_path, incoming_data)
                override_detail += f"; staged override at {override.relative_to(project_dir).as_posix()}"
            else:
                safe_patch = re.sub(r"[^A-Za-z0-9_.-]+", "_", Path(patch_zip.name).stem)
                override_detail += f"; would stage override at {override_dir_name}/{safe_patch}/{rel_path}"
        else:
            override_detail += "; override staging disabled"
        return FileAction(patch_zip.name, rel_path, action, override_detail, old_size=old_size, new_size=new_size if new_size is not None else old_size, incoming_size=len(incoming_data))

    for rel, incoming in sorted(entries.items()):
        rel = rel.replace("\\", "/")
        if rel in skip_paths:
            actions.append(FileAction(patch_zip.name, rel, "zip-skip-diff-applied", "path was already handled by paired diff"))
            continue
        target = project_dir / rel
        old = target.read_bytes() if target.exists() else b""
        protected = is_protected_path(rel, protected_patterns)
        diff_failed_for_path = diff_failed and (not diff_touched_paths or rel in diff_touched_paths)

        if target.exists() and sha256_bytes(old) == sha256_bytes(incoming):
            actions.append(FileAction(patch_zip.name, rel, "skip-identical", old_size=len(old), incoming_size=len(incoming)))
            continue

        # Optional conservative workflow: small existing-file updates can be
        # preserved as drop-in override candidates rather than applied.  This is
        # useful for UI text/data/config snippets or partial hand-authored files
        # when the user wants reviewable drop-ins instead of direct replacement.
        if (
            small_updates_to_overrides
            and target.exists()
            and not protected
            and len(incoming) <= small_update_max_bytes
            and Path(rel).suffix.lower() in IMPORTANT_SUFFIXES
        ):
            actions.append(stage_override(
                rel,
                incoming,
                "small-update-override-staged",
                f"small update staged as drop-in candidate; use manual review to promote",
                len(old),
            ))
            continue

        if not target.exists():
            actions.append(FileAction(patch_zip.name, rel, "add", old_size=0, new_size=len(incoming), incoming_size=len(incoming)))
            if not dry_run:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(incoming)
            continue

        # Protected files are the regression danger zone.  If a paired diff failed,
        # or if strict mode is on and no diff handled this file, never full-overwrite
        # them unless the caller explicitly opted in.
        if protected and strict_protected and not allow_protected_overwrite:
            should_guard = diff_failed_for_path or rel not in skip_paths
            if should_guard:
                if Path(rel).suffix.lower() == ".py":
                    merged, detail, unresolved = python_additive_merge(old, incoming, rel)
                    if merged is not None:
                        action = "python-additive-merge"
                        if unresolved:
                            action = "python-additive-merge-with-override"
                            if stage_overrides and not dry_run:
                                override = write_override_copy(project_dir, override_dir_name, patch_zip.name, rel, incoming)
                                detail += f"; unresolved incoming changes staged at {override.relative_to(project_dir).as_posix()}"
                            elif stage_overrides:
                                safe_patch = re.sub(r"[^A-Za-z0-9_.-]+", "_", Path(patch_zip.name).stem)
                                detail += f"; unresolved incoming changes would be staged at {override_dir_name}/{safe_patch}/{rel}"
                        actions.append(FileAction(patch_zip.name, rel, action, detail, old_size=len(old), new_size=len(merged), incoming_size=len(incoming)))
                        if not dry_run:
                            target.write_bytes(merged)
                        continue
                reason = "protected file blocked from blind overwrite"
                if diff_failed_for_path:
                    reason += " after paired diff failed"
                actions.append(stage_override(rel, incoming, "protected-override-staged", reason, len(old)))
                if not dry_run and not stage_overrides:
                    write_conflict_copy(target, incoming)
                continue

        if suspicious_shrink(old, incoming, rel, shrink_min_bytes, shrink_ratio) and not allow_shrink_overwrite:
            if Path(rel).suffix.lower() == ".py":
                if protected:
                    merged, detail, unresolved = python_additive_merge(old, incoming, rel)
                    merge_action = "python-additive-merge-shrink"
                else:
                    merged_def, detail_def = python_definition_merge(old, incoming, rel)
                    merged, detail, unresolved = merged_def, detail_def, False
                    merge_action = "python-definition-merge"
                if merged is not None:
                    if unresolved and stage_overrides:
                        if not dry_run:
                            override = write_override_copy(project_dir, override_dir_name, patch_zip.name, rel, incoming)
                            detail += f"; unresolved incoming changes staged at {override.relative_to(project_dir).as_posix()}"
                        else:
                            safe_patch = re.sub(r"[^A-Za-z0-9_.-]+", "_", Path(patch_zip.name).stem)
                            detail += f"; unresolved incoming changes would be staged at {override_dir_name}/{safe_patch}/{rel}"
                        merge_action += "-with-override"
                    actions.append(FileAction(patch_zip.name, rel, merge_action, detail, old_size=len(old), new_size=len(merged), incoming_size=len(incoming)))
                    if not dry_run:
                        target.write_bytes(merged)
                    continue
            conflict_path = target.with_name(target.name + ".incoming.CONFLICT")
            detail = f"incoming saved as {conflict_path.name}; use --allow-shrink-overwrite only after review"
            if stage_overrides:
                if not dry_run:
                    override = write_override_copy(project_dir, override_dir_name, patch_zip.name, rel, incoming)
                    detail += f"; staged override at {override.relative_to(project_dir).as_posix()}"
                else:
                    safe_patch = re.sub(r"[^A-Za-z0-9_.-]+", "_", Path(patch_zip.name).stem)
                    detail += f"; would stage override at {override_dir_name}/{safe_patch}/{rel}"
            actions.append(FileAction(patch_zip.name, rel, "conflict-suspicious-shrink", detail, old_size=len(old), new_size=len(old), incoming_size=len(incoming)))
            if not dry_run:
                write_conflict_copy(target, incoming)
            continue

        action = "overwrite"
        if len(incoming) < len(old):
            action = "overwrite-smaller-reviewed"
        actions.append(FileAction(patch_zip.name, rel, action, old_size=len(old), new_size=len(incoming), incoming_size=len(incoming)))
        if not dry_run:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(incoming)
    return actions



def _is_text_like_path(path: str) -> bool:
    return Path(path).suffix.lower() in TEXT_DIFF_SUFFIXES


def read_text_or_none(path: Path) -> str | None:
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if b"\x00" in data[:4096]:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("utf-8", errors="replace")


def iter_clean_files(root: Path, include_overrides: bool = False):
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        if not include_overrides and rel.startswith("_pass_overrides/"):
            continue
        if is_junk_path(rel) or rel.endswith(".incoming.CONFLICT"):
            continue
        yield rel, path


def create_delta_outputs(
    before_dir: Path,
    after_dir: Path,
    patch_zip: Path | None = None,
    diff_path: Path | None = None,
    root_folder: str | None = None,
    deletion_manifest_name: str = "PATCH_DELETIONS.json",
) -> dict[str, object]:
    """Create repo-friendly patch-only zip and unified diff from before/after dirs."""
    before_files = {rel: path for rel, path in iter_clean_files(before_dir)}
    after_files = {rel: path for rel, path in iter_clean_files(after_dir)}
    added: list[str] = []
    modified: list[str] = []
    deleted: list[str] = []
    for rel, after_path in after_files.items():
        before_path = before_files.get(rel)
        if before_path is None:
            added.append(rel)
        elif sha256_bytes(before_path.read_bytes()) != sha256_bytes(after_path.read_bytes()):
            modified.append(rel)
    for rel in before_files:
        if rel not in after_files:
            deleted.append(rel)

    if patch_zip:
        patch_zip.parent.mkdir(parents=True, exist_ok=True)
        if patch_zip.exists():
            patch_zip.unlink()
        with zipfile.ZipFile(patch_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for rel in sorted(added + modified):
                arc = f"{root_folder}/{rel}" if root_folder else rel
                zf.write(after_dir / rel, arc)
            if deleted:
                payload = json.dumps({"delete": sorted(deleted)}, indent=2).encode("utf-8")
                arc = f"{root_folder}/{deletion_manifest_name}" if root_folder else deletion_manifest_name
                zf.writestr(arc, payload)

    binary_or_omitted: list[str] = []
    if diff_path:
        diff_path.parent.mkdir(parents=True, exist_ok=True)
        lines: list[str] = []
        for rel in sorted(added + modified + deleted):
            before_path = before_dir / rel
            after_path = after_dir / rel
            before_text = read_text_or_none(before_path) if before_path.exists() else ""
            after_text = read_text_or_none(after_path) if after_path.exists() else ""
            if before_text is None or after_text is None or not _is_text_like_path(rel):
                binary_or_omitted.append(rel)
                continue
            a_name = f"a/{rel}" if before_path.exists() else "/dev/null"
            b_name = f"b/{rel}" if after_path.exists() else "/dev/null"
            before_lines = before_text.splitlines(keepends=True)
            after_lines = after_text.splitlines(keepends=True)
            lines.extend(difflib.unified_diff(before_lines, after_lines, fromfile=a_name, tofile=b_name, lineterm=""))
            if lines and not lines[-1].endswith("\n"):
                lines[-1] += "\n"
        if binary_or_omitted:
            lines.append("\n# Binary or non-text files omitted from unified diff:\n")
            for rel in binary_or_omitted:
                lines.append(f"#   {rel}\n")
        diff_path.write_text("".join(lines), encoding="utf-8")

    return {
        "added": sorted(added),
        "modified": sorted(modified),
        "deleted": sorted(deleted),
        "patch_zip": str(patch_zip) if patch_zip else None,
        "diff": str(diff_path) if diff_path else None,
        "binary_or_omitted_from_diff": sorted(binary_or_omitted),
    }


def python_symbol_manifest(root: Path, protected_patterns: list[str]) -> dict[str, dict[str, list[str]]]:
    manifest: dict[str, dict[str, list[str]]] = {}
    for rel, path in iter_clean_files(root):
        if Path(rel).suffix.lower() != ".py":
            continue
        if protected_patterns and not is_protected_path(rel, protected_patterns):
            continue
        text = read_text_or_none(path)
        if text is None:
            continue
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        funcs: list[str] = []
        classes: list[str] = []
        methods: list[str] = []
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                funcs.append(node.name)
            elif isinstance(node, ast.ClassDef):
                classes.append(node.name)
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        methods.append(f"{node.name}.{item.name}")
        manifest[rel] = {
            "functions": sorted(set(funcs)),
            "classes": sorted(set(classes)),
            "methods": sorted(set(methods)),
        }
    return manifest


def compare_symbol_manifests(before: dict[str, dict[str, list[str]]], after: dict[str, dict[str, list[str]]]) -> dict[str, dict[str, list[str]]]:
    changes: dict[str, dict[str, list[str]]] = {}
    for rel, old_sets in before.items():
        new_sets = after.get(rel, {"functions": [], "classes": [], "methods": []})
        removed: dict[str, list[str]] = {}
        for key in ("functions", "classes", "methods"):
            lost = sorted(set(old_sets.get(key, [])) - set(new_sets.get(key, [])))
            if lost:
                removed[f"removed_{key}"] = lost
        if removed:
            changes[rel] = removed
    return changes


def scan_banned_text(root: Path, banned_terms: list[str]) -> list[dict[str, object]]:
    hits: list[dict[str, object]] = []
    if not banned_terms:
        return hits
    for rel, path in iter_clean_files(root):
        if not _is_text_like_path(rel):
            continue
        text = read_text_or_none(path)
        if text is None:
            continue
        for term in banned_terms:
            idx = text.find(term)
            if idx >= 0:
                line = text.count("\n", 0, idx) + 1
                hits.append({"path": rel, "term": term, "line": line})
    return hits


def write_repo_handoff(report_dir: Path, repo_name: str | None, delta: dict[str, object] | None, final_status: str, final_reasons: list[str]) -> Path:
    path = report_dir / "repo_patch_handoff.md"
    lines = ["# Repo patch handoff\n\n"]
    if repo_name:
        lines.append(f"Repository: `{repo_name}`\n\n")
    lines.append(f"Final status: `{final_status}`\n\n")
    if final_reasons:
        lines.append("Review/failure reasons:\n")
        for reason in final_reasons:
            lines.append(f"- {reason}\n")
        lines.append("\n")
    if delta:
        lines.append("## Delta summary\n\n")
        for key in ("added", "modified", "deleted"):
            vals = list(delta.get(key, []) or [])
            lines.append(f"- `{key}`: {len(vals)}\n")
        lines.append("\nPatch-only zip: `{}`\n\n".format(delta.get("patch_zip") or "not written"))
        lines.append("Unified diff: `{}`\n\n".format(delta.get("diff") or "not written"))
        if delta.get("deleted"):
            lines.append("Deletions are recorded in `PATCH_DELETIONS.json` inside the patch zip; review before applying.\n\n")
    lines.append("## Suggested local workflow\n\n")
    lines.append("```powershell\n")
    lines.append("git checkout -b pass-combiner-review\n")
    lines.append("# unzip the patch-only zip over the repo, then review:\n")
    lines.append("git status\n")
    lines.append("git diff --stat\n")
    lines.append("git diff\n")
    lines.append("# run validators listed in pass_combiner_report.md before committing\n")
    lines.append("```\n")
    path.write_text("".join(lines), encoding="utf-8")
    return path


def load_order_file(path: Path) -> list[Path]:
    paths: list[Path] = []
    base_dir = path.parent
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        p = Path(line)
        if not p.is_absolute():
            p = base_dir / p
        paths.append(p)
    return paths


def cleanup_junk_tree(root: Path) -> None:
    for path in sorted(root.rglob("*"), reverse=True):
        try:
            if path.is_file() and (path.suffix.lower() in {".pyc", ".pyo"} or path.name.endswith((".rej", ".orig"))):
                path.unlink()
            elif path.is_dir() and path.name in {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}:
                shutil.rmtree(path)
        except OSError:
            pass


def make_zip_from_dir(src_dir: Path, out_zip: Path, root_folder: str | None = None) -> None:
    out_zip.parent.mkdir(parents=True, exist_ok=True)
    if out_zip.exists():
        out_zip.unlink()
    with zipfile.ZipFile(out_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(src_dir.rglob("*")):
            if path.is_dir():
                continue
            rel = path.relative_to(src_dir).as_posix()
            if is_junk_path(rel) or rel.endswith(".incoming.CONFLICT"):
                continue
            arc = f"{root_folder}/{rel}" if root_folder else rel
            zf.write(path, arc)


def compile_project(project_dir: Path, timeout_seconds: int = DEFAULT_COMMAND_TIMEOUT_SECONDS) -> tuple[bool, str]:
    exclude = r"(^|/|\\)(_pass_overrides|__pycache__|logs|crash_reports)(/|\\|$)"
    proc = run_process([sys.executable, "-m", "compileall", "-q", "-x", exclude, str(project_dir)], timeout_seconds=timeout_seconds)
    cleanup_junk_tree(project_dir)
    return proc.returncode == 0, proc.stdout.strip()


def run_validators(project_dir: Path, commands: list[str], timeout_seconds: int = DEFAULT_COMMAND_TIMEOUT_SECONDS) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    for command in commands:
        proc = run_process(command, shell=True, cwd=project_dir, timeout_seconds=timeout_seconds)
        results.append({
            "command": command,
            "passed": proc.returncode == 0,
            "returncode": proc.returncode,
            "output": proc.stdout.strip(),
        })
    return results


def build_file_manifest(root: Path, include_overrides: bool = True) -> list[dict[str, object]]:
    """Return a deterministic manifest of project files for review reports."""
    rows: list[dict[str, object]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        if is_junk_path(rel) or rel.endswith(".incoming.CONFLICT"):
            continue
        if not include_overrides and rel.startswith("_pass_overrides/"):
            continue
        try:
            data = path.read_bytes()
        except OSError:
            continue
        rows.append({"path": rel, "size": len(data), "sha256": sha256_bytes(data)})
    return rows


def write_file_manifest(report_dir: Path, project_dir: Path) -> Path:
    manifest_path = report_dir / "combined_file_manifest.json"
    manifest_path.write_text(json.dumps(build_file_manifest(project_dir), indent=2), encoding="utf-8")
    return manifest_path


def classify_final_status(
    results: list[PatchResult],
    compile_status: tuple[bool, str] | None,
    validator_statuses: list[dict[str, object]],
    fail_on_diff_failure: bool,
) -> tuple[str, list[str]]:
    reasons: list[str] = []
    conflict_count = sum(1 for r in results for a in r.actions if "conflict" in a.action)
    override_count = sum(1 for r in results for a in r.actions if "override" in a.action)
    diff_fail_count = sum(1 for r in results if str(r.diff_status).startswith("failed"))
    validator_fail_count = sum(1 for v in validator_statuses if not v.get("passed"))
    regression_count = sum(1 for r in results for a in r.actions if "regression" in a.action or "banned-text" in a.action)
    if compile_status is not None and not compile_status[0]:
        reasons.append("compileall failed")
    if validator_fail_count:
        reasons.append(f"{validator_fail_count} validator(s) failed")
    if regression_count:
        reasons.append(f"{regression_count} regression check(s) failed")
    if conflict_count:
        reasons.append(f"{conflict_count} conflict file(s) require review")
    if override_count:
        reasons.append(f"{override_count} override candidate(s) require review")
    if fail_on_diff_failure and diff_fail_count:
        reasons.append(f"{diff_fail_count} paired diff(s) failed")
    if not reasons:
        return "clean", []
    hard = any("failed" in r for r in reasons) or any("validator" in r for r in reasons)
    return ("failed" if hard else "review_required"), reasons


def write_report(out_dir: Path, project_dir: Path, results: list[PatchResult], compile_status: tuple[bool, str] | None, validator_statuses: list[dict[str, object]] | None, dry_run: bool, protected_patterns: list[str], override_dir_name: str, final_status: str = "unknown", final_reasons: list[str] | None = None, zip_written: str | None = None) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    report_json = out_dir / "pass_combiner_report.json"
    report_md = out_dir / "pass_combiner_report.md"
    data = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "dry_run": dry_run,
        "project_dir": str(project_dir),
        "compile_status": None if compile_status is None else {"passed": compile_status[0], "output": compile_status[1]},
        "validator_statuses": validator_statuses or [],
        "protected_patterns": protected_patterns,
        "override_dir_name": override_dir_name,
        "final_status": final_status,
        "final_reasons": final_reasons or [],
        "zip_written": zip_written,
        "patches": [
            {
                "patch": r.patch,
                "diff": r.diff,
                "diff_status": r.diff_status,
                "actions": [asdict(a) for a in r.actions],
            }
            for r in results
        ],
    }
    report_json.write_text(json.dumps(data, indent=2), encoding="utf-8")

    counts: dict[str, int] = {}
    for r in results:
        for a in r.actions:
            counts[a.action] = counts.get(a.action, 0) + 1
    conflicts = [a for r in results for a in r.actions if "conflict" in a.action]
    overrides = [a for r in results for a in r.actions if "override" in a.action]
    suspicious = [a for r in results for a in r.actions if a.action in {"python-definition-merge", "python-additive-merge", "python-additive-merge-with-override", "python-additive-merge-shrink", "python-additive-merge-shrink-with-override", "conflict-suspicious-shrink", "overwrite-smaller-reviewed", "protected-override-staged"}]

    lines: list[str] = []
    lines.append("# Pass Combiner Report\n")
    lines.append(f"Generated: `{data['generated_at']}`\n")
    lines.append(f"Dry run: `{dry_run}`\n")
    lines.append(f"Final status: `{final_status}`\n")
    if final_reasons:
        for reason in final_reasons:
            lines.append(f"- `{reason}`\n")
    if zip_written:
        lines.append(f"Zip written: `{zip_written}`\n")
    else:
        lines.append("Zip written: `no`\n")
    lines.append("## Summary\n")
    for key in sorted(counts):
        lines.append(f"- `{key}`: {counts[key]}\n")
    if compile_status is not None:
        lines.append(f"- `compileall`: {'passed' if compile_status[0] else 'FAILED'}\n")
        if compile_status[1]:
            lines.append("\n```text\n" + compile_status[1][:4000] + "\n```\n")
    if validator_statuses:
        passed_count = sum(1 for v in validator_statuses if v.get("passed"))
        lines.append(f"- `validators`: {passed_count}/{len(validator_statuses)} passed\n")
    if overrides:
        lines.append(f"- `override_staged`: {len(overrides)} candidate files in `{override_dir_name}`\n")
    lines.append("\n## Protected patterns\n")
    for pat in protected_patterns:
        lines.append(f"- `{pat}`\n")
    if validator_statuses:
        lines.append("\n## Validators\n")
        for v in validator_statuses:
            status = "passed" if v.get("passed") else "FAILED"
            lines.append(f"- `{status}` `{v.get('command')}` rc={v.get('returncode')}\n")
            output = str(v.get("output") or "")
            if output:
                lines.append("\n```text\n" + output[:3000] + "\n```\n")
    lines.append("\n## Important review items\n")
    if not suspicious:
        lines.append("\nNo suspicious smaller overwrites were accepted silently.\n")
    else:
        for a in suspicious:
            lines.append(f"- `{a.action}` `{a.path}` from `{a.patch}` old={a.old_size} incoming={a.incoming_size} new={a.new_size}: {a.detail}\n")
    lines.append("\n## Patch details\n")
    for r in results:
        lines.append(f"\n### {r.patch}\n")
        lines.append(f"Diff: `{r.diff or 'none'}` — {r.diff_status}\n")
        for a in r.actions:
            lines.append(f"- `{a.action}` `{a.path}`")
            if a.old_size is not None or a.incoming_size is not None or a.new_size is not None:
                lines.append(f" old={a.old_size} incoming={a.incoming_size} new={a.new_size}")
            if a.detail:
                lines.append(f" — {a.detail}")
            lines.append("\n")
    report_md.write_text("".join(lines), encoding="utf-8")
    return report_json, report_md


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Combine iterative patch zips while guarding against partial-file overwrites.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent(
            """
            Examples:
              python pass_combiner.py --base HoloCore.zip --patches pass1.zip pass2.zip --output-dir combined --output-zip HoloCore_combined.zip
              python pass_combiner.py --base HoloCore.zip --order-file holocore_pass_order.txt --output-dir combined --report-dir reports
              python pass_combiner.py --base ./HoloCore --patch-glob "HoloCore_PASS_*_PATCH_ONLY.zip" --dry-run
            """
        ),
    )
    p.add_argument("--profile", choices=sorted(BUILTIN_PROFILES), default="generic", help="Built-in project profile for protected patterns, validators, and review rules")
    p.add_argument("--use-profile-validators", action="store_true", help="Append validators from the selected --profile")
    p.add_argument("--base", required=True, help="Base project directory or .zip")
    p.add_argument("--patches", nargs="*", default=[], help="Patch-only zip files in application order")
    p.add_argument("--patch-glob", help="Glob for patch zips. Sorted alphabetically; prefer --order-file for real pass chains")
    p.add_argument("--order-file", help="Text file listing patch zips in exact application order")
    p.add_argument("--project-root-name", help="Optional top-level project folder name to strip from patch zips, e.g. HoloCore")
    p.add_argument("--output-dir", default="combined_project", help="Directory to write combined project")
    p.add_argument("--output-zip", help="Optional final combined zip output")
    p.add_argument("--report-dir", default="pass_combiner_reports", help="Directory for JSON/Markdown reports")
    p.add_argument("--dry-run", action="store_true", help="Report actions without writing project changes")
    p.add_argument("--allow-shrink-overwrite", action="store_true", help="Allow suspicious smaller important files to overwrite current files")
    p.add_argument("--strict-protected", dest="strict_protected", action="store_true", default=True, help="Guard protected files from blind overwrite. Enabled by default")
    p.add_argument("--relaxed-protected", dest="strict_protected", action="store_false", help="Allow old v1 behavior for protected files. Not recommended for final builds")
    p.add_argument("--allow-protected-overwrite", action="store_true", help="Permit direct overwrite of protected files when no diff applied. Not recommended")
    p.add_argument("--protected-pattern", action="append", default=[], help="Extra fnmatch pattern for protected files, e.g. 'data/routes/*.json'")
    p.add_argument("--override-dir-name", default="_pass_overrides", help="Folder inside output project for blocked drop-in candidate files")
    p.add_argument("--no-overrides", action="store_true", help="Do not stage blocked candidate files in the override folder")
    p.add_argument("--small-updates-to-overrides", action="store_true", help="Stage small existing-file updates in the override folder instead of applying them directly")
    p.add_argument("--small-update-max-bytes", type=int, default=32768, help="Max incoming byte size treated as a small drop-in override candidate")
    p.add_argument("--fail-on-diff-failure", action="store_true", help="Return failure if any paired diff fails, even if guarded zip overlay succeeds")
    p.add_argument("--write-zip-on-failure", action="store_true", help="Still write output zip when conflicts, overrides, compile, validator, or diff failures are present. Not recommended")
    p.add_argument("--emit-file-manifest", action="store_true", help="Write a final file manifest with sizes and sha256 hashes")
    p.add_argument("--output-patch-zip", help="Optional patch-only zip containing only files changed relative to the base input")
    p.add_argument("--output-diff", help="Optional unified diff containing text changes relative to the base input")
    p.add_argument("--repo-name", help="Optional GitHub repository name for repo_patch_handoff.md, e.g. GLITCHEDMATR1X/GX-Prototype-Lab")
    p.add_argument("--emit-repo-handoff", action="store_true", help="Write a repo_patch_handoff.md with review/PR workflow notes")
    p.add_argument("--emit-symbol-manifest", action="store_true", help="Write before/after protected Python symbol manifests")
    p.add_argument("--fail-on-symbol-removal", action="store_true", help="Fail/review if protected Python functions/classes/methods disappear from the combined output")
    p.add_argument("--banned-text", action="append", default=[], help="Text term that must not appear in final text files; repeatable")
    p.add_argument("--fail-on-banned-text", action="store_true", help="Fail/review if banned text appears in final text files")
    p.add_argument("--validate", action="append", default=[], help="Validator command to run after combine; repeatable. Runs from project root")
    p.add_argument("--allow-validator-failure", action="store_true", help="Do not return failure when a validator command fails")
    p.add_argument("--shrink-min-bytes", type=int, default=4096, help="Byte drop that triggers shrink guard")
    p.add_argument("--shrink-ratio", type=float, default=0.90, help="Incoming/current ratio below this triggers shrink guard")
    p.add_argument("--compileall", action="store_true", help="Run python -m compileall after combining")
    p.add_argument("--command-timeout", type=int, default=DEFAULT_COMMAND_TIMEOUT_SECONDS, help="Seconds before patch/compile/validator commands are treated as timed out")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    base = Path(args.base)
    patch_paths: list[Path] = []
    if args.order_file:
        patch_paths.extend(load_order_file(Path(args.order_file)))
    if args.patch_glob:
        patch_paths.extend(sorted(Path().glob(args.patch_glob)))
    patch_paths.extend(Path(p) for p in args.patches)
    if not patch_paths:
        print("No patch zips supplied. Use --patches, --patch-glob, or --order-file.", file=sys.stderr)
        return 2
    missing = [str(p) for p in patch_paths if not p.exists()]
    if missing:
        print("Missing patch files:\n" + "\n".join(missing), file=sys.stderr)
        return 2

    output_dir = Path(args.output_dir).resolve()
    report_dir = Path(args.report_dir).resolve()
    work_parent = output_dir.parent / (output_dir.name + "__work")
    if work_parent.exists():
        shutil.rmtree(work_parent)
    work_parent.mkdir(parents=True)

    project_dir = prepare_base(base, work_parent, args.project_root_name)
    # Move/copy work project to final output location for stable paths.
    if output_dir.exists():
        shutil.rmtree(output_dir)
    shutil.move(str(project_dir), str(output_dir))
    project_dir = output_dir
    project_root_name = args.project_root_name or (Path(args.base).stem if base.is_file() else project_dir.name)

    baseline_dir = work_parent / "baseline_project_snapshot"
    if baseline_dir.exists():
        shutil.rmtree(baseline_dir)
    copy_tree(project_dir, baseline_dir)

    profile = BUILTIN_PROFILES.get(args.profile, BUILTIN_PROFILES["generic"])
    protected_patterns = list(DEFAULT_PROTECTED_PATTERNS) + list(profile.get("protected_patterns", [])) + list(args.protected_pattern or [])
    profile_validators = list(profile.get("validators", [])) if args.use_profile_validators else []
    validator_commands = profile_validators + list(args.validate or [])
    banned_terms = list(profile.get("banned_text", [])) + list(args.banned_text or [])

    before_symbols = python_symbol_manifest(baseline_dir, protected_patterns) if (args.emit_symbol_manifest or args.fail_on_symbol_removal) else {}

    results: list[PatchResult] = []
    for patch_zip in patch_paths:
        patch_zip = patch_zip.resolve()
        entries = normalized_zip_entries(patch_zip, project_root_name)
        paired_diff = discover_paired_diff(patch_zip)
        diff_status = "not used"
        diff_paths: set[str] = set()
        diff_touched_paths: set[str] = set()
        diff_failed = False
        if paired_diff is not None:
            ok, detail, paths = apply_diff_with_patch(project_dir, paired_diff, project_root_name, dry_run=args.dry_run)
            diff_touched_paths = paths
            diff_paths = paths if ok else set()
            diff_failed = not ok
            diff_status = ("applied" if ok else "failed") + (f": {detail[:1000]}" if detail else "")
        actions = apply_zip_entries(
            project_dir,
            patch_zip,
            entries,
            skip_paths=diff_paths,
            shrink_min_bytes=args.shrink_min_bytes,
            shrink_ratio=args.shrink_ratio,
            allow_shrink_overwrite=args.allow_shrink_overwrite,
            dry_run=args.dry_run,
            protected_patterns=protected_patterns,
            strict_protected=args.strict_protected,
            allow_protected_overwrite=args.allow_protected_overwrite,
            stage_overrides=not args.no_overrides,
            override_dir_name=args.override_dir_name,
            diff_failed=diff_failed,
            diff_touched_paths=diff_touched_paths,
            small_updates_to_overrides=args.small_updates_to_overrides,
            small_update_max_bytes=args.small_update_max_bytes,
        )
        results.append(PatchResult(patch_zip.name, str(paired_diff) if paired_diff else None, diff_status, actions))

    compile_status = compile_project(project_dir, args.command_timeout) if args.compileall and not args.dry_run else None
    validator_statuses = run_validators(project_dir, validator_commands, args.command_timeout) if validator_commands and not args.dry_run else []

    if not args.dry_run and (args.emit_symbol_manifest or args.fail_on_symbol_removal):
        after_symbols = python_symbol_manifest(project_dir, protected_patterns)
        symbol_changes = compare_symbol_manifests(before_symbols, after_symbols)
        report_dir.mkdir(parents=True, exist_ok=True)
        (report_dir / "symbol_manifest_before.json").write_text(json.dumps(before_symbols, indent=2), encoding="utf-8")
        (report_dir / "symbol_manifest_after.json").write_text(json.dumps(after_symbols, indent=2), encoding="utf-8")
        (report_dir / "symbol_regressions.json").write_text(json.dumps(symbol_changes, indent=2), encoding="utf-8")
        if args.fail_on_symbol_removal and symbol_changes:
            actions = []
            for rel, changes in sorted(symbol_changes.items()):
                detail = json.dumps(changes, sort_keys=True)
                actions.append(FileAction("symbol-regression-check", rel, "symbol-regression", detail))
            results.append(PatchResult("_regression_checks", None, "symbol regression check", actions))

    if not args.dry_run and (args.fail_on_banned_text or banned_terms):
        banned_hits = scan_banned_text(project_dir, banned_terms)
        if banned_hits:
            report_dir.mkdir(parents=True, exist_ok=True)
            (report_dir / "banned_text_hits.json").write_text(json.dumps(banned_hits, indent=2), encoding="utf-8")
        if args.fail_on_banned_text and banned_hits:
            actions = [FileAction("banned-text-check", str(hit["path"]), "banned-text-hit", f"{hit['term']!r} at line {hit['line']}") for hit in banned_hits]
            results.append(PatchResult("_regression_checks", None, "banned text check", actions))

    final_status, final_reasons = classify_final_status(results, compile_status, validator_statuses, args.fail_on_diff_failure)

    if not args.dry_run:
        cleanup_junk_tree(project_dir)

    zip_written: str | None = None
    delta_written: dict[str, object] | None = None
    should_write_zip = bool(args.output_zip and not args.dry_run and (final_status == "clean" or args.write_zip_on_failure or args.allow_validator_failure))
    # Validator failures are still blocked by default even if allow_validator_failure is false.
    if args.output_zip and not args.dry_run and final_status != "clean" and not (args.write_zip_on_failure or args.allow_validator_failure):
        zip_written = None
    elif should_write_zip:
        root_name = args.project_root_name or project_dir.name
        out_zip = Path(args.output_zip).resolve()
        make_zip_from_dir(project_dir, out_zip, root_folder=root_name)
        zip_written = str(out_zip)

    if not args.dry_run and (args.output_patch_zip or args.output_diff):
        if final_status == "clean" or args.write_zip_on_failure:
            root_name = args.project_root_name or project_dir.name
            delta_written = create_delta_outputs(
                baseline_dir,
                project_dir,
                Path(args.output_patch_zip).resolve() if args.output_patch_zip else None,
                Path(args.output_diff).resolve() if args.output_diff else None,
                root_folder=root_name,
            )
            report_dir.mkdir(parents=True, exist_ok=True)
            (report_dir / "repo_delta_summary.json").write_text(json.dumps(delta_written, indent=2), encoding="utf-8")
        else:
            delta_written = {"blocked": True, "reason": "review/failure state present; use --write-zip-on-failure only after review"}

    report_json, report_md = write_report(report_dir, project_dir, results, compile_status, validator_statuses, args.dry_run, protected_patterns, args.override_dir_name, final_status, final_reasons, zip_written)
    if args.emit_file_manifest and not args.dry_run:
        write_file_manifest(report_dir, project_dir)
    if args.emit_repo_handoff and not args.dry_run:
        write_repo_handoff(report_dir, args.repo_name, delta_written, final_status, final_reasons)

    conflict_count = sum(1 for r in results for a in r.actions if "conflict" in a.action)
    override_count = sum(1 for r in results for a in r.actions if "override" in a.action)
    diff_fail_count = sum(1 for r in results if str(r.diff_status).startswith("failed"))
    validator_fail_count = sum(1 for v in validator_statuses if not v.get("passed"))
    regression_count = sum(1 for r in results for a in r.actions if "regression" in a.action or "banned-text" in a.action)
    print(f"Combined project: {project_dir}")
    if zip_written:
        print(f"Combined zip: {zip_written}")
    elif args.output_zip and not args.dry_run:
        print("Combined zip: not written because review/failure state is present", file=sys.stderr)
    if delta_written and not delta_written.get("blocked"):
        if delta_written.get("patch_zip"):
            print(f"Patch-only delta zip: {delta_written.get('patch_zip')}")
        if delta_written.get("diff"):
            print(f"Unified delta diff: {delta_written.get('diff')}")
    elif delta_written and delta_written.get("blocked"):
        print("Patch-only delta outputs: blocked because review/failure state is present", file=sys.stderr)
    print(f"Reports: {report_md} and {report_json}")
    print(f"final status: {final_status}")
    if compile_status is not None:
        print(f"compileall: {'passed' if compile_status[0] else 'FAILED'}")
    if override_count:
        print(f"Overrides staged for review: {override_count}", file=sys.stderr)
    if validator_fail_count:
        print(f"Validators failed: {validator_fail_count}", file=sys.stderr)
    if regression_count:
        print(f"Regression checks failed: {regression_count}", file=sys.stderr)
    if diff_fail_count and args.fail_on_diff_failure:
        print(f"Paired diffs failed: {diff_fail_count}", file=sys.stderr)
    if conflict_count:
        print(f"Conflicts requiring review: {conflict_count}", file=sys.stderr)
        return 1
    if override_count:
        return 1
    if diff_fail_count and args.fail_on_diff_failure:
        return 1
    if compile_status is not None and not compile_status[0]:
        return 1
    if validator_fail_count and not args.allow_validator_failure:
        return 1
    if regression_count:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
