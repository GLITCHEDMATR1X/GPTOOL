from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

INPUT_PLAN_SCHEMA = "gptool.input_plan.v1"
ALLOWED_INPUT_ACTIONS = {
    "wait",
    "press",
    "hold_key",
    "release_key",
    "tap_key",
    "mouse_move",
    "mouse_click",
    "hold_mouse",
    "release_mouse",
    "enter_artifact",
    "exit_to_hub",
    "screenshot",
    "assert_state",
    "note",
}
REQUIRED_KEYS_BY_ACTION = {
    "wait": ("seconds",),
    "press": ("key",),
    "hold_key": ("key", "seconds"),
    "release_key": ("key",),
    "tap_key": ("key",),
    "mouse_move": ("dx", "dy"),
    "mouse_click": ("button",),
    "hold_mouse": ("button", "seconds"),
    "release_mouse": ("button",),
    "enter_artifact": ("slot",),
    "exit_to_hub": (),
    "screenshot": ("name",),
    "assert_state": ("state",),
    "note": ("message",),
}


@dataclass(frozen=True)
class InputPlanSummary:
    ok: bool
    step_count: int
    errors: list[str]
    warnings: list[str]
    duration_seconds: float
    screenshot_count: int
    artifact_slots: list[int]


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def normalize_input_plan(raw: dict[str, Any]) -> dict[str, Any]:
    plan = dict(raw or {})
    plan.setdefault("schema", INPUT_PLAN_SCHEMA)
    plan.setdefault("id", "input_plan")
    plan.setdefault("title", str(plan.get("id") or "Input Plan"))
    plan.setdefault("steps", [])
    return plan


def validate_input_plan(raw: dict[str, Any]) -> dict[str, Any]:
    plan = normalize_input_plan(raw)
    errors: list[str] = []
    warnings: list[str] = []
    if plan.get("schema") != INPUT_PLAN_SCHEMA:
        warnings.append(f"schema is {plan.get('schema')!r}; expected {INPUT_PLAN_SCHEMA!r}")
    if not str(plan.get("id") or "").strip():
        errors.append("missing id")
    steps = plan.get("steps")
    if not isinstance(steps, list):
        errors.append("steps must be a list")
        steps = []
    duration = 0.0
    screenshots = 0
    slots: list[int] = []
    for index, step in enumerate(steps, start=1):
        if not isinstance(step, dict):
            errors.append(f"step {index} is not an object")
            continue
        action = step.get("action")
        if action not in ALLOWED_INPUT_ACTIONS:
            errors.append(f"step {index} unsupported input action {action!r}")
            continue
        for key in REQUIRED_KEYS_BY_ACTION.get(action, ()):
            if key not in step:
                errors.append(f"step {index} {action} missing {key}")
        if action in {"wait", "hold_key", "hold_mouse"}:
            seconds = _as_float(step.get("seconds"), -1.0)
            if seconds < 0:
                errors.append(f"step {index} {action} seconds must be >= 0")
            else:
                duration += seconds
        if action == "screenshot":
            screenshots += 1
        if action == "enter_artifact":
            try:
                slot = int(step.get("slot"))
                if not (0 <= slot <= 15):
                    errors.append(f"step {index} artifact slot out of conservative range 0..15")
                elif slot not in slots:
                    slots.append(slot)
            except Exception:
                errors.append(f"step {index} enter_artifact slot must be int")
    summary = InputPlanSummary(
        ok=not errors,
        step_count=len(steps),
        errors=errors,
        warnings=warnings,
        duration_seconds=round(duration, 3),
        screenshot_count=screenshots,
        artifact_slots=slots,
    )
    return asdict(summary)


def write_input_plan(path: str | Path, raw: dict[str, Any]) -> dict[str, Any]:
    plan = normalize_input_plan(raw)
    validation = validate_input_plan(plan)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    return {"path": str(target), "plan": plan, "validation": validation, "ok": bool(validation.get("ok"))}


def load_input_plan(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    data = json.loads(p.read_text(encoding="utf-8"))
    return normalize_input_plan(data)


def render_input_plan_markdown(plan: dict[str, Any], validation: dict[str, Any] | None = None) -> str:
    validation = validation or validate_input_plan(plan)
    lines = [
        "# GPTOOL Input Plan",
        "",
        f"- ID: `{plan.get('id')}`",
        f"- Title: {plan.get('title') or ''}",
        f"- Status: **{'PASS' if validation.get('ok') else 'FAIL'}**",
        f"- Steps: {validation.get('step_count')}",
        f"- Estimated active duration: {validation.get('duration_seconds')}s",
        f"- Screenshot checkpoints: {validation.get('screenshot_count')}",
        "",
        "## Steps",
        "",
    ]
    for i, step in enumerate(plan.get("steps") or [], start=1):
        action = step.get("action")
        label = step.get("label") or step.get("name") or ""
        detail = ""
        if action == "enter_artifact":
            detail = f" slot={step.get('slot')}"
        elif action in {"press", "tap_key", "hold_key"}:
            detail = f" key={step.get('key')}"
        elif action in {"mouse_click", "hold_mouse"}:
            detail = f" button={step.get('button')}"
        elif action == "screenshot":
            detail = f" name={step.get('name')}"
        lines.append(f"- {i}. `{action}`{detail} {label}".rstrip())
    errors = validation.get("errors") or []
    if errors:
        lines.extend(["", "## Errors", ""])
        lines.extend(f"- {item}" for item in errors)
    warnings = validation.get("warnings") or []
    if warnings:
        lines.extend(["", "## Warnings", ""])
        lines.extend(f"- {item}" for item in warnings)
    return "\n".join(lines) + "\n"
