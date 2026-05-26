from __future__ import annotations

"""Path-variable support for GPTOOL task manifests.

Task manifests are shared in source control, so they should not hardcode one
machine's absolute paths.  Values like ``${holoverse}`` are expanded from a
local, uncommitted project-root config.
"""

import json
import os
from pathlib import Path
import re
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TOKEN_RE = re.compile(r"\$\{([A-Za-z0-9_.-]+)\}")


def default_root_config_candidates() -> list[Path]:
    candidates: list[Path] = []
    env = os.environ.get("GPTOOL_LOCAL_ROOTS") or os.environ.get("GPT_TOOL_LOCAL_ROOTS")
    if env:
        candidates.append(Path(env))
    candidates.append(ROOT / "project_registry" / "local_project_roots.json")
    candidates.append(ROOT / "project_registry" / "local_project_roots.template.json")
    return candidates


def load_roots(config_path: str | Path | None = None) -> tuple[dict[str, str], str | None]:
    candidates = [Path(config_path)] if config_path else default_root_config_candidates()
    roots: dict[str, str] = {
        "gptool": str(ROOT),
        "gptool_root": str(ROOT),
    }
    used: str | None = None
    for candidate in candidates:
        try:
            if candidate and candidate.is_file():
                data = json.loads(candidate.read_text(encoding="utf-8"))
                raw_roots = data.get("roots") if isinstance(data, dict) else None
                if isinstance(raw_roots, dict):
                    for key, value in raw_roots.items():
                        if isinstance(value, str):
                            roots[str(key)] = value
                    used = str(candidate.resolve())
                    break
        except Exception:
            continue
    return roots, used


def expand_string(value: str, roots: dict[str, str]) -> str:
    def repl(match: re.Match[str]) -> str:
        key = match.group(1)
        if key.startswith("roots."):
            key = key.split(".", 1)[1]
        return str(roots.get(key, match.group(0)))
    return TOKEN_RE.sub(repl, value)


def expand_value(value: Any, roots: dict[str, str]) -> Any:
    if isinstance(value, str):
        return expand_string(value, roots)
    if isinstance(value, list):
        return [expand_value(item, roots) for item in value]
    if isinstance(value, dict):
        return {key: expand_value(item, roots) for key, item in value.items()}
    return value


def unresolved_tokens(value: Any) -> list[str]:
    found: set[str] = set()
    def visit(item: Any) -> None:
        if isinstance(item, str):
            found.update(match.group(1) for match in TOKEN_RE.finditer(item))
        elif isinstance(item, list):
            for child in item:
                visit(child)
        elif isinstance(item, dict):
            for child in item.values():
                visit(child)
    visit(value)
    return sorted(found)
