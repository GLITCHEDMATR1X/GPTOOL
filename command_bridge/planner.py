from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _contains(text: str, *needles: str) -> bool:
    lowered = text.lower()
    return any(needle.lower() in lowered for needle in needles)


def _has_word(text: str, *words: str) -> bool:
    return any(re.search(r"\b" + re.escape(word.lower()) + r"\b", text.lower()) for word in words)


def _add_unique(items: list[Any], value: Any) -> None:
    if value not in items:
        items.append(value)


def _rule(rule_id: str, kind: str, description: str, *, severity: str = "fail", data: dict[str, Any] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": rule_id,
        "kind": kind,
        "severity": severity,
        "description": description,
    }
    if data:
        payload.update(data)
    return payload


def _guess_intents(command: str) -> list[str]:
    intents: list[str] = []
    text = command.lower()
    if any(k in text for k in ["fps", "hud", "ui", "points", "counter", "off screen", "off-screen", "transparent", "background box"]):
        intents.append("ui_hud_accuracy")
    if any(k in text for k in ["spawn", "spawning", "persistent", "despawn", "select", "selected", "robot", "bot", "standby"]):
        intents.append("spawn_route_state")
    if any(k in text for k in ["urban", "metropolis", "sable", "archivist", "warzone", "runtime", "world route", "player route"]):
        intents.append("holoverse_route_accuracy")
    if any(k in text for k in ["terrain", "visible", "region", "biome", "ground", "fog", "background", "sky"]):
        intents.append("world_visual_accuracy")
    if any(k in text for k in ["regression", "solid", "robust", "check", "fix any code", "works fine"]):
        intents.append("regression_hardening")
    if not intents:
        intents.append("general_game_change")
    return intents


def _affected_areas(command: str, profile: str) -> list[str]:
    text = command.lower()
    areas: list[str] = []
    for keyword, area in [
        ("ui", "UI/HUD"),
        ("hud", "UI/HUD"),
        ("fps", "UI/HUD"),
        ("points", "Scoring/points display"),
        ("score", "Scoring/points display"),
        ("urban", "HoloVerse Urban route/region"),
        ("warzone", "HoloVerse Urban Warzone runtime"),
        ("metropolis", "HoloVerse Metropolis route/robot selection"),
        ("robot", "Robot/bot state transfer"),
        ("bot", "Robot/bot state transfer"),
        ("terrain", "Terrain/world rendering"),
        ("background", "Visual presentation/backgrounds"),
        ("animal", "Creature models/spawn visuals"),
        ("persistent", "Spawn persistence/state"),
        ("spawn", "Spawn persistence/state"),
    ]:
        if keyword in text:
            _add_unique(areas, area)
    if profile.lower() in {"panda3d", "holoverse", "codered", "code_red"}:
        _add_unique(areas, "Panda3D runtime/screenshot proof")
    return areas or ["Project files requested by command"]


def _scope_keywords(command: str, profile: str) -> list[str]:
    text = command.lower()
    keywords = ["main", "runtime", "world", "ui", "hud", "config", "manifest"]
    if "urban" in text or "warzone" in text:
        keywords += ["urban", "warzone", "sable", "dimension", "dimensions"]
    if "metropolis" in text or "robot" in text or "bot" in text:
        keywords += ["metropolis", "robot", "bot", "archivist"]
    if "points" in text or "score" in text:
        keywords += ["points", "score"]
    if "animal" in text or "hill" in text or "mushroom" in text:
        keywords += ["animal", "hill", "mushroom", "creature"]
    if profile.lower() in {"holoverse", "panda3d"}:
        keywords += ["holoverse", "data"]
    return sorted(set(keywords))


def build_work_order(project_root: str | Path | None, profile: str, command: str) -> dict[str, Any]:
    """Build a deterministic AI-facing work order from a user command.

    This intentionally avoids LLM calls. It is meant to be predictable enough for
    CI and safe enough for AI agents to consume before editing a game project.
    """
    source = command.strip()
    text = source.lower()
    command_id = hashlib.sha1(f"{profile}\n{source}".encode("utf-8", errors="ignore")).hexdigest()[:12]

    must_do: list[str] = []
    must_not_do: list[str] = []
    do_not_touch: list[str] = []
    visual_tests: list[dict[str, Any]] = []
    acceptance_tests: list[dict[str, Any]] = []
    runtime_tests: list[dict[str, Any]] = []
    static_checks: list[dict[str, Any]] = []
    regression_risks: list[str] = []

    # Safe defaults for AI agents.
    must_not_do.extend([
        "Do not add unrelated features before satisfying the requested change.",
        "Do not claim the change is verified without a concrete validation result or screenshot/runtime proof.",
        "Do not change unrelated modes, dimensions, plugins, or packaging files unless the command explicitly requires it.",
    ])
    do_not_touch.extend([
        "Unrelated prototypes or game modes",
        "Generated build output folders unless the command is about packaging",
        "Working systems outside the requested scope",
    ])
    acceptance_tests.append(_rule("ack_original_command", "agent_receipt", "AI must restate the parsed must-do and must-not-do items before editing.", severity="warn"))

    if _contains(text, "fps"):
        _add_unique(must_do, "Remove the FPS counter from the player-visible UI path.")
        _add_unique(must_not_do, "Do not leave any player-visible FPS/debug counter behind.")
        _add_unique(regression_risks, "Old FPS/debug UI still appears through a different render route.")
        visual_tests.append(_rule("forbid_visible_fps", "forbidden_text", "No visible FPS text/counter should appear in the final screenshot.", data={"terms": ["FPS", "fps"]}))
        static_checks.append(_rule("static_fps_reference_review", "forbidden_term_static", "Review remaining FPS references; player-visible FPS UI should be removed or gated off.", severity="warn", data={"terms": ["fps", "FPS"]}))

    if _contains(text, "redacted"):
        _add_unique(must_do, "Remove redacted/debug placeholder UI from the player-visible route.")
        visual_tests.append(_rule("forbid_visible_redacted", "forbidden_text", "No visible redacted/debug placeholder text should appear in the final screenshot.", data={"terms": ["redacted", "REDACTED"]}))
        static_checks.append(_rule("static_redacted_reference_review", "forbidden_term_static", "Review remaining redacted/debug placeholder references.", severity="warn", data={"terms": ["redacted", "REDACTED"]}))

    if _contains(text, "points", "score"):
        _add_unique(must_do, "Display the requested points/score information clearly.")
        _add_unique(must_do, "Preserve the scoring data path so the displayed value updates correctly.")
        _add_unique(must_not_do, "Do not replace the scoring display with unrelated debug data.")
        _add_unique(regression_risks, "Points display appears but no longer updates from the real score state.")
        visual_tests.append(_rule("require_points_display", "required_text_or_hook", "Final proof should show or hook-verify the requested points display.", data={"terms": ["POINT", "POINTS", "score", "points"]}))
        static_checks.append(_rule("static_points_reference", "required_term_static", "Project should contain a scoring/points display path after the change.", severity="warn", data={"terms": ["point", "points", "score"]}))

    if _contains(text, "right corner", "right-corner", "top right", "top-right"):
        _add_unique(must_do, "Place the requested UI element in the top-right/right-corner area.")
        visual_tests.append(_rule("top_right_ui_bounds", "ui_zone", "Requested UI should be small and inside the top-right screen bounds.", data={"zone": "top_right"}))

    if _contains(text, "small") and _contains(text, "ui", "points", "counter", "hud"):
        _add_unique(must_do, "Keep the requested UI element compact and unobtrusive.")
        visual_tests.append(_rule("compact_ui", "layout_expectation", "Requested UI should not dominate the gameplay view.", severity="warn"))

    if _contains(text, "off screen", "off-screen", "run off screen", "outside screen"):
        _add_unique(must_do, "Keep all relevant UI inside the visible screen bounds at the configured resolution.")
        _add_unique(must_not_do, "Do not ship UI that clips, runs off screen, or depends on a single untested resolution.")
        _add_unique(regression_risks, "UI fits at one resolution but clips at another.")
        acceptance_tests.append(_rule("ui_bounds_static_required", "static_validator", "Run UI bounds/static layout validation."))

    if _contains(text, "transparent", "transparency"):
        _add_unique(must_do, "Make requested UI backgrounds more transparent without hurting readability.")
        visual_tests.append(_rule("transparent_ui_backgrounds", "layout_expectation", "UI panel backgrounds should be more transparent while text remains readable.", severity="warn"))

    if _contains(text, "no ui background", "no background box", "remove ui box", "remove the box", "background box"):
        _add_unique(must_do, "Remove the background box from the requested UI element.")
        _add_unique(must_not_do, "Do not keep a solid/debug-looking box behind the requested UI element.")
        visual_tests.append(_rule("forbid_requested_ui_box", "layout_expectation", "Requested UI element should not have its old background box.", data={"forbid_box": True}))

    if _contains(text, "persistent", "persist"):
        _add_unique(must_do, "Make the requested spawned objects persist after spawning.")
        _add_unique(must_not_do, "Do not let requested spawned objects disappear because of route reloads or cleanup passes.")
        _add_unique(regression_risks, "Spawned objects exist during proof route but disappear in the real player route.")
        acceptance_tests.append(_rule("spawn_persistence_check", "runtime_or_state_check", "Verify spawned objects remain after the relevant route/state update."))

    if _contains(text, "animal", "animals"):
        _add_unique(must_do, "Represent animals with grown/recognizable forms instead of placeholder egg-like forms.")
        _add_unique(must_not_do, "Do not leave animal visuals looking like eggs/placeholders when grown animals were requested.")
        visual_tests.append(_rule("grown_animal_visuals", "visual_expectation", "Screenshot/proof should show grown animal forms, not egg-like placeholders.", severity="warn"))

    if _contains(text, "urban", "warzone", "sable"):
        _add_unique(must_do, "Apply the change to the real player-visible Urban route, not only a proof/demo route.")
        _add_unique(must_not_do, "Do not verify only a separate proof scene if the player uses a different Urban/world route.")
        _add_unique(regression_risks, "Proof route works but the real player-visible Urban route remains unchanged.")
        runtime_tests.append(_rule("real_urban_route_smoke", "route_runtime_check", "Launch or navigate through the same route the player uses for Urban and capture proof."))

    if _contains(text, "metropolis", "robot", "bot", "select", "selected"):
        _add_unique(must_do, "Preserve the requested robot/bot selection and transfer behavior across routes.")
        _add_unique(must_not_do, "Do not spawn the player into the wrong region when selecting a bot/robot.")
        _add_unique(regression_risks, "Bot selection changes the player's region incorrectly.")
        runtime_tests.append(_rule("bot_selection_route_check", "route_runtime_check", "Verify bot/robot selection keeps the player on the intended route until the command says otherwise."))

    if _contains(text, "terrain") or _has_word(text, "ground", "visible"):
        _add_unique(must_do, "Keep requested terrain/ground visuals visible without breaking performance or route logic.")
        visual_tests.append(_rule("terrain_visibility", "visual_expectation", "Final screenshot should make the requested terrain/ground visible enough to inspect.", severity="warn"))

    if _contains(text, "regression", "regressions", "solid", "robust", "works fine", "check"):
        _add_unique(must_do, "Run regression-oriented validation before delivery.")
        acceptance_tests.append(_rule("regression_required", "regression_validator", "Compare candidate against a baseline when a baseline is available."))
        _add_unique(regression_risks, "Fix introduces unrelated file changes or removes existing working content.")

    if not must_do:
        must_do.append("Implement only the requested game/app change described by the source command.")
        acceptance_tests.append(_rule("manual_acceptance_needed", "manual_review", "Command was broad; AI must document exact interpretation before editing.", severity="warn"))

    if profile.lower() in {"panda3d", "holoverse", "codered", "code_red"}:
        runtime_tests.append(_rule("panda3d_smoke_or_mock", "runtime_validator", "Run Panda3D smoke validation when a system, portable, or packaged runtime is available; otherwise mark visual proof unverified.", severity="warn"))
        if visual_tests:
            acceptance_tests.append(_rule("screenshot_proof_required", "screenshot_validator", "Capture or review screenshot proof for the requested visible change when possible."))

    order = {
        "schema_version": "work_order.v1",
        "bridge_version": "0.5.4-pass4",
        "command_id": command_id,
        "created_at": _now_iso(),
        "project_root": str(Path(project_root).resolve()) if project_root else None,
        "profile": profile,
        "source_command": source,
        "intents": _guess_intents(source),
        "affected_areas": _affected_areas(source, profile),
        "must_do": must_do,
        "must_not_do": must_not_do,
        "do_not_touch": do_not_touch,
        "scope_hints": {
            "allowed_keywords": _scope_keywords(source, profile),
            "prefer_smallest_safe_change": True,
            "review_other_files_before_editing": True,
            "require_reason_for_out_of_scope_files": True,
        },
        "acceptance_tests": acceptance_tests,
        "visual_tests": visual_tests,
        "runtime_tests": runtime_tests,
        "static_checks": static_checks,
        "regression_risks": regression_risks,
        "suggested_commands": [
            "python bridge.py verify-command . --work-order reports/work_order.json",
            "python bridge.py full-pass . --profile {profile} --work-order reports/work_order.json".format(profile=profile),
        ],
        "ai_agent_instructions": [
            "Read this work order before editing.",
            "Implement must_do items before considering any optional cleanup.",
            "Treat must_not_do items as delivery blockers.",
            "Do not broaden scope without adding a note explaining why.",
            "After editing, run verify-command and full-pass, then report unverified items honestly.",
        ],
    }
    return order


def render_work_order_markdown(order: dict[str, Any]) -> str:
    lines: list[str] = [
        "# AI Game Command Work Order",
        "",
        f"- Command ID: `{order.get('command_id')}`",
        f"- Bridge version: `{order.get('bridge_version')}`",
        f"- Profile: `{order.get('profile')}`",
        f"- Source command: {order.get('source_command')}",
        f"- Intents: {', '.join(order.get('intents') or [])}",
        "",
        "## Must Do",
        "",
    ]
    for item in order.get("must_do", []):
        lines.append(f"- {item}")
    lines.extend(["", "## Must Not Do", ""])
    for item in order.get("must_not_do", []):
        lines.append(f"- {item}")
    lines.extend(["", "## Do Not Touch", ""])
    for item in order.get("do_not_touch", []):
        lines.append(f"- {item}")
    areas = order.get("affected_areas") or []
    if areas:
        lines.extend(["", "## Affected Areas", ""])
        for item in areas:
            lines.append(f"- {item}")
    for title, key in [
        ("Acceptance Tests", "acceptance_tests"),
        ("Visual Tests", "visual_tests"),
        ("Runtime Tests", "runtime_tests"),
        ("Static Checks", "static_checks"),
    ]:
        values = order.get(key) or []
        if values:
            lines.extend(["", f"## {title}", ""])
            for rule in values:
                lines.append(f"- `{rule.get('id')}` [{rule.get('severity', 'fail')}]: {rule.get('description')}")
    risks = order.get("regression_risks") or []
    if risks:
        lines.extend(["", "## Regression Risks", ""])
        for item in risks:
            lines.append(f"- {item}")
    scope = order.get("scope_hints") or {}
    if scope:
        lines.extend(["", "## Scope Hints", ""])
        lines.append("- Allowed keywords: " + ", ".join(scope.get("allowed_keywords") or []))
        if scope.get("prefer_smallest_safe_change"):
            lines.append("- Prefer the smallest safe change that satisfies the command.")
    lines.extend(["", "## Suggested Commands", ""])
    for cmd in order.get("suggested_commands", []):
        lines.append(f"```bash\n{cmd}\n```")
    return "\n".join(lines) + "\n"
