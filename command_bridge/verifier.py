from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

EXCLUDED_PARTS = {".git", "__pycache__", ".mypy_cache", ".pytest_cache", "node_modules", "dist", "build", ".venv", "venv"}
TEXT_EXTS = {".py", ".json", ".yaml", ".yml", ".toml", ".txt", ".md", ".ini", ".cfg"}


def _status(ok: bool | None, *, warn: bool = False, skipped: bool = False) -> str:
    if skipped:
        return "skipped"
    if ok is None:
        return "unknown"
    if warn and not ok:
        return "warn"
    return "pass" if ok else "fail"


def _validation(name: str, ok: bool | None, details: Any = None, *, warn: bool = False, skipped: bool = False) -> dict[str, Any]:
    item = {"name": name, "status": _status(ok, warn=warn, skipped=skipped)}
    if details is not None:
        item["details"] = details
    return item


def _iter_text_files(project_root: Path, max_files: int = 5000):
    count = 0
    for path in sorted(project_root.rglob("*")):
        if not path.is_file():
            continue
        try:
            rel_parts = path.relative_to(project_root).parts
        except Exception:
            rel_parts = path.parts
        if any(part in EXCLUDED_PARTS for part in rel_parts):
            continue
        if path.suffix.lower() not in TEXT_EXTS:
            continue
        count += 1
        if count > max_files:
            break
        yield path


def _scan_terms(project_root: Path, terms: list[str], max_files: int = 5000) -> dict[str, Any]:
    hits: list[dict[str, Any]] = []
    lower_terms = [term.lower() for term in terms if term]
    if not lower_terms:
        return {"checked_file_count": 0, "terms": terms, "hits": []}
    checked = 0
    for path in _iter_text_files(project_root, max_files=max_files):
        checked += 1
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception as exc:
            hits.append({"file": str(path), "error": str(exc)})
            continue
        lowered = text.lower()
        found = sorted({terms[idx] for idx, term in enumerate(lower_terms) if term in lowered})
        if found:
            try:
                rel = str(path.relative_to(project_root)).replace("\\", "/")
            except Exception:
                rel = str(path)
            hits.append({"file": rel, "terms": found})
            if len(hits) >= 50:
                break
    return {"checked_file_count": checked, "terms": terms, "hits": hits}


def _changed_scope(changed_files: list[str], allowed_keywords: list[str]) -> dict[str, Any]:
    allowed = [item.lower() for item in allowed_keywords if item]
    out_of_scope: list[str] = []
    for raw in changed_files:
        text = raw.replace("\\", "/").lower()
        if not allowed or not any(keyword in text for keyword in allowed):
            out_of_scope.append(raw)
    return {
        "changed_file_count": len(changed_files),
        "allowed_keywords": allowed_keywords,
        "out_of_scope": out_of_scope,
        "ok": not out_of_scope,
    }


def _report_validation_status(report: dict[str, Any], names: list[str]) -> dict[str, Any]:
    validations = report.get("validations") or []
    found = [item for item in validations if item.get("name") in names]
    return {
        "required_names": names,
        "found": found,
        "ok": any(item.get("status") == "pass" for item in found),
    }


def verify_work_order(
    project_root: str | Path,
    work_order: dict[str, Any],
    *,
    latest_report: dict[str, Any] | None = None,
    changed_files: list[str] | None = None,
    strict_static: bool = False,
    max_files: int = 5000,
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    validations: list[dict[str, Any]] = []

    schema_ok = work_order.get("schema_version") == "work_order.v1" and bool(work_order.get("source_command"))
    validations.append(_validation("work_order_schema", schema_ok, {
        "schema_version": work_order.get("schema_version"),
        "command_id": work_order.get("command_id"),
    }))

    must_do = work_order.get("must_do") or []
    must_not_do = work_order.get("must_not_do") or []
    validations.append(_validation("work_order_tasks_present", bool(must_do and must_not_do), {
        "must_do_count": len(must_do),
        "must_not_do_count": len(must_not_do),
    }))

    if changed_files:
        scope = _changed_scope(changed_files, (work_order.get("scope_hints") or {}).get("allowed_keywords") or [])
        validations.append(_validation("changed_file_scope", scope.get("ok"), scope))
    else:
        validations.append(_validation("changed_file_scope", None, "No changed files supplied. Use --changed-files or a baseline/regression flow for scope enforcement.", skipped=True))

    forbidden_terms: list[str] = []
    required_terms: list[str] = []
    for rule in work_order.get("static_checks") or []:
        kind = rule.get("kind")
        terms = [str(term) for term in rule.get("terms", [])]
        if kind == "forbidden_term_static":
            forbidden_terms.extend(terms)
        elif kind == "required_term_static":
            required_terms.extend(terms)

    if forbidden_terms:
        scan = _scan_terms(root, sorted(set(forbidden_terms)), max_files=max_files)
        ok = not bool(scan.get("hits"))
        validations.append(_validation("forbidden_terms_static", ok, scan, warn=not strict_static))
    else:
        validations.append(_validation("forbidden_terms_static", None, "No forbidden static terms in this work order.", skipped=True))

    if required_terms:
        scan = _scan_terms(root, sorted(set(required_terms)), max_files=max_files)
        ok = bool(scan.get("hits"))
        validations.append(_validation("required_terms_static", ok, scan, warn=True))
    else:
        validations.append(_validation("required_terms_static", None, "No required static terms in this work order.", skipped=True))

    if latest_report:
        delivery = latest_report.get("delivery") or {}
        validations.append(_validation("latest_report_delivery", bool(delivery.get("deliverable")), {
            "deliverable": delivery.get("deliverable"),
            "blockers": delivery.get("blockers", []),
        }))
        if work_order.get("visual_tests"):
            screenshot_status = _report_validation_status(latest_report, ["panda3d_screenshot_proof", "panda3d_runtime_smoke"])
            validations.append(_validation("visual_proof_reported", bool(screenshot_status.get("ok")), screenshot_status, warn=True))
        if any(rule.get("kind") == "regression_validator" for rule in work_order.get("acceptance_tests") or []):
            regression_status = _report_validation_status(latest_report, ["regression_diff"])
            validations.append(_validation("regression_proof_reported", bool(regression_status.get("ok")), regression_status, warn=True))
    else:
        validations.append(_validation("latest_report_delivery", None, "No latest report supplied. Use --report reports/latest_report.json after full-pass.", skipped=True))
        if work_order.get("visual_tests"):
            validations.append(_validation("visual_proof_reported", False, "Visual tests exist but no report/screenshot proof was supplied.", warn=True))

    blocker_statuses = {"fail"}
    deliverable = not any(item.get("status") in blocker_statuses for item in validations)
    return {
        "schema_version": "command_verification.v1",
        "command_id": work_order.get("command_id"),
        "source_command": work_order.get("source_command"),
        "project_root": str(root),
        "strict_static": strict_static,
        "validations": validations,
        "delivery": {
            "deliverable": deliverable,
            "blockers": [item.get("name") for item in validations if item.get("status") in blocker_statuses],
            "known_limitations": [item.get("name") for item in validations if item.get("status") in {"warn", "skipped", "unknown"}],
        },
    }


def render_command_verification_markdown(result: dict[str, Any]) -> str:
    delivery = result.get("delivery") or {}
    lines = [
        "# AI Command Verification Report",
        "",
        f"- Command ID: `{result.get('command_id')}`",
        f"- Source command: {result.get('source_command')}",
        f"- Delivery allowed: **{'YES' if delivery.get('deliverable') else 'NO'}**",
        "",
        "## Checks",
        "",
    ]
    for item in result.get("validations") or []:
        lines.append(f"- **{item.get('name')}**: `{item.get('status')}`")
    blockers = delivery.get("blockers") or []
    if blockers:
        lines.extend(["", "## Blockers", ""])
        for item in blockers:
            lines.append(f"- {item}")
    limits = delivery.get("known_limitations") or []
    if limits:
        lines.extend(["", "## Known Limitations", ""])
        for item in limits:
            lines.append(f"- {item}")
    return "\n".join(lines) + "\n"
