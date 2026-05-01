from __future__ import annotations

import importlib.metadata
import importlib.util
import json
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

BRIDGE_ROOT = Path(__file__).resolve().parents[1]
PANDA_IMPORT_ROOTS = ("panda3d", "direct")
PANDA_OPTIONAL_ROOTS = ("gltf", "simplepbr", "PIL")
RUNTIME_PROVIDERS = ("auto", "system_python", "portable_python", "packaged_exe", "mock_display")
DEFAULT_ENTRY_CANDIDATES = (
    "main.py",
    "app.py",
    "game.py",
    "run.py",
    "launcher.py",
    "src/main.py",
    "src/app.py",
    "HoloVerse/main.py",
    "data/HoloVerse/main.py",
)
PANDA_SIGNAL_STRINGS = (
    "panda3d.core",
    "direct.showbase",
    "ShowBase",
    "loadPrcFileData",
    "loader.loadModel",
    "base.run(",
    ".run()",
)
CRASH_SIGNATURES = (
    "Traceback (most recent call last)",
    "ModuleNotFoundError",
    "ImportError",
    "Exception:",
    "AssertionError",
    ":error:",
    "Could not load",
    "Unable to load",
    "No module named",
)


def _module_present(module_name: str) -> dict[str, Any]:
    spec = importlib.util.find_spec(module_name)
    result: dict[str, Any] = {"present": spec is not None, "module": module_name}
    if spec and spec.origin:
        result["origin"] = spec.origin
    if spec:
        try:
            dist_name = {
                "PIL": "Pillow",
                "gltf": "panda3d-gltf",
            }.get(module_name, module_name)
            result["version"] = importlib.metadata.version(dist_name)
        except Exception:
            result["version"] = None
    return result


def probe_panda3d_environment(python_executable: str | Path | None = None) -> dict[str, Any]:
    """Probe Panda3D availability.

    Without python_executable this probes the current interpreter. With one supplied, it
    probes a sidecar/portable interpreter by spawning it. This keeps the bridge from
    confusing "my Python lacks Panda3D" with "no reusable Panda3D runtime exists".
    """
    if python_executable:
        return probe_python_panda3d(Path(python_executable))

    required = {name: _module_present(name) for name in PANDA_IMPORT_ROOTS}
    optional = {name: _module_present(name) for name in PANDA_OPTIONAL_ROOTS}
    ready = all(item["present"] for item in required.values())
    notes: list[str] = []
    if ready:
        notes.append("Panda3D core modules are import-discoverable in the current interpreter.")
    else:
        missing = [name for name, item in required.items() if not item["present"]]
        notes.append("Missing Panda3D core module(s) in current interpreter: " + ", ".join(missing))
    if not optional["PIL"]["present"]:
        notes.append("Pillow is not available; screenshot image heuristics may be unavailable until installed.")
    if not optional["gltf"]["present"]:
        notes.append("panda3d-gltf/gltf import support was not detected; glTF projects may need it installed.")
    return {
        "validator": "panda3d_environment_probe",
        "provider": "system_python",
        "python_executable": sys.executable,
        "ready": ready,
        "required": required,
        "optional": optional,
        "notes": notes,
    }


def probe_python_panda3d(python_executable: Path, timeout: int = 8) -> dict[str, Any]:
    python_executable = python_executable.expanduser()
    if not python_executable.exists():
        return {
            "validator": "panda3d_environment_probe",
            "provider": "portable_python",
            "python_executable": str(python_executable),
            "ready": False,
            "required": {},
            "optional": {},
            "notes": ["Python executable does not exist."],
        }
    script = r'''
import importlib.metadata, importlib.util, json, sys
required_names = ["panda3d", "direct"]
optional_names = ["gltf", "simplepbr", "PIL"]
def mod(name):
    spec = importlib.util.find_spec(name)
    out = {"present": spec is not None, "module": name}
    if spec and spec.origin:
        out["origin"] = spec.origin
    if spec:
        try:
            dist = {"PIL": "Pillow", "gltf": "panda3d-gltf"}.get(name, name)
            out["version"] = importlib.metadata.version(dist)
        except Exception:
            out["version"] = None
    return out
required = {name: mod(name) for name in required_names}
optional = {name: mod(name) for name in optional_names}
ready = all(item["present"] for item in required.values())
notes = []
if ready:
    notes.append("Panda3D core modules are import-discoverable in this runtime.")
else:
    notes.append("Missing Panda3D core module(s): " + ", ".join([name for name, item in required.items() if not item["present"]]))
print(json.dumps({
    "validator": "panda3d_environment_probe",
    "provider": "portable_python",
    "python_executable": sys.executable,
    "ready": ready,
    "required": required,
    "optional": optional,
    "notes": notes,
}))
'''
    try:
        proc = subprocess.run(
            [str(python_executable), "-c", script],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except Exception as exc:
        return {
            "validator": "panda3d_environment_probe",
            "provider": "portable_python",
            "python_executable": str(python_executable),
            "ready": False,
            "required": {},
            "optional": {},
            "notes": [f"Could not execute runtime probe: {exc}"],
        }
    try:
        data = json.loads((proc.stdout or "").strip().splitlines()[-1])
    except Exception:
        data = {
            "validator": "panda3d_environment_probe",
            "provider": "portable_python",
            "python_executable": str(python_executable),
            "ready": False,
            "required": {},
            "optional": {},
            "notes": ["Runtime probe did not return valid JSON."],
            "stdout_tail": _tail(proc.stdout),
            "stderr_tail": _tail(proc.stderr),
        }
    data["returncode"] = proc.returncode
    data["python_executable"] = str(python_executable)
    if proc.returncode != 0:
        data["ready"] = False
        data.setdefault("notes", []).append("Runtime probe exited nonzero.")
        data["stderr_tail"] = _tail(proc.stderr)
    return data


def _read_small_text(path: Path, limit: int = 180_000) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""
    if len(text) > limit:
        return text[:limit]
    return text


def _score_entry(path: Path, project_root: Path) -> dict[str, Any]:
    text = _read_small_text(path)
    signals = [s for s in PANDA_SIGNAL_STRINGS if s in text]
    score = len(signals) * 10
    rel = str(path.resolve().relative_to(project_root.resolve())).replace("\\", "/")
    lower = rel.lower()
    if lower in DEFAULT_ENTRY_CANDIDATES:
        score += 8
    if path.name.lower() == "main.py":
        score += 5
    if "if __name__" in text and "__main__" in text:
        score += 4
    if "run(" in text:
        score += 2
    return {
        "path": rel,
        "score": score,
        "signals": signals,
        "has_main_guard": "if __name__" in text and "__main__" in text,
    }


def discover_panda3d_project(project_root: Path, explicit_entry: str | None = None, max_files: int = 5000) -> dict[str, Any]:
    project_root = project_root.resolve()
    candidates: list[dict[str, Any]] = []
    notes: list[str] = []

    if explicit_entry:
        raw_entry = Path(explicit_entry)
        entry_path = raw_entry if raw_entry.is_absolute() else project_root / raw_entry
        exists = entry_path.exists()
        selected = str(entry_path.resolve().relative_to(project_root)).replace("\\", "/") if exists else explicit_entry
        return {
            "validator": "panda3d_project_discovery",
            "project_root": str(project_root),
            "selected_entry": selected if exists else None,
            "explicit_entry": explicit_entry,
            "entry_exists": exists,
            "candidates": [_score_entry(entry_path, project_root)] if exists and entry_path.suffix == ".py" else [],
            "notes": [] if exists else ["Explicit entry point was supplied but does not exist."],
        }

    for rel in DEFAULT_ENTRY_CANDIDATES:
        path = project_root / rel
        if path.exists() and path.suffix == ".py":
            candidates.append(_score_entry(path, project_root))

    count = 0
    excluded = {".git", "__pycache__", ".mypy_cache", ".pytest_cache", "node_modules", "dist", "build"}
    for py_path in sorted(project_root.rglob("*.py")):
        if any(part in excluded for part in py_path.relative_to(project_root).parts):
            continue
        count += 1
        if count > max_files:
            notes.append(f"Stopped Panda3D entry scan after {max_files} Python files.")
            break
        if any(str(py_path.relative_to(project_root)).replace("\\", "/") == c["path"] for c in candidates):
            continue
        text = _read_small_text(py_path)
        if any(signal in text for signal in PANDA_SIGNAL_STRINGS):
            candidates.append(_score_entry(py_path, project_root))

    candidates = sorted(candidates, key=lambda item: (-int(item["score"]), item["path"]))[:50]
    selected = candidates[0]["path"] if candidates else None
    if not selected:
        notes.append("No Panda3D-looking Python entry point was discovered. Supply --entry or --smoke-command.")
    return {
        "validator": "panda3d_project_discovery",
        "project_root": str(project_root),
        "selected_entry": selected,
        "explicit_entry": None,
        "entry_exists": selected is not None,
        "candidates": candidates,
        "notes": notes,
    }


def _split_command(command: str) -> list[str]:
    return shlex.split(command, posix=(os.name != "nt"))


def _tail(text: str | bytes | None, limit: int = 6000) -> str:
    if text is None:
        return ""
    if isinstance(text, bytes):
        text = text.decode("utf-8", errors="replace")
    return text[-limit:]


def _parse_extra_env(items: list[str] | None) -> dict[str, str]:
    env: dict[str, str] = {}
    for raw in items or []:
        if "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        key = key.strip()
        if key:
            env[key] = value
    return env


def _resolve_path(raw: str | Path, project_root: Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else project_root / path


def _candidate_python_paths(root: Path) -> list[Path]:
    root = root.resolve()
    if root.is_file():
        return [root]
    names = [
        "python.exe",
        "python",
        "python3",
        "Scripts/python.exe",
        "Scripts/python",
        "bin/python",
        "bin/python3",
        ".venv/Scripts/python.exe",
        ".venv/bin/python",
        "venv/Scripts/python.exe",
        "venv/bin/python",
    ]
    return [root / name for name in names]


def _find_python_executable(root: Path | None) -> Path | None:
    if not root:
        return None
    for candidate in _candidate_python_paths(root):
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def _portable_runtime_roots(project_root: Path, runtime_path: str | None = None) -> list[Path]:
    roots: list[Path] = []
    for env_name in ("GPT_BRIDGE_PANDA3D_PYTHON", "GPT_BRIDGE_PANDA3D_RUNTIME"):
        raw = os.environ.get(env_name)
        if raw:
            roots.append(Path(raw))
    if runtime_path:
        roots.append(_resolve_path(runtime_path, project_root))
    roots.extend([
        project_root / ".gpt_runtimes" / "panda3d_py313",
        project_root / ".gpt_runtimes" / "panda3d",
        project_root / "runtimes" / "panda3d_py313",
        project_root / "runtimes" / "panda3d",
        BRIDGE_ROOT / "runtimes" / "panda3d_py313",
        BRIDGE_ROOT / "runtimes" / "panda3d",
    ])
    seen: set[str] = set()
    unique: list[Path] = []
    for root in roots:
        key = str(root.expanduser().resolve()) if root.exists() else str(root.expanduser())
        if key in seen:
            continue
        seen.add(key)
        unique.append(root.expanduser())
    return unique


def discover_portable_runtime(project_root: Path, runtime_path: str | None = None) -> dict[str, Any]:
    project_root = project_root.resolve()
    checked: list[str] = []
    probes: list[dict[str, Any]] = []
    for root in _portable_runtime_roots(project_root, runtime_path):
        checked.append(str(root))
        python_exe = _find_python_executable(root)
        if not python_exe:
            continue
        probe = probe_python_panda3d(python_exe)
        probes.append(probe)
        if probe.get("ready"):
            return {
                "provider": "portable_python",
                "ready": True,
                "python_executable": str(python_exe),
                "runtime_root": str(root),
                "environment": probe,
                "checked": checked,
                "notes": ["Reusable portable Panda3D runtime found."],
            }
    notes = ["No portable Python runtime with Panda3D was found."]
    if runtime_path:
        notes.append("The supplied --runtime-path did not resolve to a working Panda3D Python runtime.")
    return {
        "provider": "portable_python",
        "ready": False,
        "python_executable": None,
        "runtime_root": None,
        "environment": probes[-1] if probes else None,
        "checked": checked,
        "notes": notes,
    }


def discover_packaged_exe(project_root: Path, packaged_exe: str | None = None, max_candidates: int = 40) -> dict[str, Any]:
    project_root = project_root.resolve()
    explicit = packaged_exe or os.environ.get("GPT_BRIDGE_PACKAGED_EXE")
    candidates: list[Path] = []
    notes: list[str] = []
    if explicit:
        candidate = _resolve_path(explicit, project_root)
        exists = candidate.exists() and candidate.is_file()
        return {
            "provider": "packaged_exe",
            "ready": exists,
            "executable": str(candidate.resolve()) if exists else str(candidate),
            "explicit": True,
            "candidates": [str(candidate)] if exists else [],
            "notes": [] if exists else ["Explicit packaged executable was supplied but does not exist."],
        }
    patterns = [
        "dist/*.exe",
        "dist/*/*.exe",
        "build/*.exe",
        "*.exe",
        "dist/*",
    ]
    seen: set[Path] = set()
    for pattern in patterns:
        for path in sorted(project_root.glob(pattern)):
            if path in seen or not path.is_file():
                continue
            lower = path.name.lower()
            if lower.endswith((".dll", ".pyd", ".zip", ".json", ".txt", ".log")):
                continue
            if lower.endswith(".exe") or os.access(path, os.X_OK):
                candidates.append(path.resolve())
                seen.add(path)
            if len(candidates) >= max_candidates:
                break
        if candidates:
            break
    if not candidates:
        notes.append("No packaged executable was discovered. Supply --exe when testing a built game.")
    return {
        "provider": "packaged_exe",
        "ready": bool(candidates),
        "executable": str(candidates[0]) if candidates else None,
        "explicit": False,
        "candidates": [str(path) for path in candidates[:max_candidates]],
        "notes": notes,
    }


def resolve_runtime_provider(
    project_root: Path,
    *,
    requested: str = "auto",
    runtime_path: str | None = None,
    packaged_exe: str | None = None,
    command: str | None = None,
) -> dict[str, Any]:
    project_root = project_root.resolve()
    requested = (requested or "auto").lower().replace("-", "_")
    if requested == "portable":
        requested = "portable_python"
    if requested == "system":
        requested = "system_python"
    if requested in {"packaged", "exe", "packaged_exe"}:
        requested = "packaged_exe"
    if requested in {"mock", "none", "mock_display"}:
        requested = "mock_display"
    notes: list[str] = []

    if command:
        return {
            "validator": "panda3d_runtime_provider",
            "requested": requested,
            "selected": "custom_command",
            "ready": True,
            "visual_capable": True,
            "python_executable": None,
            "packaged_exe": None,
            "environment": None,
            "notes": ["Using explicit --smoke-command; runtime provider discovery is advisory only."],
        }

    if requested not in RUNTIME_PROVIDERS:
        return {
            "validator": "panda3d_runtime_provider",
            "requested": requested,
            "selected": None,
            "ready": False,
            "visual_capable": False,
            "notes": [f"Unknown runtime provider '{requested}'. Valid providers: {', '.join(RUNTIME_PROVIDERS)}."],
        }

    def system_provider() -> dict[str, Any]:
        env = probe_panda3d_environment()
        return {
            "validator": "panda3d_runtime_provider",
            "requested": requested,
            "selected": "system_python",
            "ready": bool(env.get("ready")),
            "visual_capable": bool(env.get("ready")),
            "python_executable": sys.executable,
            "packaged_exe": None,
            "environment": env,
            "notes": env.get("notes", []),
        }

    def portable_provider() -> dict[str, Any]:
        found = discover_portable_runtime(project_root, runtime_path=runtime_path)
        return {
            "validator": "panda3d_runtime_provider",
            "requested": requested,
            "selected": "portable_python",
            "ready": bool(found.get("ready")),
            "visual_capable": bool(found.get("ready")),
            "python_executable": found.get("python_executable"),
            "runtime_root": found.get("runtime_root"),
            "packaged_exe": None,
            "environment": found.get("environment"),
            "checked": found.get("checked", []),
            "notes": found.get("notes", []),
        }

    def packaged_provider() -> dict[str, Any]:
        found = discover_packaged_exe(project_root, packaged_exe=packaged_exe)
        return {
            "validator": "panda3d_runtime_provider",
            "requested": requested,
            "selected": "packaged_exe",
            "ready": bool(found.get("ready")),
            "visual_capable": bool(found.get("ready")),
            "python_executable": None,
            "packaged_exe": found.get("executable"),
            "environment": None,
            "candidates": found.get("candidates", []),
            "notes": found.get("notes", []),
        }

    def mock_provider(extra_notes: list[str] | None = None) -> dict[str, Any]:
        return {
            "validator": "panda3d_runtime_provider",
            "requested": requested,
            "selected": "mock_display",
            "ready": True,
            "visual_capable": False,
            "python_executable": None,
            "packaged_exe": None,
            "environment": None,
            "notes": (extra_notes or []) + [
                "Using mock display fallback: static/non-render checks can run, but real Panda3D visual proof is unverified."
            ],
        }

    if requested == "system_python":
        return system_provider()
    if requested == "portable_python":
        return portable_provider()
    if requested == "packaged_exe":
        return packaged_provider()
    if requested == "mock_display":
        return mock_provider()

    # Auto mode: prefer the player-visible packaged build if supplied/found, then
    # reusable portable runtime, then current Python, then honest mock fallback.
    packaged = packaged_provider()
    if packaged_exe or packaged.get("ready"):
        if packaged.get("ready"):
            packaged["requested"] = "auto"
            packaged.setdefault("notes", []).insert(0, "Auto selected packaged executable runtime.")
            return packaged
        notes.extend(packaged.get("notes", []))

    portable = portable_provider()
    if portable.get("ready"):
        portable["requested"] = "auto"
        portable.setdefault("notes", []).insert(0, "Auto selected portable Python Panda3D runtime.")
        return portable
    notes.extend(portable.get("notes", []))

    system = system_provider()
    if system.get("ready"):
        system["requested"] = "auto"
        system.setdefault("notes", []).insert(0, "Auto selected system Python Panda3D runtime.")
        return system
    notes.extend(system.get("notes", []))

    return mock_provider(notes)


def _recent_logs(project_root: Path, started_at: float, limit: int = 30) -> list[dict[str, Any]]:
    patterns = ["logs/*.log", "logs/*.txt", "*.log", "crash*.txt", "crash*.log"]
    found: list[dict[str, Any]] = []
    seen: set[Path] = set()
    for pattern in patterns:
        for path in project_root.glob(pattern):
            try:
                resolved = path.resolve()
                if resolved in seen or not path.is_file():
                    continue
                stat = path.stat()
                if stat.st_mtime + 2 < started_at:
                    continue
                text = _tail(path.read_text(encoding="utf-8", errors="replace"), 3000)
                found.append({
                    "path": str(path.relative_to(project_root)).replace("\\", "/"),
                    "size_bytes": stat.st_size,
                    "modified_epoch": round(stat.st_mtime, 3),
                    "tail": text,
                    "crash_signatures": [sig for sig in CRASH_SIGNATURES if sig.lower() in text.lower()],
                })
                seen.add(resolved)
            except Exception:
                continue
    return sorted(found, key=lambda item: item["modified_epoch"], reverse=True)[:limit]


def _build_smoke_command(
    project_root: Path,
    *,
    provider: dict[str, Any],
    selected_entry: str | None,
    command: str | None,
) -> tuple[list[str] | None, str, list[str]]:
    notes: list[str] = []
    selected = provider.get("selected")
    if command:
        return _split_command(command), "smoke_command", notes
    if selected == "packaged_exe":
        exe = provider.get("packaged_exe")
        if exe:
            return [str(exe)], "packaged_exe", notes
        notes.append("Packaged EXE runtime was selected, but no executable path was available.")
        return None, "packaged_exe", notes
    if selected in {"portable_python", "system_python"}:
        python_exe = provider.get("python_executable") or sys.executable
        if selected_entry:
            return [str(python_exe), str(project_root / selected_entry)], "entry_point", notes
        notes.append("Python runtime was selected, but no Panda3D entry point was available.")
        return None, "entry_point", notes
    if selected == "mock_display":
        return None, "mock_display", notes
    notes.append(f"Runtime provider '{selected}' cannot build a smoke command.")
    return None, str(selected or "unknown"), notes



def _resolve_project_path(project_root: Path, raw_path: str | None, default_relative: str) -> Path:
    path = Path(raw_path) if raw_path else project_root / default_relative
    if not path.is_absolute():
        path = project_root / path
    path.parent.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def _read_json_if_exists(path: Path, limit: int = 200_000) -> dict[str, Any] | None:
    if not path.exists() or not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        if len(text) > limit:
            text = text[:limit]
        data = json.loads(text)
        return data if isinstance(data, dict) else {"raw": data}
    except Exception as exc:
        return {"read_error": f"{type(exc).__name__}: {exc}"}


def run_panda3d_smoke(
    project_root: Path,
    *,
    entry: str | None = None,
    command: str | None = None,
    timeout: int = 20,
    screenshot_path: str | None = None,
    require_screenshot: bool = False,
    proof_path: str | None = None,
    require_proof: bool = False,
    frames: int = 4,
    window_type: str = "default",
    extra_env: list[str] | None = None,
    runtime_provider: str = "auto",
    runtime_path: str | None = None,
    packaged_exe: str | None = None,
) -> dict[str, Any]:
    project_root = project_root.resolve()
    discovery = discover_panda3d_project(project_root, explicit_entry=entry)
    selected_entry = discovery.get("selected_entry")
    screenshot = _resolve_project_path(project_root, screenshot_path, "reports/panda3d_smoke.png")
    proof = _resolve_project_path(project_root, proof_path, "reports/panda3d_scene_proof.json")

    provider = resolve_runtime_provider(
        project_root,
        requested=runtime_provider,
        runtime_path=runtime_path,
        packaged_exe=packaged_exe,
        command=command,
    )

    if provider.get("selected") == "mock_display":
        ok = not require_screenshot and not require_proof
        return {
            "validator": "panda3d_runtime_smoke",
            "ok": ok,
            "mode": "mock_display",
            "project_root": str(project_root),
            "runtime_provider": provider,
            "command": None,
            "timeout_seconds": timeout,
            "timed_out": False,
            "returncode": None,
            "duration_seconds": 0,
            "stdout_tail": "",
            "stderr_tail": "",
            "crash_signatures": [],
            "screenshot": {
                "path": str(screenshot),
                "exists": screenshot.exists(),
                "required": require_screenshot,
                "env_var": "GPT_BRIDGE_SCREENSHOT_PATH",
            },
            "proof": {
                "path": str(proof),
                "exists": proof.exists(),
                "required": require_proof,
                "env_var": "GPT_BRIDGE_SMOKE_PROOF_PATH",
                "data": _read_json_if_exists(proof),
            },
            "visual_proof": "unverified",
            "logs": [],
            "discovery": discovery,
            "next_actions": [
                "No real Panda3D display/runtime was available. Static checks ran, but screenshot proof is unverified.",
                "Install or attach a reusable runtime under runtimes/panda3d_py313, pass --runtime-path, or test the packaged EXE with --runtime packaged-exe --exe path/to/game.exe.",
            ] + (["Because --require-screenshot was used, delivery must stay blocked until a real runtime captures a screenshot."] if require_screenshot else []) + (["Because --require-proof was used, delivery must stay blocked until a real scene-proof JSON file is written."] if require_proof else []),
            "adapter_notes": [
                "Mock display mode is intentionally honest: it does not claim that rendering worked.",
            ],
        }

    if not provider.get("ready"):
        return {
            "validator": "panda3d_runtime_smoke",
            "ok": False,
            "mode": str(provider.get("selected") or runtime_provider),
            "project_root": str(project_root),
            "runtime_provider": provider,
            "returncode": None,
            "timed_out": False,
            "duration_seconds": 0,
            "screenshot": {"path": str(screenshot), "exists": screenshot.exists(), "required": require_screenshot},
            "proof": {"path": str(proof), "exists": proof.exists(), "required": require_proof, "data": _read_json_if_exists(proof)},
            "logs": [],
            "discovery": discovery,
            "next_actions": provider.get("notes", []) + ["Select a working runtime provider or use --runtime mock for non-render checks only."],
        }

    cmd, mode, command_notes = _build_smoke_command(project_root, provider=provider, selected_entry=selected_entry, command=command)
    if not cmd:
        return {
            "validator": "panda3d_runtime_smoke",
            "ok": False,
            "mode": mode,
            "project_root": str(project_root),
            "runtime_provider": provider,
            "discovery": discovery,
            "returncode": None,
            "timed_out": False,
            "duration_seconds": 0,
            "screenshot": {"path": str(screenshot), "exists": screenshot.exists(), "required": require_screenshot},
            "proof": {"path": str(proof), "exists": proof.exists(), "required": require_proof, "data": _read_json_if_exists(proof)},
            "logs": [],
            "next_actions": command_notes + ["Supply --entry, --smoke-command, or --exe depending on the selected runtime."],
        }

    env = os.environ.copy()
    env.update(_parse_extra_env(extra_env))
    env.setdefault("PYTHONUNBUFFERED", "1")
    env["GPT_BRIDGE_TEST_MODE"] = "1"
    env["GPT_BRIDGE_SMOKE"] = "1"
    env["GPT_BRIDGE_SMOKE_FRAMES"] = str(frames)
    env["GPT_BRIDGE_SCREENSHOT_PATH"] = str(screenshot)
    env["GPT_BRIDGE_SMOKE_PROOF_PATH"] = str(proof)
    env["GPT_BRIDGE_WINDOW_TYPE"] = window_type
    env["GPT_BRIDGE_EXIT_AFTER_SCREENSHOT"] = "1"
    env["GPT_BRIDGE_RUNTIME_PROVIDER"] = str(provider.get("selected"))
    pythonpath_parts = [str(project_root), str(BRIDGE_ROOT)]
    if env.get("PYTHONPATH"):
        pythonpath_parts.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(pythonpath_parts)

    started = time.time()
    timed_out = False
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(project_root),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        returncode = proc.returncode
        stdout = _tail(proc.stdout)
        stderr = _tail(proc.stderr)
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        returncode = None
        stdout = _tail(exc.stdout)
        stderr = _tail(exc.stderr)
    duration = round(time.time() - started, 3)
    logs = _recent_logs(project_root, started)
    combined = "\n".join([stdout, stderr] + [item.get("tail", "") for item in logs])
    signatures = sorted({sig for sig in CRASH_SIGNATURES if sig.lower() in combined.lower()})
    screenshot_exists = screenshot.exists()
    proof_exists = proof.exists()
    proof_data = _read_json_if_exists(proof)
    ok = (returncode == 0) and not timed_out and not signatures
    if require_screenshot and not screenshot_exists:
        ok = False
    if require_proof and not proof_exists:
        ok = False

    next_actions: list[str] = []
    if timed_out:
        next_actions.append("The process timed out. Add the runtime hook or a project smoke mode so the app exits after capture.")
    if returncode not in (0, None):
        next_actions.append("Open stdout/stderr tails and fix the launch crash before visual review.")
    if require_screenshot and not screenshot_exists:
        next_actions.append("No screenshot was produced. Add runtime_hooks.panda3d_smoke_hook.install_from_env(base) after ShowBase creation or make the packaged EXE honor GPT_BRIDGE_SCREENSHOT_PATH.")
    if require_proof and not proof_exists:
        next_actions.append("No scene-proof JSON was produced. Add runtime_hooks.panda3d_smoke_hook.install_from_env(base) or make the app honor GPT_BRIDGE_SMOKE_PROOF_PATH.")
    if not command and not selected_entry and provider.get("selected") != "packaged_exe":
        next_actions.append("Supply an explicit entry point with --entry.")
    if not next_actions:
        next_actions.append("Runtime smoke completed without adapter-detected blockers.")

    return {
        "validator": "panda3d_runtime_smoke",
        "ok": ok,
        "mode": mode,
        "project_root": str(project_root),
        "runtime_provider": provider,
        "command": cmd,
        "timeout_seconds": timeout,
        "timed_out": timed_out,
        "returncode": returncode,
        "duration_seconds": duration,
        "stdout_tail": stdout,
        "stderr_tail": stderr,
        "crash_signatures": signatures,
        "screenshot": {
            "path": str(screenshot),
            "exists": screenshot_exists,
            "required": require_screenshot,
            "env_var": "GPT_BRIDGE_SCREENSHOT_PATH",
        },
        "proof": {
            "path": str(proof),
            "exists": proof_exists,
            "required": require_proof,
            "env_var": "GPT_BRIDGE_SMOKE_PROOF_PATH",
            "data": proof_data,
        },
        "visual_proof": "screenshot_verified" if screenshot_exists else ("headless_scene_verified" if proof_exists else "not_captured"),
        "logs": logs,
        "discovery": discovery,
        "next_actions": next_actions,
        "adapter_notes": [
            "Automatic screenshots require the game to honor GPT_BRIDGE_SCREENSHOT_PATH or use the included Panda3D smoke hook.",
            "Headless scene proof requires the game to honor GPT_BRIDGE_SMOKE_PROOF_PATH or use the included Panda3D smoke hook.",
            "Portable runtimes should live beside the bridge or project under runtimes/panda3d_py313 and contain a Python executable with Panda3D installed.",
            "Packaged EXE mode is the strongest player-route proof when testing final/Steam builds.",
        ],
    }
