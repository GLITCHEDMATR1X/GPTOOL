from __future__ import annotations

"""Central bridge.py extension registry.

The core bridge CLI should not keep growing by pasting every subsystem directly
into bridge.py.  Extensions register their own commands through a small adapter
module and this registry calls those adapters from one place.
"""

import argparse
import importlib
import json
import traceback
from dataclasses import asdict, dataclass
from typing import Callable, Iterable


@dataclass(frozen=True)
class BridgeExtension:
    name: str
    module: str
    register_function: str
    commands: tuple[str, ...]
    description: str


EXTENSIONS: tuple[BridgeExtension, ...] = (
    BridgeExtension(
        name="patch_gate",
        module="patching.bridge_patch_adapter",
        register_function="add_patch_gate_commands",
        commands=(
            "patch-menu",
            "patch-rules",
            "patch-combine",
            "patch-repo-dry-run",
            "patch-repo-apply",
        ),
        description="Safe pass combining, protected-file merge, and repo patch dry-run/apply workflows.",
    ),
    BridgeExtension(
        name="app_capsules",
        module="app_capsules.bridge_app_adapter",
        register_function="add_app_capsule_commands",
        commands=(
            "app-menu",
            "app-scan",
            "app-migrate-plan",
            "app-adapter-audit",
            "app-validate",
        ),
        description="App capsule scanning, migration planning, adapter auditing, and capsule validation.",
    ),
    BridgeExtension(
        name="automation_tasks",
        module="automation_tasks.bridge_task_adapter",
        register_function="add_automation_task_commands",
        commands=(
            "task-menu",
            "task-validate",
            "task-run",
            "task-new",
        ),
        description="Local Codex-style automation task manifests and repeatable test-run workflows.",
    ),
)


_LAST_STATUS: list[dict[str, object]] = []


def _load_extension(extension: BridgeExtension) -> tuple[bool, str, Callable[[argparse._SubParsersAction], None] | None]:
    try:
        module = importlib.import_module(extension.module)
        register = getattr(module, extension.register_function)
        if not callable(register):
            return False, f"{extension.module}.{extension.register_function} is not callable", None
        return True, "ready", register
    except Exception:
        return False, traceback.format_exc(limit=8), None


def extension_status() -> list[dict[str, object]]:
    """Return current extension import status without registering commands."""
    status: list[dict[str, object]] = []
    for extension in EXTENSIONS:
        ok, message, _register = _load_extension(extension)
        status.append({
            "name": extension.name,
            "module": extension.module,
            "register_function": extension.register_function,
            "commands": list(extension.commands),
            "description": extension.description,
            "ok": ok,
            "message": message,
        })
    return status


def register_bridge_extensions(sub: argparse._SubParsersAction) -> list[dict[str, object]]:
    """Register all available bridge extensions and always add extension-status.

    Extension import/registration failures are reported through the returned
    status and through ``bridge.py extension-status``.  They should not prevent
    the base bridge commands from working.
    """
    global _LAST_STATUS
    registered: list[dict[str, object]] = []
    for extension in EXTENSIONS:
        ok, message, register = _load_extension(extension)
        item: dict[str, object] = {
            "name": extension.name,
            "module": extension.module,
            "register_function": extension.register_function,
            "commands": list(extension.commands),
            "description": extension.description,
            "ok": ok,
            "message": message,
            "registered": False,
        }
        if ok and register is not None:
            try:
                register(sub)
                item["registered"] = True
            except Exception:
                item["ok"] = False
                item["message"] = traceback.format_exc(limit=8)
        registered.append(item)
    _LAST_STATUS = registered

    status_parser = sub.add_parser("extension-status", help="Show GPTOOL bridge extension registration status.")
    status_parser.add_argument("--json", action="store_true")
    status_parser.set_defaults(func=command_extension_status)
    return registered


def command_extension_status(args: argparse.Namespace) -> int:
    status = _LAST_STATUS or extension_status()
    payload = {
        "schema": "gptool.bridge_extensions.v1",
        "ok": all(bool(item.get("ok")) for item in status),
        "extensions": status,
    }
    if getattr(args, "json", False):
        print(json.dumps(payload, indent=2))
    else:
        print("GPTOOL bridge extensions:")
        for item in status:
            state = "OK" if item.get("ok") else "FAIL"
            registered = "registered" if item.get("registered") else "import-only"
            print(f"- {item.get('name')}: {state} ({registered})")
            print(f"  commands: {', '.join(item.get('commands') or [])}")
            if not item.get("ok"):
                print(f"  reason: {item.get('message')}")
    return 0 if payload["ok"] else 1
